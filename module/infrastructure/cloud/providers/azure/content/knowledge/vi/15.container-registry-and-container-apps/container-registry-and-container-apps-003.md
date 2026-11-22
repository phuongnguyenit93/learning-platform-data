# Xác thực Registry bằng RBAC và managed identity

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta khám phá Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu, đồng thời học triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Ở chương **Container Registry và Container Apps**, nội dung trọng tâm là bảo vệ nguồn cung cấp container image: **ai được đẩy (push), ai được tải (pull), từ repository nào và bằng danh tính gì?**

Ví dụ, nhóm phát triển xây image `orders-api` rồi đẩy lên **Azure Container Registry (ACR)**. Một **Azure Container Apps** ở production cần tải đúng image đó khi tạo revision mới hoặc scale ra replica. Nếu dùng tài khoản quản trị registry và đặt mật khẩu vào cấu hình ứng dụng, sự cố rò rỉ có thể làm lộ khả năng truy cập rộng tới image của cả hệ thống. Giải pháp tốt hơn là dùng **Microsoft Entra ID + Azure RBAC**, kết hợp **managed identity** cho workload chạy trên Azure.

Sau bài học, bạn có thể:

- Phân biệt **authentication** và **authorization** trong ACR, cùng control plane và data plane.
- Hiểu các lựa chọn đăng nhập ACR: Entra ID, managed identity, service principal/federated identity và registry admin account.
- Chọn quyền **pull**, **push**, quản lý repository phù hợp với hai chế độ phân quyền: registry-level RBAC và repository-level **RBAC + ABAC**.
- Cấp quyền cho một **user-assigned managed identity**, rồi cấu hình Azure Container Apps kéo image riêng tư mà không lưu mật khẩu registry.
- Kiểm tra các lỗi `401 Unauthorized`, `403 Forbidden`, tên image sai, token hết hạn và lỗi DNS/firewall.
- Áp dụng least privilege, logging, quy trình xoay vòng quyền, kiểm thử và kiểm soát chi phí.

## 1. Azure Container Registry và các đối tượng cần bảo vệ

**Azure Container Registry (ACR)** là dịch vụ registry do Azure quản lý để lưu trữ và phân phối container images cùng các OCI artifacts được hỗ trợ. Khi build ứng dụng Java, Node.js hoặc .NET thành container, đội phát triển có thể push artifact lên ACR; App Service, Container Apps, AKS, Azure Container Instances hoặc công cụ khác sau đó pull artifact để chạy.

Một registry có tên tài nguyên ví dụ là `acrordersdev001` thường có **login server** dạng:

```text
acrordersdev001.azurecr.io
```

Các image được định danh theo repository, tag hoặc digest:

```text
acrordersdev001.azurecr.io/orders/api:1.4.2
acrordersdev001.azurecr.io/orders/web:1.2.0
acrordersdev001.azurecr.io/orders/api@sha256:<digest>
```

Trong đó:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Registry | `acrordersdev001` | Tài nguyên Azure lưu và cung cấp artifact |
| Login server | `acrordersdev001.azurecr.io` | Endpoint mà Docker/OCI client kết nối |
| Repository | `orders/api` | Tập hợp manifest/tag của một image trong registry |
| Tag | `1.4.2` | Tên tham chiếu thuận tiện; có thể thay đổi đích nếu không kiểm soát |
| Digest | `sha256:...` | Định danh nội dung manifest được băm, phù hợp ghim artifact chính xác |
| Manifest/layers | Nội dung OCI image | Dữ liệu thực tế mà client phải tải khi pull |

**Pull** là tải manifest và các layer cần thiết; **push** là đưa manifest/layers hoặc phiên bản image mới lên registry. Những thao tác như xóa tag, xóa repository, liệt kê catalog và sửa cấu hình registry không mặc nhiên có cùng quyền.

### 1.1. Bản đồ luồng build → registry → ứng dụng

```text
Developer / CI pipeline
       |
       | 1. Entra ID / workload identity
       | 2. Được phép push vào repository cần thiết
       v
Azure Container Registry
       |    acrordersdev001.azurecr.io/orders/api:1.4.2
       |
       | 3. Container Apps dùng managed identity
       | 4. RBAC/ABAC cho phép pull
       v
Azure Container Apps environment
       |
       +-- Container App: orders-api
            +-- Revision: image 1.4.2
            +-- Replica 1
            +-- Replica 2
```

Đây là mô hình logic. Để triển khai thành công, luồng mạng đến ACR, DNS, Container Apps environment, image tag/digest và quyền của danh tính cũng phải đúng.

## 2. Xác thực khác phân quyền như thế nào?

**Authentication (xác thực):** chứng minh một tác nhân là ai. Ví dụ developer đăng nhập Azure CLI bằng Microsoft Entra ID; hoặc Container App sử dụng managed identity để lấy token phục vụ truy cập ACR.

**Authorization (phân quyền):** xác định tác nhân đã được xác thực có thể làm gì. Một danh tính đăng nhập thành công có thể vẫn **không có quyền pull** hoặc **không có quyền push** vào repository.

```text
Danh tính người dùng / workload
          |
          v
Microsoft Entra ID xác thực
          |
          v
Nhận token phù hợp và yêu cầu đến ACR
          |
          v
ACR đánh giá role assignments + điều kiện repository
          |
          +-- Có quyền với hành động/tài nguyên -> cho phép
          |
          +-- Không đủ quyền -> từ chối
```

Token đăng nhập vào Azure Portal không tự biến mọi thao tác Docker thành được phép. ACR client cần cơ chế xác thực tương thích với registry, đồng thời Entra principal cần quyền dữ liệu đúng phạm vi.

### 2.1. Control plane và data plane

Azure phân biệt hai loại thao tác:

| Plane | Ví dụ | Loại quyền |
|---|---|---|
| **Control plane** (quản lý tài nguyên Azure) | Tạo ACR, đổi SKU, cấu hình networking, tạo role assignment | Azure Resource Manager operations và các role quản trị tương ứng |
| **Data plane** (nội dung registry) | Pull image, push image, đọc repository manifest, thao tác artifact | Quyền registry/repository theo cơ chế RBAC hoặc RBAC + ABAC của ACR |

Một người có thể được phép **xem thông tin cấu hình ACR** trong Azure Portal nhưng không được tải image. Ngược lại, pipeline có thể được phép **push image** nhưng không được thay firewall của registry hoặc cấp quyền cho người khác.

**Sai lầm phổ biến:** cấp `Owner` hoặc `Contributor` cho cả resource group chỉ để sửa lỗi Docker pull. Cách này mở rộng quyền quản trị không cần thiết và không phải giải pháp đúng cho mọi chế độ repository permissions.

## 3. Các cách xác thực vào ACR

### 3.1. Microsoft Entra ID cho người dùng

Developer thường đăng nhập tương tác:

```bash
az login
az account set --subscription "<subscription-id>"
az acr login --name acrordersdev001
```

`az acr login` sử dụng danh tính Entra ID đang đăng nhập Azure CLI để thực hiện luồng đăng nhập registry và, khi Docker CLI/daemon sẵn sàng, cấu hình đăng nhập cho Docker. Việc lệnh login thành công **không chứng minh** developer được push vào mọi repository: quyền sẽ được kiểm tra khi thao tác thực tế.

Một số môi trường không có Docker daemon có thể sử dụng chế độ token phù hợp của Azure CLI/OCI client; cần kiểm tra hướng dẫn và không in token ra terminal, file log hoặc pipeline output.

### 3.2. Managed identity cho workload Azure

**Managed identity** là danh tính Microsoft Entra được Azure quản lý cho tài nguyên Azure được hỗ trợ. Workload dùng danh tính này lấy token mà **không phải lưu client secret hoặc password trong app settings**.

Có hai kiểu:

- **System-assigned managed identity:** gắn với vòng đời của tài nguyên chủ; xóa tài nguyên thường làm danh tính đó không còn tồn tại.
- **User-assigned managed identity:** tài nguyên danh tính riêng, có thể gán cho một hoặc nhiều workload theo tính năng hỗ trợ; vòng đời không phụ thuộc vào một Container App.

Đối với luồng Container Apps kéo image từ ACR, **user-assigned managed identity** thường giúp chuẩn bị quyền trước khi tạo Container App và tái sử dụng có kiểm soát. System-assigned identity cũng được hỗ trợ trong những quy trình/sản phẩm phù hợp, nhưng có thể cần thứ tự tạo app và cấu hình registry khác, đặc biệt nếu image riêng tư phải được pull ngay trong bước tạo app đầu tiên.

Managed identity **chỉ cung cấp cách lấy danh tính/token**; nó **không tự cấp quyền `AcrPull`**, không tự mở firewall, không tự cấu hình image name và không thay thế chính sách bảo mật supply chain.

### 3.3. Service principal và workload identity federation

Pipeline CI/CD chạy ngoài Azure hoặc cần một danh tính ứng dụng độc lập có thể sử dụng **service principal** và role assignment phù hợp.

- Với **client secret/certificate**, pipeline phải bảo vệ và quản lý vòng đời credential.
- Với **workload identity federation / OIDC**, một provider CI/CD được hỗ trợ có thể trao đổi token đáng tin cậy với Microsoft Entra ID theo federated credential; phương pháp này thường giảm nhu cầu lưu client secret lâu dài.

Nếu CI chạy trên một dịch vụ Azure hỗ trợ managed identity, có thể dùng managed identity thay cho secret. Nếu CI chạy trên GitHub Actions hay hệ thống ngoài Azure, cân nhắc OIDC federation với scope phù hợp thay vì dùng registry admin password.

### 3.4. Registry admin user và token registry

ACR có **admin account** dạng username/password ở cấp registry trên các cấu hình hỗ trợ. Đây là cơ chế tiện thử nghiệm hoặc tương thích, nhưng có quyền rộng và không phải mô hình lý tưởng cho production.

Ngoài ra ACR còn có cơ chế **repository-scoped tokens và scope maps** ở những SKU/tính năng được hỗ trợ. Chúng có thể phục vụ client không dùng được Entra ID, nhưng vẫn là credentials riêng cần bảo vệ, giới hạn, xoay vòng và thu hồi. **Repository-scoped token không phải managed identity**, và cũng không tự trở thành Azure RBAC role.

| Lựa chọn | Lợi ích | Rủi ro / lưu ý |
|---|---|---|
| Entra user + `az acr login` | Thuận tiện cho developer, theo danh tính tổ chức | Không dùng login tương tác cho workload production |
| Managed identity | Không lưu mật khẩu registry trong workload Azure | Cần role đúng và hỗ trợ của dịch vụ chủ |
| Service principal + OIDC | Phù hợp CI/CD ngoài Azure | Cần cấu hình federation, điều kiện trust và role |
| Service principal + secret | Tương thích nhiều tool | Secret có thể rò rỉ, cần rotation |
| Registry admin account | Đơn giản trong một số lab | Đặc quyền rộng, khó quy về danh tính cá nhân |
| Repository-scoped token | Quyền theo scope map trên registry khi được hỗ trợ | Credential độc lập phải quản lý an toàn |

**Khuyến nghị:** với người dùng dùng Entra ID; với Container Apps dùng managed identity; với CI/CD dùng managed identity hoặc federation khi phù hợp. Tránh dùng admin account làm giải pháp mặc định.

## 4. Azure RBAC cho Azure Container Registry

Azure RBAC gán một **role** cho một **principal** tại một **scope**. Principal có thể là người dùng, nhóm, service principal hoặc managed identity.

```text
Role assignment
   ├── Principal: <object-id-của-managed-identity>
   ├── Role:      AcrPull (mô hình RBAC registry truyền thống)
   └── Scope:     /subscriptions/.../registries/acrordersdev001
```

Một số role liên quan khi registry sử dụng chế độ **RBAC Registry Permissions**:

| Role | Thao tác data plane tiêu biểu | Nhu cầu |
|---|---|---|
| `AcrPull` | Pull image và artifact được phép ở registry | Container Apps hoặc workload chỉ cần chạy image |
| `AcrPush` | Push và pull trong phạm vi quyền của role | Pipeline build/publish image |
| `AcrDelete` | Thao tác xóa nội dung registry theo quyền role | Tác vụ dọn artifact được phê duyệt |
| `AcrImageSigner` | Các thao tác ký image theo khả năng/tính năng tương ứng | Trường hợp quản lý chữ ký chuyên biệt, không phải role pull/push thường ngày |

**Không tự gán `AcrPush` cho một runtime chỉ cần `pull`.** Một danh tính bị chiếm đoạt với quyền push có thể gây rủi ro đưa artifact sai lệch vào registry nếu hệ thống triển khai không kiểm soát tag/digest.

### 4.1. Registry-level RBAC không phải lúc nào cũng là repository-level isolation

Ở mô hình RBAC registry truyền thống, `AcrPull` và `AcrPush` thường được gán tại **scope registry**, mang quyền đối với tập repository trong registry theo vai trò. Nếu registry chứa images của nhiều đội, cấp một role registry-level rộng có thể vượt yêu cầu least privilege.

Ví dụ:

```text
acrsharedprod.azurecr.io
  ├── payments/api
  ├── orders/api
  └── hr/reporting
```

App `orders-api` chỉ nên tải `orders/api`. Nếu dùng `AcrPull` rộng trên cả registry, danh tính có thể được cấp khả năng pull những repository khác dù ứng dụng không cần. Khi cần phân đoạn theo repository, hãy đánh giá **RBAC + ABAC Repository Permissions mode** hoặc thiết kế nhiều registry theo ranh giới bảo mật.

## 5. Hai chế độ phân quyền của ACR: RBAC và RBAC + ABAC

Đây là điểm rất quan trọng đối với ACR hiện đại. Registry có thể được cấu hình theo **role assignment permissions mode** được dịch vụ hỗ trợ. Việc chọn mode quyết định các role nào được sử dụng cho thao tác dữ liệu.

### 5.1. RBAC Registry Permissions (kiểu registry-level)

- Dùng các role registry quen thuộc như `AcrPull` và `AcrPush`.
- Quyền thường áp dụng trên phạm vi registry; không diễn đạt chi tiết từng repository qua những role legacy đó.
- Phù hợp khi registry đã được phân tách đúng theo boundary của một workload/đội và không cần policy repository chi tiết.

### 5.2. RBAC Registry + ABAC Repository Permissions

**ABAC (Attribute-Based Access Control)** cho phép áp dụng điều kiện dựa trên **tên repository** cho những role repository chuyên biệt của ACR theo khả năng hỗ trợ. Mục tiêu là vẫn dùng principal/role assignments của Entra ID nhưng giới hạn hành động theo repository thay vì mở toàn registry.

Những role cần biết trong chế độ này gồm:

| Role repository | Vai trò chính | Khi chọn |
|---|---|---|
| `Container Registry Repository Reader` | Pull/đọc artifacts theo scope và điều kiện | Runtime chỉ tải image |
| `Container Registry Repository Writer` | Đẩy và đọc artifacts theo quyền được hỗ trợ | Pipeline build/publish |
| `Container Registry Repository Contributor` | Thao tác quản lý artifacts rộng hơn, có thể gồm xóa theo quyền hỗ trợ | Tác vụ bảo trì repository được phê duyệt |
| `Container Registry Repository Catalog Lister` | Liệt kê tên repository ở mức registry theo cơ chế hỗ trợ | Chỉ khi cần catalog discovery |

Khi registry dùng **ABAC repository permissions mode**, không mặc định `AcrPull`/`AcrPush` kiểu cũ tiếp tục cấp quyền dữ liệu tương tự. Cần **kiểm tra mode, lựa chọn role tương ứng và cấu hình điều kiện đúng cách**. Các quyền catalog cũng khác với việc pull một image đã biết tên; không cấp Catalog Lister chỉ vì workload cần pull một image cụ thể.

Ví dụ chính sách mục tiêu:

| Principal | Role | Điều kiện repository | Quyền mong muốn |
|---|---|---|---|
| `mi-orders-api-prod` | Repository Reader | `orders/api` | Pull đúng image API đơn hàng |
| `ci-orders-build` | Repository Writer | `orders/api` | Push bản build vào repository API |
| `ci-payments-build` | Repository Writer | `payments/api` | Không push vào `orders/api` |
| `registry-maintainers` | Repository Contributor | Phạm vi repository được phê duyệt | Bảo trì artifacts theo quy trình |

Các điều kiện ABAC được cấu hình trên **role assignment** và phải dựa trên cú pháp, thuộc tính và thao tác được ACR/Azure RBAC hỗ trợ. Không thể chỉ thêm chuỗi tên repository vào phần mô tả role rồi coi đó là giới hạn có hiệu lực.

### 5.3. Chọn mode nào?

| Nhu cầu | Hướng thiết kế |
|---|---|
| Mỗi registry thuộc một đội, quyền pull/push được quản lý ở cấp registry | RBAC Registry Permissions có thể đủ |
| Một registry dùng chung nhiều đội, cần phân quyền theo repository | RBAC + ABAC Repository Permissions |
| Client legacy không dùng được Entra ID và cần scope riêng | Cân nhắc repository-scoped token/scope map theo SKU, với kiểm soát credential |
| Cách ly nghiêm ngặt theo môi trường, network hoặc billing | Cân nhắc nhiều registry thay vì chỉ dựa trên role conditions |

**Lưu ý khi chuyển mode:** thay đổi mode có thể làm những role assignments hiện tại không còn cấp quyền dữ liệu theo kỳ vọng. Trước khi bật hoặc chuyển đổi, kiểm kê mọi client pull/push, pipeline, service principal, managed identity và cách đăng nhập; lập kế hoạch chuyển role cùng thử nghiệm ở môi trường phù hợp. Không đổi mode trên registry production chỉ để khắc phục một lỗi `403` chưa được xác minh.

### 5.4. Ví dụ tạo role assignment có điều kiện

Khi dùng Azure Portal trong chế độ ABAC:

1. Mở **Azure Container Registry** cần quản lý, xác nhận **Role assignment permissions mode**.
2. Vào **Access control (IAM)**, chọn **Add role assignment**.
3. Chọn role repository chuyên biệt, ví dụ **Container Registry Repository Reader**.
4. Chọn principal là **managed identity** của ứng dụng.
5. Ở bước **Conditions**, đặt điều kiện repository theo khả năng giao diện/Azure RBAC đang hỗ trợ, ví dụ chỉ `orders/api`.
6. Review biểu thức điều kiện, principal và scope; áp dụng, chờ RBAC propagation, rồi kiểm thử **pull được repository cho phép và bị từ chối repository khác**.

Không dùng một câu lệnh CLI tự chế với điều kiện ABAC chưa được xác minh, vì sai biểu thức có thể vô tình cấp quyền rộng hoặc không cấp quyền nào. Với production, nên quản lý role assignments + conditions bằng IaC/API version đã được kiểm thử, có review thay đổi và kiểm thử negative case.

## 6. Managed identity: chọn danh tính và hiểu các ID

Một user-assigned managed identity có ít nhất ba loại định danh mà người học dễ nhầm:

| Thuộc tính | Ví dụ minh họa | Dùng cho |
|---|---|---|
| **Resource ID** | `/subscriptions/.../userAssignedIdentities/mi-orders-acr-pull` | Gán identity vào Azure Container App |
| **Principal ID / Object ID** | UUID của service principal tương ứng trong Entra tenant | Chọn principal khi tạo Azure RBAC role assignment |
| **Client ID** | UUID ứng dụng của managed identity | Chọn identity trong SDK/luồng lấy token khi cần |

Đừng dùng **Client ID** thay cho **Object ID** ở `--assignee-object-id`, và đừng dùng **Principal ID** thay cho **Resource ID** khi CLI yêu cầu `--user-assigned` hoặc `--identity` theo Azure resource.

### 6.1. System-assigned hay user-assigned cho Container Apps?

| Tiêu chí | System-assigned | User-assigned |
|---|---|---|
| Vòng đời | Theo Container App | Tài nguyên độc lập |
| Chuẩn bị quyền trước khi app được tạo | Khó hơn vì principal chưa tồn tại trước khi có app | Dễ: tạo identity và gán RBAC trước |
| Sử dụng chung cho nhiều app | Không: gắn với một tài nguyên | Có thể, nhưng cần cân nhắc blast radius |
| Phù hợp | App đã tồn tại hoặc quy trình hỗ trợ cấp quyền sau khi tạo | Bootstrap pull image riêng tư, môi trường CI/CD theo IaC |
| Rủi ro | Xóa app có thể làm mất identity và role mapping liên quan | Dùng chung identity có thể tạo quyền vượt mức nếu không phân ranh giới |

Đối với production, **không bắt buộc mọi app dùng cùng một user-assigned identity**. Nếu các app thuộc các vùng dữ liệu khác nhau, nên cân nhắc identity tách biệt và role condition riêng để tránh một app bị xâm nhập có thể pull image nhạy cảm của app khác.

## 7. Quy trình tổng thể: Container App kéo image riêng tư

Một đường triển khai chuẩn:

```text
1. ACR đã có image orders/api:1.4.2
                    |
2. Tạo user-assigned managed identity
                    |
3. Cấp role pull đúng ACR mode/scope/repository
                    |
4. Gắn identity vào Azure Container App
                    |
5. Cấu hình registry server + identity (không có password)
                    |
6. Đặt image reference của Container App
                    |
7. Azure lấy token từ managed identity, kiểm tra quyền ACR
                    |
8. Revision/replica pull được image và chạy
```

Các bước 3 và 7 là nơi kiểm soát phân quyền. Nếu image có tag/digest sai, registry endpoint bị chặn, hoặc Container App chưa gắn identity đúng, chỉ có role assignment chưa đủ.

**Security boundary:** identity dùng để **pull image** không nhất thiết phải giống identity mà code chạy trong container dùng để gọi Key Vault, Storage hoặc database. Để giảm quyền dư thừa, nên phân biệt quyền tải artifact và quyền truy cập dữ liệu của ứng dụng, dù kỹ thuật có thể cho phép một identity phục vụ nhiều mục đích.

## 8. Thực hành Azure CLI: cấp quyền ACR cho managed identity

Phần thực hành sử dụng **Bash trong Azure Cloud Shell hoặc máy có Azure CLI**. Các lệnh mẫu minh họa registry ở chế độ **RBAC Registry Permissions truyền thống**; **không chạy nguyên xi đoạn gán `AcrPull` lên registry đã chọn RBAC + ABAC mode**, vì role dữ liệu phải đổi theo mode và có thể cần điều kiện repository.

Giả định:

- Có ACR `acrordersdev001` với image `orders/api:1.4.2` đã được push.
- Có resource group `rg-orders-dev` chứa ACR, hoặc người thực hiện biết resource group của registry.
- Có resource group `rg-orders-app-dev` cho danh tính và Container Apps.
- Người chạy lệnh có quyền tạo managed identity và **quyền gán Azure RBAC roles** tại ACR (ví dụ quyền quản lý role assignments phù hợp), không chỉ quyền đọc registry.
- Có một **Container Apps environment** `cae-orders-dev` được tạo đúng region và network; hoặc người thực hiện sẽ chuẩn bị environment theo quy trình riêng trước khi triển khai app.
- Có quyền tạo Container Apps và đủ quota, firewall/DNS phù hợp. Mọi lệnh chỉ thực hành trên tài nguyên dev đã được phê duyệt.

### 8.1. Xác nhận registry, subscription và mode

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

ACR="acrordersdev001"
ACR_RG="rg-orders-dev"
APP_RG="rg-orders-app-dev"
LOCATION="southeastasia"
IDENTITY="mi-orders-acr-pull-dev"
CONTAINERAPP="ca-orders-api-dev"
ENVIRONMENT="cae-orders-dev"

ACR_ID=$(az acr show \
  --resource-group "$ACR_RG" \
  --name "$ACR" \
  --query id --output tsv)

LOGIN_SERVER=$(az acr show \
  --resource-group "$ACR_RG" \
  --name "$ACR" \
  --query loginServer --output tsv)

az acr show \
  --resource-group "$ACR_RG" \
  --name "$ACR" \
  --query "{name:name,loginServer:loginServer,sku:sku.name,adminUserEnabled:adminUserEnabled,id:id}" \
  --output json
```

**Trước khi cấp role:** trong ACR → **Access control (IAM)** hoặc phần cấu hình registry permissions theo Azure Portal/CLI đang được hỗ trợ, xác minh registry đang dùng **RBAC Registry Permissions** hay **RBAC Registry + ABAC Repository Permissions**. Không suy ra mode chỉ từ SKU hay tên tài nguyên. Nếu ABAC mode được bật, chuyển sang hướng dẫn role repository ở mục 5, không dùng đoạn `AcrPull` bên dưới.

### 8.2. Tạo user-assigned managed identity

```bash
az identity create \
  --resource-group "$APP_RG" \
  --name "$IDENTITY" \
  --location "$LOCATION"

UAMI_RESOURCE_ID=$(az identity show \
  --resource-group "$APP_RG" \
  --name "$IDENTITY" \
  --query id --output tsv)

UAMI_PRINCIPAL_ID=$(az identity show \
  --resource-group "$APP_RG" \
  --name "$IDENTITY" \
  --query principalId --output tsv)

UAMI_CLIENT_ID=$(az identity show \
  --resource-group "$APP_RG" \
  --name "$IDENTITY" \
  --query clientId --output tsv)
```

Ba biến trên phục vụ ba ngữ cảnh khác nhau:

- `UAMI_RESOURCE_ID`: gắn danh tính vào Azure Container App.
- `UAMI_PRINCIPAL_ID`: làm **assignee object ID** của role assignment.
- `UAMI_CLIENT_ID`: có thể dùng để chọn danh tính khi code/SDK thực hiện lấy token, nếu ứng dụng cần.

Kiểm tra identity không có nghĩa có quyền pull; ở bước này Azure mới tạo principal, chưa cấp data plane permissions của ACR.

### 8.3. Cấp đúng quyền pull cho chế độ registry-level RBAC

**Chỉ dành cho registry dùng RBAC Registry Permissions mode:**

```bash
az role assignment create \
  --assignee-object-id "$UAMI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "$ACR_ID"
```

Lệnh này không trao `AcrPush`, không tạo password và không sửa registry admin user. Scope là **ACR resource**, không phải toàn subscription hay resource group. Tuy nhiên, `AcrPull` tại registry vẫn có thể cho phép pull nhiều repository trong registry: đó là lý do cần ABAC hoặc phân chia registry nếu yêu cầu nghiêm ngặt.

Đọc lại assignments:

```bash
az role assignment list \
  --scope "$ACR_ID" \
  --assignee "$UAMI_PRINCIPAL_ID" \
  --output table
```

Role assignments có thể cần thời gian lan truyền; khi vừa tạo xong mà pull thất bại, cần kiểm tra role, mode và chờ propagation phù hợp trước khi liên tục cấp thêm quyền mới.

**Nếu ACR dùng RBAC + ABAC Repository Permissions mode:** thay bước 8.3 bằng role **Container Registry Repository Reader** với điều kiện giới hạn `orders/api`. Phải triển khai đúng cú pháp condition của Azure RBAC qua Portal hoặc IaC được kiểm tra; không coi lệnh `AcrPull` truyền thống là đủ. Nếu runtime còn cần liệt kê catalog để discovery, đánh giá quyền riêng cho tác vụ đó; pull một tên image cụ thể không mặc nhiên yêu cầu quyền catalog toàn registry.

### 8.4. Kiểm tra hình ảnh thực sự tồn tại

Với **developer hoặc pipeline identity được cấp quyền phù hợp** để kiểm tra image, có thể dùng:

```bash
az acr repository show-tags \
  --name "$ACR" \
  --repository orders/api \
  --output table
```

Lệnh này chạy bằng **danh tính hiện tại của Azure CLI**, không phải thử quyền của managed identity được tạo ở bước 8.2. Nếu danh tính CLI không có quyền repository, lệnh có thể thất bại dù workload identity có quyền. Đừng dùng việc kiểm tra này để kết luận Container Apps đã được cấu hình đúng.

Tạo image reference:

```bash
IMAGE="$LOGIN_SERVER/orders/api:1.4.2"
```

Để tái lập production chính xác và hạn chế sự cố ghi đè tag, cân nhắc pin image bằng **digest** thay vì chỉ dựa vào tag có thể bị đổi. Pipeline phải kiểm tra manifest được build, provenance và chính sách bảo mật image, không chỉ tên tag.

## 9. Cấu hình Azure Container Apps dùng managed identity để pull ACR

Azure Container Apps có cấu hình **registry authentication** cho từng Container App. Mục đích là tạo một mối liên kết giữa **login server ACR** và **identity có quyền pull**, không phải đưa admin password vào secret của Container App.

### 9.1. Luồng tạo Container App mới

Ở môi trường được hỗ trợ, Azure CLI cho phép chỉ định user-assigned identity trong quá trình tạo Container App:

```bash
# Giả định Container Apps environment đã tồn tại và image có thể truy cập.
az containerapp create \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --environment "$ENVIRONMENT" \
  --image "$IMAGE" \
  --user-assigned "$UAMI_RESOURCE_ID" \
  --registry-server "$LOGIN_SERVER" \
  --registry-identity "$UAMI_RESOURCE_ID" \
  --ingress internal \
  --target-port 8080
```

Điều kiện:

- CLI và **Azure Container Apps extension** phải hỗ trợ các tham số tương ứng ở phiên bản đang dùng.
- `--user-assigned` gắn danh tính vào app; `--registry-identity` yêu cầu sử dụng danh tính đó khi xác thực với ACR.
- `--ingress internal` chỉ phù hợp nếu workload cần truy cập nội bộ theo topology của Container Apps environment; không biến toàn bộ môi trường hoặc ACR tự động riêng tư.
- `--target-port 8080` chỉ đúng nếu container thực sự lắng nghe cổng 8080. Nếu ứng dụng không cần HTTP ingress, hãy lựa chọn cấu hình ingress phù hợp thay vì mở cổng mẫu.
- ACR role đã cấp và network/registry authentication phải cho phép pull ở thời điểm tạo revision.

Nếu CLI/tính năng không hỗ trợ cách bootstrap gộp này, bạn có thể dùng **Azure Portal** để tạo Container App với user-assigned identity đã tồn tại, chọn image trong ACR và cấu hình registry authentication bằng identity. Không dùng admin account chỉ để bỏ qua yêu cầu bootstrap.

### 9.2. Gắn identity cho Container App đã có

Khi Container App tồn tại, có thể gắn user-assigned identity trước:

```bash
az containerapp identity assign \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --user-assigned "$UAMI_RESOURCE_ID"
```

Sau đó khai báo registry server và danh tính tương ứng:

```bash
az containerapp registry set \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --server "$LOGIN_SERVER" \
  --identity "$UAMI_RESOURCE_ID"
```

Thao tác này cấu hình ACR credential source cho Container App mà **không cần truyền `--username` hoặc `--password`**. Nếu Container App đang sử dụng private image và chưa thể tạo revision, cần bảo đảm trình tự bootstrap và quyền pull đã sẵn sàng.

Đọc lại registry configuration:

```bash
az containerapp registry list \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --output json

az containerapp identity show \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --output json
```

Kiểm tra login server, resource ID của identity và sự vắng mặt của cấu hình username/password không cần thiết. Khi thay đổi registry identity, kiểm tra những registry entries khác đã có để tránh vô tình thay cấu hình của workload khác.

### 9.3. Cập nhật image và revision

Sau khi role và registry configuration đúng:

```bash
az containerapp update \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --image "$IMAGE"
```

Container Apps quản lý các **revisions** theo cơ chế của dịch vụ. Khi thay template/image, có thể tạo revision mới; cần quan sát trạng thái provisioning, replica, health và traffic split trước khi chuyển toàn bộ lưu lượng production.

Đối với release quan trọng, phải gắn image tag/digest với build ID và khả năng rollback. **Managed identity chỉ chứng minh workload có quyền pull**, không chứng minh image đã qua scan bảo mật, không chứa lỗ hổng hay là phiên bản đã được phê duyệt.

### 9.4. Kiểm tra role assignment và policy trên ACR

Nếu Container App báo không tải được image:

1. Xác nhận **Container App thực sự gắn identity** có Resource ID `UAMI_RESOURCE_ID`.
2. Xác nhận registry config trỏ đến đúng `LOGIN_SERVER` và identity đó.
3. Xác nhận principal ID của identity được cấp **role phù hợp với mode ACR** và điều kiện repository chính xác.
4. Xác nhận image repository/tag/digest tồn tại và không bị xóa.
5. Kiểm tra Azure Container Apps revision/provisioning events cùng ACR logs, DNS, firewall và private endpoint.

Nếu một Container App dùng **system-assigned identity**, danh tính phải tồn tại trước khi có thể gán role theo principal ID. Trình tự tạo/assign/đặt image có thể khác với user-assigned identity; điều này không có nghĩa system-assigned identity không được hỗ trợ trong mọi kịch bản.

## 10. Pipeline build/push: không dùng quyền runtime cho CI

Phân quyền cho **pipeline tạo image** khác quyền của **Container App chạy image**. Một pipeline có thể cần quyền `push` vào repository; Container App chỉ cần `pull`.

```text
Git repository / CI
      |
      | Workload identity federation hoặc service principal phù hợp
      | Quyền Push theo registry mode
      v
ACR/orders/api:1.4.2
      |
      | User-assigned managed identity của Container App
      | Quyền Pull theo registry mode
      v
Container Apps (runtime)
```

### 10.1. Ví dụ developer push bằng Entra ID

Giả sử developer đã có quyền push vào repository và Docker daemon hoạt động:

```bash
az login
az account set --subscription "<subscription-id>"
az acr login --name "$ACR"

# Image đã được build tại máy developer/pipeline.
docker tag orders-api:1.4.2 "$LOGIN_SERVER/orders/api:1.4.2"
docker push "$LOGIN_SERVER/orders/api:1.4.2"
```

Lệnh `docker push` cần quyền dữ liệu theo **mode registry hiện tại**. Nếu developer chỉ có `AcrPull` hoặc Repository Reader, push sẽ bị từ chối dù `az acr login` có thể thành công.

### 10.2. Cấp quyền pipeline tối thiểu

Với **RBAC Registry Permissions mode**, pipeline có thể dùng role `AcrPush` tại scope registry nếu thực sự cần. Trong **ABAC mode**, dùng **Container Registry Repository Writer** cùng điều kiện giới hạn đúng repository. Không cấp Contributor repository hoặc Owner chỉ để pipeline push một image.

Một số pipeline còn cần đọc tag, xóa artifacts cũ hoặc liệt kê catalog; các quyền đó phải được đánh giá và cấp riêng theo tác vụ. Đừng lấy việc một bước `az acr repository list` bị từ chối làm lý do tự động cấp quyền push/xóa cho toàn registry.

### 10.3. Federated credentials thay cho client secret

Với nền tảng CI hỗ trợ OIDC, quy trình tổng quát là:

1. Tạo Entra application/service principal hoặc một identity hỗ trợ federation theo kiến trúc.
2. Cấu hình **federated credential** có issuer, subject và audience tương ứng với repository/branch/environment được tin cậy.
3. Gán role dữ liệu ACR với phạm vi hẹp nhất và điều kiện repository nếu dùng ABAC mode.
4. Pipeline trao đổi OIDC token lấy Entra access token và đăng nhập ACR qua lệnh/công cụ được hỗ trợ.
5. Push image, ghi digest và metadata build; không lưu password registry trong CI secrets.

Không chấp nhận mọi branch hoặc mọi repository trong điều kiện federation khi chỉ một protected environment được phép publish production image. Điều kiện trust của identity federation và quyền data plane của ACR là **hai lớp bảo vệ khác nhau**.

## 11. Phân quyền theo repository: ví dụ thiết kế nhiều nhóm

Một registry được chia sẻ cho các nhóm:

```text
acrplatformprod.azurecr.io
  ├── orders/api
  ├── orders/web
  ├── payments/api
  └── reports/worker
```

Yêu cầu:

- Container App orders-api chỉ pull `orders/api`.
- Container App payments-api chỉ pull `payments/api`.
- Pipeline orders có thể push `orders/api` và `orders/web`, không được sửa payments.
- Đội kiểm toán được xem danh sách những repository cần thiết nhưng không push hoặc delete.

Phương án tham khảo khi registry dùng **RBAC + ABAC Repository Permissions mode**:

| Principal | Role | Điều kiện |
|---|---|---|
| `mi-orders-api-prod` | Container Registry Repository Reader | Repository = `orders/api` |
| `mi-payments-api-prod` | Container Registry Repository Reader | Repository = `payments/api` |
| `ci-orders-prod` | Container Registry Repository Writer | Repository thuộc tập `orders/api`, `orders/web` theo cú pháp điều kiện được hỗ trợ |
| `auditors` | Quyền đọc/catalog cần thiết theo tác vụ | Chỉ phạm vi và tác vụ kiểm toán được phê duyệt |

**Kiểm thử bắt buộc:** identities được phép pull repo đúng nhưng **không** pull repo của team khác, không push khi chỉ có Reader, không delete khi chỉ có quyền build/pull và không tự thay quyền IAM. Những phép thử “deny” này mới chứng minh boundary được triển khai đúng.

Nếu cần **network isolation, khóa mã hóa hoặc chính sách vòng đời khác nhau** giữa orders và payments, repository-level ABAC có thể chưa đủ: cân nhắc đặt chúng trong **registry riêng**.

### 11.1. Khi nào phải dùng quyền Catalog Lister?

Một container runtime biết sẵn tên image `acrplatformprod.azurecr.io/orders/api:1.4.2` thường chỉ cần thao tác pull. Một công cụ discovery muốn gọi API liệt kê tất cả repository có thể cần role catalog riêng trong ABAC mode.

Cho quyền liệt kê catalog có thể làm lộ **tên repository**, dù không cho phép tải mọi manifest. Vì thế chỉ gán `Container Registry Repository Catalog Lister` cho những tác vụ có lý do cụ thể, không cho mọi runtime.

## 12. Network security: có role vẫn có thể không pull được

ACR có thể được bảo vệ bằng **firewall/network rules**, private endpoint, DNS và các cơ chế mạng khác tùy SKU/khả năng. Azure Container Apps có quyền `pull` nhưng **không có đường mạng** đến registry vẫn gặp lỗi khi tải image.

Sơ đồ minh họa registry private:

```text
Container Apps environment
         |
         | Outbound qua VNet/route được hỗ trợ
         v
Private DNS resolution
         |
         v
ACR private endpoint (IP riêng)
         |
         v
Azure Container Registry
         |
         +-- Kiểm tra identity + RBAC/ABAC repository permissions
```

Các lớp cần kiểm tra:

1. **DNS:** login server của registry và các endpoint dữ liệu cần thiết phải được phân giải đúng theo mô hình private endpoint. Cần cấu hình private DNS zone/link, custom DNS hoặc resolver thích hợp.
2. **Networking:** Container Apps environment, VNet/subnet, UDR, NSG, Azure Firewall/NAT và outbound rules có cho phép HTTPS/TCP 443 tới ACR endpoints không?
3. **Registry firewall:** ACR có giới hạn public access hoặc chỉ cho phép private endpoint? Có policy khác chặn IP nguồn hoặc đường đi?
4. **Danh tính:** Container App dùng đúng identity và role tương ứng với permissions mode không?
5. **Artifact:** Image tag/digest có tồn tại và cho phép tải manifest/layers không?

**Đừng mở public network access của ACR ra toàn Internet chỉ để xử lý một lỗi pull chưa xác minh.** Kiểm tra riêng vấn đề network với lỗi authorization; khi bắt buộc thay đổi firewall để thử, thực hiện trong môi trường test và có kế hoạch khôi phục cấu hình an toàn.

### 12.1. ARM audience token cho managed identity

Trong một số cấu hình ACR, khả năng xác thực token có **Azure Resource Manager (ARM) audience** là điều kiện liên quan đến luồng pull dùng managed identity của dịch vụ Azure. Kiểm tra tình trạng hỗ trợ/tùy chọn của registry thay vì chỉ tập trung vào role assignment.

Ví dụ lệnh kiểm tra trên phiên bản CLI hỗ trợ:

```bash
az acr config authentication-as-arm show \
  --registry "$ACR" \
  --output json
```

Nếu trạng thái không phù hợp với luồng managed identity đang triển khai, hãy đọc điều kiện của tính năng và thực hiện thay đổi theo phê duyệt. **Không bật/tắt tùy tiện trong production** vì có thể ảnh hưởng những client khác đang dùng registry.

### 12.2. Private endpoint không thay thế quyền pull

Private endpoint chỉ thay đổi đường mạng. Một client đã kết nối thành công đến private IP vẫn có thể nhận lỗi `401` hoặc `403` do thiếu Entra token hoặc role phù hợp. Ngược lại, role `AcrPull` đúng không vượt qua route/firewall bị chặn.

Khi debug, nên lập bảng tách hai lớp:

| Kiểm tra mạng | Kiểm tra authorization |
|---|---|
| DNS resolution của `<acr>.azurecr.io` | Identity thực tế đang được Container App sử dụng |
| Route/NSG/Firewall/Private endpoint | Mode RBAC hay RBAC + ABAC |
| Kết nối TLS đến endpoint liên quan | Role assignment và scope |
| Data endpoint và image layers | ABAC repository condition, pull permissions |

## 13. Quan sát, log và xử lý sự cố

### 13.1. Thu thập dấu vết ở đúng điểm

Để điều tra một sự cố pull image, nên xem:

- **Container Apps revision state và provisioning events**: revision nào thất bại, image reference gì, lỗi lấy image ở giai đoạn nào.
- **Container Apps system logs**: các thông báo từ nền tảng về khởi tạo container và image pull trong phạm vi log dịch vụ cung cấp.
- **ACR diagnostic logs**: request đăng nhập, truy cập repository, thao tác và lỗi theo category đang bật.
- **Azure Activity Log**: thay đổi role assignment, networking, registry settings hoặc managed identity ở control plane.
- **Entra ID / identity events** theo quyền và phạm vi có sẵn: xác thực token, sai principal/tenant và vấn đề của workload identity.

Đừng ghi access token, registry passwords hoặc chuỗi Docker login đầy đủ vào support ticket. Lưu timestamp UTC, ACR resource ID, login server, repository/tag, Container App revision, principal **Object ID** và error code là đủ cho phần lớn bước phân tích ban đầu.

### 13.2. Các lỗi điển hình

| Dấu hiệu | Nguyên nhân khả dĩ | Kiểm tra hoặc xử lý |
|---|---|---|
| `401 Unauthorized` khi pull | Không có token hợp lệ, identity chưa gắn, registry auth sai | Container App registry config, managed identity, Entra token flow |
| `403 Forbidden` | Danh tính tồn tại nhưng role/scope/condition không cho phép | RBAC mode, role assignment, ABAC repository condition |
| `denied: requested access to the resource is denied` | Pull repo/tag không được cho phép hoặc auth không đáp ứng | Xác định repo, action pull, identity và policy |
| `manifest unknown` hoặc `not found` | Tag/digest không tồn tại, sai tên repository hoặc registry | Kiểm tra tên image chuẩn, push/publish pipeline |
| Timeout, TLS handshake hoặc DNS error | Mạng, firewall, DNS, private endpoint hoặc data endpoint không truy cập được | Đường egress, resolver, route, network restrictions |
| Lỗi sau khi đổi registry mode | Vai trò AcrPull/AcrPush cũ không còn phù hợp với ABAC mode | Migrate sang Repository Reader/Writer và conditions |
| Pull được orders nhưng không pull payments | Có thể là ABAC condition đúng hoặc permission bị thiếu | Đối chiếu chính sách mong muốn và negative tests |
| `az acr login` thành công, `docker push` lỗi | Login thành công nhưng principal không có quyền push | Role Push/Repository Writer phù hợp, repository condition |
| Chỉ app mới lỗi, app cũ vẫn chạy | App mới dùng identity khác, revision mới cần tải image, thay tag/digest | Identity bindings, revision events, artifact và registry config |
| Role mới cấp nhưng chưa pull được | RBAC chưa lan truyền hoặc token/session cũ | Chờ propagation phù hợp, xác nhận role/scope, làm mới phiên theo hướng dẫn |
| Admin login hoạt động nhưng managed identity lỗi | Hai cách xác thực khác nhau; admin bỏ qua ranh giới RBAC mong muốn | Không thay bằng admin; sửa role, identity và ARM audience support |

Mã HTTP/status và thông báo cụ thể có thể khác theo Docker/OCI client, Azure Container Apps và cấu hình registry. Hãy đối chiếu **nội dung thực tế của log** thay vì suy luận một lỗi 401 luôn do đúng một nguyên nhân.

### 13.3. Quy trình điều tra có thứ tự

1. **Xác định image:** login server, repository, tag/digest, environment và revision thực sự thất bại.
2. **Xem revision/system events:** lỗi xảy ra trước khi container chạy (pull) hay trong startup ứng dụng?
3. **Kiểm tra mạng:** registry endpoint và các endpoint layer/data có reachable không? DNS/route/firewall ra sao?
4. **Kiểm tra principal:** Container App đã gắn đúng resource ID managed identity chưa? Registry configuration sử dụng identity nào?
5. **Kiểm tra ACR permissions mode:** RBAC truyền thống hay RBAC + ABAC?
6. **Đối chiếu role và condition:** Object ID/scope/action/repository có đúng?
7. **Kiểm tra cấu hình token/registry:** cơ chế ARM audience hoặc API yêu cầu có phù hợp không?
8. **Kiểm tra artifact:** tag hoặc digest tồn tại, pipeline đã publish thành công chưa?
9. **Kiểm thử có kiểm soát:** thử pull repository được phép và không được phép bằng danh tính tương đương trong môi trường hỗ trợ.
10. **Khắc phục tối thiểu:** sửa role/condition, identity binding, route hoặc tên image; quan sát revision mới và ghi nhận kết quả.

Không cần tạo một registry admin password hoặc gán `Owner` để “thử xem có chạy không”. Việc đó có thể che lỗi cấu hình, làm mất hiệu lực kiểm thử least privilege và tạo rủi ro dài hạn.

## 14. Thực thi least privilege và vận hành vòng đời danh tính

### 14.1. Tách build identity và runtime identity

Một kiến trúc production có thể quy định:

| Danh tính | Resource được phép | Hành động |
|---|---|---|
| `ci-orders-build` | `orders/api` | Push và đọc những artifact cần build/test |
| `mi-orders-acr-pull-prod` | `orders/api` | Pull, không push/xóa |
| `mi-orders-workload-prod` | Key Vault hoặc Storage có liên quan | Truy cập dữ liệu đúng nhu cầu ứng dụng |
| `registry-operators` | Cấu hình ACR và IAM được phê duyệt | Quản trị hạ tầng, không dùng làm credential runtime |

Đặt hai danh tính riêng cho pull và data access không bắt buộc về cú pháp, nhưng giúp tách blast radius khi app bị khai thác. Nếu nhóm quyết định dùng chung một identity cho đơn giản, phải tài liệu hóa lý do và tổng quyền mà identity đang có.

### 14.2. Role assignments có vòng đời

Khi tạo, sửa hoặc xóa Container App:

- Kiểm kê **principal IDs** đang có và role assignments tương ứng.
- Với **system-assigned identity**, xóa resource chủ có thể làm principal biến mất; role assignment liên quan cần được kiểm tra và dọn.
- Với **user-assigned identity**, xóa một Container App không tự xóa danh tính. Nếu giữ identity, phải xem nó còn gắn app nào và còn cần quyền trên registry không.
- Khi chuyển app từ dev sang prod, **không tái sử dụng bừa bãi identity dev có role quá rộng**.
- Khi thu hồi quyền, xem token/credential đã cấp có hiệu lực trong một khoảng thời gian hay không; kiểm thử sau thay đổi và có kế hoạch xử lý khẩn cấp.

Quyền bị thu hồi có thể không khiến một container đang chạy **lập tức dừng lại**: image đã được tải và tiến trình đang hoạt động không cần pull lại mỗi giây. Việc thu hồi sẽ ảnh hưởng các thao tác dữ liệu registry mới, ví dụ pull khi tạo revision/replica mới theo điều kiện dịch vụ.

### 14.3. Bảo vệ artifact ngoài RBAC

RBAC chỉ quyết định người nào được làm thao tác trên registry. Không thể suy ra artifact do pipeline có quyền push là an toàn hoặc đã qua phê duyệt. Hãy bổ sung:

- **Vulnerability scanning** và chính sách chặn bản build có rủi ro nghiêm trọng.
- **Image signing/attestation, provenance và SBOM** theo khả năng công cụ.
- **Digest pinning** trong release manifest và quản lý các tag production quan trọng.
- Review dependency và base image, cập nhật bản vá định kỳ.
- Phê duyệt pipeline release, tách dev/test/prod và bảo vệ branch/tag.
- Kiểm tra cấu hình container runtime: không chạy đặc quyền cao khi không cần, không bake secrets vào image.

Nếu pipeline bị chiếm đoạt nhưng có quyền push vào repository production, attacker vẫn có thể đưa image xấu lên registry. ABAC giảm phạm vi repository bị ảnh hưởng nhưng không thay thế kiểm tra supply chain.

### 14.4. Disable admin user khi đã di chuyển client

Nếu ACR không còn client phụ thuộc vào admin account, có thể cân nhắc tắt:

```bash
# Chỉ chạy sau khi kiểm kê credential và phê duyệt thay đổi.
az acr update \
  --name "$ACR" \
  --resource-group "$ACR_RG" \
  --admin-enabled false
```

Thao tác này có thể làm client cũ mất khả năng login nếu chúng đang dùng admin username/password. Vì thế phải kiểm kê CI pipelines, App Service, Container Apps, AKS và các công cụ ngoài Azure trước khi áp dụng. Việc tắt admin user không thay thế việc xóa secret đã từng bị đưa vào repository hoặc log.

## 15. Tổ chức triển khai bằng Infrastructure as Code

Để tránh drift, nên version hóa:

1. ACR (SKU, networking, policy, permissions mode và diagnostics).
2. Managed identity resources và vị trí gán chúng vào workload.
3. Azure RBAC role assignments và **ABAC conditions** khi dùng mode repository.
4. Container Apps environment, Container App registry configuration và image references.
5. CI/CD federation, policy release và các thông số không nhạy cảm.

Ví dụ tài liệu thiết kế **minh họa, không phải YAML triển khai trực tiếp**:

```yaml
environment: production
acr:
  name: acrplatformprod
  roleAssignmentMode: RBAC+ABAC
  repositories:
    - name: orders/api
      runtimeReader: mi-orders-acr-pull-prod
      pipelineWriter: ci-orders-build
    - name: payments/api
      runtimeReader: mi-payments-acr-pull-prod
      pipelineWriter: ci-payments-build

containerApp:
  name: ca-orders-api-prod
  image: acrplatformprod.azurecr.io/orders/api@sha256:<approved-digest>
  registryIdentity: mi-orders-acr-pull-prod
  applicationIdentity: mi-orders-workload-prod
```

Manifest trên giúp mô tả **ý định** và kiểm thử ranh giới; để triển khai, phải dùng schema thật của **Bicep, ARM hoặc Terraform** và điều kiện ABAC đúng theo API version/khả năng hiện hành. Không đưa secret hay token vào source control.

### 15.1. Thứ tự triển khai để tránh vòng phụ thuộc

Với user-assigned identity, trình tự IaC gợi ý:

```text
Create ACR / chọn permissions mode
         |
         v
Create user-assigned managed identity
         |
         v
Assign Repository Reader hoặc AcrPull theo mode
         |
         v
Create/Update Container Apps environment
         |
         v
Create Container App + identity + registry config + image
         |
         v
Verify revision, image pull, ứng dụng và monitoring
```

Nếu ACR có private endpoint và Container Apps environment cấu hình VNet, phải chuẩn bị **network/DNS trước bước pull**. Khi thay policy trên production, thử nghiệm với canary revision để phát hiện các vấn đề do propagation hoặc network trước khi đổi toàn bộ traffic.

## 16. Chi phí và khả năng vận hành

**Managed identity và role assignment** không phải lý do chính khiến ACR tốn chi phí; tổng chi phí phụ thuộc vào những tài nguyên được tạo và sử dụng.

| Thành phần | Yếu tố chi phí cần dự toán |
|---|---|
| Azure Container Registry | SKU, dung lượng artifacts, thời gian duy trì, các tính năng bổ sung và hoạt động dữ liệu theo giá áp dụng |
| Registry networking | Private endpoint, dữ liệu truyền qua mạng, các thành phần VNet/NAT/firewall |
| Container Apps | Compute/requests/replicas theo mô hình billing của environment và workload |
| Logging | Log Analytics ingestion, retention, Azure Monitor alerts |
| CI/CD | Build agents, image layers/cache, registry tasks nếu dùng |
| Nhân bản/geo-replication | Dung lượng và phân phối image theo SKU và region hỗ trợ |

Đặt tất cả team vào một registry để tiết kiệm có thể làm giảm số resource, nhưng nếu yêu cầu bảo mật và isolation khác nhau, một registry dùng chung đòi hỏi chính sách ABAC/IAM/network và vận hành chặt hơn. Hãy so sánh chi phí với **blast radius** và mức độ phức tạp, không chỉ số lượng registry.

### 16.1. Vì sao nên dọn artifacts và quyền cũ?

Registry tích lũy nhiều tags/manifests/image layers qua mỗi release. Nếu không có retention/cleanup, lưu trữ tăng dần; nếu không dọn role assignments và identities, quyền cũ có thể tồn tại lâu hơn nhu cầu.

Một quy trình tốt:

- Giữ image version đang chạy và các bản rollback theo SLA/DR.
- Dùng retention policy hoặc job dọn artifacts theo khả năng SKU, review trước khi xóa.
- Ghi nhận mapping **Container App revision → digest image** để không xóa nhầm artifact vẫn cần.
- Kiểm kê các principal có quyền Writer/Contributor và các condition quá rộng.
- Theo dõi chi phí và alert khi tăng đột biến dung lượng, số image pull hoặc số revision.

Xóa artifact có thể không làm container đang chạy ngừng ngay, nhưng có thể khiến **scale-out hoặc redeployment không pull lại được**. Luôn đối chiếu các dependency trước khi dọn.

## 17. Bài tập tình huống

### Tình huống A: Container App không pull được image

Một nhóm triển khai:

```text
Container App: ca-orders-api-prod
Registry: acrplatformprod.azurecr.io
Image: acrplatformprod.azurecr.io/orders/api:1.4.2
Identity: mi-orders-acr-pull-prod
```

Registry đã chuyển sang **RBAC + ABAC Repository Permissions mode**. Pipeline trước đây gán role `AcrPull` cho managed identity ở scope registry, nhưng Container Apps revision mới báo lỗi `403` khi pull.

**Nhiệm vụ:**

1. Giải thích vì sao role cũ có thể không còn cấp quyền dữ liệu.
2. Đề xuất role mới và condition chỉ giới hạn `orders/api`.
3. Phân biệt Resource ID và Principal/Object ID của managed identity khi cấu hình hai bước.
4. Liệt kê ba nguồn log/thông tin cần lấy trước khi thay đổi quyền.
5. Nêu một kiểm thử chứng minh app **không** tải được `payments/api`.

**Hướng giải:** xác nhận mode, chuyển sang `Container Registry Repository Reader` với condition repository `orders/api`, gán đúng principal và cấu hình registry identity bằng Resource ID. Kiểm tra Container Apps revision/system logs, ACR diagnostics, role assignments/mode, network và image reference. Kiểm thử positive pull của `orders/api` và negative pull của `payments/api` bằng identity tương đương, tránh dùng admin account vì sẽ che lỗi.

### Tình huống B: tách quyền CI và runtime

Một pipeline tạo bản `2.0.0` của `payments/api` và một Container App tải image này để chạy. Đội bảo mật muốn khi app bị chiếm quyền, kẻ tấn công **không thể ghi đè image production**.

**Yêu cầu thiết kế:**

- Dùng hai danh tính: `ci-payments-build` và `mi-payments-acr-pull-prod`.
- Pipeline có khả năng publish theo repository cần thiết.
- Runtime chỉ có quyền pull.
- Không lưu admin password của ACR trong Container App secrets.
- Ghim image bằng digest trong release manifest.

**Hướng giải:** pipeline sử dụng service principal/OIDC federation hoặc identity của môi trường CI phù hợp, gán `AcrPush` (legacy mode) hoặc Repository Writer (ABAC mode) tại phạm vi cần thiết. Container App dùng user-assigned identity chỉ có `AcrPull` hoặc Repository Reader. Đặt điều kiện repository khi registry dùng ABAC. Cùng với đó, áp dụng image signing/scanning và review release để tránh pipeline push image chưa được phê duyệt.

### Tình huống C: registry private endpoint

Một Container App đã có quyền đúng và registry config đúng, nhưng `orders/api` vẫn không pull được. ACR chỉ cho phép private endpoint và nằm trong topology hub/spoke.

**Nhiệm vụ:** mô tả cách kiểm tra DNS, route, firewall và private endpoint trước khi thêm role; xác định vì sao một lệnh `az acr login` thành công từ laptop của developer không chứng minh Container Apps có đường mạng đến registry.

**Hướng giải:** laptop và Container Apps có thể dùng **những mạng, DNS resolver và nguồn IP khác nhau**. Cần xác minh từ môi trường/workload liên quan: network egress, private DNS, các endpoint registry/data, cổng HTTPS, UDR/NSG/firewall và log. Sau khi mạng đúng mới đối chiếu identity/permissions.

### Tình huống D: thu hồi quyền khi xóa app

Một team đã xóa `ca-orders-api-test` nhưng user-assigned identity `mi-orders-test` vẫn tồn tại và có role Reader ở registry production.

**Nhiệm vụ:** đề xuất quy trình dọn identity và role assignments không còn dùng, xác minh không có Container App khác đang sử dụng identity, và mô tả vì sao xóa app không tự thu hồi toàn bộ quyền của user-assigned identity.

**Hướng giải:** kiểm kê identity bindings, role assignments, owner và last-use evidence nếu có; thực hiện revoke role trước rồi xóa identity theo quy trình khi không còn phụ thuộc. User-assigned identity có vòng đời riêng nên vẫn có thể tồn tại dù một app đã bị xóa.

## 18. Câu hỏi tự kiểm tra

**1. `az acr login` thành công có chứng minh principal được push mọi image không?** Không. Login là xác thực; push cần role/điều kiện authorization phù hợp với repository và registry mode.

**2. Runtime Container App chỉ cần tải image nên chọn quyền gì?** `AcrPull` ở RBAC registry mode, hoặc `Container Registry Repository Reader` với condition phù hợp ở RBAC + ABAC mode.

**3. Vì sao không gán `AcrPush` cho runtime?** Vì runtime không cần sửa artifacts; quyền push làm tăng hậu quả khi danh tính bị lộ hoặc bị lạm dụng.

**4. Managed identity khác admin account của ACR ra sao?** Managed identity là Entra principal được Azure quản lý và kiểm soát bằng role assignments; admin account là credential registry đặc quyền rộng, không gắn với quyền RBAC chi tiết theo principal tương tự.

**5. Principal ID và Resource ID của user-assigned identity có hoán đổi được không?** Không. Principal/Object ID dùng cho RBAC assignee; Resource ID dùng để gán identity vào Container App và chọn registry identity theo cú pháp hỗ trợ.

**6. ACR RBAC + ABAC khác RBAC registry mode thế nào?** ABAC cho phép role repository và điều kiện theo tên repository trong phạm vi hỗ trợ; các role legacy như `AcrPull` không nên được giả định có hiệu lực như cũ.

**7. Container App có quyền Repository Reader nhưng ACR private endpoint bị chặn mạng thì có pull được không?** Không. Cần cả network connectivity và authorization.

**8. Một workload đã pull image và đang chạy có tự dừng ngay khi thu hồi role Reader không?** Không mặc nhiên. Việc đang chạy không cần tải lại image liên tục; pull mới sẽ chịu điều kiện quyền và token còn hiệu lực.

**9. Khi nào nên cấp role Catalog Lister?** Khi client thực sự cần liệt kê tên repository theo khả năng hỗ trợ, không phải chỉ để pull image đã biết tên.

**10. Dùng một registry chung với ABAC có thay thế mọi nhu cầu tách registry không?** Không. Network isolation, encryption boundary, billing, vận hành và compliance có thể vẫn yêu cầu registry riêng.

## 19. Checklist production

- [ ] Đã xác định chính xác ACR, login server, repository, tag/digest và Container App/environment.
- [ ] Đã xác minh **role assignment permissions mode** của registry trước khi chọn role.
- [ ] Chỉ cấp pull cho runtime; cấp push riêng cho CI; tránh admin password trong ứng dụng.
- [ ] Với ABAC mode, đã đặt **repository condition** chính xác và kiểm thử cả allow/deny.
- [ ] Với RBAC registry mode, đã đánh giá việc `AcrPull` áp dụng trên toàn registry có phù hợp không.
- [ ] Đã ghi rõ Principal/Object ID, Client ID và Resource ID của managed identity, không nhầm khi cấu hình.
- [ ] Identity được gắn thật vào Container App và registry entry dùng đúng identity.
- [ ] Đã xem xét **ARM audience token authentication** khi cần cho cơ chế managed identity pull.
- [ ] Đã kiểm tra DNS, TLS, private endpoint, registry firewall và đường egress từ Container Apps environment.
- [ ] Đã chọn OCI image được phê duyệt, ghim version/digest, có scan và provenance phù hợp.
- [ ] Đã tách quyền CI publish với quyền runtime pull; federation/credentials của CI có scope hẹp.
- [ ] Đã cấu hình ACR diagnostic logs, Container Apps system logs, Azure Activity Log và cảnh báo phù hợp.
- [ ] Đã thử Container Apps revision mới, trường hợp image không tồn tại, thiếu quyền và mất kết nối mạng.
- [ ] Đã có runbook xử lý sự cố 401/403, network timeout, RBAC propagation và đổi permission mode.
- [ ] Đã kiểm kê user-assigned identities dùng chung, role assignments không còn cần và quyền Catalog Lister.
- [ ] Đã dự toán và theo dõi chi phí registry, storage, networking, Container Apps, logging và CI.
- [ ] Đã đưa ACR, identities, role assignments/ABAC conditions và Container Apps config vào IaC/review.

## Kết luận

**Azure Container Registry** là nơi lưu và phân phối image, còn **Microsoft Entra ID, Azure RBAC và managed identity** cung cấp cơ chế xác thực/ủy quyền có thể kiểm soát theo workload mà không phải chia sẻ mật khẩu registry. Với Container Apps, user-assigned managed identity giúp chuẩn bị quyền **pull** trước, gắn danh tính vào app và cấu hình registry authentication bằng identity thay vì username/password.

Điểm quan trọng nhất là chọn đúng mô hình phân quyền ACR: **`AcrPull`/`AcrPush`** cho chế độ registry-level RBAC tương ứng, hoặc **Container Registry Repository Reader/Writer** cùng điều kiện repository khi dùng **RBAC + ABAC Repository Permissions mode**. Cấu hình đúng cần đi cùng kết nối mạng, DNS, bảo mật pipeline, version/digest của image, logging, kiểm thử từ chối và quản trị vòng đời identity. Nhờ đó, ứng dụng Azure chỉ có những quyền registry thật sự cần thiết trong suốt quá trình build, deploy, scale và vận hành.
