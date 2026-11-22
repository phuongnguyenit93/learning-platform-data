# Chi phí mạng, dữ liệu, kiểm thử và vận hành phát sinh khi chọn Microservices

## 1. Vì sao đây là một tiêu chí chọn kiến trúc?

Microservices chia hệ thống thành các dịch vụ có ranh giới nghiệp vụ, dữ liệu, vòng đời triển khai và khả năng mở rộng tương đối độc lập. Sự độc lập này có giá trị khi nhiều nhóm cần phát triển song song, một miền nghiệp vụ cần mở rộng khác phần còn lại, hoặc tổ chức cần triển khai và cách ly sự cố theo từng dịch vụ. Đổi lại, những công việc vốn diễn ra trong một tiến trình hoặc một cơ sở dữ liệu trở thành tương tác qua mạng và phối hợp giữa nhiều thành phần.

Hãy tưởng tượng luồng đặt hàng:

~~~text
Client -> API Gateway -> Order Service
                           |-> Inventory Service
                           |-> Payment Service
                           |-> Order Database
                    -> Event Broker -> Notification Service
~~~

Trong một **modular monolith**, các module Order, Inventory, Payment có thể gọi nhau trong cùng tiến trình; một số thay đổi dữ liệu có thể nằm trong cùng giao dịch. Với microservices, mỗi lời gọi sang dịch vụ khác phải tính thêm truyền dữ liệu, timeout, xác thực, khả năng mất kết nối, phiên bản hợp đồng API và cách xử lý trạng thái khi một bên thành công còn bên kia thất bại. Mỗi dịch vụ cũng cần được build, cấu hình, giám sát, triển khai và hỗ trợ khi có sự cố.

Vì vậy, câu hỏi lựa chọn kiến trúc là: **giá trị của độc lập triển khai, độc lập mở rộng và ranh giới đội nhóm có đủ lớn để bù chi phí phân tán hay không?** “Nhiều dịch vụ” tự nó không bảo đảm dễ bảo trì hoặc chịu tải tốt hơn.

## 2. Chi phí mạng: độ trễ, độ tin cậy và lưu lượng

### 2.1. Một lời gọi từ xa đắt hơn một lời gọi trong tiến trình

Lời gọi HTTP/gRPC hoặc trao đổi qua message broker thường bao gồm một phần của các bước: thiết lập/kế thừa kết nối, TLS, phân giải địa chỉ, serialize/deserialize, truyền trên mạng, đi qua proxy/load balancer, xác thực, xếp hàng tại đích, xử lý nghiệp vụ và nhận phản hồi. Kể cả khi mỗi dịch vụ xử lý rất nhanh, tổng độ trễ vẫn có thể tăng do nhiều hop.

Có thể ước lượng một đường đi đồng bộ theo:

~~~text
T_request ≈ T_gateway + Σ(T_network_i + T_queue_i + T_service_i)
            + T_serialization + T_other
~~~

Công thức này là mô hình sơ bộ cho các bước **tuần tự**. Nếu gọi song song, thời gian phần gọi song song phụ thuộc chủ yếu vào nhánh chậm nhất và chi phí điều phối. Không được cộng trực tiếp các giá trị p95 riêng lẻ rồi mặc nhiên coi kết quả là p95 của toàn tuyến; phải đo phân phối độ trễ thực tế tại điểm người dùng.

Ví dụ minh họa: một endpoint có ngân sách 300 ms. Kiến trúc sư có thể phân bổ khoảng 20 ms cho gateway, 40 ms cho Order, 60 ms cho Inventory, 100 ms cho Payment và 80 ms dự phòng cho biến động mạng/hàng đợi. Đây là **ngân sách thiết kế**, không phải số đo hoặc cam kết hiệu năng. Nếu Payment thường xuyên gần 100 ms và đôi lúc vượt xa, p99 của toàn luồng sẽ xấu đi dù trung bình vẫn ổn.

### 2.2. Chuỗi phụ thuộc có thể giảm xác suất thành công

Nếu một request cần năm lời gọi thành công nối tiếp và giả sử *mỗi lời gọi* thành công độc lập với xác suất 99,9%, thì xác suất cả chuỗi thành công xấp xỉ:

~~~text
0,999 ^ 5 ≈ 99,50%
~~~

Đây chỉ là ví dụ toán học để thấy tác động tích lũy: trong thực tế, lỗi có thể tương quan vì các dịch vụ dùng chung mạng, cơ sở hạ tầng hoặc broker. Khả năng thành công của người dùng phải được đo ở toàn luồng, không suy ra đơn giản từ uptime của từng container.

Các dạng lỗi cần thiết kế trước gồm: timeout; kết nối bị reset; DNS hoặc service discovery lỗi; upstream quá tải; phản hồi đến trễ; request đã xử lý nhưng client không nhận được phản hồi; broker gửi lại thông điệp. Đặc biệt, **timeout không chứng minh thao tác đã thất bại**: ví dụ thanh toán có thể đã được ghi nhận ở phía đích.

### 2.3. Retry có thể khuếch đại tải

Retry có ích khi lỗi nhất thời, nhưng nếu nhiều tầng đều retry một cách độc lập thì tải tăng nhanh. Ví dụ ba tầng, mỗi tầng có tối đa ba lần gửi cho một thao tác, có thể tạo tới 3 × 3 × 3 = 27 lần thử ở phụ thuộc phía dưới trong trường hợp xấu nhất. Khi hệ thống đang quá tải, điều này gây “retry storm”.

Nguyên tắc thiết kế:

- Đặt **timeout/deadline từ đầu request**; mỗi lời gọi con phải nằm trong ngân sách còn lại.
- Retry có giới hạn, kèm exponential backoff và jitter; chỉ áp dụng cho lỗi có khả năng hồi phục và thao tác an toàn để lặp lại.
- Dùng **idempotency key** cho thao tác tạo đơn, giữ chỗ hoặc thanh toán; phía nhận phải lưu và kiểm tra khóa để chống xử lý trùng.
- Dùng **circuit breaker** để ngừng gọi tạm thời tới phụ thuộc đang lỗi, **bulkhead** để cô lập tài nguyên và **backpressure** để tránh nhận việc vượt năng lực xử lý.
- Chọn fallback theo nghiệp vụ. Có thể trả dữ liệu cache cho danh mục sản phẩm, nhưng không được tự suy đoán “thanh toán thành công” khi Payment Service không phản hồi.

### 2.4. Chi phí băng thông, hạ tầng mạng và bảo mật

Số lượng lần gọi, kích thước payload, retry, replication, log và lưu lượng liên vùng đều có thể phát sinh chi phí. Ví dụ giả định: 1 triệu request/ngày, mỗi request tạo ba lời gọi nội bộ, tổng payload trung bình mỗi lời gọi là 2 KB, tức khoảng **6 GB/ngày** dữ liệu ứng dụng trước khi cộng header, telemetry, retry và cơ chế truyền tải khác. Giá thành thực tế phụ thuộc vị trí triển khai, chính sách egress, lưu lượng cross-zone/cross-region và nhà cung cấp.

Các thành phần có thể cần thêm: API gateway, service discovery, ingress, load balancer, TLS/mTLS, certificate rotation, network policy, rate limiting, DNS, service mesh. Không nhất thiết dùng tất cả; mỗi lớp bổ sung phải có lợi ích rõ ràng và người vận hành chịu trách nhiệm.

**Cách giảm chi phí mạng:** thiết kế API theo tác vụ nghiệp vụ để tránh nhiều lời gọi vụn; hạn chế giao tiếp đồng bộ sâu; gộp dữ liệu hợp lý; phân trang và giới hạn payload; tái sử dụng kết nối; dùng cache phù hợp; đặt dịch vụ có giao tiếp chặt gần nhau; cân nhắc async messaging khi không cần câu trả lời tức thì. Đồng thời phải đo latency p50/p95/p99, throughput, error rate, retry rate và traffic theo từng dependency.

## 3. Chi phí dữ liệu: quyền sở hữu, nhất quán và truy vấn liên dịch vụ

### 3.1. Mỗi dịch vụ sở hữu dữ liệu của mình

Ranh giới dịch vụ chỉ thực sự độc lập khi dữ liệu và quyền thay đổi schema có chủ sở hữu rõ. Order Service không nên cập nhật trực tiếp bảng của Payment Service. Nếu mọi dịch vụ vẫn cùng đọc/ghi tùy ý một database chung, việc tách mã nguồn thành nhiều deployment chưa loại bỏ được coupling.

Sở hữu dữ liệu dẫn đến những chi phí mới:

- Mỗi nhóm phải quản lý schema migration, backup, restore, capacity, index và bảo mật dữ liệu trong phạm vi sở hữu.
- Một câu JOIN liên miền có thể biến thành gọi API, xây dựng read model hoặc đồng bộ sự kiện.
- Báo cáo tổng hợp, tìm kiếm và analytics có thể cần pipeline dữ liệu riêng; dữ liệu sao chép phải có cách làm mới, đối chiếu và xử lý sai lệch.
- Hệ thống phải định nghĩa rõ ai là nguồn dữ liệu có thẩm quyền cho mỗi thuộc tính, thay vì lưu nhiều bản có quyền sửa ngang nhau.

Không phải cứ một service là một máy chủ database riêng. Có thể dùng cùng cụm hạ tầng nhưng schema/quyền truy cập tách biệt, nếu bảo đảm các dịch vụ không tùy tiện thao tác lên dữ liệu của nhau. Quyết định phụ thuộc mức cô lập, độ phức tạp và năng lực vận hành.

### 3.2. Giao dịch phân tán thay cho transaction cục bộ

Trong một tiến trình với một database, thao tác “tạo đơn + trừ tồn kho + ghi thanh toán” có thể dễ biểu diễn bằng một transaction. Khi ba dịch vụ sở hữu ba kho dữ liệu, không còn mặc định có một ACID transaction bao trùm toàn bộ luồng. Dùng distributed transaction/2PC có thể tạo phụ thuộc mạnh, tăng latency và phức tạp khôi phục; thường cần xem xét rất kỹ trước khi áp dụng.

Một cách phổ biến là **Saga**: mỗi bước commit giao dịch cục bộ; nếu bước sau thất bại thì kích hoạt hành động bù phù hợp với nghiệp vụ.

~~~text
1. Order tạo đơn PENDING.
2. Inventory thử reserve tồn kho.
3. Payment thử authorize thanh toán.
4. Nếu các bước cần thiết thành công: Order chuyển CONFIRMED.
5. Nếu Payment thất bại: Inventory release reservation; Order chuyển FAILED.
~~~

Cần phân biệt **compensation** với rollback database: việc hoàn tiền, hủy giữ chỗ hoặc gửi thông báo sửa sai có thể cần thời gian và có thể tự thất bại. Không thể giả định thế giới bên ngoài quay lại trạng thái ban đầu ngay lập tức.

Với một số quy trình, nên giảm số bước đồng bộ: ghi trạng thái ban đầu, phát event, theo dõi tiến trình và trả cho người dùng trạng thái đang xử lý. Tuy nhiên, UX phải minh bạch: PENDING không đồng nghĩa với SUCCESS.

### 3.3. Outbox, giao hàng lặp và idempotency

Nếu service ghi database rồi publish event trong hai thao tác tách rời, có thể xảy ra trạng thái “database đã commit nhưng event chưa được gửi” hoặc ngược lại. **Transactional Outbox** ghi dữ liệu nghiệp vụ và bản ghi sự kiện trong cùng một giao dịch cục bộ; một tiến trình khác chuyển event tới broker.

~~~sql
BEGIN;

INSERT INTO orders (id, status)
VALUES (:order_id, 'PENDING');

INSERT INTO outbox (event_id, aggregate_id, event_type, payload)
VALUES (:event_id, :order_id, 'OrderCreated', :payload);

COMMIT;
~~~

Worker có thể gửi lại event nếu chưa nhận được xác nhận. Consumer vì vậy phải xử lý trùng an toàn, chẳng hạn có bảng **inbox/processed_events** với khóa duy nhất event_id, hoặc thao tác cập nhật có điều kiện. Mô hình thực tế thường hướng tới **at-least-once delivery + idempotent consumer**; không nên mặc định broker bảo đảm “một sự kiện được xử lý chính xác một lần” xuyên suốt database và tác dụng phụ bên ngoài.

Cần thêm cơ chế chống mất event, xử lý dead-letter queue, retry có giới hạn, theo dõi consumer lag, replay và quy trình khôi phục khi dữ liệu lệch.

### 3.4. Eventual consistency và thiết kế trải nghiệm người dùng

Nếu Inventory phát sự kiện “StockChanged” để cập nhật read model của Catalog, hai bản dữ liệu có thể lệch nhau trong một khoảng thời gian. Hãy định nghĩa rõ:

- **Thông tin nào phải nhất quán ngay?** Ví dụ không bán vượt tồn kho đã giữ; không ghi nhận trùng giao dịch thanh toán.
- **Thông tin nào có thể trễ?** Ví dụ bộ đếm lượt xem, dashboard doanh thu gần thời gian thực hoặc email xác nhận.
- **Độ trễ chấp nhận là bao nhiêu?** Ví dụ hệ thống có thể đặt mục tiêu một tỷ lệ cập nhật xuất hiện trong vài giây; phải đo và xác nhận bằng nhu cầu sản phẩm.
- **Người dùng thấy gì khi chờ?** Trạng thái PENDING, tiến độ, lựa chọn retry an toàn, tra cứu mã giao dịch và thông báo khi hoàn tất.

Bất biến nghiệp vụ quan trọng phải được bảo vệ tại owner service, bằng transaction cục bộ, unique constraint, version check hoặc reservation. Không đặt toàn bộ tính đúng đắn vào giả định rằng mọi sự kiện luôn đến đúng thứ tự và chỉ đến một lần.

### 3.5. Versioning và tiến hóa dữ liệu

Khi một service triển khai API/schema mới trước những service còn lại, bản phát hành phải tương thích với consumer cũ trong giai đoạn chuyển tiếp. Với API có thể dùng nguyên tắc additive change trước, bỏ trường cũ sau; với database migration có thể dùng **expand → migrate → contract**. Với sự kiện, cần tài liệu hóa schema, ý nghĩa trường, version, quy tắc optional/null và chiến lược consumer khi gặp phiên bản không hỗ trợ.

Chi phí dữ liệu không chỉ là tiền lưu trữ; còn là công sức bảo đảm ownership, correctness, khôi phục và thay đổi lâu dài.

## 4. Chi phí kiểm thử: tổ hợp phiên bản và tình huống thất bại

### 4.1. Vì sao kiểm thử tăng độ phức tạp?

Trong monolith, nhiều kiểm thử tích hợp có thể chạy với một artifact và một database thử nghiệm. Với microservices, kết quả có thể phụ thuộc vào phiên bản của nhiều dịch vụ, cấu hình mạng, broker, trạng thái dữ liệu và tốc độ xử lý bất đồng bộ. Một đường đi “thành công” trên máy lập trình viên chưa chứng minh được luồng sẽ đúng khi response bị mất, broker trễ hoặc một deployment đang nâng cấp.

Nếu có nhiều dịch vụ và mỗi dịch vụ triển khai độc lập, số tổ hợp phiên bản về mặt lý thuyết có thể tăng rất nhanh. Tuy nhiên không cần chạy E2E cho mọi tổ hợp; cần kiểm soát tương thích bằng hợp đồng, chiến lược rollout và kiểm thử tại đúng tầng.

### 4.2. Phân tầng kiểm thử để quản lý chi phí

| Tầng | Mục tiêu | Ví dụ trong luồng đặt hàng |
| --- | --- | --- |
| Unit/domain | Kiểm tra quy tắc nghiệp vụ nhanh và ổn định, không cần mạng | Không cho xác nhận đơn chưa reserve tồn kho |
| Component/service | Kiểm tra API, persistence, xử lý event trong phạm vi một service | Order lưu PENDING và outbox trong cùng transaction |
| Contract | Xác nhận provider/consumer hiểu cùng request, response và event schema | Payment vẫn chấp nhận field hiện có của Order |
| Integration | Xác nhận giao tiếp với database, broker, auth và service thật trong tập phạm vi | Event bị gửi lặp vẫn chỉ reserve một lần |
| End-to-end | Kiểm tra ít luồng nghiệp vụ quan trọng từ phía client | Tạo đơn → giữ hàng → thanh toán → xác nhận |
| Reliability/performance | Đo hành vi khi lỗi, tải cao, trễ, mất mạng | Payment timeout nhưng đã charge; retry không charge lần hai |

Một chiến lược thực dụng là để phần lớn quy tắc nằm ở unit/component tests, dùng contract tests ở ranh giới tương tác, chỉ giữ các E2E tests có giá trị cao và kiểm thử lỗi có mục tiêu. Test E2E quá nhiều thường chậm, dễ flaky và khó xác định dịch vụ gây lỗi.

### 4.3. Các tình huống nhất định phải mô phỏng

Trong phạm vi quy trình đặt hàng, kiểm tra tối thiểu các tình huống nghiệp vụ có ảnh hưởng lớn:

1. Inventory báo hết hàng trước khi Payment được gọi.
2. Payment phản hồi lỗi rõ ràng.
3. Payment thành công nhưng phản hồi đến Order bị mất hoặc hết timeout.
4. Event bị gửi hai lần; consumer được restart giữa chừng.
5. Hai request đồng thời cùng đặt lượng hàng tồn cuối.
6. Event đến sai thứ tự, đến trễ hoặc bị đưa vào dead-letter queue.
7. Một bản service mới chạy cùng bản cũ trong rolling deployment.
8. Schema mới cần đọc dữ liệu tạo bởi phiên bản cũ.
9. Broker tạm ngừng; outbox tích lũy rồi được gửi tiếp khi kết nối khôi phục.

Điểm chính không phải viết tất cả thành một bài E2E khổng lồ. Hãy gán mỗi rủi ro cho tầng kiểm thử rẻ nhất có thể phát hiện được lỗi thật, dùng dữ liệu kiểm thử có tính lặp lại và đặt quy trình dọn tài nguyên rõ ràng.

### 4.4. Môi trường kiểm thử cũng là một khoản chi

Những khoản hay bị bỏ sót: chạy database/broker/container trong CI, dựng môi trường tạm, seed dữ liệu hợp lệ, tạo credentials thử nghiệm, giả lập dịch vụ bên thứ ba, quản lý test data giữa các nhóm, điều tra flaky tests và chờ pipeline. Kiểm thử hiệu năng cần môi trường đủ giống production để tránh kết luận sai, đồng thời có chi phí chạy tải và quan sát hệ thống.

Đừng lấy việc “một dịch vụ tự chạy test xanh” làm bằng chứng toàn luồng an toàn. Dịch vụ đạt chất lượng trong ranh giới của nó và giao tiếp giữa các dịch vụ là hai vấn đề cần bằng chứng riêng.

## 5. Chi phí vận hành: nhiều đơn vị triển khai, nhiều điểm hỏng

### 5.1. Hạ tầng và vòng đời triển khai

Mỗi dịch vụ cần ít nhất một tập quyết định về build artifact, image, secrets, cấu hình theo môi trường, quản lý phiên bản, deploy, rollback, capacity, health check và backup/restore nếu nó có dữ liệu. Khi số lượng dịch vụ tăng, chi phí của CI/CD, service catalog, provisioning, certificate, network policy, namespace, logging và quyền truy cập cũng tăng.

Khả năng deploy độc lập chỉ có thật nếu các bên duy trì contract tương thích và không buộc phải phát hành đồng loạt. Nếu thay đổi một field đòi sửa sáu service, lập kế hoạch deploy cùng thời điểm và sửa cùng một database, lợi ích độc lập triển khai đã giảm rất nhiều.

Các chiến lược thường cần gồm rolling/canary deployment, feature flags, backward compatibility, schema migration theo giai đoạn và rollback không phá hủy dữ liệu đã được phiên bản mới tạo ra.

### 5.2. Observability trở thành yêu cầu cơ bản

Khi request đi qua nhiều dịch vụ, log của từng container không đủ để giải thích toàn bộ sự cố. Hệ thống nên có:

- **Metrics:** traffic, error rate, latency, saturation; thêm queue depth, consumer lag, DB connection pool, retry rate và số lượng tác vụ PENDING quá hạn.
- **Structured logs:** timestamp, service/version, trace ID, request/correlation ID và mã nghiệp vụ cần thiết; tránh đưa mật khẩu, token, thông tin thanh toán hoặc PII không cần thiết vào log.
- **Distributed tracing:** liên kết span giữa gateway, Order, Inventory, Payment và broker; biết đường đi nào tăng độ trễ hoặc gặp lỗi.
- **Alert theo trải nghiệm:** dựa trên SLI/SLO của luồng đặt hàng (tỷ lệ hoàn tất, latency, tuổi của tác vụ PENDING), tránh chỉ nhìn CPU và trạng thái “container còn sống”.

Telemetry cũng có giá: hệ thống thu thập, lưu trữ, chỉ mục, egress, sampling, retention và thời gian phân tích. Cardinality quá cao, chẳng hạn gắn user_id hoặc order_id thành nhãn metric, có thể làm chi phí tăng mạnh; dùng trace/log cho dữ liệu có tính định danh cao.

### 5.3. On-call, khắc phục sự cố và trách nhiệm đội nhóm

Trong hệ thống phân tán, một lỗi đơn giản theo cảm nhận người dùng có thể có nguyên nhân từ timeout ở gateway, backlog broker, deadlock database, version API hay việc một service phát event không hợp lệ. Đội vận hành cần sơ đồ dependency, runbook, dashboard chung và ranh giới ownership rõ.

Một incident tốt cần trả lời nhanh: dịch vụ nào đang lỗi, ảnh hưởng người dùng tới đâu, request nào bị mắc, có cần replay hay compensation không, hành động rollback nào an toàn, ai chịu trách nhiệm khôi phục dữ liệu. Hãy diễn tập khôi phục backup, broker outage và mất kết nối liên vùng theo mức độ rủi ro của hệ thống. Có nhiều service mà không có đội vận hành/observability đủ năng lực thường làm MTTR tăng.

### 5.4. Bảo mật và quản trị

Thêm nhiều kết nối nội bộ có nghĩa thêm danh tính máy, policy, quyền gọi API, bí mật cần luân chuyển và audit trail. Không nên xem mạng nội bộ là mặc nhiên đáng tin: xác thực/ủy quyền giữa service, giới hạn quyền truy cập dữ liệu và mã hóa đường truyền theo yêu cầu thực tế. Service mesh hay platform có thể giảm thao tác lặp lại, nhưng bản thân chúng cũng cần kỹ năng, nâng cấp và xử lý lỗi.

## 6. Đánh giá tổng chi phí sở hữu (TCO)

Không chỉ tính số tiền máy chủ. Một mô hình định tính/định lượng có thể dùng trong quá trình ra quyết định:

~~~text
TCO_microservices
  = compute + storage + network + broker/gateway
  + CI/CD + observability + security/platform
  + development/testing + vận hành/on-call
  + chi phí sự cố, khôi phục và phối hợp giữa nhóm
~~~

Ở mức ứng dụng, hãy so sánh **chi phí tăng thêm** với phương án modular monolith ở cùng mức tải, độ sẵn sàng và yêu cầu nghiệp vụ. Tính cả chi phí đầu tư ban đầu để xây platform và chi phí duy trì lâu dài; tránh so “microservices có đầy đủ monitoring” với “monolith không được vận hành nghiêm túc”.

| Khía cạnh | Modular monolith | Microservices |
| --- | --- | --- |
| Gọi giữa thành phần | Chủ yếu trong tiến trình | Có mạng, serialization, timeout, retry |
| Giao dịch nghiệp vụ | Có thể dùng transaction trong cùng database | Thường cần transaction cục bộ, Saga/compensation |
| Truy vấn dữ liệu | JOIN nội bộ thuận tiện hơn | Data ownership, read model, sync/denormalization |
| Kiểm thử | Ít tổ hợp triển khai hơn | Contract, integration, failure testing quan trọng hơn |
| Triển khai | Ít đơn vị phát hành | Nhiều pipeline, cấu hình và version |
| Giám sát | Vẫn cần logs/metrics | Cần correlation và distributed tracing rõ hơn |
| Mở rộng | Thường mở rộng cả ứng dụng hoặc tách module khó hơn | Có thể mở rộng theo dịch vụ khi ranh giới tốt |
| Đội nhóm | Phối hợp trong cùng codebase/artifact | Tự chủ hơn khi ownership và contract ổn định |

### 6.1. Ví dụ cách đặt giả định tính chi phí

Giả sử một hệ thống có 6 dịch vụ, một broker và hai database cluster. Hàng tháng, thay vì hỏi “mỗi container giá bao nhiêu?”, cần thu thập ít nhất:

- Tổng request người dùng và số hop nội bộ trung bình/trong trường hợp xấu; traffic qua vùng tính phí và tỷ lệ retry.
- CPU/memory theo tải nền, giờ cao điểm và số replica tối thiểu để chịu lỗi; mức overprovisioning.
- Dung lượng lưu trữ, bản sao, backup, log/trace, retention và dữ liệu event giữ lại.
- Thời gian CI trung bình, số môi trường đang chạy, thời gian phát hành một thay đổi và số thành phần phải cùng cập nhật.
- Giờ công hỗ trợ platform, kiểm thử, điều tra incident, khôi phục dữ liệu và xử lý dependency.
- Các SLO kinh doanh: p95/p99 đặt hàng, tỷ lệ checkout thành công, thời gian khôi phục và số lần deploy độc lập.

Không có giá dịch vụ cloud hoặc profile tải cụ thể thì không thể gán một con số TCO đáng tin cậy. Dùng các biến trên để lập baseline, đo proof of concept ở quy mô thực tế và cập nhật giả định khi workload đổi.

### 6.2. Chi phí nào “đáng trả”?

Chi phí phát sinh có thể hợp lý nếu đạt một hay nhiều lợi ích đo được:

- Nhóm Payment cần phát hành độc lập mà không chờ toàn bộ ứng dụng, và contract giữ được tương thích.
- Notification có tải sự kiện rất khác checkout, cần scale/queue riêng để không ảnh hưởng đường đặt hàng.
- Một lỗi ở khối ít quan trọng được cách ly, không kéo sập luồng nghiệp vụ trọng yếu.
- Ranh giới dữ liệu và sở hữu nghiệp vụ đủ ổn định để các nhóm giảm xung đột phát triển.
- Nhu cầu cách ly bảo mật hoặc tuân thủ thực sự yêu cầu phân vùng trách nhiệm.

Nếu chưa có nhu cầu này hoặc đội chưa có khả năng vận hành hệ thống phân tán, bắt đầu bằng modular monolith có module boundaries rõ thường giảm chi phí và vẫn giữ đường tách dịch vụ về sau.

## 7. Quy tắc ra quyết định thực tế

Trước khi chọn hoặc tách thêm một microservice, hãy trả lời năm nhóm câu hỏi:

**Ranh giới nghiệp vụ.** Có một bounded context rõ, sở hữu dữ liệu và quy tắc riêng không? Hay các “service” chỉ chia theo controller/repository và vẫn gọi chéo liên tục? Nếu một thao tác luôn cần transaction chặt qua nhiều thành phần, ranh giới có thể đang quá nhỏ.

**Nhu cầu độc lập.** Dịch vụ có tốc độ thay đổi, nhu cầu scale, SLA, bảo mật hoặc nhóm sở hữu khác biệt đủ lớn không? Mỗi lần thay đổi vẫn phải deploy đồng loạt bao nhiêu thành phần?

**Mạng và tính đúng đắn.** Bao nhiêu hop đồng bộ nằm trên critical path? Timeout và retry đã có giới hạn? Luồng thanh toán/đặt hàng có bảo đảm idempotency, compensation và trạng thái chờ rõ ràng không?

**Kiểm thử và vận hành.** Có contract tests, pipeline tự động, logs có correlation ID, metrics/SLO, tracing, backup/restore, runbook và người trực sự cố không? Nếu chưa, có kế hoạch và ngân sách trước khi tăng số service không?

**Lợi ích đo được.** Kết quả cần cải thiện là lead time triển khai, tần suất thay đổi, lỗi lan truyền, thời gian khôi phục, chi phí scale hay hiệu quả đội nhóm? Đặt chỉ tiêu và đo trước/sau; đừng chỉ đếm số service.

Một tín hiệu cần xem xét lại là **distributed monolith**: nhiều deployment nhưng phụ thuộc thời gian chạy và release quá chặt. Nó nhận phần lớn chi phí của microservices mà chưa thu được quyền tự chủ tương ứng.

## 8. Cách giảm rủi ro khi chuyển đổi

1. **Đo baseline của kiến trúc hiện tại:** throughput, p95/p99, tỷ lệ lỗi, thời gian build/deploy, số incident, chi phí hạ tầng, độ khó thay đổi một tính năng xuyên module.
2. **Làm rõ domain và data ownership:** xác định invariant, transaction boundary, API/event contracts và dữ liệu cần nhất quán mạnh. Cân nhắc củng cố modular monolith trước.
3. **Tách dịch vụ có lý do rõ nhất:** ưu tiên ranh giới ít gọi đồng bộ, tốc độ phát hành/scale khác biệt, hoặc có yêu cầu cô lập mạnh; tránh tách toàn bộ cùng lúc.
4. **Bổ sung các khả năng tối thiểu trước khi tăng quy mô:** timeout/deadline, idempotency, tracing, health/metrics, contract tests, automated deployment, rollback và runbook.
5. **Chạy thử dưới tải và lỗi có chủ đích:** đo p95/p99 cuối luồng, retry amplification, backlog, consistency lag, chi phí telemetry và thời gian khôi phục; kiểm tra được các trạng thái “thành công nhưng mất phản hồi”.
6. **Đánh giá lại bằng số đo:** nếu chi phí tăng mà deploy độc lập, khả năng chịu lỗi hoặc tốc độ thay đổi không cải thiện, thu hẹp ranh giới hoặc giữ chức năng trong monolith.

Không phải mọi giao tiếp liên dịch vụ đều nên chuyển sang event; async có thể giảm coupling về thời gian nhưng tăng độ phức tạp trạng thái, debugging và nhất quán. Chỉ dùng khi phù hợp semantics nghiệp vụ.

## 9. Tình huống áp dụng: chọn kiến trúc cho quy trình checkout

Một đội có ứng dụng bán hàng, đơn hàng tăng vào giờ khuyến mại, còn cập nhật nội dung và báo cáo có lưu lượng thấp. Đội cân nhắc ba lựa chọn:

**Phương án A — modular monolith:** Order, Inventory, Payment là các module rõ ràng cùng artifact; database dùng các ranh giới schema/quyền thích hợp. Chọn khi đội còn nhỏ, yêu cầu giao dịch đồng bộ cao, lưu lượng vừa và chưa có platform cho distributed tracing/on-call. Vẫn có thể tách worker gửi email hoặc xử lý tác vụ nền khi cần.

**Phương án B — tách Notification trước:** Checkout vẫn có transaction boundary đơn giản; sau commit phát sự kiện qua outbox để gửi thông báo bất đồng bộ. Lợi ích là phần Notification có thể scale và lỗi độc lập. Chi phí cần trả gồm broker, outbox, idempotent consumer, giám sát queue và xử lý retry/dead-letter.

**Phương án C — Order, Inventory, Payment độc lập:** Chọn khi ranh giới ownership rõ, các nhóm cần phát hành/scale riêng và tổ chức chấp nhận được chi phí Saga, contract testing, observability, sự cố mạng và reconciliation. Trước khi triển khai, phải vẽ trạng thái Order/Payment/Reservation, chỉ ra quyền quyết định trạng thái cuối, định nghĩa deadline, retry, compensation và UI khi pending.

Đối với bất kỳ phương án nào, thử một tình huống khó: Payment đã authorize nhưng đường truyền mất phản hồi. Hệ thống phải có mã giao dịch/idempotency key, tra cứu hoặc hòa giải trạng thái, tránh authorize lặp và chỉ thông báo kết quả chắc chắn khi có bằng chứng. Đây là ví dụ cho thấy chất lượng lựa chọn kiến trúc nằm ở xử lý đúng trạng thái thất bại, không chỉ ở sơ đồ service.

## 10. Những điểm cần ghi nhớ

- Microservices đổi lời gọi nội bộ thành giao tiếp phân tán, nên tạo thêm latency, traffic, timeout và failure mode; tối ưu số hop và đo latency ở toàn hành trình người dùng.
- Tách dữ liệu theo owner giúp tự chủ nhưng khiến transaction, query liên miền, replication và eventual consistency khó hơn; cần invariant, Saga/outbox và idempotency thích hợp.
- Kiểm thử cần bảo vệ API/event contracts và các lỗi thực tế như duplicate, timeout, partial success, version skew; nhiều E2E không tự động đồng nghĩa an toàn hơn.
- Vận hành cần automation, tracing, metrics/SLO, runbook, bảo mật và trách nhiệm ownership; chi phí con người và incident thường lớn hơn phần container nhìn thấy trên hóa đơn.
- So sánh **tổng chi phí và lợi ích đo được** với modular monolith. Chỉ chấp nhận độ phức tạp phân tán khi nhu cầu nghiệp vụ, tổ chức và vận hành thực sự biện minh cho nó.
