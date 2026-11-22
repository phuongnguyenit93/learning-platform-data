# GitHub Actions và triển khai workload lên Azure

Một nhóm phát triển ứng dụng Spring Boot nhận hàng chục pull requests mỗi tuần. Họ cần **tự động kiểm thử khi có PR, build một artifact có thể truy vết, triển khai bản đã kiểm tra lên staging**, rồi chỉ đưa lên production sau khi có phê duyệt. Workload có thể là một ứng dụng Java chạy trên **Azure App Service**, container chạy trên **Azure Container Apps** hoặc service trong **Azure Kubernetes Service (AKS)**. Nhóm không muốn lưu Azure service principal client secret dài hạn trong GitHub, cũng không muốn workflow trên một nhánh bất kỳ có quyền sửa toàn subscription.

**GitHub Actions** cung cấp bộ máy chạy workflow theo sự kiện GitHub. Khi kết hợp **Microsoft Entra workload identity federation qua OpenID Connect (OIDC)**, Azure RBAC, GitHub Environments và một quy trình artifact promotion, nhóm có thể xây pipeline CI/CD mà **không phải cấp mật khẩu Azure tĩnh cho runner**. Tuy nhiên, thiết kế bảo mật quan trọng không kém YAML: workflow có thể bị lạm dụng nếu GitHub token quá rộng, phụ thuộc third-party action chưa kiểm soát, chạy code PR không tin cậy với quyền deploy, hoặc publish image thay đổi được sau khi phê duyệt.

Bài **“GitHub Actions và triển khai workload lên Azure”** thuộc chương **CI/CD và chuỗi cung ứng phần mềm** trong module **CLOUD_PROVIDERS_AZURE**. Nội dung đặt GitHub Actions vào bức tranh Azure rộng hơn: subscription/resource group, Microsoft Entra ID, mạng ảo, compute, container registry, dữ liệu, giám sát, bảo vệ tài nguyên và FinOps.

Sau bài học, bạn có thể:

- Phân biệt **continuous integration, continuous delivery, continuous deployment** và pipeline theo workload.
- Đọc/viết một workflow GitHub Actions: `on`, jobs, steps, runners, contexts, permissions, artifacts, cache, environments và concurrency.
- Thiết lập **GitHub OIDC → Microsoft Entra federated credential → Azure RBAC** đúng repo/branch/environment, không cần Azure password.
- Viết pipeline **Maven/Java 21 → Azure App Service** có kiểm thử, artifact độc lập và môi trường staging.
- Viết pipeline **Docker image → Azure Container Registry (ACR) → Azure Container Apps** sử dụng image digest bất biến.
- Quyết định khi nào dùng **AKS/Helm** hoặc **GitOps/Flux** và tránh cấp cluster-admin cho CI.
- Triển khai release gates, canary/slots/revisions, rollback, migrations và smoke tests có kiểm soát.
- Áp dụng security scanning, SBOM/provenance, pin GitHub Actions, least privilege, secrets và branch protection.
- Vận hành runner/network/private endpoints, xử lý lỗi OIDC/ACR/health, đo SLO và quản lý chi phí pipeline.

> **Phạm vi:** Những workflow YAML và lệnh Azure là **mẫu giáo dục có placeholder**. Không có tài nguyên Azure hoặc GitHub thật nào được thay đổi khi soạn bài. GitHub Action major versions, Azure CLI options và tính năng hosting có thể đổi; trước khi áp dụng thực tế phải kiểm tra compatibility của action/runtime, khóa commit SHA cho third-party actions và chạy thử trên môi trường được phê duyệt.

## 1. Từ commit đến bản phát hành có thể truy vết

**CI** trả lời: “Source code ở commit này có compile, test, lint và đáp ứng kiểm tra bảo mật không?” **CD** trả lời: “Artifact đã qua kiểm tra có được đưa đến môi trường đích một cách an toàn, lặp lại được và có thể phục hồi không?”

| Khái niệm | Đầu vào | Đầu ra | Có tự deploy production? |
|---|---|---|---|
| **CI** | Push/PR, commit SHA | Tests, static analysis, binary/image, reports | Không |
| **Continuous delivery** | Artifact đã kiểm tra | Sẵn sàng release với approval gate | Không nhất thiết |
| **Continuous deployment** | Artifact đã kiểm tra và policy tự động | Triển khai production tự động | Có, nếu mọi gate đạt |
| **Release management** | Version/digest, changelog, risk, approvals | Release decision/audit | Có thể thủ công hoặc tự động |
| **GitOps** | Git desired state được phê duyệt | Controller trong cluster reconcile workload | CI thường chỉ build và cập nhật Git |

Một pipeline đáng tin cần:

~~~text
Git commit SHA
    ↓
CI: compile → unit/integration tests → security checks
    ↓
Build immutable artifact/image + metadata/SBOM
    ↓
Publish artifact to trusted store/registry
    ↓
Deploy exactly that artifact to staging
    ↓
Health/smoke/security/performance gates
    ↓
Human approval (when required)
    ↓
Promote same artifact digest to production
    ↓
Monitor → rollback/mitigate if SLO breached
~~~

**Không build lại một image từ nhánh `main` sau khi staging pass rồi gọi đó là cùng release**: dependencies/base image có thể thay đổi, tạo binary khác. Promotion phải đi theo **artifact ID/digest** đã được kiểm tra.

## 2. GitHub Actions: mô hình vận hành

~~~mermaid
flowchart LR
    DEV[Developer PR/Push] --> GH[GitHub repository and events]
    GH --> WF[Workflow .github/workflows/deploy.yml]
    WF --> CI[CI job on runner]
    CI --> ART[Build artifact / image digest]
    ART --> STG[Staging job with OIDC]
    STG --> APPROVAL[GitHub Environment approval]
    APPROVAL --> PROD[Production job with separate OIDC identity]
    PROD --> AZ[Azure App Service / Container Apps / AKS]
    AZ --> MON[Azure Monitor + smoke checks]
    MON -. Failed health .-> RB[Rollback process]
~~~

### 2.1. Những thành phần chính

| Thành phần | Ý nghĩa | Rủi ro phổ biến |
|---|---|---|
| **Workflow** | File YAML trong `.github/workflows/` | Trigger quá rộng hoặc lỗi branch filtering |
| **Event** | `pull_request`, `push`, `workflow_dispatch`, release... | Chạy code PR không tin cậy với secrets |
| **Job** | Một tập steps trên runner | Giả định filesystem/state dùng chung giữa jobs |
| **Step** | Chạy shell command hoặc action | Dùng action từ untrusted source |
| **Runner** | Máy GitHub-hosted hoặc self-hosted chạy job | Quyền mạng/identity/egress và rò dữ liệu |
| **GITHUB_TOKEN** | Token GitHub sinh cho workflow/job | Mặc định quyền quá rộng nếu không khai báo |
| **OIDC token** | JWT ngắn hạn từ GitHub issuer cho federation | Subject/audience không giới hạn hoặc identity Azure quá quyền |
| **Environment** | Staging/prod, protection rules, environment vars | Không có review gate hoặc dùng identity staging cho prod |
| **Artifact** | Build output và reports lưu giữa jobs | Build/redeploy khác artifact hoặc giữ quá lâu |
| **Cache** | Dữ liệu tăng tốc package manager/build | Cache poisoning/không thay artifact integrity |
| **Concurrency** | Không cho nhiều deployments trùng môi trường | Cancel nhầm production job đang rollout |

### 2.2. Workflow, jobs và steps

~~~yaml
name: Minimal CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Show runtime
        run: java -version
~~~

Mẫu này minh họa **cú pháp**, không đủ để bảo đảm Java 21 đã cài hay test đã chạy. Lưu ý YAML parse tên khóa `on` đặc biệt ở một số thư viện YAML 1.1; GitHub Actions hiểu `on` theo schema workflow. Khi lint workflow dùng công cụ tương thích GitHub Actions.

### 2.3. Runners không tự chia sẻ filesystem

Nếu job `build` tạo `target/orders-api.jar`, job `deploy` chạy trên runner mới sẽ **không thấy file đó** trừ khi dùng `upload-artifact`/`download-artifact` hoặc registry. Đừng build lại trong deployment job nếu mục tiêu là promote nguyên artifact.

~~~text
Job build → actions/upload-artifact → GitHub artifact store
Job deploy → actions/download-artifact → Azure deployment action
~~~

Với OCI image, **ACR và image digest** là artifact store thích hợp hơn việc truyền Docker tarfile giữa jobs.

### 2.4. GitHub-hosted hay self-hosted runner?

**GitHub-hosted:** môi trường ephemeral do GitHub vận hành, đơn giản cho CI và thường thích hợp với build/test, public Azure endpoints. Nó **không mặc định có private route** tới Azure SQL/AKS/private-only apps trong VNet.

**Self-hosted:** chạy trong mạng do tổ chức quản lý, có thể tiếp cận private Azure endpoints, nhưng phải vá OS, cô lập workflows, kiểm soát labels/permissions và dọn workspaces. Không cấp trusted runner cho mọi PR từ fork; attacker có thể khai thác quyền mạng hoặc dữ liệu còn lại.

### 2.5. Workflow files là code có đặc quyền

Sửa `.github/workflows/deploy.yml` có thể thay đổi điều kiện phê duyệt, lệnh deploy, đường upload artifact hoặc credentials. Vì vậy cần branch protection, CODEOWNERS và review đặc biệt cho workflow files. Không cấp runner quyền production chỉ vì repository là private.

## 3. Sự kiện và giới hạn trigger

### 3.1. Chọn đúng sự kiện

| Trigger | Khi nào | Quyền nên có |
|---|---|---|
| `pull_request` | Build/test PR, kiểm tra trước merge | Chỉ đọc; không deploy production |
| `push` vào `main` | Build artifact/release tới staging | OIDC staging nếu branch được bảo vệ |
| `workflow_dispatch` | Run thủ công có kiểm soát | Environment approvals/validation input |
| `release` | Deploy một release đã phát hành | Validate source tag/artifact/digest |
| `schedule` | Security scans/maintenance checks | Minimal GitHub/Azure permissions |
| `workflow_call` | Reusable workflow đã review | Giới hạn inputs/secrets/permissions ở caller |
| `pull_request_target` | Automation cần quyền context base repo | **Nguy hiểm** nếu checkout/chạy code PR không tin cậy |

### 3.2. Tránh trigger production từ code không tin cậy

Một pattern an toàn:

~~~text
PR from feature/fork:
  tests and static analysis only
  no Azure OIDC/id-token permission
  no production environment access

Protected main:
  CI + staging deployment, staging identity only

Production:
  reviewed environment with separate Azure identity
  deployment restricted by branches/release policy
~~~

Với `pull_request_target`, workflow có thể chạy với quyền của base repository. **Không checkout và thực thi mã từ untrusted PR bằng token có quyền ghi/secrets**. Chỉ sử dụng sự kiện này khi đã review threat model cho từng action/checkout command.

### 3.3. Branch filtering, paths và tag không phải authorization

~~~yaml
on:
  push:
    branches: [main]
    paths:
      - 'src/**'
      - 'pom.xml'
      - '.github/workflows/deploy.yml'
~~~

`paths` giúp giảm build không cần thiết nhưng không bảo vệ production. Một người có quyền ghi vào `main` có thể sửa file workflow để thay điều kiện. **Branch protection và GitHub Environment protection rules**, cộng Entra federated identity subject, mới là lớp authorization cần kết hợp.

### 3.4. Concurrency cho môi trường

~~~yaml
concurrency:
  group: staging-deploy
  cancel-in-progress: true
~~~

Trên staging có thể muốn bỏ run cũ khi commit mới đến. Với production, `cancel-in-progress: true` có thể **cắt ngang rollout hoặc migration**. Thiết kế group riêng theo environment và chỉ cho phép concurrency policy đã kiểm chứng; không dùng cùng group cho mọi môi trường.

## 4. Xác thực GitHub → Azure bằng OIDC, không dùng secret dài hạn

**OpenID Connect federation** cho phép workflow trên GitHub nhận một **OIDC JWT ngắn hạn**, được Microsoft Entra kiểm tra theo **issuer, audience và subject** của một federated identity credential. Entra cấp access token để workflow gọi Azure Resource Manager/đích được phép.

### 4.1. Chuỗi tin cậy

~~~mermaid
sequenceDiagram
    participant GH as GitHub job
    participant OIDC as GitHub OIDC issuer
    participant ENTRA as Microsoft Entra ID
    participant ARM as Azure Resource Manager
    participant TARGET as Azure workload
    GH->>OIDC: Request job OIDC token (id-token permission)
    OIDC-->>GH: Short-lived signed JWT (repo/environment claims)
    GH->>ENTRA: Exchange JWT for Azure access token
    ENTRA->>ENTRA: Match issuer / audience / subject credential
    ENTRA-->>GH: Scoped Azure access token
    GH->>ARM: Deploy using Azure token
    ARM->>ARM: Enforce Azure RBAC
    ARM->>TARGET: Apply permitted resource operation
~~~

Có **hai phép kiểm soát riêng**:

1. **Federated credential** quyết định workflow identity nào có thể nhận token với Azure principal.
2. **Azure RBAC** quyết định principal đó có thể làm gì ở subscription/resource group/resource cụ thể.

Federation khớp không đồng nghĩa có quyền deploy; Azure RBAC Contributor rộng không đồng nghĩa workflow từ nhánh bất kỳ được cấp OIDC token nếu federated credential chặt.

### 4.2. Những claims quan trọng

| Claim/field | Giá trị minh họa | Vai trò |
|---|---|---|
| **Issuer** | `https://token.actions.githubusercontent.com` | JWT issuer của GitHub |
| **Audience** | `api://AzureADTokenExchange` | Token exchange audience thông dụng của Azure |
| **Subject** (environment) | `repo:acme/orders-api:environment:staging` | Workflow job gắn GitHub Environment staging |
| **Subject** (branch) | `repo:acme/orders-api:ref:refs/heads/main` | Workflow từ branch main theo subject format |
| **Principal/client ID** | Client ID của Entra app hoặc user-assigned MI | Target identity để trao token |
| **Tenant ID** | Azure tenant chứa principal | Môi trường xác thực |
| **Subscription ID** | Subscription deploy theo quy trình | Scope quản Azure, không phải credential |

**Lưu ý cực quan trọng:** Nếu job dùng `environment: staging`, subject mặc định thường là dạng `repo:ORG/REPO:environment:staging` **không phải** branch subject `ref:refs/heads/main`. Chọn subject **phù hợp chính xác** với workflow và policy; GitHub cho phép tùy biến subject claims ở một số tổ chức, nên phải kiểm tra claim thực. **Subject chỉ gắn environment không tự hạn chế branch** nếu environment protection không hạn chế; cần branch restrictions/approvals của GitHub Environment.

### 4.3. Service principal hoặc user-assigned managed identity?

OIDC federation có thể gắn với **Microsoft Entra application/service principal** hoặc **user-assigned managed identity** ở những kiểu cấu hình được hỗ trợ:

- **Entra application:** tạo app registration/service principal, thêm federated credential, assign Azure RBAC.
- **User-assigned managed identity:** tạo identity, thêm federated credential, assign Azure RBAC và dùng client ID của identity.

Không cần tạo client secret khi dùng OIDC. **System-assigned managed identity gắn vào App Service/runtime Azure** không tự trở thành identity GitHub workflow; CI cần principal có federation phù hợp. Runtime identity để app truy cập Key Vault/SQL/ACR thường **khác** CI deployment identity để giảm blast radius.

### 4.4. Quy trình cấu hình ở mức khái niệm

1. Tạo **GitHub Environment staging** và **production**, cấu hình required reviewers và deployment branch rules phù hợp.
2. Tạo **hai Azure identities riêng** cho staging/prod khi có thể.
3. Trên mỗi Entra principal, tạo federated credential với issuer/audience và **subject đúng Environment**.
4. Cấp **Azure RBAC tối thiểu** cho identity staging tại staging resource, identity production tại production resource.
5. Ghi **client ID, tenant ID, subscription ID** ở GitHub **environment variables** (chúng là identifiers, không phải passwords).
6. Workflow dùng `permissions: id-token: write` và `azure/login@v2` để trao token.
7. Test staging rồi đọc Azure Activity Log/Entra sign-in tương ứng, xác nhận quyền không vượt scope.
8. Test yêu cầu approval/branch restriction trước khi workflow production nhận được token.

### 4.5. YAML OIDC login tối thiểu

~~~yaml
name: Azure OIDC smoke test

on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  azure-whoami:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Login to Azure
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
      - name: Confirm authorized scope
        run: |
          az account show --query "{name:name,id:id,tenantId:tenantId}" -o table
~~~

**`id-token: write` cho phép workflow yêu cầu OIDC token**, không tự cấp Azure Contributor. **`contents: read`** là quyền GitHub token để checkout/truy cập repository, không phải permission ở Azure. Trong production, pin full commit SHA của `azure/login` và các actions khác; `@v2` chỉ là phiên bản dễ đọc trong bài.

### 4.6. Những lỗi federation điển hình

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Không lấy được OIDC token | Thiếu `id-token: write` | Thêm permission cho **đúng job** cần login |
| Entra token exchange bị từ chối | Issuer/audience/subject không khớp | Đối chiếu federated credential với job environment/branch |
| Environment staging nhưng credential branch main | GitHub subject là `environment:staging` | Tạo đúng subject, bật environment rules |
| Azure login thành công, deploy bị 403 | Azure RBAC chưa được cấp ở target scope | Cấp role tối thiểu tại đúng resource |
| Login trỏ nhầm subscription | GitHub vars/chọn subscription sai | Đối chiếu tenant/subscription và resource IDs |
| Production job chạy trên PR | Trigger/jobs/branch restrictions thiếu | Tách CI và deploy, GitHub environment protection |
| Token bị gửi lên ngoài | Untrusted action/script đọc OIDC token | Action allowlist/pinning, permission minimization |

**Không sửa federation failed bằng cách tạo client secret rồi lưu vào GitHub Secrets** khi mục tiêu là passwordless OIDC; trước tiên kiểm tra policy/claims/role đúng.

## 5. Chuẩn bị Azure, GitHub và ranh giới quyền

Trong bài thực hành, giả định nhóm **đã được cấp**:

- Một GitHub repository chứa ứng dụng Spring Boot/Maven, có branch `main` được bảo vệ.
- GitHub Environments `staging` và `production`, với reviewers/branch policies phù hợp.
- Một Azure subscription/resource group staging, một subscription/resource group production (hoặc boundaries tương đương được phê duyệt).
- Azure App Service hoặc Container Apps đã provision, Java runtime/container settings và DNS/health checks hoạt động.
- ACR dùng cho image workloads nếu chọn Container Apps/AKS.
- Hai Microsoft Entra identities với federated credentials **khớp GitHub environment**, RBAC hạn chế ở từng đích.
- Quyền đọc Azure Monitor/Application Insights/Activity Log phục vụ xác minh sau deploy.

**Bài không yêu cầu tạo mới resources production.** Nếu chưa có tenant, subscription, target app, hoặc người thực hành không có quyền IAM, có thể làm bài phân tích YAML/policy và unit tests trên local, nhưng không được bypass review bằng personal subscription/tài khoản không được phép.

### 5.1. Tách CI principal và runtime identity

~~~mermaid
flowchart LR
    GH[GitHub workflow] -->|OIDC federation| DEPLOY[Deployment identity]
    DEPLOY -->|Azure RBAC scoped to target| ARM[Azure Resource Manager]
    ARM --> APP[App Service/Container App]
    APP -->|Runtime managed identity| KV[Key Vault]
    APP -->|Runtime database identity| DB[Azure SQL/PostgreSQL]
    APP -->|Runtime AcrPull if container| ACR[Azure Container Registry]
~~~

**Không cấp identity của GitHub workflow quyền đọc mọi secrets trong Key Vault hoặc mọi bảng database** chỉ vì ứng dụng runtime cần chúng. Deployment identity chỉnh resource/phiên bản chạy; runtime identity truy cập dependencies phục vụ business; migration identity có quyền DDL riêng khi cần.

### 5.2. Scope RBAC

| Principal | Scope mong muốn | Quyền cần xét |
|---|---|---|
| GitHub staging deploy | App Service/Container App staging và phụ thuộc deploy | Role built-in/custom cho thao tác deploy cần thiết |
| GitHub production deploy | Production app hoặc resource group hạn chế | Không cấp toàn subscription Contributor nếu không cần |
| GitHub image publisher | ACR hoặc repository cụ thể | `AcrPush`/repository Writer theo ACR authorization mode |
| App Service/Container App runtime | Key Vault, Storage, Azure SQL theo nhu cầu | Key Vault Secrets User/DB grants tương ứng |
| Container App/AKS image pull identity | ACR | `AcrPull`/repository Reader |
| Database migration job | Target DB schema | DDL permission theo migration plan |
| Observability operator | Azure Monitor/Log Analytics | Đọc logs/metrics không sửa workload |

**Azure RBAC Contributor không tự cấp quyền JDBC `SELECT` cho Azure SQL** hoặc PostgreSQL. Tương tự, `AcrPull` không cấp quyền publish image.

### 5.3. Ví dụ Azure CLI chỉ đọc kiểm tra subscription

~~~bash
az account show --query "{name:name,id:id,tenantId:tenantId}" -o table
az resource show \
  --ids "<approved-target-resource-id>" \
  --query "{id:id,type:type,location:location}" \
  -o json
~~~

Những lệnh này không deploy; chỉ xác nhận đúng target. Mọi lệnh `az role assignment create` hoặc thay federation cần phê duyệt IAM. Không copy tên role/target resource IDs từ môi trường staging sang production mà không kiểm tra.

### 5.4. GitHub Environments và deployment branches

Trong repository settings, cấu hình:

~~~text
Environment: staging
  deployment branches: main
  required reviewers: optional depending on team policy
  vars: AZURE_CLIENT_ID, AZURE_TENANT_ID,
        AZURE_SUBSCRIPTION_ID, AZURE_WEBAPP_NAME

Environment: production
  deployment branches: main or approved release tags
  required reviewers: platform/on-call/release owner
  vars: separate production identity and resource identifiers
~~~

**Environment protection có thể có giới hạn theo GitHub plan/loại repository/cấu hình tổ chức**; không coi một trường UI chưa bật là gate thật. Để production approval có giá trị, cần kiểm tra người submit không thể tự sửa workflow/điều kiện bảo vệ hoặc approve chính job của họ trái policy.

### 5.5. GitHub variables và secrets

- **`vars.AZURE_CLIENT_ID`, `vars.AZURE_TENANT_ID`, `vars.AZURE_SUBSCRIPTION_ID`:** identifiers, không phải credential bí mật; vẫn nên bảo vệ quyền thay đổi để tránh deploy nhầm.
- **GitHub Secrets:** dùng cho third-party credentials khi không thể thay OIDC; audit/rotate/quyền đọc.
- **GitHub `GITHUB_TOKEN`:** token tự cấp cho job theo `permissions`; không lưu thủ công.
- **Azure managed identity:** không đưa password vào GitHub; federation cấp token ngắn hạn.
- **App runtime secrets:** dùng Key Vault/managed identity hoặc cơ chế secret injection an toàn ở hosting service, không bake trong JAR/Docker image.

## 6. Thiết kế pipeline nhiều jobs: kiểm thử, artifact và triển khai

### 6.1. Job graph có checkpoints

~~~mermaid
flowchart TB
    PR[Pull Request] --> TEST[Build + unit/integration tests]
    MAIN[Push protected main] --> TEST
    TEST -->|PASS| PKG[Publish immutable build artifact]
    PKG --> STAGING[Deploy staging with staging OIDC]
    STAGING --> SMOKE[Health + API contract smoke tests]
    SMOKE --> APPROVAL[Production Environment approval]
    APPROVAL --> PROD[Deploy same artifact with prod OIDC]
    PROD --> VERIFY[Validate production health/SLO]
    VERIFY -->|FAIL| ROLLBACK[Approved rollback / incident]
~~~

Trong YAML có thể dùng `needs` để định nghĩa dependencies. Nếu bất kỳ job trước thất bại, downstream thường không chạy; đây là **release gate** chứ không cần thêm một shell check `if previous.status == failed` cho mỗi step.

### 6.2. CI chỉ đọc mã nguồn

~~~yaml
permissions:
  contents: read

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - name: Build and verify
        run: mvn --batch-mode --no-transfer-progress clean verify
~~~

**`setup-java cache: maven`** tăng tốc tải dependencies, **không thay** reproducible dependency locks/SBOM. Với project có Maven Wrapper, ưu tiên wrapper `./mvnw` đã được review và kiểm tra checksum; ví dụ dùng Maven CLI sẵn trên runner để dễ đọc.

### 6.3. Tách build và deploy

Với Java JAR:

~~~yaml
- uses: actions/upload-artifact@v4
  with:
    name: orders-api-jar
    path: target/orders-api-1.0.0.jar
    if-no-files-found: error
    retention-days: 7
~~~

Ở job deploy:

~~~yaml
- uses: actions/download-artifact@v4
  with:
    name: orders-api-jar
    path: dist
~~~

Tên JAR là giả định project `orders-api` version `1.0.0` tạo đúng file. Nếu Maven tạo thêm `original-...jar`, dùng output path xác định sau packaging, **không deploy wildcard trùng nhiều artifacts**. Nếu build chạy trên PR, artifact là untrusted until reviewed; không nâng artifact từ PR lên production chỉ bằng cách biết tên.

### 6.4. CI test matrix

Với ứng dụng liên quan PostgreSQL/SQL Server hoặc nhiều JDK:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: ['21']
    test-suite: [unit, integration]
~~~

Một matrix cần **lệnh riêng tương ứng test-suite**, chứ không có nghĩa `mvn verify` tự đổi tests theo matrix name. Integration tests có thể cần Testcontainers/Docker, database secrets hoặc private Azure network; phân biệt tests ephemeral an toàn trên PR với tests Azure staging có quyền.

### 6.5. Không dùng cache làm artifact nguồn của production

Cache được tối ưu để reuse dependencies/builder state, có eviction/miss. Artifact release cần **định danh, integrity và retention**; container image nên pin digest; JAR nên có SHA-256, commit provenance và xác minh download. Cache poisoning có thể xảy ra nếu trust boundaries không phù hợp, nên tránh restore cache writable từ untrusted workflows vào privileged builds mà không kiểm soát.

## 7. Mẫu đầy đủ: Maven → Azure App Service staging → production

Giả sử dự án có:

~~~text
Repository: acme/orders-api
Protected branch: main
Maven output: target/orders-api-1.0.0.jar
Azure staging App Service: orders-api-staging
Azure production App Service: orders-api-production
Runtime: Java 21, Spring Boot
Environment vars: AZURE_CLIENT_ID, AZURE_TENANT_ID,
                  AZURE_SUBSCRIPTION_ID, AZURE_WEBAPP_NAME
Authentication: GitHub OIDC / separate identities per environment
~~~

**Hai App Services tách biệt** được dùng để minh họa promotion. Cách này không phụ thuộc deployment slots; slot swap được đề cập ở phần sau.

### 7.1. Workflow tự chứa cho một repository mẫu

File hướng dẫn người học tạo `.github/workflows/app-service-release.yml` trong repository riêng:

~~~yaml
name: Java App Service release

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout exact source revision
        uses: actions/checkout@v4

      - name: Set up Java 21
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Compile and test
        run: mvn --batch-mode --no-transfer-progress clean verify

      - name: Publish verified JAR
        uses: actions/upload-artifact@v4
        with:
          name: orders-api-jar
          path: target/orders-api-1.0.0.jar
          if-no-files-found: error
          retention-days: 7

  deploy-staging:
    if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    permissions:
      contents: read
      id-token: write
    concurrency:
      group: orders-api-staging
      cancel-in-progress: false
    steps:
      - name: Download the exact build artifact
        uses: actions/download-artifact@v4
        with:
          name: orders-api-jar
          path: dist

      - name: Azure login via OIDC (staging)
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy JAR to staging App Service
        uses: azure/webapps-deploy@v3
        with:
          app-name: ${{ vars.AZURE_WEBAPP_NAME }}
          package: dist/orders-api-1.0.0.jar

      - name: Staging smoke check
        shell: bash
        env:
          APP_HOST: ${{ vars.AZURE_WEBAPP_HOSTNAME }}
        run: |
          test -n "$APP_HOST"
          curl --fail --silent --show-error --retry 4 --retry-delay 5 \
            "https://$APP_HOST/actuator/health/readiness"

  deploy-production:
    if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    concurrency:
      group: orders-api-production
      cancel-in-progress: false
    steps:
      - name: Download the same build artifact
        uses: actions/download-artifact@v4
        with:
          name: orders-api-jar
          path: dist

      - name: Azure login via OIDC (production)
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy the approved JAR to production
        uses: azure/webapps-deploy@v3
        with:
          app-name: ${{ vars.AZURE_WEBAPP_NAME }}
          package: dist/orders-api-1.0.0.jar

      - name: Production smoke check
        shell: bash
        env:
          APP_HOST: ${{ vars.AZURE_WEBAPP_HOSTNAME }}
        run: |
          test -n "$APP_HOST"
          curl --fail --silent --show-error --retry 4 --retry-delay 5 \
            "https://$APP_HOST/actuator/health/readiness"
~~~

**Yêu cầu để ví dụ hoạt động thực sự:**

1. App Service **đã tồn tại**, có Java 21 runtime và khả năng deploy JAR theo `azure/webapps-deploy`; không dùng ví dụ như lệnh provision Azure.
2. Maven project tạo đúng `target/orders-api-1.0.0.jar` có entry point Spring Boot.
3. `staging` và `production` environments khai báo **variables tương ứng**; hai client IDs/identities không nên trùng.
4. Entra federated credentials phải khớp `repo:ORG/REPO:environment:staging` và `...:production`, environment protection rules giới hạn branch/review.
5. Identities có Azure RBAC deploy đủ nhưng không vượt scope; app runtime identities và DB permissions là chuyện riêng.
6. Endpoint `/actuator/health/readiness` phải **được cấu hình, có thể truy cập từ runner** và không để lộ metadata nhạy cảm. App Service private-only cần runner/network hoặc internal health check khác.
7. Workflow `workflow_dispatch` chỉ deploy khi ref là `refs/heads/main`; nếu muốn release từ tag, phải thiết kế trigger/ref policy và federation riêng.
8. `@v4`/`@v3`/`@v2` cho actions là **major tags minh họa**, không đủ supply-chain hardening; pin SHA đầy đủ của trusted actions trong repo thật.

### 7.2. Vì sao đây là một artifact promotion?

~~~text
build job:
  target/orders-api-1.0.0.jar
  → actions/upload-artifact (name: orders-api-jar)

deploy-staging job:
  download name: orders-api-jar
  → deploy JAR to staging
  → smoke passes

deploy-production job:
  download same name: orders-api-jar
  → deploy JAR to production
~~~

Job production **không rebuild Maven**. Tuy nhiên để có chứng nhận release tốt hơn, thêm SHA-256 digest/signing và bảo đảm artifact được lấy từ **cùng GitHub workflow run đã thông qua CI**; không chỉ so trùng filename. Artifact retention cần đủ thời gian chờ approval, hoặc phát hành vào kho immutable theo chính sách.

### 7.3. Vì sao không đặt `id-token: write` ở mọi job?

CI chạy PR không cần Azure access. Cấp `id-token: write` tại **deploy jobs** thay vì workflow-wide giảm bề mặt để untrusted code/action có thể yêu cầu OIDC token. Environment restrictions và federated credential vẫn cần; GitHub token permissions không thay Entra claims.

### 7.4. Production approval và audit

`environment: production` cho phép dùng required reviewers khi plan/setting hỗ trợ. Trong workflow mẫu, approval được yêu cầu **trước khi production job bắt đầu** và trước bước `azure/login` production. Nếu production environment không có rules, job có thể chạy **tự động** sau staging. Vì vậy production release policy phải được **kiểm chứng trong Settings và thử nghiệm**, không chỉ nhìn YAML.

### 7.5. Khi `workflow_dispatch` có input release version

Cho phép workflow chạy thủ công có thể hữu ích, nhưng input tự do dạng `resource_group`/`subscription_id` hoặc `script_to_run` dễ dẫn đến target confusion/command injection nếu ghép vào shell. Ưu tiên lựa chọn enumerated, môi trường được bảo vệ và immutable artifact digest đã tồn tại, không để operator nhập chuỗi lệnh PowerShell/Bash tùy ý.

## 8. Xác minh và rollback ứng dụng trên App Service

### 8.1. Triển khai thành công ≠ ứng dụng khỏe

`azure/webapps-deploy` có thể hoàn tất upload package mà Spring Boot vẫn không khởi động vì:

- App Service runtime Java/OS không phù hợp JAR.
- Thiếu environment variable/KV reference/database connection.
- Migrations chưa hoàn thành hoặc database private DNS sai.
- Startup command/port sai, hoặc health endpoint bị chặn.
- JVM khởi động chậm hơn timeout health.
- Phiên bản mới làm tăng HTTP 500/CPU/memory.

Pipeline phải thực hiện **post-deploy smoke checks** và quan sát traces/metrics, không dừng ở trạng thái GitHub job xanh.

### 8.2. Kiểm tra release đúng version

Một endpoint `/version` đã được bảo vệ có thể báo:

~~~json
{
  "service": "orders-api",
  "commitSha": "cafebabe0123",
  "artifactSha256": "<sha256>",
  "buildTimeUtc": "2026-11-20T09:20:00Z",
  "environment": "staging"
}
~~~

Các giá trị là **minh họa**. Đừng đưa secrets, token, internal database hostname hoặc dữ liệu nhạy cảm ra public version endpoint. Khi kiểm tra production, so sánh commit/artifact hash với release manifest, không chỉ dựa `200 OK`.

### 8.3. Kế hoạch rollback App Service

Trường hợp dùng **hai App Services độc lập** như workflow phần 7:

1. Giữ **last known good JAR** trong artifact repository/retention phù hợp.
2. Khi production release gây lỗi, tạm dừng các deployments tiếp theo.
3. Chọn release đã phê duyệt bằng **immutable artifact identifier/hash**, không rebuild `main`.
4. Deploy lại JAR cũ bằng production identity có quyền, qua approval/break-glass policy.
5. Đo health, 5xx, dependency latency và business transactions.
6. Nếu schema database đã đổi không tương thích, **rollback binary có thể thất bại**; áp dụng expand/contract migrations hoặc forward-fix được kiểm soát.
7. Ghi incident timeline, affected users, evidence và hành động cải tiến.

**Git revert source code không phải rollback tức thì**: nó cần build/deploy mới và không tự đảo ngược những database writes đã xảy ra.

### 8.4. App Service deployment slots

Nếu plan hỗ trợ, **deployment slots** giúp staging một version trong cùng App Service app, sau đó **swap traffic**:

~~~text
App Service production slot: v1 (receives customer traffic)
App Service staging slot:    v2 (smoke/warm-up)
    ↓
Approved slot swap:
production receives v2 after swap process
    ↓
Monitor; swap back only if safe and compatible
~~~

Lệnh Azure CLI minh họa trên **resource lab đã có slots**, không chạy khi chưa có approval:

~~~bash
az webapp deployment slot swap \
  --resource-group "<approved-app-rg>" \
  --name "<approved-app-name>" \
  --slot staging \
  --target-slot production
~~~

**Slot-specific settings** (ví dụ DB connection, environment variables, identity, VNet integration) phải được đánh giá trước swap. “Swap back” không undo DB migrations/events đã phát. Với app slots, dùng đúng resource/slot scope trong RBAC thay vì cấp quyền toàn subscription.

### 8.5. Smoke test nên kiểm chứng gì?

| Check | Mục tiêu |
|---|---|
| Readiness | Ứng dụng có thể nhận requests theo dependency contract |
| Version/digest | Đúng artifact đã promote |
| Authentication | API không lộ endpoint production vô danh |
| Read-only API | Query business không lỗi, latency trong giới hạn |
| Write test có kiểm soát | Chỉ trên tenant/test data được phép, có cleanup plan |
| Database migrations | Schema version tương thích, không có startup race |
| Telemetry | Application Insights/Monitor nhận logs/traces mới |
| 5xx, p95, CPU | Không có regression/canary alarm |

Không chạy load test ghi dữ liệu thật trong production chỉ để kiểm tra release. Với private App Service, runner cần private route hoặc dùng internal/synthetic monitors theo topology.

## 9. Từ JAR sang container: tại sao cần Azure Container Registry?

Với Azure Container Apps/AKS, artifact triển khai thông thường là **OCI image** lưu trong registry. Azure Container Registry (ACR) giữ các image manifests, layers và tags; deployment chỉ định **image reference**.

### 9.1. Tag và digest

~~~text
Mutable tag (không đủ làm release identity):
  myacr.azurecr.io/orders-api:latest

Commit-based tag (tốt hơn, vẫn có thể bị ghi đè nếu registry policy cho phép):
  myacr.azurecr.io/orders-api:cafebabe0123

Immutable content reference:
  myacr.azurecr.io/orders-api@sha256:<digest>
~~~

**Digest** trỏ nội dung manifest bất biến. Với **multi-architecture images**, digest của image index khác digest từng platform image; chọn digest phù hợp với deploy runtime và registry manifest. Security scan/provenance phải gắn với **digest thực sự được deploy**, không chỉ tag.

### 9.2. Dockerfile cho Spring Boot đã build

Giả sử CI đã tạo `dist/orders-api-1.0.0.jar`:

~~~dockerfile
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app
COPY dist/orders-api-1.0.0.jar /app/orders-api.jar

RUN useradd --system --uid 10001 appuser
USER 10001

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
~~~

Đây là bản mẫu, chưa pin **base image digest** và chưa đặt resource limits/JVM memory flags. Ở production:

- Pin trusted base image bằng digest, cập nhật security fixes định kỳ.
- Scan dependencies trong JAR và image OS packages.
- Không `COPY .env` hoặc cloud credentials vào image.
- Dùng non-root, read-only filesystem nếu ứng dụng hỗ trợ.
- Build đúng `linux/amd64`/`linux/arm64` theo Azure target.
- Inject runtime settings/secrets qua hosting service, không qua Docker build args.

### 9.3. CI identity push khác runtime identity pull

~~~mermaid
flowchart LR
    GH[GitHub build-and-publish job] -->|OIDC| CI[Publisher identity]
    CI -->|ACR push permission| ACR[(Azure Container Registry)]
    ACA[Container App runtime] -->|Managed identity with ACR pull| ACR
    CD[GitHub deploy job] -->|Azure RBAC update app image| ACA
~~~

Nên có **ba ranh giới quyền**: publisher đẩy image, deployer thay config image trong Azure resource, runtime được pull image. Không cấp ACR Admin username/password cho tất cả nơi để “đơn giản hóa”.

### 9.4. Network và access mode của ACR

- Nếu ACR public endpoint bị giới hạn firewall/private networking, runner build cần route hợp lệ.
- GitHub-hosted runner mặc định không ở trong VNet của doanh nghiệp.
- Container App/AKS runtime cần registry network access và pull identity.
- ACR RBAC có thể dùng `AcrPush`/`AcrPull` truyền thống hoặc repository-level role mode mới; **không trộn các tên role mà không kiểm tra registry permission mode**.
- CI không được phụ thuộc admin credentials trong GitHub Secrets nếu có OIDC/Entra path được hỗ trợ.

## 10. Mẫu đầy đủ: GitHub Actions → ACR → Azure Container Apps

Ví dụ dùng **cùng JAR đã qua tests**, build OCI image một lần, push ACR theo commit SHA, lấy **digest output**, rồi deploy staging và production bằng hai identities khác nhau.

### 10.1. Điều kiện cấu hình

~~~text
GitHub environments:
  image-publish:
    OIDC publisher identity; vars ACR_NAME, ACR_LOGIN_SERVER
    AZURE_CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID
  staging:
    separate OIDC deploy identity; vars AZURE_RESOURCE_GROUP,
    AZURE_CONTAINERAPP_NAME, AZURE_CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID
  production:
    separate OIDC deploy identity; same kinds of vars

Azure:
  Existing ACR:       myacr.azurecr.io
  Existing Container Apps: orders-api-staging, orders-api-production
  Runtime registry pull: preconfigured managed identity/permissions
~~~

**Nếu production Container App dùng ACR khác staging**, digest từ registry A không tự tồn tại ở registry B. Cần copy/replicate image **theo content digest** và xác minh identity/provenance trước deploy; mẫu này giả định **cùng trusted registry** cho hai môi trường.

### 10.2. Workflow YAML

File hướng dẫn người học tạo `.github/workflows/container-apps-release.yml` trong repo riêng:

~~~yaml
name: Container Apps release

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - name: Build and verify JAR
        run: mvn --batch-mode --no-transfer-progress clean verify
      - uses: actions/upload-artifact@v4
        with:
          name: orders-api-jar
          path: target/orders-api-1.0.0.jar
          if-no-files-found: error

  publish-image:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: test
    runs-on: ubuntu-latest
    environment: image-publish
    permissions:
      contents: read
      id-token: write
    outputs:
      image_ref: ${{ steps.image-ref.outputs.value }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: orders-api-jar
          path: dist
      - uses: docker/setup-buildx-action@v3

      - name: Azure OIDC login for image publishing
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Authenticate Docker to ACR
        shell: bash
        env:
          REGISTRY_NAME: ${{ vars.ACR_NAME }}
        run: az acr login --name "$REGISTRY_NAME"

      - name: Build and push one release image
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          platforms: linux/amd64
          tags: ${{ vars.ACR_LOGIN_SERVER }}/orders-api:${{ github.sha }}

      - name: Record immutable image reference
        id: image-ref
        shell: bash
        env:
          IMAGE: ${{ vars.ACR_LOGIN_SERVER }}/orders-api@${{ steps.build.outputs.digest }}
        run: |
          test -n "$IMAGE"
          echo "value=$IMAGE" >> "$GITHUB_OUTPUT"

  deploy-staging:
    needs: publish-image
    runs-on: ubuntu-latest
    environment: staging
    permissions:
      contents: read
      id-token: write
    concurrency:
      group: orders-api-containerapp-staging
      cancel-in-progress: false
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy by image digest
        shell: bash
        env:
          RG: ${{ vars.AZURE_RESOURCE_GROUP }}
          APP: ${{ vars.AZURE_CONTAINERAPP_NAME }}
          IMAGE_REF: ${{ needs.publish-image.outputs.image_ref }}
        run: |
          test -n "$IMAGE_REF"
          az containerapp update \
            --resource-group "$RG" \
            --name "$APP" \
            --image "$IMAGE_REF"

      - name: Verify staging revisions
        shell: bash
        env:
          RG: ${{ vars.AZURE_RESOURCE_GROUP }}
          APP: ${{ vars.AZURE_CONTAINERAPP_NAME }}
        run: |
          az containerapp revision list \
            --resource-group "$RG" --name "$APP" -o table

  deploy-production:
    needs: [publish-image, deploy-staging]
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    concurrency:
      group: orders-api-containerapp-production
      cancel-in-progress: false
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Promote exact image digest to production
        shell: bash
        env:
          RG: ${{ vars.AZURE_RESOURCE_GROUP }}
          APP: ${{ vars.AZURE_CONTAINERAPP_NAME }}
          IMAGE_REF: ${{ needs.publish-image.outputs.image_ref }}
        run: |
          test -n "$IMAGE_REF"
          az containerapp update \
            --resource-group "$RG" \
            --name "$APP" \
            --image "$IMAGE_REF"
~~~

### 10.3. Giới hạn và bổ sung bắt buộc cho production

Workflow là **bản khung học tập**, chưa phải production pipeline hoàn chỉnh:

1. `Dockerfile` phải `COPY dist/orders-api-1.0.0.jar` và build context không loại `dist` trong `.dockerignore`.
2. `AZURE_CLIENT_ID`/`TENANT_ID`/`SUBSCRIPTION_ID` khác nhau theo môi trường/identity; environment protection rules hạn chế publish và prod.
3. Publisher có quyền ACR push, deployer có quyền sửa đúng Container App, runtime identity có quyền ACR pull. Cả **role assignments và registry access** phải tồn tại.
4. Container Apps resource đã được cấu hình image registry/identity, networking, runtime env, readiness/liveness; `az containerapp update` không tạo giúp toàn bộ dependencies.
5. Image phải hỗ trợ target architecture `linux/amd64`; nếu target cần ARM64, build multi-platform và test phù hợp.
6. Bổ sung **security/SBOM/attestation gates** trước publish; quét source/dependencies/image và xác minh digest đã quét.
7. Bổ sung **health/smoke/SLO checks** sau staging và production; lệnh `revision list` chỉ xem revisions, chưa chứng minh API khỏe.
8. Bổ sung release artifact manifest, image signature/provenance và rollback plan; image digest output từ `build-push-action` cần được kiểm tra không rỗng.
9. Pin action SHA đầy đủ ở repo thật; các major tags ở đây chỉ giúp người học theo dõi cấu trúc.
10. Với private ACR, runner cần private network; lỗi firewall không giải quyết bằng việc bật admin user cho registry.

### 10.4. Vì sao tránh `az acr build` rồi deploy tag `latest`?

ACR Tasks có thể build image trực tiếp trên Azure và là lựa chọn hợp lệ khi thiết kế đúng. Nhưng với ví dụ này, cần **gắn image đã kiểm thử vào một content digest**. Nếu pipeline build lại hoặc deploy `latest`, release promotion có thể trỏ tới content mới hơn commit đã duyệt. `docker/build-push-action` output digest chỉ rõ artifact thực; alternative như `az acr build` cũng phải ghi/validate digest theo cách được hỗ trợ.

### 10.5. Phân biệt success của Azure ARM và success của Container Apps revision

Sau `az containerapp update`, kiểm tra:

- Revision mới có tên/image digest mong đợi.
- Replica khởi động, pull ACR thành công, readiness healthy.
- Nếu dùng **multiple revision mode**, traffic weights đang ở phiên bản nào?
- App error rate/p95/CPU/memory và business events có trong SLO?
- Có cần migration/backward compatibility khi hai revisions chạy đồng thời?

Không coi `az containerapp update` exit code 0 là proof “production đã nhận đúng traffic và không lỗi”.

## 11. Container Apps revisions, traffic splitting và rollback

**Azure Container Apps** có khái niệm **revision**, bản snapshot của một số thuộc tính cấu hình/application template. Khi đổi image hoặc revision-scope properties, hệ thống có thể tạo revision mới. Cách phân phối traffic khác nhau giữa **single revision mode** và **multiple revision mode**.

### 11.1. Single revision mode

~~~text
Revision v1 is active.
Deploy image digest v2.
Platform prepares new revision.
Traffic transitions according to revision/readiness behavior.
Observe application health and routing.
~~~

Ưu điểm: đơn giản cho ứng dụng không cần song song nhiều versions. Nhưng không mặc định **zero downtime** cho mọi workload: readiness, startup, scaling, database compatibility và ingress đều ảnh hưởng. Nếu revision mới không khỏe, điều tra rollout state và có rollback plan.

### 11.2. Multiple revision mode

~~~mermaid
flowchart LR
    USERS[Client traffic] --> INGRESS[Container Apps ingress]
    INGRESS -->|90%| V1[Revision v1: known good]
    INGRESS -->|10%| V2[Revision v2: canary]
    V1 --> DB[(Shared compatible database)]
    V2 --> DB
    OBS[Monitor errors/latency/business signals] -. metrics .-> V1
    OBS -. metrics .-> V2
~~~

Có thể triển khai v2 và thay **traffic weights** dần dần. Tuy nhiên:

- Cú pháp CLI thay traffic theo revision hoặc label tùy version; chạy `az containerapp ingress traffic set --help` và xem revision names thực.
- Health/smoke test phải hướng đúng revision hoặc label, không chỉ URL production đang trỏ v1.
- **Database migrations phải tương thích đồng thời v1/v2**.
- Nếu v2 gửi events dạng khác, consumers cần versioned schema.
- “Đưa v2 về 0% traffic” không undo những requests/data đã xử lý trước đó.

### 11.3. Canary promotion plan

| Bước | Tỷ lệ v2 minh họa | Cần đo |
|---|---:|---|
| Preflight | 0% public | Revision up, image digest, internal smoke |
| Canary | 5% | HTTP 5xx, p95/p99, business validation |
| Pilot | 25% | Resource capacity, dependency errors, telemetry |
| Ramp-up | 50% | Database contention, queue lag, memory |
| Full | 100% | 24h SLO/incident monitoring theo policy |

Các tỷ lệ/cửa sổ là **ví dụ**. Không dùng ngưỡng cố định cho hệ thanh toán/điều khiển công nghiệp mà chưa có SLO và business owner phê duyệt.

### 11.4. Rollback Container Apps

Nếu revision v2 gây lỗi:

1. Dừng promotion, ghi image digest/revision và impacted traffic.
2. Với multiple mode, điều chỉnh traffic về revision v1 **theo chính sách**, khi v1 vẫn sẵn sàng.
3. Với single mode hoặc revision cũ không sẵn, deploy lại last-known-good digest.
4. Kiểm tra image pull/registry accessibility và runtime env.
5. Theo dõi user traffic/business correctness, không chỉ `revision list`.
6. Đánh giá dữ liệu đã ghi, message schemas, migrations/side effects và reconciliation.
7. Lưu incident evidence và cập nhật release gate.

**GitHub workflow deploy thành công** và **Container App revision active** là những điều kiện cần, chưa đủ để kết luận business rollout tốt.

## 12. AKS: triển khai trực tiếp hay GitOps?

Với AKS, GitHub Actions có thể:

1. Build/test/push image ACR.
2. **Deploy trực tiếp** bằng Helm/kubectl sau khi OIDC Azure login và Kubernetes authentication/RBAC hợp lệ.
3. Hoặc theo **GitOps**: CI cập nhật file desired image digest trong Git, rồi Flux/Argo CD ở cluster reconcile.

### 12.1. So sánh hai mô hình

| Mục tiêu | GitHub Actions deploy Helm trực tiếp | GitOps controller reconcile |
|---|---|---|
| Actor có quyền cluster | GitHub runner/CI principal | Controller bên trong cluster |
| Source of truth | CI command/Helm release history + repo | Git desired state |
| Cập nhật khi cluster private | Runner cần network vào AKS API | GitOps controller pull Git từ cluster |
| Drift correction | Cần kiểm tra/redeploy riêng | Controller có thể reconcile |
| Review | Workflow + Helm chart/values | PR vào GitOps repo/overlay |
| Rollback | Helm rollback/redeploy digest | Git revert desired state + reconcile |
| Rủi ro | Cấp runner cluster permissions quá rộng | Controller/Repo quyền rộng hoặc cấu hình prune sai |

**GitOps không bỏ qua pipeline CI:** CI vẫn phải build/scan/attest image và promote digest. Sự khác biệt là **ai làm deployment action**.

### 12.2. Helm deploy trực tiếp: chuỗi thao tác

Nếu tổ chức chọn direct Helm và **AKS có Microsoft Entra integration/cluster RBAC phù hợp**:

~~~text
GitHub job:
  azure/login@v2 with OIDC
     ↓
  az aks get-credentials for allowed cluster
     ↓
  kubelogin / Entra auth plugin when required
     ↓
  helm upgrade --install app with image digest
     ↓
  kubectl rollout status + service smoke checks
~~~

Các lệnh minh họa **chỉ chạy ở cluster lab được cấp phép**, chart `./charts/orders-api` phải tồn tại và chart hỗ trợ các values tương ứng:

~~~bash
az aks get-credentials \
  --resource-group "<approved-aks-resource-group>" \
  --name "<approved-aks-cluster>" \
  --overwrite-existing

# Chỉ khi cluster/runner auth model yêu cầu kubelogin.
kubelogin convert-kubeconfig -l azurecli

# Ví dụ chart phải hỗ trợ image.repository và image.digest.
helm upgrade --install orders-api ./charts/orders-api \
  --namespace orders --create-namespace \
  --set-string image.repository="<acr>.azurecr.io/orders-api" \
  --set-string image.digest="sha256:<approved-digest>" \
  --wait --timeout 10m

kubectl -n orders rollout status deployment/orders-api --timeout=5m
~~~

**Không dùng `az aks get-credentials --admin` như workaround mặc định.** Cluster permission có **hai tầng**: Azure quyền lấy kubeconfig (ví dụ AKS Cluster User role) và **Kubernetes RBAC/Azure RBAC for Kubernetes authorization** cho namespace/resource actions. API server private cần GitHub runner network route/VPN/private runner hoặc chọn GitOps.

### 12.3. Helm values và digest

Chart nên hỗ trợ:

~~~yaml
image:
  repository: myacr.azurecr.io/orders-api
  digest: sha256:<approved-digest>

replicaCount: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
~~~

**Đây là values file giả định**; Helm/Kubernetes không có magic fields `image.digest` trừ khi chart templates dùng chúng để sinh `image: repo@sha256:...`. Review chart template để tránh tạo invalid reference hoặc silently deploy tag cũ.

### 12.4. GitOps/Flux cho AKS

Một GitOps repo:

~~~text
gitops/
  clusters/
    staging/
      orders-api/
        kustomization.yaml
        deployment.yaml  # image reference @sha256...
    production/
      orders-api/
        kustomization.yaml
        deployment.yaml
~~~

Pipeline sau CI:

1. Ghi digest/SBOM/provenance vào release artifact.
2. Tạo PR cập nhật **staging** image digest trong GitOps repo.
3. GitOps controller chạy ở AKS reconcile staging.
4. Kết hợp GitOps health/reconcile và business smoke metrics.
5. Tạo PR promotion production tới **cùng digest**.
6. Review/approval, merge; controller reconcile production.
7. Rollback qua Git revert manifest/digest đã phê duyệt và xác minh thực tế.

**Không để GitHub Actions tự sửa production branch bằng token có write permission rộng mà bỏ PR protection** nếu mục tiêu là approval gate. Controller cần least-privilege namespace scope, quản lý secret/certificate và policy `prune` cẩn thận.

### 12.5. AKS workloads và ACR image pull

Build identity có quyền push không đồng nghĩa AKS nodes/kubelet/workload có quyền pull. Tùy identity và registry permission mode, phải cấp ACR Pull/Repository Reader phù hợp tới **kubelet identity/managed identity** hoặc workload registry integration được hỗ trợ. Một image có trong ACR mà Pod `ImagePullBackOff` vẫn có thể do mạng private registry/DNS, manifest reference hoặc missing pull permission.

### 12.6. Service traffic, migrations và rollback ở AKS

Deploy mới có thể vượt readiness nhưng gây lỗi downstream. Kết hợp:

- Deployment rolling update maxSurge/maxUnavailable.
- Readiness/liveness/startup probes.
- PodDisruptionBudget, HPA/resource requests/limits.
- Ingress/gateway TLS và smoke test đúng route.
- Deployment/Helm history hoặc GitOps commit digest.
- Database expand/contract migrations và idempotent events.

Helm rollback không tự rollback database schema hoặc Service Bus messages đã gửi. Với ứng dụng quan trọng, dùng canary controller/service mesh/gateway traffic splitting theo kiến trúc, không giả định Kubernetes Deployment cho canary chính xác theo phần trăm.

## 13. Azure Functions và những workload không phải container

GitHub Actions không chỉ dùng cho Spring Boot và container:

| Azure workload | Artifact thường dùng | Cách deploy tham khảo |
|---|---|---|
| **App Service (Java/JAR)** | JAR/ZIP build output | `azure/webapps-deploy` hoặc Azure CLI |
| **Azure Container Apps** | ACR image digest | `az containerapp update`/IaC |
| **AKS** | ACR image digest + Helm/GitOps | Helm/kubectl hoặc Flux |
| **Azure Functions** | Function app package/image | `Azure/functions-action`/supported CLI |
| **Static Web Apps** | Built web assets | Azure Static Web Apps action/workflow |
| **Azure VM/VMSS** | Script/package/image | IaC/extension/approved deployment tooling |

Với Azure Functions, build framework/hosting plan, trigger configuration và package deployment khác App Service Java web app; **không copy nguyên `azure/webapps-deploy` workflow rồi mong runtime Functions tìm function triggers**. Xác minh action version/identity/auth mode, Function app plan, deployment slots và private networking riêng.

### 13.1. Infrastructure deployment khác application deployment

Một pipeline có thể quản hai lớp:

~~~text
Infra (Bicep/Terraform):
  subscription/RG/VNet/ACR/App Service/Container App/AKS
  identities/RBAC/diagnostics

Application:
  JAR/image digest
  runtime configuration, deployment/revisions
  health and business checks
~~~

Không nhất thiết để mỗi code push tự tạo/xóa hạ tầng. Infra apply cần plan/approval và target isolation rõ; app deploy nên dùng **resource đã provision** và quyền hạn chế. Khi dùng Terraform, state backend, locking và drift phải được bảo vệ; GitHub OIDC identity cho Terraform có thể cần khác với app deployer.

## 14. Chuỗi cung ứng phần mềm: từ source đến artifact tin cậy

CI/CD không chỉ là `mvn package` và `az ... update`. Người tấn công có thể thay dependency, Docker base image, GitHub action, build script hoặc release tag mà vẫn tạo workflow “green”.

### 14.1. Threat model cho pipeline

~~~mermaid
flowchart TD
    S[Git source / PR] --> A[GitHub Actions code and dependencies]
    A --> B[Build tooling / package repositories]
    B --> C[Artifact and OCI image]
    C --> D[ACR / artifact store]
    D --> E[Deploy identity and Azure target]
    E --> F[Runtime + data]
    X[Attacker on fork / action / dependency] -. attempts influence .-> A
    X -. supply chain injection .-> B
    X -. artifact substitution .-> D
    DEF[Review, pinning, scanning, provenance, RBAC, signatures] -. protects .-> A
    DEF -. protects .-> C
    DEF -. protects .-> E
~~~

Các điểm kiểm soát bổ sung nhau:

| Giai đoạn | Kiểm soát |
|---|---|
| **Source** | Protected branches, CODEOWNERS, signed commits nếu policy yêu cầu |
| **Workflow** | Review workflow files, allowlist actions, pin full commit SHA |
| **Dependencies** | SCA/dependency review, lock/constraints, license policy |
| **Build** | Ephemeral runner, reproducibility/provenance, no secrets in logs |
| **Artifact** | SHA-256/digest, SBOM, signing/attestations |
| **Registry** | Access controls, immutable references, retention, scan results |
| **Deploy** | OIDC least privilege, environment approvals, target allowlist |
| **Runtime** | Managed identity, policy, scanning, detection, rollback |

### 14.2. Pin actions bằng commit SHA

Trong bài dùng:

~~~yaml
- uses: actions/checkout@v4
- uses: azure/login@v2
- uses: docker/build-push-action@v6
~~~

Đây là **major tags minh họa**. Trong production, thay bằng **full commit SHA đã được review**:

~~~yaml
- uses: actions/checkout@<approved-full-commit-sha>
~~~

**Placeholder trên chưa chạy được**. Pin SHA giúp tránh code bất ngờ thay vì chỉ phụ thuộc mutable tag; vẫn phải theo dõi vulnerabilities và chủ động cập nhật pinned SHA. Với third-party actions, đánh giá publisher, code, permissions, network egress và secrets access. Không pin một action không rõ nguồn rồi nghĩ đã an toàn.

### 14.3. Dependencies, SCA và licenses

Với Java:

- Maven dependencies/BOM được quản lý và review.
- SCA alerts hoặc dependency review trên PR theo repository policy.
- Không tự động update major version trên production nếu tests chưa đủ.
- Ghi SBOM (ví dụ CycloneDX/SPDX theo tooling được phê duyệt).
- Scan dependency CVEs và license restrictions theo threshold rõ.

**SCA không thay runtime vulnerability scanning**: một container có thể có lỗ hổng OS package dù JAR dependencies đều sạch.

### 14.4. SBOM và provenance

Một release có thể gắn:

~~~json
{
  "service": "orders-api",
  "gitCommit": "cafebabe0123",
  "image": "myacr.azurecr.io/orders-api@sha256:<digest>",
  "sbomFormat": "CycloneDX or SPDX",
  "builder": "reviewed GitHub Actions workflow",
  "tests": ["unit", "integration", "security-scan"],
  "approvedEnvironment": "production"
}
~~~

Đây là **release metadata ví dụ**, không phải nội dung mặc định của attestations. Provenance cần liên kết **source revision, builder, artifact digest và signed attestation** theo tooling được hỗ trợ. Chỉ tự ghi JSON vào Git không tạo integrity guarantee nếu actor có quyền sửa nội dung/signature.

### 14.5. Artifact attestations và chữ ký

GitHub/OCI ecosystems cung cấp các tính năng artifact attestations, signing và verification. Trước deploy:

1. Tạo SBOM và scan reports cho artifact.
2. Sinh provenance/attestation từ pipeline builder được tin cậy.
3. Gắn signature vào **image digest**, không chỉ tag.
4. Verify signer/issuer/source repo/ref/commit và artifact digest ở promotion gate.
5. Lưu evidence trong artifact/registry/system có retention phù hợp.

**Không mặc định `id-token: write` và một script `cosign sign` là đủ**: OIDC audience, registry permissions, transparency log, signer identity và verification policy cần được thiết kế. Nếu dùng GitHub artifact attestations, kiểm tra action/API/required GitHub permissions và artifact type theo phiên bản hiện hành.

### 14.6. Không chạy arbitrary scripts từ PR với deployment identity

Một dòng shell như:

~~~bash
curl -fsSL "https://example.invalid/install.sh" | bash
~~~

chỉ là mô hình nguy hiểm, **không nên thực thi**. Script từ Internet có thể bị thay đổi và chạy với quyền của runner, thậm chí đọc OIDC token hoặc GitHub secrets. Pin tools/package versions, verify checksums, dùng runner images đã phê duyệt và không lấy code từ untrusted branches bằng token privileged.

## 15. Hardening GitHub Actions workflow và quyền GitHub token

### 15.1. Đặt `permissions` tường minh

Một workflow CI chỉ cần:

~~~yaml
permissions:
  contents: read
~~~

Một job deploy Azure qua OIDC:

~~~yaml
permissions:
  contents: read
  id-token: write
~~~

Các permissions này cấp cho **GitHub GITHUB_TOKEN/OIDC request**, không đồng nghĩa cấp Azure RBAC. Nếu workflow cần tạo release/tag/pull request, cấp đúng permission ở **job cần thiết** thay vì `contents: write`/`pull-requests: write` toàn workflow.

### 15.2. Tránh injection từ GitHub context vào shell

Nguy hiểm khi nhét trực tiếp string do PR/user kiểm soát vào script shell:

~~~yaml
# KHÔNG ÁP DỤNG: tên PR có thể chứa ký tự làm đổi shell logic.
- run: echo "PR title: ${{ github.event.pull_request.title }}"
~~~

Đặt values vào **environment variables** trước, không interpolate vào shell source:

~~~yaml
- name: Print PR title safely
  shell: bash
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: printf 'PR title: %s\n' "$PR_TITLE"
~~~

Vẫn cần validate/escape khi dùng dữ liệu input để tạo JSON, shell arguments, Terraform vars, image tag hoặc Azure resource name. Environment variables giảm rủi ro expression trở thành shell code, **không thay input validation**.

### 15.3. Dữ liệu/credentials trên runner

- Không chạy `printenv`/`env` hoặc `set -x` khi secrets/token có thể xuất hiện.
- Không in Azure access tokens/ACR credentials/Key Vault secret values.
- Không đưa token vào command line arguments nếu có thể bị ghi vào process list/logs.
- Xóa temporary credentials và session contexts sau job, không truyền sang untrusted jobs.
- Với self-hosted runner, dọn workspace/build cache/credentials sau run, sử dụng ephemeral runners nếu có thể.
- Không dùng artifacts để truyền `.azure/`, kubeconfig privileged hoặc connection strings.

### 15.4. `workflow_run` và artifacts từ workflow không tin cậy

Một privileged workflow có thể được kích hoạt sau khi workflow PR hoàn tất qua `workflow_run`. Điều này **không tự làm artifact/checkout của PR trở nên tin cậy**. Nếu privileged job tải artifact do PR tạo rồi thực thi script/deploy, attacker có thể điều khiển artifact. Dùng commit/ref verification, provenance, artifact signature và policy chỉ cho phép build từ protected branches.

### 15.5. Reusable workflows và quyền kế thừa

`workflow_call` giúp tổ chức chuẩn hóa deployment logic, nhưng phải xem:

- Caller có thể truyền **image URI, subscription ID hoặc script** tùy ý không?
- Called workflow có production permissions rộng không?
- Secrets được inherit/forward thế nào?
- Reusable workflow repo/ref có được pin SHA và protected không?
- Environment approval nằm ở job nào?

Một workflow reusable “deploy-any-resource” với quyền Contributor toàn tenant có thể nguy hiểm hơn 10 workflow riêng được scope đúng. Dùng typed inputs, target allowlist, separate identities và policy restrictions.

## 16. Bảo mật secrets, configuration và danh tính runtime

### 16.1. Phân biệt ba loại dữ liệu

| Loại | Ví dụ | Quản lý phù hợp |
|---|---|---|
| **Non-secret configuration** | Environment name, resource group, client ID | GitHub Environment Variables/IaC |
| **Deployment token** | OIDC JWT/Azure access token ngắn hạn | GitHub OIDC + Entra, không lưu lâu |
| **Runtime secret** | DB password, API token, connection string | Azure Key Vault/managed identity/secret injection |

**Entra client ID/tenant ID/subscription ID là identifiers**, có thể đặt ở `vars` thay vì `secrets`, nhưng quyền sửa values này phải bảo vệ. Thay một client ID thành identity khác có thể gây **target confusion** hoặc deployment sai, dù không lộ password.

### 16.2. Runtime Key Vault references

App Service/Container Apps/AKS có cơ chế khác nhau để ứng dụng truy cập Key Vault hoặc inject secrets. Đối với Spring Boot, dùng **runtime managed identity** và quyền `Key Vault Secrets User`/RBAC scope phù hợp thay vì đưa `spring.datasource.password` vào Dockerfile. Một App Service Key Vault Reference có thể đưa giá trị secret vào app setting nhưng phải xem cơ chế refresh, identity và network path thật; **Key Vault Reference không tạo database principal hoặc mở Private Endpoint**.

### 16.3. GitHub encrypted secrets khi nào vẫn cần?

Có thể cần secret từ hệ thống bên ngoài không hỗ trợ federation. Khi đó:

- Chọn organization/repository/environment secret scope tối thiểu.
- Enable required reviewers với environment production.
- Định kỳ rotate/revoke, audit access và no untrusted PR access.
- Không đưa secret vào cache/artifact/logs.
- Sử dụng masking nhưng không dựa vào masking như DLP tuyệt đối (transformed secret có thể không bị che).
- Di chuyển sang OIDC/short-lived credentials khi provider hỗ trợ.

### 16.4. Tách secret của CI với database migration

CI kiểm thử có thể dùng PostgreSQL Testcontainers local; migration production cần identity/DB grants riêng. Đừng cung cấp production database password cho **PR test job**, và đừng cho database runtime role quyền `DROP TABLE` chỉ vì pipeline có Flyway.

### 16.5. Secrets scanning và incident

Nếu phát hiện token/client secret đã bị commit:

1. **Thu hồi/rotate** credential ở nguồn cấp trước.
2. Điều tra Git history, caches, artifacts và log exposure.
3. Xem Azure Activity Log/Entra sign-ins/GitHub audit để xác định lạm dụng.
4. Gỡ secret khỏi source bằng quy trình được phê duyệt, tránh force-push mù quáng làm mất evidence.
5. Chuyển sang federation hoặc secret manager thích hợp.
6. Bổ sung pre-commit/CI secret scanning và repo protections.

Chỉ xóa dòng khỏi commit mới **không làm secret cũ hết hiệu lực**.

## 17. GitHub-hosted, self-hosted và private networking Azure

### 17.1. Tại sao runner không thấy Private Endpoint?

~~~mermaid
flowchart LR
    GH[GitHub-hosted runner public network] -. no default private route .-> PE[Azure Private Endpoint]
    SH[Approved self-hosted/managed runner in VNet] --> VNET[VNet DNS/routing]
    VNET --> PE
    PE --> DB[(Azure SQL/ACR/private AKS API)]
    GH -->|Azure ARM public management endpoint if policy allows| ARM[Azure Resource Manager]
    ARM --> APP[Private workload resources]
~~~

**Management-plane deploy và data-plane health khác nhau:** GitHub-hosted runner có thể gọi Azure Resource Manager để đổi Container App image dù không có private connection vào app endpoint. Nhưng nó có thể **không chạy được integration tests vào private Azure SQL**, không gọi internal HTTPS smoke endpoint và không push ACR private-only khi thiếu private connectivity.

### 17.2. Chọn runner theo job

| Job | Runner thường phù hợp | Điều kiện |
|---|---|---|
| PR unit tests | GitHub-hosted | Không có secrets/production network |
| Maven build + SCA | GitHub-hosted/ephemeral | Package registry access, cache security |
| Push public ACR endpoint theo policy | GitHub-hosted | OIDC + RBAC + allowed network |
| Push private ACR | Approved VNet-connected runner | Private DNS/route/registry access |
| Azure SQL integration tests private-only | VNet runner hoặc test service trong Azure | DB role/identity riêng |
| AKS API server private | VNet-connected runner hoặc GitOps | Cluster RBAC và network |
| Public App Service smoke | GitHub-hosted | HTTPS endpoint có kiểm soát |
| Internal service smoke | Private runner/synthetic monitor | DNS/TLS/trust và least privilege |

### 17.3. Self-hosted runner threat model

Self-hosted runner có thể bị mã độc từ một PR làm bẩn workspace hoặc lấy credentials của job tiếp theo nếu dùng chung host. Mitigation:

- Dùng **ephemeral runner per job** khi có thể.
- Tách runner groups/labels cho untrusted CI và privileged deploy.
- Không cho fork PR kích hoạt privileged runner tự do.
- Harden OS, Docker socket, filesystem, outbound network, patch cadence.
- Cho runner identity/Azure access theo job/environment, không để host có perpetual Owner secret.
- Quản lý runner đăng ký, revocation, inventory và log retention.
- Giới hạn outbound destinations/monitor suspicious actions, nhưng không phá GitHub/Azure OIDC endpoints cần thiết.

**Kubernetes Pod chạy GitHub runner không mặc nhiên an toàn** nếu mount host Docker socket hoặc được cấp privileged service account; xem supply-chain và cluster isolation.

### 17.4. Private DNS và identity

Network path thành công không thay authentication: ACR pull/push vẫn cần identity role, Azure SQL vẫn cần database grants, AKS Kubernetes RBAC vẫn cần quyền. Một workflow chạy được `nslookup`/`nc -vz` không chứng minh TLS hostname validation hoặc credential đúng.

### 17.5. Runner cost

GitHub-hosted minutes/concurrency/storage, self-hosted VM/AKS compute, egress, Docker cache, maintenance/patching và private network có chi phí. Chọn runner theo **độ tin cậy, khả năng bảo mật và private connectivity**; đừng chuyển mọi unit tests sang self-hosted trong production VNet chỉ vì một database integration job cần private route.

## 18. Release gates và chiến lược triển khai an toàn

### 18.1. Một gate phải có điều kiện kiểm chứng được

| Gate | Tiêu chí pass | Thất bại xử lý |
|---|---|---|
| **Code review** | Required reviewers/branch protection, CODEOWNERS | Không merge |
| **CI** | Unit/integration tests xanh, artifacts hợp lệ | Không publish/deploy |
| **Security** | CVEs/secrets/license policy đạt | Chặn hoặc exception có owner/time bound |
| **Artifact provenance** | Digest/signature/source được verify | Không promote |
| **Staging** | Deploy revision/artifact đúng, smoke/metrics đạt | Chặn production |
| **Production approval** | Environment reviewer/branch rule được áp | Chờ hoặc từ chối release |
| **Canary** | Error rate/p95/business SLO trong ngưỡng | Rollback/stop traffic |
| **Post-production** | Health, customer metrics, audit events ổn | Incident response |

Một workflow hiển thị “success” không chứng minh release được phê duyệt nếu environment protection chưa cấu hình. Ngược lại, một reviewer bấm “Approve” không thay security scans/health checks.

### 18.2. Thay đổi có rủi ro cao

- Database schema phá vỡ compatibility.
- Message schemas không có version.
- Auth/Key Vault/VNet changes ảnh hưởng toàn fleet.
- Container Apps traffic weights/AKS ingress changes.
- Upgrade runtime/JDK/base OS image.
- Thay CI OIDC federated credential/role assignments.
- Dùng Terraform/Bicep có kế hoạch xóa resource.

Với những thay đổi này, yêu cầu **change review riêng, testing staging, backup/restore hoặc rollback/forward-fix plan**, không chỉ dựa vào auto-deploy vì tests xanh.

### 18.3. Migration phải đi cùng application release

Một quy trình phù hợp cho Spring Boot + Azure SQL/PostgreSQL:

~~~text
Schema expand migration (approved, backward-compatible)
    ↓
New app v2 deployed to staging, tested on migrated schema
    ↓
Production migration with separate DDL principal
    ↓
Canary v2 while old v1 still works
    ↓
Full v2 rollout
    ↓
Contract migration removing old columns after safe window
~~~

**Không đặt Flyway DDL auto-execute trên mọi App Service/Container Apps replica với database owner credential** nếu migration có thể chặn/đập vào nhau. Nếu dùng startup migrations, phải có quyền và locking/retry policy được kiểm chứng; với production nên ưu tiên migration job riêng.

### 18.4. Release freeze và break-glass

Khi incident đang diễn ra, có thể cần rollback nhanh. Break-glass phải có:

- Principal/role được định nghĩa trước với audit/approval.
- Kịch bản deploy lại **known-good digest**.
- Giới hạn người sử dụng và thời gian.
- Tự động tạo incident record và postmortem review.

Không thiết kế break-glass bằng cách lưu một Azure Owner client secret vô hạn trong GitHub repository secrets.

## 19. Kiểm thử CI/CD: từ unit đến end-to-end trên Azure

### 19.1. Test pyramid

| Lớp | Mục tiêu | Thực thi |
|---|---|---|
| **Lint/config** | Workflow/YAML/Bicep/chart syntax và policy | PR workflow, không cần Azure write |
| **Unit** | Logic Java/Node/Python, no external dependencies | PR runner |
| **Integration local** | JDBC/Testcontainers, API contract | PR runner có Docker |
| **Artifact/image** | Build, scan, SBOM, signature/digest | Protected branch |
| **Staging smoke** | TLS/auth, HTTP 2xx, dependencies, API version | Deploy staging + approved network |
| **Staging load/resilience** | p95, retry/backoff, scale/failover | Controlled Azure staging |
| **Production canary** | Real traffic error/latency/business SLO | Limited scope and approval |
| **Post-deploy audit** | Release hash, logs/monitoring/Activity Log | Production observability |

### 19.2. Test GitHub Actions configuration

Tại PR:

1. Validate YAML schema/indentation bằng tooling hỗ trợ GitHub workflow semantics.
2. Kiểm tra `permissions`, events, environment/branch restrictions.
3. Tìm sử dụng actions không được allowlist hoặc chỉ pin mutable tags.
4. Kiểm tra untrusted GitHub expressions trong `run`.
5. Lint Dockerfile/IaC/Helm schema, không hardcode secrets.
6. Kiểm tra workflow chỉ xuất Azure token trong job cần deploy.
7. Test release jobs với environment lab/sandbox trước khi cấp production RBAC.

Không thể mô phỏng hoàn toàn GitHub OIDC ở local bằng cách chạy shell script trực tiếp; issuer/claims/audience gắn với GitHub job thực. Cần một **smoke job có quyền staging tối thiểu** để xác minh federation.

### 19.3. Test REST sau deploy

Với Spring Boot đã cấu hình Actuator readiness:

~~~bash
APP_HOST="<approved-staging-hostname>"

curl --fail --show-error --silent \
  "https://$APP_HOST/actuator/health/readiness"

# Nếu app có endpoint đọc dữ liệu tổng hợp không nhạy cảm:
curl --fail --show-error --silent \
  "https://$APP_HOST/api/version"
~~~

Nếu endpoint yêu cầu authentication, dùng test identity/token ngắn hạn **được phê duyệt**, không disable auth để chạy curl. Không log raw response khi có thể chứa PII.

### 19.4. Test HTTP 200 chưa đủ

Một container có thể trả 200 nhưng kết nối DB bị lỗi ở 5% requests, queue consumer ngừng hoặc circuit breaker đang trả cached data cũ. Cần kiểm tra:

- Image/JAR artifact ID và commit SHA.
- p95/p99 HTTP latency và 5xx rate.
- Database connectivity/transaction correctness.
- Service Bus/Event Hubs consumer lag nếu có.
- Application Insights/logs/traces đủ.
- Số resources/revisions/replicas và readiness thực.
- Business KPI: đơn hàng tạo thành công, không double-charge.

### 19.5. Test rollback

Ở staging:

1. Release v1 known-good.
2. Deploy v2 có lỗi giả lập vô hại.
3. Trigger deployment gate thất bại hoặc canary stop.
4. Deploy lại digest v1 (hoặc traffic switch về revision v1).
5. Verify SLO và state dữ liệu sau rollback.
6. Ghi thời gian phục hồi, giới hạn RTO/RPO.

Đừng giả lập lỗi bằng cách xóa production SQL table hoặc revoke critical Key Vault role trong giờ vận hành.

## 20. Quan sát release bằng Azure Monitor và GitHub Actions

Một deployment cần được nhìn ở **hai mặt**:

1. **Delivery plane:** GitHub job đã chạy step nào, dùng artifact/digest nào, Azure ARM đã chấp nhận lệnh gì.
2. **Runtime/business plane:** workload có khởi động, nhận traffic, xử lý dữ liệu và giữ SLO/SLI không.

~~~mermaid
flowchart LR
    GH[GitHub Actions run] --> LOG[Workflow logs and deployment evidence]
    GH --> ARM[Azure resource update]
    ARM --> ACT[Azure Activity Log]
    ARM --> APP[App Service / Container App / AKS]
    APP --> APM[Application Insights/OpenTelemetry]
    APP --> MET[Azure Monitor metrics and resource logs]
    ACT --> DASH[Release dashboard/runbook]
    APM --> DASH
    MET --> DASH
    LOG --> DASH
~~~

### 20.1. Phải ghi lại những gì cho mỗi release?

~~~json
{
  "service": "orders-api",
  "environment": "production",
  "githubRepository": "acme/orders-api",
  "gitCommit": "cafebabe0123",
  "githubRunId": "123456789",
  "artifact": "myacr.azurecr.io/orders-api@sha256:<digest>",
  "deployedResource": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.App/containerApps/orders-api-production",
  "approvedBy": "reviewed GitHub environment gate",
  "deployedAtUtc": "2026-11-20T09:30:00Z"
}
~~~

Đây là **release evidence schema minh họa**. Không giả định GitHub/Container Apps tự phát record JSON này; pipeline/release system phải tạo bằng chứng phù hợp, và `approvedBy` nên lấy từ audit data thật thay vì tự ghi chuỗi “reviewed” rồi coi là chứng minh approval.

### 20.2. SLO release health

| SLI | Ví dụ threshold của lab | Điều cần đo |
|---|---|---|
| HTTP 5xx | Không tăng đáng kể so baseline | Số requests/denominator và cửa sổ |
| p95/p99 latency | Dưới ngưỡng business | Rolling windows, sample size đủ |
| Startup/readiness | Healthy trước nhận traffic | Probe status/revision readiness |
| Dependency failures | Không tăng DB/Key Vault/Service Bus errors | Traces/errors |
| Queue consumer lag | Không vượt budget | Broker consumer metrics |
| Resource pressure | CPU/RAM/connection pool trong headroom | App và DB metrics |
| Business KPI | Không tăng duplicate orders/failed payments | Business telemetry |
| Rollback time | Trong RTO release | Incident/automation timestamps |

Những thresholds **phải được định nghĩa theo từng workload**, không coi một HTTP 200 đủ cho hệ thống đơn hàng.

### 20.3. Azure Activity Log và diagnostic settings

Azure Activity Log có thể ghi các **management-plane changes** như sửa cấu hình Container App/App Service/RBAC. Resource logs và application traces phải được cấu hình riêng qua Diagnostic settings/Application Insights/DCR như phù hợp.

Ví dụ cần:

~~~text
GitHub deployment run ID
     ↕ correlate by time/resource/actor
Azure Activity Log resource operation
     ↕ correlate by deployment/revision
Application Insights health and exception traces
     ↕ correlate by business eventId / traceId
Customer-facing SLO and transaction outcome
~~~

**Một Azure Activity Log event không chứng minh mọi code path của Spring Boot đã chạy thành công.** Cần end-to-end checks.

### 20.4. KQL kiểm tra thay đổi nguồn lực sau deploy

Nếu workspace đã được cấu hình nhận **subscription Activity Log** vào `AzureActivity`:

~~~kusto
AzureActivity
| where TimeGenerated > ago(24h)
| where ResourceGroup =~ "rg-orders-production"
| summarize Changes=count()
    by OperationNameValue, ActivityStatusValue
| order by Changes desc
~~~

Resource group/bảng/columns là **ví dụ**, cần kiểm tra actual schema; nếu Activity Log chưa được export vào workspace, query có thể không có bảng. KQL này đếm control-plane operations, **không đo trực tiếp số lần deploy thật**; một deployment có thể phát nhiều operations.

### 20.5. KQL application error rate

Với workspace-based Application Insights dùng bảng `AppRequests` (khi schema đó được triển khai):

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    Requests=count(),
    Failed=countif(Success == false)
  by bin(TimeGenerated, 5m)
| extend ErrorRatePercent =
    iff(Requests == 0, real(null), 100.0 * Failed / Requests)
| order by TimeGenerated asc
~~~

**Xác minh tên bảng/columns ở workspace thật**; Application Insights Classic/schema cũ và một số data collection routes có bảng khác như `requests`. Một khoảng có 0 requests không nên diễn giải thành “0% lỗi và service khỏe”. Kết hợp synthetic monitors/heartbeat và canary traffic.

### 20.6. GitHub Actions logs phải an toàn

Workflow cần lưu log đủ để điều tra failed build/deploy, nhưng:

- Không in bearer tokens, client secret, SAS/connection strings.
- Không dump environment variables/configurations chứa credentials.
- Giới hạn retention phù hợp compliance và cost.
- Giữ artifact digest, commit, target resource ID và success/failure reason.
- Dùng audit logs của GitHub Environments/approvals khi cần kiểm tra ai phê duyệt.
- Với container image, lưu original build provenance và digest; không dựa vào `latest`.

### 20.7. Cảnh báo “pipeline xanh nhưng production đỏ”

Một job deployment thành công có thể vẫn làm p95 latency tăng 3 lần hoặc nổ lỗi DB. Nếu gate post-deploy không có, production bị ảnh hưởng nhưng GitHub UI xanh. Thiết kế action:

~~~text
Deployed release + 5-minute monitoring window
  → health/SLO within approved threshold?
       ├─ Yes: mark release healthy and continue observation
       └─ No: pause further promotion, notify on-call,
              rollback/traffic shift via approved runbook
~~~

Không tự động rollback mọi lỗi transient khi traffic thấp, vì có thể gây **flapping** giữa revisions. Chọn sample window/hysteresis và có owner.

## 21. Troubleshooting GitHub Actions và Azure deployment

### 21.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| Workflow không chạy khi push | YAML syntax, branch/path filter, workflow disabled | `on` event/ref, GitHub Actions settings |
| PR CI chạy nhưng không deploy | Điều kiện cố ý skip non-main/untrusted PR | `if`/`needs`, environment policy |
| OIDC token request bị từ chối | Thiếu `id-token: write` | Job permissions |
| Azure login trả federated credential mismatch | Subject/issuer/audience khác | Entra credential và GitHub env/ref |
| Azure login ok nhưng deploy 403 | Principal thiếu Azure RBAC ở target | Target ARM ID, role scope |
| Staging identity deploy production | Sai GitHub vars/identity mapping | Environment vars và Entra RBAC isolation |
| `upload-artifact` báo không tìm file | Maven output path/version khác | `target` manifest, packaging, JAR name |
| Download artifact rỗng | Sai name/job/run context/retention | Artifact metadata và needs |
| `webapps-deploy` success nhưng app 500 | Runtime/migration/config/port issue | App Service logs, readiness, App Insights |
| ACR Docker login denied | Principal thiếu push role hoặc registry auth mode | ACR RBAC/ABAC, subscription/network |
| Docker build failed `COPY dist...` | Artifacts chưa download hoặc `.dockerignore` chặn | Build context paths |
| Image build cho sai CPU arch | Target platform không phù hợp | Image manifest và workload architecture |
| Container App `ImagePullBackOff`/revisions unhealthy | Pull identity, ACR firewall, image digest | ACR permissions, runtime logs |
| Container App update ok nhưng traffic vẫn v1 | Multiple revision mode/traffic weights | Revision traffic config |
| Private AKS API timeout | Runner không ở VNet/DNS route sai | Runner placement/private DNS/NSG |
| AKS kubectl forbidden | Kubernetes RBAC/Entra mapping thiếu | Namespace permissions, không dùng `--admin` |
| Production approval không xuất hiện | Environment rules không bật/unsupported | Repository Settings → Environments |
| Entra MI token hết hạn trong job lâu | Token lifecycle/auth re-login | Auth step before deploy/reconnect |
| Workflow chạy trên fork với credentials | Events/permissions/`pull_request_target` nguy hiểm | Trust boundaries and protected env |
| SLO xấu sau deploy | Application regression hoặc infrastructure issue | Runtime metrics, release artifact/version |
| GitHub deploy không vào private ACR | Hosted runner không có network path | Private runner/VNet route |
| Release tag trỏ artifact khác staging | Rebuild/push mutable tag | Digest/provenance/hash comparison |

### 21.2. Runbook theo thứ tự

**1. Đúng workflow/ref?** Xem repo, `github.ref`, event type, branch protection và effective workflow YAML.

**2. Đúng job?** Có bị `if` skip không, `needs` pass chưa, environment đã approved chưa?

**3. Runner có an toàn/đủ network?** GitHub-hosted hay self-hosted, đúng architecture, registry/private endpoint access?

**4. CI có thực sự test?** Maven/test reports/scan results, artifact file path và SHA?

**5. OIDC có khớp không?** Job `id-token: write`, federated credential issuer/audience/subject, environment claim?

**6. Azure RBAC đúng target?** Principal ID, subscription, resource group/resource ID, ACR publisher/deployer/runtime roles?

**7. Artifact có đúng không?** Download JAR artifact từ run đã kiểm tra, image digest trùng provenance?

**8. Azure có áp thay đổi không?** App Service version, Container Apps revision, AKS deployment/Flux sync?

**9. Traffic và runtime khỏe không?** Readiness, 5xx/p95, dependencies, database migrations, image pull?

**10. Cần rollback hay fix forward?** Dừng promotion, giữ evidence, lựa chọn known-good artifact/digest, xác nhận business behavior.

### 21.3. Tình huống: Azure login báo “no matching federated identity”

Giả sử Entra federated credential tạo với:

~~~text
repo:acme/orders-api:ref:refs/heads/main
~~~

Nhưng job có:

~~~yaml
environment: staging
~~~

Default GitHub OIDC subject cho environment job có thể thành:

~~~text
repo:acme/orders-api:environment:staging
~~~

Khi subject không khớp, Entra từ chối token exchange. Sửa bằng **federated credential khớp protected environment** và enforce deployment branch rules. Không cấp wildcard subject rộng cho mọi repo/branch chỉ để pass.

### 21.4. Tình huống: Azure login PASS, Container Apps update 403

OIDC federation đã cấp Azure token hợp lệ, nhưng token principal không có quyền `Microsoft.App/containerApps/write` (hoặc action tương ứng) tại target. Kiểm tra principal object ID và Azure RBAC scope đúng, hạn chế nhất. **Không tạo thêm GitHub secret với subscription Owner**.

### 21.5. Tình huống: ACR push ok, production không pull image

CI publisher có push permission; runtime Container App/AKS có thể thiếu `AcrPull` hoặc repository reader, ACR firewall/private endpoint không thể truy cập từ runtime, hoặc image digest/tag sai. Đánh giá **runtime identity và network**, không chỉ build job logs.

### 21.6. Tình huống: Helm release `deployed` nhưng site lỗi

Helm status có thể báo applied manifests, trong khi readiness checks/Ingress/database queries chưa đúng. Kiểm tra `kubectl rollout status`, Pod events, ACR pull, probes, service selector, ingress TLS, app traces và business smoke. **Không cho CI cluster-admin để điều tra một deployment lỗi**.

### 21.7. Tình huống: artifact ghi đè

Nếu pipeline deploy image tag `latest`, một job khác có thể đẩy content khác lên cùng tag giữa staging và production. Fix: capture digest từ image publish job, freeze release metadata, deploy by digest và verify attestation/signature. Cần audit/policy chặn mutable tag promotion.

### 21.8. Tình huống: production approval bị bỏ qua

Workflow có `environment: production` nhưng GitHub Environment **không bật required reviewers**, hoặc reviewer branch policies không áp đúng; job chạy tự động. Fix ở GitHub repository/org settings, not just YAML. Test bằng staging/protected sandbox và kiểm tra workflow audit approvals trước khi cho pipeline production hoạt động.

### 21.9. Tình huống: network private chặn smoke check

Azure ARM deploy thành công từ GitHub-hosted runner, nhưng `curl https://internal-app...` timeout. Không sửa bằng public exposure trong production. Sử dụng VNet-connected self-hosted/managed runner, internal synthetic test hoặc thực thi smoke ở môi trường Azure có approved network path; verify DNS/TLS/identity.

## 22. FinOps: chi phí CI/CD và workload Azure

### 22.1. Các nhóm chi phí

| Thành phần | Nguồn chi phí |
|---|---|
| GitHub-hosted runners | Job minutes, runner size/concurrency theo plan |
| GitHub artifacts/cache | Storage/retention/billing theo plan |
| Self-hosted runners | VM/AKS/Container compute, disk, patching, network |
| Maven/package dependencies | Artifact repository, bandwidth/cache |
| ACR | Registry SKU, storage, transfer, security scans |
| App Service | Plan instances, deployment slots, networking |
| Container Apps | vCPU/RAM, requests, revisions/replicas, log costs |
| AKS | Nodes, networking, storage, monitoring |
| Azure Monitor | App Insights/Log Analytics ingestion/retention/alerts |
| Databases and messaging | Compute/storage/connections/transactions |
| Private connectivity | NAT/Firewall/VPN/Private Endpoints/DNS as billed |
| Security tooling | Scans/signing/attestation/secrets management |

**Giá hiện hành phụ thuộc region, plan, date, reserved pricing và lượng sử dụng**. Không chốt chi phí USD/tổng run khi chưa xem GitHub billing và Azure Cost Management.

### 22.2. Ước lượng runner minutes

Giả sử:

~~~text
40 PRs per day
CI checks average 6 minutes
22 working days per month
Each PR runs 1 comparable job
~~~

Thời gian runner logic:

\[
40 \times 6 \times 22 = 5{,}280\ \text{runner-minutes/month}.
\]

Nếu workflow có **4 matrix jobs chạy song song** mỗi job 6 phút, tổng billable runner minutes có thể gần **4 × 5.280 = 21.120** trong giả định tương tự, không phải chỉ 5.280 dù wall-clock của một PR không tăng 4 lần. Billing multiplier phụ thuộc GitHub runner type/plan; phép tính chỉ để hoạch định.

### 22.3. Giảm chi phí có kiểm soát

- Cấu hình `paths`/concurrency để tránh chạy lại CI không cần thiết, nhưng không dùng path filtering bỏ qua security checks bắt buộc.
- Cache Maven/dependencies an toàn, không cache privileged tokens.
- Tách unit jobs nhanh và integration tests tốn tài nguyên theo gates hợp lý.
- Dùng ephemeral runners tự động tắt khi idle.
- Rút ngắn artifact retention khi không thuộc release evidence/compliance cần giữ.
- Xóa image/layers cũ sau khi **last-known-good rollback window** hết và có approval.
- Sizing Container Apps/AKS/App Service theo load, không chạy production-sized infra cho PR ephemeral environments vô thời hạn.
- Theo dõi Log Analytics/App Insights debug volume, không log tất cả HTTP bodies chứa PII.
- Review database connection pool × replicas khi scale release workloads.

### 22.4. PR preview environments

Preview environments hữu ích cho review UX, nhưng có chi phí và rủi ro:

~~~text
PR opened → ephemeral test app with synthetic data
PR updated → redeploy preview
PR closed/merged → approved cleanup
Budget/quota limits → prevent abandoned environments
~~~

Không cấp preview PR environment quyền truy cập production database, Key Vault hoặc ACR publish identity. Nếu preview infrastructure được tạo tự động, phải gắn PR/owner tags, TTL/cleanup reconciliation và guardrails chống xóa nhầm resources shared.

### 22.5. Cost guardrails

Budget alerts ở Azure/GitHub không luôn là hard stop. Cần owner hành động khi vượt mức, tránh giải pháp “tự xóa production resource” vì bill tăng. Đánh giá **chi phí trên mỗi release đáng tin cậy**: tăng test/security cost có thể đáng giá nếu giảm incidents/data loss.

## 23. Case study: đơn hàng Spring Boot từ commit đến Azure Container Apps

### 23.1. Bối cảnh

Một công ty có dịch vụ **`orders-api`** Java 21/Spring Boot, dùng Azure SQL Database và Service Bus. Họ deploy container vào Azure Container Apps, lưu image trong ACR và theo dõi telemetry qua Application Insights/Log Analytics. Đội bảo mật yêu cầu **không lưu Azure client secret trong GitHub**, production release phải được phê duyệt và mọi image có thể truy vết từ commit.

Yêu cầu kỹ thuật:

~~~text
Repository:             acme/orders-api
Protected branch:       main
CI:                     Maven unit + integration tests
Artifact:               orders-api JAR, Docker image digest
Registry:               private ACR with approved runner network path
Staging:                Container App + staging SQL/Service Bus identities
Production:             Container App + production identities
Auth GitHub → Azure:    OIDC federated credentials, separate identities
Release policy:         staging smoke + required prod approval + canary
Monitoring:             Azure Monitor, tracing, rollout dashboard
Failure recovery:       restore last-known-good image digest
~~~

### 23.2. Luồng triển khai

~~~mermaid
flowchart TB
    PR[PR with source and tests] --> REVIEW[Protected branch, CODEOWNERS, policy]
    REVIEW --> CI[Maven verify + SCA]
    CI --> ART[Upload JAR with commit]
    ART --> PUB[Build image + scan + SBOM/provenance]
    PUB --> ACR[Push ACR, record sha256 digest]
    ACR --> STAGING[Staging Container App revision]
    STAGING --> VERIFY[Smoke + DB/Service Bus tests + SLO]
    VERIFY --> GATE[Production Environment approval]
    GATE --> PROD[Production Container App canary]
    PROD --> FULL[Promote traffic after health gates]
    PROD -. Regression .-> ROLLBACK[Traffic to known-good revision]
~~~

### 23.3. IAM thiết kế

| Identity | Scope | Quyền |
|---|---|---|
| `gh-orders-image-publisher` | ACR registry/repo | Push image, không sửa production app |
| `gh-orders-staging-deployer` | Staging Container App | Deploy/read staging revisions |
| `gh-orders-production-deployer` | Production Container App | Deploy/read production revisions sau approval |
| `orders-staging-runtime-mi` | Staging ACR/Key Vault/SQL/Service Bus | Pull image, runtime data access |
| `orders-production-runtime-mi` | Production dependencies | Tương ứng production, không dùng staging MI |
| `orders-migration-principal` | Database schema | DDL migration theo approved run |

**Không tái sử dụng publisher identity như runtime database principal.** Khi CI bị compromise, attacker chỉ nên có quyền giới hạn để phát hành image hoặc thay tài nguyên được giao, không tự đọc toàn bộ dữ liệu khách hàng.

### 23.4. Chi tiết release v1

1. Developer tạo PR, GitHub chạy CI với `contents: read`, **không** có `id-token: write`.
2. CODEOWNERS/review và security policy pass, PR merge `main`.
3. CI build `orders-api-1.0.0.jar` và lưu artifact cùng commit SHA.
4. Publisher job dùng Environment `image-publish`, OIDC để login Azure, push image ACR và lấy digest.
5. Staging job nhận **image digest từ job publisher**, không tự build lại.
6. Check staging readiness, TLS, database identity, Service Bus test message trong môi trường riêng.
7. GitHub production Environment required reviewers xác nhận release.
8. Deployer production update Container App image digest.
9. Nếu multiple revision mode, chuyển một phần traffic rồi theo dõi HTTP/DB/business SLO.
10. Ghi release evidence: commit, run ID, image digest, revisions, approver audit, timestamps.

### 23.5. Sự cố: OIDC staging pass nhưng production thất bại

Triệu chứng:

~~~text
staging:
  azure/login succeeds
  Container App update succeeds

production:
  azure/login fails token exchange
  no production changes applied
~~~

Nguyên nhân: Entra production credential có subject `repo:acme/orders-api:ref:refs/heads/main` nhưng job `environment: production` phát subject `repo:acme/orders-api:environment:production`. **Không mở rộng wildcard subject** để sửa. IAM tạo đúng credential theo protected environment và kiểm tra GitHub restrictions, sau đó chạy lại approved job.

### 23.6. Sự cố: image v2 được push nhưng production vẫn ở v1

Có thể:

- `deploy-production` bị skip do `if`/`needs` hoặc approval chưa được cấp.
- Job trỏ nhầm Container App do environment variable bị đổi.
- Image digest v2 chưa được pull vì runtime identity thiếu ACR permissions.
- Revision v2 đã chạy nhưng **traffic weight** vẫn ở v1.
- Deployment job cập nhật wrong resource group/subscription.

Điều tra từ GitHub run → Azure identity → Azure resource/revision → traffic router → app telemetry. Không đổi tag `latest` để “buộc” production cập nhật vì sẽ mất release identity.

### 23.7. Sự cố: app v2 đúng digest nhưng tạo đơn hàng trùng

Staging smoke GET/health pass, nhưng production canary cho thấy duplicate orders. Nguyên nhân có thể là retry sau timeout khi Service Bus/SQL transaction đã commit, không phải lỗi registry. Hành động:

1. Tạm dừng promotion, chuyển traffic về v1 theo runbook.
2. Giữ version/digest và traces để điều tra.
3. Bảo vệ database bằng unique idempotency key, outbox/consumer dedup nếu use case yêu cầu.
4. Không tự delete duplicate rows mà chưa có owner/business reconciliation.
5. Sửa logic, test concurrent retries, tạo release v3 với digest mới.

**Rollback binary không đảo ngược tác dụng lên dữ liệu** của các requests v2 đã xử lý.

### 23.8. Bài học từ case study

**An toàn release là chuỗi điều kiện liên tục**, không phải một nút Deploy:

~~~text
Protected source
→ trusted build
→ scanned/attested artifact
→ Azure OIDC least privilege
→ staging/runtime checks
→ approved production promotion
→ SLO-backed canary
→ auditable recovery
~~~

## 24. Lab end-to-end: pipeline GitHub Actions lên Azure

Lab có thể thực hành theo hai mức:

- **Lab A — không có Azure resources:** đọc workflow, tạo test Maven/JAR/Dockerfile trong repo riêng, phân tích OIDC claims và RBAC, không chạy deploy.
- **Lab B — Azure lab được cấp phép:** dùng App Service hoặc Container Apps staging thật, OIDC identity riêng, GitHub repo được review và budget/quota được phê duyệt.

### 24.1. Preflight checklist

| Điều kiện | Bằng chứng |
|---|---|
| Repo/branch có quyền | URL repo, branch protection, CODEOWNERS |
| Workflow files được review | `.github/workflows/*.yml` PR reviews |
| Runner phù hợp | GitHub-hosted hoặc VNet runner theo target |
| Maven/JDK | JDK 21 và reproducible Maven verify |
| Artifact | JAR path hoặc Dockerfile/ACR repo |
| GitHub Environments | Staging/prod đúng protection rules |
| OIDC | Entra federated credentials issuer/audience/subjects đúng |
| Azure RBAC | Deploy identity chỉ có target scope |
| Workload | App Service hoặc Container App tồn tại, runtime healthy |
| Monitoring | Health endpoint/metrics/traces, release runbook |
| Budget | App/registry/runner costs được quản lý |

### 24.2. Lab A — PR CI không có quyền Azure

1. Tạo một branch feature và PR với thay đổi nhỏ trong ứng dụng demo.
2. Viết workflow `pull_request` chỉ có `contents: read`.
3. Dùng `actions/setup-java` Java 21 và `mvn verify`.
4. Xác nhận test failure sẽ chặn artifact release.
5. Lưu JAR bằng `upload-artifact` và đọc output metadata.
6. Kiểm tra YAML không có `AZURE_CLIENT_SECRET` hay Azure login trên PR job.
7. Mô tả vì sao PR từ fork không được dùng protected production runner.
8. Review actions pinning/dependency scanning/caching risks.

**Kết quả cần có:** CI pass/fail có thể tái hiện, artifact gắn commit SHA và không có quyền Azure deployment trong job PR.

### 24.3. Lab B1 — App Service staging

1. Dùng Azure Portal/CLI **chỉ đọc** xác nhận App Service staging resource ID và Java runtime.
2. IAM tạo Entra principal/federated credential với đúng subject `environment:staging`.
3. Cấp deploy RBAC cần thiết tại **staging app resource**; không cấp rộng production.
4. GitHub Environment staging đặt `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_WEBAPP_NAME`.
5. Chạy OIDC smoke job phần 4 trên protected branch/environment.
6. Sử dụng App Service workflow phần 7, verify JAR build artifact.
7. Deploy lên staging, kiểm tra App Service logs và health endpoint.
8. Xác minh app commit/version endpoint khớp build run.
9. Kiểm tra Azure Activity Log và Application Insights nếu đã cấu hình.
10. Không thực hiện production deploy nếu production gate chưa được review/phê duyệt.

### 24.4. Lab B2 — ACR và Container Apps

1. Xác nhận Dockerfile, `dist/orders-api-1.0.0.jar`, architecture.
2. IAM tạo environment publisher/deployer identities và federated credentials.
3. Cấp ACR push cho publisher, ACR pull cho Container Apps runtime identity.
4. Bật GitHub `image-publish` environment; registry network phải reachable từ runner.
5. Build image và scan, đẩy với commit tag, lấy image digest output.
6. Đọc lại registry manifest/digest trước deploy.
7. Staging Container App update bằng `repo@sha256:...`; kiểm tra revision name, image reference và readiness.
8. Test API và các dependencies giả lập hoặc staging database.
9. Định nghĩa production environment approval và tách identity.
10. Với canary được phê duyệt, test revision traffic weights, SLO và rollback.

### 24.5. Dùng lệnh read-only để xác minh Azure target

~~~bash
az account show \
  --query "{name:name,id:id,tenant:tenantId}" -o table

# App Service, resource đã biết từ Azure/IaC:
az webapp show \
  --resource-group "<approved-rg>" \
  --name "<approved-app-service-name>" \
  --query "{name:name,id:id,state:state,hostNames:hostNames}" -o json

# Container Apps:
az containerapp show \
  --resource-group "<approved-rg>" \
  --name "<approved-containerapp-name>" \
  --query "{id:id,name:name,latestRevisionName:properties.latestRevisionName}" \
  -o json

az containerapp revision list \
  --resource-group "<approved-rg>" \
  --name "<approved-containerapp-name>" -o table
~~~

Những lệnh **chỉ đọc** cần Azure CLI đúng extension/version và quyền tương ứng. Không tự thêm `--admin` khi gặp access denied. `latestRevisionName` có thể không đồng nghĩa revision đang nhận 100% traffic, nhất là multiple revision mode.

### 24.6. Test matrix tối thiểu

| Case | Điều kiện | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| PR1 | PR bình thường | Chỉ CI; không OIDC Azure deploy | GitHub job permissions |
| PR2 | Unit test fail | Không publish/deploy | Job graph |
| AUTH1 | Job staging, credential đúng | Azure login thành công | Azure principal/tenant/scope |
| AUTH2 | Production job thiếu approval | Không được nhận prod deploy access trước gate | Environment audit |
| AUTH3 | Wrong subject | Entra token exchange denied | Federated claim mismatch |
| PERM1 | Staging principal thử sửa prod | Azure RBAC deny | 403 ở target lab/sandbox được phép |
| ART1 | Staging vs prod artifact | Cùng SHA/digest | Release metadata |
| ACR1 | Publisher push đúng role | Registry nhận image | Digest manifest |
| ACR2 | Container App thiếu pull role | Revision fail rõ | Runtime/ACR diagnostics |
| NET1 | Hosted runner tới private API | Bị chặn nếu không có route | DNS/network evidence |
| APP1 | Staging readiness pass | App nhận traffic lab | Health+metrics |
| CAN1 | Canary vượt error threshold | Stop promotion/rollback | Revision/traffic record |
| DATA1 | Schema migration chưa backward-compatible | Gate chặn hoặc forward-fix | DB integration tests |
| OBS1 | Release tới production | Monitor/Activity Log ghi nhận | Time/version correlation |

**Các test gây lỗi quyền/network phải thực hiện trong môi trường lab/sandbox** hoặc kiểm tra policy tĩnh; không cố ý phá production để chứng minh bảo vệ.

### 24.7. Bài thực hành với data giả

Ví dụ một API `/orders` trong staging nhận event tổng hợp:

~~~json
{
  "orderId": "LAB-ORDER-001",
  "customerRef": "synthetic-customer",
  "items": [{"sku":"SKU-LAB","quantity":2}],
  "requestedAtUtc": "2026-11-20T09:20:00Z"
}
~~~

Đừng dùng credit card thật, production customer ID hoặc gửi email/SMS ra bên ngoài trong lab. Nếu pipeline có side effects, phải có idempotency key và cleanup strategy.

### 24.8. Bài đạt khi nào?

Bài lab được xem là đạt nếu:

- CI PR không có Azure deployment privileges.
- OIDC staging hoạt động, production identity/approvals độc lập.
- Build artifact có hash/digest/commit rõ, không rebuild khi promote.
- App Service hoặc Container App staging chạy đúng release.
- GitHub/ARM/Runtime evidence khớp image hoặc JAR version.
- Có sức khỏe workload (readiness + API smoke) và telemetry sau deploy.
- Có rollback/incident plan có thể diễn tập với **known-good artifact**.
- Secrets/PII không nằm trong logs/image/repo; Azure RBAC và network được review.
- Có cost/cleanup plan cho tài nguyên lab.

## 25. Bài tập tổng hợp và đáp án định hướng

### 25.1. Câu hỏi lý thuyết và tình huống

1. Phân biệt **continuous integration, continuous delivery và continuous deployment**.
2. Workflow GitHub Actions nằm ở đâu trong repository và kích hoạt bằng những events nào?
3. Khác nhau giữa job, step, action và runner là gì?
4. Vì sao job `deploy` không tự đọc được JAR đã build ở job `test`?
5. `actions/upload-artifact`/`download-artifact` khác cache thế nào?
6. Vì sao không nên deployment từ một untrusted PR trên fork?
7. Vì sao `pull_request_target` kết hợp checkout/run PR code với secrets là nguy hiểm?
8. `GITHUB_TOKEN` permissions khác Azure RBAC như thế nào?
9. `id-token: write` làm gì và **không** làm gì?
10. Ghi issuer, audience và subject mặc định cho job `environment: staging`.
11. So sánh subject branch `ref:refs/heads/main` và subject environment `environment:staging`.
12. Nếu Entra báo federated credential mismatch, bạn sẽ kiểm tra những gì?
13. Azure login thành công nhưng deployment 403 nghĩa là lỗi có thể ở lớp nào?
14. Vì sao cần hai identities staging và production?
15. GitHub Environment `production` có tự yêu cầu reviewer ngay khi chỉ khai báo tên trong YAML không?
16. `vars.AZURE_CLIENT_ID` là secret không? Có cần bảo vệ người sửa biến không?
17. Nêu các bước Maven build/test trước App Service deploy.
18. Làm sao chứng minh production dùng **đúng JAR** đã test staging?
19. `azure/webapps-deploy` thành công có chứng minh HTTP API khỏe không?
20. App Service deployment slots giúp rollout/rollback ra sao, và không rollback điều gì?
21. Tại sao Docker image tag `latest` nguy hiểm cho promotion?
22. So sánh tag commit SHA với digest `sha256` của ACR image.
23. Publisher có `AcrPush` thì Container App đã pull được image chưa?
24. Vì sao GitHub-hosted runner thường không kết nối thẳng tới ACR/AKS private endpoint?
25. So sánh Azure Container Apps single và multiple revision modes.
26. Với multiple revision mode, cần giám sát gì trước khi tăng traffic 10% → 100%?
27. AKS deployment qua Helm trực tiếp khác GitOps/Flux chỗ nào?
28. Vì sao không cấp `az aks get-credentials --admin` mặc định cho CI?
29. SBOM/provenance/attestation kiểm soát rủi ro supply chain nào?
30. Tại sao pin full action commit SHA tốt hơn mutable major tag?
31. Một PR title được chèn trực tiếp vào Bash `run` có thể gây lỗi bảo mật gì?
32. Khi database migration không backward-compatible, rollback JAR/image sẽ gặp rủi ro gì?
33. Vì sao production canary cần business KPI ngoài CPU/HTTP 200?
34. Chỉ Azure ARM update 200 OK có đủ kết luận release thành công không?
35. Phân biệt Readiness, liveness, application version/digest, HTTP error rate.
36. Tính runner-minutes khi 40 PR/ngày × 6 phút × 22 ngày.
37. Một workflow matrix 4 jobs mỗi job 6 phút có thể làm runner-minutes tăng thế nào?
38. Vì sao automation dọn PR ephemeral environment cần resource tags/owner TTL?
39. Khi OIDC token hết hạn, vì sao không nên dùng Azure client secret dài hạn để chữa nhanh?
40. Hãy thiết kế một end-to-end release gate và rollback plan cho ứng dụng xử lý đơn hàng.

### 25.2. Đáp án mẫu: OIDC và quyền

**Câu 9:** `id-token: write` cho phép GitHub job **yêu cầu OIDC JWT** từ GitHub. Entra chỉ cấp Azure access token khi JWT khớp federated credential; Azure RBAC tiếp tục giới hạn operations. Quyền này **không tự là Contributor**.

**Câu 10:** Các giá trị thường dùng:

~~~text
issuer:   https://token.actions.githubusercontent.com
audience: api://AzureADTokenExchange
subject:  repo:acme/orders-api:environment:staging
~~~

Subject phải phù hợp với **repository thật**, environment và claim customization nếu có. Bảo vệ environment branch/approval rules vì subject environment không tự giới hạn nhánh.

**Câu 12:** Xác minh repo/branch/environment, subject chính xác, tenant/client ID, issuer, audience, job `id-token: write` và federation principal. Không mở wildcard rồi cấp subscription Owner.

**Câu 13:** Azure RBAC thiếu action ở target resource scope, resource/subscription ID sai hoặc deploy identity không đúng. Federation chỉ xác thực, không tự ủy quyền mọi ARM action.

**Câu 15:** Không. Required reviewers/deployment branch rules phải được cấu hình **thật** trong GitHub Settings và plan hỗ trợ. `environment: production` đơn thuần chưa chứng minh approval.

### 25.3. Đáp án mẫu: artifacts và deploy

**Câu 18:** Lưu binary JAR với SHA-256/commit/run ID; job production tải chính artifact của **cùng workflow run** đã test và staging smoke pass. Không rebuild hoặc download file trùng tên từ run khác.

**Câu 22:** Commit tag giúp liên hệ source revision nhưng có thể bị overwrite nếu registry policy cho phép. Digest `sha256` trỏ **content**, là lựa chọn tốt để deploy chính xác một image. Với multi-arch cần rõ digest index/platform.

**Câu 23:** Chưa. Runtime cần riêng ACR pull permission và registry network path. CI publisher push permission chỉ áp cho publisher principal.

**Câu 27:** Helm direct chạy từ runner có cluster access/Kubernetes RBAC; GitOps controller trong cluster reconcile Git desired state. CI vẫn build/scan và cập nhật image digest vào GitOps repo.

**Câu 28:** `--admin` có thể bypass mô hình Entra/Kubernetes least privilege và mở rộng blast radius của CI; dùng cluster user credentials với namespace-limited authorization đúng thiết kế.

### 25.4. Đáp án mẫu: bảo mật, vận hành và chi phí

**Câu 30:** Tag như `@v4` có thể được publisher cập nhật đến code mới; SHA pin giữ commit code cụ thể. Vẫn cần security update cadence và allowlist.

**Câu 31:** Nếu PR title được interpolation trực tiếp vào Bash source, ký tự đặc biệt có thể thay đổi shell command. Dùng `env` và validate/quote dữ liệu trước khi truyền cho commands.

**Câu 32:** DB schema đã đổi/xóa column có thể khiến binary cũ không hoạt động; rollback không hoàn tác data writes. Dùng expand/contract migrations và forward-fix/recovery plan.

**Câu 36:** `40 × 6 × 22 = 5.280` runner-minutes/tháng trong giả định một job mỗi PR.

**Câu 37:** Nếu 4 jobs cùng chạy 6 phút cho mỗi PR và cùng số PR, aggregate runner minutes có thể gần `21.120`, dù wall-clock của PR chỉ khoảng 6 phút; pricing multipliers/plan cần xác minh.

**Câu 40:** Pipeline: protected source → CI tests → image/JAR digest + SCA/SBOM → OIDC staging deploy → smoke/traces/DB tests → required production approval → canary → SLO observation → traffic rollback/known-good digest và business reconciliation khi lỗi. Không tự xóa database để rollback.

### 25.5. Rubric

| Tiêu chí | Mức đạt |
|---|---|
| **GitHub Actions fundamentals** | Trigger/jobs/steps/permissions/artifacts và environments đúng |
| **Azure OIDC** | Issuer/audience/subject/federated credential và RBAC giải thích rõ |
| **Security** | PR trust boundary, token least privilege, pin action SHA, secret hygiene |
| **Artifact promotion** | Same JAR/image digest staging → production, provenance |
| **Azure workload deployment** | App Service/Container Apps/AKS phù hợp context |
| **Operations** | Smoke, canary, monitor, rollback, database compatibility |
| **Networking** | Private registry/cluster/DB runner route được đánh giá |
| **FinOps** | Runner minutes, registry/artifact retention, workload compute |

## 26. Checklist production GitHub Actions → Azure

### 26.1. Governance repository và workflow

- [ ] Branch `main`/release branches được bảo vệ bằng review/required status checks.
- [ ] CODEOWNERS/review bắt buộc cho `.github/workflows/**`, Dockerfiles, Terraform/Bicep, Helm manifests.
- [ ] Workflow trigger phù hợp event/ref và không auto-deploy từ fork PR.
- [ ] Không dùng `pull_request_target` để chạy untrusted PR code với secrets/writable token.
- [ ] `permissions` khai báo minimal cho từng job; PR CI chỉ `contents: read`.
- [ ] Deploy jobs mới có `id-token: write`, không cấp OIDC cho mọi job.
- [ ] Actions được allowlist/review và pin full immutable commit SHA.
- [ ] Reusable workflows có review, inputs restrictions và target allowlist.
- [ ] Concurrency không cancel production release/migration giữa chừng.
- [ ] Logs/artifacts/caches có retention/permission và không chứa tokens/PII.

### 26.2. OIDC/Entra/Azure RBAC

- [ ] GitHub Environments staging/production có reviewers/branch rules được test.
- [ ] Federated credentials issuer/audience/subject khớp jobs thật.
- [ ] Separate identities staging/prod/publisher khi có thể.
- [ ] Azure RBAC scope tối thiểu tới target resource/registry, không blanket Contributor subscription.
- [ ] GitHub environment vars chứa đúng client/tenant/subscription IDs.
- [ ] Không lưu client secret/password Azure tĩnh chỉ để login workflow.
- [ ] CI publisher và Azure runtime pull/database identities tách nhau.
- [ ] Migration principal tách runtime principal, có DB grants đúng.
- [ ] Có quyền thu hồi federation/rotate identities và audit sign-ins.

### 26.3. Build và artifacts

- [ ] Toolchain Java/Node/Docker được pin phiên bản và có build determinism plan.
- [ ] CI gồm unit/integration tests, lint và security checks.
- [ ] Dependency/SCA/license scanning có policy exceptions được duyệt.
- [ ] Container base image được pin/scan, SBOM/provenance/signature nếu yêu cầu.
- [ ] Artifact hash/digest/commit/run ID được ghi và kiểm tra trước promote.
- [ ] Production **không rebuild** artifact đã test staging.
- [ ] Docker image pin digest, không chỉ `latest` hoặc mutable tag.
- [ ] Multi-architecture image phù hợp target CPU/OS.
- [ ] Không build secret vào JAR/image hoặc log CI.
- [ ] Last-known-good artifact được giữ đủ rollback window.

### 26.4. Azure workload và networking

- [ ] App Service/Container App/AKS target đã tồn tại và được provision bằng IaC được review.
- [ ] OIDC deployment identity có đúng RBAC actions, không hơn.
- [ ] Private endpoints/ACR/AKS/SQL có runner/VNet/DNS route phù hợp.
- [ ] Container runtime image pull identity có đúng ACR pull permissions.
- [ ] Runtime managed identity truy cập Key Vault/DB/Service Bus theo least privilege.
- [ ] SSL/TLS, secrets, custom domains, network ingress/egress đúng policy.
- [ ] Readiness/liveness/startup probes hoạt động và không leak sensitive metadata.
- [ ] Database/schema changes backward-compatible với rolling revisions.
- [ ] Container Apps traffic weights/AKS rollout/App Service slot swap có plan.

### 26.5. Release gates và observability

- [ ] Staging smoke/contract tests thực thi từ đúng network path.
- [ ] GitHub production required reviewers và protected branch rules được xác minh.
- [ ] Canary thresholds/rollback conditions gắn HTTP SLO và business signals.
- [ ] Deploy success kiểm chứng image/JAR digest và actual running revision.
- [ ] Azure Monitor/App Insights/Activity Log và GitHub release evidence có correlation.
- [ ] Action Groups/on-call/runbooks được cấu hình theo mức độ nghiêm trọng.
- [ ] Có rollout freeze, break-glass, rollback và data reconciliation plan.
- [ ] Có audit/ownership cho production deploy, credentials và policy changes.

### 26.6. Chi phí và phục hồi

- [ ] GitHub Actions minutes/concurrency/caches/artifacts có budget và retention.
- [ ] ACR storage/retention/scan policy, runner VM và private network costs được tính.
- [ ] App Service/Container Apps/AKS scaling không vượt database/queue budgets.
- [ ] PR preview resources có owner/TTL/cleanup không đụng shared resources.
- [ ] Backups/DR và restore tests phù hợp business RPO/RTO.
- [ ] Không xóa rollback image/charts/previous revision khi chưa qua safe window.
- [ ] Có review chi phí sau release và hành động nếu budget tăng.

## 27. Dọn dẹp lab an toàn và phát hành quyền sở hữu

Sau bài lab, workload/runner/ACR/Identity/Environments có thể là **tài nguyên dùng chung**. Dọn một bản thử nghiệm không được xóa nhầm production App Service, ACR registry, AKS cluster, GitHub Environment hoặc Entra principal đang được workflows khác dùng.

### 27.1. Kiểm kê các lớp tài nguyên

~~~text
GitHub:
  repository workflows, environments, variables/secrets, artifacts,
  runners, action permissions, branch protections

Microsoft Entra:
  federated credentials, app registration/user-assigned MI,
  role assignments

Azure:
  resource groups, App Service/slots, Container Apps/revisions,
  AKS, ACR images, Key Vault, SQL/Storage/Service Bus,
  Azure Monitor/Log Analytics and billing
~~~

**Workflow run kết thúc không tự thu hồi một Entra federated credential** hoặc role assignment; đây là IAM configuration tồn tại đến khi owner thay đổi.

### 27.2. Các lệnh Azure CLI chỉ đọc

~~~bash
az account show \
  --query "{name:name,id:id,tenantId:tenantId}" -o table

az resource list \
  --resource-group "<approved-lab-rg>" \
  --output table

az webapp list \
  --resource-group "<approved-lab-rg>" \
  --query "[].{name:name,id:id,state:state}" \
  -o table

az containerapp list \
  --resource-group "<approved-lab-rg>" \
  --query "[].{name:name,id:id}" \
  -o table

az acr repository list \
  --name "<approved-lab-acr-name>" \
  --output table
~~~

Các lệnh trên đọc metadata; một số cần Azure CLI extension/role hỗ trợ. Không nhầm việc có quyền xem ACR repository list với quyền xóa image manifests.

### 27.3. Cleanup checklist

1. Xác nhận **subscription/RG/environment/resource IDs** và owner.
2. Xem PR preview environment có đang phục vụ review hoặc test của team khác không.
3. Đảm bảo release evidence/SBOM/attestations/logs cần retention đã được lưu đúng.
4. Chỉ tắt hoặc xóa **lab-only** deployment/config được phê duyệt.
5. Không xóa App Service/Container Apps/AKS/ACR dùng chung chỉ để xóa một version.
6. Kiểm tra Azure Container Apps revisions cũ, ACR images/layers và PR preview compute **theo rollback window**.
7. Thu hồi Entra federated credential/role assignment **lab-only** khi không còn dùng; không revoke identity chung của production.
8. Xóa GitHub Environment variables/secrets lab không còn dùng theo approval; không đụng production branch protection.
9. Kiểm tra worker/runner VMs, disks, container caches và GitHub artifacts/retention.
10. Xác minh Azure Cost Management/GitHub billing không còn các resource lab bất thường.
11. Ghi thao tác, người phê duyệt và trạng thái sau cleanup.

### 27.4. Lệnh phá hủy không được tự chạy trong bài

~~~bash
# Các lệnh chỉ minh họa phạm vi rủi ro. KHÔNG TỰ THỰC THI.

# Xóa resource group phá hủy tất cả resources trong group.
# az group delete --name "<approved-lab-rg>" --yes

# Xóa app/container có thể làm production traffic mất ngay.
# az webapp delete --resource-group "<rg>" --name "<app>"
# az containerapp delete --resource-group "<rg>" --name "<app>" --yes

# ACR image/tag delete có thể làm rollback và offline image pull lỗi.
# az acr repository delete --name "<acr>" --image "orders-api:<tag>" --yes
~~~

**Một image không còn được production traffic dùng ngay bây giờ vẫn có thể là bản rollback** hoặc đang được các thiết bị offline/pod restart cần pull. Dọn image phải dựa trên inventory, retention và approvals.

### 27.5. Hậu kiểm cleanup

| Hạng mục | Bằng chứng cần có |
|---|---|
| GitHub repo | Branch protection/production environment còn nguyên |
| Entra identities | Lab-only federation/role đã thu hồi; production identity không ảnh hưởng |
| ACR | Images cần rollback còn sẵn; chỉ lab tags được dọn |
| Azure app workloads | Production versions/traffic vẫn healthy |
| Databases/queues | Không có dữ liệu thật bị xóa bởi cleanup |
| Monitoring | Logs/alerts/retention vẫn theo policy |
| Billing | Không còn runner/preview resources mồ côi |
| Report | Owner, timestamp và phạm vi thay đổi đã ghi |

## 28. Tài liệu tham khảo và ghi nhớ

### 28.1. Nguồn chính thức để xác minh trước triển khai

- [GitHub Actions documentation](https://docs.github.com/actions) — workflow, events, jobs, environments, permissions và runners.
- [GitHub OpenID Connect with Azure](https://docs.github.com/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure) — OIDC issuer/audience/subject và thiết lập Azure.
- [GitHub security hardening for Actions](https://docs.github.com/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions) — token permissions, untrusted input, third-party actions.
- [GitHub environments for deployment](https://docs.github.com/actions/reference/workflows-and-actions/deployments-and-environments) — required reviewers và deployment branch rules.
- [Azure Login GitHub Action](https://github.com/Azure/login) — `azure/login` OIDC workflow và properties.
- [Azure Web Apps Deploy Action](https://github.com/Azure/webapps-deploy) — package deployment tới App Service.
- [Microsoft Entra workload identity federation](https://learn.microsoft.com/entra/workload-id/workload-identity-federation) — federated credential trust.
- [Deploy to Azure App Service](https://learn.microsoft.com/azure/app-service/deploy-github-actions) — App Service/GitHub Actions integration.
- [Azure Container Apps documentation](https://learn.microsoft.com/azure/container-apps/) — revisions, traffic, identities, ACR.
- [Azure Container Registry authentication](https://learn.microsoft.com/azure/container-registry/container-registry-authentication) — registry access models và identities.
- [Azure Kubernetes Service documentation](https://learn.microsoft.com/azure/aks/) — Kubernetes RBAC, workloads, GitOps.
- [Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/) — logs, metrics, alerts, Application Insights.
- [GitHub Docker build-push-action](https://github.com/docker/build-push-action) — build/push OCI images và digest output.
- [GitHub artifact attestations](https://docs.github.com/actions/concepts/security/artifact-attestations) — provenance, artifact integrity/verification.
- [Microsoft Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — ước lượng dịch vụ Azure theo region/tier.

**Tính thời điểm:** Action major versions, GitHub OIDC custom subject capabilities, GitHub Environment protections, ACR ABAC roles, Azure CLI options, Container Apps revision behavior và pricing có thể thay đổi. Khi production, kiểm tra **tài liệu và support matrix tại ngày triển khai**, pin action/image commit/digest đã kiểm tra và diễn tập trên staging trước.

### 28.2. Mười hai điều cốt lõi

1. **GitHub Actions điều phối workflows**, còn Azure hosting services chịu trách nhiệm runtime workload và health.
2. **CI và CD có ranh giới quyền**: PR chỉ test; protected branch/environment mới có deploy rights.
3. **OIDC federation** cho phép GitHub xác thực Azure không cần client secret dài hạn.
4. **Issuer, audience, subject phải khớp**, đặc biệt `environment:staging` khác `ref:refs/heads/main`.
5. **Azure RBAC tối thiểu** giới hạn deployer trên đúng resource; runtime MI và CI publisher tách nhau.
6. **GitHub Environments cần protection rules thực**, không tự có approval chỉ vì YAML ghi `environment: production`.
7. **Build once, promote same artifact**: JAR SHA-256 hoặc OCI digest, không rebuild giữa staging/prod.
8. **App Service, Container Apps và AKS có cách release khác nhau**: JAR/slots, revisions/traffic, Helm/GitOps.
9. **Private networking là ranh giới riêng**: GitHub-hosted runner không mặc định truy cập private Azure endpoints.
10. **Chuỗi cung ứng cần kiểm soát**: pin actions, scan dependencies/images, SBOM/provenance, không chạy untrusted PR scripts với token đặc quyền.
11. **Deploy success không phải runtime success**: health/SLO/business metrics/rollback/DB compatibility là bắt buộc.
12. **FinOps và cleanup an toàn**: runners, registry, artifacts, preview environments và monitoring đều có chi phí/owner.

### 28.3. Kết luận

Một quy trình **GitHub Actions và triển khai workload lên Azure** đáng tin cậy không chỉ build và gọi lệnh deploy. Nó phải **liên kết commit với artifact bất biến, bảo vệ mã nguồn và runner, xác thực Azure bằng OIDC theo GitHub Environment được kiểm soát, cấp RBAC tối thiểu cho từng nhiệm vụ, triển khai đúng workload/phiên bản tới staging rồi production, kiểm chứng sức khỏe và nghiệp vụ thực tế, đồng thời có khả năng rollback, giám sát và kiểm soát chi phí rõ ràng**.
