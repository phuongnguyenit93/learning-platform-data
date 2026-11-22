# Xây dựng bảng thuật ngữ gắn với ngữ cảnh và ví dụ sử dụng

Trong một tổ chức, cùng một từ có thể được dùng bởi nhiều nhóm nhưng mang những ý nghĩa khác nhau. Nhóm bán hàng nói đến “đơn hàng” như một cam kết mua bán với khách hàng. Nhóm kho vận có thể dùng “đơn” để chỉ yêu cầu lấy hàng, đóng gói và giao hàng. Nhóm thanh toán lại quan tâm đến khoản tiền cần thu, lần thử thanh toán và giao dịch hoàn tiền. Nếu đội phát triển đưa tất cả những cách hiểu này vào một mô hình chung mà không làm rõ ranh giới, các quy tắc nghiệp vụ dễ bị trộn lẫn.

Trong Domain-Driven Design (DDD), *Ubiquitous Language* (ngôn ngữ chung) là ngôn ngữ được chuyên gia nghiệp vụ và đội phát triển cùng sử dụng khi trao đổi, mô hình hóa, viết tài liệu và đặt tên trong mã nguồn. Một bảng thuật ngữ (*glossary*) giúp ghi lại những từ quan trọng, định nghĩa đã thống nhất và ví dụ cho thấy cách dùng từ trong một tình huống cụ thể.

Tuy nhiên, bảng thuật ngữ của DDD phải gắn với phạm vi ngữ cảnh. Một thuật ngữ có ý nghĩa rõ ràng trong một *Bounded Context* (ranh giới ngữ cảnh) có thể mang ý nghĩa khác trong ngữ cảnh khác. Mục tiêu của bảng thuật ngữ là giúp mọi người hiểu và dùng đúng từ trong phạm vi đang làm việc, đồng thời nhận biết nơi cần chuyển đổi cách hiểu khi các ngữ cảnh giao tiếp với nhau.

Sau bài học này, bạn có thể:

- Giải thích vì sao một bảng thuật ngữ cần ghi rõ ngữ cảnh sử dụng.
- Xác định những thuật ngữ, định nghĩa, ví dụ và quan hệ cần có trong một mục từ.
- Xây dựng bảng thuật ngữ từ trao đổi với chuyên gia nghiệp vụ và các tình huống thực tế.
- Phát hiện từ mơ hồ, từ đồng nghĩa và trường hợp một từ có nghĩa khác nhau giữa các Bounded Context.
- Duy trì bảng thuật ngữ đồng bộ với mô hình, mã nguồn và giao tiếp giữa các nhóm.

## 1. Bảng thuật ngữ trong DDD giải quyết vấn đề gì?

Ngôn ngữ là công cụ để con người trao đổi về domain. Khi mỗi người dùng một từ theo cách hiểu riêng, cuộc trao đổi có thể nghe có vẻ thống nhất nhưng dẫn đến những quyết định khác nhau.

Ví dụ, trong một cuộc họp về thương mại điện tử, một người nói: “Đơn đã hoàn tất”. Câu nói này có thể được hiểu theo nhiều cách:

- Đơn hàng đã được khách hàng đặt thành công.
- Đơn hàng đã được thanh toán đủ.
- Hàng đã được đóng gói và bàn giao cho đơn vị vận chuyển.
- Khách hàng đã nhận hàng.
- Thời hạn đổi trả đã kết thúc và đơn được đóng hồ sơ.

Nếu đội phát triển chỉ tạo một trạng thái `COMPLETED`, phần mềm sẽ không thể hiện rõ người nói đang đề cập đến mốc nào. Các nhóm có thể cùng dùng một từ nhưng mong đợi những hành vi khác nhau.

Bảng thuật ngữ giúp:

**Thống nhất ý nghĩa.** Mỗi thuật ngữ quan trọng có một định nghĩa được xác nhận trong phạm vi cụ thể. Khi trao đổi về thuật ngữ đó, mọi người có một điểm tham chiếu chung.

**Làm rõ ranh giới.** Bảng ghi nhận thuật ngữ thuộc Bounded Context nào. Điều này giúp tránh giả định rằng mô hình của một nhóm phải được dùng nguyên vẹn bởi mọi nhóm khác.

**Gắn từ với hành vi.** Ví dụ sử dụng cho thấy thuật ngữ xuất hiện trong câu nói, quy trình, quyết định, sự kiện hoặc quy tắc nào. Định nghĩa vì vậy dễ kiểm chứng hơn một câu mô tả trừu tượng.

**Phát hiện mâu thuẫn sớm.** Từ đồng nghĩa, từ đa nghĩa, cách gọi không thống nhất và những khác biệt giữa các nhóm được đưa ra thảo luận trước khi trở thành lỗi trong thiết kế.

**Giữ mô hình và mã nguồn dễ hiểu.** Khi thuật ngữ được thống nhất, tên lớp, thuộc tính, phương thức, sự kiện domain và API có thể phản ánh đúng cách tổ chức hiểu về nghiệp vụ.

Bảng thuật ngữ không thay thế cuộc trao đổi với chuyên gia nghiệp vụ. Nó lưu lại kết quả đã được làm rõ để nhóm có thể sử dụng nhất quán và tiếp tục điều chỉnh khi hiểu biết về domain thay đổi.

## 2. Vì sao phải gắn thuật ngữ với ngữ cảnh?

Trong DDD, *Bounded Context* là ranh giới mà bên trong đó một mô hình domain và ngôn ngữ của nó có ý nghĩa nhất quán. Ranh giới này thường gắn với một năng lực nghiệp vụ, trách nhiệm của nhóm hoặc một phần hệ thống. Một tổ chức có thể có nhiều Bounded Context, mỗi context giải quyết một phần bài toán với mô hình riêng.

Do đó, không nên mặc định rằng một thuật ngữ chỉ có một định nghĩa duy nhất cho toàn doanh nghiệp. Ví dụ, từ “Sản phẩm” có thể được hiểu như sau:

| Ngữ cảnh | Thuật ngữ | Ý nghĩa trong ngữ cảnh |
|---|---|---|
| Product Catalog | Product (Sản phẩm) | Định nghĩa mặt hàng được doanh nghiệp cung cấp, gồm tên, mô tả, thuộc tính và các lựa chọn bán |
| Sales | Order Line Product (Sản phẩm trên dòng đơn hàng) | Thông tin sản phẩm được ghi nhận tại thời điểm khách mua, có thể bao gồm tên và giá đã chốt |
| Fulfillment | Stock Item (Mặt hàng tồn kho) | Đơn vị vật lý hoặc mã hàng mà kho cần tìm, lấy và đóng gói |

Ba cách hiểu có liên quan đến cùng một mặt hàng nhưng phục vụ các quyết định khác nhau. Catalog quan tâm đến thông tin được công bố và khả năng bán. Sales cần biết khách đã đồng ý mua thứ gì với mức giá nào. Fulfillment cần xác định chính xác mặt hàng vật lý cần lấy khỏi kho.

Tương tự, “Đơn hàng” có thể chỉ một cam kết mua bán trong Sales Context, trong khi Fulfillment Context có một yêu cầu thực hiện việc giao hàng. Hai đối tượng có quan hệ với nhau nhưng không nhất thiết có cùng vòng đời hoặc cùng quy tắc.

### Phân biệt bảng thuật ngữ, từ điển dữ liệu và tài liệu API

Các loại tài liệu này có thể liên kết với nhau nhưng trả lời những câu hỏi khác nhau:

| Tài liệu | Câu hỏi chính | Nội dung điển hình |
|---|---|---|
| Bảng thuật ngữ domain | Từ này có nghĩa gì trong ngữ cảnh nghiệp vụ? | Định nghĩa, ngữ cảnh, ví dụ, thuật ngữ liên quan và cách dùng được chấp nhận |
| Từ điển dữ liệu | Trường dữ liệu này lưu giá trị gì và có cấu trúc ra sao? | Tên cột, kiểu dữ liệu, miền giá trị, ràng buộc và nguồn dữ liệu |
| Tài liệu API | Thành phần khác gọi giao diện này như thế nào? | Endpoint, request, response, mã lỗi, xác thực và phiên bản |

Ví dụ, bảng thuật ngữ giải thích “Ngày giao thành công” là thời điểm đơn vị vận chuyển xác nhận đã bàn giao hàng cho người nhận theo quy tắc của Fulfillment Context. Từ điển dữ liệu có thể mô tả trường `delivered_at` là thời điểm UTC được lưu trong cơ sở dữ liệu. Tài liệu API mô tả trường này được trả về trong response nào và có thể vắng mặt khi nào.

Nếu chỉ có tên trường `status` hoặc `delivered_at`, người đọc vẫn có thể không hiểu ý nghĩa nghiệp vụ của dữ liệu. Bảng thuật ngữ bổ sung phần ý nghĩa đó.

## 3. Một mục từ nên có những thông tin nào?

Không cần biến bảng thuật ngữ thành một bộ tài liệu nặng nề. Một mục từ tốt cần đủ thông tin để người đọc hiểu thuật ngữ được dùng ở đâu, có nghĩa gì và nên sử dụng như thế nào.

Có thể bắt đầu với cấu trúc sau:

| Trường | Nội dung cần ghi | Mục đích |
|---|---|---|
| Thuật ngữ chuẩn | Tên được nhóm thống nhất sử dụng | Tạo một cách gọi nhất quán trong context |
| Ngữ cảnh | Tên Bounded Context hoặc phạm vi nghiệp vụ | Giới hạn nơi định nghĩa có hiệu lực |
| Định nghĩa | Ý nghĩa nghiệp vụ ngắn gọn, rõ ràng | Trả lời thuật ngữ đại diện cho điều gì |
| Ví dụ sử dụng | Câu nói, tình huống, quy tắc hoặc sự kiện có dùng thuật ngữ | Kiểm tra định nghĩa trong thực tế |
| Không bao gồm / phân biệt | Khái niệm dễ nhầm hoặc trường hợp không thuộc định nghĩa | Tránh mở rộng nghĩa ngoài ý muốn |
| Thuật ngữ liên quan | Các khái niệm có quan hệ trực tiếp | Giúp hiểu thuật ngữ trong mô hình |
| Tên trong mã nguồn (nếu có) | Tên lớp, kiểu, phương thức hoặc event đã thống nhất | Kết nối ngôn ngữ nghiệp vụ với mã nguồn |

Với nhóm nhỏ, có thể chỉ cần bốn trường đầu tiên và bổ sung các trường còn lại khi có nhu cầu. Không phải thuật ngữ nào cũng cần có tên lớp hoặc event tương ứng.

### Mẫu một mục từ

```text
Thuật ngữ: Order (Đơn hàng)
Ngữ cảnh: Sales
Định nghĩa:
  Cam kết mua bán được ghi nhận khi hệ thống chấp nhận
  yêu cầu đặt mua của khách hàng theo chính sách bán hàng.

Ví dụ sử dụng:
  "Order ORD-1042 đã được xác nhận với hai dòng hàng."
  "Đơn hàng chỉ được hủy khi chưa chuyển sang trạng thái xử lý
   mà chính sách bán hàng không cho phép hủy."

Không bao gồm:
  Yêu cầu lấy hàng và giao hàng thuộc Fulfillment Context.

Thuật ngữ liên quan:
  Order Line, Order Placed, Order Cancellation.

Tên trong mã nguồn:
  Order, OrderPlaced.
```

Định nghĩa trên là ví dụ minh họa. Một tổ chức cần điều chỉnh nó theo chính sách và cách vận hành thực tế của mình. Điểm quan trọng là định nghĩa có ranh giới: Order thuộc Sales Context và có điều kiện được chấp nhận cụ thể.

## 4. Xây dựng bảng thuật ngữ từ trao đổi nghiệp vụ

Bảng thuật ngữ nên được hình thành từ ngôn ngữ mà chuyên gia và đội phát triển thực sự sử dụng. Nếu chỉ một kỹ sư tự đặt tên rồi ghi vào tài liệu, kết quả có thể nhất quán về mặt kỹ thuật nhưng không phản ánh đúng cách nghiệp vụ hoạt động.

### Bước 1: Chọn ngữ cảnh và phạm vi

Trước tiên, xác định nhóm đang mô hình hóa phần nghiệp vụ nào. Phạm vi có thể là Sales, Payment, Fulfillment hoặc một Bounded Context cụ thể khác.

Không nên bắt đầu bằng yêu cầu “lập từ điển cho toàn công ty” khi chưa xác định được ai sử dụng mô hình và quyết định nào cần hỗ trợ. Một phạm vi rõ giúp cuộc thảo luận đi sâu vào thuật ngữ và quy tắc thực tế.

Hãy ghi nhận:

- Bounded Context đang được xem xét.
- Năng lực nghiệp vụ hoặc quy trình mà context chịu trách nhiệm.
- Những nhóm và chuyên gia tham gia xác nhận thuật ngữ.
- Những ngữ cảnh bên ngoài có trao đổi dữ liệu hoặc sự kiện với context này.

### Bước 2: Thu thập từ trong các tình huống thực tế

Hãy quan sát cách chuyên gia mô tả công việc, xử lý ngoại lệ và giải thích quyết định. Có thể dùng phỏng vấn, workshop, Event Storming, phân tích quy trình, câu chuyện người dùng và ví dụ từ các giao dịch đã xảy ra.

Đừng chỉ thu thập danh từ. Ngôn ngữ domain còn bao gồm:

- **Danh từ:** Order, Customer, Shipment, Invoice.
- **Hành động:** Place Order, Capture Payment, Dispatch Shipment.
- **Trạng thái:** Pending Approval, Paid, Dispatched, Delivered.
- **Sự kiện:** Order Placed, Payment Captured, Shipment Delivered.
- **Chính sách và quy tắc:** Return Policy, Credit Limit, Free Shipping Eligibility.
- **Đơn vị và khái niệm đo lường:** Billable Weight, Available Quantity, Settlement Amount.

Các động từ đặc biệt hữu ích vì chúng thể hiện hành vi và quyết định. Nếu mọi người chỉ thống nhất danh từ nhưng không làm rõ “xác nhận”, “chấp thuận”, “ghi nhận” hay “hoàn tất” có nghĩa gì, mô hình vẫn dễ mơ hồ.

### Bước 3: Phát hiện từ mơ hồ và cách gọi khác nhau

Khi một thuật ngữ xuất hiện, hãy hỏi:

- Người nói đang dùng từ này để chỉ đối tượng, hành động, trạng thái hay sự kiện nào?
- Từ này có nghĩa giống nhau trong mọi tình huống không?
- Nhóm khác có dùng một từ khác cho cùng khái niệm không?
- Có từ nào giống nhau nhưng đại diện cho hai khái niệm khác nhau không?
- Có trường hợp nào mà thuật ngữ này không áp dụng không?

Ví dụ, “khách hàng” có thể là người đặt mua, người thanh toán hoặc người nhận hàng. Trong một giao dịch mua quà tặng, ba vai trò này có thể thuộc về ba người khác nhau. Nếu hệ thống chỉ có một trường `customer`, định nghĩa nghiệp vụ cần được làm rõ trước khi chọn mô hình dữ liệu.

### Bước 4: Viết định nghĩa có ranh giới

Một định nghĩa nên ngắn nhưng phải chỉ ra được bản chất và giới hạn của thuật ngữ. Tránh dùng một từ mơ hồ khác để giải thích từ đang được định nghĩa.

Ví dụ chưa đủ rõ:

> Đơn hàng là một đơn được khách hàng tạo ra.

Định nghĩa này lặp lại chính thuật ngữ cần giải thích và không cho biết khi nào một yêu cầu trở thành đơn hàng.

Ví dụ rõ hơn trong Sales Context:

> Đơn hàng là cam kết mua bán được hệ thống ghi nhận sau khi yêu cầu đặt mua vượt qua các kiểm tra và được chấp nhận theo chính sách bán hàng.

Định nghĩa thứ hai làm rõ thời điểm hình thành Order và liên hệ của nó với chính sách chấp nhận đơn. Nếu trong doanh nghiệp có nhiều loại đơn với quy tắc khác nhau, cần ghi rõ loại đơn hoặc tạo thuật ngữ cụ thể hơn.

### Bước 5: Thêm ví dụ và phản ví dụ

Ví dụ sử dụng kiểm tra xem định nghĩa có phù hợp với tình huống thật hay không. Phản ví dụ giúp chỉ ra điều không thuộc khái niệm, nhất là với những từ thường bị dùng lẫn.

Ví dụ với thuật ngữ `Shipment` trong Fulfillment Context:

- Ví dụ: “Shipment SH-902 đã được bàn giao cho hãng vận chuyển và có mã theo dõi.”
- Phản ví dụ: “Order ORD-1042 đã được thanh toán” không chứng minh shipment đã được tạo hoặc đã rời kho.

Nếu một thuật ngữ không thể tạo ra câu ví dụ mà các thành viên đều hiểu giống nhau, hãy tiếp tục thảo luận thay vì vội đưa nó vào danh sách thuật ngữ đã thống nhất.

### Bước 6: Xác nhận bằng kịch bản và mô hình

Đọc lại các mục từ cùng chuyên gia nghiệp vụ bằng một quy trình cụ thể. Hãy kiểm tra cả luồng bình thường lẫn ngoại lệ. Sau đó xem các thuật ngữ có phù hợp với:

- Quy tắc và quyết định nghiệp vụ.
- Trạng thái và chuyển đổi trạng thái.
- Tên lệnh, sự kiện domain và các đối tượng trong mô hình.
- Tài liệu và hợp đồng giao tiếp giữa các Bounded Context.

Nếu định nghĩa nói “Order chỉ được tạo sau khi thanh toán thành công” nhưng kịch bản cho phép đặt hàng trước rồi thanh toán sau, định nghĩa hoặc mô hình đang mâu thuẫn với thực tế. Nhóm cần sửa và xác nhận lại.

## 5. Ví dụ bảng thuật ngữ cho hệ thống thương mại điện tử

Giả sử một doanh nghiệp thương mại điện tử tổ chức công việc thành ba Bounded Context minh họa: Sales, Payment và Fulfillment. Đây chỉ là một cách phân chia để giải thích; ranh giới thực tế phụ thuộc vào tổ chức và trách nhiệm của từng nhóm.

### 5.1. Các thuật ngữ trong Sales Context

| Thuật ngữ | Định nghĩa | Ví dụ sử dụng |
|---|---|---|
| Order (Đơn hàng) | Cam kết mua bán được ghi nhận khi yêu cầu đặt mua được chấp nhận theo chính sách bán hàng | “Order ORD-1042 gồm hai dòng hàng và có tổng tiền đã chốt.” |
| Order Line (Dòng đơn hàng) | Một dòng hàng trong Order, ghi nhận mặt hàng, số lượng và điều kiện giá đã chấp nhận | “Order Line 2 có số lượng là hai.” |
| Order Placed (Đơn hàng được đặt) | Sự kiện cho biết hệ thống đã chấp nhận và ghi nhận một Order | “OrderPlaced được phát ra sau khi đơn vượt qua các kiểm tra cần thiết.” |
| Order Cancellation (Hủy đơn hàng) | Quy trình kết thúc cam kết mua bán theo điều kiện hủy của Sales | “Yêu cầu hủy bị từ chối vì đơn đã qua mốc không thể hủy.” |

### 5.2. Các thuật ngữ trong Payment Context

| Thuật ngữ | Định nghĩa | Ví dụ sử dụng |
|---|---|---|
| Payment (Thanh toán) | Hồ sơ xử lý việc thu tiền cho một nghĩa vụ thanh toán được tham chiếu từ giao dịch bán hàng | “Payment PAY-81 đang chờ kết quả từ nhà cung cấp.” |
| Payment Attempt (Lần thử thanh toán) | Một lần gửi yêu cầu xử lý thanh toán đến phương thức hoặc nhà cung cấp thanh toán | “Payment PAY-81 có lần thử thứ hai sau khi lần đầu bị từ chối.” |
| Capture (Thu tiền) | Hành động ghi nhận việc thu một khoản tiền đã được cho phép theo quy trình thanh toán | “Payment đã được capture với số tiền 500.000 đồng.” |
| Refund (Hoàn tiền) | Giao dịch trả lại toàn bộ hoặc một phần khoản tiền đã thu theo điều kiện hoàn tiền | “Refund RF-18 hoàn lại 100.000 đồng cho giao dịch ban đầu.” |

Trong ví dụ này, một Payment có thể có nhiều Payment Attempt. Vì vậy, không nên dùng hai thuật ngữ này thay thế cho nhau. Một lần thử thất bại không nhất thiết có nghĩa toàn bộ nghĩa vụ thanh toán đã thất bại vĩnh viễn.

### 5.3. Các thuật ngữ trong Fulfillment Context

| Thuật ngữ | Định nghĩa | Ví dụ sử dụng |
|---|---|---|
| Fulfillment Order (Yêu cầu thực hiện đơn) | Yêu cầu nội bộ để chuẩn bị và giao một phần hoặc toàn bộ hàng đã bán | “Fulfillment Order FO-32 được phân công cho kho phía Bắc.” |
| Picking (Lấy hàng) | Hoạt động tìm và lấy đúng mặt hàng, số lượng theo yêu cầu thực hiện | “Picking hoàn tất khi các mặt hàng trong danh sách đã được lấy đủ hoặc ghi nhận thiếu hàng.” |
| Shipment (Lô giao hàng) | Đơn vị hàng hóa được đóng gói và bàn giao để vận chuyển, có thông tin theo dõi riêng | “Shipment SH-902 đã được bàn giao cho hãng vận chuyển.” |
| Delivered (Đã giao) | Trạng thái xác nhận hàng đã được bàn giao cho người nhận theo bằng chứng giao hàng được chấp nhận | “Shipment chuyển sang Delivered sau khi nhận xác nhận giao thành công.” |

Các mục từ trên cho thấy một Order trong Sales có thể dẫn đến một hoặc nhiều Fulfillment Order, và một Fulfillment Order có thể được thực hiện qua một hoặc nhiều Shipment tùy cách vận hành. Những quan hệ này cần được xác nhận trong domain thực tế; không nên suy ra từ tên gọi.

### 5.4. Bảng đối chiếu thuật ngữ giữa các ngữ cảnh

Một số từ xuất hiện ở nhiều nơi nhưng không có cùng định nghĩa. Bảng đối chiếu giúp các nhóm hiểu dữ liệu và thông điệp khi trao đổi qua ranh giới context.

| Từ thường gặp | Sales | Payment | Fulfillment |
|---|---|---|---|
| Order | Cam kết mua bán được chấp nhận | Tham chiếu đến nghĩa vụ cần thu tiền | Nguồn tạo yêu cầu thực hiện và giao hàng |
| Customer | Người hoặc tổ chức thực hiện giao dịch mua | Bên có nghĩa vụ hoặc phương thức thanh toán được đăng ký | Có thể là người đặt yêu cầu; người nhận hàng có thể khác |
| Amount | Giá trị bán hàng hoặc số tiền khách phải trả theo Order | Số tiền được yêu cầu thu, đã thu hoặc hoàn | Có thể không phải khái niệm chính; Fulfillment quan tâm đến số lượng và mặt hàng |

Đây là bảng đối chiếu cách hiểu, không phải yêu cầu mọi context phải chia sẻ cùng một lớp `Order`, `Customer` hoặc `Amount`. Khi trao đổi, mỗi context cần xác định rõ dữ liệu nào được gửi, dữ liệu nào được tiếp nhận và cách diễn giải chúng trong mô hình của mình.

## 6. Biến ngôn ngữ đã thống nhất thành tên trong mô hình và mã nguồn

Một bảng thuật ngữ chỉ có ích lâu dài khi ngôn ngữ đó được sử dụng trong công việc hằng ngày. Đội phát triển nên dùng các thuật ngữ đã xác nhận khi đặt tên đối tượng, hành vi, trạng thái và sự kiện domain.

Ví dụ, trong Sales Context:

```java
public class Order {
    private OrderId id;
    private List<OrderLine> lines;
    private OrderStatus status;

    public void cancel(CancellationReason reason) {
        // Kiểm tra chính sách và điều kiện hủy của Order.
    }
}
```

Tên `Order`, `OrderLine`, `OrderStatus` và `CancellationReason` thể hiện các khái niệm đã được xác định trong ngữ cảnh Sales. Tên phương thức `cancel` diễn đạt hành động nghiệp vụ mà đối tượng hỗ trợ. Phần thân mã chỉ mang tính minh họa; quy tắc cụ thể phải đến từ chính sách thực tế.

Khi một sự kiện được phát ra, tên sự kiện nên mô tả sự việc đã xảy ra:

```text
OrderPlaced
OrderCancelled
PaymentCaptured
RefundIssued
ShipmentDispatched
ShipmentDelivered
```

Những tên này giúp người đọc nhận ra sự kiện thuộc về hành vi nào. Cần phân biệt sự kiện đã xảy ra với yêu cầu thực hiện hành động. Ví dụ, `CancelOrder` có thể là một command yêu cầu hủy đơn; `OrderCancelled` là sự kiện xác nhận đơn đã được hủy. Đổi hai tên này cho nhau sẽ làm mờ khác biệt giữa ý định và kết quả.

Khi tên trong mã nguồn khác với thuật ngữ trong bảng, hãy kiểm tra xem đó là khác biệt có chủ đích hay dấu hiệu của ngôn ngữ chưa thống nhất. Không nhất thiết mọi từ nghiệp vụ phải được ánh xạ một-một thành một lớp. Tuy vậy, nếu một khái niệm quan trọng được gọi bằng nhiều tên trong cùng context, nhóm nên thống nhất cách gọi hoặc ghi rõ lý do.

## 7. Xử lý từ đồng nghĩa, từ đa nghĩa và thuật ngữ thay đổi

### Từ đồng nghĩa trong cùng một ngữ cảnh

Một khái niệm có thể được gọi bằng nhiều từ như “hủy đơn”, “xóa đơn” và “bỏ đơn”. Những từ này nghe gần giống nhau nhưng có thể mô tả hành vi khác nhau:

- Hủy đơn: kết thúc một Order đã được ghi nhận theo chính sách, đồng thời giữ lại lịch sử.
- Xóa bản nháp: loại bỏ một đối tượng chưa trở thành Order chính thức.
- Bỏ qua dòng hàng: loại một Order Line khỏi bản nháp trước khi đặt mua.

Nếu các hành vi khác nhau, hãy dùng thuật ngữ riêng và ghi rõ định nghĩa. Nếu chúng thực sự cùng chỉ một khái niệm, chọn một thuật ngữ chuẩn; các cách gọi khác được ghi ở phần từ đồng nghĩa để người đọc tra cứu, nhưng không dùng lẫn trong mô hình và trao đổi thường ngày.

### Một từ có nhiều nghĩa

Các từ như “hoàn tất”, “xác nhận”, “đã xử lý” hoặc “thành công” thường quá rộng. Hãy hỏi trạng thái nào đã thay đổi, sự kiện nào đã xảy ra và ai xác nhận kết quả.

Thay vì ghi `Completed`, có thể cần các thuật ngữ cụ thể hơn như `PaymentCaptured`, `ShipmentDispatched`, `ShipmentDelivered` hoặc `ReturnClosed`, tùy domain. Không nên chọn tên mới chỉ để làm mã nguồn dài hơn; tên phải phân biệt được các mốc có ý nghĩa nghiệp vụ khác nhau.

### Thuật ngữ khác nhau giữa các ngữ cảnh

Nếu Sales gọi là `Order` và Fulfillment gọi là `Fulfillment Order`, điều đó có thể phản ánh đúng trách nhiệm riêng của mỗi context. Không cần ép hai nhóm dùng chung một định nghĩa. Thay vào đó, bảng thuật ngữ ghi rõ mối quan hệ và tài liệu tích hợp giải thích cách chuyển thông tin giữa hai mô hình.

Khi có thay đổi, hãy xác định phạm vi ảnh hưởng:

1. Định nghĩa mới áp dụng cho một context hay nhiều context?
2. Đây là thay đổi tên gọi hay thay đổi ý nghĩa nghiệp vụ?
3. Mô hình, dữ liệu, API hoặc sự kiện đã phát hành có cần tương thích với cách hiểu cũ không?
4. Những nhóm nào cần xác nhận và cập nhật tài liệu?

Thay đổi định nghĩa thường có ảnh hưởng lớn hơn thay đổi cách viết. Nếu “Customer” từ nay chỉ người trả tiền thay vì người đặt mua, các quy tắc và dữ liệu liên quan có thể cần xem xét lại.

## 8. Dùng bảng thuật ngữ tại ranh giới giữa các Bounded Context

Khi hai context trao đổi, thuật ngữ của context gửi không tự động mang cùng ý nghĩa trong context nhận. Ví dụ, Sales có thể phát sự kiện `OrderPlaced` với mã đơn, các dòng hàng và địa chỉ giao hàng. Fulfillment tiếp nhận thông tin đó để tạo yêu cầu thực hiện theo mô hình riêng.

Luồng khái niệm:

```text
Sales Context
  Order được chấp nhận
       |
       | OrderPlaced
       v
Integration Boundary
  Kiểm tra và chuyển đổi thông tin cần thiết
       |
       v
Fulfillment Context
  Tạo Fulfillment Order
  Phân công kho và chuẩn bị hàng
```

Ở ranh giới này, nhóm cần làm rõ:

- `OrderPlaced` biểu thị sự kiện nào và điều kiện phát ra là gì?
- Mã Order có ý nghĩa gì trong Sales và được Fulfillment lưu làm tham chiếu như thế nào?
- Sales gửi địa chỉ giao hàng đã chốt hay chỉ gửi mã tham chiếu đến địa chỉ?
- Fulfillment có thể từ chối hoặc chỉ thực hiện một phần yêu cầu trong trường hợp nào?
- Nếu thông tin được thay đổi sau khi sự kiện phát ra, context nhận được thông báo bằng cách nào?

Việc chuyển đổi có thể được thực hiện qua một lớp dịch, adapter hoặc cơ chế tích hợp phù hợp với Context Map. Bảng thuật ngữ giúp các nhóm biết từ nào thuộc mô hình nguồn, từ nào thuộc mô hình đích và quan hệ giữa chúng. Nó không tự thay thế hợp đồng tích hợp, nhưng làm cho hợp đồng đó dễ hiểu hơn.

## 9. Duy trì bảng thuật ngữ như một phần của công việc

Bảng thuật ngữ là tài liệu sống. Domain có thể thay đổi khi doanh nghiệp bổ sung sản phẩm, chính sách hoặc quy trình. Nếu thuật ngữ thay đổi nhưng bảng không được cập nhật, tài liệu sẽ nhanh chóng mất giá trị.

Một số thực hành hữu ích:

- **Có người chịu trách nhiệm:** mỗi Bounded Context nên có người điều phối việc cập nhật và người có thẩm quyền nghiệp vụ xác nhận định nghĩa.
- **Cập nhật khi mô hình thay đổi:** khi thêm trạng thái, quy tắc, command hoặc domain event mới, kiểm tra xem có thuật ngữ nào cần bổ sung hoặc điều chỉnh.
- **Đưa thuật ngữ vào thảo luận:** trong refinement, review thiết kế và review mã nguồn, hỏi xem tên gọi có phản ánh đúng định nghĩa đã thống nhất không.
- **Giữ lịch sử thay đổi:** với thuật ngữ quan trọng, ghi ngày thay đổi, lý do và context bị ảnh hưởng để giải thích các quyết định cũ.
- **Dễ tìm và dễ sửa:** đặt bảng ở nơi các thành viên sử dụng hằng ngày, hỗ trợ tìm kiếm và cho phép đề xuất thay đổi.
- **Không ghi mọi từ thông thường:** ưu tiên thuật ngữ ảnh hưởng đến quy tắc, quyết định, trạng thái, sự kiện hoặc giao tiếp giữa các nhóm.

Trong thực tế, một thuật ngữ có thể đang ở trạng thái đề xuất, đang được thảo luận hoặc đã thống nhất. Việc phân biệt trạng thái này giúp tránh xem một cách gọi tạm thời là quyết định chính thức.

## 10. Những sai lầm thường gặp

**Tạo một từ điển chung cho toàn hệ thống.** Cách làm này dễ ép các nhóm vào một mô hình thống nhất giả tạo. Hãy gắn định nghĩa với Bounded Context và ghi nhận sự khác biệt giữa các context.

**Chỉ ghi tên và định nghĩa ngắn.** Nếu thiếu ví dụ, nhóm khó biết thuật ngữ có được hiểu đúng trong tình huống thật hay không. Hãy thêm ít nhất một câu sử dụng có ngữ cảnh.

**Định nghĩa bằng thuật ngữ chưa được giải thích.** Ví dụ, định nghĩa “Capture là xử lý thanh toán” không giúp làm rõ capture là bước nào. Hãy mô tả hành động, điều kiện và kết quả.

**Để kỹ sư tự quyết định ngôn ngữ nghiệp vụ.** Đội phát triển có thể đề xuất cách diễn đạt, nhưng chuyên gia nghiệp vụ cần xác nhận ý nghĩa và ngoại lệ.

**Đưa mọi từ vào bảng.** Danh sách quá dài và chứa nhiều từ không có ý nghĩa domain khiến tài liệu khó tra cứu. Hãy tập trung vào các từ có khả năng gây hiểu nhầm hoặc chi phối mô hình.

**Không đồng bộ với mã nguồn.** Bảng ghi `Payment Attempt` nhưng mã dùng `Transaction`, trong khi hai khái niệm có phạm vi khác nhau. Khi phát hiện lệch nghĩa, cần xác định và sửa một cách có chủ đích.

**Coi bảng thuật ngữ là tài liệu bất biến.** Khi chính sách và mô hình thay đổi, định nghĩa cũng cần được xem xét lại. Hãy đưa việc cập nhật vào quy trình làm việc của nhóm.

## 11. Bài tập thực hành

Một nền tảng đặt lịch khám có ba nhóm: Booking, Billing và Clinic Operations. Các thành viên thường sử dụng những từ “Lịch hẹn”, “Bệnh nhân”, “Thanh toán” và “Hoàn tất” nhưng chưa thống nhất ý nghĩa.

Hãy chọn một Bounded Context, sau đó xây dựng ít nhất năm mục từ. Mỗi mục cần có thuật ngữ chuẩn, ngữ cảnh, định nghĩa và một ví dụ sử dụng. Trong số đó, hãy chọn ít nhất hai từ có khả năng mang nghĩa khác nhau giữa các context.

Gợi ý để bắt đầu:

| Ngữ cảnh | Câu hỏi cần làm rõ |
|---|---|
| Booking | Khi nào một yêu cầu trở thành lịch hẹn đã được xác nhận? Đổi lịch và hủy lịch khác nhau ra sao? |
| Billing | “Thanh toán” là nghĩa vụ phải trả, yêu cầu thu tiền hay khoản tiền đã thu thành công? |
| Clinic Operations | “Bệnh nhân đã đến” được xác nhận bởi ai và có khác với “đã đăng ký tiếp nhận” không? |

Sau khi viết, hãy nhờ một người không tham gia soạn bảng đọc các mục từ và áp dụng vào một tình huống giả định. Nếu người đó không thể xác định thuật ngữ nào được dùng hoặc hiểu kết quả khác với nhóm, hãy sửa định nghĩa và ví dụ.

## Kết luận

Bảng thuật ngữ trong DDD ghi lại ngôn ngữ chung của chuyên gia nghiệp vụ và đội phát triển. Mỗi mục từ cần gắn với Bounded Context, có định nghĩa rõ ràng và ví dụ thể hiện cách dùng trong tình huống thực tế. Cách làm này giúp phát hiện từ mơ hồ, phân biệt những khái niệm gần nhau và bảo vệ ý nghĩa của domain trong mô hình cũng như mã nguồn.

Một tổ chức có thể có nhiều cách hiểu hợp lệ cho cùng một từ ở những ngữ cảnh khác nhau. Khi ghi rõ phạm vi và cách chuyển đổi giữa các cách hiểu, các nhóm có thể phối hợp mà vẫn giữ được mô hình phù hợp với trách nhiệm nghiệp vụ của mình. Hãy xây dựng bảng thuật ngữ cùng chuyên gia, kiểm chứng bằng kịch bản thực tế và cập nhật nó mỗi khi ngôn ngữ hoặc mô hình domain thay đổi.
