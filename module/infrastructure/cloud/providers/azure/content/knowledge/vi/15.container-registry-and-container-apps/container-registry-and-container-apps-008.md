# Triển khai microservice bằng Azure Container Apps

> **Chương:** Container Registry và Container Apps  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Hoàn thành bài này, bạn có thể:

1. Giải thích vai trò của **Azure Container Apps**, **Container Apps environment**, **Container App**, **revision**, **replica** và **Azure Container Registry (ACR)**.
2. Chia một ứng dụng thành các microservice có ranh giới trách nhiệm, API và dữ liệu rõ ràng.
3. Xây dựng và lưu trữ container images, sau đó triển khai hai microservice trên Azure Container Apps bằng Azure CLI.
4. Cấu hình **external/internal ingress**, service discovery, biến môi trường, secrets và **managed identity**.
5. Hiểu **KEDA-based scaling**, scale-to-zero, truy cập HTTP đồng bộ và xử lý công việc bất đồng bộ qua hàng đợi.
6. Triển khai phiên bản mới bằng **revisions**, traffic splitting, kiểm tra sức khỏe và rollback.
7. Thiết kế logging, tracing, quyền truy cập mạng, ngân sách và quy trình xử lý sự cố.

## 1. Bài toán: API đơn khối cần tách thành dịch vụ độc lập

Một công ty bán hàng đang có ứng dụng duy nhất vừa nhận yêu cầu người dùng, vừa quản lý danh mục sản phẩm, đơn hàng và thông báo. Khi nhu cầu tăng, nhóm phát triển muốn:

- Phát hành tính năng danh mục mà không phải triển khai lại toàn bộ ứng dụng.
- Tăng số bản chạy của API nhận request mà không tăng số bản chạy của worker gửi email.
- Chỉ cho API công khai đi ra Internet; dịch vụ dữ liệu phía sau chỉ được các thành phần nội bộ gọi.
- Đưa image lên registry riêng và triển khai lại theo phiên bản có thể truy vết.
- Theo dõi lỗi từng service, kiểm soát chi phí và phản ứng khi tải thay đổi.

Một thiết kế microservice đơn giản:

| Thành phần | Trách nhiệm | Cách truy cập |
| --- | --- | --- |
| `gateway-api` | API public, tổng hợp kết quả và kiểm soát đầu vào | HTTPS external ingress |
| `catalog-api` | Trả dữ liệu danh mục, sở hữu API và logic danh mục | HTTP internal ingress trong environment |
| `orders-worker` | Xử lý đơn hàng/tác vụ bất đồng bộ | Không nhất thiết cần ingress; đọc từ queue |
| Azure Container Registry | Lưu image được kiểm soát | Managed identity với quyền pull |
| Azure Service Bus hoặc Queue Storage | Tách tác vụ, chống dồn tải tức thời | Kết nối có xác thực và quyền tối thiểu |
| Azure Monitor / Log Analytics | Quan sát log, metric, lỗi | Nhóm vận hành được phân quyền |

Trong bài thực hành, ta triển khai **hai service HTTP**; `orders-worker` được trình bày như phần mở rộng kiến trúc, không buộc tạo thêm tài nguyên.

~~~mermaid
flowchart LR
    U["Người dùng\nInternet"]
    G["gateway-api\nexternal ingress :443"]
    C["catalog-api\ninternal ingress :8080"]
    Q["Queue / Service Bus\nnếu dùng async"]
    W["orders-worker\nkhông cần ingress"]
    DB["Database / Storage"]
    ACR["Azure Container Registry\nversioned images"]
    OBS["Azure Monitor\nLogs + metrics"]
    U -->|"HTTPS"| G
    G -->|"HTTP nội bộ\nservice discovery"| C
    G -.->|"Event / message"| Q
    Q -.-> W
    C --> DB
    W -.-> DB
    ACR -.-> G
    ACR -.-> C
    G -.-> OBS
    C -.-> OBS
    W -.-> OBS
~~~

Sơ đồ mô tả luồng chức năng. Ở production, phải chọn đúng ranh giới môi trường, mạng riêng, TLS trên từng đoạn, xác thực giữa các service và bảo vệ database theo yêu cầu.

## 2. Azure Container Apps là gì?

**Azure Container Apps (ACA)** là dịch vụ chạy ứng dụng container và workload dạng microservice mà nhóm phát triển không phải tự quản lý Kubernetes control plane. Dịch vụ giúp triển khai container image, cấu hình ingress, scaling, revisions, secrets và telemetry với mức trừu tượng cao.

Các khái niệm nền tảng:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Container image** | Artifact chứa mã và môi trường chạy | `myregistry.azurecr.io/catalog-api:v1` |
| **Container App** | Tài nguyên Azure định nghĩa ứng dụng container và các cấu hình chung | `catalog-api` |
| **Container Apps environment** | Ranh giới triển khai chung cho nhiều Container Apps, với khả năng mạng và observability được cấu hình | `aca-env-dev` |
| **Revision** | Bản chụp bất biến của các phần cấu hình versioned/template | `catalog-api--r1` |
| **Replica** | Một bản chạy của một revision; có thể chứa một hoặc nhiều containers trong template | Replica số 1 của revision r1 |
| **Ingress** | Cách đưa lưu lượng TCP/HTTP vào ứng dụng theo chế độ được hỗ trợ | External hoặc internal |
| **Scale rule** | Quy tắc tăng/giảm replicas theo lưu lượng hoặc sự kiện | HTTP concurrent requests, queue length |
| **Secret** | Giá trị nhạy cảm được quản lý ở cấp ứng dụng và tham chiếu từ container config | `db-password` |
| **Managed identity** | Danh tính Microsoft Entra được cấp cho workload Azure | Pull image từ ACR không dùng mật khẩu |
| **Container Apps Job** | Tài nguyên chạy công việc đến khi hoàn tất theo lịch, thủ công hoặc event | Batch import dữ liệu |

### ACA khác AKS, App Service và Azure Functions như thế nào?

| Dịch vụ | Trọng tâm | Khi nào cân nhắc |
| --- | --- | --- |
| **Container Apps** | Containerized apps, microservice, event-driven workloads, scaling và revisions với ít vận hành hạ tầng | API, worker, service-to-service, queue consumers |
| **Azure Kubernetes Service (AKS)** | Nền tảng Kubernetes với quyền kiểm soát cluster/networking/extension sâu hơn | Cần API Kubernetes, controllers hoặc vận hành cluster tùy chỉnh |
| **Azure App Service** | Website/API PaaS với tính năng web hosting trưởng thành | Web app, API cần quy trình deploy/hosting trực tiếp |
| **Azure Functions** | Event-driven functions với các trigger và hosting model phù hợp | Logic theo sự kiện/tác vụ ngắn hoặc luồng Functions |
| **Azure Container Registry** | Lưu image, OCI artifacts và chính sách truy cập image | CI/CD build/push/pull, không phải nơi chạy container |

Chọn ACA khi cần chạy container theo mô hình dịch vụ quản lý, nhưng không mặc định mọi yêu cầu Kubernetes hoặc mọi ràng buộc stateful storage đều được giải quyết trực tiếp bằng Container Apps.

## 3. Kiến trúc tài nguyên và ranh giới triển khai

~~~mermaid
flowchart TD
    SUB["Azure subscription"]
    RG["Resource group: rg-aca-lab"]
    ACR["Azure Container Registry"]
    ENV["Container Apps environment\nregion + networking + logs"]
    G["Container App: gateway-api"]
    C["Container App: catalog-api"]
    GR1["Revision gateway--v1"]
    GR2["Revision gateway--v2"]
    CR["Revision catalog--v1"]
    REP["Replicas theo scale rules"]
    SUB --> RG
    RG --> ACR
    RG --> ENV
    ENV --> G --> GR1 --> REP
    G --> GR2
    ENV --> C --> CR
~~~

Một **environment** có thể chứa nhiều Container Apps. Những app trong cùng environment có thể dùng cơ chế service discovery theo tên ứng dụng khi đã cấu hình ingress phù hợp. Tài nguyên container app và environment có các phạm vi cấu hình và vòng đời khác nhau.

### 3.1. Environment không phải là Container App

Khi tạo environment, bạn thiết lập bối cảnh triển khai và các lựa chọn liên quan đến vùng, mạng, observability, workload profiles và những đặc tính hỗ trợ. Tạo environment chưa tạo dịch vụ `gateway-api`.

Container App chứa cấu hình image, containers, resources, ingress, secrets, identities, scale rules và revisions.

**Quy tắc:** tất cả microservice không cần nằm trong cùng một environment. Gom nhóm theo môi trường Dev/Prod, ranh giới network, quyền quản trị và yêu cầu tuân thủ. Không dùng chung production và lab chỉ vì tiện service discovery.

### 3.2. Revision khác replica

- **Revision** được tạo khi cập nhật phần cấu hình thuộc revision scope, ví dụ container image, environment variables hoặc scale settings theo cơ chế hỗ trợ.
- **Replica** là bản chạy thực tế của revision; hệ thống tăng/giảm số replica dựa trên scaling.

Ví dụ:

~~~text
catalog-api
  Revision r1 (image catalog-api:v1)
    Replica A
    Replica B

gateway-api
  Revision r1 (image gateway-api:v1)
    Replica C
  Revision r2 (image gateway-api:v2)
    Replica D
~~~

Một revision có thể có nhiều replicas. **Tăng replica không đồng nghĩa tạo revision mới**. Ở multiple-revision mode, nhiều revisions có thể hoạt động đồng thời và nhận các tỷ lệ traffic khác nhau theo cấu hình ingress.

### 3.3. Revision scope và application scope

Một số thuộc tính thay đổi tạo revision mới (ví dụ image và các thuộc tính template được version hóa). Một số thuộc tính cấp app có thể thay đổi mà **không tạo revision mới** (ví dụ cấu hình secrets hoặc ingress theo phạm vi hỗ trợ).

Tác động thực tế: **đổi một secret không đảm bảo container đang chạy tự đọc lại giá trị mới**; có thể cần restart revision hoặc phát hành revision mới tùy cách secrets được tham chiếu và hành vi runtime. Khi triển khai production phải hiểu scope của thuộc tính đang đổi.

## 4. Thiết kế microservice trước khi viết lệnh triển khai

### 4.1. Chọn ranh giới trách nhiệm

Microservice không chỉ là “chia một ứng dụng thành nhiều container”. Mỗi service nên có trách nhiệm và giao diện rõ:

- `gateway-api` chịu trách nhiệm tiếp nhận HTTP public và tổng hợp dữ liệu.
- `catalog-api` chịu trách nhiệm trả thông tin sản phẩm.
- `orders-worker` xử lý hàng đợi/tác vụ bất đồng bộ và phải hỗ trợ retry, idempotency.

Một ranh giới tốt giúp nhóm triển khai/scale riêng service và tránh kéo theo mọi hệ thống khi một chức năng thay đổi. Nhưng quá nhiều service tạo thêm chi phí networking, tracing, quyền truy cập và vận hành.

### 4.2. Đồng bộ HTTP và bất đồng bộ queue

| Mẫu giao tiếp | Đặc điểm | Khi phù hợp | Rủi ro |
| --- | --- | --- | --- |
| **HTTP request/response** | Caller chờ downstream hoàn thành | Đọc danh mục, kiểm tra thông tin ngắn | Timeout, lỗi dây chuyền, fan-out |
| **Message queue** | Publisher gửi message, consumer xử lý sau | Xử lý đơn hàng, email, image processing | Duplicate delivery, retry, dead-letter |
| **Event publish/subscribe** | Nhiều subscribers phản ứng với event | Đồng bộ hệ thống, event-driven workflows | Event schema/versioning và eventual consistency |
| **Dapr (tùy chọn)** | Sidecar cung cấp service invocation, pub/sub, state API... theo components | Muốn giảm code tích hợp hạ tầng | Thêm cấu hình runtime, observability và quyền |

Trong bài thực hành, `gateway-api` gọi `catalog-api` bằng HTTP. Với nghiệp vụ đặt hàng thực, không nên giữ HTTP request mở hàng phút để chờ toàn bộ workflow hoàn tất; hãy cân nhắc queue + background worker.

### 4.3. Health endpoint và stateless design

Mỗi HTTP service nên có endpoint nhanh, ví dụ `GET /healthz`, để xác định process đang chạy. Với readiness sâu hơn, có thể tạo `/ready` trả status theo khả năng đáp ứng request.

Khi scale nhiều replicas:

- Không lưu session quan trọng chỉ trong RAM của một replica.
- Không lưu uploads/dữ liệu cần bền vững vào local temporary filesystem.
- Sử dụng database, Blob Storage hoặc shared storage phù hợp.
- Thiết kế retry, timeout, idempotency và graceful shutdown.
- Giới hạn connections từ mỗi replica để không vượt tải dịch vụ phía sau.

### 4.4. Security boundary

**Internal ingress** ngăn công bố trực tiếp ứng dụng theo đường ingress public của ACA trong thiết kế tiêu chuẩn, nhưng **không tự xác thực người gọi là ứng dụng được phép**. Nếu yêu cầu chỉ `gateway-api` được gọi `catalog-api`, cần thêm xác thực/ủy quyền nội bộ, network segmentation thích hợp hoặc cơ chế mTLS/service invocation theo khả năng và cấu hình.

Không dùng câu “nội bộ” để suy ra microservice đã an toàn trước truy cập không được phép từ mọi workload bên trong cùng environment.

## 5. Ví dụ hai microservice có thể chạy bằng container

Ví dụ dùng **Python FastAPI** để phần thực hành dễ đọc. Các file bên dưới được minh họa **trong bài học**, không phải được tạo thật trên máy hoặc repository của người học. Bạn có thể tạo cấu trúc sau trong một thư mục lab của riêng mình:

~~~text
aca-microservices-lab/
  catalog/
    app.py
    requirements.txt
    Dockerfile
  gateway/
    app.py
    requirements.txt
    Dockerfile
~~~

### 5.1. catalog-api: cung cấp dữ liệu nội bộ

Tệp `catalog/app.py`:

~~~python
from fastapi import FastAPI

app = FastAPI(title="catalog-api")

PRODUCTS = [
    {"id": "p-101", "name": "Keyboard", "price": 59},
    {"id": "p-102", "name": "Mouse", "price": 29},
]

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/items")
def list_items():
    return {"items": PRODUCTS}
~~~

Tệp `catalog/requirements.txt`:

~~~text
fastapi
uvicorn
~~~

Tệp `catalog/Dockerfile`:

~~~dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
USER 10001
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
~~~

Ở production, pin phiên bản dependencies, quét lỗ hổng image, ký/xác minh artifact theo chính sách và cố định image digest. Dữ liệu danh mục ở đây là **giả lập trong bộ nhớ**, không phải dữ liệu production.

### 5.2. gateway-api: nhận yêu cầu và gọi catalog qua HTTP

Tệp `gateway/app.py`:

~~~python
import os

import httpx
from fastapi import FastAPI, HTTPException

app = FastAPI(title="gateway-api")
CATALOG_URL = os.getenv("CATALOG_URL", "http://catalog-api").rstrip("/")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/products")
async def products():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{CATALOG_URL}/items")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504, detail="catalog-api timeout"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="catalog-api unavailable"
        ) from exc
~~~

Tệp `gateway/requirements.txt`:

~~~text
fastapi
uvicorn
httpx
~~~

Tệp `gateway/Dockerfile` (tương tự catalog):

~~~dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
USER 10001
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
~~~

Hai ứng dụng đều lắng nghe cổng **8080** trong container. Gateway gọi một URL nội bộ dạng `http://catalog-api/items`; tên ngắn `catalog-api` sẽ được ACA phân giải trong cùng environment **khi đã bật ingress thích hợp cho service đích**.

Trong thực tế, đừng trả toàn bộ nội dung lỗi nội bộ về client. Ví dụ trên chỉ trả một thông báo tổng quát và giữ chi tiết nguyên nhân trong log của service để tránh lộ địa chỉ/secret.

### 5.3. Kiểm tra local trước khi đưa lên Azure

Từ thư mục gốc chứa `catalog` và `gateway`:

~~~bash
docker build -t catalog-api:local ./catalog
docker build -t gateway-api:local ./gateway

# Chạy catalog trong một Docker network riêng cho lab.
docker network create aca-lab-net
docker run --rm --name catalog-api \
  --network aca-lab-net \
  -p 8081:8080 \
  catalog-api:local

# Mở terminal khác; container gateway truy cập catalog
# qua tên container trong Docker network.
docker run --rm --name gateway-api \
  --network aca-lab-net \
  -e CATALOG_URL=http://catalog-api:8080 \
  -p 8080:8080 \
  gateway-api:local
~~~

Thử API:

~~~bash
curl http://localhost:8080/healthz
curl http://localhost:8080/products
curl http://localhost:8081/items
~~~

Ở Docker local, hai container giao tiếp trực tiếp trên **port 8080** qua DNS của Docker network. Sau triển khai ACA với ingress, URL nội bộ `http://catalog-api` không cần gắn port container thủ công trong ví dụ này, vì ACA ingress xử lý routing tới `target-port=8080`.

Không mở port catalog ra Internet ở production chỉ vì bài thử local có `-p 8081:8080`; đó chỉ là cách quan sát container trong lab.

## 6. Chuẩn bị Azure resources và chi phí

### 6.1. Những thứ cần có

- Azure subscription được phép tạo tài nguyên và tính phí.
- Azure CLI và extension `containerapp` hiện hành.
- Docker cho kiểm tra local nếu thực hành phần 5; có thể dùng `az acr build` để build trên Azure.
- Quyền quản lý resource group, Container Apps environment, Container Apps, ACR và user-assigned managed identity.
- Nếu tạo role assignment, cần quyền được phép **gán vai trò** tại scope ACR; có Contributor không đương nhiên có quyền này.
- Resource name cho ACR phải **duy nhất theo không gian tên dịch vụ** và đúng quy tắc đặt tên.

**Chi phí có thể phát sinh** từ ACR, Container Apps compute/request, environment/logs, networking và các dịch vụ kèm theo. Chỉ chạy lệnh ghi trong lab được chấp thuận; kiểm tra giá theo region và subscription thực tế.

### 6.2. Khai báo biến môi trường CLI

Các lệnh minh họa bên dưới dùng **Bash**. Nếu dùng PowerShell, cần đổi cú pháp biến/command substitution phù hợp.

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-aca-lab"
LOCATION="southeastasia"
ENV="aca-env-lab"
ACR="acrdemounique12345"
IDENTITY="id-aca-pull"

az extension add --name containerapp --upgrade
~~~

Thay `ACR` bằng tên registry **duy nhất thực tế**, chỉ gồm ký tự hợp lệ và được tổ chức phê duyệt. Nếu extension đã cài đặt, lệnh nâng cấp có thể đòi kết nối Internet và quyền môi trường phát triển.

### 6.3. Tạo resource group, ACR và Container Apps environment

~~~bash
az group create \
  --name "$RG" \
  --location "$LOCATION"

az acr create \
  --resource-group "$RG" \
  --name "$ACR" \
  --sku Basic

az containerapp env create \
  --name "$ENV" \
  --resource-group "$RG" \
  --location "$LOCATION"
~~~

Đây là **các thao tác tạo tài nguyên có thể tính phí**. Môi trường mới thường có cấu hình logging/observability được tạo hoặc liên kết tùy tham số và CLI hiện hành; kiểm tra chính xác Log Analytics workspace đích nếu cần tuân thủ chính sách dữ liệu.

Lệnh tạo environment mặc định không đảm bảo hệ thống đã có VNet private hoặc DNS routing theo thiết kế production. Nếu cần mạng riêng, phải chọn loại environment, subnet, routing, DNS và cơ chế ingress tương thích từ lúc xây kiến trúc.

### 6.4. Build và đẩy hai images vào ACR

Khi đang ở thư mục gốc `aca-microservices-lab` chứa hai thư mục nguồn:

~~~bash
az acr build \
  --registry "$ACR" \
  --image catalog-api:v1 \
  ./catalog

az acr build \
  --registry "$ACR" \
  --image gateway-api:v1 \
  ./gateway

LOGIN_SERVER=$(az acr show \
  --name "$ACR" \
  --resource-group "$RG" \
  --query loginServer \
  --output tsv)

echo "$LOGIN_SERVER"
~~~

Kết quả image refs có dạng:

~~~text
<login-server>/catalog-api:v1
<login-server>/gateway-api:v1
~~~

Ví dụ `acrdemounique12345.azurecr.io/catalog-api:v1`. Với production, hãy dùng tags bất biến kết hợp **image digest** để truy vết bản build; không dùng tag `latest` thay đổi âm thầm mà không có quản trị phiên bản.

### 6.5. Managed identity để Container Apps pull images

Không cần bật ACR admin user hoặc chép mật khẩu registry vào source code. Có thể dùng **user-assigned managed identity**:

~~~bash
az identity create \
  --resource-group "$RG" \
  --name "$IDENTITY" \
  --location "$LOCATION"

IDENTITY_ID=$(az identity show \
  --resource-group "$RG" \
  --name "$IDENTITY" \
  --query id \
  --output tsv)

PRINCIPAL_ID=$(az identity show \
  --resource-group "$RG" \
  --name "$IDENTITY" \
  --query principalId \
  --output tsv)

ACR_ID=$(az acr show \
  --resource-group "$RG" \
  --name "$ACR" \
  --query id \
  --output tsv)
~~~

Với ACR ở **chế độ cấp quyền RBAC registry cổ điển** có hỗ trợ role này, grant quyền `AcrPull`:

~~~bash
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "$ACR_ID"
~~~

**Điểm cần xác minh:** ACR có thể sử dụng **chế độ phân quyền ABAC repository-scoped**; khi đó mô hình role cần thiết có thể khác `AcrPull`. Hãy kiểm tra permission mode, role phù hợp và chính sách tổ chức trước khi cấp quyền. Role assignment có thể cần thời gian lan truyền. Danh tính chỉ cần quyền pull image, không cần quyền push hoặc Owner trên subscription.

Nếu quy trình cấp quyền không hoàn tất, đừng chuyển sang nhúng ACR admin password vào lệnh production như một “cách sửa nhanh”. Báo người quản trị IAM để cấp đúng quyền.


## 7. Triển khai hai microservice bằng Azure Container Apps

Mục tiêu của ví dụ:

- `catalog-api` chỉ nhận lưu lượng qua **internal ingress**, không có URL public trực tiếp.
- `gateway-api` có **external ingress** để người dùng gọi bằng HTTPS.
- Cả hai chạy trong `aca-env-lab`, lấy image từ ACR qua user-assigned managed identity.
- Gateway gọi catalog qua tên service `http://catalog-api` trong cùng environment.
- Đặt **min replicas = 1** trong lab để hạn chế cold start khi kiểm thử; đặt max theo khả năng và ngân sách.

### 7.1. Tạo catalog-api trước

~~~bash
az containerapp create \
  --name catalog-api \
  --resource-group "$RG" \
  --environment "$ENV" \
  --image "$LOGIN_SERVER/catalog-api:v1" \
  --user-assigned "$IDENTITY_ID" \
  --registry-server "$LOGIN_SERVER" \
  --registry-identity "$IDENTITY_ID" \
  --ingress internal \
  --target-port 8080 \
  --transport auto \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 3
~~~

**Ý nghĩa của các tham số:**

| Tham số | Vai trò | Lưu ý |
| --- | --- | --- |
| `--environment` | Chỉ định Container Apps environment | Hai app phải cùng environment để dùng tên ngắn như ví dụ |
| `--image` | Image ref chứa mã catalog | Không có trong registry hoặc thiếu quyền pull sẽ lỗi |
| `--user-assigned` | Gắn managed identity với app | Phải tồn tại và được quản trị đúng scope |
| `--registry-identity` | Dùng identity xác thực khi pull từ registry | Khác với việc tự động cấp quyền ACR |
| `--ingress internal` | Đặt endpoint nội bộ theo phạm vi ACA hỗ trợ | Không phải cơ chế xác thực người gọi |
| `--target-port 8080` | Port mà process trong container lắng nghe | Phải khớp `uvicorn --port 8080` |
| `--cpu`, `--memory` | Tài nguyên trên mỗi replica | Cần là tổ hợp được workload profile hỗ trợ |
| `--min-replicas`, `--max-replicas` | Giới hạn tự mở rộng | 1–3 chỉ là ví dụ lab |

Tạo app là **thao tác có chi phí** và đòi permission thích hợp. Các cú pháp CLI có thể thay đổi theo phiên bản extension; kiểm tra `az containerapp create --help` nếu CLI của bạn yêu cầu cú pháp khác.

### 7.2. Xác minh catalog-api

~~~bash
az containerapp show \
  --resource-group "$RG" \
  --name catalog-api \
  --query "{name:name, state:properties.provisioningState, ingress:properties.configuration.ingress, latestRevision:properties.latestRevisionName}" \
  --output json

az containerapp revision list \
  --resource-group "$RG" \
  --name catalog-api \
  --output table
~~~

Cần xác nhận:

1. Trạng thái provisioning thành công.
2. Image ref đúng version và registry.
3. Internal ingress đã bật, target port đúng 8080.
4. Có revision được kích hoạt và replica sẵn sàng theo mong đợi.
5. Không có lỗi `ImagePullBackOff`, khởi động process hoặc port mismatch.

`catalog-api` không cần public endpoint chỉ để kiểm tra sức khỏe. Có thể dùng logs, ingress nội bộ từ một app cùng environment hoặc cơ chế debug được cấp quyền.

### 7.3. Triển khai gateway-api với external ingress

~~~bash
az containerapp create \
  --name gateway-api \
  --resource-group "$RG" \
  --environment "$ENV" \
  --image "$LOGIN_SERVER/gateway-api:v1" \
  --user-assigned "$IDENTITY_ID" \
  --registry-server "$LOGIN_SERVER" \
  --registry-identity "$IDENTITY_ID" \
  --ingress external \
  --target-port 8080 \
  --transport auto \
  --env-vars CATALOG_URL=http://catalog-api \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 5
~~~

Biến môi trường `CATALOG_URL` là địa chỉ nội bộ mà ứng dụng gateway gọi. Vì hai Container Apps ở cùng environment và catalog đã bật ingress, tên ngắn `http://catalog-api` có thể được giải quyết qua **service discovery** của ACA.

Nếu triển khai hai app ở **hai environments khác nhau**, cách gọi tên ngắn này không còn là giả định phù hợp. Khi đó phải thiết kế DNS/FQDN, network reachability và bảo mật cho kết nối liên môi trường.

### 7.4. Lấy URL và kiểm tra luồng end-to-end

~~~bash
GATEWAY_FQDN=$(az containerapp show \
  --resource-group "$RG" \
  --name gateway-api \
  --query properties.configuration.ingress.fqdn \
  --output tsv)

echo "$GATEWAY_FQDN"

curl -i "https://$GATEWAY_FQDN/healthz"
curl -i "https://$GATEWAY_FQDN/products"
~~~

Nếu hoạt động, endpoint `/products` trả JSON gần dạng:

~~~json
{
  "items": [
    {"id": "p-101", "name": "Keyboard", "price": 59},
    {"id": "p-102", "name": "Mouse", "price": 29}
  ]
}
~~~

Đây là phép kiểm tra **hai microservice hoạt động phối hợp**, không chỉ kiểm tra gateway process. `/healthz` của gateway có thể trả 200 trong khi `/products` trả 502/504 nếu catalog lỗi hoặc giao tiếp nội bộ không hoạt động.

### 7.5. HTTP/TLS ở đường public và đường nội bộ

- Với **external HTTP ingress**, ACA cung cấp endpoint HTTPS và quản lý TLS ở điểm vào theo khả năng môi trường/tên miền.
- Container `gateway-api` vẫn lắng nghe HTTP trong container ở port 8080; ingress chuyển tiếp tới target port.
- Kết nối nội bộ `http://catalog-api` trong ví dụ dùng HTTP qua cơ chế ACA ingress, **không đồng nghĩa end-to-end TLS hoặc mTLS đã được cấu hình riêng**.
- Khi thiết kế production, xem xét yêu cầu mã hóa đường nội bộ, xác thực dịch vụ, Dapr/service invocation, private networking và chính sách bảo mật.

**Đừng suy rằng chọn `--ingress internal` sẽ tự xác minh JWT hoặc chỉ cho gateway app gọi catalog.** Phân quyền giữa các service là một bài toán riêng.

## 8. Service discovery và mạng nội bộ

### 8.1. Ingress external và internal

| Loại | Ai có thể dùng endpoint? | Ví dụ |
| --- | --- | --- |
| **External ingress** | Có thể truy cập từ bên ngoài theo cấu hình network/environment và security controls | `gateway-api` |
| **Internal ingress** | Cung cấp điểm vào nội bộ trong phạm vi được ACA hỗ trợ, phục vụ các app/workload được phép | `catalog-api` |
| **Không ingress** | Không nhận request vào qua ACA ingress; vẫn có thể chạy worker/event consumer | `orders-worker` |

**External** không nhất thiết có nghĩa endpoint luôn public trên Internet: một **internal Container Apps environment** hoặc thiết kế network có thể thay đổi khả năng truy cập. Cần phân biệt **environment-level networking** với **app-level ingress**.

**Internal** cũng không có nghĩa một ứng dụng chỉ nhận request từ đúng một app khác; phải xác định ai có network access và đặt authentication/authorization phù hợp.

### 8.2. Vì sao gọi tên ngắn hoạt động?

Khi nhiều Container Apps nằm trong cùng environment và đích có ingress bật phù hợp, service discovery giúp gọi tên app thay vì hard-code IP của từng replica:

~~~text
gateway-api
  GET http://catalog-api/items
      |
      v
ACA service discovery + ingress
      |
      v
catalog-api replicas
~~~

Lợi ích:

- Không cần cập nhật IP khi catalog thay replicas.
- Phía gọi không phải nắm danh sách replica IP.
- Có thể thay revision của catalog mà giữ tên service ổn định.

Giới hạn:

- Tên app không thay thế API versioning; service vẫn phải tương thích.
- Gọi HTTP đồng bộ vẫn cần timeout, retry/backoff có giới hạn và circuit breaker khi phù hợp.
- Các yêu cầu lớn hoặc chuỗi gọi nhiều service có thể làm latency tăng.
- Nếu catalog scale về 0, request đầu có thể gặp cold start.
- DNS name không tự bảo đảm ứng dụng phía đích khỏe hoặc có quyền truy cập dữ liệu.

### 8.3. VNet và private dependencies

Một ứng dụng có thể cần truy cập Azure SQL, Storage hoặc Key Vault qua network được kiểm soát. Khi đó:

1. Xác định Container Apps environment hỗ trợ phương án VNet và workload profile cần dùng.
2. Chuẩn bị subnet có kích thước, delegation/quy tắc được hỗ trợ theo kiểu environment.
3. Xác định cần **private endpoint** cho dịch vụ phụ thuộc hay không.
4. Thiết kế DNS resolution (Private DNS Zone/Private Resolver khi cần).
5. Cấu hình outbound access, firewall và NAT theo yêu cầu.
6. Kiểm tra Azure RBAC/data-plane permissions độc lập với mạng.

Việc đặt hai Container Apps trong cùng environment không tự làm mọi kết nối Azure SQL/Storage trở thành private. Đừng chỉ thay URL dịch vụ bằng private IP mà không cấu hình DNS/network đúng.

### 8.4. Tách environments theo ranh giới vận hành

Một mô hình triển khai:

| Environment | Mục đích | Chính sách ví dụ |
| --- | --- | --- |
| `aca-env-dev` | Thử nghiệm chức năng | Ngân sách thấp, dữ liệu giả, cho phép scale-to-zero |
| `aca-env-staging` | Kiểm thử tích hợp/revision | Cấu hình gần production, dữ liệu kiểm thử |
| `aca-env-prod` | Phục vụ người dùng | Identity tối thiểu, private dependencies, giám sát/SLO |

Không nên dùng một environment duy nhất cho toàn bộ Dev/Prod nếu yêu cầu bảo mật và phân tách quyền nghiêm ngặt.

## 9. Scaling với KEDA và scale-to-zero

Azure Container Apps dùng khả năng scaling dựa trên **Kubernetes Event-driven Autoscaling (KEDA)** theo mô hình dịch vụ quản lý. Bạn không cần tự quản lý KEDA operator trong Container Apps thông thường.

### 9.1. Replica count khác revision

Ví dụ `gateway-api` có một revision `r1` với 2 replicas; KEDA có thể nâng từ 2 lên 5 replicas khi tải tăng mà **không tạo revision mới**. Thay image từ `v1` sang `v2` sẽ tạo revision mới thuộc template của app.

### 9.2. Các dạng scaling phổ biến

| Loại | Tín hiệu | Tình huống |
| --- | --- | --- |
| **HTTP scaling** | Số request đồng thời theo ngưỡng được hỗ trợ | Web API, frontend |
| **TCP scaling** | Kết nối TCP đồng thời theo cơ chế ingress hỗ trợ | Workload TCP thích hợp |
| **Event-driven scaling** | Queue length hoặc metric nguồn sự kiện qua KEDA scaler được hỗ trợ | Consumer Service Bus, Queue Storage |
| **Custom scaler** | Metric/trigger tùy nguồn tích hợp hỗ trợ | Tích hợp nghiệp vụ chuyên biệt |

**CPU/memory scaling** có điều kiện và hành vi khác HTTP/event scaling tùy cấu hình; không giả định cứ CPU vượt một ngưỡng là app sẽ scale nếu chưa có scale rules và min/max phù hợp.

### 9.3. minReplicas và maxReplicas

| Cấu hình | Ưu điểm | Nhược điểm |
| --- | --- | --- |
| `minReplicas=0` | Có thể scale-to-zero, giảm chi phí idle theo điều kiện của billing model | Cold start khi có request/event mới; không phù hợp mọi SLO |
| `minReplicas=1` | Ít nhất một replica được duy trì theo cấu hình | Có compute hoạt động khi ít tải |
| `maxReplicas=5` | Giới hạn mức mở rộng/chi phí và tải xuống downstream | Có thể không đủ khi tăng tải lớn |

Scale-to-zero chỉ khả dụng khi workload và **scale trigger** tương ứng hỗ trợ. Không phải mọi worker CPU-bound không có HTTP ingress hoặc không có event scaler đều tự thức dậy từ số 0. Nếu cần listener lâu dài, đặt min replicas phù hợp.

### 9.4. Cấu hình HTTP scaling rule

Ví dụ cập nhật scale rule cho gateway khi môi trường hỗ trợ:

~~~bash
az containerapp update \
  --resource-group "$RG" \
  --name gateway-api \
  --min-replicas 1 \
  --max-replicas 5 \
  --scale-rule-name http-concurrency \
  --scale-rule-type http \
  --scale-rule-http-concurrency 50
~~~

Câu lệnh **thay đổi cấu hình revision** và có thể tạo revision mới. Một HTTP concurrency threshold 50 **không có nghĩa chính xác 50 requests/giây**; đó là giới hạn về **số request đồng thời** theo ý nghĩa scaler. Phải kiểm tra mức hỗ trợ của extension/CLI đang dùng và xem revision/template sau khi cập nhật.

### 9.5. Sizing theo concurrency, latency và SLO

Nếu trung bình một request tốn 0,2 giây và hệ thống có 100 requests/giây ở trạng thái tương đối ổn định, số request đang xử lý đồng thời xấp xỉ:

\[
L=\lambda W = 100\times0{,}2=20
\]

Nếu một replica có thể phục vụ an toàn 10 requests đồng thời ở SLO yêu cầu, ít nhất cần khoảng 2 replicas theo mô hình đơn giản, **chưa tính headroom, tải lệch, cold start hoặc dependency bottleneck**.

Không chọn scale rule chỉ từ CPU khi API có thời gian chờ database dài. Đo **p95/p99 response time** và concurrency thật của ứng dụng.

### 9.6. Event-driven worker từ queue

Microservice `orders-worker` có thể xử lý thông điệp từ Azure Service Bus hoặc Queue Storage:

~~~mermaid
flowchart LR
    G["gateway-api"]
    Q["Service Bus Queue"]
    K["KEDA scaler\nqueue length"]
    W["orders-worker replicas"]
    DB["Database / external APIs"]
    G -->|"Publish order event"| Q
    Q -->|"Consume"| W --> DB
    Q -.->|"Metric / backlog"| K -.->|"Scale"| W
~~~

Một consumer đúng cần:

- Xác thực queue bằng managed identity/permission thích hợp.
- Xử lý duplicate message bằng **idempotency key**.
- Retry có giới hạn và **dead-letter** khi vượt số lần thử.
- Chỉ xác nhận/hoàn tất message sau khi xử lý thành công theo queue semantics.
- Kiểm soát số kết nối tới database và API phụ thuộc khi tăng replicas.
- Có thể cân nhắc **Container Apps Jobs** nếu workload mang tính run-to-completion.

Không dùng số replicas cao để che consumer xử lý sai thứ tự hoặc chưa có cơ chế idempotent.

## 10. Revisions, rollout và traffic splitting

### 10.1. Khi nào tạo revision mới?

Trong Container Apps, thay những trường thuộc **revision template** như image, CPU/memory, environment variables hoặc scale configuration có thể tạo revision mới. Những thiết lập cấp app như secrets và ingress có thể có vòng đời cập nhật khác.

Điều này cho phép giữ một bản ổn định và đưa bản mới vào một phần lưu lượng trước khi chuyển hẳn.

### 10.2. Single-revision và multiple-revision mode

| Chế độ | Đặc điểm | Sử dụng |
| --- | --- | --- |
| **Single revision mode** | Thường chỉ một revision active tại một thời điểm theo cơ chế điều phối | Phát hành đơn giản |
| **Multiple revision mode** | Có thể giữ nhiều revisions active, phân phối HTTP ingress traffic theo trọng số | Canary, A/B, rollback nhanh |

Ở **multiple revision mode**, hai revisions cùng active có thể đồng thời tiêu thụ compute; phải cân nhắc chi phí và giới hạn. Traffic splitting là cơ chế ở **ingress HTTP**; không mặc định cùng hành vi cho event consumers không có ingress.

### 10.3. Chuẩn bị v2 và bật multiple-revision mode

Trong một lab được phép, sửa source `gateway/app.py` hoặc logic response (không làm thay đổi API contract quan trọng), rồi build:

~~~bash
az acr build \
  --registry "$ACR" \
  --image gateway-api:v2 \
  ./gateway
~~~

Chuyển mode:

~~~bash
az containerapp revision set-mode \
  --resource-group "$RG" \
  --name gateway-api \
  --mode multiple
~~~

Sau đó deploy image mới:

~~~bash
az containerapp update \
  --resource-group "$RG" \
  --name gateway-api \
  --image "$LOGIN_SERVER/gateway-api:v2"
~~~

Lưu ý: **không cập nhật tag `v1` để nó chỉ sang image khác** rồi kỳ vọng ACA tự hiểu là một revision mới. Đặt tag/digest mới giúp theo dõi và tạo revision khi thay image template.

### 10.4. Xem revision names và phân phối traffic

~~~bash
az containerapp revision list \
  --resource-group "$RG" \
  --name gateway-api \
  --output table

az containerapp show \
  --resource-group "$RG" \
  --name gateway-api \
  --query properties.configuration.ingress.traffic \
  --output json
~~~

Ví dụ khi có hai revision thật:

~~~text
gateway-api--r1    (image v1)
gateway-api--r2    (image v2)
~~~

Tên này chỉ để minh họa. Revision thật do Azure sinh ra, có hậu tố riêng; **đừng đoán tên revision từ tag image**.

Khi đã xác minh tên và health của từng revision, có thể áp dụng traffic weight:

~~~bash
# Thay hai placeholder bằng revision names THẬT từ revision list.
az containerapp ingress traffic set \
  --resource-group "$RG" \
  --name gateway-api \
  --revision-weight \
    "<REVISION_V1>=90" \
    "<REVISION_V2>=10"
~~~

Mục đích là chuyển khoảng **90% lưu lượng HTTP ingress tới v1 và 10% tới v2**, theo cơ chế phân phối của dịch vụ. Đây không phải cam kết mỗi 10 request phải có đúng 1 request vào v2; tỷ lệ quan sát trên mẫu nhỏ có thể khác.

### 10.5. Canary và rollback

Quy trình phát hành an toàn:

1. Build/push image v2 có tag/digest rõ ràng, quét bảo mật theo chính sách.
2. Deploy revision mới và xác minh image, startup, health và dependencies.
3. Chuyển một tỷ lệ nhỏ traffic tới v2.
4. So sánh 5xx rate, p95 latency, CPU, log và trace **theo revision**.
5. Tăng traffic dần khi SLO đạt yêu cầu và không thấy lỗi nghiệp vụ.
6. Nếu v2 lỗi, chuyển traffic trở lại revision ổn định; chỉ deactivate revision lỗi sau khi xác nhận rollback và không còn phụ thuộc.

Ví dụ rollback về v1:

~~~bash
az containerapp ingress traffic set \
  --resource-group "$RG" \
  --name gateway-api \
  --revision-weight \
    "<REVISION_V1>=100" \
    "<REVISION_V2>=0"
~~~

Hãy kiểm tra trạng thái active và trọng số sau mỗi thay đổi. Chuyển traffic **không tự rollback schema database hay message đã xử lý**. Với microservice production, thiết kế backward-compatible API/database migration để rollback an toàn.

## 11. Secrets, configuration và managed identity

### 11.1. Biến môi trường không dành cho bí mật

Trong ví dụ, `CATALOG_URL` là địa chỉ service, không phải secret:

~~~bash
--env-vars CATALOG_URL=http://catalog-api
~~~

Tuy nhiên, không nên đặt trực tiếp password, connection string chứa credential hoặc token ở biến môi trường khai báo bằng plaintext trong shell history hoặc deployment pipeline logs.

Azure Container Apps hỗ trợ **secrets** ở cấp ứng dụng và tham chiếu secret qua cấu hình container. Có thể kết hợp **Key Vault references** với managed identity theo khả năng hỗ trợ để quản trị vòng đời secret tập trung.

### 11.2. Tách các loại quyền

| Tác vụ | Identity/quyền cần | Ghi chú |
| --- | --- | --- |
| Deploy Container App | Azure RBAC management-plane đối với environment/app | Khác quyền chạy workload |
| Pull image từ ACR | Identity được gắn với app và quyền pull phù hợp | Không cần registry admin password |
| Đọc Azure Key Vault secret | Managed identity của workload có quyền đọc secret | Tùy RBAC/access-policy model của vault |
| Đọc/ghi Blob Storage | Identity có data-plane role phù hợp | Network access cũng phải cho phép |
| Consume Service Bus | Identity có data receiver role phù hợp | Không cần quyền quản trị namespace |
| Publish Service Bus | Identity có data sender role phù hợp | Giới hạn đúng queue/topic |

**Managed identity là danh tính, không tự có mọi quyền.** Gắn identity vào Container App rồi vẫn phải cấp đúng role tại đúng scope và xác minh propagation.

### 11.3. Đổi secret chưa chắc làm revision mới

Secrets được quản lý ở application scope theo mô hình ACA. Thay một giá trị secret có thể không tạo revision mới hoặc không cập nhật giá trị bên trong process đang chạy ngay lập tức.

Quy trình an toàn:

1. Cập nhật secret/Key Vault reference bằng cơ chế được hỗ trợ.
2. Kiểm tra quyền identity và trạng thái tham chiếu.
3. Restart revision hoặc rollout revision mới khi cần theo cách ứng dụng đọc secret.
4. Xác minh hệ thống vẫn kết nối dependency.
5. Thu hồi credential cũ sau khi xác nhận ứng dụng dùng giá trị mới.

### 11.4. Không dùng container filesystem làm storage nghiệp vụ

Replicas có thể bị tạo/xóa khi autoscale hoặc deploy revision. Dữ liệu chỉ lưu bên trong container filesystem có thể mất khi replica bị thay thế.

Phân loại dữ liệu:

| Loại dữ liệu | Cách lưu phù hợp |
| --- | --- |
| Request/session | Stateless token hoặc cache/session store dùng chung |
| Uploads | Blob Storage hoặc dịch vụ storage được thiết kế bền vững |
| Database nghiệp vụ | Azure SQL/Cosmos DB/PostgreSQL theo yêu cầu |
| Temporary scratch | Ephemeral storage, chấp nhận mất khi replica bị xóa |
| Shared file volume | Azure Files volume khi ACA và kiến trúc hỗ trợ |
| Secrets | Container Apps secrets/Key Vault, không đóng gói vào image |

Không mặc định volume Azure Files là thay thế hoàn hảo database hoặc giải quyết mọi bài toán concurrent write; cần xác định semantics và hiệu năng.

## 12. Quan sát hoạt động bằng logs, metrics và traces

### 12.1. Ba loại tín hiệu bổ sung cho nhau

- **Logs:** ứng dụng ghi lại lỗi, request, startup/shutdown, dependency failure và revision.
- **Metrics:** request rate, replica count, CPU, memory, network/HTTP metrics, queue backlog và trạng thái scaling.
- **Traces:** theo dõi một request từ gateway qua catalog tới storage/database.

Nếu gateway trả 502, cần phân biệt:

1. Gateway code không kết nối được catalog vì DNS/ingress.
2. Catalog scale-to-zero và chưa sẵn sàng hoặc startup lỗi.
3. Catalog trả 500 vì dependency.
4. Timeout 5 giây của gateway quá ngắn so với thực tế.
5. Container crash, image pull fail hoặc revision chưa healthy.

### 12.2. Xem logs bằng Azure CLI

~~~bash
az containerapp logs show \
  --resource-group "$RG" \
  --name gateway-api \
  --type console \
  --tail 50

az containerapp logs show \
  --resource-group "$RG" \
  --name catalog-api \
  --type console \
  --tail 50
~~~

Muốn theo dõi realtime trong lab:

~~~bash
az containerapp logs show \
  --resource-group "$RG" \
  --name gateway-api \
  --type console \
  --follow
~~~

Với nhiều revisions/replicas, cần chọn đúng revision và replica khi xem log hoặc sử dụng workspace để lọc theo nhãn. Logs console chủ yếu phản ánh stdout/stderr mà container phát ra; không đảm bảo ứng dụng đã được cấu hình structured logging hay correlation IDs.

### 12.3. Xem trạng thái revision và replica

~~~bash
az containerapp revision list \
  --resource-group "$RG" \
  --name gateway-api \
  --output json

az containerapp show \
  --resource-group "$RG" \
  --name gateway-api \
  --query "{latestRevision:properties.latestRevisionName, ingress:properties.configuration.ingress, template:properties.template}" \
  --output json
~~~

Một app ở trạng thái provisioning thành công vẫn có thể có container startup lỗi. Cần xem **revision health, replica readiness, log khởi động và image pull**.

### 12.4. Log Analytics

Tùy cấu hình environment và cách gửi log, ACA có thể gửi console/system logs vào Log Analytics. Những bảng thường gặp gồm `ContainerAppConsoleLogs_CL` và `ContainerAppSystemLogs_CL` với các trường phụ thuộc schema/chế độ ghi log.

Ví dụ truy vấn console logs ở workspace có bảng tương ứng:

~~~kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(1h)
| where ContainerAppName_s in ("gateway-api", "catalog-api")
| project TimeGenerated, ContainerAppName_s, RevisionName_s, Log_s
| order by TimeGenerated desc
~~~

**Quan trọng:** tên bảng/cột ở thực tế có thể thay đổi theo resource-specific/legacy schemas và pipeline của môi trường. Nếu bảng hoặc cột không tồn tại, kiểm tra schema thực tế trước khi sửa truy vấn; không suy “không có lỗi” chỉ từ kết quả rỗng.

### 12.5. Correlation ID và distributed tracing

Khi gateway gọi catalog, nên tạo/tiếp nhận **trace ID** và truyền ngữ cảnh theo chuẩn như W3C Trace Context:

~~~text
Client request
  trace_id = abc...
  gateway-api /products
    catalog-api /items
      database query
~~~

Sử dụng OpenTelemetry SDK và exporter phù hợp với hệ thống quan sát như Application Insights theo kiến trúc được hỗ trợ. Ghi thêm:

- `service.name`.
- Environment và revision identifier.
- HTTP route và status.
- Dependency latency và error category.
- Không log bearer token, password, connection string hay dữ liệu nhạy cảm không cần thiết.

**Không dựa duy nhất vào một dòng “500 error”**: cần biết request nào, revision nào, dependency nào và thời điểm nào.


## 13. Chẩn đoán lỗi khi triển khai hoặc gọi giữa các service

### 13.1. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Bằng chứng và bước kiểm tra |
| --- | --- | --- |
| App tạo xong nhưng image không pull được | Sai image ref, thiếu quyền ACR, registry private, identity chưa propagation | Xem system logs, ACR login server, image tag, identity và role |
| Container restart liên tục | Process crash, thiếu env vars, import lỗi, memory thấp | Console logs, startup command, replica status, CPU/memory |
| Gateway public trả 404 | Sai route `/products`, app không khởi động đúng code, ingress nhầm port | `curl /healthz`, route trong app, target port |
| Gateway trả 502/504 khi gọi catalog | Catalog không ready, DNS/ingress sai, timeout hoặc backend trả lỗi | Gateway logs, catalog logs, gọi thử nội bộ |
| `http://catalog-api` không phân giải | Hai apps khác environment, catalog chưa bật ingress hoặc cấu hình DNS khác | Đối chiếu environment ID, ingress và tên app |
| Catalog có ingress internal nhưng bị từ chối | Authentication/network controls hoặc caller không được phép | Kiểm tra policy, app auth, network và logs |
| Gateway public FQDN chưa truy cập được | Provisioning/ingress chưa sẵn sàng, FQDN sai, environment networking | Xem `properties.configuration.ingress.fqdn`, provisioning và environment |
| App trả lỗi sau đổi secret | Process chưa tải giá trị mới, quyền Key Vault sai | Kiểm tra identity, secret reference, restart/rollout |
| Replicas luôn ở minimum | Không có scale rule phù hợp, tải chưa đạt threshold hoặc metric không được hỗ trợ | Xem scale config và system metrics/logs |
| App scale về 0 rồi không “thức dậy” | Không có trigger đủ điều kiện, scaler không lấy được event metric | Kiểm tra KEDA scaler, min replicas, quyền queue |
| Event worker xử lý trùng | Message delivery thường có thể retry, consumer thiếu idempotency | Message IDs, deduplication, dead-letter |
| Canary cho kết quả lệch | Traffic weight chưa cập nhật hoặc test gọi revision FQDN trực tiếp | Kiểm tra revision list, ingress traffic, FQDN dùng khi test |
| Chi phí cao dù traffic thấp | min replicas giữ compute, nhiều revisions active, profile/Log Analytics | Kiểm tra replica count, workload profile, retention và billing |

### 13.2. Chẩn đoán theo tầng

Khi client gọi `https://<gateway-fqdn>/products` và nhận HTTP 502:

**Tầng 1 — Endpoint public**

- Gọi `GET /healthz` ở gateway.
- Xác nhận gateway ingress external, target port 8080 và FQDN đúng.
- Nếu `/healthz` cũng lỗi, tập trung vào gateway startup, ingress, TLS/provisioning.

**Tầng 2 — Gateway application**

- Đọc console logs để biết gateway có thực sự gửi request đến `CATALOG_URL` không.
- Xác minh `CATALOG_URL` trong cấu hình revision đang chạy; đừng chỉ nhìn bản deployment script.
- Kiểm tra HTTP timeout và exception category.

**Tầng 3 — Catalog internal service**

- Xác nhận `catalog-api` trong cùng environment.
- Kiểm tra internal ingress và revision health.
- Xem `GET /items` từ đường mạng/workload được phép.
- Đọc logs catalog và kiểm tra dependency.

**Tầng 4 — Downstream**

Nếu catalog truy cập database, kiểm tra managed identity, DNS, private endpoint, firewall, connection pool và SQL metrics. Không tăng `maxReplicas` chỉ để che SQL timeout.

### 13.3. Startup/readiness khác app resource tồn tại

Một tài nguyên ACA hiển thị tồn tại không có nghĩa HTTP process đang sẵn sàng:

- Image có thể chưa được pull.
- Container đang khởi động hoặc crash loop.
- Process chỉ lắng nghe `127.0.0.1` thay vì `0.0.0.0`.
- Target port khác với port thật của process.
- Liveness/readiness probe cấu hình sai có thể gây restart hoặc không đưa replica nhận traffic.
- Một dependency bắt buộc có thể chưa sẵn sàng.

Với FastAPI ví dụ, `uvicorn` chạy `--host 0.0.0.0 --port 8080` để ingress ACA có thể chuyển tiếp đúng. Nếu đổi port trong Dockerfile hoặc entrypoint phải cập nhật `--target-port`.

## 14. Thiết kế độ tin cậy giữa microservices

### 14.1. Timeouts, retries và idempotency

Gọi service đồng bộ cần giới hạn thời gian chờ. Ví dụ gateway dùng timeout 5 giây khi gọi catalog. Nếu catalog không phản hồi, gateway trả 504 thay vì giữ request vô hạn.

Tuy nhiên, **retry** phải có chủ đích:

- Với HTTP GET idempotent, có thể retry giới hạn số lần nếu lỗi tạm thời.
- Với HTTP POST tạo đơn, retry mù quáng có thể tạo trùng đơn.
- Sử dụng **idempotency key**, backoff với jitter và timeout budget.
- Giới hạn số retries để tránh làm tải lên một service đang hỏng tăng thêm.
- Có thể dùng circuit breaker hoặc cache/stale fallback khi nghiệp vụ phù hợp.

### 14.2. Health check theo vai trò

| Endpoint | Mục tiêu | Ví dụ |
| --- | --- | --- |
| `/healthz` | Process còn sống | Trả 200 nhanh, không phụ thuộc quá nhiều hệ thống |
| `/ready` | Service sẵn sàng nhận request mới | Khởi tạo xong, dependency thiết yếu có thể dùng |
| `/metrics` | Xuất telemetry theo công cụ hỗ trợ | Không nên công khai dữ liệu nhạy cảm |
| `/items` | Business API | Có logic và dependency thực |

Trong ACA, liveness/readiness/startup probes có thể được định nghĩa theo kiểu container probe được hỗ trợ. **Đừng coi chỉ tạo URL `/healthz` trong code là đã tự cấu hình probe Azure.** Cần xác minh template có probes và các ngưỡng phù hợp.

### 14.3. Container Apps Job và long-running workloads

Nếu một tác vụ chỉ cần chạy theo sự kiện, lịch hoặc lệnh thủ công rồi hoàn tất, **Container Apps Jobs** có thể phù hợp hơn một Container App luôn chạy HTTP server.

| Tình huống | Lựa chọn đáng cân nhắc |
| --- | --- |
| API xử lý HTTP liên tục | Container App với ingress |
| Consumer queue chạy dài, scaling theo backlog | Container App không ingress với KEDA event scaler |
| Import dữ liệu chạy theo lịch rồi thoát | Container Apps Job scheduled |
| Migration/manual batch run | Container Apps Job manual |
| Task theo queue cần run-to-completion | Container Apps Job event-driven khi phù hợp |

Chọn dựa trên xử lý lỗi, thời lượng, retry, concurrency và cơ chế hoàn tất; không cần ép mọi loại công việc thành API HTTP.

### 14.4. Dapr là tùy chọn, không bắt buộc

**Distributed Application Runtime (Dapr)** cung cấp những building blocks như service invocation, pub/sub, state management hoặc bindings thông qua sidecar và components được cấu hình.

Dapr có thể giúp chuẩn hóa tương tác đa ngôn ngữ, nhưng:

- Cần chọn đúng component backend và authentication.
- Tăng lượng cấu hình, log và khả năng vận hành phải kiểm soát.
- Không làm API contract hay dữ liệu tự động nhất quán.
- Không tự giải quyết mọi yêu cầu idempotency/transaction.
- **Không cần bật Dapr** chỉ để dùng service discovery `http://catalog-api` trong cùng ACA environment như ví dụ.

### 14.5. API versioning và database migration

Một đội triển khai `catalog-api:v2` trong khi `gateway-api:v1` còn hoạt động. Nếu v2 xóa trường JSON mà gateway v1 vẫn dùng, canary có thể gây lỗi dù cả hai container đều Healthy.

Nên:

1. Định nghĩa API contract và schema.
2. Thực hiện **backward-compatible changes** trước.
3. Dùng contract/integration tests giữa các service.
4. Chỉ gỡ trường cũ khi tất cả consumers đã nâng version.
5. Tách database migration thành các bước có thể rollback phù hợp.
6. Kiểm tra retry/duplicate processing trong giai đoạn nhiều versions chạy song song.

## 15. Bảo mật production: từ image tới runtime

### 15.1. Bảo vệ supply chain của image

- Dùng ACR hoặc registry có quyền truy cập kiểm soát.
- Tách quyền **push** của CI/CD khỏi quyền **pull** của ACA runtime.
- Dùng image tags/digests rõ ràng, không dựa vào `latest` cho triển khai có yêu cầu kiểm toán.
- Quét dependency/image theo quy trình bảo mật.
- Hạn chế image size, dùng non-root user khi app tương thích.
- Không đóng gói private key, token, password hay `.env` production vào image.
- Xây quy trình ký/xác minh artifact và kiểm soát đường build nếu tổ chức yêu cầu.

### 15.2. Quyền cho môi trường và ứng dụng

Các role phải phân tách theo nhiệm vụ:

| Nhóm | Quyền cần | Không nên mặc định có |
| --- | --- | --- |
| Developer | Đọc logs, deploy app trong Dev | Quyền thay toàn production network |
| CI/CD deployment principal | Update Container Apps/registry đúng scope | Owner toàn subscription |
| Workload identity | Pull image, đọc secrets/data đúng nghiệp vụ | Push image hoặc tạo role assignments |
| SOC/SRE | Metrics, logs, incident operations | Quyền đọc secrets hoặc xóa environment |
| FinOps | Cost visibility, budget/alerts | Quyền sửa business data |

Managed identity chỉ là danh tính; Azure RBAC phải cấp đúng role tại đúng resource và, khi cần, dữ liệu qua data-plane phải được phân quyền riêng.

### 15.3. Ingress không thay thế authentication

External ingress public cần:

- TLS/HTTPS được cấu hình và quản lý chứng chỉ phù hợp.
- Authentication/authorization, API gateway hoặc identity proxy khi nghiệp vụ yêu cầu.
- Rate limiting, WAF hoặc các biện pháp bảo vệ L7 thích hợp.
- CORS phù hợp nhưng không coi CORS là cơ chế xác thực.
- Quản lý custom domain, DNS và certificate rotation.

Internal ingress vẫn cần xác định **trust boundary**: app nào được phép gọi, token/service identity nào được chấp nhận, dữ liệu nào được phép xem hoặc thay đổi.

### 15.4. Secrets và cấu hình theo môi trường

- Dev/Staging/Prod có secrets khác nhau và identity tương ứng.
- Production secrets không để trong repo hoặc command logs.
- Đặt scope truy cập Key Vault/Storage/Service Bus tối thiểu.
- Thử rotation và recovery, không đợi đến khi secret hết hạn.
- Không in toàn bộ env vars vào logs khi có thể chứa secrets.

### 15.5. Resource limits và bảo vệ downstream

Giới hạn CPU/memory cho mỗi replica để tránh cấu hình không tương thích hoặc vượt ngân sách. Nhưng nếu memory quá thấp, container có thể bị OOM hoặc restart liên tục.

Khi tăng max replicas, kiểm tra tổng số connections, hàng đợi, số consumers và quota của backend. **Scale out không làm Database hoặc Service Bus tự tăng capacity.**

## 16. Chi phí và lựa chọn workload profile

### 16.1. Những chi phí có thể xuất hiện

Một kiến trúc ACA có thể phát sinh phí từ:

| Thành phần | Yếu tố chi phí cần kiểm tra |
| --- | --- |
| Container Apps compute | vCPU/memory usage, số replicas, workload profile và cách tính phí |
| HTTP requests | Mô hình tính phí theo gói/điều kiện dịch vụ nếu áp dụng |
| Dedicated workload profile | Năng lực compute provisioned và mức sử dụng theo mô hình profile |
| Azure Container Registry | SKU, lưu images, build/tasks và networking |
| Log Analytics/Monitor | Dữ liệu nạp, retention, alert và observability |
| Network | VNet, private endpoint, egress/NAT, data transfer |
| Service Bus/Storage/Database | Tài nguyên phụ thuộc và transactions |
| Nhiều revisions active | Compute có thể chạy song song khi canary |
| Min replicas > 0 | Replicas duy trì hoạt động khi ít traffic |

**Pricing thay đổi theo region, workload profile, plan và thời điểm.** Không dùng một con số giá cố định trong bài học để cam kết chi phí sản xuất.

### 16.2. Consumption so với dedicated workload profiles

- **Consumption:** thích hợp khi muốn scale linh hoạt theo tải, có thể scale-to-zero khi có trigger hỗ trợ; cách tính compute/request theo chính sách áp dụng.
- **Dedicated workload profiles:** có thể phù hợp khi cần năng lực ổn định, đặc điểm compute/mạng hoặc cách tổ chức chi phí phù hợp, với mô hình tính tiền riêng.

Khi chọn, cần xem region, nhu cầu tài nguyên, scale bounds, thời gian idle, mô hình networking và profile hỗ trợ. Không mặc định **Consumption luôn rẻ hơn** hoặc dedicated luôn nhanh hơn: hãy đo workload thật và dùng công cụ dự toán giá.

### 16.3. Tính quy mô bằng Little's Law

Giả sử:

~~~text
Incoming rate:       200 requests/giây
Average latency:     0,25 giây
Concurrency trung bình ≈ 200 × 0,25 = 50 requests
~~~

Nếu một replica an toàn ở khoảng 10 request đồng thời trong SLO, cần ít nhất khoảng **5 replicas theo mô hình lý tưởng**, chưa có headroom.

Nếu trong giờ cao điểm latency tăng lên 1 giây do database chậm thì concurrency có thể lên **200**; tăng replicas mà không xử lý database có thể làm backlog lớn hơn và phát sinh thêm phí.

Vì vậy hãy sizing theo:

- Request rate/concurrency thực.
- CPU/memory của mỗi replica.
- p95/p99 latency và tỷ lệ lỗi.
- Headroom và thời gian warm-up.
- Database connections, queue consumers và service quotas.
- Max replicas phù hợp cả chi phí và downstream.

### 16.4. Giảm chi phí không phá SLO

- Dùng `minReplicas=0` cho các service chịu được cold start và có trigger phù hợp.
- Dùng `minReplicas=1` hoặc cao hơn cho endpoint yêu cầu độ trễ thấp ổn định.
- Giới hạn max replicas theo kiểm thử backend.
- Không lưu quá nhiều images/tags hoặc giữ nhiều revisions active không cần thiết.
- Điều chỉnh log retention, sampling và verbosity phù hợp yêu cầu kiểm toán.
- Dùng Cost Management budgets và cảnh báo chi phí.
- Dọn dẹp tài nguyên lab sau khi học xong bằng danh sách đã xác minh.

## 17. Bài thực hành tổng hợp

### 17.1. Kịch bản

Nhóm Dev muốn triển khai:

- `catalog-api` phục vụ dữ liệu nội bộ, 1–3 replicas.
- `gateway-api` public HTTPS, 1–5 replicas.
- Images trên ACR, pull bằng managed identity.
- Hai ứng dụng cùng environment.
- Có khả năng phát hành gateway v2 và kiểm tra canary.
- Theo dõi log lỗi và chi phí.

**Tiêu chí hoàn thành:** gọi HTTPS `/products` ở gateway trả được dữ liệu catalog, catalog không có public ingress trực tiếp, và bạn giải thích được cách cấu hình scale và rollback.

### 17.2. Checklist thao tác

| Bước | Tác vụ | Bằng chứng |
| --- | --- | --- |
| 1 | Chọn subscription và kiểm tra quyền | `az account show` đúng |
| 2 | Tạo environment/ACR lab | Resources hiện đúng region/resource group |
| 3 | Build/push `catalog-api:v1` và `gateway-api:v1` | Hai image tags có trong ACR |
| 4 | Cấp identity và quyền pull phù hợp | Không cần dùng ACR admin password |
| 5 | Triển khai catalog với internal ingress | App có revision healthy, target port 8080 |
| 6 | Triển khai gateway với external ingress và `CATALOG_URL` | Có public HTTPS FQDN |
| 7 | Gọi `GET /healthz` và `GET /products` | HTTP 200, response đúng |
| 8 | Kiểm tra min/max replicas và logs | Đọc được template và console logs |
| 9 | Build/push v2, bật multiple revision và canary | Hai revisions có traffic weights |
| 10 | Rollback về v1 khi có lỗi giả định | Ingress traffic trả 100% về v1 |
| 11 | Kiểm tra resource usage và phí | Có ước lượng chi phí, budget |
| 12 | Dọn lab khi được phép | Không xóa nhầm resources của nhóm khác |

### 17.3. Câu hỏi tình huống A — Gateway trả 502

Gateway `/healthz` trả 200, nhưng `/products` trả 502. Catalog logs cho thấy process chưa khởi động đúng port.

**Hỏi:** lỗi chủ yếu nằm ở đâu?

**Gợi ý:** không phải frontend TLS hay mã FastAPI `/healthz` của gateway. Kiểm tra target port 8080 của catalog, process binding `0.0.0.0`, revision health và console logs, rồi gọi nội bộ từ gateway.

### 17.4. Câu hỏi tình huống B — Scale lên 10 replicas rồi SQL lỗi

Một service ban đầu có 2 replicas, mỗi replica tối đa 30 SQL connections. Khi scale lên 10, số kết nối tiềm năng:

\[
10\times30=300
\]

Nếu database chỉ chịu an toàn khoảng 150 connections theo số liệu kiểm thử, cách tăng replicas này có thể gây contention hoặc timeout.

**Đáp án:** điều chỉnh connection pooling, concurrency, database capacity và max replicas; không mặc định max lớn hơn luôn tốt hơn.

### 17.5. Câu hỏi tình huống C — Canary 10% vẫn thấy lỗi trên v1

`gateway-api:v2` chỉ được gán 10% ingress traffic, nhưng database migration làm thay đổi schema khiến v1 cũng lỗi.

**Bài học:** traffic splitting ở gateway không cô lập mọi thay đổi chung. Database schema, queues và data contracts cần được thiết kế tương thích nhiều phiên bản.

### 17.6. Câu hỏi tình huống D — Worker nhận message hai lần

Service `orders-worker` xử lý một đơn hàng, rồi bị restart trước khi xác nhận message đã hoàn tất. Queue redeliver cùng message.

**Đáp án:** consumer phải có cơ chế **idempotency** theo order ID/message ID và chỉ hoàn tất message theo đúng semantics; retry và dead-letter phải được xử lý có kiểm soát.

### 17.7. Câu hỏi tình huống E — Chọn minReplicas

| Workload | Phương án cân nhắc |
| --- | --- |
| API thanh toán cần p99 thấp, không được cold start | Giữ min replicas > 0 và có headroom |
| Worker chỉ chạy vài lần một ngày theo queue | Có thể min=0 nếu event scaler phù hợp |
| Catalog được nhiều API gọi liên tục | Min replicas theo tải thật, không chỉ theo chi phí idle |
| Batch import chạy theo lịch rồi kết thúc | Đánh giá Container Apps Job |

Không có một giá trị min replicas tối ưu cho mọi service. Quyết định phải gắn với SLO, tính chất trigger và chi phí.

## 18. Dọn dẹp và bảo vệ môi trường thực hành

### 18.1. Chỉ dọn tài nguyên đã xác minh thuộc lab

Sau khi thử nghiệm, ghi lại danh sách App, environment, ACR, identity, Log Analytics workspace và role assignments được tạo. Nếu resource group `rg-aca-lab` **chỉ chứa tài nguyên do bài lab tạo** và đã được xác minh không còn workload khác sử dụng, có thể xóa resource group theo quy trình được phép.

~~~bash
# CHỈ ĐỌC để kiểm tra trước khi dọn.
az resource list \
  --resource-group "$RG" \
  --output table
~~~

Ví dụ lệnh dọn tài nguyên là **thao tác phá hủy dữ liệu** và không nên chạy khi chưa xác minh tuyệt đối phạm vi:

~~~bash
# Chỉ chạy khi RG chỉ chứa tài nguyên lab và được phê duyệt xóa.
az group delete \
  --name "$RG" \
  --yes
~~~

Không chạy lệnh này với resource group chứa tài nguyên dùng chung. Nếu environment hoặc ACR được sử dụng bởi service khác, hãy xóa từng tài nguyên lab đã được định danh và kiểm tra dependencies trước.

### 18.2. Kiểm tra sau khi dọn

- Không còn resource compute/registry lab đang phát sinh phí không mong muốn.
- Role assignments và identities được rà soát theo quy trình.
- Không còn secrets hoặc test data nhạy cảm trong logs/artifacts.
- Dữ liệu cần giữ lại đã được backup hoặc xuất theo chính sách.
- Cost Management không còn mức chi phí bất thường từ môi trường thực hành.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Container Apps environment khác Container App thế nào?

**Trả lời:** Environment là bối cảnh triển khai dùng chung liên quan mạng/observability/workload profiles; Container App là tài nguyên ứng dụng định nghĩa image, ingress, secrets, identities, revisions và scaling.

**Câu 2.** Một app có một revision nhưng bốn replicas. Vậy có bao nhiêu phiên bản cấu hình được triển khai?

**Trả lời:** Một revision được chạy ở bốn replicas; số replica không đồng nghĩa số revision.

**Câu 3.** Vì sao dùng `--ingress internal` cho `catalog-api` chưa đủ đảm bảo chỉ `gateway-api` được gọi?

**Trả lời:** Internal ingress giới hạn phạm vi tiếp cận theo cấu hình mạng, nhưng không tự xác thực và ủy quyền identity của caller. Cần kiểm soát trust boundary và auth nếu nghiệp vụ yêu cầu.

**Câu 4.** Nếu hai app trong cùng ACA environment, gateway thường gọi catalog bằng gì?

**Trả lời:** Với ingress được cấu hình phù hợp, có thể dùng URL nội bộ dạng `http://catalog-api` thông qua service discovery của ACA, thay vì quản lý IP replica.

**Câu 5.** Managed identity được gắn với app nhưng vẫn không pull được ACR image. Tại sao?

**Trả lời:** Identity cần đúng quyền pull theo ACR permission mode và đúng scope; role assignment còn có thể đang lan truyền, hoặc image reference/network không đúng.

**Câu 6.** Khi thay image `gateway-api:v1` thành `gateway-api:v2`, hành vi nào xảy ra?

**Trả lời:** Thay container image trong revision template sẽ tạo một revision mới theo cơ chế ACA; cần kiểm tra health và traffic routing. Không đồng nghĩa old revision bị xóa ngay.

**Câu 7.** KEDA HTTP concurrency 50 có nghĩa service tự scale ở 50 requests/giây không?

**Trả lời:** Không. Concurrency là số request đồng thời; requests/giây còn phụ thuộc thời gian xử lý và lưu lượng.

**Câu 8.** Vì sao `minReplicas=0` có thể gây latency cao cho request đầu?

**Trả lời:** Service phải khởi tạo replica từ trạng thái zero khi trigger có hiệu lực; có thể có cold start và thời gian warm-up.

**Câu 9.** Khi rollout 90/10 giữa v1 và v2, có thể ngay lập tức xóa v1 không?

**Trả lời:** Không nên. Giữ v1 active giúp rollback khi cần; trước khi xóa cần xác minh health, data compatibility, traffic và tài nguyên phụ thuộc.

**Câu 10.** Vì sao scale out worker từ 2 lên 10 có thể làm database kém ổn định?

**Trả lời:** Tổng số kết nối/requests đồng thời tới database có thể tăng nhanh, vượt giới hạn của backend; cần kiểm soát concurrency, pooling và capacity.

**Câu 11.** Container Apps Jobs phù hợp với loại tác vụ nào?

**Trả lời:** Những tác vụ run-to-completion, kích hoạt thủ công, theo lịch hoặc event theo khả năng dịch vụ, thay vì server HTTP luôn lắng nghe.

**Câu 12.** Vì sao thay một secret không chắc tạo revision mới hoặc cập nhật process đang chạy ngay lập tức?

**Trả lời:** Secrets có phạm vi cấu hình cấp app và ứng dụng có thể chỉ đọc khi startup; cần quy trình restart/rollout và xác minh secret reference.

## Ghi nhớ

- **Azure Container Apps** giúp chạy microservices dưới dạng container mà không cần tự vận hành Kubernetes cluster.
- **Container Apps environment** chứa nhiều apps; mỗi app có **revisions** và từng revision có **replicas** được điều chỉnh bởi scaling.
- Dùng **external ingress** cho điểm vào cần công khai, **internal ingress** cho dịch vụ nội bộ, nhưng vẫn thiết kế xác thực/ủy quyền và mạng riêng khi cần.
- Lưu images trong **ACR**, dùng **managed identity** và phân quyền pull tối thiểu; không đưa credentials vào image hoặc script.
- **KEDA scaling** dựa trên concurrency/queue/event; `minReplicas=0` có thể tiết kiệm chi phí nhưng phải chấp nhận cold start và đúng trigger.
- **Multiple revisions + traffic splitting** giúp canary và rollback, nhưng không tự bảo vệ khỏi schema migration hoặc event contract breaking changes.
- Microservices đáng tin cậy cần **stateless design, timeout, retries có giới hạn, idempotency, health checks, logs, metrics và tracing**.
- Luôn xác minh **SLO, quyền truy cập, region/networking, ngân sách và chi phí** trước và sau khi triển khai.
