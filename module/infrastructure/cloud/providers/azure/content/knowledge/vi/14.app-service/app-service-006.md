# Scale up, scale out và autoscale ứng dụng web

> **Chương:** Ứng dụng web với App Service  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **scale up**, **scale down**, **scale out** và **scale in** trong Azure App Service.
2. Giải thích quan hệ giữa **Web App**, **App Service Plan**, các **worker instances**, deployment slots và chi phí.
3. Chọn scale up hay scale out theo CPU, bộ nhớ, throughput, độ trễ, tính chất workload và giới hạn tài nguyên.
4. Hiểu hai cách tự điều chỉnh số instance: **Azure Monitor autoscale theo quy tắc/metric** và **automatic scaling của App Service** khi được hỗ trợ.
5. Thiết kế ngưỡng scale out/scale in, minimum/maximum instance, cooldown, lịch hoạt động và cảnh báo.
6. Dùng Azure portal, Azure CLI và Azure Monitor để xem cấu hình, quan sát hiệu năng và kiểm tra thay đổi.
7. Áp dụng nguyên tắc **stateless**, health checks, lưu session dùng chung và kiểm soát chi phí khi tăng số instance.

## 1. Bối cảnh: một ứng dụng web tăng trưởng tải

Một hệ thống bán vé triển khai trên Azure App Service phục vụ khoảng 300 yêu cầu/giây ở ngày thường. Đến giờ mở bán, số yêu cầu tăng đột ngột lên 1.200 yêu cầu/giây. Biểu đồ cho thấy CPU ứng dụng gần 95%, HTTP p95 latency tăng và lỗi 5xx bắt đầu xuất hiện.

Có ít nhất ba phương án:

- **Scale up:** đổi App Service Plan sang mức tài nguyên cao hơn, chẳng hạn worker có nhiều CPU/bộ nhớ hơn.
- **Scale out:** tăng số lượng worker instances để nhiều bản chạy ứng dụng phục vụ request song song.
- **Autoscale:** để hệ thống tự thay đổi số instance theo quy tắc metric, lịch hoặc cơ chế tự động được hỗ trợ.

Không nên chọn ngay phương án “thêm thật nhiều instance” khi chưa biết nguyên nhân. Nếu ứng dụng đang chậm do **SQL Database**, một API bên thứ ba hoặc lock trong mã nguồn, bổ sung App Service instances có thể chỉ làm tăng số request cùng lúc đổ vào điểm nghẽn đó.

### Mô hình tổng quan

~~~mermaid
flowchart TD
    U["Người dùng / client"]
    IN["Điểm vào App Service / routing"]
    PLAN["App Service Plan\nSKU, region, số worker instances"]
    W1["Worker 1\nWeb App"]
    W2["Worker 2\nWeb App"]
    W3["Worker 3\nWeb App"]
    DB["Database / Cache / Storage"]
    MON["Azure Monitor\nCPU, memory, HTTP, latency"]
    CTRL["Scaling configuration\nmanual / rule-based / automatic"]
    U --> IN
    IN --> W1
    IN --> W2
    IN --> W3
    PLAN -.-> W1
    PLAN -.-> W2
    PLAN -.-> W3
    W1 --> DB
    W2 --> DB
    W3 --> DB
    PLAN -.-> MON --> CTRL
    CTRL -.-> PLAN
~~~

Sơ đồ khái quát các lớp để học; kiến trúc định tuyến và chi tiết worker do nền tảng Azure quản lý. Một Web App có thể chạy trên một hoặc nhiều instances của App Service Plan tùy chế độ scale và cấu hình.

## 2. Web App, App Service Plan và instance

**Azure App Service** là dịch vụ PaaS dùng để chạy web applications, API và các workload web được hỗ trợ. Bạn quản lý mã ứng dụng, cấu hình, kết nối và triển khai; Azure quản lý nhiều công việc hạ tầng.

Các đối tượng cần phân biệt:

| Đối tượng | Chức năng | Ví dụ |
| --- | --- | --- |
| **Web App** | Tài nguyên chứa cấu hình và bản triển khai của ứng dụng | `shop-api-prod` |
| **App Service Plan (ASP)** | Xác định region, hệ điều hành, tier, khả năng và công suất tính toán được phân bổ | `asp-shop-prod` |
| **Worker instance** | Một đơn vị compute đang chạy ứng dụng trong plan | Worker 1, Worker 2 |
| **Deployment slot** | Môi trường triển khai/phát hành riêng trong một Web App trên tier hỗ trợ | `staging`, `production` |
| **Azure Monitor** | Thu thập và xem metric/log, tạo alert và autoscale theo quy tắc khi được hỗ trợ | CPU percentage, memory, HTTP responses |
| **Backend dependencies** | Dịch vụ ứng dụng gọi tới; có thể là điểm nghẽn riêng | Azure SQL, Redis, Blob Storage |

### Một plan có thể chạy nhiều Web App

Ví dụ:

~~~text
App Service Plan: asp-team-prod
  SKU: Standard S1
  Instances: 2

  Web App: shop-api
  Web App: admin-portal
  Web App: reporting
~~~

Trong cấu hình plan chia sẻ này, **ba ứng dụng cạnh tranh cùng năng lực compute của plan**. Khi bạn scale out plan từ 2 lên 4 instances theo mô hình plan-level thông thường, mức tài nguyên và chi phí của **plan** thay đổi; các ứng dụng trong plan có thể cùng chịu tác động.

Vì vậy:

- CPU cao trong `reporting` có thể ảnh hưởng `shop-api`.
- Scale up/scale out plan có thể làm tăng chi phí cho toàn bộ plan dù chỉ một ứng dụng cần thêm tài nguyên.
- Muốn cách ly năng lực hoặc chi phí của ứng dụng quan trọng, cân nhắc **App Service Plan riêng**.
- Một số tính năng scaling theo web app/per-site hoặc automatic scaling có phạm vi riêng tùy tier và cấu hình; không được mặc định mọi ứng dụng đều có thể đặt số worker độc lập trong cùng plan.

### Không nhầm instance với số App Service Plans

Một plan có 4 instances **khác** với 4 App Service Plans. Nó cũng khác 4 deployment slots. Việc tạo thêm slot không tự tạo thêm một máy riêng để scale production.

## 3. Scale up, scale down, scale out và scale in

### 3.1. Scale up (vertical scaling)

**Scale up** nghĩa là chuyển plan lên tier/size có nhiều tài nguyên hoặc tính năng hơn. Ví dụ:

~~~text
Trước:  App Service Plan Standard S1
Sau:    App Service Plan Premium v3 P1v3
~~~

Đây là ví dụ minh họa về **thay tier và size**; không phải phép so sánh hiệu năng tuyệt đối cho mọi ứng dụng. Các mức CPU, memory, tính năng và giá cần đối chiếu đúng SKU tại thời điểm triển khai.

Scale up thích hợp khi:

- Một instance thiếu **RAM**, bị out-of-memory hoặc phải garbage collection quá nhiều.
- Workload cần tài nguyên mạnh hơn cho một process/request, không phân chia tốt cho nhiều instances.
- Cần tính năng thuộc tier cao hơn như một số lựa chọn networking, deployment slots hoặc cấu hình hỗ trợ riêng.
- Ứng dụng hiện đã scale out nhưng **mỗi worker vẫn thiếu tài nguyên**.

**Scale down** là giảm tier/size để tiết kiệm khi workload đã thấp, với điều kiện tier đích vẫn hỗ trợ ứng dụng và đủ headroom.

### 3.2. Scale out (horizontal scaling)

**Scale out** tăng số instances chạy ứng dụng:

~~~text
Trước:  2 worker instances
Sau:    5 worker instances
~~~

Scale out thường phù hợp khi ứng dụng:

- Xử lý request có thể chia độc lập cho nhiều workers.
- Phần lớn xử lý nằm trong CPU và bộ nhớ của ứng dụng, không bị phụ thuộc duy nhất khác nghẽn.
- Đã được thiết kế **stateless** hoặc có session state dùng chung.
- Có health check và cơ chế khởi tạo instance mới an toàn.

**Scale in** giảm số instances khi tải xuống thấp. Scale in cần đặc biệt chú ý request đang xử lý, session, background jobs và dữ liệu lưu cục bộ.

### 3.3. Bảng so sánh

| Tiêu chí | Scale up/down | Scale out/in |
| --- | --- | --- |
| Thay đổi | Tier/size năng lực của worker | Số lượng instances |
| Mục tiêu | Tăng/giảm năng lực mỗi worker, thay tính năng plan | Tăng/giảm tổng năng lực phục vụ song song |
| Tối ưu cho | Memory-bound hoặc xử lý khó phân phối | HTTP/API request độc lập, workload song song |
| Tác động tới trạng thái | Thay SKU có thể gây restart/di chuyển workload | Instance mới khởi động, instance cũ có thể bị loại bỏ |
| Ứng dụng cần chuẩn bị | Kiểm tra tương thích tier, tài nguyên, cấu hình | Stateless, session store, shared storage, graceful shutdown |
| Chi phí | Phụ thuộc tier/size và số instances | Thường tăng/giảm cùng số lượng instances tính phí |
| Rủi ro | Chọn tier đắt nhưng vẫn bị nghẽn dependency | Chia nhỏ tài nguyên không giải quyết DB, lock hoặc rate limit |
| Khả năng tự động | Không nên mặc định autoscale sẽ tự chuyển SKU | Autoscale thường thay đổi **instance count**, không tự nâng cấp tier |

### 3.4. Ví dụ quyết định

Giả sử chỉ có một instance và:

- CPU 25%, memory sử dụng gần giới hạn, thường xuyên OOM: ưu tiên đánh giá **scale up** hoặc sửa memory leak.
- CPU 85%, memory 45%, mỗi request độc lập, database còn headroom: đánh giá **scale out**.
- CPU 20%, số kết nối SQL chạm tối đa, latency truy vấn SQL tăng: điều tra **database và connection pool** trước.
- CPU tăng vào 12:00–13:00 hằng ngày, thấp về đêm: cân nhắc **autoscale theo metric hoặc schedule**.

Trong cả bốn tình huống, cần đối chiếu với error rate, latency và nguyên nhân ứng dụng; metric CPU đơn lẻ không đủ để ra quyết định.

## 4. Những giới hạn phải kiểm tra trước khi scale

### 4.1. SKU/tier và khả năng scaling

App Service có các tier như Free/Shared, Basic, Standard, Premium và Isolated, cùng các thế hệ/biến thể. **Manual scaling, Azure Monitor autoscale và App Service automatic scaling không khả dụng như nhau trên tất cả tiers.**

Cách kiểm tra thực tế:

1. Xác định SKU/tier của **App Service Plan**, ví dụ `S1` hay `P1v3`.
2. Xem tính năng scale trong Azure portal đối với plan/web app đó.
3. Xem giới hạn instances, VM family, region và quota subscription.
4. Kiểm tra đang sử dụng **rule-based autoscale** hay một chế độ **automatic scaling** khác.
5. Kiểm tra giới hạn tổng instances và những điều kiện riêng của App Service Environment khi có.

Không dùng một con số giới hạn instance cố định lấy từ tier khác để quyết định scale trên production.

### 4.2. Tăng instance không tăng tài nguyên vô hạn

Một lần scale out có thể bị chặn hoặc không đạt kỳ vọng vì:

- Đã tới giới hạn count của tier hoặc cấu hình plan.
- Subscription/region có quota/capacity constraint.
- Instance mới đang khởi động hoặc ứng dụng cần warm-up.
- Database, API ngoài hoặc storage đang là điểm nghẽn.
- Những instance mới lỗi startup/health check nên không thực sự nhận request.
- Cấu hình session affinity, filesystem cục bộ hoặc background job không hỗ trợ multi-instance.

**Desired instance count không đồng nghĩa số instances khỏe mạnh ngay lập tức.** Trong sự cố tải cao, phải xem cả thời gian scale và số worker thực sự sẵn sàng.

### 4.3. Scale không tự động cải thiện tính sẵn sàng toàn hệ thống

Nhiều instances giúp phân tán tải và giảm phụ thuộc vào một worker, nhưng:

- Các instances cùng plan có thể vẫn nằm trong một region và cùng chịu sự cố vùng.
- Database single point of failure vẫn tồn tại.
- Một lỗi trong phiên bản ứng dụng mới có thể tác động **mọi worker**.
- Muốn tính sẵn sàng theo zone/multi-region phải thiết kế riêng theo khả năng SKU, region và kiến trúc phù hợp.
- Scale out không thay thế backup, disaster recovery hoặc giám sát.

## 5. Chuẩn bị ứng dụng trước khi scale out

Một ứng dụng chạy tốt trên một instance chưa chắc chạy đúng khi có nhiều instances.

### 5.1. Tránh lưu session quan trọng trong bộ nhớ của một worker

Ví dụ người dùng đăng nhập và session chỉ nằm trong RAM của Worker A:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant R as App Service routing
    participant A as Worker A
    participant B as Worker B
    U->>R: Login
    R->>A: Request 1
    A-->>U: Session chỉ lưu ở Worker A
    U->>R: Request 2
    R->>B: Request chuyển sang Worker B
    B-->>U: Không thấy session
~~~

Để tránh lỗi:

- Dùng session store dùng chung, ví dụ **Azure Managed Redis** hoặc một dịch vụ/cache phù hợp với ứng dụng.
- Đặt trạng thái nghiệp vụ trong database, storage hoặc dịch vụ được thiết kế để chia sẻ.
- Ưu tiên token/session được xác thực an toàn và không phụ thuộc một instance khi kiến trúc phù hợp.
- Không coi **ARR affinity/sticky session** là giải pháp bền vững duy nhất: worker có thể bị recycle, scale in hoặc đổi đích.

### 5.2. Không dựa vào local filesystem cho trạng thái bền vững

App Service có thể có không gian lưu trữ ứng dụng và temporary storage với semantics khác nhau theo môi trường. Khi có nhiều instances, không giả định mọi tệp được ghi vào **thư mục tạm cục bộ** đều hiện trên các worker khác hoặc tồn tại sau restart.

Các loại dữ liệu thường nên đưa ra khỏi worker:

| Dữ liệu | Nơi nên xem xét |
| --- | --- |
| Tệp upload | Azure Blob Storage hoặc dịch vụ storage phù hợp |
| Session | Shared cache hoặc session service |
| Job queue | Azure Service Bus, Azure Queue Storage hoặc hàng đợi phù hợp |
| Kết quả xử lý cần lưu | Database / Blob Storage |
| Log quan trọng | Application Insights / Log Analytics / đích ghi log |
| Khóa/bí mật | Azure Key Vault và managed identity theo thiết kế |

Không dùng local cache hoặc thư mục tạm làm nguồn dữ liệu nghiệp vụ duy nhất.

### 5.3. Xử lý background jobs và singleton tasks

Một ứng dụng thường chạy timer, scheduled task hoặc xử lý queue ngay trong web process. Sau scale out, **mỗi instance có thể cùng khởi tạo tác vụ** nếu mã không được thiết kế để điều phối.

Ví dụ một job “gửi báo cáo lúc 00:00” chạy trên 4 instances có thể gửi 4 email hoặc ghi trùng dữ liệu.

Giải pháp:

- Chuyển công việc nền sang Azure Functions, WebJobs hoặc dịch vụ job độc lập phù hợp.
- Dùng queue và cơ chế claim/lock/idempotency nếu nhiều workers cùng xử lý.
- Đảm bảo operations có thể chạy lại an toàn.
- Theo dõi retry và dead-letter, không dựa vào việc scale in sẽ dừng job đúng thời điểm.

### 5.4. Warm-up, readiness và graceful shutdown

Worker mới cần thời gian để:

1. Khởi tạo runtime và nạp ứng dụng.
2. Mở kết nối cần thiết.
3. Nạp cấu hình, cache hoặc dependencies.
4. Sẵn sàng đáp ứng request hợp lệ.

Cần thiết kế **Health check** endpoint như `/health/ready` để phản ánh khả năng phục vụ, đặc biệt khi khởi tạo chậm. Trên các tier/cấu hình hỗ trợ, **Always On** có thể giúp hạn chế việc ứng dụng bị idle rồi khởi động lại, nhưng không thay thế health check hay capacity planning.

Khi instance bị loại bỏ, ứng dụng cần xử lý shutdown an toàn, tránh để mất request/dữ liệu. Không nên chạy tác vụ cần nhiều giờ trong một HTTP request nếu worker có thể bị recycle hoặc scale in.

### 5.5. Connection pools và downstream limits

Giả sử mỗi instance mở tối đa 80 kết nối database:

~~~text
2 instances × 80 connections = 160 possible connections
6 instances × 80 connections = 480 possible connections
~~~

Nếu database chỉ cho phép hoặc chịu tải tốt ở khoảng 250 kết nối, scale out lên 6 có thể làm hệ thống **kém ổn định hơn**. Cần điều chỉnh pool limits, caching, pooling strategy, database capacity và retry/backoff có kiểm soát.

## 6. Manual scaling trong Azure portal và Azure CLI

### 6.1. Kiểm tra trạng thái hiện tại

Đầu tiên chọn đúng tenant/subscription và đọc cấu hình:

~~~bash
az login

az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Chỉ đổi subscription khi đã xác minh đúng subscription đích.
az account set --subscription "<SUBSCRIPTION_ID>"

# Đọc cấu hình plan.
az appservice plan show \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --query "{name:name, location:location, sku:sku.name, tier:sku.tier, capacity:sku.capacity}" \
  --output json

# Đọc web app và plan mà ứng dụng đang sử dụng.
az webapp show \
  --resource-group rg-web-lab \
  --name shop-api-lab \
  --query "{name:name, state:state, serverFarmId:serverFarmId}" \
  --output json
~~~

Các tên trong ví dụ là giả định; phải thay bằng tài nguyên thực tế được cấp quyền. Lệnh trên không tạo/chỉnh sửa tài nguyên. Nếu App Service Plan không tồn tại, kiểm tra subscription và resource group trước khi làm việc tiếp.

### 6.2. Scale up bằng portal

Với người có quyền quản lý App Service Plan:

1. Mở **Azure portal → App Service Plans** và chọn plan chứa Web App.
2. Xem SKU/tier và các ứng dụng đang chia sẻ plan.
3. Mở chức năng **Scale up (App Service plan)** hoặc khu vực thay đổi pricing plan tương ứng.
4. So sánh CPU, memory, khả năng, giá và hỗ trợ của tier đích.
5. Áp dụng thay đổi trong thời điểm bảo trì được phê duyệt nếu có nguy cơ khởi động lại/gián đoạn.
6. Quan sát provisioning, HTTP error rate, p95 latency và ứng dụng phụ thuộc sau thay đổi.

### 6.3. Scale up bằng Azure CLI

~~~bash
# Ví dụ thay SKU của App Service Plan; CÓ thể phát sinh phí và restart.
az appservice plan update \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --sku P1v3
~~~

**Không chạy lệnh này trên production khi chưa được phép.** Nó thay plan, có thể ảnh hưởng các apps/slots chung plan, tính năng, chi phí và vòng đời worker. Phải xác minh hỗ trợ SKU đích tại region và tương thích với môi trường.

### 6.4. Scale out thủ công

Trong portal, dùng **Scale out (App Service plan)** và chọn số instances trong mức tier cho phép. Với CLI:

~~~bash
# Ví dụ thay số worker instances thành 3.
# Thao tác thay đổi tài nguyên và chi phí.
az appservice plan update \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --number-of-workers 3
~~~

Sau đó đọc lại cấu hình:

~~~bash
az appservice plan show \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --query "{name:name, sku:sku.name, tier:sku.tier, instances:sku.capacity}" \
  --output json
~~~

`sku.capacity` thể hiện số instances theo cấu hình plan, nhưng thời gian khởi động, health và việc request thực sự tới worker cần được kiểm tra thêm qua metric/log.

### 6.5. Phân biệt thay cấu hình và xác minh hiệu quả

Một thay đổi scale là **thao tác control plane**. Thành công khi Azure API trả kết quả không đồng nghĩa p95 latency giảm hoặc tất cả instances đã sẵn sàng. Sau scale cần:

- Xác nhận effective instance count theo dữ liệu sản phẩm.
- Kiểm tra hoạt động của các app chia sẻ plan.
- Đối chiếu HTTP 2xx/4xx/5xx, thời gian phản hồi.
- Xem CPU/memory, DB connections, errors và logs.
- Kiểm tra chi phí tăng/giảm phù hợp kỳ vọng.

## 7. Autoscale theo metric với Azure Monitor

**Azure Monitor autoscale** là cơ chế định nghĩa quy tắc tự động tăng/giảm **số instances** của tài nguyên được hỗ trợ theo metric hoặc schedule. Với App Service Plan đủ điều kiện, autoscale có thể điều chỉnh capacity của plan khi tải thay đổi.

### 7.1. Các thành phần của autoscale setting

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Target resource** | Plan sẽ bị thay số instances | `asp-web-prod` |
| **Minimum instances** | Mức thấp nhất autoscale được phép giảm | 2 |
| **Maximum instances** | Mức cao nhất autoscale được phép tăng | 6 |
| **Default instances** | Mức mặc định cho profile khi cần | 2 |
| **Metric rule** | Ngưỡng và cửa sổ tính toán | Average CPU trên 70% trong 10 phút |
| **Scale action** | Thêm hoặc bớt instances | +1 / −1 |
| **Cooldown** | Khoảng hạn chế đánh giá lại hành động scale sau thay đổi | 10–20 phút |
| **Autoscale profile** | Nhóm ngưỡng/instance bounds theo lịch | Giờ cao điểm / ngoài giờ |
| **Notification** | Báo sự kiện scaling và lỗi cho vận hành | Email, webhook, alert tùy khả năng |

### 7.2. Ví dụ quy tắc quy mô nhỏ

Giả sử một web API được thiết kế stateless và xử lý CPU-bound. Nhóm vận hành chọn:

~~~yaml
# CẤU HÌNH MINH HỌA, không phải tệp ARM/Bicep có thể triển khai trực tiếp.
target: asp-web-prod
instances:
  min: 2
  default: 2
  max: 6
rules:
  - direction: scale-out
    metric: CPU Percentage
    condition: average > 70% during 10 minutes
    action: add 1 instance
    cooldown: 10 minutes
  - direction: scale-in
    metric: CPU Percentage
    condition: average < 35% during 20 minutes
    action: remove 1 instance
    cooldown: 20 minutes
~~~

Giữa 35% và 70%, không có yêu cầu scale từ hai quy tắc này. Khoảng cách giữa ngưỡng lên/xuống gọi là **hysteresis** trong thiết kế điều khiển, giúp giảm thay đổi liên tục khi metric dao động quanh một mốc.

Các giá trị 70%, 35%, 10/20 phút là **ví dụ cần điều chỉnh theo SLO và dữ liệu thực tế**, không phải ngưỡng Azure khuyến nghị cho mọi ứng dụng.

### 7.3. Vì sao phải có scale-in rule và cooldown?

Nếu chỉ tăng mà không giảm, chi phí có thể giữ ở mức cao sau khi traffic hạ. Ngược lại, nếu scale in quá sớm, ứng dụng có thể gặp tình trạng dao động:

~~~text
CPU 72% → thêm instance
CPU 32% → bớt instance
CPU 75% → thêm instance
...
~~~

**Cooldown, ngưỡng lên/xuống khác nhau và cửa sổ thời gian** giúp hạn chế việc tăng/giảm liên tục. Autoscale service còn có những cơ chế đánh giá quy tắc/điều chỉnh theo bảo vệ riêng; không nên coi kết quả sẽ tăng hoặc giảm tức thời theo từng điểm metric đơn lẻ.

### 7.4. Không nên dựa duy nhất vào CPU

CPU là tín hiệu tốt cho một số workload compute-bound, nhưng:

- App chờ database/API: CPU thấp trong khi request latency cao.
- App memory leak: CPU bình thường, memory tăng liên tục.
- Queue dài nhưng CPU không tăng vì phần mềm chỉ có một thread xử lý.
- Một tác vụ batch dùng CPU của plan chung có thể kích autoscale cho nhiều Web App.

Tùy metric được phát hành, có thể cân nhắc **memory usage, HTTP queue length, request count, response time** hoặc metric tùy chỉnh thích hợp. Cần xác minh loại metric hỗ trợ làm tín hiệu autoscale cho tài nguyên ở thời điểm triển khai.

**Quy tắc tốt xuất phát từ bottleneck thật**, không chỉ từ việc metric dễ thấy trong portal.

### 7.5. Schedule-based scaling

Nếu có giờ cao điểm dự báo trước, ví dụ 18:00–22:00 hằng ngày, có thể dùng autoscale profiles theo lịch:

| Thời gian | Min | Default | Max | Ý nghĩa |
| --- | ---: | ---: | ---: | --- |
| Ban ngày thường | 2 | 2 | 5 | Chi phí thấp hơn |
| Giờ mở bán đã biết | 4 | 4 | 10 | Có capacity sẵn trước khi tải tăng |
| Ban đêm | 2 | 2 | 4 | Có giới hạn scale in phù hợp |

Con số minh họa. Schedule cần cấu hình timezone/chuyển giờ đúng và xác minh một profile không chồng lấn với profile khác theo cách gây khó dự đoán.

**Kết hợp quy tắc và lịch** giúp chuẩn bị capacity trước khi metric tăng; autoscale theo metric thuần thường có độ trễ do thời gian thu thập metric, đánh giá, provision và warm-up.


## 8. Tạo và kiểm tra Azure Monitor autoscale

### 8.1. Cấu hình qua Azure portal

Trên App Service Plan có tier hỗ trợ rule-based autoscale:

1. Mở **App Service Plan** trong Azure portal, xác nhận region, SKU, danh sách Web Apps và current instance count.
2. Mở **Scale out** hoặc mục **Autoscale** liên quan. Giao diện có thể chuyển tới **Azure Monitor autoscale settings** tùy phiên bản portal.
3. Chọn chế độ **custom/rule-based autoscale** phù hợp, tạo profile với min, default và max instances.
4. Tạo **scale-out rule** theo metric và khoảng thời gian đã phân tích. Ví dụ CPU trung bình vượt 70% trong 10 phút, thêm một instance.
5. Tạo **scale-in rule** với ngưỡng thấp hơn và thời gian duy trì dài hơn. Ví dụ CPU dưới 35% trong 20 phút, giảm một instance.
6. Cấu hình cooldown, notification, lịch đặc biệt nếu cần; bảo đảm khoảng min/max không vượt giới hạn tài nguyên.
7. Lưu autoscale settings rồi kiểm tra **Scale history / Run history / Activity Log** và sự thay đổi instance count.
8. Theo dõi latency, 5xx, CPU/memory và lỗi backend trong ít nhất một chu kỳ tải đại diện.

Hãy xem kỹ liệu hệ thống đang dùng rule-based autoscale **hay một chế độ automatic scaling khác** trước khi bật thêm cấu hình. Không tạo hai bộ điều khiển tự động mâu thuẫn nhau cho cùng mục tiêu.

### 8.2. Đọc resource ID và metric được hỗ trợ bằng CLI

~~~bash
# Đọc Resource ID của App Service Plan.
PLAN_ID=$(az appservice plan show \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --query id \
  --output tsv)

echo "$PLAN_ID"

# Liệt kê các autoscale settings trong resource group.
az monitor autoscale list \
  --resource-group rg-web-lab \
  --output table

# Xem các metric definitions thực sự có trên plan.
az monitor metrics list-definitions \
  --resource "$PLAN_ID" \
  --output table
~~~

Lệnh chỉ đọc. Cần kiểm tra **tên metric và unit thực tế** thay vì suy từ một dashboard mẫu. Chẳng hạn CPU percentage và memory percentage có thể được đặt tên khác nhau giữa resource types hoặc API.

### 8.3. Tạo autoscale setting bằng CLI (ví dụ cấu hình có thay đổi tài nguyên)

Khi có môi trường lab được phép và tier hỗ trợ, Azure CLI cung cấp nhóm lệnh quản lý autoscale:

~~~bash
# THAO TÁC GHI: tạo autoscale setting cho plan.
az monitor autoscale create \
  --resource-group rg-web-lab \
  --name autoscale-asp-web-lab \
  --resource "$PLAN_ID" \
  --min-count 2 \
  --max-count 6 \
  --count 2
~~~

Lệnh tạo thiết lập với giới hạn instance. **Phải thêm metric rules/profile phù hợp** thì mới có hành vi scale theo tải như thiết kế. Trong một số phiên bản CLI/extension, đối số, tính năng và quyền hỗ trợ có thể khác; kiểm tra `az monitor autoscale create --help` trước khi chạy.

Làm tiếp qua Azure portal để thiết lập quy tắc theo CPU và cooldown; hoặc dùng `az monitor autoscale rule create --help` rồi khai báo chính xác metric có sẵn. Không dùng một chuỗi biểu thức rule sao chép từ loại tài nguyên khác mà chưa kiểm tra.

### 8.4. Xác nhận autoscale setting đang áp dụng

~~~bash
az monitor autoscale show \
  --resource-group rg-web-lab \
  --name autoscale-asp-web-lab \
  --output json

az appservice plan show \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --query "{sku:sku.name, configuredInstances:sku.capacity}" \
  --output json
~~~

Cần phân biệt ba phép kiểm tra:

- **Setting đúng:** có min/max, rule và cooldown như phê duyệt.
- **Scale action xảy ra:** nhật ký/activity phản ánh tăng/giảm count tại thời điểm phù hợp.
- **Ứng dụng cải thiện:** ứng dụng đáp ứng SLO, instances khỏe, không phát sinh lỗi 5xx hoặc quá tải database.

Một autoscale setting hoạt động về mặt kỹ thuật chưa có nghĩa quy tắc đang mang lại hiệu quả cho người dùng.

## 9. Automatic scaling của App Service khác rule-based autoscale

Azure App Service có thể cung cấp **automatic scaling** theo lưu lượng HTTP cho những App Service Plan/tier đủ điều kiện. Đây là một chế độ khác với **Azure Monitor autoscale** dựa trên metric/schedule mà bạn tự đặt.

### 9.1. Tư duy của automatic scaling

Ở chế độ được hỗ trợ, App Service có thể tự điều chỉnh số instances phục vụ **từng ứng dụng web** theo HTTP traffic và các tham số luôn sẵn sàng/giới hạn của cơ chế này.

Những khái niệm thường gặp:

- **Always ready instances:** số instances tối thiểu được giữ sẵn cho ứng dụng ở cấu hình hỗ trợ.
- **Maximum scale limit:** trần instances cho ứng dụng trong phạm vi được phép.
- **Prewarmed instances:** năng lực được chuẩn bị theo cơ chế của tính năng, giúp nhận tải khi cần.
- **Traffic-based scale:** dịch vụ quản lý quyết định scale dựa trên lưu lượng, thay vì người dùng tự đặt ngưỡng CPU 70%.

Khả năng, cấu hình, nơi hiển thị trong portal và giới hạn có thể thay đổi theo **tier, region, loại App Service Plan và phiên bản dịch vụ**. Không giả định tính năng này có mặt ở Basic hoặc mọi môi trường App Service.

### 9.2. So sánh hai chế độ tự động

| Tiêu chí | Azure Monitor autoscale | App Service automatic scaling |
| --- | --- | --- |
| Cách kích hoạt | Quy tắc metric hoặc schedule do người vận hành định nghĩa | Cơ chế automatic scaling của App Service theo traffic khi được hỗ trợ |
| Phạm vi thông dụng | Điều chỉnh số instances của App Service Plan | Có thể điều chỉnh theo Web App trong phạm vi cấu hình tính năng |
| Người dùng đặt ngưỡng CPU cụ thể? | Có, nếu chọn metric CPU | Không phải mô hình chính của tính năng |
| Cấu hình chính | Min/default/max, metric rules, cooldown, profiles | Always-ready, maximum scale limit và các tùy chọn liên quan |
| Phù hợp khi | Cần kiểm soát ngưỡng, lịch, metric đặc thù | HTTP workload cần quản lý scale tự động với ít quy tắc tùy chỉnh |
| Điều kiện hỗ trợ | Phụ thuộc tier, SKU và target resource | Phụ thuộc tiers/tính năng App Service cụ thể |
| Giới hạn | Tác động bởi metric delay, min/max, quota, warm-up | Vẫn có trần, warm-up, dependency bottleneck, chi phí |

Nếu portal cho phép lựa chọn các chế độ, hãy dùng **một cơ chế phù hợp** và kiểm tra cấu hình hiện có. Không cho rằng hai loại autoscale có thể cùng ghi đè instance count mà không xung đột.

### 9.3. Automatic scaling không giải quyết mọi bài toán

Dù số worker được tự quản lý, ứng dụng vẫn cần:

- Stateless session và shared dependencies.
- Readiness/health checks.
- Database capacity và connection pooling.
- Đo p95 latency, lỗi HTTP và capacity.
- Chính sách min/max phù hợp ngân sách.
- Quy trình phản ứng khi autoscale chạm trần nhưng ứng dụng còn chậm.

Nếu một Web App trong shared plan có tải khác hẳn các apps còn lại, automatic scaling có thể là lựa chọn đáng đánh giá **nếu cấu hình hỗ trợ theo ứng dụng**; cũng có thể cần tách plan để bảo đảm cách ly tài nguyên và chi phí.

## 10. Đo hiệu quả scale bằng Azure Monitor và Application Insights

### 10.1. Không chỉ nhìn CPU

Trước và sau một thay đổi scale, ghi cùng các nhóm dữ liệu:

| Nhóm chỉ số | Tác dụng |
| --- | --- |
| **CPU Percentage** | Nhận diện compute-bound workload hoặc background CPU contention |
| **Memory Percentage / Working Set** | Kiểm tra memory pressure, garbage collection và OOM |
| **Requests/Second** | Đo tải đầu vào và capacity đạt được |
| **HTTP 5xx** | Theo dõi lỗi máy chủ, backend hoặc ứng dụng |
| **Response time, p95/p99** | Kiểm tra SLO độ trễ thực tế |
| **HTTP queue length** | Phát hiện yêu cầu xếp hàng khi worker thiếu capacity |
| **Instance count** | Xác minh autoscale đã đổi công suất |
| **Restarts, availability, health check** | Xác định worker có thực sự sẵn sàng |
| **Dependency latency** | SQL, cache, storage hoặc API bên ngoài có bị quá tải không |
| **Cost and budget** | Chi phí compute/monitoring so với lợi ích |

Không phải metric nào cũng sẵn với mọi SKU và cấu hình telemetry. Chọn danh sách metric thực tế của **App Service Plan, Web App, Application Insights** hoặc hệ thống log đang dùng.

### 10.2. Phân biệt metric cấp plan và cấp app

- Metric của **App Service Plan** có thể bao gồm tải tổng thể các ứng dụng/slots dùng chung compute.
- Metric của **Web App** phản ánh đặc điểm cụ thể của ứng dụng, ví dụ số request, status code hoặc response time.
- **Application Insights** giúp xem request, dependency, exception và latency theo operation, nếu đã được cấu hình.
- Metric của Azure SQL hoặc cache phải xem riêng, vì những dịch vụ này không tự scale cùng App Service Plan.

Nếu plan chạy `shop-api` và `reporting`, CPU plan cao có thể do job trong `reporting`. Khi đó, autoscale CPU của plan vẫn phản ứng theo tải chung, nhưng không chứng minh `shop-api` là nguyên nhân.

### 10.3. Ví dụ KQL khi dùng Application Insights

Nếu môi trường đã thu thập request telemetry vào bảng `requests` của Application Insights:

~~~kusto
requests
| where timestamp >= ago(2h)
| summarize
    TotalRequests = count(),
    Failures = countif(success == false),
    P95Latency = percentile(duration, 95)
    by bin(timestamp, 5m)
| order by timestamp asc
~~~

Truy vấn này giúp đối chiếu thời điểm tăng traffic với p95 latency và số request thất bại. **Bảng và tên trường có thể khác** nếu dùng workspace-based resource-specific tables hoặc pipeline observability khác; hãy xem schema thực tế và thay truy vấn tương ứng.

Để tìm thao tác chậm:

~~~kusto
requests
| where timestamp >= ago(1h)
| summarize
    Requests = count(),
    P95Latency = percentile(duration, 95),
    FailureCount = countif(success == false)
    by name
| order by P95Latency desc
~~~

Nếu kết quả cho thấy chỉ `POST /checkout` chậm còn các endpoint khác bình thường, cần điều tra dependency/lock/query của checkout trước khi kết luận thiếu số instances.

### 10.4. Theo dõi sự kiện autoscale

Có thể sử dụng:

- **Azure Monitor autoscale history / Activity Log**.
- Metrics của plan/web app theo thời gian.
- Application Insights hoặc Log Analytics.
- Azure Monitor alerts để báo khi instance count sát maximum hoặc khi SLO xấu.
- **Cost Management** để theo dõi compute và dịch vụ phụ trợ.

Khi autoscale không xảy ra, kiểm tra trạng thái enable của setting, profile hiệu lực, điều kiện metric, thời gian tổng hợp, quota và lịch sử hành động. Không mặc định lỗi ngay chỉ vì CPU vượt ngưỡng trong một lần đo vài giây.

## 11. Bài toán sizing: 2 hay 10 instances?

### 11.1. Ước tính từ throughput đo thực tế

Giả sử load test trong lab cho biết một instance xử lý khoảng **150 requests/giây** khi p95 latency còn dưới ngưỡng SLO. Giờ cao điểm dự kiến có **1.200 requests/giây**.

Không có headroom:

\[
\text{Số instances tối thiểu theo mô hình đơn giản}
=
\left\lceil\frac{1200}{150}\right\rceil
=8
\]

Nếu chủ động chỉ sử dụng tối đa khoảng 80% capacity đo được để có headroom:

\[
N
=
\left\lceil\frac{1200}{150\times0.8}\right\rceil
=
10
\]

**Kết luận sơ bộ:** cân nhắc khoảng 10 instances để đáp ứng workload giả định theo mô hình tuyến tính.

Đây chỉ là **bài toán ước lượng**, không bảo đảm 10 instances luôn đạt 1.200 RPS. Hiệu năng thực tế còn phụ thuộc concurrency, response size, database, cache, warm-up, routing, instance variance và chi phí.

### 11.2. Tăng instances có thể làm database quá tải

Giả sử ứng dụng mỗi instance có connection pool tối đa 50 kết nối:

~~~text
2 instances × 50 connections = 100
8 instances × 50 connections = 400
10 instances × 50 connections = 500
~~~

Nếu database chỉ chịu khoảng 300 kết nối hữu ích theo tải thật, 10 instances có thể làm SQL contention tăng, gây request timeout dù CPU của web app thấp.

Cần tối ưu query, thiết kế cache, điều chỉnh connection pools và sizing backend trước khi tăng tối đa lên 10. Autoscale phải đặt **max count có cơ sở**, không chỉ theo ngân sách.

### 11.3. Ước tính compute instance-hours

Giả sử một ngày có 21 giờ chạy 2 instances và 3 giờ mở bán cần 10 instances, ở cùng tier/SKU.

~~~text
21 giờ × 2 instances = 42 instance-hours
 3 giờ × 10 instances = 30 instance-hours
Tổng                   = 72 instance-hours/ngày
~~~

Nếu chạy cố định 10 instances suốt ngày:

~~~text
24 giờ × 10 instances = 240 instance-hours/ngày
~~~

Theo mô hình đơn giản, autoscale có thể giảm mức dùng compute từ 240 xuống 72 instance-hours/ngày. Tuy nhiên, **chi phí thực tế** còn phụ thuộc thời gian provision/scale-in, đơn giá tier, thời lượng tính phí, tính năng cùng plan, các dịch vụ khác và quy định giá hiện hành. Không nên dùng tỷ lệ này để khẳng định hóa đơn sẽ giảm chính xác bao nhiêu phần trăm.

### 11.4. Tốc độ mở bán tăng trong 20 giây

Nếu traffic nhảy từ 200 lên 1.200 RPS trong 20 giây, rule “CPU > 70% trung bình 10 phút” **có thể phản ứng muộn** do thời gian lấy mẫu và khởi tạo instances.

Nên cân nhắc:

- **Pre-scale theo lịch** trước giờ mở bán dự kiến.
- Duy trì minimum instances đủ cho tải không thể dự báo.
- Caching/CDN, queue và rate limiting để làm mềm đỉnh.
- Kiểm thử hiệu năng warm-up của worker mới.
- Điều chỉnh rules theo dữ liệu thực tế, tránh thay ngưỡng quá nhạy gây oscillation.

## 12. Những tình huống autoscale không giúp hoặc gây lỗi

### 12.1. CPU thấp, response time cao

**Dấu hiệu:** CPU App Service Plan chỉ 25%, nhưng p95 latency của API tăng từ 250 ms lên 4 giây. Azure SQL có nhiều slow query.

**Phân tích:** request đang chờ database. Thêm web instances có thể làm tăng số request cùng lúc tới SQL.

**Hướng xử lý:** phân tích query/index, connection pool, retries, caching và SQL capacity. Chỉ scale web khi bằng chứng cho thấy web tier đang là bottleneck.

### 12.2. Memory leak trên mỗi instance

**Dấu hiệu:** sau mỗi vài giờ, memory của một worker tăng dần tới ngưỡng, sau đó tiến trình bị restart. Scale out từ 2 lên 5 instances giảm tải nhưng leak vẫn tái diễn.

**Phân tích:** scale out có thể kéo dài thời gian trước khi chạm trần nhưng không loại bỏ memory leak.

**Hướng xử lý:** ghi heap dumps/diagnostics theo quy trình bảo mật, xem object retention, connection/resource leaks, sửa mã và load test. Scale up tạm thời có thể giúp giảm tác động nhưng vẫn phải xử lý gốc.

### 12.3. Session lưu trong RAM và người dùng bị đăng xuất

**Dấu hiệu:** sau scale out, người dùng chuyển trang và đôi khi mất phiên đăng nhập.

**Phân tích:** session chỉ nằm trên một worker. ARR affinity có thể làm hiện tượng ít xảy ra hơn nhưng worker recycling và scale in vẫn là rủi ro.

**Hướng xử lý:** chuyển session state ra shared store, kiểm tra khóa mã hóa/session secrets dùng chung, logout và retry. Kiểm thử có chủ đích khi tắt sticky session nếu ứng dụng hỗ trợ.

### 12.4. Cron job chạy lặp sau scale out

**Dấu hiệu:** hệ thống gửi cùng thông báo bốn lần khi scale từ 1 lên 4 instances.

**Phân tích:** timer nằm trong web process được nhân bản.

**Hướng xử lý:** tách scheduled job, dùng queue/lock/idempotency và giám sát duplicate executions.

### 12.5. Scale in làm mất công việc đang chạy

**Dấu hiệu:** một HTTP request xuất báo cáo 15 phút bị gián đoạn khi instance bị scale in/recycle.

**Hướng xử lý:** chuyển công việc dài sang background processing có lưu trạng thái, queue và cơ chế retry; request HTTP chỉ khởi tạo job và trả job ID.

### 12.6. Autoscale đã chạm maximum

**Dấu hiệu:** CPU cao, instance count ở 6/6, HTTP queue tăng.

**Hướng xử lý:** kiểm tra tier/quota, tối ưu app, đánh giá kế hoạch mở rộng max và backend capacity, chuẩn bị scale up hoặc tách workloads. Không vô hạn tăng max mà thiếu ngân sách và khả năng backend.

### 12.7. Hai ứng dụng dùng chung plan gây nhiễu metric

**Dấu hiệu:** `shop-api` ít traffic nhưng CPU plan cao mỗi đêm do `reporting`.

**Hướng xử lý:** tách App Service Plan cho workload quan trọng nếu cần; điều chỉnh lịch batch; chọn metric autoscale phù hợp và xem giới hạn từng app. Không giả định cả hai cần cùng số worker.

## 13. Kiểm soát chi phí khi scale

### 13.1. Compute được tính theo App Service Plan và công suất

Với mô hình plan dedicated thông thường, chi phí compute gắn với **tier/size và số instances theo thời gian**, không chỉ số request thực tế. Một plan chia sẻ bởi nhiều Web Apps vẫn là tài nguyên compute chung; các dịch vụ như Log Analytics, Application Insights, database, network hoặc storage có thể tính phí riêng.

| Quyết định | Ảnh hưởng chi phí |
| --- | --- |
| Scale up lên tier/size cao hơn | Đơn giá mỗi instance có thể tăng |
| Scale out từ 2 lên 6 instances | Công suất tính phí tăng cùng số instances |
| Tăng minimum instances | Có thể tăng chi phí nền suốt ngày |
| Scale in khi tải giảm | Giảm instance-hours nếu cấu hình cho phép |
| Giữ plan riêng cho từng ứng dụng | Tăng cách ly nhưng có thể tăng số plan/instances |
| Thêm Application Insights hoặc log lưu lâu | Có thể tăng chi phí nạp/lưu giữ |
| Scale web mà không scale database | Chi phí web tăng nhưng SLO chưa chắc tốt hơn |

### 13.2. Thiết kế giới hạn có chủ đích

Một autoscale profile hợp lý cần:

- Min instances đáp ứng tải bình thường và yêu cầu sẵn sàng.
- Max instances vừa đảm bảo tải dự kiến vừa bảo vệ budget/downstream.
- Scale-in rule để không giữ công suất cao quá lâu.
- Alert khi ở max quá lâu hoặc autoscale thất bại.
- Đánh giá chi phí thực sau ít nhất một chu kỳ tải điển hình.

Chi phí cần được kiểm tra bằng **Azure Pricing Calculator** và **Cost Management** theo region, SKU, chính sách giá và subscription thực tế. Không sao chép giá/giới hạn từ một region hoặc tier khác.

## 14. Thực hành có hướng dẫn: thiết kế autoscale cho API

### 14.1. Dữ liệu giả lập

Một API trên App Service Plan Standard/Premium đủ điều kiện rule-based autoscale có telemetry sau:

| Thời điểm UTC | Instances | CPU trung bình | P95 latency | HTTP 5xx |
| --- | ---: | ---: | ---: | ---: |
| 08:00 | 2 | 35% | 180 ms | 0,1% |
| 09:00 | 2 | 78% | 520 ms | 1,2% |
| 09:15 | 3 | 61% | 340 ms | 0,5% |
| 09:30 | 4 | 48% | 220 ms | 0,2% |
| 12:00 | 4 | 21% | 190 ms | 0,1% |
| 12:40 | 2 | 39% | 200 ms | 0,1% |

Số liệu chỉ để diễn tập; không thể suy ra chính xác cách Azure xử lý rules chỉ từ sáu điểm đo.

### 14.2. Yêu cầu A — Chọn min/max và quy tắc

Thiết kế ban đầu:

~~~text
min instances: 2
default:       2
max:           6

Scale out: CPU average > 70% trong 10 phút, +1 instance
Scale in:  CPU average < 35% trong 20 phút, -1 instance
Cooldown: 10 phút sau scale out, 20 phút sau scale in
~~~

**Câu hỏi:** tại sao không dùng cùng một ngưỡng 60% cho scale out và scale in?

**Đáp án:** CPU dao động quanh 60% có thể khiến hệ thống tăng rồi giảm liên tục. Khoảng ngưỡng giúp giảm flapping, tuy vẫn cần quan sát dữ liệu thật.

### 14.3. Yêu cầu B — Đánh giá kết quả

- Sau tăng instances, CPU và latency giảm. Đây là tín hiệu tích cực nhưng chưa chứng minh causality hoàn toàn; cần đối chiếu cùng lượng request.
- Khi tải hạ, scale in dần để giảm chi phí nếu không ảnh hưởng SLO.
- Nếu p95 vẫn cao dù CPU thấp, điều tra database hoặc network dependency.
- Nếu 5xx tăng mỗi lần thêm worker, xem startup/health, connection pool và cấu hình app.

### 14.4. Yêu cầu C — Kiểm tra bằng CLI mà không thay đổi tài nguyên

Chạy các lệnh đọc:

~~~bash
az appservice plan show \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --query "{plan:name, sku:sku.name, instances:sku.capacity}" \
  --output json

az monitor autoscale list \
  --resource-group rg-web-lab \
  --output table

# Nếu đã có autoscale setting:
az monitor autoscale show \
  --resource-group rg-web-lab \
  --name autoscale-asp-web-lab \
  --output json
~~~

Ghi lại plan/tier, min/max/profile và các rules nếu tồn tại. Nếu không có autoscale setting, chỉ nêu rõ **chưa có autoscale theo Azure Monitor tại scope đang đọc**; kiểm tra liệu ứng dụng có dùng chế độ automatic scaling khác trước khi kết luận không có cơ chế tự động.

### 14.5. Yêu cầu D — Tình huống tải tăng trước giờ mở bán

Một cuộc bán vé bắt đầu 19:00, tải tăng trong 30 giây; rule CPU trung bình 10 phút có thể không kịp.

**Thiết kế đề xuất:** pre-scale theo lịch ở thời điểm trước 19:00 với min instances cao hơn, warm-up và kiểm thử; sau sự kiện giảm dần theo metrics/schedule. Kết hợp caching, queue và các biện pháp điều tiết hợp lệ để tránh dồn tải vào database.

### 14.6. Yêu cầu E — Giới hạn database

Mỗi instance có 60 DB connections tối đa và database chịu khoảng 300 connections theo đo thực tế.

\[
\text{Nếu 6 instances: }6\times60=360
\]

**Đáp án:** cần điều chỉnh connection pool, giới hạn concurrency, backend capacity hoặc min/max. Không dùng max=6 mà bỏ qua giới hạn downstream.

## 15. Checklist vận hành trước và sau khi scale

### Trước khi thay đổi

- Xác nhận đúng subscription, plan, tier và những Web Apps cùng plan.
- Xác định nguyên nhân nghẽn bằng CPU/memory/latency/error/dependency metrics.
- Kiểm tra quota/tier và số instances đang dùng.
- Xem ứng dụng có stateless/session store, upload storage dùng chung và idempotent jobs không.
- Chọn min/max, rules, cooldown hoặc lịch dựa trên tải và SLO.
- Ước tính instance-hours, database connections và chi phí.
- Có quyền được cấp, kế hoạch kiểm thử và rollback phù hợp.

### Sau khi thay đổi

- Xác nhận cấu hình/instance count được áp dụng và workers sẵn sàng.
- Kiểm tra health endpoint, login/session và request đại diện.
- Xem p95/p99 latency, 5xx, CPU/memory, response queue.
- Kiểm tra các Web Apps khác dùng chung plan và tải database.
- Theo dõi autoscale history, cảnh báo và mức chi phí.
- Ghi lại kết luận, thay đổi đã thực hiện và điều chỉnh autoscale nếu có căn cứ.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Scale up là thêm nhiều instances.” | Scale up đổi năng lực/tier/size; scale out đổi số instances. |
| “Autoscale tự nâng từ S1 lên Premium khi CPU cao.” | Azure Monitor autoscale thường thay **instance count**, không mặc định chuyển SKU. |
| “Scale out một Web App luôn độc lập với mọi app cùng plan.” | Plan thường chia sẻ compute; cần xem chế độ per-app/automatic scaling cụ thể. |
| “Có 10 instances thì chịu gấp 10 lưu lượng.” | Khả năng mở rộng còn phụ thuộc database, cache, lock, network và cấu trúc app. |
| “Có ARR affinity nên lưu session RAM là an toàn.” | Instance có thể recycle/scale in; cần trạng thái dùng chung. |
| “Scale in sẽ bảo toàn mọi tác vụ đang chạy.” | Background jobs và request dài cần thiết kế retry/queue/shutdown. |
| “Autoscale scale ngay khi CPU tăng một giây.” | Có cửa sổ metric, đánh giá rule, cooldown và thời gian khởi tạo. |
| “Scale up luôn không gián đoạn.” | Đổi SKU/worker có thể gây restart hoặc thay đổi capacity tạm thời. |
| “CPU thấp nghĩa là không thiếu tài nguyên.” | Có thể đang chờ DB, I/O, memory hoặc queue. |
| “Tăng max instances không có rủi ro.” | Có thể vượt ngân sách hoặc làm quá tải dependencies. |
| “Deployment slot là một plan/VM riêng.” | Slots thường chia sẻ plan compute và có thể tăng tải tổng. |
| “Application Insights không thấy request tức là hệ thống không lỗi.” | Có thể chưa bật instrumentation, sampling hoặc route/log khác. |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Khi nào nên ưu tiên scale up thay vì scale out?

**Đáp án:** Khi thiếu RAM/CPU trên mỗi instance, có nhu cầu tính năng tier cao hơn hoặc workload khó chia song song; vẫn cần kiểm chứng bottleneck thực tế.

**Câu 2.** Web App A và B cùng App Service Plan. Nếu scale out plan từ 2 lên 4 instances, chi phí và ứng dụng nào cần được kiểm tra?

**Đáp án:** Chi phí compute plan tăng theo instances; phải kiểm tra cả A và B vì cùng dùng plan và có thể cùng chịu thay đổi.

**Câu 3.** CPU giảm từ 80% xuống 45% sau scale out, nhưng p95 latency không giảm. Bạn điều tra gì?

**Đáp án:** Database, cache, network, external dependencies, locks và request queues. CPU plan thấp hơn chưa chứng minh SLO tốt hơn.

**Câu 4.** Vì sao không nên đặt scale out > 70% và scale in < 69% trên cùng cửa sổ ngắn?

**Đáp án:** Khoảng ngưỡng quá hẹp khiến dễ tăng/giảm liên tục theo biến động metric. Nên có hysteresis và cooldown được kiểm thử.

**Câu 5.** Một ứng dụng lưu session trong bộ nhớ worker. Tại sao dễ có lỗi khi scale out?

**Đáp án:** Các workers không tự có cùng session memory. Request có thể tới worker khác, instance restart hoặc scale in; cần session store dùng chung.

**Câu 6.** Azure Monitor autoscale và App Service automatic scaling có giống nhau không?

**Đáp án:** Không hoàn toàn. Azure Monitor autoscale theo metric/schedule và thường điều chỉnh capacity của plan; automatic scaling của App Service dùng cơ chế theo traffic/từng app khi được tier hỗ trợ.

**Câu 7.** Mỗi worker chịu 100 RPS ở SLO mong muốn. Để phục vụ 450 RPS, cần ít nhất bao nhiêu worker theo tính toán tuyến tính chưa có headroom?

**Đáp án:** `ceil(450/100) = 5`. Cần dự trù headroom và kiểm tra dependencies khi triển khai thật.

**Câu 8.** Autoscale được cấu hình maximum 6 instances và hiện đã ở 6, ứng dụng vẫn chậm. Nên làm gì?

**Đáp án:** Kiểm tra tier/quota, CPU/memory, app/dependency bottleneck; cân nhắc scale up, tối ưu code, chia workload hoặc thay max có kiểm soát.

**Câu 9.** Lưu file upload trong temporary local directory sẽ có vấn đề gì khi scale out?

**Đáp án:** File có thể không tồn tại trên worker khác và không có độ bền mong muốn. Nên lưu trong Blob Storage hoặc dịch vụ lưu trữ dùng chung phù hợp.

**Câu 10.** Tại sao autoscale theo lịch đôi khi hiệu quả hơn chỉ dựa vào metric?

**Đáp án:** Với peak biết trước, có thể tăng capacity và warm up trước khi request tăng, giảm độ trễ do đánh giá metrics và khởi tạo workers.

## Ghi nhớ

- **Scale up/down** thay năng lực mỗi worker hoặc tier; **scale out/in** thay số worker instances.
- **App Service Plan** là ranh giới quan trọng về compute và chi phí; nhiều Web Apps có thể chia sẻ một plan.
- **Azure Monitor autoscale** dùng metric, min/max, cooldown và schedule; **App Service automatic scaling** là cơ chế theo traffic khi tier hỗ trợ.
- Quy tắc autoscale hiệu quả phải dựa trên **SLO, bottleneck thật, thời gian warm-up và downstream capacity**.
- Ứng dụng muốn scale out ổn định cần **stateless state, session store dùng chung, queue/idempotency, health check và graceful shutdown**.
- Luôn kiểm tra **CPU, memory, request rate, p95/p99 latency, errors, instance count, database và chi phí** trước/sau thay đổi.
- Scale chỉ có ý nghĩa khi ứng dụng phục vụ người dùng tốt hơn trong giới hạn chi phí và độ tin cậy mong muốn.
