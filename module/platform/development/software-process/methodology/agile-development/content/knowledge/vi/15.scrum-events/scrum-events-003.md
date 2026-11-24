# Xây dựng Sprint Goal làm định hướng chung cho Sprint

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Sprint Goal** là gì, vì sao nó là cam kết gắn với **Sprint Backlog** và khác với danh sách công việc, Product Goal hoặc Definition of Done.
2. Cùng Scrum Team xây dựng một Sprint Goal **có giá trị, rõ ý định, khả thi và đủ linh hoạt** trong Sprint Planning.
3. Chuyển mục tiêu sản phẩm thành kết quả ngắn hạn, lựa chọn Product Backlog Items và lập kế hoạch tạo Increment để phục vụ mục tiêu đó.
4. Dùng Sprint Goal làm tiêu chuẩn ra quyết định khi phát sinh yêu cầu mới, lỗi kỹ thuật, phụ thuộc, thay đổi phạm vi hoặc rủi ro chất lượng trong Sprint.
5. Kiểm tra tiến triển hướng Sprint Goal qua Daily Scrum, Increment và Sprint Review; rút kinh nghiệm từ kết quả thực tế để cải thiện cách lập mục tiêu.

## 1. Vì sao Sprint cần một mục tiêu chung?

Trong một Sprint, Scrum Team có thể làm nhiều việc: sửa lỗi, xây giao diện, tích hợp API, bổ sung kiểm thử hoặc cải thiện hiệu năng. Nếu mỗi thành viên chỉ tập trung vào ticket riêng, đội có thể hoàn thành nhiều việc nhưng **không tạo được kết quả chung có ý nghĩa**.

**Sprint Goal** trả lời câu hỏi:

> **Vì sao Sprint này đáng thực hiện và điều quan trọng nhất mà Scrum Team muốn đạt được trong Sprint là gì?**

Theo Scrum, Sprint Goal là **mục tiêu duy nhất của Sprint** và là **cam kết của Sprint Backlog**. Mục tiêu được xây dựng trong **Sprint Planning**, tạo sự nhất quán và tập trung, giúp Scrum Team làm việc cùng nhau thay vì theo đuổi các sáng kiến riêng rẽ.

### Ví dụ mở đầu

Một đội phát triển nền tảng học trực tuyến dự định thực hiện:

- Hiển thị nút “Tiếp tục học” trên trang chủ.
- Lấy bài học gần nhất của tài khoản đang đăng nhập.
- Kiểm tra học viên còn quyền truy cập vào bài hay không.
- Xử lý trường hợp chưa có tiến độ học.
- Bổ sung kiểm thử tích hợp và kiểm thử phân quyền.

Nếu hỏi “Sprint này làm gì?”, câu trả lời có thể chỉ là danh sách năm việc. Nhưng **điều mà đội muốn tạo ra** là:

> **Sprint Goal:** “Học viên đã có tiến độ hợp lệ có thể mở lại đúng bài học gần nhất từ trang chủ, mà không truy cập nhầm dữ liệu của tài khoản khác.”

Khi một hạng mục trở nên phức tạp, mục tiêu này giúp đội xác định **việc nào phải giữ, việc nào có thể điều chỉnh, việc nào không nên chen vào**. Chẳng hạn, hiệu ứng chuyển động trên nút có thể để sau, nhưng kiểm tra quyền truy cập không thể bỏ để giữ tiến độ.

## 2. Sprint Goal là gì và không phải là gì?

Sprint Goal là một **mục tiêu thống nhất**, đủ rõ để Scrum Team biết Sprint sẽ đóng góp giá trị gì và dùng làm định hướng khi lập kế hoạch hay điều chỉnh công việc. Nó không nhất thiết là một số KPI có thể tăng ngay trong hai tuần; một mục tiêu có thể nói về **khả năng sản phẩm được tạo ra và xác minh**, nếu giá trị và điều kiện thành công được diễn đạt rõ.

### Bốn cách hiểu cần phân biệt

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Sprint Goal** | Vì sao Sprint này có giá trị? Kết quả chung nào cần đạt? | “Học viên mở lại được bài học hợp lệ gần nhất khi đổi thiết bị.” |
| **Product Backlog Items được chọn** | Những thay đổi nào dự kiến giúp đạt mục tiêu? | Đọc tiến độ, hiển thị nút, lọc quyền, xử lý không có dữ liệu. |
| **Kế hoạch thực hiện** | Developers dự định thực hiện, phối hợp và kiểm thử như thế nào? | Chốt quy tắc nghiệp vụ, tích hợp API, xây giao diện, kiểm thử và hoàn thiện Increment. |
| **Definition of Done** | Khi nào phần sản phẩm được coi là Increment hoàn thành với chất lượng cần có? | Tích hợp đạt, test và yêu cầu bảo mật phù hợp được đáp ứng, không bỏ sót tiêu chuẩn chất lượng. |

Sprint Backlog bao gồm **Sprint Goal (why)**, các **Product Backlog Items được chọn (what)** và **kế hoạch thực hiện (how)**. Sprint Goal không thay thế hai phần còn lại; nó giúp hai phần ấy có **lý do và hướng điều chỉnh chung**.

### Các phát biểu dễ bị nhầm với Sprint Goal

- “Hoàn thành 25 story point” là **mục tiêu về số lượng điểm**, không trực tiếp diễn đạt giá trị sản phẩm.
- “Làm xong ticket A, B, C, D” là **danh sách việc**, chưa cho biết vì sao chúng thuộc cùng Sprint.
- “Không còn bug nào” quá tuyệt đối, thiếu phạm vi và không làm rõ điều gì có giá trị nhất.
- “Cải thiện trải nghiệm người dùng” quá rộng để định hướng lựa chọn trong một Sprint.
- “Tăng 30% tỷ lệ hoàn thành khóa học ngay trong Sprint” có thể vượt khả năng kiểm soát hoặc không có đủ thời gian đo tác động; cần phân biệt **khả năng được giao** với **tác động cần kiểm chứng về sau**.

Một Sprint Goal tốt không phải lời hứa rằng mọi điều kiện bên ngoài sẽ thuận lợi. Nó là **cam kết hướng đến mục tiêu**, trong khi kế hoạch cụ thể có thể được thích nghi khi có thêm kiến thức.

## 3. Sprint Goal nằm ở đâu trong hệ thống Scrum?

Để xây dựng mục tiêu đúng, cần thấy mối quan hệ giữa ba tạo tác và ba cam kết của Scrum:

| Tạo tác Scrum | Cam kết gắn với tạo tác | Tác dụng đối với Sprint Goal |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Cung cấp định hướng sản phẩm và những cơ hội được ưu tiên; Sprint Goal là một bước cụ thể hướng tới giá trị sản phẩm. |
| **Sprint Backlog** | **Sprint Goal** | Cho Developers và Scrum Team lý do để chọn việc, phối hợp và điều chỉnh kế hoạch. |
| **Increment** | **Definition of Done** | Cung cấp bằng chứng chất lượng của phần sản phẩm đã hoàn thành, giúp đánh giá tiến triển thực tế hướng Sprint Goal. |

**Product Goal** mô tả trạng thái tương lai mà sản phẩm hướng đến, thường lớn hơn phạm vi một Sprint. **Sprint Goal** làm rõ bước đi có giá trị trong Sprint hiện tại. **Definition of Done** là tiêu chuẩn chất lượng chung cho Increment, không phải một mục tiêu chức năng tùy chọn.

### Ví dụ ba tầng liên kết

> **Product Goal:** Học viên có thể bắt đầu, tiếp tục và hoàn thành việc học trên thiết bị thường dùng mà không mất tiến độ.
>
> **Sprint Goal:** Học viên đã có tiến độ có thể mở đúng bài gần nhất từ trang chủ khi đăng nhập trên thiết bị khác.
>
> **Definition of Done:** Increment tích hợp được, đáp ứng tiêu chí chất lượng chung, kiểm thử quan trọng liên quan đạt, có kiểm soát quyền truy cập và khả năng vận hành theo tiêu chuẩn đã thống nhất.

Mục tiêu sản phẩm giúp xác định **điều gì đáng ưu tiên**; mục tiêu Sprint giúp xác định **điều gì quan trọng ngay bây giờ**; DoD giúp xác định **đã hoàn thành thật sự chưa**. Không nên đổi chất lượng lấy một báo cáo hoàn thành Sprint Goal trông đẹp.

## 4. Ai xây dựng Sprint Goal?

**Toàn Scrum Team cộng tác xác định Sprint Goal trong Sprint Planning.** Mỗi trách nhiệm giải trình đóng góp một góc nhìn:

| Trách nhiệm | Đóng góp điển hình | Không nên hiểu thành |
| --- | --- | --- |
| **Product Owner** | Đề xuất cách sản phẩm có thể tăng giá trị trong Sprint, giải thích Product Goal, thứ tự Product Backlog và nhu cầu các bên liên quan. | Người đơn phương giao sẵn Sprint Goal và từng task cho Developers. |
| **Developers** | Làm rõ tính khả thi, năng lực thực tế, cách tạo Increment, phụ thuộc và rủi ro; cùng xác định mục tiêu và tạo Sprint Backlog. | Người chỉ nhận việc và buộc hoàn tất mọi item đã chọn dù có thông tin mới. |
| **Scrum Master** | Giúp Scrum Team hiểu mục đích Sprint Planning, Sprint Goal và cách tạo cuộc trao đổi hữu ích; hỗ trợ khi có trở ngại phối hợp. | Người chỉ định mục tiêu, phân công việc hoặc tự quyết thứ tự backlog thay Product Owner. |

Trong Scrum Guide, Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả; **Developers chịu trách nhiệm về Sprint Backlog** và cách tạo Increment đáp ứng DoD. Sprint Goal được **Scrum Team xác định chung** trước khi Sprint Planning kết thúc.

### Bất đồng là thông tin cần làm rõ

Product Owner muốn thêm tính năng thông báo nhắc học vì có yêu cầu từ khách hàng. Developers cho biết API tiến độ còn lỗi có thể khiến lời nhắc dẫn đến bài không đúng. Scrum Master giúp hai bên đưa ra câu hỏi:

> “Đâu là kết quả quan trọng hơn đối với người học trong Sprint này: nhận thêm thông báo hay có thể mở lại đúng bài mà không mất dữ liệu?”

Cuộc trao đổi cần dựa trên giá trị, rủi ro và năng lực, không dựa vào ai có chức danh cao hơn. Sau khi thống nhất mục tiêu, Developers có cơ sở dự báo phần công việc phù hợp.

## 5. Xây Sprint Goal trong Sprint Planning: Why – What – How

Sprint Planning đề cập ba chủ đề chính: **Vì sao Sprint có giá trị? Làm gì? Làm như thế nào?** Đây là các chủ đề có liên hệ, không nhất thiết phải đi thành ba phiên họp tách biệt.

### Bước 1 — Làm rõ “Why”: giá trị cần tiến gần hơn

Product Owner đề xuất cách tăng giá trị sản phẩm trong Sprint. Scrum Team xem:

1. Product Goal hiện tại là gì?
2. Vấn đề hoặc nhu cầu quan trọng nhất của người dùng là gì?
3. Product Backlog Item nào đang có bằng chứng và độ khẩn cao?
4. Có rủi ro dữ liệu, bảo mật, vận hành hoặc thời hạn bắt buộc nào cần xử lý trước?
5. Nếu chỉ đạt **một kết quả có ý nghĩa** trong Sprint, kết quả nào đáng lựa chọn?

Đội tạo bản nháp Sprint Goal theo **kết quả**, không bắt đầu bằng việc cộng tất cả công việc mà mọi bên muốn làm.

**Ví dụ bản nháp:**

> “Cho học viên mở lại bài đang học từ trang chủ bằng dữ liệu tiến độ đáng tin cậy.”

Đội cần hỏi thêm: “Đáng tin cậy” trong phạm vi này là thế nào? Cần dùng thiết bị nào? Nếu không có dữ liệu hoặc mất quyền thì sao?

### Bước 2 — Kiểm tra “What”: những Product Backlog Item khả thi

Developers trao đổi với Product Owner để chọn những Product Backlog Items có thể hoàn thành. Việc chọn có thể dựa trên:

- Năng lực của đội trong Sprint, gồm cả hỗ trợ vận hành và công việc đã biết.
- Hiệu quả giao hàng gần đây và khả năng hoàn tất theo DoD.
- Mức hiểu biết về user story, ví dụ, tiêu chí chấp nhận và phụ thuộc.
- Phạm vi cần cho kết quả chung, thay vì nhận tối đa số lượng ticket.
- Công việc cần giảm rủi ro hoặc bảo đảm chất lượng của Increment.

Nếu bản nháp Sprint Goal đòi quá nhiều việc hoặc phụ thuộc chưa thể xử lý trong Sprint, đội cần **điều chỉnh mục tiêu hoặc phạm vi trước khi chốt**.

### Bước 3 — Làm rõ “How”: cách đạt Increment

Developers lập kế hoạch thực hiện: nghiên cứu API, chia nhỏ task, xây dựng, kiểm thử, phối hợp các kỹ năng và xử lý phụ thuộc. Họ có thể chia các Product Backlog Item thành công việc nhỏ hơn, nhưng Scrum không yêu cầu tất cả task phải được phân tích hết ngay tại Sprint Planning.

Khi kế hoạch hình thành, Scrum Team kiểm tra lại:

- Các việc đã chọn có **cùng phục vụ mục tiêu** không?
- Nếu một item khó hơn dự kiến, còn phương án nào **vẫn đạt Sprint Goal**?
- Có tiêu chuẩn chất lượng nào đang bị xem nhẹ không?
- Mục tiêu có đủ rõ để cả đội cùng giải thích mà không tranh cãi nghĩa chính?

Đến cuối Sprint Planning, **Sprint Goal, các Product Backlog Items được chọn và kế hoạch thực hiện** hình thành Sprint Backlog.

### Timebox không phải mục đích

Theo Scrum Guide, Sprint Planning có timebox tối đa **8 giờ với Sprint một tháng**; Sprint ngắn hơn thường cần ít thời gian hơn. Giới hạn thời gian giúp cuộc trao đổi tập trung, không có nghĩa phải dùng đủ giờ hoặc bắt buộc giải quyết mọi ý tưởng tương lai.

## 6. Tiêu chuẩn đánh giá một Sprint Goal hữu ích

Không có mẫu câu bắt buộc, nhưng một Sprint Goal thường hữu ích hơn khi có những đặc điểm sau:

| Tiêu chí | Câu hỏi kiểm tra | Dấu hiệu tích cực |
| --- | --- | --- |
| **Gắn với giá trị** | Nếu đạt, ai được hưởng lợi và vấn đề nào tiến gần giải quyết? | Được nối với Product Goal, nhu cầu thực hoặc rủi ro quan trọng. |
| **Một định hướng chung** | Các thành viên có thể giải thích cùng một kết quả ưu tiên không? | Không phải ba sáng kiến không liên quan chỉ vì cùng nằm trong một Sprint. |
| **Đủ cụ thể** | Cuối Sprint có bằng chứng nào cho biết đã tiến đến mục tiêu? | Có hành vi/khả năng/dữ kiện có thể kiểm tra. |
| **Khả thi với điều kiện hiện biết** | Đội có kỹ năng, năng lực và phụ thuộc cần thiết không? | Không dựa trên việc mọi rủi ro đều tự biến mất. |
| **Đủ linh hoạt về phương tiện** | Khi một ticket hoặc giải pháp không phù hợp, đội còn lựa chọn nào khác? | Mô tả mục đích thay vì đóng đinh từng task. |
| **Không đánh đổi chất lượng** | Để đạt mục tiêu có phải bỏ test, phân quyền hoặc DoD không? | Ranh giới chất lượng giữ nhất quán. |
| **Được hiểu và cùng sở hữu** | Product Owner, Developers và Scrum Master có thống nhất ý nghĩa? | Tất cả biết khi nào cần trao đổi và thích nghi. |

### Cần “đo được” đến mức nào?

Một câu Sprint Goal không nhất thiết phải chứa số phần trăm. Đội có thể dùng **bằng chứng kiểm chứng**:

> “Đội vận hành có thể phát hiện yêu cầu ghi tiến độ thất bại và xác định đúng luồng bị ảnh hưởng trước khi mở rộng phát hành.”

Có thể kiểm tra bằng luồng cảnh báo, dữ liệu quan sát và một tình huống diễn tập. Ngược lại, cam kết “tăng 20% tỷ lệ hoàn thành khóa học trong hai tuần” có thể khó chứng minh khi chu kỳ học kéo dài nhiều tháng.

Vì vậy hãy phân biệt:

- **Khả năng/phần sản phẩm có thể đạt trong Sprint:** kiểm tra được ngay bằng Increment và DoD.
- **Outcome của người dùng cần xác nhận:** có thể cần thử nghiệm, đo lường sau Sprint hoặc nhiều vòng phản hồi.

SMART hoặc OKR có thể là nguồn gợi ý khi diễn đạt mục tiêu, nhưng **không phải công thức bắt buộc của Scrum**. Nếu ép một KPI quá chính xác mà không có dữ liệu, mục tiêu có thể trở nên kém hữu ích hơn.

## 7. So sánh Sprint Goal yếu và tốt hơn

| Phát biểu ban đầu | Vấn đề | Cách viết tốt hơn theo bối cảnh |
| --- | --- | --- |
| “Hoàn thành 20 story point.” | Chú trọng điểm ước lượng, không nêu giá trị. | “Học viên mở lại đúng bài gần nhất từ trang chủ với quyền truy cập hợp lệ.” |
| “Làm xong API, UI, test, tài liệu.” | Là danh sách hoạt động, không có kết quả chung. | “Người dùng có thể bắt đầu và hoàn thành luồng đăng ký khóa học miễn phí một cách nhất quán.” |
| “Nâng cao chất lượng.” | Quá rộng, khó chọn việc hoặc đánh giá. | “Giảm nguy cơ tạo ghi danh trùng bằng cách xử lý gửi lại yêu cầu và chứng minh qua test tích hợp.” |
| “Tăng doanh thu 30% trong Sprint.” | Kết quả có thể bị chi phối bởi yếu tố ngoài đội và thiếu thời gian đo. | “Khách hàng có thể hoàn thành luồng đăng ký gói trả phí đã kiểm chứng trên một kênh thử nghiệm.” |
| “Phát hành đúng ngày bất kể điều gì.” | Dễ dẫn tới bỏ qua chất lượng khi phát sinh rủi ro. | “Giao một lát cắt đặt hàng an toàn, đáp ứng DoD và điều kiện phát hành áp dụng.” |
| “Hoàn thành mọi ticket A, B, C.” | Sprint Goal trùng danh sách và không hỗ trợ thích nghi. | “Nhân viên hỗ trợ có thể tra cứu trạng thái yêu cầu học viên để giải quyết sự cố nhanh hơn.” |
| “Viết lại toàn bộ hệ thống đồng bộ.” | Giải pháp và phạm vi quá lớn hoặc chưa rõ giá trị. | “Chứng minh luồng lưu tiến độ không mất dữ liệu khi yêu cầu gửi lại trong phạm vi đã chọn.” |

Các câu “tốt hơn” vẫn cần được kiểm tra với Product Goal, năng lực đội, dữ liệu và rủi ro cụ thể. Không có mẫu câu nào tự đảm bảo một Sprint Goal là tốt.

### Sprint Goal định hướng, không gói tất cả việc lặt vặt

Một Scrum Team vẫn có thể phải xử lý bảo trì nhỏ, sự cố khẩn hoặc nghĩa vụ không trực tiếp góp vào cùng Sprint Goal. Điều này không bắt buộc đội viết một mục tiêu hỗn hợp vô nghĩa như “Làm tính năng A, sửa bug B, nâng cấp C và họp D”. Đội cần minh bạch năng lực dành cho các công việc đó, quản lý tác động lên mục tiêu chung và trao đổi với Product Owner khi cần.

## 8. Một ví dụ đầy đủ: từ Product Goal đến Sprint Backlog

### 8.1. Bối cảnh và dữ liệu

Product Goal của nền tảng học trực tuyến:

> “Học viên học liên tục giữa các thiết bị và không mất tiến độ đã ghi nhận.”

Phản hồi từ thử nghiệm gần đây cho thấy người học khó tìm lại bài. Trong khi đó, đội kỹ thuật phát hiện một số request đọc tiến độ có thể trả kết quả sai khi khóa học bị thu hồi quyền.

Product Backlog được sắp thứ tự như sau (thứ tự minh họa):

| Item | Giá trị hoặc rủi ro | Mức hiểu biết | Dự kiến liên quan Sprint |
| --- | --- | --- | --- |
| A. Lấy bài gần nhất còn quyền truy cập | Tránh người học chọn nhầm hoặc thấy nội dung không được phép | Luồng và ví dụ đã rõ | Cao |
| B. Hiển thị nút “Tiếp tục học” | Giảm thời gian tìm bài | Có prototype và tiêu chí chấp nhận | Cao |
| C. Xử lý không có tiến độ hoặc API lỗi | Tránh gây hiểu nhầm cho người học | Có quy tắc, cần kiểm thử | Cao |
| D. Đồng bộ vị trí video từng giây | Có thể tăng tính liền mạch | Quy tắc xung đột chưa rõ | Cần khám phá thêm |
| E. Thêm hoạt ảnh khi hoàn thành bài | Tăng trải nghiệm cảm nhận | Chưa có bằng chứng tác động | Thấp |

### 8.2. Cùng tạo Sprint Goal

Ở Sprint Planning:

1. Product Owner giải thích rằng việc **tìm lại đúng bài** là vấn đề hiện có thể cải thiện.
2. Developers xác nhận A, B, C có thể tạo thành một lát cắt xuyên suốt, nhưng item D chưa đủ thông tin về đồng bộ.
3. Scrum Team thống nhất Sprint Goal:

> **“Học viên đã có tiến độ hợp lệ có thể mở lại bài gần nhất từ trang chủ, không nhìn thấy nội dung ngoài quyền truy cập.”**

4. Developers lựa chọn A, B, C theo năng lực và lập kế hoạch tích hợp, UI, test phân quyền và kiểm thử lỗi.

Sprint Goal này **không yêu cầu** hoàn tất item D hoặc E, nhưng vẫn là bước tiến có giá trị hướng Product Goal. Nếu muốn giải quyết một rủi ro của D bằng spike nhỏ mà không ảnh hưởng Sprint Goal, Developers và Product Owner có thể cân nhắc theo năng lực.

### 8.3. Sprint Backlog minh họa

| Thành phần | Nội dung |
| --- | --- |
| **Why — Sprint Goal** | Học viên mở lại đúng bài gần nhất, có kiểm soát quyền truy cập. |
| **What — PBI đã chọn** | A. Lấy bài hợp lệ; B. Nút trang chủ; C. Không có tiến độ và lỗi API. |
| **How — Kế hoạch của Developers** | Chốt quy tắc “gần nhất”, tích hợp API, xử lý quyền, xây UI, viết/chạy test, tích hợp Increment. |
| **Điều kiện chất lượng** | Tuân thủ DoD; kiểm thử phân quyền và các trường hợp lỗi quan trọng. |
| **Phụ thuộc** | Cần xác nhận cách API phân biệt bài đã bị thu hồi quyền. |
| **Cách xem tiến triển** | Demo luồng thật trên tài khoản hợp lệ/không hợp lệ; kết quả test, trở ngại và Increment đạt DoD. |

### 8.4. Ví dụ tiêu chí chấp nhận hỗ trợ mục tiêu

| Tình huống | Dữ kiện trước thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Học viên có bài gần nhất hợp lệ | Tài khoản A có quyền khóa X, đã lưu bài 4 của X | Nút mở bài 4 thuộc X. |
| Bài mới nhất đã hết quyền | Bài 5 của Y mới hơn nhưng A không còn quyền | Không mở nội dung Y; chọn bài hợp lệ khác theo quy tắc đã thống nhất hoặc hiển thị trạng thái phù hợp. |
| Không có tiến độ | A chưa bắt đầu khóa nào | Không hiện thông tin bài giả; có hướng chọn khóa học. |
| Khác tài khoản | B đăng nhập trên thiết bị từng dùng bởi A | B không nhìn thấy dữ liệu tiến độ riêng của A. |
| API đọc lỗi | Không thể xác nhận tiến độ | Không thông báo sai rằng người dùng chưa từng học; phản hồi lỗi phù hợp. |

Tiêu chí chấp nhận làm rõ các hành vi riêng của item, còn **DoD** quy định chất lượng chung của Increment. Kết quả kiểm thử cho phép biết Sprint Goal có đạt **bằng chứng sản phẩm** hay chưa, thay vì chỉ dựa vào số ticket đóng.

## 9. Sprint Goal giúp chọn hành động khi tình huống thay đổi

Trong Sprint, Developers có thể học được thông tin mới: item lớn hơn dự kiến, API hỏng, xuất hiện lỗi dữ liệu, khách hàng đề xuất tính năng mới hoặc số người tham gia thực tế ít hơn. Sprint Goal là **la bàn ra quyết định**, không phải rào cản ngăn mọi thay đổi.

### Sơ đồ quyết định thực tế

~~~mermaid
flowchart TD
    A["Xuất hiện yêu cầu hoặc thông tin mới"] --> B{"Có ảnh hưởng đến Sprint Goal hoặc chất lượng bắt buộc?"}
    B -- "Không rõ" --> C["Làm rõ tác động, phạm vi và độ khẩn"]
    C --> B
    B -- "Có" --> D["Developers kiểm tra kế hoạch và phương án"]
    D --> E{"Có thể thích nghi mà vẫn bảo vệ Sprint Goal và DoD?"}
    E -- "Có" --> F["Điều chỉnh Sprint Backlog; trao đổi với PO khi cần"]
    E -- "Chưa thể" --> G["Minh bạch rủi ro, thương lượng phạm vi và lựa chọn"]
    B -- "Không" --> H["Ghi vào Product Backlog để PO cân nhắc hoặc xử lý theo chính sách khẩn"]
    F --> I["Tích hợp, kiểm thử, kiểm tra lại kết quả"]
    G --> I
    H --> I
~~~

Sơ đồ chỉ là công cụ thảo luận. Nếu Sprint Goal **trở nên lỗi thời**, chỉ Product Owner có quyền **hủy Sprint** theo Scrum Guide. Hủy Sprint là tình huống đặc biệt, không phải thủ thuật thường xuyên để sửa một kế hoạch khó thực hiện.

### Tình huống 1 — Có yêu cầu mới không liên quan

Giữa Sprint, bên kinh doanh muốn thêm hiệu ứng huy hiệu trong bài học. Mục tiêu hiện tại là mở lại bài hợp lệ. Product Owner có thể đưa yêu cầu mới vào Product Backlog, đánh giá giá trị và thứ tự cho tương lai. Không cần phá sự tập trung của Sprint chỉ vì người yêu cầu có ảnh hưởng lớn.

### Tình huống 2 — Một item lớn hơn dự kiến

API “bài gần nhất” cần thêm bước kiểm tra quyền nên mất nhiều thời gian hơn. Developers không có nghĩa vụ giữ nguyên mọi task. Họ có thể:

- Ưu tiên luồng hợp lệ và các tình huống phân quyền bắt buộc.
- Đơn giản hóa một số thành phần giao diện không tác động tới giá trị chính.
- Phối hợp để hoàn thành lát cắt tích hợp trước khi bắt đầu việc ít quan trọng.
- Minh bạch tình hình với Product Owner; thương lượng phạm vi nếu cần.

**Không thể cắt bỏ điều kiện phân quyền, tính toàn vẹn dữ liệu hay DoD** chỉ để tuyên bố Sprint Goal đã hoàn thành.

### Tình huống 3 — Xuất hiện lỗi sản xuất nghiêm trọng

Một lỗi khiến tiến độ học của nhiều người bị ghi sai, gây nguy cơ mất dữ liệu. Scrum Team cần xử lý theo mức độ nghiêm trọng; Developers có thể phải điều chỉnh Sprint Backlog và cập nhật Product Owner. Scrum Master giúp loại bỏ trở ngại phối hợp.

Sự cố khẩn có thể ảnh hưởng mục tiêu đang theo đuổi. Đội nên minh bạch tác động và lựa chọn thay vì giữ nguyên báo cáo “đúng kế hoạch” bằng mọi giá.

### Tình huống 4 — Mục tiêu không còn giá trị

Giữa Sprint, tổ chức quyết định ngừng sản phẩm vì một thay đổi chiến lược đã được xác nhận. Sprint Goal có thể trở nên lỗi thời. **Product Owner là người có quyền hủy Sprint**; những phần việc đã hoàn thành cần được xem xét lại phù hợp. Không nên hủy Sprint chỉ vì velocity thấp hoặc vì một hạng mục khó hơn ước tính.

## 10. Kiểm tra tiến triển hướng Sprint Goal trong Daily Scrum

**Daily Scrum** là sự kiện 15 phút dành cho Developers mỗi ngày làm việc của Sprint. Mục đích là **kiểm tra tiến độ hướng Sprint Goal** và điều chỉnh Sprint Backlog khi cần.

Không bắt buộc đi theo ba câu hỏi “Hôm qua tôi làm gì? Hôm nay tôi làm gì? Bị chặn không?”. Đội có thể tập trung trực tiếp vào mục tiêu:

1. **Đã có bằng chứng gì** cho thấy Increment đang tiến gần Sprint Goal?
2. **Điều gì đang ngăn** nhóm đạt mục tiêu hoặc đáp ứng DoD?
3. **Hôm nay cần phối hợp và điều chỉnh gì** để hoàn tất phần có giá trị nhất?

### Ví dụ một Daily Scrum ngắn

> **Sprint Goal:** Học viên mở đúng bài hợp lệ gần nhất từ trang chủ.
>
> **Bằng chứng:** Luồng trên một tài khoản đã chạy, nhưng bài vừa hết quyền vẫn còn xuất hiện.
>
> **Ảnh hưởng:** Chưa đạt hành vi và DoD về kiểm soát quyền; chưa thể gọi là Done.
>
> **Điều chỉnh:** Hai Developers phối hợp sửa lọc quyền và thêm integration test. Cả đội ưu tiên giải quyết vấn đề này trước khi làm hoạt ảnh nút.
>
> **Điểm kiểm tra:** Chạy lại test và xem kết quả build trước cuối ngày.

Kết quả Daily Scrum là **kế hoạch hành động được thích nghi**, không phải biên bản từng người đã bận thế nào. Nếu cần trao đổi kỹ thuật dài hơn, các thành viên liên quan tiếp tục sau sự kiện.

### Minh bạch Sprint Backlog

Scrum Team có thể dùng bảng công việc chung để thấy:

- Những item nào đã đạt DoD, item nào còn kiểm thử hoặc review.
- Việc gì đang **bị chặn**, bởi nguyên nhân và phụ thuộc nào.
- Phần việc nào trực tiếp góp vào Sprint Goal.
- Sự thay đổi kế hoạch hoặc rủi ro mới.

**Sprint Backlog là kế hoạch sống của Developers**, không phải hợp đồng bất biến. Minh bạch giúp hỗ trợ hành động nhanh, không phải để biến số ticket hoặc story point thành công cụ phạt cá nhân.

## 11. Kiểm tra kết quả trong Sprint Review

**Sprint Review** là dịp Scrum Team và các bên liên quan kiểm tra kết quả Sprint và quyết định những thay đổi cho tương lai. Sprint Goal là điểm tham chiếu để giải thích **đội đã cố gắng tạo giá trị gì** và Increment thực tế đã hỗ trợ điều đó ra sao.

Một cấu trúc trao đổi gọn:

1. **Nhắc Sprint Goal và Product Goal** liên quan.
2. **Cho thấy Increment thật** đáp ứng Definition of Done; phân biệt rõ công việc chưa đạt DoD.
3. **Trình bày bằng chứng**: luồng hoạt động, kết quả kiểm thử, phản hồi người dùng, rủi ro còn lại.
4. **Trao đổi bối cảnh thay đổi**: nhu cầu mới, dữ liệu vận hành, nghĩa vụ, mục tiêu tổ chức.
5. **Thích nghi Product Backlog** nếu có lý do; Product Owner chịu trách nhiệm thứ tự backlog.

### Ba kết quả Sprint có thể xảy ra

| Tình hình | Cách trình bày có trách nhiệm | Quyết định tiếp theo |
| --- | --- | --- |
| **Đạt mục tiêu và Increment đáp ứng DoD** | Demo luồng hoạt động, nêu bằng chứng và giới hạn | Nhận phản hồi, cân nhắc bước tiếp theo của Product Goal. |
| **Có Increment đạt DoD nhưng chưa đạt toàn bộ ý định Sprint Goal** | Minh bạch phần có thể sử dụng và khoảng cách so với mục tiêu | Phân tích nguyên nhân, sắp xếp lại Product Backlog; không giả vờ đã đạt. |
| **Chưa có Increment đạt DoD cho mục tiêu** | Nêu rõ điều đã học, lỗi/điểm chặn và tác động | Điều chỉnh kế hoạch, phạm vi, ưu tiên và thực hành cải tiến; không gắn Done hình thức. |

Sprint Review **không phải cổng duy nhất** cho phép phát hành: một Increment đáp ứng DoD và các điều kiện áp dụng có thể được giao trước khi Sprint kết thúc. Mục tiêu của Review vẫn là **kiểm tra và học hỏi**.

### Đánh giá giá trị đúng mức

Nếu người dùng mở lại đúng bài trong bản thử nhưng chưa có đủ dữ liệu để kết luận tỷ lệ hoàn thành khóa học tăng, hãy báo:

> “Lát cắt mở bài đã hoạt động và đạt tiêu chí kiểm chứng. Chúng ta có bằng chứng cải thiện khả năng tìm lại bài trong thử nghiệm ban đầu; tác động lên tỷ lệ hoàn thành khóa học cần quan sát thêm.”

Đừng dùng một con số ước lượng hoặc một buổi demo làm bằng chứng quá mức cho outcome dài hạn.

## 12. Sprint Retrospective: cải thiện cách đạt mục tiêu

**Sprint Retrospective** tập trung vào cách Scrum Team tăng chất lượng và hiệu quả làm việc. Không nên chỉ hỏi “Đạt Sprint Goal chưa?” mà cần hỏi **vì sao mục tiêu hữu ích hoặc không hữu ích để định hướng nhóm**.

Các câu hỏi có thể thảo luận:

- Sprint Goal có rõ để giúp quyết định khi phát sinh yêu cầu mới không?
- Các item được chọn có thực sự liên kết với mục tiêu hay là nhiều việc rời rạc?
- Team có phát hiện phụ thuộc quan trọng quá muộn không?
- Có khi nào chất lượng hoặc DoD bị đánh đổi để “hoàn tất” mục tiêu?
- Cách nói về tiến triển có dựa trên Increment và bằng chứng hay chỉ dựa vào phần trăm task?
- Có thể cải thiện việc trao đổi trước Sprint Planning, refinement hoặc phân chia lát cắt không?

### Ví dụ một cải tiến có thể kiểm chứng

**Quan sát:** Sprint Goal lần trước là “Hoàn thành tất cả item đã chọn”, khiến đội liên tục chuyển giữa công việc UI, báo cáo và API không liên quan.

**Giả thuyết cải tiến:** Ở Sprint Planning tiếp theo, Scrum Team sẽ nói rõ outcome chung, chọn item theo mức đóng góp và viết một câu mục tiêu để mọi thành viên cùng hiểu.

**Thử nghiệm:** Áp dụng trong một Sprint; tại Daily Scrum, thử nêu quyết định dựa trên mục tiêu; cuối Sprint xem tần suất đổi việc và mức hoàn thành luồng tích hợp.

**Điểm xem lại:** Retrospective tiếp theo. Nếu vẫn bị gián đoạn vì sự cố sản xuất, cần giải quyết cả chính sách nhận công việc khẩn chứ không chỉ sửa câu chữ Sprint Goal.

## 13. Những dạng Sprint Goal khác nhau theo bản chất công việc

Không phải Sprint nào cũng có một giao diện mới. Sprint Goal có thể xoay quanh **khả năng kinh doanh, chất lượng, giảm rủi ro hoặc kiểm chứng một giả thuyết**, miễn có mục đích chung có ý nghĩa và kết quả kiểm tra phù hợp.

| Bối cảnh | Ví dụ Sprint Goal | Bằng chứng nên xem |
| --- | --- | --- |
| **Phát triển tính năng** | “Học viên ghi danh được khóa miễn phí đang nhận học viên và nhìn thấy khóa trong danh sách học.” | Luồng hoạt động, ca lỗi quan trọng, Increment đạt DoD. |
| **Ổn định sản phẩm** | “Ngăn yêu cầu thanh toán gửi lại tạo giao dịch trùng trong phạm vi tích hợp hiện có.” | Test gửi lặp, kiểm thử tích hợp, dữ liệu giao dịch đúng. |
| **Tích hợp** | “Luồng lấy tiến độ từ API đối tác hoạt động tin cậy với quyền truy cập hợp lệ.” | Contract test, integration test, xử lý trạng thái lỗi. |
| **Cải thiện vận hành** | “Đội vận hành phát hiện được lỗi lưu tiến độ và xác định đối tượng ảnh hưởng theo tiêu chuẩn sản phẩm.” | Thử cảnh báo, log phù hợp, diễn tập chẩn đoán. |
| **Khám phá bất định** | “Xác định và kiểm chứng giải pháp khả thi cho xung đột tiến độ giữa hai thiết bị để quyết định phạm vi bước tiếp theo.” | Bằng chứng thử nghiệm và quyết định rõ; cần xem có Increment đáp ứng DoD nào được tạo ra trong Sprint hay không. |

**Lưu ý với Sprint khám phá:** Scrum Team vẫn có trách nhiệm tạo Increment có giá trị, dùng được và đáp ứng DoD mỗi Sprint. Một spike hoặc nghiên cứu có thể giảm rủi ro và hỗ trợ sản phẩm, nhưng **không tự động được gọi là Increment** chỉ vì đã tạo báo cáo. Cần minh bạch sự khác biệt giữa học hỏi, nguyên mẫu và phần sản phẩm thực sự hoàn thành.

### Khi đội có cả công việc liên tục lẫn công việc theo mục tiêu

Một nhóm có thể phải xử lý ticket hỗ trợ trong khi phát triển sản phẩm. Đừng che khối lượng hỗ trợ khi lập Sprint Goal. Hãy xem năng lực thực tế, loại công việc và chính sách cho sự cố khẩn. Nếu tính chất công việc chủ yếu là luồng liên tục với ưu tiên thay đổi thường xuyên, nhóm cũng có thể cân nhắc **Kanban** hoặc phối hợp thực hành quản lý dòng việc phù hợp; không phải mọi đội bắt buộc dùng Sprint.

Các thực hành **XP** như kiểm thử tự động, tích hợp liên tục, refactor và lập trình cặp giúp Scrum Team thay đổi kỹ thuật an toàn hơn khi Sprint Backlog được thích nghi. XP hỗ trợ chất lượng và phản hồi, không thay thế Sprint Goal hay Product Goal.

## 14. Một quy trình ngắn để viết Sprint Goal có thể dùng ngay

Khi Sprint Planning gặp khó khăn, Scrum Team có thể dùng khung trao đổi sau:

### Bước A — Hoàn thành câu “Sprint này có giá trị vì…”

Ví dụ:

> “Sprint này có giá trị vì học viên đang mất thời gian tìm lại bài đã học; một luồng tiếp tục học đúng sẽ giảm thao tác tìm kiếm.”

Đây là **lý do**, không phải kế hoạch kỹ thuật.

### Bước B — Xác định một thay đổi có thể kiểm tra

Hỏi: “Nếu Sprint thành công, **người dùng hoặc hệ thống có khả năng gì mà trước đó chưa có hoặc chưa đáng tin?**”

> “Học viên đăng nhập trên điện thoại có thể mở bài hợp lệ gần nhất từ trang chủ.”

Nếu chưa có cách kiểm chứng kết quả, hãy xem lại câu diễn đạt.

### Bước C — Xác định ranh giới giá trị và chất lượng

Hỏi:

- Hạng mục nào nằm **ngoài phạm vi** Sprint Goal?
- Điều kiện nào là **bắt buộc** để tính năng không gây hại?
- Nếu phải điều chỉnh, đội có thể giảm **phương tiện hoặc phần tùy chọn** nào?

Ví dụ: Chưa cần đồng bộ vị trí video từng giây; nhưng không thể bỏ kiểm tra quyền truy cập vào bài học.

### Bước D — Kiểm tra với năng lực và kế hoạch

Developers dựa trên năng lực, DoD và hạng mục đã hiểu để dự báo. Nếu một mục tiêu chỉ đạt được khi mọi rủi ro đều thuận lợi hoặc phải làm rất nhiều việc không liên quan, hãy thu hẹp **kết quả** hoặc chia thành các bước qua nhiều Sprint.

### Bước E — Viết câu mục tiêu cuối cùng

Một dạng gợi ý:

> **“[Nhóm người dùng/đối tượng] có thể [kết quả hoặc khả năng có giá trị] trong [phạm vi quan trọng], đồng thời [ràng buộc cốt lõi nếu cần làm rõ].”**

Không bắt buộc dùng mẫu câu này. Kết quả có thể ngắn hơn nếu cả Scrum Team cùng hiểu rõ.

### Bước F — Kiểm tra sự đồng thuận

Mời mỗi người tự trả lời:

1. “Sprint Goal là gì và vì sao nó quan trọng?”
2. “Nếu phải bỏ một item, ta sẽ quyết định dựa trên điều gì?”
3. “Điều gì chứng minh kết quả đã đạt và chất lượng không bị hạ?”

Nếu câu trả lời khác nhau về bản chất, Scrum Team cần làm rõ **trước khi kết thúc Sprint Planning**.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| **Viết Sprint Goal sau khi đã nhồi đầy Sprint** | Mục tiêu trở thành khẩu hiệu hợp thức hóa danh sách | Thảo luận giá trị và “Why” từ đầu, rồi chọn việc phù hợp. |
| **Biến Sprint Goal thành số story point** | Đội tối ưu số lượng thay vì outcome hoặc chất lượng | Diễn đạt kết quả chung có thể kiểm tra; dùng point chỉ để hỗ trợ dự báo khi hữu ích. |
| **Gộp nhiều mục tiêu không liên quan** | Khi phát sinh thay đổi, không biết điều gì phải giữ | Chọn một trọng tâm; minh bạch những việc khác chiếm năng lực. |
| **Mục tiêu quá mơ hồ** | Daily Scrum không biết đang tiến triển đến đâu | Chỉ rõ người dùng, khả năng hoặc rủi ro cần giải quyết. |
| **Mục tiêu buộc một giải pháp cụ thể** | Khó thích nghi khi kỹ thuật hoặc nhu cầu thay đổi | Nêu giá trị/khả năng trước; để Developers chọn cách thực hiện. |
| **Product Owner đơn phương áp mục tiêu** | Mất sự cộng tác về khả thi, rủi ro và năng lực | Toàn Scrum Team xác định Sprint Goal trong Sprint Planning. |
| **Mọi item được chọn đều coi là cam kết bất biến** | Dễ bỏ qua thông tin mới hoặc hạ chất lượng để chạy theo danh sách | Giữ Sprint Goal, điều chỉnh kế hoạch và thương lượng phạm vi khi cần. |
| **Không nhìn Sprint Goal ở Daily Scrum** | Trở thành buổi báo cáo từng người | Kiểm tra bằng chứng tiến triển và điều chỉnh Sprint Backlog. |
| **Giữ mục tiêu bằng mọi giá kể cả vi phạm DoD** | Increment lỗi, rủi ro chuyển sang người dùng | Không hạ chất lượng; minh bạch điều chưa đạt và điều chỉnh phạm vi/đánh giá. |
| **Coi Review là nơi chỉ tuyên bố đạt mục tiêu** | Thiếu phản hồi và cơ hội thích nghi Product Backlog | Cho thấy Increment thật, bối cảnh và học hỏi mới. |
| **Hủy Sprint vì một story khó hơn dự kiến** | Mất nhịp tập trung, nhầm kế hoạch với mục tiêu | Trước tiên điều chỉnh kế hoạch và phạm vi; chỉ PO hủy khi Sprint Goal lỗi thời. |
| **Đặt KPI phụ thuộc bên ngoài mà không có khả năng kiểm tra trong Sprint** | Không thể biết đã đạt mục tiêu ngay cả khi Increment hoàn tất | Chọn khả năng sản phẩm có thể xác nhận trong Sprint và theo dõi outcome sau đó. |

## 16. Bài tập thực hành

### Bài tập 1 — Chuyển danh sách task thành Sprint Goal

Một Sprint dự kiến có các việc:

- Hiển thị bài học gần nhất trên trang chủ.
- Kiểm tra quyền truy cập khóa học.
- Thêm thông báo khi dịch vụ tiến độ lỗi.
- Kiểm thử người dùng mới chưa có dữ liệu.
- Đổi màu nút “Tiếp tục học”.

**Yêu cầu:** Viết một Sprint Goal có giá trị người dùng, chỉ ra việc nào trực tiếp cần để đạt mục tiêu, việc nào có thể linh hoạt và điều kiện nào không thể cắt giảm.

**Gợi ý:** Việc đổi màu nút có thể không thiết yếu; kiểm tra quyền truy cập là điều kiện bắt buộc. Mục tiêu nên mô tả **mở lại đúng bài hợp lệ**, không phải tổng số việc.

### Bài tập 2 — Chọn giữa ba Sprint Goal

Ba đề xuất cho Sprint hai tuần:

A. “Hoàn thành 30 story point và tất cả ticket được giao.”

B. “Học viên đăng nhập có thể ghi danh vào khóa miễn phí đang nhận học viên và xem khóa trong danh sách học.”

C. “Tăng 40% tỷ lệ giữ chân khách hàng trong đúng hai tuần tới.”

**Yêu cầu:** Chọn đề xuất có cơ sở nhất, giải thích điểm yếu của hai đề xuất còn lại và những thông tin vẫn phải xác minh trước khi chốt.

**Gợi ý:** B mô tả một khả năng người dùng kiểm chứng được; cần xác nhận năng lực, quy tắc ghi danh, quyền truy cập, chất lượng và mức phù hợp với Product Goal. A chỉ là số lượng việc; C có thể là outcome dài hạn khó kiểm soát trong phạm vi Sprint.

### Bài tập 3 — Điều chỉnh khi có lỗi giữa Sprint

Sprint Goal: “Người dùng mở lại đúng bài hợp lệ gần nhất trên thiết bị khác.”

Ngày thứ tư, Developers phát hiện API đôi khi trả bài đã bị thu hồi quyền. Một bên liên quan đồng thời yêu cầu thêm huy hiệu thành tích.

**Yêu cầu:** Nêu ba quyết định cần đưa ra:

1. Làm gì trước để bảo vệ Sprint Goal và DoD?
2. Yêu cầu huy hiệu được xử lý thế nào trong Product Backlog?
3. Nếu API cần sửa quá lớn, Developers và Product Owner nên thương lượng phạm vi ra sao mà không đánh đổi quyền truy cập?

**Gợi ý:** Không gọi story Done khi lỗi phân quyền chưa xử lý. Có thể giảm phần UI tùy chọn, ưu tiên lát cắt an toàn hoặc đánh giá lại mục tiêu nếu điều kiện đã thay đổi căn bản.

### Bài tập 4 — Đánh giá Sprint Goal từ bằng chứng

Cuối Sprint, đội báo “đã hoàn tất 90% task”, nhưng:

- Luồng mở bài đúng trên thiết bị thử của developer.
- Test phân quyền trên hai tài khoản vẫn thất bại.
- Người dùng thử không tìm thấy nút “Tiếp tục học” trên điện thoại.
- Một số phần giao diện đã vượt qua code review.

**Yêu cầu:** Viết bản cập nhật Sprint Review khoảng 100–150 từ, phân biệt **phần có bằng chứng**, **phần chưa đáp ứng DoD**, **mức đạt Sprint Goal** và **điều cần kiểm tra/ưu tiên tiếp**.

**Gợi ý:** Không dùng “90% task” để kết luận Sprint Goal đã đạt. Nêu trung thực rủi ro quyền truy cập và phản hồi người dùng.

### Bài tập 5 — Mô phỏng Sprint Planning

Chia nhóm thành Product Owner, Scrum Master và Developers. Trong 20 phút:

1. Product Owner trình bày Product Goal và ba nhu cầu ưu tiên.
2. Developers nêu khả năng, phụ thuộc, tiêu chuẩn chất lượng và mức bất định.
3. Cả Scrum Team đề xuất hai Sprint Goal, thảo luận mục tiêu nào có giá trị và khả thi hơn.
4. Developers chọn một số Product Backlog Items, lập kế hoạch ban đầu.
5. Mỗi thành viên tự diễn đạt Sprint Goal để kiểm tra mức thống nhất.

**Tiêu chí đánh giá:** Một mục tiêu chung, ý nghĩa rõ; các item liên quan; không áp đặt danh sách bất biến; có cách kiểm tra Increment và phương án xử lý trở ngại.

### Bài tập 6 — Sprint cải tiến kỹ thuật có mục tiêu gì?

Đội ghi nhận lỗi đồng bộ tiến độ lặp lại qua nhiều đợt phát hành. Một người đề xuất Sprint Goal: “Refactor codebase và tăng coverage.”

**Yêu cầu:** Viết lại mục tiêu sao cho liên quan đến một năng lực hoặc rủi ro sản phẩm cụ thể. Chọn hai bằng chứng kiểm chứng được trong Sprint và một tín hiệu theo dõi chất lượng ở các Sprint tiếp theo.

**Gợi ý:** Có thể tập trung vào việc loại bỏ lỗi mất dữ liệu khi request gửi lại, với integration test cho các trường hợp quan trọng. Coverage chỉ là tín hiệu phụ, không tự chứng minh hành vi đúng.

## 17. Checklist trước khi chốt Sprint Goal

Trước khi kết thúc Sprint Planning, Scrum Team có thể rà soát:

- [ ] Mục tiêu có trả lời rõ **“Vì sao Sprint này có giá trị?”**?
- [ ] Mục tiêu có liên kết với Product Goal hoặc vấn đề sản phẩm có căn cứ?
- [ ] Cả Scrum Team đã cộng tác xây và hiểu **một định hướng chung**?
- [ ] Mục tiêu có diễn đạt **kết quả/khả năng cần đạt**, thay vì chỉ cộng ticket hoặc story point?
- [ ] Có bằng chứng nào cho phép xem xét mức đạt mục tiêu vào cuối Sprint?
- [ ] Phần người dùng nào được hưởng lợi, phạm vi nào chưa nằm trong Sprint?
- [ ] Developers đã xem xét năng lực thực tế, phụ thuộc và mức bất định?
- [ ] Product Backlog Items được chọn có phục vụ mục tiêu hoặc nghĩa vụ rõ ràng?
- [ ] Sprint Backlog có **Sprint Goal, item được chọn và kế hoạch thực hiện**?
- [ ] Definition of Done và các yêu cầu an toàn, bảo mật, dữ liệu, vận hành vẫn được giữ?
- [ ] Có thể thay đổi kế hoạch, phối hợp hoặc phạm vi mà **không làm nguy hiểm Sprint Goal**?
- [ ] Khi có yêu cầu mới hay sự cố, người liên quan biết ai cần trao đổi và quyết định?
- [ ] Daily Scrum sẽ kiểm tra tiến triển hướng Sprint Goal thay vì chỉ đọc trạng thái?
- [ ] Sprint Review sẽ cho thấy Increment thật và dùng phản hồi để cân nhắc backlog?
- [ ] Nếu không đạt mục tiêu, đội có sẵn sàng nói rõ bằng chứng và học hỏi thay vì đổi nhãn Done?

Checklist chỉ để hỗ trợ đối thoại, không phải một “cổng” thủ tục bắt buộc ngoài Scrum. Với một Sprint nhỏ, mục tiêu có thể được diễn đạt rất ngắn nếu vẫn rõ ràng và hữu ích.

## 18. Ghi nhớ

- **Sprint Goal là mục tiêu duy nhất của Sprint và là cam kết của Sprint Backlog.** Nó tạo sự tập trung, hợp tác và linh hoạt về công việc chính xác cần làm.
- **Toàn Scrum Team xây Sprint Goal trong Sprint Planning.** Product Owner làm rõ giá trị; Developers dự báo và lập kế hoạch tạo Increment; Scrum Master giúp đội sử dụng Scrum hiệu quả.
- **Sprint Backlog gồm Why – What – How:** Sprint Goal, các Product Backlog Items được chọn và kế hoạch của Developers.
- **Mục tiêu khác danh sách ticket, velocity và lời hứa KPI tuyệt đối.** Hãy chọn một kết quả có giá trị, đủ rõ và khả thi, gắn với Product Goal.
- **Sprint Goal hỗ trợ thích nghi, không đóng băng kế hoạch.** Khi học thêm, Developers điều chỉnh Sprint Backlog và thương lượng phạm vi với Product Owner khi cần, không làm nguy hiểm Sprint Goal và không hạ chất lượng.
- **Increment chỉ được coi hoàn thành khi đáp ứng Definition of Done.** Một demo hoặc phần trăm task không thay thế bằng chứng chất lượng.
- **Daily Scrum kiểm tra tiến trình; Sprint Review kiểm tra kết quả và hướng sản phẩm; Sprint Retrospective cải tiến cách làm.** Các sự kiện này giúp mục tiêu thật sự trở thành định hướng công việc hằng ngày.

Khi đội phân vân trước hai việc trong Sprint, hãy đặt câu hỏi: **“Việc nào đưa chúng ta gần Sprint Goal hơn, và phương án đó có giữ được chất lượng cũng như giá trị cho người dùng không?”**
