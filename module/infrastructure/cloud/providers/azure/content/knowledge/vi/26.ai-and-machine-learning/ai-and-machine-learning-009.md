# Azure Machine Learning với workspace, compute và data asset

Một nhóm phát triển ứng dụng bán lẻ đang lưu đơn hàng trong Azure SQL Database, ảnh sản phẩm ở Azure Blob Storage và sự kiện người dùng ở Azure Event Hubs. Nhóm muốn xây mô hình dự đoán khách hàng có khả năng ngừng sử dụng dịch vụ, huấn luyện lại định kỳ rồi theo dõi kết quả trên Azure. Nếu từng kỹ sư chạy notebook trên laptop với tập dữ liệu khác nhau, việc tái lập kết quả, quản lý quyền và kiểm soát chi phí sẽ rất khó.

**Azure Machine Learning (Azure ML)** cung cấp nền tảng quản lý vòng đời học máy. Ba thành phần nền tảng cần hiểu đầu tiên là **workspace** (không gian tổ chức tài nguyên và thí nghiệm), **compute** (tài nguyên thực thi mã) và **data asset** (tài nguyên dữ liệu có tên, kiểu và phiên bản để tham chiếu trong công việc ML). Khi kết hợp đúng, ba thành phần này giúp nhóm chạy huấn luyện có thể kiểm chứng, tách dữ liệu khỏi mã, tái sử dụng tài nguyên, quản lý bảo mật và theo dõi chi phí.

Bài thuộc chương **AI và học máy trên Azure** của mô-đun **CLOUD_PROVIDERS_AZURE**. Mô-đun bao quát Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; sau đó học triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Azure ML là nơi những kiến thức hạ tầng, dữ liệu và identity cùng phục vụ quy trình huấn luyện và triển khai mô hình.

> **Phạm vi:** Tài liệu ưu tiên **Azure Machine Learning v2**, Azure ML Studio, Azure CLI extension **ml** và **azure-ai-ml Python SDK**. Một số hướng dẫn cũ dùng v1 SDK, Datasets v1 hoặc thuật ngữ khác: không trộn cú pháp v1 và v2. Tính năng, quota, VM SKU, GPU, workspace networking, vùng Azure và giá có thể thay đổi; cần kiểm tra cấu hình thật trước khi áp dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả quan hệ giữa Azure subscription, resource group, Azure ML workspace và các dịch vụ phụ thuộc.
2. Phân biệt **compute instance**, **AML compute cluster** và những loại compute target khác.
3. Chọn CPU/GPU SKU, min/max nodes, dedicated/low-priority, network và auto-scale theo workload.
4. Giải thích **datastore** khác **data asset**, **URI_FILE**, **URI_FOLDER** và **MLTABLE**.
5. Tạo phiên bản data asset và tham chiếu một phiên bản xác định trong job.
6. Mô tả job gồm **code, command, environment, compute, inputs và outputs**.
7. Sử dụng ví dụ Azure CLI và Python SDK v2 để xem workspace/compute/data và tạo tài nguyên lab có kiểm soát.
8. Hiểu quản lý identity, RBAC, data-plane permissions, managed identity, Key Vault và private networking.
9. Phân biệt ML workspace với Azure AI services, Azure OpenAI/Azure AI Foundry và ứng dụng suy luận.
10. Lập checklist kiểm thử, theo dõi, tối ưu chi phí và dọn tài nguyên sau lab.

## 1. Azure Machine Learning là gì?

Azure ML là dịch vụ nền tảng dành cho người xây dựng, huấn luyện, đăng ký, triển khai và quản lý mô hình học máy. Nó tích hợp với nhiều dịch vụ Azure để:

- Tổ chức workspace, jobs, experiments, data assets, model assets và environments.
- Chạy mã Python/R hoặc container-based workflows theo loại compute được hỗ trợ.
- Quản lý tập dữ liệu và các đường dẫn đến storage.
- Theo dõi trạng thái chạy, logs, metrics và model artifacts.
- Hỗ trợ pipelines, AutoML, model registry và endpoints theo khả năng.
- Kiểm soát identity, quyền, mạng và chi phí hạ tầng.

~~~text
Data sources                    Azure Machine Learning
Azure SQL / Blob / ADLS         +---------------------------+
Cosmos DB / Event Hubs -------> | Workspace                 |
                                |   Data assets             |
                                |   Environments            |
                                |   Jobs / Experiments      |
                                |      |                    |
                                |      v                    |
                                |   Compute instance/cluster|
                                |      |                    |
                                |      v                    |
                                |   Models / outputs        |
                                +---------------------------+
                                             |
                                             v
                                  Evaluation / deployment
                                             |
                                             v
                                    API / application
~~~

**Azure ML không tự tạo dữ liệu đáng tin cậy từ nguồn thô**. Vẫn cần quy trình data quality, partitioning, nhãn, consent, model validation và trách nhiệm bảo mật của đội dự án.

## 2. Workspace: trung tâm cộng tác và quản trị

**Azure Machine Learning workspace** là tài nguyên Azure dùng làm phạm vi tổ chức các công việc ML. Nó giúp nhóm xác định:

- Jobs và experiments thuộc dự án nào.
- Data/model/environment assets nằm ở workspace nào.
- Ai được tạo, xem, chạy hoặc quản trị tài nguyên.
- Compute targets nào được đăng ký và sử dụng.
- Kết nối đến datastores và external services.
- Logs, metrics, lineage và các metadata liên quan.

~~~text
Azure subscription
    |
    v
Resource group: rg-ml-lab
    |
    +-- Azure ML workspace: aml-churn-lab
    |      |
    |      +-- Data assets: churn_data:1, churn_data:2
    |      +-- Environments: sklearn-env:1
    |      +-- Jobs / experiments
    |      +-- Compute: cpu-cluster-lab
    |      +-- Models / endpoints
    |
    +-- Storage account (hoặc nguồn được liên kết)
    +-- Key Vault
    +-- Application Insights / monitoring resources
    +-- Container Registry (khi cần, theo cơ chế dịch vụ)
~~~

Workspace không phải một VM. Tạo workspace **không đồng nghĩa đã có sẵn GPU đang chạy**. Compute là tài nguyên được chọn hoặc gắn với workspace và có vòng đời/tính phí riêng.

### Workspace khác resource group

| Khái niệm | Chịu trách nhiệm chính |
|---|---|
| **Subscription** | Billing, policy/quota và phạm vi quản trị Azure |
| **Resource group** | Nhóm tài nguyên Azure để quản lý vòng đời/IaC |
| **Azure ML workspace** | Quản lý assets, jobs, metadata và trải nghiệm ML |
| **Compute target** | Thực thi code/job, tiêu thụ CPU/GPU/memory |
| **Datastore** | Thông tin truy cập một vùng lưu trữ dữ liệu được hỗ trợ |
| **Data asset** | Tham chiếu dữ liệu có tên/phiên bản/kiểu để dùng lại |

Một workspace có thể liên kết nhiều nguồn lưu trữ và compute; **workspace boundary không tự làm cho mọi Azure storage container thành dữ liệu được phép sử dụng**.

## 3. Các dịch vụ phụ thuộc của workspace

Workspace thường kết hợp với những tài nguyên Azure khác:

| Dịch vụ | Vai trò thường gặp | Điểm vận hành |
|---|---|---|
| **Azure Storage** | Chứa dữ liệu, job snapshots, artifacts hoặc default datastore theo cấu hình | RBAC, firewall, network, retention, storage cost |
| **Azure Key Vault** | Quản lý secrets và một số cấu hình nhạy cảm | Least privilege, auditing, rotation |
| **Application Insights/Azure Monitor** | Telemetry và chẩn đoán theo tính năng | Log retention, dữ liệu nhạy cảm, chi phí |
| **Azure Container Registry** | Container images cho environments/jobs/endpoints theo yêu cầu | Registry access, image security, data transfer |
| **Microsoft Entra ID** | Danh tính người dùng/service/workload | RBAC, managed identity, token lifetime |
| **VNet/Private Endpoint** | Kết nối riêng và hạn chế đường truy cập khi cấu hình | DNS, outbound dependencies, firewall |

**Không nên khẳng định ACR luôn được tạo ngay khi workspace tạo**. Trong các luồng Azure ML, container registry có thể được tạo hoặc yêu cầu khi cần xây image, tùy cấu hình/vòng đời của workspace.

### Tạo workspace có tốn tiền không?

Quy tắc tính phí còn tùy Azure ML và các dịch vụ liên quan. **Jobs, compute, storage, registry, network và log** là nguồn chi phí phổ biến; không suy ra “workspace rỗng miễn phí tuyệt đối” vì các tài nguyên liên kết vẫn có thể phát sinh phí.

## 4. Workspace và Azure ML Studio

**Azure ML Studio** là giao diện web để:

1. Xem workspace và cấu hình liên quan.
2. Quản lý compute instances/clusters.
3. Tạo, đăng ký và kiểm tra data assets.
4. Tạo/chạy jobs, pipelines hoặc AutoML.
5. Xem experiments, logs, metrics và outputs.
6. Quản lý models, endpoints và những thành phần khác theo quyền.

~~~text
Azure Portal
  -> Azure ML workspace resource
     -> Launch Studio
        -> Data
        -> Compute
        -> Jobs / Experiments
        -> Models / Endpoints
~~~

Tên menu và vị trí có thể thay đổi. **Studio là công cụ thao tác**, không phải một compute instance tự chạy notebook. Notebook có thể cần compute session/compute instance hoặc compute thực thi được hỗ trợ.

### Phân quyền đọc và chạy

Một người có thể được phép xem job logs nhưng không đủ quyền tạo compute; hoặc được chạy job nhưng không có quyền đọc storage nguồn. Phải kiểm tra cả **Azure ML workspace permissions** và **data-source permissions**.

## 5. Compute trong Azure ML nghĩa là gì?

**Compute** là năng lực xử lý để chạy notebook, training jobs, batch inference hoặc một số workloads ML. Cần xác định rõ người dùng muốn:

- Môi trường phát triển tương tác.
- Hạ tầng tự co giãn theo jobs.
- Chạy GPU training.
- Chạy một job ngắn định kỳ.
- Sử dụng tài nguyên compute ngoài workspace được attach.
- Phục vụ inference online với những cơ chế endpoint riêng.

~~~text
Data scientist
    |
    +--> Compute instance: khám phá, viết notebook, debug
    |
    +--> AML compute cluster: chạy job huấn luyện có hàng đợi
    |          |
    |          +--> CPU nodes
    |          +--> GPU nodes (nếu cần)
    |
    +--> Other supported compute targets / inference
               |
               +--> Tùy loại workload và khả năng dịch vụ
~~~

**Không coi mọi compute là một loại VM có cùng vòng đời.** Compute instance, AML compute cluster và managed online endpoints có cơ chế provisioning, auto-scaling và tính phí khác nhau.

## 6. Compute instance: môi trường phát triển tương tác

**Compute instance** là tài nguyên tính toán được quản lý cho công việc tương tác: notebook, terminal, chuẩn bị code, kiểm thử nhỏ hoặc debug trong workspace.

### Tình huống phù hợp

Một data scientist muốn thử pandas/scikit-learn, xem vài nghìn rows, xây feature transformations và xác nhận mã chạy đúng trước khi nộp job lên cluster.

~~~text
User -> Azure ML Studio -> Compute instance
                              |
                              +-- Jupyter/terminal
                              +-- Edit code
                              +-- Debug on sample
                              +-- Submit remote job
~~~

### Điểm cần nhớ

- Compute instance thường gắn với một người hoặc cấu hình quyền truy cập tương ứng.
- Khi đang **Running**, compute có thể phát sinh chi phí dù không dùng notebook.
- **Stop** khi không sử dụng; dùng shutdown/idle schedules nếu khả năng hỗ trợ.
- Lưu code/dữ liệu quan trọng vào nguồn thích hợp (Git, storage, data assets), **không coi local filesystem instance là backup duy nhất**.
- Dùng SKU phù hợp; notebook EDA thường không cần GPU đắt tiền.
- Quyền người dùng/identity của compute instance không tự cho phép truy cập mọi datastore.

### “Stop instance” có xóa dữ liệu không?

Stop và Delete có ngữ nghĩa khác nhau. Tuy nhiên **không dùng ổ đĩa compute instance làm source of truth**, vì lifecycle, backup và retention phải được xác định chính thức. Trước khi xóa instance phải kiểm tra dữ liệu/local changes cần giữ.

## 7. AML compute cluster: chạy jobs theo nhu cầu

**AML compute cluster (AmlCompute)** dùng cho training/batch jobs, có thể cấu hình số nodes tối thiểu/tối đa để quản lý tải theo hàng đợi.

~~~text
Job A ---------\
Job B ----------> Azure ML scheduler -> AML Compute Cluster
Job C ---------/                            |
                                             +-- Node 1
                                             +-- Node 2
                                             +-- ... tới max nodes
                                             |
                                    Idle -> scale xuống min nodes
~~~

### Khi nào dùng?

- Huấn luyện mô hình nhiều lần trên datasets/version khác nhau.
- Batch scoring định kỳ.
- Chạy hyperparameter sweeps hoặc pipeline steps.
- GPU training cần tách khỏi notebook cá nhân.
- Tác vụ có thể chờ trong job queue để tiết kiệm tài nguyên.

### Cấu hình chính

- **VM size:** CPU/GPU, memory, network, region availability.
- **Min instances:** lượng nodes nền có thể duy trì.
- **Max instances:** giới hạn scale và chi phí.
- **Idle scale-down delay:** điều kiện giảm nodes khi không còn việc.
- **Priority/tier:** dedicated hoặc low-priority/spot theo loại cluster và hỗ trợ.
- **Identity/network settings:** managed identity, VNet/isolation và access data.

Nếu đặt **min_instances = 0**, cluster có khả năng scale về 0 khi idle, nhưng **không đảm bảo mọi chi phí storage/network/log bằng 0**, và job mới có thể phải chờ provisioning nodes.

## 8. So sánh compute instance và compute cluster

| Tiêu chí | Compute instance | AML compute cluster |
|---|---|---|
| Mục tiêu chính | Interactive development | Chạy training/batch jobs |
| Người dùng | Thường gắn workflow cá nhân | Dùng chung theo job scheduler/workspace policy |
| Auto-scale | Stop/start theo cơ chế/schedule | Scale min/max nodes theo nhu cầu |
| Chi phí idle | Có thể tính khi instance còn running | Có thể scale tới 0 khi min=0 |
| GPU | Chọn SKU GPU nếu có hỗ trợ/quota | GPU compute nodes khi được cấp quota |
| Code storage | Có môi trường tương tác/local filesystem | Job code snapshot/mount/download và outputs |
| Job reproducibility | Dễ thử tay, ít chuẩn hóa nếu không version | Phù hợp jobs với code/env/data version được ghi |
| Rủi ro | Quên stop, dữ liệu local không được lưu | Queue/provisioning, VM quota, node interruptions |

**Compute instance không phải lựa chọn mặc định để chạy tác vụ production định kỳ 24/7**; hãy dùng job scheduler/compute cluster hoặc inference endpoint phù hợp.

## 9. CPU hay GPU: chọn theo workload

| Workload | Tài nguyên khởi đầu để đánh giá | Lưu ý |
|---|---|---|
| Data cleaning nhỏ/pandas | CPU + RAM đủ | Tối ưu memory trước |
| Scikit-learn cơ bản | CPU | GPU không tự mang lại lợi ích |
| NLP/CV deep learning | GPU phù hợp framework | CUDA/driver, VRAM, quota và giá |
| Batch scoring nhỏ | CPU | Cần đo time-to-provision và throughput |
| Distributed training | Nhiều nodes/GPU theo khả năng | Networking, parallel/distributed config |
| Feature engineering dữ liệu lớn | CPU nhiều RAM/Spark theo quy mô | Không nhầm tập lớn với bắt buộc GPU |

### Các giới hạn hay gặp

- Azure VM family không có ở region hoặc subscription đã chọn.
- GPU quota chưa được cấp dù giao diện có hiển thị SKU.
- Không đủ **regional vCPU quota** hoặc **AML compute quota**.
- Capacity tạm thời không sẵn có.
- Container environment thiếu CUDA/framework compatibility.

**Không tự mua GPU lớn để sửa một bài toán đọc CSV có lỗi schema.** Chẩn đoán code và dữ liệu trước khi scale.

## 10. Dedicated và low-priority/spot compute

Một số cấu hình AML compute cluster hỗ trợ loại VM ưu tiên thấp/spot để giảm chi phí với khả năng bị thu hồi tài nguyên.

### Dedicated

- Phù hợp jobs cần độ ổn định cao hơn.
- Giá thường cao hơn spot tương đương.
- Vẫn có thể có lỗi hạ tầng, quota, retries; không đảm bảo job bất tử.

### Low-priority/spot

- Có thể tiết kiệm cho batch jobs chịu được interruption.
- Node có thể bị preempted/evicted.
- Công việc cần checkpoints và retry/idempotency.
- Không phù hợp nếu SLA thời gian hoàn thành chặt mà không có phương án dự phòng.

### Ví dụ huấn luyện dài

~~~text
Training 8 giờ, Spot node bị thu hồi sau 6 giờ.

Không checkpoint:
  Có thể phải train lại từ đầu.

Có checkpoint định kỳ:
  Resume từ trạng thái đã lưu
  nếu framework/job logic hỗ trợ.
~~~

Không khẳng định mọi job/framework tự restore checkpoint chỉ vì compute dùng Spot. **Checkpoint phải được lưu ở storage bền vững và code hỗ trợ resume**.

## 11. Data asset: dữ liệu có tên, kiểu và phiên bản

**Data asset** trong Azure ML v2 là tài nguyên metadata tham chiếu dữ liệu, có thể có:

- **name**: tên dùng lại trong các jobs.
- **version**: phiên bản xác định.
- **type**: ví dụ **uri_file**, **uri_folder**, **mltable**.
- **path**: vị trí dữ liệu (local upload, datastore URI hoặc nguồn được hỗ trợ).
- **description/tags**: mô tả, owner, nhãn nghiệp vụ.

~~~text
Azure Blob / ADLS data:
  training/churn/2026-11/part-*.parquet
                |
                v
Azure ML Data asset:
  name: churn_train
  version: 3
  type: uri_folder
  path: azureml://datastores/.../paths/...
                |
                v
Training Job:
  input: azureml:churn_train:3
~~~

Data asset giúp quản lý **tham chiếu có tên/version**; không có nghĩa dữ liệu luôn được copy sang một database riêng trong workspace.

### Data asset khác một dataset theo nghĩa thống kê

“Dataset” có thể là bất kỳ tập bản ghi. “Data asset” ở Azure ML v2 là một **đối tượng quản lý để tham chiếu nguồn dữ liệu**. Khi tài liệu cũ nhắc **Dataset v1**, không sao chép lệnh tạo Dataset v1 vào SDK v2.

## 12. Datastore và data asset khác nhau thế nào?

| Tiêu chí | Datastore | Data asset |
|---|---|---|
| Vai trò | Khai báo kết nối đến storage được hỗ trợ | Khai báo dữ liệu cụ thể có tên/phiên bản |
| Ví dụ | Azure Blob container, ADLS Gen2 path, các kiểu hỗ trợ | Tập CSV huấn luyện, thư mục ảnh, MLTable |
| Thông tin | Storage location, auth/connection configuration | Name, version, type, path, metadata |
| Mức tái sử dụng | Nhiều datasets cùng dùng một storage | Một dataset cụ thể được nhiều jobs dùng |
| Bảo mật | Identity/credentials/network tới storage | Quyền truy cập asset metadata và quyền tới dữ liệu gốc |
| Mối liên hệ | Cung cấp nơi lưu/đọc dữ liệu | Có thể tham chiếu đường dẫn nằm trong datastore |

### Phân biệt qua ví dụ

~~~text
Datastore:
  team-adls
  -> Azure Data Lake Storage Gen2 container curated

Data assets:
  churn_features:1
  -> team-adls/churn/2026-10

  churn_features:2
  -> team-adls/churn/2026-11
~~~

**Chỉ tạo datastore hoặc data asset không cấp quyền tự động cho mọi compute identity đọc storage.** Phải kiểm tra RBAC, ACL, firewall, private endpoint và authentication của job.

## 13. URI_FILE, URI_FOLDER và MLTABLE

| Data asset type | Mô tả | Khi dùng |
|---|---|---|
| **uri_file** | Tham chiếu một file | Model input CSV hoặc file cấu hình đã chuẩn hóa |
| **uri_folder** | Tham chiếu thư mục/tập files | Ảnh huấn luyện, nhiều Parquet files, batch dữ liệu |
| **mltable** | Định nghĩa tabular data qua tệp MLTable và chỉ dẫn đọc/transformation phù hợp | Tabular datasets cần rules cho paths, filters hoặc data loading |

### URI file

~~~text
churn_train_csv:1
type: uri_file
path: azureml://datastores/teamblob/paths/churn/train.csv
~~~

### URI folder

~~~text
product_images:2
type: uri_folder
path: azureml://datastores/teamblob/paths/images/train/
~~~

### MLTable

**MLTable** định nghĩa cách nạp tabular data từ file paths, có thể hỗ trợ các bước transformation phù hợp với thư viện/dịch vụ. Cần có **MLTable definition** và file nguồn ở vị trí hợp lệ; không phải đặt tên một folder là “mltable” là Azure ML tự đoán được schema.

## 14. Phiên bản dữ liệu và khả năng tái lập

Giả sử tháng 10 huấn luyện mô hình bằng một tập 100.000 khách hàng; tháng 11 dữ liệu tăng lên 110.000 khách hàng.

~~~text
Data asset: churn_train:1 -> snapshot/2026-10
Data asset: churn_train:2 -> snapshot/2026-11

Job run-001:
  data = churn_train:1
  environment = churn-sklearn:1
  code = commit abc123

Job run-002:
  data = churn_train:2
  environment = churn-sklearn:1
  code = commit def456
~~~

### Data asset version có bất biến dữ liệu không?

**Phiên bản metadata và nội dung bytes của storage là hai vấn đề khác nhau.** Một asset tham chiếu đến đường dẫn mà người khác vẫn có thể ghi đè file có thể khiến cùng version trả dữ liệu khác vào hai thời điểm nếu không có chiến lược immutable snapshots/versioned storage.

Để tái lập:

1. Đóng băng hoặc sao chép tập dữ liệu đầu vào vào **immutable/versioned path** theo chính sách.
2. Gắn data asset version xác định, tránh phụ thuộc hoàn toàn vào alias latest.
3. Ghi **code commit hash**, environment image/dependencies và parameters.
4. Ghi metrics, job ID, output/model version và nguồn gốc label.
5. Kiểm tra quyền/retention để dữ liệu còn truy cập được lúc audit.

**Alias latest** rất tiện cho phát triển nhưng có thể chuyển sang version khác; không nên xem nó là tham chiếu bất biến cho một lần chạy production cần audit.

## 15. Data asset so với đường dẫn trực tiếp

Một job có thể nhận đường dẫn trực tiếp hoặc tham chiếu data asset tùy SDK/API. Hai cách có trade-off:

| Đặc tính | Path trực tiếp | Versioned data asset |
|---|---|---|
| Bắt đầu nhanh | Có thể tiện cho thử nghiệm | Cần đăng ký asset |
| Khả năng tái sử dụng | Phụ thuộc tên/path | Rõ name/version |
| Metadata/description | Ít tiêu chuẩn hóa | Có thể quản lý cùng asset |
| Reproducibility | Phải tự kiểm soát path bất biến | Tốt hơn về tham chiếu; vẫn phải bảo vệ bytes |
| Governance | Phải tìm owner bằng quy trình riêng | Asset giúp nhóm tìm và quản lý dữ liệu |

Không cần tạo data asset cho mọi file trung gian một lần dùng; nhưng **training/evaluation datasets quan trọng** nên có cách versioning, lineage và quyền rõ ràng.

## 16. Các chế độ truy cập input: download, mount, direct

Azure ML jobs có thể hỗ trợ nhiều kiểu đưa dữ liệu vào compute, tùy asset type, compute target và SDK:

- **Download:** tải dữ liệu về đĩa trên compute trước/để chạy job.
- **Read-only mount:** cung cấp đường dẫn ảo/được mount để đọc khi cần.
- **Direct:** truyền URI/đường dẫn tham chiếu để code tự đọc qua công cụ thích hợp, khi được hỗ trợ.

~~~text
Azure storage ----download----> Local disk on compute
              \
               \---read-only mount---> Filesystem path at runtime
                \
                 \---direct URI------> Application-specific reader
~~~

### Chọn mode theo workload

| Trường hợp | Hướng đánh giá |
|---|---|
| Dataset nhỏ, đọc lặp lại nhiều lần | Download có thể hiệu quả |
| Dataset lớn, chỉ đọc một phần | Mount có thể giảm sao chép toàn bộ |
| Spark/SDK xử lý trực tiếp storage URI | Direct khi được hỗ trợ và được cấu hình |
| Nguồn dữ liệu private | Kiểm tra identity, firewall, routing và credential |
| Job offline cần files local | Download hoặc cơ chế cache được kiểm chứng |

**Không mặc định mọi kiểu data asset hỗ trợ cả ba modes**. MLTable có khả năng/mode và API đọc riêng; kết nối storage và compute/network phải tương thích.

## 17. Job trong Azure ML v2

Một **command job** là một đơn vị thực thi có khai báo đầy đủ các thành phần để Azure ML có thể lên lịch chạy và theo dõi.

~~~text
Job:
  code: train.py cùng thư mục mã
  command: python train.py --data <input-path>
  environment: image + Python dependencies
  compute: cpu-cluster-lab
  inputs:
    training_data -> churn_train:3
  outputs:
    model_output -> một thư mục artifacts
  experiment_name: churn-training
~~~

### Năm câu hỏi trước khi nộp job

1. **Code** nào được snapshot hoặc tham chiếu?
2. **Environment** nào chứa đúng Python/packages/CUDA?
3. **Input** có đúng data asset version và storage access không?
4. **Compute** có quota, network và capacity không?
5. **Output** được lưu ở đâu và có cần model registration/audit?

Không nhầm **job submission thành công** với **mô hình đã huấn luyện thành công**. Job có thể queued, preparing, running, failed, canceled hoặc completed tùy trạng thái.

## 18. Environment: đóng gói phần mềm chạy job

Một job cần nhiều hơn Python script: phiên bản Python, thư viện, container image và framework phải tương thích. **Azure ML environment** giúp khai báo image và dependencies để nhóm không chỉ dựa vào những package vô tình cài trên laptop.

~~~text
Code commit abc123
    + Data asset churn_train:1
    + Environment sklearn-lab:1
    + Compute cpu-churn-lab
                 |
                 v
             Training job
                 |
                 v
        Metrics + model artifacts
~~~

| Cách chọn environment | Lợi ích | Đánh đổi |
|---|---|---|
| **Curated environment** | Bắt đầu nhanh, có cấu hình tham khảo do Azure cung cấp | Cần kiểm tra tag/version và compatibility |
| **Custom environment** | Kiểm soát dependencies và image | Tốn công build, cập nhật bảo mật |

Không dùng image chứa secrets. Pin dependencies để tái lập, nhưng cũng duy trì quy trình vá CVE. **Tag latest không bất biến**, nên production cần kiểm soát image version/digest và lịch nâng cấp.

## 19. Tách quyền quản lý, chạy job và đọc dữ liệu

| Hoạt động | Lớp quyền liên quan |
|---|---|
| Tạo workspace, sửa network | Azure management plane / RBAC |
| Submit job, sửa data/model asset | Azure ML workspace permissions |
| Đọc CSV trong ADLS/Blob | Storage data-plane RBAC/ACL hoặc credentials thích hợp |
| Pull container từ ACR | Registry pull rights/identity |
| Đọc secret Key Vault | Key Vault data-plane permissions |
| Gọi model endpoint | Endpoint authentication/authorization |

**Có quyền Azure ML Contributor không tự có Storage Blob Data Reader trên mọi storage account.** Phải xác định principal thực sự truy cập dữ liệu trong job: user identity, compute managed identity hoặc cơ chế datastore credentials theo cấu hình.

## 20. Python SDK v2: kết nối workspace an toàn

Trong dự án Python lab riêng, cài SDK:

~~~bash
python -m pip install azure-ai-ml azure-identity
~~~

Sau khi được cấp workspace và identity:

~~~python
import os
from azure.ai.ml import MLClient
from azure.identity import DefaultAzureCredential

ml_client = MLClient(
    credential=DefaultAzureCredential(),
    subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
    resource_group_name=os.environ["AZURE_RESOURCE_GROUP"],
    workspace_name=os.environ["AZURE_ML_WORKSPACE"],
)

workspace = ml_client.workspaces.get(
    os.environ["AZURE_ML_WORKSPACE"]
)
print({"name": workspace.name, "location": workspace.location})
~~~

Đây là **đọc cấu hình**. DefaultAzureCredential không tự cấp quyền; local developer và managed identity production có thể là **hai principal khác nhau**. Không nhúng client secret/token trong source, logs hoặc notebook chia sẻ.

## 21. Azure CLI v2: xem workspace/compute/data

Azure ML v2 dùng Azure CLI extension **ml**. Các lệnh dưới đây chỉ đọc Azure resources; người thực hành phải cài extension theo tài liệu chính thức nếu máy chưa có.

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --query "{id:id,name:name,tenantId:tenantId}" -o json

az ml workspace show \
  --name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o json

az ml compute list \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o table

az ml data list \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o table

az ml data show \
  --name "churn_train" --version "1" \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o json

az ml datastore list \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o table

az ml job list \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o table
~~~

Nếu show báo không tìm thấy, trước tiên xác nhận **subscription, resource group, workspace/asset name, version và quyền**. Không tự tạo tài nguyên khác chỉ để tránh lỗi tên.

## 22. Python SDK v2: liệt kê hiện trạng trước khi tạo

~~~python
for compute in ml_client.compute.list():
    print({"name": compute.name, "type": compute.type})

for asset in ml_client.data.list():
    print({
        "name": asset.name,
        "version": asset.version,
        "type": asset.type,
    })
~~~

Việc liệt kê giúp tránh đụng cluster hoặc data asset đang được nhóm khác sử dụng. **Tên giống nhau không có nghĩa quyền sở hữu giống nhau**; những thao tác create_or_update có thể sửa tài nguyên hiện hữu nếu không kiểm tra trước.

## 23. Khai báo AML compute cluster dùng SDK v2

Ví dụ mô tả một CPU cluster cho workspace lab:

~~~python
from azure.ai.ml.entities import AmlCompute

cluster = AmlCompute(
    name="cpu-churn-lab",
    size="STANDARD_DS3_V2",
    min_instances=0,
    max_instances=2,
    idle_time_before_scale_down=120,
)

# Chỉ chạy trên workspace LAB sau khi được phép:
# op = ml_client.compute.begin_create_or_update(cluster)
# op.result()
~~~

- **size** chỉ minh họa VM SKU; cần kiểm tra availability/quota và cost theo region.
- **min_instances=0** cho phép scale về 0 khi idle trong điều kiện phù hợp, không xóa phí storage/log/network.
- **max_instances=2** giới hạn scale, không hứa rằng luôn có 2 nodes sẵn sàng.
- **idle_time_before_scale_down** là tham số vận hành, không cam kết provisioning sẽ tức thời.
- **begin_create_or_update** thay đổi Azure resource thật; đã đặt trong comment để tránh chạy nhầm.

Ví dụ YAML trong một dự án thực hành:

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/amlCompute.schema.json
name: cpu-churn-lab
type: amlcompute
size: STANDARD_DS3_V2
min_instances: 0
max_instances: 2
idle_time_before_scale_down: 120
~~~

Nếu người vận hành đã chuẩn bị file **cpu-cluster.yml** tại dự án lab và có quyền:

~~~bash
# TẠO/CẬP NHẬT COMPUTE - chỉ thực hiện trên LAB.
az ml compute create --file cpu-cluster.yml \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab"
~~~

Không dùng lệnh tạo/sửa trên production hoặc một cluster trùng tên khi chưa xác nhận owner và change window.

## 24. Đăng ký data asset URI_FOLDER có phiên bản

Giả sử Azure ML đã có datastore **teamblob**, chứa thư mục **churn/train/v1/**.

~~~python
from azure.ai.ml.entities import Data
from azure.ai.ml.constants import AssetTypes

training_asset = Data(
    name="churn_train",
    version="1",
    type=AssetTypes.URI_FOLDER,
    path="azureml://datastores/teamblob/paths/churn/train/v1/",
    description="Churn synthetic dataset for lab",
    tags={"purpose": "lab", "sensitivity": "synthetic"},
)

# Chỉ ghi vào Azure ML LAB khi được phép:
# registered = ml_client.data.create_or_update(training_asset)
~~~

**Điều kiện:** datastore và folder nguồn tồn tại, người tạo asset có quyền thao tác phù hợp, compute identity có quyền đọc dữ liệu. Đăng ký asset **không tự copy** nội dung của một URI datastore và không tự bảo vệ files khỏi bị ghi đè.

### CLI data asset YAML

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/data.schema.json
name: churn_train
version: 1
type: uri_folder
description: Synthetic churn training data for lab
path: azureml://datastores/teamblob/paths/churn/train/v1/
tags:
  purpose: lab
~~~

~~~bash
# TẠO DATA ASSET - chỉ trên LAB với file churn-data.yml được chuẩn bị.
az ml data create --file churn-data.yml \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab"
~~~

### Khi nào dùng URI_FILE?

Nếu data chỉ có một **train.csv**, type **uri_file** và path tới file là phù hợp. Nếu script kỳ vọng một folder rồi tự nối **train.csv**, hãy dùng **uri_folder**. Kiểu input phải khớp với logic trong code.

## 25. MLTable để định nghĩa cách đọc dữ liệu bảng

MLTable là kiểu data asset mô tả dữ liệu tabular bằng một file định nghĩa, có thể chứa paths và rules đọc/transformation.

~~~text
churn-mltable/
  MLTable
  data/
    part-0001.parquet
    part-0002.parquet
~~~

Ví dụ **minh họa cấu trúc**:

~~~yaml
paths:
  - pattern: ./data/*.parquet
transformations:
  - read_parquet:
      include_path_column: false
~~~

**Cú pháp/biến thể transformation phải được xác minh với MLTable schema và package version thực**. Không chỉ đổi extension hoặc đặt type=mltable cho một CSV tùy ý. File MLTable, dữ liệu nguồn, quyền truy cập và versioned path vẫn phải tồn tại.

### So sánh chọn kiểu

| Nhu cầu | Kiểu tham khảo |
|---|---|
| Một file CSV | uri_file |
| Thư mục ảnh, nhiều files | uri_folder |
| Tabular data có khai báo paths/reader | mltable |
| Query trực tiếp một database | Code + connector/identity, có chiến lược snapshot riêng |

## 26. Chuẩn bị dữ liệu giả cho bài lab

Tạo file **train.csv** trong thư mục dữ liệu lab, không sử dụng thông tin khách hàng thật:

~~~csv
age,monthly_spend,support_tickets,churned
23,150,0,0
47,35,4,1
32,200,1,0
58,40,5,1
29,125,1,0
43,65,3,1
36,180,0,0
55,50,4,1
26,220,0,0
51,45,5,1
31,175,1,0
48,60,3,1
~~~

Các cột **age, monthly_spend, support_tickets** là features; **churned** là label. **12 dòng không đủ** để kiểm chứng chất lượng ML production: chỉ dùng để chứng minh luồng input → train → output.

### Bảo vệ tập dữ liệu thật

Tập dữ liệu khách hàng từ SQL/Cosmos DB phải được phân loại PII, kiểm tra cơ sở pháp lý/consent, giới hạn truy cập, retention và chất lượng label. Data scientist có quyền đọc bản đã anonymize không nhất thiết được quyền đọc raw table.

## 27. Mã train.py đơn giản

File **src/train.py** trong dự án lab:

~~~python
import argparse
import json
import os

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

parser = argparse.ArgumentParser()
parser.add_argument("--data-folder", required=True)
parser.add_argument("--output-dir", required=True)
args = parser.parse_args()

df = pd.read_csv(os.path.join(args.data_folder, "train.csv"))
features = ["age", "monthly_spend", "support_tickets"]
target = "churned"

if any(column not in df.columns for column in features + [target]):
    raise ValueError("Missing training columns")

df = df.dropna(subset=features + [target])
if len(df) < 10 or df[target].nunique() < 2:
    raise ValueError("Dataset too small or one-class only")

x_train, x_test, y_train, y_test = train_test_split(
    df[features], df[target],
    test_size=0.25, stratify=df[target], random_state=42,
)

model = LogisticRegression(max_iter=500, random_state=42)
model.fit(x_train, y_train)
accuracy = float(accuracy_score(y_test, model.predict(x_test)))

os.makedirs(args.output_dir, exist_ok=True)
joblib.dump(model, os.path.join(args.output_dir, "model.joblib"))
with open(
    os.path.join(args.output_dir, "metrics.json"),
    "w", encoding="utf-8",
) as file:
    json.dump({"test_accuracy": accuracy}, file, indent=2)

print({"rows": len(df), "test_accuracy": accuracy})
~~~

**Cảnh báo:** accuracy trên 12 dòng không có ý nghĩa đánh giá mô hình thực; cần validation/cross-validation, fairness, drift và tập test độc lập. **Không deserialize file joblib/pickle từ nguồn chưa tin cậy**. Các ví dụ chỉ tạo artifacts trong job lab.

## 28. Khai báo environment cho command job

File **conda.yml** ở dự án lab:

~~~yaml
name: churn-sklearn-lab
dependencies:
  - python=3.10
  - pip
  - pip:
      - pandas==2.2.3
      - scikit-learn==1.5.2
      - joblib==1.4.2
~~~

Đây là phiên bản minh họa, không phải bộ dependencies mới nhất/an toàn nhất. Cần kiểm tra CVEs, base image và compatibility trước production.

~~~python
from azure.ai.ml.entities import Environment

environment = Environment(
    name="sklearn-churn-lab",
    version="1",
    image="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest",
    conda_file="./conda.yml",
)

# TẠO/CẬP NHẬT ENVIRONMENT Ở WORKSPACE LAB nếu được phép:
# ml_client.environments.create_or_update(environment)
~~~

**Image latest không ổn định**; chọn digest/tag được tổ chức phê duyệt và quét bảo mật để đảm bảo reproducibility. Build image cần network/registry rights.

## 29. Tạo định nghĩa command job bằng SDK v2

Ví dụ dưới đây kết nối **src/train.py**, **churn_train:1**, environment đã đăng ký và cluster lab:

~~~python
from azure.ai.ml import Input, Output, command
from azure.ai.ml.constants import AssetTypes

training_input = Input(
    type=AssetTypes.URI_FOLDER,
    path="azureml:churn_train:1",
    mode="ro_mount",
)
model_output = Output(
    type=AssetTypes.URI_FOLDER,
    mode="rw_mount",
)

job = command(
    code="./src",
    command=(
        "python train.py "
        "--data-folder ${{inputs.training_data}} "
        "--output-dir ${{outputs.model_output}}"
    ),
    inputs={"training_data": training_input},
    outputs={"model_output": model_output},
    compute="cpu-churn-lab",
    environment="azureml:sklearn-churn-lab:1",
    experiment_name="churn-synthetic-lab",
    display_name="train-churn-v1",
)

# CHẠY JOB TRÊN AZURE VÀ CÓ THỂ PHÁT SINH PHÍ:
# submitted = ml_client.jobs.create_or_update(job)
# print(submitted.name)
~~~

**Điều kiện trước khi bỏ comment submit:**

1. Thư mục **src** có train.py.
2. Tài khoản Azure có quyền submit job.
3. Compute cluster, environment và data asset đúng tên/version đã tồn tại.
4. Data asset folder có train.csv.
5. Identity của job đọc được Blob/ADLS input và ghi được output.
6. Container image có thể được pull, environment build thành công.
7. GPU không cần thiết cho ví dụ scikit-learn nhỏ; chọn cluster CPU để kiểm soát chi phí.

**Không đổi placeholder command path thành đường dẫn máy local**: expressions của job engine được giải quyết tại runtime.

## 30. Theo dõi trạng thái, logs và output job

Sau khi được phép submit job trong lab:

~~~bash
az ml job show \
  --name "<JOB_NAME>" \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o json
~~~

~~~python
details = ml_client.jobs.get("<JOB_NAME>")
print({"name": details.name, "status": details.status})
~~~

Trong Studio, kiểm tra:

- Job queued/preparing/running/completed/failed.
- Compute allocation/provisioning logs.
- Environment image build/dependency errors.
- Input mount/download diagnostics.
- Script stdout/stderr, metrics.json.
- Output artifact path và file model.joblib.

**Job Completed không đồng nghĩa mô hình đạt chuẩn production**. Nó chỉ chứng minh quá trình kỹ thuật kết thúc thành công theo job runner; accuracy, tính công bằng, bảo mật và độ tin cậy cần được đánh giá riêng.

## 31. Phân biệt job, experiment, pipeline và model

| Khái niệm | Mục đích |
|---|---|
| **Job** | Một lần thực thi có code, env, compute, inputs/outputs |
| **Experiment** | Nhóm runs/jobs để theo dõi thử nghiệm |
| **Pipeline job** | Điều phối nhiều bước/jobs theo dependency |
| **Model asset** | Model artifacts có name/version để quản lý |
| **Online endpoint** | Phục vụ inference request/response theo loại endpoint |
| **Batch endpoint** | Chạy inference theo batch theo khả năng dịch vụ |

Một **data asset** là input; **model asset** là output được quản lý sau huấn luyện. Đăng ký model không tự triển khai endpoint, và có endpoint không tự khiến model được giám sát drift/fairness.

## 32. Model lineage và tái lập

Mỗi job quan trọng nên ghi:

~~~text
Data version + immutable storage snapshot
               |
               v
Code commit + job parameters
               |
               v
Environment version/image digest
               |
               v
Compute configuration/region
               |
               v
Job ID + logs + metrics + artifacts
               |
               v
Evaluation decision / model registration
~~~

**Version của data asset không tự khiến bytes ở storage bất biến.** Nếu file được ghi đè dưới cùng đường dẫn, hai lần dùng churn_train:1 có thể đọc dữ liệu khác. Kết hợp immutable paths/snapshots, retention, hashes và Azure storage access policy để audit.

Ngay cả khi đặt random_state, GPU kernels, versions, multithreading và algorithms có thể vẫn không tuyệt đối deterministic. Reproducibility cần kiểm nghiệm, không chỉ đặt seed.

## 33. Compute scheduling và chia sẻ tài nguyên

Một nhóm có thể thiết kế:

~~~text
Development EDA       -> CPU compute instance
Daily CPU training    -> AML compute cluster min=0
Deep learning         -> GPU cluster có quota
Batch model scoring   -> cluster/endpoint phù hợp
Online inference      -> managed online endpoint hoặc target tương ứng
~~~

Nếu để Spark-like preprocessing job và GPU training cùng tranh capacity không hợp lý, queue time, chi phí và quyền có thể khó kiểm soát. Tách compute khi workload có nhu cầu GPU/CPU, SLO hoặc data permissions khác biệt; không mặc định tất cả jobs vào một cluster.

### Các chỉ số để điều chỉnh cluster

- Queue wait time và node provisioning time.
- Node CPU/GPU utilization.
- Job success/failure/retry rates.
- Total VM hours và storage/network cost.
- Spot eviction/checkpoint rate.
- Thời gian idle chạy compute instance.

## 34. Quota và lỗi thiếu compute

Một job có thể không khởi chạy dù code hoàn toàn hợp lệ:

- VM family không có trong region.
- GPU/vCPU quota chưa đủ.
- Compute cluster max nodes đã đạt.
- Không còn capacity spot/dedicated tại thời điểm yêu cầu.
- Network không truy cập storage/ACR.
- Identity thiếu quyền tạo/pull/đọc tài nguyên.

### Quy trình

1. Xác nhận workspace region và VM SKU.
2. Đọc compute status, job scheduling errors.
3. Kiểm tra Azure ML/VM family quota và per-region limits.
4. Kiểm tra autoscale min/max và node allocation.
5. Kiểm tra quyền storage/ACR nếu job fail ở preparation.
6. Yêu cầu quota tăng theo quy trình nếu thực sự thiếu.
7. Đánh giá SKU khác, region khác hoặc phân lịch nếu phù hợp.

**Không giải quyết lỗi authentication bằng cách tăng GPU quota**, hoặc sửa job script để che lỗi compute provisioning.

## 35. Quản lý Microsoft Entra ID và managed identity

Trong Azure ML, ba danh tính có thể khác nhau:

1. **Developer identity:** người dùng đăng nhập Studio/CLI để tạo jobs/assets.
2. **Compute/workload identity:** danh tính mà job sử dụng khi truy cập storage/Key Vault/registry theo cấu hình.
3. **Source identity:** service principal/credential của datastore hoặc external source nếu kết nối không dùng identity của job.

~~~text
Developer (Microsoft Entra ID)
       |
       | Workspace RBAC: submit job
       v
Azure ML Workspace
       |
       | Scheduler starts job
       v
AML Compute identity
       |
       +-- Storage Blob Data Reader -> input data
       +-- Storage Blob Data Contributor -> outputs nếu cần
       +-- ACR pull rights -> environment image khi cần
       +-- Key Vault secrets read -> chỉ khi thực sự cần
~~~

### Least privilege thực tế

- Người phát triển không cần Owner subscription để chạy mọi job.
- Job đọc dữ liệu không cần Storage Blob Data Owner cho toàn storage account.
- Pipeline chỉ được đọc đúng container/dataset đã duyệt.
- Tách identity dev/test/prod, tránh workspace lab truy cập storage production.
- Ghi lại resource IDs và principal IDs trong tài liệu vận hành, không ghi tokens/passwords.
- Nếu dùng user identity passthrough hoặc credential-based datastore, xem lại principal thực tế mà data access dùng.

**Azure RBAC management plane không phải là cách duy nhất quyết định data access.** Azure Storage có vai trò data plane/ACL, Key Vault có cơ chế truy cập riêng và các nguồn SQL yêu cầu quyền dữ liệu phù hợp.

## 36. Datastore credentials và quản trị secrets

Azure ML datastore có thể dùng **identity-based access** hoặc các cơ chế credentials khác tùy loại datastore và SDK/feature. Nên chọn cách ít phụ thuộc secrets tĩnh khi phù hợp.

| Cách truy cập | Ưu điểm | Rủi ro/điểm cần kiểm tra |
|---|---|---|
| **Managed identity / identity-based** | Không cần nhúng account key vào script | Role/ACL, auth flow, runtime identity, network |
| **Service principal** | Có thể dùng cho automation | Certificate/secret lifetime, least privilege, rotation |
| **Account key/SAS** | Có thể tương thích nhiều workflows | Lộ secret, quyền quá rộng, expiration, rotation |
| **External source credential** | Kết nối được nguồn được hỗ trợ | Ownership, change control và log redaction |

### Điều không nên làm

- Không đưa Storage account keys trong job YAML hoặc notebook cell output.
- Không commit connection string/SAS vào Git.
- Không cho Compute Instance quyền đọc tất cả containers chỉ vì tiện học.
- Không dùng SAS hết hạn sau vài ngày cho pipeline production dài hạn mà không thiết kế renewal.
- Không in URI chứa SAS query parameters vào logs/artifacts.

### Key Vault đóng vai trò gì?

Key Vault có thể quản lý secrets của hạ tầng và ứng dụng, nhưng **không có nghĩa tạo workspace sẽ tự cấp quyền Key Vault secrets cho mọi người dùng**. Dùng managed identities và role/permissions đúng phạm vi, có rotation và audit.

## 37. Network isolation và private endpoints

Một Azure ML workspace có thể làm việc với Storage, Key Vault, ACR, Compute và endpoints qua mạng Azure. Đối với doanh nghiệp yêu cầu kết nối riêng:

~~~text
Developer / CI
      |
      v
Azure ML workspace control/API
      |
      v
Managed network / approved VNet path
      |
      +--> Compute instance / cluster
      |          |
      |          +--> Storage Private Endpoint
      |          +--> ACR access
      |          +--> Key Vault access
      |
      +--> Other approved destinations
~~~

**Managed virtual network/isolation mode**, private endpoints, outbound rules và workspace public access là những lựa chọn cần thiết kế phù hợp, không phải mặc định mọi workspace đã hoàn toàn private.

### Cần kiểm tra

1. Workspace có network isolation mode nào?
2. Compute có internet outbound không, và có thực sự cần không?
3. Storage, ACR, Key Vault có firewall/private endpoints riêng không?
4. Private DNS/FQDN được phân giải đúng từ compute nodes chưa?
5. Container image/conda packages đến từ nguồn nào?
6. Script có cần truy cập PyPI/Git/external model registry không?
7. Azure ML Studio/API có truy cập được từ mạng người dùng/CI không?
8. Region/data residency của workspace và storage có phù hợp policy không?

### Hai lỗi phổ biến

**Lỗi 1: workspace private nhưng storage public.** Không thể kết luận dữ liệu được cách ly hoàn toàn chỉ vì Azure ML workspace có Private Link.

**Lỗi 2: compute private nhưng không pull được image.** Không nên tắt firewall toàn cục ngay; xác định cần private registry route, approved outbound hoặc prebuilt image.

### Khi sửa lỗi network

Phân biệt **DNS → TCP/route → TLS → Identity/RBAC → Service API**. Nếu thấy Storage 403, có thể do firewall hoặc thiếu quyền; cần xem diagnostics và principal, không phải luôn là sai access key.

## 38. Workspace và compute trong nhiều môi trường

Nên tách rõ mục đích của các workspace:

~~~text
Resource group ml-dev
  Workspace aml-dev
  Compute dev-cluster (CPU, low max nodes)
  Data synthetic/approved sample

Resource group ml-test
  Workspace aml-test
  Compute test-cluster
  Data sanitized staging snapshot

Resource group ml-prod
  Workspace aml-prod
  Compute prod-cluster
  Data production với quyền hẹp
~~~

### Tại sao tách?

- Tránh chạy notebook khám phá trên dữ liệu nhạy cảm.
- Phân chia RBAC, network và compliance.
- Ngăn job thử nghiệm chiếm GPU quota production.
- Theo dõi chi phí theo team/môi trường.
- Tăng khả năng audit và change control.

**Tách workspace chưa đủ** nếu tất cả cùng dùng một storage account/container và cùng quyền ghi rộng. Cần kiểm soát data boundaries ở storage và identity.

### Chia sẻ assets giữa workspaces

Azure ML có khả năng quản lý assets qua workspace/registry theo loại tài nguyên và tính năng. Nhưng **đăng ký một data asset trong workspace A không có nghĩa workspace B tự có quyền đọc bytes ở storage**. Cần xác minh support, identity, sharing policy và data residency trước.

## 39. Lựa chọn nguồn dữ liệu cho huấn luyện

Một tổ chức có dữ liệu ở Azure SQL, Cosmos DB, Blob/ADLS, Event Hubs và Microsoft Fabric.

| Nguồn | Đường vào Azure ML phù hợp để đánh giá | Cần lưu ý |
|---|---|---|
| **Azure SQL Database** | Export/snapshot to Blob/ADLS, job code connector | Transactional load, snapshot consistency, SQL permissions |
| **Azure Cosmos DB** | Export/snapshot hoặc connector/code được hỗ trợ | RU/s, partition key, data freshness và consent |
| **Azure Blob/ADLS** | Datastore + URI_FILE/URI_FOLDER/MLTable | RBAC/ACL, private endpoints, versioned paths |
| **Azure Event Hubs** | Streaming pipeline tới curated storage trước train | Event ordering, consumer lag, dedup, retention |
| **Microsoft Fabric/OneLake** | Export/approved integration hoặc đường đọc được hỗ trợ | Data permissions, copy vs shortcut, file formats, residency |
| **On-premises data** | Secure data pipeline/gateway tới staging storage | Compliance, PII, network/firewall, lineage |

### Không train trực tiếp trên OLTP nóng theo mặc định

Một tác vụ huấn luyện có thể quét hàng triệu rows, gây ảnh hưởng giao dịch thanh toán. Thường nên snapshot/curate dữ liệu sang ADLS/Blob hoặc kho phân tích, version rồi cho Azure ML đọc. Việc snapshot phải giữ **đúng thời điểm dữ liệu/label** để tránh data leakage.

## 40. Data quality, leakage và reproducibility

Một job có thể chạy thành công nhưng huấn luyện trên dữ liệu sai:

- Nhãn churn được tính sau thời điểm prediction.
- Features chứa cột trực tiếp tiết lộ kết quả tương lai.
- Train/test cùng customer records trùng nhau.
- Số lượng missing/invalid rows tăng bất thường.
- Dữ liệu của tenant này vô tình trộn vào tenant khác.
- Dữ liệu nguồn thay đổi dù data asset version không đổi.

### Các bước bắt buộc trước khi training

1. Kiểm tra schema, dtype, null-rate và ranges.
2. Kiểm tra duplicates và sample identifiers.
3. Xác định thời gian feature/label hợp lệ.
4. Tách train/validation/test đúng đơn vị như khách hàng/thời gian.
5. Kiểm tra class imbalance và fairness theo nhóm khi phù hợp.
6. Ghi row counts, dataset hashes/version và data quality metrics.
7. Quarantine các rows lỗi thay vì xóa im lặng.

**Không tăng compute để giải quyết label leakage.** Nếu mô hình học được thông tin tương lai, accuracy cao vẫn không thể tin khi suy luận trên dữ liệu thật.

## 41. Theo dõi metrics, logs và khả năng quan sát

| Thành phần | Metric/log | Dùng để |
|---|---|---|
| **Workspace** | Job counts/status, asset changes, access events | Theo dõi hoạt động và thay đổi |
| **Compute instance** | Running hours, CPU/RAM/GPU, idle time | Tối ưu tài nguyên dev |
| **Cluster** | Node allocation, queue time, failures, utilization | Sizing/quota |
| **Environment** | Image build/pull errors, dependency issues | Chẩn đoán job chuẩn bị lỗi |
| **Data** | Read failures, mount time, data size, schema quality | Phát hiện storage/format |
| **Training** | Loss, accuracy, AUC, elapsed time, checkpoints | Đánh giá mô hình |
| **Cost** | VM hours, storage/egress, network/logs | TCO |
| **Security** | Identity failures, anomalous access, secret exposure | Incident response |

Không phải tất cả là **Azure Monitor metrics mặc định**. Một số như data quality/label drift/checkpoint rate cần custom logging trong code hoặc hệ thống MLOps phù hợp.

### Logging an toàn

~~~json
{
  "experiment": "churn-synthetic-lab",
  "dataAsset": "churn_train:1",
  "environment": "sklearn-churn-lab:1",
  "compute": "cpu-churn-lab",
  "rows": 12000,
  "trainDurationSeconds": 42,
  "testAccuracy": 0.81
}
~~~

Đây là **log giả định minh họa** và không phải kết quả của bộ dữ liệu 12 dòng. Không in raw customer rows, access tokens, SAS URLs hoặc toàn bộ Key Vault responses vào logs.

### Có nên chỉ xem accuracy?

Không. Với dự đoán churn có thể cần precision/recall, calibration, AUC, lỗi theo nhóm khách hàng và business impact. Một mô hình đạt accuracy 90% trên tập mất cân bằng nghiêm trọng có thể vẫn không phát hiện được nhóm churn hiếm.

## 42. Cost: đâu là khoản tiền chính?

Một Azure ML solution có thể tốn chi phí ở:

- **Compute instance/cluster VM hours** (CPU/GPU, node count, idle).
- **Storage** của datasets, model outputs, workspace artifacts.
- **Container Registry/image build**, theo resource/config.
- **Network/Private Endpoint/egress** khi truyền dữ liệu.
- **Monitoring/Log Analytics/Application Insights** theo retention và volume.
- **Managed online endpoints** hoặc batch inference infrastructure.
- **External Azure sources** như SQL/Cosmos DB/ADLS và data processing.

### Ví dụ tính compute sơ bộ

Giả sử một job huấn luyện dùng:

~~~text
Cluster CPU 2 nodes
Mỗi node hoạt động 3 giờ cho job

Tổng VM-node-hours:
  2 x 3 = 6 node-hours

Chi phí compute sơ bộ:
  6 x đơn giá node/giờ ở region tương ứng
~~~

Chưa tính environment build, node provisioning, data transfer, storage/logs và các khoản dịch vụ liên quan. Số tiền không được ghi cứng vì Azure prices thay đổi theo region/SKU/offer.

### Compute instance quên stop

~~~text
Compute instance chạy 24 giờ/ngày
Nhưng developer chỉ dùng 2 giờ/ngày

Giờ compute không có hoạt động trực tiếp:
  22 giờ/ngày (minh họa)
~~~

Nếu instance vẫn Running, chi phí compute có thể tiếp tục. Thiết lập shutdown schedule/idle policy khi phù hợp và đo thực tế; **không xóa instance trước khi giữ lại code/assets cần thiết**.

### Các cách tối ưu

1. Min cluster nodes = 0 khi phù hợp với cold start.
2. Đặt max nodes/quotas và budgets.
3. Stop compute instances, hạn chế GPU notebook.
4. Chọn Spot cho workloads có checkpoint/retry.
5. Tối ưu input data size và tránh copy lớn qua region.
6. Cache environment images hợp lý, pin dependencies.
7. Gắn tags cost-center/team/project.
8. Dùng Azure Cost Management, budgets và alerts.

**Không tối ưu số tiền bằng cách xóa outputs/metadata cần audit**. Data/model lifecycle và retention là quyết định nghiệp vụ.

## 43. Lab A: xác minh workspace, compute và datastore

**Mục tiêu:** hiểu tài nguyên hiện có bằng công cụ **read-only**. Không tạo VM, không thay chính sách, không chạy training.

### Chuẩn bị

- Subscription/resource group có Azure ML workspace lab.
- Developer identity có quyền đọc workspace.
- Azure CLI v2 extension ml hoặc Python SDK phù hợp.
- Kế hoạch không ghi dữ liệu production ra ngoài.

### Các bước

1. Xác nhận subscription bằng **az account show**.
2. Dùng **az ml workspace show** đọc workspace name/location.
3. Dùng **az ml compute list** phân biệt compute instance và cluster.
4. Dùng **az ml datastore list** xem datastore đã đăng ký.
5. Dùng **az ml data list** xem assets, tên và versions.
6. Chọn một asset giả, dùng **az ml data show** kiểm tra URI/type.
7. Đối chiếu data asset path với datastore và storage owner.
8. Xem jobs đã chạy mà không tải về raw customer data.
9. Ghi lại những thiếu sót: quota, identity, network, missing dataset.

### Tiêu chí PASS

| Hạng mục | Kỳ vọng |
|---|---|
| Workspace | Đúng subscription/resource group/location |
| Compute | Phân biệt instance và cluster, biết running/idle |
| Data asset | Biết name, version, type, source path |
| Datastore | Biết storage source, loại credential/auth |
| Quyền | Không tự mở rộng RBAC khi chưa có lý do |
| Network | Không thử bypass firewall/Private Endpoint |
| Chi phí | Không tạo VM/job ngoài ý định |

## 44. Lab B: huấn luyện dữ liệu tổng hợp trên CPU cluster

**Mục tiêu:** tự ghép workspace, compute, data asset và environment thành một command job. Những bước **tạo resource/chạy job có thể phát sinh phí**, chỉ thực hiện trong workspace lab được phê duyệt.

### Chuẩn bị

1. Có quyền tạo asset/job/compute hoặc được người quản trị chuẩn bị trước.
2. Tài khoản Azure ML và storage lab được cấu hình đúng.
3. Có chi phí dự kiến, max nodes giới hạn, idle scale-down.
4. Có dataset tổng hợp **train.csv** mục 26.
5. Có mã **src/train.py** mục 27 và **conda.yml** mục 28.
6. Có quyền đọc source và ghi job artifacts.

### Quy trình

1. Tạo hoặc xác nhận **cpu-churn-lab** (CPU cluster min 0, max 2) sau khi kiểm tra quota.
2. Upload train.csv lên thư mục datastore lab được phép hoặc tạo data asset theo luồng local upload chính thức.
3. Đăng ký **churn_train:1** kiểu URI_FOLDER tới đúng folder chứa train.csv.
4. Đăng ký **sklearn-churn-lab:1** environment với dependencies được kiểm thử.
5. Tạo command job ở mục 29 và submit bằng SDK/Studio.
6. Kiểm tra job đi qua trạng thái Queued/Preparing/Running.
7. Xác minh file **model.joblib** và **metrics.json** trong job outputs.
8. Ghi job ID, versions và thử cùng data/env trên lần chạy thứ hai.
9. Không gọi model là production-ready chỉ vì script trả accuracy.
10. Dừng compute instance cá nhân; đảm bảo cluster scale về 0 khi idle và theo dõi chi phí.

### Các kiểm tra lỗi chủ động

- Cố tình chọn asset version không tồn tại **chỉ bằng config ở lab**, quan sát lỗi lookup.
- Thử một input folder thiếu train.csv để phân biệt job setup vs script error.
- Kiểm tra thiếu quyền storage bằng một identity lab hạn chế **nếu được phê duyệt**; không sửa quyền production.
- Không cần load test GPU, tăng quota hay đụng dữ liệu khách hàng để hoàn thành bài.

### Nghiệm thu

| Tiêu chí | PASS khi |
|---|---|
| Scope | Chỉ tài nguyên lab |
| Compute | CPU SKU phù hợp, max nodes giới hạn |
| Input | Data asset có version rõ và đúng file |
| Environment | Image/dependencies được xác định |
| Job | Chạy xong, có logs, metrics và model artifact |
| Reproducibility | Có job ID/data version/code/env |
| Security | Không lộ secret, permissions đúng |
| Billing | Biết VM hours, storage và chi phí liên quan |

## 45. Lab C: thử read-only đối với data asset

**Mục tiêu:** hiểu metadata không tương đương quyền đọc bytes.

~~~text
Developer: xem data asset churn_train:1 thành công
            |
            v
Compute job: cố đọc train.csv
            |
          /   \
    Cho phép   Không có quyền
       |           |
       v           v
    Train OK     403/AccessDenied
~~~

Các bước:

1. Xem data asset metadata, ghi lại datastore/URI và type.
2. Xác định identity nào đọc storage trong job path.
3. Kiểm tra **Storage Blob Data Reader/ACL** theo phạm vi cần thiết.
4. Kiểm tra storage firewall/private endpoint/DNS.
5. Chạy thử bằng test job được phê duyệt.
6. Khi thất bại, xem Storage diagnostics và Azure ML job logs để phân loại auth/network.

**Không phản ứng bằng cách đưa storage account key vào Python file hoặc cấp Owner subscription.** Sửa đúng principal và đúng phạm vi quyền.

## 46. Case study: dự đoán churn cho nền tảng SaaS

Một SaaS chạy trên Azure có:

- Azure SQL Database lưu giao dịch và thông tin đăng ký.
- Azure Cosmos DB lưu tương tác người dùng.
- ADLS Gen2 chứa lịch sử dữ liệu đã qua xử lý.
- 8 data scientists cần notebooks phát triển.
- Training chạy mỗi đêm, thỉnh thoảng cần GPU cho NLP.
- Data privacy yêu cầu không đưa PII vào log và không dùng dữ liệu production cho thử nghiệm tùy tiện.
- API dự đoán churn muốn p95 latency thấp nhưng bài học hiện chỉ tập trung setup training.
- Nhóm tài chính cần phân bổ chi phí theo team/project.

### Nhiệm vụ

1. Chọn workspace/resource group cho dev/test/prod và giải thích lý do tách.
2. Xác định compute instance nào cần cho 8 nhà phát triển; làm sao tránh idle VM spend?
3. Thiết kế CPU training cluster min/max nodes.
4. Quyết định khi nào cần một GPU cluster tách riêng.
5. Thiết kế ADLS datastore và các data asset **churn_train:1**, **churn_eval:1**.
6. Chọn URI_FOLDER, URI_FILE hay MLTABLE cho các nguồn khác nhau.
7. Mô tả cách ghi version/immutable source snapshot để tái lập jobs.
8. Chọn environment/dependencies và quản lý image security.
9. Thiết kế identity đọc storage và ghi outputs theo least privilege.
10. Giải thích vì sao Azure ML job submit thành công vẫn có thể fail vì Storage 403.
11. Vẽ đường network private tới ADLS, ACR và Key Vault.
12. Xây job/pipeline để huấn luyện rồi đánh giá trên dữ liệu độc lập.
13. Xác định metric ngoài accuracy cần xem cho churn model.
14. Thiết kế budget, tags, quota, timeout và Spot checkpoint.
15. Phân biệt model asset registration với online endpoint deployment.

### Hướng giải

~~~text
Azure SQL / Cosmos DB
       |
       v
Curated + privacy-approved data in ADLS
       |
       v
Datastore: team-adls
       |
       v
Data assets:
  churn_train:1
  churn_eval:1
       |
       +-- sklearn environment:1
       +-- CPU training cluster (min 0)
       |
       v
Azure ML command/pipeline job
       |
       +--> metrics + model artifact
       +--> evaluation/quality/security checks
       |
       v
Model registration / approval
       |
       v
Separate inference deployment process
~~~

Đây là **kiến trúc tham khảo**. Nếu dữ liệu phải được xử lý ở một region hoặc workspace có yêu cầu private networking, việc chọn datastore, compute và identity phải tuân thủ những ràng buộc đó trước khi huấn luyện.

## 47. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không mở được Azure ML workspace | Sai tenant/subscription, thiếu RBAC | Azure portal/resource ID, az account |
| Compute cluster không cấp node | VM quota, SKU unavailable, policy/network | Region, quotas, compute status |
| Notebook chậm khi idle lâu | Compute instance stopped hoặc môi trường chưa sẵn | Instance state/startup logs |
| Job Queued quá lâu | Compute max nodes, quota hoặc thiếu capacity | Queue/node allocation/cluster config |
| Environment build fail | Image/conda dependency/ACR access | Build logs, registry/network |
| Data asset hiển thị nhưng job báo 403 | Job identity không có storage permissions | Principal, RBAC/ACL/firewall |
| Input mount timeout | Private DNS/network hoặc storage access | Compute path, endpoints, URI |
| Script FileNotFoundError | URI_FILE vs URI_FOLDER, thiếu train.csv | Input mode/path và code |
| Job Completed nhưng không có model | Script ghi sai output path | Job outputs, local vs mounted dirs |
| Metrics bất thường quá cao | Label leakage hoặc train/test overlap | Data validation và splits |
| Cùng data asset version cho dữ liệu khác nhau | Storage files bị ghi đè | Snapshot immutability và hashes |
| Chi phí GPU tăng cao | Compute instance quên stop hoặc cluster min >0 | VM hours, auto-shutdown |
| Job fail khi truy cập PyPI | Network isolation/outbound rules | Build logs và policy |
| Không tìm thấy CLI command | Extension ml thiếu/sai version | az extension list và tài liệu CLI |
| Cannot read Key Vault secret | Key Vault data-plane RBAC chưa đúng | Managed identity, vault access |
| Inference API không hoạt động | Model chưa deploy hoặc endpoint auth/network | Endpoint settings khác job lifecycle |

### Quy trình điều tra sáu bước

1. **Scope:** đúng tenant, subscription, resource group, workspace?
2. **Identity:** user/job/compute/data principal là ai?
3. **Compute:** type, VM size, quota, scheduler và node status?
4. **Data:** asset version/path, mode và bytes có thực sự tồn tại?
5. **Environment:** image, dependencies, ACR/network, code snapshot?
6. **Outcome:** job logs, metrics, artifacts, business data quality và cost?

Không xóa workspace/compute/data asset chỉ vì job đầu tiên báo lỗi. Chẩn đoán đúng lớp và giữ lại logs để điều tra.

## 48. Checklist trước production

| Nhóm | Câu hỏi cần đạt |
|---|---|
| Workspace | Môi trường và resource ownership rõ ràng? |
| Subscription | Region, policy, quota, tags và ngân sách được phê duyệt? |
| Identity | Entra RBAC và data-plane permissions tối thiểu? |
| Network | Managed network/VNet, DNS, Storage/ACR/Key Vault paths hợp lệ? |
| Compute instance | Có owner, schedule stop và không giữ data local duy nhất? |
| Cluster | Min/max nodes, SKU/quota, scale-down và concurrency được đo? |
| GPU/Spot | Framework compatibility, checkpoint và preemption handling? |
| Datastore | Storage location, credential mode và lifecycle rõ? |
| Data assets | Name/version/type/path và ownership rõ? |
| Data integrity | Source snapshot bất biến và có quality checks? |
| MLTable/URI | Input type khớp với cách đọc của script? |
| Environment | Image/dependencies pin và quét security? |
| Job | Code commit, params, inputs/outputs được ghi lại? |
| Training evaluation | Không leakage, có validation/test độc lập? |
| Model | Registry/approval tách biệt endpoint deployment? |
| Monitoring | Logs, metrics, queue time, failures và data quality alerts? |
| Cost | VM hours, storage, ACR, network và logs được đo? |
| DR/retention | Data snapshots, artifacts, code và restore plan tồn tại? |
| MLOps | CI/CD, tests, approvals, rollback và owner của models rõ? |
| Security | Không chứa PII/secrets trong job logs/artifacts hoặc model output? |

## 49. Câu hỏi tự kiểm tra

1. Azure ML workspace khác resource group và VM như thế nào?
2. Các dịch vụ Azure nào thường liên kết với workspace?
3. Vì sao tạo workspace không đồng nghĩa GPU đang chạy?
4. Compute instance phù hợp interactive development hay batch job queue?
5. AML compute cluster min_instances=0 đem lại lợi ích và đánh đổi nào?
6. Khi nào Spot/low-priority compute phù hợp?
7. Vì sao GPU có thể không giúp bài toán scikit-learn nhỏ?
8. Datastore và data asset khác nhau về vai trò và quyền như thế nào?
9. Data asset version có tự bảo đảm bytes tại storage bất biến không?
10. URI_FILE và URI_FOLDER khác nhau ở cách script nhận đường dẫn gì?
11. MLTable định nghĩa gì và cần những files nào?
12. Khi nào download, mount và direct access phù hợp?
13. Vì sao data asset hiển thị trong Studio nhưng job vẫn có thể gặp Storage 403?
14. Những thành phần nào tạo nên command job v2?
15. Environment có vai trò gì trong khả năng tái lập?
16. Vì sao cần pin container image/dependencies nhưng vẫn phải vá CVEs?
17. Azure ML v1 Dataset và v2 data asset có nên dùng lẫn cú pháp không?
18. Câu lệnh az ml compute list có làm phát sinh compute VM mới không?
19. Câu lệnh az ml compute create có thể thay tài nguyên nào?
20. Tại sao job name, code commit và data version cần được ghi?
21. Vì sao Completed job chưa chứng minh model production-ready?
22. Data leakage và train/test overlap có thể làm sai metric thế nào?
23. Vì sao nên export snapshot từ OLTP trước khi train scan lớn?
24. RBAC quản trị workspace có tự cấp quyền đọc ADLS data không?
25. Managed identity khác storage account key về quản lý bí mật thế nào?
26. Azure ML private networking cần xem những resource dependencies nào?
27. Lỗi ACR pull có thể bắt nguồn từ network hay identity?
28. Một compute instance Running nhưng không có notebook hoạt động có thể tốn tiền không?
29. Chọn CPU cluster 2 nodes x 3 giờ tương ứng bao nhiêu node-hours?
30. Vì sao chỉ nhìn Azure ML workspace billing không phản ánh đầy đủ TCO?
31. Model registration và deployment endpoint khác nhau thế nào?
32. Những chỉ số nào nên xem khi job Queued quá lâu?
33. Nên phân chia workspace dev/test/prod theo nguyên tắc gì?
34. Một training job tái lập cần những metadata/artifacts nào?
35. Ba bước quan trọng nhất để bảo vệ dataset khách hàng là gì?

## Tài liệu tham khảo

- Microsoft Learn — *What is Azure Machine Learning?*: https://learn.microsoft.com/azure/machine-learning/overview-what-is-azure-machine-learning?view=azureml-api-2
- Microsoft Learn — *Azure Machine Learning workspaces*: https://learn.microsoft.com/azure/machine-learning/concept-workspace?view=azureml-api-2
- Microsoft Learn — *Compute targets*: https://learn.microsoft.com/azure/machine-learning/concept-compute-target?view=azureml-api-2
- Microsoft Learn — *Create a compute instance*: https://learn.microsoft.com/azure/machine-learning/how-to-create-compute-instance?view=azureml-api-2
- Microsoft Learn — *Create an AML compute cluster*: https://learn.microsoft.com/azure/machine-learning/how-to-create-attach-compute-cluster?view=azureml-api-2
- Microsoft Learn — *Data in Azure Machine Learning*: https://learn.microsoft.com/azure/machine-learning/concept-data?view=azureml-api-2
- Microsoft Learn — *Create and manage data assets*: https://learn.microsoft.com/azure/machine-learning/how-to-create-data-assets?view=azureml-api-2
- Microsoft Learn — *Manage datastores*: https://learn.microsoft.com/azure/machine-learning/how-to-manage-datastores?view=azureml-api-2
- Microsoft Learn — *Train models with jobs*: https://learn.microsoft.com/azure/machine-learning/how-to-train-model?view=azureml-api-2
- Microsoft Learn — *Authentication for Azure Machine Learning*: https://learn.microsoft.com/azure/machine-learning/how-to-authenticate?view=azureml-api-2
- Microsoft Learn — *Secure workspace and networking*: https://learn.microsoft.com/azure/machine-learning/how-to-secure-workspace-vnet?view=azureml-api-2
- Microsoft Learn — *Private endpoint for workspaces*: https://learn.microsoft.com/azure/machine-learning/how-to-configure-private-link?view=azureml-api-2
- Microsoft Learn — *Azure ML CLI v2*: https://learn.microsoft.com/azure/machine-learning/how-to-configure-cli?view=azureml-api-2
- Microsoft Learn — *Manage quotas for Azure Machine Learning*: https://learn.microsoft.com/azure/machine-learning/how-to-manage-quotas?view=azureml-api-2
- Microsoft Learn — *Manage models in Azure Machine Learning*: https://learn.microsoft.com/azure/machine-learning/how-to-manage-models?view=azureml-api-2
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
