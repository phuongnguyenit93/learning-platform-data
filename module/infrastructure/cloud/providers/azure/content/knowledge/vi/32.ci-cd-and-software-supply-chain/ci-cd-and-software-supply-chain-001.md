# Tổ chức mã nguồn và môi trường triển khai Azure

## 1. Bài toán thực tế: từ Git commit đến production

Một nhóm phát triển xây dựng hệ thống bán hàng trên Azure: Java/Spring Boot **orders-api**, một **payment-worker**, frontend, Azure Container Registry, Azure Container Apps hoặc AKS, Azure SQL, Storage, Key Vault và Application Insights. Ban đầu, một kỹ sư build image trên máy cá nhân, lưu cấu hình trong file và triển khai trực tiếp vào resource group duy nhất.

Khi dự án lớn hơn, các vấn đề xuất hiện:

- Môi trường của từng thành viên khác nhau, không tái tạo được khi xảy ra lỗi.
- Cùng một commit nhưng staging và production chạy những build khác nhau.
- Một developer có quyền thay resource và secrets của production.
- Mã Java bị nhân bản thành các thư mục dev/test/prod rồi phát triển lệch nhau.
- CI không kiểm tra test, dependency vulnerabilities và IaC security.
- Không biết artifact đang chạy có nguồn gốc commit, build và dependency nào.
- Lệnh sửa firewall hoặc thay database schema làm hỏng ứng dụng.
- Logs, budgets và quyền quản trị của các môi trường bị trộn lẫn.

**Tổ chức mã nguồn và môi trường triển khai Azure** là thiết kế repository, cấu trúc ứng dụng, nguồn artifact, Infrastructure as Code, identity và quá trình promotion để ứng dụng có thể thay đổi nhanh mà vẫn truy vết, kiểm chứng và khôi phục được.

Đây là bài thuộc chương **CI/CD và chuỗi cung ứng phần mềm** của module **CLOUD_PROVIDERS_AZURE**. Ngữ cảnh module gồm Azure subscription/resource group, Microsoft Entra ID, mạng, tính toán, lưu trữ, dữ liệu, monitoring, security và cost management. Trọng tâm là ranh giới **source → artifact → environment**, không chỉ một lệnh build/deploy.

Tên môi trường, resource, region và con số trong bài đều là **ví dụ giả định**. Chỉ thực thi trên subscription được phép.

## 2. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt source, commit, artifact, deployment, release và runtime environment.
2. Lựa chọn monorepo, polyrepo hoặc hybrid dựa trên ownership và release cadence.
3. Tổ chức thư mục services, libraries, IaC, CI/CD, docs, tests và runbooks.
4. Áp dụng protected branches, pull requests, CODEOWNERS và quality gates.
5. Thiết kế dev/test/staging/prod bằng Azure subscriptions, RGs, quyền và mạng phù hợp.
6. Quản lý thông số môi trường bằng config và secrets thay vì fork mã nguồn.
7. Viết Bicep/Terraform theo module và tham số hóa môi trường.
8. Hiểu OIDC/workload identity federation cho GitHub Actions hoặc Azure Pipelines.
9. Triển khai build một lần, promote cùng artifact image digest qua nhiều environments.
10. Dùng SBOM, dependency/secret scanning, provenance và artifact signing khi thích hợp.
11. Thiết kế migrations, approval gates, rollback, canary và feature flags.
12. Đo SLO, lỗi sau deploy, pipeline lead time, sự cố bảo mật và chi phí theo môi trường.

## 3. Khái niệm cốt lõi

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Source repository** | Mã nguồn được quản lý bằng Git | Java, tests, Dockerfile, Bicep |
| **Commit** | Ảnh chụp thay đổi với Git hash | PR merge commit |
| **Build artifact** | Sản phẩm được CI tạo | JAR, OCI container image |
| **Artifact digest** | Định danh nội dung không phụ thuộc tên tag | SHA-256 image digest |
| **Deployment environment** | Tập tài nguyên, dữ liệu, identity, policy | dev, staging, prod |
| **Infrastructure as Code** | Mô tả cloud resources bằng code | Bicep, Terraform |
| **Deployment** | Đặt artifact và cấu hình vào runtime | Container Apps revision |
| **Release** | Cho người dùng tiếp cận thay đổi | Canary hoặc bật feature flag |
| **Runtime identity** | Principal ứng dụng dùng truy cập Azure | User-assigned managed identity |
| **Deployment identity** | Principal CI/CD dùng quản lý resources | OIDC federated service principal |
| **Policy gate** | Điều kiện không cho promotion nếu không đạt | Required checks, manual approval |

### 3.1. Deploy khác release

Ứng dụng có thể đã được deploy nhưng tính năng vẫn tắt sau feature flag. Chỉ khi bật flag cho một nhóm người dùng mới là release theo nghĩa sản phẩm. Cách này giảm nhu cầu redeploy khi muốn bật/tắt một chức năng, nhưng flag cũng phải được kiểm soát.

### 3.2. Môi trường không phải nhánh Git

Branch tên prod không chứng minh code đã an toàn hoặc đang chạy production. Môi trường là tài nguyên Azure với quyền, mạng, dữ liệu và cấu hình cụ thể. Trunk-based development vẫn có thể deploy từ cùng main commit qua dev → staging → prod.

### 3.3. Repository không phải artifact registry

Git lưu mã nguồn và cấu hình được phép version hóa. ACR hoặc artifact repository giữ những build artifacts và metadata. Không commit binary JAR và container layers vào Git để thay cho artifact management.

## 4. Mô hình tổng thể source → Azure

~~~mermaid
flowchart LR
    DEV[Developer / Pull Request] --> GIT[Git repository]
    GIT --> CI[CI: test, scan, build]
    CI --> ART[Artifact + digest + SBOM]
    ART --> ACR[(Azure Container Registry)]
    GIT --> IAC[IaC plan and policy checks]
    IAC --> INFRA[Azure subscriptions / RG / network / identity]
    ACR --> CD[CD: approvals + promotion]
    CD --> D[Development / QA]
    D --> S[Staging]
    S --> P[Production]
    INFRA --> D
    INFRA --> S
    INFRA --> P
    P --> MON[Azure Monitor / Application Insights]
    MON --> GATE[Verification and rollback decision]
~~~

Hai luồng có liên hệ nhưng cần tách quyền:

- **Application delivery:** mã nguồn, tests, build, scan, artifact, deploy.
- **Infrastructure management:** Azure Policy, network, IAM, Key Vault, workloads, budgets, IaC state.

Không nên để một workflow pull request thông thường có quyền Owner toàn subscription chỉ vì cần deploy một ứng dụng.

## 5. Nguyên tắc thiết kế repository

1. **Một source of truth:** mỗi resource/module có owner và nơi quản lý chính.
2. **Bounded contexts:** mã theo domain/service thay vì một thư mục chung vô hạn.
3. **Reproducible builds:** pin toolchain, dependency versions và giữ lock/manifest phù hợp.
4. **Build artifact không chứa secrets.**
5. **Cấu hình không bí mật và secrets tách khỏi business code.**
6. **IaC được review:** hạn chế drift từ thay đổi Portal thủ công.
7. **CI phải kiểm tra trước khi publish hoặc deploy.**
8. **Audit trail:** biết ai duyệt thay đổi và digest nào đang chạy.
9. **Least privilege:** reviewer, CI, deploy principal và runtime app có quyền khác nhau.
10. **Testability:** business modules không cần production resources để unit test.

### 5.1. Không nhân bản source theo environment

Tránh ba bản **orders-api-dev**, **orders-api-stage**, **orders-api-prod** chứa mã Java gần giống nhau. Một codebase với artifact chung và môi trường cấu hình riêng cho phép dễ kiểm tra code đã chạy trên staging chính là code được promote.

### 5.2. Không đặt mọi thứ vào thư mục utils

Shared code cần có owner, version, tests, compatibility contract và API rõ. Một thư mục helpers khổng lồ sẽ tạo coupling xuyên services.

### 5.3. Deployable boundary khác library boundary

Một microservice được deploy độc lập; một shared library chỉ là dependency. Không tạo microservice mới khi chưa có lý do về ownership, scale, security hoặc release cadence.

## 6. Monorepo, polyrepo và hybrid

| Kiểu | Định nghĩa | Ưu điểm | Đánh đổi |
|---|---|---|---|
| **Monorepo** | Nhiều services/libraries/IaC một repo | Refactor cross-service dễ, CI thống nhất | Selective builds, quyền và dependency graph phức tạp |
| **Polyrepo** | Mỗi service hoặc library một repo | Ownership/release cadence độc lập | Contract/version coordination và automation nhiều hơn |
| **Hybrid** | Repo service riêng, platform/IaC/GitOps repo riêng | Tách security boundary, chia shared policy | Cần quản lý version artifact/config nhất quán |

### 6.1. Khi monorepo phù hợp

Services đổi cùng nhau, team không quá phân tán, các contract được quản lý tập trung và CI có path filters/dependency graph đáng tin.

### 6.2. Khi polyrepo phù hợp

Các teams có quyền bảo mật, release cadence và business ownership khác nhau. Phải có versioning, API contract tests và phụ thuộc build minh bạch.

### 6.3. Hybrid cho Azure landing zone

Platform team có thể sở hữu repo về subscription policies, hub networking và identities; mỗi application team sở hữu repo service; repo cấu hình triển khai/GitOps được bảo vệ. Khi đó application CI không cần quyền chỉnh management groups.

### 6.4. Không tự động chọn kiểu phức tạp nhất

Số services, team size, permissions, cross-repo changes và lead time mới quyết định. Thay đổi topology repository sau này đòi bảo toàn Git history, releases, dependency paths và automation.

## 7. Cấu trúc monorepo gợi ý

~~~text
commerce-platform/
  README.md
  CODEOWNERS
  .editorconfig
  .gitignore
  .github/
    workflows/
      pr-verify.yml
      publish-image.yml
      deploy.yml
  docs/
    architecture/
      adr/
    runbooks/
    security/
  services/
    orders-api/
      pom.xml
      Dockerfile
      src/
        main/
          java/
          resources/
            application.yml
        test/
          java/
    payment-worker/
      pom.xml
      Dockerfile
      src/
        main/
        test/
  libraries/
    event-contracts/
      pom.xml
  infra/
    modules/
      network.bicep
      identity.bicep
      monitoring.bicep
      container-app.bicep
    environments/
      dev/
        main.bicep
        main.bicepparam
      staging/
        main.bicep
        main.bicepparam
      prod/
        main.bicep
        main.bicepparam
  deploy/
    dev.yml
    staging.yml
    prod.yml
  scripts/
    validate-config.ps1
    smoke-test.sh
  security/
    threat-model.md
    supply-chain-policy.md
~~~

Đây là một ví dụ lý thuyết, không phải các file thực đang tồn tại trong workspace người học.

### 7.1. Vai trò từng khu vực

- **services/**: các ứng dụng được deploy độc lập.
- **libraries/**: contract và thư viện dùng chung.
- **infra/modules/**: resource components có thể tái sử dụng.
- **infra/environments/**: composition/parameters theo môi trường.
- **deploy/**: những giá trị cấu hình không bí mật.
- **.github/workflows/**: CI/CD và permission controls.
- **docs/architecture/adr/**: lý do và đánh đổi của quyết định.
- **docs/runbooks/**: vận hành, incident, rollback và recovery.

### 7.2. Terraform thay thế Bicep

Nếu dùng Terraform, có thể tổ chức cùng nguyên tắc modules/environments; cần thêm remote state, locking, provider pinning và approval. Không để hai IaC engines cùng độc lập quản lý một Azure resource mà không phân định ownership.

### 7.3. Không commit secrets vào deploy/prod.yml

Chỉ lưu các thông số không bí mật: tên resource, replica limits, image digest hoặc Key Vault reference không lộ secret. Không lưu password, SAS token, service principal secret hoặc dữ liệu khách hàng thật.

## 8. Ranh giới domain trong Java

Ví dụ packages của orders-api:

~~~text
com.example.orders
  api/
    OrderController.java
    request/
    response/
  application/
    CreateOrderService.java
    OrderQueryService.java
  domain/
    Order.java
    OrderStatus.java
  ports/
    OrderRepository.java
    EventPublisher.java
  adapters/
    persistence/
      CosmosOrderRepository.java
    messaging/
      ServiceBusEventPublisher.java
  config/
    AzureClientsConfiguration.java
  observability/
    RequestTracing.java
~~~

### 8.1. Business logic không phụ thuộc quá sâu vào SDK

Phần domain/application có thể dựa trên interfaces (ports). Các adapters dùng Cosmos DB, Azure SQL hoặc Service Bus SDK để thực thi. Cách này giúp unit test không cần Azure subscription và giảm chi phí thay công nghệ lưu trữ.

### 8.2. API/event contracts

Giữ versioned HTTP API schema hoặc event contracts khi có nhiều services. Không chia sẻ nội bộ database entity bừa bãi vì một thay đổi mapping có thể phá downstream consumer.

### 8.3. Test pyramid

Unit tests kiểm tra business rules, contract tests kiểm tra compatibility, integration tests dùng Azure test resources hoặc emulator phù hợp và end-to-end tests xác minh đường đi triển khai.

## 9. Branching, pull requests và ownership

Hai kiểu phổ biến:

- **Trunk-based:** PR nhỏ → main bảo vệ → CI → build/promotion, dùng feature flags khi cần.
- **GitFlow:** develop/release/hotfix branches phục vụ lịch release, với chi phí merge và divergence cao hơn.

Một chính sách hợp lý cho hệ thống mẫu:

1. main được protected; không force-push tùy tiện.
2. PR phải có reviewer theo CODEOWNERS.
3. Required CI checks phải đạt trước merge.
4. Thay đổi IaC/security cần platform/security review.
5. Pull requests từ fork chạy trong context không có production secrets/deploy permissions.
6. Release tags và image digests được quản lý, ghi rõ commit.
7. Emergency hotfix vẫn cần traceability và post-deployment review.

### 9.1. Path filters trong monorepo

PR chỉ sửa orders-api có thể chạy focused tests; PR sửa shared contract, parent BOM hoặc IaC module phải kích hoạt test cho các dependents. Path filters không thay dependency graph.

### 9.2. Không map branch name thành authorization

Branch prod không tự bảo đảm đủ quyền triển khai. CI deployment identity, protected environment, approval và artifact checks mới phải quyết định.

### 9.3. PR từ fork có thể là untrusted code

Không dùng workflow privileged token để checkout và chạy tùy ý mã của contributor chưa tin cậy. Tách jobs kiểm thử (chỉ đọc) khỏi jobs release (quyền Azure hạn chế).
## 10. Thiết kế dev, test, staging và production

Mỗi môi trường phải có **mục đích kiểm chứng**, ranh giới truy cập và dữ liệu rõ ràng.

| Môi trường | Mục tiêu | Dữ liệu | Quyền và kiểm soát |
|---|---|---|---|
| **Development** | Phát triển, thử tích hợp | Fake/synthetic | Dev identity, ngân sách thấp |
| **Test/QA** | Functional/contract/regression | Synthetic sát schema thật | QA pipeline identity |
| **Staging/Preprod** | Kiểm chứng topology gần prod | Synthetic hoặc đã xử lý privacy | Release identity, gated deploy |
| **Production** | Người dùng thật | Dữ liệu thật được bảo vệ | Prod-only identity, approvals/SLO |
| **Ephemeral PR** | Preview tạm theo PR | Dữ liệu thử | Unique names, auto-cleanup, TTL |

### 10.1. Có bắt buộc đủ bốn môi trường?

Không. Đội nhỏ có thể dùng dev–staging–prod. Một môi trường không có bài test hoặc quy trình sử dụng cụ thể chỉ tăng chi phí và drift.

### 10.2. Không copy raw production data xuống QA

Dùng dữ liệu giả hoặc masking có kiểm chứng và tuân thủ chính sách privacy. Đừng cho QA quyền đọc trực tiếp Key Vault hoặc database production chỉ để debug nhanh.

### 10.3. Staging phải giống production ở những rủi ro chính

Authentication, private networking, TLS, app identity, database migration, ingress, observability và deployment mechanism cần được thử trong topology tương đương. Quy mô RU/s/replicas có thể khác nếu đã ghi rõ đánh đổi.

### 10.4. Ephemeral environments cần owner và thời hạn

Preview phải có suffix riêng, tags, giới hạn costs, destroy có kiểm soát khi PR đóng, tránh giữ cluster/DB/secret lâu dài không ai quản lý.

## 11. Azure tenant, management groups, subscriptions và RG

~~~text
Microsoft Entra tenant
  |
Management Group hierarchy
  |
  +-- Nonproduction subscription
  |      +-- rg-commerce-dev
  |      +-- rg-commerce-test
  |
  +-- Production subscription
         +-- rg-commerce-staging (nếu policy cho phép)
         +-- rg-commerce-prod
~~~

- **Entra tenant:** identities và directory controls.
- **Management group:** áp governance/policy trên nhiều subscriptions.
- **Subscription:** billing, quotas, Azure RBAC và governance scope.
- **Resource group:** tổ chức resources theo vòng đời/quản lý.
- **Resource:** compute, data, storage, network, secrets, monitoring.

### 11.1. Resource group không phải firewall

Hai tài nguyên ở hai RG vẫn có thể kết nối hoặc chia quyền. Isolation phải dùng network, authentication, RBAC và service policies.

### 11.2. Khi nào prod nên ở subscription riêng?

Khi cần ngân sách, quyền, quota, guardrails hoặc compliance độc lập; tách prod khỏi nonprod giúp hạn chế blast radius quản trị.

### 11.3. Không tạo subscriptions vô hạn

Nhiều subscriptions cần thêm network, monitoring, quotas, billing, role management. Tuân thủ Azure landing zone/governance của tổ chức thay vì tự phát minh hệ phân cấp.

## 12. Isolation matrix theo tài nguyên

| Thành phần | Nonprod | Staging | Prod |
|---|---|---|---|
| **Resource group** | Riêng | Riêng | Riêng |
| **ACR** | Dùng chung có kiểm soát hoặc tách | Kéo image đã kiểm chứng | Pull-only, digest pinning |
| **Key Vault** | Secrets test | Secrets staging | Vault/permissions production riêng |
| **Database** | Data giả | Data giả sát schema | Data thật + backup policy |
| **Managed identity** | Sandbox role | Preprod role | Least-privilege production identity |
| **Private network** | Cấu hình theo khả năng | Test topology prod | Private DNS/endpoint/firewall theo policy |
| **Log Analytics** | Retention/budget ngắn | Release telemetry | Retention và access riêng |
| **Budget** | Capped | Forecast | Alert + chargeback |

### 12.1. Shared ACR có thể hợp lý

Một ACR dùng chung để chứa build artifacts giúp promotion cùng digest. Nhưng CI push scope, prod pull scope, network/trust và artifact integrity cần được tách.

### 12.2. Không dùng chung production DB làm staging

Ngay cả khi schema giống nhau, việc deploy migration hoặc chạy load test có thể ảnh hưởng dữ liệu/hiệu năng của người dùng thật.

### 12.3. Staging khác production phải có tài liệu

Một khác biệt chủ ý như replica count thấp hơn không đáng ngại bằng khác biệt không biết, chẳng hạn prod chỉ kết nối qua private endpoint còn staging luôn dùng public endpoint.

## 13. Naming, tagging và Azure Policy

Quy tắc tên ví dụ:

~~~text
rg-<app>-<env>-<region>
ca-<app>-<service>-<env>
kv-<app>-<env>-<suffix>
mi-<app>-<service>-<env>
law-<app>-<env>
acr<app><env><suffix>
~~~

**Giới hạn tên khác nhau theo Azure resource type**, nên kiểm tra ký tự, độ dài và yêu cầu globally unique thay vì dùng nguyên mẫu cho mọi dịch vụ.

Tags gợi ý:

~~~text
application = commerce
environment = prod
owner = platform-team
costCenter = cc-200
dataClassification = confidential
businessCriticality = high
managedBy = iac
~~~

### 13.1. Tag không cấp quyền

Tag environment=prod không làm tài nguyên an toàn. Entra/RBAC, network policy và Azure Policy assignments mới là controls.

### 13.2. Azure Policy và guardrails

Allowed regions, required tags, public access restrictions và baseline security có thể được kiểm soát bằng policy. Các thay đổi management group/subscription-wide cần review riêng vì blast radius lớn.

### 13.3. Không chứa secrets hoặc PII trong tags

Tên/tag có thể xuất hiện trong Portal, diagnostics và bills; chỉ lưu metadata quản trị được phép.

## 14. Cấu hình runtime, không fork code

~~~text
Nonsecret code defaults
   + Environment config
   + Deployment settings
   + Managed identity / Key Vault
   + Feature flags
   = Runtime configuration
~~~

Ví dụ **Spring Boot application.yml** dùng environment placeholders:

~~~yaml
spring:
  application:
    name: orders-api

app:
  storage:
    endpoint: ${AZURE_BLOB_ENDPOINT}
  messaging:
    namespace: ${AZURE_SERVICEBUS_NAMESPACE}
  features:
    newCheckout: ${FEATURE_NEW_CHECKOUT:false}
~~~

Các placeholders trong file Markdown sau khi tạo sẽ có cú pháp Spring với dấu đô-la và ngoặc nhọn. Cấu hình thực được inject qua deployment runtime, không hardcode URL hoặc secret production.

### 14.1. Những giá trị có thể version hóa

Tên logical environment, tên tài nguyên không bí mật, quota/replicas, feature defaults, timeout, region được phê duyệt và Key Vault reference theo policy.

### 14.2. Không commit

Database password, SAS/storage account key, service principal secrets, access tokens, private certificates, raw production customer data hoặc connection string có credentials.

### 14.3. Spring profile không phải boundary bảo mật

spring.profiles.active=prod chỉ chọn cấu hình. Pipeline phải xác minh subscription/resource target và runtime identity riêng.

## 15. Microsoft Entra, workload identity và Key Vault

~~~mermaid
flowchart LR
    PIPE[CI/CD federated identity] --> ARM[Azure control plane]
    ARM --> APP[Azure runtime app]
    APP --> MI[Runtime managed identity]
    MI --> DB[(Azure SQL / Cosmos)]
    MI --> BLOB[(Azure Storage)]
    MI --> BUS[Service Bus]
    MI --> KV[Azure Key Vault]
~~~

### 15.1. Tách identities theo nhiệm vụ

- **CI identity:** deploy chỉ đúng resources/environment.
- **Runtime managed identity:** data-plane roles cho Storage, Service Bus, SQL/Cosmos, Key Vault theo nghiệp vụ.
- **Developer identity:** quyền dev/sandbox, không mặc nhiên production access.

### 15.2. Không dùng client secret dài hạn nếu có federation

OIDC/workload identity federation cho CI giúp nhận token ngắn hạn qua Microsoft Entra. Phải cấu hình trust chặt cho repo/branch/environment và audience theo provider; không cấp phạm vi subscription Owner vô cớ.

### 15.3. Key Vault và App Configuration

Key Vault dành cho secrets/certificates/keys. Nonsecret config và feature flags có thể qua App Configuration khi phù hợp. Kiểm tra refresh/cache behavior, identity permissions và rotation.

### 15.4. Khi secrets lộ vào Git

Chỉ xóa dòng code là không đủ. Revoke/rotate, kiểm tra lịch sử/forks/artifact logs, đánh giá truy cập và thực hiện incident response.

## 16. Network phải được thử từ runtime thật

~~~mermaid
flowchart LR
    USERS[Users] --> EDGE[Front Door / Ingress]
    EDGE --> APP[App Service / AKS / Container Apps]
    APP --> DNS[Private DNS]
    DNS --> PE[Private Endpoints]
    PE --> DB[(Database)]
    PE --> KV[(Key Vault)]
    PE --> STORAGE[(Storage)]
    APP --> MON[Azure Monitor]
~~~

### 16.1. Private DNS và networking là phần của environment

Nếu dev dùng public DB còn production dùng private endpoint, bug DNS/firewall có thể chỉ lộ khi release. Thiết kế staging kiểm tra cùng con đường quan trọng.

### 16.2. Network khác RBAC

DNS/TLS thành công không chứng minh principal có quyền database/Key Vault. Phân loại riêng network errors, authentication và data-plane authorization.

### 16.3. Không sửa lỗi kết nối bằng cách tắt bảo mật

Không bật public access allow-all, bỏ TLS certificate validation hoặc đưa production credential vào CI để chữa tạm mà không có approval.

### 16.4. Shared resources khác subscription cần hợp đồng truy cập

ACR, private DNS và central logging có thể ở subscription platform. Đảm bảo role/scope, network routes, data residency và ownership được định nghĩa.
## 17. IaC: một nguồn định nghĩa tài nguyên Azure

Hai cách phổ biến:

- **Bicep/ARM**: mô tả Azure Resource Manager resources theo schema, hỗ trợ modules và parameter files.
- **Terraform**: quản lý multi-provider infrastructure bằng plan/apply, provider versions và state backend.

Có thể sử dụng cả hai trong một tổ chức khi **phân định scope/ownership**; tránh hai IaC engines cùng độc lập apply lên một tài nguyên.

### 17.1. Bicep module Storage mẫu

~~~bicep
targetScope = 'resourceGroup'

@description('Storage account name must be globally unique')
param storageName string

param location string = resourceGroup().location

param commonTags object = {
  environment: 'dev'
  application: 'commerce'
  managedBy: 'bicep'
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  tags: commonTags
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

output storageResourceId string = storage.id
~~~

Đây là mẫu giáo dục. Kiểm tra Azure API version, allowed regions, naming rules, network restrictions, encryption/backup và organizational policies trước khi áp dụng.

### 17.2. Tách module và composition

**infra/modules** có network, identity, app runtime, monitoring, database; **infra/environments** composition các modules với parameter sets cho dev/staging/prod. Cách này giảm duplicate definitions.

### 17.3. Không tự tạo cả production infrastructure ở mọi code deploy

Application CI/CD thông thường chỉ update app artifact/config đúng scope. Quản lý foundation như policies, VNet hub, Azure SQL provisioning có release/change controls riêng.

### 17.4. IaC review giống source code review

Phải xem quyền, network exposure, xóa resource, retention, cost, destructive changes, regional availability và compliance trước khi apply.

## 18. Parameter files theo môi trường

Giả sử **infra/environments/dev/main.bicep** định nghĩa các parameters tương ứng, một file parameters có thể là:

~~~bicep
using './main.bicep'

param location = 'southeastasia'
param environment = 'dev'
param minReplicas = 1
param maxReplicas = 2
param storageAccountName = 'commerceorderdev001'
~~~

### 18.1. Mẫu không phải lệnh triển khai hoàn chỉnh

File chính phải khai báo các parameters nêu trên và modules/resources cụ thể. Tên Storage là ví dụ, có thể chưa globally unique. Region chỉ minh họa, không phải mặc định cho mọi tổ chức.

### 18.2. Cấu hình không chứa secrets

Bicep parameters trong Git nên chỉ chứa nonsecret. Nếu cần secret input, dùng secure parameter/Key Vault integration theo cơ chế hỗ trợ và policy. Không in secret values trong job logs.

### 18.3. Một composition, nhiều parameter sets

Cùng source Bicep modules nhưng tách env dev/test/staging/prod qua parameter files. Các khác biệt phải được review, không tạo bốn bản duplicate Bicep rồi chỉnh lệch.

## 19. Terraform state là dữ liệu nhạy cảm

Khi dùng Terraform:

- Pin provider/Terraform versions.
- Dùng **remote backend** có access control/encryption.
- Bật locking khi backend hỗ trợ để tránh concurrent apply.
- Giữ **state riêng cho từng environment/ownership boundary**.
- Bảo vệ snapshots/backups và tránh xuất state vào PR logs.
- Review plan và policy compliance trước apply.
- Dùng migration/import/state move commands theo quy trình kiểm soát, không sửa state tùy tiện.

### 19.1. Terraform workspace không thay Azure subscription

Workspace của Terraform giúp phân tách state nhưng không tự tạo RBAC/network/billing boundary. Với prod có yêu cầu security cao, dùng tách biệt backend/state cùng principal và scope được phê duyệt.

### 19.2. Không để PR job tự apply hoặc destroy

Pull request validation thường lint/validate/plan trong môi trường giới hạn. Apply/destroy cần identity có quyền đúng environment, manual/reviewer gate cho thay đổi nhạy cảm và log audit.

### 19.3. Sensitive outputs không đồng nghĩa state không chứa secrets

Dữ liệu Terraform state có thể lưu raw attributes nhạy cảm. Dùng RBAC, encryption, secure pipelines và giảm việc tạo secrets qua Terraform khi không cần.

## 20. Drift detection, what-if và quy trình thay đổi hạ tầng

**Drift** là sự khác biệt giữa hạ tầng Azure thực và trạng thái mong muốn trong IaC, chẳng hạn operator bật public network access để debug rồi không sửa IaC.

Quy trình:

1. Inventory đúng subscription/resource group/owner.
2. Chạy Bicep what-if hoặc Terraform plan.
3. Review network/IAM/data loss/change impact và cost.
4. Được phê duyệt theo mức rủi ro.
5. Deploy/apply với principal đúng scope.
6. Readback state/critical properties từ Azure.
7. Chạy integration/smoke/policy checks.
8. Lưu deployment ID/commit, đối soát drift còn lại.

### 20.1. What-if không chứng minh production hoàn toàn an toàn

Provider/API responses có thể thiếu thông tin runtime. Những thay đổi network, database schema, RBAC và deletes vẫn cần owner xem xét.

### 20.2. Emergency Portal changes

Nếu phải thay nhanh để khôi phục service, ghi incident/change record và backport vào IaC sau đó. Không để cấu hình production trở thành nguồn duy nhất mà Git không phản ánh.

### 20.3. Ngăn destructive cleanup

Các scripts cần kiểm tra subscription ID, RG, environment tags và approval trước khi xóa. Không dùng wildcard hoặc shell biến rỗng làm target xóa resource group.

## 21. Dữ liệu và database migration theo môi trường

**Dev/test** dùng dữ liệu giả; **staging** dùng schema và connectivity gần production; **prod** có backup/restore, retention và change policy riêng.

### 21.1. Expand–migrate–contract

Một thay đổi database schema an toàn thường qua:

1. **Expand:** thêm field/cột mới, code cũ còn chạy.
2. **Migrate:** backfill/dual-read/write khi cần, kiểm tra quality.
3. **Contract:** chỉ xóa field cũ khi tất cả consumers đã chuyển và rollback window kết thúc.

### 21.2. Rollback ứng dụng không rollback database

Nếu bản mới đã ghi format mới, image cũ có thể không đọc được. Phải thiết kế backward compatibility và forward-fix thay vì giả định revert commit là khôi phục mọi state.

### 21.3. Tránh migration ở mọi Pod startup

20 replicas chạy destructive migration đồng thời có thể gây conflict. Dùng release migration job riêng, locking/idempotency, verification và approval.

### 21.4. Không dùng production DB cho load tests

Load/performance tests có thể thay dữ liệu, tạo locks, tăng RU/s hoặc kích hoạt billing. Chạy trong môi trường có dataset synthetic và thông số đủ đại diện.

## 22. CI là gì và cần tạo ra bằng chứng nào?

**Continuous Integration (CI)** kiểm chứng thay đổi trước khi merge hoặc tạo artifact đáng tin cậy.

Một pipeline CI cho Java/containers nên gồm:

~~~text
Checkout exact commit
    |
Toolchain setup + pinned dependencies
    |
Formatting / lint
    |
Compile + unit tests
    |
Contract + integration tests phù hợp
    |
SAST / SCA / license + secret scan
    |
IaC validation (nếu có thay đổi)
    |
Build OCI image / JAR
    |
Image and dependency scan
    |
SBOM + provenance / signing theo policy
    |
Push immutable artifact to registry
~~~

### 22.1. Không merge khi test fail rồi hy vọng deploy sửa được

Required checks cần chạy từ trusted pipeline configuration. Duy trì branch protection và review dù test nhanh.

### 22.2. Dependency cache không phải nguồn tin duy nhất

Cache giúp tăng tốc, nhưng dependency resolution phải có version pinning và xác thực nguồn phù hợp. Không cache credential hoặc artifact chưa được tin cậy rồi dùng trong privileged release job.

### 22.3. Trạng thái PR khác release

PR verification nên có quyền đọc và không cần Azure production credentials. Publish/release jobs chỉ chạy trên protected refs với approvals và identities riêng.

## 23. CI build một lần, deploy nhiều lần

Nguyên tắc **build once, promote the same artifact**:

~~~text
Source commit A
    |
CI build and verify
    |
Image: acr.example.azurecr.io/orders-api@sha256:<digest>
    |
    +--> Development
    |
    +--> Staging
    |
    +--> Production
~~~

### 23.1. Vì sao digest quan trọng?

Một tag như **latest**, **stable** hoặc **v1.2.3** có thể được gán lại nếu registry không có controls phù hợp. **Image digest** tham chiếu nội dung artifact và giúp biết chính xác image được kiểm thử là image nào được deploy.

### 23.2. Không rebuild ở bước promotion

Nếu staging rebuild từ cùng source nhưng dependency resolution hoặc toolchain khác, artifact có thể thay đổi. Promotion nên mang theo digest/version/provenance đã kiểm tra, không biên dịch lại production bằng một job khác.

### 23.3. Registry artifact và deployment config độc lập

Image digest là một phần của release manifest. Environment-specific config, database connectivity, managed identity và compute size được cung cấp khi deploy. Image không cần chứa các secrets.

### 23.4. Khi copy image giữa registries

Nếu chính sách bắt buộc separate ACRs, có thể promote image qua import/copy được hỗ trợ. Cần verify image manifest/digest, signatures/provenance và policy, không chỉ nhìn tag giống nhau.

## 24. Chọn platform cho artifacts và runtime

| Workload | Hình thức artifact | Azure runtime có thể phù hợp |
|---|---|---|
| Spring Boot REST API | OCI image hoặc JAR | Container Apps, AKS, App Service |
| Java batch/worker | OCI image | Container Apps Jobs, AKS Jobs, VM |
| Azure Functions | Function app package/container tùy hosting | Azure Functions |
| Frontend static | Built static assets | Static Web Apps, Storage/CDN tùy nhu cầu |
| Shared Java library | Maven package | Artifact repository được quản lý |
| IaC | Bicep/Terraform modules | CI/CD deployment engine |

### 24.1. Một image có thể có nhiều target runtimes?

Không phải image nào cũng portable hoàn toàn: port, probes, filesystem, env vars, network, identity integration và architecture cần đúng. Dù cùng digest, runtime behavior còn phụ thuộc environment.

### 24.2. AKS hay Container Apps?

AKS phù hợp khi cần kiểm soát Kubernetes/network/policy phức tạp. Container Apps có mô hình container PaaS với revisions/scaling thuận tiện cho nhiều workloads. Chọn theo yêu cầu vận hành, không vì “CI/CD dễ hơn” mà bỏ qua networking/data needs.

### 24.3. ACR permissions

Publisher cần quyền push phù hợp. Runtime identity cần pull. Không bật ACR admin user làm default shortcut nếu có Entra RBAC/managed identity khả dụng.

## 25. CD: luồng promotion có gating

~~~mermaid
flowchart TD
    B[Verified artifact digest] --> D[Deploy Dev]
    D --> T{Smoke / Integration PASS?}
    T -- No --> X[Stop + investigate]
    T -- Yes --> S[Deploy Staging]
    S --> Q{E2E / Security / Performance PASS?}
    Q -- No --> X
    Q -- Yes --> A{Protected approval / change policy}
    A -- No --> X
    A -- Yes --> P[Deploy Production gradually]
    P --> H{Health and SLO within budget?}
    H -- No --> R[Rollback or halt rollout]
    H -- Yes --> F[Record release provenance]
~~~

### 25.1. Không bắt buộc người duyệt mọi nonprod deploy

Dev có thể tự động deploy khi CI đạt. Production cần gate tương xứng với rủi ro/compliance; platform hỗ trợ protected environments, reviewers, required checks hoặc approvals trong toolchain đang dùng.

### 25.2. Promotion artifact đã qua staging

Ghi rõ digest, source commit, build workflow run, scan reports và approval change ID. Không cho deploy một tag tùy ý từ registry chưa được đánh giá.

### 25.3. Idempotent deployments

Chạy lại deploy cùng manifest/digest nên dẫn tới trạng thái kỳ vọng, không tạo resource vô hạn hoặc duplicate business operations.

### 25.4. IaC và app deployment có thể có vòng đời khác

Một thay đổi network/cơ sở dữ liệu có thể cần migration/staged rollout trước khi deploy image. Release orchestrator phải biết dependency và compatibility, không chỉ chạy thứ tự file theo alphabet.

## 26. GitHub Actions và Azure Pipelines: chọn tool, giữ nguyên nguyên tắc

Cả **GitHub Actions** và **Azure DevOps Pipelines** đều có thể tự động hóa CI/CD với Entra/federated identities, reusable pipeline templates và approval controls theo khả năng sản phẩm.

| Mục đích | GitHub Actions | Azure Pipelines |
|---|---|---|
| PR checks | workflows và branch rules | PR validation/policies |
| Build Java | runner + Maven/JDK setup | agent + Maven/Java tasks |
| Authentication Azure | OIDC qua azure/login khi cấu hình | Workload identity federation service connection |
| Protected production | GitHub environments/rules | Environments/approvals/checks |
| Artifact metadata | build artifacts/packages, container registry | pipeline artifacts/packages, ACR |
| IaC checks | Bicep/Terraform CLI/actions | CLI/tasks/templates |
| Logs/audit | Workflow/job records | Pipeline run logs and approvals |

### 26.1. Không đặt toàn bộ CI và CD trong một quyền

PR job không cần quyền production deploy. Release job có trust/policy và principal riêng. Tránh workflow tái sử dụng có thể bị caller untrusted truyền script rồi chạy với token đặc quyền.

### 26.2. Pin actions/tasks/tool versions

Dùng approved action versions, tốt hơn nữa pin immutable commit digests theo policy chuỗi cung ứng. Có quy trình review updates thay vì dùng action branch không kiểm soát.

### 26.3. Self-hosted runners có nguy cơ riêng

Runner dùng chung cho untrusted PR và production deployment có nguy cơ token theft/persistent compromise. Dùng isolated ephemeral runners hoặc managed trusted environments, cập nhật/patch và không giữ secret lâu dài trên disk.
## 27. CI workflow mẫu cho Java Maven

GitHub Actions có thể kiểm chứng PR và commit trên main:

~~~yaml
name: verify-orders

on:
  pull_request:
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
          java-version: '17'
          cache: maven
          cache-dependency-path: services/orders-api/pom.xml
      - name: Verify Java code
        working-directory: services/orders-api
        run: mvn -B -ntp verify
~~~

### 27.1. PR job chỉ cần contents: read

PR verification không cần OIDC token, ACR push hoặc Azure resource deployment. Điều này giảm rủi ro khi chạy code từ contributor chưa tin cậy.

### 27.2. Quality gates cần bổ sung

Ví dụ chỉ là Maven verify. CI thực cần static security analysis, dependency/secret scanning, license checks, contract/integration tests và IaC security checks khi phù hợp. Có required checks bảo vệ main.

### 27.3. Pin dependencies và actions

Major version như checkout@v4 là minh họa. Policies chặt hơn có thể yêu cầu pin immutable commit SHA và review khi cập nhật. Maven plugin/dependency versions cũng cần quản lý, không trông cậy vào cache.

## 28. OCI image và workflow publish qua ACR

Dockerfile minh họa cho một Spring Boot service:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /app
COPY pom.xml ./
COPY src ./src
RUN mvn -B -ntp verify

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Trước production:** pin base image digest, scan OS packages, dùng JAR path xác định thay vì wildcard nếu có nhiều artifacts, không COPY secrets, verify file ownership/non-root runtime và quan sát JVM memory/probes.

Workflow mẫu build/push từ protected main khi đã có OIDC identity/ACR permissions:

~~~yaml
name: publish-orders

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: build
    steps:
      - uses: actions/checkout@v4

      - name: Azure login via OIDC
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Login to ACR
        run: az acr login --name "${{ vars.ACR_NAME }}"

      - name: Build and push image
        id: image
        uses: docker/build-push-action@v6
        with:
          context: services/orders-api
          push: true
          tags: ${{ vars.ACR_LOGIN_SERVER }}/orders-api:${{ github.sha }}

      - name: Record digest
        run: echo "Image digest: ${{ steps.image.outputs.digest }}" >> "$GITHUB_STEP_SUMMARY"
~~~

### 28.1. Những điều workflow giả định

- Protected main và environment build có governance.
- Entra federated identity credential trust đúng repository/ref/environment.
- Principal có quyền push ACR theo permission model hiện tại.
- Registry/network/runner đã cấu hình.
- Docker build context hợp lệ và tests/security checks là required gates.

### 28.2. Tag không thay digest

Tag theo commit giúp tìm kiếm, nhưng release manifest nên ghi OCI digest thực để xác minh đúng nội dung image. Tag có thể bị di chuyển nếu không khóa bằng policy.

### 28.3. Mẫu chưa đủ supply-chain gates cho prod

Cần bổ sung SBOM, signature/provenance, vulnerability/secret scanning và kiểm chứng release metadata theo chính sách. Đừng coi việc workflow push thành công là image đã đáng tin.

## 29. Ví dụ CD chỉ vào staging, theo digest

~~~yaml
name: deploy-orders-staging

on:
  workflow_dispatch:
    inputs:
      image_digest:
        description: 'Approved OCI digest sha256:...'
        required: true
        type: string

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Update Container App image
        shell: bash
        env:
          RG: ${{ vars.RESOURCE_GROUP }}
          APP: ${{ vars.CONTAINER_APP }}
          REGISTRY: ${{ vars.ACR_LOGIN_SERVER }}
          DIGEST: ${{ inputs.image_digest }}
        run: |
          set -euo pipefail
          [[ "$DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 2
          az containerapp update \
            --resource-group "$RG" \
            --name "$APP" \
            --image "$REGISTRY/orders-api@$DIGEST"
~~~

### 29.1. Regex chỉ kiểm tra định dạng digest

Mẫu chỉ xác minh chuỗi sha256 đúng hình thức, **không kiểm tra provenance, signature, image đã qua CI hoặc allowlist release**. Production workflow phải lấy digest từ verified release manifest và có gate kiểm tra trust.

### 29.2. Registry và runtime identities

Container App cần có cách pull image hợp lệ qua registry config/managed identity và role phù hợp. Pipeline deployment chỉ có quyền cập nhật đúng app/resource group.

### 29.3. Production dùng identity/approvals riêng

Không đơn giản thay environment staging thành production rồi cho mọi contributor chạy. Production cần protected release ref, reviewed digest, approvers, OIDC trust bị giới hạn và post-deployment SLO checks.

### 29.4. Deploy CLI success chưa là release healthy

Kiểm tra app revision ready, probes, ingress, database connectivity, logs/traces và synthetic business tests sau lệnh update.

## 30. OIDC / workload identity federation

~~~mermaid
sequenceDiagram
    participant CI as CI runner
    participant ISS as OIDC issuer
    participant ID as Microsoft Entra ID
    participant AZ as Azure Resource Manager
    CI->>ISS: Request identity token
    ISS-->>CI: Signed short-lived token
    CI->>ID: Exchange for Azure access token
    Note over ID: Verify issuer, subject, audience, federation
    ID-->>CI: Azure token
    CI->>AZ: Deploy at authorized scope
    AZ-->>CI: Result
~~~

### 30.1. Cần cấu hình đồng bộ

1. Principal ở đúng Entra tenant.
2. Federated credential issuer/subject/audience đúng.
3. Pipeline có id-token permission.
4. Azure role ở đúng RG/resource.
5. Protected ref/environment checks.
6. Azure login, runner, DNS/network có thể hoạt động.

### 30.2. CI identity khác runtime identity

CI token dùng cập nhật Azure resource; ứng dụng sử dụng managed identity riêng để gọi SQL, Storage, Key Vault và Service Bus. Không đưa CI token vào image hoặc app config.

### 30.3. Khi OIDC login lỗi

Kiểm tra tenant, subject, environment name, audience, RBAC và principal/client ID. Không lưu client secret production vào Git để chữa nhanh.

## 31. Azure Pipelines và GitHub Actions cùng chung nguyên tắc

Với Azure DevOps, có thể dùng **service connection** dựa trên workload identity federation, protected Environments/approvals/checks, pipeline artifacts và reusable YAML templates.

| Khả năng | GitHub Actions | Azure Pipelines |
|---|---|---|
| PR validation | Workflow + branch rules | PR validation/policies |
| Azure auth | OIDC/federated identity | Federated service connection |
| Protected deployments | Environments/reviewers | Environments/approvals/checks |
| Artifacts | OCI registry/build artifacts | Pipeline artifacts/ACR |
| IaC | Azure CLI/Bicep/Terraform tasks | Azure CLI/Bicep/Terraform tasks |
| Audit | Workflow/deployment records | Runs/approvals/service connection logs |

### 31.1. Không cấp Owner chỉ để deploy

Deployment identity nên có quyền tối thiểu trên đúng Azure resource/RG. Quyền cấp role assignments hoặc thay policy cần deployment pipeline đặc biệt có approval.

### 31.2. Build artifact được giữ nguyên qua stages

Prod stage lấy metadata/digest do CI tạo và staging xác minh; không Maven rebuild riêng trước prod mà mất kiểm soát dependencies.

### 31.3. Self-hosted runner/agent isolation

Không dùng một host lâu dài chạy untrusted PR rồi dùng token deploy prod trên cùng workspace/cache/container socket. Dùng isolated/ephemeral runners và secret hygiene.

## 32. SBOM: biết artifact chứa những thành phần nào

**Software Bill of Materials (SBOM)** liệt kê dependencies, versions, licenses và components của một release theo format như **CycloneDX** hoặc **SPDX**.

### 32.1. Ví dụ thành phần

- Java Maven direct/transitive dependencies.
- OS packages của container base image.
- Third-party binaries/tools trong image.
- Metadata về build tool, artifact digest và licenses.

### 32.2. Giá trị khi có CVE

Khi thư viện bị công bố lỗ hổng, có thể tìm artifacts/digests chứa phiên bản ảnh hưởng, owner và deployment environments đang dùng chúng.

### 32.3. SBOM không bảo đảm secure

Nó có thể thiếu/không đúng. Cần source integrity, dependency/SCA scanning, policy, cập nhật và vulnerability management liên tục.

### 32.4. Gắn SBOM với immutable digest

Đừng để file SBOM mô tả tag latest đã bị thay image. Có access control cho SBOM nội bộ nếu chứa danh sách dependencies nhạy cảm.

## 33. Provenance, signature và deployment trust

**Build provenance** giúp ghi source revision, builder/workflow identity, build inputs và metadata liên quan tới artifact. Kết hợp signing/attestations theo toolchain phù hợp.

~~~text
Protected source ref
   -> Reviewed code + dependency policies
   -> Trusted builder
   -> Tests / scans
   -> Immutable digest
   -> SBOM + provenance + signature
   -> Controlled OCI registry
   -> Verification gate at deployment
   -> Runtime audit + monitoring
~~~

### 33.1. Signing cần verification

Một công cụ như cosign/Sigstore có thể hỗ trợ ký/kiểm tra OCI artifacts theo trust policy. Nhưng ký image mà CD không verify signature/provenance thì không thực sự có deploy gate.

### 33.2. Trust chain có nhiều mắt xích

Source protection, token scope, runner isolation, dependency pinning, registry permissions và artifact verification đều quan trọng. Một chữ ký không thay test/security review.

### 33.3. Không suy build provenance là bảo đảm ứng dụng đúng

Provenance trả lời “artifact đến từ đâu”, không tự trả lời “logic không có lỗ hổng” hoặc “dữ liệu migration an toàn”. Vẫn cần kiểm thử và theo dõi production.
## 34. Dependency security, SAST/SCA và license policy

Một bản Java/container build xanh vẫn có thể chứa libraries có vulnerabilities, transitive dependencies cũ hoặc mã độc trong build chain. Pipeline nên có:

1. **Static Application Security Testing (SAST)** cho code.
2. **Software Composition Analysis (SCA)** cho dependency và CVE.
3. **Container image scanning** cho OS packages/layers.
4. **Secret scanning** của source, histories và IaC theo policy.
5. **License compliance** đối với dependency distribution.
6. **IaC scanning** cho public exposure, wildcard permissions, encryption/network.
7. **Artifact provenance** và signed verification.
8. **Dependency updates** và rebuild từ patched base images.
9. **Finding triage** theo severity, exposure và exploitability.
10. **Exception approvals** có owner, lý do và expiry.

### 34.1. Không dùng CVSS là tiêu chí duy nhất

Một finding quan trọng được đánh giá cùng reachability, exploit availability, internet exposure và compensating controls. Tuy nhiên, không nên tự tắt tất cả security gates chỉ vì pipeline cần “xanh”.

### 34.2. Pinning và reproducibility

Dùng version pinning cho Java/Maven plugins, base image digests và workflow actions theo security policy. Một tag phiên bản động khiến rebuild cùng commit có thể sinh ra artifact khác.

### 34.3. Vulnerabilities sau release

SBOM/provenance giúp định danh artifacts đang chứa dependency bị ảnh hưởng. Có quy trình rebuild, retest và promote bản vá, không chỉ scan một lần lúc PR.

### 34.4. Không cho scanner đọc production secrets

Security scanners cũng là software chạy trong pipeline. Quản lý token, filesystem scope, network access và nơi nhận reports như một mắt xích có rủi ro chuỗi cung ứng.

## 35. Secrets scanning và runner hardening

### 35.1. Secrets có thể rò ở ngoài Git

Build logs, environment dumps, Docker build args, crash reports, SBOM custom metadata, artifact uploads và diagnostic archives đều có thể chứa token. Không dùng shell verbose trace khi chạy lệnh có credentials.

### 35.2. Untrusted PR và privileged workflows

PR từ fork chỉ nên được chạy với quyền và secrets theo policy an toàn. Không chuyển đổi workflow sang privileged event rồi checkout/run mã PR chưa tin cậy.

### 35.3. Reusable workflow input validation

Chỉ cho phép deployment inputs như **verified digest, approved environment, release ID**. Không nhận shell script tùy ý từ caller không tin cậy rồi chạy trong release identity context.

### 35.4. OIDC vẫn cần bảo vệ pipeline

Short-lived tokens giảm rủi ro secrets dài hạn nhưng workflow bị chiếm hoặc federation trust quá rộng vẫn có thể xin Azure token. Bảo vệ branch, env, runner, identity và permissions đồng thời.

## 36. Chiến lược triển khai: rolling, blue/green, canary

| Chiến lược | Cách hoạt động | Lưu ý |
|---|---|---|
| **Rolling update** | Thay dần replicas | Readiness, schema compatibility, disruption budget |
| **Blue/green** | Hai phiên bản cùng tồn tại, chuyển traffic | Tốn capacity tạm thời, data migrations |
| **Canary** | Đưa một phần nhỏ traffic tới bản mới | Metrics/routing/stop conditions |
| **Feature flags** | Deploy trước, bật sau | Quản trị flag, rollout và rollback state |
| **Manual cutover** | Chuyển khi có approval | Downtime và switch-back plan |

### 36.1. AKS rolling deployments

Cần startup/readiness/liveness probes, resource requests/limits, networking, rollout configuration và PodDisruptionBudget khi phù hợp. Kubernetes thông báo rollout success không chứng minh business API đúng.

### 36.2. Azure Container Apps revisions

Container Apps có revisions và traffic management theo chế độ/capability hỗ trợ, phù hợp một số canary patterns. Phải kiểm tra ingress, revision mode và traffic weights thực, không giả định giống App Service slots.

### 36.3. Azure App Service deployment slots

Slots có thể cho staging/prod swap theo App Service plan/support, nhưng slot-sticky settings, managed identities, warmup, network/database configuration phải được đánh giá. Swap không đảm bảo zero-risk.

### 36.4. Giữ app state bên ngoài replica

Rolling/canary an toàn hơn khi in-memory state không giữ dữ liệu nghiệp vụ duy nhất. Payment workflows cần durable state và idempotency để tránh duplicate khi request/retry chuyển giữa revisions.

## 37. Feature flags và configuration rollout

Feature flags giảm nhu cầu tạo long-lived branches và có thể cho phép tách thời điểm deploy khỏi thời điểm bật chức năng.

### 37.1. Phân loại flags

- **Release flags:** mở tính năng mới theo từng nhóm người dùng.
- **Operational flags:** tắt tích hợp gây lỗi hoặc chuyển fallback.
- **Experiment flags:** A/B testing có thống kê thích hợp.
- **Permission flags:** chỉ bổ sung UI/config, **không thay authorization backend**.

### 37.2. Flag cũng cần quản lý như code

Có owner, mục tiêu, ngày xóa/TTL, default value, môi trường áp dụng và test trạng thái on/off. Flags sống nhiều năm có thể biến code thành ma trận điều kiện khó duy trì.

### 37.3. Azure App Configuration

Khi phù hợp, có thể dùng Azure App Configuration cho nonsecret config/feature flags và managed identity để truy cập. Kiểm tra label/refresh semantics, data-plane roles và SDK/runtime integration được hỗ trợ.

### 37.4. Rollback flag không xóa side effect

Nếu tính năng đã chuyển tiền hoặc ghi dữ liệu, tắt flag ngăn hoạt động mới chứ không tự bù trừ transactions đã xảy ra.

## 38. Database schema compatibility trước và sau deployment

Một pipeline tốt phải biết bản ứng dụng cũ và mới cùng tồn tại trong giai đoạn rollout.

### 38.1. Expand–migrate–contract

1. **Expand:** thêm bảng/cột/field mới theo cách tương thích.
2. **Migrate:** backfill hoặc dual-read/write theo plan có kiểm chứng.
3. **Contract:** gỡ field cũ khi tất cả consumers đã chuyển và qua rollback window.

### 38.2. Database migration job riêng

Tránh chạy migration destructive khi 20 Pods cùng startup. Dùng job riêng có ownership/locking/idempotency và quyền database tối thiểu, backup khi cần.

### 38.3. Rollback code không tự rollback schema

Nếu bản mới ghi schemaVersion 2, bản cũ có thể không parse được. Cần forward fix hoặc compatibility window; rollback image mù có thể làm lỗi nặng hơn.

### 38.4. Event schema evolution

Các phiên bản payment-worker có thể xử lý messages do version orders-api khác tạo. Dùng schema compatibility tests, versioned events, idempotent consumers và DLQ theo policy.

## 39. Observability sau deploy: thế nào là thành công?

Ghi một **release marker** chứa:

~~~text
environment = production
service = orders-api
sourceCommit = <git-sha>
imageDigest = sha256:<digest>
releaseId = <release-id>
deployedAtUtc = <UTC timestamp>
approvedBy = <workflow/approver record>
~~~

Không log token/secret trong release marker.

### 39.1. Các tín hiệu cần theo dõi

| Tín hiệu | Mục đích |
|---|---|
| Successful requests/s | Nhu cầu và throughput |
| Error rate/5xx | Chất lượng sau deploy |
| p95/p99 latency | Long-tail failures |
| Pod/revision readiness | Runtime rollout |
| Database 429/deadlocks/timeouts | Hệ dữ liệu bị quá tải |
| Queue backlog/age/DLQ | Worker đang chậm hoặc lỗi |
| JVM heap/GC/CPU | Resource pressure |
| Dependency errors | Azure SQL, Storage, Service Bus |
| Cost per operation | Tác động ngân sách |
| Correlation/traces | Tìm nguyên nhân liên dịch vụ |

### 39.2. Azure Monitor và Application Insights

Dùng metrics, logs, traces, workbooks/alerts phù hợp với Azure runtime. CorrelationId/traceId giúp nối API request với SQL, Storage và Service Bus operations. Tránh high-cardinality tags chứa user IDs/PII.

### 39.3. Alerting không chỉ sau production

Staging phải có signals để biết smoke/performance tests fail. Production cần monitors độc lập với deployment tool để phát hiện lỗi ngay cả khi pipeline đã kết thúc.

### 39.4. Đặt SLO và rollback thresholds trước release

Không tự chọn “p99 dưới 100 ms” khi production workload thực cần 500 ms. Dùng baseline, user impact, error budget và business-critical transactions để đặt ngưỡng.

## 40. Verification, rollback và forward-fix

Quy trình release production:

1. Xác minh CI artifact digest, SBOM/provenance và approval.
2. Verify subscription/resource/app target.
3. Triển khai canary hoặc rolling theo policy.
4. Kiểm tra runtime readiness và smoke.
5. So sánh error rate/p95/p99 với baseline.
6. Nếu đạt, mở traffic từng phần.
7. Nếu fail, halt/rollback image hoặc tắt feature flag theo runbook.
8. Ghi kết quả và đối chiếu release manifest.

### 40.1. Previous known-good digest

Ghi lại digest cũ **trước** release; rollback phải chỉ đích danh digest/manifest tương thích, không dùng mutable latest.

### 40.2. Rollback IaC có thể nguy hiểm

Git revert không hoàn tác dữ liệu đã xóa hoặc mất; thay network/policy/SQL có thể cần recovery plan khác. IaC destructive changes phải có backup/approval.

### 40.3. Khi forward-fix tốt hơn

Nếu database đã migrate sang schema mới không tương thích bản cũ, cần deploy hotfix hợp tác với DB migration, không khôi phục image cũ rồi hy vọng hoạt động.

### 40.4. DR khác deployment rollback

Vấn đề regional outage/replication/failover khác lỗi bản release. Tài liệu DR phải tính RPO/RTO, data consistency, region restrictions, secrets và DNS/cutover.

## 41. Azure Cost Management cho nhiều môi trường

Chi phí có thể phát sinh từ:

- Compute: App Service, Container Apps, AKS/node pools, Functions.
- ACR image storage/network.
- Azure SQL/Cosmos DB Storage và throughput.
- Azure Storage operations, capacity, snapshots/backup.
- Application Insights/Log Analytics ingestion/retention.
- Private Link, firewall/NAT và egress.
- CI runners/agents và test resources.
- Ephemeral PR environments còn sót.
- Multi-region replication/DR.

### 41.1. Budget theo môi trường và owner

Tags/subscription/RG boundaries giúp chargeback nhưng cost allocation cần xác minh scope thực. Đặt budget alerts và forecast riêng cho nonprod/prod.

### 41.2. Scale không tự tăng hiệu quả

HPA tăng Pods trong khi database RU/s cố định có thể gây 429 và retries. Tính total system capacity, không chỉ tăng compute.

### 41.3. Production và staging có thể khác scale

Giữ những topology/security constraints quan trọng, nhưng staging không cần cùng capacity khi không chạy full-scale performance tests. Ghi nhận khác biệt.

### 41.4. Preview cleanup là một tính năng CI/CD

Các môi trường tạo theo PR phải có TTL, ownership, resource tags và job cleanup có guardrails, tránh tích lũy resources tính phí nhiều tuần.

## 42. Policy-as-code và change control

Một tổ chức có thể dùng Azure Policy, IaC security tools, branch rules và deployment gates để thực thi:

- Allowed regions/SKUs.
- Required tags/ownership.
- No public access cho dữ liệu nhạy cảm.
- Encryption/TLS minimums.
- Identity/RBAC boundaries.
- Protected environments và reviewers.
- Artifact integrity/provenance.
- Budget/retention policies.
- Backup, disaster recovery và monitoring baselines.

### 42.1. Nhiều chính sách tạo nhiều cấp độ

Quy tắc Azure Policy kiểm tra resources; pipeline rules kiểm tra code/artifacts; Spring Security kiểm tra user actions; network security kiểm tra data paths. Không một công cụ nào thay tất cả.

### 42.2. Exception có thời hạn

Nếu một service cần policy exemption hợp pháp, ghi owner, lý do, ngày hết hạn, scope và compensating controls. Không disable toàn subscription vì một test nhỏ không deploy được.

### 42.3. Break-glass access

Quyền khẩn cấp phải quản lý, giám sát và audit; không dùng tài khoản break-glass làm credential cho pipeline thường ngày.

## 43. Runbook: release sai môi trường hoặc sai artifact

**Tình huống:** phát hiện staging artifact mới đã được deploy lên production mà chưa có approval.

### Bước 1 — Hạn chế tác động

Dừng promotion pipeline, xác minh blast radius và customer impact. Không chạy bừa một deploy mới trước khi hiểu trạng thái.

### Bước 2 — Ghi bằng chứng

Lấy pipeline run ID, Git commit, artifact digest, resource group/subscription ID, thời điểm, principal và change ticket.

### Bước 3 — Đánh giá state và side effects

Có schema migration, payment/business events hoặc dữ liệu nào đã thay đổi không? Rollback image có an toàn không?

### Bước 4 — Khôi phục

Nếu tương thích, deploy previous known-good digest hoặc chuyển traffic về revision/slot cũ. Nếu data/schema không tương thích, dùng approved forward-fix/compensation.

### Bước 5 — Xác minh

Smoke tests, readiness, error rate, queues, database metrics và traces. Đối soát artifacts thực chạy bằng digest, không chỉ tag.

### Bước 6 — Khắc phục nguyên nhân

Review GitHub environment rules/Azure DevOps approvals, OIDC trust subject, RBAC scopes, workflow triggers và principal permissions. Bổ sung hard gate để ngăn lặp lại.

### Bước 7 — Post-incident

Lưu incident report, timeline, owner và action items. Không xuất secrets/production customer data vào báo cáo công khai.
## 44. Ma trận quyết định tổ chức repository và môi trường

Đưa ra lựa chọn dựa trên rủi ro và cách team làm việc thay vì theo công cụ đang thịnh hành.

| Câu hỏi | Khi câu trả lời là “có” | Hướng xử lý |
|---|---|---|
| Nhiều services luôn đổi cùng nhau? | Các contract/service coupling cao | Cân nhắc monorepo và dependency-aware CI |
| Teams có release cadence/quyền khác nhau? | Quyền và ownership tách biệt | Polyrepo/hybrid |
| Network/IAM production rất nhạy cảm? | Có compliance/segregation of duties | Platform IaC repo/pipeline riêng |
| Cần tái hiện ứng dụng từ commit? | Có yêu cầu audit/rollback | Version pinning, digest, provenance |
| Cần PR environment? | UI/integration review thường xuyên | Ephemeral env với TTL và bounded cost |
| Staging khác prod về identity/network? | Có rủi ro production-only failures | Bổ sung preprod parity tests |
| DB schema thay đổi thường xuyên? | Có nhiều consumers cùng hoạt động | Expand–migrate–contract và contract tests |
| Cần rollback nhanh? | SLO và change frequency cao | Immutable artifacts, canary, previous digest |
| Có yêu cầu giữ dữ liệu theo vùng? | Data residency cụ thể | Regions/subscriptions/workspace boundaries |
| Chi phí nonprod tăng khó kiểm soát? | Có nhiều preview/test resources | Tags/budgets/cleanup automation |

### 44.1. Architecture Decision Record (ADR)

Một ADR ngắn nên chứa **context, options, decision, rationale, security/privacy impacts, cost, rollback/migration plan và owner**. Ví dụ chọn monorepo cho 3 services cùng đội và tách platform subscription repo do quyền quản trị khác nhau.

### 44.2. Không chọn thứ không thể vận hành

Một pipeline signing/phân quyền nhiều tầng nhưng không ai biết kiểm tra khi fail có thể làm release tắc. Đưa khả năng vận hành, runbook và training vào quyết định kiến trúc.

## 45. Lab 1: thiết kế cấu trúc repository cho hệ thống Azure

**Mục tiêu:** biến yêu cầu nghiệp vụ thành ranh giới modules/ownership và source layout.

### A. Bài toán giả định

Có orders-api, payment-worker, frontend, shared event schemas, ACR, Key Vault, Azure SQL, Service Bus, Application Insights và network policy.

### B. Thiết kế

1. Chọn monorepo/polyrepo/hybrid và giải thích lý do.
2. Vẽ source tree gồm services, libraries, infra, deploy, docs và CI.
3. Xác định CODEOWNERS cho service, platform IaC, security.
4. Viết danh sách build dependencies giữa modules.
5. Định nghĩa shared contract versioning và test scope khi thay contract.
6. Mô tả nguyên tắc configuration không fork code.

### C. Kiểm tra anti-pattern

- Có secrets trong application-prod.yml không?
- Có Docker image/JAR binary committed trong Git không?
- CI có chạy lại tất cả tests khi shared contract thay đổi không?
- Developer có quyền sửa platform policy production không?
- Repo có runbook deployment/rollback và ADR không?

### D. Deliverable

Một cây thư mục như mục 7, bảng ownership, rules PR/branch, và ADR tối đa vài trang nêu đánh đổi. **Đây là bài lab thiết kế; không cần tạo subscription thật.**

## 46. Lab 2: dựng môi trường Azure bằng IaC

**Chỉ thực hành trên Azure lab subscription và resource group đã được cấp phép; không sử dụng subscription production.**

### A. Xác định mục tiêu

- Dev có Storage hoặc Container Apps environment nhỏ.
- Staging có identity riêng, network rules và logs riêng.
- Prod chỉ được mô tả bằng parameters và policy; không cần triển khai thật trong lab.
- Tất cả tài nguyên có tags và owner.

### B. Bicep hoặc Terraform

1. Chọn IaC engine được phép.
2. Tạo module storage/network/identity tối thiểu theo service support.
3. Tạo parameter sets dev/staging.
4. Khai báo region, tags, unique resource names và SKU.
5. Không nhúng storage account keys hoặc database secrets.
6. Thêm validate/what-if hoặc plan review.
7. Chạy trên target subscription/RG đã xác nhận.
8. Readback properties/identity từ Azure.
9. Ghi bằng chứng plan/apply và kết quả smoke check.
10. Cleanup **chỉ resources riêng của lab** sau khi review.

### C. Một chuỗi Azure CLI kiểm tra scope

~~~bash
az account show \
  --query "{subscription:id,name:name,tenant:tenantId}" -o table

az group list \
  --query "[].{name:name,location:location}" -o table
~~~

Đây là **read-only inspection** minh họa. Trước khi chạy bất kỳ lệnh tạo/xóa, xác nhận account và RG cụ thể. Không đưa một lệnh destroy chung vào bài lab nếu chưa chứng minh phạm vi lab độc lập.

### D. Tiêu chí hoàn thành

Một module có thể deploy lại idempotent; env dev/staging có parameters khác hợp lý; không có public data exposure trái policy; kết quả plan/readback khớp; resources không bị bỏ quên.

## 47. Lab 3: PR validation, OCI image và supply-chain metadata

### A. Chuẩn bị

1. Chọn repo test chứa Java 17/Spring Boot app và Dockerfile.
2. Dùng branches/PR protected theo quyền được cấp.
3. Chạy Maven verify tự động.
4. Thêm SAST/SCA/secret scan theo toolchain.
5. Kiểm tra một PR với test fail bị chặn merge.
6. Kiểm tra PR từ fork không nhận production deployment token.

### B. Build và ACR

1. Cấu hình Entra OIDC trust cho environment **build** đúng repo/ref.
2. Cấp quyền push registry giới hạn, không cấp subscription Owner.
3. Build image từ main commit được bảo vệ.
4. Push tag gắn commit SHA.
5. Ghi OCI digest do registry/build action trả về.
6. Tạo SBOM và provenance theo tool được phê duyệt.
7. Scan image/dependencies và ghi nhận findings.
8. Nếu có policy signing, tạo signature/attestation và kiểm tra lại.
9. Đảm bảo không có secrets nằm trong Docker layers.

### C. Bảng ghi nhận

| Thuộc tính | Nguồn xác minh |
|---|---|
| Git commit | CI run |
| Builder workflow/run ID | CI system |
| Artifact registry/path | ACR |
| Image digest | OCI manifest |
| SBOM ID/format | Artifact metadata |
| Provenance/signature | Approved verifier |
| SAST/SCA/container scan | Security reports |
| Reviewer/approval | PR/change record |

### D. Tiêu chí

Từ digest có thể truy ra commit/build, kiểm tra test/scan outcomes và biết image còn được tin cậy theo policy hay không.

## 48. Lab 4: promote cùng digest qua staging

### A. Bước chuẩn bị

1. Có image digest được CI phê duyệt.
2. Có Container App/AKS test resource riêng.
3. Runtime identity có quyền pull ACR.
4. Environment staging có Entra federated deployment identity.
5. Có staging config nonsecret và Key Vault references riêng.
6. Có readiness/smoke checks và monitoring.

### B. Thực hành deployment

1. Lấy digest từ release manifest, **không build lại**.
2. Verify provenance/signature theo khả năng lab.
3. Chạy staging deployment bằng target scope chính xác.
4. Readback image digest thực tại Container App revision/AKS workload.
5. Kiểm tra HTTPS/ingress/TLS.
6. Kiểm tra kết nối Storage/SQL/Service Bus theo dữ liệu giả.
7. Đo p95/error rate/correlation logs.
8. Ghi release ID, commit, digest và approval.
9. Thử redeploy cùng digest, kiểm tra idempotency.

### C. Trường hợp lỗi

- Azure login 401/403: kiểm tra federation subject, principal và RBAC.
- ACR pull fail: kiểm tra registry identity/network.
- Revision không ready: xem startup/probes/config và logs.
- SQL/Storage timeout: xem private DNS, routing, data-plane roles.
- Sai digest: chặn deploy, không chấp nhận tag gần giống.

### D. Không triển khai prod thật

Bài lab chỉ cần đề xuất **production promotion design** với protected environment, approvers, verified image provenance và rollout gates. Không cấp quyền production cho người học.

## 49. Lab 5: canary, rollback và giả lập sự cố

### A. Giả lập release xấu

Trên staging lab, tạo một version có lỗi synthetic làm tăng HTTP 500 hoặc request duration trong phạm vi an toàn, không gọi API production.

### B. Chạy canary

1. Đặt một lượng traffic test nhỏ tới revision mới nếu platform hỗ trợ.
2. Theo dõi error rate, latency, logs và request correlation.
3. So sánh với baseline version cũ.
4. Xác định threshold dừng rollout trước khi thử.
5. Khi fail, dừng tăng traffic và chuyển về revision/digest lành mạnh.

### C. Rollback không được tạo duplicate

1. Gửi synthetic order requests với idempotency key.
2. Thử một request bị timeout rồi retry qua phiên bản cũ/mới.
3. Đảm bảo không tạo duplicate payments/orders.
4. Xác minh database schema còn tương thích với image rollback.
5. Nếu không tương thích, viết đề xuất forward-fix.

### D. Post-release verification

| Tín hiệu | Trước | Sau | Kết luận |
|---|---|---|---|
| Error rate | Baseline | Đo | Pass/fail |
| p95/p99 latency | Baseline | Đo | Pass/fail |
| Revision readiness | Stable | Đo | Pass/fail |
| Payment smoke outcome | Pass | Đo | Pass/fail |
| Queue backlog | Baseline | Đo | Pass/fail |
| DB retries | Baseline | Đo | Pass/fail |
| Running digest | Good digest | Đo | Đã rollback đúng? |

### E. Tiêu chí

Người học phải chứng minh deployment audit trail, rollback decision, artifact identity và dữ liệu không bị phá bởi việc chuyển phiên bản.

## 50. Checklist production trước khi mở quyền deploy

- [ ] Repository topology có ADR và ownership rõ.
- [ ] Không nhân bản code theo dev/staging/prod.
- [ ] Branch protection và CODEOWNERS được bật theo chính sách.
- [ ] PR verification không có production credentials.
- [ ] Có format, compile, unit/integration/contract tests.
- [ ] Có SAST, SCA, dependency/secret/license/IaC security checks.
- [ ] Build toolchain, dependencies và actions được pin/review.
- [ ] Docker build không nhúng secrets, chạy non-root nếu phù hợp.
- [ ] Artifacts lưu trong registry và dùng immutable digest.
- [ ] SBOM/provenance/signature gắn với digest theo yêu cầu.
- [ ] Deployment kiểm tra trust và policy, không chỉ regex digest.
- [ ] Dev/test/staging/prod có mục tiêu kiểm chứng rõ.
- [ ] Resource groups/subscriptions và scopes được xác định.
- [ ] Production data không được copy nguyên sang nonprod.
- [ ] Environment identities khác nhau, least privilege.
- [ ] OIDC trust subject/audience/issuer được cấu hình chặt.
- [ ] Runtime managed identity tách CI deployment identity.
- [ ] Key Vault secrets không xuất hiện trong Git/image/logs.
- [ ] Networking/private DNS/TLS được kiểm thử từ runtime thật.
- [ ] Azure Policy/tags/regions/cost budgets đúng governance.
- [ ] Bicep/Terraform state/parameters có owner và change approval.
- [ ] IaC plan/what-if, security và destructive changes được review.
- [ ] Không để hai IaC tools cùng quản lý một resource vô chủ.
- [ ] CI chỉ push artifact sau required tests/scans.
- [ ] CD promote cùng digest, không rebuild theo environment.
- [ ] Staging smoke/performance/security đạt trước production.
- [ ] Production có protected approval và identity riêng.
- [ ] Canary/rolling/blue-green strategy được chọn theo runtime.
- [ ] Readiness/liveness và application metrics đúng.
- [ ] Release marker ghi commit, digest, runtime, approval.
- [ ] Previous known-good digest và rollback runbook sẵn sàng.
- [ ] DB migration tương thích, idempotent và có backup plan.
- [ ] Feature flags có owner, default và expiry.
- [ ] App/DB/queue/network quotas được định cỡ đồng bộ.
- [ ] Monitoring/alerting có p95/p99, errors, backlog và logs.
- [ ] Có SLO/error-budget stop conditions cho rollout.
- [ ] Cost Management theo environment và service owner.
- [ ] Preview environments có TTL/auto-cleanup/guardrails.
- [ ] Có runbook khi triển khai sai resource, artifact hoặc identity.
- [ ] Break-glass changes được audit và backport vào IaC.
- [ ] Có post-deployment verification và change record.
- [ ] Có kiểm thử recovery/DR theo RPO/RTO yêu cầu.

## 51. Câu hỏi tự kiểm tra

1. Source code, artifact và environment khác nhau ở đâu?
2. Vì sao không giữ ba bản Java code cho dev/test/prod?
3. Deploy có đồng nghĩa với release cho người dùng không?
4. Monorepo có lợi thế gì khi thay shared API contract?
5. Khi nào nên dùng polyrepo hoặc hybrid?
6. CODEOWNERS có thay CI tests không?
7. Vì sao PR từ fork không được dùng production identity?
8. Branch tên prod có phải bảo đảm authorization không?
9. Azure management group, subscription và resource group khác nhau thế nào?
10. Resource group có tự tạo network isolation không?
11. Vì sao production subscription riêng có thể giảm blast radius?
12. Staging cần giống prod ở các mặt quan trọng nào?
13. Có nên copy raw production customer data vào staging không?
14. Tại sao ephemeral PR environment phải có TTL?
15. Resource tags có thay RBAC hay Azure Policy không?
16. Những loại cấu hình nào được phép lưu trong Git?
17. Vì sao không nhúng database key vào Docker image?
18. Deployment identity khác runtime managed identity thế nào?
19. Key Vault có thay Spring Security/business authorization không?
20. OIDC giảm rủi ro nào so với long-lived client secret?
21. Khi OIDC login lỗi, cần kiểm tra điều gì trước?
22. DCR/monitoring và IaC thuộc source layout nào?
23. Vì sao cần Bicep/Terraform modules và parameter files?
24. Terraform state có thể chứa secrets không?
25. Làm sao phát hiện drift do sửa Azure Portal?
26. What-if có tự bảo đảm apply an toàn không?
27. CI cần tạo những bằng chứng gì ngoài kết quả compile?
28. Build once/promote same digest khác rebuild-on-prod thế nào?
29. Vì sao image tag không đủ để xác định artifact?
30. ACR push permission khác runtime pull permission thế nào?
31. SBOM là gì và giúp tìm CVE ra sao?
32. Provenance/signature có tự thay security testing không?
33. Vì sao deployment phải verify signing/provenance khi policy yêu cầu?
34. GitHub environment approval khác code review như thế nào?
35. Khi nào rolling, blue/green hoặc canary hợp lý?
36. Vì sao readiness green chưa chứng minh business flow đúng?
37. Feature flag có tự rollback dữ liệu/transactions không?
38. DB expand–migrate–contract giúp ích gì khi có hai app versions?
39. Vì sao rollback image không rollback database schema?
40. Những chỉ số nào nên được theo dõi ngay sau release?
41. Scale Azure compute có tự scale SQL/Cosmos capacity không?
42. Chi phí preview environments được kiểm soát thế nào?
43. Nếu deploy sai subscription, hành động đầu tiên là gì?
44. Break-glass Portal change cần được xử lý ra sao?
45. Khi nào cần forward-fix thay vì rollback?
46. RPO và RTO có liên quan gì đến deployment rollback?
47. Làm sao xác minh image thực chạy đúng digest đã duyệt?
48. Vì sao promotion phải có audit trail và release manifest?
49. Một pipeline “xanh” có thể vẫn gây sự cố production vì sao?
50. Ba quyết định quan trọng nhất khi thiết kế môi trường Azure là gì?

## 52. Tổng kết

**Tổ chức mã nguồn và môi trường triển khai Azure** cần một thiết kế xuyên suốt từ repository tới runtime. Source layout phải phản ánh **service ownership, testability và ranh giới modules**; môi trường dev/test/staging/prod phải khác nhau theo **mục đích kiểm chứng, dữ liệu, identity, policy, network, chi phí và quyền triển khai** chứ không chỉ tên folder hoặc nhánh Git.

Một luồng đáng tin xây dựng artifact từ commit được kiểm duyệt, chạy **tests và security gates**, ghi nhận **SBOM, provenance và immutable digest**, rồi **promote chính artifact đó** qua các protected environments. Bicep/Terraform quản lý hạ tầng theo IaC; Microsoft Entra/OIDC và managed identity loại bỏ nhiều credentials dài hạn; Azure Policy, Key Vault, network controls và môi trường tách biệt giới hạn blast radius.

Production release không kết thúc khi CLI trả thành công. Cần **readiness, smoke tests, telemetry, SLO, approvals, previous known-good digest, database compatibility và rollback/forward-fix runbooks**. Với Azure Monitor, Cost Management và governance theo subscription/resource group, đội phát triển có thể giao phần mềm thường xuyên mà vẫn đảm bảo tính truy vết, bảo mật, khả năng phục hồi và kiểm soát chi phí.






