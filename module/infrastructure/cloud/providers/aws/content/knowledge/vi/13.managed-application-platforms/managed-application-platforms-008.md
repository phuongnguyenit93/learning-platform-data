# Lightsail instance và phạm vi sử dụng phù hợp

> **Chương:** Nền tảng ứng dụng quản lý  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS từ Region/AZ, IAM và VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; thực hành chọn dịch vụ, thiết kế hệ thống an toàn, quan sát được, có khả năng phục hồi và kiểm soát chi phí.

Một doanh nghiệp nhỏ cần đưa website giới thiệu, trang WordPress hoặc ứng dụng web đơn giản lên Internet. Nếu sử dụng Amazon EC2, nhóm phải cân nhắc AMI, instance type, EBS, VPC, subnet, route table, Security Group, Elastic IP và nhiều thành phần khác. **Amazon Lightsail** gom những lựa chọn phổ biến thành một trải nghiệm đơn giản hơn: chọn **blueprint**, **instance plan (bundle)**, Region/Availability Zone rồi tạo một máy chủ có mạng và dung lượng lưu trữ cơ bản.

Lightsail giúp giảm số quyết định về hạ tầng ở bước khởi đầu, **không biến máy chủ ảo thành dịch vụ tự quản trị toàn bộ ứng dụng**. Người vận hành vẫn chịu trách nhiệm đối với hệ điều hành, bản vá, tài khoản SSH, cấu hình web server, dữ liệu ứng dụng, chứng chỉ và kế hoạch sao lưu. Bài học tập trung vào **Lightsail instance** và cách nhận biết khi nào nó phù hợp hơn EC2, Elastic Beanstalk, App Runner hoặc container platform.

Các ví dụ sử dụng tên miền `example.com`, IP tài liệu và tên tài nguyên giả định. Khả năng cấp tài nguyên, kiểu mạng IPv4/IPv6, tên gói, giá và tính năng Lightsail thay đổi theo Region và thời điểm; khi triển khai thật phải đối chiếu trong AWS Console, API và bảng giá hiện hành.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **Lightsail instance**, **blueprint**, **bundle**, **Region**, **Availability Zone**, **static IP** và **instance firewall**.
2. Tạo kiến trúc cơ bản `DNS → Lightsail instance → ứng dụng` với HTTP/HTTPS, kết nối SSH an toàn và địa chỉ IP ổn định.
3. Phân biệt **root disk**, **attached block storage**, **snapshot** và **application/database backup**.
4. Đánh giá khả năng mở rộng, vận hành nhiều instance sau Lightsail load balancer và giới hạn dự phòng một Region.
5. Tính đến **chi phí gói**, lưu trữ bổ sung, snapshots, IP, traffic và những tài nguyên Lightsail khác.
6. Chọn đúng dịch vụ dựa trên nhu cầu: website nhỏ, thử nghiệm, hệ thống ổn định hoặc ứng dụng production phức tạp.
7. Dùng AWS Console và AWS CLI để kiểm tra cấu hình, bảo mật và tài nguyên trước khi thực hiện thay đổi.

## 2. Lightsail instance thực chất là gì?

**Amazon Lightsail** là dịch vụ điện toán đám mây nhằm đơn giản hóa việc triển khai những ứng dụng, website và workload nhỏ hoặc có nhu cầu tài nguyên tương đối dễ dự đoán. **Lightsail instance** là một **máy chủ ảo**, thường chạy Linux/Unix hoặc Windows theo plan và blueprint được hỗ trợ.

Một instance bao gồm những thành phần cơ bản:

| Thành phần | Ý nghĩa | Người vận hành cần quyết định |
| --- | --- | --- |
| **Blueprint** | Hệ điều hành hoặc image có ứng dụng dựng sẵn | Chọn OS trống hay WordPress/LAMP/ngăn xếp phù hợp |
| **Bundle/instance plan** | Gói tài nguyên tính toán và lưu trữ | CPU, RAM, dung lượng root disk, mức transfer, giá |
| **Region và AZ** | Vị trí chạy máy ảo | Độ trễ, dữ liệu, AZ được hỗ trợ và kế hoạch chịu lỗi |
| **Root disk** | Ổ đĩa hệ thống gắn với instance | Dung lượng, cách lưu file và chiến lược snapshot |
| **Networking** | Private address, địa chỉ công khai theo loại plan, firewall | Cổng nào mở, IPv4/IPv6, DNS và truy cập quản trị |
| **Key pair/credentials** | Thông tin truy cập quản trị ban đầu | SSH key Linux hoặc cách nhận/quản lý mật khẩu Windows |
| **Monitoring** | Chỉ số instance và cảnh báo được Lightsail hỗ trợ | CPU, burst, network, disk, trạng thái/chi phí |

Một gói Lightsail thường công bố tài nguyên theo tháng, thuận tiện dự toán hơn việc lựa chọn từng tài nguyên EC2/EBS/network. Tuy nhiên, **tổng hóa đơn không nhất thiết bằng đúng giá một bundle** vì còn có thể phát sinh dịch vụ bổ sung, lưu trữ snapshots, data transfer vượt allowance và các loại địa chỉ/tài nguyên theo quy tắc giá hiện hành.

### 2.1. Lightsail “managed” đến mức nào?

Không nên nhầm **Lightsail đơn giản hóa hạ tầng** với **ứng dụng được AWS vận hành hoàn toàn**.

| AWS/Lightsail quản lý | Người sở hữu workload vẫn quản lý |
| --- | --- |
| Hạ tầng vật lý và máy chủ nền tảng | Bản vá hệ điều hành và phần mềm trong instance |
| Cung cấp máy ảo, plan và storage đi kèm | Web server, runtime, ứng dụng, cấu hình và lỗi triển khai |
| Các thao tác tạo/xóa, snapshot ở mức dịch vụ | Backup dữ liệu có kiểm chứng, khôi phục ứng dụng |
| Mạng/địa chỉ và instance firewall cấp Lightsail | Quy tắc truy cập, SSH key, firewall hệ điều hành, TLS |
| Metrics cơ bản và một số cơ chế cảnh báo | Application logs, tracing, giám sát nghiệp vụ, phản ứng sự cố |

Ví dụ: triển khai WordPress blueprint không có nghĩa AWS tự kiểm thử và cập nhật tất cả plugin của website hoặc giữ bản sao nhất quán của mọi giao dịch mới. Nếu trang bị tấn công vì plugin lỗi thời, đội vận hành vẫn cần vá, điều tra và khôi phục.

### 2.2. Lightsail không chỉ có instance

Ngoài instance, Lightsail có những thành phần được quản lý ở mức khác nhau như:

- **Static IP**, DNS zones và bản ghi DNS.
- **Block storage disks** và snapshots.
- **Load balancer** cho các instance Lightsail phù hợp.
- **Managed relational database** theo những plan/engine được hỗ trợ.
- **Object storage** và **Lightsail container services**, cùng một số tùy chọn phân phối nội dung.

Bài học **không đồng nhất** các sản phẩm này với instance. Ví dụ **Lightsail container service** là mô hình triển khai container riêng, còn một Lightsail instance vẫn là máy ảo phải quản trị OS. Lightsail managed database giảm phần vận hành database so với tự cài MySQL trong instance, nhưng bạn vẫn chịu trách nhiệm schema, truy cập, query và dữ liệu.

## 3. Blueprint và bundle: hai quyết định khác nhau

Khi tạo instance, giao diện thường yêu cầu chọn **blueprint** rồi chọn **instance plan**.

### 3.1. Blueprint là gì?

**Blueprint** xác định OS hoặc một ứng dụng/ngăn xếp phần mềm được cài sẵn:

| Nhóm blueprint | Ví dụ theo tính năng được cung cấp | Khi phù hợp |
| --- | --- | --- |
| **OS only** | Ubuntu, Amazon Linux, Debian, Windows Server theo Region | Muốn tự cài Nginx, Java, Node.js, PostgreSQL client... |
| **Application + OS** | WordPress, LAMP, các app/stack phổ biến | Muốn khởi động nhanh một mô hình web quen thuộc |
| **Blueprint tùy mục đích** | App server hoặc nền tảng khác trong danh mục | Khi đã đánh giá hỗ trợ bảo mật, cập nhật và backup |

Image ứng dụng dựng sẵn giúp triển khai nhanh nhưng có thể chứa mặc định về web server, đường dẫn config, tài khoản và phiên bản runtime. **Đọc hướng dẫn blueprint** trước khi nâng cấp; không dựa vào việc cài sẵn để kết luận cấu hình đã đạt chuẩn production.

### 3.2. Bundle/plan là gì?

**Bundle** là gói tài nguyên được chọn lúc tạo instance. Những thuộc tính thường cần so:

- **vCPU và CPU performance model**: khả năng xử lý, burst capacity nếu plan có đặc tính burst.
- **RAM**: đủ cho runtime, cache, connection pool và OS hay không.
- **Root SSD storage**: chứa hệ thống, ứng dụng và dữ liệu đang đặt trên root disk.
- **Data transfer allowance**: giới hạn lưu lượng bao gồm trong plan theo chính sách tính phí cụ thể.
- **Kiểu nền tảng và network**: Linux/Windows, IPv4/IPv6, loại instance và khả năng của Region.

Một workload **Java/JVM** có RAM quá thấp có thể liên tục bị OOM hoặc GC làm tăng độ trễ dù CPU không cao. Ngược lại, một landing page tĩnh có thể đủ với plan nhỏ, nhưng khi cần xử lý ảnh hay job nền, CPU burst và storage I/O trở thành giới hạn.

**Lưu ý về CPU burst:** một số Lightsail instance plans có khả năng chạy vượt mức CPU nền trong thời gian ngắn nhờ burst capacity. Nếu CPU liên tục cao, hiệu năng có thể không giữ được như benchmark ngắn. Quan sát CPU utilization và burst metrics liên quan, kiểm thử tải bền vững thay vì chỉ chạy vài request.

### 3.3. Ví dụ chọn gói dựa trên yêu cầu

Giả sử một ứng dụng Java Spring Boot có:

~~~text
Ứng dụng: catalog API + trang quản trị nội bộ
Tải hiện tại: khoảng 10 request/giây, tăng theo chiến dịch
Runtime: JVM, cần 2 GiB RAM ở cấu hình kiểm thử
Storage: 10 GiB dữ liệu upload, còn tiếp tục tăng
Yêu cầu: HTTPS, backup hằng ngày, RTO 4 giờ
~~~

Quy trình chọn plan:

1. Đo **RAM ổn định + JVM heap + native memory + OS + database/proxy nếu cài chung**.
2. Đo CPU p95/p99, khoảng burst và thời gian job nền.
3. Tính disk với OS, logs, artifacts, uploads, backup tạm và biên mở rộng.
4. Ước tính outbound transfer từ số request và dung lượng response.
5. Đối chiếu plan thực tế trong Region, sau đó **benchmark** trên cùng runtime/image.

Không có “plan chính xác” chỉ từ 10 req/s: cùng request rate nhưng query/response size và workload CPU khác nhau có thể cần cấu hình hoàn toàn khác.

## 4. Region, Availability Zone và giới hạn chịu lỗi

Một Lightsail instance được tạo tại **một Availability Zone** trong **một AWS Region** được hỗ trợ. Region ảnh hưởng độ trễ, tuân thủ vị trí dữ liệu và các dịch vụ có thể kết nối; AZ là miền lỗi cấp hạ tầng.

### 4.1. Single instance là một điểm lỗi đơn

~~~mermaid
flowchart LR
    U["Người dùng"] --> DNS["DNS"]
    DNS --> VM["Lightsail instance\n1 AZ"]
    VM --> APP["Web server + ứng dụng"]
    VM --> DATA["File/DB trên cùng instance"]
~~~

Ưu điểm: ít thành phần, dễ học và quản lý. Nhược điểm:

- Khi instance dừng, OS treo, disk hỏng hoặc AZ lỗi, **ứng dụng có thể ngừng phục vụ**.
- Nếu cả ứng dụng và database nằm trên một instance, backup/restore và kế hoạch phục hồi phức tạp hơn.
- Một bản cập nhật lỗi có thể tác động đồng thời toàn bộ dịch vụ.

Snapshot giúp tạo **khả năng khôi phục**, nhưng không biến single instance thành HA ngay lập tức. Nếu cần mục tiêu uptime rất cao hoặc RTO ngắn, thiết kế phải mở rộng hơn.

### 4.2. Mở rộng trong một Region

Một thiết kế nhiều instance có thể dùng **Lightsail load balancer**, nhiều web instances ở các AZ phù hợp và database riêng:

~~~mermaid
flowchart TB
    U["Người dùng"] --> DNS["DNS: app.example.com"]
    DNS --> LB["Lightsail load balancer\nHTTP/HTTPS + health checks"]
    subgraph REG["Một AWS Region"]
      subgraph A["AZ A"]
        WA["Lightsail web instance A\nstateless"]
      end
      subgraph B["AZ B"]
        WB["Lightsail web instance B\nstateless"]
      end
      DB["Lightsail managed database\nHA nếu plan hỗ trợ và đã bật"]
    end
    LB --> WA
    LB --> WB
    WA --> DB
    WB --> DB
    WA -.->|"Ảnh/tệp dùng chung"| OBJ["Object storage / S3 theo nhu cầu"]
    WB -.->|"Ảnh/tệp dùng chung"| OBJ
~~~

Thiết kế này giảm phụ thuộc vào **một web instance** nhưng không tự bảo đảm:

- Database có dự phòng khi lỗi AZ.
- Session, upload và dữ liệu cần thiết được chia sẻ giữa các instances.
- Hệ thống còn đủ **capacity** khi mất một AZ.
- Load balancer, secrets, job nền, DNS và nguồn dữ liệu đáp ứng RTO/RPO.

Không nên cố “gắn hai instance sau LB” trong khi cả hai lưu dữ liệu đơn hàng vào file local riêng; kết quả có thể không nhất quán giữa các request.

### 4.3. Mục tiêu phục hồi

| Khái niệm | Câu hỏi |
| --- | --- |
| **RTO** | Sau lỗi mất bao lâu ứng dụng phải phục hồi chức năng? |
| **RPO** | Chấp nhận mất tối đa bao nhiêu dữ liệu tính theo thời gian? |
| **HA** | Trong những lỗi nào ứng dụng vẫn tiếp tục phục vụ được mà không cần restore thủ công? |
| **DR** | Khi mất tài nguyên, AZ hoặc Region, làm thế nào khôi phục ứng dụng và dữ liệu? |

Snapshot một lần/ngày **không** đáp ứng RPO một phút cho dữ liệu đơn hàng liên tục phát sinh. Nhiều AZ **không** tự xử lý sự cố toàn Region hay xóa nhầm dữ liệu được sao chép sang bản dự phòng.

## 5. IP, firewall và DNS của Lightsail instance

### 5.1. Public IP, private IP và static IP

Lightsail instance có **private network address** dùng trong mô hình mạng được hỗ trợ. Tùy loại plan và cách cấu hình, instance có **public IPv4**, **IPv6**, hoặc tùy chọn khác.

Với website cần tên miền trỏ tới một máy ảo, nên xem xét **static IPv4 address**:

- Địa chỉ công khai tĩnh giúp tránh việc DNS phải thay đổi khi instance được thay thế hoặc có thao tác mạng liên quan.
- Static IP là tài nguyên riêng cần **allocate/attach** theo Region và điều kiện hỗ trợ.
- Có thể gắn lại static IP tới instance thay thế theo quy tắc dịch vụ để giảm thời gian đổi DNS; vẫn cần DNS TTL và ứng dụng đã sẵn sàng.
- **Địa chỉ công khai mặc định** không nên được xem như một định danh vĩnh viễn trong mọi vòng đời stop/rebuild.
- Kiểm tra **giá và chính sách charge của static IP/public IPv4** theo tình trạng sử dụng, thời gian gắn/không gắn và plan hiện hành; không suy rằng tất cả public IP đều miễn phí.

Nếu dùng **IPv6-only plan** trong Region hỗ trợ, phải hiểu client/đích/ứng dụng phụ thuộc IPv4 như thế nào. Không cấu hình chỉ AAAA rồi mặc định mọi người dùng IPv4 đều truy cập được.

### 5.2. Instance firewall

Lightsail có firewall riêng cho instance. Nó thường điều khiển **inbound traffic** theo protocol, port và địa chỉ nguồn; các quy tắc IPv4 và IPv6 phải được kiểm tra riêng theo tính năng hỗ trợ.

| Mục đích | Protocol/port | Nguồn nên cho phép |
| --- | --- | --- |
| Truy cập website HTTP hoặc redirect sang HTTPS | TCP 80 | Public nếu website thật sự công khai |
| Website HTTPS | TCP 443 | Public nếu website thật sự công khai |
| Quản trị Linux bằng SSH | TCP 22 | **Chỉ IP/mạng quản trị đáng tin**, khi có thể |
| Quản trị Windows RDP | TCP 3389 | **Giới hạn IP/VPN**, không mở Internet rộng |
| Database trong instance | MySQL 3306/PostgreSQL 5432 | Không mở public nếu không thực sự cần và được kiểm soát |

**Không đồng nhất Lightsail firewall với EC2 Security Group.** Lightsail trình bày bộ điều khiển mạng đơn giản hơn; không giả định có toàn bộ cơ chế tham chiếu SG, cấu hình subnet/NACL hoặc rule egress chi tiết như EC2. Nếu cần phân đoạn mạng phức tạp, có thể phải chọn EC2/VPC chuyên dụng.

Ngoài Lightsail firewall, kiểm tra firewall trong **hệ điều hành** (ví dụ `ufw`/`firewalld` hoặc Windows Firewall) và cấu hình listener ứng dụng. Mở Lightsail TCP 443 không giúp ích nếu Nginx chưa lắng nghe port 443 hoặc chứng chỉ TLS không hợp lệ.

### 5.3. DNS và HTTPS

Ví dụ website:

~~~text
Domain:         www.example.com
Static IPv4:    198.51.100.25  (IP tài liệu minh họa)
DNS record:     www.example.com A → 198.51.100.25
Ứng dụng:       Nginx/Apache trên Lightsail :80/:443
~~~

Sơ đồ luồng:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as DNS resolver
    participant V as Lightsail instance
    B->>R: Tra www.example.com
    R-->>B: 198.51.100.25 (minh họa)
    B->>V: HTTPS tới :443
    V-->>B: Trang web / API response
~~~

Bạn có thể quản lý bản ghi bằng **Lightsail DNS zone** hoặc **Amazon Route 53**, tùy nhu cầu. Đảm bảo domain thực sự ủy quyền đến authoritative DNS đúng và kiểm tra **TTL** khi đổi IP. Có thể dùng chứng chỉ Let's Encrypt trên web server nếu tự quản lý TLS, hoặc cơ chế chứng chỉ của Lightsail load balancer khi ứng dụng đứng sau LB phù hợp.

**Chú ý:** IP `198.51.100.25` là địa chỉ chỉ dùng cho tài liệu, không phải IP thực. Một bản ghi DNS chính xác không bảo đảm website chạy được: listener, OS firewall, Lightsail firewall và TLS phải đồng thời đúng.

## 6. Tạo instance bằng Console: quy trình có kiểm soát

Mục tiêu bài thực hành là dựng **website thử nghiệm** trên Linux instance có tên `lab-lightsail-web`. Chỉ thực hiện trong tài khoản/Region được phép, xem chi phí trước khi tạo và **không sử dụng dữ liệu thật của khách hàng**.

### 6.1. Chuẩn bị

1. Kiểm tra tài khoản, Region và **AWS Budgets/chi phí dự kiến**.
2. Quyết định dùng OS-only blueprint hay một ứng dụng dựng sẵn.
3. Chọn bundle đủ RAM/CPU/storage theo nhu cầu lab; ghi lại giá, allowance và điều kiện charge.
4. Chọn AZ trong Region được hỗ trợ; ghi rõ việc đây là **một instance, một AZ**.
5. Tạo và giữ an toàn SSH key pair hoặc dùng phương thức kết nối do Lightsail Console hỗ trợ.

### 6.2. Tạo qua Lightsail Console

1. Vào **Amazon Lightsail → Instances → Create instance**.
2. Chọn Region/AZ và blueprint Linux phù hợp.
3. Xem lại bundle, network/IP type và dung lượng root disk.
4. Nếu có ô thêm launch script/user data, chỉ dùng script đã được review.
5. Gắn tên `lab-lightsail-web` và tag phục vụ quản lý như `Environment=lab`.
6. Tạo instance, xem trạng thái và private/public IP sau khi provisioning.
7. Kiểm tra firewall inbound; chỉ mở `80/443` cho web và giới hạn `22` theo nguồn quản trị.
8. Khi cần tên miền ổn định, cân nhắc static IP và cấu hình DNS/TLS.

Giao diện cụ thể và tên loại bundle có thể thay đổi. Đối với environment production, nên ghi lại toàn bộ cấu hình thành runbook/IaC/API workflow để có thể tái tạo.

### 6.3. Kết nối SSH an toàn

Linux instance có thể được quản trị bằng **browser-based SSH** của Lightsail Console khi hỗ trợ hoặc SSH client trên máy quản trị.

~~~bash
# Thay tên user và địa chỉ theo blueprint/instance thật
ssh -i ./lightsail-lab-key.pem ubuntu@PUBLIC_IP
~~~

Quyền file private key cần hạn chế, không đưa key vào Git, chat, tài liệu công khai hoặc image Docker. Username thay đổi theo blueprint: không mặc định mọi AMI/blueprint đều dùng `ubuntu`. Khi SSH từ máy quản trị, Lightsail/OS firewall phải cho phép nguồn thực tế.

Với Windows, phương thức quản trị có thể là browser-based RDP hoặc RDP client theo cấu hình được Lightsail hỗ trợ; phải bảo vệ mật khẩu và hạn chế cổng RDP.

### 6.4. Triển khai website tối giản trên Ubuntu (lab)

Chỉ chạy trên **instance lab Ubuntu/Debian** đã xác minh không chứa dữ liệu quan trọng. Ví dụ cài một trang HTML bằng Nginx:

~~~bash
sudo apt-get update
sudo apt-get install -y nginx
sudo systemctl enable --now nginx
sudo systemctl status nginx

cat <<'HTML' | sudo tee /var/www/html/index.html >/dev/null
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Lightsail Lab</title></head>
<body><h1>Website đang chạy trên Lightsail</h1></body>
</html>
HTML

curl -I http://127.0.0.1/
~~~

Đây là **HTTP lab**. Trước khi public website thật, cần HTTPS với certificate hợp lệ, patch/update, backup và các chính sách bảo mật khác. Không cấu hình HTTP cơ bản như giải pháp production hoàn chỉnh.

### 6.5. Sau khi triển khai, cần kiểm tra bốn lớp

~~~text
Client → DNS A/AAAA record
       → Static/public IP của instance
       → Lightsail firewall + OS firewall
       → Nginx/ứng dụng đang nghe 80/443
~~~

Nếu `curl http://127.0.0.1` trong máy trả 200 nhưng truy cập ngoài bị timeout, nghiêng về IP, route, firewall hoặc DNS. Nếu ngoài truy cập được HTTP mà HTTPS lỗi, xem port 443, TLS listener và certificate.

## 7. Storage: root disk, attached disk và backup

### 7.1. Root disk

Root disk đi cùng bundle, chứa OS và dữ liệu bạn ghi trong instance. Nếu database, logs và uploads đều được lưu ở root disk, việc tăng dữ liệu có thể làm đầy ổ, khiến package manager, database hoặc application không hoạt động.

**Không nên để root disk làm điểm lưu dữ liệu duy nhất** cho hệ thống cần khôi phục. Có thể tách dữ liệu sang disk gắn thêm, object storage hoặc managed database theo nhu cầu.

### 7.2. Attached block storage disk

Lightsail cung cấp disk gắn thêm theo khả năng của Region và OS/instance:

- Có dung lượng, chi phí và vòng đời **riêng**.
- Phải **attach**, tạo filesystem nếu disk mới, **mount** và bảo đảm mount lại sau restart.
- Disk có quan hệ với AZ, nên không giả định được attach tùy ý sang instance ở AZ khác mà không có bước snapshot/khôi phục.
- Nếu app cần đọc/ghi song song từ nhiều instance, một block disk gắn một instance **không mặc nhiên là shared filesystem**.

### 7.3. Snapshots

**Snapshot** là cơ chế lưu trạng thái của instance hoặc disk theo khả năng sản phẩm. Có thể sử dụng **manual snapshot** hoặc tùy chọn **automatic snapshots** nếu loại tài nguyên và Region hỗ trợ.

| Đối tượng | Có thể dùng snapshot cho việc gì? | Giới hạn cần nhớ |
| --- | --- | --- |
| **Instance snapshot** | Tạo lại instance khi cần hoặc chọn plan khác qua workflow hỗ trợ | Thời gian tạo máy/đổi DNS/khôi phục vẫn tồn tại |
| **Block disk snapshot** | Tạo lại disk theo chính sách | Phải attach/mount và kiểm tra filesystem/app |
| **Database logical/application backup** | Phục hồi dữ liệu/giao dịch theo logic ứng dụng | Snapshot máy ảo không tự bảo đảm tính nhất quán của transaction đang ghi |

Trong hệ thống có database đang chạy, snapshot ở mức ổ đĩa có thể mang trạng thái **crash-consistent** thay vì **application-consistent**, tùy cơ chế quiesce và DB. Với dữ liệu quan trọng, hãy dùng backup/restore được database hỗ trợ, thử phục hồi trên bản sao và đặt **RPO/RTO** rõ ràng.

### 7.4. Tình huống khôi phục từ snapshot

~~~mermaid
flowchart LR
    A["Instance bị lỗi / cập nhật sai"] --> S["Chọn snapshot hợp lệ"]
    S --> NEW["Tạo instance thay thế"]
    NEW --> TEST["Kiểm tra OS, dữ liệu, app, TLS"]
    TEST --> IP["Gắn static IP hoặc đổi DNS"]
    IP --> LIVE["Kiểm thử từ client + giám sát"]
~~~

Quy trình này có thể làm mất dữ liệu phát sinh **sau thời điểm backup** và cần thời gian thực hiện. Nếu business đặt RPO vài phút hoặc RTO vài chục giây, một snapshot mỗi ngày thường **không đủ**.

### 7.5. Kiểm soát snapshot và vòng đời dữ liệu

- Đặt lịch snapshot theo yêu cầu và thiết lập **retention** theo tính năng hiện có.
- Giữ bản sao/backup ở vị trí phù hợp với chiến lược chống lỗi AZ/Region.
- Mã hóa dữ liệu và giới hạn IAM quyền tạo, khôi phục, xóa snapshots.
- Phân biệt xóa instance với xóa **snapshots/disks còn tồn tại**; chúng có thể tiếp tục phát sinh phí.
- Diễn tập khôi phục, không chỉ xác nhận dashboard ghi “snapshot completed”.

## 8. Lightsail load balancer và mở rộng website

### 8.1. Mở rộng theo chiều dọc

Khi instance thiếu RAM/CPU/storage, một hướng là chọn **plan lớn hơn**. Tùy loại instance và quy trình hỗ trợ, có thể cần **tạo snapshot rồi tạo instance mới** từ snapshot với bundle cao hơn; không coi mọi thông số của một máy đang chạy đều resize trực tiếp được.

Thao tác đổi plan có thể cần:

1. Tạo snapshot sau khi đảm bảo dữ liệu nhất quán.
2. Tạo instance mới từ snapshot với plan phù hợp.
3. Kiểm tra application/config, public/private networking và firewall.
4. Chuyển static IP hoặc cập nhật DNS theo quy trình.
5. Theo dõi traffic/CPU/errors rồi mới dọn tài nguyên cũ.

Vertical scaling không loại bỏ single point of failure: một instance lớn vẫn nằm ở một AZ.

### 8.2. Mở rộng theo chiều ngang

Khi ứng dụng cần nhiều web instances, có thể sử dụng **Lightsail load balancer** để phân phối request giữa các instances phù hợp. Điều kiện:

- Các instances phục vụ **cùng phiên bản ứng dụng**, cấu hình nhất quán.
- **Health check** có endpoint phản ánh khả năng nhận request, không chỉ port mở.
- Session, file upload, cache và dữ liệu quan trọng **không bị khóa trong một instance**.
- Những AZ được sử dụng phải phù hợp với lựa chọn dịch vụ và mức chịu lỗi mong muốn.
- TLS certificate, domain và đường DNS phải được kiểm tra đầu-cuối.

**Không nhầm Lightsail load balancer với ALB của EC2/EKS.** ALB trên EC2/VPC có nhiều rule/target group/integration nâng cao; Lightsail cung cấp trải nghiệm đơn giản hơn và có giới hạn riêng về protocol, cấu hình và tích hợp.

### 8.3. Capacity khi mất một instance/AZ

Ví dụ một API có hai web instances, mỗi instance theo benchmark phục vụ an toàn `80 requests/giây`. Lưu lượng đỉnh `120 requests/giây`:

~~~text
Tổng khi hai máy khỏe   = 2 × 80 = 160 req/s
Sau khi mất một máy     = 1 × 80 =  80 req/s
Tải cần phục vụ         = 120 req/s
→ Không còn đủ capacity mặc dù một instance vẫn đang chạy.
~~~

Muốn tiếp tục phục vụ 120 req/s khi mất một instance, **phải để đủ năng lực sẵn sàng ở các máy còn lại**, hoặc chấp nhận mất thời gian scale/throttle. Kết quả thực tế còn phụ thuộc database, burst CPU, network, storage I/O và application behavior.

## 9. Database, uploads và những thành phần cần tách khỏi instance

### 9.1. Tự cài database trên instance

Ưu điểm của một instance chạy cả web server và DB là **đơn giản, ít tài nguyên** cho demo hoặc website ít quan trọng. Nhược điểm:

- CPU/RAM/I/O tranh chấp giữa app và DB.
- OS disk/snapshot trở thành điểm phụ thuộc của cả ứng dụng lẫn dữ liệu.
- Mở rộng web instances cần chuyển sang **database dùng chung**.
- Backup/restore và cập nhật runtime/DB có thể gián đoạn cả hệ thống.

Đối với dữ liệu đơn hàng hoặc giao dịch quan trọng, cân nhắc **Lightsail managed database** hoặc dịch vụ như Amazon RDS nếu nhu cầu vượt phạm vi Lightsail.

### 9.2. Managed relational database

Lightsail managed database cung cấp MySQL/PostgreSQL theo những engine/plan hiện hành được hỗ trợ, đơn giản hóa một phần các hoạt động quản trị database. Một số plan/tùy chọn hỗ trợ **high availability**; cần kiểm tra cấu hình, giới hạn và chi phí.

Ứng dụng vẫn cần:

- Quản lý schema, migrations, transactions và indexes.
- Xác thực DB, mạng truy cập, secrets và quyền ứng dụng.
- Theo dõi kết nối, dung lượng, latency và query performance.
- Thiết kế backup/restore và kiểm thử failover.

**Không suy rằng mọi managed database của Lightsail đều mặc định Multi-AZ.** Tính HA phụ thuộc vào gói và thiết lập cụ thể; cần xác minh khi chọn plan.

### 9.3. File upload và tài sản tĩnh

Khi có hai web instances:

~~~text
Client tải ảnh → Web A ghi /var/www/uploads/abc.jpg
Client khác → Web B không có file abc.jpg
~~~

Đây là lỗi **không chia sẻ trạng thái**. Giải pháp có thể là lưu file trong **Lightsail object storage**, **Amazon S3** hoặc dịch vụ lưu trữ phù hợp, còn DB lưu key/URL và quyền truy cập. Khi dùng S3, cần kiểm soát IAM/credentials, encryption, bucket policy và chi phí. Không mặc định Lightsail instance có đúng mô hình **EC2 instance profile** để ứng dụng tự lấy AWS credentials; phải xác minh khả năng tích hợp và tránh hardcode access keys.

### 9.4. Job nền và queue

Một ứng dụng vừa nhận HTTP request vừa chạy báo cáo hằng đêm trên một instance có thể khiến CPU burst bị tiêu hao, tăng latency. Khi workflow phức tạp hơn, cân nhắc tách worker và queue, sử dụng dịch vụ AWS tương ứng hoặc chuyển kiến trúc sang ECS/App Runner/Lambda khi phù hợp.

## 10. Bảo mật Lightsail ở môi trường production

### 10.1. Các lớp cần bảo vệ

~~~mermaid
flowchart TB
    NET["Internet / trusted networks"] --> FW["Lightsail firewall"]
    FW --> OSFW["OS firewall + SSH config"]
    OSFW --> WEB["TLS + web server"]
    WEB --> APP["Application authentication/authorization"]
    APP --> DATA["Database / object storage / secrets"]
~~~

**Không dùng một lớp bảo vệ thay cho các lớp khác**. Chẳng hạn, firewall chỉ mở 443 không ngăn ứng dụng có lỗ hổng SQL injection; TLS không tự kiểm soát quyền người dùng đã đăng nhập.

### 10.2. Checklist bảo mật tối thiểu

- **SSH/RDP:** chỉ mở khi cần; giới hạn nguồn quản trị; private key được bảo vệ, dùng các phương pháp chống brute force phù hợp.
- **Cập nhật OS và runtime:** tự quản lý security patches, package updates và ứng dụng/WordPress plugins.
- **TLS:** cấp và gia hạn chứng chỉ; không chấp nhận website production chỉ HTTP khi truyền thông tin nhạy cảm.
- **Secret management:** không hardcode DB password/API keys vào repository, userdata công khai hay file webroot; hạn chế quyền truy cập.
- **Nguyên tắc đặc quyền tối thiểu:** tách user OS, ứng dụng không chạy `root` khi không cần, giới hạn quyền file và database.
- **Firewall:** phân biệt IPv4 và IPv6; không quên port dịch vụ ngoài ý muốn.
- **Backup:** có snapshot/application backup, retention và restore test; không dùng snapshot như lá chắn chống mọi tấn công.
- **Logging:** web access/error logs, auth logs, application logs; thiết lập rotation/retention và bảo vệ dữ liệu nhạy cảm.
- **IAM của AWS account:** MFA, quyền quản trị Lightsail hẹp, CloudTrail và quy trình review khi thay đổi IP/firewall.
- **Cost guardrails:** AWS Budgets, tag/owner, cảnh báo tài nguyên bỏ quên.

**Lưu ý về credential:** Lightsail instance không nên được xem như EC2 có đầy đủ tính năng instance profile/role hay mọi networking control theo mặc định. Nếu workload cần sử dụng nhiều AWS APIs và cơ chế cấp credentials tự động, hãy kiểm tra tùy chọn hỗ trợ thực tế hoặc ưu tiên EC2/ECS/Lambda với workload IAM roles rõ ràng.

### 10.3. Shared Responsibility Model

AWS quản lý bảo mật **của** đám mây (hạ tầng nền), còn người dùng quản lý bảo mật **trong** workload: cấu hình OS, ứng dụng, IAM, keys, dữ liệu, firewall, backup và kiểm soát truy cập. Bundle rẻ/đơn giản không làm trách nhiệm vận hành biến mất.

## 11. Quan sát và xử lý sự cố

### 11.1. Metrics nên xem

| Lớp | Tín hiệu quan trọng |
| --- | --- |
| **Compute** | CPU utilization, burst capacity metrics khi plan hỗ trợ, trạng thái instance |
| **Network** | Inbound/outbound traffic, kết nối thất bại, firewall, DNS và TLS |
| **Disk** | Dung lượng filesystem, inode, I/O hoặc metrics disk theo khả năng monitor |
| **Application** | HTTP 4xx/5xx, latency p95/p99, request count, process health |
| **Database** | Connections, free space, slow queries, backups và DB availability |
| **Backup** | Snapshot gần nhất, restore test và tuổi dữ liệu backup |
| **Billing** | Chi phí instance, storage, snapshot, static/public IP, transfer và dịch vụ khác |

Lightsail có trang monitoring và những metrics/alarms của sản phẩm. **Không giả định tất cả app-level metrics như disk filesystem % hoặc HTTP latency tự xuất hiện**: có thể cần công cụ/agent/logging bổ sung.

### 11.2. Những lỗi hay gặp

| Triệu chứng | Khả năng chính | Cách điều tra |
| --- | --- | --- |
| Website timeout sau khi tạo instance | Chưa mở firewall 80/443, DNS/IP sai, OS firewall chặn | Kiểm tra public/static IP, Lightsail firewall và web listener |
| `Connection refused` tới port 80 | Nginx/app chưa chạy hoặc không listen port mong đợi | `systemctl status nginx`, `ss -lntp`, local curl |
| HTTPS báo chứng chỉ không hợp lệ | Cert hết hạn, sai hostname, 443 chưa cấu hình TLS | Xem certificate, SNI, redirect, DNS |
| SSH timeout | Sai IP/source CIDR, firewall hoặc SSH service | Kiểm tra Lightsail firewall 22, OS firewall và trạng thái sshd |
| SSH `Permission denied (publickey)` | Sai user/key, key không khớp hoặc permissions | Đối chiếu blueprint username, key pair và SSH logs |
| CPU cao nhưng response chậm | Plan thiếu tài nguyên hoặc burst capacity cạn | Theo dõi CPU/burst theo thời gian, benchmark tải dài |
| Instance chạy nhưng website 500 | Runtime/app/DB lỗi | Web/app logs, DB connections, disk space |
| Disk đầy | Uploads, logs, cache, backups chiếm root disk | `df -h`, `du` cẩn trọng, log rotation và storage plan |
| Sau tạo máy từ snapshot không vào website | Public IP/secret/config/DNS/firewall khác máy cũ | Kiểm tra từng lớp; chỉ chuyển static IP sau kiểm thử |
| Hóa đơn còn tăng khi không dùng website | Instance/disk/snapshot/IP/LB vẫn tồn tại hoặc plan tiếp tục tính phí | Xem resource inventory và AWS billing |

**Đừng sửa lỗi bằng cách mở tất cả cổng cho `0.0.0.0/0` hoặc tắt OS firewall**. Hãy xác định tầng lỗi trước và thay đổi có kiểm soát.

### 11.3. Lệnh kiểm tra bên trong Linux instance

~~~bash
# Chỉ đọc; chạy khi đã truy cập hợp lệ vào máy Linux lab
uname -a
df -h
free -h
sudo ss -lntp
sudo systemctl status nginx
curl -I http://127.0.0.1/
~~~

Không mặc định mọi OS đã có Nginx hoặc `systemd`. Với container/app framework khác, thay lệnh theo runtime thực tế.

## 12. AWS CLI cho Lightsail: quan sát tài nguyên an toàn

Ví dụ giả định Region `ap-southeast-1`, có AWS CLI được cấu hình và danh tính được cấp quyền đọc tài nguyên Lightsail. Tất cả các lệnh sau **chỉ đọc**, không tạo/xóa instance.

### 12.1. Xem danh tính và gói hiện có

~~~bash
aws sts get-caller-identity

aws lightsail get-regions \
  --query "regions[].{Name:name,AvailabilityZones:availabilityZones[].zoneName}" \
  --output json

aws lightsail get-blueprints \
  --region ap-southeast-1 \
  --query "blueprints[].{Id:blueprintId,Name:name,Platform:platform}" \
  --output table

aws lightsail get-bundles \
  --region ap-southeast-1 \
  --query "bundles[].{Id:bundleId,Price:price,CPUs:cpuCount,MemoryGB:ramSizeInGb,DiskGB:diskSizeInGb,TransferGB:transferPerMonthInGb}" \
  --output table
~~~

Khi danh sách lớn, lọc các plan phù hợp trong AWS Console hoặc dùng JMESPath thêm điều kiện trên bundle đã tìm được. Một số plan có thể không hiện ở mọi Region/loại OS; danh sách API là nguồn kiểm tra tốt hơn việc nhớ tên bundle từ hướng dẫn cũ.

### 12.2. Xem instances và địa chỉ

~~~bash
aws lightsail get-instances \
  --region ap-southeast-1 \
  --query "instances[].{Name:name,State:state.name,AZ:location.availabilityZone,PublicIP:publicIpAddress,PrivateIP:privateIpAddress,Blueprint:blueprintId,Bundle:bundleId}" \
  --output table

aws lightsail get-instance \
  --region ap-southeast-1 \
  --instance-name lab-lightsail-web
~~~

Nếu instance chưa có trong tài khoản/Region, lệnh theo tên có thể báo không tìm thấy. Không suy ra từ đó rằng instance không tồn tại ở mọi Region khác.

### 12.3. Xem instance firewall, static IP và snapshots

~~~bash
aws lightsail get-instance-port-states \
  --region ap-southeast-1 \
  --instance-name lab-lightsail-web \
  --query "portStates[].{From:fromPort,To:toPort,Protocol:protocol,State:state,CIDRs:cidrs,IPv6:ipv6Cidrs}" \
  --output json

aws lightsail get-static-ips \
  --region ap-southeast-1 \
  --output json

aws lightsail get-instance-snapshots \
  --region ap-southeast-1 \
  --query "instanceSnapshots[].{Name:name,From:fromInstanceName,Created:createdAt}" \
  --output table
~~~

Đọc `portStates` để tìm cổng quản trị đang mở cho mọi nguồn IPv4/IPv6 không cần thiết; đối chiếu với OS firewall. `get-instance-snapshots` chỉ cho thấy snapshots tồn tại, **chưa chứng minh restore sẽ thành công**.

### 12.4. Xem hạ tầng hỗ trợ

~~~bash
aws lightsail get-load-balancers \
  --region ap-southeast-1

aws lightsail get-relational-databases \
  --region ap-southeast-1
~~~

Đừng tạo thêm load balancer/database chỉ vì thấy danh sách trống. Mỗi loại tài nguyên có điều kiện hỗ trợ và **chi phí riêng**.

### 12.5. Khi cần tạo/xóa, hãy chuẩn bị review

Các API như `create-instances`, `allocate-static-ip`, `open-instance-public-ports`, `create-instance-snapshot`, `delete-instance` có thể làm thay đổi hạ tầng hoặc chi phí. Với production, chỉ thực hiện sau khi có:

1. Tên/Region/blueprint/bundle cụ thể đã đối chiếu.
2. Phạm vi IP/port và người sở hữu tài nguyên.
3. Dữ liệu cần backup trước thao tác.
4. Dự toán chi phí và kế hoạch dọn tài nguyên lab.
5. Kế hoạch rollback/restore khi thay đổi không đạt.

## 13. Chi phí Lightsail: gói đơn giản vẫn có khoản ngoài plan

### 13.1. Những khoản cần tính

| Nhóm | Chi phí có thể phát sinh | Cách giảm bất ngờ |
| --- | --- | --- |
| **Instance** | Gói compute, RAM, root disk, transfer theo plan/giờ-tháng | Chọn plan vừa đủ, xóa lab khi xong |
| **Attached disks** | Dung lượng disk bổ sung và snapshots | Theo dõi disk thừa, retention |
| **Snapshots** | Dung lượng snapshot được lưu trữ | Giữ theo RPO/chính sách; không xóa backup còn cần |
| **Static/public IP** | Phí phụ thuộc plan và trạng thái sử dụng | Kiểm tra static IP chưa gắn và quy tắc charge hiện hành |
| **Data transfer** | Lưu lượng vượt allowance hoặc loại transfer tính phí riêng | Đo egress, tránh truyền file lớn không cần thiết |
| **Load balancer** | Phí LB và phần sử dụng liên quan | Chỉ tạo khi bài toán thực sự cần nhiều instances |
| **Managed DB/object storage** | Gói/requests/storage/transfer của dịch vụ | Theo dõi kích thước, backup, traffic |
| **Logging, DNS, dịch vụ AWS khác** | Route 53, CloudWatch, S3, egress/cross-service | Gộp vào ngân sách toàn ứng dụng |

**Tắt máy không đồng nghĩa ngừng mọi chi phí.** Trong nhiều trường hợp, Lightsail instance plan vẫn được tính phí cho tới khi tài nguyên bị **xóa**, kể cả khi instance ở trạng thái stopped; disk/snapshot/IP có vòng đời tính phí riêng. Luôn kiểm tra quy tắc billing hiện hành trước khi dùng stop như cách tiết kiệm.

### 13.2. Mô hình dự toán

Giả sử mô hình có hai instances, một load balancer và một managed database. Không dùng bảng giá cụ thể:

~~~text
Tổng chi phí kỳ tính
  ≈ 2 × giá instance plan tương ứng
  + giá Lightsail load balancer
  + giá managed database plan
  + attached disk / snapshot storage
  + traffic / địa chỉ / request ngoài allowance
  + DNS / logs / service AWS bổ sung (nếu dùng)
~~~

Giả sử mỗi tháng workload tăng trưởng 30% dung lượng upload, cần đưa cả **retention và tốc độ tăng** vào dự báo chứ không chỉ chi phí hiện tại. Nếu website phục vụ video/tệp lớn, outbound transfer có thể ảnh hưởng tổng chi phí hơn số request đơn thuần.

### 13.3. Đánh đổi chi phí với công vận hành

Một Lightsail instance rẻ nhưng cần kỹ sư vá OS, xoay secret, cài monitoring và khôi phục khi lỗi. Một dịch vụ managed hơn có thể có phí tài nguyên lớn hơn nhưng giảm thời gian vận hành. Quyết định nên tính **total cost of ownership (TCO)**, bao gồm thời gian nhân sự, rủi ro downtime và nghĩa vụ bảo mật.

## 14. Khi nào Lightsail instance phù hợp?

### 14.1. Phù hợp tốt

- Website doanh nghiệp nhỏ, blog hoặc WordPress có tải khá ổn định.
- Trang demo/MVP, prototype, môi trường phát triển và dự án học AWS.
- Ứng dụng web đơn giản cần **quyền quản trị OS** nhưng không muốn tự thiết kế VPC nhiều tầng.
- Workload ít phụ thuộc dịch vụ AWS nâng cao và có thể quản lý bằng một hoặc vài instances.
- Nhóm nhỏ cần **gói tài nguyên dễ dự toán**, có thể chấp nhận lịch bảo trì và RTO của mô hình đã chọn.

**Ví dụ:** một công ty muốn trang giới thiệu và hệ thống đặt lịch nhỏ; vài trang web chạy trên Lightsail với snapshot có kiểm tra, HTTPS, firewall chặt và database được quản lý có thể là cách khởi động hợp lý khi đáp ứng yêu cầu bảo mật/dữ liệu.

### 14.2. Cần cân nhắc chuyển nền tảng

- Workload cần **custom VPC topology**, nhiều subnet route/Network ACL, PrivateLink phức tạp, Transit Gateway hoặc kiểm soát mạng nâng cao.
- Cần **fine-grained IAM workload roles**, quản lý hạ tầng và tích hợp AWS services ở mức sâu.
- Cần **Auto Scaling** đa tầng, deployment strategies/canary, target groups/rules phức tạp hoặc ECS/EKS orchestration.
- Có traffic biến động lớn, mục tiêu SLO/RTO rất nghiêm ngặt hoặc workload dữ liệu phân tán.
- Yêu cầu CPU/memory/GPU/storage IOPS hoặc instance families mà bundle Lightsail không đáp ứng.
- Cần automation/IaC/observability phức tạp, compliance hoặc nhiều đội với ranh giới quyền rõ ràng.

Không có nghĩa “Lightsail không thể chạy production”. Nó **có thể** chạy ứng dụng thật với yêu cầu phù hợp, nhưng thiết kế phải chứng minh được bảo mật, phục hồi, capacity và giới hạn dịch vụ. Ngược lại, chuyển sang EC2/EKS quá sớm cũng có thể làm tăng độ phức tạp không cần thiết.

## 15. So sánh Lightsail instance với các lựa chọn AWS khác

| Dịch vụ | Đơn vị triển khai | Độ kiểm soát | Trách nhiệm vận hành chính | Khi nên cân nhắc |
| --- | --- | --- | --- | --- |
| **Lightsail instance** | VPS theo bundle | OS/app trên máy ảo; network đơn giản | Vá OS, app, backup, TLS, vận hành | Website/MVP/workload đơn giản |
| **Amazon EC2** | Instance theo loại tùy chọn trong VPC | Rất linh hoạt về networking, instance, storage, IAM | OS/app và hạ tầng được cấu hình | Custom networking, scaling, tích hợp AWS nâng cao |
| **Elastic Beanstalk** | Application/environment; dưới nền thường là EC2, LB và dịch vụ liên quan | Chọn platform và nhiều thiết lập environment | Code/app và một số phần OS/config/patch tùy trách nhiệm | Muốn deploy web app theo platform, giảm việc nối các AWS resources bằng tay |
| **AWS App Runner** | Source code/container image | Ít kiểm soát server hơn; service-managed deployment | Code, runtime behavior, IAM/networking phù hợp | Web API/container HTTP muốn giảm quản lý server |
| **Amazon ECS on Fargate** | Container task/service | Networking, scaling và deployment container | Image, task/service, IAM, VPC/ALB | Microservices, container workloads với quyền mạng rõ |
| **Amazon EKS** | Kubernetes workloads | Kubernetes APIs và hệ sinh thái controller | Cluster/app, networking, upgrade/add-ons theo mode | Đã có nhu cầu Kubernetes thực sự |
| **AWS Lambda** | Function theo event | Không quản trị server; giới hạn runtime/event model | Function, permissions, integrations | API/event jobs ngắn, không cần always-on VPS |

**Điều cần tránh:** không so sánh bằng “mức giá CPU/RAM” đơn thuần. Ví dụ một API nhỏ chạy 24/7 có thể hợp với Lightsail/App Runner; nhưng API cần private subnet, nhiều security domains và IAM task roles có thể hợp ECS Fargate hơn, dù cùng một lượng request.

### 15.1. Cây quyết định nhanh

~~~mermaid
flowchart TD
    START["Cần triển khai ứng dụng AWS"] --> OS{"Cần quyền quản trị toàn bộ OS?"}
    OS -->|"Có"| SIMPLE{"Workload đơn giản, networking tiêu chuẩn, gói phù hợp?"}
    SIMPLE -->|"Có"| LS["Đánh giá Lightsail instance"]
    SIMPLE -->|"Không"| EC2["Đánh giá EC2 + VPC/ASG/ELB"]
    OS -->|"Không"| APP{"Ứng dụng HTTP/container hay event?"}
    APP -->|"HTTP app"| RUN["Đánh giá App Runner / Beanstalk"]
    APP -->|"Container nhiều service"| ECS["Đánh giá ECS Fargate"]
    APP -->|"Kubernetes yêu cầu rõ"| EKS["Đánh giá EKS"]
    APP -->|"Event/function"| LAM["Đánh giá Lambda"]
~~~

*Đây là công cụ định hướng, không phải bộ quy tắc tuyệt đối. Phải tiếp tục kiểm tra giá, Region, compliance, latency, dữ liệu, network và mục tiêu vận hành.*

## 16. Lộ trình khi Lightsail không còn đủ

Một sản phẩm thường bắt đầu trên một instance rồi phát triển:

| Giai đoạn | Kiến trúc có thể phù hợp | Tín hiệu cần điều chỉnh |
| --- | --- | --- |
| **Thử nghiệm** | Một instance + snapshot + HTTPS | Demo hoạt động, cost thấp |
| **Website thật nhỏ** | Một instance + static IP + backup/monitoring | Lưu lượng ổn định, RTO cho phép restore |
| **Tăng trưởng** | Nhiều instances + Lightsail LB + managed DB/object storage | Cần phân tải, không giữ state local |
| **Phức tạp hơn** | EC2 + ALB/ASG/RDS hoặc App Runner/ECS | Cần scaling/routing/IAM/VPC nâng cao |
| **Nhiều đội/microservices** | ECS/EKS và dịch vụ managed khác | Có vận hành container/CI-CD, service discovery, observability |

### 16.1. Migrate bằng snapshot/export

Lightsail có những workflow **export snapshot sang Amazon EC2** hoặc tạo EC2 resources từ Lightsail snapshots đối với loại tài nguyên được hỗ trợ. Nhưng không được coi đây là “chuyển 1-click mọi thứ”:

- Kiểm tra OS/blueprint và snapshot **có hỗ trợ export**.
- EC2 cần **VPC, subnet, route, Security Group, IP, IAM role, EBS và monitoring** được thiết kế lại phù hợp.
- Database, external disks, object storage, secrets, cron jobs, certificates và DNS có thể cần chuyển riêng.
- Kiểm thử app tại môi trường EC2 mới, đo downtime/data sync rồi mới cutover.
- Có kế hoạch rollback trong thời gian DNS TTL/traffic thay đổi.

### 16.2. Migrate theo tầng thay vì “lớn lên bằng một máy thật to”

Với website đang tăng trưởng, cách cải thiện thường là:

1. Tách **database** khỏi web instance và backup dữ liệu riêng.
2. Đưa **upload/static assets** sang object storage.
3. Chuyển ứng dụng thành **stateless** và làm rõ session storage.
4. Thiết lập CI/CD, secrets, logs và health checks.
5. Chọn nền tảng mới theo khả năng scale, IAM và networking thực tế.

Thứ tự này giúp giảm khóa chặt vào instance và tạo điều kiện kiểm thử trước khi chuyển dữ liệu production.

## 17. Case study: website đặt lịch của một doanh nghiệp nhỏ

### 17.1. Bối cảnh

Một doanh nghiệp cần website có chức năng đặt lịch và gửi email nhắc khách:

~~~text
Khách truy cập:         2.000 người/ngày
Lưu lượng giờ cao điểm: khoảng 15-25 req/s
Tính năng:              đăng nhập, đặt lịch, upload ảnh
Dữ liệu:                khách hàng và giao dịch lịch hẹn
Nhân sự vận hành:       một developer kiêm quản trị
Mục tiêu ban đầu:       triển khai đơn giản, chi phí đoán trước
~~~

Thông số chỉ minh họa; không thể suy bundle từ số lượt người truy cập mà không benchmark. Vì đây là hệ thống chứa dữ liệu cá nhân, phải kiểm soát quyền truy cập, encryption và tuân thủ yêu cầu dữ liệu của tổ chức.

### 17.2. Giai đoạn đầu: lựa chọn Lightsail

Mô hình có thể gồm:

- Một Linux Lightsail instance chạy ứng dụng và Nginx.
- Static IP, DNS và HTTPS.
- Database managed hoặc ít nhất backup ứng dụng/DB được kiểm chứng.
- Upload vào object storage, không khóa vào root disk.
- Firewall chỉ mở web và SSH từ mạng quản trị.
- Snapshot, backup, metrics, cảnh báo và ngân sách.

**Lý do:** ít thành phần hạ tầng, dễ triển khai, team nhỏ kiểm soát được OS/app. Hạn chế: nếu chỉ một instance, vẫn có downtime khi AZ/host lỗi hoặc bảo trì.

### 17.3. Khi số khách tăng và uptime quan trọng

Sau sáu tháng, tính năng đặt lịch trở thành kênh kinh doanh chính; downtime 1 giờ có thể ảnh hưởng nhiều khách. Team phát hiện:

- CPU thường xuyên cao và burst capacity thấp.
- Upload nằm trong local filesystem nên khó nhân bản web.
- Khôi phục snapshot mất quá lâu so với RTO mới.
- Database cùng instance khiến khôi phục và cập nhật rủi ro.

Những bước hợp lý:

1. Chuyển upload và dữ liệu trạng thái khỏi instance, tách DB.
2. Đo tải và kiểm thử nhiều instances sau load balancer nếu nhu cầu vẫn nằm trong phạm vi Lightsail.
3. Xác định RTO/RPO mới và chọn plan/HA database phù hợp.
4. Nếu cần network/IAM/scaling/deployment phức tạp, đánh giá **App Runner/ECS Fargate/EC2** theo kiến trúc mới.

**Kết luận:** không nên giữ Lightsail bằng mọi giá, cũng không nhất thiết phải chuyển ngay EKS. Dịch vụ phù hợp là dịch vụ đáp ứng mục tiêu nghiệp vụ với chi phí và độ phức tạp có thể quản lý.

## 18. Bài tập củng cố

### Bài tập 1 — chọn Lightsail hay EC2?

Đội A cần WordPress giới thiệu công ty, ước lượng tải ổn định và chỉ có một admin. Đội B cần hệ thống nhiều subnet, Transit Gateway, IAM role cho từng workload, Auto Scaling và hàng chục microservices.

**Gợi ý:** đội A nên **đánh giá Lightsail** nếu kiểm soát được OS, backup và uptime; đội B thường cần **EC2/ECS/EKS cùng VPC** hoặc nền tảng phù hợp hơn, không nên ép tất cả vào vài Lightsail instances.

### Bài tập 2 — vì sao static IP hữu ích?

Website trỏ bản ghi `A` vào public IP hiện tại của instance, nhưng sau một thao tác thay instance, IP thay đổi khiến DNS trỏ tới IP cũ.

**Gợi ý:** dùng **static IP** gắn với Lightsail instance khi mô hình hỗ trợ; khi thay máy, thực hiện cutover có kiểm soát và kiểm tra DNS TTL. Không coi IP public mặc định là vĩnh viễn.

### Bài tập 3 — lỗi SSH

Một máy Linux mở TCP 22 cho mọi địa chỉ IPv4/IPv6. Developer muốn giữ nguyên để luôn có thể vào server.

**Gợi ý:** đây là rủi ro brute-force và tấn công Internet. Giới hạn theo mạng quản trị, bảo vệ private key, tắt/giới hạn password login theo chính sách OS, giám sát authentication logs và chuẩn bị phương án truy cập khẩn cấp phù hợp.

### Bài tập 4 — snapshot có đủ cho RPO?

Ứng dụng nhận đơn hàng liên tục và chụp instance snapshot mỗi đêm lúc 00:00. Máy lỗi lúc 17:00 hôm sau. Doanh nghiệp yêu cầu RPO tối đa 15 phút.

**Gợi ý:** snapshot hằng ngày không đáp ứng RPO 15 phút. Cần chiến lược dữ liệu/backup/replication khác với tần suất thích hợp, đồng thời **thử restore** để đo RTO.

### Bài tập 5 — hai instances sau LB nhưng ảnh bị mất

Khách upload ảnh qua instance A, request tiếp theo được LB chuyển tới instance B và trả 404. Phải thay đổi điều gì?

**Gợi ý:** ứng dụng đang lưu state vào **local disk**. Chuyển ảnh sang object storage/dịch vụ chia sẻ phù hợp, DB lưu metadata/key và đảm bảo cả hai instances có cùng logic đọc/tải ảnh.

### Bài tập 6 — ước lượng khả năng chịu lỗi

Hai instances phục vụ tối đa 80 req/s mỗi máy theo mức benchmark an toàn; giờ cao điểm là 120 req/s. Một instance đột ngột mất kết nối.

**Gợi ý:** năng lực còn 80 req/s, **không đủ** để giữ 120 req/s. Cần đủ số instance/capacity dự phòng, autoscaling và kế hoạch xử lý tải theo RTO/SLO; LB không tạo thêm tài nguyên tính toán.

### Bài tập 7 — tính chi phí đầy đủ

Người quản lý chỉ tính giá bundle, bỏ qua snapshots, data transfer, managed DB và load balancer. Hãy bổ sung bảng dự toán theo tài nguyên, traffic dự kiến, người chịu trách nhiệm và cảnh báo ngân sách.

**Gợi ý:** giá bundle là một **phần** của TCO. Cần tính các thành phần đang tồn tại và chính sách bill khi stopped, plus retention snapshots, IP, disk và services khác.

### Bài tập 8 — kế hoạch chuyển nền tảng

Một API đang chạy trên Lightsail cần kết nối private tới nhiều AWS services, workload identity tự động, CI/CD canary và phát hành nhiều lần/ngày. Hãy đề xuất tiêu chí chọn App Runner, ECS Fargate hoặc EC2.

**Gợi ý:** so sánh yêu cầu ingress/egress VPC, IAM roles, deployment/revision, rollback, scaling và công vận hành; một bản export snapshot không thay thế được quá trình thiết kế IAM, network và application rollout.

## 19. Những hiểu nhầm thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “Lightsail là một website hosting được AWS vá mọi thứ tự động.” | Lightsail instance là **máy ảo**; vẫn phải quản trị OS, app và bảo mật. |
| “Blueprint WordPress có nghĩa plugin và DB luôn được backup đúng.” | Cần kế hoạch backup và kiểm thử restore riêng. |
| “Instance đã stop nên không bị tính tiền.” | Phải xem billing theo vòng đời resource; stop không nhất thiết dừng phí plan. |
| “Public IP của instance luôn cố định.” | Cần hiểu vòng đời IP; dùng static IP khi cần định danh ổn định. |
| “Mở firewall 443 thì HTTPS tự hoạt động.” | Cần web listener, TLS certificate, DNS và OS firewall phù hợp. |
| “Snapshot = HA.” | Snapshot là **khả năng phục hồi**, không phải tự động chuyển traffic. |
| “Có load balancer là đủ chịu lỗi một AZ.” | Còn cần đủ instances/capacity, state, DB, dữ liệu và egress. |
| “Gói lớn nhất luôn là cách scale tốt nhất.” | Vertical scaling vẫn có single point of failure và giới hạn mở rộng. |
| “Lightsail có toàn bộ VPC/IAM giống EC2.” | Lightsail đơn giản hóa và giới hạn một số cấu hình; phải kiểm tra yêu cầu thực tế. |
| “Lightsail chỉ được dùng cho demo.” | Có thể phù hợp production nhỏ nếu mục tiêu availability, bảo mật và dữ liệu được đáp ứng. |
| “EC2/EKS luôn là lựa chọn tốt hơn.” | Độ phức tạp và chi phí vận hành có thể vượt nhu cầu ứng dụng nhỏ. |

## 20. Checklist quyết định trước khi triển khai production

- [ ] Mục tiêu workload rõ: website, API, CMS hay app nội bộ; người chịu trách nhiệm vận hành được chỉ định.
- [ ] Blueprint, bundle, CPU burst/RAM/storage và Region/AZ được kiểm thử với tải dự kiến.
- [ ] Mô hình public IPv4/IPv6, static IP, DNS, TLS và cách chuyển máy khi lỗi được ghi lại.
- [ ] Instance firewall và OS firewall giới hạn SSH/RDP và chỉ mở port ứng dụng cần thiết.
- [ ] OS patches, runtime updates, secret handling, user permissions và authentication đã có quy trình.
- [ ] Upload, database, session và logs được đặt ở vị trí có chiến lược backup và khôi phục rõ.
- [ ] Snapshot/backup có retention, kiểm tra định kỳ và đã diễn tập restore.
- [ ] RPO/RTO, health checks, capacity và ảnh hưởng khi mất instance/AZ được định lượng.
- [ ] Metrics, log rotation, alerts, budget và owner đã được cấu hình.
- [ ] Các giới hạn Lightsail về network/IAM/scaling được đối chiếu với nhu cầu hiện tại và tương lai.
- [ ] Đã so sánh Lightsail với EC2, App Runner, Elastic Beanstalk, ECS hoặc Lambda theo TCO và vận hành.
- [ ] Có kế hoạch dọn tài nguyên lab và chuyển nền tảng khi tăng trưởng vượt giới hạn.

## 21. Ghi nhớ

**Lightsail instance** là lựa chọn đơn giản hóa VPS trên AWS: chọn **blueprint**, **bundle**, **Region/AZ**, quản lý **IP/firewall/DNS**, rồi cài và vận hành ứng dụng trên OS đã chọn. Nó giúp một nhóm nhỏ đưa ứng dụng đơn giản lên mạng nhanh và dự toán tài nguyên thuận tiện.

Giới hạn quan trọng không nằm chỉ ở dung lượng máy: **một instance là một điểm lỗi đơn**, OS/app vẫn cần bảo trì, backup không đồng nghĩa HA, còn networking/IAM/scaling phức tạp có thể vượt phạm vi Lightsail. Khi cần nhiều AZ, dữ liệu dùng chung, deployment tự động và khả năng mở rộng chuyên sâu, hãy đánh giá load balancer/database được Lightsail hỗ trợ **hoặc** chuyển sang những dịch vụ AWS chuyên dụng.

Chọn Lightsail khi nó **đủ tốt cho yêu cầu nghiệp vụ và vận hành**, không chỉ vì có giá bundle dễ hiểu. Chọn dịch vụ cao hơn khi các mục tiêu về bảo mật, RTO/RPO, scale hoặc tự động hóa đòi hỏi.

### Tài liệu AWS chính thức

- [What is Amazon Lightsail?](https://docs.aws.amazon.com/lightsail/latest/userguide/what-is-amazon-lightsail.html) — khái niệm và thành phần Lightsail.
- [Amazon Lightsail User Guide](https://docs.aws.amazon.com/lightsail/latest/userguide/) — tạo/quản lý instance, blueprint, bundle, storage và network.
- [Amazon Lightsail pricing](https://aws.amazon.com/lightsail/pricing/) — plan, transfer allowance và các khoản phí dịch vụ liên quan.
- [Amazon Lightsail static IP addresses](https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-static-ip-addresses-in-amazon-lightsail.html) — sử dụng IP tĩnh và DNS.
- [Lightsail networking and firewalls](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-editing-firewall-rules.html) — inbound ports, nguồn và IP versions.
- [Amazon Lightsail snapshots](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-snapshots.html) — backup/restore máy và block storage.
- [Lightsail load balancers](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-load-balancers.html) — phân tải và HTTPS theo hỗ trợ.
- [Lightsail managed databases](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-relational-databases.html) — các lựa chọn database.
- [AWS CLI Lightsail reference](https://docs.aws.amazon.com/cli/latest/reference/lightsail/index.html) — lệnh `get-bundles`, `get-instances`, `get-instance-port-states` và snapshots.
- [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/) — trách nhiệm hạ tầng của AWS và workload của khách hàng.
