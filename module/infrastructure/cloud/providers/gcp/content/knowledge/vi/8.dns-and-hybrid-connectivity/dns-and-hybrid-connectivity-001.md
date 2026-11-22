# Cloud DNS public zones và quản lý bản ghi

Một nhóm triển khai API lên Google Cloud và muốn khách hàng truy cập qua tên `api.example.com` thay vì địa chỉ IP. Song song, nhóm cần cấu hình email, xác minh quyền sở hữu domain, chuyển endpoint giữa các lần phát hành mà không gián đoạn và giới hạn người được phép thay đổi DNS. **Cloud DNS public managed zone** giúp quản lý bản ghi DNS có thẩm quyền cho tên miền công khai trên Internet.

Bài học thuộc chương **DNS và kết nối hybrid** của học phần **CLOUD_PROVIDERS_GCP**. DNS kết nối kiến thức tổ chức project, IAM, VPC với các dịch vụ triển khai Compute Engine, GKE, Cloud Run, Cloud Storage và cơ sở dữ liệu. Nắm chắc public DNS giúp chọn đúng endpoint công khai, phát hành có kiểm soát, theo dõi độ tin cậy và quản lý chi phí.

Sau bài này, bạn có thể:

- Giải thích authoritative name server, registrar, delegation, public zone, recursive resolver và cache.
- Tạo public managed zone, phân biệt zone name với DNS suffix.
- Quản lý các RRset A, AAAA, CNAME, MX, TXT, CAA và NS theo đúng ràng buộc.
- Dùng Google Cloud Console, `gcloud` và Terraform để thêm, sửa, kiểm tra bản ghi.
- Lập kế hoạch TTL, DNS cutover, DNSSEC, phân quyền IAM và rollback.
- Phân tích các trường hợp DNS sai bản ghi, delegation thiếu hoặc cache chưa hết.

> **Quy ước ví dụ:** `example.com` và các tên con chỉ là domain dành cho tài liệu; `203.0.113.0/24`, `198.51.100.0/24` và `2001:db8::/32` là dải IP tài liệu. Không dùng nguyên xi làm endpoint thực tế. Để thao tác trên Internet, cần tên miền thuộc quyền kiểm soát và địa chỉ ứng dụng hợp lệ.

## 1. DNS công khai hoạt động như thế nào?

**DNS (Domain Name System)** dùng cơ chế phân cấp để tìm dữ liệu gắn với tên miền. Ví dụ khi ứng dụng cần IP của `api.example.com.`, nó thường hỏi **recursive resolver**. Resolver trả kết quả từ cache nếu còn hiệu lực; nếu không, nó truy vấn hệ thống root, TLD và authoritative name server để tìm RRset tương ứng.

~~~mermaid
flowchart LR
  A["Browser hoặc ứng dụng"] --> B["Recursive resolver"]
  B --> C["Root DNS"]
  C --> D["TLD .com"]
  D --> E["Authoritative NS của example.com"]
  E --> F["Bản ghi A / AAAA / CNAME ..."]
  F --> B
  B --> A
~~~

Sơ đồ là chuỗi truy vấn khi chưa có cache. Trên thực tế, resolver không cần hỏi đủ mọi tầng nếu nó đã có tên name server hoặc RRset trong cache.

| Thành phần | Công việc | Điểm cần phân biệt |
|---|---|---|
| **Registrar** | Quản lý việc đăng ký domain và giao diện cập nhật nameserver | Cloud DNS không phải nhà đăng ký tên miền |
| **Parent DNS zone** | Chứa thông tin NS để ủy quyền tên miền con | Với `example.com`, cấp cha ở hệ thống DNS `.com` |
| **Cloud DNS public zone** | Quản lý và trả lời bản ghi có thẩm quyền | Zone có thể tồn tại dù registrar chưa trỏ đến Cloud DNS |
| **Authoritative name server** | Trả lời RRset của zone | Name server do Cloud DNS gán cho public zone |
| **Recursive resolver** | Phân giải thay client và cache theo TTL | Có thể vẫn trả kết quả cũ sau khi bạn đổi RRset |
| **Application endpoint** | Nhận kết nối khi client đã có IP | Load balancer, website hoặc API; DNS không tự phục vụ HTTP |

**Điểm cốt lõi:** tạo public managed zone trong Google Cloud **chưa tự chuyển DNS của tên miền**. Cần thay delegation NS tại registrar hoặc parent zone để Internet dùng các authoritative NS do Cloud DNS cấp.

## 2. Public zone khác private zone ở đâu?

Cloud DNS hỗ trợ nhiều mô hình phân giải. Bài này tập trung vào **public managed zone**.

| Tiêu chí | Public managed zone | Private managed zone |
|---|---|---|
| Ai có thể tra cứu? | Resolver trên Internet khi có đường delegation hợp lệ | Các VPC được cho phép theo cấu hình |
| Dùng cho | Website, API, mail và bản ghi công khai | Service nội bộ, private IP, workload trong VPC |
| Cơ chế phân giải | Hệ thống authoritative DNS công cộng | Phân giải nội bộ Google Cloud |
| Cần cập nhật registrar? | Có nếu tên miền thuộc hệ thống DNS công cộng cần được ủy quyền | Không theo mô hình registrar/parent công cộng |
| Vai trò VPC | Không quy định ai được đọc bản ghi public | Quy định mạng nào có thể dùng zone private |

Public managed zone là tài nguyên thuộc **Google Cloud project** để quản trị IAM và billing, nhưng không gắn với một region duy nhất như VM hoặc Cloud Run service. Một bản ghi public có thể chứa IP private về mặt định dạng, song điều đó **không làm IP private truy cập được qua Internet**.

Với hybrid connectivity, public DNS chỉ giải quyết tên miền công khai; để phân giải hostname nội bộ giữa on-premises và GCP, sẽ cần các cơ chế phù hợp như private zone, DNS forwarding, peering, VPN hoặc Interconnect.

## 3. Zone name, DNS suffix và Resource Record Set

### Hai loại tên rất khác nhau

- **Managed zone name** là định danh dùng trong Google Cloud API/CLI, ví dụ `corp-public`.
- **DNS suffix** là tên miền mà zone quản lý, ví dụ `example.com.`. Dấu chấm cuối chỉ tên miền đầy đủ (*FQDN*).
- **Record name** là tên của RRset trong zone, ví dụ `api.example.com.`, phải nằm trong phạm vi DNS suffix.
- **Zone apex** là gốc zone, ví dụ `example.com.`.

Khi tạo zone public, Cloud DNS tự tạo bản ghi **SOA** và **NS** ở zone apex. Hãy lấy tập authoritative NS thực từ Cloud DNS; không tự ý sửa danh sách NS đỉnh zone do dịch vụ gán.

### RRset là đơn vị thao tác

**Resource Record Set (RRset)** kết hợp tên DNS, loại bản ghi, TTL và một hoặc nhiều giá trị `RDATA`. Ví dụ mô tả theo hình dạng dữ liệu:

~~~yaml
name: api.example.com.
type: A
ttl: 300
rrdatas:
  - 203.0.113.10
  - 203.0.113.11
~~~

Cả hai IP cùng tên/loại thuộc **một RRset A**. Nếu đổi danh sách địa chỉ, phải cập nhật tập giá trị hiện tại đúng cách. Thêm bản ghi TXT cho cùng tên khác với việc sửa RRset A.

**Ràng buộc CNAME:** CNAME không được cùng tồn tại với RRset có loại khác ở cùng tên. Do zone apex đã có NS/SOA, không thể đặt CNAME thông thường ngay tại apex.

## 4. Các loại bản ghi thường gặp

| Loại | RDATA minh họa | Mục đích | Điều cần nhớ |
|---|---|---|---|
| `A` | `203.0.113.10` | Tên → IPv4 | Nên dùng external static IP khi trỏ tới load balancer cần ổn định |
| `AAAA` | `2001:db8::10` | Tên → IPv6 | Chỉ dùng khi endpoint thực sự phục vụ IPv6 |
| `CNAME` | `example.com.` | Tên bí danh → tên đích | Không cùng tên với bản ghi khác |
| `MX` | `10 mail.example.net.` | Mail exchanger | Số nhỏ thường được ưu tiên hơn; đích mail phải được cấu hình |
| `TXT` | `"google-site-verification=DEMO"` | Xác minh tên miền, SPF/DKIM/DMARC | Nội dung chuỗi và quy tắc quote phải đúng |
| `CAA` | `0 issue "letsencrypt.org"` | Chỉ định CA được phép cấp certificate | Có thể ảnh hưởng cấp hoặc gia hạn TLS |
| `NS` | Tên authoritative name server | Delegation domain/subdomain | NS apex được Cloud DNS quản lý |
| `SOA` | Metadata serial, timers và nameserver | Thông tin quản trị zone | Cloud DNS khởi tạo tại apex |
| `SRV` | `10 20 443 service.example.com.` | Khai báo dịch vụ, host và port | Client phải hỗ trợ SRV |

Ví dụ một website, API và hệ thống thư điện tử:

~~~text
example.com.           A        203.0.113.10
example.com.           AAAA     2001:db8::10
www.example.com.       CNAME    example.com.
api.example.com.       A        203.0.113.20
example.com.           MX       10 mail.example.net.
example.com.           TXT      "google-site-verification=DEMO"
_dmarc.example.com.    TXT      "v=DMARC1; p=none"
~~~

Bảng chỉ minh họa cấu trúc bản ghi, không phải một cấu hình mail sẵn sàng đưa vào production. SPF, DKIM, DMARC và MX phải theo hướng dẫn của nhà cung cấp email. Ví dụ `p=none` của DMARC chủ yếu phục vụ quan sát; nó không chủ động từ chối email giả mạo.

**Apex và `www`:** đặt A/AAAA cho `example.com.` và CNAME cho `www.example.com.` là hợp lệ. Ngược lại, đặt CNAME ngay `example.com.` xung đột với NS/SOA tại apex. Nếu cần trỏ apex đến ứng dụng, hãy sử dụng cơ chế record được endpoint hỗ trợ, ví dụ A/AAAA đến frontend IP của external load balancer.

## 5. Chuẩn bị và tạo public managed zone

Trước khi tạo zone:

1. Chọn Google Cloud project có billing và chủ sở hữu rõ ràng.
2. Bật API `dns.googleapis.com`.
3. Bảo đảm danh tính được cấp quyền tạo zone, chẳng hạn `roles/dns.admin` tại phạm vi cần thiết.
4. Xác định quyền quản lý domain tại registrar và người có quyền cập nhật nameserver.
5. Với domain đã hoạt động, **kiểm kê toàn bộ bản ghi cũ**: web, API, mail, xác minh, subdomain, DNSSEC và TTL.

### Tạo qua Console

Trong Google Cloud Console, mở **Network services → Cloud DNS → Create zone**, chọn:

- **Zone type:** Public.
- **Zone name:** `corp-public` (tên quản trị).
- **DNS name:** `example.com.` (DNS suffix).
- **Description:** mô tả mục đích, owner và môi trường.
- **DNSSEC:** chọn theo yêu cầu và kế hoạch cập nhật DS ở registrar.

Sau khi Create, mở thông tin zone để xem NS, SOA mặc định. Zone này chưa được Internet sử dụng cho domain cho đến khi delegation được thay đổi.

### Tạo qua gcloud

~~~bash
# Chỉ là ví dụ minh họa; thay bằng project/domain thuộc quyền quản lý.
PROJECT_ID="my-dns-project"
ZONE="corp-public"
DOMAIN="example.com."

gcloud config set project "$PROJECT_ID"
gcloud services enable dns.googleapis.com

gcloud dns managed-zones create "$ZONE" \
  --dns-name="$DOMAIN" \
  --description="Public DNS for example.com" \
  --visibility=public \
  --labels="team=platform,environment=production"

gcloud dns managed-zones describe "$ZONE"
gcloud dns record-sets list --zone="$ZONE"
~~~

Đừng thực thi nguyên xi với `example.com.`. Tạo public zone có thể phát sinh **phí duy trì zone** ngay cả khi chưa cập nhật registrar. Lệnh cần quyền và API hợp lệ.

## 6. Delegation: để Internet tìm đúng authoritative NS

Khi public zone tạo xong, Cloud DNS cấp tập **authoritative name server**. Để resolver công cộng dùng zone mới, parent DNS phải chứa **NS delegation** phù hợp.

~~~text
Client hỏi api.example.com.
            ↓
Recursive DNS → root → .com
                       ↓
                NS của example.com.
                       ↓
            Cloud DNS authoritative NS
                       ↓
            A api.example.com. = endpoint IP
~~~

### Chuyển một domain đang hoạt động

1. **Xuất zone hiện tại** ở nhà cung cấp cũ; kiểm tra tất cả RRset, nhất là MX, TXT verification, DKIM, SPF, CAA và NS subdomain.
2. **Tạo Cloud DNS public zone** với cùng suffix, thêm đầy đủ dữ liệu.
3. **Hỏi trực tiếp NS Cloud DNS** để chắc chắn tất cả bản ghi quan trọng trả về đúng trước khi cutover.
4. **Đánh giá DNSSEC** nếu zone cũ đã có DS ở parent. Xử lý chuỗi tin cậy theo kế hoạch trước khi chuyển nameserver.
5. **Cập nhật nameserver tại registrar** bằng danh sách NS do Cloud DNS cấp. Nếu chỉ chuyển subdomain, thêm NS delegation tại parent zone tương ứng.
6. **Kiểm tra qua nhiều recursive resolver** và theo dõi chức năng website/API/mail; cho nhà cung cấp cũ hoạt động đủ lâu để các cache cũ hết hạn.
7. **Ngừng hạ tầng DNS cũ** khi delegation, câu trả lời và các hệ thống liên quan đã ổn định.

Cloud DNS không tự đổi NS ở registrar. Có thể gặp tình huống `dig @<Cloud-DNS-NS>` trả đúng nhưng `dig` từ Internet vẫn tới DNS cũ: đây thường là delegation chưa được cập nhật hoặc cache chưa hết TTL.

### Ủy quyền subdomain

Ví dụ nhóm platform giữ `example.com.` và giao nhóm dev quản lý zone `dev.example.com.`:

~~~text
Parent zone: example.com.
  dev.example.com.      NS  (tập NS của child Cloud DNS zone)

Child zone: dev.example.com.
  app.dev.example.com.  A   203.0.113.30
~~~

Tạo child zone trước, lấy chính xác NS từ Cloud DNS, sau đó tạo RRset NS tại tên `dev.example.com.` trong zone cha. Đừng thay NS/SOA apex của child zone bằng tên tùy chọn. Khi quản trị hai zone ở hai project, cần chủ sở hữu và quy trình phê duyệt phối hợp để tránh delegation không khớp.

## 7. TTL, caching và độ trễ thay đổi

**TTL (Time To Live)** là thời gian resolver có thể cache RRset. Ví dụ TTL 300 giây cho phép cache khoảng 5 phút; điều đó **không bảo đảm mọi máy trên Internet nhìn thấy bản ghi mới đúng sau 5 phút**, vì còn nhiều tầng cache và việc thay đổi delegation.

Các nguyên nhân kết quả cập nhật chậm:

- Resolver vừa cache RRset cũ với TTL lớn trước khi cập nhật.
- Hệ điều hành, trình duyệt hoặc ứng dụng còn cache riêng.
- Parent zone và recursive resolver cache NS delegation cũ.
- Truy vấn trước đó trả `NXDOMAIN` hoặc `NODATA`, dẫn đến **negative caching** theo thông tin SOA.
- Cloud DNS cần xử lý change operation và đồng bộ authoritative servers; việc operation xong vẫn không xóa cache ngoài hệ thống.

| Tình huống | TTL tham khảo | Giải thích |
|---|---:|---|
| Bản ghi ổn định | 1 giờ hoặc hơn | Giảm tần suất truy vấn authoritative |
| Chuẩn bị chuyển endpoint | Vài phút, sau khi giảm TTL đủ sớm | Giúp chuyển/khôi phục nhanh hơn |
| MX, DNS verification | Theo yêu cầu nhà cung cấp | Không tự ý đổi khi hệ thống phụ thuộc |
| Delegation NS | Theo parent/registrar | Cần tính cả TTL NS ngoài zone |

**Kế hoạch cutover:** nếu TTL cũ 3600 giây, hạ xuống 300 **trước** khi đổi IP và đợi cache TTL cũ hết hạn. Hạ TTL đồng thời với đổi IP không thể ép resolver đang giữ dữ liệu 3600 giây hỏi lại ngay.

TTL nhỏ không hoàn toàn miễn phí: nó có thể tăng số truy vấn tới authoritative server và ảnh hưởng chi phí DNS. Đừng dùng TTL quá thấp để thay thế kiến trúc load balancing hoặc quy trình vận hành phù hợp.

## 8. Thêm, đọc và sửa bản ghi bằng gcloud

### Tạo bản ghi cơ bản

~~~bash
ZONE="corp-public"

gcloud dns record-sets create "example.com." \
  --zone="$ZONE" --type=A --ttl=300 \
  --rrdatas="203.0.113.10"

gcloud dns record-sets create "www.example.com." \
  --zone="$ZONE" --type=CNAME --ttl=300 \
  --rrdatas="example.com."

gcloud dns record-sets create "api.example.com." \
  --zone="$ZONE" --type=A --ttl=300 \
  --rrdatas="203.0.113.20"

gcloud dns record-sets list --zone="$ZONE"
~~~

Những lệnh tạo tài nguyên trên chỉ dành cho minh họa. Nếu RRset cùng tên/loại đã tồn tại, hãy cập nhật RRset hiện hữu; không cố tạo thêm bản ghi `A` độc lập cùng tên. Trong Console, mục **Add standard** tạo RRset mới; sửa RRset A đang tồn tại khi cần thêm IP thứ hai vào cùng tập dữ liệu.

### Thay IP bằng transaction

Cloud DNS hỗ trợ transaction gồm nhiều thao tác **remove** và **add** để tạo thay đổi logic đồng nhất. Giả sử `api.example.com.` đang có RRset A chứa đúng một IP `203.0.113.20` và TTL 300:

~~~bash
ZONE="corp-public"
RECORD="api.example.com."

# Đọc lại trước khi thay: thông số phải khớp chính xác RRset hiện hữu.
gcloud dns record-sets list --zone="$ZONE" \
  --filter="name=$RECORD"

gcloud dns record-sets transaction start --zone="$ZONE"

gcloud dns record-sets transaction remove "203.0.113.20" \
  --zone="$ZONE" --name="$RECORD" --type=A --ttl=300

gcloud dns record-sets transaction add "198.51.100.20" \
  --zone="$ZONE" --name="$RECORD" --type=A --ttl=300

gcloud dns record-sets transaction execute --zone="$ZONE"
gcloud dns record-sets list --zone="$ZONE"
~~~

**Lưu ý:** trước remove cần lấy **đúng TTL và toàn bộ RDATA** của RRset cũ; nếu nó có hai IP, bạn phải xử lý cả tập, không đoán một giá trị. Transaction không nên được tạo đồng thời bởi nhiều người trong cùng thư mục dùng chung file mặc định `transaction.yaml`; trong pipeline hãy dùng file transaction riêng theo job hoặc triển khai qua API/IaC có kiểm soát concurrency.

Kiểm tra change operation và đọc lại zone trước khi retry nếu gặp lỗi. Đừng tạo một bản ghi mới sai tên hoặc đổi Project ID để né thông báo lỗi.

### Quản lý TXT, MX và CAA

- Nhiều TXT value cùng tên thuộc một RRset TXT; khi thêm verification token mới, đừng xóa token đang được dịch vụ khác dùng.
- MX chứa **priority** và tên máy chủ email; sửa MX cần phối hợp với nhà cung cấp mail và theo dõi deliverability.
- SPF, DKIM, DMARC đều liên quan TXT; chỉ dùng giá trị do đội email xác nhận.
- CAA có thể ảnh hưởng CA cấp TLS certificate: sửa CAA phải cân nhắc renew.
- Bản ghi CNAME không thể cùng tên với TXT/A/MX khác và không đặt tại zone apex.

## 9. Quản lý DNS bằng Terraform và quy trình review

Tổ chức thường dùng Infrastructure as Code để lưu cấu hình DNS trong Git và chỉ cấp quyền ghi cho pipeline chuyên trách:

~~~hcl
resource "google_dns_managed_zone" "public" {
  name        = "corp-public"
  dns_name    = "example.com."
  description = "Public DNS managed by platform"
  visibility  = "public"

  labels = {
    team        = "platform"
    environment = "production"
  }
}

resource "google_dns_record_set" "root_a" {
  managed_zone = google_dns_managed_zone.public.name
  name         = google_dns_managed_zone.public.dns_name
  type         = "A"
  ttl          = 300
  rrdatas      = ["203.0.113.10"]
}

resource "google_dns_record_set" "www_cname" {
  managed_zone = google_dns_managed_zone.public.name
  name         = "www.example.com."
  type         = "CNAME"
  ttl          = 300
  rrdatas      = ["example.com."]
}

resource "google_dns_record_set" "api_a" {
  managed_zone = google_dns_managed_zone.public.name
  name         = "api.example.com."
  type         = "A"
  ttl          = 300
  rrdatas      = ["203.0.113.20"]
}
~~~

Ví dụ chưa có provider/backend state, TLS, DNSSEC, email và quota; nó để hiểu cách khai báo zone/RRset. Nếu zone đã tồn tại, phải **import** và đối chiếu state với tài nguyên đang chạy thay vì tạo zone trùng suffix rồi dùng NS mới không mong muốn.

Quy trình thay đổi khuyến nghị:

1. Developer đề xuất pull request chứa tên record, loại, RRdata, TTL, lý do và endpoint đích.
2. CI kiểm tra syntax, xung đột CNAME, domain ownership và `terraform plan`.
3. Platform DNS và owner ứng dụng review; thay MX/NS/CAA/DNSSEC cần thêm bên liên quan.
4. Pipeline sử dụng service account có IAM giới hạn để `terraform apply`; ghi log ai duyệt, khi nào thay.
5. Kiểm tra authoritative NS và recursive resolver; theo dõi ứng dụng rồi xác nhận.

Không quản lý một RRset đồng thời bằng Terraform và công cụ thủ công nếu không có cách đồng bộ thay đổi; drift có thể khiến lần apply sau ghi đè. Kiểm tra `plan` thật kỹ nếu có thao tác thay thế hoặc xóa **managed zone** vì việc tạo lại có thể dẫn tới tập NS khác.

## 10. IAM và kiểm soát thay đổi public DNS

Người có quyền ghi DNS có thể đổi luồng truy cập website, làm gián đoạn email hoặc thao tác bản ghi dùng xác minh domain. Vì vậy quyền DNS production cần được quản trị nghiêm túc.

| Nhóm | Quyền cần thiết | Cách phân quyền |
|---|---|---|
| Platform DNS administrator | Tạo zone, cấu hình DNSSEC, thay RRset quan trọng | Quyền quản trị Cloud DNS phù hợp, ví dụ `roles/dns.admin` ở project có kiểm soát |
| Developer | Xem và đề xuất thay đổi | Quyền đọc hoặc quy trình PR |
| DNS deployment pipeline | Áp RRset đã duyệt | Service account riêng, quyền tối thiểu |
| Security/Audit | Xem IAM và lịch sử thay đổi | Quyền đọc và audit tương ứng |
| Registrar administrator | Sửa NS/DS ở registrar | Tài khoản registrar, độc lập Google Cloud IAM |

IAM có **kế thừa** từ Organization/Folder/Project. Nếu role `dns.admin` đã được cấp ở Folder, gỡ quyền local tại project có thể **không** thu hồi quyền hiệu lực. Cần rà soát principal, group membership, Allow/Deny/PAB khi áp dụng, và quyền cần thiết để truy cập DNS API.

Để hạn chế rủi ro, nên đặt public DNS vào project quản trị riêng, quản lý IAM theo nhóm, tách danh tính triển khai ứng dụng khỏi danh tính sửa DNS, dùng review và ghi audit cho production. Không cấp quyền sửa DNS chỉ vì developer đã có quyền deploy Cloud Run.

## 11. DNSSEC: bảo vệ tính xác thực câu trả lời

**DNSSEC** ký dữ liệu zone để resolver có hỗ trợ có thể xác minh tính xác thực/toàn vẹn của câu trả lời. DNSSEC giúp chống spoofing/cache poisoning nhưng **không mã hóa nội dung truy vấn DNS** và không thay thế HTTPS/TLS.

Để DNSSEC hoạt động với chuỗi tin cậy đầy đủ:

1. Bật DNSSEC cho public zone trong Cloud DNS.
2. Lấy **DS record** gắn với DNSKEY của zone.
3. Đăng DS tại **registrar/parent zone** theo hướng dẫn.
4. Xác minh trên resolver có DNSSEC validation; theo dõi mọi sự cố `SERVFAIL`.

Ví dụ xem DS:

~~~bash
gcloud dns dns-keys list \
  --zone="corp-public" \
  --filter="type=keySigning" \
  --format="value(ds_record())"
~~~

Nếu bật DNSSEC ở zone nhưng không đăng DS hợp lệ, chuỗi tin cậy chưa đầy đủ. Nếu DS tại parent **không khớp** khóa được dùng sau khi đổi NS hoặc thay khóa, resolver validating có thể trả `SERVFAIL` làm domain không phân giải được.

**Tắt DNSSEC phải làm đúng thứ tự:** gỡ DS tại registrar/parent, chờ thay đổi được resolver nhận theo TTL, kiểm chứng, rồi mới tắt DNSSEC tại public zone. Không tắt ký zone trong khi DS cũ còn hiệu lực. Chuyển DNS provider trên domain đang dùng DNSSEC phải có phương án phối hợp DS riêng.

## 12. Routing policy không đồng nghĩa load balancing HTTP

Ngoài bản ghi tiêu chuẩn, Cloud DNS hỗ trợ routing policy như **weighted round robin (WRR)**, **geolocation** và **failover** với các loại endpoint/cấu hình được hỗ trợ.

| Chính sách | Ý tưởng sử dụng | Giới hạn |
|---|---|---|
| WRR | Chọn câu trả lời theo trọng số | Resolver cache có thể làm tỷ lệ lưu lượng khác trọng số |
| Geolocation | Trả record theo nơi phát sinh truy vấn DNS | Nơi truy vấn có thể là resolver hoặc EDNS Client Subnet, không nhất thiết là người dùng |
| Failover | Chọn endpoint dự phòng khi cấu hình hỗ trợ health checks | Health check, kiểu endpoint và firewall phải tương thích |

DNS trả lời tên theo truy vấn, không xử lý từng HTTP request. Resolver có thể cache và chia sẻ câu trả lời cho nhiều người, nên không đảm bảo canary 10% chính xác về lưu lượng ứng dụng. Khi cần TLS, route theo host/path, health checks theo HTTP hay bảo vệ DDoS/WAF, xem xét External Application Load Balancer và trỏ `A/AAAA` đến frontend IP ổn định của load balancer.

## 13. Kiểm tra phân giải và thay đổi bằng dig

Sau khi thay RRset, luôn kiểm tra **authoritative NS** và **recursive resolver**.

~~~bash
# Xem cấu hình đang quản lý và lịch sử thay đổi trong Cloud DNS.
ZONE="corp-public"
gcloud dns managed-zones describe "$ZONE"
gcloud dns record-sets list --zone="$ZONE"
gcloud dns record-sets changes list --zone="$ZONE"

# Thay NS_DO_CLOUD_DNS_CAP bằng authoritative NS thực trả từ describe.
dig @NS_DO_CLOUD_DNS_CAP A api.example.com. +noall +answer

# Kiểm tra delegation và recursive resolvers.
dig NS example.com. +noall +answer
dig +trace api.example.com.
dig @8.8.8.8 A api.example.com. +noall +answer
dig @1.1.1.1 A api.example.com. +noall +answer
dig @8.8.8.8 MX example.com. +noall +answer
~~~

**Đọc kết quả:** nếu authoritative NS đúng mà resolver công cộng cũ, hãy kiểm tra cache và delegation. Nếu cả authoritative NS mới sai, kiểm tra RRset và change operation. Nếu `dig +trace` vẫn hướng đến NS nhà cung cấp cũ, registrar/parent chưa cập nhật hoặc resolver còn giữ delegation cũ.

### Logging và Monitoring

Cloud DNS cho phép bật query logging ở cấp **public managed zone**:

~~~bash
gcloud dns managed-zones update "corp-public" --log-dns-queries
~~~

Các truy vấn **thực sự đến authoritative name server** có thể được ghi vào Cloud Logging; câu trả lời do resolver ngoài hệ thống phục vụ từ cache không đi qua name server và sẽ không tạo query log mới. Có thể tạo **log-based metrics** cho mã phản hồi, query name/type hoặc lượng truy vấn rồi làm dashboard/alert trong Cloud Monitoring. Dữ liệu DNS query có thể chứa metadata nhạy cảm; kiểm soát quyền xem, thời gian lưu giữ và phí Cloud Logging.

Theo dõi các dấu hiệu như `NXDOMAIN` tăng bất thường, `SERVFAIL` khi bật DNSSEC, lượng truy vấn đột biến, lỗi 5xx/timeout ở load balancer sau cutover hoặc các thay đổi record set ngoài quy trình.

### Chi phí

Cloud DNS có **phí managed zone theo thời gian zone tồn tại** và **phí theo số truy vấn**, có thể có đơn giá khác với query dùng routing policy. Phí zone vẫn có thể tồn tại dù không còn truy vấn hoặc chưa delegate. Không có free tier Cloud DNS phổ quát. Logging/Monitoring có chi phí riêng theo cách sử dụng. Dùng labels để phân bổ, xem Cloud Billing và đặt budget alerts; budget alert **không tự chặn truy vấn hoặc xóa zone**.

## 14. Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Có RRset trong Cloud DNS nhưng Internet không thấy | Delegation chưa trỏ NS Cloud DNS | `dig NS`, `dig +trace` |
| Authoritative trả mới, resolver ngoài trả cũ | Cache TTL/negative caching | Hỏi trực tiếp NS và xem TTL còn lại |
| Không thêm được CNAME | Cùng tên đã có A/TXT/MX hoặc là apex | Liệt kê mọi RRset cùng tên |
| Không tạo được zone | API chưa bật, thiếu IAM, tên không hợp lệ | Kiểm tra Cloud DNS API và lỗi CLI |
| Bản ghi A đúng nhưng HTTPS không hoạt động | Endpoint, certificate hoặc host mapping chưa đúng | Kiểm tra load balancer/Cloud Run và TLS |
| Email lỗi sau cutover | MX, SPF/DKIM/DMARC thiếu hoặc NS cũ còn cache | So sánh bản ghi với cấu hình mail |
| `SERVFAIL` sau bật DNSSEC | DS/DNSKEY không khớp | Xác minh DS ở registrar/parent và khóa trong zone |
| Không xóa được zone | Còn bản ghi người dùng hoặc phụ thuộc | Kiểm kê, xuất dữ liệu và gỡ delegation an toàn |
| Chi phí tăng dù ứng dụng đã tắt | Zone vẫn tồn tại hoặc còn query/logging | Billing theo zone, query và Logging |

### Ví dụ cutover API production

API đang dùng `203.0.113.20` và cần đổi sang `198.51.100.20`:

1. Triển khai endpoint mới, kiểm tra HTTPS, certificate, health check và ứng dụng trước khi sửa DNS.
2. Giảm TTL đủ sớm và đợi cache với TTL cũ hết hạn.
3. Xuất snapshot RRset cũ; xác nhận thời điểm, chủ sở hữu và phương án quay lại.
4. Đổi bản ghi A bằng transaction hoặc Terraform có review.
5. Hỏi authoritative NS và recursive resolvers; theo dõi lỗi/latency ứng dụng.
6. Nếu lỗi, hoàn nguyên RRset cũ nhưng **giữ cả hai endpoint sống** trong giai đoạn resolver còn cache kết quả khác nhau.
7. Khi ổn định, tăng TTL về giá trị thường dùng và dọn endpoint cũ đúng kế hoạch.

**DNS rollback không tức thì.** Dữ liệu trong cache ngoài hệ thống có thể tồn tại một thời gian, nên độ tin cậy của cutover phụ thuộc kế hoạch chạy song song và kiểm chứng endpoint nhiều hơn một lệnh thay DNS.

## 15. Tình huống: website, API và mail trên Google Cloud

Một công ty thương mại điện tử vận hành website, API Java và hệ thống mail:

~~~text
Cloud DNS public zone: example.com.
  example.com.       A       203.0.113.10       → External LB website
  www.example.com.   CNAME   example.com.       → Website
  api.example.com.   A       203.0.113.20       → External LB API
  example.com.       MX      10 mail.example.net. → Mail provider
  example.com.       TXT     verification...     → Xác minh domain
~~~

Team platform sở hữu project DNS, quản lý delegation và DNSSEC. Team ứng dụng triển khai Compute Engine/GKE/Cloud Run phía sau load balancer theo project dev/staging/prod. Thay đổi DNS production qua pull request và pipeline riêng với IAM giới hạn. Đội mail xác nhận MX/TXT trước khi chuyển NS; SRE theo dõi tỷ lệ lỗi HTTP, độ trễ và query log sau thay đổi.

Khi ứng dụng cần database private trong VPC hoặc máy chủ on-premises, public zone không tạo tuyến kết nối và cũng không tự phân giải các tên private. Lúc đó cần thiết kế DNS private, inbound/outbound forwarding và kết nối mạng hybrid theo yêu cầu.

## 16. Checklist và bài tập vận dụng

- [ ] Đã xác định registrar, parent zone, owner và NS hiện tại.
- [ ] Project Cloud DNS có billing, IAM và owner rõ ràng.
- [ ] Zone name khác DNS suffix, NS/SOA do Cloud DNS khởi tạo được giữ nguyên.
- [ ] Bản ghi A/AAAA/CNAME/MX/TXT/CAA và các child delegation được kiểm kê.
- [ ] Không có CNAME trùng tên RRset khác hoặc tại apex.
- [ ] Đã xác minh endpoint và TLS độc lập trước cutover.
- [ ] Có snapshot, TTL dự kiến, lịch chuyển và phương án rollback.
- [ ] DNSSEC và DS tại registrar/parent nhất quán nếu sử dụng.
- [ ] Đã kiểm tra authoritative NS, `dig +trace` và nhiều recursive resolver.
- [ ] Có quy trình review cho DNS production và phân quyền CI/CD riêng.
- [ ] Đã cân nhắc query logging, giám sát, chi phí zone/query và chi phí logging.
- [ ] Trước khi ngừng zone, đã chuyển delegation và xác minh các dịch vụ phụ thuộc.

**Bài tập thực hành:** Doanh nghiệp quản lý domain `company.example.`, cần `www` trỏ external load balancer cho website, `api` trỏ external load balancer cho dịch vụ Java, email qua nhà cung cấp ngoài và nhóm dev tự quản `dev.company.example.` qua child public zone. Hãy:

1. Vẽ cây delegation giữa registrar, parent zone và child zone, nêu NS nào được Cloud DNS tự tạo.
2. Thiết kế RRset và TTL cho website, API, MX, TXT và NS của child zone.
3. Viết lệnh `gcloud` tạo public zone, A/CNAME, đọc zone và xem change operation.
4. Mô tả cách chuyển API sang IP mới có thời gian hạ TTL, kiểm thử và rollback.
5. Giải thích lý do DNS chưa hoạt động công khai chỉ sau khi tạo zone trong Console.
6. Đề xuất IAM cho platform, developer và pipeline để tránh ai cũng có `roles/dns.admin`.
7. Giải thích tác động nếu registrar có DS cũ không khớp DNSKEY của zone mới.

## Tài liệu tham khảo chính thức

- [Cloud DNS overview](https://cloud.google.com/dns/docs/overview) — chức năng dịch vụ và public/private zones.
- [Create, modify and delete zones](https://cloud.google.com/dns/docs/zones) — tạo zone và NS/SOA mặc định.
- [Add, update, and delete records](https://cloud.google.com/dns/docs/records) — RRset, transaction, CNAME.
- [Set up DNS records for a domain](https://cloud.google.com/dns/docs/set-up-dns-records-domain-name) — cấu hình và delegation.
- [DNSSEC configuration](https://cloud.google.com/dns/docs/dnssec-config) — bật và tắt DNSSEC.
- [Activate DNSSEC at registrar](https://cloud.google.com/dns/docs/registrars) — DS và chuỗi tin cậy.
- [DNS routing policies and health checks](https://cloud.google.com/dns/docs/routing-policies-overview) — WRR, geolocation và failover.
- [Cloud DNS logging and monitoring](https://cloud.google.com/dns/docs/monitoring) — query logging, theo dõi changes.
- [Cloud DNS pricing](https://cloud.google.com/dns/pricing) — chi phí zone và query.
- [gcloud dns reference](https://cloud.google.com/sdk/gcloud/reference/dns) — cú pháp CLI.
