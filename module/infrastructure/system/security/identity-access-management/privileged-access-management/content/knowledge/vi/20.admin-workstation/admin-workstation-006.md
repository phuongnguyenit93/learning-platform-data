# Không duyệt email trên PAW

## Mục tiêu bài học

**Privileged Access Workstation (PAW)** là máy trạm được thiết kế và quản trị để thực hiện công việc có quyền cao. Trong phạm vi Privileged Access Management (PAM), PAW là nơi người quản trị xác thực, yêu cầu quyền JIT, truy cập vault và điều khiển các phiên quản trị nhạy cảm.

Duyệt email đưa một luồng nội dung có nguồn gốc đa dạng vào chính môi trường đang có khả năng sử dụng quyền đặc biệt. Vì vậy, một nguyên tắc thiết kế quan trọng là giữ email và hoạt động làm việc hằng ngày ngoài PAW.

Sau bài học, bạn có thể:

- Giải thích vì sao email làm tăng rủi ro đối với môi trường quản trị.
- Phân biệt tách tài khoản, tách trình duyệt và tách ranh giới thiết bị.
- Thiết kế luồng tiếp nhận ticket, tài liệu và tệp hỗ trợ mà không mở hộp thư trên PAW.
- Áp dụng kiểm soát kỹ thuật và quy trình vận hành để nguyên tắc có hiệu lực.
- Xử lý sự cố hoặc ngoại lệ mà không mặc định PAW vẫn đáng tin sau một lần quét.
- Liên kết rủi ro endpoint với grant, phiên PAM và credential cần thu hồi.

Các ví dụ chính sách trong bài là mô tả thiết kế, không phải cấu hình sản phẩm có thể dùng nguyên trạng.

## 1. PAW bảo vệ điều gì?

PAW không chỉ bảo vệ một chiếc máy tính. Nó bảo vệ **đường điều khiển** đi từ người quản trị tới hạ tầng nhạy cảm.

```text
Người quản trị
    |
    v
PAW được quản lý
    |
    v
IdP / PAM / vault / cơ chế cấp quyền
    |
    v
Phiên hoặc công cụ quản trị
    |
    v
Hệ thống sản xuất và hạ tầng nhạy cảm
```

Nếu máy ở đầu đường điều khiển bị xâm nhập, kẻ tấn công có thể lợi dụng phiên hoặc hành động mà người quản trị được phép thực hiện.

Không nhất thiết phải lấy được mật khẩu để gây tác động. Một phiên đang mở, một token, một công cụ quản trị hoặc việc điều khiển thao tác của người dùng có thể đã đủ tạo ra rủi ro.

Giữ PAW tách khỏi email giúp giảm một nhóm đường tiếp xúc với nội dung không đáng tin. Việc này cần đi cùng cập nhật, quản trị thiết bị, xác thực mạnh, least privilege, JIT/JEA và kiểm soát phiên; nó không tự bảo đảm PAW không thể bị xâm nhập.

## 2. Vì sao email không phù hợp với môi trường PAW?

### 2.1. Nội dung bên ngoài đi vào luồng quản trị

Email phục vụ liên lạc với nhiều nguồn: đồng nghiệp, khách hàng, nhà cung cấp và các hệ thống tự động. Tên người gửi hoặc một chuỗi trao đổi quen thuộc không bảo đảm toàn bộ nội dung an toàn.

Một thư có thể dẫn người dùng tới:

- Trang đăng nhập hoặc trang chấp thuận ứng dụng giả mạo.
- Tệp đính kèm, bản xem trước hoặc nội dung cần trình xử lý khác.
- Đường dẫn tải công cụ hay script chưa được kiểm tra.
- Yêu cầu thay đổi khẩn cấp tạo áp lực bỏ qua quy trình.
- Một địa chỉ thật nhưng được dùng để hướng dẫn thao tác sai phạm vi.

Không phải mỗi lần mở thư đều gây xâm nhập. Vấn đề là email làm tăng bề mặt tiếp xúc và khả năng bị dẫn dắt trong một môi trường có hậu quả sự cố lớn.

### 2.2. Cùng endpoint với công cụ đặc quyền

Nếu nội dung độc hại hoặc một lỗ hổng làm ảnh hưởng endpoint, các tài khoản tách biệt vẫn có thể cùng chịu rủi ro trên máy đó.

Ví dụ, quản trị viên đọc email bằng tài khoản thường rồi mở phiên PAM bằng tài khoản đặc quyền trên cùng hệ điều hành. Việc dùng hai tài khoản giúp tách một số quyền, nhưng không tự tạo hai môi trường thiết bị độc lập.

Một tiến trình có khả năng theo dõi hoặc điều khiển môi trường người dùng có thể tác động tới phiên quản trị. Mức ảnh hưởng phụ thuộc hệ thống và quyền đã có, nhưng không nên giả định đổi tài khoản là đủ để loại trừ rủi ro.

### 2.3. Email làm phát sinh nhiều chức năng phụ

Một ứng dụng thư có thể kéo theo lưu tệp tạm, đồng bộ nội dung, trình xem tài liệu, plugin, thông báo, cache hoặc trình duyệt nhúng.

Gỡ một ứng dụng email không giải quyết toàn bộ nếu webmail, hộp thư trong công cụ cộng tác hoặc tệp thư đã xuất vẫn được mở trên PAW.

Nguyên tắc cần bao phủ **hoạt động đọc và xử lý email**, không chỉ tên một phần mềm.

## 3. MFA và vault không thay thế ranh giới PAW

### 3.1. MFA bảo vệ một phần đường xác thực

MFA phù hợp giúp giảm rủi ro đăng nhập trái phép, nhưng không tự làm một endpoint bị điều khiển trở nên đáng tin.

Nếu một phiên hợp lệ đã được mở, kẻ điều khiển endpoint có thể cố lợi dụng chính phiên đó. Một yêu cầu MFA mới cũng có thể bị người dùng chấp thuận trong ngữ cảnh bị dẫn dắt.

Vì vậy, “đã có MFA” không phải lý do để trộn hộp thư và công cụ quản trị trên PAW.

### 3.2. Vault giảm lộ bí mật nhưng không loại bỏ khả năng lạm dụng phiên

PAM có thể thiết lập phiên mà không hiển thị credential cho người quản trị. Điều này giảm một số rủi ro sao chép mật khẩu.

Tuy nhiên, người điều khiển phiên vẫn có khả năng thực hiện những thao tác mà phiên cho phép. Nếu endpoint đầu vào bị kiểm soát, việc không biết mật khẩu chưa đủ ngăn tác động.

Cần giữ quyền phiên đủ hẹp, giám sát, có khả năng kết thúc và bảo vệ thiết bị khởi tạo.

### 3.3. JIT giảm thời gian tồn tại quyền

Quyền chỉ tồn tại trong một cửa sổ ngắn làm giảm thời gian bị lạm dụng, nhưng khoảng thời gian đó vẫn có thể đủ để thực hiện một thay đổi có tác động lớn.

Một thiết kế tốt kết hợp PAW sạch hơn về bề mặt tiếp xúc với quyền tối thiểu và quyền có thời hạn, thay vì trông chờ một cơ chế bù cho mọi cơ chế khác.

## 4. Mô hình tách công việc hằng ngày và công việc quản trị

Một mô hình tham khảo:

```text
Thiết bị làm việc hằng ngày
  - email
  - họp, trao đổi, tài liệu thông thường
  - tiếp nhận yêu cầu và ticket
              |
              | mã ticket / luồng tệp đã kiểm soát
              v
PAW
  - công cụ quản trị được phép
  - truy cập IdP, PAM và tài nguyên quản trị cần thiết
  - không hộp thư, không hoạt động email thường ngày
              |
              v
Phiên quản trị có phạm vi và thời hạn
```

Điều quan trọng là đường chuyển thông tin giữa hai môi trường được thiết kế rõ, không hình thành một kênh sao chép tùy ý.

### 4.1. Tách tài khoản

Tài khoản làm việc hằng ngày dùng cho email và công việc thông thường. Tài khoản đặc quyền dùng theo vai trò quản trị.

Không đăng nhập tài khoản đặc quyền vào hộp thư chỉ để nhận thông báo hoặc tải tệp. Cũng không dùng hộp thư hằng ngày làm một đường khôi phục yếu có thể tự đặt lại toàn bộ quyền đặc biệt mà thiếu kiểm soát tương xứng.

Thiết kế thông báo và phục hồi cần được xem xét riêng: người quản trị vẫn phải nhận được cảnh báo và có cách khôi phục hợp lệ, nhưng các chức năng đó không yêu cầu mở hộp thư trên PAW.

### 4.2. Tách profile trình duyệt chưa đủ

Hai profile hoặc hai trình duyệt trên cùng endpoint có thể tách cookie và một số dữ liệu ứng dụng. Chúng không tự tạo cùng ranh giới như hai môi trường thiết bị độc lập được quản trị.

Trình duyệt trên PAW vẫn có thể cần thiết cho cổng quản trị web, IdP hoặc PAM. Mục tiêu là giới hạn ứng dụng và nguồn truy cập theo chức năng quản trị, không mặc định cấm mọi trình duyệt.

### 4.3. Máy ảo, VDI và remote desktop

Một máy ảo quản trị hoặc VDI có thể là thành phần của thiết kế, nhưng cần đánh giá toàn bộ đường nhập liệu và điều khiển.

Nếu người dùng truy cập môi trường quản trị từ một máy hằng ngày đã bị xâm nhập, endpoint nguồn có thể theo dõi hoặc điều khiển tương tác. Việc đích là một desktop được quản lý không tự làm nguồn truy cập trở nên đáng tin.

Nếu dùng ảo hóa để tách môi trường trên cùng thiết bị, phải đánh giá host, công cụ quản lý, clipboard, chia sẻ tệp, chuyển tiếp thiết bị và đường điều khiển giữa các vùng. Không mặc định “có máy ảo” là đã đạt mục tiêu PAW.

Lựa chọn kiến trúc phụ thuộc mô hình đe dọa và mức bảo vệ cần thiết. Những giới hạn còn lại phải được biết và kiểm chứng.

## 5. Biến nguyên tắc thành kiểm soát có hiệu lực

Một dòng nội quy “không đọc email trên PAW” cần được hỗ trợ bằng cấu hình và quy trình đủ dùng.

### 5.1. Giới hạn ứng dụng và chức năng

Baseline PAW có thể quy định:

- Chỉ cài công cụ cần cho nhiệm vụ quản trị.
- Không cấu hình tài khoản thư hoặc ứng dụng đồng bộ hộp thư.
- Không tự cài tiện ích trình duyệt hoặc plugin ngoài danh sách được quản trị.
- Không dùng chức năng xem email trong ứng dụng khác như một đường thay thế.
- Giới hạn ứng dụng xử lý tài liệu và nội dung không cần thiết.
- Quản lý mở tệp từ bên ngoài, phương tiện lưu trữ và chia sẻ tệp theo chính sách.

Tên ứng dụng không phải ranh giới duy nhất. Một ứng dụng quản trị được phép có thể tích hợp webview hoặc mở liên kết ra ngoài, nên cần đánh giá hành vi thực tế.

Cho phép phần mềm có chữ ký hoặc từ nguồn nội bộ không tự chứng minh mọi nội dung nó xử lý đều an toàn. Cần quản lý phiên bản, cập nhật và mục đích sử dụng.

### 5.2. Giới hạn truy cập dịch vụ

PAW nên truy cập những dịch vụ cần cho quản trị và vận hành thiết bị, với phạm vi được xác định. Các phụ thuộc có thể gồm IdP, PAM, kho công cụ, cập nhật, bảo mật endpoint, phân giải tên và thời gian.

Truy cập hộp thư hoặc webmail không thuộc hoạt động quản trị thông thường trên PAW.

Nếu một nền tảng dùng chung hạ tầng cho nhiều ứng dụng, chặn hoặc cho phép theo tên miền đơn thuần có thể quá rộng hoặc làm hỏng đăng nhập. Cần phối hợp kiểm soát ứng dụng, proxy, trình duyệt được quản lý hoặc cơ chế truy cập dịch vụ phù hợp.

Không hạ kiểm tra bảo mật chỉ để một trang được mở. Cũng không chặn mù các phụ thuộc cần thiết khiến PAW mất cập nhật hoặc cơ chế xác thực.

### 5.3. Không lưu trạng thái hộp thư cũ

Khi chuyển một máy sang PAW hoặc phát hiện cấu hình sai, cần biết có còn profile thư, dữ liệu cache, tệp đính kèm hoặc phiên đăng nhập liên quan hay không.

Việc chỉ gỡ shortcut không chứng minh trạng thái cũ đã được xử lý. Tùy mô hình và mức tin cậy, tổ chức có thể cần dựng lại từ baseline được quản lý thay vì tiếp tục dùng một máy làm việc hằng ngày vừa được đổi tên.

Không tự xóa dữ liệu nghi liên quan sự cố trước khi đội có trách nhiệm quyết định cách bảo toàn và xử lý bằng chứng.

### 5.4. Giám sát độ lệch

Có thể theo dõi việc cài ứng dụng thư, mở dịch vụ email không được phép hoặc thay đổi baseline liên quan. Cần biết cơ chế nào chỉ phát hiện và cơ chế nào thực sự chặn.

Tín hiệu nên đủ để phát hiện độ lệch, tránh thu thập nội dung thư không cần thiết. Có thể ghi định danh thiết bị, ứng dụng, đích dịch vụ, thời điểm và kết quả chính sách thay vì sao chép dữ liệu hộp thư.

## 6. Quy trình tiếp nhận công việc mà không mở email trên PAW

### 6.1. Nhận yêu cầu trên thiết bị hằng ngày

Người quản trị đọc email hoặc trao đổi ở môi trường làm việc hằng ngày. Nếu có yêu cầu thay đổi hạ tầng, chuyển nó thành công việc trong hệ thống được tổ chức quản trị.

Thông tin cần thiết có thể gồm mã ticket, người yêu cầu, chủ sở hữu, tài sản, mục đích, cửa sổ và phạm vi. Một email tự xưng “đã được duyệt” không thay thế việc kiểm tra hồ sơ phê duyệt.

### 6.2. Truy cập nguồn công việc đã định trên PAW

Từ PAW, mở cổng PAM hoặc hệ thống công việc được phép bằng địa chỉ đã được quản trị, chẳng hạn bookmark do tổ chức cung cấp. Dùng mã ticket để tìm đúng hồ sơ.

Không đăng nhập hộp thư trên PAW để bấm liên kết. Không đưa token, đường dẫn chứa bí mật hoặc mã khôi phục từ email vào thanh địa chỉ.

Hệ thống ticket cũng có thể chứa liên kết, HTML hoặc tệp do nhiều người gửi. Nếu được phép truy cập trên PAW, cần cấu hình và quy trình xử lý nội dung phù hợp; nhãn “nội bộ” không tự làm mọi phần dữ liệu đáng tin.

### 6.3. Kiểm tra chỉ dẫn trước khi làm

Tách thiết bị giảm một số đường lây nhiễm kỹ thuật nhưng không ngăn mọi thao túng xã hội. Người quản trị vẫn có thể đọc một email giả trên máy khác rồi tự chạy lệnh nguy hiểm trên PAW.

Cần xác minh công việc, người có thẩm quyền, tài sản và runbook. Nếu yêu cầu thay đổi ngoài phạm vi hoặc mâu thuẫn hồ sơ, làm rõ trước khi thực thi.

Gõ lại một lệnh từ email thay vì copy không biến lệnh đó thành an toàn.

### 6.4. Xin và sử dụng quyền qua PAM

Sau khi công việc được xác nhận:

1. Đăng nhập bằng tài khoản và phương thức phù hợp.
2. Yêu cầu đúng resource, hành động và thời hạn.
3. Chờ các phê duyệt cần thiết.
4. Kích hoạt quyền JIT hoặc mở phiên theo profile.
5. Thực hiện công việc trong phạm vi.
6. Kết thúc, thu hồi và đối chiếu kết quả.

Email có thể thông báo có một công việc cần xử lý ở môi trường hằng ngày. Nó không phải phương tiện mang credential hoặc tự cấp quyền vào phiên quản trị.

## 7. Tệp đính kèm, script, bản vá và gói chẩn đoán

Một nhu cầu phổ biến là “nhà cung cấp gửi bản vá qua email”. Giữ email ngoài PAW vẫn cần một đường đưa tệp cần thiết vào hệ thống.

### 7.1. Luồng tệp có kiểm soát

```text
Nguồn cung cấp tệp
       |
       v
Kênh tiếp nhận được phép ở vùng phù hợp
       |
       v
Kiểm tra nguồn gốc, nội dung và điều kiện sử dụng
       |
       v
Kho tệp/công cụ được quản trị
       |
       v
PAW lấy đúng hiện vật đã được duyệt
       |
       v
Thực hiện theo runbook và quyền tối thiểu
```

Quy trình có thể bao gồm:

- Xác minh nguồn cung cấp qua kênh đã thống nhất.
- Kiểm tra chữ ký khi có, mã băm và phiên bản.
- Kiểm tra nội dung hoặc thử nghiệm trong môi trường phù hợp.
- Gắn với ticket, người duyệt và tài sản đích.
- Phân quyền tải, thực thi và lưu tệp.
- Ghi lại hiện vật nào được dùng, ở đâu và khi nào.

Mã băm giúp đối chiếu đúng tệp; nó không chứng minh tệp an toàn. Chữ ký hợp lệ cũng không thay kiểm tra mục đích, phiên bản và tác động. Kết quả quét không phải bảo đảm tuyệt đối.

### 7.2. Script không nên đi thẳng từ hộp thư tới shell quản trị

Script cần được xem xét như một hiện vật có quyền tác động hệ thống. Nguồn gửi quen thuộc không thay thế đánh giá nội dung và kiểm thử.

Có thể dùng kho mã hoặc kho công cụ được kiểm soát để giữ phiên bản đã duyệt. PAW lấy hiện vật theo tham chiếu cụ thể, không kéo một nội dung thay đổi tùy ý từ đường dẫn trong thư.

Nếu runbook có tham số, cần kiểm tra tài sản và phạm vi. Một script đã duyệt vẫn có thể gây tác động sai nếu chạy trên nhầm môi trường.

### 7.3. Clipboard, USB và đồng bộ đám mây

Không dùng một kênh thay thế không kiểm soát để vượt việc không mở email: sao chép toàn bộ tệp từ máy hằng ngày, đồng bộ thư mục cá nhân hoặc cắm thiết bị lưu trữ tùy ý vào PAW.

Nhu cầu chuyển dữ liệu phải có đường được thiết kế. Kênh đó cần giới hạn loại dữ liệu, nguồn, đích, quyền và bằng chứng theo rủi ro.

Cũng cần kiểm soát chiều đi ra: log, dump hoặc gói chẩn đoán có thể chứa token, cấu hình và dữ liệu nhạy cảm. Không gửi chúng qua email chỉ vì mục đích là hỗ trợ kỹ thuật.

## 8. Thông báo, xác nhận và công việc khẩn cấp

### 8.1. Nhận thông báo mà không mang hộp thư vào PAW

Có thể nhận nhắc việc ở thiết bị hằng ngày, sau đó mở hồ sơ tương ứng từ nguồn được phép trên PAW. Không nhất thiết phải tắt mọi thông báo của tổ chức; cần thiết kế đúng nơi nhận và cách chuyển sang công việc quản trị.

Thông báo MFA hoặc phê duyệt cần được kiểm tra đúng hành động. Không chấp thuận chỉ vì vừa nhận một email nói “sẽ có thông báo”.

### 8.2. Hỗ trợ từ xa của nhà cung cấp

Nhà cung cấp cần được tiếp nhận qua quy trình truy cập bên ngoài, định danh cá nhân, người bảo trợ và phạm vi quyền phù hợp.

Không cài công cụ điều khiển được gửi qua email lên PAW rồi coi đó là hỗ trợ bình thường. Công cụ hỗ trợ và đường truy cập phải được đánh giá, quản lý và cho phép theo kiến trúc.

### 8.3. Sự cố cần xử lý ngay

Một sự cố có thể khiến quy trình tiếp nhận khó hơn, nhưng không tự làm email trên PAW trở thành cần thiết.

Nên chuẩn bị trước thiết bị liên lạc, cổng công việc, runbook và đường khẩn cấp. Nếu một thành phần không sẵn sàng, sử dụng phương án đã xác định với người chịu trách nhiệm.

Không dùng lý do “chỉ mở một phút” để biến PAW thành máy hằng ngày. Nếu cần một ngoại lệ thực sự, phải mô tả rủi ro, điều kiện và cách khôi phục mức tin cậy; không mặc định đóng tab là đủ.

## 9. Khi email đã bị mở trên PAW

Mức độ sự cố phụ thuộc hành động đã xảy ra: chỉ cố mở dịch vụ bị chặn, đã đăng nhập hộp thư, mở tệp hay thực thi nội dung. Cần ghi đúng thực tế thay vì mặc định tất cả đều giống nhau.

### 9.1. Dừng mở rộng rủi ro và thông báo

Người quản trị nên dừng các thao tác đặc quyền mới trên máy nghi bị ảnh hưởng và thông báo qua kênh tin cậy theo quy trình sự cố.

Không tiếp tục đăng nhập thêm tài khoản nhạy cảm để “kiểm tra máy có sao không”. Không tự xóa tệp, lịch sử hoặc cài công cụ không được phép nếu việc đó có thể làm mất bằng chứng.

Việc cô lập thiết bị, kết thúc phiên hoặc duy trì một kênh điều tra cần do vai trò có trách nhiệm thực hiện theo kế hoạch, có xét tác động tới dịch vụ và khả năng thu thập.

### 9.2. Xác định phạm vi liên quan

Các câu hỏi quan trọng:

- Email hoặc tệp nào đã được mở và trong khoảng thời gian nào?
- Có đăng nhập, chấp thuận ứng dụng, tải tệp hay chạy nội dung không?
- Tài khoản nào đã đăng nhập trên PAW trong khoảng liên quan?
- Có phiên PAM hoặc phiên quản trị tại đích đang hoạt động không?
- Credential nào đã được hiển thị, tải hoặc có thể đã bị lộ?
- Có grant, token hoặc thay đổi quyền nào cần xử lý?
- Có dấu hiệu cài công cụ, tạo tác vụ hoặc thay đổi cấu hình không?

Không cần đưa giá trị bí mật vào báo cáo. Dùng định danh tài khoản, secret tham chiếu và mã phiên được bảo vệ.

### 9.3. Thu hồi theo lớp

Khóa thiết bị khỏi đường truy cập quản trị không tự kết thúc mọi trạng thái đã tạo trước đó.

Có thể cần xử lý phiên IdP, phiên PAM, grant JIT, kết nối đích và credential liên quan. Phạm vi phải dựa trên điều tra và chính sách, không tùy tiện luân chuyển mọi tài khoản dịch vụ mà bỏ qua phụ thuộc.

Đổi mật khẩu không bảo đảm dừng phiên cũ. Ngắt kết nối cũng không tự dừng tác vụ nền hoặc hoàn tác một thay đổi đã thực hiện.

Cần kiểm chứng kết quả và ghi rõ phần còn chưa thu hồi được cùng người xử lý.

### 9.4. Khôi phục mức tin cậy

Một lần quét không phát hiện không đủ để chứng minh máy chắc chắn sạch. Tùy sự kiện và tiêu chí của tổ chức, có thể cần điều tra, dựng lại từ baseline tin cậy, kiểm tra quản lý thiết bị và xử lý danh tính thiết bị liên quan.

Trước khi cho máy trở lại đường quản trị, cần xác nhận những điều kiện đã xác lập như baseline, cập nhật, bảo mật endpoint, trạng thái đăng ký, chính sách truy cập và việc xử lý phiên hoặc credential cũ.

Không dùng một bản đánh giá thiết bị cũ để coi máy đã đạt điều kiện sau sự cố. Bằng chứng đưa trở lại sử dụng phải phản ánh trạng thái sau xử lý.

## 10. Tình huống thực hành: bản vá khẩn cấp gửi qua email

### 10.1. Bối cảnh

Nhà cung cấp gửi thư cho Linh, quản trị viên nền tảng, yêu cầu chạy một script để sửa lỗi dịch vụ sản xuất. Linh đang dùng PAW để theo dõi một phiên bảo trì.

Thư nói cần tải script từ liên kết và chạy ngay với quyền cao. Chữ ký email trông quen thuộc.

### 10.2. Cách xử lý phù hợp

1. Linh đọc và trao đổi email trên thiết bị hằng ngày.
2. Linh xác minh yêu cầu qua kênh liên hệ đã thống nhất và kiểm tra ticket.
3. Chủ sở hữu đánh giá phạm vi thay đổi, tác động và cửa sổ thực hiện.
4. Hiện vật được tiếp nhận vào quy trình kiểm tra, xác định phiên bản và đưa vào kho được phép.
5. Trên PAW, Linh mở ticket và runbook qua nguồn đã quản trị.
6. Linh yêu cầu đúng quyền JIT cho đúng tài sản và profile.
7. Linh dùng hiện vật đã được duyệt, thực hiện rồi kiểm tra kết quả.
8. Kết thúc quyền, phiên và lưu bằng chứng.

Nếu yêu cầu thực sự khẩn cấp, áp dụng quy trình khẩn cấp với trách nhiệm và giới hạn tương ứng. Không bỏ qua việc xác minh nguồn và quyền chỉ vì thư dùng từ “khẩn cấp”.

### 10.3. Những lựa chọn làm mất ranh giới

| Lựa chọn | Vấn đề |
|---|---|
| Mở webmail trên PAW nhưng không cài ứng dụng thư | Hoạt động email vẫn diễn ra trong môi trường quản trị |
| Mở thư bằng profile trình duyệt khác | Không tạo ranh giới endpoint độc lập |
| Tải script ở máy thường rồi copy thẳng sang PAW | Vượt đường tiếp nhận và kiểm tra hiện vật |
| Gõ lại lệnh trong thư | Không xác minh tính đúng đắn của lệnh |
| Chạy script vì nguồn có chữ ký | Chưa kiểm tra mục đích, phiên bản và tác động |
| Đăng nhập mailbox bằng tài khoản đặc quyền | Đưa danh tính nhạy cảm vào một luồng không cần thiết |
| Cho rằng MFA và vault đã bảo vệ mọi thứ | Bỏ qua rủi ro điều khiển endpoint và phiên |
| Đóng tab email rồi tiếp tục như chưa có gì | Chưa đánh giá hành động và trạng thái liên quan |

### 10.4. Nếu Linh đã lỡ mở tệp

Linh cần ghi nhận hành động và báo theo quy trình, dừng mở thêm quyền từ PAW đó. Đội có trách nhiệm đánh giá thiết bị, phiên và hiện vật; xử lý quyền đang tồn tại và quyết định cách phục hồi.

Nếu cần tiếp tục khắc phục dịch vụ, sử dụng một đường quản trị và thiết bị còn đáp ứng điều kiện. Không mặc định chính PAW nghi bị ảnh hưởng là nơi an toàn để sửa cả sự cố hạ tầng lẫn sự cố của nó.

## 11. Kiểm chứng nguyên tắc trong vận hành

Thử bằng dữ liệu và tài khoản kiểm thử, không dùng tệp độc hại thật để chứng minh kiểm soát.

| Phép thử | Điều cần xác nhận |
|---|---|
| Mở ứng dụng thư hoặc cấu hình mailbox trên PAW | Chính sách ứng dụng được thực thi và ghi nhận |
| Truy cập webmail | Hành vi chặn hoặc giới hạn đúng thiết kế |
| Thử đường email trong ứng dụng khác | Không tạo lối thay thế ngoài ý định |
| Dùng profile trình duyệt khác | Không vượt kiểm soát hoạt động |
| Mở tệp thư hoặc hiện vật chưa được duyệt | Xử lý theo chính sách ứng dụng và tệp |
| Tải script từ liên kết trong nội dung hỗ trợ | Không bỏ qua luồng hiện vật được quản trị |
| Chuyển tệp từ thiết bị hằng ngày | Chỉ đi qua kênh và kiểm tra được phép |
| Mở cổng IdP, PAM và công cụ quản trị cần thiết | Vẫn đáp ứng công việc hợp lệ |
| Kiểm tra cập nhật, DNS, thời gian và bảo mật endpoint | Giới hạn truy cập không làm mất phụ thuộc bảo vệ |
| Truy cập desktop quản trị từ endpoint không đạt điều kiện | Không mặc định nguồn được tin chỉ vì đích được quản lý |
| Mô phỏng PAW mất trạng thái đáp ứng | Có quyết định chặn hoặc xử lý tại điểm truy cập phù hợp |
| Diễn tập sự cố email trên PAW | Liên lạc, thu hồi và phục hồi có người chịu trách nhiệm |
| Đưa máy trở lại sử dụng | Có bằng chứng sau xử lý, không chỉ trạng thái cũ |

Cần phân biệt chặn và phát hiện. Nếu một hành vi chỉ tạo cảnh báo, báo cáo không được mô tả rằng nó đã bị ngăn.

Cũng cần kiểm tra lối đi hợp lệ. Một PAW không thực hiện được công việc cần thiết có thể khiến người dùng tạo đường thay thế không được thiết kế.

## 12. Bằng chứng và trách nhiệm

### 12.1. Hồ sơ thiết kế

Nên xác định chủ sở hữu PAW, mục đích, tài khoản được phép dùng, baseline, ứng dụng, dịch vụ truy cập và đường chuyển hiện vật.

Các phụ thuộc và ngoại lệ cần có người chịu trách nhiệm, thời hạn hoặc điều kiện rà soát. Một ngoại lệ không rõ vòng đời dễ trở thành hoạt động thường trực.

### 12.2. Hồ sơ vận hành

Thông tin hữu ích có thể gồm:

- Định danh thiết bị và người sử dụng.
- Phiên bản baseline và trạng thái tuân thủ.
- Ứng dụng hoặc truy cập bị chặn, với thời điểm và kết quả.
- Ticket, hiện vật, phiên bản và nguồn được duyệt.
- Yêu cầu PAM, grant, tài sản và mã phiên.
- Sự kiện mất trạng thái, cô lập, thu hồi và phục hồi.

Không cần sao chép nội dung hộp thư để chứng minh một thiết bị đã cố truy cập dịch vụ email. Bằng chứng cần vừa đủ cho mục tiêu, được phân quyền và giữ theo vòng đời phù hợp.

### 12.3. Phối hợp giữa các đội

Đội endpoint quản trị baseline và tín hiệu thiết bị; đội định danh/PAM thực thi điều kiện truy cập; chủ sở hữu dịch vụ xác nhận công việc; đội ứng phó xử lý dấu hiệu sự cố.

Nếu dữ liệu endpoint không truyền được đến điểm cấp quyền, PAM có thể vẫn tiếp tục cho truy cập từ một máy không còn đáp ứng. Cần thử đường phối hợp và biết khoảng trễ thực tế.

## 13. Những sai lầm thường gặp

**Chỉ cấm ứng dụng email nhưng cho webmail.** Cần kiểm soát hoạt động, không chỉ phần mềm.

**Dùng hai tài khoản trên một endpoint rồi coi đã tách PAW.** Tài khoản và ranh giới thiết bị giải quyết những phần khác nhau.

**Cho rằng mọi trình duyệt đều bị cấm trên PAW.** Cổng quản trị web có thể cần trình duyệt; mục tiêu là nguồn và chức năng được phép.

**Tách email nhưng chạy nguyên lệnh từ thư.** Ranh giới kỹ thuật không thay việc xác minh công việc và nội dung.

**Tạo kênh copy tệp tùy ý để thuận tiện.** Nó có thể mang nội dung chưa kiểm tra vào PAW qua đường khác.

**Coi desktop từ xa luôn sạch bất kể endpoint nguồn.** Nguồn điều khiển là một phần của đường quản trị.

**Đóng email hoặc quét không phát hiện rồi kết luận an toàn.** Cần tiêu chí đánh giá và khôi phục theo hành động thực tế.

**Thu hồi một phiên mà quên các trạng thái khác.** Grant, token, phiên đích và credential có thể cần xử lý riêng.

## 14. Tự kiểm tra

1. Vì sao không cần lấy được mật khẩu thì một endpoint bị xâm nhập vẫn có thể gây hại?
2. Dùng tài khoản thường để đọc thư trên cùng PAW có giải quyết toàn bộ rủi ro không?
3. Vì sao profile trình duyệt khác không tương đương một ranh giới thiết bị độc lập?
4. Làm thế nào nhận một ticket được báo qua email mà không mở mailbox trên PAW?
5. Vì sao gõ lại lệnh từ email không chứng minh lệnh an toàn?
6. Một bản vá cần đi qua những bước nào trước khi được dùng từ PAW?
7. Nếu email đã được mở, cần xem các trạng thái PAM nào?
8. Một lần quét không phát hiện có đủ để đưa PAW trở lại sử dụng không?

### Gợi ý trả lời

1. Kẻ điều khiển endpoint có thể lợi dụng phiên, token hoặc hành động đã được phép.
2. Không. Cùng endpoint vẫn có những đường ảnh hưởng tới môi trường quản trị.
3. Nó có thể tách dữ liệu ứng dụng nhưng không tự tách toàn bộ hệ điều hành và đường điều khiển.
4. Dùng thiết bị hằng ngày để nhận thông báo, rồi mở nguồn công việc được phép trên PAW bằng mã tham chiếu.
5. Nội dung và tác động vẫn chưa được xác minh; cách nhập không thay đổi điều đó.
6. Xác minh nguồn, kiểm tra hiện vật, đánh giá và phê duyệt thay đổi, đưa vào kho được quản trị rồi thực hiện theo phạm vi.
7. Phiên IdP/PAM, grant JIT, phiên đích và credential liên quan, theo phạm vi điều tra.
8. Không tự đủ. Cần tiêu chí và bằng chứng sau xử lý phù hợp với sự kiện.

## Kết luận

Giữ email ngoài PAW giúp giảm việc đưa nội dung không đáng tin vào đường điều khiển đặc quyền. Nguyên tắc cần được hỗ trợ bằng tách môi trường, kiểm soát ứng dụng và dịch vụ, đường tiếp nhận công việc đủ dùng cùng luồng hiện vật được quản trị.

Trong PAM, PAW còn phải phối hợp với MFA, least privilege, JIT/JEA, vault, kiểm soát phiên và thu hồi có bằng chứng. Khi ranh giới bị vượt, cần đánh giá trạng thái thực tế và khôi phục mức tin cậy trước khi tiếp tục sử dụng quyền nhạy cảm.
