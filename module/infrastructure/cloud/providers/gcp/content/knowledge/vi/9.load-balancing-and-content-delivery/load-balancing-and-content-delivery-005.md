# URL maps và định tuyến theo host, path

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích **URL map** là gì, vị trí của nó trong **Application Load Balancer** và cách định tuyến HTTP(S) theo **hostname** và **URL path**.
2. Phân biệt **URL map default**, **host rule**, **path matcher**, **path rule**, **route rule**, **backend service** và **backend bucket**.
3. Dự đoán đúng đích đến khi có đường dẫn chính xác, wildcard cuối path, nhiều host, default backend và route ưu tiên.
4. Cấu hình một URL map mẫu bằng **gcloud** để tách website, API và nội dung tĩnh; biết cách kiểm thử trước và sau khi triển khai.
5. Nhận biết giới hạn theo loại load balancer, khác biệt giữa **routing**, **redirect** và **rewrite**, cùng các vấn đề bảo mật, độ tin cậy, quan sát và chi phí.

## 1. Vì sao cần định tuyến theo host và path?

Một cửa hàng trực tuyến có thể muốn dùng một địa chỉ HTTPS công khai và phục vụ nhiều thành phần:

- **https://shop.example.com/**: trang web bán hàng.
- **https://api.shop.example.com/v1/orders**: API Java/Spring phiên bản 1.
- **https://api.shop.example.com/v2/orders**: API phiên bản 2.
- **https://static.shop.example.com/images/logo.png**: hình ảnh và nội dung tĩnh.

Nếu mỗi thành phần có địa chỉ IP, chứng chỉ và entry point riêng, việc quản lý DNS, TLS, firewall, phát hành và giám sát sẽ phức tạp hơn. **Application Load Balancer** hoạt động ở lớp 7, có thể nhận yêu cầu HTTP(S) rồi dựa vào **Host** và **path** để chuyển tiếp đến đúng backend.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học lựa chọn dịch vụ từ Compute Engine, GKE, Cloud Run đến lưu trữ, cơ sở dữ liệu, đồng thời bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. URL maps là một thành phần giúp đặt nhiều workload phía sau entry point HTTP(S) chung và kiểm soát đường đi của yêu cầu.

**URL map** là tài nguyên cấu hình tập hợp các quy tắc định tuyến HTTP(S) tới **backend services** hoặc **backend buckets**. Nó có thể được sử dụng bởi Application Load Balancers và một số sản phẩm khác như Cloud Service Mesh. Bài này tập trung vào **Application Load Balancer**; chi tiết và khả năng tính năng khác nhau theo chế độ global, regional, external, internal và classic.

## 2. URL map nằm ở đâu trong kiến trúc load balancing?

~~~mermaid
flowchart LR
    U["Trình duyệt / API client"] --> DNS["DNS: tên miền → IP frontend"]
    DNS --> FR["Forwarding rule<br/>IP, cổng, giao thức"]
    FR --> TP["Target HTTP(S) proxy<br/>TLS với HTTPS"]
    TP --> UM["URL map<br/>hostRules + pathMatchers"]
    UM --> BS1["Backend service<br/>web"]
    UM --> BS2["Backend service<br/>Java API"]
    UM --> BB["Backend bucket<br/>static assets"]
    BS1 --> W["MIG / NEG"]
    BS2 --> A["VM / GKE / Cloud Run<br/>qua loại backend hỗ trợ"]
    BB --> CS["Cloud Storage"]
~~~

Các thành phần đảm nhiệm việc khác nhau:

| Thành phần | Vai trò chính | Có quyết định host/path không? |
|---|---|---|
| **Cloud DNS hoặc nhà cung cấp DNS** | Chuyển tên miền sang IP frontend | Không chọn backend theo URL path |
| **Forwarding rule** | Nhận traffic tại IP và cổng; trỏ tới target proxy | Không đọc path |
| **Target HTTP(S) proxy** | Xử lý HTTP, TLS khi dùng HTTPS; liên kết URL map | Dùng URL map để quyết định định tuyến |
| **URL map** | Đọc host/path và áp dụng rule/fallback để chọn đích | **Có** |
| **Backend service** | Phân phối request đến nhóm instance hoặc network endpoints, có cấu hình health/capacity | Không phải nơi khai báo host/path của URL map |
| **Backend bucket** | Hướng lưu lượng đến bucket Cloud Storage được hỗ trợ | Có thể nhận traffic theo URL map |

**Lưu ý:** tạo URL map chưa tự tạo IP, DNS record, HTTPS certificate, backend hoặc frontend. Một URL map chỉ có hiệu lực với request khi **target HTTP(S) proxy** đang phục vụ traffic sử dụng nó.

### URL map có hỗ trợ mọi kiểu load balancer?

Không. URL map dùng cho những sản phẩm xử lý HTTP(S) lớp 7 phù hợp, đặc biệt là **Application Load Balancers**. Một **passthrough Network Load Balancer** lớp 4 không dùng URL map để đọc **/api** hoặc **/images**. Nếu yêu cầu là định tuyến TCP/UDP thuần túy, cần chọn họ load balancer theo giao thức và kiến trúc.

| Loại Application Load Balancer | Loại URL map | Nhận xét |
|---|---|---|
| **Global external** | **Global** | External managed; nhiều khả năng traffic management nâng cao |
| **Classic external** | **Global** | Có host/path rules; một số tính năng nâng cao không được hỗ trợ |
| **Regional external** | **Regional** | Tài nguyên URL map đặt theo region |
| **Cross-region internal** | **Global** | Internal managed, phục vụ nội bộ qua các region theo thiết kế |
| **Regional internal** | **Regional** | Internal managed trong phạm vi khu vực |

Việc **URL map là global hay regional** phải tương thích với target proxy và backend resources của load balancer. Không thể lấy một URL map global đặt vào proxy regional tùy ý.

## 3. Cấu trúc bên trong URL map

Một URL map có cấu trúc logic:

~~~text
URL map: shop-map
|
|-- defaultService: web-main
|
|-- hostRules:
|   |-- api.shop.example.com    → pathMatcher: api-paths
|   |-- static.shop.example.com → pathMatcher: static-paths
|
|-- pathMatchers:
|   |-- api-paths
|   |   |-- /v1      → api-v1
|   |   |-- /v1/*    → api-v1
|   |   |-- /v2      → api-v2
|   |   |-- /v2/*    → api-v2
|   |   '-- defaultService: api-default
|   |
|   '-- static-paths
|       '-- defaultBackendBucket: static-assets
~~~

Đây là **sơ đồ khái niệm**, không phải nội dung YAML áp dụng trực tiếp. Các backend trong ví dụ phải được tạo và cấu hình trước.

### 3.1. URL map default

**defaultService** hoặc **defaultBackendBucket** ở **cấp URL map** là đích dự phòng khi **không có host rule nào khớp** hostname nhận được. URL map đơn giản nhất chỉ có một default và chưa cần host rules hay path matchers.

Ví dụ request **https://unknown.shop.example.com/v1/orders** không khớp hai host rule trong sơ đồ, nên đi đến **web-main**, dù path **/v1/orders** giống đường của API. **Host được chọn trước path**.

### 3.2. Host rule

Một **host rule** gắn **một hoặc nhiều hostname** với đúng **một path matcher**. Nhiều host rules có thể dùng chung path matcher, nhưng một hostname không được chỉ sang hai host rules đối lập trong cùng URL map.

Ví dụ:

| Host từ HTTP request | Path matcher được chọn |
|---|---|
| api.shop.example.com | **api-paths** |
| static.shop.example.com | **static-paths** |
| shop.example.com | Không có host rule riêng → **URL map default** |

Hostnames có thể là FQDN cụ thể hoặc mẫu wildcard được sản phẩm hỗ trợ, ví dụ **\*.example.com**. Đừng dùng IP IPv4/IPv6 làm tên trong host rule. Cần hiểu wildcard khớp theo hostname; nó không phải biểu thức regex tùy ý cho mọi chuỗi.

### 3.3. Path matcher

**Path matcher** là tập rule định tuyến trong phạm vi host mà nó phục vụ. Mỗi matcher có **default riêng**, dùng khi đã khớp host nhưng path không khớp rule cụ thể.

Ví dụ request **https://api.shop.example.com/health**:

1. Host **api.shop.example.com** khớp **api-paths**.
2. Không có path rule **/health**.
3. Chuyển đến **api-default** của path matcher.

Request này **không quay lại** default **web-main** ở cấp URL map.

### 3.4. Path rules và route rules

| Thuộc tính | **pathRules** cơ bản | **routeRules** nâng cao |
|---|---|---|
| Mục tiêu | Chọn đích theo path đơn giản | Điều kiện và hành động phức tạp |
| Match | Path chính xác hoặc prefix với wildcard ở cuối theo cú pháp hỗ trợ | Exact/prefix/regex, header/query param và các điều kiện được hỗ trợ |
| Thứ tự | Chọn exact path trước, sau đó wildcard có prefix dài nhất | Dựa trên **priority**: số nhỏ có ưu tiên cao hơn |
| Đích | Một backend service/bucket hoặc hành động phù hợp | Có thể chọn service, redirect hoặc routeAction như weighted backend |
| Khi nào chọn? | API v1/v2, assets, web cơ bản | Canary release, traffic split, header-based routing, rewrite hoặc redirect nâng cao |

Trong **một path matcher**, khai báo **pathRules hoặc routeRules** theo cấu trúc được hỗ trợ; không trộn cả hai tùy tiện vào cùng một matcher. Không phải mọi chế độ load balancer hỗ trợ đầy đủ mọi trường của routeRules.

## 4. Thứ tự xử lý request: host → path → backend

~~~mermaid
flowchart TD
    R["HTTP(S) request đến proxy"] --> H{"Hostname khớp hostRule?"}
    H -->|Không| G["URL map default"]
    H -->|Có| PM["Chọn pathMatcher gắn với hostRule"]
    PM --> P{"Path/routing condition khớp?"}
    P -->|Có| D["Backend hoặc action của rule"]
    P -->|Không| F["Path matcher default"]
    G --> B["Forward / redirect theo cấu hình"]
    D --> B
    F --> B
~~~

**Thứ tự có ý nghĩa:** hệ thống không tìm tất cả path rules rồi chọn backend trước khi xét host. Với một host đã khớp, chỉ các rules thuộc path matcher được gắn với host đó mới quyết định đích.

### 4.1. Exact path và wildcard không đồng nghĩa

Hai biểu thức cơ bản:

- /api: chỉ path **/api**.
- /api/\*: khớp các đường bắt đầu từ **/api/** với phần sau đó, nhưng **không khớp /api**.

Đó là lý do cấu hình muốn phục vụ cả **/v1** và **/v1/orders** thường cần **hai path patterns**: **/v1** và **/v1/\***.

| Request path | **/v1** | **/v1/\*** | Kết quả nếu cả hai trỏ api-v1 |
|---|---|---|---|
| /v1 | Có | Không | **api-v1** |
| /v1/ | Không | Có | **api-v1** |
| /v1/orders | Không | Có | **api-v1** |
| /v1/orders/123 | Không | Có | **api-v1** |
| /v1beta/orders | Không | Không | **matcher default** |
| /V1/orders | Không theo quy tắc phân biệt chữ | Không theo quy tắc phân biệt chữ | **matcher default** |

**Quy tắc path cơ bản:** một wildcard dùng trong path rule phải theo cú pháp hỗ trợ (ví dụ phần đuôi **/\***), không phải **/v\*1** hoặc regex tự do. Nếu có nhiều wildcard cùng khớp, prefix dài hơn được ưu tiên, ví dụ **/api/admin/\*** trước **/api/\***.

### 4.2. Ví dụ kết quả routing theo host và path

Giả sử URL map ở phần 3 đã được triển khai:

| Request | Đích kỳ vọng | Lý do |
|---|---|---|
| **shop.example.com/** | **web-main** | Không có host rule riêng → URL map default |
| **api.shop.example.com/v1/orders** | **api-v1** | Host khớp api-paths; prefix /v1/* |
| **api.shop.example.com/v1** | **api-v1** | Exact /v1 |
| **api.shop.example.com/v2/orders** | **api-v2** | Prefix /v2/* |
| **api.shop.example.com/health** | **api-default** | Host khớp nhưng path không khớp |
| **static.shop.example.com/images/a.png** | **static-assets** | Path matcher static có default backend bucket |
| **unknown.shop.example.com/v2/orders** | **web-main** | Host không khớp nên bỏ qua pathRules API |

Việc chọn backend không đồng nghĩa backend khỏe mạnh hoặc API thực sự trả **200 OK**. URL map quyết định đường đến; backend service, health check, firewall và ứng dụng còn ảnh hưởng đến kết quả cuối cùng.

### 4.3. Hostname, port, query string và TLS

Trong ví dụ **https://api.shop.example.com:443/v1/orders?state=pending**:

- **Hostname:** api.shop.example.com, dùng cho host matching.
- **Path:** /v1/orders, dùng cho pathRules cơ bản.
- **Query:** state=pending; pathRules cơ bản không phải công cụ phân nhánh theo query value. **routeRules** có thể khớp query parameters trong các chế độ hỗ trợ.
- **TLS/SNI:** chứng chỉ và kết nối HTTPS phải hoạt động đúng ở target HTTPS proxy. URL map **không tự cấp hoặc xác nhận** chứng chỉ cho hostname.

Nếu khách hàng gửi hostname chưa được cho phép trong TLS hoặc ứng dụng, cần có kiểm soát riêng; host routing không thay thế xác thực người dùng hay chặn Host header độc hại ở tầng ứng dụng.

## 5. Thực hành: xây URL map cho một cửa hàng

Bài thực hành dùng **global external Application Load Balancer** với global URL map. Mọi tên sau là ví dụ; phải thay project ID, backend names và domain bằng giá trị thật đã được tạo.

### 5.1. Chuẩn bị backend và quyền

Giả sử project **shop-prod-001** đã có:

| Resource | Loại | Vai trò |
|---|---|---|
| **web-main** | Global backend service | Trang chủ và fallback |
| **api-default** | Global backend service | API fallback, health hoặc lỗi có kiểm soát |
| **api-v1** | Global backend service | Ứng dụng Java phiên bản 1 |
| **api-v2** | Global backend service | Ứng dụng Java phiên bản 2 |
| **static-assets** | Global backend bucket | Cloud Storage static assets nếu loại LB hỗ trợ |
| **shop-map** | Global URL map cần tạo | Định tuyến HTTP(S) |

Backend service có thể dùng instance groups hoặc NEGs phù hợp; ví dụ **serverless NEG** đến Cloud Run khi kiến trúc và loại load balancer hỗ trợ. **Tạo backend service hoặc bucket là công việc riêng**. URL map trỏ tới tài nguyên đã tồn tại; nó không triển khai container Java, tạo VM hoặc nạp dữ liệu lên Cloud Storage.

Người thực hiện cần quyền Compute Load Balancing phù hợp (bao gồm quyền trên URL map và quyền **use** tài nguyên backend được tham chiếu). Nếu có cross-project service referencing, phải xử lý cả IAM ở project chứa backend. Thử trước với một dự án riêng, tránh thay đổi production khi chưa được review.

### 5.2. Đọc hiện trạng trước khi thay đổi

~~~bash
gcloud config get-value project

gcloud compute backend-services list \
  --project=shop-prod-001 --global

gcloud compute backend-buckets list \
  --project=shop-prod-001

gcloud compute url-maps list \
  --project=shop-prod-001
~~~

Kiểm tra kỹ **loại backend**, **load balancing scheme**, tên chính xác và phạm vi global/region. Nếu đang chỉnh URL map đã tồn tại, nên **export và review** trước khi import hoặc dùng CLI cập nhật.

### 5.3. Tạo URL map với default backend

~~~bash
gcloud compute url-maps create shop-map \
  --project=shop-prod-001 \
  --default-service=web-main \
  --global

gcloud compute url-maps describe shop-map \
  --project=shop-prod-001 \
  --global
~~~

Ở trạng thái này URL map chỉ có default **web-main**. Mọi hostname/path đều chọn web-main. Cấu hình này hữu ích để xác minh fallback trước khi thêm phân nhánh.

### 5.4. Tạo path matcher cho API

~~~bash
gcloud compute url-maps add-path-matcher shop-map \
  --project=shop-prod-001 \
  --global \
  --path-matcher-name=api-paths \
  --default-service=api-default \
  --path-rules="/v1=api-v1,/v1/*=api-v1,/v2=api-v2,/v2/*=api-v2" \
  --new-hosts=api.shop.example.com
~~~

Lệnh tạo **path matcher** tên **api-paths**, có default **api-default** và 4 pattern; đồng thời **--new-hosts** tạo host rule ánh xạ **api.shop.example.com** đến matcher đó. CLI yêu cầu matcher được tham chiếu bởi host rule, vì vậy cách tạo cùng lúc này tránh matcher không có host sử dụng.

### 5.5. Bổ sung host rule nếu API có hostname thứ hai

Giả sử doanh nghiệp còn muốn tên **api-alt.shop.example.com** dùng cùng các path rules. Khi matcher **api-paths** đã tồn tại:

~~~bash
gcloud compute url-maps add-host-rule shop-map \
  --project=shop-prod-001 \
  --global \
  --hosts=api-alt.shop.example.com \
  --path-matcher-name=api-paths
~~~

Lệnh thêm một host rule **khác** tham chiếu lại matcher đã có. Cả **api.shop.example.com** và **api-alt.shop.example.com** dùng **api-paths**; các host không khớp vẫn dùng URL map default **web-main**. Nếu bài thực hành chỉ có một hostname API, có thể bỏ bước 5.5.

### 5.6. Thêm path matcher cho nội dung tĩnh

~~~bash
gcloud compute url-maps add-path-matcher shop-map \
  --project=shop-prod-001 \
  --global \
  --path-matcher-name=static-paths \
  --default-backend-bucket=static-assets \
  --new-hosts=static.shop.example.com
~~~

Lệnh đồng thời tạo **static-paths** và host rule của **static.shop.example.com**. Tất cả request tới host này đi đến backend bucket nếu không có rule khác. Backend bucket phục vụ nội dung Cloud Storage phù hợp và có thể sử dụng **Cloud CDN** khi được bật/cấu hình. URL map không mặc nhiên bật caching hoặc cấp quyền đọc object.

### 5.7. Đọc lại cấu hình

~~~bash
gcloud compute url-maps describe shop-map \
  --project=shop-prod-001 \
  --global \
  --format="yaml(name,defaultService,hostRules,pathMatchers)"
~~~

Kiểm tra cả hai host rules, tên path matcher tương ứng, default của API/static và bốn path rules. Ghi lại output trước khi đưa vào target proxy.

### 5.8. Gắn URL map vào frontend (kiến thức liên quan)

Target HTTP(S) proxy tham chiếu URL map; forwarding rule trỏ tới proxy. Nếu proxy đã tồn tại, việc đổi URL map của proxy là thay đổi riêng, có tác động lên traffic:

~~~bash
# Đọc URL map mà HTTPS proxy hiện tại đang dùng
gcloud compute target-https-proxies describe shop-https-proxy \
  --project=shop-prod-001 \
  --global \
  --format="yaml(name,urlMap)"
~~~

Chỉ khi đã được phê duyệt và kiểm tra đầy đủ mới thực hiện thao tác đổi URL map cho proxy theo quy trình phát hành của tổ chức. URL map mới **có thể chưa nhận traffic** dù đã tạo thành công nếu chưa có proxy sử dụng nó.

## 6. Cấu hình URL map bằng YAML và kiểm thử đường đi

Với bản đồ phức tạp hoặc quản lý qua CI/CD, YAML export/import giúp review thay đổi. Ví dụ logic dưới đây là cấu hình **minh họa** cho global URL map; **PROJECT_ID** và tên backend phải thay bằng tài nguyên thực.

~~~yaml
kind: compute#urlMap
name: shop-map
defaultService: projects/PROJECT_ID/global/backendServices/web-main

hostRules:
  - hosts:
      - api.shop.example.com
    pathMatcher: api-paths
  - hosts:
      - static.shop.example.com
    pathMatcher: static-paths

pathMatchers:
  - name: api-paths
    defaultService: projects/PROJECT_ID/global/backendServices/api-default
    pathRules:
      - paths: ["/v1", "/v1/*"]
        service: projects/PROJECT_ID/global/backendServices/api-v1
      - paths: ["/v2", "/v2/*"]
        service: projects/PROJECT_ID/global/backendServices/api-v2

  - name: static-paths
    defaultService: projects/PROJECT_ID/global/backendBuckets/static-assets
~~~

**Giải thích:** hai host rules tham chiếu hai matchers khác nhau; mỗi matcher chỉ có path rules phù hợp với host của nó. **web-main** là default của toàn URL map; **api-default** và **static-assets** là defaults của hai matchers.

Nếu xuất cấu hình hiện hành, làm việc trên bản export giúp giữ nguyên những trường không có trong ví dụ này. Không import nguyên ví dụ rút gọn lên URL map production vì có thể làm mất những thiết lập khác.

### 6.1. Tạo ma trận kiểm thử trước khi release

| Host | Path | Expected backend |
|---|---|---|
| shop.example.com | / | web-main |
| api.shop.example.com | /v1 | api-v1 |
| api.shop.example.com | /v1/orders | api-v1 |
| api.shop.example.com | /v2/orders | api-v2 |
| api.shop.example.com | /v1beta | api-default |
| api.shop.example.com | /health | api-default |
| static.shop.example.com | /images/logo.png | static-assets |
| unexpected.shop.example.com | /v1/orders | web-main |

Tập kiểm thử cố ý bao gồm **negative cases**: **/v1beta** không được gửi nhầm đến v1, hostname lạ không được tự đi vào API.

### 6.2. URL map configuration tests

Với **global external** hoặc **classic Application Load Balancer**, gcloud hỗ trợ **URL map validate** để kiểm tra cấu hình và những **tests** được khai báo mà **không cập nhật URL map đang chạy**.

Ví dụ một phần tests trong file YAML đã được export, sau khi thay **PROJECT_ID**:

~~~yaml
tests:
  - description: API v1 exact path
    host: api.shop.example.com
    path: /v1
    service: projects/PROJECT_ID/global/backendServices/api-v1

  - description: API v1 nested path
    host: api.shop.example.com
    path: /v1/orders
    service: projects/PROJECT_ID/global/backendServices/api-v1

  - description: API unknown path uses matcher default
    host: api.shop.example.com
    path: /v1beta
    service: projects/PROJECT_ID/global/backendServices/api-default

  - description: Unknown host uses URL map default
    host: unexpected.shop.example.com
    path: /v2/orders
    service: projects/PROJECT_ID/global/backendServices/web-main
~~~

Các test là phần của **cùng file URL map YAML hoàn chỉnh**, không phải một file YAML chỉ chứa **tests** độc lập. Việc validate cần đúng quyền IAM và tài nguyên backend phù hợp.

~~~bash
# Xuất cấu hình hiện có để review
gcloud compute url-maps export shop-map \
  --project=shop-prod-001 \
  --global \
  --destination=shop-map.yaml

# Chỉnh shop-map.yaml: route rules + tests, giữ nguyên các field cần thiết
# Kiểm tra tĩnh, không tạo/cập nhật URL map
gcloud compute url-maps validate \
  --project=shop-prod-001 \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --source=shop-map.yaml
~~~

**Giới hạn:** **gcloud compute url-maps validate** theo tài liệu cấu hình Google Cloud **không hỗ trợ regional external Application Load Balancer và internal Application Load Balancer**. Đối với loại không hỗ trợ, cần review bằng API/Console, kiểm tra config và chạy thử nghiệm thực tế ở môi trường kiểm thử theo công cụ phù hợp. Không được ghi “đã validate” nếu công cụ của loại LB đó không hỗ trợ.

### 6.3. Import khi đã có phê duyệt

~~~bash
# Ví dụ thao tác có tác động, chỉ thực hiện sau review và chuẩn bị rollback
gcloud compute url-maps import shop-map \
  --project=shop-prod-001 \
  --global \
  --source=shop-map.yaml
~~~

**Import có thể thay thế cấu hình URL map hiện có.** Trước import cần diff bản hiện hành, xác nhận backends, giữ bản export để rollback và kiểm tra loại LB. Sau import phải kiểm tra request thật, không chỉ dựa vào việc lệnh trả exit code 0.

### 6.4. Kiểm thử thực tế trên frontend

Khi URL map đã được proxy dùng và DNS/TLS được cấu hình:

~~~bash
curl -i https://api.shop.example.com/v1/orders
curl -i https://api.shop.example.com/v2/orders
curl -i https://api.shop.example.com/v1beta
curl -I https://static.shop.example.com/images/logo.png
~~~

Nếu chưa chuyển DNS sang frontend mới nhưng đã biết **LB_IP**, có thể kiểm tra hostname và TLS/SNI bằng **--resolve**:

~~~bash
curl --resolve api.shop.example.com:443:LB_IP \
  -i https://api.shop.example.com/v1/orders
~~~

Thay **LB_IP** bằng IP frontend thực và dùng chứng chỉ hợp lệ cho hostname. Cách này điều khiển DNS resolution cục bộ của **curl**, không thay đổi DNS của người dùng và không bỏ qua kiểm tra TLS.

Để xác nhận chính xác backend nào nhận request, có thể tạm dùng header đánh dấu phiên bản trong môi trường thử nghiệm hoặc đối chiếu Cloud Logging/Cloud Monitoring của load balancer và backends. Không đưa các header debug nhạy cảm ra production.

## 7. Nâng cao: routeRules và các điều kiện ngoài path

Khi yêu cầu chỉ là **/v1 → API v1** và **/v2 → API v2**, **pathRules** là đủ. Khi cần quyết định theo request headers, query parameters, tỷ lệ traffic, redirects hoặc rewrites, những chế độ Application Load Balancer được hỗ trợ có thể dùng **routeRules**.

### 7.1. Priority thấp hơn được xét trước

Với routeRules, số **priority** nhỏ hơn được đánh giá trước. Ví dụ:

| Priority | Match condition | Backend |
|---:|---|---|
| 10 | Header **x-canary: true** và prefix **/api/** | api-canary |
| 100 | Prefix **/api/** | api-stable |
| Default | Không khớp các routeRules | web-default |

Một request có **x-canary: true** và path **/api/orders** có thể khớp cả hai rule, nhưng rule **priority 10** được xét trước. Request thiếu header canary sẽ đi vào rule 100.

Trong một **routeRule**, các mục ở **matchRules** có logic **OR** giữa các mục; các điều kiện đồng thời trong cùng một **matchRule** có logic **AND**. Để bắt buộc vừa path vừa header, đặt chúng trong **cùng một matchRule**.

~~~yaml
# Đoạn minh họa thuộc pathMatchers[].routeRules của LB hỗ trợ
routeRules:
  - priority: 10
    matchRules:
      - prefixMatch: /api/
        headerMatches:
          - headerName: x-canary
            exactMatch: "true"
    service: projects/PROJECT_ID/global/backendServices/api-canary

  - priority: 100
    matchRules:
      - prefixMatch: /api/
    service: projects/PROJECT_ID/global/backendServices/api-stable
~~~

**Điều kiện tiên quyết:** chọn một path matcher dùng **routeRules**, không đồng thời đặt **pathRules** trong cùng matcher. Cần kiểm tra hỗ trợ field của loại LB trước khi import.

### 7.2. Route theo query parameter

Ví dụ chỉ khi truy vấn chứa **?preview=true** mới gửi sang backend preview; còn lại dùng stable. **pathRules** cơ bản không xử lý logic này. Các điều kiện **queryParameterMatches** của **routeRules** cho phép triển khai trên chế độ LB hỗ trợ.

Các điều kiện được hỗ trợ gồm exact, prefix, regex và một số kiểu match khác tùy sản phẩm. **Regex** cần theo cú pháp **RE2**, không phải cú pháp PCRE tùy ý. **Classic Application Load Balancer** không hỗ trợ regular expression routing như các chế độ managed được chỉ ra trong tài liệu.

### 7.3. Weighted backend services cho rollout

Một routeRule có thể chia lưu lượng giữa hai backend services theo trọng số:

~~~yaml
# Đoạn minh họa cho route rule /api/ trên LB hỗ trợ
routeRules:
  - priority: 20
    matchRules:
      - prefixMatch: /api/
    routeAction:
      weightedBackendServices:
        - backendService: projects/PROJECT_ID/global/backendServices/api-stable
          weight: 95
        - backendService: projects/PROJECT_ID/global/backendServices/api-canary
          weight: 5
~~~

Ví dụ **95/5** là tỷ lệ phân phối có kỳ vọng theo thống kê, **không bảo đảm đúng 95 request stable và 5 request canary trong mỗi 100 request**. Health, session affinity, cấu hình backend và cache có thể làm số quan sát khác dự tính. Cần đo error rate, latency, request count và business metrics trước khi tăng tỷ lệ canary.

## 8. Routing, redirect và rewrite: ba hành vi dễ nhầm

| Hành vi | URL người dùng nhìn thấy | Request được xử lý | Ví dụ |
|---|---|---|---|
| **Route** | Giữ nguyên | Chọn backend phù hợp | **/v2/orders → api-v2** |
| **Redirect** | Client nhận **HTTP 3xx + Location** và thường gửi request mới | Chuyển hướng ở phía client | **http://... → https://...**, hoặc **/old → /new** |
| **Rewrite** | Thường giữ URL client đã yêu cầu | LB thay host/path khi **forward đến backend** | **/public/v1/orders → /orders** ở backend |

### 8.1. Redirect khác backend routing

Ví dụ muốn mọi request HTTP đổi sang HTTPS, có thể cấu hình **URL map redirect** trả response 301/302/307/308 theo khả năng dịch vụ. Với global external Application Load Balancer, tài liệu hướng dẫn thường cần **một partial HTTP load balancer** (forwarding rule + target HTTP proxy + redirect URL map) dùng chung IP frontend với HTTPS load balancer. Một URL map hướng đến backend HTTPS **không tự biến** các request HTTP trên cổng 80 thành redirect.

### 8.2. Rewrite cần thận trọng

Giả sử backend Java chỉ cung cấp **/orders**, còn API công khai là **/v1/orders**. URL rewrite có thể xóa prefix **/v1** ở request chuyển tới backend. Khi đó application logs có thể ghi nhận đường dẫn đã được rewrite; hãy đưa điều này vào chẩn đoán và kiểm thử.

**URL rewrite không tương đương HTTP redirect.** Client vẫn thấy URL mà nó gọi; backend nhận đường dẫn mới theo hành động tại load balancer. Rewrite phải được kiểm thử với route paths, cache keys, signature validation và auth logic của ứng dụng.

### 8.3. Nơi nào áp dụng được?

Khả năng **redirect**, **rewrite**, **header modification**, **traffic splitting**, **retry/timeout** và **regex match** khác nhau giữa **classic**, **global/regional external** và **internal Application Load Balancers**. Trước khi dùng một trường trong YAML, tra bảng hỗ trợ theo sản phẩm và API schema tương ứng. Không chuyển nguyên config advanced của một LB sang loại khác chỉ vì cả hai đều có URL map.

## 9. URL map có quan hệ gì với Cloud CDN và phân phối nội dung?

Khi đưa assets qua **backend bucket** hoặc một backend service hỗ trợ **Cloud CDN**, URL map quyết định **request được gửi đến backend nào**, còn Cloud CDN quyết định caching và phục vụ nội dung tại edge theo cấu hình.

Ví dụ:

~~~text
https://static.shop.example.com/images/logo.png
        |
        v
hostRule: static.shop.example.com
        |
        v
pathMatcher: static-paths
        |
        v
backend bucket: static-assets
        |
        v
Cloud CDN (nếu đã bật) / Cloud Storage
~~~

**Không phải có backend bucket là đã bật Cloud CDN.** Các thiết lập cache mode, TTL, signed URL/cookie, cache key và invalidation là cấu hình của backend bucket/service và Cloud CDN, không phải phép so khớp host/path của URL map.

### 9.1. Cache ảnh hưởng cách đo routing

Khi thay backend, những response đã cache có thể vẫn được phục vụ ở edge theo chính sách TTL. Do đó hãy phân biệt:

- Request **đã được load balancer route theo URL map** tới backend/cache tương ứng.
- Request **thực sự tới origin** hay được trả từ cache.
- Nội dung stale là vấn đề **cache policy hoặc invalidation**, chưa chắc URL map trỏ sai.

Trước rollout thay đổi ảnh hưởng assets, xác định cách đặt tên file theo hash, TTL, cache invalidation và chính sách rollback. Kết hợp Cloud Monitoring và logs tại lớp phù hợp để tránh kết luận nhầm khi backend không có log request vì response được cache.

## 10. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách chẩn đoán |
|---|---|---|
| **/v1** đi vào default nhưng **/v1/orders** đúng | Chỉ khai báo **/v1/\*** | Thêm exact path **/v1** |
| **/v1beta** bị route nhầm tới v1 | Dùng prefix quá rộng trong routeRules, hoặc rule wildcard không đúng ý | Dùng path rules **/v1**, **/v1/\*** hoặc condition chặt hơn |
| **api.shop.example.com** trả website | Host rule không tồn tại/sai host, proxy trỏ URL map khác | Kiểm tra Host, **url-maps describe**, target proxy |
| Host khớp nhưng path lạ vẫn vào backend API | Path matcher default đặt api-default | Đây là fallback theo thiết kế; điều chỉnh nếu không mong muốn |
| Không thấy thay đổi sau khi tạo URL map | Target proxy vẫn dùng map cũ hoặc DNS trỏ frontend khác | **target-https-proxies describe**, forwarding rule, DNS/IP |
| Mọi path đi vào cùng backend | URL map chỉ có default, chưa gắn host rule hoặc matcher | Xem **hostRules**, **pathMatchers**, **defaultService** |
| Request trả **404** | Có thể backend/application không có endpoint, hoặc map chọn error backend | Dùng routing tests, header/log của backend và kiểm tra app |
| Request trả **502/503** | Backend không có endpoint khỏe, timeout, firewall/health check hoặc lỗi application | Health, backend logs, proxy logs, firewall |
| Một số đường dẫn không hoạt động | Phân biệt chữ hoa/thường, slash, path prefix, query/redirect/rewrite | Kiểm thử exact path, **/path/**, **/path/x**, encoded path |
| Traffic canary khác 95/5 | Số lượng request nhỏ, session affinity, cache, health hoặc cấu hình traffic split | Phân tích phân phối đủ lớn, logs và health |
| SSL/TLS báo lỗi dù rule đúng | Certificate không khớp hostname hoặc DNS/SNI sai | TLS cert, target HTTPS proxy, domain/IP frontend |
| Sau import mất route cũ | YAML import thiếu field hoặc ghi đè map hiện có | Diff export trước/sau và rollback có kiểm soát |
| Không validate được regional URL map | Lệnh **validate** có giới hạn theo loại LB | Dùng quy trình kiểm thử thích hợp của sản phẩm |
| Routing đúng nhưng xuất hiện chi phí cao | CDN miss, egress, backend autoscaling, request đột biến | Báo cáo billing, metrics của LB, CDN và backend |

### Quy trình điều tra theo lớp

1. **DNS/IP:** tên miền có trỏ đến đúng frontend không?
2. **TLS/Proxy:** HTTPS certificate hợp lệ, proxy có sử dụng URL map dự kiến không?
3. **Host:** HTTP Host header có khớp hostRule mong muốn không?
4. **Path:** URL path có exact match, wildcard match hoặc routeRule priority như dự kiến không?
5. **Fallback:** request đang chọn URL map default hay path matcher default?
6. **Backend:** service/bucket có tồn tại, healthy, đủ IAM và route/network cho traffic?
7. **Cache:** response đến từ Cloud CDN hay từ origin?
8. **Log và test:** so sánh cùng hostname/path giữa bản cấu hình đã review và request thật.

Không nên nới IAM hoặc firewall toàn cục chỉ vì thấy 404: đó có thể là lỗi định tuyến hoặc endpoint ứng dụng. Cũng không nên chỉ nhìn response code để kết luận URL map sai khi chứng chỉ hoặc backend health chưa đúng.

## 11. Bảo mật, độ tin cậy và tự động hóa phát hành

### 11.1. Bảo mật nhiều host trên cùng frontend

- **TLS certificate** phải bao phủ hostname phục vụ; kiểm tra wildcard cert có đáp ứng phạm vi domain thực không.
- **Host rules** chỉ quyết định định tuyến, không cung cấp **authentication** hoặc **authorization** cho dữ liệu. Bảo vệ API bằng cơ chế ứng dụng, IAM, IAP/Cloud Armor hoặc tính năng tương thích được lựa chọn đúng phạm vi.
- Chọn **default backend** an toàn cho host lạ, ví dụ backend trả **404** có kiểm soát, để không vô tình công bố nội dung không thuộc domain.
- Nếu định tuyến theo header hoặc query do client điều khiển, không dùng chúng làm bằng chứng quyền truy cập đặc biệt khi thiếu xác thực thích hợp.
- Review **backend IAM** khi có service account của Cloud Run, cross-project backends hoặc private services. Một URL map hợp lệ không tự cấp quyền truy cập mọi tài nguyên.

### 11.2. Độ tin cậy

Một URL map tốt có đường fallback rõ ràng, nhưng fallback **không tự chuyển traffic sang API khỏe khác** nếu backend hỏng. Mỗi backend service cần health checks, capacity, autoscaling và timeout phù hợp với loại backend.

Với API đặt hàng, có thể đặt health endpoints không phụ thuộc quá nhiều hệ thống ngoài để tránh quá nhạy, nhưng phải đủ phản ánh khả năng phục vụ. Khi rollout v2, dùng môi trường kiểm thử, canary, theo dõi lỗi 4xx/5xx, latency phân vị và SLO trước khi chuyển toàn bộ request sang v2.

### 11.3. CI/CD và Infrastructure as Code

Luồng phù hợp:

~~~mermaid
flowchart LR
    D["Thay đổi URL map<br/>trong Git / IaC"] --> R["Review + kiểm tra cấu trúc"]
    R --> V["Validate/tests nếu LB hỗ trợ"]
    V --> S["Triển khai staging"]
    S --> P["Smoke tests host/path + backend"]
    P --> A["Phê duyệt production"]
    A --> M["Apply / import có kiểm soát"]
    M --> O["Metrics, logs, rollback"]
~~~

Nếu dùng **Terraform**, quản lý URL map, proxy và backends cùng state/phạm vi resource phù hợp. Tránh xen kẽ sửa tay trong Console rồi apply Terraform mà không reconcile drift, vì bản IaC cũ có thể ghi đè thay đổi.

**Rollback:** lưu cấu hình export đã biết hoạt động, giữ backend cũ trong thời gian quan sát, biết lệnh hoặc pipeline khôi phục URL map. Việc rollback routing không tự khôi phục dữ liệu do backend mới đã ghi; cần cân nhắc tương thích API/schema khi canary.

### 11.4. Chi phí

Cân nhắc chi phí **Application Load Balancer**, lượng dữ liệu xử lý, egress, Cloud CDN/cache egress, backend service compute, Cloud Storage/backend buckets và logging. Định tuyến theo host/path không biến hai backend thành một tài nguyên miễn phí.

Tối ưu có thể đến từ giảm request đến origin qua cache, điều chỉnh kích thước backend và sử dụng path routing hợp lý. Nhưng quyết định luôn phải cân bằng với latency, hit rate, bảo mật và độ tin cậy. Theo dõi billing theo project, labels, service và workload thực tế.

## 12. Tình huống thiết kế: thương mại điện tử trên GCP

Doanh nghiệp **Minh Phát** muốn phục vụ frontend web, API Java v1/v2 và hình ảnh sản phẩm qua một Application Load Balancer bên ngoài. Hệ thống gồm:

- **web-main** trên managed instance group hoặc backend phù hợp.
- **api-v1** và **api-v2** trên Cloud Run qua **serverless NEG** hoặc backend service tương ứng với thiết kế.
- **static-assets** là Cloud Storage backend bucket có thể bật Cloud CDN.
- **Cloud SQL** là cơ sở dữ liệu của API, không nhận request trực tiếp từ URL map.

### 12.1. Kế hoạch routing

| Host/path | Backend | Chủ sở hữu |
|---|---|---|
| shop.example.com/* | web-main | Frontend team |
| api.shop.example.com/v1 và /v1/* | api-v1 | Java API team |
| api.shop.example.com/v2 và /v2/* | api-v2 | Java API team |
| api.shop.example.com/khác | api-default | Java API team |
| static.shop.example.com/* | static-assets | Content team |
| Host không nằm trong allowlist | Error/default backend an toàn | Platform team |

Trong dự án thật, nên quyết định default cho hostname lạ dựa trên chính sách an toàn. Ví dụ **web-main** dùng để học routing, nhưng khi phục vụ nhiều tenant hoặc môi trường nhạy cảm, có thể thay bằng backend **unknown-host** trả lỗi có kiểm soát.

### 12.2. Kế hoạch kiểm thử

1. **Unit routing tests:** kiểm tra đủ exact paths, wildcard, các host và default; xác nhận **/v1beta** không vào v1.
2. **Integration:** gọi frontend thật hoặc dùng **curl --resolve** để xác nhận proxy, TLS và backend.
3. **Security:** thử Host header lạ, path traversal/canonicalization, endpoint yêu cầu token, các path admin không dự kiến công bố.
4. **Performance:** đo latency từng backend, Cloud CDN hit rate, lưu lượng và 5xx khi tải tăng.
5. **Resilience:** kiểm tra backend unhealthy và khả năng rollback v2 về v1 theo cơ chế phát hành.
6. **Cost:** theo dõi chi phí egress, CDN, compute và log trước/sau thay đổi.

### 12.3. Ví dụ sai lầm trong rollout

Một kỹ sư đổi host rule **api.shop.example.com** sang path matcher **web-paths**, nhưng vẫn còn pathRules v1/v2 ở **api-paths**. Kết quả API trả trang web hoặc 404, dù hai backend API hoàn toàn khỏe.

**Nguyên nhân:** chỉ path matcher được **host rule tham chiếu** mới được đánh giá. Các rules trong matcher không được gắn host sẽ không ảnh hưởng request đến hostname đó.

**Cách xác minh:** đọc URL map, so sánh hostRules/pathMatchers, chạy cấu hình tests và smoke tests. Cách sửa là gắn lại đúng path matcher đã review, không phải cấp thêm IAM cho API.

## 13. Bài tập thực hành

### Bài tập A: dự đoán backend

Cho URL map có:

- URL map default = **web-main**.
- Host **api.example.com → api-matcher**.
- **api-matcher** có path rules **/orders**, **/orders/\*** → **orders-api**; **/users/\*** → **users-api**; matcher default = **api-fallback**.
- Host **static.example.com → assets-matcher**; matcher default = **assets-bucket**.

Hãy chọn backend cho từng request:

| Request | Đáp án |
|---|---|
| api.example.com/orders | **orders-api** |
| api.example.com/orders/123 | **orders-api** |
| api.example.com/users | **api-fallback** |
| api.example.com/users/123 | **users-api** |
| api.example.com/orders2 | **api-fallback** |
| static.example.com/logo.svg | **assets-bucket** |
| unknown.example.com/orders/123 | **web-main** |

Giải thích vì sao **/users** không khớp **/users/\*** và hostname không khớp không được phép dùng path rules của api-matcher.

### Bài tập B: thiết kế migration v1 → v2

Một API Java v1 đang phục vụ 100% traffic ở **/api/orders**; nhóm muốn phát hành v2 thử nghiệm cho 5% requests và có khả năng rollback.

Hãy:

1. Chọn **pathRules** hay **routeRules** và giải thích.
2. Đề xuất cách phân chia traffic và những chỉ số phải theo dõi.
3. Xác định rủi ro khi v1/v2 ghi vào cùng Cloud SQL schema.
4. Mô tả bước phê duyệt và rollback nếu v2 làm tăng 5xx hoặc latency.

**Hướng giải:** Dùng **routeRules + weightedBackendServices** khi load balancer hỗ trợ. Tỷ lệ 95/5 chỉ là kỳ vọng; đo trên đủ request, theo dõi lỗi và tương thích dữ liệu. Rollback routing cần giữ v1 tương thích với dữ liệu đã ghi trong giai đoạn canary.

### Bài tập C: phân biệt redirect và rewrite

Ứng dụng legacy chỉ hỗ trợ **/users**, nhưng API công khai là **/v2/users**. Đồng thời người dùng HTTP phải chuyển sang HTTPS.

Hãy phân biệt:

- Hành vi cần **rewrite** để backend nhận **/users** trong khi client vẫn thấy **/v2/users**.
- Hành vi cần **redirect** để client chuyển từ HTTP sang HTTPS với response 3xx.
- Các cấu hình phụ trợ cần có: HTTPS certificate, target proxies, forwarding rules và hỗ trợ tính năng đúng loại load balancer.

### Bài tập D: kiểm thử và chẩn đoán

Nhóm tạo URL map mới nhưng production vẫn gửi tất cả request tới **web-main**.

Hãy viết runbook 5–8 bước gồm: DNS và IP, proxy đang tham chiếu URL map nào, hostRules và pathMatchers, URL map default và matcher default, gcloud validate nếu hỗ trợ, curl --resolve, backend health, logs và rollback.

## 14. Ghi nhớ và tài liệu tham khảo

**Những nguyên tắc chính:**

1. **URL map** là tài nguyên định tuyến HTTP(S) lớp 7: **hostname** chọn **hostRule/pathMatcher**, còn **path** chọn pathRule hoặc routeRule tương ứng.
2. Có **hai fallback**: default ở **cấp URL map** khi host không khớp, và default ở **path matcher** khi host khớp nhưng không có path/route rule phù hợp.
3. **/api** khác **/api/\***. Exact path và wildcard cần được thiết kế, kiểm thử tách bạch.
4. **pathRules** dùng cho đường dẫn đơn giản; **routeRules** hỗ trợ ưu tiên, điều kiện nâng cao, weighted traffic theo sản phẩm.
5. **Redirect** trả 3xx cho client, **rewrite** biến đổi request đến backend, **routing** chọn đích. Không nhầm lẫn ba hành vi.
6. **Global và regional URL maps** khác nhau; tính năng validate và traffic management có giới hạn theo loại load balancer.
7. URL map không thay thế **DNS, TLS, IAM, Cloud Armor, health check, CDN policy hoặc giám sát**. Luôn kiểm thử đường đi từ frontend tới backend thật.

**Tài liệu Google Cloud chính thức:**

1. [URL maps overview](https://docs.cloud.google.com/load-balancing/docs/url-map-concepts) — cấu trúc, host/path order, fallback, routeRules và giới hạn.
2. [Use URL maps](https://docs.cloud.google.com/load-balancing/docs/url-map) — CLI cấu hình, export/import, configuration tests và validate.
3. [gcloud compute url-maps add-host-rule](https://docs.cloud.google.com/sdk/gcloud/reference/compute/url-maps/add-host-rule) — tham số host và path matcher.
4. [gcloud compute url-maps add-path-matcher](https://docs.cloud.google.com/sdk/gcloud/reference/compute/url-maps/add-path-matcher) — khai báo matcher, default và path rules.
5. [gcloud compute url-maps validate](https://docs.cloud.google.com/sdk/gcloud/reference/compute/url-maps/validate) — phạm vi và giới hạn kiểm thử tĩnh.
6. [Traffic management for global external Application Load Balancers](https://docs.cloud.google.com/load-balancing/docs/https/traffic-management-global) — routeRules, headers, weighted backends, rewrites và redirects.
7. [Set up HTTP-to-HTTPS redirect for global external Application Load Balancers](https://docs.cloud.google.com/load-balancing/docs/https/setting-up-global-http-https-redirect) — cấu hình redirect bằng HTTP frontend bổ sung.
8. [Cloud CDN overview](https://docs.cloud.google.com/cdn/docs/overview) — caching tại edge và backend hỗ trợ.
