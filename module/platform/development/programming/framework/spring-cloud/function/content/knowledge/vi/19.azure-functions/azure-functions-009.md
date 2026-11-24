# Cấu hình môi trường, quyền truy cập và triển khai Azure

## 1. Mục tiêu: đưa Spring Cloud Function vào môi trường Azure an toàn

**Spring Cloud Function (SCF)** cho phép phát triển logic nghiệp vụ tái sử dụng bằng `Supplier<T>`, `Function<T,R>` và `Consumer<T>`. `FunctionCatalog` đăng ký/tra cứu các hàm, hỗ trợ composition và các adapter giúp cùng một logic được gọi qua HTTP, queue, event hoặc môi trường serverless khác.

Khi đưa ứng dụng lên **Azure Functions**, code và package chỉ là một phần của quá trình phát hành. Function App còn cần cấu hình môi trường, quyền truy cập tới dịch vụ bên ngoài, cơ chế xác thực người gọi và chính sách triển khai phù hợp với hosting plan.

Bài này đi theo một tình huống thực tế: một Function App xử lý đơn hàng, đọc ngưỡng ưu tiên từ cấu hình, nhận request HTTP, ghi dữ liệu hoặc gửi message sang Azure Storage/Service Bus, và cần kết nối Key Vault khi có secret.

Sau bài học, bạn có thể:

1. Tách cấu hình giữa source code, Spring Boot properties, Azure Host settings, local settings và Azure App Settings.
2. Dùng Spring profiles và `@ConfigurationProperties` để cấu hình nghiệp vụ theo môi trường.
3. Phân biệt quyền deploy Function App với quyền runtime của ứng dụng.
4. Bật system-assigned hoặc user-assigned managed identity.
5. Cấp Azure RBAC đúng scope và đúng data-plane role.
6. Dùng identity-based connection cho `AzureWebJobsStorage` và binding.
7. Dùng Key Vault references hoặc Azure SDK khi dịch vụ còn cần secret.
8. Phân biệt xác thực inbound HTTP với xác thực outbound tới Azure resources.
9. Chọn deployment method theo hosting plan, thiết kế CI/CD, smoke test và rollback.

**Nguyên tắc xuyên suốt:** mỗi môi trường cần cấu hình và danh tính riêng; runtime identity chỉ có quyền tối thiểu để xử lý công việc; deployment identity chỉ có quyền cần thiết để phát hành code và cấu hình.

## 2. Bản đồ các lớp cấu hình

Một Azure Function App thường có nhiều nguồn cấu hình. Chúng có phạm vi và thời điểm đọc khác nhau.

| Nguồn | Ai đọc? | Phạm vi | Ví dụ |
| --- | --- | --- | --- |
| Java source / default values | Ứng dụng | Logic và giá trị mặc định an toàn | Quy tắc parse, default threshold. |
| `application.properties` | Spring Boot | Spring Environment / bean configuration | `orders.threshold`, log level. |
| Spring profile files | Spring Boot | Một profile được kích hoạt | `application-prod.properties`. |
| `host.json` | Azure Functions Host | Tất cả functions trong Function App | Host logging, timeout, extension options. |
| `local.settings.json` | Core Tools local | Môi trường chạy trên máy dev | `FUNCTIONS_WORKER_RUNTIME`, local connection. |
| Azure App Settings | Azure platform và process runtime | Function App trên cloud | `MAIN_CLASS`, `SPRING_PROFILES_ACTIVE`, connection settings. |
| Managed Identity / Azure RBAC | Microsoft Entra ID và dịch vụ đích | Danh tính runtime hoặc deploy | Quyền đọc Key Vault, ghi Queue. |
| Key Vault | Azure platform hoặc Azure SDK | Secret values | Database password, API token khi không thể dùng identity trực tiếp. |

Azure lưu App Settings ở mức Function App và đưa chúng vào process như **environment variables**; các function trong cùng Function App dùng chung cấu hình đó. Thay đổi App Settings thường khiến Function App restart. Vì vậy, các workload cần giá trị cấu hình hoặc lịch scale khác nhau nên được phân chia thành Function Apps riêng khi có lý do vận hành rõ. Tham khảo [Function App settings](https://learn.microsoft.com/en-us/azure/azure-functions/functions-how-to-use-azure-function-app-settings) và [App settings reference](https://learn.microsoft.com/en-us/azure/azure-functions/functions-app-settings).

### 2.1. Không nhầm ba file cấu hình

**`host.json`** thuộc Azure Functions Host, không phải file Spring Boot. Nó áp dụng cho toàn bộ functions trong cùng Function App.

**`local.settings.json`** dùng bởi Azure Functions Core Tools khi chạy local. Nó chứa bản sao các app settings cần thiết cho máy dev; không được tự động publish lên Azure theo mặc định và có thể chứa secret, nên không commit.

**`application.properties`** thuộc Spring Boot. Nó cấu hình Spring beans, profiles, logging và nghiệp vụ. Spring Boot cũng có thể nhận giá trị override từ environment variables do Azure App Settings cung cấp.

### 2.2. Ranh giới host settings và business settings

Ví dụ:

~~~json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true
      }
    }
  }
}
~~~

Đây là một phần cấu hình host minh họa. Ngưỡng đơn hàng, URL đối tác hoặc feature flags thuộc **Spring/application configuration**, không nên nhét vào `host.json` chỉ vì chúng được dùng trong Azure.

## 3. Thiết kế môi trường dev, staging và production

Một cách tổ chức dễ vận hành là tách các môi trường bằng **Function App và tài nguyên phụ trợ riêng**:

~~~mermaid
flowchart TB
    subgraph Dev["Development"]
      D["Function App: orders-dev"]
      DS["Storage dev"]
      DK["Key Vault dev"]
      DI["Managed Identity dev"]
      D --> DS
      D --> DK
      D --> DI
    end
    subgraph Stage["Staging"]
      S["Function App: orders-staging"]
      SS["Storage staging"]
      SK["Key Vault staging"]
      SI["Managed Identity staging"]
      S --> SS
      S --> SK
      S --> SI
    end
    subgraph Prod["Production"]
      P["Function App: orders-prod"]
      PS["Storage prod"]
      PK["Key Vault prod"]
      PI["Managed Identity prod"]
      P --> PS
      P --> PK
      P --> PI
    end
    A["Cùng source code / versioned artifact"] --> D
    A --> S
    A --> P
~~~

Mỗi Function App có thể dùng cùng code artifact nhưng App Settings, identity, RBAC, network access và downstream resources riêng.

| Thuộc tính | Dev | Staging | Production |
| --- | --- | --- | --- |
| Storage | Tài khoản thử nghiệm | Tài khoản pre-prod | Tài khoản production |
| Key Vault | Vault dev | Vault staging | Vault production |
| Managed identity | Chỉ quyền dev | Quyền kiểm thử | Quyền tối thiểu thật |
| Spring profile | `dev` | `staging` | `prod` |
| Telemetry | Log phục vụ debug | Theo dõi smoke/load test | Alert, retention và audit |
| Inbound access | Giới hạn nhóm dev | Tester/gateway | Entra auth/API gateway/network policy |
| Deploy | Theo nhánh dev | Sau kiểm thử | Qua release gate và approval |

Không dùng một storage account production cho local testing hoặc staging chỉ để tiết kiệm cấu hình. Trigger có thể thật sự consume message, ghi dữ liệu và gây side effect. Tách dữ liệu giúp kiểm thử rollback, retry và idempotency an toàn hơn.

### 3.1. Function App là một ranh giới cấu hình và scale

Các functions trong cùng Function App:

- Chia sẻ App Settings và host configuration.
- Được deploy cùng nhau.
- Chia sẻ tài nguyên theo instance khi app scale.
- Có cùng OS/runtime/hosting plan constraints.

Nếu hai nhóm function cần secret, quyền, network policy, scale hoặc lịch phát hành khác nhau, hãy cân nhắc tách Function App. Không nên tách chỉ vì có nhiều `@Bean Function`; Spring function beans vẫn có thể được composition và tái sử dụng trong cùng application.

## 4. Cấu hình nghiệp vụ trong Spring Boot

### 4.1. Định nghĩa configuration properties

Không hard-code ngưỡng đơn hàng trong functional bean. Tạo `src/main/java/example/azure/OrderProperties.java`:

~~~java
package example.azure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public record OrderProperties(
        long threshold,
        String prefix) {
}
~~~

Trong class Spring Boot chính, bật configuration properties scanning:

~~~java
package example.azure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderFunctionApplication.class, args);
    }
}
~~~

`OrderProperties` là cấu hình nghiệp vụ. Nó không phụ thuộc Azure SDK, nên cùng class này có thể được dùng trong test hoặc một adapter khác.

### 4.2. Giá trị mặc định trong application.properties

`src/main/resources/application.properties`:

~~~properties
orders.threshold=1000000
orders.prefix=REF-
spring.application.name=orders-function
~~~

Đây là **default config an toàn**, không phải secret. Azure App Settings hoặc profile-specific properties có thể override các giá trị này.

### 4.3. Function bean sử dụng cấu hình

~~~java
@Bean
Function<String, String> normalizeOrder(OrderProperties properties) {
    return raw -> {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("Mã đơn rỗng");
        }
        return properties.prefix()
                + raw.strip().toUpperCase(Locale.ROOT);
    };
}

@Bean
Function<OrderInput, OrderDecision> classifyOrder(
        OrderProperties properties) {
    return order -> new OrderDecision(
            order.id(),
            order.totalVnd(),
            order.totalVnd() >= properties.threshold()
                    ? "PRIORITY" : "STANDARD");
}
~~~

Đây là các method minh họa cần đặt trong Spring configuration class có imports và domain records tương ứng. Function bean vẫn là `Function` thuần; cấu hình được inject lúc Spring context khởi tạo.

### 4.4. Override bằng environment variables

Spring Boot ánh xạ canonical property names sang environment variable theo quy tắc: thay dấu chấm bằng dấu gạch dưới, bỏ dấu gạch nối, rồi viết hoa. Vì vậy:

| Spring property | Environment variable |
| --- | --- |
| `orders.threshold` | `ORDERS_THRESHOLD` |
| `orders.prefix` | `ORDERS_PREFIX` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |

Ví dụ App Settings cho staging:

~~~text
SPRING_PROFILES_ACTIVE=staging
ORDERS_THRESHOLD=1500000
ORDERS_PREFIX=STG-
~~~

Không dùng `ORDERS_PRIORITY_THRESHOLD` cho property `orders.priority-threshold` nếu chưa đối chiếu quy tắc binding; dấu gạch nối bị loại bỏ trong cách ánh xạ environment variable của Spring Boot.

### 4.5. Spring profiles

Có thể tạo:

~~~text
application.properties
application-dev.properties
application-staging.properties
application-prod.properties
~~~

Ví dụ `application-prod.properties`:

~~~properties
orders.threshold=2000000
orders.prefix=ORD-
logging.level.example.azure=INFO
~~~

Kích hoạt profile bằng App Setting `SPRING_PROFILES_ACTIVE=prod`. Hãy kiểm tra startup log để biết profile nào đang active. Không đóng gói secret vào file `application-prod.properties` trong source repository.

## 5. Quản lý Azure App Settings

### 5.1. Những settings thường gặp

| Setting | Vai trò |
| --- | --- |
| `FUNCTIONS_WORKER_RUNTIME=java` | Chọn Java language worker. |
| `FUNCTIONS_EXTENSION_VERSION=~4` | Chọn Azure Functions runtime 4.x. |
| `MAIN_CLASS` | Spring application class khi adapter/build cần khai báo tường minh. |
| `SPRING_PROFILES_ACTIVE` | Spring profile. |
| `ORDERS_THRESHOLD` | Cấu hình nghiệp vụ ví dụ. |
| `AzureWebJobsStorage` | Host storage connection hoặc identity-based connection. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Application Insights connection nếu dùng dạng connection string. |

Chỉ khai báo setting thực sự cần cho app và hosting plan. Một số giá trị được Azure tạo sẵn khi Function App được provision; không ghi đè chúng một cách tùy tiện.

### 5.2. Đặt settings bằng Azure Portal

1. Mở Function App đúng môi trường.
2. Vào **Settings → Environment variables → App settings**.
3. Thêm hoặc cập nhật tên và giá trị setting.
4. Lưu thay đổi và xác nhận app restart nếu platform yêu cầu.
5. Kiểm tra function startup và behavior sau khi restart.

App Settings được Azure mã hóa khi lưu trữ, nhưng người có quyền đọc cấu hình vẫn có thể xem chúng. Không coi “encrypted at rest” là lý do để đưa mọi password/token trực tiếp vào setting; ưu tiên Managed Identity hoặc Key Vault reference.

### 5.3. Đặt settings bằng Azure CLI

Ví dụ cập nhật các giá trị không bí mật:

~~~bash
az functionapp config appsettings set \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --settings \
    SPRING_PROFILES_ACTIVE=staging \
    ORDERS_THRESHOLD=1500000 \
    ORDERS_PREFIX=STG-
~~~

Lệnh này **thay đổi cấu hình cloud** và thường làm Function App restart. Thay placeholder bằng tài nguyên đã được cấp phép, kiểm tra subscription trước khi thực hiện. Không truyền secret plaintext trong command line vì có thể lưu lại trong shell history hoặc pipeline logs.

Xem cấu hình bằng:

~~~bash
az functionapp config appsettings list \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP>
~~~

Output có thể chứa thông tin nhạy cảm; không paste nguyên output vào issue/chat hoặc log CI.

### 5.4. Cấu hình thay đổi có thể restart ứng dụng

Thay App Settings thường restart Function App trên các hosting plans. Điều này có thể ngắt invocation đang chạy. Khi thay đổi nhiều settings:

- Gom thay đổi thành một lần release có kiểm thử.
- Dùng staging slot nếu plan hỗ trợ.
- Với Flex Consumption, đánh giá rolling update/site update strategy hiện hành.
- Đo lại cold start và kiểm tra trigger sau restart.
- Không giả định việc đổi một giá trị config chỉ ảnh hưởng một function method.

## 6. Managed Identity: xác thực outbound không dùng secret

**Managed Identity** là danh tính do Microsoft Entra ID quản lý cho Azure resource. Function App dùng danh tính này để xin access token và truy cập Key Vault, Storage, Service Bus hoặc các dịch vụ hỗ trợ Microsoft Entra authentication mà không cần lưu client secret trong source/config.

### 6.1. System-assigned và user-assigned

| Đặc điểm | System-assigned | User-assigned |
| --- | --- | --- |
| Vòng đời | Gắn với một Function App; xóa app thì identity cũng bị xóa. | Là Azure resource độc lập, có thể gắn vào nhiều apps. |
| Số lượng | Một identity system-assigned cho mỗi app. | Có thể gắn nhiều identity user-assigned. |
| Tạo lúc nào? | Bật trên Function App. | Tạo identity resource trước rồi gắn vào app. |
| Trường hợp dùng | App có vòng đời độc lập, quyền riêng. | Muốn identity tồn tại qua app replacement hoặc dùng chung có kiểm soát. |
| Cấu hình kết nối | Mặc định được chọn nếu không chỉ định user-assigned. | Thường cần client ID hoặc resource ID trong connection settings. |

**Khuyến nghị:** dùng system-assigned khi một Function App có danh tính và quyền riêng; dùng user-assigned khi cần identity ổn định qua nhiều lần tạo app, hoặc cần cấp quyền cho identity trước khi Function App được tạo.

### 6.2. Bật system-assigned identity

Qua Azure Portal:

1. Mở Function App.
2. Chọn **Settings → Identity**.
3. Trong tab **System assigned**, chuyển Status sang **On**.
4. Save và ghi nhận Principal/Object ID.
5. Gán RBAC role ở tài nguyên đích.

Azure CLI:

~~~bash
az functionapp identity assign \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP>
~~~

Kiểm tra identity:

~~~bash
az functionapp identity show \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP>
~~~

Identity chưa có quyền truy cập dịch vụ đích chỉ vì đã được bật. Cần role assignment ở scope phù hợp.

### 6.3. User-assigned identity

Tạo identity độc lập:

~~~bash
az identity create \
  --name <IDENTITY_NAME> \
  --resource-group <RESOURCE_GROUP>
~~~

Lấy tên, resource ID và client ID của identity; ví dụ CLI sau dùng tên identity:

~~~bash
az functionapp identity assign \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --identities <USER_ASSIGNED_IDENTITY_NAME>
~~~

Khi có nhiều identity, chỉ định đúng client ID/resource ID trong connection cụ thể. Không đặt một biến identity toàn cục rồi mong mọi binding/SDK tự chọn đúng identity trong mọi tình huống.

### 6.4. Identity của deployment slot

Nếu dùng deployment slots, identity và cấu hình identity của slot có phạm vi riêng. Không giả định slot staging tự động có cùng managed identity hoặc role assignments như production. Kiểm tra identity ở **đúng slot** trước khi chạy smoke test.

## 7. Azure RBAC: cấp đúng quyền và đúng scope

Managed Identity cần được cấp quyền bằng **Azure Role-Based Access Control (RBAC)**. Việc có thể đọc ARM resource metadata không đồng nghĩa có quyền đọc/ghi dữ liệu ở data plane.

### 7.1. Control plane và data plane

| Loại quyền | Ví dụ | Dùng cho |
| --- | --- | --- |
| Control plane | Reader, Contributor, Website Contributor | Quản lý resource, cấu hình app, deploy code theo phạm vi role. |
| Data plane | Storage Blob Data Reader, Storage Queue Data Message Processor, Key Vault Secrets User | Đọc/ghi blob, consume queue, đọc secret. |

Một role `Contributor` ở resource group không mặc nhiên cấp quyền đọc blob hoặc secret. Ngược lại, `Storage Blob Data Reader` không cho phép deploy code hay sửa Function App settings.

### 7.2. Nguyên tắc cấp quyền

- Gán role tại **resource scope nhỏ nhất** có thể: storage account, queue, container hoặc vault phù hợp.
- Dùng role built-in chỉ có quyền ứng dụng cần.
- Không cấp `Owner` hoặc `Contributor` cho runtime identity chỉ để tránh lỗi 403.
- Phân biệt quyền đọc với quyền ghi.
- Role assignment có thể mất vài phút để propagate; 403 ngay sau khi cấp role chưa chắc cấu hình sai.
- Mỗi trigger/binding có thể cần role khác nhau, kể cả trên cùng storage account.

### 7.3. Ví dụ: cấp quyền đọc Key Vault secret

Với Key Vault dùng Azure RBAC, role phổ biến cho ứng dụng chỉ đọc secrets là **Key Vault Secrets User**. Cấp role ở scope vault:

~~~bash
az role assignment create \
  --assignee-object-id <FUNCTION_APP_PRINCIPAL_ID> \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope <KEY_VAULT_RESOURCE_ID>
~~~

Nếu vault dùng mô hình access policies thay vì Azure RBAC, phải cấp secret permission tương ứng theo mô hình đó. Không đồng thời giả định RBAC role và access policy là cùng một cơ chế.

### 7.4. Ví dụ: quyền Storage cho host và Queue Trigger

Với host-required `AzureWebJobsStorage`, Microsoft liệt kê `Storage Blob Data Owner` là role tối thiểu cho kết nối host storage trong mô hình managed identity. Một số diagnostic events còn cần `Storage Table Data Contributor`.

Nếu dùng Queue Trigger, role của binding còn phụ thuộc hành vi:

| Thành phần | Role tham khảo |
| --- | --- |
| Host-required AzureWebJobsStorage | Storage Blob Data Owner |
| Queue Trigger chỉ nhận message | Storage Queue Data Message Processor (hoặc role được docs/extension yêu cầu cho scenario). |
| Queue output/send message | Storage Queue Data Message Sender. |
| Queue input + output cần nhiều thao tác | Chọn role tối thiểu bao phủ các thao tác thật; thường Storage Queue Data Contributor. |

Với Blob Trigger, có thể cần quyền ghi poison message vào Queue; vì vậy role cho Blob Trigger rộng hơn quyền đọc Blob đơn thuần. Kiểm tra [identity-based connections role matrix](https://learn.microsoft.com/en-us/azure/azure-functions/manage-connections) cho đúng extension/version và binding.

### 7.5. Cấp quyền bằng Azure CLI

Lấy Principal ID của Function App:

~~~bash
az functionapp identity show \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --query principalId \
  --output tsv
~~~

Cấp role tại resource scope:

~~~bash
az role assignment create \
  --assignee-object-id <PRINCIPAL_ID> \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Queue Data Message Processor" \
  --scope <STORAGE_ACCOUNT_RESOURCE_ID>
~~~

Đây là lệnh có tác động quyền thật. Kiểm tra subscription, principal và resource scope trước khi chạy. Nếu chỉ cần consume một queue cụ thể và role/extension cho phép scope nhỏ hơn, hãy thu hẹp scope xuống queue thay vì cả storage account.

### 7.6. Đừng cấp quyền runtime và deploy cho cùng một danh tính

Tách hai danh tính:

- **Deployment principal:** pipeline/nhân sự phát hành code, cần quyền cập nhật Function App/package/settings ở scope app.
- **Runtime managed identity:** process đang chạy, chỉ cần quyền đọc/ghi dữ liệu, secrets hoặc telemetry theo nghiệp vụ.

Nếu runtime app bị khai thác, identity runtime không nên có quyền tạo role assignment, xóa resource hoặc thay code. Đây là ranh giới quan trọng trong mô hình least privilege.


## 8. Identity-based connection cho AzureWebJobsStorage

`AzureWebJobsStorage` là **host-required connection**. Azure Functions dùng storage mặc định để phối hợp timer/singleton execution, lưu function keys và các hoạt động host khác. Function App thường không thể khởi động nếu thiếu kết nối này.

### 8.1. Dùng managed identity với storage account chuẩn Azure DNS

Với system-assigned identity, App Settings có thể khai báo:

~~~text
AzureWebJobsStorage__accountName=<STORAGE_ACCOUNT_NAME>
AzureWebJobsStorage__credential=managedidentity
~~~

Nếu dùng user-assigned identity, bổ sung client ID:

~~~text
AzureWebJobsStorage__accountName=<STORAGE_ACCOUNT_NAME>
AzureWebJobsStorage__credential=managedidentity
AzureWebJobsStorage__clientId=<USER_ASSIGNED_IDENTITY_CLIENT_ID>
~~~

Azure Functions Host hiểu các setting có tiền tố `AzureWebJobsStorage__` như các thuộc tính của một identity-based connection. Không đặt thêm một connection string cũ vào cùng tên nếu đã chuyển sang dạng identity-based; cần kiểm tra cấu hình hiện tại để tránh xung đột.

### 8.2. Storage account dùng custom DNS hoặc sovereign cloud

Khi account không dùng endpoint Azure DNS chuẩn, có thể phải khai báo URI service cụ thể:

~~~text
AzureWebJobsStorage__blobServiceUri=https://<ACCOUNT>.blob.contoso.com
AzureWebJobsStorage__queueServiceUri=https://<ACCOUNT>.queue.contoso.com
AzureWebJobsStorage__tableServiceUri=https://<ACCOUNT>.table.contoso.com
AzureWebJobsStorage__credential=managedidentity
~~~

Dùng đúng URI và DNS của cloud/storage account. Không dùng ví dụ `contoso.com` trong môi trường thật.

### 8.3. Cấp quyền cho host storage

Với managed identity, `Storage Blob Data Owner` là role tối thiểu được Microsoft nêu cho host-required `AzureWebJobsStorage` trong mô hình hiện hành. Diagnostic events ghi vào Table Storage có thể cần thêm `Storage Table Data Contributor`.

Một số trigger có thêm yêu cầu storage riêng:

| Trigger / feature | Quyền bổ sung có thể cần |
| --- | --- |
| Timer Trigger | Blob lock/coordination trên host storage; kiểm role matrix của runtime. |
| Blob Trigger | Storage Blob Data Owner và quyền Queue cần thiết để ghi poison blobs. |
| Event Hubs Trigger | Blob Storage Data Owner trên host storage cho checkpointing khi dùng storage checkpoint store. |
| Durable Functions | Blob, Queue và Table data roles theo extension configuration. |

Đừng áp dụng một role duy nhất cho tất cả extensions. Phiên bản binding extension, loại trigger và host storage configuration quyết định quyền cụ thể. Xem [Configure connections to remote services](https://learn.microsoft.com/en-us/azure/azure-functions/manage-connections).

### 8.4. Managed identity cho host storage theo hosting plan

Identity-based `AzureWebJobsStorage` có những giới hạn liên quan Azure Files:

| Hosting plan | Managed identity cho host storage | Lưu ý |
| --- | --- | --- |
| Flex Consumption | Hỗ trợ đầy đủ theo hướng dẫn hiện hành. | Không dùng Azure Files cho content share theo mô hình cũ. |
| Dedicated (App Service) | Hỗ trợ đầy đủ. | Không có dynamic scaling Azure Files như Consumption/Premium. |
| Consumption | Hỗ trợ identity cho Blob/Queue/Table trong các trường hợp được hỗ trợ. | `WEBSITE_CONTENTAZUREFILECONNECTIONSTRING` có thể vẫn cần secret/Key Vault nếu dùng Azure Files. |
| Elastic Premium | Hỗ trợ identity cho Blob/Queue/Table trong các trường hợp được hỗ trợ. | Azure Files content share vẫn có yêu cầu riêng. |

Nếu không thể bỏ Azure Files ở Consumption/Premium, Microsoft hướng dẫn bảo vệ `WEBSITE_CONTENTAZUREFILECONNECTIONSTRING` bằng Key Vault. Kiểm tra hosting plan cụ thể trước khi xóa connection string; xóa nhầm có thể khiến app không mount được content share hoặc không khởi động.

### 8.5. Khác biệt local và cloud

Khi chạy local, Azure Functions Host dùng **developer identity** chứ không có managed identity của Function App. Với identity-based local connection, đăng nhập bằng Azure CLI hoặc công cụ developer credential, cấp quyền cho tài khoản developer ở storage scope và làm theo hướng dẫn local của binding. Không ép `credential=managedidentity` vào `local.settings.json` khi đang dùng developer identity; thuộc tính này dành cho môi trường hosting có managed identity.

Để local dùng Azurite, `AzureWebJobsStorage` có thể tiếp tục là `UseDevelopmentStorage=true`. Đây là hai cách chạy khác nhau: local emulator không xác minh RBAC/managed identity của Azure.

## 9. Identity-based connections cho Queue, Blob và Service Bus

Ngoài host storage, từng trigger/binding có connection riêng. Tên connection được chỉ định ở annotation và settings phải có prefix trùng khớp.

### 9.1. Azure Storage Queue

Ví dụ handler:

~~~java
@FunctionName("receiveOrder")
public void receiveOrder(
        @QueueTrigger(
                name = "message",
                queueName = "orders-input",
                connection = "OrdersQueue")
        String payload,
        ExecutionContext context) {
    // Validate payload rồi gọi FunctionCatalog/service.
}
~~~

Với standard Azure Storage endpoint và system-assigned identity, cấu hình:

~~~text
OrdersQueue__queueServiceUri=https://<STORAGE_ACCOUNT>.queue.core.windows.net
OrdersQueue__credential=managedidentity
~~~

Với user-assigned identity, thêm:

~~~text
OrdersQueue__clientId=<USER_ASSIGNED_IDENTITY_CLIENT_ID>
~~~

Tên prefix `OrdersQueue` phải khớp chính xác với `connection = "OrdersQueue"`. Nếu đổi annotation sang `connection = "OrderEvents"`, cấu hình connection cũng phải đổi theo.

### 9.2. Azure Blob Storage

Ví dụ settings cho connection `OrdersBlob`:

~~~text
OrdersBlob__blobServiceUri=https://<STORAGE_ACCOUNT>.blob.core.windows.net
OrdersBlob__credential=managedidentity
~~~

Blob Trigger có thể cần thêm Queue service URI của cùng storage account để ghi poison blob metadata/queue:

~~~text
OrdersBlob__queueServiceUri=https://<STORAGE_ACCOUNT>.queue.core.windows.net
~~~

Role thường rộng hơn Blob Reader đơn thuần khi trigger cần cập nhật checkpoint/poison queue. Kiểm tra bảng role của extension và cấp đúng quyền cho trigger thực tế.

### 9.3. Azure Service Bus

Một connection theo Microsoft Entra ID có dạng:

~~~text
OrderBus__fullyQualifiedNamespace=<NAMESPACE>.servicebus.windows.net
OrderBus__credential=managedidentity
~~~

Với user-assigned identity:

~~~text
OrderBus__clientId=<USER_ASSIGNED_IDENTITY_CLIENT_ID>
~~~

Trong trigger annotation, dùng `connection = "OrderBus"`. Với consumer queue, role thường là `Azure Service Bus Data Receiver`; với sender/output, role là `Azure Service Bus Data Sender`. Nếu trigger dùng topic subscription, role assignment cần scope hiệu lực tới **subscription** theo yêu cầu của extension; cấp ở topic nhưng thiếu subscription scope có thể dẫn tới lỗi authorization.

### 9.4. Một connection prefix cho một mục đích

Không tái sử dụng `AzureWebJobsStorage` làm tên cho mọi connection chỉ vì nó đã có. Có thể dùng cùng storage account về mặt hạ tầng, nhưng đặt connection prefix riêng giúp:

- Chỉ rõ binding nào dùng identity/endpoint nào.
- Cấp role riêng cho host storage và data binding.
- Thay storage account cho một binding mà không đổi host connection.
- Phân biệt lỗi host startup với lỗi xử lý message.

### 9.5. Version và extension compatibility

Identity-based connection chỉ được hỗ trợ trên Azure Functions runtime 4.x trở lên, và binding extension cần có version hỗ trợ. Khi upgrade host/runtime/extension, test lại:

1. App Settings prefix có đúng.
2. Managed identity đang gắn vào đúng Function App/slot.
3. RBAC roles đã propagate.
4. Storage/Service Bus firewall và private endpoint cho phép network.
5. Trigger có thể nhận/gửi message và retry đúng như mong đợi.

## 10. Azure Key Vault: lưu secret khi không thể dùng Managed Identity trực tiếp

Ưu tiên managed identity trực tiếp tới dịch vụ hỗ trợ Microsoft Entra ID. Khi dịch vụ chỉ chấp nhận password/connection string/API key, dùng **Azure Key Vault** để quản lý secret, rotation và audit.

Có hai cách thường gặp:

1. **Key Vault references trong App Settings:** platform resolve secret, Spring/Java đọc giá trị như environment variable bình thường.
2. **Azure SDK trong code:** Java client truy cập Key Vault bằng `DefaultAzureCredential`.

### 10.1. Tạo Key Vault reference

Giả sử secret có tên `partner-api-key`. Azure App Setting có thể đặt:

~~~text
PARTNER_API_KEY=@Microsoft.KeyVault(SecretUri=https://<VAULT_NAME>.vault.azure.net/secrets/partner-api-key)
~~~

Ứng dụng đọc bằng environment variable hoặc Spring configuration:

~~~java
String apiKey = environment.getProperty("PARTNER_API_KEY");
~~~

Code không cần tự gọi Key Vault nếu chỉ dùng reference này. Platform thay reference bằng secret value khi cung cấp setting cho process.

**Không commit giá trị secret**, không đưa reference có version cố định nếu muốn tự nhận bản mới khi rotate, trừ khi release process cần pin version có chủ đích.

### 10.2. Cấp quyền đọc Key Vault

Với Key Vault dùng Azure RBAC, role phổ biến cho ứng dụng chỉ đọc secrets là **Key Vault Secrets User**. Cấp role ở scope vault. Với access policy model, cấp quyền `Get` secret theo cơ chế đó.

Key Vault reference mặc định dùng system-assigned identity của Function App. Nếu dùng user-assigned identity, cần gắn identity vào app và cấu hình `keyVaultReferenceIdentity` bằng **resource ID** của identity.

Key Vault có network restrictions thì app cũng cần đường mạng hợp lệ tới vault. Đúng RBAC mà DNS/private endpoint/VNet routing sai vẫn có thể nhận lỗi truy cập.

### 10.3. Rotation và cache của Key Vault references

Nếu reference không pin secret version, platform dùng version mới nhất. Việc refresh có thể mất một khoảng thời gian do cache của App Service; tài liệu hiện hành nêu cơ chế cập nhật tự động trong vòng tối đa khoảng 24 giờ. Restart/configuration change có thể kích hoạt fetch lại sớm hơn.

Vì vậy, khi rotate secret:

- Đảm bảo secret mới đã được tạo và dịch vụ đích chấp nhận.
- Kiểm resolution status của Key Vault reference.
- Xác minh app đọc được giá trị mới.
- Nếu cần refresh ngay, dùng quy trình refresh reference được Microsoft hỗ trợ.
- Không xóa secret cũ trước khi các instances và consumers đã chuyển sang secret mới.

### 10.4. Chẩn đoán Key Vault reference

Nếu reference không resolve, platform có thể đưa nguyên chuỗi `@Microsoft.KeyVault(...)` vào process. Khi đó code tưởng đang đọc password thật nhưng nhận được chuỗi reference.

Kiểm tra:

- Secret name và URI có đúng.
- Managed identity được bật và có quyền đọc secret.
- Vault network/firewall/private DNS cho phép app.
- Key Vault reference status trong Azure Portal.
- Secret chưa bị disable/expired/deleted.
- Nếu dùng user-assigned identity, `keyVaultReferenceIdentity` có đúng resource ID.


## 11. Truy cập Key Vault trực tiếp từ Java bằng Azure SDK

Nếu cần truy vấn secret theo logic động, có thể dùng Azure SDK thay cho App Setting reference.

### 11.1. Maven dependencies

Quản lý version bằng Azure SDK BOM hoặc dependency management của project, sau đó thêm:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-security-keyvault-secrets</artifactId>
</dependency>
~~~

Không chọn ngẫu nhiên các version riêng cho từng Azure SDK module nếu project đã dùng BOM; giữ chúng tương thích với Spring Boot/SCF release train.

### 11.2. SecretClient với DefaultAzureCredential

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

SecretClient client = new SecretClientBuilder()
        .vaultUrl("https://<VAULT_NAME>.vault.azure.net/")
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();

String secret = client.getSecret("partner-api-key").getValue();
~~~

`DefaultAzureCredential` chọn credential phù hợp môi trường. Khi local, developer có thể đăng nhập bằng Azure CLI/IDE credential; khi chạy trên Azure, credential chain có thể sử dụng managed identity được gắn cho Function App. Cấp quyền đọc secret cho **đúng identity** đang được chọn.

### 11.3. Đăng ký client một lần

Azure SDK client nên được tái sử dụng giữa invocations. Có thể đăng ký singleton bean:

~~~java
@Configuration
class KeyVaultClientConfiguration {

    @Bean
    SecretClient secretClient(Environment environment) {
        String vaultUrl = environment.getRequiredProperty(
                "AZURE_KEY_VAULT_URL");

        return new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient();
    }
}
~~~

Đây là ví dụ Spring configuration, cần imports `org.springframework.context.annotation.Bean`, `Configuration` và `org.springframework.core.env.Environment`. Không gọi `new SecretClientBuilder()` trong mỗi function invocation. Không log secret value, không giữ secret trong static mutable field và không trả secret trong HTTP response.

### 11.4. Chọn Key Vault reference hay Azure SDK?

| Tiêu chí | App Setting Key Vault reference | Azure SDK trong Java |
| --- | --- | --- |
| Code cần thay đổi | Thường không. | Có. |
| Đọc secret | Platform resolve thành App Setting. | Application chủ động gọi Key Vault. |
| Cần nhiều secret theo tên động | Không tiện bằng SDK. | Phù hợp hơn. |
| Rotation/cache | Do platform quản lý reference/cache. | Ứng dụng quản lý refresh/cache/lifecycle. |
| Test | Kiểm resolution và setting. | Mock/test client hoặc dev vault. |
| Quyền | Function App identity đọc secret. | Credential thực tế của SDK đọc secret. |

Nếu chỉ cần một connection string cố định, Key Vault reference thường đơn giản. Nếu nghiệp vụ phải truy xuất nhiều secret theo tenant/secret name, cân nhắc SDK và thiết kế cache, rotation, timeout và error handling.

## 12. Xác thực người gọi HTTP và quyền truy cập tài nguyên là hai việc khác nhau

**Managed Identity** trong các phần trên dùng để Function App truy cập **outbound** tới Azure resources. Nó không tự xác thực user gọi vào HTTP Trigger.

### 12.1. Function key không phải user authentication

Một HTTP Trigger có thể khai báo:

~~~java
@HttpTrigger(
        name = "request",
        methods = {HttpMethod.POST},
        authLevel = AuthorizationLevel.FUNCTION,
        route = "orders")
HttpRequestMessage<Optional<String>> request
~~~

Các mức thường gặp:

| Auth level | Ý nghĩa |
| --- | --- |
| `ANONYMOUS` | Không yêu cầu function key ở lớp trigger. |
| `FUNCTION` | Yêu cầu function-specific hoặc host key. |
| `ADMIN` | Yêu cầu master key; quyền rất rộng, không dùng cho API thông thường. |

Function key là shared secret để gọi endpoint, không phải danh tính user và không thay thế authorization theo vai trò/tenant. Nếu cần xác thực người dùng/ứng dụng, hãy dùng Microsoft Entra ID authentication (App Service Authentication), API Management hoặc cơ chế gateway phù hợp.

Nếu bật App Service Authentication đồng thời giữ `authLevel=FUNCTION`, hãy kiểm tra cả hai lớp: caller có thể cần Entra token và function key tùy cấu hình. Thiết kế rõ lớp nào xác thực người gọi và lớp nào áp dụng authorization cho nghiệp vụ; tránh tạo hai yêu cầu credential ngoài ý muốn.

### 12.2. Microsoft Entra authentication và API Management

Với API phục vụ client bên ngoài:

- Cấu hình App Service Authentication để yêu cầu Microsoft Entra ID token nếu phù hợp.
- Xác minh issuer, audience, tenant và claims/roles ở đúng tầng.
- Dùng API Management khi cần quota, versioning, request transformation, subscription management hoặc policy.
- Không chỉ dựa vào function key để quyết định một user được phép đọc đơn hàng của tenant nào.
- Kiểm tra cả authentication lẫn authorization ở business boundary.

### 12.3. CORS, access restrictions và private endpoints

- **CORS** kiểm soát browser origin; nó không phải authentication.
- **Access restrictions** giới hạn nguồn mạng được gọi Function App.
- **Private endpoint** có thể giới hạn inbound traffic vào mạng riêng.
- **VNet integration** hỗ trợ outbound connectivity tới dịch vụ private/network-restricted.
- Key Vault/Storage firewall và private DNS phải được cấu hình cùng network path của Function App.

Khi bật private endpoint và tắt public network access, pipeline deploy cũng phải có network connectivity/DNS tới deployment endpoint. Không chỉ runtime mà cả máy build/runner có thể cần nằm trong mạng được phép.

### 12.4. Function keys và nơi lưu trữ

Azure Functions lưu function/host keys trong secret storage theo cấu hình host. Có thể chọn Blob Storage hoặc Key Vault secret storage trên runtime hỗ trợ. Nếu chuyển key storage sang Key Vault, phải cấu hình `AzureWebJobsSecretStorageType` và `AzureWebJobsSecretStorageKeyVaultUri` theo tài liệu; cấp các quyền quản lý keys mà host cần, không nhầm với quyền `Key Vault Secrets User` chỉ đọc secrets thông thường.

Với Key Vault dùng để **lưu function keys**, host cần các quyền quản lý secret như `Get`, `Set`, `List` và `Delete` theo cấu hình/runtime. Đây là use case khác với Key Vault reference chỉ cần đọc secret. Nên dùng vault riêng cho key storage của từng Function App vì keys có thể được chia sẻ trong cùng vault và có nguy cơ collision/overwrite.

Đừng chia sẻ master key cho client. Ưu tiên Entra authentication/gateway cho API production và quản lý function keys như credentials có vòng đời/rotation rõ ràng.

## 13. Local development và danh tính của developer

Trên máy local không có managed identity của Function App. Khi dùng Azure SDK `DefaultAzureCredential`, credential chain có thể lấy danh tính từ Azure CLI hoặc công cụ developer đã đăng nhập. Với Azure Functions binding identity-based, local development cũng dùng developer identity theo hướng dẫn riêng của binding.

### 13.1. Đăng nhập Azure CLI

~~~bash
az login
az account show
~~~

Đảm bảo đang ở subscription và tenant dev được phép. Không dùng identity production chỉ để chạy local.

### 13.2. Cấp quyền cho developer

Nếu local function cần đọc Queue/Blob/Key Vault bằng Entra ID, cấp role phù hợp cho **developer account** ở scope dev resource. Không cấp role cho user developer rồi nghĩ Function App managed identity cũng được hưởng quyền đó; đây là hai principal khác nhau.

### 13.3. Local settings khác App Settings cloud

Ví dụ `local.settings.json`:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.OrderFunctionApplication",
    "SPRING_PROFILES_ACTIVE": "dev",
    "ORDERS_THRESHOLD": "1000000",
    "ORDERS_PREFIX": "DEV-",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

Các setting trong `Values` được Core Tools đưa vào process environment khi chạy local. Khi publish, Core Tools không tự đồng bộ chúng lên Azure theo mặc định. Tạo App Settings cloud riêng và dùng connection/identity phù hợp.

Không commit `local.settings.json` nếu file có secrets, connection strings hoặc local credentials. Dùng `.gitignore`, secret manager và tài nguyên dev riêng.


## 14. Mạng, private endpoint và kết nối tới dịch vụ đích

Managed identity giải quyết **authentication**, nhưng không tự tạo **network connectivity**. Một Function App có token hợp lệ vẫn có thể không kết nối được Storage/Key Vault/Service Bus nếu firewall, DNS hoặc route chặn.

### 14.1. Inbound và outbound networking

| Cơ chế | Hướng traffic | Mục đích |
| --- | --- | --- |
| Private endpoint của Function App | Inbound | Client trong mạng riêng truy cập Function App. |
| VNet integration | Outbound | Function App truy cập resource private trong VNet/peered network. |
| Private endpoint của Key Vault/Storage | Inbound tới resource đích | Chỉ nhận traffic từ mạng được phép. |
| Access restrictions | Inbound | Cho phép/chặn IP/subnet theo policy. |
| Private DNS zone | Phân giải tên | Đảm bảo hostname dịch vụ resolve tới private IP phù hợp. |

Đừng nhầm private endpoint inbound của Function App với VNet integration outbound. Một app có private inbound endpoint vẫn cần cấu hình outbound network riêng để truy cập storage/vault private.

### 14.1.1. Networking support phụ thuộc hosting plan

| Hosting plan | Inbound access restrictions | Private endpoint cho Function App | Outbound VNet integration |
| --- | --- | --- | --- |
| Flex Consumption | Có | Có | Có |
| Consumption (legacy) | Có | Không | Không |
| Elastic Premium | Có | Có | Có |
| Dedicated (App Service) | Có | Có | Có |
| Azure Container Apps | Do Container Apps environment quản lý | Không dùng App Service private endpoint cho Function App trong mô hình legacy; dùng networking của environment | Do environment quản lý |

Vì vậy, không giả định private endpoint hoặc VNet integration khả dụng trên mọi plan. Consumption plan legacy không hỗ trợ outbound VNet integration; nếu workload cần private network access, phải chọn plan/architecture hỗ trợ.

### 14.2. Key Vault network restriction

Nếu Key Vault chỉ cho phép private network:

1. Bật VNet integration phù hợp với hosting plan.
2. Tạo private endpoint và cấu hình private DNS.
3. Đảm bảo Function App route được tới subnet/endpoint.
4. Nếu plan/OS cần route all traffic, bật cấu hình theo hướng dẫn Microsoft.
5. Kiểm tra Key Vault reference resolution status và audit logs.

Trong Flex Consumption, một số routing behavior khác Linux Consumption/Premium; không copy nguyên lệnh cấu hình VNet từ plan khác. Kiểm tra [Azure Functions networking options](https://learn.microsoft.com/en-us/azure/azure-functions/functions-networking-options) theo plan/OS đang dùng.

### 14.3. Storage firewall và host startup

Nếu khóa public network access của storage account được dùng làm `AzureWebJobsStorage`, Azure Functions Host cũng phải truy cập được account đó. Nếu không, host có thể không khởi động, timer/queue coordination lỗi hoặc trigger không hoạt động.

Kiểm tra cả:

- Network rules của storage account.
- Private endpoint cho Blob/Queue/Table services cần thiết.
- DNS từ Function App và deployment runner.
- RBAC data roles của managed identity.
- Connection settings và identity đúng prefix.

### 14.4. 403 chưa chắc là lỗi RBAC

Một lỗi 403 có thể do:

- Identity không có role data plane.
- Role assignment scope sai hoặc chưa propagate.
- Key Vault/storage firewall từ chối IP/subnet.
- Private DNS resolve nhầm public endpoint.
- Function App dùng sai system-assigned/user-assigned identity.
- App Setting connection prefix không khớp binding.

Đọc response details/diagnostic logs và kiểm tra network trước khi cấp thêm quyền rộng.

## 15. Triển khai: tách cấu hình runtime khỏi deployment artifact

Một deployment artifact nên chứa code, dependencies và metadata cần thiết; environment-specific settings được cung cấp riêng trên Function App. Cách này giúp cùng một version artifact đi qua dev, staging và production.

### 15.1. Quy trình triển khai Maven

Sau khi build/package thành công và Azure Functions Maven plugin được cấu hình:

~~~bash
./mvnw clean package
./mvnw azure-functions:deploy
~~~

Lệnh deploy thay đổi code đang chạy và có thể tạo tài nguyên hoặc phát sinh chi phí tùy cấu hình plugin. Trước khi chạy cần xác minh subscription, resource group, Function App name, Java runtime, hosting plan, app settings và identity. Không đặt secret trong `pom.xml` hoặc command line.

### 15.2. Core Tools publish

Với project đã có package phù hợp:

~~~bash
func azure functionapp publish <FUNCTION_APP_NAME>
~~~

Lệnh này phù hợp cho workflow phát triển/publish trực tiếp. Production nên dùng pipeline có build, test, artifact versioning và release gate.

### 15.3. Deployment method phụ thuộc hosting plan

| Hosting plan | Deployment behavior | Chiến lược phát hành |
| --- | --- | --- |
| Flex Consumption | Flex package deployment; code package lưu trong deployment container. | Dùng công cụ hỗ trợ Flex; rolling updates/site update strategy khi được hỗ trợ. Không có deployment slots. |
| Consumption (legacy) | ZIP/external package tùy OS và deployment path. | Kiểm tra đúng Windows/Linux và các ràng buộc storage. |
| Elastic Premium | ZIP/external package và deployment slots theo hỗ trợ. | Có thể deploy staging slot rồi swap sau smoke test. |
| Dedicated (App Service) | ZIP và slots theo App Service plan. | Staging slot/release pipeline. |
| Azure Container Apps | Container image và revisions. | Quản lý image tag/digest và revision traffic. |

Không dùng một lệnh ZIP deployment cho mọi plan. Flex Consumption có deployment technology riêng; Premium/Dedicated có thể dùng slots. Xem [Deployment technologies in Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-deployment-technologies).

### 15.4. Deployment slots và identity

Với plan có hỗ trợ slots:

- Slot là môi trường chạy riêng và có cấu hình/identity riêng.
- Kiểm tra slot-specific App Settings và connection strings.
- Cấp RBAC cho đúng managed identity của slot.
- Chạy smoke test trên staging slot trước swap.
- Sau swap, xác nhận identity, secret references, storage và network policy vẫn đúng.

Flex Consumption hiện không hỗ trợ deployment slots. Dùng Function App staging riêng hoặc rolling update/site update strategy theo tài liệu của plan.

### 15.5. App Settings thay đổi có thể restart app

Thay App Settings thường restart Function App. Nếu thay settings cùng lúc với deploy code, hãy tính đến restart/cold start và invocation đang chạy. Với các workload event-driven, thiết kế handler stateless và idempotent để xử lý redelivery khi có restart.

## 16. CI/CD và deployment identity

### 16.1. Tách pipeline identity khỏi runtime identity

| Danh tính | Nhiệm vụ | Quyền nên có |
| --- | --- | --- |
| Developer identity | Chạy local, debug và đọc dev resources. | Quyền giới hạn trong môi trường dev. |
| CI/CD identity | Deploy package, cập nhật App Settings nếu pipeline quản lý chúng. | Role deploy như Website Contributor ở scope Function App/resource cần thiết; không cấp Owner toàn subscription. |
| Runtime managed identity | Truy cập storage, queue, vault, database, telemetry. | Chỉ các data roles cần cho workload. |

Không tái sử dụng credential runtime để đăng nhập CI/CD hoặc cấp quyền quản trị resource cho Function App.

### 16.2. Dùng workload identity federation

Với GitHub Actions hoặc Azure DevOps, ưu tiên OIDC/workload identity federation thay cho client secret tĩnh khi nền tảng hỗ trợ. Pipeline lấy token theo trust configuration đã thiết lập trong Microsoft Entra ID; không cần lưu password dài hạn trong repository secret.

Cần cấu hình:

- Federated credential đúng repository/branch/environment hoặc service connection.
- Role deploy được scope ở Function App/resource group cần thiết.
- Quyền cập nhật App Settings riêng nếu pipeline có nhiệm vụ quản lý settings.
- Quyền tạo role assignment tách biệt và chỉ cấp khi thật sự cần provisioning IAM.
- Approval gate trước production.

### 16.3. Một artifact qua nhiều môi trường

~~~mermaid
flowchart LR
    A["Commit / Pull request"] --> B["Build + unit tests"]
    B --> C["Spring context + catalog tests"]
    C --> D["Azure package + artifact hash"]
    D --> E["Deploy dev"]
    E --> F["Deploy staging"]
    F --> G["Smoke test + approval"]
    G --> H["Deploy / promote production"]
    H --> I["Monitor + rollback if needed"]
~~~

Không build lại cùng source với dependency versions khác nhau cho mỗi environment. Build một artifact có version/hash rõ, rồi inject settings, secrets và identity theo từng Function App.

### 16.4. Quản lý hạ tầng bằng IaC

Dùng Bicep, Terraform hoặc ARM templates để khai báo:

- Function App và hosting plan.
- Storage, Key Vault, Application Insights.
- Managed identity assignment.
- RBAC role assignments.
- VNet/private endpoints/DNS.
- App Settings và deployment configuration.

Tách secrets khỏi state file nếu backend/state system có thể lưu chúng. Với Key Vault reference, IaC khai báo reference URI thay vì secret value.

## 17. Kiểm chứng sau deploy, rollback và vận hành

### 17.1. Checklist smoke test

Sau khi triển khai vào staging:

1. Function App ở trạng thái Running và dùng đúng Java/runtime version.
2. Azure Host discover đủ `@FunctionName` methods.
3. Spring context khởi tạo và `FunctionCatalog.lookup(...)` thành công.
4. `SPRING_PROFILES_ACTIVE` và các business settings đúng môi trường.
5. Managed identity của app/slot là identity mong muốn.
6. Identity đọc được Key Vault reference và connection settings resolve thành công.
7. Storage/Queue/Service Bus/Database binding truy cập đúng resource dev/staging.
8. HTTP auth, function key/Entra policy và network restrictions đúng.
9. Log có invocation ID/correlation ID, không lộ secret hoặc payload nhạy cảm.
10. Queue retry, poison/DLQ, idempotency và output bindings hoạt động như thiết kế.

### 17.2. Kiểm tra cấu hình mà không lộ secret

Không dump toàn bộ App Settings ra console/CI log. Tạo health/config diagnostic endpoint hoặc startup log chỉ hiển thị:

- Spring profile đang active.
- Tên resource/endpoint không nhạy cảm.
- Tên managed identity/client ID nếu policy cho phép.
- Trạng thái resolution của dependency (không in secret).
- Version/commit SHA của artifact.

Không log connection string, API key, function key, token hoặc secret value.

### 17.3. Rollback

Khi release lỗi:

1. Dừng promotion nếu staging smoke test thất bại.
2. Nếu plan hỗ trợ deployment slots, swap/revert về slot version ổn định theo quy trình.
3. Với package deployment, redeploy artifact đã lưu trước đó bằng đúng công cụ/plan.
4. Khôi phục App Settings/Key Vault secret version nếu thay đổi cấu hình gây lỗi.
5. Kiểm tra identity/RBAC/network rules không bị thay đổi ngoài dự kiến.
6. Xác minh trigger discovery, HTTP request và event processing sau rollback.
7. Đối soát message bị retry/redeliver; bảo đảm idempotency không tạo side effect trùng.

Rollback code không tự rollback database schema, event schema hoặc message đã gửi. Những thay đổi đó cần backward-compatible migration strategy riêng.

### 17.4. Monitoring

Theo dõi ít nhất:

- Spring/Java startup failure và dependency injection errors.
- Function discovery/binding errors.
- HTTP 4xx/5xx, latency và cold start.
- Queue backlog, retry, poison/dead-letter.
- Storage/Key Vault/Service Bus 401/403/timeout.
- RBAC changes và secret access audit.
- Memory, concurrency và dependency response time.
- Deployment status và version đang chạy.


## 18. Troubleshooting cấu hình, identity và deployment

| Triệu chứng | Tầng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Spring dùng sai threshold/prefix | Spring config binding | Kiểm `SPRING_PROFILES_ACTIVE`, env name và precedence. |
| App Setting đổi nhưng code không đổi | App restart/config cache | Kiểm setting đã lưu, restart/startup logs và profile. |
| Function App không khởi động sau đổi storage | Host-required connection | Kiểm `AzureWebJobsStorage`, identity, role, DNS/network. |
| 401 từ Azure Storage/Key Vault | Authentication | Kiểm identity có được gắn, token audience/credential chain. |
| 403 từ Storage | Data-plane RBAC hoặc firewall | Kiểm role, scope, propagation và network rules. |
| 403 từ Key Vault | RBAC/access policy hoặc private network | Kiểm Key Vault Secrets User/Get permission, DNS/VNet và reference status. |
| Binding không nhận message | Connection prefix/extension | `connection` có khớp setting prefix? Extension version có hỗ trợ identity? |
| Queue Trigger đọc được nhưng không ghi output | Role thiếu quyền send/write | Cấp role data-plane đúng output operation. |
| Local chạy nhưng Azure lỗi identity | Developer credential khác managed identity | Kiểm principal runtime và role assignment cloud. |
| App dùng nhầm user-assigned identity | Client ID/resource ID | Kiểm `__clientId` hoặc `__managedIdentityResourceId` theo connection prefix. |
| Timer/Blob/Event Hub lỗi sau chuyển host storage sang MI | Host storage permissions | Kiểm role bổ sung và extension support. |
| Premium/Consumption lỗi sau bỏ connection Azure Files | Content share | Kiểm `WEBSITE_CONTENTAZUREFILECONNECTIONSTRING` và plan requirements. |
| Key Vault reference hiển thị nguyên chuỗi | Reference không resolve | Kiểm URI, identity, role, secret status, network và reference diagnostics. |
| Secret mới chưa được dùng | Reference cache/refresh | Kiểm version, refresh policy, restart/config update. |
| HTTP endpoint bị gọi trái phép | Inbound auth | Function key không thay Entra authentication; kiểm App Service Auth/API gateway. |
| Deploy thành công nhưng trigger không xuất hiện | Package/trigger sync | Kiểm package metadata và deployment technology; sync trigger khi phương thức yêu cầu. |
| Pipeline deploy bị 403 | Deployment identity | Kiểm federated credential và role scope của pipeline principal. |
| Pipeline không tới deployment endpoint | Network | Self-hosted runner/VNet/DNS/private endpoint connectivity. |
| Staging slot không đọc được Key Vault | Slot identity/settings | Gán identity/RBAC cho slot và kiểm slot-specific settings. |
| Flex app không dùng slot/ZIP như hướng dẫn cũ | Hosting plan | Dùng Flex package deployment và site update strategy đúng plan. |

### 18.1. Trình tự điều tra 401/403

~~~text
1. Principal: Function App đang dùng system-assigned hay user-assigned identity?
2. Credential: connection prefix/DefaultAzureCredential chọn đúng identity?
3. Authentication: token có được cấp cho service đúng?
4. Authorization: RBAC role đúng loại data plane và scope?
5. Propagation: role assignment đã có thời gian áp dụng?
6. Network: firewall/private endpoint/DNS/VNet có cho phép?
7. Service: binding extension/SDK version có hỗ trợ identity mode?
8. Settings: app setting name và connection prefix có đúng?
~~~

Không cấp thêm `Contributor` toàn subscription để “thử xem có hết 403 không”. Cách đó che khuất root cause và tạo quyền vượt nhu cầu.

## 19. Bài tập thực hành và câu hỏi tự đánh giá

### 19.1. Bài tập

1. **Tách môi trường:** tạo bảng settings cho dev/staging/prod; dùng cùng artifact nhưng threshold/prefix khác nhau.
2. **Spring binding:** tạo `OrderProperties` bằng `@ConfigurationProperties` và override bằng `ORDERS_THRESHOLD`.
3. **App Settings:** cập nhật một setting không bí mật bằng Azure CLI; quan sát restart và xác minh profile.
4. **System-assigned identity:** bật identity cho Function App dev, ghi lại principal ID.
5. **RBAC scope:** cấp `Storage Queue Data Message Processor` cho identity trên dev queue/storage; thử receive message.
6. **Queue output:** thêm output binding và chỉ cấp role send phù hợp; xác minh quyền đọc và ghi khác nhau.
7. **AzureWebJobsStorage:** chuyển sang identity-based connection trong môi trường test, kiểm timer/host startup và các extension cần storage.
8. **Key Vault reference:** tạo secret dev, cấp Key Vault Secrets User và cấu hình app setting reference.
9. **Secret rotation:** tạo version mới, quan sát refresh/caching và kiểm tra app dùng secret mới.
10. **Java SDK:** dùng `DefaultAzureCredential` để đọc secret từ Key Vault; chạy local với Azure CLI identity rồi kiểm trên Function App managed identity.
11. **Inbound auth:** thử Function key và Microsoft Entra authentication; giải thích chúng bảo vệ các lớp khác nhau.
12. **Network:** hạn chế public access của dev vault/storage, cấu hình private endpoint/DNS/VNet rồi kiểm kết nối.
13. **CI/CD:** tạo pipeline dùng workload identity federation và deploy identity có scope Function App.
14. **Rollback:** lưu artifact version trước, triển khai version mới vào staging, mô phỏng lỗi và quay lại version ổn định.
15. **Troubleshooting:** tạo một 403 do thiếu role ở dev, xác định principal/scope/role thay vì cấp Contributor rộng.

### 19.2. Câu hỏi tự đánh giá

- Khác biệt giữa `host.json`, `local.settings.json` và Azure App Settings là gì?
- Vì sao App Settings thay đổi thường làm Function App restart?
- Spring property `orders.threshold` được ánh xạ thành environment variable nào?
- System-assigned identity khác user-assigned identity về lifecycle thế nào?
- Vì sao bật managed identity chưa đủ để truy cập Storage?
- Khác nhau giữa control-plane Contributor và data-plane Storage Blob Data Reader là gì?
- Tại sao `AzureWebJobsStorage` là host-required connection?
- Vì sao Consumption/Premium có thể còn cần Azure Files connection dù đã dùng managed identity cho host storage?
- `connection="OrdersQueue"` liên hệ thế nào với `OrdersQueue__queueServiceUri`?
- Khi nào chọn Key Vault reference thay cho Azure SDK?
- Vì sao local developer identity khác Function App managed identity?
- Function key có thay thế Microsoft Entra authentication không?
- Private endpoint inbound khác VNet integration outbound thế nào?
- Vì sao deployment identity không nên là runtime identity?
- Hosting plan ảnh hưởng deployment method, slots và rollback ra sao?

## 20. Tài liệu tham khảo chính thức

- [Microsoft Learn — Configure function app settings](https://learn.microsoft.com/en-us/azure/azure-functions/functions-how-to-use-azure-function-app-settings): App Settings, environment variables, restart và Azure CLI.
- [Microsoft Learn — App settings reference for Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-app-settings): host/runtime settings và application settings.
- [Microsoft Learn — Configure connections to remote services](https://learn.microsoft.com/en-us/azure/azure-functions/manage-connections): host-required connections, binding connections, identity-based settings và RBAC role matrix.
- [Microsoft Learn — Use managed identities for App Service and Azure Functions](https://learn.microsoft.com/en-us/azure/app-service/overview-managed-identity): system-assigned/user-assigned identity, gắn identity và cấp quyền.
- [Microsoft Learn — Key Vault references as App Settings](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references): reference syntax, managed identity, network restrictions và rotation/cache.
- [Microsoft Learn — Azure Key Vault Secret client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/security-keyvault-secrets-readme): `SecretClient` và `DefaultAzureCredential`.
- [Microsoft Learn — Azure Functions networking options](https://learn.microsoft.com/en-us/azure/azure-functions/functions-networking-options): VNet integration, private endpoints và networking.
- [Microsoft Learn — Authentication and authorization in Azure App Service and Azure Functions](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization): built-in authentication (Easy Auth), identity providers và authorization.
- [Microsoft Learn — Deployment technologies in Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-deployment-technologies): ZIP/package deployment, Flex Consumption, slots, remote package và trigger sync.
- [Microsoft Learn — Azure Functions GitHub Actions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-how-to-github-actions): CI/CD và federated identity.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): environment variables, property sources, profiles và configuration binding.
- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): Azure adapter, FunctionCatalog, Java handlers và packaging.

**Kết luận:** Một ứng dụng Spring Cloud Function trên Azure cần quản lý đồng thời **cấu hình Spring**, **App Settings của Function App**, **danh tính runtime**, **quyền Azure RBAC**, **xác thực inbound** và **deployment pipeline**. Dùng Spring profiles/`@ConfigurationProperties` cho nghiệp vụ; dùng managed identity và least-privilege roles cho dịch vụ hỗ trợ Entra ID; dùng Key Vault khi còn phải giữ shared secrets; chọn deployment method theo hosting plan. Tách deployment identity khỏi runtime identity, kiểm tra network và trigger bindings, rồi chạy smoke test/rollback có kiểm soát trước production.





