# Routing policies, virtual hostnames và session persistence

Trong chương **Cân bằng tải ứng dụng** của module **CLOUD_PROVIDERS_ORACLE**, bài học này kết hợp ba khả năng của OCI Load Balancer: phục vụ nhiều tên miền, định tuyến yêu cầu HTTP tới nhóm ứng dụng phù hợp và giữ các yêu cầu cùng phiên trên một backend.

Tình huống xuyên suốt là một cửa hàng có giao diện web, API và trang quản trị. Các thành phần dùng chung một load balancer nhưng có backend set và yêu cầu quản lý phiên khác nhau. Cấu hình cần đi cùng DNS, TLS, IAM, mạng VCN, health check và giám sát để vận hành ổn định, tự động hóa được và kiểm soát chi phí.

## 1. Mục tiêu và phạm vi

Sau bài học, người học có thể:

- Phân biệt vai trò của virtual hostname, routing policy và session persistence.
- Viết điều kiện định tuyến có ranh giới đường dẫn và thứ tự rõ ràng.
- Kết nối tên miền DNS, hostname resource và chứng thư của listener.
- Chọn giữa cookie do ứng dụng và cookie do load balancer quản lý.
- Kiểm tra phiên mới, phiên cũ, hostname không khớp và backend bị lỗi.
- Lập kế hoạch thay đổi cấu hình mà vẫn theo dõi được ảnh hưởng tới người dùng.

Bài áp dụng cho **OCI Load Balancer**, sử dụng mô hình HTTP/HTTPS và nhóm lệnh **oci lb**. Ví dụ không giả định các tính năng cookie này có thể áp dụng nguyên trạng cho OCI Network Load Balancer hoặc listener TCP.

Tên miền **shop.example.com** và **admin.example.com** là tên minh họa. Khi thực hành, dùng tên miền lab mà mình kiểm soát cùng cơ chế phân giải DNS và chứng thư phù hợp.

## 2. Ba quyết định trên đường đi của yêu cầu

| Khả năng | Quyết định chính | Ví dụ |
| --- | --- | --- |
| Virtual hostname | Listener nào phù hợp với hostname của yêu cầu? | shop.example.com tới shop_https |
| Routing policy | Backend set nào nhận yêu cầu HTTP? | /api/orders tới api_bs |
| Session persistence | Backend nào trong phạm vi phù hợp tiếp tục nhận phiên? | Phiên giỏ hàng quay lại shop-a |

Không dùng cookie để thay thế điều kiện chọn ứng dụng. Cũng không dùng tên miền quản trị như bằng chứng người gọi đã được cấp quyền quản trị.

~~~mermaid
flowchart TD
    Request["Yêu cầu HTTPS"] --> Host["Hostname và listener phù hợp"]
    Host --> Shop["shop_https"]
    Host --> Admin["admin_https"]
    Shop --> Rules["Routing policy shop_routes"]
    Rules -->|"Khớp /api hoặc /api/"| Api["Backend set api_bs"]
    Rules -->|"Không khớp"| Web["Default backend set shop_bs"]
    Admin --> AdminSet["Default backend set admin_bs"]
    Web --> Cookie["Kiểm tra phiên và backend đủ điều kiện"]
    Cookie --> A["shop-a"]
    Cookie --> B["shop-b"]
~~~

Sơ đồ là cách phân tích logic để thiết kế và chẩn đoán, không mô tả các tiến trình nội bộ của dịch vụ. Bằng chứng cuối cùng vẫn là yêu cầu tới đúng ứng dụng và được xử lý đúng.

## 3. Virtual hostnames: nhiều ứng dụng trên một địa chỉ

### DNS record, hostname resource và chứng thư

Ba đối tượng này giải quyết các việc khác nhau:

| Đối tượng | Trách nhiệm |
| --- | --- |
| Bản ghi DNS | Giúp client tìm địa chỉ load balancer từ tên miền |
| Virtual hostname resource | Khai báo tên hoặc mẫu hostname để liên kết với listener |
| Chứng thư TLS | Cho client kiểm chứng danh tính của dịch vụ HTTPS |

Tạo hostname resource trong Load Balancer không tự tạo bản ghi DNS. Nhiều tên miền có thể trỏ về cùng địa chỉ load balancer, nhưng mỗi tên vẫn cần cấu hình phân giải phù hợp. Virtual hostnames của OCI hỗ trợ listener HTTP và HTTPS. [Nguồn: Virtual Hostnames](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/hostname_management.htm).

Ví dụ ánh xạ:

~~~text
DNS:
  shop.example.com  → địa chỉ load balancer
  admin.example.com → cùng địa chỉ load balancer

Hostname resources:
  shop_host  = shop.example.com
  admin_host = admin.example.com

Listeners:
  shop_https  :443 → shop_host  → shop_bs, có shop_routes
  admin_https :443 → admin_host → admin_bs
~~~

Tên **shop_host** là tên tài nguyên cấu hình, còn **shop.example.com** là hostname mà client sử dụng. Khi gắn vào listener, chọn đúng tài nguyên đã tạo.

Với HTTPS, client thường gửi SNI trong bắt tay TLS rồi gửi hostname trong yêu cầu HTTP. Kiểm tra bằng đúng URL của ứng dụng để thử cả định danh TLS lẫn định tuyến. Chỉ thay HTTP Host trong một lệnh gọi trực tiếp IP không thay thế đầy đủ phép kiểm tra tên miền HTTPS.

### Exact match, wildcard và đường mặc định

OCI ưu tiên tên khớp chính xác, sau đó mẫu wildcard bắt đầu bằng dấu sao dài nhất, rồi mẫu kết thúc bằng dấu sao dài nhất. Virtual hostname không phải biểu thức chính quy. Khi không khớp tên, dịch vụ vẫn có cơ chế listener mặc định của cổng: listener không gắn hostname là mặc định; nếu tất cả đều gắn hostname, hostname được cấu hình đầu tiên trên cổng có vai trò mặc định. [Nguồn: Defining Hostnaming](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/hostname_management.htm).

Ví dụ, **shop.example.com** và ***.example.com** có thể cùng tồn tại để phục vụ nhu cầu khác nhau. Quy tắc wildcard của listener không tự cung cấp chứng thư wildcard và không thay đổi quy tắc kiểm chứng tên của client TLS.

Thiết kế một listener mặc định có chủ đích cho cổng đang dùng. Trong lab có thể cho listener đó dùng **reject_bs**, một backend set chỉ trả phản hồi không phục vụ hostname lạ. Backend của nhóm này vẫn cần endpoint health check riêng hoạt động bình thường, ví dụ /ready trả 200 trong khi yêu cầu ứng dụng trả 404.

Không giả định mọi hostname ngoài danh sách đều bị dịch vụ loại bỏ trước khi tới ứng dụng. Với HTTPS, tên lạ còn có thể bị client từ chối ở bước kiểm chứng chứng thư trước khi có phản hồi HTTP.

## 4. Routing policy: chọn backend set theo yêu cầu

### Cấu trúc và thứ tự

Routing policy là danh sách rule có thứ tự, gắn vào listener HTTP hoặc HTTPS. Mỗi rule có điều kiện và hành động chuyển tới backend set đã tồn tại. Dịch vụ dừng ở rule đầu tiên khớp; khi không rule nào khớp, yêu cầu tới default backend set của listener. [Nguồn: Routing Policies](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/routing-policy_management.htm).

Phân biệt hai loại policy:

- **Routing policy** chọn nhóm ứng dụng, chẳng hạn shop_bs hay api_bs.
- **Load balancing policy** của backend set chọn cách phân phối giữa các server trong nhóm.

Một rule chuyển tới api_bs không mô tả tỷ lệ chia tải giữa api-a và api-b. Nó cũng không tự tạo health check, thêm backend hoặc mở quyền mạng.

### Điều kiện có ranh giới rõ ràng

Cú pháp điều kiện có các toán tử như **eq**, **sw** và các tổ hợp **any(...)**, **all(...)**. So sánh chuỗi mặc định phân biệt hoa/thường; biểu thức **(i '...')** dùng khi chủ đích so sánh không phân biệt hoa/thường. [Nguồn: Routing Policy Language](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/routing_policy_conditions.htm).

Ví dụ cho nhóm API:

~~~text
any(
  http.request.url.path eq '/api',
  http.request.url.path sw '/api/'
)
~~~

Biểu thức này phân biệt ranh giới một đoạn đường dẫn:

| Path | Kết quả của điều kiện ví dụ |
| --- | --- |
| /api | Khớp |
| /api/ | Khớp |
| /api/orders | Khớp |
| /apiv2/orders | Không khớp |
| /API/orders | Không khớp với cấu hình phân biệt hoa/thường |
| /cart | Không khớp |

Nếu chỉ dùng tiền tố **/api**, chuỗi **/apiv2/orders** cũng có thể khớp. Hãy viết điều kiện theo hợp đồng URL, rồi kiểm tra cả những đầu vào gần giống.

Ví dụ một điều kiện kết hợp hostname với path:

~~~text
all(
  http.request.headers[(i 'host')] eq (i 'shop.example.com'),
  http.request.url.path sw '/api/'
)
~~~

Đây là mẫu cho yêu cầu có giá trị Host đúng như trong biểu thức. Nếu client có thể gửi hostname kèm cổng, cần bổ sung ca kiểm tra và điều kiện phù hợp. Với lab đã tách listener theo virtual hostname, rule /api không cần lặp lại điều kiện Host.

Path và query là các trường khác nhau: **/api/orders?status=open** vẫn có path **/api/orders**. Nếu cần định tuyến theo query hoặc header, mô tả rõ lý do nghiệp vụ và các giá trị được chấp nhận.

### Thứ tự quan trọng hơn mức độ cụ thể mà người đọc cảm nhận

Giả sử một hệ thống có hai rule:

~~~text
1. Path bắt đầu bằng /api/         → api_bs
2. Path bắt đầu bằng /api/reports/ → reports_bs
~~~

Yêu cầu **/api/reports/monthly** khớp rule đầu tiên nên rule thứ hai không được dùng. Muốn nhóm reports nhận đường dẫn đó, đặt rule tương ứng trước rule tổng quát.

Không giả định hệ thống tự chọn rule có path dài nhất như cách chọn một số mẫu virtual hostname. Đây là hai cơ chế lựa chọn khác nhau.

Routing condition dựa trên header, query hoặc cookie do client cung cấp cũng không xác thực người gọi. Ví dụ header **X-Environment: preview** chỉ nên làm tín hiệu chọn môi trường thử nghiệm khi toàn bộ quyền truy cập đã được thiết kế phù hợp.

### Cấu hình JSON minh họa

Policy chính trong lab có một rule, default backend set của listener là shop_bs:

~~~json
{
  "name": "shop_routes",
  "conditionLanguageVersion": "V1",
  "rules": [
    {
      "name": "route_api",
      "condition": "any(http.request.url.path eq '/api', http.request.url.path sw '/api/')",
      "actions": [
        {
          "name": "FORWARD_TO_BACKENDSET",
          "backendSetName": "api_bs"
        }
      ]
    }
  ]
}
~~~

Đây là mẫu biểu diễn policy, không phải toàn bộ yêu cầu tạo load balancer. Trong OCI CLI, **--rules** nhận danh sách rule bên trong trường rules; các tham số name và condition language version được truyền riêng. [Nguồn: OCI CLI routing-policy create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/routing-policy/create.html).

Hành động chuyển nhóm trong ví dụ không tự bỏ tiền tố **/api**. Backend phải xử lý được đường dẫn nhận vào; nếu cần rewrite, thiết kế và kiểm thử cơ chế đó riêng. Tương tự, rule routing không phải một phản hồi redirect cho trình duyệt.

## 5. Session persistence: giữ phiên trên một backend

### Khi nào cần và dữ liệu nào được giữ?

Một cửa hàng cũ có thể lưu giỏ hàng trong RAM của từng máy. Nếu yêu cầu sau tới máy khác, giỏ hàng có thể không còn. Session persistence giúp các yêu cầu trong một phiên quay lại backend phù hợp, nhưng không sao chép giỏ hàng sang máy khác.

Cần phân biệt:

| Khái niệm | Vai trò |
| --- | --- |
| Cookie xác thực hoặc phiên ứng dụng | Định danh phiên theo cơ chế ứng dụng |
| Cookie hoặc thông tin persistence của load balancer | Hỗ trợ chọn backend cho phiên |
| Kho lưu trạng thái phiên | Lưu giỏ hàng, dữ liệu đăng nhập hoặc trạng thái nghiệp vụ |

Một cookie routing tồn tại không chứng minh người dùng đã đăng nhập. Một phiên được chuyển tới backend còn khỏe cũng không chứng minh backend đó có toàn bộ dữ liệu phiên trước.

### Application cookie stickiness

Với chế độ này, cấu hình tên cookie mà ứng dụng phát hành. Ví dụ backend trả:

~~~http
Set-Cookie: APPSESSID=opaque-application-value; Path=/; Secure; HttpOnly
~~~

Persistence chỉ được kích hoạt khi phản hồi backend có Set-Cookie với tên đã cấu hình; nếu chưa có cookie phù hợp, yêu cầu vẫn theo chính sách phân phối thông thường. Có thể dùng dấu sao để khớp mọi cookie, nhưng chọn tên cụ thể giúp mục đích rõ ràng hơn. [Nguồn: Application Session Persistence Configuration](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/load_balancer/models/oci.load_balancer.models.SessionPersistenceConfigurationDetails.html).

Ví dụ cấu hình ở cấp backend set:

~~~json
{
  "cookieName": "APPSESSID",
  "disableFallback": false
}
~~~

Nếu ứng dụng Java thực tế dùng một tên khác như JSESSIONID, cấu hình theo cookie thực sự được gửi, không suy đoán từ tên framework. Cũng cần kiểm tra Path, Domain và chính sách client với cookie đó.

Thông tin routing do load balancer tạo phục vụ persistence cần được xem là dữ liệu opaque. Ứng dụng không nên phân tích nó để suy ra quyền hoặc danh tính người dùng.

### Load balancer cookie stickiness

Khi ứng dụng không phát hành cookie phù hợp hoặc muốn tách riêng cơ chế routing, load balancer có thể chèn cookie. Hai chế độ application cookie và load balancer cookie loại trừ nhau trong cùng backend set. [Nguồn: Load Balancer Cookie Configuration](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/load_balancer/models/oci.load_balancer.models.LBCookieSessionPersistenceConfigurationDetails.html).

Cấu hình minh họa cho shop_bs:

~~~json
{
  "cookieName": "X-Oracle-OCI-ShopRoute",
  "disableFallback": false,
  "path": "/",
  "maxAgeInSeconds": 1800,
  "isSecure": true,
  "isHttpOnly": true
}
~~~

Không đặt Domain trong ví dụ để cookie được giới hạn theo host đã nhận phản hồi. Max-Age 1800 giây là lựa chọn minh họa cho lab, không phải mặc định OCI hay khuyến nghị thời gian phiên cho mọi ứng dụng.

### Cookie scope và thuộc tính

| Thuộc tính | Tác động cần kiểm tra |
| --- | --- |
| Name | Tránh trùng tên cookie do ứng dụng tự phát hành |
| Domain | Xác định phạm vi host mà client gửi lại cookie |
| Path | Xác định phạm vi đường dẫn được gửi cookie |
| Max-Age | Thời gian giữ cookie; không đồng nghĩa thời gian dữ liệu phiên còn tồn tại ở server |
| Secure | Client chỉ gửi cookie qua giao thức bảo mật |
| HttpOnly | Hạn chế JavaScript truy cập cookie qua API phía client |

Không đặt Domain rộng tới example.com chỉ vì nhiều tên miền dùng cùng load balancer. Trong ví dụ, shop và admin là hai ứng dụng khác nhau; cookie giữ phiên của shop cần phạm vi phù hợp với shop.

OCI không cho gắn backend set có cookie persistence đặt Secure=true với listener HTTP. Vì vậy, cấu hình trong ví dụ được dùng với HTTPS. Các tùy chọn và hành vi Domain, Path, Secure, HttpOnly được mô tả trong [Load Balancer Session Persistence](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/sessionpersistence.htm).

Nếu đổi Path thành **/cart**, cookie đó sẽ không được gửi cho mọi đường dẫn của shop. Phải đánh giá liệu các trang như /checkout cũng cần cùng phiên hay không.

## 6. Tương tác giữa routing, persistence và tính sẵn sàng

### Rule chọn nhóm vẫn phải được tôn trọng

Một client có cookie của shop_bs vẫn có thể gửi **/api/orders**. Kết quả mong muốn là yêu cầu tới api_bs theo routing policy, không quay lại shop-a chỉ vì đã có cookie.

Hãy kiểm tra cookie theo nhóm đích, tên, phạm vi và cấu hình persistence thực tế. Tài liệu Oracle nêu rằng các quy tắc định tuyến đường dẫn được ưu tiên và cookie không hợp lệ với đích bị bỏ qua. [Nguồn: LB Cookie Session Persistence Configuration](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/load_balancer/models/oci.load_balancer.models.LBCookieSessionPersistenceConfigurationDetails.html).

Khi thay routing policy, client có cookie cũ là một nhóm kiểm thử riêng. Chỉ kiểm tra trình duyệt ẩn danh có thể bỏ sót lỗi trong phiên đang tồn tại.

### Fallback khi backend của phiên không còn sẵn sàng

Mặc định cho phép fallback tới backend khác. Nếu cấu hình **disableFallback=true**, yêu cầu của phiên có thể nhận HTTP 502 khi backend đã gắn không sử dụng được. Phiên tiếp tục gửi cookie tới backend không sẵn sàng có thể tiếp tục lỗi. [Nguồn: Common Load Balancer Errors](https://docs.oracle.com/en-us/iaas/Content/Balance/Troubleshooting/common_load_balancer_errors.htm).

| Lựa chọn | Khi backend cũ lỗi | Việc ứng dụng vẫn phải giải quyết |
| --- | --- | --- |
| disableFallback=false | Có thể chuyển sang backend khác | Khôi phục phiên, đọc trạng thái dùng chung hoặc yêu cầu đăng nhập lại |
| disableFallback=true | Không chuyển phiên sang backend khác theo cơ chế fallback | Chấp nhận lỗi, kế hoạch phục hồi backend và xử lý cookie/phiên |

Cho phép fallback giúp duy trì đường phục vụ nhưng không bảo toàn dữ liệu chỉ lưu trong RAM. Tắt fallback cũng không biến bộ nhớ của máy thành kho dữ liệu bền vững.

Chọn cấu hình theo hậu quả nghiệp vụ của việc đổi máy. Nếu một giao dịch có thể bị gửi lại sau lỗi, ứng dụng cần quy tắc xử lý trùng phù hợp, độc lập với stickiness.

### Drain không cắt mọi phiên đang tồn tại

Backend ở trạng thái drain vẫn được xem là khả dụng cho các persisted session đang có; yêu cầu mới không thuộc phiên đó không được đưa tới máy đang drain. [Nguồn: Session Persistence — Fallback](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/sessionpersistence.htm).

Do đó, khi bảo trì:

1. Bật drain và quan sát kết nối, phiên còn hoạt động.
2. Đặt điều kiện kết thúc chờ dựa trên ứng dụng.
3. Xử lý các phiên dài theo kế hoạch triển khai.
4. Dừng dịch vụ khi đã sẵn sàng bảo trì.
5. Khôi phục và kiểm tra rồi mới đưa máy trở lại phục vụ.

Cookie sống quá lâu có thể làm quá trình chuyển phiên kéo dài. Không coi drain là phép xóa toàn bộ session hoặc bằng chứng máy không còn xử lý yêu cầu.

## 7. Thiết kế lab nhiều ứng dụng

### Tài nguyên chuẩn bị

Sử dụng một OCI Load Balancer lab với khả năng truy cập từ máy thử nghiệm, các backend set đã có backend khỏe và các endpoint nhận diện:

| Backend set | Hợp đồng dùng để kiểm tra |
| --- | --- |
| shop_bs | /cart trả service=shop và node=shop-a hoặc shop-b |
| api_bs | /api/orders trả service=api cùng tên node |
| admin_bs | / trả trang quản trị giả lập |
| reject_bs | /ready trả 200, yêu cầu ứng dụng trả phản hồi từ chối hoặc không tìm thấy |

Không cần dùng dữ liệu khách hàng hay tài khoản quản trị thật. Các endpoint phải thực sự được cài trên backend; load balancer không sinh nội dung này.

Chuẩn bị chứng thư được client tin cậy, bao phủ shop và admin, cùng DNS lab tương ứng. Nếu dùng private load balancer, máy thử nghiệm phải có đường mạng tới địa chỉ private.

### Quyền và mạng

Danh tính cấu hình cần quyền quản lý load balancer trong đúng compartment. Khi thay đổi DNS, chứng thư hoặc log, cần các quyền tương ứng của các tài nguyên đó. Không mở quyền toàn tenancy chỉ để tránh xác định tài nguyên thiếu quyền.

Đường mạng gồm client tới cổng HTTPS của load balancer, load balancer tới cổng ứng dụng và health check tới backend. Đồng thời kiểm tra NSG, security list, route và firewall hệ điều hành.

Hostname và path không tạo ranh giới phân quyền giữa người dùng. Trang admin vẫn cần xác thực và kiểm tra quyền ở lớp ứng dụng hoặc cơ chế bảo vệ đã thiết kế.

### Cấu hình theo thứ tự phụ thuộc

Thực hiện bằng Console để quan sát rõ từng liên kết:

1. Xác nhận backend của shop_bs, api_bs, admin_bs và reject_bs khỏe.
2. Tạo hostname resources shop_host và admin_host.
3. Tạo shop_routes theo mẫu rule /api của bài.
4. Cấu hình shop_https trên 443 với shop_host, default shop_bs và shop_routes.
5. Cấu hình admin_https trên 443 với admin_host và default admin_bs.
6. Chuẩn bị listener mặc định không gắn hostname theo thiết kế, dùng reject_bs.
7. Gắn chứng thư phù hợp và kiểm tra cấu hình HTTPS của từng listener.
8. Bật load balancer cookie persistence trên shop_bs theo cấu hình minh họa.
9. Giữ api_bs và admin_bs theo yêu cầu phiên đã xác định; lab không cần bật cùng một cookie cho tất cả nhóm.
10. Kiểm tra DNS rồi chạy ma trận yêu cầu.

Đợi work request của mỗi thay đổi hoàn tất trước khi thực hiện thay đổi phụ thuộc. Việc tạo policy thành công chưa chứng minh policy đã được gắn vào listener.

## 8. Minh họa tự động hóa và đọc lại cấu hình

Các lệnh dưới đây là nội dung thực hành, không phải lệnh đã chạy trên tenancy. Thay biến mẫu trước khi sử dụng OCI CLI trong PowerShell.

### Tạo hai hostname resources

~~~powershell
$Region = 'THAY_REGION'
$LoadBalancerId = 'THAY_OCID_LOAD_BALANCER'
$Hostnames = @(
    @{ Name = 'shop_host'; Hostname = 'shop.example.com' },
    @{ Name = 'admin_host'; Hostname = 'admin.example.com' }
)

foreach ($HostnameItem in $Hostnames) {
    $CreateArgs = @(
        'lb', 'hostname', 'create',
        '--region', $Region,
        '--load-balancer-id', $LoadBalancerId,
        '--name', $HostnameItem.Name,
        '--hostname', $HostnameItem.Hostname,
        '--wait-for-state', 'SUCCEEDED',
        '--max-wait-seconds', '300'
    )
    oci @CreateArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Can kiem tra work request cho hostname $($HostnameItem.Name)"
    }
}
~~~

Chỉ chạy phần tạo nếu các tài nguyên này chưa tồn tại. Hostname resource được thêm vào load balancer; vẫn cần liên kết với listener và cấu hình DNS. [Tham chiếu OCI CLI hostname create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/hostname/create.html).

Nếu timeout, xem work request và trạng thái hiện tại trước khi gửi lại. Không giả định timeout đồng nghĩa dịch vụ chưa tạo tài nguyên.

### Đọc lại routing policy

~~~powershell
$GetRoutingArgs = @(
    'lb', 'routing-policy', 'get',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--routing-policy-name', 'shop_routes'
)
oci @GetRoutingArgs
~~~

Đối chiếu điều kiện, thứ tự rules và backendSetName với bản thiết kế. Sau đó kiểm tra listener thực sự tham chiếu shop_routes trên Console. [Tham chiếu OCI CLI routing-policy get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/routing-policy/get.html).

Với pipeline tự động hóa, lưu cấu hình mong muốn trong hệ thống quản lý cấu hình của dự án, đọc trạng thái hiện tại và kiểm soát thay đổi đồng thời. Tránh gửi một thao tác update chứa danh sách thiếu làm mất cấu hình đang được ứng dụng khác sử dụng.

## 9. Kiểm tra định tuyến và cookie

### Ma trận kiểm tra bắt buộc

| Host | Path | Phiên | Kết quả định tuyến mong muốn trong lab |
| --- | --- | --- | --- |
| shop.example.com | /cart | Mới | shop_bs, nhận cookie persistence |
| shop.example.com | /cart | Đã có cookie | Tiếp tục backend phù hợp của phiên nếu còn khả dụng |
| shop.example.com | /api | Bất kỳ | api_bs |
| shop.example.com | /api/orders | Đã có cookie shop | api_bs |
| shop.example.com | /apiv2/orders | Bất kỳ | Default shop_bs theo rule đang dùng |
| admin.example.com | / | Mới | admin_bs |
| Host không được khai báo | / | Bất kỳ | Đường mặc định nếu yêu cầu đi qua được TLS |
| shop.example.com | /cart | Cookie cũ, backend lỗi | Hành vi theo cấu hình fallback |

Bảng xác định **nhóm đích**, không khẳng định mọi URL đều trả HTTP 200. Ví dụ shop_bs có thể trả 404 cho /apiv2/orders vì ứng dụng không cung cấp đường dẫn đó.

### Kiểm tra HTTPS trước khi đổi DNS chung

Có thể dùng curl trên máy thử nghiệm có đường tới load balancer:

~~~powershell
$LoadBalancerIp = 'THAY_IP_LOAD_BALANCER'
$ShopResolve = 'shop.example.com:443:{0}' -f $LoadBalancerIp

curl.exe --http1.1 --resolve $ShopResolve --silent --show-error --dump-header - 'https://shop.example.com/api/orders'
~~~

Tùy chọn --resolve cung cấp ánh xạ host/cổng tới IP cho lần gọi, trong khi URL vẫn mang hostname cần kiểm tra. Chứng thư vẫn phải hợp lệ và được client tin cậy. Dùng curl.exe để gọi đúng chương trình curl trong PowerShell. [Nguồn: curl --resolve](https://curl.se/docs/manpage.html#--resolve).

Lệnh này kiểm tra một yêu cầu chưa duy trì cookie giữa các lần chạy. Khi thử default listener ở tầng HTTP, có thể giữ SNI hợp lệ của shop nhưng thay Host:

~~~powershell
curl.exe --http1.1 --resolve $ShopResolve --header 'Host: unknown.example.com' --silent --show-error --dump-header - 'https://shop.example.com/'
~~~

Đây là phép kiểm tra có chủ đích cho Host không khớp sau bước TLS. Nó không chứng minh chứng thư sẽ hợp lệ khi người dùng truy cập URL https://unknown.example.com/.

### Kiểm tra phiên bằng cookie container

Sau khi DNS lab hoạt động, dùng một cookie container riêng cho client A:

~~~powershell
$ShopUri = 'https://shop.example.com/cart'
$SessionA = New-Object Microsoft.PowerShell.Commands.WebRequestSession

1..5 | ForEach-Object {
    $Response = Invoke-WebRequest -Uri $ShopUri -WebSession $SessionA -UseBasicParsing
    [pscustomobject]@{
        StatusCode = $Response.StatusCode
        Body = $Response.Content
    }
}

$SessionA.Cookies.GetCookies([uri]$ShopUri) |
    Select-Object Name, Domain, Path, Secure, HttpOnly
~~~

Kiểm tra cùng node qua phản hồi và access log. Bảng cookie chỉ in thuộc tính, không cần in giá trị cookie vào báo cáo.

Tạo một WebRequestSession khác cho client B để thử phiên độc lập. Hai phiên có thể được chọn cùng một backend; điều đó không tự chứng minh cấu hình sai.

Với application cookie mode, phải gọi đúng chức năng làm ứng dụng phát APPSESSID trước khi kiểm tra giữ phiên. Tạo một request vô danh không phát cookie rồi mong nó luôn về cùng máy là một phép thử thiếu điều kiện.

### Thử lỗi có kiểm soát

Dùng backend lab:

1. Tạo phiên và ghi nhận node đang xử lý.
2. Cho node đó không đạt health check hoặc dừng dịch vụ theo kế hoạch.
3. Đợi trạng thái liên quan cập nhật và gọi lại bằng cùng cookie container.
4. Đối chiếu kết quả với disableFallback.
5. Kiểm tra trạng thái nghiệp vụ trên node mới nếu được chuyển.
6. Khôi phục backend và tạo phiên mới để so sánh.

Khi thử disableFallback=true, ghi nhận mã lỗi và log thay vì kết luận lỗi mạng chung. Không đổi cấu hình của hệ thống thật chỉ để quan sát một mã HTTP.

## 10. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Hướng điều tra |
| --- | --- |
| Cả shop và admin cùng trả một ứng dụng | DNS/IP, hostname resources, liên kết listener và listener mặc định |
| HTTPS lỗi trước khi thấy nội dung | Tên miền trong URL, SNI, chứng thư và chuỗi tin cậy |
| /api/orders về shop | Rule chưa gắn, điều kiện không khớp hoặc policy khác đang được listener dùng |
| Rule cụ thể không bao giờ chạy | Thứ tự rule tổng quát đặt phía trước |
| Backend nhận /api/... rồi trả 404 | Hợp đồng đường dẫn và giả định rewrite |
| Refresh thay node dù đã bật application persistence | Backend có phát đúng Set-Cookie chưa; client có lưu và gửi lại không |
| Chỉ một số trang mất giữ phiên | Domain, Path, Secure, redirect và phạm vi cookie |
| Có cookie shop nhưng gọi API sai ứng dụng | Liên kết routing/backend set và cấu hình cookie theo nhóm đích |
| Chỉ client cũ bị 502 sau khi một node lỗi | Cookie persistence cũ và disableFallback |
| Drain nhưng máy vẫn có yêu cầu | Persisted session đang tồn tại và kết nối chưa kết thúc |

Khi điều tra, lưu thời điểm UTC, host, path, listener hoặc nhóm đích quan sát được và node xử lý. Đối chiếu log load balancer với log ứng dụng bằng mã tương quan nếu ứng dụng hỗ trợ.

Không cần ghi toàn bộ Cookie, Authorization hoặc nội dung phiên vào log để biết yêu cầu tới máy nào. Dùng giá trị nhận diện node giả lập và che thông tin nhạy cảm trong bằng chứng.

Nếu cookie không hoạt động trong trình duyệt nhưng công cụ thử hoạt động, kiểm tra cả chính sách chấp nhận cookie và luồng redirect thực tế của trình duyệt. Đừng sửa rule routing trước khi xác định cookie có được gửi hay không.

## 11. Vận hành, thay đổi và lựa chọn kiến trúc

### Thay đổi routing khi có phiên đang tồn tại

Trước khi áp dụng:

- Ghi nhận policy, liên kết listener và cấu hình persistence hiện tại.
- Kiểm tra backend set mới đã khỏe và xử lý đúng đường dẫn.
- Chuẩn bị ca thử cho phiên mới và cookie cũ.
- Xác định thay đổi nào có thể hoàn nguyên và dữ liệu phiên nào cần xử lý.

Sau khi áp dụng, quan sát tỷ lệ lỗi, độ trễ, phân bố node và phản hồi của các đường quan trọng. Nếu cần quay lại, khôi phục đúng cấu hình liên kết và kiểm tra lại với cả client cũ.

Không giả định rollback policy làm sống lại dữ liệu RAM đã mất trên backend hoặc hoàn tác giao dịch người dùng đã thực hiện.

### Stateless, kho phiên dùng chung và stickiness

Ứng dụng có trạng thái phiên dùng chung thường linh hoạt hơn khi backend thay đổi. Điều đó vẫn cần thiết kế thời hạn phiên, quyền truy cập kho, hành vi lỗi và khả năng phục hồi phù hợp.

Có thể dùng stickiness để giảm chi phí cache hoặc hỗ trợ một ứng dụng cũ, nhưng phải có câu trả lời khi máy giữ phiên bị mất. Nếu kho phiên nằm trong cơ sở dữ liệu Oracle hoặc dịch vụ khác, đưa phụ thuộc đó vào kiểm tra tính sẵn sàng và năng lực.

Không chọn IP_HASH chỉ vì nghĩ rằng mỗi IP luôn đại diện một người dùng. NAT có thể gom nhiều người sau một IP, trong khi client di động có thể thay IP.

### Chia sẻ load balancer và kiểm soát chi phí

Dùng chung địa chỉ và load balancer cho nhiều ứng dụng có thể giảm số tài nguyên cần vận hành. Đổi lại, các ứng dụng chia sẻ năng lực, phạm vi ảnh hưởng khi sửa cấu hình và lịch thay đổi.

Quyết định dùng chung hay tách cần xét:

- Tổng lưu lượng và năng lực dự phòng.
- Mức độc lập cần có giữa nhóm vận hành.
- Chính sách TLS, truy cập và log.
- Hậu quả khi cấu hình mặc định hoặc rule bị thay sai.
- Chi phí load balancer, backend và giám sát theo môi trường thực tế.

Không suy ra số hostname hoặc số rule tự tạo ra một mức phí độc lập cố định. Kiểm tra tài nguyên và điều kiện tính phí thực tế trước khi dự toán.

## 12. Bài thực hành củng cố

Hoàn thành trong môi trường lab:

1. Vẽ ánh xạ DNS, virtual hostname, listener, routing policy và backend set.
2. Chạy đầy đủ ma trận host/path, gồm /api, /api/orders và /apiv2/orders.
3. Xác nhận hostname lạ đi theo đường mặc định đã thiết kế.
4. So sánh một client không giữ cookie với client có cookie container.
5. Chuyển riêng shop_bs giữa hai chế độ persistence, mỗi lần chỉ bật một chế độ và tạo phiên thử mới.
6. So sánh bật và tắt fallback khi backend của phiên không khả dụng.
7. Thử drain và giải thích tại sao phiên cũ vẫn có thể tới máy đó.
8. Đề xuất cách giữ giỏ hàng khi cần chuyển sang backend khác.

Kết quả cần có: bản đồ cấu hình, thứ tự rule, phạm vi cookie, bằng chứng node xử lý và hành vi khi lỗi. Khôi phục các cấu hình thử nghiệm đã thay và chỉ dọn tài nguyên lab sau khi kiểm tra không còn phụ thuộc.

Một thiết kế hoàn chỉnh phải trả lời được ba câu hỏi: tên miền này tới listener nào, yêu cầu này tới nhóm nào và khi backend giữ phiên không còn sẵn sàng thì người dùng tiếp tục ra sao.