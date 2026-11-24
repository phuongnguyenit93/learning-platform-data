# Chạy cục bộ bằng Azure Functions Core Tools

## 1. Mục tiêu: chạy Azure Function trên máy phát triển

Trong module **SPRING_CLOUD_FUNCTION**, ta phát triển logic nghiệp vụ có thể tái sử dụng bằng `Supplier<T>`, `Function<T,R>` và `Consumer<T>`. `FunctionCatalog` đăng ký/tra cứu các hàm, composition ghép nhiều bước và các adapter giúp cùng một logic được gọi qua HTTP, sự kiện hoặc môi trường serverless.

Khi triển khai lên **Azure Functions**, Java handler được Azure Functions Host kích hoạt theo trigger. Trước khi phát hành lên cloud, ta cần chạy chính runtime Azure trên máy phát triển để xác minh:

- Azure Host có khởi động và nhận diện các `@FunctionName` methods không?
- Spring Cloud Function adapter có tạo Spring context và inject handler/services đúng không?
- `FunctionCatalog.lookup(...)` có tìm được function/composition không?
- HTTP route, body, response và validation có đúng hợp đồng không?
- Queue/Blob/Timer triggers có kết nối đúng nguồn dữ liệu và chạy theo kỳ vọng không?
- Log, exception, retry và invocation metadata có thể quan sát khi debug không?

**Azure Functions Core Tools** là bộ công cụ dòng lệnh cung cấp local Functions Host để phát triển, chạy và kiểm thử function app. Với project Java Maven, Azure Maven plugin tích hợp Core Tools thông qua goal `azure-functions:run`. Đây là cách chạy được dùng xuyên suốt bài học.

### Sau bài học, bạn có thể

1. Chuẩn bị JDK, Maven, Azure Functions Core Tools v4 và Azurite khi cần.
2. Kiểm tra phiên bản công cụ và xử lý xung đột `func` trên Windows.
3. Cấu hình `host.json` và `local.settings.json` đúng vai trò.
4. Build và chạy Spring Cloud Function Azure adapter bằng Maven hoặc Gradle.
5. Gọi HTTP Trigger local bằng cURL/PowerShell, kiểm tra status và response.
6. Chạy Queue/Blob/Timer Trigger trong môi trường local phù hợp.
7. Debug Java worker từ IntelliJ IDEA hoặc VS Code.
8. Chẩn đoán lỗi Core Tools, Java worker, Spring dependency injection, FunctionCatalog và binding extensions.
9. Biết điều gì có thể kiểm thử local và điều gì vẫn phải xác minh trên Azure staging.

**Phạm vi:** bài hướng dẫn phát triển và chạy local cho Azure Functions Java dùng Spring Cloud Function Azure adapter. Không thay thế các bài riêng về cấu hình triển khai production hoặc quản lý tài nguyên cloud.

## 2. Kiến trúc local runtime

~~~mermaid
flowchart TB
    subgraph Dev["Máy phát triển"]
        A["Terminal / IDE"]
        B["Maven hoặc Gradle"]
        C["Spring Cloud Function Azure adapter"]
        D["Java classes: @Component / @FunctionName"]
        E["local.settings.json + host.json"]
        F["Azurite (khi cần Storage)"]
    end
    subgraph LocalHost["Azure Functions Core Tools v4"]
        G["Azure Functions Host"]
        H["Java language worker"]
        I["Azure trigger / binding runtime"]
    end
    A --> B
    B --> C
    B --> G
    D --> H
    E --> G
    G --> I
    I --> H
    F <--> I
    H --> J["Spring ApplicationContext"]
    J --> K["FunctionCatalog"]
    K --> L["Supplier / Function / Consumer"]
    L --> H
    H --> M["HTTP response / output binding"]
~~~

Luồng xử lý điển hình:

1. Maven compile và package Java application.
2. `azure-functions:run` khởi chạy Azure Functions Host local.
3. Host đọc `host.json`, local settings và metadata các Azure Functions.
4. Host khởi tạo Java language worker và gửi invocation khi có trigger.
5. Spring Cloud Function Azure adapter khởi tạo Spring context, tạo handler `@Component` và inject các dependencies.
6. Handler gọi function bean trực tiếp hoặc qua `FunctionCatalog`.
7. Handler trả HTTP response hoặc ghi output binding; Host quản lý trigger/binding lifecycle.

**Ba thành phần không thay thế nhau:**

| Thành phần | Trách nhiệm | Không làm thay |
| --- | --- | --- |
| **Core Tools / Functions Host** | Chạy runtime Azure local, load functions, trigger và bindings. | Không tự viết nghiệp vụ Spring. |
| **Maven/Gradle Azure plugin** | Build/package, cấu hình chạy local và tích hợp Core Tools. | Không thay thế Java compiler hoặc Spring context. |
| **Spring Cloud Function Azure adapter** | Nối Java Worker với Spring DI, FunctionCatalog và function model. | Không tự tạo mọi Azure trigger nếu thiếu Azure annotations/metadata. |

### 2.1. Chạy local khác chạy Spring Boot thông thường

Một Spring Boot application có thể chạy bằng `java -jar` hoặc Maven goal `spring-boot:run`, nhưng cách đó **không tự khởi động Azure Functions Host**. Đối với handler có `@FunctionName`, cần chạy local Functions Host để kiểm tra:

- Function discovery và binding metadata.
- Java worker startup.
- Trigger routing và authorization behavior.
- `ExecutionContext` thực tế do Azure runtime cấp.
- HTTP response mapping và output bindings.

**Không dùng `java -jar` làm bằng chứng duy nhất rằng Azure Function chạy được.**

## 3. Công cụ cần chuẩn bị

| Công cụ | Vai trò | Có bắt buộc cho mọi trường hợp? |
| --- | --- | --- |
| **JDK** | Compile và chạy Java worker/application. | Có. |
| **Apache Maven hoặc Gradle** | Build và gọi Azure Functions plugin. | Có một trong hai theo project. |
| **Azure Functions Core Tools v4** | Local Functions Host và lệnh `func`. | Có cho workflow local này. |
| **Node.js/npm** | Cài Core Tools qua npm hoặc chạy Azurite qua npm. | Chỉ cần nếu chọn cách cài đó. |
| **Azurite** | Giả lập Azure Storage Blob/Queue/Table. | Chỉ cần khi Host/trigger/binding dùng Storage. |
| **Azure CLI** | Đăng nhập và thao tác tài nguyên cloud; một số workflow deploy dùng nó. | Không cần cho HTTP-only local test. |
| **IDE Java** | Đặt breakpoint, xem stack trace và debug. | Tùy chọn. |

### 3.1. Kiểm tra JDK và Maven

Trên Windows PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
mvn -version
~~~

Nếu project có Maven Wrapper:

~~~powershell
.\mvnw.cmd -version
~~~

Kết quả cần cho biết:

- Java version mà project yêu cầu, ví dụ Java 17.
- `JAVA_HOME` trỏ đến thư mục JDK, không phải thư mục `bin`.
- Maven chạy bằng JDK dự kiến.
- Compiler release trong `pom.xml` khớp Java runtime được dùng.

Ví dụ cấu hình Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đây là ví dụ cho project Java 17; nếu project đã dùng compiler plugin hoặc property khác do parent quản lý, hãy theo cấu hình thực tế. Không đặt Java target mới hơn runtime Azure/local worker.

### 3.2. Kiểm tra Azure Functions Core Tools

~~~powershell
func --version
where.exe func
~~~

Với workflow ổn định, sử dụng **Azure Functions Core Tools v4**, tương thích với Azure Functions runtime 4.x. Tài liệu Microsoft hiện có thêm Azure Functions CLI v5 ở trạng thái preview; bài này tập trung vào Core Tools v4 GA và Azure Maven plugin cho Java.

Nếu `func --version` không chạy:

- Kiểm tra Core Tools đã được cài chưa.
- Mở terminal mới sau khi cài để cập nhật PATH.
- Trên Windows dùng `where.exe func` để biết executable được gọi.
- Nếu có nhiều đường dẫn `func.exe`, xử lý bản cài trùng trước khi tiếp tục.

### 3.3. Kiểm tra các công cụ tùy chọn

~~~powershell
node --version
npm --version
az version
~~~

`node`/`npm` chỉ cần nếu cài Core Tools/Azurite bằng npm. Azure CLI chỉ cần cho thao tác đăng nhập, đồng bộ settings hoặc triển khai lên cloud; không cần cho một bài kiểm thử HTTP local đơn giản.

## 4. Cài đặt Azure Functions Core Tools trên Windows

Windows có hai cách phổ biến:

1. **MSI installer:** phù hợp với người dùng muốn cài công cụ dòng lệnh mà không cần Node.js.
2. **npm package:** phù hợp với môi trường VS Code/Node.js và Azure Functions extension.

Chọn **một** phương thức và dùng cùng phương thức đó khi nâng cấp.

### 4.1. Cài bằng Windows MSI

1. Mở trang Microsoft Learn về [cài đặt Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local).
2. Chọn Windows và tải bản **64-bit MSI** phù hợp.
3. Cài đặt theo wizard.
4. Mở PowerShell mới và chạy:

~~~powershell
func --version
where.exe func
~~~

Không cần Node.js chỉ để dùng bản MSI.

### 4.2. Cài bằng npm

Nếu đã cài Node.js và npm:

~~~powershell
npm install -g azure-functions-core-tools@4 --unsafe-perm true
~~~

Sau khi cài:

~~~powershell
func --version
where.exe func
~~~

Nếu lệnh `func` chưa được nhận diện, kiểm tra npm global bin folder có trong PATH và mở terminal mới. Không nên cài MSI và npm cùng lúc trên một máy rồi hy vọng Windows luôn chọn đúng version; Microsoft cảnh báo hai cách cài có thể tạo xung đột PATH.

### 4.3. Cập nhật Core Tools

Cập nhật bằng **đúng phương thức đã dùng khi cài**:

- MSI: gỡ phiên bản cũ theo hướng dẫn Windows rồi cài MSI mới.
- npm: chạy lại npm install cho major version 4.
- Chocolatey: dùng quy trình upgrade của Chocolatey nếu đã cài theo cách đó.

Sau cập nhật, kiểm tra lại `func --version` và `where.exe func`. Không nên để IDE sử dụng một Core Tools khác với terminal.

### 4.4. macOS và Linux

macOS có thể cài qua Homebrew:

~~~bash
brew tap azure/functions
brew install azure-functions-core-tools@4
~~~

Ubuntu/Debian có package Microsoft dành cho Core Tools v4; thực hiện theo hướng dẫn cài đặt chính thức cho đúng bản phân phối và kiến trúc. Có thể dùng npm nếu môi trường Node.js phù hợp.

Không sao chép lệnh APT giữa Ubuntu/Debian versions mà không kiểm tra package repository tương ứng.

## 5. Tạo project Java hoặc chuẩn bị project Spring Cloud Function có sẵn

### 5.1. Nếu bắt đầu một Azure Java Functions project mới

Microsoft hướng dẫn dùng **Azure Functions Maven archetype** cho Java. Trong một thư mục trống:

~~~powershell
mvn archetype:generate "-DarchetypeGroupId=com.microsoft.azure" "-DarchetypeArtifactId=azure-functions-archetype" "-DjavaVersion=17"
~~~

Maven sẽ hỏi các giá trị như `groupId`, `artifactId`, `version` và Java package. Sau khi xác nhận, archetype tạo project Java Azure Functions mẫu có:

- Maven build file.
- Java HTTP-triggered function mẫu.
- `host.json`.
- `local.settings.json` cho phát triển local.
- Cấu hình Azure Functions Maven plugin.

Đây là cách khởi tạo **project mới**. Không chạy archetype vào thư mục project Spring Cloud Function hiện có vì có thể tạo/xung đột cấu trúc và file.

### 5.2. Nếu project đã có Spring Cloud Function Azure adapter

Trong project hiện tại, kiểm tra:

- Có `pom.xml` hoặc `build.gradle`.
- Có `spring-cloud-function-adapter-azure`.
- Có Azure Java Functions library tương thích.
- Có Azure Maven/Gradle plugin.
- Có handler `@Component` với public method `@FunctionName`.
- Có Spring Boot main class được adapter xác định.
- Có `host.json` và cấu hình local settings thích hợp.

**Không cần chạy `func init` hoặc `func new` để tạo Java functions theo kiểu các language templates khác.** Java dùng Maven archetype/plugin làm workflow chính; nếu đã có source Spring Cloud Function thì bổ sung đúng adapter/handler/package configuration theo project.

### 5.3. Cấu trúc thư mục ví dụ

~~~text
spring-cloud-function-azure/
├── pom.xml
├── local.settings.json
└── src/
    ├── main/
    │   ├── java/example/azure/
    │   │   ├── OrderFunctionApplication.java
    │   │   └── OrderAzureHandler.java
    │   └── resources/
    │       ├── host.json
    │       └── application.properties
    └── test/
        └── java/example/azure/
            └── OrderFunctionApplicationTest.java
~~~

`local.settings.json` thường nằm ở **root project**, cùng cấp `host.json`. Không đặt nó trong `src/main/resources` để đóng gói vào JAR như một file cấu hình ứng dụng thông thường.

## 6. Cấu hình host.json và local.settings.json

### 6.1. host.json

`host.json` là cấu hình **Azure Functions Host**, dùng chung cho các functions trong một Function App. Mẫu tối thiểu:

~~~json
{
  "version": "2.0"
}
~~~

Một cấu hình khai báo HTTP route prefix tường minh (giá trị mặc định của host là `api`):

~~~json
{
  "version": "2.0",
  "extensions": {
    "http": {
      "routePrefix": "api"
    }
  }
}
~~~

Với cấu hình trên, route `orders/normalize` sẽ có URL `/api/orders/normalize`. Nếu đặt `routePrefix` thành chuỗi rỗng, URL không có tiền tố `/api`.

Một số trigger cần binding extension và cấu hình extension tương ứng. Không thêm extension bundle hay binding-specific setting chỉ vì một function khác dùng nó; kiểm tài liệu của trigger/extension đang sử dụng.

### 6.2. local.settings.json

File này cung cấp **environment/app settings cho lần chạy local**, chủ yếu trong collection `Values`. Ví dụ với Spring Cloud Function Azure adapter:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.OrderFunctionApplication",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

Giải thích:

| Setting | Ý nghĩa |
| --- | --- |
| `IsEncrypted` | Cho biết file local settings có được Core Tools mã hóa hay không. |
| `FUNCTIONS_WORKER_RUNTIME=java` | Chọn Java worker runtime. |
| `FUNCTIONS_EXTENSION_VERSION=~4` | Chọn Azure Functions runtime 4.x. |
| `MAIN_CLASS` | Chỉ rõ Spring Boot application class cho adapter khi project cần cấu hình tường minh. |
| `AzureWebJobsStorage` | Storage connection cho host/bindings; `UseDevelopmentStorage=true` trỏ tới Azurite. |

`MAIN_CLASS` phải là **fully qualified name** của Spring application class, ví dụ `example.azure.OrderFunctionApplication`; không trỏ đến handler `OrderAzureHandler`. Nếu adapter tự xác định main class từ manifest, setting này có thể không cần, nhưng cấu hình tường minh giúp tránh nhầm lẫn trong project có nhiều entrypoints.

`AzureWebJobsStorage` phụ thuộc hosting/trigger và host operations. Với Queue/Blob/Timer hoặc các chức năng cần host storage, phải cấu hình connection phù hợp. Nếu chỉ có HTTP function và project không cần storage, kiểm tra yêu cầu thực tế của runtime/adapter thay vì mặc định thêm một connection string cloud.

### 6.3. Phân biệt ba file cấu hình

| File | Được đọc bởi | Dùng cho |
| --- | --- | --- |
| `host.json` | Azure Functions Host | Trigger, binding, logging và host behavior. |
| `local.settings.json` | Core Tools local runtime | App settings và connection dùng khi phát triển. |
| `application.properties` | Spring Boot | Business configuration, Spring logging, bean configuration. |

Ví dụ `application.properties`:

~~~properties
logging.level.example.azure=INFO
spring.cloud.function.definition=normalizeOrder
~~~

Thuộc tính `spring.cloud.function.definition` có ý nghĩa với những adapter/flow dùng definition mặc định của SCF; nếu handler đang gọi `catalog.lookup("normalizeOrder")` tường minh thì property này không tự tạo Azure route hoặc thay thế handler. Chỉ khai báo khi ứng dụng thực sự cần.

### 6.4. Bảo vệ local settings

`local.settings.json` có thể chứa connection strings, keys hoặc secrets:

- Thêm file này vào `.gitignore` theo chính sách project; không commit secrets.
- Dùng connection của tài nguyên **development**, không dùng nhầm production.
- Core Tools hỗ trợ mã hóa local settings bằng `func settings encrypt`; việc mã hóa local không thay thế secret management.
- Khi publish, local settings **không tự động được đồng bộ lên Azure theo mặc định**. Tạo App Settings cloud riêng bằng quy trình đã được phê duyệt.
- Nếu tải settings từ Azure về local, lưu ý thao tác có thể ghi đè giá trị hiện có.

### 6.5. Không dùng storage emulator cho mọi dịch vụ

`UseDevelopmentStorage=true` chỉ dùng với **Azure Storage emulator Azurite**. Azurite hỗ trợ Blob, Queue và Table; nó không giả lập Service Bus, Event Hubs, Cosmos DB hoặc mọi Azure service khác. Với những binding đó, cần service dev riêng, connection phù hợp hoặc test double theo đúng mục tiêu.

## 7. Chạy Azurite khi cần Azure Storage

### 7.1. Khi nào cần Azurite?

| Function/host behavior | Có cần Azurite? |
| --- | --- |
| HTTP Trigger thuần, không dùng Storage | Thường không cần riêng Azurite. |
| Azure Storage Queue Trigger/Output | Có, nếu muốn kiểm thử local bằng Storage emulator. |
| Blob Trigger/Input/Output | Có, nếu test local với Blob emulator. |
| Timer Trigger | Tùy host/storage configuration; Timer có thể sử dụng host storage cho coordination. |
| Service Bus Trigger | Không; cần Service Bus dev resource/emulator tương ứng. |
| Event Hubs Trigger | Không; cần Event Hubs dev resource/connection. |

### 7.2. Cài Azurite bằng npm

Nếu máy có Node.js/npm:

~~~powershell
npm install -g azurite
~~~

Tạo workspace dữ liệu:

~~~powershell
New-Item -ItemType Directory -Force -Path C:\azurite
~~~

Chạy Azurite trong **một terminal riêng**:

~~~powershell
azurite --silent --location C:\azurite
~~~

Giữ terminal đó mở khi chạy Azure Functions Host. Mặc định Azurite sử dụng:

| Storage service | Port |
| --- | ---: |
| Blob | 10000 |
| Queue | 10001 |
| Table | 10002 |

Có thể bật debug log:

~~~powershell
azurite --location C:\azurite --debug C:\azurite\debug.log
~~~

### 7.3. Dùng Docker nếu không muốn cài npm global

Nếu đã có Docker:

~~~powershell
docker run -p 10000:10000 -p 10001:10001 -p 10002:10002 -v C:\azurite:/data mcr.microsoft.com/azure-storage/azurite
~~~

Đây là lệnh minh họa trên Windows PowerShell. Thư mục host phải tồn tại và Docker Desktop cần chạy. Chỉ expose các port mà project cần nếu muốn giới hạn phạm vi.

### 7.4. Kiểm tra Azurite trước khi chạy function

- Terminal Azurite không báo port đã được sử dụng.
- Storage Explorer có thể kết nối emulator nếu cần kiểm tra Queue/Blob.
- `AzureWebJobsStorage` trong `local.settings.json` dùng `UseDevelopmentStorage=true`.
- Queue/container được tạo đúng tên trước khi gửi message, hoặc được tạo bằng tooling phù hợp.
- Không để host local trỏ nhầm sang production Storage account.

## 8. Build và chạy Java Azure Functions bằng Maven

### 8.1. Build trước

Tại thư mục gốc chứa `pom.xml`:

~~~powershell
.\mvnw.cmd clean package
~~~

Nếu project không có Maven Wrapper:

~~~powershell
mvn clean package
~~~

Build phải hoàn thành thành công trước khi khởi động local Host. Trong log, kiểm tra:

- Java compiler sử dụng đúng JDK.
- Spring Cloud Function Azure adapter được resolve.
- Azure Functions Maven plugin được cấu hình.
- Plugin xử lý các method `@FunctionName` và trigger annotations.
- Build tạo staging metadata/package theo cấu hình project.

### 8.2. Chạy local bằng Azure Maven plugin

~~~powershell
.\mvnw.cmd azure-functions:run
~~~

Hoặc:

~~~powershell
mvn azure-functions:run
~~~

Đây là workflow Java Maven chính được Microsoft và Spring Cloud Function hướng dẫn. Azure Maven plugin khởi chạy local Functions Host thông qua Core Tools và chuẩn bị Java application theo project configuration.

**Không cần chạy `func init` sau khi project đã có Azure Java Maven structure.** Cũng không chạy `SpringApplication.run` bằng một terminal thứ hai để thay cho Functions Host.

### 8.3. Kết quả mong đợi khi host khởi động

Log thường hiển thị thông tin tương tự:

~~~text
Azure Functions Core Tools
Core Tools Version: 4.x
Function Runtime Version: 4.x

Worker process started and initialized.

Functions:

    normalizeAzureOrder: [POST] http://localhost:7071/api/orders/normalize
~~~

Dòng log và định dạng có thể khác theo version Core Tools/plugin. Điều cần xác nhận là:

- Host khởi động thành công.
- Java worker được khởi tạo.
- Tên Azure Function xuất hiện.
- HTTP URL, method và route đúng với annotations/metadata.
- Không có lỗi Spring context, dependency injection hoặc FunctionCatalog lookup.

### 8.4. Dừng host

Nhấn `Ctrl+C` tại terminal đang chạy `azure-functions:run`. Chờ host và Java worker dừng hoàn toàn trước khi chạy lại project hoặc khởi động một host khác.

Chỉ nên có **một Functions Host cho cùng local project/port** đang phục vụ test tại một thời điểm.

## 9. Chạy với Gradle

Nếu project dùng Gradle và đã cấu hình Azure Functions plugin:

~~~powershell
.\gradlew.bat clean jar --info
~~~

Sau đó:

~~~powershell
.\gradlew.bat azureFunctionsRun
~~~

Trên macOS/Linux:

~~~bash
./gradlew clean jar --info
./gradlew azureFunctionsRun
~~~

Azure Gradle plugin chịu trách nhiệm build/package và gọi local runtime. Task name/cấu hình chính xác phụ thuộc version plugin đã khóa trong `build.gradle`; xem task list của project nếu task khác tên.

**Không trộn Maven và Gradle cho cùng một release** nếu không có quy trình build đã định nghĩa. Chọn build tool làm nguồn package duy nhất để tránh staging artifacts khác nhau.

## 10. Gọi HTTP Trigger local

### 10.1. URL mặc định

Azure Functions Host local mặc định dùng:

~~~text
http://localhost:7071
~~~

Với `routePrefix` mặc định `api`, một trigger:

~~~java
@FunctionName("normalizeAzureOrder")
public HttpResponseMessage normalize(
        @HttpTrigger(
                name = "request",
                methods = {HttpMethod.POST},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/normalize")
        HttpRequestMessage<Optional<String>> request,
        ExecutionContext context) {
    // ...
}
~~~

có URL:

~~~text
POST http://localhost:7071/api/orders/normalize
~~~

URL chính xác phải lấy từ **host startup output**; route prefix/port có thể được cấu hình khác.

### 10.2. Gửi request bằng cURL

Mở terminal thứ hai, trong khi Azure Functions Host vẫn chạy:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/normalize" \
  -H "Content-Type: text/plain" \
  --data " dh-701 "
~~~

Giả sử function chuẩn hóa uppercase và thêm prefix, body mong đợi:

~~~text
REF-DH-701
~~~

Tùy code và response builder, header content type/status có thể khác. Đừng lấy response sample của bài khác làm contract; dùng output do chính function của project quy định.

### 10.3. Gửi request từ Windows PowerShell

Windows PowerShell 5.1 có alias `curl`, vì vậy có thể gọi tường minh `curl.exe`:

~~~powershell
curl.exe -i -X POST "http://localhost:7071/api/orders/normalize" -H "Content-Type: text/plain" --data " dh-701 "
~~~

Hoặc dùng cmdlet PowerShell:

~~~powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:7071/api/orders/normalize" -ContentType "text/plain" -Body " dh-701 "
~~~

`Invoke-RestMethod` tiện khi chỉ cần đọc body. Để kiểm tra status/header chi tiết, dùng `Invoke-WebRequest` hoặc `curl.exe -i`.

### 10.4. Kiểm tra input hợp lệ và không hợp lệ

| Request body | Kết quả mong đợi theo ví dụ | Mục đích |
| --- | --- | --- |
| `" dh-701 "` | `REF-DH-701`, HTTP 200 | Kiểm trim/uppercase/composition. |
| `"   "` | HTTP 400 | Validation rỗng. |
| Body rỗng | HTTP 400 | Xác nhận handler không gọi function với input không hợp lệ. |
| `"dh-702"` | Tùy contract của function; ví dụ cần body có dữ liệu đơn hợp lệ | Kiểm schema/input format. |

Nếu function trả JSON, dùng `Content-Type: application/json` và gửi JSON hợp lệ; nếu function trả text, dùng `text/plain`. HTTP body và content type phải khớp converter/contract của adapter.

### 10.5. Authorization khi chạy local

Với `AuthorizationLevel.FUNCTION`, Azure cloud yêu cầu function key theo host policy. Nhưng **local Functions Host không enforce access keys giống môi trường cloud** trong các workflow Core Tools thông thường. Do đó:

- Local request có thể không cần key.
- Không kết luận endpoint production đã bảo mật chỉ vì local request chạy được.
- Kiểm tra function key/authentication/network restrictions trên Azure staging.
- Không commit hoặc log key trong quá trình test.


## 11. Chạy non-HTTP triggers cục bộ

HTTP là loại trigger dễ kiểm thử nhất vì chỉ cần gọi URL. Các trigger sự kiện cần một nguồn dữ liệu hoặc một cơ chế kích hoạt khác.

### 11.1. Queue Trigger với Azurite

Nếu method dùng `@QueueTrigger`:

~~~java
@FunctionName("processOrder")
public void processOrder(
        @QueueTrigger(
                name = "order",
                queueName = "orders-input",
                connection = "AzureWebJobsStorage")
        String payload,
        ExecutionContext context) {
    // Gọi Spring function/service.
}
~~~

Cần:

1. Azurite đang chạy và Queue service khả dụng.
2. `AzureWebJobsStorage` trỏ tới Azurite.
3. Queue `orders-input` đã tồn tại hoặc được tạo bởi tooling.
4. Host local đã khởi động và discover `processOrder`.
5. Một message hợp lệ được gửi vào queue.

Có thể dùng Azure Storage Explorer để tạo queue và gửi message; hoặc dùng Azure Storage SDK/CLI tool phù hợp. Azurite không tự tạo mọi queue của ứng dụng khi chỉ khởi chạy process.

### 11.2. Blob Trigger

Với `@BlobTrigger`, cần Blob service của Azurite hoặc Azure Storage dev account và container/path phù hợp. Upload file vào đúng container sẽ kích hoạt function theo cơ chế của extension. Kiểm tra log host để thấy trigger processing.

Blob trigger có thể có độ trễ phát hiện tùy trigger source/extension; không kỳ vọng upload và invocation luôn xảy ra đồng bộ ngay lập tức.

### 11.3. Timer Trigger

`@TimerTrigger` dùng lịch NCRONTAB của Azure Functions Host. Khi host chạy local, lịch vẫn được áp dụng; ví dụ:

~~~java
@TimerTrigger(
        name = "timer",
        schedule = "0 */1 * * * *")
String timerInfo
~~~

Biểu thức trên minh họa mỗi phút tại giây 0. Timer không cần HTTP request để kích hoạt. Để test nhanh, chọn schedule phù hợp và xem host log; tránh schedule quá dày gây tải hoặc log nhiễu.

### 11.4. Service Bus, Event Hubs và dịch vụ khác

Azurite **không** giả lập Service Bus hoặc Event Hubs. Khi function dùng các trigger này, chọn một trong các phương án:

- Kết nối đến một resource development riêng trong Azure.
- Dùng emulator/test infrastructure do dịch vụ đó hỗ trợ.
- Test business function với message giả lập, còn binding được xác minh trong integration/staging test.

Không đặt connection string production vào local settings. Khi local test kết nối cloud resource, message có thể thật sự được consume, ghi hoặc phát ra dịch vụ.

## 12. Debug Java worker từ IDE

### 12.1. Khởi động Maven plugin ở debug mode

Dừng host đang chạy bình thường, sau đó:

~~~powershell
.\mvnw.cmd azure-functions:run -DenableDebug
~~~

Hoặc:

~~~powershell
mvn azure-functions:run -DenableDebug
~~~

Java worker thường mở debug socket tại port `5005`. Xem log startup để xác nhận dòng thông báo tương tự `Listening for transport dt_socket at address: 5005`.

### 12.2. Attach debugger trong IntelliJ IDEA

1. Mở project Maven trong IntelliJ.
2. Chọn **Run → Edit Configurations**.
3. Thêm **Remote JVM Debug**.
4. Host `127.0.0.1`, port `5005`, transport `Socket`.
5. Start `azure-functions:run -DenableDebug`.
6. Attach debugger.
7. Đặt breakpoint trong Azure handler hoặc Spring functional bean.
8. Gửi HTTP request từ terminal thứ hai để đi qua breakpoint.

### 12.3. Attach debugger trong Visual Studio Code

Một cấu hình `.vscode/launch.json` minh họa:

~~~json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "java",
      "name": "Attach to Azure Functions Java Worker",
      "request": "attach",
      "hostName": "127.0.0.1",
      "port": 5005
    }
  ]
}
~~~

Chạy Maven goal debug, sau đó chọn cấu hình attach. Gửi request HTTP để debugger dừng ở breakpoint.

**Bảo mật:** debug port chỉ nên mở trên loopback/local developer machine. Không mở remote debugger port công khai trên môi trường Azure hoặc mạng không tin cậy.

### 12.4. Debug host khác debug Java worker

- **Functions Host logs:** discovery, trigger, binding, route và host lifecycle.
- **Java worker debugger:** code Java, Spring handler, function bean và stack trace.
- **Spring logs:** context startup, bean creation, catalog registration và dependency injection.

Một lỗi function không xuất hiện breakpoint có thể xảy ra **trước khi Java method được gọi**, ví dụ Host chưa discover function hoặc binding không kích hoạt.

## 13. Đọc log và quan sát invocation

### 13.1. Ba nguồn log

| Nguồn | Nội dung | Nơi xem |
| --- | --- | --- |
| Azure Functions Host | Worker startup, function discovery, trigger/binding, HTTP route. | Terminal chạy `azure-functions:run`. |
| Java/Spring application | Bean startup, service, FunctionCatalog, business errors. | Cùng terminal hoặc IDE console theo cấu hình logging. |
| Storage emulator | Queue/Blob requests, connection và storage errors. | Terminal/log file Azurite. |

### 13.2. Log từ ExecutionContext

Azure handler nhận `ExecutionContext` cho mỗi invocation:

~~~java
context.getLogger().info(
        "Function=" + context.getFunctionName()
        + ", invocation=" + context.getInvocationId());
~~~

`getInvocationId()` là ID của **một lần thực thi**, không phải event ID nghiệp vụ. Queue message được retry có thể nhận invocation ID mới. Khi cần idempotency, dùng business event ID ổn định.

### 13.3. Không log dữ liệu nhạy cảm

Không log:

- Function key, connection string, access token.
- Authorization header/cookie.
- Toàn bộ request body có dữ liệu cá nhân.
- `local.settings.json` nguyên văn.
- Runtime object hoặc mọi headers một cách không chọn lọc.

Ưu tiên log function name, invocation ID, correlation ID được phép, trạng thái xử lý và error code.

### 13.4. Điều chỉnh Spring logging

Có thể cấu hình `src/main/resources/application.properties`:

~~~properties
logging.level.root=INFO
logging.level.example.azure=DEBUG
~~~

Không để `DEBUG` rộng trên production nếu log chứa payload hoặc metadata nhạy cảm. Log level local và cloud có thể khác do environment-specific app settings.

## 14. Troubleshooting khi chạy local

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `func` không được nhận diện | Core Tools chưa cài hoặc PATH chưa cập nhật. | `func --version`, `where.exe func`, mở terminal mới. |
| Sai version Core Tools | MSI/npm/Chocolatey cài chồng. | Xem tất cả đường dẫn `func.exe` và chỉ giữ một phương thức. |
| Maven không tìm thấy goal `azure-functions:run` | Thiếu Azure Functions Maven plugin hoặc sai plugin version. | Kiểm `pom.xml` và Maven effective configuration. |
| Host không khởi động | `host.json` sai, port bận hoặc thiếu runtime dependency. | Đọc log startup đầu tiên, kiểm port 7071 và config. |
| Port 7071 đã được dùng | Có một Functions Host khác đang chạy. | Dừng process/terminal host cũ trước khi khởi động. |
| Không thấy function trong danh sách | Annotation/metadata không được plugin sinh. | `@FunctionName`, method public, trigger annotation, package staging. |
| Host thấy function nhưng gọi lỗi Spring | Handler không được Spring quản lý hoặc main class sai. | `@Component`, component scan, `MAIN_CLASS`, adapter. |
| `NoSuchBeanDefinitionException` | Thiếu service/function bean hoặc component scan. | Spring Boot main class và package layout. |
| `FunctionCatalog.lookup(...)` trả null | Sai function bean name/definition hoặc bean không được đăng ký. | Kiểm `@Bean` name, catalog test và dependency versions. |
| `UnsupportedClassVersionError` | JDK compile target cao hơn Java runtime. | `java -version`, `mvn -version`, compiler release và runtime. |
| Worker process không khởi tạo | JAVA_HOME/PATH hoặc dependency/classpath sai. | Xác minh JDK, main class, Azure adapter và package layout. |
| HTTP 404 | Sai route hoặc prefix `/api`. | Dùng URL host in ra, kiểm `host.json` routePrefix và `@HttpTrigger`. |
| HTTP 405 | Gửi sai method. | Đối chiếu methods trong trigger annotation. |
| HTTP 400 | Request body không đúng business contract. | Kiểm body, content type và validation. |
| HTTP 500 | Lỗi nghiệp vụ, conversion, DI hoặc dependency. | Đọc Java stack trace, root cause và function log. |
| HTTP key local không được yêu cầu | Core Tools local không enforce key như cloud. | Đây là khác biệt local; test auth riêng ở Azure. |
| Queue Trigger không chạy | Azurite chưa chạy, queue/connection sai. | Port 10001, queue name, `AzureWebJobsStorage` và host log. |
| Blob Trigger không nhận file | Sai container/path, Blob service chưa chạy. | Port 10000, binding expression, extension và upload target. |
| `UseDevelopmentStorage=true` bị lỗi | Azurite không chạy hoặc emulator endpoint sai. | Khởi động Azurite, kiểm port và settings. |
| Debugger không attach | Debug mode chưa bật hoặc port 5005 bận. | `-DenableDebug`, worker log, host/port và IDE config. |
| Có hai host local cạnh tranh | Terminal/IDE cũ chưa dừng. | Dừng host cũ; chỉ chạy một instance cho project/port. |

### 14.1. Quy trình điều tra theo thứ tự

~~~text
1. Công cụ: java, mvn, func có đúng version/PATH?
2. Project: Azure adapter, Java library và plugin có trong dependency/build?
3. Settings: host.json, local.settings.json, MAIN_CLASS có đúng?
4. Build: Maven/Gradle package thành công và tạo metadata?
5. Host: Core Tools khởi động, Java worker initialized?
6. Discovery: Host liệt kê đúng @FunctionName và trigger?
7. Spring: ApplicationContext/DI/FunctionCatalog khởi tạo?
8. Request/event: route, payload, connection và binding đúng?
9. Business: function output/error mapping đúng?
10. Security: secrets, keys, cloud settings và permissions?
~~~

Không thay đổi hàng loạt plugin/Java version khi chưa biết lỗi nằm ở tầng nào. Ghi lại **lỗi đầu tiên** trong startup log; các lỗi sau có thể chỉ là hậu quả.

## 15. Local test và cloud test khác nhau thế nào?

| Hạng mục | Local Core Tools | Azure staging/cloud |
| --- | --- | --- |
| Functions Host | Host local qua Core Tools. | Host do Azure quản lý. |
| Java worker | Java process trên máy dev. | Runtime Java của Function App/plan. |
| Spring DI | Có thể kiểm tra đầy đủ qua adapter. | Phải xác nhận trên deployment package thật. |
| FunctionCatalog | Test lookup/composition local. | Xác nhận dependency/runtime cùng version trong cloud. |
| HTTP route | Gọi localhost:7071. | Domain Function App, auth/network thật. |
| Function key | Không enforce như cloud trong local workflow thông thường. | Kiểm tra theo authLevel/host policy. |
| Storage | Azurite hoặc dev account. | Azure Storage và IAM/managed identity thật. |
| Service Bus/Event Hubs | Dev resource/emulator tương ứng. | Resource, network và quyền cloud thật. |
| Cold start/scale | Không mô phỏng đầy đủ plan. | Phụ thuộc hosting plan và tải thật. |
| Observability | Terminal/IDE/emulator logs. | Azure Monitor/Application Insights theo config. |
| Secrets | Local settings/dev secrets. | App Settings/Key Vault/managed identity. |

**Local pass không có nghĩa production pass.** Các yếu tố như Java runtime trên Azure, identity, network, scale, binding extension và deployment configuration cần staging smoke tests.

### 15.1. Không dùng local.settings.json làm cấu hình production

Azure Function App dùng **Application Settings** trên cloud. Các setting trong `local.settings.json` không tự động đồng bộ lên cloud theo mặc định. Khi cần đồng bộ, dùng công cụ phù hợp và kiểm tra từng setting trước khi ghi; thao tác fetch có thể ghi đè file local.

### 15.2. Dùng Azure resources thật khi nào?

Một số dịch vụ không có local emulator tương đương. Nếu buộc phải test với Azure dev resource:

- Dùng subscription/resource group riêng được cấp quyền.
- Tách queue/container/topic development khỏi production.
- Dùng identity/credentials quyền tối thiểu.
- Theo dõi chi phí và dữ liệu được tạo/consume.
- Không gửi message test vào hệ thống production.
- Xóa hoặc dọn test data theo quy trình.

## 16. Quy trình làm việc local khuyến nghị

Một chu trình lặp lại:

1. **Kiểm tra môi trường:** `java -version`, `mvn -version`, `func --version`.
2. **Chuẩn bị settings:** `host.json`, `local.settings.json`, Spring properties.
3. **Khởi động Azurite** nếu project dùng Blob/Queue/Table Storage.
4. **Build:** `mvn clean package` hoặc Gradle task tương ứng.
5. **Chạy Host:** `mvn azure-functions:run` hoặc `gradle azureFunctionsRun`.
6. **Kiểm discovery:** đọc danh sách functions/URL từ log startup.
7. **Gọi HTTP:** gửi request hợp lệ và invalid input.
8. **Gửi event:** tạo Queue message hoặc upload Blob khi test non-HTTP trigger.
9. **Debug/log:** attach debugger, đọc host/Java logs, tìm invocation ID.
10. **Dừng host/emulator:** tránh process/port còn chạy khi chuyển project.
11. **Chạy test tự động:** unit, Spring context và integration tests.
12. **Staging smoke test:** chỉ sau khi local behavior ổn định và tài nguyên cloud đã được chuẩn bị.

### 16.1. Script kiểm tra phiên bản trên Windows

Có thể chạy các lệnh sau trước khi bắt đầu:

~~~powershell
java -version
mvn -version
func --version
where.exe func
node --version
az version
~~~

Nếu không dùng npm/Azurite/Azure CLI thì các lệnh tương ứng là tùy chọn. Ghi lại kết quả khi báo lỗi cho nhóm; điều này giúp xác định khác biệt môi trường.

### 16.2. Một host, một project, một cấu hình rõ ràng

Không mở nhiều host trên cùng port, không dùng local settings của project A khi chạy project B, và không để hai phiên bản plugin khác nhau tạo package không nhất quán. Nếu cần nhiều cấu hình, dùng profile/environment tách biệt và test rõ.

## 17. Bài tập thực hành

1. **Cài Core Tools:** cài Core Tools v4 bằng một phương thức trên Windows, chạy `func --version` và `where.exe func`; ghi lại đường dẫn thực tế.
2. **Kiểm JDK/Maven:** xác minh `JAVA_HOME`, `java -version` và `mvn -version` dùng cùng JDK.
3. **Build project Java:** chạy `mvn clean package` hoặc Maven Wrapper, kiểm tra plugin Azure hoàn tất.
4. **Chạy HTTP local:** dùng `azure-functions:run`, gửi POST tới URL host in ra, xác nhận response.
5. **Thử validation:** gửi body rỗng, body sai schema và body hợp lệ; so sánh HTTP 400/200.
6. **Thử Spring DI:** cố ý đổi tên function trong `catalog.lookup(...)`, quan sát startup/fail-fast và sửa lại.
7. **Dùng Azurite:** khởi động Azurite, tạo queue, gửi message và xác minh Queue Trigger.
8. **Timer Trigger:** tạo schedule ngắn trong local, quan sát invocation logs và dừng host đúng cách.
9. **Debug Java:** chạy `-DenableDebug`, attach IDE vào port 5005 và đặt breakpoint trong handler/function bean.
10. **Lỗi port:** chạy một host, thử khởi động host thứ hai, quan sát lỗi rồi dừng instance cũ.
11. **Phân biệt local/cloud:** ghi ra năm thiết lập phải kiểm lại trên Azure staging (runtime, auth, identity, storage, app settings).
12. **Không commit secrets:** kiểm tra `local.settings.json` có nằm trong ignore policy và không chứa thông tin production.

## 18. Câu hỏi tự đánh giá

- Azure Functions Core Tools cung cấp thành phần nào khi chạy local?
- Vì sao `java -jar` hoặc `spring-boot:run` không thay thế Azure Functions Host?
- Với Java, vì sao Maven archetype/Azure Maven plugin thường là workflow phù hợp hơn `func init`/`func new`?
- `host.json` và `local.settings.json` khác nhau ở điểm nào?
- Khi nào cần Azurite và Azurite hỗ trợ những Storage services nào?
- `UseDevelopmentStorage=true` trỏ tới đâu?
- `MAIN_CLASS` trỏ tới Spring Boot application hay Azure handler?
- Tại sao phải xem danh sách functions trong startup output trước khi gọi HTTP?
- URL mặc định thường có port và route prefix nào?
- Vì sao local HTTP function có thể chạy mà không cần function key?
- Khi nào cần dùng `-DenableDebug` và debug port mặc định thường là bao nhiêu?
- Queue Trigger local cần nguồn message và connection như thế nào?
- Tại sao một Spring context test không đủ để chứng minh Azure binding chạy?
- Khi nào local nên kết nối Azure dev resource thật thay vì emulator?
- Những khác biệt nào phải kiểm tra lại trên Azure staging trước production?

## 19. Tài liệu tham khảo chính thức

- [Microsoft Learn — Develop Azure Functions locally by using Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): cài Core Tools, chạy Functions Host, HTTP/non-HTTP triggers, local settings và Java Maven workflow.
- [Microsoft Learn — Code and test Azure Functions locally](https://learn.microsoft.com/en-us/azure/azure-functions/functions-develop-local): local runtime, đồng bộ settings, test HTTP, trigger và storage emulator.
- [Microsoft Learn — Quickstart: Create a Java Function from the command line](https://learn.microsoft.com/en-us/azure/azure-functions/functions-create-first-java-maven): Java JDK, Maven archetype, Core Tools, chạy Maven local và kiểm thử HTTP.
- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): Azure adapter, Spring DI, `@Component` handler, `FunctionCatalog` và Maven/Gradle local run.
- [Microsoft Learn — Install and run the Azurite emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite): cài Azurite bằng npm/Docker/VS Code và cấu hình local endpoints.
- [Microsoft Learn — Use the Azurite emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite): giới hạn và khác biệt giữa Azurite với Azure Storage thật.
- [Microsoft Learn — Azure Functions Java ExecutionContext](https://learn.microsoft.com/en-us/java/api/com.microsoft.azure.functions.executioncontext): invocation ID, function name và logger.
- [Microsoft Learn — Debug Java Azure Functions](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/getting-started-with-spring-cloud-function-in-azure): `azure-functions:run -DenableDebug`, Java worker port 5005 và remote attach.
- [Microsoft Learn — Azure Functions Core Tools reference](https://learn.microsoft.com/en-us/azure/azure-functions/functions-core-tools-reference): `func` commands, host startup và options.

**Kết luận:** Chạy local bằng **Azure Functions Core Tools** giúp kiểm thử ứng dụng trong một Functions Host gần với runtime Azure trước khi triển khai. Với project Spring Cloud Function Java, hãy chuẩn bị đúng JDK/Maven/Core Tools, cấu hình `host.json` và `local.settings.json`, dùng `azure-functions:run` để khởi động host, rồi xác nhận function discovery, HTTP/event trigger, Spring DI và `FunctionCatalog`. Dùng Azurite cho Azure Storage khi phù hợp, debug Java worker khi cần và luôn kiểm tra lại authentication, identity, runtime, settings cùng trigger behavior trên Azure staging trước production.
