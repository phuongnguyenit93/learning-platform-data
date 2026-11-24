# Đưa yêu cầu chất lượng, bảo mật và vận hành vào kế hoạch

Một sản phẩm có thể đáp ứng đầy đủ các tính năng trên giấy nhưng vẫn không sẵn sàng để người dùng sử dụng. Chức năng đăng ký workshop có thể hiển thị nút **Đăng ký** và lưu một bản ghi đúng quy trình, nhưng nếu hai người cùng lấy chỗ cuối, hệ thống có thể xác nhận vượt số chỗ. Một trang tiến độ học có thể đẹp và dễ hiểu, nhưng nếu học viên xem được dữ liệu của người khác bằng cách đổi mã định danh trên URL, sản phẩm có lỗi bảo mật nghiêm trọng. Một lần phát hành có thể chạy tốt trong môi trường kiểm thử, nhưng nếu không có cách phát hiện và khôi phục sự cố, vận hành thực tế vẫn chịu rủi ro lớn.

Trong **Agile**, nhu cầu và giải pháp được làm rõ dần qua phản hồi, giao phần mềm hoạt động được theo từng phần và cải tiến liên tục. Điều đó không có nghĩa chất lượng, bảo mật và vận hành được để tới cuối dự án mới xử lý. Ngược lại, những yêu cầu này phải xuất hiện **ngay khi nhóm định nghĩa giá trị, sắp xếp backlog, chia nhỏ user story, xây Increment và quyết định phát hành**.

Bài học thuộc chương **Yêu cầu thích ứng** trong module **AGILE_DEVELOPMENT**. Mục tiêu là biết cách biến những kỳ vọng như “nhanh”, “an toàn”, “dễ bảo trì” hay “sẵn sàng vận hành” thành yêu cầu rõ ràng, có người chịu trách nhiệm và có bằng chứng kiểm chứng; sau đó tích hợp chúng vào Scrum, Kanban, XP và cách đo lường dòng công việc phù hợp.

## 1. Yêu cầu tính năng chưa đủ để tạo ra giá trị

Hãy xét một nền tảng học tập cần chức năng **đăng ký workshop có giới hạn số chỗ**.

Một user story ban đầu:

> **Là** học viên, **tôi muốn** chọn workshop còn chỗ và đăng ký, **để** biết chắc mình có thể tham gia.

Story này mô tả giá trị người dùng, nhưng chưa trả lời các câu hỏi quan trọng:

- Nếu hai học viên gửi yêu cầu gần như đồng thời khi chỉ còn một chỗ, điều gì xảy ra?
- Nếu học viên sửa mã workshop hoặc mã người khác trong yêu cầu, hệ thống có kiểm tra quyền không?
- Nếu dịch vụ gửi email xác nhận bị lỗi, giao dịch đăng ký và trạng thái người dùng có còn đúng không?
- Khi lượng truy cập tăng cao, thời gian chờ và tỷ lệ lỗi nào là chấp nhận được?
- Khi triển khai phiên bản mới phát sinh lỗi, ai nhận cảnh báo, cách dừng và khôi phục ra sao?
- Nếu dữ liệu bị mất hoặc hỏng, có thể phục hồi phần nào, trong bao lâu?

Các câu hỏi trên **không phải phần trang trí thêm**. Chúng quyết định liệu tính năng có thực sự sử dụng được, đáng tin và bền vững khi mở rộng hay không.

### Ba nhóm yêu cầu cần nhìn cùng nhau

| Nhóm yêu cầu | Câu hỏi chính | Ví dụ trong đăng ký workshop |
| --- | --- | --- |
| **Chức năng** (*functional requirements*) | Hệ thống phải làm được việc gì? | Xem workshop, kiểm tra điều kiện, đăng ký, hủy và xem trạng thái |
| **Chất lượng** (*quality attributes*) | Hệ thống phải thực hiện những việc đó tốt đến mức nào, trong điều kiện nào? | Không xác nhận vượt số chỗ; phản hồi đủ nhanh; dễ sử dụng; truy cập được trên thiết bị mục tiêu |
| **Bảo mật và quyền riêng tư** (*security and privacy*) | Ai được làm gì, dữ liệu được bảo vệ ra sao và hệ thống chống các hành vi không hợp lệ thế nào? | Kiểm tra quyền ở máy chủ; không lộ thông tin học viên khác; bảo vệ dữ liệu và dấu vết thao tác |
| **Vận hành** (*operability*) | Làm sao triển khai, quan sát, hỗ trợ, khôi phục và duy trì dịch vụ? | Theo dõi lỗi đăng ký, có cảnh báo, quy trình xử lý sự cố, sao lưu và thử khôi phục |

Ranh giới giữa các nhóm **có thể giao nhau**: bảo mật là một chiều chất lượng; vận hành tác động tới độ tin cậy; tính nhất quán khi đặt chỗ vừa là quy tắc nghiệp vụ vừa là yêu cầu chất lượng. Phân loại giúp không bỏ sót; không nên dùng phân loại để đẩy trách nhiệm từ nhóm này sang nhóm khác.

## 2. Từ tính từ mơ hồ tới tiêu chí kiểm chứng được

Những yêu cầu như “hệ thống phải nhanh, bảo mật cao, dễ dùng và ổn định” rất khó lập kế hoạch, khó kiểm thử và dễ dẫn tới bất đồng khi nghiệm thu. Một yêu cầu có ích cần thể hiện **bối cảnh, hành vi mong đợi, giới hạn hoặc mục tiêu đo được và cách thu bằng chứng**.

### Công thức diễn đạt một yêu cầu chất lượng

> **Trong [điều kiện sử dụng]**, khi **[sự kiện xảy ra]**, hệ thống phải **[hành vi mong đợi]** với **[ngưỡng/tiêu chí rõ ràng]**, được kiểm chứng bằng **[phương pháp]**.

Ví dụ:

| Phát biểu mơ hồ | Phát biểu có thể kiểm chứng | Bằng chứng dự kiến |
| --- | --- | --- |
| “Đăng ký phải nhanh” | Trong kịch bản tải đại diện đã thống nhất, 95% yêu cầu đăng ký hợp lệ có thời gian phản hồi từ phía dịch vụ không vượt mục tiêu được chấp thuận | Kết quả kiểm thử tải theo dữ liệu và cấu hình được ghi rõ |
| “Không được trùng chỗ” | Khi chỉ còn một chỗ và có nhiều yêu cầu đồng thời, tổng số đăng ký được xác nhận không vượt sức chứa | Kiểm thử đồng thời; kiểm tra ràng buộc dữ liệu |
| “Bảo mật tốt” | Người dùng chỉ truy cập và hủy đăng ký thuộc quyền của mình; mọi yêu cầu thay đổi thông tin phải được kiểm tra quyền phía máy chủ | Kiểm thử ủy quyền với người dùng khác vai trò và đối tượng |
| “Dễ khôi phục” | Có quy trình khôi phục được diễn tập theo thời gian và mức mất dữ liệu tối đa do tổ chức chấp thuận | Kết quả diễn tập sao lưu/khôi phục, biên bản vấn đề và cải tiến |
| “Dễ vận hành” | Lỗi đăng ký vượt ngưỡng đã thống nhất được ghi nhận, cảnh báo tới đúng người và có hướng dẫn xử lý | Kiểm tra sự kiện, ngưỡng cảnh báo, kênh nhận và runbook |
| “Dễ dùng” | Người học thuộc nhóm mục tiêu thực hiện được tác vụ đăng ký và hiểu rõ trạng thái thành công/thất bại | Thử tác vụ với người dùng phù hợp, quan sát lỗi thao tác |

**Không tự chọn ngưỡng chỉ để có con số.** Độ trễ, tỷ lệ thành công, thời gian khôi phục hay tỷ lệ hoàn thành tác vụ phải xuất phát từ nhu cầu, rủi ro, chi phí và năng lực thực tế. Khi chưa có dữ liệu nền, hãy ghi yêu cầu dưới dạng **mục tiêu cần hiệu chỉnh** và đưa việc đo cơ sở vào backlog.

### Một ví dụ về ngưỡng minh họa

Giả sử sản phẩm có mục tiêu **95% yêu cầu đăng ký phản hồi trong 800 ms** với 100 người dùng đồng thời, trên môi trường và dữ liệu đại diện. Đây chỉ là **giả định dạy học**, không phải ngưỡng chuẩn cho mọi hệ thống. Trước khi chấp nhận, nhóm cần làm rõ:

1. Đồng hồ đo bắt đầu/kết thúc tại đâu: trên trình duyệt, gateway hay trong dịch vụ?
2. Yêu cầu nào được tính: đăng ký thành công, lỗi nghiệp vụ hợp lệ, hay cả lỗi hạ tầng?
3. Kiểm thử với khối lượng dữ liệu, phần cứng và hành vi người dùng như thế nào?
4. Có cần bảo vệ thêm tỷ lệ lỗi, tính đúng đắn dữ liệu và độ trễ ở phần đuôi phân phối?
5. Khi kết quả chưa đạt, ai quyết định giảm tải, tối ưu, mở rộng hoặc điều chỉnh kỳ vọng?

Ngưỡng có thể điều chỉnh khi nhóm có bằng chứng mới, nhưng **không được hạ ngưỡng sau khi thất bại chỉ để tuyên bố hoàn thành mà bỏ qua tác động với người dùng**.

## 3. Khám phá yêu cầu phi chức năng cùng người có liên quan

Trong cách làm thích ứng, yêu cầu chất lượng, bảo mật và vận hành không phải một phụ lục cố định do một bộ phận viết ở đầu dự án. Chúng được khám phá dần, từ khi hiểu nhu cầu tới khi sử dụng phần mềm thật.

### 3.1. Ai có thông tin cần thiết?

| Người hoặc vai trò | Kiến thức cần khai thác | Câu hỏi ví dụ |
| --- | --- | --- |
| Học viên và người dùng thực | Hành vi, mức độ chấp nhận chờ đợi, khả năng sử dụng và tiếp cận | Khi đăng ký không thành công, thông điệp nào giúp bạn biết phải làm gì? |
| Product Owner hoặc người phụ trách sản phẩm | Giá trị, mức độ ưu tiên, chính sách và đánh đổi | Mất một đăng ký hoặc xác nhận sai chỗ gây thiệt hại gì? |
| Developers và QA | Luồng dữ liệu, lỗi kỹ thuật, cách kiểm chứng và rủi ro tích hợp | Có tình huống cạnh tranh nào làm số chỗ sai lệch? |
| Người phụ trách bảo mật và quyền riêng tư | Mô hình truy cập, dữ liệu nhạy cảm, kịch bản tấn công, yêu cầu kiểm soát | Ai có thể xem danh sách đăng ký; cần lưu dấu vết gì? |
| Vận hành/SRE/hỗ trợ | Triển khai, cảnh báo, khôi phục, ca trực, giới hạn hạ tầng | Khi dịch vụ đăng ký lỗi lúc cao điểm, ai phát hiện và xử lý? |
| Nhóm tích hợp hoặc nền tảng | Hợp đồng API, phụ thuộc và khả năng chịu lỗi | Dịch vụ email chậm có được làm chậm xác nhận đăng ký không? |
| Bên quản lý rủi ro hoặc pháp lý khi áp dụng | Ràng buộc hợp đồng, thời gian lưu dữ liệu, quy trình phê duyệt | Dữ liệu nào phải xóa hoặc lưu theo chính sách đã xác nhận? |

Một nhóm liên chức năng nên tham gia cùng nhau khi làm rõ các rủi ro quan trọng. Mời chuyên gia tư vấn **không đồng nghĩa chuyển toàn bộ chất lượng hoặc bảo mật thành công việc của riêng chuyên gia đó**.

### 3.2. Từ hành trình người dùng tới tình huống thất bại

Với mỗi bước chính trong hành trình, đặt câu hỏi: **Nếu bước này không xảy ra như dự định, điều gì hỏng, ai bị ảnh hưởng và chúng ta phát hiện bằng cách nào?**

~~~mermaid
flowchart LR
    A["Xem workshop"] --> B["Chọn chỗ"]
    B --> C["Gửi đăng ký"]
    C --> D["Kiểm tra quyền và điều kiện"]
    D --> E["Ghi đăng ký nhất quán"]
    E --> F["Trả trạng thái rõ ràng"]
    F --> G["Gửi thông báo"]
    C -.-> H["Lỗi kết nối hoặc tải cao"]
    D -.-> I["Truy cập sai quyền"]
    E -.-> J["Hai yêu cầu tranh chỗ cuối"]
    G -.-> K["Dịch vụ email không khả dụng"]
~~~

Mỗi đường lỗi tạo ra câu hỏi cho backlog và kiểm thử. Chẳng hạn, lỗi email có thể cần **ghi việc gửi để thử lại**, trong khi giao dịch đăng ký vẫn hoàn tất và học viên nhìn thấy trạng thái đúng. Quyết định cụ thể phụ thuộc yêu cầu nghiệp vụ, nhưng nhóm phải **định nghĩa rõ trạng thái nào đã cam kết**, không hứa “đã đăng ký” khi dữ liệu chưa được lưu chắc chắn.

## 4. Phân loại yêu cầu theo cách nhóm có thể lập kế hoạch

Thay vì gom mọi yêu cầu vào một tài liệu “NFR” khó cập nhật, hãy quyết định **yêu cầu nào gắn trực tiếp với story, yêu cầu nào cần được thỏa mãn trên mọi Increment, yêu cầu nào cần công việc hỗ trợ riêng**.

| Loại yêu cầu | Cách biểu diễn thích hợp | Ví dụ |
| --- | --- | --- |
| **Điều kiện của một hành vi cụ thể** | Tiêu chí chấp nhận của user story | Đăng ký không vượt sức chứa; chỉ học viên sở hữu đăng ký được hủy |
| **Chuẩn chất lượng áp dụng xuyên suốt** | Definition of Done (DoD), tiêu chuẩn kỹ thuật và checklist kiểm chứng | Code review, kiểm thử tự động phù hợp, không để lộ bí mật trong mã, ghi log không chứa dữ liệu nhạy cảm |
| **Khả năng nền tảng cần xây** | Product Backlog Item kỹ thuật hoặc lát cắt hỗ trợ rõ kết quả | Thêm cơ chế kiểm soát đồng thời, thiết lập chỉ số và cảnh báo cho API đăng ký |
| **Giả định chưa kiểm chứng** | Spike/experiment có giới hạn thời gian, mục tiêu học được | Kiểm tra khả năng chịu tải với mẫu giao dịch và tập dữ liệu đại diện |
| **Ràng buộc phát hành hoặc vận hành** | Điều kiện phát hành/hoạt động, kế hoạch triển khai và vận hành | Cơ chế rollback đã thử, quy trình xử lý sự cố, người chịu trách nhiệm nhận cảnh báo |
| **Sự cố hoặc khoảng trống đã phát hiện** | Bug, risk hoặc hạng mục cải tiến được ưu tiên | Có thể đọc dữ liệu người khác; thiếu sao lưu; cảnh báo bỏ sót lỗi |

Một yêu cầu có thể xuất hiện ở **nhiều lớp bổ trợ**, miễn mỗi lớp có mục đích riêng. Ví dụ kiểm tra quyền khi hủy nằm trong tiêu chí chấp nhận của story; DoD yêu cầu kiểm thử quyền truy cập cho các endpoint phù hợp; còn hoạt động đánh giá phân quyền toàn hệ thống có thể là hạng mục riêng. Tránh ghi ba bản mô tả mâu thuẫn nhau.

### Ba cấp điều kiện thường bị lẫn

| Cấp | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Tiêu chí chấp nhận** (*acceptance criteria*) | Hạng mục cụ thể phải thể hiện hành vi nào? | Học viên A không hủy được đăng ký của học viên B |
| **Definition of Done** | Công việc phải đạt mức chất lượng chung nào để tính là Increment hoàn chỉnh? | Kiểm thử phù hợp đã chạy, tích hợp xong, review hoàn thành, tài liệu vận hành liên quan đã cập nhật |
| **Điều kiện phát hành** (*release readiness / operational readiness*) | Increment đã hoàn chỉnh có thể mở tới đối tượng hoặc môi trường mục tiêu an toàn chưa? | Cảnh báo và runbook hoạt động, có phương án khôi phục, đã hoàn tất kiểm tra bắt buộc cho lần phát hành |

Trong **Scrum**, Increment phải đáp ứng Definition of Done mới được xem là hoàn chỉnh; Sprint Review không phải cổng duy nhất cho phép release. Một tổ chức có thể có thủ tục phát hành riêng theo rủi ro, nhưng không nên biến điều kiện phát hành thành lý do để coi công việc **chưa đạt DoD** là đã Done.

## 5. Bảo mật phải đi từ thiết kế tới kiểm chứng

Một câu “bảo mật là quan trọng” không đủ để bảo vệ hệ thống. Yêu cầu bảo mật cần đi qua **mô hình đối tượng, quyền truy cập, luồng dữ liệu, khả năng tấn công và quy trình phản ứng sự cố**.

### 5.1. Xác định tài sản, tác nhân và ranh giới tin cậy

Trong đăng ký workshop:

- **Tài sản cần bảo vệ:** Tài khoản, danh sách học viên đăng ký, lịch học, dữ liệu liên hệ, trạng thái chỗ trống và dấu vết thao tác.
- **Tác nhân:** Học viên, mentor, nhân viên quản trị, dịch vụ thông báo và hệ thống tích hợp.
- **Hành vi hợp lệ:** Học viên xem/hủy đăng ký của mình; người quản trị có quyền xem hoặc điều chỉnh theo chính sách; dịch vụ gửi thông báo chỉ sử dụng dữ liệu cần thiết.
- **Ranh giới tin cậy:** Trình duyệt không thể được tin chỉ vì đã ẩn một nút; dữ liệu từ API bên ngoài cũng phải được xác minh; quyền ở máy chủ không phụ thuộc lời khai của người dùng.

Câu hỏi đe dọa đơn giản: **Điều gì có thể bị đọc sai người, sửa sai người, giả mạo, làm gián đoạn hoặc bị ghi nhận sai?** Đây là cách bắt đầu phân tích mối đe dọa (*threat modeling*) ở mức phù hợp, chưa phải một bài đánh giá an toàn đầy đủ cho mọi hệ thống.

### 5.2. Mẫu yêu cầu bảo mật kiểm chứng được

| Rủi ro | Yêu cầu/kiểm soát | Bằng chứng |
| --- | --- | --- |
| Thay mã đăng ký trong URL để truy cập của người khác | Mọi thao tác đọc/hủy kiểm tra quyền ở backend theo đối tượng cụ thể | Kiểm thử bằng hai tài khoản khác nhau; xác minh trạng thái từ chối |
| Gửi dữ liệu đầu vào không hợp lệ | Kiểm tra dữ liệu phía server, ràng buộc nghiệp vụ và xử lý lỗi an toàn | Kiểm thử giá trị thiếu, sai loại, sai miền, trường hợp biên |
| Chia sẻ quá nhiều thông tin | API chỉ trả dữ liệu cần cho vai trò hiện tại; log và thông báo không chứa bí mật | Review trường dữ liệu, kiểm thử phân quyền và mẫu log |
| Rò rỉ khóa hoặc mật khẩu dịch vụ | Bí mật được quản lý qua cơ chế phù hợp, không đưa vào mã hay thông tin ghi log | Quét secret, kiểm tra cấu hình và quyền truy cập |
| Thành phần phụ thuộc có lỗ hổng đã biết | Có cơ chế đánh giá phụ thuộc và xử lý lỗ hổng theo mức rủi ro | Kết quả kiểm tra, quyết định xử lý hoặc ngoại lệ đã chấp thuận |
| Hành động quản trị không truy vết được | Ghi các sự kiện nghiệp vụ quan trọng với người thực hiện và thời gian phù hợp | Kiểm tra audit log và quyền xem log |

Các hoạt động bảo mật phải được **ưu tiên theo tác động và khả năng xảy ra**, chứ không chỉ đếm số công cụ quét đã chạy. Đặc biệt với lỗi đọc/sửa dữ liệu của người khác, nhóm không nên chờ phát hành rộng rồi mới xem đó là ưu tiên.

### 5.3. Bảo mật trong mỗi vòng phát triển

1. **Khám phá:** Làm rõ dữ liệu cần bảo vệ, tác nhân, quyền và rủi ro chính khi viết story.
2. **Thiết kế:** Chọn giải pháp giữ ranh giới quyền, cách xác thực/ủy quyền, tính nhất quán và phương án xử lý lỗi.
3. **Triển khai:** Thực hiện kiểm tra đầu vào, quyền, cấu hình và xử lý bí mật ở nơi đáng tin cậy.
4. **Kiểm chứng:** Dùng kiểm thử tự động, review và kiểm tra chuyên sâu theo rủi ro.
5. **Phát hành và vận hành:** Theo dõi hành vi bất thường phù hợp, có quy trình xử lý và cập nhật khi xuất hiện mối đe dọa mới.

**Shift left** có nghĩa đưa các thảo luận và kiểm tra phù hợp đến sớm hơn; không có nghĩa mọi kiểm thử bảo mật chỉ làm ở đầu dự án. Hệ thống vẫn cần giám sát, kiểm chứng và cải tiến sau khi hoạt động.

## 6. Yêu cầu vận hành là một phần của hành vi sản phẩm

Người dùng không phân biệt một lỗi bắt nguồn từ giao diện, cơ sở dữ liệu, mạng hay quá trình triển khai; họ chỉ thấy sản phẩm thất bại. Vì vậy, nhóm cần xem **khả năng vận hành và khôi phục** là phần của chất lượng dịch vụ.

### 6.1. Những yêu cầu vận hành cơ bản

| Khía cạnh | Cần làm rõ | Ví dụ yêu cầu hoặc sản phẩm công việc |
| --- | --- | --- |
| **Quan sát** (*observability*) | Làm sao phát hiện hệ thống đang lỗi hoặc suy giảm? | Chỉ số số yêu cầu, tỷ lệ lỗi, độ trễ, số chỗ xác nhận sai; log có mã tương quan |
| **Cảnh báo** | Điều gì đủ nghiêm trọng để gọi người xử lý? | Cảnh báo khi tỷ lệ lỗi vượt ngưỡng trong thời gian đã xác định hoặc xuất hiện lỗi dữ liệu nghiêm trọng |
| **Triển khai** | Làm sao đưa thay đổi vào môi trường mục tiêu? | Pipeline kiểm thử; cấu hình môi trường; thay đổi schema có kế hoạch |
| **Khôi phục** | Làm sao quay lại trạng thái ổn định? | Rollback hoặc tắt tính năng; quy trình phục hồi có tập dượt |
| **Sao lưu và phục hồi dữ liệu** | Cho phép mất dữ liệu bao nhiêu và ngừng dịch vụ bao lâu? | Chính sách backup, thử restore và mục tiêu phục hồi đã thống nhất |
| **Phụ thuộc bên ngoài** | Dịch vụ khác lỗi thì phần chính phản ứng ra sao? | Timeout, retry có kiểm soát, trạng thái rõ ràng, tránh lặp giao dịch |
| **Hỗ trợ và trách nhiệm** | Ai nhận, phân loại và xử lý sự cố? | Runbook, owner, kênh liên hệ và mức ưu tiên sự cố |
| **Chi phí và năng lực** | Hạ tầng có đáp ứng tải với chi phí cho phép? | Kịch bản tải, theo dõi tài nguyên và khả năng mở rộng |

Một dashboard có nhiều đồ thị không chứng minh hệ thống đã vận hành tốt. Nhóm cần chứng minh **có tín hiệu phát hiện vấn đề, có người nhận tín hiệu và có hành động khôi phục khả thi**.

### 6.2. SLI, SLO và SLA khác nhau ở đâu?

- **SLI (Service Level Indicator):** Chỉ số đo một mặt dịch vụ, ví dụ tỷ lệ yêu cầu đăng ký hợp lệ được xử lý thành công.
- **SLO (Service Level Objective):** Mục tiêu nội bộ của SLI trong một khoảng thời gian, ví dụ một mục tiêu độ sẵn sàng được nhóm và bên liên quan thống nhất.
- **SLA (Service Level Agreement):** Thỏa thuận dịch vụ với bên liên quan hoặc khách hàng, thường nêu nghĩa vụ và hệ quả nếu không đạt, tùy hợp đồng.

Không phải mọi tính năng đều cần SLA riêng. SLO chỉ có ý nghĩa khi định nghĩa SLI, phạm vi đo và tác động người dùng rõ. Ví dụ một tỷ lệ lỗi tổng hợp có thể che việc API đăng ký bị hỏng trong khi các trang ít quan trọng vẫn hoạt động; hãy đo những luồng **quan trọng với người dùng**.

### 6.3. RTO và RPO khi lên kế hoạch khôi phục

- **RTO (Recovery Time Objective):** Mục tiêu thời gian tối đa để phục hồi hoạt động sau sự cố theo phạm vi đã định nghĩa.
- **RPO (Recovery Point Objective):** Mức dữ liệu có thể chấp nhận mất tính từ điểm khôi phục so với thời điểm sự cố.

Hai mục tiêu này thường bị nhầm. Khôi phục dịch vụ trong 30 phút không tự nói lên dữ liệu có thể mất bao nhiêu. Với đăng ký có sức chứa giới hạn, cả **thời gian gián đoạn** và **tính đúng đắn của dữ liệu sau phục hồi** đều quan trọng. Mọi ngưỡng cụ thể phải do tổ chức quyết trên cơ sở tác động, năng lực và chi phí, rồi được kiểm tra bằng diễn tập.

### 6.4. Khả năng khôi phục không chỉ là nút rollback

Nếu phiên bản mới đã thay đổi dữ liệu hoặc cấu trúc bảng theo cách không tương thích, rollback phần mềm chưa chắc đưa dữ liệu trở lại đúng trạng thái. Một kế hoạch phát hành cần cân nhắc:

1. Thay đổi schema có tương thích với phiên bản cũ trong giai đoạn chuyển đổi không?
2. Việc gửi thông báo hoặc thanh toán có thể xảy ra lặp khi thử lại không?
3. Khi tắt tính năng, dữ liệu phát sinh trong thời gian mở sẽ được xử lý thế nào?
4. Ai quyết định rollback, theo tín hiệu nào, và ai thông báo cho người bị ảnh hưởng?

Làm rõ những câu hỏi này trước khi phát hành sẽ giảm rủi ro, đặc biệt với hệ thống có dữ liệu khó phục hồi.

## 7. Ưu tiên chất lượng, bảo mật và vận hành trong backlog

Một Product Backlog không chỉ có màn hình và API phục vụ tính năng trực tiếp. Nó cần phản ánh các công việc **tạo khả năng giao giá trị bền vững**.

### 7.1. Xem yêu cầu qua giá trị, rủi ro và phụ thuộc

Khi cân nhắc một hạng mục chất lượng, hãy hỏi:

1. **Nếu bỏ hạng mục này, điều gì có thể xảy ra với người dùng hoặc tổ chức?**
2. **Rủi ro có thể xuất hiện ngay trong lát cắt sắp giao hay chỉ khi quy mô lớn hơn?**
3. **Hạng mục này là điều kiện bắt buộc để giao an toàn hay là tối ưu có thể làm sau?**
4. **Có thể thử một phần nhỏ để giảm bất định trước khi đầu tư toàn bộ không?**
5. **Bỏ qua bây giờ có tạo phụ thuộc hoặc chi phí làm lại lớn không?**

Một lỗ hổng cho phép xem dữ liệu người khác thường cần xử lý trước khi mở tính năng cho người dùng thật. Trái lại, việc tối ưu thời gian tải từ mức đã đáp ứng mục tiêu xuống thấp hơn nữa có thể được ưu tiên sau một nhu cầu thiết yếu hơn. **Không có bảng xếp hạng cố định áp dụng được cho mọi sản phẩm**.

### 7.2. Minh họa backlog cân bằng cho chức năng đăng ký

| Hạng mục backlog | Loại | Kết quả kỳ vọng | Bằng chứng hoàn thành |
| --- | --- | --- | --- |
| Học viên đăng ký một workshop còn chỗ | Lát cắt chức năng | Người học tự hoàn thành luồng chính | Kiểm thử hành vi đầu cuối và dữ liệu |
| Ngăn xác nhận vượt sức chứa khi yêu cầu đồng thời | Điều kiện nghiệp vụ/chất lượng | Không xuất hiện chỗ được xác nhận vượt giới hạn | Kiểm thử cạnh tranh, ràng buộc lưu trữ |
| Chỉ chủ sở hữu được hủy đăng ký | Bảo mật gắn vào story | Không sửa được dữ liệu của người khác | Kiểm thử ủy quyền với nhiều tài khoản |
| Xây chỉ số và cảnh báo lỗi đăng ký | Năng lực vận hành | Nhóm phát hiện và xử lý sự cố sớm | Kiểm tra sự kiện, tuyến cảnh báo và runbook |
| Khảo sát tải giờ cao điểm | Spike | Hiểu ngưỡng đáp ứng và điểm nghẽn | Báo cáo kịch bản tải, đo lường, quyết định tiếp theo |
| Thử khôi phục dữ liệu đăng ký | Năng lực vận hành | Có bằng chứng phục hồi đúng dữ liệu | Diễn tập restore và xác minh nhất quán |
| Tối ưu bộ lọc tìm workshop | Chức năng/khả năng dùng | Học viên dễ tìm sự kiện phù hợp | Quan sát sử dụng, kiểm thử tác vụ |

Nếu những hạng mục chất lượng và vận hành bị ẩn thành “việc nội bộ làm khi rảnh”, người phụ trách sản phẩm dễ đánh giá sai khả năng bàn giao. Cần giải thích **giá trị hoặc rủi ro mà chúng giải quyết** để ưu tiên cùng các tính năng khác.

### 7.3. Không biến mọi kiểm tra nhỏ thành một story riêng

Một số yêu cầu phải gắn trực tiếp vào user story và DoD. Nếu nhóm tách “xác thực quyền”, “kiểm thử”, “bảo mật” và “viết log” thành các việc luôn thực hiện sau khi story được đánh dấu Done, họ có thể tạo ra nhiều mục “hoàn thành” nhưng chưa có Increment đủ chất lượng.

Tách riêng khi công việc thực sự cần được **lập kế hoạch độc lập**: xây cơ chế giám sát chung, nâng cấp khả năng thử tải, diễn tập phục hồi, xử lý một lỗ hổng hiện có. Với hành vi bảo mật và chất lượng thiết yếu của story mới, hãy đưa vào **định nghĩa hoàn thành của chính story đó**.

## 8. Chia nhỏ theo lát cắt chức năng mà vẫn giữ chất lượng

Đặt mục tiêu giao tăng dần dễ tạo cám dỗ: “Sprint này làm giao diện, Sprint sau mới thêm kiểm tra quyền, cuối dự án mới viết cảnh báo.” Đây là cách trì hoãn chất lượng, không phải chia nhỏ giá trị.

**Lát cắt dọc** (*vertical slice*) nên đi qua đủ tầng cần thiết để người dùng hoàn thành một việc có ý nghĩa, đồng thời giữ các điều kiện chất lượng bắt buộc của phạm vi ấy.

### Ví dụ lộ trình tăng dần

Các mốc dưới đây chỉ minh họa trình tự học hỏi, **không quy định mọi nhóm phải dùng Sprint một tuần hoặc phải phát hành công khai sau từng mốc**.

| Lát cắt | Giá trị được giao | Chất lượng và bảo mật đi kèm | Vận hành và học hỏi |
| --- | --- | --- | --- |
| **1. Đăng ký cơ bản** | Một học viên đủ điều kiện đăng ký workshop còn chỗ và biết kết quả | Kiểm tra quyền, không vượt chỗ, dữ liệu nhất quán, thông báo lỗi rõ | Log/metric cho luồng chính, cách vô hiệu hóa khi sự cố, kiểm thử đầu cuối |
| **2. Xem và hủy đăng ký** | Học viên quản lý đăng ký của mình | Không xem/hủy của người khác; cập nhật chỗ an toàn; kiểm tra trường hợp đồng thời | Theo dõi tỷ lệ hủy lỗi, xác minh dấu vết thay đổi |
| **3. Thông báo và phụ thuộc** | Gửi xác nhận/nhắc lịch theo chính sách | Không lộ dữ liệu; tránh gửi nhầm hoặc gửi trùng; lỗi email không làm sai giao dịch | Theo dõi hàng đợi, thử lại có kiểm soát, cảnh báo khi lỗi kéo dài |
| **4. Mở rộng tải** | Phục vụ nhiều nhóm học viên hơn | Kiểm chứng độ trễ, độ tin cậy và giới hạn đã thống nhất | Thử tải, xem xét năng lực, diễn tập khôi phục và mở rộng có kiểm soát |

Mỗi lát cắt có thể có **điều kiện riêng theo rủi ro của phạm vi mở ra**. Nếu một luồng cho phép hủy và hoàn tiền đã được mở ở lát cắt đầu, các kiểm soát liên quan phải nằm ngay ở lát cắt ấy; không được viện lý do “sẽ làm bảo mật ở lát cắt 3”.

### Sơ đồ kết hợp ba chiều trong một Increment

~~~mermaid
flowchart TD
    A["Chọn kết quả người dùng có giá trị"] --> B["Xác định rủi ro chất lượng, bảo mật, vận hành"]
    B --> C["Viết tiêu chí chấp nhận + DoD + điều kiện phát hành"]
    C --> D["Chia lát cắt dọc và đưa việc cần thiết vào backlog"]
    D --> E["Xây dựng, kiểm thử và tích hợp"]
    E --> F{"Bằng chứng đạt điều kiện đã thống nhất?"}
    F -->|"Chưa"| G["Sửa lỗi hoặc điều chỉnh phạm vi chưa mở"]
    G --> E
    F -->|"Đạt"| H["Bàn giao/phát hành phù hợp rủi ro"]
    H --> I["Quan sát, phản hồi, cập nhật backlog"]
    I --> A
~~~

Agile cho phép **thích ứng giải pháp và thứ tự công việc** khi có bằng chứng mới. Nó không cho phép gọi phần việc chưa an toàn là hoàn thành chỉ vì thời hạn Sprint đã tới.

## 9. Ví dụ tiêu chí chấp nhận tích hợp chất lượng và bảo mật

Với user story “Là học viên, tôi muốn đăng ký workshop còn chỗ để biết chắc mình có thể tham gia”, nhóm có thể xác định các kịch bản đủ để bắt đầu triển khai:

~~~gherkin
Feature: Dang ky workshop

  Scenario: Hoc vien du dieu kien dat cho thanh cong
    Given hoc vien A da dang nhap va du dieu kien dang ky
    And workshop W con cho trong
    When hoc vien A gui yeu cau dang ky hop le
    Then he thong ghi nhan dang ky da xac nhan
    And hoc vien A nhan trang thai ro rang

  Scenario: Hai yeu cau tranh cho cuoi cung
    Given workshop W chi con 1 cho
    When hai hoc vien khac nhau gui yeu cau gan nhu dong thoi
    Then tong so dang ky duoc xac nhan khong vuot suc chua
    And yeu cau khong thanh cong nhan thong bao phu hop

  Scenario: Khong duoc huy dang ky cua nguoi khac
    Given hoc vien A co dang ky R
    And hoc vien B khong co quyen quan ly dang ky R
    When hoc vien B gui yeu cau huy dang ky R
    Then he thong tu choi thao tac
    And trang thai dang ky R khong thay doi
~~~

Các kịch bản trên mô tả **hành vi nghiệp vụ có thể kiểm chứng**; chúng chưa đủ bao quát tất cả đe dọa bảo mật, tình huống lỗi hoặc yêu cầu vận hành. Nhóm còn cần xác định điều kiện kiểm thử phù hợp, chẳng hạn trạng thái chưa đăng nhập, yêu cầu lặp, lỗi cơ sở dữ liệu và sự cố tích hợp.

### Chất lượng của tiêu chí chấp nhận

Một tiêu chí tốt nên có:

1. **Điều kiện đầu vào rõ:** Người dùng, trạng thái dữ liệu, quyền và điều kiện môi trường.
2. **Hành vi quan sát được:** Yêu cầu nào được gửi, hệ thống phải trả lời và lưu trạng thái gì.
3. **Trường hợp lỗi quan trọng:** Thiếu quyền, hết chỗ, yêu cầu trùng, dịch vụ phụ thuộc không hoạt động.
4. **Bằng chứng kiểm chứng:** Kiểm thử tự động/thủ công phù hợp, log/metric hoặc buổi thử người dùng.

Không cần viết mọi trường hợp dưới dạng Gherkin. Bảng ví dụ, mô hình trạng thái, sơ đồ luồng, checklist hoặc mô tả bằng lời rõ ràng cũng có thể phù hợp, miễn các bên hiểu thống nhất và biết cách kiểm chứng.

## 10. Definition of Done cần bảo vệ khả năng giao Increment

DoD là thỏa thuận minh bạch về chất lượng cần đạt trước khi một phần sản phẩm được coi là hoàn chỉnh. Một DoD thực dụng cho nhóm phát triển có thể đề cập:

| Nhóm kiểm tra | Câu hỏi trước khi đánh dấu Done |
| --- | --- |
| Hành vi và dữ liệu | Story đạt tiêu chí chấp nhận? Các ràng buộc dữ liệu và lỗi quan trọng đã được xử lý? |
| Tích hợp | Code được tích hợp vào phiên bản chung? Phụ thuộc hoạt động theo hợp đồng đã thống nhất? |
| Kiểm thử | Kiểm thử tự động và kiểm tra cần thiết theo rủi ro đã qua? Có lỗi nghiêm trọng chưa xử lý? |
| Bảo mật | Quyền truy cập và đầu vào được kiểm tra? Bí mật không bị lộ? Các yêu cầu bảo mật liên quan đã được xác minh? |
| Khả năng sử dụng | Luồng chính và thông báo lỗi đủ rõ, truy cập được với nhóm người dùng mục tiêu? |
| Vận hành | Có log/metric, xử lý lỗi và tài liệu vận hành cần thiết cho thay đổi? |
| Minh bạch | Những giới hạn, quyết định kỹ thuật và thông tin cần bàn giao đã được cập nhật? |

DoD **không phải văn bản bất biến**. Nhóm có thể nâng tiêu chuẩn khi trưởng thành, sản phẩm thay đổi hoặc phát hiện rủi ro mới. Nếu tổ chức có tiêu chuẩn DoD chung, Scrum Team phải tuân thủ tối thiểu tiêu chuẩn đó; tiêu chuẩn thêm của nhóm không nên thấp hơn phần bắt buộc.

**Không đánh đồng “đã chạy đủ công cụ” với “đủ an toàn”.** Một kết quả quét tĩnh sạch không bảo đảm endpoint kiểm tra đúng quyền đối tượng; kiểm thử hiệu năng thành công trên dữ liệu quá nhỏ không bảo đảm tải thực tế; pipeline xanh không bảo đảm yêu cầu nghiệp vụ đã hiểu đúng.

## 11. Lập kế hoạch theo rủi ro và bằng chứng, không chờ đến cuối

Những yêu cầu chưa chắc chắn cần **được kiểm chứng sớm**, nhất là khi quyết định có chi phí đổi lớn. Nhóm có thể lập một bảng rủi ro gọn:

| Giả định/rủi ro | Hậu quả nếu sai | Điều cần làm sớm | Khi nào mới đủ yên tâm? |
| --- | --- | --- | --- |
| Cách trừ chỗ vẫn đúng dưới truy cập đồng thời | Xác nhận vượt sức chứa, khiếu nại | Thiết kế invariant và kiểm thử giao dịch đồng thời | Kiểm thử các kịch bản cạnh tranh quan trọng đạt; cách xử lý lỗi rõ |
| Có thể giới hạn quyền theo từng đăng ký | Rò rỉ hoặc sửa dữ liệu người khác | Làm rõ chính sách, viết kiểm thử ủy quyền ngay từ story đầu | Vai trò, đối tượng và thao tác được kiểm chứng |
| Dịch vụ email ổn định | Người học không nhận thông báo | Kiểm thử lỗi/timeout, định nghĩa trạng thái và xử lý thử lại | Luồng đăng ký đúng dù email lỗi; cảnh báo phù hợp |
| Tải giờ cao điểm đáp ứng được | Độ trễ cao, bỏ dở đăng ký | Đo tải cơ sở, thử mẫu tải đại diện | Đạt ngưỡng dịch vụ đã thống nhất hoặc có kế hoạch giảm rủi ro được chấp thuận |
| Có thể khôi phục nếu lỗi phát hành | Gián đoạn kéo dài, dữ liệu sai | Thử rollback/restore với kịch bản đại diện | Diễn tập đạt mục tiêu phục hồi liên quan |

Không phải mọi rủi ro cần một đợt nghiên cứu lớn. Có thể dùng **spike có giới hạn**, bản mẫu, mô hình dữ liệu nhỏ, kiểm thử tự động hoặc chạy thử trong môi trường cô lập. Kết quả spike nên là **quyết định và bằng chứng**, không phải lời hứa “phần đó chắc chắn xong”.

### Khi các ràng buộc mâu thuẫn nhau

Đôi khi yêu cầu “phản hồi dưới một ngưỡng rất thấp” xung đột với “kiểm tra nhiều điều kiện và ghi dấu vết đầy đủ”; hoặc “lưu log chi tiết để điều tra” xung đột với “không lưu dữ liệu nhạy cảm”.

Nhóm cần:

1. Làm rõ **mục đích của từng yêu cầu**, không chỉ câu chữ.
2. Phân biệt **điều bắt buộc** (ví dụ quyền truy cập đúng) với **mục tiêu có thể đàm phán** (ví dụ ngưỡng độ trễ chưa có dữ liệu).
3. Tìm phương án kỹ thuật giảm xung đột: ghi sự kiện đã được làm sạch dữ liệu; tối ưu kiểm tra quyền; xử lý bất đồng bộ những việc không cần chặn giao dịch.
4. Khi vẫn có đánh đổi, đưa phương án, tác động và bằng chứng cho **người có quyền quyết định**; ghi quyết định và điều kiện xem lại.

Agile giúp phản hồi và điều chỉnh lựa chọn, nhưng **không trao quyền tự ý bỏ nghĩa vụ bảo mật, quyền riêng tư hay các cam kết đã được xác định**.

## 12. Gắn yêu cầu vào kế hoạch Sprint, dòng công việc và phát hành

### 12.1. Với Scrum

Product Owner làm rõ giá trị và sắp xếp Product Backlog; Developers cùng phân tích tính khả thi, rủi ro và công việc cần thiết để tạo Increment đạt DoD. Trong Sprint Planning, Scrum Team xác định Sprint Goal và chọn cách triển khai phù hợp với năng lực hiện có.

Ví dụ, nếu Sprint Goal là **“Học viên đăng ký được workshop và biết chắc trạng thái”**, Developers không nên chỉ đưa giao diện và API cơ bản vào Sprint Backlog rồi hoãn kiểm soát cạnh tranh và phân quyền sang Sprint sau. Những kiểm soát ấy là một phần của chức năng có thể giao an toàn.

Nếu giữa Sprint phát hiện thêm rủi ro nghiêm trọng, nhóm trao đổi với Product Owner về phạm vi và kế hoạch, giữ Sprint Goal làm định hướng. Công việc được xem lại minh bạch; **không hạ DoD để làm đẹp báo cáo**.

### 12.2. Với Kanban

Trực quan hóa toàn bộ các bước cần để hạng mục thực sự hoàn tất: làm rõ yêu cầu, triển khai, review, kiểm thử phù hợp, xác minh vận hành, sẵn sàng bàn giao. Đặt chính sách cụ thể cho điểm vào/ra của từng trạng thái và giới hạn WIP.

Một bảng công việc chỉ có cột “Đang code” và “Done” có thể che khuất hàng đợi kiểm thử bảo mật hoặc khâu phê duyệt triển khai. Đo **cycle time** và tuổi công việc đang làm giúp tìm nơi bị chờ. Việc giảm WIP có thể tạo năng lực hoàn thành các hạng mục chất lượng, thay vì khởi động quá nhiều tính năng.

### 12.3. Với XP và thực hành kỹ thuật

Kiểm thử tự động, refactoring, tích hợp liên tục, thiết kế đơn giản và phản hồi nhanh giúp nhóm đưa thay đổi nhỏ vào phần mềm mà vẫn kiểm soát rủi ro. Nhưng kỹ thuật tốt phải đi cùng **câu hỏi kiểm thử đúng**. Kiểm thử chỉ đường đi thành công không thay thế kiểm thử quyền, dữ liệu đồng thời hoặc lỗi tích hợp.

### 12.4. Với kế hoạch phát hành

Nên nhìn kế hoạch như chuỗi lựa chọn:

**Kết quả người dùng cần đạt → ràng buộc và rủi ro → lát cắt và backlog → DoD → điều kiện phát hành → quan sát thực tế → thay đổi ưu tiên.**

Không nhất thiết cứ kết thúc Sprint là phải mở cho mọi người dùng. Một Increment đạt DoD có thể được kiểm chứng hoặc phát hành ở phạm vi giới hạn, còn việc phát hành công khai phụ thuộc mức độ sẵn sàng, chính sách và rủi ro.

## 13. Đo lường cả dòng công việc, độ tin cậy và giá trị

Nếu chỉ đo số story hoàn thành hoặc tốc độ triển khai, nhóm có thể tăng tốc làm tính năng trong khi vấn đề chất lượng và vận hành tích tụ. Cần theo dõi một tập chỉ báo cân bằng.

| Góc nhìn | Chỉ số hoặc tín hiệu gợi ý | Cách tránh diễn giải sai |
| --- | --- | --- |
| **Dòng công việc** | Lead time, cycle time, WIP, throughput và thời gian chờ review/kiểm thử | Thống nhất điểm đầu/cuối, không dùng số lượng việc làm thước đo chất lượng cá nhân |
| **Chất lượng** | Lỗi lọt sau phát hành, lỗi dữ liệu, tỷ lệ làm lại, kiểm thử bị lỗi | Xem mức ảnh hưởng và xu hướng; số lỗi thấp có thể vì quan sát kém |
| **Bảo mật** | Lỗi phân quyền phát hiện, thời gian xử lý rủi ro, độ phủ của kiểm tra liên quan | Không coi “0 cảnh báo” là bằng chứng chắc chắn an toàn |
| **Vận hành** | Tỷ lệ yêu cầu thành công, độ trễ, thời gian phát hiện và phục hồi sự cố | Đo những luồng quan trọng, phân biệt nhiễu cảnh báo với vấn đề thật |
| **Giá trị** | Tỷ lệ đăng ký thành công hợp lệ, giảm xử lý hỗ trợ, cảm nhận người dùng | Không đồng nhất nhiều click hoặc nhiều deploy với giá trị |
| **Khả năng thích ứng** | Thời gian từ khi phát hiện rủi ro tới khi có kiểm chứng hoặc quyết định | Nhanh mà thiếu bằng chứng không hẳn tốt hơn |

Một ví dụ diễn giải: nếu cycle time giảm nhưng lỗi sau phát hành và thời gian khôi phục cùng tăng, nhóm cần kiểm tra liệu các bước chất lượng đang bị bỏ qua hoặc trở thành điểm nghẽn ẩn. Nếu hệ thống xử lý ít sự cố hơn sau khi bổ sung kiểm thử và quan sát, đó là tín hiệu tích cực nhưng cần xét các yếu tố như thay đổi lưu lượng, loại công việc và cách ghi nhận.

**Chỉ số phục vụ học hỏi và quyết định**, không nên biến thành cuộc thi xếp hạng cá nhân. Một nhóm phát hiện nhiều lỗ hổng nhờ cải thiện kiểm tra chưa chắc kém an toàn hơn nhóm không phát hiện gì.

## 14. Quy trình thực hành bảy bước

### Bước 1. Chọn luồng tạo giá trị và điều kiện sử dụng

Viết user story hoặc mô tả kết quả cụ thể, xác định nhóm người dùng, thiết bị, dữ liệu, tải, giờ cao điểm và phụ thuộc chính. Ví dụ: một học viên đủ điều kiện đăng ký một workshop còn chỗ và nhận kết quả rõ ràng.

### Bước 2. Hỏi “điều gì phải đúng?” và “điều gì có thể hỏng?”

Xác định bất biến dữ liệu, quyền truy cập, yêu cầu sử dụng, thời gian phản hồi, lỗi tích hợp, cách phát hiện và phục hồi. Mời đúng người có thông tin cùng trao đổi, nhất là khi thay đổi chạm tới dữ liệu nhạy cảm hoặc các nhóm khác.

### Bước 3. Biến yêu cầu thành điều kiện kiểm chứng

Với từng yêu cầu, ghi điều kiện, hành vi, mức chấp nhận, bằng chứng và người có quyền xác nhận. Nếu chưa có thông tin để đặt ngưỡng, tạo hạng mục đo cơ sở hoặc thử nghiệm, không tự bịa thông số.

### Bước 4. Phân bổ vào story, DoD, backlog hỗ trợ và điều kiện phát hành

Yêu cầu gắn với một hành vi nên có trong tiêu chí chấp nhận; tiêu chuẩn chung nằm trong DoD; năng lực nền tảng hoặc rủi ro chưa rõ trở thành hạng mục được ưu tiên; ràng buộc triển khai được đưa vào điều kiện phát hành và kế hoạch vận hành.

### Bước 5. Chia lát cắt dọc có thể sử dụng và kiểm chứng

Chọn phạm vi nhỏ nhất tạo giá trị mà vẫn đáp ứng yêu cầu an toàn bắt buộc. Nếu chưa thể triển khai đủ năng lực, **giảm phạm vi người dùng hoặc chức năng được mở**, không loại bỏ kiểm soát quan trọng.

### Bước 6. Tích hợp, kiểm thử, quan sát và diễn tập phù hợp

Thực hiện kiểm thử chức năng, bảo mật, tải hoặc khôi phục theo rủi ro. Với thay đổi lớn, chuẩn bị cảnh báo, runbook, rollback và kiểm tra dữ liệu trước khi mở rộng. Ghi lại bằng chứng và giới hạn chưa được xác nhận.

### Bước 7. Đánh giá bằng kết quả và điều chỉnh backlog

Sau khi người dùng thực sự sử dụng, quan sát hiệu năng, lỗi, hành vi và tác động. Cập nhật ưu tiên: có thể thêm kiểm soát, cải thiện trải nghiệm, xử lý nợ kỹ thuật hoặc dừng một phương án chưa tạo giá trị. Việc cập nhật có người chịu trách nhiệm và lý do rõ ràng.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Viết “nhanh, an toàn, ổn định” rồi không định nghĩa thêm | Không thể kiểm chứng hoặc thống nhất nghiệm thu | Viết điều kiện, hành vi, mục tiêu và cách thu bằng chứng |
| Chờ hết dự án mới kiểm tra bảo mật và tải | Phát hiện muộn, sửa tốn kém, nguy cơ hoãn phát hành | Khám phá rủi ro sớm, kiểm chứng theo lát cắt |
| Mọi yêu cầu chất lượng đều nằm trong một epic không được ưu tiên | Công việc quan trọng bị trì hoãn vô hạn | Đưa vào story/DoD hoặc backlog rõ kết quả và rủi ro |
| Đánh dấu Done khi mới code xong | Increment chưa tích hợp hoặc chưa an toàn | Giữ DoD rõ và kiểm chứng được |
| Tuyên bố “Agile nên không cần tài liệu” | Không có căn cứ vận hành, quyền và quyết định khó truyền đạt | Ghi vừa đủ: tiêu chí, ranh giới, quyết định, runbook và bằng chứng |
| Ép mọi rủi ro có một ngưỡng duy nhất | Bỏ qua bối cảnh, độ nguy hiểm và chi phí | Chọn ngưỡng theo dịch vụ, nhóm người dùng và hậu quả |
| Chỉ dùng kết quả scan làm bằng chứng bảo mật | Bỏ sót lỗi nghiệp vụ và sai quyền đối tượng | Kết hợp phân tích đe dọa, review và kiểm thử hành vi |
| Chỉ nhìn trung bình độ trễ | Che các yêu cầu chậm ở phần đuôi và lỗi giờ cao điểm | Xem phân phối, tải, tỷ lệ lỗi và kịch bản đại diện |
| Có dashboard nhưng không có người nhận cảnh báo | Sự cố được ghi nhưng không được xử lý | Xác định owner, ngưỡng, kênh cảnh báo và runbook |
| Có backup nhưng chưa từng thử restore | Không biết dữ liệu có phục hồi được đúng yêu cầu không | Diễn tập và kiểm chứng tính nhất quán theo rủi ro |
| Ép release đúng lịch dù không đạt điều kiện an toàn | Tổn thất người dùng và công sức phục hồi tăng | Thương lượng giảm phạm vi hoặc hoãn mở tính năng; không che rủi ro |
| Chất lượng là “việc của QA”, bảo mật là “việc của security”, vận hành là “việc của ops” | Quyết định phân mảnh, phản hồi chậm | Trách nhiệm phối hợp xuyên suốt và ranh giới chuyên môn rõ |

## 16. Mẫu kế hoạch một lát cắt có thể dùng lại

Mẫu sau giúp nhóm đặt yêu cầu chất lượng, bảo mật và vận hành **cạnh giá trị người dùng**, thay vì ghi ở cuối tài liệu.

~~~text
TÊN LÁT CẮT:
NGƯỜI DÙNG / GIÁ TRỊ CẦN GIAO:
ĐIỀU KIỆN SỬ DỤNG VÀ PHẠM VI:

HÀNH VI CHÍNH VÀ TIÊU CHÍ CHẤP NHẬN:
- Trường hợp thành công:
- Trường hợp không hợp lệ / lỗi quan trọng:

YÊU CẦU CHẤT LƯỢNG:
- Tính đúng đắn / nhất quán:
- Khả năng sử dụng / tiếp cận:
- Tải và thời gian phản hồi:
- Bằng chứng kiểm chứng:

YÊU CẦU BẢO MẬT VÀ QUYỀN RIÊNG TƯ:
- Dữ liệu, tác nhân, quyền được phép:
- Rủi ro chính và kiểm soát cần có:
- Bằng chứng kiểm tra:

YÊU CẦU VẬN HÀNH:
- Sự kiện / chỉ số / cảnh báo:
- Lỗi phụ thuộc và cách phục hồi:
- Runbook / người chịu trách nhiệm:
- Điều kiện phát hành:

GIẢ ĐỊNH CHƯA BIẾT:
- Cách thử nhỏ nhất để kiểm chứng:

RÀNG BUỘC PHẢI GIỮ:
MỤC BACKLOG / PHỤ THUỘC:
DEFINITION OF DONE ÁP DỤNG:
NGƯỜI CÓ QUYỀN XÁC NHẬN ĐIỀU KIỆN:
KẾT QUẢ QUAN SÁT SAU BÀN GIAO:
QUYẾT ĐỊNH VÀ LẦN XEM XÉT TIẾP:
~~~

Mẫu cần được **tinh chỉnh theo mức rủi ro**. Một nhãn giao diện ít tác động không cần hồ sơ dài bằng thay đổi phân quyền hoặc thanh toán. Nhưng yêu cầu ít giấy tờ hơn không đồng nghĩa được bỏ kiểm soát cần thiết.

## 17. Bài tập áp dụng

**Bối cảnh:** Nhóm xây chức năng cho học viên tải chứng chỉ hoàn thành khóa học. Bên liên quan muốn phát hành trong hai tuần. Bản đầu tiên cho phép nhấn **Tải chứng chỉ** để tạo tệp PDF và trả về cho người dùng.

Hãy lập kế hoạch cho một lát cắt đầu tiên theo các câu hỏi:

1. **Giá trị người dùng:** Ai được tải chứng chỉ, điều kiện đủ và kết quả cần nhìn thấy là gì?
2. **Tính đúng đắn:** Chứng chỉ có thể bị tạo nhầm cho học viên chưa hoàn thành không? Làm sao kiểm chứng dữ liệu đầu vào?
3. **Bảo mật/quyền riêng tư:** Nếu học viên đổi mã chứng chỉ trên URL, có thể tải tệp của người khác không? Dữ liệu nào được phép xuất hiện trong tệp và log?
4. **Chất lượng:** Nếu việc tạo PDF mất nhiều thời gian hoặc thất bại, người dùng sẽ nhận trạng thái nào? Ngưỡng chờ nào cần đo trước khi cam kết?
5. **Vận hành:** Nhóm phát hiện tỷ lệ tạo tệp lỗi ra sao? Có giới hạn tài nguyên, cơ chế thử lại và cách xử lý khi dịch vụ tạo PDF không hoạt động không?
6. **Backlog:** Điều nào là tiêu chí chấp nhận của story, điều nào thuộc DoD, điều nào cần spike hoặc hạng mục hỗ trợ riêng?
7. **Phát hành:** Nếu PDF đã tạo được nhưng kiểm thử quyền truy cập không đạt, có nên mở cho toàn bộ học viên chỉ để giữ lịch không? Có thể thay đổi phạm vi hoặc kế hoạch thế nào?

### Gợi ý hướng giải

Một lát cắt có giá trị có thể là **học viên đã hoàn thành khóa được tải chứng chỉ của chính mình**, hiển thị dữ liệu đúng, tải an toàn và có trạng thái rõ khi lỗi. Kiểm tra quyền tại backend và điều kiện hoàn thành là những yêu cầu thiết yếu ngay từ lát cắt đầu tiên; không được chuyển thành “giai đoạn bảo mật sau”. Nếu hiệu năng tạo PDF chưa rõ, nhóm có thể thử tải nhỏ và đo cơ sở, sau đó thống nhất mục tiêu; nếu cần tạo bất đồng bộ, phải làm rõ khi nào tệp sẵn sàng và cách tránh gửi nhầm. Phần quan sát lỗi, giới hạn tài nguyên và hướng xử lý sự cố nên có mức phù hợp với phạm vi mở. Nếu chưa đạt kiểm soát quyền, cần sửa hoặc hoãn phát hành tính năng đó; có thể tiếp tục thử trong môi trường phù hợp thay vì mở rộng rủi ro cho học viên.

## 18. Ghi nhớ và tự kiểm tra

**Ý chính:** Trong phát triển Agile, yêu cầu chất lượng, bảo mật và vận hành là một phần của giá trị sản phẩm, **không phải những công việc còn thừa sau khi hoàn tất tính năng**. Nhóm cần khám phá chúng cùng người có liên quan, chuyển từ khái niệm mơ hồ thành điều kiện có thể kiểm chứng, đưa vào tiêu chí chấp nhận, Definition of Done, backlog và kế hoạch phát hành. Mỗi Increment cần có phạm vi vừa đủ để giao sớm **và** có chất lượng phù hợp với phạm vi đã mở.

Tự kiểm tra:

1. Vì sao một user story “đăng ký workshop thành công” chưa đầy đủ nếu không nói rõ khi hai yêu cầu tranh chỗ cuối?
2. Hãy chuyển câu “dịch vụ phải nhanh và ổn định” thành hai yêu cầu có thể kiểm chứng, đồng thời nêu điều kiện đo.
3. Sự khác nhau giữa **tiêu chí chấp nhận**, **Definition of Done** và **điều kiện phát hành** là gì?
4. Lỗ hổng cho phép đọc dữ liệu người khác nên nằm ở đâu trong kế hoạch của một story mới?
5. Vì sao “có backup” chưa chứng minh hệ thống có thể phục hồi đúng RTO và RPO?
6. Khi nào tạo một backlog item kỹ thuật riêng, khi nào đưa yêu cầu chất lượng vào story hiện tại?
7. Tại sao kiểm thử tải với dữ liệu không đại diện có thể dẫn tới quyết định sai?
8. Scrum, Kanban và XP giúp việc thực hiện các yêu cầu này bằng những cơ chế khác nhau như thế nào?
9. Nếu một Increment đạt chức năng nhưng chưa đạt DoD, nhóm nên xử lý và báo cáo ra sao?
10. Đo lường nào giúp phân biệt “giao mã nhanh hơn” với “người dùng nhận giá trị ổn định hơn”?

Trước khi tuyên bố một lát cắt đã sẵn sàng, nhóm nên trả lời ba câu hỏi: **“Người dùng làm được gì?”, “Chúng ta có bằng chứng gì rằng việc đó đủ đúng và đủ an toàn?”, “Nếu xảy ra sự cố sau bàn giao, ai sẽ phát hiện và khôi phục bằng cách nào?”** Trả lời được cả ba là nền tảng của phát triển thích ứng có trách nhiệm.
