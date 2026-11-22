# Phân biệt tích hợp giữa thành phần và tích hợp giữa hệ thống

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, kiểm thử tích hợp giúp phát hiện lỗi ở ranh giới nơi các phần mềm trao đổi dữ liệu, gọi chức năng hoặc phối hợp xử lý. Hai phạm vi thường cần phân biệt là **tích hợp giữa thành phần** (component integration testing) và **tích hợp giữa hệ thống** (system integration testing). Cả hai đều kiểm tra sự tương tác, nhưng khác nhau ở ranh giới được kiểm tra, loại phụ thuộc, mục tiêu bằng chứng và điều kiện môi trường.

Tích hợp giữa thành phần tập trung vào cách các thành phần bên trong một hệ thống phối hợp với nhau. Tích hợp giữa hệ thống tập trung vào cách hệ thống đang kiểm thử trao đổi với những hệ thống độc lập khác, chẳng hạn hệ thống thanh toán, quản lý kho, định danh hoặc đối tác bên ngoài. Phân biệt đúng hai phạm vi giúp nhóm chọn môi trường, dữ liệu, công cụ mô phỏng, người phối hợp và tiêu chí hoàn tất phù hợp.

## 1. Trước hết, hiểu ranh giới tích hợp

Một sản phẩm phần mềm thường gồm nhiều phần: module, lớp, dịch vụ nội bộ, cơ sở dữ liệu, hàng đợi, API và các hệ thống bên ngoài. Các phần này có thể được phát triển bởi một nhóm hoặc nhiều nhóm, triển khai cùng nhau hoặc độc lập, dùng chung hoặc sở hữu dữ liệu riêng.

Để phân loại hoạt động tích hợp, cần xác định ranh giới kiến trúc mà dự án đã thống nhất:

- **Thành phần (component):** một phần có trách nhiệm tương đối rõ trong một hệ thống, cung cấp hoặc sử dụng giao diện với phần khác. Thành phần có thể là module, package, service nội bộ, adapter hoặc một đơn vị phần mềm được kiểm soát trong phạm vi sản phẩm.
- **Hệ thống (system):** một hệ thống phần mềm có ranh giới chức năng và trách nhiệm riêng, thường có giao diện tích hợp được xác định với hệ thống khác. Hệ thống có thể được triển khai, vận hành hoặc quản lý độc lập.
- **Giao diện tích hợp:** nơi các phần trao đổi dữ liệu hoặc điều khiển, ví dụ lời gọi hàm, API, sự kiện, thông điệp hàng đợi, tệp trao đổi, giao thức mạng hoặc thao tác cơ sở dữ liệu.

Ranh giới này phụ thuộc kiến trúc và cách tổ chức sản phẩm. Trong một kiến trúc nguyên khối, hai module trong cùng ứng dụng thường được xem là hai thành phần. Trong kiến trúc phân tán, một microservice có thể được xem là một thành phần của sản phẩm ở góc nhìn kiến trúc tổng thể, nhưng lại được kiểm thử như một hệ thống độc lập khi đánh giá hợp đồng và tương tác với service khác. Vì vậy, hãy ghi rõ ranh giới trong kế hoạch thay vì chỉ dựa vào tên gọi.

## 2. Tích hợp giữa thành phần (component integration testing)

Kiểm thử tích hợp giữa thành phần đánh giá tương tác giữa các thành phần bên trong một hệ thống. Mục tiêu là xác nhận các giao diện nội bộ, luồng dữ liệu, thứ tự gọi, xử lý lỗi và phối hợp trạng thái hoạt động đúng khi các phần được kết nối.

Những vấn đề thường được kiểm tra gồm:

- Thành phần gọi đúng giao diện và truyền đúng tham số.
- Dữ liệu trả về có cấu trúc, kiểu, đơn vị và ý nghĩa như mong đợi.
- Quy tắc chuyển đổi dữ liệu giữa các module không làm mất hoặc biến đổi sai thông tin.
- Thứ tự thực hiện và phụ thuộc giữa các thành phần đúng với thiết kế.
- Ngoại lệ, lỗi và trạng thái không hợp lệ được truyền hoặc xử lý đúng.
- Giao dịch, rollback, cache và trạng thái dùng chung được quản lý nhất quán.
- Thành phần có thể thay thế hoặc cấu hình phụ thuộc theo cách đã thiết kế.

### Ví dụ trong một hệ thống đặt hàng

Giả sử một ứng dụng đặt hàng gồm các thành phần nội bộ:

1. `OrderController` nhận yêu cầu từ giao diện.
2. `OrderService` điều phối việc tạo đơn.
3. `PricingComponent` tính giá, thuế và giảm giá.
4. `InventoryComponent` kiểm tra và giữ hàng trong phạm vi ứng dụng.
5. `OrderRepository` lưu đơn vào cơ sở dữ liệu.

Kiểm thử đơn vị có thể xác nhận riêng `PricingComponent` tính đúng một tập đầu vào. Kiểm thử tích hợp giữa thành phần kiểm tra `OrderService` gọi `PricingComponent`, `InventoryComponent` và `OrderRepository` đúng thứ tự, truyền đúng dữ liệu và xử lý đúng khi một thành phần từ chối giữ hàng hoặc thao tác lưu thất bại.

Ví dụ, khi không còn đủ hàng, `InventoryComponent` trả về kết quả không thành công. Test cần xác nhận `OrderService` không tạo đơn ở trạng thái đã xác nhận và không để lại dữ liệu giữ hàng không hợp lệ. Khi lưu đơn thất bại sau khi giữ hàng, nhóm cần kiểm tra cơ chế giải phóng giữ hàng hoặc bù trừ theo thiết kế.

### Phương pháp và công cụ thường dùng

- Chạy các thành phần thật cùng nhau trong một tiến trình hoặc môi trường kiểm thử cô lập.
- Dùng test double, stub, fake hoặc mock cho phụ thuộc chưa thuộc phạm vi đang kiểm tra.
- Kiểm tra giao diện nội bộ, schema, kiểu dữ liệu, ngoại lệ và trạng thái.
- Kiểm tra giao dịch cơ sở dữ liệu, cache, hàng đợi nội bộ hoặc adapter tùy ranh giới thành phần.
- Dùng log, assertion và trace để xác định thành phần nào tạo ra sai lệch.
- Chạy kiểm thử tự động gần với mỗi thay đổi để phát hiện lỗi sớm.

Test double giúp cô lập một phụ thuộc để tập trung vào tương tác cần kiểm tra, nhưng không chứng minh phụ thuộc thật hoạt động đúng. Do đó, cần kết hợp kiểm thử với phụ thuộc thật ở những ranh giới có rủi ro đáng kể.

## 3. Tích hợp giữa hệ thống (system integration testing)

Kiểm thử tích hợp giữa hệ thống đánh giá tương tác giữa hệ thống đang kiểm thử với một hoặc nhiều hệ thống độc lập khác. Các hệ thống có thể thuộc cùng tổ chức, thuộc nhóm khác, do nhà cung cấp vận hành hoặc do đối tác bên ngoài cung cấp.

Mục tiêu là xác nhận giao tiếp xuyên ranh giới hệ thống hoạt động đúng trong điều kiện thực tế hoặc điều kiện đại diện. Nhóm cần xem xét cả giao thức kỹ thuật lẫn ý nghĩa nghiệp vụ của dữ liệu được trao đổi.

Những vấn đề thường được kiểm tra gồm:

- Endpoint, giao thức, phương thức xác thực và quyền truy cập đúng.
- Hợp đồng API hoặc thông điệp phù hợp giữa bên gửi và bên nhận.
- Phiên bản, schema, kiểu dữ liệu, đơn vị, mã hóa và quy tắc tương thích được xử lý đúng.
- Timeout, retry, rate limit, circuit breaker và lỗi mạng có hành vi phù hợp.
- Sự kiện trùng, đến trễ, sai thứ tự hoặc bị mất được xử lý theo thiết kế.
- Dữ liệu được đối soát và duy trì tính nhất quán qua các hệ thống.
- Quyền riêng tư, bảo mật, mã hóa, audit và quản lý bí mật được bảo đảm ở ranh giới tích hợp.
- Quy trình xuyên hệ thống có thể hoàn tất, hoặc thất bại theo cách an toàn và có thể phục hồi.

### Ví dụ: hệ thống đặt hàng kết nối với thanh toán và kho

Hệ thống đặt hàng cần trao đổi với ba hệ thống độc lập:

- **Payment Gateway:** tiếp nhận yêu cầu thanh toán và gửi kết quả qua API hoặc webhook.
- **Warehouse Management System (WMS):** kiểm tra tồn kho, giữ hàng và xác nhận xuất kho.
- **Notification Service:** gửi email hoặc tin nhắn thông báo trạng thái đơn.

Kiểm thử tích hợp giữa hệ thống xác nhận hệ thống đặt hàng gửi yêu cầu đúng đến Payment Gateway, xác minh chữ ký webhook, cập nhật trạng thái đơn khi thanh toán thành công và phối hợp với WMS. Nhóm cũng kiểm tra trường hợp cổng thanh toán timeout nhưng giao dịch thực tế đã thành công, webhook gửi lặp, WMS tạm ngừng hoạt động hoặc Notification Service từ chối nhận thông điệp.

Một test có thể gửi yêu cầu thanh toán qua sandbox của nhà cung cấp, nhận webhook thử nghiệm, rồi xác minh trạng thái đơn hàng và dữ liệu đối soát. Nếu sandbox không mô phỏng được một tình huống quan trọng, nhóm cần ghi rõ giới hạn và bổ sung phương pháp khác như mô phỏng lỗi, kiểm tra hợp đồng hoặc xác nhận với nhà cung cấp.

### Phương pháp và công cụ thường dùng

- Kiểm thử hợp đồng API hoặc message contract giữa consumer và provider.
- Kiểm thử tích hợp với môi trường sandbox hoặc test environment của đối tác.
- Dùng service virtualization hoặc simulator khi hệ thống thật không sẵn sàng.
- Kiểm tra API, webhook, message broker, tệp trao đổi hoặc giao thức mạng.
- Mô phỏng timeout, mất kết nối, lỗi xác thực, rate limit và phản hồi bất thường.
- Đối soát dữ liệu và trạng thái xuyên hệ thống bằng correlation ID hoặc mã giao dịch.
- Kiểm tra tương thích phiên bản và khả năng triển khai độc lập của các bên.

## 4. So sánh hai phạm vi tích hợp

| Khía cạnh | Tích hợp giữa thành phần | Tích hợp giữa hệ thống |
|---|---|---|
| Ranh giới | Giữa các thành phần bên trong một hệ thống | Giữa hệ thống đang kiểm thử và hệ thống độc lập khác |
| Trọng tâm | Giao diện nội bộ, lời gọi, luồng dữ liệu và phối hợp trạng thái | API/giao thức, hợp đồng, thông điệp, phiên bản và quy trình xuyên hệ thống |
| Phụ thuộc | Module, package, adapter, repository, service nội bộ | Hệ thống khác, nhà cung cấp, đối tác, nền tảng dùng chung |
| Điều kiện môi trường | Thường có thể kiểm soát trong môi trường phát triển hoặc test tích hợp | Cần cấu hình mạng, tài khoản, chứng thư, sandbox, endpoint và quyền từ các bên liên quan |
| Dữ liệu | Dữ liệu nội bộ, giao dịch, trạng thái và cấu trúc dùng chung | Dữ liệu trao đổi, mapping, đồng bộ, mã định danh và đối soát xuyên hệ thống |
| Lỗi điển hình | Gọi sai hàm, truyền sai tham số, xử lý ngoại lệ sai, rollback không đúng | Timeout, lỗi xác thực, schema không tương thích, retry trùng, sự kiện đến trễ hoặc sai thứ tự |
| Phương pháp | Thành phần thật kết hợp test double, kiểm tra giao diện và trạng thái | Contract test, sandbox, service virtualization, kiểm tra giao thức và đối soát |
| Phối hợp | Thường trong một nhóm hoặc các nhóm nội bộ gần nhau | Có thể cần nhóm sở hữu hệ thống khác, nhà cung cấp hoặc đối tác |
| Bằng chứng | Kết quả tương tác nội bộ, trạng thái dữ liệu, log và lỗi thành phần | Request/response, message, trace, mã giao dịch, log hai phía và kết quả đối soát |

Sự khác biệt cốt lõi là **ranh giới tích hợp được kiểm tra**. Một bài kiểm thử có thể bao gồm cả hai loại ranh giới. Ví dụ, hệ thống đặt hàng gọi `PaymentAdapter` nội bộ, rồi adapter giao tiếp với cổng thanh toán bên ngoài. Tương tác giữa `OrderService` và `PaymentAdapter` là tích hợp giữa thành phần; giao tiếp từ adapter đến Payment Gateway là tích hợp giữa hệ thống.

## 5. Không nhầm tích hợp giữa hệ thống với kiểm thử hệ thống

Tên gọi gần nhau nhưng mục tiêu khác nhau:

- **Kiểm thử hệ thống (system testing):** đánh giá hệ thống hoàn chỉnh so với yêu cầu của chính hệ thống đó. Có thể bao gồm chức năng, hiệu năng, bảo mật, khả năng sử dụng và các thuộc tính chất lượng khác.
- **Kiểm thử tích hợp giữa hệ thống (system integration testing):** đánh giá tương tác giữa hệ thống này và các hệ thống khác ở ranh giới tích hợp.

Ví dụ, kiểm tra toàn bộ chức năng tạo đơn, tìm kiếm đơn và hủy đơn trong hệ thống đặt hàng là kiểm thử hệ thống. Kiểm tra đơn hàng được đồng bộ đúng sang WMS, thanh toán được ghi nhận từ cổng thanh toán và webhook được xử lý đúng là kiểm thử tích hợp giữa hệ thống.

Kiểm thử hệ thống có thể dùng các hệ thống phụ thuộc thật hoặc giả lập, tùy mục tiêu và môi trường. Điều quan trọng là báo cáo cần nói rõ điều gì đã được kiểm tra với phụ thuộc thật, điều gì dùng test double và ranh giới nào chưa có bằng chứng.

## 6. Thiết kế kiểm thử tích hợp giữa thành phần

Để có phạm vi rõ và dễ chẩn đoán, nhóm nên bắt đầu từ các giao diện và đường đi dữ liệu nội bộ.

### Xác định các tương tác quan trọng

Từ kiến trúc và yêu cầu, lập danh sách thành phần, trách nhiệm, đầu vào/đầu ra, trạng thái và phụ thuộc. Ưu tiên các đường đi có nhiều logic, thay đổi thường xuyên, dùng chung dữ liệu hoặc có hậu quả lớn nếu phối hợp sai.

### Xác định các trường hợp cần kiểm tra

- Luồng thành công giữa các thành phần.
- Giá trị rỗng, thiếu, sai kiểu, ngoài biên hoặc không nhất quán.
- Thành phần trả lỗi, ném ngoại lệ hoặc không phản hồi.
- Thứ tự gọi thay đổi hoặc một bước thất bại sau khi bước trước đã tạo trạng thái.
- Giao dịch commit/rollback, retry nội bộ và xử lý cạnh tranh.
- Cấu hình khác nhau hoặc phụ thuộc được thay thế.

### Chọn cách kết hợp thành phần thật và test double

Giữ các thành phần thuộc mục tiêu kiểm tra ở trạng thái thật để xác nhận tương tác. Thay thế các phụ thuộc ngoài phạm vi nếu cần cô lập lỗi hoặc tạo điều kiện khó tái lập. Đối với ranh giới quan trọng, bổ sung bài kiểm thử dùng phụ thuộc thật để tránh chỉ xác nhận hành vi của mock.

### Ghi nhận trạng thái và nguyên nhân

Khi test thất bại, lưu đầu vào, trạng thái trước/sau, kết quả mong đợi, kết quả thực tế, log và phiên bản build. Test tích hợp tốt cần giúp nhóm xác định lỗi nằm ở thành phần gọi, thành phần nhận, hợp đồng nội bộ hay cấu hình kết nối.

## 7. Thiết kế kiểm thử tích hợp giữa hệ thống

Tích hợp giữa hệ thống thường có nhiều phụ thuộc bên ngoài nhóm, vì vậy việc chuẩn bị hợp đồng, môi trường và dữ liệu rất quan trọng.

### Làm rõ hợp đồng và trách nhiệm hai phía

Với mỗi giao diện, ghi rõ:

- Ai là consumer và ai là provider.
- Endpoint, giao thức, phương thức xác thực và quyền.
- Schema, kiểu dữ liệu, đơn vị, trường bắt buộc và trường tùy chọn.
- Mã trạng thái, mã lỗi, định dạng lỗi và ý nghĩa nghiệp vụ.
- Timeout, retry, rate limit, idempotency và thứ tự xử lý.
- Quy tắc phiên bản, tương thích ngược và lịch thay đổi.
- Chủ sở hữu kỹ thuật và đầu mối phối hợp khi có sự cố.

Consumer-driven contract testing có thể giúp consumer mô tả những tương tác mà nó cần provider hỗ trợ. Provider có thể xác minh việc triển khai đáp ứng các hợp đồng đó. Contract test giúp phát hiện sai lệch giao diện sớm, nhưng không thay thế hoàn toàn kiểm thử end-to-end với hệ thống thật khi cần đánh giá mạng, cấu hình, bảo mật hoặc quy trình nghiệp vụ xuyên hệ thống.

### Chuẩn bị môi trường tích hợp

Xác nhận endpoint đúng môi trường, DNS, firewall, chứng thư TLS, tài khoản, khóa, secret, allowlist, phiên bản API và khả năng truy cập. Môi trường sandbox có thể khác production về dữ liệu, tải, tính năng và cách mô phỏng lỗi; cần ghi lại các khác biệt có ảnh hưởng đến kết quả.

Không ghi secret hoặc token thật vào mã nguồn, test report hay log. Dùng cơ chế quản lý bí mật được tổ chức phê duyệt và phân quyền tối thiểu cho tài khoản kiểm thử.

### Chuẩn bị dữ liệu và đối soát

Xác định cách tạo dữ liệu ở cả hai phía, mã định danh chung, quy tắc mapping, trạng thái đồng bộ và cách dọn dẹp. Với xử lý bất đồng bộ, cần xác định thời gian chờ hợp lý, điều kiện hoàn tất, cách nhận biết thông điệp trùng và cách đối soát khi hai hệ thống tạm thời không đồng nhất.

Ví dụ, một đơn hàng có thể được tạo trong hệ thống bán hàng trước khi WMS nhận sự kiện. Trong khoảng thời gian đó, hai hệ thống có thể thể hiện trạng thái khác nhau theo thiết kế eventual consistency. Test cần xác định thời hạn hội tụ và trạng thái trung gian hợp lệ, thay vì yêu cầu dữ liệu phải đồng nhất tức thời nếu kiến trúc không cam kết điều đó.

### Kiểm tra lỗi và khả năng phục hồi

Các tình huống cần xem xét gồm:

- Provider không khả dụng hoặc phản hồi chậm.
- Kết nối bị ngắt sau khi provider đã xử lý yêu cầu nhưng consumer chưa nhận phản hồi.
- Consumer gửi lại yêu cầu hoặc provider gửi lại sự kiện.
- Thông điệp đến sai thứ tự, đến trễ hoặc bị đưa vào dead-letter queue.
- Schema thay đổi, trường mới xuất hiện hoặc trường cũ bị loại bỏ.
- Token hết hạn, chứng thư hết hạn, quyền bị thu hồi hoặc rate limit bị kích hoạt.
- Một hệ thống thành công nhưng hệ thống còn lại thất bại, cần retry hoặc quy trình bù trừ.

Không nên mặc định retry luôn an toàn. Với thao tác tạo giao dịch hoặc cập nhật trạng thái, cần cơ chế idempotency hoặc cách đối soát để tránh xử lý trùng.

## 8. Ví dụ xuyên suốt: quy trình tạo và giao đơn hàng

Giả sử một nền tảng thương mại điện tử có hệ thống Order Management (OMS), Payment Gateway, Warehouse Management System (WMS) và dịch vụ vận chuyển. OMS điều phối quy trình đặt hàng, nhưng mỗi hệ thống có dữ liệu và vòng đời riêng.

### Phạm vi tích hợp giữa thành phần trong OMS

OMS có các thành phần `OrderService`, `PricingService`, `StockReservationAdapter` và `OrderRepository`. Nhóm kiểm tra:

1. `OrderService` gọi `PricingService` và nhận đúng tổng tiền.
2. Kết quả tính giá được truyền đúng sang bước tạo đơn.
3. Nếu repository không lưu được đơn, trạng thái điều phối và giữ hàng nội bộ được xử lý theo thiết kế.
4. Lỗi từ một thành phần được chuyển thành kết quả nghiệp vụ phù hợp.
5. Không tạo trạng thái đơn hàng không hợp lệ khi một bước giữa chừng thất bại.

Đây là kiểm thử tương tác bên trong OMS. Nhóm có thể dùng cơ sở dữ liệu test thật cho repository và stub cho phụ thuộc ngoài, miễn là ghi rõ giới hạn bằng chứng.

### Phạm vi tích hợp giữa các hệ thống

Nhóm kiểm tra các giao tiếp:

| Kết nối | Trường hợp chính | Lỗi hoặc tình huống biên |
|---|---|---|
| OMS ↔ Payment Gateway | Tạo yêu cầu thanh toán, nhận kết quả và webhook | Timeout, webhook lặp, chữ ký sai, giao dịch thành công nhưng phản hồi bị mất |
| OMS ↔ WMS | Giữ hàng, xác nhận xuất kho và nhận trạng thái | Hết hàng, sự kiện đến trễ, thông điệp trùng, WMS tạm ngừng |
| OMS ↔ Dịch vụ vận chuyển | Tạo vận đơn, nhận mã theo dõi và trạng thái giao | API giới hạn tốc độ, địa chỉ không hợp lệ, trạng thái giao sai thứ tự |

Nhóm cần kiểm tra hợp đồng, xác thực, mapping dữ liệu, xử lý lỗi, đối soát và kết quả nghiệp vụ xuyên hệ thống. Với mỗi giao dịch, nên dùng correlation ID hoặc mã tham chiếu có thể truy vết ở các hệ thống liên quan.

### Một kịch bản lỗi điển hình

1. OMS gửi yêu cầu thanh toán đến Payment Gateway.
2. Gateway xử lý thành công nhưng phản hồi bị timeout trên đường về.
3. OMS chưa biết giao dịch thành công nên có thể thử lại.
4. Gateway gửi webhook xác nhận giao dịch.
5. Webhook bị gửi lặp do lỗi mạng.

Kiểm thử cần xác nhận OMS không tạo thanh toán hoặc đơn hàng trùng, có thể liên kết webhook với yêu cầu ban đầu, xử lý retry an toàn và cuối cùng đưa trạng thái đơn về trạng thái đúng. Một test chỉ mock Gateway sẽ không chứng minh được hành vi thực tế của webhook, xác thực chữ ký hoặc cấu hình mạng; cần bổ sung kiểm thử sandbox hay kiểm thử tích hợp phù hợp.

## 9. Lựa chọn thứ tự và mức độ kiểm thử

Không phải dự án nào cũng cần chạy mọi kiểm tra ở mọi lần build. Có thể tổ chức theo lớp và rủi ro:

- Chạy kiểm thử tích hợp giữa thành phần sớm trong pipeline khi thay đổi các module liên quan.
- Chạy contract test khi consumer hoặc provider thay đổi giao diện.
- Chạy kiểm thử tích hợp hệ thống trong môi trường có đủ phụ thuộc và dữ liệu đại diện.
- Chạy các kịch bản xuyên hệ thống quan trọng trước mốc phát hành hoặc khi có thay đổi lớn ở quy trình.
- Bổ sung kiểm tra hiệu năng, bảo mật, phục hồi và tương thích theo rủi ro của kết nối.

Một số phép kiểm tra có thể chạy thường xuyên bằng môi trường mô phỏng; một số cần sandbox hoặc lịch phối hợp với đối tác. Kết quả phải ghi rõ môi trường, phiên bản của các bên, dữ liệu, điều kiện mạng và phụ thuộc được dùng.

### Tiêu chí hoàn tất

Với tích hợp giữa thành phần, tiêu chí có thể gồm:

- Các giao diện nội bộ quan trọng đã được kiểm tra với dữ liệu hợp lệ và không hợp lệ.
- Luồng thành công, lỗi, ngoại lệ và trạng thái giao dịch được xác minh.
- Các lỗi nghiêm trọng liên quan đến phối hợp thành phần đã được xử lý.
- Test có thể chạy lặp lại và kết quả gắn với phiên bản build.

Với tích hợp giữa hệ thống, tiêu chí có thể gồm:

- Hợp đồng, xác thực và giao tiếp với các hệ thống trong phạm vi đã được xác minh.
- Các luồng dữ liệu và trạng thái nghiệp vụ xuyên hệ thống được đối soát.
- Timeout, retry, lỗi phụ thuộc và xử lý sự kiện trùng/trễ đã được kiểm tra theo rủi ro.
- Giới hạn sandbox, hệ thống giả lập và phần chưa kiểm tra với hệ thống thật được ghi nhận.
- Có bằng chứng về quyền, bảo mật, khả năng quan sát và đầu mối xử lý lỗi.

Không nên dùng riêng tỷ lệ test pass để kết luận tích hợp đã hoàn tất. Một bộ test có thể pass nhưng chỉ kiểm tra luồng thành công hoặc dùng mock cho tất cả phụ thuộc. Cần xem xét ranh giới thực sự đã được kiểm tra và mức đại diện của môi trường.

## 10. Những sai lầm thường gặp

**Gọi mọi bài kiểm thử có nhiều module là system integration testing.** Cần xác định các phần có phải hệ thống độc lập theo ranh giới kiến trúc đã thống nhất hay không. Nếu chúng là các thành phần nội bộ, đó thường là component integration testing.

**Nhầm system integration testing với system testing.** System testing đánh giá hệ thống hoàn chỉnh so với yêu cầu; system integration testing đánh giá tương tác với hệ thống khác. Một bài test có thể làm cả hai, nhưng cần nêu rõ mục tiêu và bằng chứng.

**Chỉ kiểm tra đường đi thành công.** Tích hợp thường hỏng ở timeout, retry, lỗi xác thực, dữ liệu sai, thông điệp lặp hoặc sai thứ tự. Cần thiết kế trường hợp lỗi dựa trên hợp đồng và rủi ro.

**Dùng mock và coi đó là bằng chứng hệ thống thật tương thích.** Mock chỉ xác nhận cách thành phần gọi tương tác với mô hình đã lập trình. Cần contract test, sandbox hoặc kiểm tra với provider thật cho các ranh giới quan trọng.

**Không kiểm soát phiên bản của các bên.** Một test có thể thất bại hoặc pass khác nhau do provider thay đổi. Lưu phiên bản API, schema, cấu hình và thời điểm chạy để có thể điều tra.

**Bỏ qua dữ liệu và trạng thái bất đồng bộ.** Một sự kiện có thể đến trễ hoặc lặp; hai hệ thống có thể hội tụ sau một khoảng thời gian. Cần xác định trạng thái trung gian hợp lệ, thời hạn hội tụ và cách đối soát.

**Không có người sở hữu lỗi ở ranh giới.** Khi nhiều nhóm hoặc nhà cung cấp cùng tham gia, lỗi dễ bị chuyển qua lại. Xác định consumer, provider, chủ sở hữu giao diện và đầu mối phối hợp trước khi chạy.

**Không ghi rõ giới hạn môi trường.** Sandbox hoặc simulator không đại diện đầy đủ cho production. Hãy báo cáo phần đã kiểm tra, phần chưa kiểm tra và rủi ro còn lại.

## 11. Checklist lựa chọn và thực hiện kiểm thử tích hợp

Trước khi thiết kế:

- [ ] Ranh giới hệ thống và thành phần đã được thống nhất, có sơ đồ hoặc danh sách giao diện.
- [ ] Yêu cầu, luồng dữ liệu, trạng thái và rủi ro của từng kết nối đã được xác định.
- [ ] Đã phân biệt mục tiêu component integration, system integration và system testing.
- [ ] Consumer, provider và chủ sở hữu giao diện đã rõ.

Khi chuẩn bị:

- [ ] Hợp đồng, schema, phiên bản, xác thực và quyền truy cập đã được xác nhận.
- [ ] Môi trường, endpoint, chứng thư, secret, dữ liệu và công cụ mô phỏng đã sẵn sàng.
- [ ] Có kịch bản thành công, lỗi, timeout, retry, dữ liệu biên và xử lý bất đồng bộ phù hợp.
- [ ] Có cách truy vết và đối soát giao dịch giữa các thành phần/hệ thống.

Khi thực hiện và kết thúc:

- [ ] Bằng chứng được lưu cùng build, phiên bản phụ thuộc, cấu hình và môi trường.
- [ ] Các lỗi và trạng thái trung gian được kiểm tra theo rủi ro.
- [ ] Giới hạn của mock, sandbox và môi trường được ghi nhận.
- [ ] Lỗi nghiêm trọng có chủ sở hữu và phương án xử lý.
- [ ] Tiêu chí hoàn tất và rủi ro tồn dư được xem xét trước quyết định phát hành.

## 12. Tự kiểm tra mức độ hiểu

**Tình huống 1:** `OrderService` gọi `PricingComponent` và `OrderRepository` trong cùng ứng dụng. Nhóm kiểm tra dữ liệu tính giá được lưu đúng và lỗi repository không để lại trạng thái đơn sai. Đây là tích hợp giữa thành phần vì ranh giới được kiểm tra nằm bên trong một hệ thống.

**Tình huống 2:** Hệ thống đặt hàng gửi yêu cầu đến cổng thanh toán do nhà cung cấp vận hành, sau đó nhận webhook. Nhóm kiểm tra hợp đồng, chữ ký, timeout, retry và trạng thái giao dịch. Đây là tích hợp giữa hệ thống vì giao tiếp vượt qua ranh giới của một hệ thống độc lập.

**Tình huống 3:** Nhóm kiểm tra toàn bộ chức năng tạo, tìm kiếm và hủy đơn trong ứng dụng đặt hàng. Mục tiêu là đánh giá hệ thống hoàn chỉnh theo yêu cầu, nên đây là kiểm thử hệ thống. Nếu test tập trung vào việc đơn hàng đồng bộ sang WMS đúng hay không, đó là kiểm thử tích hợp giữa hệ thống.

**Tình huống 4:** Một microservice trong cùng sản phẩm được triển khai độc lập và có API riêng. Tùy ranh giới đã thống nhất, kiểm tra tương tác giữa service này và service khác có thể được phân loại là tích hợp giữa hệ thống ở góc nhìn các đơn vị triển khai độc lập. Tài liệu kế hoạch cần nói rõ cách phân loại và phạm vi thay vì dựa vào tên “microservice”.

**Tình huống 5:** Test tích hợp với sandbox thanh toán đều pass nhưng production gặp lỗi chứng thư TLS. Điều này cho thấy bằng chứng sandbox chưa bao phủ đầy đủ cấu hình production. Nhóm cần bổ sung kiểm tra cấu hình, chứng thư và kết nối ở môi trường đích theo cách an toàn.

Khi thiết kế một bài kiểm thử tích hợp, hãy tự hỏi: **hai phía đang giao tiếp có phải các thành phần trong cùng hệ thống hay hai hệ thống độc lập, giao diện nào đang được kiểm tra và bằng chứng nào xác nhận dữ liệu cùng trạng thái được phối hợp đúng?** Trả lời rõ giúp chọn đúng loại kiểm thử và tránh kết luận vượt quá phạm vi đã thực hiện.

## Kết luận

Tích hợp giữa thành phần kiểm tra sự phối hợp của các phần bên trong một hệ thống; tích hợp giữa hệ thống kiểm tra giao tiếp và quy trình giữa các hệ thống độc lập. Cả hai đều cần xác nhận giao diện, dữ liệu, trạng thái và xử lý lỗi, nhưng khác nhau về ranh giới, phụ thuộc, môi trường và cách phối hợp. Khi xác định rõ ranh giới kiến trúc, chọn test theo rủi ro, chuẩn bị hợp đồng và dữ liệu, kiểm tra cả lỗi lẫn luồng thành công và ghi nhận giới hạn bằng chứng, nhóm có thể đánh giá chất lượng tích hợp một cách đáng tin cậy hơn.
