# Liên kết mười hai nguyên tắc với các quyết định thực tế trong nhóm

> **Chương:** Nguyên tắc Agile  
> **Học phần:** **AGILE_DEVELOPMENT** — phát triển phần mềm thích ứng bằng phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục, kết hợp user story, backlog, Scrum, Kanban, XP và các chỉ số dòng công việc khi phù hợp.

**Mười hai nguyên tắc đằng sau Tuyên ngôn Agile** không phải mười hai bước thực hiện theo thứ tự, cũng không phải danh sách mười hai nghi thức bắt buộc. Chúng là các tiêu chí giúp nhóm **ra quyết định khi điều kiện thực tế không rõ ràng**: giao gì trước, tiếp nhận thay đổi thế nào, trao đổi với ai, cần đầu tư bao nhiêu cho chất lượng, đo tiến độ bằng gì và khi nào phải cải tiến cách làm.

Ví dụ, nhóm có thể đang đối diện ba yêu cầu cùng lúc: khách hàng muốn thêm tính năng, kiểm thử phát hiện lỗi ở luồng chính và một hệ thống đối tác sắp ngừng API cũ. Không có nguyên tắc riêng lẻ nào tự động giải quyết toàn bộ tình huống. Nhóm cần kết hợp ưu tiên giá trị, phản hồi sớm, an toàn kỹ thuật, nhịp làm việc bền vững và trao quyền quyết định trong phạm vi rõ ràng.

Bài viết sử dụng **cách diễn giải tiếng Việt** nội dung của 12 nguyên tắc trong [Agile Manifesto](https://agilemanifesto.org/principles.html), kết hợp những quyết định cụ thể cho nhóm phát triển phần mềm. Các ví dụ, quy trình và chỉ số trong bài là **gợi ý thực hành**, không phải câu chữ hay quy định bắt buộc của Tuyên ngôn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích đúng ý nghĩa của cả mười hai nguyên tắc Agile, tránh nhầm chúng với các sự kiện Scrum hoặc cột bảng Kanban.
2. Với mỗi tình huống, nêu **quyết định**, **bằng chứng cần xem**, **người cần tham gia**, **hành động cụ thể** và **tín hiệu kiểm chứng**.
3. Nối các nguyên tắc với user story, Product Backlog, Scrum, Kanban, XP, tích hợp liên tục và đo lường dòng công việc.
4. Xử lý những xung đột thường gặp: yêu cầu mới với mục tiêu ngắn hạn; tốc độ giao hàng với chất lượng; trao quyền nhóm với ràng buộc tổ chức; giảm phạm vi với cam kết khách hàng.
5. Phân biệt tiến độ kỹ thuật, kết quả sản phẩm và độ ổn định vận hành để cải tiến dựa trên dữ liệu.

## 2. Nhìn tổng thể: mười hai nguyên tắc dẫn tới quyết định nào?

Bảng dưới đây giữ đúng **thứ tự mười hai nguyên tắc** trong Tuyên ngôn Agile. Các câu diễn đạt được rút gọn và diễn giải để phục vụ học tập.

| # | Ý chính của nguyên tắc | Câu hỏi quyết định trong nhóm | Ví dụ hành động |
| --- | --- | --- | --- |
| **1** | Ưu tiên cao nhất là làm khách hàng hài lòng qua giao phần mềm có giá trị **sớm và liên tục**. | Phần nhỏ nhất nào tạo giá trị có thể kiểm chứng sớm? | Giao luồng đặt lịch cơ bản trước các tính năng phụ. |
| **2** | Đón nhận yêu cầu thay đổi, kể cả muộn; sử dụng thay đổi để tạo lợi thế cho khách hàng. | Bằng chứng mới có khiến ta cần đổi thứ tự hoặc giải pháp? | Đổi backlog khi phát hiện điểm nghẽn trong hành trình người dùng. |
| **3** | Giao phần mềm chạy được thường xuyên, tính bằng vài tuần tới vài tháng và ưu tiên chu kỳ ngắn hơn. | Có thể giảm kích thước lô giao và nhận phản hồi sớm không? | Phát hành từng lát cắt đã kiểm thử thay vì chờ tất cả màn hình. |
| **4** | Người làm kinh doanh và người phát triển phối hợp hằng ngày suốt dự án. | Ai cần cùng làm rõ ưu tiên và quy tắc nghiệp vụ ngay hôm nay? | Product Owner và Developers cùng xử lý trường hợp đặt lịch trùng. |
| **5** | Xây dựng dự án quanh những cá nhân có động lực, cung cấp môi trường, hỗ trợ và tin tưởng họ hoàn thành. | Nhóm thiếu mục tiêu, năng lực, quyền quyết định hay điều kiện làm việc nào? | Làm rõ mục tiêu, tháo trở ngại và để nhóm chọn phương án kỹ thuật. |
| **6** | Trao đổi trực tiếp là cách hiệu quả để truyền đạt thông tin trong nhóm phát triển. | Vấn đề mơ hồ này nên trao đổi đồng bộ để hiểu nhanh hơn không? | Cùng người dùng xem bản mẫu, xác nhận lại bằng ví dụ và tài liệu ngắn. |
| **7** | Phần mềm hoạt động được là thước đo chính của tiến độ. | Công việc đã thật sự tạo hành vi có thể chạy và kiểm chứng chưa? | Demo đặt lịch hoàn chỉnh đi qua UI, API và lưu dữ liệu. |
| **8** | Phát triển Agile cần nhịp làm việc bền vững mà các bên có thể duy trì lâu dài. | Lựa chọn này có khiến nhóm liên tục quá tải hoặc làm giảm chất lượng? | Giảm WIP, thương lượng phạm vi và dự phòng công việc vận hành. |
| **9** | Liên tục chú trọng kỹ thuật xuất sắc và thiết kế tốt giúp tăng khả năng linh hoạt. | Cải thiện kỹ thuật nào làm thay đổi tiếp theo an toàn hơn? | Thêm kiểm thử tự động và refactor khu vực thường sửa. |
| **10** | Đơn giản là nghệ thuật tối đa hóa lượng công việc không cần làm. | Có phần nào có thể bỏ hoặc hoãn mà vẫn giải quyết vấn đề cốt lõi? | Chưa xây hệ thống cấu hình phức tạp khi chưa có nhu cầu thật. |
| **11** | Kiến trúc, yêu cầu và thiết kế tốt nhất nảy sinh từ các nhóm tự tổ chức. | Nhóm có đủ hiểu biết và quyền chủ động quyết định cách làm? | Nhóm liên chức năng cùng thiết kế giải pháp trong các ràng buộc rõ ràng. |
| **12** | Định kỳ suy ngẫm cách làm hiệu quả hơn, rồi điều chỉnh hành vi. | Hệ thống làm việc đang gây lãng phí gì và ta thử cải tiến ra sao? | Giảm thời gian chờ review, đo lại cycle time sau hai tuần. |

Một cách nhóm các nguyên tắc theo câu hỏi ra quyết định:

- **Giá trị và phản hồi:** 1, 2, 3, 7, 10.
- **Cộng tác và quyền chủ động:** 4, 5, 6, 11.
- **Khả năng làm việc bền vững:** 8, 9, 12.

Nhóm này chỉ để học cho dễ; các nguyên tắc luôn liên quan nhau. Chẳng hạn, việc giao sớm theo nguyên tắc 1 sẽ không bền nếu bỏ chất lượng kỹ thuật của nguyên tắc 9.

## 3. Nguyên tắc 1 — Giao giá trị cho khách hàng sớm và liên tục

**Ý nghĩa:** Thành công không nằm ở việc lập đủ danh sách chức năng hoặc báo cáo đã tiêu hết bao nhiêu công sức. Nhóm cần tạo phần mềm thực sự giải quyết được một nhu cầu, để khách hàng có thể dùng hoặc kiểm chứng sớm và nhận giá trị liên tục.

**Quyết định thực tế:** “Nên triển khai cả quy trình đặt lịch gồm 12 màn hình hay chọn một lát cắt đủ dùng để khách đặt được lịch đầu tiên?”

Một nhóm phát triển ứng dụng đặt lịch tư vấn có thể chọn:

1. Cho người dùng chọn **một loại dịch vụ**, xem khung giờ trống và xác nhận đặt lịch.
2. Giao luồng này với kiểm thử và xác nhận thành công rõ ràng.
3. Quan sát người dùng dùng nó ra sao trước khi đầu tư vào bộ lọc địa điểm, lịch sử hẹn và giao diện tùy biến.

Đây là **lát cắt dọc**: đi qua UI, logic nghiệp vụ và lưu trữ để hoàn thành một hành vi người dùng, thay vì chỉ hoàn thiện riêng database hay API. Không nhất thiết phải làm tính năng nhỏ nhất về số dòng mã; phải nhỏ theo **phạm vi giá trị có thể kiểm chứng**.

**Bằng chứng cần xem:** Nỗi đau của người dùng, tần suất tác vụ, rủi ro nghiệp vụ, độ sẵn sàng của phần mềm và phản hồi từ đại diện khách hàng.

**Tín hiệu kiểm chứng:** Người dùng hoàn tất tác vụ, thời gian từ ý tưởng đến lần dùng đầu, phản hồi về mức hữu ích và những vấn đề mới được phát hiện.

**Cạm bẫy:** “Giao sớm” không có nghĩa giao phần mềm lỗi hoặc phát hành cho toàn bộ người dùng khi chưa đủ an toàn. Giao có giá trị cần đi cùng chuẩn chất lượng và chiến lược phát hành phù hợp.

## 4. Nguyên tắc 2 — Đón nhận thay đổi, kể cả khi đã phát triển muộn

**Ý nghĩa:** Khi nhóm có bằng chứng mới, kế hoạch ban đầu phải có khả năng thay đổi. Nhưng thay đổi được đón nhận **vì nó có thể đem lại giá trị**, không phải vì ai có ý tưởng mới cũng được đổi ưu tiên tức thì.

**Quyết định thực tế:** “Chúng ta đã làm 70% trang tìm kiếm nâng cao, nhưng thử nghiệm cho thấy người dùng chủ yếu cần tìm nhanh theo mã đơn. Có nên đổi hướng?”

Nhóm nên:

- Làm rõ bằng chứng: số liệu sử dụng, phỏng vấn, quan sát và mức tin cậy.
- Đối chiếu với **Product Goal** và kết quả khách hàng cần.
- So sánh giá trị của phương án mới với công việc còn lại, chi phí chuyển hướng và rủi ro.
- Cập nhật Product Backlog và truyền đạt phần việc bị hoãn, thay đổi dự báo hay phụ thuộc phát sinh.
- Thử giải pháp mới trên phạm vi nhỏ khi chưa đủ chắc chắn.

Điểm đặc biệt: nếu đã đầu tư công sức lớn vào chức năng cũ, chi phí đó **không tự nó chứng minh** rằng cần làm tiếp. Quyết định nên dựa trên chi phí, lợi ích và rủi ro **từ thời điểm hiện tại trở đi**.

**Trong Scrum:** Product Backlog được làm rõ liên tục. Trong Sprint, nhóm bảo vệ **Sprint Goal** và không làm giảm chất lượng; phạm vi có thể được làm rõ, thương lượng với Product Owner khi học thêm. Trường hợp Sprint Goal trở nên lỗi thời, chỉ Product Owner có thẩm quyền hủy Sprint theo Scrum Guide.

**Tín hiệu kiểm chứng:** Quyết định đổi hướng có lý do được ghi lại; sau thay đổi, kết quả người dùng hoặc rủi ro có cải thiện không?

**Cạm bẫy:** Dùng câu “Agile phải chấp nhận thay đổi” để liên tục xen việc khẩn cấp giả, phá WIP và khiến nhóm không hoàn tất bất kỳ lát cắt nào.

## 5. Nguyên tắc 3 — Giao phần mềm hoạt động được với nhịp thường xuyên

**Ý nghĩa:** Giao phần mềm trong các khoảng thời gian ngắn, thường từ **vài tuần đến vài tháng**, ưu tiên chu kỳ ngắn để thu nhận phản hồi. Nhịp giao giúp phát hiện các giả định sai, lỗi tích hợp và sai lệch ưu tiên sớm hơn.

**Quyết định thực tế:** “Có nên chờ cả hệ thống đặt lịch đủ tính năng trong bốn tháng, hay tích hợp và giao các lát cắt theo từng vòng ngắn?”

Ví dụ kế hoạch tăng dần:

| Lần giao | Khả năng người dùng kiểm chứng được | Bằng chứng thu được |
| --- | --- | --- |
| **1** | Xem giờ trống và đặt một loại lịch. | Người dùng có hoàn tất luồng cơ bản không? |
| **2** | Nhận xác nhận, xem lại lịch đã đặt. | Người dùng có tin là lịch đã được ghi nhận không? |
| **3** | Hủy và đổi lịch theo chính sách. | Có giảm yêu cầu hỗ trợ thủ công không? |
| **4** | Chọn nhiều loại tư vấn và địa điểm. | Những lựa chọn mở rộng có thật sự được dùng không? |

**Không nhầm lẫn:** Tích hợp được một thay đổi, tạo **Increment** đạt Definition of Done, triển khai lên môi trường chạy và **phát hành tới người dùng** là những khái niệm liên quan nhưng khác nhau. Trong Scrum, Increment phải đạt DoD để coi là Done; không có quy tắc bắt buộc chỉ được phát hành cuối Sprint. Nhóm có thể giao bản thử nghiệm trong môi trường kiểm soát và quyết định phát hành theo rủi ro.

**Thực hành giúp giao ngắn:** Chia user story theo hành vi, giảm kích thước lô, tích hợp liên tục, kiểm thử tự động, dùng feature flag khi thích hợp, xử lý phụ thuộc sớm và giữ backlog gần đủ rõ.

**Tín hiệu kiểm chứng:** Tần suất giao phần mềm có thể dùng, thời gian từ thay đổi đến phản hồi, cycle time, số lỗi tích hợp phát hiện muộn.

**Cạm bẫy:** Đếm số lần triển khai hoặc số bản build mà bỏ qua câu hỏi “người dùng đã nhận được giá trị gì?”.

## 6. Nguyên tắc 4 — Người làm kinh doanh và phát triển phối hợp hằng ngày

**Ý nghĩa:** Quyết định nghiệp vụ và quyết định kỹ thuật liên quan chặt chẽ. Trao đổi thường xuyên làm giảm suy đoán, vòng phê duyệt dài và tình trạng “ném tài liệu qua hàng rào”.

**Quyết định thực tế:** “Một story ghi rằng người dùng có thể đổi giờ hẹn, nhưng không nói thời điểm cuối cùng được đổi. Ai sẽ quyết định điều kiện đó?”

Nhóm nên mời người nắm quy tắc kinh doanh và những người triển khai/kiểm thử cùng làm rõ:

1. Có cho đổi trước giờ hẹn một tiếng không?
2. Đổi lịch có phát sinh phí hoặc thông báo không?
3. Nếu người dùng đổi trong lúc giờ mới được đặt bởi người khác, hệ thống xử lý thế nào?
4. Quy tắc nào bắt buộc vì hợp đồng hoặc pháp lý?

Sau cuộc trao đổi, nhóm cập nhật user story, ví dụ và tiêu chí chấp nhận. Không nhất thiết phải tạo một cuộc họp chính thức mới mỗi ngày; nguyên tắc muốn **đường trao đổi thường xuyên, dễ tiếp cận**.

**Trong Scrum:** Product Owner có trách nhiệm về giá trị và backlog, Developers tạo Increment; cả hai cần phối hợp trực tiếp, cùng các chuyên gia nghiệp vụ khi cần. Trong tổ chức không dùng Scrum, trách nhiệm có thể mang tên khác nhưng nhu cầu cộng tác vẫn vậy.

**Tín hiệu kiểm chứng:** Ít yêu cầu phải làm lại vì hiểu sai nghiệp vụ; thời gian chờ câu trả lời giảm; tiêu chí chấp nhận rõ và phản hồi tới đúng người.

**Cạm bẫy:** Hiểu “business và development làm việc hằng ngày” thành việc tất cả thành viên phải tham dự mọi cuộc họp, làm tăng gián đoạn hơn là tăng hiểu biết.

## 7. Nguyên tắc 5 — Trao môi trường, hỗ trợ và niềm tin cho người có động lực

**Ý nghĩa:** Nhóm có động lực cần được biết **vì sao** công việc quan trọng, có phương tiện và điều kiện để làm tốt, được tin tưởng đưa ra quyết định trong phạm vi năng lực. Chỉ giao KPI rồi kiểm soát từng giờ không tạo nên sự chủ động.

**Quyết định thực tế:** “Một nhiệm vụ kéo dài vì nhóm thiếu quyền truy cập môi trường kiểm thử. Quản lý nên thêm báo cáo tiến độ hằng ngày hay tháo trở ngại?”

Hành động phù hợp là làm rõ mục tiêu, cấp quyền theo chính sách, hỗ trợ chuyên môn và trao quyền xử lý trong những giới hạn minh bạch. Nhóm kỹ thuật có thể đề xuất cách tích hợp và kiểm thử; người chịu trách nhiệm sản phẩm cùng xác định mức giá trị và thứ tự ưu tiên.

**Các điều kiện tạo niềm tin:**

- Mục tiêu, ưu tiên và ranh giới quyết định rõ ràng.
- Đủ công cụ, dữ liệu thử, môi trường và kỹ năng cần thiết.
- Phản hồi an toàn, không đổ lỗi khi phát hiện vấn đề.
- Quyền đề xuất cải tiến kỹ thuật và cách phối hợp.
- Trách nhiệm cùng nhìn thấy kết quả, không chỉ giao đầu việc cá nhân.

**Tín hiệu kiểm chứng:** Trở ngại được giải quyết nhanh hơn; các quyết định được đưa ra tại nơi có thông tin; nhóm có thể giải thích kết quả và tự điều chỉnh công việc.

**Cạm bẫy:** “Tin tưởng” không có nghĩa bỏ mục tiêu, trách nhiệm giải trình hoặc tiêu chuẩn bảo mật. Quyền chủ động hiệu quả cần mục tiêu chung và ranh giới rõ.

## 8. Nguyên tắc 6 — Ưu tiên trao đổi trực tiếp để hiểu nhau nhanh

**Ý nghĩa:** Tuyên ngôn nhấn mạnh **hội thoại mặt đối mặt** là cách truyền đạt thông tin hiệu quả trong nhóm phát triển. Bản chất của nguyên tắc là rút ngắn đường truyền đạt và xử lý hiểu lầm, đặc biệt khi vấn đề mơ hồ, nhiều sắc thái hoặc cần ra quyết định.

**Quyết định thực tế:** “Sau mười bình luận trên một ticket, nhóm vẫn hiểu khác nhau về ‘người dùng đã xác nhận’. Có nên tiếp tục nhắn qua lại?”

Nhóm có thể mở một cuộc trao đổi ngắn giữa người hiểu nghiệp vụ, lập trình viên và người kiểm thử, cùng chỉ vào bản mẫu hoặc ví dụ cụ thể. Sau đó ghi lại **kết luận có thể kiểm chứng** trong tiêu chí chấp nhận hoặc sơ đồ hành vi để tránh mất ngữ cảnh.

Trong đội ngũ phân tán, cuộc gọi có video, chia sẻ màn hình hoặc lập trình đôi từ xa có thể đáp ứng mục đích tương tác trực tiếp. Những câu hỏi đơn giản hoặc quyết định không khẩn cấp vẫn có thể xử lý không đồng bộ để giữ thời gian tập trung. Không nên ép tất cả mọi người bật video cả ngày hoặc loại bỏ tài liệu vì câu chữ trong Tuyên ngôn.

**Tín hiệu kiểm chứng:** Giảm vòng hỏi đáp kéo dài, quyết định quan trọng được hiểu thống nhất và số lỗi vì diễn giải khác nhau giảm.

**Cạm bẫy:** Coi một cuộc họp là đủ dù kết luận không được lưu lại, khiến người vắng mặt và người bảo trì sau này không biết vì sao quyết định được đưa ra.

## 9. Nguyên tắc 7 — Phần mềm chạy được là thước đo chính của tiến độ

**Ý nghĩa:** Báo cáo đã thiết kế xong, viết 90% mã hoặc hoàn thành 50 story point có thể hữu ích để nhìn hoạt động, nhưng chưa chứng minh sản phẩm tiến gần hơn tới chỗ sử dụng được. Thước đo chính về **tiến độ phát triển** là phần mềm thực sự hoạt động.

**Quyết định thực tế:** “Trong Sprint Review, nhóm nên báo cáo 30 ticket đã đóng hay trình diễn người dùng đặt lịch thành công trong một luồng hoàn chỉnh?”

Một Increment được kiểm chứng cần có:

- Hành vi từ góc nhìn người dùng có thể chạy và kiểm tra.
- Chức năng được tích hợp với các thành phần cần thiết.
- Điều kiện chấp nhận và chuẩn chất lượng liên quan đã được đáp ứng.
- Các giới hạn, rủi ro còn lại được nói rõ để không hiểu nhầm phần đã giao.

**Phân biệt tiến độ và thành công:** Phần mềm hoạt động được cho thấy công việc đã biến thành khả năng dùng được; muốn biết khả năng ấy **có tạo giá trị không**, nhóm còn phải đo kết quả sản phẩm như tỷ lệ hoàn tất tác vụ, mức sử dụng và phản hồi người dùng. Phần mềm chạy tốt nhưng không giải quyết nhu cầu vẫn chưa phải thành công về sản phẩm.

**Tín hiệu kiểm chứng:** Increment dùng được, hành vi chạy xuyên suốt, số lỗi nghiêm trọng, số việc thật sự Done theo định nghĩa thống nhất.

**Cạm bẫy:** Demo màn hình giả lập hoặc chỉ trình bày code khi chức năng chưa tích hợp mà gọi đó là phần mềm đã hoàn tất.

## 10. Nguyên tắc 8 — Giữ nhịp phát triển bền vững

**Ý nghĩa:** Người đầu tư, người phát triển và người sử dụng cần có thể duy trì nhịp làm việc ổn định trong thời gian dài. Làm thêm giờ liên tục để đạt một mốc thường tạo lỗi, kiệt sức, nợ kỹ thuật và giảm khả năng dự báo ở các vòng sau.

**Quyết định thực tế:** “Nhóm liên tục nhận thêm lỗi production và yêu cầu mới, nhưng ngày cam kết không đổi. Có nên yêu cầu tất cả làm thêm cuối tuần để giữ toàn bộ phạm vi?”

Các bước có trách nhiệm hơn:

1. Làm hiện rõ công việc đang làm, phần hỗ trợ vận hành và giới hạn năng lực.
2. Ưu tiên sự cố thật sự cấp bách và bảo vệ dữ liệu, dịch vụ.
3. Đánh giá lại phạm vi, thứ tự backlog, WIP và các phụ thuộc.
4. Thương lượng thời điểm, phạm vi hoặc bổ sung năng lực nếu thực tế cho phép.
5. Giảm việc bị chặn và cải thiện tự động hóa ở những điểm lặp lại.

**Kanban** có thể giới hạn WIP để giảm đa nhiệm; **Scrum** tạo nhịp mục tiêu để nhóm không liên tục tản mạn; **XP** nhấn mạnh nhịp làm việc có thể duy trì. Cách làm cụ thể phụ thuộc loại sản phẩm, nhưng không framework nào biến làm thêm giờ kéo dài thành giải pháp mặc định.

**Tín hiệu kiểm chứng:** Cycle time không tăng bất thường, số lỗi và yêu cầu khẩn cấp không tích tụ, nhịp giao tương đối ổn định và nhóm vẫn có thời gian cải tiến.

**Cạm bẫy:** Hiểu “bền vững” thành không được nỗ lực xử lý sự cố cấp bách. Sự cố có thể cần ứng cứu bất thường; sau đó cần phục hồi năng lực và học cách giảm tái diễn.

## 11. Nguyên tắc 9 — Chất lượng kỹ thuật và thiết kế tốt nâng khả năng thích ứng

**Ý nghĩa:** Muốn đón nhận thay đổi mà không làm hỏng hệ thống, nhóm phải duy trì nền tảng kỹ thuật đủ tốt. Kiểm thử, thiết kế, tích hợp và quan sát hệ thống là khoản đầu tư cho những quyết định tương lai.

**Quyết định thực tế:** “Mỗi lần đổi quy tắc đặt lịch đều làm lỗi chức năng hủy lịch. Có nên chỉ tăng số người sửa lỗi hay cải tiến cấu trúc và kiểm thử?”

Nhóm có thể:

- Viết kiểm thử cho các quy tắc quan trọng: không tạo lịch trùng, hủy đúng quyền, giữ dữ liệu nhất quán.
- Tích hợp thay đổi thường xuyên bằng CI để phát hiện lỗi hồi quy sớm.
- Refactor logic có trách nhiệm và phân tách quy tắc dễ thay đổi.
- Dùng review, pair programming hoặc các buổi thiết kế ngắn để chia sẻ tri thức.
- Bổ sung quan sát kỹ thuật và phương án hồi phục cho thay đổi có rủi ro vận hành.

Các thực hành này liên hệ với **Extreme Programming (XP)** như TDD, continuous integration, refactoring, thiết kế đơn giản và lập trình đôi. XP là tập hợp thực hành hỗ trợ nguyên tắc, không phải phần được Tuyên ngôn bắt buộc tất cả nhóm áp dụng nguyên xi.

**Tín hiệu kiểm chứng:** Giảm lỗi hồi quy; thay đổi nghiệp vụ mất ít thời gian và ít rủi ro hơn; đội ngũ có thể phát hành thay đổi nhỏ đều đặn.

**Cạm bẫy:** Nhầm “thiết kế tốt” với xây trước kiến trúc phức tạp cho mọi nhu cầu tương lai. Thiết kế cần tương xứng với vấn đề hiện tại và vẫn mở đường cải tiến.

## 12. Nguyên tắc 10 — Đơn giản bằng cách tối đa hóa công việc không cần làm

**Ý nghĩa:** Đơn giản không chỉ là giao diện ít nút hoặc mã ngắn. Cốt lõi là **không đầu tư vào những việc chưa cần thiết** để giải quyết vấn đề và giữ khả năng thay đổi.

**Quyết định thực tế:** “Có cần xây bộ máy quy tắc cấu hình riêng cho 50 loại lịch, khi hiện tại sản phẩm chỉ hỗ trợ một loại dịch vụ và chưa có bằng chứng mở rộng?”

Nhóm có thể quyết định dùng cấu trúc đơn giản cho nhu cầu hiện tại, đồng thời không khóa cứng dữ liệu theo cách làm những thay đổi đã biết trở nên rủi ro. Nếu nhu cầu đa loại lịch được xác nhận, nhóm sẽ mở rộng trên cơ sở kiểm thử và thực tế vận hành.

**Một phép thử trước khi thêm backlog item:**

1. Vấn đề nào sẽ không được giải quyết nếu bỏ mục này?
2. Bằng chứng về giá trị hoặc rủi ro là gì?
3. Có phương án nào nhỏ hơn hoặc dùng quy trình hiện tại không?
4. Việc này có cần để đạt chuẩn chất lượng, bảo mật hoặc nghĩa vụ bắt buộc không?
5. Hoãn việc này có làm phát sinh chi phí đáng kể sau đó không?

**Ví dụ đơn giản có chủ đích:** Thay vì viết ngay hệ thống thông báo đa kênh và tùy biến theo hàng chục quy tắc, nhóm có thể bắt đầu với xác nhận trên màn hình và email cơ bản nếu đủ đáp ứng nhu cầu, sau đó mở rộng theo bằng chứng. Dù phạm vi nhỏ, việc bảo vệ dữ liệu cá nhân và xử lý gửi trùng vẫn phải được xem xét.

**Tín hiệu kiểm chứng:** Ít tính năng không dùng tới, backlog gọn hơn, nhanh đạt kết quả ưu tiên mà không tăng nợ kỹ thuật đáng kể.

**Cạm bẫy:** Dùng “đơn giản” làm lý do bỏ kiểm thử, quan sát hệ thống, khả năng tiếp cận hoặc biện pháp an toàn bắt buộc. Đó là chuyển chi phí sang tương lai, không phải loại bỏ việc vô ích.

## 13. Nguyên tắc 11 — Giải pháp tốt nảy sinh từ nhóm tự tổ chức

**Ý nghĩa:** Người trực tiếp hiểu người dùng, mã, dữ liệu và ràng buộc cần có cơ hội cùng quyết định phương án. Nhóm tự tổ chức phối hợp cách làm, không chỉ nhận một danh sách việc đã chia cứng từng người. Trong Scrum hiện đại, thuật ngữ **self-managing** nhấn mạnh nhóm tự quản lý ai làm gì, khi nào và như thế nào.

**Quyết định thực tế:** “Để giảm độ trễ của API đặt lịch, quản lý phải chỉ định từng người sửa từng hàm hay để nhóm liên chức năng phân tích đường đi và đề xuất phương án?”

Nhóm có thể họp thiết kế ngắn, đo độ trễ, xem các phương án và xác định một thí nghiệm có thể đảo ngược. Những người triển khai, kiểm thử, vận hành và người nắm nghiệp vụ cùng đóng góp, trong khi quyền quyết định và ràng buộc kiến trúc được nêu rõ.

**Tự tổ chức không đồng nghĩa thiếu định hướng:**

- Product Owner hoặc người chịu trách nhiệm sản phẩm làm rõ vấn đề và thứ tự giá trị.
- Nhóm kỹ thuật chọn cách thực hiện trong khung chất lượng, bảo mật và kiến trúc phù hợp.
- Chuyên gia bảo mật, pháp lý hoặc vận hành tham gia các quyết định có tác động thuộc phạm vi của họ.
- Nhóm minh bạch kết quả, rủi ro, giả định và lý do lựa chọn.

Một nhóm có thể chọn chuyên gia kiến trúc dẫn dắt một quyết định; nguyên tắc không cấm vai trò chuyên môn hoặc tiêu chuẩn kỹ thuật cấp tổ chức. Điều quan trọng là **khả năng học hỏi và đóng góp quyết định thực chất** không bị thay thế bằng kiểm soát vi mô.

**Tín hiệu kiểm chứng:** Ít nút thắt phê duyệt không cần thiết, chất lượng quyết định tăng, thông tin được chia sẻ và nhóm có trách nhiệm với kết quả chung.

**Cạm bẫy:** Gọi là “tự tổ chức” nhưng không trao quyền, mục tiêu, nguồn lực hoặc quyền truy cập cần thiết; hoặc ngược lại, không làm rõ ai chịu trách nhiệm quyết định có tác động lớn.

## 14. Nguyên tắc 12 — Thường xuyên suy ngẫm và điều chỉnh cách làm

**Ý nghĩa:** Agile không chỉ cải thiện **sản phẩm** mà còn cải thiện **hệ thống tạo ra sản phẩm**. Tại các thời điểm phù hợp, nhóm cần nhìn lại cách phối hợp và thử thay đổi hành vi cụ thể, rồi kiểm tra tác dụng.

**Quyết định thực tế:** “Dữ liệu cho thấy các user story mất trung bình hai ngày để phát triển nhưng thêm năm ngày chờ review. Nhóm cần làm gì ở vòng tiếp theo?”

Thay vì yêu cầu lập trình viên viết mã nhanh hơn, nhóm có thể:

1. Xem dữ liệu dòng công việc và hỏi vì sao review là điểm nghẽn.
2. Thỏa thuận giới hạn WIP và ưu tiên hỗ trợ những mục đang chờ review.
3. Đặt một thử nghiệm nhỏ trong hai tuần, ví dụ khung review chung hằng ngày và story nhỏ hơn.
4. Đo lại **cycle time**, thời gian chờ review, số việc bị chặn và chất lượng.
5. Giữ, điều chỉnh hoặc bỏ thực hành mới tùy kết quả.

**Trong Scrum**, Sprint Retrospective là một sự kiện dành cho cải tiến chất lượng và hiệu quả. **Trong Kanban**, nhóm có thể tổ chức các vòng phản hồi định kỳ và điều chỉnh chính sách dòng công việc. Ngoài ra, postmortem sau sự cố có thể tạo đầu vào cải tiến vận hành.

**Tín hiệu kiểm chứng:** Có ít nhất một hành động cải tiến được thực hiện và xem lại; trở ngại hoặc thời gian chờ có thay đổi; chất lượng không suy giảm.

**Cạm bẫy:** Kết thúc mỗi retrospective bằng danh sách 20 ý tưởng nhưng không người phụ trách, không thời điểm kiểm tra và không thay đổi hành vi thực tế.

## 15. Khi các nguyên tắc có vẻ xung đột: cách ra quyết định

Các nguyên tắc là những định hướng cần cân bằng. Chúng không loại bỏ sự đánh đổi và cũng không đưa ra công thức tối ưu duy nhất.

| Tình huống | Những nguyên tắc liên quan | Quyết định hợp lý cần cân nhắc |
| --- | --- | --- |
| Khách hàng đòi thêm tính năng đúng lúc Sprint đang xử lý luồng chính. | **1, 2, 7, 8, 10** | Xác minh giá trị, xem ảnh hưởng Sprint Goal và WIP, thương lượng ưu tiên; không tự động ngắt mọi việc. |
| Muốn giao sớm nhưng kiểm thử tự động chưa đủ. | **1, 3, 7, 9** | Giảm phạm vi lát cắt, xây kiểm thử thiết yếu, thử triển khai giới hạn; không hạ chuẩn chất lượng. |
| Đã lên roadmap chi tiết nhưng người dùng thay đổi hành vi. | **1, 2, 3, 10** | Kiểm chứng dữ liệu, cập nhật giả định và thứ tự backlog, thông báo hệ quả kế hoạch. |
| Nhóm phân tán trao đổi không đồng bộ kéo dài. | **4, 5, 6, 11** | Tổ chức cuộc trao đổi đồng bộ ngắn khi cần, lưu quyết định bằng tiêu chí chấp nhận dễ tìm. |
| Nhóm muốn tự chọn kiến trúc nhưng hệ thống có quy định an toàn bắt buộc. | **5, 9, 11** | Đặt ranh giới bảo mật và trách nhiệm rõ, cho nhóm chủ động thiết kế bên trong ranh giới. |
| Số lỗi production và việc hỗ trợ tăng, nhóm bắt đầu kiệt sức. | **3, 8, 9, 12** | Điều chỉnh phạm vi, dành năng lực xử lý độ tin cậy, giảm WIP và phân tích nguyên nhân lặp lại. |
| Một hạng mục đã đầu tư nhiều nhưng chưa có bằng chứng giá trị. | **1, 2, 7, 10** | Đánh giá giá trị tương lai và chi phí còn lại; cân nhắc thử nhỏ, hoãn hoặc dừng. |

### Quy trình nhanh cho một quyết định khó

~~~mermaid
flowchart TD
    A["Nêu quyết định đang gặp"] --> B["Làm rõ mục tiêu, người dùng, ràng buộc"]
    B --> C["Thu thập bằng chứng và giả định"]
    C --> D["Xác định nguyên tắc liên quan"]
    D --> E["Đề xuất 2–3 phương án khả thi"]
    E --> F["So giá trị, rủi ro, WIP, chất lượng"]
    F --> G["Chọn phương án, nêu trách nhiệm và tác động"]
    G --> H["Giao lát cắt nhỏ và đo tín hiệu"]
    H --> I["Xem lại kết quả và điều chỉnh"]
    I --> C
~~~

Mục đích của việc “xác định nguyên tắc liên quan” là làm rõ lý do quyết định, không phải bỏ phiếu xem nguyên tắc nào thắng. Một yêu cầu pháp lý bắt buộc, ví dụ, vẫn cần được tuân thủ dù phương án đó ít tạo lợi ích sản phẩm trực tiếp.

## 16. Ví dụ xuyên suốt: nhóm xây hệ thống đặt lịch tư vấn

Để thấy mười hai nguyên tắc phối hợp, giả sử một nhóm liên chức năng gồm người hiểu sản phẩm, lập trình viên, kiểm thử và vận hành đang tạo một dịch vụ đặt lịch tư vấn qua web. Tình huống và các con số dưới đây chỉ là **giả định để học**, không phải dữ liệu từ một dự án thật.

### 16.1. Tuần đầu: xác định vấn đề, không bắt đầu từ 40 chức năng

Nhóm nhận danh sách mong muốn gồm tìm kiếm địa điểm, thông báo SMS, thanh toán, lịch sử, đánh giá và tính năng đặt lịch. Qua trao đổi, họ xác định vấn đề đầu tiên là **khách không đặt được khung giờ phù hợp mà không gọi tổng đài**.

**Quyết định:** Chọn Product Goal “khách đặt lịch trực tuyến thuận tiện và tin cậy”; làm lát cắt đầu tiên gồm xem giờ trống, điền thông tin bắt buộc và xác nhận. Product Owner và Developers trao đổi quy tắc khung giờ; nhóm tự tổ chức cách chia việc; chưa triển khai những tùy chọn chưa có bằng chứng.

Liên hệ: **1** (giao giá trị sớm), **4** (cộng tác), **10** (loại việc không cần thiết), **11** (nhóm chủ động thiết kế).

### 16.2. Vòng giao đầu: phần mềm chạy được tạo thông tin mới

Nhóm chia user story thành lát cắt dọc, viết tiêu chí chấp nhận và kiểm thử trường hợp đặt thành công, khung giờ hết chỗ, mạng chậm. Họ tích hợp thường xuyên và cho một nhóm người dùng kiểm chứng luồng từ giao diện đến lưu dữ liệu.

**Quyết định:** Trình diễn Increment thực sự chạy; thu thập lỗi và phản hồi trước khi mở rộng nhiều loại lịch.

Liên hệ: **3** (giao thường xuyên), **7** (phần mềm hoạt động được là tiến độ), **9** (kỹ thuật xuất sắc).

### 16.3. Phản hồi khiến thứ tự backlog đổi

Người dùng thử nghiệm cho biết nút xác nhận khó nhận ra, còn nhật ký cho thấy một số yêu cầu gửi lặp. Một số bên liên quan vẫn muốn ưu tiên SMS và bộ lọc địa điểm như kế hoạch ban đầu.

**Quyết định:** Nhóm ưu tiên làm rõ trạng thái xác nhận và bảo vệ chống lịch trùng; cập nhật backlog công khai, giải thích các mục bị hoãn. Nếu đang trong Sprint, họ xem xét liên hệ của thay đổi với Sprint Goal và chất lượng, rồi thương lượng phạm vi với Product Owner nếu cần.

Liên hệ: **2** (đón nhận thay đổi), **1** (giá trị khách hàng), **7** (hành vi chạy được), **10** (không làm việc ít giá trị trước).

### 16.4. Áp lực giao hàng khiến nhóm xem lại cách làm

Sau vài vòng, thời gian review code tăng, lỗi production xen ngang công việc và một thành viên phải hỗ trợ ngoài giờ thường xuyên. Nhóm nhìn bảng Kanban và thấy nhiều việc bắt đầu nhưng chưa hoàn tất.

**Quyết định:** Giảm giới hạn WIP, ưu tiên xử lý các mục đang bị chặn, cải tiến kiểm thử hồi quy và lịch phối hợp xử lý sự cố. Trong retrospective hoặc vòng cải tiến dòng, nhóm chọn một thử nghiệm cụ thể và đo lại sau hai tuần.

Liên hệ: **5** (môi trường và hỗ trợ), **8** (bền vững), **9** (chất lượng kỹ thuật), **12** (điều chỉnh cách làm).

### 16.5. Đo kết quả để biết đã thực sự tiến bộ chưa

Giả sử tỷ lệ hoàn tất đặt lịch quan sát được thay đổi theo minh họa:

| Giai đoạn | Tỷ lệ hoàn tất | Tỷ lệ lỗi tạo lịch |
| --- | ---: | ---: |
| Bản đầu | 43% | 2,2% |
| Sau cải tiến xác nhận | 51% | 1,5% |

Nhóm chưa vội kết luận thay đổi giao diện là nguyên nhân vì nguồn người dùng và thời gian đo có thể khác nhau. Họ kiểm tra định nghĩa lượt bắt đầu hợp lệ, phân đoạn dữ liệu, phản hồi định tính và cân nhắc thử nghiệm đối chứng nếu cần suy luận nhân quả. Đồng thời, họ theo dõi lỗi và độ tin cậy để không tối ưu chuyển đổi bằng cách chấp nhận lịch trùng.

Liên hệ: **1** (giá trị), **2** (học và đổi), **7** (tiến độ hoạt động), **9** (chất lượng) và **12** (cải tiến dựa trên thực tế).

### 16.6. Bảng liên kết 12 nguyên tắc với quyết định của tình huống

| Nguyên tắc | Quyết định quan sát được |
| --- | --- |
| 1 | Ưu tiên luồng đặt lịch dùng được trước các chức năng phụ. |
| 2 | Đổi backlog khi có bằng chứng mới về bước xác nhận. |
| 3 | Giao từng lát cắt để nhận phản hồi thay vì chờ dự án hoàn tất. |
| 4 | Người nắm nghiệp vụ cùng người triển khai làm rõ điều kiện đặt lịch. |
| 5 | Cấp hỗ trợ, quyền chủ động và loại bỏ trở ngại cho nhóm. |
| 6 | Trao đổi trực tiếp khi quy tắc giờ trống gây hiểu lầm; lưu kết luận. |
| 7 | Kiểm chứng hành vi chạy xuyên qua toàn bộ luồng đặt lịch. |
| 8 | Điều chỉnh WIP và năng lực hỗ trợ thay vì kéo dài làm thêm giờ. |
| 9 | Xây kiểm thử chống lịch trùng, tích hợp và quan sát hệ thống. |
| 10 | Hoãn SMS và bộ lọc khi chưa có bằng chứng ưu tiên. |
| 11 | Nhóm liên chức năng chọn thiết kế trong ranh giới sản phẩm và an toàn. |
| 12 | Thử cải thiện quy trình review và đo kết quả sau một khoảng thời gian. |

## 17. Từ nguyên tắc tới thực hành Scrum, Kanban, XP và đo lường

Tuyên ngôn Agile có trước và **không đồng nhất** với một framework. Scrum, Kanban và XP có thể hỗ trợ hiện thực hóa các nguyên tắc theo nhu cầu, nhưng không có quy tắc “mỗi nguyên tắc tương ứng đúng một nghi thức”.

| Nhu cầu ra quyết định | Thực hành có thể dùng | Nguyên tắc được hỗ trợ |
| --- | --- | --- |
| Làm rõ nhu cầu theo góc nhìn người dùng. | User story, ví dụ chấp nhận, discovery, Product Backlog refinement. | 1, 2, 4, 6, 10. |
| Tập trung một mục tiêu ngắn hạn và xem phản hồi. | Scrum: Sprint Goal, Sprint Planning, Sprint Review. | 1, 2, 3, 4, 7. |
| Cải tiến hệ thống làm việc. | Scrum Retrospective hoặc vòng phản hồi Kanban. | 5, 8, 11, 12. |
| Nhìn thấy và giảm tắc nghẽn dòng công việc. | Kanban: workflow, WIP limit, pull, cycle time, throughput. | 3, 8, 10, 12. |
| Dễ thay đổi mà ít lỗi hồi quy. | XP: TDD, CI, refactoring, pair programming, thiết kế đơn giản. | 3, 7, 9, 10, 11. |
| Kiểm tra giá trị và chất lượng sau phát hành. | Chỉ số outcome, telemetry, phản hồi hỗ trợ, SLI/SLO, quan sát lỗi. | 1, 2, 7, 8, 9, 12. |

### 17.1. Đừng thay thế kết quả bằng số đầu việc

Một số chỉ số có vai trò khác nhau:

- **Outcome metric:** Tỷ lệ hoàn tất tác vụ, tỷ lệ giữ chân, thời gian giải quyết vấn đề. Giúp hiểu **giá trị sản phẩm**, cần kết hợp ngữ cảnh và kiểm tra chất lượng dữ liệu.
- **Cycle time:** Thời gian một mục từ lúc bắt đầu xử lý đến lúc hoàn tất theo định nghĩa của nhóm. Giúp thấy **dòng công việc**.
- **Throughput:** Số mục hoàn tất trong một khoảng thời gian. Giúp dự báo dòng khi cách chia việc tương đối nhất quán.
- **WIP:** Số việc đã bắt đầu nhưng chưa hoàn tất. Giúp nhìn nguy cơ đa nhiệm và hàng đợi.
- **Change failure / độ ổn định:** Lỗi hoặc sự cố sau thay đổi; cùng thời gian phục hồi và dữ liệu chất lượng dịch vụ cho thấy **rủi ro của việc giao thay đổi**.

Không dùng **story point**, **velocity** hoặc số lần triển khai làm công thức xếp hạng năng suất giữa người và giữa nhóm. Các con số này có thể bị méo khi mục tiêu đo lường biến thành mục tiêu thi đua. Nhóm cần hỏi “chỉ số này giúp quyết định việc gì?” và “có thể gây hành vi sai lệch nào?”.

### 17.2. Kết hợp các vòng phản hồi theo thời gian

~~~text
Mỗi thay đổi mã      -> kiểm thử tự động, CI, review, quan sát lỗi sớm.
Mỗi lát cắt sản phẩm -> dùng thử, tiêu chí chấp nhận, demo Increment.
Mỗi vòng ưu tiên     -> Product Backlog, Sprint Review / xem lại dòng công việc.
Sau phát hành        -> outcome, độ ổn định, hỗ trợ khách hàng, giả thuyết mới.
Định kỳ              -> retrospective, cải tiến kỹ thuật và chính sách phối hợp.
~~~

Nhịp trên là gợi ý, không phải lịch cứng từ Tuyên ngôn. Vấn đề quan trọng là **thông tin đi được từ nơi phát hiện tới nơi có thể đưa ra quyết định**.

## 18. Mẫu quyết định ngắn để dùng trong nhóm

Khi có một yêu cầu quan trọng hoặc một xung đột ưu tiên, ghi lại:

~~~text
Vấn đề / tín hiệu        : Người dùng không thấy xác nhận đặt lịch.
Mục tiêu liên quan      : Hoàn tất lịch hẹn hợp lệ và tin cậy.
Bằng chứng              : Quan sát tác vụ, log thao tác, phản hồi hỗ trợ.
Giả định chưa rõ        : Đổi trạng thái nút có cải thiện kết quả hay không.
Các phương án           : Giữ nguyên / thử UI mới / thay cả luồng.
Nguyên tắc liên quan    : 1, 2, 3, 7, 9, 10.
Rủi ro và ràng buộc     : Lịch trùng, khả năng tiếp cận, độ trễ, quyền riêng tư.
Quyết định và người quyết: Thử UI mới phạm vi nhỏ, Product Owner và nhóm thống nhất.
Việc phải hoãn          : Bộ lọc địa điểm.
Tín hiệu kiểm chứng     : Tỷ lệ hoàn tất + tỷ lệ lỗi đặt lịch.
Thời điểm xem lại       : Sau đủ lượt sử dụng và dữ liệu đáng tin.
~~~

Không cần lập biểu mẫu như trên cho mọi thay đổi nhỏ. Nó hữu ích khi quyết định có nhiều người liên quan, cần giải thích lý do hoặc có rủi ro việc cũ bị gián đoạn. Hãy giữ tài liệu ngắn và cập nhật thông tin quan trọng.

## 19. Bài tập thực hành

### Tình huống A — Khách hàng yêu cầu thay đổi vào phút cuối

Một nhóm đang chuẩn bị giao một lát cắt quản lý đơn hàng. Ba ngày trước mốc phát hành, khách hàng yêu cầu thêm bộ lọc nâng cao. Cùng lúc, kiểm thử cho thấy có thể tạo đơn hàng trùng khi người dùng bấm nút nhiều lần.

**Câu hỏi:**

1. Những nguyên tắc nào giúp quyết định phải làm gì trước?
2. Cần hỏi khách hàng điều gì để hiểu giá trị của bộ lọc?
3. Việc sửa đơn trùng liên quan thế nào tới phần mềm hoạt động được và kỹ thuật xuất sắc?
4. Nếu ngày phát hành cố định, có những lựa chọn phạm vi nào thay vì bỏ kiểm thử?

**Hướng giải tham khảo:** Nguyên tắc **1, 7, 9** nhấn mạnh giao khả năng cốt lõi tin cậy; **2** giúp tiếp nhận yêu cầu mới có trách nhiệm; **10** giúp hoãn việc chưa cần; **4 và 6** khuyến khích nói rõ ưu tiên với khách hàng và nhóm. Cần sửa nguy cơ đơn trùng trước khi phát hành rộng. Với bộ lọc, nhóm xem bằng chứng nhu cầu, chi phí trì hoãn và có thể đưa vào backlog cho vòng sau. Nếu bắt buộc bàn giao trước ngày cụ thể, cần thương lượng phạm vi minh bạch và giữ chuẩn chất lượng.

### Tình huống B — Công việc đứng ở cột review

Nhóm Kanban có 12 mục đang thực hiện, trong đó bảy mục chờ review. Thành viên vẫn tiếp tục bắt đầu việc mới. Thời gian từ bắt đầu tới hoàn tất tăng trong bốn tuần liên tiếp.

**Câu hỏi:**

1. Nguyên tắc nào liên quan tới nhịp bền vững và cải tiến liên tục?
2. Thay vì thúc mọi người viết mã nhanh hơn, thử nghiệm dòng công việc nào hợp lý?
3. Chỉ số nào cần xem để biết thay đổi có tác dụng?

**Hướng giải tham khảo:** Nguyên tắc **8, 10, 12** hướng tới giảm WIP, hoàn tất việc đang làm và cải tiến chính sách review; **5 và 11** khuyến khích nhóm tự tìm giải pháp. Đặt giới hạn WIP, ưu tiên review, chia nhỏ hạng mục nếu phù hợp rồi theo dõi cycle time, WIP, thời gian chờ và lỗi sau review. Không kết luận chỉ từ một ngày có số liệu tốt.

### Tình huống C — Nhóm từ xa hiểu sai quy tắc nghiệp vụ

Một ticket mô tả “khách có thể hủy lịch trước giờ hẹn”, nhưng không nêu giới hạn thời gian. Lập trình viên hiểu là bất kỳ lúc nào trước giờ hẹn, bên vận hành hiểu là phải trước 24 giờ, người kiểm thử không rõ kỳ vọng.

**Câu hỏi:** Nguyên tắc nào phù hợp và bạn sẽ tổ chức cuộc trao đổi như thế nào?

**Hướng giải tham khảo:** Nguyên tắc **4 và 6** gợi ý cuộc trao đổi trực tiếp có người nắm quy tắc, Developers và người kiểm thử; **11** hỗ trợ nhóm cùng thiết kế cách triển khai, **7 và 9** yêu cầu biến kết luận thành hành vi được kiểm thử. Sau cuộc trao đổi, cập nhật user story và tiêu chí chấp nhận cho các trường hợp sát ranh giới giờ hẹn, múi giờ và quyền hủy.

### Bài tập nhóm: ánh xạ một quyết định thật

Chọn một quyết định vừa xảy ra trong dự án. Hoàn thành bảng:

| Câu hỏi | Câu trả lời của nhóm |
| --- | --- |
| Vấn đề và mục tiêu là gì? | ... |
| Quyết định cụ thể cần đưa ra? | ... |
| Tối thiểu ba nguyên tắc Agile có liên quan? | ... |
| Dữ liệu hoặc phản hồi đang có, điều chưa chắc chắn? | ... |
| Hai phương án khả thi và đánh đổi của từng phương án? | ... |
| Ai cần tham gia và ai chịu trách nhiệm quyết định? | ... |
| Lát cắt nhỏ và chuẩn chất lượng cần giữ? | ... |
| Sau bao lâu, dựa vào chỉ số nào để xem lại? | ... |

Trao đổi kết quả với nhóm: Nếu hôm nay biết những gì đã biết sau khi làm, quyết định ban đầu có còn hợp lý không? Phần nào nên điều chỉnh ở vòng tới? Không cần tìm một nguyên tắc “đúng nhất”; hãy giải thích cách kết hợp các nguyên tắc cho một tình huống có thật.

## 20. Checklist khi áp dụng mười hai nguyên tắc

- [ ] Chúng ta biết vấn đề khách hàng cần giải quyết và kết quả muốn đạt.
- [ ] Lát cắt sắp giao có giá trị và có thể kiểm chứng, đạt chuẩn chất lượng.
- [ ] Thông tin mới được xem xét và backlog có thể đổi với lý do rõ ràng.
- [ ] Người có hiểu biết nghiệp vụ, kỹ thuật và vận hành có đường trao đổi thông suốt.
- [ ] Nhóm hiểu mục tiêu, có quyền chủ động hợp lý và được hỗ trợ tháo trở ngại.
- [ ] Các câu hỏi mơ hồ được trao đổi trực tiếp và kết luận quan trọng được ghi lại.
- [ ] Báo cáo tiến độ dựa vào phần mềm hoạt động được, có phân biệt với kết quả sản phẩm.
- [ ] WIP, năng lực và nhịp làm việc không phụ thuộc vào làm thêm giờ kéo dài.
- [ ] Kiểm thử, tích hợp, thiết kế và quan sát hệ thống đủ để thay đổi an toàn.
- [ ] Đã cân nhắc bỏ hoặc hoãn phần việc ít giá trị, đồng thời giữ nghĩa vụ bắt buộc.
- [ ] Nhóm có tiếng nói trong thiết kế, cách phối hợp và trách nhiệm với kết quả.
- [ ] Có hành động cải tiến cụ thể được thử, đo và xem lại định kỳ.

## 21. Tổng kết

Mười hai nguyên tắc Agile đưa ra một hệ thống câu hỏi cho các lựa chọn hằng ngày: **giao giá trị gì trước, phản ứng với thay đổi ra sao, phối hợp thế nào, bảo vệ chất lượng đến đâu và học từ kết quả bằng cách nào**. Chúng có ích nhất khi được dùng để phân tích một quyết định thực tế, thay vì học thuộc lòng rồi kiểm tra xem nhóm tổ chức bao nhiêu cuộc họp.

Một nhóm có thể áp dụng **Scrum** để tập trung mục tiêu và kiểm tra theo Sprint, **Kanban** để thấy và cải tiến dòng công việc, **XP** để giữ khả năng thay đổi ở cấp kỹ thuật. Dù lựa chọn cách phối hợp nào, những dấu hiệu quan trọng vẫn là phần mềm hữu ích được giao tăng dần, phản hồi tới quyết định sớm, chất lượng và vận hành đáng tin cậy, cùng việc điều chỉnh liên tục dựa trên bằng chứng.

### Tài liệu tham khảo nền tảng

- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — nguồn gốc và thứ tự mười hai nguyên tắc.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — bốn giá trị làm nền cho các nguyên tắc.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — cách Scrum tổ chức mục tiêu, Increment và kiểm tra thích ứng.
- [The Kanban Guide](https://kanbanguides.org/) — định nghĩa dòng công việc, WIP và các thước đo dòng.
- [DORA](https://dora.dev/) — nghiên cứu và hướng dẫn về năng lực giao thay đổi phần mềm, độ ổn định vận hành.
