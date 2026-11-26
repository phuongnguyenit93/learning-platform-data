# Cân bằng tính đơn giản, khả năng kiểm thử, hiệu năng và mở rộng

Một thiết kế kiến trúc tốt không phải là thiết kế có nhiều tầng, nhiều interface hay nhiều dịch vụ nhất. Nó là thiết kế đáp ứng được nhu cầu hiện tại, giữ được đường đi hợp lý cho những thay đổi có khả năng xảy ra và không tạo ra chi phí phức tạp vượt quá lợi ích nhận được. Trong kiến trúc phân tầng, việc tách trách nhiệm giúp mã dễ hiểu và kiểm thử, nhưng thêm quá nhiều lớp trung gian có thể làm luồng xử lý khó lần theo. Tối ưu hiệu năng quá sớm có thể làm mã khó bảo trì; tách nhiều dịch vụ để mở rộng có thể tăng độ trễ và gánh nặng vận hành.

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, với mục tiêu học tổ chức phần mềm theo kiến trúc phân tầng. Trong chương **Sai lầm và đánh giá thiết kế**, ta xem cách cân bằng bốn mục tiêu: tính đơn giản, khả năng kiểm thử, hiệu năng và khả năng mở rộng; đồng thời học cách đưa ra quyết định dựa trên yêu cầu và số liệu thay vì áp dụng một công thức kiến trúc cho mọi dự án.

## Bốn mục tiêu có thể hỗ trợ hoặc xung đột nhau

| Mục tiêu | Thiết kế hướng tới | Chi phí hoặc rủi ro khi theo đuổi quá mức |
|---|---|---|
| Đơn giản | Ít khái niệm cần hiểu, luồng xử lý rõ, dễ thay đổi | Có thể gom quá nhiều trách nhiệm vào một nơi nếu hiểu đơn giản là ít file nhất |
| Khả năng kiểm thử | Quy tắc có thể kiểm tra độc lập, phụ thuộc được kiểm soát | Quá nhiều interface và mock có thể khiến test xa hành vi thực tế |
| Hiệu năng | Độ trễ, throughput và mức sử dụng tài nguyên đáp ứng mục tiêu | Cache, batch, concurrency hoặc tối ưu sớm có thể tăng trạng thái và độ phức tạp |
| Khả năng mở rộng | Có thể tăng tải, thêm tính năng hoặc mở rộng nhóm phát triển | Phân tán quá sớm làm tăng network hop, vận hành và đồng bộ dữ liệu |

Các mục tiêu không luôn đối lập. Tách một quy tắc nghiệp vụ khỏi controller có thể vừa làm mã dễ hiểu vừa giúp unit test nhanh hơn. Nhưng việc tạo một interface cho mỗi lớp chỉ để có thể mock có thể làm luồng gọi dài hơn mà không tăng khả năng thay đổi thực tế. Cần đánh giá lợi ích và chi phí trong bối cảnh cụ thể.

## Đơn giản là giảm độ phức tạp cần thiết

Đơn giản không đồng nghĩa với việc viết tất cả vào một controller hoặc một service khổng lồ. Một lớp có quá nhiều lý do thay đổi cũng khó hiểu và khó sửa. Đơn giản có nghĩa là mỗi thành phần có trách nhiệm rõ, các phụ thuộc dễ nhận biết và người đọc có thể theo dõi ca sử dụng mà không phải mở quá nhiều lớp không mang thêm ý nghĩa.

Ví dụ một ứng dụng quản lý đơn hàng nhỏ có thể bắt đầu với cấu trúc:

```text
orders
├── OrderController
├── OrderService
├── Order
└── OrderRepository
```

`OrderController` nhận request, `OrderService` điều phối ca sử dụng, `Order` bảo vệ trạng thái hợp lệ và `OrderRepository` truy cập dữ liệu. Cấu trúc này có thể đủ cho một ứng dụng CRUD có quy tắc đơn giản.

Nếu quy tắc định giá ngày càng phức tạp, nhiều luồng cùng sử dụng và cần kiểm thử độc lập, có thể thêm `PricingPolicy`. Nếu chưa có nhu cầu đó, không cần tạo sẵn `PricingPolicyFactory`, `PricingPolicyResolver`, `PricingPolicyProvider` và nhiều lớp bao quanh một phép tính nhỏ. Mỗi abstraction nên giải quyết một vấn đề có thật: che giấu chi tiết thay đổi, tạo ranh giới có ý nghĩa hoặc cho phép kiểm thử một quy tắc quan trọng.

### Dấu hiệu đang thiết kế quá mức

- Một ca sử dụng đi qua nhiều interface và lớp chuyển tiếp nhưng mỗi lớp chỉ gọi tiếp phương thức cùng tên.
- Có nhiều abstraction chỉ có một implementation ổn định và không có nhu cầu thay thế hoặc ranh giới kiểm thử có ý nghĩa.
- Cấu hình, factory và dependency injection chiếm nhiều công sức hơn phần nghiệp vụ.
- Nhóm phải hiểu framework hoặc pattern phức tạp để thay đổi một hành vi nhỏ.
- Package được tạo trước khi có nhóm trách nhiệm hoặc khái niệm thực sự cần tách.

Đây không phải quy tắc cấm interface hoặc factory. Một interface có thể cần thiết để đảo chiều phụ thuộc, tách adapter database hoặc định nghĩa hợp đồng giữa module. Câu hỏi review nên là “abstraction này bảo vệ điều gì?” thay vì “dự án có đủ số lượng interface chưa?”.

## Khả năng kiểm thử đến từ ranh giới đúng

Một thiết kế dễ kiểm thử giúp xác minh quy tắc nghiệp vụ mà không phải dựng toàn bộ hệ thống. Domain object hoặc policy thuần Java thường có thể kiểm thử bằng unit test. Application service có thể kiểm thử việc điều phối với repository giả. Repository và adapter cần integration test để xác minh truy vấn, ánh xạ và hành vi với hệ thống thật.

Ví dụ, quy tắc hủy đơn có thể được đặt trong domain model:

```java
public class Order {
    private OrderStatus status;

    public void cancel() {
        if (status != OrderStatus.PENDING
                && status != OrderStatus.CONFIRMED) {
            throw new OrderCannotBeCancelledException(status);
        }
        status = OrderStatus.CANCELLED;
    }
}
```

Unit test có thể kiểm tra trực tiếp các trạng thái:

```java
@Test
void cancelsPendingOrder() {
    Order order = Order.withStatus(OrderStatus.PENDING);

    order.cancel();

    assertEquals(OrderStatus.CANCELLED, order.status());
}

@Test
void rejectsCancellationAfterShipment() {
    Order order = Order.withStatus(OrderStatus.SHIPPED);

    assertThrows(OrderCannotBeCancelledException.class, order::cancel);
}
```

Nhờ quy tắc được đặt trong domain, test không cần khởi động Spring, mở HTTP server hoặc kết nối database. Tuy nhiên, unit test không chứng minh repository đang lưu đúng trạng thái hoặc endpoint đang ánh xạ lỗi đúng mã HTTP. Những hành vi đó cần test ở mức tích hợp hoặc API.

### Không biến mọi phụ thuộc thành mock

Mock hữu ích khi muốn cô lập application service khỏi một cổng bên ngoài hoặc kiểm tra một tương tác quan trọng. Nhưng nếu mock toàn bộ repository, mapper, factory, clock, policy và mọi lớp trung gian, test có thể chỉ xác nhận cách cài đặt hiện tại gọi nhau. Một thay đổi refactor vô hại có thể làm test thất bại dù hành vi người dùng không đổi.

Chọn loại test theo câu hỏi cần trả lời:

| Loại test | Nên dùng để xác minh | Không đủ để chứng minh |
|---|---|---|
| Unit test | Quy tắc và trường hợp biên của một đối tượng/policy | SQL, cấu hình Spring hoặc tích hợp mạng đúng |
| Application service test | Trình tự điều phối và phản ứng với kết quả phụ thuộc | Database thực thi truy vấn như mong đợi |
| Repository integration test | Query, mapping, transaction và constraint | Toàn bộ API hoặc giao diện người dùng |
| API/integration test | Luồng qua nhiều thành phần và hợp đồng bên ngoài | Mọi tổ hợp quy tắc có thể kiểm tra nhanh ở mức unit |
| Architecture test | Quy tắc phụ thuộc giữa package/module | Hành vi nghiệp vụ đúng với từng dữ liệu đầu vào |

Một bộ test cân bằng thường có nhiều test nhỏ, nhanh cho quy tắc, một số integration test cho các ranh giới kỹ thuật quan trọng và số lượng vừa đủ end-to-end test cho luồng người dùng cốt lõi. Không cần ép mọi dự án theo một tỷ lệ test cố định.

## Hiệu năng: đo trước khi tối ưu

Một ứng dụng phân tầng chạy trong cùng JVM thường chỉ tốn chi phí nhỏ cho lời gọi phương thức giữa các lớp. Những vấn đề hiệu năng lớn thường đến từ I/O, truy vấn database, gọi dịch vụ mạng, serialize dữ liệu, khóa cạnh tranh, cấp phát bộ nhớ hoặc xử lý lặp. Vì vậy, xóa một application service chỉ để giảm một lần gọi phương thức thường không giải quyết được nút thắt thực tế.

Hãy đo các chỉ số phù hợp với trải nghiệm và tải:

- Latency p50, p95 và p99 cho các API hoặc ca sử dụng quan trọng.
- Throughput, số request đồng thời và tỷ lệ lỗi.
- CPU, heap, garbage collection và allocation rate.
- Connection pool, thời gian chờ connection, query duration và số query mỗi request.
- Queue depth, thời gian chờ và thời gian xử lý tác vụ nền.

Ví dụ, nếu API danh sách đơn hàng mất 1,5 giây và trace cho thấy 1,2 giây nằm trong các truy vấn lặp để tải khách hàng, nút thắt có thể là N+1 query. Tối ưu bằng fetch strategy, projection, batch hoặc một query phù hợp có thể mang lại lợi ích lớn hơn việc gộp controller và service thành một lớp.

### Cân nhắc cache, batch và xử lý bất đồng bộ

| Kỹ thuật | Lợi ích | Chi phí và điều kiện cần xem xét |
|---|---|---|
| Cache | Giảm truy vấn lặp và thời gian phản hồi | Phải xử lý invalidation, dữ liệu cũ, eviction và cache stampede |
| Batch | Giảm số lần round-trip và overhead mỗi thao tác | Tăng kích thước request, bộ nhớ và độ trễ chờ đủ batch |
| Async/background job | Trả response sớm cho công việc có thể trì hoãn | Cần trạng thái công việc, retry, idempotency, quan sát và xử lý lỗi |
| Read model/projection | Trả dữ liệu đọc theo cấu trúc phù hợp, giảm join hoặc chuyển đổi | Phải đồng bộ với dữ liệu ghi và chấp nhận độ trễ cập nhật nếu có |
| Connection pooling | Tái sử dụng kết nối và giảm chi phí thiết lập | Pool quá lớn có thể làm database quá tải; quá nhỏ gây chờ |

Không chọn cache chỉ vì một truy vấn “có vẻ chậm”. Đo tần suất đọc, tỷ lệ thay đổi, mức độ chấp nhận dữ liệu cũ và chi phí invalidation trước. Nếu tính nhất quán cần cao, cache có thể tạo lỗi nghiệp vụ khó phát hiện hơn lợi ích hiệu năng.

## Khả năng mở rộng có nhiều chiều

Mở rộng không chỉ là thêm máy chủ. Có thể phân biệt:

- **Mở rộng theo tải:** xử lý nhiều request hoặc dữ liệu hơn, thường bằng scale-up, scale-out, cache, partitioning hoặc tối ưu dependency.
- **Mở rộng theo tính năng:** thêm quy tắc và use case mà không làm các phần hiện có rối hoặc phụ thuộc chéo.
- **Mở rộng theo nhóm phát triển:** nhiều nhóm có thể sở hữu và thay đổi các khu vực khác nhau với xung đột thấp.
- **Mở rộng vận hành:** triển khai, quan sát, khôi phục và thay đổi cấu hình mà không làm hệ thống khó kiểm soát.

Package theo tính năng, module boundaries và hợp đồng rõ ràng có thể hỗ trợ mở rộng theo tính năng và nhóm phát triển mà chưa cần tách thành microservice. Một modular monolith vẫn có thể có ranh giới module nghiêm túc và triển khai như một ứng dụng duy nhất.

### Khi nào cần tách tiến trình hoặc service?

Tách deployment có thể hợp lý khi một phần cần scale độc lập, có yêu cầu bảo mật hoặc cô lập lỗi khác biệt, có vòng đời triển khai riêng, hoặc được sở hữu bởi nhóm có trách nhiệm vận hành rõ. Nhưng khi tách, lời gọi nội bộ trở thành giao tiếp mạng: phát sinh latency, timeout, retry, xác thực service-to-service, serialization, observability và lỗi từng phần.

Trước khi tách, hãy cân nhắc:

1. Có số liệu cho thấy một phần đang là nút thắt và cần scale riêng không?
2. Ranh giới dữ liệu và quyền sở hữu có đủ rõ để giảm phụ thuộc đồng bộ không?
3. Hệ thống xử lý thế nào nếu service chậm, mất kết nối hoặc trả kết quả không xác định?
4. Có đội ngũ và hạ tầng để triển khai, giám sát, bảo mật và xử lý sự cố cho nhiều service không?
5. Lợi ích độc lập có lớn hơn chi phí giao tiếp, đồng bộ dữ liệu và vận hành không?

Không có số lượng tầng triển khai hay service bắt buộc. Một ứng dụng Spring Boot trong một tiến trình có thể đáp ứng tốt tải và nhu cầu tổ chức trong thời gian dài. Tách service là một lựa chọn khi có lý do cụ thể, không phải bước tiến tự động của mọi hệ thống.

## Một ví dụ cân bằng theo từng giai đoạn

Giả sử nhóm xây dựng hệ thống đặt lịch cho một phòng khám nhỏ. Ở giai đoạn đầu, một ứng dụng Spring Boot có thể gồm controller, application service, domain model và repository trong cùng tiến trình. Database là một tier riêng. Nhóm giữ các quy tắc như kiểm tra khung giờ và trạng thái lịch hẹn trong domain; controller chỉ xử lý HTTP. Unit test xác minh quy tắc, integration test kiểm tra repository và API test bao phủ luồng đặt lịch.

Khi số lượng lịch tăng, số liệu cho thấy truy vấn tìm khung giờ trống là nút thắt. Nhóm thêm index phù hợp, tối ưu query và kiểm thử tải. Nếu dữ liệu tra cứu ít thay đổi, có thể thử cache với thời hạn ngắn và chính sách invalidation rõ ràng. Không cần tách toàn bộ chức năng lịch hẹn thành một service mới nếu tối ưu database đã đáp ứng mục tiêu.

Sau này, chức năng gửi nhắc lịch có thể được đưa sang worker bất đồng bộ vì nó có tải và yêu cầu retry riêng, đồng thời không cần giữ request đặt lịch chờ email. Nhóm thêm outbox hoặc hàng đợi bền vững, idempotency và metric cho số job tồn đọng. Đây là một ranh giới triển khai có lý do cụ thể; phần quản lý lịch chính vẫn có thể nằm trong modular monolith.

Ví dụ cho thấy kiến trúc có thể tiến hóa theo bằng chứng. Mỗi lần thay đổi nên giải quyết một giới hạn đã quan sát được và giữ được khả năng vận hành, thay vì xây trước mọi cơ chế có thể cần trong tương lai.

## Quy trình đánh giá một quyết định thiết kế

Khi review một thay đổi kiến trúc, có thể dùng trình tự sau:

1. **Nêu mục tiêu có thể kiểm chứng.** Ví dụ p95 dưới 300 ms ở 200 request/giây, quy tắc hủy đơn được test độc lập, hoặc nhóm sản phẩm có thể triển khai mà không ảnh hưởng module đơn hàng.
2. **Xác định ràng buộc và mức quan trọng.** Bảo mật, tính đúng đắn dữ liệu, thời gian phản hồi, chi phí vận hành và năng lực nhóm có thể có mức ưu tiên khác nhau.
3. **Đo trạng thái hiện tại.** Dùng profiling, metrics, tracing, test và phản hồi từ nhóm vận hành để xác định vấn đề thực sự.
4. **So sánh phương án nhỏ nhất đáp ứng mục tiêu.** Có thể là sửa query, tách policy, thêm test, tạo module boundary hoặc tách một worker.
5. **Đánh giá chi phí mới.** Xem số khái niệm, điểm lỗi, network hop, trạng thái cần đồng bộ, công sức test và yêu cầu vận hành được thêm vào.
6. **Triển khai từng bước và đo lại.** Giữ khả năng rollback thay đổi triển khai, so sánh trước/sau và điều chỉnh nếu lợi ích không xuất hiện.

Một quyết định tốt nên ghi rõ bối cảnh, mục tiêu, phương án đã chọn, trade-off chấp nhận và tín hiệu cho biết khi nào cần xem xét lại. Không cần viết tài liệu dài cho mọi thay đổi nhỏ; một ghi chú ngắn cũng có thể đủ nếu lý do và hệ quả được hiểu rõ.

## Checklist cân bằng kiến trúc

| Câu hỏi review | Dấu hiệu tích cực |
|---|---|
| Luồng ca sử dụng có dễ theo dõi không? | Mỗi lớp có trách nhiệm và lý do tồn tại rõ |
| Quy tắc quan trọng có kiểm thử độc lập không? | Domain/policy test không cần khởi động toàn bộ hệ thống |
| Test có xác minh hành vi thực ở ranh giới kỹ thuật không? | Có integration test cho query, transaction và adapter quan trọng |
| Hiệu năng có được đo không? | Có latency, throughput, saturation và trace theo dependency |
| Tối ưu có giải quyết nút thắt đã xác định không? | Có số liệu trước/sau và giới hạn được mô tả |
| Mở rộng có lý do cụ thể không? | Nhu cầu scale, ownership, bảo mật hoặc cô lập lỗi đã rõ |
| Độ phức tạp mới có được tính đến không? | Có kế hoạch vận hành, quan sát, bảo mật và khôi phục |

## Chọn kiến trúc phù hợp thay vì kiến trúc lớn nhất

Tính đơn giản, khả năng kiểm thử, hiệu năng và khả năng mở rộng là những mục tiêu cần được cân bằng liên tục. Tách trách nhiệm vừa đủ giúp quy tắc nghiệp vụ rõ và dễ kiểm thử; đo đạc giúp xác định nơi cần tối ưu; ranh giới module rõ giúp hệ thống phát triển mà không buộc phải phân tán sớm. Ngược lại, quá ít cấu trúc có thể tạo khối mã khó thay đổi, còn quá nhiều abstraction hoặc service có thể làm hệ thống đắt đỏ và khó vận hành.

Hãy bắt đầu từ yêu cầu và quy mô hiện tại, giữ các ranh giới logic có ý nghĩa, đo những giới hạn thực tế rồi mở rộng đúng nơi cần thiết. Không có một cách chia tầng, tỷ lệ test hay số lượng service phù hợp cho mọi dự án; chất lượng thiết kế nằm ở việc hiểu rõ trade-off và có thể giải thích vì sao lựa chọn đó đáp ứng mục tiêu của hệ thống.
