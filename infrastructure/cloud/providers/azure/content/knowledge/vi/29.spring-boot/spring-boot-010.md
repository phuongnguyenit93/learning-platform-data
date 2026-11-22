# Quản lý cấu hình bằng Azure App Configuration

Một ứng dụng **Spring Boot** thường có các giá trị thay đổi theo môi trường: timeout của dịch vụ thanh toán, số lần retry, kích thước trang dữ liệu, mức giới hạn đơn hàng, giao diện tính năng mới hoặc endpoint của các dịch vụ nội bộ. Khi mỗi giá trị được sao chép vào application.yml, manifest Kubernetes, cấu hình App Service hay các biến môi trường, đội vận hành dễ gặp **configuration drift**: production sử dụng một giá trị khác staging, một instance chưa được cập nhật, hoặc phải build và deploy lại chỉ vì thay đổi một timeout.

**Azure App Configuration** cung cấp kho **key-value có quản lý tập trung**, hỗ trợ **labels**, **feature flags**, **snapshots**, đồng bộ ứng dụng và tích hợp với **Azure Key Vault** để tham chiếu bí mật. Đối với Java, có thể truy cập qua **Azure SDK for Java**; với Spring Boot có thể tích hợp thông qua **Spring Cloud Azure App Configuration** để nạp giá trị vào Spring Environment và tùy cấu hình, làm mới một số giá trị khi ứng dụng đang chạy.

Bài thuộc chương **Spring Boot trên Azure**, module **CLOUD_PROVIDERS_AZURE**. Trong lộ trình khám phá Azure từ subscription, resource group, Microsoft Entra ID đến compute, mạng, lưu trữ và dữ liệu, đây là khâu thiết kế cấu hình để **triển khai, vận hành, bảo mật, giám sát và kiểm soát chi phí** của ứng dụng một cách nhất quán.

> **Nguyên tắc cốt lõi:** Azure App Configuration là nơi quản lý **cấu hình ứng dụng**, không phải nơi phát tán mật khẩu. App Configuration có thể chứa **Key Vault references**, nhưng secret value phải được bảo vệ bằng danh tính, quyền đọc Key Vault, networking và chính sách log riêng. “Thay đổi key-value trong store” cũng **không mặc nhiên** có nghĩa tất cả Spring Boot instances đã thấy và áp dụng thay đổi ngay.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **local application.yml**, **environment variables**, **Azure App Configuration** và **Azure Key Vault**.
2. Giải thích cấu trúc key-value, label, content type, tag, ETag, feature flag và snapshot.
3. Thiết kế naming convention, phạm vi theo ứng dụng/môi trường/tenant và chính sách precedence.
4. Chọn Azure RBAC cho **App Configuration Data Reader** và **App Configuration Data Owner**, khác với quyền Azure control plane.
5. Tạo store, key-values và labels trong một lab bằng Azure Portal/CLI với dữ liệu demo.
6. Cấu hình Java SDK để đọc cấu hình qua **DefaultAzureCredential** hoặc managed identity.
7. Tích hợp **Spring Cloud Azure App Configuration starter** theo **Spring Boot/Spring Cloud Azure version compatibility**.
8. Bind cấu hình vào **@ConfigurationProperties**, kiểm tra dữ liệu bằng validation và tránh hard-code.
9. Hiểu **refresh**, **sentinel key**, **refresh interval**, caching và sự khác nhau giữa refresh environment với cập nhật state của beans.
10. Phân biệt feature flags với giá trị config thông thường và thực hiện rollout có kiểm soát.
11. Kết hợp **Key Vault reference** với quyền truy cập riêng của workload mà không đưa secret vào store.
12. Thiết kế fail-fast, stale-cache policy, startup fallback và khả năng xử lý store outage.
13. Phân tích private endpoint, DNS, VNet Integration, role propagation và lỗi 401/403/404/429.
14. Đo end-to-end propagation, logging, auditing, rollback, FinOps và kiểm thử production.

## 2. Tình huống xuyên suốt: Orders API

Orders API chạy trên Azure App Service hoặc AKS, gồm ba environments: **dev**, **staging**, **prod**. Các tham số:

| Cấu hình | Giá trị dev | Giá trị prod | Lưu ở đâu? |
|---|---|---|---|
| Checkout timeout | 1500 ms | 800 ms | App Configuration |
| Retry count | 1 | 2 | App Configuration |
| Page size | 20 | 50 | App Configuration |
| Feature: new-checkout | bật cho QA | rollout có điều kiện | App Configuration feature flag |
| Partner payment endpoint | sandbox URL | production URL | App Configuration nếu không nhạy cảm |
| Partner API key | demo secret | production secret | Key Vault |
| Instance port | do platform cấp | do platform cấp | Runtime/environment |
| Java heap limit | theo host/container | theo host/container | Runtime/deployment |
| Database password | không cần nếu Entra auth | legacy credential nếu bắt buộc | Key Vault, hoặc bỏ hẳn khi dùng managed identity |

Một thay đổi “checkout timeout từ 800 lên 1000 ms” không nên buộc đóng gói JAR mới. Nhưng thay đổi này vẫn phải được **review**, có người sở hữu, được triển khai theo môi trường, có đường rollback và kiểm tra ảnh hưởng.

Yêu cầu kiến trúc:

- Cấu hình phải gắn với **đúng application và environment**.
- Production chỉ tải những keys nó được phép sử dụng.
- Mọi instance cuối cùng phải đạt cấu hình mong muốn trong **propagation SLO**.
- Không đưa connection string chứa secret vào App Configuration dưới dạng plain text.
- Có cách xử lý khi App Configuration tạm không khả dụng.
- Có telemetry để biết instance đang sử dụng revision/version nào.
- Không mở quyền ghi cho một ứng dụng chỉ cần đọc.

## 3. Sơ đồ kiến trúc tham chiếu

~~~mermaid
flowchart LR
    ENG["DevOps / IaC / operators"] --> STORE["Azure App Configuration<br/>keys + labels + feature flags"]
    STORE --> KVREF["Key Vault reference metadata"]
    KVREF --> KV["Azure Key Vault<br/>secret value"]
    MI["Microsoft Entra ID<br/>Managed Identity"] --> APP["Orders API<br/>Spring Boot"]
    APP --> SDK["Spring Cloud Azure<br/>or Java SDK"]
    SDK --> STORE
    SDK --> KV
    APP --> CLIENT["HTTP clients / checkout"]
    OBS["Azure Monitor / App Insights"] -. "metrics / audit" .-> APP
    OBS -. "diagnostics" .-> STORE
    SOURCE["Git + reviewed IaC"] --> ENG
~~~

**Đường quản trị:** người quản trị hoặc pipeline được phép tạo store, thay key-values/feature flags/labels, kiểm soát version/snapshot.

**Đường dữ liệu:** ứng dụng xác thực với Entra ID, truy cập endpoint của App Configuration bằng role đọc, lấy key-values và tham chiếu Key Vault khi có cấu hình phù hợp.

**Đường ứng dụng:** Spring Environment hoặc một lớp config service chuyển các giá trị thành kiểu dữ liệu có validation, rồi các Spring beans sử dụng để quyết định hành vi.

**Đường quan sát:** đo lỗi nạp cấu hình, thời gian làm mới, thay đổi flag, phiên bản được áp dụng và ảnh hưởng lên SLO nghiệp vụ.

App Configuration **không tự đẩy** mọi thay đổi vào từng object Java đang tồn tại. Cơ chế thay đổi còn phụ thuộc integration library, refresh activation, caching và bean lifecycle.

## 4. App Configuration khác Key Vault, application.yml và Environment

| Công cụ | Vai trò | Thế mạnh | Giới hạn |
|---|---|---|---|
| Spring application.yml | Cấu hình gắn với JAR/environment | Đơn giản, dễ dùng local | Thay đổi thường gắn với deploy |
| Environment variables | Tham số runtime/platform, bootstrap | Phổ biến trong container/App Service | Khó đồng bộ/audit trên nhiều services |
| **Azure App Configuration** | Quản lý key-values, labels, feature flags | Tập trung, metadata, dynamic refresh patterns | Là dependency từ xa, cần auth/network |
| **Azure Key Vault** | Bảo vệ secrets, keys, certificates | Data-plane authorization, audit, rotation | Không dành cho mọi non-secret parameter |
| Azure App Configuration + Key Vault reference | Cấu hình + chỉ dẫn lấy secret | Không lưu secret value trong store | Vẫn cần role/network tới cả hai |
| Azure SQL/Cosmos DB | Business state và transaction | Query/transactions, persistence | Không nên dùng làm kho config nếu không cần |
| Kubernetes ConfigMap | Pod-scoped non-secret config | Native K8s deployment | Drift và rollout phụ thuộc cluster |
| Kubernetes Secret | Secret distribution của K8s | Tích hợp pod | Cần bảo vệ etcd/RBAC, rotation riêng |

**Ưu tiên managed identity trực tiếp** khi Azure SQL/Storage/Service Bus hỗ trợ Entra auth; lúc đó không cần cất một account key trong Key Vault chỉ vì “cấu hình tập trung”.

### 4.1. Những gì không nên đưa vào App Configuration

- Mật khẩu, access token, private keys, shared secret dưới dạng plain text.
- Dữ liệu khách hàng hoặc transaction records.
- Session state, cart state và locking state.
- Giá trị riêng cho từng HTTP request/người dùng có thể thay đổi liên tục.
- Log payload hoặc metrics liên tục cập nhật.
- Những config bắt buộc phải cập nhật tức thời/atomic across all instances nếu application chưa có giao thức điều phối phù hợp.

## 5. Cấu trúc key-value và metadata

Một mục App Configuration được nhận diện bằng **key + label**. Giá trị có thể là string, JSON document, feature flag content hoặc tham chiếu Key Vault tùy **content type**.

Ví dụ:

~~~text
key:         orders:checkout:timeout-ms
label:       prod
value:       800
contentType: text/plain
tags:
    owner=orders-team
    classification=internal
etag:        "revision-from-service"
~~~

### 5.1. Key

**Key** nên diễn đạt application, area và setting:

~~~text
orders:checkout:timeout-ms
orders:checkout:retry-count
orders:ui:page-size
orders:payments:endpoint-url
orders:sentinel
~~~

Tên có dấu phân cách cần thống nhất với binding strategy. Chọn **prefix theo ứng dụng** để tìm kiếm, cấp quyền và vận hành dễ hơn. Không nhúng PII, access token hoặc tenant secret vào tên key.

### 5.2. Label

**Label** phân biệt một key theo environment hoặc phân khúc có chủ đích:

~~~text
key: orders:checkout:timeout-ms
label: dev       value: 1500
label: staging   value: 1100
label: prod      value: 800
~~~

Còn **null label** là một label không được gán, không phải chuỗi literal **"null"**. Một chiến lược có thể:

- Null label: default dùng chung.
- dev/staging/prod: override theo environment.
- Canary labels: chỉ khi có thiết kế selector/precedence rõ.
- Không dùng label động cho hàng triệu users/requests.

**Cảnh báo precedence:** việc tải nhiều selectors và override phụ thuộc library/configuration; cần kiểm thử explicit thứ tự loading và conflict resolution. Không mặc định “label prod” tự override null label nếu integration chưa cấu hình như vậy.

### 5.3. Content type

Content type phân biệt text thuần và dữ liệu có cấu trúc:

~~~text
text/plain
application/json
application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8
application/vnd.microsoft.appconfig.ff+json;charset=utf-8
~~~

Các MIME strings thể hiện các kiểu thường dùng; cần kiểm tra supported syntax theo API/library hiện hành.

### 5.4. Tags, ETag, last modified

Tags hỗ trợ metadata vận hành như owner và classification, không thay thế access controls. **ETag** là dấu phiên bản để thực hiện thao tác cập nhật có điều kiện/optimistic concurrency khi SDK/API cho phép. Last modified giúp điều tra thay đổi, nhưng **không phải** giao thức atomic deployment cho toàn bộ 20 keys.

### 5.5. Snapshot

**Snapshot** lưu một tập key-values đã chọn tại một thời điểm theo tính năng App Configuration, có thể giúp đảm bảo application lấy một bộ cấu hình nhất quán và có nguồn gốc triển khai rõ. Snapshot là **immutable collection** theo semantics dịch vụ; cách tạo, archive, revoke, giới hạn và billing phải kiểm tra trong phiên bản đang sử dụng.

Không nhầm:

- Snapshot của App Configuration với backup toàn bộ Azure resource.
- Snapshot với một Git commit chứa secret.
- Snapshot với feature flag rollout đang thay đổi động.

## 6. Naming convention, môi trường và ownership

Một ví dụ tổ chức:

~~~text
Application = orders
Environment = dev | staging | prod

Keys:
    orders:checkout:timeout-ms
    orders:checkout:retry-count
    orders:ui:page-size
    orders:payments:endpoint-url
    orders:sentinel

Feature names:
    new-checkout
    shipping-preview

Labels:
    <null>     defaults
    dev        dev overrides
    staging    preprod test
    prod       production overrides
~~~

### 6.1. Một store hay nhiều stores?

| Mô hình | Ưu điểm | Nhược điểm |
|---|---|---|
| Một store chung và labels theo environment | Chi phí/quản trị đơn giản, reuse default | Blast radius lớn nếu permissions sai |
| Store riêng cho dev/staging/prod | Tách boundary, network và RBAC rõ | Nhiều resources, chi phí/vận hành tăng |
| Store riêng theo business domain/application | Ownership và blast radius rõ | Cross-app defaults cần quản lý |
| Store riêng theo tenant | Isolation tốt trong một số tình huống | Bùng nổ số resources và complexity |

**Label không tự là ranh giới an toàn.** Nếu một principal có quyền data-reader trên toàn store, đừng mặc định nó chỉ đọc label prod mà không đọc staging. Khi phân tách dữ liệu có yêu cầu bảo mật mạnh, cần thiết kế **store/RBAC scopes** thích hợp, không dựa vào naming convention.

### 6.2. Chọn quyền sở hữu

- Product team sở hữu business configuration và feature rollout.
- Platform team sở hữu store, identity, network, capacity và IaC.
- Security team xác định secret classification, access reviews và audit.
- SRE/operations chịu trách nhiệm refresh SLO, runbooks và alerting.
- CI/CD pipelines có quyền ghi đúng scope, được review.
- Application workload chỉ có quyền **read**, không tự sửa production config.

## 7. Feature flags khác với config thông thường

**Feature flag** biểu diễn khả năng bật/tắt tính năng hoặc triển khai có điều kiện, ví dụ **new-checkout**, chứ không chỉ là một boolean config cố định.

### 7.1. Các kiểu quyết định

- **Boolean on/off:** bật hoặc tắt toàn bộ.
- **Time window:** chỉ bật trong khoảng thời gian có điều kiện.
- **Targeting:** bật theo nhóm/user hoặc phần trăm nếu feature management library hỗ trợ.
- **Canary release:** bật cho một nhóm nhỏ trước.
- **Kill switch:** có thể tắt một tính năng mới khi metrics xấu.

Việc hỗ trợ filters, percentage rollout, targeting và feature usage analytics phụ thuộc App Configuration + Feature Management library/version và application context cung cấp. Một flag không tự biết **userId** hay nhóm quyền nếu backend không truyền context.

### 7.2. Ví dụ feature flag

Một key-value feature flag có cấu trúc mang **id, enabled, conditions**:

~~~json
{
  "id": "new-checkout",
  "description": "Checkout flow thử nghiệm",
  "enabled": true,
  "conditions": {
    "client_filters": []
  }
}
~~~

Đây là payload **minh họa** về cấu trúc. Trong thực hành, nên tạo/sửa qua Azure Portal hoặc Feature Management SDK/CLI tương thích để tránh sai content type/schema.

### 7.3. Cẩn thận với flag

- Flag **không thay authorization**: dù nút UI bị ẩn, API vẫn phải kiểm tra quyền.
- Kill switch có độ trễ refresh; không bảo đảm ngắt ngay trong mili-giây.
- Rollout theo phần trăm cần bucketing ổn định để user không bị chuyển trạng thái liên tục giữa requests.
- Flags cũ cần được xóa sau rollout để giảm technical debt.
- Khi feature phụ thuộc schema/database migration, flag off không tự rollback database.
- Flag không được dùng để che lộ dữ liệu nhạy cảm hoặc bỏ qua policy bắt buộc.

## 8. Bootstrap và thứ tự nguồn cấu hình trong Spring Boot

Spring Boot có **Environment** kết hợp các PropertySources, ví dụ application.yml, environment variables, system properties, command-line arguments và các nguồn thêm bằng integration library.

### 8.1. Bootstrap là vấn đề hai giai đoạn

Để đọc App Configuration, ứng dụng trước tiên cần có **endpoint và credentials**. Nhưng chúng không thể chỉ nằm trong một App Configuration store chưa kết nối được.

Một thiết kế phổ biến:

~~~text
Bootstrap / application config:
    APP_CONFIG_ENDPOINT
    identity method
    selectors/labels
    refresh/failure policy

Azure App Configuration:
    orders:checkout:timeout-ms
    orders:ui:page-size
    feature flags
    Key Vault reference metadata

Azure Key Vault:
    payment API key / legacy secret values
~~~

**Endpoint URI không phải secret**. Nếu dùng connection string của App Configuration, connection string có thể mang credentials, phải lưu và truyền qua cơ chế secret an toàn. Với Azure workloads, **managed identity + endpoint** thường là lựa chọn nên ưu tiên.

### 8.2. Spring Cloud Azure integration

Spring Cloud Azure App Configuration starter có thể thêm **PropertySource** vào Spring Environment, cung cấp binding và refresh patterns. Tuy nhiên:

- Property names và bootstrap mechanism khác nhau theo **Spring Boot major version, Spring Cloud Azure version và Spring Cloud compatibility**.
- Tài liệu một version có thể sử dụng **bootstrap.yml**, trong khi version khác có cơ chế **spring.config.import** hoặc bootstrap starter tương ứng.
- Không copy config keys của một thế hệ thư viện vào project khác mà không đối chiếu version matrix.
- SDK low-level không tự biến key-values thành Spring properties; đó là trách nhiệm integration layer hoặc code tự viết.

### 8.3. Precedence phải kiểm thử

Giả sử cùng một property tồn tại ở application.yml, environment variable và App Configuration. Giá trị cuối cùng tùy thứ tự PropertySources và naming/binding rules.

Đặt một integration test xác nhận:

1. Default local config được nạp.
2. App Configuration null-label keys được nạp.
3. Label môi trường (prod) override đúng key.
4. Có hoặc không cho phép environment override theo policy.
5. Khi một source lỗi, fallback có chủ đích, không silently dùng unsafe default.

Không khẳng định một thứ tự ưu tiên chung cho mọi bản Spring Boot/Spring Cloud Azure.

## 9. Chọn công cụ Java cho App Configuration

| Cách triển khai | Khi phù hợp | Cần lưu ý |
|---|---|---|
| **Azure SDK for Java: azure-data-appconfiguration** | Muốn tự quản lý key-values, retrieval và caching | Phải tự map sang Spring config/refresh |
| **Spring Cloud Azure App Configuration starter** | Spring Boot cần binding vào Environment | Theo version compatibility |
| **Feature Management library** | Feature flags/targeting/conditional gates | Context/filters và refresh |
| **Azure Portal/CLI** | Operator tạo key-values và triển khai lab | Đúng role, audit, network |
| **IaC + release automation** | Quản lý store/labels/snapshots theo quy trình | Tách secret, drift detection |
| **Key Vault references** | Config trỏ tới secret được bảo vệ | Role/network tới Key Vault riêng |

Bài sẽ trình bày cả **SDK thấp tầng** (có API Java cụ thể) và **Spring Boot integration** (version-sensitive), để người học hiểu ranh giới tính năng thay vì tin rằng một starter sẽ tự xử lý mọi loại refresh/feature flag.

## 10. Lab Azure CLI: tạo store và cấu hình theo label

Các lệnh sau là **hướng dẫn**, không có Azure resource nào được tạo khi soạn bài. App Configuration có quota và phí tùy tier; dùng subscription lab, ngân sách và tên tài nguyên riêng.

### 10.1. Tạo store

~~~bash
az login
az account set --subscription "<lab-subscription-id>"

RG="rg-appconfig-spring-lab"
LOCATION="southeastasia"
STORE="<unique-appconfig-store-name>"

az group create --name "$RG" --location "$LOCATION"

az appconfig create \
  --name "$STORE" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku Standard

az appconfig show \
  --name "$STORE" \
  --resource-group "$RG" \
  --output table
~~~

**Standard** là lựa chọn lab minh họa, không phải khuyến nghị cho mọi tổ chức. Kiểm tra tier/region, features và cost hiện hành. Endpoint thường có dạng **https://store-name.azconfig.io**; endpoint không phải credential, còn connection string và access keys có thể chứa secrets.

### 10.2. Gán data-plane role

Các roles thường gặp:

| Role | Công dụng | Identity |
|---|---|---|
| **App Configuration Data Reader** | Đọc key-values/flags | Spring Boot runtime |
| **App Configuration Data Owner** | Ghi/quản lý key-values ở data plane | CI/CD/operator được duyệt |
| Azure resource Contributor | Quản lý resource ở control plane | Platform/IaC; không tự thay data-plane role |

Người có quyền tạo role assignment có thể cấp quyền ghi cho developer **chỉ trong lab**:

~~~bash
STORE_ID=$(az appconfig show \
  --name "$STORE" \
  --resource-group "$RG" \
  --query id --output tsv)

USER_ID=$(az ad signed-in-user show \
  --query id --output tsv)

az role assignment create \
  --assignee-object-id "$USER_ID" \
  --assignee-principal-type User \
  --role "App Configuration Data Owner" \
  --scope "$STORE_ID"
~~~

Tại production, cấp **Data Reader** cho managed identity của ứng dụng, không cấp Data Owner chỉ để đọc. Role propagation có thể cần thời gian; đừng vội nâng quyền rộng nếu nhận 403.

### 10.3. Tạo non-secret keys

Sử dụng dot-separated keys để dễ map với Spring Boot:

~~~bash
az appconfig kv set \
  --name "$STORE" --auth-mode login \
  --key "orders.checkout.timeout-ms" \
  --label "prod" --value "800" --yes

az appconfig kv set \
  --name "$STORE" --auth-mode login \
  --key "orders.checkout.retry-count" \
  --label "prod" --value "2" --yes

az appconfig kv set \
  --name "$STORE" --auth-mode login \
  --key "orders.ui.page-size" \
  --label "prod" --value "50" --yes

az appconfig kv set \
  --name "$STORE" --auth-mode login \
  --key "orders.checkout.timeout-ms" \
  --label "dev" --value "1500" --yes
~~~

Các options CLI phụ thuộc phiên bản extension; kiểm tra **az appconfig kv set --help** trước khi automation. **--auth-mode login** giúp CLI dùng Microsoft Entra identity thay vì lấy access key.

### 10.4. Xem giá trị demo và labels

~~~bash
az appconfig kv show \
  --name "$STORE" --auth-mode login \
  --key "orders.checkout.timeout-ms" \
  --label "prod" \
  --query "{key:key,label:label,value:value}" \
  --output json
~~~

Ở đây giá trị **800** không nhạy cảm. Không ghi/lấy ra terminal những values chứa API key thật. Với null label, việc bỏ tham số label có semantics riêng; không sử dụng chuỗi **"null"** thay null label.

### 10.5. Feature Manager và snapshots trong Portal

Trong Azure Portal, mở store:

1. **Configuration Explorer:** tạo key-values và labels.
2. **Feature Manager:** tạo flag **new-checkout**, kiểm tra conditional targeting nếu feature version hỗ trợ.
3. **Snapshots:** tạo bộ cấu hình snapshot được review nếu tier/tính năng hỗ trợ.
4. **Access control (IAM):** gán data-reader role cho runtime identity.
5. **Networking:** áp public firewall hoặc Private Endpoint theo policy.
6. **Diagnostic settings:** bật logs/metrics cần thiết.

Không tự giả định một command preview tạo snapshot/feature flag chạy trên mọi CLI version; có thể dùng Portal để kiểm tra rồi chuyển thành automation có kiểm thử.

## 11. Java SDK thấp tầng: azure-data-appconfiguration

Khi cần đọc một key theo yêu cầu hoặc tự điều phối cache/refresh, dùng **ConfigurationClient** từ **com.azure:azure-data-appconfiguration** và **TokenCredential** từ **com.azure:azure-identity**.

### 11.1. Maven dependencies

~~~xml
<dependencies>
  <!-- Quản lý versions bằng Azure SDK BOM hoặc pin bản được duyệt. -->
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-data-appconfiguration</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
  </dependency>
</dependencies>
~~~

Đây là **POM fragment**, cần Azure SDK BOM/explicit versions và các phần còn lại của Maven project. **Azure SDK low-level không tự thêm PropertySource vào Spring Environment**; đó là phần tích hợp riêng.

### 11.2. Java đọc key có label

~~~java
package com.example.orders.config;

import com.azure.core.credential.TokenCredential;
import com.azure.data.appconfiguration.ConfigurationClient;
import com.azure.data.appconfiguration.ConfigurationClientBuilder;
import com.azure.data.appconfiguration.models.ConfigurationSetting;
import com.azure.identity.DefaultAzureCredentialBuilder;

public final class AppConfigReadDemo {
    public static void main(String[] args) {
        String endpoint = System.getenv("APP_CONFIG_ENDPOINT");
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException(
                "APP_CONFIG_ENDPOINT is required");
        }

        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        ConfigurationClient client =
            new ConfigurationClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .buildClient();

        ConfigurationSetting setting =
            client.getConfigurationSetting(
                "orders.checkout.timeout-ms", "prod");

        String value = setting.getValue();
        int timeoutMs = Integer.parseInt(value);

        if (timeoutMs < 100 || timeoutMs > 10000) {
            throw new IllegalStateException(
                "Checkout timeout out of permitted range");
        }

        // Chỉ in cấu hình demo không nhạy cảm.
        System.out.println("Configured timeout: " + timeoutMs);
    }
}
~~~

Lưu ý:

- **DefaultAzureCredential** lựa chọn credential source theo SDK/runtime; local Azure CLI account có thể khác managed identity của Azure workload.
- Chỉ identity có **Data Reader** ở đúng scope và networking phù hợp mới gọi được.
- Java xử lý parsing/validation; không xem value string là dữ liệu đã an toàn.
- Cần xử lý lỗi 401/403/404/429 và timeout ở production.
- Client nên được tái sử dụng thay vì tạo trên mỗi HTTP request.
- Không in values bí mật và không đưa một admin connection string vào source.

### 11.3. Liệt kê một prefix

~~~java
import com.azure.data.appconfiguration.models.SettingSelector;
import com.azure.data.appconfiguration.models.ConfigurationSetting;

SettingSelector selector = new SettingSelector()
    .setKeyFilter("orders.*")
    .setLabelFilter("prod");

for (ConfigurationSetting item :
        client.listConfigurationSettings(selector)) {
    // Kiểm tra metadata; không log toàn bộ values.
    String key = item.getKey();
    String label = item.getLabel();
    System.out.println("Loaded metadata for key " + key);
}
~~~

Mẫu dùng biến **client** đã tạo trước đó. Query có thể phân trang và phát sinh nhiều requests. Không list toàn bộ store ở mỗi HTTP request. Lưu ý tên key cũng có thể nhạy cảm trong một tổ chức.

### 11.4. Chỉnh key-value trong operator tool

~~~java
import com.azure.data.appconfiguration.models.ConfigurationSetting;

ConfigurationSetting item = new ConfigurationSetting()
    .setKey("orders.checkout.timeout-ms")
    .setLabel("dev")
    .setValue("1500");

client.setConfigurationSetting(item);
~~~

**Chỉ operator/CI identity có Data Owner** được làm việc này với store phù hợp. Khi nhiều writers có thể cập nhật cùng một key, cân nhắc **ETag-based conditional writes**/optimistic concurrency theo SDK để tránh ghi đè ngoài ý muốn.

## 12. Spring Cloud Azure App Configuration starter

Đối với Spring Boot, tích hợp ở tầng **Spring Environment** giúp cấu hình binding với **@ConfigurationProperties**. Cần pin cả ba nhóm versions:

- Spring Boot.
- Spring Cloud/Spring Cloud Azure release train.
- Java và Azure SDK dependencies.

Các property names và bootstrap patterns có thể khác nhau theo thế hệ. Không xem một mẫu trên internet như config đảm bảo chạy trên mọi bản Spring Boot.

### 12.1. Maven BOM pattern

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure.spring</groupId>
      <artifactId>spring-cloud-azure-dependencies</artifactId>
      <version>REPLACE_WITH_COMPATIBLE_RELEASE</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-appconfiguration-config</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
</dependencies>
~~~

Đây là **pom fragment**: cần Spring Boot parent/dependency management và thay placeholder bằng release tương thích được kiểm chứng trong version matrix của Microsoft. Không giả vờ Maven chạy với placeholder.

### 12.2. Mẫu cấu trúc cấu hình

Một cấu trúc Spring Cloud Azure App Configuration thường dùng:

~~~yaml
# Pattern minh họa: kiểm tra tên thuộc tính/activation của version đang dùng.
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "https://example-appconfig.azconfig.io"
            selects:
              - key-filter: "orders.*"
                label-filter: "prod"
~~~

Trong triển khai thật, endpoint và label được truyền từ app deployment, ví dụ **APP_CONFIG_ENDPOINT** và **APP_CONFIG_LABEL**. Các release có thể nạp sớm qua **bootstrap.yml**, **spring.config.import** hoặc cơ chế bootstrap starter thích hợp; phải đọc **versioned reference**, không trộn hai phương thức ngẫu nhiên.

### 12.3. Chọn label theo environment

Một chiến lược:

~~~text
APP_CONFIG_ENDPOINT = https://<your-store>.azconfig.io
APP_CONFIG_LABEL    = dev | staging | prod
APP_CONFIG_PREFIX   = orders.
~~~

Cấu hình bootstrap phải lấy label từ deployment environment hoặc profile đã được cho phép. Với production, **thiếu label prod phải fail validation**, không âm thầm rơi về dev.

### 12.4. Dấu phân cách của key trong Spring

Để bind trực tiếp thành fields như **timeoutMs**, nên chọn keys **orders.checkout.timeout-ms**. Những ví dụ khác dùng colon **orders:checkout:timeout-ms** có thể yêu cầu key transformation/trimming; không giả định Spring starter tự động đổi colon thành dot.

### 12.5. Kiểm thử precedence

Khi cùng một property tồn tại ở application.yml, environment variable và App Configuration, thứ tự ưu tiên phụ thuộc Spring PropertySources và integration library. Thêm integration test xác minh:

1. Local fallback nào được phép.
2. Null-label defaults có được tải không.
3. Environment label prod/staging override như mong đợi.
4. Environment variable có quyền override remote config hay không.
5. Khi remote store lỗi, app fail-fast hay tiếp tục dùng last-known-good.

**Không công bố một thứ tự precedence phổ quát** cho mọi Spring Boot/Spring Cloud Azure version.

## 13. @ConfigurationProperties: cấu hình có kiểu và kiểm tra

### 13.1. Từ key-values thành Java bean

Với những keys:

~~~text
orders.checkout.timeout-ms = 800
orders.checkout.retry-count = 2
~~~

Bean:

~~~java
package com.example.orders.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "orders.checkout")
public class CheckoutProperties {
    @Min(100)
    @Max(10000)
    private int timeoutMs = 800;

    @Min(0)
    @Max(5)
    private int retryCount = 1;

    public int getTimeoutMs() { return timeoutMs; }
    public void setTimeoutMs(int value) { this.timeoutMs = value; }

    public int getRetryCount() { return retryCount; }
    public void setRetryCount(int value) { this.retryCount = value; }
}
~~~

Đăng ký bằng **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties**:

~~~java
package com.example.orders;

import com.example.orders.config.CheckoutProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(CheckoutProperties.class)
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

### 13.2. Dùng typed configuration

~~~java
package com.example.orders.service;

import com.example.orders.config.CheckoutProperties;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final CheckoutProperties config;

    public CheckoutService(CheckoutProperties config) {
        this.config = config;
    }

    public int configuredTimeoutMs() {
        return config.getTimeoutMs();
    }
}
~~~

Ví dụ nhấn mạnh strongly typed config, không chứa implementation của HTTP client. Nếu timeout thay đổi, cần xác minh bean/client thực sự đọc property mới hoặc được rebuild; một HTTP connection pool đã tạo có thể vẫn giữ timeout cũ.

### 13.3. Validation khi startup và refresh

- Chỉ cho timeout trong khoảng an toàn.
- Retry count phải bounded, nhất là khi payment POST không idempotent.
- Endpoint URL phải được kiểm tra scheme/host whitelist.
- Missing required critical setting nên fail startup nếu không có fallback được phê duyệt.
- Khi refresh, **cũng phải kiểm tra** giá trị mới trước khi áp dụng cho live traffic.
- Dùng integration tests vì binding/refresh semantics phụ thuộc starter version.

## 14. Default label, overrides và blast radius

Một policy minh họa:

~~~text
orders.checkout.timeout-ms [no label] = 1000
orders.checkout.timeout-ms [dev]      = 1500
orders.checkout.timeout-ms [staging]  = 1100
orders.checkout.timeout-ms [prod]     = 800
~~~

Cách nạp defaults rồi overrides cần selectors và precedence được cấu hình rõ, **không có nghĩa App Configuration tự ưu tiên prod** nếu caller không chỉ định label.

**Label không phải security boundary.** Một data reader ở store scope có thể được đọc nhiều labels theo role. Nếu quyền truy cập dev/prod cần cách ly mạnh, cân nhắc store riêng, identity và network riêng, thay vì hy vọng tên label sẽ chặn người đọc.

Khi production thiếu giá trị quan trọng, chọn fail-safe behavior. Không dùng default dev như một fallback không được báo cáo.

## 15. Làm mới cấu hình khi ứng dụng đang chạy

Điểm mạnh của App Configuration là có thể quản lý giá trị tập trung **không cần rebuild JAR**, nhưng **dynamic refresh** là một quy trình nhiều bước:

~~~mermaid
sequenceDiagram
    participant O as Operator / CI
    participant AC as App Configuration
    participant REF as App refresh monitor
    participant SPR as Spring Environment
    participant B as Business bean
    O->>AC: Update key-values
    O->>AC: Update sentinel last
    REF->>AC: Poll/check trigger after interval
    AC-->>REF: Changed ETag/setting
    REF->>AC: Reload selected configuration
    AC-->>REF: New values
    REF->>SPR: Update PropertySources
    SPR->>B: Rebind/recreate only if supported
    B-->>B: New behavior after validation
~~~

**Không giả định** App Configuration gửi một push trực tiếp và ngay lập tức tới mọi JVM. Refresh thường được kiểm tra qua một hoạt động của application/library, với minimum refresh interval, selected keys và caching tùy phiên bản. Một instance ít traffic có thể áp dụng thay đổi chậm hơn khi cơ chế refresh chỉ được kích hoạt bởi requests.

### 15.1. Những thời điểm cần phân biệt

| Mốc | Nghĩa |
|---|---|
| **SettingUpdated** | Operator/CI đã ghi App Configuration |
| **SentinelUpdated** | Hệ thống có tín hiệu một bộ thay đổi đã hoàn tất |
| **RefreshChecked** | Một instance kiểm tra thay đổi theo policy |
| **PropertySourceUpdated** | Remote values đã được nạp vào Spring Environment |
| **BeanApplied** | Component Java thực sự đang dùng giá trị mới |
| **BusinessMetricVerified** | Hệ thống đo được hành vi sau thay đổi đúng SLO |

Chỉ biết CLI **kv set** trả success không chứng minh mọi instance đã áp dụng cấu hình.

### 15.2. Sentinel key

Giả sử muốn thay ba settings cùng lúc:

~~~text
orders.checkout.timeout-ms [prod] = 800
orders.checkout.retry-count [prod] = 2
orders.ui.page-size [prod]        = 50
orders.settings.revision [prod]    = "2026-11-20-release-1"
~~~

Khi triển khai revision mới:

1. Tạo/ghi các key-values liên quan.
2. Validate inputs, type/range và dependencies.
3. **Cập nhật sentinel cuối cùng** sau khi toàn bộ dữ liệu đã sẵn sàng.
4. Instances kiểm tra sentinel theo polling policy.
5. Khi sentinel thay đổi, refresh selected configuration.
6. Validate và áp dụng đến beans có cơ chế refresh.
7. Theo dõi revision mà từng instance đã áp dụng.

Sentinel giúp giảm khả năng client nhìn thấy thay đổi từng key rời rạc, nhưng **không tự tạo ACID transaction across all clients/instances**. Với cấu hình yêu cầu snapshot nhất quán tuyệt đối, cân nhắc **immutable snapshot + explicit promotion** và readiness gating.

### 15.3. Refresh interval và quota

Mẫu khái niệm cấu hình refresh:

~~~yaml
# Pseudoconfiguration: property names và bootstrap source
# PHẢI xác nhận theo Spring Cloud Azure release đã chọn.
app-config-refresh-policy:
  store: "orders-appconfig"
  environment-label: "prod"
  enabled: true
  sentinel-key: "orders.settings.revision"
  min-check-interval: "30s"
  change-behavior: "reload-selected-keys"
~~~

Đây **không phải** namespace cấu hình của Spring Cloud Azure starter, không copy nguyên vào application.yml để kỳ vọng starter xử lý. Nó nêu các biến cần tìm trong documentation của release: **monitoring.enabled**, **triggers**, **refresh-interval**, **watch keys** và cách kích hoạt refresh.

Nếu muốn sử dụng trực tiếp starter configuration, kiểm tra các thuộc tính dạng:

~~~text
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled
spring.cloud.azure.appconfiguration.stores[0].monitoring.triggers[0].key
spring.cloud.azure.appconfiguration.stores[0].monitoring.refresh-interval
~~~

**Cảnh báo tương thích:** tên thuộc tính, cấu trúc selects/triggers và cách refresh thực thi là **version-sensitive**; không xem các dòng trên như cấu hình đã kiểm thử. Tham khảo versioned Spring Cloud Azure docs và thêm integration test trên chính release được pin.

### 15.4. RefreshScope và bean lifecycle

Trong một số cấu hình Spring Cloud, **@RefreshScope** cho phép tái tạo bean khi có refresh signal. Ví dụ Spring Cloud Context nếu dependency đã được cài đặt:

~~~java
package com.example.orders.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class DynamicCheckoutTimeout {
    private final int timeoutMs;

    public DynamicCheckoutTimeout(
        @Value("${orders.checkout.timeout-ms}") String rawSetting) {
        // Đọc từ Spring Environment tại thời điểm tạo bean.
        this.timeoutMs = Integer.parseInt(rawSetting);
    }

    public int timeoutMs() {
        return timeoutMs;
    }
}
~~~

**Lưu ý:** ví dụ dùng cú pháp placeholder **@Value** của Spring. Nó cần Spring Cloud Context có hỗ trợ **@RefreshScope**, một nguồn giá trị đã nạp và cơ chế kích hoạt refresh tương ứng. Mẫu chưa chứng minh starter sẽ tự phát refresh signal; hãy xác minh **PropertySources và refresh context** trên release cụ thể. Có thể thay bằng **CheckoutProperties** nếu project dùng binding typed settings.

Một cách dễ kiểm soát hơn trong hệ thống nhạy cảm là một **ConfigSnapshot** bất biến được validate, sau đó cập nhật vào **AtomicReference**:

~~~java
package com.example.orders.config;

public record ConfigSnapshot(int timeoutMs, int retryCount,
                             String revision) {
    public ConfigSnapshot {
        if (timeoutMs < 100 || timeoutMs > 10000) {
            throw new IllegalArgumentException("timeoutMs");
        }
        if (retryCount < 0 || retryCount > 5) {
            throw new IllegalArgumentException("retryCount");
        }
    }
}
~~~

~~~java
package com.example.orders.config;

import java.util.concurrent.atomic.AtomicReference;

public final class DynamicConfig {
    private final AtomicReference<ConfigSnapshot> current;

    public DynamicConfig(ConfigSnapshot initial) {
        this.current = new AtomicReference<>(initial);
    }

    public ConfigSnapshot snapshot() {
        return current.get();
    }

    public void installValidated(ConfigSnapshot candidate) {
        // Candidate đã validate trong record constructor.
        // Mỗi request có thể giữ một snapshot nhất quán.
        current.set(candidate);
    }
}
~~~

Mô hình này làm rõ ranh giới **“nạp một bộ cấu hình mới” → “đổi reference atomically trong process”**. Nhưng nhiều JVM instances vẫn áp dụng ở thời điểm khác nhau; muốn coordination across instances cần protocol/rollout strategy riêng.

### 15.5. Tác động lên HTTP client và resources

Một timeout mới chưa chắc ảnh hưởng tới một **WebClient/RestClient/connection pool** đã được tạo trước đó:

- Nếu timeout được đọc trên mỗi call qua config holder → có thể có hiệu lực ngay.
- Nếu HTTP client được xây ở startup với timeout cũ → cần recreate hoặc điều chỉnh connector theo API.
- Khi thay endpoint/base URL, phải cân nhắc in-flight requests.
- Khi thay DB pool size, chỉ đổi property không bảo đảm pool tự resize.
- Thay đổi quan trọng cần canary/rolling restart nếu hot refresh khó xác minh.

## 16. Kiểm soát tính nhất quán của nhiều key-values

### 16.1. Rủi ro partial update

Một hệ thống đang có:

~~~text
orders.checkout.endpoint = https://partner-v1.example
orders.checkout.api-version = v1
~~~

Operator đổi endpoint trước rồi đổi version sau. Một instance refresh ở giữa có thể dùng **endpoint v2 + api-version v1**, gây lỗi.

### 16.2. Chiến lược A: sentinel update last

Ưu điểm: đơn giản, phù hợp thay đổi có thể refresh cuối đợt. Giới hạn: các key-values vẫn được ghi từng cái; một ứng dụng bỏ qua sentinel hoặc refresh trigger khác có thể nhìn partial state.

### 16.3. Chiến lược B: immutable snapshot

Tạo snapshot đã validate và promote một tham chiếu snapshot/revision duy nhất cho ứng dụng, dùng khi feature/tier hỗ trợ.

~~~text
snapshot orders-prod-2026-11-20-r1
    endpoint v2
    api-version v2
    checkout timeout 800ms

release manifest references snapshot r1
~~~

Ứng dụng tải một collection nhất quán cho một release, sau đó canary chuyển sang r2. Snapshot có thể làm giảm flexibility của dynamic updates, nhưng tăng reproducibility/rollback.

### 16.4. Chiến lược C: typed JSON document

Thay vì 5 keys độc lập, có thể lưu một JSON config object và validate toàn bộ trước khi atomic swap trong process:

~~~json
{
  "endpoint": "https://partner.example.invalid",
  "apiVersion": "v2",
  "timeoutMs": 800,
  "retryCount": 2,
  "revision": "orders-checkout-r2"
}
~~~

Tuy nhiên, JSON chunk lớn làm giảm khả năng override từng property/label và có thể phức tạp hơn với Spring binding. Chỉ chọn khi cần **atomic unit** và đã có schema/version migration.

### 16.5. Rollback

Không chỉ “ghi lại timeout cũ” mà phải biết **tập các keys** và release nào đã được áp dụng. Có thể dùng snapshot, versioned release manifest hoặc IaC source-of-truth để rollback nhất quán.

## 17. Feature flags trong Spring Boot

### 17.1. Một Boolean configuration không bằng feature-management framework

Nếu chỉ cần một công tắc đơn giản:

~~~text
orders.checkout.new-flow-enabled [prod] = false
~~~

Spring có thể bind boolean và controller/service kiểm tra giá trị. Tuy nhiên cách này **không có** targeting, percentage rollout, scheduling hoặc experiment auditing đầy đủ.

Với một **feature flag thực thụ**, App Configuration Feature Manager định nghĩa flag và điều kiện; Spring Cloud Azure Feature Management package/library thực thi filters theo phiên bản.

### 17.2. Quy trình rollout

~~~mermaid
flowchart TD
    DEV["Deploy code: old + new paths"] --> FLAG["Create flag: new-checkout"]
    FLAG --> QA["Enable for QA / dev"]
    QA --> CANARY["Canary subset / percentage"]
    CANARY --> METRIC["Measure errors, latency, conversion"]
    METRIC --> DEC{"SLO acceptable?"}
    DEC -->|Yes| EXPAND["Expand to more users"]
    DEC -->|No| OFF["Disable feature flag"]
    EXPAND --> CLEAN["Remove flag after rollout"]
~~~

**Tắt flag** có độ trễ phụ thuộc refresh mechanism và implementation. Không cam kết “kill switch dưới 1 giây” nếu hệ thống chỉ refresh mỗi 60 giây.

### 17.3. Feature context và targeting

Để chọn user/group:

- Backend phải có userId từ authenticated session.
- Tên group/role lấy từ validated identity/authorization data.
- Percentage bucketing cần ổn định cho cùng user để tránh chập chờn.
- Việc user được bật tính năng **không cấp quyền** xem tài liệu hoặc thực hiện API nhạy cảm.
- Mọi server-side route vẫn phải enforce authorization.

### 17.4. Đừng ràng buộc schema migration vào flag đơn giản

Nếu tính năng checkout mới thay DB schema không backward-compatible, chỉ tắt flag chưa chắc rollback được. Dùng **expand–migrate–contract** hoặc migration tương thích ngược, rồi rollout có kiểm soát.

### 17.5. Testing

Phải kiểm thử:

1. Flag không tồn tại → default an toàn.
2. Flag disabled → old path.
3. Flag enabled → new path.
4. Target group không có quyền → không được xử lý nhầm.
5. Flag refresh chậm → app có trạng thái transition rõ.
6. Hai instances nhận flag ở thời điểm khác nhau → không phá giao thức.
7. Cleanup flag sau release kết thúc.

## 18. Key Vault references: cấu hình và bí mật là hai dịch vụ

### 18.1. Tại sao không để API key trong App Configuration?

Nếu lưu plain value:

~~~text
orders.payment.api-key = REAL_PAYMENT_API_KEY
~~~

Thì principal đọc App Configuration có thể đọc credential, và các lệnh dump configuration hoặc config response dễ làm rò. Điều này trái nguyên tắc secret isolation.

Thay bằng **Key Vault reference**:

~~~text
App Configuration key:
    orders.payment.api-key

Content type:
    application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8

Value (reference JSON):
    {"uri":"https://<vault-name>.vault.azure.net/secrets/orders-payment-key/"}
~~~

**App Configuration lưu URI tham chiếu, không lưu bản secret plaintext.** Nhưng URI/secret name cũng có thể tiết lộ metadata và cần bảo vệ khỏi log không cần thiết.

### 18.2. Luồng lấy secret

~~~mermaid
sequenceDiagram
    participant APP as Spring Boot
    participant AC as App Configuration
    participant ID as Entra Identity
    participant KV as Key Vault
    APP->>ID: Acquire credentials
    APP->>AC: Read key-value reference
    AC-->>APP: Key Vault reference URI
    APP->>KV: Resolve secret with allowed identity
    KV-->>APP: Secret value
    APP->>APP: Use secret in server-side component
~~~

Luồng này là mô hình: việc resolve được thực hiện bởi integration layer nếu có, hoặc code riêng khi dùng SDK trực tiếp.

### 18.3. Cần hai nhóm quyền

| Service | Quyền data plane | Công dụng |
|---|---|---|
| App Configuration | **App Configuration Data Reader** | Đọc reference key-values |
| Key Vault | **Key Vault Secrets User** hoặc get permission theo model | Lấy secret value |
| Microsoft Entra ID | Workload identity hợp lệ | Lấy tokens phù hợp cho cả hai |
| Networking | Route + firewall/private endpoint/DNS | Kết nối HTTPS tới cả hai |

**Data Reader trên App Configuration không tự cấp quyền đọc Key Vault**. Và Key Vault Secrets User không cho phép đọc App Configuration.

### 18.4. SDK low-level không tự resolve reference

Khi gọi **ConfigurationClient.getConfigurationSetting** cho một setting kiểu Key Vault reference, SDK low-level trả **ConfigurationSetting** với content type và JSON reference, **không tự biến JSON thành secret value**.

Muốn dùng secret:

- Tích hợp **Spring Cloud Azure App Configuration Key Vault reference resolution** nếu release hỗ trợ và cấu hình rõ.
- Hoặc parse reference URI một cách an toàn và dùng **SecretClient** từ azure-security-keyvault-secrets với quyền riêng.
- Không tạo credential có quyền rộng hay chấp nhận arbitrary URI từ untrusted user.
- Validate allowed vault hosts/tenant/environment để tránh request tới vault không mong muốn.

### 18.5. Secret rotation và refresh có hai vòng đời

- App Configuration reference có thể vẫn trỏ tới **versionless Key Vault URI**.
- Key Vault tạo version mới.
- Spring integration hoặc app cache có thể chưa refresh secret.
- TokenCredential caching không đồng nghĩa secret value caching.
- Nếu pinned version URI, app có thể tiếp tục dùng version cũ.
- Rotation còn yêu cầu thay credential ở hệ thống đối tác.

Đặt SLO riêng cho **config refresh** và **secret rotation propagation**. Không đánh đồng hai cơ chế.

### 18.6. Xử lý lỗi Key Vault

Nếu App Configuration thành công nhưng Key Vault trả 403, cần kiểm tra **Key Vault role/network**, không cấp thêm App Configuration Data Owner. Có thể policy chọn fail startup, giữ last-known-good ngắn hạn hoặc disable route phụ thuộc secret; không hard-code backup secret trong code.

## 19. Authentication và authorization bằng Microsoft Entra ID

### 19.1. Local development

Ở máy lập trình viên:

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
az account show --output table
~~~

Trong Java, **DefaultAzureCredential** có thể dùng developer identity từ Azure CLI hoặc những sources khác theo thứ tự chain được SDK version xác định. Nếu environment có nhiều credential variables hoặc IDE accounts, principal thật có thể không phải người bạn vừa đăng nhập qua az login.

**Có token Entra chưa đủ:** identity phải có **App Configuration Data Reader** (hoặc role phù hợp) trên store và được network cho phép.

### 19.2. App Service system-assigned identity

Quy trình:

1. Bật system-assigned managed identity cho App Service.
2. Lấy **principal object ID** của managed identity (không nhầm với client ID).
3. Gán **App Configuration Data Reader** trên store hoặc scope được hỗ trợ.
4. Nếu dùng Key Vault reference, gán **Key Vault Secrets User**/permission get tương ứng.
5. Thiết lập **APP_CONFIG_ENDPOINT** và environment label.
6. Kiểm tra outbound VNet routing, private DNS nếu store private.
7. Deploy Spring Boot app.
8. Verify identity principal, config loaded, refresh và audit logs.
9. Không đưa connection string vào Git hoặc App Service logs.

### 19.3. User-assigned managed identity

Khi một workload cần user-assigned identity hoặc nhiều identities, chỉ rõ **client ID** cho credential chain theo version/library support. Không gán role cho một principal rồi bảo ứng dụng dùng client ID của principal khác.

### 19.4. AKS workload identity

Trong AKS, ưu tiên **Microsoft Entra Workload ID** khi được tổ chức hỗ trợ:

- Kubernetes ServiceAccount có annotation/config đúng.
- Federated identity credential khớp issuer/subject/audience.
- Workload token được mount đúng và Azure Identity SDK đọc được.
- App Configuration role được gán cho Entra principal thật.
- Nếu dùng Key Vault reference, có thêm data-plane permission tại vault.
- Network tới cả hai endpoints hợp lệ.

Không nhúng static connection string vào image, ConfigMap hoặc một shared Kubernetes Secret chỉ để bỏ qua workload identity.

### 19.5. CI/CD writer khác runtime reader

| Principal | Quyền mục tiêu |
|---|---|
| App runtime identity | App Configuration Data Reader |
| CI/CD config promotion identity | App Configuration Data Owner theo phạm vi, chỉ khi được duyệt |
| IaC resource deployment principal | ARM resource create/manage, role assignment theo nhiệm vụ |
| Secret rotation identity | Key Vault secret write/management, không gộp vào app reader |
| Human operator | JIT/PIM và audit theo policy |

Một pipeline có quyền ghi config production có thể làm thay đổi hành vi nghiệp vụ diện rộng. Dùng approvals, branch protection, four-eyes review và log thay đổi.

## 20. Mạng: Private Endpoint, firewall và DNS

### 20.1. App Configuration endpoint vẫn là FQDN

Ứng dụng truy cập endpoint dạng:

~~~text
https://<store-name>.azconfig.io
~~~

Khi dùng **Private Endpoint**, DNS trong VNet phải phân giải hostname này sang private IP theo quy tắc Private Link. Private DNS zone liên quan thường là:

~~~text
privatelink.azconfig.io
~~~

Dùng đúng FQDN để TLS hostname/certificate validation hoạt động. **Không thay client endpoint bằng private IP** rồi tắt chứng thực certificate.

### 20.2. Sơ đồ luồng mạng

~~~mermaid
flowchart TB
    APP["Spring Boot app<br/>App Service / AKS"] --> DNS["VNet DNS resolver"]
    DNS --> PE["App Configuration Private Endpoint"]
    PE --> AC["Azure App Configuration"]
    APP --> EN["Microsoft Entra token endpoint"]
    APP --> KVPE["Key Vault Private Endpoint<br/>nếu dùng references"]
    KVPE --> KV["Azure Key Vault"]
    OBS["Azure Monitor"] -. "diagnostics" .-> AC
~~~

### 20.3. App Service VNet Integration khác App Service Private Endpoint

- **VNet Integration** cung cấp outbound path từ App Service vào VNet/tài nguyên riêng.
- **Private Endpoint của App Configuration** là endpoint private để application truy cập store.
- **Private Endpoint của App Service** là thiết lập inbound private access tới chính web app.
- Network security groups, route tables, Azure Firewall và DNS có vai trò riêng.

Đừng chỉ bật private endpoint ở App Configuration rồi giả định một App Service public không có VNet integration đã kết nối được.

### 20.4. Firewall deny và HTTP 403

Một 403 có thể xảy ra khi:

- Identity có token nhưng thiếu data-plane role.
- App đang dùng principal/tenant khác dự định.
- Store chọn auth method không khớp.
- Firewall/network policy từ chối request.
- Feature/tier không cho phép đường gọi.

Đọc error details, request ID, network diagnostics và principal. Không sửa bằng cách cấp Owner hoặc mở public access toàn internet.

### 20.5. Key Vault reference cần đường mạng thứ hai

App Configuration đọc được **reference URI** không bảo đảm lấy được secret. Cần thêm:

- Key Vault hostname/private DNS, thường liên quan **privatelink.vaultcore.azure.net**.
- Outbound network path tới Key Vault.
- Microsoft Entra token/Key Vault data-plane permission.
- Chế độ vault RBAC hoặc access policy đúng.
- Cơ chế secret refresh/cache/rotation riêng.

Một lỗi 403 từ **Key Vault** không được “sửa” bằng App Configuration Data Owner.

## 21. Startup failure và fallback policy

App Configuration là một remote dependency. Một Java workload có thể fail startup nếu:

- Store endpoint sai.
- Role assignment chưa propagate.
- Private DNS chưa hoạt động.
- Key-value quan trọng không tồn tại ở label đang chọn.
- Value không parse được thành kiểu Java.
- Key Vault reference bị lỗi quyền.
- Store hoặc network tạm không sẵn sàng.

### 21.1. Ba chiến lược

| Policy | Hành vi | Khi phù hợp |
|---|---|---|
| **Fail fast** | Từ chối startup khi critical config không tải được | Payment/authorization/security-critical app |
| **Use approved local defaults** | Chạy bằng defaults đã được review | Optional UX settings; không được làm lệch bảo mật |
| **Last-known-good** | Tạm dùng bản config được validate trước đó | App yêu cầu availability, có quy định stale window |

**Last-known-good** phải có policy về thời gian sống, phương thức lưu trữ an toàn và invalidation. Nó không tự động xuất hiện khi thư viện Spring Cloud Azure được cài; muốn có phải xác minh support hoặc tự thiết kế.

### 21.2. Fail-open nguy hiểm với security settings

Nếu **orders.checkout.fraud-check-enabled** không tải được, để mặc định false có thể dẫn đến bỏ qua kiểm tra bảo mật. Với cấu hình security-sensitive, **fail closed** hoặc một fallback an toàn đã được business duyệt tốt hơn.

### 21.3. Readiness khác liveness

Không đặt “gọi App Configuration GET” trong **liveness probe mỗi vài giây**. Khi store outage, toàn bộ pods có thể bị restart đồng thời, gây retry storm. Liveness đo process, readiness đo app đủ config/trạng thái để phục vụ route an toàn.

Nếu app đã có validated config và chính sách cho phép tiếp tục dùng trong một khoảng, có thể giữ readiness. Nếu không có critical config, readiness false/fail startup theo policy.

### 21.4. Refresh failure

Khi refresh thất bại:

1. Giữ validated active snapshot cũ nếu cho phép.
2. Ghi metric và sanitized diagnostics.
3. Retry theo budget/backoff.
4. Không publish partially parsed/invalid state.
5. Báo alert khi age của bản config vượt allowed stale SLO.
6. Khi hồi phục, kiểm tra cả sentinel và selected values.
7. Ghi revision mới đã áp dụng vào telemetry.

Không tự động reset config về default dev chỉ vì store unreachable.

## 22. Race conditions và nhiều instances

### 22.1. Các instance nhận thay đổi lệch nhau

~~~text
10:00:00 Operator cập nhật timeout trong store
10:00:10 Instance A refresh → timeout=1000ms
10:00:20 Instance B vẫn giữ 800ms
10:00:50 Instance B refresh → timeout=1000ms
~~~

Trong khoảng 40 giây, cùng một request có thể gặp hành vi khác nhau tùy load balancer. Nếu hệ thống không chịu được sự khác biệt, không dùng hot config refresh đơn thuần.

### 22.2. Các giải pháp khi cần nhất quán mạnh hơn

- Canary hoặc rolling deployment gắn với **immutable snapshot/version**.
- Tạm giữ một tính năng disabled cho tới khi mọi instances báo đã nạp revision.
- Release gate kiểm tra revision của các instances trong SLO.
- Chỉ thay config tương thích ngược, cho phép mixed versions.
- Với thông số cần atomic across whole system, dùng một điều phối/transaction protocol khác thay vì yêu cầu cache refresh tự đảm nhận.

### 22.3. Tránh stampede

Nếu 500 instances cùng kiểm tra store và Key Vault sau một sentinel update:

- Có thể tăng API operations/throttling.
- Dùng min refresh interval và jitter nếu SDK/library hỗ trợ.
- Giới hạn số concurrent refresh.
- Không chủ động refresh tất cả keys sau mỗi business request.
- Không lặp GET retry vô hạn khi bị 429.
- Dùng snapshots/versioning giúp giảm thay đổi quá dày.

### 22.4. ETag không làm nhiều keys trở thành transaction

ETag hỗ trợ compare-and-set trên một item/operation theo API. Nó **không tự bảo đảm** atomic update cho 20 key-values hoặc atomic rollout đến nhiều instances. Dùng sentinel/snapshot/release manifest và validation phù hợp.

## 23. Feature flag rollout có kiểm soát

### 23.1. Progressive delivery

Một kế hoạch:

| Giai đoạn | Audience | Tiêu chí tiếp tục |
|---|---|---|
| Dev | QA team | Functional tests pass |
| Staging | Staging accounts | Regression/performance pass |
| Canary 1 | 1% theo targeting ổn định | Error rate và payment failures không tăng |
| Canary 2 | 10–25% | Latency p95, conversion, retry có kiểm soát |
| Production | 100% | Dashboard và incident plan sẵn sàng |
| Cleanup | Xóa flag, xóa old code | Không còn phụ thuộc cũ |

Các tỷ lệ minh họa, không phải khuyến nghị rollout chung cho mọi nghiệp vụ.

### 23.2. User bucketing phải ổn định

Nếu percentage filter đánh giá mỗi request ngẫu nhiên, một user có thể nhảy giữa hai checkout flows. Sử dụng context có stable ID và thuật toán bucketing được library hỗ trợ. Đừng gửi PII thô trong logs/counters chỉ để tính targeting.

### 23.3. Audit flags

Ghi:

- Flag name, label/snapshot, revision.
- Thời điểm enable/disable.
- Actor/approval.
- Audience/targeting policy.
- Metrics trước/sau.
- Rollback instructions.
- Cleanup owner.

Không ghi secret/token từ auth context vào telemetry của feature flags.

### 23.4. Kill switch và latency

Một kill switch cần phản hồi trong 5 giây **không thể** chỉ dựa trên polling 60 giây mà không có cơ chế khác. Phải thiết kế trigger/operational control phù hợp, hoặc dùng central safety enforcement nếu là thay đổi liên quan an toàn.

## 24. Deployment bằng IaC và cấu hình như dữ liệu có quản lý

### 24.1. Tách resource definition và data-plane settings

Có hai nhóm thay đổi:

1. **ARM/Bicep/Terraform:** tạo App Configuration resource, network, managed identities, role assignments, diagnostic settings.
2. **Data-plane configuration:** tạo/sửa key-values, labels, feature flags, snapshots.

Permissions và tooling cho hai nhóm có thể khác nhau. Một identity có quyền tạo resource group không tự có quyền sửa key-values.

### 24.2. Quy trình review

~~~mermaid
flowchart LR
    PR["Pull request<br/>config manifest"] --> REVIEW["Schema/owner/security review"]
    REVIEW --> CI["CI validation<br/>types/ranges/labels"]
    CI --> STAGE["Deploy staging config"]
    STAGE --> TEST["Integration + canary test"]
    TEST --> PROD["Promote prod snapshot / keys"]
    PROD --> OBS["Monitor applied revision"]
    OBS --> ROLLBACK["Rollback if needed"]
~~~

### 24.3. Không coi Portal edits là nguồn thật duy nhất

Manual Portal edit có thể phù hợp cho incident response nhưng sau đó phải đồng bộ với manifest/release record. Nếu không, lần deploy kế tiếp từ Git có thể ghi đè và làm mất thay đổi khẩn cấp.

### 24.4. Phân quyền CI/CD

- Dùng federated identity/OIDC khi hỗ trợ.
- CI writer chỉ có data-plane quyền cần thiết trên đúng store.
- Tách production deploy job với local dev identity.
- Bắt buộc approvals cho config ảnh hưởng payment/security.
- Không in access key/connection string vào build logs.
- Validate values trước khi update sentinel.
- Log ETag/revision mà không log sensitive payload.
- Giới hạn số setting writes/giây để tránh quota.

### 24.5. Rollback không phải chỉ deploy JAR cũ

Vì config nằm bên ngoài binary, rollback code mà không rollback config có thể phá backward compatibility. Ghi **app artifact version + config snapshot/revision + feature flags state** vào release manifest, rồi rollback như một bộ.

## 25. Monitoring và telemetry

### 25.1. Các chỉ số cần theo dõi

| Lớp | Metric/log | Mục tiêu |
|---|---|---|
| App Configuration service | Request counts/errors, throttling/latency theo metrics khả dụng | Service health |
| Spring bootstrap | Config load succeeded/failed, startup duration | Failures khi deploy |
| App refresh | Last refresh success time, revision/ETag, refresh failures | Propagation SLO |
| Feature flags | Flag evaluation/targeting counts, outcome | Rollout quality |
| Key Vault | 401/403/429, latency, secret refresh errors | Secret dependency |
| HTTP business app | Error rate, checkout latency p95/p99, retry count | Tác động thực |
| IaC/operations | Who changed what, when, change ticket | Audit |
| Cost Management | Store tier/requests, network, logs, extra resources | FinOps |

Không phải tất cả là Azure metrics tích hợp sẵn dưới chính tên trên. **ConfigAppliedRevision** hoặc **LastSuccessfulRefreshAge** thường phải được ứng dụng instrument.

### 25.2. Log có thể giữ thông tin gì?

Một log an toàn:

~~~json
{
  "event": "APP_CONFIG_APPLIED",
  "application": "orders-api",
  "environment": "prod",
  "revision": "orders-2026-11-20-r2",
  "result": "SUCCESS",
  "source": "azure-app-configuration",
  "refreshLatencyMs": 55,
  "correlationId": "corr-demo-481"
}
~~~

Các con số là giả định. Không log nguyên JSON settings nếu có thể chứa secrets/reference metadata nhạy cảm, connection string, token hoặc user attributes.

### 25.3. Tính propagation latency

~~~text
Operator commits revision r2:       10:00:00
Instance A reports applied r2:      10:00:20
Instance B reports applied r2:      10:00:55

Propagation latency:
    A = 20 giây
    B = 55 giây
Fleet converged after 55 giây trong ví dụ
~~~

Nếu SLO yêu cầu toàn fleet trong 30 giây, ví dụ trên là **vi phạm** dù store update API đã thành công.

### 25.4. Cảnh báo

- Config refresh failure kéo dài.
- Applied revision quá cũ so expected release revision.
- Mismatch label/environment giữa deployment và store.
- Store 403/429/5xx tăng.
- Key Vault reference resolution lỗi.
- Feature flag có thay đổi không được review.
- Checkout error rate/latency tăng ngay sau config change.
- Data-plane write identity không mong đợi.
- Log xuất hiện secret/connection string.

## 26. Hiệu năng, quota và cấu hình cache

### 26.1. Không GET config cho mỗi HTTP request

Giả sử API nhận **500 requests/giây** và mỗi request đọc 3 keys từ App Configuration:

~~~text
500 requests/s × 3 key GET/request
= 1.500 config GET/s

Trong một ngày:
1.500 × 86.400
= 129.600.000 config GET/ngày
~~~

Đây là ví dụ tải, không phải quota/pricing Azure. Kiểu thiết kế này tăng latency, request volume, throttling và dependency coupling.

### 26.2. Load once + refresh

Nếu 40 instances nạp 20 keys mỗi 5 phút:

~~~text
40 instances × 20 keys × 12 lần/giờ × 24 giờ
= 230.400 key read operations/ngày
~~~

Đây chỉ là phép tính **giả sử mỗi lần refresh đọc đủ 20 keys**. Một SDK có cache, ETag check, sentinel polling hoặc bulk retrieval có thể tạo ít/khác số requests; đừng lấy phép tính này làm số meter tính phí chắc chắn.

### 26.3. Refresh interval trade-off

| Refresh interval | Lợi ích | Đổi lại |
|---|---|---|
| Rất ngắn | Phát hiện thay đổi nhanh | Quota/traffic/tải/race |
| Trung bình | Cân bằng latency và operations | Propagation chậm hơn |
| Dài | Ít requests | Flags/values stale lâu |
| Không dynamic refresh | Dễ tái lập release | Phải restart/rollout |

Chọn theo **propagation SLO**, chứ không chọn ngẫu nhiên một số giây. Quy định latency tối đa cũng cần xét traffic-dependent triggers, startup caches và outage behavior.

### 26.4. Backoff và thundering herd

Khi store từ chối 429:

- Phân loại nguồn lỗi (App Configuration, Key Vault, Entra hay app API).
- Respect Retry-After nếu có.
- Exponential backoff + jitter.
- Bounded retries và concurrent refresh.
- Không tạo 500 instances đồng loạt restart vì một lỗi refresh.
- Giữ last validated config khi policy cho phép.
- Không dùng per-request fallback khiến lượng GET tăng đột biến.

## 27. Chi phí và FinOps cho App Configuration

### 27.1. Các nguồn chi phí

| Thành phần | Nguồn chi phí/ảnh hưởng |
|---|---|
| Azure App Configuration | Store tier, request/operation volume, capacity và tính năng theo plan |
| Feature flags | Usage/quota theo App Configuration feature support |
| Snapshot | Lưu trữ/số snapshots/operations theo tier và pricing model |
| Key Vault | Separate secret-read operations, bảo vệ khóa/cert theo pricing |
| Java compute | CPU/RAM của App Service/AKS/Container Apps/VM |
| Private networking | Private Endpoint, network firewall, NAT/data transfer |
| Azure Monitor | Diagnostic ingestion, retention và alerts |
| CI/CD | Config promotion, validation, repeated writes |
| DR/high availability | Nhiều stores/vùng, vận hành và đồng bộ |

Không đưa giá cụ thể vì Azure pricing theo region/tier/thời điểm; dùng **Azure Pricing Calculator**, Cost Management, budgets và tài liệu quota được cập nhật.

### 27.2. Một store chung có luôn tiết kiệm?

Một store phục vụ dev/staging/prod có thể giảm số resources nhưng cũng làm tăng **blast radius** và khó tách quyền. Chi phí incident hoặc leak đôi khi lớn hơn phí thêm một store riêng cho production.

### 27.3. Cost per safe configuration rollout

Một KPI vận hành:

~~~text
Total cost per approved config release
= (App Configuration + Key Vault + compute
   + CI/CD + monitoring + networking + operations)
  / số release được validate và áp dụng đúng toàn fleet
~~~

Không chỉ đo requests/giây. Một hệ thống rẻ nhưng thường xuyên trộn cấu hình dev/prod là không đạt mục tiêu.

### 27.4. Tối ưu

- Không dùng remote GET per request.
- Giảm số keys bị refresh không cần thiết.
- Group các thay đổi và dùng sentinel khi hỗ trợ.
- Chọn interval theo SLO thực.
- Không bật semantic/full feature targeting phức tạp nếu một boolean config đã đủ.
- Cân nhắc snapshots/versioned releases thay cho polling quá dày.
- Giảm logging high cardinality/tags/PII.
- Sử dụng **Key Vault chỉ cho secrets**, không đưa mọi setting vào đó.
- Dọn stores, snapshots và configurations lab không còn owner, có approval.
- Theo dõi data-plane operations và provisioning tier thay vì chỉ chi phí ứng dụng.

## 28. Troubleshooting: bảng triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Bước xử lý |
|---|---|---|
| Java không nạp được config lúc startup | Endpoint/identity/network/spring bootstrap sai | Kiểm tra bootstrap logs và connector setup |
| **401** từ App Configuration | Token/audience/credential invalid | Xác định TokenCredential và tenant |
| **403** từ App Configuration | Data-plane RBAC hoặc network/firewall | Kiểm tra principal, role và DNS |
| **404** khi lấy key | Key/label không tồn tại | Kiểm tra chính xác key+label, null label |
| **429** | Quá nhiều GET/refresh/write | Backoff, TTL, bounded concurrency |
| **5xx/timeout** | Service/network transient | Retry budget, validated fallback |
| Bean luôn dùng config cũ | PropertySource refresh nhưng bean chưa rebind | Kiểm tra @RefreshScope/bean lifecycle |
| Một instance dùng giá trị khác | Refresh không đồng bộ | SLO convergence, revision telemetry |
| Prod nhận giá trị dev | Label/precedence sai | Deployment label verification |
| Key Vault reference trả JSON thay vì secret | SDK low-level chưa resolve reference | Dùng SecretClient/integration resolver |
| Key Vault reference 403 | Key Vault role/network thiếu | Data-plane permission Key Vault riêng |
| Feature flag không áp targeting | Thiếu feature management filter/context | Kiểm tra library và authenticated user/group |
| Feature flag tắt nhưng API vẫn chạy | Flag chỉ điều khiển UI | Enforce server-side gate và auth |
| Thay config có hiệu lực sau restart nhưng không live | Không có trigger/monitoring/refresh scope | Test refresh pipeline |
| Sentinel đổi nhưng keys vẫn cũ | Triggers, interval, selectors hoặc cache | Kiểm tra applied revision & polling |
| Config chưa đầy đủ khi refresh | Update keys từng phần, sentinel quá sớm | Sentinel last/snapshot |
| Cấu hình sai làm startup thất bại | Validation tốt hoặc defaults không an toàn | Fix config với owner/approval |
| Logs có secret value | Debug dump config/Actuator/HTTP body | Incident response, redact/rotate |
| Private Endpoint không đi được | Private DNS/route/VNet Integration lỗi | Kiểm tra FQDN, network từ đúng host |
| CLI kv set trả Forbidden | Người thao tác thiếu Data Owner | Kiểm tra role và auth-mode login |
| Service cost tăng | Per-request GET, quá nhiều instances/polling | Metrics và refresh policy |

### 28.1. Đọc lỗi đúng lớp

Một lỗi từ backend có thể bị bọc trong Spring BeanCreationException/IllegalStateException. Đừng chỉ xem exception lớp ngoài; tìm root cause:

~~~text
Spring ApplicationContext startup
    └── App Configuration PropertySource load
         ├── Azure Identity token acquisition
         ├── App Configuration network request
         ├── RBAC / 403 / network policy
         ├── Label/key selector
         └── Property binding / validation
~~~

Nếu lỗi Key Vault reference, trace thêm endpoint và quyền **Key Vault Secrets User**.

### 28.2. SDK low-level và starter xử lý lỗi khác nhau

- Low-level SDK: application trực tiếp nhận exception từ ConfigurationClient.
- Spring starter: lỗi có thể xảy ra rất sớm trong bootstrap, trước khi REST controllers và Actuator chạy.
- Nếu bật optional/fallback behavior, app có thể khởi động với local defaults mà không báo lỗi HTTP rõ ràng.

Cần cấu hình logs/metrics hợp lý từ startup và explicit readiness tests. Không giả định một SDK exception mapping giống Spring Boot integration.

## 29. Runbook xử lý 403 khi Spring Boot chạy trên App Service

Một tình huống phổ biến: developer chạy local thành công, deploy App Service thì lỗi 403.

Quy trình:

1. **Xác định source của 403**: App Configuration, Key Vault, proxy/firewall hay một API business khác.
2. Kiểm tra environment và **APP_CONFIG_ENDPOINT** trên instance.
3. Kiểm tra App Service managed identity có được bật.
4. Xác định **principal object ID** thực, không nhầm user-assigned client ID.
5. Kiểm tra role assignment **App Configuration Data Reader** ở store scope.
6. Nếu App Configuration có reference, kiểm tra role **Key Vault Secrets User** tại vault.
7. Kiểm tra store auth mode/network rules, Private Endpoint và VNet Integration.
8. Kiểm tra DNS hostname **store.azconfig.io** từ đúng instance.
9. Kiểm tra tenant/token credential chain có chọn developer credential từ environment variables không mong muốn.
10. Nếu role mới cấp, xác minh propagation, không tăng role lên Owner mù quáng.
11. Chạy test GET một key **không nhạy cảm** qua SDK/CLI trong network được phép.
12. Kiểm tra Spring Cloud Azure release/config bootstrap và application logs.
13. Khi đã sửa, xác minh config revision applied, readiness và telemetry.
14. Viết regression test cho identity+network+label đúng.

### 29.1. Khi không tìm được key

~~~text
getConfigurationSetting("orders.checkout.timeout-ms", "prod")
→ Not found
~~~

Kiểm tra:

- Store endpoint có đúng production?
- Key dùng dấu chấm hay colon?
- Label có thật là prod, không phải null/staging?
- Key có bị xóa/đổi tên?
- Prefix filter có bao phủ key?
- Setting content type có phù hợp?
- App đang dùng một snapshot không chứa key?
- Role/network có làm error bị wrapper chuyển thành thông điệp không rõ?

Không tạo key sản xuất bằng code runtime khi gặp 404. Việc ghi phải qua operator/pipeline được duyệt.

### 29.2. Khi bean không thay đổi sau refresh

Kiểm tra theo 4 mốc:

~~~text
Store updated?              YES
Instance refresh detected?  YES
PropertySource updated?     YES
Bean picked new value?      NO
~~~

Nếu chỉ bean chưa đổi:

- Bean có được tạo lại theo refresh scope không?
- Có dùng immutable constructor snapshot?
- Đã đăng ký properties bean đúng?
- Có service giữ bản sao timeout trong final field từ startup?
- HTTP client/DB pool có được rebuild?
- Có cơ chế refresh event/actuator trigger phù hợp phiên bản?
- Có concurrent access race?

Không kết luận App Configuration hỏng khi Store/Environment đều có value mới nhưng application lifecycle không áp dụng.

### 29.3. Khi refresh làm lỗi sản phẩm

- Xác nhận revision/actor và thời gian cập nhật.
- Nếu configuration manifest có rollback, quay lại snapshot/values trước.
- Tạm disable feature flag mới nếu được phép và đủ hiệu quả.
- Xem metrics checkout error/latency/retry.
- Kiểm tra units không nhận lại cấu hình lỗi khi timer tiếp tục poll.
- Có thể pause promotion/refresh hoặc roll instance theo runbook.
- Cập nhật validation constraints để chặn lần tái diễn.

## 30. Data security và governance

### 30.1. Mô hình các ranh giới

~~~mermaid
flowchart LR
    USER["Authenticated user"] --> APP["Spring Boot API"]
    ID["Workload identity"] --> APP
    APP --> AC["App Configuration<br/>non-secret config"]
    APP --> KV["Key Vault<br/>secrets"]
    APP --> DB["Business data"]
    ADMIN["IaC/CI operators"] --> AC
    AUTH["Authorization layer"] -. "tenant/group rules" .-> APP
~~~

Phân biệt **workload identity** để đọc config và **end-user identity** để gọi business APIs. Không cấp runtime writer role chỉ vì một user được phép bật tùy chọn trên UI.

### 30.2. App Configuration Data Reader vẫn có phạm vi rộng

Nếu một store chứa cấu hình dev/prod và app identity có role reader ở scope toàn store, có thể đọc nhiều labels. Tách **stores/identities/network** khi compliance yêu cầu environment isolation. Labels giúp quản lý variants, không thay RBAC.

### 30.3. Config injection và nguy cơ SSRF

Giá trị **orders.payments.endpoint-url** đến từ một store do CI/operator ghi. Nhưng nếu attacker chiếm được quyền ghi store:

- Có thể đổi endpoint sang máy chủ độc hại.
- Có thể thay timeout/retry để gây outage.
- Có thể bật flag admin không đúng.
- Có thể thay Key Vault reference URI sang vault ngoài phạm vi.

Ứng dụng vẫn cần **validate endpoints/allowed hosts**, xem config write role như quyền nhạy cảm, audit changes và chống SSRF qua downstream HTTP clients.

### 30.4. Key Vault reference URI là untrusted metadata với SDK thấp tầng

Nếu parser nhận URI tùy ý:

- Chỉ cho phép **https**.
- Hạn chế vault host theo environment/tenant/allowlist.
- Không tạo SecretClient trỏ tới arbitrary domains.
- Không log secretName/URI nếu không cần.
- Kiểm soát quyền Key Vault và tránh app có quyền đọc vault ngoài nhiệm vụ.

### 30.5. Actuator và config endpoints

Spring Actuator có endpoints như **/env** hoặc **/configprops** theo cấu hình, có thể tiết lộ configuration metadata hoặc values nếu expose quá rộng. Giới hạn mạng/authorization, bật sanitization, không mở toàn bộ endpoints qua public ingress.

### 30.6. Feature flags không thay authorization

Dù flag **admin-dashboard** tắt, backend route phải kiểm tra user role. Nếu flag bật cho một nhóm, nó chỉ quyết định hành vi tính năng, **không tự cấp quyền đọc data tenant khác**.

### 30.7. Secret rotation khi reference thay đổi

- App Configuration writer identity không nên được phép đọc mọi secret value.
- Key Vault rotation operator riêng thay credential.
- App runtime được phép get đúng secret.
- Refresh/Key Vault cache policy giúp nhận version mới.
- Cần partner-side credential activation/revocation.
- Không log secret vào diff, IaC state hoặc feature experiment analytics.

## 31. Testing strategy và môi trường staging

### 31.1. Unit tests: không gọi Azure

Test typed config và business code bằng object giả:

~~~java
import com.example.orders.config.CheckoutProperties;

CheckoutProperties props = new CheckoutProperties();
props.setTimeoutMs(900);
props.setRetryCount(2);

if (props.getTimeoutMs() != 900 || props.getRetryCount() != 2) {
    throw new AssertionError("Unexpected bound properties");
}
~~~

Đoạn này là mô tả một test body; đặt trong JUnit test method của project thật. Để test validation, sử dụng Bean Validation/Jakarta Validation test context.

### 31.2. Integration tests với App Configuration lab

1. Tạo store lab và user/managed identity test được phép.
2. Tạo key có null label và prod/dev labels.
3. Xác minh SDK getConfigurationSetting(key, label) đúng.
4. Xác minh Spring Cloud Azure PropertySource và @ConfigurationProperties binding.
5. Xác minh default/override precedence.
6. Kiểm tra missing required key → fail-fast nếu policy yêu cầu.
7. Đổi setting và sentinel → đo thời gian applied revision.
8. Kiểm tra bean thực sự sử dụng giá trị mới.
9. Kiểm tra identity không có data role bị từ chối.
10. Kiểm tra feature flag enabled/disabled và targeting nếu dùng.
11. Kiểm tra Key Vault reference cần quyền độc lập.
12. Dọn tài nguyên lab theo approval/retention.

### 31.3. Negative tests quan trọng

| Test | Kết quả mong đợi |
|---|---|
| Spring Boot prod chạy với label dev | Deployment validation chặn |
| Runtime identity chỉ có Azure Contributor | Không tự có data-reader permission |
| Identity mất App Configuration Data Reader | Remote access bị từ chối |
| Key Vault reference có nhưng thiếu Secrets User | Secret không resolve |
| Key value timeout = -500 | Validation chặn áp dụng |
| Retry count = 100 | Validation chặn |
| Sentinel cập nhật trước keys | Test phát hiện partial config risk |
| Bean không nằm trong refresh lifecycle | Test chứng minh bean không tự đổi |
| User không có role admin nhưng feature flag on | Backend authorization vẫn từ chối |
| Cross-tenant/config label access | Không có rò dữ liệu theo thiết kế isolation |
| Store 429/network timeout | Bounded retry và safe fallback |
| Feature flag disable chậm | Đo propagation SLO và cảnh báo |
| Config writer bị lộ | Quyền bị thu hồi, audit và rollback |

### 31.4. Chaos tests trên staging

- Chặn outbound tới App Configuration vài phút.
- Làm Key Vault reference lỗi do permission test.
- Gây 429/throttling có kiểm soát.
- Restart pods giữa lúc refresh.
- Thay 10 keys và sentinel với độ trễ mô phỏng.
- Đổi snapshot/reference khi một nửa instances vẫn ở revision cũ.
- Test concurrent requests đọc config.
- Quan sát readiness/liveness không tạo restart storm.
- Kiểm tra cả logs/Actuator không lộ keys.
- Đo thời gian hội tụ và tính nhất quán hành vi.

**Không chạy chaos tests với vault/store production hoặc tài nguyên shared** nếu chưa có approval riêng.

## 32. Hướng dẫn thực hành end-to-end trên Spring Boot

Các bước chỉ mang tính hướng dẫn, chưa có ứng dụng hoặc Azure resource nào được triển khai:

1. Tạo một Spring Boot project Java 17 với Spring Web và Validation.
2. Chọn Spring Boot/Spring Cloud Azure versions tương thích theo release matrix.
3. Tạo App Configuration lab store và 3 dot-separated keys ở mục 10.
4. Cấp **Data Reader** cho identity đọc runtime; Data Owner chỉ cho operator.
5. Cấu hình **APP_CONFIG_ENDPOINT** và **APP_CONFIG_LABEL** ở deployment.
6. Đưa Spring Cloud Azure App Configuration starter vào Maven, chọn đúng bootstrap mechanism.
7. Bind các keys vào **CheckoutProperties**, bật Bean Validation.
8. Tạo một service sử dụng timeout/retry được inject.
9. Chạy local với **az login**, xác minh user có data role.
10. Ghi sanitized startup log **configured revision/label**; không dump toàn bộ Environment.
11. Bật refresh/sentinel theo syntax đúng release; thay timeout bằng CLI.
12. Kiểm tra từng instance thật sự thay đổi behavior.
13. Thử giá trị invalid để xác nhận validation không cho áp dụng.
14. Tạo feature flag **new-checkout**, kiểm tra on/off, targeting nếu library hỗ trợ.
15. Tạo Key Vault demo secret và App Configuration reference metadata.
16. Cấp Key Vault Secrets User cho runtime identity, kiểm tra quyền riêng.
17. Thử lỗi 403/429/Key Vault reference/network và safe fallback.
18. Bật metrics/diagnostics, so chi phí và propagation latency.
19. Dọn lab resources riêng đã được phê duyệt.

**Tiêu chí đạt lab:** cùng một binary Spring Boot chạy dev/prod với labels khác nhau, mọi settings có type/range validation, không hard-code secrets, reader role đúng, refresh có bằng chứng applied revision, và lỗi remote dependency không làm hệ thống vận hành ngoài policy.

## 33. Chọn phương án cấu hình theo tình huống

| Tình huống | Phương án gợi ý | Lý do |
|---|---|---|
| Ứng dụng nhỏ, ít cấu hình thay đổi | application.yml + environment | Đơn giản, ít remote dependency |
| Nhiều Spring Boot services cần chung config | Azure App Configuration | Tập trung, labels, quản lý thay đổi |
| Chỉ cần secret từ đối tác | Azure Key Vault hoặc managed identity trực tiếp | Không đặt secret plaintext trong App Config |
| Feature bật/tắt và targeting theo nhóm | App Configuration Feature Manager | Condition filters và gradual rollout |
| Cần cùng binary cho nhiều environments | App Configuration labels hoặc stores riêng | Tránh rebuild JAR cho từng môi trường |
| Đòi hỏi tách quyền prod/dev mạnh | Stores/identities khác nhau | Label không phải security boundary |
| Config thay đổi thường xuyên, cần refresh | Starter/SDK + sentinel + applied revision | Có cơ chế refresh kiểm chứng |
| Config cần bất biến theo release | Snapshot/versioned manifest | Tính nhất quán và rollback |
| App chỉ có vài non-secret keys | Environment/App Service settings | Tránh thêm complexity |
| Payment API key không thể loại bỏ | Key Vault reference hoặc SecretClient | Rotation/least privilege |
| Dữ liệu thay đổi cho mỗi user/request | Business DB/API | Không dùng App Configuration làm session store |
| Backend cần giá trị live của transaction | Azure SQL/Cosmos/service API | Cấu hình không phải nguồn trạng thái nghiệp vụ |
| AKS có nhiều services cần config | App Configuration + Workload ID nếu phù hợp | Central governance; K8s ConfigMaps vẫn hữu ích |
| Một cờ security bắt buộc tắt dưới 1 giây | Thiết kế central enforcement/low-latency control riêng | Polling refresh có propagation lag |
| Nhiều settings thay đổi như một bộ | Snapshot + canary/release manifest | Tránh mixed config không tương thích |

**Quy tắc lựa chọn:** Bắt đầu từ tác động nghiệp vụ, tốc độ thay đổi, yêu cầu nhất quán, phạm vi bảo mật và số lượng ứng dụng. Không triển khai App Configuration chỉ để thay một dòng local YAML không có nhu cầu vận hành rõ ràng.

## 34. Checklist production

### 34.1. Kiến trúc và dữ liệu

- [ ] Đã phân loại config thường, feature flags, secrets và runtime settings.
- [ ] Không lưu API keys/passwords/private keys dạng plain text trong App Configuration.
- [ ] Đã quyết định use case nào dùng Key Vault reference, use case nào dùng managed identity trực tiếp.
- [ ] Keys có naming convention nhất quán và owner.
- [ ] Dot-separated Spring properties được kiểm tra mapping, không lẫn colon/prefix semantics.
- [ ] Labels dev/staging/prod có precedence được test.
- [ ] Store/shared labels không được dùng thay data isolation.
- [ ] Có snapshot/manifest/sentinel strategy khi cần thay nhiều keys nhất quán.
- [ ] Có validation cho timeouts, retries, URLs, feature conditions và bounds.
- [ ] Không dùng App Configuration như database/session store.
- [ ] Đã định nghĩa fail-open/fail-closed policy theo risk.
- [ ] App biết revision/version đang được áp dụng.

### 34.2. Java/Spring Boot

- [ ] Spring Boot/Spring Cloud Azure/Java versions tương thích và được pin.
- [ ] Đã chọn SDK low-level hay starter dựa trên yêu cầu.
- [ ] Bootstrap endpoint và identity có từ nguồn local/platform an toàn.
- [ ] Remote PropertySource được nạp đúng trước khi bind beans.
- [ ] @ConfigurationProperties hoạt động với key/label đã chọn.
- [ ] Bind/refresh validation được thử ở startup và runtime.
- [ ] @RefreshScope/bean lifecycle hoặc atomic snapshot update đã được kiểm tra.
- [ ] HTTP clients/pools có chính sách tái cấu hình khi timeout/endpoint đổi.
- [ ] Không tạo ConfigurationClient/credential mới trong mỗi HTTP request.
- [ ] Không gọi remote App Configuration GET trên từng business request.
- [ ] Remote refresh interval phù hợp SLO/quota.
- [ ] Có circuit breaker/backoff/timeout/retry budget cho remote calls.
- [ ] Startup hoặc outage behavior đã được quyết định và thử.
- [ ] Liveness probe không tự gọi App Configuration/Key Vault liên tục.

### 34.3. Bảo mật và vận hành

- [ ] Workload identity dùng Entra/managed identity, không có static connection string nếu có thể.
- [ ] Runtime chỉ có App Configuration Data Reader hoặc quyền tối thiểu.
- [ ] Config deployment writer role tách khỏi runtime reader.
- [ ] Key Vault reference có Key Vault Secrets User riêng.
- [ ] Role assignment scopes và principal IDs đã xác minh.
- [ ] Private Endpoint/firewall/DNS/VNet Integration đúng theo môi trường.
- [ ] TLS certificate validation không bị vô hiệu.
- [ ] Feature flags không thay application authorization.
- [ ] Spring Actuator và error pages không làm lộ values/secrets.
- [ ] Có config change audit, approver và rollback.
- [ ] Logging được sanitize, không chứa credentials/tokens/plaintext secret.
- [ ] Có cảnh báo 401/403/429, refresh errors, stale revision và mismatch labels.
- [ ] Đã thử đa instance, reconnect/startup storm và config drift.
- [ ] Có owner/budget/quota/cost dashboard cho App Configuration/Key Vault.
- [ ] Runbook bao gồm rollback cả binary lẫn config revision.
- [ ] Lab/test không được phép thay secrets hoặc feature flags production.

## 35. Bài tập thực hành

### Bài 1: Phân loại cấu hình

Với các giá trị sau, chọn application.yml, environment, App Configuration, Key Vault hoặc business database:

1. Checkout timeout.
2. Partner API key.
3. DB connection endpoint không chứa credential.
4. DB password legacy.
5. SKU đang tồn kho.
6. Feature flag new-checkout.
7. Java heap limit.
8. LastReadNotificationId của một user.
9. Tên môi trường prod.
10. Cấu hình retry.

Giải thích mỗi lựa chọn theo **sensitivity, update frequency và ownership**.

### Bài 2: Key-value và labels

Thiết lập:

~~~text
orders.checkout.timeout-ms [no label] = 1000
orders.checkout.timeout-ms [dev]      = 1500
orders.checkout.timeout-ms [staging]  = 1100
orders.checkout.timeout-ms [prod]     = 800
~~~

Hãy viết test chứng minh ứng dụng prod nhận 800, dev nhận 1500. Giải thích cần làm gì nếu prod key bị xóa: fallback null-label hay fail-fast?

### Bài 3: CLI, RBAC và managed identity

1. Tạo App Configuration store lab.
2. Operator cấp Data Owner cho identity tạo demo values.
3. Ghi 3 dot-separated keys bằng **--auth-mode login**.
4. App managed identity được cấp Data Reader.
5. Chạy SDK getConfigurationSetting.
6. Dùng identity không có data role để kiểm tra 403.
7. Ghi ra request ID/status nhưng không log secret.

### Bài 4: Java SDK thấp tầng

Dùng **ConfigurationClient**:

- Đọc timeout theo key/label.
- Parse int và validate 100–10000.
- Với key không có → xử lý 404 theo policy.
- Với 429 → bounded retry.
- Đọc một tập keys bằng selector và chỉ log metadata.
- Không dùng một ConfigurationClient mới cho từng request.

### Bài 5: @ConfigurationProperties

1. Tạo Spring Boot class **CheckoutProperties**.
2. Bind timeoutMs/retryCount.
3. Thêm Bean Validation cho khoảng giá trị.
4. Test invalid timeout **-1** không được áp dụng.
5. Test thiếu endpoint partner bắt buộc.
6. Kiểm tra label prod không lấy dev fallback.

### Bài 6: Sentinel và refresh

Cho 5 instances, refresh interval 30 giây, đang dùng revision r1.

1. Cập nhật 3 keys.
2. Update sentinel sau cùng thành r2.
3. Đo thời gian từng instance báo đã áp dụng r2.
4. Một instance không có traffic và không refresh; thiết kế cách phát hiện.
5. Simulate invalid value trong r3.
6. Đảm bảo app giữ r2 theo policy.
7. Viết SLO “99% instances apply within 90 seconds” và metric để kiểm chứng.

### Bài 7: Config Snapshot và rollback

Một release đổi checkout endpoint và API version. Nếu update từng key, một instance có thể nhận endpoint v2 + version v1.

- Dùng snapshot hoặc typed JSON atomic unit.
- Tạo release manifest gắn JAR + config revision.
- Canary r2.
- Rollback app/config như một bộ khi lỗi tăng.
- Giải thích vì sao ETag từng key chưa phải transaction đa key.

### Bài 8: Feature flags

Bật **new-checkout** cho nhóm QA, rồi 5%, 25%, 100%.

- Chọn targeting context từ authenticated identity.
- Đo error rate/conversion/p95.
- Thử flag off trong khi có request đang xử lý.
- Giải thích giới hạn kill switch do refresh latency.
- Bổ sung cleanup flag sau rollout.

### Bài 9: Key Vault reference

1. Tạo secret demo trong Key Vault lab.
2. App Configuration lưu Key Vault reference URI.
3. App identity có App Configuration Data Reader nhưng **chưa** có Key Vault Secrets User: test failure.
4. Cấp thêm Key Vault role đúng.
5. Dùng SDK/integration có resolver để lấy secret.
6. Kiểm tra không ghi secret value vào logs.
7. Đổi secret version và test refresh riêng.

### Bài 10: Private Endpoint

Vẽ đường từ App Service tới **store.azconfig.io** và từ ứng dụng tới Key Vault:

- VNet Integration.
- Private Endpoint.
- Private DNS.
- TLS hostname.
- Entra token endpoint.
- Data-plane RBAC.

Giải thích tại sao 403 không nhất thiết là thiếu role và tại sao không kết nối raw private IP.

### Bài 11: Outage

Giả lập App Configuration không khả dụng trong 10 phút:

- Instance A đang chạy với config validated.
- Instance B vừa scale-out.
- Instance C đang refresh feature flag quan trọng.

Thiết kế fail-fast/last-known-good/readiness cho từng instance, nêu khi nào tiếp tục dùng stale config và khi nào phải fail closed.

### Bài 12: FinOps

Giả định 40 instances, 20 keys, refresh 5 phút và 500 business requests/s:

1. Tính lý tưởng số GET operations nếu đọc config per request.
2. Tính upper-bound nếu mỗi refresh đọc đủ 20 keys.
3. Phân tích thực tế sentinel/ETag caching và bulk requests làm số khác đi.
4. Liệt kê chi phí App Configuration, Key Vault, networking và Azure Monitor.
5. Đề xuất thay đổi để tiết kiệm mà vẫn đạt refresh SLO.

## 36. Câu hỏi tự kiểm tra

1. Azure App Configuration giải quyết vấn đề gì mà application.yml khó giải quyết khi có nhiều instances?
2. Vì sao nên tách non-secret config và secret?
3. App Configuration khác Key Vault ở mục tiêu và data protection thế nào?
4. Một setting được nhận diện bởi key và trường nào?
5. Null label có giống chuỗi "null" không?
6. Labels có tạo security boundary giữa dev/prod không?
7. Vì sao naming convention quan trọng cho Spring Boot property binding?
8. Khi nào cần stores riêng thay vì một store dùng labels?
9. Feature flag khác một boolean config cố định ở đâu?
10. Targeting filters cần identity context từ nguồn nào?
11. Feature flag có thay application authorization không?
12. Key Vault reference chứa secret value hay URI?
13. App Configuration Data Reader có được đọc Key Vault secret không?
14. Azure Contributor có mặc nhiên Data Reader trong App Configuration không?
15. DefaultAzureCredential lấy identity nào ở local và trên App Service?
16. Managed identity khác connection string access key thế nào?
17. Spring Cloud Azure starter làm gì khác ConfigurationClient thấp tầng?
18. Vì sao cần kiểm tra Spring Boot/Spring Cloud Azure version compatibility?
19. Endpoint của App Configuration nên được cung cấp ở giai đoạn nào?
20. Khi nào nên dùng @ConfigurationProperties thay vì tự parse Strings?
21. @Validated cần kiểm tra những loại giới hạn nào?
22. Một PropertySource refresh có luôn rebuild HTTP clients cũ không?
23. @RefreshScope có tự tạo push từ App Configuration không?
24. Sentinel key giúp giải quyết vấn đề gì?
25. Vì sao update sentinel cuối cùng vẫn chưa tạo transaction across fleet?
26. Snapshot khác null-label defaults như thế nào?
27. ETag có tác dụng gì trong concurrent config updates?
28. Một config revision có hiệu lực tại mọi instance cùng thời điểm không?
29. Vì sao phải đo applied revision thay vì chỉ nhìn CLI kv set success?
30. App Service VNet Integration khác Private Endpoint của App Configuration thế nào?
31. Private DNS zone cho App Configuration thường thuộc tên nào?
32. Vì sao không đổi endpoint sang private IP để sửa DNS lỗi?
33. HTTP 401, 403, 404, 429 thường chỉ ra những lớp lỗi gì?
34. Khi thiếu key có nên tự tạo bằng runtime identity không?
35. Startup fail-fast phù hợp cấu hình nào?
36. Last-known-good có rủi ro gì khi config liên quan security?
37. Tại sao liveness probe không nên gọi remote config mỗi 5 giây?
38. Feature flag disable có thể chậm do yếu tố gì?
39. Vì sao một application không nên GET config trên mọi request?
40. App Configuration Store tier, operations và monitoring ảnh hưởng FinOps ra sao?
41. Tại sao rollback JAR nhưng không rollback config là nguy hiểm?
42. Key Vault reference versionless có đảm bảo secret mới được dùng tức thời không?
43. Khi Spring Actuator expose /env có rủi ro gì?
44. Tại sao config writer role cần được review chặt?
45. Khi nào nên dùng business database thay cho App Configuration?
46. Làm thế nào phát hiện một instance đang dùng revision cũ?
47. Làm sao giảm thundering herd khi hàng trăm instances refresh đồng loạt?
48. Vì sao phải kiểm thử negative permissions và private networking?
49. Cần log thông tin gì để debug mà không lộ secret?
50. Khi nào một kiến trúc chỉ dùng local application.yml lại là lựa chọn tốt nhất?

## 37. Tài liệu tham khảo

- [Azure App Configuration overview — Microsoft Learn](https://learn.microsoft.com/azure/azure-app-configuration/overview)
- [Keys and values in App Configuration](https://learn.microsoft.com/azure/azure-app-configuration/concept-key-value)
- [Use labels for application configuration](https://learn.microsoft.com/azure/azure-app-configuration/howto-labels)
- [Feature management overview](https://learn.microsoft.com/azure/azure-app-configuration/concept-feature-management)
- [Feature flag schema and conventions](https://learn.microsoft.com/azure/azure-app-configuration/concept-feature-filters)
- [Azure App Configuration snapshots](https://learn.microsoft.com/azure/azure-app-configuration/concept-snapshots)
- [Use Key Vault references in Azure App Configuration](https://learn.microsoft.com/azure/azure-app-configuration/use-key-vault-references-dotnet-core)
- [Azure App Configuration with Java and Spring](https://learn.microsoft.com/azure/azure-app-configuration/quickstart-java-spring-app)
- [Use dynamic configuration in Java Spring apps](https://learn.microsoft.com/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app)
- [Use feature flags in Java Spring apps](https://learn.microsoft.com/azure/azure-app-configuration/quickstart-feature-flag-spring-boot)
- [Azure App Configuration Java SDK documentation](https://learn.microsoft.com/java/api/overview/azure/data-appconfiguration-readme)
- [Azure App Configuration Java client API](https://learn.microsoft.com/java/api/com.azure.data.appconfiguration.configurationclient)
- [Spring Cloud Azure overview](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Spring Cloud Azure App Configuration integration](https://learn.microsoft.com/azure/developer/java/spring-framework/configuration-properties-azure-app-configuration)
- [Spring Cloud Azure compatibility reference](https://learn.microsoft.com/azure/developer/java/spring-framework/spring-versions)
- [Azure App Configuration authentication with Microsoft Entra ID](https://learn.microsoft.com/azure/azure-app-configuration/concept-enable-rbac)
- [Azure App Configuration Private Endpoint](https://learn.microsoft.com/azure/azure-app-configuration/concept-private-endpoint)
- [Azure App Configuration monitoring](https://learn.microsoft.com/azure/azure-app-configuration/monitor-app-configuration)
- [Azure Key Vault overview](https://learn.microsoft.com/azure/key-vault/general/overview)
- [Key Vault RBAC permissions](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Azure Managed Identities overview](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Spring Boot externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot ConfigurationProperties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Cloud refresh scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Azure App Configuration pricing](https://azure.microsoft.com/pricing/details/app-configuration/)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)






