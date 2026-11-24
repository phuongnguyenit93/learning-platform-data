# Làm rõ yêu cầu đúng mức cho quyết định sắp tới

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **làm rõ yêu cầu dần theo thời điểm cần quyết định** phù hợp với tư duy Agile và khi nào cần chuẩn bị sớm hơn.
2. Phân biệt mức chi tiết cần thiết cho định hướng sản phẩm, lựa chọn ưu tiên backlog, quyết định bắt đầu triển khai, kiểm thử và phát hành.
3. Xác định những thông tin còn thiếu thực sự cản trở quyết định, đồng thời phân biệt **sự thật, giả định, câu hỏi mở và rủi ro**.
4. Sử dụng trao đổi trực tiếp, ví dụ cụ thể, user story, tiêu chí chấp nhận, prototype và thử nghiệm kỹ thuật để giảm bất định.
5. Thực hành chia nhỏ yêu cầu, ghi nhận quyết định và phản hồi, tránh cả hai cực đoan: đặc tả quá sớm hoặc bắt đầu việc khi còn mơ hồ nguy hiểm.

## 1. Làm rõ yêu cầu đúng mức nghĩa là gì?

Trong phát triển phần mềm thích ứng, yêu cầu ban đầu hiếm khi đầy đủ và bất biến. Người dùng có thể chưa biết cách giải quyết nào hiệu quả; đội kỹ thuật cũng có thể chưa biết một ràng buộc tích hợp hay hiệu năng sẽ ảnh hưởng đến thiết kế ra sao. Vì vậy, cố định mọi chi tiết ngay đầu dự án thường làm tăng khối lượng tài liệu cần sửa khi học được điều mới.

**Làm rõ yêu cầu đúng mức cho quyết định sắp tới** (*just-in-time requirements clarification*, *progressive elaboration*) là chủ động bổ sung thông tin **vừa đủ để đưa ra quyết định hiện tại có trách nhiệm**, rồi tiếp tục làm rõ khi tiến gần đến thời điểm sử dụng thông tin đó.

Ba câu hỏi định hướng:

1. **Sắp phải quyết định điều gì?** Đầu tư vào cơ hội nào, ưu tiên hạng mục nào, bắt đầu một lát cắt nào, chọn quy tắc nghiệp vụ nào hay phát hành được chưa?
2. **Muốn quyết định đúng, cần biết tối thiểu điều gì?** Người dùng, giá trị, ràng buộc, ví dụ hành vi, độ lớn tương đối, phụ thuộc, tiêu chí chất lượng hay bằng chứng?
3. **Điều gì có thể để lại để tìm hiểu sau, và rủi ro của việc chờ là bao nhiêu?** Thông tin nào sẽ lỗi thời nếu viết sớm; thông tin nào bắt buộc chuẩn bị từ bây giờ vì chi phí thay đổi lớn?

Đúng mức **không phải ít tài liệu nhất**. Một thay đổi câu chữ trên nút bấm có thể chỉ cần ví dụ và tiêu chí ngắn; một thay đổi luồng thanh toán hoặc quyền truy cập dữ liệu cần phân tích ngoại lệ, truy vết, bảo mật, thử nghiệm và phê duyệt sâu hơn trước khi tiến hành.

### Ví dụ mở đầu

Một nền tảng học trực tuyến nhận đề xuất: “Cải thiện khả năng học tiếp khi đổi thiết bị.”

- **Khi lựa chọn cơ hội đầu tư:** Cần biết học viên nào gặp vấn đề, mức ảnh hưởng, quan hệ với mục tiêu sản phẩm và cách đo kết quả. Chưa cần mô tả từng endpoint.
- **Khi quyết định thứ tự backlog:** Cần so sánh giá trị dự kiến, mức khẩn, phụ thuộc đồng bộ dữ liệu và nỗ lực tương đối với các hạng mục khác.
- **Ngay trước khi triển khai một lát cắt:** Cần ví dụ về vị trí dừng, hai thiết bị cập nhật khác nhau, quyền truy cập, tiêu chí chấp nhận và cách kiểm thử.
- **Trước khi phát hành:** Cần xác minh behavior, kết quả kiểm thử, tác động dữ liệu, giám sát lỗi, phương án khôi phục và các điều kiện phê duyệt liên quan.

Thông tin tăng dần theo **quyết định và rủi ro**, không theo mong muốn viết càng nhiều tài liệu càng tốt.

## 2. Vì sao phải chọn thời điểm làm rõ?

Trong Agile, việc tạo sản phẩm tăng dần và nhận phản hồi sớm giúp nhóm kiểm tra các giả thuyết. Làm rõ từng bước giúp giảm hai loại lãng phí đối lập:

| Cực đoan | Biểu hiện | Hậu quả có thể xảy ra |
| --- | --- | --- |
| **Đặc tả toàn bộ quá sớm** | Viết mọi luồng và từng trường dữ liệu cho các tính năng chưa biết có làm hay không | Mất nhiều công phân tích; yêu cầu lỗi thời; tạo cảm giác chắc chắn giả và ngại điều chỉnh. |
| **Làm rõ quá muộn** | Bắt đầu code khi chưa thống nhất người dùng, hành vi chính, điều kiện bảo mật, quy tắc lỗi | Phải làm lại, kiểm thử không biết đúng sai, tăng phụ thuộc và rủi ro vận hành. |
| **Làm rõ đúng thời điểm** | Đủ thông tin cho quyết định kế tiếp; ghi giả định và xử lý sớm các rủi ro đắt đỏ | Giữ lựa chọn mở khi có thể, giảm sai lệch, nâng khả năng phản hồi nhanh. |

Có thể mô tả cách tiếp cận bằng hai trục:

- **Mức chắc chắn tăng lên:** Khi có người dùng thực, ví dụ nghiệp vụ, kiểm thử và phản hồi từ increment.
- **Chi phí thay đổi có thể tăng:** Khi thiết kế đã được tích hợp sâu, dữ liệu đã di chuyển, hợp đồng đã ký hoặc việc phát hành đã hoàn tất.

Vì vậy, quyết định khó đảo ngược cần được làm rõ **sớm hơn và kỹ hơn**; quyết định có thể đảo ngược an toàn có thể được học qua thử nghiệm nhỏ.

**Quy tắc:** Trì hoãn chi tiết chưa cần, nhưng không trì hoãn **việc phát hiện rủi ro có thể làm hỏng quyết định**.

## 3. Bốn cấp độ thông tin theo chân trời quyết định

Thông tin không phải lúc nào cũng cần đạt một mức chi tiết cố định. Bảng sau là mô hình thực hành; thời gian như “vài tháng” hay “Sprint sau” chỉ mang tính ví dụ.

| Cấp độ | Quyết định sắp tới | Thông tin cần tương đối rõ | Có thể chưa cần |
| --- | --- | --- | --- |
| **Định hướng sản phẩm** | Vấn đề hoặc cơ hội nào đáng đầu tư? | Người dùng mục tiêu, nhu cầu, outcome mong muốn, cơ hội/rủi ro chiến lược và giới hạn bắt buộc | Chi tiết màn hình, endpoint, test case cho mọi trường hợp |
| **Sắp xếp Product Backlog** | Nên làm gì trước, việc nào cần nghiên cứu thêm? | Giá trị, mức khẩn, kích thước tương đối, phụ thuộc lớn, bất định và giả thuyết cần kiểm chứng | Toàn bộ thiết kế kỹ thuật và từng bước thao tác |
| **Sẵn sàng triển khai lát cắt** | Nhóm có thể bắt đầu và hoàn thành hạng mục nào? | User story hoặc mô tả có ý nghĩa, ví dụ điển hình/ngoại lệ quan trọng, tiêu chí chấp nhận, dữ liệu, ràng buộc kỹ thuật và điểm cần phối hợp | Kịch bản hiếm có thể kiểm tra sau nếu không gây nguy cơ, chi tiết của hạng mục còn xa |
| **Xác nhận và phát hành** | Hạng mục đáp ứng yêu cầu và đủ an toàn để dùng chưa? | Kết quả kiểm thử, Definition of Done nếu dùng Scrum, rủi ro còn lại, giám sát/khôi phục, bằng chứng và phê duyệt bắt buộc | Ý tưởng hoặc yêu cầu chưa được chọn làm ở bản này |

### Ba câu hỏi trước một buổi refinement

Một Product Owner hỏi đội: “Trong buổi này chúng ta cần quyết định **chọn hay không chọn** hạng mục, hay cần làm rõ đủ để **bắt đầu thực hiện**?” Hai mục đích này yêu cầu lượng thông tin khác nhau.

- Nếu chỉ chọn thứ tự, thường cần phân biệt những lựa chọn lớn và rủi ro, chưa cần phân tích từng thông báo lỗi.
- Nếu định bắt đầu trong ít ngày, cần làm rõ các hành vi giúp đội lập kế hoạch, viết code và kiểm thử.
- Nếu đang đụng rủi ro an toàn, dữ liệu hoặc kiểm định, phải mở rộng điều tra ngay dù công việc còn xa.

Nêu rõ mục tiêu buổi trao đổi giúp tránh tình trạng thảo luận lan sang các chi tiết chưa ảnh hưởng quyết định hiện tại.

## 4. Xác định “đủ rõ” theo rủi ro và khả năng đảo ngược

“Đủ” là một mức độ theo bối cảnh. Đánh giá ít nhất năm yếu tố:

1. **Giá trị và người bị ảnh hưởng:** Sai yêu cầu có khiến người dùng không hoàn thành công việc, mất tiền, mất dữ liệu hoặc tổn hại quyền lợi không?
2. **Độ bất định:** Có dữ kiện người dùng hay mới là suy đoán? Có thiếu quy tắc nghiệp vụ hoặc kiến thức kỹ thuật then chốt không?
3. **Chi phí sửa sai:** Có thể rollback bằng feature flag, hay cần migration dữ liệu phức tạp hoặc thay đổi hệ thống đối tác?
4. **Phụ thuộc:** Quyết định có ràng buộc API, hợp đồng, hạ tầng, lịch đội khác hoặc cổng phê duyệt?
5. **Thời điểm:** Nếu làm rõ muộn thêm một tuần, liệu đội có bỏ lỡ hạn đặt thiết bị, kiểm định, khả năng tích hợp hay cơ hội học hỏi không?

### Ví dụ đối chiếu

| Yêu cầu | Làm rõ tối thiểu trước khi thực hiện | Vì sao khác nhau |
| --- | --- | --- |
| Đổi nhãn nút “Tiếp tục” thành “Học tiếp” | Người dùng mục tiêu, chỗ hiển thị, ngôn ngữ, khả năng truy cập và tiêu chí nhận biết | Dễ thử và đảo ngược; rủi ro nhìn chung thấp. |
| Thêm thông báo nhắc học | Quyền đồng ý nhận thông báo, thời gian và tần suất, trạng thái tắt thông báo, tác động trải nghiệm | Có quyền riêng tư, chi phí gửi và nguy cơ làm phiền. |
| Đồng bộ tiến độ giữa thiết bị | Quy tắc xung đột, danh tính, tính nhất quán, mạng lỗi, khôi phục và test liên quan | Sai sót có thể làm mất dữ liệu học tập; cần ví dụ ngoại lệ rõ. |
| Thanh toán khóa học | Trạng thái giao dịch, gửi lại yêu cầu, đối soát, hoàn tiền, quyền truy cập, bảo mật, nhà cung cấp và bằng chứng kiểm thử | Rủi ro tài chính/pháp lý cao, nhiều trường hợp khó đảo ngược. |

Không có ngưỡng story point, số trang hay số cuộc họp nào tự động chứng minh yêu cầu đã đủ rõ. **Hãy xác định rủi ro lớn nhất còn có thể làm nhóm chọn sai hoặc triển khai sai**.

## 5. Quy trình làm rõ yêu cầu theo từng quyết định

Một vòng làm rõ thực dụng có thể thực hiện như sau:

### Bước 1 — Gọi tên quyết định cần ra

Ví dụ: “Có nên đưa tính năng học tiếp lên đầu Product Backlog?” hoặc “Có thể bắt đầu lát cắt đồng bộ tiến độ trên hai thiết bị trong Sprint tới chưa?”

Nếu không nói rõ quyết định, nhóm dễ chuyển sang liệt kê mọi câu hỏi có thể nghĩ ra và mất dấu mục đích.

### Bước 2 — Xác định outcome, người dùng và ranh giới

Làm rõ ai dùng, vấn đề thực tế, giá trị mong muốn và những điều không được vi phạm. Ví dụ:

> Học viên đang học trên máy tính muốn tiếp tục trên điện thoại mà không phải tìm lại bài. Dữ liệu tiến độ phải thuộc đúng tài khoản và không được mất khi đồng bộ.

Như vậy đã có **kết quả mong muốn** và **điều kiện bảo vệ dữ liệu**. Chưa nhất thiết phải chọn ngay loại cơ sở dữ liệu.

### Bước 3 — Phân loại thông tin hiện có

Ghi riêng bốn loại:

| Loại | Ví dụ | Việc làm tiếp theo |
| --- | --- | --- |
| **Đã quan sát** | Trong buổi dùng thử, 4/6 học viên mất thời gian tìm lại bài khi chuyển thiết bị | Xác định mức đại diện và tác động; không coi mẫu nhỏ là kết luận tuyệt đối. |
| **Giả định** | Người học muốn tự động mở đúng vị trí giây cuối cùng | Kiểm tra qua phỏng vấn hoặc prototype. |
| **Câu hỏi mở** | Nếu hai thiết bị cập nhật cùng lúc, lấy vị trí nào? | Làm rõ quy tắc với người phụ trách sản phẩm và kỹ thuật trước khi triển khai đồng bộ. |
| **Rủi ro/phụ thuộc** | API tiến độ có thể chưa hỗ trợ versioning; thay đổi dữ liệu cần migration | Làm technical spike hoặc trao đổi với đội API sớm. |

Phân loại giúp người đọc không nhầm **ý kiến** với **quy tắc đã được xác nhận**.

### Bước 4 — Đặt câu hỏi có tác dụng đổi quyết định

Ưu tiên các câu hỏi mà câu trả lời sẽ ảnh hưởng phạm vi, kiến trúc, thời hạn, độ an toàn hoặc thứ tự backlog:

- Người dùng có thật sự cần đồng bộ chính xác đến giây, hay chỉ cần mở lại đúng bài?
- Nếu mất mạng, app có ghi tiến độ cục bộ không và khi nào đồng bộ?
- Ai được phép xem hoặc sửa tiến độ?
- Lỗi nào được phép hiển thị, lỗi nào phải ngăn thao tác?
- Có hệ thống/đối tác nào phải thay đổi trước?
- Phần nhỏ nào có thể giao mà vẫn đem lại giá trị và đủ chất lượng?

Tránh tốn một giờ tranh luận về màu viền của thông báo khi nhóm còn chưa thống nhất mất dữ liệu có thể xảy ra hay không.

### Bước 5 — Chọn cách học nhanh và ít rủi ro

Không phải câu hỏi nào cũng giải bằng cuộc họp. Có thể:

- **Trao đổi với người dùng:** xác nhận vấn đề, bối cảnh và cách họ đánh giá thành công.
- **Three Amigos:** đại diện sản phẩm/nghiệp vụ, phát triển và kiểm thử cùng xem ví dụ, ngoại lệ và tiêu chí chấp nhận. Đây là một thực hành cộng tác, không phải sự kiện bắt buộc trong Scrum.
- **Prototype/wireframe:** kiểm tra luồng, khả năng hiểu thao tác trước khi xây đầy đủ.
- **Example mapping:** tách quy tắc, ví dụ và câu hỏi chưa được giải đáp.
- **Technical spike có giới hạn thời gian:** điều tra khả thi, API, dữ liệu hoặc công nghệ; đầu ra là kiến thức và quyết định, không nhất thiết là tính năng sản xuất.
- **Thử nghiệm trong phạm vi kiểm soát:** giao lát cắt nhỏ hoặc bật cho nhóm người dùng thích hợp để quan sát kết quả.

### Bước 6 — Ghi lại quyết định cần truy vết

Kết thúc bằng mô tả ngắn: **quyết định, lý do, giả định còn mở, người chịu trách nhiệm, thời điểm xem lại**. Thông tin nên lưu ở nơi nhóm có thể tìm lại (backlog item, ADR, tài liệu nghiệp vụ hoặc hệ thống quản lý việc) theo nhu cầu.

### Bước 7 — Kiểm tra khi có bằng chứng mới

Sau khi tạo increment, xem hành vi và phản hồi. Nếu giả thuyết sai, cập nhật backlog và chi tiết yêu cầu. Phát triển thích ứng nghĩa là **có khả năng thay đổi hiểu biết**, không phải bảo vệ đặc tả cũ bất kể kết quả.

## 6. Conversation, Confirmation và tài liệu hỗ trợ

Trong thực hành user story thường nói đến **3C**:

- **Card:** mô tả ngắn về nhu cầu, đủ để nhận diện và trao đổi.
- **Conversation:** cuộc trao đổi để hiểu mục đích, quy tắc và các lựa chọn; không giới hạn vào một lần họp.
- **Confirmation:** ví dụ và tiêu chí giúp xác nhận yêu cầu đã được đáp ứng.

3C nhắc rằng một dòng user story **không phải toàn bộ đặc tả**. Một story ngắn nhưng không có cuộc trao đổi hoặc tiêu chí kiểm chứng có thể mơ hồ; một story dài hàng trang cũng có thể sai nhu cầu nếu chưa nghe người dùng.

### Ai cần tham gia?

| Quyết định | Người nên tham gia theo bối cảnh | Thông tin họ mang đến |
| --- | --- | --- |
| Xác định vấn đề và giá trị | Product Owner, người dùng/khách hàng, UX, chuyên gia nghiệp vụ | Mục tiêu, hành vi thực, tác động và bằng chứng. |
| Làm rõ quy tắc và ngoại lệ | Người phụ trách nghiệp vụ, Developers, QA/tester | Quy tắc xử lý, dữ liệu, tình huống lỗi, ví dụ kiểm chứng. |
| Chọn phương án kỹ thuật | Developers, kiến trúc sư khi cần, đội hạ tầng và bảo mật | Khả thi, rủi ro kỹ thuật, phụ thuộc, cách vận hành. |
| Xác định quyền truy cập và tuân thủ | Người có trách nhiệm về bảo mật, dữ liệu, pháp lý theo phạm vi | Nghĩa vụ, ranh giới an toàn, hồ sơ/phê duyệt cần có. |
| Quyết định ưu tiên | Product Owner hoặc người có quyền quản lý backlog, cùng ý kiến chuyên môn cần thiết | Giá trị, chi phí cơ hội, năng lực, rủi ro và mục tiêu sản phẩm. |

Đội không cần mời tất cả những người này vào mọi cuộc họp. Chỉ đưa **đúng người có thông tin hoặc quyền quyết định** vào đúng cuộc trao đổi.

### Cách hỏi giúp tránh giải pháp hóa quá sớm

Thay vì hỏi “Anh/chị muốn nút màu gì?”, hãy hỏi:

- “Người học đang cố hoàn thành việc gì khi gặp vấn đề này?”
- “Tình huống gần đây nhất diễn ra thế nào?”
- “Nếu chỉ cải thiện được một điều, anh/chị muốn điều gì tốt hơn?”
- “Nếu không có chức năng mới này, điều gì sẽ xảy ra?”
- “Có trường hợp nào mà cách xử lý dự kiến trở nên nguy hiểm hoặc gây bất ngờ không?”

Điều này không phủ nhận kiến thức của khách hàng. Nó giúp nhóm hiểu **kết quả** trước khi chốt **cách triển khai**.

## 7. Ví dụ đầy đủ: làm rõ story “Tiếp tục học trên thiết bị khác”

### 7.1. Yêu cầu ban đầu còn mơ hồ

> “Khi đăng nhập trên điện thoại, học viên phải tiếp tục được bài đã học trên máy tính.”

Chưa rõ “tiếp tục” là đúng **khóa học**, **bài học**, **vị trí phát video**, **bài kiểm tra**, hay tất cả. Nếu developer và tester tự chọn ý nghĩa khác nhau, nhóm sẽ phải làm lại dù cùng nghĩ mình hiểu yêu cầu.

### 7.2. Xác định lát cắt đầu tiên

Giả sử sau khi phỏng vấn, nhóm nhận thấy giá trị quan trọng nhất là **mở lại đúng bài học gần nhất**. Lát cắt đầu có thể là:

> **Là** học viên đã đăng nhập trên nhiều thiết bị, **tôi muốn** nhìn thấy bài học gần nhất đã lưu và mở lại bài đó **để** không mất thời gian tìm kiếm.

Phạm vi tạm thống nhất:

- Hỗ trợ cùng một tài khoản đã đăng nhập trên hai trình duyệt/thiết bị.
- Hiển thị khóa học và bài đã lưu gần nhất; mở đúng bài khi nhấn “Tiếp tục học”.
- Ghi thời điểm cập nhật để xác định bản ghi gần nhất theo quy tắc đã thống nhất.
- Chưa triển khai tải nội dung ngoại tuyến hay đồng bộ vị trí từng giây; những yêu cầu này được ghi riêng trong Product Backlog.

**Cảnh báo:** Việc chọn bản ghi có thời gian mới nhất chỉ là một quy tắc nghiệp vụ có thể cân nhắc. Nếu đồng hồ thiết bị không đáng tin hoặc một cập nhật cũ đến muộn, nhóm phải thiết kế cơ chế xác định thứ tự phù hợp ở phía hệ thống. Không được giả định “mới nhất” tự động là đúng.

### 7.3. Tiêu chí chấp nhận với ví dụ cụ thể

| Tình huống | Đầu vào/điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Có tiến độ gần nhất | Tài khoản A đã mở bài 4 của khóa X trên máy tính; dữ liệu lưu thành công | Trên điện thoại của A, nút “Tiếp tục học” dẫn đến bài 4 của khóa X. |
| Chưa có tiến độ | Tài khoản mới chưa bắt đầu khóa học | Không hiển thị thông tin bài học giả; hướng người học chọn khóa phù hợp. |
| Khác tài khoản | Tài khoản B đăng nhập cùng thiết bị từng dùng bởi A | B không nhìn thấy hoặc truy cập được tiến độ riêng của A. |
| Mất kết nối khi ghi | Trình duyệt gửi cập nhật nhưng mạng thất bại | Ứng dụng không báo đã lưu thành công khi chưa được xác nhận; có hành vi thử lại/thông báo theo thiết kế. |
| Bài không còn được truy cập | Người học hết quyền vào khóa X | Không mở nội dung trái quyền; hiển thị thông báo phù hợp. |
| Cập nhật cạnh tranh | Hai thiết bị gửi tiến độ gần cùng lúc | Xử lý theo quy tắc xung đột đã được xác nhận và kiểm thử. |

Các trường hợp trên không nhất thiết phải nằm tất cả trong cùng một user story. Nhóm có thể tách theo **lát cắt giá trị**, nhưng không được bỏ những điều kiện an toàn bắt buộc đối với lát cắt được giao.

### 7.4. Minh họa bằng Gherkin

Gherkin giúp một số nhóm viết ví dụ hành vi theo cấu trúc Given–When–Then; nó là **lựa chọn diễn đạt**, không phải yêu cầu bắt buộc của Agile hay Scrum.

~~~gherkin
Feature: Tiếp tục bài học đã lưu

  Scenario: Mở lại bài học gần nhất trên thiết bị khác
    Given học viên A đã đăng nhập và có quyền học khóa X
    And tiến độ gần nhất đã được lưu của A là bài 4 thuộc khóa X
    When A đăng nhập trên điện thoại và chọn "Tiếp tục học"
    Then hệ thống mở bài 4 thuộc khóa X
    And không hiển thị thông tin tiến độ của tài khoản khác

  Scenario: Không có tiến độ đã lưu
    Given học viên A chưa bắt đầu khóa học nào
    When A mở trang chủ
    Then không hiển thị nút "Tiếp tục học" với dữ liệu không tồn tại
    And A có thể tìm và chọn khóa học để bắt đầu
~~~

Gherkin chỉ diễn đạt một phần hành vi. Một số rủi ro như đồng bộ cạnh tranh, hiệu năng hoặc bảo mật có thể cần **test tích hợp, mô hình dữ liệu, kiểm thử quyền truy cập và quyết định kiến trúc** riêng.

### 7.5. Tách điều đã chốt và điều còn mở

| Mục | Trạng thái | Cách xử lý |
| --- | --- | --- |
| Mục tiêu người dùng: mở lại đúng bài | Đã xác nhận cho lát cắt đầu | Ghi vào user story và tiêu chí chấp nhận. |
| Khả năng truy cập chỉ của đúng tài khoản | Ràng buộc bắt buộc | Thiết kế và kiểm thử trước khi phát hành. |
| Vị trí video chính xác đến từng giây | Chưa có bằng chứng đủ | Đưa vào backlog khám phá; không ngầm hứa ở bản đầu. |
| Quy tắc hai thiết bị ghi cùng lúc | Chưa thống nhất | Trao đổi với sản phẩm, kỹ thuật và QA trước khi code phần đồng bộ liên quan. |
| Cách API xác định phiên bản tiến độ | Chưa chắc về kỹ thuật | Technical spike hoặc contract test với dịch vụ tiến độ. |

Nhóm có thể bắt đầu lát cắt an toàn nếu các điểm còn mở **không ngăn hoàn thành tiêu chí đã chọn**; nếu điểm mở liên quan trực tiếp đến tính đúng đắn hoặc bảo mật, phải làm rõ trước.

## 8. Chia nhỏ yêu cầu để giảm lượng chi tiết cần quyết định

Khi một yêu cầu quá lớn, nhóm có thể tranh luận hàng giờ vì nhiều vấn đề bị gói vào cùng một hạng mục. Chia theo **lát cắt từ đầu đến cuối** làm rõ được phần nào có thể tạo giá trị độc lập và phần nào còn bất định.

### Ví dụ phân rã

Yêu cầu lớn: “Đồng bộ toàn bộ trải nghiệm học tập giữa mọi thiết bị và khi ngoại tuyến.”

Một chuỗi lát cắt có thể là:

1. Trên thiết bị mới, hiển thị bài học gần nhất đã lưu.
2. Mở đúng bài và vị trí thích hợp khi có kết nối ổn định.
3. Xử lý rõ trạng thái mạng không ổn định và việc lưu chưa thành công.
4. Giải quyết xung đột khi hai thiết bị cập nhật gần nhau.
5. Hỗ trợ một loại nội dung ngoại tuyến được phép, với đồng bộ khi kết nối trở lại.

Đây là **phương án ví dụ**, không có nghĩa các bước sau luôn độc lập với nhau. Độ an toàn của dữ liệu, danh tính và quyền truy cập cần được bảo vệ ở mỗi lát cắt được phát hành.

### Chia theo giá trị hay theo tầng kỹ thuật?

| Kiểu chia | Ưu điểm/hạn chế | Khi nào hữu ích |
| --- | --- | --- |
| “Làm database → làm API → làm UI” | Tiện phân công kỹ thuật nhưng người dùng chưa thấy hành vi hoàn chỉnh đến cuối. | Có thể dùng như task nội bộ của một story; không nên mặc nhiên coi mỗi tầng là increment có giá trị độc lập. |
| “Người dùng mở được bài gần nhất” | Có thể demo, kiểm thử và nhận phản hồi từ luồng hoàn chỉnh. | Thường tốt để kiểm chứng sản phẩm tăng dần. |
| “Tìm hiểu giải pháp lưu xung đột” | Tạo kiến thức và giảm rủi ro nhưng chưa trực tiếp tạo chức năng dùng được. | Phù hợp khi thiếu kiến thức kỹ thuật cần thiết; giới hạn thời gian và ghi kết quả. |

### Câu hỏi kiểm tra lát cắt

- Người dùng nào có thể làm việc gì sau khi hoàn thành?
- Có thể kiểm thử hành vi qua hệ thống tích hợp thực tế hay môi trường phù hợp không?
- Có thể bỏ phần còn lại khỏi lần giao này mà vẫn giữ chất lượng và quyền truy cập không?
- Bằng chứng từ lát cắt này có thể thay đổi quyết định về phần tiếp theo không?

Nếu hạng mục quá lớn để trả lời rõ, cần chia nhỏ hoặc xác định một thí nghiệm giảm bất định trước.

## 9. Làm rõ yêu cầu phi chức năng và điều kiện bắt buộc

Những tiêu chí như bảo mật, tính đúng đắn dữ liệu, hiệu năng, khả năng truy cập, khả năng quan sát và khôi phục thường khó nhìn thấy trong một câu user story, nhưng có thể quyết định sản phẩm có sử dụng được hay không.

### 9.1. Đưa yêu cầu chất lượng về tình huống kiểm chứng

| Yêu cầu mơ hồ | Làm rõ thành câu hỏi/tiêu chí |
| --- | --- |
| “Trang phải nhanh.” | Nhanh ở thao tác nào, với nhóm thiết bị và tải nào? Dùng chỉ số độ trễ nào, trong khoảng thời gian nào? |
| “Dữ liệu an toàn.” | Ai được xem/sửa dữ liệu nào? Có kiểm thử phân quyền, ghi log phù hợp và xử lý dữ liệu nhạy cảm không? |
| “Không được mất tiến độ.” | Trong trường hợp ngắt mạng, tải lại trang, nhiều thiết bị, lưu thất bại hoặc sự cố dịch vụ, hành vi bảo toàn và khôi phục là gì? |
| “Dễ dùng.” | Người dùng mục tiêu có hoàn thành tác vụ không; lỗi phổ biến, tiêu chuẩn khả năng truy cập và bằng chứng thử nghiệm là gì? |
| “Vận hành tốt.” | Ai trực xử lý? Có cảnh báo, log phù hợp, runbook và phương án rollback/migration khi phát hành không? |

Đừng tự bịa một ngưỡng “95% nhanh”, “99,99% sẵn sàng” hoặc số người dùng đồng thời khi chưa có mục tiêu, dữ liệu nền hay nghĩa vụ tương ứng. Ngưỡng nên do những người có trách nhiệm thỏa thuận dựa trên tác động và rủi ro.

### 9.2. Điều gì thuộc user story, điều gì thuộc Definition of Done?

- **Tiêu chí chấp nhận của story:** Quy tắc riêng của hạng mục, chẳng hạn tài khoản B không được thấy tiến độ tài khoản A.
- **Definition of Done** (trong Scrum): Tiêu chuẩn chất lượng chung cho increment, chẳng hạn thay đổi đã được review, test thích hợp đạt, các yêu cầu bảo mật và vận hành liên quan được đáp ứng.
- **Bằng chứng phê duyệt đặc thù:** Quy trình bắt buộc như pháp lý, kiểm toán, thay đổi dữ liệu hoặc an toàn, tùy sản phẩm.

Ba yếu tố bổ sung cho nhau. Đủ chi tiết nghiệp vụ mà bỏ qua rủi ro hệ thống không phải là yêu cầu đã được làm rõ đúng mức.

### 9.3. Khi phải phân tích sớm hơn

Một số công việc có chi phí đảo ngược rất lớn hoặc phụ thuộc lịch bên ngoài, ví dụ:

- Thay đổi định dạng lưu dữ liệu trên quy mô lớn.
- Tích hợp thanh toán, định danh và thông tin cá nhân.
- Yêu cầu phải qua kiểm định, chứng nhận hoặc phê duyệt theo pháp luật.
- Thỏa thuận hợp đồng API với nhiều đội hoặc nhà cung cấp.

Ở những trường hợp này, có thể cần tài liệu thiết kế, truy vết, kiểm thử và phê duyệt từ sớm hơn bình thường. Điều đó **không đi ngược Agile** nếu thông tin phục vụ quyết định và an toàn thực tế.

## 10. Khi chưa thể trả lời, hãy chọn một thí nghiệm học hỏi

Một câu hỏi mở không nhất thiết khiến cả backlog phải dừng. Cần xác định **thông tin chưa biết có cản trở quyết định gần nhất không** và thử cách học với chi phí thích hợp.

### 10.1. Technical spike

Ví dụ: “API tiến độ hiện tại có thể xử lý hai cập nhật gần đồng thời mà không mất dữ liệu không?”

Mô tả một spike có mục tiêu:

| Thành phần | Nội dung ví dụ |
| --- | --- |
| Câu hỏi | Có cách nào phát hiện và xử lý xung đột phiên bản tiến độ an toàn? |
| Phạm vi | Thử hai cơ chế cập nhật trên môi trường thử, không thay đổi dữ liệu sản xuất. |
| Giới hạn | Tối đa hai ngày làm việc trong kế hoạch ví dụ; điều chỉnh theo độ rủi ro. |
| Bằng chứng cần có | Test cạnh tranh, trường hợp lỗi và hạn chế của từng cơ chế. |
| Đầu ra | Khuyến nghị lựa chọn, rủi ro còn lại, thay đổi API cần thiết và hạng mục backlog tiếp theo. |

Spike giúp giảm bất định nhưng không tự động là increment đạt giá trị người dùng. Khi điều tra xong, đội cần **ra quyết định** chứ không tiếp tục nghiên cứu vô thời hạn.

### 10.2. Prototype và thử nghiệm người dùng

Nếu câu hỏi là “Học viên hiểu nút tiếp tục học đặt ở đâu?”, prototype thường hữu ích hơn cuộc họp đoán ý. Quan sát người dùng thực hiện tác vụ, ghi thành công/thất bại và lý do; cẩn thận với mẫu nhỏ hoặc nhóm thử không đại diện.

Nếu câu hỏi là “Cách lưu tiến độ này có bảo toàn dữ liệu khi mạng thất thường?”, cần kiểm thử kỹ thuật và kịch bản lỗi; một prototype đẹp không cung cấp đủ bằng chứng.

### 10.3. Quy tắc quyết định tiếp theo

Mỗi hoạt động khám phá nên trả lời: **Khi có kết quả A ta làm gì, khi có kết quả B ta làm gì?** Nếu không có hành động nào phụ thuộc kết quả, hoạt động có nguy cơ chỉ tạo thêm tài liệu.

## 11. Làm rõ liên tục trong Scrum, Kanban và XP

### 11.1. Scrum: refinement là hoạt động liên tục

Trong Scrum, **Product Backlog refinement** là hoạt động phân rã và làm rõ Product Backlog Item thành các hạng mục nhỏ và chính xác hơn, bổ sung mô tả, thứ tự, kích thước khi phù hợp. Đây **không phải một sự kiện Scrum bắt buộc có timebox cố định**. Đội chọn cách và thời điểm phù hợp với công việc.

- **Product Goal** định hướng loại giá trị đang theo đuổi.
- **Product Backlog** minh bạch các hạng mục và thứ tự; hạng mục tương lai xa có thể ít chi tiết.
- **Sprint Planning** cần thông tin đủ để xây dựng Sprint Goal và kế hoạch ban đầu khả thi.
- **Sprint Backlog** được Developers điều chỉnh khi có thêm kiến thức; các chi tiết có thể tiếp tục được làm rõ trong Sprint.
- **Sprint Review** cung cấp phản hồi về increment, từ đó ảnh hưởng Product Backlog.

**Definition of Ready** có thể là một thỏa thuận hỗ trợ nhóm nhận diện thông tin cần có trước khi bắt đầu; nó **không phải artefact/cam kết bắt buộc được định nghĩa trong Scrum Guide** và không nên trở thành cổng thủ tục cứng nhắc. Nếu dùng checklist sẵn sàng, phải tránh biến nó thành yêu cầu đặc tả hoàn chỉnh hoặc quyền ngăn đội học qua thử nghiệm.

### 11.2. Kanban: làm rõ theo chính sách chọn việc và dòng chảy

Với công việc đến liên tục như hỗ trợ sản phẩm hoặc xử lý lỗi, Kanban có thể dùng chính sách **replenishment/commitment** để quyết định khi nào công việc được kéo vào dòng thực hiện.

Ví dụ: trước khi một hạng mục vào cột “Sẵn sàng”, nhóm cần biết tác động, mức khẩn, cách tái hiện hoặc tiêu chí thành công, người có quyền giải đáp và phụ thuộc quan trọng. Nếu một lỗi khẩn đang làm gián đoạn dịch vụ, đội có thể có chính sách xử lý khẩn riêng; không chờ một biểu mẫu đầy đủ mới được bắt đầu khôi phục.

**Giới hạn WIP** cũng giúp tránh khởi động quá nhiều yêu cầu chưa rõ, rồi bỏ dở vì thiếu thông tin. Khi một hạng mục bị chặn, bảng nên hiển thị rõ **câu hỏi còn thiếu, ai đang xử lý và tuổi công việc**.

### 11.3. XP: biến ví dụ thành phản hồi kỹ thuật

Các thực hành XP giúp giảm chi phí khi yêu cầu thay đổi:

- TDD hoặc kiểm thử tự động phù hợp giúp làm rõ hành vi mong đợi và phát hiện hồi quy.
- Tích hợp liên tục giúp lộ sớm hiểu lầm giữa các thành phần.
- Pair programming/review tạo cơ hội chia sẻ cách hiểu và chất lượng thiết kế.
- Refactor có kiểm thử giúp cải thiện cấu trúc khi hiểu biết phát triển.

Tuy nhiên, code chạy qua test không chứng minh rằng nhóm đã hiểu **đúng vấn đề của người dùng**. Vẫn phải kiểm chứng giá trị qua người dùng hoặc đại diện nghiệp vụ phù hợp.

## 12. Khi yêu cầu thay đổi sau khi đã làm rõ

Không nên coi bản mô tả yêu cầu như hợp đồng bất biến. Một khi có dữ kiện mới, nhóm cần đánh giá:

1. **Nguồn thay đổi:** Phản hồi người dùng, luật mới, lỗi nghiêm trọng, kiến thức kỹ thuật mới hay yêu cầu tùy hứng?
2. **Tác động giá trị:** Mục tiêu ban đầu còn đúng không? Trường hợp nào bị ảnh hưởng?
3. **Độ khẩn và rủi ro:** Có tác động bảo mật, dữ liệu, tính sẵn sàng hoặc mốc bắt buộc?
4. **Chi phí thay đổi:** Phải sửa code, test, migration, tích hợp và tài liệu nào?
5. **Quyền quyết định:** Ai điều chỉnh Product Backlog, cam kết phát hành và rủi ro?
6. **Kiểm chứng:** Cần bổ sung tiêu chí chấp nhận, test hoặc thí nghiệm nào?

### Ví dụ thay đổi trong Sprint

Sprint Goal là giúp học viên mở lại bài gần nhất. Trong Sprint, người dùng thử chỉ ra nút “Tiếp tục học” khó tìm trên điện thoại.

Nếu thay đổi vị trí nút là cách làm rõ hơn mục tiêu hiện tại và đội có thể kiểm thử an toàn, nhóm có thể thương lượng cập nhật kế hoạch để đạt Sprint Goal. Nếu kinh doanh yêu cầu thêm toàn bộ hệ thống điểm thưởng, đây có thể là một nhu cầu khác cần Product Owner đánh giá và sắp xếp lại Product Backlog, thay vì mở rộng bất ngờ vào Sprint.

Trong Scrum, **không nên tạo thay đổi làm nguy hiểm Sprint Goal**; phạm vi có thể được làm rõ và thương lượng khi có thêm kiến thức. Yêu cầu khẩn về an toàn hoặc dữ liệu phải được xử lý phù hợp với mức rủi ro và cơ chế quyết định thực tế.

### Cách ghi thay đổi ngắn

~~~text
Thông tin mới: 4/6 người dùng thử không thấy nút "Tiếp tục học" trên điện thoại.
Ảnh hưởng: Giảm khả năng đạt mục tiêu mở lại bài nhanh.
Giả thuyết: Đưa nút lên vùng hiển thị đầu trang sẽ dễ nhận thấy hơn.
Quyết định: Thử phương án A trong phạm vi hiện tại, giữ tiêu chí phân quyền.
Người quyết định ưu tiên: Product Owner; Developers chọn cách thực hiện.
Kiểm chứng: Quan sát thao tác thử, theo dõi lỗi và kết quả sử dụng.
Điểm xem lại: Buổi review sau khi có bản thử và dữ liệu phù hợp.
~~~

Nhờ ghi quyết định, nhóm giữ được **vết thay đổi về lý do**, không phải tạo một bản tài liệu dài mới mỗi lần điều chỉnh.

## 13. Đo hiệu quả của việc làm rõ yêu cầu

Làm rõ đúng mức không nên được đánh giá bằng số trang tài liệu, số buổi refinement hay số story point đã ước lượng. Hãy quan sát **khả năng ra quyết định và kết quả của dòng công việc**.

| Tín hiệu | Câu hỏi cần tìm hiểu | Lưu ý |
| --- | --- | --- |
| **Việc bị chặn vì thiếu quyết định** | Những hạng mục nào chờ câu trả lời nghiệp vụ hoặc kỹ thuật? Chờ bao lâu? | Cần phân biệt thiếu thông tin với phụ thuộc nhân lực hoặc môi trường. |
| **Làm lại do hiểu sai yêu cầu** | Có bao nhiêu lần sửa lớn vì hai bên hiểu khác nhau? Nguyên nhân cụ thể? | Không quy lỗi cho cá nhân; một thay đổi do học hỏi có giá trị không nhất thiết là lãng phí. |
| **Lead time / cycle time** | Việc làm rõ có làm thời gian từ yêu cầu đến giá trị dễ dự báo hơn không? | Nêu rõ mốc bắt đầu/kết thúc và loại việc; xem phân bố, không chỉ trung bình. |
| **Lỗi liên quan tiêu chí chấp nhận** | Có lỗi do bỏ sót quy tắc nghiệp vụ hoặc ngoại lệ quan trọng? | Gắn bằng chứng với ví dụ và test; đừng chỉ đếm lỗi. |
| **Kết quả người dùng** | Lát cắt giao có giải quyết đúng vấn đề ban đầu? | Dựa vào hành vi, phản hồi và ngữ cảnh, không chỉ số tính năng giao. |
| **Chi phí khám phá không tạo quyết định** | Các cuộc họp/prototype có kết thúc bằng kiến thức, lựa chọn hay cập nhật backlog? | Không cắt bỏ hoạt động học hỏi chỉ vì chưa sinh code. |

### Một thí nghiệm cải tiến quy trình

**Vấn đề:** Trong bốn Sprint gần đây, nhiều hạng mục phải dừng giữa chừng vì chưa thống nhất quy tắc lỗi.

**Giả thuyết:** Nếu Product Owner, Developer và Tester dành một cuộc trao đổi ngắn với các ví dụ “đường thành công – ngoại lệ – lỗi” trước khi bắt đầu những story có rủi ro cao, số lần bị chặn vì thiếu quyết định sẽ giảm.

**Thử nghiệm:** Áp dụng cho một nhóm story trong hai Sprint; ghi rõ loại trở ngại, thời gian chờ và tỷ lệ làm lại, rồi so với bối cảnh trước đó.

**Quyết định sau thử:** Giữ, điều chỉnh hoặc bỏ thực hành tùy dữ liệu. Nếu nguyên nhân chính là API của nhà cung cấp không ổn định, việc tăng số cuộc họp refinement có thể không giải quyết được điểm nghẽn.

## 14. Những ngộ nhận và sai lầm thường gặp

| Ngộ nhận | Vì sao chưa đúng | Cách thực hành tốt hơn |
| --- | --- | --- |
| “Agile không cần yêu cầu rõ.” | Thiếu hành vi và điều kiện kiểm chứng gây làm lại, lỗi và rủi ro. | Làm rõ đến mức cần để quyết định/triển khai an toàn; tiếp tục học khi có phản hồi. |
| “Mọi user story phải đủ chi tiết từ đầu dự án.” | Hạng mục xa thường thay đổi hoặc bị loại; chi tiết sớm có thể lãng phí. | Làm rõ dần theo mức gần thực hiện và rủi ro. |
| “Story nào cũng phải có Definition of Ready cứng.” | Definition of Ready không phải yêu cầu bắt buộc của Scrum; dễ thành cổng thủ tục. | Dùng thỏa thuận nhóm linh hoạt và tập trung vào thông tin thật sự cần. |
| “Một câu As a–I want–So that là đủ.” | Một câu không giải quyết quy tắc, ví dụ hay bất định. | Dùng 3C: mô tả, trao đổi và xác nhận bằng ví dụ/tiêu chí. |
| “Cứ viết nhiều test case là hiểu đúng.” | Test có thể xác nhận một hành vi sai mục tiêu người dùng. | Kiểm chứng giả thuyết giá trị song song với hành vi kỹ thuật. |
| “Bất kỳ câu hỏi chưa trả lời nào cũng phải chặn story.” | Có câu hỏi có thể học sau mà không làm nguy hiểm lát cắt hiện tại. | Phân loại theo ảnh hưởng quyết định, rủi ro và chi phí trì hoãn. |
| “Spike là cách kéo dài nghiên cứu cho chắc.” | Không có thời hạn và đầu ra rõ sẽ khó chuyển thành giá trị. | Timebox spike, nêu câu hỏi và tiêu chí quyết định sau kết quả. |
| “Đã thống nhất yêu cầu thì không được đổi.” | Phản hồi mới có thể làm giả định ban đầu sai. | Đánh giá tác động, cập nhật backlog và cam kết theo quyền quyết định. |
| “Chia nhỏ theo tầng kỹ thuật là đã có increment.” | Chưa chắc người dùng có luồng hoàn chỉnh để thử. | Ưu tiên lát cắt theo hành vi người dùng và chất lượng xuyên suốt. |
| “Làm rõ đúng lúc có nghĩa chờ tới phút cuối.” | Rủi ro lớn, phê duyệt và phụ thuộc bên ngoài cần được phát hiện sớm. | Phân tích sớm những quyết định khó đảo ngược; để lại chi tiết không cấp thiết. |

## 15. Bài tập thực hành

### Bài tập 1 — Mức làm rõ theo quyết định

Một người quản lý yêu cầu “Thêm chức năng nhắc học để giảm bỏ dở khóa học” nhưng dự án chỉ có thể bắt đầu tính năng này sau khoảng hai tháng.

**Yêu cầu:** Viết hai nhóm câu hỏi: (a) những câu hỏi cần trả lời **ngay** để quyết định cơ hội có đáng ưu tiên; (b) những câu hỏi có thể giải quyết **gần lúc bắt đầu triển khai**.

**Gợi ý:** Ngay lúc này cần biết nhóm học viên nào bỏ dở, nguyên nhân nào đã được quan sát, tác động mong muốn, rủi ro quyền riêng tư và thứ tự với cơ hội khác. Chi tiết mẫu thông báo, vị trí nút hoặc từng kịch bản lỗi có thể tiếp tục làm rõ khi giải pháp được chọn; riêng nghĩa vụ đồng ý nhận thông báo cần nhận diện từ sớm.

### Bài tập 2 — Tìm câu hỏi làm thay đổi quyết định

Backlog có story “Cho phép học viên tải video xuống điện thoại”. Nhóm mới có hai dữ kiện: nhiều học viên học khi di chuyển; bản quyền nội dung thay đổi theo khóa học.

**Yêu cầu:** Viết ít nhất sáu câu hỏi, phân loại thành (1) giá trị, (2) chất lượng/vận hành, (3) nghĩa vụ/rủi ro. Chọn ba câu cần trả lời trước khi xây bản thử đầu tiên và giải thích.

**Gợi ý:** Có bao nhiêu người thường mất mạng? Có nội dung nào được phép tải? Dữ liệu lưu trong bao lâu? Quyền truy cập bị thu hồi xử lý ra sao? Dung lượng và chi phí thế nào? Làm sao quan sát lỗi tải?

### Bài tập 3 — Viết lại yêu cầu bằng ví dụ

Yêu cầu ban đầu:

> “Hệ thống phải tự động đồng bộ tiến độ thật nhanh và chính xác.”

**Yêu cầu:** Viết một user story và ít nhất bốn tình huống Given–When–Then (thành công, chưa có tiến độ, lỗi mạng, khác tài khoản). Chỉ ra một giả định còn mở về quy tắc xung đột mà chưa nên tự ý kết luận.

**Gợi ý:** Không tự chọn ngưỡng “nhanh” khi chưa biết thiết bị, tải và mục tiêu. Trình bày cách sẽ xác nhận tiêu chí hiệu năng với các bên liên quan.

### Bài tập 4 — Đánh giá có nên bắt đầu Sprint Item

Một story có mục tiêu người dùng rõ, luồng chính đã được xác nhận, nhưng quy tắc xử lý giao dịch thanh toán gửi lại chưa được thống nhất. Product Owner muốn bắt đầu vì “chỉ còn một trường hợp nhỏ”.

**Yêu cầu:** Phân tích rủi ro, đề xuất câu hỏi và bằng chứng cần có, quyết định có thể bắt đầu phần nào trước khi giải đáp. Nêu cách giữ tiến độ mà không đánh đổi tính toàn vẹn giao dịch.

**Gợi ý:** Gửi lại yêu cầu có thể tạo thanh toán trùng hoặc cấp quyền học sai; đó là rủi ro cốt lõi. Đội có thể thực hiện hoạt động khám phá, test contract, hoặc lát cắt độc lập không đi vào luồng thanh toán nguy hiểm; không đánh dấu increment hoàn tất nếu tiêu chí an toàn chưa đạt.

### Bài tập 5 — Tổ chức một cuộc refinement 20 phút

Chia vai Product Owner, Developer, Tester và người dùng đại diện. Lấy story “Học viên tiếp tục bài trên thiết bị khác”.

1. Phút 1–3: làm rõ quyết định cần ra và outcome.
2. Phút 4–9: thảo luận ví dụ luồng chính và ngoại lệ quan trọng.
3. Phút 10–14: ghi giả định, rủi ro/phụ thuộc và câu hỏi chưa có lời giải.
4. Phút 15–18: chọn lát cắt nhỏ nhất có thể kiểm chứng, xác nhận tiêu chí bắt đầu.
5. Phút 19–20: ghi quyết định, người phụ trách và thời điểm xem lại.

**Tiêu chí đánh giá:** Sau cuộc trao đổi, người không dự họp vẫn hiểu **quyết định gì đã được đưa ra, bằng chứng nào hỗ trợ và điều gì còn mở**. Không chấm điểm theo số trang tài liệu.

## 16. Checklist trước quyết định sắp tới

Không cần điền mọi mục cho mọi yêu cầu; chọn những câu hỏi liên quan đến mức rủi ro và loại quyết định.

- [ ] Tôi có nêu rõ **quyết định sắp tới** là đầu tư, ưu tiên, triển khai, kiểm thử hay phát hành?
- [ ] Có biết người dùng, vấn đề, giá trị/outcome và liên hệ với mục tiêu sản phẩm?
- [ ] Có phân biệt dữ kiện đã quan sát, giả định, câu hỏi mở và rủi ro?
- [ ] Những câu hỏi chưa trả lời có thể **làm đổi quyết định, kiến trúc, chi phí hoặc an toàn** đã được ưu tiên xử lý?
- [ ] Người có thông tin và quyền quyết định đã tham gia ở mức cần thiết?
- [ ] Với phần sắp triển khai, có ví dụ luồng chính, ngoại lệ quan trọng và tiêu chí chấp nhận đủ để kiểm chứng?
- [ ] Có làm rõ điều kiện bảo mật, dữ liệu, hiệu năng, vận hành, hợp đồng hoặc kiểm định khi liên quan?
- [ ] Yêu cầu có thể chia thành lát cắt giá trị đủ nhỏ mà vẫn đáp ứng chất lượng?
- [ ] Việc chưa biết có phương án tìm hiểu cụ thể: phỏng vấn, prototype, spike, test hay thử nghiệm?
- [ ] Quyết định và lý do được ghi ở nơi nhóm tra cứu được; có người chịu trách nhiệm và thời điểm xem lại?

## 17. Tổng kết

**Làm rõ yêu cầu đúng mức** là một kỹ năng ra quyết định trong Agile: thu thập đủ thông tin để hành động có trách nhiệm ở thời điểm hiện tại, đồng thời giữ khả năng học hỏi và thay đổi khi có phản hồi mới.

- **Nói rõ quyết định trước khi yêu cầu chi tiết:** làm rõ để đầu tư, để ưu tiên, để triển khai hay để xác nhận/phát hành.
- **Làm rõ theo rủi ro:** yêu cầu liên quan đến dữ liệu, tiền bạc, an toàn, pháp lý và phụ thuộc khó đảo ngược cần được chuẩn bị sớm hơn.
- **Dùng ví dụ và hội thoại:** user story, 3C, Three Amigos, tiêu chí chấp nhận và phép thử giúp mọi người có cùng cách hiểu.
- **Chia nhỏ theo giá trị:** lát cắt hoàn chỉnh giúp kiểm tra giả thuyết bằng increment, trong khi spike/prototype giúp giải quyết bất định.
- **Gắn với dòng công việc:** Scrum hỗ trợ refinement và phản hồi qua Sprint; Kanban làm rõ chính sách kéo việc và trở ngại; thực hành XP giúp kiểm tra thay đổi an toàn.
- **Không nhầm chắc chắn với chi tiết:** một tài liệu dài vẫn có thể sai; điều quan trọng là bằng chứng, những giả định còn mở và hành động tiếp theo.

Khi đứng trước một yêu cầu chưa hoàn chỉnh, hãy tự hỏi: **“Để đưa ra quyết định sắp tới một cách an toàn và có cơ sở, điều gì nhất thiết phải biết ngay, điều gì cần kiểm chứng và điều gì có thể tiếp tục học sau?”**
