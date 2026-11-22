# Cloud Armor kết hợp load balancer tại biên

Một API Java phục vụ khách hàng qua `api.example.com`, chạy trên Cloud Run hoặc GKE và được công bố bằng External Application Load Balancer. Trong giờ cao điểm, hệ thống nhận một lượng lớn HTTP request bất thường vào `/login`; một số request có dấu hiệu SQL injection, một số xuất phát từ mạng có lịch sử lạm dụng. Nếu toàn bộ lưu lượng đi thẳng đến ứng dụng, CPU, connection pool, database và chi phí autoscaling có thể bị ảnh hưởng trước khi nhóm phát hiện nguyên nhân.

**Google Cloud Armor** giúp áp dụng các quy tắc bảo vệ lưu lượng tại hạ tầng của Google, trước khi request đến backend được load balancer bảo vệ. Kết hợp Cloud Armor với **Cloud Load Balancing** tạo một lớp kiểm soát ở biên cho ứng dụng web: nhận request qua một frontend được quản lý, chọn backend dựa trên routing, đánh giá security policy, rồi chỉ chuyển những request hợp lệ tới dịch vụ. Cloud Armor hỗ trợ lọc theo IP, quốc gia, thuộc tính HTTP, quy tắc WAF và hạn chế tần suất truy cập; từng khả năng phụ thuộc loại policy, load balancer và gói dịch vụ.

Bài thuộc chương **Cân bằng tải và phân phối nội dung** của học phần **CLOUD_PROVIDERS_GCP**. Kiến thức về Cloud Armor nối tiếp việc tổ chức project, IAM, VPC và đi vào các tình huống vận hành Compute Engine, GKE, Cloud Run, Cloud Storage, tự động hóa phát hành, quan sát độ tin cậy và kiểm soát chi phí.

Sau bài học, bạn có thể:

- Giải thích vị trí của Cloud Armor trong đường đi của HTTP(S) request qua load balancer.
- Phân biệt **backend security policy**, **edge security policy** và **network edge security policy**.
- Thiết kế rule theo priority, mặc định allow/deny, preview, WAF và rate limiting.
- Gắn policy đúng backend service hoặc backend bucket, xét ảnh hưởng của Cloud CDN cache.
- Triển khai policy qua Console, `gcloud` và Infrastructure as Code.
- Chặn đường truy cập trực tiếp tới backend, xem log và thử thay đổi trước khi enforce.
- Nhận diện giới hạn bảo vệ, chi phí và lỗi cấu hình thường gặp.

## 1. Vì sao Cloud Armor thường đi cùng load balancer?

External Application Load Balancer là bộ cân bằng tải HTTP(S) lớp 7. Frontend tiếp nhận lưu lượng với IP/port, xử lý TLS theo cấu hình, URL map chọn backend service hoặc backend bucket, rồi hạ tầng proxy chuyển request tới backend thích hợp. Cloud Armor áp security policy cho **đích được bảo vệ** trong tuyến đó, giúp lọc request trước khi nó tiêu thụ tài nguyên ứng dụng.

~~~mermaid
flowchart LR
    A["Client trên Internet"] --> B["Cloud DNS / Frontend IP + TLS"]
    B --> C["External Application Load Balancer"]
    C --> D["URL map → Backend service"]
    D --> E["Cloud Armor security policy"]
    E -- "Cho phép" --> F["Cloud Run / GKE / Compute Engine"]
    E -- "Từ chối / giới hạn" --> G["HTTP 403 / 429 / hành động khác"]
    F --> H["Database / Storage / dịch vụ phụ thuộc"]
~~~

Đây là **sơ đồ khái niệm** cho trường hợp không minh họa Cloud CDN. Vị trí và thứ tự đánh giá thực tế thay đổi theo loại load balancer, edge/backend policy, CDN và IAP. Một frontend có thể định tuyến tới nhiều backend service; **policy phải được gắn vào đúng tài nguyên backend nhận request**, không chỉ cấu hình IP frontend hoặc DNS.

| Thành phần | Vai trò | Không tự giải quyết được |
|---|---|---|
| **Cloud DNS** | Cho tên miền trỏ đến frontend IP | Không tự lọc HTTP hay chống SQL injection |
| **External Application Load Balancer** | Nhận HTTP(S), TLS, routing và phân phối tới backend | Không tự thay thế toàn bộ quy tắc WAF tùy chỉnh |
| **Cloud Armor** | Đánh giá request theo security policy, lọc/rate-limit tại hạ tầng Google | Không sửa lỗ hổng ứng dụng hay thay xác thực |
| **Cloud CDN** | Cache nội dung phù hợp và giảm tải origin | Không thay quy tắc phân quyền cho dữ liệu riêng |
| **VPC firewall / ingress control** | Giới hạn đường mạng vào backend | Không hiểu toàn bộ nội dung HTTP như WAF |
| **IAM / IAP / xác thực ứng dụng** | Xác định danh tính và quyền truy cập | Không thay thế phát hiện traffic flood tại biên |

Lợi ích thiết kế là giảm lượng request không mong muốn trước khi chúng chạm backend, bảo vệ availability và tạo nơi quản trị các quy tắc chung. Tuy nhiên, **Cloud Armor chỉ kiểm soát traffic đi qua những đường và tài nguyên mà policy thực sự áp dụng**. Nếu người dùng có thể gọi trực tiếp endpoint backend không qua load balancer, họ có thể bỏ qua lớp policy này.

## 2. Chọn đúng loại Cloud Armor security policy

Tên gọi “ở biên” dễ gây nhầm lẫn vì Cloud Armor có nhiều loại policy. Cần chọn theo **loại frontend**, **nơi gắn policy** và **các thuộc tính được hỗ trợ**.

| Loại policy | Gắn ở đâu? | Trường hợp chính | Phạm vi và lưu ý |
|---|---|---|---|
| **Backend security policy** (`CLOUD_ARMOR`) | Backend service | WAF, điều kiện HTTP/IP, rate limiting để bảo vệ ứng dụng | Hỗ trợ nhiều Application Load Balancer và một số proxy Network Load Balancer; tính năng tùy frontend |
| **Edge security policy** (`CLOUD_ARMOR_EDGE`) | Backend service hoặc backend bucket của frontend được hỗ trợ | Lọc request trước Cloud CDN cache, bảo vệ cả cache hit | Dùng với global external hoặc classic Application Load Balancer; tập thuộc tính hạn chế hơn backend policy |
| **Regional backend security policy** | Regional backend service | Ứng dụng dùng regional external hoặc regional internal Application Load Balancer | Tạo/gắn theo region; không giả định mọi tính năng global đều tương đồng |
| **Network edge security policy** (`CLOUD_ARMOR_NETWORK`) | Tài nguyên network-level được hỗ trợ | Bảo vệ network edge với passthrough Network Load Balancer, protocol forwarding hoặc VM external IP | Cơ chế và rule ở lớp mạng; không phải WAF HTTP theo cùng cách |

**Với bài học này**, trường hợp chính là **global external Application Load Balancer** và backend security policy; khi có Cloud CDN, kết hợp thêm edge security policy. Cloud Armor cũng hỗ trợ các loại load balancer khác, nhưng trước khi dùng phải đọc bảng khả năng theo loại frontend và security policy cụ thể.

### Một backend service có thể gắn policy nào?

- Backend service của global external Application Load Balancer có thể dùng **backend policy**, **edge policy** hoặc cả hai theo tính năng hỗ trợ.
- Backend service được nhiều URL map/backend khác tham chiếu thì các request được đưa đến service đó có thể chịu tác động của policy gắn với service.
- **Backend bucket** (ví dụ Cloud Storage được cung cấp qua load balancer/Cloud CDN) chỉ hỗ trợ **edge security policy**, không gắn backend security policy thông thường.
- Một backend service chỉ có **một policy của mỗi loại** gắn trực tiếp theo mô hình service-level; muốn nhiều quy tắc thì thêm rule trong policy hoặc xem mô hình hierarchical policy được hỗ trợ.
- Với **GKE Ingress**, cấu hình của controller có thể ghi đè việc chỉnh backend service thủ công. Dùng cấu hình khai báo tương ứng, chẳng hạn `BackendConfig` khi sử dụng GKE Ingress, để tránh drift.

**Không đồng nhất mọi Cloud Armor policy với WAF:** network edge policy và edge policy không có toàn bộ ngôn ngữ kiểm tra nội dung HTTP/WAF như backend policy.

## 3. Cloud Armor và Cloud CDN: cache hit được bảo vệ ở đâu?

Khi một backend service bật Cloud CDN, nội dung tĩnh có thể được phục vụ từ cache của Google. **Backend security policy** áp cho những request được định tuyến tới backend sau cache lookup, chẳng hạn cache miss hoặc request không dùng cache. Để kiểm soát cả request được phục vụ từ cache, dùng **edge security policy** với frontend hỗ trợ.

~~~mermaid
flowchart TD
    A["Client HTTP(S)"] --> B["Global / Classic Application LB"]
    B --> C{"Edge security policy"}
    C -- "Deny" --> X["Từ chối tại biên"]
    C -- "Allow" --> D{"Cloud CDN cache"}
    D -- "Hit" --> E["Trả nội dung đã cache"]
    D -- "Miss hoặc bypass" --> F{"Backend security policy"}
    F -- "Deny" --> X
    F -- "Allow" --> G["Backend service / origin"]
    G --> H["Phản hồi / cache nếu đủ điều kiện"]
~~~

Điều cần nhớ:

1. **Edge policy lọc trước cache** nên có thể chặn request kể cả khi nội dung đã được cache.
2. **Backend policy bảo vệ đường về origin**; với Cloud CDN, không giả định backend policy xem mọi cache hit.
3. **Backend bucket chỉ gắn edge policy**. Nếu cần WAF logic phức tạp cho ứng dụng động, thiết kế backend service và policy phù hợp.
4. **Cache không phải biện pháp bảo vệ dữ liệu nhạy cảm.** Đánh giá kỹ `Cache-Control`, cookie, authorization và khả năng dữ liệu người dùng bị chia sẻ giữa các client.

Ví dụ website có `/assets/app.js` được Cloud CDN cache, còn `/api/orders` là dữ liệu động. Có thể đặt kiểm soát IP cơ bản cho tất cả request ở edge policy, WAF và rate limiting chi tiết tại backend service ứng dụng. Nhưng nếu URL map định tuyến `/api/orders` tới backend khác, cần gắn policy **cho đúng backend service của API**.

## 4. Cấu trúc của một security policy

Một security policy gồm các **rule**. Mỗi rule có:

- **Priority:** số nguyên, số **càng nhỏ** thì được xét **càng sớm**.
- **Match:** điều kiện như IP/CIDR, region, path, header hoặc biểu thức WAF, tùy policy.
- **Action:** `allow`, `deny-403`, `deny-404`, `deny-502`, `throttle`, `rate-based-ban` hoặc hành động khác được hỗ trợ.
- **Preview:** ghi nhận tác động của rule nhưng chưa thực thi hành động chặn của rule đó.
- **Description:** mục đích và căn cứ vận hành để review.

Các rule thông thường có priority từ `0` đến `2147483646`, không trùng nhau. Policy có **default rule** ở `2147483647`, được xét khi không rule nào ở trước quyết định xử lý request. Default rule có thể là `allow` hoặc `deny` theo thiết kế.

### Ví dụ thứ tự xử lý

| Priority | Điều kiện | Action | Mục đích |
|---:|---|---|---|
| 100 | IP trong danh sách chặn đã xác minh | `deny-403` | Chặn nguồn lạm dụng |
| 500 | Rule WAF SQL injection được chọn | `deny-403` (ban đầu Preview) | Phát hiện payload nghi ngờ |
| 900 | Request tới `/login` vượt ngưỡng theo IP | `throttle` | Giảm tốc độ truy cập |
| 2000 | IP trong dải mạng công ty, nếu muốn ưu tiên riêng | `allow` | Cho phép theo yêu cầu nghiệp vụ |
| 2147483647 | Mọi traffic chưa match | `allow` hoặc `deny` | Hành vi mặc định |

**Lưu ý:** một rule `allow` có priority nhỏ sẽ kết thúc đánh giá sớm, có thể bỏ qua các rule WAF/deny ở priority lớn hơn. Vì vậy không nên đặt “allowlist” rộng ở phía trước tất cả kiểm soát khác mà chưa đánh giá hậu quả. Khi rule WAF ở **Preview**, hệ thống tiếp tục xét các rule khác để có kết quả enforced thực tế.

Chọn chiến lược:

**Default allow** phù hợp website công cộng có tập traffic hợp lệ rộng: chặn dấu hiệu xấu, throttling, theo dõi false positive. **Default deny** phù hợp ứng dụng chỉ mở cho tập nguồn xác định (ví dụ một hệ thống dành cho đối tác), cần đặt allowlist chính xác ở priority cao hơn default deny. Đừng dùng default deny cho API công khai khi chưa kiểm thử phạm vi client thật.

## 5. WAF: phát hiện request có dấu hiệu tấn công

**Web Application Firewall (WAF)** của Cloud Armor hỗ trợ **preconfigured WAF rules** dựa trên các bộ chữ ký phổ biến cho nhóm rủi ro ứng dụng web (ví dụ SQL injection, cross-site scripting). Từ góc nhìn triển khai, một rule có thể dùng biểu thức:

~~~text
evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})
~~~

Ví dụ này chọn một nhóm chữ ký SQL injection và mức nhạy cảm tương ứng. Tên bộ chữ ký, phiên bản và mức nhạy cảm phải đối chiếu tài liệu hiện hành trước khi áp dụng cho production. Một ứng dụng dùng tham số chứa ký tự đặc biệt hoặc JSON phức tạp có thể bị phát hiện nhầm là tấn công.

Ngoài WAF sẵn có, **custom rule** có thể viết biểu thức dựa trên các thuộc tính được hỗ trợ:

~~~text
# Minh họa điều kiện CEL của Cloud Armor:
request.path.startsWith('/admin')

origin.region_code == 'VN'

inIpRange(origin.ip, '203.0.113.0/24')

request.path.startsWith('/login') &&
request.method == 'POST'
~~~

Mỗi biểu thức là **ví dụ độc lập**, không phải một policy đầy đủ. IP trong ví dụ thuộc dải tài liệu; mã vùng `VN` chỉ dùng để minh họa. **Chặn theo vị trí địa lý** có thể ảnh hưởng VPN, khách hàng đi công tác hoặc trình duyệt dùng proxy; không phải công cụ xác thực danh tính.

### Tuning WAF đúng cách

1. Bật rule mới trong **Preview**, duy trì logging phù hợp.
2. Chạy các request hợp lệ từ trình duyệt, mobile app, webhook, khách hàng nội bộ; nếu có môi trường kiểm thử thì chạy cả tình huống có payload mẫu được kiểm soát.
3. Xem match rule/subsignature, URL, request path, client và tỷ lệ false positive.
4. Tinh chỉnh mức sensitivity, ngoại lệ chữ ký cụ thể (`opt-out`) hoặc điều kiện match được phê duyệt.
5. Khi kết quả đáp ứng yêu cầu, tắt Preview để enforce theo kế hoạch, tiếp tục giám sát.

Cloud Armor **không đọc toàn bộ request body ở mọi tình huống**. WAF có giới hạn kích thước inspection (có thể cấu hình trong dải được hỗ trợ, ví dụ 8–64 KiB tùy cơ chế) và cách giải mã theo content type; phần body bên ngoài giới hạn có thể không được kiểm tra. Với WebSocket, Cloud Armor có thể đánh giá HTTP request mở kết nối nhưng không tự xét mọi message sau đó.

WAF giúp giảm rủi ro, **không thay thế** validation, parameterized query, encoding output, authentication, authorization, patching và rate limit trong ứng dụng.

## 6. Rate limiting: giảm request flood và lạm dụng API

Cloud Armor hỗ trợ các hành động giới hạn tần suất:

| Cơ chế | Cách hoạt động | Khi dùng |
|---|---|---|
| **Throttle** | Nếu số request vượt ngưỡng trong cửa sổ thời gian, xử lý request vượt ngưỡng theo `exceed-action` | Endpoint login, public API, traffic burst |
| **Rate-based ban** | Có thể tạm cấm client trong thời gian xác định sau khi đạt ngưỡng/bản quy tắc | Nguồn liên tục vượt ngưỡng hoặc tấn công kéo dài |

Ngưỡng được xác định theo **key**, chẳng hạn IP client, HTTP header/cookie hoặc thuộc tính khác theo tính năng hỗ trợ. Rate limiting trong Cloud Armor được thực thi theo backend service được gắn policy; dùng cùng policy cho hai backend **không đồng nghĩa** chúng chia sẻ một bộ đếm chung cho cả hai dịch vụ.

### Ví dụ thiết kế cho `/login`

Ứng dụng public có endpoint đăng nhập dễ bị thử mật khẩu hàng loạt. Nhóm vận hành đặt ngưỡng thử nghiệm **100 request mỗi 60 giây trên một IP**; vượt ngưỡng trả HTTP 429.

Đây là **ngưỡng minh họa**, không phải khuyến nghị chung cho mọi ứng dụng. Người dùng cùng mạng NAT, trường học hoặc doanh nghiệp có thể dùng chung IP và bị ảnh hưởng; ngược lại bot phân tán trên nhiều IP có thể né được giới hạn theo IP. Cần đo traffic hợp lệ, phân phối IP, tần suất đăng nhập và mức độ false positive trước khi enforce.

Cloud Armor giảm áp lực từ request ở biên. Ứng dụng vẫn cần quy trình khóa/tạm hoãn theo tài khoản, bảo vệ session, chống credential stuffing, giám sát gian lận và giới hạn quota nghiệp vụ, bởi biện pháp theo IP đơn thuần không đủ.

## 7. Điều kiện để triển khai policy lên load balancer

Trong bài thực hành, giả sử đã tồn tại:

- Một **global external Application Load Balancer** hoạt động và có frontend HTTPS.
- URL map đã định tuyến `api.example.com` đến **backend service** tên `api-backend`.
- Backend service đang phục vụ Cloud Run qua serverless NEG hoặc VM/GKE qua loại backend được hỗ trợ.
- Project được bật Compute Engine API, billing đang hoạt động và người thao tác có quyền tương ứng.
- Có access log mẫu và nhóm chịu trách nhiệm khôi phục nếu rule ảnh hưởng traffic hợp lệ.

**Không cần tạo thêm một load balancer chỉ để có Cloud Armor** nếu kiến trúc hiện tại dùng frontend/backend được hỗ trợ. Ngược lại, không thể chỉ tạo Cloud Armor policy rồi mong nó tự bảo vệ một Cloud Run URL trực tiếp: phải định tuyến qua load balancer và khóa đường bypass.

### Quyền IAM cần thiết

Quyền quản lý security policy và quyền gắn policy vào backend service là hai thao tác khác nhau:

| Nhiệm vụ | Permission/vai trò tham khảo |
|---|---|
| Tạo/sửa/xóa policy và rule | `roles/compute.securityAdmin` hoặc custom role có `compute.securityPolicies.*` phù hợp |
| Gắn policy vào backend service | Quyền sử dụng policy và cập nhật backend service, thường trong `roles/compute.networkAdmin` tùy phạm vi |
| Xem load balancer logs | Quyền đọc Cloud Logging/Monitoring phù hợp |
| Thay cấu hình backend, URL map hoặc frontend | Vai trò quản trị load balancing tương ứng, tách khỏi quyền sửa WAF khi có thể |

Thiết kế IAM theo Google Group và service account CI/CD riêng. Cần chú ý IAM kế thừa từ Organization/Folder, vì việc gỡ một binding local ở project có thể chưa thu hồi quyền hiệu lực nếu có binding rộng ở cấp cha.

## 8. Tạo backend security policy và rule bằng gcloud

Các lệnh dưới đây chỉ là **ví dụ để học**, sử dụng tên giả định; thực thi trên project thật có thể tạo chi phí hoặc ảnh hưởng traffic production. Chỉ áp dụng khi đã kiểm tra project, backend service, phạm vi tác động và quyền IAM.

~~~bash
PROJECT_ID="demo-security-project"
POLICY="api-armor-policy"
BACKEND="api-backend"

gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com

# 1. Tạo backend security policy toàn cục.
gcloud compute security-policies create "$POLICY" \
  --type=CLOUD_ARMOR \
  --description="Protect API backend"

# 2. Ví dụ chặn dải IP minh họa, ban đầu chạy Preview.
gcloud compute security-policies rules create 100 \
  --security-policy="$POLICY" \
  --src-ip-ranges="203.0.113.0/24" \
  --action=deny-403 \
  --description="Example denylist in preview" \
  --preview

# 3. Thêm WAF SQL injection với sensitivity ban đầu.
gcloud compute security-policies rules create 500 \
  --security-policy="$POLICY" \
  --expression="evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})" \
  --action=deny-403 \
  --description="SQLi detection in preview" \
  --preview

# 4. Gắn policy vào đúng global backend service.
gcloud compute backend-services update "$BACKEND" \
  --global \
  --security-policy="$POLICY"

# 5. Đọc lại cấu hình.
gcloud compute security-policies describe "$POLICY"
gcloud compute security-policies rules list --security-policy="$POLICY"
gcloud compute backend-services describe "$BACKEND" --global
~~~

Lệnh `rules create` sẽ lỗi nếu đã có rule tại priority đó. Trước khi sửa production, kiểm tra policy và backend service nào đang được sử dụng; có thể trên backend đã gắn một policy khác cần được giữ và điều chỉnh, thay vì thay bằng policy mới.

**Preview chỉ áp dụng cho các rule được đặt Preview.** Chính sách và các rule khác đang enforced vẫn hoạt động; default rule và các deny rule khác có thể tiếp tục chặn request. Vì vậy nên đọc toàn bộ policy và log, không suy luận rằng “bật Preview” cho một rule nghĩa là hệ thống không chặn traffic nào.

### Thêm throttle cho API

Một ví dụ độc lập: áp ngưỡng minh họa cho request `/login` của backend service:

~~~bash
gcloud compute security-policies rules create 900 \
  --security-policy="$POLICY" \
  --expression="request.path.startsWith('/login')" \
  --action=throttle \
  --rate-limit-threshold-count=100 \
  --rate-limit-threshold-interval-sec=60 \
  --conform-action=allow \
  --exceed-action=deny-429 \
  --enforce-on-key=IP \
  --description="Preview login rate limit" \
  --preview
~~~

Thứ tự priority ảnh hưởng trực tiếp: nếu request đã bị rule priority 100 chặn, nó sẽ không đến rule 900. Nếu một allow rule ở 200 đã match và quyết định xử lý, rule throttle ở 900 có thể không được áp dụng cho request đó. Để kiểm tra tác động, hãy theo dõi quyết định enforced và preview trong log.

### Tắt Preview sau khi đã đánh giá

~~~bash
# Chỉ áp dụng sau khi đã xác minh tác động và có kế hoạch rollback.
gcloud compute security-policies rules update 500 \
  --security-policy="$POLICY" \
  --no-preview
~~~

Khi enforce, Cloud Armor có thể trả `403` cho request match WAF. Hãy kiểm tra traffic thực tế và log sau thay đổi. Nếu false positive ảnh hưởng người dùng, có thể chuyển rule về Preview hoặc điều chỉnh rule/ngoại lệ đã được review; đừng vội xóa toàn bộ policy.

## 9. Thêm edge security policy khi có Cloud CDN

Giả sử website có CDN và backend service tên `static-backend`. Để lọc trước cache, tạo **edge security policy** riêng:

~~~bash
EDGE_POLICY="public-edge-policy"
STATIC_BACKEND="static-backend"

gcloud compute security-policies create "$EDGE_POLICY" \
  --type=CLOUD_ARMOR_EDGE \
  --description="Basic filtering before CDN cache"

# Rule minh họa, chưa enforce.
gcloud compute security-policies rules create 100 \
  --security-policy="$EDGE_POLICY" \
  --src-ip-ranges="198.51.100.0/24" \
  --action=deny-403 \
  --preview

# Áp edge policy lên backend service của global load balancer.
gcloud compute backend-services update "$STATIC_BACKEND" \
  --global \
  --edge-security-policy="$EDGE_POLICY"
~~~

Với **backend bucket** lưu nội dung Cloud Storage, cần thao tác gắn edge policy trên backend bucket qua Console/API hoặc lệnh backend-buckets tương ứng, **không dùng lệnh backend-services cho backend bucket**. Edge policy chỉ cung cấp tập tính năng được hỗ trợ của loại policy đó; không chuyển nguyên mọi rule WAF/rate limit từ backend policy sang edge policy một cách máy móc.

Nếu cùng backend service có cả edge và backend policy:

1. Request bị **edge policy từ chối** thì không được phục vụ từ cache hoặc origin.
2. Request vượt qua edge policy và **cache hit** thì nội dung có thể được trả ngay, không đi đến backend policy.
3. Request **cache miss/bypass** được đánh giá bởi backend policy trước khi tới origin.

Trong hệ thống có nội dung riêng theo người dùng, kiểm tra cấu hình cache và authentication độc lập. Cloud Armor không tự bảo đảm rằng một phản hồi cá nhân hóa bị cache sai sẽ được giấu khỏi người dùng khác.

## 10. Đảm bảo backend không thể bỏ qua Cloud Armor

Cloud Armor bảo vệ traffic **đi qua load balancer và backend có policy**. Nếu client có một URL hoặc địa chỉ khác đi thẳng tới backend, lớp bảo vệ đó có thể bị bỏ qua.

### Compute Engine và GKE

Với backend VM, cấu hình **VPC firewall** để chỉ các dải nguồn được Google quy định cho proxies và health checks phù hợp có thể đến cổng ứng dụng. Nếu VM còn có external IP với cổng ứng dụng mở tự do, attacker có thể đi thẳng vào VM không qua frontend có Cloud Armor.

Đối với GKE, lưu ý Ingress controller và các tài nguyên Network Endpoint Group, firewall, BackendConfig. Nếu workload có thêm ingress/Service `LoadBalancer` hoặc endpoint công khai khác, rà soát để bảo đảm tất cả đường vào ứng dụng đều đi qua lớp kiểm soát đã thiết kế.

### Cloud Run và serverless NEG

Cloud Run thường có URL dạng `*.run.app`. Khi dùng external Application Load Balancer với serverless NEG, người dùng có thể bypass policy nếu URL trực tiếp vẫn cho phép truy cập công cộng.

Đối với dịch vụ chỉ mong muốn traffic từ internet qua external Application Load Balancer, cân nhắc đặt ingress là:

~~~bash
# Minh họa thiết lập cho Cloud Run có external Application LB hợp lệ.
gcloud run services update orders-api \
  --region="asia-southeast1" \
  --ingress=internal-and-cloud-load-balancing
~~~

Tùy kiến trúc, một số request nội bộ được định nghĩa là internal vẫn có thể truy cập theo cơ chế Cloud Run. Do đó, kiểm tra quyền `roles/run.invoker`, cấu hình ingress, đường gọi nội bộ và các endpoint phụ. **Kiểm soát đường truy cập** và **xác thực/ủy quyền ứng dụng** là những lớp bổ sung cho WAF.

### Identity-Aware Proxy và ứng dụng private

IAP kiểm tra **danh tính người dùng**, trong khi Cloud Armor xét **thuộc tính của request/traffic**. Với global external Application Load Balancer, Cloud Armor được đánh giá trước IAP theo quy trình hỗ trợ; với classic Application Load Balancer có thể khác. Khi thiết kế, cần kiểm tra thứ tự cụ thể để giải thích 403, redirect đăng nhập và log request.

Cloud Armor không thay thế IAM, IAP, OAuth, session và phân quyền nghiệp vụ. Ví dụ request là HTTP hợp lệ và qua được WAF nhưng người gửi không có quyền xem đơn hàng: ứng dụng vẫn phải trả 401/403 đúng logic nghiệp vụ.

## 11. Dùng Terraform để quản lý policy cùng hạ tầng

Khi có nhiều môi trường dev, staging, production, hãy lưu policy dưới dạng Infrastructure as Code để review, kiểm tra và rollback có bằng chứng. Ví dụ Terraform tối giản chỉ khai báo **một backend security policy**:

~~~hcl
resource "google_compute_security_policy" "api" {
  name        = "api-armor-policy"
  description = "Protect the public API backend"
  type        = "CLOUD_ARMOR"

  rule {
    priority    = 500
    action      = "deny(403)"
    description = "SQLi signatures, preview first"
    preview     = true

    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    priority    = 2147483647
    action      = "allow"
    description = "Default allow"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}
~~~

Đoạn này cần provider, project và quy trình CI/CD thực tế; việc **gắn vào backend service** phải được khai báo ở tài nguyên backend service tương ứng (`security_policy` hoặc cơ chế hỗ trợ). Không kết luận một policy đang bảo vệ ứng dụng chỉ vì Terraform đã tạo ra resource policy.

Một quy trình release rule hữu ích:

~~~text
Threat / incident / change request
    ↓
Pull request sửa policy hoặc rule
    ↓
Linter + review biểu thức, priority, expected impact
    ↓
Terraform plan (kiểm tra policy + attachment)
    ↓
Apply ở dev/staging hoặc Preview trên production
    ↓
Phân tích logs / false positive / khách hàng bị ảnh hưởng
    ↓
Phê duyệt enforce và tiếp tục giám sát
~~~

**Quản lý drift:** nếu policy của GKE Ingress do `BackendConfig` điều khiển, chỉnh trực tiếp backend service bằng Terraform hoặc `gcloud` có thể bị controller ghi đè. Xác định rõ “nguồn sự thật” của attachment trước khi thay đổi; tránh để Terraform, Ingress controller và thao tác Console cùng tranh quyền quản lý một thuộc tính.

## 12. Quan sát quyết định của Cloud Armor

Một policy tốt cần bằng chứng cho thấy nó đang **được áp dụng vào đúng request**. Cloud Armor dùng hạ tầng logging của load balancer cho per-request logging. Với nhiều backend service, **request logging có thể chưa bật theo mặc định**; cần bật logging ở backend service tương ứng và chọn sampling rate phù hợp.

### Bật logging cho backend service

~~~bash
gcloud compute backend-services update "$BACKEND" \
  --global \
  --enable-logging \
  --logging-sample-rate=1.0
~~~

Ví dụ dùng sample rate 1.0 để phân tích quá trình cấu hình. Khi traffic lớn, cân nhắc chi phí/khả năng lưu log và điều chỉnh có chủ đích. Một số định dạng log, trường dữ liệu và phạm vi hỗ trợ khác nhau giữa các loại load balancer.

### Tìm request bị chặn trong Logs Explorer

~~~text
resource.type="http_load_balancer"
jsonPayload.enforcedSecurityPolicy.outcome="DENY"
~~~

Hoặc thử lọc theo:

~~~text
resource.type="http_load_balancer"
jsonPayload.statusDetails="denied_by_security_policy"
~~~

Đây là các bộ lọc ví dụ. Kết quả còn phụ thuộc loại LB, sampling, thời gian, dự án chứa frontend và cấu trúc log. Nếu frontend/backend được tham chiếu xuyên project, log có thể nằm ở **project chứa frontend/URL map**; đội backend cần quyền xem log phù hợp.

Các trường hữu ích trong request log:

- `enforcedSecurityPolicy`: policy và rule thực sự chi phối kết quả khi có dữ liệu.
- `previewSecurityPolicy`: rule Preview match nhưng không tự chặn request.
- Priority, action, outcome và statusDetails: giúp giải thích vì sao request bị deny.
- Client IP/region, URI path, response code, latency: giúp so sánh với traffic hợp lệ.

**Cloud Logging không phải tự động ghi lại mọi request** nếu sampling thấp, backend chưa bật logging hoặc request không đi qua đường bảo vệ. Preview cũng phát sinh xử lý/phí theo chính sách giá dịch vụ, nên không nên để vô thời hạn nếu không còn mục tiêu quan sát.

### Metric và cảnh báo

Đề xuất theo dõi:

| Chỉ số | Điều cần tìm |
|---|---|
| Tỷ lệ request bị deny/throttle theo policy/rule | Rule có đang chặn quá nhiều người dùng hợp lệ? |
| HTTP 403 và 429 theo endpoint | Gia tăng do tấn công, thay rule hay client bất thường? |
| HTTP 5xx ở backend / error rate | Tấn công có lọt tới backend và ảnh hưởng availability? |
| Request count theo IP, region, URL | Spike traffic hoặc bot lặp lại |
| Latency và backend utilization | Load balancer/Cloud Run/GKE có bị quá tải không? |
| Preview matches theo rule mới | Rule chuẩn bị enforce sẽ ảnh hưởng bao nhiêu request? |
| Chi phí load balancing, Armor, logging | Traffic tấn công có làm tăng ngân sách không? |

Khi cần phân tích false positive của WAF, có thể bật **verbose logging** tạm thời để nhận thông tin chi tiết hơn về chữ ký, nhưng cần xét rủi ro chứa dữ liệu request và chi phí. Giới hạn người được quyền đọc log; tắt verbose sau khi điều chỉnh xong.

## 13. Quy trình phát hành và rollback rule an toàn

Lỗi thường gặp nhất của người mới là bật WAF ở chế độ chặn toàn bộ mà không đo traffic hợp lệ, dẫn tới nhiều request API chính đáng nhận 403.

Một quy trình từng bước:

1. **Xác định mục tiêu:** muốn chặn CIDR cụ thể, giảm HTTP flood, bảo vệ `/login` hay phát hiện chữ ký SQLi/XSS?
2. **Chọn đúng backend service:** từ frontend/URL map xác định route thực sự nhận traffic; kiểm tra service đang có policy khác không.
3. **Chọn match và priority:** đánh giá giao nhau giữa allowlist, WAF, rate limiting, default rule.
4. **Bật Preview:** giữ nguyên trải nghiệm người dùng trong giai đoạn quan sát tác động của rule mới.
5. **Thu log đủ đại diện:** kiểm tra cả mobile app, webhook, API client, khách hàng qua NAT/proxy, đối tác và traffic cao điểm.
6. **Giảm false positive:** sửa biểu thức, tuning WAF/sensitivity hoặc thay ngưỡng rate limit.
7. **Enforce có kiểm soát:** thông báo lịch, người chịu trách nhiệm, tiêu chí rollback và dashboards; bắt đầu với phạm vi nhỏ nếu công cụ cho phép.
8. **Quan sát sau release:** so sánh HTTP 403/429, 5xx, business metrics, latency và complaint.
9. **Rollback:** trả rule về Preview hoặc cấu hình đã xác minh trước đó, rồi phân tích nguyên nhân. Không xoá cả lớp bảo vệ nếu chỉ một rule gây lỗi.

Khi lượng request bất thường tăng rất nhanh, người vận hành có thể cần rule khẩn cấp. Vẫn cần ghi lại ai sửa, mục đích, thời hạn và kiểm tra sau sự cố để tránh một CIDR bị chặn vĩnh viễn dù nó phục vụ người dùng hợp lệ.

## 14. Giới hạn và các lớp bảo vệ bổ sung

| Vấn đề | Cloud Armor giúp gì? | Cần thêm gì? |
|---|---|---|
| L7 HTTP flood qua load balancer | Throttle, rate-based ban, WAF hoặc cơ chế bảo vệ DDoS phù hợp | Autoscaling, timeout, circuit breaker, load test |
| SQL injection / XSS payload | WAF rule signatures, custom CEL | Parameterized query, input/output validation, security testing |
| Credential stuffing | Giới hạn tần suất, bot defense tùy gói | MFA, account-level rate limit, phát hiện hành vi, xác thực mạnh |
| Backend bị gọi trực tiếp | Không bảo vệ request bypass LB | VM firewall, Cloud Run ingress, hạn chế endpoint phụ |
| Lộ dữ liệu do phân quyền API sai | Không đủ, request có thể hợp lệ về HTTP | IAM, IAP, OAuth, business authorization |
| Dữ liệu cá nhân bị cache không đúng | Không tự ngăn cache cấu hình sai | Cache-Control, authorization-aware caching, kiểm thử CDN |
| Tấn công qua kết nối WebSocket đã mở | Có thể kiểm soát HTTP upgrade ban đầu | Xác thực và validate từng message trong ứng dụng |
| Backend/network outage | Không sửa lỗi cơ sở hạ tầng | Multi-zone/region, health checks, failover, SLO và runbooks |

Cloud Armor phù hợp với **defense in depth**: một lớp bảo vệ ở đường request được load balancer kiểm soát, phối hợp với hệ thống xác thực, mạng, bảo mật ứng dụng và vận hành backend.

## 15. Chi phí và lựa chọn mô hình dịch vụ

Chi phí phải xem cùng toàn bộ đường đi: frontend/forwarding rule, load balancing data processing, Cloud CDN/cache egress nếu bật, Cloud Armor policies/rules/requests, Cloud Logging và backend compute. Cloud Armor có các gói **Standard** và **Enterprise**; mức phí và tính năng phụ thuộc hình thức sử dụng, loại policy, subscription tier và khối lượng traffic. Có thể phát sinh phí cho rule chạy Preview.

Trước khi triển khai:

- Xác nhận tính năng và loại endpoint đang được hỗ trợ trong gói dịch vụ dùng thật.
- Đọc **Cloud Armor pricing** và **Load Balancing pricing** tại region/network tier liên quan, không tự áp một đơn giá cho mọi backend.
- Dự tính số backend service, số policy/rule, số request trong giờ bình thường và lúc bị tấn công.
- Theo dõi phí Cloud Logging khi bật sample rate cao và verbose logging.
- Đặt Cloud Billing budget/alerts và theo dõi chi phí theo project, nhưng nhớ **budget alert không tự ngắt traffic hoặc loại bỏ phí**.

Giảm request xấu trước backend có thể tiết kiệm CPU và autoscaling, nhưng điều đó không đồng nghĩa Cloud Armor luôn giảm tổng hóa đơn: chi phí policy, phân tích request và logging vẫn cần đưa vào dự toán.

## 16. Tình huống thực tế: website thương mại điện tử và API Java

Giả sử doanh nghiệp dùng:

~~~text
Cloud DNS: shop.example.com → global external Application LB
  |
  +-- /assets/* → static-backend (Cloud CDN cache)
  |                  └── Cloud Armor EDGE policy
  |
  +-- /api/* → api-backend → Cloud Run (Java)
  |             └── Cloud Armor BACKEND policy
  |
  +-- /admin/* → admin-backend → GKE
                └── Backend policy + IAP / ứng dụng xác thực
~~~

**Thiết kế đề xuất:**

| Thành phần | Quy tắc / giải pháp | Mục tiêu |
|---|---|---|
| `static-backend` | Edge policy lọc nguồn lạm dụng, Cloud CDN cache | Bảo vệ cả cache hit và giảm tải origin |
| `api-backend` | WAF SQLi/XSS Preview rồi enforce; throttle `/login` | Bảo vệ API và tránh flood |
| `admin-backend` | Rule IP phù hợp, IAP hoặc auth nghiêm ngặt | Giảm bề mặt truy cập admin |
| Cloud Run origin | Ingress `internal-and-cloud-load-balancing` nếu phù hợp | Hạn chế gọi trực tiếp `run.app` từ Internet |
| GKE origin | Ingress controller/`BackendConfig` + firewall và IAM đúng | Tránh bypass và cấu hình bị ghi đè |
| Platform SRE | Cloud Logging/Monitoring, alert và runbook | Phát hiện sự cố và rollback |
| CI/CD bảo mật | Terraform + review + quyền IAM giới hạn | Quản trị thay đổi có thể kiểm toán |

**Bài toán xảy ra:** một đợt traffic tới `/api/login` tăng gấp nhiều lần, một số IP vượt ngưỡng, đồng thời có request chứa mẫu SQLi. Nhóm quan sát log Preview, điều chỉnh ngưỡng theo client thật, sau đó enforce WAF và throttle. Nếu backend vẫn tăng latency, nhóm tiếp tục xem autoscaling Cloud Run và database connection pool; việc Cloud Armor chặn một phần traffic không tự xử lý nghẽn tài nguyên bên trong.

Khi khách hàng hợp lệ bị chặn do cùng NAT IP với một nhóm tạo traffic lớn, nhóm cân nhắc sửa key/threshold theo khả năng dịch vụ, nới rule có điều kiện hoặc cơ chế xác thực bổ sung. Không mặc định “tăng ngưỡng toàn cầu” là cách tốt nhất; cần hiểu nhóm client bị ảnh hưởng và rủi ro tấn công.

## 17. Checklist trước khi đưa Cloud Armor vào production

- [ ] Xác định rõ loại load balancer, backend service/backend bucket và các endpoint cần bảo vệ.
- [ ] Chọn đúng backend, edge hoặc network edge policy và xác nhận tính năng hỗ trợ.
- [ ] Kiểm tra URL map có nhiều backend nào chưa được gắn policy.
- [ ] Kiểm tra priority thấp được xét trước; default rule có hành vi mong muốn.
- [ ] Triển khai rule mới ở Preview và thu thập log đủ đại diện.
- [ ] Tuning WAF, rate-limit threshold và allowlist để giảm false positive.
- [ ] Với Cloud CDN, xác định policy nào áp trước cache và policy nào chỉ áp cache miss.
- [ ] Đóng mọi đường truy cập trực tiếp tới backend có thể bỏ qua Cloud Armor.
- [ ] Nếu dùng GKE Ingress, cập nhật đúng nguồn cấu hình của controller.
- [ ] Bật load balancer request logging và cấu hình sample rate phù hợp.
- [ ] Dashboard có 403/429, denied requests, 5xx, latency và backend metrics.
- [ ] Có người chịu trách nhiệm security rule, quy trình review/rollback và dấu vết thay đổi.
- [ ] Đã kiểm tra chi phí Armor, LB, CDN và Logging; đặt budget/alert phù hợp.
- [ ] IAM của pipeline chỉ đủ quyền tạo/sửa/gắn policy theo phạm vi cần thiết.

**Bài tập vận dụng:** Một ứng dụng quản lý đặt hàng chạy trên Cloud Run, được public qua global external Application Load Balancer. Website tĩnh bật Cloud CDN; API động có hai route `/api/orders` và `/api/login`. Hãy:

1. Vẽ đường đi của request qua DNS, load balancer, edge policy, cache, backend policy, Cloud Run.
2. Thiết kế hai security policy cho nội dung CDN và API; chỉ rõ nơi gắn, priority và default rule.
3. Viết một rule WAF ở Preview và một throttle giới hạn `/api/login` theo IP; giải thích cách chọn threshold.
4. Nêu trường hợp cache hit không đi qua backend policy, nhưng vẫn phải qua edge policy.
5. Giải thích cách hạn chế client gọi trực tiếp URL `run.app` để bypass load balancer.
6. Viết lệnh xem policy, backend attachment và bộ lọc log để tìm request bị chặn.
7. Lập kế hoạch enforce/rollback khi có 403 tăng đột biến đối với khách hàng hợp lệ.
8. Đề xuất các metric quan sát độ tin cậy và nhóm chi phí phát sinh.

## Tài liệu tham khảo chính thức

- [Google Cloud Armor overview](https://cloud.google.com/armor/docs/cloud-armor-overview) — công dụng và nhóm endpoint.
- [Security policy overview](https://cloud.google.com/armor/docs/security-policy-overview) — loại policy, priorities và phạm vi bảo vệ.
- [Create and manage security policies](https://cloud.google.com/armor/docs/configure-security-policies) — quản lý policy/rule.
- [Manage Cloud Armor security policies](https://cloud.google.com/armor/docs/manage-security-policies) — gắn policy, Preview, export và rollback.
- [Set up preconfigured WAF rules](https://cloud.google.com/armor/docs/configure-waf) — chữ ký WAF, sensitivity và giới hạn body.
- [Configure rate limiting](https://cloud.google.com/armor/docs/configure-rate-limiting) — throttle và rate-based ban.
- [Integrate Cloud Armor with Cloud CDN, IAP, GKE and hybrid](https://cloud.google.com/armor/docs/integrating-cloud-armor) — thứ tự xử lý và đường ingress.
- [Per-request logging](https://cloud.google.com/armor/docs/request-logging) — điều kiện ghi log và bộ lọc.
- [Cloud Run ingress settings](https://cloud.google.com/run/docs/securing/ingress) — hạn chế truy cập trực tiếp vào service.
- [Google Cloud Armor pricing](https://cloud.google.com/armor/pricing) — gói Standard/Enterprise và cách tính phí.
