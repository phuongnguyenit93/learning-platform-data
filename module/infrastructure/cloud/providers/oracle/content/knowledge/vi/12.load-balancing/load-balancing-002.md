# Public load balancer và private load balancer

Trong chương **Cân bằng tải ứng dụng** của module **CLOUD_PROVIDERS_ORACLE**, lựa chọn public hay private load balancer xác định nơi client bắt đầu kết nối vào ứng dụng. Quyết định này liên quan trực tiếp đến VCN, subnet, định tuyến, IAM, chứng chỉ và cách kiểm chứng khả năng truy cập.

Một hệ thống trên Oracle Cloud Infrastructure có thể mở website cho khách hàng nhưng giữ Compute, lưu trữ và cơ sở dữ liệu Oracle trong mạng riêng. Hệ thống đó cũng có thể cung cấp API nội bộ cho các dịch vụ khác hoặc người dùng tại văn phòng qua kết nối riêng. Hai nhu cầu có thể dùng cùng cơ chế cân bằng tải, nhưng điểm vào mạng và phạm vi client được phép truy cập khác nhau.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt địa chỉ frontend của load balancer với địa chỉ backend.
- Chọn public hoặc private load balancer theo nhóm client thực sự cần truy cập.
- Thiết kế subnet, route và security rule cho từng chặng kết nối.
- Giải thích tại sao public load balancer không yêu cầu backend có public IP.
- Kiểm chứng khả năng truy cập từ Internet, trong VCN và qua mạng riêng.
- Kết hợp health check, giám sát, tự động hóa và kiểm soát chi phí cho kiến trúc đã chọn.

## Phạm vi: OCI Load Balancer

Bài này sử dụng dịch vụ **OCI Load Balancer**, thường gặp với flexible shape và các thành phần listener, backend set, backend server. Dịch vụ phân phối lưu lượng từ một điểm vào tới các server có thể truy cập được từ VCN. Xem [tổng quan OCI Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/balanceoverview.htm).

**Public/private** là lựa chọn về khả năng hiển thị của frontend. **Load Balancer/Network Load Balancer** là lựa chọn dịch vụ. Khi làm thực hành, cần chọn đúng Load Balancer trong Console và dùng nhóm lệnh `oci lb`. Không áp dụng mặc định hành vi địa chỉ nguồn hay cấu hình của một dịch vụ cân bằng tải khác cho bài này.

## Frontend và backend là hai chặng riêng biệt

Một request qua reverse proxy tạo ra hai chặng cần xem xét:

~~~text
Client
  -> địa chỉ frontend + cổng listener của load balancer
  -> địa chỉ backend + cổng ứng dụng
~~~

**Frontend** là điểm client kết nối tới. **Listener** nhận lưu lượng theo cổng và giao thức đã cấu hình. **Backend set** tập hợp backend, chính sách phân phối và health check. **Backend server** là đích chạy ứng dụng, chẳng hạn private IP của một Compute instance. Xem [các khái niệm Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/balanceoverview_topic-Load_Balancing_Concepts.htm).

Ví dụ, client gọi HTTPS cổng 443 tới frontend; load balancer chuyển tiếp tới `10.40.20.11:8080`. Cổng 443 không bắt buộc giống 8080. Việc client đến được 443 cũng chưa chứng minh load balancer đến được backend 8080.

Trong thiết kế này, backend không phải nhận kết nối trực tiếp từ Internet. Nó chỉ cần nhận đúng lưu lượng từ load balancer và các nguồn vận hành đã được cho phép.

## So sánh public và private load balancer

| Tiêu chí | Public load balancer | Private load balancer |
| --- | --- | --- |
| Địa chỉ frontend | Public IP | Private IP trong subnet được chọn |
| Client điển hình | Trình duyệt, ứng dụng hoặc đối tác truy cập qua Internet | Dịch vụ trong mạng riêng, client qua kết nối riêng |
| Truy cập từ Internet thông thường | Có thể, nếu route, listener và security rule cho phép | Không có frontend công khai để truy cập trực tiếp |
| Backend | Có thể dùng private IP | Có thể dùng private IP |
| DNS thường dùng | Tên công khai trỏ tới public frontend | Tên trong private DNS trỏ tới private frontend |
| Xác thực người dùng | Do thiết kế ứng dụng và các lớp bảo vệ đảm nhiệm | Vẫn cần xác thực và phân quyền phù hợp |
| TLS | Cấu hình theo listener và backend set | Cũng cấu hình theo listener và backend set |
| Ví dụ | Website khách hàng, API dành cho đối tác ngoài Internet | API giữa các dịch vụ, cổng nội bộ của doanh nghiệp |

Public load balancer có public IP làm điểm vào; private load balancer dùng private IP. Tuy nhiên, private không có nghĩa chỉ có client trong cùng một subnet mới truy cập được. Client từ VCN khác hoặc mạng doanh nghiệp có thể đến private IP qua peering hay kết nối riêng đã cấu hình. Xem [visibility và cách truy cập private frontend](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/balanceoverview_topic-Load_Balancing_Concepts.htm).

Một public frontend giới hạn nguồn bằng security rule vẫn là public load balancer. Một private frontend có DNS bị công bố ngoài Internet vẫn là private frontend; công bố tên không tạo đường mạng đến địa chỉ đó.

## Hai kiến trúc điển hình

### Ứng dụng công khai, backend riêng tư

~~~mermaid
flowchart LR
    C["Khách hàng trên Internet"] --> IGW["Internet Gateway và route phù hợp"]
    IGW --> PLB["Public Load Balancer"]
    PLB --> A["Compute A - private IP"]
    PLB --> B["Compute B - private IP"]
    A --> DB["Cơ sở dữ liệu Oracle - mạng riêng"]
    B --> DB
~~~

Trong mô hình này, public load balancer ở public subnet, còn Compute backend ở private subnet. Client chỉ biết frontend hoặc tên DNS của ứng dụng. Backend dùng kết nối riêng để làm việc với cơ sở dữ liệu và các thành phần nội bộ.

Đặt backend trong private subnet giúp giảm bề mặt truy cập trực tiếp, nhưng vẫn cần giới hạn listener, cổng backend, tài khoản ứng dụng và quyền truy cập cơ sở dữ liệu. Một đường dẫn quản trị được public listener chuyển tiếp tới vẫn có thể bị lộ dù server chạy trong private subnet.

### API nội bộ hoặc ứng dụng doanh nghiệp

~~~mermaid
flowchart LR
    S["Dịch vụ trong VCN"] --> ILB["Private Load Balancer"]
    O["Người dùng tại văn phòng"] --> VPN["VPN hoặc FastConnect"]
    VPN --> D["DRG và route hai chiều"]
    D --> ILB
    P["VCN được kết nối riêng"] --> ILB
    ILB --> A["Compute A"]
    ILB --> B["Compute B"]
~~~

Mũi tên trong sơ đồ biểu diễn luồng logic, không thay thế thiết kế gateway và route cụ thể. Ngoài đường đi tới private load balancer, phải có đường về client. CIDR không được chồng lấn theo cách làm định tuyến mơ hồ; security rule phải cho phép đúng nguồn.

Với client ở văn phòng, cần giải quyết riêng hai việc: tìm được địa chỉ bằng DNS và có kết nối tới địa chỉ đó. Private DNS có thể phục vụ giữa các VCN và mạng tại chỗ khi cấu hình resolver, forwarding và kết nối tương ứng. Xem [Private DNS trên OCI](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/privatedns.htm).

## Chọn subnet và hiểu tính sẵn sàng

Public load balancer cần public subnet. Với region có nhiều Availability Domain, có thể dùng một **regional public subnet** hoặc hai **AD-specific public subnet** ở hai AD khác nhau. Bài thực hành chọn regional subnet để cấu hình rõ ràng hơn. Private load balancer dùng một subnet để chứa các thành phần primary và standby; bài thực hành đặt nó trong regional private subnet. Xem [điều kiện mạng của Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer.htm).

Cơ chế primary/standby của dịch vụ giúp duy trì frontend khi một thành phần gặp lỗi. Trong region nhiều AD, regional subnet hỗ trợ bố trí phục vụ khả năng failover giữa AD. Nếu region chỉ có một AD, không thể coi hai thành phần trong cùng AD là phương án sống sót khi toàn AD ngừng hoạt động. Xem [các loại load balancer và phạm vi failover](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/load_balancer_types.htm).

Cần phân biệt ba lớp tính sẵn sàng:

| Lớp | Câu hỏi thiết kế |
| --- | --- |
| Frontend | Load balancer có duy trì được điểm vào khi thành phần phục vụ gặp lỗi không? |
| Ứng dụng | Có backend khỏe ở miền lỗi khác và đủ công suất để nhận thêm lưu lượng không? |
| Phụ thuộc | Cơ sở dữ liệu, lưu trữ và dịch vụ phụ trợ có tránh được điểm lỗi duy nhất không? |

Có load balancer không tự làm ứng dụng nhiều bản sao. Hai backend cùng phụ thuộc một tiến trình hoặc một dữ liệu dùng chung không sẵn sàng vẫn có thể lỗi cùng lúc.

Subnet cũng phải còn đủ địa chỉ. Trong mô hình IPv4 được tài liệu OCI mô tả, public load balancer trên một regional subnet dùng hai private IPv4; private load balancer trên một subnet dùng ba private IP, gồm địa chỉ phục vụ client và các địa chỉ cho thành phần dịch vụ. Không chỉ dự trù một IP vì client nhìn thấy một endpoint. Xem [mức sử dụng private IP của Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer.htm).

## Định tuyến: xác minh từng chặng

### Client Internet tới public frontend

Public subnet cần đường ra Internet Gateway theo thiết kế và security rule cho phép listener nhận lưu lượng mong muốn. Public IP chỉ là một phần điều kiện; listener sai cổng hoặc rule chặn vẫn làm client thất bại.

Một route thường dùng cho public subnet IPv4 là `0.0.0.0/0 -> Internet Gateway`. Không sao chép route này sang mọi subnet chỉ để sửa lỗi timeout. Nó phải phù hợp với vai trò subnet và mô hình truy cập.

### Client riêng tới private frontend

Client trong cùng VCN thường sử dụng đường định tuyến nội bộ của VCN. Với client qua kết nối giữa các mạng, kiểm tra route của cả hai phía và các thành phần trung gian, chẳng hạn DRG đối với kết nối mạng doanh nghiệp.

NAT Gateway phục vụ kết nối khởi tạo ra ngoài theo chức năng của nó, không biến private frontend thành một điểm nhận request công khai. Thêm NAT không phải cách làm private load balancer nhận kết nối từ một người dùng Internet bất kỳ.

### Load balancer tới backend

Load balancer phải truy cập được private IP và cổng backend. Với backend trong cùng VCN, không cần đưa request ra Internet rồi quay vào public IP của server.

Kiểm tra độc lập các điều kiện sau:

- Đường định tuyến tới backend và đường về.
- Egress của load balancer và ingress của backend.
- Firewall trong hệ điều hành.
- Tiến trình ứng dụng lắng nghe trên giao diện mạng thích hợp.
- Giao thức và cổng của backend set khớp ứng dụng.

Ứng dụng chỉ bind `127.0.0.1:8080` có thể trả lời kiểm tra local nhưng không nhận request đến private IP. Một health check thất bại vì lý do này không được sửa bằng cách mở mọi nguồn trên NSG.

## Security rule theo vai trò

NSG cho phép gắn rule theo nhóm tài nguyên có cùng vai trò. Một NSG có thể dùng NSG khác làm nguồn hoặc đích khi chúng ở cùng VCN. NSG được gắn vào load balancer, còn các VNIC của Compute được gắn vào NSG backend tương ứng. Xem [Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

Ví dụ cho hệ thống dùng HTTPS frontend 443 và HTTP backend 8080:

| Nơi áp dụng | Chiều | Nguồn hoặc đích | Cổng đích | Mục đích |
| --- | --- | --- | --- | --- |
| NSG public LB | Ingress | Nhóm client Internet được phục vụ | TCP 443 | Nhận request công khai |
| NSG private LB | Ingress | CIDR hoặc NSG của client nội bộ được phép | TCP 443 | Nhận request nội bộ |
| NSG public LB | Egress | NSG backend | TCP 8080 | Chuyển tiếp và health check nếu cùng cổng |
| NSG private LB | Egress | NSG backend | TCP 8080 | Chuyển tiếp và health check nếu cùng cổng |
| NSG backend | Ingress | NSG public LB | TCP 8080 | Nhận kết nối từ public LB |
| NSG backend | Ingress | NSG private LB | TCP 8080 | Nhận kết nối từ private LB |

Đây là các rule cho kết nối chính, không phải toàn bộ firewall của một hệ thống. Nếu health check dùng cổng khác, thêm đúng luồng của cổng đó. Luồng quản trị, DNS và các phụ thuộc của ứng dụng phải được xét riêng.

Với stateful rule, lưu lượng phản hồi của kết nối đã được cho phép được theo dõi theo trạng thái. Nếu chọn stateless rule, phải thiết kế cả chiều về; không dùng bảng rule stateful rồi mặc định nó đủ cho stateless.

Security list và NSG cùng tác động lên tài nguyên. Một rule cho phép rộng còn tồn tại trong security list có thể làm mất mục tiêu giới hạn mà bạn vừa đặt trong NSG. Chúng không tạo ra cơ chế “NSG hẹp sẽ phủ quyết mọi rule rộng khác”. Xem [nguyên tắc Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm). Nếu môi trường đang áp dụng thêm ZPR, luồng cũng phải đáp ứng policy ZPR liên quan.

## Listener, TLS và địa chỉ client

Một listener phải khớp cổng và giao thức client sử dụng. Mở cổng trong NSG mà không tạo listener không làm ứng dụng tự xuất hiện. Ngược lại, listener tồn tại nhưng security rule chặn vẫn không nhận được kết nối. Xem [listener của Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managinglisteners.htm).

Public/private không quyết định có mã hóa hay không. Có thể triển khai HTTPS cho cả hai. Hai lựa chọn cần thiết kế riêng là:

- TLS từ client đến listener.
- TLS hoặc kết nối không mã hóa từ load balancer tới backend.

Với HTTPS, tên client gọi phải khớp chứng chỉ và client phải tin cậy chuỗi cấp chứng chỉ. Private DNS không loại bỏ yêu cầu kiểm tra chứng chỉ. Cần quản lý việc cấp, gia hạn và thay chứng chỉ cho cả endpoint nội bộ. Xem [quản lý chứng chỉ với OCI Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingcertificates.htm).

Load Balancer hoạt động như reverse proxy. Với HTTP, các header chuyển tiếp như `X-Forwarded-For` và `X-Forwarded-Proto` giúp ứng dụng biết thông tin kết nối ban đầu. OCI nối thêm địa chỉ peer vào `X-Forwarded-For`; dữ liệu client gửi sẵn trong header không mặc nhiên đáng tin. Ứng dụng phải cấu hình rõ proxy được tin cậy thay vì dùng tùy ý địa chỉ bên trái để phân quyền. Xem [Load Balancer Headers](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/httpheaders.htm).

## IAM quản lý hạ tầng và quyền gọi ứng dụng

IAM kiểm soát ai được tạo, xem hoặc sửa tài nguyên Load Balancer qua Console/API/CLI. Nó không tự buộc mọi request HTTP tới listener phải có danh tính người dùng OCI.

| Mặt phẳng | Kiểm soát điển hình |
| --- | --- |
| Quản lý tài nguyên | IAM policy, compartment, quyền với mạng và chứng chỉ |
| Kết nối mạng | Route, NSG, security list, firewall và các policy mạng đang áp dụng |
| Truy cập ứng dụng | Đăng nhập, token, phân quyền nghiệp vụ, mTLS khi có yêu cầu |
| Vận hành | Quyền đọc metric/log, thay backend, đổi listener và triển khai cấu hình |

Một người có quyền đọc cấu hình load balancer chưa chắc có đường mạng tới private frontend. Một client gọi được listener cũng chưa chắc được tạo hoặc xóa load balancer.

Phân quyền quản trị theo compartment được giao, bổ sung quyền mạng cần thiết nếu VCN và load balancer nằm ở các compartment khác nhau. Không giải quyết mọi lỗi bằng policy quản lý toàn tenancy. Tham khảo [Details for Load Balancing](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/lbpolicyreference.htm).

## Thực hành: so sánh hai frontend trên cùng nhóm backend

Mục tiêu lab là quan sát sự khác nhau về điểm vào. Để giảm số server cần chuẩn bị, hai load balancer trong lab dùng chung hai backend trả về nội dung vô hại. Đây là lựa chọn minh họa; một dịch vụ quản trị nội bộ thực tế không được đưa vào public backend set chỉ vì lab dùng chung server.

### Chuẩn bị mạng và ứng dụng

Dùng một compartment lab đã được cấp quyền. Kiểm tra quota và ngân sách trước khi tạo hai load balancer. Sơ đồ địa chỉ dưới đây là ví dụ, cần thay nếu trùng mạng của bạn:

| Thành phần | CIDR hoặc địa chỉ minh họa | Vai trò |
| --- | --- | --- |
| VCN | `10.40.0.0/16` | Mạng lab |
| Regional public subnet | `10.40.0.0/24` | Chứa public load balancer |
| Regional private LB subnet | `10.40.10.0/24` | Chứa private load balancer |
| Regional backend subnet | `10.40.20.0/24` | Hai Compute không có public IP |
| Regional client subnet | `10.40.30.0/24` | Máy kiểm tra trong VCN |
| Backend A | `10.40.20.11:8080` | Trả nội dung nhận diện A |
| Backend B | `10.40.20.12:8080` | Trả nội dung nhận diện B |
| Client riêng | `10.40.30.10` | Gọi private frontend |

Chuẩn bị hai Compute với HTTP server đã cài và lắng nghe trên cổng 8080. Mỗi server cần hai endpoint:

~~~text
GET /health  -> HTTP 200, nội dung ok
GET /        -> HTTP 200, nội dung backend-a hoặc backend-b
~~~

Nếu đã có NGINX, có thể dùng server block minh họa sau trong cấu hình lab được nạp ở ngữ cảnh HTTP:

~~~nginx
server {
    listen 8080;
    server_name _;
    default_type text/plain;

    location = /health {
        return 200 "ok\n";
    }

    location = / {
        return 200 "backend-a\n";
    }
}
~~~

Trên server B, đổi nội dung thành `backend-b`. Kiểm tra cấu hình rồi nạp lại bằng cách quản lý NGINX của hệ điều hành đang dùng. Directive `return` trả mã và nội dung phản hồi trực tiếp; xem [tài liệu NGINX return](https://nginx.org/en/docs/http/ngx_http_rewrite_module.html#return).

Từ chính từng backend, kiểm tra:

~~~bash
curl --fail --noproxy '*' http://127.0.0.1:8080/health
curl --fail --noproxy '*' http://127.0.0.1:8080/
~~~

Các lệnh trong bài dành cho Bash. Đây là hướng dẫn để người học chạy trong môi trường lab, không phải kết quả đã được chạy sẵn.

### Thiết lập rule cho lab

Lab dùng HTTP frontend cổng 80 để tách kiểm tra mạng khỏi việc chuẩn bị chứng chỉ; chỉ gửi dữ liệu minh họa, không gửi tài khoản hay bí mật. Với triển khai ứng dụng thật, thiết kế HTTPS như phần trước.

Tạo các NSG `lab-public-lb`, `lab-private-lb` và `lab-backends`:

- Public LB ingress TCP 80 chỉ từ public IPv4 hiện tại của máy kiểm tra, dưới dạng `/32`.
- Private LB ingress TCP 80 chỉ từ `10.40.30.10/32`.
- Cả hai LB egress TCP 8080 tới NSG backend.
- Backend ingress TCP 8080 từ từng NSG LB.

Dùng stateful rule cho các luồng lab này và kiểm tra không có security list hay NSG khác cho phép rộng hơn dự định. Firewall của backend cũng phải cho phép lưu lượng từ hạ tầng LB đến cổng 8080 theo thiết kế.

Giữ đường quản trị Compute qua phương án đã được cấp, chẳng hạn Bastion hoặc mạng riêng. Không cần gán public IP cho backend để thêm nó vào backend set.

### Tạo public load balancer

Trong Console, chọn đúng region và compartment lab rồi tạo tài nguyên **Load Balancer** với cấu hình:

| Thuộc tính | Giá trị lab |
| --- | --- |
| Display name | `lab-public-lb` |
| Visibility | Public |
| Network | VCN lab |
| Subnet | Regional public subnet |
| NSG | `lab-public-lb` |
| Shape | Flexible, chọn giới hạn băng thông phù hợp quota và nhu cầu lab |
| Backend set | `web-backends` |
| Backend policy | Round Robin |
| Backends | Private IP của A và B, cổng 8080, cùng weight |
| Health check | HTTP, cổng 8080, path `/health`, expected status 200 |
| Listener | HTTP cổng 80, default backend set `web-backends` |

Public subnet cần Internet Gateway và route đã chuẩn bị. Chờ các work request hoàn tất và backend đạt trạng thái khỏe trước khi thử từ Internet.

### Tạo private load balancer

Tạo một Load Balancer khác với:

| Thuộc tính | Giá trị lab |
| --- | --- |
| Display name | `lab-private-lb` |
| Visibility | Private |
| Network | VCN lab |
| Subnet | Regional private LB subnet |
| NSG | `lab-private-lb` |
| Backend set | `web-backends`, tạo riêng trong LB này |
| Backends và health check | Giống hợp đồng ứng dụng của public LB |
| Listener | HTTP cổng 80 |

Backend set cùng tên trong hai LB là hai cấu hình riêng. Sửa health check ở một LB không đồng nghĩa LB còn lại được sửa theo.

Ghi lại OCID và địa chỉ frontend thực tế của cả hai LB. Đừng lấy địa chỉ nội bộ của một thành phần dịch vụ làm endpoint client. Các bước visibility, subnet, listener và backend của Console được mô tả trong [hướng dẫn tạo Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer_topic-Creating_Load_Balancers.htm).

### Đọc cấu hình và health bằng CLI

Trên máy quản trị đã cấu hình OCI CLI, thay các giá trị dưới đây bằng OCID thật:

~~~bash
REGION="ap-singapore-1"
PUBLIC_LB_ID="REPLACE_WITH_PUBLIC_LB_OCID"
PRIVATE_LB_ID="REPLACE_WITH_PRIVATE_LB_OCID"

oci lb load-balancer get \
  --region "$REGION" --load-balancer-id "$PUBLIC_LB_ID"

oci lb load-balancer get \
  --region "$REGION" --load-balancer-id "$PRIVATE_LB_ID"

oci lb backend-set-health get \
  --region "$REGION" --load-balancer-id "$PUBLIC_LB_ID" \
  --backend-set-name web-backends

oci lb backend-set-health get \
  --region "$REGION" --load-balancer-id "$PRIVATE_LB_ID" \
  --backend-set-name web-backends
~~~

Lệnh `load-balancer get` đọc cấu hình tài nguyên; nó không mở một kết nối HTTP từ máy của bạn tới frontend. Xem [CLI lấy cấu hình Load Balancer](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/load-balancer/get.html). Lệnh `backend-set-health get` đọc trạng thái backend set; xem [CLI lấy health của backend set](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set-health/get.html).

### Kiểm tra từ hai vị trí mạng

Trên máy Internet có địa chỉ đã được cho phép, thay public IP rồi chạy:

~~~bash
PUBLIC_LB_IP="REPLACE_WITH_ASSIGNED_PUBLIC_IPV4"

curl --fail --show-error --noproxy '*' \
  --connect-timeout 3 --max-time 10 \
  "http://$PUBLIC_LB_IP/"
~~~

Trên máy `10.40.30.10` trong VCN, dùng private frontend được cấp:

~~~bash
PRIVATE_LB_IP="REPLACE_WITH_ASSIGNED_PRIVATE_IPV4"

curl --fail --show-error --noproxy '*' \
  --connect-timeout 3 --max-time 10 \
  "http://$PRIVATE_LB_IP/"
~~~

Có thể lặp lại nhiều request để quan sát cả hai backend:

~~~bash
for attempt in 1 2 3 4 5 6; do
  curl --fail --silent --show-error --noproxy '*' \
    --connect-timeout 3 --max-time 10 \
    "http://$PRIVATE_LB_IP/"
done
~~~

Đánh giá trên nhiều request và trạng thái backend, không yêu cầu một mẫu luân phiên tuyệt đối ở mọi lần gọi. Các thiết lập kết nối, persistence hoặc thay đổi health có thể ảnh hưởng quan sát.

Ma trận nghiệm thu cho cấu hình lab:

| Nguồn kiểm tra | Đích | Kết quả dự kiến |
| --- | --- | --- |
| Máy Internet được cho phép | Public LB, TCP 80 | Nhận HTTP 200 từ backend |
| Client riêng `10.40.30.10` | Private LB, TCP 80 | Nhận HTTP 200 từ backend |
| Máy Internet không có VPN, proxy hoặc đường riêng tới VCN | Private frontend | Không gọi được endpoint lab qua Internet |
| Client riêng chưa được cấp quyền gọi backend trực tiếp | Backend, TCP 8080 | Bị giới hạn bởi rule đã thiết kế |
| Health checker của LB | Backend, TCP 8080, `/health` | Nhận HTTP 200 |

Các kết quả là dự kiến để kiểm tra, không phải bằng chứng đo sẵn. Bài test âm cần chạy từ đúng nguồn và tới đúng endpoint; một lỗi DNS hoặc sai IP không chứng minh security rule hoạt động đúng.

### Quan sát khi một backend lỗi

Trên backend A của lab, tạm dừng dịch vụ HTTP bằng cơ chế quản lý dịch vụ đang dùng. Không dừng backend B.

Theo dõi health của cả hai LB. Sau khi health check phát hiện A lỗi và cập nhật trạng thái, request mới được phục vụ bởi backend còn khỏe. Có thể có request lỗi trong thời gian phát hiện; không suy ra zero downtime tuyệt đối từ một bài thử ngắn.

Khởi động lại dịch vụ trên A, chờ health phục hồi rồi gọi lại hai frontend. Health check liên tục đánh giá backend theo chính sách; một backend khỏe lại có thể được đưa vào vòng phân phối. Xem [Health Check Policies](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/load_balancer_health_management.htm).

Health của backend trả lời câu hỏi “LB có gọi được endpoint kiểm tra không”. Nó không đo toàn bộ đường đi từ client Internet, không kiểm tra đầy đủ DNS và không thay thế test chức năng ứng dụng.

## DNS và HTTPS sau khi mạng đã thông

Sau khi lab IP hoạt động, mới thêm DNS để tách lỗi theo lớp:

- Tên public của ứng dụng trỏ đến public frontend.
- Tên trong private zone trỏ đến private frontend.
- Client riêng phải dùng resolver có thể phân giải zone đó.
- Client tại văn phòng cần cấu hình chuyển tiếp DNS và kết nối đến resolver phù hợp.

Tên như `api.internal.example.com` chỉ là ví dụ. Hậu tố “internal” trong tên không tự làm endpoint trở thành riêng tư.

Với HTTPS, kiểm tra theo hostname thật để có đúng Host và TLS SNI. Khi cần tạm bỏ qua DNS để khoanh vùng mà vẫn giữ hostname cho TLS, có thể dùng:

~~~bash
curl --fail --show-error \
  --resolve "app.example.com:443:$PUBLIC_LB_IP" \
  "https://app.example.com/health"
~~~

Chỉ dùng khi đã triển khai listener HTTPS và chứng chỉ phù hợp cho hostname được thay trong ví dụ. Không dùng tùy chọn bỏ xác minh chứng chỉ làm tiêu chí nghiệm thu thành công.

## Giám sát, tự động hóa và chi phí

Một public frontend cần kiểm tra từ vị trí phản ánh người dùng bên ngoài. Một private frontend cần điểm kiểm tra có kết nối riêng đúng phạm vi. Đặt monitor ngoài Internet rồi kết luận private LB bị lỗi vì không truy cập được sẽ tạo cảnh báo sai.

Kết hợp số backend không khỏe, lưu lượng, lỗi HTTP, độ trễ và mức sử dụng băng thông. OCI phát metric Load Balancer trong namespace `oci_lbaas`; chọn đúng resource, listener hoặc backend set khi đọc metric. Xem [Load Balancer Metrics](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/loadbalancermetrics.htm).

Khi tự động hóa hạ tầng, lưu cùng một thiết kế có thể tái tạo được: compartment, visibility, subnet, NSG, listener, backend set, health check, chứng chỉ và DNS. Trước khi áp dụng thay đổi, kiểm tra kế hoạch có làm mở listener nội bộ ra Internet, thay endpoint hoặc ngắt các kết nối đang dùng hay không. Không đưa private key chứng chỉ vào tài liệu hoặc log triển khai.

Flexible shape có mức băng thông tối thiểu và tối đa; chọn theo tải, yêu cầu sẵn sàng, quota và ngân sách. Hai LB phục vụ hai ranh giới truy cập có thể hợp lý, nhưng không cần tạo thêm LB chỉ vì có nhiều đường dẫn nếu một cấu hình listener/routing phù hợp đã đáp ứng yêu cầu. Xem [cấu hình băng thông khi tạo Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer_topic-Creating_Load_Balancers.htm).

Không mặc định private LB miễn phí hoặc public LB luôn đắt hơn chỉ vì visibility. Ước lượng toàn kiến trúc, gồm LB, backend Compute, kết nối mạng, log và các tài nguyên liên quan. Sau lab, xóa các LB và tài nguyên riêng đã tạo khi không còn dùng; kiểm tra tài nguyên chia sẻ trước khi xóa NSG, route, subnet hoặc gateway.

## Khoanh vùng sự cố theo biểu hiện

| Biểu hiện | Lớp cần kiểm tra trước | Hướng kiểm tra |
| --- | --- | --- |
| Public frontend timeout | Đường client tới listener | Public IP, route Internet Gateway, nguồn được phép, cổng listener |
| Private frontend chỉ gọi được từ một VCN | Kết nối giữa các mạng | Route hai chiều, peering hoặc DRG, CIDR và security rule |
| Gọi IP được nhưng hostname lỗi | DNS hoặc TLS | Resolver, bản ghi, Host/SNI, chứng chỉ và chuỗi tin cậy |
| Backend unhealthy | Chặng LB tới backend | Cổng, giao thức, path, status code, NSG, firewall, bind address |
| Backend khỏe nhưng client không gọi được | Chặng frontend hoặc cấu hình listener | Listener, rule nhận vào, route và thử từ đúng nguồn |
| Nhận HTTP 502 hoặc 504 | Kết nối và phản hồi upstream | Backend health, thời gian phản hồi, TLS backend và log liên quan |
| Ứng dụng thấy địa chỉ proxy | Reverse proxy và log ứng dụng | Header chuyển tiếp và cấu hình trusted proxy |
| Người dùng không đăng nhập OCI vẫn gọi được public website | Quyền ứng dụng | Kiểm tra cơ chế xác thực ứng dụng và phạm vi listener |
| Một backend lỗi làm toàn bộ dịch vụ ngừng | Tính sẵn sàng ứng dụng | Công suất backend còn lại, session và phụ thuộc chung |

Không gán duy nhất một nguyên nhân cho mọi mã lỗi. Tài liệu [troubleshooting health của Oracle](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/troubleshooting_health.htm) hướng dẫn đối chiếu health check, timeout, ứng dụng và phụ thuộc khi khoanh vùng.

## Cách đưa ra quyết định kiến trúc

Chọn public load balancer khi nhóm client cần một endpoint có thể truy cập qua Internet và đã xác định các kiểm soát cần áp dụng ở điểm vào. Giữ backend và cơ sở dữ liệu trong mạng riêng khi không có nhu cầu công khai chúng.

Chọn private load balancer khi client có đường mạng riêng tới dịch vụ và yêu cầu truy cập không cần public frontend. Cùng với LB, thiết kế route, DNS, chứng chỉ và phân quyền ứng dụng cho các client đó.

Dùng cả hai khi có hai ranh giới truy cập rõ ràng, chẳng hạn website cho khách hàng và API nội bộ. Tách listener, backend set hoặc backend thực tế theo phạm vi dữ liệu; không vô tình cho public LB định tuyến tới chức năng chỉ dành cho nội bộ.

Bằng chứng hoàn tất thiết kế gồm khả năng truy cập từ đúng client, chặn được nguồn không được phép, backend health phù hợp, phản hồi ứng dụng đúng, và khả năng tiếp tục phục vụ khi một backend gặp lỗi. Visibility là điểm bắt đầu của thiết kế; kết quả phải được chứng minh trên toàn bộ luồng kết nối.