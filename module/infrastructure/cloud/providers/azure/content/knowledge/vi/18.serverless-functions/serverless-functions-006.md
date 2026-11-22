# Cấu hình ứng dụng, secret và managed identity cho Function

Một Azure Function có thể chỉ chứa vài dòng code xử lý HTTP request, sự kiện từ hàng đợi hoặc tệp được tải lên. Nhưng khi vận hành thực tế, Function thường cần URL API bên ngoài, cờ tính năng, cấu hình môi trường, thông tin kết nối Storage, quyền truy cập Azure Key Vault, database hoặc message broker. Nếu đặt tất cả trong mã nguồn, ứng dụng sẽ khó chuyển giữa dev/staging/production, khó xoay vòng khóa và dễ vô tình làm lộ bí mật khi build, triển khai hoặc ghi log.

**Azure Functions app settings** giúp tách cấu hình khỏi code. **Azure Key Vault** lưu và quản lý secret theo chính sách. **Managed identity** cho phép Function App nhận danh tính Microsoft Entra ID để truy cập nhiều dịch vụ Azure mà không phải tự quản lý mật khẩu hoặc client secret dài hạn.

Bài học thuộc chương **Serverless với Azure Functions** trong mô-đun **CLOUD_PROVIDERS_AZURE**. Nội dung gắn với Subscription, Resource Group, Microsoft Entra ID, mạng ảo, Storage, ứng dụng serverless, Azure Monitor và quản lý chi phí. Trọng tâm là biến một Function từ bản thử nghiệm có chuỗi kết nối viết cứng thành dịch vụ có cấu hình rõ ràng, quyền tối thiểu, khả năng kiểm toán và vận hành ổn định.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt application setting, environment variable, connection string, secret, Key Vault reference và managed identity.
2. Cấu hình Azure Functions ở máy phát triển bằng local.settings.json và trên Azure bằng Function App settings.
3. Nhận biết các setting runtime thiết yếu, đặc biệt FUNCTIONS_WORKER_RUNTIME và AzureWebJobsStorage.
4. Chọn system-assigned hoặc user-assigned managed identity đúng trường hợp sử dụng.
5. Cấp quyền dữ liệu tối thiểu bằng Azure RBAC cho Key Vault, Blob Storage, Queue Storage và những dịch vụ được hỗ trợ.
6. Dùng Key Vault references hoặc SDK với DefaultAzureCredential/ManagedIdentityCredential mà không đưa secret thật vào source.
7. Giải thích kết nối identity-based của Functions triggers/bindings và những điều kiện extension/hosting plan.
8. Triển khai quy trình cấu hình, xoay secret, chẩn đoán lỗi 401/403/DNS và kiểm tra log an toàn.
9. Thiết kế production checklist, tách môi trường, bảo mật CI/CD và theo dõi chi phí.

Các lệnh Azure CLI bên dưới là ví dụ; chúng không tự chạy và phải được điều chỉnh cho đúng Azure subscription, runtime, hosting plan, region và chính sách của tổ chức.

## 2. Ba bài toán phải giải quyết riêng

### 2.1. Cấu hình không phải lúc nào cũng là secret

Một ứng dụng có thể cần các giá trị:

| Ví dụ | Phân loại | Nơi quản lý thường phù hợp |
|---|---|---|
| APP_ENV=production | Cấu hình không bí mật | Function App settings |
| API_TIMEOUT_SECONDS=20 | Cấu hình không bí mật | Function App settings |
| FEATURE_PROCESS_V2=false | Feature flag | App settings hoặc hệ thống feature management |
| STORAGE_BLOB_URI=https://...blob.core.windows.net/ | Service endpoint; thường không phải credential | App settings |
| Database password | Secret | Key Vault hoặc identity-based access khi có thể |
| API token của bên thứ ba | Secret | Key Vault |
| Storage Account key | Credential quyền rộng | Tránh dùng khi hỗ trợ Entra identity; nếu bắt buộc, quản lý secret nghiêm ngặt |
| Client ID của managed identity | Định danh, thông thường không phải password | App setting theo thiết kế |
| Azure Function host key | Khóa cho một số kịch bản HTTP/webhook | Chỉ dùng ở vị trí bảo mật phù hợp, không đặt trong client công khai |

**Đường dẫn tới một secret không nhất thiết là secret**, nhưng tên vault, tên tài khoản, resource ID và topology nội bộ vẫn cần được quản lý theo phân loại thông tin của tổ chức.

### 2.2. Secret và identity giải quyết hai vấn đề khác nhau

- **Secret** là một giá trị cần được bảo mật, ví dụ API token của một nhà cung cấp không hỗ trợ Microsoft Entra ID.
- **Managed identity** là danh tính Azure quản lý cho một tài nguyên; nó cho phép xin token truy cập tới dịch vụ chấp nhận Entra ID và kiểm tra Azure RBAC.
- **App setting** là cơ chế phân phối giá trị cấu hình vào Function runtime, có thể chứa chuỗi hoặc Key Vault reference.
- **Key Vault reference** là một cú pháp trong app setting, cho phép nền tảng App Service/Functions phân giải secret phù hợp và đưa giá trị vào ứng dụng theo cơ chế được hỗ trợ.
- **SDK gọi Key Vault trực tiếp** là lựa chọn khác: ứng dụng dùng identity để gọi Key Vault API, tự chịu trách nhiệm caching, lỗi và thời điểm refresh.

Một Function dùng managed identity để lấy token của Azure Storage có thể không cần secret Storage key. Nhưng nếu gọi API bên thứ ba chỉ hỗ trợ static API key, Function vẫn cần giữ secret đó ở nơi thích hợp.

### 2.3. Xác thực người gọi khác với identity outbound

~~~mermaid
flowchart LR
    C["Client / Event Source"] -->|HTTP/trigger| F["Azure Function"]
    E["App Settings"] -.-> F
    F -->|Managed Identity token| S["Blob / Queue / Key Vault"]
    F -->|API key từ Key Vault nếu bắt buộc| X["Dịch vụ bên thứ ba"]
    I["Microsoft Entra ID"] -. "Phát hành access token" .-> F
~~~

**Không nhầm lẫn:**

- **Inbound authentication:** ai được gọi HTTP Function? Có thể liên quan Function key, App Service Authentication, API Management hoặc xác thực của ứng dụng.
- **Outbound authorization:** Function được phép đọc Blob, nhận Queue message hoặc lấy secret nào? Dựa vào managed identity, Azure RBAC và chính sách dữ liệu của dịch vụ đích.

Bật managed identity **không tự làm HTTP endpoint trở thành private hoặc chỉ chấp nhận Entra token**. Cần bảo vệ endpoint độc lập.

## 3. Azure Functions nhận cấu hình như thế nào?

### 3.1. Mô hình cấu hình nhiều môi trường

~~~mermaid
flowchart TD
    G["Source code / artifact"] --> D["Dev Function"]
    G --> T["Staging Function / slot"]
    G --> P["Production Function"]
    LD["local.settings.json<br/>chỉ để phát triển"] -.-> D
    SD["Dev settings / dev identity"] -.-> D
    ST["Staging settings / identity"] -.-> T
    SP["Production settings / identity"] -.-> P
    KV["Key Vault và RBAC theo môi trường"] -.-> T
    KV -.-> P
~~~

Mục tiêu là dùng **cùng artifact đã kiểm thử** cho nhiều môi trường trong phạm vi tương thích, còn endpoint, quyền, resource ID và secret được cấp ở môi trường tương ứng. Không nhúng mật khẩu production vào file zip, container image hoặc source code.

### 3.2. local.settings.json

Trong quá trình chạy Azure Functions Core Tools tại máy cá nhân, dự án thường có tệp local.settings.json:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "APP_ENV": "local",
    "API_TIMEOUT_SECONDS": "20",
    "DOCUMENTS_BLOB_URI": "http://127.0.0.1:10000/devstoreaccount1"
  }
}
~~~

Giải thích:

- **IsEncrypted** cho biết cách Core Tools xử lý giá trị local; đặt false không biến file thành kho chứa secret an toàn.
- **Values** là các cặp key/value được runtime sử dụng.
- **FUNCTIONS_WORKER_RUNTIME** chọn language worker, ví dụ python, node, dotnet-isolated tùy ứng dụng.
- **AzureWebJobsStorage=UseDevelopmentStorage=true** hướng đến storage emulator như Azurite cho những phần chức năng có hỗ trợ.
- **APP_ENV** và **API_TIMEOUT_SECONDS** là cấu hình do ứng dụng tự định nghĩa.

Các giá trị JSON trong Values nên biểu diễn dưới dạng chuỗi khi cần tương thích cách runtime đọc environment variables. Các storage triggers/bindings có thể cần Azurite hoặc dịch vụ thật tùy loại; không giả định emulator hỗ trợ mọi tính năng Azure Storage.

**Quan trọng:** local.settings.json có thể chứa connection string/password ở máy dev, vì vậy:

1. Không commit file chứa giá trị thực lên Git.
2. Dùng local.settings.json.example hoặc hướng dẫn với placeholder không nhạy cảm nếu cần.
3. Giới hạn quyền đọc file trên máy.
4. Không upload file này như một phần artifact triển khai.
5. Nếu đã lộ credential, thu hồi/xoay credential chứ không chỉ xóa dòng khỏi Git.
6. Khi dùng Entra credentials trên máy dev, ưu tiên cơ chế đăng nhập của lập trình viên theo chính sách và cấp quyền dev tối thiểu.

### 3.3. Cấu hình trên Azure

Khi chạy trên Azure, Function App settings được cung cấp dưới dạng biến môi trường/cấu hình ứng dụng theo runtime. Có thể quản lý bằng Azure Portal, Azure CLI, Bicep/Terraform hoặc pipeline.

Ví dụ:

~~~text
APP_ENV=production
API_TIMEOUT_SECONDS=20
DOCUMENTS_BLOB_URI=https://stordersprod.blob.core.windows.net/
THIRD_PARTY_API_KEY=@Microsoft.KeyVault(...)
~~~

Không dùng local.settings.json như nguồn cấu hình production. Một số setting đặc biệt do Azure Functions platform/hosting plan quản lý có tác động khác app setting thông thường. Cập nhật app settings có thể gây restart Function App hoặc thay đổi worker instances, nên production cần quy trình thay đổi và kiểm tra sau deploy.

### 3.4. Những key nền tảng cần nhận biết

| Setting | Mục đích | Lưu ý |
|---|---|---|
| FUNCTIONS_WORKER_RUNTIME | Chọn language worker | Phải khớp runtime và artifact |
| FUNCTIONS_EXTENSION_VERSION | Chọn dòng runtime Functions hỗ trợ, thường ~4 trong các kịch bản hiện đại | Không tự nâng phiên bản mà không thử tương thích |
| AzureWebJobsStorage | Kết nối Storage của Functions host | Có thể dùng connection string hoặc cấu hình identity-based tùy plan/runtime |
| APP_ENV | Setting ứng dụng tùy chọn | Không có semantics tự động từ Azure nếu app không đọc |
| WEBSITE_RUN_FROM_PACKAGE | Điều khiển cách ứng dụng chạy từ package ở các plan/kịch bản phù hợp | Không tự thêm vào mọi plan, đặc biệt phải kiểm tra Flex Consumption |
| WEBSITE_CONTENTAZUREFILECONNECTIONSTRING, WEBSITE_CONTENTSHARE | Liên quan content storage trên một số hosting plans | Không yêu cầu giống nhau cho mọi Functions plan; không tự xóa khi đổi sang managed identity |
| APPLICATIONINSIGHTS_CONNECTION_STRING | Thông tin cấu hình telemetry | Không đồng nghĩa credential để gọi mọi API |
| AzureWebJobs.<FunctionName>.Disabled | Có thể dùng để vô hiệu hóa Function cụ thể theo cơ chế hỗ trợ | Cẩn trọng với trigger khi dùng slots và thay đổi setting |

**Không chuyển tất cả setting thành secret.** Chỉ bí mật thực sự cần vault. Cấu hình không bí mật nên nằm trong IaC hoặc app settings được review để dễ theo dõi thay đổi.

### 3.5. Đặt tên và cấu hình phân cấp

Trong các trường hợp cấu hình identity-based connection, Azure Functions dùng nhóm app settings có **cùng prefix**, ví dụ:

~~~text
AzureWebJobsStorage__accountName
OrdersStorage__queueServiceUri
OrdersStorage__credential
OrdersStorage__clientId
~~~

Dấu hai gạch dưới là một phần cách tạo cấu hình theo tiền tố, khác với một setting tên đơn chứa connection string. Đối với ứng dụng .NET và environment variables, dấu hai gạch dưới cũng thường dùng biểu diễn cấu hình phân cấp; nhưng cách đọc tên sẽ tùy runtime/SDK/extension.

Không viết code giả định tất cả dấu hai gạch dưới đều có nghĩa giống nhau đối với mọi thư viện. Với Functions triggers/bindings, phải tuân theo schema connection riêng của extension tương ứng.

## 4. Secret: đặt ở đâu và không nên đặt ở đâu?

### 4.1. Những nơi dễ lộ secret

Rủi ro thường phát sinh khi:

- Ghi password trong source code hoặc Dockerfile.
- Commit local.settings.json có token thật.
- Đưa key vào CLI argument rồi bật shell history hoặc debug tracing.
- In environment variables ra Application Insights hoặc CI/CD log.
- Ghi secret vào HTTP response khi bật debug.
- Đưa credential vào URL query string.
- Dùng chung account key cho dev, staging và production.
- Cấp quyền Key Vault rộng thay vì chỉ một tập secret cần thiết.

Git history có thể giữ các commit cũ ngay cả sau khi xóa dòng secret trong branch hiện tại. Cần thực hiện **rotation/revocation** khi nghi lộ.

### 4.2. Azure Key Vault

Azure Key Vault có thể quản lý **secrets**, **keys** và **certificates**, nhưng các đối tượng không đồng nhất. Trong bài này tập trung vào secrets như API keys.

Một quy trình phù hợp:

1. Tạo/chuẩn bị vault trong subscription và resource group được quản trị.
2. Chọn permission model (Azure RBAC hoặc access policies) theo thiết kế tổ chức.
3. Đặt secret với tên rõ ràng và phân loại dữ liệu.
4. Cấp Function identity quyền tối thiểu để đọc secret cần thiết.
5. Cấu hình network access, firewall/private endpoint khi yêu cầu.
6. Tham chiếu secret từ Function settings hoặc gọi Key Vault SDK.
7. Thiết lập giám sát, vòng đời secret và runbook thu hồi.

Không dùng Key Vault chỉ như nơi nhập lại mọi environment variable mà không có chính sách quyền và vòng đời.

### 4.3. Key Vault references và SDK khác gì?

| Khía cạnh | Key Vault reference trong app setting | SDK gọi Key Vault trực tiếp |
|---|---|---|
| Code ứng dụng | Đọc app setting như giá trị cấu hình thông thường | Ứng dụng tự gọi Key Vault |
| Cơ chế identity | Platform dùng identity tham chiếu được cấu hình | SDK dùng credential chain hoặc managed identity |
| Cache/refresh | Theo cơ chế cache và refresh của nền tảng App Service/Functions | Ứng dụng tự thiết kế cache/retry/refresh |
| Lỗi thường gặp | Reference không resolve, identity hoặc network không đủ | SDK nhận 401/403/timeout, retry và auth config |
| Tính linh hoạt | Thuận tiện cho một secret được dùng như app setting | Hữu ích khi cần truy vấn nhiều secret hoặc điều kiện động |
| Truy vết | Cần kiểm tra trạng thái resolve và logs nền tảng | Ứng dụng có thể đo dependency và phân loại lỗi riêng |

**Key Vault reference có thể phân giải thành giá trị secret trong môi trường của tiến trình ứng dụng.** Do đó vẫn phải bảo vệ environment dumps, diagnostic endpoints, debug tools và quyền vào Function App. Dùng vault không làm plaintext biến mất khỏi bộ nhớ khi ứng dụng cần sử dụng.

## 5. Managed identity là gì?

### 5.1. Ý tưởng cốt lõi

Managed identity gắn một danh tính được Microsoft Entra ID quản lý với tài nguyên Azure. Ứng dụng có thể nhận access token cho dịch vụ hỗ trợ Entra ID mà không cần cất client secret hoặc certificate như service principal thông thường.

~~~mermaid
sequenceDiagram
    participant F as Azure Function
    participant M as Managed Identity endpoint
    participant E as Microsoft Entra ID
    participant S as Azure Storage / Key Vault
    F->>M: Yêu cầu token cho resource/scope
    M->>E: Trao đổi danh tính nền tảng
    E-->>M: Access token
    M-->>F: Token ngắn hạn
    F->>S: Gọi API cùng token
    S->>S: Xác thực token + kiểm tra quyền
    S-->>F: 200 hoặc lỗi xác thực/phân quyền
~~~

Sơ đồ mô tả logic. Token endpoint và chi tiết kỹ thuật do Azure platform quản lý; ứng dụng nên dùng SDK hỗ trợ Azure Identity thay vì tự viết giao thức token.

**Có managed identity chưa có quyền dữ liệu.** Sau khi bật identity vẫn phải cấp role hoặc quyền phù hợp ở Storage, Key Vault, Service Bus, database hay dịch vụ đích.

### 5.2. System-assigned và user-assigned

| Tiêu chí | System-assigned managed identity | User-assigned managed identity |
|---|---|---|
| Vòng đời | Gắn với tài nguyên Function App | Tài nguyên Azure độc lập |
| Khi xóa Function App | Danh tính hệ thống tương ứng không còn | Danh tính user-assigned vẫn có thể tồn tại |
| Tái sử dụng | Dành cho Function App cụ thể | Có thể gắn với nhiều tài nguyên được hỗ trợ |
| Độ phức tạp | Đơn giản cho ứng dụng riêng | Cần quản lý identity resource và vòng đời riêng |
| Principal/object ID | Gắn với identity của app và có thể đổi nếu tái tạo | Thuộc identity resource độc lập |
| Use case | Một Function App cần truy cập Storage và vault của mình | Nhiều Function Apps, slot hoặc workload cần identity chủ động/quản trị riêng |

Không mặc định tái sử dụng một user-assigned identity cho nhiều ứng dụng là an toàn hơn: chia sẻ identity có thể tăng **blast radius** nếu một ứng dụng bị xâm phạm. Chỉ chia sẻ khi quyền và vòng đời thật sự cần chung.

### 5.3. App identity và người dùng Entra là hai chủ thể khác nhau

- **User:** kỹ sư đăng nhập Azure Portal/CLI.
- **CI/CD identity:** danh tính pipeline có quyền cập nhật Function App.
- **Function managed identity:** danh tính mà mã chạy bên trong Function sử dụng để gọi dịch vụ.
- **HTTP caller identity:** người hoặc dịch vụ gọi endpoint của Function.
- **Service Account/credential ngoài Azure:** cơ chế riêng của bên thứ ba.

Không cấp mọi quyền cho cùng một principal chỉ để tiện triển khai. Một pipeline cần quyền deploy code không nhất thiết được quyền đọc secret runtime, và Function không cần Owner trên resource group để đọc một blob.

## 6. Thực hành 1: bật system-assigned identity

Giả sử Function App **func-orders-prod** thuộc resource group **rg-functions-prod** đã tồn tại với hosting plan/runtime phù hợp.

### 6.1. Kiểm tra subscription và Function App

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az functionapp show \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --query "{name:name,state:state,kind:kind,identity:identity}" \
  --output json
~~~

Lệnh show có thể trả thông tin identity ở cấu trúc khác tùy API; cần xác nhận Function App tồn tại trong đúng subscription/tenant. Không tự tạo mới ứng dụng production nếu chỉ cần kiểm tra.

### 6.2. Bật identity

~~~bash
az functionapp identity assign \
  --resource-group rg-functions-prod \
  --name func-orders-prod
~~~

Đọc principal ID:

~~~bash
PRINCIPAL_ID=$(az functionapp identity show \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --query principalId --output tsv)

echo "$PRINCIPAL_ID"
~~~

**principalId/object ID** là định danh dùng phổ biến cho Azure role assignment. **clientId** là định danh ứng dụng/managed identity theo ngữ cảnh khác; không lấy clientId rồi dùng thay cho object ID ở mọi CLI argument.

Identity được tạo xong vẫn chưa có quyền trên các dịch vụ đích. Việc thay đổi identity và role assignment có thể cần thời gian để Entra/RBAC phản ánh.

### 6.3. Cấp quyền chỉ đọc cho Blob Storage

Giả sử tài khoản Storage chứa container tài liệu mà Function chỉ cần đọc. Lấy resource ID của account:

~~~bash
STORAGE_ID=$(az storage account show \
  --resource-group rg-data-prod \
  --name stordersdata01 \
  --query id --output tsv)

echo "$STORAGE_ID"
~~~

Cấp role dữ liệu Blob:

~~~bash
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Reader" \
  --scope "$STORAGE_ID"
~~~

Role **Storage Blob Data Reader** phù hợp cho thao tác đọc Blob trong phạm vi được cấp, không phải role cho tất cả Storage operations. Với sản phẩm thật, có thể thu hẹp scope xuống container nếu công cụ/quyền hỗ trợ. Cần kiểm tra có role assignment khác rộng hơn bị kế thừa hay không.

### 6.4. Kiểm tra quyền đã cấp

~~~bash
az role assignment list \
  --assignee-object-id "$PRINCIPAL_ID" \
  --scope "$STORAGE_ID" \
  --include-inherited \
  --output table
~~~

Sự tồn tại của role assignment không chứng minh mạng tới Blob đã hoạt động; cần kiểm tra đường truy cập, quyền thực tế và kết quả gọi SDK.

Không khắc phục lỗi 403 bằng cách cấp Contributor toàn subscription. Phân biệt đúng **data-plane role** cho Blob với các role Azure quản lý Storage Account ở **management plane**.

## 7. Thực hành 2: tham chiếu secret từ Key Vault

### 7.1. Chọn permission model rõ ràng

Key Vault hỗ trợ các mô hình cấp quyền khác nhau theo cấu hình, phổ biến là **Azure RBAC** và **Vault access policies**. Hai mô hình không nên bị trộn lẫn tùy tiện.

Ví dụ dưới đây giả định vault **kv-orders-prod** đã được quản trị bằng Azure RBAC permission model. Nếu vault đang dùng access policies, cần cấp permission theo đúng mô hình vault thay vì áp role và kỳ vọng nó có hiệu lực như RBAC data plane.

**Không tự chuyển permission model của vault production** chỉ để chạy ví dụ, vì có thể thay đổi quyền của những ứng dụng khác.

### 7.2. Cấp quyền đọc secret cho Function

~~~bash
VAULT_ID=$(az keyvault show \
  --resource-group rg-security-prod \
  --name kv-orders-prod \
  --query id --output tsv)

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID"
~~~

Role trên cho phép truy cập secret values theo phạm vi được cấp trong mô hình Key Vault RBAC phù hợp. Cân nhắc thu hẹp scope nếu yêu cầu và sản phẩm hỗ trợ, đồng thời kiểm tra quyền kế thừa.

Các role như Key Vault Reader **không mặc nhiên cho phép đọc secret value**; tên role dễ gây nhầm giữa metadata và nội dung bí mật.

### 7.3. Tạo secret an toàn

Giả sử một API bên thứ ba cung cấp token. Người vận hành có quyền tạo/ghi secret dùng phương án được tổ chức cho phép để lưu giá trị trong vault.

Để tránh secret lọt vào history, logs hoặc process command line, bài này **không đưa ví dụ truyền token thật qua tham số CLI**. Có thể thực hiện qua quy trình secret provisioning/automation có vault permission phù hợp; các môi trường khác nhau cần chọn cách nhập bảo mật riêng.

Ví dụ tên secret:

~~~text
Vault: kv-orders-prod
Secret: partner-api-token
Secret value: [được lưu bằng quy trình quản lý bí mật]
~~~

Để tham chiếu phiên bản cụ thể hoặc phiên bản mới nhất, cần hiểu hậu quả của việc cố định version so với không cố định version. Một reference cố định version sẽ không tự trỏ sang version mới khi xoay secret.

### 7.4. Đặt Key Vault reference vào Function App setting

Cú pháp nền tảng thường gặp:

~~~text
@Microsoft.KeyVault(VaultName=kv-orders-prod;SecretName=partner-api-token)
~~~

Hoặc dùng dạng SecretUri phù hợp với secret identifier được Key Vault hỗ trợ:

~~~text
@Microsoft.KeyVault(SecretUri=https://kv-orders-prod.vault.azure.net/secrets/partner-api-token/<SECRET_VERSION>)
~~~

Ví dụ CLI (không chứa secret value):

~~~bash
az functionapp config appsettings set \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --settings 'PARTNER_API_TOKEN=@Microsoft.KeyVault(VaultName=kv-orders-prod;SecretName=partner-api-token)' \
  --query '[].{name:name,slotSetting:slotSetting}' \
  --output table
~~~

Sử dụng nháy đơn trong Bash để dấu chấm phẩy nằm trong một argument. **Windows PowerShell có quy tắc quoting khác**; hãy kiểm tra chuỗi truyền thực tế trước khi dùng trong pipeline.

Cấu hình Key Vault reference dùng **system-assigned identity theo mặc định trong nhiều kịch bản được hỗ trợ**; khi muốn dùng user-assigned identity cần cấu hình thuộc tính keyVaultReferenceIdentity phù hợp của Function App theo tài liệu. Đừng nghĩ chỉ attach user-assigned identity là nền tảng tự chuyển reference sang identity đó.

### 7.5. Đọc secret trong code

Trong code, sau khi platform giải quyết reference theo cơ chế hỗ trợ, ứng dụng chỉ cần đọc setting:

~~~python
import os

PARTNER_API_TOKEN = os.environ["PARTNER_API_TOKEN"]
~~~

**Không** in token ra console hoặc trả lại token trong HTTP response. Nếu Key Vault reference không được giải quyết do lỗi identity, quyền hoặc network, việc đọc setting có thể cho kết quả không như mong đợi; ứng dụng phải fail an toàn, không tiếp tục gọi API với một chuỗi reference chưa được phân giải.

Với Function có nhiều triggers/instances, cân nhắc thời điểm refresh và việc reload cấu hình khi secret đổi. Không nên assume đọc mỗi request là luôn nhận bản secret mới ngay lập tức.

### 7.6. Thời gian refresh và rotation

Key Vault references được nền tảng lưu cache và làm mới theo cơ chế App Service/Functions. Việc cập nhật secret tại vault **không đảm bảo mọi worker nhận giá trị mới ngay tức khắc**. Trong những kịch bản phổ biến, reference không chỉ rõ version có thể được làm mới trong chu kỳ lên tới khoảng 24 giờ; thay đổi cấu hình hoặc cơ chế refresh được hỗ trợ có thể thúc đẩy việc phân giải lại.

Quy trình rotation đề xuất:

1. Tạo secret version mới hoặc cấp credential mới ở bên thứ ba.
2. Bảo đảm một giai đoạn chuyển tiếp chấp nhận cả key cũ và key mới nếu nhà cung cấp hỗ trợ.
3. Cập nhật/refresh reference theo cơ chế được phép.
4. Kiểm thử Function qua health/transaction an toàn và theo dõi lỗi.
5. Thu hồi key cũ sau khi xác nhận toàn bộ clients đã chuyển.
6. Ghi change record, thời gian UTC và bằng chứng kiểm tra.

Nếu provider chỉ hỗ trợ một token, lên kế hoạch downtime/cutover và rollback phù hợp. Không xóa secret cũ trước khi có đường khôi phục.

## 8. User-assigned identity và Key Vault reference

### 8.1. Khi nào cần user-assigned identity?

User-assigned identity phù hợp nếu:

- Muốn quản lý vòng đời identity độc lập với Function App.
- Cần identity tồn tại trước khi Function App khởi động hoặc tham chiếu secret.
- Triển khai lại Function App thường xuyên nhưng muốn giữ principal/role assignment cố định.
- Dùng một identity được kiểm soát cho nhiều tài nguyên có **cùng mục đích/quyền**.
- Kịch bản hosting/Key Vault reference yêu cầu identity có sẵn trước khi cấu hình resource.

Không chia sẻ user-assigned identity cho tất cả function apps chỉ để giảm số role assignments; một identity có quyền rộng khiến mọi ứng dụng gắn identity có thể mang theo phạm vi truy cập lớn.

### 8.2. Tạo user-assigned identity

~~~bash
az identity create \
  --resource-group rg-identity-prod \
  --name id-func-orders \
  --location southeastasia
~~~

Lấy thông tin:

~~~bash
UAMI_ID=$(az identity show \
  --resource-group rg-identity-prod \
  --name id-func-orders \
  --query id --output tsv)

UAMI_CLIENT_ID=$(az identity show \
  --resource-group rg-identity-prod \
  --name id-func-orders \
  --query clientId --output tsv)

UAMI_PRINCIPAL_ID=$(az identity show \
  --resource-group rg-identity-prod \
  --name id-func-orders \
  --query principalId --output tsv)
~~~

Ba giá trị không giống nhau:

- **Resource ID:** định danh Azure Resource Manager cho identity.
- **Client ID:** chọn đúng managed identity khi ứng dụng hoặc SDK có nhiều identity.
- **Principal ID:** object/principal được cấp Azure RBAC role assignments.

Gắn identity vào Function App:

~~~bash
az functionapp identity assign \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --identities "$UAMI_ID"
~~~

Sau đó cấp role cho **UAMI_PRINCIPAL_ID** trên resource đích theo least privilege. Nếu muốn Key Vault references sử dụng user-assigned identity, phải cấu hình **keyVaultReferenceIdentity** bằng resource ID tương ứng qua Portal/ARM/IaC hoặc công cụ được hỗ trợ và kiểm tra kết quả.

### 8.3. Chọn đúng identity trong SDK

Với một user-assigned identity, Azure SDK thường cho phép chọn bằng client ID. Ví dụ ứng dụng có thể đặt setting:

~~~text
AZURE_CLIENT_ID=<UAMI_CLIENT_ID>
~~~

Trong các SDK hỗ trợ Azure Identity, AZURE_CLIENT_ID có thể được DefaultAzureCredential dùng để định danh managed identity tương ứng ở môi trường Azure. Không trộn client ID của identity này với principal ID của identity khác.

Khi dùng system-assigned identity, thường không cần chỉ định client ID. Nếu gắn nhiều identities cho cùng Function App, hãy cấu hình rõ loại credential/identity mà ứng dụng sử dụng; tránh phụ thuộc thứ tự chọn không chắc chắn.

## 9. Code minh họa: Python Function đọc Blob bằng identity

### 9.1. Vì sao không cần Storage Account key?

Một Function có quyền **Storage Blob Data Reader** có thể sử dụng Microsoft Entra access token qua Azure SDK để đọc Blob. Ứng dụng không cần giữ Account key cho thao tác đọc Blob theo mô hình hỗ trợ.

Ví dụ dưới đây giả định:

- Function App có managed identity phù hợp.
- Identity được cấp quyền đọc Blob/container.
- Storage account endpoint reachable qua network.
- Các thư viện azure-identity và azure-storage-blob đã được đưa vào dependencies.
- Chương trình không dùng trực tiếp key/connection string để tạo BlobServiceClient.

### 9.2. Mã Python tối giản

~~~python
import os

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

def read_small_text_document(blob_name: str) -> str:
    # Chỉ dùng cho tài liệu nhỏ, có tên đã được kiểm soát.
    account_url = os.environ["DOCUMENTS_BLOB_URI"]

    credential = DefaultAzureCredential()
    blob_service = BlobServiceClient(
        account_url=account_url,
        credential=credential,
    )
    blob = blob_service.get_blob_client(
        container="documents",
        blob=blob_name,
    )

    content = blob.download_blob().readall()
    return content.decode("utf-8")
~~~

Code cho thấy luồng credential, không phải Function HTTP endpoint production đầy đủ. Những ứng dụng thực phải:

- Kiểm soát input/blob name, tránh người dùng tự do đọc mọi tệp.
- Xác thực người gọi và kiểm tra quyền ở tầng ứng dụng.
- Xử lý BlobNotFound, 403, 429, timeout và retry theo nhu cầu.
- Không đọc một Blob rất lớn hoàn toàn vào RAM.
- Dùng client/credential tái sử dụng có kiểm soát thay vì tạo lại mọi thứ trên mỗi invocation khi phù hợp.
- Không log nội dung tài liệu nhạy cảm.

**DefaultAzureCredential** có thể sử dụng chuỗi credential khác nhau giữa máy phát triển và Azure (developer login, environment, managed identity...). Điều này hữu ích cho dev/prod nhưng cần kiểm soát môi trường và identity thực tế để không vô tình dùng quyền của người phát triển ở nơi không mong đợi.

### 9.3. Cấu hình không bí mật cho SDK

~~~bash
az functionapp config appsettings set \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --settings DOCUMENTS_BLOB_URI=https://stordersdata01.blob.core.windows.net/ \
  --query '[].{name:name}' \
  --output table
~~~

Giá trị này là service URI, không phải secret. Nếu Storage Account dùng private endpoint và chặn public access, URI vẫn dùng hostname dịch vụ nhưng DNS/private networking phải trả đích phù hợp.

### 9.4. Khi chạy local

Đăng nhập Azure CLI bằng tài khoản dev phù hợp hoặc sử dụng cơ chế developer identity được tổ chức cho phép; cấp quyền dev trên **tài nguyên dev**, không phải cấp Contributor production để convenience.

Kiểm tra credential đã thực sự chọn đúng principal. Nếu local chạy thành công nhưng production trả 403, thường là hai identity khác nhau với role assignments khác nhau.

## 10. Identity-based connections cho triggers và bindings

### 10.1. Điểm khác biệt giữa SDK và Functions binding

Ví dụ SDK ở phần trước tạo BlobServiceClient bằng Azure Identity và gọi trực tiếp. Nhưng một Azure Function có thể sử dụng **trigger/binding**, chẳng hạn QueueTrigger, BlobTrigger hoặc input binding. Extensions tạo kết nối và xử lý xác thực thay ứng dụng.

Do đó, cấu hình cho SDK không tự động khiến trigger dùng managed identity. Phải dùng **extension version có hỗ trợ identity-based connections** và khai báo đúng connection prefix, service URI, role và hosting-plan requirements.

### 10.2. Ví dụ QueueTrigger trong Python v2

Giả sử function_app.py:

~~~python
import azure.functions as func
import logging

app = func.FunctionApp()

@app.queue_trigger(
    arg_name="message",
    queue_name="orders-pending",
    connection="OrdersQueue",
)
def process_order(message: func.QueueMessage) -> None:
    logging.info("Received an order message")
    # Gọi lớp nghiệp vụ; không log toàn bộ payload nếu chứa dữ liệu nhạy cảm.
~~~

Trong decorator, **connection="OrdersQueue"** chỉ prefix cấu hình kết nối. Nó không nên chứa connection string hoặc token thật.

Nếu extension và hosting plan của ứng dụng hỗ trợ identity-based queue connection, các app settings có thể có dạng:

~~~text
OrdersQueue__queueServiceUri=https://stordersqueue01.queue.core.windows.net/
~~~

Nếu dùng user-assigned managed identity được hỗ trợ:

~~~text
OrdersQueue__credential=managedidentity
OrdersQueue__clientId=<UAMI_CLIENT_ID>
~~~

Tên setting, khả năng mặc định dùng system-assigned identity và yêu cầu bổ sung phụ thuộc phiên bản Storage Queue extension/Functions runtime. **Không thêm connection string tên chính xác OrdersQueue cùng lúc** nếu đang cố sử dụng prefix identity-based: exact match có thể được ưu tiên và làm binding lấy connection string thay vì những settings mới.

Identity xử lý QueueTrigger cần quyền thao tác queue cần thiết, không chỉ quyền đọc metadata. Role data-plane có thể là **Storage Queue Data Contributor** hoặc các vai trò granular phù hợp với thao tác theo tính năng/service. Xem permission matrix hiện hành và kiểm tra thực tế việc đọc/xóa message.

### 10.3. BlobTrigger có thể cần nhiều loại quyền

Một BlobTrigger có thể cần quyền truy cập blob nguồn, lưu checkpoint/receipt, dùng queue nội bộ hoặc những dịch vụ hỗ trợ host tùy extension và cơ chế xử lý. Vì vậy:

- Không nghĩ Storage Blob Data Reader luôn đủ cho tất cả BlobTrigger.
- Xác định kết nối được dùng để **đọc blob** và kết nối dùng cho **host state**.
- Kiểm tra extension version 5.x hoặc phiên bản tương ứng hỗ trợ identity.
- Phân biệt event-based BlobTrigger và cơ chế polling nếu extension hỗ trợ.
- Cấp đúng data roles và kiểm tra logs của trigger.
- Thực hiện test với file thật trong container dev trước khi bỏ connection string.

Kết nối **AzureWebJobsStorage** của Functions host và kết nối **OrdersQueue** của binding là những mối liên hệ khác nhau dù đôi khi cùng trỏ về một Storage Account.

### 10.4. Các dịch vụ khác

| Trigger/binding | Loại quyền cần xem | Điều kiện quan trọng |
|---|---|---|
| Azure Queue Storage | Queue data-plane | Extension hỗ trợ identity-based config và thao tác trigger |
| Azure Blob Storage | Blob data-plane, có thể thêm quyền host/queue | Checkpoint/receipt và mode trigger |
| Azure Service Bus | Service Bus Data Receiver/Sender theo chiều dùng | Namespace/entity permissions, extension và network |
| Azure Event Hubs | Event Hubs Data Receiver/Sender theo kịch bản | Consumer group, checkpoint store, scaling |
| Azure Cosmos DB | Data-plane RBAC tương ứng | SDK/extension support và quyền trên container/database |
| Azure SQL | Entra authentication/SQL permissions | Driver/connection mode và database contained user |
| HTTP trigger | Bảo vệ inbound theo thiết kế | Không tự dùng managed identity để xác thực mọi caller |

Nhiều dịch vụ Azure phân biệt management-plane Azure RBAC với data-plane permissions. Role Contributor trên resource group không tự thay thế tất cả quyền truy cập dữ liệu trong một cơ chế kết nối runtime.

## 11. AzureWebJobsStorage: kết nối đặc biệt của Functions host

### 11.1. Host storage dùng để làm gì?

Azure Functions runtime cần Storage trong nhiều kịch bản để lưu trạng thái vận hành, khóa/lease và dữ liệu phục vụ hoạt động của host/triggers, tùy hosting plan và loại trigger.

Ở một số kiến trúc cũ hoặc deployment mặc định, app setting có dạng:

~~~text
AzureWebJobsStorage=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net
~~~

Đây là storage connection string chứa key; **không đưa giá trị thật vào bài tập hoặc repository**. Một số phiên bản hosting/runtime cho phép hoặc khuyến khích cấu hình host storage bằng managed identity để giảm phụ thuộc vào key.

Không được xóa AzureWebJobsStorage khỏi Function App mà chưa có cấu hình tương đương phù hợp; nhiều triggers có thể ngừng hoạt động hoặc host không khởi động đúng.

### 11.2. Identity-based host storage

Trong môi trường và runtime hỗ trợ, có thể cấu hình theo prefix:

~~~text
AzureWebJobsStorage__accountName=stfunctionshost01
~~~

Hoặc dùng những service URIs khi cần (ví dụ sovereign cloud/custom endpoint hoặc theo feature):

~~~text
AzureWebJobsStorage__blobServiceUri=https://stfunctionshost01.blob.core.windows.net/
AzureWebJobsStorage__queueServiceUri=https://stfunctionshost01.queue.core.windows.net/
AzureWebJobsStorage__tableServiceUri=https://stfunctionshost01.table.core.windows.net/
~~~

Cấu hình service URI cần được kiểm tra theo Functions host/extension thực tế: không phải mọi trường hợp đều cần cả ba URIs, và định dạng accountName có điều kiện sử dụng.

Với user-assigned identity được hỗ trợ:

~~~text
AzureWebJobsStorage__credential=managedidentity
AzureWebJobsStorage__clientId=<UAMI_CLIENT_ID>
~~~

**Chỉ chuyển sang identity-based host storage sau khi đã kiểm tra compatibility của hosting plan, worker runtime, extensions và deployment method.** Những thành phần khác như content share, package deployment hoặc diagnostic extension có thể vẫn cần cấu hình riêng và không tự kế thừa token-based auth của host storage.

### 11.3. Quyền host storage không giống quyền ứng dụng

Host cần thao tác lưu trạng thái vận hành, nên thường cần nhiều hơn quyền Blob Reader. Tùy cấu hình, có thể cần các quyền dữ liệu Blob/Queue/Table và một số thao tác quản lý storage. Danh sách role chính xác phụ thuộc Functions host, triggers và extension.

Ví dụ kiểm tra các nhóm quyền:

| Thành phần | Thao tác | Cấp quyền theo |
|---|---|---|
| Functions host | Lưu khóa/receipt/state/lease theo tính năng | Host storage identity và role matrix chính thức |
| QueueTrigger | Đọc/xử lý/xóa message | Binding connection identity |
| Blob input SDK | Đọc blob tài liệu | App managed identity với Blob Data Reader khi đủ |
| Key Vault reference | Đọc secret | Identity tham chiếu Key Vault và secret permission |
| Container Apps/App Service deployment | Deploy artifact | CI/CD identity, khác runtime identity |

Không cấp quyền Storage Account Contributor hoặc Owner một cách rộng rãi cho mọi Function chỉ vì host storage khởi động lỗi. Trước tiên xác định yêu cầu permission cụ thể và phạm vi tối thiểu.

### 11.4. Kế hoạch chuyển đổi từ Storage key sang identity

1. Kiểm kê AzureWebJobsStorage và tất cả connection strings/bindings đang dùng.
2. Xác định runtime, extension versions và plan có hỗ trợ identity-based connections không.
3. Bật managed identity, gán đúng data-plane roles trước.
4. Chuẩn bị môi trường staging hoặc Function App thử nghiệm với host storage tương đương.
5. Cấu hình prefix identity-based đúng, tránh xung đột exact-match setting.
6. Khởi động Function, kiểm tra host logs và trigger thực sự hoạt động.
7. Kiểm tra network/private endpoint/DNS và scale behavior.
8. Chuyển production theo kế hoạch rollback; thu hồi key chỉ khi không còn dependency.
9. Ghi bằng chứng cấu hình và kế hoạch xoay key còn tồn tại.

Đặc biệt lưu ý **WEBSITE_CONTENTAZUREFILECONNECTIONSTRING** và **WEBSITE_CONTENTSHARE** ở những plans cần Azure Files content share. Chúng không tự được thay thế chỉ bằng AzureWebJobsStorage__accountName; kiểm tra khả năng identity-based configuration cho content storage của **đúng hosting plan**.

## 12. Bảo mật mạng khi Function truy cập Key Vault và Storage

### 12.1. Managed identity không tạo đường mạng

Một Function có RBAC đúng nhưng không kết nối được đến dịch vụ vì firewall/DNS vẫn thất bại. Hai điều kiện phải có đồng thời:

~~~text
Function runtime
  ├─ Token + quyền RBAC đúng
  └─ DNS + route + firewall/private endpoint đúng
              |
              v
       Key Vault / Storage / Service Bus
~~~

Đối với production có yêu cầu mạng riêng:

- Xác định Function hosting plan có hỗ trợ VNet integration outbound theo mô hình nào.
- Cấu hình Private Endpoint ở dịch vụ đích nếu muốn truy cập riêng.
- Liên kết Private DNS zone, hoặc có DNS forwarder/Private Resolver khi dùng custom DNS.
- Bảo đảm NSG, UDR và firewall cho phép yêu cầu cần thiết.
- Kiểm tra truy cập tới Entra token endpoints và các dependency vận hành mà runtime cần.
- Theo dõi DNS, connection timeout, 403 do network rules và lỗi authorization riêng.

### 12.2. Inbound và outbound khác nhau

**VNet Integration** của Function App chủ yếu giải quyết kết nối **outbound** của ứng dụng vào mạng theo tính năng plan. **Private Endpoint cho Function App** là một khả năng khác liên quan kết nối inbound, với điều kiện hosting plan/SKU riêng.

Vì vậy:

- Function có thể được gọi công khai qua HTTP nhưng gọi Storage qua mạng riêng.
- Function có thể được giới hạn HTTP inbound mà vẫn cần outbound egress để lấy token, gửi telemetry hoặc gọi API ngoài.
- Tắt public network access ở Storage/Vault trước khi private DNS/routing hoàn tất có thể làm Function mất kết nối.
- Không đồng nhất việc Function App có managed identity với việc endpoint HTTP chỉ chấp nhận caller từ VNet.

### 12.3. Vì sao Key Vault reference đôi khi không resolve?

Một số nguyên nhân:

1. Chưa bật system-assigned identity hoặc chưa gắn user-assigned identity phù hợp.
2. keyVaultReferenceIdentity đang trỏ sai identity.
3. Vault dùng permission model khác với role bạn vừa cấp.
4. Role chưa có hiệu lực hoặc không đủ quyền đọc secret value.
5. Secret name/version sai, secret disabled/expired hoặc không còn tồn tại.
6. Function App không đi được tới Vault vì firewall, private endpoint hoặc DNS.
7. Nền tảng đang dùng giá trị cache cũ hoặc chưa refresh theo kế hoạch.

Để chẩn đoán, bắt đầu bằng **trạng thái reference trong cấu hình**, identity/principal, Key Vault permission model và network reachability. Không log nguyên secret value để chứng minh nó đã được đọc.

## 13. Deployment slots, cấu hình môi trường và triggers

### 13.1. Slot không phải một sandbox an toàn theo mặc định

Một Function App trên tier hỗ trợ deployment slots có thể có production và staging. Tùy platform, chúng chia sẻ một số tài nguyên nhưng có hostname và cấu hình riêng.

Một số Function triggers **có thể thực thi trong staging**, không chỉ sau khi swap. Nếu staging đọc cùng Queue Storage hoặc Service Bus subscription như production, hai slot có thể cạnh tranh xử lý message, tạo side effect hoặc xử lý trùng.

Thiết kế cần:

- Tách queue/topic/container theo môi trường nếu phù hợp.
- Kiểm tra setting nào cần đánh dấu **deployment slot setting** (sticky).
- Quản lý việc bật/tắt triggers của staging theo cơ chế Functions hỗ trợ.
- Không đặt database migration/logic gửi email vào startup/warm-up không được kiểm soát.
- Kiểm tra managed identity và Key Vault access riêng của từng slot theo tính năng.
- Có approval, smoke test và rollback plan cho Function App và dữ liệu.

### 13.2. Ví dụ sticky settings

~~~text
Production:
  APP_ENV=production              [slot-specific]
  ORDERS_QUEUE_URI=...prod...     [slot-specific]

Staging:
  APP_ENV=staging                 [slot-specific]
  ORDERS_QUEUE_URI=...test...     [slot-specific]
~~~

Đây là mô hình kỳ vọng, không phải giá trị Azure tự động áp đặt. Phải đánh dấu đúng setting tại Azure App Service/Function deployment slots. Nếu một connection setting không sticky, swap có thể chuyển giá trị không mong muốn giữa môi trường theo quy tắc dịch vụ.

**Managed identity và cấu hình slot** có tính chất riêng; không tự suy luận system-assigned identity hoặc user-assigned identity sẽ chuyển theo mã nguồn khi swap. Kiểm tra identity, RBAC và Key Vault references ở cả source/target trước thay đổi.

### 13.3. Pipeline cấu hình ứng dụng an toàn

Một pipeline phát hành phù hợp có thể gồm:

~~~mermaid
flowchart TD
    S["Source code / reviewed IaC"] --> B["Build + tests"]
    B --> A["Artifact bất biến"]
    C["Cấu hình không bí mật trong IaC"] --> D["Deploy staging"]
    A --> D
    V["Secret trong Key Vault + RBAC"] -.-> D
    D --> T["Smoke test / verify identity / health"]
    T --> P{"Approval"}
    P -->|Đạt| R["Release production"]
    P -->|Không| F["Không chuyển traffic/trigger"]
    R --> M["Monitor + rollback nếu cần"]
~~~

Nếu build artifact chứa host.json hoặc function.json cần thiết, bảo đảm chúng được đóng gói theo worker runtime. Secret không được nằm trong artifact; cấu hình được áp dụng theo deployment stage.

**Không cấp CI/CD pipeline quyền đọc mọi Key Vault secret** chỉ để điền app setting. Thường chỉ cần ghi Key Vault reference string và cấp quyền đọc secret cho Function runtime identity.

## 14. Quan sát, log và điều tra vấn đề identity

### 14.1. Nguồn log khác nhau

| Nguồn | Điều giúp xác minh |
|---|---|
| Azure Activity Log | Ai bật identity, sửa Function App settings, gán role, đổi VNet hoặc resource |
| Microsoft Entra sign-in/managed identity logs theo tính năng | Hoạt động xác thực identity trong phạm vi log được cung cấp |
| Azure Functions host logs | Host startup, trigger initialization, binding errors |
| Application Insights | Exceptions, traces, dependencies, latency và invocation success |
| Key Vault diagnostic logs | Secret access, denied requests, network/authentication evidence theo cấu hình |
| Azure Storage metrics/logs | Truy cập data plane, lỗi 403/429, availability, throttling |
| Azure RBAC role assignments | Quyền hiện tại và phạm vi role |
| CI/CD release records | Artifact, config change, approver, thời gian |
| Network/DNS diagnostics | Private endpoint resolution, firewall deny, timeout |

Không mặc định mọi request của Function được ghi đầy đủ nếu Application Insights/diagnostic settings chưa được cấu hình. Cũng không tin rằng **Azure Activity Log** sẽ ghi từng lần Function đọc Blob hoặc Secret; đây là hai mặt phẳng dữ liệu/management khác nhau.

### 14.2. Kiểm tra app settings mà không lộ value

~~~bash
az functionapp config appsettings list \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --query '[].{name:name,slotSetting:slotSetting}' \
  --output table
~~~

Khi phải kiểm tra một cấu hình, có thể xem tên và metadata thay vì giá trị. Không chạy lệnh list nguyên output JSON trong pipeline log nếu có khả năng chứa credential.

Kiểm tra identity:

~~~bash
az functionapp identity show \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --output json
~~~

Kiểm tra role bindings của identity với scope đích. Khi log không đủ rõ, tránh bật debug để in toàn bộ environment hoặc authorization headers.

### 14.3. KQL minh họa tìm lỗi Function

Nếu Azure Functions được tích hợp workspace-based Application Insights và có bảng AppExceptions:

~~~kusto
AppExceptions
| where TimeGenerated > ago(1h)
| summarize Failures = count() by bin(TimeGenerated, 5m), ProblemId
| order by TimeGenerated asc
~~~

Đây là truy vấn mẫu cho schema có trường ProblemId; workspace/agent khác có thể dùng bảng hoặc trường khác. Kiểm tra telemetry thực tế và chọn dimension phù hợp để phân biệt production/staging và các Function.

Khi điều tra lỗi Key Vault/Storage, xem mã trạng thái, resource ID, operation, correlation ID và thời điểm UTC. **Không lưu secret value, SAS token hoặc Authorization header** trong log điều tra.

### 14.4. Alert có ích

- Function invocation failure rate tăng đột biến.
- Host startup/binding initialization error sau khi chuyển identity.
- Key Vault access denied hoặc secret expired.
- Storage authentication/authorization failure tăng.
- Function bị restart liên tục sau thay đổi app settings.
- Managed identity/role assignments bị thay đổi ngoài cửa sổ phê duyệt.
- Secret reference resolution lỗi hoặc không được refresh đúng kỳ vọng.
- Queue backlog tăng khi trigger không hoạt động.
- Application Insights không còn nhận telemetry theo baseline.
- Chi phí Key Vault/Storage/Functions/Log Analytics tăng bất thường.

Bảo đảm alert không ghi vào thông báo giá trị bí mật hoặc dữ liệu nhận diện không cần thiết.

## 15. Quy trình chẩn đoán lỗi phổ biến

### 15.1. Phân biệt các loại lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
|---|---|---|
| App setting không tồn tại | Chưa cấu hình trên Azure; nhầm local.settings.json với cloud | Kiểm tra app settings names và deployment stage |
| Key Vault reference chưa resolve | Identity/role/vault policy/network/secret version | Kiểm tra status reference, principal, RBAC và DNS |
| Key Vault trả 403 | Thiếu quyền secret, sai principal hoặc firewall | Đối chiếu permission model và diagnostic logs |
| Storage Blob trả 403 | Thiếu data role, scope sai hoặc Storage firewall | Xác nhận Blob Data Reader/Contributor, endpoint và network |
| Token acquisition failed | Managed identity chưa gắn, user-assigned client ID sai hoặc dịch vụ identity không sẵn sàng | Kiểm tra identity object, client ID, SDK credential chain |
| local chạy nhưng Azure lỗi | Local dùng developer credential có quyền rộng hơn identity trên Azure | So sánh principal/scope và runtime config |
| Function host không khởi động | AzureWebJobsStorage lỗi, storage bị chặn hoặc runtime settings sai | Host logs, host storage URI/roles và Functions runtime |
| QueueTrigger không chạy | Connection prefix sai, extension không hỗ trợ identity hoặc thiếu Queue Data role | Host/binding logs, service URI, role, trigger status |
| BlobTrigger không chạy | Storage extension/mode hoặc host checkpoint/queue permission thiếu | Kiểm tra extension, container, receipts và host storage |
| App crash sau config change | Setting sai, Key Vault reference unresolved, startup exception | Application Insights và version/config change |
| Vault private endpoint nhưng request timeout | VNet integration, DNS/UDR/NSG lỗi | Resolve private FQDN từ đúng runtime path, kiểm tra outbound |
| Connection string vẫn được dùng | Exact-match setting còn tồn tại song song prefix identity | Kiểm tra names của các app settings |
| User-assigned identity có role nhưng SDK dùng system identity | Chưa chọn clientId hoặc chain dùng identity khác | Kiểm tra AZURE_CLIENT_ID và credential configuration |
| Function key được chấp nhận dù client không dùng Entra token | HTTP trigger sử dụng Function key auth | Phân biệt inbound Function auth với outbound managed identity |
| Secret rotation xong app vẫn dùng bản cũ | Reference cache/SDK cache hoặc pinned version | Kiểm tra refresh strategy và versioned reference |
| Pipeline in ra secret | Debug output hoặc lệnh list settings không lọc value | Thu hồi secret, xóa/giới hạn log, sửa script |

### 15.2. Quy trình điều tra có thứ tự

1. **Ứng dụng:** xác định Function App, slot, subscription và thời điểm phát sinh lỗi.
2. **Cấu hình:** kiểm tra **tên** app setting, runtime, extension và giá trị non-secret khi được phép.
3. **Danh tính:** xác định system-assigned/user-assigned identity mà host hoặc SDK thực sự dùng.
4. **Quyền:** kiểm tra role data-plane và scope của resource đích; đừng đánh đồng role quản trị.
5. **Mạng:** xác nhận DNS, route, VNet integration, firewall và Private Endpoint.
6. **Secret/version:** nếu dùng vault reference, kiểm tra secret tồn tại, được bật và cơ chế refresh.
7. **Binding/host:** kiểm tra AzureWebJobsStorage, host locks/receipts và extension connection prefix.
8. **Logs/telemetry:** đối chiếu error code, correlation ID, thời gian UTC và thay đổi gần nhất.
9. **Rollback:** phục hồi cấu hình trước đó theo kế hoạch, kiểm tra triggers và dữ liệu.
10. **Nguyên nhân gốc:** ghi incident record và thêm test/policy ngăn tái diễn.

**Đừng giải quyết lỗi 403 bằng cách cấp Owner toàn resource group, bật access key cho mọi dịch vụ hoặc mở public network vô thời hạn.** Hãy kiểm tra đúng lớp gây lỗi.

## 16. Tình huống thực tế: Function xử lý tài liệu theo sự kiện

Một nhóm phát triển hệ thống hóa đơn muốn sử dụng Azure Functions để xử lý file mới:

- Người dùng tải tài liệu lên Azure Blob Storage.
- BlobTrigger hoặc Event Grid đưa sự kiện vào Function theo mô hình được chọn.
- Function đọc dữ liệu, trích metadata, gửi thông báo tới Queue hoặc Service Bus.
- Function gọi API đối tác bằng token được lưu trong Key Vault.
- Application Insights theo dõi thời gian xử lý và lỗi.

### 16.1. Thiết kế cấu hình

| Thành phần | Cấu hình hoặc identity | Kiểm soát |
|---|---|---|
| Function App | FUNCTIONS_WORKER_RUNTIME, APP_ENV, telemetry settings | Quản lý bằng IaC |
| Host storage | AzureWebJobsStorage theo cơ chế được hỗ trợ | Identity/role riêng và network |
| Blob input | DOCUMENTS_BLOB_URI hoặc binding connection prefix | Blob data role tối thiểu |
| Queue output | Identity-based connection phù hợp | Queue send quyền vừa đủ |
| Key Vault | PARTNER_API_TOKEN reference | Secrets User hoặc access policy tương ứng |
| Application code | SDK Azure Identity | Không hard-code account key |
| CI/CD | Deploy artifact và non-secret config | WIF/managed identity, không cần đọc runtime secret |
| Monitoring | App Insights, host/Storage/Key Vault logs | Không ghi file payload hay secret |

### 16.2. Luồng hoạt động

~~~mermaid
flowchart LR
    U["Upload tài liệu"] --> B["Azure Blob Storage"]
    B --> F["Azure Function xử lý"]
    I["Managed Identity"] -.-> F
    F --> K["Key Vault: token đối tác"]
    F --> Q["Queue / Service Bus"]
    F --> P["API đối tác"]
    F --> M["Application Insights"]
    D["IaC + RBAC + Network"] -.-> F
~~~

Cần phân biệt khi dùng BlobTrigger thì Function host có quyền và network để quan sát sự kiện, còn chính nghiệp vụ có quyền đọc blob qua binding/SDK. Sự khác biệt này ảnh hưởng số role và khả năng chẩn đoán sự cố.

### 16.3. Kế hoạch chuyển từ key sang identity

Giả sử phiên bản v1 sử dụng Storage connection string chứa account key, phiên bản v2 chuyển sang managed identity:

1. Kiểm kê tất cả Function bindings và AzureWebJobsStorage.
2. Nâng/kiểm tra extensions hỗ trợ identity-based connections.
3. Bật managed identity và cấp role ở phạm vi cần thiết.
4. Chuẩn bị Storage networking/Private DNS cho runtime.
5. Triển khai v2 lên Function App/slot test có queue/container riêng.
6. Thay connection string bằng nhóm settings identity-based tương ứng.
7. Kiểm tra host startup, BlobTrigger/QueueTrigger, checkpoint và lần xử lý thực tế.
8. Ghi image/artifact version và settings metadata (không ghi secret).
9. Deploy production có approval và cửa sổ theo dõi.
10. Sau khi hết phụ thuộc, xoay/thu hồi access key cũ theo kế hoạch.

Nếu hai cấu hình exact connection string và prefix identity vẫn tồn tại, **phải kiểm tra cấu hình thật mà extension chọn**, không kết luận migration thành công chỉ vì role assignment đã có.

### 16.4. Chấp nhận release

- Function nhận đúng sự kiện và không xử lý trùng ngoài khả năng idempotency.
- Identity đọc blob/ghi queue đúng quyền, không có role rộng bất thường.
- App vẫn hoạt động khi key cũ bị thu hồi trong test có kiểm soát.
- Key Vault reference được resolve ở đúng môi trường.
- Không có secret trong source, artifact, logs và response.
- DNS/network private hoạt động và không mở public ngoài chính sách.
- Khi một dependency lỗi, Function có retry/dead-letter và alert phù hợp.
- Cost/latency theo kỳ đạt ngưỡng đã thống nhất.
- Có runbook rollback, rotation và định danh người quản trị.

## 17. Hiệu năng, độ tin cậy và chi phí

### 17.1. Managed identity và Key Vault có tác động vận hành

Token acquisition, Key Vault resolution và network calls có thể ảnh hưởng cold start hoặc thời gian xử lý nếu thiết kế không hợp lý. Một số nguyên tắc:

- Sử dụng Azure Identity SDK chính thức, cho phép credential/token caching theo SDK.
- Không gọi Key Vault cho cùng một secret ở mọi invocation nếu không có nhu cầu và không có cache/refresh strategy.
- Không lưu secret vĩnh viễn trong global state nếu tổ chức yêu cầu rotation nhanh.
- Đặt timeout/retry có giới hạn cho Storage/Key Vault/API bên ngoài.
- Xử lý 429 throttling, 5xx và transient network errors khác với 403 permission denied.
- Dùng async SDK ở workload I/O-bound nếu runtime hỗ trợ và cách gọi được viết đúng.
- Giữ client/credential phù hợp vòng đời worker khi giúp giảm overhead.
- Tránh log payload và secret trong trường hợp retry thất bại.

**Không retry vô hạn lỗi 403**: nếu role hoặc policy sai, retry chỉ tăng traffic, log và chi phí mà không sửa nguyên nhân.

### 17.2. Hosting plan ảnh hưởng cách cấu hình

Azure Functions có các hosting plans/kiểu triển khai khác nhau, chẳng hạn Consumption trong kịch bản còn hỗ trợ, Flex Consumption, Premium và Dedicated. Từng plan có khả năng khác nhau về:

- VNet integration/private networking.
- Cold start, always-ready instances và scaling.
- Content storage và cách deploy package.
- Deployment slots và giới hạn tính năng.
- Cấu hình host storage/identity-based auth.
- Thời gian chạy tối đa và concurrency.
- Pricing theo execution, resources hoặc provisioned capacity.

Không dùng một checklist WEBSITE_CONTENTAZUREFILECONNECTIONSTRING/WEBSITE_RUN_FROM_PACKAGE áp dụng cho mọi plan. Cần chọn plan trước rồi kiểm tra các settings runtime được hỗ trợ.

### 17.3. Các khoản chi phí cần xem

- Compute/execution/capacity của Function App theo plan.
- Storage host và data-plane operations.
- Key Vault secrets operations và networking theo mô hình giá.
- Private Endpoint, NAT, VNet integration hoặc giải pháp kết nối riêng.
- Application Insights/Log Analytics ingestion và retention.
- Dữ liệu truyền, Service Bus/Queue, Event Grid và các dependency.
- Staging environments, slot resources và quá trình test.
- Công sức rotation, kiểm toán IAM, DR và incident response.

Managed identity giúp giảm nhu cầu quản lý secret nhưng **không tự loại bỏ phí của các dịch vụ mà identity truy cập**. Chọn budget alert theo resource group/tag và xem Cost Management thực tế.

## 18. Checklist trước production

### Cấu hình

- [ ] Tách cấu hình không bí mật khỏi secrets và source code.
- [ ] local.settings.json không chứa secret được commit vào Git.
- [ ] FUNCTIONS_WORKER_RUNTIME, FUNCTIONS_EXTENSION_VERSION và host settings phù hợp runtime/plan.
- [ ] App settings quan trọng được quản lý bằng IaC/release pipeline.
- [ ] Không in giá trị app setting chứa secret khi kiểm tra bằng CLI/log.
- [ ] Có kế hoạch lưu trữ và xoay secret từ bên thứ ba.
- [ ] Key Vault reference dùng cú pháp đúng và có refresh/rotation strategy.
- [ ] Staging/production có cấu hình tách biệt, trigger không xử lý nhầm dữ liệu.

### Identity và bảo mật

- [ ] Đã chọn system-assigned hoặc user-assigned identity theo vòng đời.
- [ ] Role assignments dùng **principal ID đúng** và scope tối thiểu.
- [ ] Vault permission model và secret-level access được kiểm tra.
- [ ] Storage data roles được cấp cho đúng Blob/Queue/host operations.
- [ ] Trigger extensions có hỗ trợ identity-based connection trên runtime đang dùng.
- [ ] Không còn connection string chứa key cũ khi migration đã hoàn tất và đã xác minh.
- [ ] HTTP Function có inbound authentication riêng; managed identity outbound không thay thế bảo vệ API.
- [ ] VNet/private endpoint/DNS và egress được kiểm tra nếu dịch vụ chặn public access.
- [ ] Không có credential thật trong artifact, logs hoặc pipeline variables không bảo vệ.

### Vận hành

- [ ] Host khởi động, triggers chạy và các bindings hoạt động với identity mới.
- [ ] Có telemetry cho 401/403/429, Key Vault failure và Storage error.
- [ ] Có alert khi trigger backlog, function failure hoặc secret rotation thất bại.
- [ ] Có runbook đổi secret, cấp/tước role và xử lý mất network.
- [ ] Có kế hoạch rollback cấu hình khi Function startup fail.
- [ ] Có định kỳ rà soát role assignments và Key Vault access logs.
- [ ] Có thống kê chi phí Function, Key Vault, Storage, network và monitoring.

## 19. Câu hỏi tự kiểm tra

1. **App setting khác secret như thế nào?** App setting là nơi cung cấp giá trị cấu hình; secret là giá trị nhạy cảm cần bảo vệ, có thể được tham chiếu qua setting.
2. **local.settings.json có tự áp dụng lên Function App production không?** Không. Cần cấu hình trên Azure theo quy trình triển khai.
3. **IsEncrypted=false có khiến local.settings.json an toàn để commit không?** Không.
4. **Managed identity giải quyết vấn đề chính nào?** Cho ứng dụng danh tính Entra do Azure quản lý để xin token mà không cần client secret dài hạn.
5. **Bật system-assigned identity có tự cho Function quyền đọc Blob không?** Không. Còn phải có data-plane role và network.
6. **System-assigned khác user-assigned thế nào?** Một loại có vòng đời gắn với Function App, loại còn lại là Azure resource độc lập.
7. **Principal ID và client ID có dùng thay nhau ở mọi chỗ không?** Không. Role assignment thường dùng principal ID; SDK có thể dùng client ID để chọn user-assigned identity.
8. **Key Vault reference có cần sửa code đọc environment variable không?** Thường không; nền tảng giải quyết reference theo cơ chế hỗ trợ, ứng dụng đọc app setting.
9. **Key Vault reference có luôn refresh ngay khi secret mới được tạo không?** Không. Cần hiểu caching/refresh và rotation strategy.
10. **Key Vault Reader có mặc nhiên xem được secret value không?** Không. Quyền đọc nội dung bí mật phụ thuộc permission model và role/policy cụ thể.
11. **Local DefaultAzureCredential và managed identity production có thể là hai principal khác nhau không?** Có; cần kiểm tra RBAC cho từng môi trường.
12. **HTTP Function có managed identity thì tự bảo vệ endpoint khỏi client lạ không?** Không. Inbound authentication là vấn đề riêng.
13. **AzureWebJobsStorage dùng cho chuyện gì?** Kết nối vận hành của Functions host và một số trigger/host state theo plan.
14. **Thay AzureWebJobsStorage connection string bằng setting accountName có luôn chạy không?** Không. Cần runtime/plan/extension compatibility và RBAC đúng.
15. **Trong QueueTrigger, connection="OrdersQueue" có phải secret thật không?** Không. Nó tham chiếu tên/prefix connection settings.
16. **Vì sao BlobTrigger có thể cần quyền Queue bên cạnh quyền Blob?** Một số cơ chế trigger/host dùng queue/receipt/checkpoint nội bộ.
17. **Private Endpoint có tự cấp quyền đọc Key Vault không?** Không. Nó xử lý đường mạng, không thay thế Azure RBAC.
18. **403 từ Storage luôn có nghĩa thiếu RBAC không?** Không. Có thể là firewall/network hoặc cơ chế auth khác; xem mã và log.
19. **Vì sao không nên để staging và production dùng cùng QueueTrigger source tùy tiện?** Hai slot có thể xử lý cạnh tranh hoặc gây side effect.
20. **Tại sao pipeline deploy không nhất thiết cần quyền đọc secret runtime?** Pipeline có thể ghi reference; Function identity được cấp quyền lấy secret lúc chạy.
21. **Có nên dùng account key thay managed identity chỉ vì SDK lần đầu báo 403 không?** Không. Cần kiểm tra principal, quyền và network trước.
22. **Phải làm gì nếu token vô tình bị ghi vào Git?** Thu hồi/xoay token, xử lý lịch sử/lộ dữ liệu và sửa quy trình ngăn tái diễn.
23. **Managed identity có thay thế Key Vault với API key bên thứ ba không?** Không nếu bên thứ ba không chấp nhận Entra; vẫn cần quản lý key.
24. **Thế nào là một Function được cấu hình production an toàn?** Cấu hình phân tách, quyền tối thiểu, secret quản lý đúng, network bảo vệ, triggers được kiểm chứng, logs không lộ dữ liệu và có rollback/rotation plan.

## 20. Tài liệu tham khảo

- [Azure Functions documentation](https://learn.microsoft.com/azure/azure-functions/) — tổng quan serverless, hosting và quản lý Function Apps.
- [App settings reference for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-app-settings) — những setting runtime và cấu hình đặc biệt.
- [Develop and test Azure Functions locally](https://learn.microsoft.com/azure/azure-functions/functions-develop-local) — local.settings.json và Core Tools.
- [Use managed identities with Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-identity-based-connections-tutorial) — thực hành identity-based access.
- [Identity-based connections in Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference#configure-an-identity-based-connection) — prefix connection settings và extension compatibility.
- [App Service Key Vault references](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references) — reference syntax, identity, cache và networking.
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview) — system-assigned và user-assigned.
- [Azure Key Vault RBAC](https://learn.microsoft.com/azure/key-vault/general/rbac-guide) — role và permission model.
- [Authenticate Python apps to Azure services](https://learn.microsoft.com/azure/developer/python/sdk/authentication/overview) — Azure Identity và DefaultAzureCredential.
- [Azure Storage Blob authorization with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory) — data-plane roles và token authentication.
- [Azure Functions networking options](https://learn.microsoft.com/azure/azure-functions/functions-networking-options) — VNet integration, private endpoint và plan limitations.
- [Azure Functions monitoring](https://learn.microsoft.com/azure/azure-functions/functions-monitoring) — Application Insights và diagnostics.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — giám sát ngân sách và chi phí.

**Kết luận:** một Azure Function an toàn không nên phụ thuộc vào account key hoặc mật khẩu được nhúng trong source. Hãy dùng **app settings cho cấu hình**, **Key Vault cho secret cần bảo vệ** và **managed identity + Azure RBAC cho những dịch vụ hỗ trợ Entra ID**. Phân biệt xác thực người gọi với quyền outbound, kiểm tra riêng host storage và trigger bindings, quản lý network/Private DNS và bảo đảm logs không tiết lộ credential. Chỉ coi migration từ connection string sang identity thành công khi Function thực sự khởi động, các triggers xử lý được sự kiện và có bằng chứng kiểm thử/khôi phục trong đúng hosting plan.
