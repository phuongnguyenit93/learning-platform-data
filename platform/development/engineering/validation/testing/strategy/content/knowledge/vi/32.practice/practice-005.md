# Thiết kế chiến lược cho chức năng mới có nhiều điểm tích hợp

Một chức năng mới có thể trông đơn giản ở giao diện nhưng tạo ra nhiều tương tác phía sau: gọi API của các dịch vụ nội bộ, ghi dữ liệu qua nhiều kho, phát message, chờ worker xử lý và gọi nhà cung cấp bên ngoài. Nếu chỉ kiểm thử từng màn hình hoặc từng API riêng lẻ, nhóm có thể bỏ sót lỗi về thứ tự sự kiện, tính nhất quán dữ liệu, retry, timeout, phân quyền hoặc tác dụng phụ trùng lặp. Nếu chỉ dựa vào một kịch bản E2E lớn, lỗi lại khó định vị, thời gian chạy cao và phụ thuộc nhiều môi trường.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, thiết kế chiến lược cho chức năng mới có nhiều điểm tích hợp là việc chuyển yêu cầu thành một mô hình xác thực có thể thực thi: xác định hành trình và ranh giới, lập bản đồ phụ thuộc, nhận diện rủi ro, chọn cấp độ và kỹ thuật kiểm thử, chuẩn bị dữ liệu và môi trường, tổ chức thứ tự chạy, quy định cổng chất lượng và thu thập bằng chứng. Chiến lược cần kiểm tra được cả hành vi thành công lẫn cách hệ thống phản ứng khi một hoặc nhiều phụ thuộc chậm, lỗi, trả kết quả trùng hoặc không sẵn sàng.

Bài này dùng ví dụ chức năng đặt hàng mới trong một hệ thống thương mại điện tử. Hành trình đặt hàng tích hợp với định danh, giỏ hàng, giá và khuyến mại, tồn kho, thanh toán, vận chuyển, thông báo và hệ thống phân tích. Các tên dịch vụ chỉ là ví dụ; khi áp dụng, thay bằng thành phần, hợp đồng và rủi ro thực tế của sản phẩm.

## 1. Xác định mục tiêu và phạm vi chức năng

### Bắt đầu từ hành vi người dùng và kết quả nghiệp vụ

Trước khi chọn test, mô tả chức năng theo góc nhìn người dùng và nghiệp vụ. Với chức năng đặt hàng, một luồng thành công có thể là:

1. Người dùng đã đăng nhập và có quyền đặt hàng.
2. Hệ thống xác nhận giỏ hàng và giá hiện tại.
3. Hệ thống áp dụng khuyến mại và tính thuế, phí.
4. Hệ thống kiểm tra hoặc giữ tồn kho.
5. Hệ thống tạo đơn hàng ở trạng thái phù hợp.
6. Hệ thống yêu cầu thanh toán qua nhà cung cấp.
7. Hệ thống xác nhận kết quả thanh toán và cập nhật trạng thái đơn.
8. Hệ thống tạo yêu cầu vận chuyển.
9. Hệ thống gửi thông báo cho người dùng.
10. Hệ thống ghi nhận sự kiện phục vụ đối soát và phân tích.

Không mặc định tất cả bước phải xảy ra đồng bộ trong một request. Có thể có bước đồng bộ, bước bất đồng bộ và bước được xử lý sau khi giao dịch chính hoàn tất. Đây là quyết định kiến trúc ảnh hưởng trực tiếp đến cách kiểm thử.

### Xác định đầu vào, đầu ra và bất biến nghiệp vụ

Với mỗi hành vi, ghi rõ:

- Đầu vào bắt buộc và tùy chọn.
- Vai trò và quyền cần có.
- Điều kiện trước khi thao tác.
- Quy tắc nghiệp vụ và thứ tự áp dụng.
- Trạng thái đầu và trạng thái cuối.
- Dữ liệu được tạo, cập nhật hoặc phát đi.
- Tác dụng phụ với dịch vụ ngoài.
- Hành vi khi một bước thất bại.
- Điều kiện thành công mà người dùng quan sát được.

Ví dụ về các bất biến:

- Đơn hàng chỉ thuộc về đúng tenant và người dùng có quyền.
- Tổng tiền trên đơn, yêu cầu thanh toán và hóa đơn phải theo cùng quy tắc làm tròn.
- Không thể xác nhận thanh toán cho đơn không hợp lệ.
- Một yêu cầu đặt hàng được gửi lại không tạo nhiều đơn ngoài quy tắc đã định.
- Tồn kho không bị giữ hoặc trừ nhiều lần cho cùng một đơn.
- Đơn đã hủy không được chuyển sang trạng thái đã giao chỉ vì một event đến muộn.
- Thông báo không chứa dữ liệu của người dùng khác.

Bất biến giúp tạo oracle rõ ràng hơn so với việc chỉ kiểm tra HTTP 200 hoặc thông báo thành công trên giao diện.

### Xác định phạm vi trong và ngoài hệ thống

Phân định thành phần do nhóm kiểm soát và thành phần bên ngoài:

- Thành phần nội bộ: service, database, queue, worker, cache và API gateway.
- Phụ thuộc bên ngoài: cổng thanh toán, đơn vị vận chuyển, email/SMS provider hoặc dịch vụ định danh.
- Thành phần vận hành: CI runner, secret store, monitoring, feature flag và hệ thống triển khai.
- Người hoặc hệ thống tiêu thụ: ứng dụng web/mobile, đối tác, back-office và data platform.

Ranh giới này quyết định nơi dùng contract test, sandbox, stub, test double hoặc kiểm thử đầu-cuối với nhà cung cấp thật. Không coi mọi phụ thuộc đều có thể điều khiển như một service nội bộ.

### Chốt điều không nằm trong phạm vi

Ghi rõ chức năng nào chưa được triển khai, vùng nào chưa hỗ trợ và giới hạn của sandbox. Phạm vi ngoài bài kiểm thử cần có lý do và người chấp nhận rủi ro nếu nó ảnh hưởng đến quyết định phát hành.

## 2. Lập bản đồ các điểm tích hợp

### Liệt kê provider, consumer và luồng dữ liệu

Với mỗi ranh giới, xác định bên gửi, bên nhận và dữ liệu trao đổi:

| Điểm tích hợp | Provider | Consumer | Dữ liệu hoặc hợp đồng chính |
|---|---|---|---|
| Định danh | Identity service | Order API | User, tenant, role, token claims |
| Giỏ hàng | Cart service | Order API | Item, quantity, price reference |
| Giá và khuyến mại | Pricing service | Order API | Discount, tax, currency, quote expiry |
| Tồn kho | Inventory service | Order workflow | Availability, reservation, release |
| Thanh toán | Payment provider | Payment adapter | Amount, currency, payment reference, callback |
| Vận chuyển | Shipping provider | Fulfillment service | Address, parcel, shipment status |
| Thông báo | Notification service | Email/SMS provider | Template, recipient, event |
| Phân tích | Event platform | Data consumer | Order event, schema, event time |

Bảng này là điểm khởi đầu. Cần thêm phiên bản API, giao thức, cơ chế xác thực, timeout, retry, giới hạn quota và owner của từng bên.

### Phân biệt tương tác đồng bộ và bất đồng bộ

Tương tác đồng bộ thường có request và response trong cùng luồng xử lý. Cần kiểm tra deadline, mã lỗi, schema, retry và hành vi khi caller timeout.

Tương tác bất đồng bộ thường qua queue, event bus hoặc callback. Cần kiểm tra:

- Event có được publish đúng khi transaction nghiệp vụ commit không?
- Consumer có xử lý event trùng một cách an toàn không?
- Thứ tự event có được bảo đảm hay cần xử lý event đến sai thứ tự?
- Message lỗi có retry, delay hoặc chuyển dead-letter queue không?
- Có thể đối soát khi provider đã xử lý nhưng caller chưa nhận được phản hồi không?
- Trạng thái cuối được xác định từ nguồn dữ liệu có thẩm quyền nào?

Không giả định queue bảo đảm xử lý đúng một lần. Nhiều hệ thống cung cấp ít nhất một lần giao nhận, vì vậy consumer cần idempotency hoặc cơ chế chống tác dụng phụ trùng.

### Vẽ đồ thị phụ thuộc

Sơ đồ giúp nhìn thấy đường đi và điểm có thể lan truyền lỗi:

~~~mermaid
flowchart TD
    U["Web / Mobile"] --> G["API Gateway"]
    G --> I["Identity"]
    G --> C["Cart"]
    G --> O["Order API"]
    O --> P["Pricing"]
    O --> V["Inventory"]
    O --> D["Order Database"]
    O --> Q["Outbox / Event Bus"]
    Q --> W["Payment Worker"]
    W --> X["Payment Adapter"]
    X --> S["Payment Provider"]
    Q --> F["Fulfillment Worker"]
    F --> H["Shipping Provider"]
    Q --> N["Notification Worker"]
    N --> M["Email / SMS Provider"]
    Q --> A["Analytics Consumer"]
~~~

Sơ đồ cần được điều chỉnh theo kiến trúc thật. Bổ sung chiều dữ liệu trả về, callback, webhook, retry queue và các phụ thuộc dùng chung nếu chúng ảnh hưởng đến kết quả.

### Xác định điểm lỗi và ranh giới tin cậy

Với mỗi điểm tích hợp, hỏi:

- Network có thể mất kết nối ở thời điểm nào?
- Request có thể timeout sau khi provider đã thực hiện tác dụng phụ không?
- Response có thể đến trễ hoặc bị gửi lại không?
- Dữ liệu có thể thiếu, sai phiên bản hoặc không hợp lệ không?
- Credential có thể hết hạn hoặc thiếu quyền không?
- Provider có giới hạn tốc độ hoặc thời gian bảo trì không?
- Consumer có thể restart giữa lúc xử lý không?
- Có dữ liệu nhạy cảm đi qua ranh giới không?

Đánh dấu trust boundary, vùng dữ liệu nhạy cảm và các điểm mà một lỗi có thể ảnh hưởng nhiều tenant hoặc nhiều đơn hàng.

## 3. Chuyển bản đồ tích hợp thành mô hình rủi ro

### Nhận diện rủi ro theo từng ranh giới

Không chỉ liệt kê “API lỗi”. Mô tả điều kiện, hậu quả và khả năng phát hiện. Ví dụ:

| Rủi ro | Điều kiện có thể gây ra | Hậu quả |
|---|---|---|
| Giá không nhất quán | Quote hết hạn giữa lúc tạo đơn và thanh toán | Thu sai tiền hoặc sai hóa đơn |
| Giữ tồn kho trùng | Request retry sau timeout | Giảm tồn kho nhiều lần |
| Thanh toán trùng | Callback hoặc message được giao lại | Thu tiền nhiều lần |
| Đơn kẹt PROCESSING | Consumer lỗi hoặc event bị mất | Người dùng không biết kết quả |
| Event sai thứ tự | Callback đến sau khi đơn đã hủy | Trạng thái đơn không hợp lệ |
| Rò rỉ tenant | Token hoặc kiểm tra ownership sai | Người dùng xem dữ liệu người khác |
| Tạo shipment lặp | Worker retry sau khi provider đã tạo vận đơn | Nhiều vận đơn cho một đơn |
| Mất thông báo | Provider lỗi hoặc quota hết | Người dùng không nhận trạng thái |
| Dữ liệu phân tích sai | Event schema không tương thích | Báo cáo và quyết định kinh doanh sai |

### Chấm điểm và ưu tiên

Có thể đánh giá từng rủi ro theo:

- Mức nghiêm trọng của hậu quả.
- Khả năng xảy ra.
- Mức phơi nhiễm hoặc tần suất luồng được sử dụng.
- Khả năng phát hiện trước khi ảnh hưởng người dùng.
- Khả năng phục hồi và có workaround.
- Phạm vi lan truyền qua các dịch vụ.

Không nhất thiết phải dùng một công thức số học phức tạp. Nếu dùng thang điểm, định nghĩa rõ ý nghĩa từng mức và cách xử lý khi điểm bằng nhau. Rủi ro dữ liệu, bảo mật và giao dịch tài chính cần được xem xét riêng ngay cả khi tần suất thấp.

### Phân biệt rủi ro chức năng và rủi ro tích hợp

Rủi ro chức năng liên quan đến quy tắc nghiệp vụ, chẳng hạn giảm giá không đúng. Rủi ro tích hợp liên quan đến cách nhiều thành phần phối hợp, chẳng hạn event được gửi hai lần hoặc trạng thái không hội tụ. Một lỗi có thể thuộc cả hai nhóm.

Với mỗi rủi ro, xác định nơi lỗi có thể phát sinh, nơi có thể quan sát và nơi có thể ngăn tác dụng phụ. Điều này giúp đặt test tại đúng ranh giới thay vì chỉ kiểm tra kết quả cuối.

### Xác định oracle và nguồn dữ liệu có thẩm quyền

Oracle là cơ sở quyết định kết quả đúng hay sai. Với chức năng nhiều tích hợp, không nên dùng một nguồn dữ liệu duy nhất cho mọi kiểm tra.

Ví dụ:

- Order database là nguồn xác nhận trạng thái đơn.
- Payment provider reference hoặc ledger là nguồn đối soát thanh toán.
- Inventory reservation là nguồn xác nhận giữ tồn.
- Event log hoặc outbox là nguồn xác minh phát sự kiện.
- Shipping provider reference là nguồn xác nhận vận đơn.
- Audit log là nguồn xác minh hành động nhạy cảm.

Ghi rõ thời gian hội tụ được chấp nhận nếu hệ thống eventual consistency. Một test không nên kết luận fail ngay sau một khoảng chờ quá ngắn khi kiến trúc cho phép xử lý bất đồng bộ, nhưng cũng không được chờ vô hạn.

## 4. Chọn cấp độ kiểm thử cho từng ranh giới

### Unit và component test cho logic cục bộ

Đặt các quy tắc có thể kiểm tra độc lập ở cấp unit hoặc component:

- Tính tổng tiền, thuế và chiết khấu.
- Kiểm tra trạng thái đơn hợp lệ.
- Xác định quyền đặt hàng.
- Xây dựng payload gửi provider.
- Quy tắc retry và backoff.
- Quy tắc chuyển trạng thái khi nhận event.
- Ánh xạ lỗi provider sang lỗi nghiệp vụ.

Dùng dependency injection để kiểm soát clock, random, provider adapter và dữ liệu. Test cần xác minh hành vi và invariant, không phụ thuộc vào chi tiết triển khai không ổn định.

### Contract test ở từng API và event boundary

Contract test phù hợp cho:

- Request/response giữa Order API và Pricing.
- Payload reservation gửi Inventory.
- Event OrderCreated hoặc PaymentConfirmed.
- Callback từ Payment Provider.
- Request tạo shipment.
- Payload gửi Notification hoặc Analytics.

Kiểm tra schema, trường bắt buộc, kiểu dữ liệu, enum, semantics, versioning, mã lỗi và tương thích. Nếu có provider và consumer độc lập triển khai, kiểm tra cả kỳ vọng consumer và khả năng đáp ứng của provider theo quy trình của nhóm.

### Integration test cho tương tác thật có chọn lọc

Dùng integration test để xác minh điều mà mock không thể chứng minh:

- Transaction và outbox cùng commit.
- Database constraint và locking.
- Publish/consume message.
- Idempotency khi xử lý message trùng.
- Retry và dead-letter behavior.
- Cache hoặc read model cập nhật.
- Adapter với sandbox nhà cung cấp.
- Callback được xác thực và liên kết đúng giao dịch.

Chọn các phụ thuộc thật theo rủi ro. Không cần khởi chạy toàn bộ hệ thống cho mọi test; có thể dùng container hoặc sandbox riêng cho ranh giới cần xác minh.

### System và E2E cho hành trình quan trọng

Giữ một tập hành trình đại diện:

- Đặt hàng thành công và thanh toán.
- Thanh toán bị từ chối.
- Người dùng hủy trước khi thanh toán hoàn tất.
- Thanh toán thành công nhưng callback đến chậm.
- Hết tồn kho trong lúc checkout.
- Đơn được hoàn tiền hoặc hoàn tất vận chuyển.
- Người dùng không có quyền truy cập đơn của tenant khác.

E2E xác minh các thành phần đã triển khai phối hợp đúng. Không lặp lại mọi tổ hợp đầu vào ở E2E; các trường hợp biên nên được kiểm tra ở cấp rẻ và ổn định hơn.

### Acceptance test cho tiêu chí nghiệp vụ

Product owner hoặc đại diện nghiệp vụ cần xác nhận các điều kiện có ý nghĩa đối với người dùng: tổng tiền, trạng thái đơn, cách hiển thị khi chờ thanh toán, chính sách hủy và thông báo. Acceptance test có thể dùng ví dụ cụ thể hoặc kịch bản nghiệp vụ, với dữ liệu và oracle được thống nhất trước.

## 5. Chọn loại và kỹ thuật kiểm thử theo rủi ro

### Functional và data integrity

Dùng phân vùng tương đương, giá trị biên, bảng quyết định và kiểm tra invariant cho:

- Số lượng bằng không, âm, tối đa hoặc vượt tồn.
- Mã giảm giá hết hạn, không hợp lệ hoặc chỉ áp dụng cho một số mặt hàng.
- Tiền tệ và quy tắc làm tròn.
- Địa chỉ thiếu hoặc không hỗ trợ.
- Chuyển trạng thái đơn và thanh toán.
- Tổng tiền và dữ liệu đối soát giữa các hệ thống.

Ví dụ, bảng quyết định có thể kết hợp trạng thái tài khoản, tenant, loại sản phẩm và phương thức thanh toán để xác định một đơn có được tạo hay không.

### Reliability và resilience

Kiểm tra timeout, retry, backoff, circuit breaker, failover và phục hồi:

- Pricing timeout trước khi trả quote.
- Inventory trả lỗi sau khi request giữ hàng đã được xử lý.
- Payment provider nhận request nhưng response bị mất.
- Callback bị giao lại.
- Queue bị chậm hoặc consumer restart.
- Shipping provider không khả dụng.
- Notification provider giới hạn tốc độ.

Với từng trường hợp, xác định trạng thái mong đợi, số lần retry, idempotency key, thời hạn xử lý và cách đối soát. Không retry mù những thao tác có tác dụng phụ tài chính hoặc tạo tài nguyên ngoài.

### Security và privacy

Kiểm tra:

- Token hết hạn hoặc sai chữ ký.
- Người dùng đổi order ID để truy cập dữ liệu khác.
- Service account có quyền vượt mức cần thiết.
- Callback không có chữ ký hợp lệ.
- Webhook replay.
- Dữ liệu nhạy cảm xuất hiện trong log hoặc message.
- Tenant ID bị giả mạo hoặc không được kiểm tra ở service nhận.
- Secret sandbox bị lộ trong artifact.

Dùng ma trận vai trò/tenant, negative testing, kiểm tra audit và rà soát dữ liệu qua từng ranh giới. Dữ liệu thử phải được khử định danh và giới hạn quyền truy cập.

### Performance và capacity

Xác định workload đại diện: số checkout đồng thời, số item trong giỏ, tỷ lệ provider chậm, số event mỗi đơn và tải tăng đột biến. Đo latency theo từng service, end-to-end latency, throughput, queue lag, retry rate và tài nguyên.

Một E2E nhanh trong tải thấp không chứng minh chuỗi tích hợp chịu được tải cao. Có thể dùng integration/load test ở ranh giới và system load test cho luồng tổng thể.

### Compatibility và contract evolution

Kiểm tra phiên bản API, schema event, consumer cũ và mới, migration dữ liệu và rollout không đồng thời. Nếu producer triển khai trước consumer hoặc ngược lại, cần chứng minh tương thích trong giai đoạn chuyển tiếp.

## 6. Thiết kế chiến lược cho lỗi một phần và tác dụng phụ

### Xây dựng ma trận lỗi theo từng điểm tích hợp

Với mỗi provider, xem xét tối thiểu:

- Thành công bình thường.
- Từ chối nghiệp vụ.
- Lỗi xác thực hoặc phân quyền.
- Timeout trước khi provider xử lý.
- Timeout sau khi provider đã xử lý.
- HTTP 5xx hoặc lỗi tạm thời.
- Rate limit.
- Response sai schema hoặc thiếu trường.
- Response đến trễ.
- Response hoặc event bị lặp.
- Kết nối bị ngắt giữa lúc gửi và nhận.
- Provider phục hồi sau một khoảng gián đoạn.

Không phải mọi test cần chạy ở mọi cấp. Chọn một số trường hợp trọng yếu ở component/integration và xác minh một số hành trình đại diện ở system/E2E.

### Phân biệt thất bại trước và sau tác dụng phụ

Đây là điểm quan trọng của hệ thống nhiều tích hợp. Khi caller timeout, không thể suy ra provider chưa thực hiện thao tác. Ví dụ, yêu cầu tạo payment có thể đã được chấp nhận nhưng response bị mất.

Thiết kế kiểm thử cần xác minh:

1. Request có operation ID hoặc idempotency key ổn định.
2. Retry sử dụng cùng khóa cho cùng một ý định nghiệp vụ.
3. Hệ thống có thể truy vấn trạng thái theo reference.
4. Không tạo tác dụng phụ trùng khi retry.
5. Nếu kết quả chưa rõ, đơn chuyển sang trạng thái chờ đối soát.
6. Kết quả đối soát cuối cùng được ghi nhận và có audit.

Test nên mô phỏng cả timeout trước khi provider xử lý và timeout sau khi provider đã hoàn tất nhưng caller chưa nhận response.

### Kiểm tra thứ tự và sự hội tụ trạng thái

Các event có thể đến sai thứ tự hoặc trễ. Xác định:

- Event nào có version, sequence hoặc occurredAt?
- Trạng thái nào là trạng thái cuối và trạng thái nào có thể đảo ngược?
- Event cũ có bị bỏ qua không?
- Một event hợp lệ đến muộn có cần đối soát không?
- Có thể xử lý song song nhiều event của cùng một đơn không?
- Read model và cache hội tụ trong thời gian bao lâu?

Kiểm tra các chuỗi như PaymentFailed đến trước PaymentPending, hoặc OrderCancelled đến trước PaymentConfirmed. Hệ thống cần có quy tắc chuyển trạng thái rõ và không để event đến muộn ghi đè trạng thái không hợp lệ.

### Kiểm tra bù trừ và saga

Nếu quy trình gồm nhiều bước không thể đặt trong một transaction phân tán, kiến trúc có thể dùng saga hoặc hành động bù:

- Giữ tồn kho.
- Tạo đơn.
- Yêu cầu thanh toán.
- Xác nhận thanh toán.
- Tạo shipment.

Nếu thanh toán thất bại sau khi đã giữ tồn kho, cần giải phóng reservation. Nếu tạo shipment thất bại sau khi đã thu tiền, có thể cần retry, giữ trạng thái chờ hoặc hoàn tiền theo quy tắc.

Test cần xác minh cả hành động thuận và hành động bù, kể cả khi một bước bù cũng lỗi. Ghi rõ trạng thái cuối và cách vận hành can thiệp khi saga không tự phục hồi.

## 7. Thiết kế dữ liệu kiểm thử và môi trường tích hợp

### Tạo dữ liệu có định danh và cô lập

Mỗi lần chạy nên có run ID và dữ liệu riêng:

- Tenant, user và role riêng.
- Cart và order riêng.
- Payment reference giả lập hoặc sandbox riêng.
- Inventory reservation riêng.
- Shipment và notification ID riêng.
- Queue namespace hoặc correlation ID riêng.

Dùng dữ liệu nền bất biến khi có thể. Dữ liệu có tác dụng phụ phải được tạo trong namespace của run và cleanup theo owner. Không dùng một tài khoản hoặc đơn hàng chung có thể bị nhiều test sửa đồng thời.

### Chuẩn bị bộ dữ liệu theo kịch bản

Một tập dữ liệu tối thiểu có thể gồm:

- Giỏ hàng một mặt hàng và nhiều mặt hàng.
- Sản phẩm còn hàng, hết hàng và gần chạm ngưỡng.
- Mã giảm giá hợp lệ, hết hạn và không áp dụng.
- Địa chỉ hợp lệ và không được hỗ trợ.
- Người dùng có quyền và không có quyền.
- Thanh toán được chấp nhận, từ chối và pending.
- Provider trả timeout, rate limit và response lỗi.
- Event trùng hoặc đến sai thứ tự.

Mỗi fixture cần ghi mục đích, version, trạng thái ban đầu và cách tạo lại.

### Dùng sandbox và test double có chủ đích

Sandbox thật hữu ích để kiểm tra contract và hành vi gần provider, nhưng có thể chậm, không ổn định hoặc giới hạn quota. Test double cho phép mô phỏng lỗi hiếm và kết quả xác định.

Phân bổ như sau:

- Unit/component: fake hoặc stub để kiểm tra nhánh logic.
- Contract: xác minh schema và semantics với provider/consumer.
- Integration: sandbox hoặc container thật cho ranh giới quan trọng.
- E2E: một số hành trình đại diện với sandbox được kiểm soát.
- Resilience: test double có khả năng tiêm lỗi để tạo timeout, duplicate và out-of-order event.

Ghi rõ phần nào được kiểm tra bằng sandbox và phần nào chỉ được mô phỏng. Không tuyên bố đã xác minh provider thật nếu test chỉ dùng stub.

### Quản lý cleanup và đối soát

Cleanup cần theo thứ tự phụ thuộc và ownership:

- Dừng worker hoặc test producer.
- Xác minh tác vụ bất đồng bộ đã kết thúc hoặc được ghi nhận.
- Đối soát payment và shipment sandbox nếu cần.
- Xóa dữ liệu theo run ID.
- Xóa queue message, cache và object tạm.
- Thu hồi credential hoặc token tạm.
- Giữ artifact cần điều tra theo retention.

Nếu provider đã tạo giao dịch hoặc tài nguyên không thể xóa ngay, ghi reference và trạng thái cleanup. Không báo môi trường sạch khi còn tác dụng phụ chưa được đối soát.

## 8. Xây dựng ma trận kiểm thử và kế hoạch bằng chứng

### Ma trận tích hợp và rủi ro

Một ma trận thực hành có thể dùng:

| Ranh giới/rủi ro | Cấp độ chính | Loại | Kỹ thuật | Bằng chứng |
|---|---|---|---|---|
| Order–Pricing: sai tổng tiền | Unit, contract, integration | Functional/data integrity | Boundary, decision table, schema | Quote, order total, tax breakdown |
| Order–Inventory: giữ hàng trùng | Component, integration | Reliability/data integrity | Retry, concurrency, invariant | Reservation ID và số lượng tồn |
| Order–Payment: callback trùng | Contract, integration, E2E | Reliability/security | Signature, replay, idempotency | Payment reference, event ID, order state |
| Order–Shipping: tạo vận đơn lặp | Integration | Reliability | Timeout-after-side-effect, deduplication | Shipment reference |
| Order–Notification: gửi sai người | Component, integration | Security/functional | Recipient matrix, event assertion | Message metadata đã khử dữ liệu |
| Order–Analytics: schema lệch | Contract, integration | Compatibility/data quality | Schema validation, replay | Event schema version và consumer result |
| Toàn hành trình đặt hàng | System/E2E, acceptance | Functional/regression | Scenario và state transition | Trace, order state, payment và shipment state |

Ma trận phải chỉ rõ test đã tồn tại, cần tạo mới hay đang có khoảng trống. Nếu một rủi ro được kiểm tra ở nhiều cấp, ghi mục đích riêng của từng lớp.

### Gắn test với yêu cầu và pipeline stage

Mỗi test hoặc suite nên liên kết với:

- Requirement/behavior ID.
- Risk ID.
- Service hoặc boundary.
- Test level và test type.
- Kỹ thuật và oracle.
- Dataset/fixture.
- Môi trường.
- Pipeline stage.
- Owner.
- Kết quả và artifact.

Điều này cho phép thay đổi một API hoặc schema và tìm được test, dữ liệu, gate cần rà soát.

### Định nghĩa pass/fail và thời gian hội tụ

Với tương tác bất đồng bộ, quy định:

- Điều kiện cuối mong đợi.
- Deadline tổng.
- Polling interval hoặc cơ chế chờ sự kiện.
- Trạng thái trung gian được phép.
- Nguồn dữ liệu dùng để xác minh.
- Hành vi nếu deadline hết.
- Bằng chứng cần giữ khi fail.

Không dùng sleep cố định dài nếu có thể chờ điều kiện có deadline. Không chờ vô hạn vì test sẽ treo khi consumer không xử lý.

## 9. Tổ chức thứ tự thực thi và cổng chất lượng

### Chạy từ phản hồi nhanh đến bằng chứng xuyên hệ thống

Một thứ tự có thể là:

1. Static analysis, lint và kiểm tra cấu hình.
2. Unit và component test cho logic mới.
3. Contract test cho API và event.
4. Integration test cho database, queue và adapter.
5. Test resilience cho các rủi ro tích hợp trọng yếu.
6. E2E cho hành trình đại diện.
7. Acceptance, security và performance theo điều kiện phát hành.
8. Smoke/synthetic sau deploy.

Thứ tự có thể thay đổi theo dependency và thời gian. Test nhanh, ổn định nên chạy sớm để phản hồi; test cần sandbox hoặc môi trường đắt tiền có thể chạy sau khi các lớp rẻ hơn đạt.

### Xác định gate theo rủi ro

Ví dụ các điều kiện chặn:

- Không có lỗi nghiêm trọng về quyền hoặc tenant isolation.
- Contract bắt buộc tương thích với provider/consumer được hỗ trợ.
- Invariant về số tiền, tồn kho và idempotency đạt.
- Không còn trạng thái giao dịch không xác định vượt ngưỡng.
- Hành trình cốt lõi đạt trong môi trường đại diện.
- Migration và tương thích dữ liệu đạt.
- Test bắt buộc không bị skip hoặc cách ly ngoài ngoại lệ được phê duyệt.

Gate phải nêu ai có quyền chấp nhận ngoại lệ và bằng chứng nào cần có. Không để trạng thái xanh của một số suite che khuất test bắt buộc chưa chạy.

### Fallback khi phụ thuộc kiểm thử không khả dụng

Nếu sandbox provider hoặc môi trường tích hợp không sẵn sàng:

- Xác định test nào vẫn có thể chạy bằng contract hoặc test double.
- Ghi rõ phần bằng chứng chưa có.
- Chạy kiểm tra thay thế đã được phê duyệt.
- Đánh giá mức rủi ro còn lại.
- Chặn release nếu thiếu bằng chứng bắt buộc và không có kiểm soát bù phù hợp.
- Lên lịch chạy lại khi phụ thuộc phục hồi.

Không chuyển một test bị blocked thành passed. Không coi sandbox lỗi là bằng chứng sản phẩm đúng hoặc sai.

### Quản lý timeout, retry và hủy

Đặt timeout cho request, test, job và toàn workflow. Retry chỉ dùng khi thao tác an toàn và có giới hạn. Khi hủy:

- Truyền tín hiệu đến process con và worker.
- Ngừng tạo tác dụng phụ mới.
- Lưu trạng thái và artifact.
- Đối soát request có kết quả chưa rõ.
- Cleanup theo run ID.
- Ghi tài nguyên còn sót nếu cleanup thất bại.

Đặc biệt với payment hoặc shipment, timeout không có nghĩa provider chưa xử lý. Truy vấn theo operation reference trước khi retry hoặc xóa dữ liệu.

## 10. Quan sát và chẩn đoán xuyên nhiều dịch vụ

### Dùng correlation ID và trace

Một hành trình có thể đi qua gateway, order, pricing, inventory, payment và notification. Dùng correlation ID hoặc trace context để liên kết:

- Request ban đầu.
- Các lời gọi service.
- Event được publish.
- Consumer xử lý.
- Callback từ provider.
- Hành động bù.
- Kết quả cuối.

Không đưa dữ liệu nhạy cảm vào trace attribute. Bảo đảm ID được truyền qua async boundary theo chuẩn của hệ thống.

### Thu thập metric theo ranh giới

Các metric hữu ích:

- Request rate, error rate và latency theo provider.
- Timeout và retry rate.
- Queue lag và số message ở dead-letter queue.
- Tỷ lệ callback hợp lệ, trùng và bị từ chối.
- Thời gian từ order creation đến trạng thái cuối.
- Tỷ lệ reservation được giải phóng.
- Tỷ lệ payment cần đối soát.
- Tỷ lệ shipment hoặc notification bị tạo trùng.
- Số saga đang ở trạng thái chờ quá hạn.

Metric cần có ngưỡng và owner. Test có thể xác minh metric hoặc alert xuất hiện trong một số kịch bản lỗi được kiểm soát.

### Thiết kế báo cáo dễ điều tra

Khi test fail, báo cáo nên nêu:

- Run ID, test ID và build.
- Order ID và reference đã khử dữ liệu.
- Service và boundary đang kiểm tra.
- Request/response hoặc event liên quan.
- Thời điểm và trạng thái trước/sau.
- Correlation ID và trace link.
- Expected/actual.
- Lần retry và trạng thái cuối.
- Tài nguyên còn tồn tại sau cleanup.

Một báo cáo chỉ có “E2E failed” không đủ cho một luồng nhiều tích hợp.

## 11. Kiểm thử chuyển đổi, rollout và tương thích

### Kiểm tra triển khai không đồng thời

Các service có thể được triển khai ở thời điểm khác nhau. Kiểm tra:

- Consumer mới có đọc được event từ producer cũ không?
- Producer mới có gửi payload mà consumer cũ hiểu được không?
- Schema có hỗ trợ trường tùy chọn hoặc versioning không?
- Migration có tương thích với hai phiên bản ứng dụng không?
- Rollback có giữ dữ liệu ở trạng thái đọc được không?

Dùng expand-and-contract khi phù hợp: mở rộng schema, triển khai consumer tương thích, chuyển producer, rồi mới loại bỏ trường cũ sau khi không còn consumer sử dụng.

### Kiểm tra feature flag và rollout từng phần

Nếu chức năng được bật theo tenant, vùng hoặc tỷ lệ người dùng:

- Xác minh cả nhánh bật và tắt.
- Kiểm tra chuyển đổi trạng thái flag.
- Kiểm tra dữ liệu được tạo bởi phiên bản mới khi flag tắt lại.
- Xác minh không trộn lẫn hành vi giữa tenant.
- Định nghĩa metric và ngưỡng rollback.
- Kiểm tra hành vi khi flag service không khả dụng.

Feature flag không thay thế migration hoặc tương thích. Cần xác minh mọi tổ hợp phiên bản có thể cùng tồn tại trong rollout.

### Kiểm tra rollback và phục hồi

Tạo tình huống rollout thất bại sau khi một số service đã cập nhật. Xác minh:

- Phiên bản nào đang phục vụ.
- Dữ liệu đã ghi có đọc được bởi phiên bản trước không.
- Message đang chờ có được consumer cũ xử lý không.
- Reservation/payment/shipment có cần đối soát không.
- Feature flag có thể tắt an toàn không.
- Có thể tiếp tục triển khai mà không tạo tác dụng phụ trùng không.

Không coi rollback code là rollback toàn bộ tác dụng phụ bên ngoài. Cần quy trình bù hoặc đối soát riêng.

## 12. Ví dụ thực hành: lập chiến lược cho chức năng đặt hàng

### Bước 1: Mô tả hành trình và tiêu chí chấp nhận

Nhóm xác định hành vi:

- Người dùng có quyền tạo đơn từ giỏ hàng hợp lệ.
- Giá, thuế và giảm giá được tính nhất quán.
- Tồn kho được giữ trước khi xác nhận đơn theo quy tắc nghiệp vụ.
- Thanh toán có một kết quả có thể đối soát.
- Đơn chuyển trạng thái đúng khi payment thành công, thất bại hoặc chờ.
- Vận chuyển chỉ được tạo khi điều kiện hoàn tất phù hợp.
- Thông báo gửi đúng người nhận và không làm lộ dữ liệu.

### Bước 2: Liệt kê ranh giới và owner

| Thành phần | Owner giả định | Ranh giới cần xác minh |
|---|---|---|
| Order API | Nhóm Commerce | Request, trạng thái và transaction |
| Pricing | Nhóm Pricing | Quote, thuế và giảm giá |
| Inventory | Nhóm Supply | Reservation và release |
| Payment adapter | Nhóm Payments | Provider contract và idempotency |
| Shipping adapter | Nhóm Fulfillment | Tạo và hủy shipment |
| Notification | Nhóm Messaging | Recipient, template và retry |
| Event platform | Nhóm Platform | Delivery, ordering và retention |

Tên owner phải được thay bằng nhóm thực tế. Mỗi boundary cần có người phối hợp ở cả phía provider và consumer.

### Bước 3: Lập risk register ban đầu

| ID | Rủi ro | Mức ưu tiên gợi ý | Bằng chứng chính |
|---|---|---|---|
| R-01 | Tính sai tổng tiền | Cao | Unit, component, integration |
| R-02 | Giữ tồn kho trùng | Cao | Integration, concurrency |
| R-03 | Thu tiền trùng sau retry | Rất cao | Payment idempotency, replay |
| R-04 | Callback giả hoặc replay | Rất cao | Signature, security test |
| R-05 | Đơn kẹt trạng thái | Cao | Async integration, E2E |
| R-06 | Shipment tạo trùng | Cao | Provider reference, retry test |
| R-07 | Rò rỉ tenant | Rất cao | API/system security |
| R-08 | Event schema không tương thích | Trung bình đến cao | Contract và compatibility |

Mức ưu tiên cần được xác nhận bằng tiêu chí rủi ro của sản phẩm, phạm vi người dùng và hậu quả thực tế.

### Bước 4: Chọn test và oracle

- R-01: kiểm tra giá trị biên, nhiều loại giảm giá và invariant tổng tiền.
- R-02: chạy đồng thời hai request giữ lượng tồn cuối cùng, xác minh chỉ số lượng hợp lệ được giữ.
- R-03: mô phỏng provider xử lý thành công nhưng response timeout, sau đó retry cùng idempotency key.
- R-04: gửi callback chữ ký sai, callback cũ và callback lặp; xác minh bị từ chối hoặc xử lý idempotent.
- R-05: dừng consumer, gửi event rồi khởi động lại; xác minh đơn hội tụ trạng thái trong deadline.
- R-06: mô phỏng timeout sau khi shipment đã tạo và xác minh không tạo vận đơn thứ hai.
- R-07: dùng token tenant khác truy cập order ID; xác minh bị từ chối và không lộ dữ liệu.
- R-08: chạy consumer contract với schema cũ và mới trong giai đoạn chuyển tiếp.

Oracle phải lấy từ nguồn dữ liệu có thẩm quyền và kiểm tra cả trạng thái nghiệp vụ lẫn tác dụng phụ.

### Bước 5: Chuẩn bị dữ liệu và môi trường

Tạo tenant, user, cart, product, inventory, discount và provider reference theo run ID. Dùng sandbox cho một số hành trình thật, test double để tạo timeout và event sai thứ tự. Mỗi run có namespace queue và registry tài nguyên. Chuẩn bị cleanup và đối soát trước khi chạy test có tác dụng phụ.

### Bước 6: Sắp xếp pipeline

- Pull request: unit, component, contract và static security.
- Sau tích hợp: database/queue/provider adapter, idempotency và concurrency.
- Nightly: E2E hành trình, lỗi một phần và regression rộng.
- Pre-release: performance, security, migration và acceptance.
- Post-deploy: smoke/synthetic, metric và canary theo phạm vi.

Gate bắt buộc cho invariant tài chính, tenant isolation, contract và trạng thái giao dịch không xác định. Nếu sandbox không khả dụng, báo rõ phần chưa có bằng chứng và áp dụng quyết định release theo chính sách.

### Bước 7: Xác minh tính đầy đủ của chiến lược

Nhóm review:

- Mọi rủi ro mức cao có test hoặc kiểm soát thay thế không?
- Các boundary có owner ở hai phía không?
- Timeout sau tác dụng phụ có được kiểm tra không?
- Event trùng và sai thứ tự có được xử lý không?
- Dữ liệu có cô lập và cleanup được không?
- Pipeline có fallback khi provider hoặc môi trường lỗi không?
- Artifact có đủ để điều tra xuyên service không?
- Rollback có tính đến dữ liệu và tác dụng phụ bên ngoài không?

Kết quả review phải tạo danh sách việc còn thiếu, owner và thời hạn trước khi chức năng được đưa qua gate phát hành.

## 13. Những sai lầm thường gặp

- **Chỉ kiểm tra API từng service:** không xác minh hành trình và trạng thái xuyên hệ thống.
- **Chỉ có một E2E lớn:** khó định vị lỗi và dễ flaky.
- **Mock tất cả phụ thuộc:** bỏ sót contract, transaction và hành vi tích hợp thật.
- **Tin rằng timeout nghĩa là provider chưa xử lý:** có thể tạo tác dụng phụ trùng khi retry.
- **Giả định message chỉ được giao một lần:** bỏ sót duplicate và idempotency.
- **Không kiểm tra event sai thứ tự:** trạng thái có thể bị ghi đè không hợp lệ.
- **Chỉ kiểm tra response 200:** không xác minh dữ liệu và tác dụng phụ.
- **Không có nguồn oracle rõ:** kết luận pass dựa trên dữ liệu không có thẩm quyền.
- **Dùng dữ liệu chung giữa run:** gây va chạm và test phụ thuộc thứ tự.
- **Không kiểm tra cleanup và đối soát:** để lại giao dịch hoặc tài nguyên sandbox.
- **Không có fallback khi provider lỗi:** pipeline bị chặn mà không có quyết định rủi ro rõ.
- **Chỉ test happy path:** bỏ qua lỗi một phần, retry, callback và phục hồi.
- **Không kiểm tra rollout nhiều phiên bản:** provider và consumer có thể không tương thích.
- **Không có trace xuyên dịch vụ:** mất nhiều thời gian điều tra khi test fail.
- **Không liên kết test với risk ID:** khó biết khoảng trống nào cần ưu tiên.

## 14. Đầu ra cần có trước khi chốt chiến lược cho chức năng nhiều tích hợp

Một chiến lược đủ dùng nên có:

1. **Mô tả hành vi và tiêu chí chấp nhận:** đầu vào, đầu ra, trạng thái và bất biến nghiệp vụ.
2. **Bản đồ kiến trúc và tích hợp:** provider, consumer, giao thức, dữ liệu và owner.
3. **Danh mục rủi ro:** điều kiện kích hoạt, hậu quả, khả năng và ưu tiên.
4. **Ma trận cấp độ/loại/kỹ thuật:** test nào kiểm tra rủi ro nào và vì sao.
5. **Contract và compatibility plan:** API, event, schema, versioning và rollout.
6. **Kế hoạch lỗi một phần:** timeout, retry, duplicate, out-of-order, rate limit và phục hồi.
7. **Kế hoạch dữ liệu:** fixture, namespace, seed, sandbox và đối soát.
8. **Kế hoạch môi trường:** service cần khởi chạy, cấu hình, readiness, quota và cleanup.
9. **Oracle và bằng chứng:** nguồn dữ liệu có thẩm quyền, trace, metric và artifact.
10. **Kế hoạch pipeline:** thứ tự stage, gate, fallback và điều kiện release.
11. **Kế hoạch rollout/rollback:** feature flag, tương thích nhiều phiên bản và hành động bù.
12. **Ownership và lịch rà soát:** người chịu trách nhiệm, phụ thuộc và cập nhật sau incident.

Trước khi chốt, hãy rà soát:

- Hành trình và bất biến nghiệp vụ đã được mô tả rõ chưa?
- Mọi điểm tích hợp có provider, consumer, contract và owner chưa?
- Luồng đồng bộ và bất đồng bộ có được phân biệt không?
- Rủi ro timeout sau tác dụng phụ, retry, duplicate và event sai thứ tự đã được kiểm tra chưa?
- Có test cho quyền, tenant isolation và dữ liệu nhạy cảm không?
- Oracle có dựa trên nguồn dữ liệu có thẩm quyền không?
- Mỗi rủi ro quan trọng có test ở cấp phù hợp và có bằng chứng không?
- Sandbox, test double và phụ thuộc thật được dùng có chủ đích không?
- Dữ liệu có cô lập theo run và cleanup/đối soát được không?
- Pipeline có gate và fallback rõ khi môi trường hoặc provider không khả dụng không?
- Có trace và artifact đủ để điều tra xuyên dịch vụ không?
- Rollout và rollback có xử lý dữ liệu, message và tác dụng phụ bên ngoài không?
- Owner và hành động còn thiếu đã được ghi nhận chưa?

Thiết kế chiến lược cho chức năng mới có nhiều điểm tích hợp đòi hỏi nhìn toàn bộ hành trình cùng các ranh giới nơi dữ liệu và tác dụng phụ đi qua. Khi nhóm kết hợp bản đồ phụ thuộc, phân tích rủi ro, test ở nhiều cấp, mô phỏng lỗi một phần, dữ liệu cô lập và bằng chứng có thể truy vết, chiến lược sẽ kiểm tra được cả kết quả nghiệp vụ lẫn độ bền của các tương tác. Hãy bắt đầu từ những rủi ro có hậu quả lớn, xác minh từng boundary và mở rộng đến hành trình tổng thể trước khi chốt điều kiện phát hành.

