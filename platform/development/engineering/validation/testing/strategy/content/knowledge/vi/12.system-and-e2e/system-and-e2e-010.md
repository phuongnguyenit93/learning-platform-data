# Ghi rõ giới hạn kết luận của luồng đã được kiểm chứng

Một luồng kiểm thử hệ thống hoặc đầu cuối (E2E) thành công cho biết một hành trình cụ thể đã hoạt động đúng trong những điều kiện đã thiết lập. Kết quả đó là bằng chứng có giá trị, nhưng chỉ hỗ trợ kết luận trong phạm vi dữ liệu, cấu hình, môi trường, phiên bản, nhánh xử lý và các điểm kiểm tra thực sự được thực hiện.

Ví dụ, một kiểm thử E2E tạo đơn hàng, thanh toán bằng thẻ thử nghiệm và nhận trang xác nhận thành công chứng minh rằng hành trình đó đã hoàn tất trong môi trường và dữ liệu của lần chạy. Nó không tự động chứng minh mọi phương thức thanh toán đều hoạt động, mọi đơn hàng đều được xử lý đúng, hệ thống chịu được tải cao, quyền truy cập không có lỗ hổng hoặc quy trình hoàn tiền cũng chính xác.

Chiến lược kiểm thử cần yêu cầu nhóm ghi rõ giới hạn kết luận để người đọc không suy rộng bằng chứng vượt quá những gì đã kiểm tra. Một báo cáo tốt nêu được hành trình nào đã chạy, điều kiện nào được sử dụng, điểm nào đã được xác minh, điểm nào chưa được kiểm tra và rủi ro nào còn lại.

## 1. Vì sao một luồng thành công không chứng minh toàn bộ hệ thống?

Kiểm thử hệ thống và E2E thường bao phủ nhiều thành phần hơn kiểm thử đơn vị hoặc kiểm thử thành phần. Chúng có thể xác minh sự phối hợp giữa giao diện, API, dịch vụ, cơ sở dữ liệu và hệ thống bên ngoài. Tuy nhiên, một luồng kiểm thử vẫn chỉ quan sát một tập hợp hữu hạn các tình huống.

Một luồng đặt hàng có thể đi qua các bước:

1. Người dùng đăng nhập.
2. Tìm sản phẩm và thêm vào giỏ hàng.
3. Nhập địa chỉ giao hàng.
4. Xác nhận đơn hàng.
5. Thanh toán.
6. Nhận xác nhận đơn.

Nếu luồng này thành công, nhóm có bằng chứng rằng các bước và điều kiện đã được thiết lập phối hợp đúng trong lần chạy. Kết quả chưa đủ để kết luận rằng:

- Tất cả các vai trò người dùng đều có thể thực hiện đúng hành trình.
- Mọi dữ liệu đầu vào và giá trị biên đều được xử lý chính xác.
- Các nhánh từ chối, hủy, timeout và phục hồi đều hoạt động.
- Tất cả nhà cung cấp thanh toán và phương thức thanh toán đều tương thích.
- Dữ liệu không bị trùng khi yêu cầu được gửi lặp hoặc xử lý đồng thời.
- Hệ thống hoạt động đúng ở mọi trình duyệt, thiết bị và cấu hình được hỗ trợ.
- Hiệu năng đáp ứng khi số lượng người dùng tăng cao.
- Các kiểm soát bảo mật và quyền riêng tư đều hiệu quả.
- Quy trình vận hành và khôi phục sau sự cố đã được xác minh.

Những kết luận này cần bằng chứng riêng. Một kiểm thử có phạm vi rộng không đồng nghĩa với một kiểm thử có phạm vi đầy đủ.

### Phân biệt phạm vi hành trình và phạm vi chất lượng

Hành trình E2E thường tập trung vào kết quả người dùng muốn đạt được. Các thuộc tính chất lượng như hiệu năng, bảo mật, khả năng phục hồi, khả năng tiếp cận và tính tương thích có thể cần phương pháp và điều kiện kiểm tra chuyên biệt.

Ví dụ, việc một người dùng hoàn thành thao tác đăng nhập không chứng minh hệ thống chống được tấn công dò mật khẩu. Việc trang tìm kiếm trả kết quả đúng không chứng minh thời gian phản hồi đạt yêu cầu dưới tải cao. Việc đơn hàng được lưu không chứng minh dữ liệu có thể phục hồi sau sự cố cơ sở dữ liệu.

Do đó, báo cáo cần phân biệt rõ hành vi nghiệp vụ đã xác minh với các thuộc tính chất lượng chưa được đánh giá trong luồng đó.

## 2. Xác định chính xác luồng nào đã được kiểm chứng

Tên kiểm thử như “Đặt hàng thành công” thường quá chung để làm căn cứ cho một kết luận. Nhóm cần mô tả hành trình đủ cụ thể để người khác hiểu lần chạy đã bao gồm những gì.

Một mô tả luồng nên có:

- **Mục tiêu:** kết quả nghiệp vụ cần xác minh.
- **Điểm bắt đầu:** trạng thái, vai trò và điều kiện trước khi chạy.
- **Các bước chính:** hành động và chuyển tiếp giữa các thành phần.
- **Nhánh được bao phủ:** các điều kiện hoặc kết quả khác nhau đã được kiểm tra.
- **Điểm kết thúc:** trạng thái cuối và dữ liệu cần quan sát.
- **Các điểm tích hợp:** dịch vụ, API, cơ sở dữ liệu hoặc nhà cung cấp tham gia.
- **Điều kiện môi trường:** phiên bản, cấu hình, nền tảng và dữ liệu.
- **Assertion:** các điều kiện cụ thể được dùng để xác định đạt hoặc không đạt.

Ví dụ, thay vì ghi “Kiểm thử thanh toán thành công”, hãy mô tả: “Người dùng đã xác thực, tạo một đơn có một sản phẩm còn hàng, thanh toán bằng thẻ thử nghiệm trong môi trường tích hợp, nhận phản hồi thành công và xác minh đơn chuyển sang trạng thái đã thanh toán với một mã giao dịch.”

Mô tả cụ thể giúp giới hạn kết luận vào đúng phương thức, dữ liệu, trạng thái và môi trường đã chạy.

### Phân biệt hành trình chính và các nhánh thay thế

Một hành trình có thể có nhiều nhánh. Nếu chỉ kiểm tra nhánh thành công, báo cáo phải nói rõ các nhánh khác chưa được kiểm chứng trong lần chạy đó.

Với luồng đặt hàng, các nhánh có thể gồm:

- Sản phẩm hết hàng.
- Mã giảm giá không hợp lệ.
- Thanh toán bị từ chối.
- Nhà cung cấp thanh toán timeout.
- Người dùng hủy trước khi xác nhận.
- Tồn kho thay đổi trong lúc thanh toán.
- Yêu cầu được gửi lặp.
- Thông báo thanh toán đến muộn hoặc nhiều lần.
- Dịch vụ thông báo không khả dụng sau khi đơn đã được xác nhận.

Không cần đưa mọi nhánh vào một kịch bản E2E duy nhất. Có thể chia thành nhiều kiểm thử nhỏ hơn, kiểm thử ở cấp độ tích hợp hoặc kiểm thử chuyên biệt. Điều quan trọng là ma trận bằng chứng cho thấy nhánh nào đã được kiểm tra và ở đâu.

## 3. Ghi rõ điều kiện tiền đề và dữ liệu kiểm thử

Kết quả kiểm thử phụ thuộc vào trạng thái ban đầu và dữ liệu. Nếu không ghi nhận các điều kiện này, người đọc có thể hiểu sai khả năng áp dụng của kết quả.

Các điều kiện cần mô tả gồm:

- Tài khoản và vai trò được sử dụng.
- Trạng thái ban đầu của đối tượng.
- Loại dữ liệu và các giá trị quan trọng.
- Số lượng bản ghi hoặc dữ liệu liên quan.
- Cấu hình tính năng và cờ bật/tắt.
- Phiên bản ứng dụng và các dịch vụ phụ thuộc.
- Dữ liệu được tạo mới, tái sử dụng hay làm sạch trước khi chạy.
- Những điều kiện bên ngoài như thời gian, múi giờ hoặc trạng thái nhà cung cấp.

Ví dụ, kiểm thử thanh toán với một tài khoản có hạn mức đủ và một thẻ thử nghiệm hợp lệ không chứng minh hành vi với thẻ hết hạn, hạn mức không đủ hoặc tài khoản bị khóa.

Dữ liệu cũng có thể ảnh hưởng đến kết quả theo cách khó nhận thấy. Một đơn hàng có giá trị nhỏ có thể không đi qua quy tắc làm tròn giống đơn hàng có nhiều sản phẩm. Một người dùng có quyền quản trị không đại diện cho người dùng thông thường. Một sản phẩm luôn còn hàng không thể kiểm tra nhánh hết hàng.

### Dữ liệu đại diện và giới hạn lấy mẫu

Trong hệ thống thực tế, không thể kiểm tra mọi tổ hợp dữ liệu. Nhóm cần chọn dữ liệu đại diện theo rủi ro, bao gồm dữ liệu thông thường, dữ liệu biên, dữ liệu không hợp lệ và dữ liệu có quan hệ giữa nhiều đối tượng.

Báo cáo cần ghi rõ cách lấy mẫu. Nếu chỉ chạy một tài khoản, một trình duyệt và một sản phẩm, không nên suy rộng kết quả sang mọi người dùng, nền tảng hoặc loại sản phẩm.

Với dữ liệu nhạy cảm, cần sử dụng dữ liệu tổng hợp hoặc dữ liệu đã được bảo vệ phù hợp. Báo cáo không nên chứa mật khẩu, token, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết.

## 4. Ghi nhận môi trường và cấu hình của lần chạy

Một luồng có thể thành công ở môi trường kiểm thử nhưng thất bại ở môi trường khác do khác biệt về cấu hình, phiên bản, dữ liệu hoặc phụ thuộc.

Báo cáo nên ghi nhận những yếu tố có ảnh hưởng đến kết quả:

| Yếu tố | Thông tin cần ghi |
|---|---|
| Môi trường | Local, test, staging, sandbox hoặc production |
| Phiên bản ứng dụng | Build, commit hoặc release được kiểm tra |
| Phiên bản dịch vụ | Các dịch vụ tham gia và phiên bản liên quan |
| Cấu hình | Feature flag, biến môi trường và cấu hình quan trọng |
| Nền tảng | Trình duyệt, hệ điều hành, thiết bị hoặc runtime |
| Dữ liệu | Bộ dữ liệu, tài khoản, trạng thái và cách khởi tạo |
| Phụ thuộc | Dịch vụ thật, sandbox, mock, stub hoặc giả lập |
| Thời điểm | Thời gian chạy và múi giờ nếu có ý nghĩa |

Cần phân biệt môi trường dùng dịch vụ thật với môi trường dùng mock hoặc sandbox. Một mock có thể giúp kiểm tra cách consumer xử lý phản hồi đã định nghĩa, nhưng không chứng minh nhà cung cấp thật đang hoạt động đúng. Sandbox có thể không mô phỏng đầy đủ giới hạn tốc độ, độ trễ, dữ liệu hoặc sự cố của môi trường sản xuất.

Nếu một điểm tích hợp được thay thế bằng mock, báo cáo cần chỉ rõ điểm đó và giới hạn bằng chứng tương ứng.

### Mức độ tương đồng với môi trường thực tế

Không phải mọi môi trường kiểm thử đều phải giống sản xuất hoàn toàn. Tuy nhiên, những khác biệt có thể ảnh hưởng đến kết quả cần được ghi nhận.

Ví dụ:

- Môi trường staging dùng một cơ sở dữ liệu nhỏ hơn.
- Cổng thanh toán dùng sandbox.
- Dịch vụ email được thay bằng bộ thu nhận thư thử nghiệm.
- Hệ thống chỉ chạy một instance thay vì nhiều instance.
- Cấu hình cache hoặc timeout khác sản xuất.
- Không có tải đồng thời hoặc dữ liệu lịch sử lớn.

Các khác biệt này không làm kết quả kiểm thử vô giá trị. Chúng giới hạn loại kết luận có thể đưa ra.

## 5. Xác định những gì assertion thực sự chứng minh

Một kiểm thử chỉ có giá trị khi xác minh đúng kết quả cần quan tâm. Việc kiểm tra một thông báo thành công trên giao diện có thể chưa đủ để chứng minh giao dịch đã được ghi nhận đúng.

Với mỗi luồng, hãy xem xét các điểm quan sát:

- Phản hồi giao diện và thông báo cho người dùng.
- Mã trạng thái và nội dung phản hồi API.
- Trạng thái đối tượng trong cơ sở dữ liệu.
- Sự kiện được phát và được tiêu thụ.
- Bản ghi giao dịch hoặc lịch sử thay đổi.
- Log, metric và trace liên quan.
- Kết quả ở hệ thống bên ngoài nếu có thể truy cập.

Ví dụ, kiểm thử đặt hàng có thể xác nhận:

1. Giao diện hiển thị thông báo đặt hàng thành công.
2. API trả mã phản hồi theo hợp đồng.
3. Đơn hàng tồn tại với đúng người sở hữu và tổng tiền.
4. Trạng thái đơn là đã xác nhận.
5. Có đúng một giao dịch liên quan.
6. Sự kiện xác nhận được phát theo quy tắc.
7. Không có bản ghi trùng sau khi xử lý thông điệp lặp.

Nếu kiểm thử chỉ kiểm tra mục 1, kết luận phải giới hạn ở phản hồi giao diện. Nếu kiểm tra cả bảy mục, bằng chứng mạnh hơn cho các bất biến được nêu, nhưng vẫn không chứng minh mọi nhánh hoặc mọi điều kiện vận hành đều đúng.

### Tránh assertion yếu

Một số assertion không đủ mạnh để chứng minh hành vi:

- Chỉ xác nhận trang đã tải mà không kiểm tra nội dung hoặc trạng thái.
- Chỉ xác nhận phản hồi HTTP thành công mà không kiểm tra dữ liệu.
- Chỉ kiểm tra số bản ghi lớn hơn không thay vì xác minh đúng bản ghi.
- Chỉ kiểm tra thông báo thành công mà không xác minh giao dịch.
- Chỉ kiểm tra một thành phần mà không xác minh kết quả ở phía nhận.
- Dùng dữ liệu cố định nhưng không xác minh dữ liệu đó thực sự được sử dụng.

Assertion cần phản ánh quy tắc nghiệp vụ và rủi ro. Với giao dịch tiền, cần kiểm tra số tiền, đơn vị, trạng thái và tính duy nhất của giao dịch. Với phân quyền, cần xác minh cả truy cập được phép và truy cập bị từ chối.

## 6. Ghi rõ các điểm tích hợp đã được kiểm tra

Một kiểm thử hệ thống có thể đi qua nhiều thành phần nhưng không phải lúc nào cũng xác minh mọi giao tiếp giữa chúng. Có thành phần được thay thế bằng mock, có lời gọi chỉ được xác nhận qua phản hồi tổng thể và có dịch vụ bên ngoài không thể quan sát trực tiếp.

Nên lập danh sách các điểm tích hợp:

| Điểm tích hợp | Cách kiểm tra | Điều kết quả hỗ trợ kết luận |
|---|---|---|
| Giao diện → API đơn hàng | Gửi yêu cầu qua giao diện và xác minh phản hồi | Hành vi gọi API trong kịch bản đã chạy |
| API đơn hàng → cơ sở dữ liệu | Kiểm tra trạng thái và bản ghi sau thao tác | Dữ liệu được ghi đúng trong điều kiện đã thử |
| Đơn hàng → thanh toán | Gọi sandbox và xác minh kết quả | Tích hợp hoạt động với cấu hình và tình huống sandbox đó |
| Thanh toán → sự kiện | Quan sát sự kiện và consumer | Hành vi xử lý sự kiện trong lần chạy |
| Đơn hàng → thông báo | Dùng dịch vụ thử nghiệm hoặc mock | Hành vi gửi yêu cầu thông báo theo hợp đồng đã kiểm tra |

Nếu một điểm không được quan sát trực tiếp, cần nêu cách suy luận và giới hạn của nó. Ví dụ, nhận email xác nhận có thể chứng minh một thông báo đã được nhận trong hộp thư thử nghiệm, nhưng chưa chắc chứng minh khả năng gửi email ổn định đến mọi nhà cung cấp.

## 7. Phân biệt kết quả đạt, không đạt, bỏ qua và chưa kiểm tra

Một báo cáo cần dùng trạng thái rõ ràng. Không nên gom mọi trường hợp không có lỗi thành “Passed”.

| Trạng thái | Ý nghĩa |
|---|---|
| Passed | Kiểm thử đã chạy, các assertion đã xác minh và kết quả đáp ứng điều kiện mong đợi |
| Failed | Kiểm thử đã chạy và có ít nhất một kết quả không đáp ứng điều kiện |
| Blocked | Không thể hoàn tất do phụ thuộc, môi trường, dữ liệu hoặc quyền truy cập |
| Skipped | Kiểm thử được chủ động bỏ qua theo điều kiện hoặc quyết định đã ghi nhận |
| Not run | Kiểm thử chưa được thực hiện trong lần đánh giá |
| Inconclusive | Có chạy nhưng bằng chứng chưa đủ để kết luận |
| Flaky | Kết quả không ổn định giữa các lần chạy trong điều kiện tương đương |

### Passed không đồng nghĩa không còn rủi ro

Passed chỉ áp dụng cho các điều kiện và assertion của kiểm thử đó. Nó không có nghĩa toàn bộ hệ thống không còn lỗi.

### Failed cần được phân loại

Một kiểm thử thất bại có thể do lỗi sản phẩm, lỗi kiểm thử, dữ liệu, môi trường hoặc phụ thuộc. Cần điều tra trước khi kết luận nguyên nhân. Tuy nhiên, không nên tự động bỏ qua kết quả chỉ vì chưa xác định được lỗi nằm ở đâu.

### Blocked và Skipped phải được nhìn thấy

Nếu một kiểm thử bị chặn do môi trường không sẵn sàng hoặc bị bỏ qua vì thiếu dữ liệu, báo cáo cần ghi rõ. Không nên đưa các trường hợp này vào mẫu số của tỷ lệ đạt mà không giải thích, vì điều đó có thể làm kết quả trông tốt hơn thực tế.

### Flaky không phải là Passed

Một kiểm thử lúc đạt lúc thất bại làm giảm độ tin cậy của bằng chứng. Cần ghi nhận tỷ lệ không ổn định, nguyên nhân đã biết và kế hoạch xử lý. Nếu phải chạy lại để có kết quả, báo cáo nên giữ lại cả lần thất bại ban đầu và lần chạy lại.

## 8. Giới hạn của kiểm thử hệ thống và E2E

Mỗi loại kiểm thử có phạm vi và điểm mù riêng. Báo cáo cần nêu những giới hạn quan trọng để tránh hiểu nhầm.

### Giới hạn về tổ hợp

Một luồng thường dùng một tập dữ liệu và cấu hình đại diện. Nó không bao phủ tất cả tổ hợp người dùng, quyền, dữ liệu, thiết bị và trạng thái.

### Giới hạn về thời gian và tính đồng thời

Một lần chạy tuần tự không chứng minh hệ thống xử lý đúng nhiều yêu cầu đồng thời. Muốn đánh giá race condition, deadlock hoặc tải cao cần kịch bản riêng.

### Giới hạn về môi trường

Kết quả trong môi trường thử nghiệm không tự động áp dụng cho sản xuất nếu có khác biệt về cấu hình, dữ liệu, hạ tầng hoặc nhà cung cấp.

### Giới hạn về phụ thuộc bên ngoài

Sandbox, mock và stub chỉ cung cấp bằng chứng cho cách tích hợp trong phạm vi mô phỏng. Chúng không xác nhận mọi hành vi của dịch vụ bên ngoài.

### Giới hạn về thuộc tính phi chức năng

Một luồng E2E chức năng không chứng minh hiệu năng, bảo mật, khả năng tiếp cận, độ bền hoặc khả năng phục hồi nếu không có phép đo và tiêu chí tương ứng.

### Giới hạn về dữ liệu và thời gian dài

Một lần chạy với dữ liệu nhỏ không chứng minh hành vi khi dữ liệu tích lũy lớn. Một phiên ngắn không chứng minh hệ thống không rò rỉ tài nguyên hoặc không suy giảm sau nhiều giờ hoạt động.

### Giới hạn về khả năng quan sát

Nếu kiểm thử chỉ quan sát giao diện, lỗi nội bộ hoặc trạng thái dữ liệu sai có thể không được phát hiện. Kết luận cần phản ánh những điểm mà kiểm thử thực sự quan sát được.

## 9. Cách diễn đạt kết luận có giới hạn

Kết luận nên mô tả điều đã xác minh, điều kiện áp dụng và những gì chưa được chứng minh. Tránh các câu tuyệt đối như “toàn bộ hệ thống hoạt động hoàn hảo” hoặc “không còn lỗi”.

Ví dụ về cách viết:

| Diễn đạt quá rộng | Diễn đạt có giới hạn |
|---|---|
| Luồng thanh toán đã hoạt động tốt. | Luồng thanh toán bằng thẻ thử nghiệm đã hoàn tất trong môi trường staging với một tài khoản và một đơn hàng hợp lệ. |
| Tích hợp thanh toán không có lỗi. | Yêu cầu và phản hồi thanh toán trong kịch bản thành công đã khớp hợp đồng; timeout, webhook lặp và đối soát chưa được kiểm tra trong lần chạy này. |
| Hệ thống đặt hàng đã được xác minh. | Hành trình tạo và xác nhận đơn hàng đã được kiểm tra với một sản phẩm còn hàng; nhánh hết hàng, gửi đồng thời và hủy đơn chưa nằm trong phạm vi. |
| Bảo mật đã đạt. | Kiểm tra quyền truy cập cho hai vai trò được chọn đã đạt; chưa thực hiện đánh giá bảo mật chuyên sâu hoặc kiểm tra xâm nhập. |
| Hệ thống đáp ứng hiệu năng. | Thời gian phản hồi được đo ở mức tải đã mô tả; chưa đánh giá tải cực đại hoặc thử nghiệm kéo dài. |

Một kết luận hữu ích không làm giảm giá trị của kết quả. Nó giúp người đọc hiểu chính xác bằng chứng có thể hỗ trợ quyết định nào.

### Dùng cấu trúc bốn phần

Có thể viết kết luận theo bốn phần:

1. **Đã kiểm chứng:** hành trình, nhánh, assertion và kết quả cụ thể.
2. **Điều kiện:** môi trường, phiên bản, dữ liệu, cấu hình và phụ thuộc.
3. **Chưa kiểm chứng:** nhánh, nền tảng hoặc thuộc tính chất lượng chưa được đánh giá.
4. **Rủi ro còn lại:** mức ảnh hưởng, biện pháp bổ sung và người chịu trách nhiệm.

Ví dụ:

“Trong bản dựng 2.8.1 trên staging, hành trình tạo đơn và thanh toán thành công bằng thẻ sandbox đã đạt. Kiểm thử xác minh phản hồi API, trạng thái đơn và một bản ghi giao dịch. Lần chạy dùng một tài khoản khách hàng và một sản phẩm còn hàng. Chưa kiểm tra thanh toán bị từ chối, timeout, webhook lặp, tải đồng thời và giao dịch hoàn tiền. Rủi ro về xử lý kết quả không chắc chắn vẫn cần kiểm thử tích hợp riêng trước khi phát hành.”

## 10. Ví dụ thực tế: giới hạn kết luận của luồng đặt hàng

Giả sử một nhóm chạy E2E cho hành trình:

1. Đăng nhập bằng tài khoản khách hàng.
2. Chọn một sản phẩm còn hàng.
3. Thêm một sản phẩm vào giỏ.
4. Nhập địa chỉ giao hàng hợp lệ.
5. Tạo đơn.
6. Thanh toán bằng thẻ sandbox.
7. Xác minh trang xác nhận và trạng thái đơn.

Kết quả Passed có thể hỗ trợ kết luận:

- Tài khoản được dùng có thể đăng nhập trong môi trường đã thử.
- Sản phẩm và địa chỉ được chọn được chấp nhận.
- Hành trình tạo đơn đã hoàn tất.
- Tích hợp thanh toán sandbox trả kết quả thành công trong tình huống này.
- Các assertion về trang xác nhận, trạng thái đơn và giao dịch đã đạt.

Kết quả này chưa hỗ trợ kết luận:

- Tất cả sản phẩm hoặc mọi mức tồn kho đều được xử lý đúng.
- Mọi mã giảm giá, thuế và phí vận chuyển đều tính chính xác.
- Mọi phương thức thanh toán đều hoạt động.
- Hệ thống xử lý đúng yêu cầu gửi lặp hoặc đồng thời.
- Giao dịch được đối soát chính xác khi phản hồi bị mất.
- Đơn hàng được xử lý đúng khi dịch vụ vận chuyển hoặc thông báo lỗi.
- Mọi vai trò và người dùng đều có quyền phù hợp.
- Hệ thống đáp ứng tải cao và hoạt động ổn định trong thời gian dài.

### Bảng bằng chứng và khoảng trống

| Hạng mục | Kết quả | Giới hạn hoặc công việc tiếp theo |
|---|---|---|
| Đăng nhập khách hàng | Passed | Chưa kiểm tra tài khoản khóa hoặc phiên hết hạn |
| Tạo đơn với sản phẩm còn hàng | Passed | Chưa kiểm tra hết hàng và cập nhật tồn kho đồng thời |
| Địa chỉ giao hàng hợp lệ | Passed | Chưa kiểm tra địa chỉ sai định dạng hoặc vùng không hỗ trợ |
| Thanh toán thẻ sandbox thành công | Passed | Chưa kiểm tra từ chối, timeout và webhook lặp |
| Trạng thái đơn sau thanh toán | Passed | Chưa kiểm tra cập nhật một phần hoặc sự kiện đến sai thứ tự |
| Gửi thông báo | Skipped | Phụ thuộc dịch vụ thử nghiệm chưa sẵn sàng |
| Hiệu năng dưới tải | Not run | Cần kịch bản tải riêng |
| Quyền truy cập chéo tài khoản | Not run | Cần kiểm thử bảo mật API |

Bảng này giúp người ra quyết định thấy rằng hành trình chính đã đạt nhưng vẫn còn các khoảng trống cụ thể. Nhóm có thể quyết định chạy bổ sung các kiểm thử rủi ro cao hoặc ghi nhận rủi ro còn lại theo quy trình phát hành.

## 11. Liên kết kết quả E2E với kiểm thử ở các tầng khác

Một luồng E2E không cần tự xác minh mọi quy tắc ở mức chi tiết. Các tầng thấp hơn có thể cung cấp bằng chứng chuyên biệt, còn E2E xác nhận hành trình phối hợp.

Ví dụ với tính tổng tiền đơn hàng:

- Kiểm thử đơn vị xác minh công thức, thuế, giảm giá và làm tròn trên nhiều giá trị.
- Kiểm thử hợp đồng xác minh đơn vị tiền và cấu trúc dữ liệu giữa dịch vụ đơn hàng và thanh toán.
- Kiểm thử tích hợp xác minh dữ liệu và trạng thái giao dịch được ghi nhất quán.
- Kiểm thử E2E xác minh người dùng nhìn thấy tổng tiền phù hợp và hoàn tất hành trình với dữ liệu đại diện.

Khi báo cáo kết quả, nên liên kết đến bằng chứng ở từng tầng. Nếu E2E đạt nhưng kiểm thử hợp đồng thất bại hoặc chưa chạy, không nên tuyên bố toàn bộ tích hợp đã được xác minh.

### Ma trận truy vết bằng chứng

| Rủi ro hoặc yêu cầu | Đơn vị | Hợp đồng | Tích hợp | E2E | Kết luận |
|---|---|---|---|---|---|
| Tính tổng tiền chính xác | Đã kiểm tra | Kiểm tra định dạng tiền | Kiểm tra lưu và chuyển dữ liệu | Kiểm tra hành trình đại diện | Có bằng chứng ở nhiều tầng; cần xem phạm vi từng tầng |
| Không tạo giao dịch trùng | Kiểm tra logic idempotency | Kiểm tra mã giao dịch | Kiểm tra thông điệp lặp | Chưa chạy nhánh gửi lặp | Chưa đủ bằng chứng xuyên suốt |
| Chặn truy cập đơn của người khác | Kiểm tra chính sách | Kiểm tra yêu cầu quyền | Kiểm tra API thực tế | Chỉ chạy vai trò khách hàng hợp lệ | Cần bổ sung kiểm tra truy cập trái phép |
| Phục hồi khi nhà cung cấp timeout | Kiểm tra logic retry | Kiểm tra mã lỗi và phản hồi | Kiểm tra timeout thực tế | Chưa chạy | Chưa được xác minh |

Trạng thái trong bảng chỉ là minh họa. Nhóm cần ghi kết quả thực tế và liên kết đến báo cáo tương ứng.

## 12. Quản lý rủi ro còn lại và quyết định phát hành

Sau khi kiểm thử, luôn có thể còn những điều chưa được xác minh. Điều quan trọng là phân biệt khoảng trống đã biết, rủi ro được chấp nhận và vấn đề chưa rõ.

Một rủi ro còn lại nên có:

- Mô tả tình huống và hậu quả.
- Lý do chưa được kiểm tra hoặc chưa thể xử lý.
- Mức độ ảnh hưởng và khả năng xảy ra.
- Bằng chứng hiện có và giới hạn của bằng chứng.
- Biện pháp giảm thiểu hoặc giám sát.
- Người hoặc nhóm sở hữu.
- Người có thẩm quyền chấp nhận nếu cần.
- Thời hạn hoặc điều kiện xem xét lại.

Ví dụ, nhóm chưa thể kiểm tra webhook thanh toán lặp trong môi trường staging. Nếu luồng này có thể gây giao dịch trùng, cần xác định mức rủi ro, kiểm tra logic idempotency ở tầng thấp hơn, chuẩn bị kịch bản tích hợp và quyết định liệu có đủ điều kiện phát hành hay không.

Không nên dùng tỷ lệ E2E Passed làm tiêu chí phát hành duy nhất. Một bộ kiểm thử đạt 100% vẫn có thể bỏ qua nhánh lỗi quan trọng. Quyết định cần xét mức độ rủi ro, bằng chứng ở các tầng, giới hạn môi trường, khả năng giám sát và phương án phục hồi.

### Khi nào cần bổ sung kiểm thử?

Có thể ưu tiên bổ sung khi:

- Luồng liên quan đến tiền, dữ liệu nhạy cảm hoặc quyền truy cập.
- Có thay đổi lớn ở ranh giới dịch vụ hoặc hợp đồng.
- Lỗi tương tự từng xảy ra trong sản xuất.
- Nhánh lỗi có hậu quả nghiêm trọng chưa được kiểm tra.
- Kết quả phụ thuộc vào mock hoặc sandbox không đại diện đủ cho sản xuất.
- Kiểm thử không ổn định hoặc assertion chưa đủ mạnh.
- Không có bằng chứng cho khả năng phục hồi hoặc đối soát.

Nếu không thể bổ sung ngay, cần ghi nhận rủi ro và người có trách nhiệm quyết định.

## 13. Những sai lầm thường gặp khi báo cáo kết quả E2E

- **Kết luận quá rộng từ một luồng thành công:** một hành trình đại diện không bao phủ mọi người dùng, dữ liệu và nhánh.
- **Không ghi điều kiện tiền đề:** người đọc không biết tài khoản, dữ liệu và trạng thái nào đã được sử dụng.
- **Không phân biệt dịch vụ thật với mock:** kết quả bị hiểu nhầm là đã xác minh nhà cung cấp thật.
- **Chỉ kiểm tra thông báo giao diện:** có thể bỏ sót dữ liệu hoặc giao dịch không nhất quán phía sau.
- **Gộp Skipped và Not run vào Passed:** làm sai lệch tỷ lệ đạt và che giấu khoảng trống.
- **Bỏ qua kiểm thử không ổn định:** lần chạy lại đạt không xóa bỏ bằng chứng thất bại trước đó.
- **Không nêu giới hạn phi chức năng:** kiểm thử chức năng không chứng minh hiệu năng, bảo mật hoặc khả năng phục hồi.
- **Không liên kết bằng chứng giữa các tầng:** E2E đạt nhưng các hợp đồng hoặc kiểm thử tích hợp quan trọng có thể chưa được xác minh.
- **Không ghi rủi ro còn lại:** người ra quyết định không biết phần nào chưa được kiểm tra.
- **Dùng từ tuyệt đối:** các tuyên bố như “hệ thống không còn lỗi” vượt quá khả năng chứng minh của kiểm thử.

## 14. Mẫu báo cáo giới hạn kết luận của một luồng

Có thể dùng mẫu sau cho một lần chạy hệ thống hoặc E2E:

~~~text
TÊN LUỒNG:
MỤC TIÊU NGHIỆP VỤ:

PHẠM VI ĐÃ CHẠY:
- Điểm bắt đầu:
- Các bước chính:
- Nhánh được kiểm tra:
- Điểm kết thúc:

ĐIỀU KIỆN:
- Môi trường:
- Phiên bản:
- Cấu hình:
- Tài khoản / vai trò:
- Dữ liệu:
- Dịch vụ thật / sandbox / mock:

ASSERTION:
- Hành vi đã xác minh:
- Trạng thái và dữ liệu đã kiểm tra:
- Điểm tích hợp đã quan sát:
- Bằng chứng:

KẾT QUẢ:
- Passed:
- Failed:
- Blocked:
- Skipped:
- Not run:
- Inconclusive / Flaky:

GIỚI HẠN:
- Nhánh chưa kiểm tra:
- Nền tảng hoặc cấu hình chưa kiểm tra:
- Thuộc tính chất lượng chưa đánh giá:
- Phụ thuộc được mô phỏng:

RỦI RO CÒN LẠI:
- Mô tả:
- Mức ảnh hưởng:
- Biện pháp giảm thiểu:
- Chủ sở hữu:
- Thời điểm xem xét lại:

KẾT LUẬN:
Điều đã được chứng minh:
Điều chưa thể kết luận:
Điều kiện áp dụng của kết quả:
~~~

Mẫu không cần được điền dài dòng cho mọi kiểm thử nhỏ. Với luồng có rủi ro cao hoặc được dùng làm bằng chứng phát hành, cần ghi đủ thông tin để người khác có thể đánh giá độc lập.

## Kết luận

Một luồng hệ thống hoặc E2E thành công chỉ chứng minh các hành vi và assertion đã được kiểm tra trong điều kiện cụ thể của lần chạy. Kết quả không tự động đại diện cho mọi dữ liệu, người dùng, nhánh lỗi, môi trường, tải hoặc thuộc tính chất lượng.

Khi ghi rõ phạm vi, tiền điều kiện, dữ liệu, cấu hình, điểm tích hợp, assertion, trạng thái chưa chạy và rủi ro còn lại, nhóm có thể truyền đạt chính xác giá trị của bằng chứng. Kết luận có giới hạn giúp người ra quyết định hiểu điều gì đã được xác minh, điều gì vẫn chưa chắc chắn và cần bổ sung kiểm thử hoặc biện pháp kiểm soát nào trước khi phát hành.
