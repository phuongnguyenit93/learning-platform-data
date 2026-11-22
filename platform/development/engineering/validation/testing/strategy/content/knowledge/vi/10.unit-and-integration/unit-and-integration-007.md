# Lựa chọn container, trình mô phỏng hoặc môi trường dùng chung

## 1. Vì sao lựa chọn môi trường kiểm thử quan trọng?

Kiểm thử đơn vị và tích hợp cần một môi trường có thể thực thi mã, cung cấp dữ liệu và kết nối các thành phần liên quan. Môi trường quá khác sản xuất có thể tạo kết quả sai lệch; môi trường dùng chung thiếu kiểm soát có thể khiến kết quả không ổn định; phụ thuộc thật có thể chậm, tốn phí hoặc khó tái tạo lỗi. Vì vậy, lựa chọn nơi chạy kiểm thử là một phần của chiến lược xác nhận chất lượng.

Ba lựa chọn thường gặp là:

- **Container:** đóng gói ứng dụng hoặc dịch vụ cùng các phụ thuộc cần thiết trong môi trường cô lập, có thể tạo và hủy theo nhu cầu.
- **Trình mô phỏng hoặc dịch vụ giả lập:** thay thế một thành phần phụ thuộc bằng một triển khai mô phỏng giao diện và hành vi cần thiết cho kịch bản kiểm thử.
- **Môi trường dùng chung:** một môi trường được nhiều người hoặc nhiều nhóm sử dụng, thường chứa các dịch vụ tích hợp và cấu hình gần với hệ thống thực tế hơn.

Không có lựa chọn nào luôn tốt nhất. Container có thể giúp kiểm thử lặp lại nhưng không tự mô phỏng đầy đủ hạ tầng sản xuất. Trình mô phỏng giúp tạo tình huống lỗi khó tái hiện với hệ thống thật nhưng có thể khác hành vi của đối tác. Môi trường dùng chung cho phép kiểm tra tích hợp thực tế nhưng dễ phát sinh tranh chấp dữ liệu, cấu hình và tài nguyên.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, quyết định lựa chọn cần dựa trên mục tiêu kiểm thử, rủi ro, độ trung thực cần thiết, khả năng cô lập, tốc độ phản hồi, chi phí và khả năng duy trì. Có thể kết hợp nhiều cách tiếp cận ở các tầng kiểm thử khác nhau.

## 2. Hiểu rõ từng lựa chọn

### 2.1. Container

Container là đơn vị đóng gói ứng dụng và các phụ thuộc ở mức hệ điều hành để chạy nhất quán trên những máy có runtime tương thích. Container thường khởi tạo nhanh hơn máy ảo đầy đủ, dễ tạo theo phiên bản và có thể được quản lý bằng cấu hình dưới dạng mã.

Trong kiểm thử, container có thể dùng để:

- Khởi chạy cơ sở dữ liệu, hàng đợi, cache hoặc dịch vụ phụ trợ với phiên bản xác định.
- Tạo môi trường tạm thời cho một test run hoặc một nhánh pull request.
- Chạy ứng dụng cùng cấu hình phụ thuộc nhất quán trong CI và máy phát triển.
- Kiểm tra quá trình khởi động, health check, cấu hình và kết nối giữa các dịch vụ.
- Tạo dữ liệu ban đầu và hủy môi trường sau khi hoàn tất để tránh ảnh hưởng lần chạy sau.

Ví dụ, kiểm thử tích hợp của một repository có thể khởi động container PostgreSQL với schema và dữ liệu seed riêng, chạy kiểm thử repository, sau đó hủy container. Mỗi lần chạy có thể dùng phiên bản database đã ghim và dữ liệu được tạo mới.

Container không phải là máy ảo đầy đủ. Trên các nền tảng phổ biến, container Linux chia sẻ kernel của máy chủ; khác biệt kernel, driver, mạng, lưu trữ và tài nguyên có thể ảnh hưởng hành vi. Một container chạy thành công không chứng minh hệ thống sẽ hoạt động giống hệt trên mọi cấu hình sản xuất. Kiểm thử phần cứng, kernel, hệ điều hành hoặc cấu hình mạng đặc thù có thể cần môi trường chuyên biệt.

### 2.2. Trình mô phỏng, mock, stub, fake và service virtualization

Những thuật ngữ này thường được dùng gần nhau nhưng có mục đích khác nhau:

| Kỹ thuật | Vai trò | Ví dụ |
|---|---|---|
| Stub | Trả về phản hồi đã định trước để kiểm tra luồng gọi | Dịch vụ định danh trả về token hợp lệ hoặc lỗi xác thực |
| Mock | Thay thế phụ thuộc và cho phép xác minh tương tác/kỳ vọng được thiết lập | Xác minh ứng dụng gọi cổng thanh toán đúng số tiền và khóa idempotency |
| Fake | Triển khai đơn giản nhưng có hành vi thực thi được, phù hợp cho kiểm thử | Repository lưu dữ liệu trong bộ nhớ thay vì database thật |
| Simulator | Mô phỏng hành vi hoặc trạng thái của thiết bị/hệ thống bên ngoài | Mô phỏng thiết bị IoT gửi dữ liệu cảm biến và mất kết nối |
| Service virtualization | Mô phỏng một dịch vụ hoặc hệ thống tích hợp qua giao diện để tái tạo nhiều tình huống | Mô phỏng API đối tác có timeout, giới hạn tốc độ và phản hồi không theo thứ tự |

Ranh giới giữa các thuật ngữ có thể khác nhau giữa công cụ và cộng đồng. Điều quan trọng là ghi rõ thành phần nào được thay thế, giao diện nào được giữ, hành vi nào được mô phỏng và điều gì không được xác nhận.

Trình mô phỏng hữu ích khi phụ thuộc thật khó truy cập, tốn phí, không ổn định, có giới hạn sandbox hoặc không thể tạo tình huống hiếm. Nhóm có thể mô phỏng timeout, phản hồi sai định dạng, lỗi xác thực, giới hạn tốc độ, sự kiện lặp hoặc sự kiện đến trễ.

Tuy nhiên, trình mô phỏng chỉ đáng tin trong phạm vi hành vi đã được xây dựng và xác nhận. Nếu mock trả về một cấu trúc đơn giản hơn API thật, nhóm có thể bỏ sót lỗi tương thích. Vì vậy, nên duy trì kiểm thử hợp đồng và một số kiểm thử tích hợp với dịch vụ thật trong môi trường được phép.

### 2.3. Môi trường dùng chung

Môi trường dùng chung là một tập hợp tài nguyên được nhiều người hoặc nhóm sử dụng, chẳng hạn môi trường tích hợp, staging, sandbox đối tác hoặc cụm kiểm thử nội bộ. Môi trường này có thể chứa nhiều dịch vụ, cơ sở dữ liệu, cấu hình mạng, hệ thống xác thực và tích hợp thực tế.

Ưu điểm chính là kiểm tra được tương tác giữa các thành phần đang triển khai trong một cấu hình chung. Môi trường dùng chung phù hợp với kiểm thử tích hợp xuyên dịch vụ, xác nhận quy trình triển khai, kiểm thử hồi quy trước phát hành và một số hoạt động kiểm thử thủ công cần dữ liệu hoặc dịch vụ thật.

Nhược điểm là các nhóm có thể làm thay đổi trạng thái hoặc cấu hình của nhau. Dữ liệu bị dùng chung, phiên bản dịch vụ không đồng nhất, lịch triển khai xung đột và tài nguyên bị tranh chấp đều có thể khiến kết quả khó lặp lại. Cần có chủ sở hữu, quy tắc đặt lịch, quản lý phiên bản, phân quyền, dữ liệu và quy trình khôi phục.

Môi trường dùng chung không mặc nhiên tương đương sản xuất. Nếu cấu hình, dung lượng, dữ liệu, mạng, danh tính hoặc nhà cung cấp khác nhau, phải ghi rõ khác biệt và giới hạn kết luận.

## 3. Tiêu chí lựa chọn

Trước khi quyết định, hãy xác định kiểm thử cần chứng minh điều gì. Sau đó so sánh các lựa chọn theo các tiêu chí sau:

| Tiêu chí | Câu hỏi cần đặt ra | Ý nghĩa |
|---|---|---|
| Độ trung thực (fidelity) | Môi trường có mô phỏng đúng giao diện, giao thức, phiên bản và hành vi cần kiểm tra không? | Cần độ trung thực cao khi xác nhận tích hợp, dữ liệu, hiệu năng hoặc hành vi phụ thuộc nền tảng |
| Khả năng cô lập | Test run có tránh ảnh hưởng đến người khác và lần chạy khác không? | Cô lập giúp giảm lỗi do tranh chấp dữ liệu và trạng thái |
| Khả năng tái lập | Có thể tạo lại cùng cấu hình, dữ liệu và điều kiện để điều tra lỗi không? | Quan trọng với CI, hồi quy và phân tích sự cố |
| Tốc độ phản hồi | Môi trường khởi tạo, chạy và dọn dẹp mất bao lâu? | Ảnh hưởng thời gian pipeline và vòng lặp phát triển |
| Độ ổn định | Phụ thuộc có sẵn sàng và kết quả có ít biến động ngoài ý muốn không? | Tránh kiểm thử chập chờn và cảnh báo giả |
| Bao phủ tình huống lỗi | Có thể tạo timeout, lỗi mạng, dữ liệu sai hoặc phản hồi bất thường không? | Trình mô phỏng thường hữu ích cho tình huống khó điều khiển ở hệ thống thật |
| Tương thích với sản xuất | Phiên bản runtime, database, cấu hình và hạ tầng có đại diện cho môi trường đích không? | Tránh kết luận vượt quá điều kiện đã kiểm tra |
| Bảo mật và dữ liệu | Có dùng dữ liệu nhạy cảm, bí mật, tài khoản hoặc quyền truy cập nào không? | Cần phân quyền, che dữ liệu, quản lý secret và dọn dữ liệu đúng cách |
| Chi phí | Có chi phí hạ tầng, giấy phép, tài nguyên, giao dịch sandbox hoặc công sức bảo trì không? | Cần xét tổng chi phí vòng đời, không chỉ chi phí khởi tạo |
| Khả năng vận hành | Ai tạo, cập nhật, giám sát, sửa lỗi và dọn môi trường? | Tránh phụ thuộc vào một cá nhân hoặc tài nguyên không có chủ sở hữu |

Không nhất thiết phải chấm điểm mọi tiêu chí. Với quyết định quan trọng, có thể dùng ma trận so sánh định tính hoặc định lượng, nhưng hãy giữ các điều kiện bắt buộc riêng. Ví dụ, phương án có chi phí thấp không thể được chọn nếu không đáp ứng yêu cầu bảo vệ dữ liệu hoặc không tạo được bằng chứng cần thiết cho rủi ro trọng yếu.

## 4. Chọn môi trường theo tầng kiểm thử

Một chiến lược hợp lý thường kết hợp nhiều môi trường. Tầng kiểm thử càng gần ranh giới tích hợp hoặc hành vi sản xuất thì nhu cầu về độ trung thực thường càng cao, nhưng không phải mọi kiểm thử đều cần toàn bộ hệ thống.

| Tầng kiểm thử | Lựa chọn thường phù hợp | Lưu ý |
|---|---|---|
| Đơn vị | Stub, mock hoặc fake cho phụ thuộc bên ngoài; không cần container nếu không có lợi ích cụ thể | Tập trung vào logic của đơn vị đang kiểm tra; tránh mock quá sâu khiến kiểm thử chỉ xác nhận cách triển khai nội bộ |
| Thành phần/repository | Container cho database, cache hoặc broker với phiên bản xác định; fake cho một số phụ thuộc | Kiểm tra hành vi thành phần với phụ thuộc thực tế ở ranh giới cần thiết |
| API/hợp đồng | Stub/service virtualization cho phản hồi đa dạng; kiểm thử hợp đồng với schema và phiên bản thật | Giữ hợp đồng đồng bộ giữa bên cung cấp và bên tiêu thụ |
| Tích hợp nhiều dịch vụ | Container hoặc môi trường tạm thời cho các thành phần có thể đóng gói; môi trường dùng chung cho dịch vụ cần thiết | Chọn phạm vi đủ để xác nhận tương tác, kiểm soát trạng thái và dữ liệu |
| Đầu cuối | Môi trường tích hợp hoặc staging gần sản xuất, có thể dùng một số dịch vụ mô phỏng được kiểm soát | Duy trì số lượng kịch bản có giá trị cao; ghi rõ phần nào là thật và phần nào là mô phỏng |
| Hiệu năng, phục hồi, bảo mật | Môi trường chuyên biệt hoặc staging có cấu hình đại diện; phụ thuộc mô phỏng cho tình huống lỗi có kiểm soát | Không suy rộng kết quả nếu tải, dữ liệu, mạng hoặc tài nguyên khác đáng kể so với sản xuất |

Một nguyên tắc thực tế là dùng môi trường nhỏ và nhanh để phát hiện lỗi cục bộ, sau đó mở rộng sang kiểm thử tích hợp có độ trung thực cao hơn cho các rủi ro liên thành phần. Giữ một số kiểm thử trên môi trường thật hoặc sandbox được phê duyệt để phát hiện sai lệch giữa mô phỏng và hệ thống bên ngoài.

## 5. Quy trình quyết định lựa chọn

### Bước 1: Xác định mục tiêu kiểm thử

Mô tả hành vi cần xác nhận, rủi ro cần kiểm soát và kết quả mong đợi. Ví dụ: “Xác nhận dịch vụ đặt hàng xử lý đúng khi cổng thanh toán timeout, webhook đến trễ và người dùng gửi lại yêu cầu”. Mục tiêu này cần mô phỏng được một số tình huống lỗi nhưng cũng cần kiểm tra hợp đồng tích hợp thật.

### Bước 2: Liệt kê phụ thuộc và ranh giới

Vẽ các thành phần cần tham gia: ứng dụng, database, broker, dịch vụ nội bộ, đối tác và thiết bị. Phân loại phụ thuộc theo khả năng đóng gói, khả năng mô phỏng, quyền truy cập, chi phí và mức độ cần xác nhận thật.

### Bước 3: Xác định độ trung thực cần thiết

Hỏi hành vi nào cần giống sản xuất: phiên bản giao thức, schema, transaction, locking, thời gian, thứ tự sự kiện, mạng, quyền truy cập hay tài nguyên. Một fake trong bộ nhớ có thể đủ cho kiểm tra logic nhưng không xác nhận transaction hoặc truy vấn SQL của database thật.

### Bước 4: Đánh giá cô lập và tái lập

Kiểm tra mỗi lần chạy có thể có dữ liệu và cấu hình riêng không; môi trường có thể được tạo mới, reset hoặc dọn dẹp không; test chạy song song có gây xung đột không. Nếu dùng môi trường chung, xác định cách khóa tài nguyên, đặt lịch, đặt tên dữ liệu và khôi phục trạng thái.

### Bước 5: So sánh chi phí và tốc độ

Ước lượng thời gian khởi tạo, chạy, dọn dẹp, thời gian chờ môi trường, chi phí hạ tầng, phí sandbox và công sức duy trì mô phỏng. Cân nhắc tổng chi phí trong cả vòng đời. Một container cần bảo trì image và dữ liệu seed; một mock cần cập nhật theo hợp đồng; môi trường chung cần người vận hành và lịch sử dụng.

### Bước 6: Chọn phương án hoặc tổ hợp

Chọn phương án đáp ứng điều kiện bắt buộc và cân bằng tốt các tiêu chí ưu tiên. Có thể dùng container cho database, service virtualization cho đối tác và môi trường dùng chung cho kiểm thử xuyên dịch vụ. Ghi rõ thành phần nào là thật, thành phần nào được thay thế và lý do.

### Bước 7: Xác định cách kiểm chứng môi trường

Kiểm tra chính môi trường trước khi tin vào kết quả: phiên bản, cấu hình, health check, schema, dữ liệu seed, chứng chỉ, secret, kết nối và trạng thái phụ thuộc. Một môi trường chưa sẵn sàng có thể khiến test thất bại giả hoặc bỏ qua lỗi thật.

### Bước 8: Đặt tiêu chí đánh giá và xem xét lại

Theo dõi thời gian khởi tạo, tỷ lệ test chập chờn, thời gian chờ môi trường, mức sai lệch với sản xuất, chi phí và số lỗi tích hợp lọt ra. Xác định sự kiện cần xem xét lại như thay đổi phiên bản dịch vụ, tăng số nhóm dùng chung, thay đổi hợp đồng hoặc sự cố do khác biệt môi trường.

## 6. Thiết kế container cho kiểm thử đáng tin cậy

### 6.1. Ghim phiên bản và cấu hình

Nên ghim phiên bản image cụ thể hoặc digest đã được kiểm soát, thay vì dùng tag trôi nổi như `latest` cho môi trường cần tái lập. Cấu hình khởi tạo, schema và dữ liệu seed nên được quản lý cùng mã nguồn hoặc trong kho cấu hình có phiên bản.

Ví dụ Docker Compose tối giản cho kiểm thử tích hợp với PostgreSQL:

```yaml
services:
  database:
    image: postgres:16.4
    environment:
      POSTGRES_DB: app_test
      POSTGRES_USER: app_test
      POSTGRES_PASSWORD: test_only_password
    ports:
      - "127.0.0.1:55432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_test -d app_test"]
      interval: 2s
      timeout: 2s
      retries: 20
```

Đây là ví dụ minh họa. Mật khẩu chỉ dùng cho môi trường kiểm thử cục bộ và không được tái sử dụng trong sản xuất. Trong CI, nên dùng secret hoặc cơ chế cấp thông tin xác thực riêng; tránh mở cổng ra mọi giao diện mạng nếu không cần thiết. Với yêu cầu tái lập nghiêm ngặt, có thể ghim image bằng digest và quản lý phiên bản Compose/runtime.

### 6.2. Chờ dịch vụ sẵn sàng

Container chạy không đồng nghĩa dịch vụ đã sẵn sàng nhận yêu cầu. Ứng dụng kiểm thử nên đợi health check hoặc kiểm tra kết nối có timeout hữu hạn trước khi chạy. Tránh dùng một khoảng sleep cố định dài vì nó vừa làm chậm pipeline vừa không bảo đảm dịch vụ đã sẵn sàng.

### 6.3. Cô lập dữ liệu và trạng thái

Mỗi test run nên có database, schema, database name hoặc namespace riêng khi cần chạy song song. Tạo dữ liệu seed xác định, dùng migration thực tế và dọn dẹp sau khi hoàn tất. Nếu dùng volume lưu trữ, xác định rõ khi nào giữ dữ liệu để điều tra và khi nào xóa để tránh rò rỉ giữa các lần chạy.

Không dùng dữ liệu cá nhân hoặc dữ liệu sản xuất chưa được phép trong container kiểm thử. Container không tự bảo vệ dữ liệu; quyền truy cập, secret, log và volume vẫn cần được quản lý.

### 6.4. Quản lý tài nguyên và tính tương đồng

Đặt giới hạn CPU, bộ nhớ và dung lượng phù hợp với mục đích kiểm thử. Nếu giới hạn quá thấp, test có thể thất bại do tài nguyên môi trường thay vì lỗi ứng dụng; nếu không giới hạn, một test run có thể ảnh hưởng máy chủ CI khác.

Với kiểm thử hiệu năng, cần cân nhắc mức tài nguyên và topology có đại diện cho sản xuất. Container tiện lợi cho kiểm thử chức năng và tích hợp, nhưng không nên dùng kết quả trên máy CI nhỏ để kết luận năng lực tải của cụm sản xuất.

## 7. Thiết kế trình mô phỏng và dịch vụ giả lập

### 7.1. Mô phỏng theo hợp đồng

Trình mô phỏng nên bám theo hợp đồng API, schema sự kiện hoặc giao thức đã thống nhất. Có thể sinh client/server từ schema hoặc xác minh phản hồi của simulator bằng kiểm thử hợp đồng. Khi hợp đồng thay đổi, cần cập nhật simulator và chạy kiểm thử để phát hiện sai lệch.

Không nên chỉ mô phỏng phản hồi thành công. Hãy chọn các hành vi quan trọng theo rủi ro: timeout, lỗi xác thực, lỗi máy chủ, giới hạn tốc độ, dữ liệu không hợp lệ, phản hồi lặp, phản hồi đến trễ, mất kết nối và phục hồi.

### 7.2. Mô phỏng trạng thái và thứ tự sự kiện

Với hệ thống bất đồng bộ, hành vi phụ thuộc trạng thái và thứ tự sự kiện. Simulator nên cho phép cấu hình sự kiện đến trễ, lặp, thiếu hoặc sai thứ tự nếu đây là tình huống cần xác nhận. Cần ghi rõ quy tắc chuyển trạng thái để kiểm thử không dựa trên phản hồi tùy ý.

### 7.3. Tránh mô phỏng quá mức

Mock quá sâu có thể khiến kiểm thử chỉ xác nhận rằng mã gọi đúng một phương thức giả lập, trong khi hành vi tích hợp thật vẫn sai. Nên thay thế ở ranh giới phụ thuộc và giữ phần logic cần xác nhận thật. Ví dụ, có thể mô phỏng cổng thanh toán bên ngoài nhưng vẫn chạy database, transaction và logic xử lý trạng thái thật trong container.

Một số kiểm thử với simulator cần được đối chiếu định kỳ với sandbox hoặc dịch vụ thật. Khi phát hiện sai lệch, sửa hợp đồng hoặc simulator và đánh giá lại các kết luận trước đó nếu sai lệch ảnh hưởng phạm vi đã xác nhận.

## 8. Quản trị môi trường dùng chung

### 8.1. Chủ sở hữu và quy tắc sử dụng

Mỗi môi trường dùng chung cần có chủ sở hữu chịu trách nhiệm về trạng thái, phiên bản, cấu hình, quyền truy cập và lịch bảo trì. Nhóm cần biết cách yêu cầu sử dụng, nơi xem trạng thái, kênh báo sự cố và quy trình khôi phục.

Nếu nhiều nhóm triển khai cùng lúc, có thể dùng lịch đặt chỗ, namespace riêng, môi trường tạm thời hoặc quy tắc đóng băng phiên bản trong một cửa sổ kiểm thử. Tránh thay đổi cấu hình nền mà không thông báo cho các nhóm đang sử dụng.

### 8.2. Quản lý dữ liệu và quyền truy cập

Dữ liệu dùng chung cần có quy tắc tạo, phân vùng, làm mới, ẩn danh và xóa. Tài khoản kiểm thử nên dùng quyền tối thiểu, có thể thu hồi và không chia sẻ thông tin xác thực cá nhân. Nhật ký cần hỗ trợ truy vết nhưng không ghi lộ secret hoặc dữ liệu nhạy cảm.

Đối với dữ liệu có trạng thái, mỗi nhóm hoặc test run nên có phạm vi dữ liệu riêng. Nếu không thể cô lập, cần quy định khóa, lịch chạy hoặc reset dữ liệu và ghi nhận nguy cơ xung đột.

### 8.3. Theo dõi sức khỏe môi trường

Theo dõi tình trạng dịch vụ, dung lượng, kết nối, chứng chỉ, phiên bản, hàng đợi, dữ liệu và các thay đổi cấu hình. Khi môi trường không khỏe, đánh dấu rõ để nhóm không hiểu nhầm lỗi môi trường thành lỗi sản phẩm. Sau khi khôi phục, chạy kiểm tra smoke để xác nhận môi trường sẵn sàng.

### 8.4. Phân biệt lỗi môi trường và lỗi sản phẩm

Khi test thất bại, thu thập log, trace, phiên bản, cấu hình, dữ liệu và trạng thái phụ thuộc trước khi phân loại. Có thể tái chạy trong môi trường cô lập để so sánh. Không tự động retry mọi lỗi đến khi xanh vì điều đó che giấu vấn đề môi trường và làm giảm độ tin cậy của pipeline.

Nếu nguyên nhân chưa rõ, đánh dấu kết quả là chưa xác định hoặc bị chặn theo quy ước nhóm. Chỉ đóng lỗi môi trường khi có bằng chứng môi trường đã được khôi phục và test chạy lại trong điều kiện xác định.

## 9. Ví dụ lựa chọn theo tình huống

### Ví dụ A: Kiểm thử repository với database

Một ứng dụng dùng PostgreSQL và cần xác nhận truy vấn, migration, transaction và ràng buộc dữ liệu. Fake repository trong bộ nhớ không thể chứng minh SQL và transaction hoạt động đúng trên database mục tiêu. Nhóm chọn container PostgreSQL với phiên bản ghim, migration thực tế và dữ liệu seed riêng cho từng lần chạy.

Container giúp test có thể chạy trong CI mà không cần database dùng chung. Nhóm vẫn cần một bước kiểm thử tương thích trên phiên bản database được hỗ trợ ở môi trường gần sản xuất nếu có khác biệt về cấu hình hoặc extension.

### Ví dụ B: Kiểm thử timeout của cổng thanh toán

Sandbox của nhà cung cấp không dễ tạo timeout hoặc webhook sai thứ tự. Nhóm dùng service virtualization để mô phỏng phản hồi trễ, timeout, retry, lỗi xác thực và webhook lặp. Logic xử lý trạng thái và database vẫn chạy thật trong container. Trước phát hành, nhóm thực hiện thêm một số kiểm thử tích hợp với sandbox chính thức để xác nhận hợp đồng và xác thực.

Simulator tạo điều kiện tái lập tình huống hiếm; sandbox kiểm tra tương tác với nhà cung cấp trong giới hạn môi trường họ cung cấp. Hai loại bằng chứng được ghi riêng.

### Ví dụ C: Kiểm thử đầu cuối trên nhiều dịch vụ

Một sản phẩm gồm nhiều dịch vụ do các nhóm khác nhau triển khai. Khởi chạy toàn bộ dịch vụ bằng container cho mỗi test run vượt quá tài nguyên CI và khó phản ánh cấu hình tích hợp. Nhóm duy trì môi trường tích hợp dùng chung có lịch triển khai và phiên bản được công bố; các kiểm thử đơn vị, repository và hợp đồng vẫn chạy trong môi trường cô lập.

Nhóm giảm xung đột bằng namespace dữ liệu riêng, lịch kiểm thử hồi quy, smoke test sau triển khai và thông báo thay đổi cấu hình. Các lỗi do môi trường được ghi nhận riêng để không làm sai lệch chất lượng của bản dựng.

### Ví dụ D: Mô phỏng thiết bị IoT

Ứng dụng nhận dữ liệu từ nhiều loại thiết bị, nhưng không thể luôn có thiết bị vật lý cho mỗi lần chạy CI. Nhóm dùng simulator để tạo dữ liệu cảm biến, pin yếu, mất kết nối, gửi lặp và phục hồi. Một tập kiểm thử trên thiết bị thật vẫn được duy trì trước phát hành để xác nhận driver, giao tiếp vật lý, thời gian và sai khác phần cứng.

Simulator hỗ trợ độ bao phủ rộng và tái lập; thiết bị thật xác nhận các đặc tính không thể mô phỏng đáng tin cậy.

## 10. Ma trận quyết định tham khảo

Bảng dưới đây là định hướng ban đầu, không phải quy tắc cứng:

| Nhu cầu chính | Container | Trình mô phỏng | Môi trường dùng chung |
|---|---|---|---|
| Tái lập phụ thuộc như database hoặc broker | Phù hợp nếu image và cấu hình đại diện | Có thể thay thế cho test logic đơn giản, nhưng không xác nhận hành vi thật của phụ thuộc | Có thể dùng, nhưng dễ tranh chấp trạng thái |
| Tạo lỗi hiếm hoặc khó điều khiển | Có thể mô phỏng một số lỗi qua cấu hình hoặc proxy | Rất phù hợp nếu hành vi cần mô phỏng được định nghĩa rõ | Có thể khó tạo lỗi mà không ảnh hưởng người khác |
| Kiểm tra tương tác dịch vụ thật | Có thể chạy một phần hệ thống | Không đủ nếu toàn bộ phụ thuộc đều bị thay thế | Phù hợp khi phiên bản và cấu hình được quản lý |
| Chạy song song trong CI | Phù hợp khi tài nguyên đủ và test được cô lập | Phù hợp nếu simulator hỗ trợ trạng thái riêng theo test run | Cần namespace, đặt lịch hoặc cơ chế cô lập rõ |
| Xác nhận hành vi phần cứng/nền tảng đặc thù | Có giới hạn, phụ thuộc kernel và quyền truy cập thiết bị | Chỉ phù hợp với phần hành vi có thể mô phỏng | Có thể cần thiết bị hoặc môi trường chuyên dụng thật |
| Kiểm tra gần sản xuất trước phát hành | Hữu ích cho dịch vụ có thể đóng gói, nhưng cần đối chiếu khác biệt | Bổ trợ cho phụ thuộc khó kiểm soát | Thường hữu ích nếu staging được quản trị tốt |

Trong nhiều trường hợp, lựa chọn phù hợp là kết hợp: container cho thành phần nội bộ có thể tái tạo, simulator cho tình huống phụ thuộc ngoài, và môi trường dùng chung cho một số luồng tích hợp thật. Mỗi loại kiểm thử phải nêu rõ kết luận nào được hỗ trợ bởi bằng chứng tương ứng.

## 11. Chỉ số đánh giá chất lượng môi trường

Không chỉ đo tốc độ chạy test. Cần theo dõi chất lượng và chi phí của môi trường để biết lựa chọn có còn phù hợp.

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Thời gian khởi tạo | Thời gian từ yêu cầu tạo môi trường đến khi sẵn sàng | Tìm điểm nghẽn trong CI hoặc quy trình cấp phát |
| Thời gian dọn dẹp | Thời gian giải phóng tài nguyên và dữ liệu | Đánh giá khả năng chạy song song và nguy cơ rò rỉ tài nguyên |
| Tỷ lệ kiểm thử chập chờn | Tỷ lệ test thay đổi kết quả khi đầu vào và mã nguồn không đổi | Phân tích tính ổn định của môi trường, dữ liệu và test |
| Thời gian chờ môi trường | Thời gian nhóm chờ được cấp hoặc sửa môi trường | Đánh giá năng lực và quản trị môi trường dùng chung |
| Sai lệch với sản xuất | Khác biệt về phiên bản, cấu hình, dữ liệu, mạng và phụ thuộc | Xác định giới hạn của bằng chứng và nhu cầu kiểm tra bổ sung |
| Tỷ lệ lỗi tích hợp lọt ra | Lỗi giao tiếp hoặc cấu hình được phát hiện sau khi triển khai | Đánh giá liệu môi trường và kiểm thử tích hợp có đủ đại diện |
| Chi phí duy trì | Hạ tầng, giấy phép, công sức cập nhật image, simulator và dữ liệu | So sánh tổng chi phí với giá trị kiểm thử |

Chỉ số phải có định nghĩa, cửa sổ đo và nguồn dữ liệu. Ví dụ, tỷ lệ flaky test cần phân biệt lỗi do test, do môi trường và do sản phẩm; nếu gộp tất cả, nhóm có thể xử lý sai nguyên nhân.

## 12. Những sai lầm thường gặp

- **Cho rằng container giống hệt sản xuất:** container không mô phỏng đầy đủ kernel, mạng, phần cứng, quy mô hoặc topology của môi trường đích.
- **Dùng tag image trôi nổi:** cùng một cấu hình có thể kéo về phiên bản khác nhau ở các lần chạy.
- **Không chờ health check:** test bắt đầu trước khi dịch vụ sẵn sàng và thất bại ngẫu nhiên.
- **Dùng mock cho mọi tầng:** kiểm thử có thể bỏ qua sai lệch hợp đồng và hành vi của phụ thuộc thật.
- **Không cập nhật simulator theo hợp đồng:** mô phỏng tiếp tục trả về hành vi cũ và tạo cảm giác an toàn giả.
- **Dùng môi trường chung mà không có chủ sở hữu:** cấu hình thay đổi không báo trước, dữ liệu bị ghi đè và lỗi khó tái hiện.
- **Chia sẻ dữ liệu hoặc tài khoản tùy tiện:** test chạy song song ảnh hưởng nhau hoặc làm lộ thông tin nhạy cảm.
- **Retry đến khi test xanh:** che giấu lỗi môi trường và làm giảm độ tin cậy của pipeline.
- **Không ghi phần được mô phỏng:** người đọc hiểu nhầm kết quả là xác nhận toàn bộ tích hợp thật.
- **Không dọn tài nguyên:** container, volume, namespace và dữ liệu cũ tích tụ, gây thiếu tài nguyên hoặc rò rỉ dữ liệu.
- **Dùng môi trường kiểm thử hiệu năng không đại diện:** kết quả đo không phản ánh năng lực hệ thống khi vận hành thật.

## 13. Checklist trước khi chốt lựa chọn môi trường

- [ ] Mục tiêu kiểm thử, rủi ro và hành vi cần xác nhận được mô tả rõ.
- [ ] Các phụ thuộc và ranh giới kiểm thử đã được liệt kê.
- [ ] Độ trung thực cần thiết được xác định cho từng thành phần.
- [ ] Đã đánh giá khả năng cô lập, tái lập, tốc độ và độ ổn định.
- [ ] Phiên bản image, simulator, schema và cấu hình có thể được quản lý.
- [ ] Có health check và cơ chế chờ dịch vụ sẵn sàng.
- [ ] Dữ liệu, secret, tài khoản và quyền truy cập được quản lý an toàn.
- [ ] Test chạy song song không gây tranh chấp trạng thái hoặc tài nguyên.
- [ ] Môi trường dùng chung có chủ sở hữu, lịch sử dụng và quy trình khôi phục.
- [ ] Simulator được đối chiếu với hợp đồng và có kiểm thử tích hợp thật khi cần.
- [ ] Khác biệt với sản xuất và giới hạn của bằng chứng được ghi nhận.
- [ ] Có quy trình dọn dẹp, theo dõi sức khỏe và xử lý lỗi môi trường.
- [ ] Có chỉ số và điều kiện để xem xét lại lựa chọn khi bối cảnh thay đổi.

## Kết luận

Lựa chọn container, trình mô phỏng hoặc môi trường dùng chung cần bắt đầu từ hành vi và rủi ro muốn xác nhận. Container hỗ trợ môi trường cô lập và tái lập; simulator giúp điều khiển phụ thuộc và tình huống lỗi; môi trường dùng chung cho phép kiểm tra tương tác giữa các thành phần thực tế. Mỗi lựa chọn đều có giới hạn về độ trung thực, trạng thái, dữ liệu, chi phí và khả năng vận hành. Khi nhóm kết hợp đúng tầng kiểm thử, quản lý phiên bản và dữ liệu, ghi rõ phần được mô phỏng, đồng thời theo dõi chất lượng môi trường, kết quả kiểm thử sẽ đáng tin cậy và có thể giải thích hơn.
