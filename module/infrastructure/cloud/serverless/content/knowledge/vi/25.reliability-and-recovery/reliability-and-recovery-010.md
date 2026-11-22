# Chaos testing và diễn tập chuyển vùng

Ứng dụng serverless có thể tự động mở rộng và được quản lý bởi cloud provider, nhưng điều đó không có nghĩa ứng dụng tự phục hồi trước mọi sự cố. Một function vẫn có thể timeout khi database chậm, xử lý message trùng khi retry, bị throttle khi concurrency tăng, mất kết nối sau sự cố mạng hoặc không thể phục vụ khi Region chính gặp lỗi. Nếu chưa từng kiểm tra các tình huống này, nhóm chỉ biết hệ thống hoạt động trong điều kiện bình thường.

**Chaos testing** là cách chủ động tạo ra một lỗi có kiểm soát để kiểm tra giả thuyết về khả năng chịu lỗi của hệ thống. **Diễn tập chuyển vùng (failover drill)** kiểm chứng khả năng chuyển workload sang vùng dự phòng, khôi phục dữ liệu và đưa traffic trở lại trạng thái ổn định. Cả hai cần có mục tiêu, phạm vi, tiêu chí dừng, người chịu trách nhiệm và bằng chứng đo lường.

Trong Java serverless, kiểm thử không chỉ dừng ở việc function còn trả HTTP 200 hay không. Cần xác minh toàn bộ luồng: trigger, runtime, quyền truy cập, queue, database, API đối tác, dữ liệu đã commit, retry, idempotency, routing và khả năng phục hồi. Một hệ thống chỉ được xem là phục hồi khi nghiệp vụ tiếp tục đúng và dữ liệu không bị mất hoặc ghi trùng ngoài chính sách.

## 1. Chaos testing và failover drill giải quyết vấn đề gì?

Chaos testing tập trung vào phản ứng của hệ thống khi một thành phần bị lỗi hoặc hoạt động kém. Failover drill tập trung vào quy trình khôi phục khi workload phải chuyển sang một môi trường hoặc Region khác.

| Hoạt động | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Fault injection | Hệ thống phản ứng thế nào khi dependency lỗi? | Database trả 503 hoặc timeout |
| Resilience test | Retry, timeout, circuit breaker có hoạt động đúng? | Function dừng retry sau số lần tối đa |
| Chaos experiment | Hành vi thực tế có khớp giả thuyết không? | Làm chậm 10% invocation trong 2 phút |
| Failover drill | Có chuyển được traffic sang vùng dự phòng? | Chuyển API từ Region A sang Region B |
| Recovery test | Sau khi chuyển vùng, dữ liệu và nghiệp vụ có đúng? | Đối soát order và replay message |
| Failback drill | Có đưa hệ thống về vùng chính an toàn? | Đồng bộ dữ liệu ngược và chuyển traffic lại |

Chaos testing không phải là cố tình làm hỏng production mà không có kế hoạch. Một thí nghiệm có trách nhiệm phải xác định rõ lỗi nào được tạo ra, ảnh hưởng tới thành phần nào, kéo dài bao lâu, chỉ số nào báo hiệu mất an toàn và ai có quyền dừng.

Failover drill cũng không chỉ là thay DNS. Cần xác minh vùng dự phòng có đủ code, cấu hình, quyền, network, quota, dữ liệu, queue và dependency để xử lý traffic thật.

## 2. HA, resilience và disaster recovery

Ba khái niệm có liên quan nhưng khác mục tiêu:

- **High Availability (HA):** giảm thời gian gián đoạn bằng dự phòng và tự động xử lý lỗi thường gặp. Lambda là dịch vụ managed được thiết kế để chạy qua nhiều Availability Zone trong một Region, nhưng dependency mà function gọi vẫn có thể tạo điểm lỗi đơn.
- **Resilience:** khả năng tiếp tục cung cấp hành vi nghiệp vụ đúng khi gặp lỗi, suy giảm hiệu năng hoặc thay đổi tải.
- **Disaster Recovery (DR):** khôi phục workload sau sự cố nghiêm trọng làm mất khả năng phục vụ tại địa điểm triển khai chính, ví dụ Region outage hoặc dữ liệu bị hỏng.

Một hệ thống có HA trong một Region chưa chắc có DR cho sự cố mất toàn Region. Ngược lại, có bản sao dữ liệu ở Region khác chưa chắc có thể phục vụ ngay vì function, API, secret, quyền và routing có thể chưa được triển khai.

Với serverless, cloud provider quản lý nhiều thành phần hạ tầng, nhưng nhóm ứng dụng vẫn chịu trách nhiệm về:

- Cách function xử lý dependency failure.
- Retry, timeout, duplicate và idempotency.
- Trạng thái và dữ liệu nghiệp vụ.
- Cấu hình trigger, queue, event source mapping.
- Khả năng triển khai cùng phiên bản ở Region dự phòng.
- Chuyển traffic và kiểm tra sau chuyển vùng.
- Quy trình failback và đối soát dữ liệu.

## 3. Xác định RTO và RPO trước khi thử nghiệm

Hai chỉ số quan trọng nhất của DR là:

**Recovery Time Objective (RTO)** là khoảng thời gian gián đoạn tối đa mà nghiệp vụ có thể chấp nhận. Ví dụ, nếu RTO là 30 phút, nhóm phải khôi phục khả năng xử lý giao dịch trong tối đa 30 phút kể từ thời điểm sự cố được xác định theo quy ước đo đã thống nhất.

**Recovery Point Objective (RPO)** là mức mất dữ liệu tối đa có thể chấp nhận, thường được biểu diễn bằng khoảng thời gian dữ liệu. Nếu RPO là 5 phút, hệ thống khôi phục không được mất quá 5 phút dữ liệu đã được xác nhận theo tiêu chí nghiệp vụ.

Ví dụ:

| Workload | RTO mục tiêu | RPO mục tiêu | Ý nghĩa |
|---|---:|---:|---|
| API tra cứu danh mục | 60 phút | 15 phút | Có thể chấp nhận khôi phục chậm và mất một ít thay đổi gần nhất |
| Tạo đơn hàng | 15 phút | 1 phút | Cần khôi phục nhanh và hạn chế mất giao dịch |
| Xử lý thanh toán | 5 phút | Gần 0 theo cam kết nghiệp vụ | Cần trạng thái giao dịch bền vững, idempotency và đối soát |
| Báo cáo nội bộ | 4 giờ | 1 giờ | Có thể dùng chiến lược backup/restore tiết kiệm hơn |

Các con số trên chỉ là ví dụ để minh họa cách đặt mục tiêu, không phải mức bảo đảm của dịch vụ cloud.

Đo RTO từ thời điểm bắt đầu gián đoạn theo định nghĩa tổ chức đến lúc nghiệp vụ được xác minh hoạt động trở lại. Đo RPO bằng cách so sánh các giao dịch đã xác nhận ở vùng chính với dữ liệu hiện có tại vùng phục hồi. Đừng chỉ đo thời gian API bắt đầu trả 200; cần kiểm tra giao dịch có thể đọc lại, cập nhật và hoàn tất đúng.

## 4. Các chiến lược DR theo chi phí và thời gian phục hồi

Một workload đa Region thường chọn một trong bốn mô hình:

| Chiến lược | Vùng dự phòng | Thời gian phục hồi tương đối | Chi phí và độ phức tạp |
|---|---|---|---|
| Backup and restore | Có backup, cần dựng môi trường khi sự cố xảy ra | Dài nhất | Thấp nhất |
| Pilot light | Hạ tầng lõi và dữ liệu quan trọng đã có, cần mở rộng/hoàn thiện khi failover | Trung bình đến dài | Trung bình |
| Warm standby | Môi trường chạy sẵn ở quy mô nhỏ, có thể nhận traffic sau khi scale | Ngắn hơn | Cao hơn |
| Multi-site active/active | Nhiều Region cùng phục vụ traffic | Có thể gần như liên tục nếu thiết kế đúng | Cao nhất |

**Backup and restore:** phù hợp với workload có RTO/RPO rộng. Cần backup dữ liệu, code, cấu hình và IaC; khi sự cố xảy ra, triển khai stack và restore dữ liệu.

**Pilot light:** giữ sẵn phần lõi như bản sao dữ liệu hoặc các thành phần thiết yếu. Khi failover, triển khai hoặc scale các thành phần còn lại.

**Warm standby:** môi trường dự phòng đã chạy và có thể xử lý một phần traffic. Khi sự cố, tăng capacity và chuyển traffic.

**Multi-site active/active:** nhiều Region cùng xử lý request. Mô hình này giảm phụ thuộc vào thao tác dựng môi trường nhưng yêu cầu giải quyết dữ liệu đồng thời, xung đột ghi, routing và tính nhất quán.

Chiến lược nhanh hơn thường tốn chi phí vận hành và hạ tầng cao hơn. Hãy chọn theo RTO/RPO và giá trị nghiệp vụ, không chọn active/active chỉ vì nghe có vẻ an toàn hơn.

## 5. Phân loại failure mode của serverless

Trước khi thiết kế thí nghiệm, lập danh sách lỗi theo lớp:

| Lớp | Failure mode | Biểu hiện |
|---|---|---|
| Trigger | API Gateway hoặc event source không gọi được function | Request 5xx, queue backlog tăng |
| Runtime | JVM khởi động lỗi, function timeout hoặc out of memory | Init error, duration tăng, invocation thất bại |
| Capacity | Concurrency quota hoặc reserved concurrency bị chạm | Throttles, retry và backlog |
| Network | DNS, NAT, route hoặc endpoint private lỗi | Connection timeout, name resolution failure |
| Dependency | Database, cache hoặc partner API chậm/ngừng | Latency tăng, 5xx, pool cạn |
| Identity | IAM role, token hoặc secret hết hạn/sai quyền | AccessDenied, authentication failure |
| Messaging | Duplicate, poison message, DLQ hoặc event ordering | Xử lý lặp, backlog, sai thứ tự |
| Data | Replica lag, dữ liệu hỏng hoặc mất consistency | Thiếu bản ghi, conflict, stale read |
| Region | API, function hoặc data service ở Region chính không sẵn sàng | Không thể phục vụ traffic tại Region |
| Release/config | Phiên bản mới hoặc cấu hình sai | Tăng lỗi sau deploy, trigger bị disable |

Không thử tất cả failure mode cùng lúc. Chọn một giả thuyết, một fault chính và một phạm vi có thể quan sát. Nếu nhiều lỗi xảy ra đồng thời, nhóm khó xác định nguyên nhân của kết quả.

## 6. Viết giả thuyết cho mỗi chaos experiment

Một thí nghiệm tốt bắt đầu bằng giả thuyết có thể kiểm chứng:

> Khi 10% request tới payment dependency nhận lỗi 503 trong 2 phút, Java function sẽ retry có giới hạn, giữ idempotency key, không tạo giao dịch trùng và duy trì tỷ lệ lỗi nghiệp vụ dưới ngưỡng đã thống nhất.

Một giả thuyết cần có:

1. **Steady state:** hệ thống bình thường được xác định bằng metric nào?
2. **Fault:** lỗi nào sẽ được tạo ra?
3. **Target:** thành phần hoặc tỷ lệ invocation nào bị tác động?
4. **Expected behavior:** ứng dụng phải phản ứng ra sao?
5. **Success criteria:** metric nào chứng minh giả thuyết đúng?
6. **Stop conditions:** điều gì khiến thí nghiệm phải dừng?
7. **Recovery:** fault được gỡ thế nào và hệ thống trở lại bình thường ra sao?

Ví dụ khác:

- Nếu một function nhận timeout từ database, circuit breaker phải ngăn request mới làm database quá tải.
- Nếu consumer xử lý cùng một event hai lần, chỉ một giao dịch nghiệp vụ được commit.
- Nếu Region chính không thể phục vụ, traffic chuyển sang Region dự phòng trong RTO và dữ liệu không vượt quá RPO.
- Nếu queue tăng backlog, consumer có thể xử lý lại mà không làm phát sinh side effect trùng.

Không dùng mục tiêu mơ hồ như "ứng dụng vẫn chạy tốt". Hãy đặt ngưỡng latency, error rate, backlog, duplicate count và business success rate cụ thể.

## 7. Thiết kế guardrails và giới hạn blast radius

Trước khi inject fault, xác định phạm vi ảnh hưởng tối đa. Các guardrail thường gồm:

- Chỉ chọn resource có tag dành riêng cho experiment.
- Bắt đầu ở dev hoặc staging với dữ liệu giả.
- Giới hạn số resource bằng count hoặc phần trăm nhỏ.
- Giới hạn thời gian fault.
- Có CloudWatch alarm hoặc monitoring tương đương làm stop condition.
- Có người trực theo dõi và quyền dừng ngay.
- Có runbook khôi phục và owner của dependency.
- Không chạy cùng lúc với deploy, migration hoặc campaign lớn.
- Bảo đảm backup và đường phục hồi hoạt động.
- Ghi lại trạng thái ban đầu để so sánh sau thí nghiệm.

AWS Fault Injection Service (FIS) dùng experiment template gồm actions, targets, stop conditions và experiment role. Stop condition có thể tham chiếu CloudWatch alarm; khi alarm được kích hoạt, FIS dừng experiment. Mỗi template cần một IAM role cho các hành động được phép. Xem [FIS experiment templates](https://docs.aws.amazon.com/fis/latest/userguide/experiment-templates.html) và [stop conditions](https://docs.aws.amazon.com/fis/latest/userguide/stop-conditions.html).

Một nguyên tắc an toàn là giới hạn cả **phạm vi kỹ thuật** lẫn **phạm vi nghiệp vụ**. Ví dụ, chỉ inject lỗi vào function staging, nhưng nếu function đó dùng chung database hoặc queue production thì blast radius vẫn có thể chạm production. Phải kiểm tra dependency thực tế, không chỉ nhìn tên environment.

## 8. Chuẩn bị steady-state metrics và stop conditions

Stop condition phải được định nghĩa trước khi bắt đầu. Một số metric cần cân nhắc:

| Metric | Tín hiệu dừng có thể dùng |
|---|---|
| HTTP 5xx/error rate | Vượt ngưỡng trong nhiều cửa sổ liên tiếp |
| p95/p99 latency | Vượt latency budget |
| Lambda Throttles | Tăng vượt giới hạn cho phép |
| Queue age | Message cũ nhất vượt SLA |
| DLQ message count | Xuất hiện poison message ngoài mức thử nghiệm |
| Database connections | Pool hoặc connection limit gần bão hòa |
| Replication lag | Vượt RPO |
| Business success rate | Tỷ lệ hoàn tất nghiệp vụ giảm dưới ngưỡng |
| Duplicate transaction | Có giao dịch trùng không được chặn |
| Customer impact | Có lỗi ảnh hưởng user thật ngoài phạm vi cho phép |

Stop condition không chỉ để bảo vệ CPU hoặc hạ tầng. Một thí nghiệm vẫn có thể nguy hiểm khi metric kỹ thuật xanh nhưng giao dịch bị tạo trùng, đơn hàng bị mất hoặc payment bị ghi sai trạng thái.

Hãy dùng nhiều lớp bảo vệ: alarm tự động, người theo dõi và nút dừng thủ công. Với AWS FIS, safety lever có thể dừng các experiment đang chạy và ngăn experiment mới bắt đầu trong Region đó. Xem [AWS FIS Safety Levers](https://docs.aws.amazon.com/fis/latest/userguide/safety-lever.html).

## 9. AWS FIS cho Lambda: fault injection vào invocation

AWS FIS có các action dành cho Lambda để tạo lỗi ở invocation. Tài liệu hiện hành liệt kê:

- **aws:lambda:invocation-add-delay:** thêm độ trễ trước khi function code chạy.
- **aws:lambda:invocation-error:** đánh dấu invocation thất bại; có thể chọn có chạy function code trước khi trả lỗi hay không.
- **aws:lambda:invocation-http-integration-response:** mô phỏng HTTP integration response.

Các action này dùng AWS FIS managed extension. Để sử dụng, cần gắn extension layer vào function, cấu hình S3 bucket để trao đổi fault configuration và thiết lập các quyền IAM cần thiết. Mỗi Region cần bucket riêng cho cấu hình extension. Extension không dùng được với Lambda response streaming; tài liệu cảnh báo nó có thể suppress streaming configuration ngay cả khi không inject fault.

Tham khảo [AWS FIS Lambda actions](https://docs.aws.amazon.com/fis/latest/userguide/use-lambda-actions.html) trước khi cấu hình. Không chỉ cài extension rồi chạy experiment: phải xác nhận layer version, S3 policy, environment variable, execution role và experiment role.

Hai environment variable bắt buộc của extension là:

~~~text
AWS_FIS_CONFIGURATION_LOCATION=arn:aws:s3:::fis-config-bucket/FisConfigs/
AWS_LAMBDA_EXEC_WRAPPER=/opt/aws-fis/bootstrap
~~~

Execution role của Lambda cần quyền đọc cấu hình trong bucket/prefix; experiment role cần quyền ghi và xóa fault configuration cùng các quyền cần để FIS kiểm tra function. Giữ bucket và policy tách biệt theo Region như hướng dẫn của AWS. Khi extension chờ cấu hình, polling mặc định có thể tạo ramp-up tối đa khoảng 60 giây; sau khi fault kết thúc có thể còn ramp-down khoảng 20 giây. Tính các khoảng này vào thời gian đo của experiment.

Một số chi tiết vận hành đáng lưu ý:

- Extension polling fault configuration có thể tạo khoảng ramp-up trước khi fault tác động tới mọi invocation.
- Với SnapStart, lần đầu nhận cấu hình fault có thể bị trễ hơn do snapshot chứa trạng thái polling.
- Function chạy rất nhanh hoặc ít được invoke có thể cần cấu hình poll behavior riêng.
- Fault injection có thể làm tăng billed duration nếu thêm delay.
- Phải kiểm thử extension ở staging và xác minh nó không thay đổi hành vi bình thường ngoài phạm vi dự kiến.

## 10. Ví dụ thiết kế thí nghiệm Lambda

Giả sử có function **orders-api** gọi **payment-service**. Mục tiêu là kiểm tra handler khi nhận lỗi tạm thời.

| Thuộc tính | Giá trị minh họa |
|---|---|
| Giả thuyết | Function retry tối đa 2 lần với backoff, không tạo payment trùng |
| Target | ARN cụ thể của function staging |
| Fault | Invocation error hoặc thêm delay |
| Tỷ lệ | 10% invocation |
| Thời gian | 2 phút |
| Success criteria | Không có duplicate payment; p99 và error rate trong ngưỡng |
| Stop condition | Business success giảm mạnh hoặc DLQ tăng bất thường |
| Recovery | Dừng experiment, xác minh extension ngừng fault, replay message an toàn |

Trước khi chạy, tạo một dashboard theo dõi invocation count, errors, duration, retries, DLQ, payment transaction ID và idempotency key. Dùng sandbox payment provider hoặc stub để không tạo giao dịch tài chính thật.

Không bắt đầu với 100% invocation ở production. Tăng tỷ lệ từ nhỏ lên lớn chỉ sau khi các lần thử trước chứng minh hệ thống giữ được steady state.

## 11. Kiểm thử dependency chậm hoặc không sẵn sàng

Dependency failure là một trong những tình huống phổ biến nhất với serverless. Function scale nhanh có thể tạo áp lực lên database hoặc partner API khi dependency đang suy giảm.

Các fault nên thử:

- Response 503 hoặc 429.
- Connect timeout.
- Read timeout.
- Latency tăng cao nhưng vẫn trả 200.
- DNS không phân giải được hostname.
- TLS handshake thất bại.
- Connection bị reset giữa chừng.
- Database từ chối connection hoặc đạt connection limit.

Kết quả mong đợi:

- Timeout được đặt rõ cho connect và read.
- Retry chỉ áp dụng với lỗi transient và operation an toàn để retry.
- Exponential backoff có jitter để tránh retry storm.
- Circuit breaker ngăn gọi dependency liên tục khi đang lỗi.
- Bulkhead giới hạn concurrency hoặc connection pool.
- Caller nhận lỗi có thể xử lý hoặc degraded response theo contract.
- Log/trace có correlation ID để nối request với dependency failure.

Không retry vô hạn. Khi dependency đã quá tải, retry dồn dập làm tăng tải và khiến sự cố kéo dài hơn. Có thể trả lỗi tạm thời, đưa message về queue hoặc sử dụng dữ liệu cache cũ nếu nghiệp vụ cho phép.

## 12. Kiểm thử retry, duplicate và idempotency

Nhiều trigger serverless có semantics giao nhận ít nhất một lần hoặc có thể retry khi function lỗi. Do đó, một event có thể được xử lý lại sau timeout, mất acknowledgment hoặc lỗi tạm thời.

Chaos experiment nên chủ động tạo các trường hợp:

- Cùng event được gửi hai lần.
- Function commit database nhưng timeout trước khi trả kết quả.
- Function gửi request tới partner thành công nhưng không nhận được response.
- Message bị xử lý lại sau khi visibility timeout.
- Hai invocation đồng thời xử lý cùng một business key.
- Event cũ đến sau event mới.

Một handler an toàn phải có idempotency key ổn định, thường là event ID hoặc business operation ID. Lưu key bằng thao tác atomic/conditional write cùng trạng thái kết quả. Nếu event đã hoàn tất, trả lại kết quả trước đó hoặc bỏ qua side effect lặp theo contract.

Ví dụ logic:

~~~java
public Result handle(OrderEvent event) {
    String key = event.eventId();

    IdempotencyRecord existing = store.find(key);
    if (existing != null && existing.isCompleted()) {
        return existing.result();
    }

    // reserveIfAbsent phải là thao tác atomic trong persistent store.
    boolean reserved = store.reserveIfAbsent(key);
    if (!reserved) {
        return store.waitForOrReadResult(key);
    }

    try {
        Result result = orderService.process(event);
        store.markCompleted(key, result);
        return result;
    } catch (TransientDependencyException error) {
        store.markRetryableFailure(key, safeErrorCode(error));
        throw error;
    } catch (RuntimeException error) {
        store.markPermanentFailure(key, safeErrorCode(error));
        throw error;
    }
}
~~~

Đây là pseudocode minh họa; repository phải bảo đảm atomicity, xử lý lease/timeout cho record đang xử lý và không để một invocation lỗi giữ khóa vĩnh viễn. Không dùng static HashSet hoặc in-memory map làm kho idempotency vì execution environment có thể bị tái tạo và nhiều environment chạy đồng thời.

TransientDependencyException là kiểu lỗi ứng dụng dùng để biểu thị lỗi có thể thử lại. Lỗi validation, authorization hoặc business rule phải đi theo nhánh permanent; với queue trigger, cấu hình consumer để chuyển lỗi permanent tới DLQ/quarantine thay vì retry vô hạn. Pseudocode cần được điều chỉnh theo semantics của trigger và transaction store thực tế.

## 13. Kiểm thử timeout, concurrency và backpressure

Một function có thể xử lý tốt ở tải thấp nhưng thất bại khi nhiều invocation chạy cùng lúc. Hãy thử:

- Tăng concurrency theo từng bước.
- Giảm reserved concurrency để mô phỏng giới hạn.
- Tạo backlog lớn ở queue.
- Làm chậm database để connection pool đầy.
- Tạo burst request tới API Gateway.
- Làm dependency trả 429/503 theo tỷ lệ.
- Tạo một nhóm message xử lý lâu hơn visibility timeout.

Quan sát:

- ConcurrentExecutions và Throttles.
- Queue age, visible/in-flight messages và DLQ.
- Database connection count, CPU, lock wait và query latency.
- Retry count và số lần xử lý trung bình mỗi event.
- p95/p99 end-to-end latency.
- Tỷ lệ business success và duplicate.

Backpressure có thể được tạo bằng cách giới hạn concurrency, batch size hoặc tốc độ tiêu thụ. Nếu queue backlog tăng, hệ thống cần có cách giảm producer rate, giới hạn consumer concurrency hoặc chuyển message lỗi sang DLQ để bảo vệ dependency.

Không tăng concurrency vô hạn để giải backlog. Nếu downstream chỉ chịu được 100 request đồng thời, scale function lên 1.000 có thể làm sự cố nặng hơn.

## 14. Kiểm thử lỗi mạng và DNS

Serverless function thường kết nối tới database private, cache, API đối tác hoặc dịch vụ cloud qua DNS và network path. Một lỗi DNS hoặc route có thể khiến function timeout dù runtime vẫn khỏe.

Các tình huống:

- DNS resolver không phản hồi.
- Hostname trả địa chỉ cũ.
- Private DNS zone không được liên kết với VPC/VNet.
- NAT gateway hoặc route không hoạt động.
- Security group/firewall chặn port.
- TLS certificate hết hạn hoặc hostname mismatch.
- Connection pool giữ socket đã bị peer đóng.

Kiểm thử trong môi trường được cô lập và chỉ inject lỗi vào endpoint thử nghiệm. Theo dõi DNS lookup latency, connection timeout, TLS handshake failure và số lần reconnect.

Trong Java, không giữ connection hoặc IP cache vô thời hạn. Dùng timeout, pool lifetime hợp lý và retry có giới hạn. Với SnapStart hoặc runtime có thể restore environment, kiểm tra lại socket và DNS cache sau restore.

## 15. Kiểm thử IAM, token và secret failure

Một function có thể hoạt động ở test nhưng thất bại khi credential hết hạn hoặc policy bị thay đổi.

Các thí nghiệm nên làm trong staging:

- Role bị thiếu quyền đọc object hoặc gửi message.
- Secret bị rotate trong khi environment còn tồn tại.
- Token của partner hết hạn.
- KMS decrypt bị từ chối.
- Managed identity/service role không thể truy cập dependency.
- Certificate hoặc trust bundle thay đổi.

Hành vi mong đợi:

- Function trả lỗi có thể chẩn đoán, không lộ secret.
- Credential được refresh theo cơ chế SDK/provider.
- Permission error không bị retry liên tục như lỗi transient.
- Secret rotation không yêu cầu redeploy code nếu thiết kế cho phép refresh an toàn.
- Audit log ghi lại principal và thao tác bị từ chối.

Không inject policy deny vào role production dùng chung. Tạo role, secret hoặc resource riêng cho thử nghiệm để giới hạn blast radius.

## 16. Kiểm thử poison message và DLQ

Poison message là message luôn thất bại vì dữ liệu không hợp lệ, schema không tương thích hoặc lỗi nghiệp vụ không thể tự phục hồi. Nếu message được retry liên tục, nó có thể chiếm capacity và làm backlog tăng.

Một chaos drill nên tạo message có:

- Field bắt buộc bị thiếu.
- Schema version không được hỗ trợ.
- Payload vượt giới hạn.
- Reference tới resource không tồn tại.
- Giá trị nghiệp vụ ngoài miền cho phép.
- Dữ liệu gây lỗi parser.

Consumer cần phân loại lỗi:

- Lỗi transient: retry theo policy.
- Lỗi permanent: đưa vào DLQ hoặc quarantine.
- Lỗi không rõ: giới hạn retry, log context và yêu cầu điều tra.

Sau khi sửa lỗi, replay message từ DLQ theo batch nhỏ, có idempotency và quan sát kết quả. Không replay toàn bộ DLQ trực tiếp vào production khi chưa biết nguyên nhân hoặc chưa kiểm tra side effect.

## 17. Kiểm thử lỗi trong một Availability Zone

Một Region thường có nhiều Availability Zone. Nếu workload sử dụng dịch vụ managed multi-AZ, nhiều lỗi hạ tầng có thể được provider xử lý tự động. Tuy nhiên, ứng dụng vẫn có thể phụ thuộc vào tài nguyên đặt ở một AZ, subnet, NAT, database endpoint hoặc service endpoint không có redundancy.

Thử nghiệm AZ cần xác định:

- Function có cấu hình VPC subnet ở nhiều AZ không?
- Database có replica/failover trong AZ khác không?
- Network route và NAT có điểm lỗi đơn không?
- Có dependency private chỉ tồn tại ở một AZ không?
- Queue/event source có tiếp tục cung cấp message khi một AZ mất không?
- Application có chịu được connection reset và reconnect không?

Không nên tự giả định Lambda function gắn với một AZ cố định. Lambda quản lý execution environment; khi function kết nối VPC, cần xem xét subnet, ENI và dependency network. Fault injection nên tác động vào thành phần có thể kiểm soát và đo được, thay vì cố tình phá một AZ thật.

Sau thử nghiệm, xác minh function tiếp tục xử lý, database failover hoàn tất, connection pool tái lập và không có message bị mất hoặc xử lý trùng ngoài chính sách.

## 18. Chiến lược đa Region cho serverless

Một kiến trúc DR đa Region thường gồm:

~~~mermaid
flowchart TD
    U["Clients"] --> R["Global DNS / routing control"]
    R --> P["Primary Region"]
    R -. "Failover" .-> S["Recovery Region"]
    subgraph PR["Primary Region"]
      P --> PF["API Gateway"]
      PF --> PL["Java Lambda functions"]
      PL --> PD[("Primary data store")]
      PL --> PQ["Queue / event bus"]
    end
    subgraph DR["Recovery Region"]
      S --> SF["API Gateway"]
      SF --> SL["Java Lambda functions"]
      SL --> SD[("Replicated data store")]
      SL --> SQ["Recovery queue / event bus"]
    end
    PD -. "Replication / backup" .-> SD
~~~

Các thành phần cần có ở Region dự phòng:

- Cùng artifact và version của Java function.
- API Gateway, custom domain mapping và authorizer.
- IAM role, resource policy và managed identity.
- Environment variables, secret và KMS key phù hợp.
- VPC, subnet, security group, route và private DNS.
- Queue, event bus, DLQ và event source mapping.
- Database replica hoặc cơ chế restore.
- Alarm, dashboard, log group và tracing.
- Service quota, concurrency và deployment pipeline.
- DNS/routing control và runbook chuyển vùng.

Đừng coi Region dự phòng chỉ là nơi có database replica. Nếu function code, secret, KMS, queue hoặc IAM chưa sẵn sàng, traffic được chuyển sang đó vẫn không xử lý được nghiệp vụ.

## 19. Kiểm tra dữ liệu replication và consistency

Replication thường có độ trễ. Với asynchronous replication, một giao dịch vừa commit ở Region chính có thể chưa xuất hiện ở Region dự phòng.

Khi failover:

- Xác định thời điểm dữ liệu cuối cùng đã replicate.
- Đối chiếu transaction ID hoặc sequence number.
- Kiểm tra record đã commit nhưng chưa replicate.
- Chặn hai Region cùng ghi nếu kiến trúc active/passive.
- Có cơ chế fencing hoặc ownership token để ngăn split-brain.
- Xử lý event đến trễ và duplicate.
- Ghi nhận giao dịch cần reconcile.

Với active/active, cần thiết kế conflict resolution. Có thể phân vùng quyền ghi theo tenant hoặc aggregate, dùng version/sequence và conditional update, hoặc có một writer authority cho từng business entity. Không để hai Region cập nhật cùng một bản ghi theo last-write-wins nếu nghiệp vụ không chấp nhận mất cập nhật.

Replication không thay thế backup. Nếu dữ liệu bị xóa hoặc mã hóa sai ở Region chính, replication có thể sao chép lỗi sang Region dự phòng. Cần backup có point-in-time recovery và kiểm tra restore định kỳ.

## 20. Failover routing bằng DNS

DNS failover có thể chuyển client tới endpoint ở Region dự phòng dựa trên health check hoặc routing policy. Với Route 53, failover record có primary và secondary; health check giúp Route 53 chọn record phù hợp.

Một số điểm cần nhớ:

- TTL ảnh hưởng thời gian resolver cache answer cũ.
- Client có thể giữ connection hiện tại dù DNS đã đổi.
- Health check phải phản ánh trạng thái ứng dụng có thể phục vụ nghiệp vụ.
- Một endpoint trả 200 từ health endpoint chưa chắc database hoặc queue hoạt động.
- Không nên cho health check gọi thao tác có side effect.
- Test failover từ nhiều network/resolver nếu user phân bố nhiều vùng.

Route 53 có chế độ last resort: khi mọi record bị xem là unhealthy, thuật toán có thể coi tất cả record là healthy để tránh trả NXDOMAIN. Vì vậy, không thể giả định "mọi endpoint đỏ" sẽ tự động khiến DNS ngừng trả record. Hãy đọc [Route 53 failover behavior](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-problems.html) và kiểm thử policy thực tế.

AWS khuyến nghị dùng TTL thấp hơn cho record cần failover nhanh; 60 hoặc 120 giây là ví dụ phổ biến, nhưng resolver và connection cache vẫn có thể kéo dài thời gian chuyển traffic. Xem [Route 53 DNS best practices](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/best-practices-dns.html).

## 21. Dùng Application Recovery Controller routing controls

Amazon Application Recovery Controller (ARC) cung cấp routing controls để chuyển traffic giữa các application replica. Routing control là công tắc on/off gắn với Route 53 health check; bản thân nó không đo latency hay health của endpoint.

Mô hình đơn giản:

1. Có routing control cho primary và recovery replica.
2. Mỗi control gắn với health check tương ứng.
3. Health check gắn với DNS record định tuyến tới endpoint Region.
4. Khi failover, operator hoặc automation đổi trạng thái control.
5. DNS routing chuyển traffic theo health check mới.

ARC có safety rules để ngăn thao tác chuyển traffic làm giảm availability, ví dụ bật traffic vào standby chưa sẵn sàng hoặc tắt cả hai replica. Routing control có thể là manual override hữu ích khi health check tự động không nhận ra lỗi nghiệp vụ.

Việc chuyển traffic không nhất thiết tức thì. DNS cache và connection đang mở có thể tiếp tục đưa request tới Region cũ trong một khoảng thời gian. Xem [ARC routing control](https://docs.aws.amazon.com/r53recovery/latest/dg/routing-control.about.html).

Đối với DR, ưu tiên đường điều khiển phục hồi đã được chuẩn bị và kiểm thử trước sự cố. AWS khuyến nghị cân nhắc data plane operations cho failover vì control plane thường có kiến trúc tập trung hơn. Xem [Route 53 data plane best practices](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/best-practices-dns.html).

## 22. Diễn tập chuyển vùng: quy trình tổng thể

Một failover drill nên chạy theo trình tự:

~~~mermaid
flowchart TD
    A["Chọn kịch bản và mục tiêu RTO/RPO"] --> B["Kiểm tra preconditions"]
    B --> C["Ghi baseline và xác nhận dữ liệu"]
    C --> D["Mô phỏng sự cố Region chính"]
    D --> E["Phát hiện và tuyên bố failover"]
    E --> F["Kích hoạt Region dự phòng"]
    F --> G["Chuyển routing"]
    G --> H["Smoke test và kiểm tra dữ liệu"]
    H --> I{"Đạt RTO/RPO và business checks?"}
    I -->|"Không"| J["Dừng drill / khôi phục trạng thái an toàn"]
    I -->|"Có"| K["Giữ traffic và theo dõi ổn định"]
    K --> L["Chuẩn bị failback"]
    L --> M["Đồng bộ dữ liệu và chuyển traffic về"]
    M --> N["Đối soát và ghi nhận bài học"]
~~~

### Giai đoạn 1: chuẩn bị

- Chọn một Region chính và một Region dự phòng.
- Xác định owner của API, function, data, network và routing.
- Xác nhận backup, replication và IaC.
- Kiểm tra service quota và concurrency ở Region dự phòng.
- Xác định cách dừng experiment.
- Thông báo người tham gia và thời gian diễn tập.
- Chụp baseline của metric và dữ liệu nghiệp vụ.

### Giai đoạn 2: chuyển vùng

- Tạo lỗi mô phỏng hoặc đánh dấu primary không thể phục vụ theo kịch bản.
- Xác nhận tiêu chí declare disaster đã đạt.
- Kích hoạt recovery stack nếu dùng pilot light hoặc warm standby.
- Xác nhận function, API, IAM, secret, queue và database sẵn sàng.
- Chuyển traffic bằng routing control hoặc failover policy.
- Theo dõi request mới, request đang mở và queue backlog.

### Giai đoạn 3: xác minh

- Gọi health endpoint và business transaction test.
- Đọc lại dữ liệu vừa ghi.
- Kiểm tra duplicate, missing event và DLQ.
- Đo RTO và RPO thực tế.
- Xác nhận p95/p99, error rate và throughput.
- Kiểm tra audit log và trace.

### Giai đoạn 4: kết thúc

- Giữ vùng dự phòng trong trạng thái ổn định đủ lâu để quan sát.
- Quyết định failback hoặc tiếp tục chạy ở Region dự phòng.
- Đồng bộ dữ liệu theo hướng quay lại.
- Chuyển traffic theo từng bước.
- Đối soát dữ liệu và xử lý backlog.
- Viết báo cáo với thời gian, metric, sai lệch và action item.

## 23. Failback: đưa traffic về Region chính

Failback thường khó hơn failover vì Region chính có thể chứa dữ liệu cũ, cấu hình lệch hoặc resource đã bị thay đổi trong lúc phục hồi.

Trước khi failback:

1. Xác định Region nào đang là writer.
2. Ngăn hai Region cùng nhận quyền ghi nếu kiến trúc active/passive.
3. Đồng bộ dữ liệu mới nhất từ Region đang hoạt động về Region chính.
4. Xử lý event chưa hoàn tất và message trong queue.
5. Kiểm tra schema, version và cấu hình tương thích.
6. Chạy smoke test ở Region chính.
7. Chuyển một phần traffic để quan sát nếu routing hỗ trợ.
8. Chuyển phần traffic còn lại sau khi đạt tiêu chí.
9. Giữ đường rollback nếu Region chính phát sinh lỗi.
10. Đối soát giao dịch sau khi hoàn tất.

Không failback tự động ngay khi health check của Region chính chuyển xanh. Region có thể trả lời health request nhưng dữ liệu chưa đồng bộ, queue chưa sẵn sàng hoặc dependency còn bị suy giảm.

## 24. Các kịch bản chaos và DR nên diễn tập

| Kịch bản | Cách mô phỏng | Điều cần xác minh |
|---|---|---|
| Lambda invocation lỗi | FIS invocation-error hoặc test adapter | Retry, alarm và DLQ hoạt động |
| Function chậm | FIS invocation-add-delay | Timeout, caller deadline và concurrency |
| Partner API 503 | Stub/proxy trả lỗi | Backoff, circuit breaker và idempotency |
| Database mất kết nối | Fault ở test dependency/network | Reconnect, timeout, fallback |
| Queue backlog | Giới hạn consumer concurrency | Backpressure và recovery throughput |
| Poison message | Gửi payload không hợp lệ | DLQ và replay an toàn |
| IAM deny | Role thử nghiệm thiếu permission | Error classification, audit và không retry vô hạn |
| DNS sai | Private DNS test zone hoặc resolver fault | Timeout, fallback endpoint |
| AZ dependency outage | Fault vào endpoint/AZ dependency thử nghiệm | Multi-AZ behavior và reconnect |
| Region primary unavailable | Diễn tập routing và DR stack | RTO, RPO, data consistency |
| Data corruption | Tạo bản ghi sai trong dataset test | Backup restore và reconciliation |
| Secret rotation | Rotate secret trong lúc function chạy | Refresh credential và tránh downtime |

Chọn kịch bản theo rủi ro có thật trong kiến trúc. Không cần chạy mọi loại fault nếu hệ thống không dùng thành phần tương ứng.

## 25. Java function cần làm gì khi sự cố xảy ra?

Một Java function có khả năng phục hồi thường có các đặc điểm:

- Handler stateless; không phụ thuộc vào memory của một execution environment.
- Dùng timeout ngắn hơn deadline của caller và dành thời gian cho cleanup.
- Retry có giới hạn, exponential backoff và jitter.
- Không retry lỗi permanent như validation hoặc authorization.
- Idempotency cho thao tác tạo dữ liệu và side effect.
- Circuit breaker hoặc bulkhead bảo vệ dependency quan trọng.
- Connection pool có giới hạn và tự phục hồi.
- Không lưu trạng thái nghiệp vụ duy nhất trong /tmp hoặc static field.
- Log có correlation ID, event ID và release version.
- Có graceful degradation khi một dependency phụ không sẵn sàng.

Không nên catch mọi exception rồi trả HTTP 200. Điều đó che giấu failure khỏi caller, queue retry và monitoring. Hãy trả status hoặc kết quả theo contract để hệ thống gọi quyết định retry, dead-letter hoặc thông báo lỗi.

Với queue trigger, chỉ xác nhận message thành công sau khi trạng thái nghiệp vụ đã được ghi bền vững. Với HTTP, nếu client timeout nhưng transaction đã commit, idempotency key giúp client retry mà không tạo side effect thứ hai.

## 26. Công cụ chaos theo nền tảng

Nguyên tắc giả thuyết, blast radius, stop condition và đo steady state giống nhau giữa các cloud; công cụ và loại fault được hỗ trợ sẽ khác:

| Nền tảng | Công cụ/khả năng | Điểm cần chú ý |
|---|---|---|
| AWS | AWS Fault Injection Service; Lambda actions qua managed extension | Experiment template, target, IAM role, stop condition; Lambda extension cần S3 configuration bucket và không hỗ trợ response streaming |
| Azure | Azure Chaos Studio | Experiment resource, target/capability và managed identity; quyền bắt đầu experiment phải được giới hạn chặt |
| Ứng dụng Java | Test double, fault proxy hoặc dependency stub | Hữu ích để mô phỏng lỗi ở tầng application/dependency mà công cụ hạ tầng không thể tạo trực tiếp |

Với Azure Chaos Studio, kiểm soát quyền bắt đầu experiment là trọng yếu vì thao tác đó có thể inject fault vào resource đã chọn. Xem [Azure Chaos Studio security and permissions](https://learn.microsoft.com/en-us/azure/chaos-studio/chaos-studio-permissions-security). Dù dùng công cụ nào, hãy thử nghiệm trên resource cô lập trước và xác nhận cách dừng fault.

## 27. Kiểm thử stateful workflow và saga

Một quy trình serverless có thể gồm nhiều function và service: tạo order, giữ inventory, thanh toán, gửi email. Nếu một bước thất bại, không thể chỉ retry toàn bộ workflow mà không biết các bước trước đã commit hay chưa.

Chaos testing nên inject lỗi tại từng bước:

- Function A commit order nhưng timeout trước response.
- Function B giữ inventory thành công nhưng message bị duplicate.
- Function C thanh toán thành công nhưng acknowledgment bị mất.
- Function D gửi email lỗi trong khi giao dịch chính đã hoàn tất.

Cần có workflow state bền vững, event ID, idempotency key và compensation action. Saga có thể dùng action bù để hoàn tác hoặc đưa nghiệp vụ về trạng thái nhất quán, ví dụ release inventory hoặc refund payment.

Không giả định compensation luôn khôi phục thế giới về trạng thái ban đầu. Một email đã gửi không thể "thu hồi"; một payment đã capture có thể cần refund riêng. Thiết kế trạng thái nghiệp vụ như PENDING, AUTHORIZED, CAPTURED, FAILED, COMPENSATING để phân biệt kết quả.

## 28. Kiểm tra backup và restore dữ liệu

Một DR drill không hoàn chỉnh nếu chỉ kiểm tra replication. Hãy thử restore từ backup vào môi trường cô lập:

1. Chọn recovery point theo RPO.
2. Khôi phục database hoặc object store.
3. Xác minh schema và index.
4. Chạy query kiểm tra tính toàn vẹn.
5. Đối chiếu số lượng record và tổng giá trị nghiệp vụ.
6. Chạy application smoke test trên dữ liệu đã restore.
7. Xác minh quyền, KMS key và secret.
8. Đo thời gian hoàn tất restore.
9. Ghi lại dữ liệu bị mất theo RPO.
10. Xóa môi trường thử nghiệm theo quy trình.

Replication giúp có bản sao gần thời gian thực nhưng có thể sao chép dữ liệu bị hỏng hoặc bị xóa. Backup point-in-time giúp quay lại trạng thái trước lỗi. Cần cả hai nếu workload yêu cầu bảo vệ trước data corruption hoặc thao tác xóa nhầm.

## 29. Kiểm thử event replay và backlog recovery

Sau failover, queue hoặc event stream có thể chứa message chưa được xử lý. Một số message có thể đang in-flight, một số bị retry và một số đã vào DLQ.

Quy trình recovery:

- Xác định queue/stream nào là nguồn authoritative.
- Kiểm tra offset, checkpoint hoặc visibility timeout.
- Xác định message đã xử lý nhưng chưa ack.
- Đảm bảo consumer ở Region mới dùng idempotency store phù hợp.
- Replay theo batch có giới hạn.
- Theo dõi age of oldest message và processing throughput.
- Dừng replay nếu duplicate hoặc business error vượt ngưỡng.
- Đối soát event count với transaction count.

Với stream partitioned, cần bảo toàn ordering theo partition/aggregate khi nghiệp vụ yêu cầu. Không replay toàn bộ stream mà không xác định checkpoint vì có thể đảo thứ tự hoặc tạo lại side effect.

## 30. Quan sát chaos experiment và failover

Mỗi thí nghiệm cần có dashboard và log riêng. Các nhóm metric nên theo dõi:

**Application**
- Request success/error rate.
- p50, p95, p99 latency.
- Function Errors, Duration, Throttles và ConcurrentExecutions.
- Init/restore hoặc timeout count.

**Messaging**
- Queue depth.
- Age of oldest message.
- Retry count.
- DLQ count.
- Duplicate event count.
- Consumer throughput.

**Data**
- Database connections, latency và failover events.
- Replication lag.
- Transaction count và reconciliation mismatch.
- Backup/restore duration.

**Routing**
- Health check status.
- DNS answer theo resolver.
- Routing control state.
- Traffic split theo Region.
- Connection còn mở tới Region cũ.

**Business**
- Order success rate.
- Payment success/failure/unknown state.
- Inventory mismatch.
- Giao dịch cần manual reconciliation.
- Customer-visible errors.

Gắn experiment ID, Region, fault type và release version vào log/metric dimension. Tránh dùng raw customer data làm metric label hoặc ghi secret vào log.

## 31. Runbook cho sự cố Region

Runbook cần trả lời được các câu hỏi sau mà không cần người trực phải tự đoán:

1. Điều kiện nào được coi là Region outage?
2. Ai có quyền tuyên bố failover?
3. Dashboard và health check nào là nguồn sự thật?
4. Region dự phòng có đang sẵn sàng không?
5. Dữ liệu replicate đến thời điểm nào?
6. Có cần fence Region chính trước khi bật writer ở Region mới?
7. Lệnh hoặc thao tác nào chuyển routing?
8. Cách xác minh API và business transaction?
9. Cách xử lý queue backlog, DLQ và event replay?
10. Khi nào được phép failback?
11. Ai phê duyệt failback và ai theo dõi đối soát?
12. Cách thông báo trạng thái cho các nhóm liên quan?

Runbook nên lưu ở nơi có thể truy cập khi hệ thống chính gặp sự cố. Nếu runbook chỉ nằm trong wiki hoặc storage ở Region chính, nhóm có thể mất quyền truy cập đúng lúc cần nhất. Duy trì bản offline hoặc bản sao độc lập theo chính sách tổ chức.

## 32. Game day và vai trò của nhóm

Một game day là buổi diễn tập có người điều phối, người vận hành và người quan sát. Vai trò có thể gồm:

| Vai trò | Trách nhiệm |
|---|---|
| Incident commander | Quyết định bắt đầu, dừng và tuyên bố failover |
| Experiment operator | Thực hiện fault injection theo template |
| Application owner | Theo dõi function và business behavior |
| Data owner | Kiểm tra replication, backup và consistency |
| Network/platform owner | Theo dõi DNS, routing, VPC và quota |
| Observer/scribe | Ghi timeline, metric, quyết định và sai lệch |
| Communications lead | Cập nhật trạng thái cho stakeholder |

Trong game day đầu tiên, nên chọn kịch bản nhỏ, phạm vi rõ và không ảnh hưởng khách hàng. Sau khi nhóm quen quy trình, có thể diễn tập failover ở staging hoặc một phần traffic production theo policy.

Không biến game day thành bài kiểm tra cá nhân. Mục tiêu là tìm ra lỗ hổng trong kiến trúc, automation, runbook và quyền truy cập.

## 33. Tiêu chí kết thúc và báo cáo sau diễn tập

Một experiment chỉ hoàn tất khi:

- Fault đã được gỡ hoặc experiment đã dừng.
- Hệ thống trở về steady state.
- Không còn queue backlog bất thường hoặc có kế hoạch xử lý rõ.
- Không có side effect nghiệp vụ ngoài dự kiến.
- Data consistency được kiểm tra.
- Region/routing state được xác nhận.
- Alarm đã trở về trạng thái bình thường.
- Người điều phối xác nhận kết thúc.

Báo cáo sau diễn tập nên ghi:

- Giả thuyết và mục tiêu.
- Ngày giờ, Region và resource scope.
- Fault đã inject và thời gian thực tế.
- Timeline phát hiện, quyết định, failover, phục hồi và failback.
- RTO/RPO thực tế so với mục tiêu.
- Metric trước/trong/sau.
- Giao dịch mất, trùng hoặc cần đối soát.
- Điểm nào hoạt động tốt.
- Điểm nào không đạt.
- Action item, owner và deadline.

Ưu tiên sửa những lỗi có thể gây mất dữ liệu, split-brain, side effect trùng hoặc vượt RTO/RPO. Sau khi sửa, chạy lại đúng thí nghiệm để xác nhận.

## 34. Lỗi thường gặp khi chaos testing và failover

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Không có giả thuyết rõ | Không biết kết quả có thành công | Định nghĩa steady state và success criteria |
| Không có stop condition | Fault vượt blast radius | Alarm, safety lever và operator |
| Chỉ test function, bỏ qua database/queue | Bỏ sót dependency bottleneck | Kiểm thử toàn bộ request path |
| Health check chỉ ping runtime | Chuyển traffic tới ứng dụng không dùng được | Health check phản ánh dependency và nghiệp vụ |
| Chỉ kiểm tra DNS đổi record | Client vẫn gọi Region cũ | Test resolver cache và connection reuse |
| Region dự phòng chưa đủ quota | Không scale được khi failover | Preflight quota và concurrency |
| Replication lag không được đo | RPO vượt mục tiêu | Theo dõi lag và transaction sequence |
| Hai Region cùng ghi | Split-brain và conflict | Fencing, writer ownership và conflict policy |
| Replay DLQ không idempotent | Side effect trùng | Deduplication và replay batch |
| Không diễn tập failback | Vùng chính không thể nhận traffic lại an toàn | Có runbook và rehearsal riêng |
| Không đối soát nghiệp vụ | API xanh nhưng dữ liệu sai | Business reconciliation sau recovery |

## 35. Checklist production cho chaos và DR

**Trước thí nghiệm**

1. Có giả thuyết và steady-state metric?
2. Đã xác định target, blast radius và thời gian fault?
3. Có stop condition tự động và người dừng thủ công?
4. Có backup/restore hoặc rollback phù hợp?
5. Đã kiểm tra dependency dùng chung với production?
6. Experiment role và IAM permission chỉ đủ quyền cần thiết?
7. Đã thông báo owner và người trực?
8. Không trùng với deploy hoặc migration rủi ro?

**Trong thí nghiệm**

9. Có dashboard theo dõi application và business metric?
10. Có correlation ID và experiment ID?
11. Fault có tác động đúng tỷ lệ và thời gian?
12. Retry, timeout, circuit breaker và DLQ hoạt động?
13. Không phát sinh duplicate transaction?
14. Có thể dừng và gỡ fault ngay?

**Diễn tập chuyển vùng**

15. RTO/RPO được định nghĩa và đo được?
16. Code, config, secret, IAM, network và trigger đã có ở Region dự phòng?
17. Data replication và backup restore đã được kiểm tra?
18. Có cơ chế ngăn split-brain?
19. Routing control/DNS và health check đã được thử?
20. Queue, DLQ, checkpoint và event replay có runbook?
21. Business transaction test đạt sau failover?
22. Có kế hoạch failback và reconciliation?

**Sau thí nghiệm**

23. Hệ thống trở về steady state?
24. Metric và dữ liệu được đối soát?
25. RTO/RPO thực tế có đạt mục tiêu?
26. Action item có owner và deadline?
27. Đã lên lịch chạy lại sau khi sửa lỗi?

## Tài liệu tham khảo

- [AWS Fault Injection Service: Experiment templates](https://docs.aws.amazon.com/fis/latest/userguide/experiment-templates.html)
- [AWS Fault Injection Service: Stop conditions](https://docs.aws.amazon.com/fis/latest/userguide/stop-conditions.html)
- [AWS Fault Injection Service: Safety levers](https://docs.aws.amazon.com/fis/latest/userguide/safety-lever.html)
- [AWS FIS: Lambda function actions](https://docs.aws.amazon.com/fis/latest/userguide/use-lambda-actions.html)
- [AWS Well-Architected: Disaster recovery options](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html)
- [Amazon Route 53: DNS failover best practices](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/best-practices-dns.html)
- [Amazon Route 53: Failover behavior and cascading failures](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-problems.html)
- [Amazon Application Recovery Controller: Routing controls](https://docs.aws.amazon.com/r53recovery/latest/dg/routing-control.about.html)
- [Azure Chaos Studio: Security and permissions](https://learn.microsoft.com/en-us/azure/chaos-studio/chaos-studio-permissions-security)

## Kết luận

Chaos testing kiểm chứng khả năng chịu lỗi của function và dependency; failover drill kiểm chứng khả năng khôi phục toàn bộ workload ở vùng dự phòng. Cả hai phải dựa trên giả thuyết rõ, phạm vi có giới hạn, stop conditions và chỉ số nghiệp vụ.

Với Java serverless, hãy kiểm thử timeout, retry, idempotency, duplicate event, queue backlog, dependency outage và dữ liệu sau restore. Với DR đa Region, chuẩn bị đầy đủ code, cấu hình, identity, network, queue, dữ liệu, quota và routing. Đo RTO/RPO thực tế, kiểm tra consistency và diễn tập failback riêng. Chỉ khi hệ thống đã phục hồi nghiệp vụ đúng và dữ liệu được đối soát, bài diễn tập mới được xem là thành công.

