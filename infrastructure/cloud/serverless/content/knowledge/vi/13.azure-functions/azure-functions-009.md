# Phát hành function và sử dụng deployment slot khi được hỗ trợ

Azure Functions cho phép triển khai mã theo nhiều cách: ZIP package, package deployment, container image hoặc pipeline CI/CD. Một lần deploy có thể làm host khởi động lại và ảnh hưởng các invocation đang chạy. Với những hosting plan hỗ trợ deployment slot, nhóm có thể triển khai phiên bản mới vào một môi trường staging, kiểm tra ứng dụng rồi chuyển slot đó thành production bằng thao tác swap.

Deployment slot hữu ích cho việc kiểm thử phiên bản mới, làm nóng ứng dụng trước khi nhận traffic và rollback nhanh về phiên bản trước. Tuy nhiên, slot không phải môi trường production độc lập hoàn toàn: các slot thuộc cùng Function App và App Service plan, dùng chung một số tài nguyên và giới hạn; cấu hình nào đi theo code, cấu hình nào ở lại với slot phải được xác định rõ. Swap cũng không bảo đảm mọi invocation đang chạy sẽ được giữ nguyên.

Điều kiện hỗ trợ phụ thuộc hosting plan. Consumption, Premium và Dedicated hỗ trợ slot với số lượng khác nhau; Flex Consumption hiện không hỗ trợ deployment slot; Azure Functions chạy trên Azure Container Apps sử dụng revisions. Vì vậy, trước khi thiết kế release pipeline, hãy xác định hosting plan, hệ điều hành, cách đóng gói và yêu cầu sẵn sàng của ứng dụng.

## 1. Vòng đời phát hành một Function App

Một bản phát hành tốt bắt đầu từ artifact đã được build và kiểm thử, sau đó triển khai vào môi trường kiểm tra, xác minh hành vi rồi mới đưa vào production. Với slot, luồng phổ biến là:

~~~mermaid
flowchart TD
    A["Commit source code"] --> B["Build và test Java project"]
    B --> C["Tạo deployment artifact"]
    C --> D["Deploy vào staging slot"]
    D --> E["Kiểm tra cấu hình và warm-up"]
    E --> F["Smoke test / integration test"]
    F --> G{"Đạt tiêu chí phát hành?"}
    G -->|"Không"| H["Sửa lỗi hoặc deploy artifact mới"]
    H --> D
    G -->|"Có"| I["Swap staging với production"]
    I --> J["Kiểm tra production"]
    J --> K{"Ổn định?"}
    K -->|"Có"| L["Giữ release"]
    K -->|"Không"| M["Swap rollback"]
~~~

Các bước có thể được tự động hóa bằng Azure Pipelines, GitHub Actions hoặc công cụ phát hành khác. Điểm quan trọng là cùng một artifact đã kiểm thử phải được đưa lên staging và sau đó chuyển sang production. Tránh build lại một gói khác ở bước production vì hai môi trường có thể nhận mã khác nhau.

Một Function App có thể chứa nhiều function. Vì vậy, một lần deploy thường thay thế package của cả Function App chứ không chỉ một function riêng lẻ. Nếu các function có lịch phát hành, dependency hoặc ranh giới bảo mật khác nhau, hãy cân nhắc tách chúng thành các Function App riêng.

## 2. Hosting plan nào hỗ trợ deployment slot?

Theo tài liệu Azure Functions hiện hành, số slot được tính cả production slot:

| Hosting option | Số slot (bao gồm production) | Cách phát hành tương ứng |
|---|---:|---|
| Consumption plan | 2: production và một staging | Deployment slot và swap được hỗ trợ |
| Flex Consumption plan | Không hỗ trợ | Dùng site update strategy, có thể cấu hình rolling updates |
| Premium plan | 3 | Deployment slot và swap |
| Dedicated (App Service) plan | 1–20, tùy tier | Deployment slot và swap |
| Azure Container Apps | Không áp dụng slot | Dùng revisions để quản lý phiên bản và traffic |

Số lượng slot thực tế còn phụ thuộc tier và giới hạn dịch vụ của subscription. Hãy kiểm tra quota của plan trước khi tạo slot mới.

Có ba điểm cần nhớ:

- **Flex Consumption:** không có deployment slot. Nếu cần kiểm soát phát hành và giảm downtime, dùng rolling update theo site update strategy của Flex Consumption cùng pipeline kiểm thử.
- **Azure Container Apps:** Function App được phát hành qua container image và revisions. Revision có thể được cấu hình để nhận traffic theo chiến lược của Container Apps; không dùng lệnh swap slot của App Service.
- **Consumption, Premium và Dedicated:** có thể deploy vào slot riêng rồi swap với production. Số lượng slot và khả năng mở rộng phụ thuộc hosting plan.

Không nên chọn hosting plan chỉ vì muốn có slot. Hãy cân nhắc cả thời gian chạy, scale, network, memory, concurrency, chi phí và khả năng vận hành của workload.

## 3. Deployment slot là gì?

Deployment slot là một instance riêng của Function App có hostname riêng. Một Function App luôn có production slot và có thể có một hoặc nhiều slot khác như staging, test hoặc canary nếu plan hỗ trợ.

Ví dụ hostname:

~~~text
orders-api.azurewebsites.net
orders-api-staging.azurewebsites.net
~~~

Mỗi slot có thể nhận deployment và được kiểm tra qua endpoint riêng. Khi swap staging với production, Azure thay đổi slot nào được xem là production và chuyển routing theo quy trình swap.

Slot giúp:

- Kiểm tra phiên bản mới trên endpoint staging trước khi chuyển traffic.
- Khởi động ứng dụng và làm nóng một số thành phần trước khi phát hành.
- Kiểm tra cấu hình theo môi trường.
- Giữ phiên bản production trước đó trong slot còn lại để có thể rollback nhanh.
- Thực hiện release có kiểm soát từ pipeline.

Slot vẫn thuộc cùng Function App và App Service plan. Các slot chia sẻ plan capacity và chịu ảnh hưởng từ cấu hình, quota, networking và tài nguyên nền tảng liên quan. Slot không tương đương một subscription hoặc một ranh giới bảo mật độc lập. Nếu staging cần cô lập dữ liệu hoặc quyền truy cập nghiêm ngặt, phải thiết kế identity, network, storage và resource permissions phù hợp.

## 4. Tạo và quản lý slot

Có thể tạo slot bằng Azure Portal hoặc Azure CLI. Ví dụ tạo slot tên staging:

~~~bash
az functionapp deployment slot create \
  --name orders-api \
  --resource-group rg-orders-prod \
  --slot staging
~~~

Sau khi tạo, kiểm tra slot và hostname:

~~~bash
az functionapp deployment slot list \
  --name orders-api \
  --resource-group rg-orders-prod \
  --output table
~~~

Slot mới cần được cấu hình trước khi nhận traffic hoặc xử lý event. Không giả định rằng mọi setting được sao chép hoặc tách biệt theo đúng mong muốn của nhóm. Khi tạo slot, Azure có thể khởi tạo một số setting dựa trên production; hãy rà soát toàn bộ cấu hình của slot trước khi deploy.

Các thao tác quản trị thường gặp:

- Tạo slot cho staging hoặc test.
- Cập nhật app settings và connection strings.
- Deploy package vào slot.
- Kiểm tra slot bằng hostname riêng.
- Swap slot với production.
- Swap ngược để rollback.
- Xóa slot khi không còn cần.

Nên dùng tên slot phản ánh mục đích và môi trường. Tránh tạo nhiều slot tạm mà không có quy trình dọn dẹp, vì chúng vẫn tiêu thụ tài nguyên và làm tăng độ phức tạp vận hành.

## 5. Đóng gói ứng dụng Java cho Azure Functions

Azure Functions Java project thường được build bằng Maven. Plugin Azure Functions tạo cấu trúc sẵn sàng triển khai trong thư mục đích, thường là:

~~~text
target/
  azure-functions/
    orders-api/
      host.json
      orders-api.jar
      FunctionName/
        function.json
      lib/
        dependency-1.jar
        dependency-2.jar
~~~

Thư mục Function App cần được đóng gói sao cho host.json nằm ở gốc của package sau khi giải nén. Nếu ZIP chứa thêm một thư mục cha, runtime có thể không tìm thấy host.json hoặc metadata của function.

Một quy trình build thường dùng:

~~~bash
mvn -B clean verify
~~~

Với Azure Functions Maven plugin, lệnh deploy tiêu chuẩn có dạng:

~~~bash
mvn azure-functions:deploy
~~~

Lệnh Maven deploy phù hợp để triển khai trực tiếp Function App theo cấu hình trong pom.xml. Khi pipeline cần phát hành qua slot, hãy xác nhận phương thức deploy và phiên bản plugin hỗ trợ slot trong dự án; có thể dùng Azure CLI ZIP deployment hoặc task CI/CD có tham số slot rõ ràng. Không giả định mọi phiên bản Maven plugin đều có cùng khả năng chọn slot.

Nếu dùng ZIP deployment, hãy tạo archive từ nội dung của thư mục output, để host.json nằm ngay ở root. Ví dụ trên PowerShell:

~~~powershell
$functionOutput = "target/azure-functions/orders-api"
Compress-Archive -Path "$functionOutput/*" -DestinationPath "orders-api.zip" -Force
~~~

Trước khi upload, kiểm tra nội dung ZIP. Package cần có host.json, JAR của ứng dụng, function metadata và dependency mà runtime cần. Không đóng gói toàn bộ thư mục source nếu cấu trúc đó không phải deployment output đã build.

## 6. Chọn deployment technology theo hosting plan

Cách deploy khác nhau theo hosting plan và hệ điều hành. Các lựa chọn chính:

| Hosting plan | Deployment technology phổ biến | Ghi chú |
|---|---|---|
| Flex Consumption | Managed package deployment | Package deployment là phương thức code deployment được hỗ trợ; ứng dụng chạy trực tiếp từ package |
| Consumption | ZIP deployment; một số trường hợp Linux legacy dùng external package URL | Kiểm tra hệ điều hành và hướng dẫn hiện hành của plan |
| Premium | ZIP deployment hoặc container image trên Linux | ZIP deployment là lựa chọn phổ biến cho code |
| Dedicated | ZIP deployment hoặc container image trên Linux | Có thể dùng slot nếu tier hỗ trợ |
| Azure Container Apps | Container image | Dùng revision thay cho slot |

Với ZIP deployment trên Consumption, Premium và Dedicated, có thể cấu hình ứng dụng chạy trực tiếp từ package bằng setting WEBSITE_RUN_FROM_PACKAGE=1 ở các plan/hệ điều hành được hỗ trợ. Cách này mount package thành thư mục wwwroot chỉ đọc, giúp tránh một số vấn đề khóa file và làm rõ nội dung đang chạy.

Flex Consumption dùng managed package deployment và chạy từ package theo mặc định; không thêm WEBSITE_RUN_FROM_PACKAGE theo hướng dẫn của ZIP deployment truyền thống. Flex cũng không hỗ trợ slot, vì vậy cần dùng release strategy dành riêng cho plan này.

Azure Container Apps triển khai image mới thành revision. Hãy dùng cơ chế traffic splitting và revision management của Container Apps nếu muốn phát hành canary hoặc rollback.

## 7. Deploy Java package vào staging slot

Với slot được hỗ trợ, có thể dùng Azure CLI ZIP deployment để đẩy artifact vào staging. Ví dụ:

~~~bash
az functionapp deployment source config-zip \
  --resource-group rg-orders-prod \
  --name orders-api \
  --slot staging \
  --src orders-api.zip
~~~

Lệnh trên triển khai ZIP vào slot staging. Tài khoản Azure CLI cần được xác thực và có quyền deploy vào Function App. Package phải tương thích runtime, operating system và architecture của Function App.

Sau khi deploy:

1. Kiểm tra deployment command hoàn tất thành công.
2. Kiểm tra Function App staging khởi động và host nhận diện đúng các function.
3. Kiểm tra app settings, connection strings và managed identity.
4. Gọi HTTP endpoint của staging nếu có HTTP trigger.
5. Chạy smoke test với dữ liệu kiểm thử.
6. Kiểm tra log và dependency connectivity.
7. Chỉ swap khi các tiêu chí phát hành đạt yêu cầu.

Đối với GitHub Actions, Azure Functions deploy action hỗ trợ tham số slot-name trên các hosting plan có slot. Đối với Azure Pipelines, task AzureFunctionApp có thể chỉ định deployment slot. Flex Consumption không hỗ trợ slot-name; pipeline phải dùng package deployment và site update strategy của Flex.

## 8. Cấu hình slot-specific settings và sticky settings

Một trong những lỗi phổ biến nhất khi swap là nhầm lẫn setting nào đi theo code và setting nào phải ở lại với môi trường.

**Sticky setting** (còn gọi là deployment slot setting) là setting được giữ nguyên với slot trong quá trình swap. Ví dụ, staging cần dùng database, storage account hoặc queue thử nghiệm; production cần dùng tài nguyên production. Những setting này phải được đánh dấu là slot-specific để giá trị không bị đổi chéo khi swap.

Các setting thường cần xem xét:

- Connection string và endpoint của database.
- Storage account hoặc container riêng theo môi trường.
- Queue, topic, event hub hoặc subscription của staging.
- Secret reference hoặc cấu hình dependency theo môi trường.
- Feature flag dành riêng cho staging.
- Cờ tắt trigger trong staging.
- Setting chỉ định môi trường hoặc telemetry destination.

Ví dụ, cấu hình app settings cho staging:

~~~bash
az functionapp config appsettings set \
  --name orders-api \
  --resource-group rg-orders-prod \
  --slot staging \
  --slot-settings \
    "APP_ENV=staging" \
    "ORDERS_TABLE=orders-staging" \
    "AzureWebJobs.QueueTrigger.Disabled=true"
~~~

Tùy CLI version, có thể cần truyền danh sách setting theo cú pháp shell phù hợp. Hãy kiểm tra kết quả sau khi cập nhật và bảo đảm setting được đánh dấu là slot-specific.

Nếu một setting cần tồn tại ở cả staging và production, nên giữ cùng tên ở hai slot nhưng gán giá trị riêng. Điều này giúp code không gặp lỗi thiếu setting sau swap. Không đưa secret trực tiếp vào file pipeline hoặc source control; dùng Key Vault reference hoặc cơ chế secret management phù hợp.

Không phải mọi cấu hình đều có thể đánh dấu sticky. Một số thuộc tính nền tảng như hostname, publishing endpoint, private certificate, IP restriction, diagnostic setting, CORS, private endpoint hoặc scale setting được giữ riêng theo slot theo quy tắc của App Service. Virtual network integration và một số cấu hình mạng khác cũng có semantics riêng. Hãy kiểm tra danh sách swap/non-swap hiện hành trước khi thiết kế.

## 9. Ngăn staging xử lý event production

Đối với HTTP trigger, staging có hostname riêng và có thể được gọi trực tiếp trong quá trình kiểm thử. Với queue trigger, timer trigger hoặc event trigger, staging có thể khởi chạy listener và nhận sự kiện nếu được cấu hình kết nối tới cùng nguồn production.

Nếu cả staging và production cùng xử lý một queue hoặc subscription, cùng một event có thể bị xử lý bởi hai slot hoặc bị lấy khỏi nguồn bởi slot không mong muốn. Điều này có thể tạo side effect trùng, dữ liệu thử nghiệm lẫn vào production hoặc mất quyền kiểm soát thứ tự xử lý.

Các cách giảm rủi ro:

- Dùng queue, topic, storage hoặc database riêng cho staging.
- Đánh dấu setting kết nối nguồn event là sticky.
- Tắt các function không cần chạy trong staging bằng setting slot-specific.
- Chỉ bật trigger trong staging khi kiểm thử có chủ đích.
- Dùng idempotency và conditional update ở consumer.
- Kiểm tra quyền của managed identity từng slot.
- Kiểm thử việc swap với event source và binding trước khi production.

Azure Functions hỗ trợ setting theo function để vô hiệu hóa function, ví dụ:

~~~text
AzureWebJobs.QueueTrigger.Disabled=true
~~~

Hãy tạo setting này như một slot-specific setting trên staging nếu muốn trigger tiếp tục bị tắt trong staging sau swap. Khi slot staging được swap thành production, giá trị sticky ở lại slot; vì vậy cần chuẩn bị giá trị đúng cho cả hai slot và kiểm tra trạng thái trigger sau phát hành.

Đối với Timer Trigger, đặc biệt cẩn thận để không có hai host cùng thực hiện công việc định kỳ ngoài ý muốn. Dùng cơ chế host lock của nền tảng đúng cách, giữ cấu hình riêng theo slot và thiết kế tác vụ idempotent.

## 10. Warm-up và kiểm tra readiness trước khi swap

Slot cho phép triển khai phiên bản mới trước khi chuyển traffic. Tuy nhiên, việc package đã upload xong không chứng minh ứng dụng đã sẵn sàng. Java function có thể cần khởi động JVM, nạp class, tạo dependency, đọc cấu hình và thiết lập kết nối.

Hãy chuẩn bị một health endpoint hoặc cơ chế kiểm tra phù hợp. Với HTTP function, endpoint readiness có thể xác nhận:

- Function host đã khởi động.
- Cấu hình bắt buộc đã được đọc.
- Dependency quan trọng có thể kết nối.
- Database schema tương thích.
- Secret reference hoặc managed identity hoạt động.
- Ứng dụng không đang ở trạng thái bảo trì.

App Service hỗ trợ cấu hình đường dẫn warm-up cho slot swap bằng các app settings như:

~~~text
WEBSITE_SWAP_WARMUP_PING_PATH=/api/health
WEBSITE_SWAP_WARMUP_PING_STATUSES=200,202
~~~

Đường dẫn phải trả về status được chấp nhận. Nếu endpoint yêu cầu function key hoặc xác thực mà warm-up request không thể cung cấp credential, việc warm-up có thể thất bại. Hãy thiết kế endpoint kiểm tra an toàn, không tiết lộ thông tin nhạy cảm và chỉ trả trạng thái readiness cần thiết.

Warm-up giảm nguy cơ chuyển traffic tới instance chưa sẵn sàng, nhưng không thay thế smoke test và không biến slot swap thành bảo đảm zero downtime.

## 11. Swap staging với production

Khi staging đã được kiểm tra, thực hiện swap để chuyển phiên bản mới vào production:

~~~bash
az functionapp deployment slot swap \
  --name orders-api \
  --resource-group rg-orders-prod \
  --slot staging \
  --target-slot production
~~~

Trong quá trình swap, Azure áp dụng cấu hình theo quy tắc slot, chuẩn bị và khởi động instance của source slot với các setting cần thiết, sau đó chuyển routing khi quá trình sẵn sàng đáp ứng điều kiện. Sau swap, staging thường giữ phiên bản đã từng chạy ở production; điều này hữu ích cho rollback.

Trước khi bắt đầu, kiểm tra:

- Production là target slot.
- App settings và connection strings được phân loại sticky đúng.
- Event source và binding trỏ tới đúng tài nguyên.
- Function không mong muốn trong staging đã được disable.
- Database migration tương thích với phiên bản cũ và mới.
- Warm-up endpoint trả status hợp lệ.
- Monitoring và rollback plan đã sẵn sàng.

Swap có thể ảnh hưởng invocation đang chạy. Azure Functions documentation cảnh báo slot swap không bảo đảm zero downtime; function đang thực thi có thể bị kết thúc và ứng dụng scale có thể suy giảm availability trong thời gian chuyển đổi. Vì vậy, function cần stateless, idempotent và có khả năng chịu việc invocation bị retry.

## 12. Rollback sau khi phát hành

Nếu phiên bản mới gây lỗi sau swap, có thể swap ngược staging với production để đưa phiên bản trước trở lại production:

~~~bash
az functionapp deployment slot swap \
  --name orders-api \
  --resource-group rg-orders-prod \
  --slot staging \
  --target-slot production
~~~

Lệnh rollback dùng cùng thao tác swap theo hướng staging sang production vì sau lần swap đầu, staging đang giữ phiên bản cũ. Trước khi rollback, xác minh slot nào đang chứa phiên bản cần khôi phục.

Rollback code không tự động rollback dữ liệu. Nếu release đã chạy database migration không tương thích, đổi code về phiên bản trước có thể làm ứng dụng lỗi nặng hơn. Hãy dùng chiến lược expand/contract:

1. Thêm schema hoặc field mới theo cách tương thích ngược.
2. Deploy code có thể đọc cả định dạng cũ và mới.
3. Chuyển traffic và xác minh.
4. Chuyển dữ liệu hoặc ngừng dùng schema cũ.
5. Chỉ xóa cấu trúc cũ sau khi không còn phiên bản nào cần nó.

Giữ artifact đã phát hành trong kho artifact của CI/CD. Slot không phải nơi lưu lịch sử release lâu dài; deployment mới có thể thay thế nội dung trong slot. Artifact có version, checksum và metadata build giúp tái tạo chính xác bản cần rollback.

## 13. Những giới hạn và rủi ro của slot swap

Slot giúp phát hành có kiểm soát nhưng có một số giới hạn cần tính đến:

- **Không bảo đảm zero downtime:** invocation đang chạy có thể bị kết thúc trong lúc swap.
- **Chia sẻ capacity:** các slot cùng dùng App Service plan capacity; staging test tải lớn có thể ảnh hưởng production.
- **Trigger chạy ngoài ý muốn:** staging có thể nhận event nếu cấu hình nguồn không được tách hoặc disable.
- **Sticky settings sai:** connection string hoặc queue có thể bị đổi chéo môi trường.
- **Database schema không tương thích:** rollback code không khôi phục schema.
- **Secret và key behavior:** một số cấu hình secret storage có hành vi đặc biệt khi swap. Ví dụ, swap có thể reset function keys nếu app dùng AzureWebJobsSecretStorageType=files.
- **Storage bảo mật:** slot swap có thể thất bại trong một số cấu hình storage account được bảo vệ dùng làm AzureWebJobsStorage; cần kiểm tra tài liệu và diagnostic tương ứng.
- **Tên Function App:** Microsoft khuyến nghị giữ tên Function App ngắn hơn 32 ký tự để tránh host ID collision trong một số tình huống.
- **Cấu hình không swap:** managed identity, private endpoint, IP restrictions và một số network/diagnostic settings có quy tắc riêng.

Đừng coi staging slot là bản sao an toàn tuyệt đối của production. Cần rà soát quyền truy cập, dữ liệu, trigger, network và cấu hình trước khi cho phép kiểm thử.

## 14. Tự động hóa release bằng CI/CD

Pipeline phát hành nên có các stage rõ ràng:

1. Checkout source và xác định commit.
2. Build Java bằng Maven.
3. Chạy unit test và integration test phù hợp.
4. Tạo package và lưu artifact có version.
5. Deploy artifact vào staging slot.
6. Cập nhật slot-specific settings nếu pipeline quản lý chúng.
7. Chạy smoke test và kiểm tra readiness.
8. Yêu cầu approval nếu release policy cần.
9. Swap staging với production.
10. Kiểm tra health, errors, latency và business metrics.
11. Rollback nếu tiêu chí sau phát hành không đạt.

Ví dụ Azure Pipelines rút gọn cho deploy vào slot và swap:

~~~yaml
steps:
  - task: AzureFunctionApp@2
    displayName: Deploy Java Function to staging
    inputs:
      azureSubscription: $(AZURE_SERVICE_CONNECTION)
      appType: functionAppLinux
      appName: orders-api
      package: $(Pipeline.Workspace)/drop/orders-api.zip
      deployToSlotOrASE: true
      resourceGroupName: rg-orders-prod
      slotName: staging

  - script: |
      echo "Run smoke tests against the staging hostname here"
    displayName: Validate staging

  - task: AzureAppServiceManage@0
    displayName: Swap staging into production
    inputs:
      azureSubscription: $(AZURE_SERVICE_CONNECTION)
      WebAppName: orders-api
      ResourceGroupName: rg-orders-prod
      SourceSlot: staging
      SwapWithProduction: true
~~~

Đây là skeleton pipeline; cần cấu hình service connection, quyền Azure Resource Manager, package artifact và test command theo repository. Task AzureFunctionApp hỗ trợ slot trên các hosting plan có deployment slot. Không dùng slot task cho Flex Consumption.

Với GitHub Actions, Azure Functions deploy action có tham số slot-name cho các plan hỗ trợ slot. Nên dùng workload identity federation/OIDC với azure/login thay vì lưu publish profile dài hạn khi môi trường hỗ trợ. Không commit credential vào workflow.

## 15. Cấu hình IaC cho deployment slot

Slot nên được quản lý cùng Function App bằng Bicep hoặc ARM template. Resource slot sử dụng loại tài nguyên Microsoft.Web/sites/slots. Ví dụ rút gọn:

~~~bicep
resource functionApp 'Microsoft.Web/sites@2022-09-01' existing = {
  name: 'orders-api'
}

resource stagingSlot 'Microsoft.Web/sites/slots@2022-09-01' = {
  parent: functionApp
  name: 'staging'
  location: resourceGroup().location
  properties: {
    serverFarmId: functionApp.properties.serverFarmId
  }
}
~~~

Ví dụ chỉ minh họa quan hệ tài nguyên. Template thực tế cần xác định cấu hình runtime, app settings, identity, networking và dependency theo API version được hỗ trợ. Không tự đặt WEBSITE_CONTENTSHARE trong slot definition nếu tài liệu platform yêu cầu quá trình tạo slot tự sinh setting này.

Với app settings cần sticky, ARM/Bicep có thể biểu diễn slot setting bằng thuộc tính slotSetting trong cấu trúc app settings theo schema tương ứng. Hãy quản lý cùng lúc cả giá trị của staging và production để code luôn thấy các key cần thiết.

IaC giúp tránh cấu hình thủ công bị lệch giữa môi trường. Tuy nhiên, cần kiểm tra deployment diff vì thay đổi cấu hình slot có thể restart app hoặc làm thay đổi hành vi trigger.

## 16. Chiến lược phát hành khi không có slot

Nếu dùng Flex Consumption, không có deployment slot. Có thể kiểm soát phát hành bằng các phương pháp phù hợp với plan:

- Dùng package deployment được quản lý của Flex Consumption.
- Build artifact bất biến và lưu trong pipeline.
- Dùng rolling update site update strategy theo hướng dẫn của Flex Consumption.
- Chạy kiểm thử trước deploy và xác minh sau deploy.
- Thiết kế function stateless, idempotent và chịu retry.
- Giữ database schema tương thích ngược để có thể phát hành phiên bản mới an toàn.
- Có kế hoạch phục hồi package trước đó theo hướng dẫn của Flex Consumption.

Với Azure Container Apps, dùng revisions. Có thể triển khai revision mới, kiểm tra revision và điều chỉnh traffic giữa revisions theo cấu hình Container Apps. Đây là mô hình phát hành riêng; không dùng slot swap của App Service.

Nếu yêu cầu của workload là canary traffic splitting, hãy so sánh revision-based rollout, slot swap và API Management/front-door routing theo hosting plan. Chọn chiến lược dựa trên khả năng hỗ trợ thực tế của dịch vụ, không chỉ dựa vào tên gọi “staging”.

## 17. Quan sát release và xác định thời điểm rollback

Một deployment có thể thành công về mặt kỹ thuật nhưng thất bại về nghiệp vụ. Chỉ kiểm tra trạng thái deploy không đủ. Hãy quan sát trước, trong và sau swap.

Các tín hiệu nên theo dõi:

- Deployment status và log của build/deploy task.
- Function host startup và function indexing errors.
- Invocation count, error count, duration và timeout.
- HTTP 4xx/5xx, latency p50/p95/p99.
- Queue age, retry, poison message hoặc dead-letter count.
- Database connection failures và dependency latency.
- Application Insights traces/exceptions.
- Business metrics như đơn hàng tạo thành công, job hoàn tất và duplicate event bị chặn.

Định nghĩa tiêu chí rollback trước khi phát hành, ví dụ error rate tăng vượt ngưỡng, health check thất bại, queue backlog tăng nhanh hoặc business success rate giảm. Rollback nên là thao tác pipeline có log và approval theo chính sách tổ chức.

Dùng deployment ID, commit SHA, package version và slot name trong telemetry để xác định invocation chạy từ release nào. Tránh log secret, token hoặc payload nhạy cảm chỉ để chẩn đoán.

## 18. Checklist phát hành Azure Functions production

Trước khi deploy, hãy kiểm tra:

1. Hosting plan có hỗ trợ slot không? Nếu không, release strategy thay thế là gì?
2. Số slot còn khả dụng theo tier và quota chưa?
3. Java version, Functions runtime và package có tương thích không?
4. ZIP có host.json ở root và chứa đầy đủ JAR, function metadata, dependency không?
5. Artifact có được build một lần và giữ lại để rollback không?
6. Staging dùng đúng database, storage, queue và secret của môi trường staging không?
7. App settings và connection strings cần sticky đã được đánh dấu chưa?
8. Trigger không mong muốn trong staging đã được disable chưa?
9. Managed identity và quyền truy cập của từng slot đã được kiểm tra chưa?
10. Health/warm-up endpoint có trả status hợp lệ không?
11. Smoke test có kiểm tra cả HTTP và các dependency quan trọng không?
12. Database migration có tương thích với code cũ và mới không?
13. Invocation đang chạy có thể bị kết thúc trong swap không, và handler có chịu được không?
14. Có tiêu chí rõ ràng để swap và rollback không?
15. Pipeline có theo dõi error rate, latency, queue age và business metrics sau deploy không?
16. Với Flex Consumption, rolling update đã được cấu hình thay cho slot chưa?
17. Với Azure Container Apps, revision và traffic configuration đã được kiểm thử chưa?

## Tài liệu tham khảo

- [Azure Functions deployment slots](https://learn.microsoft.com/azure/azure-functions/functions-deployment-slots)
- [Deployment technologies in Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-deployment-technologies)
- [Package-based deployment for Azure Functions](https://learn.microsoft.com/azure/azure-functions/deployment-zip-push)
- [Continuous deployment for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-continuous-deployment)
- [Java developer reference for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-java)
- [Set up staging environments in Azure App Service](https://learn.microsoft.com/azure/app-service/deploy-staging-slots)

## Kết luận

Phát hành Azure Functions cần chọn deployment technology theo hosting plan, build package đúng cấu trúc, kiểm thử artifact và tự động hóa release bằng CI/CD. Với Consumption, Premium và Dedicated, deployment slot cho phép đưa phiên bản mới vào staging, kiểm tra, warm-up và swap sang production. Sticky settings giúp giữ connection, storage, queue và cấu hình môi trường đúng slot; trigger staging cần được kiểm soát để tránh xử lý event production ngoài ý muốn.

Slot không bảo đảm zero downtime và không thay thế thiết kế function stateless, idempotent hoặc database migration tương thích ngược. Flex Consumption dùng package deployment và rolling updates thay cho slot; Azure Container Apps dùng revisions. Khi pipeline lưu artifact bất biến, kiểm tra readiness, theo dõi telemetry và có rollback plan, nhóm có thể phát hành Java Function App có kiểm soát và phục hồi nhanh hơn khi phiên bản mới gặp lỗi.

