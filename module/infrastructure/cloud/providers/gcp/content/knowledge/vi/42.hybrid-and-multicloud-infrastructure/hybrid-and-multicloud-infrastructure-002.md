# Thiết kế kết nối, DNS và định tuyến xuyên môi trường

Hạ tầng lai và đa đám mây kết nối các hệ thống đang chạy tại trung tâm dữ liệu, văn phòng, Google Cloud và có thể cả AWS hoặc Azure. Một kết nối mạng hoạt động tốt không chỉ là việc hai máy có thể ping nhau. Ứng dụng cần tìm đúng tên dịch vụ, gói tin phải có đường đi và đường về phù hợp, firewall phải cho phép đúng lưu lượng, còn sự cố một tuyến không được khiến toàn bộ hệ thống mất kết nối.

Trên Google Cloud, những thành phần quan trọng gồm VPC, HA VPN, Cloud Interconnect, Cloud Router, Cloud DNS, firewall và các cơ chế kết nối tài nguyên được quản lý. Bài học hướng dẫn cách thiết kế chúng thành một kiến trúc có thể mở rộng: xác định dải IP, chọn công nghệ kết nối, lập chính sách định tuyến, thiết kế phân giải DNS hai chiều và kiểm thử khả năng khôi phục. Mục tiêu cuối cùng là giúp ứng dụng triển khai trên Compute Engine, GKE, Cloud Run và các dịch vụ dữ liệu giao tiếp đúng nơi, đúng quyền, với độ tin cậy và chi phí phù hợp.

## 1. Bắt đầu từ yêu cầu kết nối, không bắt đầu từ sản phẩm

Trước khi tạo tunnel hoặc cấu hình DNS, nhóm mạng và nhóm ứng dụng phải thống nhất hệ thống nào thực sự cần kết nối. Một thiết kế tốt ghi được nguồn, đích, giao thức, nhu cầu lưu lượng, kỳ vọng độ trễ và ai sở hữu kết nối đó.

| Câu hỏi | Ví dụ cần xác định | Ảnh hưởng đến kiến trúc |
| --- | --- | --- |
| Nguồn và đích ở đâu? | GKE production đến Oracle on-premises | Có cần route hai chiều và DNS private không? |
| Lưu lượng loại nào? | HTTPS, database TCP, DNS UDP/TCP, replication | Chọn firewall và kiểm tra MTU |
| Băng thông và độ trễ? | Tải ổn định hay truyền dữ liệu lớn theo đợt | Chọn VPN hoặc Interconnect và công suất |
| Mức độ sẵn sàng? | Cần chịu được lỗi một thiết bị, tunnel hay vùng | Số đường vật lý, peer BGP và phương án failover |
| Ranh giới bảo mật? | Production không được truy cập trực tiếp môi trường dev | Segmentation, IAM, routing và firewall |
| Cách tìm dịch vụ? | Tên nội bộ db.corp.example.com | Private DNS zone, conditional forwarding, resolver |
| Ai vận hành? | Network team quản lý BGP, platform team quản lý DNS | Quyền thay đổi và runbook |

Không phải mọi hệ thống đều cần địa chỉ IP riêng xuyên môi trường. Nếu ứng dụng chỉ cần gọi một API cụ thể, một phương án qua HTTPS, gateway hoặc Private Service Connect được hỗ trợ có thể hạn chế phạm vi kết nối hơn một mạng định tuyến đầy đủ. Hãy chọn mức kết nối nhỏ nhất đáp ứng nghiệp vụ.

## 2. Kiến trúc tham chiếu hybrid và multicloud

Một kiến trúc mẫu gồm trung tâm dữ liệu có router, DNS và database; VPC Google Cloud có workload GKE/Compute Engine; cùng một mạng ở nhà cung cấp cloud khác. Kết nối giữa chúng phải có quyết định riêng về bảo mật, địa chỉ IP, quảng bá route và DNS.

~~~mermaid
flowchart LR
  subgraph DC["Trung tâm dữ liệu"]
    DR["Router / firewall A, B"]
    DNSDC["DNS nội bộ"]
    DBDC["Database nội bộ"]
  end
  subgraph GCP["Google Cloud"]
    CR["Cloud Router / BGP"]
    VPC["Production VPC"]
    DNSG["Cloud DNS private / forwarding"]
    APP["GKE / VM / Cloud Run"]
  end
  subgraph OTHER["Cloud khác"]
    RTR["VPN gateway / cloud router"]
    SVC["Workload / resolver"]
  end
  DR <-->|"HA VPN hoặc Interconnect"| CR
  CR --- VPC
  VPC --- APP
  VPC --- DNSG
  DR --- DNSDC
  DR --- DBDC
  RTR <-->|"VPN hoặc kết nối private hỗ trợ"| VPC
  RTR --- SVC
~~~

Sơ đồ là luồng logic, không phải tài liệu cấu hình đủ các cổng và thiết bị. Trong triển khai thật, phải tách rõ các đường dự phòng, điểm kết nối vật lý, BGP sessions, giới hạn tuyến và policy bảo mật. Không xem liên kết với cloud khác là đường dự phòng tự động cho trung tâm dữ liệu nếu chưa thiết kế và thử nghiệm chức năng chuyển tiếp đó.

Ba lớp cần xem xét độc lập:

1. **Kết nối (underlay):** tunnel IPsec hoặc đường truyền chuyên dụng có hoạt động và đủ công suất không?
2. **Định tuyến (routing):** prefix nào được học và quảng bá, next hop nào được chọn, tuyến chiều về có tồn tại không?
3. **Phân giải tên (DNS):** tên dịch vụ được phân giải bởi resolver nào, bản ghi private có đúng địa chỉ hiện hành không?

Một ứng dụng vẫn có thể thất bại dù kết nối vật lý và BGP đều đang hoạt động, chẳng hạn vì DNS trỏ đến IP cũ hoặc firewall chỉ cho phép đường đi mà chặn đường về.

## 3. IPAM: thiết kế địa chỉ trước khi kết nối

IP Address Management (IPAM) là bước quan trọng nhất để tránh phải sửa kiến trúc về sau. Các vùng địa chỉ được định tuyến tới nhau phải không chồng lấp, trừ khi có thiết kế dịch địa chỉ rõ ràng. Phải tính cả các dải mà ứng dụng không trực tiếp nhìn thấy: secondary ranges của GKE, private service ranges, mạng của VPN appliance và dải mạng ở các cloud khác.

Ví dụ bảng quy hoạch cho môi trường thử nghiệm:

| Mạng hoặc chức năng | Dải ví dụ | Ghi chú |
| --- | --- | --- |
| On-premises | 10.10.0.0/16 | Các subnet ứng dụng và database tại DC |
| GCP production - subnet chính | 10.20.0.0/16 | Chia thành các subnet nhỏ hơn theo region và tier |
| GKE Pod secondary range | 10.21.0.0/16 | Dùng khi GKE được cấu hình VPC-native |
| GKE Service secondary range | 10.22.0.0/20 | Phạm vi ClusterIP, kiểm tra nhu cầu thực tế |
| Private services access | 10.23.0.0/16 | Dành riêng nếu kiến trúc sử dụng dịch vụ hỗ trợ PSA |
| GCP staging | 10.30.0.0/16 | Tách chính sách và tuyến với production |
| AWS hoặc cloud khác | 10.40.0.0/16 | Không chồng lấp với mạng trên |
| Azure hoặc cloud khác | 10.50.0.0/16 | Không chồng lấp với mạng trên |

Các dải trên chỉ minh họa cách phân bổ, không phải cấu hình mặc định hay gợi ý cấp phát đủ cho mọi workload. Kế hoạch thực tế cần xét tăng trưởng, subnet region, IP dành cho node và Pod của GKE, VIP của dịch vụ, IP của endpoint private và các giới hạn kỹ thuật từng sản phẩm.

Một số nguyên tắc:

- Dự trữ CIDR theo miền quản trị và môi trường trước khi tạo subnet, thay vì cấp phát rời rạc từng project.
- Không chỉ kiểm tra primary subnet ranges; kiểm tra cả secondary ranges, allocated ranges của dịch vụ và mạng on-premises.
- Thống nhất người có quyền cấp phát hoặc thu hồi CIDR; mọi thay đổi phải cập nhật IPAM.
- Đánh giá IPv6 riêng nếu hệ thống sử dụng dual-stack; quy tắc quảng bá tuyến và hỗ trợ sản phẩm có thể khác IPv4.
- Chỉ sử dụng NAT để xử lý địa chỉ chồng lấp khi không thể đổi dải và đã chấp nhận độ phức tạp về log, firewall, DNS và troubleshooting.

Với mạng dùng cùng CIDR ở hai cloud, BGP không tự giải quyết xung đột. Route trùng đích có thể khiến traffic đi nhầm nơi hoặc không có đường về. Nếu bắt buộc giữ địa chỉ chồng lấp, hãy thiết kế lớp dịch địa chỉ hoặc gateway trung gian với địa chỉ đã dịch duy nhất và kiểm thử end-to-end theo từng ứng dụng.

## 4. Chọn kết nối: HA VPN, Interconnect hay phương án khác?

Không có một dịch vụ kết nối tối ưu cho mọi nhu cầu. HA VPN thường phù hợp với yêu cầu kết nối IPsec cần triển khai nhanh và băng thông trong giới hạn hỗ trợ. Cloud Interconnect phù hợp khi cần kết nối có tính dự đoán cao về công suất và đường truyền chuyên dụng. Một số mô hình multicloud có thể dùng Cross-Cloud Interconnect hoặc kết nối của nhà cung cấp đối tác nếu vùng triển khai, nhà cung cấp và sản phẩm hỗ trợ.

| Phương án | Đặc điểm | Khi xem xét |
| --- | --- | --- |
| HA VPN | Kết nối IPsec qua internet hoặc đường đi hỗ trợ, dùng BGP với Cloud Router | Tạo kết nối hybrid an toàn, dự phòng tunnel và peer |
| Dedicated Interconnect | Kết nối vật lý chuyên dụng tại vị trí kết nối được hỗ trợ | Lưu lượng lớn, ổn định, yêu cầu kiểm soát kết nối vật lý |
| Partner Interconnect | Kết nối qua nhà cung cấp dịch vụ được hỗ trợ | Không có mặt tại cơ sở kết nối trực tiếp hoặc muốn dùng đối tác |
| Cross-Cloud Interconnect | Kết nối chuyên dụng với một số nhà cung cấp cloud được hỗ trợ | Multicloud cần công suất cao và tuyến private theo khả năng cung cấp |
| VPN giữa các cloud | Các gateway IPsec và BGP của hai cloud | Lưu lượng vừa phải, cần triển khai linh hoạt |
| Kết nối theo ứng dụng | HTTPS, API gateway, proxy hoặc PSC khi phù hợp | Chỉ cần kết nối một dịch vụ, hạn chế mở toàn bộ mạng |

**HA** phải được thiết kế từ đầu: hai đường hay hai tunnel không bảo đảm độc lập nếu chúng phụ thuộc cùng một router, thiết bị firewall, nguồn điện hoặc nhà cung cấp. Với Interconnect, thiết kế độ tin cậy thường cần nhiều kết nối tại các vị trí và miền lỗi phù hợp, đi cùng các VLAN attachments và phiên BGP tương ứng.

Hãy đo băng thông thực tế của ứng dụng, đặc biệt chiều truyền dữ liệu lớn, rồi so với giới hạn từng đường kết nối. Đồng thời kiểm tra chi phí vận chuyển dữ liệu, phí port/attachment/tunnel, phí lưu lượng ra và phí đối tác trước khi chọn. Một VPN là lựa chọn đúng trong giai đoạn đầu không nhất thiết còn phù hợp khi lượng replication tăng nhiều lần.

## 5. Cloud Router và BGP vận hành ở lớp định tuyến

Cloud Router là dịch vụ điều khiển việc trao đổi route động qua BGP với các gateway hoặc kết nối được hỗ trợ. Cloud Router **không phải** thiết bị chuyển tiếp gói tin truyền thống: dữ liệu được chuyển tiếp qua hạ tầng mạng của Google Cloud và thành phần kết nối; Cloud Router quản lý thông tin định tuyến.

Một phiên BGP cần các tham số tương thích ở hai đầu: ASN, địa chỉ peering, khả năng IPv4/IPv6 theo sản phẩm, timer và policy. Những prefix được quảng bá phải là những dải mà phía nhận thực sự được phép và có khả năng truy cập.

Các khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Learned routes | Prefix Google Cloud học từ router đối tác qua BGP |
| Advertised routes | Prefix Cloud Router quảng bá sang phía đối tác |
| Regional dynamic routing | Ảnh hưởng phạm vi áp dụng dynamic routes theo regional mode của VPC |
| Global dynamic routing | Cho phép phạm vi áp dụng dynamic routes ở nhiều region theo chính sách mạng, cần xét cơ chế ưu tiên tuyến |
| BGP base advertised priority | Tín hiệu ưu tiên route quảng bá trong thiết kế, không thay thế policy ở peer |
| Route next hop | Hướng lưu lượng thực sự đi qua kết nối hoặc tài nguyên tương ứng |

Hãy kiểm tra dynamic routing mode của VPC, đặc biệt khi có workload tại nhiều region. Thiết kế chỉ xem đường đi từ một subnet trong một region có thể bỏ sót việc subnet ở region khác không dùng được route như kỳ vọng.

Không nên quảng bá mặc định 0.0.0.0/0 xuyên kết nối chỉ để sửa một lỗi truy cập. Default route có thể đưa lưu lượng internet hoặc traffic không mong muốn qua trung tâm dữ liệu, tăng độ trễ và chi phí, đồng thời tạo điểm nghẽn hoặc đường đi không an toàn. Chỉ áp dụng khi đó là mục tiêu kiến trúc rõ ràng, ví dụ egress tập trung, và đã thiết kế return path cùng các vùng bảo mật.

## 6. Thiết kế ưu tiên tuyến và failover

Hệ thống có thể có nhiều đường: hai VPN tunnels, hai Interconnect attachments hoặc một Interconnect chính và một VPN dự phòng. Điều quan trọng không chỉ là có nhiều route mà phải biết khi nào route nào được chọn và điều gì xảy ra khi mất một phiên BGP.

Ví dụ chính sách:

| Tình huống | Mong muốn | Kiểm chứng |
| --- | --- | --- |
| Cả hai kết nối khỏe | Chọn tuyến chính hoặc phân tải theo thiết kế | Quan sát route được chọn và luồng traffic |
| Một tunnel hoặc peer BGP lỗi | Chuyển sang tuyến khác mà không quảng bá sai CIDR | Kiểm tra route mới và request thành công |
| Phía on-prem mất router chính | Không mất toàn bộ DNS và kết nối ứng dụng | Thử nghiệm firewall/router dự phòng |
| Một region gặp sự cố | Workload ở region khác còn truy cập được nếu kiến trúc cho phép | Kiểm tra routing mode và năng lực còn lại |
| Đường dự phòng có công suất thấp | Dịch vụ ưu tiên vẫn hoạt động, không quá tải | Đo throughput và giới hạn ưu tiên traffic |

Không nhầm metric "BGP session UP" với "ứng dụng truy cập được". BGP có thể vẫn UP dù firewall chặn TCP 443 hoặc DNS bị lỗi. Ngược lại, BGP DOWN chỉ ra vấn đề lớp định tuyến cần điều tra, không nhất thiết là nguyên nhân trực tiếp của mọi lỗi nếu một tuyến khác còn hoạt động.

Để điều chỉnh hướng traffic, hãy tìm hiểu thứ tự chọn route của Google Cloud, route priority, BGP advertised priorities và policy của peer. Không giả định rằng đặt một giá trị priority ở một phía sẽ điều khiển được cả chiều đi lẫn chiều về. Thiết kế tuyến không đối xứng cũng cần đánh giá firewall stateful và thiết bị NAT ở cả hai đầu.

## 7. Định tuyến giữa nhiều VPC và nhiều cloud

Google Cloud VPC Network Peering hỗ trợ giao tiếp giữa những VPC được peering theo quy tắc và tùy chọn import/export route của sản phẩm. Tuy nhiên, **VPC Peering không cung cấp định tuyến bắc cầu tự động**: nếu VPC A peering với B, và B peering với C, không thể suy ra A đi được C qua B.

Với kiến trúc nhiều spoke hoặc cần kết nối hybrid tại quy mô lớn, có thể đánh giá Network Connectivity Center (NCC) và các loại spoke được hỗ trợ để tổ chức hub-and-spoke. Cần cấu hình rõ mô hình truyền dữ liệu site-to-site, nhóm spoke, route exchange và những tính năng được hỗ trợ theo loại spoke/region; không giả định mọi cặp spoke sẽ tự động trao đổi mọi route.

Đối với AWS và Azure, phía đối tác có các thành phần định tuyến, gateway và route table riêng. Thiết kế phải xác định rõ:

- CIDR ở từng VPC/VNet và subnet nào thật sự cần route.
- Route được propagate tự động hay cần khai báo tĩnh tại phía đối tác.
- Tổ hợp BGP ASN, tunnel và mạng có được hai nhà cung cấp hỗ trợ không.
- Firewall, security group, network security group hoặc policy của từng cloud.
- Có tồn tại NAT hoặc gateway trung gian làm đổi source IP mà phía nhận dùng để kiểm soát truy cập không.
- Những route nào được phép trở thành đường quá cảnh giữa on-prem, GCP, AWS và Azure.

Một mạng multicloud cần chính sách route exchange theo nguyên tắc ít quyền nhất. Ví dụ, production GCP cần truy cập dịch vụ báo cáo tại AWS không đồng nghĩa AWS phải học toàn bộ mạng staging GCP hoặc toàn bộ mạng quản trị on-premises.

## 8. DNS là một mặt phẳng thiết kế riêng

Định tuyến theo IP và phân giải DNS là hai bài toán khác nhau. Một tuyến có thể hoạt động tốt nhưng ứng dụng vẫn lỗi vì tên nội bộ không được phân giải, có bản ghi cũ hoặc resolver trả về địa chỉ public không đúng.

Trong Google Cloud, Cloud DNS có thể cung cấp:

| Thành phần DNS | Mục đích |
| --- | --- |
| Private managed zone | Lưu bản ghi DNS private và chỉ cho các VPC được ủy quyền truy vấn |
| Forwarding zone | Chuyển truy vấn cho một hậu tố domain đến DNS server đích |
| DNS peering zone | Cho phép một VPC dùng quy trình phân giải DNS của một VPC khác theo khả năng hỗ trợ |
| Inbound forwarding policy | Cung cấp điểm truy vấn để hệ thống ngoài VPC, chẳng hạn on-prem, hỏi resolver Cloud DNS của VPC |
| DNS server policy và outbound forwarding | Điều chỉnh cách các tên phù hợp được chuyển tiếp đến DNS khác |
| Public managed zone | Công bố bản ghi public; không thay thế zone private khi dữ liệu nội bộ cần giới hạn truy cập |

Private zone được gắn với các VPC đã được ủy quyền. Kết nối mạng hoặc VPC Peering không có nghĩa bản ghi private sẽ tự động hiện ở mọi VPC. Cần kiểm tra quyền truy cập DNS riêng cho từng VPC và lựa chọn peering hoặc forwarding khi cần.

DNS service có thể hỗ trợ ứng dụng truy cập workload private, nhưng bản ghi tồn tại không tự cấp quyền truy cập dịch vụ. Sau phân giải tên, firewall, routing, ingress, IAM và authentication vẫn phải được kiểm tra.

## 9. Thiết kế namespace và quyền sở hữu domain

Nên xác định một cấu trúc tên rõ ràng để tránh chồng lấp và vòng lặp truy vấn. Ví dụ:

| Namespace | Nơi có bản ghi authoritative hoặc nơi quản trị | Ứng dụng |
| --- | --- | --- |
| corp.example.com. | DNS on-premises | Tên máy chủ và database nội bộ |
| gcp.corp.example.com. | Cloud DNS private zone | Tên dịch vụ private của Google Cloud |
| aws.corp.example.com. | DNS của môi trường AWS | Dịch vụ nội bộ ở AWS |
| azure.corp.example.com. | DNS của môi trường Azure | Dịch vụ nội bộ ở Azure |

Tên chỉ là minh họa. Trong hệ thống thật, phải thống nhất domain do tổ chức kiểm soát, chính sách DNS public/private và cách quản lý bản ghi. Không tạo hai authoritative zones có cùng tên nhưng nội dung mâu thuẫn mà không có chiến lược phân giải rõ ràng.

**Split-horizon DNS** có thể trả lời khác nhau cho một tên tùy phía truy vấn. Mô hình này hữu ích khi muốn người dùng nội bộ nhận IP private còn người dùng ngoài nhận IP public, nhưng tạo rủi ro khó quan sát khi các resolver dùng cache khác nhau.

Hãy tài liệu hóa:

- Domain và subdomain nào do nhóm nào sở hữu.
- Client ở GCP, on-prem và cloud khác sẽ truy vấn resolver nào.
- Bản ghi nào được phép xuất hiện ở DNS public, bản ghi nào chỉ ở DNS private.
- Chính sách TTL, thay đổi bản ghi và rollback.
- Quy trình xử lý khi authoritative server hoặc forwarding target không khả dụng.

## 10. DNS từ Google Cloud đến on-premises

Giả sử workload GKE cần truy vấn tên database.corp.example.com được quản lý bởi DNS server on-premises. Cloud DNS forwarding zone có thể chuyển các truy vấn cho hậu tố corp.example.com. đến DNS server nội bộ, nếu kết nối và các quy tắc định tuyến cho phép.

Luồng ý tưởng:

~~~mermaid
sequenceDiagram
  participant App as GKE / VM
  participant Google as Cloud DNS resolver
  participant DC as DNS on-prem
  App->>Google: A database.corp.example.com?
  Google->>DC: Forward truy vấn theo zone
  DC-->>Google: A 10.10.20.15
  Google-->>App: Trả IP private
  App->>DC: TCP đến 10.10.20.15 qua VPN/Interconnect
~~~

Ví dụ tạo forwarding zone trong một VPC thử nghiệm:

~~~bash
gcloud dns managed-zones create corp-forward \
  --project=PROJECT_ID \
  --description="Forward on-prem namespace" \
  --dns-name=corp.example.com. \
  --visibility=private \
  --networks=prod-vpc \
  --forwarding-targets=10.10.1.10
~~~

Đây là cấu hình tham khảo với DNS server on-prem giả định 10.10.1.10. Trước khi dùng, cần bảo đảm Cloud DNS có thể tới forwarding target qua đường kết nối được hỗ trợ, DNS server chấp nhận truy vấn và đường trả lời hoạt động. Việc forwarding có thể sử dụng dải IP nguồn đặc biệt của Cloud DNS, vì vậy firewall và return routing phía on-prem phải được cấu hình theo tài liệu Cloud DNS forwarding hiện hành, không chỉ dựa vào CIDR của subnet workload.

Kiểm tra cả UDP và TCP cổng 53 khi phù hợp. DNS có thể cần TCP cho câu trả lời lớn, fallback hoặc một số luồng xử lý. Nếu truy vấn trả NXDOMAIN, xác minh hậu tố zone, bản ghi authoritative và cache trước khi kết luận kết nối mạng bị lỗi.

## 11. DNS từ on-premises vào Google Cloud

Giả sử máy chủ tại DC cần tìm api.gcp.corp.example.com, một bản ghi thuộc private zone của Google Cloud. On-prem resolver có thể đặt conditional forwarder cho gcp.corp.example.com. trỏ tới điểm vào của Cloud DNS inbound forwarding.

Các bước thiết kế:

1. Tạo private managed zone gcp.corp.example.com. và ủy quyền đúng VPC Google Cloud.
2. Tạo DNS policy bật inbound forwarding cho VPC theo khả năng hỗ trợ.
3. Lấy danh sách địa chỉ inbound forwarding entry point được Google Cloud cung cấp.
4. Cấu hình DNS server on-prem conditional forwarder cho đúng hậu tố đến các địa chỉ inbound đó.
5. Cho phép DNS traffic và đảm bảo route đi/về qua kết nối phù hợp.
6. Truy vấn tên mẫu từ DC; xác minh IP trả về đúng VPC hoặc endpoint private.

Ví dụ lệnh minh họa bật inbound forwarding policy:

~~~bash
gcloud dns policies create prod-inbound \
  --project=PROJECT_ID \
  --networks=prod-vpc \
  --enable-inbound-forwarding \
  --description="Enable DNS queries from connected networks"
~~~

Sau khi tạo policy, hãy xem chi tiết policy và các địa chỉ inbound resolver của mạng để cấu hình phía DC. Không hardcode địa chỉ inbound DNS từ một ví dụ sang môi trường thật. Việc có IP inbound không tự cấp phép mạng: firewall, route và quyền truy cập DNS phải được thiết kế đúng.

Cloud DNS private zones không được chuyển thành public chỉ để on-prem tìm thấy bản ghi. Sử dụng inbound forwarding, DNS peering hoặc giải pháp name-resolution tương thích theo phạm vi cần thiết.

## 12. DNS giữa các VPC và giữa các cloud

Trong tổ chức có Shared VPC, ứng dụng thuộc service project có thể sử dụng network của host project. Cần xác định VPC nào thực sự là mạng truy vấn DNS và nơi quản trị private zone. Không nhầm ranh giới project sở hữu ứng dụng với ranh giới VPC liên quan đến DNS.

Với nhiều VPC, có thể cân nhắc:

- Gắn private zone vào nhiều VPC nếu mục tiêu là dùng chung chính zone đó và chính sách cho phép.
- Sử dụng DNS peering zone khi muốn chuyển việc phân giải cho một VPC khác mà không nhân bản dữ liệu zone.
- Sử dụng forwarding zone khi có một DNS resolver chịu trách nhiệm cho một namespace.
- Tạo zone riêng theo môi trường production/staging khi cần cô lập tên và quyền.

DNS peering không đồng nghĩa với IP routing. Một VPC có thể phân giải thành công tên trong VPC khác nhưng không có route hoặc firewall cho phép truy cập IP vừa nhận. Cần kiểm tra độc lập hai phần.

Với AWS, khả năng tích hợp DNS private thường liên quan Route 53 Resolver và các inbound/outbound endpoints được cấu hình đúng; với Azure, có thể dùng Azure DNS Private Resolver và forwarding rulesets theo khả năng hỗ trợ. Khi kết nối qua GCP VPN/Interconnect, thiết kế chiều truy vấn, source IP, route trả về, ACL và quyền quản trị ở cả hai cloud. Không tự giả định private hosted zone bên cloud đối tác có thể được phân giải trực tiếp từ GCP khi chưa có cơ chế forwarding hoặc resolver phù hợp.

Một lỗi phổ biến là tạo forwarding theo cả hai chiều cho cùng một suffix mà không có bên nào thực sự authoritative. Truy vấn khi đó có thể đi vòng giữa các resolver cho đến timeout. Hãy ghi rõ bên nào là nguồn sự thật của từng namespace và dùng forwarding chỉ để hướng truy vấn đến bên đó.

## 13. Thứ tự phân giải và xử lý xung đột tên

Khi có public zone, private zone, peering zone, forwarding zone và nhiều resolver trong cùng môi trường, tên nào được khớp có thể ảnh hưởng mạnh đến kết quả. Các zone có hậu tố cụ thể hơn thường có ý nghĩa ưu tiên trong quy tắc phân giải phù hợp, nhưng chi tiết phụ thuộc cơ chế Cloud DNS và chính sách của network.

Ví dụ nếu tồn tại:

- Forwarding zone cho corp.example.com. đến DC.
- Private zone gcp.corp.example.com. tại GCP.

Truy vấn api.gcp.corp.example.com. phải được xử lý theo zone cụ thể và cấu hình resolver phù hợp, thay vì chuyển mọi tên dưới corp.example.com. về DC. Khi triển khai cần kiểm tra cách Cloud DNS chọn vùng DNS và các quy tắc chồng lấp được hỗ trợ.

Kiểm thử ít nhất các trường hợp:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Bản ghi tồn tại ở zone private GCP | Trả IP private dự kiến |
| Bản ghi tồn tại ở on-prem | GCP forward đúng DNS server đích |
| Bản ghi không tồn tại | Trả NXDOMAIN hợp lệ, không vòng lặp |
| Bản ghi trùng tên giữa private/public | Resolver trả đúng đáp án cho từng phía |
| DNS target primary lỗi | Truy vấn có dùng target dự phòng nếu cấu hình hỗ trợ |
| TTL đã giảm trước cutover | Client và resolver có nhận bản ghi mới sau khoảng chờ hợp lý |

DNS caching có thể khiến việc đổi bản ghi chưa có tác dụng ngay. TTL và negative caching đều quan trọng: một truy vấn không tìm thấy tên trước khi tạo bản ghi có thể tiếp tục trả kết quả âm trong một thời gian. Hãy lên kế hoạch thay đổi DNS trước cutover, không giảm TTL ngay lúc sự cố rồi kỳ vọng toàn bộ cache được làm mới tức thì.

## 14. Bảo mật kết nối, DNS và phân đoạn mạng

VPN mã hóa lưu lượng ở lớp tunnel theo giao thức IPsec. Kết nối vật lý private không tự đồng nghĩa mọi gói tin được mã hóa end-to-end. Dù dùng Interconnect hay VPN, các giao thức chứa dữ liệu nhạy cảm vẫn cần kiểm tra yêu cầu TLS/mTLS, xác thực ứng dụng và kiểm soát truy cập phù hợp.

Một bảng policy mạng mẫu:

| Nguồn | Đích | Giao thức | Mục đích | Nguyên tắc |
| --- | --- | --- | --- | --- |
| GKE app subnet | Database on-prem | TCP cổng database | Truy vấn nghiệp vụ | Chỉ đúng subnet/identity được phép |
| On-prem DNS resolver | Cloud DNS inbound entry point | UDP/TCP 53 | Phân giải tên GCP private | Chỉ các resolver được ủy quyền |
| Cloud DNS forwarding | DNS on-prem | UDP/TCP 53 | Phân giải tên nội bộ DC | Cho phép nguồn forwarding được tài liệu hóa |
| Admin subnet | Bastion hoặc endpoint quản trị | SSH/HTTPS theo kiến trúc | Quản trị có kiểm soát | Không mở cho toàn bộ mạng |

Ngoài firewall trong VPC, phải kiểm tra firewall/router phía DC, network policy của GKE, ACL của resolver và security controls của các cloud khác. Gắn tên DNS với tài nguyên không thay thế IAM hoặc xác thực ứng dụng; DNS là cơ chế khám phá địa chỉ, không phải giấy phép truy cập.

Một số kiểm soát nên có:

- Chặn phân giải hoặc kết nối không được phép giữa dev, staging và production.
- Hạn chế thay đổi Cloud DNS zones, Cloud Router, VPN tunnels và route advertisement theo phân tách nhiệm vụ.
- Kiểm tra log thay đổi IAM, DNS, firewall và cấu hình kết nối; sử dụng audit logs và change management.
- Không mở DNS resolver thành dịch vụ đệ quy cho mọi địa chỉ internet.
- Tránh ghi dữ liệu nhạy cảm trong tên truy vấn DNS hoặc log không được bảo vệ.
- Khi có thể, dùng endpoint private và danh tính dịch vụ thay vì cấp route rộng chỉ để truy cập một API.

## 15. Cloud NAT, Private Service Connect và dịch vụ được quản lý

Không phải mọi dịch vụ Google Cloud có private IP đều hoạt động giống một VM trong subnet. Khi thiết kế kết nối đến Cloud SQL, dịch vụ qua Private Services Access (PSA), Private Service Connect (PSC) hoặc dịch vụ quản lý khác, phải kiểm tra mô hình địa chỉ và route của dịch vụ đó.

| Thành phần | Vai trò và giới hạn quan trọng |
| --- | --- |
| Cloud NAT | Hỗ trợ một số workload đi ra ngoài mà không cần public IP; không tạo VPN hay tuyến inbound vào DC |
| Private Services Access | Kết nối riêng đến các dịch vụ Google được hỗ trợ qua service networking, có vùng địa chỉ allocated riêng |
| Private Service Connect | Mô hình endpoint hoặc dịch vụ xuất bản private theo loại sản phẩm; cần DNS và IAM/acceptance phù hợp |
| Serverless VPC Access / Direct VPC egress | Các cách để workload serverless dùng mạng VPC theo cấu hình và khả năng hỗ trợ |

Với Cloud Run truy cập database on-prem, cần kiểm tra cơ chế VPC egress, network, subnet và các route đến IP đích. Không giả định Cloud Run trực tiếp sử dụng địa chỉ mạng như một VM; hãy chọn Direct VPC egress hoặc cơ chế kết nối VPC được dịch vụ hỗ trợ rồi xác minh đường đi.

Với PSA hoặc PSC, phải xác định ai sở hữu endpoint, dải IP nào cần được định tuyến hoặc quảng bá và tính năng truy cập từ on-prem có được hỗ trợ không. Không tự quảng bá mọi service allocated range qua BGP chỉ vì thấy một địa chỉ private; hãy kiểm tra hướng dẫn định tuyến riêng của dịch vụ.

## 16. Ví dụ quy trình cấu hình và xác minh

Giả sử VPC prod-vpc ở region asia-southeast1 cần kết nối on-prem qua HA VPN. Phần dưới minh họa một số lệnh tạo thành phần nền tảng và quan sát trạng thái; đây **không phải** quy trình hoàn chỉnh để tạo hai gateway, tunnels và BGP peers.

Tạo Cloud Router và HA VPN gateway:

~~~bash
gcloud compute routers create prod-router \
  --project=PROJECT_ID \
  --network=prod-vpc \
  --region=asia-southeast1 \
  --asn=64514

gcloud compute vpn-gateways create prod-ha-vpn \
  --project=PROJECT_ID \
  --network=prod-vpc \
  --region=asia-southeast1
~~~

Cần bổ sung peer VPN gateway, external IP, shared secrets, tunnel mapping và BGP interfaces/peers theo topology cụ thể. Hai đầu phải thống nhất tham số tunnel, BGP peering addresses và route policy; không triển khai tunnel vào production từ một ví dụ thiếu thông số dự phòng.

Kiểm tra trạng thái Cloud Router:

~~~bash
gcloud compute routers get-status prod-router \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Liệt kê VPN tunnels trong region:

~~~bash
gcloud compute vpn-tunnels list \
  --project=PROJECT_ID \
  --filter="region:asia-southeast1"
~~~

Thông tin cần xác minh gồm phiên BGP ở trạng thái mong muốn, số lượng learned/advertised prefixes, next hop đúng và không có route không chủ ý. Sau đó chạy kiểm thử từ workload đến đúng IP ứng dụng đích. Trạng thái tunnel tốt chưa chứng minh port dịch vụ được cho phép.

Đối với DNS, xác minh riêng:

~~~bash
nslookup database.corp.example.com
nslookup api.gcp.corp.example.com
~~~

Khi cần kiểm tra cụ thể resolver:

~~~bash
dig @DNS_SERVER_IP database.corp.example.com A
dig @CLOUD_DNS_INBOUND_IP api.gcp.corp.example.com A
~~~

Những lệnh này chỉ là ví dụ chạy từ đúng máy/client có quyền và route tương ứng; tên và IP cần thay. Với hệ thống không có dig, sử dụng công cụ DNS tương đương. Kiểm tra cả việc kết nối TCP đến IP nhận được để phân biệt lỗi DNS và lỗi mạng.

## 17. Kiểm thử định tuyến, DNS và chuyển đổi dự phòng

Một checklist end-to-end nên đi từ phân giải tên đến kết nối ứng dụng, sau đó mới thử mất đường mạng.

| Test case | Cách thử | Kết quả mong muốn |
| --- | --- | --- |
| GCP đến DC qua IP | TCP tới một endpoint kiểm thử được cho phép | Thành công, xác định đúng source/destination |
| GCP đến DC qua tên | Resolver trong GCP truy vấn tên on-prem | Trả IP private đúng và kết nối thành công |
| DC đến GCP qua tên | Resolver DC truy vấn hậu tố GCP private | Trả bản ghi đúng từ Cloud DNS |
| Prefix chưa được phép | Thử nguồn hoặc đích ngoài policy | Bị chặn đúng ranh giới, có log khi phù hợp |
| Mất một tunnel/peer | Chuyển trạng thái tuyến thử nghiệm có kiểm soát | Route dự phòng được dùng theo thiết kế |
| Mất một DNS target | Ngừng target thử nghiệm theo quy trình | Resolver phục hồi theo cơ chế dự phòng đã cấu hình |
| Đổi bản ghi DNS | Hạ TTL có kế hoạch, thực hiện thay đổi | Client chuyển sang IP mới trong khoảng thời gian dự kiến |
| Lưu lượng cao | Tăng tải trong mức được phép | Không vượt băng thông, session hoặc quota đã cấp |
| Cắt đường rồi khôi phục | Quan sát route, latency và lỗi ứng dụng | Hệ thống không bị mắc kẹt trên tuyến sai |

Với thiết bị firewall stateful hoặc NAT, đường đi và đường về khác nhau có thể khiến kết nối TCP lỗi dù ICMP vẫn hoạt động ở một số vị trí. Sử dụng traceroute/tcpdump hoặc công cụ chẩn đoán tương đương tại các điểm được phép; kết hợp log firewall và BGP state để tìm vị trí rơi gói.

Network Intelligence Center và các công cụ chẩn đoán kết nối của Google Cloud có thể hỗ trợ phân tích cấu hình đường đi theo phạm vi hỗ trợ, nhưng kết quả mô phỏng không thay thế hoàn toàn kiểm thử end-to-end qua mạng đối tác. Cần quan sát cả log và metric của hệ thống on-prem hoặc cloud đối tác.

## 18. Giám sát độ tin cậy và xử lý sự cố

Quan sát kết nối hybrid nên có cả tín hiệu hạ tầng và tín hiệu ứng dụng:

- Trạng thái VPN tunnel, BGP sessions và sự thay đổi learned/advertised routes.
- Băng thông inbound/outbound, packet loss, RTT, jitter và tỷ lệ lỗi ứng dụng.
- Số lỗi DNS, DNS response latency, forwarding failures và tỷ lệ NXDOMAIN tăng bất thường.
- Firewall denies, NAT state, drop counters và những thay đổi policy gần thời điểm sự cố.
- SLO cho những hành trình quan trọng, chẳng hạn ứng dụng GKE truy cập database on-prem.

Ví dụ runbook khi ứng dụng không truy cập database qua tên:

1. Xác định DNS lookup trả NXDOMAIN, timeout hay IP không đúng.
2. Nếu DNS lỗi, truy vấn resolver được chỉ định; kiểm tra private/forwarding zone, target và đường UDP/TCP 53.
3. Nếu DNS trả IP đúng, thử kết nối trực tiếp đến IP và port.
4. Kiểm tra BGP session, learned routes, route priority và đường trả về.
5. Kiểm tra firewall ở cả GCP và DC, cũng như NAT hoặc stateful inspection.
6. Đối chiếu thời điểm bắt đầu lỗi với thay đổi DNS TTL, VPN, route advertisement hoặc workload scaling.
7. Nếu vấn đề liên quan một đường, chuyển sang phương án dự phòng theo runbook và giám sát dịch vụ sau chuyển đổi.

Không giải quyết sự cố bằng cách mở tạm toàn bộ firewall hoặc quảng bá default route nếu chưa xác định rõ phạm vi ảnh hưởng. Các thay đổi khẩn cấp cần có người duyệt, ghi log, thời hạn và kế hoạch hoàn nguyên.

## 19. Chi phí, độ trễ và vận hành dài hạn

Hạ tầng kết nối có chi phí cố định và chi phí theo lưu lượng. VPN có thể phát sinh phí tunnel và dữ liệu; Interconnect có phí kết nối/attachment và truyền dữ liệu; nhà cung cấp đối tác có phí riêng. Chi phí còn xuất hiện do lưu lượng giữa region/cloud, DNS queries và hệ thống giám sát.

Khi lựa chọn kiến trúc, hãy đánh giá:

- Chi phí đường truyền chính/dự phòng và khả năng mở rộng băng thông.
- Lưu lượng egress giữa cloud với on-prem hoặc giữa các cloud.
- Mức RTT và tác động đến những giao thức nhiều vòng trao đổi, như database transaction.
- Số DNS forwarding queries, hiệu quả caching và sức tải resolver phía đối tác.
- Chi phí vận hành nhiều router, BGP peers, firewall policies và cấu hình ở hai hoặc nhiều cloud.
- Mức phụ thuộc nhà cung cấp, độ khó failover, khả năng rollback và người trực on-call.

Không phải lưu lượng nào cũng nên chạy xuyên môi trường thời gian thực. Với analytics hoặc dữ liệu khối lượng lớn, có thể cân nhắc đồng bộ theo lô, event-driven hoặc dịch vụ truyền dữ liệu phù hợp thay vì để mỗi request người dùng đi qua đường liên kết xa. Điều này giảm số lần round trip và giúp tách failure domain.

Một phương án có băng thông rất lớn nhưng DNS và ứng dụng không có khả năng failover vẫn có thể kém tin cậy. Chi phí nên được đánh giá cùng SLO và mức độ phục hồi, không chỉ đơn giá trên mỗi GB.

## 20. Bài thực hành: thiết kế truy cập database hybrid

**Tình huống:** công ty duy trì database nội bộ tại DC, còn một API Spring Boot chạy trên GKE tại Google Cloud. API phải kết nối database bằng tên database.corp.example.com và cần cho nhóm vận hành DC truy vấn một endpoint quản trị private của GCP qua tên admin.gcp.corp.example.com.

**Yêu cầu giả định:**

- GCP production dùng subnet 10.20.10.0/24; database DC nằm tại 10.10.20.15.
- Không truy cập database từ staging hoặc từ internet public.
- Có hai đường kết nối độc lập theo điều kiện kỹ thuật khả thi.
- Mất một đường phải có quy trình failover; sự cố DNS không được gây vòng lặp.
- Mọi thay đổi cấu hình route và DNS đều có người sở hữu và cách rollback.

Hãy xây dựng:

1. Bảng IPAM bao gồm primary/secondary ranges và những dải được quảng bá.
2. Sơ đồ hai đường kết nối, vị trí Cloud Router/BGP peers, firewall và resolver.
3. Danh sách route GCP cần học từ DC và route DC cần học từ GCP.
4. Ma trận firewall từ subnet ứng dụng đến database và giữa hai hệ DNS.
5. Private DNS zone gcp.corp.example.com., forwarding zone corp.example.com. và conditional forwarder tại DC.
6. Bộ test có phân biệt IP connectivity, DNS resolution, TCP ứng dụng và failover.
7. Danh sách metric, alert, chi phí và phương án hoàn nguyên khi cutover thất bại.

**Tiêu chí đánh giá:** thiết kế không có CIDR chồng lấp; route đi/về rõ ràng; DNS mỗi namespace có một nguồn authoritative; không quảng bá tuyến rộng không cần thiết; có đường dự phòng thực tế; policy chỉ cho phép nguồn và cổng cần thiết; kiểm thử chứng minh ứng dụng hoạt động bằng tên chứ không chỉ ping theo IP.

## 21. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra subnet primary mà quên GKE secondary/PSA | CIDR chồng lấp, đường đi sai | Tập trung IPAM cho mọi dải địa chỉ |
| Có hai VPN tunnels nhưng cùng một điểm lỗi | Mất một thiết bị vẫn mất toàn bộ kết nối | Thiết kế các miền lỗi và đường dự phòng thực sự |
| Cho rằng BGP UP thì ứng dụng hoạt động | DNS/firewall hoặc port vẫn có thể lỗi | Kiểm thử end-to-end theo ứng dụng |
| Dùng default route để sửa thiếu một prefix | Traffic không liên quan bị chuyển hướng | Quảng bá prefix tối thiểu và kiểm tra route tables |
| Cho rằng VPC Peering tự bắc cầu | Workload không tới được VPC thứ ba | Dùng topology/routing được hỗ trợ rõ ràng |
| Private DNS zone chỉ gắn vào một VPC | VPC khác không tìm thấy tên | Kiểm tra authorization, DNS peering/forwarding |
| Forwarding DNS hai chiều vô điều kiện | Truy vấn vòng lặp, timeout | Xác định một authoritative owner cho mỗi namespace |
| Chỉ mở UDP 53 hoặc quên return route | Một số truy vấn DNS thất bại | Kiểm tra TCP/UDP, nguồn forwarding, định tuyến hai chiều |
| Không xét firewall stateful hoặc NAT | Đường về khác làm kết nối bị rớt | Xác minh symmetry/translation và state |
| Chỉ đo latency nội bộ GCP | Bỏ qua RTT sang DC và cloud khác | Đo hành trình ứng dụng từ nguồn thật |
| Thiếu diễn tập failover | Đường dự phòng chỉ tồn tại trên giấy | Tập kiểm thử định kỳ với điều kiện dừng an toàn |

## 22. Checklist thiết kế trước khi đưa vào production

- Có sơ đồ môi trường, nguồn/đích và nhu cầu ứng dụng được phê duyệt.
- IPAM bao gồm VPC subnets, GKE secondary ranges, PSA/PSC endpoints và mạng đối tác.
- Chọn công nghệ kết nối theo băng thông, bảo mật, khả năng hỗ trợ và chi phí.
- Các kết nối dự phòng không chia sẻ một điểm lỗi không chấp nhận được.
- BGP ASN, peers, learned/advertised prefixes và routing mode được tài liệu hóa.
- Route đi/về được xác minh, không dùng route rộng khi chỉ cần vài dải IP.
- Không giả định VPC Peering hay multicloud gateway tự định tuyến bắc cầu.
- Namespace DNS có chủ sở hữu rõ, private/forwarding/peering zones đúng phạm vi.
- On-prem resolver và Cloud DNS inbound/outbound forwarding có return routing phù hợp.
- Đã kiểm tra firewall, DNS UDP/TCP 53, ứng dụng và cơ chế xác thực.
- Đã kiểm thử failover, sự cố DNS, thay đổi TTL, traffic spike và khôi phục tuyến.
- Có dashboard, alert, runbook, change review và người chịu trách nhiệm on-call.
- Có ước lượng chi phí đường kết nối, lưu lượng, DNS và mô hình vận hành.
- Không có tuyến, bản ghi hoặc quyền tạm nào bị bỏ lại sau thử nghiệm.

Thiết kế kết nối hybrid và multicloud đáng tin cậy là sự phối hợp của ba mặt phẳng: mạng có thể truyền gói, định tuyến chọn đúng đường và DNS trả đúng địa chỉ dịch vụ. Với Google Cloud, HA VPN hoặc Interconnect cung cấp nền kết nối, Cloud Router trao đổi thông tin route, Cloud DNS giúp các môi trường tìm đúng tên, còn firewall, IAM và kiểm thử end-to-end bảo vệ hành trình ứng dụng. Khi mỗi dải IP, prefix, namespace và đường dự phòng đều có chủ sở hữu cùng bằng chứng kiểm thử, doanh nghiệp có thể mở rộng hạ tầng xuyên môi trường mà vẫn kiểm soát rủi ro vận hành.
