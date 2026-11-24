# Region, availability zone, endpoint và vị trí lưu trữ dữ liệu

Một ứng dụng Spring Boot có thể chạy ở Singapore, gọi API qua một tên miền toàn cầu, ghi dữ liệu vào bucket ở khu vực khác và đồng bộ bản sao sang khu vực thứ ba. Nếu chỉ nhìn vào endpoint, ta rất dễ hiểu sai **dữ liệu nằm ở đâu**, **dịch vụ chịu được sự cố nào** và **ai chịu chi phí truyền dữ liệu liên vùng**. Bài này giúp phân tách bốn khái niệm: **region**, **availability zone**, **endpoint** và **data location**.

Trong chương **Nền tảng đám mây** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**, những khái niệm này là tiền đề để thực hành tích hợp Spring Boot với dịch vụ managed trên **AWS, Microsoft Azure và Google Cloud** thông qua các thư viện Spring Cloud tương ứng. Chọn đúng vị trí ảnh hưởng trực tiếp đến truy cập storage, messaging, database, secret, cấu hình danh tính và quyền, kiểm thử tích hợp, độ trễ, tính sẵn sàng, chi phí và yêu cầu lưu trú dữ liệu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt region, availability zone (AZ), địa điểm edge/local, endpoint toàn cầu và endpoint khu vực.
- Xác định **vị trí lưu dữ liệu** từ thuộc tính của tài nguyên và chính sách sao chép, thay vì suy đoán từ URL hoặc vị trí ứng dụng.
- So sánh khái niệm Region/AZ trên AWS, Azure và Google Cloud, nhận biết giới hạn hỗ trợ tùy dịch vụ và địa điểm.
- Thiết kế triển khai đa AZ, đa region theo mục tiêu RTO/RPO và yêu cầu dữ liệu, hiểu sự khác biệt giữa khả năng chịu lỗi và sao lưu.
- Cấu hình client Spring Boot/Spring Cloud hướng về đúng đích; kiểm tra độ trễ, mạng, quyền, data residency và rủi ro phát sinh phí.
- Chẩn đoán sự cố thường gặp: sai Region, endpoint không khớp, một zone bị lỗi, replicated data ở ngoài phạm vi cho phép.

## 2. Bốn khái niệm lõi

**Region** là một khu vực địa lý do cloud provider công bố để triển khai tài nguyên. Mỗi provider có cách đặt mã region riêng; chúng không dùng chung một danh mục. Nhiều dịch vụ yêu cầu chọn region khi tạo tài nguyên; một số dịch vụ có phạm vi global hoặc multi-region.

**Availability zone (AZ)** là vùng hạ tầng nằm trong một region, được thiết kế làm **failure domain** tương đối độc lập với các zone khác về nguồn điện, mạng hoặc hạ tầng vật lý. AZ giúp phân tán rủi ro lỗi cục bộ nhưng không bảo đảm hoàn toàn độc lập với mọi sự cố và **không thay thế** chiến lược đa region.

**Endpoint** là địa chỉ DNS/URL hoặc cổng mạng mà client kết nối tới dịch vụ. Endpoint có thể toàn cầu, theo region, riêng tư qua private networking hoặc do nhà cung cấp định tuyến. **Vị trí của endpoint không đủ để kết luận vị trí dữ liệu.** Một tên miền toàn cầu vẫn có thể phục vụ dữ liệu lưu ở region cụ thể; một endpoint khu vực cũng không tự bảo đảm mọi bản sao và log chỉ ở region đó.

**Data location** là nơi hệ thống lưu trữ hoặc xử lý dữ liệu, bao gồm dữ liệu chính, bản sao đồng bộ/bất đồng bộ, backup, snapshot, log, metadata và dữ liệu đi qua các hệ thống phụ trợ. Phạm vi bảo đảm phụ thuộc **từng dịch vụ, cấu hình replication, loại dữ liệu và điều khoản sản phẩm**.

| Thuật ngữ | Trả lời câu hỏi | Được quyết định bởi |
|---|---|---|
| Region | Hạ tầng logic của tài nguyên đặt ở khu vực nào? | Cấu hình lúc tạo tài nguyên, đôi khi không đổi được sau khi tạo |
| Availability zone | Tài nguyên cụ thể chạy ở failure domain nào trong region? | Tùy chọn zonal/zonal redundant, scheduler và khả năng hỗ trợ của dịch vụ |
| Endpoint | Ứng dụng gọi địa chỉ nào và qua mạng nào? | SDK/client, DNS, routing, public/private endpoint |
| Data location | Bản dữ liệu, backup, log và bản sao thực tế có thể ở đâu? | Thuộc tính tài nguyên, replication/backup, chính sách địa lý và cam kết dịch vụ |

### 2.1. Region không giống AZ; endpoint không giống data location

~~~mermaid
flowchart LR
    App["Spring Boot workload<br/>Region A"] --> DNS["Service endpoint<br/>global / regional / private"]
    DNS --> R["Tài nguyên dữ liệu chính<br/>Region A"]
    R --> Z1["Availability Zone 1"]
    R --> Z2["Availability Zone 2"]
    R -. "Sao chép nếu bật" .-> DR["Bản sao dự phòng<br/>Region B"]
    DNS -. "Không quyết định" .-> DR
~~~

Sơ đồ mô tả **các quan hệ khái niệm**, không phải sơ đồ triển khai bắt buộc của một dịch vụ. Chẳng hạn, một bucket object storage thường được mô tả ở cấp location/region; người dùng có thể không nhìn thấy AZ vật lý nào lưu từng object. Tương tự, một managed database có thể hỗ trợ multi-AZ nhưng yêu cầu bật chế độ HA và trả thêm phí.

### 2.2. Phạm vi khu vực có thể là nhiều mức khác nhau

Các mức thường gặp gồm: **zonal** (một zone), **regional** (một region, có thể gồm nhiều zone), **dual-region / multi-region** (nhiều region theo mô hình dịch vụ), và **global** (phạm vi quản trị hoặc phục vụ toàn cầu). Hai tài nguyên đều được gọi là “regional” chưa chắc có cùng cơ chế sao chép, tính nhất quán hoặc tính sẵn sàng. Phải tra đặc tính của **chính loại dịch vụ** đang dùng.

Không được suy luận: “region = dữ liệu chỉ ở một datacenter”, “multi-zone = cross-region backup” hoặc “global API = dữ liệu lưu khắp thế giới”. Đó là những khía cạnh độc lập.

## 3. AWS: Region, AZ và cách dùng endpoint

### 3.1. Region và AZ trong AWS

AWS dùng mã region như `ap-southeast-1` (Singapore), `ap-northeast-1` (Tokyo), `us-east-1` (N. Virginia). Các AZ thường xuất hiện dưới tên như `ap-southeast-1a`, `ap-southeast-1b`. Tuy nhiên, **chữ cái AZ có thể ánh xạ sang AZ vật lý khác nhau giữa các AWS account**. Khi cần so sánh cùng một failure domain giữa nhiều account, dùng **AZ ID** (ví dụ dạng `apse1-az1`) theo thông tin AWS cung cấp, không so chữ `a`/`b`.

Với VPC, subnet thuộc một AZ; EC2 instance nằm trong subnet/AZ cụ thể. Để tăng khả năng chịu lỗi, một hệ thống có thể chạy workload qua nhiều subnet ở các AZ khác nhau, dùng load balancer phù hợp và triển khai database có chế độ high availability. Các dịch vụ managed khác nhau có mô hình chống lỗi riêng; không mặc định mọi dịch vụ triển khai nhiều AZ chỉ vì region có nhiều AZ.

AWS còn có Local Zones, Wavelength Zones và Outposts phục vụ trường hợp độ trễ hoặc vị trí cụ thể. Chúng không tương đương một AWS Region độc lập, và **mức hỗ trợ dịch vụ, lưu dữ liệu, khả năng chịu lỗi** cần kiểm tra riêng.

~~~mermaid
flowchart TD
    AWS["AWS Region: ap-southeast-1"] --> A["AZ: ap-southeast-1a"]
    AWS --> B["AZ: ap-southeast-1b"]
    A --> EC1["Ứng dụng / subnet A"]
    B --> EC2["Ứng dụng / subnet B"]
    EC1 --> LB["Load balancing / service routing"]
    EC2 --> LB
    LB --> DB["Managed database<br/>HA theo cấu hình dịch vụ"]
~~~

### 3.2. Endpoint và location của các dịch vụ AWS

- **Amazon S3:** bucket có một **Region** được chọn lúc tạo. Endpoint có thể ở dạng `<bucket>.s3.<region>.amazonaws.com` (ví dụ minh họa cho cấu trúc phổ biến). Bucket S3 thông dụng không được định vị bằng một AZ do ứng dụng chọn; loại bucket chuyên biệt có thể có mô hình zonal khác. Việc SDK chọn sai Region có thể gây redirect, lỗi chữ ký hoặc lỗi location.
- **Amazon SQS:** queue gắn với một Region. URL queue chứa region và account, ví dụ `https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders-prod`. Lấy đúng URL queue và cấu hình client đúng Region; lưu ý AWS partition và endpoint đặc thù.
- **Amazon RDS:** DB instance thuộc Region, có Availability Zone và có thể cấu hình Multi-AZ tùy engine/chế độ. **Multi-AZ HA trong một Region** khác với replica liên Region và khác với chiến lược backup khôi phục ở Region khác.
- **Secrets Manager và AWS KMS:** secret và key có phạm vi region; có khả năng đồng bộ/replication tùy dịch vụ, nhưng phải cấu hình rõ và xem xét quyền, encryption và location từng bản sao.
- **Dịch vụ global hoặc phạm vi đặc biệt:** không áp một quy tắc đặt endpoint duy nhất cho Route 53, CloudFront, IAM, STS hay các dịch vụ khác. Chẳng hạn STS hỗ trợ regional endpoints; behavior có thể phụ thuộc cấu hình SDK và endpoint.

Một kết nối qua **VPC endpoint** hoặc PrivateLink có thể giữ luồng kết nối trên đường mạng riêng được cung cấp, nhưng bản thân cơ chế mạng riêng **không di chuyển** bucket/database sang Region của VPC và không đảm bảo toàn bộ hoạt động xử lý chỉ ở một nơi.

## 4. Azure: Region, availability zone và resource location

Azure dùng tên region như `southeastasia` (Southeast Asia) và `eastasia` (East Asia). Availability zone thường được thể hiện bằng số `1`, `2`, `3` **ở những region và dịch vụ có hỗ trợ**. Không phải region, SKU và dịch vụ nào cũng cho chọn zone hoặc hỗ trợ zone redundancy.

Trong Azure, cần phân biệt:

- **Resource group location** là location của metadata quản trị resource group. Các tài nguyên trong cùng resource group có thể nằm ở nhiều region; không nên suy luận location của resource group chính là nơi lưu dữ liệu của storage account hoặc database.
- **Resource location** là thuộc tính location của từng tài nguyên, ví dụ storage account, virtual machine hoặc managed database. Với dịch vụ nhất định, location chính có thể khác nơi dữ liệu được replicate sang.
- **Zonal resource** đặt ở zone được chọn; **zone-redundant resource** phân tán hoặc được cung cấp khả năng chịu lỗi qua các zone tùy dịch vụ. Một số managed service không cho người dùng trực tiếp nhìn hay chọn từng zone.
- **Region pair và geo-redundancy** là các khái niệm khác với zone redundancy. Azure có các mối quan hệ region-pair cho nhiều region, nhưng **việc có region pair không có nghĩa mọi resource tự động sao chép hoặc failover**. Khả năng geo-replication và failover là cấu hình của từng dịch vụ/SKU.

### 4.1. Vị trí dữ liệu và mức dư thừa của Azure Storage

Azure Storage có các lựa chọn redundancy phổ biến (khả năng sử dụng còn tùy loại tài khoản, dịch vụ và region):

| Chế độ | Ý nghĩa tổng quát | Cần lưu ý |
|---|---|---|
| **LRS** | Duy trì các bản sao trong một location/datacenter thuộc region chính theo mô hình dịch vụ | Không được xem là bảo vệ trước mất toàn bộ region |
| **ZRS** | Đồng bộ dữ liệu qua nhiều availability zone trong một region | Chỉ khả dụng ở region/SKU/dịch vụ hỗ trợ |
| **GRS** | Kết hợp sao chép tại region chính với geo-replication bất đồng bộ sang region phụ | RPO có thể khác 0; không tự đồng nghĩa đọc được dữ liệu phụ |
| **GZRS** | Kết hợp zone redundancy ở region chính và geo-replication sang region phụ | Có giới hạn hỗ trợ và chi phí riêng |
| **RA-GRS / RA-GZRS** | Biến thể hỗ trợ đọc bản sao vùng phụ theo cơ chế dịch vụ | Đọc bản sao phụ có thể trễ; không thay thế chiến lược nhất quán dữ liệu |

Endpoint Blob Storage công khai thường có dạng `https://<storage-account>.blob.core.windows.net`. **Tên host không chứa region**; region được quyết định khi tạo storage account và bởi tùy chọn redundancy. Nếu dùng private endpoint, tên miền và DNS riêng liên quan đến mạng, **không phải tuyên bố mới về vị trí lưu dữ liệu**.

Azure Service Bus namespace, Azure SQL Database, Key Vault và các dịch vụ khác cũng có **resource location** và quy tắc geo-disaster recovery/replication riêng. Không chuyển nguyên giả định về redundancy của Blob Storage sang messaging hoặc database.

### 4.2. Đặt ứng dụng Spring Boot trong Azure

Giả sử Spring Boot chạy trong Azure App Service ở `southeastasia`, còn Azure Storage account ở `eastasia`. Ứng dụng vẫn có thể kết nối qua endpoint hợp lệ và Managed Identity đúng quyền, nhưng đường đi dữ liệu sẽ liên region: độ trễ và egress có thể tăng, đồng thời phải đánh giá yêu cầu residency. **Cùng Azure subscription/resource group không có nghĩa cùng region**.

## 5. Google Cloud: region, zone và location của managed service

Google Cloud có region `asia-southeast1` (Singapore) và các zone có dạng `asia-southeast1-a`, `asia-southeast1-b`, `asia-southeast1-c` khi khả dụng. **Mã region này khác mã của AWS và Azure** dù cùng đại diện một khu vực địa lý. Không ghép trực tiếp mã region giữa các provider khi triển khai đa cloud.

Compute Engine có tài nguyên zonal như VM, regional như regional managed instance group và các resource có phạm vi rộng hơn. GKE có cluster zonal/regional tùy cấu hình. Cloud Run là dịch vụ được triển khai theo region nhưng chi tiết lập lịch zone do nền tảng quản lý.

### 5.1. Location của Cloud Storage

Bucket Cloud Storage có **location** và **location type**: regional, dual-region hoặc multi-region tùy lựa chọn. Ví dụ bucket regional có location `ASIA-SOUTHEAST1`; bucket multi-region có thể dùng một phạm vi rộng như `ASIA` theo quy tắc của Cloud Storage. **Đặt location `ASIA` không có nghĩa chỉ lưu ở Singapore**. Với dual-region/multi-region, phải hiểu phạm vi đặt bản sao, cách replication hoạt động và tùy chọn replication cụ thể.

Một client gọi `storage.googleapis.com` có thể thao tác với bucket lưu tại Singapore. Host này **không xác nhận** bucket đang ở Singapore; phải kiểm tra metadata của bucket. URL object, DNS hay region mà ứng dụng triển khai không thay thế thuộc tính bucket location.

### 5.2. Messaging, database và secret

- **Pub/Sub:** API có thể dùng endpoint mặc định hoặc endpoint được thiết kế cho vị trí nhất định tùy tính năng; việc dữ liệu thông điệp được phép lưu ở đâu liên quan đến **message storage policy** của topic và cấu hình dịch vụ. Chỉ chọn project hoặc endpoint không đủ để suy ra nơi dữ liệu thông điệp được lưu.
- **Cloud SQL:** instance gắn region và zone, có tùy chọn HA liên zone; cross-region replica/backup là phạm vi cấu hình riêng. Vị trí client khác vị trí instance không làm database tự di chuyển.
- **Secret Manager:** secret có các lựa chọn replication theo dịch vụ (ví dụ automatic hoặc user-managed ở các location được hỗ trợ). Cần kiểm tra chính sách replication khi secret có yêu cầu residency.
- **Cloud KMS:** key ring có location; vị trí key, vùng dữ liệu được mã hóa và phương thức sử dụng key là ba yếu tố cần đánh giá riêng.

Organization Policy có thể áp ràng buộc vị trí lên các tài nguyên **mà chính sách/dịch vụ hỗ trợ**. Không mặc định một constraint sẽ kiểm soát mọi kiểu dữ liệu, mọi backup hoặc lưu lượng mạng của tất cả các dịch vụ.

## 6. So sánh nhanh giữa AWS, Azure và Google Cloud

| Câu hỏi | AWS | Azure | Google Cloud |
|---|---|---|---|
| Ví dụ region tại Singapore | `ap-southeast-1` | `southeastasia` | `asia-southeast1` |
| Ví dụ zone | `ap-southeast-1a` (tên ánh xạ theo account) | Zone `1` trong region hỗ trợ | `asia-southeast1-a` |
| Tài nguyên lưu object | S3 bucket có Region; loại/tuỳ chọn quyết định mô hình lưu | Storage account có location và redundancy SKU | Cloud Storage bucket có location/locationType |
| Endpoint thông dụng | Thường theo Region, nhưng nhiều trường hợp khác | Nhiều endpoint theo tên resource, không chứa Region | Nhiều endpoint API toàn cầu; có lựa chọn theo dịch vụ |
| Đa zone | Dịch vụ managed có thể tự cung cấp hoặc yêu cầu cấu hình | Zonal/zone-redundant tùy dịch vụ/SKU | Zonal/regional và HA tùy dịch vụ |
| Sao chép liên region | Theo loại tài nguyên và cấu hình replication | Geo-redundancy/DR theo dịch vụ và SKU | Dual/multi-region, cross-region replication hoặc DR theo dịch vụ |
| Điều kiện residency | Chọn location, replica, backup, log, guardrail | Chọn region, redundancy, geo-copy, policy | Chọn location, replication, policy và scope dữ liệu |

**Điểm mấu chốt:** dù cả ba cloud đều nói “region”, “zone” và “redundant”, ý nghĩa chính xác của **một lựa chọn redundancy** phụ thuộc dịch vụ, không thể dịch máy móc thành tính năng tương đương giữa các provider.

## 7. Chọn location cho hệ thống Spring Boot: sáu yếu tố

### 7.1. Độ trễ

Nếu ứng dụng tại Singapore đọc database ở khu vực xa, mọi truy vấn hoặc transaction đồng bộ phải trả giá cho round-trip qua mạng. Các thao tác nhiều lần gọi nối tiếp thường bị ảnh hưởng rõ hơn so với batch. Để giảm độ trễ, đặt workload và các dữ liệu cần đồng bộ gần nhau khi có thể; đo **p50/p95/p99 latency** từ đúng môi trường chạy và qua đúng loại mạng.

### 7.2. Khả năng sẵn sàng

Chọn một region có nhiều AZ **chưa đủ**. Kiểm tra workload có chạy qua nhiều AZ không, load balancer có định tuyến đến AZ còn khỏe không, database có cấu hình HA/failover không, và messaging có mức chịu lỗi được dịch vụ cam kết không. Thử failure mode trên staging, đọc SLO/SLA của từng dịch vụ.

### 7.3. Chi phí và truyền dữ liệu

Chi phí có thể xuất hiện khi:

- Gọi dịch vụ khác region, chuyển dữ liệu qua các vùng hoặc qua internet.
- Sao chép backup, object, database, log và event sang location dự phòng.
- Dùng SKU redundancy cao hơn, dung lượng lưu bản sao hoặc endpoint riêng.
- Chuyển dữ liệu giữa AZ, qua load balancer/NAT/gateway theo cấu trúc mạng và bảng giá dịch vụ.

Không giả định mọi luồng truyền dữ liệu **trong cùng region** đều miễn phí. Bảng giá thay đổi theo provider, dịch vụ, phương thức mạng và chiều truyền.

### 7.4. Tuân thủ lưu trú dữ liệu

Yêu cầu “dữ liệu khách hàng phải lưu tại khu vực được phép” cần được diễn giải rõ: áp dụng cho **dữ liệu chính, bản sao, backup, log, metadata, dữ liệu xử lý tạm thời và dịch vụ hỗ trợ nào**? Xác định biên giới địa lý/địa phương được phép bằng chính sách tổ chức và hợp đồng, sau đó kiểm tra tài liệu residency của **từng managed service**. Region của một tài nguyên là đầu vào quan trọng nhưng **không phải chứng nhận tuân thủ tự động**.

### 7.5. Danh tính, quyền và khóa mã hóa

Role/IAM/RBAC quyết định ai được thao tác; Region và endpoint quyết định truy cập đâu. Một workload dùng được danh tính hợp lệ vẫn có thể thiếu quyền với secret hoặc key ở region/resource khác. KMS/Key Vault/Cloud KMS có chính sách và location khác nhau; phải kiểm tra key dùng giải mã có phù hợp với thiết kế replication/failover không.

### 7.6. Tính khả dụng của dịch vụ

Không phải region nào cũng hỗ trợ cùng dịch vụ, engine version, machine SKU, storage redundancy, availability zones hoặc quota. Trước khi chốt kiến trúc hãy xác nhận dịch vụ thực sự có ở region đích, cấu hình HA/replication hỗ trợ gì và có ràng buộc về thời điểm tạo tài nguyên hay chuyển vùng không.

## 8. Chọn một AZ, nhiều AZ hay nhiều region?

| Mô hình | Bảo vệ trước | Không tự bảo vệ trước | Sử dụng khi |
|---|---|---|---|
| Một AZ | Một số lỗi ứng dụng khi có restart/backup riêng | Mất cả AZ, sự cố region | Dev/lab hoặc workload chấp nhận downtime |
| Nhiều AZ trong một region | Sự cố một AZ nếu mọi thành phần đều được thiết kế HA | Mất toàn region; lỗi logic, xóa nhầm, corrupt dữ liệu | Production cần HA trong khu vực |
| Nhiều region | Có thể giảm ảnh hưởng sự cố mất region nếu có DR hoàn chỉnh | Lỗi ứng dụng lan rộng, dữ liệu bị xóa đồng bộ, sự cố DNS/identity chung | SLO cao, yêu cầu DR địa lý được cho phép |
| Sao lưu tách biệt | Hỗ trợ khôi phục sau lỗi logic hoặc mất dữ liệu trong phạm vi backup bảo đảm | Không tự cho phép failover tức thời | Mọi môi trường có yêu cầu phục hồi dữ liệu |

**RTO (Recovery Time Objective)** là thời gian gián đoạn tối đa mục tiêu; **RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa mục tiêu tính theo thời gian. Sao chép bất đồng bộ giữa region có thể mang RPO lớn hơn 0; sao chép đồng bộ/zone redundancy cũng không thay thế backup chống xóa nhầm hoặc corruption. Không công bố RPO=0 hay failover tự động nếu dịch vụ và thiết kế chưa bảo đảm.

~~~mermaid
flowchart TD
    U["Người dùng"] --> G["DNS / ingress"]
    G --> P["Primary Region"]
    P --> A1["AZ 1: Spring Boot"]
    P --> A2["AZ 2: Spring Boot"]
    A1 --> DB["Database HA trong Region"]
    A2 --> DB
    DB -. "Replication/backup theo chính sách" .-> DR["Secondary Region: DR"]
    DR --> S["Kiểm tra RPO/RTO và residency"]
~~~

Hai AZ ứng dụng nhưng database một AZ vẫn để lộ **single point of failure**. Tương tự, hai region có database bản sao nhưng thiếu luồng chuyển traffic, secret, quyền, DNS, infrastructure as code và diễn tập phục hồi thì chưa tạo thành hệ thống DR hoạt động.

## 9. Cấu hình client Spring Boot đúng Region và endpoint

### 9.1. Định nghĩa “source of truth” cho đích tích hợp

Một ứng dụng thường có **ba vị trí cần kiểm tra riêng**:

1. **Runtime location:** nơi Spring Boot thực thi (VM/container/managed runtime).
2. **Client target:** Region/endpoint/project/resource ID mà SDK sẽ gửi request đến.
3. **Data placement:** location của tài nguyên và các bản sao/backup được cấu hình.

Spring profile như `prod` chỉ chọn một tập cấu hình ứng dụng; nó không bảo đảm ba vị trí trên khớp nhau. Nên quản lý location qua biến môi trường, cấu hình triển khai hoặc secret/config service được kiểm soát, và kiểm tra giá trị hiệu lực khi khởi động hoặc trước thao tác ghi dữ liệu.

Ví dụ về **cấu hình ứng dụng tự định nghĩa** (không phải key tự động của mọi Spring Cloud starter):

~~~yaml
app:
  deployment:
    provider: aws
    environment: production
    runtime-region: ap-southeast-1
  destinations:
    invoices:
      resource-name: orders-prod-invoices
      expected-region: ap-southeast-1
    orders-queue:
      resource-url: https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders-prod
      expected-region: ap-southeast-1
~~~

Các khóa dưới `app.*` chỉ có tác dụng nếu code tự bind và validate. Khi dùng Spring Cloud AWS/Azure/GCP, các **property và starter thực tế phụ thuộc phiên bản**, cần dùng BOM tương thích với Spring Boot và tài liệu tương ứng; tránh sao chép key từ một thế hệ thư viện sang thế hệ khác.

### 9.2. Ví dụ AWS SDK v2: chọn Region minh bạch

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
class S3ClientConfig {
    @Bean
    S3Client s3Client(@Value("${app.aws.s3-region}") String region) {
        return S3Client.builder()
                .region(Region.of(region))
                // Credential lấy từ default provider chain của SDK.
                .build();
    }
}
~~~

~~~yaml
app:
  aws:
    s3-region: ap-southeast-1
~~~

Ví dụ cần dependency AWS SDK v2 S3 tương thích với dự án. **`app.aws.s3-region` là property do bài học định nghĩa**, không phải property mặc định của Spring Cloud AWS. Mã chọn Region cho S3 client nhưng **không chứng minh** bucket tồn tại ở Region đó: cần kiểm tra bucket region qua API hoặc IaC, đồng thời đối chiếu bucket ARN/name, quyền và endpoint nếu có override. Nếu muốn sử dụng auto-configuration của Spring Cloud AWS, phải kiểm tra cách framework cung cấp bean và property theo version để tránh cấu hình hai client xung đột.

Không nhúng access key hoặc secret key trong code ví dụ. Trên AWS sử dụng role/temporary credentials; ở local dùng profile hoặc cơ chế credential được kiểm soát. Nếu cần kết nối endpoint giả lập trong test, thiết lập endpoint override **riêng cho test**, không mang vào production.

### 9.3. Azure và Google Cloud: location không nhất thiết nằm trong URL

**Azure Blob Storage:** client thường được tạo từ endpoint của **storage account** (ví dụ `https://ordersprod.blob.core.windows.net`) và thông tin xác thực từ `DefaultAzureCredential`/Managed Identity khi phù hợp. Tên storage account không cho biết region; phải truy vấn **`location`, `primaryLocation` và `sku`** của account, sau đó xét geo-redundancy. Việc application chạy tại cùng region không tự bảo đảm data plane và backup cũng ở đó.

**Google Cloud Storage:** SDK truy cập bucket theo tên và project/danh tính thích hợp, thường qua API host không chứa region. Kiểm tra **bucket location và locationType** bằng API hoặc công cụ quản trị. Một giá trị `project-id` đúng không đảm bảo bucket của project đó ở location mong muốn; bucket có location riêng.

**Messaging và databases:** dùng namespace/topic/queue/database **định danh đầy đủ**, các thuộc tính endpoint/region mà SDK yêu cầu và kiểm tra location của resource đích. Với Azure Service Bus, namespace endpoint có dạng `<namespace>.servicebus.windows.net`; với SQS URL có Region; với Pub/Sub project/topic ID phải được xác định rõ. Không áp cách cấu hình S3 sang tất cả các dịch vụ.

### 9.4. Endpoint công khai, private và DNS

Public endpoint là địa chỉ dịch vụ được tiếp cận theo mạng công khai nếu security policy cho phép; private endpoint kết nối dịch vụ qua mạng riêng phù hợp (AWS VPC endpoints, Azure Private Endpoint, Google Cloud Private Service Connect hoặc cơ chế tương ứng tùy dịch vụ). Những lựa chọn này có thể thay đổi **đường đi, DNS, firewall, certificate/TLS và chi phí**, nhưng không tự đổi location/replication của tài nguyên.

Khi override endpoint, không bỏ qua hostname validation/TLS trong production. Nếu một SDK tự định tuyến đến endpoint theo Region, chỉ định endpoint tùy ý có thể vô hiệu hóa hoặc thay đổi hành vi tự động. Dùng đúng tên miền và tham số mà provider công bố cho dịch vụ và partition/cloud tương ứng.

## 10. Xác minh location thực tế qua CLI

Các lệnh dưới đây dành cho người có CLI đã cài đặt và quyền **đọc metadata** phù hợp. Thay các tên ví dụ bằng tài nguyên thật; không dựa hoàn toàn vào default profile của máy local để suy ra danh tính ứng dụng trong production.

### 10.1. AWS CLI

~~~bash
# Danh tính/account hiệu lực
aws sts get-caller-identity

# Region của bucket S3 (một số kết quả có quy ước lịch sử)
aws s3api get-bucket-location --bucket orders-prod-invoices

# Các zone trong region và AZ ID tương ứng
aws ec2 describe-availability-zones --region ap-southeast-1 \
  --query "AvailabilityZones[].{Name:ZoneName,Id:ZoneId,State:State}"
~~~

`get-bucket-location` có khác biệt trả về lịch sử đối với một số Region, ví dụ giá trị `null` có thể đại diện cho `us-east-1`. Trong các chương trình mới, AWS khuyến nghị cân nhắc API **HeadBucket** để xác định Region một cách phù hợp với SDK. Không suy luận location chỉ từ hậu tố tên bucket. Muốn biết replication phải kiểm tra cấu hình replication riêng.

### 10.2. Azure CLI

~~~bash
# Subscription và tenant đang dùng bởi Azure CLI
az account show --query "{tenant:tenantId,subscription:id,name:name}"

# Vị trí thực của storage account và redundancy SKU
az storage account show --name ordersprod --resource-group rg-orders-prod \
  --query "{name:name,location:location,primary:primaryLocation,secondary:secondaryLocation,sku:sku.name}"

# Vị trí của resource bất kỳ theo Azure resource ID
az resource show --ids RESOURCE_ID --query "{name:name,type:type,location:location}"
~~~

Trên Azure, `resource group location` có thể khác `resource location`. Trường `secondaryLocation` có thể rỗng nếu loại tài khoản không có bản sao vùng phụ, hoặc không khả dụng tùy sản phẩm. Muốn xác minh đường dữ liệu thật phải xem thêm storage replication, networking và loại dữ liệu sử dụng.

### 10.3. Google Cloud CLI

~~~bash
# Project mặc định của CLI (khác với resource location)
gcloud config get-value project

# Location và location type của bucket
gcloud storage buckets describe gs://orders-prod-invoices \
  --format="yaml(name,location,locationType)"

# Region/HA mode của Cloud SQL instance
gcloud sql instances describe orders-db \
  --format="yaml(region,settings.availabilityType)"
~~~

Project không phải region; vị trí bucket và database là thuộc tính của từng tài nguyên. `gcloud auth`, Application Default Credentials và service account của runtime có thể khác nhau. Trong tự động hóa, đặt project/credential tường minh và ghi log scope đã xác minh **mà không log token hoặc secret**.

## 11. Thiết kế thử nghiệm tích hợp ba cloud

Giả sử dịch vụ Spring Boot nhận đơn hàng, ghi hóa đơn vào object storage, gửi message lên queue/topic và lưu trạng thái vào managed database. Nhóm triển khai tại Singapore và yêu cầu dữ liệu kinh doanh ở location được phê duyệt.

| Tầng | AWS | Azure | Google Cloud |
|---|---|---|---|
| Runtime | ECS/EKS/EC2 tại `ap-southeast-1` | App Service/AKS tại `southeastasia` | Cloud Run/GKE tại `asia-southeast1` |
| Object storage | S3 bucket Region `ap-southeast-1` | Storage account location `southeastasia` | Cloud Storage bucket location `ASIA-SOUTHEAST1` |
| Messaging | SQS queue ở cùng Region | Service Bus namespace ở cùng Region | Pub/Sub: kiểm tra message storage policy và đặc tính location |
| Database | RDS Region tương ứng và cấu hình HA | Azure SQL/PostgreSQL theo region và HA được hỗ trợ | Cloud SQL Region và HA/backup phù hợp |
| Recovery | Multi-AZ/backup/cross-region nếu được phép | ZRS/geo-redundancy/backup theo dịch vụ | Regional HA, backup/replication theo dịch vụ |

Các resource trong bảng mang tính **thiết kế tham chiếu**, không đồng nghĩa tất cả dịch vụ đều hỗ trợ cùng SKU, redundancy và location ở Singapore. Mỗi provider có mã region và khả năng triển khai riêng; phải xác minh bằng metadata thực và tài liệu dịch vụ.

### 11.1. Kịch bản kiểm thử phải gồm cả negative cases

1. **Đúng Region:** ghi và đọc dữ liệu, đo latency và log resource ID/region đã xác minh.
2. **Sai Region/endpoint:** cố tình cấu hình Region khác ở môi trường test; kỳ vọng SDK xử lý đúng thông báo lỗi hoặc validation chặn trước khi ghi.
3. **Đứt một AZ:** với dịch vụ cho phép, mô phỏng hỏng một node/zone hoặc diễn tập failover theo quy trình được hỗ trợ, kiểm tra request retry và thời gian phục hồi.
4. **Đứt kết nối/endpoint:** thử DNS/private endpoint/network policy, kiểm tra timeout và retry có giới hạn, tránh tạo duplicate message khi retry.
5. **Replica/backup:** kiểm tra điểm khôi phục và thời gian phục hồi từ bản sao; không chỉ nhìn vào công tắc “replication enabled”.
6. **Residency:** truy vấn cấu hình location của dữ liệu chính, replica, backup, secret và log; phát hiện resource ngoài danh sách region cho phép.
7. **Chi phí:** ghi nhận mức truyền dữ liệu giữa zone/region và chi phí replication trong một kịch bản test có giới hạn.

Unit test và emulator có thể xác nhận mapping/cấu hình client, nhưng **không chứng minh** vị trí lưu thật, khả năng chịu sự cố zone, chính sách data residency hay phí mạng thực tế. Các điều này cần kiểm tra ở môi trường cloud cô lập.

## 12. Chẩn đoán lỗi vị trí thường gặp

| Triệu chứng | Giả thuyết cần kiểm tra | Hướng xử lý |
|---|---|---|
| AWS S3 trả lỗi redirect/chữ ký hoặc không tìm được bucket | S3 client sai Region; bucket nằm region khác; endpoint override | Xem Region thực của bucket và cấu hình S3 client; tránh hardcode endpoint sai |
| SQS queue URL hoạt động local nhưng fail khi deploy | Region của SQS client khác Region trong queue URL hoặc role thiếu quyền | So sánh queue URL, runtime credential, Region và IAM policy |
| Azure Blob URL truy cập được nhưng độ trễ cao | App ở region A, storage account region B hoặc đi qua network path không tối ưu | Xem resource location, routing/private endpoint, đo latency/egress |
| Azure Storage có bản sao ngoài phạm vi dự kiến | Chọn GRS/GZRS hoặc cấu hình geo-replication | Kiểm tra SKU, primary/secondary location và chính sách dữ liệu |
| GCP Storage API dùng host global và nhóm không biết dữ liệu ở đâu | Nhầm hostname với bucket location | Đọc bucket location/locationType, kiểm tra policy replication |
| App multi-AZ vẫn gián đoạn khi một AZ mất | Database, cache hoặc worker ở một AZ; load balancing và failover chưa đúng | Kiểm kê mọi thành phần stateful, thử failover có kiểm soát |
| Chuyển DR sang region thứ hai nhưng không giải mã được dữ liệu | Key/secret hoặc quyền không được chuẩn bị cho region DR | Kiểm tra key location, replica/permissions và thứ tự recovery |
| Chi phí network tăng dù dùng dịch vụ cùng cloud | Cross-region calls, traffic qua gateway, replication, zone transfer | Xem billing theo service/resource, đối chiếu sơ đồ đường đi |

### 12.1. Trình tự điều tra

~~~mermaid
flowchart TD
    E["Lỗi hoặc latency tăng"] --> I["Xác minh runtime identity / project / account"]
    I --> C["Đọc client config: Region + endpoint + resource ID"]
    C --> M["Truy vấn metadata resource: location + replication"]
    M --> N["Kiểm tra DNS, network, IAM, key và policy"]
    N --> T["Kiểm chứng bằng request có trace/metric"]
    T --> F["Điều chỉnh và test lại trong staging"]
~~~

Không kết luận lỗi do Region chỉ vì HTTP 403/404: thông điệp có thể xuất phát từ **quyền**, tài nguyên không tồn tại, endpoint sai, DNS, encryption key hoặc network. Nên giữ correlation ID/request ID trong log (không ghi credential/token), so sánh request thực với metadata và policy của đích.

## 13. Checklist trước khi tạo tài nguyên hoặc deploy

- **Region và service availability:** region đích được cho phép, hỗ trợ dịch vụ/SKU/HA/zone mà kiến trúc yêu cầu.
- **Zone/HA:** mọi thành phần quan trọng có mô hình chịu lỗi đúng, không chỉ ứng dụng frontend.
- **Endpoint:** SDK chọn đúng Region/host/project/resource ID; TLS, DNS và private networking được cấu hình phù hợp.
- **Data location:** kiểm tra vùng dữ liệu chính, replica, backup, secret, log, metadata theo cam kết của từng dịch vụ.
- **Identity và key:** runtime identity, IAM/RBAC, region của key/secret và quyền failover phù hợp.
- **RTO/RPO:** có backup, kiểm tra restore, có runbook diễn tập và xác minh mục tiêu thực tế.
- **Chi phí:** đánh giá data transfer, replication, zone traffic, endpoint và vận hành DR.
- **Testing:** có kiểm thử location thực, negative cases, latency và phương án cleanup cô lập.

## 14. Tổng kết

**Region** xác định phạm vi địa lý/hạ tầng của tài nguyên; **availability zone** là phạm vi chịu lỗi bên trong region; **endpoint** là địa chỉ và đường truy cập dịch vụ; **vị trí dữ liệu** phụ thuộc loại tài nguyên và cấu hình sao chép, backup, log. Bốn khái niệm liên quan chặt chẽ nhưng **không thay thế cho nhau**.

Trong tích hợp Spring Boot với Spring Cloud AWS, Spring Cloud Azure hoặc Spring Cloud GCP, hãy luôn đối chiếu **runtime location → client Region/endpoint → resource location → replication/backup policy** trước khi xử lý dữ liệu thật. Sơ đồ này giúp thiết kế latency và HA hợp lý, hạn chế truy cập nhầm vùng, kiểm soát chi phí liên region và đáp ứng các yêu cầu data residency có thể kiểm chứng.
