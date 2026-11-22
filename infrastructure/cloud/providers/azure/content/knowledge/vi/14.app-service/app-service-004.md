# Triển khai container lên App Service

Một ứng dụng web có thể chạy tốt trên laptop nhưng gặp lỗi khi chuyển lên cloud vì phiên bản runtime khác, thiếu thư viện hệ điều hành, cấu hình cổng sai hoặc môi trường không cho phép ghi file vào vị trí ứng dụng mong đợi. Đóng gói ứng dụng thành **container image** giúp mô tả tương đối nhất quán những thành phần cần thiết để chạy chương trình. **Azure App Service** cho phép triển khai một ứng dụng web/API bằng image đó trên nền tảng được Azure quản lý, thay vì phải tự cấp phát và bảo trì máy ảo hoặc dựng một cụm Kubernetes chỉ để chạy một dịch vụ nhỏ.

Trong chương **Ứng dụng web với App Service** thuộc module **CLOUD_PROVIDERS_AZURE**, bài học này hướng dẫn cách xây dựng, kiểm thử, lưu trữ và triển khai **Linux custom container** lên **Azure App Service**, đặc biệt qua **Azure Container Registry (ACR)**. Toàn bộ quy trình gắn với những phần khác của module: subscription/resource group để tổ chức tài nguyên, Microsoft Entra ID/managed identity để phân quyền, mạng ảo và Private Endpoint để kết nối dữ liệu, Azure Monitor để giám sát, và Azure Cost Management để kiểm soát chi phí.

Sau bài học, bạn có thể:

- Phân biệt Dockerfile, image, container, registry, App Service Plan và Web App.
- Xây dựng image web tối giản, kiểm thử tại máy phát triển và đẩy image lên ACR.
- Triển khai custom container từ ACR vào Linux Web App, cấu hình cổng và app settings.
- Thiết lập cơ chế **managed identity** để App Service kéo private image mà không lưu mật khẩu registry dài hạn.
- Giải thích startup, health check, scale-out, rolling release và deployment slot.
- Thiết kế truy cập mạng, bảo mật, lưu trữ trạng thái, logging, xử lý lỗi image pull và tối ưu chi phí.

## 1. Vì sao triển khai container trên App Service?

Azure App Service là nền tảng PaaS để chạy website và API, cung cấp các khả năng như điểm vào HTTPS, cấu hình ứng dụng, domain, chứng chỉ, scale, monitoring và triển khai. Ở mô hình **built-in runtime**, bạn triển khai source/artifact và App Service quản lý runtime được hỗ trợ. Ở mô hình **custom container**, bạn chịu trách nhiệm xây dựng image có runtime, thư viện và ứng dụng, còn App Service quản lý nền tảng host và vòng đời chạy container theo khả năng dịch vụ.

Ví dụ API Java dùng thư viện native, một ứng dụng Node.js có các package đặc thù, hoặc một server Python cần phiên bản hệ điều hành cụ thể. Đóng gói chúng trong image giúp đưa cùng artifact qua dev, test và production; tuy vậy vẫn phải kiểm tra khác biệt về app settings, identity, network, filesystem, scaling và dữ liệu.

| Cách chạy | Bạn triển khai | Azure quản lý chính | Khi phù hợp |
|---|---|---|---|
| App Service built-in runtime | Mã nguồn/package ứng dụng | Runtime hỗ trợ và nền tảng App Service | Ứng dụng dùng stack/runtime được hỗ trợ, muốn tối giản Docker |
| **App Service custom container** | **Image đã build** và cấu hình Web App | Nền tảng chạy container, HTTPS edge, scale và nhiều tính năng PaaS | Cần đóng gói runtime/dependency tùy biến, ứng dụng web/API |
| Azure Container Apps | Image + mô hình container app/revision | Nền tảng container có các khả năng dành cho microservice, autoscaling theo cơ chế được hỗ trợ | Các workload container cần nhiều kiểu scale, service-to-service, background processing |
| Azure Kubernetes Service (AKS) | Workload và cấu hình Kubernetes | Control plane được quản lý; nhiều phần cluster/workload vẫn do bạn vận hành | Cần Kubernetes API, scheduling và hệ sinh thái điều phối phức tạp |
| Azure VM | OS, runtime, container engine và app | Hạ tầng compute bên dưới | Yêu cầu kiểm soát host/OS vượt phạm vi PaaS |

**Không có một lựa chọn luôn tốt nhất.** App Service custom container hợp lý cho web/API có thể chạy trong một container theo mô hình dịch vụ. Nếu workload cần nhiều container phối hợp phức tạp, daemon chạy đặc quyền, custom host networking, tác vụ batch đặc thù hoặc điều phối Kubernetes chuyên sâu, cần đánh giá Container Apps/AKS/VM thay vì cố ép tất cả vào Web App.

### Trách nhiệm chia sẻ

| Hạng mục | Trách nhiệm nhóm ứng dụng | Trách nhiệm nền tảng Azure |
|---|---|---|
| Application code | Phát triển, vá lỗi, bảo mật dữ liệu | Không tự sửa bug ứng dụng |
| Container image | Chọn base image, cập nhật OS package, quét CVE, ký/pin artifact | Cung cấp môi trường App Service để chạy image |
| Runtime app | Chọn entrypoint, listener, cổng, health endpoint | Khởi chạy/giám sát container theo cấu hình dịch vụ |
| Dữ liệu và secret | Phân quyền, Key Vault, backup, dữ liệu lưu bền | Cung cấp dịch vụ lưu trữ/bảo mật theo cấu hình chọn |
| Network | Cấu hình inbound/outbound, identity, access restrictions | Hạ tầng mạng và tính năng PaaS |
| Scale và SLA | Chọn plan/SKU, số instance, health và kiến trúc ứng dụng | Vận hành các khả năng sẵn sàng của dịch vụ tương ứng |

Container image **không tự miễn trách nhiệm cập nhật hệ điều hành**: nếu image dùng base chứa lỗ hổng, đội phát triển phải build và triển khai image mới. Azure không tự rebuild Dockerfile của bạn chỉ vì base image có bản phát hành mới.

## 2. Luồng triển khai từ source tới người dùng

Một hệ thống ví dụ gồm repository chứa source và Dockerfile, quy trình build, Azure Container Registry và Azure App Service:

~~~mermaid
flowchart LR
    DEV[Source code + Dockerfile] --> CI[Build/test/scan image]
    CI --> ACR[Azure Container Registry]
    ACR -->|Pull image| APP[Azure App Service Linux Web App]
    USER[Người dùng HTTPS] --> APP
    APP -->|Managed identity / dữ liệu| KV[Key Vault]
    APP -->|Private/network access| DB[(Azure SQL / Storage)]
    APP -. Logs + metrics .-> OBS[Azure Monitor / App Insights]
    ADMIN[Entra ID + Azure RBAC] -. Quản trị .-> ACR
    ADMIN -. Quản trị .-> APP
~~~

Diễn giải:

1. Developer thay đổi source, Dockerfile và unit tests.
2. CI kiểm thử, quét dependency/image rồi build **Linux image**.
3. Image được tag theo phiên bản hoặc commit, đẩy lên private registry như **ACR**.
4. Web App được cấu hình tham chiếu đúng image/tag (hoặc digest trong quy trình hỗ trợ).
5. App Service cần **kết nối registry và quyền pull**, sau đó khởi tạo container trên các worker.
6. Container lắng nghe đúng IP/cổng; App Service định tuyến HTTP/HTTPS từ frontend đến container.
7. App settings/managed identity/networking cấp quyền kết nối dữ liệu; logs và metrics phục vụ giám sát.

**Một bản build image thành công không đồng nghĩa triển khai thành công.** Registry có thể từ chối quyền pull, app có thể crash lúc startup hoặc cổng bị sai. Từng ranh giới phải có phép kiểm chứng riêng.

### Các thành phần cần nhớ

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Dockerfile** | Công thức build image | Chọn Node/Python/Java base, copy mã, khai báo startup |
| **Image** | Artifact bất biến ở cấp digest | `orders-api:1.0.0` |
| **Container** | Tiến trình chạy từ một image | App Service khởi tạo instance ứng dụng |
| **Registry** | Lưu image/repository và tags | `myregistry.azurecr.io/orders-api:1.0.0` |
| **App Service Plan** | Compute capacity, OS, region, SKU và scale của Web App | Linux plan `asp-orders-prod` |
| **Web App** | Tài nguyên ứng dụng, image config, settings, URL, identity | `app-orders-prod` |
| **Managed identity** | Danh tính workload được Entra quản lý | Web App pull image và đọc secret với quyền riêng |
| **Health Check** | Đánh giá instance đủ điều kiện theo HTTP endpoint | `/health` |

Image tag là tên tham chiếu có thể bị cập nhật trỏ sang digest khác nếu pipeline cho phép. Khi cần khả năng tái hiện/rollback, quản lý chính xác **image digest** và chính sách tag bất biến, không chỉ một tên `latest`.

## 3. Chuẩn bị Dockerfile đúng cho App Service

Ví dụ bài học sử dụng **Node.js HTTP server chỉ dùng thư viện chuẩn**, để người học nhìn rõ cổng, quá trình khởi động và hành vi health check. Ứng dụng thực tế có thể là Spring Boot, ASP.NET Core, Python, Go hoặc runtime khác, miễn image chạy phù hợp với yêu cầu App Service.

### 3.1. File `server.js`

~~~javascript
const http = require("node:http");

// App Service forward HTTP traffic tới cổng được cấu hình.
// Trong ví dụ, PORT của ứng dụng và WEBSITES_PORT phải khớp.
const port = Number(process.env.PORT || 8080);

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ready" }));
    return;
  }

  if (req.url === "/") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      service: "azure-app-service-container-demo",
      message: "Hello from a Linux custom container"
    }));
    return;
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "not-found" }));
});

server.listen(port, "0.0.0.0", () => {
  console.log("HTTP server started on port " + port);
});

process.on("SIGTERM", () => {
  console.log("Shutdown requested");
  server.close(() => process.exit(0));
});
~~~

**Vì sao bind `0.0.0.0`?** Nếu ứng dụng chỉ nghe trên `127.0.0.1` bên trong container, lưu lượng từ hạ tầng App Service tới network interface của container có thể không kết nối được. Phải lắng nghe địa chỉ phù hợp với container network và sử dụng port khớp cấu hình forwarding.

`/health` trong demo chỉ xác nhận HTTP server đang phản hồi. Production nên thiết kế readiness phản ánh những dependency thiết yếu; không tạo endpoint gọi đồng bộ hàng loạt dịch vụ bên ngoài khiến một sự cố chung loại tất cả instance khỏi pool.

### 3.2. File `Dockerfile`

~~~dockerfile
# Chọn base image được duy trì và kiểm tra digest cho production.
FROM node:22-alpine

ENV NODE_ENV=production
ENV PORT=8080

WORKDIR /app
COPY --chown=node:node server.js /app/server.js

# Tránh chạy ứng dụng bằng root nếu không có nhu cầu.
USER node

# EXPOSE chỉ là metadata; ứng dụng vẫn phải thực sự listen.
EXPOSE 8080

CMD ["node", "server.js"]
~~~

Trong production, nên **pin base image theo digest**, rà soát thời gian hỗ trợ Node/image và rebuild khi có bản vá. `node:22-alpine` là một ví dụ học tập, không phải cam kết nó luôn là base mới nhất hay phù hợp với mọi native dependency. Với Java, Python hoặc .NET, có thể dùng multi-stage build để giảm kích thước runtime image, bỏ build tool và giới hạn quyền trong container.

### 3.3. Build và chạy thử local

Ở thư mục chỉ chứa `server.js` và `Dockerfile`:

~~~bash
docker build -t appservice-demo:1.0.0 .

# Port host 8080 chuyển vào container 8080.
docker run --rm --name appservice-demo-local \
  -p 8080:8080 appservice-demo:1.0.0
~~~

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/health
~~~

Kỳ vọng hai endpoint trả HTTP 200, `/` có JSON mô tả dịch vụ và `/health` trả `{"status":"ready"}`. Nếu chạy Docker local thất bại, hãy sửa trước khi đưa lên cloud: App Service không giải quyết được lỗi syntax, CMD sai, thiếu file hoặc listener không chạy.

### 3.4. Thử startup và shutdown

- `docker logs appservice-demo-local` phải cho thấy dòng khởi động mong đợi.
- Khi gửi `SIGTERM`, server dừng nhận kết nối và đóng listener theo logic chương trình.
- Đừng ghi dữ liệu cần giữ vào filesystem trong container rồi mặc định nó tồn tại sau restart.
- Không đưa secret vào `Dockerfile`, build argument được lưu trong image metadata hoặc source code.
- Đảm bảo image được build cho kiến trúc CPU mà App Service Linux hỗ trợ; image ARM được tạo trên laptop có thể không chạy trên worker x86_64.

Kiểm tra image:

~~~bash
docker image inspect appservice-demo:1.0.0 \
  --format '{{.Os}}/{{.Architecture}}'
~~~

Ví dụ mong đợi là `linux/amd64` cho một môi trường Linux x86_64 tương thích. Với máy phát triển Apple Silicon/ARM, cần build image cho platform mục tiêu hoặc dùng ACR Tasks/CI runner phù hợp thay vì giả định image local chạy được ở Azure.

## 4. App Service Plan và Web App: hai tài nguyên khác nhau

**App Service Plan** xác định công suất compute dùng chung và các đặc tính như OS Linux, region, tier, số worker và scale. **Web App** là cấu hình ứng dụng nằm trên một plan: image, domain, app settings, identity, health check, logging và deployment.

~~~mermaid
flowchart TB
    SUB[Subscription] --> RG[Resource group]
    RG --> PLAN[Linux App Service Plan]
    PLAN --> WEB1[Web App orders-api]
    PLAN --> WEB2[Web App internal-api]
    WEB1 --> IMAGE1[Image ACR orders-api]
    WEB2 --> IMAGE2[Image ACR internal-api]
~~~

Một plan có thể chứa nhiều app tương thích, chia sẻ compute. Khi hai app dùng chung plan, lưu lượng hoặc tác vụ CPU nặng của một app có thể gây ảnh hưởng đến app khác nếu không dự phòng công suất; scale plan có thể tác động chi phí chung. Ngược lại, tách plan giúp cô lập workload quan trọng nhưng tăng số nguồn chi phí.

### Các tiêu chí chọn plan

| Tiêu chí | Cần quyết định |
|---|---|
| Hệ điều hành | **Linux** khi dùng Linux custom container |
| Region | Gần người dùng/data source; cân nhắc latency, tính năng khả dụng và residency |
| SKU | Đủ CPU/RAM, scale, deployment slots, networking và SLA; không chỉ chọn thấp nhất |
| Số instance | Một instance cho lab; production thường cần nhiều instance nếu SLO yêu cầu |
| App placement | App nào có thể dùng chung plan mà không ảnh hưởng hiệu năng/bảo mật |
| Quản lý cấu hình | Resource group/subscription/tag, Azure Policy, IaC, quy trình deployment |

Không nên đưa tất cả ứng dụng có mức độ quan trọng khác nhau vào một plan chỉ vì chúng cùng ngôn ngữ lập trình. Khi cần **deployment slots**, phải chọn tier có hỗ trợ (thường Standard/Premium trở lên trong mô hình App Service phù hợp); một plan Basic dùng cho lab không nên được mặc định là có slot.

## 5. Azure Container Registry: lưu image cho Azure

**Azure Container Registry (ACR)** là private container registry. Một repository có thể có nhiều tag và manifest/digest:

~~~text
myregistry.azurecr.io/appservice-demo:1.0.0
myregistry.azurecr.io/appservice-demo:1.0.1
myregistry.azurecr.io/appservice-demo:commit-abc1234
~~~

Ở đây:

- `myregistry.azurecr.io` là **login server**.
- `appservice-demo` là repository.
- `1.0.0` là tag; image được xác định chính xác hơn bằng digest.

Khi phát hành production, ưu tiên đặt tag theo build/commit, kiểm thử artifact và giữ thông tin digest. Không dùng `latest` làm nguồn sự thật duy nhất, bởi một image mới được đẩy lên `latest` không bảo đảm mọi instance cập nhật cùng lúc hoặc cho phép rollback có thể dự đoán.

### Các bước kiểm soát image

1. Build từ Dockerfile được review.
2. Test chức năng, security scan dependency và base image.
3. Không để key/token trong layer hoặc Docker build context.
4. Push image vào registry được phê duyệt.
5. Ghi lại digest, commit, thời gian build và pipeline identity.
6. Triển khai đúng version; theo dõi health và giữ phương án rollback.

ACR có SKU và khả năng mạng riêng khác nhau. Nếu cần **private endpoint** tới ACR, chọn SKU/tính năng tương ứng tại thời điểm triển khai; không mặc định Basic SKU hỗ trợ mọi khả năng của Premium.

## 6. Xác thực khi App Service kéo private image

Một image private đòi hỏi ít nhất hai điều kiện: **đường mạng tới registry** và **quyền pull**. Tạo ACR trong cùng resource group với Web App **không tự cấp quyền** cho Web App tải image.

### 6.1. Các lựa chọn xác thực

| Cơ chế | Cách hoạt động | Đánh giá |
|---|---|---|
| **Managed identity** | Web App dùng identity do Entra quản lý để xác thực ACR | Ưu tiên khi hỗ trợ, tránh lưu mật khẩu registry |
| Service principal/credential | App Service cấu hình credentials với registry | Cần bảo vệ, luân chuyển và giới hạn scope |
| ACR admin account | Dùng username/password cấp registry | Không khuyến khích cho production; quyền rộng và quản lý key thủ công |
| Public image | Registry cho phép pull không cần auth | Chỉ phù hợp image công khai được phê duyệt; không dùng cho artifact bí mật |

Managed identity được dùng để **pull image** là danh tính workload của Web App, không giống danh tính developer chạy `az acr build` và cũng không tự có quyền đọc Key Vault hay database.

### 6.2. System-assigned và user-assigned identity

- **System-assigned:** gắn với vòng đời Web App, thuận tiện nếu mỗi ứng dụng có quyền pull riêng.
- **User-assigned:** identity tồn tại riêng và có thể được gắn vào nhiều workload phù hợp; giúp chuẩn bị quyền trước khi tạo app, nhưng cần kiểm soát phạm vi chia sẻ và lifecycle.

Ở registry dùng mô hình **Azure RBAC registry permissions**, vai trò **AcrPull** tại phạm vi registry thường được dùng cho pull. Nếu registry bật mô hình **ABAC repository permissions**, quyền repository cần dùng vai trò/cấu hình tương ứng (ví dụ repository reader theo khả năng dịch vụ) thay vì giả định AcrPull luôn hợp lệ. Cấu hình phải theo permission mode của ACR và nhu cầu truy cập từng repository.

### 6.3. Mã hóa và secret

Không hardcode `DOCKER_REGISTRY_SERVER_PASSWORD` hoặc storage connection string trong Dockerfile. Trong trường hợp dùng credential vì chưa áp dụng được managed identity, phải quản lý secret bằng cơ chế được phê duyệt (ví dụ Key Vault), giới hạn người xem, thời hạn và rotate định kỳ. Cân nhắc **Key Vault references** cho app settings được hỗ trợ, nhưng lưu ý identity dùng khi ứng dụng chạy và identity dùng để pull image có thể cần role/scope khác nhau.

## 7. Thực hành end-to-end: build lên ACR rồi triển khai Linux Web App

Phần này mô tả một lab trên Azure CLI (Bash/Cloud Shell chế độ Bash). **Không thực thi các lệnh trong khi soạn bài.** Người học chỉ chạy trong subscription thử nghiệm được cho phép; phải thay tên account/app mang tính duy nhất và kiểm tra quota/chi phí.

### 7.1. Điều kiện đầu vào

- Đã đăng nhập Azure CLI, có quyền tạo resource group, ACR, Linux App Service Plan và Web App trong subscription thử nghiệm.
- Có quyền **gán Azure RBAC role** trên ACR để cho managed identity của Web App được pull image; một quyền Contributor thông thường có thể **không đủ** để gán role.
- Có Docker local hoặc dùng `az acr build` với ACR Tasks được hỗ trợ.
- Thư mục hiện tại chứa đúng `Dockerfile` và `server.js` ở phần 3.
- ACR và Web App có đường mạng kết nối hợp lệ; ví dụ lab ban đầu không khóa toàn bộ public registry endpoint.
- Sẵn sàng trả phí cho tài nguyên App Service Plan và ACR khi còn tồn tại; App Service Plan vẫn có thể tính phí ngay cả khi Web App không có lưu lượng.

### 7.2. Chọn subscription và tên tài nguyên

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RG="rg-appservice-container-lab"
LOCATION="southeastasia"
ACR="<globallyuniquelabregistry>"
PLAN="asp-container-lab"
APP="<globally-unique-web-app-name>"
IMAGE="appservice-demo"
TAG="1.0.0"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id, name:name, tenantId:tenantId}" -o table
~~~

Các giá trị trong dấu `<...>` là **placeholder**. Tên ACR phải đáp ứng quy tắc đặt tên Azure Container Registry (chỉ ký tự cho phép và duy nhất); tên Web App phải duy nhất trong namespace tên miền App Service tương ứng. Kiểm tra vùng, quota plan và điều kiện sử dụng các tính năng trước khi tiếp tục.

### 7.3. Tạo resource group và ACR thử nghiệm

~~~bash
az group create \
  --name "$RG" \
  --location "$LOCATION"

az acr create \
  --resource-group "$RG" \
  --name "$ACR" \
  --sku Basic \
  --admin-enabled false

LOGIN_SERVER=$(az acr show \
  --resource-group "$RG" \
  --name "$ACR" \
  --query loginServer -o tsv)

echo "$LOGIN_SERVER"
~~~

`Basic` dùng để minh họa lab, không phải lựa chọn mặc định cho production hoặc ACR cần private endpoint/khả năng nâng cao. Không bật admin account chỉ để đơn giản hóa việc triển khai. Nếu môi trường yêu cầu registry private-only, phải thiết kế build runner và image pull qua mạng riêng ngay từ đầu; lab công khai này không thay thế kiến trúc đó.

### 7.4. Build image trong ACR

Trong thư mục có Dockerfile:

~~~bash
az acr build \
  --registry "$ACR" \
  --image "$IMAGE:$TAG" \
  .

az acr repository show-tags \
  --name "$ACR" \
  --repository "$IMAGE" \
  --output table
~~~

`az acr build` gửi build context và dùng cơ chế build của ACR được hỗ trợ, nên không cần push một image đã build local qua Docker daemon trong quy trình này. Vẫn phải chú ý **.dockerignore**, secret vô tình nằm trong build context và quyền build trên registry. Trong CI/CD, nên dùng identity và quy trình phê duyệt riêng cho khả năng **push**, khác với identity chỉ có quyền **pull** của Web App.

Ví dụ image tham chiếu sau build:

~~~text
<registry-name>.azurecr.io/appservice-demo:1.0.0
~~~

### 7.5. Tạo Linux App Service Plan

~~~bash
az appservice plan create \
  --resource-group "$RG" \
  --name "$PLAN" \
  --location "$LOCATION" \
  --sku B1 \
  --is-linux
~~~

`B1` chỉ dùng minh họa một plan cơ bản. Với production cần xem xét hiệu năng, số instance, health check, networking, scale, deployment slots, tính sẵn sàng và giá theo SKU. Nếu dự định thực hành **deployment slots**, cần nâng plan lên tier hỗ trợ trước khi tạo slot.

### 7.6. Tạo Web App dùng image ACR

~~~bash
az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --name "$APP" \
  --deployment-container-image-name "$LOGIN_SERVER/$IMAGE:$TAG"
~~~

Một số phiên bản Azure CLI có tên hoặc behavior khác cho tham số container image; kiểm tra `az webapp create --help` trong môi trường sử dụng. **Có thể xuất hiện lỗi image pull tạm thời ngay sau bước tạo** vì Web App chưa được cấp managed identity và ACR pull permission; các bước tiếp theo thiết lập quyền cần thiết. Không xử lý bằng cách bật ACR admin credential vô điều kiện.

### 7.7. Cấp managed identity và quyền pull ACR

~~~bash
# Bật system-assigned managed identity cho Web App.
PRINCIPAL_ID=$(az webapp identity assign \
  --resource-group "$RG" \
  --name "$APP" \
  --query principalId -o tsv)

# Lấy Azure resource ID của ACR.
ACR_ID=$(az acr show \
  --resource-group "$RG" \
  --name "$ACR" \
  --query id -o tsv)

# Ví dụ cho registry dùng RBAC permissions mode thông thường.
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "$ACR_ID"
~~~

Nếu registry dùng **ABAC-enabled repository permissions**, không dùng đoạn `AcrPull` này như kết luận về quyền hợp lệ: hãy cấp đúng vai trò và điều kiện repository cho mô hình đã cấu hình. Role assignment có thể cần thời gian lan truyền; có quyền gán role ở scope registry là điều kiện cần của người thực thi lệnh.

### 7.8. Yêu cầu App Service dùng managed identity cho image pull

~~~bash
# Cấu hình Web App sử dụng managed identity khi xác thực ACR.
# Đây là cú pháp Azure CLI cho site configuration được hỗ trợ;
# xác minh với: az webapp config set --help
az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --generic-configurations '{"acrUseManagedIdentityCreds": true}'

# Đặt rõ registry endpoint và image của custom container.
# Kiểm tra lựa chọn mới nhất qua: az webapp config container set --help
az webapp config container set \
  --resource-group "$RG" \
  --name "$APP" \
  --container-image-name "$LOGIN_SERVER/$IMAGE:$TAG" \
  --container-registry-url "https://$LOGIN_SERVER"
~~~

Nếu Azure CLI đang dùng vẫn yêu cầu các tên tham số cũ (có tiền tố Docker), hãy xem `--help` của lệnh thực tế; tránh chuyển sang đăng nhập bằng password chỉ vì khác tên flag. Tại **Deployment Center → Containers** hoặc khu vực cấu hình tương ứng trên Azure Portal, cũng có thể xác minh registry, image, tag và phương thức xác thực bằng managed identity.

**Quan trọng:** đừng chọn ngẫu nhiên một user-assigned identity chưa được gắn vào Web App. Với UAMI, cần cấu hình đúng identity mà App Service sử dụng cho ACR pull (thường liên quan đến client ID), gán quyền ACR và kiểm tra kết nối. Ví dụ bên trên dùng system-assigned identity để giảm số biến phụ thuộc.

### 7.9. Khai báo cổng HTTP và chạy lại app

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings "WEBSITES_PORT=8080" "PORT=8080"

az webapp restart \
  --resource-group "$RG" \
  --name "$APP"

HOST=$(az webapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query defaultHostName -o tsv)

echo "https://$HOST"
~~~

Hai settings này có nhiệm vụ **khác nhau**: `WEBSITES_PORT` cho App Service biết cổng HTTP của custom container; `PORT` được **ứng dụng mẫu của bài** đọc để chọn cổng lắng nghe. Không giả định `WEBSITES_PORT` tự động xuất hiện như biến môi trường bên trong container cho mọi phiên bản/tính năng; khai báo `PORT` minh bạch giúp ứng dụng không phụ thuộc điều đó.

### 7.10. Kiểm chứng từ góc nhìn người dùng

~~~bash
curl -i "https://$HOST/"
curl -i "https://$HOST/health"
~~~

Kết quả kỳ vọng: HTTP 200 và JSON từ ứng dụng mẫu. Nếu gặp 503 hoặc container restart liên tục, cần kiểm tra image pull, cổng, entrypoint và logs; **không kết luận App Service Plan thiếu CPU** khi chưa có bằng chứng. Nếu DNS/endpoint khác do cấu hình custom domain, cần thử đúng hostname đã cấu hình.

### 7.11. Xem image config và managed identity

~~~bash
az webapp identity show \
  --resource-group "$RG" \
  --name "$APP" \
  --output json

az webapp config container show \
  --resource-group "$RG" \
  --name "$APP" \
  --output json

az role assignment list \
  --assignee "$PRINCIPAL_ID" \
  --scope "$ACR_ID" \
  --output table
~~~

Nếu lệnh trả về các trường cấu hình có chứa credential/token trong môi trường dùng registry auth khác, **không dán nguyên output vào ticket công khai**. Với ACR private, cần đồng thời kiểm tra network resolution và pull permission, không chỉ danh sách role.

## 8. Cổng, HTTPS và vòng đời khởi động container

### 8.1. Cổng công khai và cổng nội bộ là hai lớp khác nhau

Từ góc nhìn người dùng, Azure App Service thường cung cấp kết nối HTTP/HTTPS qua frontend dịch vụ. Custom container được kết nối tới **một HTTP port ứng dụng chính** theo cấu hình nền tảng; App Service không phải bộ chuyển tiếp mọi cổng TCP/UDP tùy ý của Docker.

~~~text
Client HTTPS :443
        |
        v
Azure App Service frontend (TLS termination theo cấu hình)
        |
        v
Ứng dụng trong container :8080 (HTTP)
~~~

Vì vậy:

- `EXPOSE 8080` trong Dockerfile là **metadata**, không tự làm App Service chọn cổng.
- `WEBSITES_PORT=8080` cấu hình cổng để nền tảng route đến container trong mô hình Linux custom container.
- Ứng dụng phải lắng nghe `0.0.0.0:8080`; `127.0.0.1` trong container có thể khiến frontend không gọi được.
- Nếu app dùng redirect HTTPS nội bộ sai cấu hình, có thể tạo vòng lặp redirect sau TLS termination; cần hiểu header `X-Forwarded-Proto` và cấu hình trusted proxy của framework.
- Nếu dùng WebSocket/streaming/long-running requests, đánh giá timeout, keep-alive, session và giới hạn của App Service, thay vì mặc định mọi flow bền vững mãi mãi.

### 8.2. Startup và warm-up

App Service cần kéo image, tạo container, chạy entrypoint và chờ ứng dụng sẵn sàng. Startup chậm do image lớn, migration database, tải mô hình AI hoặc gọi dependency không ổn định có thể làm app bị coi là chưa khởi động được.

Những lựa chọn thiết kế:

1. Giảm kích thước image, bỏ dev dependency/build tool không cần trong runtime.
2. Đưa schema migration hoặc công việc dài sang **bước triển khai độc lập**; không để tất cả instance tranh nhau chạy migration.
3. Tách readiness khỏi liveness. Một app bắt đầu nghe cổng không nhất thiết đã sẵn sàng nhận request nghiệp vụ.
4. Thiết lập startup/warm-up behavior và timeout theo các app settings/tính năng App Service hỗ trợ khi cần; đừng tăng timeout vô hạn để che lỗi.
5. Ghi rõ log lúc startup và thất bại, không log secret.

Khi chỉnh các settings như thời gian container startup hoặc warmup path, phải kiểm tra tên/giới hạn hiện hành theo mô hình Linux custom container và thử nghiệm; không có một thời lượng tối ưu cho mọi app.

### 8.3. Biến môi trường, cấu hình và secret

App settings của App Service được cung cấp cho ứng dụng dưới dạng cấu hình/môi trường theo cơ chế hỗ trợ. Ví dụ:

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings \
    "NODE_ENV=production" \
    "LOG_LEVEL=info" \
    "FEATURE_X_ENABLED=false"
~~~

Thay đổi app settings có thể kích hoạt restart/recycle ứng dụng; đánh giá tác động lên phiên đang chạy và giờ triển khai. Một số cài đặt dùng để cấu hình App Service platform, không phải tham số ứng dụng; nên đặt tên rõ và ghi tài liệu.

Đối với **mật khẩu database, API key và chứng chỉ**, ưu tiên managed identity/Entra authentication khi dịch vụ đích hỗ trợ. Nếu phải dùng secret, đặt trong Key Vault và truy cập qua cơ chế được phép, tránh `Dockerfile ENV SECRET=...` và hardcode trong source/image. Khi kết nối SQL hoặc Storage, phân biệt **quyền control plane** của Web App với quyền **data plane** trên tài nguyên dữ liệu.

## 9. Health Check, Always On và scale

### 9.1. Health Check

**App Service Health Check** gửi request tới path được cấu hình (chẳng hạn `/health`), dùng phản hồi HTTP để đánh giá instance. Một endpoint nên trả **2xx** nhanh khi app có thể phục vụ. Trả 401 do yêu cầu đăng nhập, redirect hoặc timeout có thể khiến health check không được đánh giá là khỏe, tùy hợp đồng dịch vụ; thiết kế endpoint rõ ràng và giới hạn dữ liệu trả về.

Trên Azure Portal, chọn Web App → **Health check** (hoặc phần Monitoring tương ứng) → chọn path `/health`, cấu hình các tùy chọn hỗ trợ và kiểm tra trạng thái sau khi save. Trên các plan/tier và số instance khác nhau, hành vi đưa instance không khỏe ra khỏi luồng phục vụ và thay thế instance cần được kiểm tra theo khả năng của App Service.

| Endpoint | Mục đích | Ví dụ |
|---|---|---|
| `/health/live` | Tiến trình còn sống? | Trả 200 nếu event loop/server đang chạy |
| `/health/ready` | Có thể xử lý request mới? | Trả 200 nếu tài nguyên thiết yếu đã khởi tạo |
| `/health/deep` | Chẩn đoán dependency chuyên sâu | Dùng cho monitoring có xác thực; không nhất thiết dùng làm health check nền tảng |

Ví dụ demo chỉ có `/health` trả 200; production cần bổ sung logic thực tế nhưng tránh để một dependency không thiết yếu làm toàn bộ instances bị loại cùng lúc. Đừng trả stack trace, connection string hay dữ liệu nội bộ cho endpoint có thể bị truy cập công khai.

### 9.2. Always On

**Always On** trên các tier được hỗ trợ giúp app tránh bị idle unload theo hành vi dịch vụ. Nó **không thay** Health Check, readiness, load testing hoặc một SLA của ứng dụng. Với ứng dụng container khởi động chậm, chọn plan/tier và cấu hình phù hợp để đảm bảo trải nghiệm sau một thời gian ít lưu lượng.

### 9.3. Scale up và scale out

- **Scale up:** chọn worker SKU có CPU/RAM tốt hơn trong App Service Plan.
- **Scale out:** tăng số instances/worker của plan hoặc đặt autoscale theo khả năng hỗ trợ.
- **Ứng dụng phải chịu được đa instance:** không giữ session/bản ghi quan trọng chỉ trong RAM hoặc filesystem cục bộ. Dùng cache/DB/Blob Storage phù hợp.
- **Mỗi instance có thể pull image và khởi tạo riêng:** image lớn và startup lâu ảnh hưởng thời gian mở rộng.
- **Scale plan ảnh hưởng các app cùng plan:** dự toán tổng công suất, không chỉ tài nguyên của một Web App.

Với một workload ít lưu lượng, việc tăng số instance chỉ để “có HA” cần được đánh giá cùng SLA/tier/zone support, readiness và phụ thuộc dữ liệu. Nhiều instances trong một region không thay thế chiến lược phục hồi khi region bị sự cố.

## 10. Deployment Center, version tag, CI/CD và release an toàn

### 10.1. Quy trình phát hành khuyến nghị

~~~mermaid
flowchart LR
    COMMIT[Commit được review] --> TEST[Unit/integration tests]
    TEST --> BUILD[Build image + scan]
    BUILD --> PUSH[Push ACR tag bất biến]
    PUSH --> STAGE[Deploy staging]
    STAGE --> VERIFY[Smoke/health/security tests]
    VERIFY --> APPROVE[Phê duyệt]
    APPROVE --> PROD[Deploy hoặc swap production]
    PROD --> OBS[Observe, rollback nếu cần]
~~~

Mỗi release cần ghi rõ commit, version, image digest, pipeline execution ID, môi trường và người phê duyệt. Không tự động cập nhật production ngay khi `latest` thay đổi nếu tổ chức yêu cầu kiểm thử/phê duyệt. Nên dùng automation (GitHub Actions, Azure Pipelines hoặc hệ thống CI/CD được phê duyệt) với **federated identity** thay vì lưu service principal secret dài hạn trong repository.

### 10.2. Phát hành phiên bản mới

Giả sử đã kiểm thử và build version `1.0.1`:

~~~bash
NEW_TAG="1.0.1"

az acr build \
  --registry "$ACR" \
  --image "$IMAGE:$NEW_TAG" \
  .

# Ví dụ thay image của Web App sau khi review.
az webapp config container set \
  --resource-group "$RG" \
  --name "$APP" \
  --container-image-name "$LOGIN_SERVER/$IMAGE:$NEW_TAG" \
  --container-registry-url "https://$LOGIN_SERVER"
~~~

Với ứng dụng có lưu lượng quan trọng, không nhất thiết thay trực tiếp production như lệnh demo. Có thể triển khai vào **slot staging** trên tier hỗ trợ, kiểm thử, rồi swap/cutover theo kế hoạch. Nếu chọn image bằng digest, kiểm tra cú pháp tham chiếu được hỗ trợ và pipeline quản lý digest cho đúng môi trường.

### 10.3. Deployment slots

Slot tạo môi trường ứng dụng song song trong một Web App trên tier hỗ trợ. Chúng giúp kiểm tra phiên bản trước khi chuyển traffic production, nhưng không phải môi trường hoàn toàn tách biệt về mọi tài nguyên: slot có thể chia sẻ App Service Plan và một số phụ thuộc nếu không thiết kế riêng.

Một workflow:

1. Tạo `staging` slot trên Web App thuộc plan hỗ trợ.
2. Cấu hình image version mới cho staging, secrets/connection riêng nếu cần.
3. Đánh dấu những **slot-specific app settings** cần giữ theo môi trường; rà soát kết nối database/storage trước khi swap.
4. Warm-up staging, chạy smoke test, kiểm tra health và telemetry.
5. Phê duyệt rồi swap theo cơ chế có sẵn; xác minh production sau swap.
6. Nếu regression, thực hiện rollback/swap back hoặc trở về image digest đã kiểm chứng, sau khi xác nhận thay đổi dữ liệu có tương thích.

**Swap không rollback schema/data migration tự động.** Khi release thay đổi database schema theo cách không tương thích ngược, quay lại image cũ vẫn có thể khiến app hỏng. Dùng chiến lược migration tương thích (expand/contract) và backup/restore riêng.

### 10.4. Continuous deployment từ registry

App Service có cơ chế tích hợp với registry/webhook cho một số workflow cập nhật image. Khi bật continuous deployment, cần hiểu:

- Điều kiện nào kích hoạt restart/pull image mới.
- Registry webhook/permission và các hạn chế khi ACR bị khóa mạng.
- Có phê duyệt giữa build và production hay không.
- Cách ghi nhận digest đã chạy và cách rollback.

Nếu quy trình yêu cầu phê duyệt nghiêm ngặt, ưu tiên pipeline **đẩy image → kiểm thử → cập nhật Web App rõ ràng** thay vì cho production tự theo một tag có thể bị ghi đè.

## 11. Networking: inbound, outbound và private image pull

Khi App Service chạy container, cần tách ít nhất ba đường mạng:

1. **Client → Web App**: đường vào HTTP/HTTPS, domain, TLS và access restrictions.
2. **Web App → dịch vụ dữ liệu/API**: đường outbound đến Azure SQL, Storage, Key Vault hoặc API đối tác.
3. **App Service platform → image registry**: đường dùng để kéo image lúc tạo/restart/scale-out.

Một đường hoạt động tốt **không chứng minh** hai đường còn lại hoạt động. Ví dụ người dùng có thể thấy trang web nhưng ứng dụng không gọi được database; ngược lại, Web App có quyền ACR pull nhưng container vẫn chưa thể khởi động nếu DNS/private endpoint sai.

### 11.1. Inbound: access restrictions và Private Endpoint

App Service cung cấp hostname public theo cấu hình mặc định được hỗ trợ. Tùy yêu cầu:

- **Access restrictions** giới hạn những nguồn có thể kết nối vào ứng dụng qua đường ingress tương ứng.
- **Private Endpoint cho Web App** đưa đường truy cập inbound riêng vào VNet theo khả năng dịch vụ; client cần DNS/route và quyền truy cập thích hợp.
- **Application Gateway / Azure Front Door với WAF** có thể bảo vệ web HTTP/HTTPS khi kiến trúc cần kiểm tra L7 và điều phối theo host/path.
- **Authentication/Authorization** ở App Service hoặc trong ứng dụng quyết định ai thực sự được dùng chức năng; Private Endpoint và allowlist IP không thay thế quyền ứng dụng.

Nếu ứng dụng chỉ phục vụ nhân viên qua mạng nội bộ, có thể thiết kế private ingress thay vì mở Internet rồi cố bổ sung rule chặn sau. Khi dùng Front Door hoặc gateway công khai làm điểm vào, phải bảo vệ **origin** để client không truy cập bỏ qua lớp bảo vệ nếu kiến trúc yêu cầu.

### 11.2. Outbound: VNet Integration

**Regional VNet Integration** cho phép ứng dụng App Service hỗ trợ tính năng kết nối outbound vào tài nguyên VNet. Nó **không tự biến inbound của Web App thành private**; đó là phạm vi của private endpoint hoặc giải pháp ingress riêng.

~~~mermaid
flowchart TB
    CLIENT[Client Internet / Internal] --> FRONT[App Service ingress]
    FRONT --> APP[Linux Web App custom container]
    APP -->|Regional VNet Integration| INTSUB[Delegated integration subnet]
    INTSUB --> SQL[Azure SQL Private Endpoint]
    INTSUB --> KV[Key Vault Private Endpoint]
    INTSUB --> STORAGE[Blob Storage Private Endpoint]
    INTSUB --> FW[Azure Firewall / NAT egress nếu áp dụng]
    APP -. Image pull path được cấu hình .-> ACR[ACR]
~~~

Subnets cần được quy hoạch:

- **Integration subnet** phải đáp ứng điều kiện sizing/delegation theo App Service, để đủ IP khi scale và nâng cấp worker.
- **Private Endpoint** của SQL/Storage/Key Vault thường nằm ở subnet riêng phù hợp; không đặt bừa vào integration subnet đã delegate.
- **DNS** phải phân giải tên dịch vụ về private endpoint đúng cho workload App Service, không chỉ từ máy admin.
- **UDR/firewall/NAT** ảnh hưởng đường outbound theo routing và route-all configuration được hỗ trợ; kiểm tra đường đi thực tế.
- Khi App Service Plan scale-out, dung lượng IP tích hợp VNet phải đủ cho các instance và những đợt nâng cấp có thể cần thêm IP tạm thời.

### 11.3. ACR private endpoint và image pull qua VNet

Khi ACR tắt public network access hoặc dùng private endpoint, App Service phải có **đường mạng riêng** để kéo image. Đây là tình huống thường gây lỗi startup ở production dù build/push thành công.

Thiết kế cần:

1. ACR SKU và vùng/tính năng hỗ trợ private endpoint; tạo private endpoint cho registry.
2. Private DNS đúng cho `<acr-name>.azurecr.io` và các endpoint liên quan theo kiến trúc ACR, bao gồm data endpoints khi cần.
3. App Service tích hợp mạng outbound phù hợp, có route/DNS đến ACR private endpoint.
4. Cấu hình **image pull over VNet**, thường thông qua setting `WEBSITE_PULL_IMAGE_OVER_VNET=true` ở những Linux App Service configurations hỗ trợ.
5. Managed identity của Web App có quyền pull theo ACR permission mode đang dùng.
6. Kiểm tra image pull khi **restart và scale-out**, không chỉ trong lần deploy đầu.

Nếu registry chỉ truy cập riêng, dùng `az acr build` từ một môi trường không được phép truy cập registry cũng có thể bị ảnh hưởng; hãy bố trí build pipeline/runner được phép và kiểm tra quy tắc mạng của ACR. **Private Endpoint không cấp quyền pull** và **AcrPull không tạo được route mạng**. Hai lớp phải được kiểm chứng độc lập.

### 11.4. Kết nối ra Internet và public outbound IP

Khi Web App gọi API đối tác, phải xác định IP nguồn mà đối tác thấy, đặc biệt khi đối tác dùng allowlist. App Service có các địa chỉ outbound theo cấu hình/tier và chúng có thể thay đổi khi có những thao tác scale/plan; nếu nghiệp vụ cần source IP ổn định, cân nhắc **VNet Integration kết hợp NAT Gateway** hoặc **Azure Firewall** theo thiết kế egress được hỗ trợ.

Không coi riêng `az webapp show` cho biết một danh sách outbound IP là cam kết vĩnh viễn trong mọi tình huống. Với forced tunneling, UDR hoặc route-all, đường đi có thể khác mặc định; kiểm tra khả năng egress và bản ghi kết nối thực tế sau thay đổi.

### 11.5. Ma trận mạng cần kiểm thử

| Luồng | Đích | Kiểm soát |
|---|---|---|
| Người dùng → Web App | HTTPS hostname hoặc private ingress | TLS, custom domain, access restrictions, auth/WAF |
| Web App → Azure SQL | Private Endpoint hoặc cơ chế mạng được duyệt | VNet Integration, DNS, port, Entra/database permission |
| Web App → Blob Storage | Blob private endpoint | DNS, route, identity và Storage Blob Data role |
| Web App → Key Vault | Vault endpoint riêng | Network policy, Key Vault data-plane RBAC, managed identity |
| App Service → ACR | Registry + data endpoints | Pull identity, role, image tag và DNS/network |
| Web App → API đối tác | Internet/public endpoint | NAT/firewall, DNS, TLS, IP allowlist và retry |

## 12. Trạng thái ứng dụng, filesystem và dữ liệu lưu bền

Container phù hợp với ứng dụng **stateless**, nhưng một số app truyền thống vẫn viết file upload, session, cache hoặc ảnh tạm vào ổ local. Trong App Service, container có thể được thay thế khi deploy, restart, scale hoặc bảo trì nền tảng. Không giả định dữ liệu trong writable layer của image tồn tại vĩnh viễn hoặc được chia sẻ giữa mọi instance.

### 12.1. Phân loại dữ liệu

| Loại dữ liệu | Nơi phù hợp | Vì sao |
|---|---|---|
| Source/runtime/dependency | Image đã build | Tái hiện bản phát hành |
| Secret | Key Vault / hệ thống secret được phê duyệt | Tránh lộ trong image và file cấu hình |
| File do người dùng upload | Azure Blob Storage hoặc file service được hỗ trợ | Lưu bền, phân quyền, backup/lifecycle |
| Session nhiều instance | Cache/DB phân tán được thiết kế | Không mất khi chuyển instance |
| Dữ liệu giao dịch | Azure SQL, Cosmos DB hoặc DB phù hợp | Đồng thời, query, transaction và backup |
| Log ứng dụng | stdout/stderr, Azure Monitor/App Insights hoặc pipeline log | Tra cứu sau restart/scale |
| Temporary files | Thư mục tạm theo hạn mức được hỗ trợ | Tự dọn, không coi là lưu trữ vĩnh viễn |

### 12.2. Persistent storage của Linux custom container

App Service có những khả năng mount/persist vùng lưu trữ như `/home` trong cấu hình Linux custom container, và một setting thường gặp là `WEBSITES_ENABLE_APP_SERVICE_STORAGE`. **Hành vi mặc định và phạm vi hỗ trợ phải được xác minh theo loại ứng dụng/tính năng**; đừng giả định cứ ghi file vào `/home` thì dữ liệu luôn bền vững và đồng bộ theo nhu cầu nghiệp vụ.

Ngay cả khi bật persistent storage, vẫn cần xem xét:

- Dữ liệu được chia sẻ giữa các instance như thế nào.
- Quota và performance của vùng lưu trữ.
- File locking, tính nhất quán và xử lý writer đồng thời.
- Backup/restore và vòng đời tệp.
- Phân tách dữ liệu giữa các deployment slots hoặc môi trường.

Với ảnh, tài liệu, sao lưu hoặc file khách hàng, thường nên dùng **Azure Blob Storage**/file service riêng và lưu metadata trong database nếu cần. Đừng dùng writable container layer làm “database miễn phí”.

### 12.3. Application configuration

Giữ **image độc lập với môi trường**: cùng artifact có thể chạy ở dev/test/prod, với app settings/secret/network khác nhau. Không build ba image chỉ khác connection string nhúng trong Dockerfile; điều đó tăng số artifact và nguy cơ lộ secret.

Một lần đổi app setting có thể recycle ứng dụng, nên cần quản lý qua IaC/pipeline review và phân biệt cấu hình **slot-specific** để tránh lộ dữ liệu giữa staging và production.

## 13. Bảo mật container từ build đến runtime

Container image là một phần của chuỗi cung ứng phần mềm. Đóng gói ứng dụng trong Docker **không tự loại bỏ CVE** hoặc ngăn kẻ tấn công dùng quyền ứng dụng để đọc dữ liệu.

### 13.1. Trước khi push lên registry

- Dùng base image từ nguồn đáng tin và **pin digest** khi cần build có thể tái lập.
- Cập nhật runtime/OS packages định kỳ; hạn chế package không cần.
- Quét source dependency và container image với công cụ được phê duyệt.
- Nếu có yêu cầu, tạo SBOM, lưu provenance/signature và quy trình xác minh artifact.
- Dùng multi-stage build để tách compiler/build tool khỏi runtime khi phù hợp.
- Không đưa `.env`, private key, credentials hay file backup vào Docker build context; dùng `.dockerignore`.
- Không chạy app bằng root nếu không có nhu cầu thật; hạn chế writable path.
- Đưa quyền push image vào danh tính CI riêng, không dùng identity pull-only của production để push.

Ví dụ `.dockerignore` cho repo Node.js:

~~~text
.git
node_modules
.env
.env.*
*.pem
*.key
secrets/
coverage/
tmp/
~~~

`.dockerignore` là lớp giảm rủi ro, **không thay thế** secret scanner hoặc review Dockerfile. Nếu secret đã được commit/push vào registry trước đó, xóa nó khỏi Dockerfile hiện tại không làm secret từng được phát hành tự động mất khả năng sử dụng; cần rotate và kiểm tra artifact tồn tại.

### 13.2. Trong khi chạy trên App Service

- Web App dùng **managed identity** để gọi các Azure services hỗ trợ Entra; cấp quyền tối thiểu theo đúng scope.
- Hạn chế public ingress, áp dụng HTTPS/TLS, auth và WAF nếu cần.
- Không ghi token, SAS, account key hoặc thông tin khách hàng nhạy cảm vào log.
- Đặt quota/concurrency, rate limit và timeout ở ứng dụng hoặc gateway phù hợp.
- Gắn Azure Policy, RBAC và audit cho việc thay đổi image/config.
- Cấu hình diagnostics, Health Check và alert để phát hiện lỗi runtime.
- Không dựa vào `USER root` trong Dockerfile để giải quyết lỗi quyền file; chỉnh đúng owner và volume thay vì nới toàn bộ quyền.

### 13.3. Image refresh và CVE

Một CVE mới trên `node:22-alpine` hoặc thư viện ứng dụng cần được xử lý bằng:

1. Xác định image digest và phiên bản package bị ảnh hưởng.
2. Nâng base image/dependency lên bản vá được hỗ trợ.
3. Build image mới và chạy test/security scan.
4. Deploy vào staging/canary, kiểm tra trước khi chuyển production.
5. Xác minh runtime thật đang chạy digest mới, không chỉ tag.
6. Giữ bằng chứng và xử lý image cũ/secret lộ theo chính sách retention.

**App Service không tự build lại custom image của bạn** sau khi vendor phát hành một base image mới. Cập nhật Web App runtime setting khác với phát hành image đã vá.

## 14. Logging và quan sát container

Khi lỗi xảy ra, hãy trả lời rõ **lỗi ở khâu pull image**, **startup**, **routing**, **ứng dụng** hay **dependency**. Mỗi loại có nguồn log khác nhau.

### 14.1. Các nguồn telemetry

| Nguồn | Dữ liệu quan trọng |
|---|---|
| Container startup/deployment logs | Image pull, registry authentication, entrypoint và container startup |
| Application stdout/stderr | Lỗi runtime, request processing, stack trace đã lọc dữ liệu nhạy cảm |
| App Service metrics | Request count, response time, HTTP 4xx/5xx, CPU/memory, số instances |
| Health Check | Instance sẵn sàng hoặc không khỏe theo path được cấu hình |
| Application Insights | Request traces, dependency failures, distributed tracing khi instrument |
| Azure Activity Log | Ai đổi container image, app settings, identity, network hoặc plan |
| ACR diagnostics | Các hoạt động registry theo nguồn dữ liệu/tính năng được bật |
| Azure Monitor/Log Analytics | Tổng hợp và cảnh báo khi đã cấu hình các luồng log thích hợp |

Không mặc định tạo workspace là mọi log tự động đi vào đó. Cần bật application instrumentation, log settings, diagnostic settings hoặc exporter phù hợp; đánh giá chi phí ingest và retention.

### 14.2. Xem log thử nghiệm bằng Azure CLI

~~~bash
# Bật logging container vào filesystem trong lab khi CLI/runtime hỗ trợ.
az webapp log config \
  --resource-group "$RG" \
  --name "$APP" \
  --docker-container-logging filesystem

# Stream log của Web App để quan sát startup và request.
az webapp log tail \
  --resource-group "$RG" \
  --name "$APP"
~~~

Nếu không thấy log, kiểm tra đã bật đúng loại logging, trạng thái app, kết nối log streaming và khả năng hỗ trợ của SKU/mô hình container. `log tail` thường phù hợp thao tác lab/điều tra ngắn; production cần chiến lược log bền vững, phân quyền và retention thay vì chỉ trông chờ cửa sổ terminal đang mở.

### 14.3. Alert gắn với SLO

Một số cảnh báo nên có owner và runbook:

1. HTTP 5xx hoặc latency p95 tăng sau release.
2. Nhiều container restart hoặc startup thất bại trên một số instance.
3. Health Check thất bại kéo dài.
4. CPU/RAM/connection tăng cao trước giờ cao điểm.
5. Registry pull thất bại khi scale hoặc restart.
6. Dependency đến SQL/Storage/Key Vault trả timeout hoặc 403.
7. Có thay đổi image tag/digest hoặc App Service settings ngoài pipeline.
8. Egress IP/network policy thay đổi làm API đối tác từ chối kết nối.

Ví dụ, nếu trang trả 503 sau deploy, việc tăng số instances không chắc có tác dụng nếu **mọi instance đều không pull được image**. Đầu tiên cần phân loại bằng log rồi mới chọn phương án sửa.

## 15. Troubleshooting: container không chạy như kỳ vọng

### 15.1. Quy trình xác định lỗi theo thứ tự

Khi URL không trả kết quả, đừng thay đồng thời ACR, Dockerfile, cổng, NSG và database settings: làm vậy khó biết thay đổi nào giải quyết vấn đề.

1. **Web App đã tồn tại và chạy đúng plan/OS chưa?** Kiểm tra trạng thái App Service Plan, Web App, Linux và SKU.
2. **Image tham chiếu có tồn tại không?** Xác định đầy đủ login server, repository, tag/digest và build result trong ACR.
3. **ACR pull có đủ điều kiện?** Xem managed identity, role assignment, permission mode, registry network và DNS.
4. **Container khởi động chưa?** Đọc startup logs, kiểm tra CPU architecture, entrypoint, dependency và runtime error.
5. **Ứng dụng có lắng nghe đúng cổng không?** Đối chiếu `WEBSITES_PORT`, `PORT`, `EXPOSE` và bind address.
6. **Có response nội bộ đúng không?** Thử `/` và `/health`, phân biệt 503 do platform với 500 do app.
7. **Dependency có hoạt động không?** Kiểm tra VNet Integration, Key Vault, SQL, Blob, DNS và RBAC data-plane.
8. **Lỗi chỉ sau scale/deploy không?** Kiểm tra mọi instance, tag/digest, startup thời gian dài, data state và slot settings.
9. **Đã thay đổi cấu hình gần đây chưa?** Đối chiếu Activity Log và deployment pipeline.
10. **Có thể rollback không?** Khi release lỗi, dùng image digest đã kiểm chứng hoặc deployment slot theo quy trình; đừng sửa production bằng nhiều thay đổi không được ghi nhận.

### 15.2. Bảng triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/cách xử lý |
|---|---|---|
| Log có `unauthorized`, `denied` khi pull | Web App chưa có quyền pull; identity sai hoặc ACR dùng ABAC | Xác nhận principal ID, permission mode, role/repository scope, chờ RBAC propagation |
| `manifest unknown` / image not found | Sai repository/tag hoặc image chưa push | Xem tags/digest trong ACR; đối chiếu image reference |
| `no matching manifest for platform` | Image build sai CPU/OS architecture | Kiểm tra manifest và build image Linux/amd64 tương thích |
| Container start rồi exit liên tục | CMD/ENTRYPOINT sai, lỗi code, thư viện thiếu | Đọc container logs, kiểm tra exit code; chạy local |
| Container chạy nhưng App Service trả 503 | Sai cổng, bind localhost, startup chưa xong | Kiểm tra `WEBSITES_PORT`, `PORT`, listener `0.0.0.0`, startup logs |
| `/` chạy, `/health` trả 401/404 | Endpoint sai path hoặc bắt đăng nhập | Sửa Health Check path/readiness behavior; không mở lộ dữ liệu nhạy cảm |
| App chạy local nhưng lỗi trên Azure | Khác env/arch, secret, outbound DNS hoặc access đến PaaS | So app settings, image arch, managed identity và VNet |
| SQL/Storage/Key Vault trả 403 | Có thể sai RBAC, credential, firewall hoặc policy dịch vụ | Phân biệt data-plane permission và network policy, kiểm tra token/endpoint |
| ACR pull lỗi chỉ khi tắt public access | Chưa có VNet-based image pull, private DNS hoặc routing | Kiểm tra `WEBSITE_PULL_IMAGE_OVER_VNET`, VNet integration, registry data endpoints |
| Chỉ instance scale-out mới lỗi | Instance mới không pull được image hoặc startup/resource không đủ | Kiểm tra từng instance, pull auth, DNS, startup và IP subnet |
| Thay cấu hình staging làm production lỗi | Slot-specific setting chưa khai báo hoặc dữ liệu dùng chung | Review swap config, database/Key Vault và connection references |
| File upload biến mất sau restart | Ghi vào writable layer tạm | Đưa dữ liệu sang Blob Storage/DB hoặc storage có bảo đảm phù hợp |
| Image mới không xuất hiện sau push `latest` | Tag bị cache/reference chưa cập nhật/restart hoặc webhook không hoạt động | Kiểm tra digest chạy thực tế và pipeline deploy rõ ràng |
| API đối tác từ chối IP | Outbound IP thay đổi sau thay đổi plan/network | Kiểm tra đường egress, NAT/Firewall, allowlist và DNS |

**Không chép credentials vào log** khi kiểm tra lỗi kéo image. Những chuỗi URL hoặc response chứa token/registry password phải được che trước khi chia sẻ với nhóm hỗ trợ.

### 15.3. Các lệnh đọc cấu hình hữu ích

~~~bash
# Web App và plan liên quan.
az webapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,state:state,host:defaultHostName,plan:serverFarmId}" \
  -o json

# Danh sách setting; có thể chứa thông tin nhạy cảm.
# Chỉ xem ở terminal được phép, không dán nguyên output công khai.
az webapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --output json

# Image config và registry.
az webapp config container show \
  --resource-group "$RG" \
  --name "$APP" \
  --output json

# Image version có trong registry.
az acr repository show-tags \
  --name "$ACR" \
  --repository "$IMAGE" \
  -o table
~~~

Nếu yêu cầu hỗ trợ kỹ thuật, nên lưu dấu thời gian, request/correlation ID, Web App resource ID, image digest, mức ảnh hưởng và thay đổi gần nhất. Không đính kèm secret hoặc token.

## 16. Chọn kiến trúc phù hợp và kiểm soát chi phí

### 16.1. App Service custom container có thực sự cần thiết?

| Câu hỏi | Nếu câu trả lời là “Có” |
|---|---|
| Ứng dụng cần custom runtime hoặc native dependency khó triển khai bằng built-in stack? | Container có thể tạo lợi ích rõ ràng |
| Chỉ có web/API và không cần host-level privileged operation? | App Service custom container có thể phù hợp |
| Có background worker, queue consumer hoặc nhiều container cần phối hợp đặc thù? | Đánh giá Container Apps, Functions, AKS hoặc workload service khác |
| Cần Kubernetes scheduling, CRD, operator hoặc service mesh phức tạp? | AKS có thể phù hợp hơn App Service |
| Cần đơn giản hóa vận hành cho một ứng dụng monolith? | App Service thường dễ vận hành hơn tự quản lý VM/Kubernetes |
| Web app có state ghi local không thể tách ngay? | Cần refactor storage/session hoặc đánh giá platform phù hợp trước khi scale-out |

Đừng chọn container chỉ vì đã có Dockerfile. Một ứng dụng dùng built-in runtime có thể đơn giản hơn, ít artifact cần vá và giảm công vận hành build/scan. Mặt khác, container tăng tính tái lập, portability theo điều kiện môi trường và kiểm soát dependency khi thực sự cần.

### 16.2. Các nguồn chi phí cần dự toán

| Hạng mục | Tác động chi phí |
|---|---|
| **App Service Plan** | Phí worker/instance theo SKU và thời gian sử dụng; app idle không có nghĩa plan miễn phí |
| **ACR** | Phí registry SKU, storage image, network và các tính năng/operation theo mô hình giá |
| **Scale out** | Thêm worker tăng compute cost, có thể cần thêm IP khi VNet integration |
| **Application Insights / Log Analytics** | Ingest, retention, tracing, alert và volume log |
| **Private networking** | Private Endpoint, NAT Gateway, Azure Firewall, data processing/egress tùy kiến trúc |
| **Blob Storage / Database** | Data capacity, operations, backup, redundancy và truy cập dữ liệu |
| **CI/CD/build** | Build runners, artifact retention, image scans và các dịch vụ bảo mật |
| **Lưu lượng** | Outbound data transfer, kết nối liên vùng và dịch vụ phân phối nếu có |

Các khoản phí và điều kiện tính giá thay đổi theo region, SKU và thời điểm. Cần dùng Azure Cost Management/giá Azure áp dụng cho subscription thật, không hardcode một giá trong tài liệu.

### 16.3. Cách tối ưu thực tế

- Giảm image size để kéo nhanh hơn và tiết kiệm thời gian build/storage registry.
- Loại bỏ unused tags/digests theo chính sách retention, nhưng không xóa artifact còn cần để rollback.
- Dùng app plan chung khi workload tương thích và team chấp nhận chia sẻ capacity; tách plan khi cần cô lập.
- Chọn đúng SKU và cấu hình scale theo metric tải thực tế, không chỉ theo CPU trung bình.
- Giới hạn log debug và dữ liệu nhạy cảm; chọn sampling/retention thích hợp.
- Chỉ triển khai Private Endpoint/NAT/Firewall nơi yêu cầu bảo mật và lưu lượng thực tế biện minh chi phí.
- Gắn tags `owner`, `application`, `environment` và `costCenter`; đặt budget alert và review xu hướng.

**Budget alert không phải hard cap**. Khi dừng hoặc xóa Web App nhưng giữ App Service Plan/ACR/NAT Gateway, tài nguyên còn lại vẫn có thể tính phí. Chi phí được xác nhận bằng billing data, không chỉ việc thấy trang web không còn hoạt động.

## 17. Tình huống kiến trúc: triển khai API đơn hàng

**Bối cảnh giả định:** Một công ty có API đơn hàng viết bằng Java, trước đây chạy trong VM; nhóm phát triển muốn chuyển sang custom container App Service. API gọi Azure SQL và Azure Blob Storage, đọc secret từ Key Vault, đồng thời gọi hệ thống đối tác. Dữ liệu là production và có yêu cầu không downtime trong giờ cao điểm.

### 17.1. Kiến trúc gợi ý

~~~mermaid
flowchart TB
    DEV[Git repository] --> CI[CI build, tests, image scan]
    CI --> ACR[ACR private images]
    APP[Linux App Service custom container] --> SQL[Azure SQL Private Endpoint]
    APP --> BLOB[Blob Storage Private Endpoint]
    APP --> KV[Key Vault Private Endpoint]
    APP --> NAT[NAT Gateway / approved egress]
    NAT --> PARTNER[Partner API]
    USER[Người dùng] --> EDGE[HTTPS edge / WAF nếu cần]
    EDGE --> APP
    APP -. Diagnostics .-> MON[Azure Monitor / App Insights]
    ACR -. Image pull với managed identity .-> APP
    APP --- VNET[Regional VNet Integration]
    VNET --- SQL
    VNET --- BLOB
    VNET --- KV
~~~

Sơ đồ biểu diễn những kết nối logic; việc khai báo App Service Plan, Web App, frontend, private endpoint và subnet phải theo kiến trúc vùng triển khai cụ thể. DNS và đường đi giữa VNet Integration và các private endpoint cần được kiểm chứng; một cạnh trong sơ đồ không tự cấu hình firewall rule hay RBAC.

### 17.2. Các bước triển khai được phê duyệt

1. **Phân tách subscription/resource group** theo mô hình nền tảng và workload; xác định owner, môi trường, quyền Azure RBAC.
2. **Dockerize và test** Java API với multi-stage build, image non-root, readiness `/health/ready` và metadata version.
3. **Build/scan/push** image lên ACR, lưu digest theo commit.
4. **Cấp quyền**: CI identity chỉ được push phạm vi cần, Web App managed identity chỉ được pull image và đọc đúng tài nguyên dữ liệu.
5. **Provision** Linux App Service Plan/slot, Web App, app settings và cổng HTTP của container.
6. **Networking**: regional VNet integration, private endpoint + DNS cho SQL/Storage/Key Vault, đường pull ACR và outbound IP cho đối tác.
7. **Staging**: deploy image, chạy unit/integration, health, TLS, auth, data-plane tests và tải giả lập.
8. **Production rollout**: swap/cutover có phê duyệt, quan sát 5xx/latency, chuẩn bị image rollback.
9. **Operations**: giám sát, patch base image, rotate secret và kiểm soát chi phí.

### 17.3. Ma trận kiểm thử

| Kiểm thử | Kết quả kỳ vọng | Nếu thất bại, điều tra |
|---|---|---|
| Image pull từ ACR private | Worker lấy được đúng digest | Entra identity, AcrPull/ABAC, registry DNS/network |
| Health/ready sau startup | Trả 2xx khi app thật sự sẵn sàng | Port, entrypoint, app startup, dependency |
| Client truy cập HTTPS | Certificate/TLS hợp lệ, auth đúng | Domain, ingress policy, application auth |
| API truy cập SQL | Đúng DB và identity permission | VNet integration, private DNS, SQL auth |
| API đọc Blob Storage | Đọc đúng container, không đọc vượt quyền | Storage data RBAC, network và object path |
| API đọc Key Vault | Chỉ secret cần thiết | Managed identity, Key Vault RBAC, network |
| API gọi đối tác | Source IP và TLS theo allowlist | NAT/Firewall, DNS, route, retry logic |
| Scale từ 1 lên 2 instances | Cả hai startup/health và phục vụ | Image pull, subnet IP, shared state, app plan |
| Swap và rollback | Chuyển version an toàn, không mất dữ liệu | Slot settings, migrations, digest, health metrics |

**Câu hỏi thiết kế:** Nếu ACR ngừng kết nối khi một instance đang phục vụ, điều gì xảy ra khi App Service cần restart/scale-out? Nếu database migration thay schema, image cũ có thể rollback không? Nếu NAT Gateway đổi public IP, đối tác có từ chối API không? Phải trả lời những câu hỏi này trước khi go-live, không chỉ sau khi có incident.

## 18. Bài thực hành tự triển khai và đánh giá

**Đề bài:** Xây một HTTP API đơn giản có `/` và `/health`, đóng gói bằng Linux container, đẩy lên ACR, triển khai lên Azure App Service. Ứng dụng phải dùng private registry và không được lưu password registry trong Dockerfile. Sau đó chuẩn bị phương án kết nối Azure SQL qua private endpoint và một deployment pipeline an toàn.

Thực hiện các yêu cầu:

1. Vẽ sơ đồ source → build → ACR → App Service → client, ghi rõ đâu là image pull, đâu là request HTTP.
2. Viết `Dockerfile` có base image được duy trì, chạy non-root và lắng nghe cổng 8080. Giải thích khác biệt giữa `EXPOSE` và listener thật.
3. Build và test local bằng Docker; chứng minh `/` và `/health` trả HTTP 200.
4. Tạo ACR/private repository và build tag version cụ thể; đọc lại tag/digest.
5. Tạo Linux App Service Plan và Web App trong subscription lab, cấu hình image ACR.
6. Cấp managed identity và quyền pull phù hợp, giải thích cách thay đổi khi registry dùng ABAC repository permissions.
7. Đặt `WEBSITES_PORT=8080` và `PORT=8080`; giải thích dấu hiệu khi một trong hai sai.
8. Cấu hình log streaming/Health Check; ghi lại startup message và trạng thái endpoint.
9. Vẽ đường **outbound** tới Azure SQL qua VNet Integration/Private Endpoint/DNS. Giải thích vì sao đó không phải inbound Private Endpoint của Web App.
10. Giả sử ACR bị khóa public access, liệt kê bổ sung về private registry DNS, image pull over VNet và quyền.
11. Mô tả pipeline phát hành `1.0.1` có scan, staging test, approval, production và rollback theo digest.
12. Nêu ba cách có thể lộ secret trong Docker build/log/app settings và đề xuất biện pháp phòng tránh.
13. Dự toán nhóm chi phí plan/ACR/logging/network, đặt tag và budget alert.
14. Lập runbook cho tình huống “deployment succeeded nhưng Web App trả 503”.
15. Kết thúc lab bằng việc xác định **đúng tài nguyên được phép xóa**, không ảnh hưởng subscription hoặc tài nguyên dùng chung.

### Khung kết quả mong đợi

| Thành phần | Kết quả phải chứng minh |
|---|---|
| Source + Dockerfile | Build thành công, image đúng Linux architecture, non-root |
| Local container | Listener trên 0.0.0.0:8080, health 200 |
| ACR | Có image tag/digest và danh tính pull chỉ có quyền cần thiết |
| Web App | Linux plan, image đúng, `WEBSITES_PORT` đúng |
| HTTP edge | Truy cập HTTPS từ client thành công |
| Data | Phân biệt network private endpoint, DNS và data-plane RBAC |
| Deployment | Có version, kiểm thử staging, cách rollback |
| Observability | Có startup logs, health, error metrics và alert có owner |
| FinOps | Tài nguyên lab được kiểm kê; không quên plan/ACR/network còn tính phí |

Bài thực hành đạt yêu cầu khi người học có thể phân tích độc lập **một lỗi image pull**, **một lỗi port** và **một lỗi truy cập SQL** bằng những bằng chứng riêng, thay vì sửa cùng lúc tất cả cấu hình.

## 19. Dọn dẹp tài nguyên lab và các sai lầm cần tránh

Trước khi xóa:

1. Xác nhận subscription bằng `az account show` và resource group đúng là **lab do bạn sở hữu**.
2. Liệt kê Web App, App Service Plan, ACR, public/private endpoints, log workspace và mọi tài nguyên có liên kết khác.
3. Kiểm tra plan không đang chứa một Web App được nhóm khác dùng chung.
4. Kiểm tra ACR có image phục vụ môi trường khác hoặc pipeline khác không.
5. Xác nhận quy trình lưu giữ log, image và bằng chứng theo chính sách.
6. Chỉ khi chắc chắn RG chứa **toàn bộ tài nguyên thử nghiệm** mới có thể xóa RG theo quy trình được phê duyệt.

~~~bash
az account show --query "{id:id,name:name}" -o table
az resource list --resource-group "$RG" -o table

# CẢNH BÁO: lệnh xóa hủy toàn bộ tài nguyên trong resource group.
# Chỉ sau khi xác nhận RG hoàn toàn dành cho lab:
# az group delete --name "$RG" --yes
~~~

Những sai lầm thường gặp:

| Sai lầm | Hệ quả | Cách tránh |
|---|---|---|
| Push image nhưng quên cấp pull identity | App Service không thể khởi tạo image private | Gán role và kiểm tra permission mode ACR |
| Chỉ cấu hình `EXPOSE 8080` | Frontend không biết đúng cổng; app có thể không listen | `WEBSITES_PORT`, `PORT` và bind `0.0.0.0` |
| Dùng tag `latest` có thể ghi đè | Không biết digest nào đang chạy, rollback khó | Immutable tag/digest và deployment history |
| Đưa secret vào Dockerfile/`.env` trong image | Secret có thể lộ qua registry/layer/history | Managed identity, Key Vault, .dockerignore và scan |
| Bật VNet Integration rồi nghĩ public ingress đã đóng | Web App có thể còn public endpoint | Private Endpoint/access restrictions và auth |
| Tạo ACR private endpoint nhưng quên image pull over VNet/DNS | Build hoặc startup fail khi registry bị khóa public | Kiểm tra network pull path đầy đủ |
| Ghi file khách hàng vào container local | Mất dữ liệu sau restart/scale | Blob Storage/DB và backup |
| Coi Health Check là test nghiệp vụ toàn diện | Deploy có thể vẫn lỗi logic hoặc dependency khác | Synthetic checks và integration tests |
| Swap staging/production khi dùng chung DB không tương thích | Rollback image không cứu được dữ liệu/schema | Migration tương thích và backup |
| Xóa Web App nhưng giữ plan/ACR/NAT | Chi phí vẫn tiếp tục | Kiểm kê tất cả tài nguyên liên quan |

## 20. Ghi nhớ

Triển khai container lên Azure App Service là một chuỗi công việc có ranh giới rõ:

1. **Build image đúng**: Dockerfile có runtime, entrypoint, port, security và architecture phù hợp.
2. **Lưu artifact đáng tin**: ACR giữ image theo tag/digest; build/test/scan trước khi phát hành.
3. **Cấu hình platform**: Linux App Service Plan và Web App tham chiếu image đúng, có cổng `WEBSITES_PORT` và app settings phù hợp.
4. **Xác thực image pull**: managed identity có quyền registry/repository tương ứng; khi ACR private còn cần đường mạng và DNS hợp lệ.
5. **Bảo vệ và kết nối ứng dụng**: inbound HTTPS/auth, VNet Integration outbound, private endpoint/data-plane RBAC, dữ liệu lưu bền ngoài writable container.
6. **Vận hành release**: health check, metrics/logging, scale, staging/slots, rollback và cập nhật base image đều phải được kiểm chứng.
7. **Kiểm soát chi phí**: chọn SKU/instances thích hợp, quản lý ACR/image retention, log và networking.

Điểm quan trọng nhất: **“container image đã build/push thành công” không đồng nghĩa “web app đã sẵn sàng phục vụ”**. Một bản triển khai chỉ hoàn thành về mặt vận hành khi registry pull, startup, routing, bảo mật, dependency, giám sát và khả năng phục hồi đều được kiểm thử trong kiến trúc Azure thực tế.
