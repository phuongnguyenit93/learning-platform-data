# Chọn leader election hay cơ chế điều phối tác vụ khác

## Mục tiêu và bối cảnh

Một ứng dụng Spring có ba replica, mỗi replica đều chứa cùng một phương thức `@Scheduled`. Nhóm phát triển muốn “chỉ chạy tác vụ một lần”, nên cân nhắc thêm leader election. Quyết định này chỉ đúng khi yêu cầu thật sự là cần một replica giữ vai trò chủ động. Nếu yêu cầu là không bỏ sót từng đơn hàng, chia việc cho nhiều worker hoặc tiếp tục một batch sau lỗi, cần một cơ chế quản lý công việc rõ hơn.

Trong module **SPRING_CLOUD_KUBERNETES**, leader election là một khả năng tùy chọn bên cạnh discovery, cấu hình, load balancing và theo dõi sức khỏe Pod. Bài này giúp chọn đúng khả năng cần triển khai, thay vì dùng một leader chung cho mọi tác vụ nền.

Sau bài học, bạn có thể:

- Phân biệt quyền lãnh đạo, quyền xử lý một công việc và tính duy nhất của tác động nghiệp vụ.
- Chọn giữa leader election, Job/CronJob, khóa cho từng lượt chạy, hàng đợi và cơ chế nhận việc trong database.
- Nhận ra nhu cầu scheduler có trạng thái, batch checkpoint hoặc workflow.
- Đánh giá tải, phục hồi, phân quyền và chi phí vận hành.
- Viết một quyết định kiến trúc có tiêu chí và bằng chứng kiểm chứng.

## 1. Đổi câu hỏi “chạy một lần” thành yêu cầu cụ thể

“Chạy một lần” có thể mang nhiều ý nghĩa:

| Ý định | Ví dụ | Phần cần kiểm soát |
| --- | --- | --- |
| Một bộ điều phối chủ động | Chỉ một replica duy trì phiên quét nguồn ngoài | Vai trò active/standby |
| Một lượt cho mỗi thời điểm lịch | Báo cáo lúc 02:00 mỗi ngày | Trigger, kỳ chạy và lịch bị lỡ |
| Một worker giữ một item tại một thời điểm | Xử lý từng đơn hàng đang chờ | Quyền sở hữu item và thời hạn |
| Không tạo tác động nghiệp vụ lặp | Gửi cùng yêu cầu đối soát nhiều lần vẫn chỉ ghi một kết quả | Idempotency, transaction hoặc fencing |
| Tiếp tục từ tiến độ đã lưu | Batch đọc hàng triệu bản ghi | Checkpoint, trạng thái bước và dữ liệu đầu vào |
| Một thứ tự theo thực thể | Các thao tác của cùng tài khoản không đảo thứ tự | Partition/key và kiểm soát phiên bản |

Các ý định có thể cùng tồn tại. Một leader có thể điều phối nhiều worker; một CronJob có thể chạy một Spring Batch job; worker từ hàng đợi vẫn cần idempotency.

Trước khi chọn công nghệ, trả lời:

1. Đơn vị công việc có mã định danh ổn định không?
2. Công việc đến từ lịch, sự kiện, bảng dữ liệu hay một vòng quét liên tục?
3. Mỗi item có thể xử lý độc lập không? Cần thứ tự trong phạm vi nào?
4. Khi worker chết, ai biết item nào còn dở và ai nhận lại?
5. Cho phép thử lại, bỏ qua một kỳ lịch hoặc xử lý trùng đến mức nào?
6. Tác động ngoài database có hỗ trợ idempotency hoặc kiểm soát phiên bản không?
7. Thời gian tiếp quản và tuổi backlog tối đa là bao nhiêu?
8. Hệ thống đã vận hành database, broker hoặc scheduler nào?
9. Quyền sở hữu cần có phạm vi một namespace, một cluster hay nhiều cluster?

Đừng dùng số replica làm câu trả lời cho các câu hỏi trên.

## 2. Ba ranh giới bảo đảm phải phân biệt

### 2.1. Leader election chọn vai trò chủ động

Trong mô hình active/standby, nhiều ứng viên phối hợp để một ứng viên giữ vai trò leader. Ứng dụng cần dùng sự kiện hoặc trạng thái leadership để bắt đầu và dừng phần công việc tương ứng.

Cơ chế Fabric8 truyền thống được tài liệu Spring Cloud Kubernetes 3.3 mô tả dùng ConfigMap và các sự kiện `OnGrantedEvent`, `OnRevokedEvent`. Xem [Leader Election nhánh 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html).

Việc có dependency leader không tự làm mọi `@Scheduled`, HTTP endpoint hoặc consumer trở thành “chỉ chạy trên leader”. Phần thực thi phải được nối với lifecycle của leadership.

### 2.2. Nhận việc xác định worker nào đang sở hữu một item

Một hàng đợi hoặc bảng công việc có thể gắn trạng thái với từng item:

~~~text
READY → RUNNING → DONE
           ↓
       RETRY / FAILED
~~~

Cơ chế này trả lời câu hỏi khác: item nào chưa hoàn tất, ai đang làm và khi nào được nhận lại?

Leader election đơn thuần không tạo danh sách READY/RUNNING/DONE cho nghiệp vụ. Nếu cursor, danh sách item đã phát hoặc tiến độ chỉ nằm trong RAM leader cũ, leader mới không tự khôi phục chúng.

### 2.3. Tác động duy nhất cần được bảo vệ ở tài nguyên đích

Ví dụ một worker gọi API ngoài thành công rồi chết trước khi ghi DONE. Worker tiếp theo không biết lần gọi đó đã thành công và có thể gọi lại.

Không thể suy từ một bản ghi khóa rằng tác động bên ngoài chỉ xuất hiện một lần. Tài liệu leader election của Kubernetes cũng phân biệt election với bảo đảm fencing; xem [ghi chú về fencing của client-go](https://pkg.go.dev/k8s.io/client-go/tools/leaderelection). Đây là nguyên lý để xem xét, không có nghĩa ứng dụng Spring trong bài dùng client-go.

Phải chỉ rõ ranh giới của lời hứa “exactly once”: ghi trong một transaction database, xử lý message trong một hệ thống hay tác động sang API ngoài. Các ranh giới đó không tự nối thành một transaction toàn cục.

## 3. Tình huống leader cũ vẫn tiếp tục làm việc

Một tình huống cần kiểm thử:

~~~text
t0: Pod A đang giữ leadership và bắt đầu một đơn vị việc
t1: A không còn liên lạc được với nơi phối hợp hoặc bị pause dài
t2: Theo điều kiện của cơ chế đang dùng, Pod B nhận leadership
t3: A tiếp tục chạy phần việc cũ hoặc request trước đó vẫn hoàn tất
~~~

Không được giả định Pod A đã bị hệ điều hành dừng tại t2. Ngay cả khi A đã biết mất leadership, thao tác mạng gửi trước đó có thể vẫn hoàn tất.

Có ba lớp biện pháp khác nhau:

| Biện pháp | Giúp xử lý | Giới hạn |
| --- | --- | --- |
| Ngừng nhận việc mới khi mất leadership | Giảm việc phát sinh từ leader cũ | Không thu hồi tác động đã gửi |
| Idempotency key ổn định theo nghiệp vụ | Lần thử lại không tạo thêm tác động nếu đích hỗ trợ đúng hợp đồng | Phải định nghĩa key và thời hạn lưu kết quả |
| Fencing token hoặc version được đích kiểm tra | Đích từ chối thao tác của chủ sở hữu cũ | Đích phải thực sự kiểm tra token trong thao tác ghi |

Ví dụ key phù hợp: `reconcile:order-42:period-17`. Request ID riêng cho từng lần thử có thể khác nhau, nhưng idempotency key cho cùng một tác động phải ổn định.

Một token chỉ được ghi vào log không tạo fencing. Một bộ đếm tăng riêng trong từng Pod cũng không tạo thứ tự chung. Với Lease/ConfigMap, không tự coi `resourceVersion` là số tăng toàn cục có thể dùng làm fencing nghiệp vụ.

Nếu tài nguyên đích không hỗ trợ idempotency hoặc fencing, cần một thiết kế kiểm tra kết quả, đối soát hoặc giới hạn tác động phù hợp; giảm timeout của election không giải quyết ranh giới này.

## 4. Bảng lựa chọn theo nhu cầu chính

| Cơ chế | Phù hợp khi | Lưu việc/tiến độ ở đâu? | Điểm cần bổ sung |
| --- | --- | --- | --- |
| Spring Cloud Kubernetes leader election | Một vai trò điều phối liên tục cần active/standby | Ứng dụng phải tự lưu ngoài election | Dừng/tiếp quản, checkpoint, chống lặp |
| Kubernetes Job | Một lượt hữu hạn cần chạy đến khi hoàn tất | Job theo dõi trạng thái workload; tiến độ nghiệp vụ do ứng dụng lưu | Idempotency và restart/resume của tác vụ |
| Kubernetes CronJob | Công việc hữu hạn theo lịch, chấp nhận ngữ nghĩa lịch đã chọn | CronJob/Job và kho kết quả nghiệp vụ | Kỳ chạy, lịch lỡ, chống trùng và backfill |
| Khóa cho từng lượt `@Scheduled` | Giữ scheduler trong ứng dụng, chỉ cần ngăn một số lượt chạy chồng | Lock store, không mặc định có lịch sử item | TTL, skip/retry và idempotency |
| Queue với nhiều worker | Việc đến theo item/sự kiện, cần hấp thụ backlog và tăng worker | Broker cùng kho trạng thái/kết quả cần thiết | Ack, redelivery, retry và chống lặp |
| Bảng công việc với nhận quyền nguyên tử | Công việc đã nằm trong database, cần trạng thái và truy vấn theo item | Bảng công việc | Lease, version, retry, index và dọn dữ liệu |
| Scheduler phân tán có persistent store | Nhiều trigger, lịch động, misfire/recovery cần quản lý tập trung | Job store của scheduler | Hợp đồng thực thi và idempotency |
| Batch/workflow có trạng thái | Nhiều bước, checkpoint, chờ hoặc phục hồi phức tạp | Repository/lịch sử thực thi phù hợp | Thiết kế bước, tương tác ngoài và quản trị |

Một database hiện có có thể làm phương án nhận việc phù hợp ở giai đoạn đầu; điều đó không có nghĩa database luôn thay thế broker tốt hơn. Tương tự, có Kubernetes không có nghĩa mọi tác vụ đều cần leader trong ứng dụng.

Sơ đồ định hướng:

~~~mermaid
flowchart TD
    A[Định nghĩa đơn vị công việc và yêu cầu phục hồi] --> B{Đặc điểm chi phối?}
    B -->|Vai trò chủ động liên tục| C[Xem xét leader election]
    B -->|Lượt hữu hạn theo lịch| D[Job/CronJob hoặc persistent scheduler]
    B -->|Nhiều item độc lập| E[Queue hoặc bảng công việc]
    B -->|Nhiều bước và cần resume| F[Batch hoặc workflow có trạng thái]
    C --> G[Bảo vệ tác động và lưu tiến độ]
    D --> G
    E --> G
    F --> G
~~~

Các nhánh không loại trừ việc kết hợp, nhưng mỗi thành phần được thêm phải có trách nhiệm rõ ràng.

## 5. Khi nên dùng leader election của Spring Cloud Kubernetes

### 5.1. Trường hợp phù hợp

Ví dụ một hệ thống ngoài chỉ cho phép một phiên chủ động quét file. Ứng dụng có nhiều replica chờ dự phòng và cần:

- Chỉ một replica mở phiên quét tại một thời điểm theo thiết kế phối hợp.
- Khi replica đó không còn khả dụng, một replica khác có thể tiếp quản.
- Cursor hoặc danh sách file đã nhận được lưu bền vững.
- File có định danh để thử lại không tạo thêm công việc trùng.
- Có hành động dừng nhận việc mới khi leadership bị thu hồi.

Ở đây, leader giữ một **vai trò dài hạn**. Nó có thể phát item vào queue hoặc bảng công việc; việc xử lý item không nhất thiết phải chạy trên leader.

~~~text
Một leader quét nguồn
        → tạo task với business key duy nhất
        → nhiều worker nhận task
        → lưu kết quả và tiến độ
~~~

Cách tách này phù hợp khi ràng buộc chỉ nằm ở việc quét nguồn, còn xử lý từng item có thể song song.

### 5.2. Chốt implementation theo phiên bản

Không dùng một bộ cấu hình chung cho mọi bản:

| Mốc tài liệu | Cơ chế được mô tả | Điểm phải chốt |
| --- | --- | --- |
| Nhánh 3.3, Fabric8 truyền thống | ConfigMap, sự kiện Granted/Revoked của Spring Integration | Tên ConfigMap, namespace, role, candidate và quyền Pod/ConfigMap |
| Tài liệu hiển thị 5.1.0, lựa chọn native | Lease hoặc ConfigMap; StartLeading/StopLeading/NewLeader | Tính năng hỗ trợ, nhóm cấu hình, loại khóa và sự kiện tương ứng |

Xem [Leader Election](https://docs.spring.io/spring-cloud-kubernetes/reference/leader-election.html) cho lựa chọn native. Không suy rằng có lựa chọn mới thì implementation cũ đã bị xóa ngay ở mọi phiên bản.

Ví dụ tên nhóm cho cơ chế ConfigMap truyền thống:

~~~yaml
spring:
  cloud:
    kubernetes:
      leader:
        enabled: true
        namespace: tasks-lab
        config-map-name: source-scanner-leaders
        role: source-scanner
~~~

Đây là phần thể hiện quyết định về nhóm cạnh tranh, không phải manifest triển khai đầy đủ. Cần dependency, client, RBAC và xử lý lifecycle đúng phiên bản.

Cùng role nhưng khác namespace hoặc khác khóa tạo ra các nhóm phối hợp khác nhau. Hai cluster dùng API server độc lập cũng không trở thành một nhóm leader toàn cục chỉ vì cùng đặt tên ConfigMap.

### 5.3. Lifecycle phải điều khiển phần việc

Mã giả cho thiết kế, không phải API có sẵn:

~~~text
khi nhận leadership:
    cho phép nhận đơn vị việc mới

khi mất leadership:
    ngừng nhận đơn vị việc mới
    hủy phần có thể hủy an toàn
    hoàn tất hoặc đối soát phần đang dở theo hợp đồng

mỗi lần xử lý:
    kiểm tra còn được phép nhận việc
    nhận quyền xử lý item nếu hệ thống có claim
    thực hiện bằng idempotency key ổn định
    lưu tiến độ/kết quả theo điều kiện sở hữu hiện tại
~~~

Spring Integration cung cấp sự kiện và Context để ứng dụng phản ứng theo leadership; xem [Leadership Event Handling](https://docs.spring.io/spring-integration/reference/leadership-event-handling.html).

Không đặt một tác vụ dài vào listener rồi mặc định framework sẽ tự hủy nó khi mất leadership. Process chết cũng không có cơ hội xử lý sự kiện thu hồi. Cần thiết kế phục hồi không phụ thuộc duy nhất vào callback dừng êm.

### 5.4. Khi leader election không đủ hoặc không cần

Cần xem xét cơ chế khác nếu:

- Có hàng nghìn item độc lập nhưng chỉ leader được xử lý tất cả.
- Không có nơi lưu việc đang dở ngoài RAM.
- Nhu cầu chính là báo cáo theo lịch hữu hạn.
- Cần lịch sử theo từng execution, lịch bị lỡ hoặc backfill.
- Phạm vi độc quyền trải nhiều cluster nhưng khóa chỉ nằm trong từng cluster.
- Tác động đòi hỏi bảo đảm tại tài nguyên đích mà thiết kế chưa có.

Tăng số follower không tăng thông lượng của một luồng xử lý tuần tự trên leader.

## 6. Khi chọn Job hoặc CronJob

### 6.1. Tác vụ hữu hạn có điểm kết thúc rõ

Ví dụ báo cáo đối soát ban đêm đọc dữ liệu theo một kỳ, xuất kết quả rồi kết thúc. Kubernetes CronJob phù hợp để tạo Job theo lịch; không cần giữ ba JVM chạy cả ngày chỉ để chờ một lần chạy.

Manifest minh họa cho namespace lab đã tồn tại:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-reconciliation-report
  namespace: tasks-lab
spec:
  schedule: "0 2 * * *"
  timeZone: Asia/Ho_Chi_Minh
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 1800
      template:
        spec:
          automountServiceAccountToken: false
          restartPolicy: Never
          containers:
            - name: report
              image: registry.example.com/team/report-runner:1.0.0
              args:
                - "--task.mode=nightly-report"
              resources:
                requests:
                  cpu: 100m
                  memory: 256Mi
                limits:
                  cpu: "1"
                  memory: 512Mi
~~~

Image là chỗ thay bằng ứng dụng thực tế. Process phải thực hiện một lượt hữu hạn và thoát với mã kết quả phù hợp; một ứng dụng web chỉ khởi động server sẽ không tự hoàn tất Job.

`timeZone` cần được cluster hỗ trợ; trường này ổn định từ Kubernetes 1.27. Lịch sử Job không phải kho lịch sử nghiệp vụ đầy đủ. Xem [CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/).

### 6.2. Hiểu phạm vi của chính sách lịch

`Forbid` kiểm soát chạy chồng giữa các Job do **cùng CronJob** tạo. Nó không khóa mọi Job thủ công, CronJob khác hoặc ứng dụng khác cùng tác động dữ liệu.

`startingDeadlineSeconds` là cửa sổ chấp nhận bắt đầu trễ, không phải thời gian chạy tối đa. Thời gian chạy của Job được điều khiển riêng; xem [CronJob API](https://kubernetes.io/docs/reference/kubernetes-api/batch/cron-job-v1/).

Cần quyết định nghiệp vụ:

- Một kỳ bị lỡ có cần chạy bù không?
- Lượt chạy bù nhận kỳ dữ liệu từ tham số nào?
- Nếu hai lượt cùng nhắm một kỳ, hệ thống nhận biết bằng key nào?
- Lượt retry xử lý lại từ đầu hay từ checkpoint?

Không lấy thời điểm Pod khởi động làm định danh duy nhất của kỳ báo cáo, vì một lượt chạy trễ hoặc retry có thể xử lý dữ liệu của một kỳ trước.

### 6.3. Job không tự tạo tác động đúng một lần

Tài liệu Job nêu rằng ngay cả khi parallelism và completions đều bằng một, chương trình vẫn có thể được khởi động hai lần trong một số tình huống. Xem [Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/).

Vì vậy, báo cáo theo kỳ vẫn cần định danh như `report:tenant-7:period-17`, chính sách ghi đè/xuất bản kết quả và cách xử lý retry. CronJob chọn thời điểm tạo công việc; tính duy nhất của kết quả là hợp đồng ứng dụng.

## 7. Khi giữ @Scheduled và chỉ khóa từng lượt

### 7.1. Khóa theo tác vụ khác với bầu leader dài hạn

Nếu hệ thống đã có vài tác vụ ngắn theo lịch và mỗi lượt độc lập, có thể khóa theo tên tác vụ:

~~~text
Mỗi replica có lịch cục bộ
        → thử lấy khóa của tác vụ
        → replica lấy được khóa thực hiện lượt đó
        → replica khác bỏ qua hoặc xử lý theo chính sách đã chọn
~~~

Replica chạy lượt kế tiếp không nhất thiết là replica chạy lượt trước. Cơ chế này có thể đơn giản hơn việc duy trì một vai trò leader chung cho mọi tác vụ.

Spring `@Scheduled` tạo lịch cho các bean tương ứng; nó không tự phối hợp giữa các JVM. Xem [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).

### 7.2. Phải hiểu cách thư viện xử lý lượt không lấy được khóa

Ví dụ, ShedLock mô tả rằng lượt chạy ở node khác sẽ bị bỏ qua khi tác vụ đang được giữ khóa; nó không phải một distributed scheduler đầy đủ. Xem [tài liệu chính thức của ShedLock](https://github.com/lukas-krecan/ShedLock).

Điều này phù hợp với tác vụ quét có thể chạy lại ở lần sau, nhưng không tự đáp ứng yêu cầu “mọi lần kích hoạt đều phải được ghi nhận và xử lý”.

Những quyết định cần chốt:

- Mất lượt lịch có được chấp nhận không?
- Thời hạn khóa có thể hết trước tác vụ không?
- Có gia hạn khóa không, và mất gia hạn thì tác vụ phản ứng ra sao?
- Clock hoặc nguồn thời gian nào được provider sử dụng?
- Một key khóa có bao phủ đúng phạm vi nghiệp vụ không?
- Khi process chết, lần tiếp theo nhận lại công việc nào?

Đặt thời hạn khóa lớn chỉ làm tăng thời gian chờ sau sự cố; đặt quá nhỏ có thể khiến lượt cũ còn chạy khi lượt mới bắt đầu. Phải kiểm tra cả phía dừng công việc và phía bảo vệ tác động.

### 7.3. Khi không nên dừng ở giải pháp khóa

Khóa một phương thức không đủ nếu bạn cần lịch sử từng item, retry riêng từng item, backpressure, phân phối theo key hoặc trạng thái nhiều bước.

Không dùng một khóa toàn cục cho tất cả tác vụ chỉ để tránh thiết kế đơn vị công việc. Nó có thể tuần tự hóa những việc vốn độc lập và tạo backlog không cần thiết.

## 8. Khi chọn queue và nhiều worker

### 8.1. Đơn vị công việc đã rõ

Ví dụ mỗi sự kiện `OrderReadyForReconciliation` tương ứng một item có thể xử lý độc lập. Queue cho phép nhiều worker cùng tiêu thụ thay vì chỉ leader thực hiện mọi việc:

~~~text
Producer → queue bền vững → worker A
                        → worker B
                        → worker C
~~~

Mô hình work queue phân phối tác vụ cho nhiều worker được minh họa trong [RabbitMQ Work Queues với Spring AMQP](https://www.rabbitmq.com/tutorials/tutorial-two-spring-amqp). Đây là một ví dụ nền tảng, không bắt buộc dự án phải chọn RabbitMQ nếu đã có broker phù hợp.

Thường không cần thêm leader election bao ngoài toàn bộ nhóm consumer. Làm vậy có thể vô hiệu hóa chính khả năng chia việc của broker.

### 8.2. Ack không xóa cửa sổ xử lý trùng

Luồng xử lý điển hình:

1. Worker nhận item có business key ổn định.
2. Kiểm tra hoặc thiết lập quyền xử lý theo hợp đồng.
3. Thực hiện và lưu kết quả.
4. Ack/commit vị trí sau mốc bền vững phù hợp.

Nếu worker chết sau bước 3 nhưng trước bước 4, item có thể được giao lại. Nếu ack quá sớm, process chết có thể làm mất phần việc chưa được lưu.

RabbitMQ phân biệt consumer acknowledgement với publisher confirm; xác nhận một message đã được broker nhận không đồng nghĩa tác vụ nghiệp vụ đã hoàn tất. Xem [Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms).

Do đó, cần phối hợp:

- Idempotency theo business key.
- Chính sách retry có giới hạn và độ trễ.
- Nơi xử lý item không thể hoàn tất sau nhiều lần thử.
- Giới hạn số việc đang giữ để tránh một worker ôm quá nhiều.
- Quan sát backlog, tuổi item cũ nhất và số lần giao lại.

Nếu vừa ghi database vừa phát sự kiện, phải xem xét cửa sổ giữa hai thao tác. Có thể dùng outbox hoặc một thiết kế giao dịch phù hợp; leader election không tự làm hai hệ thống commit cùng nhau.

### 8.3. Chọn phạm vi song song và thứ tự

Không phải mọi item đều độc lập. Nếu thao tác của cùng một đơn hàng cần giữ thứ tự, hãy chọn key phân vùng hoặc cơ chế điều phối theo thực thể mà broker và ứng dụng thực sự hỗ trợ.

Một khóa toàn hệ thống có thể giữ thứ tự bằng cách loại bỏ mọi song song, nhưng thường lớn hơn phạm vi cần bảo vệ. Hãy phân biệt:

- Thứ tự toàn cục.
- Thứ tự trong một tenant/tài khoản/đơn hàng.
- Chỉ yêu cầu kết quả cuối thỏa điều kiện version, không cần thứ tự xử lý tuyệt đối.

Nhiều consumer và nhiều replica tự thân không bảo đảm FIFO ở mức kết quả nghiệp vụ.

## 9. Khi chọn bảng công việc trong database

### 9.1. Tận dụng nơi đã lưu công việc

Nếu các item đã nằm trong database và nhóm chưa vận hành broker, nhận việc bằng transaction có thể phù hợp. Thay vì bầu một leader toàn cục, mỗi worker nhận một tập item khác nhau.

Phần dưới minh họa bằng **PostgreSQL**, không phải SQL dùng nguyên trạng cho mọi database. Các tham số dạng `:worker_id` được application layer bind, chẳng hạn qua NamedParameterJdbcTemplate.

Schema giản lược:

~~~sql
CREATE TABLE task_work (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    business_key   text NOT NULL UNIQUE,
    status         text NOT NULL DEFAULT 'READY'
                   CHECK (status IN ('READY', 'RUNNING', 'DONE', 'FAILED')),
    available_at   timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    owner_id       text,
    lease_until    timestamptz,
    claim_version  bigint NOT NULL DEFAULT 0,
    attempts       integer NOT NULL DEFAULT 0,
    completed_at   timestamptz
);
~~~

`business_key` duy nhất giúp tránh tạo hai bản ghi cho cùng đơn vị việc theo hợp đồng đã định. Nó không tự bảo vệ một API ngoài được gọi hai lần.

### 9.2. Nhận việc nguyên tử

~~~sql
WITH picked AS (
    SELECT id
    FROM task_work
    WHERE available_at <= CURRENT_TIMESTAMP
      AND (
          status = 'READY'
          OR (
              status = 'RUNNING'
              AND lease_until < CURRENT_TIMESTAMP
          )
      )
    ORDER BY id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE task_work AS task
SET status = 'RUNNING',
    owner_id = :worker_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    claim_version = task.claim_version + 1,
    attempts = task.attempts + 1
FROM picked
WHERE task.id = picked.id
RETURNING task.id,
          task.business_key,
          task.owner_id,
          task.claim_version,
          task.lease_until;
~~~

Chạy thao tác nhận việc trong transaction ngắn và commit quyền sở hữu trước khi làm tác vụ dài. Không giữ row lock trong một transaction mở suốt lúc gọi mạng.

`SKIP LOCKED` cho phép bỏ qua hàng đang bị khóa, phù hợp một số bảng dạng queue nhưng không cung cấp ảnh chụp nhất quán cho truy vấn tổng quát. Xem [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html).

`ORDER BY id` hỗ trợ cách chọn item trong ví dụ; nó không bảo đảm thứ tự hoàn tất khi nhiều worker chạy song song.

### 9.3. Gia hạn và hoàn tất theo đúng lần nhận quyền

Nếu tác vụ cần lâu hơn thời hạn nhận quyền, có thể dùng heartbeat có điều kiện:

~~~sql
UPDATE task_work
SET lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds'
WHERE id = :task_id
  AND owner_id = :worker_id
  AND claim_version = :claim_version
  AND status = 'RUNNING'
  AND lease_until > CURRENT_TIMESTAMP;
~~~

Nếu số hàng cập nhật bằng không, worker không được tự cho rằng vẫn sở hữu item. Cần ngừng nhận thêm việc và xử lý phần đang dở theo hợp đồng.

Hoàn tất cũng phải xác minh phiên nhận quyền:

~~~sql
UPDATE task_work
SET status = 'DONE',
    completed_at = CURRENT_TIMESTAMP,
    lease_until = NULL
WHERE id = :task_id
  AND owner_id = :worker_id
  AND claim_version = :claim_version
  AND status = 'RUNNING'
  AND lease_until > CURRENT_TIMESTAMP;
~~~

Số hàng cập nhật phải được kiểm tra. Điều kiện version ngăn worker cũ đánh dấu DONE cho một lần nhận quyền mới đã thay thế nó.

Tuy nhiên, query này chỉ kiểm soát cập nhật bản ghi task. Nó không hủy một HTTP request đã gửi trước đó. Nếu tài nguyên ngoài không kiểm tra version, vẫn phải dùng idempotency hoặc cơ chế đối soát phù hợp.

Nếu kết quả nghiệp vụ cùng nằm trong database, việc xác minh quyền, ghi kết quả và đổi trạng thái cần được thiết kế trong cùng transaction ngắn với lock/constraint phù hợp. Không ghi kết quả ở một transaction rồi chỉ kiểm tra quyền ở transaction khác mà coi là đã bảo vệ toàn bộ tác động.

### 9.4. Đây chưa phải một task engine hoàn chỉnh

Ví dụ còn cần được hoàn thiện theo yêu cầu thật:

- Index và kế hoạch truy vấn theo tải.
- Backoff, giới hạn attempts và trạng thái thất bại cuối.
- Xử lý item bị kẹt, gia hạn quá hạn hoặc liên tục bị nhận lại.
- Theo dõi công bằng, starvation và tuổi item.
- Retention/archive để bảng không tăng vô hạn.
- Cách xử lý khi database failover hoặc transaction có kết quả chưa rõ.
- Kiểm thử việc worker cũ tiếp tục sau khi lease hết hạn.

Dùng thời gian database giúp tập trung nguồn thời gian trong ví dụ, nhưng không loại bỏ mọi vấn đề về pause, độ trễ và tác vụ ngoài. Các transaction gia hạn/hoàn tất phải ngắn; không dựa vào một transaction đã mở từ lâu để suy ra thời gian hiện tại.

## 10. Khi cần scheduler có trạng thái, batch hoặc workflow

### 10.1. Scheduler phân tán quản lý lịch rõ hơn

Nếu yêu cầu có nhiều lịch động, trigger lưu bền vững, chính sách misfire và quản trị execution, một scheduler có persistent store có thể phù hợp hơn việc tự xây một vòng leader cộng nhiều `@Scheduled`.

Quartz clustering với JDBC JobStore dùng database dùng chung để phối hợp các node và có hành vi recovery theo cấu hình job. Không phải mọi JobStore hoặc mọi cách khởi tạo Quartz đều tạo thành cluster. Xem [Quartz JDBC JobStore Clustering](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/configuration/ConfigJDBCJobStoreClustering.html).

Điều scheduler giúp quản lý là lịch và lượt thực thi theo hợp đồng của nó. Nó không làm một tác động ra hệ thống ngoài tự trở thành không thể lặp.

Cần so sánh cả chi phí vận hành: schema/job store, cấu hình các node, nâng cấp, quan sát misfire và cách xử lý job được chạy lại.

### 10.2. Batch cần tiến độ và định danh lượt chạy

Một batch có thể gồm nhiều step, đọc/ghi theo chunk và lưu checkpoint. Spring Batch cung cấp mô hình Job/Step và JobRepository để lưu metadata thực thi. Xem [The Domain Language of Batch, nhánh 5.2](https://docs.spring.io/spring-batch/reference/5.2/domain.html).

Phân biệt:

- Kubernetes Job quản lý workload hữu hạn.
- Spring Batch Job biểu diễn quy trình batch trong ứng dụng.
- Scheduler hoặc CronJob có thể là thành phần khởi chạy Spring Batch Job.

Ba khái niệm có thể kết hợp; không nhất thiết chọn một để loại bỏ hai khái niệm còn lại.

Khi cần chạy lại cùng kỳ dữ liệu, định danh JobInstance và tham số phải phù hợp với ý định restart. Tạo một định danh hoàn toàn mới cho mỗi retry có thể làm hệ thống bắt đầu lại thay vì tiếp tục trạng thái cũ.

### 10.3. Workflow cho tiến trình dài và nhiều chặng chờ

Nếu quy trình kéo dài qua nhiều ngày, chờ tín hiệu, gọi nhiều dịch vụ và có nhánh bù trừ, cần đánh giá một cơ chế workflow lưu trạng thái/lịch sử phù hợp.

Một leader giữ state machine trong RAM không tự bảo đảm quy trình còn tiếp tục đúng sau khi Pod bị thay. Một event listener cũng không tự có lịch sử đủ để giải thích toàn bộ tiến trình.

Dù chọn workflow, mỗi bước có tác động vẫn cần chính sách thử lại và chống lặp. “Compensation” phải là hành động nghiệp vụ được thiết kế; nó không tự đảo ngược mọi tác động ngoài.

## 11. Đánh giá thông lượng và thời gian phục hồi

### 11.1. Đừng nhầm số replica với số đơn vị thực thi

Giả sử công việc đến trung bình 100 item/giây và mỗi item chiếm một slot xử lý trong 50 ms. Nếu leader xử lý tuần tự từng item, thông lượng lý thuyết chỉ khoảng:

~~~text
1 / 0,05 giây = 20 item/giây
~~~

Thêm năm follower không làm luồng tuần tự đó trở thành 120 item/giây.

Nếu có tám slot thực thi độc lập, giới hạn lý thuyết trong giả định giản lược là:

~~~text
8 / 0,05 giây = 160 item/giây
~~~

Đây là phép tính minh họa, chưa tính I/O dùng chung, database, rate limit, thời gian chờ, retry và tải đỉnh. Nó cho thấy cần đo đường thực thi thực tế, không chỉ số Pod.

Leader vẫn có thể phù hợp nếu phần bắt buộc đơn luồng chỉ là lấy dữ liệu nguồn, sau đó item được phát cho các worker. Cần chứng minh bộ điều phối đủ nhanh và việc phát item không bị mất hoặc trùng ngoài hợp đồng.

### 11.2. Tiếp quản xong chưa có nghĩa backlog đã hồi phục

Phân tách thời gian:

~~~text
Tạm dừng công việc mới
    → phát hiện tình trạng
    → có chủ sở hữu/worker mới
    → khôi phục checkpoint hoặc nhận lại item
    → công việc đầu tiên tiếp tục
    → xử lý hết backlog phát sinh
~~~

Mỗi cơ chế có các mốc khác nhau. Không lấy một log “new leader” làm bằng chứng toàn bộ nghiệp vụ đã phục hồi.

Ví dụ giản lược: nguồn tiếp tục tạo 100 item/giây trong 30 giây gián đoạn, nên backlog tăng 3.000 item. Khi hệ thống phục hồi với khả năng xử lý 160 item/giây và nguồn vẫn thêm 100 item/giây, phần công suất để xóa backlog chỉ còn 60 item/giây. Thời gian xóa backlog lý thuyết là 50 giây sau khi xử lý đã tiếp tục.

Do đó, tiêu chí kiến trúc nên có cả thời gian tiếp quản lẫn tuổi item hoặc độ trễ hoàn tất.

### 11.3. Xác định điểm phụ thuộc khi điều phối không truy cập được

| Nơi phối hợp | Điều phải kiểm tra khi gián đoạn |
| --- | --- |
| Kubernetes API | Khả năng giữ/nhận leadership theo implementation; quyền và trạng thái ứng viên |
| Database | Transaction nhận việc, heartbeat, commit kết quả và các item đang chạy |
| Broker | Delivery, ack/confirm, redelivery sau reconnect và backlog |
| Persistent scheduler | Lịch mới, job đang chạy, phát hiện node lỗi và recovery |
| Hệ thống đích | Kết quả request chưa rõ, idempotency và đối soát |

Với leader election, hành vi khi mất API phụ thuộc implementation và cấu hình; không áp một công thức Lease cho cơ chế ConfigMap truyền thống. Với queue hoặc database, cũng phải xem những worker đã có việc trong tay sẽ tiếp tục hay dừng theo điều kiện nào.

Nếu Kubernetes control plane tạm thời không tạo được Job mới, một Pod đang chạy vẫn có thể tiếp tục xử lý nếu các phụ thuộc của nó còn hoạt động. Tách khả năng khởi tạo/điều phối mới khỏi khả năng thực thi phần việc hiện tại.

## 12. Quyết định theo ba tình huống thực tế

### 12.1. Quét nguồn có giới hạn một phiên chủ động

**Yêu cầu:** Một nguồn file chỉ cho phép một phiên quét. Cần kiểm tra thường xuyên, nhiều replica chờ dự phòng và có thể nhận lại file sau lỗi.

**Phương án có cơ sở:** Leader election cho vai trò quét; cursor dùng chung hoặc cơ chế quét lại an toàn; file được chuyển thành item có business key duy nhất. Phần xử lý file có thể chạy ở nhiều worker.

**Điểm phải chứng minh:** Sau pause hoặc chuyển leader, file không bị bỏ sót; thử lại không tạo thêm kết quả trùng; leader cũ không tiếp tục phát việc trái hợp đồng.

**Điều kiện xem xét lại:** Nguồn ngoài hỗ trợ phân vùng hoặc nhiều phiên độc lập. Khi đó leader toàn cục có thể không còn cần thiết.

### 12.2. Đối soát nhiều đơn hàng độc lập đã nằm trong database

**Yêu cầu:** Mỗi đơn hàng có một bản ghi cần xử lý; phải biết trạng thái từng item và tăng thông lượng bằng nhiều worker. Hiện chưa có broker trong hệ thống.

**Phương án có cơ sở:** Nhận việc nguyên tử trong database với version/lease, retry theo item và bảo vệ tác động. Không chỉ cấp quyền xử lý cho một leader toàn hệ thống.

**Điểm phải chứng minh:** Hai worker không hoàn tất trái phép cùng một phiên nhận quyền; item hết hạn được nhận lại; worker cũ không làm hỏng kết quả mới; backlog được xử lý trong mục tiêu.

**Điều kiện xem xét lại:** Tải polling quá lớn, cần fan-out sự kiện, nhiều hệ thống tiêu thụ hoặc database trở thành điểm nghẽn. Lúc đó đánh giá queue và chiến lược phát sự kiện đáng tin cậy.

### 12.3. Báo cáo theo kỳ cần chạy lại và có nhiều bước

**Yêu cầu:** Báo cáo ban đêm có kỳ dữ liệu cụ thể, có thể chạy bù và tiếp tục từ tiến độ đã lưu.

**Phương án có cơ sở:** CronJob hoặc scheduler tạo lượt chạy; ứng dụng batch quản lý các bước và checkpoint. Kỳ dữ liệu tham gia định danh lượt nghiệp vụ.

**Điểm phải chứng minh:** Retry và backfill xử lý đúng kỳ; kết quả không bị xuất bản hai lần ngoài chính sách; restart dùng được trạng thái hợp lệ.

**Điều kiện xem xét lại:** Lịch động rất nhiều, misfire phức tạp hoặc có chờ tín hiệu dài giữa các dịch vụ. Đánh giá scheduler/workflow có trạng thái thay vì tiếp tục thêm điều kiện vào một vòng leader.

## 13. Mẫu quyết định kiến trúc có thể kiểm chứng

Ví dụ dưới đây là **đề xuất cho tình huống đối soát từng đơn hàng**, không phải quyết định áp dụng cho mọi tác vụ của module.

~~~text
ADR: Điều phối các item đối soát đơn hàng

Trạng thái:
  Đề xuất để thực hiện thử nghiệm.

Bối cảnh:
  Item đã được lưu trong database.
  Nhiều item xử lý độc lập.
  Cần lịch sử và retry theo từng item.
  Chưa có broker trong môi trường hiện tại.

Quyết định dự kiến:
  Dùng thao tác nhận việc nguyên tử trong database.
  Mỗi lần nhận quyền có owner và claim_version.
  Lưu business key duy nhất và bảo vệ tác động khi thử lại.
  Không dùng một leader toàn cục để tuần tự hóa toàn bộ worker.

Các phương án đã cân nhắc:
  Leader election:
    Phù hợp nếu cần một bộ điều phối chủ động,
    nhưng không cung cấp trạng thái từng item cho nhu cầu này.
  Queue:
    Có thể phù hợp với mô hình item và backlog,
    cần đánh giá thêm chi phí vận hành/phát sự kiện đáng tin cậy.
  CronJob:
    Phù hợp để khởi chạy lượt hữu hạn theo lịch,
    không thay thế quyền sở hữu từng item đang xử lý.

Hệ quả cần chấp nhận:
  Database phải chịu tải nhận việc và heartbeat.
  Phải có index, retention, retry và xử lý item kẹt.
  Version trong task table không tự bảo vệ API ngoài.

Bằng chứng cần có:
  Thử nhiều worker đồng thời.
  Thử hết hạn nhận quyền rồi worker cũ tiếp tục.
  Thử tác động thành công nhưng mất cập nhật trạng thái.
  Đo thông lượng, tuổi backlog và thời gian nhận lại item.

Điều kiện xem xét lại:
  Tải hoặc mô hình tiêu thụ vượt khả năng đã đo.
  Cần phối hợp nhiều cluster.
  Xuất hiện quy trình nhiều bước có chờ dài.
~~~

Một ADR đủ hữu ích phải nêu cả điều kiện thay đổi quyết định. Không dùng một điểm số tổng hợp mơ hồ để che việc chưa kiểm tra ranh giới chống lặp hoặc phục hồi.

Nếu yêu cầu “không tạo thêm tác động ngoài” chưa có cơ chế đáp ứng, đó là điểm chưa được giải quyết của thiết kế. Không đánh dấu đã đạt chỉ vì công nghệ được chọn có từ “distributed” hoặc “HA”.

## 14. Phân quyền, cấu hình và sức khỏe trong Spring Cloud Kubernetes

### 14.1. Chỉ đưa thêm khả năng cần cho quyết định

| Khả năng trong module | Vai trò có thể có | Không tự cung cấp |
| --- | --- | --- |
| DiscoveryClient | Tìm instance của dịch vụ | Quyền sở hữu một item |
| Spring Cloud LoadBalancer | Chọn nơi gửi request | Chống lặp tác động của retry |
| ConfigMap/Secret | Cấp cấu hình và credential | Lịch sử tác vụ hoặc hàng đợi nghiệp vụ |
| Configuration Watcher | Phát hiện/thông báo cập nhật cấu hình theo thiết kế | Điều phối mọi tác vụ nền của ứng dụng |
| Health/probe | Quan sát khả năng sẵn sàng và điều kiện sống | Chứng nhận toàn bộ việc đã hoàn tất duy nhất |
| Leader election | Chọn vai trò chủ động | Checkpoint, backlog và fencing ở đích |

Không dùng ConfigMap như một hàng đợi tự chế chỉ vì đã có quyền cập nhật ConfigMap. Kubernetes API phục vụ trạng thái và điều phối tài nguyên; hợp đồng nhận việc, retry và lưu kết quả vẫn phải được thiết kế.

### 14.2. Quyền và phạm vi phối hợp

Với leader election, xác định đúng loại khóa và những thao tác client thực sự cần trong namespace được chọn. Cơ chế dùng Lease và cơ chế dùng ConfigMap có API group khác nhau; không cấp một bộ quyền rộng rồi mặc định đã giải quyết đúng.

Với CronJob không gọi Kubernetes API từ bên trong ứng dụng, container có thể không cần token ServiceAccount. Với queue hoặc database, quyền truy cập nguồn công việc được quản lý theo broker/database; không tự thêm quyền Kubernetes cho worker nếu không cần.

Không đặt chung khóa leader của nhiều nhiệm vụ không liên quan chỉ để giảm số resource. Ngược lại, nếu cùng một nhiệm vụ vô tình dùng hai tên khóa hoặc hai namespace khác nhau, nó có thể hình thành hai nhóm điều phối độc lập.

### 14.3. Cấu hình điều phối là một phần của rollout

Thay đổi role, tên khóa, namespace, thời hạn, queue name hoặc chiến lược nhận việc có thể thay đổi nhóm sở hữu công việc.

Khi rollout, cần biết:

- Replica cũ và mới có còn cùng giao thức phối hợp không?
- Có giai đoạn hai nhóm khác nhau cùng tác động một tập dữ liệu không?
- Schema hoặc token của bản mới có được bản cũ hiểu đúng không?
- Việc quay lại image có cần khôi phục cấu hình hoặc trạng thái không?

Một lần refresh ConfigMap không mặc định tái tạo mọi client, scheduler hoặc initiator. Thay đổi ảnh hưởng lifecycle phải dùng cơ chế phiên bản đó hỗ trợ và được kiểm chứng.

### 14.4. Health cần phản ánh đúng vai trò

Không dùng điều kiện “đã là leader” làm readiness chung cho mọi replica chờ dự phòng mà chưa xem xét yêu cầu của implementation. Một follower có thể sẵn sàng tham gia tiếp quản dù chưa đang xử lý vai trò chủ động.

Tách ba tín hiệu khi quan sát:

1. Process/Pod có khả năng chạy không?
2. Replica có được phép nhận việc mới trong vai trò hiện tại không?
3. Công việc nghiệp vụ có đang hoàn tất trong mục tiêu không?

Một nhóm Pod đều Ready nhưng backlog tăng không ngừng vẫn là một vấn đề vận hành.

## 15. Kế hoạch thử nghiệm trước khi chấp nhận quyết định

### 15.1. Kiểm tra cửa sổ lỗi có ý nghĩa

| Tình huống lab | Điều cần quan sát | Bằng chứng đạt theo thiết kế |
| --- | --- | --- |
| Worker chết sau nhận quyền, trước tác động | Thời gian item được nhận lại | Item không bị bỏ quên vô hạn |
| Worker cũ pause quá thời hạn rồi tiếp tục | Version/ownership tại nơi ghi | Cập nhật stale bị từ chối đúng phạm vi |
| Tác động ngoài thành công, chưa ghi DONE hoặc ack | Lần thử lại và kết quả ở đích | Không tạo thêm tác động ngoài hợp đồng |
| Mất nơi phối hợp nhưng worker còn chạy | Hành vi tiếp tục/dừng và khả năng nhận việc mới | Đúng chính sách đã mô tả cho implementation |
| Hai trigger cùng business key | Constraint/idempotency và kết quả | Không xuất bản kết quả trùng ngoài chính sách |
| Nhiều cluster cùng hoạt động | Phạm vi khóa hoặc phân vùng quyền sở hữu | Không có hai chủ sở hữu ngoài thiết kế |
| Một item lỗi liên tục | Retry/backoff và trạng thái cuối | Không chặn mọi item khác, có đường xử lý rõ |
| Đổi image/cấu hình khi còn việc | Khả năng tương thích giao thức và tiếp quản | Trạng thái chuyển tiếp có thể giải thích và phục hồi |

Không dừng ở thử xóa Pod bình thường. Dừng êm có thể chạy cleanup, còn process chết đột ngột hoặc request có kết quả chưa rõ sẽ bộc lộ ranh giới khác.

Với leader election, đếm sự kiện granted/revoked giúp chẩn đoán nhưng không thay thế việc đếm tác động nghiệp vụ. Với queue, số message được ack cũng cần được liên kết với kết quả bền vững theo hợp đồng.

### 15.2. Ghi các định danh phù hợp

Log nên nối được:

~~~text
work key
    → attempt hoặc execution ID
    → owner/Pod và nhóm điều phối
    → claim version hoặc phiên leadership liên quan
    → idempotency key của tác động
    → kết quả và checkpoint
~~~

Dùng mã không nhạy cảm hoặc cách biểu diễn phù hợp với dữ liệu hệ thống. Request ID cho từng lần thử cần được phân biệt với business key của công việc.

Metric nên thể hiện số hoàn tất, retry, tuổi backlog, thời gian nhận lại và tần suất đổi leader nếu dùng election. Tránh đưa từng work key vào metric label không giới hạn; chi tiết theo item phù hợp hơn trong log hoặc kho trạng thái.

### 15.3. Đặt điều kiện chấp nhận trước khi chạy

Ví dụ điều kiện cần điền bằng số đo và hợp đồng thật:

- Tối đa bao lâu không nhận được việc mới sau sự cố?
- Item READY lâu nhất được phép chờ bao lâu?
- Một item có thể được thử bao nhiêu lần và sẽ đi đâu khi vượt ngưỡng?
- Thử lại cùng business key tạo ra kết quả nào?
- Sau khi owner cũ tiếp tục, thao tác nào bị chặn và ở đâu?
- Người vận hành phát hiện, đối soát và phục hồi tình huống chưa rõ kết quả bằng cách nào?

Nếu đích không hỗ trợ cơ chế cần thiết, phải sửa hợp đồng hoặc kiến trúc. Không hạ tiêu chí thành “chỉ có một dòng log leader” để đạt thử nghiệm.

## 16. Bài tập ra quyết định và tiêu chí hoàn thành

Chọn một tác vụ nền thật hoặc dùng ba tác vụ sau:

1. Quét một nguồn file chỉ cho phép một phiên chủ động.
2. Xử lý nhiều item độc lập đã có trong database.
3. Tạo báo cáo theo kỳ với nhu cầu chạy lại.

Với mỗi tác vụ:

- Viết đơn vị công việc, trigger, phạm vi thứ tự và chính sách thử lại.
- Chọn tối thiểu hai phương án để so sánh.
- Chỉ rõ nơi lưu trạng thái và nơi bảo vệ tác động nghiệp vụ.
- Mô tả một cửa sổ lỗi mà lựa chọn ban đầu chưa giải quyết.
- Thiết kế phép thử cho tình huống đó.
- Ghi quyết định tạm thời, điều kiện chấp nhận và điều kiện xem xét lại.

Hoàn thành bài khi giải thích được vì sao một cơ chế phù hợp với yêu cầu cụ thể, đồng thời nêu đúng giới hạn của nó. Leader election là lựa chọn hợp lý cho một vai trò chủ động cần dự phòng; công việc có lịch, backlog, trạng thái từng item hoặc checkpoint phải được giao cho những cơ chế thực sự quản lý các phần đó. Tác động nghiệp vụ vẫn cần hợp đồng chống lặp và phục hồi ở đúng ranh giới.
