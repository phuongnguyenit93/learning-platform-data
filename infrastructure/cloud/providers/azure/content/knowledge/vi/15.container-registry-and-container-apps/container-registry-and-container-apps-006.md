# Azure Container Instances và workload container ngắn hạn

Trong hệ sinh thái Microsoft Azure, không phải workload nào cũng cần một máy ảo chạy 24/7 hoặc một cụm Kubernetes. Có những công việc chỉ thực hiện trong vài phút: đọc một lô dữ liệu, kết xuất báo cáo, chuyển đổi định dạng tệp, kiểm tra kết nối từ một mạng riêng hoặc chạy một script bảo trì đã được phê duyệt. Nếu đóng gói thành container, những công việc này có thể được chạy khi cần, ghi kết quả ra nơi lưu trữ bền vững rồi kết thúc.

**Azure Container Instances (ACI)** là dịch vụ chạy container theo yêu cầu mà không cần tự tạo và quản trị VM, container host hoặc Kubernetes cluster. Đơn vị triển khai quan trọng của ACI là **container group**: một hoặc nhiều container cùng chia sẻ một phần môi trường mạng, bộ lưu trữ gắn kèm và vòng đời theo cấu hình. ACI đặc biệt thuận tiện cho **workload ngắn hạn, chạy theo lô hoặc tác vụ thử nghiệm** khi nhu cầu điều phối chưa phức tạp.

Bài này thuộc chương **Container Registry và Container Apps** trong module **CLOUD_PROVIDERS_AZURE**. Người học đã có bối cảnh về subscription, resource group, Microsoft Entra ID, Azure networking, lưu trữ và quản lý chi phí; ở đây ta kết hợp các kiến thức đó để triển khai, giám sát, bảo vệ và dọn dẹp một tác vụ container thực tế.

> **Nguyên tắc cốt lõi:** Đối với job chạy một lần, phải phân biệt **container hoàn thành thành công** với **container vẫn cần phục vụ liên tục**. Cấu hình **restart policy** không phù hợp có thể khiến chương trình đã xong lại tự chạy, tiêu tốn tài nguyên hoặc tạo kết quả trùng lặp.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Giải thích ACI, container group, image, command, environment variables, CPU/memory requests và restart policy.
2. Quyết định khi nào dùng ACI thay vì Azure Container Apps Jobs, AKS Job/CronJob, Azure Batch hoặc VM.
3. Phân biệt ba chính sách **Always**, **OnFailure**, **Never**; đọc exit code và kết quả job.
4. Chạy một workload ngắn hạn bằng Azure CLI và một container group khai báo bằng Bicep.
5. Đóng gói một ứng dụng Java batch thành container image và đưa image tới Azure Container Registry (ACR).
6. Hiểu luồng kéo image từ private registry, quản lý secret và quyền truy cập.
7. Thiết kế network ingress/egress, VNet, lưu trữ bền vững và khả năng xử lý job lặp.
8. Lấy logs, kiểm tra trạng thái, chẩn đoán image pull failure, lỗi resource hoặc container exit bất thường.
9. Đánh giá CPU/memory, thời gian chạy, chi phí, lịch kích hoạt và dọn dẹp tài nguyên.
10. Thiết kế retry, idempotency, observability và runbook cho workload production.

## 2. Azure Container Instances giải quyết bài toán gì?

Để chạy một container trên VM thông thường, đội vận hành phải cung cấp OS, container runtime, network, patching, monitoring và cơ chế dọn dẹp. Với ACI, bạn yêu cầu Azure tạo **container group** từ image và cấu hình đã chỉ định; nền tảng chịu trách nhiệm cấp hạ tầng chạy container theo mô hình dịch vụ.

Một chu kỳ đơn giản:

~~~mermaid
flowchart LR
    T["Người dùng / scheduler / event"] --> A["Tạo container group ACI"]
    I["Container image trong registry"] -->|"Pull image"| A
    A --> R["Chạy command hoặc entrypoint"]
    R --> O["Ghi kết quả vào Azure Storage / DB"]
    R --> L["Phát logs, exit code, metrics"]
    O --> E["Job kết thúc; kiểm tra kết quả"]
    L --> E
    E --> C["Giữ metadata khi cần rồi xóa group lab"]
~~~

ACI giúp giảm thao tác quản trị host, nhưng **không thay đội phát triển** quyết định thời điểm chạy, cách retry, lịch kích hoạt, quyền của container hoặc tính nhất quán của dữ liệu đầu ra.

### 2.1. Ví dụ nên cân nhắc ACI

| Tình huống | Cách sử dụng ACI | Điều cần thiết kế |
|---|---|---|
| Chuyển đổi ảnh theo yêu cầu | Tạo container, đọc blob đầu vào, ghi blob đã xử lý rồi exit | Idempotency, kiểm tra đầu ra, retry |
| Sinh báo cáo cuối ngày | Scheduler gọi API tạo container group, Java job chạy xong | Lịch, quyền Azure, kiểm tra exit code |
| Thử nghiệm Java worker | Chạy image phát triển trong vài phút | Giới hạn CPU/memory và tự dọn lab |
| Chạy script vận hành được phép | Khởi tạo một group tạm trong VNet phù hợp | Least privilege, audit, không nhúng secret |
| Xử lý một lô dữ liệu nhỏ | Một container đọc input và ghi Azure Storage | Dữ liệu lớn, timeout, network và cost |
| Network diagnostics từ mạng riêng | Chạy image được duyệt trong subnet riêng | VNet permissions, DNS, logging |

### 2.2. Khi ACI không phải lựa chọn đầu tiên

ACI thường **không phải lựa chọn tối ưu** nếu:

- Có hàng nghìn jobs liên tục, yêu cầu hàng đợi, retry policy, cron và autoscaling tích hợp ở cấp workload.
- Ứng dụng có nhiều microservice dài hạn, cần service discovery, rollout, autoscaling và quản trị traffic phức tạp.
- Cần tính năng Kubernetes như controller, admission policies, Job/CronJob hoặc hệ sinh thái operators.
- Batch xử lý tính toán quy mô lớn cần hàng nghìn task, queue/scheduling và điều phối chuyên dụng.
- Cần địa chỉ IP ổn định, ingress HTTPS, TLS certificate và routing ứng dụng đầy đủ.
- Workload đòi hỏi tài nguyên phần cứng, thời lượng, OS/architecture hoặc network capability ngoài giới hạn hỗ trợ của ACI.

Trong những trường hợp đó, hãy so sánh với **Azure Container Apps (đặc biệt là Jobs)**, **Azure Kubernetes Service (AKS)**, **Azure Batch**, **Azure Functions** hoặc dịch vụ web được quản lý tương ứng.

## 3. Phân biệt ACI với Azure Container Apps Jobs và các dịch vụ khác

| Dịch vụ | Đơn vị chạy | Đặc tính nổi bật | Ví dụ phù hợp |
|---|---|---|---|
| **Azure Container Instances** | Container group | Tạo container theo yêu cầu, không tự quản cluster; vòng đời, restart policy và tài nguyên theo group | Một batch job được hệ thống ngoài kích hoạt |
| **Azure Container Apps Jobs** | Job execution | Nền tảng hỗ trợ mô hình chạy **manual**, **scheduled** hoặc **event-driven** và khả năng điều phối thực thi theo tính năng | Job định kỳ hoặc trigger từ queue, cần retry/scale theo cấu hình |
| **Azure Container Apps applications** | Revision/replica | Chạy dịch vụ container với ingress, scaling, revision và quản trị môi trường | HTTP API, background worker dài hạn |
| **AKS Jobs/CronJobs** | Kubernetes Job/Pod | Điều phối K8s, scheduling, policy và quản lý cluster | Tổ chức đã chuẩn hóa Kubernetes |
| **Azure Batch** | Pools/tasks | Điều phối batch tính toán, tác vụ lớn và phân phối tài nguyên | HPC hoặc xử lý song song nhiều task |
| **Azure Functions** | Function invocation | Event trigger, managed execution, nhiều binding theo runtime | Logic ngắn theo sự kiện, không cần tự vận hành image khi không bắt buộc |
| **Azure VM** | VM/process | Toàn quyền điều khiển OS và runtime | Workload cần mức tùy biến host cao |

**Không nhầm ACI với Container Apps Jobs** chỉ vì cả hai chạy container ngắn hạn. Với ACI, việc tạo group theo lịch, quyết định retry ở cấp nghiệp vụ, gom trạng thái nhiều lần chạy thường phải do **hệ thống điều phối bên ngoài** đảm nhiệm.

Các tính năng, vùng hỗ trợ, quota và bảng giá của các dịch vụ có thể thay đổi. Chọn dựa trên yêu cầu thực tế chứ không chỉ tên sản phẩm.

## 4. Thành phần kiến trúc của ACI

### 4.1. Container image

Image là gói bất biến tương đối gồm chương trình, dependency, runtime, filesystem layer và metadata khởi chạy. Ví dụ:

~~~text
myregistry.azurecr.io/orders/report-worker:1.2.0
    ├── Base image (JRE)
    ├── Java classes / dependency
    ├── ENTRYPOINT
    └── Cấu hình mặc định không nhạy cảm
~~~

**Không coi image tag là bằng chứng duy nhất về nội dung**: tag có thể bị ghi đè nếu registry cho phép. Production nên version hóa rõ ràng, quét lỗ hổng, kiểm soát quyền push và có thể triển khai theo image digest để tăng khả năng tái lập.

### 4.2. Container group

**Container group** là đơn vị triển khai, cấp tài nguyên và vòng đời trong ACI. Một group có thể chứa một container hoặc nhiều container phù hợp với giới hạn của dịch vụ.

Các container trong cùng group chia sẻ một số thành phần như network namespace/địa chỉ IP của group và có thể giao tiếp qua **localhost** theo mô hình hỗ trợ. Điều đó thuận tiện cho sidecar logging/proxy, nhưng kéo theo ràng buộc về lifecycle và tài nguyên.

~~~mermaid
flowchart TB
    subgraph Group["Container group: report-job"]
      J["Container Java Worker<br/>1 vCPU, 1.5 GiB (ví dụ)"]
      S["Container phụ (tùy chọn)<br/>logging/proxy"]
      J <-->|"localhost / shared network"| S
    end
    CR["ACR / Registry"] -->|"Image pull"| Group
    Group -->|"HTTPS"| ST["Azure Blob Storage"]
    Group -->|"Logs / telemetry"| MON["Azure Monitor"]
~~~

Đối với **job chạy một lần**, nên bắt đầu với **một container** để đơn giản hóa quyết định khi nào cả group hoàn thành. Nhiều container có sidecar chạy mãi có thể khiến group tiếp tục hoạt động dù container chính đã xong.

### 4.3. Khai báo container và resources

Một cấu hình triển khai thường gồm:

- **Location**: Azure region được hỗ trợ.
- **OS type**: Linux hoặc Windows khi dịch vụ/feature hỗ trợ.
- **Image**: tên image từ Docker Hub, MCR hoặc private registry.
- **Resources**: số vCPU và bộ nhớ được yêu cầu theo điều kiện dịch vụ.
- **Command/entrypoint**: chương trình sẽ thực thi.
- **Restart policy**: Always, OnFailure hoặc Never.
- **Environment variables**: cấu hình không nhạy cảm và secrets theo phương pháp hỗ trợ.
- **Networking**: IP public/private, port, DNS hoặc subnet nếu được cấu hình.
- **Volumes**: Azure Files hoặc loại volume được hỗ trợ khi cần dữ liệu bên ngoài lifecycle của container.
- **Identity/registry credentials**: quyền kéo image và truy cập dịch vụ.
- **Tags**: owner, environment, workload, run ID để quản lý chi phí/audit.

Không phải mọi tổ hợp tính năng đều được hỗ trợ ở mọi region và OS. Ví dụ Windows container, networking, managed identity, volume mount và resource shape có thể có các giới hạn riêng.

## 5. Ba restart policy và ý nghĩa đối với job

Đây là quyết định quan trọng nhất khi dùng ACI cho tác vụ ngắn hạn.

| Restart policy | Khi process kết thúc với exit code 0 | Khi kết thúc với exit code khác 0 | Mục đích |
|---|---|---|---|
| **Always** | Có thể khởi động lại | Có thể khởi động lại | Dịch vụ/container cần tiếp tục chạy, đây là lựa chọn mặc định thường gặp |
| **OnFailure** | Không tự restart vì kết thúc thành công | Thử restart theo hành vi dịch vụ | Công việc cần chạy đến khi hoàn thành thành công, chấp nhận retry |
| **Never** | Không restart | Không restart | Tác vụ một lần, cần giữ exit code cuối để hệ thống ngoài đánh giá |

### 5.1. Always: cẩn thận với job đã hoàn thành

Nếu Java worker xử lý xong và gọi **System.exit(0)**, chọn **Always** có thể khiến ACI khởi động container thêm lần nữa. Hậu quả:

- File báo cáo bị tạo trùng hoặc ghi đè.
- Email/thông báo được gửi lặp.
- Phát sinh thêm request tới database.
- Workload tiếp tục tiêu thụ compute và memory dù công việc đã xong.

**Không dùng Always cho batch chạy một lần** nếu không có lý do rõ ràng và cơ chế kết thúc bên ngoài phù hợp.

### 5.2. OnFailure: retry không thay thế idempotency

Khi process exit với mã khác 0, OnFailure có thể chạy lại. Tuy nhiên, job có thể đã hoàn thành một phần trước khi lỗi. Ví dụ:

1. Đã ghi report vào Blob Storage.
2. Chưa cập nhật trạng thái vào database.
3. Container crash.
4. Lần retry chạy lại và tạo bản report thứ hai.

Vì vậy, dùng **idempotency key**, marker hoàn tất, cơ chế upsert hoặc transaction phù hợp. Không coi retry là vô hại.

**Không giả định** chính sách OnFailure của ACI cho phép đặt đầy đủ retry count, exponential backoff hay dead-letter policy như một hệ thống orchestration. Nếu cần chính sách retry phức tạp, dùng orchestrator ngoài hoặc dịch vụ jobs chuyên dụng.

### 5.3. Never: thực thi một lần và kiểm tra kết quả

Với **Never**, một container kết thúc thì không tự được chạy lại vì chính sách restart. Kết quả thành công hay thất bại phải được hệ thống điều phối đánh giá qua:

- Trạng thái container group.
- **Container exit code**.
- Log ứng dụng.
- Bằng chứng đầu ra trong Storage/Database.
- Thời gian thực thi và các cảnh báo.

Với job có yêu cầu **mỗi lần kích hoạt tạo một execution độc lập**, cách rõ ràng là dùng một container group mới theo **run ID** duy nhất hoặc một cơ chế khởi tạo được tổ chức hỗ trợ. Không chỉ dựa vào hành vi restart của một group cũ để mô phỏng lịch hàng ngày.

## 6. Lifecycle của container group khác lifecycle của process

Một container có thể ở trạng thái chờ, kéo image, chạy hoặc đã kết thúc. Group là thực thể quản lý bên ngoài và có trạng thái tổng hợp.

~~~mermaid
flowchart LR
    A["Create request"] --> B["Pending / Pulling image"]
    B --> C["Running"]
    C --> D{"Process exit code?"}
    D -->|"0"| E["Succeeded / terminated"]
    D -->|"Khác 0"| F["Failed / terminated"]
    F -. "OnFailure có thể restart" .-> C
    E -. "Always có thể restart" .-> C
~~~

Tùy API và thời điểm, bạn có thể thấy **Pending**, **Running**, **Succeeded**, **Failed** hoặc những trạng thái của container như **Waiting**, **Running**, **Terminated**.

### 6.1. Exit code là tín hiệu kỹ thuật, không phải kết quả nghiệp vụ đầy đủ

| Exit code | Cách hiểu phổ biến | Giới hạn |
|---|---|---|
| **0** | Process kết thúc thành công theo quy ước ứng dụng | Có thể job vẫn xuất sai dữ liệu nếu code không kiểm tra |
| **Khác 0** | Có lỗi theo quy ước ứng dụng | Cần đọc log, error type và trạng thái đầu ra |
| Không có exit code | Có thể container chưa kết thúc hoặc chưa chạy được | Kiểm tra trạng thái group và event |

Hãy thiết kế chương trình batch trả **exit code khác 0** khi thao tác nghiệp vụ không hoàn tất. Đồng thời tạo một **kết quả có thể kiểm chứng** trong hệ thống ngoài container.

### 6.2. Khi nào phát sinh phí?

ACI thường tính phí theo tài nguyên CPU/memory được yêu cầu và thời gian triển khai/chạy đủ điều kiện theo bảng giá dịch vụ, với quy tắc metering và mức tối thiểu hiện hành. Thời gian khởi động, image pull và trạng thái container/group là những chi tiết cần đối chiếu bảng giá hiện tại.

Điều quan trọng về vận hành:

- Container/group còn **Running** có thể tiếp tục phát sinh phí.
- Job kết thúc theo restart policy phù hợp có thể ngừng tiêu thụ compute cho lần chạy đó, nhưng **resource record** có thể còn tồn tại cho đến khi được xóa.
- Azure Files, Azure Container Registry, logs, IP/network resources hoặc các dịch vụ phụ trợ có thể tiếp tục tính phí.
- Không lấy việc process chỉ có 10 giây CPU làm bằng chứng tổng thời gian được tính phí đúng 10 giây.

Trước khi triển khai production, dùng bảng giá ACI, Azure Pricing Calculator và dữ liệu Cost Management để dự toán theo cấu hình thực tế.

## 7. Thực hành A: chạy một job ngắn hạn bằng Azure CLI

Trong bài lab, ta chạy một container đơn giản in ra log, chờ vài giây, rồi kết thúc thành công. **Không cần mở cổng hoặc public IP** vì đây không phải dịch vụ HTTP.

### 7.1. Điều kiện trước khi bắt đầu

- Có subscription Azure và quyền tạo resource group/container group.
- Đã cài Azure CLI hoặc dùng Azure Cloud Shell.
- Region đã chọn hỗ trợ ACI với cấu hình CPU/memory minh họa.
- Môi trường có thể pull image từ public registry và không bị chặn bởi chính sách mạng.
- Có ngân sách lab, đặt owner và quy trình xóa resource sau thực hành.

**Lưu ý:** ví dụ sử dụng **busybox:1.36** từ một registry công cộng. Với môi trường doanh nghiệp, nên pin image digest và dùng image được tổ chức cho phép, quét lỗ hổng; public registry có thể giới hạn tốc độ hoặc thay đổi cách phân phối.

### 7.2. Tạo resource group

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-aci-batch-lab"
REGION="southeastasia"

az group create \
  --name "$RG" \
  --location "$REGION"
~~~

Resource group giúp tập hợp tài nguyên lab theo vòng đời, nhưng **không tự đặt giới hạn chi phí**. Có thể tạo budget và cảnh báo theo scope nếu có quyền.

### 7.3. Tạo container group chạy một lần

~~~bash
CG="aci-report-demo"

az container create \
  --resource-group "$RG" \
  --name "$CG" \
  --location "$REGION" \
  --image "busybox:1.36" \
  --os-type Linux \
  --cpu 1 \
  --memory 1.5 \
  --restart-policy Never \
  --command-line "/bin/sh -c 'echo job-start; date; sleep 8; echo job-completed'"
~~~

Giải thích:

- **--image** chọn image có shell và lệnh cơ bản.
- **--cpu 1**, **--memory 1.5** là cấu hình minh họa; đây là **requested capacity**, phải kiểm tra giới hạn SKU/region.
- **--restart-policy Never** giúp container chỉ thực thi một lần theo chính sách.
- **--command-line** ghi đè command mặc định của image; cấu hình command có thể cần được thử để phù hợp cách CLI xử lý dấu nháy.
- **Không có --ports, --ip-address Public** vì worker không phục vụ kết nối từ Internet.

Lệnh gửi yêu cầu tạo tài nguyên thật và có thể phát sinh phí. Chỉ chạy trong subscription lab được phê duyệt. Nếu image pull hoặc container provisioning lỗi, đọc thông báo chi tiết thay vì đổi sang quyền registry rộng hơn.

### 7.4. Theo dõi trạng thái

~~~bash
az container show \
  --resource-group "$RG" \
  --name "$CG" \
  --query "{name:name,groupState:instanceView.state,containers:containers[].{name:name,state:instanceView.currentState.state,exitCode:instanceView.currentState.exitCode}}" \
  --output json
~~~

Nếu job vẫn Running, xem lại sau một khoảng thời gian phù hợp. Khi container đã kết thúc, kiểm tra cả **groupState**, **container state** và **exitCode**.

Một kết quả **minh họa**:

~~~json
{
  "name": "aci-report-demo",
  "groupState": "Succeeded",
  "containers": [
    {
      "name": "aci-report-demo",
      "state": "Terminated",
      "exitCode": 0
    }
  ]
}
~~~

Tên container thực tế do cấu hình triển khai xác định và có thể khác. Ví dụ trên **không phải output đã chạy**. Với API/CLI khác phiên bản, tên trường trạng thái có thể thay đổi; đọc JSON đầy đủ nếu truy vấn chọn lọc trả giá trị rỗng.

### 7.5. Đọc stdout/stderr

~~~bash
az container logs \
  --resource-group "$RG" \
  --name "$CG"
~~~

Kỳ vọng trong lab thấy các dòng tương tự:

~~~text
job-start
...
job-completed
~~~

Logs giúp xem chương trình đã đi qua bước nào, nhưng **không đủ** nếu job có nhiều bước ghi dữ liệu ra ngoài. Kết hợp exit code với kiểm tra Blob/Database/công việc đầu ra.

### 7.6. Khi cần chạy lại

Không nên đặt một group đã hoàn thành thành “scheduler”. Trong quy trình batch chuẩn, mỗi lần chạy có thể dùng **run ID** mới:

~~~text
aci-report-20261120-001
aci-report-20261120-002
~~~

Hãy bảo đảm tên hợp lệ theo ACI, không trùng và không tiết lộ dữ liệu nhạy cảm. Orchestrator cần ngăn hai lần kích hoạt cùng một job vô tình ghi đè nhau.

### 7.7. Dọn dẹp group

Sau khi lưu log/bằng chứng đầu ra cần thiết:

~~~bash
az container delete \
  --resource-group "$RG" \
  --name "$CG" \
  --yes
~~~

Xóa container group **không tự xóa** Azure Storage, ACR hoặc Log Analytics workspace khác mà nó dùng. Chỉ dọn những tài nguyên thuộc lab đã được owner xác nhận.

## 8. Thực hành B: chạy một container HTTP để phân biệt job và service

Một container trả HTTP liên tục có vòng đời khác worker chỉ in log rồi kết thúc. Ví dụ minh họa bằng image web mẫu có sẵn trên Microsoft Container Registry:

~~~bash
WEB_CG="aci-web-demo"
DNS_LABEL="<unique-valid-dns-label>"

az container create \
  --resource-group "$RG" \
  --name "$WEB_CG" \
  --location "$REGION" \
  --image "mcr.microsoft.com/azuredocs/aci-helloworld" \
  --cpu 1 \
  --memory 1.5 \
  --ip-address Public \
  --ports 80 \
  --dns-name-label "$DNS_LABEL" \
  --restart-policy Always
~~~

Trong tình huống này:

- Container **cần tiếp tục chạy** để phục vụ HTTP.
- **Always** phù hợp hơn Never khi muốn process được khởi động lại theo chính sách container group.
- Public IP/DNS đưa ứng dụng lab ra Internet; **không** dùng cấu hình demo HTTP port 80 cho dữ liệu nhạy cảm hoặc sản phẩm production.
- Nếu yêu cầu TLS/WAF/custom domain/HA, cần kiến trúc ingress được quản lý và tính năng hỗ trợ phù hợp.

Kiểm tra endpoint từ thuộc tính thực tế:

~~~bash
az container show \
  --resource-group "$RG" \
  --name "$WEB_CG" \
  --query "{state:instanceView.state,ip:ipAddress.ip,fqdn:ipAddress.fqdn,ports:ipAddress.ports}" \
  --output json
~~~

Khi đã xác minh FQDN, kiểm tra HTTP theo quy tắc lab:

~~~bash
curl -i "http://<actual-fqdn>/"
~~~

Đừng coi FQDN hoặc địa chỉ public IP này là endpoint vĩnh viễn. Khi group được xóa/tạo lại, cần kiểm tra thay đổi IP, tên, DNS và cách dịch vụ hỗ trợ.

Sau lab:

~~~bash
az container delete \
  --resource-group "$RG" \
  --name "$WEB_CG" \
  --yes
~~~

**So sánh:** Web service hướng tới **Running ổn định**; batch job hướng tới **Succeeded và exit code 0**. Cùng một nền tảng ACI nhưng restart policy, giám sát và tiêu chí hoàn tất khác nhau.

## 9. Khai báo ACI bằng Bicep

Với Infrastructure as Code, container group có thể được mô tả dưới dạng tài nguyên quản lý thay vì được tạo thủ công nhiều lần. Ví dụ sau tạo **một job Linux chạy một lần**, không có public IP.

~~~bicep
@description('Tên của container group job')
param containerGroupName string = 'aci-batch-once'

@description('Region triển khai')
param location string = resourceGroup().location

@description('Image đã được phê duyệt cho lab')
param image string = 'busybox:1.36'

resource group 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = {
  name: containerGroupName
  location: location
  properties: {
    osType: 'Linux'
    restartPolicy: 'Never'
    containers: [
      {
        name: 'job'
        properties: {
          image: image
          command: [
            '/bin/sh'
            '-c'
            'echo start; sleep 8; echo done'
          ]
          resources: {
            requests: {
              cpu: 1
              memoryInGB: 1.5
            }
          }
        }
      }
    ]
  }
}

output containerGroupId string = group.id
~~~

Lưu nội dung thành một file Bicep trong dự án IaC **nếu bạn thực sự thực hành**. Bài học này không tạo file ngoài hai tài liệu được giao.

Xem trước và triển khai ở resource group lab:

~~~bash
az deployment group what-if \
  --resource-group "$RG" \
  --template-file aci-batch.bicep \
  --parameters containerGroupName="aci-batch-bicep-demo"

az deployment group create \
  --resource-group "$RG" \
  --template-file aci-batch.bicep \
  --parameters containerGroupName="aci-batch-bicep-demo"
~~~

**Lưu ý quan trọng về idempotent deployment:** IaC xác định trạng thái tài nguyên mong muốn, **không phải cơ chế schedule job**. Không xem việc chạy lại deployment đối với cùng tên group là một cam kết tạo **một execution mới** với lịch sử độc lập. Nếu cần nhiều lần chạy có dấu vết riêng, hãy thiết kế run ID và lifecycle rõ ràng.

Khi tạo một group có nhiều container, cách tính trạng thái kết thúc và chi phí phụ thuộc từng container trong group. Với job ngắn hạn, không nên tự thêm một sidecar chạy vô hạn.

## 10. Đóng gói một Java batch worker

Trong module cloud Azure, một ví dụ phù hợp là **Java worker tạo báo cáo**, chạy xong và thoát. Điểm khác ứng dụng Java web là worker **không cần mở HTTP port** và không nên nằm ở trạng thái Running mãi.

### 10.1. Source Java minh họa

Tập tin **BatchReport.java**:

~~~java
import java.time.Instant;

public final class BatchReport {
    public static void main(String[] args) {
        String jobId = System.getenv()
                .getOrDefault("JOB_ID", "local-demo");

        try {
            System.out.println("START job=" + jobId
                    + " at=" + Instant.now());

            // Trong hệ thống thật: đọc dữ liệu từ Azure Storage
            // hoặc DB, xử lý, rồi ghi output ra lưu trữ bền vững.
            long recordsProcessed = 10;

            System.out.println("recordsProcessed=" + recordsProcessed);
            System.out.println("SUCCESS job=" + jobId
                    + " at=" + Instant.now());

            // Exit code 0 nghĩa process hoàn thành theo quy ước.
        } catch (Exception error) {
            System.err.println("FAILED job=" + jobId
                    + " error=" + error.getMessage());
            System.exit(1);
        }
    }
}
~~~

Ví dụ trên đơn giản nhằm thể hiện **lifecycle và exit code**, không phải một pipeline xử lý dữ liệu production. Ở production cần kiểm tra nguồn dữ liệu, tính đúng đắn của báo cáo, retry và phương pháp lưu output.

### 10.2. Dockerfile nhiều giai đoạn

Đặt **Dockerfile** ở thư mục gốc dự án:

~~~dockerfile
# Giai đoạn build: dùng JDK biên dịch
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY BatchReport.java .
RUN javac -d /out BatchReport.java

# Giai đoạn chạy: chỉ cần JRE
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /out /app
ENTRYPOINT ["java", "-cp", "/app", "BatchReport"]
~~~

Với một image được sử dụng nhiều lần, hãy **pin phiên bản hoặc digest của base image** theo chính sách và rebuild định kỳ để nhận bản vá. Image Java thực tế có thể cần dependency, toolchain, chứng chỉ CA, timezone, locale và xử lý tín hiệu shutdown.

### 10.3. Build/test local

~~~bash
docker build -t orders-report:1.0.0 .

docker run --rm \
  -e JOB_ID="local-001" \
  orders-report:1.0.0

# Xem exit code ngay sau khi docker run nếu cần
echo $?
~~~

Nếu chương trình kết thúc thành công, Docker process trả exit code **0** và container được dọn bởi **--rm**. Nếu cần kiểm thử retry, hãy tạo test scenario được kiểm soát dẫn đến exit code khác 0.

### 10.4. Dữ liệu đầu ra không nên chỉ nằm trong filesystem container

Filesystem ghi được của container thường mang tính **tạm thời** đối với lifecycle của ACI. Khi container dừng, bị xóa, tái tạo hay chạy trên host khác, không được dựa vào dữ liệu chỉ nằm trong writable layer để làm kết quả bền vững.

Các cách lưu output thường gặp:

- **Azure Blob Storage**: file báo cáo, JSON, CSV, PDF hoặc artifact.
- **Azure Files**: file share khi chương trình cần filesystem semantics và dịch vụ hỗ trợ.
- **Azure SQL Database / Azure Cosmos DB**: trạng thái nghiệp vụ có schema và consistency phù hợp.
- **Queue/Event**: thông báo một kết quả đã xử lý xong để workflow tiếp theo thực hiện.

Ưu tiên giao thức ứng dụng và SDK để ghi output có **transaction/checkpoint/idempotency**. Tránh dựa vào một lần ghi file local rồi coi đã hoàn tất job.

## 11. Đưa image lên Azure Container Registry (ACR)

ACI có thể kéo image từ public registry hoặc private ACR. Với production, ACR giúp tổ chức quản lý image, quyền truy cập, tên/digest, retention và các công cụ bảo mật theo chính sách.

### 11.1. Luồng image supply chain

~~~mermaid
flowchart LR
    DEV["Git source"] --> CI["CI build + test + scan"]
    CI --> IMG["Container image có version/digest"]
    IMG --> ACR["Azure Container Registry"]
    ACR -->|"Pull đúng quyền"| ACI["ACI container group"]
    ACI --> OUT["Azure Storage / Database"]
~~~

### 11.2. Ví dụ tạo ACR lab và push image

Các lệnh dưới đây **chỉ để minh họa**, cần quyền phù hợp, tên registry duy nhất và xác nhận chi phí trước khi chạy.

~~~bash
ACR_NAME="<globally-unique-acr-name>"
IMAGE_NAME="orders-report"
IMAGE_TAG="1.0.0"

az acr create \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --location "$REGION"

# Yêu cầu Docker engine hoặc môi trường build phù hợp
az acr login --name "$ACR_NAME"

docker tag \
  orders-report:1.0.0 \
  "$ACR_NAME.azurecr.io/$IMAGE_NAME:$IMAGE_TAG"

docker push \
  "$ACR_NAME.azurecr.io/$IMAGE_NAME:$IMAGE_TAG"
~~~

Sau push, xác minh repository/tag và nếu có thể lưu **image digest**:

~~~bash
az acr repository show-tags \
  --name "$ACR_NAME" \
  --repository "$IMAGE_NAME" \
  --output table
~~~

Không bật **admin user** rộng quyền chỉ để nhanh chóng chạy lab trên production. Với CI/CD, dùng danh tính đã cấp quyền push và cơ chế đăng nhập phù hợp.

### 11.3. ACI kéo private image

Để ACI kéo private image, cần **cơ chế xác thực registry**:

- Ưu tiên **managed identity và quyền AcrPull** ở phạm vi phù hợp **nếu** tổ hợp ACI, region, registry/network được sử dụng hỗ trợ cơ chế này.
- Một số quy trình dùng registry username/password hoặc token; đây là credential cần bảo vệ, rotate và không ghi vào CLI history/repository.
- Nếu registry dùng private endpoint, phải xác minh đường mạng, DNS, tính năng ACI private networking và yêu cầu image pull được hỗ trợ.
- Kiểm tra rằng image tag/digest tồn tại và architecture/OS image tương thích với container group.

Không đưa password ACR vào ví dụ lệnh command line theo dạng **--registry-password plaintext**. Hãy theo hướng dẫn ACI + ACR hiện hành cho cơ chế triển khai được tổ chức lựa chọn và bảo đảm credential không bị rò.

## 12. Environment variables, secrets và managed identity

Một Java worker thường cần các giá trị như:

~~~text
JOB_ID=report-20261120-001
INPUT_CONTAINER=orders
OUTPUT_CONTAINER=reports
LOG_LEVEL=INFO
~~~

Các giá trị trên không phải secret. Nếu dùng CLI, có thể cấu hình:

~~~bash
az container create \
  --resource-group "$RG" \
  --name "aci-env-demo" \
  --location "$REGION" \
  --image "busybox:1.36" \
  --cpu 1 \
  --memory 1.5 \
  --restart-policy Never \
  --environment-variables JOB_ID=lab-001 LOG_LEVEL=INFO \
  --command-line "/bin/sh -c 'echo JOB_ID=$JOB_ID; echo done'"
~~~

**Chú ý:** shell có thể expand **$JOB_ID** ở máy gọi CLI trước khi command được truyền đi, tùy cách quoting. Khi muốn in biến môi trường **bên trong container**, cần escape/quote đúng theo shell và tool đang dùng. Để tránh nhầm lẫn, cũng có thể đặt command và env trong YAML/Bicep rồi kiểm tra qua logs.

### 12.1. Không đưa secret vào môi trường kiểu plain text tùy tiện

- Không nhúng password/token vào source, Dockerfile, image layer, Git hoặc command history.
- Dùng **secure environment variables** hoặc secret reference theo cơ chế triển khai được ACI hỗ trợ khi thật sự cần.
- Tốt hơn, với các dịch vụ Azure hỗ trợ Azure AD/Entra authentication, dùng **managed identity** của container group và Azure SDK.
- Cấp quyền tối thiểu như quyền đọc đúng Blob container hoặc ghi đúng đích theo khả năng phân quyền thực tế.
- Xác nhận identity được **gán vào container group** và role assignment có hiệu lực; chỉ tạo identity không tự cấp quyền dữ liệu.
- Không ghi giá trị secret vào stdout/stderr dù container chỉ chạy ngắn hạn.

### 12.2. Ví dụ Java đọc cấu hình

~~~java
String jobId = System.getenv("JOB_ID");
String inputContainer = System.getenv("INPUT_CONTAINER");

if (jobId == null || jobId.isBlank()) {
    throw new IllegalArgumentException("Missing JOB_ID");
}
~~~

Khi cần kết nối Azure Storage/Key Vault, sử dụng Azure SDK với cơ chế credential thích hợp. Việc tạo một token trong container phải căn cứ vào managed identity/runtime được hỗ trợ; đừng mặc định mọi identity endpoint giống nhau giữa ACI, App Service và VM.

### 12.3. Phân quyền không chỉ là image pull

Hai loại quyền độc lập:

1. **Image pull**: cho phép runtime lấy image từ registry.
2. **Data plane/workload access**: cho phép Java worker đọc Blob, ghi bảng dữ liệu hoặc truy cập secret.

Có image pull thành công không có nghĩa ứng dụng đã được cấp quyền Azure Storage; ngược lại, một managed identity có quyền Blob không tự có quyền kéo mọi private image.

## 13. Mạng: public IP, VNet và outbound

### 13.1. Batch job không cần public inbound

Với worker chạy một lần, thường chỉ cần **outbound HTTPS** đến Azure Storage hoặc API ngoài. Không nên cấp public IP/port cho container không có endpoint cần được truy cập từ client.

Khi dùng public networking, vẫn cần đánh giá:

- Destination có cho phép outbound IP của ACI không.
- DNS resolution, TLS và firewall ở dịch vụ đích.
- Khả năng thay đổi egress IP, rate limit và quota.
- Rủi ro để image hoặc endpoint có quyền quá rộng.

**Không phụ thuộc vào một outbound IP bất biến** của ACI nếu dịch vụ không cam kết. Nếu phải có egress ổn định, thiết kế network riêng với NAT Gateway hoặc giải pháp phù hợp theo khả năng hỗ trợ.

### 13.2. ACI trong VNet

Một container group có thể được triển khai vào subnet của Azure Virtual Network theo điều kiện hỗ trợ. Khi đó:

- Cần subnet phù hợp, thường có yêu cầu **delegation cho Microsoft.ContainerInstance/containerGroups**.
- Cần kiểm tra IP plan, NSG, route table, DNS và các dịch vụ hỗ trợ cho ACI trong VNet.
- ACI VNet deployment sử dụng private networking; **không tự tạo public IP trực tiếp cho group nằm trong VNet** theo mô hình hỗ trợ thông dụng.
- Nếu cần public ingress, phải thiết kế ingress gateway/proxy/load balancing được hỗ trợ, không tự xem container group là Application Gateway.
- Các yêu cầu outbound/NAT và image pull cần được kiểm chứng cho region, subnet và loại registry.
- Các nhóm chia sẻ subnet phải được kiểm soát quyền, quota và địa chỉ IP.

Sơ đồ:

~~~mermaid
flowchart LR
    T["Event / scheduler có quyền"] --> M["Azure control plane"]
    M --> ACI["ACI group trong subnet riêng"]
    ACI -->|"Private IP / TLS"| DB["Private Endpoint của DB hoặc Storage"]
    ACI -->|"Qua NAT / firewall nếu cần"| API["External API"]
    DNS["Private DNS / custom DNS"] -. "Phân giải tên" .-> ACI
~~~

### 13.3. Điều cần hiểu về subnet

Tạo VNet không đủ để group chạy trong mạng riêng. Phải:

1. Tạo hoặc chọn subnet có address space phù hợp.
2. Kiểm tra delegation theo ACI.
3. Kiểm tra điều kiện vùng triển khai và tính năng ACI networking.
4. Tạo group với cấu hình subnet/resource ID tương ứng.
5. Xác nhận DNS và route từ group tới dependency.
6. Thử kết nối theo port thực tế (ví dụ HTTPS/443) và xác minh response.
7. Theo dõi network egress, firewall logs và tài nguyên NAT nếu có.

**Không mở NSG inbound Any/Any** để giải quyết một lỗi DNS hoặc image pull. Phải xác định chính xác traffic bị chặn tại lớp nào.

## 14. Lưu trữ bền vững: Azure Files, Blob Storage và lifecycle

Container group không phải máy lưu trữ dữ liệu vĩnh viễn. Nếu job tạo file quan trọng, phải đảm bảo file nằm ở hệ thống bền vững trước khi process exit 0.

### 14.1. Ba mô hình lưu dữ liệu

| Nhu cầu | Cách tiếp cận | Trade-off |
|---|---|---|
| File tạm nhỏ trong lúc chạy | Writable container filesystem hoặc volume tạm theo khả năng hỗ trợ | Mất khi group bị xóa/redeploy; không dùng làm bản dữ liệu duy nhất |
| File đầu vào/đầu ra dạng object | Azure Blob Storage qua SDK hoặc HTTPS | Có API, retry, identity, object semantics; thích hợp report, CSV, JSON |
| Cần thư mục dùng chung có file semantics | Azure Files volume mount nếu OS và feature hỗ trợ | Phải quản lý quota, quyền, network, locking và chi phí |

### 14.2. Mount Azure Files

ACI có khả năng mount Azure Files volume trong những cấu hình được hỗ trợ. Với volume mount:

- Tạo Storage Account và Azure file share trước.
- Đảm bảo network path tới file service và cơ chế xác thực cho mount.
- Gắn volume vào path trong container theo cấu hình group.
- Kiểm tra giới hạn OS, quyền POSIX/SMB, file locking và hiệu năng.
- Không nhúng storage account key vào repository/IaC không được bảo vệ.

Ví dụ logic:

~~~text
Container /work
    └── /work/output/report.csv
                 |
                 v
Azure Files share: reports
~~~

Các chi tiết khai báo volume và credential cần theo tài liệu ACI hiện hành. Với job Java chỉ ghi một file rồi tải lên, **Azure Blob SDK** thường đơn giản hơn mount SMB.

### 14.3. Kiểm tra đầu ra trước khi công bố thành công

Một giao thức thực thi an toàn:

1. Job nhận **runId** duy nhất.
2. Đọc input có version/ETag nếu thích hợp.
3. Xử lý và ghi output vào đường dẫn tạm, ví dụ **reports/runId/tmp/**.
4. Kiểm tra kích thước, checksum/schema và business validation.
5. Công bố marker **reports/runId/success.json** hoặc cập nhật trạng thái transaction phù hợp.
6. Chỉ lúc đó exit **0**.
7. Nếu lỗi, ghi thông tin thất bại không chứa secret, exit khác **0**.
8. Orchestrator chỉ chuyển bước tiếp khi thấy cả exit code và trạng thái output hợp lệ.

Lý do: kết thúc với exit code 0 nhưng dữ liệu chưa được upload thành công là một **false positive** nguy hiểm.

## 15. Thiết kế job theo sự kiện hoặc theo lịch

ACI cung cấp compute container; nó không tự định nghĩa một lịch cron hay hàng đợi nghiệp vụ đầy đủ. Để chạy theo giờ/sự kiện, dùng công cụ ngoài.

### 15.1. Workflow một job theo lịch

~~~mermaid
flowchart TB
    S["Scheduler: Logic Apps / Automation / Function"] --> V["Kiểm tra lịch, quota, concurrency"]
    V --> I["Tạo run ID + container group ACI"]
    I --> W["Java worker xử lý dữ liệu"]
    W --> R{"Exit code và output?"}
    R -->|"Đạt"| OK["Đánh dấu success"]
    R -->|"Lỗi"| FAIL["Đánh dấu failure / retry có kiểm soát"]
    OK --> C["Lưu log, dọn group"]
    FAIL --> C
~~~

Một scheduler cần quyền tạo và đọc container group ở scope đã định; nên dùng **managed identity**, không lưu user/password vào code hoặc job definition.

### 15.2. Tránh tạo job trùng

Khi một sự kiện được gửi lại hoặc scheduler retry sau timeout, có thể xuất hiện hai container group xử lý cùng input. Dùng:

- **Job ID** lấy từ event/queue message hoặc batch identifier.
- **Idempotency key** trong hệ thống lưu trạng thái.
- Kiểm tra **already succeeded** trước khi ghi đầu ra.
- Unique constraint hoặc trạng thái điều phối lưu bền vững.
- Giới hạn concurrency và cơ chế lock/lease theo dịch vụ hỗ trợ.
- Retry theo policy ở orchestrator, không để mọi tầng retry vô hạn.

Ví dụ, thay vì ghi **report.csv** cố định, job có thể ghi **reports/2026-11-20/run-123/report.csv**, rồi cập nhật con trỏ bản báo cáo được phê duyệt sau khi xác minh.

### 15.3. Khi nên dùng Azure Container Apps Jobs

Nếu yêu cầu thường xuyên gồm **Cron schedule**, **event-driven scaling**, **parallel executions**, **retry policy** hoặc **execution history** theo tính năng được dịch vụ hỗ trợ, hãy đánh giá Azure Container Apps Jobs trước khi tự xây nhiều Logic Apps/Functions quanh ACI.

ACI vẫn hữu ích nếu cần khởi tạo nhanh một container group qua API hoặc cần kiểm soát trực tiếp lifecycle của từng group cho một tác vụ đơn giản.

## 16. CPU, RAM, giới hạn và hiệu năng

### 16.1. Resources là một quyết định kỹ thuật và tài chính

Ví dụ:

~~~text
Job A: 1 vCPU và 1.5 GiB RAM, chạy vài phút
Job B: 2 vCPU và 4 GiB RAM, chạy khối dữ liệu lớn hơn
~~~

Nếu tăng CPU/RAM, job có thể chạy nhanh hơn nhưng chi phí trên một đơn vị thời gian cũng tăng. Ngược lại, cấp thiếu RAM làm process bị kill hoặc không đủ khả năng khởi động.

**Không suy luận tỷ lệ tăng tốc tuyến tính**: Java worker có thể bị giới hạn bởi I/O, API throttling, database connection, garbage collection hoặc network chứ không phải CPU.

### 16.2. Bài toán tối ưu thời gian–chi phí

Giả sử hai cấu hình của cùng một tác vụ:

| Cấu hình | Tài nguyên yêu cầu | Thời gian thử nghiệm | Nhận xét |
|---|---|---|---|
| A | 1 vCPU, 1.5 GiB | 6 phút | Ít tài nguyên, chạy lâu |
| B | 2 vCPU, 3 GiB | 4 phút | Nhiều tài nguyên hơn, chạy nhanh hơn |

Đây là **số liệu giả định**, không phải benchmark của ACI. Để so sánh chi phí, cần áp dụng **đơn giá vCPU/giây và memory/giây hiện hành** và các quy tắc tính thời gian metering, cộng thêm chi phí Storage, Registry và logs. Không thể chọn B chỉ vì hoàn thành sớm hơn.

### 16.3. Các giới hạn cần kiểm tra

- Số vCPU/GiB tối đa cho group và cho container trong region.
- Quota subscription và hạn mức container groups.
- OS, image architecture và các feature được hỗ trợ.
- Thời gian startup và image pull; kích thước image lớn làm chậm cold start.
- Khả năng networking/VNet, IP, port, DNS và NAT.
- Số container trong group, số volume, dung lượng log và giới hạn API.
- Tài nguyên có sẵn trong region tại thời điểm triển khai.
- Tương thích giữa CPU/memory requests của container và hạn mức group.

Không dùng ACI để hứa hẹn thời gian khởi động vài giây trong mọi trường hợp. Với SLA khắt khe, cần đo startup distribution (p50/p95) và cân nhắc pre-warmed hoặc dịch vụ khác.

## 17. Đánh giá chi phí ACI cho workload ngắn hạn

### 17.1. Ví dụ định lượng

Một batch job giả định:

- Chạy **20 lần/ngày**.
- Mỗi lần **4 phút** (đã tính theo cách mô phỏng một lần chạy).
- Tháng có **30 ngày**.
- Mỗi container group yêu cầu **1 vCPU và 1,5 GiB RAM**.

Tổng thời gian chạy tính theo ví dụ:

~~~text
20 lần/ngày × 4 phút/lần × 30 ngày = 2.400 phút
2.400 phút ÷ 60 = 40 giờ

vCPU-hours quy đổi          = 1 × 40   = 40 vCPU-giờ
GiB-hours quy đổi           = 1,5 × 40 = 60 GiB-giờ
~~~

Đây là phép tính **resource-time minh họa**, **không phải hóa đơn Azure**. Thời gian được metering thực tế còn phụ thuộc quy tắc của dịch vụ, đặc biệt các giai đoạn tạo/start/stop và thời lượng tối thiểu. Giá từng region cũng khác nhau.

Nếu để một container service **chạy liên tục** 30 ngày:

~~~text
30 ngày × 24 giờ = 720 giờ
~~~

Nó có thời lượng cấp tài nguyên lớn hơn rất nhiều so với 40 giờ job giả định. Nhưng muốn so sánh công bằng còn phải xét số lần cold start, kích thước image, throughput, lỗi/retry và dịch vụ orchestration phụ trợ.

### 17.2. Các dòng chi phí thường bị bỏ sót

| Thành phần | Cách có thể phát sinh chi phí |
|---|---|
| ACI compute | vCPU/memory và thời gian được tính phí |
| Azure Container Registry | Tier registry, dung lượng image và chức năng bổ sung |
| Azure Blob Storage/Azure Files | Dữ liệu lưu, transactions, backup và retention |
| Azure Monitor/Log Analytics | Ingestion, retention, truy vấn và alert |
| Network/NAT Gateway/Firewall | Theo tài nguyên/dữ liệu và cấu hình |
| Service orchestration | Logic Apps/Functions/Automation và API calls tùy mô hình |
| Image scanning/security | Dịch vụ quét, quản lý bảo mật hoặc công cụ bên ngoài |
| Vận hành | Công sức quản lý job, lỗi và báo cáo |

Khi job ngừng chạy, **không mặc định** ACR, Storage, workspace, NAT Gateway hoặc network-related resources ngừng tính phí. Đặc biệt tài nguyên NAT có thể tính phí ngay cả khi không có container đang chạy, theo mô hình dịch vụ.

### 17.3. Đo sau triển khai

Trong Cost Management:

1. Chọn subscription/resource group có container group.
2. Xem chi phí theo service/resource/meter trong khoảng thời gian đủ để dữ liệu billing cập nhật.
3. Đối chiếu số lần chạy, thời gian chạy, CPU/memory request và số lần retry.
4. So sánh với log của orchestrator và trạng thái container thực tế.
5. Tách chi phí lưu trữ, registry và network để tránh kết luận sai.
6. Đặt budget/alert cho lab và nhóm workload.

Dữ liệu cost có thể cập nhật chậm, nên biểu đồ ngay sau lệnh delete không phải bằng chứng cuối cùng cho một kỳ billing.

## 18. Monitoring và kiểm chứng kết quả job

### 18.1. Tối thiểu phải quan sát những gì?

| Tín hiệu | Ý nghĩa |
|---|---|
| Request tạo container group | Azure đã chấp nhận yêu cầu triển khai hay chưa |
| Provisioning state / group state | Group có được tạo và chạy không |
| Container state / exit code | Process kết thúc thế nào |
| Startup, image pull và error events | Có lỗi registry, capacity, network hoặc image |
| Stdout/stderr logs | Ứng dụng đã thực hiện bước nào |
| Output verification | Báo cáo/tệp/trạng thái nghiệp vụ có đúng không |
| Run ID và correlation ID | Kết nối logs với lần chạy và dữ liệu input |
| Runtime duration | Giám sát SLO và chi phí |
| Retry count và dead-letter/failed jobs | Ngăn retry vô hạn |
| Security/audit events | Ai đã triển khai image và đổi cấu hình |

### 18.2. Xem trạng thái và logs bằng CLI

~~~bash
az container list \
  --resource-group "$RG" \
  --output table

az container show \
  --resource-group "$RG" \
  --name "$CG" \
  --output json

az container logs \
  --resource-group "$RG" \
  --name "$CG"
~~~

Đối với group nhiều container, chỉ rõ container cần xem bằng tham số **--container-name** nếu phiên bản CLI hỗ trợ:

~~~bash
az container logs \
  --resource-group "$RG" \
  --name "$CG" \
  --container-name "<container-name>"
~~~

Trong production, logs phải được thu thập và lưu trước khi container group bị xóa theo retention policy; **stdout/stderr gắn với group không thay thế kho logs bền vững**.

### 18.3. Xem trực tiếp khi container còn chạy

Một số lệnh như **az container attach** có thể hỗ trợ theo dõi dòng output/events trong lúc group hoạt động:

~~~bash
az container attach \
  --resource-group "$RG" \
  --name "$CG"
~~~

Với job chỉ chạy vài giây, attach có thể đến sau khi process đã kết thúc. Vì vậy trong runbook hãy ưu tiên **show + logs + output validation** và không phụ thuộc vào phiên tương tác để xác nhận thành công.

### 18.4. Monitoring dài hạn

Với ứng dụng production, nên:

- Gửi logs/telemetry đến hệ thống quan sát phù hợp khi ACI và cấu hình hỗ trợ.
- Dùng Azure Monitor/Log Analytics và giám sát của orchestration system cho job failures và runtime.
- Lưu correlation ID trong mọi log quan trọng.
- Tạo cảnh báo nếu không có kết quả trước deadline.
- Tạo cảnh báo khi số retry bất thường hoặc container chạy quá lâu.
- Tách cảnh báo **platform deployment error** với **application business error**.

Không đưa dữ liệu khách hàng, secret, connection string hay token vào stdout.

## 19. Xử lý sự cố: từ image đến kết quả nghiệp vụ

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Container group không được tạo | Sai region, quota, CPU/memory không hợp lệ, thiếu quyền | Thông báo CLI/Activity Log, limits và RBAC |
| Không kéo được image | Sai image/tag, private registry auth, registry network, rate limiting | Image ref, pull credentials, ACR permission, DNS |
| Image được kéo nhưng process không chạy | ENTRYPOINT/CMD sai, OS/architecture không tương thích | Container events, startup logs, image metadata |
| Job chạy xong rồi chạy lại | **restartPolicy Always** | Kiểm tra restart policy và exit events |
| Job Failed sau vài giây | Chương trình exit khác 0, thiếu env/secret, lỗi dependency | Container exit code, stderr và cấu hình |
| Group Running quá lâu | Vòng lặp vô hạn, sidecar không thoát, external API treo | Logs, deadlines, timeout và group components |
| Job Succeeded nhưng không thấy report | Chỉ ghi file local hoặc validate output chưa đủ | Kiểm tra upload/commit và Blob/Database path |
| Hai báo cáo trùng nhau | Retry/scheduler tạo hai execution | Run ID, idempotency key và orchestration logs |
| Không kết nối được Storage/DB | DNS, firewall, VNet, private endpoint, identity | Network path, RBAC và app logs |
| Không thấy stdout/stderr | Ứng dụng không ghi log, group đã xóa, sai container name | Kiểm tra group state và log retention |
| ACI đã xong nhưng tổng bill còn | ACR, Storage, NAT, logs hoặc metering lag | Cost Management theo resource/meter |
| Container bị dừng do thiếu memory | Memory request thấp hoặc Java heap vượt giới hạn | Events, memory usage, JVM flags |
| Network private không hoạt động | Subnet delegation/UDR/NSG/DNS hoặc VNet feature không hỗ trợ | Subnet config, effective routes, ACI networking docs |
| Public endpoint không phản hồi | Không mở port, process bind localhost, sai DNS/port | Group IP, image listener và logs |

### 19.1. Quy trình điều tra bốn lớp

**Lớp 1 — Deployment:** request tạo container group thành công? đúng subscription, region, SKU, quota?

**Lớp 2 — Image/runtime:** image pull thành công, command có tồn tại, container OS/architecture phù hợp, process có khởi động?

**Lớp 3 — Application/dependencies:** env vars, managed identity, DNS, network, Storage/DB, memory và timeout có hoạt động?

**Lớp 4 — Business outcome:** output đúng version, không bị tạo trùng, exit code 0 và có marker thành công?

Sửa đúng lớp. Không giải quyết lỗi private registry bằng cách bật admin user không kiểm soát, cũng không mở public database firewall Any/Any để xử lý sai DNS.

### 19.2. Trường hợp Java worker thiếu memory

Java sử dụng heap, metaspace, stacks, JIT code cache và native memory. Với group yêu cầu **1.5 GiB**, không nên đặt heap bằng 1.5 GiB và kỳ vọng JVM luôn an toàn. Cần chừa chỗ cho non-heap và container runtime, theo dõi GC và peak memory.

Cấu hình JVM phải được thử bằng workload thật; không hard-code một **-Xmx** vượt memory đã khai báo cho container.

### 19.3. Nếu ACI chạy lâu quá giới hạn nghiệp vụ

Đừng chỉ dựa vào restart policy. Orchestrator nên có **deadline** cho job:

1. Tạo group với run ID.
2. Ghi nhận thời điểm bắt đầu.
3. Poll trạng thái theo backoff và hạn chế API calls.
4. Nếu quá hạn, ghi log/sự kiện và yêu cầu stop/delete phù hợp theo runbook.
5. Xác minh output có hoàn tất một phần hay không.
6. Quyết định retry với idempotency, hoặc đưa vào hàng đợi xử lý thủ công.

## 20. Bảo mật và vận hành production

### 20.1. Least privilege và identities

Phân chia vai trò:

- CI pipeline: chỉ được push image vào registry/repository được duyệt.
- Orchestrator: chỉ được tạo/xem/xóa container group trong phạm vi cần thiết.
- Container runtime: chỉ được kéo image cần thiết.
- Java worker: chỉ được đọc input và ghi output tại nơi được phép.
- Operator: được xem health/logs nhưng không tự động có quyền đọc secret nhạy cảm.

Azure RBAC quản lý tài nguyên không tự cấp quyền data plane trên Blob/SQL/Key Vault. Hãy kiểm tra role assignment ở từng dịch vụ.

### 20.2. Container image hygiene

- Dùng image tối thiểu và có nguồn tin cậy.
- Quét CVE, kiểm tra dependencies và ký/kiểm soát artifact khi quy trình yêu cầu.
- Pin version/digest; tránh chỉ dùng **latest** trong production.
- Tránh chạy process với quyền root khi không cần và khi base image/cấu hình hỗ trợ.
- Không đóng gói private key, password hoặc token vào image layer.
- Rebuild image khi runtime hoặc hệ điều hành có bản vá.
- Kiểm tra SBOM và license nếu tổ chức yêu cầu.

### 20.3. Network boundary

- Không cấp public IP nếu job chỉ cần outbound.
- Nếu dùng VNet, chọn subnet/delegation và DNS theo yêu cầu.
- Giới hạn luồng tới các private endpoints và API cần thiết.
- Sử dụng TLS cho dữ liệu trong quá trình truyền.
- Có cơ chế egress ổn định nếu hệ thống đích bắt buộc IP allowlist.
- Không giả định container chạy trong VNet sẽ tự có quyền truy cập mọi private resource.

### 20.4. Data safety

- Input/output quan trọng phải ở lưu trữ bền vững.
- Đặt timeout, idempotency, retry và dead-letter/failed status.
- Không xóa input ngay sau khi bắt đầu xử lý.
- Ghi output theo run ID và chỉ công bố khi validate xong.
- Có backup/retention phù hợp với lớp lưu trữ.
- Dọn container group không được xóa business data cần giữ.

### 20.5. Quy trình thay đổi

Khi đổi image, CPU/memory, restart policy hoặc network:

1. Review thay đổi và vùng ảnh hưởng.
2. Chạy thử với tập dữ liệu nhỏ.
3. Đo time-to-start, duration, exit code và output correctness.
4. Kiểm tra trạng thái lỗi và khả năng retry.
5. Xác nhận log/alert có đầy đủ.
6. Theo dõi chi phí thực tế trong giai đoạn đầu.
7. Có cách quay về image/config đã biết hoạt động.

## 21. Checklist trước khi đưa workload ngắn hạn vào production

- [ ] Đã xác định job hoàn tất khi nào và exit code có ý nghĩa ra sao.
- [ ] Đã chọn đúng ACI thay vì ACA Jobs, Functions, AKS Jobs hoặc Batch theo yêu cầu.
- [ ] Image có version/digest, được build/test/scan theo quy trình.
- [ ] Restart policy đúng: **Never** hoặc **OnFailure** cho job phù hợp; không vô tình dùng Always.
- [ ] CPU/memory requests đủ và nằm trong quota/region hỗ trợ.
- [ ] Container group không chứa sidecar chạy vô hạn ngoài ý muốn.
- [ ] Không mở inbound/public IP nếu không cần.
- [ ] Đã thử DNS, firewall, private endpoint, VNet egress và image pull.
- [ ] Registry credentials/managed identity được cấu hình đúng theo khả năng hỗ trợ.
- [ ] Secret không nằm trong image, repo, command history hoặc logs.
- [ ] Job dùng run ID và idempotency để chống xử lý trùng.
- [ ] Output được lưu bền vững, kiểm tra trước khi exit thành công.
- [ ] Có deadline, retry có giới hạn và cách xử lý job thất bại.
- [ ] Có log, metric, correlation ID và alert theo SLO.
- [ ] Có lịch hoặc event trigger nằm ở hệ thống điều phối phù hợp.
- [ ] Đã phân tích cost ACI và chi phí ACR/Storage/NAT/logging.
- [ ] Đã có quy trình dọn container group và lưu lại bằng chứng chạy.
- [ ] Đã thử phục hồi sau image pull failure, OOM và mất kết nối dữ liệu.

## 22. Bài tập thực hành và tình huống suy luận

### Bài tập 1: Phân loại workload

Chọn ACI, Azure Container Apps Jobs, Azure Functions, AKS hoặc Azure Batch cho các trường hợp:

1. Chạy script xử lý một file CSV trong vài phút, người vận hành tạo thủ công.
2. Cron job chạy 1 lần mỗi đêm, cần retry và lịch sử execution.
3. HTTP REST API chạy 24/7 có autoscale và nhiều revisions.
4. Hàng chục nghìn tác vụ tính toán song song.
5. Tổ chức đã có AKS và muốn chạy batch Job sử dụng chính sách Kubernetes hiện hành.

Giải thích trade-off, không chỉ nêu tên dịch vụ.

### Bài tập 2: Thử ba restart policy

Viết một container script in **start**, sau đó exit **0**. Thực hiện trong lab với restart policy **Never**, **OnFailure** và **Always** ở những group riêng biệt, theo dõi hành vi và chi phí. Sau đó đổi script exit **1** để quan sát khác biệt.

**Cảnh báo:** với Always có thể xuất hiện vòng lặp restart; chỉ thử trong lab được phê duyệt và đặt giới hạn thời gian rõ ràng.

### Bài tập 3: Chạy Java batch image

1. Tạo **BatchReport.java** và Dockerfile ví dụ.
2. Build/test local, xem exit code.
3. Push vào ACR lab qua quyền thích hợp.
4. Cấu hình ACI kéo private image bằng cơ chế được hỗ trợ.
5. Chạy với restartPolicy Never và truyền JOB_ID.
6. Đọc logs, exit code, kiểm tra output.
7. Dọn resource lab sau khi lưu bằng chứng.

### Bài tập 4: Thiết kế idempotent job

Một event “file uploaded” có thể được phát ít nhất một lần và có thể gửi lại. Worker đọc file, sinh PDF và cập nhật database.

Hãy thiết kế:

- Khóa idempotency.
- Cơ chế chống hai execution chạy đồng thời.
- Đường output có run ID.
- Cách xác nhận thành công.
- Retry khi database tạm thời unavailable.
- Cách xử lý khi PDF đã upload nhưng database chưa commit.

### Bài tập 5: Networking private

ACI worker chỉ được gọi Azure SQL qua Private Endpoint và ghi Blob Storage trong mạng riêng. Hãy vẽ subnet/delegation, DNS, VNet path, RBAC, firewall, NAT cho egress nếu cần. Giải thích vì sao tạo public IP cho group không phải điều kiện để truy cập database private.

### Bài tập 6: Phân tích chi phí

Một job chạy 30 lần/ngày, mỗi lần 3 phút với 1 vCPU và 2 GiB, trong tháng 30 ngày.

1. Tính tổng phút và giờ tài nguyên theo giả định.
2. Tính vCPU-hours và GiB-hours quy đổi.
3. Liệt kê khoản chi phí phụ thuộc CPU/memory/time và những khoản khác.
4. Giải thích vì sao nếu Always khiến job lặp vô hạn thì dự toán sai.
5. Đề xuất KPI giám sát theo lần chạy.

### Câu hỏi tự kiểm tra

1. Container group trong ACI là gì?
2. Restart policy mặc định Always có nguy cơ gì với một batch job?
3. OnFailure có thể tạo trùng output trong tình huống nào?
4. Never khác OnFailure ở cách xử lý exit code khác 0 thế nào?
5. Group Succeeded có đủ chứng minh báo cáo nghiệp vụ chính xác không?
6. Vì sao ACI không tự thay thế một hệ thống CronJob/queue orchestration?
7. Khi nào nên dùng ACA Jobs thay vì tự viết scheduler cho ACI?
8. Image pull từ private ACR khác gì quyền Java worker đọc Azure Blob?
9. Vì sao không nên ghi output duy nhất vào writable filesystem của container?
10. Khi nào cần NAT Gateway hoặc thiết kế egress cụ thể?
11. Chi phí ACI ngoài CPU/memory còn gồm những gì?
12. Vì sao phải kiểm tra toàn bộ các container nếu group có sidecar?
13. Khi group không start, nên kiểm tra image pull hay nghiệp vụ trước?
14. Làm cách nào chứng minh một job chạy đúng một lần theo ý nghĩa nghiệp vụ?

## 23. Tài liệu tham khảo

- [Azure Container Instances overview — Microsoft Learn](https://learn.microsoft.com/azure/container-instances/container-instances-overview)
- [Container groups in Azure Container Instances](https://learn.microsoft.com/azure/container-instances/container-instances-container-groups)
- [Container restart policies](https://learn.microsoft.com/azure/container-instances/container-instances-restart-policy)
- [Quickstart: Deploy a container instance using Azure CLI](https://learn.microsoft.com/azure/container-instances/container-instances-quickstart)
- [Deploy container groups with Azure CLI and YAML](https://learn.microsoft.com/azure/container-instances/container-instances-multi-container-yaml)
- [Use Azure Container Registry with Azure Container Instances](https://learn.microsoft.com/azure/container-instances/container-instances-using-azure-container-registry)
- [Deploy container instances into an Azure virtual network](https://learn.microsoft.com/azure/container-instances/container-instances-vnet)
- [Mount an Azure file share in Azure Container Instances](https://learn.microsoft.com/azure/container-instances/container-instances-volume-azure-files)
- [Azure Container Apps jobs overview](https://learn.microsoft.com/azure/container-apps/jobs)
- [Azure Container Instances pricing](https://azure.microsoft.com/pricing/details/container-instances/)
- [Azure Container Registry pricing](https://azure.microsoft.com/pricing/details/container-registry/)

