# Firewall, private endpoint và truy cập Storage an toàn

Azure Storage có thể chứa ảnh sản phẩm, hóa đơn, tệp sao lưu, dữ liệu giao dịch và những tài liệu quan trọng khác của ứng dụng. Một Storage Account hoạt động tốt về hiệu năng chưa chắc đã được bảo vệ tốt: dịch vụ có thể đang tiếp nhận kết nối từ mạng công cộng, một khóa tài khoản có thể bị chia sẻ quá rộng, hoặc hệ thống nội bộ vẫn đang truy cập sai endpoint sau khi triển khai mạng riêng.

Để bảo vệ dữ liệu trên Azure, cần kết hợp **kiểm soát đường mạng** (Storage firewall, virtual network rules, private endpoint và DNS), **xác thực và phân quyền** (Microsoft Entra ID, Azure RBAC, SAS khi thực sự cần) cùng **giám sát và quản trị cấu hình**. Không có một công tắc đơn lẻ nào thay thế được toàn bộ những lớp này.

Bài học thuộc chương **Nền tảng Azure Storage**, trong lộ trình tìm hiểu Microsoft Azure từ subscription và resource group tới mạng ảo, tính toán, lưu trữ, dữ liệu, bảo mật, giám sát và kiểm soát chi phí của một ứng dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao cần tách biệt quyền truy cập mạng với quyền đọc/ghi dữ liệu trong Azure Storage.
2. Phân biệt public endpoint, Storage firewall, virtual network service endpoint và private endpoint.
3. Thiết kế đường truy cập Storage qua private IP, Private DNS Zone và mạng doanh nghiệp kết nối với Azure.
4. Nhận biết các phương án xác thực bằng Microsoft Entra ID, RBAC, managed identity, SAS và account key.
5. Thực hiện quy trình cấu hình Storage firewall, private endpoint và DNS an toàn trên Azure portal.
6. Kiểm tra trạng thái cấu hình bằng Azure CLI và xác minh truy cập bằng công cụ mạng.
7. Xử lý các lỗi thường gặp như DNS trả IP công cộng, kết nối timeout hoặc nhận phản hồi 403.

## 1. Hai lớp kiểm soát: mạng và danh tính

Khi một ứng dụng muốn đọc blob trong Storage Account, cần ít nhất hai nhóm điều kiện:

- **Đường mạng hợp lệ:** request có tới đúng endpoint hay không; Storage firewall cho phép đường vào công cộng hay không; private endpoint và DNS có hoạt động không; NSG, route table, firewall trung gian có cho phép kết nối không.
- **Quyền trên dữ liệu:** danh tính hoặc thông tin xác thực được cung cấp có quyền thực hiện thao tác đó không, ví dụ đọc blob hay ghi một tệp mới.

Một người dùng có quyền **Storage Blob Data Reader** vẫn có thể bị chặn nếu họ gửi request từ mạng công cộng không được cho phép. Ngược lại, một máy nằm trong subnet được phép không tự có quyền tải xuống toàn bộ dữ liệu nếu không có thông tin xác thực hoặc quyền dữ liệu phù hợp.

~~~text
Client / ứng dụng
    |
    | 1. DNS chọn endpoint
    v
Đường mạng: public endpoint hoặc private endpoint
    |
    | 2. Network controls (firewall / route / NSG nếu áp dụng)
    v
Azure Storage data plane
    |
    | 3. Authentication + authorization
    v
Blob / File / Queue / Table / dữ liệu ứng dụng
~~~

**Control plane** dùng để quản lý tài nguyên qua Azure Resource Manager (ARM), chẳng hạn tạo Storage Account hoặc sửa cấu hình mạng. **Data plane** dùng để đọc, ghi, xóa dữ liệu trong dịch vụ Storage. Quyền quản lý tài nguyên và quyền truy cập dữ liệu là hai lớp khác nhau. Việc vẫn xem được Storage Account trên Azure portal không chứng minh máy hiện tại có thể đọc dữ liệu qua data plane.

## 2. Public endpoint và Storage firewall

Một Storage Account thường có các endpoint của từng dịch vụ, ví dụ:

~~~text
https://stordersprod.blob.core.windows.net
https://stordersprod.queue.core.windows.net
https://stordersprod.table.core.windows.net
https://stordersprod.file.core.windows.net
~~~

Tên **stordersprod** chỉ là ví dụ; không phải tài khoản thực. Các dịch vụ hoặc cấu hình khác, như Data Lake Storage Gen2, có thể thêm endpoint **dfs**. Những tên trên là tên dịch vụ tiêu chuẩn; chúng không có nghĩa dữ liệu đang được phép truy cập ẩn danh.

**Storage firewall** kiểm soát những request đi tới **public endpoint** của Storage Account. Các lựa chọn cấu hình mạng hiện hành thường thể hiện qua những trạng thái logic sau:

| Cấu hình | Tác dụng đối với public endpoint | Lưu ý |
|---|---|---|
| Cho phép public network access từ mọi mạng | Endpoint công cộng có thể được tiếp cận từ nhiều nguồn mạng | Vẫn cần xác thực/quyền dữ liệu, nhưng bề mặt mạng rộng |
| Cho phép public network access từ **selected networks** | Chỉ những nguồn phù hợp quy tắc IP, VNet hoặc ngoại lệ được cho phép mới đi qua firewall | Cần default deny, rà soát rules và bypass |
| **Disable public network access** | Chặn truy cập data plane qua public endpoint theo cơ chế hỗ trợ của Storage | Truy cập qua private endpoint đã cấu hình và được chấp thuận vẫn có thể hoạt động |

Trong Azure CLI, hai thuộc tính thường được kiểm tra là **publicNetworkAccess** và **networkRuleSet.defaultAction**. Chúng không phải cùng một thuộc tính: trạng thái truy cập mạng công cộng quyết định public endpoint có được sử dụng không, còn default action/rules quy định nguồn nào được phép khi public network access được bật.

### IP network rules

Có thể cho phép những **địa chỉ IPv4 công cộng** hoặc dải nguồn phù hợp đi tới public endpoint. Ví dụ, máy chủ trong văn phòng sử dụng NAT ra Internet bằng một IP công cộng ổn định; doanh nghiệp có thể cho phép địa chỉ egress đó khi thật sự cần truy cập Storage qua public endpoint.

Không nên điền các địa chỉ riêng RFC 1918 như **10.20.0.0/16** vào danh sách IP public firewall rồi mong Storage nhận biết đó là nguồn trên Internet. Nếu mạng văn phòng đi qua NAT, Storage nhìn thấy địa chỉ IP công cộng sau NAT. Hơn nữa, IP-based firewall rules có những giới hạn về loại địa chỉ, dải prefix và nguồn trong cùng region; phải kiểm tra điều kiện hỗ trợ trước khi lựa chọn.

### Virtual network rules và service endpoint

Azure Storage hỗ trợ **virtual network rules** để chỉ cho phép request qua những subnet Azure nhất định khi sử dụng cơ chế **service endpoint** phù hợp. Với mô hình này:

1. Subnet bật service endpoint cho dịch vụ Storage theo khả năng hỗ trợ.
2. Storage Account cho phép subnet đó trong cấu hình mạng.
3. Lưu lượng vẫn hướng tới **public service endpoint** của Storage, nhưng nguồn được Azure nhận diện theo VNet/subnet thay vì chỉ dựa vào địa chỉ IP công cộng.

**Service endpoint không cấp private IP cho Storage Account.** Đây là điểm khác với Private Endpoint. Cần bảo đảm cả cấu hình subnet lẫn firewall rule được thiết lập đúng; chỉ bật service endpoint trên subnet chưa tự cấp quyền truy cập.

### Trusted services và resource instances

Một số Storage Account có tùy chọn cho phép những **trusted Microsoft services** được liệt kê trong tài liệu vượt qua giới hạn mạng công cộng trong điều kiện được hỗ trợ. Đây **không phải** ngoại lệ dành cho mọi dịch vụ Azure, mọi VM của Microsoft hay mọi subscription. Các request vẫn phải đáp ứng điều kiện xác thực và quyền cần thiết.

Hãy ghi lại rõ ràng lý do bật bypass, phạm vi tác động và chủ sở hữu. Một số kịch bản còn có resource instance rules hoặc cơ chế ngoại lệ đặc thù theo dịch vụ. Tránh mở rộng bypass chỉ để giải quyết nhanh một lỗi truy cập chưa được chẩn đoán.

## 3. Private Endpoint và Azure Private Link

**Private Endpoint** là một network interface với **private IP** được tạo trong subnet của VNet và kết nối tới một dịch vụ được hỗ trợ qua **Azure Private Link**. Với Azure Storage, endpoint này giúp ứng dụng truy cập data plane thông qua địa chỉ riêng thay vì phải đi tới public endpoint.

Ví dụ:

~~~text
VM API: 10.50.2.10
  |
  | TLS tới stordersprod.blob.core.windows.net
  v
Private DNS: stordersprod.blob.core.windows.net
             -> 10.50.3.4
  |
  v
Private Endpoint (blob): 10.50.3.4
  |
  v
Azure Private Link
  |
  v
Storage Account: stordersprod
~~~

Trong ví dụ này, ứng dụng vẫn dùng hostname của dịch vụ Storage thông thường. DNS trong phạm vi được cấu hình phân giải nó về IP riêng của Private Endpoint. Nhờ vậy, không cần sửa mã ứng dụng để dùng một địa chỉ IP cố định.

### Những điểm quan trọng

- Private Endpoint được tạo **trong subnet**, vì vậy cần quy hoạch đủ địa chỉ IP còn trống.
- Endpoint có **private endpoint connection** với Storage Account; trạng thái như **Approved**, **Pending** hoặc **Rejected** ảnh hưởng khả năng sử dụng.
- Một private endpoint gắn tới **subresource** cụ thể của Storage, ví dụ **blob**, **file**, **queue**, **table** hoặc **dfs** tùy tài khoản và mục đích.
- Nếu ứng dụng sử dụng đồng thời Blob và ADLS Gen2 DFS API, có thể cần private endpoint và DNS cho **cả blob và dfs** theo yêu cầu luồng ứng dụng.
- Private Endpoint không tự cấp quyền truy cập dữ liệu; ứng dụng vẫn cần Microsoft Entra ID/RBAC, SAS hoặc phương thức xác thực hợp lệ.
- Có thể **vô hiệu hóa public network access** của Storage sau khi xác minh tất cả đường truy cập hợp lệ đều đã dùng private endpoint hoặc phương án được hỗ trợ khác.

### Private endpoint không phải VNet service endpoint

| Tiêu chí | Service endpoint + VNet rule | Private endpoint |
|---|---|---|
| Địa chỉ Storage mà client kết nối | Public endpoint của dịch vụ | Private IP của endpoint trong VNet |
| Cơ chế kiểm soát chính | Nhận diện subnet được phép truy cập public endpoint | Private Link connection, private IP, DNS và network path |
| DNS | Thường không cần đổi sang tên riêng | Cần phân giải hostname về private IP trong môi trường truy cập |
| Truy cập từ on-premises | Phụ thuộc thiết kế mạng và khả năng hỗ trợ từng mô hình; không tự là kết nối riêng từ on-prem | Có thể qua VPN/ExpressRoute, với route và DNS tới private IP đúng |
| Khả năng tắt public network access | Không tiếp tục dùng public endpoint khi bị tắt | Vẫn dùng private endpoint nếu connection, DNS và xác thực hợp lệ |
| Cấu hình bổ sung | Service endpoint trên subnet, VNet rule trên Storage | Private endpoint, phê duyệt kết nối và Private DNS |

Không có lựa chọn luôn tối ưu cho mọi hệ thống. Service endpoint có thể phù hợp khi ứng dụng Azure đang sử dụng public endpoint nhưng cần giới hạn subnet. Private Endpoint thường thích hợp hơn khi muốn đường truy cập riêng và có thể đóng hoàn toàn public network access.

## 4. Private DNS Zone: điều kiện để đi đúng đường

Tạo Private Endpoint mà **không thiết kế DNS** là một lỗi thường gặp. Ứng dụng có thể tiếp tục phân giải tên Storage thành địa chỉ công cộng, dẫn tới truy cập sai đường hoặc bị firewall chặn dù endpoint riêng đã được tạo thành công.

Với Blob Storage, vùng DNS riêng thường dùng là:

~~~text
privatelink.blob.core.windows.net
~~~

Trong VNet được liên kết với Private DNS Zone và được cấu hình bản ghi phù hợp, luồng phân giải có thể như sau:

~~~text
Ứng dụng gọi:
stordersprod.blob.core.windows.net
          |
          v
Phân giải thông qua tên Private Link liên quan:
stordersprod.privatelink.blob.core.windows.net
          |
          v
Private DNS A record
          |
          v
10.50.3.4  (Private Endpoint IP)
~~~

**Ứng dụng vẫn gọi hostname Storage gốc**, ví dụ **stordersprod.blob.core.windows.net**. Không nên mã hóa cứng IP của Private Endpoint vào connection string hay trong mã nguồn.

### DNS zone cho từng Storage subresource

| Subresource | Private DNS Zone thường dùng |
|---|---|
| blob | privatelink.blob.core.windows.net |
| dfs | privatelink.dfs.core.windows.net |
| file | privatelink.file.core.windows.net |
| queue | privatelink.queue.core.windows.net |
| table | privatelink.table.core.windows.net |

Chỉ tạo những endpoint và zone mà ứng dụng thực sự cần. **Azure Data Lake Storage Gen2** có thể dùng cả DFS và Blob API trong các hoạt động như chuyển hướng hoặc tương tác với dữ liệu; cần kiểm tra kịch bản và tạo cả hai endpoint khi yêu cầu.

### VNet link và DNS zone group

Private DNS Zone cần được liên kết tới VNet có client hoặc hạ tầng DNS phù hợp. **Private DNS zone group** gắn với private endpoint giúp quản lý các bản ghi DNS liên quan khi được cấu hình. Nếu không có bản ghi đúng, client có thể vẫn nhận IP public hoặc không phân giải được tên.

Khi nhiều VNet hoặc nhiều private endpoint cùng sử dụng Storage Account, cần thiết kế zone, link và bản ghi cẩn thận để tránh xung đột hoặc phân giải sai. Không dùng cùng một bản ghi thủ công cho mọi endpoint nếu các mạng cần đường truy cập khác nhau.

### Truy cập từ mạng tại chỗ qua VPN hoặc ExpressRoute

Với máy chủ on-premises, việc có VPN/ExpressRoute tới VNet chưa đủ. DNS tại chỗ cần chuyển tiếp truy vấn liên quan tới Private Link qua hạ tầng DNS/forwarder có thể truy vấn Private DNS Zone trong Azure. Có thể dùng **Azure DNS Private Resolver** hoặc DNS forwarder do tổ chức quản lý theo kiến trúc được hỗ trợ.

Luồng cần đạt:

1. Máy on-premises phân giải tên Storage ra **private IP** đúng.
2. Router và firewall tại chỗ có route tới subnet chứa private endpoint.
3. VNet/NSG/route/firewall trung gian cho phép lưu lượng theo điều kiện hỗ trợ.
4. Private endpoint connection ở trạng thái chấp thuận.
5. Request có quyền truy cập dữ liệu hợp lệ.

**Đừng chỉ kiểm tra DNS từ một VM Azure.** Hãy chạy truy vấn DNS từ chính môi trường sử dụng Storage, gồm máy chủ on-premises, App Service, container hoặc tác vụ batch.

## 5. Public network access và private endpoint hoạt động cùng nhau

Một mô hình production phổ biến:

~~~text
                         Internet
                             |
                             X  Public network access: Disabled
                             |
                     Storage public endpoint

Workload Azure / on-premises kết nối riêng
            |
            v
      VNet + private DNS
            |
            v
   Storage private endpoint (10.50.3.4)
            |
            v
      Azure Storage data plane
            |
            v
       Entra ID + Azure RBAC
~~~

Trong mô hình này, việc tắt public network access nhằm loại bỏ đường truy cập data plane qua public endpoint; kết nối đến private endpoint vẫn phải đáp ứng các điều kiện mạng, DNS và danh tính. **Storage firewall không phải cơ chế thay thế NSG, route table hoặc Azure Firewall trên phía VNet**.

Khi tổ chức áp dụng NSG hoặc UDR tới subnet chứa private endpoint, hãy kiểm tra chế độ **private endpoint network policies** được hỗ trợ và đang bật hay tắt. Không nên giả định mọi NSG/UDR áp dụng cho private endpoint theo cách giống hệt NIC của VM trong mọi cấu hình.

### Vì sao vẫn có thể thấy tên miền công cộng?

Ứng dụng dùng hostname **stordersprod.blob.core.windows.net** không có nghĩa request nhất thiết đi qua Internet. Điều quyết định đường thực tế là kết quả DNS, địa chỉ IP đích và route. Trong cấu hình đúng, hostname thông thường được phân giải qua Private Link thành một private IP.

Ngược lại, nếu client dùng hostname đúng nhưng nhận địa chỉ công cộng trong môi trường chỉ cho phép private endpoint, request có thể bị chặn. Cần sửa DNS/route trước khi nghĩ tới việc mở lại Storage public access.

## 6. Xác thực và phân quyền dữ liệu Storage

**Giới hạn mạng chỉ là một lớp bảo vệ.** Cần lựa chọn cách ứng dụng chứng minh danh tính và được cấp quyền đối với dữ liệu.

### Microsoft Entra ID và Azure RBAC

Với Blob Storage, một phương án được ưu tiên là dùng **Microsoft Entra ID** và Azure RBAC data-plane roles:

- **Storage Blob Data Reader:** đọc blob phù hợp với phạm vi được cấp.
- **Storage Blob Data Contributor:** đọc/ghi và thao tác dữ liệu Blob theo quyền của vai trò.
- Các vai trò hoặc mô hình truy cập khác có thể cần cho Queue, Table, Files và từng workload cụ thể.

Ví dụ một API chạy trên Azure App Service có thể sử dụng **managed identity** được cấp vai trò Storage Blob Data Contributor ở phạm vi container hoặc Storage Account theo yêu cầu. Ứng dụng dùng SDK Azure để yêu cầu token thay vì lưu một account key trong cấu hình.

**Azure Contributor hoặc Owner ở management plane không tự động đồng nghĩa được cấp mọi quyền Blob data plane qua Microsoft Entra ID.** Một số quyền quản lý có thể tạo tác động gián tiếp lên dữ liệu hoặc khóa tùy cấu hình, nên phải đánh giá role cụ thể và áp dụng nguyên tắc quyền tối thiểu.

### Shared Access Signature (SAS)

**SAS** cấp quyền có điều kiện trong thời gian giới hạn tới tài nguyên Storage theo loại SAS và cách ký. Dùng SAS khi cần cấp quyền tạm thời cho một tác vụ hoặc đối tác, nhưng phải giới hạn:

- Dịch vụ, container hoặc đối tượng được phép truy cập.
- Hành động cần thiết, ví dụ chỉ đọc hoặc chỉ ghi.
- Thời gian hiệu lực và thời điểm hết hạn.
- Các điều kiện bổ sung được loại SAS hỗ trợ, chẳng hạn giới hạn IP hoặc HTTPS.

Với Blob Storage, nên ưu tiên **user delegation SAS** được ủy quyền qua Microsoft Entra ID khi kịch bản hỗ trợ, thay vì tạo SAS ký bằng account key. Bảo vệ SAS như một thông tin xác thực nhạy cảm: ai có chuỗi SAS hợp lệ có thể sử dụng quyền mà chuỗi đó cấp.

### Account key và Shared Key authorization

Storage Account có thể hỗ trợ **account keys**, một loại bí mật có quyền rộng đối với dữ liệu khi dùng Shared Key. Chia sẻ account key cho nhiều ứng dụng khiến việc thu hồi/luân chuyển và kiểm soát quyền trở nên khó khăn.

Với những workload hỗ trợ Microsoft Entra ID, cân nhắc không dùng Shared Key và thiết lập chính sách hạn chế phù hợp. **Không tắt Shared Key một cách vội vàng** nếu các ứng dụng, Azure Files hoặc công cụ cũ đang phụ thuộc vào nó; cần kiểm kê tương thích và chuyển đổi từng bước.

### Truy cập ẩn danh Blob là cấu hình riêng

**Allow Blob anonymous access** ở cấp Storage Account và mức truy cập của container là các kiểm soát khác với public network access. Một endpoint có thể tiếp cận được từ Internet nhưng vẫn từ chối đọc dữ liệu ẩn danh vì yêu cầu xác thực. Ngược lại, khi quyền đọc ẩn danh được cho phép trong phạm vi hỗ trợ, cần đánh giá nguy cơ lộ dữ liệu.

Đừng dùng trạng thái network firewall để suy đoán quyền đọc/ghi blob, và đừng dùng quyền data plane để suy đoán endpoint có đang công khai hay không.

## 7. Kiến trúc mẫu: ứng dụng bán hàng truy cập Storage qua Private Endpoint

Giả sử doanh nghiệp có:

- Subscription **sub-sales-prod**, resource group **rg-sales-prod**.
- API chạy trên VM hoặc dịch vụ tính toán có đường truy cập vào VNet.
- Storage Account **stordersprod** chứa hóa đơn và ảnh sản phẩm.
- VNet **vnet-sales (10.50.0.0/16)**, subnet API **10.50.2.0/24** và subnet private endpoint **10.50.3.0/27**.
- Máy chủ kế toán tại chỗ kết nối tới mạng Azure qua VPN hoặc ExpressRoute.

Mục tiêu bảo mật:

1. API và máy chủ kế toán truy cập Blob qua private IP.
2. Public network access tới Storage Account được tắt sau khi nghiệm thu.
3. API dùng managed identity và role data plane tối thiểu; máy chủ kế toán có danh tính/quyền tương ứng.
4. DNS ở Azure và on-premises trả về địa chỉ private endpoint đúng.
5. Có log truy cập dữ liệu, giám sát và phương án phục hồi nếu DNS hoặc tuyến mạng gặp sự cố.

~~~text
                  Người dùng Internet
                           |
                  Frontend/API HTTPS
                           |
                    API workload
                (managed identity)
                           |
                           | Blob HTTPS
                           v
             VNet / Private DNS Zone
                           |
               PE blob: 10.50.3.4
                           |
                           v
                  Storage Blob data
               (network + RBAC)

Máy chủ kế toán tại chỗ
        |
       VPN / ExpressRoute
        |
       DNS forwarder / resolver
        |
        +--------> PE blob: 10.50.3.4
~~~

Đường đi của người dùng Internet tới frontend khác với đường API tới Storage. API có thể là dịch vụ công khai, nhưng Storage Account vẫn không cần mở public data endpoint cho người dùng.

### Phân công trách nhiệm

| Nhóm | Việc cần làm |
|---|---|
| Nhóm mạng | VNet/subnet, route, private endpoint, DNS, firewall và kết nối on-premises |
| Nhóm ứng dụng | SDK, managed identity, quyền blob cần thiết, xử lý lỗi và kiểm thử |
| Nhóm bảo mật | Chính sách public access, RBAC, SAS/keys, giám sát và ngoại lệ |
| Nhóm vận hành | IaC, backup, alert, chi phí và thay đổi cấu hình có phê duyệt |

## 8. Quy trình cấu hình an toàn trên Azure portal

Ví dụ dưới đây mô tả quy trình tạo môi trường thực hành **trong subscription được phép sử dụng**. Cần xác nhận trước các khoản phí có thể phát sinh từ Private Endpoint, Private DNS, kết nối mạng và mức dùng Storage. Không thay đổi Storage Account production nếu chưa có kế hoạch chuyển đổi và phê duyệt.

### Bước 1: kiểm tra cấu hình hiện tại

Trong **Azure portal**, mở Storage Account, xác nhận subscription, resource group và region. Kiểm tra:

- Storage service nào thực sự được dùng: blob, dfs, file, queue hoặc table.
- Phần **Networking**: public network access, firewall/VNet/IP rules, trusted services bypass.
- Phần **Private endpoint connections**: đã có endpoint nào, trạng thái connection.
- Phần **Access control (IAM)** và **Configuration**: phương thức xác thực, anonymous access, Shared Key access khi có.
- Diagnostic settings, Azure Monitor và các client hiện đang truy cập.

Ghi lại **baseline**: ai đang truy cập, từ đâu, dùng DNS nào và thao tác read/write nào quan trọng. Nếu chưa xác định được tất cả client, chưa nên chặn public endpoint.

### Bước 2: chuẩn bị VNet/subnet

Chọn VNet có thể kết nối tới workload. Tạo hoặc dùng subnet đủ IP để đặt private endpoint, chẳng hạn **snet-private-endpoints (10.50.3.0/27)**. Xác nhận CIDR không chồng lấn, route hợp lệ, và cấu hình subnet/NSG/Private Endpoint network policies theo thiết kế.

Private Endpoint dành cho Storage **không phải** subnet delegation cho một dịch vụ ứng dụng. Hãy kiểm tra subnet có đáp ứng điều kiện triển khai endpoint và không sử dụng chung với cấu hình xung đột.

### Bước 3: tạo Private Endpoint cho đúng subresource

Tại Storage Account, mở phần **Networking** hoặc **Private endpoint connections** rồi tạo Private Endpoint. Chọn:

1. Resource group, tên endpoint và region phù hợp.
2. Storage Account mục tiêu.
3. **Target subresource**: ví dụ **blob**.
4. VNet và subnet **snet-private-endpoints**.
5. Tích hợp **Private DNS Zone** nếu dùng cơ chế DNS do Azure quản lý.

Nếu ứng dụng dùng cả Blob API và DFS API, đánh giá việc tạo thêm endpoint **dfs**. Nếu dùng Azure Files, chọn **file** và cấu hình DNS riêng cho File endpoint theo hướng dẫn của dịch vụ.

Kiểm tra private endpoint connection đạt **Approved** trước khi dựa vào endpoint này trong production. Có thể phải nhờ chủ sở hữu Storage Account phê duyệt nếu quyền được phân chia theo nhóm/subscription.

### Bước 4: xác minh Private DNS

Trong Private DNS Zone, kiểm tra:

- Tên zone đúng theo subresource, ví dụ **privatelink.blob.core.windows.net**.
- Bản ghi A trỏ tên Storage tới private IP đúng.
- VNet link tồn tại cho mạng có client hoặc resolver.
- DNS forwarder/private resolver có xử lý truy vấn từ on-premises nếu cần.

Từ một VM hoặc workload trong mạng cần truy cập, phân giải tên chuẩn của Storage:

~~~bash
nslookup stordersprod.blob.core.windows.net
~~~

Kỳ vọng là địa chỉ private endpoint theo thiết kế, ví dụ **10.50.3.4**. Không chỉ dựa vào việc thấy tên **privatelink** trong chuỗi CNAME; phải xem **địa chỉ cuối cùng** mà client nhận được.

### Bước 5: kiểm tra data plane trước khi khóa public access

Từ ứng dụng trong VNet:

1. Xác nhận DNS trả về private IP.
2. Xác nhận có kết nối TCP/443 tới endpoint.
3. Đăng nhập bằng danh tính hợp lệ và thử **đọc** một blob thử nghiệm.
4. Nếu ứng dụng cần ghi, thử thao tác ghi/xóa trong vùng dữ liệu thử nghiệm được phép.
5. Kiểm tra log và kết quả từ chính ứng dụng hoặc SDK.

Kiểm thử lại từ các môi trường có thật như máy chủ kế toán ở on-premises. Nếu client không truy cập được qua private endpoint, sửa DNS, route, firewall hoặc phân quyền trước; chưa nên tắt public network access.

### Bước 6: siết public network access

Sau khi tất cả client hợp lệ đã dùng đường truy cập riêng, chọn **Disabled** cho public network access của Storage Account và lưu thay đổi theo quy trình change management. Nếu vẫn có tích hợp bắt buộc sử dụng public endpoint, có thể phải giữ trạng thái selected networks và giới hạn nguồn trong giai đoạn chuyển đổi.

Việc đổi firewall có thể cắt kết nối ngay với các tác vụ cũ, pipeline hoặc máy quản trị. Hãy có cửa sổ bảo trì, người chịu trách nhiệm và kế hoạch quay lại cấu hình trước đó khi được phê duyệt.

### Bước 7: nghiệm thu và giám sát

Kiểm tra ba nhóm luồng:

| Nguồn request | Kỳ vọng sau khi siết mạng |
|---|---|
| API có private DNS, route và RBAC đúng | Đọc/ghi đúng phạm vi được phép |
| Máy tại chỗ đi qua VPN/ExpressRoute, DNS và quyền phù hợp | Truy cập thành công nếu thiết kế cho phép |
| Client từ Internet không qua private endpoint | Không thể truy cập data plane qua public endpoint |

Đồng thời xác minh người dùng **không có quyền dữ liệu** vẫn bị từ chối ngay cả khi kết nối từ một mạng hợp lệ. Kiểm tra diagnostic settings, alert và ngân sách cho các tài nguyên mới.

## 9. Kiểm tra cấu hình bằng Azure CLI

Các lệnh sau dùng để đọc cấu hình trong một môi trường đã tồn tại. Chúng phù hợp để đối chiếu trước/sau thay đổi, **không tự bật/tắt firewall**.

### Chọn subscription

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

### Xem public network access và network rule set

~~~bash
az storage account show \
  --resource-group "rg-sales-prod" \
  --name "stordersprod" \
  --query "{name:name,publicNetworkAccess:publicNetworkAccess,defaultAction:networkRuleSet.defaultAction,bypass:networkRuleSet.bypass,allowBlobPublicAccess:allowBlobPublicAccess,allowSharedKeyAccess:allowSharedKeyAccess}" \
  --output json
~~~

Lưu ý thuộc tính có thể không có hoặc có giá trị khác tùy cấu hình và phiên bản API. Đọc trạng thái thực tế trước khi kết luận chính sách đã được áp dụng đầy đủ.

~~~bash
az storage account network-rule list \
  --resource-group "rg-sales-prod" \
  --account-name "stordersprod" \
  --output json
~~~

Kiểm tra IP rules, VNet rules và bypass. Nếu **publicNetworkAccess** đang **Disabled**, đừng hiểu một IP rule cũ trong cấu hình là public endpoint đang mở.

### Xem Private Endpoint và kết nối

~~~bash
az network private-endpoint show \
  --resource-group "rg-sales-network" \
  --name "pe-blob-orders" \
  --query "{name:name,provisioningState:provisioningState,subnet:subnet.id,connections:privateLinkServiceConnections}" \
  --output json
~~~

Có thể kiểm tra danh sách private endpoint connections ở phía Storage Account qua Azure portal hoặc lệnh của dịch vụ tương ứng. **ProvisioningState = Succeeded** của private endpoint resource không thay thế việc xem trạng thái **Approved** của kết nối Private Link.

### Kiểm tra DNS từ client

~~~bash
nslookup stordersprod.blob.core.windows.net
~~~

Nếu đang dùng Linux với công cụ dig:

~~~bash
dig stordersprod.blob.core.windows.net
~~~

Khi cần kiểm thử kết nối cổng 443, trên máy có PowerShell có thể dùng:

~~~powershell
Test-NetConnection stordersprod.blob.core.windows.net -Port 443
~~~

Kết quả TCP/443 chỉ chứng minh có thể thiết lập kết nối mạng tới địa chỉ đã phân giải. Nó **không** chứng minh token, role hoặc quyền đọc/ghi Blob hợp lệ.

### Ví dụ cấu hình có điều kiện (không chạy nếu chưa phê duyệt)

Để minh họa quan hệ giữa các thuộc tính: một thiết kế **selected networks** có thể đặt public network access bật nhưng mặc định từ chối, sau đó bổ sung IP/VNet rules đã được xét duyệt:

~~~bash
az storage account update \
  --resource-group "rg-sales-prod" \
  --name "stordersprod" \
  --public-network-access Enabled \
  --default-action Deny
~~~

Lệnh trên **thay đổi cấu hình thật** và có thể gây gián đoạn. Nó không tự thêm mạng được phép, nên chỉ là ví dụ dưới sự kiểm soát thay đổi. Khi mọi client đã truy cập private endpoint đúng, có thể đặt **Disabled** thay vì mở lại public network access. Đừng sao chép lệnh vào production chỉ để thử bài học.

## 10. Xử lý lỗi thường gặp

Khi gặp lỗi truy cập Storage, cần phân loại theo **DNS**, **đường mạng**, **Storage firewall**, **trạng thái private endpoint** và **quyền data plane** trước khi sửa.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| DNS vẫn trả IP công cộng | Thiếu Private DNS Zone link, record sai hoặc on-premises forwarding chưa đúng | Chạy nslookup từ client thực, xem CNAME/A record, VNet link và resolver |
| TCP/443 timeout tới IP riêng | Route, VPN/ExpressRoute, NSG/UDR hoặc firewall trung gian chặn | Kiểm tra route đi/về, subnet endpoint, effective rules và kết nối từ nguồn |
| Private Endpoint tồn tại nhưng không dùng được | Connection chưa Approved, sai subresource hoặc DNS trỏ sai IP | Xem connection status, target subresource và endpoint NIC |
| Blob hoạt động nhưng DFS API lỗi | Chưa có endpoint/zone hoặc đường DNS tương ứng cho dfs | Kiểm tra sử dụng ADLS Gen2 và cấu hình blob/dfs |
| Portal thấy Storage Account nhưng không liệt kê được blob | Management plane hoạt động nhưng data plane bị network rule hoặc thiếu role | Kiểm tra network nguồn của trình duyệt và quyền Storage Blob Data Reader |
| Phản hồi HTTP 403 | Không có quyền dữ liệu, SAS sai/hết hạn, Shared Key bị tắt hoặc network firewall từ chối | Đọc mã lỗi chi tiết và request ID; kiểm tra auth và network riêng biệt |
| Dùng selected networks nhưng VM vẫn bị chặn | Subnet chưa bật service endpoint, VNet rule thiếu hoặc client dùng đường khác | Kiểm tra service endpoint của subnet, rule Storage và DNS |
| On-premises đi private endpoint vẫn lỗi | DNS on-premises hoặc route tới PE private IP chưa đúng | Kiểm tra kết quả DNS và route từ chính máy on-premises |
| Chuyển sang Disabled làm pipeline thất bại | Pipeline chạy ngoài VNet/private endpoint và trước đó dùng public endpoint | Xác định nơi pipeline chạy, cấp đường truy cập riêng hoặc điều chỉnh thiết kế |
| App Service không dùng được Private Endpoint | Chưa thiết lập mạng outbound/VNet Integration, DNS hoặc route tương ứng | Phân biệt Private Endpoint của Storage với tính năng mạng của App Service |

### Phân biệt lỗi 403 với lỗi kết nối

**Timeout hoặc không bắt tay được TCP** thường gợi ý DNS, route hoặc tường lửa trên đường đi. **HTTP 403** nghĩa request đã tới một thành phần trả phản hồi HTTP nhưng bị từ chối; nguyên nhân có thể nằm ở Storage network rules hoặc ở xác thực/phân quyền dữ liệu.

Hãy thu thập **mã lỗi chi tiết**, request ID, thời điểm, hostname, IP được phân giải và nguồn mạng. Với Azure Storage, một thông báo 403 đơn lẻ không đủ để kết luận lỗi do RBAC. Đồng thời, không giải quyết bằng cách bật **Allow access from all networks** hay chia sẻ account key rộng rãi nếu chưa xác định nguyên nhân.

### Quy trình chẩn đoán ngắn

1. Xác nhận Storage Account, subresource và subscription đích.
2. Từ client bị lỗi, xem DNS trả về private hay public IP.
3. Kiểm tra TCP/443 hoặc luồng mạng tới IP đã phân giải.
4. Kiểm tra private endpoint Approved, Storage public network access và các network rules tương ứng.
5. Kiểm tra phương thức xác thực, role data plane, token/SAS và quyền thao tác.
6. Đối chiếu diagnostic logs, request ID và những thay đổi gần đây.
7. Khắc phục thay đổi nhỏ nhất, kiểm thử lại ở cả luồng được phép và luồng cần bị chặn.

## 11. Giám sát, quản trị và kiểm soát chi phí

Một giải pháp Storage an toàn cần duy trì được trạng thái mong muốn sau mỗi lần triển khai hoặc mở rộng ứng dụng.

### Policy và phân quyền

Sử dụng Azure Policy để đánh giá hoặc áp dụng những cấu hình được hỗ trợ, chẳng hạn giới hạn public network access hoặc yêu cầu cơ chế truy cập mạng riêng theo chuẩn tổ chức. Dùng Azure RBAC để giới hạn ai được sửa Storage Account, network settings, Private Endpoint, DNS zone và các vai trò data plane.

Với nhiều subscription/resource group, cần gắn **tag** chủ sở hữu và phân công rõ nhóm mạng, nhóm ứng dụng và nhóm bảo mật. Không dùng quyền Owner ở phạm vi toàn subscription nếu tác vụ chỉ cần quyền nhỏ hơn.

### Log và cảnh báo

Cân nhắc bật **diagnostic settings** và dữ liệu giám sát phù hợp cho dịch vụ Storage, ví dụ log hoạt động đọc/ghi/xóa khi được hỗ trợ, metrics về số request, lỗi và độ trễ. Tùy dịch vụ và cấu hình, log có thể được gửi tới Log Analytics, Storage Account hoặc Event Hubs.

Theo dõi những dấu hiệu như:

- Số lượng request thất bại hoặc tăng đột ngột.
- Phản hồi 403 sau khi thay đổi firewall/DNS.
- Private endpoint connection bị thay đổi trạng thái.
- Public network access bị bật lại ngoài quy trình phê duyệt.
- Token, SAS hoặc account key được sử dụng không theo chính sách.

**Log Storage có thể chứa thông tin nhạy cảm hoặc định danh client.** Cần quản lý thời hạn lưu, quyền đọc log và chi phí thu thập dữ liệu theo chính sách tổ chức.

### Chi phí

Các khoản cần tính gồm dung lượng và thao tác Storage, băng thông/truyền dữ liệu, Private Endpoint (thời gian sử dụng và lưu lượng theo biểu phí hiện hành), Private DNS Zone/Resolver, VPN hoặc ExpressRoute, log và hệ thống giám sát. Tăng số Private Endpoint cho nhiều subresource hoặc nhiều mạng có thể làm tăng chi phí và độ phức tạp.

Trước khi triển khai production, kiểm tra **Azure Cost Management** cùng bảng giá và giới hạn của region/SKU hiện hành. Đừng cho rằng Private Endpoint miễn phí hay việc tắt public network access làm chi phí Storage bằng không.

## 12. Checklist chuyển đổi Storage từ public sang private

| Thời điểm | Công việc | Kết quả cần có |
|---|---|---|
| Trước | Kiểm kê client, endpoint blob/dfs/file/queue/table được sử dụng | Danh sách workload và chủ sở hữu |
| Trước | Kiểm tra public access, firewall rules, bypass và account keys/SAS | Baseline mạng và danh tính |
| Trước | Quy hoạch subnet, IP, VPN/ExpressRoute và route | Mạng đến Private Endpoint hợp lệ |
| Trước | Tạo endpoint đúng subresource và phê duyệt connection | Private Endpoint Approved |
| Trước | Liên kết Private DNS Zone và cấu hình forwarding | Client thật phân giải ra private IP |
| Trước | Kiểm thử read/write với Entra ID/RBAC hoặc phương thức hợp lệ | Ứng dụng hoạt động trên đường private |
| Thay đổi | Tắt public network access theo lịch đã phê duyệt | Public endpoint không còn phục vụ luồng ngoài ý muốn |
| Sau | Thử request từ mạng hợp lệ và mạng không được phép | Đúng luồng cho phép/từ chối |
| Sau | Kiểm tra log, alert, policy, role assignment và chi phí | Có giám sát và chủ sở hữu |
| Sau | Cập nhật IaC, DNS, runbook và kế hoạch khôi phục | Có khả năng vận hành/ứng phó sự cố |

**Kế hoạch quay lại cấu hình cũ (rollback)** phải được xác định trước khi thay đổi. Khi cần quay lại, không mặc định mở public endpoint cho mọi mạng; hãy khôi phục phạm vi truy cập đã phê duyệt và giữ nguyên yêu cầu xác thực.

## 13. Bài tập tình huống

Một ứng dụng quản lý hợp đồng chạy API trên Azure App Service và lưu PDF trên Blob Storage. Hiện tại, ứng dụng dùng connection string chứa account key; Storage Account cho phép mạng công cộng. Công ty muốn chuyển sang truy cập riêng nhưng vẫn cần một tác vụ kế toán tại trung tâm dữ liệu sử dụng file PDF.

Hãy thiết kế giải pháp, trả lời:

1. Những thành phần mạng nào cần có để App Service truy cập Blob qua Private Endpoint?
2. App Service cần cơ chế kết nối outbound nào tới VNet và DNS phải trả về địa chỉ nào?
3. Máy chủ kế toán tại chỗ cần cấu hình VPN/ExpressRoute, route và DNS forwarding ra sao?
4. Trong trường hợp chỉ dùng Blob API, cần chọn Storage subresource và Private DNS Zone nào?
5. Làm thế nào chuyển từ account key sang managed identity và Azure RBAC mà không làm gián đoạn ứng dụng?
6. Cần kiểm thử những thao tác read/write, quyền bị từ chối và luồng public nào trước khi tắt public network access?
7. Nếu sau thay đổi API nhận 403 còn máy kế toán timeout, hai nhóm nguyên nhân khác nhau nào cần điều tra?
8. Nêu log, policy, chi phí và kế hoạch rollback cần chuẩn bị.

Một phương án tốt có Storage Private Endpoint cho **blob**, Private DNS Zone tương ứng, VNet Integration outbound cho App Service theo tính năng hỗ trợ, kết nối riêng từ trung tâm dữ liệu cùng DNS forwarding, và managed identity được cấp vai trò Blob data plane tối thiểu. Chỉ tắt public network access khi các nguồn hợp lệ đã được kiểm chứng; không chia sẻ account key để thay thế giải pháp RBAC.

## 14. Những hiểu lầm thường gặp

**“Đã có Private Endpoint thì Storage public endpoint tự đóng.”** Không nhất thiết. Phải kiểm tra và đặt public network access theo chính sách; tạo endpoint riêng không tự loại bỏ mọi đường công cộng.

**“Firewall selected networks nghĩa là chỉ các private IP mới được vào.”** Sai. Selected networks có thể cho phép IP công cộng hoặc subnet dùng service endpoint. Private Endpoint là cơ chế khác.

**“Service endpoint và Private Endpoint giống nhau.”** Không. Service endpoint giúp giới hạn nguồn subnet khi đi tới public service endpoint; Private Endpoint dùng private IP kết nối qua Private Link.

**“Có thể dùng private IP cố định trong connection string và bỏ qua DNS.”** Không nên. Tên dịch vụ chuẩn kết hợp DNS đúng hỗ trợ TLS, endpoint routing và khả năng thay đổi hạ tầng tốt hơn.

**“Private Endpoint có quyền đọc blob dù không cần đăng nhập.”** Sai. Network connectivity và authorization là hai lớp độc lập.

**“Storage firewall chặn Internet nên không cần vô hiệu hóa blob anonymous access.”** Sai. Đây là hai kiểm soát riêng; cần thiết lập cả mạng và quyền truy cập dữ liệu đúng mục tiêu.

**“Chọn All networks để sửa lỗi 403 là giải pháp an toàn.”** Không. 403 có thể do RBAC, SAS, account key hoặc firewall; cần phân tích nguyên nhân và chỉ mở phạm vi cần thiết nếu được phê duyệt.

**“VPN đã chạy thì Storage private endpoint luôn truy cập được.”** Chưa đủ. Còn cần DNS đúng, route tới private IP, connection Approved và xác thực hợp lệ.

## 15. Câu hỏi tự kiểm tra

1. Storage firewall bảo vệ public endpoint như thế nào? Nó có thay thế RBAC data plane không?
2. Khi public network access ở trạng thái Disabled, client nên kết nối Storage theo đường nào?
3. Sự khác biệt quan trọng nhất giữa Storage service endpoint và Private Endpoint là gì?
4. Vì sao tạo Private Endpoint cho **blob** không mặc định giải quyết mọi truy cập **dfs** hoặc **file**?
5. Vì sao DNS từ chính máy client là bằng chứng quan trọng khi kiểm tra Private Endpoint?
6. Tại sao Azure portal vẫn hiển thị thông tin Storage Account dù bạn không xem được danh sách blob?
7. Khi ứng dụng nhận HTTP 403, hãy liệt kê ít nhất ba nhóm nguyên nhân cần phân biệt.
8. Dùng managed identity và Storage Blob Data Contributor có lợi ích gì so với chia sẻ account key?
9. Vì sao cần kiểm thử lưu lượng từ on-premises trước khi tắt public network access?
10. Những khoản chi phí và cấu hình giám sát nào phải được cân nhắc khi triển khai nhiều Private Endpoint?

## Tài liệu tham khảo

- Microsoft Learn — *Configure Azure Storage firewalls and virtual networks*: https://learn.microsoft.com/azure/storage/common/storage-network-security
- Microsoft Learn — *Use private endpoints for Azure Storage*: https://learn.microsoft.com/azure/storage/common/storage-private-endpoints
- Microsoft Learn — *What is a private endpoint?*: https://learn.microsoft.com/azure/private-link/private-endpoint-overview
- Microsoft Learn — *Private endpoint DNS configuration*: https://learn.microsoft.com/azure/private-link/private-endpoint-dns
- Microsoft Learn — *Authorize access to Azure Storage*: https://learn.microsoft.com/azure/storage/common/authorize-data-access
- Microsoft Learn — *Authorize access to Blob data with Microsoft Entra ID*: https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory
- Microsoft Learn — *Security recommendations for Azure Blob Storage*: https://learn.microsoft.com/azure/storage/blobs/security-recommendations
