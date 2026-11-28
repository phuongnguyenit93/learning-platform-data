# Viết requirement kiểm chứng được

## 1. Từ mong muốn bảo mật đến điều có thể đánh giá

“Hệ thống phải an toàn”, “phân quyền chặt chẽ” hoặc “phục hồi nhanh” thể hiện mong muốn bảo vệ nhưng chưa cho người triển khai và người đánh giá một cách hiểu thống nhất. Nếu mỗi nhóm tự diễn giải, hệ thống có thể vượt qua kiểm thử đã viết mà vẫn không giải quyết rủi ro ban đầu.

Một **yêu cầu bảo mật kiểm chứng được** mô tả đủ rõ đối tượng, phạm vi, điều kiện và kết quả cần đạt để người đánh giá có thể dùng bằng chứng phù hợp kết luận yêu cầu được đáp ứng hay chưa.

Ví dụ:

- Phát biểu ban đầu: “thu hồi phiên nhanh khi khóa tài khoản”.
- Phát biểu có thể kiểm chứng: “không muộn hơn 60 giây sau khi thao tác khóa tài khoản được hệ thống quản lý danh tính xác nhận thành công, mọi yêu cầu mới dùng phiên hoặc token cũ của tài khoản đó đến API quản trị phải bị từ chối”.
- Nội dung còn phải định nghĩa: API nào thuộc phạm vi, cách xác định mốc thời gian, xử lý yêu cầu đang chạy và bằng chứng nào chứng minh không có tác động quản trị.

Ngưỡng **60 giây** trong bài là giả định minh họa, không phải mặc định của tiêu chuẩn. Giá trị thực tế cần có căn cứ rủi ro, nhu cầu nghiệp vụ và xác nhận của người có trách nhiệm.

Trong chương **Requirement lifecycle**, viết yêu cầu kiểm chứng được là bước chuyển từ thông tin đã thu thập sang một thỏa thuận kỹ thuật có thể thiết kế, triển khai và đánh giá. Mỗi yêu cầu cần giữ liên kết với mục tiêu an toàn thông tin, kịch bản đe dọa và rủi ro đã làm phát sinh nó.

[NASA — Technical Requirements Definition](https://www.nasa.gov/reference/4-2-technical-requirements-definition/) xem tính kiểm chứng được là một tiêu chí của yêu cầu: cần đủ thông tin để có thể xác minh sau khi sản phẩm được triển khai. Bài học áp dụng nguyên tắc này vào yêu cầu bảo mật phần mềm.

Sau bài học, người học cần có thể:

1. Chuyển một phát biểu mơ hồ thành yêu cầu có phạm vi và kết quả rõ.
2. Phân biệt yêu cầu, lý do, giải pháp, tiêu chí chấp nhận và thủ tục kiểm tra.
3. Viết yêu cầu về hành vi được phép, bị cấm, ngoại lệ và lỗi phụ thuộc.
4. Đặc tả ngưỡng đo mà không để trống cách tính hoặc điều kiện đo.
5. Xác định bằng chứng cần có cho xác thực, phân quyền, dữ liệu, logging và phục hồi.

## 2. “Kiểm chứng được” có nghĩa gì?

### 2.1. Có cơ sở để phân biệt đạt và không đạt

Một yêu cầu đủ rõ khi người đánh giá trả lời được:

- Đang đánh giá thành phần, giao diện, dữ liệu và môi trường nào?
- Hành vi được kích hoạt trong điều kiện nào?
- Chủ thể nào được phép hoặc không được phép?
- Kết quả đúng phải quan sát được ở đâu?
- Điều gì làm kết luận không đạt?
- Cần loại bằng chứng nào và những giới hạn của bằng chứng là gì?

Nếu không trả lời được, vấn đề có thể nằm ở yêu cầu chứ không chỉ ở công cụ kiểm thử.

“Không có lỗ hổng” không xác định được phạm vi lỗi, giả định đe dọa hoặc phương pháp chứng minh. Một nhóm yêu cầu về kiểm soát cụ thể cùng kế hoạch đánh giá phù hợp tạo cơ sở thực tế hơn để kết luận về mức đáp ứng.

### 2.2. Không phải yêu cầu nào cũng cần con số

Các yêu cầu sau có thể kiểm chứng bằng kết quả phân loại:

- Người dùng tenant A không được đọc tài liệu thuộc tenant B khi không có quyền được cấp theo quy trình đã xác định.
- Token truy cập không được xuất hiện trong các trường log thuộc phạm vi đã định nghĩa.
- Khi không xác định được quyền đối với tài nguyên, hệ thống không được cấp quyền truy cập tài nguyên đó.

Các yêu cầu về độ trễ, thời hạn hoặc khả năng phục hồi thường cần ngưỡng định lượng:

- Thu hồi quyền có hiệu lực trong thời gian tối đa đã thống nhất.
- Sự kiện được chuyển đến kho log trong giới hạn thời gian đã định nghĩa.
- Khôi phục chức năng thiết yếu trong RTO và giới hạn mất dữ liệu trong RPO.

Không thêm tỷ lệ hoặc thời hạn chỉ để câu có vẻ đo được. Mỗi ngưỡng phải giải quyết một nhu cầu bảo vệ cụ thể.

### 2.3. Kiểm chứng và xác nhận nhu cầu là hai việc liên quan

- **Kiểm chứng việc đáp ứng yêu cầu:** hệ thống có thực hiện điều đã đặc tả không?
- **Xác nhận yêu cầu phù hợp:** điều đã đặc tả có giải quyết đúng nhu cầu và rủi ro của các bên liên quan không?

Ví dụ, hệ thống thu hồi phiên trong 60 giây đúng như yêu cầu nhưng chủ dữ liệu thực sự cần chặn một hành động rút tiền trước khi nó được xác nhận. Yêu cầu có thể đã được triển khai đúng mà vẫn chưa bảo vệ đúng thời điểm quan trọng.

Vì vậy, trước khi chốt yêu cầu cần kiểm tra cả tính rõ ràng lẫn lý do tồn tại của nó.

## 3. Phân biệt các phần của một đặc tả

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Mục tiêu bảo vệ | Cần tránh tổn thất nào? | Ngăn lộ hồ sơ dự án giữa các tenant |
| Kịch bản đe dọa | Điều xấu có thể xảy ra bằng cách nào? | Người đã đăng nhập đổi mã tài liệu để tải tệp của tenant khác |
| Yêu cầu | Hệ thống phải có hành vi hoặc thuộc tính nào? | Chỉ trả nội dung cho chủ thể đáp ứng chính sách truy cập của tài liệu |
| Lý do | Vì sao yêu cầu cần thiết? | Tệp chứa thông tin thuộc phạm vi khách hàng riêng biệt |
| Ràng buộc | Điều kiện nào phải tuân theo khi thiết kế? | Tích hợp với IdP do tổ chức chỉ định |
| Giải pháp thiết kế | Sẽ thực hiện yêu cầu bằng cách nào? | Dùng thành phần quyết định quyền và cơ chế thực thi phù hợp |
| Tiêu chí chấp nhận | Những quan sát nào đủ để kết luận trong phạm vi đã định? | Có trường hợp đúng quyền, sai vai trò, chéo tenant và không xác định được quyền |
| Thủ tục kiểm tra | Các bước đánh giá cụ thể là gì? | Tạo hai tenant, cấp quyền, gửi yêu cầu và kiểm tra phản hồi lẫn tác động |
| Bằng chứng | Kết quả đánh giá được lưu ở đâu? | Báo cáo kiểm thử, cấu hình, phân tích mã và log đã giảm dữ liệu nhạy cảm |

Một yêu cầu có thể tham chiếu chính sách hoặc cấu hình đã được kiểm soát phiên bản. Tham chiếu đó phải truy cập được, rõ phạm vi và chứa các giá trị cần thiết. Câu “mã hóa theo chính sách phù hợp” vẫn mơ hồ nếu không xác định được chính sách nào.

Không đưa toàn bộ các bước dùng một công cụ cụ thể vào câu yêu cầu. Có thể thay công cụ đánh giá mà vẫn giữ nguyên kết quả bảo vệ cần đạt.

## 4. Cấu trúc của một yêu cầu kiểm chứng được

Có thể dùng cấu trúc:

**Trong [phạm vi], khi [điều kiện hoặc sự kiện], [hệ thống/thành phần] phải [hành vi bảo vệ] đối với [chủ thể, hành động, tài nguyên], đáp ứng [kết quả và giới hạn cần thiết].**

Không cần ép mọi câu theo một mẫu ngữ pháp cứng. Mục đích là phát hiện những phần đang bị bỏ trống.

| Thành phần | Điều cần làm rõ | Lỗi thường gặp |
| --- | --- | --- |
| Phạm vi | Giao diện, dữ liệu, môi trường và phiên bản áp dụng | Chỉ ghi “ứng dụng” nhưng bỏ tác vụ nền và tải tệp |
| Chủ thể chịu trách nhiệm | Thành phần hoặc hệ thống phải đáp ứng | Ghi “người dùng cần được bảo vệ” mà không rõ ai thực hiện |
| Điều kiện | Trạng thái hoặc sự kiện làm yêu cầu có hiệu lực | Không xét token cũ, quyền thay đổi hoặc dịch vụ lỗi |
| Hành vi | Một nghĩa vụ bảo vệ có ý nghĩa độc lập | Ghép mã hóa, logging, backup và MFA vào cùng một câu |
| Đối tượng | Chủ thể, hành động, tài nguyên liên quan | “Dữ liệu nhạy cảm” nhưng không có danh mục hoặc tiêu chí |
| Kết quả | Quan sát được cho phép, từ chối, khôi phục hoặc cảnh báo | Chỉ quy định mã HTTP, không xét dữ liệu đã bị trả |
| Giới hạn | Ngưỡng, thời hạn, độ trễ hoặc điều kiện chất lượng | “Nhanh”, “đủ”, “thường xuyên” |
| Ngoại lệ | Điều kiện áp dụng, người có thẩm quyền và giới hạn | “Trừ khi cần thiết” |
| Tham chiếu | Chính sách, nguồn, rủi ro và phiên bản | Dẫn tài liệu không có tên hoặc đã lỗi thời |

### Một nghĩa vụ chính cho mỗi mã yêu cầu

Câu “hệ thống phải dùng MFA, mã hóa dữ liệu, ghi log và phục hồi trong bốn giờ” có thể được đáp ứng một phần nhưng không có cách quản lý kết quả rõ ràng. Nên tách thành các yêu cầu độc lập và liên kết chúng với mục tiêu chung.

Một yêu cầu vẫn có thể có nhiều tiêu chí chấp nhận để kiểm tra cùng một nghĩa vụ ở các điều kiện khác nhau. Ví dụ, chính sách cách ly tenant cần được đánh giá trên API chi tiết, tìm kiếm và tải tệp; các tiêu chí đó hỗ trợ cùng một thuộc tính bảo vệ.

Hướng dẫn về sự rõ ràng và một ý chính trong mỗi yêu cầu cũng xuất hiện trong [NASA Systems Engineering Handbook — Requirements Validation Checklist](https://www.nasa.gov/reference/system-engineering-handbook-appendix/).

## 5. Từ câu mơ hồ đến yêu cầu có thể đánh giá

Các phát biểu trong bảng là ví dụ về cách làm rõ. Những phạm vi và ngưỡng minh họa cần được điều chỉnh theo hệ thống thực tế.

| Phát biểu ban đầu | Phần còn thiếu | Cách viết cụ thể hơn |
| --- | --- | --- |
| Hệ thống phải phân quyền chặt chẽ | Ai, tài nguyên nào, quy tắc nào? | Với yêu cầu đọc tài liệu, chỉ trả nội dung khi chủ thể thuộc tenant của tài liệu và có vai trò được phép trên dự án sở hữu tài liệu |
| Phải ghi đầy đủ log | Sự kiện, trường, dữ liệu cấm và điểm quan sát? | Mỗi thay đổi quyền dự án phải tạo sự kiện chứa chủ thể, tenant, dự án, quyền trước/sau, thời gian, kết quả và mã tương quan theo lược đồ đã xác định |
| Phiên phải hết hạn nhanh | Hết hạn do nhàn rỗi, thời gian tuyệt đối hay bị thu hồi? | Với API quản trị, yêu cầu mới dùng phiên của tài khoản đã khóa phải bị từ chối không muộn hơn giới hạn thu hồi đã xác nhận |
| Dữ liệu phải được mã hóa | Dữ liệu nào, khi truyền hay khi lưu, bằng chính sách nào? | Các vị trí lưu trong danh mục dữ liệu thuộc phạm vi phải dùng cấu hình mã hóa được liệt kê trong baseline đã duyệt; đánh giá cả bản chính và backup |
| Backup phải an toàn | Quyền đọc, mã hóa, tính toàn vẹn hay khả năng phục hồi? | Tách yêu cầu bảo vệ backup khỏi yêu cầu khôi phục dịch vụ và dữ liệu theo RTO/RPO |
| Không được lộ thông tin | Lộ cho ai, qua đường nào, thông tin nào? | Phản hồi cho chủ thể không đủ quyền không được chứa nội dung tài liệu, liên kết tải hoặc thuộc tính bị hạn chế đã được liệt kê |
| Phải chống mọi cuộc tấn công | Mô hình đe dọa và giới hạn ở đâu? | Xác định từng kịch bản gây hại, thuộc tính cần bảo vệ và yêu cầu tương ứng |
| Phải tuân thủ tiêu chuẩn | Phiên bản, mục áp dụng, cách đánh giá? | Ghi danh mục yêu cầu áp dụng, phiên bản tham chiếu, ánh xạ sang hệ thống và bằng chứng cần có |

Không biến một câu rất ngắn thành một đoạn dài chứa mọi điều về bảo mật. Khi cần nhiều nghĩa vụ, tách mã và dùng bảng phạm vi, chính sách hoặc tài liệu tham chiếu để giữ tính rõ ràng.

## 6. Ví dụ xuyên suốt: bảo vệ tài liệu dự án nhiều tenant

### 6.1. Bối cảnh và chính sách nghiệp vụ

Giả sử nền tảng quản lý tài liệu phục vụ nhiều tổ chức khách hàng. Mỗi tài liệu thuộc một dự án; mỗi dự án thuộc đúng một tenant.

Chính sách giả định của ví dụ:

- Viewer, Editor và Owner của một dự án được đọc tài liệu của dự án đó.
- Editor và Owner được thay đổi nội dung theo chính sách chỉnh sửa riêng.
- Người không thuộc tenant của dự án không có quyền đọc chỉ vì biết mã tài liệu.
- Quản trị hạ tầng không tự động có quyền đọc nội dung nghiệp vụ.
- Nếu có hỗ trợ xuyên tenant, quyền đó phải thuộc một quy trình đặc quyền riêng được đặc tả.

Các giao diện cần xem xét gồm danh sách, chi tiết, tìm kiếm, tải tệp, xuất dữ liệu và tác vụ nền liên quan.

### 6.2. Yêu cầu về kiểm soát đọc

**SEC-AC-01 — Giới hạn đọc tài liệu:** Trong các giao diện cung cấp nội dung tài liệu, hệ thống chỉ được trả nội dung khi chủ thể đã được xác thực, thuộc tenant sở hữu tài liệu và có một trong các vai trò Viewer, Editor hoặc Owner trên dự án sở hữu tài liệu. Khi không xác định được một điều kiện cần thiết, hệ thống phải từ chối trả nội dung.

Phạm vi “giao diện cung cấp nội dung” phải có danh mục được quản lý, gồm đường đọc trực tiếp và đường xuất dữ liệu có liên quan. Một đường mới cần được phân tích tác động và đưa vào danh mục trước khi dựa vào kết quả đánh giá cũ.

**SEC-ERROR-01 — Giới hạn thông tin trong phản hồi từ chối:** Với yêu cầu không đáp ứng SEC-AC-01, phản hồi không được chứa nội dung tài liệu, liên kết tải có hiệu lực hoặc các trường metadata bị hạn chế theo danh mục dữ liệu của hệ thống.

Yêu cầu thứ hai tách vấn đề lộ dữ liệu qua phản hồi lỗi. Không bắt buộc mọi ứng dụng dùng cùng mã trạng thái HTTP; hợp đồng API cần quy định cách biểu diễn từ chối mà vẫn đáp ứng mục tiêu bảo vệ.

### 6.3. Tiêu chí chấp nhận cho SEC-AC-01

| Mã tình huống | Điều kiện | Kết quả cần quan sát |
| --- | --- | --- |
| AC-POS-01 | Chủ thể thuộc đúng tenant, có vai trò Viewer trên đúng dự án | Trả nội dung đúng tài liệu |
| AC-NEG-01 | Chủ thể tenant A dùng mã tài liệu của tenant B | Không trả nội dung |
| AC-NEG-02 | Chủ thể cùng tenant nhưng không có vai trò trên dự án | Không trả nội dung |
| AC-NEG-03 | Token không hợp lệ hoặc không có danh tính được xác nhận | Không trả nội dung |
| AC-NEG-04 | Không xác định được dữ liệu quyền cần thiết | Không cấp quyền từ dữ liệu thiếu |
| AC-PATH-01 | Gọi trực tiếp đường tải tệp thay vì qua giao diện web | Áp dụng cùng chính sách đọc |
| AC-PATH-02 | Tìm kiếm hoặc xuất dữ liệu chứa nhiều tài liệu | Không đưa tài liệu ngoài phạm vi quyền vào kết quả |

Phải có tình huống được phép để phát hiện một triển khai từ chối mọi thứ. Đồng thời phải có tình huống bị từ chối để phát hiện triển khai chỉ kiểm tra người dùng đã đăng nhập.

Mã trạng thái 403 chưa đủ chứng minh yêu cầu được đáp ứng nếu phần thân, tệp đính kèm hoặc phản hồi trước đó đã chứa dữ liệu bị cấm.

### 6.4. Minh họa một kịch bản kiểm tra

~~~gherkin
Feature: Document read authorization

  Scenario: A user cannot read a document from another tenant
    Given a valid user belongs to tenant A
    And a document belongs to a project in tenant B
    And the user has no separately authorized cross-tenant access
    When the user requests the document through a content endpoint
    Then the document content is not returned
    And no effective download link is returned
~~~

Kịch bản là một cách diễn đạt tiêu chí, chưa phải toàn bộ kế hoạch đánh giá. Cần bao phủ các đường truy cập và các tổ hợp quyền có ý nghĩa, đồng thời kiểm tra thiết kế hoặc mã khi cần để đánh giá phạm vi thực thi.

## 7. Viết yêu cầu về xác thực, phiên và thay đổi quyền

### 7.1. Xác thực đặc quyền phải gắn với hành động được bảo vệ

Phát biểu yếu:

> Người quản trị phải dùng MFA.

Phát biểu cụ thể hơn:

**SEC-AUTH-01:** Trước khi cho phép hành động quản trị thuộc danh mục ADMIN-ACTIONS-v1, hệ thống phải xác minh phiên có bằng chứng xác thực đa yếu tố hợp lệ từ IdP được cấu hình tin cậy. Phiên không có hoặc có bằng chứng không hợp lệ không được thực hiện hành động đó.

Để đánh giá, cần xác định:

- Danh mục hành động quản trị cụ thể.
- Thuộc tính hoặc bằng chứng mà IdP cung cấp và điều kiện hợp lệ.
- Các đường đăng nhập thông thường, khôi phục và truy cập trực tiếp.
- Tài khoản khẩn cấp hoặc tài khoản dịch vụ nếu có.
- Cách quan sát rằng hành động quản trị không xảy ra.

Hiển thị màn hình MFA không chứng minh phía máy chủ đã kiểm tra bằng chứng. Tiêu chí cần đánh giá hành vi thực thi ở nơi hành động được quyết định.

Tên ADMIN-ACTIONS-v1 là tham chiếu minh họa. Trong hồ sơ thực tế, tài liệu tương ứng phải tồn tại và có nội dung đã được xác nhận.

### 7.2. Định nghĩa mốc và giới hạn thu hồi

**SEC-SESSION-01:** Với API quản trị, không muộn hơn 60 giây sau khi thao tác khóa tài khoản được hệ thống quản lý danh tính xác nhận thành công, mọi yêu cầu mới dùng phiên hoặc token đã cấp cho tài khoản đó phải bị từ chối thực hiện hành động quản trị.

Điều kiện đo của ví dụ:

- Mốc bắt đầu là xác nhận thành công của thao tác khóa, không phải lúc người dùng bấm nút.
- Mốc kết thúc là thời điểm yêu cầu mới được tiếp nhận tại biên API thuộc phạm vi.
- Các nút xử lý đang hoạt động và các loại phiên được hỗ trợ đều thuộc phạm vi.
- Phương pháp đo phải kiểm soát sai lệch đồng hồ và độ chính xác cần thiết.
- Không dùng giá trị trung bình để thay cho giới hạn tối đa 60 giây.
- Một yêu cầu mới sau giới hạn vẫn tạo được tác động quản trị là kết quả không đạt.

SEC-SESSION-01 chưa quyết định cách xử lý yêu cầu đã bắt đầu trước khi khóa tài khoản. Điều đó cần yêu cầu riêng nếu có tác động đến nghiệp vụ hoặc rủi ro.

### 7.3. Đừng bỏ quên tác vụ dài

**SEC-JOB-01:** Trước khi bàn giao bản xuất tài liệu cho người nhận, tác vụ xuất phải kiểm tra lại quyền hiện hành của người nhận đối với từng tài liệu. Tài liệu không còn được phép đọc không được xuất hiện trong phần dữ liệu bàn giao.

Đây là yêu cầu về thời điểm bảo vệ. Chỉ kiểm tra quyền khi xếp hàng có thể không đáp ứng nó nếu quyền đã bị thu hồi trong lúc tác vụ chờ hoặc chạy.

Cần đặc tả thêm hành vi với bản xuất đã tạo nhưng chưa bàn giao, thông báo lỗi và tệp tạm nếu các vấn đề đó thuộc phạm vi. Mỗi nghĩa vụ nên có mã riêng để theo dõi kết quả.

## 8. Viết yêu cầu bảo vệ dữ liệu và logging

### 8.1. Đặc tả phạm vi dữ liệu trước khi nói về mã hóa

“Dữ liệu được mã hóa” có thể chỉ đề cập database, trong khi tệp xuất và backup vẫn chưa được xem xét.

Một đặc tả cần xác định:

1. Danh mục dữ liệu và nơi lưu thuộc phạm vi.
2. Kênh truyền hoặc trạng thái lưu trữ cần bảo vệ.
3. Baseline cấu hình mật mã và phiên bản áp dụng.
4. Trách nhiệm quản lý khóa và quyền sử dụng khóa.
5. Cách kiểm tra cấu hình thực tế, vị trí phát sinh mới và bản sao.
6. Các giới hạn không được giải quyết chỉ bằng mã hóa.

Ví dụ cấu trúc:

**SEC-DATA-01:** Mỗi vị trí lưu dữ liệu trong DATA-STORES-v1 phải sử dụng một cấu hình mã hóa nằm trong CRYPTO-BASELINE-v1 đã được phê duyệt cho loại vị trí đó. Vị trí lưu mới không được đưa vào xử lý dữ liệu thuộc phạm vi trước khi được bổ sung và xác minh theo cùng cơ chế.

Đây là mẫu yêu cầu có tham chiếu. Nó chỉ đủ kiểm chứng khi DATA-STORES-v1 liệt kê các vị trí thực tế và CRYPTO-BASELINE-v1 liệt kê cấu hình được phép cùng điều kiện áp dụng. Hai tên tài liệu đứng một mình chưa tạo ra đặc tả hoàn chỉnh.

Mã hóa lưu trữ không chứng minh người dùng ứng dụng đã được phân quyền đúng. Quyền truy cập dữ liệu và quyền sử dụng khóa cần các yêu cầu tương ứng.

### 8.2. Tách nội dung sự kiện khỏi việc chuyển và lưu log

Có thể chia một mong muốn “logging đầy đủ” thành các nghĩa vụ:

| Mã minh họa | Nghĩa vụ |
| --- | --- |
| SEC-LOG-01 | Tạo sự kiện cho nhóm hành động đã xác định với các trường bắt buộc |
| SEC-LOG-02 | Chuyển sự kiện đến điểm tiếp nhận trong giới hạn đã định |
| SEC-LOG-03 | Ngăn đưa các loại bí mật và dữ liệu bị cấm vào log |
| SEC-LOG-04 | Giới hạn quyền đọc, sửa hoặc xóa dữ liệu log |
| SEC-LOG-05 | Phát hiện và xử lý gián đoạn logging theo chính sách vận hành |

Ví dụ:

**SEC-LOG-01:** Mỗi thay đổi thành viên hoặc vai trò dự án phải tạo một sự kiện theo AUDIT-EVENT-v1, chứa mã chủ thể, tenant, dự án, quyền trước/sau, thời gian, kết quả và mã tương quan của thao tác.

**SEC-LOG-03:** Các trường sự kiện thuộc AUDIT-EVENT-v1 không được chứa mật khẩu, giá trị token truy cập, cookie phiên hoặc nội dung tệp tài liệu.

Để kiểm tra SEC-LOG-03, có thể dùng giá trị đánh dấu trong dữ liệu thử và xem xét các nhánh thành công, bị từ chối, lỗi hoặc ngoại lệ. Chỉ kiểm tra một dòng log của luồng thành công không đủ đánh giá mọi nhánh quan trọng.

Đối với quyền riêng tư, mã người dùng hoặc mã tài nguyên vẫn có thể liên kết đến cá nhân. Không tự coi chúng là dữ liệu vô danh chỉ vì không chứa tên.

### 8.3. Nêu rõ hành vi khi logging lỗi

Câu “nếu mất log thì vẫn hoạt động bình thường” hoặc “mất log thì dừng toàn hệ thống” đều cần phân tích tác động.

Cần xác định riêng:

- Hành động nào được tiếp tục.
- Hành động nào phải bị chặn nếu không ghi nhận được sự kiện cần thiết.
- Có cho phép bộ đệm không, giới hạn và cách phát hiện đầy bộ đệm.
- Ai nhận cảnh báo và phản ứng trong thời gian nào.
- Cách xử lý khoảng trống bằng chứng sau phục hồi.

Lựa chọn phải dựa vào loại hành động và nhu cầu nghiệp vụ. Không mặc định cùng một chính sách lỗi cho thao tác đọc công khai và thao tác cấp quyền đặc quyền.

## 9. Viết yêu cầu phục hồi có điểm bắt đầu và kết thúc

Phát biểu “backup mỗi giờ và phục hồi nhanh” chưa xác định được dịch vụ nào cần hoạt động trở lại hoặc dữ liệu được phép mất đến đâu.

Trong ví dụ, giả sử tổ chức đã xác nhận:

- RTO của chức năng đọc và cập nhật tài liệu thiết yếu: 4 giờ.
- RPO cho dữ liệu thuộc phạm vi: 1 giờ.
- Tình huống đánh giá: mất kho dữ liệu chính; vùng phục hồi cùng các nguồn backup được xác định vẫn khả dụng.
- Những tình huống mất đồng thời các phụ thuộc khác được phân tích trong phạm vi khác.

Các giá trị và điều kiện này là giả định của bài học.

**SEC-REC-01:** Trong tình huống phục hồi đã xác định, hệ thống phải khôi phục chức năng đọc và cập nhật tài liệu thiết yếu trong tối đa 4 giờ, tính từ mốc dịch vụ thuộc phạm vi mất khả năng sử dụng theo tiêu chí đã thống nhất đến khi bộ kiểm tra chấp nhận phục hồi hoàn tất.

**SEC-REC-02:** Dữ liệu khôi phục phải đáp ứng RPO tối đa 1 giờ theo mốc sự cố và cách xác định điểm dữ liệu nhất quán đã thống nhất; các dữ liệu đã được hệ thống xác nhận ghi nhận trước giới hạn đó phải được kiểm tra trong kết quả khôi phục.

Trong đó:

- **RTO — Recovery Time Objective:** mục tiêu về thời gian khôi phục hoạt động.
- **RPO — Recovery Point Objective:** mục tiêu về khoảng mất dữ liệu có thể chấp nhận, thể hiện bằng thời gian.

Hồ sơ đánh giá cần định nghĩa rõ điểm dữ liệu nhất quán đối với database, tệp và các hệ thống phụ thuộc. Một database khôi phục được nhưng tham chiếu đến tệp không tồn tại có thể chưa đáp ứng chức năng phục hồi.

Bộ kiểm tra chấp nhận nên bao gồm:

- Người dùng hợp lệ thực hiện được các chức năng thiết yếu.
- Quyền truy cập và cách ly tenant vẫn đúng.
- Dữ liệu mẫu kiểm tra có tính toàn vẹn và quan hệ phù hợp.
- Khóa và thông tin cấu hình cần thiết đã khả dụng đúng quyền.
- Những giới hạn hoặc dữ liệu chưa phục hồi được ghi nhận.

Mốc đo không nên bắt đầu muộn ở thời điểm kỹ sư bắt tay vào thao tác nếu mục tiêu nghiệp vụ bao gồm cả thời gian phát hiện và huy động. Cách đo phải được thống nhất trước diễn tập.

## 10. Đặc tả phép đo để tránh kết quả “đạt” gây hiểu nhầm

### 10.1. Một ngưỡng cần đi cùng định nghĩa

Với yêu cầu định lượng, cần ghi:

| Nội dung | Ví dụ điều phải làm rõ |
| --- | --- |
| Đại lượng | Độ trễ tiếp nhận log, thời gian thu hồi hay thời gian phục hồi? |
| Đơn vị | Giây, phút, số yêu cầu hay số bản ghi? |
| Mốc bắt đầu/kết thúc | Phát sinh sự kiện đến tiếp nhận bền vững tại kho log |
| Phạm vi mẫu | Loại sự kiện, loại chủ thể, giao diện và môi trường |
| Tải và trạng thái | Tải dự kiến, trạng thái suy giảm hoặc lỗi phụ thuộc |
| Cửa sổ đo | Đo trong lần đánh giá, khoảng vận hành hay từng sự kiện |
| Cách tính | Giá trị tối đa, tỷ lệ hoặc phân vị |
| Ngoại lệ | Trường hợp nào được loại khỏi phép đo và căn cứ |
| Bằng chứng | Nguồn thời gian, bản ghi đầu vào/đầu ra và phương pháp đối chiếu |
| Điều kiện không đạt | Ngưỡng nào bị vượt, thiếu dữ liệu nào làm chưa thể kết luận |

“P99 không quá 60 giây” và “mọi sự kiện không quá 60 giây” là hai nghĩa vụ khác nhau. Yêu cầu về phân vị không tự đặt giới hạn cho phần còn lại.

### 10.2. Ví dụ độ trễ log

Một đề xuất minh họa có thể quy định: ít nhất 99% sự kiện thay đổi quyền trong mỗi cửa sổ đo 60 phút được kho log tiếp nhận bền vững trong vòng 60 giây; mọi sự kiện còn lại phải được tiếp nhận trong 300 giây.

Để dùng được, phải làm rõ thêm:

- Điểm phát sinh và điểm tiếp nhận bền vững.
- Cách đối chiếu số sự kiện duy nhất, tránh đếm bản sao như sự kiện mới.
- Tải thử và cấu hình hệ thống thuộc phạm vi.
- Xử lý sự kiện bị mất, thiếu timestamp hoặc không đối chiếu được.
- Sai lệch đồng hồ và cách tính ở ranh giới cửa sổ.
- Cách đánh giá khi số mẫu rất nhỏ hoặc không có sự kiện.

Không loại sự kiện bị mất khỏi mẫu chỉ vì không có thời gian kết thúc. Theo mục tiêu bảo vệ, đó là thiếu bằng chứng hoặc vi phạm cần được xử lý theo tiêu chí đã xác định.

Các tỷ lệ ở trên chỉ phục vụ minh họa kỹ thuật đặc tả. Không dùng tỷ lệ thành công tương tự để cho phép một phần yêu cầu trái quyền đọc được dữ liệu. Một ca truy cập trái quyền thành công là phát hiện bảo mật, không phải sai số bình thường được bỏ qua.

### 10.3. Thử nghiệm và vận hành phải có quan hệ rõ

Một lần thử trong môi trường kiểm tra chỉ cung cấp bằng chứng cho điều kiện đã thực hiện. Nếu yêu cầu áp dụng liên tục trong vận hành, cần có kế hoạch theo dõi và bằng chứng tương ứng.

Khi môi trường đánh giá khác môi trường thật, phải nêu khác biệt có thể ảnh hưởng kết quả: số tenant, tải, cấu hình khóa, topology, độ trễ phụ thuộc hoặc cơ chế quản lý phiên.

## 11. Chọn bằng chứng phù hợp với điều cần chứng minh

[NIST SP 800-53A Rev. 5](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53Ar5.pdf) mô tả ba phương pháp đánh giá: examine, interview và test. Có thể phối hợp xem xét đối tượng đánh giá, trao đổi để làm rõ và thực hiện kiểm tra trong điều kiện xác định.

Áp dụng vào bài học:

| Điều cần đánh giá | Bằng chứng phù hợp | Giới hạn cần nhận biết |
| --- | --- | --- |
| Chính sách quyền được thực thi trên các đường đọc | Danh mục giao diện, phân tích thiết kế/mã, kiểm thử nhiều vai trò và tenant | Một ca API không chứng minh mọi đường truy cập |
| MFA bảo vệ hành động quản trị | Cấu hình IdP, kiểm tra bằng chứng xác thực và ca bỏ qua/thiếu bằng chứng | Ảnh chụp màn hình MFA không chứng minh kiểm soát phía máy chủ |
| Vị trí lưu dùng cấu hình mã hóa đúng | Kiểm kê, cấu hình triển khai, thông tin khóa và kiểm tra quyền liên quan | Tuyên bố của nhà cung cấp chưa chứng minh cấu hình ứng dụng cụ thể |
| Không đưa token vào log | Kiểm thử giá trị đánh dấu, xem lược đồ, cấu hình và các nhánh ghi log | Tìm chuỗi trong một mẫu nhỏ chưa bao phủ hết nhánh |
| Có thể phục hồi dịch vụ | Diễn tập, mốc thời gian, đối chiếu dữ liệu và chức năng sau phục hồi | Trạng thái “backup thành công” chưa đủ |
| Quy trình truy cập khẩn cấp được quản lý | Hồ sơ cấp quyền, bằng chứng hết hạn, log sử dụng và phỏng vấn người phụ trách | Một tài liệu quy trình không chứng minh đã được thực hiện |

Với mỗi bằng chứng, nên lưu:

- Mã và phiên bản yêu cầu được đánh giá.
- Phiên bản phần mềm, cấu hình và môi trường.
- Dữ liệu và điều kiện thử có ý nghĩa.
- Thời điểm, phương pháp và người thực hiện.
- Kết quả, giới hạn và phát hiện.
- Tham chiếu tới hiện vật được bảo vệ phù hợp.

Không nhất thiết lưu nguyên dữ liệu nhạy cảm để chứng minh kết quả. Cần chọn dữ liệu mẫu, che giảm thông tin và giới hạn quyền truy cập vào bằng chứng.

Một tập kiểm thử hữu hạn hỗ trợ kết luận trong phạm vi đã đánh giá; nó không tự chứng minh không tồn tại mọi lỗ hổng. Khi rủi ro yêu cầu, cần bổ sung phân tích thiết kế, mã, cấu hình hoặc phương pháp có mức bảo đảm cao hơn.

## 12. Bản ghi yêu cầu và truy vết

### 12.1. Mẫu bản ghi

~~~text
Mã: SEC-SESSION-01
Tên: Thu hồi quyền dùng phiên quản trị sau khi khóa tài khoản
Phiên bản: 1.0

Phát biểu:
Không muộn hơn 60 giây sau khi thao tác khóa tài khoản được hệ thống
quản lý danh tính xác nhận thành công, mọi yêu cầu mới dùng phiên
hoặc token cũ đến API quản trị phải bị từ chối thực hiện hành động.

Phạm vi:
- Các API quản trị trong danh mục đã xác nhận.
- Các loại phiên và token được hỗ trợ.
- Các nút xử lý đang hoạt động trong cấu hình đánh giá.

Nguồn:
- Quy trình vô hiệu hóa tài khoản và quyết định ngưỡng của chủ nghiệp vụ.
- Kịch bản tài khoản đã khóa vẫn thực hiện hành động đặc quyền.

Lý do:
Giới hạn thời gian quyền cũ tiếp tục tạo tác động quản trị.

Ý định kiểm chứng:
- Xác định mốc khóa thành công.
- Gửi yêu cầu bằng phiên và token đã cấp trước đó.
- Đánh giá trên các đường xử lý có liên quan.
- Kiểm tra kết quả từ chối và không có tác động nghiệp vụ.

Điều kiện không đạt:
Yêu cầu mới sau giới hạn vẫn thực hiện được hành động quản trị.

Giới hạn:
Yêu cầu đang chạy trước mốc khóa được đặc tả riêng.

Người xác nhận:
Chủ nghiệp vụ và người phụ trách bảo mật theo thẩm quyền của tổ chức.

Bằng chứng:
Liên kết tới kết quả đánh giá của đúng bản phát hành và cấu hình.
~~~

Mẫu trên là ví dụ nội dung tài liệu. Ngưỡng và phạm vi phải được xác nhận thực sự trước khi xem yêu cầu là baseline dùng để nghiệm thu.

### 12.2. Ma trận truy vết ngắn

| Rủi ro | Yêu cầu | Hướng thiết kế cần đáp ứng | Bằng chứng dự kiến |
| --- | --- | --- | --- |
| Đọc tài liệu tenant khác | SEC-AC-01 | Thực thi chính sách trên các đường cung cấp nội dung | Phân tích phạm vi và kiểm thử quyền |
| Rò dữ liệu qua phản hồi từ chối | SEC-ERROR-01 | Hợp đồng lỗi và giới hạn dữ liệu phản hồi | Kiểm tra response, tệp và liên kết |
| Phiên cũ còn quyền sau khi khóa | SEC-SESSION-01 | Cơ chế thu hồi đáp ứng giới hạn thời gian | Dữ liệu thời gian và kiểm tra tác động |
| Tác vụ xuất dùng quyền đã mất | SEC-JOB-01 | Xét quyền tại thời điểm bàn giao | Kiểm tra đổi quyền trong lúc tác vụ chạy |
| Không điều tra được thay đổi quyền | SEC-LOG-01 | Sự kiện theo lược đồ đã xác định | Đối chiếu thao tác và sự kiện |
| Bí mật xuất hiện trong log | SEC-LOG-03 | Loại bỏ dữ liệu cấm ở các nhánh ghi log | Kiểm tra dữ liệu đánh dấu và phân tích mã |
| Gián đoạn hoặc mất dữ liệu vượt mức chấp nhận | SEC-REC-01, SEC-REC-02 | Phương án phục hồi có phụ thuộc và điểm đo rõ | Biên bản diễn tập và đối chiếu dữ liệu |

Một yêu cầu có thể giảm nhiều rủi ro và một rủi ro có thể cần nhiều yêu cầu. Không ép quan hệ một-một nếu điều đó làm mất bản chất.

Khi tham chiếu yêu cầu chuẩn, ghi cả phiên bản. [OWASP ASVS](https://asvs.owasp.org/) hướng dẫn dùng định danh có phiên bản vì mã và nội dung có thể thay đổi giữa các bản.

## 13. Những dấu hiệu cần sửa trước khi chốt đặc tả

- Câu chứa “an toàn”, “đầy đủ”, “thích hợp”, “nhanh” nhưng không có định nghĩa.
- Không biết người nào hoặc thành phần nào phải đáp ứng.
- Không rõ áp dụng cho API, tác vụ nền, tệp trực tiếp hay chỉ giao diện.
- Có ngưỡng nhưng không có điểm đo và điều kiện đo.
- Ghi “không bao giờ” nhưng chưa xác định đối tượng, trạng thái và giới hạn đánh giá.
- Chỉ có ca từ chối, khiến triển khai chặn mọi người vẫn được coi là đạt.
- Chỉ kiểm tra phản hồi, bỏ qua tác động đã xảy ra ở phía sau.
- Dùng con số trung bình cho một yêu cầu về giới hạn tối đa.
- Coi “chưa đủ bằng chứng” là đạt.
- Có ngoại lệ không xác định người quyết định, thời hạn và điều kiện.
- Tham chiếu baseline hoặc chính sách không tìm được nội dung.
- Gộp nhiều nghĩa vụ khiến một phát hiện không xác định được yêu cầu nào chưa đạt.
- Chọn công nghệ nhưng chưa nêu rủi ro hoặc kết quả cần bảo vệ.
- Kết quả chỉ đúng trên bản cũ nhưng không có phân tích tác động thay đổi.

Không cần làm yêu cầu dài hơn chỉ để xử lý các dấu hiệu này. Có thể tách nghĩa vụ, bổ sung bảng phạm vi, định nghĩa thuật ngữ hoặc dẫn đến một tài liệu phiên bản rõ ràng.

## 14. Tiêu chí sẵn sàng để chuyển sang triển khai và đánh giá

Đây là kiểm tra mức rõ của đặc tả, chưa phải kết luận hệ thống đã đáp ứng yêu cầu.

- [ ] Có mã và phiên bản để truy vết.
- [ ] Có nguồn, mục tiêu bảo vệ và rủi ro liên quan.
- [ ] Có một nghĩa vụ chính rõ ràng.
- [ ] Xác định được chủ thể, hành động, tài nguyên và điều kiện cần thiết.
- [ ] Phạm vi bao phủ các đường xử lý liên quan hoặc nêu rõ phần ngoài phạm vi.
- [ ] Có kết quả quan sát được và điều kiện không đạt.
- [ ] Các ngưỡng có căn cứ, đơn vị, điểm đo và cách tính.
- [ ] Có tình huống được phép, bị từ chối, ngoại lệ và lỗi có ý nghĩa.
- [ ] Có cách đánh giá phù hợp, không chỉ dựa vào tuyên bố hoặc ảnh chụp.
- [ ] Tài liệu tham chiếu tồn tại và có phiên bản.
- [ ] Giả định chưa xác nhận không bị trình bày như sự thật.
- [ ] Người có trách nhiệm đã xác nhận nội dung trong phạm vi thẩm quyền.
- [ ] Biết bằng chứng nào phải được tạo và gắn với phiên bản triển khai nào.
- [ ] Có thể xác định phần cần đánh giá lại khi yêu cầu, cấu hình hoặc kiến trúc thay đổi.

## 15. Tài liệu tham khảo

- [NASA — Technical Requirements Definition](https://www.nasa.gov/reference/4-2-technical-requirements-definition/): tính phù hợp, khả thi và kiểm chứng được của yêu cầu.
- [NASA Systems Engineering Handbook — Appendix](https://www.nasa.gov/reference/system-engineering-handbook-appendix/): danh sách kiểm tra về sự rõ ràng và cấu trúc yêu cầu.
- [NIST SP 800-53A Rev. 5 — Assessing Security and Privacy Controls](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53Ar5.pdf): phương pháp thu thập và đánh giá bằng chứng kiểm soát.
- [OWASP Application Security Verification Standard](https://asvs.owasp.org/): yêu cầu kiểm chứng bảo mật ứng dụng và cách tham chiếu phiên bản.
