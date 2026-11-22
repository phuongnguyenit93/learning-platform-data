# Bảo vệ ứng dụng web bằng Web Application Firewall

Một ứng dụng web có thể đã được triển khai trong VNet, giới hạn cổng truy cập bằng Network Security Group (NSG) và sử dụng HTTPS, nhưng vẫn đối diện với các yêu cầu HTTP độc hại: khai thác SQL injection, cross-site scripting (XSS), truy cập đường dẫn nhạy cảm hoặc lưu lượng tự động bất thường. Những hành vi này diễn ra ở tầng ứng dụng, nơi một quy tắc mở cổng TCP 443 không thể phân biệt yêu cầu hợp lệ và yêu cầu chứa mẫu tấn công.

**Web Application Firewall (WAF)** là lớp kiểm soát lưu lượng HTTP/HTTPS đặt phía trước ứng dụng web hoặc API. Azure cung cấp WAF gắn với **Azure Application Gateway** và **Azure Front Door**. WAF phân tích các đặc trưng của HTTP request theo chính sách, áp dụng tập quy tắc được quản lý hoặc quy tắc tự định nghĩa và ghi nhận các sự kiện để vận hành, điều tra và điều chỉnh.

Bài này thuộc chương **Kết nối và bảo vệ mạng** của module **CLOUD_PROVIDERS_AZURE**. Module giới thiệu Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ, dữ liệu, triển khai, giám sát, bảo vệ và kiểm soát chi phí. Trong kiến trúc ứng dụng Azure, WAF bổ sung lớp bảo vệ **Layer 7** bên cạnh VNet, NSG, quản lý danh tính, giám sát và các cơ chế bảo mật ứng dụng.

Sau bài học, bạn có thể:

- Giải thích WAF kiểm soát gì và những giới hạn WAF không thể giải quyết.
- Chọn Azure Application Gateway WAF hay Azure Front Door WAF theo kiến trúc.
- Phân biệt **managed rules**, **custom rules**, **Detection** và **Prevention**.
- Thiết kế WAF policy, phạm vi gắn policy, quy tắc, ngoại lệ và giám sát.
- Giảm false positive mà không tắt toàn bộ lớp bảo vệ.
- Xây dựng lộ trình triển khai từ thử nghiệm tới production, kiểm tra log và truy vết sự cố.
- Bảo vệ đường truy cập vào origin để hạn chế việc vượt qua WAF.

## 1. WAF hoạt động ở vị trí nào?

WAF là reverse-proxy security control nằm trên đường lưu lượng web. Nó nhận request, đối chiếu chính sách và chuyển request hợp lệ tới máy chủ phía sau (origin/backend). Những request bị chặn sẽ không được chuyển tiếp theo luồng bình thường.

~~~text
 Người dùng / trình duyệt / API client
                  |
               HTTPS
                  |
      +-----------v------------+
      | Azure Front Door WAF   |
      | hoặc Application       |
      | Gateway WAF            |
      +-----------+------------+
                  |
        Kiểm tra HTTP request
        - managed rules
        - custom rules
        - policy action/mode
                  |
          +-------+-------+
          |               |
     Request hợp lệ   Request bị chặn
          |               |
          v               v
     Backend web/API   Log + phản hồi
          |
     Cơ sở dữ liệu /
     dịch vụ nội bộ
~~~

### WAF có thể quan sát những gì?

Tùy sản phẩm, chính sách, kiểu request và giới hạn kiểm tra, WAF có thể đánh giá phương thức HTTP, URL, query string, header, cookie, địa chỉ IP client và phần request body được hỗ trợ. Managed rules nhận diện các mẫu khai thác ứng dụng phổ biến; custom rules xử lý điều kiện cụ thể của tổ chức.

Ví dụ một endpoint **/products?search=...** dùng để tìm sản phẩm. Một yêu cầu có mẫu giống SQL injection trong tham số **search** có thể bị managed rule ghi nhận hoặc chặn. Tuy nhiên, WAF không chạy thay logic xác thực trong ứng dụng: nó không biết người dùng có được phép xem đơn hàng của người khác hay không nếu yêu cầu trông hợp lệ về cú pháp.

### WAF không thay thế những gì?

| Công cụ/cơ chế | Phạm vi chính | Vì sao vẫn cần khi có WAF? |
|---|---|---|
| **NSG** | Cho phép/chặn kết nối mạng L3/L4 theo IP, port và protocol | Giới hạn luồng mạng tới subnet/NIC, không kiểm tra đầy đủ nội dung HTTP |
| **Azure DDoS Protection** | Phòng vệ trước các kiểu tấn công DDoS ở tầng mạng | WAF không thay toàn bộ biện pháp chống DDoS L3/L4 |
| **Azure Firewall** | Kiểm soát lưu lượng mạng tập trung, nhiều giao thức | Phạm vi và chính sách khác WAF chuyên về HTTP |
| **Microsoft Entra ID / xác thực** | Xác minh danh tính và cấp token | WAF không xác định quyền nghiệp vụ của từng người dùng |
| **Ủy quyền trong API** | Quyết định ai được đọc/sửa bản ghi nào | Chặn lỗi truy cập chéo tài khoản hoặc tenant mà rule chung khó nhận biết |
| **Secure coding, SAST/DAST** | Phòng và tìm lỗ hổng tại nguồn | WAF chỉ là lớp giảm thiểu rủi ro; lỗi gốc phải được sửa |
| **Backup, DR, giám sát** | Phục hồi, phát hiện và điều tra | WAF không bảo đảm dữ liệu có thể khôi phục hoặc ứng dụng luôn khả dụng |

WAF chủ yếu đánh giá **HTTP/HTTPS**. Không dùng WAF để bảo vệ một cổng TCP tùy ý, dịch vụ SSH, giao thức cơ sở dữ liệu hoặc toàn bộ lưu lượng bên trong VNet.

## 2. Chọn Azure Application Gateway WAF hay Azure Front Door WAF?

Trong Azure có hai hướng triển khai WAF phổ biến, phù hợp với những nhu cầu khác nhau.

| Tiêu chí | Application Gateway WAF | Azure Front Door WAF |
|---|---|---|
| Vị trí | Reverse proxy Layer 7 trong khu vực Azure (regional) | Reverse proxy/điểm vào toàn cầu ở mạng biên (global edge) |
| Kiến trúc thường gặp | Ứng dụng trong VNet, các backend theo vùng, điều hướng host/path | Website hoặc API toàn cầu, nhiều region, cần edge routing/acceleration |
| Tài nguyên liên quan | Application Gateway SKU hỗ trợ WAF, backend pool, listener, routing rule | Front Door profile/endpoint, origin group, route, domain và security policy |
| Tập quy tắc | WAF policy với managed rules và custom rules được hỗ trợ | WAF policy với tính năng theo Front Door SKU/tier |
| Phạm vi áp dụng | Có thể áp dụng policy ở gateway và các phạm vi được hỗ trợ như listener/path | Gắn WAF policy với domain/đường dẫn qua cấu hình security policy |
| Điều cần chú ý | VNet, subnet dành riêng, backend health, TLS, đường đến backend | Origin security, bypass prevention, tên miền, routing và khả năng dùng tính năng theo tier |

**Application Gateway WAF_v2** thường phù hợp khi bạn muốn bảo vệ một ứng dụng vùng Azure, truy cập các backend trong VNet và quản lý ingress cùng cấu trúc mạng. Ví dụ: cổng nhân sự triển khai trong một khu vực, backend là VM hoặc private endpoint đến dịch vụ web tùy khả năng kết nối.

**Azure Front Door WAF** phù hợp khi doanh nghiệp phục vụ người dùng nhiều khu vực địa lý, cần một điểm vào công khai toàn cầu, điều hướng về các origin và bổ sung bảo vệ ở edge. Ví dụ: SaaS có origin tại Đông Nam Á và châu Âu. Các khả năng như managed rule sets và bot protection phụ thuộc vào **tier/SKU** và phiên bản dịch vụ; cần kiểm tra tính năng khả dụng trước khi lập thiết kế. Với Front Door Standard/Premium, không áp dụng nguyên xi hướng dẫn của dịch vụ Front Door (classic) cũ.

Trong một số kiến trúc, Front Door đứng phía trước Application Gateway. Khi đó, cần xác định rõ **lớp nào thực thi WAF**, ranh giới mạng và mục đích của từng policy để tránh cấu hình trùng lặp khó vận hành. Việc có hai lớp WAF không tự động làm an toàn hơn nếu origin vẫn được truy cập trực tiếp hoặc các policy mâu thuẫn.

### Quy trình chọn nền tảng

1. **Vị trí người dùng:** một vùng nội bộ hay Internet toàn cầu?
2. **Vị trí backend:** trong VNet, App Service, nhiều region hay kết hợp?
3. **Yêu cầu availability và routing:** chỉ phân phối regional hay cần chuyển hướng giữa origin toàn cầu?
4. **Security requirements:** cần managed rules, bot protection, rate limiting, logging và khả năng tùy biến nào?
5. **Chi phí/vận hành:** dịch vụ gateway/edge, số request, dữ liệu truyền, log, khả năng dự phòng và nhân sự vận hành.
6. **Giới hạn sản phẩm:** SKU, region, tình trạng hỗ trợ rule set và các feature phải được xác nhận cho môi trường cụ thể.

## 3. Các thành phần của WAF policy

**WAF policy** là nơi gom cấu hình bảo vệ để quản lý độc lập với nhiều phần còn lại của gateway hoặc Front Door. Các mục quan trọng:

| Thành phần | Ý nghĩa | Quyết định cần thực hiện |
|---|---|---|
| Policy mode | Detection hoặc Prevention | Quan sát hay chặn theo kết quả đánh giá |
| Managed rule sets | Tập quy tắc do nhà cung cấp duy trì | Chọn rule set và phiên bản được hỗ trợ |
| Custom rules | Quy tắc tự định nghĩa theo điều kiện và ưu tiên | Chặn/cho phép/lập chính sách theo IP, URL, rate, v.v. |
| Rule exclusions | Loại trừ có kiểm soát một phần yêu cầu khỏi kiểm tra managed rule | Giảm false positive có bằng chứng |
| Request body/file limits | Cấu hình và giới hạn kiểm tra phần thân/đính kèm | Đảm bảo phù hợp API và tải tệp |
| Policy association | Vùng áp dụng policy | Tất cả traffic hay chỉ hostname/route/listener cụ thể |
| Diagnostics | Log, metric, cảnh báo | Phát hiện tấn công và ảnh hưởng người dùng |

Một policy chưa gắn đúng điểm tiếp nhận traffic có thể không bảo vệ ứng dụng dù bản thân policy đã được tạo thành công. Bạn luôn phải kiểm tra đường đi **client → gateway/Front Door → backend** và phạm vi association.

### Detection và Prevention

| Mode | Hành vi điển hình | Khi sử dụng |
|---|---|---|
| **Detection** | Ghi nhận những yêu cầu khớp rule mà không chặn chúng chỉ vì managed-rule detection | Giai đoạn quan sát và điều chỉnh false positive |
| **Prevention** | Thực thi hành động chặn theo policy/rule | Sau khi kiểm thử và sẵn sàng bảo vệ production |

**Quan trọng:** Đừng diễn giải Detection là mọi custom rule sẽ bị vô hiệu hóa trong mọi trường hợp hoặc mọi phiên bản sản phẩm. Hành vi của **custom rule action**, managed rules và mode có thể khác theo WAF platform. Khi thử nghiệm, đối chiếu log và kết quả HTTP thực tế của đúng sản phẩm và chính sách đang dùng.

Chuyển thẳng sang Prevention trên hệ thống có request phức tạp (API JSON, upload, callback thanh toán) có nguy cơ làm gián đoạn người dùng hợp lệ. Quy trình được khuyến nghị: thu thập baseline ở Detection, xem log, điều chỉnh, thử nghiệm có kiểm soát, sau đó đưa Prevention vào vận hành với khả năng rollback.

## 4. Managed rules: bảo vệ trước kiểu tấn công phổ biến

Managed rules là những quy tắc bảo vệ được nhà cung cấp duy trì. Trên Azure Application Gateway, các tập quy tắc phổ biến có nguồn gốc từ **OWASP Core Rule Set (CRS)** và các bộ quy tắc Microsoft cung cấp tùy nền tảng/phiên bản. Trên Azure Front Door, tập quy tắc được hỗ trợ phụ thuộc SKU và phiên bản dịch vụ. Không giả định rằng tên, phiên bản, số rule ID hay khả năng cập nhật hoàn toàn giống nhau giữa hai sản phẩm.

Một số nhóm rủi ro WAF có thể giúp nhận diện:

- **SQL injection (SQLi):** các mẫu chèn biểu thức SQL vào URL, query hoặc body.
- **Cross-site scripting (XSS):** nội dung có đặc trưng mã script nguy hiểm trong request.
- **Local/remote file inclusion và path traversal:** các mẫu cố tìm đọc hoặc sử dụng tệp ngoài ý muốn.
- **Protocol anomaly:** request có cấu trúc bất thường, header sai định dạng hoặc biểu hiện né tránh kiểm tra.
- **Command injection và các mẫu khai thác ứng dụng khác:** phụ thuộc tập quy tắc cụ thể và cách xử lý request.
- **Bot-related patterns:** chỉ khi policy/SKU hỗ trợ bot protection thích hợp.

### Cơ chế anomaly scoring

Nhiều managed rule set dùng **anomaly scoring**: một request có thể khớp một hay nhiều rule, mỗi lần khớp đóng góp điểm, và hành động cuối cùng phụ thuộc ngưỡng/chính sách. Không nên hiểu rằng mọi lần một rule xuất hiện trong log đều tương đương với một request đã bị từ chối.

Ví dụ mang tính minh họa:

~~~text
Request: GET /search?q=...
  |
  +-- Managed rule A: matched, ghi nhận tín hiệu bất thường
  +-- Managed rule B: matched, bổ sung tín hiệu
  |
  +-- Kết quả đánh giá policy
        |
        +-- Detection: log kết quả đánh giá
        |
        +-- Prevention: chặn nếu điều kiện chặn được thỏa mãn
~~~

Khi điều tra, phải xem **action**, **rule ID**, **thông điệp**, **transaction/request correlation** và bối cảnh chính sách, thay vì chỉ đếm các dòng matched rule.

### Cập nhật managed rules

Rule set mới có thể tăng khả năng nhận diện nhưng cũng thay đổi kết quả đối với lưu lượng hợp lệ. Để nâng phiên bản: xác nhận khả năng hỗ trợ, kiểm thử trên staging, so sánh số lượng block/false positive, lập lịch cập nhật và có kế hoạch rollback. Tránh tự động nâng rule set khi chưa kiểm thử các luồng quan trọng.

## 5. Custom rules: áp dụng yêu cầu riêng

**Custom rule** là quy tắc bạn xây dựng để xử lý những điều kiện cụ thể, ví dụ:

- Giới hạn truy cập vào vùng quản trị từ các IP công ty được phê duyệt.
- Chặn một dải IP đã được nhóm an ninh xác định độc hại.
- Áp dụng rate limiting cho endpoint dễ bị lạm dụng nếu nền tảng hỗ trợ.
- Bổ sung kiểm soát theo URI, header, method hoặc các match variable khác.

Một custom rule có thể có **priority**, điều kiện so khớp và action. Các action sẵn có khác nhau theo nền tảng; thường bao gồm **Allow** hoặc **Block**, và có thể có **Log**, **Redirect**, challenge hoặc rate limiting trong những cấu hình/SKU nhất định. Luôn đối chiếu tùy chọn hiển thị trên policy cụ thể trước khi dùng.

### Ví dụ quy tắc bảo vệ đường dẫn quản trị

Giả sử giao diện quản trị nằm tại **/admin** và chỉ nhân viên qua egress IP công ty mới được vào. Có thể thiết kế custom rule với điều kiện:

~~~text
Nếu đường dẫn request bắt đầu với /admin
và địa chỉ IP client không thuộc dải egress được phê duyệt
thì Block.
~~~

Đây là **mô tả logic**, chưa phải cấu hình sản phẩm hoàn chỉnh. Phải kiểm tra cách match URL/path, normalization, địa chỉ nguồn client đáng tin cậy và thứ tự đánh giá rule trong WAF platform. Thực tế một người quản trị có thể dùng VPN hoặc Zero Trust Access với IP thay đổi; không nên coi IP allowlist là lớp xác thực duy nhất. Ứng dụng vẫn phải yêu cầu đăng nhập và kiểm tra vai trò quản trị.

### Ví dụ rate limiting

API công khai **/api/search** bị một bot gửi quá nhiều request. Nếu WAF platform/tier hỗ trợ rate limiting, có thể áp dụng ngưỡng theo client hoặc key được hỗ trợ để giảm lạm dụng. Không đặt ngưỡng chỉ dựa trên một IP nếu nhiều người dùng hợp lệ có thể đi chung NAT hoặc proxy; cần điều chỉnh dựa trên dữ liệu quan sát, độ trễ và mục tiêu nghiệp vụ.

Rate limiting không thay thế quota/rate limit trong API backend, vì danh tính người dùng, API key và gói thuê bao thường chỉ được ứng dụng biết chính xác.

### Thứ tự và tác động của custom rules

Quy tắc có priority cao có thể được xử lý trước các quy tắc khác; một số action **Allow** có khả năng bỏ qua các bước kiểm tra tiếp theo theo hành vi của sản phẩm. Vì vậy, một rule Allow quá rộng có thể vô tình tạo ngoại lệ lớn và làm mất tác dụng của managed rules đối với traffic đó. Hãy ưu tiên điều kiện hẹp, review độc lập và kiểm thử cả request đáng ngờ lẫn request hợp lệ.

## 6. Kiến trúc mẫu: WAF cho ứng dụng trên Azure

Một công ty triển khai web thương mại điện tử gồm frontend, API và cơ sở dữ liệu trong Azure. Yêu cầu: HTTPS công khai, ngăn các mẫu tấn công HTTP phổ biến, bảo vệ trang quản trị, ghi log để điều tra, không cho client truy cập thẳng API backend.

~~~text
                    Internet
                       |
                DNS: shop.example
                       |
            +----------v-----------+
            | Front Door WAF       |
            | hoặc App Gateway WAF |
            +----------+-----------+
                       |
                 HTTPS tới origin
                       |
          +------------v-------------+
          | Web frontend / API       |
          | AuthN / AuthZ / logging  |
          +------------+-------------+
                       |
                Dữ liệu nội bộ
             (không public trực tiếp)
~~~

Trong mô hình này, WAF bảo vệ **đường HTTP đi vào**. Các yêu cầu khác vẫn cần triển khai:

1. Backend kiểm tra danh tính và quyền đối với từng API/đối tượng.
2. Cấu hình TLS cho client → WAF và khi cần WAF → origin; quản lý vòng đời chứng chỉ.
3. Giới hạn đường truy cập thẳng vào origin bằng cơ chế mạng và xác minh nguồn request phù hợp.
4. Áp dụng NSG, private networking và least privilege khi có thể.
5. Gửi WAF/access logs tới công cụ giám sát và tạo cảnh báo trên block/error/latency.
6. Theo dõi health probe/backend health để tránh nhầm lỗi ứng dụng với lỗi WAF.

### Vấn đề quan trọng: origin bypass

Nếu website công khai đi qua Front Door WAF nhưng App Service hoặc public load balancer gốc vẫn chấp nhận request trực tiếp từ Internet, kẻ tấn công có thể bỏ qua WAF bằng cách gửi request tới địa chỉ origin thay vì hostname được bảo vệ.

Đối với Front Door, cần áp dụng các biện pháp kiểm soát truy cập origin tương ứng với loại backend, chẳng hạn **Private Link khi được hỗ trợ**, giới hạn nguồn kết nối và **xác minh danh tính instance Front Door** bằng cơ chế được tài liệu sản phẩm quy định. Chỉ cho phép một dải IP mạng biên chung chưa chắc bảo đảm request đi qua đúng Front Door profile của bạn. Không dựa vào một header tự khai báo từ Internet nếu chưa khóa đường truy cập origin.

Đối với Application Gateway, nên đặt backend trong mạng riêng hoặc cấu hình hạn chế inbound để chỉ các thành phần ingress được phép có thể kết nối, phù hợp với topology thực tế.

## 7. Tạo WAF policy bằng Azure Portal

Ví dụ sau dùng **Application Gateway WAF_v2**. Nếu chọn Front Door, nguyên tắc thiết kế tương tự nhưng đường dẫn menu, association và các lựa chọn rule khác nhau.

### Bước 1: chuẩn bị

- Có subscription và resource group được phép cấu hình.
- Có quyền tạo/sửa WAF policy và quyền liên kết với gateway.
- Có Application Gateway với SKU hỗ trợ WAF; nếu chưa có, chỉ thực hành tạo bản thiết kế hoặc policy chưa liên kết để tránh chi phí tài nguyên hạ tầng.
- Biết hostname, đường dẫn API, quy tắc truy cập cần bảo vệ, yêu cầu upload và những luồng đặc biệt của ứng dụng.

### Bước 2: tạo policy

1. Mở [Azure Portal](https://portal.azure.com), tìm **Web Application Firewall policies** hoặc mục WAF policy liên quan của Application Gateway.
2. Chọn **Create**, xác định subscription, resource group, location và tên policy, ví dụ **wafp-shop-prod**.
3. Chọn kiểu policy cho **Application Gateway** và managed rule set/phiên bản khả dụng.
4. Đặt **Detection** cho giai đoạn quan sát ban đầu.
5. Xác minh cấu hình kiểm tra request body, giới hạn upload và các tùy chọn khác theo loại ứng dụng.
6. Tạo policy rồi mở lại để kiểm tra các giá trị đã lưu.

### Bước 3: liên kết policy

Liên kết policy với Application Gateway hoặc phạm vi listener/path được hỗ trợ, phù hợp mô hình ingress và quy tắc kế thừa của sản phẩm. Sau khi association, kiểm tra gateway đã dùng policy mới và không bị một policy ở phạm vi khác ghi đè theo cơ chế sản phẩm.

### Bước 4: thêm custom rule

Ví dụ tạo rule giới hạn truy cập **/admin** từ nguồn không được phép. Trong Portal, chọn custom rules, tạo tên có ý nghĩa, chọn priority phù hợp, thêm điều kiện và action **Block**. Đối chiếu điều kiện với cách ứng dụng sử dụng URL encoding, proxy và địa chỉ client.

Trong môi trường thật, trước khi bật Block cần xác minh IP công ty hoặc danh tính hệ thống vẫn truy cập đúng, bao gồm cả health probe, bộ phận vận hành và quy trình khẩn cấp.

### Bước 5: chuyển sang Prevention có kiểm soát

Sau khi quan sát log ở Detection, thử các luồng đăng nhập, checkout, tìm kiếm, upload và API callback. Giải quyết false positive theo quy trình ở mục 10. Chỉ chuyển sang **Prevention** khi đã có bằng chứng kiểm thử, cửa sổ theo dõi và phương án quay lại trạng thái an toàn.

**Lưu ý:** giao diện Portal và danh mục managed rule thay đổi theo sản phẩm/SKU. Các bước diễn giải ý nghĩa cấu hình; nhãn menu có thể khác với phiên bản Portal mà bạn đang dùng.

## 8. Kiểm tra policy và thành phần liên quan bằng Azure CLI

Azure CLI giúp liệt kê và kiểm tra policy. Nhóm lệnh cho **Application Gateway WAF policy** khác nhóm lệnh Front Door; tránh trộn cú pháp giữa hai nền tảng.

Đầu tiên xác nhận tài khoản và subscription:

~~~bash
az login
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table
~~~

Nếu muốn xem các Application Gateway WAF policies đã tồn tại trong một resource group:

~~~bash
az network application-gateway waf-policy list \
  --resource-group <RESOURCE_GROUP> \
  --output table
~~~

Xem chi tiết policy đã được tạo:

~~~bash
az network application-gateway waf-policy show \
  --resource-group <RESOURCE_GROUP> \
  --name <WAF_POLICY_NAME> \
  --output json
~~~

Quan sát các trường cấu hình như policy settings, managed rules, custom rules, ID và phạm vi association nếu kết quả phiên bản CLI cung cấp. Một số thông tin liên kết nằm trong cấu hình Application Gateway/listener; vì thế hãy kiểm tra cả thành phần dùng policy.

Xem Application Gateway và cấu hình tổng quát:

~~~bash
az network application-gateway show \
  --resource-group <RESOURCE_GROUP> \
  --name <APPLICATION_GATEWAY_NAME> \
  --output json
~~~

Ở Front Door Standard/Premium, việc xem WAF policy cần dùng nhóm lệnh phù hợp với **Front Door WAF** và security policy association; không dùng lệnh của Application Gateway để kiểm tra Front Door. Trước khi tự động hóa việc tạo/sửa rule, dùng **az ... --help** để xác nhận đối số cho phiên bản Azure CLI đang cài. Bài học không coi các lệnh **show/list** là bằng chứng request đã được bảo vệ; bạn vẫn cần xem association, gửi traffic thử nghiệm và đọc log.

## 9. Ghi log, metric và điều tra sự kiện WAF

Một WAF policy chỉ hữu ích lâu dài khi nhóm vận hành biết đang chặn gì, lưu lượng hợp lệ có bị ảnh hưởng không và nguồn tấn công thay đổi như thế nào.

### Các loại dữ liệu nên theo dõi

| Dữ liệu | Ý nghĩa vận hành |
|---|---|
| WAF firewall logs | Rule ID, action, URI, client IP, lý do khớp rule, correlation/transaction ID tùy dịch vụ |
| Access logs | Trạng thái HTTP, latency, hostname, backend và request context |
| Metrics | Số request, số bị block, lỗi gateway/origin, health và latency |
| Application logs | Lỗi nghiệp vụ, trace ID, user journey và trạng thái xử lý backend |
| Azure Activity Log | Các thao tác thay đổi cấu hình policy/gateway ở management plane |

Để có log cho phân tích, cấu hình **Diagnostic settings** trên đúng tài nguyên Application Gateway/Front Door, chọn category thích hợp và gửi tới **Log Analytics workspace** hoặc đích logging được phê duyệt. Với Log Analytics, tên bảng phụ thuộc việc bạn chọn chế độ **resource-specific** hay **AzureDiagnostics** và từng loại dịch vụ.

### Ví dụ Kusto Query Language (KQL)

Với Application Gateway khi log được gửi vào bảng resource-specific **AGWFirewallLogs**, có thể bắt đầu bằng:

~~~kusto
AGWFirewallLogs
| where TimeGenerated > ago(1h)
| summarize Requests = count() by Action, RuleId
| order by Requests desc
~~~

Để khảo sát một số sự kiện mới nhất:

~~~kusto
AGWFirewallLogs
| where TimeGenerated > ago(30m)
| order by TimeGenerated desc
| take 30
~~~

Nếu workspace dùng **AzureDiagnostics**, một ví dụ khởi đầu là:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(1h)
| where Category == "ApplicationGatewayFirewallLog"
| order by TimeGenerated desc
| take 30
~~~

Với **Azure Front Door Standard/Premium**, log có tên bảng/category khác. Trường hợp dùng resource-specific table và workspace có dữ liệu, có thể khám phá sự kiện bằng:

~~~kusto
FrontDoorWebApplicationFirewallLog
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
| take 30
~~~

Đây là các truy vấn mẫu, **không phải cam kết** mọi workspace đều có sẵn bảng đó. Tên bảng, cột và category phải được xác nhận từ Diagnostic settings và schema hiện hành của dịch vụ. Nếu truy vấn báo bảng không tồn tại, hãy kiểm tra đã bật diagnostics chưa, chọn destination nào và có dữ liệu mới hay không.

### Liên kết các log khi có sự cố

Khi người dùng báo request bị từ chối, ghi nhận:

1. Thời điểm lỗi có timezone, hostname, URL path (không bao gồm secret hoặc dữ liệu nhạy cảm).
2. Mã HTTP và correlation/transaction ID nếu có.
3. WAF action, rule ID, policy ID và phần request dẫn đến match (chỉ lưu mức tối thiểu cần thiết).
4. Access logs và backend health để phân biệt **WAF block** với **origin 403/500/502**.
5. Thay đổi gần đây trong policy, managed rules, deployment và traffic pattern.

Không ghi access token, mật khẩu, cookie phiên hoặc payload chứa thông tin cá nhân vào ticket công khai. WAF logs có thể chứa URL, query string hoặc dấu vết nhạy cảm; phân quyền truy cập log, retention và masking theo chính sách dữ liệu.

## 10. Xử lý false positive mà vẫn giữ bảo vệ

**False positive** là request hợp lệ nhưng bị WAF đánh giá là nguy hiểm. Ví dụ: một hệ thống quản lý nội dung cho phép biên tập viên lưu mẫu HTML; managed rule có thể coi nội dung chứa thẻ script là dấu hiệu XSS. Nếu chặn toàn bộ, chức năng quản trị có thể không hoạt động.

Quy trình an toàn:

1. **Xác minh tác động:** thu thập đường dẫn, request mẫu hợp lệ, user journey, action và rule ID.
2. **Kiểm tra nguyên nhân:** so sánh rule match với input thực tế và cách ứng dụng xử lý/escape nội dung đó.
3. **Đánh giá rủi ro:** nội dung có thật sự cần được gửi hay nên sửa ứng dụng để dùng định dạng an toàn hơn?
4. **Chọn ngoại lệ hẹp:** chỉ loại trừ đúng tên tham số, header, cookie hoặc vị trí được sản phẩm hỗ trợ; nếu có thể, giới hạn đến rule hoặc rule group cụ thể.
5. **Giữ lại kiểm soát khác:** tiếp tục xác thực, ủy quyền, validation/encoding trong ứng dụng.
6. **Thử nghiệm:** xác nhận request hợp lệ hoạt động và các biến thể độc hại vẫn bị phát hiện.
7. **Theo dõi:** ghi ticket, người phê duyệt, lý do và thời điểm xem xét lại ngoại lệ.

**Không nên:** tắt toàn bộ managed rule set chỉ vì một endpoint lỗi; tạo custom Allow cho tất cả request tới /api; chuyển toàn production về Detection vô thời hạn; hoặc vô hiệu hóa request body inspection khi chưa hiểu rủi ro.

### Ví dụ ngoại lệ hợp lý

Endpoint **POST /content/save** có field **articleHtml** dùng để lưu HTML từ trình soạn thảo đã được kiểm soát. Log cho thấy một managed rule luôn khớp field này với request hợp lệ. Sau khi nhóm ứng dụng xác nhận input được kiểm soát và output được sanitize/encode phù hợp, có thể xem xét exclusion cho **trường cần thiết và rule gây false positive**, thay vì bỏ qua mọi kiểm tra với endpoint.

Tính năng exclusions, phạm vi theo rule ID, cách match selector và thứ tự đánh giá khác nhau giữa Application Gateway và Front Door. Chỉ tạo ngoại lệ nếu chính policy/tier đang dùng hỗ trợ cách khoanh vùng mong muốn.

## 11. Tối ưu request body, upload và API

Một website hiện đại có thể có upload ảnh, upload tài liệu, JSON API lớn, webhook và request body nhiều trường. WAF cần được cấu hình để kiểm tra phù hợp giới hạn và lưu lượng thực tế.

- **Request body inspection:** bật theo nhu cầu bảo vệ, nhưng kiểm tra hành vi đối với request quá lớn hoặc định dạng không được hỗ trợ.
- **File upload:** xét giới hạn kích thước, dịch vụ nhận file, chống mã độc cho nội dung tệp và lưu trữ an toàn; WAF không phải dịch vụ quét antivirus.
- **JSON/XML/form data:** hiểu vị trí body, query, header và tên trường mà managed rule/custom rule đánh giá.
- **Compression/encoding:** kiểm tra khả năng xử lý theo phiên bản dịch vụ; tránh giả định WAF luôn kiểm tra mọi byte của mọi payload.
- **Webhooks:** lưu ý endpoint thanh toán/đối tác có payload đặc thù, signature và yêu cầu retry; WAF policy không thay cơ chế xác minh webhook signature.
- **Streaming/WebSocket:** xác nhận khả năng hỗ trợ của gateway/Front Door và phần lưu lượng WAF có thể thực sự kiểm tra.

Giới hạn byte, kích thước upload và cách xử lý request vượt giới hạn thay đổi theo nền tảng, tier và cấu hình. Không sao chép một con số mặc định từ tài liệu cũ sang hệ thống mới; cần kiểm tra thông số hiện hành trước khi đưa vào production.

## 12. Lộ trình rollout WAF cho production

Thực thi WAF là thay đổi mạng và bảo mật có thể ảnh hưởng người dùng thật. Một kế hoạch triển khai nên có các mốc rõ ràng:

| Giai đoạn | Hoạt động | Tiêu chí đi tiếp |
|---|---|---|
| **Thiết kế** | Chọn ingress, xác định origin, inventory hostname/path, yêu cầu logging | Kiến trúc, SKU, chi phí và chính sách được phê duyệt |
| **Chuẩn bị** | Bật TLS, tạo policy, cấu hình managed rule, giới hạn quyền quản trị | Traffic đi qua WAF; origin không bị bỏ ngỏ |
| **Quan sát** | Dùng Detection khi phù hợp, bật diagnostics, lấy baseline request và lỗi | Log hoạt động, có dữ liệu request hợp lệ |
| **Tuning** | Phân tích false positive, chọn exclusion hẹp, kiểm thử ứng dụng | Các luồng quan trọng không bị ảnh hưởng bất hợp lý |
| **Chặn có kiểm soát** | Chuyển Prevention theo cửa sổ thay đổi, theo dõi cảnh báo | Không tăng mạnh lỗi nghiệp vụ; WAF block theo kỳ vọng |
| **Vận hành** | Rà soát rule set, sự kiện, exception, chứng chỉ và chi phí | Có chủ sở hữu, lịch review và phương án ứng cứu |

Trong giai đoạn rollout, chuẩn bị một rollback cụ thể: ai có quyền đổi policy, thay đổi được phê duyệt ở đâu, cách quay lại cấu hình đã kiểm thử, cách xác nhận traffic phục hồi và cách tránh mở origin công khai trong lúc xử lý.

### Chỉ số đáng theo dõi

- Số request bị block theo thời gian, rule ID và endpoint.
- Tỷ lệ lỗi HTTP 4xx/5xx, đặc biệt trước/sau thay đổi policy.
- Tỷ lệ false positive đã xác minh và thời gian giải quyết.
- Latency p95/p99, backend health và biến động lưu lượng.
- Lưu lượng theo client IP/vị trí địa lý ở mức cần thiết cho điều tra.
- Dung lượng lưu log, retention và chi phí WAF/gateway/edge.

Không tối ưu bằng cách đặt mục tiêu **càng nhiều request bị block càng tốt**. Nhiều block có thể phản ánh tấn công thật, cấu hình quá nhạy hoặc lỗi của ứng dụng. Mục tiêu là giảm rủi ro trong khi duy trì trải nghiệm của người dùng hợp lệ.

## 13. Xử lý sự cố WAF phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Tạo WAF policy thành công nhưng không thấy log/block | Policy chưa associate với đường ingress, traffic đi đường khác hoặc diagnostics chưa bật | Kiểm tra association, DNS/route, request đến WAF và log destination |
| Người dùng thấy 403 sau khi bật Prevention | Managed rule/custom rule chặn hoặc ứng dụng tự trả 403 | So sánh WAF firewall log với access/origin log, correlation ID |
| Một API JSON hoặc upload bị chặn | False positive, body inspection hoặc giới hạn request | Lấy rule ID, kiểm tra payload hợp lệ, tạo exclusion hẹp |
| Dùng Detection nhưng request vẫn bị chặn | Custom rule action, hạn chế ở tầng khác hoặc hành vi riêng của sản phẩm | Xem action thực tế, rule scope, NSG/origin và policy mode |
| WAF log không xuất hiện trong KQL | Diagnostic settings chưa gửi log, chọn sai bảng/category hoặc chưa có dữ liệu | Kiểm tra Log Analytics destination và bảng tương ứng |
| Backend trả 502/504 | Lỗi kết nối origin, health probe, TLS, DNS hoặc firewall | Kiểm tra backend health, origin access logs và network path |
| Khách vẫn truy cập được origin khi bỏ qua hostname WAF | Origin công khai chưa được hạn chế | Cấu hình origin access restriction/Private Link và xác minh nguồn |
| Rule Allow khiến request nguy hiểm đi qua | Ưu tiên hoặc action bỏ qua kiểm tra còn lại | Thu hẹp điều kiện, review thứ tự rule và kiểm thử |
| Sau nâng managed rules xuất hiện nhiều block mới | Tập quy tắc thay đổi hành vi | So sánh log trước/sau, rà soát rule, rollback theo quy trình |
| Website chậm sau thay đổi WAF | Tăng bước xử lý, thay đổi đường đi hoặc vấn đề backend | Theo dõi latency ở edge/gateway và origin, kiểm tra tải/chi phí |

Khi cần khôi phục sự cố sản xuất, đừng lập tức tắt WAF toàn bộ. Hãy xác định policy/rule/phạm vi gây lỗi, cân nhắc tạm thời điều chỉnh hẹp dưới quy trình được duyệt và ghi lại mọi thay đổi.

## 14. Bài thực hành: thiết kế và thử nghiệm WAF theo cách an toàn

Bạn có thể hoàn thành phần lớn bài thực hành này dưới dạng thiết kế và khảo sát Portal, không cần tạo Application Gateway hay Front Door có phát sinh chi phí. Nếu có sandbox và quyền phù hợp, thực hiện phần cấu hình trên ứng dụng **do bạn sở hữu hoặc được phép thử nghiệm**.

### Bối cảnh

Ứng dụng **shop.lab.example** có ba khu vực:

- **/**: website mua sắm công khai.
- **/api/search**: tìm kiếm sản phẩm, có request JSON/query và lưu lượng tương đối lớn.
- **/admin**: trang quản trị yêu cầu đăng nhập, chỉ dùng từ nguồn truy cập được phê duyệt.

Đội phát triển muốn bắt đầu bằng Detection để đo độ chính xác của managed rules, sau đó chuyển sang Prevention. Mọi request đi vào ứng dụng phải qua WAF; backend không được cho phép kết nối trực tiếp từ Internet.

### Phần A: thiết kế WAF policy

Hoàn thiện bảng:

| Thành phần | Cấu hình đề xuất | Lý do |
|---|---|---|
| Ingress | App Gateway WAF_v2 hoặc Front Door theo topology | Đặt WAF đúng trước origin |
| Managed rules | Rule set được hỗ trợ và đã kiểm thử | Chống nhóm rủi ro web phổ biến |
| Mode ban đầu | Detection | Quan sát false positive |
| Mode sau rollout | Prevention | Thực thi chính sách chặn |
| /admin | Custom rule chặn nguồn không được phê duyệt, kết hợp Entra ID/role | Giảm bề mặt tấn công, không thay auth |
| /api/search | Rate limit tùy khả năng hỗ trợ và số liệu thực tế | Giảm lạm dụng, tránh chặn người dùng qua shared NAT |
| Logging | WAF/access diagnostics đến Log Analytics | Điều tra theo action/rule/URI |
| Origin | Hạn chế đường trực tiếp tới backend | Không cho bypass WAF |
| Ngoại lệ | Chỉ tạo sau khi chứng minh false positive | Giữ hiệu lực bảo vệ |

### Phần B: nếu có môi trường lab Azure

1. Chọn subscription và resource group dành riêng cho lab; xác nhận chi phí của gateway/Front Door, log, IP public và các tài nguyên liên quan trước khi tạo.
2. Tạo một ứng dụng web thử nghiệm hoặc dùng backend thử nghiệm đã được phê duyệt.
3. Tạo policy phù hợp với nền tảng và gắn vào ingress xử lý hostname lab.
4. Bật managed rules và chế độ Detection; cấu hình Diagnostic settings tới workspace được cấp quyền.
5. Gửi vài request hợp lệ tới trang chủ, tìm kiếm và đăng nhập; ghi lại status, latency và log.
6. Nếu được phép kiểm thử trong môi trường cô lập, gửi một request **vô hại** có chuỗi trông giống mẫu script vào tham số tìm kiếm:

~~~bash
curl -i "https://shop.lab.example/api/search?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E"
~~~

7. Kiểm tra xem rule được ghi nhận hay không. **Không phải mọi rule set đều nhất thiết bắt request mẫu này**, và request có thể thất bại vì chính ứng dụng hoặc cấu hình khác; không suy luận kết quả chỉ từ HTTP status.
8. Đối chiếu WAF log theo thời gian, URI, rule ID và action. Khi đã hiểu false positive và có kế hoạch rollback, mới thử chế độ Prevention.
9. Gửi request hợp lệ một lần nữa và xác nhận không làm hỏng các luồng nghiệp vụ.
10. Xóa hoặc trả lại cấu hình lab theo kế hoạch, bao gồm WAF policy, gateway/Front Door, origin, public IP và diagnostics phát sinh nếu không còn sử dụng.

Không thử payload tấn công trên website bên ngoài, môi trường production hoặc hệ thống chưa cấp quyền. Dùng tên miền ví dụ và dữ liệu giả, không ghi token/cookie thật vào log hay tài liệu.

### Phần C: kiểm tra yêu cầu thiết kế

| Tình huống | Kỳ vọng |
|---|---|
| Client gửi request hợp lệ tới trang chủ | Được ứng dụng xử lý bình thường |
| Request có mẫu bất thường và managed rule nhận diện trong Detection | Có dấu vết đánh giá WAF, không tự khẳng định bị block |
| Request thuộc rule chặn trong Prevention | Bị thực thi theo action/chính sách tương ứng |
| Người dùng không được ủy quyền truy cập /admin dù request vượt qua WAF | Ứng dụng từ chối vì thiếu quyền |
| Người dùng truy cập trực tiếp origin để né WAF | Bị cơ chế mạng/xác minh nguồn tại origin từ chối |
| API upload hợp lệ có false positive | Có rule ID và phương án exclusion hẹp đã được review |
| WAF log không về workspace | Có quy trình kiểm tra diagnostics, destination và schema |
| Chính sách mới gây lỗi chức năng quan trọng | Có người chịu trách nhiệm và kế hoạch rollback |

### Bài tập tự kiểm tra

1. Vì sao NSG chỉ mở TCP 443 không thể thay WAF kiểm tra HTTP request?
2. Tình huống nào khiến bạn chọn Front Door WAF thay vì Application Gateway WAF?
3. Detection và Prevention khác nhau ra sao? Vì sao không nên bật Prevention ngay khi chưa quan sát?
4. Managed rules khác custom rules ở điểm nào?
5. Vì sao một dòng log matched rule chưa chắc đồng nghĩa request đã bị chặn?
6. Một rule Allow theo **/api/** có thể gây hậu quả gì?
7. Khi Front Door WAF đang bảo vệ website, vì sao cần khóa đường truy cập trực tiếp tới origin?
8. Khi người dùng báo lỗi 403, bạn kiểm tra những loại log nào để biết lỗi do WAF hay ứng dụng?
9. Vì sao exclusion theo đúng trường **articleHtml** an toàn hơn tắt toàn bộ rule set?
10. WAF có thể thay kiểm soát truy cập từng bản ghi của một API SaaS không? Giải thích.

## 15. Checklist trước khi dùng WAF ở production

- [ ] Tất cả hostname/route công khai quan trọng đều đi qua WAF và đúng policy association.
- [ ] Origin không bị truy cập trực tiếp ngoài đường đã kiểm soát; TLS từ client tới ingress và từ ingress tới origin được thiết kế đúng.
- [ ] Chọn đúng SKU/tier và managed rule set được hỗ trợ; thông số request body/upload phù hợp ứng dụng.
- [ ] Managed rules được kiểm thử với các luồng quan trọng, các ngoại lệ có bằng chứng và được giới hạn hẹp.
- [ ] Custom rules có priority/action rõ ràng; rule Allow không vô tình vô hiệu hóa lớp kiểm tra khác.
- [ ] Diagnostics hoạt động; nhóm vận hành có quyền xem log, dashboard và cảnh báo cần thiết.
- [ ] Có baseline về latency, HTTP errors và số block để so sánh trước/sau rollout.
- [ ] Có tài liệu chính sách Detection → Prevention, phương án rollback và chủ sở hữu.
- [ ] Ứng dụng vẫn thực hiện xác thực, ủy quyền, input validation, output encoding và quản lý secret.
- [ ] Đã cân nhắc chi phí gateway/edge, lưu lượng, log và retention; có kế hoạch rà soát định kỳ.

## 16. Tài liệu tham khảo

- [What is Azure Web Application Firewall?](https://learn.microsoft.com/azure/web-application-firewall/overview) — tổng quan nền tảng WAF của Azure.
- [Web Application Firewall on Azure Application Gateway](https://learn.microsoft.com/azure/web-application-firewall/ag/ag-overview) — kiến trúc và khả năng WAF trên Application Gateway.
- [Web Application Firewall on Azure Front Door](https://learn.microsoft.com/azure/web-application-firewall/afds/afds-overview) — WAF tại edge cho Azure Front Door.
- [Application Gateway WAF policies](https://learn.microsoft.com/azure/web-application-firewall/ag/policy-overview) — cấu trúc và phạm vi WAF policy.
- [Application Gateway WAF custom rules](https://learn.microsoft.com/azure/web-application-firewall/ag/custom-waf-rules-overview) — custom rule và điều kiện.
- [Monitor Azure Application Gateway](https://learn.microsoft.com/azure/application-gateway/monitor-application-gateway) — metrics, logs và diagnostic settings.
- [Azure CLI: application-gateway waf-policy](https://learn.microsoft.com/cli/azure/network/application-gateway/waf-policy) — cú pháp CLI để xem và quản lý WAF policy.

**Kết luận:** WAF là một lớp bảo vệ HTTP/HTTPS quan trọng, nhưng hiệu quả phụ thuộc vào vị trí triển khai, cấu hình rule, khả năng quan sát và việc ngăn bypass origin. Hãy dùng WAF như một phần của kiến trúc phòng thủ nhiều lớp, kiểm thử trên lưu lượng đại diện trước khi chặn, giữ ngoại lệ ở phạm vi tối thiểu và luôn duy trì bảo vệ ngay trong ứng dụng.
