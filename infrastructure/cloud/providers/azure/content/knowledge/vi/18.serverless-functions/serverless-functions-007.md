# Concurrency, cold start và tối ưu thời gian khởi động

## 1. Vì sao Azure Functions có thể nhanh ở lần gọi này nhưng chậm ở lần gọi khác?

**Azure Functions** cho phép chạy mã theo sự kiện mà không cần tự xây dựng và quản lý từng máy chủ ứng dụng. Một Function có thể được kích hoạt bằng HTTP request, message từ Azure Queue Storage hoặc Service Bus, blob event, timer hay các trigger được runtime hỗ trợ. Nền tảng có thể cung cấp thêm instance khi tải tăng và giảm năng lực chạy khi tải thấp, tùy **hosting plan**.

Tuy nhiên, serverless không có nghĩa tất cả lời gọi đều có độ trễ bằng nhau. Một API Java chạy trên Azure Functions có thể đáp ứng nhanh khi runtime đã sẵn sàng (**warm execution**), nhưng yêu cầu đầu tiên sau thời gian rảnh hoặc sau khi mở rộng năng lực có thể chậm hơn vì cần khởi tạo runtime, worker và ứng dụng (**cold start**).

Với queue processor, tăng số instance hoặc số message xử lý đồng thời có thể giúp hoàn tất backlog nhanh hơn. Nhưng nếu mỗi message gọi cùng một database với giới hạn 100 kết nối, tăng concurrency không kiểm soát có thể làm database nghẽn và khiến toàn bộ hệ thống **chậm hơn**.

Bài học thuộc chương **Serverless với Azure Functions** trong module tìm hiểu hệ sinh thái Microsoft Azure: từ subscription, resource group và Entra ID đến mạng, tính toán, lưu trữ, dữ liệu, giám sát, bảo mật và chi phí. Trọng tâm là **hiểu sự tương tác giữa concurrency, scale-out và cold start**, lựa chọn hosting plan phù hợp, sau đó tối ưu bằng đo đạc thay vì dựa vào suy đoán.

> **Thông điệp chính:** concurrency là số công việc có thể được xử lý đồng thời; scale-out là tăng số instance; cold start là phần thời gian khởi tạo khi chưa có môi trường chạy sẵn. Đây là ba khái niệm liên quan nhưng không thay thế nhau.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **concurrency trong một instance**, **số instance** và **tổng thông lượng**.
2. Giải thích cold start, warm start, scale-out start và các loại độ trễ khi gọi Azure Functions.
3. Hiểu tại sao các HTTP, Queue, Service Bus và những trigger khác có cơ chế concurrency khác nhau.
4. Đọc và sử dụng cấu hình **host.json** với các lưu ý về phiên bản extension và dynamic concurrency.
5. So sánh các định hướng của Consumption, Flex Consumption, Premium và Dedicated/App Service plans.
6. Chọn chiến lược giảm cold start bằng cách tối ưu code Java, dependency, image/package và tài nguyên khởi tạo.
7. Thiết kế idempotency, timeout, retry, backpressure và bảo vệ database khi tăng concurrency.
8. Đo latency p50/p95/p99, throughput, error rate, số instance và các mốc cold/warm execution.
9. Thực hiện một thí nghiệm có kiểm soát để kiểm chứng hiệu quả trước khi triển khai production.
10. Đánh đổi giữa tốc độ phản hồi, mức dự phòng và tổng chi phí Azure.

## 3. Ba thước đo cơ bản: latency, throughput và concurrency

| Thuật ngữ | Định nghĩa | Ví dụ |
|---|---|---|
| **Latency** | Thời gian một request hoặc công việc cần để hoàn thành | HTTP request mất 300 ms |
| **Throughput** | Số công việc hoàn tất trong một đơn vị thời gian | 120 requests/giây |
| **Concurrency** | Số công việc đang xử lý tại cùng thời điểm | 8 requests đang chạy |
| **Scale-out** | Tăng số worker/compute instances để xử lý thêm công việc | Từ 2 lên 5 instances |
| **Scale-in** | Giảm số instances khi không cần nhiều capacity | Từ 5 xuống 2 |
| **Cold start** | Phần khởi tạo khi runtime/worker cần được cấp và bắt đầu | Function được gọi khi chưa có instance ấm |
| **Warm execution** | Lời gọi được xử lý trên môi trường đã sẵn sàng | Request tiếp theo dùng worker đang chạy |

Một hệ thống có latency thấp chưa chắc chịu được lượng lớn requests. Ngược lại, hệ thống có throughput cao vẫn có thể có **p99 latency** rất lớn do một phần nhỏ requests bị chờ hoặc khởi tạo.

### 3.1. Tư duy bằng Little's Law

Trong trạng thái tương đối ổn định, một quan hệ hữu ích:

\[
L \approx \lambda \times W
\]

Trong đó:

- \(L\): số yêu cầu trung bình đang ở trong hệ thống.
- \(\lambda\): tốc độ hoàn thành yêu cầu, ví dụ requests/giây.
- \(W\): thời gian yêu cầu ở trong hệ thống, tính bằng giây.

Nếu trung bình một request chiếm 0,25 giây và có khoảng 20 requests đồng thời, ta có ước lượng lý tưởng gần:

\[
\lambda \approx 20/0{,}25 = 80 \text{ requests/giây}
\]

Công thức này **không phải cam kết công suất của Azure Functions**: CPU, memory, runtime threads, mạng, rate limit, database và thời gian chờ trong queue đều có thể tạo giới hạn khác.

## 4. Concurrency trong một Azure Functions instance

Một **Functions instance** là môi trường compute chạy một function app hoặc một nhóm functions theo mô hình hosting tương ứng. Trong một instance, runtime có thể xử lý nhiều function executions cùng lúc, tùy:

- Loại trigger và extension.
- Ngôn ngữ cùng worker runtime.
- Cấu hình host/trigger.
- HTTP concurrency settings của hosting plan khi hỗ trợ.
- CPU/memory của instance.
- Tác vụ đồng bộ, bất đồng bộ hoặc mức sử dụng thread.
- Những giới hạn mà platform áp dụng.

Ví dụ một instance có concurrency thực tế là 8, nghĩa là tại một thời điểm instance có thể đang thực thi 8 công việc. Nếu mỗi công việc cần 500 ms và không có bottleneck khác, năng lực lý thuyết là khoảng 16 jobs/giây cho instance đó; trong thực tế thường cần headroom.

**Một instance có nhiều executions không đồng nghĩa có nhiều tiến trình Java khác nhau.** Một Java worker process có thể nhận nhiều invocations; tùy runtime và cấu hình, một instance có thể dùng nhiều worker processes hoặc threads. Những lựa chọn này phải được kiểm chứng với runtime/hosting plan cụ thể.

### 4.1. Concurrency quá thấp

- Mỗi instance xử lý ít công việc, CPU có thể nhàn rỗi.
- Nền tảng có thể phải thêm nhiều instances để đạt cùng thông lượng.
- Số instance tăng kéo theo cold starts và chi phí/tài nguyên khởi tạo.

### 4.2. Concurrency quá cao

- CPU bị cạnh tranh, JVM thread pool hoặc GC trở thành nút cổ chai.
- Memory tăng, có thể phát sinh OOM hoặc restarts.
- Database/HTTP connection pool cạn.
- Latency p95/p99 tăng.
- Retry và timeout gây vòng lặp quá tải.

**Concurrency hợp lý là giá trị được xác nhận bằng load test**, không phải luôn bằng số vCPU hoặc giá trị lớn nhất mà runtime chấp nhận.

## 5. Scale-out khác tăng concurrency như thế nào?

Giả sử một instance xử lý tối đa 8 requests cùng lúc. Với 4 instances, tổng số requests đang được xử lý có thể xấp xỉ 32 trong điều kiện phân phối và cấu hình phù hợp.

~~~mermaid
flowchart LR
    CLIENT[HTTP requests hoặc queue events] --> ROUTE[Trigger dispatcher / scale controller]
    ROUTE --> I1[Instance 1: 8 executions]
    ROUTE --> I2[Instance 2: 8 executions]
    ROUTE --> I3[Instance 3: 8 executions]
    ROUTE --> I4[Instance 4: 8 executions]
    I1 --> DB[(Downstream database)]
    I2 --> DB
    I3 --> DB
    I4 --> DB
~~~

Một ước lượng công suất trong điều kiện lý tưởng:

\[
\text{Thông lượng} \approx
\frac{\text{Số instances} \times \text{Concurrency/instance}}
{\text{Thời gian xử lý trung bình}}
\]

Ví dụ 4 instances, concurrency 8, thời gian 0,4 giây:

\[
\text{Thông lượng lý thuyết} \approx (4\times8)/0{,}4=80
\text{ yêu cầu/giây}
\]

Đây là bài tính năng lực để hiểu xu hướng, **không phải một chỉ tiêu chắc chắn**. Nếu 32 công việc cùng truy cập một database chỉ cho phép 10 truy vấn nặng đồng thời, throughput có thể còn thấp hơn trường hợp concurrency vừa phải.

### 5.1. Phân biệt ba nút điều chỉnh

1. **Per-instance concurrency:** mỗi instance nhận bao nhiêu công việc.
2. **Scale-out capacity:** có bao nhiêu instances được cấp và sẵn sàng.
3. **Downstream capacity:** hệ thống dữ liệu/API bên ngoài chịu được bao nhiêu công việc.

Tăng một nút mà không cân nhắc hai nút còn lại có thể làm mất ổn định hệ thống.

## 6. Concurrency là đặc tính của trigger, không có một công tắc chung cho mọi function

Các loại trigger khác nhau nhận và phân phối công việc theo cơ chế khác nhau.

| Trigger | Tính chất tải | Cần chú ý |
|---|---|---|
| **HTTP** | Request-response trực tiếp, người dùng quan sát latency | HTTP concurrency per instance, thời gian khởi động, timeout và ingress |
| **Azure Queue Storage** | Message được kéo và xử lý theo batch/concurrency | Batch, visibility timeout, retry/poison messages |
| **Azure Service Bus** | Message/session với lock và xử lý concurrent | maxConcurrentCalls, sessions, prefetch, lock renewal |
| **Event Hubs** | Xử lý luồng dữ liệu theo partitions và checkpoints | Partition count, batch size, checkpoint và ordering |
| **Blob trigger** | Kích hoạt khi có blob/sự kiện blob theo cơ chế extension | Cơ chế trigger/extension, kích thước tệp và concurrency |
| **Timer trigger** | Công việc định kỳ | Không tự có nghĩa mở rộng xử lý một lịch chạy thành nhiều bản song song |
| **Durable Functions** | Orchestration và activity executions | Replay, activity concurrency, checkpoint và idempotency |

**Không áp dụng cấu hình Queue batchSize cho HTTP trigger rồi kỳ vọng HTTP concurrency đổi theo.** Tương tự, HTTP concurrency không trực tiếp quyết định số Event Hub partitions có thể xử lý song song.

Một function app có nhiều triggers cần được phân tích từng nhóm, nhất là khi chúng chia sẻ cùng worker process, memory hoặc các dependency.

## 7. HTTP trigger: latency người dùng và concurrency

Với HTTP-triggered Functions, mỗi request đi qua gateway/platform, được định tuyến đến một môi trường chạy, rồi vào function invocation. Độ trễ người dùng nhìn thấy có thể gồm nhiều phần:

~~~mermaid
flowchart LR
    A[Client gửi HTTP] --> B[Routing/platform]
    B --> C{Worker đã sẵn sàng?}
    C -->|Chưa| D[Cold initialization]
    C -->|Rồi| E[Function invocation]
    D --> E
    E --> F[Database / API / Storage]
    F --> G[Response]
~~~

### 7.1. HTTP concurrency per instance

Một số hosting plans cho phép cấu hình số HTTP requests đồng thời trên mỗi instance. Trong **Flex Consumption**, HTTP concurrency có cơ chế cài đặt theo app và có defaults phụ thuộc memory size/language/runtime hoặc những giới hạn dịch vụ hiện hành. Cách điều chỉnh có thể dùng Azure Portal, CLI hoặc API được plan hỗ trợ.

**Không nhập một con số được học thuộc từ một tài liệu cũ rồi mặc định áp dụng mọi function app.** Hãy kiểm tra hosting plan, runtime, instance memory, HTTP concurrency settings và khả năng scale hiện tại.

### 7.2. Tác động của HTTP concurrency

- Giảm concurrency có thể cải thiện latency khi mỗi invocation dùng nhiều CPU/RAM.
- Tăng concurrency có thể giúp tác vụ I/O-bound tận dụng worker tốt hơn.
- Nhưng concurrency cao có thể dẫn đến CPU contention, connection exhaustion và tail latency xấu.

### 7.3. Timeout và yêu cầu dài

HTTP request-response không phù hợp cho mọi tác vụ dài. Gateway, client và dịch vụ nền tảng có timeout giới hạn; việc tăng function timeout không nhất thiết làm HTTP connection được giữ vô hạn.

Với công việc kéo dài nhiều phút, cân nhắc:

1. HTTP function xác thực request và gửi job vào queue.
2. Trả **202 Accepted** kèm operation ID hoặc URL trạng thái.
3. Queue-triggered function hoặc Durable Functions xử lý nền.
4. Client polling hoặc nhận callback thông báo khi hoàn tất.

Giải pháp này giảm thời gian giữ HTTP request mở, đồng thời cho phép kiểm soát retries và concurrency của worker riêng.

## 8. Queue Storage trigger: batch và concurrency

Với Azure Queue Storage trigger, runtime lấy messages và gọi function để xử lý. Nếu tải tăng, nền tảng có thể tăng concurrent processing trong một instance và/hoặc scale-out theo tín hiệu workload, tùy plan và extension.

Các tham số đáng chú ý trong **mô hình fixed concurrency** của Queue extension:

- **batchSize:** số message runtime lấy trong một batch theo cấu hình.
- **newBatchThreshold:** ngưỡng còn lại khiến runtime lấy batch bổ sung.
- **visibilityTimeout:** một phần cơ chế retry cho message thất bại theo extension.
- **maxDequeueCount:** số lần nhận trước khi xử lý message độc/poison theo cơ chế Queue extension.

Một ví dụ host.json dùng **fixed concurrency**:

~~~json
{
  "version": "2.0",
  "extensions": {
    "queues": {
      "batchSize": 4,
      "newBatchThreshold": 2,
      "visibilityTimeout": "00:00:30",
      "maxDequeueCount": 5
    }
  }
}
~~~

Các giá trị trên là ví dụ học tập và phải tương thích với extension version đang dùng. Với kiểu tải này, số executions cùng lúc trong một instance có thể liên hệ với batchSize và newBatchThreshold; không nên diễn giải công thức đó như giới hạn toàn cluster hay mọi worker process.

### 8.1. Tại sao giảm batchSize?

Giả sử mỗi message ghi vào database. Nếu 16 messages cùng chạy và mỗi invocation sử dụng 5 DB connections, tổng kết nối có thể vượt ngưỡng mà database cho phép. Giảm batchSize có thể tránh burst quá lớn.

### 8.2. Tại sao tăng batchSize?

Nếu messages chỉ làm tác vụ ngắn và chủ yếu chờ I/O độc lập, concurrency thấp có thể bỏ phí năng lực. Tăng theo bước, quan sát throughput và p95 completion time trước khi giữ cấu hình.

### 8.3. Một message có thể được xử lý lại

Queue trigger thường có hành vi **at-least-once** theo ngữ cảnh xử lý thực tế. Khi worker bị kết thúc, lock/visibility hết hạn hoặc handler lỗi, message có thể xuất hiện lại. Function phải được thiết kế **idempotent**; tăng concurrency làm nguy cơ xử lý trùng/đua tranh dễ lộ rõ hơn.

## 9. Service Bus trigger: calls, sessions và locks

Azure Service Bus hỗ trợ queue và topic/subscription với khả năng message broker phong phú hơn Azure Queue Storage. Concurrency của Service Bus trigger phụ thuộc extension version và chế độ xử lý.

Các cấu hình thường gặp trong một số phiên bản Service Bus extension:

- **maxConcurrentCalls:** số non-session messages đang xử lý đồng thời trên một instance.
- **maxConcurrentSessions:** giới hạn sessions được xử lý đồng thời.
- **prefetchCount:** số messages có thể được prefetch để tăng throughput.
- **maxAutoLockRenewalDuration:** mức thời gian gia hạn lock tự động theo điều kiện cấu hình.
- **autoCompleteMessages:** cơ chế complete message khi handler thành công theo phiên bản binding.

Ví dụ khái niệm host.json khi **không dùng dynamic concurrency**:

~~~json
{
  "version": "2.0",
  "extensions": {
    "serviceBus": {
      "prefetchCount": 0,
      "maxConcurrentCalls": 8,
      "maxConcurrentSessions": 4
    }
  }
}
~~~

**Cần xác nhận đúng phiên bản extension**, loại trigger (sessions hay không), host plan và config schema. Không phải mọi property đều được áp dụng trong mọi chế độ. Khi dynamic concurrency được bật cho trigger hỗ trợ, các ngưỡng thủ công có thể bị runtime điều phối và không còn tác dụng theo cách cũ.

### 9.1. Session ordering

Với session-enabled messages, một session thể hiện luồng cần xử lý có điều kiện ordering/affinity. Đừng đặt concurrency cao rồi giả định có thể xử lý tùy ý nhiều messages trong cùng session mà vẫn bảo đảm thứ tự nghiệp vụ.

### 9.2. Lock và xử lý lâu

Nếu thời gian xử lý vượt lock duration hoặc việc gia hạn lock thất bại, message có thể được giao lại. Cần kiểm tra completion, retry và idempotency, không chỉ đẩy maxConcurrentCalls lên cao.

### 9.3. Không quy một lỗi dependency thành lý do scale-out

Nếu tất cả Service Bus handlers đều gọi một API đang rate-limited, tăng số instances làm tăng số request bị từ chối. Cần backoff, circuit breaker hoặc giới hạn concurrency đầu ra.

## 10. Event Hubs, Blob và Timer: đặc tính mở rộng riêng

### 10.1. Event Hubs

Event Hubs chia dữ liệu thành **partitions**. Khả năng song song hóa của một consumer group chịu ảnh hưởng từ số partitions, cách cân bằng ownership, batch processing và checkpoints.

- Partition count có thể là giới hạn về số đơn vị tiêu thụ song song có ý nghĩa.
- Quá nhiều instances so với partition count có thể không cải thiện throughput tương ứng.
- Checkpoint quá thường xuyên tăng overhead; quá hiếm có thể dẫn tới replay lớn khi lỗi.
- Function cần chịu được duplicate/replay theo mô hình streaming.

### 10.2. Blob trigger

Blob-triggered Functions có những chế độ phát hiện/kích hoạt khác nhau tùy extension và hạ tầng, gồm cơ chế polling hoặc event-based ở cấu hình hỗ trợ. Khi xử lý blob lớn, memory/network bandwidth có thể trở thành giới hạn trước CPU.

Không nên đọc toàn bộ file rất lớn vào RAM chỉ vì function binding cung cấp stream hoặc bytes; ưu tiên streaming/chunking và giới hạn concurrent blob processing theo năng lực thực.

### 10.3. Timer trigger

Timer trigger chạy theo lịch. Lịch không tự nhân một công việc lên hàng chục instances để hoàn thành nhanh hơn. Nếu cần batch song song:

1. Timer function tạo danh sách công việc.
2. Gửi từng công việc vào Queue hoặc điều phối bằng Durable Functions.
3. Workers xử lý theo concurrency được kiểm soát.
4. Kết quả được tổng hợp với idempotency.

### 10.4. Durable Functions

Durable Functions có orchestration state và replay semantics riêng. Orchestrator phải tuân theo quy tắc tính xác định (determinism) trong logic orchestration; tác dụng phụ thực hiện ở activities hoặc các bước được thiết kế đúng.

Concurrency của activities/orchestrations có cấu hình/tương tác với storage provider và worker runtime. Khi đánh giá performance, phân biệt latency của orchestration, số activities song song và khả năng scale-out của hosting plan.

## 11. Dynamic concurrency: runtime học mức song song phù hợp

Với các trigger và extension **có hỗ trợ**, Azure Functions có **dynamic concurrency** để runtime tự điều chỉnh số concurrent executions dựa trên tài nguyên thực tế và tín hiệu health của host.

Một ví dụ host.json:

~~~json
{
  "version": "2.0",
  "concurrency": {
    "dynamicConcurrencyEnabled": true,
    "snapshotPersistenceEnabled": true
  }
}
~~~

Ý nghĩa:

- **dynamicConcurrencyEnabled:** yêu cầu runtime sử dụng cơ chế dynamic concurrency cho các trigger hỗ trợ.
- **snapshotPersistenceEnabled:** cho phép lưu/sử dụng snapshots về mức concurrency đã học theo cơ chế runtime để giúp khởi động lại ít phải học từ đầu hơn trong điều kiện hỗ trợ.

**Đây không phải công tắc khiến mọi trigger và mọi language runtime tự scale giống nhau.** Một số trigger không hỗ trợ hoặc chịu điều khiển khác, đặc biệt HTTP. Phải kiểm tra phiên bản extension và tài liệu của trigger cụ thể.

### 11.1. Khi bật dynamic concurrency

Với trigger được hỗ trợ, một số cấu hình fixed concurrency như batchSize hoặc maxConcurrentCalls có thể được bỏ qua hoặc bị thay thế bởi cơ chế động. Đừng vừa bật dynamic concurrency vừa kết luận việc đổi một thông số fixed đã trực tiếp tạo ra kết quả load test.

### 11.2. Ưu điểm

- Giảm nhu cầu điều chỉnh thủ công các ngưỡng cho mọi máy.
- Có thể tận dụng công suất tốt hơn khi tải và instance size khác nhau.
- Có thể phản ứng khi CPU hoặc tài nguyên host bị áp lực.

### 11.3. Giới hạn

- Không biết toàn bộ giới hạn của API/database ngoài Azure Functions.
- Có thể cần thời gian học trong những điều kiện chưa có snapshot.
- Không thay thế application-level throttling, queue semantics hoặc SLO.
- Không chắc phù hợp với workload có downstream concurrency cap rất nhỏ.

**Phân biệt hai cơ chế:** dynamic concurrency quyết định số executions đồng thời trong instance cho trigger được hỗ trợ; scale controller quyết định số instances theo plan và trigger signals. Hai cơ chế có thể tương tác, nhưng không phải cùng một nút điều chỉnh.

## 12. host.json và app settings: cấu hình ở đúng tầng

Một function app có thể dùng:

- **host.json:** runtime host settings và extension-specific settings.
- **Application settings/environment variables:** configuration như connection references, feature flags, worker process settings.
- **Platform/hosting plan settings:** memory/instance size, HTTP concurrency, always-ready/prewarmed capacity và scaling limits khi được hỗ trợ.
- **Function code:** thread pool, HTTP client pool, retry logic, cache và khởi tạo dependency.

### 12.1. Ví dụ host.json tối giản

~~~json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true
      }
    }
  },
  "functionTimeout": "00:05:00"
}
~~~

Thời hạn tối đa thực sự phụ thuộc hosting plan và loại trigger. Cấu hình **functionTimeout** không có nghĩa request HTTP có thể giữ kết nối vô hạn, cũng không đảm bảo nền tảng không ngừng một instance vì sự cố hoặc scale-in.

### 12.2. Không copy cấu hình cũ nguyên xi

Các extension version có thể đổi key, mặc định và behavior. Một giá trị từ Queue extension bản cũ chưa chắc phù hợp bản mới. Sau mỗi nâng cấp Azure Functions runtime/extension, nên kiểm tra compatibility và thử workload thật.

### 12.3. Các biến môi trường nhạy cảm

Đừng đưa Storage account keys, connection strings production hoặc client secrets vào Git. Khi có thể, dùng Microsoft Entra managed identity và cấu hình kết nối dựa trên identity của Azure Functions, kết hợp Azure RBAC phù hợp.

## 13. Ngôn ngữ lập trình và worker processes ảnh hưởng concurrency

Một Function App chạy Java có đặc điểm khởi tạo khác ứng dụng JavaScript hoặc .NET. **Thời gian JVM startup, class loading, JIT, dependency injection và HTTP client initialization** có thể đáng kể, nhất là khi instance mới được cấp.

Các nhóm ngôn ngữ có mô hình worker/runtime khác nhau:

| Runtime | Điểm cần chú ý |
|---|---|
| **Java** | JVM, class loading, classpath, threads và connection pools |
| **.NET** | Mô hình isolated/in-process tùy support, DI và runtime initialization |
| **Node.js** | Event loop, async I/O, tác vụ CPU-bound có thể chặn luồng |
| **Python** | Sync/async functions, thread pool, worker processes và GIL trong CPython |
| **PowerShell** | Worker initialization và môi trường modules |

Một số runtime/plan hỗ trợ cấu hình số **language worker processes** như **FUNCTIONS_WORKER_PROCESS_COUNT**, nhưng phạm vi, mặc định và giới hạn phụ thuộc ngôn ngữ, runtime version và hosting plan. Tăng số process có thể tăng song song hóa một số workload, đồng thời tăng RAM, thời gian khởi động và số connection pools.

### 13.1. Java: thread-safety quan trọng

Các lần invocation có thể cùng sử dụng đối tượng static/singleton trong một worker process. Không lưu trạng thái một request vào trường mutable dùng chung mà không có đồng bộ thích hợp.

Ví dụ **không an toàn**:

~~~java
public class BadFunctionState {
    private static String currentCustomerId;

    public void handle(String customerId) {
        currentCustomerId = customerId;
        // Invocation khác có thể ghi đè trước khi xử lý xong.
    }
}
~~~

Cách tốt hơn là giữ dữ liệu thuộc request trong biến local và dùng client libraries được thiết kế thread-safe ở phạm vi chia sẻ.

### 13.2. Tăng threads chưa chắc tăng throughput

Nếu 30 threads cùng gọi một database tối đa 10 connections, 20 threads sẽ chờ pool. Cần chọn **concurrency limit, connection pool size và timeout** như một bộ tham số thay vì tối ưu từng tham số riêng lẻ.

## 14. Azure Functions có thể cold start vào những thời điểm nào?

Cold start xảy ra khi nền tảng cần chuẩn bị một môi trường chạy chưa sẵn sàng. Các tình huống thường gặp:

- Function App nhận sự kiện sau thời gian rảnh và hosting plan có thể scale về zero.
- Nền tảng cấp thêm instance để xử lý lượng yêu cầu tăng.
- Deployment phiên bản mới hoặc thay đổi cấu hình khiến worker/host khởi động lại.
- Host/worker bị thay thế do bảo trì, lỗi hoặc restart.
- Một trigger được kích hoạt ở một instance chưa load ứng dụng/worker tương ứng.

**Một Function App đang có lưu lượng vẫn có thể có cold start trên instance mới.** Vì vậy, cold start không chỉ là “request đầu tiên vào buổi sáng”.

### 14.1. Phân loại khởi động

| Loại | Mô tả | Tác động |
|---|---|---|
| **Warm invocation** | Worker và ứng dụng đã sẵn sàng | Thường không phải trả chi phí khởi tạo toàn bộ |
| **Cold start từ zero** | Không có môi trường ấm, cần cấp/khởi tạo | Request/event đầu có thể chờ |
| **Scale-out cold start** | Thêm instance khi tải tăng | Một phần yêu cầu trên instance mới chịu startup |
| **Restart/redeployment start** | Worker khởi động lại do deploy/config/health | Thời gian khởi tạo có thể xuất hiện |
| **Application lazy initialization** | Một thư viện/chức năng chỉ khởi tạo khi dùng lần đầu | Có thể tạo spike ngay cả trên worker đã chạy |

Cần đo đúng tầng, vì một request đầu tiên chậm có thể do DNS hoặc database cold cache chứ không nhất thiết do Functions platform.

## 15. Phân rã thời gian cold start

Một request có thể trải qua:

~~~mermaid
flowchart LR
    A[Event tới nền tảng] --> B[Chọn/cấp compute instance]
    B --> C[Khởi tạo Functions host]
    C --> D[Khởi tạo language worker / JVM]
    D --> E[Load app, classes, dependencies]
    E --> F[Khởi tạo clients, config, secrets]
    F --> G[Thực thi handler]
    G --> H[Downstream I/O]
    H --> I[Response / message completion]
~~~

Có thể chia phần đo thành:

\[
T_{\text{end-to-end}} =
T_{\text{routing/queue}} +
T_{\text{platform startup}} +
T_{\text{worker/app init}} +
T_{\text{execution}} +
T_{\text{network/downstream}}
\]

Không phải lúc nào bạn cũng đo độc lập được từng thành phần bằng log ứng dụng, vì một phần diễn ra trước khi code chạy. Cần kết hợp **client-side latency**, Azure Monitor/Functions metrics, host logs và timestamps do ứng dụng instrument.

### 15.1. Cold start không bằng execution time

Nếu Java method thực thi 100 ms nhưng client thấy 2 giây, phần chênh có thể đến từ startup, routing, handshake hoặc dependency trước khi timer ở method bắt đầu.

### 15.2. Warm request cũng có thể chậm

Database failover, VNet DNS, Key Vault latency, cold cache hoặc một truy vấn nặng vẫn khiến warm invocation chậm. Vì vậy, không kết luận mọi spike p99 là cold start.

### 15.3. Thời gian chờ trong queue

Queue trigger có thể chưa xử lý message vì backlog hoặc lock/visibility. Hãy đo **enqueue-to-start latency** và **processing duration** riêng; không gán toàn bộ thời gian chờ queue vào cold start.

## 16. So sánh các hosting plans theo mục tiêu latency

Azure Functions có nhiều lựa chọn hosting. Tính năng, trạng thái hỗ trợ, cấu hình luôn-ready, scale limit và giá có thể thay đổi theo thời điểm/region.

| Hướng hosting | Tư duy thiết kế | Tác động cold start và concurrency |
|---|---|---|
| **Consumption (classic)** | Tính phí theo sử dụng, có thể scale về zero | Cold start là rủi ro cần đo, một số khả năng mới có thể không được hỗ trợ giống Flex |
| **Flex Consumption** | Serverless mới với tùy chọn bộ nhớ, scaling và năng lực luôn sẵn sàng theo hỗ trợ | Có cơ chế HTTP concurrency riêng và khả năng always-ready để giảm latency |
| **Elastic Premium** | Có năng lực được chuẩn bị trước và tính năng hosting nâng cao | Pre-warmed/always-available capacity có thể giảm cold starts khi cấu hình phù hợp |
| **Dedicated/App Service plan** | Compute được cấp theo App Service plan | Với Always On và instances đang chạy, thường tránh startup do idle scale-to-zero nhưng vẫn có restart/deploy start |

**Không nên nói “Premium không bao giờ cold start” hoặc “Flex luôn nhanh hơn mọi plan khác”.** Nếu tải tăng vượt năng lực ấm, instance mới có thể cần khởi động. Mỗi plan có đặc điểm scale, network, instance memory, chi phí và hỗ trợ runtime khác nhau.

### 16.1. Chọn theo workload

- API yêu cầu p95 thấp, tải không đều: cân nhắc Flex Consumption với always-ready hoặc Premium, kiểm thử bằng dữ liệu thật.
- Queue worker có backlog không thường xuyên, cho phép xử lý trễ hơn: Consumption/Flex có thể phù hợp tùy triggers và chi phí.
- App chạy liên tục, tài nguyên tương đối ổn định: đánh giá Dedicated/App Service plan hoặc Premium.
- Có nhiều ứng dụng dùng chung môi trường và yêu cầu mạng enterprise: đánh giá Premium hoặc các lựa chọn có VNet/identity/scale phù hợp.

### 16.2. Không chọn plan chỉ theo giá mỗi invocation

Nếu mỗi cold start làm request vượt SLA, chi phí cho always-ready capacity có thể hợp lý. Ngược lại, nếu xử lý batch một lần mỗi ngày, giữ instance ấm 24/7 có thể lãng phí.

## 17. Always-ready, pre-warmed và Always On

Ba khái niệm này gần nhau về mục tiêu giảm thời gian khởi tạo nhưng thuộc những loại hosting/configuration khác nhau.

- **Always-ready instances**: trong các plan hỗ trợ như Flex Consumption, giữ một mức compute sẵn sàng theo cấu hình để giảm độ trễ khi có event.
- **Pre-warmed/ready capacity**: ở Premium, năng lực được chuẩn bị giúp phục vụ tải mới nhanh hơn tùy setup và scaling.
- **Always On**: ở Dedicated/App Service plan, giúp app không bị dừng vì idle theo cơ chế App Service.

### 17.1. Giữ ấm không bảo đảm p99 bằng nhau

Khi lưu lượng vượt mức compute sẵn có, nền tảng vẫn có thể scale-out và khởi tạo instance mới. Deployment, thay đổi cấu hình hoặc sự cố cũng có thể gây restart.

### 17.2. Lựa chọn kinh tế

Giả sử API chỉ nhận vài requests mỗi giờ nhưng có yêu cầu phản hồi luôn dưới một ngưỡng rất thấp. Phải cân nhắc:

1. Giữ ít nhất một instance ấm.
2. Tối ưu code và giảm dependency init.
3. Dùng async queue nếu nhiệm vụ không cần trả kết quả ngay.
4. Đánh giá App Service/Container Apps hoặc một hạ tầng đáp ứng latency phù hợp nếu yêu cầu ổn định hơn.
5. So sánh hóa đơn compute, networking, storage và monitoring.

**Không lạm dụng timer ping tự gọi HTTP endpoint để “giữ ấm”** như giải pháp bảo đảm SLA. Nó có thể không được hỗ trợ/không đáng tin cậy theo plan, làm tăng invocation cost, tạo số đo giả và vẫn không giữ ấm mọi instance mới.

## 18. Startup của Java Functions gồm những chi phí nào?

Một Java Function có thể cần:

1. Khởi tạo language worker/JVM.
2. Nạp classpath và các classes của ứng dụng.
3. Đọc annotations/function metadata.
4. Khởi tạo dependency injection nếu framework có dùng.
5. Khởi tạo SDK clients và connection pools.
6. Đọc cấu hình và bí mật cần thiết.
7. Thiết lập logging/telemetry.
8. JIT warm-up hoặc nạp thư viện chỉ dùng ở invocation đầu tiên.

Thời gian startup phụ thuộc vào version Java, gói ứng dụng, số dependency, tài nguyên CPU/memory và cách khởi tạo code. Không nên quy mọi độ trễ khởi tạo cho bản thân Azure Functions platform.

### 18.1. Thư viện nặng có thể làm cold start dài hơn

Nếu một Function chỉ nhận HTTP và ghi một message vào Queue nhưng kéo theo toàn bộ framework web lớn, ORM và hàng trăm dependencies không dùng tới, class loading và initialization có thể vượt nhu cầu thật.

### 18.2. JVM flags không phải thuốc chữa chung

Tùy chỉnh memory, heap, JIT hoặc những flags khác cần đối chiếu Java version và môi trường Functions hỗ trợ. Một flag tối ưu startup nhưng làm throughput warm giảm hoặc tăng RAM có thể tạo kết quả tổng thể tệ hơn.

### 18.3. Không init dependency không cần thiết

Nếu function chỉ gọi Blob Storage mà constructor lại mở đồng thời kết nối database, Service Bus, Key Vault và tải cấu hình lớn, cold path bị kéo dài và độ sẵn sàng phụ thuộc nhiều hệ thống không liên quan.

## 19. Nguyên tắc tối ưu thời gian khởi động Java

### 19.1. Giảm dependency

- Kiểm tra Maven/Gradle dependency graph trong dự án thật khi được phép.
- Loại các thư viện không dùng.
- Tránh trùng lặp logging backends và SDK versions.
- Dùng Azure SDK modules theo nhu cầu thay vì gom mọi dịch vụ không sử dụng.
- Kiểm tra cơ chế build/package không vô tình đưa dữ liệu mẫu hoặc file lớn.

### 19.2. Tách công việc khỏi cold path

- Không thực hiện migration database trong static initializer.
- Không tải nhiều MB cấu hình ở class initialization.
- Không gọi APIs bên ngoài không thiết yếu trước khi handler bắt đầu.
- Chỉ khởi tạo thành phần cần thiết ở thời điểm an toàn.

### 19.3. Tái sử dụng client phù hợp

Các SDK client thường hỗ trợ reuse và connection pooling. Thay vì tạo HTTP client mới cho từng invocation, có thể giữ một client được thiết kế thread-safe và quản lý lifecycle thích hợp.

Ví dụ minh họa:

~~~java
public final class ClientHolder {
    private ClientHolder() {}

    // Chi su dung client duoc thu vien xac nhan thread-safe.
    // Vi du gia dinh day la SDK client da duoc cau hinh.
    // static final SomeSdkClient CLIENT = buildClientFromIdentity();

    public static String getEndpoint() {
        return System.getenv("API_ENDPOINT");
    }
}
~~~

Không phải mọi client đều thread-safe; phải kiểm tra tài liệu của SDK được dùng, timeout, retry và cách refresh credentials. Nếu tạo client trong static initializer cần gọi dịch vụ ngoài, có thể đổi cold start nhanh thành cold start chậm.

### 19.4. Cân nhắc lazy initialization có chủ đích

Lazy init tránh khởi tạo thứ không sử dụng, nhưng chuyển một phần latency sang invocation đầu tiên cần thành phần đó. Nếu cần SLA nghiêm ngặt cho request đầu, có thể chủ động warm-up thành phần thiết yếu ở instance có capacity được chuẩn bị, khi hosting hỗ trợ và kiểm thử thấy hiệu quả.

**Không có một chiến lược initialization tốt nhất cho mọi Function.** Tối ưu phải dựa trên call graph thật và phân phối traffic theo endpoint.

## 20. Tối ưu package và quy trình triển khai

Cold start có thể liên quan đến việc runtime tải package, chuẩn bị filesystem, xác định metadata và load dependencies.

Những thực hành có ích:

- Gói triển khai chỉ gồm những artifact cần chạy.
- Tránh các file test, SDK docs, logs hoặc assets không cần thiết trong package.
- Dùng Functions runtime và Java version được Azure hỗ trợ ở plan mục tiêu.
- Quản lý dependencies và extension versions đồng bộ.
- Sử dụng cơ chế deploy package được Functions plan hỗ trợ thay vì tự xây bản copy file thủ công khó tái lập.
- Giữ cấu hình environment nhất quán giữa staging và production.
- Đánh giá ảnh hưởng của các thay đổi app settings làm worker restart.
- Không đẩy nhiều lần deploy nhỏ không cần thiết vào giờ cao điểm.

### 20.1. Image container tùy chỉnh

Một số hosting plans cho phép triển khai Functions dưới dạng container image. Trong trường hợp đó, image size, layers, registry locality và thời gian pull cũng ảnh hưởng startup.

Nhưng **không phải mọi hosting plan đều hỗ trợ custom container giống nhau**. Hãy xác nhận tính năng trước khi quyết định dùng container chỉ để tối ưu cold start.

### 20.2. Version của gói phải được truy vết

Ghi lại Git commit, function package/image digest, Java/runtime version, extension versions và app settings revision để có thể đối chiếu latency trước/sau mỗi thay đổi.

## 21. Networking và dependency latency dễ bị nhầm là cold start

Một function có thể chạy trên warm worker nhưng request vẫn bị chậm do:

- DNS lookup hoặc TLS handshake đến database/API.
- Kết nối mới vì connection pool chưa có.
- NAT/SNAT port exhaustion.
- Azure SQL hoặc Cosmos DB đang throttling.
- Storage/Service Bus latency tăng.
- Private endpoint/VNet integration sai.
- Key Vault call trên đường xử lý.
- Firewall hoặc route làm timeout.
- Proxy, connection reset hoặc retry kéo dài.

### 21.1. Phân biệt bằng phép đo

Instrument các mốc:

~~~text
Client request received
  -> Function handler entered
  -> Acquire database connection
  -> Execute query
  -> Serialize response
  -> Function handler returned
  -> Client response completed
~~~

Nếu handler mất 80 ms nhưng client mất 1.500 ms, cần kiểm tra những phần ngoài handler. Nếu handler mất 1.200 ms và dependency trace cho thấy database query chiếm 1.100 ms, đó **không phải vấn đề có thể giải quyết chỉ bằng keep-warm**.

### 21.2. Kết nối mạng an toàn vẫn quan trọng

Không tắt TLS, private networking hoặc authentication chỉ để tiết kiệm vài ms. Dùng connection reuse, DNS/connection timeout hợp lý và điểm triển khai phù hợp region để giảm latency mà vẫn bảo vệ dữ liệu.

## 22. HTTP APIs: thiết kế cho cold start và p99

### 22.1. Trả kết quả nhanh khi công việc ngắn

Với các thao tác GET/POST nhẹ, giảm thời gian xử lý, tránh blocking và tái sử dụng SDK clients.

### 22.2. Đẩy xử lý nặng sang bất đồng bộ

Một ví dụ kiến trúc:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant H as HTTP Function
    participant Q as Azure Queue
    participant W as Queue Function
    participant S as Blob Storage
    C->>H: POST /reports
    H->>Q: Enqueue report job
    H-->>C: 202 + operationId
    W->>Q: Trigger nhận message
    W->>S: Ghi report output
    C->>H: GET /reports/{id}
    H-->>C: Trạng thái / output
~~~

Ưu điểm:

- HTTP request không cần đợi job nhiều phút.
- Worker concurrency được điều khiển độc lập.
- Có thể retry xử lý khi thất bại.
- Có thể đo queue wait time và processing time riêng.

Hệ thống phải cung cấp operation ID, trạng thái bền vững và idempotency khi client gửi lại request.

### 22.3. Đặt timeout và circuit breaker

Nếu function gọi một API ngoài, nên đặt timeout rõ ràng, retry có giới hạn/jitter khi phù hợp và circuit breaker để tránh giữ vô số concurrent invocations chờ dịch vụ đã lỗi.

### 22.4. Hạn chế synchronous bottleneck

Trong Java, dùng HttpClient/SDK theo đặc tính non-blocking hoặc blocking mà runtime hỗ trợ. Chọn async không tự cải thiện tốc độ CPU-bound; một tác vụ tính toán nặng vẫn cần tài nguyên CPU.

## 23. Queue workloads: tối ưu throughput mà không làm mất tính đúng

Một queue worker cần các chỉ số:

- **Backlog length:** số jobs đang chờ.
- **Oldest message age:** jobs chờ lâu đến mức nào.
- **Processing duration:** thời gian thực thi mỗi job.
- **Completion throughput:** số jobs hoàn tất/giây.
- **Failure/retry rate:** tỷ lệ cần chạy lại.
- **Poison/dead-letter count:** số jobs không thể xử lý bình thường.
- **Downstream latency:** database/API/Storage đang đáp ứng thế nào.

### 23.1. Concurrency thấp có thể là đúng

Nếu mỗi job ghi vào một bảng có lock contention lớn, concurrency bằng 4 có thể có throughput thực cao hơn 20 do ít retry và ít deadlocks hơn.

### 23.2. Concurrency cao phù hợp tác vụ độc lập

Xử lý nhiều ảnh nhỏ chỉ đọc Blob và ghi output độc lập có thể tận dụng concurrency cao hơn, miễn CPU, memory, network và Storage throughput đủ.

### 23.3. Bắt buộc xử lý duplicate

Thiết kế idempotent với:

- Job ID duy nhất.
- Unique constraint hoặc idempotency key.
- Transaction đảm bảo trạng thái hoàn thành.
- Output name ổn định theo job ID.
- Cơ chế tránh race khi hai invocations xử lý cùng key.

**Không giả định serverless queues cung cấp exactly-once end-to-end**. Một lần function invocation thành công chưa chắc client biết message đã được complete nếu có sự cố mạng.

## 24. Backpressure và giới hạn downstream concurrency

Một cơ chế mở rộng tốt phải tránh làm quá tải hệ thống dữ liệu.

Ví dụ:

~~~text
Azure Functions:
  6 instances x 12 concurrent invocations = 72 in-flight jobs

Database:
  chỉ phù hợp 30 kết nối/transaction nặng đồng thời
~~~

Nếu mỗi invocation mở một kết nối đồng thời, tổng tải có thể vượt giới hạn database.

### 24.1. Các chiến lược bảo vệ

- Giảm per-instance concurrency hoặc batch size.
- Đặt max connections của HTTP/DB client pool.
- Dùng semaphore/queue nội bộ **trong process** để giới hạn tài nguyên cục bộ.
- Dùng queue để hấp thụ traffic burst và phân phối công việc.
- Đặt rate limit/throttling trên gateway hoặc API.
- Dùng retry với exponential backoff và jitter, có giới hạn.
- Áp dụng circuit breaker khi dependency lỗi.
- Cân nhắc giới hạn scale-out/instance capacity theo khả năng hosting plan.
- Dùng durable workflow/checkpoint với tác vụ dài.

### 24.2. Giới hạn trong process không phải giới hạn toàn hệ thống

Một **Semaphore(5)** trong mỗi Java worker chỉ giới hạn 5 operations tại **worker đó**. Nếu nền tảng scale lên 10 workers, có thể vẫn có đến 50 operations cùng lúc. Với giới hạn toàn hệ thống, cần cơ chế phân phối hoặc chính sách scale/rate limit được thiết kế tương ứng.

### 24.3. Timeout và retry có thể làm quá tải tăng thêm

Nếu một API chậm, hàng trăm invocations retry đồng loạt có thể tạo **retry storm**. Hãy dùng backoff, jitter, tổng retry budget và deadline; không retry vô hạn mọi lỗi 4xx/5xx.

## 25. Java Azure Function: ví dụ HTTP trigger đơn giản

Một ví dụ sử dụng thư viện Azure Functions Java annotations trong dự án Java Functions đã cấu hình sẵn:

~~~java
package example.functions;

import com.microsoft.azure.functions.*;
import com.microsoft.azure.functions.annotation.*;

import java.util.Optional;

public class HelloFunction {

    @FunctionName("hello")
    public HttpResponseMessage run(
            @HttpTrigger(
                name = "req",
                methods = {HttpMethod.GET},
                authLevel = AuthorizationLevel.FUNCTION)
            HttpRequestMessage<Optional<String>> request,
            final ExecutionContext context) {

        String name = request.getQueryParameters()
                .getOrDefault("name", "Azure");

        context.getLogger().info("Hello function invoked");

        return request.createResponseBuilder(HttpStatus.OK)
                .body("Xin chao " + name)
                .build();
    }
}
~~~

### 25.1. Ví dụ thể hiện điều gì?

- **@FunctionName** đặt tên function.
- **@HttpTrigger** khai báo HTTP trigger.
- **AuthorizationLevel.FUNCTION** yêu cầu key khi gọi endpoint được bảo vệ, tùy cơ chế Functions; nó không phải hệ thống xác thực người dùng thay cho Microsoft Entra ID.
- **ExecutionContext** cung cấp logger và metadata hữu ích.
- Handler không mở database, đọc nhiều file hoặc tạo thread pool không cần thiết trong mỗi invocation.

### 25.2. Không hardcode secret vào code

Khi ứng dụng thật truy cập Azure Storage hoặc Key Vault, nên dùng managed identity/DefaultAzureCredential trong phạm vi SDK và hosting support, cấp Azure RBAC đúng data-plane role.

### 25.3. Không dùng ví dụ này để ước tính cold start production

Ví dụ nhỏ có thể bắt đầu nhanh nhưng ứng dụng thực có SDK, dependency injection, TLS/database initialization và nhiều functions. Hãy đo package thật của ứng dụng.

## 26. Đo concurrent executions trong Java worker

Dưới đây là cách đo **số invocations đang thực thi trong một Java worker process** để hiểu concurrency. Đây là instrumentation minh họa, không phải cơ chế cấu hình scale toàn Function App.

~~~java
package example.functions;

import java.util.concurrent.atomic.AtomicInteger;

public final class ConcurrencyGauge {
    private static final AtomicInteger IN_FLIGHT =
            new AtomicInteger(0);
    private static final AtomicInteger MAX_SEEN =
            new AtomicInteger(0);

    private ConcurrencyGauge() {}

    public static int enter() {
        int current = IN_FLIGHT.incrementAndGet();
        MAX_SEEN.accumulateAndGet(current, Math::max);
        return current;
    }

    public static void leave() {
        IN_FLIGHT.decrementAndGet();
    }

    public static int maxSeen() {
        return MAX_SEEN.get();
    }
}
~~~

Trong handler:

~~~java
int concurrentNow = ConcurrencyGauge.enter();

try {
    context.getLogger().info(
            "Concurrent invocations in this process: " + concurrentNow);
    // Xu ly nghiep vu.
} finally {
    ConcurrencyGauge.leave();
}
~~~

**Quan trọng:**

- Đây chỉ là số đo **nội bộ một JVM process**, không phải concurrency của toàn Azure Functions app.
- Nếu runtime tạo nhiều worker processes/instances, mỗi process có biến static riêng.
- Logging mỗi invocation ở throughput cao có thể làm tăng chi phí và latency; nên dùng metric sampling/aggregation thích hợp.
- Không dùng số đo này làm giới hạn giao dịch phân tán.

Có thể gắn thêm một ID process/instance an toàn để phân tích per-instance observations, nhưng tránh log secrets, tokens hoặc dữ liệu người dùng nhạy cảm.

## 27. Phân biệt cold start và warm execution bằng telemetry

Không có một phép đo application-side nào tự phản ánh trọn vẹn thời gian platform cấp compute trước khi code chạy. Một cách thực dụng là kết hợp:

1. **Client-side latency**: từ khi gửi HTTP đến khi nhận response.
2. **Function invocation duration**: thời gian host/runtime và telemetry quan sát.
3. **Application handler timing**: thời gian code thực thi.
4. **Worker/process startup marker**: dấu hiệu JVM/class đã khởi tạo lần đầu.
5. **Downstream dependencies**: thời gian DB/HTTP/Storage calls.
6. **Instance counts**: biến động instance trước/sau các đợt traffic.

### 27.1. Dấu hiệu gợi ý cold start

- Request đầu sau thời gian idle chậm hơn warm requests.
- Trước invocation có log worker/JVM startup.
- Latency spike trùng thời điểm scale-out hoặc deploy.
- Một số instances có execution đầu tiên chậm hơn những execution tiếp theo.

**Đây là suy luận có bằng chứng, không phải định nghĩa tuyệt đối.** Nếu database cold cache trùng thời điểm request đầu, cần phân tách các nguyên nhân.

### 27.2. Theo dõi percentile thay vì chỉ average

Ví dụ:

~~~text
p50 = 110 ms
p95 = 380 ms
p99 = 2.100 ms
mean = 170 ms
~~~

Mean có thể trông tốt trong khi 1% requests có độ trễ rất lớn. Với ứng dụng tương tác, hãy đặt SLO theo p95/p99 hoặc mức phù hợp thay vì chỉ xem trung bình.

### 27.3. Tách theo route, version và plan

Nếu gộp 10 endpoints vào một nhóm latency, endpoint nặng có thể che endpoint nhẹ. Phân tích riêng theo function name, môi trường, package version, hosting plan và traffic shape.

## 28. Dùng Azure Monitor và Application Insights

Có thể giám sát Azure Functions với **Azure Monitor/Application Insights** theo mô hình telemetry được cấu hình. Một số Function Apps dùng workspace-based Application Insights với bảng Log Analytics **AppRequests** và **AppDependencies**; những môi trường cũ hoặc giao diện khác có thể dùng các bảng/schema tên khác.

Ví dụ KQL cho môi trường có bảng **AppRequests**:

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    requests = count(),
    failures = countif(Success == false),
    p50_ms = percentile(DurationMs, 50),
    p95_ms = percentile(DurationMs, 95),
    p99_ms = percentile(DurationMs, 99)
  by bin(TimeGenerated, 5m), Name
| order by TimeGenerated asc
~~~

**Lệnh query chỉ chạy khi có telemetry đúng schema và dữ liệu.** Nếu workspace dùng bảng khác, hãy kiểm tra schema thực tế; đừng tự đổi tên trường một cách tùy tiện.

### 28.1. Phân tích dependency

Dùng dependency telemetry để tìm các phần chậm như:

- Azure SQL query.
- Cosmos DB request.
- Blob upload/download.
- Service Bus send.
- HTTP call đến dịch vụ ngoài.
- Key Vault read.

Thời gian function invocation và client-side latency phải được so sánh với dependency duration.

### 28.2. Theo dõi scale và cold start

Các metric và log khả dụng có thể khác theo hosting plan/runtime. Nên theo dõi:

- Invocation count và error rate.
- Duration percentiles.
- Instance count hoặc tín hiệu scale.
- Cold start indicators/worker startup logs khi có.
- Memory/CPU và host health.
- Queue backlog/oldest message age.
- HTTP 429/5xx, database throttling và retry count.
- Chi phí compute, always-ready/plan, network và Log Analytics ingestion.

### 28.3. Không biến logging thành nút cổ chai

Log toàn bộ request/response body có thể tăng chi phí, thời gian serialization và rủi ro lộ dữ liệu. Hãy dùng sampling có kiểm soát, correlation IDs và log ở những mốc hữu ích. Khi đánh giá p99 rất hiếm, cần hiểu sampling có thể làm mất những sự kiện quan trọng.

## 29. Thí nghiệm: đo cold start trước khi tối ưu

Một thí nghiệm tốt cần có **baseline** và điều kiện so sánh công bằng.

### 29.1. Chuẩn bị

1. Chọn một Azure Function App trong resource group thử nghiệm.
2. Ghi rõ hosting plan, runtime version, region, memory size và trigger.
3. Ghi package/image version, dependencies và app settings liên quan.
4. Chọn endpoint HTTP đơn giản và một endpoint gọi downstream thực, nếu có.
5. Bật telemetry và chọn client đo latency.
6. Chuẩn bị giới hạn số requests để không tạo chi phí hoặc tải quá mức.

### 29.2. Thí nghiệm A — Warm steady load

1. Gọi function một số lần để môi trường chạy ổn định.
2. Gửi các requests ở tốc độ thấp, cố định.
3. Đo p50/p95/p99, error rate và throughput.
4. Lưu latency handler và dependency.
5. Ghi số instances và concurrency thực tế nếu quan sát được.

### 29.3. Thí nghiệm B — After idle

1. Chờ thời gian idle phù hợp với plan có thể scale-to-zero.
2. Gửi một request đầu tiên rồi một chuỗi requests tiếp theo.
3. So sánh client latency và handler timing.
4. Đối chiếu startup logs hoặc instance signals.
5. Lặp lại nhiều lần, vì một mẫu đơn lẻ không đủ chứng minh cold start.

**Không dùng thời gian idle cố định để khẳng định Azure chắc chắn đã scale về zero.** Cơ chế scale-in phụ thuộc platform, plan và traffic; phải xác nhận bằng tín hiệu phù hợp nếu có.

### 29.4. Thí nghiệm C — Burst/scale-out

1. Tăng load theo bậc có kiểm soát.
2. Đo thời gian request bắt đầu tăng.
3. Quan sát scale-out và khả năng thêm instance.
4. Ghi các khoảng latency spike/timeout.
5. Quan sát CPU, memory, downstream và retry rate.
6. Giảm tải và xem hệ thống phục hồi ra sao.

### 29.5. Thí nghiệm D — Thay một yếu tố

Ví dụ:

- Bỏ một dependency không dùng.
- Chuyển client SDK từ tạo mỗi lần sang reuse.
- Thay memory/plan khi được hỗ trợ.
- Điều chỉnh HTTP concurrency theo plan.
- Chuyển queue trigger sang dynamic concurrency khi có hỗ trợ.

Chỉ thay **một yếu tố chính** mỗi vòng để tránh kết luận sai. Cần tính cả giá: một thay đổi giảm p99 nhưng tăng chi phí gấp nhiều lần có thể không đáng đối với workload đó.

## 30. Thiết kế load test an toàn

Để kiểm thử concurrency, có thể dùng công cụ load testing được tổ chức cho phép hoặc một client phát requests. Mô hình nên gồm:

- **Constant arrival rate**: gửi request ở tốc độ cố định để đo SLO.
- **Step load**: tăng tải theo các mức và quan sát scale-out.
- **Spike**: tải đột biến ngắn để kiểm tra startup/capacity dự phòng.
- **Soak test**: tải duy trì để tìm memory leak, pool exhaustion và chi phí.
- **Recovery test**: hạ tải, kiểm tra error rate/latency phục hồi.

Ví dụ kế hoạch:

| Giai đoạn | Lưu lượng gợi ý | Thời lượng | Quan sát |
|---|---:|---|---|
| Baseline | 2 req/s | Một khoảng đủ lấy mẫu | Warm latency |
| Step 1 | 10 req/s | Đủ quan sát | Concurrency |
| Step 2 | 30 req/s | Đủ quan sát | Scale và downstream |
| Spike | 60 req/s trong thời gian ngắn | Có giới hạn | p99, 429/5xx |
| Recovery | 2 req/s | Đủ quan sát | Hồi phục |

Những con số chỉ là ví dụ, không phải mức tải được phép cho mọi môi trường. Chỉ test trong subscription/app được phê duyệt; tránh làm ảnh hưởng cơ sở dữ liệu hoặc dịch vụ dùng chung.

### 30.1. Tránh coordinated omission

Nếu công cụ test chỉ phát request sau khi response trước kết thúc, lúc hệ thống chậm nó sẽ vô tình **giảm** tốc độ gửi và che mất độ trễ của hàng đợi. Với workload có yêu cầu arrival rate, cần công cụ và phương pháp đo không bỏ qua các yêu cầu đáng lẽ xuất hiện trong giai đoạn nghẽn.

### 30.2. Dùng percentile theo cửa sổ thời gian

p99 của cả bài test có thể che spike trong thời gian scale-out. Hãy xem p95/p99 theo từng khoảng 1–5 phút, đồng thời đối chiếu instance/worker startup events.

## 31. Kịch bản tính toán: API Java cần p95 thấp

Giả sử một API Java có các số liệu thử nghiệm:

| Chỉ số | Baseline |
|---|---:|
| Thời gian xử lý warm trung bình | 220 ms |
| p95 warm | 410 ms |
| p99 ở tải thấp | 2.400 ms |
| CPU cao nhất ở burst | 82% |
| Cold/startup indicators | Xuất hiện ở các thời điểm tăng instance |
| Yêu cầu sản phẩm | p95 dưới 700 ms trong điều kiện định nghĩa |

Những giá trị chỉ để minh họa cách ra quyết định, không phải performance công bố của Azure Functions.

### 31.1. Giả thuyết thứ nhất

Các p99 spikes có thể liên quan đến cold start khi instance mới. Kiểm chứng bằng worker startup logs, thời gian scale-out, client latency và handler/dependency traces.

### 31.2. Thử tối ưu không đổi plan

- Loại dependencies không dùng.
- Không tải cấu hình lớn ở static initializer.
- Reuse SDK clients/HTTP connections đúng cách.
- Giảm các calls đến Key Vault/Storage khỏi đường khởi tạo không cần thiết.
- Phân tách API response khỏi tác vụ dài bằng Queue.

Đo lại bằng cùng profile, không chỉ lấy request nhanh nhất để so sánh.

### 31.3. Thử điều chỉnh capacity

Nếu SLO vẫn bị vi phạm và plan cho phép, đánh giá always-ready/pre-warmed capacity hoặc plan khác. So sánh p95/p99, số instance, warm capacity và chi phí. Nếu API vốn luôn bận, có thể tối ưu concurrency hoặc VM/memory thay vì trả phí cho idle-ready capacity không cần.

### 31.4. Kết luận theo SLO

Một giải pháp tốt là phương án có **chi phí hợp lý nhất** mà vẫn đạt SLO và giữ error rate, bảo mật, khả năng vận hành và độ tin cậy theo yêu cầu. Đừng chọn cấu hình chỉ vì bảng benchmark cho thời gian trung bình thấp nhất.

## 32. Kịch bản tính toán: queue worker xử lý 100.000 jobs

Giả sử một worker xử lý trung bình 400 ms/job, có 5 instances và concurrency thực tế 6 jobs/instance:

\[
\text{Thông lượng lý thuyết}
\approx \frac{5\times6}{0{,}4}=75\text{ jobs/s}
\]

Với 100.000 jobs, thời gian lý tưởng là:

\[
100000/75\approx1333\text{ giây}\approx22{,}2\text{ phút}
\]

Giả định này chưa tính thời gian scale-out, cold starts, retries, kích thước message, I/O, locks và giới hạn downstream.

### 32.1. Nếu database chỉ chịu 20 operations đồng thời

30 jobs cùng hoạt động có thể gây lock contention và timeout. Tổng throughput thực tế có thể thấp hơn 75 jobs/s.

Giải pháp đánh giá:

- Giảm concurrency xuống mức database chịu được.
- Giảm thời gian DB transaction bằng truy vấn/index phù hợp.
- Dùng queue partitioning hoặc nhiều luồng theo key nếu cần ordering.
- Tăng downstream capacity nếu có cơ sở đo và ngân sách.
- Kiểm tra retry rate, latency và chi phí thay vì chỉ số worker.

### 32.2. Nếu job CPU-bound

Nhiều threads trên instance có ít vCPU có thể không cải thiện throughput. Tăng CPU/memory của instance hoặc scale-out có thể hiệu quả hơn tăng per-instance concurrency, nhưng vẫn phải đo.

### 32.3. Nếu job I/O-bound

Concurrency cao hơn có thể che latency khi chờ I/O. Tuy nhiên vẫn bị giới hạn bởi network sockets, connections, API rate limits và bộ nhớ.

## 33. Local development và Azure thật khác nhau thế nào?

Để phát triển Azure Functions ở máy cá nhân, có thể dùng **Azure Functions Core Tools** và local runtime, tùy Java version và cấu hình dự án. Trong ví dụ dự án Java Functions đã thiết lập, có thể chạy:

~~~bash
func start
~~~

Hoặc sử dụng lệnh Maven plugin tương ứng khi dự án đã cấu hình plugin. **Đây không phải hướng dẫn tạo project Java Functions từ đầu**, chỉ là minh họa cho bước chạy local sau khi build và chuẩn bị config.

### 33.1. local.settings.json

Một file local settings ví dụ:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "java"
  }
}
~~~

**UseDevelopmentStorage=true** chỉ phù hợp khi emulator như Azurite được chạy và trigger/runtime cần Storage. Không dùng chuỗi này làm credential production. Không commit local.settings.json có secrets.

### 33.2. Những gì local có thể kiểm thử

- Function binding và logic.
- HTTP handler.
- Queue trigger với emulator hoặc tài nguyên thử nghiệm theo yêu cầu.
- Thread-safety của một phần code.
- Dependency initialization và application startup.
- Độ đúng chức năng và một số kiểm thử concurrency.

### 33.3. Những gì local không tái hiện đầy đủ

- Azure platform scale-out/scale-in thực tế.
- Cold start do compute provisioning của hosting plan.
- Always-ready/prewarmed behavior.
- VNet integration/private DNS và network capacity tương tự production.
- Cloud identity/RBAC và throttling thật.
- Billing, quota và khả năng chịu tải của region.

Vì vậy, **local test không thể chứng minh p99 cold start của Azure hosting plan**. Cần kiểm thử trên plan/region/runtime gần với production.

## 34. Bảo mật khi tối ưu concurrency và startup

Hiệu năng không được đánh đổi bằng việc giảm bảo mật một cách thiếu kiểm soát.

### 34.1. Không tắt authentication để giảm startup

Bỏ Microsoft Entra ID hoặc function keys khỏi endpoint để tăng tốc là hướng sai. Nếu auth/token acquisition gây chậm, kiểm tra token caching, connection reuse, cấu hình RBAC và vị trí dịch vụ.

### 34.2. Hạn chế secret trong app settings

App settings có thể chứa cấu hình nhạy cảm; quyền truy cập và logging cần được quản lý. Khi hỗ trợ, ưu tiên managed identity, Azure Key Vault và các SDK có credential chain phù hợp.

### 34.3. Chú ý quyền của queue workers

Tăng số concurrent invocations làm tăng số thao tác Storage/Service Bus/DB. Danh tính app vẫn chỉ cần quyền tối thiểu ở scope phù hợp; không cấp Owner subscription để giải quyết lỗi permission.

### 34.4. Logging và dữ liệu nhạy cảm

Đo latency bằng correlation ID, endpoint name và duration; không log request body, access token, cookie, connection strings hay PII nếu không có mục đích và kiểm soát phù hợp.

### 34.5. Cold start có thể làm lộ lỗi cấu hình

Một ứng dụng có thể chạy tốt khi token/cache đang còn, nhưng khi instance mới khởi động thì thất bại vì private DNS, RBAC hoặc secret đã thay đổi. Đây là lỗi vận hành cần sửa gốc, không phải lý do để giữ instance ấm mãi mãi.

## 35. Những lỗi và hiểu nhầm thường gặp

### 35.1. “Tăng concurrency luôn làm Function nhanh hơn”

Sai. Với CPU-bound code hoặc database có giới hạn, quá nhiều concurrency tạo contention, queueing và retry. Cần đo throughput **và** p95/p99/error rate.

### 35.2. “Tăng số worker processes luôn xóa cold start”

Sai. Nhiều Java worker processes có thể tăng memory, initialization và số connection pools. Worker process count khác số instances.

### 35.3. “Chỉ có request đầu tiên mới cold start”

Sai. Scale-out, restart hoặc deploy có thể tạo thêm worker mới trong lúc app vẫn có traffic.

### 35.4. “Bật dynamic concurrency là mọi trigger được tối ưu”

Sai. Dynamic concurrency chỉ áp dụng đúng các triggers/extensions được hỗ trợ; HTTP và những kiểu trigger khác có logic riêng. Runtime không biết hết giới hạn downstream.

### 35.5. “Đặt functionTimeout rất cao là giải pháp HTTP timeout”

Sai. HTTP request còn chịu giới hạn của client, gateway và platform. Dùng async pattern cho công việc dài.

### 35.6. “Warm execution chậm nghĩa là cold start”

Không nhất thiết. Có thể do DNS, DB, network, Key Vault, throttling hoặc GC.

### 35.7. “Không có lỗi nhưng queue backlog vẫn tăng thì scale-out chưa đủ”

Có thể thiếu throughput, nhưng cũng có thể message locking, downstream bottleneck hoặc trigger cấu hình sai. Cần đo age và processing time.

### 35.8. “Always-ready miễn phí khi không có request”

Không thể giả định. Năng lực giữ sẵn có thể phát sinh phí theo plan/thiết lập; tính tổng chi phí trước khi bật.

### 35.9. “Local Functions benchmark phản ánh trực tiếp production”

Không. Local không mô phỏng đầy đủ scale controller, platform startup, mạng và cloud dependencies.

### 35.10. “p50 tốt thì trải nghiệm người dùng tốt”

Không đủ. Một phần nhỏ requests có p99 cao có thể ảnh hưởng trực tiếp giao dịch quan trọng. SLO nên phản ánh chất lượng thực của người dùng.

## 36. Quy trình xử lý sự cố khi p99 tăng

### Bước 1 — Xác định thời điểm

P99 tăng sau deploy, sau idle, trong burst hay xuyên suốt? Có trùng với thay đổi app settings hoặc hosting plan không?

### Bước 2 — Tách request groups

Phân tích theo function name, endpoint, environment, package version và region.

### Bước 3 — Đối chiếu logs và metrics

Xem instance changes, worker startup, function duration, dependencies, errors, CPU/memory và queue backlog.

### Bước 4 — Kiểm tra cold-path code

Tìm static initialization nặng, dependency injection, file/class loading, Key Vault call, token acquisition và HTTP client creation.

### Bước 5 — Kiểm tra concurrency

Xem actual in-flight work, thread pools, HTTP concurrency settings, host.json, dynamic concurrency, DB connection count và retry rate.

### Bước 6 — So sánh kế hoạch hosting

Có cần always-ready/prewarmed capacity không? Memory/instance size có đủ không? Có phải một số cold starts xuất hiện do scale-out bình thường?

### Bước 7 — Thay đổi một yếu tố

Thử loại dependency, reuse client, giảm concurrency, điều chỉnh memory/plan hoặc tối ưu downstream, rồi đo lại cùng workload.

### Bước 8 — Xác nhận SLO và chi phí

Không chỉ báo giảm latency trung bình; cần p95/p99, error rate, throughput, backlog và tổng chi phí.

## 37. Bài thực hành có kiểm soát

**Bối cảnh:** một API Java dùng HTTP trigger để nhận yêu cầu tạo báo cáo, sau đó worker xử lý Queue message và lưu kết quả ở Blob Storage. Bạn cần xác định cold start xuất hiện ở đâu và tối ưu concurrency không làm database quá tải.

### Phần A — Vẽ đường xử lý

1. Vẽ Client → HTTP Function → Queue → Queue Function → Blob/Database.
2. Ghi rõ request nào cần trả ngay và công việc nào có thể chạy nền.
3. Xác định dữ liệu cần idempotency key và nơi lưu trạng thái job.
4. Liệt kê những dependency có thể gây latency ở mỗi bước.

### Phần B — Chuẩn bị môi trường

1. Tạo Function App thử nghiệm trên plan được phê duyệt.
2. Ghi runtime Java, plan, instance memory, region và app version.
3. Bật Application Insights/Azure Monitor với sampling phù hợp.
4. Sử dụng dữ liệu giả, không gọi production database ngoài phép thử.
5. Thiết lập ngân sách và giới hạn requests/concurrency để tránh bùng nổ chi phí.

### Phần C — Đo baseline

1. Chạy một số requests warm.
2. Đo client latency, function duration, p50/p95/p99 và lỗi.
3. Đo phần dependency.
4. Ghi các mốc worker/instance startup nếu có.
5. Chạy thử sau idle khi plan có khả năng scale-to-zero; không mặc định chắc chắn scale-to-zero chỉ vì chờ một khoảng cố định.

### Phần D — Kiểm tra concurrency

1. Tạo tải theo từng bước nhỏ, có giới hạn.
2. Đo in-flight executions trên từng worker nếu đã instrument.
3. Ghi CPU/memory, queue backlog và database connections.
4. Điều chỉnh fixed hoặc dynamic concurrency cho trigger được hỗ trợ.
5. Đo lại p95/p99, throughput và số retries.
6. Dừng test nếu error rate hoặc database load vượt ngưỡng an toàn.

### Phần E — Tối ưu startup

1. Xác định dependency/class loading hoặc initialization tốn thời gian.
2. Loại thư viện không dùng hoặc tách startup tasks không thiết yếu.
3. Thử reuse SDK clients đúng cách.
4. So sánh package sizes và startup logs trước/sau.
5. Nếu vẫn cần p99 thấp hơn, đánh giá plan/memory/always-ready settings theo hỗ trợ và ngân sách.

### Phần F — Mô phỏng lỗi

1. Giới hạn một dependency thử nghiệm để quan sát timeout và backpressure.
2. Kiểm tra retry không tăng vô hạn.
3. Cho queue worker xử lý lại một job để xác minh idempotency.
4. Ghi latency phân tách: queue wait, processing, downstream.
5. Phục hồi mọi cấu hình test về mức an toàn.

### Phần G — Báo cáo

Lập bảng:

| Chỉ số | Baseline | Sau tối ưu | Nhận xét |
|---|---:|---:|---|
| Warm p50 | Giá trị đo | Giá trị đo | Có thay đổi không? |
| p95/p99 | Giá trị đo | Giá trị đo | SLO đạt chưa? |
| Time-to-first-result | Giá trị đo | Giá trị đo | Cold start được giảm không? |
| Throughput | Giá trị đo | Giá trị đo | Tăng thật hay chỉ queue nhanh hơn? |
| Error/retry rate | Giá trị đo | Giá trị đo | Có xấu đi không? |
| DB connections | Giá trị đo | Giá trị đo | Có vượt giới hạn không? |
| Instance count | Giá trị đo | Giá trị đo | Scale-out ảnh hưởng thế nào? |
| Chi phí | Giá trị đo | Giá trị đo | Lợi ích có đáng giá? |

**Tiêu chí hoàn thành:** giải thích được spike latency bằng telemetry, chỉ ra cấu hình concurrency của đúng trigger, chứng minh một thay đổi cải thiện SLO mà không làm tăng lỗi hoặc vi phạm giới hạn downstream.

## 38. Checklist trước khi triển khai Azure Functions production

- [ ] Đã chọn hosting plan theo latency SLO, trigger type, region và chi phí.
- [ ] Đã phân biệt HTTP concurrency, trigger-specific concurrency và scale-out.
- [ ] Runtime/extension/Java versions được pin và kiểm thử phù hợp.
- [ ] Host.json settings đúng với extension version và dynamic concurrency behavior.
- [ ] Mức per-instance concurrency được load test, không chọn ngẫu nhiên.
- [ ] CPU, memory, thread pool và DB/API connection pools được giám sát.
- [ ] Không có shared mutable state không thread-safe trong Java worker.
- [ ] HTTP công việc dài đã chuyển sang Queue/Durable pattern khi phù hợp.
- [ ] Có timeout, bounded retries, exponential backoff và circuit breaker.
- [ ] Queue workers có idempotency, poison handling và checkpoint khi cần.
- [ ] App package không chứa dependencies hoặc dữ liệu thừa.
- [ ] Startup không thực hiện migration hoặc network calls không thiết yếu.
- [ ] SDK clients được reuse đúng theo tài liệu thread-safety.
- [ ] App settings/secret/identity được bảo vệ và không log dữ liệu nhạy cảm.
- [ ] Monitoring có p50/p95/p99, error rate, throughput và dependencies.
- [ ] Có quan sát scale/cold start và phân biệt handler time với client time.
- [ ] Đã kiểm thử traffic after-idle, burst, steady và recovery trong môi trường hợp lệ.
- [ ] Có quy trình rollback nếu deployment làm tăng cold start hoặc lỗi.
- [ ] Đã dự toán compute, always-ready, Storage/Service Bus, networking và telemetry cost.
- [ ] Không dùng timer ping như biện pháp đảm bảo cold start bằng zero.
- [ ] Có runbook điều tra p99 và cảnh báo SLO, không chỉ CPU.

## 39. Câu hỏi tự kiểm tra

1. Concurrency và scale-out khác nhau về phạm vi nào?
2. Vì sao thông lượng không tăng tuyến tính khi số invocations tăng?
3. Cold start chỉ xảy ra sau thời gian idle hay có thể xảy ra khi scale-out?
4. Phân biệt warm invocation, platform cold start và application lazy initialization.
5. HTTP concurrency được điều chỉnh theo những thành phần nào?
6. Queue batchSize và Service Bus maxConcurrentCalls có dùng chung một cơ chế không?
7. Dynamic concurrency được hỗ trợ cho mọi trigger không? Nó khác scale controller như thế nào?
8. Khi dùng dynamic concurrency, điều gì có thể xảy ra với các ngưỡng fixed concurrency?
9. Vì sao một function với handler 80 ms vẫn có client latency 1.500 ms?
10. p95/p99 hữu ích thế nào so với mean latency?
11. Khi nào always-ready/prewarmed capacity có thể đáng chi phí?
12. Vì sao không nên dùng keep-warm timer ping làm cam kết SLA?
13. Những phần nào của JVM startup khiến Java Function có cold start dài hơn?
14. Tái sử dụng SDK client trong Java cần kiểm tra điều kiện gì?
15. Một static mutable field trong worker có những rủi ro concurrency nào?
16. Vì sao một semaphore trong process không giới hạn được toàn bộ distributed workers?
17. Nếu database có 20 concurrent connections nhưng Functions tạo 100 jobs, nên làm gì?
18. Queue worker vì sao phải idempotent và xử lý poison messages?
19. Khi một task mất 5 phút, vì sao HTTP trigger đồng bộ có thể là lựa chọn chưa tốt?
20. Local Core Tools có kiểm thử được đầy đủ cold start của Azure hosting plan không?
21. Những metrics nào giúp chứng minh một thay đổi tối ưu khởi động là hiệu quả?
22. Vì sao giữ instance luôn sẵn sàng có thể tăng chi phí dù không có request?

## 40. Tổng kết

**Concurrency, cold start và thời gian khởi động** là ba yếu tố quyết định hiệu năng và chi phí của Azure Functions. Concurrency cho biết một instance xử lý bao nhiêu công việc cùng lúc; scale-out tăng số instances; cold start xuất hiện khi platform và application cần khởi tạo môi trường chạy mới. Chúng tương tác với nhau nhưng không thể thay thế bằng một tham số duy nhất.

Đối với **HTTP APIs**, hãy tối ưu để đáp ứng p95/p99, hạn chế xử lý dài đồng bộ và cân nhắc always-ready/prewarmed capacity khi SLO cần. Đối với **Queue/Service Bus workloads**, hãy chọn concurrency theo khả năng CPU, memory, downstream services, retries và idempotency; sử dụng dynamic concurrency khi trigger/extension hỗ trợ và đo thấy hiệu quả. Với **Java Functions**, chú ý dependency size, JVM/class initialization, client reuse, thread-safety và connection pools.

Một quy trình đúng là **đo baseline → phân rã latency → xác định nút cổ chai → tối ưu một yếu tố → load test lại → kiểm tra SLO và chi phí**. Kết hợp Azure Monitor/Application Insights, managed identity, Storage/Service Bus, hosting plan và Azure Cost Management để xây dựng hệ thống serverless có thời gian phản hồi ổn định, xử lý tải an toàn và không đánh đổi bảo mật hoặc tính đúng của dữ liệu.
