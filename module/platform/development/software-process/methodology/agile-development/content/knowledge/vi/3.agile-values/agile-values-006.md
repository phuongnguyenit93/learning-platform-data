# Vận dụng bốn giá trị vào quyết định công việc hằng ngày

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích đúng ý nghĩa của bốn giá trị trong **Tuyên ngôn Agile** và tránh hiểu nhầm rằng một vế hoàn toàn không còn giá trị.
2. Dùng bốn giá trị làm căn cứ cho các quyết định thường gặp khi viết user story, sắp xếp backlog, phát triển, kiểm thử, review và cải tiến.
3. Xử lý tình huống các giá trị có vẻ xung đột với thời hạn, hợp đồng, an toàn, tài liệu hoặc sự tập trung của đội.
4. Đề xuất một quyết định có lý do, người chịu trách nhiệm, cách kiểm chứng và giới hạn rủi ro rõ ràng.

## 1. Từ khẩu hiệu đến tiêu chí ra quyết định

Tuyên ngôn Agile (2001) đưa ra **bốn giá trị** cho việc phát triển phần mềm:

| Giá trị được ưu tiên hơn | Vế vẫn có giá trị |
| --- | --- |
| **Cá nhân và tương tác** (*Individuals and interactions*) | Quy trình và công cụ (*Processes and tools*) |
| **Phần mềm hoạt động được** (*Working software*) | Tài liệu đầy đủ (*Comprehensive documentation*) |
| **Cộng tác với khách hàng** (*Customer collaboration*) | Thương lượng hợp đồng (*Contract negotiation*) |
| **Đáp ứng với thay đổi** (*Responding to change*) | Tuân thủ kế hoạch (*Following a plan*) |

Từ **“hơn”** là trọng tâm. Tuyên ngôn nói rõ các yếu tố bên phải vẫn có giá trị, nhưng các yếu tố bên trái được coi trọng hơn khi cần cân nhắc. Vì vậy:

- Ưu tiên **tương tác** không có nghĩa bỏ quy trình, không dùng hệ thống quản lý công việc hoặc chỉ trao đổi bằng lời nói.
- Ưu tiên **phần mềm hoạt động được** không có nghĩa bỏ kiểm thử, tài liệu vận hành, hồ sơ pháp lý hay thiết kế.
- Ưu tiên **cộng tác** không có nghĩa khách hàng có thể đơn phương xóa mọi ràng buộc hợp đồng.
- Ưu tiên **thích ứng** không có nghĩa thay mục tiêu theo mọi yêu cầu vừa xuất hiện.

Bốn giá trị không phải bốn bước thực hiện theo thứ tự. Chúng là **bốn góc nhìn bổ sung** để hỏi: “Quyết định hôm nay có giúp đội giao giá trị thực, học nhanh và duy trì chất lượng không?”

### Một ví dụ xuyên suốt

Một nhóm xây dựng nền tảng học trực tuyến nhận phản hồi: học viên thường mất dấu bài đang học và bỏ dở khóa học. Nhóm có ba lựa chọn:

1. Thiết kế lại toàn bộ trang học tập trong hai tháng, vì đó là kế hoạch ban đầu.
2. Tạo một tính năng nhỏ **“Tiếp tục học”**, dùng được từ trang chủ, kiểm chứng với người học và cải thiện dần.
3. Họp nhiều lần để hoàn thiện tài liệu phân tích nhưng chưa làm gì có thể thử.

Nhóm không thể khẳng định phương án 2 tốt nhất chỉ bằng niềm tin vào Agile. Họ cần nói chuyện với người học, xác định vấn đề, kiểm tra khả năng kỹ thuật và đo kết quả. Tuy nhiên, nếu có thể giao an toàn một lát cắt nhỏ, phương án 2 thường tạo cơ hội **kiểm chứng giả thuyết sớm hơn**. Từ đây, bốn giá trị trở thành hướng dẫn cho những quyết định cụ thể.

## 2. Giá trị 1 — Cá nhân và tương tác hơn quy trình và công cụ

### Ý nghĩa trong công việc

Phần mềm được tạo bởi những người có kiến thức, góc nhìn và trách nhiệm khác nhau. Công cụ quản lý backlog, quy trình review hay biểu mẫu có ích khi giúp họ phối hợp; chúng mất tác dụng nếu tạo ra nhiều thao tác hơn giá trị trao đổi.

Hãy ưu tiên cuộc trao đổi trực tiếp hoặc đồng bộ khi cần giải quyết **hiểu nhầm, quyết định phức tạp, phụ thuộc khó gỡ hoặc rủi ro khẩn**. Sau đó ghi lại kết luận cần truy vết. Không phải mọi việc đều cần họp: thông tin rõ ràng, ít tranh cãi có thể trao đổi bất đồng bộ bằng issue, pull request hay tài liệu ngắn.

### Quyết định thường gặp

| Tình huống | Cách vận dụng | Vẫn cần giữ |
| --- | --- | --- |
| Một user story có tiêu chí chấp nhận mơ hồ | Hẹn cuộc trao đổi ngắn giữa người phụ trách sản phẩm, lập trình viên và kiểm thử viên; dùng ví dụ đầu vào/đầu ra cụ thể | Cập nhật tiêu chí chấp nhận trong backlog để mọi người cùng hiểu |
| Pull request bị tranh luận kéo dài bằng bình luận | Chuyển sang trao đổi trực tiếp, chạy thử phương án và thống nhất tiêu chí kỹ thuật | Lưu quyết định và lý do trong PR hoặc tài liệu thiết kế khi cần |
| Một việc bị chặn vì phụ thuộc đội khác | Liên hệ người chịu trách nhiệm, cùng xác định cách tháo gỡ và mốc phản hồi | Cập nhật trạng thái phụ thuộc, người phụ trách, thời hạn |
| Daily Scrum chỉ trở thành vòng đọc trạng thái | Dùng thời gian để điều chỉnh kế hoạch của Developers, phát hiện trở ngại hướng tới Sprint Goal | Minh bạch tiến độ bằng bảng công việc; không bỏ kiểm soát cần thiết |
| Sự cố sản xuất đang diễn ra | Lập kênh phối hợp nhanh, phân vai người chỉ huy, người khắc phục và người truyền thông | Giữ log sự cố, mốc thời gian, bằng chứng và quy trình an toàn |

**Ví dụ đối thoại ngắn:** Tester hỏi: “Khi học viên đang học ở phút thứ 12 mà mất mạng, nút ‘Tiếp tục học’ sẽ mở ở đâu?” Developer nghĩ rằng mở ở đầu bài; người phụ trách sản phẩm tưởng mở đúng phút đã dừng. Chỉ một cuộc trao đổi có ví dụ cụ thể có thể ngăn việc làm sai cả tuần.

### Quy tắc áp dụng

1. Nhận diện **người đang thiếu thông tin hoặc quyền quyết định**, không chỉ “ticket đang ở trạng thái nào”.
2. Chọn hình thức giao tiếp phù hợp với mức phức tạp: bình luận ngắn, trao đổi trực tiếp hoặc workshop.
3. Kết thúc cuộc trao đổi bằng quyết định rõ: làm gì, ai làm, điều kiện chấp nhận, khi nào kiểm tra lại.
4. Lưu thông tin cần thiết cho người không có mặt và cho các lần bảo trì sau.

**Bẫy thường gặp:** “Ưu tiên con người” bị hiểu thành chỉ dựa vào trí nhớ hoặc quan hệ cá nhân. Điều này loại trừ thành viên làm việc lệch múi giờ, người mới vào nhóm và người cần tra cứu về sau. Tương tác tốt đi kèm **ghi chép tối thiểu nhưng đủ dùng**.

## 3. Giá trị 2 — Phần mềm hoạt động được hơn tài liệu đầy đủ

### Ý nghĩa trong công việc

Một bản mô tả có thể trình bày rất đẹp nhưng chưa chứng minh sản phẩm đáp ứng nhu cầu. Ngược lại, một phần mềm chạy được, đáp ứng các tiêu chí chấp nhận và có thể dùng để kiểm tra giả thuyết sẽ tạo bằng chứng mạnh hơn về tiến độ thực chất.

“Hoạt động được” không chỉ là giao diện mở lên hoặc bản demo thao tác được trên máy lập trình viên. Tùy tính chất sản phẩm, nó còn bao gồm hành vi đúng, dữ liệu nhất quán, kiểm thử, bảo mật, khả năng vận hành và tích hợp. Trong **Scrum**, increment phải đáp ứng **Definition of Done** để được xem là hoàn thành; một increment có thể sẵn sàng sử dụng nhưng thời điểm phát hành ra người dùng vẫn là quyết định riêng.

### Biến ý tưởng thành một lát cắt có thể kiểm chứng

Thay vì tách công việc thành ba ticket lớn “làm UI”, “làm API”, “làm database” và nhiều tuần sau mới tích hợp, hãy cân nhắc một **lát cắt từ đầu đến cuối** đủ nhỏ để tạo ra hành vi có ích.

Ví dụ user story:

> **Là** học viên đã đăng nhập, **tôi muốn** mở lại bài học gần nhất từ trang chủ **để** tiếp tục học mà không cần tìm lại vị trí trước đó.

Tiêu chí chấp nhận khả thi cho lát cắt đầu:

- Khi có bài đang học, học viên nhìn thấy khóa học, tên bài và nút “Tiếp tục học”.
- Khi nhấn nút, hệ thống mở đúng bài học gần nhất đã lưu và vị trí phát phù hợp với thiết kế được thống nhất.
- Khi chưa có tiến độ học, hệ thống không hiển thị nút gây hiểu nhầm.
- Học viên không thể truy cập tiến độ của tài khoản khác.
- Các trường hợp quan trọng được kiểm thử; dữ liệu không bị hỏng nếu gửi lại yêu cầu.

Tiêu chí trên tạo điều kiện cho lập trình viên và người kiểm thử xác định khi nào sản phẩm **thực sự đáp ứng** mục tiêu. Bản tiếp theo có thể xử lý nhiều thiết bị, mạng kém hoặc gợi ý bài học, nếu bằng chứng cho thấy những phần đó cần thiết.

### Khi nào cần tài liệu?

Tài liệu có giá trị nếu hỗ trợ quyết định, sử dụng, tuân thủ hoặc bảo trì. Chọn **đúng loại tài liệu**:

| Mục đích | Tài liệu hoặc bằng chứng phù hợp |
| --- | --- |
| Thống nhất yêu cầu | User story, tiêu chí chấp nhận, ví dụ hành vi, phác thảo giao diện khi cần |
| Giải thích quyết định kỹ thuật khó đảo ngược | Quyết định kiến trúc ngắn (ADR), sơ đồ luồng dữ liệu, các đánh đổi |
| Bàn giao và vận hành | Hướng dẫn triển khai, giám sát, rollback, runbook xử lý sự cố |
| An toàn, pháp lý và bảo mật | Hồ sơ kiểm thử, truy vết yêu cầu, phê duyệt, chính sách và bằng chứng bắt buộc |
| Dùng API giữa các nhóm | API contract, ví dụ request/response, phiên bản, trường hợp lỗi |

**Câu hỏi ra quyết định:** “Tài liệu này giúp ai đưa ra quyết định, vận hành hoặc kiểm chứng điều gì?” Nếu không có câu trả lời cụ thể, nên xem lại mức chi tiết. Nếu tài liệu là yêu cầu pháp lý hoặc giảm rủi ro cao, phải thực hiện đầy đủ dù không trực tiếp tạo giao diện mới.

### Dấu hiệu làm sai giá trị

- Báo “hoàn thành 90%” vì viết xong tài liệu và gần xong code, nhưng chưa có đường đi người dùng nào chạy được.
- Demo chỉ có dữ liệu giả, bỏ qua trường hợp lỗi, trong khi báo như sản phẩm đã hoàn tất.
- Từ chối bổ sung kiểm thử hoặc cập nhật runbook với lý do “Agile không cần giấy tờ”.

Đo tiến độ thực chất bằng **phần chức năng đáp ứng Definition of Done và giá trị có thể kiểm chứng**, kết hợp số lỗi và phản hồi người dùng; không chỉ bằng số trang tài liệu hay số dòng mã.

## 4. Giá trị 3 — Cộng tác với khách hàng hơn thương lượng hợp đồng

### Ý nghĩa trong công việc

Khi xây dựng phần mềm, cả đội và người sử dụng đều có thể chưa biết chính xác giải pháp tốt nhất ngay từ đầu. Nếu mọi tương tác chỉ nhằm đối chiếu điều khoản, sản phẩm có thể “đúng đặc tả ban đầu” nhưng giải quyết sai vấn đề hiện tại. Cộng tác thường xuyên giúp làm rõ nhu cầu và cùng lựa chọn đánh đổi.

**Khách hàng** trong thực tế có thể là người đặt hàng, đại diện nghiệp vụ, người dùng cuối, bộ phận vận hành hoặc các nhóm chịu tác động khác nhau. Ý kiến của họ không phải lúc nào cũng giống nhau. Đội cần xác định **ai có quyền ưu tiên backlog, ai đại diện trải nghiệm người dùng, ai phê duyệt rủi ro**. Trong Scrum, **Product Owner** chịu trách nhiệm quản lý Product Backlog và tối đa hóa giá trị sản phẩm; điều này không thay thế việc lắng nghe người dùng thực tế.

### Vận dụng từ yêu cầu đến phản hồi

1. **Hỏi về kết quả cần đạt:** “Học viên bỏ dở vì khó tìm bài đang học hay vì nội dung quá dài?” thay vì lập tức nhận yêu cầu “thêm một widget mới”.
2. **Cùng làm rõ giả thuyết:** “Nếu có nút tiếp tục học, học viên quay lại bài cũ nhanh hơn.”
3. **Chọn lát cắt thử nghiệm:** Đưa ra phạm vi nhỏ, nêu chi phí và rủi ro dự kiến.
4. **Cùng xem sản phẩm chạy được:** Review luồng thực tế, không chỉ đọc báo cáo %.
5. **Quyết định dựa trên bằng chứng:** Giữ, sửa, bỏ hoặc ưu tiên thay đổi tiếp theo.

Một câu hỏi tốt tại buổi review là: **“Bằng chứng này đã thay đổi quyết định ưu tiên nào?”** Nếu người dùng phản hồi nhưng backlog không được điều chỉnh và cũng không có lời giải thích, đội chưa thực sự dùng vòng phản hồi để học.

### Khi khách hàng yêu cầu quá nhiều

Ví dụ: Khách hàng muốn thêm chứng chỉ, diễn đàn, gamification và tính năng AI vào cùng một đợt phát hành. Một nhóm Agile không cần nhận tất cả để thể hiện sự cộng tác. Họ có thể:

- Cùng xác định mục tiêu quan trọng nhất, chẳng hạn tăng tỷ lệ hoàn thành khóa học.
- Thống nhất tiêu chí xếp ưu tiên: mức tác động dự kiến, độ tin cậy của bằng chứng, chi phí, rủi ro, phụ thuộc.
- Đề xuất cách kiểm chứng ít tốn kém hơn trước khi đầu tư đầy đủ.
- Ghi lại lựa chọn, nội dung chưa làm, thời điểm đánh giá lại và tác động lên thời hạn.

**Hợp đồng vẫn quan trọng:** Với dự án thuê ngoài, chi phí, phạm vi, bảo mật, quyền sở hữu, nghiệm thu và quy trình thay đổi là cam kết thực. Nhóm có thể thỏa thuận cách xử lý yêu cầu mới, mốc review và nguyên tắc đổi phạm vi trong khuôn khổ hợp đồng. Không tự ý làm khác cam kết hoặc bỏ yêu cầu phê duyệt.

### Phản hồi chất lượng cao và phản hồi yếu

| Phản hồi | Độ hữu ích | Bước tiếp theo |
| --- | --- | --- |
| “Tôi không thích giao diện này.” | Chưa đủ rõ | Hỏi thao tác cụ thể nào khó, quan sát người dùng thực hiện |
| “Trong 5 lần thử, 3 học viên không tìm thấy nút tiếp tục học.” | Có tín hiệu hành vi, nhưng mẫu nhỏ | Tìm nguyên nhân, cải thiện khả năng nhận biết, thử lại trên nhóm phù hợp |
| “Phải thêm AI vì đối thủ có AI.” | Nêu giải pháp, chưa nêu kết quả | Hỏi người học cần giải quyết việc gì và cách kiểm chứng giá trị |
| “Tỷ lệ quay lại tăng sau khi phát hành.” | Tín hiệu đáng theo dõi nhưng chưa chắc do thay đổi gây ra | So sánh bối cảnh, chất lượng dữ liệu và yếu tố khác trước khi kết luận |

Không dùng phản hồi của một người để đại diện cho tất cả người dùng. Khi cần, kết hợp phỏng vấn, quan sát, dữ liệu hành vi, hỗ trợ khách hàng và thử nghiệm có thiết kế phù hợp.

## 5. Giá trị 4 — Đáp ứng với thay đổi hơn tuân thủ kế hoạch

### Ý nghĩa trong công việc

Kế hoạch là giả thuyết tốt nhất dựa trên thông tin hiện có. Khi xuất hiện dữ liệu mới đáng tin cậy, việc điều chỉnh là hành động có trách nhiệm. Tuy nhiên, thay đổi cũng có **chi phí chuyển ngữ cảnh, sửa code, kiểm thử lại, thay đổi tài liệu, phụ thuộc và cam kết**. Giá trị Agile hướng đến khả năng thay đổi có chủ đích, không phải trạng thái luôn đổi ý.

### Phân biệt thay đổi có căn cứ và nhiễu ưu tiên

Trước khi nhận một yêu cầu mới, hãy trả lời:

1. **Điều gì vừa thay đổi?** Luật mới, lỗi nghiêm trọng, dữ liệu người dùng, mục tiêu kinh doanh hay chỉ sở thích?
2. **Mức khẩn và chi phí chậm trễ ra sao?** Có nguy cơ an toàn, mất dữ liệu, vi phạm cam kết hoặc bỏ lỡ thời điểm quan trọng không?
3. **Tác động tới mục tiêu hiện tại là gì?** Có thể điều chỉnh cách làm mà vẫn đạt mục tiêu hay cần thương lượng lại mục tiêu?
4. **Cần đổi thứ tự backlog, phạm vi, ngày giao hoặc nguồn lực nào?** Ai có quyền quyết định?
5. **Cần kiểm chứng lại điều gì?** Test, bảo mật, migration, tài liệu, thông báo cho người dùng?

Với **Scrum**, Sprint Goal giúp đội tập trung: các chi tiết công việc có thể được làm rõ, thương lượng khi học được điều mới miễn là không làm nguy hiểm mục tiêu Sprint; những thay đổi làm Sprint Goal không còn giá trị cần được xử lý theo cơ chế Scrum và quyền quyết định thích hợp. Với **Kanban**, nhóm có thể điều chỉnh thứ tự công việc theo chính sách ưu tiên, giới hạn **WIP** (work in progress, lượng công việc đang làm) và quy tắc xử lý công việc khẩn cấp.

### Ví dụ: một yêu cầu thay đổi giữa Sprint

Đội đang thực hiện mục tiêu “Học viên tiếp tục được bài đang học”. Giữa Sprint, bộ phận kinh doanh đề nghị thêm bộ huy hiệu thành tích.

- Nếu yêu cầu không có hạn bắt buộc và không liên quan trực tiếp tới Sprint Goal, Product Owner có thể xếp nó vào Product Backlog để đánh giá, thay vì ngắt toàn bộ nhóm.
- Nếu phản hồi cho thấy vị trí lưu bài học đang sai và làm người dùng mất tiến độ, đội cần ưu tiên sửa lỗi vì nó đe dọa giá trị của mục tiêu hiện tại.
- Nếu phát sinh một yêu cầu bảo mật nghiêm trọng, việc xử lý cần theo mức rủi ro và quyền phê duyệt tương ứng, kể cả phải thay đổi kế hoạch đã thống nhất.

Để thích ứng với chi phí thấp, đội có thể giao các increment nhỏ, làm rõ tiêu chí chấp nhận, tự động hóa kiểm thử, tích hợp thường xuyên, sử dụng feature flag khi phù hợp và giữ kiến trúc dễ thay đổi. Các thực hành của **Extreme Programming (XP)** như kiểm thử tự động, tích hợp liên tục, refactor và lập trình cặp có thể hỗ trợ điều này.

### Khi nên giữ kế hoạch

Giữ kế hoạch là hợp lý khi thông tin mới không đủ thuyết phục, thay đổi tạo rủi ro quá lớn hoặc có cam kết bắt buộc. Ví dụ: đợt phát hành cần chứng nhận pháp lý vào ngày xác định không nên thêm tính năng mới sát thời điểm kiểm định chỉ vì có ý tưởng thú vị. Đội có thể đưa ý tưởng vào backlog đợt sau, đồng thời giữ khả năng học hỏi qua bản thử nghiệm không ảnh hưởng bản phát hành chính.

**Bài học:** Khả năng thích ứng là khả năng **chọn đúng thay đổi và thực hiện an toàn**.

## 6. Áp dụng đồng thời bốn giá trị

Trong công việc thực, một quyết định thường liên quan đến nhiều giá trị. Dùng bảng sau để chuyển giá trị thành hành động:

| Quyết định hằng ngày | Cá nhân và tương tác | Phần mềm hoạt động được | Cộng tác với khách hàng | Đáp ứng thay đổi |
| --- | --- | --- | --- | --- |
| **Làm rõ user story** | Developer, tester và đại diện sản phẩm cùng nêu ví dụ | Viết tiêu chí có thể kiểm chứng bằng hành vi chạy được | Xác nhận kết quả người dùng cần | Cho phép làm rõ phạm vi khi học được điều mới |
| **Sắp xếp backlog** | Người có dữ liệu, kỹ thuật và trách nhiệm sản phẩm cùng trao đổi | Ưu tiên lát cắt mang lại increment dùng được | Tập trung vào kết quả người dùng | Điều chỉnh thứ tự khi xuất hiện bằng chứng đáng tin |
| **Review pull request** | Thảo luận các khác biệt quan trọng bằng ví dụ, tránh tranh luận vô tận | Chú trọng hành vi, test, khả năng vận hành | Kiểm tra mã có đáp ứng tiêu chí chấp nhận | Thiết kế đủ dễ sửa khi yêu cầu hợp lý thay đổi |
| **Demo/review** | Trao đổi hai chiều, không chỉ trình bày một chiều | Chạy tính năng thật trong môi trường thích hợp | Thu phản hồi từ đúng người | Chuyển thông tin mới thành quyết định backlog |
| **Xử lý sự cố** | Kết nối đúng người, phân vai và thông tin minh bạch | Ưu tiên khôi phục chức năng an toàn | Cập nhật tác động và nhu cầu người bị ảnh hưởng | Đổi ưu tiên theo mức độ nghiêm trọng và bằng chứng |
| **Retrospective** | Tìm nguyên nhân trong hệ thống phối hợp, tránh đổ lỗi | Kiểm tra việc cải tiến có giúp giao chất lượng hơn | Xem các cải tiến có tăng khả năng phục vụ người dùng | Chọn một thay đổi nhỏ, đo và điều chỉnh |

### Một vòng quyết định ngắn

Khi hai lựa chọn đều có lý, đội có thể sử dụng quy trình:

~~~mermaid
flowchart TD
    A["Vấn đề hoặc thông tin mới"] --> B["Xác định giá trị người dùng và ràng buộc"]
    B --> C["Trao đổi với người có chuyên môn và quyền quyết định"]
    C --> D{"Có thể kiểm chứng bằng phần mềm hoặc thử nghiệm nhỏ?"}
    D -- Có --> E["Tạo lát cắt/giả thuyết và tiêu chí chấp nhận"]
    D -- Chưa --> F["Làm rõ rủi ro, phương án mô phỏng hoặc bằng chứng cần có"]
    F --> E
    E --> G["Giao/kiểm tra an toàn, lấy phản hồi"]
    G --> H{"Bằng chứng có làm thay đổi ưu tiên?"}
    H -- Có --> I["Cập nhật backlog, phạm vi và cam kết liên quan"]
    H -- Không --> J["Tiếp tục mục tiêu đã thống nhất"]
    I --> K["Ghi quyết định và điểm kiểm tra tiếp"]
    J --> K
~~~

Đây là sơ đồ hỗ trợ tư duy, không phải quy trình phê duyệt bắt buộc cho mọi ticket. Sự cố nghiêm trọng có thể cần hành động ngay theo quy trình ứng cứu, còn thay đổi pháp lý có thể cần xác nhận của bộ phận chuyên trách trước khi triển khai.

## 7. Tình huống thực hành: chọn giữa bốn phương án

### Bối cảnh

Nhóm phát triển chức năng “Tiếp tục học” cho nền tảng đào tạo. Còn ba ngày trước buổi review, nhóm gặp bốn thông tin:

- **A:** Lập trình viên đã hoàn thành giao diện nhưng phát hiện API lưu tiến độ đôi khi trả về vị trí sai.
- **B:** Người phụ trách sản phẩm muốn bổ sung hoạt ảnh mới để buổi demo trông đẹp hơn.
- **C:** Tester chưa rõ khi một học viên học trên hai thiết bị, vị trí nào được chọn.
- **D:** Một người dùng thử cho biết họ thường dùng điện thoại và không nhận ra nút tiếp tục học.

### Phân tích theo giá trị

| Thông tin | Quyết định đề xuất | Căn cứ |
| --- | --- | --- |
| A — Lỗi dữ liệu tiến độ | Ưu tiên điều tra và sửa lỗi, bổ sung kiểm thử hồi quy trước khi tuyên bố hoàn tất | Phần mềm hoạt động đúng quan trọng hơn buổi demo trông hoàn chỉnh |
| B — Hoạt ảnh | Hỏi hoạt ảnh giúp giải quyết vấn đề nào; nếu chưa có bằng chứng, cân nhắc đưa vào backlog sau | Cộng tác để hiểu giá trị, đồng thời giữ Sprint Goal và chất lượng |
| C — Quy tắc hai thiết bị | Tổ chức trao đổi ngắn giữa sản phẩm, dev và tester; ghi quy tắc cụ thể vào tiêu chí chấp nhận | Tương tác giúp giảm hiểu nhầm; tài liệu ngắn lưu kết luận |
| D — Vị trí nút trên điện thoại | Tái hiện tình huống, hỏi thêm người dùng hoặc chạy kiểm tra khả dụng nhỏ; cân nhắc sửa nếu tác động mục tiêu chính | Phản hồi mới có thể đáng để điều chỉnh kế hoạch |

### Quyết định tổng thể hợp lý

Nhóm có thể giữ Sprint Goal là giúp học viên tiếp tục việc học **một cách tin cậy**, ưu tiên A và C trước. D cần xác minh nhanh vì ảnh hưởng khả năng tìm chức năng; nếu bằng chứng đủ mạnh và chi phí thay đổi chấp nhận được, nhóm có thể điều chỉnh vị trí nút ngay trong phạm vi mục tiêu. B được ghi nhận, giải thích vì sao chưa ưu tiên và hẹn xem xét lại.

Trước buổi review, nhóm phải nói rõ phần nào đáp ứng Definition of Done, phần nào chưa. Nếu API vẫn sai, không nên gắn nhãn “Done” hay trình bày giao diện như một chức năng đã sẵn sàng, kể cả khi có thể chạy demo trên một bộ dữ liệu thuận lợi.

**Điều cần rút ra:** Bốn giá trị không tự trả lời “chọn A hay D” bằng công thức. Chúng giúp đội ưu tiên đối thoại, sản phẩm đúng, phản hồi khách hàng và thích ứng có kiểm soát khi đưa ra lựa chọn dựa trên mức độ tác động và rủi ro.

## 8. Những xung đột thường gặp và cách xử lý

### 8.1. Khách hàng muốn thay đổi, còn nhóm đã cam kết tiến độ

Không tự động đồng ý hoặc từ chối. Làm rõ giá trị và mức khẩn, sau đó trình bày lựa chọn: đổi phạm vi, đổi ngày giao, giảm tính năng ít quan trọng hơn, hoặc chuyển yêu cầu sang đợt sau. Quyết định cuối cần người có thẩm quyền, cập nhật backlog và thông báo cho các bên chịu tác động.

**Ví dụ cách trao đổi:**

> “Phản hồi này cho thấy học viên dùng điện thoại khó tìm nút. Chúng tôi đề xuất thử cách hiển thị mới trước buổi review. Để giữ chất lượng và ngày giao, phần hoạt ảnh sẽ chuyển sang backlog sau. Anh/chị có đồng ý ưu tiên theo cách đó không?”

### 8.2. Quy trình yêu cầu một bước phê duyệt làm chậm phát hành

Trước hết xác định lý do phê duyệt: pháp lý, bảo mật, an toàn, tài chính hay thói quen tồn tại lâu. Với bước thực sự bắt buộc, hãy tự động hóa bằng chứng, chuẩn bị hồ sơ sớm hoặc tách việc giao increment nội bộ khỏi phát hành bên ngoài. Với bước không còn giá trị, trao đổi với người phụ trách để điều chỉnh quy trình theo thẩm quyền.

Giá trị “cá nhân và tương tác” không cho phép bỏ qua kiểm soát để nhanh hơn.

### 8.3. Developer muốn refactor, Product Owner muốn thêm tính năng

Đừng đối lập “giá trị kỹ thuật” với “giá trị kinh doanh” theo trực giác. Làm rõ rủi ro: thay đổi hiện tại có gây lỗi, chậm tích hợp, dễ mất dữ liệu hay khiến yêu cầu tương lai rất tốn kém không? Nếu có, cần thể hiện ảnh hưởng lên khả năng giao giá trị và thống nhất thứ tự xử lý. Refactor nhỏ, có kiểm thử, trong phạm vi xây dựng chức năng có thể là lựa chọn tốt; tái cấu trúc lớn cần mục tiêu và căn cứ rõ.

Các thực hành XP như TDD, CI và refactor thường xuyên giúp giảm chi phí thay đổi, hỗ trợ giá trị “đáp ứng thay đổi” về dài hạn.

### 8.4. Nhiều cuộc họp hơn nhưng ít việc hoàn tất hơn

Đếm số cuộc họp không phản ánh chất lượng tương tác. Xem mục đích từng cuộc họp, quyết định tạo ra và thời gian chờ giữa các bước. Có thể chuyển các cập nhật trạng thái đơn giản sang bảng Kanban, giới hạn WIP, xử lý trở ngại trực tiếp và dành buổi review để quan sát sản phẩm thật.

### 8.5. Phản hồi liên tục làm đội mất tập trung

Đặt một chính sách minh bạch: nguồn tiếp nhận yêu cầu, người quyết định ưu tiên, tiêu chí khẩn cấp, thời điểm xem lại backlog và cách xử lý thay đổi ảnh hưởng Sprint Goal. Lắng nghe liên tục **không đòi hỏi chuyển ngay mọi ý kiến thành công việc đang làm**.

## 9. Từ giá trị đến hành vi trong Scrum, Kanban và XP

Các khung và thực hành là công cụ biến giá trị thành cách làm cụ thể, nhưng chúng không thay thế việc xét đoán.

| Cách làm | Hành vi áp dụng bốn giá trị | Điều cần cảnh giác |
| --- | --- | --- |
| **Scrum — Product Backlog và Sprint Planning** | Cùng làm rõ mục tiêu, chọn công việc phục vụ giá trị, dự báo dựa trên năng lực và thông tin thực | Coi Sprint Backlog là hợp đồng bất biến hoặc ép cả đội nhận quá tải |
| **Scrum — Daily Scrum** | Developers kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch phối hợp | Đọc trạng thái cho quản lý mà không giải quyết trở ngại |
| **Scrum — Sprint Review** | Xem increment, cùng các bên liên quan xem điều gì đã học và hướng đi tiếp | Chỉ trình chiếu slide và không có phản hồi dẫn đến quyết định |
| **Scrum — Retrospective** | Nhìn lại tương tác, chất lượng và quy trình; chọn cải tiến có thể kiểm chứng | Tạo danh sách cải tiến dài nhưng không theo dõi kết quả |
| **Kanban — trực quan hóa và giới hạn WIP** | Làm rõ dòng công việc, điểm nghẽn và chính sách ưu tiên | Tối ưu số ticket mà bỏ qua giá trị hoặc chất lượng |
| **XP — TDD, CI, pair programming, refactor** | Giữ code dễ thay đổi, phát hiện lỗi sớm, chia sẻ kiến thức | Áp dụng nghi thức kỹ thuật cứng nhắc mà không quan sát hiệu quả |

Một đội có thể sử dụng Scrum để quản lý mục tiêu phát triển tính năng, dùng bảng Kanban để thấy dòng việc và thực hành XP để bảo đảm chất lượng. Chỉ nên phối hợp những phần phục vụ vấn đề cụ thể; không cần tích lũy mọi nghi thức.

### Đo dấu hiệu vận dụng giá trị

Vì giá trị Agile là định hướng, không có một “điểm Agile” duy nhất. Có thể quan sát một số tín hiệu:

- **Tương tác:** Thời gian gỡ trở ngại, số lần yêu cầu phải làm lại vì hiểu sai, chất lượng quyết định được ghi lại.
- **Sản phẩm hoạt động:** Tỷ lệ hạng mục hoàn tất theo Definition of Done, lỗi lọt sản xuất, mức sẵn sàng triển khai và khả năng khôi phục.
- **Cộng tác:** Tần suất phản hồi có ý nghĩa, giả thuyết đã được kiểm chứng và quyết định backlog dựa trên phản hồi.
- **Thích ứng:** Thời gian từ thông tin mới đến quyết định, chi phí và rủi ro khi thay đổi, lead time/cycle time theo định nghĩa nhất quán.

Không nên dùng velocity/story point để so sánh năng suất giữa các đội hay xem số lần “đổi yêu cầu” càng nhiều càng tốt. Chỉ số cần phục vụ câu hỏi cải tiến, không trở thành mục tiêu bị tối ưu theo hình thức.

## 10. Công cụ nhanh để ra quyết định mỗi ngày

Khi cần quyết định trong vài phút, dùng sáu câu hỏi sau:

| Câu hỏi | Mục đích |
| --- | --- |
| **Ai bị ảnh hưởng? Ai cần tham gia quyết định?** | Đưa đúng người vào tương tác và xác định quyền chịu trách nhiệm |
| **Kết quả sử dụng cụ thể nào phải tốt hơn?** | Gắn quyết định với giá trị khách hàng |
| **Phần mềm hoặc phép thử nhỏ nào xác nhận được điều đó?** | Tập trung vào bằng chứng thực chất |
| **Điều gì mới xuất hiện khiến ta nên đổi quyết định cũ?** | Tách phản hồi hữu ích khỏi nhiễu ưu tiên |
| **Ràng buộc nào không được vi phạm?** | Giữ chất lượng, bảo mật, an toàn, tài liệu, hợp đồng và cam kết |
| **Ai làm gì, khi nào kiểm tra lại và dựa trên chỉ số nào?** | Biến thảo luận thành hành động có thể theo dõi |

Ví dụ ghi nhận một quyết định ngắn:

~~~text
Bối cảnh: Học viên trên điện thoại khó nhìn thấy nút "Tiếp tục học".
Mục tiêu: Tăng số học viên tìm được và mở lại bài đang học.
Bằng chứng: 3/5 người thử không tìm được nút trong lần thử đầu.
Các lựa chọn: (A) Dời nút lên vùng dễ thấy; (B) Giữ nguyên; (C) Thiết kế lại toàn bộ trang.
Quyết định: Thử A trên bản nhỏ trước, không mở rộng sang C.
Giới hạn: Không làm hỏng quyền truy cập và tiến độ học; kiểm thử trên thiết bị phù hợp.
Người phụ trách: Product Owner quyết định ưu tiên; đội phát triển hoàn thiện và kiểm thử.
Kiểm tra lại: Quan sát thêm lượt thử, xem tỷ lệ tìm thấy và mở lại bài.
~~~

Mẫu này không phải biểu mẫu bắt buộc; với việc đơn giản có thể chỉ cần một bình luận rõ ràng trong ticket, còn với thay đổi ảnh hưởng bảo mật hay kiến trúc phải có bằng chứng và phê duyệt đầy đủ.

## 11. Bài tập tình huống và gợi ý đáp án

**Tình huống 1 — “Đã đủ ba buổi họp rồi”.** Tester phát hiện yêu cầu không rõ và đề nghị trao đổi với người phụ trách sản phẩm. Quản lý từ chối vì quy trình chỉ cho phép làm rõ yêu cầu vào thứ Hai.

- Bạn sẽ ưu tiên giá trị nào? Có nên bỏ lịch họp cố định?
- **Gợi ý:** Ưu tiên tương tác để giải quyết mơ hồ ngay khi có thể, nhưng vẫn ghi lại tiêu chí chấp nhận. Đánh giá xem lịch họp có lý do quản trị bắt buộc không; có thể bổ sung kênh làm rõ ngắn thay vì xóa toàn bộ quy trình.

**Tình huống 2 — “Demo phải thật ấn tượng”.** Đội có thể thêm hiệu ứng giao diện hoặc hoàn thiện kiểm thử chức năng lưu tiến độ trước review.

- Khi nào có thể ưu tiên hiệu ứng? Khi nào cần ưu tiên kiểm thử?
- **Gợi ý:** Nếu lưu tiến độ chưa đáng tin, phải xử lý hành vi và chất lượng cốt lõi trước. Hiệu ứng đáng ưu tiên khi nó giải quyết vấn đề người dùng đã được chứng minh và không đánh đổi an toàn/Definition of Done.

**Tình huống 3 — “Khách hàng đổi yêu cầu vào phút cuối”.** Một khách hàng yêu cầu hỗ trợ xuất dữ liệu mới trước thời điểm bàn giao đã ký hợp đồng.

- Nên nói “có” hay “không” ngay?
- **Gợi ý:** Làm rõ nhu cầu, ràng buộc pháp lý, khả năng kỹ thuật và tác động lịch giao. Đề xuất lựa chọn: thay đổi phạm vi, lịch, chi phí hoặc chuyển phiên bản sau; xin quyết định theo quyền thỏa thuận trong hợp đồng.

**Tình huống 4 — “Có phản hồi mới nhưng đội đang chạy Sprint”.** Người dùng báo một lỗi dữ liệu có thể làm lộ tiến độ học của người khác, trong khi Sprint Goal tập trung vào cải tiến giao diện.

- Có nên tiếp tục kế hoạch?
- **Gợi ý:** Đánh giá mức nghiêm trọng và kích hoạt quy trình ứng cứu phù hợp. Bảo vệ dữ liệu và người dùng quan trọng hơn việc hoàn thành kế hoạch giao diện. Thay đổi kế hoạch phải minh bạch, có người quyết định và kiểm chứng bản sửa.

### Bài tập áp dụng cho nhóm

Chọn một công việc thật (user story mới, pull request bị chặn, sự cố, hoặc yêu cầu thay đổi). Viết tối đa một trang gồm:

1. Vấn đề và kết quả mà người dùng hoặc tổ chức cần.
2. Hai phương án khả thi cùng chi phí, rủi ro chính.
3. Mỗi giá trị Agile giúp đặt câu hỏi hoặc đánh đổi nào.
4. Quyết định của nhóm, người có quyền quyết định và cam kết bị ảnh hưởng.
5. Một phần mềm/kiểm thử/phản hồi dùng để xác nhận kết quả.
6. Thời điểm xem lại quyết định và tín hiệu cho thấy nên đổi hướng.

Nhóm khác có thể phản biện: “Nếu có dữ liệu mới trái với giả định, nhóm sẽ đổi điều gì?” và “Có nghĩa vụ quan trọng nào bị bỏ sót khi ưu tiên tốc độ không?”.

## 12. Ghi nhớ

- **Cá nhân và tương tác:** Chọn cách phối hợp giúp đúng người hiểu nhau, giải quyết vấn đề và có quyết định rõ; quy trình và công cụ nên hỗ trợ điều đó.
- **Phần mềm hoạt động được:** Dùng increment đáp ứng chất lượng để chứng minh tiến độ và học từ sản phẩm; giữ tài liệu nào thực sự giúp sử dụng, vận hành, kiểm chứng hoặc tuân thủ.
- **Cộng tác với khách hàng:** Cùng làm rõ vấn đề, giả thuyết và đánh đổi dựa trên phản hồi; tôn trọng quyền quyết định và ràng buộc hợp đồng.
- **Đáp ứng thay đổi:** Sẵn sàng điều chỉnh khi có bằng chứng mới đáng tin và thực hiện an toàn; vẫn dùng kế hoạch để tập trung và phối hợp.

Trong thực hành Agile, bốn giá trị không dùng để biện hộ cho việc bỏ kiểm soát. Chúng giúp đội liên tục đặt đúng câu hỏi: **“Lựa chọn này có giúp chúng ta giao phần mềm có ích, nhận phản hồi sớm, phối hợp tốt và cải tiến một cách bền vững hay không?”**
