# Đánh giá provisioned capacity và snapshot theo workload

Một function serverless có thể chạy nhanh ở phần xử lý nghiệp vụ nhưng vẫn trả lời chậm ở những invocation đầu tiên của một execution environment mới. Với Java, thời gian khởi động JVM, nạp class, khởi tạo framework, tạo client và thiết lập kết nối có thể làm tăng đáng kể latency ở đuôi phân phối. Nếu API có SLO chặt, vài lần khởi tạo chậm cũng có thể ảnh hưởng trải nghiệm người dùng dù phần lớn request vẫn nhanh.

AWS Lambda cung cấp hai cơ chế thường được cân nhắc để xử lý vấn đề này: **Provisioned Concurrency (PC)** và **Lambda SnapStart**. PC cấp trước một số execution environment đã khởi tạo và sẵn sàng nhận invocation. SnapStart chạy giai đoạn khởi tạo khi publish version, lưu snapshot của memory và disk state, rồi khôi phục execution environment từ snapshot khi cần scale.

Hai cơ chế giải quyết bài toán khác nhau. PC dành cho workload cần latency rất thấp và có thể dự đoán hoặc quản lý lượng concurrency cần sẵn sàng. SnapStart giảm chi phí khởi tạo khi scale out mà không phải duy trì trước một số lượng instance cố định. Trên AWS Lambda, SnapStart và Provisioned Concurrency không thể bật đồng thời cho cùng một function. Vì vậy, lựa chọn phải dựa trên traffic shape, SLO, khả năng tương thích của ứng dụng Java và chi phí thực tế.

## 1. Vì sao cần đánh giá capacity và snapshot?

Cold start xảy ra khi Lambda cần tạo execution environment mới trước khi chạy handler. Quá trình này có thể gồm tải code, khởi động runtime, khởi tạo JVM, nạp dependency, chạy static initializer và thiết lập tài nguyên dùng chung. Với Java framework như Spring Boot, Quarkus hoặc Micronaut, initialization có thể đáng kể so với thời gian xử lý request.

Một request thường đi qua các giai đoạn:

~~~mermaid
flowchart LR
    A["Request đến Lambda"] --> B{"Có environment sẵn sàng?"}
    B -->|"Có"| C["Invoke handler"]
    B -->|"Không"| D["Tạo environment mới"]
    D --> E["Khởi động runtime và Init"]
    E --> C
    C --> F["Trả response"]
~~~

Nếu request phải chờ bước Init, latency có thể tăng mạnh. Vấn đề đặc biệt rõ với:

- API đồng bộ hướng người dùng có SLO ở p95 hoặc p99.
- Endpoint thanh toán, đăng nhập hoặc xác nhận giao dịch.
- Workload có traffic burst đột ngột sau thời gian nhàn rỗi.
- Function Java dùng framework lớn hoặc nhiều dependency.
- Hệ thống xử lý theo batch có deadline và yêu cầu throughput ổn định.

Không phải mọi cold start đều cần xử lý bằng capacity hoặc snapshot. Nếu function chỉ chạy định kỳ, xử lý message bất đồng bộ hoặc caller đã có retry/backoff, độ trễ khởi tạo có thể không ảnh hưởng nghiệp vụ. Trước tiên hãy đo latency và xác định phần nào đến từ Init, Restore, handler, network hoặc dependency.

## 2. Ba khái niệm cần phân biệt

Trong AWS Lambda, các thuật ngữ dưới đây có mục đích khác nhau:

| Cơ chế | Chức năng | Có khởi tạo trước environment? | Chi phí bổ sung |
|---|---|---:|---|
| On-demand concurrency | Lambda tự tạo environment theo nhu cầu | Không | Request và duration theo mức dùng |
| Reserved Concurrency | Đặt giới hạn concurrency và dành capacity cho function | Không | Không tính phí riêng cho cấu hình reserved |
| Provisioned Concurrency | Cấp trước environment đã khởi tạo | Có | Tính phí theo lượng PC được cấu hình và thời gian duy trì |
| SnapStart | Chụp snapshot sau Init, khôi phục environment từ snapshot | Tạo snapshot khi publish version | Với Java managed runtime được hỗ trợ, không có khoản phí SnapStart cache/restore riêng |

Reserved Concurrency không phải là một số instance luôn nóng. Nó giúp function có phần concurrency được dành riêng và đặt giới hạn tối đa để bảo vệ dependency. Function vẫn có thể gặp cold start khi cần environment mới.

Provisioned Concurrency là số environment đã được khởi tạo trước. Nó phù hợp khi request cần được phục vụ với startup latency rất thấp. SnapStart lưu trạng thái sau khởi tạo để những environment được tạo khi scale có thể phục hồi nhanh hơn.

Không dùng các thuật ngữ này thay thế nhau trong thiết kế hoặc dashboard. Cần ghi rõ đang đo reserved concurrency, provisioned concurrency, on-demand concurrency hay số environment được restore từ snapshot.

## 3. Provisioned Concurrency hoạt động như thế nào?

Khi cấu hình Provisioned Concurrency, Lambda khởi tạo trước một số execution environment cho một published version hoặc alias. Những environment này sẵn sàng nhận request, giúp tránh phần lớn thời gian Init trên đường xử lý invocation.

Ví dụ, nếu alias live được cấu hình 40 PC, Lambda duy trì 40 environment đã khởi tạo cho alias đó. Khi request đồng thời không vượt quá capacity đã sẵn sàng, Lambda có thể xử lý bằng những environment này.

~~~mermaid
flowchart TD
    A["Published version / alias live"] --> B["Provisioned Concurrency = 40"]
    B --> C["40 initialized environments"]
    C --> D["Request concurrency <= 40"]
    D --> E["Invoke trên environment đã sẵn sàng"]
    C --> F["Request concurrency > 40"]
    F --> G["Spillover sang standard concurrency nếu còn capacity"]
    G --> H["Có thể phát sinh cold start"]
~~~

PC giảm cold start cho lượng concurrency đã provision. Nếu traffic vượt mức đó, Lambda có thể dùng standard concurrency để xử lý phần vượt, tùy reserved concurrency và account capacity. Phần spillover có thể gặp cold start.

PC được cấu hình cho version hoặc alias cụ thể, không áp dụng cho version chưa publish là $LATEST. Nếu API Gateway, event source hoặc caller vẫn invoke $LATEST thay vì alias có PC, request sẽ không dùng những environment đã provision.

Khi cấp PC, Lambda cần thời gian để khởi tạo environment. Cấu hình mới có thể ở trạng thái IN_PROGRESS; chỉ khi allocation hoàn tất mới nên chuyển traffic cần latency thấp vào alias đó. Đừng coi thao tác gửi lệnh cấu hình là bằng chứng capacity đã sẵn sàng.

## 4. Reserved Concurrency khác Provisioned Concurrency

Hai loại concurrency có thể được cấu hình cùng nhau nhưng không có cùng mục đích.

| Tiêu chí | Reserved Concurrency | Provisioned Concurrency |
|---|---|---|
| Mục tiêu | Dành capacity và giới hạn mức chạy đồng thời | Giữ sẵn environment đã khởi tạo |
| Ngăn function chiếm quá nhiều concurrency | Có | Không phải mục tiêu chính |
| Giảm cold start | Không | Có trong phần capacity được provision |
| Phạm vi cấu hình | Cấp function, bao gồm $LATEST | Version hoặc alias đã publish |
| Chi phí cấu hình riêng | Không | Có |
| Quan hệ giữa hai loại | Có thể đặt làm giới hạn | PC không được lớn hơn reserved concurrency khi cùng cấu hình |

Reserved Concurrency hữu ích khi function gọi database có connection limit thấp. Ví dụ, database chỉ chịu được 80 connection từ workload này, nhóm có thể đặt reserved concurrency để giới hạn mức scale của function. PC sau đó có thể được đặt thấp hơn hoặc bằng giới hạn đó nếu endpoint cần warm environment.

Không đặt reserved concurrency quá thấp chỉ để tiết kiệm tiền nếu nó khiến request bị throttle. Ngược lại, không tăng concurrency mà không kiểm tra connection pool, downstream rate limit và giới hạn account.

## 5. SnapStart hoạt động như thế nào?

SnapStart thay đổi thời điểm chạy Init. Thay vì chờ invocation đầu tiên của một environment mới, Lambda khởi tạo code khi publish function version, tạo snapshot của memory và disk state sau initialization, mã hóa snapshot và lưu cache.

Khi function version được invoke và scale lên, Lambda tạo environment bằng cách restore từ snapshot. Việc này có thể giảm đáng kể phần latency do JVM startup, class loading và framework initialization.

~~~mermaid
flowchart TD
    A["Deploy code và cấu hình SnapStart"] --> B["Publish function version"]
    B --> C["Lambda chạy Init"]
    C --> D["Chụp snapshot memory và disk"]
    D --> E["Mã hóa và cache snapshot"]
    E --> F["Invoke published version"]
    F --> G["Restore execution environment"]
    G --> H["After-restore hook nếu có"]
    H --> I["Invoke handler"]
~~~

SnapStart là tối ưu hóa startup theo snapshot, không phải giữ một số lượng environment cố định luôn sẵn sàng. Khi cần thêm environment, Lambda restore từ snapshot thay vì khởi tạo từ đầu.

SnapStart có thể giảm startup latency xuống dưới một giây trong điều kiện phù hợp, nhưng đây không phải cam kết latency cố định cho mọi request. Nó không thay thế việc đo p95/p99, kiểm tra restore time và tối ưu code trong handler.

## 6. So sánh PC, SnapStart và on-demand theo workload

| Workload | On-demand | SnapStart | Provisioned Concurrency |
|---|---|---|---|
| API ít traffic, SLO thoải mái | Thường đủ | Có thể giảm outlier Init | Thường lãng phí |
| API Java có framework lớn, traffic thay đổi | Có thể có cold start dài | Lựa chọn tốt để giảm Init | Dùng nếu cần startup rất thấp |
| API có peak theo giờ rõ ràng | Có thể scale chậm lúc peak | Giảm Init khi scale | Có thể schedule PC trước peak |
| API có burst bất ngờ và SLO cực chặt | Không đảm bảo latency thấp | Giảm nhưng không loại bỏ mọi cold start | Phù hợp hơn nếu capacity đủ |
| Queue consumer bất đồng bộ | Thường đủ | Hữu ích nếu Init là bottleneck | Chỉ dùng khi throughput/latency cần |
| Batch chạy theo lịch | Thường đủ | Có thể giúp khởi tạo Java nhanh | Provision quanh thời gian chạy nếu deadline rất chặt |
| Function hiếm khi được gọi | Chi phí thấp | Có thể không thấy nhiều lợi ích | Thường không phù hợp |

SnapStart thường là lựa chọn đầu tiên để thử cho Java function cần giảm cold start khi scale, nếu function tương thích. PC phù hợp khi latency SLO yêu cầu môi trường đã khởi tạo trước request và tổ chức chấp nhận chi phí duy trì capacity.

Đừng chọn PC chỉ vì một cold start đơn lẻ xuất hiện trong log. Hãy xác định tỷ lệ cold start, mức độ ảnh hưởng đến người dùng và latency percentile của toàn bộ request.

## 7. Xác định workload bằng traffic shape

Capacity cần thiết phụ thuộc vào số request đồng thời, không chỉ tổng request mỗi ngày.

Các traffic shape phổ biến:

- **Steady:** request đều trong ngày; PC có thể giữ một baseline nhỏ.
- **Predictable peak:** traffic tăng vào giờ mở cửa, đầu ngày hoặc cuối tháng; scheduled scaling có thể chuẩn bị capacity trước.
- **Bursty:** traffic tăng đột ngột do chiến dịch hoặc event; PC cố định có thể thiếu capacity, cần auto scaling và fallback.
- **Sporadic:** request xuất hiện không đều; on-demand hoặc SnapStart thường hợp lý hơn.
- **Batch window:** nhiều message được xử lý trong khoảng ngắn; cần tính concurrency theo throughput và duration, đồng thời cân nhắc queue batching.
- **Seasonal:** traffic thay đổi theo tuần, tháng hoặc mùa; cần theo dõi lịch sử và đặt lịch scale phù hợp.

Với mỗi workload, thu thập ít nhất:

1. Request per second theo từng khoảng thời gian.
2. Duration trung bình và phân phối p50/p95/p99.
3. Concurrent executions, đặc biệt là peak.
4. Tỷ lệ request đến khi không có environment sẵn sàng.
5. Init Duration hoặc Restore Duration.
6. Tỷ lệ spillover nếu đã bật PC.
7. Downstream capacity và giới hạn connection.
8. SLO/latency budget của caller.
9. Số giờ trong ngày thực sự cần latency thấp.

Một function có 100.000 request/ngày nhưng phân bố đều có thể cần ít concurrency hơn một function chỉ nhận 10.000 request trong một burst 30 giây.

## 8. Ước lượng concurrency cần thiết

Công thức gần đúng:

\[
Concurrency = RequestsPerSecond \times AverageDurationSeconds
\]

Ví dụ, API nhận trung bình 30 request/giây và thời gian xử lý trung bình là 0,4 giây:

\[
30 \times 0.4 = 12
\]

Mức concurrency trung bình ước tính là 12. Đây chưa phải capacity production vì traffic có peak, duration có outlier và concurrency tăng khi downstream chậm.

Một cách thực tế hơn:

1. Dùng metric ConcurrentExecutions để quan sát peak.
2. Phân tích theo cửa sổ 1 phút hoặc nhỏ hơn từ telemetry của ứng dụng.
3. Dùng p95/p99 concurrency nếu có dữ liệu đủ chi tiết.
4. Xác định tỷ lệ request cần PC để đáp ứng SLO.
5. Thêm buffer theo độ biến động traffic và thời gian scale.
6. Kiểm tra quota account và reserved concurrency.
7. Load test ở mức capacity đã chọn.

AWS hướng dẫn ước lượng concurrency bằng requests/second nhân duration trung bình và gợi ý thêm khoảng 10% buffer trên mức concurrency điển hình. Với production, buffer phải dựa trên biến động thực tế và SLO; 10% không phải bảo đảm đủ cho burst.

Ví dụ: workload thường đạt peak 200 concurrent executions. Mức khởi đầu có thể thử là 220 PC, sau đó load test và điều chỉnh theo spillover, latency và chi phí. Nếu p99 peak cao hơn nhiều so với 200, phải dùng số liệu peak đó để đánh giá.

## 9. Đo latency đúng cách

Không chỉ đo Duration của handler. Request end-to-end có thể gồm DNS, TLS, API Gateway, Lambda initialization/restore, handler, network call tới database và serialization response.

Nên đo:

- p50: trải nghiệm thông thường.
- p90/p95: phần lớn request chậm hơn mức bình thường.
- p99/p99.9: outlier có thể ảnh hưởng SLO.
- Init Duration: thời gian initialization trong các lần tạo environment.
- Restore Duration: thời gian khôi phục snapshot với SnapStart.
- Handler Duration: thời gian code xử lý invocation.
- Integration latency: thời gian gateway chờ backend.
- Error/throttle rate: lỗi do quá tải hoặc cấu hình sai.

Nếu p50 tốt nhưng p99 xấu, PC hoặc SnapStart có thể cải thiện tail latency. Tuy nhiên, nếu handler chủ yếu chờ database hoặc API đối tác, việc giảm Init chỉ cải thiện một phần nhỏ của tổng latency.

Hãy ghi correlation ID và release version để so sánh các lần đo giữa các phiên bản. Không trộn traffic canary, staging và production vào cùng một phân phối mà không phân biệt nguồn.

## 10. Chọn SnapStart cho Java function

SnapStart hỗ trợ Java 11 trở lên trên các managed runtime được hỗ trợ. Có thể dùng ZIP deployment hoặc container image dựa trên Lambda base image tương thích. Hãy kiểm tra danh sách runtime và Region trước khi bật.

SnapStart phù hợp khi:

- JVM và framework initialization chiếm phần đáng kể của cold start.
- Function scale lên nhiều execution environment.
- Latency outlier do Init ảnh hưởng tới SLO.
- Ứng dụng có thể xử lý đúng snapshot/restore semantics.
- Không cần Provisioned Concurrency trên cùng function.
- Không phụ thuộc vào các tính năng bị SnapStart giới hạn.

SnapStart chỉ hoạt động với published function versions và alias trỏ tới version. Không dùng $LATEST để đánh giá kết quả. Sau khi publish, chờ trạng thái version là Active và OptimizationStatus là On trước khi chuyển traffic.

## 11. Giới hạn tương thích của SnapStart

Trước khi chọn SnapStart, rà soát các ràng buộc hiện hành:

- Không thể bật đồng thời SnapStart và Provisioned Concurrency trên cùng function.
- Chỉ áp dụng cho published version và alias trỏ tới version, không áp dụng $LATEST.
- Không hỗ trợ Amazon EFS và Amazon S3 Files.
- Không hỗ trợ ephemeral storage lớn hơn 512 MB.
- Chỉ một số managed runtime được hỗ trợ; Java 11 trở lên là nhóm phù hợp cho bài học này.
- Container image cần dùng base image tương thích và tuân theo hướng dẫn hooks/uniqueness.
- Snapshot không giữ nguyên mọi network connection hoặc dữ liệu tạm theo cách có thể dùng an toàn sau restore.

SnapStart có thể chạy trong VPC nếu các điều kiện mạng và dịch vụ phù hợp. Tuy nhiên, vẫn cần kiểm thử DNS, kết nối và dependency sau restore.

Danh sách hỗ trợ thay đổi theo thời gian. Trước production, kiểm tra tài liệu AWS theo Region, runtime, deployment format và các dịch vụ tích hợp thực tế.

## 12. Snapshot và tính duy nhất của trạng thái

Lambda dùng một snapshot đã khởi tạo làm trạng thái ban đầu cho nhiều execution environment. Vì vậy, dữ liệu được tạo một lần trong initialization có thể bị sao chép sang nhiều environment sau restore.

Các giá trị không nên tạo rồi lưu vào snapshot nếu chúng phải duy nhất cho từng environment hoặc từng invocation:

- UUID hoặc execution environment ID.
- Seed hoặc trạng thái nội bộ của pseudo-random generator.
- Secret ngắn hạn hoặc token có expiry.
- Timestamp được tính ở thời điểm initialization.
- Nonce, challenge hoặc giá trị chống replay.
- Bộ đếm trong memory được giả định là duy nhất toàn hệ thống.

Hãy tạo giá trị duy nhất trong handler hoặc trong after-restore hook. Với randomness bảo mật, dùng CSPRNG như java.security.SecureRandom và kiểm tra phiên bản thư viện cryptography theo hướng dẫn SnapStart. Không dùng một seed cố định hoặc giá trị random đã được tạo trước snapshot để sinh secret cho nhiều environment.

Ví dụ tạo ID theo invocation:

~~~java
import java.util.UUID;

public class OrderHandler {
    public String handleRequest(OrderEvent event, Context context) {
        String invocationId = UUID.randomUUID().toString();

        return process(event, invocationId);
    }

    private String process(OrderEvent event, String invocationId) {
        // Gắn ID vào log hoặc trace của invocation.
        return "accepted";
    }
}
~~~

Nếu cần ID riêng cho execution environment, tạo ID sau restore và lưu ở state của environment. Đừng dùng hostname làm ID duy nhất vì nhiều environment restore từ cùng snapshot có thể quan sát cùng hostname.

## 13. Kết nối mạng và dữ liệu tạm sau restore

Network connection được mở trong initialization không được bảo đảm còn hợp lệ sau khi restore snapshot. Socket có thể đã hết hạn, peer đã đóng kết nối hoặc trạng thái connection không còn đồng bộ.

Với Java function:

- Kiểm tra connection pool trước khi dùng.
- Re-establish kết nối trong handler hoặc after-restore hook.
- Dùng timeout và retry có giới hạn.
- Không bind connection vào fixed source port.
- Không cache DNS trong JVM theo cách gây stale address sau restore.
- Làm mới credential và dữ liệu tạm trước khi dùng.
- Kiểm tra database pool, HTTP client và TLS session trong load test.

AWS SDK thường có cơ chế phục hồi connection/credential riêng, nhưng vẫn cần kiểm thử với phiên bản SDK và dependency thực tế. Đừng mặc định mọi thư viện HTTP hoặc JDBC đều tự khôi phục connection sau snapshot.

Nếu dùng Java DNS cache với SnapStart, kiểm tra khuyến nghị của AWS cho runtime version. Một số cấu hình JVM DNS cache có thể làm phát sinh connection timeout sau restore. Chỉ thay đổi TTL sau khi hiểu cache của JVM và DNS cache do Lambda quản lý.

## 14. Dùng CRaC runtime hooks trong Java

AWS Lambda hỗ trợ runtime hooks theo mô hình Coordinated Restore at Checkpoint (CRaC). Hai callback quan trọng:

- beforeCheckpoint(): chạy trước khi Lambda tạo snapshot.
- afterRestore(): chạy sau khi Lambda khôi phục execution environment từ snapshot.

Dùng beforeCheckpoint để đóng tài nguyên không nên được snapshot hoặc chuẩn bị trạng thái ổn định. Dùng afterRestore để tạo lại connection, refresh dữ liệu tạm hoặc tái tạo giá trị cần duy nhất.

Ví dụ minh họa:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RestoreLifecycle implements Resource {
    private static final RestoreLifecycle INSTANCE =
            new RestoreLifecycle();

    private volatile String environmentId;

    private RestoreLifecycle() {
        Core.getGlobalContext().register(this);
    }

    public static void initialize() {
        // Gọi trong static initialization để đăng ký resource.
        // INSTANCE giữ strong reference để hook không bị garbage collect.
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Đóng hoặc làm sạch resource không an toàn khi snapshot.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        environmentId = java.util.UUID.randomUUID().toString();
        // Khởi tạo lại resource cần thiết sau restore.
    }

    public String environmentId() {
        return environmentId;
    }
}
~~~

Đây là ví dụ cấu trúc; cần thêm dependency org.crac tương thích và gọi initialize trong class được runtime nạp. CRaC Context giữ WeakReference tới Resource, vì vậy ứng dụng phải giữ strong reference để callback chắc chắn được gọi. Callback afterRestore có giới hạn thời gian hoàn tất; không thực hiện công việc kéo dài hoặc chờ dependency vô hạn trong hook.

Nếu không cần hook, xử lý lazy refresh trong handler có thể đơn giản hơn. Hãy chọn nơi phục hồi dựa trên latency budget và vòng đời của resource.

## 15. Tối ưu Java initialization trước khi snapshot

SnapStart có lợi nhất khi phần việc nặng được thực hiện trong initialization để snapshot chứa trạng thái đã chuẩn bị.

Có thể cân nhắc:

- Nạp class và dependency thường dùng.
- Khởi tạo framework container.
- Tạo client SDK có thể phục hồi an toàn.
- Parse cấu hình bất biến.
- Chuẩn bị serializer/deserializer.
- Preload metadata hoặc model nhỏ, ổn định.
- Warm-up code path an toàn để JIT biên dịch trước snapshot.

Không thực hiện side effect nghiệp vụ trong initialization. Ví dụ, không tạo đơn hàng, gửi email, trừ tiền, ghi audit event hoặc publish message trong static initializer. Lambda có thể chạy initialization khi publish version và tạo snapshot; side effect đó không phải một invocation nghiệp vụ bình thường.

Nếu dùng dummy invocation để warm up, đảm bảo request giả không làm phát sinh transaction, ghi dữ liệu hoặc gửi notification. Dùng dependency mock hoặc endpoint chỉ đọc nếu có thể.

Không preload mọi dependency chỉ vì có thể. Việc tải quá nhiều dữ liệu làm snapshot lớn hơn, tăng thời gian publish/restore và tăng memory footprint. Chỉ preload những thành phần thực sự giảm latency trên đường xử lý quan trọng.

## 16. Tối ưu Java với Provisioned Concurrency

Với PC, initialization code chạy trong lúc Lambda allocate capacity trước request. Vì vậy, có thể chuyển việc khởi tạo framework, client và dependency ra ngoài handler để invocation thực tế không phải làm lại.

Ví dụ:

~~~java
public final class PaymentHandler
        implements RequestHandler<PaymentRequest, PaymentResponse> {

    private static final PaymentService PAYMENT_SERVICE =
            PaymentService.createFromEnvironment();

    @Override
    public PaymentResponse handleRequest(
            PaymentRequest request,
            Context context) {

        return PAYMENT_SERVICE.process(request);
    }
}
~~~

Đoạn code minh họa khởi tạo service một lần trong lifecycle của environment. Service phải thread-safe nếu runtime hoặc framework cho phép xử lý đồng thời trên cùng environment; không lưu mutable request state trong static field.

PC không làm handler tự động nhanh hơn nếu phần chậm nằm ở database, network hoặc thuật toán. Nó chủ yếu loại bỏ Init khỏi invocation dùng PC. Hãy tối ưu code handler, connection pool, query, serialization và dependency như bình thường.

Nếu function hết PC và spillover sang on-demand, invocation vượt ngưỡng có thể vẫn có cold start. Vì vậy, PC phải được sizing và scaling theo workload chứ không chỉ bật một con số cố định.

## 17. Cấu hình SnapStart bằng AWS CLI

Bật SnapStart cho các version được publish:

~~~bash
aws lambda update-function-configuration \
  --function-name orders-api \
  --snap-start ApplyOn=PublishedVersions
~~~

Publish version mới:

~~~bash
aws lambda publish-version \
  --function-name orders-api
~~~

Kiểm tra trạng thái version:

~~~bash
aws lambda get-function-configuration \
  --function-name orders-api:12
~~~

Xác nhận SnapStart OptimizationStatus là On và State là Active trước khi chuyển alias production sang version mới.

Tạo hoặc cập nhật alias để caller invoke đúng version:

~~~bash
aws lambda update-alias \
  --function-name orders-api \
  --name live \
  --function-version 12
~~~

API Gateway hoặc event source phải trỏ tới alias live nếu muốn sử dụng version đã có SnapStart. Kiểm tra ARN integration sau deploy để tránh vô tình gọi $LATEST.

## 18. Cấu hình Provisioned Concurrency bằng AWS CLI

Provisioned Concurrency cần một published version hoặc alias. Ví dụ cấp 40 environment cho alias live:

~~~bash
aws lambda put-provisioned-concurrency-config \
  --function-name orders-api \
  --qualifier live \
  --provisioned-concurrent-executions 40
~~~

Kiểm tra trạng thái allocation:

~~~bash
aws lambda get-provisioned-concurrency-config \
  --function-name orders-api \
  --qualifier live
~~~

Chỉ chuyển traffic sau khi status là READY và allocated concurrency đạt mức yêu cầu. Nếu đang IN_PROGRESS, capacity chưa sẵn sàng hoàn toàn.

Khi traffic tăng theo giờ, có thể dùng Application Auto Scaling để thay đổi PC theo lịch hoặc target tracking. Cần cấu hình initial provisioned concurrency value và scalable target trước khi dựa vào auto scaling.

## 19. Auto scaling Provisioned Concurrency

Có hai cách phổ biến:

- **Scheduled scaling:** tăng PC trước giờ cao điểm và giảm sau khi traffic giảm.
- **Target tracking:** giữ utilization quanh một ngưỡng mục tiêu bằng cách tự động tăng/giảm capacity.

Ví dụ đăng ký alias live làm scalable target:

~~~bash
aws application-autoscaling register-scalable-target \
  --service-namespace lambda \
  --resource-id function:orders-api:live \
  --scalable-dimension lambda:function:ProvisionedConcurrency \
  --min-capacity 5 \
  --max-capacity 120
~~~

Ví dụ target tracking giữ utilization gần 70%:

~~~bash
aws application-autoscaling put-scaling-policy \
  --service-namespace lambda \
  --resource-id function:orders-api:live \
  --scalable-dimension lambda:function:ProvisionedConcurrency \
  --policy-name orders-api-pc-utilization \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 0.7,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "LambdaProvisionedConcurrencyUtilization"
    }
  }'
~~~

Các giá trị min/max là ví dụ. Phải đặt theo account quota, downstream capacity và SLO. Target tracking cần thời gian phản ứng; với một đợt tăng traffic đã biết trước, scheduled scaling có thể chuẩn bị capacity sớm hơn.

Không scale PC lên sau khi peak đã bắt đầu rồi kỳ vọng mọi request đều được hưởng capacity mới. Allocation cần thời gian; hãy đặt schedule trước giờ tăng tải và theo dõi trạng thái READY.

## 20. Định tuyến caller tới đúng version hoặc alias

Một trong các nguyên nhân thường gặp khiến bật PC nhưng vẫn thấy cold start là caller không invoke alias đã được provision.

Kiểm tra:

- API Gateway integration URI.
- Lambda Function URL hoặc resource policy.
- Event source mapping.
- EventBridge target ARN.
- Step Functions task resource.
- SDK invoke target.
- Alias routing configuration.

Ví dụ caller cần invoke alias ARN:

~~~text
arn:aws:lambda:ap-southeast-1:123456789012:function:orders-api:live
~~~

Nếu caller invoke function ARN không qualifier hoặc $LATEST, request có thể chạy trên on-demand environment. Trong CloudWatch, đối chiếu metric của alias/version với metric function tổng thể.

Với SnapStart, cũng phải invoke published version hoặc alias trỏ tới version đó. Snapshot không áp dụng cho unpublished version.

## 21. Chi phí của Provisioned Concurrency

PC tạo thêm một chiều tính phí: số concurrency được cấu hình nhân với thời gian duy trì và mức memory của function. Khi function được invoke, request và duration vẫn được tính theo pricing model tương ứng. Initialization code trong quá trình allocate hoặc recycle environment cũng được tính phí, kể cả khi một environment chưa xử lý request nào.

Một baseline PC được duy trì 24/7 có thể tốn tiền ngay cả khi không có request. Nếu API chỉ cần latency thấp trong giờ làm việc, scheduled scaling hoặc giảm PC ngoài peak có thể tiết kiệm đáng kể.

Khi ước tính chi phí, tính:

- Mức PC tối thiểu duy trì.
- Số giờ mỗi ngày giữ PC.
- Peak PC trong các khoảng tăng tải.
- Memory allocation.
- Request count và duration.
- Initialization khi allocate/recycle.
- Chi phí downstream như database connection hoặc cache.
- Chi phí vận hành và rủi ro spillover.

Đừng so PC chỉ với Lambda on-demand theo số request. PC mua sự sẵn sàng của environment, nên phần chi phí capacity được tính ngay cả khi environment rảnh.

## 22. Chi phí của SnapStart cho Java

Theo pricing hiện hành của AWS, SnapStart không có khoản phí cache và restore riêng cho các Java managed runtime được hỗ trợ. Request và execution duration của Lambda vẫn được tính bình thường; thời gian code initialization và runtime hook cần được đưa vào đánh giá duration/billing theo quy tắc dịch vụ.

Với runtime SnapStart khác, pricing có thể bao gồm cache snapshot theo memory và thời gian version active, cùng phí restore mỗi lần khôi phục environment. Vì vậy, không áp dụng kết luận pricing của Java managed runtime cho Python, .NET hoặc custom container mà chưa kiểm tra bảng giá hiện hành.

Với Java, vẫn cần dọn các published version không còn dùng. SnapStart tạo snapshot theo version và snapshot không cần thiết làm tăng inventory cần quản lý. Java snapshot có thể chuyển sang Inactive sau 14 ngày không có invocation; lần gọi sau đó có thể nhận SnapStartNotReadyException trong khi Lambda tái tạo snapshot.

Chi phí thực tế còn phụ thuộc memory, số version được giữ, tần suất deploy và invocation. Hãy kiểm tra AWS Pricing Calculator và Cost Explorer theo Region trước khi quyết định production.

## 23. Đánh giá chi phí theo traffic shape

Ví dụ định tính:

| Workload | PC 24/7 | PC theo lịch | SnapStart Java | On-demand |
|---|---|---|---|---|
| API ổn định cả ngày | Có thể hợp lý nếu SLO rất chặt | Ít lợi ích | Có thể giảm Init | Có thể đủ nếu SLO rộng |
| API chỉ bận 8 giờ/ngày | Dễ trả phí capacity lúc rảnh | Thường hợp lý hơn | Có thể phù hợp | Rẻ nhưng có outlier |
| API burst khó dự đoán | Có thể thiếu nếu sizing thấp | Không theo kịp burst bất ngờ | Hữu ích khi scale out | Có thể có cold start |
| Job mỗi đêm | Thường không hợp lý | Chỉ provision quanh cửa sổ nếu cần | Có thể giảm startup | Thường đủ |
| Function hiếm khi chạy | Không hợp lý | Không hợp lý | Ít lợi ích nếu ít scale | Thường phù hợp |

Cần tính tổng chi phí trong cùng một cửa sổ traffic và so với mục tiêu latency. Nếu PC giảm p99 nhưng chi phí capacity vượt business value, SnapStart hoặc tối ưu code có thể là lựa chọn tốt hơn.

Đừng dùng số liệu trung bình cả tháng để sizing. Hãy tách giờ cao điểm, ngày cao điểm và sự kiện bất thường để hiểu phần nào cần capacity sẵn sàng.

## 24. Metrics cần theo dõi cho Provisioned Concurrency

Các metric CloudWatch quan trọng:

| Metric | Ý nghĩa | Cách sử dụng |
|---|---|---|
| ConcurrentExecutions | Số invocation đang chạy đồng thời | Xác định peak concurrency |
| ProvisionedConcurrentExecutions | Số environment PC đang xử lý invocation | Xem mức dùng thực tế |
| ProvisionedConcurrencyInvocations | Số invocation dùng PC | Tỷ lệ request được PC phục vụ |
| ProvisionedConcurrencySpilloverInvocations | Invocation vượt PC và dùng standard concurrency | Phát hiện thiếu PC hoặc burst |
| ProvisionedConcurrencyUtilization | Tỷ lệ PC đang được sử dụng | Phát hiện over/under allocation |
| Throttles | Invocation bị từ chối do hết concurrency | Kiểm tra reserved/account limit |
| Duration | Thời gian handler | Tách bottleneck xử lý |
| Errors | Invocation lỗi | Theo dõi chất lượng release |

ProvisionedConcurrentExecutions là số environment PC đang bận tại một thời điểm, không phải tổng PC đã allocate. ProvisionedConcurrencyInvocations là số invocation trong khoảng thời gian. ProvisionedConcurrencySpilloverInvocations cho biết phần request phải dùng standard concurrency vì PC đã bận hết.

Nếu spillover tăng và latency xấu, có thể cần thêm PC hoặc điều chỉnh scaling. Nếu utilization luôn thấp, có thể đang provision quá nhiều. Hãy đọc metric cùng Duration, Throttles và traffic pattern.

## 25. Metrics cần theo dõi cho SnapStart

Với SnapStart, cần phân biệt Init với Restore:

- Restore Duration cho biết thời gian Lambda khôi phục snapshot và chạy after-restore hooks.
- platform.restoreStart cho biết thời điểm bắt đầu restore.
- platform.restoreRuntimeDone thể hiện restore thành công, thất bại hoặc timeout.
- platform.restoreReport chứa thông tin thời gian restore và thời gian tính phí restore theo runtime.
- X-Ray Restore subsegment có thể giúp phân tích restore latency.
- Function Duration, Errors và Throttles vẫn cần theo dõi như bình thường.

SnapStart không tạo Initialization subsegment như cold start truyền thống; trace có Restore subsegment. Vì vậy, dashboard phải phân biệt hai pha để không kết luận nhầm rằng function không còn startup latency.

Đối chiếu p99 end-to-end với Restore Duration. Nếu restore nhanh nhưng handler chậm, tối ưu database/query hoặc code nghiệp vụ. Nếu restore chậm do hook hoặc snapshot lớn, tối ưu initialization và dữ liệu snapshot.

## 26. Quy trình benchmark và thử nghiệm có kiểm soát

Đừng chọn PC hoặc SnapStart chỉ dựa trên ví dụ benchmark của người khác. Hãy chạy thử trên chính function, framework, memory, Region, dependency và traffic shape của mình.

Một kế hoạch thử nghiệm:

1. Chọn một function đại diện và cố định phiên bản code.
2. Đo baseline on-demand với cùng memory và cấu hình.
3. Bật SnapStart, publish version mới và chờ snapshot Active.
4. Đo startup latency, p95/p99 và throughput khi scale out.
5. Tắt SnapStart ở một version thử nghiệm khác nếu cần so sánh công bằng.
6. Bật PC trên version/alias khác và cấp capacity theo peak dự kiến.
7. Đo latency trong PC, spillover và chi phí capacity.
8. Tạo burst ở mức thường gặp và mức cực đại.
9. Thử traffic sau idle period.
10. Thử deploy version mới, alias shift và rollback.
11. Lặp lại đủ lần để giảm ảnh hưởng nhiễu.
12. So sánh chi phí trên cùng số request và cùng SLO.

Cố định payload, dependency, memory, architecture và số request đồng thời giữa các phương án. Không so một bản build có cache nóng với một bản build vừa deploy rồi kết luận cơ chế nào tốt hơn.

## 27. Kịch bản test cần có

| Kịch bản | Điều cần xác minh |
|---|---|
| First invocation sau publish | SnapStart version đã Active và restore hoạt động |
| Scale từ 1 lên peak | Restore/PC allocation có theo kịp traffic không |
| Burst vượt PC | Spillover, latency và throttle |
| Traffic thấp kéo dài | Chi phí idle PC và trạng thái snapshot |
| Java framework initialization nặng | SnapStart có giảm p99 thực tế không |
| Dependency chậm | Startup optimization có che được bottleneck khác không |
| Connection sau restore | JDBC/HTTP client có reconnect an toàn không |
| Randomness/unique ID | Không trùng trạng thái từ snapshot |
| Credential rotation | Token/credential cũ không bị dùng sau restore |
| Deploy version mới | Alias trỏ đúng version có PC hoặc SnapStart |
| Rollback | Phiên bản cũ vẫn có cấu hình và snapshot/capacity phù hợp |
| Downstream saturation | Reserved concurrency và connection pool bảo vệ dependency |

Đối với function xử lý payment hoặc tạo order, dùng sandbox/test account và dữ liệu idempotent. Không chạy load test gây side effect lên production data.

## 28. Triển khai version và alias an toàn

PC và SnapStart gắn với version/alias. Mỗi lần publish version mới, cần xác minh cấu hình startup optimization cho version đó.

Một release flow có thể là:

~~~mermaid
flowchart TD
    A["Build và test artifact"] --> B["Update $LATEST"]
    B --> C["Enable SnapStart hoặc cấu hình PC"]
    C --> D["Publish version mới"]
    D --> E["Wait until Active / PC READY"]
    E --> F["Smoke test version"]
    F --> G["Shift alias live"]
    G --> H["Monitor p95/p99, errors, spillover"]
    H --> I{"Release ổn định?"}
    I -->|"Có"| J["Giữ version"]
    I -->|"Không"| K["Đưa alias về version cũ"]
~~~

Với PC, cần cấp capacity cho version hoặc alias mới trước khi chuyển traffic nếu muốn tránh cold start trong thời điểm release. Với SnapStart, chờ snapshot hoàn tất và trạng thái Active trước khi alias nhận traffic.

Giữ version cũ đủ lâu để rollback, nhưng có quy trình dọn version không còn sử dụng. Nếu SnapStart Java version không được invoke trong 14 ngày, snapshot có thể bị xóa và version chuyển Inactive; khi quay lại cần xử lý trạng thái tái tạo snapshot.

## 29. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Bật PC nhưng vẫn có cold start | Caller invoke $LATEST hoặc alias sai | Kiểm tra integration ARN và qualifier |
| PC ở IN_PROGRESS lâu | Allocation chưa hoàn tất hoặc quota/capacity | Kiểm tra GetProvisionedConcurrencyConfig và account quota |
| Spillover tăng | Peak concurrency vượt PC | Đối chiếu utilization và ConcurrentExecutions |
| Throttles tăng | Reserved/account concurrency hoặc downstream limit | Kiểm tra concurrency limit và dependency |
| SnapStart không hoạt động | Version chưa publish hoặc chưa Active | Kiểm tra OptimizationStatus và State |
| SnapStart restore lỗi | Hook timeout hoặc state không tương thích | Kiểm tra restoreReport và application logs |
| ID bị trùng sau restore | Giá trị unique được tạo trước snapshot | Sinh lại trong handler/afterRestore |
| Connection timeout sau restore | Socket cũ hoặc DNS cache không phù hợp | Reconnect và kiểm tra client/DNS behavior |
| Latency không cải thiện | Handler/dependency chiếm phần lớn thời gian | Trace end-to-end và phân tích breakdown |
| Chi phí PC cao dù traffic thấp | Provisioned capacity giữ liên tục | Schedule scale hoặc giảm min capacity |
| Snapshot Java không sẵn sàng sau idle | Version không được invoke trong 14 ngày | Chờ version Active sau khi Lambda tạo lại snapshot |

Khi PC đã hết, Lambda có thể xử lý phần vượt bằng standard concurrency; vì vậy không phải mọi spillover đều bị throttle. Tuy nhiên, request spillover có thể trải qua cold start. Hãy phân biệt latency xấu với lỗi throttling.

## 30. Framework Java và lựa chọn runtime optimization

Các framework Java có startup profile khác nhau. Spring Boot thường có nhiều auto-configuration và class loading; Quarkus và Micronaut tập trung giảm startup/memory qua compile-time processing, nhưng kết quả phụ thuộc ứng dụng.

Một số hướng tối ưu:

- Chỉ đưa dependency cần thiết vào package.
- Loại bỏ auto-configuration không dùng.
- Dùng client và serializer có thể tái sử dụng.
- Giảm reflection và scanning không cần thiết.
- Đo memory và CPU sau khi thay đổi memory size.
- Tối ưu connection pool theo concurrency.
- Tránh khởi tạo object nặng trong mỗi handler invocation.
- Dùng SnapStart hoặc PC sau khi đã hiểu initialization profile.
- Đo JIT warm-up và code path thường dùng.

Với Java 25 và các runtime mới, AWS có thể áp dụng mặc định JVM khác khi dùng SnapStart hoặc PC. Kiểm tra tài liệu runtime cụ thể trước khi tự đặt JAVA_TOOL_OPTIONS. Không sao chép cấu hình JVM cũ sang runtime mới mà không benchmark.

## 31. Cây quyết định chọn phương án

~~~mermaid
flowchart TD
    A["Có vấn đề cold start ảnh hưởng SLO?"] -->|"Không"| B["Dùng on-demand; tối ưu code khi cần"]
    A -->|"Có"| C["Java managed runtime có hỗ trợ SnapStart?"]
    C -->|"Không"| D["Tối ưu init hoặc xem PC"]
    C -->|"Có"| E["SnapStart có đáp ứng p95/p99?"]
    E -->|"Có"| F["Dùng SnapStart"]
    E -->|"Không"| G["Có cần startup rất thấp và latency nghiêm ngặt?"]
    G -->|"Có"| H["Dùng Provisioned Concurrency"]
    G -->|"Không"| I["Tối ưu init, dependency và handler"]
    H --> J["Sizing theo peak concurrency và autoscaling"]
~~~

Một nguyên tắc hữu ích:

- Chọn on-demand nếu cold start không ảnh hưởng SLO.
- Thử SnapStart nếu Java initialization là nguồn latency lớn và workload scale lên nhiều environment.
- Chọn PC nếu cần environment đã khởi tạo trước với latency rất thấp.
- Dùng reserved concurrency để bảo vệ dependency hoặc giới hạn scale, không coi nó là giải pháp warm start.
- Nếu PC đắt, thử scheduled scaling hoặc chỉ provision cho API/route quan trọng nhất.
- Nếu cả SnapStart và PC đều không đáp ứng, xem lại kiến trúc, runtime, framework, downstream và SLO.

## 32. Checklist đánh giá trước production

**Workload và SLO**

1. Đã đo p50, p95, p99 và p99.9 end-to-end?
2. Đã phân biệt Init, Restore, handler và downstream latency?
3. Đã có traffic profile steady, peak, burst và idle?
4. Đã tính concurrency từ request rate và duration?
5. Đã xác định phần request cần latency rất thấp?

**Provisioned Concurrency**

6. PC được gắn vào version hoặc alias đã publish?
7. Caller invoke đúng alias/version?
8. Capacity đã READY trước khi chuyển traffic?
9. Mức PC dựa trên peak và buffer thực tế?
10. Reserved concurrency và account quota đủ?
11. Downstream database/HTTP dependency chịu được concurrency?
12. Có metric spillover, utilization và throttle?
13. Có scheduled scaling hoặc target tracking khi cần?
14. Chi phí capacity lúc idle đã được tính?

**SnapStart và Java**

15. Runtime Java nằm trong danh sách được hỗ trợ?
16. SnapStart được bật cho published versions?
17. Version đã Active và OptimizationStatus On?
18. Có tạo unique ID, secret hoặc RNG state trong initialization không?
19. Network connection có được reconnect sau restore?
20. Temporary credential và cache có được refresh?
21. CRaC hook có strong reference và hoàn tất trong giới hạn?
22. Có test snapshot/restore với dependency thực tế?
23. Có dọn published versions không còn dùng?
24. Có kiểm tra trạng thái Inactive sau 14 ngày không invocation?

**Release và chi phí**

25. Có benchmark cùng điều kiện giữa on-demand, SnapStart và PC?
26. Có test burst, scale-out và idle period?
27. Có quy trình chờ snapshot Active hoặc PC READY?
28. Có rollback alias về version cũ?
29. Có dashboard latency, errors, restore/init và concurrency?
30. Có review chi phí theo traffic shape và Region?

## Tài liệu tham khảo

- [AWS Lambda: Configuring Provisioned Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html)
- [AWS Lambda: Understanding concurrency and scaling](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [AWS Lambda: Monitoring concurrency](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-concurrency.html)
- [AWS Lambda: Improving startup performance with SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html)
- [AWS Lambda: Activating and managing SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-activate.html)
- [AWS Lambda: Handling uniqueness with SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-uniqueness.html)
- [AWS Lambda: Runtime hooks for Java](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-runtime-hooks-java.html)
- [AWS Lambda: Maximize SnapStart performance](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-best-practices.html)
- [AWS Lambda Pricing](https://aws.amazon.com/lambda/pricing/)

## Kết luận

Provisioned Concurrency và SnapStart đều giúp giảm latency khởi tạo của AWS Lambda nhưng phục vụ những workload khác nhau. PC giữ sẵn một lượng execution environment đã khởi tạo, phù hợp với API có SLO nghiêm ngặt và nhu cầu concurrency có thể sizing hoặc autoscale. SnapStart tạo snapshot sau Init khi publish version, giúp scale out nhanh hơn mà không duy trì một lượng environment cố định.

Với Java, hãy bắt đầu bằng việc đo latency percentile, Init/Restore duration và concurrency theo traffic shape. Thử SnapStart khi initialization là bottleneck và kiểm tra uniqueness, random state, connection, credential cùng CRaC hooks. Chọn PC khi cần startup rất thấp và sẵn sàng trả phí capacity; cấu hình trên alias/version, chờ READY và theo dõi spillover. Reserved Concurrency vẫn hữu ích để bảo vệ dependency nhưng không làm nóng environment. Quyết định cuối cùng phải dựa trên benchmark, SLO, compatibility và tổng chi phí của workload thực tế.

