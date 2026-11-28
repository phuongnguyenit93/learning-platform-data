# Confidentiality

## 1. Confidentiality bảo vệ điều gì?

**Confidentiality — tính bí mật** là thuộc tính bảo đảm thông tin không bị tiết lộ cho chủ thể không được phép. “Chủ thể” có thể là người dùng, tài khoản quản trị, dịch vụ, tác vụ nền hoặc một hệ thống bên ngoài.

Tính bí mật không có nghĩa mọi dữ liệu đều phải được giấu với mọi người. Mục tiêu là **đúng thông tin được tiết lộ cho đúng chủ thể, trong đúng phạm vi và điều kiện được cho phép**.

Ví dụ:

- Nhân viên được đọc hồ sơ khách hàng do mình phụ trách, nhưng không được đọc hồ sơ của doanh nghiệp khác.
- Quản trị viên được quản lý thành viên nhưng không tự động được xem mọi ghi chú riêng trong hồ sơ.
- Worker tạo bản xuất cần đọc một số trường nghiệp vụ, nhưng không cần nhận mật khẩu hay token của người yêu cầu.
- Người vận hành cần biết một thao tác bị lỗi, nhưng không nhất thiết cần thấy toàn bộ dữ liệu đã xử lý.

Một hệ thống đã có đăng nhập vẫn có thể vi phạm tính bí mật. Tài khoản hợp lệ có thể nhận sai dữ liệu, API có thể trả thừa trường, hoặc log có thể chứa bí mật mà người đọc log không có quyền biết.

### 1.1. Phân biệt với các mục tiêu gần nhau

| Khái niệm | Câu hỏi trọng tâm | Ví dụ |
| --- | --- | --- |
| Confidentiality — tính bí mật | Ai được biết thông tin này? | Người tenant A không đọc được hồ sơ tenant B |
| Integrity — tính toàn vẹn | Thông tin có bị thay đổi trái phép không? | Người chỉ có quyền xem không sửa được hợp đồng |
| Availability — tính sẵn sàng | Chủ thể hợp lệ có sử dụng được khi cần không? | Nhân viên có quyền vẫn tra cứu được hồ sơ khi một thành phần lỗi |
| Authentication — xác thực | Chủ thể đang tương tác là ai theo cơ chế đã chọn? | Xác minh phiên đăng nhập |
| Authorization — phân quyền | Chủ thể đó được làm gì với tài nguyên nào? | Kiểm tra quyền đọc trên hồ sơ đích |
| Privacy — quyền riêng tư và cách xử lý dữ liệu cá nhân | Dữ liệu cá nhân được thu thập, sử dụng và chia sẻ theo mục đích nào? | Không thu thập trường không cần thiết cho nghiệp vụ |

Tính bí mật là một phần quan trọng của việc bảo vệ dữ liệu cá nhân, nhưng không bao trùm mọi vấn đề về mục đích thu thập hoặc sử dụng dữ liệu. Một tổ chức có thể giữ dữ liệu kín mà vẫn sử dụng dữ liệu không phù hợp với mục đích đã xác định.

Xác thực, phân quyền và mã hóa là các cơ chế có thể hỗ trợ tính bí mật. Chúng không đồng nghĩa với mục tiêu đó và không tự thay thế cho nhau.

### 1.2. Những cách tiết lộ cần được tính đến

Tiết lộ có thể xảy ra qua:

- Nội dung trả về từ API, trang web, tệp xuất hoặc thông báo.
- Trường dữ liệu không được hiển thị nhưng vẫn có trong phản hồi.
- Log, dấu vết lỗi và công cụ hỗ trợ.
- Cache, tệp tạm, bản sao lưu hoặc môi trường kiểm thử.
- Liên kết tải, tên đối tượng, tiêu đề hoặc metadata.
- Kết quả tìm kiếm, thống kê hoặc cách phản hồi cho tài nguyên bị cấm.
- Một tài khoản hoặc dịch vụ có quyền quá rộng.

Không cần kẻ tấn công sửa dữ liệu thì mới có sự cố bảo mật. Chỉ đọc được một tài liệu ngoài quyền đã có thể vi phạm tính bí mật.

## 2. Xác định tài sản, chủ thể và chính sách tiết lộ

Xét một dịch vụ quản lý hồ sơ khách hàng cho nhiều doanh nghiệp. Mỗi doanh nghiệp là một **tenant**, có dữ liệu và phạm vi quyền riêng.

Dữ liệu gồm thông tin liên hệ, ghi chú chăm sóc, hợp đồng đính kèm, bản xuất, log và bản sao lưu. Một số nhân viên chỉ được xem hồ sơ được phân công. Quyền xem hợp đồng hoặc xuất dữ liệu được cấp riêng.

### 2.1. Không bắt đầu bằng câu “mã hóa tất cả”

Trước khi chọn cơ chế, cần trả lời:

1. Dữ liệu nào cần giữ bí mật?
2. Ai sở hữu hoặc chịu trách nhiệm về dữ liệu?
3. Ai được đọc toàn bộ, ai chỉ được đọc một phần?
4. Được sử dụng cho thao tác và mục đích nghiệp vụ nào?
5. Điều kiện nào làm quyền có hiệu lực hoặc hết hiệu lực?
6. Những bản sao nào nằm trong phạm vi bảo vệ?
7. Có giả định nào về người vận hành, thiết bị và bên nhận không?

Nếu chưa biết ai được đọc, mã hóa chỉ giúp bảo vệ một số đường tiếp cận dữ liệu; ứng dụng vẫn có thể giải mã rồi trả nhầm cho người dùng.

### 2.2. Nhận diện mức nhạy cảm

Có thể dùng phân loại nội bộ như sau:

| Nhóm minh họa | Ví dụ | Hệ quả khi đặc tả |
| --- | --- | --- |
| Công khai | Nội dung giới thiệu dịch vụ đã được duyệt công bố | Không cần hạn chế đọc vì lý do bí mật trong phạm vi công bố |
| Nội bộ | Hướng dẫn vận hành không công khai | Xác định nhân sự hoặc dịch vụ được tiếp cận |
| Hạn chế | Hồ sơ khách hàng, ghi chú riêng, hợp đồng | Kiểm soát theo tenant, tài nguyên, trường và nhiệm vụ |
| Bí mật xác thực | Mật khẩu, mã xác thực, token, khóa sử dụng cho cơ chế bảo vệ | Hạn chế chặt nơi nhận, nơi lưu và khả năng xuất hiện trong log |

Đây là cách phân nhóm minh họa, không phải hệ thống phân loại bắt buộc cho mọi tổ chức. Mỗi nhóm cần có định nghĩa và quy tắc xử lý phù hợp.

Dữ liệu dẫn xuất cũng cần được xem xét. Một báo cáo đã bỏ tên khách hàng vẫn có thể chứa mã hồ sơ, địa chỉ hoặc thông tin đủ để liên kết lại. Không tự coi dữ liệu đã đổi định dạng là dữ liệu công khai.

### 2.3. Biểu diễn chính sách bằng ma trận quyền đọc

| Chủ thể | Thông tin cơ bản | Ghi chú riêng | Hợp đồng | Bản xuất nhiều hồ sơ |
| --- | --- | --- | --- | --- |
| Nhân viên được phân công | Trong phạm vi được giao | Khi có quyền riêng tương ứng | Khi được cấp quyền xem hợp đồng | Chỉ khi có quyền xuất và đúng phạm vi |
| Nhân viên cùng tenant nhưng không được phân công | Theo chính sách chia sẻ đã xác định | Không mặc định được đọc | Không mặc định được đọc | Không mặc định được xuất |
| Quản trị viên tenant | Theo quyền dữ liệu được cấp | Không suy ra từ quyền quản lý thành viên | Không suy ra từ quyền quản trị | Cần quyền xuất riêng |
| Người dùng tenant khác | Không | Không | Không | Không |
| Nhân sự hỗ trợ | Mặc định không có quyền đọc nội dung | Mặc định không | Mặc định không | Mặc định không |

“Không mặc định” nghĩa là phải có quy tắc cấp quyền rõ ràng, không phải để hệ thống tự đoán. Chính sách chưa được quyết định là câu hỏi còn mở; không được tự chuyển thành quyền cho phép.

Ma trận chỉ là một cách trình bày. Quyền còn có thể phụ thuộc trạng thái hồ sơ, sự phân công, thời điểm, mục đích hoặc một phê duyệt đặc biệt. Những điều kiện đó phải xuất hiện trong đặc tả.

## 3. Theo dữ liệu qua toàn bộ vòng đời

Một hồ sơ có thể được bảo vệ tốt trong cơ sở dữ liệu nhưng bị lộ ở bản xuất hoặc log. Vì vậy, mục tiêu bí mật cần được áp dụng cho **dữ liệu gốc và các bản sao thuộc phạm vi**.

~~~mermaid
flowchart LR
    D["Hồ sơ và hợp đồng gốc"] --> P["Dịch vụ xử lý"]
    P --> U["Phản hồi cho người dùng"]
    P --> E["Bản xuất và tệp tạm"]
    P --> C["Cache và chỉ mục tìm kiếm"]
    P --> L["Log và dữ liệu chẩn đoán"]
    D --> B["Quy trình sao lưu"]
    B --> S["Kho sao lưu"]
    S --> R["Quy trình phục hồi"]
    R --> D
~~~

Hình mô tả các nơi dữ liệu có thể xuất hiện, không khẳng định mọi hệ thống đều có tất cả các luồng. Với một hệ thống cụ thể, phải xác nhận đường đi thực tế, dữ liệu được chuyển và người được tiếp cận tại mỗi điểm.

### 3.1. Khi truyền, khi lưu và khi xử lý

| Trạng thái | Ví dụ | Điều cần bảo vệ |
| --- | --- | --- |
| Khi truyền | Client gọi API; dịch vụ đọc kho tệp; chuyển bản sao lưu | Nội dung không bị bên ngoài đọc; đầu nhận được xác minh phù hợp |
| Khi lưu | Cơ sở dữ liệu, kho tệp, cache trên đĩa, log, bản sao lưu | Người và dịch vụ chỉ đọc được dữ liệu thuộc quyền |
| Khi xử lý | Dữ liệu đã giải mã trong tiến trình, bộ nhớ, công cụ gỡ lỗi | Giới hạn người có quyền quan sát và tránh sao chép không cần thiết |

Bảo vệ kết nối không ngăn chính dịch vụ nhận dữ liệu tiết lộ sai sau đó. Mã hóa nơi lưu không ngăn một ứng dụng có quyền giải mã trả dữ liệu cho người không được phép.

Bộ nhớ, tệp dump và công cụ gỡ lỗi cũng có thể chứa dữ liệu rõ. Mức bảo vệ cần được xác định theo mô hình đe dọa và khả năng vận hành, không chỉ theo việc ổ đĩa đã được mã hóa.

### 3.2. Những bản sao có quyền truy cập khác dữ liệu gốc

Cần khảo sát:

- Bản xuất có giữ cùng tenant và phạm vi người được xem không?
- Cache có phân biệt tenant và trạng thái quyền không?
- Chỉ mục tìm kiếm có lưu nội dung hợp đồng hoặc ghi chú bị hạn chế không?
- Tệp tạm còn lại sau khi worker lỗi có được ai khác đọc không?
- Hệ thống kiểm thử có dùng bản sao dữ liệu thật không?
- Người đọc log có thể thấy dữ liệu mà họ không được xem trong ứng dụng không?
- Nhân sự phục hồi có thể tải toàn bộ bản sao lưu ra ngoài quy trình không?

Một đường đọc phụ có thể làm mất tác dụng của kiểm soát ở API chính. Ví dụ, API chi tiết chặn đúng nhưng endpoint tìm kiếm vẫn trả đoạn trích ghi chú riêng.

### 3.3. Metadata và suy luận

Không chỉ nội dung tài liệu mới có thể nhạy cảm. Tên tệp, mã hồ sơ, sự tồn tại của một khách hàng, số lượng hợp đồng hoặc danh sách người đang xử lý có thể là thông tin cần hạn chế.

Nếu cần che giấu sự tồn tại của tài nguyên, yêu cầu phải nói rõ phạm vi: nội dung phản hồi, mã trạng thái, thông báo lỗi và các kênh quan sát liên quan. Chọn cùng một mã lỗi chưa chứng minh mọi cách phân biệt đã được loại bỏ.

Các báo cáo tổng hợp cũng có thể làm lộ thông tin qua nhóm rất nhỏ hoặc truy vấn chồng lặp. Nếu sản phẩm cung cấp phân tích dữ liệu, cần xác định mô hình người xem và cách kiểm soát tiết lộ phù hợp thay vì mặc định “đã tổng hợp thì an toàn”.

## 4. Gắn mục tiêu bí mật với tình huống rủi ro

Một phát biểu như “không để lộ dữ liệu” quá rộng để giao trách nhiệm. Có thể bắt đầu bằng bảng sau:

| Mã rủi ro | Tình huống | Hậu quả cần ngăn hoặc giảm |
| --- | --- | --- |
| R-C01 | Người dùng thay mã hồ sơ hoặc tenant khi gọi API | Đọc hồ sơ ngoài phạm vi được cấp |
| R-C02 | API danh sách, tìm kiếm hoặc xuất trả thừa trường | Nhận ghi chú hoặc hợp đồng dù chỉ có quyền xem thông tin cơ bản |
| R-C03 | Log ghi token, nội dung hợp đồng hoặc dữ liệu nhạy cảm | Người đọc log tiếp cận bí mật ngoài nhu cầu |
| R-C04 | Dữ liệu được gửi qua kết nối không được bảo vệ hoặc sai đầu nhận | Bên không được phép đọc dữ liệu khi truyền |
| R-C05 | Tài khoản lưu trữ, bản sao lưu hoặc quyền dùng khóa quá rộng | Đọc được số lượng lớn dữ liệu qua đường vận hành |
| R-C06 | Liên kết, cache hoặc quyền cũ tiếp tục được dùng | Đọc dữ liệu sau khi quyền đã bị thu hồi hoặc kết quả đã hết hạn |

Danh sách là ngữ cảnh minh họa, chưa chứng minh hệ thống đang có những điểm yếu đó. Trong dự án, cần đánh giá khả năng xảy ra, tác động, giả định và chủ sở hữu rủi ro.

Với mỗi rủi ro, hỏi thêm:

- Chủ thể không được phép là ai?
- Dữ liệu nào có thể đến tay họ?
- Đường tiết lộ nào tạo ra hậu quả?
- Cơ chế hiện có bảo vệ được phần nào?
- Phần rủi ro nào còn lại sau biện pháp dự kiến?

Ví dụ, xác thực bổ sung có thể giảm một số đường chiếm tài khoản, nhưng không giải quyết lỗi API trả dữ liệu khác tenant cho một tài khoản đã đăng nhập.

## 5. Chuyển mục tiêu thành yêu cầu cụ thể

Một yêu cầu về tính bí mật nên mô tả:

> **Dữ liệu cần bảo vệ + chủ thể được phép + thao tác/kênh + điều kiện + hành vi khi không đạt + cách kiểm chứng.**

Không nhất thiết mọi câu đều có toàn bộ thông tin, nhưng hồ sơ yêu cầu phải cho phép tìm được chúng.

### 5.1. C-REQ-01: quyền đọc trên tài nguyên

> Với mọi yêu cầu đọc hồ sơ qua API thuộc phạm vi đặc tả, dịch vụ phải xác minh danh tính và kiểm tra quyền của chủ thể đối với hồ sơ đích theo tenant cùng chính sách phân công. Nếu không có quyền hoặc không xác định được quyền, dịch vụ phải từ chối và không trả nội dung hồ sơ.

Tiêu chí chấp nhận:

1. Người có quyền nhận được dữ liệu đúng hồ sơ trong phạm vi được cấp.
2. Người tenant A không nhận nội dung hồ sơ tenant B, kể cả khi biết mã hồ sơ.
3. Người cùng tenant nhưng ngoài phạm vi phân công không được vượt chính sách.
4. Mã tenant do client gửi không tự trở thành bằng chứng quyền.
5. Thiếu danh tính hợp lệ hoặc lỗi kiểm tra quyền không dẫn đến cho phép mặc định.
6. Phản hồi bị từ chối không chứa nội dung hồ sơ trong dữ liệu hoặc thông báo lỗi.

Từ “mọi” cần đi cùng danh mục endpoint và phiên bản trong phạm vi. Một ca kiểm thử của một endpoint chưa chứng minh toàn bộ nghĩa vụ này đã được đáp ứng.

### 5.2. C-REQ-02: quyền theo trường và dạng đầu ra

> Mỗi vai trò và điều kiện truy cập phải có tập trường được phép nhận. API chi tiết, danh sách, tìm kiếm, thông báo và bản xuất chỉ được đưa ra các trường thuộc tập đó cho chủ thể tương ứng.

Nếu một nhân viên không có quyền đọc ghi chú riêng, trường đó không được gửi xuống rồi chỉ ẩn bằng giao diện. Phải kiểm tra cả phản hồi thô, bản xuất và các trường phụ có thể chứa bản sao của nội dung.

Các cách hiển thị dữ liệu cần được đặc tả riêng:

- **Loại bỏ trường:** không đưa trường vào đầu ra.
- **Che một phần:** chỉ trả phần được phép theo quy tắc đã xác định.
- **Thay bằng tham chiếu:** trả định danh có quyền truy cập riêng.
- **Tổng hợp:** trả kết quả nhóm sau khi đánh giá nguy cơ suy luận.

Che trên giao diện không có tác dụng bảo vệ nếu giá trị đầy đủ vẫn nằm trong phản hồi hoặc thuộc tính ẩn.

### 5.3. C-REQ-03: bản xuất và quyền tại lúc tải

> Bản xuất chỉ được chứa dữ liệu trong phạm vi người yêu cầu được phép xuất theo chính sách đã xác định. Trước khi truyền nội dung tệp, hệ thống phải kiểm tra danh tính, quyền đối với bản xuất và thời hạn truy cập.

Phải chốt mốc đánh giá quyền: khi tiếp nhận công việc, khi worker bắt đầu xử lý, khi tải, hoặc kết hợp các mốc. Khi quyền thay đổi giữa các bước, hệ thống phải làm theo quy tắc đã ghi.

Một liên kết có hiệu lực theo người nắm giữ có thể cho phép người nhận chuyển tiếp quyền tải. Nếu chính sách đòi hỏi xác minh đúng danh tính ở mỗi lần tải, phải chọn thiết kế đáp ứng điều kiện đó hoặc xử lý thay đổi yêu cầu qua chủ sở hữu có thẩm quyền.

## 6. Đặc tả các kênh bảo vệ ngoài API nghiệp vụ

### 6.1. C-REQ-04: bảo vệ dữ liệu khi truyền

> Mọi kết nối thuộc danh mục luồng nhạy cảm phải dùng cơ chế bảo vệ nội dung khi truyền và xác minh đầu nhận theo thiết kế đã được chấp nhận. Khi không thiết lập được kết nối đáp ứng chính sách, thành phần gửi không được tự chuyển sang kênh kém bảo vệ để tiếp tục truyền dữ liệu nhạy cảm.

Danh mục cần bao gồm kết nối client–dịch vụ, dịch vụ–kho dữ liệu, worker–kho tệp, kênh log và sao lưu nếu chúng mang dữ liệu cần bảo vệ.

Kế hoạch kiểm chứng cần xác định:

- Luồng nào thuộc phạm vi và cấu hình nào đang áp dụng.
- Cách kiểm tra đầu nhận không hợp lệ hoặc cấu hình xác minh bị vô hiệu hóa.
- Hành vi khi kết nối bảo vệ thất bại.
- Có đường chuyển hướng, kênh phụ hoặc môi trường nào dùng cách khác không.

Bảo vệ đường truyền không bảo vệ được dữ liệu trước một đầu nhận đã bị chiếm quyền hoặc vốn được cấp quyền quá rộng. Những trường hợp đó cần yêu cầu khác.

### 6.2. C-REQ-05: quyền đọc dữ liệu lưu và quyền dùng khóa

> Cơ sở dữ liệu, kho hợp đồng, cache có lưu dữ liệu nhạy cảm, log và bản sao lưu phải có danh mục chủ thể được phép truy cập cùng phạm vi thao tác. Việc cấp quyền sử dụng khóa giải mã phải được giới hạn cho các chủ thể được xác định trong thiết kế; không suy ra quyền giải mã chỉ từ quyền tải bản dữ liệu đã mã hóa.

Khi mã hóa là biện pháp được chọn, đặc tả phải làm rõ:

- Dữ liệu và bản sao nào được mã hóa.
- Chủ thể nào có quyền mã hóa, giải mã hoặc quản lý khóa.
- Khóa có bị lưu cùng dữ liệu theo cách khiến một quyền đọc duy nhất lấy được cả hai không.
- Quy trình thay đổi khóa ảnh hưởng đến dữ liệu và bản sao cũ thế nào.
- Khi phục hồi, khóa cần thiết được lấy qua đường nào và ai được phép sử dụng.

Tách quyền tải dữ liệu và quyền giải mã chỉ có giá trị khi cơ chế quản lý thực sự duy trì sự tách biệt. Nếu một tài khoản có thể tự cấp cho mình cả hai quyền, phải đánh giá đường đặc quyền đó trong mô hình đe dọa.

Không tự triển khai một cơ chế mật mã chỉ để đáp ứng tên yêu cầu. Thiết kế phải lựa chọn cơ chế phù hợp, quản lý khóa và kiểm chứng cấu hình; thuật toán đơn lẻ không giải quyết toàn bộ vòng đời dữ liệu.

### 6.3. C-REQ-06: không tiết lộ qua log và chẩn đoán

> Log, sự kiện và bản ghi chẩn đoán của các luồng trong phạm vi chỉ được chứa các trường đã được phép. Không được ghi mật khẩu, mã xác thực dùng một lần, token truy cập, token làm mới, nội dung hợp đồng hoặc ghi chú riêng bị cấm theo chính sách log. Quy tắc áp dụng cho đường thành công, bị từ chối, xử lý ngoại lệ và thử lại.

Để vẫn phục vụ điều tra, có thể ghi định danh phù hợp, loại thao tác, kết quả, mã lý do và mã tương quan. Các định danh cũng phải được đánh giá về mức nhạy cảm, không mặc định mọi mã đều công khai.

Cần xác định nơi thực thi việc loại trừ: ứng dụng, middleware, thư viện, proxy và công cụ thu lỗi. Chỉ lọc ở nơi tập trung cuối cùng có thể để dữ liệu nhạy cảm xuất hiện ở bộ đệm hoặc nơi lưu trung gian.

Bằng chứng phù hợp là dữ liệu giả có dấu nhận diện được đưa qua nhiều nhánh, rồi đối chiếu các đích log thuộc phạm vi. Không dùng bí mật thật để chứng minh khả năng lọc bí mật.

### 6.4. C-REQ-07: hết hạn, thu hồi quyền và dữ liệu cũ

> Hệ thống phải chặn đọc hoặc tải dữ liệu theo thời điểm hết hạn và thay đổi quyền đã đặc tả. Cache, phiên, bản xuất và các điểm quyết định quyền liên quan không được làm kéo dài quyền vượt giới hạn được chấp nhận.

Giả sử nghiệp vụ chọn giới hạn minh họa: thu hồi quyền đọc phải có hiệu lực trong tối đa 60 giây từ khi thay đổi được ghi nhận thành công. Một yêu cầu cụ thể có thể viết:

> Mọi yêu cầu đọc hoặc tải bắt đầu sau mốc 60 giây phải bị từ chối nếu quyền chưa được cấp lại, kể cả khi người dùng sử dụng phiên được tạo trước khi thu hồi.

Con số là giả định học tập. Đặc tả phải nêu cách xử lý khi mất kết nối và với thao tác đã bắt đầu trước mốc thu hồi. Nếu không xác định được quyền, thao tác nhạy cảm phải theo chính sách từ chối đã chọn.

Thời điểm chặn truy cập và thời điểm dọn dữ liệu là hai nghĩa vụ khác nhau. Cần có thời hạn và phạm vi xóa cho tệp tạm, bản xuất, phiên bản cũ cùng các bản sao liên quan. Bản sao lưu có thể có chính sách riêng; phải ghi rõ thay vì khẳng định dữ liệu đã biến mất ở mọi nơi.

Thu hồi quyền phía máy chủ không tự xóa được dữ liệu mà người dùng đã tải về hợp lệ trước đó. Giới hạn này cần được phản ánh trong mô hình rủi ro và quy tắc chia sẻ dữ liệu.

### 6.5. C-REQ-08: không làm mất bí mật khi phục hồi

> Trước khi mở lại chức năng đọc dữ liệu nhạy cảm sau phục hồi, hệ thống phải xác minh phạm vi tenant, trạng thái quyền và cấu hình bảo vệ cần thiết. Các thay đổi thu hồi quyền sau điểm sao lưu phải được đối soát từ nguồn đáng tin cậy hoặc xử lý bằng phương án xác lập lại quyền đã được chấp nhận.

Nếu chưa có trạng thái quyền đáng tin cậy, không được mở chức năng nhạy cảm chỉ vì dữ liệu đã phục hồi xong.

Quy trình còn cần kiểm soát quyền truy cập môi trường phục hồi, các tệp trung gian và quyền dùng khóa. Phục hồi vào môi trường thử nghiệm ít được bảo vệ hơn có thể tạo thêm đường tiết lộ dù hệ thống sản xuất vẫn giữ đúng quyền.

### 6.6. Quyền hỗ trợ và truy cập đặc biệt

Một số sự cố cần người hỗ trợ xem dữ liệu hạn chế. Nếu có cơ chế này, phải đặc tả:

- Ai được yêu cầu và ai được phê duyệt.
- Tenant, hồ sơ và trường dữ liệu được mở.
- Lý do, thời điểm bắt đầu, thời điểm hết hiệu lực.
- Quyền có tự kết thúc hay phải thu hồi thủ công.
- Bằng chứng kiểm toán và người được xem bằng chứng.
- Hành vi khi công cụ kiểm toán hoặc phê duyệt không hoạt động.

Không dùng tài khoản quản trị dùng chung có quyền đọc lâu dài như một ngoại lệ không được quản lý. Việc ghi log truy cập cũng không tự làm cho một truy cập ngoài quyền trở thành hợp lệ.

## 7. Hiểu đúng vai trò và giới hạn của cơ chế

| Cơ chế | Hỗ trợ tính bí mật như thế nào? | Điều không thể tự chứng minh |
| --- | --- | --- |
| Xác thực bổ sung | Giảm một số đường sử dụng danh tính chỉ dựa vào bí mật bị lộ | Người đã xác thực có quyền đọc mọi tài nguyên |
| Phân quyền phía dịch vụ | Giới hạn dữ liệu theo chủ thể, tài nguyên và điều kiện | Mọi kênh phụ đều đã có cùng kiểm soát |
| Mã hóa khi truyền | Bảo vệ nội dung trên đoạn truyền thuộc phạm vi | Đầu nhận sẽ sử dụng hoặc lưu dữ liệu đúng quyền |
| Mã hóa khi lưu | Giảm khả năng đọc dữ liệu khi chỉ tiếp cận được bản lưu đã mã hóa | Ứng dụng hoặc người có quyền giải mã không thể tiết lộ dữ liệu |
| Che hoặc loại bỏ trường | Hạn chế đầu ra theo nhu cầu người nhận | Bản gốc không còn ở log, cache hoặc phản hồi khác |
| Thay định danh hoặc băm | Hỗ trợ một số mục tiêu giảm lộ trực tiếp hoặc kiểm tra một chiều | Dữ liệu chắc chắn không thể suy đoán hoặc liên kết lại |
| Giới hạn lưu giữ | Giảm số lượng và thời gian tồn tại của bản sao | Mọi bản đã tải xuống hoặc sao lưu đều được xóa đồng thời |
| Kiểm toán truy cập | Hỗ trợ phát hiện và điều tra | Truy cập đã ghi nhận đều được phép |

**Mã hóa** dùng cơ chế và khóa để bảo vệ nội dung có thể cần khôi phục. **Mã hóa biểu diễn**, như chuyển sang một định dạng khác, không tạo tính bí mật chỉ vì khó đọc bằng mắt. **Băm** là phép biến đổi một chiều theo thiết kế, nhưng dữ liệu đầu vào có ít khả năng vẫn có thể bị đoán rồi đối chiếu.

Với mật khẩu, cần cơ chế lưu và kiểm chứng chuyên dụng phù hợp; không lưu mật khẩu dưới dạng rõ hoặc coi một phép băm tổng quát là đủ. Với dữ liệu nghiệp vụ cần đọc lại, băm không thay thế cơ chế mã hóa và quản lý quyền.

Mỗi cơ chế phải gắn với tình huống rủi ro và phạm vi bảo vệ. Câu “đã mã hóa” không đủ làm kết luận rằng mục tiêu bí mật đã đạt.

## 8. Kiểm chứng mục tiêu bí mật

Cần kết hợp nhiều loại bằng chứng: kiểm thử hành vi, kiểm tra thiết kế, cấu hình quyền, quan sát luồng dữ liệu và diễn tập vận hành. Không có một phép thử duy nhất đại diện cho toàn bộ tính bí mật.

### 8.1. Ma trận truy vết từ rủi ro đến kiểm chứng

| Rủi ro | Yêu cầu liên quan | Bằng chứng cần thu thập |
| --- | --- | --- |
| R-C01: đọc ngoài tenant hoặc phân công | C-REQ-01 | T-C01: gọi API bằng danh tính khác tenant, khác phạm vi và thiếu quyền |
| R-C02: nhận thừa trường | C-REQ-02, C-REQ-03 | T-C02: đối chiếu tập trường ở chi tiết, danh sách, tìm kiếm và xuất |
| R-C03: lộ dữ liệu qua log | C-REQ-06 | T-C03: đưa giá trị giả qua nhánh thành công/lỗi và kiểm tra các đích log |
| R-C04: lộ khi truyền | C-REQ-04 | T-C04: kiểm tra cấu hình kết nối, xác minh đầu nhận và hành vi khi kết nối bảo vệ thất bại |
| R-C05: đọc qua kho dữ liệu hoặc bản sao lưu | C-REQ-05, C-REQ-08 | T-C05: kiểm tra quyền và thử truy cập bằng danh tính không được phép; diễn tập kiểm soát môi trường phục hồi |
| R-C06: tiếp tục đọc bằng trạng thái cũ | C-REQ-03, C-REQ-07, C-REQ-08 | T-C06: dùng phiên, cache và liên kết cũ; kiểm tra quyền trước và sau phục hồi |

Đây là kế hoạch kiểm chứng minh họa, chưa phải báo cáo rằng một sản phẩm đã đạt.

Một yêu cầu có thể cần nhiều ca kiểm thử. Ví dụ, T-C01 phải được phân rã theo các endpoint và tình huống trong phạm vi; một hàng trong bảng không có nghĩa chỉ cần gửi một yêu cầu API.

### 8.2. Ví dụ kiểm thử chống đọc hồ sơ khác tenant

~~~text
Yêu cầu: C-REQ-01
Phạm vi: API đọc chi tiết hồ sơ

Tiền điều kiện:
- Tenant A và tenant B có dữ liệu riêng.
- User A chỉ có quyền đọc một số hồ sơ của tenant A.
- Record A thuộc phạm vi User A được đọc.
- Record B thuộc tenant B và có giá trị dữ liệu giả dễ nhận diện.

Thao tác:
1. Dùng phiên User A đọc Record A.
2. Dùng cùng phiên gọi trực tiếp API đọc Record B.
3. Thay trường tenant ở những vị trí API hỗ trợ.
4. Kiểm tra phản hồi, trường phụ và thông báo lỗi.

Kết quả mong đợi:
- Bước đối chứng trả đúng dữ liệu được phép của Record A.
- Mọi lần đọc Record B đều bị từ chối theo hợp đồng API.
- Không có nội dung Record B trong phản hồi.
- Việc sửa tenant không mở rộng quyền.
~~~

Bước đối chứng tránh kết luận nhầm rằng cơ chế bảo vệ hoạt động khi thực tế mọi yêu cầu đều lỗi do môi trường hỏng.

Dữ liệu mong đợi phải dựa trên tập quyền và hồ sơ đã thiết lập độc lập cho phép thử. Không dùng lại chính hàm phân quyền đang được kiểm tra để suy ra kết quả mong đợi, vì cùng một lỗi có thể xuất hiện ở cả hai phía.

### 8.3. Kiểm tra cả đường hợp lệ và đường bị cấm

Hệ thống phải vừa phục vụ đúng người vừa từ chối đúng trường hợp. Những nhóm tình huống cần xem xét gồm:

- Đúng tenant, đúng phân công và đủ quyền.
- Cùng tenant nhưng thiếu quyền tài nguyên hoặc quyền trường.
- Khác tenant dù biết mã tài nguyên.
- Thiếu danh tính, phiên hết hạn hoặc bằng chứng không hợp lệ.
- Quyền bị thu hồi nhưng phiên và cache còn tồn tại.
- Công việc nền hoặc bản xuất được tạo trước khi quyền thay đổi.
- Thành phần kiểm tra quyền, kho khóa hoặc hệ thống log gặp lỗi.
- Dữ liệu được phục hồi từ thời điểm trước một thay đổi quyền.

Với trường hợp bị từ chối, cần kiểm tra các kênh đầu ra liên quan. Nếu API không trả dữ liệu nhưng log lại ghi toàn bộ hồ sơ vừa bị cấm, mục tiêu bí mật vẫn có thể bị vi phạm.

### 8.4. Bằng chứng phải gắn với phiên bản và phạm vi

Mỗi kết quả cần biết:

- Bản dựng và cấu hình được kiểm tra.
- Phiên bản yêu cầu, chính sách quyền và ca kiểm thử.
- Môi trường, dữ liệu, danh tính và phạm vi endpoint.
- Kết quả thực tế cùng bằng chứng đã lọc bí mật.
- Phụ thuộc, giả định hoặc kênh chưa được kiểm chứng.
- Lỗi phát hiện và kết quả kiểm thử lại sau khi sửa.

Kết quả đạt ở đường tải qua API không tự áp dụng sau khi chuyển sang tải trực tiếp từ kho. Tương tự, kiểm tra log ứng dụng không chứng minh proxy hoặc công cụ thu lỗi cũng đã lọc dữ liệu.

Bằng chứng về tính bí mật cũng phải được bảo vệ. Không đưa token thật hoặc hồ sơ thật vào báo cáo chia sẻ rộng chỉ để chứng minh đã tìm thấy tiết lộ.

## 9. Đo lường mà không cho phép tiết lộ trái phép

Có thể theo dõi các chỉ số hỗ trợ quản lý:

| Chỉ số | Câu hỏi được trả lời | Giới hạn |
| --- | --- | --- |
| Kênh dữ liệu đã được đánh giá trên tổng số kênh trong phạm vi | Có bỏ sót API, xuất, log, cache hoặc sao lưu không? | Không chứng minh kiểm soát ở từng kênh đều đúng |
| Tiêu chí có bằng chứng đạt phù hợp trên tổng số tiêu chí bắt buộc | Còn thiếu bằng chứng ở đâu? | Phụ thuộc chất lượng và hiệu lực của bằng chứng |
| Thời gian thay đổi quyền có hiệu lực | Quyền cũ tồn tại bao lâu sau thu hồi? | Chỉ có ý nghĩa nếu đo tại đủ điểm quyết định quyền |
| Số trường bị cấm xuất hiện trong đầu ra thử nghiệm | Có phát hiện đường tiết lộ nào trong lượt thử không? | Không tìm thấy không đồng nghĩa mọi đường đều đã được kiểm tra |
| Số phát hiện chưa xử lý theo mức rủi ro | Còn vấn đề nào ảnh hưởng đến quyết định phát hành? | Số lượng không thay thế đánh giá tác động |

Không viết “99% yêu cầu phải giữ bí mật” để cho phép một phần truy cập trái phép. Nếu yêu cầu cấm đọc hồ sơ khác tenant, một trường hợp đọc thành công ngoài quyền là lỗi của yêu cầu đó.

Cũng không dùng tỷ lệ chung để che một vấn đề nghiêm trọng. Hàng trăm kiểm thử trường không nhạy cảm đạt không bù cho một endpoint tải toàn bộ hợp đồng không kiểm tra quyền.

Khi tính tỷ lệ bao phủ, phải giữ rõ mẫu số, trạng thái chưa chạy, bị chặn, thất bại và bằng chứng đã cũ. Một ngoại lệ được chấp nhận cần báo cáo riêng; nó không biến thành bằng chứng yêu cầu đã đáp ứng.

## 10. Xử lý đánh đổi với các mục tiêu khác

### 10.1. Tính bí mật và khả năng phục vụ

Từ chối khi không xác định được quyền giúp ngăn tiết lộ, nhưng có thể làm người dùng hợp lệ không đọc được dữ liệu khi phụ thuộc lỗi.

Giải pháp cần đi vào độ tin cậy của đường kiểm tra quyền, cách vận hành và chính sách sử dụng trạng thái đã xác minh. Nếu dùng cache, phải giới hạn độ cũ theo yêu cầu thu hồi. Không bỏ qua quyền chỉ để duy trì tỷ lệ phản hồi thành công.

### 10.2. Tính bí mật và khả năng điều tra

Ghi toàn bộ yêu cầu có thể thuận tiện khi gỡ lỗi nhưng làm tăng người được tiếp cận dữ liệu. Cần xác định trường tối thiểu đủ để điều tra, dùng mã tương quan và quản lý quyền đọc công cụ quan sát.

Nếu phải thu thập chẩn đoán chi tiết trong một sự cố, cần có phạm vi, thời hạn và người chịu trách nhiệm. Đường xử lý đặc biệt không nên trở thành cấu hình ghi dữ liệu lâu dài.

### 10.3. Tính bí mật và phục hồi

Sao lưu hỗ trợ phục hồi nhưng tạo thêm bản sao cùng đường truy cập. Mã hóa hỗ trợ bí mật nhưng nếu không còn khóa cần thiết thì dữ liệu có thể không phục hồi được.

Vì vậy, yêu cầu phải đi cùng nhau: quyền sử dụng khóa được giới hạn, nhưng vẫn có quy trình phục hồi được kiểm soát và có bằng chứng. Không giải quyết khả năng phục hồi bằng cách lưu khóa ở nơi mọi người đọc được.

### 10.4. Phạm vi chia sẻ và nhu cầu nghiệp vụ

Một nhóm có thể cần báo cáo rộng hơn để phối hợp công việc. Thay vì cấp toàn bộ dữ liệu vì thuận tiện, cần xác định trường, mức tổng hợp, nhóm người nhận và thời hạn sử dụng thực sự cần thiết.

Nếu không thể đạt đồng thời các yêu cầu, phải ghi xung đột, phương án, tác động và quyết định của chủ sở hữu có thẩm quyền. Quyết định chấp nhận rủi ro không được ghi thành “đã kiểm thử đạt”.

## 11. Những lỗi đặc tả thường gặp

| Phát biểu hoặc cách làm | Vấn đề | Hướng sửa |
| --- | --- | --- |
| “Dữ liệu phải được giữ kín” | Không rõ dữ liệu, người nhận và kênh | Nêu tài sản, quyền, điều kiện và đầu ra bị cấm |
| “Đã đăng nhập thì được đọc” | Đánh đồng danh tính với quyền trên tài nguyên | Kiểm tra tenant, phân công và thao tác |
| “Ẩn trường trên giao diện là đủ” | Dữ liệu đầy đủ có thể vẫn tới client | Loại bỏ hoặc biến đổi ở nơi tạo đầu ra |
| “Mã hóa cơ sở dữ liệu là xong” | Bỏ sót quyền giải mã, bản xuất và log | Theo dõi mọi bản sao và chủ thể có thể đọc |
| “Chỉ có nhân sự nội bộ nên không cần hạn chế” | Không xác định nhu cầu và ranh giới đặc quyền | Cấp quyền theo trách nhiệm cụ thể, quản lý truy cập đặc biệt |
| “Dữ liệu đã băm nên không còn nhạy cảm” | Có thể bị đoán hoặc liên kết lại | Đánh giá miền giá trị và ngữ cảnh sử dụng |
| “Thu hồi quyền sẽ xóa mọi bản sao” | Không kiểm soát được bản đã tải về | Ghi rõ phạm vi thu hồi và giới hạn sau chia sẻ |
| “Không có báo cáo sự cố nghĩa là không bị lộ” | Có thể chưa quan sát được đường tiết lộ | Kết hợp kiểm chứng chủ động và giám sát phù hợp |
| “Một ca khác tenant đạt là đủ” | Chưa bao phủ các endpoint và kênh khác | Duy trì danh mục đường đọc cùng bằng chứng tương ứng |

## 12. Đưa mục tiêu bí mật vào vòng đời phát triển

Khi làm rõ nhu cầu, xác định dữ liệu, chủ thể và chính sách tiết lộ trước. Dùng mô hình luồng dữ liệu để nhận diện nơi có bản sao và ranh giới cần bảo vệ.

Khi thiết kế, giao trách nhiệm cho điểm xác thực, phân quyền, lọc trường, tạo bản xuất, lưu dữ liệu, ghi log và phục hồi. Giữ liên kết từ rủi ro tới yêu cầu, quyết định thiết kế và kiểm chứng.

Khi triển khai, kiểm soát mọi đường đầu ra liên quan. Một thay đổi thêm trường vào API, báo cáo hoặc log có thể làm thay đổi phạm vi tiết lộ dù không đổi cơ chế đăng nhập.

Trước phát hành, xem xét yêu cầu đã có bằng chứng, khoảng trống, phát hiện chưa sửa và ngoại lệ. Trong vận hành, đánh giá lại khi thay đổi quyền dịch vụ, cách tải tệp, hệ thống quan sát, nhà cung cấp hoặc quy trình sao lưu.

Một đặc tả tính bí mật đủ rõ phải cho phép người thiết kế và kiểm thử trả lời: **dữ liệu nào được phép đến tay ai, qua kênh nào, vào thời điểm nào, và bằng chứng nào cho thấy các đường tiết lộ ngoài quyền đã được kiểm soát trong phạm vi đã xác định**.
