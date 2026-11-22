# Đánh giá giao tiếp quá nhiều giữa những dịch vụ liên quan

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Ranh giới dịch vụ

## 1. Khi nào giao tiếp giữa microservices trở thành vấn đề?

Microservices được thiết kế để các năng lực nghiệp vụ có thể thay đổi và vận hành tương đối độc lập. Tuy nhiên, khi một tác vụ nhỏ phải gọi liên tục giữa nhiều service, kiến trúc có thể rơi vào trạng thái **chatty services**: số lượt giao tiếp qua mạng nhiều hơn mức cần thiết để hoàn thành công việc.

Ví dụ: để hiển thị một giỏ hàng gồm 20 sản phẩm, service Checkout gọi Catalog 20 lần để lấy tên, gọi Pricing 20 lần để lấy giá và gọi Inventory 20 lần để lấy tồn kho. Một yêu cầu của người dùng tạo ra ít nhất 60 lời gọi nội bộ, chưa tính xác thực, khuyến mãi và phí vận chuyển.

    Người dùng
       |
       v
    Checkout
       |---- Catalog.getProduct(id_1) ... getProduct(id_20)
       |---- Pricing.getPrice(id_1)  ... getPrice(id_20)
       '---- Inventory.getStock(id_1) ... getStock(id_20)

Kết quả có thể đúng về mặt chức năng, nhưng đường xử lý chịu nhiều round trip, số kết nối, hàng đợi, timeout và điểm thất bại. Nếu các service còn phải sửa và triển khai cùng nhau cho hầu hết thay đổi, ranh giới hiện tại có thể đã tạo ra **distributed monolith**.

**Không có ngưỡng cố định “trên N request là sai”.** Giao tiếp nhiều chỉ đáng lo khi làm tăng đáng kể chi phí thực thi, tạo phụ thuộc không cần thiết hoặc phản ánh ranh giới nghiệp vụ thiếu phù hợp. Mục tiêu là đánh giá bằng chứng, lý do nghiệp vụ và chi phí thay đổi, thay vì đếm số service hay số API một cách máy móc.

## 2. Phân biệt giao tiếp cần thiết và giao tiếp quá mức

Một số hệ thống có nhu cầu trao đổi message thường xuyên là hoàn toàn hợp lý, chẳng hạn phân phối telemetry, stream dữ liệu theo thời gian thực hoặc điều phối tiến trình nhiều bước. Vấn đề không chỉ nằm ở **tần suất** mà nằm ở cách tương tác gắn các service với nhau.

| Góc nhìn | Dấu hiệu bình thường hoặc có lý do | Tín hiệu cần điều tra |
| --- | --- | --- |
| Mục đích | Trao đổi kết quả ở ranh giới năng lực rõ ràng | Gọi từng service chỉ để ghép trường dữ liệu nội bộ |
| Độ hạt | Một API diễn đạt tác vụ nghiệp vụ đủ hoàn chỉnh | Nhiều API CRUD rất nhỏ bắt caller tự dựng business logic |
| Thời điểm | Dùng bất đồng bộ khi không cần phản hồi tức thời | Chặn toàn bộ request để chờ tác vụ không quyết định kết quả |
| Sở hữu dữ liệu | Mỗi service bảo vệ bất biến dữ liệu của mình | Service khác phải hỏi từng trường hoặc ghi trực tiếp bảng của nhau |
| Triển khai | Thay đổi nội bộ không bắt service khác phát hành đồng thời | Đổi một quy tắc nhỏ buộc nhiều service đổi contract cùng lúc |
| Sự cố | Dependency lỗi được xử lý trong ranh giới nghiệp vụ cho phép | Một service phụ trợ chậm làm cả hành trình ngừng hoạt động |

Một request thanh toán phải gọi Payment qua mạng là phụ thuộc nghiệp vụ hợp lý. Nhưng Payment phải gọi Pricing nhiều lần để biết từng phép tính chi tiết, rồi Ordering gọi lại Pricing để tính cùng một kết quả, là tín hiệu cần kiểm tra ranh giới và hợp đồng.

## 3. Các biểu hiện thường gặp

### 3.1. N+1 remote calls

Ứng dụng lấy danh sách N bản ghi, sau đó gọi một service khác N lần để lấy thông tin cho từng bản ghi:

    orderItems = order.getItems()
    for item in orderItems:
        item.price = pricing.getPrice(item.productId)

Với 100 dòng hàng, vòng lặp phát 100 remote calls. Đây là dạng **N+1** ở tầng dịch vụ: một lần lấy danh sách, nhiều lần tải phần phụ thuộc theo từng phần tử. Có thể khắc phục bằng API theo lô nếu nghiệp vụ cho phép, ví dụ `getPrices(productIds, priceContext)`, nhưng vẫn phải xét phiên bản giá, ngữ cảnh khách hàng và quy tắc tính theo cả giỏ hàng.

### 3.2. Chuỗi lời gọi đồng bộ quá dài

    Gateway → Checkout → Ordering → Pricing → Promotion → Tax
                                  → Inventory → Warehouse

Nếu một service phải đợi kết quả service tiếp theo mới trả về, latency và tính sẵn sàng của hành trình phụ thuộc vào toàn bộ chuỗi. Chuỗi dài không tự động sai; cần xác định bước nào thật sự thuộc đường phản hồi tức thời và bước nào có thể hoãn.

### 3.3. Ping-pong giữa hai service

Ví dụ Ordering hỏi Payment trạng thái giao dịch, Payment lại gọi Ordering để lấy chi tiết đơn, Ordering gọi Payment để tính lại điều kiện thanh toán. Nếu xuất hiện vòng tương tác hoặc service phụ thuộc vào dữ liệu nội bộ của nhau ở nhiều bước, đây có thể là dấu hiệu hợp đồng chưa thể hiện rõ quyền sở hữu trách nhiệm.

### 3.4. Fan-out lớn cho một yêu cầu

Một API tổng hợp gọi 15 service song song để dựng màn hình quản trị. Dù tổng thời gian có thể gần nhánh chậm nhất, nó vẫn làm tăng số nguồn lỗi và tài nguyên sử dụng. Nếu cần đủ 15 kết quả mới trả về, một service phụ trợ lỗi có thể khiến cả màn hình thất bại.

### 3.5. Cập nhật trạng thái bằng nhiều lời gọi rất nhỏ

Ví dụ một business action phải lần lượt gọi `reserveItem`, `decreaseAvailable`, `addAudit`, `setReservationState` vào cùng một service. Caller đang điều phối chi tiết bất biến của service đích, thay vì gọi một thao tác nghiệp vụ như `reserveInventoryForOrder`. Các thao tác nhỏ có thể cần giữ atomically ở nơi sở hữu dữ liệu.

## 4. Tại sao “nhiều lời gọi” ảnh hưởng đến thời gian phản hồi?

Mỗi remote call có thể thêm chi phí truyền qua mạng, mã hóa/giải mã, routing, authentication, TLS, chờ connection pool, queueing, xử lý server và truyền phản hồi. Ngay cả khi payload rất nhỏ, round trip vẫn có chi phí.

### 4.1. Chi phí gọi nối tiếp

Giả sử một request thực sự thực hiện 12 lời gọi nối tiếp, mỗi lời gọi trong lần quan sát đó mất 15 ms do tổng thời gian mạng và xử lý:

    12 lời gọi × 15 ms/lời gọi = 180 ms

Đó mới chỉ là thời gian của 12 lời gọi, chưa tính các phần khác. Nếu đổi thành một batch API mà kết quả đủ và thời gian thực tế 35 ms, request tiết kiệm khoảng 145 ms trong ví dụ giả định. **Kết quả thực tế phải đo lại** vì batch có thể gây CPU cao hơn, dữ liệu lớn hơn hoặc đường truy vấn phức tạp hơn.

Không cộng các giá trị p95 của từng service rồi khẳng định đó là p95 end-to-end. Phân vị phụ thuộc phân bố, thứ tự và tương quan giữa các lời gọi; cần đo trực tiếp cả hành trình.

### 4.2. Tác động lên khả năng thành công

Nếu một hành trình cần 12 lời gọi bắt buộc đều thành công và mỗi lần có xác suất thành công 99,9% trong điều kiện độc lập, xác suất tất cả thành công xấp xỉ:

    0,999^12 ≈ 98,81%

Đây là ví dụ mô hình đơn giản, **không phải tỷ lệ availability dự đoán cho production**. Những lỗi thường có tương quan do cùng vùng mạng, cơ sở dữ liệu hoặc hạ tầng; hệ thống có thể có retry, cache và fallback. Tuy nhiên mô hình minh họa vì sao nhiều điểm phụ thuộc đồng bộ làm tăng bề mặt sự cố.

### 4.3. Khuếch đại tải (request amplification)

Giả sử mỗi request từ client tạo ra 40 lời gọi nội bộ. Với 200 request client/giây, các downstream có thể nhận tổng khoảng 8.000 lời gọi/giây nếu mẫu truy cập và tải ổn định. Nếu có retry đồng thời ở nhiều tầng, lượng gọi thực tế còn tăng.

Khi một downstream chậm, upstream giữ thread và connection lâu hơn, dẫn đến hàng đợi tăng và timeout lan rộng. Tốc độ lỗi có thể tăng rất nhanh dù lưu lượng người dùng không đổi.

## 5. Tìm bằng chứng bằng distributed tracing và metrics

Đánh giá chatty communication cần gắn với **một hành động của người dùng hoặc một business operation**, không chỉ bảng thống kê số HTTP request tổng.

### 5.1. Truy vết theo hành trình nghiệp vụ

Đặt trace ID xuyên suốt Gateway, service gọi và service được gọi. Với mỗi trace, quan sát:

- Số span outbound theo downstream và endpoint.
- Số lời gọi **nối tiếp**, số lời gọi **song song**, chiều sâu dependency chain và những lần gọi lặp đến cùng endpoint.
- Thời gian nằm ở remote calls so với thời gian xử lý nội bộ.
- Số lần retry, timeout, response lỗi và phân bổ theo vị trí.
- Payload request/response, lượng dữ liệu truyền đi và sự lặp lại dữ liệu.
- Mối quan hệ giữa các span và loại thao tác nghiệp vụ, như `CreateOrder` hoặc `ViewCart`.

Một trace duy nhất cho thấy tình huống cụ thể, nhưng không đủ để suy ra xu hướng. Cần kết hợp thống kê p50/p95/p99, tập mẫu đủ đại diện, lưu lượng cao điểm và phân nhóm theo loại request. Nếu tracing sampling, phải hiểu mức sampling trước khi kết luận tỷ lệ.

### 5.2. Chỉ số nên đặt cạnh nhau

| Chỉ số | Ý nghĩa thực tế |
| --- | --- |
| Internal calls per business request | Mức khuếch đại lời gọi từ một tác vụ người dùng |
| Synchronous dependency depth | Độ dài đường chờ đồng bộ bắt buộc |
| Fan-out width | Số dependency song song mà thao tác gọi |
| Repeated calls to same endpoint | Dấu hiệu N+1, đọc dữ liệu lặp, contract quá vụn |
| Remote time share | Tỷ trọng thời gian request dành cho chờ downstream |
| p95/p99 end-to-end latency | Trải nghiệm phần chậm của người dùng |
| Dependency timeout/error rate | Phần tác động của giao tiếp lỗi |
| Retry amplification | Lượng gọi thêm do retry |
| Cross-service change coupling | Bao nhiêu service phải đổi cùng nhau cho một yêu cầu |
| Joint release frequency | Hai service có buộc phát hành đồng bộ thường xuyên không? |

Ví dụ bảng quan sát **giả định** cho cùng endpoint:

| Trạng thái | Lời gọi nội bộ/request | Chuỗi đồng bộ sâu nhất | p95 end-to-end |
| --- | ---: | ---: | ---: |
| Trước cải tiến | 64 | 7 bước | 930 ms |
| Sau dùng batch và bỏ lời gọi lặp | 9 | 4 bước | 410 ms |

Các số trong bảng chỉ minh họa cách trình bày trước/sau, không phải kết quả đo từ một hệ thống thật. Ngoài tốc độ, cần ghi nhận tỷ lệ lỗi, CPU, network egress, throughput và ảnh hưởng nhất quán dữ liệu để biết cải tiến có thực sự tốt hơn.

## 6. Tìm nguyên nhân ở ranh giới nghiệp vụ

Đếm request chỉ giúp biết **triệu chứng**. Câu hỏi quan trọng là: vì sao thông tin hoặc trách nhiệm lại bị chia thành các điểm mà mọi thao tác phải chạy qua?

### 6.1. Tách service theo bảng hoặc thao tác CRUD

Nếu có `UserService`, `AddressService`, `OrderLineService`, `DiscountRuleService` chỉ vì mỗi bảng có repository riêng, một năng lực nghiệp vụ có thể phải truy cập hàng chục service để hoàn tất. Kích thước class và số bảng không phải tiêu chí tốt để xác định microservice.

Cần quay về **business capability**, **bounded context**, bất biến dữ liệu và lý do thay đổi của từng năng lực.

### 6.2. Hợp đồng API quá chi tiết

Ví dụ `getBasePrice`, `getTaxRate`, `getPromotion`, `getMemberTier`, `calculateDiscount` buộc Ordering tự ghép các quy tắc giá. Có thể chính Pricing nên sở hữu thao tác `quoteOrder` trả về một báo giá hợp lệ với các thông tin cần thiết.

Đây không nhất thiết là “gộp nhiều endpoint thành một URL”; vấn đề là đưa **quyết định nghiệp vụ** về đúng nơi sở hữu nó.

### 6.3. Đọc chéo dữ liệu vì quyền sở hữu không rõ

Service A liên tục yêu cầu các trường nội bộ của B để tự đưa ra quyết định thuộc domain B. Điều này tạo knowledge coupling, làm nhiều client phải sửa mỗi khi B đổi cách lưu dữ liệu.

Nếu A thực sự cần một quyết định của B, API nên thể hiện quyết định đó. Nếu A cần dữ liệu để phục vụ màn hình đọc tổng hợp, có thể dùng mô hình đọc riêng với dữ liệu được sao chép có kiểm soát, thay vì ép A thao tác trực tiếp với bảng của B.

### 6.4. Phối hợp quá nhiều trong đường đồng bộ

Một service orchestrator đồng bộ toàn bộ công việc, kể cả gửi email, cập nhật chỉ mục tìm kiếm, ghi analytics và tạo báo cáo. Nếu các tác vụ sau không quyết định phản hồi nghiệp vụ, chờ chúng khiến hành trình dài và dễ lỗi không cần thiết.

Chuyển sang sự kiện bất đồng bộ cần có hợp đồng event, xử lý trùng, retry, dead-letter, thứ tự và khả năng đối soát. Đây là thay đổi ngữ nghĩa xử lý, không chỉ chuyển từ REST sang message broker.

### 6.5. Các service không có khả năng thay đổi độc lập

Hai service thường gọi nhau nhiều chưa đủ chứng minh phải gộp. Nhưng nếu chúng **liên tục phải đổi cùng nhau**, dùng chung bất biến nghiệp vụ, không thể triển khai tương thích và cùng một nhóm chịu trách nhiệm, cần đánh giá liệu ranh giới tách hiện tại có hợp lý hay không.

## 7. Tình huống: giỏ hàng 20 sản phẩm

Giả sử `CartService` cần hiển thị danh sách gồm tên, ảnh, giá, khuyến mãi và trạng thái hàng còn bán được.

**Thiết kế nhiều lời gọi:**

    GET /cart
      → CartService
        → Catalog.getProduct(id) × 20
        → Pricing.getPrice(id) × 20
        → Inventory.getAvailability(id) × 20

Tùy cách thực thi, 60 lời gọi này có thể nối tiếp, song song giới hạn hoặc hoàn toàn song song. Mỗi dạng có trade-off riêng; số 60 chỉ biểu thị lượng giao tiếp, không tự suy ra latency.

**Hướng cải thiện ở mức hợp đồng:**

    GET /cart
      → CartService
        → Catalog.getProducts(ids)
        → Pricing.quoteCart(items, customerContext)
        → Inventory.getAvailability(ids)

Ví dụ này giảm số lời gọi theo item, đồng thời để Pricing sở hữu quy tắc định giá cả giỏ hàng. Các lời gọi chỉ được chạy song song khi dữ liệu và quy tắc nghiệp vụ cho phép.

Những điều phải làm rõ:

- Giá trả về có hiệu lực bao lâu? Có `quoteId`, `expiresAt` và bối cảnh tiền tệ/thuế không?
- Tồn kho hiển thị là dữ liệu tham khảo hay lời hứa giữ hàng? Nếu chỉ tham khảo, khi checkout vẫn cần kiểm tra/giữ hàng đúng bất biến.
- Quy tắc giảm giá có phụ thuộc tổng giỏ, khách hàng, thị trường và thời điểm không?
- Khi Catalog mất kết nối, có được hiển thị tên/ảnh từ cache không? Khi Payment mất kết nối, có được xác nhận đơn không?

**Điểm chính:** API có độ hạt phù hợp phải thể hiện ý định nghiệp vụ và các bất biến cần bảo vệ, không chỉ gom nhiều thao tác CRUD vào một payload lớn.

## 8. Các chiến lược giảm giao tiếp quá mức

### 8.1. Batch API và bulk reads

Thay N lời gọi cùng kiểu bằng một lời gọi theo danh sách ID hoặc một thao tác nghiệp vụ cho nhiều item. Phù hợp khi caller thực sự cần cùng một tập dữ liệu. Cần quy định giới hạn kích thước batch, lỗi từng item, pagination khi cần, phiên bản dữ liệu và cách bảo toàn ngữ nghĩa.

### 8.2. Thiết kế API theo thao tác nghiệp vụ

Đổi từ các thao tác vụn như `getBalance` + `debit` + `writeLedger` sang thao tác nghiệp vụ có quyền sở hữu rõ, ví dụ `authorizePayment`. Trong domain tài chính, việc gom logic phải đi kèm ràng buộc nguyên tử, idempotency và kiểm toán; không thể coi việc đổi tên API đã giải quyết tính đúng đắn.

### 8.3. Cache có chiến lược

Cache giúp giảm lời gọi lặp khi dữ liệu ít thay đổi hoặc chấp nhận độ trễ cập nhật. Phải xác định TTL, chính sách invalidation, độ nhạy dữ liệu, phạm vi key, cách phòng stampede và hành vi khi dữ liệu cũ.

Không dùng cache cho quyết định tiền, số dư hay giữ tài nguyên khi dữ liệu stale có thể phá bất biến mà không có cơ chế xác minh.

### 8.4. Read model hoặc dữ liệu sao chép phục vụ truy vấn

Với màn hình tổng hợp cần dữ liệu từ nhiều domain, có thể tạo projection được cập nhật qua event hoặc pipeline dữ liệu. Query lúc đó đọc một mô hình được tối ưu riêng.

Đánh đổi là **eventual consistency**, việc xử lý event bị trùng/mất thứ tự, schema evolution, xử lý rebuild và cơ chế phát hiện lệch dữ liệu. Phải công bố độ mới mong đợi và nơi dữ liệu gốc được sở hữu.

### 8.5. Bất đồng bộ hóa tác vụ không nằm trên critical path

Email, analytics, cập nhật search index và những side effect được phép xử lý sau có thể nhận message/event thay vì buộc phản hồi checkout đợi. Cần outbox hoặc cơ chế tin cậy tương đương khi phải phối hợp commit dữ liệu với phát event; consumer phải an toàn với message lặp.

### 8.6. Gộp hoặc điều chỉnh lại ranh giới service

Nếu một nhóm thao tác luôn cần chung transaction, chung business invariant và thay đổi cùng nhau, hãy đánh giá đưa chúng về cùng một ranh giới sở hữu. Có thể gộp service hoặc chuyển trách nhiệm giữa các service; mục tiêu là giảm coupling và bảo vệ tính đúng đắn.

Gộp không phải giải pháp mặc định cho mọi lời gọi nhiều. Một service lớn có thể tạo nghẽn thay đổi và deploy, nên quyết định cần dựa trên mô hình domain và chi phí vận hành tổng thể.

### 8.7. Chạy song song đúng nơi

Nếu nhiều dependency độc lập, caller có thể gọi đồng thời với giới hạn concurrency và deadline chung. Điều này giảm thời gian chờ nối tiếp nhưng không giảm số request, tổng tải hay bề mặt lỗi. Fan-out quá rộng có thể làm tăng tail latency và áp lực lên downstream.

## 9. So sánh các lựa chọn và trade-off

| Cách tiếp cận | Thường cải thiện | Chi phí hoặc rủi ro mới |
| --- | --- | --- |
| Batch API | Nhiều round trip cho các thao tác cùng loại | Payload lớn, lỗi một phần, API có thể trở thành quá tổng quát |
| Business-oriented API | Caller không tự điều phối invariant nội bộ | Cần xác định rõ chủ sở hữu nghiệp vụ |
| Cache | Lời gọi đọc lặp lại, giảm tải | Staleness, invalidation, cache miss đồng loạt |
| Read projection | Truy vấn tổng hợp nhiều domain | Đồng bộ event, lag, dữ liệu dẫn xuất và rebuild |
| Async event | Giảm chờ trên đường phản hồi | Eventual consistency, retry, trùng, thứ tự, đối soát |
| Parallel requests | Độ trễ do tuần tự hóa không cần thiết | Fan-out, dùng thêm tài nguyên, lỗi nhánh |
| Gộp service | Hạn chế vòng gọi và chia sẻ invariant phức tạp | Tăng kích thước đơn vị triển khai, ảnh hưởng ownership |
| Giới hạn concurrency / timeout | Giảm lỗi lan truyền khi dependency chậm | Không trực tiếp loại bỏ coupling hoặc request dư thừa |

Khi lựa chọn, nên phân biệt **tối ưu hiệu năng cục bộ** với **sửa ranh giới kiến trúc**. Batch hoặc cache có thể cải thiện p95 ngay, nhưng nếu mỗi lần đổi quy tắc vẫn buộc nhiều nhóm phát hành đồng thời, bài toán coupling vẫn còn.

## 10. Quy trình đánh giá có thể áp dụng trong dự án

**Bước 1 — Chọn một hành trình cụ thể.** Ví dụ `ViewCart`, `CreateOrder`, `ApplyPromotion` hoặc `RefundPayment`. Xác định kết quả người dùng mong đợi, SLO và bất biến nghiệp vụ.

**Bước 2 — Dựng dependency graph thực tế.** Lấy tracing, log và metrics trong các khung giờ đại diện. Vẽ service gọi ai, endpoint nào, số lần gọi, thứ tự và điều kiện phải chờ kết quả.

**Bước 3 — Khoanh vùng lời gọi đáng nghi.** Tìm N+1, lặp dữ liệu, vòng A→B→A, chuỗi đồng bộ dài, fan-out rộng và retry amplification. Ghi nhận latency, lỗi, network egress và tải.

**Bước 4 — Hỏi ai sở hữu quyết định nghiệp vụ.** Với mỗi lời gọi, xác định: đang lấy thông tin, yêu cầu một quyết định, ghi thay đổi trạng thái hay phát một sự kiện? Thao tác đó thuộc bounded context nào? Có cần cùng transaction không?

**Bước 5 — Thiết kế một thay đổi nhỏ có thể kiểm chứng.** Ví dụ đưa vòng `getPrice(item)` sang `quoteCart` do Pricing sở hữu. Định nghĩa contract, versioning, lỗi một phần, deadline, giới hạn batch, bảo mật và nhất quán.

**Bước 6 — Đo lại cùng loại hành trình và điều kiện tải.** So sánh internal calls/request, dependency depth, p95/p99 end-to-end, error rate, CPU, memory, network egress và thời gian thay đổi nghiệp vụ. Không tuyên bố thành công chỉ vì số request giảm.

**Bước 7 — Kiểm tra chi phí thay đổi.** Sau vài lần phát hành, xem service có triển khai độc lập hơn không, hay chỉ chuyển logic phức tạp sang một orchestrator mới.

## 11. Những câu hỏi xác định có nên gộp hai service

Khi hai service liên quan giao tiếp liên tục, có thể dùng những câu hỏi sau:

1. Chúng có phải cùng bảo vệ một business invariant cần transaction nhất quán cao không?
2. Một yêu cầu nghiệp vụ thường buộc cả hai cùng sửa và deploy không?
3. Có đường vòng A→B→A hoặc một service phải biết chi tiết lưu trữ của service kia không?
4. Có thể định nghĩa một hợp đồng nghiệp vụ ổn định ở giữa, thay cho nhiều lời gọi nhỏ không?
5. Hai nhóm có ownership và nhịp phát hành thực sự khác nhau không?
6. Hai phần có yêu cầu mở rộng, bảo mật, độ tin cậy hoặc pháp lý khác biệt đáng kể không?
7. Nếu gộp, khả năng cô lập lỗi và triển khai độc lập có bị suy giảm quá mức không?
8. Có giải pháp ít xáo trộn hơn như batch API, read model hoặc chuyển một nghiệp vụ về đúng service sở hữu không?

Không cần mọi câu trả lời đều nghiêng về gộp mới điều chỉnh được kiến trúc. Có trường hợp service vẫn nên tách vì ranh giới nghiệp vụ rõ, nhưng cần thay contract hoặc cách truy vấn.

## 12. Sai lầm khi tối ưu giao tiếp

- **Chỉ giảm số HTTP calls:** một request tổng hợp quá lớn, trả dữ liệu thừa hoặc làm server nghẽn có thể tệ hơn nhiều lời gọi nhỏ hợp lý.
- **Cho mọi service đọc chung database:** có thể giảm round trip trong ngắn hạn nhưng phá quyền sở hữu dữ liệu, tăng coupling và khó triển khai schema độc lập.
- **Dùng cache để che sai ranh giới:** cache không giải quyết quyền sở hữu quy tắc nghiệp vụ hoặc vấn đề cập nhật nhất quán.
- **Đổi sang event cho mọi trường hợp:** các thao tác cần kết quả ngay có thể không phù hợp; sự kiện mang chi phí vận hành và dữ liệu trễ.
- **Coi mọi lời gọi liên domain là sai:** một tác vụ nghiệp vụ thật sự cần phối hợp nhiều năng lực thì việc giao tiếp là có lý do.
- **Gộp mọi service gọi nhau nhiều:** có thể tạo service quá lớn, nghẽn deploy và tăng blast radius.
- **Tối ưu theo trace đơn lẻ:** phải có dữ liệu theo thời gian, loại request, tải và tình trạng lỗi.
- **Bỏ qua retries:** số lượt gọi thực tế khi downstream lỗi có thể lớn hơn rất nhiều so với đồ thị lúc hệ thống khỏe.
- **Bỏ qua tính đúng đắn:** mục tiêu không thể là nhanh hơn nhưng tính sai giá, thu tiền trùng hoặc mất trạng thái đơn hàng.

## 13. Bài tập thực hành

Hệ thống bán hàng có luồng `GET /orders/{id}/summary`:

    API
      → OrderService.getOrder(id)                  (1 lần)
      → CustomerService.getCustomer(customerId)   (1 lần)
      → CatalogService.getProduct(productId)       (12 lần)
      → PricingService.getCurrentPrice(productId)  (12 lần)
      → ShippingService.getShipment(orderId)       (1 lần)

Hãy thảo luận:

1. Tổng số remote calls trong ví dụ là bao nhiêu? Service nào có dấu hiệu N+1?
2. Vì sao dùng “giá hiện tại” để hiển thị lại đơn hàng đã thanh toán có thể sai nghiệp vụ?
3. Có thể lưu snapshot giá và tên hàng trong đơn tại thời điểm mua để tránh phụ thuộc khi đọc lịch sử không? Điều này tác động gì đến việc sửa dữ liệu sản phẩm?
4. Khi nào nên batch `Catalog.getProducts(ids)`, khi nào cần projection riêng cho màn hình?
5. Nếu Shipping chậm, trang đơn hàng có thể hiển thị phần thông tin đã có và trạng thái vận chuyển tải sau hay không? Yêu cầu UX và nghiệp vụ quyết định như thế nào?
6. Những số liệu nào cần đo trước và sau thay đổi để chứng minh lợi ích mà không làm sai tính đúng đắn?

**Gợi ý:** tổng cộng 27 remote calls nếu mỗi lần ghi trên sơ đồ được phát thật một lần: 1 + 1 + 12 + 12 + 1. Nhưng ưu tiên đầu tiên là hiểu dữ liệu nào thuộc snapshot bất biến của đơn hàng, dữ liệu nào chỉ phục vụ hiển thị, dữ liệu nào bắt buộc phải cập nhật thời gian thực.

## 14. Ghi nhớ

“Chatty services” là **triệu chứng của giao tiếp vượt quá nhu cầu hợp lý của một thao tác nghiệp vụ**. Nó có thể gây độ trễ cộng dồn, khuếch đại tải, tăng rủi ro timeout và làm lộ ranh giới dịch vụ chưa phù hợp.

Đánh giá đúng cần kết hợp **tracing và metrics theo hành trình**, phân tích kiểu gọi (N+1, chain, fan-out, vòng), quyền sở hữu dữ liệu, invariant và tần suất thay đổi đồng thời. Cải tiến có thể là batch, API theo nghiệp vụ, cache, read projection, bất đồng bộ, gọi song song hoặc điều chỉnh ranh giới service. Chọn giải pháp giúp hành trình nhanh và đáng tin cậy hơn **đồng thời giữ được tính đúng đắn và khả năng thay đổi độc lập**.
