# Dangerous operation

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Nhận diện thao tác ứng dụng cần kiểm soát đặc quyền theo hậu quả thực tế.
- Phân biệt quyền truy cập ứng dụng với quyền thực hiện một thao tác nguy hiểm cụ thể.
- Thiết kế quy trình yêu cầu, phê duyệt, cấp quyền tạm thời, thực thi và xác minh.
- Xử lý thay đổi dữ liệu sau phê duyệt, thao tác hàng loạt, lỗi một phần và yêu cầu bị gửi lại.
- Thu thập bằng chứng đủ để quy trách nhiệm mà không làm lộ credential hoặc dữ liệu nhạy cảm.

## 1. Dangerous operation là gì?

Trong bài học này, **dangerous operation** là thao tác có khả năng gây hậu quả nghiêm trọng nếu người thực hiện chọn sai đối tượng, nhập sai tham số, bị chiếm tài khoản hoặc lạm dụng quyền. Mức nguy hiểm phụ thuộc vào tác động, phạm vi và khả năng phục hồi; không phụ thuộc riêng vào tên nút bấm hay tên vai trò.

Ví dụ trong ứng dụng:

- Xóa hàng loạt dữ liệu hoặc xóa bản sao lưu cần cho khôi phục.
- Xuất dữ liệu khách hàng trên diện rộng.
- Cấp quyền quản trị, thay chủ sở hữu hoặc thay cấu hình xác thực.
- Vô hiệu hóa nhật ký, cảnh báo hoặc cơ chế kiểm soát.
- Đổi đích nhận tiền, hoàn tiền hàng loạt hoặc thay hạn mức giao dịch.
- Thay credential của một tích hợp quan trọng.
- Thay chính sách khiến nhiều tài khoản dịch vụ có thêm quyền.

Không phải mọi thao tác trên đều có cùng mức rủi ro trong mọi hệ thống. Xuất một bản ghi giả lập trong môi trường học khác với xuất toàn bộ dữ liệu thật. Xóa một đối tượng có thể khôi phục trong thời hạn rõ ràng khác với hủy khóa khiến dữ liệu mất khả năng giải mã.

Trong PAM, mục tiêu là giới hạn **ai được làm việc gì, trên đối tượng nào, trong điều kiện nào, trong bao lâu và với bằng chứng gì**. Quản lý mật khẩu quản trị chỉ là một phần. Một credential được bảo vệ tốt vẫn có thể bị dùng để thực hiện thao tác sai nếu ứng dụng thiếu kiểm soát ở mức hành động.

## 2. Quyền đăng nhập không đồng nghĩa quyền thực hiện mọi hành động

Ứng dụng thường có nhiều lớp kiểm soát:

| Lớp | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Xác thực | Ai đang gửi yêu cầu? | Nhân viên vận hành đã đăng nhập |
| Quyền ứng dụng | Người đó có loại quyền nào? | Được quản lý cấu hình vận hành |
| Quyền đối tượng | Quyền áp dụng cho tài nguyên nào? | Chỉ tenant và môi trường được giao |
| Quyền thao tác | Được thực hiện hành động nào? | Được thay ngưỡng cảnh báo nhưng không được tắt audit |
| Điều kiện thực hiện | Hành động được phép trong hoàn cảnh nào? | Có phê duyệt còn hiệu lực và cửa sổ thay đổi phù hợp |

Nút bị ẩn trên giao diện không phải là cơ chế phân quyền đầy đủ. Backend phải kiểm tra yêu cầu thực tế. Người gọi có thể gửi API trực tiếp, dùng phiên bản giao diện cũ hoặc gọi một luồng tích hợp khác.

Tương tự, có quyền đọc một nhóm đối tượng không tự động có quyền xuất cả nhóm. Quyền chỉnh sửa một bản ghi không tự động bao gồm quyền cập nhật hàng loạt. Quyền tạo tài khoản không nên mặc nhiên bao gồm quyền tạo tài khoản có đặc quyền ngang hoặc cao hơn người tạo.

Một quy tắc hữu ích là tách **quyền thông thường** khỏi **quyền thực hiện thao tác hậu quả cao**. Quyền thứ hai có phạm vi hẹp, thời hạn rõ ràng và điều kiện bổ sung phù hợp.

## 3. Đánh giá rủi ro theo hậu quả

### 3.1. Các chiều cần đánh giá

Với mỗi thao tác, xác định:

1. **Tính nhạy cảm:** liên quan credential, dữ liệu cá nhân, tài chính, quyền quản trị hay bằng chứng điều tra?
2. **Phạm vi ảnh hưởng:** một bản ghi, một dịch vụ, một tenant hay toàn bộ nền tảng?
3. **Khả năng phục hồi:** có undo thực sự không, mất bao lâu và phụ thuộc vào điều kiện nào?
4. **Tốc độ gây hậu quả:** có thể kiểm tra từng phần hay tác động xảy ra ngay?
5. **Khả năng khuếch đại:** quyền mới có thể được dùng để tạo thêm đặc quyền không?
6. **Khả năng phát hiện:** audit và cảnh báo có còn đáng tin cậy sau thao tác không?
7. **Tác động bên ngoài:** tiền, thông báo, dữ liệu hoặc quyền đã chuyển sang bên thứ ba có thể thu hồi không?

Không nên gán nhãn nguy hiểm chỉ theo tên endpoint. Một endpoint cập nhật cấu hình thông thường có thể trở thành đường nâng quyền nếu cho phép đổi địa chỉ nhà cung cấp danh tính hoặc thay danh sách người phê duyệt.

### 3.2. Phân tầng biện pháp kiểm soát

Bảng sau là ví dụ thiết kế, không phải chuẩn phân loại bắt buộc:

| Nhóm thao tác | Điều kiện minh họa |
|---|---|
| Tác động nhỏ, dễ phục hồi | Quyền thường trực có giới hạn, xác minh đầu vào, audit |
| Thay đổi nhạy cảm trong phạm vi hẹp | Xác thực bổ sung theo rủi ro, quyền tạm thời, lý do thay đổi |
| Tác động lớn hoặc hàng loạt | Kế hoạch cụ thể, phê duyệt độc lập, giới hạn số lượng, triển khai theo đợt |
| Khó đảo ngược hoặc làm suy yếu kiểm soát | Kiểm tra chặt hơn, phân tách trách nhiệm, bằng chứng được bảo vệ độc lập; có thể cấm trong vận hành thông thường |

Không giải quyết mọi rủi ro bằng một hộp thoại “Bạn có chắc không?”. Hộp thoại giúp giảm nhầm lẫn nhưng không thay thế phân quyền, kiểm tra phía máy chủ hoặc phê duyệt độc lập.

## 4. Kiểm kê thao tác nguy hiểm trong ứng dụng

Một danh mục hữu ích nên gắn hành động với đối tượng và hậu quả:

| Trường | Nội dung cần ghi |
|---|---|
| Định danh hành động | Tên ổn định dùng trong chính sách và audit |
| Chủ sở hữu | Đội chịu trách nhiệm nghiệp vụ và đội vận hành |
| Đối tượng | Loại tài nguyên, tenant, môi trường và phạm vi hợp lệ |
| Tham số quan trọng | Số lượng, hạn mức, thời điểm hiệu lực, đích nhận hoặc loại quyền |
| Hậu quả | Mất dữ liệu, lộ dữ liệu, ngừng dịch vụ hoặc tăng đặc quyền |
| Điều kiện đầu vào | Trạng thái dữ liệu, yêu cầu thay đổi, phê duyệt và xác thực |
| Cách thực thi | API, tác vụ nền, công cụ hỗ trợ hoặc tài khoản dịch vụ |
| Cách xác minh | Trạng thái cuối, kết quả từng đối tượng và kiểm tra độc lập |
| Phục hồi | Điều kiện thực tế để rollback hoặc bù trừ |
| Bằng chứng | Sự kiện nào cần lưu và nơi bảo vệ bằng chứng |

Cần khảo sát cả giao diện, API, tác vụ theo lịch, tích hợp và công cụ hỗ trợ. Nếu kiểm soát chỉ áp dụng cho cổng quản trị, tài khoản dịch vụ có quyền rộng có thể trở thành đường thực hiện cùng hành động mà thiếu kiểm tra.

Danh mục phải bao gồm cả thao tác **thay đổi chính cơ chế kiểm soát**: sửa chính sách phê duyệt, đổi người phê duyệt, cấp quyền cho executor, thay thời hạn lưu audit hoặc sửa hạn mức thực thi.

## 5. Tách các vai trò trong một thao tác

Một luồng thao tác nhạy cảm có thể cần các vai trò sau:

- **Người yêu cầu:** nêu nhu cầu, đối tượng và phạm vi.
- **Người phê duyệt:** đánh giá kế hoạch cụ thể, quyền hạn và hậu quả.
- **Thành phần quyết định quyền:** kiểm tra danh tính, chính sách và điều kiện hiện tại.
- **Executor:** thực hiện đúng hành động được cho phép.
- **Người hoặc hệ thống xác minh:** kiểm tra kết quả và phát hiện sai lệch.
- **Bộ phận quản lý bằng chứng:** bảo vệ audit theo thiết kế của tổ chức.

Không nhất thiết mọi hành động đều cần sáu người hoặc sáu hệ thống khác nhau. Mức phân tách phụ thuộc rủi ro. Tuy nhiên, với thao tác hậu quả cao, một người không nên có thể tự yêu cầu, tự phê duyệt, thực hiện và xóa bằng chứng mà không có kiểm soát độc lập.

Tách hai tài khoản thuộc cùng một người chưa đủ để tạo phê duyệt độc lập. Cần kiểm tra quan hệ danh tính và các quy tắc phân tách trách nhiệm thực tế.

Quyền sửa quy trình phê duyệt cũng phải được kiểm soát. Nếu người vận hành có thể thêm một tài khoản của mình vào nhóm phê duyệt rồi tự duyệt, quy tắc “không tự phê duyệt” chỉ còn hình thức.

## 6. Thiết kế một yêu cầu có thể phê duyệt

### 6.1. Phê duyệt một kế hoạch cụ thể

Yêu cầu “cho quyền admin trong một giờ” thường quá rộng nếu mục tiêu chỉ là xóa một nhóm đối tượng đã xác định.

Một kế hoạch thao tác nên bao gồm:

- ID yêu cầu và người yêu cầu.
- Hành động được phép.
- Tenant, môi trường và danh sách đối tượng.
- Tham số ảnh hưởng đến hậu quả.
- Phiên bản hoặc điều kiện trạng thái của đối tượng.
- Giới hạn số lượng, giá trị hoặc tốc độ.
- Cửa sổ thực hiện và thời điểm hết hạn.
- Lý do và tham chiếu công việc liên quan.
- Bằng chứng kiểm tra trước thay đổi.
- Điều kiện dừng và phương án xử lý lỗi.
- Danh tính hoặc nhóm executor được phép.

Không để một trường mô tả tự do thay thế các ràng buộc máy có thể kiểm tra. “Chỉ chạy trên dữ liệu thử nghiệm” trong ghi chú không đủ nếu API vẫn chấp nhận môi trường sản xuất.

### 6.2. Bản xem trước phải phản ánh phạm vi thực

Với hành động hàng loạt, bản xem trước nên hiển thị số lượng, phạm vi, đối tượng loại trừ và hậu quả đáng chú ý. Cần tránh chỉ hiển thị một bộ lọc quá mơ hồ.

Ví dụ, yêu cầu xóa “mọi job cũ hơn 90 ngày” có thể chọn một tập đối tượng khác ở thời điểm thực hiện. Có hai hướng thiết kế phổ biến:

- Chốt danh sách đối tượng tại lúc lập kế hoạch và chỉ thực hiện trên danh sách đó.
- Phê duyệt một tiêu chí động với giới hạn và điều kiện được mô tả rõ; đánh giá lại ngay trước thực hiện và yêu cầu duyệt lại khi vượt phạm vi.

Với thao tác khó đảo ngược, chốt danh sách thường giúp người phê duyệt hiểu rõ điều mình cho phép. Dù chọn cách nào, hệ thống không được âm thầm mở rộng phạm vi sau phê duyệt.

### 6.3. Bảo vệ tính toàn vẹn của kế hoạch

Có thể lưu kế hoạch bất biến theo phiên bản và gắn phê duyệt với phiên bản đó. Một digest có thể giúp phát hiện nội dung thay đổi nếu hệ thống chuẩn hóa dữ liệu nhất quán và bảo vệ bản ghi tham chiếu.

Digest không tự tạo ra quyền thực hiện, không thay thế xác thực người phê duyệt và không ngăn người có quyền sửa cả kế hoạch lẫn bản ghi phê duyệt. Thiết kế phải bảo vệ đầy đủ nơi lưu, quyền ghi và cơ chế xác minh.

Không đưa secret vào kế hoạch. Thay vì ghi mật khẩu mới, dùng tham chiếu credential hoặc ID phiên bản phù hợp.

## 7. Quy trình tham chiếu từ yêu cầu đến kết thúc

### Bước 1: Tạo và kiểm tra yêu cầu

Kiểm tra người yêu cầu có quyền đề xuất hành động trên phạm vi đã chọn. Chuẩn hóa định danh tài nguyên, môi trường và tham số. Từ chối giá trị mơ hồ hoặc phạm vi vượt chính sách.

Đánh giá hậu quả và xác định loại kiểm soát cần áp dụng. Không để người yêu cầu tự khai mức rủi ro thấp rồi được bỏ qua kiểm tra.

### Bước 2: Tạo kế hoạch và bản xem trước

Đọc trạng thái cần thiết, lập danh sách đối tượng và tính các giới hạn. Nêu rõ phần có thể phục hồi, phần không thể phục hồi và điều kiện chưa xác minh.

Dry run chỉ phản ánh những gì công cụ thực sự kiểm tra. Nếu dry run chỉ đếm bản ghi, nó chưa chứng minh các bản ghi đều có thể xóa, phục hồi hoặc xử lý an toàn.

### Bước 3: Phê duyệt đúng phiên bản

Người phê duyệt phải có thẩm quyền trên hành động và phạm vi cụ thể. Kiểm tra tính độc lập, hiệu lực của phê duyệt và số phê duyệt cần thiết theo chính sách.

Nếu đổi danh sách đối tượng, môi trường, tham số quan trọng hoặc giới hạn sau khi duyệt, phải đánh giá lại và lấy phê duyệt mới theo thiết kế. Không giữ phê duyệt cũ cho một kế hoạch khác.

### Bước 4: Cấp khả năng thực thi có thời hạn

Cấp quyền tạm thời hoặc một khả năng thực thi giới hạn vào yêu cầu cụ thể. Ràng buộc nó với danh tính gọi, executor, hành động, tài nguyên, thời hạn và giới hạn sử dụng.

Một vé yêu cầu hoặc mã ticket không phải credential. Chỉ biết mã yêu cầu không được phép thực hiện hành động. Nếu dùng token cho executor, cần bảo vệ token, xác minh nơi phát hành và đối tượng nhận, đồng thời hạn chế khả năng phát lại theo cơ chế thực tế.

### Bước 5: Kiểm tra lại ngay trước thực hiện

Backend kiểm tra:

1. Yêu cầu và phê duyệt vẫn còn hiệu lực.
2. Người gọi và executor vẫn có thẩm quyền cần thiết.
3. Kế hoạch đúng phiên bản đã phê duyệt.
4. Đối tượng vẫn ở trạng thái được cho phép.
5. Cửa sổ thực hiện và các giới hạn vẫn được đáp ứng.
6. Không có lệnh hủy hoặc thu hồi đã có hiệu lực.
7. Có cơ chế audit và khả năng quan sát cần thiết theo chính sách.

Thời điểm quyết định quyền có thể cách thời điểm thay đổi dữ liệu. Với dữ liệu có thể thay đổi đồng thời, cần đưa điều kiện quan trọng vào thao tác ghi có điều kiện, giao dịch hoặc cơ chế phối hợp phù hợp. Kiểm tra sớm rồi ghi mù quáng không ngăn được thay đổi ở giữa.

### Bước 6: Thực hiện có giới hạn

Thực hiện trên đúng tập đối tượng và tham số đã được cho phép. Nếu chia đợt, kiểm tra điểm dừng và theo dõi kết quả từng đợt.

Không cho executor biến kế hoạch thành lệnh quản trị tùy ý. Đầu vào như “chạy chuỗi lệnh này” khó kiểm soát hơn một hành động có schema rõ ràng với danh sách tham số được phép.

### Bước 7: Xác minh kết quả

Phân biệt:

- Yêu cầu đã được tiếp nhận.
- Tác vụ đã bắt đầu.
- Thay đổi đã được áp dụng.
- Kết quả cuối đã được xác minh.

Mã phản hồi thành công từ endpoint tạo tác vụ không chứng minh tác vụ nền đã hoàn tất. Cần kiểm tra trạng thái thực tế và hậu quả liên quan.

### Bước 8: Đóng quyền và hồ sơ

Hết thời hạn hoặc hoàn tất thì thu hồi khả năng thực thi theo thiết kế. Lưu kết quả, ngoại lệ và bằng chứng xác minh. Không đóng hồ sơ nếu còn đối tượng chưa rõ kết quả hoặc quyền tạm thời chưa được xử lý.

## 8. Trạng thái quy trình và xử lý đồng thời

Một mô hình trạng thái minh họa:

~~~text
DRAFT
  → PLANNED
  → PENDING_APPROVAL
  → APPROVED
  → EXECUTING
  → VERIFYING
  → COMPLETED

Nhánh có thể có:
REJECTED / EXPIRED / CANCELLED
FAILED / PARTIAL / NEEDS_RECONCILIATION
~~~

Các trạng thái là ví dụ nội bộ, không phải thuật ngữ bắt buộc của sản phẩm.

### 8.1. Hủy trước thực hiện khác với dừng giữa chừng

Một yêu cầu bị hủy trước khi bắt đầu nên không thể được executor nhận nữa. Việc nhận yêu cầu và chuyển sang EXECUTING cần có cơ chế ngăn hai executor cùng nhận công việc theo thiết kế.

Khi đã thực hiện một phần, hủy không làm những thay đổi trước đó tự biến mất. Có thể chỉ ngăn các đợt tiếp theo. Giao diện và audit phải phản ánh số đối tượng đã xử lý, chưa xử lý và chưa rõ kết quả.

### 8.2. Kiểm tra phiên bản để ngăn sai lệch

Giả sử kế hoạch được duyệt khi bản ghi có phiên bản 12. Trước khi executor chạy, một tiến trình khác cập nhật bản ghi lên phiên bản 13.

Nếu thay đổi liên quan đến điều kiện an toàn, executor phải dừng hoặc lập kế hoạch lại. Một thao tác ghi có điều kiện có thể yêu cầu “chỉ cập nhật nếu phiên bản vẫn là 12”. Cơ chế cụ thể tùy nơi lưu trữ và kiến trúc.

Chỉ khóa trên giao diện không đủ, vì API khác hoặc tiến trình nền có thể sửa cùng dữ liệu.

### 8.3. Thu hồi trong lúc đang chạy

Quyền hết hạn hoặc phê duyệt bị thu hồi có thể ảnh hưởng khác nhau:

- Chưa bắt đầu: từ chối nhận công việc.
- Giữa các đợt: dừng trước đợt tiếp theo.
- Đang thực hiện một thao tác không thể ngắt: ghi nhận yêu cầu dừng, xác minh kết quả rồi xử lý tiếp theo runbook.

Không hứa “thu hồi là dừng tức thì” nếu hệ thống đích không hỗ trợ. Cần xác định điểm kiểm tra quyền, độ trễ và hậu quả trong khoảng chuyển tiếp.

## 9. Retry, idempotency và kết quả không rõ

Một timeout có thể xảy ra sau khi thay đổi đã thành công nhưng trước khi phản hồi quay lại. Nếu client gửi lại ngay, hành động có thể bị thực hiện lần thứ hai.

Với hoàn tiền, gửi thông báo hoặc xuất dữ liệu, thực hiện hai lần có thể tạo hậu quả mới. Với xóa, lần thứ hai có thể gặp trạng thái khác hoặc chạm vào đối tượng đã được tái tạo nếu định danh bị dùng lại.

### 9.1. Thiết kế yêu cầu có định danh ổn định

Một idempotency key có thể giúp liên kết các lần gửi lại với cùng một thao tác nếu backend lưu và thực thi quy tắc đầy đủ.

Cần ràng buộc key với người gọi hoặc miền phù hợp, kế hoạch và tham số đã chuẩn hóa. Nếu cùng key nhưng tham số khác, phải từ chối hoặc xử lý như xung đột theo thiết kế.

Key không thay thế phân quyền. Người không được phép vẫn phải bị từ chối dù biết một key đã tồn tại.

### 9.2. Giới hạn của bảo đảm một lần

Một bản ghi chống lặp trong ứng dụng không tự bảo đảm hệ thống bên ngoài chỉ thực hiện một lần. Nếu ứng dụng cập nhật cơ sở dữ liệu rồi gọi một dịch vụ khác, có thể xảy ra lỗi giữa hai bên.

Cần biết hệ thống đích hỗ trợ chống lặp, truy vấn kết quả hoặc đối soát theo mã giao dịch ra sao. Khi chưa rõ kết quả, chuyển sang trạng thái cần đối soát; không coi timeout là thất bại chắc chắn và không đánh dấu thành công bằng suy đoán.

### 9.3. Thao tác hàng loạt cần kết quả theo đối tượng

Nếu một đợt gồm 100 đối tượng và 80 đối tượng thành công, lần tiếp theo cần biết chính xác 20 đối tượng còn lại. Không chạy lại cả đợt mà bỏ qua khả năng gây tác dụng phụ.

Bản ghi kết quả nên phân biệt thành công, thất bại chắc chắn, chưa thực hiện và chưa xác định. Các trạng thái này dẫn tới hành động phục hồi khác nhau.

## 10. Danh tính thực thi và tài khoản dịch vụ

Nhiều ứng dụng thực hiện thao tác nhạy cảm bằng tài khoản dịch vụ thay cho người dùng. Khi đó, PAM cần kiểm soát cả hai lớp:

- Ai đã yêu cầu và được phê duyệt thực hiện hành động.
- Tài khoản dịch vụ nào đã thực hiện thay đổi tại hệ thống đích.

Executor không nên mặc nhiên có quyền quản trị toàn bộ tài nguyên. Giới hạn quyền vào nhóm hành động và môi trường cần thiết; tách executor khi khác biệt rủi ro hoặc phạm vi có ý nghĩa.

Credential của executor cần được quản lý theo vòng đời: owner, nơi lưu, cách cấp, thời hạn, luân chuyển và thu hồi. Dùng danh tính workload hoặc credential ngắn hạn khi kiến trúc hỗ trợ có thể giảm việc phân phối secret dài hạn, nhưng không thay thế kiểm tra quyền ở mức thao tác.

### Nguy cơ làm hộ ngoài thẩm quyền

Một backend mạnh có thể bị lợi dụng như sau:

1. Người dùng chỉ có quyền trên tenant A.
2. Người dùng gửi ID đối tượng thuộc tenant B.
3. Backend dùng tài khoản dịch vụ có quyền toàn cục để thực hiện.
4. Hệ thống đích chấp nhận vì tài khoản dịch vụ có quyền.

Để tránh tình huống này, backend phải kiểm tra mối liên hệ giữa người gọi, hành động và đối tượng. Không chỉ kiểm tra “đã đăng nhập” hoặc “ID đối tượng tồn tại”.

Audit nên liên kết người khởi tạo với executor. Tuy nhiên, trường người khởi tạo do client tự khai không phải bằng chứng danh tính đáng tin cậy. Backend phải lấy danh tính từ ngữ cảnh xác thực đã kiểm chứng.

## 11. Ví dụ: xóa dữ liệu vận hành đã hết hạn

Một ứng dụng cho phép đội vận hành xóa bản ghi chẩn đoán cũ của một tenant. Một số bản ghi đang được giữ để phục vụ điều tra, nên không được xóa theo luồng thông thường.

### 11.1. Thiết kế ban đầu có rủi ro

Người có vai trò operator gửi bộ lọc “cũ hơn 90 ngày”. Backend dùng tài khoản dịch vụ rộng quyền và xóa mọi bản ghi khớp bộ lọc.

Những điểm yếu:

- Vai trò operator không giới hạn rõ tenant.
- Không kiểm tra trạng thái giữ lại phục vụ điều tra.
- Tập dữ liệu có thể thay đổi từ lúc xem trước đến lúc chạy.
- Không có giới hạn số lượng hoặc cơ chế dừng theo đợt.
- Retry sau timeout có thể tạo kết quả khó giải thích.
- Audit chỉ ghi “delete success” mà không nêu phạm vi.

### 11.2. Kế hoạch được kiểm soát

Một kế hoạch minh họa, không chứa dữ liệu bí mật:

~~~json
{
  "requestId": "req-example-042",
  "action": "diagnostic-record.delete",
  "environment": "production",
  "tenantId": "tenant-example-a",
  "planVersion": 3,
  "objectSetRef": "object-set-example-09",
  "maxObjects": 120,
  "batchSize": 20,
  "requiredState": {
    "retentionExpired": true,
    "investigationHold": false
  },
  "executionWindow": "approved-change-window",
  "executorClass": "diagnostic-retention-worker"
}
~~~

Các tên trường và giá trị chỉ minh họa mô hình dữ liệu. Bản tham chiếu tập đối tượng phải trỏ tới dữ liệu được bảo vệ; không cho người yêu cầu sửa nội dung phía sau tham chiếu sau phê duyệt.

Người phê duyệt xem danh sách và số lượng. Executor kiểm tra lại điều kiện giữ lại trước từng thay đổi. Nếu một đối tượng được đặt vào trạng thái giữ lại sau phê duyệt, executor không được xóa đối tượng đó chỉ vì nó từng nằm trong kế hoạch.

### 11.3. Thực thi và đối soát

Giả sử ba đợt đầu thành công, đợt thứ tư bị timeout.

Executor cần:

1. Dừng mở rộng khi chưa rõ kết quả.
2. Truy vấn hoặc đối soát các đối tượng trong đợt thứ tư.
3. Ghi trạng thái từng đối tượng.
4. Chỉ tiếp tục trên đối tượng còn hợp lệ và thuộc kế hoạch.
5. Yêu cầu đánh giá lại nếu cửa sổ thực hiện đã hết hoặc điều kiện thay đổi.

Không khôi phục bằng cách lấy dữ liệu từ một nguồn không được phép. Nếu đã xóa dữ liệu thật, phương án phục hồi phụ thuộc vào khả năng lưu trữ và chính sách thực tế đã được kiểm tra trước.

### 11.4. Báo cáo kết quả phù hợp

> Kế hoạch phiên bản 3 có 120 đối tượng. Đã xác minh xóa 116 đối tượng. Hai đối tượng được giữ lại do trạng thái điều tra thay đổi, hai đối tượng chưa thực hiện vì hết cửa sổ cho phép. Quyền thực thi đã đóng. Hồ sơ còn mở để xử lý bốn đối tượng theo quyết định tiếp theo.

Báo cáo này phản ánh kết quả cụ thể hơn một thông báo “tác vụ thành công”.

## 12. Mã giả cho luồng thực thi

Đoạn sau mô tả trách nhiệm của backend; không phải API hay script có thể chạy trực tiếp:

~~~text
execute_sensitive_operation(authenticated_context, request_id):
    request = load_request(request_id)
    plan = load_protected_plan(request.plan_version)

    authorize_actor(authenticated_context, plan.action, plan.scope)
    verify_independent_approvals(request, plan)
    verify_window_and_revocation(request)

    execution = claim_execution_conditionally(request, plan.version)
    if execution.already_exists:
        return authorized_execution_status(execution)

    for batch in plan.object_batches:
        verify_request_still_executable(request)
        verify_batch_is_within_approved_set(batch, plan)
        verify_remaining_limits(execution, batch)

        for object in batch:
            observed = load_current_state(object)

            if preconditions_changed(observed, plan):
                record_skipped_or_blocked(object, observed.version)
                continue

            result = apply_conditionally(
                object_id=object.id,
                expected_version=observed.version,
                action=plan.action,
                approved_parameters=plan.parameters
            )

            record_result_without_sensitive_values(result)

        reconcile_uncertain_results_before_next_batch(execution)

    verify_final_state(execution)
    close_temporary_execution_authority(request)
    persist_final_outcome(execution)
~~~

Mã giả lược bỏ các nhánh lỗi để làm rõ luồng chính. Hệ thống thực tế phải xử lý lỗi lúc claim, ghi audit, gọi hệ thống đích, đóng quyền và lưu trạng thái.

Nếu nơi thực hiện thay đổi không hỗ trợ điều kiện phiên bản, cần cơ chế khác phù hợp để kiểm soát cạnh tranh và xác minh. Không giả định chỉ thêm một khóa trong ứng dụng là mọi thành phần khác cũng tuân thủ khóa đó.

## 13. Bằng chứng kiểm toán và giám sát

### 13.1. Những gì cần liên kết

Một chuỗi bằng chứng hữu ích liên kết được:

| Nhóm bằng chứng | Nội dung |
|---|---|
| Yêu cầu | Người yêu cầu, lý do, hành động và phạm vi |
| Kế hoạch | Phiên bản, tập đối tượng, tham số và giới hạn |
| Phê duyệt | Danh tính, thẩm quyền, thời điểm và phiên bản được duyệt |
| Quyết định quyền | Kết quả kiểm tra và phiên bản chính sách liên quan |
| Thực thi | Executor, thời điểm, lần thử và mã liên kết |
| Kết quả | Thành công, thất bại, bỏ qua hoặc chưa rõ theo đối tượng |
| Xác minh | Trạng thái cuối, người hoặc hệ thống kiểm tra |
| Đóng quyền | Thu hồi, hết hạn và ngoại lệ còn mở |

Không cần sao chép toàn bộ dữ liệu trước và sau vào log. Với dữ liệu nhạy cảm, ghi đủ metadata và tham chiếu được bảo vệ. Secret, access token, khóa riêng hoặc credential mới không được trở thành nội dung audit thông thường.

### 13.2. Bảo vệ bằng chứng khỏi chính người thao tác

Nếu executor có thể xóa toàn bộ dấu vết của mình, audit khó phục vụ quy trách nhiệm. Cần phân quyền nơi lưu, bảo vệ đường truyền và có cơ chế phát hiện thiếu sự kiện phù hợp.

Chỉ gắn nhãn “bất biến” cho log không tự bảo đảm tính toàn vẹn. Cần hiểu quyền quản trị, thời hạn lưu, khả năng thay đổi cấu hình và cách xác minh bằng chứng trong triển khai thực tế.

Nếu cơ chế audit không khả dụng, hành vi của thao tác phải theo chính sách đã thiết kế. Với thao tác khó đảo ngược, có thể cần chặn hoặc dùng một luồng khẩn cấp riêng có bằng chứng thay thế được bảo vệ. Không để executor tự bỏ qua audit mà không có quyền và dấu vết.

### 13.3. Cảnh báo có thể hành động

Ví dụ cảnh báo hữu ích:

- Có yêu cầu vượt hạn mức hoặc khác môi trường được phép.
- Một người liên tục bị từ chối trên nhiều tenant.
- Có thay đổi nhóm phê duyệt ngay trước một thao tác hậu quả cao.
- Executor chạy ngoài cửa sổ hoặc sau khi yêu cầu bị thu hồi.
- Có kết quả chưa đối soát quá thời hạn.
- Quyền tạm thời chưa đóng sau khi công việc kết thúc.
- Có yêu cầu tắt audit hoặc giảm khả năng phục hồi.
- Thao tác được thực hiện qua một đường gọi không gắn với yêu cầu hợp lệ.

Cảnh báo cần có chủ sở hữu và bước xử lý tiếp theo. Chỉ tăng số lượng log mà không có người nhận trách nhiệm không tạo ra kiểm soát đầy đủ.

## 14. Lối khẩn cấp và giới hạn phục hồi

Một tình huống sự cố có thể cần hành động nhanh hơn quy trình thông thường. Luồng break-glass nên được thiết kế trước, giới hạn đối tượng, người sử dụng, thời hạn và bằng chứng.

Cần xác định:

- Điều kiện nào cho phép kích hoạt.
- Ai được kích hoạt và ai nhận thông báo.
- Kiểm soát nào được thay thế bằng cơ chế khẩn cấp cụ thể.
- Cách ghi bằng chứng khi một thành phần bình thường đang lỗi.
- Cách đóng quyền, luân chuyển credential nếu cần và rà soát sau sự kiện.

Khẩn cấp không có nghĩa credential được chia sẻ vô thời hạn hoặc mọi hành động đều được phép. Các giới hạn còn áp dụng phải được diễn đạt và thực thi rõ ràng.

### Rollback không phải lúc nào cũng đảo ngược hậu quả

Một thay đổi cấu hình có thể được hoàn nguyên nhưng trong thời gian cấu hình sai, dữ liệu đã bị xuất hoặc tiền đã chuyển đi. Xóa quyền mới không tự thu hồi bản sao dữ liệu người dùng đã tải xuống.

Vì vậy, kế hoạch phục hồi cần phân biệt:

- Hoàn nguyên trạng thái kỹ thuật.
- Xử lý hậu quả nghiệp vụ.
- Chấm dứt truy cập hoặc credential đã phát sinh.
- Đối soát những gì không thể đảo ngược.

Không phê duyệt thao tác dựa trên một lời hứa rollback chưa được kiểm tra.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng sửa |
|---|---|---|
| Chỉ ẩn nút trên giao diện | API vẫn thực hiện được | Kiểm tra phía máy chủ tại mọi đường gọi |
| Dùng vai trò admin cho mọi thao tác | Quyền rộng và khó quy trách nhiệm | Tách hành động, đối tượng và điều kiện |
| Phê duyệt một ticket chung | Phạm vi thực thi có thể bị thay đổi | Gắn phê duyệt với kế hoạch cụ thể |
| Kiểm tra tenant theo dữ liệu client tự khai | Executor có thể thao tác sai tenant | Xác minh quan hệ với đối tượng tại backend |
| Chỉ kiểm tra trước lúc xếp hàng | Trạng thái thay đổi khi tác vụ chạy | Kiểm tra lại và ghi có điều kiện |
| Tự động retry khi timeout | Có thể thực hiện hai lần | Chống lặp và đối soát kết quả |
| Hiểu hết hạn quyền là dừng tức thì | Tác vụ đang chạy vẫn gây hậu quả | Định nghĩa điểm dừng và xác minh |
| Cho phép tự sửa nhóm phê duyệt | Phân tách trách nhiệm bị vượt qua | Kiểm soát cả quyền quản lý chính sách |
| Log toàn bộ request và response | Dữ liệu, credential bị lộ | Lưu metadata cần thiết và che dữ liệu phù hợp |
| Đánh dấu thành công khi tạo job | Bỏ sót lỗi nền và kết quả một phần | Xác minh trạng thái cuối |
| Coi rollback là luôn khả thi | Không xử lý hậu quả không đảo ngược | Kiểm tra phục hồi và giới hạn trước thay đổi |

## 16. Thực hành thiết kế

### Bài tập 1: Xuất dữ liệu khách hàng

Một nhân viên hỗ trợ cần xuất dữ liệu của một khách hàng để xử lý sự cố.

Hãy thiết kế hành động giới hạn theo khách hàng, loại dữ liệu, thời hạn tệp và người nhận. Phân biệt quyền tạo bản xuất với quyền tải xuống. Nêu cách kiểm tra việc tải qua đường dẫn trực tiếp, quyền hết hạn và bản sao đã được tải về.

Gợi ý: kết thúc thời hạn liên kết không thể tự xóa một bản sao đã tải ra ngoài. Kế hoạch phải đánh giá cả phạm vi dữ liệu và hậu quả sau khi phân phối.

### Bài tập 2: Thay người phê duyệt

Một quản trị viên ứng dụng có thể sửa danh sách người phê duyệt và tạo yêu cầu tăng hạn mức thanh toán.

Hãy chỉ ra đường tự phê duyệt có thể xảy ra dù hai hành động dùng hai tài khoản. Đề xuất cách phân tách thẩm quyền và bằng chứng cho thay đổi chính sách phê duyệt.

### Bài tập 3: Timeout khi thao tác hàng loạt

Một tác vụ đã xử lý 200 trong 300 đối tượng rồi mất kết nối. Không rõ hệ thống đích đã xử lý thêm bao nhiêu đối tượng.

Hãy xác định các trạng thái cần lưu, cách đối soát và điều kiện để tiếp tục. Giải thích vì sao gửi lại toàn bộ danh sách chưa chắc an toàn và idempotency key ở gateway chưa đủ nếu hệ thống đích không có bảo đảm tương ứng.

### Bài tập 4: Kiểm tra điều kiện thay đổi sau phê duyệt

Một kế hoạch xóa dữ liệu đã được duyệt. Trước lúc chạy, một đối tượng được đưa vào diện giữ lại để điều tra.

Hãy chỉ ra vị trí cần kiểm tra lại điều kiện và cách tránh khoảng trống giữa kiểm tra với ghi. Nêu cách báo cáo kết quả một phần mà không tự mở rộng hoặc sửa kế hoạch đã duyệt.

## 17. Điểm cần ghi nhớ

Kiểm soát dangerous operation là kiểm soát hậu quả của từng hành động trong ứng dụng. Danh tính đáng tin cậy và credential được bảo vệ là điều kiện cần, nhưng quyền phải còn được giới hạn theo hành động, đối tượng, tham số và thời điểm thực hiện.

Một quy trình đầy đủ gắn phê duyệt với kế hoạch cụ thể, kiểm tra điều kiện tại lúc thực thi, xử lý cạnh tranh và kết quả không rõ, rồi xác minh trạng thái cuối. Bằng chứng cần liên kết được người yêu cầu, người phê duyệt và executor; quyền tạm thời phải có điểm kết thúc thực tế.
