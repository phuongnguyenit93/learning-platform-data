# Yêu cầu chức năng và phi chức năng

## 1. Vì sao phải phân biệt hai loại yêu cầu?

Một hệ thống có màn hình đăng nhập chưa chắc đã bảo vệ được tài khoản. Một API trả kết quả rất nhanh chưa chắc đã ngăn người dùng đọc dữ liệu của người khác. Khi đặc tả bảo mật, cần trả lời đồng thời hai câu hỏi:

- Hệ thống phải thực hiện hành vi nào để bảo vệ tài sản?
- Những hành vi đó phải đạt chất lượng, quy mô và mức bảo đảm nào trong điều kiện vận hành cụ thể?

**Yêu cầu chức năng** mô tả hành vi hoặc khả năng mà hệ thống phải cung cấp: xác minh danh tính, kiểm tra quyền, che trường dữ liệu, tạo sự kiện kiểm toán hoặc thu hồi phiên.

**Yêu cầu phi chức năng** mô tả thuộc tính chất lượng và các ràng buộc áp dụng cho hệ thống hoặc hành vi của nó: thời gian đáp ứng, năng lực xử lý, khả năng phục hồi, khả năng quan sát, điều kiện triển khai và mức bảo đảm cần chứng minh.

Trong bảo mật, ranh giới này có thể giao nhau. “Chỉ chủ sở hữu được đọc hóa đơn” thể hiện một thuộc tính bảo mật, đồng thời có thể được đặc tả thành hành vi phân quyền cụ thể. Vì vậy, không nên coi toàn bộ bảo mật là một mục phi chức năng chung mang tên “hệ thống phải an toàn”.

Trong bài này, ta dùng quy ước:

- Gắn nhãn **FR** cho hành vi bảo vệ có đầu vào, quyết định hoặc tác động quan sát được.
- Gắn nhãn **NFR** cho chất lượng, giới hạn hoặc ràng buộc áp dụng cho hành vi đó.
- Nếu một phát biểu chứa nhiều ý, tách thành các yêu cầu liên kết với nhau thay vì cố ép cả phát biểu vào một nhãn.

Mục tiêu của việc phân loại là làm rõ trách nhiệm thiết kế và bằng chứng nghiệm thu. Tên nhóm không thay thế được nội dung yêu cầu.

## 2. Bối cảnh xuyên suốt: dịch vụ quản lý hóa đơn

Giả sử một dịch vụ cho nhiều tổ chức cùng quản lý hóa đơn. Mỗi tổ chức là một **tenant**, tức một phạm vi dữ liệu và quyền truy cập riêng.

Các đối tượng chính gồm:

| Đối tượng | Ý nghĩa trong ví dụ |
| --- | --- |
| Người dùng thường | Đọc các hóa đơn thuộc phạm vi được cấp |
| Người phê duyệt | Phê duyệt hóa đơn khi có quyền tương ứng |
| Quản trị viên tenant | Quản lý thành viên trong tenant của mình |
| Dịch vụ hóa đơn | Kiểm tra danh tính, quyền và thực hiện nghiệp vụ |
| Kho dữ liệu | Lưu hóa đơn, thông tin tài khoản và chính sách quyền |
| Hệ thống kiểm toán | Ghi nhận các thao tác cần truy vết |
| Bản sao lưu | Hỗ trợ phục hồi dữ liệu và cấu hình đã xác định |

Tài sản cần bảo vệ gồm nội dung hóa đơn, dữ liệu cá nhân trên hóa đơn, quyền phê duyệt và lịch sử thao tác.

Một số rủi ro đầu vào:

| Mã | Tình huống đe dọa | Hậu quả cần ngăn hoặc giảm |
| --- | --- | --- |
| R-01 | Kẻ tấn công sử dụng thông tin xác thực bị lộ | Thao tác bằng danh tính nạn nhân |
| R-02 | Người dùng sửa mã hóa đơn hoặc mã tenant trong yêu cầu | Đọc hoặc sửa hóa đơn ngoài phạm vi quyền |
| R-03 | Người đã bị thu hồi quyền tiếp tục dùng phiên hoặc dữ liệu quyền cũ | Phê duyệt hóa đơn sau thời điểm bị thu hồi |
| R-04 | Lỗi phần mềm đưa thông tin nhạy cảm vào log | Lộ dữ liệu qua hệ thống quan sát |
| R-05 | Dịch vụ kiểm tra quyền gặp sự cố | Bỏ qua kiểm tra hoặc làm gián đoạn nghiệp vụ |
| R-06 | Dữ liệu hoặc cấu hình bị mất, bị sửa sai | Không thể phục hồi nghiệp vụ an toàn |

Danh sách này tạo ngữ cảnh để viết yêu cầu. Nó chưa phải tập yêu cầu hoàn chỉnh: mỗi rủi ro còn phải được chuyển thành hành vi bảo vệ, giới hạn chấp nhận và cách kiểm chứng.

**Các con số trong bài chỉ là giả định minh họa.** Khi áp dụng, nhóm phát triển và chủ sở hữu nghiệp vụ phải chọn ngưỡng theo mức rủi ro, tải thực tế, chi phí và khả năng vận hành. Không được sao chép các ngưỡng ví dụ thành chính sách chung cho mọi hệ thống.

## 3. Nhận diện yêu cầu chức năng

### 3.1. Dấu hiệu của một yêu cầu chức năng

Một yêu cầu chức năng thường trả lời được các câu hỏi:

1. Ai hoặc thành phần nào khởi phát hành vi?
2. Hành vi xảy ra khi nào?
3. Hệ thống phải kiểm tra hoặc thực hiện điều gì?
4. Kết quả được phép và bị từ chối là gì?
5. Dữ liệu hoặc trạng thái nào được thay đổi?
6. Trường hợp lỗi có được phép tạo tác động một phần hay không?

Ví dụ, “có phân quyền” quá ngắn để nghiệm thu. Có thể cụ thể hóa thành:

> **FR-AUTHZ-01:** Với mọi yêu cầu đọc chi tiết hóa đơn qua API, dịch vụ phải xác minh rằng danh tính đã được xác thực có quyền đọc hóa đơn đích trong tenant của hóa đơn. Nếu không có quyền hoặc không thể xác định được quyền, dịch vụ phải từ chối và không trả về nội dung hóa đơn.

Yêu cầu này có tài nguyên đích, điều kiện cho phép, điều kiện từ chối và kết quả quan sát được. Tuy nhiên, nó chưa xác định thời gian kiểm tra quyền, quy mô dữ liệu quyền hoặc thời gian có hiệu lực sau khi thu hồi. Những nội dung đó cần các yêu cầu liên quan.

### 3.2. Các hành vi bảo mật thường gặp

| Phạm vi | Ví dụ yêu cầu chức năng | Điều cần đặc tả thêm |
| --- | --- | --- |
| Xác thực | Chỉ tạo phiên đăng nhập sau khi hoàn tất các bước xác thực bắt buộc | Tài khoản nào phải xác thực bổ sung, cách xử lý thất bại |
| Phân quyền | Kiểm tra quyền với đúng tài nguyên và thao tác trước khi thực hiện | Tenant, trạng thái nghiệp vụ, quyền bị thu hồi |
| Bảo vệ dữ liệu | Loại bỏ trường tài khoản thanh toán khỏi bản xuất dành cho vai trò chỉ xem | Danh sách trường, định dạng xuất, phạm vi người được xem |
| Quản lý phiên | Vô hiệu hóa phiên sau khi đăng xuất | Phiên hiện tại hay mọi phiên, tác động đến token đã phát hành |
| Kiểm toán | Ghi sự kiện thay đổi quyền và phê duyệt hóa đơn | Trường dữ liệu bắt buộc, điểm ghi, quyền đọc log |
| Phục hồi | Khôi phục dữ liệu từ điểm sao lưu được chọn vào môi trường phục hồi | Phạm vi dữ liệu, xác minh tính nhất quán, xử lý quyền và khóa |

Các hàng trong bảng là hướng viết yêu cầu, chưa tự động trở thành đặc tả đầy đủ. Ví dụ, “ghi sự kiện” vẫn cần xác định sự kiện nào, ghi thành công khi nào và ứng xử thế nào nếu nơi nhận sự kiện không hoạt động.

### 3.3. Đặc tả cả hành vi cho phép và hành vi từ chối

Bảo mật đòi hỏi kiểm tra cả đường đi hợp lệ lẫn đường đi bị cấm.

Với một thao tác phê duyệt hóa đơn, cần mô tả ít nhất:

- Danh tính có quyền, thuộc đúng tenant và hóa đơn đủ điều kiện: được phê duyệt.
- Danh tính đã đăng nhập nhưng không có quyền: bị từ chối.
- Danh tính thuộc tenant khác: bị từ chối, kể cả khi biết chính xác mã hóa đơn.
- Không có danh tính hợp lệ: không được thực hiện thao tác.
- Không xác định được quyền do lỗi phụ thuộc: bị từ chối theo chính sách đã chọn.
- Yêu cầu bị từ chối: không cập nhật trạng thái hóa đơn và không phát sinh thanh toán hay thông báo phê duyệt.

Mệnh đề “không phát sinh tác động nghiệp vụ” cần được kiểm chứng ở cả dữ liệu và các công việc bất đồng bộ. Chỉ thấy một mã lỗi HTTP chưa đủ chứng minh thao tác đã bị chặn hoàn toàn.

## 4. Nhận diện yêu cầu phi chức năng

### 4.1. Chất lượng phải gắn với hành vi và bối cảnh

Các câu như “đăng nhập nhanh”, “log đầy đủ”, “khả năng phục hồi cao” không đưa ra ranh giới đạt hay không đạt.

Một yêu cầu phi chức năng có thể kiểm chứng thường cần:

> **Đối tượng được đo + thuộc tính + ngưỡng + điều kiện tải/môi trường + cửa sổ quan sát + cách đo.**

Ví dụ:

> **NFR-AUTHZ-01:** Trong môi trường kiểm thử hiệu năng đã mô tả, với 200 yêu cầu đọc hóa đơn mỗi giây trong 30 phút, độ trễ của bước đánh giá quyền tại dịch vụ hóa đơn phải có p95 không quá 50 ms. Phép đo bao gồm thời gian gọi phụ thuộc và chờ trong hàng đợi của bước này; mọi yêu cầu phải có kết quả kiểm tra quyền đúng theo bộ dữ liệu kiểm thử.

Ở đây, **p95** là phân vị 95 của tập độ trễ quan sát: khoảng 95% mẫu không vượt quá giá trị đó. p95 không phải thời gian tối đa, và cũng không có nghĩa 95% quyết định được phép sai hay đúng. Tính đúng của phân quyền phải được đánh giá riêng.

Để phép đo có thể lặp lại, kế hoạch kiểm thử còn phải mô tả tài nguyên máy, cấu hình mạng, số tenant, số bản ghi, tỷ lệ truy cập hợp lệ/bị từ chối, trạng thái cache và cách thu thập mẫu.

### 4.2. Các nhóm phi chức năng liên quan đến bảo mật

| Nhóm | Câu hỏi cần trả lời | Ví dụ phát biểu cần cụ thể hóa |
| --- | --- | --- |
| Hiệu năng | Biện pháp bảo vệ mất bao lâu trong điều kiện xác định? | Độ trễ kiểm tra quyền dưới tải đã chọn |
| Năng lực xử lý | Hệ thống giữ được thuộc tính bảo vệ ở quy mô nào? | Số yêu cầu, phiên hoặc sự kiện xử lý được trong một khoảng thời gian |
| Tính sẵn sàng | Người dùng hợp lệ sử dụng được chức năng với mức phục vụ nào? | Tỷ lệ yêu cầu hợp lệ được xử lý thành công trong cửa sổ đo |
| Khả năng phục hồi | Phục hồi trong bao lâu, chấp nhận mất tối đa dữ liệu nào? | RTO, RPO và điều kiện xác minh sau phục hồi |
| Khả năng quan sát | Có đủ bằng chứng và cảnh báo kịp thời để phát hiện sự cố không? | Độ trễ đưa sự kiện kiểm toán vào kho truy vấn |
| Khả năng bảo trì | Thay đổi chính sách hoặc cập nhật thành phần bảo vệ thế nào? | Thời gian triển khai thay đổi và phạm vi gián đoạn cho phép |
| Ràng buộc kỹ thuật hoặc vận hành | Hệ thống phải tuân theo quyết định bắt buộc nào? | Chỉ dịch vụ được chỉ định có quyền sử dụng khóa giải mã |

Không phải mọi trường hợp đều phân loại giống nhau. Ví dụ, thời hạn lưu log có thể được quản lý như một ràng buộc dữ liệu; thao tác xóa log khi hết hạn lại là hành vi chức năng. Có thể tách hai phần để mỗi phần có tiêu chí kiểm chứng rõ ràng.

### 4.3. Đừng bỏ quên mẫu số và trường hợp lỗi

Yêu cầu “99,9% thành công” chưa đủ nếu chưa xác định:

- Thành công của hành vi nào?
- Mẫu số gồm những yêu cầu nào?
- Đo theo tháng, theo ngày hay theo một lượt thử?
- Những lỗi phụ thuộc, timeout và lần thử lại được tính ra sao?
- Nguồn đo và quy tắc tổng hợp là gì?

Ví dụ, tỷ lệ sẵn sàng của API có thể tính trên các yêu cầu hợp lệ đủ điều kiện phục vụ. Các yêu cầu bị từ chối đúng chính sách phải được báo cáo riêng, không trộn vào như lỗi vận hành, cũng không dùng chúng để làm đẹp tỷ lệ thành công.

Đối với phép đo thời gian quyết định quyền, timeout và lỗi phải được ghi nhận theo quy tắc đã công bố. Không được âm thầm loại các trường hợp chậm hoặc thất bại để đạt ngưỡng p95.

## 5. Tách mục tiêu, yêu cầu, giải pháp và bằng chứng

Bốn khái niệm này liên quan nhưng không thay thế cho nhau:

| Lớp thông tin | Câu hỏi | Ví dụ trong dịch vụ hóa đơn |
| --- | --- | --- |
| Mục tiêu | Muốn bảo vệ điều gì? | Giữ bí mật hóa đơn giữa các tenant |
| Yêu cầu | Hệ thống bắt buộc thể hiện hành vi hoặc thuộc tính nào? | Chỉ trả hóa đơn khi danh tính có quyền đọc trong tenant của hóa đơn |
| Quyết định thiết kế | Chọn cơ chế nào để đáp ứng yêu cầu? | Đặt kiểm tra quyền trong dịch vụ và giới hạn truy vấn dữ liệu theo tenant |
| Bằng chứng | Dựa vào đâu để kết luận đáp ứng? | Kiểm thử API giữa tenant, kiểm tra truy vấn và kết quả quan sát |

“Dùng token”, “thêm gateway” hoặc “mã hóa dữ liệu” là các lựa chọn cơ chế còn thiếu ngữ cảnh. Chúng chưa nói rõ hệ thống bảo vệ tài sản nào, trước tình huống nào và được nghiệm thu ra sao.

Một cơ chế có thể trở thành yêu cầu ràng buộc nếu có lý do bắt buộc, chẳng hạn phải tích hợp với hệ thống quản lý danh tính của tổ chức. Khi đó, phải ghi rõ căn cứ và phạm vi áp dụng; không suy ra rằng chỉ cần sử dụng cơ chế ấy là đã đáp ứng mọi yêu cầu bảo mật.

### 5.1. Chuỗi chuyển đổi từ rủi ro đến kiểm thử

Có thể xây dựng chuỗi liên kết:

**Tài sản → tình huống đe dọa → hậu quả → yêu cầu → thiết kế → bằng chứng kiểm chứng.**

Ví dụ với R-02:

1. **Tài sản:** nội dung hóa đơn của tenant B.
2. **Tình huống:** người dùng tenant A thay mã hóa đơn trong yêu cầu API.
3. **Hậu quả:** dịch vụ trả dữ liệu tenant B cho người dùng tenant A.
4. **Yêu cầu chức năng:** kiểm tra quyền trên hóa đơn đích và từ chối truy cập ngoài phạm vi.
5. **Yêu cầu phi chức năng:** việc kiểm tra phải đạt ngân sách độ trễ ở tải xác định, vẫn giữ quyết định đúng.
6. **Thiết kế:** lấy danh tính từ ngữ cảnh đã xác thực; đối chiếu tenant của tài nguyên; kiểm tra quyền ở phía dịch vụ.
7. **Bằng chứng:** gửi các yêu cầu hợp lệ và chéo tenant trực tiếp tới API, kiểm tra phản hồi, dữ liệu trả về và tác động trong hệ thống.

Việc ẩn nút trên giao diện chỉ thay đổi trải nghiệm của người dùng. Yêu cầu kiểm tra quyền vẫn phải áp dụng tại nơi thực hiện thao tác, vì API có thể được gọi trực tiếp.

### 5.2. Một bảng truy vết gọn

| Rủi ro | Yêu cầu liên quan | Thành phần chịu trách nhiệm | Bằng chứng dự kiến |
| --- | --- | --- | --- |
| R-01: thông tin xác thực bị lộ | FR-AUTHN-01: yêu cầu bước xác thực bổ sung cho tài khoản phê duyệt | Dịch vụ danh tính, luồng đăng nhập | Thử đăng nhập với các bước đủ, thiếu, sai và hết hạn |
| R-02: truy cập khác tenant | FR-AUTHZ-01; NFR-AUTHZ-01 | Dịch vụ hóa đơn, tầng dữ liệu | Kiểm thử quyền theo tài nguyên và đo độ trễ dưới tải |
| R-03: quyền cũ còn hiệu lực | FR-REVOKE-01; NFR-REVOKE-01 | Dịch vụ quản lý quyền và mọi nơi lưu trạng thái quyền | Dùng lại phiên cũ trước và sau khi thu hồi |
| R-04: lộ dữ liệu trong log | FR-LOG-02 | Ứng dụng, middleware, nơi thu gom log | Kiểm tra đường thành công, lỗi và thử lại bằng dữ liệu giả |
| R-05: lỗi phụ thuộc phân quyền | FR-AUTHZ-02 | Dịch vụ hóa đơn, thành phần đánh giá quyền | Gây timeout hoặc lỗi kết nối; xác nhận không phê duyệt |
| R-06: mất dữ liệu hoặc cấu hình | FR-REC-01; NFR-REC-01 | Kho dữ liệu, hệ thống sao lưu, vận hành | Diễn tập phục hồi và kiểm tra quyền sau phục hồi |

Một rủi ro thường cần nhiều yêu cầu. Ngược lại, một yêu cầu có thể góp phần giảm nhiều rủi ro. Bảng truy vết giúp xem phần nào còn thiếu, nhưng không tự chứng minh rằng mọi đe dọa đã được bao phủ.

## 6. Bộ ví dụ yêu cầu có thể kiểm chứng

Các đặc tả dưới đây mở rộng bối cảnh hóa đơn. Chúng minh họa cách viết yêu cầu đủ rõ để thiết kế và kiểm thử, chưa phải một chính sách bảo mật hoàn chỉnh cho sản phẩm.

### 6.1. Xác thực: có cơ chế và có điều kiện hoàn tất

**FR-AUTHN-01 — Xác thực bổ sung cho tài khoản phê duyệt**

> Khi tài khoản có quyền phê duyệt bắt đầu một phiên đăng nhập mới, dịch vụ phải yêu cầu hoàn tất bước xác thực bổ sung đã đăng ký trước khi phát hành phiên cho phép thực hiện nghiệp vụ. Trạng thái đang chờ xác thực bổ sung không được sử dụng để gọi API phê duyệt.

Tiêu chí chấp nhận:

- Hoàn tất đúng các bước bắt buộc thì được cấp phiên với quyền tương ứng.
- Chỉ hoàn tất bước đầu thì chưa được phê duyệt.
- Bằng chứng xác thực bổ sung sai hoặc hết hạn không tạo phiên hoàn chỉnh.
- Lỗi từ thành phần xác thực bổ sung không dẫn đến bỏ qua bước bắt buộc.
- Luồng khôi phục tài khoản có chính sách riêng, không ngầm trở thành đường đi bỏ qua xác thực.

Câu “hỗ trợ xác thực nhiều yếu tố” chưa giải thích tài khoản nào bắt buộc sử dụng, thời điểm kiểm tra hoặc trạng thái nào được xem là đăng nhập thành công. Những chi tiết này quyết định tính kiểm chứng của yêu cầu.

### 6.2. Phân quyền: đúng đối tượng, đúng trạng thái

**FR-AUTHZ-02 — Phê duyệt hóa đơn khi đã xác định được quyền**

> Trước khi ghi nhận một quyết định phê duyệt, dịch vụ phải xác định rằng người thực hiện có quyền phê duyệt hóa đơn đích trong tenant của hóa đơn và hóa đơn đang ở trạng thái cho phép phê duyệt. Nếu không xác định được các điều kiện này, dịch vụ phải từ chối; không cập nhật trạng thái và không phát sinh tác động nghiệp vụ của việc phê duyệt.

Từ “trước khi” thể hiện yêu cầu về thứ tự và tính nhất quán của quyết định. Thiết kế cần xử lý trường hợp quyền hoặc trạng thái hóa đơn thay đổi trong lúc thao tác đang diễn ra. Chỉ kiểm tra ở giao diện hoặc kiểm tra một lần khi đăng nhập không đáp ứng điều kiện này.

Ví dụ tiêu chí chấp nhận theo cấu trúc tiền điều kiện – hành động – kết quả:

| Tiền điều kiện | Hành động | Kết quả bắt buộc |
| --- | --- | --- |
| Có quyền, đúng tenant, hóa đơn chờ phê duyệt | Gửi yêu cầu phê duyệt | Ghi nhận phê duyệt theo quy tắc nghiệp vụ |
| Không có quyền phê duyệt | Gọi trực tiếp API | Từ chối; hóa đơn và tác động nghiệp vụ giữ nguyên |
| Có quyền tại tenant A, hóa đơn thuộc tenant B | Thay mã hóa đơn trong yêu cầu | Từ chối; không lộ nội dung hóa đơn B |
| Dịch vụ đánh giá quyền bị timeout | Gửi yêu cầu phê duyệt | Không phê duyệt; phản hồi lỗi theo hợp đồng API |
| Hóa đơn đã chuyển sang trạng thái không cho phép phê duyệt | Gửi yêu cầu trên dữ liệu vừa thay đổi | Không ghi nhận một quyết định không hợp lệ |

**Fail closed** là cách xử lý từ chối khi không xác định được quyền. Nó giúp bảo vệ tài nguyên nhưng có thể làm giảm tính sẵn sàng. Vì vậy, cần mô tả rõ thao tác nào áp dụng chính sách này, đồng thời thiết kế cơ chế khôi phục và giám sát để giảm gián đoạn.

### 6.3. Thu hồi quyền: hành vi và thời hạn là hai phần khác nhau

**FR-REVOKE-01 — Thu hồi quyền phê duyệt**

> Khi quản trị viên hợp lệ thu hồi quyền phê duyệt của một thành viên trong tenant của mình, hệ thống phải lưu thay đổi quyền và áp dụng thay đổi đó cho các yêu cầu phê duyệt tiếp theo, kể cả khi thành viên sử dụng phiên đã được tạo trước khi thu hồi.

**NFR-REVOKE-01 — Giới hạn thời gian quyền cũ còn có thể được dùng**

> Trong điều kiện kết nối bình thường giữa các thành phần thuộc phạm vi triển khai, thay đổi thu hồi quyền phải có hiệu lực tại mọi điểm quyết định quyền trong tối đa 60 giây tính từ lúc thao tác thu hồi được ghi nhận thành công. Mọi yêu cầu phê duyệt bắt đầu sau mốc này phải bị từ chối nếu quyền không được cấp lại.

Cần chốt thêm cách xử lý với yêu cầu đang chạy và trường hợp mất kết nối. Trong ví dụ này:

- Một yêu cầu bắt đầu sau mốc 60 giây không được dựa vào bản quyền cũ để phê duyệt.
- Khi không xác định được trạng thái quyền theo chính sách, áp dụng FR-AUTHZ-02.
- Yêu cầu đã bắt đầu trước khi thu hồi cần quy tắc nhất quán riêng nếu nghiệp vụ đòi hỏi hủy thao tác đang chạy.

Các quyết định thiết kế có thể liên quan đến thời gian sống của cache, token mang quyền, phiên và cơ chế lan truyền thay đổi. Một token còn hợp lệ về chữ ký không đủ chứng minh rằng quyền bên trong vẫn còn hiệu lực.

Bằng chứng cần lấy từ mọi điểm có thể quyết định quyền, không chỉ từ giao diện quản trị. Phép đo phải xác định thời điểm bắt đầu, điểm quan sát và sai lệch đồng hồ cho phép.

### 6.4. Logging: ghi được sự kiện nhưng không ghi bí mật

**FR-LOG-01 — Sự kiện kiểm toán cho thay đổi quyền và phê duyệt**

> Dịch vụ phải tạo sự kiện kiểm toán cho thao tác thay đổi quyền và cho kết quả cho phép hoặc từ chối phê duyệt hóa đơn. Sự kiện phải có thời điểm, định danh chủ thể, tenant, loại thao tác, định danh tài nguyên phù hợp, kết quả, mã lý do và mã tương quan.

“Định danh phù hợp” cần được định nghĩa trong hợp đồng dữ liệu log. Không mặc định đưa toàn bộ đối tượng người dùng hoặc toàn bộ nội dung hóa đơn vào sự kiện.

**FR-LOG-02 — Loại trừ dữ liệu nhạy cảm khỏi log**

> Các log và sự kiện của luồng xác thực, thay đổi quyền và phê duyệt không được chứa mật khẩu, mã xác thực dùng một lần, token truy cập, token làm mới hoặc toàn bộ nội dung hóa đơn. Quy tắc áp dụng cho đường thành công, bị từ chối, xử lý ngoại lệ và thử lại.

Đây là hành vi ràng buộc dữ liệu đầu ra, có thể kiểm tra bằng các giá trị giả được đánh dấu trong môi trường thử nghiệm. Phải bao phủ cả log do middleware, thư viện và cơ chế ghi lỗi tạo ra.

**NFR-LOG-01 — Độ trễ truy vấn sự kiện**

> Với 500 sự kiện kiểm toán mỗi giây trong 30 phút và đường truyền tới kho kiểm toán hoạt động bình thường, độ trễ từ lúc dịch vụ xác nhận sự kiện đã được lưu bền vững để gửi đến lúc sự kiện truy vấn được tại kho kiểm toán phải có p95 không quá 10 giây.

Đạt ngưỡng độ trễ không chứng minh rằng không mất sự kiện. Cần đối chiếu mã sự kiện giữa bên phát và bên nhận, xác định cách xử lý trùng lặp, và có yêu cầu riêng cho thời gian mất kết nối.

Đối với thao tác quan trọng, hợp đồng phải nêu rõ: chỉ trả thành công sau khi đã ghi được dấu vết bền vững, hay cho phép tiếp tục với rủi ro đã được chấp nhận. Không để quyết định này phụ thuộc ngẫu nhiên vào việc nơi thu gom log có hoạt động hay không.

### 6.5. Phục hồi: khôi phục cả dữ liệu lẫn điều kiện bảo vệ

**FR-REC-01 — Khôi phục tập dữ liệu và cấu hình cần thiết**

> Hệ thống phải cung cấp quy trình phục hồi hóa đơn, dữ liệu thành viên và chính sách quyền từ bản sao lưu được chọn vào môi trường phục hồi được kiểm soát. Trước khi mở lại nghiệp vụ, phải xác minh tính nhất quán dữ liệu, khả năng truy cập các khóa cần thiết và hiệu lực của các quy tắc phân quyền.

Hai khái niệm thường dùng:

- **RTO — Recovery Time Objective:** mục tiêu thời gian tối đa để khôi phục khả năng phục vụ đã xác định sau một sự cố thuộc phạm vi cam kết.
- **RPO — Recovery Point Objective:** mục tiêu mức mất dữ liệu tối đa chấp nhận được, diễn đạt bằng khoảng thời gian lùi về điểm dữ liệu có thể phục hồi.

**NFR-REC-01 — Mục tiêu phục hồi cho kịch bản mất kho dữ liệu chính**

> Với tập dữ liệu và cấu hình triển khai được mô tả trong kế hoạch diễn tập, quy trình phục hồi phải đưa dịch vụ trở lại mức phục vụ đã xác định trong tối đa 60 phút tính từ thời điểm bắt đầu gián đoạn trong kịch bản thử. Khoảng thời gian từ điểm dữ liệu khôi phục được đến thời điểm gián đoạn không được vượt quá 15 phút.

Trong ví dụ này, RTO là 60 phút và RPO là 15 phút. Kế hoạch phải nêu cách xác định điểm dữ liệu, kiểm tra các giao dịch quanh thời điểm sự cố, tài nguyên phục hồi và điều kiện kết thúc phép đo.

Sao lưu mỗi 15 phút chưa đủ chứng minh đạt RPO 15 phút: bản sao lưu có thể lỗi, thiếu phụ thuộc hoặc không khôi phục được. Bằng chứng mạnh hơn là phục hồi thực tế và đối chiếu dữ liệu.

Cũng cần ngăn việc phục hồi làm sống lại quyền đã thu hồi sau thời điểm sao lưu. Quy trình phải xác định nguồn thay đổi quyền mới nhất, bước đối soát và điều kiện cho phép mở lại nghiệp vụ. Nếu chưa khôi phục được trạng thái quyền đáng tin cậy, chức năng nhạy cảm phải giữ trạng thái chặn theo chính sách.

## 7. Mẫu đặc tả dùng trong công việc

Không phải yêu cầu nào cũng cần một biểu mẫu dài. Với yêu cầu ảnh hưởng đến nhiều thành phần hoặc khó nghiệm thu, có thể dùng cấu trúc sau:

| Trường | Nội dung cần ghi |
| --- | --- |
| Mã và tên | Định danh ổn định để liên kết với thiết kế và kiểm thử |
| Loại | Chức năng, phi chức năng hoặc ràng buộc theo quy ước của nhóm |
| Rủi ro và mục tiêu | Tài sản được bảo vệ, tình huống đe dọa liên quan |
| Phạm vi | Endpoint, thao tác, loại dữ liệu, vai trò, tenant hoặc thành phần áp dụng |
| Phát biểu bắt buộc | Hành vi hoặc thuộc tính phải đạt, dùng từ “phải” khi là nghĩa vụ |
| Điều kiện và giả định | Trạng thái hệ thống, phụ thuộc, tải và môi trường |
| Trường hợp lỗi | Hành vi khi thiếu dữ liệu, timeout, mất kết nối hoặc cấu hình không hợp lệ |
| Tiêu chí chấp nhận | Kết quả quan sát được, ngưỡng và cách xác định đạt |
| Phương pháp kiểm chứng | Kiểm thử, đo đạc, kiểm tra thiết kế, cấu hình hoặc diễn tập |
| Trách nhiệm và ưu tiên | Ai làm rõ, ai thực hiện, ai chấp nhận kết quả |
| Liên kết | Yêu cầu liên quan, quyết định thiết kế và bằng chứng |

Một mẫu ngắn cho yêu cầu chức năng:

~~~text
Mã: FR-...
Rủi ro liên quan: R-...
Khi <tác nhân> thực hiện <thao tác> trên <tài nguyên>,
hệ thống phải <hành vi bắt buộc> nếu <điều kiện cho phép>.
Nếu <điều kiện từ chối hoặc lỗi>, hệ thống phải <kết quả>,
và không được <tác động bị cấm>.
Bằng chứng: <tình huống và quan sát cần thu thập>.
~~~

Một mẫu ngắn cho yêu cầu phi chức năng:

~~~text
Mã: NFR-...
Áp dụng cho: FR-... hoặc <phạm vi cụ thể>.
Trong <môi trường, tải, trạng thái phụ thuộc>,
<thuộc tính> của <đối tượng đo> phải đạt <ngưỡng>
trong <cửa sổ quan sát>.
Đo từ <mốc bắt đầu> đến <mốc kết thúc>,
bao gồm <thành phần hoặc loại mẫu được tính>.
Lỗi và timeout được xử lý trong số liệu theo <quy tắc>.
Bằng chứng: <công cụ, dữ liệu và báo cáo cần có>.
~~~

Tránh ghép quá nhiều nghĩa vụ độc lập vào một mã. “Mã hóa dữ liệu, đăng nhập nhanh, có log và sao lưu tốt” không có một tiêu chí nghiệm thu thống nhất. Có thể giữ một yêu cầu cấp cao rồi tách thành các yêu cầu con, mỗi yêu cầu có bằng chứng rõ ràng.

## 8. Chọn cách kiểm chứng theo bản chất yêu cầu

Phân loại FR/NFR giúp tổ chức công việc nhưng không quyết định cứng loại kiểm thử. Một hành vi chức năng có thể cần kiểm tra kiến trúc; một thuộc tính phi chức năng có thể cần chạy kiểm thử tích hợp.

| Điều cần chứng minh | Cách kiểm chứng phù hợp | Giới hạn cần hiểu |
| --- | --- | --- |
| Không đọc được hóa đơn khác tenant | Kiểm thử API theo ma trận danh tính, tenant và tài nguyên | Một vài ví dụ đạt không chứng minh mọi endpoint đều an toàn |
| Thu hồi quyền trong thời hạn | Kiểm thử tích hợp có mốc thời gian, phiên cũ và nhiều điểm quyết định quyền | Chỉ kiểm tra một instance có thể bỏ sót cache ở instance khác |
| Độ trễ kiểm tra quyền | Kiểm thử tải với tập dữ liệu và quy tắc đo đã xác định | Đạt ở môi trường thử chưa bảo đảm đạt với mọi cấu hình sản xuất |
| Không ghi token vào log | Gửi token giả nhận diện được qua các nhánh thành công và lỗi; kiểm tra mọi nơi nhận log trong phạm vi | Chỉ tìm trong log ứng dụng có thể bỏ sót proxy hoặc bộ thu lỗi |
| Từ chối khi phụ thuộc phân quyền lỗi | Gây timeout hoặc lỗi có kiểm soát, kiểm tra cả dữ liệu và tác động bất đồng bộ | Mã lỗi trả về chưa đủ nếu tác động đã được ghi trước đó |
| Đạt mục tiêu phục hồi | Diễn tập phục hồi từ bản sao lưu và đối chiếu dữ liệu, quyền, thời gian | Bản sao lưu được tạo thành công chưa chứng minh phục hồi thành công |
| Chỉ thành phần được phép sử dụng khóa | Kiểm tra cấu hình quyền, đường truy cập và thử bằng danh tính không được phép | Bản mô tả kiến trúc không thay thế được cấu hình đang áp dụng |

Một yêu cầu mang tính phổ quát, chẳng hạn “mọi API đọc hóa đơn phải kiểm tra quyền”, không nên được nghiệm thu chỉ bằng một ca thử của một API. Cần kết hợp kiểm thử đại diện với bằng chứng về độ bao phủ endpoint, vị trí thực thi kiểm soát và cơ chế ngăn đường đi bỏ qua.

Báo cáo phải phân biệt rõ:

- **Thuộc tính cần bảo đảm:** nghĩa vụ của hệ thống.
- **Phạm vi đã kiểm chứng:** môi trường, phiên bản, tập tình huống và dữ liệu đã thử.
- **Giả định còn phụ thuộc:** điều kiện cần để kết luận vẫn có hiệu lực.

Không được biến yêu cầu bảo vệ tuyệt đối trong phạm vi đã nêu thành “đúng trong 99% trường hợp” chỉ để dễ đạt số liệu. Nếu yêu cầu là ngăn truy cập trái phép, mọi trường hợp truy cập trái phép được phát hiện đều là lỗi của yêu cầu đó.

## 9. Xử lý xung đột giữa các yêu cầu

### 9.1. Phân quyền và độ trễ

Giả sử NFR-AUTHZ-01 đặt ngân sách p95 là 50 ms, nhưng lời gọi đánh giá quyền từ xa đang chậm.

Một cách xử lý không đáp ứng yêu cầu là bỏ qua kiểm tra quyền khi hết thời gian chờ để API vẫn trả nhanh. Cách này có thể cải thiện số liệu độ trễ nhưng vi phạm FR-AUTHZ-01 hoặc FR-AUTHZ-02.

Các hướng thiết kế cần được đánh giá gồm:

- Tối ưu dữ liệu và đường xử lý của bước đánh giá quyền.
- Sử dụng cache với giới hạn độ cũ phù hợp yêu cầu thu hồi.
- Giảm số lần gọi phụ thuộc mà vẫn giữ đủ ngữ cảnh quyền.
- Tăng năng lực xử lý hoặc điều chỉnh kiến trúc.
- Thương lượng lại ngân sách độ trễ với chủ sở hữu yêu cầu nếu chưa khả thi.

Nếu dùng cache 10 phút trong khi NFR-REVOKE-01 yêu cầu quyền cũ hết hiệu lực trong 60 giây, thiết kế phải có cơ chế bổ sung để bảo đảm giới hạn 60 giây. Chỉ đặt thời gian sống cache 10 phút không đáp ứng yêu cầu.

### 9.2. Kiểm toán và tính sẵn sàng

Nếu mọi thao tác phê duyệt phải có dấu vết kiểm toán bền vững, sự cố kho nhận log không thể tự động làm mất nghĩa vụ đó.

Nhóm thiết kế cần làm rõ điểm xác nhận lưu bền vững, cách liên kết thay đổi nghiệp vụ với sự kiện, khả năng đệm và giới hạn khi bộ đệm đầy. Những câu hỏi quan trọng gồm:

- Có thể ghi nhận nghiệp vụ và sự kiện cần gửi trong cùng một đơn vị nhất quán không?
- Nếu ứng dụng dừng ngay sau khi ghi nghiệp vụ, sự kiện còn có thể được gửi lại không?
- Khi hệ thống gửi lại, bên nhận xử lý sự kiện trùng thế nào?
- Nếu không còn bảo đảm lưu được dấu vết, chức năng nào phải dừng?

Kết quả là các yêu cầu cụ thể về tính nhất quán, lưu giữ và hành vi lỗi. Không chỉ thêm một câu “log phải tin cậy”.

### 9.3. Khả năng phục hồi và quyền đã thu hồi

Phục hồi nhanh từ một bản sao lưu cũ có thể khôi phục cả quyền không còn hợp lệ. Như vậy, đạt thời gian khởi động lại chưa đủ để kết luận hệ thống phục hồi an toàn.

Điều kiện mở lại nghiệp vụ phải bao gồm kiểm tra trạng thái quyền, nguồn cấu hình, khóa cần sử dụng và các thay đổi bảo mật sau điểm sao lưu. Có thể cho phép phục hồi một phần dịch vụ trước nếu phạm vi đó đã được đặc tả và không mở lại thao tác nhạy cảm khi điều kiện bảo vệ chưa đạt.

### 9.4. Cách quyết định khi không thể đạt đồng thời

Khi có xung đột, ghi nhận rõ:

1. Hai hoặc nhiều yêu cầu nào đang xung đột.
2. Kịch bản và bằng chứng cho thấy xung đột xảy ra.
3. Tác động tới tài sản và nghiệp vụ nếu giảm một yêu cầu.
4. Phương án thiết kế, chi phí và giới hạn của từng phương án.
5. Chủ sở hữu có thẩm quyền chấp nhận rủi ro hoặc sửa yêu cầu.
6. Phạm vi, thời hạn và điều kiện xem xét lại nếu có ngoại lệ.

Ưu tiên triển khai không đồng nghĩa với miễn nghĩa vụ bảo vệ. Một yêu cầu chưa thực hiện phải được ghi nhận là chưa đáp ứng hoặc có ngoại lệ đã được chấp nhận; không đổi cách diễn đạt để làm nó có vẻ đã hoàn thành.

## 10. Những lỗi đặc tả thường gặp

| Phát biểu chưa đủ rõ | Vấn đề | Hướng viết lại |
| --- | --- | --- |
| “Hệ thống phải bảo mật” | Không có tài sản, tình huống hay kết quả quan sát | Nêu tài nguyên, danh tính, thao tác và điều kiện cho phép |
| “Bảo mật là phi chức năng” | Bỏ sót các hành vi bảo vệ phải được thiết kế | Tách xác thực, phân quyền, kiểm toán và các thuộc tính chất lượng liên quan |
| “Có token thì được truy cập” | Đánh đồng xác thực với quyền trên tài nguyên | Kiểm tra danh tính hợp lệ và quyền cho thao tác đích |
| “Người quản trị được xem tất cả” | Không rõ quản trị hệ thống hay quản trị tenant | Định nghĩa vai trò, phạm vi tenant và hành động được phép |
| “Mã hóa mọi dữ liệu” | Thiếu phạm vi, trạng thái dữ liệu và quyền dùng khóa | Nêu dữ liệu cần bảo vệ, điểm lưu/truyền và chủ thể được giải mã |
| “Log đầy đủ để điều tra” | Có thể dẫn đến thu thập bí mật và dữ liệu quá mức | Xác định sự kiện, trường cần có và trường bị cấm |
| “Thu hồi quyền ngay lập tức” | Không có mốc đo hoặc quy tắc cho yêu cầu đang chạy | Đặt thời hạn, điểm bắt đầu, điểm quan sát và chính sách lỗi |
| “API dưới 100 ms” | Không rõ phần trăm mẫu, tải, lỗi hay điểm đo | Nêu phân vị hoặc giới hạn tối đa, môi trường và quy tắc thống kê |
| “Sao lưu thường xuyên” | Không thể suy ra thời gian và dữ liệu phục hồi | Đặt mục tiêu phục hồi và xác minh bằng diễn tập |
| “Đã có kiểm thử nên đã an toàn” | Suy rộng vượt quá phạm vi bằng chứng | Gắn kết luận với yêu cầu và phạm vi thực sự đã kiểm chứng |

## 11. Áp dụng trong vòng đời phát triển

Ở giai đoạn làm rõ nhu cầu, dùng tài sản và mô hình đe dọa để chọn vấn đề cần bảo vệ. Viết từng nghĩa vụ bằng hành vi hoặc thuộc tính có thể quan sát, rồi liên kết với hậu quả cần ngăn.

Ở giai đoạn thiết kế, phân bổ yêu cầu cho dịch vụ, tầng dữ liệu, hệ thống danh tính, nơi lưu log và quy trình vận hành. Kiểm tra các quyết định có ảnh hưởng chéo: cache quyền với thu hồi quyền, xác thực với khả năng phục vụ, sao lưu với quyền sau phục hồi.

Ở giai đoạn triển khai, giữ mã yêu cầu trong hạng mục công việc và bằng chứng kiểm chứng. Với yêu cầu phi chức năng, chuẩn bị dữ liệu, tải và mốc đo từ sớm để tránh đến cuối mới phát hiện không thể thu thập số liệu.

Trước khi phát hành, đánh giá từng yêu cầu theo tiêu chí đã chốt. Phân biệt rõ yêu cầu đạt, chưa đạt, chưa đủ bằng chứng hoặc đang có ngoại lệ. Không dùng kết quả hiệu năng tốt để bù cho một lỗi phân quyền.

Trong vận hành, theo dõi các thuộc tính có thể thay đổi theo tải, dữ liệu và cấu hình. Một yêu cầu từng đạt có thể cần kiểm chứng lại khi thay đổi hệ thống danh tính, cơ chế cache, cách lưu log hoặc quy trình phục hồi.

Một đặc tả sẵn sàng đưa vào thực hiện cần trả lời được:

- Yêu cầu đang giảm rủi ro nào và bảo vệ tài sản nào?
- Ai được làm gì với tài nguyên nào, trong điều kiện nào?
- Khi bị từ chối hoặc khi phụ thuộc lỗi, tác động nào bị cấm?
- Chất lượng được đo bằng chỉ số, ngưỡng và cửa sổ nào?
- Thành phần hoặc nhóm nào chịu trách nhiệm?
- Bằng chứng nào đủ để xác nhận đáp ứng trong phạm vi đã nêu?

Khi các câu hỏi này có câu trả lời cụ thể, sự phân biệt chức năng và phi chức năng trở thành công cụ nối mục tiêu an toàn thông tin với kiến trúc, triển khai, kiểm thử và vận hành.
