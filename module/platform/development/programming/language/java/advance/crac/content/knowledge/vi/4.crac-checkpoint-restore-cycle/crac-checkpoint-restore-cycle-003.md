# Xác định thời điểm checkpoint bằng tín hiệu sẵn sàng của ứng dụng

Trong CRaC (Coordinated Restore at Checkpoint), thời điểm tạo checkpoint ảnh hưởng trực tiếp tới chất lượng của ảnh được lưu. Nếu checkpoint quá sớm, ảnh có thể chứa một ứng dụng chưa khởi tạo xong, chưa nạp cấu hình, chưa kết nối được dependency hoặc chưa hoàn tất warm-up. Nếu checkpoint quá muộn, ứng dụng có thể đã nhận request, đang xử lý transaction hoặc đang chạy các tác vụ nền khó đưa về trạng thái nhất quán.

Một cách đáng tin cậy để chọn thời điểm là dùng **tín hiệu sẵn sàng của ứng dụng**. Ứng dụng tự xác định khi nào các điều kiện cần thiết đã hoàn tất, công bố trạng thái đó cho bộ điều phối, rồi bộ điều phối mới yêu cầu CRaC tạo checkpoint.

Tín hiệu sẵn sàng không tự tạo checkpoint. Nó là hợp đồng giữa ứng dụng và thành phần điều phối: ứng dụng cho biết trạng thái hiện tại đã đạt điều kiện để bắt đầu quy trình checkpoint; CRaC sau đó chạy các callback chuẩn bị tài nguyên trước khi ảnh thực sự được tạo.

## 1. Vì sao cần tín hiệu sẵn sàng?

Một tiến trình Java có thể mở cổng HTTP rất sớm trong quá trình khởi động. Điều đó chưa có nghĩa ứng dụng đã sẵn sàng phục vụ nghiệp vụ. Sau khi cổng mở, ứng dụng vẫn có thể đang:

- Nạp cấu hình và kiểm tra cấu hình.
- Khởi tạo dependency injection container và các bean.
- Kết nối database, message broker, cache hoặc dịch vụ bên ngoài.
- Nạp metadata, schema, model hoặc dữ liệu tham chiếu.
- Tạo thread pool, scheduler và connection pool.
- Chạy warm-up để nạp class, biên dịch mã nóng bằng JIT hoặc khởi tạo cache.
- Đăng ký consumer, listener và các callback nội bộ.

Nếu tạo checkpoint ngay khi process xuất hiện hoặc port bắt đầu lắng nghe, ảnh có thể được tạo trong lúc một số bước trên chưa hoàn tất. Khi restore, ứng dụng có thể tiếp tục từ một trạng thái trung gian hoặc phải chạy lại các bước chưa được thực hiện.

Ở chiều ngược lại, nếu chờ ứng dụng nhận traffic rồi mới checkpoint, ảnh có thể chứa request đang xử lý, transaction đang mở, message đang được tiêu thụ hoặc worker đang thay đổi dữ liệu. Những hoạt động này làm quá trình đưa ứng dụng về trạng thái an toàn phức tạp hơn.

Tín hiệu sẵn sàng giúp xác định một điểm chuyển tiếp có chủ đích: ứng dụng đã khởi tạo đủ thành phần, đã hoàn thành phần warm-up cần thiết và có thể bước vào quy trình chuẩn bị checkpoint.

## 2. Phân biệt các trạng thái sẵn sàng

Trong vận hành dịch vụ, các khái niệm startup, readiness và liveness có mục đích khác nhau. Không nên dùng chúng thay thế cho nhau.

| Trạng thái hoặc tín hiệu | Ý nghĩa | Dùng để quyết định checkpoint? |
|---|---|---|
| Process started | JVM đã chạy và có PID | Chưa đủ; ứng dụng có thể chưa khởi tạo |
| Port open | Server đã bind và lắng nghe trên port | Chưa đủ; dependency hoặc warm-up có thể chưa hoàn tất |
| Startup complete | Các bước khởi động chính đã kết thúc | Là một điều kiện hữu ích, nhưng chưa chứng minh mọi dependency đã sẵn sàng |
| Readiness | Ứng dụng hiện có thể nhận và xử lý traffic theo hợp đồng vận hành | Có ích, nhưng readiness phục vụ traffic không đồng nghĩa trạng thái an toàn để checkpoint |
| Liveness | Tiến trình còn hoạt động và không bị kẹt theo tiêu chí kiểm tra | Không dùng làm tín hiệu checkpoint |
| Checkpoint-ready | Các điều kiện riêng để bắt đầu quy trình checkpoint đã thỏa mãn | Đây là tín hiệu phù hợp để bộ điều phối xem xét gửi yêu cầu checkpoint |
| Quiesced | Ứng dụng đã ngừng nhận việc mới và xử lý xong công việc đang chạy | Là điều kiện gần thời điểm tạo ảnh, thường được thiết lập trong callback trước checkpoint |

### 2.1 Startup probe

Startup probe cho hệ thống điều phối biết ứng dụng đã hoàn tất giai đoạn khởi động theo tiêu chí được cấu hình hay chưa. Trong Kubernetes, probe này giúp tránh việc liveness hoặc readiness probe đánh giá ứng dụng quá sớm khi thời gian startup dài.

Startup complete là một mốc hữu ích, nhưng ứng dụng có thể còn cần kiểm tra database, nạp cache hoặc chạy warm-up sau mốc đó. Vì vậy, không nên mặc định startup probe thành công là checkpoint-ready.

### 2.2 Readiness probe

Readiness probe trả lời câu hỏi: ứng dụng có thể nhận traffic vào thời điểm hiện tại hay không? Khi readiness thất bại, nền tảng điều phối thường ngừng gửi traffic mới tới instance đó.

Readiness thường phản ánh khả năng phục vụ request, trong khi checkpoint-ready phản ánh khả năng bắt đầu quy trình tạo ảnh. Hai trạng thái có liên quan nhưng không giống nhau.

Ví dụ, một ứng dụng có thể đã hoàn tất warm-up và đủ điều kiện tạo checkpoint, nhưng chưa muốn nhận traffic vì đang tạo ảnh dùng để khởi chạy các instance khác. Trong trường hợp này, checkpoint-ready có thể là true trong khi readiness phục vụ traffic vẫn là false.

Ngược lại, một instance đang phục vụ traffic bình thường có thể có readiness là true nhưng chưa checkpoint-ready vì vẫn còn request dài, message chưa xác nhận hoặc một dependency đang trong giai đoạn thay đổi trạng thái.

### 2.3 Liveness probe

Liveness probe trả lời câu hỏi: tiến trình có còn hoạt động đúng theo tiêu chí kiểm tra hay đã rơi vào trạng thái cần khởi động lại? Một ứng dụng có thể chưa sẵn sàng phục vụ nhưng vẫn còn sống; ví dụ, nó đang chờ database khởi động.

Không nên kích hoạt checkpoint chỉ vì liveness thành công. Liveness không cho biết ứng dụng đã warm-up xong, dependency đã sẵn sàng hay công việc đang chạy đã được drain.

## 3. Xây dựng điều kiện checkpoint-ready

Ứng dụng cần định nghĩa rõ những điều kiện nào phải thỏa mãn trước khi phát tín hiệu checkpoint-ready. Một điều kiện tổng hợp thường bao gồm các nhóm sau.

### 3.1 Khởi tạo ứng dụng hoàn tất

Các bước startup bắt buộc phải hoàn thành:

- Cấu hình đã được nạp và xác thực.
- Các thành phần cốt lõi đã được tạo.
- Các bean, service và listener cần thiết đã được khởi tạo.
- Các tác vụ khởi tạo một lần đã hoàn tất.
- Không còn một bước startup bắt buộc nào đang chạy nền mà ảnh checkpoint cần chứa kết quả của nó.

Không nên chỉ dựa vào sự kiện JVM đã chạy hoặc HTTP server đã bind port. Cần chọn mốc lifecycle phản ánh trạng thái thực tế của ứng dụng.

### 3.2 Dependency thiết yếu sẵn sàng

Kiểm tra các dependency mà ứng dụng cần ngay sau restore, chẳng hạn:

- Database có thể kết nối và xác thực.
- Message broker có thể truy cập.
- Cache hoặc kho dữ liệu tham chiếu đã được nạp.
- Dịch vụ cấu hình, secrets và certificate có thể truy cập.
- Các endpoint nội bộ cần thiết phản hồi đúng.

Không phải mọi dependency tùy chọn đều phải hoạt động mới được checkpoint. Hãy phân loại dependency thành thiết yếu và không thiết yếu. Điều kiện checkpoint-ready nên phản ánh những thành phần cần thiết để ứng dụng khởi động và phục vụ đúng chức năng sau restore.

Nếu dependency chỉ tạm thời mất kết nối, ứng dụng có thể giữ checkpoint-ready ở false và thử lại theo chính sách có giới hạn. Tránh phát tín hiệu true chỉ vì một lần kiểm tra cũ từng thành công.

### 3.3 Warm-up hoàn tất

Warm-up có thể bao gồm:

- Nạp cache ban đầu.
- Tải model hoặc metadata.
- Chạy truy vấn khởi tạo.
- Khởi tạo serializer, parser, template hoặc schema.
- Chạy một số thao tác đại diện để làm nóng JIT và đường đi xử lý quan trọng.

Không nhất thiết phải chạy mọi workload có thể có trước checkpoint. Hãy chọn các bước warm-up có giá trị khi ảnh được restore: chúng phải làm giảm thời gian khởi động hoặc giúp instance sẵn sàng nhanh hơn mà không đưa dữ liệu tạm thời hay trạng thái không an toàn vào ảnh.

Một số tác vụ warm-up có thể cần chạy lại sau restore nếu phụ thuộc vào thời gian, host, địa chỉ mạng hoặc trạng thái dịch vụ từ xa. Không nên giả định mọi cache đều còn hợp lệ chỉ vì object cache được giữ trong heap.

### 3.4 CRaC resource đã đăng ký và có thể chuẩn bị

Các thành phần quản lý tài nguyên cần được khởi tạo và đăng ký lifecycle với CRaC trước khi checkpoint được yêu cầu.

Ví dụ:

- File và channel có thể được đóng trước checkpoint và mở lại sau restore.
- Connection pool có thể được dừng và tạo lại.
- Client kết nối mạng có thể reconnect sau restore.
- Scheduler và consumer có thể pause/resume theo đúng thứ tự.

Một tín hiệu checkpoint-ready có thể kiểm tra rằng các thành phần này đã đăng ký callback và có thể bước vào quy trình chuẩn bị. Tuy nhiên, việc đăng ký thành công chưa bảo đảm callback sẽ hoàn tất thành công. Lần checkpoint thực tế vẫn phải xử lý lỗi trong callback.

### 3.5 Không có công việc khởi tạo bắt buộc đang dở

Trước khi cho phép checkpoint, cần biết những tác vụ nào phải hoàn thành trước khi chụp ảnh. Ví dụ:

- Migration hoặc kiểm tra schema.
- Nạp dữ liệu nền bắt buộc.
- Tạo tài khoản hoặc cấu hình ban đầu.
- Đăng ký consumer với broker.
- Tạo tài nguyên có side effect ở dịch vụ bên ngoài.

Nếu tác vụ chưa hoàn thành, có thể chờ nó, hủy theo cách an toàn hoặc lưu trạng thái đủ để tiếp tục sau restore. Quyết định phải dựa trên semantics của tác vụ; không nên để một tác vụ một lần chạy lại ngoài ý muốn sau mỗi lần restore.

## 4. Mô hình trạng thái và thời điểm phát tín hiệu

Nên biểu diễn lifecycle bằng các trạng thái rõ ràng thay vì một boolean duy nhất. Một mô hình đơn giản có thể gồm:

| Trạng thái | Ý nghĩa |
|---|---|
| STARTING | JVM và ứng dụng đang khởi động |
| INITIALIZING | Đang khởi tạo dependency và thành phần |
| WARMING | Đang chạy warm-up |
| CHECKPOINT_READY | Đã thỏa mãn điều kiện để bộ điều phối yêu cầu checkpoint |
| QUIESCING | Đang ngừng nhận việc mới và drain công việc đang chạy |
| CHECKPOINTED | Checkpoint đã được tạo thành công |
| RESTORING | Tiến trình vừa restore và đang dựng lại tài nguyên |
| SERVING | Ứng dụng đã sẵn sàng phục vụ traffic |
| FAILED | Có lỗi khiến ứng dụng không thể tiếp tục theo lifecycle hiện tại |

Một luồng tổng quát:

~~~mermaid
stateDiagram-v2
    [*] --> STARTING
    STARTING --> INITIALIZING
    INITIALIZING --> WARMING
    WARMING --> CHECKPOINT_READY
    CHECKPOINT_READY --> QUIESCING: Controller yêu cầu checkpoint
    QUIESCING --> CHECKPOINTED: Callback chuẩn bị thành công
    QUIESCING --> FAILED: Drain hoặc đóng resource thất bại
    CHECKPOINTED --> RESTORING: Restore image
    RESTORING --> SERVING: Tạo lại resource và kiểm tra xong
    RESTORING --> FAILED: Không thể khôi phục dependency
    SERVING --> QUIESCING: Checkpoint instance đang chạy
    SERVING --> FAILED: Lỗi không thể phục hồi
~~~

Mốc CHECKPOINT_READY nên xuất hiện sau khi ứng dụng hoàn thành startup, dependency thiết yếu và warm-up. Mốc QUIESCING chỉ xuất hiện khi đã có yêu cầu checkpoint và ứng dụng bắt đầu ngừng công việc. Việc tách hai trạng thái này giúp bộ điều phối biết ứng dụng đã đủ điều kiện để bắt đầu hay đã thực sự sẵn sàng cho thời điểm tạo ảnh.

Trạng thái CHECKPOINTED chỉ được công bố sau khi checkpoint engine xác nhận thao tác thành công. Không nên đổi trạng thái sang thành công ngay khi gửi lệnh checkpoint.

## 5. Kiến trúc phối hợp giữa ứng dụng và bộ điều phối

Một thiết kế thường có ba thành phần:

1. **Ứng dụng Java:** theo dõi startup, dependency, warm-up và điều kiện checkpoint-ready.
2. **Endpoint hoặc kênh trạng thái:** công bố trạng thái cho bộ điều phối, có thể là health endpoint nội bộ, API quản trị hoặc event.
3. **Bộ điều phối checkpoint:** kiểm tra tín hiệu, áp dụng chính sách và gửi yêu cầu checkpoint qua cơ chế mà CRaC runtime cung cấp.

Luồng hoạt động:

~~~mermaid
sequenceDiagram
    participant App as Java Application
    participant Signal as Readiness Endpoint
    participant Controller as Checkpoint Controller
    participant CRaC as CRaC Runtime

    App->>App: Khởi tạo cấu hình và dependency
    App->>App: Chạy warm-up
    App->>Signal: Công bố CHECKPOINT_READY
    Controller->>Signal: Đọc trạng thái
    Signal-->>Controller: Ready + điều kiện đã thỏa mãn
    Controller->>CRaC: Gửi yêu cầu checkpoint
    CRaC->>App: beforeCheckpoint callbacks
    App->>App: Ngừng nhận việc, drain và đóng resource
    App-->>CRaC: Callback hoàn tất
    CRaC-->>Controller: Kết quả checkpoint
    Note over App,CRaC: Ảnh checkpoint được tạo khi quá trình chuẩn bị thành công
~~~

Endpoint có thể trả về thông tin trạng thái dạng JSON:

~~~json
{
  "checkpointReady": true,
  "phase": "CHECKPOINT_READY",
  "conditions": {
    "startupComplete": true,
    "dependenciesReady": true,
    "warmupComplete": true,
    "resourcesRegistered": true
  },
  "reason": null
}
~~~

Đây là ví dụ về hợp đồng trạng thái do ứng dụng định nghĩa, không phải schema bắt buộc của CRaC. Có thể bổ sung thời điểm cập nhật, phiên bản ứng dụng hoặc mã lần khởi động để bộ điều phối nhận biết dữ liệu cũ.

Endpoint quản trị nên được giới hạn quyền truy cập. Việc đọc trạng thái có thể chỉ cần quyền nội bộ, còn gửi yêu cầu checkpoint cần quyền điều khiển riêng. Không nên để một endpoint công khai cho phép bất kỳ client nào yêu cầu checkpoint.

## 6. Tích hợp với lifecycle của Java application

Tín hiệu checkpoint-ready nên được phát từ lifecycle thực tế của ứng dụng. Có thể kết hợp nhiều event và điều kiện thay vì gắn nó vào một callback duy nhất.

### 6.1 Dùng sự kiện startup

Trong Spring Boot, ApplicationReadyEvent cho biết ứng dụng đã hoàn tất giai đoạn startup của Spring và các runner đã được thực thi. Đây là mốc tốt để bắt đầu đánh giá checkpoint-ready.

Tuy nhiên, sự kiện này không tự bảo đảm cache nghiệp vụ đã warm-up xong hoặc mọi dependency từ xa đều đang hoạt động. Nếu ứng dụng có các bước khởi tạo bất đồng bộ, cần chờ chúng hoàn tất trước khi phát tín hiệu.

Ví dụ:

~~~java
@Component
public final class CheckpointReadiness {

    private final AtomicBoolean startupComplete = new AtomicBoolean();
    private final AtomicBoolean dependenciesReady = new AtomicBoolean();
    private final AtomicBoolean warmupComplete = new AtomicBoolean();

    @EventListener
    public void onApplicationReady(ApplicationReadyEvent event) {
        startupComplete.set(true);
        publishIfReady();
    }

    public void onDependenciesReady() {
        dependenciesReady.set(true);
        publishIfReady();
    }

    public void onWarmupComplete() {
        warmupComplete.set(true);
        publishIfReady();
    }

    private void publishIfReady() {
        boolean ready = startupComplete.get()
                && dependenciesReady.get()
                && warmupComplete.get();

        if (ready) {
            // Công bố CHECKPOINT_READY qua health indicator,
            // endpoint nội bộ hoặc event của ứng dụng.
        }
    }
}
~~~

Đây là ví dụ minh họa cách kết hợp các điều kiện. Trong ứng dụng thực tế, cần xử lý cả trường hợp dependency mất kết nối sau khi từng sẵn sàng, warm-up thất bại và nhiều tác vụ hoàn thành đồng thời. Một điều kiện readiness nên có khả năng chuyển lại thành false khi trạng thái nền tảng thay đổi.

### 6.2 Dùng health indicator riêng

Có thể tạo một health indicator riêng, chẳng hạn checkpoint readiness, để bộ điều phối đọc qua endpoint quản trị. Health indicator này nên phản ánh điều kiện cụ thể:

- Startup đã hoàn tất.
- Dependency thiết yếu đang hoạt động.
- Warm-up bắt buộc đã kết thúc.
- Resource lifecycle đã đăng ký.
- Không có lỗi khởi tạo chưa được xử lý.

Nếu dùng Spring Boot Actuator, có thể duy trì readiness state chuẩn cho traffic và một health group riêng cho checkpoint. Điều này tránh việc thay đổi checkpoint state vô tình làm thay đổi routing traffic theo cách không mong muốn.

### 6.3 Dùng event nội bộ

Với ứng dụng không có health endpoint, tín hiệu có thể được phát qua event bus nội bộ hoặc một interface trạng thái mà bộ điều phối cùng tiến trình truy cập. Điều quan trọng là tín hiệu phải có semantics rõ ràng và chỉ được phát sau khi tất cả điều kiện bắt buộc hoàn tất.

Không nên dùng một biến static đơn giản mà không đồng bộ nếu nhiều thread cập nhật điều kiện. Có thể dùng atomic state, lock hoặc một state machine có cơ chế chuyển trạng thái nguyên tử.

## 7. Phân biệt checkpoint trước traffic và checkpoint instance đang phục vụ

Có hai tình huống vận hành thường gặp. Chúng có cách sử dụng readiness khác nhau.

### 7.1 Tạo checkpoint sau warm-up nhưng trước khi nhận traffic

Đây là cách phù hợp khi muốn tạo ảnh nền để khởi chạy nhiều instance đã được khởi tạo sẵn.

Trình tự:

1. JVM khởi động.
2. Ứng dụng nạp cấu hình và khởi tạo dependency.
3. Warm-up hoàn tất.
4. Ứng dụng công bố CHECKPOINT_READY.
5. Bộ điều phối yêu cầu CRaC tạo checkpoint.
6. Sau khi checkpoint thành công, ảnh được dùng để restore các instance theo chiến lược triển khai.
7. Instance sau restore kiểm tra lại các dependency cần thiết và mới chuyển sang readiness phục vụ traffic.

Trong mô hình này, readiness phục vụ traffic có thể vẫn false trước checkpoint. Điều đó giúp tránh nhận request vào instance nguồn trong lúc đang tạo ảnh.

Cần lưu ý rằng ảnh checkpoint có thể được restore trong một môi trường khác. Những thông tin gắn với host, IP, DNS, credentials hoặc file bên ngoài cần được xác minh lại sau restore.

### 7.2 Tạo checkpoint từ instance đang phục vụ traffic

Nếu checkpoint một instance đã nhận request, tín hiệu readiness bình thường không đủ. Bộ điều phối cần phối hợp với ứng dụng để ngừng nhận công việc mới và đưa các hoạt động đang chạy về trạng thái an toàn.

Một trình tự điển hình:

1. Bộ điều phối chọn instance đủ điều kiện và yêu cầu bắt đầu checkpoint.
2. Ứng dụng chuyển readiness phục vụ traffic sang false.
3. Ứng dụng đóng cổng nhận công việc mới ở cấp nội bộ.
4. Chờ các request đang xử lý hoàn tất trong giới hạn thời gian.
5. Pause consumer và scheduler; hoàn tất hoặc rollback transaction theo quy tắc.
6. Các CRaC Resource callback flush và đóng tài nguyên.
7. Checkpoint engine tạo ảnh.
8. Sau restore, ứng dụng tạo lại tài nguyên và xác minh dependency.
9. Ứng dụng chỉ chuyển readiness sang true khi đã phục hồi đầy đủ.

Readiness false ở bước 2 giúp load balancer hoặc service routing ngừng gửi traffic mới, nhưng cập nhật routing có thể không tức thời. Vì vậy, ứng dụng vẫn cần một request gate nội bộ và cơ chế drain. Không nên chỉ dựa vào thời gian chờ cố định sau khi đổi readiness.

## 8. Vai trò của Resource callbacks

Tín hiệu checkpoint-ready quyết định khi nào bộ điều phối có thể bắt đầu yêu cầu checkpoint. Interface Resource của CRaC quản lý công việc cần thực hiện quanh thời điểm checkpoint và restore.

Hai callback quan trọng:

- **beforeCheckpoint(Context):** chạy trước khi checkpoint được tạo. Ứng dụng ngừng nhận việc mới, drain công việc đang chạy, flush dữ liệu và đóng tài nguyên cần tạo lại.
- **afterRestore(Context):** chạy sau khi tiến trình được khôi phục. Ứng dụng mở lại tài nguyên, kết nối lại dependency và chuẩn bị trạng thái phục vụ.

Ví dụ phác thảo:

~~~java
import java.time.Duration;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ApplicationCheckpointResource implements Resource {

    private final RequestGate requestGate;
    private final ManagedResources resources;
    private final ReadinessState readiness;

    public ApplicationCheckpointResource(
            RequestGate requestGate,
            ManagedResources resources,
            ReadinessState readiness) {
        this.requestGate = requestGate;
        this.resources = resources;
        this.readiness = readiness;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        readiness.markNotReady();
        requestGate.stopAcceptingNewWork();

        if (!requestGate.awaitDrained(Duration.ofSeconds(30))) {
            throw new IllegalStateException(
                    "Timed out while draining in-flight work");
        }

        resources.flushAndClose();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        resources.reopenAndValidate();
        requestGate.allowNewWork();
        readiness.markReady();
    }
}
~~~

Các kiểu RequestGate, ManagedResources và ReadinessState ở đây là abstraction do ứng dụng tự xây dựng, không phải class có sẵn của CRaC. Ví dụ minh họa quan hệ giữa tín hiệu readiness và callback; thứ tự đóng/mở cụ thể cần tuân theo dependency của ứng dụng.

Nếu drain hoặc đóng resource thất bại, callback nên ném exception để checkpoint bị từ chối. Không nên bỏ qua lỗi rồi cho phép tạo ảnh từ trạng thái chưa an toàn.

Trong callback afterRestore, nếu tài nguyên thiết yếu không thể mở lại, ứng dụng cần giữ readiness ở false và báo lỗi. Chỉ chuyển sang ready sau khi các dependency bắt buộc đã được xác minh.

## 9. Tránh tín hiệu cũ và race condition

Readiness là một trạng thái thay đổi theo thời gian. Bộ điều phối cần tránh dùng một tín hiệu đã cũ để yêu cầu checkpoint khi ứng dụng đã chuyển sang trạng thái khác.

### 9.1 Tín hiệu phải phản ánh trạng thái hiện tại

Giả sử ứng dụng công bố checkpoint-ready sau warm-up. Ngay sau đó, database mất kết nối hoặc một tác vụ nền bắt đầu migration. Nếu endpoint vẫn trả true, bộ điều phối có thể yêu cầu checkpoint trong lúc ứng dụng không còn đủ điều kiện.

Khi dependency thiết yếu thay đổi trạng thái, ứng dụng cần cập nhật checkpoint readiness tương ứng. Có thể công bố thêm lý do chưa sẵn sàng để bộ điều phối giải thích vì sao chưa thể checkpoint.

### 9.2 Chuyển trạng thái nguyên tử

Khi có nhiều thread hoặc nhiều controller, có thể có hai yêu cầu checkpoint đến gần như cùng lúc. Chỉ một yêu cầu nên được phép chuyển ứng dụng từ CHECKPOINT_READY sang QUIESCING.

Dùng state machine có chuyển trạng thái nguyên tử, lock hoặc cơ chế lease để bảo đảm:

- Chỉ một checkpoint request được xử lý tại một thời điểm.
- Một instance không nhận thêm request sau khi đã bắt đầu quiesce.
- Controller không dùng kết quả readiness của một lần khởi động cũ.
- Yêu cầu lặp lại không làm đóng resource hai lần theo cách gây lỗi.

Một phản hồi trạng thái có thể chứa generation ID hoặc startup ID để controller xác nhận tín hiệu thuộc đúng instance và đúng vòng đời hiện tại.

### 9.3 Không dùng sleep cố định thay cho tín hiệu

Một cách đơn giản là chờ một khoảng thời gian sau khi process khởi động rồi gửi checkpoint command. Cách này dễ sai vì thời gian startup thay đổi theo tải, tốc độ host, tình trạng dependency và cache.

Nếu startup mất 20 giây ở máy này nhưng 90 giây ở máy khác, một sleep cố định có thể checkpoint quá sớm hoặc làm lãng phí thời gian. Hãy để ứng dụng phát tín hiệu khi các điều kiện thật sự hoàn tất; controller có thể polling với khoảng nghỉ có giới hạn hoặc nhận event.

### 9.4 Dùng timeout và trạng thái lỗi rõ ràng

Bộ điều phối không nên chờ vô hạn. Hãy đặt timeout cho:

- Startup.
- Kiểm tra dependency.
- Warm-up.
- Chờ checkpoint-ready.
- Drain request.
- Đóng resource.
- Khôi phục resource sau restore.

Khi timeout, ghi rõ điều kiện thất bại và quyết định retry, bỏ qua instance hay dừng workflow. Không chuyển sang checkpoint-ready chỉ để tránh workflow bị treo.

## 10. Thiết kế endpoint và chính sách kiểm tra

Một endpoint checkpoint readiness nên trả lời được hai câu hỏi: ứng dụng có đủ điều kiện bắt đầu checkpoint không, và nếu chưa thì đang vướng điều kiện nào?

Ví dụ phản hồi khi chưa sẵn sàng:

~~~json
{
  "checkpointReady": false,
  "phase": "WARMING",
  "conditions": {
    "startupComplete": true,
    "dependenciesReady": true,
    "warmupComplete": false,
    "resourcesRegistered": true
  },
  "reason": "initial-cache-loading"
}
~~~

Bộ điều phối có thể áp dụng các chính sách:

- Chỉ yêu cầu checkpoint khi checkpointReady là true.
- Kiểm tra trạng thái từ đúng instance, không dùng kết quả cache của instance khác.
- Yêu cầu tín hiệu ổn định trong một khoảng thời gian ngắn nếu các dependency thường xuyên chập chờn.
- Giới hạn số lần thử và thời gian chờ.
- Ghi lại lý do từ chối hoặc thất bại.
- Xác nhận checkpoint hoàn tất trước khi đánh dấu ảnh sẵn sàng sử dụng.

Nếu dùng polling, endpoint nên nhẹ, không tạo kết nối hoặc chạy warm-up mới mỗi lần được gọi. Health check chỉ nên đọc trạng thái đã được ứng dụng cập nhật.

Đối với hệ thống có nhiều instance, controller cần theo dõi trạng thái từng instance. Một instance checkpoint-ready không có nghĩa tất cả instance trong deployment đều đã sẵn sàng.

## 11. Quan sát và chẩn đoán

Để vận hành ổn định, cần ghi lại thời điểm và kết quả của từng giai đoạn.

Các log hoặc metric hữu ích:

- Thời gian từ process start tới startup complete.
- Thời gian khởi tạo dependency.
- Thời gian warm-up.
- Thời điểm checkpoint-ready được bật và tắt.
- Số request đang chạy khi bắt đầu quiesce.
- Thời gian drain và số request bị timeout.
- Thời gian flush/đóng resource.
- Kết quả checkpoint và nguyên nhân thất bại.
- Thời gian afterRestore, reconnect và kiểm tra dependency.
- Thời điểm readiness phục vụ traffic được bật lại.

Nên gắn instance ID, startup generation và checkpoint ID vào log để nối các sự kiện trước checkpoint với sự kiện sau restore. Điều này giúp phân biệt lỗi của lần khởi động mới với trạng thái được kế thừa từ ảnh cũ.

Nếu checkpoint-ready không bao giờ được bật, hãy xem điều kiện nào chưa hoàn tất. Nếu readiness chuyển true rồi false liên tục, hãy xem dependency có chập chờn hay logic health check quá nhạy. Nếu callback beforeCheckpoint thất bại, hãy kiểm tra request chưa drain, resource chưa đóng hoặc lỗi flush. Nếu afterRestore thất bại, hãy kiểm tra khả năng truy cập dependency và sự thay đổi của môi trường.

## 12. Kiểm thử thời điểm checkpoint

Không chỉ kiểm thử trường hợp khởi động thành công nhanh. Hãy kiểm thử các trạng thái biên:

1. **Dependency khởi động chậm:** ứng dụng không được phát checkpoint-ready trước khi dependency thiết yếu sẵn sàng.
2. **Warm-up thất bại:** readiness phải giữ false và cung cấp lý do.
3. **Dependency mất kết nối sau khi ready:** checkpoint-ready phải được thu hồi nếu dependency đó là điều kiện bắt buộc.
4. **Readiness thay đổi trong lúc controller polling:** controller phải đọc trạng thái mới và không dùng tín hiệu cũ.
5. **Có request dài khi checkpoint bắt đầu:** ứng dụng phải drain hoặc từ chối checkpoint theo timeout đã định.
6. **Hai yêu cầu checkpoint đồng thời:** chỉ một yêu cầu được phép đi vào QUIESCING.
7. **Callback đóng resource thất bại:** checkpoint không được báo thành công.
8. **Restore khi dependency chưa sẵn sàng:** readiness phục vụ traffic phải giữ false.
9. **Restore trên host khác:** xác minh DNS, IP, mount, certificate, credentials và file bên ngoài.
10. **Warm-up sau restore:** chỉ chạy lại những phần thực sự cần thiết và tránh lặp side effect không idempotent.

Nên kiểm thử cả hai mô hình: checkpoint sau warm-up trước traffic và checkpoint từ instance đang phục vụ. Hai mô hình có yêu cầu drain và readiness khác nhau.

## 13. Những sai lầm thường gặp

### Dùng port open làm checkpoint trigger

Server đã bind port không chứng minh ứng dụng hoàn tất startup hoặc dependency sẵn sàng. Hãy dùng tín hiệu phản ánh lifecycle và điều kiện nghiệp vụ.

### Dùng liveness thay cho readiness

Liveness chỉ cho biết process còn hoạt động theo tiêu chí kiểm tra. Nó không chứng minh ứng dụng đã sẵn sàng phục vụ hay tạo checkpoint.

### Dùng readiness phục vụ traffic làm checkpoint-ready

Readiness true có thể chỉ có nghĩa instance nhận được request. Nó không bảo đảm không có request đang chạy, transaction mở hoặc consumer đang xử lý message. Hãy có điều kiện checkpoint riêng.

### Chỉ dựa vào ApplicationReadyEvent

Sự kiện startup của framework là một mốc hữu ích, nhưng warm-up hoặc kiểm tra dependency bất đồng bộ có thể vẫn đang chạy. Cần kết hợp tất cả điều kiện bắt buộc.

### Chỉ đổi readiness false rồi checkpoint ngay

Load balancer và service routing có thể cần thời gian cập nhật. Ứng dụng vẫn cần chặn nhận công việc mới ở nội bộ và drain công việc đang chạy.

### Đánh dấu checkpoint thành công khi mới gửi lệnh

Controller phải chờ kết quả thực tế từ CRaC runtime hoặc checkpoint engine. Lệnh được gửi thành công không có nghĩa ảnh đã được tạo thành công.

### Giữ readiness true khi restore chưa hoàn tất

Object Java có thể đã được phục hồi nhưng socket, pool hoặc dependency bên ngoài chưa sẵn sàng. Chỉ công bố readiness sau khi callback và bước xác minh cần thiết hoàn tất.

### Dùng sleep cố định

Thời gian startup không ổn định giữa các môi trường. Tín hiệu theo điều kiện thực tế dễ vận hành và ít phụ thuộc cấu hình máy hơn.

## 14. Quy trình triển khai đề xuất

Khi tích hợp tín hiệu sẵn sàng vào một ứng dụng Java dùng CRaC, có thể thực hiện theo trình tự sau:

**Bước 1 — Xác định mục tiêu checkpoint.** Làm rõ ảnh được tạo sau warm-up trước traffic hay từ một instance đang phục vụ. Điều này quyết định có cần drain traffic và thay đổi readiness phục vụ hay không.

**Bước 2 — Liệt kê điều kiện checkpoint-ready.** Xác định startup, dependency, warm-up, resource registration và các tác vụ bắt buộc phải hoàn tất.

**Bước 3 — Xây dựng trạng thái lifecycle.** Tách CHECKPOINT_READY khỏi readiness phục vụ traffic, QUIESCING và CHECKPOINTED. Quy định rõ điều kiện chuyển trạng thái.

**Bước 4 — Công bố tín hiệu.** Tạo health endpoint hoặc event nội bộ để controller đọc trạng thái hiện tại và lý do chưa sẵn sàng.

**Bước 5 — Kết nối controller với CRaC.** Controller chỉ gửi yêu cầu checkpoint khi trạng thái hợp lệ, đúng instance và còn mới. Cơ chế gửi lệnh phụ thuộc CRaC JDK và checkpoint engine đang sử dụng.

**Bước 6 — Triển khai Resource callbacks.** Dừng nhận việc, drain, flush và đóng resource trong beforeCheckpoint; tạo lại resource và xác minh dependency trong afterRestore.

**Bước 7 — Xử lý lỗi và timeout.** Định nghĩa hành vi khi warm-up, drain, checkpoint hoặc restore thất bại. Không báo ready nếu điều kiện thiết yếu chưa đạt.

**Bước 8 — Kiểm thử và quan sát.** Kiểm tra trạng thái biên, đo thời gian từng giai đoạn và lưu checkpoint ID để truy vết.

Một thiết kế tốt làm cho quyết định checkpoint có thể giải thích được: bộ điều phối biết ứng dụng đã thỏa mãn điều kiện nào, vì sao thời điểm đó phù hợp và kết quả checkpoint có thành công hay không.

## Tài liệu tham khảo

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và vai trò phối hợp với ứng dụng.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): đăng ký Resource và triển khai callback trước checkpoint, sau restore.
- [CRaC — Debugging](https://crac.org/reference/debugging/): chẩn đoán lỗi trong quá trình checkpoint.
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html): các mốc lifecycle và application events.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): công bố health và trạng thái ứng dụng.
- [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): ý nghĩa và cách sử dụng các probe trong Kubernetes.

