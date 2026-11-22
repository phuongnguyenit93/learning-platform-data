# Triển khai, phân tách môi trường và quản lý phiên bản Function

Một Azure Function có thể chạy tốt trên máy lập trình viên nhưng gặp lỗi sau khi triển khai: trigger không được nhận diện, cấu hình Storage sai, phiên bản Java không tương thích hoặc staging vô tình xử lý message production. Với ứng dụng serverless, **deployment thành công chưa chứng minh Function sẵn sàng phục vụ nghiệp vụ**. Một quy trình phát hành đáng tin cậy phải kiểm soát artifact, runtime, cấu hình, dữ liệu, quyền truy cập, kiểm thử và rollback.

Bài học thuộc chương **Serverless với Azure Functions** của module **CLOUD_PROVIDERS_AZURE**. Module tìm hiểu Microsoft Azure từ subscription, resource group, Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu, đồng thời học triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Trọng tâm bài này là **triển khai Function nhất quán giữa dev/staging/production và quản lý phiên bản an toàn**, có ví dụ Java/Maven, Azure CLI và CI/CD.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

- Phân biệt Function, Function App, hosting plan, environment, deployment slot và release.
- Chọn cách triển khai theo hosting plan: Maven/Core Tools, package, One Deploy, CI/CD hoặc container image.
- Thiết kế **dev, staging, production** có nguồn dữ liệu, identity, Key Vault và monitoring tách biệt.
- Biết khi nào nên dùng **Function Apps riêng** và khi nào dùng **deployment slots**.
- Phân biệt version của mã ứng dụng, Azure Functions host, Java worker, binding extensions và hợp đồng sự kiện.
- Thiết kế pipeline **build once, test, promote same artifact**, có approvals và audit.
- Ngăn staging Timer/Queue/Event-triggered Functions xử lý dữ liệu production.
- Xác minh Function discovery, invocation, telemetry, rollback và chi phí sau deploy.

## 2. Function, Function App và đơn vị phát hành

**Function** là một xử lý được kích hoạt bởi trigger như HTTP, Timer, Queue, Service Bus hoặc Event Hubs. **Function App** là ranh giới cấu hình và phát hành chứa một hoặc nhiều Functions, cùng runtime host, app settings và mô hình scale theo hosting plan.

~~~text
Git commit
   |
   | Build + test + package
   v
Versioned Function App artifact
   |
   +----> Function App DEV  ----> Queue / DB / Key Vault dev
   |
   +----> Function App STG  ----> Queue / DB / Key Vault staging
   |
   +----> Function App PROD ----> Queue / DB / Key Vault production
               |
               +-- Azure Functions host
               +-- Java worker
               +-- HTTP Function
               +-- Queue Function
               +-- Timer Function
~~~

| Khái niệm | Quyết định gì? | Không nên nhầm |
|---|---|---|
| **Function** | Trigger, bindings và xử lý nghiệp vụ | Cả ứng dụng Azure |
| **Function App** | Runtime, cấu hình, identity, triển khai nhóm Functions | Mỗi method Java |
| **Hosting plan** | Compute, scale, memory, network, tính năng và chi phí | Phiên bản release |
| **Deployment artifact** | Code/JAR, host.json, function metadata, dependencies | App settings chứa secret |
| **Environment** | Tập tài nguyên, dữ liệu, quyền và quy trình cho dev/stg/prod | Một biến APP_ENV đơn lẻ |
| **Deployment slot** | Vùng chạy và swap trong Function App khi được hỗ trợ | Môi trường độc lập hoàn toàn |
| **Release** | Artifact bất biến + config revision + tests + approvals | Chỉ một lệnh publish |

Khi deploy một package mới, Function App có thể thay đổi nhiều Functions cùng lúc. Vì vậy, nếu hai nhóm có chu kỳ phát hành và yêu cầu scaling/bảo mật khác nhau, cân nhắc tách **Function Apps** ngay cả khi dùng chung repository.

## 3. Hosting plan quyết định khả năng triển khai

Các mô hình hosting Azure Functions có hành vi khác nhau. Trước khi xây CI/CD, xác định **hosting plan, OS, runtime và support matrix**.

| Hosting option | Mẫu vận hành | Điều cần chú ý khi deploy |
|---|---|---|
| **Flex Consumption** | Serverless, scale theo cơ chế Flex, tùy chọn networking/concurrency được hỗ trợ | Thường dùng **One Deploy** qua tooling hỗ trợ Flex; không áp ZIP Deploy/Kudu/slots theo hướng dẫn plan cũ |
| **Consumption (mô hình cũ)** | Billing và scale theo execution | Có giới hạn filesystem, package và tính năng; xem tài liệu plan hiện hành |
| **Elastic Premium** | Pre-warmed/always-ready instances và khả năng network nâng cao | Có thể dùng deployment slots nếu cấu hình/tier hỗ trợ; tốn compute nền |
| **Dedicated / App Service Plan** | Compute được cấp phát theo tier | Slot, Always On và các giới hạn phụ thuộc tier |
| **Azure Container Apps hosting** | Functions dựa trên container theo khả năng hỗ trợ | Phát hành container image/revision, không giả định có Kudu/ZIP Deploy giống code-based app |

**Không có một lệnh ZIP Deploy phổ quát cho mọi plan.** Một ví dụ lịch sử dùng **az functionapp deployment source config-zip** không nên được chạy trên Flex Consumption nếu phương thức không hỗ trợ. Với plan hiện hành, dùng Maven, Core Tools, action hoặc API được Microsoft tài liệu hóa cho chính plan đó.

### Chọn plan theo nhu cầu thực

1. Loại trigger và Java/.NET/Python/Node runtime có được hỗ trợ không?
2. Cold start, concurrency, timeout, memory và scaling có phù hợp tải không?
3. Có yêu cầu VNet, private endpoints hoặc IP egress được quản lý?
4. Cần deployment slots hay **hai Function Apps** để cô lập mạnh hơn?
5. Cần custom container hoặc thư viện hệ điều hành đặc thù?
6. RTO/RPO, giới hạn nghiệp vụ và ngân sách như thế nào?

Không chuyển toàn bộ workloads sang Premium chỉ vì muốn swap nếu hai apps độc lập và routing phù hợp đã đáp ứng độ an toàn với chi phí tốt hơn.

## 4. Quản lý phiên bản: nhiều lớp cần theo dõi

Từ "version Function" thường có ít nhất sáu nghĩa:

| Lớp | Ví dụ | Phương án quản lý |
|---|---|---|
| **Code release** | 1.4.2, commit a1b2c3 | Git tag/SHA, artifact checksum, changelog |
| **Functions host runtime** | Azure Functions 4.x | Cấu hình FUNCTIONS_EXTENSION_VERSION, theo lifecycle hỗ trợ |
| **Language worker** | FUNCTIONS_WORKER_RUNTIME=java; Java 17 | Stack/OS/JDK bytecode và deployment settings |
| **Binding extensions** | Storage, Event Hubs, Service Bus extension versions | Maven/host.json/bindings, compatibility tests |
| **Infrastructure/config revision** | Bicep/Terraform commit | IaC state, approvals, drift detection |
| **Event/API/data schema** | order-created.v2, /api/v2 | Contract tests, migration/compatibility plan |

**FUNCTIONS_EXTENSION_VERSION=~4** chọn Functions host major 4 theo cấu hình được hỗ trợ; **không** nói Function Java nghiệp vụ đang ở release 4.0. **FUNCTIONS_WORKER_RUNTIME=java** chọn language worker, nhưng **không tự quyết định JDK target** của artifact.

Một bản phát hành nên có manifest nội bộ:

~~~text
Application: orders-functions
Release: 1.4.2
Commit: a1b2c3d4
Artifact checksum: sha256:<CHECKSUM>
Functions host major: 4
Language worker: Java 17
Infrastructure revision: infra-2026-11-20
Event schema: order-created.v2
Released to: staging then production
~~~

Tài liệu trên là **release metadata**, không phải host.json hoặc lệnh CLI có thể chạy nguyên trạng.

## 5. Ví dụ Azure Function Java có thể truy vết release

Ta xây dựng một HTTP Function **ReleaseInfo**, đọc hai app settings không nhạy cảm: **APP_ENV** và **APP_VERSION**.

~~~java
package com.example.functions;

import java.util.Optional;
import com.microsoft.azure.functions.*;
import com.microsoft.azure.functions.annotation.*;

public class ReleaseInfoFunction {
    @FunctionName("ReleaseInfo")
    public HttpResponseMessage run(
        @HttpTrigger(
            name = "req",
            methods = {HttpMethod.GET},
            authLevel = AuthorizationLevel.FUNCTION,
            route = "release-info"
        ) HttpRequestMessage<Optional<String>> request,
        ExecutionContext context
    ) {
        String env = System.getenv().getOrDefault("APP_ENV", "unknown");
        String version =
            System.getenv().getOrDefault("APP_VERSION", "unversioned");

        context.getLogger().info("ReleaseInfo invoked");

        return request.createResponseBuilder(HttpStatus.OK)
            .header("Content-Type", "text/plain; charset=utf-8")
            .body("environment=" + env + "\nversion=" + version)
            .build();
    }
}
~~~

Đây là một Function ví dụ, cần project Java Functions/Maven đã cấu hình thư viện **azure-functions-java-library**. API trả dữ liệu release không nhạy cảm, tránh trả secrets, access tokens hoặc toàn bộ environment variables.

**AuthorizationLevel.FUNCTION** yêu cầu Function key khi gọi endpoint Azure, trừ những ngoại lệ cơ chế xác thực được dịch vụ định nghĩa. Chạy local qua Functions Core Tools có thể không thực thi key giống môi trường Azure, nên **local curl thành công không chứng minh endpoint cloud đã an toàn**.

### Cấu trúc project

~~~text
orders-functions/
├── pom.xml
├── host.json
├── local.settings.json          # local only, never commit secrets
├── src/main/java/com/example/functions/ReleaseInfoFunction.java
├── src/test/java/...            # test code
└── target/azure-functions/<PACKAGE_NAME>/
    ├── host.json
    ├── ReleaseInfo/function.json
    ├── orders-functions-*.jar
    └── lib/...
~~~

Đường dẫn output phụ thuộc plugin, cấu hình Maven và artifact thực tế. **Không upload một JAR trần** nếu Functions host còn cần host.json, function.json và dependencies.

### host.json không phải runtime 2.x

~~~json
{
  "version": "2.0"
}
~~~

**version=2.0** trong host.json là phiên bản schema cấu hình file, **không phải** giá trị Functions host major 2 hoặc mã nghiệp vụ v2.0.

### Maven/plugin

Project Java cần:

- **azure-functions-java-library** để dùng annotations/types.
- **azure-functions-maven-plugin** để package và có thể deploy theo cấu hình.
- Compiler target/JDK phù hợp runtime đã chọn cho Function App.
- Các test dependencies và thư viện nghiệp vụ.

Ví dụ **trích đoạn** chứ không phải pom.xml hoàn chỉnh:

~~~xml
<plugin>
    <groupId>com.microsoft.azure</groupId>
    <artifactId>azure-functions-maven-plugin</artifactId>
    <version>VERSION_CAN_XAC_MINH</version>
    <configuration>
        <appName>orders-functions-lab</appName>
        <runtime>
            <os>linux</os>
            <javaVersion>17</javaVersion>
        </runtime>
    </configuration>
</plugin>
~~~

Thay **VERSION_CAN_XAC_MINH** bằng bản plugin còn được hỗ trợ, thêm các phần POM bắt buộc và xem hướng dẫn **Java Functions Maven archetype** chính thức. Không sao chép một phiên bản Maven plugin cũ rồi coi là tương thích mọi hosting plan.

## 6. Chạy thử ở local và ý nghĩa của local.settings.json

Một dự án Java được tạo bằng template chính thức có thể chạy với JDK, Maven, **Azure Functions Core Tools v4** và dependencies phù hợp.

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "APP_ENV": "local",
    "APP_VERSION": "dev"
  }
}
~~~

Đặt nội dung này vào **local.settings.json** chỉ để thử nghiệm. **UseDevelopmentStorage=true** yêu cầu Azurite/local Storage emulator tương thích với trigger/host cần Storage. File này **không tự được deploy thành app settings trên Azure**, và trong dự án thực có thể chứa secrets nên phải nằm ngoài Git.

Với project Maven đã cấu hình:

~~~bash
mvn -B clean test
mvn -B package
mvn azure-functions:run
~~~

Nếu local host nhận diện **ReleaseInfo**, kiểm tra endpoint:

~~~bash
curl -i http://localhost:7071/api/release-info
~~~

Core Tools thường dùng cổng local 7071 theo mặc định, nhưng có thể thay. **Không hard-code cổng 7071 trong Java method**: HTTP routing do Functions host xử lý.

Local tests không tự xác nhận managed identity, Azure Storage firewall, VNet, cold start, concurrency hoặc plan-level deployments đúng; cần integration tests trên môi trường Azure riêng.

## 7. Thiết kế dev, staging và production đúng nghĩa

Một thiết kế đáng tin cậy **tách tài nguyên, quyền và dữ liệu**, không chỉ khác giá trị APP_ENV.

~~~text
Same tested artifact
      |
      +----> fa-orders-dev  ---> Queue/DB/Storage/KV dev
      |
      +----> fa-orders-stg  ---> Queue/DB/Storage/KV staging
      |
      +----> fa-orders-prod ---> Queue/DB/Storage/KV production
~~~

| Thành phần | Dev | Staging | Production |
|---|---|---|---|
| Function App | fa-orders-dev | fa-orders-stg | fa-orders-prod |
| Host storage | Storage dev | Storage stg | Storage prod |
| Queue/topic/consumer group | Nguồn sự kiện giả | Nguồn staging | Nguồn production |
| Database | Dữ liệu giả | Dữ liệu thử an toàn | Dữ liệu thật |
| Managed identity | Identity dev | Identity stg | Identity prod |
| Key Vault | Vault dev | Vault stg | Vault prod |
| App settings | APP_ENV=dev | APP_ENV=staging | APP_ENV=production |
| Monitoring | Logs/metrics dev | Smoke/regression | SLO/on-call alerts |
| Pipeline | Deploy tự động | QA gate | Approval và rollout controls |

Các tên chỉ minh họa, không phải resources đã tạo. Trong tổ chức lớn, có thể tách subscription hoặc resource group và áp Azure Policy/RBAC theo environment.

### Rủi ro khi dùng chung phụ thuộc

- Function staging dùng **QueueTrigger** trỏ nhầm queue production và xử lý message thật.
- Hai Function Apps dùng cùng **AzureWebJobsStorage/host identity** không đúng thiết kế, tạo tranh chấp state/leases hoặc timer behavior khó đoán.
- Staging sử dụng production database, làm thay đổi dữ liệu khi integration tests.
- Pipeline dev có quyền deploy prod và bỏ qua approvals.
- Identity staging có quyền đọc toàn bộ Key Vault production.

**APP_ENV=staging không phải security boundary**. Phải xác minh resource IDs, credential scopes, quyền thực tế và đường mạng.

## 8. Function Apps độc lập hay deployment slots?

**Deployment slot** là vùng triển khai phụ của một Function App trên các hosting plans hỗ trợ. Nó hữu ích để kiểm tra artifact trước khi **swap** tới production, nhưng không phải mọi plan đều có slot và không nên coi slot là một môi trường cách ly hoàn toàn.

| Tiêu chí | Function Apps riêng | Slot staging trong một Function App |
|---|---|---|
| Compute, resource boundary | Có thể độc lập theo app/plan/RG/subscription | Có thể chia sẻ plan và nhiều cấu hình |
| Identity và IAM | Có thể thiết kế tách biệt rõ | Phụ thuộc các thuộc tính slot và app |
| Event source | Dễ tách riêng | **Phải cấu hình riêng**, tránh trigger thật |
| HTTP rollout | Đổi route/gateway hoặc deploy từng app | Swap trên plan hỗ trợ |
| Tính năng khả dụng | Nhiều hosting models | Phụ thuộc SKU/hosting model |
| Chi phí | Có thể cần compute nhiều môi trường | Slot vẫn dùng tài nguyên được cấp phát |

**Không mặc định Flex Consumption có deployment slots và swap giống Premium/Dedicated.** Kiểm tra ma trận tính năng hiện hành, OS và plan thực tế. Nếu plan không hỗ trợ slots hoặc yêu cầu cô lập dữ liệu cao, sử dụng Function Apps độc lập.

HTTP Functions thường phù hợp slot swap hơn các Function xử lý **TimerTrigger, QueueTrigger, ServiceBusTrigger, EventHubTrigger hoặc Durable Functions**. Staging slot **không tự động ở trạng thái read-only** hoặc disable hết triggers.

## 9. App settings và phân quyền giữa môi trường

App settings điều khiển runtime và ứng dụng. Những giá trị cần biết:

| Setting | Ý nghĩa | Lưu ý |
|---|---|---|
| FUNCTIONS_EXTENSION_VERSION | Functions host major, ví dụ ~4 | Không phải mã release |
| FUNCTIONS_WORKER_RUNTIME | Worker ngôn ngữ, ví dụ java | Không thay bytecode target |
| AzureWebJobsStorage | Storage/host state theo khả năng hỗ trợ | Tách môi trường; kiểm soát identity/network |
| APP_ENV | Nhãn môi trường nghiệp vụ | Không thay quyền IAM |
| APP_VERSION | Release đã deploy | Không chứa secret |
| RELEASE_COMMIT | Git SHA từ pipeline | Hỗ trợ audit |
| APPLICATIONINSIGHTS_CONNECTION_STRING | Telemetry destination | Không in ra log |
| OrdersQueueConnection | Tên cấu hình binding/SDK tới queue | Nguồn dev/stg/prod phải khác |

**AzureWebJobsStorage** có thể dùng connection string hoặc identity-based configuration theo runtime/extension/plan hỗ trợ. Dù dùng cách nào, phải kiểm tra storage account thật, quyền data plane, firewall và host identity để tránh xung đột.

### Kiểm tra an toàn bằng Azure CLI

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

RG="<FUNCTION_RESOURCE_GROUP>"
APP="<FUNCTION_APP_NAME>"

az functionapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,state:state,kind:kind,location:location}" \
  --output json

az functionapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].{name:name,slotSetting:slotSetting}" \
  --output table
~~~

**Không bỏ --query và in tất cả values vào CI logs**, vì danh sách App settings có thể chứa connection strings hoặc secret references nhạy cảm.

Ví dụ thay đổi setting **không nhạy cảm** trên Function App lab đã được phê duyệt:

~~~bash
az functionapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings APP_ENV=dev APP_VERSION=1.4.2
~~~

Thay đổi app settings có thể **restart/recycle Function App**, ảnh hưởng invocations và trigger listeners. Với production, dùng IaC/CI/CD hoặc change management thay vì chỉnh thử.

## 10. Managed identity, Key Vault và trách nhiệm IAM

Để bảo vệ secrets:

1. Bật **managed identity** cho từng Function App theo mô hình hỗ trợ.
2. Cấp **data-plane roles** tối thiểu cho Storage, Key Vault, Service Bus hoặc database.
3. Ưu tiên kết nối identity-based nếu binding/SDK hỗ trợ.
4. Dùng **Azure Key Vault references** cho secrets chưa thể bỏ.
5. Đảm bảo DNS/VNet/Private Endpoint đúng nếu tài nguyên được giới hạn network.
6. Thiết kế rotation, audit và kiểm tra reference resolution.

Ví dụ Key Vault reference:

~~~text
@Microsoft.KeyVault(SecretUri=https://<VAULT_NAME>.vault.azure.net/secrets/<SECRET_NAME>/)
~~~

**Có managed identity không đồng nghĩa đã có quyền.** Function còn có thể gặp lỗi 403 khi thiếu role đọc Storage/Key Vault, hoặc timeout khi thiếu Private DNS/egress phù hợp.

Phân biệt ba chủ thể:

- **Build identity:** đọc source/dependencies và build artifact, không cần quyền prod.
- **Deployment identity:** chỉ deploy vào app/slot đích, có approvals; nên dùng OIDC/workload federation nếu CI hỗ trợ.
- **Runtime managed identity:** truy cập nguồn dữ liệu để Function chạy, không cần quyền tạo/xóa Function App.

Đừng dùng shared account key có toàn quyền chỉ để khắc phục một lỗi RBAC của Function.

## 11. Sticky settings và quy tắc swap trên deployment slots

Với hosting plan **có hỗ trợ deployment slots**, một số App settings được đánh dấu **deployment slot settings** (sticky), tức được giữ ở slot đích khi swap theo quy tắc Azure App Service/Functions. Điều này quan trọng vì staging và production thường cần connection strings/secret scopes khác nhau.

~~~text
Function App: fa-orders-prod
  |
  +-- production slot
  |     APP_ENV=production            (sticky)
  |     OrdersQueueConnection=prod    (sticky)
  |     APP_VERSION=1.4.1             (release)
  |
  +-- staging slot
        APP_ENV=staging               (sticky)
        OrdersQueueConnection=stg     (sticky)
        APP_VERSION=1.4.2             (release)
~~~

Sau swap, **code 1.4.2** cần hoạt động với dữ liệu production, không tự mang theo queue staging. Muốn vậy, phải kiểm tra cấu hình nào **được swap**, cấu hình nào **sticky** và điều kiện của plan.

Những giá trị thường cần cân nhắc sticky: **APP_ENV**, binding connections, database endpoints, AzureWebJobsStorage và host settings có tính môi trường, Key Vault reference, cấu hình enable/disable triggers. Không đánh dấu sticky một cách mù quáng: một số platform settings có quy tắc swap riêng, và việc thay setting có thể làm host restart.

Ví dụ đặt một setting không nhạy cảm là slot-specific:

~~~bash
az functionapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --slot-settings APP_ENV=staging
~~~

**Lệnh chỉ phù hợp khi slot đã tồn tại và hosting model hỗ trợ**. Trước khi thực hiện, kiểm tra **az functionapp config appsettings set --help** và policy tổ chức. Với secrets, không đặt plaintext value trong shell history; dùng Key Vault references.

## 12. Staging trigger có thể xử lý sự kiện thật

Điểm nguy hiểm nhất với Functions event-driven là **slot staging không phải bản sao bất động**. Nó có thể chạy trigger khi code và bindings khởi động.

~~~text
Queue: orders-production
            |
            +---- production Function: ProcessOrders
            |
            +---- staging Function: ProcessOrders (LỖI CẤU HÌNH)
                                      |
                                      v
                           Xử lý message production!
~~~

Tác động có thể là **tiêu thụ message trước production, gửi email hai lần, cập nhật dữ liệu thật, hoặc xử lý không tương thích schema**. Với Event Hubs/Service Bus, semantics phụ thuộc consumer group/subscription, checkpoints và giao thức; không có một kết quả mặc định chung cho mọi trigger.

### Biện pháp kiểm soát

- Tách **queue/topic/consumer group/storage** cho staging.
- Giữ connection settings riêng theo environment/slot.
- Tắt các Function không nên chạy trong staging khi có hỗ trợ.
- Với TimerTrigger, dùng schedule sandbox hoặc disable; không để cron production tự chạy ở staging.
- Test idempotency/retry/poison handling trên **dữ liệu giả**.
- Xem logs và xác minh trigger thực sự không đọc event production.

Một ví dụ app setting tắt Function có tên **ProcessOrders**:

~~~text
AzureWebJobs.ProcessOrders.Disabled=true
~~~

Tên phải khớp **Function name** mà host phát hiện. Việc disable không thay thế IAM/resource isolation: một lỗi không sticky hoặc một đợt redeploy có thể bật lại listener. Đối với HTTP trigger, khả năng gọi bằng master/admin key có hành vi khác với event triggers; kiểm tra trạng thái thực bằng runtime logs.

### Timer, host ID và storage

TimerMonitor/host state có thể lưu thông tin vào backing storage. Nếu staging và production chia sẻ cùng **AzureWebJobsStorage** hoặc host identity không được thiết kế đúng, có thể xuất hiện tranh chấp lease/lock hoặc hành vi schedule khó giải thích. **Cô lập host storage và host identity** theo hướng dẫn cho kiến trúc ứng dụng.

### Durable Functions còn nhạy cảm hơn

Durable orchestration có state và lịch sử event có thể tồn tại lâu hơn một deployment. Thay logic orchestrator đang chạy có thể phá điều kiện **determinism**. Không dùng slot swap như giải pháp tự động migration Durable instances. Cân nhắc versioned orchestrator names, side-by-side support, task hubs riêng và xử lý in-flight instances theo tài liệu Durable Functions.

## 13. Phân biệt các phương pháp triển khai

**Build** tạo artifact; **deploy** chuyển artifact tới môi trường đích. Những cơ chế phổ biến:

| Phương pháp | Mẫu ứng dụng | Giới hạn cần kiểm tra |
|---|---|---|
| **Maven Azure Functions plugin** | Java Functions Maven | POM appName/resourceGroup/plan/OS, version plugin, quyền |
| **Functions Core Tools publish** | Developer hoặc pipeline theo runtime được hỗ trợ | Plan/language compatibility, local/project settings |
| **ZIP Deploy** | Một số code-based Functions plans | Không giả định hoạt động trên Flex Consumption |
| **Run from package** | Gắn artifact package thay vì ghi file trực tiếp | Filesystem, storage và setting khác nhau theo hosting model |
| **One Deploy** | Flex Consumption và tooling hỗ trợ | Phương thức riêng; không sao chép quy trình Kudu/ZIP cũ |
| **GitHub Actions / Azure Pipelines** | Build một lần, approvals, promotion | Chọn deploy action/version tương thích plan |
| **Custom container image** | Runtime/dependencies đặc thù và plan hỗ trợ | ACR image version/digest, mạng, identity, container startup |

Không sửa code production trực tiếp qua Portal/Kudu/FTP để thay cho CI/CD. Phương án được quản lý là **immutable artifact**, có checksum, nguồn build và khả năng tái triển khai.

### ZIP Deploy ≠ Run from package ≠ One Deploy

**ZIP Deploy** là một cách gửi package đến những môi trường App Service/Functions hỗ trợ; **run from package** là mô hình host đọc/mount nội dung đã đóng gói thay vì chạy từ thư mục ghi sửa trực tiếp; **One Deploy** là phương thức được dùng cho Flex Consumption với tooling tương thích. Khái niệm gần nhau nhưng **không thể hoán đổi lệnh CLI tùy tiện**.

Ví dụ lệnh **az functionapp deployment source config-zip** trong một bài hướng dẫn cũ chỉ nên dùng sau khi xác nhận hosting plan và deployment mode hỗ trợ; không áp dụng mặc định cho Flex.

## 14. Triển khai Java Functions qua Maven

Với dự án Java được tạo từ **Azure Functions Maven archetype/template** chính thức, đã có plugin và POM đúng với target:

~~~bash
mvn -B clean test
mvn -B package

# Chỉ khi POM đã xác nhận app, plan, OS, subscription,
# resource group và user/service identity:
mvn -B azure-functions:deploy
~~~

**Lệnh deploy có thể tác động Azure resources thực.** Trước khi chạy, đọc appName/resourceGroup/region/runtime trong POM và xem plugin có tạo hoặc cập nhật Function App không. Không để POM lab trỏ tới production.

### Build once, deploy many

Để staging và production thực sự chạy **cùng binary**:

1. CI checkout **Git SHA** cố định.
2. Build một lần bằng JDK/Maven/dependencies đã xác minh.
3. Chạy tests và vulnerability/SCA scanning.
4. Lưu toàn bộ **Functions deployment package** và checksum.
5. Deploy package tới staging bằng phương thức hỗ trợ.
6. Khi staging pass, promote **chính package đã lưu** tới production.
7. Thay app settings theo môi trường, **không bake password/queue name vào JAR**.

Nếu production job lại chạy **mvn clean package** từ source mà không dùng artifact của staging, không được khẳng định là "promote cùng artifact": cùng commit vẫn có thể build khác khi dependencies hoặc toolchain đổi.

## 15. CI/CD có kiểm thử và approval

~~~mermaid
flowchart TD
    A[Git commit] --> B[Build, unit tests, SCA]
    B --> C[Immutable package + checksum]
    C --> D[Deploy dev]
    D --> E[Dev integration tests]
    E --> F[Deploy staging]
    F --> G[Smoke, event, contract tests]
    G --> H{Production approval?}
    H -- No --> I[Stop and investigate]
    H -- Yes --> J[Promote exact artifact]
    J --> K[Verify release + triggers + SLO]
    K --> L{Healthy?}
    L -- No --> M[Rollback / safe pause]
    L -- Yes --> N[Record release]
~~~

### GitHub Actions hoặc Azure Pipelines

Có thể dùng **OIDC/workload identity federation** để CI nhận token qua Microsoft Entra ID thay cho client secret dài hạn. Pipeline nên tách:

- Build identity chỉ có quyền repository/dependency.
- Staging deploy identity chỉ cập nhật staging app/slot.
- Production deploy identity có approvals và scope hẹp.
- Runtime managed identity chỉ truy cập các tài nguyên nghiệp vụ cần thiết.

Mẫu **pseudo-workflow** để thấy các giai đoạn, **không phải YAML GitHub Actions chạy trực tiếp**:

~~~yaml
build:
  checkout: fixed-commit
  java: approved-jdk
  test: mvn clean verify
  output: immutable-functions-package-and-checksum

deploy-staging:
  identity: staging-oidc
  artifact: exact-output-from-build
  target: fa-orders-stg
  checks: smoke-tests-and-event-contracts

deploy-production:
  identity: production-oidc
  approval: required
  artifact: exact-output-from-build
  target: fa-orders-prod
  checks: release-info-and-observability
~~~

Workflow thực tế cần các actions/version đúng (**azure/login**, Functions deploy action/tooling theo plan), quyền **id-token: write** khi dùng OIDC, paths artifact, RBAC và branch/environment protection. Đừng đưa client secret hoặc publishing profile vào source/workflow logs.

### Bốn khóa kiểm soát phát hành

1. **Git commit** cố định.
2. **Artifact checksum** đã kiểm thử.
3. **IaC/config revision** đã phê duyệt.
4. **Host/worker/binding compatibility** phù hợp môi trường.

## 16. Kiểm tra và tạo deployment slot khi được hỗ trợ

Trước tiên xem danh sách slot trên Function App đúng:

~~~bash
RG="<FUNCTION_APP_RESOURCE_GROUP>"
APP="<EXISTING_FUNCTION_APP>"

az functionapp deployment slot list \
  --resource-group "$RG" \
  --name "$APP" \
  --output table
~~~

Nếu plan/OS hỗ trợ và có phê duyệt:

~~~bash
az functionapp deployment slot create \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging
~~~

Slot mới có thể chạy code/triggers và dùng compute plan, nên **có tác động vận hành và chi phí**. Sau khi tạo, cấu hình nguồn event/storage riêng, trigger disablement, identity và sticky settings trước khi deploy code.

### Swap code đã kiểm tra

~~~bash
az functionapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --target-slot production
~~~

**Đây là thao tác production-impacting**, không chạy trong lab dùng chung. Xác nhận Function App/plan hỗ trợ swap, staging đã được kiểm thử, settings sticky đúng, event triggers an toàn, có kế hoạch downtime/rollback và change approval.

Swap có thể gây restart, đổi code và áp dụng config theo quy tắc dịch vụ. **Swap thành công không đồng nghĩa không có event bị lặp, timer chạy nhầm hoặc database side effect**.

## 17. Rollout HTTP-triggered Function bằng slot

Ví dụ Function App production đang phục vụ **v1.4.1**, cần phát hành **v1.4.2**:

1. Build và lưu artifact **v1.4.2** cùng checksum.
2. Kiểm tra staging slot không trỏ nhầm DB/queue production.
3. Deploy artifact lên staging; xác minh Function host nhận diện **ReleaseInfo**.
4. Gọi endpoint staging với Function key phù hợp, kiểm tra **APP_ENV=staging**, **APP_VERSION=1.4.2**.
5. Chạy smoke/integration tests và quan sát latency/error/host logs.
6. Xác nhận sticky settings, phê duyệt và phương án rollback.
7. Swap nếu hosting plan hỗ trợ.
8. Gọi production endpoint, xác nhận release mới, quyền, dependency và SLO.
9. Giữ bản tốt trước đó cho rollback; theo dõi lỗi sau khi chuyển.

### Function key khi smoke test

Với **AuthorizationLevel.FUNCTION**, bạn cần gửi Function key hợp lệ qua kênh bảo mật:

~~~bash
# FUNCTION_KEY được lấy từ secret store, không in ra màn hình.
curl -fsS \
  -H "x-functions-key: $FUNCTION_KEY" \
  "https://<FUNCTION_APP_HOST>/api/release-info"
~~~

Không đưa Function key vào URL được chia sẻ, shell history dưới dạng plaintext, log pipeline hay ticket. Không dùng master key quyền rộng nếu chỉ cần Function-scoped key cho bài test.

**ReleaseInfo** kiểm tra đúng version, không chứng minh downstream/trigger nào cũng khỏe. Kết hợp synthetic requests, Application Insights và business workflow tests.

## 18. Event-driven Function release khác HTTP release

Event sources đưa message tới Functions không phụ thuộc việc người dùng có đang gọi HTTP endpoint không. Deploy có thể làm host restart, listener đăng ký lại hoặc xử lý lại event tùy trigger semantics.

### Kịch bản QueueTrigger

1. Khóa schema message và bảo đảm consumer **backward/forward compatible** theo nhu cầu.
2. Build artifact và kiểm tra checksum.
3. Deploy vào Function App staging chỉ đọc **queue staging**.
4. Test normal, malformed message, retry, duplicate, out-of-order và poison handling.
5. Kiểm tra idempotency của các thao tác ghi dữ liệu/gửi thông báo.
6. Chuẩn bị runbook pause/drain nguồn event khi cần đổi version lớn.
7. Deploy production trong thời điểm được phê duyệt, theo dõi backlog và errors.
8. Nếu lỗi, tạm dừng an toàn, xử lý data/schema compatibility và chỉ rollback khi hợp lệ.

Nhiều event platforms/trigger behaviors có thể dẫn tới **at-least-once delivery** hoặc retry. Không xây nghiệp vụ dựa vào giả định tuyệt đối **exactly once**; cần idempotency/deduplication theo event ID/business key và quy trình xử lý poison/dead-letter.

### Versioned routing, thay vì cùng queue

~~~text
Producer
   |
   +--> orders-v1 queue/topic --> Function v1
   |
   +--> orders-v2 queue/topic --> Function v2
~~~

Sơ đồ là mô hình logic để diễn tả migration có kiểm soát. Thực tế có thể dùng event schema version, routes, topics/subscriptions hoặc consumer groups phù hợp. Không cho v1/v2 cùng đọc một queue production khi chưa hiểu semantics rồi gọi đó là canary.

### TimerTrigger, Event Hubs và Durable Functions

- **Timer:** tắt job staging hoặc dùng schedule/data riêng; kiểm tra host storage và schedule monitor.
- **Event Hubs:** kiểm soát consumer group, checkpoints và replay; hai consumers khác group có thể cùng đọc event.
- **Service Bus:** hiểu subscriptions, lock, retries, dead-letter và việc nhiều listeners dùng cùng subscription.
- **Durable:** giữ orchestrator deterministic, xét in-flight instances và task hubs; không coi swap là state migration.

## 19. Semantic versioning cho API và event contracts

Quản lý version của Function app cần tương thích dữ liệu:

| Đối tượng | Thay đổi thường an toàn hơn | Thay đổi dễ gây lỗi |
|---|---|---|
| HTTP API | Thêm trường tùy chọn và giữ route cũ | Xóa trường client đang đọc |
| Queue message | Thêm trường có default, consumer bỏ qua unknown fields | Đổi ý nghĩa trường bắt buộc |
| Database | Expand-and-contract migration | Xóa cột trước khi mọi consumer được nâng |
| Durable orchestration | Giữ code cũ cho in-flight instances | Thay flow làm mất determinism |
| App settings | Thêm default/validate config | Đổi setting name không cập nhật IaC |
| Timer job | Idempotency và checkpoint | Giả định job không bao giờ retry |

Ví dụ hai HTTP API versions:

~~~text
GET /api/v1/orders/{id}
GET /api/v2/orders/{id}
~~~

Các route **v1/v2** là phiên bản **hợp đồng API**, không phải Functions host version. Bạn có thể giữ cả hai trong một Function App hoặc tách thành apps riêng tùy SLA/ownership và cách routing.

**Semantic Versioning** giúp người dùng biết mức độ thay đổi theo MAJOR.MINOR.PATCH, còn **Git SHA/checksum** giúp biết chính xác artifact đang chạy. Không dùng tag mutable **latest** làm bằng chứng release.

## 20. Nâng host, Java và binding extensions

### Functions host runtime

**FUNCTIONS_EXTENSION_VERSION** chọn major host tương ứng với hỗ trợ của nền tảng. Trước khi nâng:

- Xem lifecycle support/breaking changes chính thức.
- Kiểm tra language worker, bindings, host.json và deployment plan.
- Thử staging với trigger/data source tương đương nhưng cách ly.
- Giữ artifact và IaC revision cũ để rollback nếu được hỗ trợ.

### Java runtime

Cần đồng bộ:

1. JDK của CI.
2. **maven-compiler-plugin** source/target/release.
3. Java runtime được chọn cho Function App trên Azure.
4. Functions Java SDK, Maven plugin và thư viện liên quan.

Nếu CI compile Java 21 bytecode nhưng Function App chạy Java 17, có thể gặp **UnsupportedClassVersionError**. Đổi Functions host từ **~4** sang một giá trị phỏng đoán không giải quyết được lỗi bytecode.

### Binding extensions

Các trigger/bindings (Storage Queue, Blob, Service Bus, Event Hubs...) có extension versions và metadata riêng. Với Java, Maven plugin và Functions host tạo/nạp binding metadata như **function.json**. Một số mô hình ngôn ngữ dùng **extension bundles** trong host.json, một số tham chiếu extension packages theo cách khác.

**Không tự áp một host.json extensionBundle range từ bài viết cũ cho mọi project Java**. Kiểm tra hướng dẫn Java Functions/hosting runtime thực tế, chạy test trigger bằng sự kiện thật trong môi trường sandbox và xác nhận logs không có binding load error.

## 21. Quản trị cấu hình bằng Infrastructure as Code

Một bản release production phụ thuộc nhiều tài nguyên hơn JAR:

- Function App và hosting plan, region, OS/runtime.
- Storage cho host, queue/topic/event source, database.
- Managed identity và role assignments.
- App settings, Key Vault references và slot stickiness.
- VNet Integration, Private Endpoint, DNS/egress và firewall nếu có.
- Application Insights, Log Analytics, alert rules và Action Groups.
- Azure Policy, tags, locks, budget và role cho CI/CD.

Hãy khai báo cấu hình qua **Bicep, Terraform hoặc ARM** theo chuẩn tổ chức; tránh tạo môi trường bằng chuỗi thao tác Portal thủ công không thể tái lập.

Ví dụ **mô hình IaC khái niệm** (không phải Bicep/Terraform/YAML Azure deployment hợp lệ):

~~~yaml
functions:
  - name: fa-orders-stg
    environment: staging
    runtime:
      hostMajor: 4
      worker: java
      javaVersion: 17
    hostStorage: stordersstg
    eventSource: orders-staging
    identity: managed
    appSettings:
      APP_ENV: staging
      ORDERS_QUEUE_NAME: orders-staging
    keyVaultReferences:
      DB_SECRET: staging-db-secret

  - name: fa-orders-prod
    environment: production
    runtime:
      hostMajor: 4
      worker: java
      javaVersion: 17
    hostStorage: stordersprod
    eventSource: orders-production
    identity: managed
~~~

Trong CI/CD, có thể dùng **plan → review → apply** và lưu revision để phát hiện **configuration drift**. Nếu người vận hành tạm disable Function khi xảy ra sự cố, pipeline IaC không nên tự bật nó trở lại mà không có quy trình hòa giải thay đổi và phê duyệt.

**IaC không thay thế dữ liệu backup hoặc khôi phục message.** Deploy infrastructure thành công vẫn có thể khiến Java Function không nhận diện trigger nếu package sai.

## 22. Kiểm thử release trước và sau deployment

| Giai đoạn | Phép kiểm tra | Điều chứng minh |
|---|---|---|
| Pull request | Unit tests, lint, SCA | Code/dependency không lỗi cơ bản |
| Build | Maven compile/package, checksum | Artifact tạo đúng, traceable |
| Local | Core Tools + Azurite hoặc test endpoints | Function metadata/logic chạy local |
| Dev | Identity/network/binding integration tests | App tương tác được với phụ thuộc dev |
| Staging | Contract tests, retries, duplicate events, smoke tests | Hành vi gần production nhưng an toàn dữ liệu |
| Pre-prod | Config/runtime diff, plan support, approvals | Giới hạn rủi ro cấu hình và triển khai |
| Post-prod | ReleaseInfo, trigger, monitoring/SLO | Bản mới hoạt động thật |
| Rollback rehearsal | Re-deploy bản cũ, xử lý event schema | Có đường quay lại đáng tin |

**HTTP smoke test** không nên ghi dữ liệu thật. **Event smoke test** chỉ dùng queue/topic sandbox và message giả. Khi test Durable Functions, cần xác định task hub và orchestration instances riêng, tránh can thiệp trạng thái đang chạy ở production.

### Kiểm tra package

Một build Java có thể kết thúc với nhiều file trong thư mục target. Trước khi deploy, kiểm tra package có:

1. **host.json** đúng schema/config.
2. **function.json** được plugin tạo cho từng Function.
3. JAR/class files và dependencies đủ.
4. Function names/route/trigger metadata khớp source.
5. Không có local.settings.json chứa secret, source map nhạy cảm hoặc file không cần thiết.

**Deploy status thành công không bảo đảm host đã discover hết Function methods**. Luôn kiểm tra Function list/host logs ở đích.

## 23. Quan sát sau deploy qua Azure Monitor và Application Insights

Một bản phát hành chỉ an toàn khi các tín hiệu vận hành ổn định:

| Tín hiệu | Dùng để xác minh |
|---|---|
| Function discovery và host startup | Host load đầy đủ Function, không lỗi extension |
| Invocation count/success/failure | Trigger thực sự gọi code và không tăng lỗi |
| Duration p50/p95/p99 | Có chậm hơn bản trước hoặc vượt SLO? |
| Queue depth/oldest event age | Consumer có theo kịp producer? |
| Retries/dead-letter/poison messages | Event nào xử lý hỏng hoặc lặp? |
| Dependency failures | Storage/Key Vault/Service Bus/database có lỗi IAM/network? |
| Cold start/instance metrics | Runtime/plan có bottleneck? |
| Cost/usage | Execution/compute, Storage, telemetry, egress |

**Application Insights** có thể thu request, exception, dependency và trace của Functions theo mô hình tích hợp. Bảng/cột Log Analytics có thể khác nhau giữa workspace-based Application Insights và classic experiences; không sao chép query nếu schema chưa được xác minh.

Ví dụ KQL trong môi trường có bảng **AppRequests**:

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    Invocations = count(),
    Failures = countif(Success == false)
  by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Đây là ví dụ khi bảng/cột thực sự tồn tại; với non-HTTP triggers hoặc telemetry khác, cần xem **AppTraces, AppExceptions** hay schema thực tế. Không mặc định mọi invocation đều tương ứng một AppRequests row.

Nên gắn **APP_VERSION**, Git SHA và environment vào telemetry dưới dạng custom dimensions theo khả năng SDK, **không gắn connection strings hoặc khách hàng định danh nhạy cảm**.

### Cảnh báo deployment gây regression

Một alert production tốt cần có:

- Ngưỡng error rate hoặc latency liên hệ với SLO.
- Thời gian quan sát để tránh nhiễu từ cold start/traffic thấp.
- Tín hiệu absence khi không còn metrics hoặc trigger không gọi.
- Action Group/on-call recipient, escalation và runbook.
- Bản release cụ thể, thời gian rollout và điều kiện rollback.

Không chỉ dựa vào một màn hình xanh trong Deployment Center.

## 24. Chẩn đoán lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Deploy báo thành công nhưng không thấy Function | Package sai root, function.json thiếu, host load/binding lỗi | Package output, host logs, Function list |
| Java UnsupportedClassVersionError | Compiler target mới hơn Java runtime Azure | JDK, Maven compiler release, app stack |
| HTTP Function trả 401 | Function key thiếu/sai, authLevel và access control | Endpoint/function key scope, identity |
| HTTP Function trả 500 | Java exception, thiếu settings, dependency lỗi | Application Insights, worker logs, exception |
| TimerTrigger không chạy | Function disabled, lịch/timezone/host state, quyền Storage | Config, host logs, schedule monitor |
| QueueTrigger không chạy | Sai connection/queue, thiếu quyền, trigger disabled, network | App settings, data RBAC, logs |
| Staging xử lý event production | Source/sticky settings sai, triggers chưa tắt | Queue identity/resource IDs, slot diff |
| Maven deploy thất bại | Plugin target, version hoặc quyền Azure sai | POM, Maven output, plan/OS support |
| ZIP Deploy lỗi trên Flex | Phương thức deployment không tương thích | Dùng One Deploy/tooling hỗ trợ Flex |
| Key Vault reference không resolve | Identity thiếu quyền, secret URI/DNS/firewall lỗi | Reference status, Key Vault IAM, networking |
| Swap xong production lỗi | Settings không sticky, runtime/config drift | Slot config, logs, smoke tests và rollback |
| Queue backlog tăng sau release | Consumer chậm/lỗi, retries, batch/concurrency thay | Invocation duration, retry/dead-letter |
| Rollback code nhưng lỗi dữ liệu vẫn còn | Schema/database/side effects đã thay | Contract/migration/reconciliation plan |
| Host không load extension | Binding version/host runtime không tương thích | host.json, dependency versions, trigger logs |

**Chỉ sửa một lớp mỗi lần** dựa trên bằng chứng. Đổi đồng thời Functions host, Java worker, Storage connection và artifact sẽ che giấu nguyên nhân gốc.

## 25. Tình huống A: staging đọc nhầm queue production

Một nhóm deploy **ProcessOrders** lên staging slot. Do slot copy settings production, QueueTrigger staging kết nối vào **orders-production**, và một số message thật đã bị xử lý bởi phiên bản chưa duyệt.

### Phân tích

Lỗi nằm ở **environment isolation**, không phải bug của Queue Storage. Có thể đã xảy ra consume/tranh giành message, side effects hoặc duplicate processing tùy broker và consumer semantics.

### Runbook

1. Dừng hoặc disable **listener staging** có kiểm soát; tránh thao tác nhầm production.
2. Ghi timeline, affected message IDs, trạng thái queue, dead-letter và audit.
3. Đối chiếu **resource IDs**, app settings/slot settings và managed identity scopes.
4. Cấu hình queue/test sources riêng; đặt sticky settings theo policy.
5. Dùng **AzureWebJobs.ProcessOrders.Disabled=true** tại staging nếu chưa cần chạy trigger.
6. Thử với message giả và xác nhận staging không chạm production.
7. Kiểm tra dữ liệu cần bù/replay/deduplicate theo logic nghiệp vụ.
8. Thêm CI check ngăn staging trỏ tới production queue hoặc Key Vault.

**Không xóa queue production hoặc reset checkpoints bừa bãi để "sửa nhanh"**. Phải bảo vệ các message chưa xử lý và dữ liệu audit.

## 26. Tình huống B: nâng Java mà Function không chạy

CI chuyển build từ Java 17 lên Java 21 nhưng Function App Azure vẫn dùng Java 17. Maven package và publish hoàn tất; sau đó logs có:

~~~text
java.lang.UnsupportedClassVersionError:
... compiled by a more recent version of the Java Runtime
~~~

### Quy trình xử lý

1. Ghi artifact checksum, Git SHA và Java version Azure.
2. Kiểm tra JDK/target bytecode và dependencies ở CI.
3. Xác minh Java 21 được hỗ trợ trên **plan/OS/region/runtime hiện tại** hay chưa.
4. Nếu chưa, **redeploy artifact Java 17 đã kiểm chứng** hoặc tạo build mới với target phù hợp (ghi checksum mới).
5. Chạy smoke/integration tests và xem host/worker logs.
6. Lập kế hoạch nâng Java trên staging trước, sau đó mới production.

**Không tự đổi FUNCTIONS_EXTENSION_VERSION từ ~4** như cách chữa UnsupportedClassVersionError; đó là lớp version khác.

## 27. Tình huống C: rollback khi event schema đã thay

Function **v2** bắt đầu đọc schema OrderCreatedV2 và migration database. Sau 20 phút, errors tăng và nhóm muốn quay về v1.

Các rủi ro:

- Message mới có field/type v1 không hiểu.
- Một phần messages đã được v2 consume và ghi dữ liệu.
- Database có thể không còn tương thích code v1.
- Durable instances có lịch sử ở version v2.

### Runbook

1. Nếu cần, tạm dừng producer/consumer theo cách không làm mất events, ghi snapshot/timeline/backlog.
2. Xác minh matrix tương thích **v1 code ↔ v2 messages ↔ current DB**.
3. Nếu v1 không xử lý an toàn, ưu tiên compatibility hotfix hoặc route sang consumer phù hợp, không rollback mù.
4. Khi có thể quay lại, deploy artifact v1 đã biết tốt; kiểm tra triggers và quyền.
5. Đánh giá backfill, compensation hoặc restore dữ liệu có kiểm soát.
6. Quan sát dead-letter, retry, queue age và business reconciliation.

**Rollback code không đảo ngược email đã gửi, đơn hàng đã xử lý hoặc transaction đã commit.** Do đó phải chuẩn bị schema evolution và idempotency trước khi phát hành.

## 28. Bài lab: thiết kế pipeline ba môi trường

### Bối cảnh

Hệ thống **OrdersFunctions** có:

- **ReleaseInfo**: HTTP Function đọc APP_ENV và APP_VERSION.
- **ProcessOrders**: QueueTrigger nhận order-created events.
- **CleanupExpiredOrders**: TimerTrigger dọn dữ liệu hết hạn theo policy.

Yêu cầu: dev/staging không được chạm dữ liệu production, production chỉ cập nhật sau kiểm thử staging, có rollback plan và chi phí quan sát được.

### Phần A: làm ma trận tài nguyên

| Thành phần | Dev | Staging | Production |
|---|---|---|---|
| Function App | fa-orders-dev | fa-orders-stg | fa-orders-prod |
| Queue source | orders-dev | orders-stg | orders-prod |
| Timer | Dev schedule/disabled | Disabled hoặc isolated | Schedule đã phê duyệt |
| Host Storage | Storage dev | Storage stg | Storage prod |
| Database | Test | Safe test | Production |
| Identity | MI-dev | MI-stg | MI-prod |
| Key Vault | KV-dev | KV-stg | KV-prod |
| Telemetry | Dev workspace/app | Staging | Production alerts |
| Release gate | CI | QA approval | Protected approval |

Đây là phương án **Function Apps riêng**. Nếu dùng slots, phải thiết kế lại sticky settings, identity, data sources và kế hoạch tắt triggers, đồng thời xác nhận plan support.

### Phần B: khám phá Function App bằng CLI (read-only)

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<LAB_RESOURCE_GROUP>"
APP="<LAB_FUNCTION_APP>"

az functionapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,state:state,kind:kind}" \
  --output json

az functionapp function list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].{name:name}" \
  --output table

az functionapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].{name:name,slotSetting:slotSetting}" \
  --output table
~~~

Chỉ áp dụng cho app được phép xem. Không bỏ phần query lọc tên app settings vì output mặc định có thể chứa secrets.

### Phần C: build Java local

1. Tạo project Java Functions Maven theo template chính thức, thêm **ReleaseInfo** từ mục 5.
2. Tạo local.settings.json với Azurite/Storage sandbox, không commit secrets.
3. Chạy **mvn -B clean test**, **mvn -B package**, **mvn azure-functions:run**.
4. Gọi **/api/release-info** trên localhost và xác nhận môi trường/version.
5. Lưu Git SHA, JDK, Maven/plugin versions và artifact checksum.

### Phần D: deployment sandbox (nếu có quyền)

1. Kiểm tra **appName, resourceGroup, runtime, hosting plan** trong Maven/pipeline.
2. Dùng deployment identity chỉ có quyền tới app staging/lab.
3. Đặt APP_ENV=staging, APP_VERSION=1.4.2 và nguồn QueueTrigger staging.
4. Deploy bằng phương thức **hỗ trợ hosting plan**, không mặc định dùng ZIP Deploy.
5. Kiểm tra Function discovery, HTTP invocation có auth, host/worker logs.
6. Chạy event tests với **queue staging**: normal, duplicate, invalid payload và retry.
7. Kiểm tra telemetry/alerts và lập bản phê duyệt production trên giấy.
8. Không tự deploy production hoặc sửa live trigger chỉ vì bài lab.

### Bảng bằng chứng

| Bằng chứng | Điều cần ghi nhận |
|---|---|
| Source/release | Commit, semantic version, artifact checksum |
| Platform | Function App, plan, region, OS, host/Java versions |
| Config | APP_ENV, APP_VERSION, names của connection settings không lộ secrets |
| Isolation | Staging queue/DB/host storage/identity thực sự khác prod |
| Function discovery | ReleaseInfo, ProcessOrders, CleanupExpiredOrders theo cấu hình |
| Smoke test | HTTP trả đúng version; event staging được xử lý |
| Observability | Invocation logs, failures, duration, retries, backlog |
| Rollback | Artifact cũ, schema compatibility, event handling plan |
| Security | Managed identity, Key Vault, least-privilege deploy |
| Cost | Tài nguyên phát sinh, cleanup và owner |

Nếu chỉ có quyền read-only, hoàn thành **phần A và B** cùng thiết kế rollout/rollback là đủ; không cần yêu cầu quyền prod để chứng minh kiến thức.

## 29. Chi phí và vòng đời tài nguyên

Tách môi trường tốt giúp tăng an toàn nhưng có chi phí:

| Thành phần | Chi phí có thể phát sinh |
|---|---|
| Function App execution/compute | Theo plan, execution/time, memory/concurrency, instance |
| Premium/Dedicated plan | Capacity được cấp phát, kể cả thời gian ít requests |
| Slots/staging | Tài nguyên compute/scale và các service phụ trợ |
| Azure Storage | Host state, queue events, packages, logs và transactions |
| Service Bus/Event Hubs | Messages, throughput, retention/tier |
| Application Insights/Log Analytics | Telemetry ingestion, retention, alerts |
| Key Vault/private networking | Secret operations, private endpoints, DNS/NAT |
| CI/CD | Runners, artifact storage, scanning, registry |

Đặt tags **environment, owner, application, costCenter** theo chính sách và dùng Cost Management. **Budget alerts không tự dừng phát sinh phí.** Một staging Function chạy Timer mỗi phút hoặc logging quá nhiều có thể làm ngân sách tăng dù không có người dùng thật.

### Dọn lab an toàn

- Chỉ xóa Function Apps, queues, storage hoặc resource groups **do chính bài lab tạo và sở hữu riêng**.
- Không xóa Storage chứa host state của các apps khác hoặc queue còn message cần xử lý.
- Với app dùng chung, đưa settings về giá trị trước khi thực hành có change record.
- Kiểm tra tài nguyên qua ARM và báo cáo chi phí cập nhật trễ.

## 30. Checklist phát hành Function production

- [ ] Hosting plan, OS, runtime, scale và deployment method tương thích.
- [ ] Source SHA, artifact checksum và release manifest được lưu.
- [ ] Functions host major, language worker, Java target và binding extensions đã kiểm thử.
- [ ] Dev/staging/prod có data sources, host storage, identities và IAM riêng hoặc slot isolation đã được xác minh.
- [ ] Staging Timer/Queue/Event/Durable triggers không xử lý dữ liệu production ngoài chủ đích.
- [ ] App settings và Key Vault references có scope đúng, secrets không có trong source/pipeline logs.
- [ ] CI build một lần, có tests/scanning/approvals, promote cùng artifact.
- [ ] IaC đã review, không bị drift hoặc ghi đè cấu hình cứu hộ ngoài ý muốn.
- [ ] Deployment slot/Swap chỉ dùng khi plan hỗ trợ, sticky settings và side effects đã kiểm tra.
- [ ] HTTP/event schema và DB migration bảo đảm compatibility.
- [ ] Retry, poison/dead-letter, idempotency và backlog/runbook được chuẩn bị.
- [ ] Azure Monitor, Application Insights, alerts và release metadata đủ để truy vết.
- [ ] Có kế hoạch rollback artifact **và** xử lý dữ liệu/event side effects.
- [ ] Post-deploy xác minh Function discovery, trigger state, version, invocations và SLO.
- [ ] Đã tính chi phí của từng môi trường, plan, storage và telemetry.

## 31. Câu hỏi tự kiểm tra

1. Function khác Function App thế nào và vì sao deployment thường ở cấp app?
2. Tại sao không sử dụng cùng lệnh ZIP Deploy cho mọi Functions hosting plans?
3. Khi nào nên dùng Function Apps riêng thay vì deployment slots?
4. FUNCTIONS_EXTENSION_VERSION=~4 có phải release 4 của Java Function không?
5. FUNCTIONS_WORKER_RUNTIME=java có tự đặt Java 17/21 không?
6. host.json version=2.0 có phải Functions host runtime 2 không?
7. Vì sao upload một JAR chưa chắc đủ để Azure host discover Function?
8. Điều gì có thể xảy ra nếu staging QueueTrigger đọc queue production?
9. Sticky slot settings bảo vệ điều gì khi swap?
10. Vì sao dùng chung AzureWebJobsStorage cần xem host identity và timer/lease state?
11. Tại sao APP_ENV=staging không phải security boundary?
12. Managed identity và deployment identity khác nhau thế nào?
13. Lý do dùng Key Vault references thay cho plaintext secrets trong CI/CD?
14. Build once, deploy many khác việc hai jobs cùng build một Git commit như thế nào?
15. UnsupportedClassVersionError xuất hiện khi nào?
16. Vì sao Durable Functions cần lưu ý in-flight orchestration instances khi nâng code?
17. Rollback code có hoàn tác message đã consume và DB migrations không?
18. Sau khi CLI báo deploy thành công, còn cần kiểm tra những telemetry/trigger nào?
19. Canary deployment cho HTTP Function khác event-driven Function ở đâu?
20. Vì sao budget alert không đủ để giới hạn chi phí staging?

## 32. Tài liệu tham khảo

- [Azure Functions overview](https://learn.microsoft.com/azure/azure-functions/functions-overview) — khái niệm Functions và ứng dụng.
- [Azure Functions hosting options](https://learn.microsoft.com/azure/azure-functions/functions-scale) — các plan, scale và giới hạn.
- [Azure Functions deployment technologies](https://learn.microsoft.com/azure/azure-functions/functions-deployment-technologies) — các phương thức triển khai.
- [Azure Functions runtime versions](https://learn.microsoft.com/azure/azure-functions/functions-versions) — host và language runtime.
- [Java developer guide for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-java) — Java annotations, Maven và package.
- [Create a Java Function](https://learn.microsoft.com/azure/azure-functions/create-first-function-cli-java) — quy trình khởi tạo/triển khai.
- [Azure Functions deployment slots](https://learn.microsoft.com/azure/azure-functions/functions-deployment-slots) — slots, swap và settings.
- [Azure Functions app settings reference](https://learn.microsoft.com/azure/azure-functions/functions-app-settings) — runtime và connection settings.
- [Disable functions](https://learn.microsoft.com/azure/azure-functions/disable-function) — tắt từng Function.
- [Azure Functions best practices](https://learn.microsoft.com/azure/azure-functions/functions-best-practices) — reliability và vận hành.
- [Durable Functions versioning](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-versioning) — workflow dài hạn.
- [Key Vault references](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references) — secret references và managed identity.
- [Azure Functions monitoring](https://learn.microsoft.com/azure/azure-functions/functions-monitoring) — telemetry/alerts.
- [Azure CLI az functionapp](https://learn.microsoft.com/cli/azure/functionapp) — đọc cấu hình, triển khai và slots.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — dự toán compute/storage/monitoring.

**Kết luận:** Triển khai Azure Functions an toàn không chỉ là publish mã nguồn. Bạn phải quản lý **mã và artifact được phiên bản hóa, host và language runtime tương thích, cấu hình và dữ liệu tách biệt giữa môi trường, trigger không xử lý nhầm sự kiện, quyền tối thiểu, kiểm thử và quan sát sau deploy**. Với HTTP Functions có thể sử dụng slot khi plan hỗ trợ; với Functions xử lý event cần đặc biệt chú ý idempotency, nguồn dữ liệu và trạng thái đang xử lý. Một bản phát hành chỉ hoàn tất khi được xác minh bằng tín hiệu nghiệp vụ và có phương án rollback thực sự an toàn.
