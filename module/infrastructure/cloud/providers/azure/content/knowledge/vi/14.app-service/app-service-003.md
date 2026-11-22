# Cấu hình runtime, biến môi trường và startup command

Một ứng dụng chạy tốt trên laptop nhưng khi triển khai lên **Azure App Service** lại trả về HTTP 500, 502 hoặc màn hình "Application Error". Nguyên nhân đôi khi không phải do mã nguồn: ứng dụng có thể đang chạy sai phiên bản Node.js/Python/.NET/Java, không tìm thấy biến môi trường, cố kết nối vào cổng không phù hợp, hoặc thực thi một **startup command** trỏ tới tệp không tồn tại. Vì App Service quản lý hệ điều hành và nhiều thành phần hạ tầng, việc nắm rõ ranh giới giữa **cấu hình nền tảng** và **cấu hình ứng dụng** là kỹ năng vận hành thiết yếu.

Bài học thuộc chương **Ứng dụng web với App Service** trong module **CLOUD_PROVIDERS_AZURE**. Module tìm hiểu hệ sinh thái Microsoft Azure từ subscription, resource group, Entra ID đến mạng ảo, tính toán, lưu trữ, dữ liệu, rồi triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng. Trong đó, App Service giúp vận hành web/API theo mô hình PaaS: bạn tập trung vào mã ứng dụng và cấu hình, còn nền tảng quản lý nhiều tác vụ như cung cấp host, tích hợp triển khai và vận hành instance.

Sau bài học, bạn có thể:

- Phân biệt **App Service Plan**, **Web App**, **runtime stack**, **application settings** và **startup command**.
- Chọn đúng runtime, phiên bản, hệ điều hành và mô hình code-based hoặc custom container.
- Dùng biến môi trường để cấu hình ứng dụng theo môi trường mà không hard-code giá trị.
- Tích hợp **managed identity** và **Key Vault references** để không đưa mật khẩu vào source code.
- Hiểu startup mặc định và khi nào cần đặt lệnh khởi động riêng cho Node.js, Python và các runtime khác.
- Cấu hình qua Azure Portal/Azure CLI, kiểm tra kết quả, triển khai qua slot và khắc phục lỗi startup.
- Thiết kế kiểm tra health, log, bảo mật, rollback và kiểm soát chi phí khi thay đổi cấu hình.

## 1. App Service chạy ứng dụng như thế nào?

**Azure App Service** là dịch vụ hosting quản lý cho web application, API và các kịch bản ứng dụng được hỗ trợ. Có hai tài nguyên cần phân biệt:

| Thành phần | Quyết định chính | Ví dụ |
|---|---|---|
| **App Service Plan** | Region, hệ điều hành, kích thước/công suất compute, tier, khả năng scale và nhiều tính năng hạ tầng | Linux plan, SKU Basic |
| **Web App (App Service app)** | Ứng dụng cụ thể, hostname, runtime stack, cấu hình, deployment, identity, slot, networking | api-orders-prod |

Nhiều Web App có thể dùng chung một App Service Plan khi đáp ứng điều kiện của nền tảng; khi đó chúng **chia sẻ năng lực compute và phạm vi chi phí plan**. Thay đổi cấu hình runtime của một Web App không đồng nghĩa thay đổi kích thước plan.

~~~text
Azure subscription
└── Resource group
    ├── App Service Plan (Linux / compute capacity)
    │   ├── Web App: orders-api
    │   │   ├── Runtime: Node.js (ví dụ)
    │   │   ├── App settings: APP_ENV, LOG_LEVEL, ...
    │   │   ├── Startup command: npm start
    │   │   └── Managed identity / Networking
    │   └── Web App: catalog-api
    │       └── Cấu hình độc lập
    └── Key Vault / Database / Application Insights
~~~

**Runtime stack** là môi trường thực thi mã ứng dụng: Node.js, Python, .NET, Java, PHP hoặc lựa chọn được App Service hỗ trợ cho OS/tier tương ứng. **Application settings** là các cặp tên/giá trị được nền tảng cung cấp cho tiến trình; **startup command** xác định cách khởi chạy ứng dụng khi cơ chế mặc định không đủ.

Một ứng dụng thực sự phục vụ request cần đủ cả bốn yếu tố: **đúng artifact đã deploy → đúng runtime và lệnh chạy → đúng cấu hình phụ thuộc → lắng nghe HTTP ở địa chỉ/cổng nền tảng yêu cầu**.

## 2. Chọn mô hình triển khai: built-in runtime hay custom container

App Service có các mô hình thường gặp:

| Mô hình | Bạn đóng gói | Cách runtime được chọn | Khi phù hợp |
|---|---|---|---|
| **Code-based App Service** | Source code hoặc build artifact theo ngôn ngữ | Chọn built-in runtime stack và phiên bản được hỗ trợ | Ứng dụng dùng runtime phổ biến, muốn ít quản trị container |
| **Custom Linux container** | Container image và cấu hình image registry | Runtime nằm trong image; App Service quản lý việc chạy container | Cần thư viện hệ thống, runtime/entrypoint hoặc đóng gói đặc thù |
| **Windows App Service** | Artifact tương thích Windows/IIS/runtime hỗ trợ | Chọn Windows stack; hành vi startup khác Linux | Ứng dụng .NET/ASP.NET hoặc yêu cầu Windows phù hợp |

Với **code-based Linux**, App Service chọn image nền/runtime tương ứng phiên bản, sau đó khởi động ứng dụng qua cơ chế mặc định hoặc lệnh bạn cấu hình. Với **custom container**, phiên bản Node/Python/Java nằm trong **Docker image**; thay trường runtime stack kiểu code-based không phải cách nâng runtime bên trong image.

### Chọn hệ điều hành trước khi chọn phiên bản

- Xác nhận ứng dụng có phụ thuộc Linux hay Windows (native library, IIS, lệnh shell, đường dẫn, filesystem case sensitivity).
- Đối chiếu phiên bản framework, runtime và mức hỗ trợ trên Azure App Service tại thời điểm triển khai.
- Xem tính năng/tier cần dùng, ví dụ deployment slots, Always On, VNet Integration và scale.
- Xác định region, ngân sách, tuân thủ và khả năng chạy thử trên một slot hoặc môi trường staging.
- Tách **runtime version** khỏi **SDK/build tool version**: compile thành công chưa chứng minh artifact tương thích runtime đang chạy.

Không mặc định tất cả ngôn ngữ và phiên bản đều được hỗ trợ trên mọi OS. Danh sách thay đổi theo vòng đời dịch vụ; hãy lấy runtime hiện khả dụng bằng Portal hoặc CLI thay vì sao chép một ví dụ cũ.

## 3. Hiểu runtime stack và version

Trong App Service Linux code-based, thông tin runtime thường nằm ở cấu hình **linuxFxVersion**. Ví dụ minh họa:

~~~text
NODE|22-lts
PYTHON|3.11
DOTNETCORE|8.0
~~~

Các giá trị chỉ **minh họa định dạng**, không phải danh sách đảm bảo luôn được mở cho app/region của bạn. Hãy chọn đúng chuỗi runtime do lệnh liệt kê hoặc Portal trả về. Trên Windows, trường điều khiển stack/version có thể khác, và một số runtime gắn với cách hosting riêng.

### Vì sao phiên bản runtime quan trọng?

Một ứng dụng Node.js dùng API chỉ có ở bản Node mới có thể bị lỗi khi App Service chạy phiên bản cũ. Ứng dụng Python có dependency chỉ hỗ trợ một dải phiên bản có thể build lỗi hoặc không import được. Một ứng dụng .NET build cho runtime cao hơn runtime được host cung cấp cũng có thể không khởi động.

Hãy kiểm soát tính tương thích ở ba nơi:

1. **Source/dependency manifest:** package.json, requirements.txt/pyproject.toml, csproj hoặc công cụ tương đương.
2. **Build pipeline:** phiên bản SDK và cách tạo artifact.
3. **App Service runtime:** phiên bản tiến trình chạy thực tế.

Lý tưởng, CI và môi trường staging dùng cùng nền tảng và phiên bản dự kiến của production. Khi nâng runtime, kiểm thử **khởi động, kết nối dữ liệu, health, chức năng nghiệp vụ và observability** trước khi chuyển traffic.

## 4. Cấu hình runtime bằng Azure Portal

Với một **Web App code-based** đã tạo:

1. Mở [Azure Portal](https://portal.azure.com/), chọn subscription và resource group đúng.
2. Mở Web App, ghi nhận **App Service Plan**, **Operating System** và trạng thái app.
3. Vào **Configuration** hoặc **Settings > Configuration / General settings** tùy giao diện.
4. Xác định mục **Stack settings** (runtime stack/version) nếu ứng dụng hỗ trợ chỉnh trong Portal.
5. Chọn phiên bản runtime được hỗ trợ cho ngôn ngữ và OS; kiểm tra tính tương thích ứng dụng.
6. Lưu thay đổi và theo dõi quá trình restart/recycle của tiến trình ứng dụng.
7. Kiểm tra log, endpoint health và các luồng nghiệp vụ quan trọng.

Không đổi production runtime trực tiếp để "thử xem có hết lỗi" nếu chưa biết artifact và dependency tương thích. Với hệ thống quan trọng, dùng **deployment slot** hoặc môi trường staging và kế hoạch rollback.

### Khi không thấy runtime stack mong muốn

Có thể bạn đã tạo **custom container**, chọn OS không phù hợp, chọn một stack đã thay đổi hỗ trợ, hoặc app bị hạn chế bởi chính sách/tier. Hãy kiểm tra loại Web App và danh sách runtime được Azure công bố trước khi quyết định tạo mới tài nguyên.

## 5. Kiểm tra và thay runtime bằng Azure CLI

Các lệnh dùng **Bash** trong Azure Cloud Shell hoặc terminal Bash cài Azure CLI. Hãy đăng nhập, chọn subscription và xem runtime có thể dùng:

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az webapp list-runtimes --os-type linux --output table
~~~

Liệt kê Windows runtime nếu cần đối chiếu:

~~~bash
az webapp list-runtimes --os-type windows --output table
~~~

Với một app Linux code-based đã tồn tại:

~~~bash
RG="<RESOURCE_GROUP>"
APP="<WEB_APP_NAME>"

az webapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,kind:kind,state:state,host:defaultHostName}" \
  --output json

az webapp config show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{runtime:linuxFxVersion,startup:appCommandLine,alwaysOn:alwaysOn}" \
  --output json
~~~

Sau khi chọn chuỗi hợp lệ từ danh sách runtime, mới cập nhật:

~~~bash
RUNTIME="<SUPPORTED_LINUX_RUNTIME_VALUE>"

az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --linux-fx-version "$RUNTIME"
~~~

Ví dụ, **SUPPORTED_LINUX_RUNTIME_VALUE** có thể có dạng **NODE|22-lts** nếu được app, vùng và nền tảng hỗ trợ. Cấu hình sai có thể làm ứng dụng không boot. **Không dùng lệnh cập nhật linuxFxVersion này để thay phiên bản runtime trong custom container image**.

Lệnh **show/list-runtimes** chỉ cho biết cấu hình hoặc các lựa chọn được nền tảng công bố; chúng không chứng minh phiên bản dependency đã deploy tương thích. Khi thay runtime, cần đo kết quả request thật và kiểm tra log.

## 6. Application settings chính là biến môi trường

Trong Azure App Service, **Application settings (App settings)** là các cặp **name=value** được quản lý ở cấp Web App/slot. Với những mô hình App Service phổ biến, các giá trị này được cung cấp cho tiến trình ứng dụng như **environment variables** lúc khởi chạy.

Ví dụ:

| Setting name | Giá trị ví dụ | Cách ứng dụng dùng |
|---|---|---|
| **APP_ENV** | production | Chọn cấu hình nghiệp vụ ứng dụng |
| **LOG_LEVEL** | info | Điều chỉnh log verbosity |
| **FEATURE_EXPORT_ENABLED** | false | Bật/tắt tính năng đã được code hỗ trợ |
| **API_BASE_URL** | https://api.example.test | Địa chỉ dịch vụ phụ thuộc |
| **DB_HOST** | db.example.internal | Tên host database được phép kết nối |

**APP_ENV** và **FEATURE_EXPORT_ENABLED** chỉ là biến do ứng dụng bạn tự đặt. Azure không tự hiểu mọi custom setting. Chỉ những setting mà code hoặc nền tảng sử dụng mới có tác dụng.

### Cách đọc biến theo runtime

**Node.js:**

~~~javascript
const logLevel = process.env.LOG_LEVEL ?? "info";
const isProduction = process.env.APP_ENV === "production";
~~~

**Python:**

~~~python
import os

log_level = os.environ.get("LOG_LEVEL", "info")
is_production = os.environ.get("APP_ENV") == "production"
~~~

**.NET:**

~~~csharp
var logLevel = Environment.GetEnvironmentVariable("LOG_LEVEL") ?? "info";
~~~

**Java:**

~~~java
String logLevel = System.getenv().getOrDefault("LOG_LEVEL", "info");
~~~

Trong .NET, ASP.NET Core còn có cơ chế configuration providers, và App Service settings thường được đưa vào qua provider môi trường. Cách ánh xạ khóa phân cấp (ví dụ dấu **__**) phụ thuộc framework và thứ tự nguồn cấu hình. Không mặc định mọi framework đọc app settings giống hệt nhau.

### Các điểm cần nhớ

- App settings của App Service thường **ghi đè hoặc được ưu tiên** hơn cấu hình tương ứng trong một số file của ứng dụng, tùy cách framework áp dụng precedence.
- Thay đổi App settings thường **kích hoạt restart/recycle** ứng dụng để tiến trình nhận giá trị mới; chuẩn bị tác động với production.
- Trên Windows, tên biến môi trường có thể được xử lý không phân biệt hoa/thường; trên Linux, **LOG_LEVEL** và **log_level** là hai tên khác nhau.
- Dữ liệu môi trường chỉ là chuỗi. Code phải parse boolean, integer hoặc JSON có validation rõ ràng.
- Không dùng tên tùy ý đè các biến do Azure hoặc runtime quản lý như một nhóm **WEBSITE_***, **WEBSITES_*** hoặc **PORT** nếu chưa hiểu vai trò và tài liệu của chúng.
- Một file **.env** trong source code không được Azure tự động xử lý giống nhau ở mọi framework. Quản lý cấu hình production qua App Service, managed identity và secret store phù hợp.

## 7. Cấu hình App settings bằng Portal và CLI

### Trên Portal

1. Mở Web App → **Environment variables** hoặc **Configuration > Application settings** tùy giao diện.
2. Chọn thêm setting, ví dụ **LOG_LEVEL=info**.
3. Xác định đây có phải **deployment slot setting** cần giữ riêng theo slot không.
4. Lưu, xem cảnh báo restart và kiểm tra hoạt động của app sau thay đổi.
5. Theo dõi Log stream, health và metric HTTP.

### Trên CLI

~~~bash
RG="<RESOURCE_GROUP>"
APP="<WEB_APP_NAME>"

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings APP_ENV=production LOG_LEVEL=info FEATURE_EXPORT_ENABLED=false
~~~

Chỉ liệt kê **tên** setting để tránh vô tình in giá trị nhạy cảm:

~~~bash
az webapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].{name:name,slotSetting:slotSetting}" \
  --output table
~~~

Lệnh sau **xóa** một setting của ứng dụng; chỉ chạy nếu bạn biết code không còn cần:

~~~bash
az webapp config appsettings delete \
  --resource-group "$RG" \
  --name "$APP" \
  --setting-names FEATURE_EXPORT_ENABLED
~~~

Không đưa mật khẩu hoặc connection string thật vào đối số **--settings SECRET=value** trong terminal dùng chung: chúng có thể bị lưu trong shell history, pipeline logs hoặc command tracing. Sử dụng Key Vault reference hoặc cách xử lý secret được tổ chức phê duyệt.

### Connection strings có gì khác?

Portal còn có nhóm **Connection strings**, cho phép lưu cấu hình kết nối theo loại kết nối và cung cấp chúng tới runtime theo cách phù hợp với nền tảng. Trên một số stack Windows/.NET, chúng có cơ chế prefix hoặc tích hợp framework riêng. Với các ứng dụng hiện đại, **App settings + Key Vault references** thường tạo mẫu cấu hình thống nhất và dễ quản lý hơn; lựa chọn tùy framework và yêu cầu hiện có.

Đừng giả định mọi connection string tự tạo trong Portal đều được ứng dụng nhận dưới đúng tên biến bạn nhập. Hãy kiểm tra cách ánh xạ của runtime và phương thức cấu hình client SDK đang dùng.

## 8. Bảo vệ secret bằng Managed Identity và Key Vault references

Mật khẩu database, API key hoặc token truy cập không nên commit vào repository, ghi trực tiếp trong Dockerfile hoặc để lộ trong deployment pipeline. App Service hỗ trợ **managed identity** và **Azure Key Vault references** để app dùng bí mật theo cách được quản lý.

### Luồng khái niệm

~~~text
Web App
  |
  +-- Managed identity (Entra ID)
  |        |
  |        v
  |   Key Vault (secret được cấp quyền đọc)
  |        |
  +-- App setting:
       DB_PASSWORD = @Microsoft.KeyVault(SecretUri=...)
           |
           v
     App Service resolve secret
           |
           v
     Tiến trình ứng dụng đọc DB_PASSWORD
~~~

Ứng dụng vẫn đọc biến **DB_PASSWORD** theo cách thông thường, nhưng trong cấu hình App Service bạn lưu một **tham chiếu Key Vault**, không sao chép giá trị secret vào cấu hình triển khai.

Ví dụ cú pháp tham chiếu:

~~~text
@Microsoft.KeyVault(SecretUri=https://<VAULT_NAME>.vault.azure.net/secrets/<SECRET_NAME>/)
~~~

Đây là mẫu minh họa, thay bằng vault và secret thật trong môi trường được quản trị. Có thể dùng secret version cụ thể khi cần pin phiên bản; bỏ version theo khả năng hỗ trợ để lấy phiên bản hiện hành qua cơ chế refresh/cache của nền tảng.

### Các bước chuẩn bị

1. Bật **system-assigned** hoặc cấu hình **user-assigned managed identity** cho Web App tùy thiết kế.
2. Trong Key Vault, cấp quyền **đọc secret** đúng identity: ví dụ role **Key Vault Secrets User** khi vault dùng Azure RBAC, hoặc access policy **Get** khi vault dùng chế độ access policy phù hợp.
3. Nếu Key Vault chỉ cho mạng riêng, cấu hình App Service VNet integration, private endpoint, DNS/route và cơ chế truy cập vault được hỗ trợ.
4. Tạo App setting chứa reference, không chứa plaintext password.
5. Kiểm tra **Key Vault reference status** trong Portal và xác minh ứng dụng kết nối thành công.
6. Thiết kế rotation và refresh, không giả định secret mới được ứng dụng nhận tức thời trong mọi trường hợp.

Ví dụ CLI bật system-assigned identity:

~~~bash
az webapp identity assign \
  --resource-group "$RG" \
  --name "$APP"
~~~

Một ví dụ đặt reference thay vì secret trực tiếp:

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings 'DB_PASSWORD=@Microsoft.KeyVault(SecretUri=https://<VAULT_NAME>.vault.azure.net/secrets/<SECRET_NAME>/)'
~~~

Cú pháp sử dụng **nháy đơn trong Bash** nhằm không cho shell biến đổi chuỗi. Thay placeholder; kiểm tra subscription, quyền Key Vault và nguồn secret. Lệnh trên **không tự cấp quyền đọc Key Vault** và không tự tạo secret.

### Những lỗi thường gặp với Key Vault reference

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Ứng dụng thấy chuỗi **@Microsoft.KeyVault(...)** thay vì secret | Reference chưa resolve thành công | Kiểm tra syntax, identity, vault permissions, trạng thái reference |
| Lỗi 403 tới Key Vault | Managed identity chưa được cấp quyền hoặc sai principal | Kiểm tra RBAC/access policy, identity Web App |
| Timeout khi lấy secret | Private Endpoint, DNS, VNet integration, firewall hoặc route | Kiểm tra network path và name resolution |
| Vừa rotate secret nhưng app vẫn dùng giá trị cũ | Cache/refresh của nền tảng hoặc ứng dụng | Kiểm tra refresh, restart/setting change phù hợp và cache trong app |

**Key Vault references có cơ chế cache/refresh**, và thay đổi cấu hình app có thể kích hoạt làm mới. Không coi secret rotation là thành công cho đến khi kiểm tra phiên bản/value thực tế **mà không in secret vào log** và xác minh chức năng kết nối.

## 9. Startup command là gì?

Sau khi nhận artifact và chuẩn bị runtime, App Service cần biết **tiến trình nào sẽ phục vụ HTTP request**. Một số runtime nhận diện dự án và chạy lệnh mặc định; với ứng dụng đặc thù, bạn phải đặt **Startup Command** (trên nhiều Linux Web App được biểu diễn bởi **appCommandLine**).

Ví dụ:

~~~text
App Service Linux code-based
    |
    +-- Runtime stack: Python
    +-- Deployment artifact: source + dependencies
    +-- Startup command: gunicorn --bind=0.0.0.0:8000 app:app
    |
    v
Tiến trình gunicorn chạy, bind cổng được nền tảng định tuyến
    |
    v
Health checks / HTTP requests
~~~

**Startup command không phải build command.** Lệnh **npm install**, **pip install**, **dotnet publish** hoặc công đoạn biên dịch thuộc quá trình build/deploy; thông thường không nên thực hiện lại toàn bộ build mỗi lần container/instance khởi động.

### Các thành phần cần đúng

1. **Executable tồn tại:** node, npm, gunicorn, java, hoặc executable của ứng dụng.
2. **Working directory đúng:** tệp bạn gọi thực sự nằm trong package/deployment path.
3. **Dependency đã cài:** node_modules, Python packages, framework runtime phù hợp.
4. **Lắng nghe đúng network interface và port:** thường là **0.0.0.0**, không chỉ **127.0.0.1** trong các mô hình container/network cần nhận request từ platform.
5. **Process sống liên tục:** không được chạy xong rồi thoát nếu nó là tiến trình phục vụ web.
6. **Log ra stdout/stderr** khi phù hợp, để Azure có thể giúp điều tra lỗi.
7. **Shutdown/restart:** ứng dụng xử lý termination signal và ngắt kết nối một cách an toàn nếu framework hỗ trợ.

Một startup command sai có thể làm App Service vẫn hiển thị site resource ở trạng thái Running nhưng ứng dụng không sẵn sàng nhận request.

## 10. Startup mặc định và ứng dụng Node.js

Với Node.js code-based trên Linux, App Service có cơ chế phát hiện cách khởi động ứng dụng và có thể dựa vào **package.json/start script** hoặc lệnh được cấu hình theo khả năng runtime. Không nên giả định một file TypeScript được chạy trực tiếp nếu bạn chưa build nó thành JavaScript.

Ví dụ ứng dụng HTTP tối giản:

~~~javascript
// server.js
const http = require("http");

const port = Number(process.env.PORT || 8080);
const host = "0.0.0.0";
const env = process.env.APP_ENV || "development";

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }

  res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
  res.end("App running in " + env);
});

server.listen(port, host, () => {
  console.log("HTTP server listening on " + host + ":" + port);
});
~~~

Một **package.json** hợp lệ có script khởi động:

~~~json
{
  "name": "app-service-runtime-demo",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "start": "node server.js"
  }
}
~~~

Nếu cần startup command tường minh:

~~~text
npm start
~~~

Ứng dụng dùng **process.env.PORT** khi nền tảng cung cấp port, có giá trị dự phòng để chạy local, và bind vào **0.0.0.0**. Với ứng dụng/framework thực tế, kiểm tra xem App Service sử dụng port nào cho stack đang chọn thay vì cố định một cổng theo giả định.

### Lỗi Node.js thường gặp

| Lỗi | Nguyên nhân | Kiểm tra |
|---|---|---|
| **Cannot find module** | Dependency thiếu hoặc build output chưa tồn tại | Artifact, npm install/build logs, package.json |
| **npm ERR! Missing script: start** | Không có script start nhưng startup gọi npm start | Thêm script hợp lệ hoặc đặt command đúng |
| **EADDRINUSE** | Hai tiến trình cùng lắng nghe một port | Kiểm tra startup tạo process trùng |
| Ứng dụng chỉ bind **127.0.0.1** | Platform không kết nối được tới process theo topology | Bind host/port được hướng dẫn |
| Khởi động được local nhưng thiếu config ở Azure | APP_ENV hoặc các biến khác chưa được cấp | Kiểm tra app settings và tên chính xác |

## 11. Startup command cho Python và các framework WSGI/ASGI

Trên Python App Service Linux code-based, nền tảng có khả năng nhận diện một số dự án phổ biến và chạy server phù hợp. Nhưng không phải mọi cấu trúc repository đều được tự nhận diện chính xác.

Ví dụ dự án Flask:

~~~text
app.py
requirements.txt
~~~

**app.py:**

~~~python
from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify(status="ok", app_env=os.getenv("APP_ENV", "development"))
~~~

**requirements.txt:**

~~~text
Flask
gunicorn
~~~

Startup command ví dụ:

~~~bash
gunicorn --bind=0.0.0.0:8000 --timeout 600 app:app
~~~

Trong **app:app**, phần đầu là Python module **app.py**, phần sau là đối tượng Flask **app**. Nếu repository của bạn nằm ở subfolder, đổi module path/working directory tương ứng. Lệnh này chỉ hợp lệ khi **gunicorn đã được cài** trong môi trường app và build đã mang đủ dependency.

### Django

Django thường dùng WSGI entrypoint dạng:

~~~text
gunicorn --bind=0.0.0.0:8000 myproject.wsgi:application
~~~

Thay **myproject** bằng tên package Django thật. Cần cấu hình **ALLOWED_HOSTS**, static files, database migrations và các setting theo framework. Một ứng dụng chạy bằng development server **manage.py runserver** không phải lựa chọn production chuẩn chỉ vì nó chạy thành công trên laptop.

### ASGI (FastAPI, Django ASGI)

ASGI cần server/worker hỗ trợ ASGI phù hợp, chẳng hạn Uvicorn/Gunicorn cấu hình đúng phiên bản. Không dùng lệnh WSGI **app:app** ở trên một cách máy móc cho mọi ứng dụng FastAPI. Hãy kiểm tra tài liệu framework và phiên bản server cụ thể.

### Lỗi Python thường gặp

- **ModuleNotFoundError:** dependency chưa được cài trong môi trường deploy, hoặc module path sai.
- **gunicorn: command not found:** gunicorn không có trong dependencies hoặc môi trường không được build đúng.
- **Error loading ASGI/WSGI app:** sai module path, tên đối tượng app hoặc exception import-time.
- **Migrations thiếu:** chương trình boot nhưng query database lỗi; cần quy trình migration tách khỏi request serving.
- **Static files không hiển thị:** thiếu bước collect/build hoặc cấu hình static serving phù hợp.

Với Python, nên phân biệt rõ **Oryx/build automation** với **startup command**. Cài dependency lúc deployment thay vì cố cài mỗi khi instance khởi động.

## 12. .NET, Java và khác biệt Linux/Windows

### .NET

Ứng dụng ASP.NET Core trên App Service có thể dùng runtime tích hợp khi đúng target framework. Trên Windows, phần hosting thường gắn với **IIS/ASP.NET Core Module** tùy mô hình; trên Linux, ứng dụng chạy trong môi trường Linux của runtime stack. Cách khởi động không giống nhau giữa hai OS.

Đối với .NET, thường **không cần startup command thủ công** nếu publish artifact theo cách nền tảng yêu cầu và runtime tương thích. Trước khi tự thêm **dotnet MyApp.dll**, hãy kiểm tra loại deployment, working directory, publish output và tài liệu App Service tương ứng.

### Java

App Service hỗ trợ một số mô hình Java như **Java SE** và **Tomcat** theo stack được cung cấp. Một JAR tự chạy (ví dụ Spring Boot) không có cấu trúc deploy giống một WAR cho Tomcat. Chọn đúng runtime/Java version và phương thức deployment; không trộn lệnh **java -jar** với Tomcat WAR nếu không có lý do kiến trúc.

Một số framework dùng environment variables như **SPRING_PROFILES_ACTIVE** hoặc **JAVA_TOOL_OPTIONS**, nhưng việc đặt biến phải dựa trên nhu cầu ứng dụng và hướng dẫn runtime; không đưa tùy chọn JVM quá mức nếu chưa đo memory/performance.

### Windows vs Linux

| Chủ đề | App Service Linux | App Service Windows |
|---|---|---|
| Startup command | Có cấu hình Startup Command cho nhiều built-in stack | Thường dựa hosting theo Windows/IIS hoặc entrypoint phù hợp |
| Shell/script | Bash/sh và đường dẫn Unix | PowerShell/cmd, Windows paths tùy mô hình |
| Case sensitivity | File và biến môi trường thường phân biệt hoa/thường | Hành vi khác tùy hệ thống/framework |
| Runtime setting | Thường dùng linuxFxVersion cho code-based stack | Cấu hình stack/version riêng của Windows |
| Custom container | Docker image Linux | Cần xem mô hình Windows Container và khả năng hỗ trợ hiện hành |

Đừng sao chép startup command Linux có dấu **/**, lệnh **bash**, hoặc module WSGI vào Web App Windows rồi kết luận App Service hỏng. Với Windows, điều tra web.config, IIS/module hosting và deployment artifact theo stack được chọn.

## 13. Thiết lập startup command bằng Portal và CLI

### Portal

1. Mở Web App Linux code-based.
2. Chọn **Configuration/General settings** hoặc trang cấu hình startup tương ứng.
3. Nhập **Startup Command** nếu cơ chế mặc định không nhận diện được entrypoint.
4. Lưu, quan sát restart, xem Log stream và kiểm tra endpoint health.

### CLI

~~~bash
az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --startup-file "npm start"
~~~

Với một Python Flask app có **app.py** đúng vị trí và dependency gunicorn đã cài:

~~~bash
az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --startup-file "gunicorn --bind=0.0.0.0:8000 app:app"
~~~

**Không chạy cả hai lệnh trên cho cùng một ứng dụng**: chúng là hai ví dụ độc lập cho hai runtime khác nhau. Mỗi lần set là thay đổi cấu hình có thể gây restart; chỉ áp dụng lệnh đúng cho app được giao.

Kiểm tra lệnh hiện tại:

~~~bash
az webapp config show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{startup:appCommandLine,runtime:linuxFxVersion}" \
  --output json
~~~

**Startup file/script:** nếu dùng một file như **startup.sh**, đảm bảo file được deploy, có đường dẫn và quyền phù hợp. Không tin rằng script sẽ tồn tại ở **/home/site/wwwroot** nếu pipeline deploy thực tế đặt artifact ở nơi khác hoặc sử dụng package mount read-only. Cách đặt/execute startup script phụ thuộc deployment mode.

## 14. Cổng HTTP và địa chỉ bind: built-in runtime khác custom container

Ứng dụng có thể chạy tiến trình nhưng không trả request nếu sai cổng. Đây là một trong các lỗi phổ biến nhất khi deploy App Service.

### Built-in Linux runtime

Với built-in stack, nền tảng thường cung cấp cấu hình port/startup tương ứng với runtime. Code cần dùng port được môi trường cung cấp hoặc lệnh server được tài liệu runtime hướng dẫn. Ví dụ Node.js thường đọc **process.env.PORT**; ví dụ Python Gunicorn trong tài liệu App Service Linux thường bind vào **0.0.0.0:8000**.

Không coi **8000** hoặc **8080** là cổng cố định cho mọi Web App: framework, stack và cơ chế launch có thể khác nhau.

### Custom Linux container

Với custom container, ứng dụng phải lắng nghe trên cổng mà App Service định tuyến traffic tới. App Service hỗ trợ setting **WEBSITES_PORT** để chỉ định **cổng container của ứng dụng** trong những cấu hình được hỗ trợ (thường mặc định nền tảng dựa trên cổng 80 khi không được chỉ định).

Ví dụ container chạy app trên cổng 8080:

~~~dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE 8080
CMD ["node", "server.js"]
~~~

App Service setting tương ứng:

~~~text
WEBSITES_PORT=8080
~~~

Trong container, process phải **thực sự lắng nghe 0.0.0.0:8080**. Dockerfile **EXPOSE 8080** chỉ khai báo ý định cổng; nó không tự làm tiến trình bind đúng cổng. **WEBSITES_PORT** dùng để App Service định tuyến tới cổng container, không nhất thiết được tự động truyền thành environment variable **PORT** bên trong image; nếu code đọc PORT, bạn phải đồng bộ cấu hình runtime trong image.

**Không dùng WEBSITES_PORT như nút sửa mọi lỗi** của built-in runtime. Khi không chắc cổng, xem container/startup logs và tài liệu đúng loại Web App.

### App phải lắng nghe trên 0.0.0.0 khi cần

~~~text
Chỉ listen 127.0.0.1:8080
  -> request từ reverse proxy/container networking có thể không đến được

Listen 0.0.0.0:8080
  -> process nhận request trên interface theo cấu hình môi trường
~~~

Vẫn phải đặt các lớp bảo mật ở App Service/network/identity; bind **0.0.0.0** bên trong container không có nghĩa bạn muốn mở API công khai mà không xác thực.

## 15. Build, deployment và startup là ba giai đoạn riêng

Khi một Web App không chạy, hãy xác định **lỗi xảy ra ở giai đoạn nào**:

| Giai đoạn | Thao tác | Dấu hiệu lỗi |
|---|---|---|
| **Build** | Cài dependency, compile, tạo static assets, chạy kiểm tra | npm/pip/dotnet build thất bại, package không tương thích |
| **Deployment** | Đưa artifact/image vào App Service, mount/package, cập nhật cấu hình | Sai ZIP path, thiếu file, container pull thất bại |
| **Startup** | Chọn runtime, chạy entrypoint, bind port, khởi tạo service | ModuleNotFoundError, thiếu secret, process thoát, ping timeout |
| **Runtime** | Xử lý HTTP requests và truy cập phụ thuộc | HTTP 5xx, timeout DB, lỗi xác thực, memory pressure |

### Oryx và remote build trên Linux

Một số code-based Linux stacks sử dụng **Oryx** để phát hiện ngôn ngữ, cài dependency và tạo lệnh startup theo cấu hình triển khai. Tuy nhiên không phải mọi deployment đều tự kích hoạt remote build. Các setting như **SCM_DO_BUILD_DURING_DEPLOYMENT** hoặc cơ chế build liên quan chỉ nên bật khi phù hợp với deployment method và hướng dẫn runtime.

Nếu bạn deploy artifact đã build sẵn, đừng mặc định App Service sẽ chạy lại **npm install** hoặc **pip install**. Nếu deploy source code, đừng mặc định dependency đã tồn tại trong container trước khi pipeline build chạy.

### Run from package

Một số phương thức triển khai sử dụng **WEBSITE_RUN_FROM_PACKAGE** để mount package, thường làm **wwwroot read-only** theo mô hình hỗ trợ. Không đặt startup script tự ghi file build hoặc cài package trực tiếp vào thư mục ứng dụng read-only.

Tách dữ liệu tạm và dữ liệu cần lưu bền vững khỏi source folder; với nội dung người dùng upload, ưu tiên Blob Storage hoặc dịch vụ lưu trữ được quản lý phù hợp. Không dựa vào local filesystem của App Service như một database dùng chung giữa nhiều instance.

## 16. Deployment slots và slot settings

**Deployment slots** giúp thử một bản ứng dụng trong URL/slot riêng trước khi chuyển traffic. Chúng có cấu hình và cơ chế swap riêng theo tier hỗ trợ.

Ví dụ:

~~~text
Web App: orders-api
  |
  +-- production slot
  |      APP_ENV=production
  |      DB_ENDPOINT=database-production
  |
  +-- staging slot
         APP_ENV=staging
         DB_ENDPOINT=database-staging
~~~

Mục tiêu là staging có thể thử phiên bản mới mà **không vô tình ghi vào database production**. Vì vậy, những cấu hình nhạy với môi trường như DB endpoint, secret tham chiếu, callback URL hoặc một số feature flags thường nên là **deployment slot settings (sticky)** nếu mô hình swap yêu cầu.

### Sticky settings là gì?

Các setting được đánh dấu **deployment slot setting** giữ nguyên ở slot liên quan khi thực hiện swap theo quy tắc App Service. Không phải toàn bộ cấu hình của App Service đều tự swap giống nhau; cần kiểm tra bảng cấu hình nào được swap và bảng nào không.

Ví dụ đặt setting riêng cho staging:

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --slot-settings APP_ENV=staging
~~~

Lệnh này yêu cầu slot **staging** đã tồn tại; **không tự tạo slot**. Slot deployment hỗ trợ theo App Service Plan tier; có chi phí/giới hạn phụ thuộc tier và cùng chia sẻ khả năng compute của plan. Khi dùng slot để thử cấu hình:

1. Đảm bảo setting cần sticky đã được đánh dấu đúng.
2. Tách secret và database staging khỏi production.
3. Kiểm tra startup command/runtime ở slot đích.
4. Chạy smoke tests trước khi swap.
5. Có kế hoạch rollback và quan sát logs/metrics sau swap.

**Swap không thay thế database migration planning**. Nếu phiên bản mới chạy migration không tương thích, swap về artifact cũ chưa chắc phục hồi được dữ liệu.

## 17. Always On, health check và khả năng sẵn sàng

App Service có tùy chọn **Always On** ở những tier được hỗ trợ, giúp giữ ứng dụng hoạt động thay vì dễ bị idle theo cơ chế của tier thấp. Điều này hữu ích cho ứng dụng cần thời gian đáp ứng ổn định, một số tác vụ nền và warm-up.

Tuy nhiên, **Always On không bảo đảm zero downtime**: thay đổi cấu hình, deployment, scale, lỗi runtime hoặc backend phụ thuộc vẫn có thể gây gián đoạn. Tùy chọn này cũng không phải cách thay thế một hệ thống queue/worker đáng tin cậy cho tác vụ dài.

### Health check

Thiết kế endpoint đơn giản:

~~~text
GET /health
200 OK           -> instance/app có thể phục vụ theo tiêu chí đã định
503 Unavailable  -> instance chưa sẵn sàng
~~~

Nếu bật tính năng **Health check** của App Service, cấu hình đường dẫn phù hợp và bảo đảm endpoint có thể được nền tảng gọi theo mô hình của dịch vụ. Endpoint này cần trả phản hồi thành công **khi instance thực sự sẵn sàng**, tránh trả 200 vô điều kiện trong lúc ứng dụng không có kết nối tới thành phần bắt buộc.

Nhưng cũng tránh health check quá sâu: nếu một dịch vụ phụ không quan trọng chập chờn, đừng lập tức làm mọi instance bị đánh dấu unhealthy. Phân biệt **liveness**, **readiness** và tình trạng business dependency.

**Security:** health endpoint không nên để lộ connection string, secret, stack traces hoặc thông tin hệ thống nhạy cảm. Dùng Application Insights/monitoring để thu thập chi tiết qua kênh có kiểm soát.

## 18. Chẩn đoán lỗi startup trong App Service

Một trình tự hiệu quả:

1. **Xác minh Web App resource:** đúng subscription, resource group, OS, plan, trạng thái và deployment slot.
2. **Kiểm tra runtime:** cấu hình stack và phiên bản có khớp artifact/framework không?
3. **Kiểm tra artifact:** file entrypoint, build output và dependencies có tồn tại tại đường dẫn App Service thực sự chạy không?
4. **Kiểm tra startup command:** lệnh đúng, executable/module có tồn tại và bind đúng port không?
5. **Kiểm tra app settings:** tên, định dạng, secret references, slot stickiness và quyền truy cập phụ thuộc.
6. **Xem log:** deployment/build logs, Log stream, app/container startup logs, Application Insights.
7. **Kiểm tra network:** database/Key Vault/DNS/private endpoint/egress/firewall nếu startup phụ thuộc vào chúng.
8. **Thực hiện một thay đổi hẹp**, kiểm tra lại bằng health/smoke test và giữ phương án rollback.

### Bật và đọc log

Trong Portal, vào **Monitoring > App Service logs** hoặc trang logging tương ứng, cấu hình logging phù hợp runtime và chính sách dữ liệu; dùng **Log stream** để xem output. Với Azure CLI:

~~~bash
az webapp log tail \
  --resource-group "$RG" \
  --name "$APP"
~~~

Lệnh trên theo dõi log tương tác; nhấn **Ctrl+C** để dừng. Nếu không có dữ liệu, kiểm tra loại app, logging đã bật chưa, stdout/stderr có được ghi và tính năng log tail có được hỗ trợ trong mô hình deployment không.

Bạn cũng có thể xem **Diagnose and solve problems** trong App Service, deployment logs và công cụ như **Kudu/Advanced Tools hoặc SSH console** tùy OS/loại Web App. Không phải mọi tính năng Kudu/SSH có mặt giống nhau ở custom container, Linux code-based và Windows.

### Ma trận lỗi thông dụng

| Triệu chứng | Nguyên nhân có thể | Hướng xác minh |
|---|---|---|
| Ứng dụng trả **Application Error** sau deploy | Process không khởi động, thoát sớm hoặc exception import-time | Startup/container logs và runtime |
| **ModuleNotFoundError / Cannot find module** | Build/dependency thiếu, sai module path | Manifest, artifact, build logs |
| **gunicorn: command not found** | Dependency không có hoặc build bị bỏ qua | requirements.txt và kết quả deploy |
| **npm start** thất bại | package.json thiếu script start, sai thư mục | package scripts và appCommandLine |
| Container bị **HTTP ping timeout** | Sai port, bind localhost, app boot quá lâu hoặc process exit | Log, WEBSITES_PORT, Docker CMD/ENTRYPOINT |
| **Key Vault reference** không resolve | Identity thiếu quyền, reference sai hoặc mạng không tới vault | Reference status, managed identity, vault permissions |
| App chạy ở staging nhưng production lỗi | Sticky settings/swap, secret hoặc dependency khác nhau | So sánh slot settings không lộ secret |
| HTTP **500** sau startup | Lỗi code hoặc phụ thuộc runtime | App logs, tracing, Application Insights |
| HTTP **502/503** | App không healthy, instance/port/startup/backend vấn đề | Health/instance metrics, platform diagnostics |
| Sau đổi app settings app restart và mất phiên | Recycle theo cấu hình, session lưu trên instance | Shared session hoặc kiến trúc stateless |
| Thay runtime rồi app không boot | Binary/dependency không tương thích phiên bản | Rollback runtime sau khi kiểm tra, thử staging |
| Upload file thất bại hoặc dữ liệu không đồng nhất | Dựa vào filesystem local/read-only hoặc storage path sai | Deployment mode, persistent storage và Blob Storage |

**HTTP status không cho biết nguyên nhân duy nhất.** Ví dụ 503 có thể xảy ra vì app không nhận traffic đúng cổng, instance bị đánh dấu không khỏe hoặc các điều kiện khác. Kết luận cần dựa trên log và trạng thái.

## 19. Bảo mật và quản trị cấu hình

Runtime/app settings là một phần của bề mặt tấn công:

- **Không commit secret** vào Git, package.json, Dockerfile, file cấu hình hoặc README.
- **Hạn chế RBAC**: người có quyền sửa App settings hoặc startup command có thể thay hành vi ứng dụng, thậm chí khiến app đọc/gửi dữ liệu nhạy cảm. Chỉ cấp quyền phù hợp.
- **Dùng managed identity và Key Vault** cho tài nguyên hỗ trợ, thay vì credential dài hạn trong code.
- **Tách environment** (dev/staging/prod) và slot settings, tránh để staging ghi production.
- **Không in environment variables toàn bộ vào log** để debug; chúng có thể chứa secrets và connection strings.
- **Giới hạn network access** đến database và Key Vault theo chính sách; nếu dùng VNet/private endpoint phải cấu hình DNS/route và egress đúng.
- **Theo dõi thay đổi** qua Azure Activity Log, deployment audit và review IaC.
- **Quản lý vòng đời runtime**: cập nhật phiên bản có hỗ trợ bảo mật, kiểm thử dependency và rollback.
- **Dùng TLS** ở public endpoint và downstream connections phù hợp.

Một cấu hình secret được che trong Portal không có nghĩa mọi người có quyền quản lý app đều không thể tác động đến cách secret được sử dụng. Kết hợp least privilege, audit, approval và môi trường tách biệt.

## 20. Cấu hình bằng Infrastructure as Code và CI/CD

Để tránh drift, nên khai báo runtime, các **tên App settings**, slot stickiness và startup command trong công cụ IaC như **Bicep/Terraform** theo phương thức tổ chức phê duyệt. Giá trị secret nên được **tham chiếu** chứ không ghi trực tiếp trong template hoặc biến pipeline có thể bị lộ.

Ví dụ **mẫu cấu hình khái niệm**, không phải Bicep/Terraform hợp lệ để chạy trực tiếp:

~~~yaml
webApp:
  operatingSystem: Linux
  runtimeStack: "<RUNTIME_FROM_SUPPORTED_LIST>"
  startupCommand: "npm start"
  settings:
    APP_ENV: production
    LOG_LEVEL: info
    DB_PASSWORD: "@Microsoft.KeyVault(SecretUri=https://<VAULT>/secrets/<NAME>/)"
  deploymentSlotSettings:
    - APP_ENV
    - DB_PASSWORD
~~~

Pipeline nên có:

1. Kiểm tra source/dependencies và tạo artifact theo đúng runtime.
2. Xác minh target environment, App Service Plan/OS và Runtime Stack tương thích.
3. Deploy trước lên staging nếu workload hỗ trợ và yêu cầu.
4. Apply configuration từ IaC/pipeline an toàn, không log secret values.
5. Chạy health/smoke tests (bao gồm endpoint ứng dụng và phụ thuộc bắt buộc).
6. Promote/swap hoặc rollout có kiểm soát, quan sát error rate/latency.
7. Có đường rollback cho cả **artifact**, **runtime version** và **settings**.

**Cần cẩn trọng khi rollback:** một schema database đã migration có thể không tương thích bản ứng dụng cũ. Không xem swap app/đổi runtime về giá trị trước như phương án phục hồi chắc chắn cho mọi thay đổi.

## 21. Thực hành: cấu hình một Web App Linux trong sandbox

Mục tiêu: quan sát runtime, thêm biến môi trường không nhạy cảm, đặt startup command đúng với artifact đã triển khai, đọc cấu hình và kiểm tra HTTP. Bài có thể thực hiện trên **Web App lab có sẵn** hoặc tạo plan/app riêng nếu được phép sử dụng ngân sách.

### Cách A — dùng Web App lab có sẵn

Chuẩn bị:

- Được cấp quyền quản trị một Web App thử nghiệm, không phải production.
- Biết ngôn ngữ/runtime và tệp startup thực tế của app.
- Có Azure CLI, subscription đúng và quyền sửa Web App.
- Có quyền xem log hoặc Application Insights khi cần.

#### Bước 1: đọc cấu hình

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<LAB_RESOURCE_GROUP>"
APP="<LAB_WEB_APP_NAME>"

az webapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,state:state,kind:kind,url:defaultHostName}" \
  --output json

az webapp config show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{runtime:linuxFxVersion,startup:appCommandLine,alwaysOn:alwaysOn}" \
  --output json
~~~

#### Bước 2: thêm các setting không nhạy cảm

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings APP_ENV=lab LOG_LEVEL=info
~~~

Đọc tên setting, không in values:

~~~bash
az webapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].name" \
  --output table
~~~

#### Bước 3: startup command theo ứng dụng đang dùng

**Chỉ với Node.js app đã deploy có script start:**

~~~bash
az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --startup-file "npm start"
~~~

**Nếu app không phải Node.js**, không chạy lệnh trên. Thay bằng startup command đã kiểm chứng cho framework hoặc để cơ chế startup mặc định nếu phù hợp. Mọi lần thay đổi có thể restart app.

#### Bước 4: kiểm tra

~~~bash
az webapp config show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{runtime:linuxFxVersion,startup:appCommandLine}" \
  --output json

az webapp log tail \
  --resource-group "$RG" \
  --name "$APP"
~~~

Với hostname do App Service trả về, kiểm tra **GET /health** hoặc endpoint đang được ứng dụng hỗ trợ. Không dùng đường dẫn **/health** làm bằng chứng bắt buộc nếu app của bạn chưa có endpoint đó.

#### Bước 5: dọn sạch thay đổi

Nếu dùng app lab **có sẵn**, đưa startup command và APP_ENV/LOG_LEVEL về **giá trị trước khi thực hành** theo bản ghi cấu hình. **Không xóa toàn bộ Web App hoặc resource group do người khác quản lý**.

### Cách B — tạo Web App lab mới (tùy chọn)

Nếu được phép tạo tài nguyên có tính phí, một mẫu CLI cho Linux App Service Plan:

~~~bash
RG="rg-appservice-runtime-lab"
LOCATION="southeastasia"
PLAN="asp-runtime-lab"
APP="<GLOBALLY_UNIQUE_LAB_APP_NAME>"
RUNTIME="<SUPPORTED_LINUX_RUNTIME_VALUE>"

az group create \
  --name "$RG" \
  --location "$LOCATION"

az appservice plan create \
  --resource-group "$RG" \
  --name "$PLAN" \
  --location "$LOCATION" \
  --is-linux \
  --sku B1

az webapp list-runtimes --os-type linux --output table

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --name "$APP" \
  --runtime "$RUNTIME"
~~~

Trước khi chạy: thay các placeholder, chọn runtime thực sự được hỗ trợ, kiểm tra quota và **xác nhận chi phí plan B1** theo region. Web App name phải hợp lệ/duy nhất trong không gian endpoint được dùng. Bài này **chưa deploy code**, nên tạo xong app không chứng minh startup command có thể chạy một server thật.

Sau khi deploy một ứng dụng thử nghiệm khớp runtime và kiểm tra health, dọn toàn bộ resource group chỉ nếu **chính bạn tạo nó và nó không chứa tài nguyên khác**:

~~~bash
az group delete --name "$RG" --yes
az group exists --name "$RG"
~~~

Không xóa shared/production resource group. Kiểm tra Azure Cost Management vì phí có thể cập nhật trễ; việc dừng Web App không nhất thiết dừng chi phí App Service Plan.

## 22. Bài tập tình huống: Python API không khởi động

Một nhóm phát triển deploy Flask API lên **Linux App Service**. Họ dùng source **src/api.py**, trong đó tạo đối tượng **app = Flask(__name__)**. Log báo:

~~~text
ModuleNotFoundError: No module named 'app'
gunicorn: command not found
~~~

Thông tin cấu hình:

~~~text
Runtime: Python (bản đang được App Service hỗ trợ)
Startup Command: gunicorn app:app
Artifact:
  requirements.txt
  src/api.py
~~~

### Phân tích

Có **ít nhất hai vấn đề có thể độc lập**:

1. Module path trong startup command **app:app** không tương ứng với **src/api.py**.
2. **gunicorn** không tìm thấy: requirements.txt có thể thiếu gunicorn, hoặc quá trình build/deploy không cài dependency.

Không nên chỉ đổi runtime Python sang bản mới rồi kết luận đã xử lý. Cần kiểm tra artifact path, dependency, build logs, working directory và cấu trúc package của **src**.

### Phương án sửa

- Đảm bảo **requirements.txt** bao gồm **Flask** và **gunicorn** phù hợp.
- Xác định module import path từ thư mục chạy: chẳng hạn **src.api:app** nếu **src** có thể import và cấu trúc package/PYTHONPATH phù hợp; hoặc cấu hình startup để chạy đúng thư mục.
- Bật/kiểm tra build automation thích hợp để dependencies thực sự được cài.
- Kiểm tra Gunicorn lắng nghe trên interface/port đúng trong App Service Linux.
- Deploy vào lab/staging và xem log sau restart, không đổi production trực tiếp.

### Tiêu chí hoàn thành

| Kiểm tra | Kỳ vọng |
|---|---|
| Build logs | Dependencies cài thành công |
| Startup logs | Không còn ModuleNotFoundError/gunicorn missing |
| Runtime | Đúng Python version của artifact |
| App settings | APP_ENV/secret references được cấu hình chính xác |
| GET /health | Trả trạng thái thành công |
| API nghiệp vụ | Kết nối database và xử lý request thật đúng |

## 23. Bài tập tình huống: custom container chạy sai cổng

Đội khác đóng gói Node.js app thành container, code hard-code **listen(3000, "127.0.0.1")**. Họ đặt App Service **WEBSITES_PORT=8080**. Container khởi động nhưng App Service báo timeout.

### Vì sao lỗi?

- Platform đang thử định tuyến tới cổng **8080**, còn app chạy cổng **3000**.
- App chỉ bind **127.0.0.1**, có thể không nhận kết nối từ đường mạng container mà nền tảng dùng.
- Dockerfile **EXPOSE** hoặc app setting không tự sửa lệnh **server.listen()**.

### Cách xử lý

1. Chọn một cổng ứng dụng thực sự lắng nghe (ví dụ 8080).
2. Sửa code hoặc startup config bind **0.0.0.0:8080**.
3. Đặt **WEBSITES_PORT=8080** cho custom container ở những mô hình yêu cầu.
4. Build và push image mới; deploy vào lab/staging.
5. Xem container startup logs, health và endpoint HTTP; xác minh không còn timeout.

Không sửa port ngẫu nhiên giữa production khi chưa biết app/framework và container runtime. Một số container tự dùng PORT hoặc endpoint mặc định do image quy định; cần đồng bộ từng lớp.

## 24. Checklist trước production

- [ ] Runtime/OS/App Service Plan phù hợp với ứng dụng và vòng đời phiên bản được hỗ trợ.
- [ ] Build pipeline, artifact và runtime dùng các phiên bản/dependency tương thích.
- [ ] Startup command chỉ được đặt khi cần, đúng executable, module path, working directory và process.
- [ ] Ứng dụng bind đúng interface/port theo built-in runtime hoặc custom container; không nhầm WEBSITES_PORT với PORT.
- [ ] App settings đặt tên nhất quán; boolean/numeric được parse và validate.
- [ ] Không hard-code secret; Key Vault references/managed identity được cấp quyền và kiểm tra trạng thái.
- [ ] Connection strings, VNet integration, Private Endpoint, DNS và outbound access đã được thử nghiệm.
- [ ] Slot settings được đánh dấu đúng; staging không ghi dữ liệu production.
- [ ] Thay đổi app settings/runtime/startup có kế hoạch restart, warm-up và rollback.
- [ ] Log stream, Application Insights, health endpoint và cảnh báo lỗi hoạt động.
- [ ] Không dựa vào local filesystem của instance để giữ dữ liệu nghiệp vụ không thể tái tạo.
- [ ] IaC/CI/CD quản lý cấu hình, review trước thay đổi và lưu audit.
- [ ] Đã kiểm thử smoke test, HTTP 5xx, thời gian startup và khả năng scale.
- [ ] Đã xem tier, Always On/slots và chi phí App Service Plan, logging và mạng.

## 25. Câu hỏi tự kiểm tra

1. App Service Plan khác Web App ở điểm nào? Hai Web App dùng chung plan có thể ảnh hưởng nhau về hiệu năng không?
2. Với code-based Linux, runtime stack khác gì phiên bản Node/Python được cài trong một custom container image?
3. Vì sao thay đổi App settings có thể dẫn tới restart và gián đoạn phiên đang xử lý?
4. **APP_ENV=production** có tự động khiến Azure đổi runtime hay bật HTTPS không?
5. Biến môi trường được đọc trong Node.js, Python, .NET và Java như thế nào?
6. Vì sao không nên truyền mật khẩu thật qua **--settings DB_PASSWORD=...** trong terminal/pipeline?
7. Key Vault reference cần những yếu tố nào để resolve thành công?
8. Startup command khác build command và deployment command ở điểm gì?
9. Vì sao một App Service Python cần gunicorn và module path đúng với artifact?
10. Trong custom container, **WEBSITES_PORT** có tự khiến chương trình listen vào cổng đó không?
11. Với Windows App Service, tại sao không nên sao chép startup command Bash Linux?
12. Slot setting dùng để giải quyết rủi ro gì khi swap staging ↔ production?
13. Khi App Service báo Application Error, bạn sẽ kiểm tra những dữ liệu nào trước khi đổi runtime?
14. Always On có bảo đảm không bao giờ có HTTP 5xx hoặc cold start trong mọi tình huống không?
15. Tại sao một pipeline deploy thành công chưa chứng minh ứng dụng đã phục vụ request đúng?

## 26. Tài liệu tham khảo

- [Configure an App Service app](https://learn.microsoft.com/azure/app-service/configure-common) — Application settings, general settings, startup và các tùy chọn chung.
- [Configure a Linux App Service app](https://learn.microsoft.com/azure/app-service/configure-linux-open-ssh-session) — truy cập và vận hành ứng dụng Linux, SSH theo mô hình hỗ trợ.
- [Configure Node.js applications in Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-nodejs) — runtime, dependency và startup.
- [Configure Python applications in Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-python) — Oryx, Gunicorn, Flask/Django và startup.
- [Configure .NET applications in Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-dotnetcore) — hosting và runtime .NET.
- [Configure Java applications in Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-java) — Java SE/Tomcat và cấu hình.
- [Configure a custom container for Azure App Service](https://learn.microsoft.com/azure/app-service/configure-custom-container) — image, port và biến container.
- [Key Vault references for Azure App Service](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references) — quản lý secret qua managed identity và references.
- [Set up staging environments with deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots) — slot settings và swap.
- [Enable diagnostic logging for Azure App Service](https://learn.microsoft.com/azure/app-service/troubleshoot-diagnostic-logs) — log khi deploy/startup thất bại.
- [Azure CLI: az webapp config](https://learn.microsoft.com/cli/azure/webapp/config) — runtime và startup command.
- [Azure CLI: az webapp config appsettings](https://learn.microsoft.com/cli/azure/webapp/config/appsettings) — tạo, đọc và xóa app settings.

**Kết luận:** Để ứng dụng chạy ổn định trên Azure App Service, cần đồng bộ **runtime stack**, **build artifact**, **application settings** và **startup command**. Mặc định hợp lý không phải lúc nào cũng phù hợp: hãy kiểm tra bản runtime được hỗ trợ, chỉ định entrypoint/port chính xác, dùng Key Vault và managed identity cho secret, thử trên staging và quan sát log/health sau mỗi thay đổi. Cấu hình có kiểm soát giúp giảm lỗi deployment, bảo vệ dữ liệu và tránh lãng phí chi phí vận hành.
