# Chọn kiểm chứng qua UI, API hoặc phối hợp các giao diện

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), kiểm thử hệ thống và kiểm thử đầu cuối cần xác minh hành vi của sản phẩm ở ranh giới có ý nghĩa. Một hành vi có thể được kiểm tra qua giao diện người dùng (UI), qua giao diện lập trình ứng dụng (API), hoặc bằng cách phối hợp cả hai. Lựa chọn đúng giúp nhóm kiểm tra được rủi ro thực tế, tạo bằng chứng dễ hiểu và giữ bộ kiểm thử ổn định.

Không có một giao diện kiểm thử phù hợp cho mọi mục tiêu. UI test cho biết người dùng có thể thực hiện thao tác và nhận kết quả đúng trên giao diện hay không. API test cho biết hệ thống xử lý yêu cầu, quy tắc nghiệp vụ và dữ liệu qua hợp đồng API như thế nào. Kiểm thử kết hợp có thể xác minh một hành động trên UI tạo ra kết quả đúng ở API hoặc dữ liệu, hay dữ liệu được chuẩn bị qua API được hiển thị đúng trên UI. Cần lựa chọn dựa trên yêu cầu, rủi ro và bằng chứng còn thiếu.

## 1. Phân biệt kiểm chứng qua UI và API

### 1.1. Kiểm chứng qua giao diện người dùng

UI test tương tác với sản phẩm qua những gì người dùng nhìn thấy và sử dụng: trình duyệt, ứng dụng di động, desktop hoặc thiết bị chuyên dụng. Test có thể nhấn nút, nhập dữ liệu, chọn menu, điều hướng, đọc thông báo và kiểm tra trạng thái hiển thị.

UI test phù hợp để xác minh:

- Thành phần hiển thị đúng và có thể tương tác.
- Luồng điều hướng, biểu mẫu, trạng thái tải và thông báo lỗi.
- Hành vi phụ thuộc vào trình duyệt, thiết bị, kích thước màn hình hoặc quyền truy cập.
- Tính khả dụng, khả năng truy cập và các thao tác bàn phím hoặc trình đọc màn hình.
- Người dùng hoàn thành được một hành trình quan trọng từ đầu đến cuối.
- Dữ liệu từ backend được trình bày đúng và cập nhật phù hợp trên giao diện.

Ví dụ, trong luồng đăng nhập, UI test có thể xác minh người dùng nhập thông tin, gửi biểu mẫu, nhận thông báo lỗi khi mật khẩu sai và được chuyển đến trang chính khi đăng nhập thành công.

UI test cho bằng chứng gần với trải nghiệm người dùng, nhưng thường chậm hơn và dễ bị ảnh hưởng bởi rendering, animation, mạng, dữ liệu dùng chung và thay đổi giao diện. Nó cũng không phải cách hiệu quả nhất để kiểm tra hàng trăm tổ hợp dữ liệu hoặc mọi mã lỗi API.

### 1.2. Kiểm chứng qua API

API test gửi yêu cầu trực tiếp đến endpoint hoặc giao diện dịch vụ, sau đó xác minh mã phản hồi, header, payload, lỗi, dữ liệu và các tác dụng phụ có thể quan sát.

API test phù hợp để xác minh:

- Quy tắc nghiệp vụ được thực thi qua request.
- Xác thực, phân quyền và quyền sở hữu tài nguyên.
- Schema request/response, mã trạng thái và cách biểu diễn lỗi.
- Tạo, cập nhật, truy vấn và xóa dữ liệu.
- Idempotency, pagination, filtering, sorting và rate limiting.
- Tương thích API giữa các phiên bản hoặc consumer.
- Hành vi khi đầu vào sai, phụ thuộc timeout hoặc dịch vụ từ chối yêu cầu.

Ví dụ, test gửi yêu cầu tạo đơn hàng với giỏ hàng hợp lệ và xác minh API trả về mã tạo thành công, có orderId, tổng tiền đúng và trạng thái ban đầu phù hợp.

API test thường nhanh và ổn định hơn UI test cho các quy tắc backend. Nó cũng giúp kiểm tra nhiều biến thể dữ liệu với chi phí thấp. Tuy nhiên, một API trả kết quả đúng không chứng minh người dùng có thể tìm thấy nút thao tác, nhập biểu mẫu hoặc hiểu thông báo trên giao diện.

### 1.3. So sánh UI test và API test

| Khía cạnh | UI test | API test |
|---|---|---|
| Điểm tương tác | Giao diện người dùng trên trình duyệt hoặc thiết bị. | Endpoint hoặc giao diện dịch vụ. |
| Bằng chứng chính | Hành vi hiển thị và tương tác của người dùng. | Phản hồi, hợp đồng, quy tắc nghiệp vụ và dữ liệu qua API. |
| Tốc độ | Thường chậm hơn do cần khởi tạo UI và chờ rendering. | Thường nhanh hơn, dễ chạy nhiều biến thể. |
| Độ ổn định | Có thể nhạy với layout, animation, selector và môi trường browser. | Thường ổn định hơn, nhưng vẫn phụ thuộc môi trường và dữ liệu. |
| Phạm vi mạnh | Điều hướng, hiển thị, thao tác, khả năng truy cập và hành trình người dùng. | Logic backend, xác thực, phân quyền, dữ liệu, schema và lỗi. |
| Giới hạn | Khó kiểm tra chi tiết nhiều tổ hợp dữ liệu và khó định vị lỗi backend. | Không chứng minh UI hoạt động hoặc trình bày kết quả đúng. |
| Khi phù hợp | Rủi ro nằm ở trải nghiệm hoặc tích hợp qua giao diện. | Rủi ro nằm ở hợp đồng và hành vi backend. |

Một test được gọi là system test hay E2E không nhất thiết phải thao tác qua UI. API test có thể kiểm tra hệ thống ở cấp độ rộng nếu nó đi qua các thành phần thật cần xác minh. Tên tầng kiểm thử nên phản ánh phạm vi và mục tiêu, không chỉ công cụ được dùng.

## 2. Khi nào nên chọn UI test?

Hãy ưu tiên UI test khi hành vi cần xác minh chỉ có thể được đánh giá đầy đủ qua giao diện hoặc khi giao diện là một phần rủi ro chính.

### 2.1. Hành vi tương tác và điều hướng

UI test cần thiết khi yêu cầu liên quan đến cách người dùng thao tác:

- Một nút hoặc liên kết có thể được sử dụng đúng.
- Biểu mẫu kiểm tra dữ liệu và hiển thị lỗi ở đúng trường.
- Người dùng được điều hướng đến đúng trang hoặc bước tiếp theo.
- Modal, menu, tab, bộ lọc và trạng thái mở/đóng hoạt động đúng.
- Thao tác bàn phím và focus order đáp ứng yêu cầu.
- Trạng thái loading, disabled và retry được trình bày phù hợp.

Ví dụ, API có thể tạo đơn hàng thành công nhưng nút “Đặt hàng” bị vô hiệu hóa sai khi người dùng nhập mã bưu chính hợp lệ. API test không phát hiện được lỗi này.

### 2.2. Hiển thị dữ liệu và phản hồi người dùng

Dùng UI test khi cần xác minh:

- Giá, ngày tháng, đơn vị tiền tệ hoặc trạng thái được định dạng đúng.
- Thông báo thành công và lỗi rõ ràng, không gây hiểu nhầm.
- Dữ liệu được cập nhật sau khi lưu hoặc tải lại trang.
- Bảng, biểu đồ, danh sách và phân trang hiển thị đúng.
- Nội dung thay đổi theo vai trò, ngôn ngữ hoặc cấu hình.
- Trạng thái rỗng, dữ liệu lớn và nội dung dài được trình bày phù hợp.

Ví dụ, API trả totalAmount là 120000 nhưng giao diện hiển thị sai đơn vị hoặc làm tròn nhầm. Cần kiểm thử trên UI để xác nhận cách trình bày.

### 2.3. Khác biệt theo trình duyệt, thiết bị và khả năng truy cập

Nếu sản phẩm hỗ trợ nhiều trình duyệt, hệ điều hành, kích thước màn hình hoặc phương thức nhập, hãy chọn UI test cho các tổ hợp có rủi ro cao.

Kiểm thử có thể bao gồm:

- Layout responsive ở các kích thước màn hình cam kết.
- Tương tác trên cảm ứng, chuột và bàn phím.
- Focus, label, thông báo lỗi và trạng thái accessible.
- Hiển thị ngôn ngữ, font, ký tự đặc biệt và nội dung dài.
- Hành vi tải file, upload, camera hoặc quyền thiết bị khi sản phẩm sử dụng chúng.

Không cần chạy mọi ca nghiệp vụ trên mọi browser. Hãy chọn ma trận nền tảng theo mức sử dụng, cam kết hỗ trợ và lịch sử lỗi. Những quy tắc backend không phụ thuộc browser nên được kiểm tra qua API hoặc tầng phù hợp.

## 3. Khi nào nên chọn API test?

API test phù hợp khi mục tiêu nằm ở logic hệ thống, dữ liệu hoặc hợp đồng giao tiếp và không cần chứng minh thao tác giao diện.

### 3.1. Quy tắc nghiệp vụ và biến thể dữ liệu

Dùng API test để kiểm tra các trường hợp như:

- Đầu vào hợp lệ, không hợp lệ và giá trị biên.
- Quy tắc tính giá, giới hạn, điều kiện và trạng thái.
- Các vai trò hoặc quyền truy cập khác nhau.
- Trạng thái tài nguyên trước và sau thao tác.
- Yêu cầu trùng lặp, idempotency và xung đột cập nhật.
- Pagination, filtering và sorting với dữ liệu đại diện.

Ví dụ, một API tìm kiếm đơn hàng có thể cần kiểm tra nhiều kết hợp trạng thái, ngày tạo, người sở hữu và trang kết quả. Kiểm tra các biến thể này qua API nhanh hơn nhiều so với thao tác từng bộ lọc trên UI.

### 3.2. Hợp đồng và tương thích

API test hoặc contract test giúp xác minh:

- HTTP method, path, header và content type.
- Trường bắt buộc, kiểu dữ liệu và quy tắc nullable.
- Mã trạng thái cho thành công và lỗi.
- Schema và phiên bản API.
- Cách xử lý trường không biết hoặc trường mới.
- Tương thích ngược với client đang được hỗ trợ.

Ví dụ, API thay đổi từ trường customerId sang accountId. Contract test có thể phát hiện consumer cũ không còn tương thích trước khi UI test được chạy.

### 3.3. Bảo mật và phân quyền ở ranh giới dịch vụ

API test đặc biệt hữu ích để kiểm tra truy cập trực tiếp:

- Người chưa xác thực không được truy cập endpoint cần đăng nhập.
- Người dùng không thể đọc hoặc sửa tài nguyên của người khác.
- Vai trò chỉ có quyền đọc không thể thực hiện thao tác ghi.
- Token hết hạn hoặc sai chữ ký bị từ chối.
- Dữ liệu nhạy cảm không xuất hiện trong response ngoài phạm vi cho phép.
- Endpoint quản trị được bảo vệ đúng.

UI có thể ẩn nút không được phép, nhưng điều đó không chứng minh API từ chối request trực tiếp. Kiểm tra quyền phải được thực hiện tại ranh giới bảo mật có liên quan.

### 3.4. Tác dụng phụ và dữ liệu được lưu

API test có thể xác minh việc tạo hoặc cập nhật tài nguyên bằng cách đọc lại qua API công khai hoặc kiểm tra trạng thái qua cơ chế test phù hợp. Với rủi ro persistence, cần bảo đảm kiểm thử đi qua đường lưu trữ thật thay vì chỉ mock repository.

Ví dụ, gửi yêu cầu hủy đơn hàng và xác minh API truy vấn sau đó trả trạng thái CANCELLED, đồng thời thông tin hoàn tiền được biểu diễn đúng nếu thuộc hợp đồng.

## 4. Khi nào nên phối hợp UI và API?

Kiểm thử kết hợp hữu ích khi một kết luận cần bằng chứng từ cả trải nghiệm người dùng và hành vi backend. Nhóm có thể dùng API để chuẩn bị dữ liệu, thực hiện một hành động qua UI rồi xác minh kết quả qua API; hoặc thực hiện thao tác qua API và xác minh UI hiển thị dữ liệu mới.

### 4.1. UI thực hiện hành động, API xác minh kết quả

Cách này phù hợp khi cần chứng minh người dùng thực hiện được thao tác và backend lưu kết quả đúng.

Ví dụ:

1. Tạo tài khoản thử nghiệm và dữ liệu ban đầu bằng API.
2. Đăng nhập qua UI.
3. Người dùng cập nhật địa chỉ giao hàng.
4. UI hiển thị thông báo lưu thành công.
5. Gọi API đọc hồ sơ và xác minh địa chỉ được lưu đúng.

UI chứng minh luồng tương tác; API cung cấp xác nhận độc lập về trạng thái backend.

Cần bảo đảm API xác minh là một giao diện quan sát phù hợp và không bỏ qua hành vi mà test đang muốn kiểm tra. Nếu mục tiêu là xác minh người dùng thực sự nhìn thấy dữ liệu đã lưu sau khi tải lại, nên có bước tải lại trang và kiểm tra UI nữa.

### 4.2. API chuẩn bị dữ liệu, UI xác minh cách trình bày

Cách này phù hợp khi dữ liệu cần chuẩn bị phức tạp hoặc khó tạo qua UI.

Ví dụ:

1. Gọi API tạo một đơn hàng ở trạng thái DELIVERED.
2. Đăng nhập bằng tài khoản có quyền xem đơn.
3. Mở trang lịch sử đơn hàng.
4. Xác minh đơn xuất hiện đúng ngày, tổng tiền và trạng thái giao hàng.

API giúp tạo dữ liệu nhanh và xác định trước trạng thái. UI test tập trung vào việc trình bày và khả năng truy cập dữ liệu của người dùng.

Tuy nhiên, nếu yêu cầu bao gồm toàn bộ hành trình tạo đơn, việc chuẩn bị đơn bằng API sẽ bỏ qua bước đó. Khi ấy cần một test UI riêng thực hiện luồng tạo đơn.

### 4.3. API xác minh trạng thái, UI xác minh thông báo và điều hướng

Một số hành vi có cả kết quả backend và phản hồi trực quan:

- Sau khi hủy đơn, API trả trạng thái CANCELLED và UI hiển thị thông báo xác nhận.
- Sau khi cập nhật quyền, API phản ánh vai trò mới và UI chỉ hiển thị chức năng được phép.
- Sau khi gửi biểu mẫu, API trả lỗi validation và UI hiển thị lỗi cạnh đúng trường.
- Sau khi thanh toán, API cho biết giao dịch đã hoàn tất và UI hiển thị trang xác nhận.

Trong các trường hợp này, hai loại assertion có thể bổ sung bằng chứng. Không cần lặp lại toàn bộ dữ liệu kiểm thử API trong UI; hãy chọn một số trường hợp đại diện để xác nhận kết nối giữa hai phía.

### 4.4. Phân biệt phối hợp kiểm thử với việc kiểm tra hai lần cùng một điều

Kết hợp UI và API không tự động làm test mạnh hơn. Nếu cả hai chỉ xác nhận cùng một trạng thái đơn giản mà không kiểm tra thêm ranh giới, chi phí tăng nhưng giá trị bằng chứng ít thay đổi.

Trước khi thêm assertion, hãy ghi rõ câu hỏi riêng:

- UI: người dùng có thực hiện được thao tác và nhận phản hồi phù hợp không?
- API: backend có lưu và trả trạng thái đúng không?
- Kết hợp: thao tác thực tế trên UI có tạo ra trạng thái backend tương ứng và UI có phản ánh trạng thái đó không?

## 5. Ma trận quyết định lựa chọn UI, API hoặc kết hợp

Bảng sau giúp chọn cách tiếp cận ban đầu theo mục tiêu.

| Mục tiêu cần xác minh | Cách tiếp cận ưu tiên | Lý do |
|---|---|---|
| Quy tắc tính giá và giá trị biên | API hoặc unit test ở tầng phù hợp | Nhiều tổ hợp dữ liệu cần được kiểm tra nhanh. |
| Schema và mã lỗi API | API/contract test | Mục tiêu nằm ở hợp đồng dịch vụ. |
| Phân quyền endpoint | API test | Cần kiểm tra request trực tiếp tại ranh giới bảo mật. |
| Nút, biểu mẫu và điều hướng | UI test | Hành vi chỉ xuất hiện qua giao diện. |
| Responsive và khả năng truy cập | UI test | Cần quan sát giao diện và phương thức tương tác. |
| Trạng thái dữ liệu sau thao tác | API test hoặc integration test | Có thể đọc lại dữ liệu qua ranh giới dịch vụ hoặc kho dữ liệu. |
| Người dùng thao tác và backend lưu đúng | UI + API | Cần bằng chứng từ cả tương tác và trạng thái. |
| Dữ liệu backend hiển thị đúng | API chuẩn bị dữ liệu + UI | API tạo trạng thái đầu vào, UI xác minh cách trình bày. |
| Hành trình thanh toán quan trọng | UI E2E + API assertion có chọn lọc | Cần xác minh trải nghiệm và kết quả giao dịch. |
| Tương thích nhiều trình duyệt | UI test | API test không kiểm tra rendering và hành vi browser. |

Có thể dùng các câu hỏi nhanh:

- Nếu người dùng không mở UI mà gọi API trực tiếp, hành vi cần kiểm tra có còn ý nghĩa không? Nếu có, API test có thể phù hợp.
- Nếu API trả đúng nhưng người dùng vẫn có thể gặp lỗi, UI test có cần thiết không? Nếu có, hãy kiểm tra giao diện.
- Nếu cần chứng minh thao tác trên UI tạo đúng trạng thái backend, có cần cả hai không? Nếu có, thiết kế một kịch bản kết hợp có assertion riêng cho mỗi phía.

## 6. Thiết kế luồng kiểm thử kết hợp đáng tin cậy

Một test kết hợp cần xác định rõ vai trò của từng giao diện, dữ liệu và điểm xác nhận. Nếu không, test có thể trở nên phức tạp và khó chẩn đoán.

### 6.1. Xác định điểm bắt đầu và hành động chính

Ghi rõ test bắt đầu bằng API hay UI, và hành động nào cần được thực hiện qua giao diện thật.

Ví dụ, nếu mục tiêu là kiểm tra chức năng người dùng đổi địa chỉ giao hàng, hành động đổi địa chỉ phải được thực hiện trên UI. Nếu tạo đơn hàng lịch sử chỉ là bước chuẩn bị, có thể dùng API để giảm thời gian setup.

### 6.2. Chuẩn bị dữ liệu bằng API có kiểm soát

API setup có thể tạo người dùng, vai trò, đơn hàng hoặc trạng thái cần thiết. Dữ liệu cần:

- Có định danh duy nhất cho từng lần chạy.
- Không phụ thuộc vào dữ liệu của test khác.
- Có trạng thái ban đầu rõ ràng.
- Được dọn dẹp hoặc cô lập sau khi test.
- Không chứa bí mật hoặc dữ liệu cá nhân thật không cần thiết.

Nếu API setup bỏ qua một hành vi nằm trong phạm vi cần kiểm tra, hãy tạo một test khác để kiểm tra hành vi đó qua UI hoặc API đúng mục tiêu.

### 6.3. Thực hiện hành động qua giao diện khi đó là mục tiêu

Dùng selector ổn định như role, accessible name hoặc test ID được quản lý. Ưu tiên thao tác gần với cách người dùng tương tác. Tránh phụ thuộc vào vị trí pixel hoặc cấu trúc DOM quá sâu nếu không cần thiết.

Chờ điều kiện có ý nghĩa như nút được bật, thông báo xuất hiện, trạng thái tải kết thúc hoặc trang chuyển sang trạng thái mong đợi. Tránh dùng thời gian chờ cố định dài vì nó làm test chậm và vẫn có thể thất bại khi môi trường chậm hơn dự kiến.

### 6.4. Xác minh backend qua API

Sau thao tác UI, gọi API đọc dữ liệu hoặc trạng thái liên quan. Kiểm tra những trường có ý nghĩa với mục tiêu, chẳng hạn:

- ID tài nguyên.
- Trạng thái nghiệp vụ.
- Số tiền, đơn vị tiền tệ hoặc dữ liệu đã cập nhật.
- Thời điểm và chủ sở hữu.
- Trạng thái xử lý bất đồng bộ.

Nếu dữ liệu cập nhật bất đồng bộ, dùng polling có giới hạn và điều kiện rõ ràng thay vì truy vấn một lần rồi giả định dữ liệu đã sẵn sàng.

### 6.5. Xác minh lại UI khi cần

Nếu mục tiêu bao gồm việc người dùng nhìn thấy trạng thái mới, hãy tải lại hoặc điều hướng đến màn hình phù hợp và xác nhận UI phản ánh đúng trạng thái backend. Điều này giúp phát hiện cache cũ, lỗi đồng bộ hoặc mapping hiển thị sai.

### 6.6. Dọn dữ liệu và lưu bằng chứng

Dọn tài nguyên được tạo trong test theo cách an toàn. Ghi lại ID test, request/response đã lọc dữ liệu nhạy cảm, screenshot khi hữu ích, trace ID và kết quả assertion. Khi test thất bại, bằng chứng cần đủ để biết lỗi xảy ra ở thao tác UI, API hay quá trình đồng bộ.

## 7. Ví dụ: kiểm thử luồng đặt hàng

Giả sử người dùng có thể đặt hàng trên website. Luồng gồm đăng nhập, xem giỏ hàng, chọn địa chỉ, xác nhận đơn, gọi checkout API, lưu đơn hàng và hiển thị trang xác nhận.

### 7.1. Phân rã mục tiêu

| Mục tiêu | UI | API | Kết hợp |
|---|---|---|---|
| Người dùng mở được giỏ hàng | Xác minh điều hướng và hiển thị. | Không cần cho mục tiêu UI. | API tạo giỏ hàng trước để chuẩn bị dữ liệu. |
| Tổng tiền được tính đúng | Một kịch bản đại diện hiển thị tổng tiền. | Kiểm tra nhiều tổ hợp giá, thuế và giảm giá. | Xác nhận một đơn đại diện hiển thị đúng tổng tiền backend trả về. |
| Địa chỉ không hợp lệ bị từ chối | Kiểm tra lỗi hiển thị cạnh trường. | Kiểm tra mã lỗi và schema phản hồi. | Gửi dữ liệu qua UI rồi xác minh response hoặc trạng thái không tạo đơn. |
| Đơn hàng được tạo đúng | Xác minh trang xác nhận. | Kiểm tra tạo đơn, trạng thái và dữ liệu trả về. | UI gửi đơn, API đọc lại đơn theo ID để xác minh. |
| Người dùng không xem đơn của người khác | Kiểm tra trang không hiển thị dữ liệu trái phép. | Gọi trực tiếp endpoint bằng tài khoản khác và xác minh bị từ chối. | Kết hợp khi cần chứng minh cả API và UI không làm lộ dữ liệu. |

### 7.2. Ví dụ luồng kết hợp

Một kịch bản E2E có thể thực hiện:

1. API tạo tài khoản thử nghiệm và giỏ hàng có một sản phẩm.
2. UI đăng nhập bằng tài khoản đó.
3. UI mở giỏ hàng và xác minh sản phẩm cùng tổng tiền hiển thị.
4. UI chọn địa chỉ và nhấn xác nhận đặt hàng.
5. UI hiển thị trang xác nhận có mã đơn.
6. API đọc đơn hàng theo mã đó và xác minh chủ sở hữu, tổng tiền, địa chỉ và trạng thái.
7. UI tải lại trang chi tiết đơn hàng và xác minh trạng thái vẫn chính xác.

Mỗi bước trả lời một câu hỏi riêng: API setup tạo dữ liệu đầu vào; UI xác minh hành vi người dùng; API assertion xác nhận trạng thái backend; bước tải lại UI kiểm tra dữ liệu được trình bày ổn định sau khi server phản hồi.

Nếu mục tiêu chỉ là kiểm tra API tạo đơn, không cần mở trình duyệt. Nếu mục tiêu chỉ là hiển thị một trạng thái đơn hàng đã có sẵn, có thể tạo đơn bằng API rồi chỉ kiểm tra UI. Chỉ phối hợp cả hai khi yêu cầu hoặc rủi ro cần bằng chứng từ cả hai phía.

## 8. Bảo mật và tính nhất quán khi phối hợp UI/API

Kết hợp nhiều giao diện có thể tạo ra rủi ro nếu test dùng quyền quá rộng hoặc bỏ qua các kiểm soát mà người dùng thực tế phải đi qua.

### 8.1. Giữ đúng ngữ cảnh xác thực

Nếu UI dùng session cookie, CSRF token hoặc cơ chế xác thực khác API test, không nên mặc định rằng token dùng cho API có thể thay thế hoàn toàn hành trình đăng nhập. Hãy xác định mục tiêu:

- Nếu kiểm tra đăng nhập, phải thực hiện qua UI hoặc giao thức đăng nhập thuộc phạm vi.
- Nếu chỉ cần chuẩn bị dữ liệu, có thể dùng API test account hoặc fixture riêng.
- Nếu kiểm tra phân quyền, cần dùng các vai trò và danh tính khác nhau.
- Nếu kiểm tra session hết hạn, phải thực hiện điều kiện hết hạn thực tế hoặc mô phỏng có kiểm soát.

Không chia sẻ credential production trong test. Dùng tài khoản thử nghiệm với quyền tối thiểu cần thiết và quản lý bí mật qua cơ chế phù hợp.

### 8.2. Không để API setup làm mất ý nghĩa của UI test

Nếu mục tiêu là xác minh người dùng có thể tạo giỏ hàng, API tạo sẵn giỏ hàng sẽ bỏ qua hành vi đó. Có thể dùng API cho dữ liệu nền nhưng phải giữ thao tác mục tiêu trên UI.

Tương tự, nếu mục tiêu là kiểm tra luồng xác thực, không nên đăng nhập sẵn qua API rồi coi việc mở trang đã xác thực là bằng chứng đăng nhập hoạt động.

### 8.3. Xử lý tính nhất quán cuối cùng

Một số hệ thống cập nhật dữ liệu bất đồng bộ. UI có thể hiển thị trạng thái PENDING trong khi worker đang xử lý. API assertion cần hiểu mô hình trạng thái và chờ điều kiện đúng trong giới hạn thời gian.

Không nên coi độ trễ ngắn là lỗi nếu hợp đồng cho phép eventual consistency. Ngược lại, nếu trạng thái phải cập nhật đồng bộ theo yêu cầu, test cần xác minh điều đó thay vì nới thời gian chờ để che giấu lỗi.

### 8.4. Tránh phụ thuộc vào API nội bộ không ổn định

Nếu UI test gọi endpoint nội bộ chỉ dành cho test setup, hãy giới hạn quyền và ghi rõ đó là cơ chế chuẩn bị dữ liệu. Không dùng endpoint nội bộ để xác minh hành vi người dùng nếu endpoint có thể thay đổi độc lập với hợp đồng sản phẩm.

Ưu tiên API công khai hoặc giao diện kiểm thử được quản lý. Nếu cần truy cập dữ liệu nội bộ để chẩn đoán, tách nó khỏi assertion chính và không để test phụ thuộc vào chi tiết triển khai không thuộc phạm vi.

## 9. Đánh giá chất lượng và chi phí của lựa chọn

Sau khi chọn UI, API hoặc kết hợp, nhóm cần theo dõi xem cách tiếp cận có tạo bằng chứng đáng tin cậy với chi phí hợp lý không.

Các yếu tố nên xem xét:

- **Thời gian chạy:** API test thường phù hợp với nhiều biến thể; UI test nên tập trung vào hành vi quan trọng.
- **Độ ổn định:** theo dõi flaky test, timeout, selector lỗi và dữ liệu dùng chung.
- **Khả năng chẩn đoán:** test cần chỉ ra lỗi ở UI, API, xác thực, dữ liệu hay đồng bộ.
- **Mức độ đại diện:** môi trường, trình duyệt, cấu hình và dữ liệu có phản ánh rủi ro cần kiểm tra không?
- **Chi phí bảo trì:** thay đổi layout có làm hỏng nhiều test không cần thiết? Thay đổi API có làm setup test phức tạp?
- **Giá trị bằng chứng:** mỗi assertion có xác minh thêm một hành vi hoặc ranh giới quan trọng không?
- **Khả năng tái lập:** test có thể chạy độc lập, có dữ liệu riêng và có cleanup rõ ràng không?

Không nên tối ưu chỉ theo tốc độ. Một UI test chậm nhưng là bằng chứng duy nhất cho luồng thanh toán quan trọng có thể cần giữ. Ngược lại, hàng trăm UI test kiểm tra lại cùng quy tắc backend có thể chuyển phần lớn biến thể sang API test.

## 10. Mẫu quyết định và ghi nhận phạm vi kiểm thử

Có thể dùng mẫu sau khi lập kế hoạch cho một hành trình hệ thống:

~~~text
Tên tính năng / hành trình:
Phiên bản / môi trường:
Mục tiêu và rủi ro:

Mục tiêu cần kiểm chứng:
- Hành vi người dùng:
- Quy tắc backend:
- Trạng thái dữ liệu:
- Hợp đồng API:
- Khả năng truy cập / nền tảng:

Lựa chọn kiểm thử:
- UI test:
- API test:
- Kết hợp UI + API:

Điểm bắt đầu và kết thúc:
Dữ liệu và tài khoản thử nghiệm:
Cấu hình / feature flag:
Phụ thuộc và trạng thái bất đồng bộ:

Assertion UI:
Assertion API:
Điều kiện chờ và timeout:
Cách dọn dữ liệu:
Bằng chứng lưu lại:

Giới hạn và giả định:
Người phụ trách:
Tiêu chí hoàn tất:
~~~

Với mỗi test kết hợp, nên ghi rõ hành động nào thực hiện qua UI, dữ liệu nào được tạo qua API và API nào dùng để xác minh. Điều đó giúp người bảo trì hiểu test đang chứng minh điều gì và tránh vô tình bỏ qua hành vi cần kiểm tra.

## 11. Những sai lầm thường gặp

- **Chỉ dùng UI để kiểm tra mọi quy tắc backend:** làm test chậm và khó bao phủ nhiều tổ hợp dữ liệu.
- **Chỉ dùng API để kết luận trải nghiệm người dùng đúng:** bỏ sót lỗi hiển thị, điều hướng, tương tác và khả năng truy cập.
- **Phối hợp UI/API nhưng không phân biệt mục tiêu:** tạo thêm assertion trùng mà không tăng bằng chứng.
- **Chuẩn bị qua API một hành vi đáng lẽ phải kiểm tra qua UI:** khiến test bỏ qua chính hành động đang cần xác minh.
- **Dùng API xác minh nội bộ quá sâu:** làm test gắn chặt vào triển khai và dễ hỏng khi thay đổi kiến trúc.
- **Dùng tài khoản có quyền quá rộng:** có thể che giấu lỗi phân quyền và tạo rủi ro cho môi trường.
- **Chờ bằng thời gian cố định:** khiến test chậm hoặc flaky; nên chờ điều kiện có ý nghĩa.
- **Không xử lý eventual consistency:** có thể báo lỗi giả hoặc che giấu lỗi đồng bộ thực sự.
- **Không dọn dữ liệu:** làm các lần chạy ảnh hưởng lẫn nhau.
- **Lưu log hoặc screenshot có dữ liệu nhạy cảm:** có thể làm lộ thông tin người dùng hoặc token.

## 12. Danh sách rà soát trước khi chốt chiến lược UI/API

- [ ] Mục tiêu kiểm thử được viết thành hành vi hoặc kết quả cụ thể.
- [ ] Nhóm xác định phần nào cần bằng chứng từ trải nghiệm UI.
- [ ] Nhóm xác định phần nào cần bằng chứng từ API hoặc dữ liệu backend.
- [ ] UI test tập trung vào thao tác, hiển thị, điều hướng và nền tảng có rủi ro.
- [ ] API test tập trung vào quy tắc nghiệp vụ, hợp đồng, dữ liệu và bảo mật.
- [ ] Test kết hợp có vai trò riêng cho UI và API, không chỉ lặp assertion.
- [ ] API setup không bỏ qua hành vi nằm trong mục tiêu UI.
- [ ] Xác thực và phân quyền dùng đúng ngữ cảnh và vai trò thử nghiệm.
- [ ] Điều kiện chờ xử lý được trạng thái bất đồng bộ và eventual consistency.
- [ ] Dữ liệu, tài khoản, cấu hình và cleanup có thể tái lập.
- [ ] Test có log và bằng chứng chẩn đoán mà không lộ dữ liệu nhạy cảm.
- [ ] Mỗi test có người sở hữu và lý do duy trì gắn với rủi ro.

## Kết luận

Chọn UI, API hay phối hợp cả hai dựa trên điều cần chứng minh. UI test xác minh người dùng có thể thao tác và nhận kết quả phù hợp; API test xác minh backend thực thi hợp đồng, quy tắc và dữ liệu; kiểm thử kết hợp chứng minh hành động qua một giao diện được phản ánh chính xác ở giao diện còn lại. Khi mỗi tầng có mục tiêu riêng, dữ liệu được kiểm soát và bằng chứng gắn với rủi ro, kiểm thử hệ thống và E2E sẽ có giá trị cao mà vẫn giữ được tốc độ và khả năng bảo trì.
