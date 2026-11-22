# Chạy batch job bằng Cloud Run Jobs

Không phải mọi workload serverless đều phục vụ HTTP request. Nhiều công việc cần đọc một tập dữ liệu lớn, xử lý hàng loạt hóa đơn, tạo báo cáo, đồng bộ dữ liệu hoặc chạy tác vụ bảo trì theo lịch. Các công việc này thường chạy đến khi hoàn tất rồi dừng, thay vì giữ một HTTP server luôn sẵn sàng.

Google Cloud Run Jobs cho phép chạy container để thực hiện một công việc rồi kết thúc. Một lần chạy (execution) có thể gồm một hoặc nhiều task. Mỗi task chạy container của image đã triển khai, nhận input qua biến môi trường hoặc đối số, thực hiện phần việc được giao và báo thành công bằng exit code. Cloud Run quản lý việc khởi chạy, phân phối task, retry và trạng thái execution.

Với Java, có thể đóng gói chương trình batch thành JAR trong container image. Ứng dụng không cần mở HTTP port; nó chạy logic trong hàm main, xử lý dữ liệu và kết thúc. Bài học này trình bày cách thiết kế task, chia batch, kiểm soát song song, phục hồi khi lỗi và vận hành Cloud Run Jobs an toàn.

## 1. Cloud Run Jobs khác Cloud Run services như thế nào?

Cloud Run có hai mô hình thực thi thường gặp:

| Tiêu chí | Cloud Run services | Cloud Run Jobs |
|---|---|---|
| Mục tiêu | Phục vụ HTTP request hoặc gRPC request | Chạy công việc đến khi hoàn tất |
| Vòng đời container | Container phục vụ request và có thể được giữ ấm để nhận request sau | Container thực hiện task rồi kết thúc |
| Cổng HTTP | Ứng dụng thường phải lắng nghe cổng được cấu hình | Không cần mở cổng HTTP |
| Cách bắt đầu | Request đến service | Người dùng, API, scheduler hoặc workflow tạo execution |
| Đầu ra | HTTP response hoặc stream | Exit code, trạng thái task, log và dữ liệu lưu ở hệ thống bên ngoài |
| Phù hợp | API, webhook, web backend | Batch, migration, báo cáo, đồng bộ và xử lý dữ liệu theo lô |

Một Cloud Run Job không phải một HTTP service chỉ chạy lâu hơn. Nó được thiết kế cho process chạy đến khi hoàn thành. Container cần kết thúc với exit code 0 khi task thành công; exit code khác 0 hoặc task timeout có thể khiến Cloud Run đánh dấu task thất bại và thử lại theo cấu hình.

Không cần viết vòng lặp chờ request hoặc chạy web server trong container của job. Chương trình Java có thể bắt đầu từ main, đọc cấu hình, xử lý batch, lưu kết quả rồi thoát.

### 1.1. Khi nào nên dùng Cloud Run Jobs?

Cloud Run Jobs phù hợp với các công việc như:

- Tạo báo cáo cuối ngày hoặc cuối tháng.
- Đọc file CSV/JSON từ Cloud Storage và xử lý từng bản ghi.
- Đồng bộ dữ liệu giữa hai hệ thống.
- Chạy migration hoặc tác vụ bảo trì database.
- Tính toán lại dữ liệu lịch sử.
- Xử lý batch lớn theo nhiều shard.
- Gửi thông báo theo danh sách đã được chuẩn bị.
- Chạy một tác vụ vận hành theo yêu cầu.

Nếu công việc cần phản hồi ngay cho từng HTTP request, Cloud Run service phù hợp hơn. Nếu công việc gồm nhiều bước phụ thuộc, có nhánh, retry theo từng bước hoặc cần phê duyệt, có thể dùng Workflows để điều phối Cloud Run Jobs và các dịch vụ khác.

## 2. Kiến trúc một batch job

Một execution có thể chạy một task duy nhất hoặc nhiều task. Khi có nhiều task, Cloud Run phân phối task theo số lượng được cấu hình và giới hạn số task chạy đồng thời bằng parallelism.

~~~mermaid
flowchart TD
    T["Cloud Scheduler / Workflows / API"] --> E["Tạo Cloud Run Job execution"]
    E --> P["Phân phối tasks"]
    P --> A["Task 0: shard 0"]
    P --> B["Task 1: shard 1"]
    P --> C["Task N: shard N"]
    A --> D["Đọc dữ liệu và xử lý"]
    B --> D
    C --> D
    D --> S["Database / Cloud Storage"]
    D --> L["Cloud Logging và trạng thái task"]
    S --> R["Execution hoàn tất khi các task kết thúc"]
~~~

Các thành phần có trách nhiệm riêng:

- **Job definition:** cấu hình image, tài nguyên, số task, parallelism, timeout, retry, biến môi trường và service account.
- **Execution:** một lần chạy cụ thể của job với cấu hình và input của lần chạy đó.
- **Task:** một đơn vị thực thi trong execution. Mỗi task có chỉ số riêng và có thể được retry.
- **Container image:** chứa Java runtime, ứng dụng và dependency.
- **Kho dữ liệu:** lưu input, checkpoint, kết quả và trạng thái nghiệp vụ.
- **Cloud Scheduler hoặc Workflows:** khởi chạy job theo lịch hoặc như một bước trong quy trình lớn.

Cloud Run Jobs quản lý vòng đời compute. Ứng dụng vẫn phải quản lý tính đúng đắn của dữ liệu, tính idempotent và cách phục hồi khi một task chỉ xử lý xong một phần.

## 3. Một execution, nhiều task và parallelism

Khi tạo job, có thể cấu hình:

- **Task count:** tổng số task cần hoàn thành trong một execution.
- **Parallelism:** số task tối đa được chạy đồng thời.
- **Task timeout:** thời gian tối đa cho một task.
- **Max retries:** số lần Cloud Run có thể thử lại một task thất bại.
- **CPU và memory:** tài nguyên cấp cho mỗi task.
- **Environment variables và arguments:** cấu hình đầu vào cho container.
- **Execution service account:** danh tính IAM mà task sử dụng khi gọi Google Cloud APIs.

Ví dụ, job có 40 task và parallelism bằng 8. Cloud Run có thể chạy tối đa 8 task đồng thời; khi một task hoàn thành hoặc được giải phóng, task khác có thể được bắt đầu. Số task không đồng nghĩa số container chạy đồng thời. Parallelism điều khiển mức đồng thời của execution.

Không nên đặt parallelism bằng task count một cách mặc định. Nếu mỗi task mở nhiều database connection hoặc gọi API bên ngoài, chạy tất cả cùng lúc có thể làm quá tải dependency. Hãy bắt đầu với mức thấp, đo throughput và tăng dần theo giới hạn thực tế.

### 3.1. Chọn cách chia dữ liệu

Có hai cách thường gặp:

- **Một task xử lý toàn bộ batch:** đơn giản, phù hợp khi dữ liệu vừa phải hoặc không cần chia song song.
- **Nhiều task xử lý các shard:** mỗi task nhận một phần dữ liệu độc lập, giúp tăng throughput và phục hồi từng phần.

Ví dụ, một file manifest chứa 100.000 record có thể được chia thành 20 shard. Mỗi task xử lý một shard. Task cần biết shard nào thuộc về mình và có cách xác định record đã hoàn tất hay chưa.

Không chia dữ liệu bằng cách để mọi task cùng đọc toàn bộ danh sách rồi tự lọc nếu danh sách lớn. Cách đó nhân số lần đọc và tăng chi phí. Có thể lưu shard ID trong manifest, dùng range partition hoặc truy vấn theo khóa phân vùng.

## 4. Biến môi trường dành cho task

Cloud Run Jobs cung cấp các biến môi trường để container biết vị trí task trong execution. Những biến thường dùng gồm:

| Biến | Ý nghĩa |
|---|---|
| CLOUD_RUN_TASK_INDEX | Chỉ số task, bắt đầu từ 0 |
| CLOUD_RUN_TASK_COUNT | Tổng số task trong execution |
| CLOUD_RUN_TASK_ATTEMPT | Số lần thử của task hiện tại |
| CLOUD_RUN_TASK_EXECUTION | Tên execution chứa task |

Các biến này hữu ích để chia dữ liệu và ghi log. Không dùng task attempt làm idempotency key vì giá trị thay đổi khi retry. Khóa nghiệp vụ phải ổn định qua các lần thử.

Ví dụ, task index 3 trong execution có 10 task có thể xử lý shard số 3. Nếu dùng phép chia theo hash, có thể xác định shard bằng chỉ số modulo số task. Tuy nhiên, khi số task thay đổi giữa hai execution, mapping record sang shard cũng có thể thay đổi. Hãy dùng khóa record để bảo vệ idempotency ở cấp nghiệp vụ, không chỉ dựa trên shard.

## 5. Viết chương trình Java chạy trong Cloud Run Job

Một chương trình Java cho Cloud Run Jobs thường có entry point là main. Nó đọc biến môi trường, khởi tạo client, xử lý phần việc được giao và kết thúc.

Ví dụ dưới đây minh họa cấu trúc của một worker chia dữ liệu theo task index. Các kiểu BatchRepository và WorkItem là adapter/model do ứng dụng định nghĩa.

~~~java
public final class BatchMain {

    public static void main(String[] args) throws Exception {
        int taskIndex = Integer.parseInt(
                System.getenv("CLOUD_RUN_TASK_INDEX"));
        int taskCount = Integer.parseInt(
                System.getenv("CLOUD_RUN_TASK_COUNT"));
        int attempt = Integer.parseInt(
                System.getenv("CLOUD_RUN_TASK_ATTEMPT"));

        String execution = System.getenv("CLOUD_RUN_TASK_EXECUTION");

        if (taskCount <= 0 || taskIndex < 0 || taskIndex >= taskCount) {
            throw new IllegalStateException("Invalid task coordinates");
        }

        System.out.printf(
                "Starting execution=%s task=%d/%d attempt=%d%n",
                execution, taskIndex, taskCount, attempt);

        try (BatchRepository repository = BatchRepository.connect()) {
            Iterable<WorkItem> items =
                    repository.loadShard(taskIndex, taskCount);

            for (WorkItem item : items) {
                repository.processIdempotently(item);
            }
        }

        System.out.printf(
                "Completed execution=%s task=%d%n",
                execution, taskIndex);
    }
}
~~~

Đây là ví dụ kiến trúc; trong ứng dụng thật, định nghĩa BatchRepository, WorkItem, cách kết nối và truy vấn shard theo nguồn dữ liệu. Nếu chạy local ngoài Cloud Run, có thể cho phép truyền task index/count qua cấu hình local hoặc cung cấp giá trị mặc định có kiểm soát.

Điểm quan trọng là main chỉ kết thúc bình thường khi toàn bộ phần việc của task đã hoàn thành. Nếu xử lý thất bại và cần Cloud Run retry, hãy để exception thoát ra hoặc kết thúc process với exit code khác 0. Không bắt exception rồi chỉ ghi log và tiếp tục thoát với mã 0, vì nền tảng sẽ coi task đã thành công.

### 5.1. Đóng tài nguyên

Dùng try-with-resources cho database connection, stream và client có vòng đời cần đóng. Nếu một client được tái sử dụng trong suốt process, hãy xác định rõ API close của thư viện. Khi task kết thúc, không để thread nền tiếp tục xử lý dữ liệu sau khi main đã trả về.

Không cần giữ một thread sống chỉ để chờ công việc mới. Cloud Run Jobs chạy task đến khi hoàn tất; nếu cần nhận request liên tục, hãy dùng Cloud Run service hoặc một worker consumer phù hợp.

## 6. Đóng gói Java thành container image

Cloud Run Jobs chạy container image. Một cách triển khai đơn giản là build JAR rồi đóng gói cùng Java runtime.

Ví dụ Dockerfile với Java 21:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/batch-worker.jar /app/batch-worker.jar

ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "/app/batch-worker.jar"]
~~~

Ứng dụng không cần khai báo EXPOSE hoặc lắng nghe cổng HTTP cho Cloud Run Job. Khi container bắt đầu, Java process chạy và kết thúc sau khi hoàn thành batch.

Có thể dùng Java 17 hoặc phiên bản LTS phù hợp với dự án. Hãy đảm bảo phiên bản JDK/JRE, dependency và native library tương thích với môi trường build và image đích. Dùng image base được duy trì, cập nhật bản vá bảo mật và tránh đưa compiler/build tool không cần thiết vào runtime image.

### 6.1. Build và đẩy image lên Artifact Registry

Một quy trình điển hình:

~~~bash
gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/batch-images/batch-worker:VERSION
~~~

Thay REGION, PROJECT_ID và VERSION bằng giá trị của môi trường. Repository Artifact Registry phải tồn tại và danh tính build cần quyền push image. Sau khi build, Cloud Run Job sẽ tham chiếu image theo URI đã đẩy.

Nên dùng tag bất biến hoặc image digest cho release production. Nếu ghi đè cùng một tag, job có thể chạy một image khác mà cấu hình triển khai không thể hiện rõ thay đổi. Ghi lại commit, build ID và image digest để truy vết.

## 7. Tạo và chạy Cloud Run Job

Có thể tạo job bằng Google Cloud Console, gcloud CLI, API hoặc Infrastructure as Code.

Ví dụ CLI:

~~~bash
gcloud run jobs create daily-reconciliation \
  --image=REGION-docker.pkg.dev/PROJECT_ID/batch-images/batch-worker:VERSION \
  --region=REGION \
  --tasks=20 \
  --parallelism=5 \
  --task-timeout=2h \
  --max-retries=3 \
  --cpu=2 \
  --memory=2Gi \
  --service-account=batch-worker@PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars=BATCH_MODE=reconcile
~~~

Các giá trị task count, parallelism, timeout, CPU, memory và retry chỉ là ví dụ. Hãy chọn theo thời gian xử lý, kích thước dữ liệu và khả năng của dependency. Một số giới hạn phụ thuộc region, loại CPU và quota của project; kiểm tra cấu hình dịch vụ trước khi triển khai production.

Chạy job thủ công:

~~~bash
gcloud run jobs execute daily-reconciliation \
  --region=REGION \
  --wait
~~~

Tùy chọn wait yêu cầu CLI chờ execution kết thúc trước khi trả kết quả. Với job dài, có thể tạo execution rồi theo dõi trạng thái bằng Console, CLI hoặc API.

Các lệnh hữu ích khác:

~~~bash
gcloud run jobs describe daily-reconciliation --region=REGION

gcloud run jobs executions list \
  --job=daily-reconciliation \
  --region=REGION
~~~

Nếu job đã tồn tại, dùng lệnh update hoặc triển khai lại bằng IaC để thay image và cấu hình. Không sửa thủ công nhiều môi trường mà không cập nhật nguồn cấu hình chuẩn.

## 8. Chia shard ổn định và tránh xử lý trùng

Giả sử batch có 1 triệu record. Có thể chia theo hash của record ID:

~~~java
static int shardFor(String recordId, int taskCount) {
    return Math.floorMod(recordId.hashCode(), taskCount);
}
~~~

Task chỉ xử lý record có shard ID bằng task index. Cách này đơn giản nhưng cần lưu ý: nếu task count thay đổi, cùng một record có thể chuyển sang shard khác. Với dữ liệu lớn hoặc nhiều lần chạy, tốt hơn là tạo manifest chứa shard assignment cố định cho một batch hoặc dùng khóa phân vùng ổn định.

Một record nên có trạng thái xử lý bền vững:

| Trường | Mục đích |
|---|---|
| batch_id | Định danh batch nghiệp vụ |
| item_id | Định danh record cần xử lý |
| status | PENDING, RUNNING, SUCCEEDED hoặc FAILED |
| attempt_count | Số lần xử lý |
| lease_until | Thời điểm quyền xử lý hiện tại hết hạn nếu dùng lease |
| result_ref | Tham chiếu đến kết quả |
| updated_at | Thời điểm cập nhật |

Dùng unique key như batch_id + item_id để bảo đảm một record không tạo hiệu ứng nghiệp vụ trùng khi task retry. Nếu thao tác ghi dữ liệu và đánh dấu SUCCEEDED nằm trong cùng database, hãy dùng transaction. Nếu side effect ở dịch vụ ngoài, truyền idempotency key ổn định cho dịch vụ đó nếu được hỗ trợ.

### 8.1. Task retry và execution chạy lại

Cần phân biệt:

- **Task retry:** Cloud Run thử lại một task thất bại trong cùng execution, theo max retries.
- **Job execution mới:** người vận hành, scheduler hoặc workflow khởi chạy job thêm một lần nữa.
- **Business replay:** đội vận hành yêu cầu xử lý lại một batch hoặc một nhóm record đã được chọn.

Một task retry có thể chạy lại code từ đầu. Nếu task đã xử lý xong 80% record rồi process bị timeout, lần retry cần bỏ qua record đã hoàn tất và tiếp tục phần còn lại. Không dựa vào memory hoặc file tạm của container để biết tiến độ.

Một execution mới có thể chạy lại tất cả task. Vì vậy, batch ID phải đại diện cho kỳ nghiệp vụ, ví dụ ngày báo cáo hoặc mã file đầu vào. Không tạo batch ID mới cho mỗi lần retry nếu mục tiêu là tiếp tục cùng một batch. Nếu muốn cố ý chạy lại với dữ liệu mới, tạo batch ID mới và lưu quan hệ với batch cũ.

## 9. Checkpoint và phục hồi khi task dài

Với task chạy lâu, nên chia công việc thành các đơn vị nhỏ có thể commit và tiếp tục. Sau mỗi batch nhỏ:

1. Xử lý một nhóm record.
2. Commit kết quả.
3. Ghi checkpoint hoặc trạng thái item đã hoàn tất.
4. Tiếp tục nhóm kế tiếp.

Nếu container bị timeout hoặc process bị dừng, lần retry có thể đọc checkpoint và tiếp tục. Checkpoint cần được lưu ở database hoặc Cloud Storage; file trong filesystem container không phải trạng thái bền vững cho lần chạy tiếp theo.

Không ghi checkpoint trước khi side effect đã được xác nhận. Nếu ghi checkpoint trước rồi process chết trước khi cập nhật dữ liệu, lần chạy sau có thể bỏ qua record chưa thực sự hoàn tất. Nếu ghi dữ liệu xong nhưng checkpoint chưa cập nhật, lần chạy sau có thể thực hiện lại side effect; idempotency xử lý trường hợp đó.

Với dữ liệu lớn, có thể dùng manifest theo shard và cursor theo khóa tăng dần. Tránh offset pagination trên tập dữ liệu thay đổi liên tục vì record có thể bị bỏ sót hoặc xử lý hai lần khi dữ liệu được thêm/xóa giữa các lần đọc.

## 10. Xử lý lỗi và cấu hình retry

Cloud Run Jobs có thể thử lại task thất bại theo số lần retry được cấu hình. Task có thể thất bại do:

- Container process thoát với exit code khác 0.
- Task vượt timeout.
- Lỗi khởi tạo hoặc lỗi tài nguyên.
- Dependency tạm thời không khả dụng.
- Dữ liệu đầu vào không hợp lệ hoặc lỗi nghiệp vụ.

Retry hữu ích với lỗi tạm thời như network reset, service unavailable hoặc throttling. Retry không tự sửa dữ liệu sai, thiếu quyền IAM hoặc schema không tương thích.

Hãy phân loại lỗi:

| Loại lỗi | Cách xử lý gợi ý |
|---|---|
| Lỗi mạng tạm thời | Retry có backoff và giới hạn |
| API bị throttling | Giảm concurrency, retry có backoff |
| Record sai định dạng | Ghi lỗi record vào bảng/quarantine, không retry vô hạn |
| Thiếu quyền IAM | Sửa cấu hình quyền; retry tự động thường không hữu ích |
| Database quá tải | Giảm parallelism, giới hạn connection và retry có kiểm soát |
| Task timeout | Tối ưu batch size, tăng timeout hợp lý hoặc chia nhỏ task |
| Side effect có kết quả không rõ | Tra cứu bằng idempotency key trước khi thực hiện lại |

Nếu một record lỗi vĩnh viễn, có thể ghi record vào dead-letter table hoặc file lỗi, sau đó tiếp tục các record khác nếu policy cho phép. Khi tất cả record đã được xử lý hoặc được phân loại lỗi theo policy, task có thể kết thúc thành công với thống kê rõ ràng. Nếu batch yêu cầu toàn bộ record thành công, task phải báo lỗi để execution được đánh dấu thất bại.

Không biến mọi exception thành exit code 0 chỉ để job hiển thị xanh. Trạng thái execution cần phản ánh đúng kết quả nghiệp vụ.

## 11. Timeout và xử lý dừng an toàn

Task timeout giới hạn thời gian một task được phép chạy. Chọn timeout dựa trên thời gian xử lý p95/p99 và thời gian cần cho cleanup. Timeout quá thấp tạo retry không cần thiết; timeout quá cao khiến phát hiện task treo chậm.

Ứng dụng nên:

- Chia batch thành đơn vị nhỏ để có checkpoint.
- Đặt timeout cho database và API ngoài ngắn hơn deadline tổng của task.
- Ngừng nhận record mới khi gần deadline.
- Commit phần việc đang an toàn và đóng resource.
- Ghi log tiến độ và checkpoint sau khi commit.
- Đảm bảo retry có thể tiếp tục mà không tạo side effect trùng.

Container có thể nhận tín hiệu kết thúc khi task bị dừng hoặc timeout. Có thể đăng ký shutdown hook để đóng resource và cố gắng flush log, nhưng không dựa vào hook để lưu kết quả nghiệp vụ duy nhất. Process có thể bị kết thúc cưỡng bức hoặc không còn đủ thời gian để hoàn tất cleanup. Checkpoint phải được ghi trong luồng xử lý bình thường.

## 12. Lập lịch chạy bằng Cloud Scheduler

Cloud Scheduler có thể gọi Cloud Run Jobs API theo cron schedule. Cách này phù hợp với báo cáo hằng ngày, đồng bộ mỗi giờ hoặc cleanup theo tuần.

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant S as Cloud Scheduler
    participant A as Cloud Run Jobs API
    participant J as Job execution
    participant T as Tasks
    S->>A: Gọi API run theo lịch
    A->>J: Tạo execution
    J->>T: Phân phối tasks
    T->>T: Xử lý batch và ghi kết quả
    T-->>J: Exit code và trạng thái
    J-->>S: API nhận yêu cầu tạo execution
~~~

Scheduler thường nhận xác nhận rằng API đã chấp nhận yêu cầu tạo execution; điều đó không có nghĩa batch đã hoàn tất. Cần theo dõi execution riêng để biết kết quả cuối cùng.

Khi tạo lịch, cấu hình timezone rõ ràng và xác định chính sách nếu lần chạy trước chưa xong. Hai execution có thể chồng lấn nếu lịch mới đến trong khi job cũ vẫn chạy. Có thể dùng lock theo batch ID, trạng thái execution hoặc một cơ chế điều phối để tránh hai lần chạy cùng kỳ.

Scheduler cần một service account có quyền gọi Cloud Run Jobs API, bao gồm quyền run.jobs.run trên job phù hợp. Dùng danh tính riêng, giới hạn phạm vi tài nguyên và cấu hình OAuth phù hợp khi gọi Google APIs. Không nhúng service account key vào scheduler payload.

Không dùng timezone mặc định của máy chủ để diễn giải lịch. Nếu lịch theo giờ địa phương, cấu hình timezone trên Cloud Scheduler và kiểm tra chính sách DST, đặc biệt với giờ bị thiếu hoặc bị lặp.

## 13. Điều phối nhiều job bằng Workflows

Cloud Run Jobs thực hiện một đơn vị batch. Nếu quy trình gồm nhiều job phụ thuộc nhau, Google Cloud Workflows có thể điều phối:

1. Chạy job import dữ liệu.
2. Chờ execution hoàn tất và kiểm tra trạng thái.
3. Chạy job kiểm tra chất lượng.
4. Chạy job tổng hợp.
5. Gửi thông báo hoặc tạo báo cáo.

Workflows quản lý thứ tự, nhánh điều kiện, retry và lỗi giữa các bước. Không cần viết một Java process dài để khởi chạy job A, ngủ chờ, rồi gọi job B.

Khi dùng Workflows, cần xác định cách theo dõi execution của Cloud Run Job. Việc API chấp nhận yêu cầu run không đồng nghĩa job đã hoàn tất. Workflow có thể gọi Cloud Run Jobs API để tạo execution, lấy tên operation/execution và polling hoặc dùng cơ chế chờ phù hợp cho đến khi có trạng thái cuối.

Nếu quy trình đơn giản chỉ cần một lịch chạy một job, Cloud Scheduler có thể đủ. Nếu cần nhiều bước, điều kiện hoặc compensation, dùng Workflows để điều phối.

## 14. Quyền truy cập và bảo mật

Cloud Run Jobs dùng service account để xác định quyền của code trong container khi gọi Google Cloud APIs. Hãy tạo service account riêng theo job hoặc nhóm trách nhiệm.

Các nguyên tắc quan trọng:

- Chỉ cấp role cần thiết trên đúng project hoặc resource.
- Dùng Application Default Credentials trong container để lấy danh tính runtime.
- Không đóng gói service account JSON key vào image.
- Lưu secret trong Secret Manager và chỉ cấp quyền truy cập cho job cần dùng.
- Không ghi access token, secret hoặc dữ liệu nhạy cảm vào log.
- Giới hạn ai có quyền tạo, cập nhật và chạy job.
- Phân biệt quyền deploy job với quyền execute job.
- Dùng VPC egress/private connectivity nếu job cần truy cập dịch vụ nội bộ.
- Kiểm tra quyền truy cập Cloud Storage, BigQuery, Cloud SQL hoặc API bên ngoài theo nguyên tắc least privilege.

Ví dụ, job đọc file từ một bucket chỉ cần quyền đọc object trong bucket đó. Job ghi kết quả vào một bucket khác cần quyền ghi riêng. Không cấp quyền Storage Admin toàn project nếu chỉ cần object viewer và object creator trên hai bucket cụ thể.

Nếu job truy cập Cloud SQL, cấu hình kết nối và network theo hướng dẫn dịch vụ. Giới hạn số connection mỗi task và tổng connection theo parallelism. Không đặt connection pool lớn mặc định vì mỗi task là một container riêng.

## 15. Kết nối dữ liệu và dịch vụ phụ thuộc

Batch job thường đọc dữ liệu từ Cloud Storage, BigQuery, Cloud SQL, Firestore hoặc Pub/Sub. Hãy chọn cách đọc phù hợp với kích thước và kiểu dữ liệu.

- Với file lớn, đọc theo stream hoặc theo chunk, tránh nạp toàn bộ file vào heap.
- Với BigQuery, dùng query/job phù hợp và đọc kết quả theo page hoặc stream.
- Với database, dùng keyset pagination và transaction ngắn.
- Với Pub/Sub, xác định rõ job đọc snapshot hay xử lý message; không tự tạo một consumer không có ack/lease semantics.
- Với API ngoài, dùng timeout, rate limit, retry có backoff và giới hạn concurrency.

Nếu mỗi task mở 5 database connection và có 20 task chạy song song, dependency có thể nhận tới khoảng 100 connection từ execution đó, chưa tính workload khác. Hãy tính tổng số connection trước khi tăng parallelism.

Với job xử lý file, nên dùng manifest chứa object name, generation/version và checksum. Nếu object bị thay thế giữa lúc job chạy, worker cần biết đang xử lý phiên bản nào. Truyền version hoặc generation giúp kết quả có thể tái lập và dễ điều tra.

## 16. Logging, metrics và vận hành

Cloud Run thu thập stdout và stderr của container vào Cloud Logging. Ứng dụng Java nên ghi log có cấu trúc để liên kết các record với job, execution và task.

Các trường hữu ích:

- Job name và execution name.
- CLOUD_RUN_TASK_INDEX, CLOUD_RUN_TASK_COUNT và CLOUD_RUN_TASK_ATTEMPT.
- Batch ID và input manifest ID.
- Record ID hoặc shard ID.
- Số record đọc, thành công, bỏ qua và thất bại.
- Checkpoint hoặc cursor hiện tại.
- Thời gian xử lý và lỗi dependency.
- Kết quả cuối của task.

Không log toàn bộ payload hoặc secret. Với batch lớn, không ghi một dòng log cho mọi record nếu làm tăng chi phí và gây nhiễu. Dùng counter tổng hợp theo batch, log chi tiết cho lỗi và sampling có kiểm soát.

Các chỉ số cần theo dõi:

- Số execution bắt đầu, thành công, thất bại và timeout.
- Thời lượng execution và task.
- Số task retry và attempt trung bình.
- Throughput record mỗi giây hoặc mỗi phút.
- Số record lỗi và số record đang chờ.
- CPU, memory và OOM.
- Database connection usage và dependency latency.
- Số execution chồng lấn.
- Chi phí compute và lưu trữ theo batch.

Tạo cảnh báo khi execution thất bại, task retry tăng đột biến, job vượt SLA hoặc batch backlog tăng. Có dashboard theo batch ID để vận hành viên xác định batch nào đang chạy và phần nào đã hoàn tất.

## 17. Chi phí và tối ưu tài nguyên

Cloud Run Jobs tính phí theo tài nguyên compute được dùng trong thời gian task chạy theo mô hình giá Cloud Run hiện hành. Khi job không chạy, không có container task hoạt động để xử lý batch; tuy nhiên vẫn có thể có chi phí từ Artifact Registry, Cloud Storage, logging, network, database hoặc dịch vụ được gọi.

Chi phí phụ thuộc vào:

- CPU và memory mỗi task.
- Thời lượng chạy của từng task.
- Số task và số lần retry.
- Parallelism và thời gian hoàn tất toàn batch.
- Dữ liệu đọc/ghi và network egress.
- Cloud Logging volume.
- Database, BigQuery và dịch vụ phụ trợ.
- Tần suất execution.

Tăng parallelism có thể giảm thời gian hoàn tất nhưng không nhất thiết giảm tổng compute time. Nếu các task cùng tranh chấp database hoặc API ngoài, parallelism quá cao có thể làm throughput giảm và retry tăng.

Để tối ưu:

1. Đo CPU và memory thực tế thay vì cấp dư quá nhiều.
2. Chọn batch size đủ lớn để giảm overhead nhưng vẫn có checkpoint thường xuyên.
3. Giới hạn parallelism theo năng lực dependency.
4. Dùng streaming để giảm peak memory.
5. Giảm log thành công lặp lại.
6. Tránh retry các lỗi không thể phục hồi.
7. Chạy job ở region gần dữ liệu và dependency.
8. Theo dõi thời gian chạy và chi phí theo một đơn vị nghiệp vụ, ví dụ chi phí trên 1.000 record.

## 18. Kiểm thử batch job

Cần kiểm thử cả chương trình Java và cách Cloud Run phân phối task:

1. Chạy local với một task và một batch nhỏ.
2. Chạy với nhiều task để kiểm tra phân vùng không bỏ sót hoặc trùng record.
3. Cho một task thất bại giữa chừng rồi xác minh retry tiếp tục an toàn.
4. Cho record lỗi vĩnh viễn và kiểm tra quarantine/dead-letter policy.
5. Kiểm tra task timeout và checkpoint.
6. Tăng parallelism để quan sát database connection và API rate limit.
7. Chạy lại cùng batch ID để xác minh idempotency.
8. Chạy hai execution cùng lúc để kiểm tra lock và overlap policy.
9. Kiểm tra secret không xuất hiện trong log hoặc image.
10. Kiểm tra service account thiếu quyền và quyền tối thiểu.
11. Xác minh job được Cloud Scheduler gọi đúng timezone.
12. Xác minh Workflows chờ trạng thái hoàn tất, không chỉ chờ API run được chấp nhận.

Không chỉ kiểm tra exit code. Cần đối chiếu số record đầu vào, số record hoàn tất, số record bị quarantine và tổng kết batch. Một task có thể thoát code 0 nhưng bỏ qua record do lỗi logic; kiểm tra dữ liệu đầu ra giúp phát hiện tình huống đó.

## 19. Quy trình thiết kế Cloud Run Job cho Java

1. **Xác định workload.** Một lần chạy xử lý bao nhiêu dữ liệu, deadline bao lâu và có cần song song không?
2. **Chọn đơn vị task.** Một task xử lý toàn batch hay mỗi task xử lý một shard?
3. **Thiết kế partition.** Dùng task index/count hoặc manifest phân vùng ổn định.
4. **Thiết kế idempotency.** Dùng batch ID và item ID, unique key và checkpoint bền vững.
5. **Viết Java process.** Dùng main, đọc cấu hình, xử lý phần việc, đóng tài nguyên và trả exit code đúng.
6. **Đóng gói container.** Chọn JRE, build image và lưu ở Artifact Registry.
7. **Cấu hình job.** Đặt task count, parallelism, timeout, retry, CPU, memory và service account.
8. **Bảo vệ dependency.** Giới hạn connection, rate và quyền truy cập.
9. **Chọn cách kích hoạt.** Dùng CLI/API cho thủ công, Cloud Scheduler cho lịch hoặc Workflows cho quy trình nhiều bước.
10. **Quan sát và phục hồi.** Ghi log theo batch/task, lưu checkpoint và cảnh báo khi execution thất bại.
11. **Kiểm thử tải và lỗi.** Mô phỏng retry, timeout, execution trùng và dependency chậm.

Cloud Run Jobs phù hợp với Java batch workload cần chạy đến khi hoàn tất mà không phải duy trì HTTP server. Thiết kế task có thể chia nhỏ, idempotent và có checkpoint giúp job tiếp tục an toàn sau timeout hoặc retry; parallelism cần được điều chỉnh theo năng lực của dịch vụ phụ thuộc.

## 20. Câu hỏi tự kiểm tra

- Cloud Run Jobs khác Cloud Run services ở vòng đời container và cách kích hoạt như thế nào?
- Task count và parallelism kiểm soát hai khía cạnh nào?
- CLOUD_RUN_TASK_INDEX và CLOUD_RUN_TASK_COUNT được dùng để chia dữ liệu ra sao?
- Vì sao CLOUD_RUN_TASK_ATTEMPT không phù hợp làm idempotency key?
- Container cần trả exit code nào khi task thành công?
- Điều gì xảy ra khi task timeout hoặc process thoát với mã khác 0?
- Vì sao cần checkpoint bền vững thay vì chỉ dùng file tạm?
- Làm thế nào để retry không xử lý side effect hai lần?
- Cloud Scheduler xác nhận điều gì khi gọi Jobs API?
- Khi nào nên dùng Workflows để điều phối nhiều Cloud Run Jobs?
- Vì sao parallelism phải tính theo giới hạn database và API bên ngoài?
- Những metric nào giúp xác định batch đang chậm hoặc thất bại?

Cloud Run Jobs giúp đóng gói Java batch application thành một đơn vị thực thi có thể khởi chạy theo yêu cầu hoặc theo lịch. Hãy chia task theo dữ liệu, kiểm soát parallelism, lưu tiến độ bền vững và thiết kế retry an toàn. Khi đó, workload batch có thể mở rộng theo nhu cầu mà không phải giữ một service HTTP hoạt động liên tục.

