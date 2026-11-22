# Cache key, cache policy và invalidation

> **Chương:** DNS và phân phối nội dung  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hạ tầng Region/AZ, IAM, VPC, tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn cách chọn dịch vụ, triển khai ứng dụng an toàn, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Khi người dùng tại nhiều khu vực truy cập ảnh, JavaScript, video hoặc API, **Amazon CloudFront** có thể phân phối nội dung qua mạng các edge location và giảm số request gửi đến origin, chẳng hạn **Amazon S3**, **Application Load Balancer** hoặc HTTP server. Lợi ích này chỉ bền vững khi cache lưu đúng biến thể nội dung, có thời hạn hợp lý và được cập nhật an toàn sau deploy.

Ba khái niệm cốt lõi:

- **Cache key:** tập thuộc tính phân biệt các bản phản hồi trong cache; quyết định hai request có thể dùng chung một đối tượng cache hay không.
- **Cache policy:** cấu hình gắn vào cache behavior của CloudFront, xác định **TTL** và các giá trị request được đưa vào cache key.
- **Invalidation:** yêu cầu CloudFront loại bỏ bản cache cũ theo **đường dẫn** để request tiếp theo cần lấy lại nội dung; không xóa object tại origin.

Sau bài học, bạn có thể:

1. Giải thích cache hit/miss, origin, cache behavior và cache key trong CloudFront.
2. Chọn đúng query strings, HTTP headers và cookies được đưa vào cache key.
3. Phân biệt **cache policy**, **origin request policy** và **response headers policy**.
4. Dự đoán tác động của Minimum/Default/Maximum TTL, `Cache-Control`, `Expires` và error caching.
5. Thiết kế cache cho HTML, hashed static assets, hình ảnh có biến thể và API cá nhân.
6. Thực hiện và kiểm tra CloudFront invalidation bằng AWS CLI, biết khi nào nên dùng **file versioning**.
7. Quan sát cache hit ratio, lỗi, latency và chi phí; chẩn đoán nội dung cũ hoặc cache lẫn giữa người dùng.

## 1. CloudFront cache trong kiến trúc AWS

CloudFront là **content delivery network (CDN)** giúp nhận request từ người dùng tại edge location thích hợp. Khi CloudFront đã có nội dung cache còn hợp lệ, nó có thể trả về ngay tại edge; nếu chưa có hoặc cần làm mới, CloudFront phải liên hệ origin hoặc những tầng cache phù hợp khác trong kiến trúc CloudFront.

~~~mermaid
flowchart TD
    U[Người dùng / Browser] --> D[DNS: www.example.com]
    D --> C[Amazon CloudFront distribution]
    C --> B{Cache behavior theo URL path}
    B -->|/assets/*| P1[Cache policy: static assets]
    B -->|/api/*| P2[Cache policy: API]
    B -->|mặc định *| P3[Cache policy: HTML]
    P1 --> K1[Cache key + TTL]
    P2 --> K2[Cache key + TTL]
    P3 --> K3[Cache key + TTL]
    K1 --> H{Cache hit?}
    K2 --> H
    K3 --> H
    H -->|Có, hợp lệ| R[Trả nội dung từ cache]
    H -->|Không hoặc hết hạn| O[Origin: S3 / ALB / HTTP]
    O --> R
~~~

### 1.1. Thành phần cần biết

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| **Distribution** | Cấu hình CloudFront phục vụ domain, origin, behavior | `d123example.cloudfront.net` hoặc `www.example.com` |
| **Origin** | Nguồn nội dung thực tế | S3 private bucket hoặc ALB |
| **Cache behavior** | Chọn origin và các policy dựa trên path pattern | `/assets/*`, `/api/*`, default `*` |
| **Cache key** | Xác định biến thể nội dung có thể tái sử dụng | Path + query `lang=vi` + header nếu cần |
| **Cache policy** | Cách dựng cache key và giới hạn TTL | Managed policy hoặc custom policy |
| **Origin request policy** | Chuyển thêm thông tin tới origin | Một số header, cookie, query không thuộc cache key |
| **Response headers policy** | Thêm/thay đổi một số header trả về viewer | Security headers, CORS và custom headers |
| **Invalidation** | Yêu cầu làm mất hiệu lực bản cache theo path | `/index.html`, `/assets/*` |

**DNS không quyết định cache key.** Route 53 (hoặc nhà cung cấp DNS khác) có thể trỏ domain tới CloudFront, nhưng logic quyết định request nào dùng chung cache nằm ở cache behavior/policy. Khi dùng custom domain với HTTPS, cần DNS và chứng chỉ TLS tương ứng với domain theo yêu cầu CloudFront.

### 1.2. Cache hit, miss và origin load

- **Hit:** có bản nội dung phù hợp và còn có thể phục vụ từ cache.
- **Miss:** không có bản cache phù hợp hoặc cần truy xuất origin theo quy tắc.
- **Refresh/validation:** bản cache có thể cần kiểm tra lại với origin, ví dụ qua `ETag` và conditional request, tùy loại origin và header.
- **Error caching:** CloudFront có thể giữ một số phản hồi lỗi trong thời hạn riêng; phải phân tích khi origin đã được sửa nhưng client còn thấy lỗi.

Chỉ số **cache hit ratio** càng cao có thể giảm origin load và latency, nhưng **không phải mục tiêu tối cao**: trả sai bản dữ liệu hoặc cache phản hồi chứa thông tin cá nhân là lỗi nghiêm trọng hơn việc cache miss.

## 2. Cache key: cùng nội dung hay hai biến thể khác nhau?

### 2.1. Mô hình suy luận

Một cache key có thể được hiểu ở mức khái niệm là:

~~~text
Cache key ≈ URL path
          + các query parameters được chọn
          + các request headers được chọn
          + các cookies được chọn
          + các yếu tố chuẩn hóa/biến thể CloudFront quản lý
~~~

CloudFront quản lý cache theo distribution và hành vi truy cập tương ứng; công thức trên **chỉ để giải thích**, không phải định dạng key nội bộ. Không tự giả định mọi header, query hoặc cookie đều mặc nhiên có trong cache key.

Ví dụ:

~~~http
GET /catalog?page=2&sort=price HTTP/1.1
Host: shop.example.com
Accept-Language: vi-VN
Cookie: theme=dark; session_id=abc123
~~~

Giả sử HTML catalog thật sự phụ thuộc vào:

- `page` và `sort`;
- ngôn ngữ đã được hệ thống chuẩn hóa thành `vi` hoặc `en`;
- giao diện `theme` nếu HTML được render khác nhau theo theme.

**Cache key tốt** chỉ cần phản ánh các giá trị có thể làm **thay đổi response cacheable**. `session_id` chỉ dùng để theo dõi đăng nhập, không nên đưa vào cache key của trang công khai nếu nội dung không phụ thuộc session. Ngược lại, **không bao giờ bỏ qua session/user identity** nếu origin thực sự trả dữ liệu cá nhân theo session; lựa chọn an toàn hơn là **không cache các phản hồi cá nhân** ở shared CDN.

### 2.2. Thiếu thành phần: nguy cơ trả sai nội dung

Giả sử origin trả:

~~~text
GET /products/123?lang=vi -> "Giá bán"
GET /products/123?lang=en -> "Price"
~~~

Nếu cache key chỉ có `/products/123` mà **không bao gồm `lang`**, CloudFront có thể lưu bản tiếng Việt rồi phục vụ cùng bản đó cho request tiếng Anh. Đây là **cache collision giữa các biến thể**.

Với dữ liệu cá nhân, hậu quả nặng hơn: cache key chỉ có URL trong khi origin tạo response khác nhau theo cookie/Authorization có thể khiến người dùng nhận nội dung không thuộc quyền mình. Do đó, **chỉ cache phản hồi công khai hoặc phản hồi có cơ chế cô lập biến thể đã được thiết kế, kiểm thử kỹ**.

### 2.3. Thừa thành phần: giảm cache hit ratio

Giả sử một nội dung công khai chỉ có hai biến thể ngôn ngữ nhưng cache key chứa:

- Header `User-Agent` có vô số giá trị;
- Cookie `session_id` riêng cho từng người;
- Các query quảng cáo như `utm_source`, `utm_campaign`;
- Header `Accept-Language` thô có nhiều tổ hợp phức tạp.

Mỗi request có thể tạo một key khác, làm tăng số bản cache, giảm hit ratio và tăng request đến origin.

Một phép tính trực giác:

~~~text
4 trang × 3 ngôn ngữ × 2 kích thước ảnh × 2 themes
= 48 biến thể trước khi tính cookie hoặc các header khác
~~~

Nếu cộng một cookie có hàng nghìn giá trị ngẫu nhiên, số biến thể tăng rất mạnh trong khi nội dung không đổi. **Nguyên tắc:** chỉ đưa vào key những thuộc tính làm thay đổi bản response được phép cache.

### 2.4. Query string trong cache key

CloudFront cache policy có thể chọn query string theo các chế độ như:

| Cách cấu hình | Ý nghĩa | Khi phù hợp |
|---|---|---|
| **None** | Không đưa query string vào key | Static assets không biến thể theo query |
| **All** | Đưa toàn bộ query string vào key | Chỉ phù hợp khi mọi tham số đều có ý nghĩa với response |
| **Include specified** | Chỉ đưa những tên tham số được chọn | Ví dụ `lang`, `page`, `size` |
| **All except specified** | Đưa các tham số trừ danh sách loại bỏ | Khi hầu hết tham số có nghĩa, trừ tracking parameters |

Ví dụ có thể chỉ giữ `lang`, `page` và loại các tham số `utm_*` không ảnh hưởng nội dung. Các chế độ **whitelist** theo *tên tham số*, không tự chuẩn hóa mọi giá trị thành tập an toàn.

Một số điểm cần lưu ý:

1. CloudFront có thể xem **thứ tự tham số query** là khác nhau trong cách tạo cache entry. Ví dụ `?a=1&b=2` và `?b=2&a=1` có thể làm giảm hit ratio dù origin coi tương đương; hãy chuẩn hóa URL ở tầng ứng dụng/edge nếu thực sự cần.
2. Tên và giá trị query có thể phân biệt chữ hoa/thường; `lang=vi` và `Lang=vi` không mặc nhiên giống nhau.
3. Query string **không thuộc path pattern** dùng chọn behavior; routing theo `/api/*` và cache-key query là hai bước khác nhau.
4. Không đưa access token, mật khẩu hoặc dữ liệu nhạy cảm vào URL để giải quyết caching; URL có thể xuất hiện trong logs và hệ thống giám sát.

### 2.5. HTTP headers trong cache key

Có thể cấu hình những header nhất định góp phần tạo key, ví dụ nội dung phụ thuộc `Accept-Language` hoặc một header phân loại định dạng. Tuy nhiên:

- Giá trị header có độ đa dạng cao làm cache phân mảnh.
- Header do client tự gửi có thể bị giả mạo; **không dùng giá trị cache-key header làm cơ chế authorization**.
- Một số header được CloudFront xử lý đặc biệt, đặc biệt `Accept-Encoding` khi bật caching theo hỗ trợ nén gzip/Brotli.
- Chỉ sử dụng header mà cache policy/API hỗ trợ và đã có kế hoạch xác minh.

**Ví dụ đáng cân nhắc:** thay vì đưa nguyên header `Accept-Language` chứa chuỗi dài và khác nhau, ứng dụng có thể tạo đường dẫn `/vi/...`, `/en/...` hoặc một giá trị ngôn ngữ đã chuẩn hóa. Cách đó thường làm cache dễ dự đoán hơn.

Header `Vary` của origin **không khiến CloudFront tự động phân biệt theo mọi header mà Vary liệt kê**. Để CloudFront cache đúng biến thể, cần đưa header phù hợp vào cache key theo khả năng dịch vụ, hoặc thiết kế URL khác.

### 2.6. Cookies trong cache key

Cookie thường dùng để giữ trạng thái, phân nhóm thử nghiệm, giao diện hoặc đăng nhập. Cache policy có các cách chọn tương tự query:

- Không gồm cookie nào;
- Tất cả cookies;
- Một danh sách cookie;
- Tất cả trừ danh sách.

**Nên đưa cookie vào cache key** khi một response cacheable thật sự khác nhau theo cookie đó (ví dụ một biến thể công khai được kiểm soát). **Không nên cache response cá nhân theo cookie mà chưa có thiết kế tách biệt quyền truy cập**. Với endpoint trả dữ liệu riêng của người dùng, áp **CachingDisabled** hoặc một cấu hình tương đương đã được kiểm thử, kể cả khi origin trả header điều khiển cache phù hợp.

## 3. Cache policy: cấu hình TTL và cache key

### 3.1. Policy được gắn vào cache behavior

Một CloudFront distribution có **default cache behavior** và có thể có nhiều ordered cache behaviors. Mỗi behavior chọn origin, phương thức truy cập và policy tương ứng.

~~~text
Distribution: www.example.com
├── /assets/*  -> S3 origin -> Cache policy: static-long
├── /images/*  -> S3 origin -> Cache policy: image-variants
├── /api/*     -> ALB origin -> Cache policy: caching-disabled
└── default *  -> S3 origin -> Cache policy: html-short
~~~

CloudFront xét path pattern của các **ordered cache behaviors** theo thứ tự cấu hình; behavior khớp đầu tiên được dùng, nếu không khớp thì dùng default. Vì vậy, path pattern cụ thể và thứ tự quan trọng khi ứng dụng có nhiều tuyến.

**Ví dụ:** nếu `/api/*` có caching disabled, còn default behavior cache HTML, cần kiểm tra `/api/user` thực sự khớp đúng behavior; nếu không, API riêng tư có thể đi qua chính sách cache không phù hợp.

### 3.2. Minimum TTL, Default TTL và Maximum TTL

| Thuộc tính | Ý nghĩa | Cách sử dụng |
|---|---|---|
| **Minimum TTL** | Ngưỡng tối thiểu CloudFront có thể giữ object trong cache | Đặt **0** nếu phải tôn trọng `no-cache`/`no-store`/`private` từ origin |
| **Default TTL** | TTL dùng khi origin không cung cấp chỉ dẫn cache thích hợp | Giá trị dự phòng cho nội dung thiếu header |
| **Maximum TTL** | Ngưỡng tối đa khi origin yêu cầu thời gian cache dài | Giới hạn mức stale có thể chấp nhận |

CloudFront dùng cache policy và các cache headers từ origin để quyết định thời hạn hợp lệ. Một mô hình tư duy thông thường:

~~~text
TTL CloudFront ≈
  Nếu origin có Cache-Control / Expires phù hợp:
      thời hạn origin yêu cầu, chịu giới hạn Min TTL và Max TTL
  Nếu origin không có cache directives:
      Default TTL của cache policy (trong giới hạn policy)
~~~

**Quy tắc an toàn rất quan trọng:** nếu **Minimum TTL > 0**, CloudFront có thể cache response trong tối thiểu khoảng đó **ngay cả khi origin trả `Cache-Control: no-cache`, `no-store` hoặc `private`**. Vì vậy, đừng gắn policy có Min TTL dương lên endpoint trả dữ liệu cá nhân chỉ vì origin đã gửi `no-store`.

### 3.3. Ví dụ thời hạn cache

Giả sử policy có:

~~~text
Minimum TTL = 0 giây
Default TTL = 300 giây
Maximum TTL = 3600 giây
~~~

| Header ở origin | TTL CloudFront thông thường | Giải thích |
|---|---:|---|
| Không có chỉ dẫn cache | 300 giây | Dùng Default TTL |
| `Cache-Control: max-age=120` | 120 giây | Origin đặt thời hạn |
| `Cache-Control: s-maxage=600` | 600 giây | Chỉ dẫn cho shared cache |
| `Cache-Control: max-age=86400` | Tối đa 3600 giây | Maximum TTL giới hạn |
| `Cache-Control: no-store` | Không nên cache theo chỉ dẫn đó với Min TTL = 0 | Đúng khi cấu hình/cache path không có cơ chế khác làm thay đổi |

Đây là ví dụ theo quy tắc phổ biến; các tổ hợp directives như `s-maxage`, `Expires`, `no-cache` và chính sách error caching cần được đối chiếu với hướng dẫn CloudFront.

### 3.4. Cache-Control của browser khác TTL tại CloudFront

CloudFront là một **shared cache** nằm giữa browser và origin. Browser còn có cache riêng. Cần phân biệt:

- `max-age`: ảnh hưởng tới cache được phép sử dụng theo semantics HTTP, gồm browser cache trong bối cảnh phù hợp.
- `s-maxage`: thời hạn dành cho shared cache như CDN; có thể ưu tiên so với `max-age` khi áp dụng.
- `no-store`: yêu cầu không lưu bản response ở các cache liên quan, cần bảo đảm CloudFront Min TTL = 0.
- `no-cache`: có thể lưu nhưng phải revalidate trước khi sử dụng lại theo quy tắc HTTP, không có nghĩa “xóa mọi bản sao”.
- `private`: response dành cho một người dùng, không nên cache ở shared cache khi có chỉ dẫn này và cấu hình phù hợp.
- `immutable`: gợi ý cho client tránh revalidation khi tài nguyên không đổi tại cùng URL; phù hợp hashed assets.

**CloudFront invalidation không tự xóa browser cache.** Nếu browser còn giữ file với `max-age` dài, người dùng có thể tiếp tục thấy bản cũ dù invalidation của CDN đã hoàn tất. Đó là lý do dùng **hashed filenames** cho asset ít đổi và giữ TTL HTML ngắn.

### 3.5. Managed cache policy và custom cache policy

AWS cung cấp managed cache policies như những lựa chọn phục vụ trường hợp phổ biến, trong đó có **CachingOptimized** và **CachingDisabled**. Chúng là cấu hình ban đầu tiện lợi nhưng **không tự hiểu semantics của ứng dụng**.

Khi tạo custom policy, quyết định:

1. Có được cache nội dung này ở shared CDN không?
2. Min/Default/Max TTL là bao nhiêu?
3. Query, cookie và header nào ảnh hưởng bản response?
4. Có cần nén gzip/Brotli theo khả năng hỗ trợ không?
5. Có những biến thể ngôn ngữ/thiết bị cần chuẩn hóa không?
6. Cần phản hồi lỗi và invalidation theo quy trình nào?

Đặt tên policy rõ mục đích, ví dụ `aws-lab-static-v1`, `aws-lab-html-short` hoặc `aws-lab-api-no-cache`. Quản trị policy qua IaC giúp dễ đánh giá khác biệt trước khi thay production.

## 4. Cache policy, origin request policy và response headers policy

### 4.1. Vì sao tách thành ba loại?

Một request có thể mang nhiều thông tin cần gửi tới origin để xác thực, ghi log hoặc điều khiển xử lý. Tuy nhiên, **không phải mọi thông tin gửi tới origin đều nên trở thành cache key**.

| Policy | Mục đích | Có làm thay đổi cache key không? |
|---|---|---|
| **Cache policy** | TTL, các query/header/cookie được đưa vào cache key | **Có** |
| **Origin request policy** | Chuyển thêm query/header/cookie đến origin | **Không trực tiếp** |
| **Response headers policy** | Điều khiển những header CloudFront gửi về viewer | **Không trực tiếp** |

CloudFront tự gửi tới origin các giá trị được cache policy đưa vào cache key. Origin request policy dùng để **bổ sung** những giá trị cần cho origin nhưng không phải thành phần key.

~~~mermaid
flowchart LR
    V[Viewer request] --> C[Cache policy]
    C --> K[Cache key + TTL]
    K --> H{Hit?}
    H -->|Yes| R[Cached response]
    H -->|Miss| O[Origin request policy: chuyển thêm giá trị]
    O --> B[Origin: S3 / ALB / API]
    B --> R
    R --> RH[Response headers policy]
    RH --> V2[Viewer nhận response]
~~~

Sơ đồ chỉ mô tả vai trò logic của các policy; request thực tế còn chịu ảnh hưởng của CloudFront Functions, Lambda@Edge, origin custom headers, Origin Shield và các thiết lập khác.

### 4.2. Rủi ro khi origin nhận thông tin không nằm trong key

Giả sử origin nhận header `X-Account-Tier` do proxy chuyển tới và trả khác nội dung theo giá trị `free`/`premium`. Nếu header được chuyển bằng **origin request policy** nhưng **không nằm trong cache key**, CloudFront có thể cache một response và dùng chung cho các request khác có cùng key.

Đây là lỗi nghiêm trọng nếu hai biến thể có quyền truy cập khác nhau. Cách xử lý:

- Với dữ liệu công khai có biến thể hợp lệ, đưa **tín hiệu đã chuẩn hóa** vào cache key theo khả năng dịch vụ.
- Với thông tin cá nhân hoặc dữ liệu đòi hỏi authorization, **tắt shared caching** ở behavior tương ứng và xác minh headers từ origin.
- Không dùng header client tự khai báo để quyết định quyền riêng tư.
- Kiểm thử trường hợp hai principal có cùng URL nhưng quyền/nội dung khác nhau trước khi deploy.

### 4.3. Response headers policy có thay được TTL ở origin không?

Response headers policy có thể thêm/sửa những header trên response tới viewer, bao gồm các header phục vụ CORS/security hoặc custom headers theo tính năng CloudFront. Tuy nhiên, **TTL của bản cache CloudFront được điều khiển bởi cache policy và chỉ dẫn cache từ origin trong quá trình caching**; thay header gửi tới viewer không đồng nghĩa đã thay TTL nội bộ của object được cache.

Ví dụ, muốn file JavaScript được cache dài tại edge cần cấu hình cache policy và origin `Cache-Control` phù hợp; chỉ chèn một header ở response gửi tới browser không phải cách đảm bảo CloudFront cache 1 năm.

### 4.4. Authorization, CORS và cache key

- **Authorization:** cần xem kỹ cách CloudFront forward header và cách cache policy xử lý cho origin cụ thể. Không bật cache cho private API chỉ bằng suy đoán rằng Authorization header luôn được đưa vào key.
- **CORS:** nếu origin tạo `Access-Control-Allow-Origin` khác nhau theo request `Origin`, việc không phân biệt biến thể có thể trả sai CORS header; cân nhắc policy/response headers policy hoặc cách thiết kế CORS chuẩn.
- **Session cookies:** thường có cardinality cao, và nội dung cá nhân không phù hợp với shared cache mặc định.
- **Cookies tracking:** không làm thay đổi nội dung thì nên tránh đưa vào key.
- **Host header:** CloudFront có xử lý đặc biệt tùy origin/policy; không giả định hành vi giống reverse proxy tự quản lý.

## 5. Thiết kế cache cho các loại nội dung

### 5.1. Ma trận khởi đầu

| Nội dung | Cách cache đề xuất | Cache key | Cập nhật |
|---|---|---|---|
| `/assets/app.a1b2c3.js`, CSS/ảnh có hash | TTL dài; file bất biến | Thường chỉ cần URL/path và biến thể thực sự có nghĩa | Upload file hash mới, HTML tham chiếu tên mới |
| `/index.html` hoặc HTML entry | TTL ngắn, có thể revalidate | Thường URL/path | Invalidation hoặc TTL ngắn sau deploy |
| Ảnh động theo `width`/`format` | Cache các biến thể đã chuẩn hóa | URL/path + query width/format có kiểm soát | Versioning hoặc invalidation theo path |
| Public API catalog | Cache ngắn nếu dữ liệu không cá nhân | Path + query chọn lọc; có thể ngôn ngữ | TTL ngắn hoặc invalidation |
| `/api/me`, giỏ hàng, hồ sơ | **CachingDisabled** hoặc bảo vệ tương đương | Không sử dụng shared CDN cache cho dữ liệu riêng tư | Origin cung cấp dữ liệu mới, `no-store` |
| Trang được render theo session | Tùy thiết kế, thường không cache shared response | Tránh dùng key thiếu danh tính | Thiết kế authorization và kiểm thử |
| File tải xuống có quyền riêng | Cân nhắc CloudFront signed URL/cookie hoặc origin authorization phù hợp | Không chia sẻ dữ liệu không được phép | Chính sách quyền và phiên bản file |

Các giá trị TTL cần chọn theo yêu cầu sản phẩm. Không tồn tại một bộ TTL đúng cho mọi dịch vụ.

### 5.2. Static assets có tên theo nội dung (content hash)

Ví dụ build tạo:

~~~text
/app.js                 (tên cố định, dễ bị stale)
/assets/app.4e9c12.js   (tên có hash nội dung)
/assets/app.8af2d1.js   (bản phát hành mới)
~~~

Với file hash, có thể dùng:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

Đây là mẫu thường dùng cho asset **thực sự bất biến** trong vòng đời tên file. Không gắn `immutable` cho `/index.html` hoặc `/app.js` nếu nội dung của URL đó có thể bị ghi đè.

Deploy mẫu:

1. Build và upload tài nguyên với tên hash **mới**.
2. Kiểm tra S3 origin và đường CloudFront tới asset mới.
3. Upload HTML entry mới tham chiếu hash mới.
4. Dùng TTL HTML ngắn hoặc invalidate `/index.html` và đường dẫn người dùng thực sự gọi (nếu cần).
5. Giữ asset cũ trong một khoảng phù hợp để tránh phá phiên web đã mở trước deploy; sau đó lifecycle/dọn theo quy trình.

Ưu điểm: URL mới sinh cache key mới, không phụ thuộc việc xóa mọi bản asset cũ tại edge. Invalidation vẫn hữu ích với HTML hoặc một số file không thể version bằng tên.

### 5.3. Ảnh có biến thể

Một URL:

~~~text
/images/course-cover.jpg?width=400&format=webp
/images/course-cover.jpg?width=800&format=webp
/images/course-cover.jpg?width=400&format=jpeg
~~~

Nếu origin/edge thực sự tạo ba nội dung khác nhau, cache key phải phân biệt `width` và `format` hoặc đưa biến thể vào path. Nếu tham số `utm_campaign` chỉ dùng đo lường, bỏ khỏi cache key.

**Chặn sự bùng nổ biến thể:** chỉ hỗ trợ các giá trị đã chuẩn hóa, chẳng hạn width ∈ {320, 640, 960} và format ∈ {webp, jpeg}. Không cho request arbitrary width từ 1 đến hàng nghìn tạo quá nhiều object mà không kiểm soát.

### 5.4. API và dữ liệu người dùng

Một endpoint:

~~~http
GET /api/me HTTP/1.1
Authorization: Bearer <token>
~~~

trả hồ sơ người dùng, tuyệt đối cần kiểm tra quyền tại origin/edge theo thiết kế được duyệt. Đối với các API riêng tư thông thường:

- Cache behavior `/api/*` dùng managed **CachingDisabled** hoặc chính sách với caching vô hiệu phù hợp.
- Origin trả `Cache-Control: private, no-store` hoặc quy định được hệ thống chấp thuận.
- Forward những header/cookie cần thiết qua cấu hình CloudFront tương thích, kiểm thử thực tế.
- Không cho một response người dùng A được phục vụ cho người dùng B; dùng test hai session độc lập.
- Kiểm tra các route đặc biệt như `/api/public/catalog` nếu muốn có behavior cache riêng và path match ưu tiên đúng.

**CloudFront signed URL/cookie** bảo vệ quyền truy cập vào một tài nguyên theo cơ chế xác thực tại edge, và cache có thể hữu ích cho tài nguyên giống nhau được cấp cho nhiều người. Điều này khác với việc tùy tiện cache nội dung **cá nhân hóa bởi origin** theo session. Thiết kế authorization là ràng buộc bắt buộc trước khi chia sẻ cache.

## 6. Invalidation: xóa hiệu lực bản cache theo path

### 6.1. Khi nào cần invalidation?

Khi origin đã có phiên bản mới của một URL không đổi, CloudFront vẫn có thể có bản cache cũ cho đến khi TTL hoặc bước revalidation thích hợp xảy ra. **Invalidation** là cách yêu cầu CloudFront loại bỏ bản cũ theo path trong distribution.

~~~mermaid
sequenceDiagram
    participant Dev as Pipeline triển khai
    participant S3 as Origin S3
    participant CF as CloudFront
    participant V as Viewer
    Dev->>S3: Upload index.html mới
    Dev->>CF: CreateInvalidation /index.html
    CF-->>Dev: Invalidation ID - InProgress
    Dev->>CF: GetInvalidation / kiểm tra Completed
    CF-->>Dev: Completed
    V->>CF: GET /index.html
    CF->>S3: Lấy bản mới khi cache cần nạp
    S3-->>CF: index.html mới
    CF-->>V: Phục vụ nội dung mới
~~~

**Invalidation không:**

- Xóa hoặc sửa object tại S3/ALB origin;
- Xóa browser cache, proxy cache bên ngoài CloudFront hay service worker cache của ứng dụng;
- Tự thay đổi `Cache-Control` hoặc TTL cho các request về sau;
- Thay thế quy trình triển khai, sao lưu hay rollback ứng dụng.

Nếu origin vẫn trả dữ liệu cũ (ví dụ deployment chưa xong, nhiều origin không đồng bộ), CloudFront có thể cache lại **chính bản cũ** sau invalidation.

### 6.2. Cú pháp invalidation path

CloudFront invalidation path bắt đầu bằng dấu `/`, ví dụ:

~~~text
/index.html
/
/assets/app.js
/images/*
/*
~~~

Dấu `*` có thể dùng làm wildcard khi xuất hiện **ở cuối invalidation path**. `/*` thường invalidates phạm vi rất rộng, không nên là lựa chọn mặc định cho mỗi lần deploy. Các đường dẫn **phân biệt chữ hoa/thường**, và cấu hình URL rewrite, default root object hoặc cache query strings có thể đòi hỏi invalidate nhiều cách truy cập tương ứng.

Ví dụ một SPA:

~~~text
GET /       -> CloudFront default root object index.html
GET /index.html
GET /courses/123 -> có thể được rewrite về /index.html (tùy cấu hình)
~~~

Tùy cơ chế default root object/URL rewrite, cần xem path nào thực sự có cache entry, rồi invalidate `/index.html`, `/` và/hoặc pattern thích hợp. **Không mặc định invalidate mỗi `/index.html` là đã làm mới mọi đường dẫn SPA**.

### 6.3. Invalidation khi có query string

Nếu CloudFront lưu **các biến thể khác nhau theo query string**, cùng một path có thể ứng với nhiều cache entries:

~~~text
/catalog?lang=vi
/catalog?lang=en
/catalog?page=2
~~~

Cần xác định invalidation path có query phù hợp hoặc dùng pattern wildcard phù hợp, ví dụ `/catalog*` khi muốn bao phủ các biến thể. Dấu `*` phải là ký tự cuối trong path. Đừng dùng `/catalog*` trên distribution có nhiều route gần tên nếu không muốn chúng bị làm mới.

**Chiến lược tốt hơn:** thiết kế key có ít biến thể và versioning cho dữ liệu/tài nguyên thay đổi thường xuyên, nhằm giảm số invalidations phải gửi.

### 6.4. Trạng thái và tính phí

CloudFront trả một **invalidation ID** và trạng thái như `InProgress` hoặc `Completed`. Chỉ khi trạng thái hoàn tất theo AWS, yêu cầu đã được xử lý qua hệ thống phân phối. Việc kiểm thử từ một điểm mạng duy nhất khi vẫn `InProgress` chưa phản ánh toàn bộ quá trình.

Invalidation có **hạn mức yêu cầu đồng thời, số path và chính sách tính phí/miễn phí theo tài khoản**; không nên giả định mọi `/*` đều miễn phí hoặc không ảnh hưởng hiệu năng origin. Kiểm tra AWS pricing và quotas hiện hành.

## 7. Invalidation hay đặt tên file theo phiên bản?

| Tiêu chí | Invalidation | Versioned filenames / content hash |
|---|---|---|
| Cơ chế | Làm mất hiệu lực URL cache hiện có | Tạo **URL mới** với cache key mới |
| Có cần đổi URL tham chiếu? | Không | Có, ứng dụng/HTML phải tham chiếu tên mới |
| Phù hợp | HTML entry, metadata, URL cố định, sửa lỗi khẩn cấp | JS, CSS, ảnh và asset bất biến |
| Độ trễ cập nhật | Phụ thuộc thời gian xử lý invalidation và origin | Client dùng URL mới sau khi bản tham chiếu cập nhật |
| Browser cache | Không xóa browser cache cũ | URL mới tránh va chạm cache cũ |
| Chi phí vận hành | Có thể tính phí invalidation | Phát sinh thêm storage/requests cho phiên bản |
| Rollback | Có thể cần invalidate lại sau khi origin quay về bản cũ | HTML quay về tham chiếu tên asset cũ nếu file còn |
| Rủi ro | Invalidate quá rộng tạo origin spike | Dọn asset cũ quá sớm làm trang phiên cũ bị lỗi |

**Khuyến nghị kiến trúc phổ biến:** versioning + TTL dài cho static assets, TTL ngắn hoặc invalidation có chọn lọc cho HTML/manifest. Không áp dụng mô hình dài hạn cho nội dung cá nhân hoặc tài nguyên có yêu cầu tuân thủ đặc biệt mà chưa thiết kế quyền truy cập.

### 7.1. Deploy an toàn theo thứ tự

Một quy trình điển hình cho website S3 + CloudFront:

~~~text
1. Build -> tạo asset filenames có hash nội dung
2. Upload assets mới với Cache-Control dài
3. Kiểm tra assets mới khả dụng từ CloudFront/origin
4. Upload HTML/manifest tham chiếu assets mới
5. Tạo invalidation chỉ cho HTML/manifest (nếu cần)
6. Theo dõi error rate, cache hit ratio, latency, origin traffic
7. Rollback HTML/manifest nếu có vấn đề và invalidate phần liên quan
8. Dọn asset rất cũ theo quy tắc retention, không xóa ngay
~~~

Khi có **service worker**, cache tại client còn có vòng đời và logic cập nhật riêng, phải kiểm thử độc lập; CloudFront invalidation không buộc service worker cache được xóa.

## 8. Cache behavior selection và giới hạn đường dẫn

### 8.1. Thứ tự behavior ảnh hưởng cả bảo mật

Giả sử distribution có:

~~~text
Ordered behaviors:
  /api/private/* -> CachingDisabled + origin API
  /api/*         -> Cache short + origin API

Default behavior:
  *              -> Cache HTML + S3
~~~

Đường dẫn `/api/private/profile` cần đi vào behavior thứ nhất. Nếu `/api/*` được đặt trước, rule tổng quát có thể bắt request trước. **Cache policy phù hợp nhưng gắn sai behavior không giúp bảo vệ endpoint**.

Cũng cần kiểm tra các biến thể path có dấu gạch chéo cuối, URL encoding, case và rewrite từ CloudFront Function/Lambda@Edge. Không chỉ thử một URL đẹp trong tài liệu.

### 8.2. Cache key và nén nội dung

CloudFront có khả năng nén phản hồi hỗ trợ gzip/Brotli. Khi bật tùy chọn tương ứng trên cache policy, CloudFront có thể **chuẩn hóa `Accept-Encoding` và phân biệt những biến thể cần thiết** trong cache key theo tính năng của dịch vụ.

Không nên thêm thủ công mọi biến thể `Accept-Encoding` hoặc toàn bộ user agent vào key khi CloudFront đã có cơ chế nén phù hợp. Cần kiểm tra:

- Origin trả đúng `Content-Type`/`Content-Encoding`.
- Không nén hai lần.
- Response có thể phục vụ đúng viewer hỗ trợ gzip/Brotli.
- Cache hit ratio trước/sau thay đổi.

### 8.3. Caching HTTP errors

CloudFront có thể cache phản hồi lỗi như 404/5xx theo **Error Caching Minimum TTL** và những quy tắc liên quan. Vì vậy:

~~~text
t0: /assets/new.js chưa tồn tại -> origin trả 404
t1: Upload /assets/new.js lên S3
t2: CloudFront vẫn có thể trả 404 cache trong khoảng còn hiệu lực
~~~

Khi một asset vừa được deploy mà vẫn 404:

1. Kiểm tra object tại origin đã tồn tại, đúng key/Region và quyền.
2. Xem HTTP status/`X-Cache` từ CloudFront.
3. Kiểm tra error caching TTL/config.
4. Cân nhắc invalidation path tương ứng, tránh `/*` khi không cần.

Đừng tăng error caching TTL cho đường API nhạy thời gian nếu không chấp nhận kéo dài lỗi sau khi origin đã hồi phục.

## 9. Thực hành 1 — Xem cache policy trên distribution bằng AWS CLI

> Phần này chỉ đọc cấu hình, không tạo tài nguyên. Bạn cần AWS CLI v2 và IAM role/user được cấp quyền như `cloudfront:ListDistributions`, `cloudfront:GetDistribution` và `cloudfront:GetCachePolicy`. AWS CloudFront là dịch vụ toàn cầu; xác định đúng **account và distribution ID** trước khi xem hoặc sửa.

### 9.1. Xác minh danh tính AWS

Ví dụ trong Bash hoặc CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

Nếu đang dùng CloudShell với danh tính đăng nhập sẵn và không có profile này, bỏ dòng `export AWS_PROFILE=...` cùng tham số `--profile`. Kết quả `Account` và `Arn` phải thuộc sandbox được cấp.

### 9.2. Liệt kê các distribution

~~~bash
aws cloudfront list-distributions \
  --query 'DistributionList.Items[].{Id:Id,Domain:DomainName,Status:Status,Enabled:Enabled}' \
  --output table
~~~

Nếu account chưa có distribution, kết quả có thể rỗng. Không tự tạo distribution production chỉ để hoàn thành bài đọc cấu hình; bạn vẫn có thể phân tích JSON/policy ví dụ bên dưới.

### 9.3. Xem behavior và policy IDs

~~~bash
DIST_ID=E123EXAMPLEABC

aws cloudfront get-distribution \
  --id "$DIST_ID" \
  --query 'Distribution.DistributionConfig.{Origins:Origins,Default:DefaultCacheBehavior,Ordered:CacheBehaviors.Items}' \
  --output json
~~~

Thay `E123EXAMPLEABC` bằng ID **được cấp quyền đọc**. Tìm các trường:

- `PathPattern` ở ordered cache behaviors và default behavior mặc định.
- `TargetOriginId` để xác định nguồn S3/ALB/HTTP.
- `CachePolicyId`, `OriginRequestPolicyId` và `ResponseHeadersPolicyId` (nếu có).
- Các tùy chọn như `ViewerProtocolPolicy`, `Compress` và allowed/cached HTTP methods.

Nếu behavior vẫn dùng cấu hình legacy `ForwardedValues`, đừng tự diễn giải như một cache policy mới đã tồn tại; cần xem quy tắc legacy và lập kế hoạch di chuyển có kiểm thử.

### 9.4. Đọc cache policy cụ thể

~~~bash
CACHE_POLICY_ID=11111111-2222-3333-4444-555555555555

aws cloudfront get-cache-policy \
  --id "$CACHE_POLICY_ID" \
  --query 'CachePolicy.CachePolicyConfig' \
  --output json
~~~

ID là placeholder. Quan sát:

~~~text
MinTTL / DefaultTTL / MaxTTL
ParametersInCacheKeyAndForwardedToOrigin:
  EnableAcceptEncodingGzip
  EnableAcceptEncodingBrotli
  HeadersConfig
  CookiesConfig
  QueryStringsConfig
~~~

**Câu hỏi phân tích:** nếu cache key đưa vào toàn bộ cookies trong khi ứng dụng không thay đổi nội dung theo cookies, hậu quả với cache hit ratio thế nào? Nếu `MinTTL=60` nhưng API origin trả `no-store`, nguy cơ là gì?

### 9.5. Xem origin request policy nếu có

~~~bash
ORIGIN_REQUEST_POLICY_ID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee

aws cloudfront get-origin-request-policy \
  --id "$ORIGIN_REQUEST_POLICY_ID" \
  --query 'OriginRequestPolicy.OriginRequestPolicyConfig' \
  --output json
~~~

Phân biệt những giá trị **được chuyển tới origin** với những giá trị **được đưa vào cache key**. Có thể kiểm tra danh sách policy bằng `list-cache-policies` và `list-origin-request-policies` theo quyền được cấp để biết những policy có sẵn.

### 9.6. Quan sát HTTP cache behavior bằng curl

Nếu bạn có CloudFront domain dành cho sandbox:

~~~bash
CF_URL=https://d123example.cloudfront.net

curl -sSI "$CF_URL/assets/app.js"
curl -sSI "$CF_URL/assets/app.js"
~~~

Xem những header có thể xuất hiện:

~~~text
HTTP/2 200
cache-control: public, max-age=...
age: ...
x-cache: Hit from cloudfront
x-amz-cf-pop: ...
x-amz-cf-id: ...
~~~

Các giá trị trên chỉ là **minh họa**, không phải output luôn giống nhau. `X-Cache` có thể là `Miss from cloudfront`, `Hit from cloudfront`, `RefreshHit` hoặc trạng thái khác; `Age` có thể vắng trong một số response. Với cache phân tán, hai request từ nơi/edge khác nhau không bảo đảm dùng chung bản tại cùng một thời điểm.

**Không dùng `X-Cache: Hit` làm bằng chứng về bảo mật.** Nó chỉ hỗ trợ quan sát caching, không xác định request đã được kiểm tra quyền đúng hay chưa.

## 10. Thực hành 2 — Invalidation có chọn lọc trên sandbox

> Phần này **làm thay đổi CloudFront distribution** và có thể tính phí invalidation. Chỉ thực hiện trên distribution sandbox mà bạn được phép cập nhật, với đường dẫn được sở hữu. Không invalidate toàn bộ distribution production để học thử.

### 10.1. Kiểm tra phiên bản ở origin trước

Giả sử origin S3 có file `index.html` và asset `assets/app.a1b2c3.js`. Nếu bạn có quyền đọc bucket:

~~~bash
BUCKET=aws-lab-cloudfront-demo

aws s3api head-object \
  --bucket "$BUCKET" \
  --key index.html \
  --query '{ETag:ETag,LastModified:LastModified,CacheControl:CacheControl,ContentType:ContentType}' \
  --output json
~~~

Kiểm tra origin thực sự đã được cập nhật và header `Cache-Control` phù hợp. Với S3 dùng versioning, xem đúng version nếu việc rollback phụ thuộc một bản cụ thể. **Một invalidation khi origin vẫn cũ sẽ nạp lại dữ liệu cũ**.

### 10.2. Tạo invalidation cho entry HTML

~~~bash
DIST_ID=E123EXAMPLEABC

aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths "/index.html" "/"
~~~

Lệnh trả về `Invalidation.Id`, `Status`, các path và metadata liên quan. Với application có URL rewrite hoặc query variants, chọn các path thực tế cần làm mới dựa trên cấu hình phân phối.

### 10.3. Kiểm tra trạng thái invalidation

~~~bash
aws cloudfront list-invalidations \
  --distribution-id "$DIST_ID" \
  --query 'InvalidationList.Items[].{Id:Id,Status:Status,Created:CreateTime}' \
  --output table
~~~

Đọc thông tin một invalidation:

~~~bash
INVALIDATION_ID=I123EXAMPLEABC

aws cloudfront get-invalidation \
  --distribution-id "$DIST_ID" \
  --id "$INVALIDATION_ID" \
  --query 'Invalidation.{Id:Id,Status:Status,Paths:InvalidationBatch.Paths.Items}' \
  --output json
~~~

Thay ID bằng giá trị từ kết quả `create-invalidation`. Khi cần chờ completion trong pipeline đã được duyệt, AWS CLI cung cấp waiter:

~~~bash
aws cloudfront wait invalidation-completed \
  --distribution-id "$DIST_ID" \
  --id "$INVALIDATION_ID"
~~~

**Không suy đoán trạng thái từ việc CLI vừa tạo thành công**; theo dõi đến `Completed` khi rollout phụ thuộc invalidation. Thời gian có thể thay đổi và pipeline cần timeout/retry phù hợp.

### 10.4. Kiểm thử sau invalidation

~~~bash
CF_URL=https://d123example.cloudfront.net

curl -sSI "$CF_URL/"
curl -sSI "$CF_URL/index.html"
~~~

Đọc `Date`, `Last-Modified`, `ETag`, `Cache-Control`, `Age` và `X-Cache` khi có; so nội dung thực tế và đối chiếu version build. Hai URL có thể không đồng nhất vì behavior/default root/rewrite/caching khác nhau; phải kiểm tra **từng đường truy cập mà người dùng thật sử dụng**.

### 10.5. Wildcard invalidation khi cần

Để làm mới một nhánh cụ thể:

~~~bash
aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths '/images/*'
~~~

Dấu nháy đơn giúp shell không mở rộng `*` thành tên file cục bộ. Kiểm tra phạm vi trước khi gửi, vì có thể làm tăng origin traffic. Tránh dùng `'/*'` làm bước mặc định sau mọi deploy.

**Dọn bài lab:** Invalidation là yêu cầu quản lý cache; không có thao tác “xóa invalidation” để hoàn nguyên. Bản cache sẽ được nạp lại khi có request. Nếu bài thực hành đã tạo object S3, chỉ xóa object riêng của lab theo quy trình; không xóa bucket/distribution dùng chung. Xem lại phí S3 request, CloudFront transfer, invalidation và logs theo dashboard chi phí khi dữ liệu cập nhật.

## 11. Thực hành tư duy: thiết kế cache key và TTL

### 11.1. Bài toán

Một nền tảng học trực tuyến dùng:

- `learn.example.com/index.html`: trang SPA được triển khai thường xuyên.
- `learn.example.com/assets/app.<hash>.js`: JavaScript và CSS build theo content hash.
- `learn.example.com/images/course.jpg?size=small|large`: ảnh có hai kích thước.
- `learn.example.com/catalog?lang=vi|en&page=N`: catalog công khai.
- `learn.example.com/api/me`: hồ sơ riêng từng học viên, có Authorization/cookie.
- `learn.example.com/api/progress`: tiến độ học tập riêng.

Yêu cầu giảm độ trễ cho người dùng toàn quốc, tránh nhầm dữ liệu, phục hồi nhanh sau deploy sai và kiểm soát chi phí CloudFront/S3/ALB.

### 11.2. Thiết kế tham khảo

| Behavior | Origin | Cache key gợi ý | TTL định hướng | Cập nhật |
|---|---|---|---|---|
| `/assets/*` | S3 private + OAC | URL/path, không đưa session cookie | Dài với hashed immutable assets | Upload hash mới; HTML tham chiếu tên mới |
| `/images/*` | S3/image service | URL/path + `size` đã chuẩn hóa | Trung bình/dài tùy thay đổi | Versioning hoặc invalidate path |
| `/catalog` | Public API | Path + `lang` + `page` | Ngắn, theo mức cập nhật dữ liệu | TTL hoặc invalidation |
| `/api/me` | ALB/API | **Không cache response cá nhân** | Disabled / Min TTL 0 | Lấy dữ liệu từ backend |
| `/api/progress` | ALB/API | **Không cache response cá nhân** | Disabled / Min TTL 0 | Backend kiểm soát quyền theo user |
| Default/HTML | S3 private + OAC | Path và biến thể thật sự cần | Ngắn, có revalidation | Invalid `/index.html` hoặc root nếu cần |

**S3 origin nên được bảo vệ bằng Origin Access Control (OAC)** để CloudFront là đường phân phối đã được duyệt; không cần bật public ACL cho bucket chỉ để phục vụ website. Đối với API, ALB và application authorization vẫn kiểm soát người dùng.

### 11.3. Tự tính số biến thể

Catalog có 2 ngôn ngữ, 10 trang, 3 kiểu sắp xếp:

~~~text
2 languages × 10 pages × 3 sorts = 60 cache variants
~~~

Nếu cache key còn thêm `session_id` riêng cho 10.000 người dùng, số biến thể lý thuyết có thể tăng lên hàng trăm nghìn mà chưa chắc phục vụ thêm nội dung khác. Câu hỏi đặt ra: thuộc tính nào thật sự thay đổi response? Nếu `sort` cũng thay đổi thứ tự item, nó phải nằm trong key hoặc path. Nếu session không làm khác catalog công khai, không đưa session vào cache key.

### 11.4. Kịch bản rollback

Phiên bản HTML vừa deploy tham chiếu `app.bad123.js` gây lỗi frontend. Cách khắc phục:

1. Build/HTML phiên bản cũ đã kiểm thử vẫn trỏ đến `app.good456.js` còn tồn tại.
2. Đưa HTML cũ về origin theo quy trình rollback có kiểm soát.
3. Invalidate HTML/root hoặc đợi TTL rất ngắn theo SLO.
4. Theo dõi CloudFront error rate, 404 assets, frontend error tracking và lượng request tới origin.
5. Không xóa những hash assets vẫn đang được phiên browser cũ sử dụng.
6. Kiểm tra browser/service worker cache nếu người dùng vẫn gặp phiên sai dù invalidation đã hoàn tất.

## 12. Giám sát cache, origin và chi phí

### 12.1. Các tín hiệu quan trọng

| Tín hiệu | Nguồn tham khảo | Câu hỏi trả lời |
|---|---|---|
| **CacheHitRate** | CloudFront monitoring / CloudWatch metrics phù hợp | Bao nhiêu request được phục vụ từ cache? |
| **Requests** | CloudFront monitoring/logs | Lưu lượng từng giai đoạn có tăng không? |
| **4xxErrorRate / 5xxErrorRate** | CloudFront metrics | Có lỗi viewer/origin đáng chú ý? |
| **OriginLatency** | CloudFront metrics khi được hỗ trợ/cấu hình | Origin có đang phản hồi chậm? |
| **X-Cache, Age** | HTTP response headers | Request mẫu vừa hit/miss/revalidate như thế nào? |
| **S3 request metrics / ALB metrics** | Origin metrics | Cache miss có làm tăng tải origin không? |
| **CloudFront access logs / real-time logs** | Logging nếu bật | Phân tích đường truy cập, hit/miss và xu hướng lỗi |
| **Cost Explorer / Budgets** | Billing | Chi phí dữ liệu truyền, request, invalidation và logs thế nào? |

Metric availability, dimensions, sampling và phí có thể thay đổi theo tính năng CloudFront. **Real-time logs** và các metric chi tiết có thể có chi phí riêng; bật theo yêu cầu quan sát cụ thể.

### 12.2. Cách đọc cache hit ratio

~~~text
Cache hit ratio ≈ số request được phục vụ từ cache
                  / tổng request thuộc phạm vi đo
~~~

Đây là cách giải thích, còn metric của CloudFront có định nghĩa và exclusions riêng. Không dùng con số tổng hợp cho một distribution để kết luận behavior `/api/*` đang đúng, vì static assets có thể chiếm phần lớn traffic và che vấn đề API.

Nếu cache hit ratio giảm:

- Kiểm tra deployment có thay URL/hash quá thường xuyên không.
- Có vô tình đưa toàn bộ cookie/headers/query vào key không?
- TTL có quá ngắn so với nhịp truy cập không?
- Có nhiều response lỗi hoặc chính sách không cache không?
- Có nhiều edge location hoặc lượng truy cập phân tán dẫn đến ít request lặp trên cùng key không?
- Origin có trả Cache-Control hoặc cookie khó cache không?

### 12.3. Chi phí và đánh đổi

Chi phí CloudFront có thể gồm data transfer ra viewer, HTTP/HTTPS requests, invalidation vượt mức được áp dụng, logging, các tính năng bảo mật/cạnh biên, và chi phí origin S3/ALB tùy kiến trúc.

**Trường hợp tối ưu đúng:** giảm request đến origin và giảm tải backend nhờ cache nội dung công khai. **Trường hợp tối ưu sai:** thêm mọi header vào cache key khiến cache miss cao, tạo nhiều request tới origin và tăng chi phí.

**Không tối ưu hit ratio bằng cách cache dữ liệu riêng tư.** Chọn mức TTL theo rủi ro dữ liệu, SLA và trải nghiệm người dùng trước, rồi mới so chi phí.

## 13. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Deploy mới nhưng người dùng còn thấy HTML cũ | HTML TTL dài, invalidation chưa xong, browser/service worker cache | Xem `Cache-Control`, invalidation status, `Age`, browser |
| Một người dùng nhận nội dung người khác | Shared cache của personalized response, thiếu biến thể key/không tắt caching | Dừng caching đường nhạy cảm, audit logs/quyền, kiểm thử hai tài khoản |
| Catalog tiếng Anh hiện nội dung tiếng Việt | `lang` không nằm trong cache key hoặc normalization sai | Xem cache policy query strings và response origin |
| Cache hit ratio rất thấp | Session cookie, User-Agent hoặc tracking query tạo quá nhiều key | Xem HeadersConfig/CookiesConfig/QueryStringsConfig |
| CloudFront hit nhưng origin đã thay file | TTL chưa hết hoặc invalidation chưa áp đúng path | Xem `Age`, `ETag`, origin version, invalidation |
| Invalidate `/index.html` xong nhưng `/` vẫn cũ | Default root object/rewrite tạo đường cache khác | Kiểm tra các URL và invalidation paths |
| Origin trả `no-store` nhưng CloudFront vẫn cache | Cache policy có Minimum TTL > 0 | Đặt Min TTL 0 hoặc CachingDisabled cho đường riêng tư |
| 404 vẫn xuất hiện sau khi upload object | Error caching, wrong object key, S3 origin permission | Kiểm tra origin, error caching TTL và invalidate đúng path |
| URL query đảo thứ tự gây miss | Cache key phân biệt thứ tự query | Chuẩn hóa query/path trước caching nếu phù hợp |
| CORS sai với một số website | Origin response khác theo Origin header nhưng cache key thiếu biến thể | Xem Origin và CORS policy, thiết kế cache hợp lệ |
| Request qua `/api/*` bị cache như HTML | Ordered behavior/path match sai | Xem thứ tự cache behaviors và test đủ path |
| `create-invalidation` báo lỗi quyền | IAM thiếu `cloudfront:CreateInvalidation` hoặc distribution sai account | Xác minh STS identity, distribution ARN và IAM policy |
| Invalidation đã Completed nhưng asset cũ vẫn hiện | Browser/proxy/service-worker cache độc lập | Kiểm tra client cache, versioned URL và response headers |
| Sau invalidation, origin tăng tải mạnh | Invalidated quá rộng hoặc lưu lượng truy cập lớn | Chọn phạm vi nhỏ hơn, versioning, origin capacity |
| TTL dài nhưng cache miss liên tục ở API | API trả private/no-store hoặc key cardinality cao | Xác định API có nên được cache hay không trước khi tối ưu |

### 13.1. Quy trình xác minh có thứ tự

~~~text
1. Kiểm tra account, distribution ID, domain và DNS.
2. Xác định URL/path và cache behavior thật sự được chọn.
3. Xem CachePolicyId, Min/Default/Max TTL, query/header/cookie key.
4. Xem OriginRequestPolicyId và thông tin origin nhận.
5. Xem Cache-Control/Expires/ETag từ origin.
6. Gọi request qua CloudFront, đọc X-Cache/Age/response body.
7. Kiểm tra invalidation path và trạng thái Completed nếu đã gửi.
8. Nếu vẫn cũ, kiểm tra browser, service worker, proxy và origin version.
9. Với nội dung nhạy cảm, ưu tiên xác nhận quyền/tránh cache lẫn.
10. Đo cache ratio, error rate, latency, origin load và chi phí.
~~~

## 14. Những hiểu lầm cần tránh

**“CloudFront cache theo mọi header, cookie và query mặc định.”** Sai. Cache key chịu cấu hình cache policy, các lựa chọn forwarding/normalization và đặc tính của CloudFront.

**“Đưa tất cả cookies vào cache key là an toàn nhất.”** Sai. Điều này thường làm giảm hit ratio; với dữ liệu cá nhân còn cần phân tích authorization và rủi ro chia sẻ dữ liệu ở CDN.

**“Origin request policy chuyển header tới origin thì header đó tự động thành cache key.”** Sai. Giá trị được chuyển qua origin request policy **không tự động** tham gia cache key.

**“Cache-Control: no-store đủ để vô hiệu hóa cache mọi lúc.”** Chưa chắc. Cache policy có **Minimum TTL > 0** có thể khiến CloudFront cache ít nhất một khoảng thời gian dù origin gửi `no-store` hoặc `private`.

**“Invalidation cập nhật cả browser cache.”** Sai. Invalidation xử lý CloudFront cache; browser, service worker và proxy khác có vòng đời cache riêng.

**“Đổi file JavaScript nhưng giữ tên cũ và TTL một năm vẫn an toàn.”** Không phù hợp. File có thể bị giữ cũ; nên dùng hashed filenames hoặc kế hoạch cập nhật rõ.

**“Invalidate /* sau mọi deploy là cách tốt nhất.”** Không cần thiết trong phần lớn trường hợp. Nó có thể tăng origin load và phí; nên invalidate theo đúng tập URL cần làm mới.

**“CacheHitRate càng cao càng chứng minh kiến trúc an toàn.”** Sai. Cache hit ratio là tín hiệu hiệu năng; an toàn dữ liệu phải xác minh riêng bằng quyền, cache key và thử nghiệm nhiều principal.

## 15. Tự kiểm tra và bài tập

1. Cache key có những thành phần logic nào? Khi nào query `lang` cần được đưa vào cache key?
2. Hai URL `/catalog?a=1&b=2` và `/catalog?b=2&a=1` có thể tạo các cache entries khác nhau không? Bạn sẽ xử lý ra sao?
3. Vì sao thêm `User-Agent` hoặc session cookie vào key có thể làm tăng origin traffic?
4. Origin request policy khác cache policy ở tác động tới cache key như thế nào?
5. Nếu `Minimum TTL = 60` nhưng origin trả `Cache-Control: no-store`, rủi ro gì với endpoint hồ sơ cá nhân?
6. Vì sao `/api/me` nên dùng `CachingDisabled` mặc dù ứng dụng có thể truyền Authorization?
7. Khi nào CloudFront dùng Default TTL?
8. `max-age` và `s-maxage` khác nhau ra sao đối với browser và shared cache?
9. Một invalidation `/index.html` có xóa mọi browser cache và service worker cache không?
10. Khi nào nên dùng `/assets/app.<hash>.js` và TTL dài thay vì ghi đè `/assets/app.js`?
11. Vì sao nên upload assets mới trước khi cập nhật HTML?
12. Invalidation `/images/*` có ảnh hưởng gì đến origin load và phí?
13. Đâu là bằng chứng để xác định response 404 còn bị error-cached tại CloudFront?
14. Nếu HTML mới đã có ở S3 nhưng CloudFront vẫn trả HTML cũ, bạn kiểm tra theo thứ tự nào?
15. Làm sao bảo đảm một request tới `/api/private/profile` không bị xử lý bởi behavior cache công khai `/api/*`?
16. Hai ứng dụng có cùng URL nhưng dữ liệu khác theo header do client gửi có nên dùng chung cache không?
17. Hãy đề xuất cache key cho catalog công khai có `lang`, `page`, `sort` và `utm_source`.
18. Với một SPA dùng service worker, vì sao invalidation của CDN chưa đủ đảm bảo mọi người thấy bản mới?
19. Ngoài cache hit ratio, cần theo dõi những chỉ số nào để đánh giá tác động của cache policy?
20. Bảo vệ S3 origin với CloudFront OAC có tác dụng gì đối với phân phối static assets?

### 15.1. Bài tập quyết định

Cho hệ thống có bốn loại response:

| URL | Response | Đề xuất cache |
|---|---|---|
| `/assets/app.f84a2.js` | JS không đổi theo user | TTL dài, URL theo hash |
| `/index.html` | HTML thay mỗi lần deploy | TTL ngắn + invalidation chọn lọc khi cần |
| `/api/products?lang=vi` | Danh mục công khai theo ngôn ngữ | Cache ngắn, key gồm `lang` |
| `/api/me` | Thông tin cá nhân theo Authorization | Không cache ở shared CDN |

**Hãy giải thích** lựa chọn, hành vi origin và bước triển khai/rollback cho từng URL. Khi trả lời, xét cả browser cache, chi phí và độ trễ chấp nhận được sau deploy.

## 16. Checklist trước khi đưa CloudFront cache vào production

- [ ] Đã liệt kê các origin, domain, TLS certificate và route DNS.
- [ ] Đã xác định behavior nào phục vụ HTML, asset, API public và API private.
- [ ] Path patterns được sắp xếp đúng thứ tự và có bộ request kiểm chứng.
- [ ] Cache key chứa đúng query/header/cookie làm thay đổi response cacheable.
- [ ] Không cache lẫn dữ liệu cá nhân, tenant hoặc nội dung đòi hỏi authorization.
- [ ] Hiểu cách dùng cache policy và origin request policy; không để origin phụ thuộc giá trị bị bỏ qua trong key.
- [ ] Minimum TTL = 0 hoặc policy tương đương cho endpoint phải tôn trọng `no-store`.
- [ ] TTL của HTML/manifest và hashed assets phù hợp nhịp deploy.
- [ ] Đã thiết kế invalidation paths và phương án versioning có giới hạn phạm vi.
- [ ] Có kiểm thử rollback, client/browser cache và service worker cache nếu sử dụng.
- [ ] S3 origin được bảo vệ bằng OAC và bucket policy phù hợp nếu đó là loại origin được dùng.
- [ ] Có CloudFront/ALB/S3 metrics, logs, cảnh báo lỗi, latency và origin load phù hợp.
- [ ] Đã kiểm tra chi phí request, data transfer, invalidation, logging và các tính năng bổ sung.
- [ ] Có runbook xử lý stale content, 404 error caching, phân mảnh cache key và sai behavior.
- [ ] Thông số TTL, policies và rollout được quản lý bằng IaC/review khi có thể.

**Kết quả mong đợi:** Bạn có thể giải thích **request nào dùng chung cache**, CloudFront giữ bản cache trong bao lâu, khi nào cần invalidation và cách phối hợp file versioning để triển khai hiệu quả. Bạn cũng có thể xác định rủi ro về quyền truy cập, đo hiệu năng và xây dựng quy trình cập nhật nội dung không làm phát sinh chi phí hoặc lỗi không kiểm soát.

## Tài liệu AWS chính thức

- [Understand cache keys](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/understanding-the-cache-key.html)
- [Control the cache key with a policy](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/controlling-the-cache-key.html)
- [Use managed cache policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html)
- [Control origin requests with a policy](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/controlling-origin-requests.html)
- [Response headers policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/modifying-response-headers.html)
- [Manage how long content stays in the cache](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Expiration.html)
- [Cache content based on query string parameters](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/QueryStringParameters.html)
- [Cache content based on cookies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Cookies.html)
- [Invalidate files to remove content](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Invalidation.html)
- [Specify invalidation files](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-specifying-objects.html)
- [Choose between invalidating files and using versioned file names](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Invalidation.html#invalidation-choosing-between)
- [CloudFront cached HTTP error responses](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/HTTPStatusCodes.html)
- [CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/)
- [Protect S3 origins with Origin Access Control](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)

> **Lưu ý áp dụng:** Tên miền, distribution ID, policy ID, bucket và output trong bài là ví dụ đào tạo. Tính năng CloudFront, giá, quota và hành vi caching có thể thay đổi theo dịch vụ và thời điểm. Trước khi đưa cache policy hoặc invalidation vào production, hãy kiểm tra tài liệu AWS hiện hành, kiểm thử bằng các request đại diện và phê duyệt thay đổi theo quy trình của tổ chức.
