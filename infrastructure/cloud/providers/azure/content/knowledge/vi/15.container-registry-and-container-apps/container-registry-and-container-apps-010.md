# Scale theo sự kiện với KEDA trong Container Apps

Một hệ thống xử lý hóa đơn có thể gần như không có việc vào ban đêm nhưng nhận hàng nghìn yêu cầu trong vài phút khi ứng dụng bán hàng chốt đơn. Nếu luôn duy trì nhiều container, doanh nghiệp trả tiền cho tài nguyên ít được sử dụng; nếu chỉ chạy một container, hàng đợi sẽ ùn tắc khi có đợt tăng tải. **Azure Container Apps** hỗ trợ tăng hoặc giảm số bản sao ứng dụng (**replica**) dựa trên HTTP hoặc tín hiệu từ hàng đợi, luồng sự kiện và các nguồn dữ liệu khác nhờ khả năng autoscaling tích hợp **KEDA (Kubernetes Event-driven Autoscaling)**.

Ví dụ: người dùng tải PDF lên Blob Storage, hệ thống phát sự kiện qua Event Grid và tạo thông điệp trong **Azure Service Bus Queue**. Một worker Container Apps đọc hàng đợi, kiểm tra tệp, trích xuất nội dung và lưu kết quả. Khi queue có nhiều thông điệp, scaler tăng replicas; khi hết việc, replicas có thể giảm về 0 nếu cấu hình và loại rule cho phép.

Bài thuộc chương **Container Registry và Container Apps** trong lộ trình Microsoft Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo đến tính toán, lưu trữ, dữ liệu, giám sát, bảo vệ và kiểm soát chi phí. Trọng tâm là thiết kế **hành vi autoscaling đáp ứng SLO và tính đúng đắn**, không chỉ chọn một ngưỡng queue.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Azure Container Apps, KEDA, nguồn sự kiện, scale rule và replica.
2. So sánh HTTP autoscaling, custom event-driven scaling và Container Apps Jobs.
3. Thiết kế worker dùng Azure Service Bus hoặc Azure Queue Storage làm nguồn tải.
4. Hiểu minReplicas, maxReplicas, scale-to-zero, cold start và ngưỡng backlog.
5. Cấu hình scale rule và kiểm tra revision/replica bằng Azure portal và CLI.
6. Thiết kế consumer an toàn trước retry, duplicate, lock timeout và scale-in.
7. Sử dụng managed identity, RBAC, ACR, secret và private networking.
8. Giám sát SLA, backlog, throughput, chi phí và xử lý các lỗi scaling phổ biến.

## 1. KEDA giải quyết vấn đề gì?

**KEDA** là cơ chế autoscaling theo tín hiệu sự kiện. Với Azure Container Apps, nền tảng cung cấp những scale rule dựa trên KEDA cho các scaler được hỗ trợ; người dùng **không phải tự triển khai Kubernetes HPA hoặc KEDA operator**.

~~~text
Ứng dụng upload PDF
         |
         v
Azure Blob Storage
         |
         v
Event Grid / dịch vụ phát sự kiện
         |
         v
Service Bus Queue: invoice-jobs
         |
         +--------------------------+
         |                          |
         v                          v
KEDA scaler kiểm tra backlog      Worker Container Apps
         |                        nhận và xử lý message
         v                          |
Đề xuất số replica                  v
         |                     Lưu kết quả / ACK
         v
Container Apps tăng/giảm replicas
~~~

KEDA **không đọc và xử lý file PDF thay ứng dụng**; nó lấy tín hiệu về công việc từ queue và điều chỉnh số replica. Code worker phải tự kết nối broker, đọc message, kiểm tra nội dung, ghi kết quả và xác nhận thành công.

### Vì sao không chỉ scale theo CPU?

Một worker đang nhàn rỗi có CPU rất thấp, nhưng queue có thể vừa nhận 10.000 thông điệp. Nếu chỉ đợi CPU tăng, hệ thống có thể phản ứng muộn. Scale theo số message đang chờ phản ánh rõ nhu cầu tiếp nhận công việc.

Ngược lại, queue length không phản ánh mọi chi phí xử lý: một thông điệp có thể là ảnh nhỏ hoặc PDF hàng trăm trang; worker có thể bị giới hạn bởi database, OCR hoặc API bên ngoài. Quy tắc scale phải được đo và điều chỉnh theo dữ liệu vận hành thực.

## 2. Các khái niệm nền tảng

| Khái niệm | Ý nghĩa |
|---|---|
| **Container Apps environment** | Ranh giới triển khai, hạ tầng và kết nối dùng chung của nhiều ứng dụng |
| **Container App** | Tài nguyên đại diện cho workload container |
| **Revision** | Phiên bản cấu hình ứng dụng theo cơ chế revision của Container Apps |
| **Replica** | Một bản sao đang chạy của revision; chứa các container thuộc template |
| **Scale rule** | Khai báo nguồn tín hiệu, metadata và xác thực cho scaler |
| **Scaler** | Thành phần quan sát tải, ví dụ queue length hoặc HTTP concurrency |
| **minReplicas** | Số bản sao tối thiểu nền tảng hướng tới duy trì |
| **maxReplicas** | Giới hạn số bản sao khi mở rộng |
| **Scale target** | Ngưỡng mục tiêu dùng để ước tính năng lực cần thiết |

**Replica không phải message**: một replica có thể xử lý nhiều message cùng lúc; một message có thể được nhận lại nếu quá trình xử lý trước thất bại. Scaler không cấp phát cứng một message cho một replica.

### Revision và scale rule

Cấu hình scale thuộc template gắn với revision của Container App. Khi thay đổi template, revision mới có thể được tạo. Ở chế độ nhiều active revisions, các phiên bản worker khác nhau có thể cùng xử lý một queue. Nếu schema message mới không tương thích bản cũ, quá trình rollout có thể gây lỗi dù scaler hoạt động đúng.

Đối với queue consumer đơn giản, cần xác định rõ dùng **single active revision** hay nhiều revision và chiến lược drain công việc trước khi chuyển phiên bản.

## 3. Chọn loại tín hiệu autoscaling

| Loại scale | Tín hiệu | Ứng dụng phù hợp |
|---|---|---|
| **HTTP scaling** | Yêu cầu HTTP đồng thời qua ingress | Web API và dịch vụ nhận request trực tiếp |
| **TCP scaling** | Kết nối TCP theo cơ chế hỗ trợ | Workload TCP có ingress tương ứng |
| **Custom KEDA scaler** | Queue length, event source hoặc metric bên ngoài | Worker xử lý Service Bus, Storage Queue, Kafka, Event Hubs |
| **Container Apps event-driven Jobs** | Tín hiệu tạo lượt thực thi job | Batch/run-to-completion, tác vụ có điểm kết thúc |

Không phải mọi scaler mã nguồn mở trong dự án KEDA đều mặc định được hỗ trợ trong mọi phiên bản Azure Container Apps. Phải kiểm tra đúng **loại scaler, metadata và phương thức xác thực** mà môi trường đang cung cấp.

### HTTP scaling và queue scaling khác nhau

~~~text
HTTP:
Browser -> Ingress Container Apps -> Web/API replicas
                 |
                 +-> HTTP concurrency là tín hiệu scale

Queue:
Producer -> Service Bus Queue
                |
                +-> KEDA đọc queue backlog để scale
                |
                +-> Worker replicas tự kết nối nhận message
~~~

Worker queue thường **không cần external HTTP ingress**. Chỉ bật ingress nếu workload thực sự cung cấp API hoặc endpoint quản trị phù hợp; tránh công khai endpoint nội bộ không cần thiết.

## 4. minReplicas, maxReplicas và scale-to-zero

Một lợi ích nổi bật của event-driven Container Apps là **scale-to-zero**: khi nguồn sự kiện không còn công việc, nền tảng có thể giảm số replica xuống 0 theo điều kiện scaler/rule và cấu hình cho phép.

| Thiết lập | Hành vi | Đánh đổi |
|---|---|---|
| **minReplicas = 0** | Có thể không duy trì worker khi queue rỗng | Tiết kiệm tài nguyên nhưng có cold start |
| **minReplicas = 1** | Duy trì ít nhất một worker | Phản ứng nhanh hơn, có chi phí nền |
| **minReplicas = 2** | Duy trì hai worker nền | Dư địa phục vụ ban đầu tốt hơn, chi phí cao hơn |
| **maxReplicas = 8** | Số replica không vượt giới hạn đã cấu hình | Hàng đợi có thể vẫn tăng nếu tải vượt năng lực tám replica |

**maxReplicas không đảm bảo số replica sẽ được tạo ngay.** Nền tảng cần đủ quota/capacity, image có thể pull, container phải khởi động được và nguồn scaler phải được xác thực.

### Cách hiểu ngưỡng backlog

Giả sử:

~~~text
minReplicas = 0
maxReplicas = 8
Service Bus active messages = 60
Ngưỡng minh họa = 10 messages / replica

Ước lượng sizing: ceil(60 / 10) = 6 replicas

Nếu backlog tăng thành 150:
  Ước lượng 15, nhưng maxReplicas = 8.
~~~

Đây chỉ là **phép chia để hình dung**, không phải công thức cam kết của Container Apps/KEDA cho mọi tình huống. Số replica thực tế phụ thuộc tín hiệu scaler, chu kỳ quan sát, kích hoạt, cooldown, concurrency, resource limits và trạng thái ứng dụng.

### Cold start

Khi queue rỗng và replicas bằng 0, message mới phải chờ:

1. Scaler nhận biết nguồn đã có công việc.
2. Nền tảng bố trí tài nguyên để chạy replica.
3. Image được sẵn sàng, tiến trình worker khởi động.
4. Worker thiết lập DNS/network, identity và kết nối broker.
5. Worker nhận thông điệp, bắt đầu xử lý.

Thời gian chờ không cố định. Image lớn, startup nặng, DNS sai, quyền chưa có hoặc môi trường thiếu năng lực có thể kéo dài độ trễ. Nếu SLO rất ngắn, cân nhắc **minReplicas lớn hơn 0** và tối ưu startup.

### Scale-in cần quản lý công việc đang chạy

Queue có thể hết active messages nhưng vẫn còn những message đã bị worker khóa và đang xử lý. Khi scale-in, container có thể nhận tín hiệu kết thúc. Worker phải xử lý **SIGTERM**, ngừng nhận thêm công việc, hoàn tất hoặc cho phép retry an toàn; không lưu trạng thái duy nhất trên filesystem tạm của replica.

## 5. Kiến trúc ví dụ: xử lý hóa đơn

Một hệ thống phát hành hóa đơn có:

- Azure Blob Storage lưu PDF trong container **incoming**.
- Event Grid thông báo tệp vừa được tạo.
- Ingest component ghi một message nhỏ vào **Azure Service Bus Queue invoice-jobs**.
- Azure Container Apps worker đọc queue, trích xuất thông tin và ghi dữ liệu đầu ra.
- Azure Container Registry (ACR) giữ image worker.
- Azure Monitor và job ledger ghi trạng thái và thời gian xử lý.

~~~text
Blob Storage/incoming
         |
         v
      Event Grid
         |
         v
    Ingest Function
         |
         v
Service Bus Queue: invoice-jobs
         |
         +----------------------+
         |                      |
         v                      v
    KEDA scaler             Worker replicas
  kiểm tra backlog        (1 đến N tùy tải)
         |                      |
         v                      v
   min=0, max=8          Đọc Blob -> xử lý
                                |
                                v
                       processed/ + job ledger
~~~

Queue tách tốc độ người dùng upload khỏi năng lực OCR/đọc dữ liệu. Trong giờ cao điểm, backlog được giữ bền vững; worker mở rộng theo tín hiệu tải. Nếu worker bị lỗi, message có thể được gửi lại hoặc chuyển DLQ theo cấu hình broker/ứng dụng.

**Event Grid delivery và Service Bus processing là hai tầng riêng.** Event Grid có thể retry khi không giao được tới ingest component; Service Bus có cơ chế lock, delivery count và dead-letter khi consumer gặp lỗi. Phải giám sát cả hai tầng.

## 6. Cấu hình Service Bus scale rule

Giả sử muốn tối đa tám worker và ngưỡng tham chiếu mười active messages cho mỗi replica:

| Trường | Giá trị minh họa | Ghi chú |
|---|---|---|
| Rule name | invoice-queue-scaler | Tên dễ tìm trong log |
| Scale type | azure-servicebus | Loại custom scaler |
| Queue name | invoice-jobs | Phải tồn tại |
| Namespace | sb-sales-prod | Tùy yêu cầu của kiểu auth |
| messageCount | "10" | Mục tiêu backlog của scaler |
| minReplicas | 0 | Muốn scale-to-zero |
| maxReplicas | 8 | Giới hạn tiêu thụ |
| Authentication | Secret reference hoặc managed identity | Phải dùng đúng schema/điều kiện hỗ trợ |

### Trích đoạn YAML minh họa

~~~yaml
# Đoạn template.scale để minh họa; không phải manifest ACA hoàn chỉnh.
template:
  scale:
    minReplicas: 0
    maxReplicas: 8
    rules:
      - name: invoice-queue-scaler
        custom:
          type: azure-servicebus
          metadata:
            queueName: invoice-jobs
            messageCount: "10"
          auth:
            - secretRef: servicebus-connection
              triggerParameter: connection
~~~

Trong ví dụ này, **servicebus-connection** là tên một secret đã được cấu hình an toàn trong Container App, **không phải connection string thật**. Secret phải được tạo trước và có quyền tối thiểu để scaler quan sát queue. Trích đoạn không gồm image, Container Apps environment, resource identity hoặc cấu hình secret nên **không thể triển khai nguyên xi**.

**Managed identity** được ưu tiên khi loại scaler, version và môi trường hỗ trợ. Với managed identity, metadata và cấu hình auth có thể khác với ví dụ dùng secretRef; cần tham chiếu tài liệu dịch vụ của scaler trước khi deploy.

### Quyền scaler khác với quyền worker

KEDA scaler cần có khả năng **đọc tín hiệu số message** từ Service Bus. Worker cần có khả năng **receive, complete, abandon hoặc dead-letter** message. Nếu scaler thiếu quyền thì app có thể không thức dậy từ 0. Nếu worker thiếu quyền thì replicas có thể tăng mà backlog vẫn không giảm.

Không cấp quyền quản trị namespace quá rộng chỉ vì đọc được queue length gặp lỗi; cần phân biệt cấu hình xác thực, RBAC và đường mạng của từng thành phần.

## 7. Sử dụng Azure Queue Storage thay Service Bus

Một lựa chọn khác là **Azure Queue Storage**. Scale rule có loại **azure-queue** với metadata phù hợp:

| Metadata thường gặp | Ý nghĩa |
|---|---|
| **queueName** | Tên Azure Storage Queue |
| **queueLength** | Ngưỡng số message dùng để scale |
| **accountName** | Storage Account chứa queue theo cách xác thực được hỗ trợ |
| **Authentication** | Connection secret hoặc managed identity theo hỗ trợ |

Không lấy metadata **messageCount** của Service Bus dùng cho Azure Queue, vì schema của hai scaler khác nhau.

### Chọn broker nào?

| Tiêu chí | Azure Queue Storage | Azure Service Bus Queue |
|---|---|---|
| Loại công việc | Hàng đợi đơn giản | Messaging doanh nghiệp nâng cao |
| Điều khiển nhận | Visibility timeout | Peek-lock/settlement theo dịch vụ |
| Xử lý lỗi | Poison handling do ứng dụng/integration quản lý | Dead-letter subqueue tích hợp |
| Sessions | Không có tính năng tương đương Service Bus sessions | Sessions theo điều kiện hỗ trợ |
| KEDA scaler | azure-queue | azure-servicebus |
| Chi phí | Theo dịch vụ Storage và operations | Theo tier/operations và tính năng |

Dù dùng broker nào, **KEDA không cung cấp exactly-once processing**. Consumer phải tự xử lý retry và tác động nghiệp vụ trùng lặp.

## 8. Worker phải tự nhận và xử lý thông điệp

Một Container App có scale rule đúng nhưng chương trình trong image không đọc queue thì hệ thống vẫn không làm được việc. Worker cần code nhận message, ghi kết quả và xác nhận.

~~~text
startup:
    authenticate using managed identity
    connect to Service Bus and Blob Storage
    prepare durable job ledger

loop:
    receive one or more messages
    validate message schema and job identifier

    if job already SUCCEEDED:
        complete duplicate message
        continue

    atomically claim the job
    read exact blob version or validate ETag
    validate file type, size, security checks
    transform and write deterministic output
    record SUCCEEDED durably
    complete message

    if permanent invalid input:
        record rejection
        dead-letter message with safe diagnostic

    if transient failure:
        abandon or retry under bounded policy

on SIGTERM:
    stop receiving new messages
    finish or safely relinquish in-flight work
    close connections and flush telemetry
~~~

Đây là **pseudocode**, không phải mã triển khai hoàn chỉnh. Dùng SDK và cơ chế auth tương ứng với broker thực tế.

### Những nguyên tắc không được bỏ qua

1. **At-least-once:** thông điệp có thể được giao lại sau crash hoặc lock hết hạn.
2. **Idempotency:** cùng jobId không được tạo kết quả nghiệp vụ trùng.
3. **Atomic claim:** dùng unique key/conditional write cho trạng thái công việc; kiểm tra rồi ghi không tự an toàn khi nhiều replica cùng xử lý.
4. **Ack sau khi kết quả bền vững:** chỉ complete message khi output và ledger đã được lưu thành công.
5. **Lock renewal:** job dài cần gia hạn lock/visibility timeout khi broker hỗ trợ.
6. **Dead-letter:** lỗi dữ liệu không sửa được không nên retry vô hạn.
7. **Graceful shutdown:** scale-in không được âm thầm làm mất công việc.
8. **Correlation ID:** liên kết message, blob, output và replica trong log.

### Prefetch và concurrency ảnh hưởng kết quả scale

Worker có thể prefetch nhiều message hoặc xử lý nhiều message song song. Lúc ấy backlog active có thể thấp nhưng vẫn có nhiều công việc **in-flight**. Nếu khóa hết hạn, thông điệp có thể quay lại queue. Vì vậy **active message count bằng 0 không chứng minh pipeline đã hoàn tất**.

Đặt prefetch phù hợp khả năng CPU/RAM và thời gian xử lý; theo dõi cả active, locked, dead-letter và trạng thái ledger.

## 9. Sizing dựa trên throughput và SLA

Giả sử một replica xử lý **6 hóa đơn/phút** và cần hoàn thành **600 hóa đơn trong 20 phút**.

~~~text
Tốc độ cần: 600 / 20 = 30 hóa đơn/phút
Tốc độ một replica: 6 hóa đơn/phút
Số replica lý thuyết: ceil(30 / 6) = 5
~~~

Kết quả 5 chưa có buffer cho cold start, tác vụ quá nặng, thời gian đợi database, retry hoặc throttling. Thử tải để chọn min/maxReplicas và ngưỡng thông điệp thực tế.

### Metrics cần đo khi sizing

- Thời gian từ enqueue tới khi bắt đầu xử lý.
- Thời gian xử lý p50/p95/p99 của mỗi loại job.
- Số message đang chờ, đang bị khóa và trong DLQ.
- Throughput hoàn thành của mỗi replica và toàn hệ thống.
- CPU, RAM, network và số kết nối backend.
- Thời gian tăng từ 0 lên 1 hoặc nhiều replicas.
- Retry rate và tỉ lệ job thất bại.

**Scale-out có thể làm hại hệ thống** khi downstream database chỉ cho phép 20 kết nối nhưng 30 replicas đồng thời mở nhiều kết nối. Giới hạn maxReplicas, concurrency, connection pool và retry rate phải tương thích toàn bộ kiến trúc.

## 10. Khi nào dùng Container Apps Jobs?

Container Apps có **Jobs**, phù hợp tác vụ có điểm bắt đầu/kết thúc. Một Job event-driven có thể sử dụng scaler để kích hoạt **job execution**, khác với scale một Container App chạy worker loop.

| Đặc điểm | Container App worker | Event-driven Container Apps Job |
|---|---|---|
| Vòng đời | Replica chạy consumer lâu dài | Job execution chạy rồi kết thúc |
| Cơ chế scale | Điều chỉnh số replicas | Điều chỉnh số lượt thực thi theo cấu hình |
| Dùng tốt cho | Listener liên tục, xử lý nhiều message | Batch/tác vụ run-to-completion |
| Xác nhận message | Code worker phải thực hiện | Code job vẫn phải xác nhận theo nghiệp vụ |
| Quy tắc cấu hình | minReplicas/maxReplicas | Tham số executions/parallelism phù hợp Jobs |

Không chép cấu hình **maxExecutions** của Jobs vào **maxReplicas** của Container App. Chọn mô hình theo vòng đời ứng dụng và khả năng xử lý lỗi.

## 11. Triển khai qua Azure portal

Các bước sau phù hợp lab có quyền và ngân sách. **Container Apps environment, ACR, Service Bus, Storage và log đều có thể phát sinh phí**.

### Bước 1: chuẩn bị image worker

Viết chương trình nhận queue, xử lý lỗi và log an toàn. Đóng gói trong container, thử local với nguồn thử nghiệm rồi publish image lên **Azure Container Registry**.

- Dùng tag phiên bản hoặc digest cụ thể, không phụ thuộc tag mới nhất không kiểm soát.
- Không nhúng secret vào Dockerfile/image.
- Chạy tiến trình với quyền tối thiểu và xử lý tín hiệu shutdown.
- Đảm bảo không lưu trạng thái quan trọng chỉ trên filesystem của container.

### Bước 2: chuẩn bị Service Bus

Tạo namespace và queue **invoice-jobs** trong môi trường được cấp phép. Producer gửi thông điệp nhỏ chứa jobId, blob reference, ETag/version; không gửi toàn bộ PDF vào queue.

Thử gửi, nhận, complete và dead-letter bằng môi trường không chứa dữ liệu khách hàng.

### Bước 3: tạo Container Apps environment và app

Tạo environment tại region phù hợp, chọn mạng, workload profile, log và quyền quản trị. Tạo Container App từ image trong ACR, cấu hình CPU/RAM, managed identity, biến môi trường và kết nối nguồn dữ liệu.

Worker tiêu thụ queue thường không cần external ingress. Khi cần dashboard quản trị, bảo vệ bằng cơ chế phù hợp thay vì công khai trực tiếp worker.

### Bước 4: cấu hình scale rule

Trong phần **Scale**, đặt minReplicas=0, maxReplicas=8 cho lab. Thêm custom rule type **azure-servicebus** với queue **invoice-jobs** và metadata messageCount phù hợp. Cấu hình secret reference hoặc identity mà scaler hỗ trợ.

Xem kỹ active revision sau khi lưu. Nếu app đang dùng multiple active revisions, xác nhận các phiên bản cũ không cùng nhận message với schema không tương thích.

### Bước 5: thử tải

Gửi một số message thử. Quan sát số replica tăng từ 0, consumer nhận/complete message, output được ghi và backlog giảm. Sau khi hết việc, quan sát scale-in; không yêu cầu nó xảy ra tức thời.

Tiếp theo gửi 50–100 message để đo throughput, thời gian xử lý, tài nguyên và mức scaling. Không cố tăng tải quá khả năng downstream.

### Bước 6: kiểm thử lỗi

Trong lab, tạo:

- Một message hợp lệ.
- Một message sai schema để xác minh DLQ.
- Hai message cùng jobId để kiểm tra idempotency.
- Một lỗi tạm thời để xác nhận retry và backoff.
- Một tình huống stop/redeploy worker khi đang xử lý để kiểm tra lock/recovery.

Sau đó ghi lại kết quả và dọn đúng tài nguyên lab đã được xác nhận không còn sử dụng.

## 12. Kiểm tra read-only bằng Azure CLI

Những lệnh dưới đây dùng để **đọc**, không tạo hay thay đổi cấu hình. Tên subscription/resource group/app là ví dụ.

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az containerapp show \
  --resource-group "rg-container-lab" \
  --name "invoice-worker" \
  --query "{name:name,state:properties.provisioningState,environment:properties.environmentId}" \
  --output json
~~~

### Xem scale rules

~~~bash
az containerapp show \
  --resource-group "rg-container-lab" \
  --name "invoice-worker" \
  --query "properties.template.scale" \
  --output json
~~~

Đối chiếu min/maxReplicas, rule type, metadata, identity/secret reference. Tránh in giá trị bí mật vào log.

### Xem revision và replicas

~~~bash
az containerapp revision list \
  --resource-group "rg-container-lab" \
  --name "invoice-worker" \
  --output table

az containerapp replica list \
  --resource-group "rg-container-lab" \
  --name "invoice-worker" \
  --revision "<ACTIVE_REVISION_NAME>" \
  --output table
~~~

Một lần list không có replica có thể bình thường nếu minReplicas=0 và nguồn không có việc. Khi backlog thực sự tăng, cần đối chiếu system logs/scale rule thay vì kết luận ngay app hỏng.

### Đọc log worker

~~~bash
az containerapp logs show \
  --resource-group "rg-container-lab" \
  --name "invoice-worker" \
  --type console \
  --tail 100
~~~

### Xem thông tin Service Bus Queue

~~~bash
az servicebus queue show \
  --resource-group "rg-container-lab" \
  --namespace-name "sb-sales-lab" \
  --name "invoice-jobs" \
  --output json
~~~

Đối chiếu số message active, dead-letter, các thuộc tính runtime được API hỗ trợ và số replica **ở cùng thời điểm**. Các phiên bản Azure CLI/extension có thể yêu cầu cập nhật theo tài liệu trước khi dùng nhóm lệnh Container Apps.

## 13. Bảo mật: scaler và worker là hai luồng truy cập

### Managed identity và RBAC

Ưu tiên **managed identity** cho Container App và service phụ thuộc khi được hỗ trợ:

| Đích | Quyền cần đánh giá |
|---|---|
| Azure Container Registry | Quyền kéo image, ví dụ AcrPull theo cơ chế hỗ trợ |
| Service Bus scaler | Quyền đọc trạng thái queue theo cách scaler hỗ trợ |
| Service Bus worker | Quyền nhận/settle message ở queue cần thiết |
| Blob Storage | Data-plane role đọc input, ghi output trong phạm vi phù hợp |
| Job ledger/DB | Quyền tạo/cập nhật record nghiệp vụ |

Cần phân biệt role cho **scaler** với role của **worker**. Khi scale rule thiếu quyền, replicas có thể không tăng; khi worker thiếu quyền, replicas tăng nhưng công việc không hoàn thành.

### Secrets

Nếu phải dùng connection string, lưu trong **Container App secret** hoặc tham chiếu Key Vault theo hỗ trợ. Scale rule chỉ chứa tên secret. Dùng chính sách luân chuyển/thu hồi và không ghi connection string vào image, YAML trong repository hay log.

### Mạng riêng

Với Service Bus hoặc Storage giới hạn qua Private Endpoint, xác minh **đường kết nối và DNS của cả scaler lẫn worker** trong kiểu environment được hỗ trợ. Việc worker truy cập được queue qua private networking chưa chứng minh scaler cũng đọc được queue metric.

Không mở public network access cho mọi nguồn chỉ để sửa lỗi 403 hoặc timeout trước khi phân loại nguyên nhân.

## 14. Nhiều scale rules và nhiều active revisions

Một app có thể khai báo nhiều scale rules được hỗ trợ, nhưng không nên nghĩ rằng các đề xuất số replica **được cộng đơn giản**. Nền tảng có cơ chế chọn yêu cầu scale theo các tín hiệu phù hợp; cần kiểm tra hành vi chính thức và thử tải.

Hai revisions cùng active có thể cùng đọc queue. Ví dụ:

~~~text
revision v1: hiểu schema message cũ
revision v2: yêu cầu thêm trường currency
queue chung: invoice-jobs

Nếu v1 và v2 cùng nhận message:
  -> v1 có thể nhận message mới không tương thích
  -> message bị retry hoặc vào DLQ
~~~

Biện pháp:

1. Thiết kế message schema tương thích ngược trong giai đoạn chuyển đổi.
2. Kiểm soát active revision mode.
3. Cân nhắc dùng queue tách theo phiên bản hoặc loại job khi cần.
4. Có drain/stop receiving và graceful shutdown.
5. Giữ idempotency khi retry sau triển khai.

## 15. Giám sát hiệu năng và SLA

Đừng đánh giá autoscaling chỉ bằng “đang có bao nhiêu replica”. SLO nghiệp vụ là **công việc hoàn thành đúng hạn, kết quả đúng và chi phí hợp lý**.

| Tín hiệu | Điều cần quan sát |
|---|---|
| Active messages | Lượng việc đang chờ |
| Oldest message age | Tuổi công việc chờ lâu nhất so với SLA |
| Locked/in-flight messages | Việc đã nhận nhưng chưa complete |
| Dead-letter messages | Số job lỗi cần xử lý hoặc replay |
| Replicas theo revision | Có scale hay không và phiên bản nào hoạt động |
| Worker throughput | Số job hoàn thành/phút |
| Latency p50/p95/p99 | Thời gian xử lý và tail latency |
| End-to-end latency | Từ enqueue tới kết quả sẵn sàng |
| Retry/duplicate rate | Độ ổn định và tính đúng đắn |
| CPU, RAM và connection usage | Giới hạn mỗi replica |
| 401/403, timeout | Lỗi xác thực hay mạng |
| Chi phí/job thành công | Hiệu quả toàn pipeline |

Ví dụ log có correlation:

~~~json
{
  "jobId": "invoice-2026-001",
  "queue": "invoice-jobs",
  "revision": "invoice-worker--rev42",
  "replica": "replica-id",
  "attempt": 2,
  "state": "SUCCEEDED",
  "durationMs": 2250
}
~~~

Không log SAS token, account key, toàn bộ payload chứa dữ liệu khách hàng hoặc hóa đơn. Sử dụng Azure Monitor, Log Analytics, Application Insights/telemetry và metrics broker theo cấu hình hỗ trợ.

### Gợi ý cảnh báo

- Oldest message age vượt SLA.
- Backlog tăng dù replicas đã đạt maxReplicas.
- Replicas bằng 0 trong thời gian dài khi queue thực sự có active messages.
- Worker crash loop hoặc liên tục lỗi auth.
- Dead-letter tăng bất thường.
- Chi phí compute hoặc monitoring vượt ngân sách.

## 16. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Queue có message nhưng replicas vẫn bằng 0 | Rule type/metadata/auth hoặc network sai | Xem scale config, identity, system logs và nguồn queue |
| Replicas tăng nhưng backlog không giảm | Worker không nhận message, lỗi quyền hoặc xử lý thất bại | Kiểm tra worker logs, Service Bus role và retry |
| Chỉ có một replica dù backlog lớn | Ngưỡng quá cao, max/quota thấp hoặc metric không đúng | Xem rule, quota, queue metrics và revision |
| Container crash loop | Lỗi startup, image, biến môi trường hoặc OOM | Kiểm tra replica status và console logs |
| Job được xử lý hai lần | Message retry/lock hết hạn và thiếu idempotency | Kiểm tra jobId, ledger, lock renewal |
| DLQ tăng liên tục | Payload lỗi, schema không tương thích hoặc hết số lần thử | Đọc dead-letter reason và sửa hợp đồng message |
| Không kết nối được Service Bus | DNS, egress, private endpoint, secret hoặc RBAC | Phân biệt timeout với 401/403 |
| Scale-to-zero phản ứng chậm | Cold start, image nặng hoặc scaler polling | Đo latency và cân nhắc minReplicas=1 |
| Tăng replicas làm throughput giảm | Database/API downstream throttling | Đo concurrency, 429/5xx và connection pool |
| Deployment xong có hai nhóm worker | Multiple active revisions cùng tiêu thụ queue | Kiểm tra revision list và rollout strategy |
| Queue rỗng nhưng không scale-in | minReplicas khác 0, cooldown hoặc rule khác hoạt động | Kiểm tra tất cả scale rules và điều kiện |
| Active count 0 nhưng job chưa xong | Message đang locked/in-flight | Xem job ledger và trạng thái settlement |

### Quy trình chẩn đoán sáu bước

1. **Nguồn:** đúng queue/namespace, active/locked/dead-letter count bao nhiêu?
2. **Rule:** đúng type/metadata, min/max, secretRef/identity và active revision không?
3. **Scaler:** có lỗi xác thực, DNS, egress hoặc metric trong platform logs không?
4. **Replica:** pull image thành công, process chạy, có OOM/restart không?
5. **Consumer:** receive/complete/abandon đúng, có lock timeout hay duplicate không?
6. **Downstream:** Blob, database, OCR có throttling hoặc lỗi làm throughput giảm không?

Nếu mọi replica đều bị lỗi 403, tăng maxReplicas chỉ làm tăng số lỗi và có thể tăng chi phí. Khắc phục đúng lớp trước khi điều chỉnh scale.

## 17. Chi phí và tối ưu quy mô

Scale-to-zero giúp giảm thời gian sử dụng compute worker khi không có việc, **không làm toàn bộ kiến trúc miễn phí**. Cần tính:

- Azure Container Apps theo **workload profile, CPU/RAM và mức dùng** theo plan đang áp dụng.
- Tài nguyên luôn chạy khi minReplicas lớn hơn 0 và chi phí môi trường khi có.
- Service Bus/Storage Queue: tier, throughput và operations.
- ACR: image storage, tier, network.
- Blob Storage, database, OCR/API và private networking.
- Azure Monitor/Log Analytics, retention và truy vấn log.

Đo **chi phí trên một job thành công**, không chỉ số replicas. Tám replica hoàn thành nhanh chưa chắc tiết kiệm hơn bốn replica nếu downstream bị giới hạn, phát sinh retry và log quá nhiều.

Đặt budget/tag cho subscription/resource group, theo dõi Azure Cost Management và bảng giá theo region/plan hiện hành.

## 18. Tình huống thực tế: tạo thumbnail ảnh sản phẩm

Một công ty có website bán hàng. Người dùng upload ảnh vào Blob Storage, Event Grid kích hoạt ingest service ghi message vào Service Bus Queue, rồi Container Apps worker tạo thumbnail.

Giả thiết:

- Một replica xử lý được trung bình **12 ảnh/phút** khi không bị throttling.
- Ban đêm gần như không có ảnh.
- Đợt khuyến mãi xuất hiện **2.400 ảnh trong 20 phút**.
- SLA: xử lý xong trong **30 phút** tính từ thời điểm enqueue.
- API nhận kết quả có giới hạn **100 request/phút**.
- Có ảnh lỗi định dạng và upload lại cùng tên.

### Yêu cầu thiết kế

1. Chọn Container App worker hay event-driven Job; giải thích.
2. Thiết kế Blob → Event Grid → queue → worker và quyền từng thành phần.
3. Đề xuất minReplicas, maxReplicas, ngưỡng backlog để bắt đầu thử tải.
4. Tính số replica lý thuyết để xử lý 2.400 ảnh trong 30 phút.
5. Giải thích tác động của API downstream giới hạn 100 request/phút.
6. Xây dựng job ID, ETag/versioning, idempotency và retry.
7. Chọn cách xử lý lỗi cố định, DLQ, replay và graceful shutdown.
8. Nêu cách kiểm tra scale-to-zero, cold start, metrics, SLA và chi phí.

### Gợi ý lời giải

~~~text
Yêu cầu: 2.400 ảnh / 30 phút = 80 ảnh/phút
Một replica: 12 ảnh/phút
Số replica lý thuyết: ceil(80/12) = 7
~~~

Bảy replica chỉ là **ước tính lý thuyết**, chưa có buffer cold start, tệp phức tạp, retry hoặc phân bố tải. Nếu mỗi ảnh đòi nhiều request tới API giới hạn 100 request/phút thì số replica tăng thêm không thể tự giải quyết nút thắt. Cần giới hạn concurrency, giảm request hoặc tăng năng lực downstream.

## 19. Checklist production

| Nhóm | Điều cần xác minh |
|---|---|
| Broker | Queue tồn tại, có producer và schema message rõ |
| Scaler | KEDA type/metadata/auth đúng phiên bản Container Apps |
| Range | min/maxReplicas phù hợp SLA, quota và downstream |
| Zero | Đã thử scale từ 0, đo cold start và kiểm tra quyền |
| Worker | Receive/process/complete/DLQ đúng hợp đồng |
| Idempotency | jobId, unique ledger, không tạo kết quả trùng |
| Locks | Renewal, timeout, xử lý SIGTERM an toàn |
| Image | ACR version/digest rõ, startup ổn định |
| IAM | Managed identity/RBAC cho ACR, scaler, queue, Blob |
| Network | DNS/egress/private endpoint đúng cả scaler và worker |
| Revision | Mode và schema migration có kiểm soát |
| Metrics | Backlog, age, throughput, replicas, retry, latency và DLQ |
| Alert | Runbook xử lý backlog, 403, crash loop, throttling |
| Chi phí | Budget compute, broker, registry, storage và logs |
| Recovery | Thử retry/replay, đối chiếu trạng thái và rollback |

## 20. Câu hỏi tự kiểm tra

1. KEDA có trực tiếp xử lý Service Bus message thay cho worker không?
2. Vì sao queue length thường hữu ích hơn CPU đối với consumer không nhận HTTP?
3. Container App replica khác Container Apps Job execution ra sao?
4. minReplicas=0 có lợi ích và rủi ro gì?
5. maxReplicas=8 có đảm bảo luôn tạo được tám replica không?
6. Metadata messageCount của Service Bus khác queueLength của Azure Queue Storage như thế nào?
7. Queue có 80 message và target 10 message/replica: ước tính bao nhiêu replica, và tại sao thực tế có thể khác?
8. Vì sao không được coi một message tương đương một replica?
9. Tại sao scaler có quyền đọc queue mà worker vẫn có thể lỗi nhận message?
10. Khi lock hết hạn và message được giao lại, làm sao tránh tạo output trùng?
11. Queue active count bằng 0 có chứng minh mọi job hoàn thành không?
12. DLQ giúp gì cho lỗi dữ liệu và quy trình replay?
13. Vì sao multiple active revisions có thể gây lỗi schema?
14. Khi dùng Private Endpoint, tại sao phải kiểm tra scaler và worker riêng?
15. Nếu replicas chạm max nhưng backlog tăng, cần đo các giới hạn nào?
16. Những metrics nào trực tiếp phản ánh SLA xử lý job?
17. Vì sao scale-to-zero có thể tăng độ trễ dù tiết kiệm compute?
18. Làm thế nào tối ưu chi phí mà không gây throttling hoặc retry hàng loạt?

## Tài liệu tham khảo

- Microsoft Learn — *Set scaling rules in Azure Container Apps*: https://learn.microsoft.com/azure/container-apps/scale-app
- Microsoft Learn — *Azure Container Apps overview*: https://learn.microsoft.com/azure/container-apps/overview
- Microsoft Learn — *Azure Container Apps revisions*: https://learn.microsoft.com/azure/container-apps/revisions
- Microsoft Learn — *Azure Container Apps jobs*: https://learn.microsoft.com/azure/container-apps/jobs
- Microsoft Learn — *Managed identities in Azure Container Apps*: https://learn.microsoft.com/azure/container-apps/managed-identity
- Microsoft Learn — *Azure Container Apps networking*: https://learn.microsoft.com/azure/container-apps/networking
- Microsoft Learn — *Azure Service Bus messaging overview*: https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview
- Microsoft Learn — *Azure Container Registry overview*: https://learn.microsoft.com/azure/container-registry/container-registry-intro
- KEDA documentation — *Scalers*: https://keda.sh/docs/latest/scalers/
