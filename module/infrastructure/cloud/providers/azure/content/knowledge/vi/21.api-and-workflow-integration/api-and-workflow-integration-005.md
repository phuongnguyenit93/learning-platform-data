# Rate limit, quota, cache và chuyển đổi request

Một hệ thống đặt hàng trên Microsoft Azure có thể phục vụ API cho ứng dụng web, thiết bị di động và đối tác. Trong giờ cao điểm, một client gửi quá nhiều yêu cầu làm backend quá tải. Một đối tác khác vượt số lượt gọi được cấp cho tháng. Các màn hình danh mục sản phẩm liên tục đọc cùng một dữ liệu, gây truy vấn database lặp lại. Ngoài ra, phiên bản API cũ gửi trường **customer_id**, trong khi backend mới nhận **customerId**.

Bốn nhu cầu này có giải pháp tương ứng: **rate limit**, **quota**, **cache** và **chuyển đổi request**. Trên Azure, **Azure API Management (APIM)** cung cấp policy engine để xử lý các hành vi đó tại API gateway mà không phải viết lại mọi client. Nhưng cấu hình gateway đúng không có nghĩa backend tự an toàn: vẫn cần xác thực, phân quyền, kiểm tra dữ liệu, đo tải và thiết kế tính nhất quán.

Bài học thuộc chương **API và tích hợp quy trình** trong mô-đun **CLOUD_PROVIDERS_AZURE**. Lộ trình này khám phá Azure từ subscription, resource group và Microsoft Entra ID tới mạng ảo, compute, storage, dữ liệu, rồi triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng.

> **Phạm vi:** Bài học tập trung vào Azure API Management policies. Những đoạn XML bên dưới là ví dụ minh họa cần triển khai trước trên **APIM/API thử nghiệm**. Phạm vi tính năng, capacity, caching và hành vi có thể khác nhau theo tier, loại gateway và phiên bản dịch vụ; hãy đối chiếu tài liệu Microsoft Learn trước khi đưa vào production.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **rate limit** với **quota** theo mục tiêu bảo vệ, ngưỡng và khoảng thời gian.
2. Hiểu policy pipeline **inbound → backend → outbound → on-error** và phạm vi áp chính sách.
3. Sử dụng **rate-limit-by-key** và **quota-by-key** với khóa định danh đáng tin cậy.
4. Thiết kế **response caching** bằng **cache-lookup** và **cache-store**, hiểu TTL, cache key và cache invalidation.
5. Phân biệt cache response của gateway với cache của ứng dụng, CDN hoặc backend.
6. Dùng **rewrite-uri**, **set-header**, **set-query-parameter** và **set-body** để chuyển đổi request.
7. Hiểu ảnh hưởng của policy order, inheritance, authentication, dữ liệu nhạy cảm và lỗi 429/403.
8. Xây dựng quy trình lab, đo hiệu năng, chẩn đoán lỗi và dự toán chi phí APIM.

## 1. Azure API Management nằm ở đâu trong kiến trúc?

**Azure API Management** là nền tảng quản lý API, trong đó **gateway** nhận request từ consumer rồi áp những chính sách được cấu hình trước khi chuyển tới backend. APIM còn có API definitions, sản phẩm (products), subscription, developer experience và các công cụ quan sát theo khả năng của từng mô hình triển khai.

~~~text
Ứng dụng web / mobile / đối tác
                 |
                 | HTTPS request
                 v
       Azure API Management
         +--------------------------+
         | Authentication/validation|
         | Rate limit / Quota       |
         | Request transformation   |
         | Cache lookup             |
         | Backend routing          |
         | Response transformation  |
         | Cache store              |
         +--------------------------+
                 |
                 v
        Azure App Service / AKS /
        Azure Functions / backend khác
                 |
                 v
             Database / Storage
~~~

APIM có thể giảm tải backend, chuẩn hóa giao diện và giới hạn mức sử dụng. Nó **không thay thế**:

- Kiểm tra quyền truy cập từng đơn hàng ở backend.
- Cơ chế đảm bảo giao dịch và idempotency.
- Giới hạn kết nối database hoặc kiểm soát tài nguyên downstream.
- Chống DDoS ở các lớp hạ tầng, WAF phù hợp và quan sát ứng dụng.
- Thiết kế cache-consistency khi dữ liệu thay đổi.

### Gateway và management plane

| Thành phần | Vai trò |
|---|---|
| **APIM gateway** | Thực thi policies trên request/response thực tế |
| **Management plane/portal/API** | Tạo API, operation, product, policy và cấu hình |
| **Backend service** | Xử lý nghiệp vụ, truy vấn DB hoặc gọi dịch vụ khác |
| **Product/subscription** | Đóng gói API và quản lý truy cập/sử dụng theo mô hình APIM |
| **Diagnostics/monitoring** | Thu thập request metrics, errors và telemetry theo cấu hình |

Đừng nhầm quyền quản lý một APIM instance trên Azure Resource Manager với quyền gọi một API qua gateway. Hai lớp quyền có thể được kiểm soát độc lập.

## 2. Bốn kỹ thuật khác nhau thế nào?

| Kỹ thuật | Câu hỏi giải quyết | Đối tượng | Kết quả thường thấy |
|---|---|---|---|
| **Rate limit** | Client được gửi nhanh tối đa bao nhiêu request? | Tốc độ trong cửa sổ ngắn | Chặn phần vượt ngưỡng; thường trả **429 Too Many Requests** |
| **Quota** | Client được sử dụng tổng cộng bao nhiêu trong kỳ? | Tổng calls/bytes trong cửa sổ dài | Chặn khi hết hạn mức; với quota policy APIM thường trả **403 Forbidden** |
| **Cache** | Request nào có thể nhận lại response còn hợp lệ mà không gọi backend? | Dữ liệu/response theo key và TTL | Cache hit giảm latency và tải backend |
| **Request transformation** | Gateway cần đổi path/header/query/body thế nào trước khi gọi backend? | Nội dung và metadata HTTP | Backend nhận contract hoặc đường dẫn khác |

**Rate limit và quota không đồng nghĩa nhau.** Một client được phép gọi 10.000 lần/ngày vẫn có thể làm nghẽn backend nếu gửi cả 10.000 lần trong vài giây. Ngược lại, một client chỉ gọi 2 lần/giây nhưng kéo dài cả ngày có thể vượt quota tháng.

**Cache không phải rate limit.** Cache hit giúp giảm tải backend, nhưng nếu gateway vẫn nhận quá nhiều requests, cần bảo vệ tài nguyên gateway hoặc áp rate limit riêng.

**Transformation không phải validation.** Đổi tên một trường JSON không chứng minh giá trị của trường đó hợp lệ, được phép sử dụng hay an toàn.

## 3. Policy pipeline của APIM

Một policy document điển hình có bốn section:

~~~xml
<policies>
  <inbound>
    <base />
    <!-- Xác thực, giới hạn, biến đổi request, tra cache -->
  </inbound>
  <backend>
    <base />
    <!-- Chuyển request tới backend hoặc các policy backend -->
  </backend>
  <outbound>
    <base />
    <!-- Biến đổi response, lưu cache -->
  </outbound>
  <on-error>
    <base />
    <!-- Xử lý lỗi gateway/policy -->
  </on-error>
</policies>
~~~

### Vai trò các section

- **Inbound:** xử lý request đến gateway trước backend: validate token, giới hạn, chỉnh URI, header, query, request body, tra cache.
- **Backend:** điều khiển chuyển tiếp request, lựa chọn backend, retry/circuit-breaker theo policy và khả năng hỗ trợ.
- **Outbound:** xử lý response trả về: header/body response, cache-store, loại bỏ thông tin không muốn công khai.
- **On-error:** chạy khi quá trình thực thi policy/gateway gặp lỗi theo cơ chế APIM, không đồng nghĩa tất cả HTTP error status của backend đều tự động được xử lý tại đây.

### Thứ tự policy có ý nghĩa

Các policy trong một section được thực thi theo trình tự phù hợp với loại policy. Ví dụ nếu muốn tính mọi request vào rate limit kể cả cache hit, rate limit phải xuất hiện **trước cache-lookup**.

~~~text
Request
   |
   v
Validate identity
   |
   v
Rate limit / Quota
   |
   v
Rewrite/query/header transformation
   |
   v
Cache lookup
   | Hit                       | Miss
   v                           v
Cached response             Backend
                               |
                               v
                           Cache store
                               |
                               v
                            Response
~~~

Đây là **mô hình khái niệm**. Cache hit có thể làm gateway trả response sớm và bỏ qua các bước backend/outbound phía sau theo hành vi cache policy. Vì vậy các yêu cầu bắt buộc như xác thực, authorization thích hợp và throttling cần được đặt trước vị trí trả cache nếu chúng phải chạy cho mọi request.

## 4. Phạm vi policy và kế thừa bằng base

APIM policies có thể được áp ở những phạm vi quản lý như:

- **Global / all APIs** trong gateway/phạm vi thích hợp.
- **Workspace** khi mô hình APIM hỗ trợ.
- **Product** dành cho nhóm API/consumer theo product.
- **API**.
- **Operation**.

Một policy ở scope cụ thể có thể kế thừa các policy của cấp ngoài qua **base** theo quy tắc APIM. Thứ tự đặt **base** trong section có thể ảnh hưởng thứ tự thực thi logic của policy.

### Ví dụ rủi ro bỏ sót base

Giả sử ở scope global có validate JWT và giới hạn chung, còn operation chỉ thêm rewrite-uri. Nếu operation policy không kế thừa các policy cha theo cách dự kiến, request có thể không chịu các bước bảo vệ mà người quản trị tưởng là có.

**Không xóa thẻ base chỉ để làm XML ngắn hơn.** Trước khi thay đổi, dùng chức năng xem **effective policy** hoặc công cụ chẩn đoán tương ứng để xác nhận thực tế có những policy nào và thứ tự nào được áp dụng.

### Policy fragments

Với nhiều API cùng dùng quy tắc xác thực và header tiêu chuẩn, APIM hỗ trợ các cơ chế tái sử dụng như **policy fragments** trong phạm vi được hỗ trợ. Fragment giúp tránh sao chép một biểu thức hàng chục lần, nhưng mọi thay đổi fragment cần được kiểm thử trên **tất cả nơi sử dụng**.

## 5. Rate limiting là gì?

**Rate limit** giới hạn số request được phép trong một khoảng thời gian ngắn, ví dụ:

~~~text
Client A được phép 60 requests / 60 giây

Trong khoảng đo:
  1  ... 60: request được nhận nếu điều kiện khác thỏa
  61       : có thể bị từ chối bằng HTTP 429

Sau thời gian áp dụng:
  bộ đếm có thể trở lại trạng thái cho phép theo chính sách
~~~

Ví dụ này giải thích trực giác; **không phải mô tả thuật toán cửa sổ nội bộ chính xác của mọi gateway**. APIM dùng bộ đếm policy, hoạt động thực tế có thể chịu độ trễ cập nhật hoặc phân tán, đặc biệt ở nhiều gateway/unit/region.

### Trường hợp sử dụng

1. Bảo vệ backend trước burst từ một client.
2. Duy trì mức sử dụng hợp lý giữa các đối tác.
3. Giảm nguy cơ client lỗi lặp request vô hạn.
4. Phân chia hạng sản phẩm API: thử nghiệm 5 req/s, thương mại 50 req/s.
5. Tránh một tenant đơn lẻ chiếm toàn bộ năng lực của service dùng chung.

### Mã lỗi 429

Khi rate limit từ chối request, phản hồi điển hình là **429 Too Many Requests**. Client nên:

- Kiểm tra thông tin retry như **Retry-After** khi gateway cung cấp.
- Dùng exponential backoff với jitter.
- Không tự động retry vô hạn hoặc tạo nhiều request song song hơn.
- Phân biệt 429 từ APIM và 429 từ backend qua diagnostics/correlation ID.

Rate limit **không** cung cấp quyền tiếp tục gọi nếu token/JWT đã hết hạn hoặc client thiếu quyền đọc dữ liệu.

## 6. Policy rate-limit-by-key

Với nhiều client/tenant, nên gắn bộ đếm vào **khóa định danh** đáng tin, thay vì đếm tất cả yêu cầu vào cùng một bucket.

Ví dụ:

~~~xml
<policies>
  <inbound>
    <base />
    <rate-limit-by-key
      calls="30"
      renewal-period="60"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

**Ý nghĩa:** minh họa giới hạn 30 calls trong cửa sổ 60 giây cho một giá trị key. Khi APIM request có **Subscription.Id**, key dùng subscription ID; nếu không có subscription, ví dụ rơi về địa chỉ IP của request.

### Đây chỉ là policy mẫu

Trong production, cần quyết định rõ:

- API có **bắt buộc subscription** không?
- Client dùng **JWT đã được xác thực** hay API key?
- Một subscription đại diện cho một ứng dụng, một partner hay nhiều người dùng?
- Có trường hợp tất cả anonymous requests phải chia sẻ một hạn mức chung không?
- Có reverse proxy/CDN khiến nhiều người dùng cùng IP không?

Dùng IP làm fallback **không tạo nhận diện tenant chính xác**; NAT có thể gom nhiều người dùng vào cùng IP, còn một người dùng có thể thay đổi IP.

### Không dùng header tự khai báo làm key mà không xác thực

Ví dụ nguy hiểm:

~~~xml
<!-- KHÔNG AN TOÀN nếu header do client tự chọn và không được xác minh -->
<rate-limit-by-key
  calls="30"
  renewal-period="60"
  counter-key="@(context.Request.Headers.GetValueOrDefault(&quot;X-Tenant-Id&quot;, &quot;unknown&quot;))" />
~~~

Client có thể đổi X-Tenant-Id mỗi request để né giới hạn. Key nên đến từ subscription đã xác thực, token claims đã validate hoặc identity do gateway thiết lập và tin cậy.

### Các tùy chọn nâng cao

APIM rate-limit-by-key có thể hỗ trợ những thuộc tính phản hồi và điều kiện đếm như **retry-after-header-name**, **remaining-calls-header-name** hoặc **increment-condition/increment-count** tùy policy. Khi cần cung cấp thông tin hạn mức cho client, hãy dùng thuộc tính được hỗ trợ thay vì tự bịa số còn lại.

**Lưu ý:** Bộ đếm có thể được cập nhật sau khi response trong một số tình huống sử dụng increment-condition hoặc policy phân tán. Đừng dùng rate-limit-by-key như **hệ thống khóa giao dịch tuyệt đối** hay đảm bảo mọi thời điểm chính xác một request cuối cùng đều bị chặn.

## 7. Rate limit theo subscription, product và API

Ngoài **rate-limit-by-key**, APIM có **rate-limit** theo cơ chế subscription và product/API trong những mô hình được hỗ trợ.

Ví dụ khái niệm:

~~~xml
<rate-limit calls="10" renewal-period="60" />
~~~

Trong những ngữ cảnh phù hợp, quy tắc giới hạn có thể được áp riêng cho sản phẩm API, ví dụ sandbox có mức thấp hơn production. Tuy nhiên:

1. Policy scope không tự quyết định danh tính người gọi; cần kiểm tra cách gateway xác định subscription.
2. Nếu API không yêu cầu subscription, phải xem cơ chế rate-limit-by-key với identity phù hợp.
3. Có nhiều sản phẩm/subscription có thể dẫn tới khác biệt trong cách đếm.
4. Không mặc định tất cả policy/cấp áp dụng đều có trên mọi tier hoặc self-hosted gateway.

Khi đặt cả rate-limit và rate-limit-by-key, hãy kiểm tra **effective policy** để tránh chặn hai lần ngoài chủ đích.

## 8. Quota là gì?

**Quota** giới hạn **tổng lượng sử dụng** trong một kỳ, chẳng hạn:

- 50.000 API calls trong một ngày.
- 1.000.000 calls trong một kỳ dài hơn theo giới hạn policy.
- Tổng bandwidth dùng trong khoảng thời gian khi policy hỗ trợ.

Ví dụ:

~~~text
Partner A:
  Quota = 10.000 calls / 24 giờ
  Đã dùng = 9.998

Hai calls tiếp theo hợp lệ có thể tiêu hết quota.
Các calls sau bị từ chối cho đến khi quota được gia hạn.
~~~

Quota phù hợp với **fair usage** và mô hình thương mại, nhưng không thể thay thế rate limit chống burst.

### Hành vi khi vượt quota

Với các quota policies của APIM, phản hồi thường là **403 Forbidden** khi đã hết quota. Đừng tự mặc định nó là 429 trong mọi trường hợp như rate limiting. Khi thiết kế client, kiểm tra response/status thực, headers và hợp đồng API được công bố.

**403 do quota** khác **403 do quyền truy cập**. Client không nên tự đổi token hoặc tăng số lần retry tức thì nếu kỳ quota chưa kết thúc.

## 9. Policy quota-by-key

Ví dụ giới hạn 10.000 calls trong một cửa sổ 86.400 giây:

~~~xml
<policies>
  <inbound>
    <base />
    <quota-by-key
      calls="10000"
      renewal-period="86400"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

Đây là **cửa sổ theo cơ chế policy**, không nên mô tả ngay thành “đặt lại chính xác lúc 00:00 mỗi ngày theo giờ Việt Nam” nếu không thiết kế mốc bắt đầu tương ứng. Phạm vi renewal period và các tùy chọn như **first-period-start** cần kiểm tra theo policy phiên bản đang dùng.

### Nếu cần quota theo tenant

Nếu mỗi tenant có nhiều subscription hoặc ứng dụng, quota theo **subscription ID** sẽ đếm riêng từng subscription, chưa chắc đúng mong muốn một tenant có tổng ngân sách chung. Cần lấy **tenant ID đã xác thực** hoặc ánh xạ đáng tin cậy từ subscription/app vào một tenant và dùng cùng counter-key.

Nếu backend có nhiều cổng truy cập ngoài APIM, quota ở gateway này **không tự bao phủ** những request đi đường khác.

### Không dùng quota như hóa đơn kế toán duy nhất

Quota policy hữu ích để giới hạn sử dụng, nhưng hệ thống tính tiền theo hợp đồng cần **metering/audit pipeline** có đầy đủ đặc tính nhất quán, xử lý trùng, đối chiếu và các quy tắc nghiệp vụ. Đừng lấy số lượng quota counter tức thời làm nguồn duy nhất để xuất hóa đơn cho khách hàng.

## 10. Kết hợp rate limit và quota

Giả sử API có:

- Rate limit: **30 calls / 60 giây** theo subscription.
- Quota: **10.000 calls / 24 giờ** theo subscription.

~~~text
Client gọi API
      |
      v
Xác thực và xác định subscription/tenant
      |
      v
Rate limit: có vượt ngưỡng ngắn hạn?
      | Có -> trả 429
      | Không
      v
Quota: còn ngân sách trong kỳ?
      | Không -> trả 403 theo quota policy
      | Có
      v
Xử lý tiếp: cache/transform/backend
~~~

Ví dụ policy:

~~~xml
<policies>
  <inbound>
    <base />
    <rate-limit-by-key
      calls="30"
      renewal-period="60"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />
    <quota-by-key
      calls="10000"
      renewal-period="86400"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

### Những câu hỏi cần quyết định

1. Request trả lỗi 4xx/5xx có tính vào hạn mức không?
2. Cache hit có tính vào quota/rate limit không?
3. Hạn mức dùng theo user, application, subscription hay tenant?
4. Premium customer và free customer có cùng giới hạn không?
5. Nếu cùng một subscription gọi nhiều API, hạn mức dùng chung hay tách riêng?
6. Nhiều region/gateway có chia sẻ counter đúng như yêu cầu không?

Với APIM, cách xử lý counter cụ thể phụ thuộc policy và vị trí áp dụng. Nếu muốn chỉ đếm những request thỏa điều kiện nhất định, phải thiết kế theo những thuộc tính/khả năng thực tế của chính policy, không giả định tất cả bộ đếm tự phản ánh “thành công nghiệp vụ”.

## 11. Bộ đếm không đồng nghĩa giới hạn concurrency

Rate limit theo số request/giây chưa chắc chặn được một tình huống:

~~~text
Một request được cho phép
     |
     v
Backend giữ kết nối trong 10 phút
     |
     v
Nhiều request tương tự tích tụ
~~~

Một API có rate limit thấp nhưng từng request rất lâu vẫn có thể làm cạn **connection pool, worker threads hoặc database sessions**. Ngược lại, nhiều request cache hit có thể ít tác động backend hơn.

Tổ chức cần xem xét:

- **Concurrency limits** hoặc giới hạn tài nguyên tại tầng gateway/backend khi khả dụng.
- Timeout phù hợp với nghiệp vụ.
- Queue-based load leveling để xử lý tác vụ dài bất đồng bộ.
- Circuit breaker, retry/backoff và autoscale theo capacity.
- Giới hạn tải ở downstream database và API bên thứ ba.

Rate limit bảo vệ một chiều của vấn đề, không phải đầy đủ năng lực điều phối tải.

## 12. Cache trong API gateway giải quyết vấn đề gì?

Nhiều API GET có response lặp lại giữa các client:

- Danh mục quốc gia, đơn vị đo lường.
- Danh mục sản phẩm công khai, thay đổi theo chu kỳ.
- Cấu hình hiển thị công khai.
- Dữ liệu tổng hợp không cần luôn nhất quán đến từng giây.

Nếu mỗi request đều gọi backend và database, hệ thống lãng phí thời gian và tài nguyên.

~~~text
Client GET /catalog?category=books
              |
              v
       APIM cache lookup
         |          |
       HIT         MISS
         |          |
         v          v
     Trả nhanh    Backend + database
                    |
                    v
                Cache store
                    |
                    v
                 Response
~~~

**Cache hit** có thể giảm latency, load và chi phí backend. Nhưng thông tin lưu trong cache có thể **stale** trong khoảng TTL, và cache sai key có thể làm lộ dữ liệu giữa các khách hàng.

## 13. Cache-lookup và cache-store

APIM hỗ trợ các policy **cache-lookup** và **cache-store** để tra và lưu response theo tính năng caching của gateway.

Một policy mẫu cho GET danh mục công khai:

~~~xml
<policies>
  <inbound>
    <base />
    <cache-lookup
      vary-by-developer="false"
      vary-by-developer-groups="false"
      downstream-caching-type="none">
      <vary-by-query-parameter>category</vary-by-query-parameter>
      <vary-by-header>Accept</vary-by-header>
    </cache-lookup>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
    <cache-store duration="60" />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

**Ý nghĩa:**

- **cache-lookup** tra response cache cho request.
- **vary-by-query-parameter** phân biệt các danh mục, ví dụ books và shoes.
- **vary-by-header Accept** phân biệt trường hợp response phụ thuộc định dạng chấp nhận.
- **cache-store duration="60"** minh họa TTL 60 giây cho response đủ điều kiện.
- **downstream-caching-type="none"** không yêu cầu client/proxy downstream lưu cache dựa trên policy này.

### Điều kiện của ví dụ

Ví dụ này giả định API **chỉ trả dữ liệu công khai, không cá nhân hóa, không chứa secrets**, và chỉ áp cho endpoint GET được phép cache. **Không áp nguyên vào API /me, /accounts/{id}, /orders/{id}** hoặc response chứa dữ liệu tenant khác nếu chưa thiết kế phân vùng cache an toàn.

Cache policies có điều kiện về loại response, phương thức, headers và sự hỗ trợ của tier/cache backend. Không diễn giải TTL=60 như cam kết mọi response sẽ được lưu và truy xuất chính xác trong 60 giây; cache có thể bị evict, chưa kịp store hoặc không đủ điều kiện.

### Internal cache và external cache

APIM có các tùy chọn cache nội bộ hoặc cache ngoài dựa trên tier và cấu hình (ví dụ Redis/managed cache được hỗ trợ). Cần đánh giá:

- Tier/gateway hiện có hỗ trợ cache nào?
- Internal cache có giới hạn capacity và phạm vi chia sẻ theo gateway/region ra sao?
- Khi scale gateway hoặc triển khai multi-region, các cache instance có nhất quán không?
- Có cần external cache chia sẻ theo môi trường đã được hỗ trợ?
- Cache data được bảo vệ bằng network, auth và retention như thế nào?

**Cache là thành phần hiệu năng, không phải nguồn dữ liệu chính**. Khi cache mất dữ liệu, hệ thống phải có khả năng quay về backend mà không trả kết quả sai hoặc tạo sự cố dây chuyền.

## 14. Thiết kế cache key và vary-by

Một cache key tốt phản ánh **mọi yếu tố thực sự làm thay đổi response**.

Ví dụ:

~~~text
GET /v1/catalog?category=books&lang=vi
GET /v1/catalog?category=books&lang=en

Nếu response phụ thuộc lang:
  Cache key phải phân biệt lang=vi và lang=en.
~~~

Nếu chính sách chỉ vary theo category nhưng response thay đổi theo lang, một người dùng có thể nhận dữ liệu sai ngôn ngữ.

### Những chiều cần xem xét

| Chiều | Cần vary khi nào? |
|---|---|
| **URL/path** | Endpoint hoặc tài nguyên khác |
| **Query parameter** | category, lang, currency, page, sort thực sự ảnh hưởng response |
| **Accept / content negotiation** | JSON/XML hoặc định dạng phản hồi khác |
| **API version** | Phiên bản hợp đồng response khác |
| **Tenant / user identity** | Response được cá nhân hóa hoặc phân quyền |
| **Authorization state** | Người dùng có quyền dữ liệu khác nhau |
| **Feature flag/locale** | Nội dung phụ thuộc cấu hình theo nhóm |

### Rủi ro lộ dữ liệu liên tenant

Nếu response của tenant A bị cache dưới key chung và tenant B nhận lại response đó, gateway có thể làm lộ dữ liệu dù backend vẫn phân quyền đúng ở lúc tạo response đầu tiên.

**Ưu tiên không cache response riêng tư tại gateway** nếu không có lý do rõ ràng và cơ chế cô lập key đã được kiểm chứng. Nếu thực sự cache dữ liệu được phân quyền, phải bảo đảm kiểm tra identity chạy trước cache-lookup, cache key phân vùng đúng theo tenant/user và chính sách không cho response nhạy cảm rò qua browser/proxy.

### Authorization header không phải key an toàn mặc định

Đưa nguyên access token vào cache key có thể gây tăng kích thước key, lộ dữ liệu hoặc tỷ lệ cache hit thấp; token cũng có thể thay đổi dù người dùng không đổi. Nên dựa trên identity đã validate và thiết kế key an toàn, hoặc không cache dữ liệu nhạy cảm.

## 15. Cache invalidation và thời gian dữ liệu cũ

TTL giới hạn thời gian cache được xem là hợp lệ theo policy, nhưng **không tự biết dữ liệu gốc đã thay đổi**.

~~~text
10:00  Backend trả giá sản phẩm = 100.000đ
10:00  APIM cache response 60 giây
10:20  Giá thay đổi tại backend = 90.000đ
10:30  Client gọi lại
       -> vẫn có thể nhận giá cũ trong cache
11:00  Entry hết hạn theo mô hình minh họa
       -> cache miss, gọi backend lấy dữ liệu mới
~~~

**Các mốc là giả định bằng giây tương đối để minh họa TTL**, không phải khẳng định hệ thống cache phải hết hạn đúng một phút theo đồng hồ treo tường trong mọi điều kiện.

### Các cách giữ dữ liệu phù hợp

1. **TTL ngắn** cho danh mục thay đổi tương đối thường xuyên.
2. **Không cache** response đòi tính mới rất cao, như số dư thanh toán tức thời.
3. **Cache versioning/key rotation** khi nguồn dữ liệu có version rõ ràng.
4. **Cache invalidation** theo khả năng tính năng/tooling và kiến trúc đang dùng.
5. **ETag/conditional requests** nếu backend/contract hỗ trợ, kiểm tra tác động tới gateway cache.
6. Tách dữ liệu **public reference** khỏi dữ liệu cá nhân hóa.

APIM có các policy liên quan caching ngoài response cache như **cache-lookup-value**, **cache-store-value** và **cache-remove-value** cho các trường hợp lưu/tra giá trị theo key; không giả định thao tác remove-value sẽ tự xóa mọi response cache entry dùng cache-lookup.

### Cache stampede

Khi một entry phổ biến hết TTL, nhiều request có thể đồng thời miss rồi cùng gọi backend. Điều này gọi là **cache stampede**. Khắc phục có thể cần:

- TTL có kiểm soát và jitter theo kiến trúc.
- Single-flight/coalescing hoặc request collapsing ở tầng hỗ trợ.
- Cache warm-up khi triển khai/tăng traffic.
- Rate limit và capacity tại backend.
- Tách các query có cardinality cao khỏi cache.

APIM cache-store có thể thực hiện lưu bất đồng bộ; **request ngay sau cache miss chưa chắc đã hit**. Đừng đặt SLA dựa trên giả định request thứ hai luôn được cache.

## 16. Cache response và cache giá trị

Hai mô hình phổ biến:

| Mô hình | Dùng để | Policy tiêu biểu |
|---|---|---|
| **Response cache** | Trả lại cả HTTP response cho request tương đương | cache-lookup / cache-store |
| **Value/fragment cache** | Lưu một giá trị trung gian để policy hoặc backend dùng lại | cache-lookup-value / cache-store-value |

Ví dụ một policy truy vấn token/metadata hoặc danh sách cấu hình từ dịch vụ phụ, rồi muốn nhớ một giá trị tạm thời. **Value cache** có thể thích hợp hơn response cache, nhưng cần hiểu cách xác định key, dữ liệu nhạy cảm, TTL và invalidation.

Không đưa refresh token, mật khẩu hay thông tin xác thực dài hạn vào value cache chỉ vì nó tiện. Những giá trị nhạy cảm phải tuân thủ chính sách quản lý bí mật và kiểm soát quyền chặt chẽ.

## 17. Policy order: rate limit và cache tác động lẫn nhau

Giả sử một request GET danh mục được phép cache 60 giây. Có hai cách xử lý với mục tiêu khác nhau.

### Cách A: rate limit trước cache

~~~text
Validate -> Rate limit -> Cache lookup -> (hit/miss) -> Response
~~~

Mọi request phải đi qua giới hạn, kể cả cache hit. Cách này phù hợp khi muốn bảo vệ gateway hoặc duy trì fair-use policy, tránh client miễn giới hạn chỉ vì cache.

### Cách B: cache trước rate limit

~~~text
Validate -> Cache lookup -> nếu miss mới vào Rate limit
~~~

Với cách thực thi cache hit trả response sớm, một số request có thể không đến rate-limit ở phía sau. Điều đó có thể làm mất ý nghĩa hợp đồng “mỗi người dùng chỉ được N request/phút”.

### Chọn cách nào?

Nếu hợp đồng API tính theo số lần client gọi, **rate limit và quota thường cần đặt trước cache-lookup** để client không vượt hạn mức chỉ nhờ cache. Nếu quota được định nghĩa theo **số lần backend thực sự bị gọi**, phải thiết kế counter theo mục tiêu đó, xác nhận policy thực thi trên cache miss và kiểm thử kết quả. Không gán tên “quota” rồi tự suy luận nó sẽ trừ đúng loại call doanh nghiệp tính tiền.

## 18. Chuyển đổi request là gì?

**Request transformation** thay đổi request trước khi backend xử lý, ví dụ:

- Chuyển đường dẫn public **/v1/products** thành backend **/internal/catalog/items**.
- Thêm hoặc chuẩn hóa header **X-Correlation-Id**.
- Thêm query parameter **api-version** để hỗ trợ backend.
- Đổi tên trường JSON từ **customer_id** sang **customerId**.
- Loại hoặc chuẩn hóa thông tin không cần thiết theo policy được phê duyệt.
- Chọn backend khác nhau theo version hoặc điều kiện routing.

~~~text
Client:
POST /api/v1/orders
Body: {"customer_id":"C42","amount":100}
             |
             v
       API Management
       - rewrite path
       - set backend query
       - map customer_id -> customerId
       - add correlation ID
             |
             v
Backend:
POST /internal/orders?api-version=2024-06-01
Body: {"customerId":"C42","amount":100}
~~~

APIM giúp **che giấu thay đổi backend khỏi client** trong giai đoạn chuyển đổi. Tuy nhiên, khi quy tắc mapping trở nên phức tạp, nên xem xét versioned API contract hoặc một integration service thay vì nhồi toàn bộ logic nghiệp vụ vào policy XML.

## 19. rewrite-uri: đổi đường dẫn backend

Policy **rewrite-uri** thay đổi URL path/query gửi tới backend theo template.

~~~xml
<rewrite-uri
  template="/internal/catalog/items"
  copy-unmatched-params="true" />
~~~

Nếu public API nhận:

~~~text
GET /v1/catalog?category=books&page=2
~~~

Backend có thể cần:

~~~text
GET /internal/catalog/items?category=books&page=2
~~~

Hành vi phụ thuộc API URL suffix, operation template, backend base URL và query rewrite. Ví dụ giả định backend đã được cấu hình đúng đường dẫn gốc.

### Chú ý copy-unmatched-params

- Nếu true, những query parameters không được khai báo/khớp trong operation template có thể được giữ theo hành vi policy.
- Nếu false, một số query parameters không khớp có thể bị bỏ, làm thay đổi hợp đồng.
- Backend có thể không cho phép client tự truyền tham số nhạy cảm như **isAdmin=true**.

Đừng bật copy mọi query parameter mà không có danh sách kiểm soát. **Rewrite không phải input validation**; các trường backend nhạy cảm vẫn phải được kiểm tra/bảo vệ.

## 20. set-header: chuẩn hóa và truyền correlation

Ví dụ thêm header dùng cho tracing:

~~~xml
<set-header name="X-Correlation-Id" exists-action="override">
  <value>@(context.RequestId.ToString())</value>
</set-header>
~~~

**context.RequestId** là định danh request theo context APIM dùng để tương quan việc gọi. Đây là ví dụ sinh identifier tại gateway, không phụ thuộc client cung cấp một header tùy ý.

### Trường hợp khác

- Thêm header nhận diện version của hợp đồng đã qua gateway.
- Gắn thông tin tenant đã xác thực để backend tham chiếu, với ràng buộc trust.
- Loại header nội bộ không được phép công khai ra Internet.
- Chuyển header theo tên mới nếu backend đổi API contract.

**Cảnh báo:** không lấy giá trị client tự gửi trong header **X-Admin**, **X-Tenant-Id** hay **X-User-Role** rồi chuyển tới backend như danh tính đã xác thực. Nếu backend tin các header này, phải bảo đảm gateway xóa/ghi đè giá trị không đáng tin và đường backend không thể bị gọi trực tiếp để giả mạo.

### Header không phải secret store

Không nhúng mã truy cập vĩnh viễn vào policy XML. Khi cần thông tin bí mật, sử dụng **named values** được bảo vệ, tích hợp Key Vault hoặc managed identity theo tính năng hỗ trợ; tránh ghi ra logs/tracing.

## 21. set-query-parameter: chỉnh query có kiểm soát

Giả sử backend cần query **api-version=2024-06-01**, còn client cũ không biết tham số này:

~~~xml
<set-query-parameter name="api-version" exists-action="override">
  <value>2024-06-01</value>
</set-query-parameter>
~~~

**exists-action="override"** giúp đảm bảo gateway gửi giá trị do chính sách quyết định, thay vì tin giá trị api-version do caller tự truyền.

### Những điều phải thử

1. Client không truyền api-version.
2. Client truyền api-version hợp lệ.
3. Client truyền api-version cố tình sai.
4. Query có nhiều tham số khác như category, page, sort.
5. Query có tên lặp hoặc ký tự URL-encoded.

Nếu backend yêu cầu tham số được ký bằng HMAC hoặc signature được tính từ URL, thay đổi query sau khi ký có thể làm signature không hợp lệ. Phải thiết kế auth/signing ở đúng điểm và có kiểm chứng.

## 22. set-body: chuyển đổi JSON request

Khi backend nâng từ **customer_id** sang **customerId**, APIM có thể biến đổi body bằng policy expressions ở những trường hợp phù hợp.

### Ví dụ minh họa

~~~xml
<set-body>@{
    var payload = context.Request.Body.As<JObject>(preserveContent: true);
    if (payload["customer_id"] != null)
    {
        payload["customerId"] = payload["customer_id"];
        payload.Remove("customer_id");
    }
    return payload.ToString();
}</set-body>
~~~

Ví dụ:

~~~json
{
  "customer_id": "C42",
  "amount": 100
}
~~~

Trở thành:

~~~json
{
  "customerId": "C42",
  "amount": 100
}
~~~

### Giới hạn và cảnh báo

- Đây là **chuyển đổi cấu trúc**, không chứng minh customer ID hợp lệ hoặc amount được phép.
- **JObject** thuộc bộ kiểu policy expressions hỗ trợ trong APIM; đoạn này giả định body là JSON object hợp lệ.
- Body rỗng, JSON array, dữ liệu không phải JSON hoặc payload hỏng cần được xử lý bằng validation/error response phù hợp.
- **preserveContent: true** hữu ích khi đọc stream body và còn cần dùng nội dung sau đó; phải cân nhắc bộ nhớ và kích thước payload.
- Chuyển đổi body có thể tốn CPU/memory và ảnh hưởng latency, đặc biệt với payload lớn.
- Không sửa dữ liệu **đã được client ký** rồi mong signature cũ vẫn đúng.
- Nếu backend có request compression/streaming, cần xác minh các policy có hỗ trợ dạng payload đang dùng hay không.

Đối với file hàng trăm MB, thường tốt hơn để client upload thẳng tới Blob Storage bằng cơ chế ủy quyền có kiểm soát, rồi phát event hoặc gửi job xử lý, thay vì yêu cầu APIM parse/transform toàn bộ bytes.

## 23. Chuyển đổi response và giữ hợp đồng API

Ngoài request, APIM có thể chỉnh response trong **outbound**.

Ví dụ thêm header version:

~~~xml
<set-header name="X-Api-Contract-Version" exists-action="override">
  <value>v1</value>
</set-header>
~~~

Bạn có thể dùng những policy đáp ứng schema/hợp đồng, chuyển đổi JSON/XML hoặc loại headers được cho phép tùy yêu cầu. Nhưng cần xác định rõ:

- Content-Type có đúng với response body mới không?
- Status code có thay đổi không và client có phụ thuộc không?
- ETag/Last-Modified hoặc Content-Length có còn hợp lệ không?
- Response có được cache ở gateway/proxy/browser không?
- Có dữ liệu nhạy cảm bị thêm vào log hoặc response không?

Một transform “chỉ thêm trường JSON” có thể phá chữ ký response hoặc làm cache key/ETag không còn khớp. Phải kiểm thử contract từ phía client, không chỉ xem backend trả HTTP 200.

## 24. Kết hợp policy trong một API công khai

Giả sử API danh mục công khai **GET /v1/catalog**, backend thực là **/internal/catalog/items** và cần api-version. Client có subscription key để giới hạn sử dụng.

### Policy tổng hợp minh họa

~~~xml
<policies>
  <inbound>
    <base />

    <!-- Đếm theo subscription, fallback IP chỉ dùng cho lab. -->
    <rate-limit-by-key
      calls="30"
      renewal-period="60"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />

    <quota-by-key
      calls="10000"
      renewal-period="86400"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />

    <set-header name="X-Correlation-Id" exists-action="override">
      <value>@(context.RequestId.ToString())</value>
    </set-header>

    <rewrite-uri
      template="/internal/catalog/items"
      copy-unmatched-params="true" />

    <set-query-parameter name="api-version" exists-action="override">
      <value>2024-06-01</value>
    </set-query-parameter>

    <cache-lookup
      vary-by-developer="false"
      vary-by-developer-groups="false"
      downstream-caching-type="none">
      <vary-by-query-parameter>category</vary-by-query-parameter>
      <vary-by-query-parameter>page</vary-by-query-parameter>
      <vary-by-header>Accept</vary-by-header>
    </cache-lookup>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
    <cache-store duration="60" />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

**Điều kiện bắt buộc để ví dụ có ý nghĩa:**

1. API trả **dữ liệu công khai giống nhau cho mọi subscription**, không trả dữ liệu user-specific.
2. API operation dùng GET; không ghép với POST/PUT thay đổi dữ liệu.
3. Query category, page, Accept và api-version được xử lý phù hợp; nếu response còn phụ thuộc lang/currency/feature flag, cần bổ sung key.
4. Backend URL đã được cấu hình chính xác.
5. Cơ chế caching hiện có trên tier/gateway và được bật.
6. Subscription/identity đã được kiểm tra trước khi dùng để phân biệt counter.
7. Cache-hit behavior, policy order và policy inheritance đã được nghiệm thu.

### Vì sao cache key phải phản ánh query backend?

Nếu public request **category=books** và **category=shoes** được rewrite cùng một path nhưng cache không phân biệt category, response có thể bị dùng nhầm. Policy vary-by theo category nhằm tránh lỗi này.

### Khi nào không nên dùng policy tổng hợp?

Đừng áp cùng một policy cho **POST /payments** hoặc **GET /users/me**. Payments không nên có response cache tổng quát; dữ liệu người dùng không được dùng chung cache key. Hãy thiết kế policy theo **API operation và mức nhạy cảm** thay vì gắn một khối XML cho mọi API.

## 25. Xác thực và phân quyền phải đứng đúng vị trí

Trong APIM, **subscription key** hỗ trợ quản lý truy cập/mức sử dụng API theo mô hình sản phẩm, nhưng nó **không thay thế** xác thực người dùng cuối hoặc quyền xem từng tài nguyên.

Một API đơn hàng có thể yêu cầu:

1. Kiểm tra JWT từ Microsoft Entra ID hoặc identity provider phù hợp.
2. Xác nhận issuer, audience, signature, expiration và những claim bắt buộc.
3. Xác định tenant/user đã xác thực.
4. Áp rate limit theo tenant hoặc subscription hợp lệ.
5. Chỉ cache khi có mô hình phân vùng dữ liệu không thể rò rỉ.
6. Backend kiểm tra quyền đọc/sửa **đúng orderId**.

~~~text
Request -> JWT validation -> tenant/user context
                         |
                         v
                  Rate limit / Quota
                         |
                         v
                  Cache/Transformation
                         |
                         v
                  Backend authorization
~~~

### Không lấy thông tin nhạy cảm từ request chưa xác thực

Một client có thể tự gửi header **X-User-Id=admin** hoặc query **tenantId=other**. Nếu gateway dùng giá trị đó làm counter-key, cache key hoặc header tin cậy gửi backend, có nguy cơ vượt giới hạn và truy cập dữ liệu trái phép.

Dùng claims đã được kiểm chứng, subscription đã xác nhận hoặc mapping ở nguồn tin cậy. Kiểm tra mọi đường đi cho phép gọi backend ngoài APIM; nếu backend cho phép truy cập trực tiếp không qua gateway, chính sách APIM có thể bị bỏ qua.

## 26. Policy XML và policy expressions: giới hạn an toàn

APIM policy XML có thể chứa **C# policy expressions** trong các thuộc tính/giá trị hỗ trợ, ví dụ:

~~~xml
<set-header name="X-Gateway-Request-Id" exists-action="override">
  <value>@(context.RequestId.ToString())</value>
</set-header>
~~~

Các biểu thức phải tuân theo tập API/.NET types mà APIM hỗ trợ. Không giả định có thể dùng tùy ý mọi thư viện C# hoặc gọi network theo cách một ứng dụng .NET thông thường.

### Các rủi ro khi viết expression

- **Null reference:** Subscription hoặc User có thể không tồn tại ở một số request.
- **Unexpected body format:** parse JObject trên XML/empty body gây lỗi.
- **Tốn CPU/memory:** xử lý body lớn tại gateway.
- **Exception:** làm request thất bại trước khi tới backend.
- **Secrets in trace:** logging những biến chứa token làm lộ dữ liệu.
- **Inconsistent scope:** policy global áp vào API không cùng contract.

Hãy kiểm tra biểu thức trên test requests bao gồm hợp lệ, thiếu trường, sai kiểu, auth lỗi và payload lớn.

### Tránh logic nghiệp vụ quá phức tạp tại gateway

APIM thích hợp với **cross-cutting concerns**: auth, routing, giới hạn, caching, header/path transformation. Logic nghiệp vụ có nhiều state, transaction, retry dài hoặc tích hợp nhiều hệ thống thường phù hợp hơn trong backend, Azure Functions, Logic Apps hoặc service chuyên dụng.

## 27. Quy trình triển khai an toàn trên Azure portal

Lab dưới đây chỉ dùng **APIM instance và API thử nghiệm đã được cấp phép**, không thay đổi production. APIM và backend có thể phát sinh chi phí ngay cả khi chỉ triển khai lab.

### Bước 1: chuẩn bị API thử nghiệm

1. Chọn subscription/resource group dành cho lab.
2. Xác minh APIM instance, tier và gateway đang sử dụng.
3. Tạo hoặc chọn API **catalog-lab** với operation **GET /v1/catalog**.
4. Backend test trả response đơn giản có category và thời gian xử lý.
5. Nếu dùng subscription, tạo tài khoản/subscription lab được phép.
6. Bật diagnostics/log phù hợp và tránh ghi secrets.

### Bước 2: đo baseline

Gửi một số GET request với category khác nhau:

- category=books.
- category=shoes.
- category=books&page=2.

Ghi lại status, latency, correlation ID và số lần backend thực sự được gọi. **Chưa bật cache** để có số liệu nền.

### Bước 3: thêm rate limit trước

Tại policy editor ở scope API/operation phù hợp, thêm **rate-limit-by-key** mức thấp (ví dụ 5 calls/60 giây) cho client lab. Xác nhận request trong hạn mức thành công và request vượt ngưỡng nhận **429**.

Chỉ dùng mức thấp ở scope lab, không đặt mức này global cho mọi API trong subscription sản xuất.

### Bước 4: thêm quota

Thêm **quota-by-key** trên scope lab với ngưỡng có thể kiểm thử. Lưu ý quota counter có thời gian gia hạn; không làm đầy quota production chỉ để quan sát lỗi.

Ghi lại thực tế status, headers và thời điểm có thể tiếp tục gọi, thay vì suy đoán quota sẽ reset ngay khi bạn đổi policy XML.

### Bước 5: thêm cache

Chỉ với operation GET dữ liệu public, thêm **cache-lookup** và **cache-store**. Gửi các GET trùng nhau, đo số lần backend được gọi và latency. Kiểm tra:

- category khác nhau không trả nhầm dữ liệu.
- response không chứa dữ liệu riêng tư.
- cache hit không bỏ qua những kiểm soát bắt buộc.
- sau khi TTL hết, dữ liệu backend mới có thể được lấy lại.

### Bước 6: thêm transformation

Thử rewrite-uri sang path backend khác; thêm api-version bằng set-query-parameter; thêm correlation header bằng set-header. Với POST JSON, dùng **API test riêng** để thử set-body; không dùng chung cache GET cho POST.

### Bước 7: đánh giá và thu hồi

Lưu bản policy trước/sau, so sánh effective policy, các test cases và metrics. Dọn tài nguyên lab đúng phạm vi sau khi hoàn thành, không xóa APIM instance hoặc resource group có workload khác.

## 28. Kiểm thử API bằng curl

Những lệnh HTTP dưới đây **gọi API thật** và có thể tạo request count/chi phí. Chỉ chạy với API lab được phê duyệt.

~~~bash
# Gán APIM_SUBSCRIPTION_KEY bằng cơ chế bí mật an toàn
# tại môi trường lab; không lưu khóa trong script/repository.

curl --request GET --include \
  --header "Ocp-Apim-Subscription-Key: $APIM_SUBSCRIPTION_KEY" \
  "https://<APIM_GATEWAY_HOST>/catalog/v1/catalog?category=books"
~~~

Kiểm tra:

- HTTP status.
- Response headers như Retry-After nếu gateway có.
- X-Correlation-Id/X-Api-Contract-Version theo policy.
- Nội dung JSON đúng category.
- Latency qua nhiều lần gọi.

### Kiểm thử rate limit

~~~text
Kịch bản trên API lab: 5 calls / 60 giây

Request 1..5: chấp nhận nếu không có lỗi khác
Request 6: kiểm tra HTTP 429 và thông tin retry
Chờ đến khi policy cho phép:
  gọi lại, xác minh hoạt động tiếp
~~~

Đừng viết stress loop hàng nghìn request vào APIM mặc định. Khi load test cần công cụ và ngân sách đã phê duyệt, giới hạn tốc độ, kịch bản dừng và người giám sát.

### Kiểm thử cache

~~~text
GET /catalog?category=books lần 1:
  kỳ vọng cache miss hoặc cache chưa sẵn

GET giống hệt sau đó:
  có thể cache hit nếu entry đã được lưu và chưa hết TTL

GET /catalog?category=shoes:
  không được nhận response của books
~~~

Không khẳng định cache hit chỉ vì thời gian đáp ứng nhanh; cần đối chiếu backend request log hoặc những công cụ quan sát được cấu hình.

## 29. Azure CLI: đọc cấu hình APIM trước khi sửa

Các lệnh sau là **read-only** đối với Azure resources. Tên service và resource group là placeholder.

### Kiểm tra subscription

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --query "{id:id,name:name,tenantId:tenantId}" --output json
~~~

### Xem APIM instance

~~~bash
az apim show \
  --resource-group "rg-api-lab" \
  --name "apim-catalog-lab" \
  --query "{name:name,location:location,sku:sku.name,gatewayUrl:gatewayUrl,provisioningState:provisioningState}" \
  --output json
~~~

### Liệt kê API

~~~bash
az apim api list \
  --resource-group "rg-api-lab" \
  --service-name "apim-catalog-lab" \
  --output table
~~~

### Liệt kê products

~~~bash
az apim product list \
  --resource-group "rg-api-lab" \
  --service-name "apim-catalog-lab" \
  --output table
~~~

Để xem policy XML ở từng scope, có thể dùng Azure portal hoặc APIM REST/CLI thao tác đọc **đúng policy resource** theo phiên bản đang dùng. Không đưa lệnh show policy với tham số đoán mò rồi coi như chắc chắn sẽ hoạt động trên mọi Azure CLI.

**Lệnh chỉ đọc cấu hình không kiểm thử được 429, cache hit hay biến đổi body.** Cần gửi request thử tới gateway trong môi trường được phép và kiểm tra backend/log.

## 30. Giám sát APIM, rate limit, quota và cache

Một API gateway cần được quan sát theo cả **request** và **outcome nghiệp vụ**.

| Nhóm | Chỉ số/câu hỏi |
|---|---|
| **Requests** | Tổng lượng requests theo API, operation, client và response code |
| **Throttling** | 429 theo key/tier/operation, có burst bất thường không? |
| **Quota** | 403 do quota, kỳ quota và client bị ảnh hưởng |
| **Latency** | Tổng thời gian tại gateway, backend latency p50/p95/p99 |
| **Backend failures** | 429/503/504, timeout, circuit-breaker hoặc connection failures |
| **Cache** | Hit/miss, TTL, backend call reduction, stale responses |
| **Transform** | Số request parse body lỗi, backend nhận sai schema/route |
| **Identity** | 401/403 auth failures, subscription/tenant scope |
| **Cost** | Gateway capacity/units, external cache, logs và backend savings |
| **Security** | Token/claims validation failures, client abuse, dữ liệu bị cache nhầm |

Không phải mọi giá trị trong bảng là metric Azure Monitor tích hợp sẵn với đúng tên đó. Ví dụ cache hit rate, lỗi transformation theo từng field hoặc 403 quota cụ thể có thể cần **custom logs, diagnostics hoặc backend telemetry**. Không bật verbose logging chứa request/response body ở production nếu dữ liệu có thể nhạy cảm.

### Correlation ID

Ở mỗi request, dùng identifier đủ để liên kết:

~~~json
{
  "requestId": "example-req-42",
  "api": "catalog-lab",
  "operation": "GET /v1/catalog",
  "outcome": "200",
  "gatewayDurationMs": 28,
  "backendDurationMs": 0,
  "throttled": false
}
~~~

**backendDurationMs=0** trong log mẫu chỉ minh họa một request không gọi backend; không phải trường metric bắt buộc của APIM. Khi đo cache hit, cần đối chiếu với phương thức ghi log thực tế để tránh báo cáo sai.

### Những cảnh báo nên xem xét

- Tỷ lệ HTTP 429 tăng đột biến.
- Nhiều client đồng thời nhận 403 do quota sau thay đổi policy.
- Backend latency hoặc 5xx tăng dù APIM response time có vẻ bình thường.
- Cache hit rate giảm mạnh sau deployment.
- Cache hit xuất hiện trên endpoint chứa dữ liệu user-specific ngoài ý định.
- Lỗi parsing/transform JSON và 400/500 bất thường.
- Sự thay đổi policy global/product/API ngoài quy trình phê duyệt.
- Chi phí gateway/Redis/logs vượt ngân sách.

## 31. Rate limit không phải hàng rào chống mọi loại tấn công

Rate-limit-by-key giúp giảm một số dạng sử dụng quá mức, nhưng:

- Một đối tượng tấn công có thể dùng nhiều tài khoản/IP.
- Các request độc hại vẫn có thể nằm dưới ngưỡng.
- Backend có thể vẫn yếu trước payload rất lớn hoặc truy vấn tốn CPU.
- Bot có thể phân tán lưu lượng qua nhiều nguồn.
- Cache có thể bị lợi dụng để tạo nhiều key, gây cache pollution.

Kết hợp:

1. Microsoft Entra ID/JWT và API subscription khi phù hợp.
2. Azure Front Door/WAF hoặc lớp kiểm soát edge theo kiến trúc.
3. Validation schema, size limits, content-type và những kiểm soát request.
4. Backend authorization, idempotency và giới hạn tài nguyên.
5. Network isolation, private endpoints, TLS và secrets management.
6. Monitoring, alert và incident response.

**WAF và APIM policies hoạt động ở những lớp khác nhau**, không nên thay thế nhau bằng một quy tắc rate limit.

## 32. Vận hành đa vùng, nhiều gateway và self-hosted gateway

Khi APIM được triển khai ở nhiều region hoặc dùng self-hosted gateways, bộ đếm và cache có thể có phạm vi/khả năng đồng bộ khác với một gateway đơn.

### Rate limit và quota

Một số bộ đếm của rate-limit-by-key là **phân tán theo gateway/region hoặc cập nhật không tức thời** tùy tính năng. Không cam kết với khách hàng rằng giới hạn 100 calls sẽ được áp **đúng tuyệt đối trên toàn thế giới trong mọi microsecond** nếu chưa chứng minh tính nhất quán qua mô hình triển khai.

### Cache

Internal cache có thể không được chia sẻ như một kho dữ liệu toàn cục giữa mọi gateway. Khi thiết kế external cache, cần tính:

- Đường mạng, Private Endpoint và DNS.
- Authentication và encryption.
- Availability, region latency và cache failover.
- Chi phí external cache và dữ liệu nhạy cảm.
- Hành vi cache miss/fallback khi cache unavailable.

### Self-hosted gateway

Self-hosted gateway là mô hình triển khai riêng với tính năng/giới hạn policy có thể khác managed gateways. Hãy xác nhận **chính policy và caching mode** được hỗ trợ trước khi di chuyển từ test managed gateway sang self-hosted.

## 33. Tác động tới SLA và chi phí

### Lợi ích chi phí

- Cache hit giảm backend requests, database reads và thời gian phản hồi.
- Rate limit hạn chế client lạm dụng, có thể giảm burst pressure.
- Quota giúp áp fair-use và ngăn một khách hàng sử dụng vượt hợp đồng.
- Transformation giảm nhu cầu duy trì nhiều backend adapters đơn giản.

### Chi phí cần tính

- APIM tier/gateway capacity và instance/units theo mô hình billing.
- External cache nếu sử dụng.
- Azure Monitor, Application Insights/Log Analytics và thời gian giữ logs.
- Network egress, Private Endpoint/Firewall/NAT khi có.
- Backend compute/database, có thể giảm khi caching hiệu quả.
- Công sức vận hành policies, debugging, CI/CD và kiểm thử contract.

**Không giả định cache luôn rẻ hơn mọi trường hợp.** API response thay đổi theo hàng triệu keys có thể có tỷ lệ hit thấp; external cache và serialization có thể tốn thêm chi phí mà backend vẫn phải xử lý hầu hết requests.

### Cách tính sơ bộ tác động cache

Ví dụ giả định:

~~~text
100.000 requests/ngày tới API danh mục
Tỷ lệ cache hit đã đo = 70%

Backend requests xấp xỉ:
  100.000 x (1 - 0,70) = 30.000/ngày

Số calls tránh tới backend:
  70.000/ngày
~~~

Đây là phép tính đơn giản chưa tính retry, cache warm-up, eviction, fan-out, request không đủ điều kiện cache và biến động dữ liệu. Phải đo thực tế trước khi dùng để dự toán tiền hoặc cam kết capacity.

## 34. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Client nhận 429 dù chỉ gọi ít | Nhiều người cùng counter-key, NAT chung IP hoặc policy cha cũng giới hạn | Xem effective policy, key và request rate thực tế |
| Client vượt ngưỡng nhưng không bị chặn ngay | Bộ đếm phân tán/cập nhật trễ, sai scope hoặc policy không được thực thi | Xem effective policy, tier, logs và test có kiểm soát |
| Quota trả 403 sau thời gian dài | Chưa tới kỳ reset hoặc key dùng chung | Kiểm tra renewal-period, scope, counter-key |
| Khách hàng đổi X-Tenant-Id để né rate limit | Key lấy từ header không tin cậy | Dùng identity/tenant đã xác thực |
| Cache hit thấp | Vary key quá nhiều, TTL ngắn, cache backend không sẵn | Xem cache mode, query/header, eviction và backend calls |
| Cache trả nhầm ngôn ngữ | Thiếu lang trong key | Bổ sung vary-by-query-parameter lang |
| Cache trả dữ liệu tenant A cho B | Cache key không chứa identity hoặc endpoint không nên cache | Ngừng caching endpoint, điều tra lộ dữ liệu, sửa phạm vi |
| Giá thay đổi nhưng client vẫn thấy giá cũ | TTL chưa hết hoặc cache khác ở downstream | Xem invalidation, TTL, browser/CDN/backend |
| Rewrite khiến backend 404 | Sai backend base URL, path hoặc copy-unmatched-params | Xem request thực backend nhận |
| POST bị 500 sau set-body | Payload không phải JObject, null/body quá lớn hoặc expression lỗi | Thử JSON hợp lệ/sai định dạng, thêm validation |
| Backend không nhận correlation ID | Header bị override sau đó hoặc policy không ở đúng scope | Xem effective order và backend logs |
| Sau cache hit thiếu header cần thiết | Header được thêm ở bước bị bỏ qua do cache short-circuit | Đặt policy bắt buộc trước cache hoặc thiết kế response phù hợp |
| Production tăng 5xx sau policy | Throttling backend, retry gây khuếch đại, timeout/circuit breaker | Xem logs từ gateway và backend cùng correlation ID |
| Scope API mới không có rule global | base inheritance sai hoặc fragment không được tham chiếu | Kiểm tra effective policy |
| Internal cache bị miss ở vùng khác | Cache không chia sẻ/khác gateway | Đánh giá external cache và kiến trúc multi-region |

### Quy trình chẩn đoán sáu bước

1. **Request:** xác nhận method, URL, query, headers, subscription/identity, correlation ID.
2. **Policy:** kiểm tra effective policy, scope và thứ tự các section.
3. **Counter/cache:** xác nhận counter-key, renewal, vary-by, TTL và backend cache mode.
4. **Backend:** kiểm tra URL/path/query/body thực tế đã nhận, latency và lỗi.
5. **Infrastructure:** tier/gateway, DNS, Private Endpoint, outbound network và scale.
6. **Business outcome:** xác minh response có đúng tenant/operation và dữ liệu không bị stale sai mức cho phép.

Đừng khắc phục 429 bằng cách bỏ rate limit toàn cục khi chưa biết key/scope đang dùng; cũng đừng bỏ cache validation chỉ vì request thứ hai nhanh hơn request đầu.

## 35. Bài tập tình huống: API đối tác bán hàng

Một doanh nghiệp có API dùng cho ba nhóm client:

- **Mobile app:** yêu cầu đọc catalog công khai với traffic cao.
- **Partner Free:** không quá **30 calls/phút** và **10.000 calls/ngày**.
- **Partner Premium:** không quá **120 calls/phút** và **100.000 calls/ngày**.

Backend mới chuyển GET **/v1/catalog** thành **/internal/catalog/items** và yêu cầu **api-version**. API POST **/v1/orders** nhận trường **customer_id** nhưng backend dùng **customerId**. Catalog thay đổi trung bình 5 phút/lần; đơn hàng là dữ liệu riêng tư.

### Nhiệm vụ

1. Chọn policy nào để áp rate limit và quota theo hai nhóm partner.
2. Xác định counter-key nào đáng tin cậy và vì sao không dùng header X-Partner-Id do client tự gửi.
3. Nêu nơi áp policy: product, API hay operation; cần kiểm tra inheritance thế nào?
4. Thiết kế cache cho GET catalog, chọn TTL thử nghiệm và các query parameters phải vary.
5. Giải thích vì sao không áp cùng cache cho GET /orders/{id} hoặc POST /orders.
6. Viết ví dụ rewrite-uri và set-query-parameter cho catalog.
7. Viết ví dụ set-body đổi customer_id thành customerId cho POST, kèm validation.
8. Thiết kế xử lý 429/403 ở mobile/partner clients và chiến lược backoff.
9. Nêu cách xác minh cache hit giảm backend load mà không trả nhầm dữ liệu.
10. Thiết kế logs, alerts và metrics cho sự cố throttling/transform.
11. Dự toán tác động tới backend nếu tỷ lệ cache hit catalog là 70%.
12. Đề xuất phương án rollout canary/test và rollback nếu API contract bị hỏng.

### Gợi ý lời giải

**Rate-limit-by-key** và **quota-by-key** theo subscription/tenant đã xác thực là điểm khởi đầu. Có thể tách products Free/Premium và áp policy tương ứng, nhưng phải kiểm tra cách subscription được ánh xạ vào product và effective policy tại operation.

**GET catalog** có thể dùng cache với key phân biệt category, page, language và version nếu response phụ thuộc những trường đó. **POST orders** không cache chung, cần validation và idempotency ở backend; set-body chỉ hỗ trợ chuyển contract cũ.

Kiểm tra cả request trong hạn mức, request vượt rate limit, request hết quota, cache hit/miss, dữ liệu theo query khác và JSON sai schema. Dùng log có correlation ID để nhận biết lỗi tại gateway hay backend.

## 36. Checklist trước khi triển khai production

| Nhóm | Điều cần xác nhận |
|---|---|
| Policy scope | Global/product/API/operation đúng chủ đích |
| Inheritance | Thẻ base, fragments và effective policy được review |
| Authentication | JWT/subscription/tenant identity được validate trước các key nhạy cảm |
| Rate limit | Ngưỡng phù hợp burst/SLO, xử lý 429 rõ ràng |
| Quota | Kỳ, key, 403/remaining budget và hợp đồng sử dụng đúng |
| Counter semantics | Hiểu scope, phân tán, multi-region và giới hạn nhất quán |
| Cache scope | Chỉ endpoint/response đủ điều kiện, không có rò rỉ dữ liệu |
| Cache key | Vary-by đủ query, version, locale, tenant khi thật sự cần |
| TTL | Đáp ứng chấp nhận stale, có invalidation khi cần |
| Cache backend | Tier, internal/external support, network và failure mode |
| Transformation | Path/query/header/body đúng, không phá auth/signature |
| Validation | Kiểm thử JSON sai, body rỗng, payload lớn và schema version |
| Backend | Không thể bypass gateway policy bằng đường truy cập ngoài ý muốn |
| Security | Entra ID, RBAC, Key Vault, TLS, firewall, WAF khi phù hợp |
| Monitoring | 429/403, 5xx, cache hit, backend latency, transformation errors |
| Cost | Budget APIM/cache/log/backend và có số liệu trước/sau |
| Rollout | Test API, canary/phiên bản và phương án rollback đã chuẩn bị |

## 37. Câu hỏi tự kiểm tra

1. Rate limit và quota khác nhau ở mục tiêu và cửa sổ thời gian thế nào?
2. Vì sao một quota 10.000 calls/ngày vẫn có thể không bảo vệ backend trước burst?
3. APIM policy pipeline gồm những section nào?
4. Vị trí của base ảnh hưởng điều gì tới kế thừa policy?
5. Phân biệt rate-limit và rate-limit-by-key.
6. Vì sao counter-key không nên lấy trực tiếp từ X-Tenant-Id do client tự gửi?
7. Vì sao key theo IP có thể gây false throttling khi nhiều client chung NAT?
8. Khi bị rate limit, client thường nhận status nào và nên xử lý ra sao?
9. Khi vượt quota trong APIM, response thường khác rate limit thế nào?
10. Quota theo subscription có đồng nghĩa quota theo tenant không?
11. Vì sao rate limit không tự kiểm soát số kết nối backend đồng thời?
12. Cache-lookup và cache-store làm gì?
13. Vary-by-query-parameter có ý nghĩa gì với category và lang?
14. Vì sao response cache public không thể áp nguyên cho API /me?
15. Một cache hit có luôn chạy mọi outbound policy phía sau không?
16. Vì sao rate limit thường nên đặt trước cache-lookup?
17. TTL=60 có đảm bảo dữ liệu sẽ không stale trong 60 giây không?
18. Phân biệt response cache và value cache.
19. Khi backend thay đổi giá, có những phương án cache invalidation nào?
20. Vì sao rewrite-uri không thay thế authorization/validation?
21. set-header có thể gây rủi ro spoofing identity như thế nào?
22. set-query-parameter exists-action=override giải quyết điều gì?
23. Khi set-body parse JObject, cần kiểm tra những đầu vào nào?
24. Vì sao không nên transform JSON cho mọi file upload lớn ở gateway?
25. Những gì cần kiểm tra khi API chuyển từ customer_id sang customerId?
26. Làm sao chứng minh cache hit thực sự giảm số request tới backend?
27. Khi APIM multi-region, điều gì cần kiểm tra về counters và cache?
28. Một APIM subscription key có tự thay thế JWT của người dùng không?
29. Lỗi 429 từ gateway khác 429 từ backend thế nào trong chẩn đoán?
30. Các thành phần chi phí chính của một giải pháp APIM có external cache là gì?

## Tài liệu tham khảo

- Microsoft Learn — *Azure API Management overview*: https://learn.microsoft.com/azure/api-management/api-management-key-concepts
- Microsoft Learn — *API Management policies overview*: https://learn.microsoft.com/azure/api-management/api-management-howto-policies
- Microsoft Learn — *Policy reference*: https://learn.microsoft.com/azure/api-management/api-management-policies
- Microsoft Learn — *Policy scopes and inheritance*: https://learn.microsoft.com/azure/api-management/api-management-howto-policies#scopes
- Microsoft Learn — *Rate limit by key*: https://learn.microsoft.com/azure/api-management/rate-limit-by-key-policy
- Microsoft Learn — *Rate limit*: https://learn.microsoft.com/azure/api-management/rate-limit-policy
- Microsoft Learn — *Quota by key*: https://learn.microsoft.com/azure/api-management/quota-by-key-policy
- Microsoft Learn — *Quota*: https://learn.microsoft.com/azure/api-management/quota-policy
- Microsoft Learn — *Cache lookup*: https://learn.microsoft.com/azure/api-management/cache-lookup-policy
- Microsoft Learn — *Cache store*: https://learn.microsoft.com/azure/api-management/cache-store-policy
- Microsoft Learn — *Cache lookup value*: https://learn.microsoft.com/azure/api-management/cache-lookup-value-policy
- Microsoft Learn — *Rewrite URL*: https://learn.microsoft.com/azure/api-management/rewrite-uri-policy
- Microsoft Learn — *Set header*: https://learn.microsoft.com/azure/api-management/set-header-policy
- Microsoft Learn — *Set query parameter*: https://learn.microsoft.com/azure/api-management/set-query-parameter-policy
- Microsoft Learn — *Set body*: https://learn.microsoft.com/azure/api-management/set-body-policy
- Microsoft Learn — *API Management monitoring*: https://learn.microsoft.com/azure/api-management/api-management-howto-use-azure-monitor
- Microsoft Learn — *API Management security baseline*: https://learn.microsoft.com/security/benchmark/azure/baselines/api-management-security-baseline
