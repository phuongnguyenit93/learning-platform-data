# Private Google Access và truy cập Google APIs

Một ứng dụng chạy trên máy ảo **Compute Engine** cần đọc đối tượng trong **Cloud Storage**, gửi log lên **Cloud Logging** hoặc gọi **Secret Manager API**. Để giảm bề mặt tấn công, nhóm vận hành không cấp địa chỉ IP ngoài (*external IP*) cho máy ảo. Vấn đề xuất hiện: làm thế nào máy ảo vẫn gọi được Google APIs qua HTTPS, trong khi mạng VPC được quản lý chặt chẽ?

**Private Google Access (PGA)** giải quyết một phần quan trọng của bài toán này: cho phép các tài nguyên đủ điều kiện trong subnet VPC, điển hình là VM chỉ có địa chỉ IPv4 nội bộ, kết nối tới các Google APIs và dịch vụ được hỗ trợ. PGA gắn với **subnet**, cần phối hợp với **DNS**, **route**, chính sách egress và quyền truy cập ứng dụng. Việc bật PGA không thay thế xác thực, IAM hoặc mọi loại kết nối riêng đến dịch vụ Google Cloud.

Bài học thuộc chương **VPC và định tuyến** của mô-đun **CLOUD_PROVIDERS_GCP**. Nội dung hỗ trợ thiết kế hạ tầng từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu; qua ví dụ triển khai, người học có thể lựa chọn phương án truy cập APIs, bảo vệ tài nguyên, tự động hóa cấu hình và kiểm tra độ tin cậy cùng tác động chi phí.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của Private Google Access khi VM không có external IPv4.
2. Phân biệt PGA với Cloud NAT, Private Service Connect và Private Services Access.
3. Chọn giữa truy cập theo tên miền Google APIs thông thường, `private.googleapis.com` và `restricted.googleapis.com`.
4. Mô tả đường đi của gói tin từ VM qua DNS, route, firewall tới Google API.
5. Bật PGA trên subnet, kiểm tra DNS/route và xác minh kết nối bằng lệnh đọc hoặc thao tác cấu hình có kiểm soát.
6. Chẩn đoán những lỗi phổ biến liên quan tới routing, tên miền, IAM, OAuth scopes và VPC Service Controls.

## 2. Private Google Access thực sự làm gì?

### 2.1. Bối cảnh: VM chỉ có IP nội bộ

Ví dụ một VM có giao diện mạng:

~~~text
Project: retail-prod
VPC:     retail-vpc
Subnet:  app-subnet (asia-southeast1)
VM:      api-worker-01
IP nội bộ: 10.20.10.15
External IPv4: không có
~~~

Ứng dụng trên VM gọi `https://storage.googleapis.com` hoặc một API qua `*.googleapis.com`. Không có external IP không đồng nghĩa VM hoàn toàn bị cấm giao tiếp với dịch vụ Google. Nếu **PGA được bật trên subnet**, đường đi và điều kiện truy cập hợp lệ, VM có thể gửi yêu cầu tới những Google APIs được hỗ trợ mà không phải tự sở hữu external IPv4 hoặc dùng Cloud NAT chỉ cho các API đó.

Trong ngữ cảnh này cần phân biệt:

- **Nguồn truy cập:** VM trong subnet; PGA là cấu hình của subnet chứ không phải một địa chỉ IP gắn riêng lên VM.
- **Đích:** các Google APIs và dịch vụ thuộc phạm vi hỗ trợ, không phải một website Internet bất kỳ.
- **Kết nối:** cần DNS phân giải tên dịch vụ, một route phù hợp tới đích và đường đi không bị chặn bởi egress policy.
- **Quyền:** dịch vụ Google đích vẫn kiểm tra danh tính, token, IAM và các điều kiện của API.

PGA áp dụng chủ yếu cho kết nối **IPv4** của những trường hợp được tài liệu Google Cloud hỗ trợ. Khi thiết kế IPv6, hybrid hoặc các nền tảng serverless, cần đọc riêng hướng dẫn kết nối của môi trường đó; không suy rằng bật cờ trên một subnet sẽ tự giải quyết mọi kiểu kết nối.

### 2.2. Tính năng được bật ở cấp nào?

Private Google Access là thuộc tính của **subnet VPC theo region**. Nếu một VPC có ba subnet, chỉ bật PGA cho `app-subnet` thì không có nghĩa tất cả subnet còn lại được bật.

| Thành phần | Điều PGA thay đổi | Điều PGA không làm |
| --- | --- | --- |
| **Subnet** | Cho phép các VM đủ điều kiện trong subnet tiếp cận Google APIs được hỗ trợ bằng IP nội bộ theo cơ chế PGA. | Không tự tạo subnet, VM hay service account. |
| **VM** | VM không có external IPv4 có thể gọi Google APIs khi mạng được cấu hình đúng. | Không tự cấp IAM role hay OAuth token. |
| **VPC route** | Route đúng cho đích API giúp chuyển gói tin theo next hop được hỗ trợ. | PGA không tự tạo mọi custom route mong muốn. |
| **DNS** | Có thể kết hợp cấu hình DNS riêng để dùng endpoint private/restricted. | Chỉ bật PGA không tự ghi đè mọi tên miền thành `restricted.googleapis.com`. |
| **Firewall / policy** | Cần cho phép traffic thích hợp để kết nối thành công. | PGA không bỏ qua lệnh chặn egress, org policy hay VPC Service Controls. |
| **Chi phí** | Có thể giảm nhu cầu dùng NAT chỉ để truy cập các API hỗ trợ. | Không loại trừ mọi phí dịch vụ, lưu lượng hoặc hạ tầng liên quan. |

### 2.3. Hình dung đường đi yêu cầu

~~~mermaid
flowchart LR
    VM["VM chỉ có internal IPv4"] --> DNS["Phân giải DNS: API hostname"]
    DNS --> IP["Địa chỉ đích Google APIs"]
    VM --> ROUTE["VPC route và egress policy"]
    IP --> ROUTE
    ROUTE --> API["Google API endpoint"]
    SA["Service account / token"] -. "Xác thực" .-> API
    IAM["IAM / các kiểm soát truy cập"] -. "Ủy quyền" .-> API
~~~

Sơ đồ là mô hình logic. DNS giải tên thành địa chỉ đích; VM sau đó gửi gói tin theo route được chọn. **DNS không tự mở mạng, route không tự cấp quyền, IAM không tự tạo kết nối TCP.** Vì vậy một thông báo `403 PERMISSION_DENIED` khác về bản chất với lỗi `Could not resolve host` hay `Connection timed out`.

## 3. Phân biệt PGA với những cơ chế truy cập khác

Các tên có chữ *private* thường gây nhầm lẫn, đặc biệt khi hệ thống đồng thời dùng Cloud SQL, GKE và Cloud Run.

| Cơ chế | Nhu cầu chính | Phạm vi và đặc điểm |
| --- | --- | --- |
| **Private Google Access** | VM không có external IPv4 gọi Google APIs/dịch vụ được hỗ trợ. | Bật trên subnet; kết hợp DNS, route và chính sách mạng. |
| **Cloud NAT** | Workload không có external IPv4 kết nối ra Internet hoặc một số đích ngoài VPC bằng NAT. | Dịch địa chỉ nguồn cho kết nối outbound được hỗ trợ; không tự tạo kết nối inbound và không thay thế IAM. |
| **Private Service Connect (PSC) cho Google APIs** | Truy cập Google APIs qua endpoint nội bộ do VPC cung cấp. | Tạo endpoint phù hợp, DNS và policy; cơ chế và tài nguyên cấu hình khác PGA truyền thống. |
| **Private Services Access** | Kết nối riêng tới các dịch vụ do Google quản lý có hỗ trợ cơ chế này, ví dụ một số cấu hình **Cloud SQL private IP**. | Dùng kết nối dịch vụ/peering và dải địa chỉ IP được phân bổ; không phải bật PGA để gọi API. |
| **VPC Service Controls** | Giảm rủi ro truy xuất dữ liệu ra khỏi ranh giới được bảo vệ đối với dịch vụ hỗ trợ. | Ràng buộc truy cập API theo service perimeter và quy tắc; không phải sản phẩm NAT hay route. |
| **VPN / Interconnect** | Kết nối từ mạng on-premises tới VPC. | Cần thiết kế routing và DNS riêng; chưa mặc nhiên cho phép host on-premises gọi mọi Google API. |

**Ví dụ phân biệt hai đường đi của Cloud SQL:**

1. Chương trình gọi **Cloud SQL Admin API** để xem cấu hình instance: đây là truy cập tới Google API; PGA có thể là một phần của giải pháp mạng.
2. Chương trình mở **kết nối dữ liệu tới cơ sở dữ liệu Cloud SQL bằng private IP**: phải cấu hình cơ chế private connectivity, routing và quyền database tương ứng; chỉ bật PGA trên subnet không đủ để kết nối.

Tương tự, Cloud Run là một dịch vụ serverless có mô hình networking riêng. Một dịch vụ Cloud Run gọi Google API qua đường egress mặc định không đồng nghĩa cần bật PGA như VM. Nếu cấu hình cho traffic đi qua VPC (ví dụ Direct VPC egress hoặc connector theo mô hình được hỗ trợ), cần xem xét đường đi, DNS và quyền riêng cho cấu hình đó.

## 4. Ba lựa chọn tên miền và endpoint Google APIs

### 4.1. Truy cập tên miền API thông thường

Một workload có thể gọi `storage.googleapis.com`, `secretmanager.googleapis.com`, `logging.googleapis.com`... DNS mặc định có thể trả về những địa chỉ IP thuộc Google APIs dùng chung. Với VM không có external IPv4, **Private Google Access** và route phù hợp có thể cho phép các API hỗ trợ nhận được traffic đó.

Trong mô hình thường gặp, VPC có route mặc định `0.0.0.0/0` qua **default internet gateway**. Khi PGA được bật cho subnet, traffic từ VM không có external IPv4 tới Google APIs hỗ trợ có thể dùng route phù hợp này. Tên next hop “internet gateway” **không tự chứng minh** rằng traffic phải đi qua Internet công cộng; đây là next hop logic của Google Cloud. Khả năng kết nối cụ thể vẫn phụ thuộc địa chỉ đích, PGA và quy tắc mạng.

Đối với môi trường muốn kiểm soát chặt đích Google API, nên xem thêm hai VIP được Google cung cấp cho private/restricted access.

### 4.2. `private.googleapis.com`

`private.googleapis.com` sử dụng một tập địa chỉ VIP IPv4:

~~~text
199.36.153.8/30
199.36.153.8
199.36.153.9
199.36.153.10
199.36.153.11
~~~

Khi DNS của mạng được cấu hình để các hostname Google APIs phù hợp trỏ đến VIP này, client kết nối tới những địa chỉ dành cho truy cập Google APIs theo cơ chế private. Đây là lựa chọn cho trường hợp cần truy cập các Google APIs và dịch vụ được hỗ trợ, bao gồm trường hợp API không thuộc tập dịch vụ hỗ trợ VPC Service Controls.

**Private VIP không thay thế quyền truy cập API:** service account vẫn phải có token, role và các quyền tương ứng; request vẫn có thể bị từ chối nếu service perimeter hoặc chính sách dịch vụ không cho phép.

### 4.3. `restricted.googleapis.com`

`restricted.googleapis.com` sử dụng tập VIP IPv4:

~~~text
199.36.153.4/30
199.36.153.4
199.36.153.5
199.36.153.6
199.36.153.7
~~~

Endpoint **restricted** dành cho các API/dịch vụ hỗ trợ **VPC Service Controls**. Nó hữu ích khi thiết kế đường đi Google API theo ranh giới dữ liệu, nhưng không cung cấp cùng tập API với `private.googleapis.com`. Với một API không được hỗ trợ, việc trỏ hostname của nó tới endpoint restricted có thể làm yêu cầu thất bại.

VPC Service Controls phải được **cấu hình service perimeter** nếu muốn thực thi ranh giới truy cập dữ liệu tương ứng. Chỉ dùng địa chỉ `restricted.googleapis.com` không tự tạo perimeter, không cấp IAM và cũng không bảo đảm chống mọi phương thức đưa dữ liệu ra ngoài.

### 4.4. Bảng so sánh lựa chọn endpoint

| Tiêu chí | Hostname mặc định | `private.googleapis.com` | `restricted.googleapis.com` |
| --- | --- | --- | --- |
| Cách sử dụng | Client gọi hostname API bình thường. | DNS hướng hostname API thích hợp tới private VIP. | DNS hướng hostname API hỗ trợ VPC SC tới restricted VIP. |
| Dải VIP của ví dụ | Do DNS của API quyết định. | `199.36.153.8/30` | `199.36.153.4/30` |
| Mục tiêu | Gọi các API hỗ trợ với cấu hình PGA/route phù hợp. | Hướng lưu lượng Google API qua endpoint private được thiết kế. | Giới hạn nhóm API theo phạm vi hỗ trợ VPC Service Controls. |
| Tương thích API | Phụ thuộc dịch vụ và phương án kết nối. | Tập API rộng hơn restricted, theo tài liệu hiện hành. | Chỉ các dịch vụ được hỗ trợ theo danh sách Google công bố. |
| IAM và xác thực | Vẫn cần. | Vẫn cần. | Vẫn cần. |
| Tự cấu hình service perimeter? | Không. | Không. | Không. |

Không nên ép mọi hostname thuộc Google vào một endpoint chỉ vì tên miền trông giống nhau. Các domain như `*.pkg.dev`, `gcr.io`, dịch vụ Google Workspace và endpoint chuyên biệt có thể yêu cầu cấu hình bổ sung hoặc không thuộc phạm vi hỗ trợ mong đợi. Kiểm tra tài liệu của đúng dịch vụ, API và tên miền ứng dụng thực sự gọi.

## 5. Cách DNS và route phối hợp với PGA

### 5.1. Phân giải tên là bước riêng

Giả sử ứng dụng gửi request:

~~~text
GET https://storage.googleapis.com/...
~~~

Trình phân giải DNS tìm địa chỉ IP của `storage.googleapis.com`. Nếu tổ chức tạo **Cloud DNS private zone** cho `googleapis.com.`, có thể cung cấp bản ghi wildcard để hostname phù hợp trở thành CNAME tới `private.googleapis.com.` hoặc `restricted.googleapis.com.`; tên đích của CNAME có các bản ghi A là địa chỉ VIP.

~~~text
storage.googleapis.com.
    -> CNAME private.googleapis.com.
private.googleapis.com.
    -> A 199.36.153.8
    -> A 199.36.153.9
    -> A 199.36.153.10
    -> A 199.36.153.11
~~~

**Wildcard không nhất thiết bao phủ mọi tên:** ví dụ bản ghi `*.googleapis.com.` không phải là một quy tắc bao quát cho `googleapis.com.` chính nó hoặc tên miền không có hậu tố `.googleapis.com`. Nếu đang có zone hoặc DNS policy dành cho domain đó, phải thiết kế sửa đổi và kiểm tra xung đột thay vì tạo thêm zone trùng lặp.

Khi dùng Shared VPC, cần xác định zone được gắn với **VPC network thực tế** mà workload sử dụng, kể cả khi network nằm trong host project. Không suy rằng chỉ cần đặt Cloud DNS private zone trong project ứng dụng thì mọi VM dùng shared network đều tự nhìn thấy zone đó.

### 5.2. Chọn route tới VIP

Sau khi DNS trả về địa chỉ trong `199.36.153.8/30`, VPC phải có đường đi phù hợp cho dải đó. Một thiết kế thường dùng route có destination là tập VIP và next hop **default internet gateway**:

~~~text
Destination: 199.36.153.8/30
Next hop:    default internet gateway
VPC:         retail-vpc
~~~

Nếu VPC vẫn có route mặc định `0.0.0.0/0` hợp lệ qua default internet gateway thì route đó có thể phục vụ kết nối tới VIP. Trong mạng bỏ route mặc định để hạn chế egress, cần tạo route cụ thể tới VIP. Một route cụ thể theo tiền tố đích cũng giúp định tuyến VIP minh bạch hơn.

Google Cloud chọn route theo các quy tắc định tuyến của VPC, bao gồm tính phù hợp của đường đi và độ đặc hiệu của đích; **priority không thay thế hoàn toàn quy tắc so khớp tiền tố**. Đặc biệt, nếu có custom route, policy-based route hoặc mạng hybrid, phải kiểm tra không có đường đi khác chiếm quyền định tuyến ngoài ý muốn.

### 5.3. Egress và DNS policy

Cho phép một đường route không đồng nghĩa gói tin qua được firewall. Nếu tổ chức dùng egress deny mặc định, cần cho phép những đích và protocol cần thiết theo thiết kế, thường là **TCP 443** tới endpoint API và lưu lượng DNS tới trình phân giải được sử dụng. Quy tắc có thể nằm ở VPC firewall, hierarchical firewall policy hoặc lớp kiểm soát khác; không tự cấp dải Internet rộng nếu chỉ cần Google APIs.

Với chính sách chặt, lưu lượng tới Google APIs có thể được giám sát kết hợp từ VPC Flow Logs (nếu bật và trong phạm vi hỗ trợ), Cloud DNS logging, Cloud Audit Logs của dịch vụ và telemetry ứng dụng. Không nên giả định một nguồn log ghi đầy đủ tất cả các request ứng dụng.

## 6. Thực hành cấu hình PGA trên Compute Engine

Ví dụ sau giả định một **project**, VPC và subnet đã tồn tại. Các giá trị `retail-prod`, `retail-vpc`, `app-subnet` và `asia-southeast1` chỉ là mẫu. Những lệnh có chữ `update`, `create` thay đổi tài nguyên thật; chỉ chạy trong môi trường được phép sau khi đánh giá tác động tới các workload đang dùng.

### 6.1. Kiểm tra subnet hiện tại

~~~bash
PROJECT_ID="retail-prod"
NETWORK="retail-vpc"
SUBNET="app-subnet"
REGION="asia-southeast1"

# Đọc cấu hình subnet, không thay đổi tài nguyên.
gcloud compute networks subnets describe "$SUBNET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(name,network,region,ipCidrRange,privateIpGoogleAccess)"
~~~

Trường `privateIpGoogleAccess` phản ánh trạng thái bật/tắt của tính năng trên subnet IPv4. Nếu dùng Shared VPC, người quản lý cần truy vấn và cập nhật subnet trong **host project** chứ không lấy nhầm một project chạy workload.

### 6.2. Bật Private Google Access

~~~bash
# Thao tác thay đổi cấu hình của subnet hiện có.
gcloud compute networks subnets update "$SUBNET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --enable-private-ip-google-access

# Đọc lại và xác nhận trạng thái sau thay đổi.
gcloud compute networks subnets describe "$SUBNET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="value(privateIpGoogleAccess)"
~~~

Kỳ vọng giá trị là `True` hoặc biểu diễn tương đương của CLI. Thao tác này không thêm external IP cho VM, không tự tạo Cloud NAT và không cấp role cho service account.

### 6.3. Kiểm tra route trước khi đổi DNS

~~~bash
# Xem cấu trúc route và next hop trong project.
gcloud compute routes list \
  --project="$PROJECT_ID" \
  --format="table(name,network.basename(),destRange,priority,nextHopGateway)"
~~~

Với một VPC dùng route mặc định qua default internet gateway, hãy đối chiếu route đó với chính sách egress hiện hành. Nếu tổ chức đã bỏ route mặc định và chọn truy cập bằng `private.googleapis.com`, có thể cần tạo route chỉ tới VIP:

~~~bash
# Thao tác ghi: chỉ dùng nếu kiến trúc đã xác nhận cần route riêng.
gcloud compute routes create googleapis-private-vip \
  --project="$PROJECT_ID" \
  --network="$NETWORK" \
  --destination-range="199.36.153.8/30" \
  --next-hop-gateway="default-internet-gateway" \
  --priority=800
~~~

Nếu tổ chức dùng `restricted.googleapis.com`, dải đích tương ứng là `199.36.153.4/30`. Cấu hình route phải tương thích với các chính sách, route hiện có và endpoint thực sự chọn; không thêm cả hai dải chỉ vì muốn “an toàn hơn”.

### 6.4. Cấu hình DNS minh họa cho private VIP

Nếu muốn các hostname API thuộc `*.googleapis.com` dùng private VIP, một phương án là tạo **Cloud DNS private zone** trên VPC phù hợp:

~~~bash
# Ví dụ Bash: CHỈ thực thi khi chưa có zone/policy xung đột.
gcloud dns managed-zones create private-googleapis-zone \
  --project="$PROJECT_ID" \
  --dns-name="googleapis.com." \
  --description="Private resolution for Google APIs" \
  --visibility="private" \
  --networks="$NETWORK"

# A records cho tên đích private.googleapis.com.
gcloud dns record-sets create private.googleapis.com. \
  --project="$PROJECT_ID" \
  --zone="private-googleapis-zone" \
  --type="A" \
  --ttl=300 \
  --rrdatas="199.36.153.8,199.36.153.9,199.36.153.10,199.36.153.11"

# Chuyển các hostname con phù hợp sang private VIP.
gcloud dns record-sets create '*.googleapis.com.' \
  --project="$PROJECT_ID" \
  --zone="private-googleapis-zone" \
  --type="CNAME" \
  --ttl=300 \
  --rrdatas="private.googleapis.com."
~~~

Ví dụ trên minh họa cách cấu hình **từ đầu** trong môi trường được phép. Nếu VPC có DNS private zone `googleapis.com.` từ trước, phải cập nhật zone hiện hữu theo quy trình thay đổi. Nếu cần endpoint **restricted**, thay record đích thành `restricted.googleapis.com.` và tập A record `199.36.153.4` đến `199.36.153.7`, đồng thời xác nhận từng API trong ứng dụng được hỗ trợ.

Một số domain Google API, artifact registry hoặc endpoint khác cần bản ghi DNS và kiểm tra hỗ trợ riêng. Không coi wildcard này là giải pháp bao phủ mọi dịch vụ Google Cloud.

### 6.5. Xác minh trên VM không có external IP

Trên chính VM ở subnet đã bật PGA, kiểm tra theo thứ tự:

~~~bash
# Xem hostname API được phân giải tới IP nào.
nslookup storage.googleapis.com

# Kiểm tra kết nối HTTPS tới endpoint.
curl -I --connect-timeout 5 --max-time 15 \
  https://storage.googleapis.com/
~~~

Nếu đang dùng private VIP, bản ghi DNS cần phân giải về `199.36.153.8`–`199.36.153.11` qua CNAME hoặc cơ chế tương đương. Nếu endpoint trả mã `400`, `401` hoặc `403` qua HTTPS, có thể xem đó là dấu hiệu **DNS, TCP và TLS đã hoạt động tới mức nhận phản hồi HTTP**; nó không chứng minh người gọi có đủ quyền dùng tài nguyên. Để xác thực nghiệp vụ, cần gọi API thật bằng danh tính hợp lệ và kiểm tra quyền IAM cụ thể.

Nếu mạng sử dụng `restricted.googleapis.com`, kết quả DNS cần phản ánh dải `199.36.153.4`–`199.36.153.7`. Với DNS mặc định, không đòi hỏi IP phải nằm trong hai dải VIP trên; cách kiểm chứng phải tương ứng phương án kết nối đã chọn.

## 7. IAM, token và VPC Service Controls: những lớp bắt buộc

### 7.1. PGA không thay thế xác thực

Một ứng dụng VM thường nên sử dụng **service account gắn với workload** và cơ chế **Application Default Credentials (ADC)** phù hợp, tránh ghi khóa JSON dài hạn vào code hoặc image.

Quy trình logic:

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng trên VM
    participant M as Metadata service / credentials
    participant G as Google API
    A->>M: Lấy token theo danh tính workload
    M-->>A: Token phù hợp
    A->>G: HTTPS request + token
    G->>G: Kiểm tra token, IAM và policy
    G-->>A: Kết quả hoặc lỗi 401/403
~~~

Ví dụ VM đọc một object trong Cloud Storage phải có **quyền đọc object** theo IAM policy phù hợp. Việc VM kết nối được tới `storage.googleapis.com` chỉ giải quyết lớp mạng. Với VM Compute Engine, cấu hình **OAuth access scopes** còn có thể giới hạn yêu cầu API bên cạnh IAM; khi troubleshoot cần xem cả scope và danh tính sử dụng thật.

### 7.2. Restricted VIP và perimeter

Trong hệ thống chứa dữ liệu nhạy cảm, nhóm bảo mật có thể chọn `restricted.googleapis.com` kết hợp **VPC Service Controls** để kiểm soát truy cập các dịch vụ hỗ trợ theo service perimeter. Cần đánh giá:

1. Các dự án và tài nguyên nào thuộc perimeter.
2. API nào được VPC Service Controls hỗ trợ và có nằm trong danh sách dịch vụ được bảo vệ hay không.
3. Các đường truy cập vào/ra perimeter hợp lệ, bao gồm CI/CD, workload và quản trị viên.
4. DNS, route, egress policy có đưa đúng traffic tới endpoint đã chọn hay không.
5. Logging và quy trình xử lý truy cập bị từ chối.

Không dùng restricted VIP để thay cho quyền IAM tối thiểu hoặc chính sách kiểm soát rò rỉ dữ liệu khác. Một thiết kế sai DNS có thể làm dịch vụ phụ trợ không gọi được API trước cả khi xem xét chính sách perimeter.

### 7.3. Những điểm cần nhớ với GKE và Cloud Run

- **GKE private nodes** thường là VM/node không có external IP; khi node hoặc workload cần gọi Google APIs qua đường mạng tương ứng, cần đối chiếu PGA, DNS, route và điều kiện của cụm. Xác thực workload nên dùng cơ chế danh tính được GKE hỗ trợ, ví dụ Workload Identity Federation for GKE khi thích hợp.
- **GKE cluster control plane** có cơ chế networking, xác thực và truy cập API riêng; không suy rằng PGA cho subnet node tự mở mọi kết nối tới control plane.
- **Cloud Run** có đường egress mặc định và tùy chọn định tuyến qua VPC. Chỉ xem xét PGA và route tương ứng với lưu lượng thực sự đi từ VPC của workload; kiểm tra chi tiết Direct VPC egress/connector, chế độ route và IAM.
- **Cloud SQL** có cả Admin API và kết nối giao thức database. Việc dùng PGA để gọi Admin API không thay thế Cloud SQL private IP, quyền kết nối, database credentials, firewall hay việc lựa chọn Cloud SQL Auth Proxy/connectors.

## 8. Thiết kế thực tế cho hệ thống bán hàng

Giả sử một nhóm có hệ thống đặt hàng chạy trên Compute Engine và Cloud Run; dữ liệu đơn hàng nằm ở Cloud SQL, ảnh sản phẩm trên Cloud Storage, một phần xử lý bất đồng bộ chạy ở GKE. Tổ chức yêu cầu **VM xử lý đơn hàng không có external IPv4** và chỉ truy cập các API cần thiết.

### 8.1. Bài toán và phương án

| Nhu cầu | Quyết định thiết kế | Cách kiểm tra |
| --- | --- | --- |
| VM gọi Cloud Storage API | Bật PGA trên subnet chứa VM; chọn DNS/route đúng với endpoint API. | DNS, HTTPS và đọc thử object bằng danh tính hạn chế. |
| VM ghi log hoặc đọc Secret Manager | Đối chiếu API/dịch vụ hỗ trợ; cấp IAM cho service account. | Kiểm tra token, permission và kết quả API. |
| VM gọi dịch vụ Internet của đối tác | PGA không giải quyết; cân nhắc Cloud NAT hoặc phương án egress được quản lý. | Kiểm tra route, NAT và quy tắc egress. |
| Cloud SQL sử dụng private IP | Thiết kế private connectivity cho database riêng. | Kiểm tra DNS/IP, đường kết nối, database credentials. |
| GKE nodes không có external IP | Đối chiếu subnet PGA, DNS, đường egress và identity. | Kiểm thử từ node/pod theo cách truy cập thực tế. |
| Dữ liệu cần service perimeter | Đánh giá restricted VIP + VPC Service Controls nếu API hỗ trợ. | Kiểm tra danh sách dịch vụ, ingress/egress policy và logs từ chối. |
| Cloud Run truy cập Google API | Xác định traffic đi theo đường egress mặc định hay VPC, sau đó thiết kế mạng tương ứng. | Kiểm thử từ revision runtime bằng đúng service account. |

### 8.2. Kiến trúc logic

~~~mermaid
flowchart TB
    subgraph V["VPC retail-vpc"]
        S["Subnet app-subnet: PGA bật"]
        VM["Compute Engine VM: internal IP"]
        S --> VM
        DNS["Cloud DNS private zone (tùy chọn)"]
        ROUTE["Route tới Google API VIP"]
        VM --> DNS
        VM --> ROUTE
    end
    ROUTE --> API["Google APIs: Storage / Logging / Secret Manager"]
    VM --> DB["Cloud SQL private IP qua cơ chế private connectivity"]
    VM --> NAT["Cloud NAT nếu cần đi Internet khác"]
    IAM["Service accounts + IAM"] -. "Quyền truy cập" .-> API
    PER["VPC Service Controls nếu áp dụng"] -. "Perimeter" .-> API
~~~

Không phải mọi mũi tên trong sơ đồ biểu diễn cùng một giao thức hoặc cùng cách định tuyến. Cloud SQL private IP, Google APIs VIP và Internet egress là **ba đường kết nối khác nhau**, có chính sách riêng.

### 8.3. Luồng triển khai từng bước

1. **Kiểm kê thực tế:** xác định VM, subnet/region, VPC, service accounts, API hostnames và những project cần truy cập.
2. **Xác định nhu cầu egress:** tách Google APIs được hỗ trợ, Internet đối tác, database private IP và các endpoint đặc thù.
3. **Chọn endpoint:** mặc định, private VIP hay restricted VIP dựa trên yêu cầu bảo mật và danh sách API tương thích.
4. **Thiết kế DNS và route:** bao gồm Shared VPC, Cloud DNS và ngoại lệ mạng hiện hữu; tránh cấu hình chồng chéo.
5. **Bật PGA trên subnet thích hợp**, kiểm tra trạng thái trước và sau.
6. **Cấp IAM tối thiểu** cho workload; kiểm tra OAuth scopes của VM nếu liên quan.
7. **Kiểm thử từ đúng môi trường**: DNS, TLS, API call có xác thực, đường đi database và Internet đối tác.
8. **Quan sát và vận hành:** giám sát lỗi DNS, timeout, 401/403, quota, route drift và các thay đổi firewall/policy.
9. **Quản lý bằng IaC và review:** chuẩn hóa cấu hình subnet, DNS, route và quyền để có thể tái tạo, đánh giá tác động khi thay đổi.

Không dùng thành công của `curl` tới một API để khẳng định mọi dịch vụ trong hệ thống đã truy cập được. Mỗi hostname có thể có cách DNS, API, quyền và VPC SC khác nhau.

## 9. Khắc phục sự cố có phương pháp

### 9.1. Bảng phân loại lỗi

| Triệu chứng | Lớp cần kiểm tra trước | Khả năng xảy ra | Bước xác minh |
| --- | --- | --- | --- |
| `Could not resolve host` | DNS | Sai private zone, resolver, CNAME hoặc domain không được xử lý. | `nslookup`/cấu hình Cloud DNS từ chính VM. |
| DNS ra IP khác dự kiến | DNS/endpoint | Chưa áp dụng zone, nhiều view DNS, chưa đổi sang private/restricted VIP. | Kiểm tra CNAME và A records, mạng gắn với zone. |
| TCP timeout | Route/firewall/egress | Subnet chưa bật PGA, route sai, egress deny hoặc đường đi không hỗ trợ. | Xem `privateIpGoogleAccess`, VPC routes, firewall/hierarchical policies. |
| TLS hoặc hostname verification lỗi | TLS/proxy/DNS | Dùng IP thay hostname trong TLS, proxy tùy chỉnh hoặc chứng chỉ không đúng. | Truy cập qua hostname chuẩn và kiểm tra proxy/trust chain. |
| HTTP `401 UNAUTHENTICATED` | Xác thực | Không có token hoặc token không hợp lệ. | Kiểm tra ADC, runtime identity và cách gọi API. |
| HTTP `403 PERMISSION_DENIED` | IAM/scopes/policy | Thiếu role, OAuth scopes giới hạn, VPC SC hoặc policy đích từ chối. | Đối chiếu principal, permission, scopes, logs từ chối. |
| API qua restricted VIP không hoạt động | Khả năng hỗ trợ endpoint | API không thuộc tập hỗ trợ VPC Service Controls. | Kiểm tra danh sách hỗ trợ và chọn endpoint phù hợp. |
| Internet đối tác không truy cập được | Egress Internet | PGA không cung cấp truy cập mọi website ngoài Google APIs. | Xem Cloud NAT, route egress và policy. |
| Cloud SQL private IP không kết nối | Private connectivity/database | Nhầm Admin API với đường kết nối database. | Kiểm tra kết nối riêng, IP, firewall, database auth. |

Một lỗi có thể xuất phát từ nhiều lớp cùng lúc. Cách kiểm tra ít tốn công nhất là đi từ **hostname → IP → route → TCP/TLS → authentication → authorization → nghiệp vụ**.

### 9.2. Checklist lệnh đọc

~~~bash
# Từ máy quản trị có quyền trên project chứa subnet.
gcloud compute networks subnets describe app-subnet \
  --project=retail-prod \
  --region=asia-southeast1 \
  --format="yaml(name,network,privateIpGoogleAccess)"

gcloud compute routes list \
  --project=retail-prod \
  --format="table(name,destRange,nextHopGateway,priority)"

# Nếu có cấu hình Cloud DNS private zone trong project này.
gcloud dns managed-zones describe private-googleapis-zone \
  --project=retail-prod

gcloud dns record-sets list \
  --project=retail-prod \
  --zone=private-googleapis-zone
~~~

Lệnh Cloud DNS sẽ báo không tìm thấy nếu môi trường chọn DNS mặc định hoặc zone nằm ở project khác; điều đó chưa chắc là lỗi. Trong Shared VPC, kiểm tra đúng host project và VPC. Nếu project có nhiều route hoặc nhiều subnet, cần xác định chúng có thực sự nằm trên đường đi của VM cụ thể.

### 9.3. Tránh ba kết luận sai

**“DNS đã ra `199.36.153.8` thì chắc chắn gọi được API.”** Chưa đủ. Phải có route, egress policy, PGA/thiết kế kết nối hỗ trợ và HTTPS thành công.

**“HTTP 403 chứng minh PGA không hoạt động.”** Chưa chính xác. HTTP 403 có nghĩa request đã đến một thành phần HTTP có khả năng phản hồi; cần đọc nội dung lỗi, danh tính, quyền và VPC Service Controls.

**“Bật Cloud NAT thì đương nhiên bật PGA.”** Không. Cloud NAT và PGA là cấu hình khác nhau. Một workload có thể dùng NAT cho Internet đối tác và PGA hoặc PSC cho Google APIs.

## 10. Bảo mật, vận hành và chi phí

### 10.1. Bảo vệ dữ liệu theo nhiều lớp

Một cấu hình production có thể cần:

- Không cấp external IP cho VM xử lý dữ liệu nhạy cảm khi không cần thiết.
- Bật PGA trên subnet dùng Google APIs, hoặc chọn endpoint PSC/thiết kế thích hợp.
- Đặt DNS, routes và egress policy rõ ràng; hạn chế các đường egress không thuộc nhu cầu.
- Dùng service account riêng cho workload, IAM theo nguyên tắc quyền tối thiểu, không nhúng khóa bí mật vào code.
- Dùng VPC Service Controls khi có yêu cầu perimeter và dịch vụ hỗ trợ; kiểm tra egress/ingress được phép.
- Quan sát lưu lượng và lỗi theo dữ liệu thực tế, xác định người chịu trách nhiệm khi thay đổi subnet/firewall.

Private Google Access **không phải một tường lửa và không bảo đảm chống rò rỉ dữ liệu** nếu ứng dụng còn các đường truyền khác hoặc IAM quá rộng. Bảo vệ dữ liệu là bài toán phối hợp giữa danh tính, mạng, policy, mã hóa và ứng dụng.

### 10.2. Độ tin cậy và khả năng vận hành

Các thay đổi tưởng nhỏ như tạo DNS private zone mới, xóa route mặc định hoặc áp dụng egress deny có thể làm nhiều VM/GKE workloads cùng mất khả năng gọi APIs. Để giảm rủi ro:

1. Lưu cấu hình DNS, route và subnet trong IaC khi tổ chức có quy trình đó.
2. Thử nghiệm trên subnet hoặc môi trường nonproduction tương đồng.
3. Kiểm tra từng hostname thực sự dùng, không chỉ một endpoint đại diện.
4. Giám sát tỷ lệ lỗi API, độ trễ, quota và các sự kiện thay đổi hạ tầng.
5. Xác định cách rollback DNS/route, bảo đảm không vô tình mở lại Internet egress ngoài ý muốn.

Đánh giá SLO của ứng dụng từ thao tác người dùng thực tế. VM gọi được một Google API không chứng minh tất cả chức năng liên quan Cloud Storage, Cloud SQL, GKE và Cloud Run vẫn đáp ứng SLO.

### 10.3. Tác động chi phí

PGA có thể giúp tránh yêu cầu triển khai Cloud NAT **chỉ nhằm truy cập một số Google APIs** từ VM không có external IP. Tuy nhiên lựa chọn cuối cùng còn phụ thuộc:

- Lưu lượng tới Internet bên thứ ba có cần Cloud NAT hay phương án khác không.
- Phí dịch vụ Google Cloud đích và dữ liệu truyền giữa các vùng/đường kết nối theo bảng giá hiện hành.
- Chi phí Cloud Logging, Cloud DNS, giám sát, lưu trữ audit và quản trị chính sách nếu áp dụng.
- Công sức vận hành DNS, policy, routes và các cấu hình đặc thù.

Không kết luận “PGA miễn phí cho toàn bộ traffic” hoặc “có PGA nên chi phí egress bằng 0”. Khi đưa vào kiến trúc thật, so sánh chi phí bằng dữ liệu Billing và thông tin giá có hiệu lực.

## 11. Bài tập thực hành

### Bài 1 — Phân loại phương án

Cho bốn nhu cầu:

1. VM không có external IP cần gọi Secret Manager API.
2. VM không có external IP cần truy cập một API thanh toán bên thứ ba.
3. Ứng dụng cần kết nối Cloud SQL bằng private IP.
4. Workload thuộc service perimeter cần gọi một Google API hỗ trợ VPC Service Controls.

**Đáp án định hướng:** (1) xem PGA/PSC và IAM; (2) xem egress Internet như Cloud NAT; (3) cấu hình private connectivity tới Cloud SQL; (4) đánh giá restricted VIP + VPC Service Controls cùng IAM. Mỗi bài toán cần route, DNS và điều kiện dịch vụ cụ thể.

### Bài 2 — Đọc cấu hình

Chạy lệnh đọc với đúng project và region:

~~~bash
gcloud compute networks subnets describe app-subnet \
  --project=retail-prod \
  --region=asia-southeast1 \
  --format="value(privateIpGoogleAccess)"
~~~

Nếu kết quả là `False`, hãy giải thích vì sao một VM không có external IPv4 trong subnet đó có thể không gọi được Google API bằng đường PGA, và cần kiểm tra thêm điều kiện gì trước khi bật cờ.

### Bài 3 — So sánh DNS

Hai môi trường trả về:

~~~text
Môi trường A: storage.googleapis.com -> 199.36.153.8
Môi trường B: storage.googleapis.com -> 199.36.153.4
~~~

**Câu hỏi:** Môi trường nào có khả năng dùng private VIP, môi trường nào dùng restricted VIP? Khi chọn môi trường B, cần kiểm tra API hỗ trợ VPC Service Controls và perimeter như thế nào? Vì sao một bản ghi DNS chưa chứng minh request đã được ủy quyền?

### Bài 4 — Phân tích lỗi 403

`curl` đến một Google API đã nhận phản hồi HTTPS nhưng ứng dụng vẫn báo `403`. Hãy nêu ít nhất bốn bước: xác định danh tính/token, kiểm tra IAM permission, kiểm tra OAuth scopes nếu chạy trên VM, kiểm tra VPC Service Controls và đọc error details. Không cấp quyền Owner/Editor để “thử cho chạy được”.

### Bài 5 — Thiết kế mạng có egress giới hạn

Một VM cần gọi Cloud Storage và một website của đối tác, trong khi VPC đã xóa default route. Hãy đề xuất route, DNS, PGA/PSC và Cloud NAT (nếu dùng) theo đúng hai nhóm đích. Giải thích vì sao route tới `199.36.153.8/30` không tự tạo đường đi hợp lệ tới IP của website đối tác.

## 12. Ghi nhớ và tài liệu chính thức

| Câu hỏi | Điểm cần nhớ |
| --- | --- |
| PGA dành cho ai? | Trường hợp điển hình là VM chỉ có internal IPv4 trong subnet bật PGA, cần gọi Google APIs được hỗ trợ. |
| Bật ở đâu? | Thuộc tính của **subnet**, không phải role IAM hay external IP của VM. |
| DNS để làm gì? | Xác định API hostname trỏ tới IP mặc định, private VIP hoặc restricted VIP. |
| Route để làm gì? | Đưa gói tin tới địa chỉ API qua next hop hợp lệ; cần xem firewall/egress. |
| `private.googleapis.com` khác `restricted.googleapis.com` thế nào? | Private VIP phục vụ tập Google APIs rộng hơn; restricted VIP dành cho API hỗ trợ VPC Service Controls. |
| PGA có thay Cloud NAT không? | Chỉ trong phạm vi truy cập Google APIs được hỗ trợ; Internet đối tác là bài toán egress khác. |
| PGA có cấp quyền API không? | Không; authentication, IAM, OAuth scopes và service perimeter vẫn áp dụng. |
| Đã có PGA thì Cloud SQL private IP kết nối được chưa? | Chưa; đường tới database qua private connectivity là bài toán khác. |

Khi làm việc với hạ tầng thực, cần kiểm tra tài liệu chính thức vì dịch vụ được hỗ trợ, endpoint, DNS và cơ chế mạng có thể thay đổi:

- [Private Google Access overview](https://cloud.google.com/vpc/docs/private-google-access)
- [Configure Private Google Access](https://cloud.google.com/vpc/docs/configure-private-google-access)
- [Private Service Connect for Google APIs](https://cloud.google.com/vpc/docs/private-service-connect)
- [Private services access](https://cloud.google.com/vpc/docs/private-services-access)
- [VPC Service Controls overview](https://cloud.google.com/vpc-service-controls/docs/overview)
- [Supported products for VPC Service Controls](https://cloud.google.com/vpc-service-controls/docs/supported-products)
- [Cloud NAT overview](https://cloud.google.com/nat/docs/overview)
- [Cloud DNS overview](https://cloud.google.com/dns/docs/overview)

Một kết nối Google API thành công cần **đúng subnet, đúng địa chỉ đích, đúng route, đúng egress và đúng danh tính**. Khi phân tách rõ những lớp đó, bạn có thể thiết kế VM không cần external IP mà vẫn thực thi tác vụ trên Google Cloud, kiểm soát truy cập dữ liệu và xử lý sự cố mạng có phương pháp.
