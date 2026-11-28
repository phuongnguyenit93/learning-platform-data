# Content inspection

## 1. Kiểm tra nội dung tệp là một yêu cầu bảo mật

Trong chương **File và resource security**, content inspection là quá trình xem xét dữ liệu thực tế của một tệp hoặc tài nguyên để quyết định nó có đáp ứng chính sách an toàn của hệ thống hay không. Quá trình này có thể gồm nhận diện định dạng, phân tích cấu trúc, tìm dấu hiệu nguy hiểm, kiểm tra giới hạn và tạo phiên bản nội dung được phép sử dụng.

Một tên tệp kết thúc bằng `.pdf` hoặc header `Content-Type: image/png` không chứng minh dữ liệu bên trong là tài liệu PDF hoặc ảnh PNG hợp lệ. Ngay cả khi đúng định dạng, nội dung vẫn có thể chứa chức năng bị cấm, gây quá tải parser hoặc khai thác thành phần xử lý.

Đối với đặc tả yêu cầu bảo mật, câu “upload phải được scan” chưa đủ. Cần trả lời:

- Những nguồn và loại tệp nào phải kiểm tra.
- Kiểm tra điều gì và tiêu chí nào quyết định cho phép.
- Tệp nằm ở đâu và có thể được sử dụng trong lúc chờ hay không.
- Kết quả kiểm tra gắn với chính xác phiên bản dữ liệu nào.
- Làm gì khi không đọc được, quá giới hạn hoặc công cụ gặp lỗi.
- Bằng chứng nào chứng minh tệp được công bố đã thực sự đi qua chính sách.

Sau bài học, người học cần có khả năng chuyển các rủi ro liên quan tới tệp thành yêu cầu cụ thể, đo được và liên kết được với kiến trúc, logging và ca kiểm thử.

Các định dạng, ngưỡng và thời gian trong bài là **ví dụ thiết kế**, cần xác nhận bằng mô hình đe dọa, đo tải và nhu cầu nghiệp vụ thực tế.

## 2. Xác định rủi ro và ranh giới tin cậy

Tệp từ người dùng, đối tác, URL nhập liệu, email, job đồng bộ hoặc một hệ thống khác đều có thể là dữ liệu chưa đáng tin tại ranh giới tiếp nhận. Việc nguồn đã xác thực không đồng nghĩa nội dung bên trong đã an toàn.

| Rủi ro | Ví dụ tác động | Hướng yêu cầu |
|---|---|---|
| Giả mạo định dạng | Tệp thực thi được đặt tên như ảnh | Xác định loại từ dữ liệu và xác thực cấu trúc theo allowlist |
| Nội dung chủ động | Tài liệu chứa chức năng chạy mã hoặc tải nội dung ngoài | Cấm, loại bỏ hoặc xử lý bằng luồng riêng đã đặc tả |
| Lỗi parser | Tệp có cấu trúc bất thường gây lỗi thành phần đọc | Parser được quản lý phiên bản, cô lập và giới hạn tài nguyên |
| Mã độc hoặc nội dung đã biết nguy hiểm | Tệp được dùng để phát tán hoặc gây hại khi mở | Kiểm tra theo công cụ và chính sách phù hợp |
| Cạn tài nguyên | Tệp nhỏ nhưng giải nén hoặc render tạo dữ liệu rất lớn | Cận dung lượng mở rộng, độ sâu, CPU, bộ nhớ và thời gian |
| Công bố trước kiểm tra | Người khác tải được tệp còn chờ scan | Cách ly và cổng cho phép sử dụng |
| Thay tệp sau scan | Scan phiên bản A nhưng phục vụ phiên bản B | Kết quả gắn với phiên bản bất biến và kiểm tra tại cổng công bố |
| Rò rỉ dữ liệu | Tệp nhạy cảm được gửi tới dịch vụ scan không phù hợp | Giới hạn đường truyền, nơi xử lý, quyền truy cập và dữ liệu log |

Content inspection không thay thế phân quyền. Một tệp đã được chấp nhận vẫn có thể chỉ thuộc về một tenant hoặc một nhóm người.

Nó cũng không bảo đảm phát hiện mọi mã độc hoặc mọi lỗi parser. Trạng thái cho phép nên được hiểu là **đạt chính sách kiểm tra đã định nghĩa với bằng chứng tương ứng**, không phải chứng nhận tuyệt đối rằng tệp vô hại trong mọi môi trường.

## 3. Các lớp kiểm tra và giới hạn của từng lớp

### 3.1. Metadata do caller cung cấp

Tên tệp, phần mở rộng, MIME header và kích thước tự khai chỉ là dữ liệu đầu vào. Chúng có thể hữu ích cho trải nghiệm và phát hiện không nhất quán, nhưng không được làm căn cứ duy nhất cho quyết định an toàn.

Cần quy định cách chuẩn hóa tên, phần mở rộng và cách xử lý khai báo không khớp. Tên hiển thị không được dùng trực tiếp làm đường dẫn lưu trữ hoặc định danh có quyền truy cập.

Nếu cho phép một MIME chung như `application/octet-stream`, điều đó không mở rộng tập định dạng được chấp nhận. Server vẫn phải xác định và kiểm tra nội dung theo chính sách.

### 3.2. Nhận diện định dạng từ dữ liệu

Magic bytes hoặc signature định dạng giúp nhận diện ban đầu. Tuy nhiên, một prefix đúng không chứng minh toàn bộ tệp hợp lệ, không có phần dữ liệu bổ sung hoặc không được trình đọc khác hiểu theo cách khác.

Yêu cầu cần kết hợp nhận diện với phân tích cấu trúc phù hợp:

- Chỉ cho phép các định dạng và biến thể nghiệp vụ thực sự cần.
- Kiểm tra cấu trúc, giới hạn và các thành phần liên quan của định dạng.
- Có quy tắc với nội dung mơ hồ, nhiều cách diễn giải hoặc không hỗ trợ.
- Không tự chuyển một lỗi nhận diện thành quyền phục vụ dữ liệu gốc.

Một tệp có thể được nhiều parser hiểu khác nhau, đôi khi gọi là polyglot. Không cần giả định một bộ kiểm tra có thể phát hiện mọi trường hợp. Có thể giảm rủi ro bằng allowlist hẹp, parser thống nhất, tái tạo đầu ra chuẩn và cách phục vụ hạn chế.

### 3.3. Nội dung và tính năng trong định dạng

Một định dạng hợp lệ vẫn có thể chứa chức năng không được phép trong sản phẩm.

| Nhóm nội dung | Ví dụ điều cần chốt |
|---|---|
| Ảnh | Kích thước, số pixel, số frame nếu hỗ trợ, metadata và khả năng decode |
| PDF | Số trang, mã hóa, tệp nhúng, hành động chủ động và tham chiếu ngoài theo chính sách |
| Tài liệu văn phòng | Macro, đối tượng nhúng, liên kết ngoài và biến thể định dạng được hỗ trợ |
| Archive | Loại archive, số phần tử, độ sâu lồng, tổng byte mở rộng và đường dẫn khi giải nén |
| Nội dung phục vụ trên trình duyệt | Kiểu nội dung, khả năng thực thi, nguồn phục vụ và chế độ hiển thị |

Không dùng câu “kiểm tra PDF” mà thiếu danh sách tính năng cho phép hoặc cấm. Với định dạng không đọc được đầy đủ, phải có quyết định rõ ràng thay vì mặc định đạt.

### 3.4. Kiểm tra mã độc và quy tắc nội dung

Nếu dùng công cụ phát hiện mã độc, cần chỉ rõ phạm vi, cấu hình, độ mới dữ liệu phát hiện, phiên bản và ý nghĩa kết quả. “Không tìm thấy dấu hiệu” khác với “không quét được”.

Kiểm tra bí mật, dữ liệu nhạy cảm hoặc nội dung vi phạm một chính sách nghiệp vụ có thể là lớp khác. Không suy rằng kết quả antivirus đã bao gồm kiểm soát dữ liệu được phép xuất hoặc chia sẻ.

Mỗi lớp phải tạo kết quả có thể phân biệt: đạt, vi phạm, không hỗ trợ, không đọc được hoặc lỗi xử lý. Quyết định cuối cùng do policy tổng hợp, không do một boolean chung che mất nguyên nhân.

## 4. Pipeline cách ly, kiểm tra và cho phép sử dụng

### 4.1. Mô hình trạng thái

```text
RECEIVING
  -> QUARANTINED
  -> INSPECTING
      -> ACCEPTED
      -> REJECTED
      -> INCONCLUSIVE
```

Ý nghĩa minh họa:

- `RECEIVING`: đang nhận byte; chưa phải một tệp hoàn tất.
- `QUARANTINED`: đã chốt nội dung, lưu riêng để chờ kiểm tra.
- `INSPECTING`: công việc kiểm tra đang chạy.
- `ACCEPTED`: phiên bản đã đạt policy cần thiết và có thể đi qua cổng sử dụng.
- `REJECTED`: đã xác định vi phạm.
- `INCONCLUSIVE`: chưa thể kết luận, ví dụ timeout, lỗi công cụ hoặc thiếu khả năng đọc.

Trong ví dụ, chỉ `ACCEPTED` được phép xuất hiện ở luồng tải xuống hoặc xử lý nghiệp vụ yêu cầu tệp đã kiểm tra. Các trạng thái còn lại không được mặc định phục vụ vì “chưa thấy mã độc”.

Cần phân biệt việc đã lưu upload với việc đã chấp nhận nội dung. API có thể trả upload ID khi nhận xong, nhưng không nên thông báo như thể tệp đã được phép chia sẻ.

### 4.2. Cách ly phải được thực thi bằng quyền truy cập

Kho cách ly không được public và không có đường tải trực tiếp dành cho người dùng thông thường. Người dùng biết object key hoặc upload ID cũng không được bỏ qua trạng thái.

Scanner có quyền đọc các object cần xử lý và quyền ghi kết quả theo phạm vi. Nó không cần quyền quản trị toàn bộ ứng dụng, đọc credential của tenant khác hoặc tự đánh dấu mọi tệp là đã công bố.

Nếu hệ thống nhận upload trực tiếp vào object storage, bước hoàn tất phải do thành phần tin cậy xác minh. Một thông báo “upload complete” từ client không chứng minh kích thước, phiên bản và nội dung đã sẵn sàng để kiểm tra.

### 4.3. Kết quả phải gắn với byte thực sự đã kiểm tra

Một record kết quả có thể gồm:

```text
upload_id
tenant_id
immutable_object_version
content_size
server_verified_content_digest
detected_type
inspection_policy_version
tool_profile_versions
job_id
outcome, reason_code
completed_at
derived_artifact_reference nếu có
```

Digest phải được xác định từ dữ liệu thực tế bởi luồng tin cậy. Digest do client tự gửi không đủ làm bằng chứng.

Sau khi finalize, không được thay byte tại cùng định danh phiên bản đã kiểm tra. Nếu cho cập nhật tệp, tạo phiên bản mới và bắt đầu lại kiểm tra cần thiết.

Kết quả của job cũ phải bị bỏ qua nếu không khớp object version hoặc phiên bản policy yêu cầu. Worker đọc phiên bản A rồi gửi verdict không được làm phiên bản B trở thành `ACCEPTED`.

Thông điệp trả kết quả cũng phải có nguồn đáng tin, liên kết job và được kiểm tra hợp lệ. Một endpoint nhận `upload_id` và `clean=true` từ client sẽ phá toàn bộ ranh giới kiểm soát.

### 4.4. Cổng sử dụng là một quyết định bảo mật

Trước khi phục vụ hoặc chuyển sang bước tiếp theo, server cần kiểm tra:

```text
caller có quyền với tài nguyên
AND artifact/version đúng phiên bản được chấp nhận
AND kết quả đáp ứng policy đang có hiệu lực theo quy tắc chuyển đổi
AND tài nguyên chưa bị thu hồi hoặc cách ly lại
```

Không chỉ kiểm tra ở giao diện danh sách. Download API, preview, chia sẻ, import vào nghiệp vụ và job nền phải dùng đúng điều kiện tương ứng.

Với URL ký sẵn hoặc cache đã được cấp, đổi trạng thái trong database không mặc nhiên thu hồi mọi bản truy cập còn hiệu lực. Cần định nghĩa cận hiệu lực của link, cách vô hiệu cache và cơ chế nếu nghiệp vụ yêu cầu chặn ngay. Những bản đã được người nhận tải về cũng không tự biến mất.

## 5. Giới hạn tài nguyên và cô lập môi trường xử lý

### 5.1. Tệp nhỏ không đồng nghĩa chi phí nhỏ

Kích thước trên đường truyền chỉ là một đại lượng. Nội dung nén, kích thước ảnh, số trang, số đối tượng hoặc cấu trúc lồng nhau có thể tạo chi phí lớn khi đọc.

Yêu cầu nên chốt theo loại nội dung:

| Đại lượng | Mục tiêu bảo vệ |
|---|---|
| Byte nhận trên từng tệp và toàn request | Băng thông, bộ nhớ đệm, dung lượng |
| Số tệp trong request và số upload đang chờ | Số object, hàng đợi và tài nguyên tenant |
| Tổng byte sau giải nén, số phần tử, độ sâu lồng | Chống khuếch đại dữ liệu và cạn tài nguyên |
| Số pixel, frame, trang hoặc đối tượng được phân tích | Chi phí decode, render và xử lý cấu trúc |
| CPU, bộ nhớ, thời gian chạy | Giới hạn tác động của tệp bất thường và parser lỗi |
| Số worker và độ dài hàng đợi | Giữ năng lực phục vụ, tránh backlog vô hạn |
| Byte và tuổi dữ liệu tạm | Ngăn rò rỉ dung lượng qua lỗi hoặc tác vụ bỏ dở |

Kiểm tra giới hạn byte trong lúc streaming, không chỉ sau khi đã nạp toàn bộ vào bộ nhớ. Với ảnh hoặc tài liệu, giới hạn khai báo trong metadata phải đi cùng giới hạn thực thi; parser có thể gặp dữ liệu không nhất quán.

Nếu một archive vi phạm ở phần tử cuối, các phần đã trích xuất trước đó vẫn phải ở khu vực tạm được kiểm soát. Không công bố từng phần như thể toàn bộ archive đã đạt.

### 5.2. Đường dẫn và tham chiếu trong nội dung

Nếu hỗ trợ giải nén, không để đường dẫn phần tử thoát thư mục đích, tạo liên kết ngoài phạm vi hoặc ghi đè dữ liệu không thuộc job. Cần xử lý đường dẫn tuyệt đối, thành phần đi lên thư mục, liên kết và các quy tắc đặc biệt của nền tảng.

Parser cũng không được tự do tải tài nguyên ngoài hoặc đọc tệp cục bộ chỉ vì nội dung chứa tham chiếu. Nếu nghiệp vụ cần truy xuất ngoài, phải dùng cơ chế fetch có kiểm soát và ranh giới tin cậy riêng.

Những kiểm soát này bảo vệ môi trường kiểm tra. Chúng không được coi là đã có chỉ vì thư viện hỗ trợ đọc định dạng tương ứng.

### 5.3. Sandbox và đặc quyền tối thiểu

Môi trường xử lý nên có:

- Danh tính dịch vụ và quyền lưu trữ tối thiểu.
- Giới hạn tài nguyên theo job hoặc nhóm công việc.
- Vùng tạm riêng và quy trình thu hồi dữ liệu tạm.
- Hạn chế network mặc định; chỉ mở những luồng đã được thiết kế.
- Không có credential nghiệp vụ hoặc quyền đọc tài nguyên không liên quan.
- Phiên bản parser và công cụ được quản lý, có khả năng cập nhật và rollback.

Việc cô lập giúp hạn chế tác động khi thành phần xử lý gặp lỗi, không thay thế bảo trì phần mềm. Không chạy parser trực tiếp trong request handler có toàn quyền chỉ để giảm độ trễ.

## 6. Tạo bản nội dung chuẩn hóa và xử lý khi không kết luận được

### 6.1. Bản dẫn xuất là một tài nguyên khác

Một số luồng có thể decode rồi encode lại ảnh, tạo preview hoặc tái tạo tài liệu theo tập tính năng được phép. Content disarm and reconstruction là một hướng loại bỏ hoặc tái tạo các thành phần theo chính sách thay vì phục vụ nguyên bản.

Cần đặc tả:

- Tính năng nào được giữ, bỏ hoặc thay đổi.
- Đầu ra nào được dùng để xem, tải hoặc xử lý tiếp.
- Có cần kiểm tra cấu trúc và nội dung đầu ra không.
- Bản gốc được giữ ở đâu, ai được truy cập và trong bao lâu.
- Quan hệ giữa digest, phiên bản bản gốc và bản dẫn xuất.

Không scan một bản preview rồi cho tải bản gốc chưa đáp ứng policy. Bản dẫn xuất phải có định danh, phiên bản và bằng chứng riêng.

Tái tạo không bảo đảm giữ mọi đặc tính của bản gốc. Nó có thể làm mất metadata, chức năng hoặc khả năng kiểm tra chữ ký gắn với byte gốc. Nghiệp vụ cần nêu rõ tính toàn vẹn nào phải giữ và khi nào phải từ chối thay vì tự sửa.

### 6.2. Không đọc được không phải là đạt

Ví dụ cần có quyết định rõ ràng:

| Tình huống | Hành vi minh họa |
|---|---|
| Tệp mã hóa không thể kiểm tra | Từ chối loại đó hoặc đưa sang luồng riêng có kiểm soát |
| Định dạng chưa hỗ trợ | Không công bố qua luồng chỉ cho phép loại đã hỗ trợ |
| Vượt CPU, bộ nhớ hoặc timeout | Dừng job, ghi nguyên nhân, không đánh dấu đạt |
| Công cụ không sẵn sàng | Giữ cách ly hoặc từ chối tiếp nhận theo hợp đồng năng lực |
| Bộ quy tắc quá cũ theo policy | Không dùng kết quả để cho phép công bố mới |
| Nhiều lớp kiểm tra mâu thuẫn | Tổng hợp theo quy tắc đã chốt, không chọn ngẫu nhiên verdict thuận lợi |

Retry phải có cận và giữ cùng tham chiếu dữ liệu bất biến. Sau khi hết số lần thử hoặc tuổi tối đa, hệ thống phải có trạng thái cuối hoặc quy trình xử lý rõ ràng. Không để hàng triệu upload chờ vô hạn.

## 7. Ví dụ đặc tả yêu cầu cho cổng tải tài liệu

### 7.1. Bối cảnh và phạm vi

Một cổng hỗ trợ nhiều tenant nhận JPEG, PNG và PDF. Người dùng tải tài liệu lên để người có quyền khác xem hoặc tải xuống. Rủi ro `R-FILE-04` là nội dung chưa kiểm tra bị công bố, parser bị gây quá tải hoặc kết quả scan bị dùng cho nhầm phiên bản.

Chính sách minh họa:

- Một request nhận một tệp, tối đa 20 MiB cho phần dữ liệu tệp; 1 MiB bằng 1.048.576 byte.
- Chỉ hỗ trợ những biến thể JPEG, PNG và PDF đã được liệt kê trong policy.
- Ảnh tối đa 25 triệu pixel và chỉ hỗ trợ ảnh tĩnh trong luồng này.
- PDF tối đa 100 trang; không nhận PDF mã hóa hoặc có tính năng chủ động, tệp nhúng hay tham chiếu ngoài bị policy cấm.
- Archive và định dạng khác bị từ chối qua luồng này.
- Ảnh được tạo lại thành bản dẫn xuất theo cấu hình chuẩn; chỉ bản dẫn xuất đạt yêu cầu mới được phục vụ.
- PDF chỉ được phục vụ nếu bản nội dung tương ứng đạt toàn bộ chính sách.

Giới hạn request tổng thể phải tính thêm phần bao gói giao thức và metadata có cận. Không nhầm mức 20 MiB của tệp thành quyền gửi request tổng thể không giới hạn.

### 7.2. Tập yêu cầu có thể kiểm chứng

| ID | Yêu cầu |
|---|---|
| SEC-CI-01 | Mọi tệp từ upload hoặc kênh nhập liệu có cùng mục đích phải đi qua policy tương ứng. Không có đường import, preview hoặc download bỏ qua cổng sử dụng. |
| SEC-CI-02 | Server phải kiểm tra số byte thực nhận trong lúc streaming và dừng khi vượt 20 MiB cho tệp. Tên, MIME và kích thước client khai không thay thế kiểm tra dữ liệu. |
| SEC-CI-03 | Nhận diện nội dung và parser phải xác nhận định dạng, biến thể, cấu trúc và các tính năng cho phép. Không kết luận đạt chỉ từ phần mở rộng hoặc magic bytes. |
| SEC-CI-04 | Tệp chưa hoàn tất, chưa kiểm tra, bị từ chối hoặc chưa kết luận phải nằm trong kho riêng có quyền truy cập hạn chế và không được phục vụ cho người dùng thông thường. |
| SEC-CI-05 | Finalize phải chốt phiên bản bất biến, số byte và digest được server xác minh. Mọi kết quả kiểm tra phải gắn với bộ định danh đó, policy version và job hợp lệ. |
| SEC-CI-06 | Ngoài xác thực cấu trúc, mọi tệp phải đi qua kiểm tra mã độc theo profile đã chọn. Lỗi công cụ hoặc dữ liệu phát hiện cũ quá 24 giờ theo nguồn thời gian được policy chấp nhận không được biến thành kết quả đạt cho công bố mới. |
| SEC-CI-07 | Mỗi attempt xử lý có cận 30 giây thời gian thực, 10 giây CPU và 256 MiB bộ nhớ trong môi trường thử của ví dụ. Vượt cận phải dừng xử lý có kiểm soát và không công bố nội dung. |
| SEC-CI-08 | Tối đa 8 worker đang xử lý và 200 job chờ trong phạm vi triển khai; mỗi tenant tối đa 20 upload chưa có quyết định cuối. Cấp suất phải an toàn khi nhiều replica cùng tiếp nhận. |
| SEC-CI-09 | Một upload có tối đa 3 attempt tự động và tuổi chờ quyết định tối đa 10 phút tính từ finalize. Hết cận mà chưa có kết quả tin cậy thì ở trạng thái không được công bố, có reason code rõ ràng. |
| SEC-CI-10 | Bản ảnh chuẩn hóa và preview phải có tham chiếu, phiên bản và kết quả xác thực đầu ra. Không dùng kết quả của bản dẫn xuất để tự cho phép tải bản gốc. |
| SEC-CI-11 | Cổng tải xuống phải kiểm tra quyền tenant, artifact/version được chấp nhận và trạng thái thu hồi. Cách phục vụ nội dung phải phù hợp loại tệp, không tự cho nội dung upload có quyền thực thi của ứng dụng. |
| SEC-CI-12 | Retry, message lặp hoặc verdict đến muộn không được đưa sai phiên bản hay job không còn hợp lệ sang trạng thái được công bố. |
| SEC-CI-13 | Thay policy, profile công cụ hoặc phát hiện mới phải có quy tắc rõ cho công bố mới và tệp đã chấp nhận: giữ hiệu lực, kiểm tra lại hoặc cách ly lại theo tác động. |
| SEC-CI-14 | Ghi nhận quyết định và binding đủ để điều tra mà không đưa toàn bộ nội dung tệp hoặc secret vào log. Dữ liệu cách ly và tạm có thời hạn lưu, quyền xóa và quy trình thu hồi rõ ràng. |

Các cận tài nguyên phải được đo với tập nội dung hợp lệ và nội dung bất thường đại diện. Chúng không có nghĩa mọi tệp dưới 20 MiB đều có thể xử lý thành công trong 30 giây. Trường hợp không xử lý được phải được phản ánh đúng, không hạ mức kiểm tra để đạt tỷ lệ thành công.

Mốc 24 giờ là điều kiện vận hành của ví dụ, không chứng minh công cụ phát hiện được mọi nguy cơ mới. Ngược lại, việc cập nhật dữ liệu phát hiện không tự chứng minh parser đã được vá.

### 7.3. Mã giả tổng hợp quyết định

```text
inspect(job):
    obtain trusted upload metadata and immutable object reference
    verify job is authorized for that tenant and version

    read the exact object under size and runtime limits
    verify observed size and digest match the finalized binding

    detect and validate an allowed format
    enforce format-specific structure and feature policy
    perform required malware inspection with an eligible tool profile
    create and validate required derived artifacts

    build result bound to:
        upload version + digest + policy version + job identity

    at the decision boundary:
        verify upload and active job still match the result
        verify required checks all produced eligible outcomes
        persist the decision and artifact references

    publish no access merely because a worker finished running
```

Mã giả mô tả ngữ nghĩa, chưa chỉ định công nghệ. Các bước đọc nội dung, tạo đầu ra và cập nhật trạng thái có thể thuộc nhiều thành phần; thiết kế phải bảo đảm không nhầm phiên bản hoặc công bố đầu ra dở dang khi có lỗi.

Một job hoàn tất mà phát hiện vi phạm phải tạo kết quả từ chối, không phải kết quả thành công chỉ vì process có exit code bằng 0. Ngược lại, worker chết hoặc trả lỗi không được ánh xạ thành “không tìm thấy mã độc”.

### 7.4. Thông báo cho người dùng

Có thể dùng các nhóm thông báo ổn định như:

```text
UPLOAD_RECEIVED
INSPECTION_PENDING
CONTENT_ACCEPTED
TYPE_NOT_ALLOWED
CONTENT_POLICY_VIOLATION
INSPECTION_UNAVAILABLE
```

Thông báo cần cho người dùng biết tệp đang chờ, bị từ chối hay cần thử lại, đồng thời không tiết lộ thông tin nội bộ không cần thiết về scanner hoặc hạ tầng.

Tên trạng thái và response phải nhất quán với quyền truy cập thực tế. Không hiển thị “sẵn sàng” khi URL đã cấp vẫn trỏ tới một bản gốc chưa đạt policy.

## 8. Tiêu chí kiểm thử và bằng chứng

### 8.1. Tách các loại bằng chứng

Cần có cả kiểm thử validator, tích hợp pipeline và cổng truy cập. Một unit test nhận MIME không chứng minh tệp thực tế đã bị cách ly.

Dùng fixture vô hại, nội dung bất thường được kiểm soát và mẫu kiểm thử an toàn mà công cụ hỗ trợ. Giả lập verdict giúp kiểm thử luồng quyết định, nhưng không thay thế kiểm tra công cụ thực sự đọc và trả kết quả theo profile dự kiến.

### 8.2. Ma trận kiểm chứng

| Ca kiểm thử | Thiết lập và kích thích | Kết quả mong đợi |
|---|---|---|
| T01 — Nội dung hợp lệ | Tải JPEG, PNG tĩnh và PDF thuộc biến thể cho phép | Chỉ có thể dùng sau khi đủ kết quả; artifact được phục vụ đúng phiên bản |
| T02 — Giả mạo tên hoặc MIME | Đặt tên và khai báo MIME cho phép nhưng dữ liệu thuộc loại bị cấm | Bị từ chối theo nội dung; không được công bố vì metadata thuận lợi |
| T03 — Prefix đúng, cấu trúc sai | Tệp có dấu hiệu nhận diện ban đầu nhưng không parse hợp lệ | Không đạt chỉ vì magic bytes; ghi nguyên nhân phù hợp |
| T04 — Tính năng bị cấm | PDF có tính năng mà policy cấm hoặc tệp mã hóa không được hỗ trợ | Không được công bố; phân biệt vi phạm và không đọc được theo policy |
| T05 — Giới hạn byte | Thử dưới, đúng và vượt 20 MiB; kích thước tự khai nhỏ hơn thực tế | Đếm byte thực; dừng khi vượt cận; không giữ upload dở như tệp đã đạt |
| T06 — Chi phí mở rộng | Nội dung kiểm thử có số pixel hoặc chi phí parse vượt cận | Dừng có kiểm soát; không vượt chính sách tài nguyên rồi vẫn chấp nhận |
| T07 — Kết quả phát hiện | Dùng mẫu kiểm thử an toàn cho công cụ và kiểm tra verdict tích hợp | Policy từ chối khi có kết quả vi phạm; binding và reason code đúng |
| T08 — Công cụ lỗi | Làm scanner timeout, mất kết nối hoặc trả kết quả không hợp lệ | Giữ trạng thái không được công bố; không chuyển lỗi thành đạt |
| T09 — Dữ liệu phát hiện quá cũ | Công cụ dùng bộ dữ liệu ngoài giới hạn freshness của policy | Không dùng kết quả để cho phép công bố mới |
| T10 — Truy cập trước kiểm tra | Gọi download, preview và đường object trực tiếp khi đang chờ | Không tải hoặc xử lý qua đường dành cho tệp đã chấp nhận |
| T11 — Đổi phiên bản | Tạo phiên bản B trong khi job của A đang xử lý | Verdict của A không làm B đạt; tải xuống không nhầm phiên bản |
| T12 — Message lặp hoặc đến muộn | Gửi lại verdict, đổi thứ tự kết quả hoặc dùng job không còn hiệu lực | Không bỏ qua binding, policy hoặc trạng thái quyết định hiện hành |
| T13 — Bản dẫn xuất | Tạo preview hoặc ảnh chuẩn hóa rồi thử truy cập bản gốc | Chỉ artifact được policy cho phép có thể dùng; không nâng quyền bản gốc theo preview |
| T14 — Quota và hàng đợi | Nhiều replica cùng nhận upload và claim worker | Không vượt cận chung; tenant không tạo vô hạn pending object |
| T15 — Thời hạn và retry | Liên tục gây lỗi tới số attempt hoặc tuổi tối đa | Không retry vô hạn; trạng thái và thông báo phản ánh đúng |
| T16 — Phân quyền và thu hồi | Thử tenant khác, tệp bị cách ly lại và link đã cấp | Cổng kiểm tra đúng quyền; hiệu lực link và cache đúng cận đã cam kết |
| T17 — Kênh nhập khác | Đưa cùng nội dung qua import, đồng bộ hoặc job nền | Không có đường cùng mục đích bỏ qua policy |
| T18 — Cô lập xử lý | Kiểm tra quyền lưu trữ, network và dữ liệu tạm của worker | Không truy cập ngoài phạm vi; kết quả lỗi không để lại quyền công bố |

Nếu hỗ trợ archive ở một policy khác, phải bổ sung ca đường dẫn thoát thư mục, liên kết, lồng nhiều cấp, số phần tử và tổng byte mở rộng. Không lấy kết quả của luồng không nhận archive để chứng minh giải nén an toàn.

### 8.3. Đối chiếu thứ được kiểm tra với thứ được phục vụ

Bằng chứng tích hợp cần liên kết:

```text
byte/version đã finalize
  -> job và profile đã chạy
  -> kết quả theo policy
  -> artifact/version được chấp nhận
  -> quyết định truy cập và byte thực tế được phục vụ
```

Đối chiếu cả quyền object storage, endpoint tải, preview và cache. Đếm số request trả lỗi không đủ nếu một URL khác vẫn tải được nội dung chưa đạt.

Các ca đồng thời nên có barrier hoặc lịch sự kiện kiểm soát được. Ghi rõ số replica, trạng thái đầu, phiên bản công cụ, policy và điều kiện gây lỗi. Một lần scan thành công không chứng minh pipeline an toàn khi message đến muộn hoặc process dừng giữa chừng.

## 9. Liên kết yêu cầu với rủi ro và kiến trúc

| Rủi ro hoặc mục tiêu | Yêu cầu liên quan | Quyết định kiến trúc | Bằng chứng |
|---|---|---|---|
| R-FILE-04: Công bố nội dung chưa đạt | SEC-CI-01, 04, 11 | Kho riêng và cổng sử dụng kiểm tra trạng thái, quyền | T10, T16, T17 |
| Giả mạo định dạng hoặc che tính năng | SEC-CI-02, 03, 06 | Nhận diện, parser và kiểm tra nội dung nhiều lớp | T02, T03, T04, T07 |
| Parser làm cạn tài nguyên | SEC-CI-07, 08, 09 | Sandbox, cận theo job và backpressure | T06, T08, T14, T15, T18 |
| Scan A nhưng phục vụ B | SEC-CI-05, 12 | Phiên bản bất biến, digest và job binding | T11, T12 và đối chiếu byte |
| Chỉ kiểm tra preview nhưng cho tải gốc | SEC-CI-10 | Artifact riêng và policy truy cập riêng | T13 |
| Công cụ hoặc policy thay đổi làm verdict cũ không còn phù hợp | SEC-CI-06, 13 | Freshness, phiên bản và kế hoạch kiểm tra lại | T09 và thử thay đổi policy |
| Không điều tra được quyết định | SEC-CI-14 | Record có cấu trúc, quyền truy cập và retention | Đối chiếu chuỗi upload tới download |

Thay parser, thêm một loại tệp, thêm preview hoặc mở kênh nhập mới đều có thể thay đổi ranh giới an toàn. Trong vòng đời phát triển, cần đánh giá lại các yêu cầu liên quan và chạy lại ca kiểm chứng chịu ảnh hưởng.

## 10. Logging, dữ liệu và vận hành

Log nên có upload reference, tenant reference được kiểm soát, object version, policy, profile, outcome, reason code, thời gian và mức tài nguyên sử dụng. Không đưa nội dung tệp, password mở tệp, credential hoặc payload nhạy cảm dư thừa vào log.

Các chỉ số hữu ích:

- Số upload theo trạng thái, loại nội dung và nhóm reason code.
- Độ trễ nhận tới quyết định, thời gian chờ queue và tuổi upload lâu nhất.
- Timeout, lỗi parser, lỗi công cụ và profile không đủ độ mới.
- CPU, bộ nhớ, byte tạm, dung lượng cách ly và số worker.
- Số kết quả không khớp phiên bản hoặc job bị từ chối.
- Số lần tải nội dung chưa được phép bị chặn và số tài nguyên bị thu hồi.

Dùng các nhãn có tập giá trị được kiểm soát. Không gắn filename, digest hoặc upload ID làm nhãn metric không giới hạn; thông tin tương quan chi tiết nên ở hệ thống log được phân quyền.

### 10.1. Chính sách dữ liệu

Tệp cách ly có thể chứa dữ liệu nhạy cảm như tệp được chấp nhận. Cần chốt nơi xử lý, quyền đọc, thời hạn giữ tệp bị từ chối, dữ liệu tạm và điều kiện xóa.

Nếu dùng dịch vụ kiểm tra bên ngoài, phải xác định nội dung nào được gửi, ai được phép chọn dịch vụ, thời gian giữ và cách kiểm soát truy cập. Không tự gửi tệp nhạy cảm tới một nơi chỉ vì công cụ đó thuận tiện.

Phân biệt quyền điều tra tệp cách ly với quyền tải tệp trong sản phẩm. Một ngoại lệ vận hành phải có chủ thể, phạm vi và audit; không sửa một cờ trạng thái để biến tệp chưa kết luận thành đã đạt mà thiếu policy.

### 10.2. Thay đổi verdict và cách phục vụ

Khi có phát hiện mới, cần xác định tệp nào bị cách ly lại, cách thu hồi truy cập và phạm vi người dùng cần được xử lý theo quy trình. Việc đánh dấu trong database phải đi cùng thực thi ở những điểm còn có thể phục vụ dữ liệu.

Cổng tải nên dùng `Content-Type` do server xác định, chế độ `Content-Disposition` phù hợp và các kiểm soát như `X-Content-Type-Options: nosniff` khi áp dụng. Với nội dung có rủi ro khi hiển thị, cân nhắc nguồn phục vụ và ngữ cảnh trình duyệt theo thiết kế. Các header này là lớp bổ sung, không thay thế inspection hoặc phân quyền.

Không nhất thiết parse lại toàn bộ tệp trong mỗi lần tải. Có thể kiểm tra record tin cậy và binding artifact tại cổng, trong khi việc scan hoặc kiểm tra lại diễn ra theo policy. Nếu cache quyết định, phải nêu thời hạn và hành vi khi tài nguyên bị thu hồi.

## 11. Các lỗi đặc tả thường gặp

| Phát biểu | Điểm thiếu | Cách viết rõ hơn |
|---|---|---|
| “Chỉ nhận file PDF” | Chưa biết xác định từ tên hay byte, có cho mã hóa hoặc tệp nhúng không | Nêu biến thể, parser, cấu trúc và tính năng cho phép |
| “Magic bytes đúng là đạt” | Không chứng minh toàn bộ tệp hợp lệ | Kết hợp nhận diện và xác thực theo định dạng |
| “Antivirus không báo gì là an toàn” | Có thể chưa quét được hoặc ngoài khả năng phát hiện | Phân biệt kết quả, lỗi và giới hạn của profile |
| “Upload xong thì trả link ngay” | Có thể công bố trước kiểm tra | Tách nhận upload khỏi quyền sử dụng |
| “Scan theo object key là đủ” | Byte có thể bị thay dưới cùng key | Ràng buộc với phiên bản bất biến và digest tin cậy |
| “Preview sạch nên bản gốc được tải” | Hai artifact khác nhau | Quyết định riêng cho artifact được phục vụ |
| “Tệp nhỏ thì không gây quá tải” | Chi phí mở rộng có thể rất lớn | Cận theo cấu trúc, tài nguyên và thời gian |
| “Scanner lỗi thì cho qua để giữ availability” | Biến sự cố kiểm soát thành đường công bố | Chọn rõ cách ly, từ chối hoặc ngoại lệ có phạm vi |
| “Đổi trạng thái là đã thu hồi mọi link” | Link hoặc cache có thể còn hiệu lực | Nêu cơ chế và cận thu hồi thực tế |
| “Đã có scan cho endpoint upload” | Import và job khác vẫn nhận cùng nội dung | Kiểm soát mọi kênh nhập và cổng sử dụng tương ứng |

## 12. Bài tập áp dụng

Bạn xây dựng cổng nộp hồ sơ nhận ảnh và tài liệu PDF. Hãy viết tập yêu cầu gồm:

1. Tác nhân, nguồn tệp và rủi ro đối với người nhận, parser và dữ liệu nhạy cảm.
2. Allowlist định dạng, biến thể và tính năng bị cấm.
3. Các cận byte, cấu trúc, CPU, bộ nhớ, thời gian và hàng đợi.
4. Vòng đời từ nhận dữ liệu tới được phép tải, gồm lỗi và retry.
5. Cách ràng buộc verdict với byte bất biến và đầu ra preview.
6. Quyền truy cập trước kiểm tra, sau chấp nhận và sau thu hồi.
7. Một ca giả mạo định dạng, một ca timeout, một ca đổi phiên bản và một ca truy cập chéo tenant.
8. Chuỗi truy vết từ rủi ro tới yêu cầu, quyết định kiến trúc và bằng chứng.

Tự kiểm tra: **Hệ thống có chứng minh được chính phiên bản được phục vụ đã đạt các kiểm tra bắt buộc, và có ngăn sử dụng khi chưa có kết luận tin cậy không?** Nếu chỉ biết một job scan từng chạy, yêu cầu vẫn còn thiếu.
