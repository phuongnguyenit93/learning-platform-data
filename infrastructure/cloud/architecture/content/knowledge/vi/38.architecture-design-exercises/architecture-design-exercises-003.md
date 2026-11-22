# Thiết kế ứng dụng web từ một khu vực đến nhiều vùng sẵn sàng

## 1. Mục tiêu bài thực hành

Một ứng dụng web có thể đang chạy ổn định trên vài máy chủ trong **một vùng sẵn sàng (Availability Zone, AZ)**. Khi số người dùng tăng, rủi ro từ hỏng phần cứng, mất kết nối mạng hoặc sự cố điện tại AZ đó trở nên đáng kể: ứng dụng có nhiều instance nhưng **tất cả cùng nằm trong một miền lỗi** vẫn có thể ngừng hoạt động đồng loạt.

Bài thực hành thuộc chương **Thực hành thiết kế** của **CLOUD_ARCHITECTURE**. Người học sẽ xuất phát từ yêu cầu nghiệp vụ, phân tích điểm lỗi đơn, rồi thiết kế và diễn tập lộ trình chuyển ứng dụng web từ **một AZ sang nhiều AZ trong cùng một region**. Bài học kết nối quyết định về **mạng, compute, dữ liệu, mô hình triển khai** với đánh đổi về **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành**, đồng thời tự đánh giá theo nguyên tắc **Well-Architected**.

Sau bài học, bạn có thể:

1. Phân biệt **region**, **AZ**, **multi-AZ** và **multi-region**, tránh dùng sai phạm vi bảo vệ.
2. Chuyển mục tiêu sẵn sàng và phục hồi của nghiệp vụ thành các tiêu chí **SLI/SLO, RTO, RPO** kiểm chứng được.
3. Thiết kế kiến trúc web nhiều lớp, đặt đúng thành phần trong từng AZ và xử lý trạng thái phiên, lưu trữ, cơ sở dữ liệu.
4. Lập kế hoạch năng lực khi một AZ mất hoàn toàn, xác định nút nghẽn và chi phí dự phòng.
5. Chọn trình tự migration, cách triển khai, kế hoạch rollback, bài kiểm thử lỗi và điều kiện nghiệm thu.

Đây là **bài tập thiết kế kiến trúc**, với dữ liệu và con số giả định để người học thực hành. Các giới hạn dịch vụ, mức SLA, khả năng đồng bộ dữ liệu, tên sản phẩm và chi phí cụ thể phải được kiểm tra lại theo nhà cung cấp và cấu hình thực tế trước khi triển khai.

### 1.1. Hiểu đúng các đơn vị địa lý

| Khái niệm | Ý nghĩa | Hỏng hóc được giảm rủi ro |
|---|---|---|
| **Region (khu vực)** | Vị trí địa lý logic của một nhà cung cấp cloud, có thể chứa nhiều AZ | Lựa chọn vị trí lưu trú dữ liệu, độ trễ và phạm vi dịch vụ |
| **Availability Zone (vùng sẵn sàng)** | Miền hạ tầng riêng biệt trong một region, được thiết kế để giảm lỗi chung với AZ khác | Sự cố ảnh hưởng đến một AZ riêng lẻ |
| **Multi-AZ** | Đặt thành phần hoặc bản sao quan trọng trên ít nhất hai AZ trong **cùng region** | Giảm nguy cơ ứng dụng ngừng toàn bộ khi một AZ gặp sự cố |
| **Multi-region** | Triển khai hoặc sao chép dịch vụ qua nhiều region | Có thể hỗ trợ ứng phó sự cố cấp region, với điều kiện failover và dữ liệu được thiết kế phù hợp |

**Giới hạn thiết kế:** multi-AZ không đồng nghĩa multi-region. Lỗi cấp region, lỗi cấu hình dùng chung, xóa dữ liệu nhầm, thông tin xác thực bị lộ hay lỗi ứng dụng được phát hành đồng loạt vẫn có thể tác động đến toàn bộ các AZ. Vì thế, nhiều AZ là một lớp của chiến lược tin cậy, không phải bảo đảm không gián đoạn tuyệt đối.

## 2. Đề bài nghiệp vụ: cổng bán hàng đang tăng trưởng

Bạn phụ trách kiến trúc cho **ShopHub**, một ứng dụng web bán hàng giả định. Hiện tại toàn bộ web frontend, API, worker nền và một database duy nhất đều chạy trong AZ-A của một region. Hệ thống đã từng gián đoạn khi AZ-A mất kết nối. Nhóm sản phẩm muốn tiếp tục vận hành khi **bất kỳ một AZ riêng lẻ** không còn phục vụ.

Các giả định về tải và yêu cầu:

| Thuộc tính | Giá trị bài tập | Ghi chú |
|---|---:|---|
| Lưu lượng giờ bình thường | 300 request/giây | Tổng request vào web/API |
| Lưu lượng đỉnh cần hỗ trợ | 1.200 request/giây | Có thể duy trì ít nhất 15 phút |
| Quy mô dữ liệu ban đầu | 2 TB dữ liệu đơn hàng và tài khoản | Cần chọn chiến lược backup và replica |
| Tệp người dùng | 5 TB ảnh sản phẩm, hóa đơn | Không đặt trên ổ đĩa cục bộ của app |
| SLO sẵn sàng dịch vụ | 99,95% trong mỗi cửa sổ 30 ngày | Định nghĩa cụ thể request hợp lệ trong đo lường |
| SLO độ trễ | p95 dưới 400 ms đối với đọc danh mục khi không có sự cố | Đọc danh mục khác với checkout |
| Khôi phục lỗi mất một AZ | RTO không quá 5 phút | Đo từ thời điểm bắt đầu gián đoạn đến khi dịch vụ đạt ngưỡng phục vụ |
| Mất dữ liệu đơn đã xác nhận | Không chấp nhận mất đơn đã báo thành công | Cần xác minh ngữ nghĩa commit/failover của DB |
| Mất dữ liệu sản phẩm phụ trợ | RPO mục tiêu không quá 5 phút | Có thể chấp nhận tái tạo index/cache |
| Bảo mật | Không công khai database; chỉ chủ tài khoản được xem đơn | Phân quyền theo chức năng và dữ liệu |
| Phạm vi | Chịu lỗi **một AZ**, chưa yêu cầu tự động chuyển region | Region outage là bài toán mở rộng khác |

Với 30 ngày = 43.200 phút, SLO **99,95%** tương ứng khoảng **21,6 phút không sẵn sàng** trong cửa sổ đó, theo phép tính đơn giản nếu thời gian và request được tính đều. Trong thực tế SLO có thể theo tỷ lệ request thành công, khi đó **không được suy diễn trực tiếp** từ tỷ lệ request sang phút downtime nếu lưu lượng thay đổi. Mục tiêu RTO 5 phút cho một lần mất AZ cũng **không có nghĩa** có thể để hệ thống mất 5 phút lặp lại nhiều lần mà vẫn đạt SLO.

### 2.1. Câu hỏi cần làm rõ trước khi vẽ sơ đồ

- **Tuyến nghiệp vụ trọng yếu:** danh mục sản phẩm, xem giỏ, đặt hàng, thanh toán và tải ảnh có mức ưu tiên giống nhau không?
- **Tiêu chí “không mất đơn”:** có bắt buộc mọi ghi đã được xác nhận đều còn sau failover? Cơ chế DB nào chứng minh được điều này?
- **SLO khi sự cố:** có cần tiếp tục phục vụ **toàn bộ** 1.200 request/giây khi mất AZ, hay cho phép suy giảm có công bố?
- **Ranh giới phụ thuộc:** dịch vụ thanh toán bên thứ ba, DNS, hệ thống định danh và CDN có nằm ngoài phạm vi kiểm soát không?
- **Ràng buộc triển khai:** có downtime được lên lịch, ngân sách thêm tối đa, yêu cầu giữ IP, dữ liệu residency hoặc điều khoản tuân thủ không?

Trong phần giải mẫu, giả định **tất cả truy cập hợp lệ phải được phục vụ ở đỉnh 1.200 request/giây ngay cả khi mất một AZ**, nhằm buộc kiến trúc phải dự phòng năng lực. Nếu nghiệp vụ cho phép giảm chất lượng dịch vụ, bản thiết kế có thể ít tốn tài nguyên hơn nhưng phải ghi rõ mức giảm và điều kiện chấp nhận.

## 3. Đánh giá kiến trúc ban đầu

~~~mermaid
flowchart LR
    U["Người dùng"] --> D["DNS"]
    D --> LB["Load balancer"]
    subgraph AZA["Region R / AZ-A"]
      APP1["Web + API instance 1"]
      APP2["Web + API instance 2"]
      DB[("Database một máy")]
      DISK[("Đĩa lưu file")]
      W["Worker nền"]
      APP1 --> DB
      APP2 --> DB
      APP1 --> DISK
      APP2 --> DISK
      W --> DB
    end
    LB --> APP1
    LB --> APP2
~~~

**Hai instance trong cùng AZ chưa tạo ra multi-AZ.** Một sự cố mạng hoặc nguồn điện của AZ-A có thể làm cả ứng dụng và dữ liệu ngừng truy cập. Các instance có thể dùng chung DB, ổ đĩa cục bộ, NAT, load balancer hoặc điểm cuối DNS. Chuyển một phần web sang AZ-B nhưng giữ database duy nhất ở AZ-A cũng chưa giải quyết rủi ro dừng giao dịch.

### 3.1. Bảng phân tích điểm lỗi đơn (SPOF)

| Thành phần | Trạng thái ban đầu | Tác động nếu AZ-A mất | Biện pháp cần xem xét |
|---|---|---|---|
| Web/API | Nhiều máy cùng AZ-A | Không còn nơi nhận request | Replica ở AZ-B/C, health check và routing đa AZ |
| Database | Primary duy nhất ở AZ-A | Không đọc/ghi đơn hàng | Chọn HA DB có replica/failover khác AZ, backup và xác minh commit |
| Phiên đăng nhập | Lưu memory từng instance | Mất session, phải đăng nhập lại | Token có thể xác minh độc lập hoặc session store HA |
| Ảnh và hóa đơn | Ổ đĩa cục bộ AZ-A | Có thể không truy cập hoặc mất dữ liệu | Object storage bền vững, quyền truy cập rõ ràng |
| Worker nền | Chạy duy nhất AZ-A | Ngừng xử lý hàng đợi | Worker nhiều AZ, queue bền vững, idempotency |
| Egress / NAT | Một thiết bị hoặc một AZ | Một số request ra ngoài bị gián đoạn | Xem xét egress theo AZ, cơ chế endpoint riêng khi phù hợp |
| Triển khai | Cập nhật toàn bộ cùng thời điểm | Lỗi release ảnh hưởng mọi instance | Rolling/canary và giữ năng lực phục vụ |

**Bài tập nhỏ:** đánh dấu thành phần nào là bắt buộc cho checkout, thành phần nào chỉ ảnh hưởng chức năng phụ. Nếu image service lỗi, có thể tạm phục vụ ảnh placeholder; nếu database đơn hàng lỗi, hệ thống có thể dừng checkout nhưng giữ danh mục nếu có cache phù hợp. Sự phân loại này quyết định thứ tự đầu tư.

## 4. Lựa chọn kiến trúc đích

Để đáp ứng bài toán, chọn một **region có ít nhất ba AZ khả dụng cho các dịch vụ cần dùng**. Nhiều thành phần được trải trên **AZ-A, AZ-B, AZ-C**. Ứng dụng nhận traffic thông qua load balancer có khả năng phục vụ đa AZ; một dịch vụ database được quản lý dùng cơ chế HA liên AZ. Các dịch vụ lưu trữ, queue, quản lý bí mật và giám sát được đánh giá theo **phạm vi chịu lỗi thực tế**, không mặc định “managed” nghĩa là không có SPOF.

~~~mermaid
flowchart TB
    USER["Người dùng"] --> EDGE["DNS + CDN/WAF nếu cần"]
    EDGE --> LB["Load balancer hỗ trợ đa AZ"]
    subgraph REGION["Region R: một region, ba AZ"]
      subgraph A["AZ-A"]
        APPA["App replicas A"]
        WA["Worker A"]
      end
      subgraph B["AZ-B"]
        APPB["App replicas B"]
        WB["Worker B"]
      end
      subgraph C["AZ-C"]
        APPC["App replicas C"]
        WC["Worker C"]
      end
      HA[("DB managed HA / replica khác AZ")]
      OBJECT[("Object storage bền vững")]
      QUEUE[["Queue bền vững"]]
      CACHE[("Cache / session store HA")]
    end
    LB --> APPA
    LB --> APPB
    LB --> APPC
    APPA --> HA
    APPB --> HA
    APPC --> HA
    APPA --> CACHE
    APPB --> CACHE
    APPC --> CACHE
    APPA --> OBJECT
    APPB --> OBJECT
    APPC --> OBJECT
    APPA --> QUEUE
    APPB --> QUEUE
    APPC --> QUEUE
    QUEUE --> WA
    QUEUE --> WB
    QUEUE --> WC
    WA --> HA
    WB --> HA
    WC --> HA
~~~

Sơ đồ trên là **mô hình logic**. Thành phần DB và cache được vẽ gọn thành một nút nhưng có thể gồm primary, standby/replica hoặc thành viên quorum đặt tại những AZ khác nhau; phải làm rõ vai trò và đường failover trong bản triển khai thật. Một database có replica chỉ đọc không tự động giải quyết lỗi ghi nếu chưa cấu hình promote/failover.

### 4.1. Vì sao chọn ba AZ?

Về nguyên tắc, **hai AZ** có thể giúp dịch vụ hoạt động sau khi một AZ mất. Với **ba AZ**, hệ thống có thêm lựa chọn để phân phối tải và, tùy loại database hoặc hệ thống đồng thuận, đạt quorum khi một thành viên bị lỗi. Tuy nhiên, số AZ khả dụng và cơ chế quorum/phân bố replica **phụ thuộc từng dịch vụ**. Không suy ra rằng bất kỳ DB nào chạy trong ba AZ đều tự động chuyển đổi an toàn.

Khuyến nghị dành cho đề bài: **ba AZ cho tầng ứng dụng**, database HA theo mô hình và giới hạn của dịch vụ được chọn. Khi ngân sách hoặc dịch vụ chỉ có hai AZ, cần thiết kế lại bảng dự phòng, rủi ro và RTO thay vì sao chép cấu hình ba AZ một cách máy móc.

### 4.2. Thành phần nào chạy active-active, thành phần nào active-standby?

| Tầng | Mô hình gợi ý | Lý do |
|---|---|---|
| Web/API không giữ trạng thái | **Active-active** ba AZ | Load balancer phân phối request; mất AZ thì AZ còn lại tiếp nhận |
| Worker độc lập | **Active-active** ba AZ | Queue phân phối job; worker ở AZ hỏng có thể bị thay thế |
| Database ghi giao dịch | **Một writer + HA standby**, hoặc multi-writer có hợp đồng consistency được kiểm chứng | Đơn giản hóa tính đúng của ghi đơn hàng; phải có failover được thử nghiệm |
| Cache | HA theo AZ, hoặc xem cache là thành phần tái tạo được | Cache miss không được làm mất dữ liệu nghiệp vụ |
| Object storage | Dịch vụ bền vững phạm vi phù hợp | Không gắn dữ liệu người dùng vào tuổi thọ instance |
| Lớp cân bằng tải | Managed, hỗ trợ định tuyến tới nhiều AZ | Health check và loại bỏ endpoint lỗi nhanh, nhưng cần kiểm chứng SLA và scope |

**Active-active không đồng nghĩa vô hạn năng lực:** AZ còn lại phải có đủ tài nguyên, quota, quyền kết nối và sức chịu tải của database, queue, bộ nhớ đệm, NAT và các hệ thống phụ thuộc.

## 5. Thiết kế mạng và bảo mật

### 5.1. Sơ đồ mạng logic

Trong một VPC/VNet hoặc mạng tương đương, tạo các **subnet riêng cho từng AZ** và phân vai trò:

~~~mermaid
flowchart TB
    INTERNET["Internet"]
    WAF["WAF / CDN, tùy nhu cầu"]
    INTERNET --> WAF
    WAF --> PUBLIC["Public entry: LB đa AZ"]
    subgraph NETWORK["Mạng riêng trong region"]
      subgraph A["AZ-A"]
        AAPP["Private app subnet A"]
        ADB["Private data subnet A"]
      end
      subgraph B["AZ-B"]
        BAPP["Private app subnet B"]
        BDB["Private data subnet B"]
      end
      subgraph C["AZ-C"]
        CAPP["Private app subnet C"]
        CDB["Private data subnet C"]
      end
    end
    PUBLIC --> AAPP
    PUBLIC --> BAPP
    PUBLIC --> CAPP
    AAPP --> ADB
    BAPP --> BDB
    CAPP --> CDB
~~~

Các mũi tên tới data subnet là minh họa phân vùng mạng; **writer database thực tế có thể ở một AZ**, nên request từ mọi app subnet có thể đi tới cùng writer. Bảo mật mạng phải cho phép đường đi hợp lệ liên AZ và từ chối truy cập không cần thiết.

**Ví dụ địa chỉ mạng minh họa:** mạng ứng dụng dùng dải riêng 10.40.0.0/16; phân subnet không chồng lấn, có chỗ trống để autoscale và nâng cấp. Dải CIDR cụ thể cần kiểm tra với mạng nội bộ, kết nối site-to-site và các mạng peering thực tế; không chọn dải trùng với hệ thống đã có.

### 5.2. Quy tắc bảo mật căn bản

1. Chỉ **load balancer/ingress** có endpoint nhận traffic Internet; app instance và database đặt ở subnet riêng, không cấp IP công khai nếu không cần.
2. Bật HTTPS từ người dùng đến ingress, mã hóa giữa các tầng cần bảo vệ; dùng chứng chỉ và cơ chế quản lý secret/identity phù hợp.
3. Firewall/security group hoặc chính sách tương đương chỉ mở **LB → app**, **app → DB/queue/object** trên các giao thức, cổng cần thiết; quyền truy cập cloud theo nguyên tắc tối thiểu.
4. Cấu hình egress phù hợp: nếu worker/app cần gọi ra Internet, cân nhắc NAT/egress độc lập theo AZ để giảm phụ thuộc chéo; dịch vụ cloud nội bộ nên ưu tiên private endpoint khi khả dụng và phù hợp chi phí.
5. Tách quyền ứng dụng đọc/ghi giao dịch, worker, deployer, người vận hành và dịch vụ sao lưu. Lưu audit log cho thay đổi quyền và thao tác nhạy cảm.
6. Giới hạn request ở ingress, bảo vệ DDoS/WAF theo rủi ro, kiểm soát tenant/session ở tầng ứng dụng và mã hóa dữ liệu khi lưu.

Không nên dùng **độ sẵn sàng** làm lý do bỏ qua bảo mật: nhân bản máy chủ qua ba AZ nhưng chia sẻ tài khoản quản trị quá rộng hoặc để database công khai sẽ tăng bề mặt tấn công. Đồng thời tránh đặt lớp kiểm soát bảo mật duy nhất vào một AZ rồi vô tình tạo điểm lỗi đơn mới.

## 6. Thiết kế compute và năng lực chịu mất một AZ

### 6.1. Tính toán năng lực bắt buộc

Giả sử kiểm thử tải cho thấy **một nhóm app instance trong một AZ** được bố trí và đo đạt năng lực **600 request/giây** tại mức độ trễ cho phép. Với ba AZ:

~~~text
Traffic đỉnh cần phục vụ                 = 1.200 request/giây
Số AZ đang hoạt động                      = 3
Số AZ còn lại sau khi mất một AZ          = 2
Năng lực tối thiểu mỗi AZ còn lại         = 1.200 / 2 = 600 request/giây
Tổng năng lực ba AZ tại thời điểm bình thường = 3 × 600 = 1.800 request/giây
Tổng năng lực sau khi mất một AZ          = 2 × 600 = 1.200 request/giây
~~~

Sự dự phòng này tương đương **50% năng lực so với tải đỉnh yêu cầu**, vì bình thường cần 1.200 nhưng đã duy trì 1.800 request/giây năng lực. Nó giúp tiếp tục xử lý đỉnh sau khi mất AZ **mà không phụ thuộc hoàn toàn vào việc autoscale kịp thời**. Nếu chỉ dự trữ 400 request/giây/AZ vì bình thường chia đều 1.200, sau khi mất một AZ chỉ còn 800, thiếu 400 request/giây trước khi có thể mở rộng.

**Lưu ý tính toán:** phép chia trên giả định LB chia tải, instance tương đương, không có nút nghẽn chung và năng lực 600 request/giây đã được kiểm chứng ở p95/p99 đáp ứng SLO. Database, cache, network throughput, pool kết nối, tài nguyên bộ nhớ và quota nhà cung cấp phải chịu được toàn bộ 1.200 request/giây khi chỉ còn hai AZ.

### 6.2. Auto scaling và lịch triển khai

- Dùng autoscaling để tăng hoặc giảm replica dựa trên CPU, concurrency, latency và request rate; không chỉ dựa trên CPU khi ứng dụng I/O-bound.
- Đặt **mức tối thiểu theo AZ** phù hợp khả năng chịu lỗi; cấu hình placement/spread để tránh scheduler vô tình dồn replica vào một AZ.
- Nếu triển khai Kubernetes, dùng **topology spread constraints** hoặc cơ chế tương đương; xem xét pod disruption budgets, readiness, startup/liveness probes và giới hạn node pool theo AZ. Nếu dùng VM hoặc container service managed, cấu hình nhóm instance trên nhiều AZ và kiểm tra phân phối thực tế.
- Rolling deployment cần giữ **năng lực phục vụ sau một AZ mất**; không triển khai đồng thời mọi AZ rồi để số replica khỏe mạnh dưới ngưỡng. Canary hoặc rolling từng vùng thích hợp khi muốn giảm blast radius lỗi phần mềm.
- Phân biệt **instance khỏe mạnh** và **instance sẵn sàng nhận request**: readiness phải phản ánh trạng thái phục vụ, tránh route vào instance vừa khởi động nhưng chưa load xong.

### 6.3. Phiên làm việc và yêu cầu stateless

Ứng dụng có session nằm trong RAM của một instance sẽ làm mất phiên khi LB chuyển request sang AZ khác. Các lựa chọn phổ biến:

- **Stateless access token** có hạn dùng và kiểm tra chữ ký/thu hồi hợp lý; dữ liệu nghiệp vụ không nhét vào token dễ lỗi thời.
- **Session store tập trung có HA** ở nhiều AZ, cấu hình TTL/replication và bảo vệ secret.
- Không lệ thuộc vào **sticky session** như cơ chế chịu lỗi; affinity có thể tăng hiệu năng nhưng không giải quyết sự cố AZ.
- File upload chuyển sang object storage; background job gửi vào queue thay vì lưu cục bộ chờ worker trên một máy.

Hãy thực hiện bài kiểm tra: **đăng nhập → thêm giỏ hàng → vô hiệu hóa instance/AZ đang nhận request → tiếp tục thao tác**. Nếu người dùng bị mất giỏ, phải xác định dữ liệu nào còn nằm trong memory hoặc ổ đĩa của AZ-A.

## 7. Cơ sở dữ liệu: phục hồi ghi quan trọng hơn số lượng replica

Với ứng dụng bán hàng, database là phần khó nhất của multi-AZ. Ba bản sao app stateless vẫn không thể tạo đơn nếu writer database duy nhất nằm trong AZ mất kết nối.

### 7.1. Phân biệt HA và sao lưu

| Cơ chế | Giải quyết vấn đề | Không tự giải quyết |
|---|---|---|
| **Replica/standby khác AZ** | Duy trì bản sao để có thể failover khi primary lỗi | Khả năng failover tự động, consistency và RPO cần xem theo cấu hình |
| **Đồng bộ khi commit** | Có thể bảo vệ các giao dịch đã xác nhận nếu hệ thống chỉ xác nhận sau khi bản sao bền vững nhận ghi | Không tự bảo vệ khỏi xóa nhầm hoặc bug logic |
| **Replica bất đồng bộ** | Giảm độ trễ ghi; tăng read capacity trong một số hệ thống | Có khoảng trễ sao chép, có thể mất các ghi mới nhất khi promote |
| **Backup/PITR** | Phục hồi dữ liệu hỏng hoặc xóa nhầm về thời điểm trước | Không phải đường tự động failover có RTO vài giây |
| **Multi-writer** | Có thể mở rộng hoặc tăng khả năng ghi | Conflict, split-brain, consistency; không thích hợp nếu chưa hiểu hợp đồng DB |

**Yêu cầu không mất đơn đã báo thành công** buộc nhóm kiểm tra hành vi của cơ chế commit, durability và failover được dịch vụ DB bảo đảm. Không nên hứa **RPO = 0** chỉ vì bật một lựa chọn có tên “Multi-AZ”: hãy thử các tình huống primary chết sau commit, connection mất sau commit, failover giữa transaction và replication lag.

### 7.2. Đường chuyển đổi khi primary mất

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Web/API
    participant D as Database endpoint
    participant P as Primary AZ-A
    participant S as Standby AZ-B
    C->>A: Tạo đơn có idempotency key
    A->>D: Ghi đơn trong transaction
    D->>P: Chuyển lệnh ghi
    P--xD: Primary mất kết nối
    Note over D,S: Cơ chế HA phát hiện lỗi, bầu/promote standby
    D->>S: Kết nối writer mới sau failover
    Note over A,D: Hủy kết nối cũ; retry có giới hạn và kiểm tra trạng thái
    A->>D: Tra cứu theo idempotency key
    D->>S: Đọc kết quả đã commit
    S-->>A: Đơn đã tồn tại hoặc chưa hoàn tất
    A-->>C: Trả trạng thái xác thực được
~~~

Đây là **trình tự tình huống chưa rõ kết quả**, không khẳng định transaction đã commit trước khi primary mất. Backend phải **tra cứu theo khóa idempotency** và trả kết quả tương ứng; không tự tạo đơn mới hoặc phát hành thanh toán lần hai khi trạng thái cũ chưa rõ.

### 7.3. Các câu hỏi vận hành DB phải trả lời

1. Khi primary lỗi, dịch vụ xác định standby đủ điều kiện thế nào, ai khởi tạo failover và thường mất bao lâu?
2. Endpoint writer đổi như thế nào? Connection pool có được làm mới, DNS cache có TTL phù hợp và retry có deadline không?
3. Các transaction đang mở bị rollback hay kết quả không xác định? Có idempotency/đối soát với tác vụ quan trọng không?
4. Có nguy cơ đọc dữ liệu cũ nếu ứng dụng chuyển sang replica chỉ đọc? Tuyến đọc nào cần **read-after-write consistency**?
5. Backup, PITR và bài diễn tập **restore sang môi trường cách ly** được kiểm chứng ra sao?
6. Một AZ lỗi có làm giảm số thành viên quorum đến mức hệ thống ngừng ghi không? Nếu có, RTO theo đề bài còn đạt không?

Nếu database hiện tại không thể chuyển sang HA mà không đổi phiên bản hoặc mô hình dữ liệu, hãy xem đây là **đầu việc migration riêng** cần thử nghiệm staging, sao lưu và kế hoạch rollback.

## 8. Các phụ thuộc dữ liệu ngoài database chính

### 8.1. File tĩnh và nội dung người dùng

Ảnh sản phẩm, tài liệu hóa đơn và kết quả xuất báo cáo không nên phụ thuộc vào disk gắn với một AZ. Chuyển sang **object storage** hoặc dịch vụ lưu trữ được quản lý có mức độ bền và sẵn sàng phù hợp. Chọn quy tắc đặt tên object, quản lý phiên bản nếu cần, lifecycle và quyền đọc/ghi. Ứng dụng chỉ tạo URL truy cập theo quyền của người dùng; kho dữ liệu gốc để riêng tư.

Object storage thuộc một region có thể được nhà cung cấp thiết kế phân tán qua nhiều AZ, nhưng **không phải mọi lớp/tier hoặc sản phẩm lưu trữ đều có phạm vi dự phòng giống nhau**. Kiểm tra tài liệu và cấu hình của loại storage được chọn, không tự kết luận chỉ từ tên “object”.

### 8.2. Cache và tìm kiếm

Cache giữ dữ liệu có thể tái tạo nên có thể dùng cụm HA hoặc cơ chế fallback sang nguồn sự thật, nhưng sau một AZ lỗi, cache miss đồng loạt có thể gây **cache stampede** lên database. Hạn chế bằng TTL phân tán, request coalescing, giới hạn concurrency, warmup và rate limiting.

Search index là bản chiếu (*projection*) từ dữ liệu gốc; cần cơ chế replay/rebuild nếu index ở một AZ bị mất. Quy định liệu tìm kiếm là tuyến nghiệp vụ trọng yếu hay được phép tạm giảm chất lượng trong quá trình phục hồi. **Không coi dữ liệu cache hoặc search index là nguồn sự thật của đơn hàng.**

### 8.3. Queue, worker và tác vụ theo lịch

Worker đặt ở nhiều AZ, đọc từ **queue bền vững** có phạm vi HA phù hợp. Worker phải:

- Thực hiện xử lý **idempotent**, bởi một job có thể được giao lại khi worker ở AZ-A bị ngắt sau khi đã bắt đầu làm.
- Giới hạn số lần retry, áp dụng backoff và dead-letter queue (DLQ); không tạo vòng retry vô hạn khi dependency chính đang lỗi.
- ACK message **sau khi** trạng thái nghiệp vụ cần thiết đã được ghi bền vững; dùng lease/visibility timeout khi công việc kéo dài.
- Tránh để **scheduler duy nhất** chạy ở AZ-A; nếu nhiều replica cùng thực thi lịch, dùng leader election/lease hoặc khóa nghiệp vụ để không chạy tác vụ quan trọng nhiều lần.
- Xây dựng quy trình reconciliation cho job dở dang và cảnh báo **oldest message age**, retry rate, DLQ depth.

### 8.4. Phụ thuộc bên ngoài

Payment provider, email, dịch vụ xác thực, hệ thống thuế hoặc API đối tác vẫn có thể ngừng hoạt động ở mức vùng hoặc toàn cầu. Multi-AZ nội bộ không chữa được sự cố của họ. Mô tả fallback theo nghiệp vụ, đặt timeout có deadline, circuit breaker và giới hạn concurrency. Đối với thao tác có side effect như thanh toán, cần idempotency key và đối soát trạng thái khi kết quả không rõ; **không retry mù sau timeout**.

## 9. Thiết kế mục tiêu RTO, RPO và phát hiện lỗi

**Recovery Time Objective (RTO)** là thời gian gián đoạn tối đa được nghiệp vụ chấp nhận cho một tình huống phục hồi đã định nghĩa. **Recovery Point Objective (RPO)** là mức mất dữ liệu tối đa được chấp nhận, thường biểu diễn bằng khoảng thời gian dữ liệu có thể bị mất.

### 9.1. RTO phải tính cả phát hiện và chuyển tải

Ví dụ phân rã RTO **5 phút** khi mất một AZ:

| Bước | Ngân sách minh họa | Cơ chế |
|---|---:|---|
| Phát hiện instance/AZ không đáp ứng | 45 giây | Health check ở LB và monitoring |
| Loại bỏ target lỗi và chuyển routing | 30 giây | LB cập nhật danh sách healthy target |
| App connection recovery/cold cache | 45 giây | Pool tái kết nối, load shedding, cache warm |
| Database failover và reconnect | 90 giây | Managed HA DB; cơ chế endpoint và retry có giới hạn |
| Xác minh giao dịch và ổn định SLO | 60 giây | Synthetic checkout, kiểm tra queue/DB |
| **Tổng ngân sách** | **270 giây = 4,5 phút** | 30 giây dự phòng so với RTO 5 phút |

Các bước có thể **chồng lấp** hoặc kéo dài hơn tùy cloud, dịch vụ, thời gian health check, network và lượng traffic thực. Bảng chỉ là phương án phân ngân sách để **đo và kiểm chứng**; không được quảng bá là thời gian failover nhà cung cấp đã cam kết. Nếu DB failover thực tế p99 là 4 phút, cộng thời gian xác minh và routing có thể vượt RTO, cần đổi phương án hoặc đàm phán lại yêu cầu.

### 9.2. RPO theo từng loại dữ liệu

| Dữ liệu | Yêu cầu thực hành | Cơ chế xác minh |
|---|---|---|
| Đơn hàng đã trả thành công | Không mất bản ghi đã xác nhận | Kiểm tra durability/commit của DB và drill failover; đối soát trạng thái qua idempotency key |
| Thanh toán kết quả chưa rõ | Không được thu hai lần | Provider reference, idempotency key, cơ chế tra cứu và reconciliation |
| Thông tin giỏ hàng | Hạn chế mất trạng thái; xác nhận với nghiệp vụ | Session/cart store HA, kiểm thử khi chuyển AZ |
| Ảnh, tệp đã được xác nhận upload | Giữ nguyên đối tượng | Storage bền vững phù hợp phạm vi và kiểm tra phiên bản/checksum nếu cần |
| Search index và cache | Có thể tái tạo trong giới hạn | Rebuild/replay từ nguồn dữ liệu gốc; kiểm tra backlog |

Một bản backup hằng ngày có thể cần thiết cho phục hồi xóa nhầm, nhưng **không đáp ứng** yêu cầu không mất giao dịch đã xác nhận trong failover AZ. Ngược lại, replica đồng bộ không thay thế được backup vì lỗi xóa dữ liệu có thể được sao chép sang replica.

## 10. Kế hoạch chuyển đổi theo giai đoạn

Migration từ single-AZ sang multi-AZ nên giảm thay đổi đồng thời và giữ các bước có thể đảo ngược. Việc đổi cơ chế database hoặc dữ liệu có thể phức tạp hơn đổi compute; hãy tách rủi ro, kiểm thử rồi mới chuyển traffic sản xuất.

| Giai đoạn | Công việc | Điều kiện hoàn thành |
|---|---|---|
| **0. Baseline** | Đo traffic, latency, error rate, DB throughput, kết nối và dependency; chụp sơ đồ trạng thái ban đầu | Có SLO/SLI và số liệu tải làm mốc so sánh |
| **1. Tách trạng thái ứng dụng** | Chuyển session, file và background job ra khỏi ổ đĩa/RAM instance đơn lẻ | Có thể dừng một instance mà không mất giỏ hàng, file hoặc job |
| **2. Mở rộng mạng** | Tạo app subnet và cấu hình mạng/quyền cho AZ-B/C; kiểm tra route/egress | App trong mỗi AZ kết nối được tới các dependency cần thiết |
| **3. Bổ sung app replica** | Tạo instance/worker ở AZ-B/C; cấu hình LB health check và autoscaling | Thấy traffic thực được chia tới nhiều AZ; đủ năng lực mỗi AZ |
| **4. Bật database HA** | Chọn dịch vụ/mô hình HA, replica/standby, backup/PITR, failover endpoint | Drill DB failover đạt mục tiêu tính đúng và RTO |
| **5. Cô lập phụ thuộc** | Kiểm tra cache/queue, NAT, scheduler, pool và timeout; thêm idempotency | Không còn phụ thuộc sống còn vào AZ-A trong đường giao dịch |
| **6. Chuyển traffic có giám sát** | Canary hoặc tăng traffic theo phần trăm, theo dõi latency/error/DB và rollback criteria | Chỉ tăng sau khi metric đạt ngưỡng đã thống nhất |
| **7. Diễn tập lỗi AZ và nghiệm thu** | Chặn traffic và giả lập mất AZ, đo RTO/RPO/tải/chi phí | Qua checklist, có biên bản và runbook cho trực vận hành |

### 10.1. Chi tiết ở các bước có rủi ro cao

**Trước migration:** tạo bản backup nhất quán, xác nhận restore được vào môi trường thử, lưu snapshot cấu hình và phương án khôi phục connection string/secrets. Khai báo tài nguyên mạng, LB, security policy, autoscaling bằng Infrastructure as Code để có thể tái tạo.

**Chuyển session:** nếu đang dùng session tại một web server, cần triển khai cookie/token hoặc session store phù hợp và kiểm thử đăng nhập trên toàn bộ replica. Đối với giỏ hàng, xác nhận dữ liệu được lưu bền vững; nếu chỉ cache, lựa chọn cơ chế phục hồi khi cache mất.

**Chuyển file cục bộ:** có thể cần copy dữ liệu lịch sử và kiểm tra checksum, phân quyền truy cập, ánh xạ URL cũ. Tránh vừa ghi vào disk cũ vừa đọc object storage mới mà không có quy tắc nhất quán. Với quá trình backfill, ghi nhận vị trí tiến độ và kế hoạch xử lý file thay đổi đồng thời.

**Chuyển database:** replication/bootstrap trên dữ liệu 2 TB có thể kéo dài, làm tăng CPU, I/O và lưu lượng mạng. Đo replication lag, hiệu ứng lên transaction latency và không bật failover trong sản xuất trước khi đã thử. Một số thay đổi cấu hình HA có thể tạo gián đoạn ngắn; lên lịch và thông báo theo quy trình vận hành.

**Traffic canary:** ví dụ tăng theo 5% → 25% → 50% → 100%, giữ mỗi mức đủ lâu để quan sát p95/p99, error rate, database locks và saturation. Đây là ví dụ về *cách tăng dần*, không phải các mức bắt buộc. Thiết kế sticky session và cache phải phù hợp trước khi chuyển người dùng sang target mới.

### 10.2. Điều kiện rollback cụ thể

Rollback không phải “quay mọi thứ về một AZ” nếu DB hoặc dữ liệu đã chuyển sang cấu hình mới. Định nghĩa riêng rollback cho từng giai đoạn:

- **Ở compute/traffic:** nếu error rate hoặc p95 vượt ngưỡng trong canary, ngừng tăng traffic, rút instance lỗi khỏi LB và trả về tập target khỏe mạnh đang có.
- **Ở cấu hình mạng:** giữ cấu hình cuối cùng hoạt động, dùng IaC để phục hồi route/security policy đã kiểm chứng; không xóa subnet/tài nguyên đang còn xử lý giao dịch.
- **Ở dữ liệu:** không tự động rollback schema hoặc restore snapshot cũ sau khi đã có ghi mới. Muốn quay lại phải có migration ngược hoặc quy trình đối soát để tránh mất đơn hàng.
- **Ở chức năng lỗi:** nếu DB chưa sẵn sàng ghi, có thể tạm từ chối checkout có kiểm soát; vẫn phục vụ các chức năng độc lập. Không trả thành công giả cho giao dịch không hoàn tất.

**Hồ sơ thay đổi** phải ghi chủ sở hữu quyết định, thời gian giám sát sau deploy, tín hiệu dừng, runbook, kiểm tra backup và đường liên lạc khi sự cố.

## 11. Diễn tập chịu lỗi: từ giả thuyết đến bằng chứng

Trước khi chạy fault injection, xác nhận phạm vi thử nghiệm, tài nguyên được phép tác động và cơ chế dừng khẩn cấp. Ưu tiên môi trường staging có tải mô phỏng, sau đó chỉ thử ở production với phạm vi, phê duyệt và biện pháp bảo vệ đã được thống nhất.

### 11.1. Ma trận tình huống kiểm thử

| Tình huống | Thao tác thử | Kỳ vọng quan sát |
|---|---|---|
| **Mất một app instance** | Ngừng một instance ở AZ-A | LB loại instance lỗi; request chuyển sang replica khác; session còn hợp lệ |
| **Mất toàn bộ AZ-A của app** | Chặn đường đến toàn bộ app replica AZ-A hoặc mô phỏng AZ failure có kiểm soát | AZ-B/C phục vụ 1.200 req/giây, không vượt ngân sách lỗi/độ trễ của tuyến áp dụng |
| **DB primary nằm ở AZ lỗi** | Chạy cơ chế failover được nhà cung cấp cho phép trong staging | Writer endpoint phục hồi, app reconnect; đơn đã xác nhận vẫn tồn tại |
| **Worker chết giữa job** | Hủy worker sau khi ghi một phần đầu ra | Job được tiếp nhận lại, chạy idempotent, không tạo kết quả trùng |
| **Cache node/AZ lỗi** | Mô phỏng mất một phần cụm cache | App chịu cache miss, DB không bị stampede và dữ liệu nguồn vẫn đúng |
| **Egress của AZ-A lỗi** | Chặn thử đường egress AZ-A | App/worker ở AZ-B/C vẫn gọi được dependency cần thiết |
| **LB/target health check sai** | Cho app trả 200 nhưng không sẵn sàng phụ thuộc quan trọng | Readiness kiểm tra đủ để không đẩy traffic vào target chưa sẵn sàng |
| **Deploy lỗi ở một AZ** | Phát hành bản canary cố tình lỗi trong staging | Không lan đồng loạt sang AZ khác; rollback trước khi tiêu hết error budget |
| **Mất quyền tới object storage** | Mô phỏng lỗi access policy | Từ chối có kiểm soát; cảnh báo và không lộ dữ liệu |
| **Mất kết nối thanh toán sau commit** | Mô phỏng timeout nhận phản hồi | Tra cứu theo idempotency key, không thanh toán/đặt đơn hai lần |

**RTO cần đo từ góc nhìn người dùng**, không chỉ thời gian nhà cung cấp báo “failover completed”. Nếu LB đã route nhưng ứng dụng liên tục 500 do DB pool chưa tái kết nối thì dịch vụ chưa phục hồi.

### 11.2. Kịch bản kiểm thử mất AZ chi tiết

1. Tạo traffic giả gồm đọc danh mục, đăng nhập, thêm giỏ và đặt hàng, tăng đến **1.200 request/giây**. Gắn correlation ID, đặt idempotency key cho checkout, lưu mốc trước thử nghiệm.
2. Ghi baseline 10–15 phút của request rate, p95/p99, HTTP 5xx, CPU, DB connections, cache hit rate, replication lag và queue age.
3. Giả lập mất AZ-A, **giữ nguyên tải gửi vào** thay vì giảm traffic để bài kiểm tra dễ đạt.
4. Xác minh LB ngừng route request mới đến target lỗi; client timeout và retry có giới hạn, không retry chồng tầng vô hạn.
5. Xác minh database failover hoàn tất, connection pool hồi phục, không mất đơn đã xác nhận. Với giao dịch kết quả chưa rõ, dùng idempotency và đối soát.
6. Kiểm tra session/giỏ hàng xuyên AZ, ảnh tải lên, job chưa ACK và các chức năng độc lập.
7. Đo **RTO**, error budget bị tiêu thụ, p95/p99 sau khi ổn định và số request lỗi. Lấy mẫu kết quả nghiệp vụ để đối chiếu với DB.
8. Khôi phục AZ-A, đưa target trở lại từ từ; tránh dồn traffic/cold cache gây sự cố thứ hai; quan sát phân phối tải và replication.
9. Viết biên bản test gồm kết quả, mốc thời gian, chỉ số, giả thuyết sai, khoảng trống cần xử lý, người phụ trách và lịch chạy lại.

Một drill chạy thành công một lần mới chứng minh được **kịch bản được thử trong điều kiện đó**. Muốn tin cậy dài hạn, phải lặp sau thay đổi lớn, kiểm thử dưới tải phù hợp và bao gồm tình huống khôi phục AZ, không chỉ tình huống AZ bị mất.

## 12. Quan sát, cảnh báo và runbook

Để biết thiết kế đạt SLO, cần đo **đầu-cuối**, theo AZ và theo dependency; không chỉ đo CPU instance.

| Nhóm tín hiệu | Metric / log / trace cần có | Dấu hiệu bất thường |
|---|---|---|
| **Người dùng** | Request success rate, p50/p95/p99, synthetic login/checkout | Checkout lỗi dù health check báo app khỏe |
| **Định tuyến** | Healthy targets theo AZ, số request và lỗi mỗi AZ | Một AZ nhận traffic nhưng không đáp ứng |
| **Năng lực** | RPS, concurrent requests, CPU/RAM, container restarts, queue lengths | AZ còn lại không đủ tải sau failover |
| **Database** | Writer status, failover events, replication lag, DB connections, locks, commit latency | App lỗi do endpoint cũ hoặc DB quá tải |
| **Cache/queue** | Cache hit rate, oldest message age, retry, DLQ depth | Job mắc kẹt hoặc DB chịu cache miss lớn |
| **Security** | WAF, auth failures, secret rotation, audit log IAM | Sự cố quyền kết nối hoặc thay đổi cấu hình bất thường |
| **Chi phí** | Compute theo AZ, storage, data transfer liên AZ, NAT, DB HA và log | Chi phí tăng do mạng chéo AZ, dự phòng hoặc log |

**Cảnh báo gợi ý:** số healthy targets giảm dưới mức chịu lỗi; mức tối thiểu replica trong AZ còn lại không đủ; tỷ lệ 5xx hoặc p95 vượt ngưỡng SLO; database failover kéo dài; queue age tiến gần deadline nghiệp vụ; replication lag tăng; chi phí egress tăng bất thường.

Một runbook cho sự cố AZ nên trả lời: ai trực nhận cảnh báo, làm sao xác định AZ lỗi, cách kiểm tra LB routing và database writer, khi nào dừng deploy, cách xử lý giao dịch kết quả chưa rõ, điều kiện mở lại AZ phục hồi và cách tổng hợp báo cáo sự cố. Các thao tác khôi phục thủ công cần được diễn tập và phân quyền trước.

## 13. Phân tích chi phí và đánh đổi

Multi-AZ không miễn phí. Với đề bài yêu cầu chịu mất một AZ ở tải đỉnh, **năng lực dự phòng phải tồn tại ở đâu đó**. Nếu chỉ dựa vào autoscale khi sự cố xảy ra, RTO có thể bị ảnh hưởng bởi thời gian khởi động instance, quota và thiếu tài nguyên AZ.

### 13.1. Mô hình ước lượng đơn giản

Giả định để so sánh, một đơn vị app capacity **600 req/giây** tiêu tốn **C tiền/tháng** (chỉ là ký hiệu):

| Kiến trúc | Năng lực app cấp sẵn | Chi phí app minh họa | Năng lực còn lại sau mất một AZ |
|---|---:|---:|---:|
| Một AZ, hai đơn vị capacity | 1.200 req/giây | 2C | 0 |
| Ba AZ, một đơn vị mỗi AZ | 1.800 req/giây | 3C | 1.200 req/giây |
| Ba AZ, chỉ 400 req/giây mỗi AZ | 1.200 req/giây | Khoảng 2C nếu chi phí tỷ lệ tuyến tính | 800 req/giây, thiếu 400 |

Bảng chỉ xét **năng lực app**, không tính DB, cache, LB, data transfer, NAT, storage, backup, giám sát hoặc giảm giá theo cam kết sử dụng. Giả định **chi phí tỷ lệ tuyến tính** thường không đúng tuyệt đối ở quy mô nhỏ hay với dịch vụ tính tiền theo thời gian khởi tạo, mức sử dụng và số request.

### 13.2. Các khoản tăng và cách tối ưu

- **Compute dự phòng:** instance/container tối thiểu ở nhiều AZ để tiếp nhận failover ngay; kiểm tra tối ưu kích thước máy và scaling theo thời gian thực.
- **Database HA:** standby/replica, lưu trữ và I/O replication, backup/PITR; giá và tính năng phụ thuộc sản phẩm.
- **Network:** data transfer liên AZ, NAT gateway/egress mỗi AZ, lưu lượng tới DB writer ở AZ khác, LB và private endpoint. Không mặc định mọi traffic nội region đều miễn phí.
- **Cache/queue:** cụm HA hoặc dịch vụ managed có giá cao hơn cấu hình đơn nhưng giúp giảm nguy cơ gián đoạn.
- **Observability và vận hành:** metrics, traces, retention log, synthetic monitoring, kiểm thử tải, diễn tập và trực vận hành.
- **Chi phí gián đoạn:** cần so sánh thêm doanh thu/giao dịch mất, uy tín, khối lượng hỗ trợ khách hàng và nghĩa vụ SLA.

**Đổi lấy chi phí thấp hơn:** có thể chấp nhận suy giảm chức năng ít quan trọng khi mất AZ, giảm mức dự phòng của search/index/worker không cần realtime và dùng lưu trữ phù hợp vòng đời dữ liệu. Không cắt dự phòng database giao dịch hoặc làm yếu bảo mật nếu trái yêu cầu nghiệm thu.

## 14. Đánh giá giải pháp theo Well-Architected

| Trụ cột | Câu hỏi đánh giá | Bằng chứng/biện pháp trong bài |
|---|---|---|
| **Operational Excellence – Vận hành xuất sắc** | Có triển khai, rollback và diễn tập được không? | IaC, canary, runbook, nhật ký thay đổi, drill có biên bản |
| **Security – Bảo mật** | Các AZ mới có tuân thủ đúng ranh giới mạng, quyền và mã hóa không? | App/DB subnet riêng, IAM tối thiểu, audit, secrets và quyền object |
| **Reliability – Tin cậy** | Mất một AZ có làm ngừng toàn bộ tuyến giao dịch? | LB multi-AZ, app replica, DB failover, idempotency, backup và kiểm thử RTO/RPO |
| **Performance Efficiency – Hiệu quả hiệu năng** | Sau mất AZ, p95 và năng lực còn đáp ứng tải đỉnh không? | N+1 capacity, kiểm thử 1.200 req/giây, autoscaling, kiểm tra DB/cache |
| **Cost Optimization – Tối ưu chi phí** | Dự phòng nào có ích, khoản liên AZ nào phát sinh? | So sánh C/3C, phân loại chức năng quan trọng, lifecycle và theo dõi mạng |
| **Sustainability – Bền vững** | Có giữ tài nguyên vượt nhu cầu và tái xử lý vô ích không? | Right-sizing, autoscaling hợp lý, lifecycle dữ liệu, giảm retry thừa |

Không có phương án tối ưu duy nhất. **Active-active ba AZ** tăng khả năng chịu lỗi và thường giảm độ trễ failover app nhưng tăng chi phí năng lực nhàn rỗi. **Active-standby** có thể giảm tài nguyên đang chạy ở một số thành phần nhưng cần tính thời gian khởi động/chuyển đổi, tính nhất quán dữ liệu và rủi ro thất bại khi kích hoạt.

Khi lựa chọn, ghi thành **Architecture Decision Record (ADR)**: bối cảnh, yêu cầu SLO/RTO/RPO, phương án đã cân nhắc, quyết định, đánh đổi, rủi ro chưa xử lý và cách kiểm chứng. Đừng chỉ kết luận “đã chọn ba AZ nên sẵn sàng cao”.

## 15. Bài tập áp dụng: tự hoàn thiện bản thiết kế

Hãy làm bài theo vai trò kiến trúc sư. Bạn được phép thay đổi công nghệ nhưng phải giữ các yêu cầu nghiệp vụ đã nêu ở Mục 2, hoặc chỉ rõ yêu cầu nào cần được thương lượng lại.

### Đầu ra cần nộp

1. **Sơ đồ hiện tại và đích**: vẽ region, ba AZ, mạng public/private, load balancer, web/API, worker, data services, DNS và các đường giao tiếp chính.
2. **Bảng SPOF và dependency**: chỉ ra mỗi thành phần lỗi ảnh hưởng tính năng nào, AZ nào, và biện pháp giảm rủi ro.
3. **Bảng SLO/RTO/RPO**: phân biệt tính sẵn sàng API, thời gian phục hồi và mất dữ liệu; nêu cách đo cụ thể.
4. **Capacity plan N+1**: chứng minh có thể xử lý 1.200 req/giây khi mất một AZ và kiểm tra DB, pool, queue, network.
5. **Lộ trình migration**: giai đoạn, điều kiện nghiệm thu, cách phát hành dần, backup và rollback của mỗi bước.
6. **Ma trận chaos/failover test**: ít nhất năm kịch bản, metric quan sát, kết quả kỳ vọng và điều kiện dừng.
7. **ADR một trang**: giải thích vì sao chọn hai hay ba AZ, mô hình DB HA và mức chi phí dự phòng.

### Câu hỏi tự luận

**Câu 1.** Có ba app replica đặt tại ba AZ, nhưng phiên đăng nhập lưu ở một Redis node trong AZ-A. Khi AZ-A lỗi, điều gì xảy ra? Thiết kế sửa là gì?

**Câu 2.** Có hai AZ đang khỏe, mỗi AZ chỉ chịu 400 req/giây, trong khi đỉnh là 1.200 req/giây. Có thể tuyên bố đạt mục tiêu chịu một AZ lỗi không? Bạn sẽ thay đổi gì?

**Câu 3.** Database có read replica ở AZ-B nhưng chỉ asynchronous replication. Sau khi primary AZ-A chết, app phát hiện một đơn đã được báo thành công nhưng không xuất hiện ở replica. Vì sao và cần thay đổi yêu cầu/kiến trúc thế nào?

**Câu 4.** Nhóm vận hành thêm nhiều app instance ở AZ-B/C, nhưng checkout vẫn lỗi khi AZ-A chết. Kể ít nhất ba điểm phụ thuộc cần kiểm tra tiếp.

**Câu 5.** Trong một lần drill, load balancer chuyển request sau 15 giây, nhưng người dùng chỉ đặt hàng thành công trở lại sau 4 phút. Bạn ghi RTO là bao nhiêu? Cần đo ở đâu để tìm khoảng trống?

### Lời giải gợi ý

**Câu 1:** web replica đã đa AZ nhưng session vẫn là SPOF; cần session store HA, token hợp lệ xuyên instance hoặc lưu dữ liệu giỏ hàng trong kho bền vững. Sticky session không bảo vệ khỏi mất AZ.

**Câu 2:** không; sau mất một AZ chỉ còn tối đa 400 req/giây theo giả định hai AZ đang chạy, thấp hơn 1.200. Ngay cả nếu cả hai AZ còn sống, tổng chỉ đạt 800. Cần ba AZ mỗi AZ tối thiểu 600 req/giây như phương án chính, hoặc nếu dùng hai AZ mỗi AZ phải có năng lực 1.200 req/giây; đồng thời kiểm thử tất cả dependency.

**Câu 3:** replica bất đồng bộ có replication lag, nên dữ liệu mới được primary xác nhận có thể chưa đến standby. Cần chọn chế độ commit/HA phù hợp yêu cầu bảo toàn ghi, xác minh thực nghiệm và có đối soát/idempotency. Nếu không đạt được, phải thương lượng lại RPO hoặc thay đổi hệ thống dữ liệu; không tuyên bố zero data loss bằng read replica bất đồng bộ.

**Câu 4:** có thể do database writer còn ở AZ-A, cache/session trong AZ-A, egress/NAT hoặc scheduler duy nhất ở AZ-A, queue chưa HA, DNS/endpoint/secret phụ thuộc AZ-A, hoặc capacity DB không đủ. Cần trace đường checkout từ client tới tất cả dependency.

**Câu 5:** nếu mốc gián đoạn bắt đầu khi người dùng không thể đặt hàng và kết thúc khi đặt hàng lại thành công, **RTO thực đo là khoảng 4 phút**, không phải 15 giây. Xem database failover, connection pool stale, cache cold, retry/timeout, throughput sau mất AZ và synthetic checkout. Kết luận phải nêu điều kiện đo và thời điểm bắt đầu sự cố chính xác.

## 16. Các phản mẫu dễ mắc và checklist nghiệm thu

| Phản mẫu | Vì sao thất bại | Hướng sửa |
|---|---|---|
| Nhân đôi app trong **cùng một AZ** rồi gọi là HA | Một sự cố AZ làm mọi instance ngừng | Phân bố replica qua các AZ khác nhau |
| Có multi-AZ app nhưng database một AZ | Checkout vẫn mất writer | Database HA được thử failover và kiểm tra consistency |
| Dựa hoàn toàn vào autoscale **sau khi** AZ mất | Cold start/quota làm vượt RTO hoặc SLO | Năng lực dự phòng theo N+1 và scale bổ sung |
| Sticky session giữ trạng thái | Mất AZ làm mất session | Session store HA hoặc token/stateless app |
| Dữ liệu người dùng lưu trên disk instance | Mất host/AZ không truy cập được file | Object storage có phạm vi HA phù hợp |
| Chỉ kiểm tra healthy target của LB | Không biết DB hay checkout đang lỗi | Synthetic transaction và SLI đầu-cuối |
| Failover DB bằng thủ công, không có runbook | RTO thực tế khó dự đoán | Chọn cơ chế failover phù hợp, drill và automation |
| Retry tạo đơn/thu tiền không idempotent | Trùng giao dịch khi timeout chưa rõ | Idempotency, đối soát và retry có deadline |
| Phát hành một lần sang mọi AZ | Bug phần mềm ảnh hưởng toàn region | Canary hoặc rolling theo vùng và rollback |
| Nghĩ multi-AZ chống được region outage | Nhầm phạm vi chịu lỗi | Nếu cần, thiết kế bài toán multi-region riêng |

### Checklist để chấp nhận bản thiết kế

- [ ] Xác định rành mạch **region, AZ, miền lỗi và phạm vi không được bảo vệ**.
- [ ] Có SLO/SLI, RTO/RPO cho từng luồng quan trọng và cách đo từ góc nhìn người dùng.
- [ ] Web/API, worker và tài nguyên cần chạy được tại **ít nhất hai AZ còn khỏe** sau khi một AZ mất.
- [ ] Tính và kiểm thử **1.200 req/giây sau mất một AZ**, bao gồm LB, DB, cache, queue, pool và network.
- [ ] Database có kế hoạch HA/failover, backup/restore và kiểm chứng tính đúng của giao dịch đã xác nhận.
- [ ] Session, file, job theo lịch và dữ liệu tạm không phụ thuộc một instance hoặc một AZ.
- [ ] Mạng được phân đoạn, DB không public, các quyền/cloud identities tối thiểu và đường kết nối chéo AZ được kiểm tra.
- [ ] Có kế hoạch migration từng giai đoạn, canary/rolling, điểm dừng, rollback riêng cho dữ liệu.
- [ ] Đo RTO thật bằng synthetic checkout và diễn tập cả **mất AZ lẫn phục hồi AZ**.
- [ ] Cảnh báo theo AZ, đủ runbook và người chịu trách nhiệm xử lý sự cố.
- [ ] Có bảng chi phí dự phòng, DB HA, truyền dữ liệu liên AZ và rủi ro còn lại.
- [ ] Lập ADR và đánh giá đủ sáu trụ cột **Well-Architected**.

### Bài mở rộng sau khi đạt multi-AZ

Giả sử ban giám đốc bổ sung yêu cầu **tiếp tục phục vụ khi toàn bộ region mất kết nối**. Bản thiết kế hiện tại chưa đáp ứng. Hãy khảo sát **multi-region**, chiến lược DNS/traffic failover, sao chép dữ liệu liên region, vấn đề consistency, DNS TTL, capacity của region dự phòng, ràng buộc pháp lý và khả năng quay về region chính. Đó là một bài toán **khác** với chuyển từ một AZ sang nhiều AZ trong cùng region, đòi hỏi RTO/RPO, chi phí và phép thử mới.

**Kết quả mong đợi của bài thực hành:** không dừng ở sơ đồ có nhiều AZ. Bản thiết kế tốt phải chứng minh được rằng một AZ có thể ngừng hoạt động, người dùng vẫn thực hiện giao dịch trong ngân sách gián đoạn đã thỏa thuận, dữ liệu quan trọng được bảo toàn và đội vận hành biết cách phát hiện, khôi phục, kiểm chứng với chi phí chấp nhận được.
