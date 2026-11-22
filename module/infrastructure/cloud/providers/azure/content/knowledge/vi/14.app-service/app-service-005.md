# Deployment slot, warm-up và swap phiên bản

Một ứng dụng web vận hành trên Azure App Service thường phải triển khai phiên bản mới nhiều lần. Nếu triển khai thẳng mã nguồn mới lên ứng dụng đang phục vụ khách hàng, tiến trình khởi động lại, nạp thư viện, kết nối cơ sở dữ liệu hoặc tải cấu hình có thể tạo ra một khoảng gián đoạn. Ngay cả khi ứng dụng khởi động thành công, phiên bản mới vẫn có thể lỗi do cấu hình production khác môi trường phát triển.

**Deployment slots** cho phép chuẩn bị phiên bản mới trong một môi trường triển khai riêng thuộc cùng App Service, kiểm tra và làm nóng ứng dụng (warm-up), rồi **swap** phiên bản đó vào production. Đây là cơ chế hữu ích để giảm rủi ro phát hành và hỗ trợ hoàn tác nhanh ở tầng mã ứng dụng. Tuy nhiên, swap **không tự hoàn tác** thay đổi database, message queue, dữ liệu người dùng hoặc các hệ thống bên ngoài.

Trong mô-đun CLOUD_PROVIDERS_AZURE, bài học này kết nối Azure App Service với subscription, resource group, Microsoft Entra ID, networking, Key Vault, monitoring và kiểm soát chi phí. Mục tiêu là triển khai **có thể kiểm chứng và phục hồi**, không chỉ chạy thành công một lệnh swap.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích deployment slot, slot hostname, production slot và staging slot.
2. Phân biệt nội dung/cấu hình di chuyển khi swap với cấu hình **slot-specific** (sticky).
3. Mô tả các bước swap, warm-up, swap with preview và hành vi restart ở các slot.
4. Thiết kế health/readiness endpoint và cấu hình warm-up cho ứng dụng.
5. Thực hành tạo slot, triển khai staging, kiểm tra, swap và rollback bằng Azure CLI.
6. Tránh rủi ro khi database migration, background jobs, queue consumers, session và secret tương tác với quá trình swap.
7. Xây dựng pipeline phát hành có approval, telemetry, rollback và giám sát chi phí.

Nền tảng cần biết: App Service Plan, App Service Web App, HTTP/HTTPS, CI/CD, environment variables, Azure RBAC, Azure Monitor và khái niệm deployment artifact. Ví dụ CLI dùng tên tài nguyên minh họa, **không được tự động thực thi** và có thể phát sinh chi phí khi tạo tài nguyên thật.

## 2. Vì sao không triển khai trực tiếp lên production?

Giả sử ứng dụng orders-api chạy trên Azure App Service tại Đông Nam Á. Một release cần đổi Java code, thêm biến môi trường và cập nhật API giao tiếp database. Nếu pipeline triển khai trực tiếp vào production:

- App Service có thể restart hoặc tái tạo worker khi nhận code/config mới.
- Java runtime/JIT, dependency injection, kết nối database, cache và thư viện có thể cần thời gian khởi động.
- Nếu start lỗi, production bị ảnh hưởng ngay khi chưa kịp chạy smoke test.
- Rollback khó nếu artifact trước đó không còn hoặc schema database đã bị thay đổi không tương thích.
- Các thay đổi cấu hình nhầm môi trường có thể khiến ứng dụng dùng credential hoặc endpoint sai.

Deployment slot giúp tách bước **đưa artifact vào môi trường** khỏi bước **cho người dùng thật nhận phiên bản mới**. Staging có URL riêng để kiểm thử. Swap được thiết kế để chuẩn bị phiên bản ở slot nguồn rồi chuyển sang slot đích có kiểm soát.

Lợi ích quan trọng: thay vì đợi ứng dụng cold start sau khi đã chuyển production traffic, App Service có thể warm up slot nguồn với cấu hình phù hợp trước khi hoàn tất đổi phiên bản.

**Giới hạn:** không nên hiểu swap là giao dịch nguyên tử cho toàn bộ hệ thống phân tán. Connection đang mở, background processing, database migrations, message queues, cấu hình ngoài App Service và session do ứng dụng tự quản lý phải được tính riêng.

## 3. Deployment slot trong App Service

### 3.1. Cấu trúc logic

Một App Service Web App có slot production mặc định và có thể thêm các slot đặt tên như staging hoặc preprod.

~~~mermaid
flowchart TB
    U["Người dùng / client"] --> P["production<br/>orders-web.azurewebsites.net"]
    T["QA / pipeline kiểm thử"] --> S["staging<br/>orders-web-staging.azurewebsites.net"]
    P --> D["App Service Plan<br/>compute chung"]
    S --> D
    S -. "Sau kiểm thử: warm-up và swap" .-> P
~~~

Ví dụ cấu trúc:

~~~text
Subscription: sub-commerce-prod
Resource group: rg-orders-prod
App Service Plan: asp-orders-prod
Web App: orders-web
  ├── production (slot mặc định)
  │   └── https://orders-web.azurewebsites.net
  └── staging
      └── https://orders-web-staging.azurewebsites.net
~~~

Tên host trên chỉ là minh họa; tên web app phải được cấp phát hợp lệ và URL thật cần lấy từ Azure.

**Production cũng là một slot.** Slot production không dùng tên staging/preprod nhưng là đích đặc biệt trong thao tác swap. Các slot thuộc cùng một Web App, chia sẻ App Service Plan và nguồn compute của plan đó. Mỗi slot là một ứng dụng sống, có hostname và cấu hình riêng theo cơ chế App Service.

### 3.2. Điều kiện hỗ trợ

- Deployment slots có trên những **App Service Plan tiers được hỗ trợ**, điển hình Standard, Premium hoặc Isolated; Free/Shared/Basic không đáp ứng cùng khả năng.
- Số lượng slot tối đa tùy tier và giới hạn dịch vụ hiện hành.
- Một slot staging tiêu thụ tài nguyên compute của App Service Plan như các ứng dụng hoạt động khác, dù không có lưu lượng người dùng production.
- Các slot cùng web app không phải hai region độc lập hoặc hai vùng lỗi hoàn toàn tách biệt.
- Slot không thay thế deployment vào App Service Plan khác, ứng dụng khác hoặc region khác; những trường hợp đó cần thiết kế routing/blue-green ở cấp ngoài.

Kiểm tra tier/region và khả năng deployment slots trước khi tạo. Không dùng một bộ lệnh từ Premium áp trực tiếp cho app đang nằm trên Basic nếu chưa nâng plan.

### 3.3. Các khái niệm dễ nhầm

| Khái niệm | Vai trò | Điều không nên suy ra |
|---|---|---|
| Slot | Môi trường chạy ứng dụng trong một Web App | Không phải một resource group/region riêng |
| Production slot | Điểm nhận lưu lượng khách hàng theo định tuyến production | Không nhất thiết có quyền hạn mạng/data khác staging nếu chưa cấu hình |
| Staging slot | Nơi đưa và kiểm tra release mới | Không mặc nhiên cô lập khỏi tài nguyên production |
| Slot hostname | Địa chỉ URL riêng để truy cập slot | Không tự động là private URL hoặc chỉ QA xem được |
| Swap | Thao tác hoán đổi những phần được thiết kế để swap giữa source và target | Không đồng nghĩa hoán đổi mọi cấu hình, secret, DNS và database |
| Sticky setting | App setting/connection string được đánh dấu là deployment slot setting | Không nên dùng để suy ra toàn bộ hành vi mọi cấu hình Azure |
| Warm-up | Giai đoạn khởi động và kiểm tra khả năng phục vụ trước khi đưa traffic mới | Một GET 200 không chứng minh toàn bộ workflow nghiệp vụ đều đúng |
| Rollback bằng swap ngược | Đưa code/config phiên bản trước trở lại production khi phù hợp | Không tự hoàn tác thay đổi ngoài App Service |

## 4. Cái gì được swap và cái gì gắn với slot?

Đây là phần quan trọng nhất để tránh triển khai nhầm cấu hình và dữ liệu.

### 4.1. Nội dung/cấu hình có thể được swap

Khi swap giữa staging và production, App Service hoán đổi **nội dung và một số cấu hình không được đánh dấu sticky** theo quy tắc dịch vụ. Tùy platform/feature, những phần liên quan có thể gồm:

- Code hoặc deployment artifact của ứng dụng.
- Những app settings và connection strings **không đánh dấu deployment slot setting**.
- Một số cấu hình ứng dụng có tính di động với phiên bản theo danh mục tính năng App Service hỗ trợ.

Không được giả định toàn bộ thiết lập trong Portal đều được hoán đổi. Cơ chế swap có bảng cấu hình hoán đổi và cấu hình giữ nguyên tại slot theo tài liệu hiện hành; các tính năng như authentication, custom domains, certificates, network integration, managed identity, health check hoặc các chính sách ở resource khác cần được đánh giá riêng.

### 4.2. Sticky settings

Những giá trị cần giữ tại môi trường có thể được đánh dấu **Deployment slot setting**. Ví dụ:

~~~text
production:
  APP_ENV=production
  ORDERS_DB_ENDPOINT=<production-db>
  PAYMENT_MODE=live

staging:
  APP_ENV=staging
  ORDERS_DB_ENDPOINT=<staging-db>
  PAYMENT_MODE=sandbox
~~~

Nếu đánh dấu slot-specific, giá trị được quản lý như cấu hình riêng của slot theo quy tắc App Service, thay vì chỉ theo artifact khi đổi phiên bản. Điều này rất quan trọng với database connection, API key, secret reference và chế độ nghiệp vụ.

**Không phải mọi thông số đều có tùy chọn sticky.** Danh sách các setting tự gắn với slot, setting có thể swap và các hành vi đặc biệt phụ thuộc sản phẩm. Hãy kiểm tra bảng chính thức thay vì dựa hoàn toàn vào trực giác.

### 4.3. Bẫy quan trọng: warm-up có thể chạy với cấu hình của slot đích

Trong giai đoạn chuẩn bị swap, App Service có thể **áp dụng cấu hình của target slot lên source slot, restart các instance và warm-up** trước khi hoàn tất thay đổi lưu lượng. Vì vậy, không nên nghĩ rằng một ứng dụng đang nằm ở staging sẽ **chỉ** dùng database test cho tới giây cuối cùng.

Ví dụ:

- Source = staging có artifact v2.
- Target = production đang chạy artifact v1.
- Khi chuẩn bị swap, v2 có thể được khởi động/warm-up với một số cấu hình target production theo quy trình dịch vụ.
- Nếu startup code tự chạy database migration, xử lý queue hoặc gửi email ngay khi khởi động, các tác vụ này có thể tác động **hệ thống thật trước khi swap hoàn tất**.

**Cách xử lý:** health/readiness endpoint phải không gây side effect; schema migration phải có quy trình riêng, tương thích hai phiên bản; background jobs cần được điều phối/khóa phù hợp ở tầng hệ thống, không chỉ dựa vào tên slot. Nên thực hiện thử nghiệm swap trong môi trường được phép trước khi dùng production.

### 4.4. Ví dụ phân loại setting

| Setting/nguồn cấu hình | Chiến lược | Lý do |
|---|---|---|
| RELEASE_VERSION | Theo artifact; có thể chuyển cùng code | Dùng cho truy vết build |
| LOG_LEVEL | Tùy môi trường/chính sách | Có thể khác để điều tra nhưng tránh lộ dữ liệu |
| DATABASE_URL | Sticky theo slot, quản lý bí mật | Ngăn nhầm môi trường khi cấu hình thay đổi |
| PAYMENT_API_KEY | Sticky hoặc Key Vault reference phù hợp | Không đưa key thật vào artifact |
| FEATURE_CHECKOUT_V2 | Có thể tách feature flag/rollout khỏi swap | Giảm coupling giữa deploy và bật chức năng |
| MIGRATION_ENABLED | Mặc định tắt trong web process; quản trị bằng migration job riêng | Tránh migration hai lần và chạy khi warm-up |
| APP_BUILD_SHA | Theo phiên bản build | Kiểm tra release hiện tại |
| BACKGROUND_WORKER_ENABLED | Điều khiển an toàn bằng cơ chế orchestration và khóa ở lớp ứng dụng | Tránh hai slot đồng thời xử lý cùng queue |

Một setting đánh dấu sticky không thay thế authorization ở database hoặc Key Vault. Phải xác minh danh tính/role, firewall và secret reference của cả production/staging.

## 5. Swap hoạt động qua những giai đoạn nào?

### 5.1. Luồng triển khai chuẩn

~~~mermaid
sequenceDiagram
    participant C as CI/CD Pipeline
    participant S as Staging Slot
    participant A as App Service Swap
    participant P as Production Slot
    participant M as Monitoring
    C->>S: Deploy artifact v2
    C->>S: Smoke test v2
    C->>A: Yêu cầu swap staging → production
    A->>S: Áp cấu hình target phù hợp, restart
    A->>S: Warm-up / kiểm tra readiness
    S-->>A: Ready theo tiêu chí dịch vụ
    A->>P: Chuyển phiên bản được swap vào target
    C->>M: Kiểm tra API, log, p95, lỗi
    M-->>C: Pass hoặc cảnh báo rollback
~~~

Mô hình trên nhằm giải thích thứ tự logic; các bước nội bộ, số lần restart hoặc thời điểm áp cấu hình có thể khác theo loại App Service và kịch bản swap. Cần kiểm tra khả năng hỗ trợ cụ thể của Linux/Windows, runtime và cấu hình ứng dụng.

### 5.2. Chuẩn bị (pre-swap)

App Service chuẩn bị source slot tương thích với cấu hình target, khởi động lại instance khi cần, thực hiện warm-up. Nếu giai đoạn chuẩn bị thất bại, swap có thể không được hoàn tất và nhóm phải điều tra thay vì buộc production nhận phiên bản chưa ready.

Điều quan trọng là định nghĩa **ready** rõ ràng, không chỉ dựa vào tiến trình đã chạy hoặc một trang HTML có thể trả 200 dù ứng dụng chưa kết nối tới các dịch vụ bắt buộc.

### 5.3. Hoàn tất swap

Sau khi source đạt điều kiện, App Service thực hiện thao tác chuyển các thành phần được phép swap. URL production tiếp tục là URL production quen thuộc; người dùng không phải chuyển sang hostname staging. Phiên bản trước có thể nằm ở slot còn lại và hỗ trợ rollback trong trường hợp phù hợp.

**Swap không di chuyển database** và không tự đồng bộ dữ liệu ngoài slot. Nó cũng không phải một chiến lược multi-region failover.

### 5.4. Swap with preview

Nếu kịch bản và platform hỗ trợ **swap with preview**, có thể tách thành hai giai đoạn:

1. **Prepare/preview:** chuẩn bị source với cấu hình target và để người vận hành kiểm tra trạng thái trước khi quyết định chuyển lưu lượng.
2. **Complete:** hoàn tất swap theo quyết định của người vận hành.
3. **Cancel/reset:** hủy giai đoạn preview nếu phát hiện bất thường, khôi phục trạng thái phù hợp với quá trình preview theo cơ chế dịch vụ.

Preview cho nhóm một điểm kiểm tra hữu ích trước khi tác động production traffic. Nhưng **không nên mặc định mọi loại App Service đều hỗ trợ preview**; một số tổ hợp hệ điều hành, authentication hoặc platform có hạn chế. Kiểm tra tính năng swap with preview của đúng App Service, không tự viết automation bắt buộc preview trên mọi app.

Cũng không được hiểu preview là cô lập tuyệt đối với production: trong bước chuẩn bị, ứng dụng có thể đang sử dụng target configuration. Các background task tự chạy vẫn là nguy cơ cần quản lý.

## 6. Warm-up và readiness là gì?

### 6.1. Warm-up không chỉ là một request HTTP

Với ứng dụng Java, .NET hoặc Node.js, cold start có thể cần:

- Tạo runtime, nạp module, cấu hình dependency injection và JIT.
- Đọc cấu hình, kiểm tra kết nối database hoặc Key Vault.
- Nạp template, metadata, rule hoặc cache cục bộ.
- Mở pool connection và khởi tạo HTTP clients.
- Hoàn tất đăng ký dependency và bắt đầu đáp ứng request.

Đối với container App Service, còn có quá trình pull image, khởi động container, nhận port và runtime startup. Bước warm-up nhằm giảm khả năng phiên bản mới nhận traffic trước khi sẵn sàng.

### 6.2. Phân biệt liveness, readiness và deep health

| Endpoint | Câu hỏi | Ví dụ kết quả |
|---|---|---|
| /health/live | Tiến trình hiện còn chạy? | 200 nếu process/scheduler chưa bị kẹt |
| /health/ready | Instance có khả năng nhận request nghiệp vụ? | 200 khi sẵn sàng, 503 nếu đang khởi động |
| /health/deep | Database và dịch vụ phụ thuộc đang khỏe? | Kết quả chi tiết chỉ cho người vận hành có quyền |

**Readiness** cho swap cần phản ánh những điều kiện thiết yếu để phục vụ lưu lượng. Tuy nhiên, tránh check quá sâu hoặc tạo side effect: endpoint không được tự tạo bảng, đổi schema, gửi thanh toán, gửi email, ghi đơn hàng hoặc consume queue để chứng minh "sẵn sàng".

Ví dụ JSON:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"status":"ready","version":"v2.3.0"}
~~~

Khi chưa sẵn sàng:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Cache-Control: no-store

{"status":"not_ready"}
~~~

Nếu endpoint có authentication redirect 302 hoặc 401, warm-up probe có thể không đánh giá đúng. Thiết kế một endpoint không lộ dữ liệu nhạy cảm, có phạm vi truy cập hợp lý cho nền tảng kiểm tra, và đáp ứng HTTP status theo quy tắc warm-up được cấu hình.

### 6.3. App settings cho swap warm-up

App Service có những app settings liên quan warm-up khi swap:

- **WEBSITE_SWAP_WARMUP_PING_PATH:** đường dẫn ping làm nóng phiên bản trong quá trình swap, ví dụ /health/ready.
- **WEBSITE_SWAP_WARMUP_PING_STATUSES:** những mã HTTP được xem là thành công cho warm-up, ví dụ 200.

Ví dụ (giá trị minh họa):

~~~text
WEBSITE_SWAP_WARMUP_PING_PATH=/health/ready
WEBSITE_SWAP_WARMUP_PING_STATUSES=200
~~~

**Điểm dễ bỏ sót:** nếu không cấu hình giới hạn HTTP status theo cơ chế hỗ trợ, một response không phù hợp (ví dụ redirect hoặc lỗi) có thể vẫn không chặn warm-up như mong muốn. Do đó cần đặt rõ mã chấp nhận được và xác minh thực tế trong bài thử swap.

Ngoài ra, App Service có những thiết lập startup/warm-up khác, chẳng hạn WEBSITE_WARMUP_PATH trong một số kịch bản container, hoặc application initialization của ứng dụng Windows/IIS. **Đừng đánh đồng** một cơ chế warm-up khi khởi động container với warm-up lúc thực hiện slot swap. Tên, hiệu lực và khả năng hỗ trợ khác nhau theo platform.

### 6.4. Ví dụ Java Spring Boot với readiness

Với Spring Boot và Spring Boot Actuator được cấu hình phù hợp, ứng dụng có thể cung cấp health endpoints. Một cấu hình tham khảo:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Khi khả năng readiness probe được bật, đường dẫn tham khảo có thể là:

~~~text
/actuator/health/readiness
~~~

Ứng dụng cần khai báo dependency Spring Boot Actuator trong build và cấu hình bảo mật cho health endpoint. Nếu dùng một readiness path riêng như /health/ready, hãy implement hoặc route tới endpoint thật; **không đưa đường dẫn chưa tồn tại vào WEBSITE_SWAP_WARMUP_PING_PATH**.

Health response phải phục vụ điều kiện readiness đã định, ví dụ Spring lifecycle hoàn tất. Nếu phụ thuộc database là điều kiện bắt buộc, có thể thiết kế health contributor phù hợp nhưng tránh chạy câu lệnh ghi hoặc query nặng khi probe được gọi liên tục.

### 6.5. Dùng Application Insights và thử cold start

Quan sát:

1. Thời gian từ startup đến readiness.
2. Tỷ lệ lỗi trong vài phút đầu sau deploy hoặc swap.
3. Thời gian trả lời p95/p99 khi lần đầu truy cập endpoint nghiệp vụ.
4. Số lượng instance chưa ready hoặc restart loop.
5. Dependency errors như DB timeout, DNS, Key Vault unavailable.

Không tuyên bố "zero downtime" chỉ vì warm-up ping thành công. Cần thử cả trạng thái load cao, scale-out và lỗi một dependency.

## 7. Thực hành: tạo slot và triển khai phiên bản staging

Giả sử app **orders-web** thuộc resource group **rg-orders-prod** và App Service Plan hỗ trợ deployment slots. Web app đã được tạo và đang chạy v1 ở production.

### Bước 1: Xác nhận subscription và app

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az webapp show \
  --resource-group rg-orders-prod \
  --name orders-web \
  --query "{name:name,kind:kind,state:state,host:defaultHostName,plan:serverFarmId}" \
  --output json
~~~

Kiểm tra App Service Plan SKU/tier được liên kết với ứng dụng; không tự nâng tier khi chưa có phê duyệt chi phí.

### Bước 2: Tạo staging slot

~~~bash
az webapp deployment slot create \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging
~~~

Tùy kịch bản, có thể tạo slot bằng cách clone cấu hình từ một slot hiện hữu qua tham số tương ứng của CLI hoặc từ Azure Portal. Nếu clone production, phải rà soát lại **tất cả** settings, connection strings, quyền, webhook và background tasks trước khi cho phép ứng dụng staging chạy.

Liệt kê slot:

~~~bash
az webapp deployment slot list \
  --resource-group rg-orders-prod \
  --name orders-web \
  --output table
~~~

Truy cập URL slot (nếu đã cấu hình và được phép truy cập):

~~~text
https://orders-web-staging.azurewebsites.net
~~~

Slot staging là endpoint sống; mặc định không nên coi URL này đã được bảo vệ khỏi truy cập công khai. Tùy môi trường, áp dụng App Service access restrictions, authentication hoặc mạng riêng theo tính năng được hỗ trợ.

### Bước 3: Phân tách cấu hình theo slot

Ví dụ gán environment marker với flag slot-specific:

~~~bash
az webapp config appsettings set \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --slot-settings APP_ENV=staging

az webapp config appsettings set \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot-settings APP_ENV=production
~~~

Tham số **--slot-settings** đặt app settings là deployment slot settings. Không đưa secret vào câu lệnh ở ví dụ production nếu có thể làm lộ qua terminal history, log hoặc pipeline output; ưu tiên identity và Key Vault references theo mô hình App Service hỗ trợ.

Đọc metadata để kiểm tra cấu hình và thuộc tính slotSetting:

~~~bash
az webapp config appsettings list \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --query "[].{name:name,slotSetting:slotSetting}" \
  --output table
~~~

**Không in value của settings khi có secret.** Một số lệnh CLI có thể trả giá trị bí mật trong output; sử dụng query hạn chế trường khi kiểm toán.

### Bước 4: Cấu hình warm-up

Giả sử ứng dụng cung cấp /health/ready. Thiết lập warm-up cho staging theo cách app settings của sản phẩm hỗ trợ:

~~~bash
az webapp config appsettings set \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --settings WEBSITE_SWAP_WARMUP_PING_PATH=/health/ready WEBSITE_SWAP_WARMUP_PING_STATUSES=200
~~~

Đọc lại names/slotSetting và kiểm tra tài liệu sản phẩm để xác định các settings cần gắn với phiên bản ứng dụng hay với slot cụ thể. Không đánh dấu một setting sticky chỉ vì nó có tên chứa WEBSITE_ nếu chưa biết mục tiêu khi swap.

Sau khi thiết lập, thử endpoint ở staging:

~~~bash
curl -i https://orders-web-staging.azurewebsites.net/health/ready
~~~

Hãy kiểm tra mã HTTP cuối cùng, nội dung, độ trễ, quyền truy cập và tính nhất quán trên nhiều instance. Một kết quả 200 đơn lẻ chưa đủ cho acceptance test.

### Bước 5: Deploy artifact vào staging

Có thể triển khai qua Azure DevOps, GitHub Actions hoặc Azure CLI. Ví dụ một ZIP đã được build phù hợp với runtime của web app:

~~~bash
az webapp deploy \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --src-path "./orders-web-v2.zip" \
  --type zip
~~~

Lệnh minh họa triển khai artifact, không tự biên dịch dự án. Với Java App Service, cách đóng gói JAR/WAR/ZIP, runtime startup command và đích triển khai phụ thuộc stack đã chọn; phải dùng kiểu artifact tương thích thay vì đổi tên một file bất kỳ thành ZIP.

Một pipeline an toàn nên **build một lần, giữ checksum/artifact ID, triển khai artifact đã được phê duyệt** thay vì tự build lại giữa các lần staging và production.

### Bước 6: Smoke test trước swap

Từ máy/kênh kiểm thử đã có quyền:

~~~bash
curl -i https://orders-web-staging.azurewebsites.net/health/ready
curl -i https://orders-web-staging.azurewebsites.net/api/version
~~~

Kiểm tra ít nhất:

- HTTP status, readiness và version/build SHA.
- Các đường API đọc không gây side effect.
- Khả năng xác thực, authorization và cấu hình CORS theo chính sách.
- Database queries ở môi trường được phép, schema tương thích.
- Key Vault, Storage, outbound network và DNS dependencies.
- Telemetry trên Application Insights, lỗi 5xx, latency và restart.
- Bảo vệ URL staging, không chứa secret trong response.
- Background jobs có thể hoạt động an toàn khi slot swap chuẩn bị.

Chỉ đưa release sang giai đoạn phê duyệt swap nếu các acceptance criteria đạt.

## 8. Thực hiện swap và kiểm tra sau phát hành

### 8.1. Swap staging sang production

Khi có approval:

~~~bash
az webapp deployment slot swap \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --target-slot production
~~~

Chạy bằng principal có quyền phù hợp với App Service resource. Swap này thay đổi phiên bản phục vụ người dùng; không dùng như bước thử nghiệm vô hại trên production.

Xác minh:

~~~bash
curl -i https://orders-web.azurewebsites.net/health/ready
curl -i https://orders-web.azurewebsites.net/api/version
~~~

Ngoài response, theo dõi Azure Monitor/Application Insights, HTTP 5xx, dependency failures, p95 latency, CPU/memory, restart, queue backlog và tỷ lệ lỗi nghiệp vụ trong một cửa sổ quan sát đã thống nhất.

### 8.2. Rollback bằng swap ngược

Sau một swap thành công, bản code trước thường có thể được đưa trở lại production bằng một thao tác swap ngược tương ứng, **nếu các slot và artifact vẫn giữ trạng thái phù hợp**.

Ví dụ:

~~~bash
az webapp deployment slot swap \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --target-slot production
~~~

Đây là cùng hướng source/target trong lệnh, nhưng sau lần swap đầu staging có thể giữ phiên bản cũ. Kiểm tra **build SHA và cấu hình thật ở cả hai slot trước khi thực hiện lần tiếp theo**; nếu pipeline đã triển khai phiên bản khác vào staging, lệnh này sẽ không còn là rollback như dự kiến.

Rollback cần được ghi nhận: ai phê duyệt, trigger nào kích hoạt, trạng thái dữ liệu, kết quả xác minh và kế hoạch xử lý nguyên nhân.

### 8.3. Giới hạn rollback

Swap ngược **không** hoàn tác:

- Database schema migration hoặc dữ liệu đã thay đổi.
- Tin nhắn đã được gửi, hàng đợi đã consume hoặc payment đã xử lý.
- Thay đổi Key Vault secret, DNS, firewall, storage ngoài slot.
- Session/cache bị thay đổi hoặc dữ liệu lưu tạm trong bộ nhớ instance.
- Các hệ thống bên ngoài đã nhận request từ phiên bản mới.

Vì vậy, muốn rollback hiệu quả phải thiết kế **compatibility và reversibility** từ trước, không chỉ giữ bản artifact v1.

### 8.4. Swap with preview trong quy trình có gate

Ở môi trường hỗ trợ preview, có thể tách chuẩn bị và hoàn tất khi được vận hành/phê duyệt theo tài liệu. CLI có các lựa chọn action tương ứng trên phiên bản hỗ trợ; hãy xác minh trợ giúp cho đúng Azure CLI:

~~~bash
az webapp deployment slot swap --help
~~~

Không phát hành một automation dựa vào những tham số preview chưa được xác minh hoặc cho rằng các platform hỗ trợ giống nhau. Với môi trường không hỗ trợ preview, dùng smoke test trên staging và swap bình thường với approval, telemetry và rollback plan.

## 9. Những rủi ro liên quan database và background processing

### 9.1. Database migration

Ví dụ release v2 thêm cột mới vào bảng orders. Nếu cùng lúc ứng dụng v1 vẫn chạy, schema mới cần giữ được hành vi của v1 cho tới khi v2 triển khai ổn định.

Mẫu **expand–migrate–contract**:

1. **Expand:** thêm bảng/cột/index theo cách tương thích ngược.
2. **Migrate:** chạy backfill bằng job riêng, có khả năng retry/idempotency và giám sát.
3. **Deploy v2:** đưa code vào staging, warm-up, smoke test và swap.
4. **Observe:** xác nhận v2 hoạt động, có thể rollback code v1 khi cần.
5. **Contract:** chỉ xóa schema cũ khi mọi phiên bản phụ thuộc đã ngừng và có approval.

**Không đặt migration phá vỡ schema trực tiếp trong startup hook của ứng dụng.** Startup có thể chạy nhiều lần trên nhiều instance, cả staging và production, và có thể được kích hoạt trong warm-up.

### 9.2. Queue consumers và scheduled jobs

Hai slot có thể cùng chạy process nền. Nếu v2 staging có worker tự động lắng nghe queue production, nó có thể tiêu thụ job trước khi swap. Tình huống có thể dẫn tới xử lý hai lần, gửi mail trùng hoặc tranh chấp data.

Các biện pháp:

- Tách web app khỏi worker service có vòng đời phát hành riêng.
- Dùng queue/endpoint riêng ở môi trường kiểm thử, nhưng phải hiểu warm-up có thể áp target settings.
- Sử dụng distributed lock hoặc lease thích hợp nếu chỉ một worker được phép chạy.
- Dùng feature flag cấp hệ thống hoặc chính sách orchestration để ngăn side effect khi chưa được phê duyệt.
- Thiết kế idempotency cho event/message và xử lý giao dịch an toàn.
- Giám sát queue backlog, dead-letter và processing metrics qua cả quá trình swap.

**Không chỉ dựa vào một biến APP_ENV=staging để bảo đảm không có side effect** khi áp cấu hình target vào source. Cần kiểm thử thật đường chạy code và hành vi khi swap.

### 9.3. Session và file tạm

App Service slots không nên được coi là nơi lưu trạng thái phiên bất biến. Trong ứng dụng scale-out, một request có thể đi vào instance khác; khi swap, instance restart hoặc route thay đổi cũng có thể làm session in-memory mất.

Nên dùng session store được hỗ trợ (ví dụ giải pháp cache phân tán), cookie/session design phù hợp và persistent storage cho những dữ liệu cần tồn tại. Với WebSocket hoặc kết nối dài, kiểm tra cơ chế reconnect và khả năng chịu ngắt phiên.

### 9.4. Feature flags

Deployment slot cho phép tách **deploy code** khỏi **đưa code nhận production traffic**, nhưng không tự tách việc **bật chức năng nghiệp vụ**. Với thay đổi lớn, nên đưa feature flags vào hệ thống cấu hình được kiểm soát để bật từng nhóm người dùng sau khi swap.

Cần bảo đảm feature flags được đọc/cached theo chiến lược cập nhật hợp lý; rollback flag không thay thế rollback code nếu có lỗi nghiêm trọng ở tầng startup hoặc dependency.

## 10. Canary release và traffic routing khác swap

Azure App Service có khả năng **traffic routing giữa production và các deployment slots** ở những cấu hình được hỗ trợ. Cách này có thể giúp kiểm thử một tỷ lệ người dùng trên slot staging, khác với swap chuyển phiên bản chính sang production.

| Tiêu chí | Swap | Traffic routing/canary |
|---|---|---|
| Mục tiêu | Phát hành phiên bản đã chuẩn bị vào production | Cho một tỷ lệ request/client đi tới slot thử nghiệm |
| Cách chọn lưu lượng | Giao dịch phát hành giữa source và target | Quy tắc phân phối của App Service |
| Thời điểm | Sau smoke test và warm-up | Có thể trước swap hoặc trong giai đoạn thử nghiệm riêng |
| Mức tiếp xúc với user | Phiên bản mới trở thành phiên bản production theo thao tác swap | Chỉ một phần người dùng tới slot mới theo phân phối/cookie |
| Rủi ro dữ liệu | Vẫn chịu tác động của database/queue/shared services | Càng cần backward compatibility vì hai phiên bản cùng phục vụ người dùng |
| Rollback | Swap lại code nếu trạng thái phù hợp | Đặt traffic về 0 hoặc thay quy tắc, sau đó xử lý dữ liệu |
| Giới hạn | Chỉ nội dung/cấu hình được hỗ trợ | Cần xét cookie routing, phiên, user experience và tính năng tier |

Không dùng tỷ lệ routing như bằng chứng chắc chắn đúng tỷ lệ request trong mọi khoảng rất ngắn: sticky routing cookie và phân phối theo client có thể ảnh hưởng quan sát. Khi kiểm thử canary, đo telemetry theo **release version/slot**, không chỉ theo tổng thể production.

Nếu dùng Front Door hoặc Application Gateway phía trước App Service, cũng có lựa chọn canary/blue-green ở lớp routing riêng. Đừng nhầm quy tắc routing ngoài App Service với slot swap bên trong Web App.

## 11. Bảo mật staging và quản lý bí mật

### 11.1. Slot staging không tự an toàn

Staging có hostname riêng và có thể truy cập từ Internet nếu web app/network config cho phép. Nó có thể chứa code chưa release, endpoint debug, seed data hoặc lỗi mới. Cần:

- Hạn chế truy cập slot qua access restrictions, authentication hoặc mạng riêng theo kịch bản hỗ trợ.
- Không dùng mật khẩu/secret thật trên staging ngoài nhu cầu đã được phê duyệt.
- Tắt debug endpoints, stack traces và thông tin phiên bản nhạy cảm.
- Không đưa data khách hàng thật vào staging nếu chưa có cơ sở bảo vệ.
- Kiểm soát người có quyền deploy vào slot, xem settings và thực hiện swap.
- Bật HTTPS, logging và kiểm tra lỗ hổng như production.

### 11.2. Key Vault references và managed identity

Khi dùng Key Vault reference trong app settings, cần kiểm tra cách đánh giá reference, danh tính truy cập và network path của từng slot. Managed identity và một số thuộc tính resource-specific không tự đồng nghĩa được swap cùng code. Với staging/production, xác định rõ:

- Slot nào có identity nào và role nào trên Key Vault?
- Key Vault reference nào là sticky?
- Key Vault có network rule/private endpoint nào?
- Có thể rotation secret mà không gián đoạn startup?
- App có cache secret quá lâu, cần restart hoặc refresh khi thay đổi không?

Nếu warm-up với target settings yêu cầu truy cập Key Vault production, source slot trong giai đoạn chuẩn bị phải có cấu hình và quyền đáp ứng **theo thiết kế đã được phê duyệt**. Đừng cấp quyền rộng vô thời hạn cho staging chỉ để vượt qua lỗi swap; xem kiến trúc danh tính và hạn chế side effect.

### 11.3. Azure RBAC và audit

Quyền triển khai artifact và quyền swap production có thể được phân tách trong pipeline/role assignment tùy cơ chế quản trị. Một mô hình thường dùng:

1. CI service principal/managed identity triển khai staging theo quyền tối thiểu.
2. QA/service owner kiểm tra và ghi acceptance.
3. Release manager hoặc approval gate cho phép swap.
4. Pipeline phát hành ghi artifact SHA, slot source/target, người phê duyệt và thời gian.
5. Azure Activity Log, deployment log và App Insights lưu dấu vết sự kiện.

Không mặc định mọi người có quyền chỉnh staging cũng được phép phát hành production.

## 12. Giám sát hiệu quả swap

### 12.1. Quan sát trước, trong và sau swap

| Giai đoạn | Dữ liệu cần xem |
|---|---|
| Trước deploy | p50/p95 latency, 5xx, CPU, memory, dependency errors ở production |
| Staging warm-up | Startup duration, readiness, lỗi cấu hình/Key Vault/DB, restart |
| Ngay sau swap | HTTP status, request rate, version/build SHA, latency, dependency duration |
| Cửa sổ quan sát | Lỗi nghiệp vụ, queue backlog, session/login, resource usage, retry rate |
| Nếu rollback | Thời gian khôi phục, error trend và tác động dữ liệu |
| Sau phát hành | Bản ghi release, retrospective, cải tiến alert/runbook |

Có thể dùng Application Insights, Azure Monitor metrics/logs, Availability Tests và hệ thống APM nội bộ. Các bảng KQL và field cụ thể phụ thuộc phiên bản Application Insights và chế độ workspace-based.

### 12.2. KQL tham khảo cho request errors

Nếu workspace có bảng AppRequests (workspace-based Application Insights):

~~~kusto
AppRequests
| where TimeGenerated > ago(30m)
| summarize
    Requests = count(),
    Failed = countif(Success == false),
    P95ms = percentile(DurationMs, 95)
  by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Ví dụ schema có thể khác theo workspace; trước khi dùng, kiểm tra tên bảng, kiểu DurationMs và cách lưu Success trong tài nguyên thật. Không mặc định query trên sẽ hoạt động ở mọi chế độ classic/legacy hoặc mọi nguồn telemetry.

KQL phân tách theo version nếu ứng dụng ghi custom dimension hoặc cloud role name:

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize Requests=count(), Failed=countif(Success == false)
  by AppRoleName, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Để phân biệt staging và production khi chúng dùng chung Application Insights, nên cấu hình cloud role name hoặc thuộc tính phiên bản/slot được ghi rõ; không suy ra role name mặc định luôn phân biệt hai slot.

### 12.3. Alert và điều kiện rollback

Ví dụ release gate nội bộ (ngưỡng hoàn toàn minh họa, không phải SLA của Azure):

- Production HTTP 5xx vượt 2% liên tục 5 phút.
- p95 latency tăng gấp đôi baseline trong cùng mức traffic.
- Dependency failure rate hoặc queue backlog vượt ngưỡng đã thống nhất.
- Xuất hiện lỗi giao dịch thanh toán/đặt hàng.
- Trạng thái readiness trở về 503 trên nhiều instance.

Cần quyết định nếu ngưỡng bị vượt: rollback ngay, giữ phiên bản để điều tra, hoặc giảm traffic canary. Tránh auto-rollback hoàn toàn không có kiểm soát nếu có database migration hoặc giao dịch không thể đảo ngược.

## 13. Chi phí, hiệu năng và tính sẵn sàng

### 13.1. Chi phí deployment slots

Slot staging thường không được tính như một App Service Plan riêng chỉ vì tạo slot, nhưng vẫn dùng **compute của App Service Plan**. Nếu staging tiêu thụ CPU/RAM lớn, phiên bản production trên cùng plan có thể chậm hơn. Những tính năng hỗ trợ, giới hạn slot và giá theo tier cần được xác nhận tại thời điểm triển khai.

Các khoản cần xem:

- Tier App Service Plan hỗ trợ slots và chi phí instance/scale-out.
- Dung lượng CPU/RAM dùng đồng thời bởi production và staging.
- Application Insights/Log Analytics ingestion và retention.
- Networking, private endpoints, VNet integration, NAT Gateway và egress nếu dùng.
- Database, Key Vault, Storage và những dịch vụ môi trường staging kết nối đến.
- Chi phí kiểm thử, load test và hệ thống CI/CD.

Đừng dùng staging để stress test không giới hạn trên App Service Plan chung với production nếu chưa đánh giá tải và áp lực lên instance.

### 13.2. Scale và high availability

Slots là công cụ **phát hành phần mềm**, không phải giải pháp HA/multi-region độc lập. Các slot chia sẻ App Service Plan, có thể cùng chịu lỗi plan, region hoặc dịch vụ phụ thuộc. Muốn tăng tính sẵn sàng cần xem autoscale, nhiều instance, zone redundancy nếu tier/region hỗ trợ, multi-region routing và cơ chế khôi phục dữ liệu.

Warm-up giúp giảm rủi ro cold start cho phiên bản mới, nhưng không bảo đảm không có kết nối bị ngắt hoặc không có p95 latency spike. Điều quan trọng là **đo thực tế** trên ứng dụng.

## 14. Tình huống mẫu: triển khai ứng dụng đơn hàng Java

**Bối cảnh:** một doanh nghiệp có orders-web chạy Spring Boot trên Azure App Service. Phiên bản v1 phục vụ production. Phiên bản v2 thêm API lọc đơn hàng, thêm cột dữ liệu tùy chọn và thay giao diện quản trị.

### 14.1. Kế hoạch release

1. Chuẩn bị database migration có tính tương thích ngược: thêm cột nullable, giữ v1 vẫn hoạt động.
2. Build artifact v2 một lần, ký/ghi hash và lưu trong artifact repository.
3. Deploy v2 vào staging slot với cấu hình, danh tính và quyền đã kiểm soát.
4. Smoke test phiên bản, auth, API đọc, đường readiness và kết nối dependency.
5. Tắt hoặc cô lập tác vụ nền không được phép trên staging, xác nhận warm-up không có side effect.
6. Chạy swap staging → production sau approval.
7. Giám sát 5xx, p95 latency, số giao dịch lỗi, queue backlog và database connections.
8. Nếu lỗi nghiêm trọng: đánh giá dữ liệu và swap lại bản cũ nếu còn phù hợp.
9. Khi v2 ổn định: hoàn tất migration theo kế hoạch và chỉ sau đó cân nhắc bỏ schema cũ.

### 14.2. Runbook rollback ví dụ

~~~yaml
releaseId: ORDERS-2026-11-20-02
app: orders-web
sourceSlot: staging
targetSlot: production
artifactVersion: v2.3.0
preSwap:
  - "Verify build SHA and artifact checksum"
  - "Readiness returns HTTP 200"
  - "Smoke tests pass"
  - "Backward-compatible schema migration completed"
  - "No unsafe background task in warm-up"
approval:
  required: true
postSwap:
  - "Check production /api/version"
  - "Monitor 5xx, p95 latency, dependency failures"
  - "Verify order creation and read flows safely"
rollback:
  - "Confirm previous version remains in staging"
  - "Assess database and external side effects"
  - "Run approved slot swap if safe"
  - "Verify production and record incident"
~~~

Đây là một mẫu quản trị release, không phải schema YAML của Azure DevOps/GitHub Actions và không phải kết quả phát hành thực tế.

### 14.3. Những trường hợp không thể rollback chỉ bằng slot

- v2 xóa một cột đang được v1 sử dụng.
- v2 gửi thông báo/thu tiền/consume queue mà v1 không biết trạng thái.
- v2 thay đổi định dạng dữ liệu không tương thích ngược.
- v2 cập nhật secret ngoài App Service.
- v1 artifact đã bị thay bằng bản khác trong staging.

Những tình huống này cần thiết kế giao thức dữ liệu, event processing và kế hoạch phục hồi riêng.

## 15. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Không tạo được deployment slot | App Service Plan tier không hỗ trợ hoặc đã đạt quota | Kiểm tra SKU, giới hạn slot |
| Staging truy cập lỗi | Artifact/runtime/startup command sai, auth hoặc access restriction | Deployment logs, application logs, hostname và route |
| Swap treo hoặc thất bại khi warm-up | Readiness không trả mã chấp nhận, app restart loop, cấu hình target gây lỗi | WEBSITE_SWAP_WARMUP_PING_PATH/STATUSES, startup logs, dependency |
| Warm-up trả 302 nhưng vẫn được coi ready | Không cấu hình danh sách mã status chấp nhận | Cấu hình 200, thiết kế endpoint health phù hợp |
| Sau swap app kết nối nhầm database | Setting không sticky, secret reference hoặc target config sai | Kiểm tra slotSetting, app settings, Key Vault reference và lịch sử |
| Staging làm thay đổi dữ liệu production | Background job/migration chạy khi warm-up hoặc source đã có quyền production | Cô lập tác vụ, kiểm tra startup hooks và cơ chế lease/flag |
| Production lỗi dù staging pass | Cấu hình target, domain, auth, network, dependency khác | Kiểm tra theo target setting, logs sau swap và role |
| Phiên bản cũ không nằm ở staging | Pipeline deploy tiếp sau swap hoặc đã sửa artifact | Kiểm tra build SHA ở cả slot, release log |
| Swap ngược không khôi phục dữ liệu | DB migration hoặc side effect đã xảy ra | Rollback dữ liệu theo kế hoạch, không chỉ code |
| 5xx/p95 tăng trong swap | Restart, cold cache, connection pooling, scale hoặc dependency | App Insights, startup time, health/readiness |
| Preview option không khả dụng | Platform/tính năng đang dùng không hỗ trợ | Kiểm tra loại App Service và tài liệu tính năng |
| Lỗi chỉ khi app scale-out | Session in-memory, local file, startup race, shared resource | Distributed session store, idempotency, telemetry theo instance |
| Secret xuất hiện trong log | Script in app settings, debug dump hoặc pipeline output | Thu hồi secret, giới hạn log, sửa pipeline, kiểm tra access |

### 15.1. Phân biệt nguyên nhân từ App Service và nguyên nhân ứng dụng

Khi swap thất bại, theo thứ tự:

1. App Service Plan và giới hạn slot.
2. Deployment status và artifact đúng của staging.
3. Startup command, runtime, logs và health endpoint.
4. App settings/connection strings và cấu hình sticky.
5. Network, DNS, Key Vault và identity của slot.
6. Database schema, queue/background jobs.
7. Swap operation status và Application Insights.
8. Version production thực tế và tiêu chí rollback.

Đừng sửa cùng lúc nhiều thiết lập production trước khi chụp lại cấu hình và logs. Điều này khiến việc xác định thay đổi nào gây lỗi khó hơn và có thể phá hỏng khả năng rollback.

## 16. Checklist triển khai production

### Trước khi triển khai

- [ ] App Service Plan hỗ trợ deployment slots và còn quota.
- [ ] Cả production và staging có owner, RBAC, logging và bảo vệ mạng phù hợp.
- [ ] Có artifact version/build SHA được truy vết.
- [ ] App settings và connection strings đã được phân loại sticky/không sticky.
- [ ] Key Vault references và managed identities được kiểm tra cho từng slot.
- [ ] Endpoint readiness không gây side effect, trả status rõ ràng.
- [ ] WEBSITE_SWAP_WARMUP_PING_PATH và STATUSES được thiết kế/kiểm thử.
- [ ] Migration tương thích ngược và không tự chạy phá dữ liệu khi startup.
- [ ] Queue consumers, scheduled jobs và external integrations đã được kiểm soát.
- [ ] Có baseline 5xx/p95 latency/functional errors và approval gate.
- [ ] Có bản artifact trước và phương án phục hồi DB/dữ liệu.

### Sau khi deploy staging

- [ ] Staging thực sự chạy release mới.
- [ ] API version/build SHA khớp artifact.
- [ ] Smoke test, auth, permissions, DB/Key Vault connectivity đạt.
- [ ] Không có lỗi startup/restart loop hoặc log lộ secret.
- [ ] Kiểm tra warm-up với cấu hình target trong môi trường được phép.
- [ ] Người phê duyệt xác nhận release có thể swap.

### Sau swap

- [ ] URL production phản hồi version mới và readiness đúng.
- [ ] Error rate, latency và dependency failures trong ngưỡng.
- [ ] Các giao dịch nghiệp vụ quan trọng hoạt động.
- [ ] Queue backlog và background jobs không xử lý trùng.
- [ ] Bản trước vẫn sẵn sàng để rollback nếu cần.
- [ ] Release record chứa thời gian UTC, người phê duyệt và kết quả.
- [ ] Không cần giữ cấu hình debug hoặc quyền staging quá rộng.

## 17. Câu hỏi tự kiểm tra

1. **Deployment slot là gì?** Là môi trường ứng dụng có hostname và cấu hình riêng thuộc cùng App Service Web App, giúp chuẩn bị phiên bản trước khi đưa vào production.
2. **Slot staging có đồng nghĩa một server/region tách biệt hoàn toàn không?** Không, các slot chia sẻ App Service Plan và có các phụ thuộc chung.
3. **Swap có tự di chuyển database không?** Không. Swap áp dụng cho nội dung và cấu hình App Service được hỗ trợ.
4. **Sticky settings nhằm mục đích gì?** Giữ một số cấu hình gắn với slot thay vì đi theo mã phiên bản khi swap.
5. **Tại sao warm-up có thể nguy hiểm nếu startup chạy migration?** Source có thể được khởi động với target configuration trước khi chuyển traffic; migration có thể tác động database thật.
6. **Warm-up 200 có chứng minh toàn bộ giao dịch sản xuất an toàn không?** Không; chỉ là một tín hiệu readiness, còn cần smoke test và giám sát.
7. **WEBSITE_SWAP_WARMUP_PING_PATH dùng làm gì?** Chỉ định URL path cho warm-up probe trong quá trình swap theo khả năng App Service.
8. **Vì sao nên cấu hình WEBSITE_SWAP_WARMUP_PING_STATUSES?** Để giới hạn những mã HTTP được xem là warm-up thành công, tránh nhận nhầm redirect/error.
9. **Swap with preview dùng khi nào?** Khi kịch bản hỗ trợ và muốn kiểm tra giai đoạn chuẩn bị trước khi hoàn tất swap.
10. **Rollback bằng swap ngược có khôi phục database schema không?** Không; database và side effects cần kế hoạch riêng.
11. **Staging có thể vô tình consume message production không?** Có, nếu worker/queue và cấu hình không được kiểm soát.
12. **Tại sao không nên hard-code secret vào artifact?** Vì artifact có thể đi giữa slot và bị lộ qua repo/log; cần identity và secret management.
13. **Khác nhau giữa traffic routing canary và swap?** Canary phân phối một phần lưu lượng tới slot; swap đưa phiên bản đã chuẩn bị vào production theo thao tác phát hành.
14. **Vì sao vẫn cần Application Insights sau swap?** Để xác minh 5xx, latency, dependencies và các lỗi không thể phát hiện chỉ từ ping readiness.
15. **Một release có trạng thái "swap succeeded" đã đủ coi là hoàn tất chưa?** Chưa. Cần tiêu chí nghiệp vụ, giám sát và xác nhận của owner.

## 18. Tài liệu tham khảo

- [Azure App Service deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots) — tạo slot, swap, preview, sticky settings và warm-up.
- [Azure App Service overview](https://learn.microsoft.com/azure/app-service/overview) — nền tảng ứng dụng, App Service Plans và hosting.
- [Configure App Service app settings](https://learn.microsoft.com/azure/app-service/configure-common) — app settings và connection strings.
- [Azure App Service configuration reference](https://learn.microsoft.com/azure/app-service/reference-app-settings) — các application settings được hỗ trợ, bao gồm thiết lập warm-up theo kịch bản.
- [App Service health check](https://learn.microsoft.com/azure/app-service/monitor-instances-health-check) — health check instance và cách sử dụng.
- [Application Insights documentation](https://learn.microsoft.com/azure/azure-monitor/app/app-insights-overview) — telemetry cho release và điều tra lỗi.
- [App Service access restrictions](https://learn.microsoft.com/azure/app-service/app-service-ip-restrictions) — giới hạn truy cập ứng dụng và slot.
- [App Service Key Vault references](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references) — cấu hình secrets thông qua Azure Key Vault.
- [Azure App Service pricing](https://azure.microsoft.com/pricing/details/app-service/) — kiểm tra tier và chi phí hiện hành.

**Kết luận:** deployment slots giúp tách việc cài đặt phiên bản mới khỏi thời điểm đưa người dùng vào bản mới; warm-up giảm rủi ro cold start; swap đưa phiên bản đã chuẩn bị vào production mà không phải thay URL khách hàng. Để quy trình thực sự an toàn, cần hiểu sticky settings và target configuration trong warm-up, giữ migration tương thích ngược, kiểm soát background jobs, xác minh bằng telemetry và chuẩn bị rollback cho cả mã lẫn dữ liệu.
