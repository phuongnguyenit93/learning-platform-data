# Tìm nguyên nhân lỗi firewall, NAT và truy cập Google APIs

Một ứng dụng chạy trên Compute Engine, GKE hoặc Cloud Run có thể gọi dịch vụ bên ngoài thành công ở môi trường thử nghiệm nhưng lại timeout ở production. Lỗi thường bị quy kết ngay cho firewall, mặc dù nguyên nhân thực tế có thể là DNS trả sai địa chỉ, không có route ra ngoài, Cloud NAT không bao phủ subnet, chưa bật Private Google Access, proxy bị cấu hình nhầm hoặc danh tính ứng dụng thiếu quyền gọi Google API.

Khắc phục hiệu quả không phải là mở toàn bộ egress hay cấp role Owner cho service account. Người vận hành cần xác định **request xuất phát từ đâu, đi đến endpoint nào, được định tuyến qua đâu và thất bại ở lớp nào**. Bài học này trình bày quy trình điều tra có thể tái lập trên Google Cloud, các công cụ quan sát, ví dụ lệnh chỉ đọc và những tình huống thường gặp. Mục tiêu là tìm đúng lỗi với bằng chứng, chỉ thay đổi cấu hình nhỏ nhất cần thiết, rồi xác minh việc phục hồi và ranh giới bảo mật.

## 1. Nhận diện đúng lớp gây lỗi

Một lời gọi HTTP đến Google API đi qua nhiều lớp. Các lỗi ở các lớp khác nhau có thể tạo thông báo gần giống nhau trong log của ứng dụng.

| Lớp | Câu hỏi cần trả lời | Triệu chứng thường gặp |
| --- | --- | --- |
| Nguồn yêu cầu | VM, Pod hay Cloud Run revision nào phát sinh lỗi? | Chỉ một môi trường hoặc một nhóm instance lỗi |
| DNS | Tên API có phân giải thành IP dự kiến không? | Không resolve, NXDOMAIN hoặc trả endpoint sai |
| Route | VPC/subnet có đường đi phù hợp đến IP đích không? | Timeout dù DNS đã trả IP |
| Firewall / network policy | Lưu lượng từ nguồn đến đích trên cổng cần thiết có được cho phép không? | Bị chặn hoặc timeout tùy đường đi |
| NAT / private access | Nguồn không có external IP có lối ra tương ứng không? | Mất kết nối internet hay chỉ một số API |
| TLS / proxy | Có bắt tay TLS đúng hostname và CA không? | Lỗi certificate, proxy, handshake |
| IAM / API control | Principal có quyền truy cập API/resource không? | HTTP 401/403, permission denied |
| Quota / service state | API có từ chối do giới hạn hoặc sự cố không? | HTTP 429, RESOURCE_EXHAUSTED, 5xx |

**Lỗi HTTP 403 không tự động là lỗi firewall.** Nếu client nhận được một HTTP response hoàn chỉnh từ Google API, thường đã có kết nối ở tầng mạng và TLS đến một endpoint. Tiếp theo cần kiểm tra IAM, phạm vi OAuth, API enabled, VPC Service Controls, organization policy hoặc quy tắc truy cập của dịch vụ. Ngược lại, timeout kết nối TCP có thể xuất phát từ firewall, route, NAT, DNS, proxy hoặc endpoint không phản hồi; không thể chẩn đoán chỉ từ một dòng lỗi.

## 2. Quy trình điều tra từ ngoài vào trong

Sử dụng một test request nhất quán để kiểm tra từng chặng:

~~~mermaid
flowchart TD
  A["Ứng dụng gọi Google API thất bại"] --> B{"DNS phân giải đúng?"}
  B -->|"Không"| D["Kiểm tra resolver, private zone, forwarding, proxy"]
  B -->|"Có"| C{"TCP/TLS tới endpoint hoạt động?"}
  C -->|"Không"| E["Kiểm tra route, firewall, NAT, PGA, egress path"]
  C -->|"Có"| F{"Nhận HTTP/gRPC status?"}
  F -->|"401/403"| G["Kiểm tra identity, IAM, scopes, VPC SC, API enabled"]
  F -->|"429/5xx"| H["Kiểm tra quota, retry, trạng thái API"]
  F -->|"2xx/3xx/4xx khác"| I["Đối chiếu semantics API và payload"]
  D --> J["Sửa đúng một thành phần rồi thử lại"]
  E --> J
  G --> J
  H --> J
  I --> J
  J --> K["Kiểm tra chức năng và telemetry sau thay đổi"]
~~~

Đừng thay cả DNS, route, firewall và IAM trong cùng một lần. Nếu nhiều thứ thay đổi đồng thời, không thể xác định biện pháp nào đã sửa lỗi, đồng thời rất dễ để lại một rule cho phép quá rộng.

## 3. Ghi nhận phạm vi và bằng chứng trước khi thao tác

Mỗi incident nên có một bản ghi tối thiểu:

- **Nguồn:** project, VPC, subnet, region/zone, VM hoặc cluster/Pod/service, network interface, địa chỉ nguồn.
- **Đích:** FQDN, IP kết quả DNS, cổng, giao thức, Google API/resource và phương thức gọi.
- **Thời gian:** thời điểm lỗi đầu tiên, tính lặp lại, vùng ảnh hưởng và những thay đổi gần nhất.
- **Triệu chứng:** lỗi DNS, timeout, TCP reset, TLS error, HTTP status hoặc gRPC status.
- **Đường egress:** external IP, Cloud NAT, Private Google Access, Private Service Connect, VPC connector hay Direct VPC egress.
- **Identity:** service account, scopes khi còn áp dụng, IAM roles, VPC Service Controls và organization policies.
- **Quan sát:** request ID, log ứng dụng, VPC Flow Logs, Firewall Rules Logging, Cloud NAT logs và API audit logs khi có.

Đặc biệt với Shared VPC, một workload thuộc **service project** có thể sử dụng subnet, firewall và NAT của **host project**. Chỉ kiểm tra firewall ở project chạy ứng dụng sẽ bỏ sót cấu hình thực tế của mạng.

Không in access token, service account key hay secret vào log sự cố. Ghi principal email và resource path khi phù hợp, không ghi credential.

## 4. Hiểu đường đi mạng: VM, Pod và serverless

Trước khi điều tra firewall, hãy xác định IP nào thực sự xuất hiện trên mạng.

| Workload | Đường mạng cần hiểu | Điểm hay bị bỏ sót |
| --- | --- | --- |
| Compute Engine có external IPv4 | VM giao tiếp qua VPC, có đường egress sử dụng external IP | Không mặc định dùng Cloud NAT cho VM đó |
| Compute Engine không có external IPv4 | Có thể dùng Cloud NAT cho internet, Private Google Access cho Google APIs | NAT chưa cấu hình đúng subnet/region; PGA bị tắt |
| GKE Standard / VPC-native | Pod IP, node IP và SNAT phụ thuộc CNI, ip-masq config, network policy | NAT thiếu dải nguồn thực tế hoặc Pod bị chặn egress |
| GKE Autopilot | Network path do GKE và cấu hình cluster quyết định | Không dùng giả định về node giống Standard khi chưa kiểm tra |
| Cloud Run | Có cơ chế egress của nền tảng hoặc VPC egress cấu hình riêng | Trộn lẫn private-ranges-only với all-traffic |
| Workload on-premises | VPN/Interconnect, DNS forwarding và các tuyến/endpoint phù hợp | Đường về, chính sách resolver và quảng bá prefix |

**Cloud NAT không phải một proxy đi qua như một hop riêng trong traceroute.** Nó thực hiện dịch địa chỉ theo các điều kiện hỗ trợ; thiếu biểu tượng NAT trong traceroute không chứng minh NAT không hoạt động.

## 5. DNS: kiểm tra hostname trước IP

Một ứng dụng gọi storage.googleapis.com hoặc một API khác thường bắt đầu từ DNS. Kết quả có thể là địa chỉ public thông thường, dải riêng dành cho truy cập Google APIs hoặc địa chỉ nội bộ của Private Service Connect, tùy kiến trúc.

Các bước:

1. Truy vấn FQDN từ **cùng môi trường đang lỗi**, không chỉ từ laptop.
2. Ghi resolver đang dùng và mọi CNAME/A/AAAA được trả về.
3. Kiểm tra private Cloud DNS zones, forwarding/peering zones và chính sách DNS nếu có.
4. Xác nhận endpoint thực tế đúng kiến trúc egress đã thiết kế.
5. Kiểm tra proxy hoặc custom DNS trong container có làm thay đổi đích không.

Ví dụ trên Linux worker:

~~~bash
getent ahostsv4 storage.googleapis.com
dig storage.googleapis.com A
dig +short storage.googleapis.com A
cat /etc/resolv.conf
~~~

Nếu công cụ dig không được cài, dùng nslookup hoặc công cụ DNS tương đương. Trên Kubernetes, /etc/resolv.conf thường trỏ đến resolver của cluster hoặc một cơ chế DNS được cấu hình; phải xét CoreDNS/Cloud DNS hoặc NodeLocal DNSCache theo kiến trúc thực tế.

**Không kết luận firewall lỗi khi lệnh dig trả NXDOMAIN hoặc phân giải sai tên.** Trước tiên phải tìm nguyên nhân DNS. Trái lại, phân giải thành công chỉ xác nhận có IP, chưa chứng minh TCP/TLS đến IP đó đi được.

## 6. Route: kiểm tra cả đích và next hop

Sau DNS, hệ thống cần có tuyến đến IP đích. Với VM không có external IP nhưng cần truy cập Google APIs qua Private Google Access, kiến trúc thường sử dụng tuyến đến địa chỉ Google API qua **default internet gateway** của VPC, mặc dù traffic đến các VIP chuyên dụng vẫn đi qua mạng Google theo cơ chế sản phẩm.

Những câu hỏi cần kiểm tra:

- Có route mặc định 0.0.0.0/0 hoặc route cụ thể tới dải IP đích không?
- Next hop có đúng thiết kế không, hay traffic bị đưa qua VPN, appliance hoặc endpoint khác?
- Route động hoặc route do network policy có đang thay thế đường mặc định không?
- Với subnet trong Shared VPC, đang xem đúng VPC/host project chưa?
- Nếu qua mạng hybrid, đường về cho nguồn yêu cầu có tồn tại không?

Lệnh chỉ đọc:

~~~bash
gcloud compute routes list \
  --project=HOST_PROJECT_ID \
  --filter="network:VPC_NAME" \
  --format="table(name,destRange,priority,nextHopGateway,nextHopInstance)"
~~~

Kết quả gcloud routes list không hiển thị mọi ngữ nghĩa định tuyến đặc biệt hoặc thứ tự lựa chọn tuyến theo mọi loại next hop. Khi cần, dùng **Connectivity Tests** và công cụ xem effective routes của Google Cloud phù hợp với resource/phiên bản để phân tích. Không thêm 0.0.0.0/0 bừa bãi chỉ để thử, đặc biệt trong mạng có egress tập trung hoặc VPC Service Controls.

## 7. Firewall VPC: stateful nhưng không phải ai cũng được vào

VPC firewall rules và network firewall policies quyết định lưu lượng được cho phép/chặn theo direction, priority, target, source/destination, protocol và port. Ở VPC không có rule/policy thay thế tương ứng, Google Cloud có những implied rules như **deny ingress** và **allow egress** theo hành vi nền tảng. Default VPC còn có các rule được tạo sẵn, không nên nhầm với implied rules.

Cần kiểm tra:

- Egress rule có thực sự cho phép TCP 443 từ đúng nguồn đến IP/API đích không?
- Ingress có cần không? Với kết nối được phép do VM khởi tạo, firewall VPC có theo dõi trạng thái phiên; không tự tạo rule ingress rộng chỉ để trả response.
- Rule áp cho toàn mạng hay chỉ VM có network tag/service account target cụ thể?
- Có rule deny có độ ưu tiên cao hoặc policy tổ chức/folder/network chặn trước không?
- Workload có thêm Kubernetes NetworkPolicy, host firewall hoặc service mesh policy không?
- Logging đã bật trên rule phù hợp chưa, và log có lưu sự kiện đã chọn không?

Trong VPC firewall rules, priority số nhỏ hơn có độ ưu tiên cao hơn trong cùng cơ chế đánh giá. Tuy nhiên, **không nên suy luận toàn bộ thứ tự hiệu lực chỉ từ danh sách VPC firewall rules** khi môi trường dùng hierarchical firewall policies và network firewall policies. Hãy xem effective firewall policy theo đường đi hiện hành.

## 8. Kiểm tra firewall bằng CLI và Connectivity Tests

Một số lệnh **chỉ đọc**:

~~~bash
gcloud compute firewall-rules list \
  --project=HOST_PROJECT_ID \
  --filter="network:VPC_NAME"

gcloud compute instances describe VM_NAME \
  --project=SERVICE_PROJECT_ID \
  --zone=ZONE \
  --format="yaml(networkInterfaces,tags,serviceAccounts)"
~~~

Thông tin network tags và service accounts trên VM giúp xác định rule nào có thể áp dụng. Nếu rule target service account hoặc secure tag, phải kiểm tra đúng selector; không chỉ xem source IP.

**Network Intelligence Center – Connectivity Tests** có thể phân tích cấu hình mạng cho một cặp nguồn/đích và nêu nguyên nhân dự đoán như thiếu route hoặc firewall deny trong phạm vi công cụ hỗ trợ. Đây là công cụ rất hữu ích để thu hẹp nghi vấn nhưng không thay thế một lời gọi thực tế: nó có thể không quan sát được toàn bộ tình trạng ứng dụng, TLS, permission, DNS động hoặc thiết bị ngoài Google Cloud.

Firewall Rules Logging chỉ có dữ liệu khi được bật trên rule/phạm vi tương ứng và log có thể không bao phủ mọi packet. VPC Flow Logs cũng phụ thuộc cấu hình bật log, sampling, aggregation và resource hỗ trợ. **Không có log không đồng nghĩa traffic chưa từng tồn tại**.

## 9. Cloud NAT giải quyết vấn đề nào?

Cloud NAT cho phép những workload đủ điều kiện không có external IPv4 khởi tạo kết nối ra ngoài thông qua cơ chế dịch địa chỉ. Public NAT được cấu hình theo **region** và gắn với Cloud Router như thành phần cấu hình điều khiển; Cloud Router ở đây không trở thành thiết bị chuyển tiếp mọi packet NAT.

Những điều quan trọng:

| Điểm kiểm tra | Ý nghĩa |
| --- | --- |
| Region | NAT phải phù hợp với region của nguồn cần phục vụ |
| VPC/subnet | Đúng subnet nguồn và loại dải IP được NAT bao phủ |
| NAT IP allocation | Có địa chỉ external NAT hợp lệ và đủ công suất |
| Port allocation | Đủ các cổng dịch địa chỉ cho lượng connection hiện tại |
| Egress route | Có đường next hop phù hợp để traffic dùng cơ chế NAT |
| Logging | Bật log phù hợp để quan sát translation/error khi cần |
| Source identity | Không nhầm node IP, Pod IP và serverless egress IP |

Cloud NAT không phải cách để client internet tự mở kết nối TCP mới vào một VM private. Nó không thay thế external load balancer, proxy hay thiết kế ingress. Một VM đã có external IP thường không dùng Cloud NAT cho chính luồng IPv4 egress đó.

**Public NAT và Private NAT là các cơ chế khác nhau** trong hệ sinh thái Cloud NAT. Khi điều tra truy cập Google APIs hoặc internet qua địa chỉ public, phải xác định đang dùng loại NAT nào và nguồn/đích có nằm trong phạm vi hỗ trợ của nó không.

## 10. Tìm lỗi Cloud NAT theo thứ tự

Một VM private có route ra internet nhưng không truy cập được website public. Trước khi thêm firewall, hãy đối chiếu:

1. VM có external IP không? Nếu có, xác định đường egress thực, không mặc định NAT.
2. VM ở region/subnet nào? NAT đang gắn VPC và region tương ứng không?
3. NAT bao phủ all primary subnet IP ranges hay một danh sách subnet/range cụ thể?
4. Với GKE, traffic đã được SNAT sang node IP hay vẫn giữ Pod secondary IP?
5. NAT dùng cấp IP tự động hay thủ công? Có thiếu địa chỉ/port allocation không?
6. Có route hoặc policy nào đổi next hop sang appliance/VPN ngoài ý muốn không?
7. Cloud NAT logs/metrics có dấu hiệu hết port, packet drop hoặc mapping không?

Lệnh kiểm tra một NAT được đặt tên:

~~~bash
gcloud compute routers nats describe NAT_NAME \
  --project=HOST_PROJECT_ID \
  --router=ROUTER_NAME \
  --region=REGION
~~~

Đừng sửa **min ports per VM**, dynamic port allocation hoặc thêm NAT IP trong lúc chưa biết giới hạn nào đang xảy ra. NAT port exhaustion có triệu chứng khác với DNS sai hoặc thiếu route. Khi connection rate tăng hoặc có nhiều kết nối tới cùng endpoint, cần xem NAT logs/metrics, số endpoint và kiểu traffic (TCP/UDP, thời gian giữ kết nối) để chọn giải pháp hợp lý.

## 11. Private Google Access không đồng nghĩa Cloud NAT

**Private Google Access (PGA)** cho phép các nguồn đủ điều kiện không có external IP trong subnet truy cập Google APIs và services được hỗ trợ thông qua đường truy cập của Google Cloud, nếu DNS và route được cấu hình phù hợp. Truy cập Google APIs qua PGA **không đòi hỏi tạo Cloud NAT** chỉ vì VM không có public IPv4.

Sự khác biệt:

| Nhu cầu | Thành phần thường liên quan |
| --- | --- |
| VM private truy cập một website internet public không thuộc Google APIs | Public Cloud NAT hoặc phương án egress tương đương |
| VM private gọi Google APIs được hỗ trợ | Private Google Access cùng DNS/route phù hợp |
| Cần kiểm soát truy cập Google APIs theo VPC Service Controls | Có thể dùng restricted.googleapis.com và perimeter khi phù hợp |
| Muốn truy cập Google APIs qua endpoint private trong VPC | Private Service Connect endpoint cho Google APIs nếu sản phẩm hỗ trợ |
| On-prem gọi Google APIs qua hybrid network | Đường kết nối, route/DNS và phương án private access được hỗ trợ |

Không suy ra từ câu “Cloud NAT đang hoạt động” rằng cấu hình PGA, VPC SC hoặc IAM cũng chính xác. Chúng là các lớp độc lập.

Đọc cấu hình của subnet:

~~~bash
gcloud compute networks subnets describe SUBNET_NAME \
  --project=HOST_PROJECT_ID \
  --region=REGION \
  --format="yaml(name,network,ipCidrRange,privateIpGoogleAccess)"
~~~

Nếu privateIpGoogleAccess là false, cần đối chiếu thiết kế: workload có external IP/egress riêng hay đang kỳ vọng dùng PGA? Chỉ thay đổi sau khi xác nhận đây là root cause và đánh giá tác động subnet.

## 12. private.googleapis.com và restricted.googleapis.com

Google Cloud cung cấp các domain đặc biệt cho một số mô hình private access:

- **private.googleapis.com** sử dụng VIP IPv4 **199.36.153.8/30** và cung cấp đường truy cập riêng tới phần lớn Google APIs/services được hỗ trợ.
- **restricted.googleapis.com** sử dụng VIP IPv4 **199.36.153.4/30** và nhằm truy cập tập API hỗ trợ VPC Service Controls theo mô hình restricted access.

Đây là **địa chỉ IP public được dành riêng cho dịch vụ truy cập Google APIs**, không phải RFC 1918. Cơ chế truy cập và tuyến đi trên mạng Google không được đánh giá chỉ qua việc IP có nằm trong dải 10.0.0.0/8 hay không.

Một kiến trúc có thể dùng private Cloud DNS zone để hướng các tên Google API phù hợp về một trong các VIP. Ví dụ về bản ghi cần kiểm chứng ở DNS:

~~~text
private.googleapis.com.       A      199.36.153.8
private.googleapis.com.       A      199.36.153.9
private.googleapis.com.       A      199.36.153.10
private.googleapis.com.       A      199.36.153.11
*.googleapis.com.             CNAME  private.googleapis.com.
~~~

Đây là sơ đồ bản ghi minh họa cho phương án private.googleapis.com, **không phải hướng dẫn thay hàng loạt DNS production**. Phải kiểm tra domain nào sử dụng googleapis.com, cách xử lý domain khác, zone scope và những tên/khả năng truy cập được sản phẩm hỗ trợ. Phương án restricted sẽ dùng endpoint và VIP khác; không nên đổi toàn bộ workload sang restricted khi chưa kiểm tra API có hỗ trợ VPC Service Controls.

Khi dùng các VIP này, cần có DNS, route đến dải đích qua next hop được hỗ trợ, egress firewall và Private Google Access theo nguồn/workload thực tế. Một CNAME đúng nhưng không có route/permission tương ứng vẫn khiến request thất bại.

## 13. DNS bị override sai: lỗi rất dễ nhầm với NAT

Giả sử ứng dụng chỉ không truy cập được storage.googleapis.com sau khi nhóm mạng thêm private DNS zone cho googleapis.com. Một vài nguyên nhân:

- Wildcard CNAME trỏ về một đích không tồn tại hoặc sai dấu chấm cuối FQDN.
- Private zone gắn vào VPC khác, không phải VPC đang thực hiện truy vấn.
- Có forwarding zone hoặc peering zone ưu tiên một namespace khác dự kiến.
- Resolver trong Pod hoặc host dùng custom DNS server không có zone tương ứng.
- Thay đổi DNS chưa hết TTL, client giữ connection cũ hoặc kết quả negative caching.
- Dùng restricted.googleapis.com cho một API không nằm trong tập hỗ trợ hoặc bị VPC SC từ chối.

Không dùng cách tắt firewall để “thử DNS”. Hãy truy vấn từ đúng Pod/VM, so sánh kết quả với cấu hình zone và kiểm tra route đến IP được trả về. Với ứng dụng dùng custom HTTP proxy, proxy có thể phân giải DNS thay client; cần test tại **đúng nơi thực hiện phân giải**.

Lệnh chỉ đọc kiểm tra private zone:

~~~bash
gcloud dns managed-zones list --project=DNS_PROJECT_ID

gcloud dns record-sets list \
  --project=DNS_PROJECT_ID \
  --zone=GOOGLEAPIS_PRIVATE_ZONE
~~~

Tên zone không quyết định VPC nào được ủy quyền truy vấn; cần xem chi tiết visibility và networks của zone khi cần.

## 14. Private Service Connect, Private Services Access và Google API endpoints

Ba cơ chế thường bị nhầm:

| Cơ chế | Bài toán giải quyết | Không nên hiểu nhầm |
| --- | --- | --- |
| Private Google Access | Nguồn đủ điều kiện không có external IP truy cập Google APIs qua đường được hỗ trợ | Không phải NAT cho mọi website internet |
| Private Service Connect (PSC) | Tạo endpoint/service attachment theo loại dịch vụ, kể cả endpoint cho Google APIs trong cấu hình hỗ trợ | Không tự cấp IAM trên API và không thay thế DNS |
| Private Services Access (PSA) | Kết nối riêng tới các producer services được hỗ trợ qua service networking | Không phải cùng cách hoạt động với PSC endpoint |

Với PSC cho Google APIs, có thể cần DNS override trỏ FQDN API đến endpoint IP nội bộ. Khi đó kiểm tra **địa chỉ endpoint, trạng thái, phạm vi global/regional tùy sản phẩm, DNS, route/firewall và API bundle**. Một endpoint PSC tồn tại không đồng nghĩa mọi API đều được hỗ trợ hoặc yêu cầu đã qua IAM.

Không khắc phục một vấn đề PSC bằng cách bật thêm Cloud NAT nếu đường dự kiến là private endpoint trong VPC. Trước tiên phải chứng minh request đang đi đúng IP endpoint đã cấu hình.

## 15. Truy cập Google APIs còn phụ thuộc IAM, scopes và VPC SC

Sau khi kết nối HTTPS thành công, Google API vẫn có thể từ chối request. Những nguyên nhân phổ biến:

1. **API chưa được bật** trong project phù hợp, tùy API và mô hình sử dụng.
2. **Service account thiếu role/permission** trên project, bucket, dataset, secret hoặc resource đích.
3. **OAuth access scope** trên một số VM/credential path còn giới hạn dù IAM role cho phép.
4. **VPC Service Controls** không cho phép truy cập theo perimeter, ingress/egress rules hoặc API support.
5. **Organization policy** hoặc chính sách dịch vụ chặn thao tác.
6. **Quota/billing** hoặc yêu cầu API sai.

Ví dụ, một VM dùng PGA có thể hoàn tất TLS đến Cloud Storage nhưng nhận HTTP 403 khi đọc bucket riêng. Khi đó thêm Cloud NAT hoặc mở firewall không cấp thêm quyền đọc bucket. Phải xem principal, IAM role của bucket/project và thông tin lỗi API.

Mã lỗi cũng cần được diễn giải theo body và dịch vụ:

| Kết quả | Diễn giải ban đầu |
| --- | --- |
| DNS NXDOMAIN / name not resolved | Kiểm tra DNS trước |
| TCP connection timeout | Kiểm tra route, firewall, NAT, proxy và endpoint |
| TLS certificate error | Kiểm tra hostname, trust store, TLS interception và thời gian hệ thống |
| HTTP 401 | Credential thiếu/hết hạn/không hợp lệ hoặc sai phương thức xác thực |
| HTTP 403 | IAM, VPC SC, API disabled hoặc chính sách dịch vụ tùy thông điệp lỗi |
| HTTP 429 | Rate limit/quota hoặc bảo vệ quá tải |
| HTTP 5xx | Sự cố dịch vụ, network trung gian hoặc lỗi từ server, cần correlation ID |

Không lấy bảng này làm quy tắc tuyệt đối; xem mã gRPC, error details, audit logs và phương thức cụ thể để xác định nguyên nhân.

## 16. Kiểm tra TCP và TLS bằng probe không phá dữ liệu

Kiểm tra từ chính nguồn đang lỗi:

~~~bash
curl -sv \
  --connect-timeout 5 \
  --max-time 15 \
  https://storage.googleapis.com/ \
  -o /dev/null

openssl s_client \
  -connect storage.googleapis.com:443 \
  -servername storage.googleapis.com \
  -brief
~~~

Một phản hồi HTTP 400/403/404 ở endpoint thử nghiệm vẫn có thể chứng minh rằng DNS/TCP/TLS đã hoàn tất, nhưng **không chứng minh quyền dùng API của ứng dụng**. Với curl, hãy ghi response code, thời điểm, remote IP, TLS error và proxy settings; không đăng access token ra log.

Không dùng cờ bỏ kiểm tra chứng chỉ TLS như giải pháp production. Nếu TLS lỗi, cần xác định đúng certificate chain, hostname, CA trust, proxy interception hoặc đồng hồ hệ thống.

Với gRPC, sử dụng công cụ phù hợp với giao thức và endpoint. Nếu mạng thông thì chuyển sang điều tra status code và quyền; không tiếp tục đoán firewall.

## 17. Compute Engine: ví dụ VM private không gọi được API

**Tình huống:** VM không có external IPv4 tại asia-southeast1 muốn đọc Cloud Storage; curl timeout.

Quy trình:

1. Xem networkInterfaces của VM để xác nhận VPC/subnet, external IP và network tags.
2. Kiểm tra DNS của storage.googleapis.com ngay trên VM.
3. Đối chiếu IP đích: VIP private/restricted, PSC IP hay endpoint mặc định.
4. Kiểm tra subnet có bật PGA nếu kiến trúc dự kiến dùng PGA.
5. Kiểm tra route đến đích và egress firewall/policies.
6. Nếu luồng thực tế đi internet public, xác định có cần Public Cloud NAT và NAT bao phủ subnet không.
7. Chạy curl/openssl không có credential để xác nhận TLS; sau đó gọi API với danh tính VM theo phương pháp xác thực an toàn.
8. Nếu chỉ thao tác đọc bucket thất bại, kiểm tra IAM/scopes và VPC Service Controls.

Không tạo external IP hoặc cấp Editor cho VM như biện pháp “sửa nhanh”. Những thay đổi đó mở rộng bề mặt tấn công và có thể che mất nguyên nhân gốc.

## 18. GKE: Pod IP, node IP và NetworkPolicy

Với GKE VPC-native, Pod IP có thể đến từ secondary range, còn node IP đến từ primary range. Egress của Pod có thể được SNAT sang node IP hoặc giữ nguyên source Pod IP tùy cơ chế masquerade, CNI và cấu hình cụ thể. Cloud NAT phải hỗ trợ **nguồn thực tế** mà traffic sử dụng; không nhất thiết chỉ cần cấu hình primary range trong mọi trường hợp.

Triệu chứng điển hình:

- Node có thể truy cập API nhưng Pod không: kiểm tra DNS trong Pod, NetworkPolicy, service mesh, proxy và egress SNAT.
- Một namespace lỗi, namespace khác bình thường: xem NetworkPolicy và identity khác nhau.
- Pod chỉ lỗi khi cluster scale lớn: xem Cloud NAT port allocation, connection rate, quota và số Pod/node mới.
- Pod nhận HTTP 403 khi gọi API: xem Workload Identity Federation for GKE, quyền service account, VPC SC và phạm vi tài nguyên.

Lệnh chỉ đọc:

~~~bash
kubectl get pods -n APP_NAMESPACE -o wide
kubectl get networkpolicy -n APP_NAMESPACE
kubectl get serviceaccounts -n APP_NAMESPACE
kubectl describe pod POD_NAME -n APP_NAMESPACE
~~~

Không dùng một Pod đặc quyền hoặc privileged DaemonSet để kiểm tra tất cả node nếu không được phép. Nếu cần Pod chẩn đoán, tạo trong namespace thử nghiệm được phê duyệt và gỡ bỏ sau khi xong.

Với GKE Autopilot, một số quyền thao tác trên node khác Standard; hãy ưu tiên công cụ quan sát được nền tảng hỗ trợ.

## 19. Cloud Run: đường egress dễ gây nhầm

Cloud Run có những cơ chế truy cập VPC như **Direct VPC egress** và **Serverless VPC Access connector** theo tính năng/region hỗ trợ. Tùy cấu hình, traffic có thể chỉ đi qua VPC cho các dải private (**private-ranges-only**) hoặc đi qua VPC cho mọi đích (**all-traffic**).

| Egress configuration | Điểm cần kiểm tra |
| --- | --- |
| Chưa cấu hình VPC egress | Không áp đặt sơ đồ Cloud NAT của một VM private lên đường egress mặc định |
| private-ranges-only | Google API VIP có địa chỉ public hoặc internet endpoint có thể không đi qua VPC như người vận hành tưởng |
| all-traffic | Kiểm tra subnet/connector, route, firewall, NAT hoặc PGA/PSC theo endpoint thực tế |

Ví dụ, một Cloud Run revision trước đây gọi API thành công, sau khi chuyển sang all-traffic thì timeout. Không kết luận Google API down: có thể là egress được đưa qua subnet mới nhưng PGA, route hoặc firewall chưa được chuẩn bị; với một website bên ngoài, Public Cloud NAT có thể chưa bao phủ nguồn.

Lệnh chỉ đọc mô tả service:

~~~bash
gcloud run services describe SERVICE_NAME \
  --project=PROJECT_ID \
  --region=REGION \
  --format=yaml
~~~

Đối chiếu revision đang nhận traffic với revision đang lỗi; khác biệt network, egress settings, env vars và IAM có thể giải thích sự cố. Cloud Run revision không có host-level network tools giống VM; dùng log ứng dụng và các probe trong container được cho phép.

## 20. Hybrid/on-premises: không dùng giả định của VM GCP

Máy chủ trong datacenter hoặc cloud khác truy cập Google APIs qua VPN/Interconnect có thêm các điều kiện về DNS, định tuyến private VIP, source address và cơ chế private access được hỗ trợ. Private Google Access của một subnet Compute Engine **không tự bật** cho mọi hệ thống on-premises.

Checklist riêng:

- DNS on-prem có phân giải đúng private/restricted VIP hoặc PSC endpoint khi phù hợp không?
- Route on-prem đến dải đích có được quảng bá/trỏ vào đường kết nối đúng không?
- Route chiều về, firewall stateful/NAT và IP source có được cho phép không?
- Hệ thống đang dùng internet egress thông thường hay một đường truy cập riêng có điều kiện?
- IAM/VPC Service Controls có cho phép yêu cầu từ nguồn ngoài VPC Google Cloud không?

Không quảng bá toàn bộ default route qua VPN chỉ vì một API lỗi. Ưu tiên route cụ thể cho endpoint và chính sách egress theo kiến trúc được hỗ trợ, rồi kiểm thử từ máy thật.

## 21. Công cụ quan sát: ưu điểm và giới hạn

| Công cụ | Dùng để kiểm tra | Giới hạn |
| --- | --- | --- |
| Connectivity Tests | Phân tích cấu hình tuyến/firewall và khả năng kết nối theo phạm vi hỗ trợ | Không xác nhận kết quả API auth hoặc tất cả thiết bị ngoài GCP |
| Firewall Rules Logging | Rule allow/deny có ghi log theo cấu hình | Phải bật logging; không phải packet capture đầy đủ |
| VPC Flow Logs | Quan sát flow, IP, port, số byte và metadata theo khả năng hỗ trợ | Có sampling/aggregation, cần diễn giải nguồn IP |
| Cloud NAT logs/metrics | Translation, port allocation, lỗi NAT và lưu lượng | Chỉ phản ánh nguồn thực sự đi qua NAT |
| Cloud DNS logs | Truy vấn, câu trả lời hoặc tình trạng resolver theo cấu hình hỗ trợ | Không có nghĩa TCP tới IP đã hoạt động |
| Cloud Audit Logs | Thay đổi cấu hình và lỗi truy cập API được ghi lại khi áp dụng | Data Access logs có thể cần bật và quyền xem phù hợp |
| Application logs/traces | Request path, method, status, deadline, proxy/TLS errors | Cần correlation ID, tránh lộ secrets |

Không có một log duy nhất giải thích toàn bộ đường đi. Ví dụ, NAT logs không có record có thể là do request đi qua PGA/PSC, NAT logging chưa bật, log không được lấy mẫu hoặc request chưa tới được NAT.

Khi thiết lập theo dõi, tránh các nhãn metric có cardinality cực cao như request ID. Request ID phù hợp với log/trace; metrics nên tổng hợp theo service, region, endpoint class và error category.

## 22. Gợi ý truy vấn Cloud Logging

Các ví dụ sau là **bộ lọc gợi ý** cho Logs Explorer; phải điều chỉnh resource type/log name theo sản phẩm, project và cách logging được cấu hình. Chúng không tự bật log.

Tìm Cloud NAT logs khi resource type được hỗ trợ:

~~~text
resource.type="nat_gateway"
severity>=WARNING
~~~

Tìm VPC Flow Logs từ subnet:

~~~text
resource.type="gce_subnetwork"
logName:"vpc_flows"
~~~

Tìm thay đổi firewall/route hoặc lỗi quyền qua audit logs:

~~~text
logName:"cloudaudit.googleapis.com"
protoPayload.serviceName="compute.googleapis.com"
~~~

Trong điều tra, giới hạn khoảng thời gian, project/host project và resource liên quan để tránh nhiễu. Đối chiếu thời điểm request lỗi với thay đổi gcloud/Terraform và telemetry; không xem một warning NAT là nguyên nhân nếu nó không liên quan source/destination đang lỗi.

## 23. Tình huống 1: API private hoạt động nhưng website public timeout

**Bối cảnh:** VM không có external IP có thể đọc metadata từ một Google API qua PGA, nhưng gọi trang public bên ngoài lại timeout.

Giả thuyết hợp lý:

1. PGA và route đến Google APIs đang hoạt động.
2. VM chưa có Public Cloud NAT hoặc egress proxy để ra internet public.
3. NAT đã có nhưng không bao phủ đúng subnet/region, thiếu IP hoặc cạn port.
4. Egress firewall chặn destination hoặc TCP 443 ngoài tập API cho phép.

Trình tự kiểm tra:

- Xác nhận IP của API và website; phân biệt endpoint Google APIs với internet public.
- Kiểm tra external IP, route và NAT coverage.
- Kiểm tra egress firewall và Cloud NAT logs/metrics.
- Dùng curl đến endpoint thử nghiệm được phép, xem DNS/TCP/TLS.
- Sau khi sửa, test cả API private và website public để phát hiện tác động phụ.

**Bài học:** Private Google Access không phải truy cập internet tổng quát; thêm IAM role cho bucket không sửa được lỗi website bên ngoài.

## 24. Tình huống 2: GKE lỗi khi số Pod tăng

**Bối cảnh:** ứng dụng hoạt động với 5 Pod nhưng timeout hoặc connection reset khi tăng lên 200 Pod, đặc biệt khi gọi dịch vụ bên ngoài.

Kiểm tra theo hướng giới hạn:

- Những Pod lỗi nằm trên node hoặc subnet nào? Có tính vùng/zone không?
- NAT ports/allocated IP có đủ cho số kết nối đồng thời không?
- Pod traffic có được SNAT thành node IP hay đang dùng secondary IP?
- Có limit trên endpoint, DNS cache, TCP connection pool hoặc external API quota không?
- HPA tăng Pod nhưng database/external endpoint không tăng công suất có gây retry storm không?

Không tăng NAT ports theo cảm tính nếu lỗi thực tế là HTTP 429 từ API. Cũng không mở toàn bộ firewall khi chỉ có một pool đang cạn connection. Đo số connection, HTTP status và packet-level evidence theo công cụ được phép.

**Bài học:** hiện tượng xuất hiện theo tải thường liên quan công suất, connection lifecycle hoặc quota; phải phân biệt với cấu hình deny tuyệt đối.

## 25. Tình huống 3: Cloud Run chuyển sang all-traffic thì lỗi

**Bối cảnh:** nhóm cấu hình Direct VPC egress hoặc connector với chế độ all-traffic để kiểm soát egress. Sau triển khai, request đến Google API hoặc website public bị timeout.

Các bước:

1. So sánh revision cũ và mới, nhất là network và egress settings.
2. Xác định region, subnet hoặc connector và source IP/range được sử dụng.
3. Kiểm tra route, effective firewall policy và NAT coverage cho website public.
4. Đối với Google APIs, kiểm tra PGA, DNS private/restricted/PSC và định tuyến tương ứng.
5. Kiểm tra proxy, certificate store và IAM nếu TLS đã hoàn tất nhưng API trả 403.
6. Dùng canary revision hoặc rollback được phê duyệt nếu lỗi ảnh hưởng production; không mở egress toàn mạng để chữa cháy.

**Bài học:** thay đổi egress path là thay đổi kiến trúc mạng, không chỉ một cờ cấu hình Cloud Run.

## 26. Tình huống 4: restricted.googleapis.com trả permission denied

**Bối cảnh:** workload có thể phân giải API về VIP restricted và kết nối TLS, nhưng một thao tác trả HTTP 403.

Hãy kiểm tra:

- Google API cụ thể có nằm trong nhóm được restricted.googleapis.com hỗ trợ không?
- Request có bị VPC Service Controls chặn do perimeter, identity, ingress/egress rule hoặc project không?
- Service account có IAM role trên đúng resource và API có được bật không?
- Endpoint có đúng hostname và API method không?
- Response có error details để xác định VPC SC so với IAM không?

Nếu response đã là 403 từ Google API, thêm Cloud NAT hoặc đổi firewall ít có khả năng giải quyết gốc lỗi. Không chuyển sang private.googleapis.com để “né” VPC Service Controls nếu đó là biện pháp bảo mật bắt buộc của tổ chức.

**Bài học:** điều tra một denial ở tầng dịch vụ bằng bằng chứng policy và identity, không gỡ bỏ kiểm soát mạng.

## 27. Runbook điều tra theo từng bước

**Bước 1 – Phân loại ảnh hưởng.** Ghi project/region, nguồn, destination FQDN/IP:port, thời điểm, error message và tần suất. Chọn một request có thể lặp lại an toàn.

**Bước 2 – Xác nhận endpoint.** Từ VM/Pod/service lỗi, kiểm tra DNS và proxy. Nếu DNS sai, sửa quyền phân giải hoặc zone đúng phạm vi trước.

**Bước 3 – Kiểm tra đường đi.** Xác định VPC/subnet và nguồn thực tế; kiểm tra route, next hop, shared VPC host project và firewall policies. Dùng Connectivity Tests khi khả thi.

**Bước 4 – Xác định egress mechanism.** Có external IP? Cần Public NAT hay PGA? Endpoint Google API đang dùng private/restricted VIP hay PSC? Source subnet/range có thuộc phạm vi cấu hình không?

**Bước 5 – Kiểm tra thực tế.** Dùng curl, TLS probe và log trong cùng thời gian. Nếu không kết nối được, theo dõi network; nếu đã nhận HTTP/gRPC response, chuyển sang IAM, VPC SC, quota hoặc API semantics.

**Bước 6 – Sửa tối thiểu.** Thay chính xác một thành phần: DNS record, route, firewall policy, NAT coverage, PGA flag, service account permission hoặc API setting. Review quyền và tác động trước apply.

**Bước 7 – Verify.** Lặp lại request lỗi ban đầu, kiểm tra response đúng nghiệp vụ và đối chiếu firewall/NAT/API logs. Test thêm một hành trình liên quan để tránh lỗi hồi quy.

**Bước 8 – Đóng incident.** Ghi root cause, bằng chứng, thời điểm sửa, người phê duyệt, regression test và thay đổi IaC. Thu hồi quyền/rule tạm, không để ngoại lệ vô thời hạn.

## 28. Những sai lầm cần tránh

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Cấp Editor/Owner vì API trả 403 | Mở quyền vượt nhu cầu, không sửa VPC SC | Tìm permission và principal bị từ chối |
| Mở egress 0.0.0.0/0 mọi port để thử | Tăng rủi ro dữ liệu thoát ra ngoài | Dùng rule tối thiểu, có phê duyệt và hết hạn |
| Thêm NAT cho mọi lỗi Google API | Bỏ qua Private Google Access và DNS | Xác định endpoint và egress path thực |
| Dùng ping để chứng minh HTTPS đi được | ICMP có thể bị chặn riêng và không kiểm tra TLS | Thử TCP 443 và response thực |
| Xem absence of logs là chứng cứ tuyệt đối | Logging có thể tắt hoặc sampled | Đối chiếu nhiều nguồn telemetry |
| Nhầm Cloud Run private-ranges-only và all-traffic | Điều tra sai VPC/NAT | Kiểm tra revision và network egress config |
| Quên Shared VPC host project | Xem nhầm firewall, subnet và NAT | Bắt đầu từ network interface/subnet owner |
| Chỉ kiểm tra node IP, bỏ qua Pod SNAT | NAT coverage sai dải | Xác minh nguồn sau NAT/masquerade |
| Tắt VPC SC để thử lỗi 403 | Có thể phá vỡ ranh giới bảo mật | Dùng audit/error details, điều chỉnh policy được phê duyệt |
| Sửa nhiều thứ cùng lúc | Khó xác định root cause và rollback | Một giả thuyết – một thay đổi – một lần đo |

## 29. Bài thực hành: ba dạng lỗi cùng một API

**Bối cảnh:** một ứng dụng Java/Spring gọi Cloud Storage từ ba môi trường: VM private, GKE Pod và Cloud Run revision. Nhóm đặt mục tiêu loại bỏ timeout và permission error mà không cấp quyền rộng.

Thiết lập bài thực hành trong project thử nghiệm có quyền phù hợp. Không phá cấu hình production hoặc tạo rule công khai để mô phỏng lỗi.

1. Xác định project, VPC, subnet, workload identity và endpoint Cloud Storage của từng nguồn.
2. Ghi kết quả DNS, route, firewall/effective policy và egress mechanism.
3. Mô phỏng bằng cấu hình thử nghiệm được phê duyệt một lỗi DNS hoặc sai endpoint; chứng minh DNS là nguyên nhân và sửa.
4. Với VM không có external IP, so sánh khả năng truy cập Google API qua PGA với việc truy cập website public qua Public NAT.
5. Trên GKE, xác định source Pod/node IP và tác động của NetworkPolicy với namespace thử nghiệm.
6. Trên Cloud Run, kiểm tra khác biệt giữa private-ranges-only và all-traffic theo khả năng triển khai được phép.
7. Thử một lời gọi API không có quyền trên resource giả, thu thập HTTP 403 và error details; không thay firewall để sửa lỗi.
8. Ghi log/metric chứng minh request đã đi đến lớp thất bại.
9. Đề xuất thay đổi nhỏ nhất, test lại đúng endpoint và kiểm tra không mở quyền ngoài phạm vi.
10. Tổng hợp runbook và lưu bản cấu hình cuối qua IaC.

**Kết quả cần nộp:** bảng nguồn/đích/route/DNS/egress, bốn loại bằng chứng (DNS, network, TLS, API), kết luận nguyên nhân, thay đổi cần thiết, test sau sửa và checklist hoàn nguyên. Không tự điền số liệu hoặc trạng thái dịch vụ như thể đã chạy đo thực tế.

## 30. Checklist trước khi kết luận sự cố

- Đã định danh đúng nguồn, project, VPC/subnet và chủ sở hữu Shared VPC nếu có.
- Có FQDN, IP, protocol, port và error message của cùng request thử nghiệm.
- DNS được kiểm tra tại đúng VM/Pod/container hoặc proxy thực hiện phân giải.
- Route đến IP đích và đường egress thực tế đã được đối chiếu.
- Effective firewall/policy, rule selectors và NetworkPolicy được kiểm tra theo workload.
- Đã phân biệt VM có external IP, Public NAT, PGA, PSC, PSA và đường serverless egress.
- NAT đúng region, subnet/source range và có đủ IP/ports theo mức tải thực.
- Private/restricted Google API VIP và private DNS được dùng đúng mục đích, không phá VPC SC.
- TLS được kiểm tra mà không vô hiệu hóa certificate verification.
- HTTP/gRPC status được phân loại; 401/403/429 không bị nhầm với network timeout.
- IAM, scopes, API enabled, organization policy và VPC Service Controls được xác minh khi liên quan.
- Firewall, VPC flow, NAT, DNS và API audit logs được diễn giải cùng thời điểm; biết giới hạn sampling.
- Sửa chữa áp dụng theo quyền tối thiểu, có rollback và kiểm thử hồi quy.
- Không còn rule, token hoặc đường egress tạm nào không được phê duyệt.
- Kết luận incident có bằng chứng và cập nhật IaC/runbook để phòng tái diễn.

Điều tra lỗi firewall, NAT và truy cập Google APIs trên GCP cần bắt đầu bằng việc xác định **đường đi thực của request**, chứ không phải mở firewall hoặc thêm NAT theo suy đoán. DNS quyết định đích, routing và policies quyết định đường truyền, Cloud NAT hoặc Private Google Access cung cấp kiểu egress phù hợp, còn IAM và VPC Service Controls quyết định API có chấp nhận thao tác hay không. Khi tách rõ các lớp và đo được điểm thất bại, đội vận hành có thể khôi phục dịch vụ nhanh hơn mà vẫn giữ ranh giới bảo mật, khả năng kiểm toán và chi phí trong tầm kiểm soát.
