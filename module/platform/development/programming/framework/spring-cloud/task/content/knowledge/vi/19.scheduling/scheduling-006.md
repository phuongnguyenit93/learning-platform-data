# Chính sách chạy chồng, thử lại và giới hạn thời gian

Trong chương **Lịch chạy** của module **SPRING_CLOUD_TASK**, tác vụ thường được khởi động theo lịch cố định: tạo báo cáo mỗi sáng, đồng bộ dữ liệu mỗi giờ hoặc đối soát cuối ngày. Spring Cloud Task giúp ứng dụng Spring Boot chạy **hữu hạn** và ghi metadata lần thực thi vào `TaskRepository`. Tuy nhiên, **Spring Cloud Task không tự là một hệ thống lập lịch phân tán**. Việc tạo lịch, cho phép hay cấm chạy chồng, quyết định thử lại tiến trình và áp dụng thời hạn thường thuộc về scheduler hoặc nền tảng triển khai như Kubernetes CronJob, Spring Cloud Data Flow (SCDF) hay một bộ điều phối riêng.

Ba vấn đề thường liên quan chặt chẽ:

- **Chạy chồng (overlap):** lần chạy trước chưa hoàn tất nhưng đã tới thời điểm của lịch tiếp theo.
- **Thử lại (retry):** một lần chạy lỗi; hệ thống quyết định có khởi động thêm attempt hay không, vào lúc nào.
- **Giới hạn thời gian (deadline/timeout):** công việc không hoàn tất kịp; scheduler có thể bỏ qua lần chạy quá muộn, ngừng tiến trình đang chạy hoặc chuyển sang đối soát.

Nếu xử lý các vấn đề này độc lập, hệ thống rất dễ tạo trùng dữ liệu: một task còn chạy bị scheduler khởi chạy tiếp; lần chạy lỗi được cả Kubernetes **và** ứng dụng thử lại; hoặc tiến trình bị kill ngay khi database đang `COMMIT`. Bài này xây dựng một chính sách nhất quán ở cả **điều phối, tiến trình và nghiệp vụ**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt lịch khởi chạy với vòng đời của Spring Cloud Task và metadata `TaskExecution`.
2. Chọn chính sách **cho phép**, **bỏ qua**, hoặc **thay thế** lần chạy chồng, hiểu giới hạn của mỗi lựa chọn.
3. Phân loại lỗi có thể thử lại, lỗi không thể thử lại và trường hợp kết quả chưa xác định.
4. Phân biệt timeout khi chờ lịch, timeout chạy tiến trình, timeout gọi dịch vụ và hạn hoàn tất nghiệp vụ.
5. Cấu hình một ví dụ Kubernetes CronJob với `concurrencyPolicy`, `startingDeadlineSeconds`, `backoffLimit` và `activeDeadlineSeconds`.
6. Giải thích vì sao `TaskRepository` và trạng thái Kubernetes Job có thể mâu thuẫn sau khi JVM chết.
7. Thiết kế business key, khóa duy nhất và đối soát để chạy lại an toàn.
8. Thiết kế checklist quan sát, cảnh báo và kiểm thử cho tác vụ được kích hoạt theo lịch hoặc theo yêu cầu.

## 2. Một lịch chạy không phải một lần thực thi

Giả sử hệ thống cần tổng hợp doanh thu **mỗi ngày lúc 02:00 theo múi giờ Asia/Ho_Chi_Minh**. Một lịch có thể tạo ra nhiều lần chạy vào những ngày khác nhau. Nếu lần chạy ngày 24 chưa xong lúc 02:00 ngày 25, có thể xuất hiện hai tác vụ đang xử lý.

Cần tách các khái niệm:

| Khái niệm | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Schedule** | 02:00 hằng ngày | Khi nào **nên** yêu cầu chạy? |
| **Scheduled occurrence** | Mốc lịch 02:00 ngày 24/11 | Lần **đến hạn** nào cần được xử lý? |
| **Launch request** | `REQ-20261124-DAILY` | Yêu cầu được bộ điều phối tiếp nhận chưa? |
| **Execution / attempt** | `TASK_EXECUTION_ID=503` | Một tiến trình đã khởi chạy như thế nào? |
| **Business key** | `tenant=shop-01;date=2026-11-23;version=v1` | Công việc nghiệp vụ **duy nhất** nào đang được xử lý? |
| **Completion** | Báo cáo được lưu, kiểm tra đủ dữ liệu | Kết quả có đạt yêu cầu hay không? |

Một scheduled occurrence có thể tạo **nhiều attempt** nếu cấu hình retry. Mỗi attempt có thể nhận một `TaskExecution` ID mới. Nhưng **cùng business key chỉ nên tạo một kết quả nghiệp vụ** nếu quy tắc nghiệp vụ yêu cầu tính duy nhất.

~~~mermaid
flowchart TD
    A["Lịch: hằng ngày 02:00"] --> B["Scheduled occurrence: ngày D"]
    B --> C["Yêu cầu chạy + business key K"]
    C --> D["Attempt 1 / TaskExecution #503"]
    D -->|"Lỗi có thể retry"| E["Attempt 2 / TaskExecution #504"]
    D -->|"Hoàn tất"| F["Kết quả nghiệp vụ K"]
    E -->|"Hoàn tất hoặc đã làm trước đó"| F
    F --> G["Đối soát + kết luận cho occurrence D"]
~~~

**Giới hạn quan trọng:** Spring Cloud Task ghi nhận lần chạy ứng dụng, không tự suy ra chính sách cron, xử lý các occurrence bị bỏ lỡ hay ngăn hai tiến trình cùng ghi kết quả. Những điều đó cần được thiết kế bên ngoài repository hoặc trong lớp nghiệp vụ.

## 3. Chính sách chạy chồng: Allow, Forbid và Replace

Khi lần chạy trước chưa xong lúc lịch tiếp theo đến hạn, bộ điều phối cần một chính sách rõ ràng. Kubernetes CronJob cung cấp ba giá trị `concurrencyPolicy` điển hình:

| Chính sách | Khi lịch mới đến lúc job cũ còn active | Phù hợp | Rủi ro |
| --- | --- | --- | --- |
| **`Allow`** | Cho phép tạo Job mới dù Job cũ chưa xong | Công việc độc lập theo kỳ/partition, tài nguyên đủ | Ghi trùng, tranh chấp dữ liệu, quá tải |
| **`Forbid`** | Không khởi tạo Job mới từ **chính CronJob đó** nếu Job cũ còn active | Tổng hợp dùng chung tài nguyên, tránh chạy chồng | Một lịch có thể bị bỏ lỡ; không mặc định được xếp hàng |
| **`Replace`** | Yêu cầu thay Job cũ bằng Job mới | Chỉ kết quả kỳ mới nhất quan trọng và công việc có thể dừng an toàn | Có thể dừng giữa transaction; quá trình kết thúc/cấp phát khiến tác động cũ vẫn tồn tại |

Những tên trên là **chính sách của Kubernetes CronJob**, không phải enum mặc định của Spring Cloud Task. Ở SCDF, Quartz hay scheduler tự xây, cơ chế và cấu hình có thể khác.

### 3.1. Allow: cho chạy song song nhưng phải có phân vùng rõ

Nếu mỗi giờ task chỉ đọc dữ liệu của **một khoảng giờ riêng**, và kết quả được ghi bằng khóa `(tenant, hour)` có unique constraint, việc chạy hai giờ khác nhau cùng lúc có thể hợp lý.

Tuy nhiên, "hai giờ khác nhau" chưa bảo đảm không dùng chung tài nguyên. Cần xem:

- Có cùng ghi một file đích hoặc bảng tổng hợp không?
- Có dùng chung bảng tạm, khóa database hoặc thư mục làm việc không?
- API upstream có giới hạn request đồng thời không?
- Có thể xảy ra out-of-order (giờ mới ghi trước giờ cũ) không?

Nếu nguồn không hỗ trợ song song, đặt `Allow` chỉ vì muốn không bỏ lỡ lịch thường là lựa chọn không an toàn.

### 3.2. Forbid: không chạy chồng, nhưng có thể bỏ lỡ lịch

`Forbid` hữu ích khi một tác vụ không nên chạy hai lần đồng thời. Ví dụ lần đồng bộ lúc 02:00 chạy tới 03:20, trong khi lịch kích hoạt mỗi giờ. Lần đến hạn 03:00 có thể bị **bỏ qua**, chứ không tự động được xếp hàng đến khi 03:20.

Vì thế, nếu từng kỳ **bắt buộc phải xử lý**, phải có bảng hoặc hàng đợi **các kỳ đến hạn chưa hoàn tất**, cùng worker đọc và xử lý backlog. `Forbid` tự nó chỉ giới hạn overlap của Job do một CronJob tạo.

**Phạm vi bảo vệ:** `concurrencyPolicy` không chặn một người khởi chạy thủ công một Job khác, một CronJob khác hay một ứng dụng trên hệ thống khác đang xử lý **cùng business key**. Vẫn cần bảo vệ tại tầng dữ liệu.

### 3.3. Replace: thay lượt chạy cũ nhưng không xóa tác động cũ

`Replace` có thể hợp lý khi làm mới một cache toàn phần mà chỉ phiên bản mới nhất có giá trị, và task có cơ chế publish kết quả nguyên tử. Nhưng nó đặc biệt nguy hiểm với nghiệp vụ thanh toán hoặc cập nhật dữ liệu không idempotent.

Khi yêu cầu thay job, tiến trình cũ có thể nhận tín hiệu dừng rồi cần thời gian đóng, rollback, hủy kết nối. **Không giả định có một thời điểm thần kỳ mà mọi tác động của job cũ đã bị xóa trước khi job mới bắt đầu.** Unique key, fencing token hoặc điều kiện cập nhật có phiên bản mới là tuyến bảo vệ cuối cùng.

### 3.4. Chọn chính sách theo tác động nghiệp vụ

- **Tổng hợp cuối ngày:** thường ưu tiên `Forbid` hoặc một hàng đợi tuần tự, nhưng phải có cơ chế xử lý các ngày bị bỏ lỡ.
- **Tính toán cho các partition độc lập:** có thể chọn `Allow`, đồng thời giới hạn tổng số worker, DB connections và CPU.
- **Refresh snapshot có thể hủy và thay thế:** có thể chọn `Replace` nếu output chỉ được publish sau khi hoàn tất và job cũ không thể ghi đè kết quả mới.
- **Gửi thanh toán/thông báo không hỗ trợ deduplication:** không dựa vào bất kỳ chính sách nào thay cho idempotency tại hệ thống đích.

## 4. Lịch, múi giờ và các lần bị lỡ

Cron expression của **Kubernetes CronJob** thường có **5 trường**: phút, giờ, ngày trong tháng, tháng, thứ trong tuần. Ví dụ:

~~~text
0 2 * * *     # 02:00 hằng ngày
*/15 * * * *  # mỗi 15 phút
~~~

Trong khi đó, cron của Spring `@Scheduled` thường có **6 trường**, gồm cả **giây**. Quartz lại có quy ước khác. **Không sao chép cron giữa các scheduler mà không kiểm tra cú pháp.**

### 4.1. Múi giờ phải được tuyên bố

Kubernetes CronJob trên các phiên bản hỗ trợ có `spec.timeZone` với tên múi giờ IANA:

~~~yaml
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
~~~

Khi không khai báo, giờ chạy có thể phụ thuộc múi giờ của controller theo cấu hình cluster. Đừng suy ra múi giờ từ nơi người vận hành đang ngồi hay từ timezone của JVM.

Khi triển khai ở vùng có DST, một số mốc giờ địa phương có thể **không tồn tại** hoặc **xuất hiện hai lần**; cần xác định policy nghiệp vụ theo *scheduled instant* và calendar. Tên vùng `Asia/Ho_Chi_Minh` trong ví dụ hiện không chuyển DST, nhưng sử dụng IANA timezone vẫn làm cấu hình rõ ràng hơn.

### 4.2. Khoảng trễ được phép khi bỏ lỡ lịch

`startingDeadlineSeconds` của Kubernetes CronJob là giới hạn về **độ trễ so với thời điểm lịch đến hạn** mà controller còn cân nhắc việc bắt đầu Job. Đây không phải thời hạn cho phép **Job chạy bao lâu**.

Ví dụ:

- Job theo lịch 02:00.
- Controller bị gián đoạn và chỉ hoạt động lại lúc 02:18.
- `startingDeadlineSeconds: 600` (10 phút).

Lần lịch 02:00 đã quá cửa sổ 10 phút nên có thể không được khởi tạo. Nếu một kỳ không được phép mất, cần hệ thống lưu occurrence để bổ sung, **không coi CronJob là một hàng đợi bền vững có bảo đảm đúng một lần**.

Kubernetes cũng có những giới hạn về cách CronJob controller xử lý số lần missed schedule; hãy kiểm tra tài liệu của phiên bản cluster. Việc xóa Job cũ do retention **không chứng minh lịch đó chưa từng chạy**.

## 5. Retry khác với khởi chạy lặp theo lịch

Một lần chạy tự kết thúc với mã khác `0` hoặc process bị lỗi có thể kích hoạt nhiều tầng retry:

1. **Trong ứng dụng:** retry JDBC, HTTP client hoặc một thao tác nhỏ.
2. **Trong Spring Batch:** retry chunk/item theo chính sách skip/retry đã cấu hình.
3. **Ở Kubernetes Job:** tạo thêm Pod hoặc khởi động lại container tùy `restartPolicy` và `backoffLimit`.
4. **Ở scheduler/SCDF:** quyết định launch lại cả task.
5. **Ở API caller:** gửi lại yêu cầu launch nếu bị timeout.

Các tầng không được cấu hình độc lập mà không tính tác động tổng thể. Ví dụ nếu một hệ thống điều phối thử **3 lần launch**, và **mỗi Job có tối đa 3 Pod attempt**, ứng dụng có thể được khởi chạy tới **9 lần** trong tình huống xấu; nếu mỗi lần lại gọi upstream 5 lần thì số yêu cầu tăng mạnh. Đây là phép minh họa giới hạn thiết kế, không phải công thức chính xác cho mọi trạng thái Kubernetes.

### 5.1. Nhóm lỗi và hành động

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Tạm thời** | HTTP 503, lỗi DNS ngắn hạn, deadlock/serialization failure | Retry có giới hạn, backoff và jitter; cùng business key |
| **Không thể retry nguyên trạng** | Ngày sai định dạng, schema thiếu, quyền DB sai, conflict dữ liệu | Fail có thông điệp rõ, sửa nguyên nhân trước |
| **Kết quả không xác định** | Đứt kết nối quanh `COMMIT`; timeout sau khi gọi API thanh toán | Đối soát bằng business key/idempotency key trước khi phát lại |
| **Quá tải** | API trả 429, database hết connection pool | Giảm concurrency, tôn trọng `Retry-After` khi có, backoff |
| **Lỗi resource** | OOMKilled, đầy disk, CPU throttling nghiêm trọng | Chỉnh resource và phân tích nguyên nhân; không lặp vô hạn |
| **Quá deadline** | Process đã chạy lâu hơn giới hạn | Xác minh trạng thái nghiệp vụ trước khi retry; xử lý cancellation |

Khi không biết transaction đã commit hay chưa, lỗi nằm trong nhóm **UNKNOWN**. Không được coi mọi exception từ database là bằng chứng “chưa ghi gì”.

### 5.2. Exponential backoff và jitter

Một quy tắc minh họa cho lỗi tạm thời:

~~~text
delay(attempt) = min(maxDelay, initialDelay × 2^(attempt-1))
wait = delay(attempt) + randomJitter
~~~

Ví dụ `initialDelay=5 giây`, `maxDelay=60 giây` và tối đa **3 attempt**. Không nên dùng cùng lịch retry chính xác của hàng nghìn task nếu nguồn upstream vừa phục hồi; jitter giúp phân tán lưu lượng.

**Giới hạn tổng thời gian** cũng cần áp dụng: retry sau deadline nghiệp vụ có thể không còn ý nghĩa. Mọi lần thử phải dùng cùng **business key** và nên có mã tương quan để nối log.

## 6. Timeout và deadline: bốn lớp khác nhau

"Task timeout" có thể chỉ nhiều loại thời hạn. Gộp chúng thành một giá trị sẽ gây nhầm khi điều tra sự cố.

| Tầng | Câu hỏi | Ví dụ cấu hình/cơ chế |
| --- | --- | --- |
| **Chậm khởi chạy** | Occurrence đến hạn bao lâu còn được phép bắt đầu? | CronJob `startingDeadlineSeconds` |
| **Thời gian sống của Job** | Một Job được phép hoạt động tối đa bao lâu? | Kubernetes Job `activeDeadlineSeconds` |
| **Lời gọi nghiệp vụ** | HTTP, SQL hay message chờ phản hồi bao lâu? | HTTP client connect/read timeout, JDBC query timeout |
| **SLA nghiệp vụ** | Báo cáo phải hoàn tất trước thời điểm nào? | Deadline riêng trong bảng điều phối/giám sát |

Thêm hai giá trị khác:

- **Thời gian chờ xác nhận launch:** caller chờ REST API trả receipt bao lâu. Timeout ở đây không chứng minh server chưa tạo Job.
- **Thời gian dừng nhẹ:** khi nhận `SIGTERM`, Pod còn bao lâu để đóng tài nguyên trước khi bị dừng cưỡng bức (`terminationGracePeriodSeconds`). Đây không phải một đảm bảo transaction đã rollback hoàn toàn.

### 6.1. activeDeadlineSeconds không giống startingDeadlineSeconds

Ví dụ:

~~~yaml
spec:
  startingDeadlineSeconds: 600
  jobTemplate:
    spec:
      activeDeadlineSeconds: 1800
~~~

- `600` giây: cửa sổ khởi chạy muộn của **CronJob occurrence**.
- `1800` giây: giới hạn thời gian hoạt động của **một Job** sau khi bắt đầu theo cách Job controller quản lý; gồm những trì hoãn triển khai liên quan, không chỉ thời gian runner xử lý.

Nếu Job vượt `activeDeadlineSeconds`, Kubernetes đánh dấu thời hạn vượt quá và dừng các Pod thuộc Job theo cơ chế nền tảng. `backoffLimit` không cho Job chạy thêm vô hạn sau deadline đó.

**Đừng dùng deadline để dự đoán kết quả database:** tiến trình có thể đã commit một phần trước khi bị dừng. Sau timeout, cần đối soát nghiệp vụ như sau lỗi kết nối.

### 6.2. Timeout phải nhất quán theo thứ bậc

Một bộ giới hạn ví dụ:

- HTTP request timeout: 30 giây.
- Retry tối đa 3 lần với backoff.
- Toàn bộ việc xử lý nghiệp vụ dự kiến dưới 20 phút.
- Job active deadline: 30 phút.
- SLA của báo cáo: trước 03:00, tính từ occurrence lúc 02:00.

Đây là **thông số minh họa**, phải điều chỉnh theo dữ liệu thực tế. Nếu tổng thời gian tối đa của HTTP retry có thể vượt 30 phút, Job sẽ bị kill giữa chừng và chính sách retry tầng trong trở nên vô nghĩa.

## 7. Ví dụ Kubernetes CronJob: tránh chạy chồng, retry giới hạn

Dưới đây là một cấu hình **minh họa** cho task tổng hợp vào 02:00 hằng ngày. Nó chọn `Forbid` vì không muốn hai Job **cùng CronJob** xử lý đồng thời.

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-report-task
  namespace: batch
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  jobTemplate:
    spec:
      backoffLimit: 1
      activeDeadlineSeconds: 1800
      parallelism: 1
      completions: 1
      template:
        spec:
          restartPolicy: Never
          terminationGracePeriodSeconds: 30
          containers:
            - name: daily-report
              image: registry.example.internal/batch/daily-report:1.0.0
              imagePullPolicy: IfNotPresent
              command: ["java"]
              args: ["-jar", "/app/daily-report.jar", "--mode=process-due"]
              env:
                - name: TASK_DB_URL
                  valueFrom:
                    secretKeyRef:
                      name: daily-report-db
                      key: jdbc-url
                - name: TASK_DB_USERNAME
                  valueFrom:
                    secretKeyRef:
                      name: daily-report-db
                      key: username
                - name: TASK_DB_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: daily-report-db
                      key: password
              resources:
                requests:
                  cpu: "250m"
                  memory: "256Mi"
                limits:
                  cpu: "1"
                  memory: "512Mi"
~~~

**Điều kiện của ví dụ:** namespace `batch`, registry/image, secret `daily-report-db` và ứng dụng JAR phải được chuẩn bị trước; `--mode=process-due` là **giao diện CLI do ứng dụng ví dụ tự quy định**, không phải cờ được Spring Cloud Task cung cấp sẵn. Nếu ứng dụng chưa hỗ trợ mode này, CronJob sẽ không tự làm được phần tìm các kỳ đến hạn.

### 7.1. Ý nghĩa từng trường

| Trường | Tác dụng thực tế |
| --- | --- |
| `schedule: "0 2 * * *"` | Yêu cầu chạy lúc 02:00 mỗi ngày |
| `timeZone` | Dùng múi giờ IANA đã chỉ định (được hỗ trợ trong các bản Kubernetes mới phù hợp) |
| `concurrencyPolicy: Forbid` | Không chạy chồng Job đang active của chính CronJob này |
| `startingDeadlineSeconds: 600` | Không cố bắt đầu occurrence đã quá cửa sổ 10 phút |
| `backoffLimit: 1` | Giới hạn số lần Job thử lại khi gặp Pod thất bại; thông thường cho phép tối đa một lần retry sau attempt đầu trong cấu hình đơn giản |
| `activeDeadlineSeconds: 1800` | Một Job không kéo dài quá khoảng 30 phút theo cơ chế deadline của Job |
| `parallelism: 1`, `completions: 1` | Job cần một lần hoàn thành, không có chủ ý chia nhiều Pod song song |
| `restartPolicy: Never` | Container thất bại không được restart ngay bên trong cùng Pod; Job controller có thể tạo Pod khác theo retry policy |
| `terminationGracePeriodSeconds: 30` | Khoảng grace dành cho Pod xử lý dừng trước khi bị kết thúc cưỡng bức |
| `successfulJobsHistoryLimit / failedJobsHistoryLimit` | Giới hạn số Job cũ được CronJob giữ, không phải retention của `TaskRepository` |

Trên hệ thống thật, phải kiểm tra admission policy, quyền đọc Secret, resource quota, image pull và khả năng truy cập database. Không hard-code mật khẩu vào `args` vì command line có thể xuất hiện trong lịch sử container hoặc metadata task.

### 7.2. Vì sao không đặt businessDate cố định trong CronJob?

Một cấu hình như:

~~~yaml
args: ["-jar", "/app/daily-report.jar", "--businessDate=2026-11-24"]
~~~

sẽ xử lý **cùng ngày 24/11 trong mọi lần chạy**, dù CronJob lặp mỗi ngày. Thay bằng ngày hiện tại lấy từ đồng hồ JVM cũng không luôn đúng: một occurrence bị trễ qua ngày hôm sau có thể chọn **sai kỳ**.

Cách ổn định hơn là **sinh business key từ scheduled occurrence** trong bộ điều phối và lưu bền vững, hoặc để `--mode=process-due` lấy một kỳ **đến hạn nhưng chưa hoàn tất** từ bảng/hàng đợi nghiệp vụ. Mỗi attempt cho cùng kỳ phải dùng cùng `businessDate`, `tenantId` và `version`. Nếu muốn dùng scheduled timestamp của Kubernetes Job, phải kiểm tra tính năng annotation/metadata trong **phiên bản Kubernetes thực tế** và cách đưa giá trị đó tới ứng dụng; đừng giả định CronJob tự truyền ngày lịch vào tham số JVM.

### 7.3. Schema metadata Spring Cloud Task

Trong ứng dụng, cấu hình JDBC metadata qua biến môi trường:

~~~yaml
spring:
  application:
    name: daily-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USERNAME}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      name: daily-report-task
      initialize-enabled: false
~~~

Dùng database bền vững, đã tạo bảng Task đúng phiên bản qua migration. `initialize-enabled: false` **không tắt TaskRepository**; nó giả định schema đã có và không để mỗi instance tự tạo bảng khi khởi động.

## 8. Thiết kế bảng kỳ đến hạn để không mất lịch

Nếu `Forbid` bỏ qua một occurrence hoặc scheduler ngừng hoạt động, quy trình không nên mặc định rằng "ngày đó không cần làm nữa". Với công việc cần xử lý đầy đủ từng kỳ, có thể dùng một **bảng yêu cầu nghiệp vụ**:

~~~sql
CREATE TABLE scheduled_work (
    tenant_id       VARCHAR(64) NOT NULL,
    business_date   DATE NOT NULL,
    report_version  VARCHAR(24) NOT NULL,
    status          VARCHAR(32) NOT NULL,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    scheduled_at    TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

**Lưu ý:** đây là schema **ứng dụng do nhóm phát triển tự tạo**, không phải bảng chuẩn của Spring Cloud Task.

Có thể có một dịch vụ lập kế hoạch tạo row khi occurrence đến hạn, và một worker xử lý `PENDING` hoặc `RETRYABLE`:

1. Xác định business key cho occurrence, ghi row bằng thao tác idempotent (`INSERT ... ON CONFLICT DO NOTHING` đối với PostgreSQL).
2. Worker chọn một row chưa hoàn tất và **claim nguyên tử** bằng transaction/row lock hoặc lease có hạn, không chỉ đọc `SELECT` rồi giả định mình sở hữu.
3. Chạy tác vụ và cập nhật kết quả nghiệp vụ theo cùng business key.
4. Chỉ đánh dấu `COMPLETED` khi kết quả thực tế đã được ghi/xác minh.
5. Nếu crash, kiểm tra lease, kết quả đã commit và khả năng tiếp tục trước khi thử lại.

### Bảo vệ xử lý đồng thời

Một kiểu claim có thể dùng `SELECT ... FOR UPDATE SKIP LOCKED` trong transaction ngắn khi nhiều worker lấy việc từ cùng database, kết hợp update trạng thái/lease. Nhưng **không giữ transaction khóa row suốt nhiều phút chỉ để làm công việc**. Hãy dùng lease có timeout, token thế hệ (*fencing token*) và ràng buộc dữ liệu ở đích để tránh worker cũ ghi đè worker mới sau khi lease hết hạn.

Nếu báo cáo được tạo từ nhiều partition, khóa duy nhất có thể ở cấp `(businessDate, partitionId, version)`; chỉ dùng khóa ngày sẽ vô tình ngăn các partition độc lập.

## 9. Retry an toàn khi mất kết nối hoặc bị dừng giữa commit

Một lỗi nguy hiểm xảy ra khi database đã commit báo cáo, nhưng kết nối bị ngắt trước khi JVM nhận xác nhận. Scheduler nhìn thấy attempt lỗi và thử lại.

Đừng suy luận:

~~~text
Exit code != 0  =>  chắc chắn nghiệp vụ chưa commit
~~~

Thay vào đó:

~~~mermaid
flowchart TD
    A["Job thất bại, timeout hoặc bị kill"] --> B["Lấy business key từ lịch / bảng yêu cầu"]
    B --> C{"Có thể đọc nguồn dữ liệu nghiệp vụ chính?"}
    C -->|"Không"| D["UNKNOWN: cảnh báo và backoff để đối soát"]
    C -->|"Có"| E["Kiểm tra kết quả đã commit theo key"]
    E --> F{"Kết quả tồn tại và đúng?"}
    F -->|"Có"| G["Xác nhận đã hoàn tất; không tạo bản trùng"]
    F -->|"Không; key đã có nhưng khác"| H["CONFLICT: điều tra"]
    F -->|"Chưa có"| I["Thử lại thao tác idempotent với cùng key"]
    I --> J["Kiểm tra lại kết quả / cập nhật trạng thái"]
    J --> G
~~~

Để bước kiểm tra và lần ghi không bị race khi hai tiến trình cùng chạy, cần `UNIQUE`/`PRIMARY KEY` hoặc cơ chế ghi nguyên tử tương đương **ở database nghiệp vụ**, không chỉ đọc `SELECT` trước `INSERT`.

Ví dụ PostgreSQL ghi **một** record kết quả cho một kỳ:

~~~sql
CREATE TABLE daily_report (
    tenant_id      VARCHAR(64) NOT NULL,
    business_date  DATE NOT NULL,
    report_version VARCHAR(24) NOT NULL,
    content_hash   CHAR(64) NOT NULL,
    report_body    TEXT NOT NULL,
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

~~~sql
INSERT INTO daily_report (
    tenant_id, business_date, report_version, content_hash, report_body
)
VALUES ('shop-01', DATE '2026-11-23', 'v1', :content_hash, :report_body)
ON CONFLICT (tenant_id, business_date, report_version)
DO NOTHING;
~~~

Các tham số `:content_hash` và `:report_body` ở đây là placeholder của layer SQL có hỗ trợ named parameters, **không phải cú pháp mặc định của `JdbcTemplate` trực tiếp**. Với `JdbcTemplate` dùng `?` và tham số binding tương ứng.

Nếu row đã tồn tại, phải kiểm tra hash và nghiệp vụ: **cùng key nhưng dữ liệu khác** là conflict hoặc yêu cầu version mới, không được trả thành công giả. Nếu task gửi email/HTTP hoặc ghi object storage, cần thêm idempotency key hoặc đối soát ở hệ thống đích; transaction JDBC một mình không thể rollback hiệu ứng ở các hệ thống khác.

## 10. Ứng dụng Spring Cloud Task phải phản ánh lỗi đúng

Một `ApplicationRunner` thường nhận tham số rồi gọi service nghiệp vụ. Khi có lỗi chưa xử lý được, không nên bắt exception rồi chỉ log để chương trình kết thúc bình thường.

Ví dụ cấu trúc Java:

~~~java
package com.example.task;

import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DailyReportApplication {

    public static void main(String[] args) {
        SpringApplication.run(DailyReportApplication.class, args);
    }

    @Bean
    ApplicationRunner dailyReportRunner(ReportService service) {
        return args -> {
            LocalDate date = requiredDate(args, "businessDate");
            String tenant = requiredValue(args, "tenant");

            service.generateIdempotently(tenant, date, "v1");
            System.out.println("Hoàn tất báo cáo: " + tenant + "/" + date);
        };
    }

    private static LocalDate requiredDate(
            ApplicationArguments args, String name) {
        return LocalDate.parse(requiredValue(args, name));
    }

    private static String requiredValue(
            ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu hoặc không hợp lệ: --" + name + "=...");
        }
        return values.get(0).trim();
    }
}
~~~

`ReportService` là service nghiệp vụ **do dự án phải triển khai**, không phải class của Spring Cloud Task. Nó cần xử lý idempotency/transaction và kết quả commit không rõ như mục 8–9; ví dụ chỉ minh họa cấu trúc runner và kiểm tra tham số.

Mặt khác, CronJob mẫu mục 7 dùng `--mode=process-due`; muốn kết hợp hai ví dụ phải **thực sự triển khai chế độ lấy kỳ đến hạn** hoặc đổi cấu hình launcher để truyền `--tenant` và `--businessDate` ổn định. Không thể dùng nguyên Java yêu cầu hai tham số với CronJob không truyền các tham số đó.

### Spring Cloud Task tự ghi nhận điều gì?

Khi hạ tầng được cấu hình đúng và repository hoạt động, mỗi lần ứng dụng khởi chạy có thể tạo một `TaskExecution`. Những thông tin hữu ích là:

- `TASK_EXECUTION_ID` — ID của attempt.
- `TASK_NAME` — tên ứng dụng task.
- `START_TIME` và `END_TIME`.
- `EXIT_CODE`, `EXIT_MESSAGE` và `ERROR_MESSAGE`.

Nhưng `EXIT_CODE=0` không thể thay thế kiểm tra kết quả nghiệp vụ. Ngược lại, `END_TIME IS NULL` cũng không tự chứng minh tiến trình còn chạy. Nếu `ApplicationContext` thất bại sớm, có thể không có row nào trong `TaskRepository`.

Ví dụ SQL tra cứu:

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME,
       END_TIME, EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-report-task'
ORDER BY START_TIME DESC;
~~~

Để biết vì sao một Job bị kill do timeout, cần **đối chiếu với trạng thái Kubernetes Job/Pod và log**, vì repository không thể luôn cập nhật metadata khi runtime dừng cưỡng bức.

## 11. Quan sát và cảnh báo theo lịch

Nên có ít nhất ba nguồn dữ liệu:

~~~mermaid
flowchart LR
    A["CronJob / scheduler"] --> B["Job / Pod trạng thái runtime"]
    A --> C["Business key + scheduled occurrence"]
    B --> D["Đối soát vận hành"]
    E["TaskRepository / TaskExecution"] --> D
    C --> D
    D --> F["Business DB: kết quả đúng/đủ?"]
    F --> G["SUCCEEDED / FAILED / MISSED / UNKNOWN"]
~~~

| Dữ liệu | Nguồn | Vì sao cần? |
| --- | --- | --- |
| `scheduledAt` | Scheduler hoặc bảng occurrence | Biết kỳ nào đã đến hạn, kể cả khi Job chưa được tạo |
| `acceptedAt` / Job UID | API runtime | Biết Job đã được tiếp nhận |
| `startedAt`, `finishedAt` | Pod, Job, scheduler | Đo thực tế thời gian khởi động/chạy |
| `taskExecutionId` | `TaskRepository` | Tra chi tiết lỗi Task khi có record |
| `businessKey` và `attempt` | Bảng điều phối | Nối nhiều lần thử thành cùng yêu cầu |
| `lastHeartbeat` / lease | Lớp công việc nếu cần | Phân biệt worker còn sống và bản ghi stale |
| `deadline` / SLA | Quy định nghiệp vụ | Xác định khi nào cần cảnh báo |
| `resultFingerprint` / output URI | Database nghiệp vụ | Xác nhận kết quả thực sự |

### Các cảnh báo hữu ích

- Một occurrence đã quá `scheduledAt + tolerance` nhưng chưa có Job và chưa có kết quả: **MISSED_SCHEDULE**.
- Một Job chạy quá ngưỡng dự kiến dù chưa vượt deadline: **SLOW_TASK**.
- Pod bị OOMKilled, `DeadlineExceeded` hoặc lặp thất bại: **EXECUTION_FAILED**.
- Job đã kết thúc nhưng `TaskExecution.END_TIME` còn trống sau thời gian đối soát: **METADATA_INCOMPLETE**.
- Nhiều attempt xử lý cùng business key đồng thời: **OVERLAP_DETECTED**.
- Chưa có kết quả nghiệp vụ sau SLA dù một attempt có `EXIT_CODE=0`: **BUSINESS_INCOMPLETE**.

Đây là tên cảnh báo **do nhóm vận hành có thể quy ước**, không phải trạng thái mặc định của Spring Cloud Task.

## 12. Tình huống ví dụ theo mốc thời gian

Giả sử lịch hằng ngày 02:00, dùng `Forbid`, `startingDeadlineSeconds=600` và `activeDeadlineSeconds=1800`.

| Thời gian | Sự kiện | Kết luận |
| --- | --- | --- |
| 02:00 | CronJob đến hạn, controller tạo Job J1 | Đã tiếp nhận lịch, **chưa** có kết quả nghiệp vụ |
| 02:02 | Pod bắt đầu JVM, `TaskExecution` được ghi | Có bằng chứng task đã thực thi |
| 02:15 | Báo cáo được commit | Có thể xác minh kết quả nghiệp vụ bằng key |
| 02:17 | TaskRepository cập nhật thành công, process kết thúc | Có đủ metadata để báo hoàn tất nếu output đúng |
| Ngày hôm sau 02:00 | Controller lại đến hạn | Đây là occurrence **khác**, có business key khác |
| Tình huống lỗi: 02:18 | JVM bị dừng ngay sau commit nhưng trước ghi `END_TIME` | Không tự retry mù; đối soát key trước |

Một ví dụ khác: nếu lịch **mỗi 10 phút**, lần 02:00 chạy tới 02:35, `Forbid` có thể làm bỏ qua các mốc 02:10, 02:20, 02:30. Vì thế cần một **backlog ledger** nếu từng kỳ 10 phút đều phải được thực hiện.

Không tự tăng số attempt hoặc đổi `businessDate` khi task chưa hoàn tất; điều đó làm mất khả năng liên hệ và chống trùng giữa các lần chạy.

## 13. Spring Cloud Data Flow và @Scheduled

Kubernetes CronJob là một cách triển khai lịch, nhưng không phải lựa chọn duy nhất.

### 13.1. Spring Cloud Data Flow

SCDF có tính năng đăng ký, khởi chạy và lên lịch Task trên các nền tảng được hỗ trợ. Khi dùng SCDF, các thuộc tính lập lịch, tài nguyên, concurrency và retry phụ thuộc **scheduler/deployer đích và phiên bản SCDF**, không nên sao chép nguyên YAML của Kubernetes để giả định chúng là các property chung của Spring Cloud Task.

Nguyên tắc vẫn giữ:

- Một lịch hoặc trigger tạo **yêu cầu launch**.
- Cần phân biệt `launch accepted` với **task completed**.
- Lưu correlation giữa scheduled occurrence, execution ID, platform Job và business key.
- Quan sát kết quả qua cả SCDF/runtime, `TaskRepository` và kho nghiệp vụ.
- Không tự động re-launch khi phản hồi launch timeout mà chưa tra cứu xem lần chạy đã được chấp nhận hay chưa.

### 13.2. @Scheduled trong Spring

`@Scheduled` phù hợp khi bạn viết một **ứng dụng service tồn tại lâu dài** để kích hoạt công việc định kỳ. Đặt `@Scheduled` bên trong một Spring Cloud Task **được thiết kế chạy một lần rồi thoát** thường không phải kiến trúc thích hợp: ứng dụng phải giữ JVM sống để chờ mốc tiếp theo, làm mất đặc tính tiến trình hữu hạn.

Nếu dùng một service điều phối có `@Scheduled`, service ấy có thể gọi launcher để **tạo tiến trình Spring Cloud Task riêng**. Tuy nhiên:

- `@Scheduled` mặc định không tự là distributed lock giữa nhiều replica.
- Cần tách timer và worker, có cơ chế leader election/lock khi đa replica.
- Không dựa vào cron của Spring để bảo đảm không bỏ lỡ lịch qua downtime nếu chưa có persistence cho occurrence.
- Cú pháp cron và cách chỉ định zone khác Kubernetes CronJob.

## 14. Phối hợp với Spring Batch

Một ứng dụng Spring Cloud Task có thể chạy Spring Batch Job. Hai loại repository theo dõi hai lớp:

- `TaskRepository`: metadata của **một lần khởi chạy ứng dụng**.
- `JobRepository`: `JobExecution`, `StepExecution`, checkpoint và restart của **Batch Job/Step**.

Khi scheduler retry cả tiến trình:

1. Xác định business key và bộ `JobParameters` theo ý nghĩa nghiệp vụ.
2. Xác định có muốn **restart cùng JobInstance** hay tạo job instance mới. Điều này phụ thuộc các **identifying parameters** của Spring Batch, không chỉ tên task.
3. Kiểm tra checkpoint và transaction của reader/writer; các bước đã commit có thể không cần chạy lại.
4. Với writer ra API, email, object storage, phải thiết kế idempotency hoặc bù trừ riêng.
5. Xác minh việc job Batch thất bại có được phản ánh vào mã thoát Task theo chính sách phiên bản. Ví dụ khi được hỗ trợ: `spring.cloud.task.batch.fail-on-job-failure=true`.

Không nên coi `BatchStatus.COMPLETED` tự động là báo cáo đã được gửi đến đối tác. Nếu gửi thông báo là bước ngoài Job và thất bại, task tổng thể vẫn có thể chưa đạt mục tiêu.

## 15. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Hai Job cùng kỳ chạy song song | `Allow`, nhiều CronJob hoặc trigger thủ công | Chọn policy phù hợp; thêm khóa nghiệp vụ/database |
| Chọn `Forbid` nhưng thiếu dữ liệu một giờ | Occurrence bị bỏ qua khi Job cũ còn active | Tạo backlog/ledger và cơ chế xử lý kỳ bỏ lỡ |
| `Replace` làm báo cáo mới bị ghi đè | Task cũ dừng chậm, không có fencing/version | Atomic publish, token thế hệ, ràng buộc unique |
| Job bị dừng sau 30 phút | `activeDeadlineSeconds` đạt giới hạn | Kiểm tra log, runtime và kết quả nghiệp vụ; tối ưu/điều chỉnh deadline |
| Không có Job khi controller chậm | Quá `startingDeadlineSeconds` hoặc schedule bị lỗi | Theo dõi missed occurrence, sửa scheduler, backfill |
| Có nhiều attempt hơn mong đợi | Retry ở nhiều tầng (client, Batch, Job, scheduler) | Tính tổng retry budget; bỏ cấu hình lặp không cần |
| Chạy lại ghi trùng báo cáo | Không có business key/unique constraint | Thiết kế idempotency và đối soát |
| `END_TIME IS NULL` nhưng Job đã Failed | JVM bị kill hoặc JDBC cập nhật lỗi | Đối chiếu Job/Pod, log, DB và trạng thái output |
| Cùng cron nhưng chạy sai giờ | Khác timezone hoặc cron syntax | Đặt timezone rõ, test lịch theo môi trường đích |
| Task chạy theo lịch nhưng JVM không kết thúc | Web server/luồng nền giữ process hoặc thiết kế job dài hạn | Dùng ứng dụng không web, bảo đảm runner hoàn tất và resource được đóng |

## 16. Checklist đưa lịch chạy lên production

- [ ] Xác định **business key** của từng kỳ và làm rõ khi nào các kỳ độc lập có thể chạy song song.
- [ ] Chọn policy overlap (`Allow`/`Forbid`/`Replace` hoặc cơ chế tương đương) dựa trên kết quả nghiệp vụ, không chỉ tiện quản trị.
- [ ] Có giải pháp cho **missed occurrence** nếu không được phép mất lịch.
- [ ] Khai báo cron và múi giờ theo scheduler thực tế; đã kiểm thử DST nếu có.
- [ ] Tách `startingDeadline`, Job active deadline, API timeout và SLA nghiệp vụ.
- [ ] Đặt retry budget xuyên các tầng; phân loại lỗi có thể retry, lỗi cấu hình và kết quả UNKNOWN.
- [ ] Dùng khóa unique/idempotency tại nguồn tác động nghiệp vụ, kể cả khi đã chọn `Forbid`.
- [ ] Có cơ chế shutdown/timeout, resource request/limit và log phục vụ điều tra.
- [ ] Tác vụ sử dụng `TaskRepository` JDBC lưu bền vững nếu yêu cầu giữ lịch sử.
- [ ] Đối soát scheduler/runtime, TaskExecution, Batch JobExecution (nếu có) và output nghiệp vụ.
- [ ] Có cảnh báo khi lịch bị bỏ lỡ, overlap bất thường, timeout, retry cạn hoặc metadata thiếu.
- [ ] Đã kiểm thử lỗi mạng quanh `COMMIT`, Pod bị kill sau commit và nhiều lần launch cùng key.
- [ ] Secret và thông tin nhạy cảm không xuất hiện trong args/log/metadata.

## 17. Bài tập và câu hỏi tự kiểm tra

**Câu hỏi 1.** Một CronJob chạy mỗi 15 phút nhưng mỗi lần xử lý mất 25 phút. So sánh hệ quả khi chọn `Allow`, `Forbid` và `Replace`. Chọn giải pháp khi **không kỳ nào được phép bỏ lỡ**.

**Câu hỏi 2.** Vì sao `startingDeadlineSeconds: 600` không có nghĩa tiến trình được phép chạy tối đa 600 giây?

**Câu hỏi 3.** Kubernetes CronJob dùng `concurrencyPolicy: Forbid`. Một người vẫn tạo Job thủ công cùng đầu vào. Điều gì có thể xảy ra và cần lớp bảo vệ nào?

**Câu hỏi 4.** Job gặp timeout ngay sau lệnh SQL `COMMIT`. Có được kết luận dữ liệu đã rollback không? Tại sao?

**Câu hỏi 5.** Nếu đã cấu hình Job retry ở Kubernetes, vì sao không nên để caller REST tự động gửi lại yêu cầu launch vô hạn?

**Câu hỏi 6.** Khi `END_TIME IS NULL` nhưng Pod đã bị OOMKilled, bạn sẽ lấy bằng chứng nào để quyết định retry?

**Bài tập A — Chọn policy.** Cho ba công việc: đồng bộ cache chỉ cần dữ liệu mới nhất, xuất hóa đơn không được trùng, và xử lý các partition độc lập. Chọn overlap policy, giải thích cách bảo vệ ở database hoặc hệ thống đích.

**Bài tập B — CronJob YAML.** Chỉnh ví dụ mục 7 thành lịch mỗi 30 phút, có deadline và retry budget thích hợp. Giải thích số occurrence có thể bị bỏ lỡ khi mỗi lần chạy mất 45 phút.

**Bài tập C — Backlog.** Thiết kế bảng `scheduled_work` và luồng claim để bảo đảm tất cả kỳ đến hạn đều được xử lý, dù `Forbid` có thể bỏ mốc cron. Thêm lease timeout và unique key.

**Bài tập D — Fault injection.** Trong môi trường test, mô phỏng Job bị dừng sau khi ghi kết quả nhưng trước khi TaskRepository cập nhật. Chạy lại cùng business key và chứng minh dữ liệu nghiệp vụ không bị nhân đôi.

**Bài tập E — Budget.** Lập bảng tính tổng số lần gọi upstream khi có retry ở HTTP client, Spring Batch, Kubernetes Job và scheduler. Đề xuất nơi nên giữ retry và giới hạn SLA.

## 18. Ghi nhớ

- **Lịch chạy nằm ở scheduler/deployer; Spring Cloud Task theo dõi một lần thực thi hữu hạn.**
- **Allow** cho phép Job chạy chồng, **Forbid** hạn chế chồng nhưng có thể bỏ lỡ occurrence, **Replace** cố thay Job cũ nhưng không xóa các tác động đã xảy ra.
- `startingDeadlineSeconds` giới hạn mức **trễ khởi chạy**; `activeDeadlineSeconds` giới hạn **thời gian Job**; timeout API/DB và SLA nghiệp vụ là các phạm vi khác.
- Retry cần **giới hạn tổng thể**, backoff/jitter và phân loại lỗi. Timeout hoặc mất kết nối quanh `COMMIT` khiến kết quả có thể **không xác định**.
- `TaskExecution` giúp tra cứu thời gian và exit code, nhưng **không đủ để chứng minh** rằng mọi kỳ đã được xử lý hoặc không có dữ liệu trùng.
- Nếu không được bỏ lỡ một lịch, hãy lưu occurrence trong **backlog/ledger bền vững** và dùng business key cố định qua các attempt.
- Khi phối hợp Spring Batch, phải đối chiếu cả `JobExecution`/`StepExecution` và kết quả nghiệp vụ, không chỉ mã thoát tiến trình.

## Tài liệu tham khảo

- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): `schedule`, `timeZone`, `concurrencyPolicy`, `startingDeadlineSeconds` và missed schedules.
- [Kubernetes — Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/): `backoffLimit`, `activeDeadlineSeconds`, `parallelism` và xử lý Pod failure.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): dừng Pod, termination signals và grace period.
- [Spring Cloud Task — Features](https://docs.spring.io/spring-cloud-task/reference/features.html): `TaskExecution`, `TaskRepository`, lifecycle và xử lý lỗi.
- [Spring Cloud Data Flow — Task Scheduling](https://docs.spring.io/spring-cloud-dataflow/reference/feature-guides/batch/scheduling.html): lập lịch task qua các platform được hỗ trợ.
- [Spring Batch — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry trong chunk/step và phối hợp với transaction.

**Lưu ý phiên bản:** các trường Kubernetes và API scheduler cần được đối chiếu với cluster/deployer thực tế; cấu hình Java/SQL trong bài mang tính minh họa, không thay thế kiểm thử tích hợp theo version Spring Boot, Spring Cloud Task, Spring Batch, JDBC driver và cơ sở dữ liệu của dự án.
