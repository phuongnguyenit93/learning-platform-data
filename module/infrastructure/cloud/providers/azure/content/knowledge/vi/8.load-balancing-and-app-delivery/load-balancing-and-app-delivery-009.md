# Tối ưu cache, nội dung tĩnh và độ trễ tại biên

Khi người dùng ở nhiều khu vực cùng truy cập một ứng dụng Azure, việc đặt toàn bộ nội dung trên một máy chủ gốc (origin) có thể làm thời gian tải trang tăng lên. Một trang web thường cần tải HTML, JavaScript, CSS, phông chữ, hình ảnh và gọi API; không phải yêu cầu nào cũng cần đi qua toàn bộ quãng đường từ trình duyệt tới origin.

**Edge caching** là kỹ thuật đưa bản sao của những nội dung được phép lưu vào bộ nhớ đệm tại các điểm hiện diện mạng (edge points of presence) gần người dùng hơn. Khi nội dung có sẵn và còn hợp lệ, hệ thống biên có thể trả kết quả trực tiếp mà không cần gọi origin. Cùng với tối ưu kích thước asset, nén, giao thức truyền tải và quy tắc cache đúng, kỹ thuật này có thể giảm độ trễ cảm nhận, giảm tải origin và cải thiện khả năng đáp ứng khi lưu lượng tăng.

Trong mô-đun CLOUD_PROVIDERS_AZURE, chủ đề này gắn với Azure Front Door, Azure CDN, Azure Storage, Azure Static Web Apps, App Service, DNS, bảo mật Web Application Firewall (WAF), giám sát Azure Monitor và kiểm soát chi phí. Mục tiêu không phải “cache càng nhiều càng tốt”, mà là **phân phối nhanh những dữ liệu an toàn để lưu đệm, đồng thời giữ tính đúng đắn và riêng tư của dữ liệu động**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích browser cache, edge cache, origin và cache hit/miss.
2. Lựa chọn kiến trúc phân phối nội dung tĩnh bằng Azure Front Door và nguồn lưu trữ hoặc dịch vụ web phù hợp.
3. Thiết kế chính sách Cache-Control, TTL, cache key, query string, versioning và purge.
4. Tách nội dung công khai khỏi nội dung cá nhân hóa để tránh rò rỉ dữ liệu qua shared cache.
5. Tối ưu hình ảnh, JavaScript, CSS, HTTP/TLS và đo độ trễ thực tế theo khu vực.
6. Cấu hình theo một quy trình an toàn, xử lý cache stale và quan sát tỷ lệ cache hit, error rate, latency, chi phí.

Kiến thức nền cần có: HTTP request/response, DNS, HTTPS, Azure resource group, Azure Storage, App Service và các khái niệm origin, endpoint, route.

## 2. Độ trễ tại biên phát sinh từ đâu?

Thời gian tải một trang không chỉ là thời gian thực thi code ứng dụng. Có thể tách các yếu tố chính:

- **DNS resolution:** trình duyệt tra địa chỉ của domain.
- **Thiết lập kết nối:** TCP/TLS hoặc QUIC/HTTP/3 tùy giao thức và khả năng hỗ trợ.
- **Round-trip time (RTT):** thời gian dữ liệu đi-về qua mạng giữa client, edge và origin.
- **Thời gian origin xử lý:** truy vấn database, xác thực, render HTML, gọi dịch vụ phụ thuộc.
- **Thời gian truyền tải:** kích thước tài nguyên, băng thông, mất gói và nén.
- **Thời gian render trên client:** parse JavaScript, dựng giao diện, tải font, xử lý ảnh.

Ví dụ: người dùng ở châu Âu truy cập website có origin tại Đông Nam Á. Nếu mọi ảnh và file JS đều được lấy từ origin, mỗi tài nguyên có thể chịu ảnh hưởng bởi RTT liên lục địa. Đưa những asset có thể cache tới edge gần người dùng giúp loại bỏ nhiều lần truy vấn origin. Nhưng một API cá nhân hóa vẫn có thể cần tới backend, nên **CDN không bảo đảm loại bỏ tất cả độ trễ**.

Có thể mô hình hóa thời gian phản hồi ở mức khái niệm:

~~~text
Cache hit:
  Client → Edge → Client

Cache miss:
  Client → Edge → Origin → Edge → Client
~~~

Với nội dung cache hit, edge vẫn cần xử lý request và chuyển dữ liệu qua mạng tới người dùng; edge không có nghĩa là độ trễ bằng 0. Hơn nữa, một hệ thống có edge gần người dùng nhưng origin chậm vẫn có thể cho trải nghiệm kém khi có nhiều cache miss.

## 3. Cache nhiều tầng trong một ứng dụng Azure

### 3.1. Browser, edge và origin

~~~mermaid
flowchart LR
    U["Trình duyệt người dùng"] --> B{"Browser cache<br/>còn hợp lệ?"}
    B -->|Hit| R["Dùng bản sao tại client"]
    B -->|Miss hoặc cần revalidate| F["Azure Front Door / CDN Edge"]
    F --> E{"Edge cache<br/>có bản hợp lệ?"}
    E -->|Hit| C["Trả dữ liệu từ edge"]
    E -->|Miss| O["Origin: Storage / App Service / API"]
    O -->|Response + headers| F
    C --> U
    F --> U
~~~

* Browser cache: bản sao tại thiết bị người dùng. Có thể tiết kiệm cả request đến edge.
* Edge cache: shared cache của dịch vụ phân phối, phục vụ nhiều người dùng khi nội dung được phép chia sẻ.
* Origin: nơi giữ bản gốc hoặc tự tạo nội dung, chẳng hạn Azure Storage, App Service hay một backend API.
* Application/data cache: ví dụ Redis hoặc cache của database, tối ưu xử lý phía backend. Đây là lớp khác với CDN edge cache.

Một request đến edge có thể trả nội dung cache hit, cache miss hoặc cần revalidate/refresh tùy thời hạn và quy tắc. Các thuật ngữ và header báo trạng thái cache cụ thể phụ thuộc dịch vụ Azure đang dùng.

### 3.2. Các chỉ số cốt lõi

| Chỉ số | Ý nghĩa | Lưu ý |
|---|---|---|
| Cache hit ratio | Tỷ lệ request được phục vụ từ cache trong tập request có thể cache | Cần phân biệt request hit với byte hit |
| Byte hit ratio | Tỷ lệ byte được phục vụ từ cache thay vì tải từ origin | Hữu ích khi file có kích thước khác nhau |
| Origin fetches | Số lần edge cần gọi origin | Một số response được revalidate vẫn có thể tạo request về origin |
| Time to first byte (TTFB) | Thời gian tới byte đầu tiên từ góc nhìn client hoặc một điểm đo cụ thể | Không tương đương thời gian tải cả trang |
| p50/p95/p99 latency | Phân vị thời gian phản hồi | p95 giúp thấy trải nghiệm nhóm người dùng chậm |
| Origin egress | Lưu lượng chuyển từ origin ra dịch vụ phân phối | Có thể ảnh hưởng chi phí |
| Error rate | Tỷ lệ 4xx/5xx theo loại và nguồn lỗi | Cần phân biệt lỗi edge, WAF và origin |
| Core Web Vitals | Các chỉ số trải nghiệm người dùng như LCP, INP, CLS | Cần đo bằng dữ liệu thực hoặc công cụ phù hợp |

**Cache hit ratio cao không tự chứng minh website nhanh.** Chẳng hạn 99% hit với nhiều ảnh quá lớn vẫn khiến tốc độ tải trên mạng di động kém. Phải tối ưu cả kích thước asset, render phía client và đường tải dữ liệu quan trọng.

## 4. Chọn dịch vụ phân phối phù hợp trong Azure

### 4.1. Các lựa chọn phổ biến

| Dịch vụ | Vai trò chính | Dùng khi |
|---|---|---|
| Azure Front Door Standard/Premium | Entry point HTTP(S) toàn cầu, edge delivery, routing, caching cho nội dung phù hợp và tích hợp WAF theo tính năng/gói | Website hoặc API phục vụ người dùng nhiều vùng; cần TLS, định tuyến toàn cầu, cache và bảo vệ ở edge |
| Azure CDN | Phân phối nội dung từ edge theo sản phẩm và cấu hình được cung cấp | Chủ yếu cần tăng tốc nội dung tĩnh và đã có dịch vụ CDN phù hợp |
| Azure Storage static website | Origin đơn giản cho file HTML/CSS/JS/ảnh tĩnh trong Storage Account | Website tĩnh không yêu cầu backend server để tạo trang |
| Azure Static Web Apps | Hosting ứng dụng web tĩnh, tích hợp build/deployment, routing và khả năng tích hợp API tùy cấu hình | SPA hoặc website tĩnh muốn dùng workflow triển khai thuận tiện |
| Azure App Service / API backend | Phục vụ trang động, xử lý nghiệp vụ và API | Nội dung phụ thuộc request, người dùng, quyền hoặc database |
| Azure Application Gateway | Load balancer HTTP(S) khu vực, có thể dùng WAF tùy SKU | Cần phân phối lớp ứng dụng bên trong một khu vực; không thay thế mạng edge toàn cầu |
| Azure Load Balancer | Cân bằng tải Layer 4 | Kết nối TCP/UDP; không phải CDN hay HTTP object cache |

Các dịch vụ không hoàn toàn loại trừ nhau. Ví dụ Azure Front Door có thể dùng Storage làm origin cho nội dung tĩnh và App Service làm origin cho API. Cũng có hệ thống mà Azure Static Web Apps tự đáp ứng yêu cầu phân phối, không cần thêm Front Door nếu không có nhu cầu đặc biệt.

Tên sản phẩm, tier và tính năng có thể thay đổi; không mặc định mọi SKU đều có WAF, Private Link, caching rule hoặc cấu hình origin giống nhau. Kiểm tra khả năng hỗ trợ và giá hiện hành của loại profile được chọn.

### 4.2. Kiến trúc mẫu: một domain, nhiều loại nội dung

Giả sử ứng dụng cửa hàng trực tuyến có domain www.example.com, các tài nguyên tĩnh nằm ở Storage và API đặt trên App Service.

~~~mermaid
flowchart TD
    U["Người dùng tại các khu vực"] --> D["DNS: www.example.com"]
    D --> F["Azure Front Door Standard/Premium<br/>TLS + routes + edge cache"]
    F -->|"/assets/*: cache public"| S["Azure Storage<br/>JS/CSS/ảnh có hash"]
    F -->|"/index.html: TTL ngắn hoặc revalidate"| H["Origin hosting HTML"]
    F -->|"/api/*: bypass cache"| A["Azure App Service API"]
    A --> DB["Azure SQL / dịch vụ dữ liệu"]
    F --- W["WAF policy và giám sát"]
~~~

**Điểm thiết kế:** cùng một domain có thể áp dụng chính sách khác nhau theo đường dẫn. Asset bất biến được cache dài; HTML entrypoint cần kiểm tra phiên bản mới nhanh; API đăng nhập và đơn hàng phải bỏ qua shared cache. Các tính năng routing và cache được gán vào route/rule set thích hợp theo sản phẩm Azure Front Door đang sử dụng.

Khi origin là Azure Storage static website endpoint, lưu ý điểm cuối website dùng để phục vụ tài nguyên công khai theo cơ chế của dịch vụ. Không đặt dữ liệu cần xác thực chỉ bằng việc hy vọng CDN sẽ che origin. Nếu cần nguồn riêng tư sau Front Door, phải xác minh **cơ chế kết nối riêng được hỗ trợ cho đúng loại origin và SKU**, không suy ra mọi static website endpoint đều hỗ trợ Private Link như nhau.

## 5. Thiết kế chính sách cache HTTP

### 5.1. Đọc Cache-Control chính xác

HTTP Cache-Control là nơi quan trọng để origin hướng dẫn browser và shared cache. Những directive thường gặp:

| Directive | Ý nghĩa khái quát | Cách sử dụng |
|---|---|---|
| public | Cho phép shared cache lưu response nếu các điều kiện khác phù hợp | File tĩnh công khai |
| private | Response dành cho cache riêng của người dùng, không dành cho shared cache | Dữ liệu thuộc về một user, khi vẫn muốn browser caching phù hợp |
| no-store | Cache tuân thủ chuẩn không được lưu response | Token, thông tin nhạy cảm hoặc dữ liệu không nên lưu |
| no-cache | Có thể lưu nhưng phải xác thực lại với origin trước khi tái sử dụng | HTML thường xuyên cập nhật |
| max-age=N | Thời gian nội dung được coi là fresh trong một số ngữ cảnh cache | Chọn theo loại tài nguyên |
| s-maxage=N | Điều khiển thời gian fresh của shared cache theo semantics HTTP | Chỉ dùng khi rõ kỳ vọng và sản phẩm edge hỗ trợ hành vi tương ứng |
| must-revalidate | Không dùng bản stale không được xác thực sau khi hết hạn theo điều kiện chuẩn | HTML cần kiểm tra bản mới |
| immutable | Thông báo nội dung không đổi trong thời hạn fresh | Asset có tên chứa hash nội dung |

**Phân biệt no-cache và no-store:** no-cache không có nghĩa tuyệt đối là “không lưu”. Nó yêu cầu revalidate trước khi sử dụng lại. Đối với dữ liệu cá nhân nhạy cảm, thường nên dùng no-store và **tắt caching tại route edge tương ứng**, thay vì chỉ dựa vào một header.

Một số cấu hình Front Door cho phép override cache behavior/TTL. Khi quy tắc edge ghi đè chỉ dẫn origin, kết quả có thể khác semantics mong đợi từ Cache-Control. Luôn xem cả header của origin, cấu hình route/rule set và header thực sự được phân phối tới client.

### 5.2. Phân loại nội dung và TTL

Không có một TTL tối ưu chung. Có thể bắt đầu với bảng định hướng sau rồi hiệu chỉnh từ dữ liệu đo:

| Nhóm nội dung | Ví dụ | Chiến lược tham khảo |
|---|---|---|
| Asset tĩnh có content hash | app.a13f9c.js, style.9ab21.css | Cache dài, ví dụ 1 năm, vì URL đổi khi nội dung đổi |
| Ảnh tĩnh có URL phiên bản | banner.v5.webp, icon.ab42.svg | Cache dài nếu tên thay đổi cùng nội dung |
| HTML entrypoint | /, /index.html | TTL rất ngắn, revalidate hoặc không cache tại edge tùy yêu cầu phát hành |
| JSON danh mục công khai | /api/public/catalog | Có thể cache ngắn nếu dữ liệu không riêng tư và được định nghĩa cache key đúng |
| API trạng thái hoặc số liệu gần thời gian thực | /api/public/stock | TTL rất ngắn hoặc bypass; cân nhắc mức sai lệch chấp nhận được |
| Trang cá nhân hóa | /account, /orders | Không dùng shared cache; thường no-store |
| Đăng nhập, token và thanh toán | /auth/*, /checkout/* | Bypass edge cache, no-store, kiểm soát bảo mật riêng |
| Bản xem trước chưa xuất bản | /preview/* | Không cache công khai nếu có giới hạn quyền hoặc nội dung mật |

Các thời hạn trong bảng là hướng dẫn thiết kế, không phải mặc định của Azure Front Door. Tài nguyên có URL không chứa phiên bản không nên nhận TTL quá dài nếu cần cập nhật khẩn cấp mà không chắc chắn khả năng invalidation của browser.

### 5.3. Ví dụ header cho file bất biến

Giả sử pipeline build tạo file app.a13f9c.js. Response phù hợp có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=utf-8
Cache-Control: public, max-age=31536000, immutable
ETag: "build-a13f9c"
~~~

Khi thay đổi JavaScript, pipeline phát hành app.b41d8e.js thay vì ghi đè nội dung dưới tên app.a13f9c.js. Với URL mới, browser và edge tải bản mới mà không cần xóa toàn bộ cache cũ.

Mục đích của content hash là **đặt phiên bản trong URL**. Nếu sử dụng cùng một URL nhưng vẫn ghi đè nội dung phía origin, header immutable dài hạn trở thành nguồn gây lỗi cập nhật.

### 5.4. Ví dụ header cho HTML và dữ liệu riêng tư

HTML entrypoint cần dễ phát hiện bản deploy mới:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Cache-Control: no-cache, max-age=0, must-revalidate
ETag: "index-build-205"
~~~

Nếu route edge có khả năng cache HTML, phải cấu hình để tôn trọng yêu cầu revalidate hoặc bypass theo chính sách triển khai. Purge ở edge không xóa được bản browser cache đang còn fresh nếu browser đã được cấp TTL dài trước đó.

Với response chứa thông tin riêng của tài khoản:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
~~~

Đối với endpoint này, không chỉ gửi no-store; còn phải tắt shared cache ở cấu hình route. Không bao giờ đưa dữ liệu người dùng, session hoặc quyền truy cập vào shared cache chỉ vì endpoint dùng GET.

### 5.5. Cache key và query string

**Cache key** là cách edge xác định hai request có thể dùng chung một bản sao hay không. Nó có thể phụ thuộc đường dẫn, query string và một số yếu tố mà sản phẩm hỗ trợ. Cấu hình query-string caching không đúng có thể gây hai loại lỗi đối lập:

- **Cache fragmentation:** hai URL trả cùng một nội dung nhưng bị coi là hai cache entry, làm giảm hit ratio.
- **Cache collision/poisoning:** hai request cần trả nội dung khác nhau bị gộp chung entry, làm nội dung sai hoặc rò rỉ dữ liệu.

Ví dụ:

~~~text
/assets/logo.svg?utm_source=email
/assets/logo.svg?utm_source=search

/api/public/catalog?lang=vi
/api/public/catalog?lang=en
~~~

Nếu query parameter utm_source không làm thay đổi response, có thể cấu hình bỏ qua nó trong cache key khi edge hỗ trợ. Ngược lại, lang ảnh hưởng nội dung và cần được phân biệt, hoặc chuyển sang URL có đường dẫn riêng như /vi/catalog và /en/catalog.

Các chế độ xử lý query string có thể gồm sử dụng đầy đủ, bỏ qua hoặc bao gồm/bỏ qua những tham số được chỉ định, tùy SKU và cách cấu hình. Không giả định mọi tham số đều vô hại. Cũng cần đặc biệt thận trọng với query chứa token, chữ ký URL, khóa truy cập hoặc mã người dùng: không thể giải quyết an toàn chỉ bằng một quy tắc “ignore all query strings”.

**Header và cookie:** không tự tin rằng edge sẽ tự phân tách cache theo Cookie, Authorization, Accept-Language hoặc mọi header Vary. Khả năng tạo cache key theo header phụ thuộc sản phẩm và cấu hình; kiểm tra tài liệu trước khi cho phép lưu response có biến thể theo user, ngôn ngữ hoặc thiết bị. Cách an toàn nhất cho dữ liệu có xác thực là bypass shared cache.

### 5.6. ETag, Last-Modified và revalidation

ETag và Last-Modified giúp client hoặc cache xác nhận một bản sao còn phù hợp mà không phải tải lại toàn bộ nội dung. Ví dụ:

~~~http
GET /index.html HTTP/1.1
Host: www.example.com
If-None-Match: "index-build-205"
~~~

Nếu dữ liệu không thay đổi và điều kiện khớp, origin có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "index-build-205"
~~~

304 thường tiết kiệm payload, nhưng vẫn có round-trip để xác thực. Với asset đã fingerprint và immutable, mục tiêu là tránh cả những request revalidation không cần thiết trong thời hạn fresh.

## 6. Nội dung tĩnh: tối ưu trước khi đưa lên CDN

CDN không thể bù hoàn toàn cho asset quá lớn hoặc trình duyệt phải thực thi JavaScript nặng. Quy trình build nên tối ưu ở nguồn.

### 6.1. JavaScript, CSS và HTML

- Minify JS/CSS/HTML ở build pipeline khi phù hợp.
- Chia bundle theo route/feature; chỉ tải những module cần cho trang hiện tại.
- Dùng tree shaking và tránh dependency không cần thiết.
- Trì hoãn mã không quan trọng, prefetch/preload có kiểm soát đối với tài nguyên thật sự cần.
- Tránh làm trang tải chậm do các script bên thứ ba, font hoặc widget không thiết yếu.
- Tạo content hash trong tên asset để dùng TTL dài.
- Luôn xuất đúng Content-Type; sai MIME có thể khiến browser từ chối file dù edge trả HTTP 200.

Đo số byte tải xuống và thời gian thực thi JS ở trình duyệt. Một file JS được phân phối từ edge rất nhanh vẫn có thể làm INP kém nếu code giữ main thread quá lâu.

### 6.2. Hình ảnh và phông chữ

- Dùng WebP/AVIF khi phù hợp và có phương án tương thích trình duyệt; ảnh vector như SVG phù hợp cho icon/đồ họa có tính chất tương ứng.
- Tạo nhiều kích thước ảnh, sử dụng srcset/sizes để thiết bị nhỏ không phải tải ảnh desktop rất lớn.
- Dùng lazy loading cho hình nằm ngoài vùng nhìn thấy ban đầu; tránh lazy-load nhầm ảnh chính của trang.
- Ưu tiên tải ảnh ảnh hưởng Largest Contentful Paint (LCP) và đặt kích thước hiển thị để giảm layout shift.
- Subset font, giảm số weight/kiểu chữ, cân nhắc font-display phù hợp.
- Đặt tên ảnh theo phiên bản/hash nếu muốn cache dài.

Ví dụ responsive image:

~~~html
<img
  src="/assets/product-640.webp"
  srcset="/assets/product-320.webp 320w, /assets/product-640.webp 640w, /assets/product-960.webp 960w"
  sizes="(max-width: 640px) 100vw, 640px"
  width="640"
  height="480"
  alt="Ảnh minh họa sản phẩm"
/>
~~~

Các URL ảnh trong ví dụ phải tồn tại và được tạo từ build/media pipeline. Tối ưu hình ảnh cần đánh giá chất lượng thị giác, không chỉ giảm kích thước bằng mọi giá.

### 6.3. Nén nội dung văn bản

Gzip và Brotli thường giúp giảm dung lượng JS, CSS, JSON và HTML; không phải lựa chọn tốt để nén lại JPEG/WebP/AVIF vốn đã được nén. Azure Front Door có khả năng hỗ trợ nén nội dung theo cơ chế và cấu hình của sản phẩm, nhưng cần xác minh loại MIME, kích thước và điều kiện request được hỗ trợ.

Kiểm tra với curl:

~~~bash
curl -sS -D - -o /dev/null \
  -H "Accept-Encoding: br,gzip" \
  https://www.example.com/assets/app.a13f9c.js
~~~

Quan sát Content-Encoding, Vary, Content-Type và kích thước response, đồng thời so sánh với trường hợp không yêu cầu nén. Header Content-Encoding: br chỉ có ý nghĩa khi payload thực sự được gửi bằng Brotli. Không tự thêm header nén nếu origin hoặc edge không nén nội dung đúng cách.

### 6.4. Giảm round-trip không cần thiết

- Sử dụng HTTPS, HTTP/2 hoặc HTTP/3 nếu edge/client hỗ trợ và đã được bật đúng.
- Tận dụng kết nối tái sử dụng và tránh chuỗi redirect nhiều bước.
- Xử lý DNS, canonical host và redirect HTTP→HTTPS sao cho không tạo vòng lặp.
- Dùng một chiến lược domain/static asset hợp lý; quá nhiều hostname có thể thêm chi phí DNS/TLS.
- Preconnect hoặc preload có chọn lọc, tránh preload quá mức cạnh tranh băng thông với nội dung quan trọng.

Không nên đánh giá hiệu năng chỉ bằng việc ping địa chỉ IP hoặc đo latency từ máy chủ chạy cùng region với origin. Hãy đo thực tế từ vị trí và thiết bị tương tự người dùng.

## 7. Quy trình cấu hình Azure Front Door có cache

### Bước 1. Chia loại URL theo khả năng cache

Lập bảng tuyến trước khi tạo profile. Ví dụ:

| Path | Origin | Cache tại edge | Ghi chú |
|---|---|---|---|
| /assets/* | Azure Storage | Bật, TTL dài cho URL có hash | Kiểm tra Content-Type và file version |
| /images/* | Azure Storage | Bật khi ảnh công khai và URL được version | Tối ưu kích thước và định dạng |
| /index.html, / | Web/static origin | TTL ngắn hoặc bypass | Cập nhật entrypoint nhanh |
| /api/public/catalog | App Service | Chỉ cân nhắc cache ngắn sau kiểm thử | Phải thiết kế cache key theo ngôn ngữ/tùy chọn |
| /api/orders/* | App Service | Tắt | Dữ liệu user, giao dịch |
| /auth/* | App Service | Tắt | Token/session và xác thực |
| /health | App Service | Thường tắt đối với phép đo sức khỏe thời gian thực | Không để cache che origin lỗi |

Đối với SPA, các đường dẫn như /products/123 có thể cần được rewrite về index.html **ở origin hoặc route phù hợp**, nhưng không được vô tình rewrite cả /api/ hay file .js không tồn tại thành HTML với HTTP 200. Quy tắc này cần được kiểm thử với deep link và response 404 hợp lệ.

### Bước 2. Chuẩn bị origin

Với tĩnh trên Azure Storage:

1. Tạo Storage Account phù hợp workload và cấu hình static website nếu chọn tính năng này.
2. Upload file build đã tối ưu lên vùng phục vụ website tĩnh; giữ cấu trúc thư mục nhất quán.
3. Thiết lập metadata Content-Type và Cache-Control trên object theo chính sách asset.
4. Kiểm tra URL origin, status 200/404, TLS và hành vi SPA fallback nếu có.
5. Kiểm soát ai được phép upload hoặc sửa object; không đặt khóa Storage Account vào mã nguồn ứng dụng.

Với App Service làm origin, tối ưu health endpoint, TLS, thời gian xử lý API và khả năng chịu tải khi edge cache miss hoặc khi vừa purge cache. Một origin yếu vẫn có thể quá tải trong sự kiện cold cache.

**Bảo mật origin:** Front Door Premium có một số tích hợp Private Link cho các loại origin được hỗ trợ. Hãy kiểm tra danh sách origin, endpoint và điều kiện SKU trước khi chọn. Với origin công khai, áp dụng hạn chế truy cập phù hợp, bảo vệ token, kiểm tra header và WAF. Không coi việc đặt Front Door phía trước là đủ để ngăn người khác gọi origin trực tiếp.

### Bước 3. Tạo Front Door profile, endpoint và origin group

Trong Azure Portal hoặc IaC, trình tự điển hình:

1. Chọn Azure Front Door Standard/Premium theo yêu cầu về WAF, kết nối origin, routing và chi phí.
2. Tạo profile trong subscription/resource group phù hợp với mô hình quản trị.
3. Tạo endpoint và origin group cho nhóm origin tĩnh; chọn protocol, host header, port và health probe phù hợp.
4. Tạo origin group riêng cho API nếu cần chính sách routing, ưu tiên hoặc health khác.
5. Gắn origin thực tế (Storage, App Service hoặc dịch vụ phù hợp) và kiểm tra TLS/hostname.
6. Tạo route gắn domain + path pattern với origin group tương ứng.
7. Cấu hình caching ở route được phép, query string strategy, compression và Rules Engine/rule set nếu tính năng tương ứng hỗ trợ.
8. Cấu hình custom domain, DNS, HTTPS certificate và redirect theo hướng dẫn Front Door.
9. Tích hợp WAF policy, diagnostic settings và Azure Monitor alert.
10. Triển khai thử trên domain phụ hoặc phạm vi kiểm thử trước khi chuyển traffic production.

Ví dụ route ở mức thiết kế, **không phải YAML API của Azure**:

~~~yaml
routes:
  - name: static-assets
    patterns: ["/assets/*"]
    originGroup: storage-static
    cache:
      enabled: true
      ttlPolicy: "long-for-fingerprinted-assets"
      queryString: "ignore-allowlisted-tracking-parameters"
      compression: true
  - name: app-html
    patterns: ["/", "/index.html"]
    originGroup: web-origin
    cache:
      enabled: false
  - name: api
    patterns: ["/api/*", "/auth/*"]
    originGroup: app-api
    cache:
      enabled: false
~~~

Trường trong đoạn trên là mô hình suy nghĩ, không thể đưa trực tiếp vào Bicep hoặc Azure CLI. Cấu hình thật phụ thuộc schema của dịch vụ. Đặc biệt cần kiểm tra độ ưu tiên route/rules để các đường dẫn nhạy cảm không vô tình rơi vào route cache chung.

### Bước 4. Kiểm tra domain và HTTPS

Một domain production nên có HTTPS hợp lệ từ client đến edge; kết nối từ edge đến origin cũng cần được cấu hình an toàn. Với custom domain, kiểm tra DNS record, chứng chỉ, hostname verification và khả năng chuyển hướng.

Nếu origin yêu cầu Host header cụ thể, cấu hình origin host header chính xác để tránh 404, lỗi certificate hoặc ứng dụng route nhầm virtual host. Đừng mở chế độ bỏ kiểm tra chứng chỉ origin chỉ để khắc phục nhanh lỗi kết nối.

### Bước 5. Cấu hình cache riêng cho từng nhóm nội dung

- Asset fingerprint: origin phát hành Cache-Control public, max-age dài, immutable; edge route cache bật.
- HTML: cấu hình revalidate/bypass theo khả năng và yêu cầu của website.
- API công khai: chỉ bật cache sau khi thống nhất nội dung nào được phép chia sẻ, query nào thay đổi response và cách invalidation.
- API riêng tư: cache disabled tại route, origin gửi no-store/private phù hợp.
- Lỗi: xem chính sách xử lý response lỗi và negative caching của sản phẩm; tránh giữ 404/500 cũ lâu sau khi đã khắc phục.

Với nhiều origin, cần đồng bộ chính sách header giữa các bản deploy; một origin gửi no-store còn origin khác gửi public cho cùng đường dẫn có thể tạo hành vi khó dự đoán.

## 8. Triển khai bản mới: versioning trước, purge sau

### 8.1. Vì sao purge không nên là chiến lược mặc định?

Purge yêu cầu dịch vụ biên loại bỏ các entry cache theo đường dẫn được chỉ định. Đây là công cụ hữu ích khi nội dung cũ phải được vô hiệu hóa, nhưng có các giới hạn:

- Thao tác có thể cần thời gian để lan tới các điểm biên.
- Purge edge **không xóa được bản sao còn fresh trong browser** của người dùng.
- Purge diện rộng có thể gây hàng loạt cache miss, tăng tải origin và chi phí egress.
- Một file đã phát hành dưới URL cũ vẫn có thể được client truy cập nếu URL đó còn tồn tại và policy cho phép.

Vì vậy, asset bất biến nên sử dụng tên chứa hash. Purge thường nên nhắm vào HTML entrypoint, file manifest hoặc URL không thể version một cách phù hợp.

### 8.2. Quy trình deploy an toàn cho SPA

Ví dụ version mới có index.html trỏ đến app.b41d8e.js thay cho app.a13f9c.js:

1. Build bundle và tạo tên file có content hash.
2. Upload **asset phiên bản mới trước** khi cập nhật HTML. Khi HTML mới được phục vụ, các file được tham chiếu đã phải tồn tại.
3. Kiểm tra status, MIME, hash/size và khả năng truy cập asset mới qua origin/edge.
4. Xuất bản HTML entrypoint mới với thời hạn cache ngắn hoặc revalidation.
5. Nếu cần, purge chính xác /index.html và những path không version.
6. Chạy smoke test từ nhiều địa điểm, cả trình duyệt mới và trình duyệt có cache cũ.
7. Giữ lại asset đã hash từ phiên bản trước ít nhất qua khoảng thời gian khách hàng còn có thể sử dụng HTML cũ.
8. Theo dõi lỗi 404 JS/CSS, tỷ lệ cache miss, p95 TTFB và phản hồi người dùng.

**Rollback:** đưa HTML về phiên bản trước chỉ an toàn nếu các asset mà HTML cũ tham chiếu vẫn có sẵn. Xóa toàn bộ asset cũ ngay sau mỗi deploy có thể làm những tab đang mở hoặc trang trong browser cache bị hỏng.

### 8.3. Khi nào purge khẩn cấp?

Purge có thể cần thiết khi nội dung công khai sai, thông tin phải gỡ bỏ hoặc một tài nguyên chưa version đang bị cache lâu. Tuy nhiên, nếu dữ liệu nhạy cảm đã từng bị public qua CDN, purge không chứng minh không ai đã tải dữ liệu đó. Cần kích hoạt quy trình sự cố, thu hồi quyền/URL, kiểm tra log, ngăn truy cập origin và đánh giá nghĩa vụ xử lý rò rỉ dữ liệu.

## 9. Đo đạc và kiểm chứng cache

### 9.1. Kiểm tra response header bằng curl

Chạy hai lần liên tiếp một request tới asset tĩnh ở domain thử nghiệm:

~~~bash
curl -sS -D - -o /dev/null \
  https://www.example.com/assets/app.a13f9c.js

curl -sS -D - -o /dev/null \
  https://www.example.com/assets/app.a13f9c.js
~~~

Quan sát:

- HTTP status và redirect.
- Cache-Control, Expires, ETag, Last-Modified.
- Age, Via, X-Cache hoặc các header chẩn đoán khác **nếu dịch vụ thực tế gửi**.
- Content-Type, Content-Encoding và Vary.
- Sự khác biệt giữa lần truy cập đầu và lần sau.

Không mặc định request đầu tiên luôn miss và request thứ hai luôn hit: edge cache có thể đã được làm nóng bởi người khác; HEAD và GET, các edge khác nhau, TTL hoặc request header có thể dẫn đến hành vi khác. Trạng thái cache nên được xác nhận thêm qua diagnostics/metrics của Front Door, không chỉ một header.

Đo TTFB bằng curl:

~~~bash
curl -sS -o /dev/null \
  -w "status=%{http_code} dns=%{time_namelookup}s connect=%{time_connect}s tls=%{time_appconnect}s ttfb=%{time_starttransfer}s total=%{time_total}s\n" \
  https://www.example.com/assets/app.a13f9c.js
~~~

Các con số đo được phản ánh từ **máy đang chạy curl**, không tự đại diện cho người dùng mọi khu vực. Kết quả chịu ảnh hưởng DNS, cache nóng/lạnh, mạng hiện tại, TLS session reuse và tải thiết bị.

### 9.2. Lấy cấu hình Front Door bằng Azure CLI

Ví dụ lệnh chỉ đọc cho Front Door Standard/Premium:

~~~bash
az account show --output table

az afd endpoint show \
  --resource-group rg-edge-prod \
  --profile-name afd-shop-prod \
  --endpoint-name ep-shop-prod \
  --output json

az afd route list \
  --resource-group rg-edge-prod \
  --profile-name afd-shop-prod \
  --endpoint-name ep-shop-prod \
  --output table

az afd origin-group list \
  --resource-group rg-edge-prod \
  --profile-name afd-shop-prod \
  --output table
~~~

Thay tên resource cho đúng môi trường. Tùy phiên bản Azure CLI, có thể cần module/extension tương ứng. Các lệnh liệt kê cấu hình không chứng minh dữ liệu đang được cache đúng; cần kết hợp kiểm thử request và dữ liệu logs.

### 9.3. Azure Monitor và log truy cập

Nên bật diagnostic settings phù hợp, chuyển log/metric đến nơi phân tích do tổ chức lựa chọn. Theo dõi:

1. Số request và dữ liệu edge phục vụ theo domain/route.
2. Cache hit và cache miss, cùng byte hit nếu metric hỗ trợ.
3. Origin latency, số origin requests và khả năng origin group hoạt động.
4. HTTP 4xx/5xx, WAF blocks và lỗi TLS/origin.
5. p50/p95/p99 latency từ client hoặc công cụ synthetic/RUM.
6. Dữ liệu theo khu vực, thiết bị và mạng.
7. Chi phí edge delivery, origin egress và log ingestion.

Ví dụ KQL cho trường hợp log được gửi vào bảng AzureDiagnostics và Category tương ứng với Front Door Access Log:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(1h)
| where Category == "FrontDoorAccessLog"
| summarize Requests = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Cấu hình resource-specific tables có thể khiến dữ liệu nằm ở bảng khác và schema khác. Hãy xem tên bảng/trường hiện có trong workspace trước khi sửa truy vấn; không coi truy vấn trả rỗng là bằng chứng không có lưu lượng nếu diagnostic settings chưa được bật hoặc log chưa ingest.

### 9.4. Benchmark trước và sau khi bật cache

Thiết lập hai trạng thái đối chiếu, cùng nội dung và tập người dùng mục tiêu:

| Chỉ số | Trước tối ưu | Sau tối ưu | Diễn giải |
|---|---|---|---|
| Median/p95 TTFB ở Việt Nam | Đo thực tế | Đo thực tế | Edge có giúp nhóm người dùng nội địa không? |
| Median/p95 TTFB tại châu Âu | Đo thực tế | Đo thực tế | Khoảng cách tới origin được giảm thế nào? |
| LCP và INP trên mobile | Đo thực tế | Đo thực tế | JS/ảnh có còn là nút cổ chai? |
| Cache hit ratio / byte hit | Đo thực tế | Đo thực tế | TTL và cache key có hợp lý không? |
| Origin request volume | Đo thực tế | Đo thực tế | Có giảm tải origin hay chỉ thêm một lớp mạng? |
| Error rate (4xx/5xx) | Đo thực tế | Đo thực tế | Route/WAF/cache có gây lỗi mới không? |
| Chi phí theo lưu lượng | Đo thực tế | Đo thực tế | Tiết kiệm origin có bù chi phí edge không? |

Cần đo trong khoảng thời gian đủ đại diện, bao gồm cache cold/warm, traffic cao điểm, nhiều địa điểm và các phiên bản asset. Cân nhắc synthetic monitoring và Real User Monitoring (RUM) để tránh kết luận chỉ từ mạng văn phòng của nhóm phát triển.

## 10. Ước lượng tác động của cache lên lưu lượng origin

Giả sử trong một khoảng thời gian, người dùng gửi 1.000.000 request cho một asset có dung lượng trung bình 100 KB. Đây là ví dụ **minh họa**, không phải số đo hoặc bảng giá Azure:

~~~text
Tổng dữ liệu client nhận (ước lượng):
  1.000.000 × 100 KB ≈ 100 GB

Nếu 80% request được edge cache hit:
  Request cần lấy từ origin ≈ 20% × 1.000.000 = 200.000
  Dữ liệu origin gửi (ước lượng) ≈ 20 GB

Phần dữ liệu không cần lấy từ origin (ước lượng) ≈ 80 GB
~~~

Tính toán bỏ qua header, revalidation, nén, range request, các bản thể asset khác kích thước và những lần edge fetch lặp ở các điểm biên. **Cache hit theo request không nhất thiết tương đương byte hit**, nên cần kiểm tra dữ liệu thực tế.

Chi phí không giảm 80% tương ứng, vì Front Door/CDN có phí phân phối tới người dùng, request và các hạng mục khác; origin có thể tính thêm egress, thao tác Storage, compute và log ingestion. Khi so sánh kinh tế, hãy lập ngân sách theo dịch vụ, traffic vùng địa lý và mô hình giá thực tế.

## 11. Bảo mật và độ tin cậy tại biên

### 11.1. Shared cache là ranh giới dữ liệu quan trọng

Rủi ro nghiêm trọng nhất của edge caching không chỉ là nội dung cũ mà còn là **trả dữ liệu của người A cho người B**. Những trường hợp nguy hiểm:

- Cache một GET /api/orders trả JSON theo cookie hoặc bearer token.
- Bỏ qua query string mặc dù query chứa language, tenant ID, variant hoặc quyền xem nội dung.
- Cache response có Set-Cookie hoặc dữ liệu xác thực mà chưa đánh giá hành vi cache của dịch vụ.
- Quy tắc route rộng như /* bật cache, vô tình bao trùm /auth/* và /checkout/*.
- Dùng một cache key chung cho nhiều host hoặc biến thể nội dung cần tách biệt.

Nguyên tắc khởi đầu an toàn: **chỉ cache nội dung công khai, xác định rõ biến thể và có thể chia sẻ giữa các client**. API riêng tư và transaction nên bypass hoàn toàn ở edge. Header no-store/private ở origin là lớp bổ sung, không thay thế cấu hình route.

### 11.2. TLS, WAF và origin access

- Dùng HTTPS cho cả đoạn client→edge và edge→origin.
- Cấu hình domain/certificate hợp lệ; tránh disable certificate validation ở origin.
- Áp dụng WAF policy phù hợp để lọc lưu lượng độc hại; kiểm thử false positive trước khi chuyển sang chặn rộng.
- Hạn chế truy cập trực tiếp origin nếu dịch vụ và SKU hỗ trợ; xác thực origin request theo phương án đáng tin cậy.
- Không đưa key bí mật, connection string hoặc access token vào SPA bundle hoặc file công khai ở Storage.
- Dùng RBAC với quyền tối thiểu cho người quản trị Front Door, Storage và pipeline deploy.
- Bật log truy cập cần thiết; tránh log chứa dữ liệu nhạy cảm không cần thiết.

WAF không thay thế bảo mật ứng dụng, và CDN không thay thế backup/khôi phục. Một sự cố ở origin, DNS, routing hoặc cấu hình rule vẫn có thể ảnh hưởng toàn bộ người dùng.

### 11.3. Khả năng sẵn sàng và failover origin

Front Door có thể hỗ trợ định tuyến đến nhiều origin, kiểm tra sức khỏe và lựa chọn origin theo tính năng cấu hình. Với hệ thống yêu cầu HA, cần kiểm tra:

1. Có ít nhất hai origin phù hợp thiết kế nếu cần dự phòng.
2. Health probe phản ánh sức khỏe ứng dụng, không chỉ trả HTTP 200 từ một trang tĩnh.
3. Nội dung tĩnh ở các origin đã đồng bộ hoặc có cùng cơ chế versioning.
4. Quy tắc cache không giữ lỗi 5xx quá lâu hoặc che lấp sự cố origin.
5. Chuyển origin không làm sai tenant, cookie, DNS hay đường tới database.
6. Có diễn tập failover và rollback theo quy trình thay đổi.

Edge cache có thể giúp giảm tải trong sự cố origin ngắn, nhưng không nên giả định mọi asset sẽ tiếp tục được phục vụ khi origin mất kết nối, vì các entry có thể hết hạn hoặc chưa được cache tại từng edge.

## 12. Tình huống thực tế: cửa hàng trực tuyến nhiều khu vực

Một nhóm phát triển ứng dụng bán hàng trên Azure có ba loại yêu cầu:

- Trang chủ và file JS/CSS/ảnh được phát hành từ pipeline.
- Danh mục sản phẩm công khai thay đổi vài lần mỗi ngày.
- Giỏ hàng, thông tin thanh toán và đơn hàng riêng của từng người dùng.

Ban đầu, mọi request đi tới App Service trong một region. Người dùng ở xa origin gặp TTFB cao cho asset; mỗi lần tải trang mới tạo nhiều request lên App Service.

### Thiết kế tối ưu

**Nhóm 1: asset tĩnh.** Pipeline build file app.<hash>.js và style.<hash>.css, nén trước khi phù hợp, tối ưu ảnh WebP/AVIF, upload vào Storage. Front Door route /assets/* bật cache dài; browser được phép giữ asset immutable.

**Nhóm 2: HTML entrypoint.** Front Door giữ TTL rất ngắn hoặc không cache, cho phép người dùng nhận manifest phiên bản mới. Pipeline upload asset trước khi đổi HTML; purge giới hạn ở entrypoint khi cần.

**Nhóm 3: API công khai.** Có thể cân nhắc cache ngắn cho danh mục nếu business chấp nhận một độ trễ cập nhật nhất định. Phải xác định biến thể theo ngôn ngữ, tiền tệ, vùng và query string; nếu không chắc chắn, ban đầu bypass.

**Nhóm 4: API riêng tư.** Đơn hàng, giỏ hàng, checkout, auth luôn bypass edge cache. Ứng dụng gửi no-store, vẫn xác thực người dùng và kiểm tra quyền ở backend.

Sau triển khai, nhóm so sánh p95 TTFB theo quốc gia, LCP trên mobile, cache hit/byte hit, 4xx/5xx, lưu lượng origin và chi phí. Nếu hit ratio tốt nhưng LCP không cải thiện, cần điều tra ảnh chính, JavaScript blocking và tài nguyên bên thứ ba thay vì chỉ tăng TTL.

### Khi có sự cố nội dung cũ

Sau một release, trình duyệt một số người dùng vẫn nhận index.html cũ, trong khi asset cũ đã bị xóa. Nhóm ứng phó:

1. Kiểm tra response header của HTML và cache behavior ở edge.
2. Xác định người dùng có browser cache đang fresh hay edge stale.
3. Khôi phục asset cũ cần thiết nếu khả thi để các tab đang mở hoạt động.
4. Đặt chính sách HTML revalidate, purge đúng path ở edge nếu cần.
5. Sửa pipeline: upload asset trước, giữ asset cũ qua thời hạn chuyển tiếp.
6. Kiểm tra nhiều region và loại trình duyệt; ghi lại nguyên nhân vào runbook.

Cách xử lý này giải quyết nguyên nhân vòng đời asset thay vì chỉ lặp lại purge toàn bộ cache.

## 13. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Hit ratio thấp dù nhiều request | Query tracking làm phân mảnh cache key, TTL quá ngắn, response không cacheable | Kiểm tra cache-key strategy, Cache-Control, log hit/miss |
| Người dùng nhận nội dung cũ | TTL browser/edge quá dài, file không version, purge chưa lan | So sánh URL, Age/header, manifest, quy trình deploy |
| CSS/JS trả HTTP 200 nhưng website lỗi | Origin phục vụ sai MIME, rewrite SPA trả HTML thay vì JS | Kiểm tra Content-Type, response body và route fallback |
| API trả dữ liệu người dùng khác | Cache route quá rộng, cache key không xét biến thể, response chứa thông tin riêng tư | Tắt route cache ngay, kích hoạt quy trình bảo mật và điều tra |
| Front Door trả lỗi 502/504 | Origin không truy cập được, health/TLS/host header sai, timeout | Kiểm tra origin health, DNS, certificate, host header, backend logs |
| Request bị 403 | WAF, chính sách Storage, xác thực origin hoặc ứng dụng | Phân biệt WAF logs, origin logs và quy tắc truy cập |
| p95 latency vẫn cao | API động không cache, origin chậm, tải asset lớn, render JS nặng | Dùng synthetic + RUM, phân tích waterfall và backend traces |
| Một vùng nhanh, vùng khác chậm | Cache warm khác nhau, origin fetch xa, mạng last-mile | Kiểm tra điểm đo, route, cache metrics theo vùng |
| Purge xong vẫn thấy bản cũ | Browser cache còn fresh, service worker, proxy trung gian | Kiểm tra DevTools, service worker, Cache-Control và URL |
| Compression không hoạt động | MIME/size không phù hợp, client không hỗ trợ, cấu hình chưa bật | So sánh Accept-Encoding, Content-Encoding và payload |
| Chi phí tăng bất ngờ | Traffic hoặc egress edge tăng, purge nhiều, cache miss, log ingestion | Đối chiếu Cost Management, hit/byte hit, origin fetches |

Đối với website dùng service worker hoặc PWA, cần chú ý thêm cache tại service worker. Edge purge không điều khiển trực tiếp bộ nhớ đệm do JavaScript của service worker quản lý. Kịch bản cập nhật PWA cần quy trình versioning và activation riêng.

## 14. Checklist triển khai và kiểm thử

### Trước khi bật edge cache

1. Phân loại public/private và liệt kê route cần cache hoặc bypass.
2. Kiểm tra header Cache-Control, Content-Type, ETag và dữ liệu user/cookie.
3. Áp dụng content hash cho asset dài hạn; xác định TTL HTML.
4. Kiểm tra origin, TLS, host header, DNS và quyền truy cập.
5. Xác định strategy cho query string và các biến thể hợp lệ.
6. Cấu hình WAF, logging và phương án rollback.
7. Đặt chỉ số baseline từ ít nhất một khu vực gần và một khu vực xa origin.

### Trong kiểm thử

1. Request hai lần cùng asset; đối chiếu header và trạng thái cache bằng log/metric.
2. Kiểm tra URL có query tracking và query làm thay đổi nội dung.
3. Kiểm tra /auth, /api/orders và các response cá nhân hóa **không được chia sẻ giữa user**.
4. Kiểm tra browser refresh, ETag/304, cache cold/warm và deployment phiên bản mới.
5. Kiểm tra HTTP status, MIME, nén, CSS/JS, SPA deep link, 404 và custom domain.
6. Kiểm tra WAF false positive, origin health và đường truy cập trực tiếp origin.
7. Đo p95 TTFB, LCP, lỗi và origin requests theo vùng trước/sau thay đổi.

### Sau khi phát hành

1. Giám sát cache hit, origin load, 4xx/5xx, WAF blocks và chi phí.
2. Đặt alert cho origin health, lỗi bất thường và biến động hit ratio.
3. Kiểm tra tính đúng đắn sau mỗi release, đặc biệt HTML và asset mapping.
4. Duy trì runbook purge mục tiêu, rollback và xử lý sự cố rò rỉ dữ liệu.
5. Rà soát TTL và cache key khi sản phẩm thêm ngôn ngữ, tenant hoặc biến thể nội dung.

## 15. Câu hỏi tự kiểm tra

1. **Cache hit khác cache miss thế nào?** Hit trả bản sao còn phù hợp từ tầng cache; miss cần lấy dữ liệu từ origin hoặc tầng phía sau.
2. **Tại sao không đặt TTL một năm cho index.html không version?** Browser và edge có thể giữ entrypoint cũ lâu, khiến người dùng không nhận bản deploy mới.
3. **File app.a13f9c.js có TTL dài, khi sửa code nên làm gì?** Tạo URL mới với content hash khác thay vì ghi đè file cũ.
4. **no-cache có đồng nghĩa với no-store không?** Không; no-cache yêu cầu revalidate trước khi tái sử dụng, còn no-store yêu cầu không lưu.
5. **Có thể cache /api/orders dùng cookie phiên đăng nhập tại edge không?** Không nên. Response riêng tư cần tắt shared cache và kiểm soát truy cập ở ứng dụng.
6. **Nếu bỏ qua toàn bộ query string, lỗi gì có thể xảy ra?** Các request theo ngôn ngữ, tenant hoặc biến thể dữ liệu có thể dùng chung response sai.
7. **Purge Front Door có xóa browser cache không?** Không. Browser cache và service worker có vòng đời riêng.
8. **Vì sao hit ratio cao chưa chắc LCP tốt?** Trang có thể vẫn tải ảnh lớn hoặc chạy JS nặng; LCP phản ánh trải nghiệm render.
9. **Azure Front Door khác Application Gateway ở điểm nào?** Front Door phục vụ phân phối HTTP(S) tại biên toàn cầu; Application Gateway chủ yếu là gateway lớp ứng dụng trong khu vực.
10. **ETag có ích gì?** Cho phép revalidate và có thể giảm việc tải lại payload khi nội dung không đổi.
11. **Một route cache cho /assets/* có thể dùng cho /auth/* không?** Không. Route đăng nhập phải được phân tách, bypass caching và bảo vệ riêng.
12. **Khi bật cache làm chi phí origin giảm, chi phí tổng có chắc chắn giảm không?** Không. Còn phí edge delivery, request, egress, WAF, logs và các hạng mục khác.
13. **Cần đo gì để khẳng định tối ưu có hiệu quả?** TTFB/p95 theo vùng, LCP/INP, hit/byte hit, origin request, lỗi và chi phí thực tế.

## 16. Tài liệu tham khảo

- [Azure Front Door documentation](https://learn.microsoft.com/azure/frontdoor/) — dịch vụ phân phối ứng dụng toàn cầu, caching, routing và bảo mật.
- [Caching with Azure Front Door](https://learn.microsoft.com/azure/frontdoor/front-door-caching) — hành vi cache, TTL và các nguyên tắc cấu hình.
- [Azure Front Door Standard/Premium](https://learn.microsoft.com/azure/frontdoor/standard-premium/overview) — tổng quan tier và tính năng.
- [Azure Storage static website hosting](https://learn.microsoft.com/azure/storage/blobs/storage-blob-static-website) — hosting HTML/CSS/JS/ảnh tĩnh.
- [Azure Static Web Apps](https://learn.microsoft.com/azure/static-web-apps/overview) — hosting và deployment ứng dụng web tĩnh.
- [Azure Monitor documentation](https://learn.microsoft.com/azure/azure-monitor/) — metrics, diagnostic settings và alerting.
- [HTTP caching (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching) — semantics của Cache-Control, ETag và revalidation.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — phân tích chi phí vận hành.

Khi triển khai thật, cần đối chiếu chính xác dịch vụ Front Door/CDN, SKU, route caching, rule set, origin access và các giới hạn tính năng tại thời điểm thực hiện. Quy tắc cốt lõi là: **cache dài cho asset công khai và bất biến, cập nhật nhanh cho entrypoint, không dùng shared cache cho dữ liệu riêng tư, và quyết định dựa trên số liệu trải nghiệm thực tế**.
