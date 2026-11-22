# Cloud NAT và kết nối đi ra cho tài nguyên riêng

Trong Google Cloud, một máy ảo Compute Engine chỉ có địa chỉ IP nội bộ vẫn có thể cần tải gói hệ điều hành, gọi API của nhà cung cấp thanh toán hoặc gửi dữ liệu ra dịch vụ bên ngoài. Tương tự, node GKE riêng hoặc ứng dụng Cloud Run có thể cần **kết nối đi ra (egress)** nhưng không cần lộ một địa chỉ IP công khai riêng cho từng workload. **Cloud NAT** cung cấp cơ chế dịch địa chỉ để hỗ trợ các kết nối như vậy mà không biến máy ảo thành một điểm truy cập công khai từ Internet.

Bài học thuộc chương **VPC và định tuyến** của mô-đun `CLOUD_PROVIDERS_GCP`. Những kiến thức này kết nối việc tổ chức project, IAM và VPC với triển khai Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; đồng thời giúp người học chọn đúng giải pháp mạng, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cũng như chi phí.

Nội dung tập trung vào **Public NAT để các tài nguyên có địa chỉ riêng kết nối ra Internet**; cuối bài giới thiệu **Private NAT** để bạn không nhầm hai dạng NAT do Google Cloud cung cấp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao VM không có external IP vẫn cần egress và Public NAT giải quyết vấn đề gì.
2. Mô tả luồng **SNAT** của gói tin đi ra và **DNAT** của gói phản hồi, đồng thời giải thích vì sao Cloud NAT không cung cấp kết nối đến không được yêu cầu từ bên ngoài.
3. Phân biệt Cloud NAT, Cloud Router, VPC route, firewall, DNS, Private Google Access và Private Service Connect.
4. Thiết kế phạm vi NAT theo **VPC, region, subnet và dải IP chính/phụ**.
5. Thực hành cấu hình Public NAT cho Compute Engine bằng Console hoặc `gcloud`.
6. Áp dụng đúng mô hình với GKE và Cloud Run, nhất là yêu cầu egress IP tĩnh khi bên thứ ba cần allowlist.
7. Kiểm tra lỗi định tuyến, thiếu quyền đi ra, cạn NAT ports và quan sát chi phí hoạt động.

## 1. Tình huống xuất phát: private VM cần tải bản cập nhật

Nhóm Commerce đặt một VM xử lý đơn hàng trong private subnet của project `atlas-commerce-dev`:

- Địa chỉ nội bộ của VM: `10.20.0.10`.
- VM **không có external IPv4 address**.
- VM cần gọi một dịch vụ HTTPS công khai để nhận thông tin cập nhật.
- Nhóm không muốn cấp external IP trực tiếp cho VM vì VM không cung cấp dịch vụ đến từ Internet.

Nếu chỉ tạo subnet và VM, bạn chưa bảo đảm VM ra Internet thành công. Đường truyền cần được **định tuyến** đến đích thích hợp, **firewall egress** phải cho phép, và địa chỉ nguồn riêng của VM cần được **dịch sang địa chỉ công khai** đối với lưu lượng Internet IPv4. Public NAT giải quyết phần dịch địa chỉ nguồn.

~~~mermaid
flowchart LR
    VM["VM riêng<br/>10.20.0.10<br/>Không external IP"]
    SUB["Subnet 10.20.0.0/24"]
    NAT["Public NAT<br/>External IP dùng chung"]
    WEB["API bên ngoài<br/>HTTPS :443"]
    VM --> SUB
    SUB -->|"Route + egress firewall cho phép"| NAT
    NAT -->|"SNAT: IP/port công khai"| WEB
    WEB -. "Phản hồi cho kết nối đã tạo" .-> NAT
    NAT -. "DNAT trả về IP nội bộ" .-> VM
~~~

Sơ đồ thể hiện **luồng logic**. Trên thực tế, Cloud NAT là dịch vụ phân tán được thực hiện trong hạ tầng mạng ảo của Google Cloud; **gói tin không phải đi qua một máy ảo NAT gateway hoặc Cloud Router như một hop chuyển tiếp**.

### 1.1. Vì sao không gắn external IP cho từng VM?

Có thể gắn external IP cho VM nếu workload thật sự cần, nhưng mô hình đó có khác biệt:

| Phương án | Nguồn kết nối đi ra | Điểm cần cân nhắc |
| --- | --- | --- |
| VM có external IP | VM sử dụng cơ chế NAT một-một được Google Cloud cung cấp cho primary internal IP khi đáp ứng điều kiện route | Có địa chỉ công khai riêng, phải kiểm soát firewall ingress/egress |
| VM chỉ có internal IP + Public NAT | Sử dụng pool external IP/ports của Public NAT | Giảm nhu cầu external IP trên từng VM, không cho kết nối inbound tự phát qua NAT |
| VM chỉ có internal IP + Private Google Access | Truy cập những Google APIs/services được hỗ trợ khi mạng được cấu hình phù hợp | Không phải cách kết nối tới mọi website hoặc API Internet |
| VM chỉ có internal IP, không NAT và không đường ra tương ứng | Không có đường Internet IPv4 thông thường từ VM | Vẫn có thể truy cập tài nguyên riêng/VPC khác nếu có route và kết nối phù hợp |

**Private IP không đồng nghĩa VM an toàn tuyệt đối.** VM vẫn cần IAM, hệ điều hành cập nhật, firewall phù hợp, quy tắc truy cập nội bộ và cơ chế giám sát.

## 2. Cloud NAT là gì? Public NAT và Private NAT

**Cloud NAT (Network Address Translation)** là dịch vụ được Google Cloud quản lý để chuyển đổi địa chỉ mạng cho những luồng đi ra từ tài nguyên được hỗ trợ. Google Cloud cung cấp hai loại chính:

| Loại | Đích sử dụng | Địa chỉ sau dịch | Ví dụ |
| --- | --- | --- | --- |
| **Public NAT** | Lưu lượng ra Internet hoặc đích IPv4 công khai theo các điều kiện hỗ trợ | External IP của NAT gateway | VM riêng tải package từ kho công khai; Cloud Run gọi API đối tác qua IP tĩnh |
| **Private NAT** | Lưu lượng từ mạng riêng đến mạng riêng khác theo các kết nối được hỗ trợ | IP thuộc dải Private NAT đã cấu hình | Kết nối giữa VPC hoặc kết nối hybrid có yêu cầu dịch dải IP |

Một NAT gateway được cấu hình cho **một loại NAT**. Hai gateway riêng có thể phục vụ các mục đích Public NAT và Private NAT trên những subnet thích hợp. Đừng coi Private NAT là một biến thể của Public NAT để đi Internet: mục tiêu, dải IP và cách định tuyến khác nhau.

Cloud NAT hỗ trợ nhiều kiểu dịch địa chỉ, trong đó **NAT44** (IPv4 → IPv4) là trường hợp chính của bài học. Một số cấu hình hỗ trợ **NAT64** (IPv6 → IPv4), nhưng phạm vi hỗ trợ khác nhau theo loại workload và NAT; cần xem tài liệu chính thức nếu triển khai IPv6.

### 2.1. Cloud Router có phải router chuyển tiếp gói tin NAT?

**Không.** Khi tạo Public NAT, bạn gắn NAT configuration với một **Cloud Router** ở cùng VPC và region. Cloud Router cung cấp **mặt điều khiển (control plane)** cho NAT; nó không trở thành thiết bị dataplane xử lý từng gói tin Internet, và Public NAT **không cần BGP** để hoạt động.

Cần phân biệt:

- **Cloud Router** có thể dùng BGP để trao đổi tuyến động trong các trường hợp kết nối hybrid như Cloud VPN/Interconnect; khi phục vụ NAT, vai trò của Cloud Router là lưu/quản lý cấu hình.
- **VPC routes** quyết định next hop cho gói tin.
- **Cloud NAT** dịch địa chỉ/port cho lưu lượng có route và phạm vi NAT phù hợp.
- **Firewall rules** quyết định kết nối được phép hay bị chặn.

Vì vậy tạo Cloud Router và NAT **không tự tạo default route** và không tự mở firewall egress.

## 3. Một kết nối đi ra được NAT như thế nào?

Giả sử một VM mở TCP connection:

~~~text
Nguồn trước NAT:
  10.20.0.10:51520  ->  198.51.100.20:443

Ví dụ sau khi Public NAT dịch:
  <NAT_EXTERNAL_IP>:30011  ->  198.51.100.20:443

Gói phản hồi:
  198.51.100.20:443  ->  <NAT_EXTERNAL_IP>:30011

Sau khi dịch ngược cho kết nối đã được thiết lập:
  198.51.100.20:443  ->  10.20.0.10:51520
~~~

`198.51.100.20` thuộc dải địa chỉ dành cho tài liệu minh họa; `<NAT_EXTERNAL_IP>` chỉ địa chỉ public thực tế được Cloud NAT cấp hoặc sử dụng. Port 30011 chỉ là ví dụ. Cloud NAT quản lý ánh xạ nguồn và cổng để các kết nối phân biệt được nhau.

### 3.1. SNAT, DNAT và connection tracking

1. VM gửi một gói tới địa chỉ công khai.
2. VPC chọn route có next hop thích hợp; firewall egress được đánh giá trên phía nguồn.
3. Public NAT thay **source IP** nội bộ bằng external IP của gateway và dùng source port được phân bổ khi cần (**SNAT**).
4. Server ngoài Internet gửi phản hồi về external IP/port đã thấy.
5. NAT nhận diện phản hồi thuộc một kết nối hợp lệ rồi đổi địa chỉ/port đích trở lại VM (**DNAT**).

Nếu một client bên ngoài tự gửi request mới vào external IP của Cloud NAT **mà không có ánh xạ kết nối thích hợp**, Public NAT không hoạt động như cơ chế mở cổng dịch vụ inbound. Nó chỉ hỗ trợ phản hồi cho lưu lượng đã bắt đầu từ bên trong.

> **Điểm quan trọng:** Public NAT không thay thế external Application Load Balancer, proxy phục vụ inbound, VPN hay các cách truy cập quản trị VM như IAP TCP forwarding. NAT chỉ xử lý bài toán egress theo cấu hình.

### 3.2. Vì sao port quan trọng?

Rất nhiều VM, node hoặc container có thể cùng chia sẻ một pool NAT external IP. Cloud NAT cấp **source ports** để phân biệt những luồng kết nối. Nếu số kết nối đồng thời, tốc độ mở kết nối hoặc kiểu traffic vượt số port được phân bổ, ứng dụng có thể gặp lỗi kết nối ra ngoài.

Cloud NAT cho phép cấu hình các thông số như **minimum ports per VM**, **maximum ports per VM** khi sử dụng dynamic port allocation, số lượng NAT IP và các timeout. Không nên tăng các giá trị vô hạn; hãy xem metric/log để xác định nút thắt, cân nhắc **connection pooling/reuse**, phân bổ thêm IP hoặc tối ưu workload.

## 4. Điều kiện để Public NAT cho phép egress

Một VM không có external IP sẽ kết nối được tới Internet qua Public NAT khi những điều kiện liên quan đều đúng:

| Điều kiện | Ví dụ đúng | Điều gì xảy ra nếu sai? |
| --- | --- | --- |
| **VPC/subnet/region** | VM nằm trong subnet region được gateway phục vụ | NAT không áp dụng cho VM |
| **Phạm vi IP nguồn** | Primary internal IP hoặc alias/secondary IP range đã bật NAT theo trường hợp hỗ trợ | Một loại traffic cụ thể không được dịch |
| **Route** | Route thích hợp tới đích có next hop là **default internet gateway** | Gói không đi theo đường mà Public NAT phục vụ |
| **Egress firewall** | Rule của VPC/VM cho phép traffic TCP 443 ra đích | Gói bị từ chối trước NAT |
| **DNS** | Tên miền public được phân giải đúng | Kết nối theo hostname thất bại dù NAT vẫn tốt |
| **NAT IP/port capacity** | Có đủ external IP và source ports khả dụng | Connection mới có thể bị drop/lỗi |
| **Chính sách dịch vụ** | API đối tác chấp nhận client và egress IP | Có thể nhận HTTP 403/401 từ phía ứng dụng dù network đã thông |

Đối với **Public NAT**, các route mà NAT sử dụng phải có next hop **default internet gateway**. Route đích `0.0.0.0/0` thường được tạo sẵn cho VPC và đáp ứng nhu cầu này. Nhưng nếu route bị xóa, bị thay thế hoặc route ưu tiên cao hơn đưa traffic đến một appliance/VPN khác, Cloud NAT có thể không được sử dụng.

### 4.1. NAT không bỏ qua firewall

Trong một VPC có rule egress chặn tất cả Internet traffic, việc tạo NAT gateway không tự vượt qua rule chặn. Google Cloud đánh giá firewall egress ở NIC nguồn trước NAT. Việc có default route và NAT IP **không đồng nghĩa mọi đích đều được truy cập**.

Cách thiết kế cho ứng dụng cần gọi API đối tác:

- Chỉ cho phép các protocol/port và đích thực sự cần (ví dụ HTTPS TCP 443) theo khả năng rule/policy.
- Giới hạn nguồn bằng network tags, service accounts hoặc cơ chế firewall phù hợp.
- Với nhu cầu kiểm soát domain/HTTP chi tiết, cân nhắc **proxy hoặc giải pháp lọc egress**; NAT không đọc và phê duyệt URL ứng dụng.
- Dùng IAM riêng để kiểm soát truy cập Google Cloud APIs; NAT không quyết định IAM của request.

### 4.2. NAT không tự cung cấp DNS

Nếu thử `curl https://api.example.com` bị báo không phân giải được tên miền, cần kiểm tra **Cloud DNS/resolver, DNS forwarding và chính sách DNS** trước. NAT chỉ có thể xử lý luồng IP sau khi client xác định địa chỉ đích và có route thích hợp.

## 5. VPC toàn cục nhưng Cloud NAT là cấu hình theo region

VPC network là tài nguyên **toàn cục**, còn subnet được đặt trong **region**. Mỗi Public NAT gateway gắn với **một VPC, một region và một Cloud Router**.

~~~mermaid
flowchart TD
    VPC["VPC: commerce-vpc (global)"]
    A["Subnet: commerce-private-a<br/>asia-southeast1"]
    B["Subnet: commerce-private-b<br/>asia-southeast1"]
    C["Subnet: commerce-private-us<br/>us-central1"]
    NA["Public NAT: nat-asia<br/>asia-southeast1"]
    NU["Public NAT: nat-us<br/>us-central1"]
    VPC --> A
    VPC --> B
    VPC --> C
    NA -. "Phục vụ subnet được chọn" .-> A
    NA -. "Có thể phục vụ" .-> B
    NU -. "Phục vụ nếu cấu hình" .-> C
~~~

Không thể lấy một gateway ở `asia-southeast1` để trực tiếp phục vụ subnet ở `us-central1`. Nếu sử dụng nhiều region, hãy thiết kế NAT tương ứng tại mỗi region cần egress.

### 5.1. Chọn những dải IP được NAT

Khi tạo Public NAT, bạn có thể chọn:

| Cách chọn | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| **All primary and secondary ranges** | NAT phục vụ primary/secondary IP ranges của mọi subnet trong region thuộc VPC | Lab nhỏ hoặc thiết kế cho phép mọi workload trong region ra ngoài |
| **Primary ranges của mọi subnet** | Chỉ primary IP ranges của mọi subnet trong region | Khi alias/secondary ranges không cần NAT |
| **Custom subnet IP ranges** | Chỉ các subnet và primary/secondary ranges được chỉ định | Production cần kiểm soát rõ subnet được phép |
| **Một custom subnet chỉ tên subnet** | Chỉ **primary range** của subnet đó | VM sử dụng primary internal IP |
| **Custom subnet với `:ALL`** | Cả primary và secondary ranges của subnet | Khi GKE/alias IP cần hỗ trợ cả dải phụ |

**Đừng mặc định chọn tất cả subnet** trong project doanh nghiệp nếu chỉ một workload cần egress. Phạm vi NAT ảnh hưởng bề mặt kết nối đi ra và có thể tác động quản trị chi phí.

### 5.2. Compute Engine VM có external IP có đi qua Public NAT không?

Đối với gói từ **primary internal IP** của NIC đã có external IP, Google Cloud thường thực hiện NAT một-một riêng của NIC; Public NAT **không thay thế** nguồn egress đó. Một số luồng từ **alias IP ranges** vẫn có thể thuộc phạm vi NAT theo cấu hình. Khi thử nghiệm, cần xác định đúng nguồn IP của gói và loại resource để tránh kết luận nhầm NAT đang làm việc.

## 6. Public NAT khác các cơ chế kết nối nào?

| Cơ chế | Mục tiêu | Khác biệt quan trọng |
| --- | --- | --- |
| **Public NAT** | Dịch địa chỉ cho egress từ resource private ra đích public IPv4 | Không mở ingress tự phát |
| **Private NAT** | Dịch địa chỉ cho kết nối private-to-private theo route/kết nối hỗ trợ | Không nhằm cung cấp Internet egress thông thường |
| **Private Google Access** | Cho VM chỉ có internal IP truy cập những Google APIs/services được hỗ trợ | Không dùng để truy cập tùy ý các website Internet |
| **Private Service Connect** | Truy cập dịch vụ được xuất bản qua endpoint/backend riêng trong VPC | Không phải NAT gateway chung cho mọi Internet traffic |
| **Cloud VPN/Interconnect** | Kết nối giữa VPC và mạng ngoài/on-premises qua các cơ chế hybrid | Không tự thay thế Public NAT |
| **Cloud Load Balancing** | Nhận và phân phối traffic tới backend (tùy loại LB) | Phục vụ inbound/forwarding theo cấu hình, khác NAT egress |
| **IAP TCP forwarding** | Cung cấp đường truy cập quản trị phù hợp đến VM không có public IP | Không phải Internet egress cho ứng dụng chạy trên VM |
| **External proxy/egress firewall** | Kiểm soát theo ứng dụng, URL hoặc policy nâng cao | Có thể bổ trợ NAT nếu cần kiểm tra lưu lượng sâu |

### 6.1. Gọi Google Cloud APIs từ VM private có cần Cloud NAT?

**Không nhất thiết.** Với Compute Engine VM không có external IP, **Private Google Access** có thể cho phép đi tới Google APIs/services được hỗ trợ. Tùy loại dịch vụ và thiết kế, còn có lựa chọn Private Service Connect.

Ví dụ VM riêng chỉ cần tải object từ Cloud Storage. Trước khi triển khai Public NAT, hãy đánh giá **Private Google Access** và IAM/service account phù hợp. Nếu VM cũng cần tải package từ kho phần mềm bên ngoài Google, Public NAT có thể vẫn cần thiết cho đường Internet đó.

Điều này giúp tránh việc dùng Cloud NAT cho mọi tình huống chỉ vì đích có tên miền Google. **DNS, route, dải IP và cơ chế dịch vụ** vẫn cần được kiểm tra theo lựa chọn kết nối.

## 7. Thực hành: tạo VPC và Public NAT cho một VM riêng

Bài thực hành sau sử dụng một VM trong region `asia-southeast1` (Singapore) với internal IP, subnet riêng, Cloud Router và Public NAT. **Lệnh tạo VM, NAT gateway và external IP có thể phát sinh chi phí**; chỉ thực hiện trong project lab được cấp phép, có budget và quy trình dọn dẹp. Tên/địa chỉ chỉ minh họa và cần kiểm tra tính sẵn có theo project.

### 7.1. Kiểm tra project và quyền

~~~bash
gcloud auth list
gcloud config set project PROJECT_ID
gcloud config get-value project
gcloud services enable compute.googleapis.com --project=PROJECT_ID
~~~

Quyền cần thiết có thể gồm tạo network, subnet, VM, router/NAT và quản lý địa chỉ IP; hãy dùng vai trò hẹp phù hợp thay vì cấp Owner không cần thiết. CLI phải đăng nhập tài khoản có quyền, project liên kết billing khi dịch vụ yêu cầu.

### 7.2. Tạo VPC custom mode và subnet

~~~bash
# Tạo VPC mới để giới hạn phạm vi lab
gcloud compute networks create nat-lab-vpc \
  --subnet-mode=custom \
  --project=PROJECT_ID

# Tạo subnet trong region dự kiến
gcloud compute networks subnets create nat-lab-private \
  --network=nat-lab-vpc \
  --region=asia-southeast1 \
  --range=10.20.0.0/24 \
  --project=PROJECT_ID
~~~

Khi tạo subnet custom, bảo đảm CIDR không trùng dải đang được dùng trong VPC. Nếu muốn kết nối Google APIs từ VM private mà không dựa vào NAT, cân nhắc bật Private Google Access theo yêu cầu kiến trúc.

### 7.3. Tạo VM không có external IP

~~~bash
gcloud compute instances create nat-lab-vm \
  --zone=asia-southeast1-b \
  --machine-type=e2-micro \
  --network-interface=subnet=nat-lab-private,no-address \
  --project=PROJECT_ID
~~~

Tùy image được chọn và cấu hình firewall/SSH, bạn có thể cần quyền và phương thức kết nối quản trị riêng, chẳng hạn **IAP TCP forwarding**. VM không có external IP không thể được SSH trực tiếp qua Internet theo cách dùng external IP của VM.

Kiểm tra địa chỉ:

~~~bash
gcloud compute instances describe nat-lab-vm \
  --zone=asia-southeast1-b \
  --format="yaml(networkInterfaces)" \
  --project=PROJECT_ID
~~~

Mục tiêu là NIC có internal IP thuộc `10.20.0.0/24` và **không có `accessConfigs` external IPv4** trên NIC dùng làm nguồn. Nếu VM đã có external IP, kết quả kiểm thử Public NAT có thể không phản ánh phương án dự kiến.

### 7.4. Tạo Cloud Router cho NAT

~~~bash
gcloud compute routers create nat-lab-router \
  --network=nat-lab-vpc \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

Không cần cấu hình BGP peer để Public NAT hoạt động trong ví dụ này.

### 7.5. Tạo Public NAT tự cấp external IP

~~~bash
gcloud compute routers nats create nat-lab-public \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --auto-allocate-nat-external-ips \
  --nat-custom-subnet-ip-ranges=nat-lab-private \
  --project=PROJECT_ID
~~~

Ý nghĩa những cờ quan trọng:

- `--router`: Cloud Router chứa NAT configuration.
- `--region`: region của Cloud Router, gateway và subnet được phục vụ.
- `--auto-allocate-nat-external-ips`: để Google Cloud tự phân bổ các external IP cho Public NAT.
- `--nat-custom-subnet-ip-ranges=nat-lab-private`: chỉ primary IP range của subnet này được cấu hình NAT; các subnet khác không tự được thêm.
- `--project`: project chứa cấu hình lab.

Trường hợp cần phục vụ primary **và** secondary ranges của subnet đó, cú pháp custom range thích hợp có dạng `--nat-custom-subnet-ip-ranges=nat-lab-private:ALL`. Nếu muốn NAT cho tất cả primary và secondary ranges của tất cả subnet trong region, có cờ `--nat-all-subnet-ip-ranges`; hai cách chọn phạm vi là **các lựa chọn loại trừ nhau** trong một lệnh.

### 7.6. Kiểm tra NAT vừa tạo

~~~bash
gcloud compute routers nats list \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud compute routers nats describe nat-lab-public \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud compute routes list \
  --filter="network:nat-lab-vpc" \
  --project=PROJECT_ID
~~~

Đọc cấu hình và xác minh phạm vi subnet, loại IP allocation, region và tuyến mặc định có next hop là default internet gateway. Đừng kết luận “NAT đã làm việc” chỉ vì lệnh create thành công.

### 7.7. Thử egress thực tế

Kết nối tới VM qua phương thức được duyệt; ví dụ IAP TCP forwarding nếu đã cấu hình quyền và firewall:

~~~bash
gcloud compute ssh nat-lab-vm \
  --zone=asia-southeast1-b \
  --tunnel-through-iap \
  --project=PROJECT_ID
~~~

Lệnh `--tunnel-through-iap` đòi hỏi cấu hình IAP phù hợp, trong đó có quyền IAM và ingress firewall cho IAP TCP forwarding. **IAP không được tự cấu hình bởi Cloud NAT**. Nếu chưa chuẩn bị IAP, sử dụng phương thức quản trị khác đã được tổ chức cho phép.

Bên trong VM, thử gọi một endpoint HTTP(S) **bên ngoài Google Cloud**:

~~~bash
curl -I --connect-timeout 10 https://example.com

# Chỉ dùng nếu cần kiểm tra IP egress từ phía dịch vụ ngoài và
# chính sách tổ chức cho phép truy cập endpoint của bên thứ ba.
curl -4 --connect-timeout 10 https://ifconfig.me/ip
~~~

Nếu nhận được phản hồi, VM có thể ra ngoài tới đích đã thử. Nếu dịch vụ kiểm tra IP phản hồi bằng IP thuộc pool NAT của gateway thì đó là dấu hiệu thêm về đường egress. Tuy nhiên phải **kiểm tra external IP thực tế được NAT cấp**, route, firewall và nguồn traffic trước khi kết luận toàn bộ workload đều dùng NAT. Dịch vụ kiểm tra IP của bên thứ ba có điều khoản, độ tin cậy và giới hạn riêng.

Để thử chắc chắn NAT cho VM private, đừng chỉ gọi Cloud Storage hoặc Google APIs: **Private Google Access** có thể khiến Google API hoạt động ngay cả khi Public NAT chưa được cấu hình.

## 8. Egress IP tĩnh khi bên thứ ba dùng allowlist

Một số API thanh toán, dịch vụ đối tác hoặc database ngoài Google Cloud chỉ nhận request từ **danh sách IP công khai cho phép (IP allowlist)**. Nếu dùng NAT với external IP **tự động phân bổ**, tập IP có thể thay đổi khi gateway được sửa hoặc mở rộng. Với yêu cầu allowlist, hãy dùng **regional static external IP** và gắn vào Public NAT theo **manual allocation**.

### 8.1. Tạo và gắn static external IP

~~~bash
# Dành riêng địa chỉ IPv4 public trong cùng region
gcloud compute addresses create nat-lab-egress-ip \
  --region=asia-southeast1 \
  --project=PROJECT_ID

# Xem địa chỉ thực tế để cung cấp cho đối tác allowlist
gcloud compute addresses describe nat-lab-egress-ip \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

Nếu tạo NAT gateway **mới** với manual IP, ví dụ:

~~~bash
gcloud compute routers nats create nat-partner-egress \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --nat-external-ip-pool=nat-lab-egress-ip \
  --nat-custom-subnet-ip-ranges=nat-lab-private \
  --project=PROJECT_ID
~~~

**Không chạy lệnh tạo gateway mới ở trên cùng với NAT gateway đã phục vụ chồng lấn cùng primary range trong lab**. Hãy chọn **một** cấu hình NAT hợp lệ: dùng manual IP **thay thế** cấu hình tự động hoặc làm ở một môi trường/cấu hình riêng đã được thiết kế. Cloud NAT có các quy tắc về dải nguồn không được chồng lấn giữa những gateway cùng loại và phạm vi.

Lệnh minh họa trên giải thích cấu hình **tạo mới** khi chọn manual allocation ngay từ đầu. Trong môi trường thực có gateway đã chạy, hãy lập kế hoạch thay đổi cấu hình `gcloud compute routers nats update` theo hướng dẫn Google Cloud, vì đổi external IP có thể ảnh hưởng kết nối đang tồn tại.

### 8.2. Một IP tĩnh có đủ không?

Không phải luôn luôn. Nếu workload mở nhiều kết nối đồng thời tới cùng đích, số source ports hữu dụng trên một IP có thể trở thành giới hạn. Với Cloud Run hoặc GKE autoscale, nhu cầu cổng có thể tăng mạnh. Khi đó:

- Dùng **connection pooling/keep-alive** thay vì tạo kết nối mới cho mọi request.
- Đo số kết nối đồng thời và các NAT error/dropped packet metrics.
- Cân nhắc nhiều static IP, kích thước port allocation và thiết kế scale.
- Thống nhất với đối tác **toàn bộ** egress IP hợp lệ; tránh thêm IP mà quên cập nhật allowlist.
- Đánh giá chi phí external IP và dữ liệu xử lý khi tăng capacity.

## 9. Cloud NAT với GKE private nodes

Trong GKE, những pod có thể chạy trên node VM không có external IP. Pod vẫn có nhu cầu tải gói, gọi API đối tác hoặc gửi telemetry bên ngoài Google Cloud. **Public NAT** có thể hỗ trợ egress cho node/pod traffic phù hợp với cấu hình.

### 9.1. Primary và secondary ranges

Nhiều GKE clusters sử dụng **VPC-native** với **alias IPs**:

- Node sử dụng primary internal IP thuộc dải primary của subnet.
- Pod IP và Service IP có thể nằm trong những **secondary ranges** được tạo/được quản lý phù hợp.
- Tùy cơ chế IP masquerading/SNAT ở node, lưu lượng pod có thể rời node bằng source IP của node hoặc IP pod.

Vì vậy NAT cần được cấu hình đúng **dải nguồn thực sự đi ra**, không mặc định mỗi kết nối pod đều dùng primary IP của node.

~~~mermaid
flowchart LR
    POD["GKE Pod<br/>Pod IP từ secondary range"]
    NODE["Node VM<br/>Primary IP"]
    MASQ["Cấu hình IP masquerade / SNAT của GKE"]
    NAT["Public NAT<br/>Primary/secondary ranges phù hợp"]
    API["Đích Internet"]
    POD --> MASQ
    NODE --> MASQ
    MASQ --> NAT
    NAT --> API
~~~

Để kiểm soát egress và tránh việc NAT hai lần không cần thiết, hãy kiểm tra **GKE IP masquerade policy**, thiết kế secondary ranges và hướng dẫn networking chính thức phù hợp với chế độ cluster. Với một số kiến trúc GKE, có thể khuyến nghị giữ nguồn pod IP thay vì SNAT tại node để Cloud NAT xử lý, nhưng cách chọn còn phụ thuộc điểm đến (Internet hay hybrid) và cấu hình cluster.

### 9.2. NAT không thay thế các kiểm soát của GKE

- **NetworkPolicy** giới hạn những kết nối pod được phép.
- **Firewall** và route VPC tác động tới đường đi.
- **Workload Identity Federation for GKE** giải quyết danh tính/IAM khi pod gọi Google APIs.
- **Private Google Access** có thể đáp ứng một số nhu cầu Google APIs mà không cần Public NAT.
- **Cloud NAT** xử lý việc dịch địa chỉ cho luồng phù hợp.

Việc GKE pod truy cập được Internet không đồng nghĩa pod đã có quyền đọc Cloud Storage hoặc Pub/Sub; quyền đó còn phụ thuộc danh tính workload và IAM.

## 10. Cloud Run và nhu cầu egress IP cố định

Cloud Run có cơ chế egress mặc định và có thể truy cập Internet mà **không dùng Cloud NAT do bạn cấu hình**. Muốn Cloud Run dùng **static egress IP** qua NAT, cần chủ động đưa traffic qua VPC và áp dụng gateway đúng region/subnet.

Một mô hình thường dùng:

1. Tạo hoặc chọn VPC/subnet phù hợp với Cloud Run service.
2. Cấu hình **Direct VPC egress** (ưu tiên khi phù hợp) hoặc **Serverless VPC Access connector**.
3. Chọn **all-traffic egress** để lưu lượng Internet từ service đi qua VPC.
4. Tạo Public NAT gateway phục vụ subnet/nguồn traffic tương ứng, dùng **manual static external IP**.
5. Kiểm tra firewall, routing, số NAT ports và địa chỉ egress thực tế ở phía đối tác.

~~~mermaid
flowchart LR
    CR["Cloud Run service"]
    V["Direct VPC egress<br/>all-traffic"]
    SUB["VPC subnet cùng region"]
    NAT["Public NAT<br/>Static external IP"]
    PARTNER["API đối tác<br/>Allowlist IP"]
    CR --> V
    V --> SUB
    SUB --> NAT
    NAT --> PARTNER
~~~

Lệnh tham khảo khi **triển khai hoặc cập nhật** Cloud Run service có sẵn image và VPC/subnet đã được cấu hình:

~~~bash
gcloud run deploy orders-api \
  --image=IMAGE_URL \
  --network=nat-lab-vpc \
  --subnet=nat-lab-private \
  --region=asia-southeast1 \
  --vpc-egress=all-traffic \
  --project=PROJECT_ID
~~~

Đây là lệnh thay đổi workload, nên chỉ chạy khi có image hợp lệ và quyền deploy phù hợp. NAT phải được cấu hình để phục vụ traffic của Cloud Run trong subnet, với public IP tĩnh nếu đối tác sử dụng allowlist.

**Cạm bẫy phổ biến:** nếu Cloud Run chỉ cấu hình VPC egress cho **private ranges** thay vì **all traffic**, những request Internet công khai có thể vẫn đi theo đường egress mặc định, nên bên thứ ba không nhìn thấy địa chỉ NAT tĩnh như mong muốn.

### 10.1. NAT không tự cấu hình inbound Cloud Run

Cloud Run có hệ thống xử lý request đến riêng (URL, ingress controls, authentication, load balancing khi dùng). Tạo Public NAT chỉ ảnh hưởng egress thích hợp, không biến NAT external IP thành endpoint nhận HTTP requests cho Cloud Run.

## 11. Private NAT: khi đích là một mạng riêng khác

Public NAT giải quyết **private-to-public**. **Private NAT** áp dụng cho **private-to-private** theo những trường hợp kết nối mạng được Google Cloud hỗ trợ, chẳng hạn các mô hình kết nối VPC hoặc hybrid.

Ví dụ hai môi trường sử dụng dải IP riêng và cần áp dụng NAT vì chính sách quản trị/khả năng trùng địa chỉ. Private NAT có thể dịch nguồn sang **dải IP Private NAT được cấu hình**; lưu lượng đi theo tuyến kết nối riêng phù hợp thay vì external Internet gateway.

| Yếu tố | Public NAT | Private NAT |
| --- | --- | --- |
| Đích điển hình | Public IPv4 trên Internet | Mạng riêng đích |
| IP sau dịch | Regional external IP | IP từ Private NAT subnet/range |
| Route sử dụng | Route phù hợp có next hop default internet gateway | Route thuộc các loại kết nối riêng được hỗ trợ |
| Tình huống | VM private tải cập nhật, Cloud Run gọi API đối tác | Private connectivity cần NAT giữa mạng |
| Có nhận inbound bất kỳ từ bên ngoài không? | Không | Không; chỉ phản hồi phù hợp với kết nối |

Private NAT **không tự tạo VPC Peering, Cloud VPN, Cloud Interconnect hoặc Network Connectivity Center kết nối mạng**. Trước khi áp dụng phải thiết kế route, phạm vi dải IP, kiểu kết nối và firewall. Chi tiết cấu hình Private NAT thuộc chủ đề triển khai nâng cao; tránh đem các cờ Public NAT cho external IP áp vào Private NAT mà không kiểm tra docs.

## 12. Observability: làm sao biết NAT đang hoạt động?

Cloud NAT cung cấp **Cloud Logging**, **Cloud Monitoring metrics** và thông tin phân tích mạng để theo dõi gateway.

### 12.1. NAT logs

Tùy cấu hình, NAT logging có thể ghi:

- **Translation logs** khi một luồng kết nối được tạo và dịch địa chỉ.
- **Error logs** khi gói bị drop do nguyên nhân được NAT log hỗ trợ, ví dụ không còn cổng phân bổ.
- Thông tin liên quan đến nguồn, đích, NAT IP, cổng và thời điểm theo khả năng log.

Ví dụ bật logging trên gateway hiện có:

~~~bash
gcloud compute routers nats update nat-lab-public \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --enable-logging \
  --log-filter=ERRORS_ONLY \
  --project=PROJECT_ID
~~~

`ERRORS_ONLY` hữu ích để quan sát những sự kiện lỗi NAT được hỗ trợ. Khi cần phân tích luồng translation để kiểm chứng traffic, có thể đổi logging policy để thu thập loại log phù hợp. **Không nên bật mọi translation logs lâu dài mà không đánh giá volume và chi phí Cloud Logging**.

Log NAT **không ghi mọi gói đã đi qua firewall và không phải công cụ duy nhất để khẳng định toàn bộ lưu lượng mạng**. Ví dụ egress firewall chặn request từ trước khi NAT thì NAT không tạo được translation log cho request đó; hãy dùng thêm Firewall Rules Logging/Connectivity Tests.

### 12.2. Những metric nên theo dõi

| Nhóm metric | Ý nghĩa vận hành | Khi nào cần phản ứng |
| --- | --- | --- |
| NAT port allocation/usage | Mức sử dụng cổng cấp cho nguồn | Gần chạm giới hạn hoặc thường xuyên thiếu cổng |
| Dropped packets / NAT errors | Luồng không được xử lý do lỗi NAT | Tăng đột ngột, đi kèm timeout |
| Open connections / connection creation | Nhu cầu kết nối theo thời gian | Spike liên quan deploy hoặc scaling |
| Egress bytes / traffic | Lượng dữ liệu xử lý qua NAT | Tăng mạnh, liên quan chi phí/egress |
| NAT IP usage | Số lượng/khả năng sử dụng IP NAT | Cần thêm IP hoặc ổn định allowlist |

Tên metric chính xác, dimension và khả năng hỗ trợ phụ thuộc dịch vụ/cấu hình. Hãy lấy tên metric trực tiếp từ **Cloud Monitoring metrics explorer** và tài liệu Cloud NAT, tránh cố định tên không được xác minh trong dashboard.

### 12.3. NAT là dịch vụ quản lý phân tán

Không có “máy ảo NAT gateway” do bạn tạo để SSH vào và xem `iptables`. Cloud Router/NAT control plane chịu trách nhiệm cấu hình; hạ tầng mạng Google Cloud thực hiện dịch địa chỉ. Việc quan sát cần dùng **logs, metrics, VPC Flow Logs**, status configuration và dữ liệu của ứng dụng thay vì kiểm tra một VM gateway giả định.

## 13. Các lỗi phổ biến và quy trình kiểm tra

| Triệu chứng | Khả năng thường gặp | Kiểm tra ưu tiên |
| --- | --- | --- |
| VM không truy cập Internet | NAT không phục vụ subnet/region, thiếu route, firewall egress deny, DNS lỗi | NIC external IP, NAT region/subnet, route, firewall, DNS |
| VM vẫn ra Internet khi chưa tạo NAT | VM có external IP hoặc tồn tại đường egress khác | `accessConfigs`, routes, proxy/NAT appliance, VPN |
| Chỉ GKE node ra được, Pod không ra | NAT chưa bao secondary range hoặc IP masquerade/SNAT không khớp | Pod source IP thực tế, secondary ranges, GKE policy |
| Cloud Run gọi được Internet nhưng IP không phải IP NAT | Chưa chọn Direct VPC egress/all-traffic hoặc NAT không đúng subnet | Cấu hình Cloud Run egress và NAT |
| Gọi Google APIs được nhưng API đối tác không được | Private Google Access hoạt động; Public NAT/route chưa đúng | Thử endpoint Internet khác Google, kiểm tra đường egress |
| Cùng một đích, lúc được lúc timeout | Cạn NAT source ports, burst connection, retry hoặc upstream giới hạn | NAT metrics, logs, connection reuse, capacity |
| Không có NAT logs | Logging chưa bật, filter không phù hợp hoặc traffic bị firewall chặn trước NAT | NAT log configuration, filters, firewall logs |
| External API trả `403` | IP allowlist sai hoặc token/authorization phía ứng dụng sai | IP egress thực tế và phản hồi HTTP/API |
| Truy cập được qua IP nhưng không qua hostname | DNS resolver không hoạt động đúng | DNS policy, Cloud DNS, kết quả phân giải |
| Traffic giữa hai private VPC không đi theo Public NAT | Public NAT không phải private connectivity NAT | Route/peering/VPN và đánh giá Private NAT |

### 13.1. Thứ tự debug có thể lặp lại

~~~mermaid
flowchart TD
    A["Không kết nối được đích ngoài"] --> B{"Workload có external IP riêng?"}
    B -->|Có| C["Xác định lại nguồn egress và routing; Public NAT có thể không áp dụng"]
    B -->|Không| D{"NAT cùng VPC/region và phục vụ source range?"}
    D -->|Không| E["Sửa NAT scope/subnet"]
    D -->|Có| F{"Route tới Internet gateway và firewall cho phép?"}
    F -->|Không| G["Rà soát route, firewall egress"]
    F -->|Có| H{"Phân giải DNS và bắt tay TCP/TLS?"}
    H -->|Không| I["Phân biệt DNS, port exhaustion, upstream timeout"]
    H -->|Có| J["Kiểm tra response ứng dụng, IAM/token và allowlist"]
~~~

**Thứ tự thực hành:**

1. Xác minh network interface, source IP, region, subnet, primary/secondary ranges và việc VM có external IP hay không.
2. Đọc cấu hình NAT gateway, Cloud Router, public NAT IP mode và các dải nguồn.
3. Kiểm tra route hiệu lực tới destination: Public NAT cần next hop default internet gateway.
4. Kiểm tra firewall egress; dùng firewall logs/Connectivity Tests khi cần.
5. Thử truy vấn DNS và HTTP(S) bằng endpoint phù hợp với bài toán.
6. Kiểm tra NAT logs/metrics về port exhaustion hoặc dropped packets.
7. Nếu network thông nhưng ứng dụng lỗi, đọc HTTP status, TLS, token, IAM, remote allowlist và quota đích.

**Không đưa private keys, access token hoặc dữ liệu khách hàng vào logs trong quá trình debug.**

## 14. Bảo mật: NAT là một lớp trong kiến trúc egress

Cloud NAT có lợi ích giảm nhu cầu external IP của từng VM, nhưng **không phải firewall kiểm soát mọi đích và không phải giải pháp ngăn exfiltration đầy đủ**. Các quyền và chính sách bổ sung cần bao gồm:

- **Firewall egress:** cho phép đúng protocol, port và đích theo thiết kế.
- **IAM/service accounts:** hạn chế quyền gọi Google Cloud APIs và thay đổi VPC/NAT.
- **Routing:** kiểm soát default routes, policy-based routing và đường qua proxy nếu có.
- **Private Google Access/PSC:** ưu tiên đường tới Google APIs khi phù hợp, giảm phụ thuộc đường Internet chung.
- **DNS/security services:** quản trị tên miền, DNS forwarding và chính sách truy cập dịch vụ.
- **Logs/metrics:** theo dõi NAT error, connection spikes và mức sử dụng.
- **Budget:** theo dõi phí NAT, IP, egress, VM/GKE/Cloud Run.

### 14.1. Dùng Shared VPC thì NAT đặt ở đâu?

Nếu sử dụng **Shared VPC**, subnet và mạng thuộc **host project**. Network team quản lý cấu hình NAT/Cloud Router tại mạng host theo quyền tương ứng; những VM hoặc workload trong **service project** có thể sử dụng mạng/subnet Shared VPC khi được cấu hình và ủy quyền đúng.

Không nên mặc định tạo NAT ở service project rồi kỳ vọng NAT tự áp dụng lên subnet của host project. Hãy xác định **project sở hữu VPC**, region/subnet được sử dụng và vai trò quản trị mạng trước khi tạo gateway.

### 14.2. NAT không thay thế xác thực dịch vụ

Một VM có egress NAT và gọi được `storage.googleapis.com` vẫn cần danh tính và IAM phù hợp để đọc bucket private. Ngược lại, service account có `roles/storage.objectViewer` vẫn có thể thất bại khi DNS/route/network không cho phép gửi request. **Authentication/authorization và network connectivity là hai lớp độc lập phải cùng đúng.**

## 15. Chi phí Cloud NAT và cách dự báo

Public NAT có thể phát sinh nhiều khoản phí, thường gồm:

1. **Chi phí gateway theo thời gian sử dụng** và mô hình định giá áp dụng.
2. **Chi phí dữ liệu được NAT xử lý** theo dung lượng.
3. **Chi phí external IP** dùng bởi gateway.
4. **Chi phí data transfer out** tương ứng với lưu lượng rời mạng.
5. **Chi phí Cloud Logging/Monitoring hoặc tài nguyên hỗ trợ** tùy cách cấu hình và sử dụng.

Do đó, một VM nhỏ chạy ít CPU không bảo đảm toàn bộ bài lab có chi phí thấp nếu download/upload dữ liệu lớn hoặc NAT gateway/IP vẫn còn tồn tại.

### 15.1. Ước tính cấu trúc chi phí

Công thức minh họa:

~~~text
Chi phí NAT và egress ước tính
  = phí gateway theo thời gian/đơn vị áp dụng
  + (GiB được NAT xử lý × đơn giá xử lý/GiB)
  + (số external IP × thời gian sử dụng × giá IP)
  + phí data transfer out
  + phí logging/khác nếu có
~~~

Không dùng công thức này như báo giá chính thức; còn có các tier, điều kiện và loại lưu lượng đặc thù. **Đơn giá cần lấy từ trang Cloud NAT pricing ở thời điểm triển khai** vì giá và tính năng có thể thay đổi theo thời gian, region hoặc thỏa thuận.

### 15.2. Những lỗi tạo chi phí ngoài dự kiến

- Tạo NAT gateway trong nhiều region để thử nghiệm nhưng quên xóa.
- Giữ regional static external IP sau khi lab kết thúc.
- Bật logging translation ở mức lớn, làm tăng lượng dữ liệu được lưu.
- Chạy job download dữ liệu giữa Internet và VM/GKE không giới hạn.
- Tăng số NAT IP mà không rà soát nhu cầu ports thực tế.
- Triển khai Cloud Run với all-traffic egress qua NAT dù workload chỉ cần gọi Google APIs có phương án kết nối riêng khác.

Nên tạo **Cloud Billing budget** cho project lab, gắn owner, ngày kết thúc và kiểm kê chi phí theo **Networking/Cloud NAT SKU**. Budget chỉ cảnh báo; không tự dừng tài nguyên.

## 16. Dọn dẹp lab sau khi thực hành

Khi không còn dùng tài nguyên demo, cần dọn theo **thứ tự phụ thuộc và xác nhận đúng project**. Những lệnh dưới đây là các thao tác **xóa thật** và có thể làm gián đoạn hệ thống nếu thay tên sai. Chỉ dùng trong project lab không có dữ liệu cần giữ.

1. Xác minh project, VM, network và NAT gateway thực sự thuộc lab.
2. Xóa VM thử nghiệm và những disk phụ trợ không còn cần.
3. Xóa NAT gateway và Cloud Router lab khi không còn consumer khác.
4. Kiểm tra và giải phóng external IP tĩnh đã reserve riêng.
5. Xóa subnet/VPC lab sau khi chắc chắn không còn tài nguyên phụ thuộc.
6. Kiểm tra Cloud Billing sau độ trễ cập nhật để phát hiện phí còn sót.

Ví dụ kiểm kê **chỉ đọc** trước khi dọn:

~~~bash
gcloud compute instances list --project=PROJECT_ID

gcloud compute routers list \
  --regions=asia-southeast1 \
  --project=PROJECT_ID

gcloud compute routers nats list \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud compute addresses list \
  --filter="region:(asia-southeast1)" \
  --project=PROJECT_ID
~~~

Nếu đã dùng static IP làm egress allowlist, phối hợp với đối tác để cập nhật allowlist sau khi ngừng sử dụng; tránh để IP được giải phóng nhưng vẫn tồn tại trong danh sách tin cậy của hệ thống bên ngoài.

## 17. Tình huống thiết kế: ba workload dùng chung project

Một công ty triển khai:

- **VM batch private** trong subnet `batch-private` ở `asia-southeast1`, cần tải dependencies từ Internet.
- **GKE private node pool** với pod IP từ secondary range; cần gọi API đối tác.
- **Cloud Run orders-api** cần gọi cổng thanh toán chỉ cho phép một số external IP cố định.

Phương án đề xuất:

| Thành phần | Thiết kế mạng | Điều cần kiểm chứng |
| --- | --- | --- |
| VM batch | Không external IP; subnet được Public NAT phục vụ | Default internet gateway route, firewall egress, NAT primary range |
| GKE private nodes/pods | Dải primary/secondary được NAT phục vụ theo source IP thực tế | IP masquerade policy, secondary ranges, port capacity |
| Cloud Run | Direct VPC egress + `all-traffic`, Public NAT manual IP | Region/subnet, egress IP thực tế, allowlist bên đối tác |
| Truy cập Google APIs | Private Google Access/PSC theo nhu cầu | DNS, API IAM, đường đi và service support |
| Quản trị | Firewall, IAM, Cloud Monitoring, Cloud Billing | Logs, dropped packets, chi phí NAT/IP/egress |

### 17.1. Vì sao phải thiết kế riêng các lớp?

Nếu VM kết nối Internet được nhưng Cloud Run trả IP khác NAT, lỗi có thể nằm ở **Cloud Run egress mode** chứ không phải NAT. Nếu GKE pod lỗi còn node kết nối được, phải kiểm tra **source range và IP masquerade**. Nếu cả ba kết nối ra được nhưng Cloud Storage trả `403`, nguyên nhân có thể là **IAM**. Nếu mọi luồng đều chậm và drop sau khi autoscaling, cần đánh giá **port allocation**.

~~~mermaid
flowchart TD
    A["Xác định nhu cầu egress"] --> B{"Đích là Google API được hỗ trợ?"}
    B -->|Có| C["Đánh giá Private Google Access / PSC"]
    B -->|Không| D{"Đích Internet công khai?"}
    D -->|Có| E["Public NAT + routes/firewall"]
    D -->|Không| F["Đánh giá private connectivity / Private NAT"]
    E --> G{"Đối tác cần IP cố định?"}
    G -->|Có| H["Manual regional static NAT IP + allowlist"]
    G -->|Không| I["Auto-allocated NAT IP có thể phù hợp"]
    C --> J["Kiểm tra IAM, DNS, metrics và chi phí"]
    F --> J
    H --> J
    I --> J
~~~

Thiết kế này giúp chọn đúng dịch vụ thay vì dùng một gateway NAT cho mọi bài toán kết nối.

## 18. Bài tập tự kiểm tra

**Câu 1.** Một VM không có external IPv4, nằm trong subnet được NAT phục vụ. VM có mặc nhiên nhận kết nối SSH từ laptop qua external IP của NAT không?

*Gợi ý:* Không. Public NAT không cho các kết nối inbound tự phát. Dùng phương thức quản trị như IAP TCP forwarding hoặc VPN/bastion được phê duyệt.

**Câu 2.** Vì sao tạo Cloud Router và Public NAT xong mà VM vẫn không truy cập được HTTPS ngoài Internet?

*Gợi ý:* Có thể thiếu route có next hop default internet gateway, egress firewall chặn, subnet/region không thuộc NAT, DNS lỗi hoặc port capacity không đủ. Cloud Router/NAT không tự sửa những điều kiện này.

**Câu 3.** VPC có subnet ở Singapore và Iowa. Có dùng cùng một NAT gateway region Singapore để phục vụ cả hai subnet không?

*Gợi ý:* Không. NAT gateway gắn với một region; tạo gateway tương ứng cho region khác nếu cần.

**Câu 4.** Cloud Run service đã có thể gọi Internet nhưng đối tác báo source IP không khớp allowlist của NAT. Bạn kiểm tra gì đầu tiên?

*Gợi ý:* Direct VPC egress hoặc connector, `--vpc-egress=all-traffic`, subnet/region, và cấu hình Public NAT manual external IP.

**Câu 5.** Một GKE node private ra Internet được, nhưng pod có alias IP từ secondary range lại timeout. Phương án điều tra phù hợp?

*Gợi ý:* Kiểm tra source IP sau IP masquerading/SNAT, secondary range trong NAT configuration, firewall egress và NAT port usage.

**Câu 6.** VM private gọi Cloud Storage bằng Private Google Access thành công. Điều đó có chứng minh Public NAT đang hoạt động không?

*Gợi ý:* Không. Private Google Access có thể cung cấp đường tới những Google APIs được hỗ trợ mà không dùng Public NAT cho Internet public. Hãy thử endpoint ngoài Google phù hợp và xem cấu hình/metrics.

**Câu 7.** Khi lưu lượng tăng cao, hệ thống gặp lỗi kết nối mới tới cùng API đối tác, còn các kết nối đã mở vẫn hoạt động. Nêu một nguyên nhân ở lớp NAT.

*Gợi ý:* Thiếu source ports do nhiều kết nối đồng thời hoặc tốc độ tạo connection cao. Kiểm tra logs/metrics, connection pooling và NAT IP/port allocation.

**Câu 8.** Dùng một external IP tĩnh cho NAT có bảo đảm ứng dụng an toàn khỏi mọi kết nối độc hại không?

*Gợi ý:* Không. NAT không thay thế firewall egress, IAM, xác thực API, DNS/security controls và giám sát.

**Câu 9.** Cloud NAT và Cloud Router có làm gói HTTP phải đi qua một VM gateway tạo thêm hop không?

*Gợi ý:* Không. Chúng cung cấp cấu hình/control plane, còn dataplane NAT được Google Cloud triển khai phân tán trong hạ tầng mạng.

**Câu 10.** Khi kết thúc lab, đã xóa VM nhưng vẫn thấy phí mạng. Những mục nào cần kiểm tra?

*Gợi ý:* NAT gateway, external IP reserve, logging, dữ liệu egress đã phát sinh và các tài nguyên khác còn hoạt động; nhớ dữ liệu billing có độ trễ.

## 19. Các điểm cần ghi nhớ

- **Public NAT là cơ chế egress** cho tài nguyên có IP riêng khi cần đi tới đích Internet IPv4, không phải cổng nhận inbound từ Internet.
- **VPC routes, firewall và DNS phải phù hợp**; NAT không tự tạo default route hay cho phép mọi kết nối.
- **Cloud NAT gắn với một VPC, region và Cloud Router**, không phục vụ tất cả region chỉ bằng một gateway.
- **Phạm vi primary/secondary IP ranges** rất quan trọng, nhất là khi GKE sử dụng pod alias IPs.
- **Cloud Run cần VPC egress + all-traffic** để chuyển traffic Internet qua gateway NAT có IP tĩnh theo mô hình này.
- **Private Google Access/PSC** có thể phù hợp hơn để truy cập Google APIs; **Private NAT** dành cho nhu cầu private-to-private được hỗ trợ.
- **NAT ports, logs, monitoring và chi phí** phải được quản lý như một phần của độ tin cậy và ngân sách cloud.

Khi thiết kế các bài về Compute Engine, GKE, Cloud Run và cơ sở dữ liệu, hãy hỏi: **“Nguồn IP thật của workload là gì? Đích nằm ở Internet hay mạng riêng? Route và firewall đã cho phép chưa? Có yêu cầu egress IP cố định, port capacity hoặc giới hạn chi phí nào không?”** Trả lời đúng những câu hỏi này giúp xây dựng kết nối riêng tư có kiểm soát, dễ chẩn đoán và vận hành ổn định.

## Tài liệu tham khảo chính thức

- [Cloud NAT overview — Google Cloud](https://cloud.google.com/nat/docs/overview)
- [Public NAT specifications](https://cloud.google.com/nat/docs/public-nat)
- [Private NAT overview](https://cloud.google.com/nat/docs/private-nat)
- [Set up Public NAT](https://cloud.google.com/nat/docs/set-up-manage-network-address-translation)
- [Cloud NAT and routing/firewall interactions](https://cloud.google.com/nat/docs/nat-product-interactions)
- [NAT IP addresses and source ports](https://cloud.google.com/nat/docs/ports-and-addresses)
- [Cloud NAT troubleshooting](https://cloud.google.com/nat/docs/troubleshooting)
- [Cloud NAT logs and metrics](https://cloud.google.com/nat/docs/monitoring)
- [Cloud NAT pricing](https://cloud.google.com/nat/pricing)
- [Private Google Access](https://cloud.google.com/vpc/docs/private-google-access)
- [Cloud Run static outbound IP](https://cloud.google.com/run/docs/configuring/static-outbound-ip)
- [gcloud compute routers nats create](https://cloud.google.com/sdk/gcloud/reference/compute/routers/nats/create)

