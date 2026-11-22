# Đánh giá sai lệch giữa thành phần thay thế với môi trường thực tế

Kiểm thử đơn vị và kiểm thử tích hợp thường sử dụng các thành phần thay thế để cô lập chức năng, tạo dữ liệu có thể kiểm soát và nhận phản hồi nhanh. Cách làm này giúp kiểm tra logic mà không cần khởi động mọi dịch vụ hoặc phụ thuộc bên ngoài. Tuy nhiên, một stub, mock, fake hoặc môi trường giả lập chỉ mô phỏng một phần hành vi. Nếu phần mô phỏng khác đáng kể so với dịch vụ thật, kiểm thử có thể đạt trong môi trường phát triển nhưng thất bại khi tích hợp hoặc triển khai.

Vì vậy, chiến lược kiểm thử cần đánh giá **mức độ khác biệt có ảnh hưởng đến hành vi giữa thành phần thay thế và phụ thuộc thực tế**. Mục tiêu không phải làm cho mọi fake giống hệt hệ thống thật, mà là hiểu rõ phần nào đang được mô phỏng, rủi ro nào chưa được kiểm tra và cần loại bằng chứng nào để bù đắp khoảng trống.

## 1. Thành phần thay thế trong kiểm thử là gì?

Thành phần thay thế (test double) là một đối tượng hoặc dịch vụ được đưa vào thay cho phụ thuộc mà phần mềm thường sử dụng. Nó giúp kiểm soát đầu vào, phản hồi, trạng thái hoặc tương tác trong một kiểm thử.

Ví dụ, khi kiểm tra dịch vụ đặt hàng, nhóm có thể thay cổng thanh toán thật bằng một đối tượng trả về kết quả thành công hoặc thất bại theo kịch bản. Khi kiểm tra logic truy vấn, nhóm có thể dùng repository giả lưu dữ liệu trong bộ nhớ thay cho cơ sở dữ liệu thật.

Các test double phổ biến gồm:

| Loại | Mục đích | Ví dụ |
|---|---|---|
| Dummy | Được truyền vào để đáp ứng chữ ký hàm nhưng không được sử dụng | Một đối tượng context không được đọc trong kiểm thử |
| Stub | Trả về phản hồi đã định trước khi được gọi | Cổng thanh toán trả về APPROVED hoặc DECLINED |
| Fake | Có triển khai đơn giản nhưng hoạt động được trong phạm vi kiểm thử | Repository lưu bản ghi trong bộ nhớ, thay cho cơ sở dữ liệu |
| Spy | Ghi nhận cách đối tượng được gọi, có thể chuyển tiếp hành vi thật | Ghi lại số lần gửi thông báo |
| Mock | Thiết lập kỳ vọng về tương tác và xác minh kỳ vọng đó | Xác minh dịch vụ gửi đúng một yêu cầu hoàn tiền với mã giao dịch tương ứng |

Các thư viện có thể hỗ trợ tạo spy hoặc mock từ cùng một đối tượng. Điều quan trọng là hiểu mục tiêu của test double đang dùng: cung cấp phản hồi, mô phỏng một phụ thuộc có thể hoạt động, ghi nhận tương tác hay xác minh một hợp đồng tương tác.

Không nên gọi mọi test double là mock. Cách gọi chính xác giúp người đọc biết kiểm thử đang xác minh kết quả nghiệp vụ hay xác minh cách các thành phần giao tiếp.

## 2. Vì sao dùng thành phần thay thế?

Thành phần thay thế có ích khi phụ thuộc thật khó khởi tạo, chậm, tốn phí, không ổn định hoặc không thể tạo ra một tình huống hiếm theo cách an toàn.

Những mục đích phổ biến:

- **Cô lập logic:** kiểm tra một đơn vị mà không cần khởi động cơ sở dữ liệu, hàng đợi hoặc dịch vụ bên ngoài.
- **Kiểm soát phản hồi:** chủ động tạo thành công, thất bại, timeout, dữ liệu sai hoặc phản hồi bất thường.
- **Tăng tốc:** chạy kiểm thử nhanh và thường xuyên trong quá trình phát triển.
- **Tính xác định:** giảm ảnh hưởng của mạng, thời gian, trạng thái dùng chung và dịch vụ bên ngoài.
- **Tạo tình huống hiếm:** mô phỏng lỗi khó tái hiện như mất kết nối đúng thời điểm, callback đến lặp hoặc dịch vụ phản hồi sai thứ tự.
- **Giảm chi phí và rủi ro:** tránh gọi dịch vụ tính phí, gửi thông báo thật hoặc tạo giao dịch tài chính khi kiểm thử.

Những lợi ích này đi kèm một giới hạn: test double chỉ thực hiện những hành vi mà người viết đã đưa vào. Nó có thể không thể hiện hết quy tắc, giới hạn, độ trễ, thứ tự sự kiện hoặc lỗi của phụ thuộc thật.

## 3. Sai lệch giữa thành phần thay thế và môi trường thực tế

Sai lệch xuất hiện khi hành vi mà kiểm thử giả định khác với hành vi của phụ thuộc hoặc môi trường thật theo cách có thể làm thay đổi kết quả, mức độ tin cậy hoặc quyết định phát hành.

### 3.1. Sai lệch về giao diện và hợp đồng

Test double có thể dùng sai tên trường, kiểu dữ liệu, mã trạng thái, định dạng ngày giờ, header, schema hoặc quy tắc tương thích phiên bản.

Ví dụ, stub trả về một trường luôn có giá trị, trong khi API thật có thể bỏ trường đó, trả về null hoặc thay đổi schema theo phiên bản. Kiểm thử đơn vị vẫn đạt nhưng bộ phân tích phản hồi có thể lỗi khi gặp dữ liệu thực tế.

### 3.2. Sai lệch về ngữ nghĩa nghiệp vụ

Hai thành phần có thể dùng cùng cấu trúc dữ liệu nhưng hiểu kết quả khác nhau. Một stub có thể coi HTTP 200 là thanh toán thành công, trong khi dịch vụ thật chỉ xác nhận đã tiếp nhận yêu cầu và kết quả cuối cùng đến qua webhook.

Các khác biệt thường gặp:

- Đã tiếp nhận yêu cầu so với đã hoàn tất nghiệp vụ.
- Thành công một phần so với thành công toàn bộ.
- Thời điểm ghi nhận so với thời điểm đối soát.
- Giá trị mặc định, làm tròn, múi giờ hoặc đơn vị đo.
- Thứ tự ưu tiên của quy tắc và cách xử lý ngoại lệ.

### 3.3. Sai lệch về trạng thái và tính nhất quán

Fake thường giữ trạng thái đơn giản trong bộ nhớ. Dịch vụ thật có thể lưu trạng thái phân tán, cập nhật bất đồng bộ, có độ trễ nhất quán hoặc cần đối soát giữa nhiều hệ thống.

Một fake có thể trả về dữ liệu vừa ghi ngay lập tức, trong khi hệ thống thật có thể cần thời gian để dữ liệu xuất hiện ở bản đọc hoặc dịch vụ phụ thuộc. Nếu kiểm thử không mô phỏng được trạng thái trung gian, lỗi về thứ tự hoặc đồng bộ có thể bị bỏ sót.

### 3.4. Sai lệch về lỗi và khả năng phục hồi

Stub thường chỉ trả về vài lỗi đã định trước. Dịch vụ thật có thể trả về nhiều loại lỗi với cách xử lý khác nhau:

- Lỗi xác thực hoặc phân quyền.
- Lỗi giới hạn tốc độ, hạn mức hoặc quota.
- Timeout trước khi nhận phản hồi.
- Kết nối bị đóng sau khi yêu cầu đã được xử lý.
- Lỗi tạm thời cần retry và lỗi vĩnh viễn không nên retry.
- Phản hồi không đúng schema hoặc không thể phân tích.
- Callback lặp, đến muộn hoặc sai thứ tự.

Một khác biệt đặc biệt nguy hiểm là không biết yêu cầu đã được xử lý hay chưa khi kết nối bị ngắt. Nếu hệ thống gửi lại mà không có cơ chế idempotency, giao dịch hoặc tác động phụ có thể bị lặp.

### 3.5. Sai lệch về thời gian và đồng thời

Fake có thể thực thi mọi thao tác tuần tự và tức thời. Hệ thống thật có độ trễ mạng, xử lý song song, tranh chấp cập nhật, khóa, giới hạn thời gian và thứ tự thông điệp không cố định.

Các vấn đề dễ bị bỏ sót:

- Hai yêu cầu cập nhật cùng một bản ghi cùng lúc.
- Callback đến trước khi luồng tạo giao dịch hoàn tất.
- Retry xảy ra khi yêu cầu đầu tiên vẫn đang được xử lý.
- Một tác vụ hết hạn trong khi tác vụ khác đang cập nhật trạng thái.
- Hàng đợi gửi thông điệp theo thứ tự khác với thứ tự tạo.

### 3.6. Sai lệch về dữ liệu và ràng buộc

Dữ liệu giả thường sạch, nhỏ và hợp lệ. Dữ liệu thực có thể có bản ghi cũ, giá trị thiếu, ký tự đặc biệt, dữ liệu trùng, giới hạn kích thước, ràng buộc khóa ngoại, độ chính xác số hoặc quy tắc mã hóa khác nhau.

Fake repository có thể chấp nhận hai bản ghi có cùng mã định danh, trong khi cơ sở dữ liệu thật từ chối do unique constraint. Một fake cũng có thể không mô phỏng transaction, rollback, isolation level hoặc hành vi khi deadlock.

### 3.7. Sai lệch về cấu hình, bảo mật và quyền truy cập

Môi trường giả lập có thể dùng thông tin xác thực đơn giản, bỏ qua TLS, chữ ký, phân quyền hoặc chính sách mạng. Môi trường thật có thể áp dụng certificate, token hết hạn, giới hạn IP, secret rotation, firewall và quyền theo vai trò.

Một kiểm thử thành công với tài khoản quản trị trong môi trường giả lập không chứng minh rằng dịch vụ hoạt động đúng với quyền tối thiểu ở môi trường triển khai.

### 3.8. Sai lệch về hiệu năng và tài nguyên

Test double chạy trong cùng tiến trình thường nhanh hơn nhiều so với gọi qua mạng hoặc truy cập dịch vụ thật. Nó không phản ánh đầy đủ thông lượng, độ trễ, giới hạn kết nối, kích thước payload, quota, tiêu thụ bộ nhớ hoặc chi phí tài nguyên.

Do đó, kiểm thử dùng fake không thể thay thế đánh giá hiệu năng của hệ thống tích hợp trong điều kiện tải đại diện.

## 4. Phân biệt test double với môi trường giả lập

Test double thường thay thế một đối tượng hoặc một phụ thuộc ở ranh giới cụ thể. Môi trường giả lập có thể thay thế một hệ thống hoặc nhóm dịch vụ lớn hơn, ví dụ sandbox của nhà cung cấp thanh toán, giả lập cloud, database container hoặc môi trường staging.

| Hình thức | Phần được thay thế | Giá trị | Khoảng trống thường còn lại |
|---|---|---|---|
| Stub/mock trong kiểm thử đơn vị | Một đối tượng hoặc cổng giao tiếp | Kiểm tra logic nhanh, kiểm soát tình huống | Không xác minh giao thức và hành vi thật |
| Fake repository | Lớp truy cập dữ liệu | Kiểm tra logic sử dụng repository | Không phản ánh đầy đủ SQL, transaction và ràng buộc DB |
| Service virtualization | Một dịch vụ hoặc API bên ngoài | Mô phỏng giao tiếp và nhiều phản hồi | Độ trung thực phụ thuộc mô hình và dữ liệu được cấu hình |
| Sandbox nhà cung cấp | Hệ thống thử nghiệm của bên thứ ba | Xác minh giao thức gần với dịch vụ thật | Có thể khác dữ liệu, quota, tải, cấu hình và quy trình production |
| Staging hoặc môi trường tiền sản xuất | Một phần lớn kiến trúc triển khai | Kiểm tra tích hợp và cấu hình gần thực tế | Không hoàn toàn giống dữ liệu, tải, quyền và hạ tầng production |

Không có một cấp mô phỏng duy nhất phù hợp cho mọi rủi ro. Nhóm cần hiểu chính xác điều gì được thay thế và điều gì vẫn được giữ thật trong mỗi môi trường.

## 5. Đánh giá mức độ sai lệch một cách có hệ thống

### Bước 1: Lập danh mục phụ thuộc và điểm thay thế

Liệt kê các phụ thuộc được thay thế trong từng bộ kiểm thử: cơ sở dữ liệu, API, hàng đợi, đồng hồ hệ thống, dịch vụ thanh toán, kho tệp, dịch vụ gửi email hoặc hệ thống nhận dạng.

Với mỗi phụ thuộc, ghi:

- Thành phần hoặc dịch vụ thật.
- Test double hoặc môi trường thay thế đang dùng.
- Bộ kiểm thử nào phụ thuộc vào nó.
- Hợp đồng, phiên bản và chủ sở hữu của phụ thuộc.
- Các hành vi đã mô phỏng và các hành vi chưa mô phỏng.

### Bước 2: Xác định rủi ro nếu mô phỏng sai

Đánh giá tác động của sai lệch theo nghiệp vụ, dữ liệu, bảo mật, độ tin cậy, hiệu năng và khả năng vận hành. Ưu tiên phụ thuộc có thể gây giao dịch lặp, mất dữ liệu, sai số tiền, lộ thông tin hoặc gián đoạn dịch vụ.

Không cần mô phỏng mọi chi tiết của phụ thuộc thật. Chỉ cần nhận diện những khác biệt có thể làm thay đổi kết luận kiểm thử hoặc quyết định phát hành.

### Bước 3: Xác định hợp đồng và hành vi chuẩn

Chọn nguồn có thẩm quyền để mô tả:

- Endpoint, phương thức, schema, header và phiên bản.
- Mã phản hồi và ý nghĩa nghiệp vụ.
- Quy tắc xác thực, phân quyền và chữ ký.
- Trạng thái, sự kiện, callback và thứ tự xử lý.
- Timeout, retry, idempotency và giới hạn tốc độ.
- Điều kiện dữ liệu, ràng buộc và quy tắc chuyển đổi.

Nguồn chuẩn có thể là OpenAPI, schema sự kiện, tài liệu nhà cung cấp, tiêu chí chấp nhận, chính sách nghiệp vụ hoặc hợp đồng đã được các nhóm phê duyệt.

### Bước 4: So sánh cùng một tình huống trên các cấp môi trường

Chọn một tập tình huống đại diện và kiểm tra hành vi của test double, sandbox và phụ thuộc thật ở nơi an toàn. So sánh theo hợp đồng và kết quả nghiệp vụ, không chỉ so sánh nội dung phản hồi từng byte.

Ví dụ, cả stub và nhà cung cấp thật có thể trả về mã khác nhau nhưng cùng thể hiện trạng thái nghiệp vụ đã được định nghĩa. Ngược lại, hai phản hồi HTTP giống nhau có thể mang ý nghĩa khác nhau nếu một bên mới tiếp nhận còn bên kia đã hoàn tất giao dịch.

### Bước 5: Phân loại sai lệch và quyết định xử lý

Phân biệt:

- Sai lệch không ảnh hưởng đến hành vi hoặc nằm ngoài mục tiêu kiểm thử.
- Sai lệch có thể chấp nhận nếu được ghi rõ giới hạn.
- Sai lệch cần cập nhật test double hoặc hợp đồng.
- Sai lệch cần bổ sung kiểm thử tích hợp với phụ thuộc thật.
- Sai lệch nghiêm trọng cần xử lý trước khi phát hành.

Ghi rõ người chịu trách nhiệm, mức ưu tiên, bằng chứng cần có và điều kiện đóng phát hiện.

### Bước 6: Duy trì mô hình thay thế

Khi API, schema, chính sách hoặc phiên bản phụ thuộc thay đổi, cập nhật test double, dữ liệu và kiểm thử hợp đồng. Nên có chủ sở hữu và quy trình rà soát thay đổi để tránh việc mô hình thay thế trở nên lỗi thời.

## 6. Các kỹ thuật phát hiện sai lệch

### 6.1. Kiểm thử hợp đồng (contract testing)

Kiểm thử hợp đồng xác minh rằng bên cung cấp và bên sử dụng tuân thủ một thỏa thuận giao tiếp. Hợp đồng có thể mô tả endpoint, cấu trúc thông điệp, kiểu dữ liệu, trạng thái, quy tắc tương thích và ý nghĩa phản hồi.

Trong mô hình consumer-driven contract, bên sử dụng ghi lại những tương tác mà nó cần; bên cung cấp xác minh rằng phiên bản dịch vụ đáp ứng các tương tác đó. Cách này giúp phát hiện sớm sai lệch giữa stub do consumer dùng và API do provider cung cấp.

Kiểm thử hợp đồng hữu ích nhưng không chứng minh toàn bộ hành vi nghiệp vụ, tải, bảo mật hoặc khả năng phục hồi. Nó cần được kết hợp với kiểm thử tích hợp và các hoạt động khác theo rủi ro.

### 6.2. Kiểm thử tích hợp với phụ thuộc thật

Thay thế một phần phụ thuộc bằng dịch vụ hoặc hạ tầng thật trong môi trường kiểm thử có kiểm soát. Ví dụ:

- Chạy với database thật trong container để xác minh SQL, constraint và transaction.
- Gọi API sandbox của nhà cung cấp để xác minh xác thực, schema và callback.
- Dùng message broker thật để kiểm tra retry, acknowledgement và thứ tự xử lý.
- Kiểm tra hệ thống nhận dạng với token, scope và thời hạn thực tế.

Không nhất thiết phải dùng toàn bộ hệ thống production. Chọn đúng ranh giới cần xác minh và cô lập dữ liệu để có thể chạy an toàn, lặp lại.

### 6.3. Kiểm thử so sánh (differential testing)

Chạy cùng đầu vào qua hai cách triển khai hoặc hai môi trường và so sánh kết quả theo những thuộc tính đã xác định. Cách này có thể phát hiện khác biệt giữa fake và dịch vụ thật, hoặc giữa phiên bản cũ và mới.

Kết quả cần được chuẩn hóa trước khi so sánh. Có thể bỏ qua trường thời gian, mã định danh ngẫu nhiên hoặc thứ tự không có ý nghĩa; vẫn phải so sánh những thuộc tính nghiệp vụ như số tiền, trạng thái, quyền và tác động dữ liệu.

Không nên giả định một bên luôn đúng. Khi có khác biệt, cần xác định oracle hoặc nguồn hợp đồng có thẩm quyền để quyết định bên nào sai.

### 6.4. Kiểm thử lỗi và khả năng phục hồi

Chủ động tạo timeout, mất kết nối, lỗi tạm thời, phản hồi sai định dạng, callback lặp và lỗi giữa chừng. Xác minh retry, backoff, idempotency, rollback hoặc bù trừ.

Test double rất hữu ích để tạo lỗi hiếm một cách xác định. Sau đó, cần xác minh một số trường hợp đại diện với dịch vụ hoặc hạ tầng thật vì cách ngắt kết nối, giữ kết nối và xử lý yêu cầu có thể khác.

### 6.5. Môi trường staging và kiểm tra gần production

Staging giúp xác minh cấu hình, quyền, mạng, triển khai và tích hợp trong một kiến trúc gần production. Cần ghi nhận khác biệt về phiên bản, dữ liệu, secret, quota, vùng triển khai và tải.

Nếu có kiểm thử trên lưu lượng thật, cần dùng cơ chế an toàn như canary, synthetic transaction hoặc shadow traffic chỉ đọc. Không gửi lại yêu cầu có thể tạo thanh toán, hoàn tiền, gửi thông báo hoặc thay đổi dữ liệu thật nếu chưa có cơ chế cô lập tác động.

## 7. Ví dụ: stub cổng thanh toán và nhà cung cấp thật

Giả sử dịch vụ đơn hàng gọi cổng thanh toán. Trong kiểm thử đơn vị, nhóm dùng stub với hai phản hồi:

- APPROVED: giao dịch thành công.
- DECLINED: giao dịch bị từ chối.

Kiểm thử xác minh đơn chuyển sang trạng thái phù hợp. Tuy nhiên, nhà cung cấp thật có thể xử lý bất đồng bộ: yêu cầu ban đầu trả về ACCEPTED, sau đó webhook mới thông báo kết quả cuối cùng.

### 7.1. Những sai lệch có thể xuất hiện

| Khía cạnh | Stub đơn giản | Nhà cung cấp thật | Rủi ro |
|---|---|---|---|
| Thời điểm phản hồi | Trả kết quả cuối ngay lập tức | Trả ACCEPTED rồi gửi webhook | Đơn bị xác nhận quá sớm |
| Trạng thái | Chỉ có APPROVED/DECLINED | Có PENDING, AUTHORIZED, CAPTURED, FAILED, REVERSED | Xử lý thiếu trạng thái trung gian |
| Callback | Không có hoặc chỉ gọi một lần | Có thể lặp, đến muộn hoặc sai thứ tự | Cập nhật trạng thái hoặc ghi nhận tiền trùng |
| Xác thực | Bỏ qua chữ ký | Yêu cầu kiểm tra chữ ký và timestamp | Chấp nhận callback giả |
| Timeout | Trả lỗi cố định | Có thể timeout sau khi giao dịch đã được xử lý | Retry tạo giao dịch trùng |
| Dữ liệu | Trả về một schema đơn giản | Có trường tùy chọn, mã lỗi và phiên bản | Lỗi phân tích phản hồi |
| Giới hạn | Không giới hạn số yêu cầu | Có quota và rate limit | Thất bại khi tải hoặc gọi quá nhanh |
| Đối soát | Không mô phỏng | Có quy trình đối soát và hoàn tất sau đó | Trạng thái nội bộ không khớp số liệu nhà cung cấp |

### 7.2. Bổ sung bằng chứng theo từng cấp

**Kiểm thử đơn vị:** tiếp tục dùng stub để kiểm tra logic đơn hàng với các kết quả thành công, thất bại, timeout và trạng thái chờ. Bổ sung callback lặp, phản hồi sai schema và retry.

**Kiểm thử hợp đồng:** xác minh adapter thanh toán gửi đúng request, đọc đúng response, kiểm tra chữ ký webhook và tương thích với schema được công bố.

**Kiểm thử tích hợp sandbox:** gửi giao dịch thử, nhận callback, kiểm tra trạng thái bất đồng bộ, xác thực chữ ký và xử lý trường hợp timeout hoặc gửi lại theo khả năng sandbox hỗ trợ.

**Kiểm thử gần production:** xác minh cấu hình secret, TLS, mạng, log, cảnh báo và quy trình đối soát trong môi trường triển khai đại diện. Dùng giao dịch thử hoặc cơ chế cô lập được nhà cung cấp cho phép.

### 7.3. Điều kiện kết luận

Không thể kết luận tích hợp thanh toán đáng tin cậy chỉ vì các test case dùng stub đều đạt. Cần có bằng chứng rằng adapter tuân thủ hợp đồng, callback được xác thực, giao dịch lặp không tạo tác động lặp và trạng thái cuối có thể đối soát. Mức kiểm tra cần thiết phụ thuộc vào rủi ro tài chính và khả năng hỗ trợ của sandbox.

## 8. Chọn mức độ thay thế theo rủi ro

Không phải phụ thuộc nào cũng cần kiểm thử với môi trường thật ở mọi lần chạy. Có thể phân bổ như sau:

| Mức rủi ro/phụ thuộc | Cách tiếp cận phù hợp | Tần suất gợi ý |
|---|---|---|
| Logic nội bộ, phụ thuộc đơn giản | Unit test với stub/fake/mock phù hợp | Mỗi thay đổi mã |
| Adapter hoặc API có hợp đồng ổn định | Unit test cộng contract test | Mỗi pull request hoặc khi hợp đồng thay đổi |
| Database, broker hoặc dịch vụ nội bộ quan trọng | Integration test với hạ tầng thật trong môi trường kiểm soát | CI, theo lịch hoặc trước phát hành |
| Nhà cung cấp bên ngoài có tác động tài chính hoặc dữ liệu | Contract test, sandbox và kiểm thử luồng đại diện | Khi adapter, cấu hình hoặc phiên bản thay đổi; trước phát hành |
| Rủi ro vận hành, hiệu năng hoặc bảo mật cao | Môi trường gần production, kiểm thử chuyên biệt và theo dõi sau triển khai | Theo kế hoạch phát hành và mức rủi ro |

Đây là gợi ý, không phải lịch cố định. Nhóm nên cân bằng độ tin cậy, chi phí, tốc độ phản hồi và giới hạn của môi trường thử nghiệm.

## 9. Thiết kế test double có độ trung thực phù hợp

Một test double tốt không cần tái tạo toàn bộ hệ thống thật. Nó cần mô phỏng chính xác những đặc điểm liên quan đến mục tiêu kiểm thử.

Khi thiết kế, hãy:

- Dùng cùng interface hoặc schema với phụ thuộc thật.
- Tái sử dụng mô hình dữ liệu và kiểu dữ liệu được chia sẻ khi phù hợp.
- Biểu diễn các trạng thái và lỗi có ý nghĩa nghiệp vụ.
- Mô phỏng bất đồng bộ, retry hoặc callback nếu chúng thuộc rủi ro cần kiểm tra.
- Đặt hành vi mặc định rõ ràng; tránh trả thành công cho mọi yêu cầu.
- Cho phép kiểm thử tạo tình huống lỗi một cách xác định.
- Ghi rõ hành vi nào chưa được mô phỏng.
- Đặt tên test double theo vai trò và kịch bản để người đọc không nhầm với dịch vụ thật.

Không nên sao chép toàn bộ mã triển khai của phụ thuộc vào fake. Hai bản sao cùng chứa một lỗi sẽ không giúp phát hiện sai lệch. Fake nên đơn giản, tập trung vào hợp đồng cần thiết và được kiểm tra độc lập bằng ví dụ chuẩn.

## 10. Quản lý dữ liệu và môi trường so sánh

Khi so sánh test double với môi trường thật, phải bảo đảm khác biệt về dữ liệu hoặc cấu hình không làm sai lệch kết luận.

Những điều cần kiểm soát:

- Dùng cùng bộ đầu vào hoặc dữ liệu tương đương về ngữ nghĩa.
- Ghi phiên bản API, schema, cấu hình và thư viện adapter.
- Kiểm soát thời gian, múi giờ, locale và dữ liệu ngẫu nhiên.
- Tách biệt dữ liệu của từng lần chạy để tránh trạng thái cũ ảnh hưởng.
- Làm sạch hoặc reset dữ liệu giữa các kiểm thử khi cần.
- Không dùng dữ liệu cá nhân hoặc bí mật production nếu chưa được phép và bảo vệ phù hợp.
- Ghi nhận giới hạn sandbox như quota, dữ liệu mô phỏng hoặc tính năng không được hỗ trợ.

Nếu môi trường thật không thể reset, dùng định danh giao dịch duy nhất, tài khoản thử nghiệm, dữ liệu có thể đối soát và quy trình dọn dẹp an toàn. Không để một lần chạy ảnh hưởng kết quả của lần tiếp theo.

## 11. Ghi nhận sai lệch và quyết định xử lý

Mỗi phát hiện nên có bản ghi đủ để nhóm hiểu khoảng trống và theo dõi hành động:

| Trường | Nội dung |
|---|---|
| Phụ thuộc | Tên dịch vụ, database, broker hoặc thành phần |
| Thành phần thay thế | Stub, fake, mock, service virtualization hoặc sandbox |
| Phiên bản/hợp đồng | Phiên bản API, schema, tài liệu và cấu hình |
| Tình huống so sánh | Đầu vào, trạng thái ban đầu và điều kiện |
| Kết quả từ test double | Phản hồi và tác động quan sát được |
| Kết quả từ môi trường thật | Phản hồi và tác động quan sát được |
| Mô tả sai lệch | Khác biệt về giao diện, ngữ nghĩa, trạng thái, lỗi hoặc thời gian |
| Tác động/rủi ro | Hậu quả nếu không phát hiện |
| Hành động | Sửa double, bổ sung contract/integration test, cập nhật adapter hoặc chấp nhận giới hạn |
| Owner và bằng chứng đóng | Người chịu trách nhiệm, thời hạn và kết quả xác minh |

Một sai lệch có thể được chấp nhận nếu không ảnh hưởng đến rủi ro đang kiểm tra và được ghi rõ. Tuy nhiên, không nên dùng cụm từ "đã kiểm thử đầy đủ" khi còn những khác biệt quan trọng chưa được xác minh.

## 12. Đo lường độ tin cậy của thành phần thay thế

Có thể theo dõi:

- Số sai lệch hợp đồng được phát hiện giữa double và provider.
- Số lỗi chỉ xuất hiện trong kiểm thử tích hợp hoặc sandbox.
- Số sự cố production bắt nguồn từ hành vi chưa được mô phỏng.
- Tỷ lệ test double được cập nhật khi hợp đồng thay đổi.
- Tỷ lệ kiểm thử thất bại do môi trường hoặc dữ liệu không ổn định.
- Thời gian từ lúc phát hiện sai lệch đến khi cập nhật double và kiểm thử liên quan.
- Số phụ thuộc quan trọng chưa có kiểm thử hợp đồng hoặc tích hợp thật.

Các chỉ số này nên được xem cùng mức rủi ro và mức độ nghiêm trọng. Số lượng sai lệch thấp không tự chứng minh độ trung thực cao nếu nhóm chưa có đủ tình huống so sánh.

## 13. Những sai lầm thường gặp

- **Tin rằng kiểm thử với mock đạt nghĩa là tích hợp sẽ đạt:** mock chỉ xác minh hành vi được mô phỏng. Cần contract test và kiểm thử tích hợp cho ranh giới quan trọng.
- **Dùng một stub luôn trả thành công:** bỏ qua lỗi, trạng thái chờ, timeout, retry và phản hồi bất thường.
- **Fake quá đơn giản so với rủi ro:** không mô phỏng transaction, constraint, trạng thái hoặc tính nhất quán cần thiết.
- **Sao chép logic thật vào fake:** hai bản sao có thể cùng chứa một lỗi và cho kết quả giống nhau nhưng sai.
- **Không quản lý phiên bản hợp đồng:** test double tiếp tục dùng schema cũ sau khi provider thay đổi.
- **Chỉ so sánh mã HTTP:** bỏ qua ý nghĩa nghiệp vụ, trạng thái cuối và tác động dữ liệu.
- **Chỉ kiểm thử sandbox:** giả định sandbox giống production về tải, dữ liệu, quota và cấu hình.
- **Chạy kiểm thử thật gây tác động ngoài ý muốn:** tạo giao dịch, gửi thông báo hoặc sửa dữ liệu không được cô lập.
- **Không ghi nhận giới hạn:** người đọc hiểu nhầm phần chưa được mô phỏng là đã được xác minh.
- **Loại bỏ mọi test double:** kiểm thử sẽ chậm và khó kiểm soát; cần chọn đúng mức thay thế theo mục tiêu.

## 14. Checklist trước khi dựa vào kết quả kiểm thử

- [ ] Đã xác định phụ thuộc nào được thay thế và vì sao.
- [ ] Loại test double và hành vi nó mô phỏng được ghi rõ.
- [ ] Interface, schema và hợp đồng đang dùng đúng phiên bản.
- [ ] Các khác biệt về ngữ nghĩa nghiệp vụ và trạng thái đã được xem xét.
- [ ] Lỗi, timeout, retry, callback lặp và hành vi bất đồng bộ được kiểm tra khi phù hợp.
- [ ] Dữ liệu, ràng buộc, transaction và tính nhất quán đã được đánh giá.
- [ ] Cấu hình, quyền truy cập, chữ ký và secret được xác minh ở cấp phù hợp.
- [ ] Phụ thuộc rủi ro cao có contract test hoặc kiểm thử tích hợp với hệ thống thật.
- [ ] Sandbox và staging có giới hạn được ghi nhận.
- [ ] Kiểm thử môi trường thật không tạo tác động không mong muốn.
- [ ] Sai lệch, owner và hành động xử lý được ghi lại.
- [ ] Test double được cập nhật khi hợp đồng hoặc hành vi phụ thuộc thay đổi.

## 15. Mối liên hệ giữa test double và bằng chứng thực tế

~~~mermaid
flowchart TD
    A["Xác định phụ thuộc và rủi ro"]
    B["Mô tả hợp đồng và hành vi chuẩn"]
    C["Thiết kế test double cho phản hồi nhanh"]
    D["Chạy unit test"]
    E["Contract test"]
    F["Integration test với phụ thuộc thật hoặc sandbox"]
    G["Kiểm thử gần production và theo dõi"]
    H["So sánh, phân loại sai lệch và cập nhật"]
    A --> B --> C --> D
    B --> E --> F --> G
    D --> H
    E --> H
    F --> H
    G --> H
    H -. "Cập nhật hợp đồng và test double" .-> B
~~~

Thành phần thay thế giúp nhóm kiểm tra nhanh và có kiểm soát, còn môi trường thực tế cung cấp bằng chứng về giao thức, trạng thái, dữ liệu và điều kiện vận hành mà mô phỏng có thể bỏ sót. Khi nhóm ghi rõ giới hạn của từng test double, xác minh hợp đồng và bổ sung kiểm thử tích hợp theo rủi ro, kết quả kiểm thử đơn vị và tích hợp sẽ đáng tin cậy hơn và phản ánh đúng hơn hành vi khi triển khai.
