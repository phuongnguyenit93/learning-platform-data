# File type validation — Đặc tả yêu cầu kiểm tra loại tệp

## 1. Mục tiêu bảo mật của kiểm tra loại tệp

**File type validation** là quá trình xác định một tệp có thuộc định dạng và hồ sơ nội dung được phép cho một nghiệp vụ hay không, dựa trên dữ liệu thực tế và chính sách do máy chủ kiểm soát.

Ví dụ, chức năng tải ảnh đại diện có thể chỉ cho phép JPEG và PNG, còn chức năng đính kèm hồ sơ có chính sách khác. Tệp có đuôi ảnh hoặc khai báo MIME của ảnh chưa đủ chứng minh nội dung phù hợp.

Trong đặc tả yêu cầu bảo mật, mục tiêu là chuyển rủi ro từ tệp không tin cậy thành các điều kiện có thể kiểm chứng:

> Tệp nào được phép, kiểm tra bằng bằng chứng nào, xử lý bằng tài nguyên nào, khi chưa kết luận thì làm gì và chính xác phiên bản dữ liệu nào được phép đưa vào sử dụng?

Sau bài học, người đọc có thể:

- Phân biệt các tín hiệu nhận diện loại tệp và giới hạn của từng tín hiệu.
- Viết chính sách cho phép theo định dạng, cấu trúc và tính năng nội dung.
- Đặc tả cách ly, kiểm tra, chuyển đổi và công bố tệp.
- Liên kết quyết định chấp nhận với đúng nội dung đã kiểm tra.
- Xây dựng tiêu chí kiểm thử cho giả mạo loại, tệp hỏng, nội dung mơ hồ và lỗi dịch vụ kiểm tra.

Bài học tập trung vào yêu cầu bảo mật cho loại tệp. Quyền tải lên, quyền đọc tệp, giới hạn tài nguyên và logging là các yêu cầu liên quan cần phối hợp; chúng không được thay thế bằng một kết quả “đúng loại”.

## 2. Bốn lớp thông tin không có cùng độ tin cậy

| Lớp thông tin | Nguồn điển hình | Giá trị sử dụng | Giới hạn |
|---|---|---|---|
| Tên và phần mở rộng | Tên do client cung cấp. | Hướng dẫn trải nghiệm và kiểm tra tính nhất quán với chính sách. | Có thể bị đổi tên; không chứng minh cấu trúc dữ liệu. |
| MIME khai báo | Metadata của phần tệp hoặc trường do client gửi. | Gợi ý loại dự kiến và phát hiện khai báo mâu thuẫn. | Bên gửi có thể tự đặt; không phải kết luận của máy chủ. |
| Dấu hiệu nhận diện | Một số byte đặc trưng hoặc đặc điểm cấu trúc ban đầu. | Phân loại sơ bộ và chọn bộ phân tích phù hợp. | Có thể chỉ nhận ra một phần; không chứng minh toàn bộ tệp hợp lệ. |
| Kết quả phân tích | Bộ phân tích định dạng chạy trên dữ liệu thực tế. | Kiểm tra cấu trúc, khả năng giải mã và tính năng theo hồ sơ. | Có thể có lỗi hoặc khác biệt cách diễn giải; cần giới hạn tài nguyên và kiểm soát đầu ra. |

Với yêu cầu tải nhiều phần, kiểu nội dung của toàn bộ request và kiểu nội dung khai báo cho từng phần tệp là hai thông tin khác nhau. Không dùng việc request có cấu trúc tải tệp hợp lệ để kết luận loại của phần dữ liệu bên trong.

Một chuỗi tên như “avatar.jpg” chỉ là tên. Tương tự, vài byte đầu phù hợp một định dạng không chứng minh phần còn lại giải mã được, không chứa cấu trúc bị cấm hoặc không vượt giới hạn xử lý.

Quyết định chấp nhận cần kết hợp các bằng chứng theo một chính sách rõ ràng, thay vì coi bất kỳ tín hiệu đơn lẻ nào là đủ tin cậy.

## 3. Từ mô hình đe dọa tới yêu cầu kiểm tra

Giả sử nền tảng có ảnh đại diện và tài liệu đính kèm riêng theo tenant. Các tệp có thể được lưu, hiển thị trong trình duyệt và xử lý bởi worker.

| Kịch bản rủi ro | Tác động cần hạn chế | Yêu cầu cần dẫn xuất |
|---|---|---|
| Đổi đuôi tệp để trông giống ảnh | Nội dung không phù hợp được lưu hoặc đưa tới thành phần xử lý sai. | Đối chiếu loại do máy chủ xác định và phân tích theo hồ sơ cho phép. |
| Khai MIME của ảnh cho nội dung khác | Bộ kiểm tra chỉ dựa trên metadata bị bỏ qua. | Không dùng MIME client làm căn cứ chấp nhận duy nhất. |
| Tệp có dấu hiệu ban đầu đúng nhưng cấu trúc hỏng | Bộ giải mã lỗi, xử lý không ổn định hoặc kết luận nhầm. | Phân tích tới mức cần thiết theo hồ sơ, từ chối dữ liệu không hoàn chỉnh. |
| Tệp hợp lệ nhưng có tính năng không cho phép | Nội dung chủ động hoặc tham chiếu ngoài được xử lý ngoài dự kiến. | Kiểm tra tính năng theo định dạng và nghiệp vụ, không chỉ tên định dạng. |
| Container được nhận thành một tài liệu hợp lệ | Dữ liệu bên trong không đúng loại logic hoặc có thành phần bị cấm. | Kiểm tra cấu trúc và thành phần bên trong theo hồ sơ container. |
| Tệp nhỏ nhưng tốn nhiều tài nguyên khi giải mã | Cạn CPU, bộ nhớ hoặc nơi lưu tạm. | Giới hạn tài nguyên và kích thước sau xử lý. |
| Tệp bị thay sau khi đã kiểm tra | Công bố nội dung khác với nội dung đã được chấp nhận. | Gắn quyết định với phiên bản hoặc dấu vân tay do máy chủ xác lập. |
| Máy chủ và thành phần hiển thị hiểu tệp khác nhau | Nội dung được diễn giải theo loại nguy hiểm hơn dự kiến. | Giữ loại đầu ra xác định và kiểm soát cách phục vụ. |

Chuỗi truy vết nên giữ dạng:

> Rủi ro → chính sách loại và tính năng → yêu cầu → điểm kiểm tra trong kiến trúc → ca thử → bằng chứng.

Ví dụ, “dùng thư viện nhận MIME” là một lựa chọn thiết kế. Yêu cầu cần nêu điều kiện nào chứng minh tệp là ảnh được phép và kết quả nào ngăn tệp chưa được kiểm tra đi vào đường phục vụ.

## 4. Đặc tả hồ sơ tệp được phép

### 4.1. Chính sách cho phép theo nghiệp vụ

Mỗi điểm tiếp nhận cần có hồ sơ riêng hoặc tham chiếu một hồ sơ chung có phiên bản. Hồ sơ tối thiểu phải xác định:

- Định dạng logic được phép và các biến thể được hỗ trợ.
- Phần mở rộng được chấp nhận và cách xử lý khai báo MIME.
- Mức kiểm tra cấu trúc, khả năng giải mã và tính năng nội dung.
- Kích thước truyền, kích thước sau giải mã và các giới hạn đặc thù.
- Thành phần dùng để phân tích hoặc chuyển đổi cùng cấu hình liên quan.
- Hành vi với tệp hỏng, không hỗ trợ, mơ hồ hoặc chưa thể kết luận.
- Nội dung đầu ra được lưu và được phép phục vụ.
- Quyền sử dụng tệp, thời hạn cách ly và bằng chứng quyết định.

Danh sách cấm chỉ chặn một số loại đã biết và không tự bao phủ các cách biểu diễn khác. Chính sách cho phép giới hạn rõ bề mặt tiếp nhận; tuy nhiên vẫn phải phân tích nội dung của các loại được phép.

### 4.2. Hồ sơ ảnh đại diện minh họa

| Thuộc tính | Chính sách của ví dụ |
|---|---|
| Định dạng đầu vào | JPEG hoặc PNG trong phạm vi bộ kiểm tra được phê duyệt. |
| Phần mở rộng | JPEG dùng .jpg hoặc .jpeg; PNG dùng .png; so sánh không phân biệt hoa thường. |
| MIME client | Có thể thiếu hoặc khai kiểu nhị phân chung; nếu khai một loại cụ thể thì phải nhất quán với kết quả máy chủ. |
| Kích thước đầu vào | Tối đa 5 MiB, với 1 MiB bằng 1.048.576 byte. |
| Kích thước ảnh | Rộng và cao không quá 4.096 pixel; tổng không quá 16.000.000 pixel. |
| Nội dung được phép | Một ảnh tĩnh giải mã được; không chấp nhận cấu trúc hoặc tính năng nằm ngoài hồ sơ hỗ trợ. |
| Đầu ra phục vụ | PNG tĩnh do máy chủ mã hóa lại, không quá 10 MiB. |
| Metadata | Loại bỏ metadata gốc không cần thiết; quy tắc chuẩn hóa hiển thị được cố định trong hồ sơ. |
| Xử lý chưa rõ | Không công bố; giữ cách ly hoặc từ chối theo loại lỗi. |

Hai giới hạn về chiều và tổng pixel là độc lập. Ảnh có cả hai chiều trong mức cho phép vẫn có thể vượt tổng pixel. Kích thước byte đầu vào nhỏ cũng không bảo đảm ảnh sau giải mã dùng ít bộ nhớ.

Nếu chức năng cần ảnh động, định dạng vector hoặc kiểu khác, phải có hồ sơ riêng cho số khung, tính năng chủ động và tài nguyên liên quan. Không tự mở rộng hồ sơ ảnh tĩnh chỉ vì bộ phân tích nhận ra tên định dạng.

### 4.3. Tên tệp là metadata cần chuẩn hóa

Cần nêu rõ cách đọc tên từ giao thức, xử lý mã hóa và xác định phần mở rộng cuối. Không giải mã nhiều vòng không kiểm soát hoặc âm thầm xử lý các tên mơ hồ theo nhiều quy tắc khác nhau.

Trong ví dụ, tên có ký tự điều khiển, thành phần đường dẫn hoặc dấu kết thúc gây diễn giải mơ hồ phải bị từ chối theo hợp đồng. Tên có nhiều dấu chấm không tự chứng minh nguy hiểm; điều quan trọng là quy tắc nhất quán và kiểm tra nội dung thực tế.

Máy chủ sinh định danh lưu trữ riêng. Tên gốc được xử lý như dữ liệu hiển thị, không dùng để xác định quyền, tạo đường dẫn tùy ý hoặc quyết định trình xử lý nội dung.

## 5. Kiểm tra cấu trúc và tính năng theo định dạng

### 5.1. Nhận diện là bước chọn parser

Nhận diện sơ bộ giúp chọn bộ phân tích thích hợp. Quyết định cuối phải dựa trên mức phân tích được quy định trong hồ sơ.

Với ảnh của ví dụ, hệ thống cần giải mã thành dữ liệu ảnh có thể xử lý, kiểm tra kích thước và xác nhận nội dung thuộc phạm vi được hỗ trợ. Đọc được header hoặc tạo được thumbnail chưa chắc chứng minh phần còn lại đáp ứng toàn bộ hồ sơ.

Với định dạng tài liệu, yêu cầu có thể cần kiểm tra các tính năng như mã thực thi, nội dung nhúng, tham chiếu ngoài, mã hóa hoặc mật khẩu. Chỉ viết “cho phép tài liệu loại X” không làm rõ các quyết định đó.

### 5.2. Container có loại vật lý và loại logic

Một số định dạng tài liệu dùng container chứa nhiều thành phần. Nhận ra lớp container không chứng minh tài liệu logic bên trong đúng cấu trúc.

Hồ sơ phải xác định:

- Thành phần bắt buộc và cách chúng liên kết với nhau.
- Loại thành phần được phép hoặc bị cấm.
- Số mục, độ sâu lồng và tổng kích thước sau mở.
- Cách xử lý thành phần mã hóa hoặc không thể kiểm tra.
- Có được giải nén không và kiểm soát nơi ghi dữ liệu nếu có.
- Cách xử lý nội dung nhúng thuộc loại khác.

Bộ kiểm tra không được tự chọn “hợp lệ” khi chỉ nhận ra container mà không xác minh loại logic cần thiết cho nghiệp vụ.

### 5.3. Dữ liệu mơ hồ và nhiều cách diễn giải

Một tệp có thể chứa đặc điểm được nhiều bộ xử lý diễn giải khác nhau. Tệp như vậy thường được mô tả là polyglot nếu nó có thể được hiểu theo nhiều định dạng.

Không nên yêu cầu một bước kiểm tra đơn giản “phát hiện mọi polyglot”. Cần đặt mục tiêu có thể kiểm chứng: hồ sơ nào được hỗ trợ, cấu trúc ngoài hồ sơ bị xử lý ra sao, parser nào đưa ra quyết định và đầu ra nào được phục vụ.

Với phần dữ liệu dư, cấu trúc không nhận diện hoặc khai báo mâu thuẫn, phải có quy tắc cụ thể theo định dạng. Không mặc định rằng mọi byte sau một mốc nhận diện đều nguy hiểm, cũng không mặc định chúng luôn vô hại.

Đối với ảnh đại diện, việc giải mã và tạo đầu ra mới theo hồ sơ hẹp giúp giảm phụ thuộc vào cách thành phần khác diễn giải tệp gốc. Nó không chứng minh bộ giải mã không có lỗ hổng hoặc mọi nội dung đã trở nên vô hại.

### 5.4. Tệp được mã hóa hoặc không hỗ trợ

Nếu không đọc được phần cần kiểm tra vì mã hóa, mật khẩu hoặc tính năng chưa hỗ trợ, hệ thống chưa có bằng chứng đáp ứng hồ sơ. Kết quả phải là từ chối hoặc trạng thái chưa thể kiểm tra, theo chính sách.

Không được chuyển việc “không kiểm tra được” thành “không phát hiện vấn đề nên cho phép”.

## 6. Giới hạn tài nguyên của chính bộ kiểm tra

Tệp không tin cậy có thể làm quá trình phân tích tốn nhiều tài nguyên trước khi có kết luận. Yêu cầu loại tệp phải phối hợp với giới hạn xử lý:

| Tài nguyên | Giới hạn cần làm rõ |
|---|---|
| Dữ liệu nhận | Số byte đầu vào và thời gian nhận. |
| Dữ liệu sau giải mã | Pixel, số trang, số mục, dung lượng mở rộng hoặc cấu trúc trong bộ nhớ. |
| CPU và thời gian | Ngân sách xử lý, thời gian chờ và cách kết thúc khi vượt giới hạn. |
| Bộ nhớ | Mức tối đa cho một công việc và toàn nhóm worker. |
| Nơi lưu tạm | Tổng dung lượng, vòng đời và dọn khi lỗi hoặc bị hủy. |
| Công việc đồng thời | Số tác vụ chạy, số chờ và thời gian tối đa chờ. |
| Truy cập bên ngoài | Quyền mạng, hệ thống tệp và dịch vụ phụ thuộc mà parser được dùng. |

Trong cấu hình ảnh minh họa, mỗi công việc kiểm tra và chuyển đổi có giới hạn thời gian thực hai giây và bộ nhớ 128 MiB. Phép thử phải chứng minh việc giới hạn và dọn tài nguyên thực tế, không chỉ chứng minh bên gọi ngừng chờ.

Worker chỉ được cấp quyền tối thiểu. Trong hồ sơ ví dụ, parser không cần truy cập mạng và không được đọc dữ liệu của tenant khác. Thành phần xử lý cần được quản lý phiên bản, cấu hình và quy trình xử lý lỗ hổng.

Giới hạn đầu vào 5 MiB không thay thế các giới hạn giải mã. Nếu tệp đúng định dạng nhưng vượt ngân sách hồ sơ, kết quả vẫn là không đáp ứng chính sách tiếp nhận.

## 7. Cách ly và vòng đời quyết định

Tệp chưa được chấp nhận không được phục vụ qua đường tải xuống hoặc hiển thị thông thường. Việc nhận đủ dữ liệu chỉ xác nhận đã nhận một đối tượng, chưa xác nhận đối tượng được phép sử dụng.

| Trạng thái | Ý nghĩa | Được phục vụ như nội dung đã chấp nhận? |
|---|---|---|
| RECEIVING | Đang nhận dữ liệu trong giới hạn đầu vào. | Không. |
| QUARANTINED | Đã nhận đủ và lưu ở khu vực cách ly. | Không. |
| VALIDATING | Đang phân loại, phân tích và thực hiện các bước bắt buộc. | Không. |
| PENDING | Chưa kết luận do lỗi hạ tầng hoặc phụ thuộc kiểm tra. | Không. |
| ACCEPTED | Đã đủ bằng chứng cho đúng đối tượng đầu ra và hồ sơ. | Chỉ đầu ra đã được chấp nhận, theo quyền đọc. |
| REJECTED | Nội dung không đáp ứng chính sách. | Không. |
| EXPIRED | Hết thời hạn kiểm tra hoặc chờ xử lý mà chưa được chấp nhận. | Không. |

Trong ví dụ, lỗi hạ tầng có thể được thử lại tối đa ba lần trong vòng 24 giờ kể từ khi nhận đủ tệp. Sau thời hạn đó, đối tượng chưa được chấp nhận chuyển EXPIRED và dữ liệu cách ly được dọn theo chính sách.

Tệp sai loại hoặc sai cấu trúc có kết luận rõ ràng không được lặp kiểm tra vô hạn với hy vọng một lần khác sẽ được chấp nhận. Nếu cập nhật bộ kiểm tra hoặc thay đổi chính sách, việc đánh giá lại phải là công việc có phiên bản và bằng chứng mới.

Nếu hồ sơ yêu cầu quét mã độc hoặc bước kiểm tra bổ sung, mọi bước bắt buộc phải hoàn tất trước ACCEPTED. Timeout của dịch vụ kiểm tra không được chuyển thành kết quả đạt.

Cách ly cần có quyền truy cập và giới hạn riêng. Người tải lên có thể tra cứu trạng thái theo quyền, nhưng không được dùng đường xem trước hoặc đường tải tạm để bỏ qua điều kiện công bố.

## 8. Gắn kết quả với đúng nội dung được sử dụng

### 8.1. Nguy cơ kiểm tra một tệp, phục vụ tệp khác

Tình huống sai có thể xảy ra khi hệ thống:

1. Kiểm tra dữ liệu ở một khóa lưu trữ.
2. Đánh dấu khóa đó là hợp lệ.
3. Cho phép ghi đè dữ liệu tại cùng khóa.
4. Phục vụ dữ liệu mới dựa trên kết quả của dữ liệu cũ.

Tên tệp hoặc khóa lưu trữ không tự xác định nội dung bất biến. Quyết định cần liên kết với định danh nội bộ, phiên bản lưu trữ hoặc dấu vân tay nội dung do máy chủ xác lập, cùng thông tin độ dài và hồ sơ kiểm tra.

Dấu vân tay do client khai chỉ là đầu vào để đối chiếu, không thay cho phép tính hoặc xác minh của máy chủ. Metadata gắn nhãn “đã kiểm tra” cũng không đủ nếu người tải lên có thể sửa nó.

### 8.2. Chuyển đổi tạo ra đối tượng mới

Với ảnh đại diện, tệp gốc được giải mã và mã hóa lại thành PNG tĩnh theo hồ sơ. Đối tượng đầu ra phải có định danh hoặc phiên bản riêng và được kiểm tra các điều kiện đầu ra, gồm loại, kích thước, khả năng giải mã và metadata được phép.

Cần lưu liên kết:

~~~text
đối tượng gốc và phiên bản nội dung
  -> hồ sơ cùng phiên bản bộ kiểm tra
  -> kết quả phân tích
  -> công việc chuyển đổi và cấu hình
  -> đối tượng đầu ra và phiên bản nội dung
  -> quyết định chấp nhận
~~~

Nếu bước chuyển đổi thất bại, không dùng tệp gốc làm đầu ra thay thế chỉ vì tệp đó đã vượt qua bước nhận diện sơ bộ.

Quy tắc loại bỏ metadata phải đi cùng yêu cầu hiển thị. Ví dụ, nếu hướng ảnh được chuẩn hóa trước khi bỏ metadata gốc, hành vi đó cần nhất quán và có kiểm thử; không để bộ hiển thị khác nhau tự quyết định lại từ dữ liệu gốc.

### 8.3. Công bố và phục vụ theo kết quả máy chủ

Đường phục vụ chỉ dùng đối tượng đầu ra đã được chấp nhận và đúng phiên bản. Loại nội dung phản hồi, cách hiển thị hoặc tải xuống phải do máy chủ quyết định theo hồ sơ đầu ra, không sao chép tùy ý MIME từ client.

Cần tránh việc một đường xem trước, phân phối nội dung hoặc liên kết trực tiếp tự truy cập tệp gốc chưa được chấp nhận. Quyền đọc theo tenant và người dùng vẫn được kiểm tra riêng; đúng loại không đồng nghĩa được công khai.

Nếu nội dung được thay thế hoặc xử lý lại, phải có quyết định gắn với phiên bản mới. Không giữ nhãn chấp nhận cũ cho dữ liệu mới chỉ vì tên và phần mở rộng không đổi.

## 9. Bộ yêu cầu kiểm tra loại tệp mẫu

Bộ yêu cầu sau áp dụng cho hồ sơ ảnh đại diện ở mục 4. Các chức năng nhận tài liệu cần hồ sơ và ca kiểm thử riêng.

### SR-FT-001 — Chính sách máy chủ theo điểm tiếp nhận

Endpoint ảnh đại diện chỉ chấp nhận JPEG hoặc PNG trong hồ sơ đã định nghĩa. Chính sách có định danh và phiên bản do máy chủ quản lý; client không được chọn hồ sơ ít hạn chế hơn bằng cách đổi tham số.

Tên và phần mở rộng phải đáp ứng quy tắc chuẩn hóa. Phần mở rộng phải nhất quán với loại xác định từ nội dung. MIME khai báo cụ thể, nếu có, cũng phải nhất quán; thiếu MIME hoặc MIME nhị phân chung không thay thế các kiểm tra nội dung.

Bằng chứng nghiệm thu gồm các tổ hợp tên, MIME và dữ liệu phù hợp hoặc mâu thuẫn. Thay đổi MIME hoặc đuôi không được biến dữ liệu ngoài hồ sơ thành dữ liệu được chấp nhận.

### SR-FT-002 — Nhận diện và phân tích cấu trúc bắt buộc

Kết quả chấp nhận phải có bằng chứng rằng dữ liệu thực tế thuộc định dạng được phép và giải mã được theo hồ sơ. Chỉ khớp dấu hiệu đầu tệp không đủ.

Nội dung bị cắt, cấu trúc hỏng, tính năng không hỗ trợ hoặc cách diễn giải chưa thể kết luận phải bị từ chối hoặc giữ ở trạng thái chưa kết luận đúng chính sách; không tự đánh dấu đạt.

Bằng chứng phải gồm tệp có dấu hiệu sơ bộ phù hợp nhưng phần còn lại không hợp lệ, tệp rỗng và tệp hợp lệ thuộc định dạng không được phép.

### SR-FT-003 — Giới hạn dữ liệu và tài nguyên xử lý

Đầu vào không quá 5 MiB. Ảnh có chiều rộng và cao tối đa 4.096 pixel, đồng thời tổng không quá 16.000.000 pixel.

Mỗi công việc kiểm tra và chuyển đổi chịu giới hạn thời gian thực hai giây và bộ nhớ 128 MiB trong cấu hình nghiệm thu. Worker không có quyền truy cập mạng và chỉ có quyền dữ liệu cần thiết.

Khi chạm giới hạn, công việc không được tạo quyết định ACCEPTED. Tác vụ còn chạy, bộ nhớ và dữ liệu tạm phải được kết thúc hoặc cô lập an toàn theo cơ chế kiểm soát tài nguyên.

Bằng chứng phải đo cả thời gian, tài nguyên và trạng thái sau lỗi, kể cả khi lặp nhiều công việc không đạt. Việc bên gọi trả lỗi nhanh chưa chứng minh tài nguyên xử lý đã được thu hồi.

### SR-FT-004 — Quyết định gắn với phiên bản nội dung

Máy chủ phải xác lập định danh nội dung đã nhận đủ và liên kết kết quả kiểm tra với phiên bản đó. Một quyết định không được tái dùng cho dữ liệu đã bị thay hoặc ghi đè.

Đối tượng đầu ra có định danh hoặc phiên bản riêng. Trước khi công bố, hệ thống phải bảo đảm đầu ra được phục vụ đúng với đầu ra đã được chấp nhận.

Bằng chứng phải có tình huống thay dữ liệu giữa lúc kiểm tra và lúc công bố, sự kiện kết quả trùng hoặc đến muộn, cùng việc cập nhật metadata không có quyền.

### SR-FT-005 — Cách ly và lỗi kiểm tra không dẫn tới công bố

Mọi đối tượng chưa ACCEPTED phải bị chặn trên đường phục vụ thông thường, đường xem trước và liên kết trực tiếp do ứng dụng cấp.

Trong ví dụ, lỗi hạ tầng được thử lại tối đa ba lần trong 24 giờ kể từ lúc nhận đủ tệp. Quá thời hạn mà chưa có kết luận đạt phải chuyển EXPIRED; dữ liệu cách ly được dọn trong vòng một giờ tiếp theo, trừ hồ sơ cần giữ đã được phê duyệt riêng.

Lỗi parser, timeout hoặc mất phản hồi của bước bắt buộc không được coi là đạt. Kết quả xử lý đến sau khi đối tượng đã bị từ chối hoặc hết hạn không tự công bố lại đối tượng.

### SR-FT-006 — Đầu ra chuẩn hóa và đường phục vụ nhất quán

Ảnh đại diện được phục vụ phải là PNG tĩnh do máy chủ tạo, không quá 10 MiB, được xác nhận giải mã được theo hồ sơ đầu ra.

Metadata gốc không cần thiết phải bị loại bỏ; quy tắc chuẩn hóa hiển thị có cấu hình và phiên bản. Nếu mã hóa lại hoặc kiểm tra đầu ra thất bại, không phục vụ tệp gốc thay thế.

Metadata phục vụ nội dung được xác lập từ đầu ra, không lấy MIME hoặc tên gốc làm căn cứ duy nhất. Bằng chứng phải kiểm tra cả đường hiển thị chính và đường thay thế trong phạm vi ứng dụng.

### SR-FT-007 — Bằng chứng kiểm tra và quyền dữ liệu

Mỗi quyết định phải lưu tenant, định danh đối tượng, phiên bản hoặc dấu vân tay máy chủ xác lập, độ dài, loại xác định, hồ sơ, phiên bản thành phần xử lý, kết quả và lý do.

Sự kiện kết quả từ worker phải được xác minh nguồn và khớp công việc, đối tượng, phiên bản cùng hồ sơ. Client không được tự gửi nhãn “đã kiểm tra” để chuyển trạng thái.

Người dùng chỉ được đọc trạng thái và nội dung theo quyền. Log không chứa token, bí mật hoặc toàn bộ tệp; tên gốc phải được xử lý an toàn khi ghi log và hiển thị.

## 10. Ma trận kiểm thử và dữ liệu mẫu

Dùng bộ tệp thử an toàn, có nguồn và kỳ vọng rõ ràng. Mục tiêu là kiểm chứng chính sách, không cần sử dụng mã khai thác thật để kiểm tra một lỗi phân loại thông thường.

| Nhóm mẫu hoặc tình huống | Kỳ vọng của hồ sơ ảnh | Bằng chứng cần có |
|---|---|---|
| JPEG hợp lệ, tên .jpg và MIME nhất quán | Chấp nhận sau đủ bước, tạo PNG đầu ra. | Loại xác định, kết quả giải mã và định danh đầu ra. |
| PNG hợp lệ, thiếu MIME khai báo | Vẫn phải kiểm tra nội dung; có thể đạt nếu đủ mọi điều kiện. | Không dựa vào việc MIME bị thiếu để bỏ bước. |
| Dữ liệu văn bản đổi tên .jpg | Từ chối. | Không được chấp nhận chỉ theo tên hoặc MIME. |
| JPEG nhưng tên .png | Từ chối theo quy tắc nhất quán của ví dụ. | Mã lý do cho mâu thuẫn được lưu. |
| Dấu hiệu sơ bộ của ảnh nhưng dữ liệu bị cắt | Không chấp nhận. | Parser không kết luận đạt chỉ từ header. |
| Định dạng hợp lệ ngoài danh sách | Từ chối dù hệ thống nhận diện được tên loại. | Nhận diện và cho phép là hai quyết định khác nhau. |
| Ảnh vượt giới hạn pixel nhưng ít byte | Từ chối theo giới hạn sau giải mã. | Không chỉ có phép đo dung lượng truyền. |
| Nội dung mơ hồ hoặc cấu trúc ngoài hồ sơ | Từ chối hoặc giữ chưa kết luận theo chính sách. | Không chọn cách diễn giải có lợi để tự động cho qua. |
| Chuyển đổi tạo đầu ra quá 10 MiB | Không công bố. | Giới hạn đầu ra được kiểm tra riêng. |
| Parser timeout hoặc worker mất kết nối | Không công bố, áp quy tắc thử lại. | Trạng thái và tài nguyên còn hoạt động được theo dõi. |
| Tệp bị thay sau kiểm tra | Kết quả cũ không áp dụng cho dữ liệu mới. | Phiên bản hoặc dấu vân tay không khớp bị phát hiện. |
| Kết quả cũ đến sau khi đã hết hạn | Không tự phục hồi ACCEPTED. | Kiểm tra trạng thái và công việc còn hiệu lực. |
| Đường xem trước truy cập cách ly | Bị từ chối. | Không có đường vòng công bố trước kiểm tra. |
| Chủ thể tenant khác đọc file_id | Bị từ chối theo quyền. | Kết quả đúng loại không mở rộng phạm vi truy cập. |

Ví dụ kịch bản trọng tâm:

~~~gherkin
Feature: Quyết định loại tệp phải áp dụng cho đúng phiên bản nội dung

  Scenario: Không dùng kết quả cũ cho tệp đã bị thay
    Given một tệp ảnh của tenant A đã được kiểm tra ở phiên bản V1
    And kết quả kiểm tra liên kết với V1 và hồ sơ ảnh hiện hành
    When dữ liệu tại đường lưu trữ được thay bằng phiên bản V2
    And hệ thống chuẩn bị công bố dựa trên kết quả của V1
    Then V2 không được phục vụ như nội dung đã được chấp nhận
    And không được dùng tệp gốc hoặc đường xem trước làm phương án thay thế
    And sự khác biệt phiên bản được ghi nhận để xử lý
~~~

Cần có kiểm thử đường hợp lệ để xác nhận chính sách không vô tình chặn mọi tệp. Đồng thời kiểm tra các biên kích thước, tổng pixel, thời gian, số lần thử lại và thời hạn cách ly.

Khi cập nhật parser, cấu hình hoặc thư viện chuyển đổi, chạy lại bộ mẫu đại diện và các trường hợp đã từng gây bất đồng giữa các thành phần. Kết quả của phiên bản cũ không tự chứng minh phiên bản mới diễn giải giống hệt.

## 11. Audit và cách diễn giải kết quả

Một sự kiện quyết định minh họa:

~~~json
{
  "event": "file_validation_decision",
  "file_id": "example-file",
  "input_version": "V1",
  "profile": "avatar-image",
  "profile_version": 3,
  "detected_format": "png",
  "structural_validation": "passed",
  "output_id": "example-output",
  "output_version": "O1",
  "decision": "accepted",
  "correlation_id": "example-correlation"
}
~~~

Đây là cấu trúc dữ liệu minh họa, không phải giao diện của một sản phẩm. Hệ thống thực tế cần thêm thông tin về tenant và quyền ở nơi thích hợp, cùng bằng chứng cấu hình và thành phần xử lý.

Phải phân biệt các kết luận:

- Nhận diện được định dạng.
- Cấu trúc đáp ứng hồ sơ.
- Các tính năng nội dung đáp ứng chính sách.
- Đầu ra chuẩn hóa đáp ứng hồ sơ.
- Những bước bổ sung như quét mã độc đã hoàn tất, nếu chúng là yêu cầu bắt buộc.
- Đối tượng cụ thể được chấp nhận và được phép phục vụ.

“Đúng loại” không đồng nghĩa “không có mã độc”, “không có dữ liệu nhạy cảm” hoặc “được phép công khai”. Mỗi mục tiêu cần yêu cầu và bằng chứng riêng.

Chỉ số vận hành nên tách tệp bị từ chối theo chính sách, lỗi bộ kiểm tra, công việc chưa kết luận, thời gian chờ và số lần đường phục vụ bị ngăn do chưa đủ điều kiện. Nếu mọi lỗi đều bị gộp thành “sai loại”, khó phát hiện khi chính hệ thống kiểm tra đang gặp sự cố.

## 12. Những cách viết dễ gây hiểu sai

| Cách viết chưa đủ | Điểm thiếu | Cách làm rõ |
|---|---|---|
| “Chỉ nhận file .jpg.” | Đổi tên không thay đổi dữ liệu thực tế. | Đặc tả định dạng, cấu trúc và quy tắc nhất quán với tên. |
| “Content-Type là ảnh thì cho phép.” | MIME khai báo do client kiểm soát. | Dùng kết quả máy chủ và parser theo hồ sơ. |
| “Khớp magic bytes là tệp an toàn.” | Chỉ chứng minh một tín hiệu nhận diện, chưa chứng minh phần còn lại. | Kiểm tra cấu trúc và tính năng cần thiết. |
| “Parser nhận được thì nhận mọi biến thể.” | Có thể vượt phạm vi hỗ trợ hoặc chứa tính năng không cho phép. | Có hồ sơ định dạng và hành vi với biến thể chưa hỗ trợ. |
| “Tệp dưới 5 MiB không gây cạn tài nguyên.” | Kích thước giải mã hoặc công việc bên trong có thể lớn. | Giới hạn đầu ra, CPU, bộ nhớ và nơi lưu tạm. |
| “Kiểm tra một lần theo tên file là đủ.” | Nội dung có thể thay ở cùng tên hoặc khóa lưu. | Gắn kết quả với phiên bản nội dung đã xác minh. |
| “Timeout thì cho qua để không làm người dùng chờ.” | Chưa có bằng chứng đáp ứng chính sách. | Giữ cách ly và áp thời hạn, thử lại hữu hạn. |
| “Chuyển đổi lỗi thì trả ảnh gốc.” | Có thể bỏ qua điều kiện đầu ra và phục vụ dữ liệu chưa được chấp nhận. | Không có đường dự phòng làm yếu hồ sơ. |
| “Đã đúng loại thì được tải công khai.” | Loại tệp không quyết định quyền đọc. | Áp quyền theo đối tượng và tenant riêng. |

## 13. Duy trì yêu cầu trong vòng đời phát triển

Khi phân tích nghiệp vụ, xác định vì sao cần từng loại tệp và tính năng nào thực sự cần thiết. Tránh mở danh sách chỉ vì một thành phần kỹ thuật có thể đọc thêm định dạng.

Khi mô hình hóa đe dọa, xem xét giả mạo tên, MIME, dữ liệu mơ hồ, tài nguyên giải mã, thay tệp sau kiểm tra và đường phục vụ bỏ qua cách ly. Liên kết từng tình huống với yêu cầu SR-FT tương ứng.

Khi thiết kế, xác định nơi nhận dữ liệu, vùng cách ly, bộ kiểm tra, worker chuyển đổi và đường phục vụ. Với từng ranh giới, nói rõ thông tin nào tin cậy và thành phần nào có quyền chấp nhận.

Khi phát triển và nghiệm thu, kiểm tra cả nội dung đầu vào, đối tượng đầu ra và quyết định công bố. Khi vận hành, theo dõi công việc chưa kết luận, thay đổi tỷ lệ từ chối, lỗi parser và các trường hợp kết quả không khớp phiên bản.

Bài tập áp dụng: một cổng tuyển dụng nhận ảnh đại diện và hồ sơ tài liệu. Hãy viết hai hồ sơ loại tệp riêng, chỉ rõ quy tắc với metadata, nội dung nhúng, mã hóa, giới hạn xử lý và đầu ra được phục vụ. Với mỗi hồ sơ, nêu ca kiểm thử cho MIME sai, dữ liệu bị cắt, vượt giới hạn, lỗi dịch vụ kiểm tra và thay nội dung sau khi có kết quả.

