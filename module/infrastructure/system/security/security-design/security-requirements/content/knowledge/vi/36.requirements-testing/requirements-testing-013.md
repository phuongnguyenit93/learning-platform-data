# Privacy test: kiểm chứng yêu cầu bảo vệ quyền riêng tư

## 1. Privacy test cần trả lời điều gì?

Privacy test là kiểm thử nhằm đánh giá hệ thống có xử lý dữ liệu về cá nhân theo đúng yêu cầu quyền riêng tư đã được xác định hay không.

Một hệ thống có thể xác thực và phân quyền đúng nhưng vẫn thu thập quá nhiều thông tin, gửi nội dung hỗ trợ sang công cụ phân tích không cần thiết hoặc giữ dữ liệu lâu hơn chính sách đã chốt. Vì vậy, kiểm thử quyền riêng tư cần đi xa hơn câu hỏi “người lạ có đọc được dữ liệu không?”.

Các câu hỏi chính gồm:

- Hệ thống thu thập dữ liệu nào, cho mục đích nào?
- Có dữ liệu không cần thiết bị thu hoặc suy ra không?
- Danh tính, thành phần hoặc bên nhận nào được phép xử lý từng trường?
- Lựa chọn của người dùng có được thực thi ở các đường xử lý liên quan không?
- Dữ liệu được lưu ở đâu, trong bao lâu và bị xóa theo cách nào?
- Cache, chỉ mục, log, công việc nền, bản xuất và backup có làm dữ liệu xuất hiện lại không?
- Phản hồi và bằng chứng có hỗ trợ đúng phạm vi kết luận hay đang hứa nhiều hơn điều đã kiểm chứng?

Đầu vào của privacy test là yêu cầu sản phẩm, luồng dữ liệu, phân loại dữ liệu, chính sách áp dụng và tiêu chí kiểm chứng. Các nghĩa vụ áp dụng phải được người có trách nhiệm xác định; bộ thử không tự suy ra nghĩa vụ hoặc thời hạn bắt buộc từ một tên tính năng.

Bài học sử dụng các mốc và chính sách giả định để minh họa cách kiểm chứng. Chúng không phải các mốc mặc định áp dụng cho mọi tổ chức.

## 2. Phân biệt quyền riêng tư với bảo mật dữ liệu

Bảo mật dữ liệu và quyền riêng tư có nhiều phần giao nhau nhưng không đồng nhất.

| Góc nhìn | Ví dụ câu hỏi kiểm chứng |
| --- | --- |
| Bí mật dữ liệu | Người không có quyền có đọc được nội dung phiếu hỗ trợ không? |
| Toàn vẹn | Dữ liệu và lựa chọn quyền riêng tư có bị sửa trái phép không? |
| Khả dụng và phục hồi | Dữ liệu cần thiết có khôi phục được theo yêu cầu không? |
| Mục đích xử lý | Dữ liệu liên hệ có bị sử dụng cho hoạt động ngoài mục đích đã cho phép không? |
| Tối thiểu hóa | Dashboard thống kê có thực sự cần email và nội dung phiếu không? |
| Vòng đời | Dữ liệu hết thời hạn có còn trong chỉ mục, bản xuất hoặc luồng nền không? |
| Tính minh bạch và thực thi lựa chọn | Giao diện nói đã tắt phân tích nhưng hệ thống còn gửi sự kiện không? |

Một tài khoản phân tích được cấp quyền kỹ thuật vẫn có thể nhận những trường không cần thiết cho mục đích của nó. Đây là khoảng trống quyền riêng tư dù cơ chế đăng nhập hoạt động đúng.

Ngược lại, tài liệu mô tả mục đích đúng chưa chứng minh API, SDK và công việc nền thực sự tuân theo mô tả đó.

### 2.1. Nhận diện dữ liệu liên quan đến cá nhân

Cần xem xét cả dữ liệu trực tiếp lẫn dữ liệu có thể liên kết:

- Tên, email, số điện thoại và địa chỉ.
- Định danh tài khoản, thiết bị hoặc phiên.
- Nội dung tự do trong phiếu hỗ trợ.
- Metadata như thời điểm, lịch sử thao tác và thông tin liên kết.
- Kết quả suy luận hoặc phân nhóm gắn được với một người.
- Mã thay thế vẫn có thể nối lại với danh tính.

Băm, mã hóa, che bớt ký tự hoặc thay tên bằng mã không tự làm dữ liệu trở thành vô danh. Nếu vẫn có khả năng liên kết hoặc nhận diện lại trong bối cảnh sử dụng, cần đánh giá và bảo vệ tương ứng.

Không được đánh dấu một trường “không nhạy cảm” chỉ vì không nhìn thấy tên thật ngay trong giá trị.

## 3. Bắt đầu bằng bản đồ dữ liệu và yêu cầu đo được

### 3.1. Theo dữ liệu qua toàn bộ luồng

Một sơ đồ tối thiểu nên mô tả:

**Nguồn thu thập → API → kho nghiệp vụ → cache/chỉ mục → xử lý nền → bên nhận → bản xuất → log/backup → xóa hoặc hết hạn.**

Một trường không được lưu ở cơ sở dữ liệu chính vẫn có thể đi vào log request, hàng đợi lỗi hoặc công cụ theo dõi phía trình duyệt.

Với mỗi luồng quan trọng, ghi:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Loại dữ liệu | Những trường, định danh hoặc nội dung nào được xử lý? |
| Chủ thể và phạm vi | Dữ liệu liên quan đến ai, tài khoản hoặc tenant nào? |
| Mục đích | Chức năng nào cần dữ liệu này? |
| Nguồn và bên nhận | Ai tạo, thành phần nào nhận, có bên ngoài nào không? |
| Quyền và lựa chọn | Ai được dùng; lựa chọn người dùng nào chi phối việc xử lý? |
| Nơi lưu và bản sao | Có cache, chỉ mục, queue, tệp, log hoặc backup nào? |
| Vòng đời | Khi nào bắt đầu lưu, khi nào hết hạn, có ngoại lệ nào? |
| Xóa và phục hồi | Xóa qua cơ chế nào, khi khôi phục dữ liệu cũ phải làm gì? |
| Kiểm chứng | Quan sát ở đâu, bằng cách nào và với giới hạn gì? |

Danh sách này cần phản ánh kiến trúc thực tế. Không coi việc không biết một bản sao tồn tại là bằng chứng bản sao đó không tồn tại.

### 3.2. Chuyển mục tiêu thành yêu cầu

Mục tiêu:

> Tôn trọng quyền riêng tư và chỉ dùng dữ liệu khi cần.

Yêu cầu có thể kiểm chứng hơn:

> Sự kiện phân tích tùy chọn chỉ chứa các trường trong danh sách đã phê duyệt; không chứa email, số điện thoại hoặc nội dung phiếu hỗ trợ. Việc gửi sự kiện chỉ được thực hiện khi lựa chọn cho mục đích này đang bật.

Yêu cầu cần nói rõ:

- Mục đích và các trường thuộc phạm vi.
- Nguồn quyết định có thẩm quyền.
- Điều kiện bật, tắt hoặc thay đổi.
- Các điểm phải thực thi.
- Ngưỡng thời gian nếu có xử lý trễ.
- Hành vi lỗi và tiêu chí kết luận.

Không dùng một câu “đã ẩn dữ liệu” nếu chưa xác định ẩn ở giao diện, phản hồi API, dữ liệu lưu hay mọi bản sao liên quan.

## 4. Ví dụ xuyên suốt: cổng hỗ trợ khách hàng nhiều tenant

### 4.1. Bối cảnh sản phẩm

Một cổng hỗ trợ có các chức năng:

1. Người dùng tạo hồ sơ liên hệ và gửi phiếu hỗ trợ.
2. Nhân viên xử lý phiếu trong phạm vi được cấp.
3. Quản lý xem dashboard thống kê.
4. Sản phẩm có phân tích hành vi tùy chọn.
5. Người dùng có thể yêu cầu xuất dữ liệu hoặc xóa dữ liệu theo phạm vi chính sách đã công bố.
6. Hệ thống có cache, chỉ mục tìm kiếm, worker, log và backup.

Chính sách ví dụ chọn phân tích hành vi là chức năng mặc định tắt, chỉ bật khi người dùng chọn cho mục đích đó. Đây là lựa chọn của sản phẩm minh họa; không suy ra rằng mọi hoạt động xử lý dữ liệu đều phải dùng cùng một cơ chế.

Phần xử lý phiếu cần thiết cho dịch vụ và phần phân tích tùy chọn được phân biệt trong yêu cầu. Tắt phân tích không được tự làm người dùng mất khả năng gửi phiếu.

### 4.2. Danh mục dữ liệu minh họa

| Nhóm | Dữ liệu | Mục đích và giới hạn |
| --- | --- | --- |
| Hồ sơ liên hệ | Tên, email, số điện thoại nếu người dùng cung cấp | Liên hệ phục vụ hỗ trợ; không tự chuyển sang phân tích tùy chọn |
| Phiếu hỗ trợ | Nội dung, tệp đính kèm, trạng thái, người tham gia | Giải quyết phiếu trong phạm vi được cấp; có thể chứa dữ liệu của nhiều người |
| Thống kê | Số phiếu, nhóm vấn đề, thời gian xử lý | Dashboard không cần danh sách email hoặc toàn bộ nội dung phiếu |
| Phân tích tùy chọn | Mã sự kiện, thời điểm, mã phân tích nếu cần | Theo lựa chọn cho mục đích đã xác định; có danh sách trường cho phép |
| Audit và log | Hành động, kết quả, đối tượng cần thiết, correlation ID | Truy vết và vận hành; cấm bí mật và nội dung thừa theo quy tắc |
| Bản xuất | Tập dữ liệu đã chuẩn bị cho một yêu cầu | Kiểm tra chủ sở hữu, người liên quan, thời hạn và quyền tải |
| Backup | Bản sao phục hồi có thể chứa dữ liệu cũ | Truy cập hạn chế, thời hạn riêng, có bước xử lý yêu cầu xóa trước khi mở lại |

Nội dung phiếu và tệp đính kèm cần được đưa vào phạm vi. Chỉ xóa trường email trong bảng hồ sơ chưa chứng minh không còn dữ liệu liên quan trong văn bản tự do.

### 4.3. Các yêu cầu nguồn

| ID | Yêu cầu minh họa | Hướng kiểm chứng |
| --- | --- | --- |
| PRV-COL-01 | Biểu mẫu và API chỉ thu các trường hồ sơ đã xác định; không tự thu thêm thông tin ngoài danh mục | Gửi dữ liệu tổng hợp và kiểm tra request, nơi lưu, các luồng chuyển tiếp |
| PRV-PUR-01 | Dữ liệu liên hệ và nội dung phiếu không được gửi vào luồng phân tích tùy chọn | Đối chiếu schema sự kiện, queue và bên nhận mô phỏng |
| PRV-CHO-01 | Phân tích tùy chọn mặc định tắt; thay đổi sang tắt phải ngăn sự kiện mới trong tối đa 60 giây từ khi lựa chọn được commit | Kiểm tra trước chọn, sau bật, sau tắt và công việc đang chờ |
| PRV-ACC-01 | Nhân viên chỉ truy cập phiếu và các trường trong phạm vi được cấp; dashboard chỉ trả dữ liệu thống kê đã xác định | Kiểm tra vai trò, tenant, trường API và đường xuất |
| PRV-LOG-01 | Các nguồn log trong phạm vi không chứa token, số điện thoại đầy đủ hoặc nội dung phiếu bị cấm | Tạo sự kiện và lỗi bằng marker tổng hợp, đối chiếu nguồn |
| PRV-EXP-01 | Bản xuất chỉ cho người yêu cầu hợp lệ tải trong đúng phạm vi dữ liệu; xử lý dữ liệu người khác theo quy tắc đã duyệt | Kiểm tra danh tính, tenant, nội dung và thời hạn tải |
| PRV-DEL-01 | Trong 24 giờ từ khi yêu cầu xóa được xác minh và tiếp nhận, dữ liệu thuộc phạm vi xóa trực tuyến phải được xử lý tại các kho đã liệt kê | Kiểm tra từng kho, bản sao và job liên quan |
| PRV-REC-01 | Backup hết hạn theo chu kỳ tối đa 30 ngày từ lúc tạo; dữ liệu khôi phục không được mở lại cho nghiệp vụ trước khi áp dụng các yêu cầu xóa liên quan | Kiểm tra chính sách hết hạn và diễn tập phục hồi có cổng đối soát |

Các ngưỡng 60 giây, 24 giờ và 30 ngày là giả định phục vụ ví dụ. Yêu cầu thực tế cần căn cứ phù hợp và cách đo rõ ràng.

Phạm vi PRV-DEL-01 không tự bao gồm việc xóa ngay mọi backup. Nếu có dữ liệu phải giữ theo chính sách hoặc nghĩa vụ đã xác nhận, cần mô tả loại dữ liệu, mục đích, quyền truy cập, thời hạn và ngoại lệ cụ thể.

Không được trả lời “mọi dữ liệu đã bị xóa hoàn toàn” khi mới hoàn tất phần xóa trực tuyến nhưng backup hoặc nhóm dữ liệu giữ lại vẫn tồn tại.

## 5. Tạo dữ liệu thử và cách quan sát

### 5.1. Dùng dữ liệu tổng hợp có khả năng truy vết

Tạo hai tenant, nhiều người dùng và các dấu nhận diện riêng cho mỗi lần chạy:

| Đối tượng | Dữ liệu thử |
| --- | --- |
| USER-A | Thuộc tenant A, hồ sơ có marker liên hệ riêng |
| USER-A2 | Cùng tenant A, có dữ liệu trong một phiếu chung |
| USER-B | Thuộc tenant B, không có quyền trên phiếu tenant A |
| AGENT-A | Nhân viên được cấp một phần phiếu tenant A |
| MANAGER-A | Xem dashboard theo tập trường thống kê |
| Analytics sink | Bên nhận mô phỏng cho luồng phân tích tùy chọn |

Có thể dùng địa chỉ thử như `privacy-user-a@example.invalid` và marker `SYNTHETIC-PRIVACY-<run-id>`. Không gửi thông báo ra người thật hoặc dùng dữ liệu khách hàng để làm fixture.

Gắn marker vào các nơi cần kiểm tra, chẳng hạn trường hồ sơ, nội dung phiếu và tệp thử. Mỗi nhóm nên có marker khác nhau để biết loại dữ liệu nào đã đi sai luồng.

Không chỉ tìm một chuỗi tên chung dễ trùng với dữ liệu khác.

### 5.2. Không coi tìm marker là phương pháp duy nhất

Dữ liệu có thể bị mã hóa biểu diễn, nén, băm hoặc chuyển thành một định danh khác. Không tìm thấy chuỗi gốc chưa chứng minh không có dữ liệu cá nhân đi qua.

Kết hợp:

- Kiểm tra schema và danh sách trường thực tế.
- Theo dõi ánh xạ định danh và quan hệ liên kết được phép.
- Kiểm tra dữ liệu sau các phép biến đổi đã biết.
- Quan sát request, sự kiện, bên nhận và dữ liệu lưu.
- Xác nhận nguồn và khoảng thời gian quan sát đầy đủ cho test.

Nếu sự kiện chỉ chứa mã phân tích, vẫn cần biết mã đó có thể gắn lại với tài khoản hay không. Không tự đặt nhãn “vô danh” cho mọi mã ngẫu nhiên.

### 5.3. Chính bộ thử cũng phải bảo vệ dữ liệu

Giữ fixture tổng hợp và quyền quan sát tối thiểu cần thiết. Báo cáo không nên sao chép token, nội dung riêng tư thật hoặc thông tin xác thực để người khác tái hiện.

Khi lưu mẫu request hay tệp xuất, dùng dữ liệu tổng hợp và ghi rõ nguồn. Nếu cần che một bằng chứng, phải giữ đủ quan hệ để người rà soát hiểu kết luận.

## 6. Kiểm thử thu thập, tối thiểu hóa và mục đích

### 6.1. Thu thập đúng danh mục

Kiểm tra cả giao diện và API:

1. Xem các trường giao diện yêu cầu.
2. Gửi request trực tiếp với trường ngoài danh mục.
3. Đối chiếu phản hồi và dữ liệu thực sự được lưu.
4. Quan sát sự kiện, log và luồng chuyển tiếp.
5. Xác nhận không có trường được tự bổ sung mà yêu cầu chưa cho phép.

Nếu chính sách là từ chối trường ngoài danh mục, test phải kiểm tra việc từ chối. Nếu chính sách là bỏ qua, phải chứng minh không lưu hoặc chuyển trường đó. Cơ chế ánh xạ dữ liệu không được tự quyết định điều này.

### 6.2. Dashboard không trả dữ liệu thừa

Dùng MANAGER-A xem dashboard. Kiểm tra:

- API chỉ có các trường thống kê đã duyệt.
- Không trả sẵn email hoặc nội dung phiếu rồi chỉ ẩn bằng giao diện.
- Tệp tải xuống, tooltip, dữ liệu HTML và trạng thái phía client không chứa trường bị cấm.
- Tham số phân trang, lọc hoặc đường xuất khác không mở thêm dữ liệu ngoài mục đích.
- Dữ liệu tenant B không xuất hiện.

Nếu dashboard có nhóm rất nhỏ, cần xem yêu cầu về khả năng suy ra danh tính. Việc chỉ trả số đếm hoặc bỏ tên chưa tự chứng minh dữ liệu đã vô danh. Nếu có cơ chế hạn chế nhóm nhỏ, cần kiểm chứng cả giới hạn và các đường có thể suy luận qua nhiều truy vấn theo phạm vi rủi ro đã xác định.

### 6.3. Kiểm tra ranh giới mục đích

Tạo một phiếu có marker riêng trong nội dung, sau đó thực hiện các hành động bình thường. Quan sát analytics sink và các queue liên quan.

Theo PRV-PUR-01, nội dung phiếu, email và số điện thoại không được xuất hiện trong luồng phân tích tùy chọn, kể cả khi người dùng đã bật chức năng đó.

Lựa chọn bật phân tích không tự mở rộng danh sách trường cho phép. Cần kiểm tra cả điều kiện được gửi lẫn nội dung được gửi.

## 7. Kiểm thử lựa chọn của người dùng và xử lý nền

### 7.1. Trước khi bật và sau khi bật

Với người dùng mới, kiểm tra mặc định tắt ở các điểm liên quan:

- Trạng thái hiển thị trên giao diện.
- Giá trị có thẩm quyền ở phía máy chủ.
- Lưu trữ phía client và thành phần phân tích.
- Sự kiện được tạo, xếp hàng và chuyển tới bên nhận.

Thực hiện các thao tác có thể phát sinh phân tích. Không được có sự kiện tùy chọn chỉ vì một SDK tự khởi động trước khi người dùng lựa chọn.

Sau khi bật, tạo một sự kiện hợp lệ để xác nhận luồng quan sát thực sự hoạt động. Nếu sink không nhận được sự kiện ngay cả lúc được phép, việc không thấy sự kiện lúc tắt chưa chứng minh kiểm soát lựa chọn đúng.

Trong cả hai trường hợp, các chức năng hỗ trợ cần thiết phải hoạt động theo yêu cầu. Không assert “không có bất kỳ log hay request nào”, vì hệ thống vẫn có thể cần ghi sự kiện bảo vệ hoặc thực hiện chức năng khác đã được xác định.

### 7.2. Tắt trong khi có sự kiện đang chờ

Để cụ thể hóa PRV-CHO-01, ví dụ chọn quy tắc: sau thời hạn 60 giây, hệ thống không được tạo hoặc gửi sự kiện phân tích tùy chọn chưa chuyển đến bên nhận, kể cả sự kiện đang chờ trong queue.

Quy tắc xử lý dữ liệu đã được bên nhận tiếp nhận trước đó thuộc yêu cầu vòng đời riêng. Không mặc định tắt chức năng đồng nghĩa mọi dữ liệu cũ lập tức bị xóa.

Kịch bản:

1. Bật phân tích và xác nhận một sự kiện được gửi đúng.
2. Giữ một sự kiện khác ở điểm chờ trước khi worker gửi.
3. Tắt phân tích và lấy mốc t0 là lúc thay đổi được commit tại nguồn quyết định.
4. Chờ đến sau ngưỡng với phép đo kiểm soát được sai số.
5. Tạo một sự kiện mới và cho worker xử lý sự kiện đang chờ.
6. Xác nhận cả hai không được gửi theo quy tắc đã chọn.
7. Kiểm tra chức năng hỗ trợ vẫn hoạt động.

Dùng điểm đồng bộ của bộ thử để giữ worker, không dựa vào việc “đợi một chút” rồi hy vọng sự kiện còn trong hàng đợi.

Nếu nguồn lựa chọn không sẵn sàng, ví dụ này chọn không gửi phân tích tùy chọn cho đến khi xác định được trạng thái cho phép. Cần có test cho hành vi đó. Không suy rộng thành chính sách lỗi mặc định của mọi chức năng.

### 7.3. Nhiều phiên và nhiều điểm thực thi

Nếu lựa chọn gắn với tài khoản, thử việc thay đổi ở một phiên rồi phát sinh sự kiện ở phiên khác hoặc công việc nền.

Nếu sản phẩm có trạng thái trước đăng nhập và sau đăng nhập, cần quy tắc về việc liên kết hoặc chuyển lựa chọn. Không tự biến một trạng thái chưa chọn thành đã bật khi người dùng đăng nhập.

Một cờ phía trình duyệt không đủ để chứng minh worker và đường gửi phía máy chủ đã áp dụng cùng quyết định.

## 8. Kiểm thử truy cập, che dữ liệu và bản xuất

### 8.1. Phân quyền theo dữ liệu cần thiết

Tạo ma trận danh tính, tenant, phiếu và trường:

- USER-A đọc dữ liệu thuộc phạm vi của mình.
- USER-B không nhận dữ liệu tenant A dù biết ID.
- AGENT-A chỉ đọc các phiếu được phân công và các trường cần cho công việc.
- MANAGER-A nhận dữ liệu thống kê theo hợp đồng.
- Một danh tính kỹ thuật không nhận toàn bộ hồ sơ chỉ vì đang ở mạng nội bộ.

Kiểm tra API, tệp tải, tìm kiếm, preview và đường truy cập thay thế nếu có. Đừng chỉ xác nhận giao diện không hiển thị một trường.

Quyền truy cập là một cơ chế hỗ trợ giới hạn mục đích. Test kỹ thuật không thể tự chứng minh mọi ý định sử dụng dữ liệu của con người; các kết luận phải bám vào hành vi, quyền và điểm thực thi có thể quan sát.

### 8.2. Che dữ liệu phải phù hợp phạm vi

Nếu một vai trò chỉ được nhìn số điện thoại đã che:

- Kiểm tra giá trị hiển thị.
- Kiểm tra body API, dữ liệu HTML và trạng thái phía client.
- Kiểm tra tệp xuất và lỗi.
- Kiểm tra chức năng sao chép hoặc tải dữ liệu.
- Xác nhận giá trị đầy đủ không được gửi đến client rồi chỉ che bằng giao diện.

Che dữ liệu không tự biến thông tin thành vô danh. Các phần còn lại có thể vẫn liên kết được với người dùng, nhất là khi kết hợp với các trường khác.

### 8.3. Bản xuất có thể chứa dữ liệu của nhiều người

Một phiếu chung có USER-A và USER-A2. Khi USER-A yêu cầu xuất, kiểm tra quy tắc đã duyệt về nội dung liên quan đến người khác.

Không mặc định mọi trường trong mọi phiếu liên quan đều được đưa nguyên vẹn vào bản xuất. Cần đặc tả trường được giữ, loại bỏ, che hoặc xử lý theo cách khác.

Các assertion quan trọng:

- Người yêu cầu được xác minh và có quyền với phạm vi xuất.
- Người khác không tải được bản xuất bằng cách đổi mã.
- Tenant B không xuất hiện trong tệp.
- Nội dung đúng với các quy tắc dữ liệu nhiều chủ thể.
- Tệp tạm và bản xuất hết hạn theo chính sách.
- Retry không làm lẫn tệp giữa các yêu cầu.
- Cache không phục vụ tệp riêng cho phiên khác.

Trong ví dụ, đường tải yêu cầu phiên hợp lệ, đúng người yêu cầu và còn thời hạn. Nếu sản phẩm chọn liên kết mang quyền tải độc lập, phải có mô hình và test riêng cho cơ chế đó.

Một header chống lưu cache là tín hiệu cấu hình cần kiểm tra, nhưng chưa đủ chứng minh mọi tầng cache thực thi đúng. Với đường có proxy hoặc cache liên quan, dùng các phiên tổng hợp khác nhau để kiểm tra hành vi thực tế.

## 9. Kiểm thử xóa dữ liệu theo phạm vi

### 9.1. Xác định thế nào là hoàn tất

Một yêu cầu xóa cần nêu:

- Chủ thể, tenant và danh tính được xác minh.
- Các loại dữ liệu và kho thuộc phạm vi.
- Mốc bắt đầu tính thời hạn.
- Cơ chế xử lý dữ liệu của người khác trong bản ghi chung.
- Nhóm được giữ lại và cơ sở đã được phê duyệt, nếu có.
- Vòng đời của bản xuất và bản sao.
- Cách ngăn dữ liệu cũ được tạo lại.
- Tình trạng backup và bước xử lý khi phục hồi.

PRV-DEL-01 dùng mốc yêu cầu đã được xác minh và tiếp nhận, không phải thời điểm người dùng vừa mở trang yêu cầu. Bộ thử cần đối chiếu đúng mốc.

Không gọi thao tác “xóa hoàn toàn” khi chỉ vô hiệu hóa đăng nhập hoặc ẩn tài khoản trên giao diện.

### 9.2. Theo dõi từng nơi lưu

Tạo dữ liệu có marker ở các nguồn thuộc phạm vi, sau đó gửi yêu cầu xóa và đối chiếu:

| Nơi có thể có dữ liệu | Kiểm tra |
| --- | --- |
| Kho hồ sơ chính | Trường và bản ghi được xử lý theo chính sách, không chỉ bị ẩn khỏi một API |
| Cache | Không trả giá trị cũ sau thời hạn |
| Chỉ mục tìm kiếm | Không tìm lại được dữ liệu phải xóa hoặc hiển thị preview cũ |
| Tệp và đính kèm | Quyền truy cập và vòng đời đúng phạm vi |
| Bản xuất | Bản đã chuẩn bị hoặc đang chờ được xử lý theo quy tắc |
| Queue và hàng đợi lỗi | Không chứa dữ liệu tồn tại ngoài vòng đời hoặc phát lại làm tái tạo hồ sơ |
| Bên nhận trong phạm vi | Có hành động hoặc xác nhận phù hợp với hợp đồng xử lý |
| Log và audit | Tuân theo danh mục trường, thời hạn và ngoại lệ riêng |
| Backup | Theo dõi hết hạn và ngăn tái xuất hiện khi phục hồi |

Tìm marker trong một kho chỉ là một phần kiểm tra. Cần biết tác vụ đã chạy, bản ghi có trạng thái gì và phép biến đổi nào có thể làm mất chuỗi marker nhưng vẫn giữ dữ liệu liên quan.

Nếu một bên nhận chưa có xác nhận hoặc chưa đủ khả năng kiểm tra, không tự đánh dấu phần đó hoàn tất.

### 9.3. Kiểm tra retry, cạnh tranh và dữ liệu đến trễ

Các tình huống quan trọng:

- Gửi lại cùng yêu cầu xóa sau timeout.
- Worker cập nhật hồ sơ đang chạy khi yêu cầu xóa được tiếp nhận.
- Một message cũ được phát lại sau khi xóa.
- Đồng bộ từ kho khác đưa dữ liệu cũ trở về.
- Một bản xuất tạo trước khi xóa hoàn tất sau đó.
- Yêu cầu xóa của USER-A tác động nhầm USER-A2 hoặc tenant B.

Hệ thống có thể cần trạng thái ngăn tái tạo từ luồng cũ hoặc một sổ theo dõi yêu cầu xóa. Cách triển khai phải phù hợp kiến trúc.

Thông tin giữ để ngăn tái tạo cũng cần được tối thiểu hóa, kiểm soát quyền và thời hạn. Không tự coi một mã băm của định danh trong sổ theo dõi là dữ liệu vô danh.

Một người chủ động đăng ký lại hợp lệ sau đó là tình huống nghiệp vụ khác. Test phải phân biệt việc tạo mới được phép với việc dữ liệu cũ tự quay lại do xử lý trễ.

### 9.4. Dữ liệu được giữ lại phải rõ và bị giới hạn

Nếu chính sách đã xác nhận cho phép hoặc yêu cầu giữ một nhóm dữ liệu:

- Ghi đúng nhóm, trường, mục đích và thời hạn.
- Hạn chế truy cập và sử dụng ngoài mục đích giữ lại.
- Không giữ toàn bộ nội dung chỉ vì một phần nhỏ cần tồn tại.
- Theo dõi thời điểm ngoại lệ kết thúc.
- Phản ánh trung thực trong kết quả xử lý yêu cầu.

Không dùng một nhãn “audit” hoặc “hỗ trợ vận hành” để mặc định mọi dữ liệu đều được giữ không thời hạn.

Bộ thử kiểm chứng việc thực hiện quy tắc đã chốt. Việc quy tắc có phù hợp nghĩa vụ áp dụng cần được xác nhận qua trách nhiệm tương ứng, không được suy ra từ kết quả test xanh.

## 10. Kiểm thử lưu giữ và phục hồi

### 10.1. Giá trị biên của thời hạn

Với mỗi chính sách, làm rõ:

- Mốc tính từ lúc tạo, đóng phiếu, hết hợp đồng hay sự kiện nào.
- Tính theo thời gian tuyệt đối hoặc ngày lịch.
- Chu kỳ tác vụ dọn và độ trễ tối đa đã cho phép.
- Hành vi khi dữ liệu được cập nhật.
- Ngoại lệ giữ lại và điều kiện kết thúc.
- Cách xử lý khi tác vụ dọn thất bại.

Thử trước, đúng và sau thời hạn bằng cơ chế kiểm soát đồng hồ hoặc dữ liệu thời gian của môi trường thử. Không cần chờ hàng tuần trong một test nếu hệ thống có cách mô phỏng thời gian đáng tin cậy.

Nếu yêu cầu có hạn chót cứng, không tự thêm “thời gian chờ dọn” trong assertion. Nếu có độ trễ được phép, phải đưa nó vào hợp đồng và cách đo.

### 10.2. Dữ liệu đã xóa không được tự trở lại từ backup

PRV-REC-01 giả định hệ thống có nguồn theo dõi yêu cầu xóa đủ tin cậy, được bảo toàn độc lập với tập dữ liệu đang phục hồi.

Kịch bản:

1. Tạo hồ sơ và dữ liệu tổng hợp của USER-A.
2. Tạo backup B0 có các marker.
3. Tiếp nhận yêu cầu xóa, hoàn tất phần xử lý trực tuyến và xác nhận các kho liên quan.
4. Khôi phục B0 trong môi trường phục hồi được kiểm soát.
5. Giữ các đường nghiệp vụ, worker và luồng gửi ra ngoài ở trạng thái chưa mở.
6. Áp dụng yêu cầu xóa từ nguồn theo dõi có thẩm quyền.
7. Kiểm tra dữ liệu, cache và chỉ mục sau đối soát.
8. Chỉ mở lại chức năng khi đạt điều kiện đã chốt.
9. Xác nhận không có marker bị phục hồi rồi gửi ra ngoài trước khi đối soát.

Nếu khôi phục cả dữ liệu chính lẫn sổ theo dõi về cùng một thời điểm cũ, hệ thống có thể mất thông tin rằng yêu cầu xóa đã xảy ra. Khi đó cần giải quyết thiết kế nguồn có thẩm quyền, không chỉ thêm một test tìm marker sau restore.

### 10.3. Hết hạn backup và giới hạn kết luận

Theo ví dụ, backup có thời hạn tối đa 30 ngày từ lúc tạo. Test cần kiểm tra cả bản sao được quản lý, chính sách giữ lại và kết quả dọn theo phạm vi.

Việc bản backup không còn trong danh sách hiển thị chưa tự chứng minh mọi bản sao đã hết vòng đời. Cần đối chiếu cơ chế lưu và cách xác nhận phù hợp.

Nếu chọn một cơ chế xóa bằng hủy khóa, phải có yêu cầu rõ về phạm vi khóa, bản sao khóa và dữ liệu liên quan. Không khẳng định dữ liệu không thể khôi phục chỉ vì đã xóa một tham chiếu khóa, trong khi vẫn còn khóa khác hoặc khóa được dùng chung với dữ liệu phải giữ.

Kết luận cần phân biệt phần dữ liệu đang sử dụng đã xử lý, phần backup còn chờ hết hạn và các nhóm được giữ lại theo chính sách. Giao diện trả kết quả phải diễn đạt đúng điều đã hoàn tất, bằng ngôn ngữ người dùng hiểu được.

## 11. Mẫu test case và mã giả

### 11.1. Đặc tả test tắt phân tích

```yaml
testId: PRIV-CHOICE-WITHDRAW-01
requirementIds:
  - PRV-CHO-01
  - PRV-PUR-01
subject: "Người dùng tổng hợp USER-A"
purpose: "Phân tích hành vi tùy chọn"
preconditions:
  - "Lựa chọn đang bật và sự kiện hợp lệ gửi được"
  - "Có một sự kiện được giữ trước điểm gửi của worker"
action:
  - "Tắt lựa chọn và lưu mốc commit t0"
  - "Sau t0 cộng 60 giây, tạo sự kiện mới và cho job cũ chạy"
expected:
  - "Không gửi hai sự kiện thuộc phạm vi đến analytics sink"
  - "Không gửi email, số điện thoại hoặc nội dung phiếu"
  - "Chức năng hỗ trợ cần thiết vẫn hoạt động"
observations:
  - "Nguồn lựa chọn có thẩm quyền"
  - "Bộ tạo sự kiện, queue và worker"
  - "Bên nhận mô phỏng và log liên quan"
```

Khi thực thi, phải kiểm soát sai số thời gian và bảo đảm job đã đi qua điểm quyết định gửi. Job chưa chạy không phải bằng chứng lựa chọn đã được thực thi.

### 11.2. Mã giả kiểm tra xóa theo danh mục

```text
fixture = createSyntheticPrivacyFixture(runId)
assert fixture.isPresentInExpectedStores()
assert observers.areReady()

request = submitVerifiedDeletionRequest(fixture.subject)
scope = loadApprovedDeletionScope(request.policyVersion)

result = waitForDeletionProcessing(request.id)
if result.didNotReachRequiredObservationPoint:
    recordInconclusive("Chưa đủ quan sát kết quả xóa")
    stopTest()

for store in scope.onlineStores:
    assert requiredDeletionActionCompleted(store, fixture.subject)
    assert forbiddenDataNotAvailableThroughRelevantPaths(store)
    assert allowedRetainedDataMatchesPolicy(store)

assert delayedMessagesCannotRecreateOldProfile(fixture.subject)
assert noCrossSubjectOrCrossTenantDeletion(fixture)
assert backupStateReportedAccordingToPolicy(request.id)
assert userFacingResultMatchesActualCompletedScope(request.id)

recordEvidenceWithoutRealPersonalData()
```

Đây là mã giả, không phải API của một thư viện. Danh mục `scope` phải đến từ yêu cầu và bản đồ dữ liệu đã được xác nhận; không để một danh sách thiếu kho tự tạo ra kết quả PASS sai.

Với dữ liệu giữ lại, assertion phải kiểm tra trường, mục đích và giới hạn cụ thể. Không chỉ kiểm tra có một cờ `exception = true`.

## 12. Đánh giá kết quả và bằng chứng

Một kết quả privacy test nên gắn với:

- ID yêu cầu và test.
- Phiên bản chính sách, mục đích và phạm vi dữ liệu.
- Build, cấu hình và môi trường.
- Fixture tổng hợp, tenant và danh tính cần thiết.
- Nguồn quan sát, khoảng thời gian và sai số.
- Schema, sự kiện, trạng thái job hoặc kết quả đối chiếu liên quan.
- Kỳ vọng, kết quả thực tế và assertion từng phần.
- Nhóm đã hoàn tất, nhóm còn chờ và ngoại lệ được quản lý.
- Giới hạn với bên ngoài hoặc nguồn chưa quan sát được.

Cần phân biệt:

| Kết quả | Ý nghĩa |
| --- | --- |
| PASS | Các assertion trong phạm vi đã được quan sát và đạt |
| FAIL | Có bằng chứng trái yêu cầu, như vẫn gửi nội dung phiếu vào analytics |
| ERROR | Bộ thử hoặc hạ tầng không thực hiện đúng phép thử |
| INCONCLUSIVE | Có hoạt động nhưng chưa đủ quan sát để kết luận |
| SKIPPED | Test không chạy và có lý do được ghi nhận |

Ví dụ, không thấy dữ liệu ở bên nhận vì bộ mô phỏng bị tắt là thiếu cơ sở, không phải PASS. Không tìm thấy hồ sơ qua API nhưng còn dữ liệu trong chỉ mục thuộc phạm vi xóa là chưa đáp ứng yêu cầu tương ứng.

Báo cáo “đáp ứng mọi yêu cầu quyền riêng tư” vượt quá một bộ test có phạm vi hạn chế. Kết luận nên nói rõ phiên bản, luồng, mục đích, nhóm dữ liệu và các điều kiện đã được kiểm chứng.

## 13. Tích hợp vào vòng đời phát triển

Privacy test nên được thiết kế khi đặc tả luồng dữ liệu, không chờ đến cuối để tìm thông tin nhạy cảm trong log.

Có thể phân lớp:

| Lớp | Nội dung phù hợp |
| --- | --- |
| Logic | Tập trường cho phép, quy tắc mục đích, lựa chọn và thời hạn |
| Tích hợp | API, quyền, queue, cache, chỉ mục và luồng gửi ra ngoài |
| Phía client | Biểu mẫu, lưu trữ, SDK, request và phản hồi thực tế |
| Toàn luồng | Xuất dữ liệu, thay đổi lựa chọn và xóa qua nhiều kho |
| Diễn tập phục hồi | Đối soát yêu cầu xóa trước khi mở lại dữ liệu cũ |

Rà soát lại khi thêm một trường, SDK, bên nhận, báo cáo, bản sao hoặc mục đích xử lý. Một thay đổi nhỏ trong tracking hoặc log có thể tạo luồng dữ liệu mới.

Khi phát hiện lỗi, liên kết với yêu cầu nguồn, giữ kết quả cũ, khắc phục và chạy lại phần bị ảnh hưởng. Test bị bỏ qua hoặc công cụ quan sát lỗi phải được theo dõi như khoảng trống bằng chứng.

## 14. Những lỗi thường gặp và checklist

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ test phân quyền | Bỏ qua thu thập thừa, mục đích và vòng đời | Đi theo dữ liệu và mục đích |
| Chỉ che giao diện | API hoặc dữ liệu client vẫn có thông tin đầy đủ | Kiểm tra phản hồi và các đường xuất |
| Không thấy marker rồi kết luận sạch | Bỏ qua mã thay thế và phép biến đổi | Kết hợp schema, ánh xạ và trace |
| Tắt lựa chọn nhưng chỉ đổi cờ UI | Worker hoặc SDK vẫn gửi | Kiểm tra nguồn có thẩm quyền và từng điểm thực thi |
| Xóa hồ sơ chính nhưng bỏ chỉ mục, queue | Dữ liệu còn truy cập được hoặc quay lại | Dùng danh mục kho và kiểm tra xử lý trễ |
| Coi băm hoặc che là vô danh | Đánh giá thấp khả năng liên kết | Phân tích bối cảnh nhận diện lại |
| Báo xóa hết khi backup còn theo chính sách | Thông báo không đúng phạm vi | Tách phần hoàn tất, chờ và giữ lại |
| Khôi phục backup trước rồi mới nghĩ đến yêu cầu xóa | Dữ liệu cũ có thể bị dùng lại | Có cổng đối soát trước khi mở nghiệp vụ |
| Giữ mọi dữ liệu dưới nhãn audit | Lưu quá phạm vi và mục đích | Đặc tả từng nhóm, trường và thời hạn |
| Dùng dữ liệu thật để dễ phát hiện rò rỉ | Tăng rủi ro từ chính bộ thử | Dùng fixture tổng hợp có marker |

Trước khi công nhận kết quả:

- [ ] Có yêu cầu nguồn, mục đích và chính sách được xác nhận.
- [ ] Bản đồ dữ liệu gồm các bản sao và bên nhận liên quan.
- [ ] Fixture tổng hợp cho nhiều chủ thể và tenant.
- [ ] Kiểm tra cả trường dữ liệu được phép và trường bị cấm.
- [ ] Lựa chọn được thực thi ở client, máy chủ và xử lý nền theo phạm vi.
- [ ] API, tìm kiếm, bản xuất và log không bỏ sót đường truy cập.
- [ ] Xóa và lưu giữ có mốc tính, thời hạn, ngoại lệ và bằng chứng từng kho.
- [ ] Replay, cạnh tranh và restore không làm dữ liệu cũ quay lại trái yêu cầu.
- [ ] Kết quả thể hiện đúng phần hoàn tất và giới hạn.
- [ ] Thiếu quan sát hoặc test chưa chạy không được tính là PASS.
