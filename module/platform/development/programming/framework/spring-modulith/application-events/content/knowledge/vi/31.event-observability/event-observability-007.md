# Theo dõi publication

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, một application event có thể được giao đến nhiều listener thuộc các module khác nhau. Khi listener chạy bất đồng bộ, xử lý lỗi hoặc được phục hồi sau khi ứng dụng restart, chỉ biết publisher đã gọi `publishEvent` là chưa đủ để kết luận sự kiện đã được xử lý. Spring Modulith Event Publication Registry ghi nhận publication và theo dõi kết quả giao đến từng listener, tạo cơ sở để quan sát backlog, phát hiện publication bị kẹt và phục hồi công việc chưa hoàn tất.

Theo dõi publication cần trả lời được ba câu hỏi: event nào đang chờ listener nào, nó đã chờ bao lâu và vì sao chưa hoàn tất. Từ đó nhóm vận hành có thể phân biệt tải tăng bình thường với lỗi thực sự, chọn đúng publication để điều tra hoặc resubmit và đo được chất lượng giao sự kiện theo yêu cầu nghiệp vụ.

## 1. Publication là gì?

Khi một application event được phát, Spring Modulith có thể tạo một publication record cho từng listener phù hợp. Nếu event được giao cho ba listener, registry theo dõi ba publication riêng. Một listener hoàn tất không có nghĩa hai listener còn lại cũng đã hoàn tất.

Ví dụ, Orders phát `OrderConfirmed`. Event được giao đến:

- Inventory để tạo reservation.
- Notification để gửi thông báo.
- Analytics để cập nhật projection.

Registry theo dõi trạng thái giao event đến từng listener. Nếu Inventory hoàn tất nhưng Notification lỗi, publication của Inventory có thể đã hoàn tất trong khi publication của Notification vẫn chưa hoàn tất. Cách theo dõi theo listener giúp xác định chính xác chặng nào đang gặp vấn đề.

Cần phân biệt các khái niệm:

| Khái niệm | Nội dung được theo dõi |
|---|---|
| Application event | Sự thật nghiệp vụ được publisher công bố |
| Event publication | Việc giao một event cụ thể đến một listener cụ thể |
| Event Publication Registry | Trạng thái và dữ liệu phục vụ theo dõi/phục hồi publication |
| Broker message | Message được gửi qua RabbitMQ, Kafka hoặc transport khác |
| Business process | Quy trình nghiệp vụ có thể gồm nhiều event, command và service |

Publication hoàn tất chỉ xác nhận listener tương ứng đã hoàn thành theo semantics của registry. Nó không chứng minh toàn bộ quy trình nghiệp vụ đã kết thúc hoặc mọi hệ thống bên ngoài đã đồng bộ.

## 2. Event Publication Registry ghi nhận điều gì?

Registry cần giữ đủ thông tin để xác định publication nào được tạo, listener nào nhận và publication đã hoàn tất hay chưa. Các trường lưu trữ cụ thể phụ thuộc implementation và phiên bản Spring Modulith, nhưng về mặt vận hành thường cần những thông tin tương đương:

- Thời điểm publication được tạo.
- Định danh hoặc mô tả listener đích.
- Loại event và dữ liệu cần thiết để giao lại.
- Thời điểm hoàn tất nếu listener xử lý thành công.
- Thông tin phục vụ phân biệt publication đang chờ và publication đã hoàn tất.

Với persistent registry, dữ liệu publication được lưu trong kho bền vững thay vì chỉ nằm trong bộ nhớ. Nhờ đó, ứng dụng có thể tìm các publication chưa hoàn tất sau khi listener lỗi hoặc tiến trình restart, tùy cấu hình và khả năng phục hồi của implementation.

Không nên phụ thuộc trực tiếp vào tên bảng, tên cột hoặc schema nội bộ của registry để xây dashboard hay viết truy vấn vận hành lâu dài. Những chi tiết đó có thể thay đổi theo phiên bản hoặc implementation. Ưu tiên API, actuator integration và metric được Spring Modulith hỗ trợ ở phiên bản đang dùng.

## 3. Vòng đời publication

Có thể hình dung vòng đời publication qua các bước:

1. Publisher phát application event.
2. Registry ghi nhận publication cho từng listener phù hợp.
3. Listener được gọi theo cơ chế đồng bộ hoặc bất đồng bộ đã cấu hình.
4. Listener xử lý thành công.
5. Registry ghi nhận publication hoàn tất.
6. Publication đã hoàn tất được giữ lại hoặc dọn dẹp theo chính sách retention.

Nếu listener ném exception hoặc tiến trình dừng trước khi registry ghi nhận hoàn tất, publication có thể vẫn ở trạng thái chưa hoàn tất và được xem xét để phục hồi.

Sơ đồ khái niệm:

~~~mermaid
flowchart TD
    A[Publisher phát event] --> B[Registry ghi publication theo listener]
    B --> C[Listener nhận event]
    C --> D{Xử lý thành công?}
    D -- Có --> E[Đánh dấu publication hoàn tất]
    D -- Không --> F[Publication còn chưa hoàn tất]
    F --> G[Quan sát, phân loại lỗi]
    G --> H[Khắc phục và resubmit có kiểm soát]
    H --> C
    E --> I[Retention và cleanup]
~~~

Với listener bất đồng bộ, thời gian từ khi publication được ghi nhận đến khi listener hoàn tất có thể dài hơn thời gian xử lý thực tế vì publication phải chờ executor hoặc tài nguyên phía sau. Do đó cần đo cả tuổi publication và thời gian xử lý listener.

## 4. Publication được tạo cho từng listener

Một event có thể có nhiều listener, mỗi listener có thời gian xử lý và yêu cầu độ tin cậy khác nhau. Vì vậy, không nên chỉ thống kê số event đã phát.

Ví dụ:

| Event | Listener | Trạng thái |
|---|---|---|
| OrderConfirmed | InventoryListener | Hoàn tất |
| OrderConfirmed | NotificationListener | Chưa hoàn tất |
| OrderConfirmed | AnalyticsListener | Hoàn tất |

Trong ví dụ này, event đã được phát và hai listener đã xử lý xong. NotificationListener vẫn còn publication cần theo dõi. Nếu dashboard chỉ hiển thị “OrderConfirmed đã phát”, nhóm vận hành có thể bỏ sót công việc đang kẹt.

Nên phân nhóm publication theo:

- Listener hoặc module nhận.
- Event type.
- Trạng thái hoàn tất/chưa hoàn tất.
- Tuổi publication.
- Môi trường và instance phát sinh.
- Correlation ID hoặc business ID nếu metadata được thiết kế để truy vết.

Tránh dùng payload nhạy cảm làm nhãn metric. Event type và listener identifier thường đủ để tổng hợp; business ID có thể được dùng trong log hoặc công cụ tra cứu có phân quyền.

## 5. Theo dõi publication chưa hoàn tất

Publication chưa hoàn tất là tín hiệu chính để phát hiện listener chậm hoặc thất bại. Tuy nhiên, không phải mọi publication chưa hoàn tất đều là lỗi. Một publication vừa được tạo có thể đang chờ executor hoặc listener đang thực hiện công việc bình thường.

Cần theo dõi ít nhất:

- Tổng số publication chưa hoàn tất.
- Số publication chưa hoàn tất theo listener.
- Tuổi của publication cũ nhất.
- Phân bố tuổi theo các khoảng thời gian.
- Tốc độ tạo publication và tốc độ hoàn tất.
- Số publication tồn tại lâu hơn ngân sách độ trễ của nghiệp vụ.

Tuổi publication nên được tính từ thời điểm registry ghi nhận publication đến thời điểm hiện tại. Với từng listener, đặt ngưỡng riêng. Listener gửi email có thể chấp nhận chậm hơn listener cập nhật reservation tồn kho.

Ví dụ ngưỡng minh họa:

| Listener | Warning | Critical |
|---|---:|---:|
| InventoryListener | 5 giây | 30 giây |
| NotificationListener | 1 phút | 10 phút |
| AnalyticsListener | 2 phút | 15 phút |

Các con số chỉ để minh họa cách phân loại. Ngưỡng thực tế phải dựa trên SLO và tác động nghiệp vụ, không sao chép nguyên trạng giữa các hệ thống.

## 6. Phân biệt backlog bình thường với publication bị kẹt

Một backlog tăng không tự động có nghĩa listener bị lỗi. Khi lưu lượng event tăng đột biến, số publication chưa hoàn tất có thể tăng rồi giảm sau khi tải trở lại bình thường.

Nên kết hợp nhiều tín hiệu:

| Tín hiệu | Cách diễn giải |
|---|---|
| Backlog tăng nhưng completion rate cũng tăng | Consumer có thể đang xử lý đợt tải lớn |
| Backlog tăng liên tục, completion rate thấp | Có thể listener hoặc downstream đang nghẽn |
| Một publication có tuổi rất lớn | Có thể là lỗi đơn lẻ, poison event hoặc listener bị treo |
| Nhiều publication cùng listener cùng tăng tuổi | Có thể lỗi ở listener hoặc dependency chung |
| Publication mới hoàn tất bình thường nhưng một nhóm event cũ còn lại | Có thể có dữ liệu lỗi hoặc một nhánh xử lý đặc biệt |
| Retry tăng đồng thời với latency tăng | Có thể downstream lỗi hoặc retry storm |

Đừng cảnh báo chỉ dựa vào tổng backlog. Kết hợp oldest publication age, tốc độ hoàn tất, tỷ lệ lỗi và phân nhóm listener sẽ giúp giảm cảnh báo giả.

## 7. Đo latency và throughput

Để hiểu chất lượng giao sự kiện, cần đo thời gian và tốc độ ở từng chặng.

Các mốc hữu ích:

- `publishedAt`: thời điểm event được phát hoặc publication được ghi nhận theo định nghĩa metric của hệ thống.
- `listenerStartedAt`: thời điểm listener bắt đầu xử lý.
- `listenerCompletedAt`: thời điểm listener hoàn tất.
- `resubmittedAt`: thời điểm publication được gửi lại nếu có.
- `observedAt`: thời điểm metric hoặc log được ghi nhận.

Không phải mọi mốc đều được registry lưu trực tiếp. Có thể bổ sung instrumentation tại listener hoặc lớp quan sát để đo phần thời gian còn thiếu.

Các metric nên có:

| Metric | Ý nghĩa |
|---|---|
| Publication created rate | Số publication mới theo thời gian |
| Publication completion rate | Số publication hoàn tất theo thời gian |
| Incomplete publication count | Số publication chưa hoàn tất |
| Oldest incomplete publication age | Tuổi publication cũ nhất |
| Publication completion latency | Thời gian từ khi tạo đến khi hoàn tất |
| Listener processing duration | Thời gian listener thực sự xử lý |
| Resubmission count | Số lần publication được gửi lại |
| Failure count/rate | Số publication lỗi theo listener/event type |

Theo dõi p50, p95 và p99 thay vì chỉ average. Average có thể che giấu một nhóm nhỏ publication bị kẹt nhiều giờ. Với luồng quan trọng, oldest incomplete age và p99 thường có giá trị vận hành cao.

## 8. Sử dụng Event Publication Registry trong Spring Modulith

Spring Modulith cung cấp Event Publication Registry để ghi nhận và theo dõi publication đến listener. Ứng dụng nên sử dụng persistence implementation phù hợp nếu cần phục hồi sau restart hoặc muốn quan sát backlog qua nhiều lần triển khai.

Một số điểm cấu hình cần xác minh theo phiên bản đang sử dụng:

- Registry implementation được tạo và đăng ký đúng.
- Database schema cần thiết đã được khởi tạo hoặc migration.
- Registry và transaction nghiệp vụ dùng transaction manager phù hợp nếu cần publication được ghi cùng transaction.
- Listener được nhận diện ổn định để publication có thể được liên kết với đúng listener.
- Cơ chế dọn publication hoàn tất không xóa dữ liệu còn cần cho vận hành hoặc audit.
- Quyền đọc dữ liệu publication chỉ cấp cho thành phần vận hành cần thiết.

Spring Modulith có API hỗ trợ truy vấn publication chưa hoàn tất và các tiện ích phục hồi publication. Tên phương thức, loại bean và cách tích hợp actuator có thể thay đổi theo phiên bản. Hãy dùng API được cung cấp bởi dependency đang chạy thay vì tự truy vấn schema nội bộ hoặc sao chép ví dụ từ phiên bản khác.

## 9. Phục hồi publication chưa hoàn tất

Khi phát hiện publication chưa hoàn tất, cần phân loại nguyên nhân trước khi resubmit. Gửi lại hàng loạt mà không hiểu lỗi có thể làm tăng tải hoặc lặp lại tác dụng phụ.

Một quy trình phục hồi:

1. Xác định listener, event type và tuổi publication.
2. Kiểm tra log/trace của lần xử lý trước.
3. Phân loại lỗi: tạm thời, dữ liệu không hợp lệ, lỗi nghiệp vụ hay lỗi cấu hình.
4. Khắc phục nguyên nhân gốc.
5. Chọn publication phù hợp theo listener, thời gian hoặc điều kiện nghiệp vụ.
6. Resubmit với giới hạn và theo dõi kết quả.
7. Xác minh publication hoàn tất và tác dụng phụ nghiệp vụ không bị lặp.

Spring Modulith cung cấp các abstraction phục vụ resubmit publication chưa hoàn tất; tùy phiên bản, có thể thao tác qua API phục hồi tương ứng hoặc actuator integration. Cần xác minh đúng semantics và phạm vi lọc trước khi vận hành.

Không nên tự động resubmit liên tục một publication có payload không thể deserialize hoặc listener luôn thất bại vì lỗi nghiệp vụ. Những trường hợp này cần cách ly, sửa dữ liệu hoặc quy trình xử lý thủ công.

## 10. Idempotency khi resubmit

Resubmit có thể khiến listener chạy lại sau khi một phần tác dụng phụ đã xảy ra. Ví dụ listener gọi API ngoài thành công nhưng process dừng trước khi registry ghi nhận hoàn tất. Khi publication được gửi lại, API có thể bị gọi lần nữa.

Vì vậy:

- Listener cần idempotent đối với event ID hoặc business operation ID.
- Thay đổi database và inbox record nên nằm trong cùng transaction.
- API ngoài nên nhận idempotency key ổn định nếu hỗ trợ.
- Không tạo event ID mới cho cùng một lần phát lại.
- Với tác dụng phụ không thể đảo ngược, cần trạng thái tiến trình và đối soát.
- Resubmit phải giữ metadata cần thiết để truy vết.

Publication Registry theo dõi trạng thái giao đến listener; nó không thay thế inbox pattern và không tự bảo đảm exactly-once side effect.

## 11. Quan sát bằng log và trace

Metric cho biết xu hướng tổng thể; log và trace giúp tìm một publication cụ thể. Nên liên kết các chặng bằng metadata ổn định.

Các trường có thể ghi:

- Event ID.
- Event type.
- Listener identifier.
- Publication ID nếu có trong API/implementation.
- Correlation ID và causation ID.
- Aggregate/business ID khi được phép.
- Thời điểm bắt đầu, kết thúc và thời gian xử lý.
- Kết quả: completed, failed hoặc resubmitted.
- Exception class và mã lỗi đã chuẩn hóa.

Không ghi toàn bộ payload vào log mặc định. Payload có thể chứa dữ liệu cá nhân, thông tin thanh toán hoặc bí mật. Dùng event ID và correlation ID để truy xuất dữ liệu qua công cụ có phân quyền.

Trace nên có span cho việc phát event và xử lý listener nếu instrumentation của ứng dụng hỗ trợ. Với listener bất đồng bộ, trace context cần được truyền qua executor hoặc transport theo cơ chế tương ứng; không giả định thread-local context tự động tồn tại sau khi đổi thread hoặc restart.

## 12. Metrics, Actuator và dashboard

Spring Boot Actuator và Micrometer có thể được dùng để công bố health, metric và thông tin vận hành. Spring Modulith có tích hợp quan sát cho các thành phần event ở những phiên bản và cấu hình phù hợp.

Khi bật endpoint hoặc metric, cần kiểm tra:

- Dependency actuator/observability tương ứng đã được thêm.
- Endpoint được expose có chủ đích.
- Endpoint quản trị được bảo vệ bằng authentication và authorization.
- Metric được export đến hệ thống giám sát.
- Tag có cardinality giới hạn.
- Thông tin event/payload nhạy cảm không bị expose ra endpoint công khai.

Không mở endpoint resubmit hoặc quản trị publication ra internet. Endpoint chỉ đọc cũng có thể làm lộ event type, listener, business identifier hoặc trạng thái xử lý nội bộ.

Dashboard nên có các góc nhìn:

1. Tổng quan publication mới, hoàn tất và chưa hoàn tất.
2. Backlog và oldest age theo listener.
3. Completion latency p50/p95/p99 theo event type.
4. Retry/resubmit và failure rate.
5. Top listener có publication tồn đọng lâu nhất.
6. Số publication cần can thiệp thủ công.
7. Tình trạng database registry và dung lượng lưu trữ.

## 13. Retention và cleanup publication đã hoàn tất

Publication đã hoàn tất vẫn có thể cần được giữ trong một khoảng thời gian để điều tra, audit hoặc đối chiếu sau sự cố. Tuy nhiên, lưu vô thời hạn có thể làm bảng registry tăng nhanh, ảnh hưởng index và truy vấn.

Chính sách retention cần xác định:

- Thời gian giữ publication đã hoàn tất.
- Publication chưa hoàn tất có được giữ vô thời hạn cho đến khi xử lý hay chuyển sang quarantine sau một ngưỡng.
- Ai được phép cleanup.
- Cleanup chạy theo batch hay theo lịch.
- Cách bảo đảm cleanup không xóa publication đang được xử lý.
- Yêu cầu audit và khả năng điều tra sau khi dữ liệu bị xóa.

Không xóa publication chưa hoàn tất chỉ để giảm backlog. Với publication đã hoàn tất, chỉ cleanup khi hết thời gian lưu cần thiết và có thể khôi phục hoặc truy vết theo chính sách.

Không nên viết job trực tiếp xóa hàng trong bảng nội bộ của registry nếu Spring Modulith cung cấp abstraction cleanup phù hợp. Schema nội bộ có thể thay đổi và xóa trực tiếp có thể phá vỡ trạng thái mà framework quản lý.

## 14. Phân biệt publication với outbox và broker lag

Trong kiến trúc có externalization, có thể có nhiều nơi chứa công việc đang chờ:

| Thành phần | Điều đang chờ | Chỉ số nên theo dõi |
|---|---|---|
| Event Publication Registry | Listener nội bộ chưa hoàn tất | Incomplete publication count, oldest age |
| Outbox | Message đã ghi nhưng relay chưa gửi | Outbox backlog, oldest outbox age |
| RabbitMQ queue | Message chưa được consumer ack | Ready/unacked, consumer count |
| Kafka consumer group | Consumer chưa xử lý đến offset mới | Consumer lag |
| Projection store | Dữ liệu đọc chưa cập nhật đến event/version mới | Projection watermark/freshness |

Không gộp các con số này thành một metric “event pending” duy nhất. Một publication có thể đã hoàn tất ở chặng nội bộ trong khi message broker vẫn còn chờ consumer. Ngược lại, outbox relay có thể đã gửi message nhưng consumer vẫn chưa cập nhật projection.

Đặt dashboard và SLO riêng cho từng ranh giới. Dùng event ID/correlation ID để liên kết cùng một luồng khi cần điều tra.

## 15. Xử lý publication tồn tại lâu

Khi publication vượt ngưỡng tuổi, hãy dùng runbook nhất quán:

1. Xác định listener và event type bị ảnh hưởng.
2. Xem publication cũ nhất và nhóm publication cùng thời điểm.
3. Kiểm tra listener có đang chạy, executor có backlog hoặc dependency có lỗi không.
4. Đọc exception đã chuẩn hóa và trace liên quan.
5. Xác định event có payload hợp lệ và schema còn được hỗ trợ không.
6. Kiểm tra listener có tác dụng phụ đã thực hiện một phần hay chưa.
7. Khắc phục dependency hoặc dữ liệu trước khi resubmit.
8. Resubmit một nhóm nhỏ có chọn lọc.
9. Theo dõi completion rate và oldest age sau phục hồi.
10. Ghi audit về quyết định resubmit, người thực hiện và kết quả.

Nếu một publication liên tục thất bại, chuyển sang quarantine hoặc manual review theo quy trình của hệ thống. Không để resubmit tự động tạo retry storm.

## 16. Bảo mật thông tin publication

Dữ liệu registry có thể chứa payload đã serialize hoặc metadata nhạy cảm. Cần áp dụng quyền tối thiểu:

- Chỉ service cần thiết được đọc/ghi registry.
- Quyền resubmit và cleanup tách biệt với quyền xem dashboard.
- Endpoint actuator được bảo vệ.
- Log và metric không chứa payload nhạy cảm hoặc identifier có cardinality quá cao.
- Database registry có backup, mã hóa và retention phù hợp.
- Công cụ vận hành ghi audit khi xem, resubmit hoặc xóa publication nếu dữ liệu yêu cầu.

Nếu payload được lưu lâu hơn dữ liệu domain, cần đánh giá rủi ro dữ liệu cũ còn tồn tại trong registry. Chính sách retention phải tính cả publication chưa hoàn tất và backup.

## 17. Ví dụ tình huống vận hành

Giả sử Orders phát OrderConfirmed cho ba listener. Dashboard cho thấy:

| Listener | Incomplete | Oldest age | Completion rate |
|---|---:|---:|---:|
| InventoryListener | 0 | — | 120/s |
| NotificationListener | 42 | 8 phút | 2/s |
| AnalyticsListener | 3 | 12 giây | 35/s |

Inventory hoạt động bình thường. Notification có backlog lớn và tuổi publication cao; Analytics chỉ có một số publication mới đang chờ.

Runbook nên tập trung vào NotificationListener: kiểm tra email provider, rate limit, executor và exception. Không resubmit toàn bộ publication của mọi listener. Sau khi provider phục hồi, có thể resubmit có chọn lọc theo listener và theo lô nhỏ, sau đó theo dõi backlog giảm.

Nếu NotificationListener đã gửi email nhưng lỗi trước khi registry ghi nhận hoàn tất, resubmit có thể gửi email trùng. Listener cần inbox hoặc một notification operation key ổn định để ngăn gửi lặp. Registry cho biết publication chưa hoàn tất; idempotency bảo vệ tác dụng phụ.

## 18. Kiểm thử khả năng theo dõi publication

Nên kiểm tra không chỉ listener có được gọi mà cả registry ghi nhận trạng thái đúng.

Các trường hợp:

- Event tạo publication cho đúng tập listener.
- Listener hoàn tất thì publication tương ứng được đánh dấu hoàn tất.
- Listener lỗi thì publication còn được nhận diện là chưa hoàn tất.
- Publication chưa hoàn tất vẫn tồn tại sau khi ứng dụng restart với persistent registry.
- Resubmit đúng publication đưa listener chạy lại.
- Publication đã hoàn tất không bị resubmit ngoài ý muốn.
- Một listener hoàn tất không làm publication của listener khác bị đánh dấu hoàn tất.
- Cleanup chỉ tác động đến publication đủ điều kiện.
- Metric phản ánh backlog và completion latency.
- Endpoint quan sát/resubmit được bảo vệ theo quyền.
- Retry hoặc resubmit không gây tác dụng phụ kép.

Integration test cần dùng persistence implementation phù hợp và transaction manager thực tế của ứng dụng. Mock registry có thể kiểm tra cách gọi API nhưng không chứng minh persistence, restart recovery hoặc transaction boundary.

## 19. Checklist triển khai

- [ ] Registry implementation phù hợp với nhu cầu phục hồi đã được cấu hình.
- [ ] Publication được theo dõi riêng theo từng listener.
- [ ] Đã xác định trạng thái hoàn tất và chưa hoàn tất theo semantics của phiên bản.
- [ ] Có metric số publication chưa hoàn tất và tuổi publication cũ nhất.
- [ ] Có completion latency p50/p95/p99 và throughput.
- [ ] Dashboard phân nhóm theo listener và event type.
- [ ] Log/trace có event ID, listener và correlation ID.
- [ ] Có cảnh báo theo SLO, không chỉ theo tổng backlog.
- [ ] Có runbook điều tra publication cũ và resubmit có chọn lọc.
- [ ] Listener idempotent trước redelivery/resubmit.
- [ ] Có chính sách retention và cleanup rõ ràng.
- [ ] Không truy vấn/xóa schema nội bộ theo cách phụ thuộc implementation.
- [ ] Actuator/management endpoint được bảo vệ.
- [ ] Metric tag có cardinality được kiểm soát.
- [ ] Đã kiểm thử listener failure, restart, resubmit và cleanup.

## 20. Nguyên tắc theo dõi publication

Event Publication Registry giúp quan sát việc giao application event đến từng listener, phát hiện publication chưa hoàn tất và hỗ trợ phục hồi theo cấu hình. Hãy theo dõi backlog, tuổi publication cũ nhất, completion latency, retry và lỗi theo listener; kết hợp metric với log/trace để tìm đúng event và nguyên nhân.

Publication hoàn tất chỉ phản ánh kết quả của listener tương ứng. Nếu hệ thống còn outbox, broker và projection, hãy theo dõi từng chặng riêng và liên kết chúng bằng event ID hoặc correlation ID. Kết hợp retention có kiểm soát, endpoint quản trị được bảo vệ, runbook resubmit và listener idempotent sẽ giúp nhóm vận hành phát hiện sớm publication bị kẹt và phục hồi mà không tạo tác dụng phụ ngoài ý muốn.
