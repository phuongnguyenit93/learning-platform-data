# Lựa chọn máy ảo, container, serverless và nền tảng ứng dụng

Khi triển khai ứng dụng trên cloud, lựa chọn compute quyết định **ai quản lý máy chủ, hệ điều hành và runtime; workload được đóng gói và mở rộng ra sao; ứng dụng phục hồi thế nào khi một instance hỏng; và đội ngũ phải vận hành bao nhiêu lớp hạ tầng**. Máy ảo (VM), container, serverless và nền tảng ứng dụng được quản lý đều có thể chạy một ứng dụng web, API hoặc tác vụ nền, nhưng cung cấp mức kiểm soát và trách nhiệm khác nhau.

Trong module **CLOUD_ARCHITECTURE**, quyết định compute phải xuất phát từ yêu cầu nghiệp vụ và ràng buộc hệ thống. Cần xét đồng thời độ tin cậy, bảo mật, khả năng mở rộng, hiệu năng, chi phí và khả năng vận hành theo tư duy Well-Architected. Không có công nghệ nào tự động tốt hơn trong mọi tình huống; mô hình phù hợp là mô hình đáp ứng workload và mục tiêu dịch vụ với mức phức tạp mà đội ngũ có thể duy trì.

## 1. Bốn mô hình compute và mức trách nhiệm

| Mô hình | Cách hoạt động | Người dùng thường quản lý | Nhà cung cấp thường quản lý |
| --- | --- | --- | --- |
| **Máy ảo (Virtual Machine)** | Một máy tính ảo có CPU, RAM, đĩa và hệ điều hành riêng | OS, bản vá, runtime, ứng dụng, agent, scaling và HA theo thiết kế | Host vật lý, hypervisor, hạ tầng datacenter |
| **Container** | Đóng gói ứng dụng và dependencies thành image, chạy bằng container runtime/orchestrator | Image, cấu hình, resource request/limit, orchestration policy, ứng dụng và bảo mật workload | Hạ tầng node/runtime hoặc control plane tùy mô hình managed/self-managed |
| **Serverless compute** | Chạy code hoặc container theo request/event/job với hạ tầng máy chủ được trừu tượng hóa | Handler/image, cấu hình, quyền, concurrency, timeout, dữ liệu và observability | Provisioning và phần lớn quản lý host; giới hạn tùy dịch vụ |
| **Nền tảng ứng dụng được quản lý** | Deploy ứng dụng lên môi trường đã cung cấp runtime, routing, scaling và health management | Code/artifact, cấu hình, version runtime được hỗ trợ và chính sách triển khai | Nhiều phần OS, runtime platform, ingress và lifecycle |

Ranh giới trách nhiệm thay đổi theo sản phẩm. **VM không có nghĩa tự quản lý phần cứng**, container không có nghĩa tự động có Kubernetes, serverless không có nghĩa không có máy chủ, và managed platform không đảm bảo mọi bản vá hay dependency ứng dụng được tự động xử lý.

### Một phổ kiểm soát và trách nhiệm

~~~mermaid
flowchart LR
    VM["VM"] --> CON["Container platform"]
    CON --> F["Serverless container / function"]
    F --> PAAS["Managed application platform"]
    subgraph CONTROL["Xu hướng trừu tượng hóa"]
      A["Nhiều quyền kiểm soát OS / network / runtime"]
      B["Ít việc quản lý host và patch hơn"]
      A --> B
    end
~~~

Sơ đồ chỉ mô tả xu hướng tổng quát, không phải thang đo tuyệt đối. Managed container có thể cho quyền kiểm soát networking rất sâu; một số serverless container vẫn cần lựa chọn CPU/RAM, VPC, image, concurrency và scaling policy. Hãy đọc mô hình trách nhiệm và giới hạn cụ thể của dịch vụ trước khi thiết kế.

## 2. Máy ảo: kiểm soát sâu và phù hợp workload cần môi trường riêng

VM cung cấp một hệ điều hành khách (guest OS) với CPU, RAM, volume, network interface và cơ chế quản trị riêng. Đội ứng dụng có thể cài runtime tùy ý, chạy tiến trình dài, agent hệ thống hoặc phần mềm legacy. Đây là lựa chọn hữu ích khi workload cần quyền truy cập OS, thư viện hệ thống đặc biệt hoặc cấu hình mạng/đĩa cụ thể.

~~~mermaid
flowchart TB
    subgraph PHYSICAL["Hạ tầng cloud"]
      H["Host vật lý / hypervisor"]
      subgraph VM1["Virtual machine"]
        OS["Guest OS"]
        RT["Runtime + libraries"]
        APP["Ứng dụng"]
        OS --> RT --> APP
      end
      subgraph VM2["Virtual machine khác"]
        OS2["Guest OS"]
        APP2["Ứng dụng khác"]
        OS2 --> APP2
      end
      H --> VM1
      H --> VM2
    end
~~~

### Ưu điểm

- **Tự do cấu hình môi trường:** chọn OS, version runtime, package và agent theo yêu cầu.
- **Tương thích phần mềm cũ:** phù hợp ứng dụng cần daemon, driver, thư viện native hoặc quy trình cài đặt truyền thống.
- **Tài nguyên có thể duy trì lâu dài:** thích hợp workload chạy liên tục hoặc cần hiệu năng ổn định khi được sizing và placement đúng.
- **Ranh giới vận hành quen thuộc:** đội ngũ có thể sử dụng kiến thức OS, monitoring, hardening và automation hiện có.

### Chi phí và trách nhiệm

- Đội vận hành thường chịu trách nhiệm **patch OS, cấu hình SSH/RDP, endpoint protection, secrets, firewall host, logging và backup**.
- Cần quy trình tạo image chuẩn (golden image), quét lỗ hổng, kiểm kê package, quản lý license và luân chuyển khóa.
- Cần tự thiết kế load balancing, auto scaling, health check, rolling replacement và recovery khi VM/zone hỏng.
- Một VM bị cấu hình lệch hoặc để lâu không vá có thể trở thành điểm rủi ro; tăng số VM cũng làm tăng khối lượng patch và theo dõi.

### Khi nào nên chọn VM?

VM phù hợp khi ứng dụng cần quyền OS sâu, workload legacy khó đóng gói, tiến trình dài cần môi trường đặc thù, license gắn với hệ điều hành hoặc phần mềm thương mại yêu cầu cấu hình xác định. Nó cũng là bước chuyển tiếp thực tế khi đưa ứng dụng cũ lên cloud trước khi tái cấu trúc.

Không nên chọn VM chỉ vì “dễ hiểu”. Nếu có hàng trăm dịch vụ nhỏ cần build/deploy độc lập, quản lý từng OS có thể làm tăng vận hành và kéo dài phát hành. Có thể dùng image tự động, configuration management và autoscaling để giảm gánh nặng, nhưng cần tính công sức duy trì OS.

## 3. Container: đóng gói ứng dụng và chuẩn hóa cách chạy

Container image đóng gói mã ứng dụng cùng runtime và libraries cần thiết. Container chạy như một tiến trình được cô lập ở mức OS kernel thông qua namespace, cgroup và các cơ chế khác; nhiều container thường dùng chung kernel của host. Khác biệt này quan trọng khi so sánh container với VM: container **không có guest OS kernel riêng** theo cách VM thông thường.

~~~mermaid
flowchart TB
    subgraph HOST["Một node / VM host"]
      K["Host OS + container runtime"]
      subgraph C1["Container A"]
        A1["App A + runtime/libs"]
      end
      subgraph C2["Container B"]
        B1["App B + runtime/libs"]
      end
      K --> C1
      K --> C2
    end
~~~

Container giúp artifact gần với môi trường thực thi giữa laptop, CI và production; version image có thể được kiểm soát và triển khai lặp lại. Tuy vậy, container không tự cung cấp orchestration, service discovery, routing, scaling hoặc HA. Những khả năng này đến từ nền tảng chạy container và cấu hình vận hành.

### Container orchestration

Khi có nhiều container và yêu cầu scheduling, self-healing, rollout, service discovery và autoscaling, tổ chức có thể dùng nền tảng điều phối như Kubernetes hoặc dịch vụ container được quản lý. Một cluster thường gồm control plane điều phối trạng thái mong muốn và node/worker chạy workload; với dịch vụ managed, trách nhiệm hai phía phụ thuộc dịch vụ cụ thể.

Các khái niệm cần nắm:

| Khái niệm | Vai trò |
| --- | --- |
| **Image** | Artifact bất biến theo tag/digest, chứa ứng dụng và thành phần chạy |
| **Registry** | Lưu trữ, phân quyền và phân phối image |
| **Container** | Instance đang chạy của image với cấu hình cụ thể |
| **Pod/task** | Đơn vị scheduling tùy orchestrator; có thể chứa một hoặc nhiều container liên quan |
| **Node/worker** | Máy tính cung cấp CPU, RAM, network và storage cho workload |
| **Deployment/service** | Định nghĩa số replica, update strategy và endpoint truy cập theo nền tảng |
| **Autoscaler** | Thay đổi số replica hoặc node theo metric và chính sách |
| **Resource request/limit** | Khai báo tài nguyên yêu cầu và giới hạn sử dụng cho workload |

### Ưu điểm

- **Đóng gói nhất quán:** giảm sai lệch môi trường build và runtime khi image được tạo và kiểm soát đúng.
- **Tăng mật độ sử dụng tài nguyên:** nhiều workload có thể cùng chạy trên node nếu được giới hạn và phân bổ hợp lý.
- **Triển khai và rollback theo version:** dùng immutable image, rollout theo replica và theo dõi sức khỏe.
- **Tính di động ở cấp artifact:** cùng image có thể chạy trên nhiều nền tảng tương thích, dù networking và storage vẫn khác.
- **Hỗ trợ modularity:** API, worker và job có thể đóng gói riêng, dùng chung codebase nhưng triển khai độc lập.

### Rủi ro vận hành

- Orchestrator, networking, ingress, service mesh, storage và observability tạo ra bề mặt vận hành đáng kể.
- Container có quyền quá rộng hoặc chạy privileged có thể làm suy giảm ranh giới bảo mật.
- Image cũ, base image dễ tổn thương, secret đóng trong image và registry quá mở là những rủi ro phổ biến.
- Cấu hình request/limit sai có thể làm workload bị throttling, OOMKilled hoặc tranh chấp tài nguyên.
- Persistent state trong container filesystem có thể biến mất khi container bị thay thế; dữ liệu cần ở volume/service lưu trữ phù hợp.

### Khi nào nên chọn container?

Container phù hợp khi cần đóng gói tiêu chuẩn, nhiều service/workload, triển khai thường xuyên, môi trường chạy có thể được quản lý như code và đội có năng lực nền tảng. Có thể bắt đầu với một dịch vụ container được quản lý để tránh tự vận hành toàn bộ orchestrator.

Không nhất thiết phải dùng Kubernetes cho một API nhỏ. Nền tảng container đơn giản hoặc managed app platform có thể giảm nhiều cấu hình và vận hành. Chọn orchestrator chỉ khi những khả năng scheduling, networking, policy, workload mix hoặc ecosystem thật sự cần đến nó.

## 4. Serverless: tập trung vào code, event và đơn vị xử lý

Serverless là mô hình cloud trong đó nhà cung cấp quản lý phần lớn provisioning và vận hành hạ tầng thực thi. Người phát triển triển khai function, container hoặc job; nền tảng cấp tài nguyên theo cấu hình và tải, có thể scale theo event/request rồi giảm về mức thấp khi không có việc. Một số dịch vụ tính phí theo request, thời gian thực thi hoặc tài nguyên được cấp; cách tính cụ thể khác nhau theo sản phẩm.

**Serverless không có nghĩa không có server.** Máy chủ vẫn tồn tại nhưng người dùng không phải trực tiếp quản lý host/OS. Người dùng vẫn chịu trách nhiệm code, dependency, IAM, dữ liệu, giới hạn concurrency, timeout, observability và thiết kế lỗi.

### Các dạng serverless thường gặp

| Dạng | Đơn vị triển khai/kích hoạt | Ví dụ workload |
| --- | --- | --- |
| **Function-as-a-Service (FaaS)** | Function chạy khi có request hoặc event | Webhook, xử lý file, event handler |
| **Serverless container** | Image container chạy theo request, job hoặc thời gian | API, worker, tác vụ batch |
| **Serverless job/batch** | Một lần chạy có thời điểm bắt đầu/kết thúc | Import dữ liệu, báo cáo, chuyển đổi file |
| **Managed event/workflow service** | Event hoặc bước workflow kích hoạt tác vụ | Điều phối quy trình bất đồng bộ, tích hợp hệ thống |

### Ưu điểm

- **Giảm công việc quản trị host:** không cần duy trì OS và node pool theo cách truyền thống (trong phạm vi dịch vụ quản lý).
- **Scale theo nhu cầu:** có thể tự tạo instance thực thi khi request/event tăng; một số dịch vụ scale về 0.
- **Chi phí theo mức sử dụng:** thuận lợi cho workload thưa, bursty hoặc job không chạy liên tục.
- **Tích hợp sự kiện:** phù hợp xử lý event từ object storage, queue, scheduler, webhook và nền tảng cloud.
- **Rút ngắn time-to-market:** nhóm nhỏ có thể triển khai chức năng mà không phải xây nền tảng compute riêng.

### Giới hạn phải tính trước

- **Cold start:** lần khởi tạo môi trường hoặc sau giai đoạn idle có thể thêm latency; mức độ phụ thuộc runtime, package, cấu hình và nền tảng.
- **Giới hạn thời gian:** một số function có timeout tối đa; job dài hoặc cần tiến trình liên tục có thể cần container/job/VM.
- **Concurrency và quota:** scale nhanh có thể tạo lượng kết nối lớn tới database hoặc vượt giới hạn của dịch vụ ngoài.
- **State và filesystem:** không nên dựa vào bộ nhớ hoặc filesystem tạm để giữ trạng thái lâu dài giữa các lần chạy.
- **Observability và debug:** execution phân tán theo request/event, cần correlation ID, tracing và log có cấu trúc.
- **Vendor coupling:** event schema, runtime, IAM, trigger và workflow có thể gắn với API riêng của nhà cung cấp; cần đánh giá khả năng chuyển đổi và chi phí thay đổi.
- **Chi phí khi chạy liên tục:** serverless không tự rẻ hơn container/VM nếu tải cao, ổn định và thực thi dài.

### Mẫu xử lý event

~~~mermaid
flowchart LR
    UPLOAD["Object upload"] --> EVENT["Storage event"]
    EVENT --> QUEUE["Queue"]
    QUEUE --> FN["Serverless handler"]
    FN --> OUT["Object kết quả"]
    FN --> DB["Metadata database"]
    QUEUE --> DLQ["Dead-letter queue"]
~~~

Trong ví dụ, file được tải lên tạo event, queue giúp hấp thụ burst, handler xử lý và ghi metadata. Thiết kế cần xác định hành vi **at-least-once**, duplicate event, retry, DLQ, giới hạn kích thước file, timeout, concurrency và cách phát lại job. Không được mặc định event chỉ tới đúng một lần hoặc handler chỉ chạy đúng một lần.

### Khi nào nên chọn serverless?

Serverless thường phù hợp với webhook, event handler, tác vụ ngắn, workload không đều, xử lý file, automation và các API có tính stateless, miễn là giới hạn timeout, latency, networking và concurrency phù hợp.

Không nên ép một workflow dài nhiều giờ vào function có giới hạn thời gian; có thể chia thành các bước idempotent được điều phối bằng workflow/job. Với API cần latency rất ổn định, workload luôn nóng, memory lớn hoặc xử lý lâu, container/VM có thể phù hợp hơn sau khi benchmark.

## 5. Nền tảng ứng dụng được quản lý: giảm việc vận hành hạ tầng

Managed application platform cung cấp con đường triển khai ứng dụng đã được chuẩn hóa. Đội phát triển thường đưa source/artifact hoặc container image lên nền tảng, cấu hình runtime, biến môi trường, domain, TLS, scaling và health check; nền tảng xử lý một phần lifecycle, routing và máy chủ bên dưới.

Các sản phẩm thường có thể được gọi là **Platform-as-a-Service (PaaS)** hoặc managed app service, nhưng phạm vi khác nhau. Một số hỗ trợ runtime ngôn ngữ cụ thể, một số nhận container; một số tự quản lý ingress và autoscaling, số khác yêu cầu cấu hình mạng, compute plan hoặc worker riêng.

~~~mermaid
flowchart TB
    DEV["Source / image / artifact"]
    PLATFORM["Managed application platform"]
    ROUTE["Ingress / TLS / routing"]
    APP["Application instances"]
    SCALE["Health / autoscaling / rollout"]
    OBS["Logs / metrics"]
    DATA["Managed data services"]
    DEV --> PLATFORM
    PLATFORM --> ROUTE
    PLATFORM --> APP
    PLATFORM --> SCALE
    PLATFORM --> OBS
    APP --> DATA
~~~

### Ưu điểm

- **Ít quản lý hạ tầng:** nhóm tập trung nhiều hơn vào ứng dụng, domain và release.
- **Đường triển khai đơn giản:** tích hợp source repository/build pipeline, cấu hình runtime và health check theo sản phẩm.
- **Khả năng tích hợp sẵn:** domain, TLS, logging, autoscale, slot/staging hoặc deployment mechanism tùy nền tảng.
- **Đội nhỏ vẫn có thể vận hành production:** không phải tự xây toàn bộ container orchestration hay OS automation.

### Đánh đổi

- **Ít quyền kiểm soát môi trường:** chỉ hỗ trợ runtime, phiên bản, hệ điều hành và mô hình networking nhất định.
- **Giới hạn workload:** job dài, daemon tùy chỉnh, kernel module, protocol đặc biệt hoặc yêu cầu OS có thể không phù hợp.
- **Hạn mức và mô hình giá:** compute plan, worker, instance, network integration và storage có thể được tính theo cách khác nhau.
- **Tính di động:** phụ thuộc vào cấu hình, API, deployment slot, runtime và dịch vụ tích hợp riêng.
- **Ranh giới trách nhiệm:** nhà cung cấp quản lý platform nhưng người dùng vẫn phải vá dependency ứng dụng, bảo vệ secret, IAM, dữ liệu, cấu hình ingress và kiểm soát quyền.

### Khi nào nên chọn managed app platform?

Phù hợp khi ứng dụng web/API theo runtime được hỗ trợ, đội ngũ muốn rút ngắn vận hành, môi trường production cần deploy/rollback có quy trình và workload không đòi quyền OS sâu. Đây thường là lựa chọn khởi đầu tốt cho ứng dụng nghiệp vụ thông thường, nhất là khi chưa có lý do để vận hành cluster.

Nếu cần cài agent hệ thống riêng, tùy chỉnh network sâu, scheduling workload đa dạng hoặc triển khai hàng chục loại service với policy thống nhất, nền tảng container có thể đem lại quyền kiểm soát phù hợp hơn. Quyết định phải dựa trên yêu cầu thực, không theo định kiến rằng PaaS “quá đơn giản” hay Kubernetes “chuyên nghiệp hơn”.

## 6. So sánh theo các tiêu chí kiến trúc

| Tiêu chí | VM | Container / orchestrator | Serverless | Managed application platform |
| --- | --- | --- | --- | --- |
| **Quản lý OS** | Thường do khách hàng quản lý guest OS | Phụ thuộc node model; managed service giảm quản lý node | Nhà cung cấp quản lý phần lớn host/OS | Nhà cung cấp quản lý phần lớn platform/OS |
| **Quyền kiểm soát runtime** | Rất cao | Cao trong image, bị giới hạn bởi runtime host/orchestrator | Theo runtime hoặc image được dịch vụ hỗ trợ | Theo runtime/version mà platform cung cấp |
| **Scale** | VM/instance group, có thể cần thời gian khởi động | Replica/pod và node autoscaling | Theo request/event/concurrency trong quota | Theo instance/plan/autoscale features |
| **Workload dài hạn** | Rất phù hợp | Phù hợp | Tùy giới hạn dịch vụ; serverless job/container có thể hỗ trợ | Tùy thời gian và loại process được phép |
| **Workload bursty** | Có thể scale nhưng cần dự báo và warm capacity | Autoscaling nhưng cần node capacity | Thường phù hợp nếu quota/cold start chấp nhận được | Tùy khả năng autoscale và mức tối thiểu |
| **Độ phức tạp vận hành** | OS và fleet management đáng kể | Có thể cao nếu tự quản lý cluster | Ít host management, nhưng cần kiểm soát event/limit | Thường thấp hơn cho ứng dụng chuẩn |
| **Tính di động** | OS/image phụ thuộc cấu hình nhưng khá linh hoạt | Container image tương đối di động | Có thể phụ thuộc trigger, IAM, workflow và runtime riêng | Phụ thuộc runtime và API của platform |
| **Cách tính chi phí** | Theo instance, storage, network và license | Node/cluster, workload, storage, network | Request, duration, provisioned capacity, network và dịch vụ phụ | Plan/instance, worker, storage, network và tích hợp |
| **Use case điển hình** | Legacy, OS-specific, process đặc thù | Microservices, API và worker đa dạng | Event handler, job ngắn, bursty | Web/API chuẩn muốn giảm vận hành |

Không có điểm số tuyệt đối cho từng ô. Cần khảo sát tính năng thực tế của nhà cung cấp: ví dụ container service được quản lý có thể loại bỏ phần lớn vận hành cluster, còn serverless container có thể chạy job dài hơn một function truyền thống. Tên marketing không đủ để kết luận giới hạn kỹ thuật.

## 7. Chọn compute từ đặc tính workload

Một quyết định có cơ sở nên phân loại workload trước:

| Đặc tính | Câu hỏi cần trả lời | Hướng cân nhắc |
| --- | --- | --- |
| Thời gian chạy | Request vài trăm ms, job vài phút hay process liên tục? | Function cho tác vụ ngắn; container/job hoặc VM cho process dài |
| Mức tải | Đều, theo giờ, theo mùa vụ, hay spike trong vài giây? | Managed scaling, queue, scheduled capacity hoặc serverless |
| Tài nguyên | CPU, RAM, GPU, I/O, network cần bao nhiêu? | VM instance family hoặc container resource profile phù hợp |
| Môi trường | Cần OS/runtime/version/native library nào? | VM khi cần OS sâu; container khi có thể chuẩn hóa image |
| Trạng thái | Có session local, file bền vững, giao dịch hay khóa? | Tách state sang database/cache/object storage/queue |
| Latency | P95/P99 có chặt? Cold start có ảnh hưởng không? | Benchmark warm/cold, giữ minimum capacity hoặc chọn mô hình process thường trực |
| Kết nối | Cần VPC/private endpoint, inbound/outbound protocol nào? | Kiểm tra network integration và quota của platform |
| Vận hành | Đội có thể quản lý OS/cluster/on-call không? | Managed platform nếu phù hợp giúp giảm gánh nặng |
| Bảo mật | Quyền host, workload identity, secret, image và patch ra sao? | Chọn mức kiểm soát đáp ứng threat model và compliance |
| Chi phí | Tải có đều, có thời gian idle, license và egress nào? | Tính TCO theo profile tải, không so một con số giờ chạy |

### Ví dụ ma trận ứng viên

| Workload | Đặc tính | Lựa chọn có thể bắt đầu |
| --- | --- | --- |
| API đặt lịch stateless | Tải đều, cần latency thấp, rollout thường xuyên | Managed app platform hoặc managed container |
| Hệ thống legacy có agent OS đặc biệt | Runtime/OS tùy chỉnh và process dài | VM trước, rồi đánh giá container hóa |
| Resize ảnh theo event | Tải bursty, job độc lập, có thể retry | Queue + serverless handler hoặc container worker |
| Batch báo cáo mỗi đêm | Job dài, lịch chạy rõ, cần checkpoint | Managed job/batch hoặc container/VM theo thời lượng |
| Service tìm kiếm cần memory lớn | Workload liên tục, index lớn | Container/VM hoặc managed search platform |
| Webhook ít lưu lượng | Request ngắn, thỉnh thoảng có spike | Serverless function/container nếu latency phù hợp |
| Kubernetes platform cho nhiều đội | Nhiều workload, yêu cầu policy và scheduling chung | Managed Kubernetes khi lợi ích vượt chi phí vận hành |

Đây là **ứng viên**, không phải kết luận; benchmark, quota, dữ liệu, tính năng sản phẩm và kỹ năng của đội sẽ quyết định cuối cùng.

## 8. Sizing compute: từ số đo tới năng lực dự phòng

Chọn loại compute trước khi biết workload dễ dẫn đến thừa hoặc thiếu tài nguyên. Hãy đo hoặc ước lượng:

- **Throughput:** request/giây, job/phút, message/giây, concurrent session.
- **CPU:** CPU giây/request hoặc job; mức sử dụng ở tải ổn định và đỉnh.
- **Memory:** working set, heap, native memory, cache và peak allocation.
- **I/O:** IOPS, throughput, latency của block/object storage và database.
- **Network:** số kết nối, bandwidth, packet rate, egress và giới hạn NAT.
- **Tail latency:** p95/p99, thời gian queue wait, cold start và thời gian hoàn tất job.
- **Availability headroom:** năng lực còn lại khi mất instance, node hoặc AZ.

### Tính CPU sơ bộ

Với workload có chi phí CPU tương đối ổn định:

\[
\text{CPU cores cần}
\approx\frac{\lambda\times c}{u}
\]

Trong đó \(\lambda\) là request/giây, \(c\) là CPU giây/request và \(u\) là mức sử dụng CPU mục tiêu (ví dụ 0,60). Đây là phép tính định hướng cho năng lực CPU, chưa gồm overhead, burst, phân bố request nặng nhẹ, memory pressure và các giới hạn khác.

**Ví dụ:** một API nhận 240 RPS, mỗi request dùng trung bình 0,02 CPU giây. Mục tiêu CPU trung bình dưới 60%:

\[
\frac{240\times0{,}02}{0{,}60}=8\text{ cores}.
\]

Nếu yêu cầu chịu mất một trong hai AZ mà vẫn giữ tải đỉnh, mỗi AZ phải có đủ năng lực tương ứng với tải mục tiêu hoặc có phương án giảm cấp được chấp nhận. Cấu hình 4 core ở mỗi AZ chỉ cung cấp 4 core còn lại khi mất một AZ, nên không đáp ứng yêu cầu 8 core nếu chưa có capacity khác sẵn sàng. Phép tính còn phải được xác minh qua load test tại SLO.

### Capacity planning cho worker

Với queue:

\[
\text{Backlog tăng/giây}\approx
\max(0,\lambda_{\text{đến}}-\mu_{\text{xử lý}})
\]

Nếu producer tạo 80 job/s nhưng worker hoàn thành 65 job/s, backlog tăng 15 job/s, tức 900 job/phút. Cần tính thời gian drain sau burst, job age tối đa chấp nhận, thời gian scale-out và quota downstream. Autoscaling chỉ theo CPU có thể bỏ qua độ trễ queue; autoscaling chỉ theo queue depth cũng có thể làm worker tăng vượt mức database hoặc provider có thể chịu.

### Đừng sizing theo con số trung bình duy nhất

Một hệ thống đạt 100 RPS trung bình nhưng có spike 1.000 RPS trong 10 giây có thể cần warm capacity, admission control hoặc queue. P99 của request nặng có thể khác xa CPU trung bình. Cần load test với dữ liệu/payload đại diện, cache warm/cold, tỉ lệ read/write, retry, lỗi dependency và các tình huống mất replica/AZ. Đo ở ngưỡng SLO; throughput cao nhưng latency vượt cam kết không phải capacity sử dụng được.

## 9. Khả năng mở rộng và tính sẵn sàng trong từng mô hình

### VM

VM thường scale bằng cách thay đổi size hoặc thêm instance trong group sau load balancer. Scale-out phụ thuộc thời gian boot, cài cấu hình, tải image và warm-up. Dùng immutable image, health check, placement qua nhiều AZ và graceful drain để instance thay thế được. Một VM lớn đơn lẻ có thể đơn giản nhưng là failure domain lớn; cần đánh giá RTO nếu host lỗi.

### Container

Orchestrator có thể tăng replica/pod theo CPU, memory, request metric hoặc queue. Nhưng cần phân biệt:

- **Horizontal scaling:** thêm replica.
- **Vertical scaling:** tăng CPU/RAM từng replica hoặc node.
- **Node scaling:** thêm worker node khi cluster thiếu capacity.
- **Pod/task placement:** phân tán workload qua node/AZ bằng topology constraints/anti-affinity theo tính năng nền tảng.

Liveness/readiness/startup probe phải có ngữ nghĩa khác nhau; cấu hình probe quá nhạy có thể tạo restart storm khi dependency chậm. Resource request/limit, disruption budget, rollout strategy và quota node cũng ảnh hưởng availability. Nếu cluster control plane được quản lý, vẫn phải đảm bảo node, network, storage và ứng dụng có khả năng chịu lỗi.

### Serverless

Serverless có thể tự tạo concurrency theo tải, nhưng cần đặt giới hạn để bảo vệ downstream. Nếu một function tăng lên 1.000 invocation cùng lúc và mỗi invocation mở một DB connection, database có thể cạn pool. Phải cấu hình reserved/max concurrency, batching, queue, connection reuse hoặc data access pattern phù hợp. Kiểm tra cold start, throttling, retry và DLQ khi nền tảng không thể nhận hết burst.

### Managed application platform

Platform có thể quản lý health check, instance replacement, routing và autoscale; cần hiểu chính xác semantics: autoscale dựa CPU, request, queue hay schedule; thay đổi capacity mất bao lâu; app có bị restart khi scale/maintenance không; deployment slot hoặc rolling release có giữ kết nối hay không. Không mặc định platform đảm bảo HA đa AZ nếu cấu hình/plan chưa bật hoặc sản phẩm không hỗ trợ.

### Mục tiêu phục hồi theo hành trình

Availability không chỉ là số instance healthy. Khi một instance bị mất, kết nối đang mở có thể reset; người dùng có thể thấy lỗi dù load balancer đã chuyển traffic. Cần xác định **SLI/SLO**, error budget, RTO/RPO cho từng hành trình, và thử failover end-to-end. Giao dịch không được mất/nhân đôi khi client retry; dữ liệu và session phải được lưu ngoài ephemeral local filesystem.

## 10. Bảo mật và mô hình trách nhiệm của compute

Chọn compute thay đổi bề mặt tấn công và phần việc đội ngũ phải bảo vệ.

| Lớp | VM | Container | Serverless / managed platform |
| --- | --- | --- | --- |
| OS/host patch | Khách hàng thường vá guest OS; cloud quản lý host/hypervisor | Managed node có thể do provider vá; self-managed phải quản lý node; image base do khách hàng cập nhật | Provider quản lý phần lớn host/OS trong phạm vi dịch vụ; khách hàng vẫn vá dependency/runtime package trong artifact |
| Artifact | VM image, package và script | Container image, base image, registry | Function package hoặc container image |
| Identity | VM role/managed identity và quyền OS | Workload identity/service account và quyền container | Execution role/function identity/platform identity |
| Secret | Secret manager, file/memory injection, rotation | Secret manager hoặc orchestrator secret; không bake vào image | Secret/config store và cơ chế cấp quyền của platform |
| Network | Security group/firewall, subnet, host firewall | Network policy, service ingress/egress, node boundary | VPC integration, endpoint, ingress/egress theo giới hạn dịch vụ |
| Runtime protection | EDR/agent, hardening, audit OS | Image scanning, admission policy, runtime security | Dependency scanning, identity policy, platform controls |
| Logging | OS + application logs | Container stdout/stderr, node và orchestration events | Application logs, invocation/request metrics và platform logs |

Các nguyên tắc quan trọng:

1. **Least privilege:** VM role, workload identity hoặc function role chỉ được phép truy cập tài nguyên cần thiết; không dùng quyền quản trị mặc định.
2. **Artifact tin cậy:** build từ source được kiểm soát, scan dependency/image, ký artifact khi quy trình yêu cầu và deploy theo digest/version có thể truy vết.
3. **Secret không nằm trong image hoặc source:** dùng secret manager, identity ngắn hạn và rotation; tránh ghi secret vào log.
4. **Patch và lifecycle rõ:** xác định ai vá OS, runtime, base image, dependency và thời hạn xử lý lỗ hổng.
5. **Network tối thiểu:** chỉ mở ingress cần thiết; egress có kiểm soát; mã hóa kết nối tới database, queue và service ngoài.
6. **Cách ly workload:** không chạy container privileged hoặc mount host path không cần thiết; tách workload nhạy cảm bằng node/plan/account khi threat model yêu cầu.
7. **Dữ liệu bền vững và backup:** không coi local ephemeral disk là nơi lưu dữ liệu nghiệp vụ duy nhất; phân quyền backup/restore và kiểm thử phục hồi.

Shared responsibility thay đổi theo dịch vụ và mức managed. Provider có thể vá host nhưng không tự chịu trách nhiệm về thư viện dễ tổn thương trong image của ứng dụng. Đọc rõ phạm vi chứng nhận/compliance và trách nhiệm vận hành của dịch vụ trước khi đưa vào hệ thống dữ liệu nhạy cảm.

## 11. Chi phí compute và total cost of ownership (TCO)

So sánh giá mỗi giờ của VM với giá mỗi request serverless không đủ. TCO cần gồm:

- **Compute trực tiếp:** vCPU, RAM, instance time, function invocations, duration, provisioned concurrency hoặc plan.
- **Storage và artifact:** disk, image registry, object storage, snapshot và backup.
- **Network:** load balancer, NAT, egress Internet, truyền giữa AZ/region, private endpoint.
- **Nền tảng phụ:** cluster control plane, message broker, monitoring/logging, secrets, registry, orchestration.
- **Dư phòng:** minimum instances, standby, headroom để chịu lỗi và capacity warm-up.
- **Vận hành nhân sự:** patch OS, upgrade cluster, trực sự cố, quản lý quota, xử lý bảo mật và pipeline.
- **License và support:** phần mềm thương mại, runtime, hệ điều hành và support plan.

### Ví dụ so sánh theo profile tải

Giả sử cùng một API có hai profile:

| Profile | Hành vi | Mô hình cần xem xét |
| --- | --- | --- |
| A — bursty | 2.000 request/ngày, phần lớn tập trung 20 phút, tác vụ ngắn | Serverless hoặc managed app có autoscale thấp |
| B — liên tục | 500 RPS gần như cả ngày, latency thấp và ổn định | Container/VM hoặc compute có capacity luôn sẵn sàng |

Profile A có thời gian idle dài nên pay-per-use có thể có lợi, nhưng phải cộng API gateway, logging, queue, cold start và egress. Profile B có utilization cao và cần capacity luôn nóng; chạy container/VM được tối ưu hoặc serverless với provisioned capacity có thể kinh tế hơn tùy giá. **Không thể kết luận bằng profile mà không có đơn giá, region, cấu hình CPU/RAM, request duration và mô hình sử dụng thực.**

### Phép tính TCO theo kịch bản

Có thể lập bảng:

| Hạng mục | Cơ sở tính | Thấp | Cơ sở | Cao |
| --- | --- | ---: | ---: | ---: |
| Compute | vCPU/RAM × thời gian hoặc invocation × duration | … | … | … |
| Storage/image | GB-tháng, image pull/cache | … | … | … |
| Network | GB egress, inter-AZ/region, NAT | … | … | … |
| HA/DR | Số replica/standby và backup | … | … | … |
| Observability | Metric, log, trace, retention | … | … | … |
| License/support | Theo instance/user/plan | … | … | … |
| Vận hành | Giờ công patch, upgrade, on-call | … | … | … |
| **Tổng** |  | … | … | … |

Đánh giá theo **cost per transaction/job**, không chỉ tổng hóa đơn. Nếu container giảm chi phí compute 15% nhưng cần đội platform trực 24/7 bổ sung, tổng chi phí có thể tăng. Ngược lại, một managed platform có đơn giá cao hơn nhưng giảm đáng kể sự cố patch và thời gian triển khai có thể có TCO tốt hơn.

## 12. Ví dụ thiết kế: ứng dụng đặt lịch trên cloud

Giả sử một nền tảng đặt lịch có các workload sau:

| Năng lực | Hồ sơ tải và yêu cầu |
| --- | --- |
| Booking API | Tải tương đối ổn định, cần latency thấp, không được tạo đặt lịch trùng |
| Catalog API | Đọc nhiều, stateless, có thể cache nội dung |
| Search | CPU/RAM biến động, index lớn, thuật toán thay đổi thường xuyên |
| Image processing | Burst theo đợt upload, mỗi job có thể chạy vài chục giây |
| Notification | Có thể xử lý bất đồng bộ, cần retry và tránh gửi trùng |
| Report batch | Job dài theo lịch, cần checkpoint và lưu kết quả bền vững |

### Phương án lựa chọn có cơ sở

- **Booking và Catalog API:** bắt đầu trên managed container hoặc managed application platform nếu runtime, networking và autoscaling đáp ứng SLO. Tổ chức module riêng; state đặt trong database/cache được quản lý.
- **Search:** service hoặc nền tảng search có tài nguyên riêng. Benchmark memory/index/query và p99; không mặc định để API booking tranh RAM với search.
- **Image processing:** queue + container worker autoscale hoặc serverless handler. Giới hạn concurrency, xử lý duplicate và ghi object theo key ổn định.
- **Notification:** queue/worker riêng, idempotency/dedupe, backoff và DLQ; không giữ request booking chờ email.
- **Report batch:** managed batch/job hoặc container job tùy thời gian chạy, checkpoint, quota và deadline.

Sơ đồ logic:

~~~mermaid
flowchart TB
    USER["Client"] --> EDGE["WAF / API ingress"]
    EDGE --> API["Booking + Catalog API"]
    EDGE --> SEARCH["Search service"]
    API --> DB["Managed database"]
    API --> Q["Message queue / outbox"]
    Q --> IMG["Image workers"]
    Q --> NOTI["Notification workers"]
    Q --> REPORT["Batch/report jobs"]
    IMG --> OBJ["Object storage"]
    SEARCH --> INDEX["Search index"]
    REPORT --> OBJ
~~~

Đây là phương án minh họa; các workload có thể cùng chạy trên một nền tảng container hoặc managed app platform nếu yêu cầu resource isolation, lifecycle và scaling tách được. Không nhất thiết mỗi hộp là một sản phẩm compute độc lập.

### Các quyết định cần thử nghiệm

1. Booking API đạt p95/p99 và error rate mục tiêu tại tải đỉnh, cả khi mất một replica/AZ chưa?
2. Search có còn tiêu thụ tài nguyên dùng chung gây ảnh hưởng booking không?
3. Worker scale-up có gây cạn connection DB, quota object storage hoặc rate limit email không?
4. Cold start của handler ảnh hưởng thời hạn xử lý ảnh hoặc trải nghiệm client không?
5. Batch job có thể checkpoint và resume sau khi container bị thay thế không?
6. Việc rollout image mới có health check, canary và rollback an toàn không?
7. Backup/restore và quyền truy cập dữ liệu có giữ được khi compute node/region gặp lỗi không?

## 13. Quy trình chọn compute trong buổi review kiến trúc

**Bước 1 — Xác định workload:** API, worker, batch, stream, stateful service hay legacy process; thời gian chạy, trigger và profile tải.

**Bước 2 — Ghi SLO và ràng buộc:** latency p95/p99, throughput, availability, RTO/RPO, dữ liệu, compliance, residency và network.

**Bước 3 — Xác định quyền kiểm soát cần thiết:** OS, kernel, runtime, library, GPU, filesystem, protocol và quyền quản trị.

**Bước 4 — Chọn hai hoặc ba ứng viên:** VM, managed container, serverless hoặc managed app platform; tránh mặc định chỉ có một lựa chọn.

**Bước 5 — Benchmark và thử lỗi:** dùng payload/dữ liệu thực, test cold/warm, burst/steady, scale-out, dependency failure, zone failure và deploy rollback.

**Bước 6 — Tính TCO:** compute, network, storage, HA/DR, observability, support và công sức vận hành trong các kịch bản tăng trưởng.

**Bước 7 — Xem lại responsibility và capability của đội:** ai vá, ai trực, ai quản lý pipeline, quota, identity, secrets, backup và platform upgrade?

**Bước 8 — Ghi quyết định và điều kiện xem lại:** nêu lý do, lựa chọn thay thế, rủi ro, metric, owner và trigger cần đánh giá lại.

~~~mermaid
flowchart TD
    W["Mô tả workload + hành trình"] --> N["SLO, dữ liệu, network, compliance"]
    N --> C["Yêu cầu kiểm soát OS/runtime"]
    C --> O["Chọn VM / container / serverless / managed platform"]
    O --> B["Benchmark + thử lỗi + sizing"]
    B --> T["TCO + năng lực vận hành"]
    T --> D{"Đạt mục tiêu?"}
    D -->|Không| O
    D -->|Có| ADR["Ghi quyết định kiến trúc và trigger review"]
~~~

## 14. Những lỗi thường gặp khi lựa chọn compute

1. **Chọn theo xu hướng:** dùng Kubernetes/serverless dù workload đơn giản, làm tăng bề mặt vận hành.
2. **Coi container là bảo đảm di động tuyệt đối:** image chạy được chưa chắc network, storage, IAM và secret giống nhau ở mọi nền tảng.
3. **Bỏ qua OS và runtime patch:** provider quản lý host nhưng dependency và image của ứng dụng vẫn có thể lỗi thời.
4. **Không đặt request/limit/concurrency:** một workload tăng vô hạn làm cạn node, database hoặc dịch vụ ngoài.
5. **Scale chỉ theo CPU:** bỏ qua queue lag, memory, connection pool, latency và quota.
6. **Dùng local filesystem cho state bền vững:** dữ liệu biến mất khi instance/function/container bị thay thế.
7. **Không tính cold start và timeout:** job hoặc API vượt ngưỡng latency khi workload scale từ 0.
8. **Cho rằng autoscaling thay thế HA:** autoscaler cần thời gian, quota và node capacity; không đảm bảo còn đủ tải khi AZ mất tức thời.
9. **Không có health check và graceful shutdown:** rollout/scale-in làm gián đoạn request đang xử lý.
10. **Dự toán chỉ bằng giá compute:** bỏ qua network, logging, storage, backup, replica, license và vận hành.
11. **Không xét đội ngũ:** chọn nền tảng đòi hỏi trực cluster 24/7 trong khi không có người sở hữu.
12. **Không kiểm thử dependency:** compute instance khỏe nhưng database, NAT hoặc API bên ngoài đã quá tải.

## 15. Bài tập thực hành và đáp án định hướng

Một công ty chuẩn bị triển khai bốn workload:

| Workload | Đặc điểm |
| --- | --- |
| A — API giao dịch | 300 RPS giờ cao điểm, request ngắn, latency p99 dưới 250 ms |
| B — Convert video | Job 8–15 phút, dùng nhiều CPU/GPU, tải theo đợt |
| C — Webhook nhận sự kiện | 1.000 request/ngày, có lúc burst gấp 20 lần, mỗi lần xử lý dưới 2 giây |
| D — Ứng dụng legacy | Cần một agent OS đã cấp phép và chỉnh cấu hình hệ thống đặc biệt |

**Câu 1: Hãy đề xuất mô hình compute cho từng workload.**

**Đáp án định hướng:** A cân nhắc managed container hoặc managed app platform luôn có capacity đủ và scale theo tải; p99 phải benchmark ở tải đỉnh. B cân nhắc container job/batch trên node CPU/GPU phù hợp hoặc nền tảng batch managed; kiểm tra timeout, checkpoint, GPU quota và thời gian chờ node. C cân nhắc serverless function/container nếu cold start, concurrency và retry phù hợp. D có thể cần VM do yêu cầu OS/agent/license; nên tự động hóa image và patch.

**Câu 2: Vì sao không nên chuyển cả bốn workload sang một VM lớn?**

**Đáp án định hướng:** Mức tài nguyên, thời gian chạy, burst, bảo mật và lifecycle khác nhau. Convert video có thể chiếm CPU/GPU ảnh hưởng API; webhook thưa tải có thể trả tiền cho tài nguyên idle; legacy cần OS riêng. Tách scaling unit giúp cô lập nhưng vẫn phải quản lý giao tiếp, network và chi phí tổng.

**Câu 3: API A có 300 RPS, CPU trung bình 0,01 giây/request và mục tiêu CPU 50%. Tính nhu cầu CPU sơ bộ.**

**Lời giải:** \(300\times0,01/0,5=6\) core hiệu dụng. Đây chưa gồm headroom, tải burst, memory/IO bottleneck, HA khi mất AZ; phải kiểm chứng bằng benchmark.

**Câu 4: Webhook C scale lên concurrency 500, mỗi invocation mở một kết nối database. Rủi ro là gì?**

**Đáp án định hướng:** Có thể tạo 500 kết nối cùng lúc vượt khả năng DB, gây connection exhaustion và làm lỗi lan rộng. Cần giới hạn concurrency, dùng connection pooling/proxy phù hợp, batch/queue nếu có thể, kiểm soát retry và đo DB connection/latency.

**Câu 5: Vì sao workload B có thể không phù hợp với function timeout ngắn?**

**Đáp án định hướng:** Job 8–15 phút có thể vượt giới hạn thời gian, cần GPU hoặc checkpoint/resume. Container job/batch hoặc VM/worker dài hạn có thể phù hợp hơn. Cần xác minh giới hạn thực tế của dịch vụ serverless được chọn, vì một số serverless container/job hỗ trợ thời gian dài hơn function thông thường.

**Câu 6: Khi chọn managed app platform, trách nhiệm bảo mật nào vẫn thuộc đội ứng dụng?**

**Đáp án định hướng:** Code và dependency, secret, IAM/identity, quyền dữ liệu, cấu hình ingress/egress, log, backup/restore theo trách nhiệm, xử lý lỗ hổng và quy trình ứng phó sự cố. Provider quản lý hạ tầng platform không đồng nghĩa bảo vệ logic hoặc dữ liệu của ứng dụng.

## 16. Checklist quyết định

- Workload, tải trung bình/đỉnh, thời gian chạy và đặc tính CPU/RAM/I/O đã rõ chưa?
- SLO, p95/p99, availability, RTO/RPO và failure domain đã được định nghĩa chưa?
- Có thật sự cần quyền OS/runtime sâu hay managed platform đã đủ?
- Image, dependency, patch, secret, IAM và network được quản lý bởi ai?
- Scale-out có chịu được quota và bảo vệ downstream không?
- Dữ liệu bền vững có tách khỏi compute ephemeral không?
- Rolling deployment, health check, graceful shutdown, canary và rollback đã thử chưa?
- Chi phí đã tính HA/DR, network, logging, storage, license và vận hành chưa?
- Có load test và failover test ở mức workload thực không?
- Có owner, dashboard, runbook và trigger xem xét lại quyết định không?

Khi kết thúc review, hãy trình bày **đặc tính workload, các ứng viên compute, bằng chứng benchmark, mô hình trách nhiệm, rủi ro và TCO**. Một quyết định tốt giải thích được vì sao VM, container, serverless hoặc managed app platform phù hợp với yêu cầu hiện tại, đồng thời xác định dấu hiệu nào sẽ khiến kiến trúc cần được đánh giá lại.
