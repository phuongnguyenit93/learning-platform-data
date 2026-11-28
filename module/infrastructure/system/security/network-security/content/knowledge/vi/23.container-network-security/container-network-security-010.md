# DNS resolution bên trong container

**DNS resolution bên trong container** là quá trình một ứng dụng chạy trong container chuyển tên miền hoặc tên dịch vụ thành địa chỉ mạng hoặc những bản ghi DNS khác để thiết lập kết nối. Trong môi trường container, quy trình này không đơn giản là “container dùng DNS giống máy host”: **network namespace, file cấu hình resolver, runtime container, Docker network, Kubernetes DNS, dịch vụ phân giải của cloud và chính sách mạng** đều có thể quyết định yêu cầu DNS đi đâu và nhận kết quả nào.

Ví dụ một ứng dụng trong Kubernetes gọi **orders-api.payments.svc.cluster.local**. Pod có thể gửi truy vấn qua DNS Service của cluster tới CoreDNS, nhận IP Service rồi kết nối tới backend qua mạng do CNI và kube-proxy hoặc dataplane tương đương quản lý. Nếu DNS trả đúng địa chỉ nhưng NetworkPolicy chặn cổng ứng dụng, kết nối vẫn thất bại. Nếu API được truy cập qua mạng nhưng client không xác minh TLS, kết quả DNS đúng cũng **không chứng minh máy chủ đã được xác thực**.

Trong chương **Bảo mật mạng container** thuộc module **SECURITY_NETWORK_SECURITY**, hiểu DNS là nền tảng để xây dựng **phân đoạn mạng, egress control, TLS/mTLS, bảo vệ DNS, giám sát IDS/IPS, chính sách cloud và kiến trúc truy cập dịch vụ an toàn**. Bài học tập trung vào cơ chế phân giải tên, điểm tin cậy, rủi ro bảo mật và phương pháp kiểm chứng bằng dữ liệu thực tế.

> **Nguyên tắc trọng tâm:** DNS giúp **tìm địa chỉ của một tên**, không tự **xác thực máy chủ**, không tự **cấp quyền truy cập**, và không bảo đảm gói tin được phép đi qua firewall. Một hệ thống an toàn phải kiểm tra riêng **kết quả DNS, đường mạng, danh tính TLS/service và quyền ứng dụng**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích quá trình từ **application resolver → /etc/hosts, NSS và /etc/resolv.conf → DNS server → IP/record** ở mức phù hợp hệ điều hành.
2. Phân biệt **DNS của host**, DNS do **Docker runtime**, **Docker embedded DNS**, **Kubernetes CoreDNS** và DNS resolver của VPC/VNet cloud cung cấp.
3. Hiểu phạm vi network namespace: **127.0.0.1 trong container** không mặc nhiên là host hoặc DNS server trên node.
4. Giải thích tên **Docker Compose services**, Kubernetes **Service DNS**, **Pod DNS**, headless Service và sự khác biệt giữa tên logic với IP động.
5. Phân tích **dnsPolicy, dnsConfig, search domains và ndots** và các hệ quả của việc phân giải tên ngắn.
6. Phân biệt **ClusterIP, DNS resolution, endpoint discovery, routing và kết nối TCP/UDP**.
7. Thiết kế **NetworkPolicy cho DNS egress**, kiểm soát DNS ngoài cluster, hạn chế resolver bypass và hiểu giới hạn lọc theo FQDN.
8. Nhận biết rủi ro **DNS spoofing/poisoning, search-domain leakage, DNS tunneling, rebinding và độc hại qua service discovery** ở mức phòng vệ.
9. Khoanh vùng lỗi bằng **getent, nslookup, dig, resolv.conf, logs, metrics, flow logs** trong môi trường được phép.
10. Xây dựng kiểm thử positive/negative, chính sách vận hành, quan sát và runbook khi DNS gặp sự cố trong cụm container.

## 2. DNS và kết nối mạng là hai hoạt động khác nhau

Giả sử một container cần kết nối **https://billing.internal.example.test**. Tối thiểu có các bước logic:

1. Ứng dụng lấy hostname từ URL hoặc cấu hình đã xác minh.
2. Resolver tìm địa chỉ IP cho hostname, có thể xét **/etc/hosts**, cache và DNS.
3. Resolver trả **A (IPv4)** hoặc **AAAA (IPv6)** tùy yêu cầu và dữ liệu có sẵn.
4. Client chọn địa chỉ và thiết lập kết nối mạng tới port dịch vụ.
5. Firewall/NetworkPolicy/route phải cho luồng đó đi qua.
6. Nếu dùng TLS, client xác minh **chứng thư và danh tính server** theo tên dịch vụ dự kiến.
7. API kiểm tra **authentication/authorization** đối với thao tác và dữ liệu.

~~~mermaid
flowchart TD
    APP["Application trong container"] --> NAME["Tên: billing.internal.example.test"]
    NAME --> RES["Name resolution: hosts/NSS/cache/DNS"]
    RES --> ADDR["A/AAAA hoặc lỗi DNS"]
    ADDR --> NET["Route, CNI, NAT, NetworkPolicy, firewall"]
    NET --> TLS["TLS server identity / mTLS nếu áp dụng"]
    TLS --> AUTH["API authentication và authorization"]
    AUTH --> DONE{"Request được chấp nhận?"}
    DONE -->|Có| OK["Thực hiện nghiệp vụ"]
    DONE -->|Không| DENY["Từ chối và ghi nhận lý do"]
~~~

**Phân giải DNS thành công không chứng minh kết nối TCP thành công.** Ngược lại, gọi trực tiếp IP có thể kết nối mạng thành công nhưng bỏ qua một số kiểm tra danh tính được thiết kế theo hostname hoặc phụ thuộc cấu hình TLS/SNI.

### 2.1. Những khái niệm cơ bản

| Khái niệm | Vai trò | Không nên hiểu nhầm |
| --- | --- | --- |
| **Resolver** | Thành phần thư viện/hệ thống tìm dữ liệu tên miền cho ứng dụng | Không nhất thiết là DNS server riêng |
| **Stub resolver** | Bộ phận phía client thường gửi yêu cầu tới recursive resolver | Không tự là authoritative DNS |
| **Recursive resolver** | Phân giải/truy vấn hoặc forward để tìm câu trả lời, có thể cache | Không tự được ứng dụng tin cho authentication |
| **Authoritative DNS** | Nguồn bản ghi có thẩm quyền cho một vùng tên | Không quyết định quyền truy cập API |
| **A / AAAA** | Ánh xạ hostname tới địa chỉ IPv4 / IPv6 | Không tự là chứng thư server |
| **CNAME** | Tên bí danh trỏ sang tên khác | Không tự mở kết nối đến tên đích |
| **SRV** | Gợi ý service, protocol, hostname và port theo định dạng bản ghi | Không phải API authorization |
| **NXDOMAIN** | Tên được truy vấn không tồn tại theo phản hồi DNS | Khác timeout hoặc SERVFAIL |
| **SERVFAIL** | Server DNS không xử lý truy vấn thành công | Không đồng nghĩa tên không tồn tại |
| **TTL** | Thời gian cache dữ liệu DNS theo chính sách resolver | Không bảo đảm container đổi endpoint ngay |

### 2.2. Vì sao gọi IP trực tiếp có thể nguy hiểm?

Một client có thể được cấu hình yêu cầu **api.example.test** và kiểm tra chứng thư hợp lệ cho tên này. Nếu thay URL thành địa chỉ IP tĩnh, nó có thể gặp **TLS hostname mismatch**; nếu kỹ sư tắt certificate verification để “chạy được”, hệ thống mất một phần cơ chế xác thực server. Cách đúng là sửa DNS/endpoint và cấu hình TLS theo danh tính được phê duyệt.

## 3. DNS nằm trong chuỗi xử lý của ứng dụng Linux

Không phải mọi ứng dụng đều gọi DNS theo cách giống nhau. Một số dùng **getaddrinfo()** hoặc cơ chế tương đương trong libc; một số dùng runtime resolver riêng, HTTP client, caching library hoặc DNS client trực tiếp.

### 3.1. /etc/hosts

File **/etc/hosts** cung cấp ánh xạ tên → địa chỉ tĩnh hoặc do runtime/node quản lý. Ví dụ trong một container giả lập:

~~~text
127.0.0.1       localhost
::1             localhost
10.60.10.11     legacy-api.internal.example.test
~~~

Thứ tự xem **hosts** và DNS có thể do **NSS/nsswitch.conf**, thư viện resolver và môi trường quyết định. Không mặc định mọi ngôn ngữ/runtime đều thực hiện cùng một trình tự.

**Không nên dùng /etc/hosts làm service discovery động cho các workloads thường xuyên scale hoặc thay IP**. Bản ghi tĩnh có thể trở nên cũ và không tự bám theo EndpointSlice hoặc Docker network membership.

### 3.2. /etc/nsswitch.conf

Trong các hệ thống dùng glibc và NSS, cấu hình như:

~~~text
hosts: files dns
~~~

có thể chỉ rằng quá trình phân giải tên lần lượt xét file và DNS theo quy tắc NSS. Những container tối giản dùng **musl**, runtime Go hoặc resolver tùy biến có thể hành xử khác. **Không kết luận toàn bộ hành vi phân giải chỉ từ một dòng nsswitch.conf** nếu ứng dụng thực tế không sử dụng cùng resolver.

### 3.3. /etc/resolv.conf

Đây là file cấu hình resolver phổ biến trên Linux. Ví dụ mang tính minh họa:

~~~text
nameserver 10.96.0.10
search payments.svc.cluster.local svc.cluster.local cluster.local
options ndots:5 timeout:2 attempts:2
~~~

| Trường | Ý nghĩa |
| --- | --- |
| **nameserver** | Địa chỉ DNS server mà stub resolver được cấu hình sử dụng |
| **search** | Danh sách suffix được thử cho tên tương đối theo quy tắc resolver |
| **options ndots:n** | Điều kiện liên quan số dấu chấm trước khi ưu tiên truy vấn tên như tên tuyệt đối |
| **options timeout:n** | Một tham số thời gian đợi theo resolver; không phải timeout của toàn ứng dụng |
| **options attempts:n** | Số lần thử theo cơ chế resolver; tổng số query thực tế có thể khác |

**10.96.0.10** và **cluster.local** là giá trị minh họa phổ biến, không được giả định là cấu hình của mọi cluster. Kubelet, cluster DNS domain và dịch vụ NodeLocal DNS có thể làm giá trị khác.

### 3.4. /etc/resolv.conf được cung cấp từ đâu?

Container runtime có thể tạo, mount hoặc điều chỉnh file này khi container khởi tạo. Trong Kubernetes, **kubelet** xây dựng cấu hình DNS cho Pod theo **dnsPolicy/dnsConfig** và cài đặt cluster. File trong container có thể là bản được quản lý; chỉnh tay trong Pod thường **không bền vững** sau tái tạo hoặc rollout.

**Không sửa trực tiếp /etc/resolv.conf trên một Pod production để tạo giải pháp lâu dài.** Nên sửa cấu hình DNS ở cấp được quản lý và kiểm thử sau tạo lại Pod.

### 3.5. Network namespace và loopback

Container với network namespace riêng có **loopback** và interface riêng. Nếu một container dùng **nameserver 127.0.0.1**, nó đang hướng tới loopback **của namespace đó**, không tự là systemd-resolved ở node hoặc máy host.

Trường hợp ngoại lệ có ý nghĩa, ví dụ **host networking**, **Docker embedded DNS** hoặc resolver chạy trong cùng namespace, phải được xác minh theo runtime cụ thể. Không biến một IP loopback thành “DNS host” bằng suy đoán.

## 4. Docker DNS: default bridge và user-defined networks

### 4.1. Docker container dùng DNS nào?

Docker thường thiết lập cấu hình resolver của container dựa trên mạng được gắn và cài đặt DNS của daemon/host. Nhưng có sự khác biệt quan trọng:

- Với **default bridge network**, container có thể nhận các DNS server được Docker chọn hoặc suy ra từ cấu hình host, cùng những điều chỉnh để xử lý resolver loopback của host.
- Với **user-defined Docker networks**, Docker thường cung cấp **embedded DNS** tại **127.0.0.11** trong namespace mạng của container để hỗ trợ service/container name resolution; resolver này có thể forward truy vấn ngoài phạm vi tên nội bộ.
- Docker có tùy chọn cấu hình DNS như **--dns**, **--dns-search**, cấu hình daemon hoặc network/service để điều chỉnh resolver theo khả năng runtime.

**127.0.0.11 là địa chỉ embedded DNS của Docker trong ngữ cảnh hỗ trợ, không phải DNS mặc định của Kubernetes và không phải địa chỉ cố định cho mọi runtime container.**

### 4.2. Vì sao tên container đôi khi không resolve?

Docker **default bridge** không cung cấp cùng trải nghiệm automatic name resolution cho các container tùy ý như **user-defined networks**. Trước khi kết luận DNS hỏng, cần kiểm tra hai container **có thật sự thuộc cùng network hỗ trợ service discovery** và tên/alias được công bố đúng hay không.

### 4.3. Ví dụ Docker user-defined network trong lab

~~~bash
# Chỉ chạy trong môi trường Docker lab được phép.
# Tạo network riêng để minh họa service discovery.
docker network create lab-private

# Tạo hai container thuộc mạng lab, dùng image đã được tổ chức phê duyệt.
# Tên image dưới đây chỉ là placeholder, không phải lệnh triển khai sẵn.
docker run -d --name lab-orders --network lab-private approved-orders-image
docker run -d --name lab-client --network lab-private approved-client-image

# Tùy image, có thể có getent hoặc nslookup.
docker exec lab-client getent hosts lab-orders
docker exec lab-client cat /etc/resolv.conf
~~~

Các placeholder **approved-orders-image**, **approved-client-image** phải được thay bằng images thực sự tồn tại trong registry lab được quản lý; chúng không phải image công khai được bảo đảm. **Việc tên lab-orders phân giải được không chứng minh cổng ứng dụng đang listen, hoặc client được phép truy cập nghiệp vụ.**

### 4.4. Docker network alias

Một container có thể được gắn **network alias** theo hỗ trợ của Docker. Alias có phạm vi liên quan tới network, không mặc nhiên tạo một tên DNS toàn doanh nghiệp. Nếu nhiều container chia sẻ alias, kết quả phân giải/tải có thể thay đổi theo cơ chế runtime; **không tự coi đó là load balancing có health check và affinity đầy đủ**.

### 4.5. Docker host networking

Với **host network mode** trên các hệ thống hỗ trợ, container dùng network stack của host thay vì một namespace riêng theo mô hình bridge thông thường. Hành vi loopback, firewall và DNS phải được đánh giá khác. **Không lấy tài liệu về bridge để suy ra nguyên xi cơ chế của host network**.

## 5. Docker Compose: tên service và network scope

Docker Compose thường tạo một network cho project và đăng ký tên service để những containers cùng network có thể truy vấn nhau theo tên logic.

Ví dụ mô tả một lab, không phải bản cấu hình production:

~~~yaml
services:
  web:
    image: approved-web-image
    networks: [backend]
    environment:
      ORDERS_API_URL: http://orders:8080
  orders:
    image: approved-orders-image
    networks: [backend]
    expose:
      - "8080"
networks:
  backend:
    internal: true
~~~

Trong mạng **backend** do Compose quản lý, service **web** có thể phân giải tên **orders** theo cơ chế service discovery. Tùy cấu hình scale và runtime, IP của container đích có thể đổi khi recreate/scale; ứng dụng nên xử lý **kết nối lỗi, retry có giới hạn và cập nhật phân giải**, không hardcode IP container.

### 5.1. expose khác publish

- **expose** mô tả cổng ứng dụng phục vụ các thành phần trong mạng theo ngữ cảnh Compose; nó **không tự là firewall cho mọi đường**.
- **ports** publish một cổng ra interface host theo cấu hình, có thể tạo bề mặt truy cập ngoài mạng container.
- **internal: true** giới hạn cách network kết nối ra ngoài theo mô hình Docker, nhưng **không phải cam kết rằng mọi container đã hết các đường egress khác** nếu chúng được nối thêm network hoặc có quyền host đặc biệt.

### 5.2. extra_hosts và dns options

Compose có thể hỗ trợ **dns**, **dns_search**, **dns_opt**, **extra_hosts** và aliases. **extra_hosts** đưa ánh xạ tĩnh vào hosts file; hữu ích trong một số lab/compatibility tests nhưng có thể gây lệch khi IP thay đổi.

Đừng dùng cấu hình DNS tùy ý để che vấn đề **service đang ở sai Docker network**, hoặc để truy cập một domain nội bộ mà không có chính sách TLS/route rõ ràng.

## 6. Kubernetes DNS: các thành phần chính

Trong Kubernetes, **DNS-based service discovery** thường được cung cấp bằng một dịch vụ DNS của cluster, phổ biến là **CoreDNS**. Pod được kubelet cấu hình resolver để tìm các service names; hệ thống DNS dùng thông tin về Services và endpoints theo cách Kubernetes/CNI triển khai.

~~~mermaid
flowchart LR
    P["Pod: checkout, namespace shop"] -->|"DNS query: orders.payments.svc.cluster.local"| NS["Pod resolv.conf / stub resolver"]
    NS -->|"UDP/TCP 53"| DNS["Cluster DNS Service / NodeLocal DNS nếu có"]
    DNS -->|"CoreDNS kubernetes plugin"| K["Kubernetes Service/Endpoint data"]
    K --> DNS
    DNS -->|"A/AAAA, NXDOMAIN hoặc lỗi"| P
    P -->|"Kết nối tới Service IP/endpoint theo dataplane"| SVC["Orders Service"]
    SVC --> EP["Ready endpoints / Pods"]
~~~

**DNS trả Service IP không tự chuyển packet từ client đến backend Pod.** Cơ chế Service dataplane, route, CNI, firewall và NetworkPolicy mới quyết định kết nối sau DNS, đồng thời backend vẫn cần ứng dụng/TLS authorization.

### 6.1. CoreDNS không phải một DNS server trong mỗi Pod

CoreDNS thường là workload/dịch vụ DNS chung của cluster với Deployment/Service, có thể có cache và các plugin. Pod truy vấn qua một địa chỉ DNS mà kubelet cung cấp; **đừng giả định mọi Pod có một sidecar CoreDNS hoặc CoreDNS chạy trong chính Pod**.

### 6.2. Cấu trúc tên Service phổ biến

Trong cluster domain thường được đặt là **cluster.local**, một Kubernetes Service có tên **orders** ở namespace **payments** thường được truy vấn qua:

~~~text
orders.payments.svc.cluster.local
~~~

Những dạng này là **chuẩn tổ chức tên thông dụng trong Kubernetes**, nhưng giá trị cluster domain được cấu hình ở cấp cluster. Pod ở cùng namespace có thể dùng tên ngắn **orders**, còn Pod ở namespace khác thường dùng **orders.payments** hoặc FQDN.

### 6.3. Kubernetes Service DNS không phải container hostname tùy ý

Tên **container** trong spec không tự trở thành DNS name để mọi Pod trong cluster truy cập. Kubernetes DNS tập trung vào **Service names**, Pod-specific records trong những điều kiện được hỗ trợ và các cấu hình hostname/subdomain có liên quan. Nên dùng **Service** làm điểm truy cập logic thay vì phụ thuộc IP của Pod.

## 7. ClusterIP, headless Service và service discovery

### 7.1. Service thông thường (ClusterIP)

Một Service kiểu **ClusterIP** thường có một địa chỉ ảo trong cluster. DNS cho tên Service có thể trả **A/AAAA** tương ứng, còn dataplane phân phối kết nối tới các endpoints theo cơ chế Kubernetes. **DNS không nhất thiết trả danh sách IP Pod** đối với ClusterIP Service thông thường.

### 7.2. Headless Service

Một Service với **clusterIP: None** là **headless Service**. Khi có những endpoints đủ điều kiện, DNS có thể trả những địa chỉ endpoint/Pod tương ứng thay vì một virtual ClusterIP, theo semantics và readiness/publication options áp dụng.

Ví dụ YAML minh họa:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-headless
  namespace: payments
spec:
  clusterIP: None
  selector:
    app: orders
  ports:
    - name: http
      port: 8080
      targetPort: 8080
~~~

YAML này là một tài nguyên Kubernetes minh họa và **không tạo NetworkPolicy, authentication hoặc certificate validation**. Trước khi dùng, workload matching label **app: orders** phải tồn tại và backend phải có ứng dụng listen tại port tương ứng.

### 7.3. StatefulSet và tên ổn định

Kết hợp **StatefulSet + headless Service** có thể cung cấp danh tính DNS ổn định cho các Pod thành viên theo quy tắc định danh của Kubernetes, ví dụ dạng:

~~~text
db-0.db-headless.data.svc.cluster.local
db-1.db-headless.data.svc.cluster.local
~~~

Tên logic ổn định **không đồng nghĩa IP Pod cố định**, và ứng dụng cần xử lý thay đổi endpoint, readiness, failover hoặc DNS cache.

### 7.4. EndpointSlice và readiness

Kubernetes theo dõi tập endpoints của Service qua các cơ chế như **EndpointSlice**. Việc DNS đưa Pod endpoint vào kết quả, đặc biệt với headless Service, có thể chịu ảnh hưởng của **ready conditions** và cấu hình publishNotReadyAddresses.

**Một tên trả IP nhưng ứng dụng không sẵn sàng** vẫn có thể gây lỗi kết nối. Không chữa bằng cách mở mọi NetworkPolicy; hãy kiểm tra health, endpoints và thời gian cập nhật.

### 7.5. SRV records

Kubernetes DNS có thể cung cấp bản ghi **SRV** cho các Service/port đặt tên theo quy tắc hỗ trợ. SRV giúp tìm tên endpoint/port nhưng **không tự cấp quyền truy cập** và không phải thư viện client nào cũng dùng SRV mặc định. Đừng cho rằng HTTP client thông thường sẽ tự đọc SRV thay vì A/AAAA.

## 8. dnsPolicy và dnsConfig của Kubernetes Pod

**dnsPolicy** quy định cách kubelet cấu hình DNS cho Pod. Những giá trị thường được Kubernetes hỗ trợ gồm:

| dnsPolicy | Ý nghĩa chính | Cần lưu ý |
| --- | --- | --- |
| **ClusterFirst** | Ưu tiên giải tên Service/cluster qua cluster DNS, forward tên ngoài theo cấu hình | Mặc định phổ biến cho Pods không dùng hostNetwork |
| **Default** | Kế thừa thiết lập DNS phù hợp từ node theo cơ chế kubelet | Không tự có bảo đảm tên Service cluster hoạt động như ClusterFirst |
| **None** | Không dùng thiết lập DNS kế thừa, cấu hình resolver chủ động bằng dnsConfig | Cần cung cấp nameservers/search/options phù hợp |
| **ClusterFirstWithHostNet** | Tương tự ClusterFirst nhưng dùng cho Pods có hostNetwork theo hỗ trợ | Không áp dụng mọi giả định của Pod network namespace riêng |

Một Pod có **hostNetwork: true** nhưng không cấu hình policy phù hợp có thể không nhận DNS cluster như dự định. Hãy đọc Pod spec và file resolver thực tế.

### 8.1. dnsConfig

Ví dụ manifest **cấu hình DNS** cho một Pod lab:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: dns-check
  namespace: payments
spec:
  dnsPolicy: ClusterFirst
  dnsConfig:
    options:
      - name: ndots
        value: "2"
  containers:
    - name: client
      image: approved-dns-toolbox-image
      command: ["sleep", "3600"]
~~~

Manifest chỉ minh họa **dnsConfig.options**; image placeholder phải được thay bằng image tool được phê duyệt. **Không khuyên thay ndots từ 5 sang 2 cho tất cả Pods**: đó là quyết định có thể làm thay đổi cách phân giải tên ngắn hoặc tăng/giảm truy vấn theo workload. Cần đo và thử các tên thực tế.

### 8.2. Nameserver tùy chỉnh có thể bỏ mất service discovery

Nếu đặt **dnsPolicy: None** rồi chọn resolver công cộng, Pod có thể phân giải được tên Internet nhưng **không phân giải được *.svc.cluster.local** nếu resolver đó không có forwarding/authoritative knowledge thích hợp.

Ngược lại, nếu cấu hình cluster resolver chỉ nhận tên nội bộ nhưng không forward DNS ngoài, ứng dụng có thể không phân giải được tên nhà cung cấp. **Đặt nameserver là quyết định kiến trúc về trust, tính riêng tư và khả dụng**, không chỉ là một IP tùy ý.

## 9. Search domains, ndots và truy vấn tên ngắn

Một Pod ở namespace **payments** có thể có search domains:

~~~text
payments.svc.cluster.local
svc.cluster.local
cluster.local
~~~

Khi ứng dụng hỏi **orders**, resolver có thể thử tên với các suffix tương ứng. Điều này giúp gọi Service cùng namespace thuận tiện, nhưng cũng làm cho các tên ngắn có thể **mơ hồ** và tạo thêm DNS queries.

### 9.1. ndots:5 có ý nghĩa gì?

Tùy resolver, **ndots:5** thường được hiểu là một tên có **ít hơn 5 dấu chấm** sẽ ưu tiên thử những tên ghép search suffix trước khi thử chính tên đó dưới dạng tuyệt đối. Tên chứa đủ số dấu chấm có thể được thử như tên tuyệt đối trước.

Ví dụ **api.partner.example.test** có ba dấu chấm. Trong một Pod với search list và ndots:5, resolver có thể thử các tên:

~~~text
api.partner.example.test.payments.svc.cluster.local
api.partner.example.test.svc.cluster.local
api.partner.example.test.cluster.local
api.partner.example.test
~~~

Đây là mô phỏng logic thông dụng, **không phải transcript bắt buộc**: thứ tự thực, A/AAAA query, early success, timeout và các domain bổ sung tùy resolver/config.

### 9.2. Trường hợp tên tuyệt đối có dấu chấm kết thúc

Theo cú pháp DNS, một tên như **api.partner.example.test.** với dấu chấm cuối có thể được xử lý như **absolute domain name**, tránh nối search suffix trong nhiều resolver. Nhưng **URL/TLS hostname normalization** có thể có quy tắc riêng; không thêm dấu chấm tùy ý vào URL của ứng dụng mà chưa kiểm tra tác động.

### 9.3. Rủi ro hiệu năng và thông tin

- Thêm search suffix có thể tăng số DNS lookups và độ trễ khi cache miss.
- Một tên cấu hình nhầm có thể sinh nhiều truy vấn không cần thiết.
- Tên nội bộ hoặc phần của hostname có thể bị forward ra upstream resolver nếu chính sách forwarding và search config không phù hợp.
- Những namespace có tên Service trùng với tên khác có thể làm ứng dụng kết nối sai đích nếu chỉ dùng tên ngắn.
- Một số ứng dụng có DNS client/caching riêng nên hiệu quả ndots không như cách libc mặc định.

### 9.4. Khi nào dùng FQDN?

Đối với kết nối **cross-namespace** hoặc những dependency nhạy cảm, dùng **Service FQDN rõ ràng** thường giúp tránh nhầm namespace. Với dịch vụ ngoài cluster, sử dụng tên chính thức được phê duyệt và kiểm thử resolver behavior.

**Không mặc định FQDN của Service là một danh tính TLS đã được cấp chứng thư**. Client phải kiểm tra chứng thư phù hợp với tên/service identity thực tế; nhiều hệ thống mTLS dùng **SPIFFE/service identity** hoặc tên chứng thư riêng theo kiến trúc.

## 10. Caching, TTL và DNS stale records

**Caching** làm DNS nhanh hơn nhưng cũng tạo khoảng thời gian giữa thay đổi endpoint và lúc client nhận bản ghi mới.

### 10.1. Có thể có cache ở nhiều lớp

Một câu trả lời DNS có thể được cache bởi:

1. **Application/runtime**: Java, Go, Node.js hoặc thư viện DNS tùy chọn.
2. **Local resolver/cache** trong container hoặc node nếu được cài.
3. **NodeLocal DNSCache** của Kubernetes khi được triển khai.
4. **CoreDNS cache plugin** hoặc cache của cluster DNS tương đương.
5. **Upstream recursive resolver** ở VPC/VNet hoặc DNS doanh nghiệp.

Không nên kết luận rằng CoreDNS đổi bản ghi rồi **mọi ứng dụng lập tức dùng IP mới**. DNS TTL và behavior của runtime client có thể làm một số kết nối tiếp tục dùng địa chỉ cũ.

### 10.2. Positive và negative caching

- **Positive caching:** lưu một kết quả A/AAAA/CNAME/SRV còn hiệu lực.
- **Negative caching:** lưu kết quả không tìm thấy hoặc một trạng thái lỗi DNS phù hợp theo cơ chế resolver/cache.

Negative caching có thể làm một tên Service vừa được tạo chưa resolve ngay trên một số clients, dù cluster DNS đã nhận đối tượng. **Không biến mọi NXDOMAIN kéo dài thành lỗi firewall**; cần xem cache, namespace và propagation.

### 10.3. Connection pooling và DNS

Một ứng dụng HTTP có connection pool có thể tái sử dụng kết nối tới IP cũ **mà không phân giải lại tên** cho mỗi request. Vì vậy hành vi failover phụ thuộc:

- TTL/caching của runtime.
- Thời gian sống connection.
- Sự kiện connection reset/timeout và retry có giới hạn.
- Health/readiness/endpoint changes.
- Quy tắc lựa chọn A/AAAA và nhiều IP.

**Giảm DNS TTL không tự xử lý một pool giữ TCP connection cũ quá lâu.**

### 10.4. TTL không phải thời gian đảm bảo tuyệt đối

Resolver, thư viện và chính sách cache có thể xử lý TTL khác nhau trong những giới hạn nhất định. Cần đo qua **ứng dụng thực tế** và môi trường production-like thay vì chỉ nhìn một lần **dig**.

## 11. NodeLocal DNSCache và HA của DNS cluster

Trong Kubernetes, **NodeLocal DNSCache** (khi được triển khai) có thể đặt một caching agent gần Pod trên mỗi node để giảm độ trễ hoặc tải tới dịch vụ DNS tập trung.

### 11.1. Vì sao dùng NodeLocal?

- Giảm những lần truy vấn lặp xuyên network tới CoreDNS.
- Có thể giảm áp lực connection tracking với một số mô hình UDP/Service NAT.
- Hỗ trợ giảm latency và phân bố tải theo node.
- Cải thiện tính sẵn sàng của các cache hit khi phù hợp.

**NodeLocal DNSCache không phải chức năng mặc định được bật ở tất cả clusters**. Cách kubelet cung cấp nameserver, các IP local và mối liên hệ với cluster DNS Service tùy chế độ triển khai.

### 11.2. Địa chỉ NodeLocal

Một cài đặt có thể dùng địa chỉ link-local ví dụ **169.254.20.10**, nhưng đó **chỉ là giá trị cấu hình minh họa**. Cần đọc thực tế **/etc/resolv.conf trong Pod, ConfigMap/DaemonSet DNS theo quyền được cấp** và tài liệu cluster trước khi dùng trong firewall rule. Không hardcode một địa chỉ NodeLocal từ bài học vào môi trường thật.

### 11.3. Caching agent không thay DNS upstream

NodeLocal có thể cache và forward, còn các nguồn authoritative/recursive thích hợp vẫn cần được phục vụ. Khi CoreDNS/upstream lỗi, cache có thể giúp một số truy vấn đã biết nhưng **không bảo đảm mọi tên mới hoặc bản ghi hết TTL đều được phân giải**.

### 11.4. Kiểm tra tính sẵn sàng

- Số replicas CoreDNS, phân bổ theo nodes/zones và tình trạng ready.
- Khả năng truy cập DNS Service từ Pods ở từng network zone.
- NodeLocal DNSCache đang chạy và healthy trên node liên quan.
- CoreDNS/upstream latency, SERVFAIL, timeout, error rate và cache metrics.
- Capacity và CPU throttling của DNS pods hoặc DNS cache agents.
- Các thay đổi CoreDNS configuration/forwarding vừa được rollout.

## 12. DNS ngoài cluster, split-horizon và private DNS

Một Pod có thể cần truy vấn cả **Service DNS của Kubernetes** và **tên private ở cloud/on-prem**. Đây là bài toán kết hợp giữa cluster DNS, VPC/VNet resolver, conditional forwarding và private zones.

### 12.1. Split-horizon DNS

**Split-horizon DNS** nghĩa là cùng một tên có thể có các kết quả hoặc cơ chế phân giải khác nhau tùy mạng/nguồn truy vấn. Ví dụ:

- Pod trong VPC được phép resolve **db.internal.example.test** thành private endpoint.
- Người dùng Internet có thể không resolve được tên này hoặc thấy kết quả khác theo thiết kế.
- Client từ on-prem qua VPN dùng resolver hybrid/forwarding rule để nhận kết quả nội bộ.

**Không nên tin split-horizon DNS như một biện pháp access control duy nhất**. Một private IP có thể vẫn truy cập được qua mạng khác nếu route/firewall cho phép; quyền API/DB phải được kiểm tra độc lập.

### 12.2. Conditional forwarding

CoreDNS hoặc recursive resolver có thể được cấu hình **forward những zone cụ thể** tới DNS server có thẩm quyền hoặc recursive resolver phù hợp. Ví dụ một zone nội bộ **corp.internal.example.test** có thể dùng DNS doanh nghiệp, trong khi các tên public dùng upstream cloud resolver.

Phải quản lý:

- Quyền thay CoreDNS ConfigMap hoặc resolver forwarding policy.
- Danh sách upstream được duyệt và đường mạng tới DNS server.
- Khả năng truy vấn TCP/UDP DNS tùy cơ chế.
- Hành vi timeout, failover, cache và tránh forwarding loops.
- Chính sách log, quyền riêng tư và dữ liệu tên miền nội bộ.

### 12.3. Forwarding loop

Nếu cluster DNS chuyển tiếp một zone tới DNS server A, nhưng A lại forward về cluster DNS cho cùng zone, có thể tạo vòng lặp hoặc lỗi phân giải. Một số phần mềm DNS có tính năng phát hiện loop trong những điều kiện nhất định; **không nên trông chờ mọi cấu hình vòng lặp đều được tự nhận ra an toàn**.

### 12.4. Cloud DNS và managed private endpoints

Khi container gọi một PaaS API qua **private endpoint**, DNS có thể phải resolve hostname dịch vụ thành địa chỉ private theo thiết kế cloud. Tuy nhiên:

1. **DNS đúng** chỉ định vị endpoint.
2. **NetworkPolicy/firewall** quyết định container có thể kết nối không.
3. **TLS** xác minh dịch vụ đích theo hostname/profile.
4. **IAM/resource policy** quyết định container/workload được thao tác gì với PaaS resource.

Đặc biệt, **private endpoint không tự cho quyền đọc mọi object storage buckets hoặc mọi database records**.

## 13. DNS records, IPv4/IPv6 và Service routing

### 13.1. A và AAAA

Container có thể nhận **A** và **AAAA** nếu dịch vụ và mạng hỗ trợ. Client chọn địa chỉ IPv4 hay IPv6 theo resolver/runtime và quy tắc lựa chọn địa chỉ. Trong cluster dual-stack, Service/Pod records và dataplane có thể liên quan tới cả hai IP families.

**Đừng chỉ kiểm tra A rồi kết luận DNS không có vấn đề**. Nếu AAAA đưa đến địa chỉ không reachable hoặc policy IPv6 khác IPv4, ứng dụng có thể gặp timeout/fallback.

### 13.2. DNS không thay Service dataplane

Trong Kubernetes:

- DNS trả địa chỉ **ClusterIP Service** hoặc endpoint records tùy Service.
- Service routing/load balancing do **kube-proxy, eBPF dataplane hoặc cơ chế CNI/cloud tương đương** thực hiện.
- NetworkPolicy, firewall, TLS và ứng dụng được đánh giá tại các lớp của chúng.

Một lỗi kube-proxy/eBPF/service endpoint có thể làm traffic TCP thất bại **dù nslookup trả đúng Service IP**.

### 13.3. CNAME và ExternalName

Kubernetes **ExternalName Service** có thể cung cấp một dạng alias DNS tới tên ngoài hoặc tên khác theo cơ chế hỗ trợ, không tạo ClusterIP proxying giống Service thông thường.

Ví dụ:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: reporting-external
  namespace: payments
spec:
  type: ExternalName
  externalName: reports.partner.example.test
~~~

**Cảnh báo quan trọng:** alias DNS không biến endpoint ngoài thành nội bộ, không tạo network firewall rule, và không làm chứng thư TLS của **reports.partner.example.test** tự khớp tên **reporting-external.payments.svc.cluster.local**. Nếu ứng dụng truy cập alias bằng HTTP Host/TLS SNI là tên Service, cần kiểm tra **hostname verification** và routing tương ứng; không tắt verify để che sai tên.

### 13.4. DNS SRV không giống HTTP load balancing

Một ứng dụng có khả năng truy vấn SRV có thể tìm port và target service theo DNS. Nhưng đa số HTTP client phổ biến sử dụng URL hostname + port và **không tự chuyển sang SRV record**. Khi thiết kế service discovery, chọn đúng mechanism mà runtime và client thật sự hỗ trợ.

## 14. Kubernetes NetworkPolicy và DNS egress

Một NetworkPolicy mặc định chặn **egress** cho Pod có thể làm Pod không truy vấn DNS được nữa. Khi đó API client báo **name resolution timeout** dù Service/DB hoạt động bình thường.

### 14.1. DNS thường dùng cả UDP và TCP 53

Truy vấn DNS phổ biến dùng **UDP 53**, nhưng **TCP 53** cũng cần được xem xét trong những tình huống như response lớn/truncated, fallback, zone transfers ở phạm vi server phù hợp hoặc thiết kế resolver cụ thể. **Không giới hạn cứng rằng “DNS chỉ dùng UDP”**.

### 14.2. Ví dụ NetworkPolicy cho DNS query tới CoreDNS

YAML bên dưới là **một policy lab có giả định**:

- Pod cần được bảo vệ mang label **app=checkout** trong namespace **shop**.
- DNS Pods dùng label **k8s-app=kube-dns** trong namespace **kube-system**.
- CNI thực thi Kubernetes NetworkPolicy theo semantics mong đợi.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-checkout-to-cluster-dns
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: checkout
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

**Quan trọng:** Đây không phải policy hoàn chỉnh cho mọi cluster. Nó dùng hai selector trong cùng một mục **to**, vì vậy ý định là **Pod có label phù hợp VÀ ở namespace được chọn**, không phải “bất kỳ Pod hoặc bất kỳ namespace”. Nếu chia chúng thành hai mục độc lập, biểu thức được hiểu theo cơ chế **OR** và có thể mở rộng quyền ngoài ý định.

### 14.3. Trước khi áp dụng phải xác minh

1. **Namespace và label DNS Pods thật**: có thể không phải k8s-app=kube-dns.
2. **Cluster DNS Service IP** và dataplane/CNI: hành vi selector policy với Service IP/NAT có thể khác theo implementation.
3. Nếu dùng **NodeLocal DNSCache**, truy vấn có thể đến một agent ở node hoặc IP link-local thay vì CoreDNS Pod; policy ví dụ có thể không khớp.
4. NetworkPolicy khác đang áp dụng có thể cho phép thêm egress, hoặc có global policies độc lập.
5. CNI có thực sự hỗ trợ **egress policy** và tính năng được kỳ vọng hay không.
6. Pod có cần DNS tới resolver ngoài cluster cho những trường hợp đặc biệt không.

**Không copy nguyên manifest và coi như đã bảo vệ DNS hoặc đã khôi phục mọi DNS traffic.** Phải kiểm tra effective enforcement bằng positive và negative tests.

### 14.4. Built-in NetworkPolicy không là FQDN firewall

Kubernetes **NetworkPolicy API chuẩn** chủ yếu mô tả policy trên Pod/namespace/IP và protocol/port; nó **không cung cấp một đối tượng FQDN allowlist chuẩn áp dụng cho mọi CNI**. Một số CNI hoặc sản phẩm mạng mở rộng hỗ trợ **FQDN-aware policy**, nhưng semantics/cache/TTL/DNS proxy và bypass sẽ là đặc tính riêng.

**Cho phép DNS query tới một tên không có nghĩa hệ thống tự chỉ cho phép kết nối tới IP được trả về từ tên đó.** Cần policy egress tới đích thực và lớp xác thực TLS/service.

## 15. DNS như một security boundary

### 15.1. DNS answer là dữ liệu có nguồn, không phải quyền truy cập

Nếu resolver bị cấu hình sai, một name có thể resolve tới IP của endpoint không được phê duyệt. Khi ứng dụng kết nối, cần kiểm tra **TLS hostname/service identity**, network policy và quyền ứng dụng. Không dùng “IP do DNS nội bộ trả” làm bằng chứng danh tính đủ mạnh.

### 15.2. Quyền sửa DNS quan trọng như quyền sửa firewall

Những người có quyền thay:

- **CoreDNS Corefile/ConfigMap** và forwarding rules.
- Kubernetes **Service, EndpointSlice, ExternalName** hoặc các tài nguyên discovery liên quan.
- **Namespace, labels, Service selectors** hoặc workload endpoints.
- **Docker network aliases** và Compose service configuration.
- **Cloud private DNS zones, records và resolver forwarding**.

có thể làm thay đổi endpoint mà ứng dụng sẽ kết nối. Đây là một nhóm quyền **control plane** cần kiểm soát bằng RBAC/IAM, audit, change review và policy-as-code.

### 15.3. DNS spoofing và cache poisoning

**DNS spoofing** hoặc **cache poisoning** làm ứng dụng nhận câu trả lời DNS không đúng theo nguồn mong muốn. Phòng vệ nên gồm:

- Chỉ dùng **resolvers được phê duyệt**, kiểm soát đường tới DNS.
- Bảo vệ quyền quản trị DNS server, zones và cache.
- Giới hạn việc sửa Service/EndpointSlice ở cluster.
- Dùng **DNSSEC validation khi phù hợp cho zone hỗ trợ**, hiểu phạm vi và trust chain thực tế.
- Xác minh **TLS server name/certificate** hoặc service identity sau resolution.
- Giám sát response bất thường, thay đổi records hoặc resolver.

**DNSSEC không tự cấp quyền API hoặc bảo đảm endpoint application an toàn**. Với tên Service nội bộ Kubernetes, DNSSEC validation **không nên được giả định đang có** chỉ vì public DNS có hỗ trợ DNSSEC.

### 15.4. DNS rebinding và các luồng ứng dụng tự gọi URL

Một ứng dụng nhận URL do user gửi có thể resolve hostname để kết nối dịch vụ khác. Nếu địa chỉ trả về thay đổi theo thời gian hoặc chứa dải nội bộ, request có thể đi tới endpoint không mong muốn trong những điều kiện có lỗ hổng logic. Đây là một nhóm rủi ro liên quan **SSRF/DNS rebinding**.

Phòng vệ ở mức kiến trúc:

1. Hạn chế ứng dụng tùy ý gọi URL do client cung cấp.
2. Có danh sách đích/địa chỉ được phép và chính sách theo nghiệp vụ.
3. Kiểm tra **địa chỉ đã resolve và địa chỉ thực sự kết nối**, kể cả IPv4/IPv6 và redirect, ở mức client/egress proxy phù hợp.
4. Hạn chế đường tới metadata/admin/internal endpoints bằng network controls.
5. Không tắt TLS hostname verification khi endpoint thay đổi.

Đây là **hướng dẫn phòng vệ**, không yêu cầu tạo payload tấn công hoặc truy cập metadata endpoints thật trong bài thực hành.

## 16. DNS tunneling và dữ liệu nhạy cảm trong truy vấn

DNS có thể bị lạm dụng như một kênh đưa thông tin ra ngoài khi workload được phép hỏi tên miền tùy ý qua một resolver. **DNS tunneling** ở cấp độ khái niệm sử dụng chuỗi truy vấn/tên miền để mang dữ liệu theo một kênh vốn được thiết kế cho name resolution.

### 16.1. Vì sao container dễ bị bỏ sót?

- Workload outbound **TCP/443 bị hạn chế**, nhưng DNS egress **UDP/TCP 53** lại được phép rộng.
- DNS queries được forward tới upstream ngoài tổ chức mà không có chính sách zone.
- Flow logs thấy lưu lượng tới resolver chung, không thấy đầy đủ **query names**.
- DNS cache/logging tắt hoặc không bao phủ những resolver khác, DoH hoặc direct IP.
- Một container bị xâm nhập có thể thử sử dụng DNS như một trong nhiều kênh outbound.

### 16.2. Dấu hiệu quan sát cần điều tra

| Dấu hiệu | Ý nghĩa có thể | Lưu ý |
| --- | --- | --- |
| Nhiều tên con ngẫu nhiên và rất dài | Tạo tên động không giống baseline | Cũng có thể do CDN/telemetry hợp lệ |
| Tỷ lệ NXDOMAIN tăng mạnh | Nhiều tên không tồn tại hoặc lỗi cấu hình | Không tự chứng minh tunneling |
| Số lượng DNS queries/Pod tăng đột biến | Vòng retry, lỗi resolver hoặc hoạt động bất thường | Kiểm tra ndots/search trước |
| Truy vấn trực tiếp tới resolver chưa duyệt | DNS bypass hoặc cấu hình nhầm | Xem network route/policy |
| Query names chứa dữ liệu nhạy cảm | Rò rỉ thông tin qua tên miền | Áp dụng redaction/retention trong DNS logs |
| DoH/DoT kết nối tới dịch vụ ngoài policy | Có thể né DNS logs tập trung | Kiểm tra egress và hành vi ứng dụng |

**Không quy kết chỉ từ “subdomain dài”**. Cần đối chiếu workload, thay đổi ứng dụng, DNS baseline và network flow trước khi phân loại sự kiện.

### 16.3. Phòng vệ

- Quy định **resolver dùng được** cho từng trust zone.
- Giới hạn **DNS egress** tới CoreDNS/managed resolver được quản lý.
- Giới hạn direct Internet egress và các đích DoH/DoT ngoài policy khi thích hợp.
- Bật **DNS query/response telemetry** theo phạm vi cần thiết và chính sách quyền riêng tư.
- Dùng detection rules theo baseline, rate và domain reputation nếu có nguồn tin cậy.
- Kết hợp DNS telemetry với EDR, container runtime, process identity và application logs.

DoH/DoT có thể là cơ chế bảo vệ riêng tư hợp lệ trong một số môi trường. **Không coi mọi truy cập DoH/DoT là độc hại**; cần chính sách rõ ràng về những resolver mã hóa được phê duyệt.

## 17. DNS over HTTPS, DNS over TLS và bypass

**DNS over HTTPS (DoH)** truyền truy vấn DNS qua HTTPS; **DNS over TLS (DoT)** truyền qua TLS theo giao thức tương ứng. Nếu container tự sử dụng một DoH client/SDK, truy vấn DNS có thể **không đi qua UDP 53 tới CoreDNS**, dù /etc/resolv.conf trỏ về cluster DNS.

### 17.1. Hệ quả phòng vệ

| Thành phần | Trường hợp DNS truyền thống | Trường hợp DoH/DoT do ứng dụng chọn |
| --- | --- | --- |
| /etc/resolv.conf | Có thể được resolver hệ điều hành sử dụng | Có thể bị ứng dụng bỏ qua |
| NetworkPolicy cho UDP/TCP 53 | Có thể cho phép/chặn những queries qua cổng 53 | Không bao phủ DoH qua HTTPS hoặc DoT trên cổng khác |
| CoreDNS query logs | Thấy queries thực sự tới CoreDNS | Không thấy query đi thẳng resolver bên ngoài |
| Egress firewall/proxy | Giới hạn DNS endpoint được phép | Cần chính sách cho resolver mã hóa và đích egress |
| TLS certificate validation | Không thay thế DNS integrity | Cần xác minh DoH/DoT server identity; vẫn không thay app auth |

### 17.2. Không “chặn mọi TCP 443” để giải quyết DNS bypass

TCP/443 còn phục vụ rất nhiều API, package registry và dịch vụ cloud hợp lệ. Một policy phù hợp có thể dựa trên **destination identities, egress proxy, managed resolver, workload policy hoặc DNS application behavior** theo khả năng nền tảng. Chặn quá rộng có thể phá hệ thống và không chắc ngăn mọi đường khác.

## 18. Container image, runtime và quyền quản trị DNS

Một container image được tạo bằng Dockerfile không tự quyết định toàn bộ /etc/resolv.conf cuối cùng, vì runtime/orchestrator có thể cung cấp cấu hình khác khi khởi chạy.

### 18.1. Minimal/distroless images

Container **distroless** hoặc image tối giản có thể không có **sh, nslookup, dig, getent, ping hoặc curl**. Việc không chạy được lệnh không chứng minh DNS lỗi.

Khi cần chẩn đoán, có thể:

- Dùng công cụ quan sát của nền tảng ở control plane, nếu được cấp phép.
- Dùng **ephemeral debug container** hoặc toolbox được phê duyệt và phù hợp security policy.
- Dùng sidecar/tooling ở **lab** với cùng namespace/pod network để so sánh.
- Thu thập resolver output qua ứng dụng hoặc synthetic health checks.

**Không cài phần mềm debug tùy ý vào production image đang chạy**, đặc biệt nếu phải mở mạng, nâng quyền hoặc thêm bí mật.

### 18.2. Runtime privileges có liên quan DNS

Một container có quyền quá rộng (ví dụ host networking, CAP_NET_ADMIN, privileged mode) có thể thay đổi hành vi mạng hoặc vượt những giả định phân đoạn khác nhau tùy host/CNI. **Không nên cấp quyền đặc biệt chỉ để sửa DNS** khi vấn đề thực sự nằm ở dnsPolicy, Service hoặc network policy.

### 18.3. Kiểm soát nguồn hình ảnh và cấu hình

Vì DNS có thể được ứng dụng gọi trực tiếp theo SDK/config, cần kiểm soát:

- Tùy chọn DNS trong runtime/client library.
- Biến môi trường **HTTP_PROXY, HTTPS_PROXY, NO_PROXY** và tên host của proxy.
- Base image, runtime updates và các thay đổi liên quan resolver.
- Workload identity và quyền thay DNS ConfigMap/Service.
- Khả năng container truy cập trực tiếp mạng host hoặc resolver không được duyệt.

**Một container có /etc/resolv.conf đúng nhưng ứng dụng vẫn đi tới DNS khác** là tình huống có thể xảy ra nếu ứng dụng nhúng resolver riêng hoặc dùng DoH.

## 19. Phân biệt DNS outage với lỗi network, TLS hoặc ứng dụng

Một ứng dụng báo **“connection failed”** chưa chắc lỗi DNS. Để chẩn đoán chính xác, cần phân biệt:

| Triệu chứng | Lớp có thể gặp lỗi | Kiểm tra ưu tiên |
| --- | --- | --- |
| **getaddrinfo: Name or service not known** | Tên, search domains, NXDOMAIN, hosts/NSS | FQDN, namespace, DNS answer, cấu hình ứng dụng |
| **Temporary failure in name resolution** | DNS timeout/SERVFAIL hoặc resolver tạm lỗi | Nameserver, CoreDNS/upstream health, egress firewall |
| **nslookup trả NXDOMAIN** | Name không tồn tại theo DNS được hỏi hoặc search suffix sai | Tên Service, namespace, zone và authoritative source |
| **nslookup trả SERVFAIL** | Resolver không hoàn tất truy vấn | CoreDNS config/forwarding, upstream, health |
| **nslookup timeout** | DNS endpoint không trả lời hoặc packet bị chặn | IP DNS, UDP/TCP 53, route, NetworkPolicy, CNI |
| **A/AAAA trả IP nhưng TCP timeout** | DNS xong, vấn đề kết nối mạng/dịch vụ | Service/Endpoints, policy, route, firewall, listener |
| **TCP connect được nhưng TLS lỗi** | Chứng thư, SNI, trust chain, hostname | TLS verification, endpoint đúng, certificate inventory |
| **HTTPS trả 401/403** | API authentication/authorization | Access token, scopes, audience, object policy |
| **Chỉ một Pod lỗi** | DNS config riêng, CNI/node cache, image/runtime | Pod spec, node placement, resolv.conf |
| **Chỉ một namespace lỗi** | Tên ngắn, search domain, NetworkPolicy, namespace resources | FQDN, policy selection và namespace |
| **Chỉ external DNS lỗi** | CoreDNS forwarding, upstream resolver hoặc private zone | Internal Service query so với external FQDN |
| **Chỉ service mới tạo lỗi** | DNS cache, resource chưa sẵn sàng, Service/EndpointSlice | Query FQDN, Service readiness, negative cache |
| **Chỉ IPv6 lỗi** | AAAA, IPv6 routing/policy/listener | A/AAAA query và kết nối theo address family |

### 19.1. Không gộp mọi lỗi thành DNS

Ví dụ CoreDNS trả **10.60.20.80** cho **orders.payments.svc.cluster.local** là kết quả DNS thành công. Nếu Pod tiếp tục nhận **Connection refused**, phải kiểm tra **Service port, targetPort, Pod listener, readiness và policy**, không sửa DNS chỉ vì URL chứa hostname.

### 19.2. Không gộp mọi lỗi thành NetworkPolicy

Nếu Pod không thể resolve một Service vì **Service chưa tồn tại**, mở UDP/53 rộng hơn không tạo ra bản ghi. Ngược lại, Service tồn tại và CoreDNS khỏe nhưng Pod **egress-isolated** có thể không gửi được DNS query.

### 19.3. Lỗi theo node và zone

Một số Pods có thể chạy được còn Pods trên node khác không, do **NodeLocal DNSCache, route, CNI, kubelet DNS config, packet loss hoặc resource pressure** trên node. Nên ghi **node name, network zone, namespace và time window** trước khi so sánh.

## 20. Quy trình chẩn đoán DNS từng lớp trong Kubernetes

Quy trình sau chỉ dành cho cluster **được cấp quyền quan sát/kiểm thử**. Lệnh là ví dụ minh họa; tên namespace, Pod, image và cluster domain phải thay bằng dữ liệu thật. Một số command đòi **RBAC** hoặc tool có sẵn trong container.

### Bước 1 – Xác định tên, nguồn và thời điểm lỗi

Ghi:

~~~text
Application:      checkout
Pod namespace:    shop
Pod:              checkout-abc123
Node:             node-lab-02
Requested name:   orders.payments.svc.cluster.local
Requested port:   8080
First observed:   2026-11-28T19:30:00+07:00
Error type:       DNS timeout / NXDOMAIN / SERVFAIL / connect timeout
Scope:            Only authorized training environment
~~~

Mục tiêu là giữ **requested name** chính xác. Nếu ứng dụng dùng tên ngắn **orders**, cần ghi lại tên đó thay vì tự đổi thành FQDN trong log điều tra.

### Bước 2 – Đọc resolver config trong Pod

~~~bash
# Chỉ chạy trên cluster được phép; command cat cần tồn tại trong container.
kubectl -n shop exec checkout-abc123 -- cat /etc/resolv.conf

# Đọc thông tin Pod, gồm dnsPolicy, dnsConfig, hostNetwork và node name.
kubectl -n shop get pod checkout-abc123 -o yaml
~~~

Nếu Pod gồm nhiều containers, có thể cần chọn đúng container; **file resolver và network namespace thường được chia sẻ trong Pod**, nhưng ứng dụng có thể dùng resolver riêng không dựa hoàn toàn vào file đó.

### Bước 3 – Xem Service và endpoints ở namespace đích

~~~bash
# Read-only kiểm tra Service và EndpointSlices trong namespace payments.
kubectl -n payments get service orders -o wide
kubectl -n payments get endpointslice -l kubernetes.io/service-name=orders
~~~

Kết quả cần xem:

- Service có tồn tại với **tên và namespace đúng** không?
- Service type là **ClusterIP** hay **headless**?
- Địa chỉ Service, ports/targetPorts và các endpoints có hợp lệ không?
- Backend Pods có ready không, endpoints có cập nhật không?

**Đừng sửa selector/namespace khi chưa xác nhận lỗi**, vì có thể ảnh hưởng những ứng dụng khác đang dùng cùng Service.

### Bước 4 – Truy vấn tên ngắn và FQDN trong Pod

Nếu Pod có công cụ được phê duyệt:

~~~bash
# Lệnh bên trong container lab hoặc debug container phù hợp.
getent hosts orders
getent hosts orders.payments.svc.cluster.local

# nslookup có thể có cú pháp khác theo BusyBox/BIND.
nslookup orders.payments.svc.cluster.local
~~~

**getent** dùng hệ thống name-service của môi trường hỗ trợ và có thể xét hosts/NSS; **nslookup/dig** thường truy vấn DNS trực tiếp theo cơ chế công cụ. Vì thế hai lệnh có thể cho kết quả khác nhau khi **/etc/hosts, local cache hoặc library resolver behavior** khác.

### Bước 5 – Xác minh cluster DNS health

Tùy cluster/nhà cung cấp, có thể quan sát DNS pods và service qua những tên được cấu hình thực tế:

~~~bash
# Tên label/dịch vụ chỉ mang tính phổ biến, cần xác minh trước khi dùng.
kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide
kubectl -n kube-system get service kube-dns
~~~

Không phải mọi cluster dùng tên Service **kube-dns** hoặc label **k8s-app=kube-dns**; CoreDNS có thể được quản lý theo kiểu khác. Nếu câu lệnh trả không có tài nguyên, **không tự kết luận DNS không tồn tại**.

### Bước 6 – Phân biệt cluster DNS với upstream

Thử hai nhóm truy vấn trong lab:

1. **Service nội bộ**, ví dụ orders.payments.svc.cluster.local.
2. **Tên ngoài hoặc private DNS**, ví dụ api.partner.example.test.

Nếu Service DNS hoạt động nhưng external DNS lỗi, ưu tiên kiểm tra **CoreDNS forward plugin/upstream, route và resolver hybrid**. Nếu cả hai lỗi, kiểm tra **resolver endpoint từ Pod, DNS Service/NodeLocal agent và DNS egress**.

### Bước 7 – Kiểm tra NetworkPolicy và CNI enforcement

~~~bash
# Read-only: xem NetworkPolicies được khai báo cho namespace shop.
kubectl -n shop get networkpolicy
kubectl -n shop describe networkpolicy
~~~

Đối chiếu **podSelector, policyTypes, egress rules, DNS endpoint thực, namespace selectors** và CNI. Kubernetes NetworkPolicy **cho phép traffic theo hợp của các policy áp dụng**, nên không đọc một policy duy nhất rồi suy nó ghi đè mọi policy khác.

Nếu có global CNI policies hoặc cloud firewalls, chúng có thể bổ sung điều kiện khác; phải kiểm tra theo hệ thống thực tế.

### Bước 8 – Tách DNS khỏi kết nối TCP

Sau khi tên đã resolve đúng, kiểm tra backend **đang listen và reachable** qua cổng được phép bằng probe có giới hạn. So sánh log ứng dụng, Service endpoints, network flow và policy denies. Nếu TCP thành công mà HTTPS lỗi, kiểm tra **TLS certificates/SNI**, không mở thêm firewall.

### Bước 9 – Đối chiếu thay đổi mới

Rà soát những thay đổi liên quan:

- Pod deployment, image/runtime resolver hoặc dnsPolicy.
- CoreDNS ConfigMap/Deployment hoặc NodeLocal DNSCache.
- NetworkPolicy/CNI/cloud firewall/route.
- Namespace/Service name/label/EndpointSlice.
- Cloud private DNS forwarding, VPN/hybrid resolver.
- Nâng cấp node, autoscaling hoặc thay đổi cluster domain.

### Bước 10 – Sửa hẹp và xác minh lại

Sửa đúng **nguồn gây lỗi**; không tự thêm public resolver hoặc tắt toàn bộ NetworkPolicy trong production để thử. Sau khi sửa, xác nhận **negative test** (Pod ngoài quyền vẫn không truy cập được endpoint bị hạn chế) và **positive test** (ứng dụng hợp lệ resolve/kết nối đúng).

## 21. Docker và Compose: kiểm tra tên dịch vụ

Trong Docker hoặc Compose, quy trình có điểm khác Kubernetes.

### 21.1. Kiểm tra mạng và DNS

~~~bash
# Chỉ quan sát container/network thuộc lab đã được cấp phép.
docker inspect lab-client
docker network inspect lab-private
docker exec lab-client cat /etc/resolv.conf
~~~

Cần kiểm tra:

- Container gắn đúng **user-defined network**?
- Network aliases/container names có hợp lệ và trong cùng phạm vi?
- File resolver có **127.0.0.11** hoặc nameserver khác theo runtime?
- Có DNS overrides, extra_hosts, proxy environment hoặc custom app resolver?
- DNS ngoài network có bị chặn bởi host firewall/VPN/cloud policy không?

### 21.2. Trường hợp Compose service recreate

Nếu service **orders** được recreate và có IP mới, ứng dụng web vẫn giữ cached IP hoặc pooled TCP connection cũ có thể lỗi dù công cụ **nslookup orders** đã trả IP mới. Cần kiểm tra **DNS cache và connection pool**, không hardcode lại IP cũ trong Compose.

### 21.3. Lỗi tên khác project

Hai Compose projects thường có network mặc định khác nhau. **Tên service giống nhau không có nghĩa hai containers khác projects có thể resolve/gọi nhau** nếu không có network chung được thiết kế và kiểm soát. Gắn chúng vào cùng một mạng làm tăng phạm vi trust, nên phải có lý do và policy rõ ràng.

## 22. Logging, metrics và DNS observability

Một chuỗi DNS có thể gồm **app → Pod/node → cluster DNS → upstream cloud/on-prem DNS**. Muốn chẩn đoán cần nhìn thấy đúng lớp, không chỉ xem một container log.

| Nguồn telemetry | Dữ liệu có thể có | Hạn chế |
| --- | --- | --- |
| Application logs | Tên truy vấn, lỗi getaddrinfo, timeout và kết nối | Có thể không ghi resolver IP hoặc kết quả cache |
| CoreDNS query/metrics | RCODE, latency, cache hits/misses, forwarding errors khi bật | Không thấy DoH/client resolver đi vòng qua CoreDNS |
| NodeLocal DNSCache logs/metrics | Cache, errors, upstream failures theo node | Chỉ khi được triển khai và thu thập |
| Network flow logs/CNI policy logs | Source/destination IP, port 53, allow/deny và bytes | Không luôn chứa query name hoặc payload DNS |
| Cloud DNS resolver logs | Queries được resolver cloud quản lý nhìn thấy | Không bao phủ mọi resolver khác/DoH |
| Cloud control-plane audit | Ai sửa DNS zones, firewall, subnet, routes | Không chứng minh request thực tế đã resolve/kết nối |
| Kubernetes audit | Thay đổi Service, EndpointSlice, ConfigMap, NetworkPolicy | Phụ thuộc cấu hình audit/retention |
| IDS/IPS/EDR telemetry | Bất thường DNS hoặc tiến trình container | Độ bao phủ khác theo điểm đặt và cơ chế mã hóa |

### 22.1. Những metric có giá trị

- **DNS query rate theo Pod/namespace/node** nếu có thông tin nguồn đáng tin.
- **NXDOMAIN/SERVFAIL** và error/timeout rate theo zone/upstream.
- Độ trễ **p50/p95/p99** truy vấn và cache hit ratio.
- CoreDNS replica readiness, CPU/memory, restarts và throttling.
- NodeLocal DNSCache health theo node.
- Số query tới **resolvers ngoài danh mục**.
- DNS egress deny theo NetworkPolicy/CNI/firewall.
- Số endpoint/service name mới hoặc thay đổi zone bất thường.
- Độ trễ từ DNS resolution tới TLS/API errors trong ứng dụng.

### 22.2. Metric không tự chứng minh root cause

Ví dụ tăng NXDOMAIN có thể do **ndots/search expansion, service mới chưa tồn tại, cache hết TTL hoặc truy vấn tên bất thường**. Không tự gắn nhãn “DNS attack” khi chưa đối chiếu nguồn và thay đổi ứng dụng.

### 22.3. Log giả lập: DNS egress bị chặn

~~~json
{
  "timestamp": "2026-11-28T19:45:00+07:00",
  "dataset": "synthetic-training-event",
  "namespace": "shop",
  "pod": "checkout-abc123",
  "node": "node-lab-02",
  "dns_query_name": "orders.payments.svc.cluster.local",
  "dns_query_type": "A",
  "resolver_destination": "10.96.0.10",
  "protocol": "UDP",
  "destination_port": 53,
  "network_policy_decision": "deny",
  "dns_answer_received": false,
  "error_category": "dns-timeout",
  "policy_version": "lab-default-deny-egress-03",
  "note": "Dia chi va tai nguyen deu la du lieu gia lap"
}
~~~

Log thể hiện một **quyết định network deny ở UDP/53**, không chứng minh CoreDNS trả NXDOMAIN. Cần phân biệt **không gửi được query** với **DNS server có trả lời rằng tên không tồn tại**.

### 22.4. Log giả lập: DNS trả đúng nhưng kết nối bị từ chối

~~~json
{
  "timestamp": "2026-11-28T19:46:00+07:00",
  "dataset": "synthetic-training-event",
  "namespace": "shop",
  "pod": "checkout-abc123",
  "requested_service": "orders.payments.svc.cluster.local",
  "dns_result": "10.60.20.80",
  "dns_status": "NOERROR",
  "application_destination_port": 8080,
  "service_network_policy": "deny",
  "application_connection": "timeout",
  "diagnosis": "dns-success-but-network-policy-blocked",
  "request_sent_to_backend": false
}
~~~

Ở đây **DNS hoạt động đúng** nhưng kết nối tới cổng ứng dụng bị chặn. Hệ thống không nên ghi lỗi tổng quát **dns-failure** trong trường hợp này.

### 22.5. Hạn chế dữ liệu nhạy cảm

DNS query names có thể bộc lộ **hostname nội bộ, tên thiết bị, tenant, user hoặc thông tin nghiệp vụ** nếu ứng dụng đưa dữ liệu đó vào tên truy vấn. Cần giới hạn quyền xem logs, retention, redaction và không in tokens, private keys hoặc payload nhạy cảm. Việc bật **full query logging** trên cluster lớn có thể tăng chi phí và rủi ro riêng tư; hãy chọn phạm vi phù hợp.

## 23. Chính sách DNS và service discovery trung lập với sản phẩm

YAML sau là **mô hình ý định bảo mật/vận hành**; không phải cấu hình dán trực tiếp vào Kubernetes CoreDNS, Docker daemon, CNI policy, cloud DNS hoặc firewall cụ thể:

~~~yaml
containerDnsSecurityPolicy:
  name: controlled-container-dns
  environment: isolated-training
  ownership:
    networkTeam: cloud-platform
    dnsTeam: infrastructure-dns
    workloadOwner: application-team
  trustedResolution:
    clusterDomain: configured-per-cluster
    kubernetesResolver: managed-cluster-dns
    nodeLocalDns: use-only-when-provisioned-and-verified
    dockerEmbeddedDns: use-for-supported-user-defined-networks
    allowedUpstreamResolvers: approved-cloud-or-enterprise
    privateZones: approved-conditional-forwarding
  workloadDnsConfiguration:
    preferQualifiedServiceNamesAcrossNamespaces: true
    requireApprovedDnsPolicy: true
    dnsConfigOverridesRequireReview: true
    testSearchDomainAndNdotsChanges: true
    avoidHardcodedPodAndContainerIps: true
    honorRuntimeDnsCacheBehavior: true
  networkControls:
    restrictDnsEgressToApprovedDestinations: true
    supportUdpAndTcpDnsWhenRequired: true
    protectNodeLocalDnsPath: according-to-cni-and-node-mode
    testDirectIpAndEncryptedDnsBypass: true
    protectIpv4AndIpv6: true
    restrictCrossZoneApplicationTraffic: true
  serviceIdentity:
    requireTlsServerValidationForSensitiveCalls: true
    requireApplicationAuthorization: true
    preventUntrustedServiceAndEndpointChanges: true
    protectPrivateEndpointIamAndResourcePolicy: true
  operations:
    manageCoreDnsAsReviewedConfiguration: true
    monitorCoreDnsAndNodeLocalHealth: true
    observeNxdomainServfailTimeoutRates: true
    correlateDnsErrorsWithNetworkAndTls: true
    redactSensitiveQueryNames: true
    detectUnexpectedResolverUsage: true
  governance:
    protectDnsAndServiceDiscoveryRbac: true
    auditChangesToServicesAndDnsConfig: true
    testPositiveAndNegativeFlows: true
    expireTemporaryExceptions: true
    maintainRollbackAndIncidentRunbook: true
~~~

**Không coi chỉ một dòng restrictDnsEgressToApprovedDestinations: true là firewall đã chặn được DoH hoặc NodeLocal DNS path.** Mỗi mục phải được ánh xạ thành cấu hình thực, có chủ sở hữu và test ở điểm enforcement liên quan.

## 24. Thiết kế DNS an toàn cho các nhóm workload

| Nhóm workload | Nhu cầu DNS | Ranh giới cần bảo vệ |
| --- | --- | --- |
| Public frontend | Cluster Service + tên API ngoài đã duyệt | Không cho truy cập trực tiếp data zone hoặc resolver lạ |
| Internal backend API | Service discovery nội bộ, IdP/DB private names | TLS/mTLS identity, namespace policy, IAM |
| Stateful database client | Tên DB ổn định, headless/StatefulSet khi phù hợp | Readiness, failover, không hardcode Pod IP |
| Batch/CI jobs | Artifact registry, Git/package endpoints, service DNS | Egress allowlist, secret protection, DoH bypass review |
| Security monitoring | DNS telemetry, service discovery, network events | Log RBAC/retention, không tạo đường truy cập tùy ý |
| System/CoreDNS | Kubernetes service records và upstream DNS | HA, resource limits, protected ConfigMap/RBAC |
| Hybrid connector | Cloud/private zones, on-prem DNS | Conditional forwarding, VPN route, split DNS và trust zones |
| Management tools | Internal admin hostnames | MFA/PAM, namespace isolation và service authorization |

### 24.1. Tiêu chí kiến trúc

Một thiết kế đúng trả lời được:

1. **Mỗi workload thực sự hỏi resolver nào?** Khi nào dùng libc, NodeLocal, CoreDNS hoặc DoH?
2. **Ai có quyền sửa tên/địa chỉ?** CoreDNS, Service, EndpointSlice, cloud private zone, Docker alias?
3. **DNS queries đi qua network controls nào?** Có đường IPv6, NAT hoặc sidecar bypass?
4. **Tên được trả về có được kiểm tra TLS/service identity không?**
5. **Nếu DNS lỗi, ứng dụng retry/cache/failover thế nào?** Có tạo retry storm không?
6. **Từ log có chứng minh query bị chặn, server trả NXDOMAIN hay ứng dụng không kết nối được không?**

## 25. Ma trận kiểm thử DNS container trong lab an toàn

Các kiểm thử dành cho **Docker lab, Kubernetes namespace, CoreDNS hoặc mạng cloud được cấp phép**. Không dùng DNS flood, không truy vấn hàng loạt domain của bên thứ ba, không cố phá dịch vụ DNS production. Nên kiểm tra cả **positive case** và **negative case** có phạm vi hẹp.

| Mã | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T-01 | Docker container A/B cùng user-defined network; tra tên service/alias hợp lệ | Resolve thành công theo network scope |
| T-02 | Docker container ở hai networks tách biệt, không có service discovery chung | Không tự resolve tên nội bộ của network còn lại |
| T-03 | Docker container đọc /etc/resolv.conf trong user-defined network | Xác nhận resolver phù hợp runtime; có thể là 127.0.0.11 |
| T-04 | Docker Compose service được recreate làm đổi IP | Tên logic tiếp tục phân giải đúng, app xử lý cache/reconnect |
| T-05 | Pod trong namespace payments hỏi Service orders bằng tên ngắn | Resolve theo search domain nếu config phù hợp |
| T-06 | Pod từ namespace shop hỏi orders.payments.svc.cluster.local | Resolve đúng Service và namespace |
| T-07 | Pod từ namespace shop hỏi tên orders ngắn nhưng không có cùng namespace Service | Không mặc định trỏ sang payments |
| T-08 | Cluster DNS domain tùy chỉnh khác cluster.local | FQDN thực theo cluster config, không hardcode tên sai |
| T-09 | Service loại ClusterIP có ready endpoints | DNS trả Service IP theo cấu hình; TCP path được kiểm thử riêng |
| T-10 | Headless Service có nhiều ready endpoints | DNS trả endpoints phù hợp; ứng dụng không hardcode Pod IP |
| T-11 | Headless Service có endpoint not ready | Record availability theo readiness/publishNotReadyAddresses |
| T-12 | Tên Service không tồn tại | Phản hồi theo DNS semantics như NXDOMAIN; không nhầm timeout |
| T-13 | Cluster DNS khỏe nhưng upstream resolver lab offline | Internal names vẫn được xử lý nếu không phụ thuộc upstream; external queries có thể lỗi |
| T-14 | Cấu hình search domains/ndots khác nhau trên hai Pods lab | Số query và kết quả được ghi nhận, không suy chỉ từ một Pod |
| T-15 | Tạo Service mới sau khi đã cache negative response | Xác minh thời gian phục hồi DNS theo TTL/cache thực |
| T-16 | Egress-isolated Pod không có rule DNS phù hợp | DNS query bị chặn theo chính sách có thể quan sát |
| T-17 | Thêm DNS egress rule đúng Pod/namespace/UDP/TCP 53 trong lab | DNS được phép; những đích ứng dụng ngoài quyền vẫn bị chặn |
| T-18 | NetworkPolicy chọn nhầm label CoreDNS | Test không đạt; sửa selector dựa trên resources thật |
| T-19 | NodeLocal DNSCache được bật trong lab | Pod hỏi đúng resolver thực và policy đúng dataplane |
| T-20 | Pod hỏi trực tiếp resolver ngoài danh mục trong lab | Bị chặn hoặc phát hiện theo policy thực tế |
| T-21 | Ứng dụng lab dùng DoH tới đích chưa được duyệt | Egress governance phát hiện/xử lý; không dựa riêng vào UDP 53 |
| T-22 | Tên đã resolve nhưng Service port không có listener | DNS pass, kết nối ứng dụng fail; log phân biệt nguyên nhân |
| T-23 | DNS/route đúng nhưng TLS server certificate sai hostname | TLS client từ chối; không tắt verify |
| T-24 | DNS trả A và AAAA trong cluster dual-stack | Kiểm tra lựa chọn family, route/policy và kết nối riêng |
| T-25 | ExternalName trỏ tới service ngoài có chứng thư tên khác alias | Client xử lý SNI/hostname theo policy, không chấp nhận mismatch |
| T-26 | Cloud private endpoint sử dụng DNS nội bộ | Đúng private address và vẫn cần IAM/resource policy |
| T-27 | Resolver hybrid on-prem không khả dụng trong lab | Timeout/SERVFAIL rõ nguồn; fallback theo thiết kế |
| T-28 | Pod ở node có NodeLocal DNSCache lỗi (lab cô lập) | Sự cố được khoanh vùng theo node, có runbook phục hồi |
| T-29 | Có thay đổi Service/EndpointSlice/ConfigMap DNS trái phê duyệt trong lab | Kubernetes audit/IaC guardrail phát hiện |
| T-30 | DNS telemetry ghi hostname chứa dữ liệu giả lập nhạy cảm | Redaction và access control logs được kiểm tra |

### 25.1. Cách đo và lưu bằng chứng

Với mỗi test, lưu tối thiểu:

1. **Environment, quyền kiểm thử và thời điểm**.
2. **Container/Pod, namespace, node, image/runtime** và network attachments.
3. **Requested hostname, record type (A/AAAA/SRV), search domains, ndots và nameserver**.
4. **DNS response**: RCODE, kết quả, TTL khi có, resolver được hỏi và timeout.
5. **Network outcome**: flow allow/deny tại đúng lớp, IPv4/IPv6 và firewall rule.
6. **Application/TLS outcome**: connect, certificate validation và authorization khi có.
7. **Policy version**, log correlation, thay đổi đã thực hiện và khả năng rollback.

### 25.2. T-17: vì sao DNS allow chưa đủ?

Một Pod đã có egress rule cho **UDP/TCP 53** tới cluster DNS có thể resolve **db.data.svc.cluster.local**, nhưng **NetworkPolicy tới database port 5432** vẫn phải được kiểm soát riêng. Bài test chỉ đạt nếu:

- Pod được phép có thể resolve tên cần thiết.
- Pod chỉ tới được **những application endpoints được duyệt**.
- Pod ngoài quyền không mở được kết nối chỉ vì cùng biết DNS name.
- Database yêu cầu xác thực/dữ liệu đúng quyền.

### 25.3. T-20/T-21: không dùng kỹ thuật xâm nhập

Để xác minh hạn chế DNS bypass, chỉ sử dụng **resolver test thuộc lab** và request có giới hạn. Không gửi dữ liệu bí mật hoặc thực hiện tunneling thật qua domain của người khác; có thể kiểm chứng bằng **policy decision logs hoặc simulated event**.

### 25.4. Chứng cứ từ công cụ DNS

Với toolbox đã được phê duyệt, có thể minh họa:

~~~bash
# Kiểm tra câu trả lời A và AAAA theo resolver đã cấu hình.
dig orders.payments.svc.cluster.local A
dig orders.payments.svc.cluster.local AAAA

# Yêu cầu DNS qua TCP từ client lab; không scan hay flood.
dig +tcp orders.payments.svc.cluster.local A

# Gửi truy vấn tới một IP DNS cụ thể chỉ khi IP là resolver lab được duyệt.
dig @10.96.0.10 orders.payments.svc.cluster.local A
~~~

**dig không giống ứng dụng dùng getaddrinfo()**: nó có thể không diễn giải hosts/NSS/cache của app theo cách giống nhau. Khi chẩn đoán một service thật, so sánh kết quả **DNS tool và application runtime**.

## 26. Runbook: DNS của Pods lỗi sau khi bật default-deny egress

**Tình huống:** Đội bảo mật triển khai default-deny egress cho namespace **shop**. Ngay sau đó các Pods checkout báo **Temporary failure in name resolution**, trong khi những Pods ở namespace khác vẫn chạy. CoreDNS pods đều healthy.

### Giai đoạn 1 – Khoanh vùng và xác định tác động

1. Ghi **deployment/policy change time**, namespace, Pod labels, node placements và danh sách dịch vụ bị ảnh hưởng.
2. Xem lỗi DNS thực tế: **timeout, NXDOMAIN, SERVFAIL** hay DNS trả IP nhưng TCP không kết nối.
3. Xem **/etc/resolv.conf**, dnsPolicy/dnsConfig của Pod bị ảnh hưởng.
4. Kiểm tra cluster DNS IP/NodeLocal address thực sự được cấu hình.
5. Đọc NetworkPolicy/CNI policy có chọn đúng Pods và có **Egress DNS** phù hợp không.
6. Kiểm tra flow logs tại điểm enforcement xem có **deny UDP/TCP 53** tới resolver không.
7. Xác nhận những namespaces/Pods khác có dùng cùng DNS path hay không.

### Giai đoạn 2 – Giảm thiểu có kiểm soát

- Nếu DNS egress thực sự bị deny, bổ sung **rule hẹp cho đúng namespace/Pod/đích resolver** thay vì bỏ toàn bộ default-deny.
- Tính đến **NodeLocal DNSCache** hoặc resolver cloud nếu Pod không hỏi trực tiếp CoreDNS Pods.
- Giữ các deny rules tới data zone/management endpoints đang có hiệu lực.
- Chỉ thay cấu hình theo quyền và change/incident process; với production có thể dùng canary hoặc rollback có kiểm soát.

**Không “sửa nhanh” bằng cách cấp egress 0.0.0.0/0:any hoặc cho phép mọi DNS server ngoài Internet.** Điều này làm mất mục tiêu egress segmentation và có thể tạo đường DNS bypass.

### Giai đoạn 3 – Kiểm thử phục hồi

1. Pod checkout resolve được **orders.payments.svc.cluster.local**.
2. Ứng dụng kết nối được Orders Service theo đúng port và authorization.
3. Pod không được phép vẫn **không kết nối** tới database/management endpoints.
4. DNS từ external approved names hoạt động nếu nghiệp vụ yêu cầu.
5. Pod ở nhiều nodes/AZs/IPv4–IPv6 được kiểm tra theo topology thực tế.
6. Flow/DNS/application logs xác nhận error rate trở về baseline mà **policy không bị mở rộng**.

### Giai đoạn 4 – Nguyên nhân gốc và phòng ngừa

- Xác định policy bị thiếu DNS rule hay dùng sai DNS Pod selector/namespace label.
- Bổ sung rule baseline DNS egress theo kiến trúc **trước khi bật deny-all** trong rollout tương lai.
- Dùng CI/policy-as-code và test negative để kiểm tra cả DNS reachability lẫn service isolation.
- Gắn owner và version vào DNS network policies, cập nhật runbook khi triển khai NodeLocal hoặc đổi CNI.
- Giám sát rate timeout/SERVFAIL theo namespace và có phát hiện sớm sau change.

### 26.1. Kết luận

**CoreDNS healthy không chứng minh Pod có thể hỏi CoreDNS.** Pod DNS path còn phụ thuộc NetworkPolicy, routing, CNI, node-level DNS agent và những khác biệt theo namespace; phải xác minh **tại nguồn bị ảnh hưởng**.

## 27. Tình huống tổng hợp: một service name trả sai hệ thống sau khi chuyển namespace

Một nhóm chuyển Orders API từ namespace **shop** sang **payments** để tách quyền truy cập. Checkout vẫn gọi URL **http://orders:8080** theo tên ngắn. Trong namespace shop, một Service cũ tên **orders** chưa được gỡ và trỏ tới một backend thử nghiệm. Request của checkout vẫn resolve được và có thể gửi dữ liệu tới backend không đúng ý định.

### 27.1. Phân tích từng lớp

1. **Name resolution:** do Pod chạy trong namespace shop và dùng search domain tương ứng, tên **orders** có thể khớp Service cũ cùng namespace.
2. **Service discovery:** tên Service mới ở **payments** có FQDN khác; Kubernetes không tự hiểu ứng dụng “muốn” Service mới nếu cấu hình vẫn dùng tên ngắn.
3. **NetworkPolicy:** nếu cho phép cross-namespace quá rộng, request sai đích có thể thực sự tới backend.
4. **TLS:** nếu dùng HTTP plaintext, client không có lớp xác minh server identity bằng TLS; nếu dùng HTTPS/mTLS đúng, mismatch danh tính có thể giúp ngăn kết nối sai.
5. **Application authorization:** backend đúng cũng phải kiểm tra người gọi/workload và quyền thao tác.

### 27.2. Sơ đồ minh họa

~~~mermaid
flowchart TD
    P["checkout Pod / namespace shop"] --> SHORT["Query: orders"]
    SHORT --> SEARCH["Search domain: shop.svc.cluster.local"]
    SEARCH --> OLD["Service orders.shop.svc.cluster.local (cũ)"]
    P -. "Ứng dụng dự định dùng" .-> NEW["Service orders.payments.svc.cluster.local (mới)"]
    OLD --> WRONG["Backend thử nghiệm / không đúng mục tiêu"]
    NEW --> RIGHT["Orders backend được phê duyệt"]
    P -. "Sửa URL thành FQDN + policy + identity" .-> NEW
~~~

### 27.3. Khắc phục

- Sửa cấu hình ứng dụng thành **orders.payments.svc.cluster.local** hoặc tên dịch vụ rõ ràng được tổ chức quản lý.
- Rà soát Service cũ: nếu không còn hợp lệ, loại bỏ theo change control và tránh bỏ qua các clients khác vẫn phụ thuộc.
- Siết **cross-namespace network access** và quyền sửa Service/EndpointSlice.
- Dùng **TLS/mTLS với service identity đúng** cho các đường nhạy cảm.
- Xác minh request sau thay đổi tới đúng backend bằng access logs, service tracing và DNS resolution.
- Đặt test bảo đảm **Service cũ không được checkout sử dụng** khi release mới.

### 27.4. Vì sao chỉ đổi DNS không đủ?

FQDN giúp chỉ rõ nơi muốn tới nhưng không tự ngăn:

- Workload không đáng tin gọi Service mới nếu network policy quá rộng.
- Backend bị chiếm quyền hoặc cấu hình sai TLS.
- Người gọi có token không đủ quyền nhưng API bỏ authorization.
- Runtime giữ DNS cache hoặc connection pool cũ sau rollout.

**Kết quả an toàn cần đủ cả tên đích đúng, đường đi được duyệt, danh tính server xác minh được và quyền ứng dụng hợp lệ.**

## 28. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “Container luôn dùng DNS giống host” | Chẩn đoán sai resolver và route | Đọc file/config trong container và runtime |
| “127.0.0.1 của Pod là host DNS” | Truy vấn tới loopback sai namespace | Xác định nameserver thật, hostNetwork/NodeLocal nếu có |
| “127.0.0.11 là DNS mặc định của Kubernetes” | Nhầm Docker embedded DNS với CoreDNS | Phân biệt runtime/network mode |
| “Docker default bridge tự resolve mọi container names” | Tên không được đăng ký theo cơ chế kỳ vọng | User-defined network hoặc service discovery được duyệt |
| “Docker containers cùng tên ở hai networks sẽ nhìn thấy nhau” | Sai phạm vi discovery và trust | Kiểm tra network attachments/aliases |
| “Đổi IP Pod rồi sửa mọi config theo IP mới” | Cấu hình dễ lỗi sau scale/recreate | Dùng Service DNS, xử lý retry/cache hợp lý |
| “Tên ngắn orders luôn chỉ Service mong muốn ở mọi namespace” | Định tuyến nhầm Service cùng tên | Dùng FQDN rõ ràng và test namespace |
| “cluster.local là domain bắt buộc của mọi Kubernetes” | Truy vấn sai cluster có domain khác | Kiểm tra cluster domain thực |
| “dnsPolicy Default tương đương ClusterFirst” | Service DNS có thể không hoạt động | Chọn policy theo nhu cầu và hostNetwork |
| “Thay ndots không có tác động bảo mật” | Truy vấn nhiều hơn, có thể sai đích hoặc lộ tên | Đo query pattern và kiểm thử FQDN |
| “Có A record nên HTTP/TCP nhất định được” | Lỗi service/route/firewall không được thấy | Tách DNS resolution khỏi kết nối |
| “Headless Service có load balancing giống ClusterIP” | Client chọn endpoint trực tiếp và hành vi khác | Hiểu endpoint records, readiness và client selection |
| “ExternalName tự tạo TLS đúng cho alias” | Chứng thư name mismatch hoặc trust sai | Kiểm tra TLS hostname theo endpoint thực |
| “Chỉ cần cho UDP/53 là DNS luôn đủ” | TCP fallback hoặc NodeLocal path vẫn lỗi | Đánh giá UDP/TCP, dataplane và CNI |
| “NetworkPolicy yaml có mặt nghĩa là có hiệu lực” | CNI không hỗ trợ/chọn sai Pods | Negative tests và effective policy |
| “K8s NetworkPolicy mặc định chặn mọi FQDN ngoài danh sách” | Built-in API không phải DNS/FQDN firewall | Dùng egress controls phù hợp có hỗ trợ |
| “Cho phép DNS tới tên A thì IP được tự cho phép” | Kết nối ứng dụng không theo DNS policy | Áp egress IP/service policy riêng |
| “CoreDNS log thấy hết DNS traffic” | DoH, cache hoặc resolver khác không xuất hiện | Theo dõi resolver/path coverage |
| “NXDOMAIN giống timeout” | Sửa sai nguồn lỗi | Phân biệt RCODE với network failure |
| “CoreDNS khỏe tức Pod không thể lỗi DNS” | NetworkPolicy/node/CNI chặn query | Test từ Pod và node bị ảnh hưởng |
| “Private endpoint không cần IAM/TLS” | Dữ liệu cloud vẫn có thể bị truy cập sai | Network + service identity + resource policy |
| “DNSSEC xác thực toàn bộ API” | Nhầm dữ liệu DNS với TLS/authz | Kết hợp DNS integrity, TLS và IAM |
| “Chỉ kiểm tra IPv4 là đủ” | AAAA/IPv6 policy có thể khác | Test dual-stack theo topology |
| “Cứ mở DNS tới Internet để khắc phục” | Bypass governance, có thể rò rỉ tên nội bộ | Chọn resolver được duyệt và sửa đúng rule |
| “Có log DNS nghĩa là không có dữ liệu cá nhân” | Query names có thể chứa thông tin nhạy cảm | RBAC, retention và redaction |

## 29. Câu hỏi và bài tập tự kiểm tra

### Câu hỏi 1

Vì sao **127.0.0.1** trong một container thường không trỏ tới DNS của host?

**Gợi ý:** network namespace và loopback riêng; cần xác định host network, Docker embedded DNS hoặc resolver trong namespace.

### Câu hỏi 2

Khác biệt quan trọng giữa **Docker embedded DNS tại 127.0.0.11** và **Kubernetes CoreDNS** là gì?

**Gợi ý:** Docker dùng service/container discovery trên user-defined networks; Kubernetes có DNS service ở cấp cluster gắn với Kubernetes Service/Endpoint records.

### Câu hỏi 3

Vì sao hai containers ở Docker default bridge có thể không resolve tên nhau giống hai services trong một Compose user-defined network?

**Gợi ý:** phạm vi và cơ chế DNS/service discovery khác nhau giữa các mạng.

### Câu hỏi 4

Pod dùng tên ngắn **orders** có thể resolve sai namespace không? Cách giảm rủi ro?

**Gợi ý:** search suffix ưu tiên namespace hiện tại; dùng FQDN rõ ràng cho dependency cross-namespace.

### Câu hỏi 5

**dnsPolicy: Default** và **dnsPolicy: ClusterFirst** khác gì? Với hostNetwork cần lưu ý điều gì?

**Gợi ý:** một policy kế thừa DNS node; policy còn lại ưu tiên cluster DNS; hostNetwork có ClusterFirstWithHostNet khi muốn Service DNS.

### Câu hỏi 6

Vì sao thay **ndots:5** có thể thay đổi số lượng DNS queries và độ trễ?

**Gợi ý:** số dấu chấm quyết định thứ tự thử tên ghép search domain và tên tuyệt đối theo resolver.

### Câu hỏi 7

Một Pod trả đúng IP Service từ DNS nhưng không kết nối được TCP. Những lớp nào cần kiểm tra?

**Gợi ý:** Service/EndpointSlice, port/targetPort, listener, route, CNI, NetworkPolicy, firewall và application readiness.

### Câu hỏi 8

Vì sao một NetworkPolicy cho DNS egress tới CoreDNS Pods có thể không hoạt động khi bật **NodeLocal DNSCache**?

**Gợi ý:** điểm đích thực của DNS query có thể là resolver node/link-local; CNI handling và label/selector policy khác.

### Câu hỏi 9

Một container chỉ cho phép DNS qua CoreDNS nhưng ứng dụng dùng DoH riêng. Điều gì cần kiểm soát?

**Gợi ý:** DNS SDK có thể bỏ qua /etc/resolv.conf; cần egress policy và resolver governance, không chỉ UDP 53.

### Câu hỏi 10

**ExternalName Service** có tự cấp chứng thư TLS hợp lệ cho tên alias trong cluster không?

**Gợi ý:** không; alias DNS không thay đổi danh tính endpoint trong certificate/SNI.

### Câu hỏi 11

Vì sao một kết quả **NXDOMAIN** và một **DNS timeout** cần hướng xử lý khác nhau?

**Gợi ý:** NXDOMAIN là phản hồi tên không tồn tại; timeout có thể do query không đến DNS server hoặc server không trả lời.

### Câu hỏi 12

Container có thể dùng **headless Service** để tìm từng Pod endpoint. Vì sao phải xem readiness và không hardcode IP?

**Gợi ý:** endpoints thay đổi theo scale/restart; DNS records và connection pool có thể không cập nhật đồng thời.

### Câu hỏi 13

Vì sao một hostname được private DNS trả IP nội bộ không chứng minh workload có quyền đọc object storage hay database?

**Gợi ý:** DNS chỉ định vị, mạng cho kết nối, TLS xác minh endpoint, IAM và application authorization mới cấp quyền.

### Câu hỏi 14

DNS query rate tăng mạnh sau đổi ndots nhưng không có dữ liệu chứng minh xâm nhập. Vì sao không nên kết luận DNS tunneling?

**Gợi ý:** resolver search expansion, retry, negative caching và lỗi cấu hình cũng tăng query volume.

### Bài tập thiết kế

Một hệ thống gồm **Docker Compose** cho phát triển cục bộ và **Kubernetes production** với namespace **shop**, **payments**, **data**; có CoreDNS, NodeLocal DNSCache, private database, external payment partner API, cloud private endpoint và API gateway.

Hãy thực hiện:

1. Vẽ **resolver path** riêng cho Docker user-defined network và Kubernetes Pod có ClusterFirst.
2. Xác định tên Service/FQDN chuẩn, search domains và ảnh hưởng của **ndots**.
3. Lập ma trận **workload → resolver được phép → tên dịch vụ → protocol/port → service identity**.
4. Thiết kế NetworkPolicy egress cho Pod checkout để hỏi đúng DNS resolver và kết nối đúng Orders API.
5. Giải thích điều kiện khiến mẫu policy chọn CoreDNS Pods không phù hợp với **NodeLocal DNSCache**.
6. So sánh ClusterIP và headless Service, giải thích readiness, cache và client connection reuse.
7. Thiết kế kết nối **private DNS → cloud private endpoint → IAM/resource policy** cho object storage.
8. Đề xuất egress governance để phát hiện hoặc giới hạn truy vấn DoH/DoT ngoài chính sách mà không chặn bừa các API HTTPS hợp lệ.
9. Xây dựng ít nhất **mười positive/negative tests**, gồm sai namespace, NXDOMAIN, DNS timeout, NetworkPolicy deny, external forwarding failure, cache stale, IPv6, ExternalName/TLS mismatch và Docker network isolation.
10. Xây dựng log correlation từ **application, CoreDNS, NodeLocal, CNI, cloud firewall, Kubernetes audit và API logs**.
11. Viết runbook khi default-deny egress vừa được bật khiến Pod không thể resolve tên Service.
12. Đưa ra các điều kiện chứng minh **DNS đã resolve đúng nhưng application authorization vẫn có thể từ chối**.

**Tiêu chí đạt:** xác định chính xác **ai phân giải tên nào, hỏi resolver nào, qua đường mạng nào, dữ liệu DNS được tin đến đâu, và application có quyền kết nối/thao tác gì sau khi đã resolve**.

## 30. Những điều cần ghi nhớ

- **DNS resolution trong container phụ thuộc runtime, network namespace, resolver configuration và ứng dụng**; không mặc nhiên giống DNS của host.
- **Docker embedded DNS 127.0.0.11** thuộc những ngữ cảnh Docker network hỗ trợ; **Kubernetes CoreDNS** phục vụ DNS-based cluster service discovery qua cơ chế khác.
- **/etc/hosts, /etc/resolv.conf, NSS, runtime resolver và cache** đều có thể tác động kết quả; đọc cấu hình trong container và kiểm tra ứng dụng thực tế.
- **Kubernetes Service DNS có phạm vi namespace/domain**: tên ngắn chịu search domains và ndots; dùng FQDN rõ khi cần tránh nhầm.
- **ClusterIP, headless Service, EndpointSlice và StatefulSet** có semantics khám phá endpoint khác nhau; DNS không đồng nghĩa load balancing hoặc readiness tự động cho mọi client.
- **dnsPolicy, dnsConfig, NodeLocal DNSCache và CoreDNS forwarding** quyết định resolver path; không tự thay bằng public DNS để che lỗi nội bộ.
- **DNS sử dụng cả UDP/TCP 53 trong nhiều tình huống**, nhưng DNS over HTTPS/TLS hoặc ứng dụng có resolver riêng có thể đi ngoài chính sách truyền thống.
- **NetworkPolicy DNS egress phải khớp endpoint DNS thực và CNI enforcement**; built-in NetworkPolicy không tự là FQDN-aware firewall.
- **DNS answer không xác thực server hay cấp quyền dữ liệu**; cần TLS/mTLS identity, network segmentation, IAM và API authorization.
- **Phân biệt NXDOMAIN, SERVFAIL, timeout, TCP failure, TLS failure và HTTP 401/403** để sửa đúng lớp.
- **Bảo vệ quyền sửa DNS/Service/Endpoint records và resolver forwarding**, giám sát DNS query bất thường nhưng không suy luận tấn công chỉ từ một metric.
- **Kiểm thử positive và negative cases trong lab được phép**, bảo đảm service hợp lệ resolve/kết nối đúng và nguồn trái quyền bị chặn dù biết DNS name.




