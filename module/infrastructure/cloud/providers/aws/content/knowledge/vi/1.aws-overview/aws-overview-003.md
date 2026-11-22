# Region, Availability Zone và hạ tầng biên

> **Chương:** Tổng quan AWS  
> **Phạm vi học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hạ tầng AWS để lựa chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

Khi triển khai một ứng dụng lên AWS, câu hỏi đầu tiên không chỉ là “dùng EC2 hay Lambda?” mà còn là **tài nguyên sẽ đặt ở đâu, phần nào cần dự phòng và người dùng truy cập qua mạng nào?** Ba khái niệm nền tảng trả lời câu hỏi đó là **Region**, **Availability Zone (AZ)** và **hạ tầng biên (edge infrastructure)**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt Region, AZ, trung tâm dữ liệu, edge location và các vị trí mở rộng như Local Zone.
2. Giải thích phạm vi hoạt động của tài nguyên theo Region/AZ và hệ quả với VPC, subnet, máy chủ, lưu trữ.
3. Chọn Region dựa trên độ trễ, vị trí dữ liệu, dịch vụ hỗ trợ, yêu cầu phục hồi và chi phí.
4. Thiết kế ứng dụng nhiều AZ để giảm tác động khi một AZ gặp sự cố; biết khi nào phải xem xét nhiều Region.
5. Xác định vai trò của CloudFront, Route 53 và Global Accelerator trong đường đi của một yêu cầu từ người dùng đến ứng dụng.

## 2. Bản đồ tư duy: các lớp hạ tầng của AWS

Một cách hình dung hệ thống là đi từ phạm vi địa lý rộng đến hẹp:

~~~text
Hạ tầng toàn cầu AWS
├── AWS Region (ví dụ: ap-southeast-1, Singapore)
│   ├── Availability Zone A
│   │   └── Một hoặc nhiều trung tâm dữ liệu độc lập
│   ├── Availability Zone B
│   │   └── Một hoặc nhiều trung tâm dữ liệu độc lập
│   └── Availability Zone C
│       └── Một hoặc nhiều trung tâm dữ liệu độc lập
├── Những Region khác (phạm vi địa lý và lỗi khác)
└── Mạng biên toàn cầu
    ├── Points of Presence / edge locations
    ├── Regional edge caches (CloudFront)
    └── Các điểm mạng của dịch vụ phân phối, định tuyến
~~~

Sơ đồ này thể hiện **quan hệ khái niệm**, không phải sơ đồ đấu nối vật lý. Edge location không phải là một AZ nằm trong Region; mạng biên hoạt động trên phạm vi toàn cầu và kết nối đến các hệ thống gốc (*origin*) ở Region hoặc nơi khác.

| Đơn vị | Bản chất | Bài toán chính | Ví dụ |
| --- | --- | --- | --- |
| **Region** | Khu vực địa lý gồm nhiều AZ độc lập | Vị trí dữ liệu, phạm vi triển khai, cách ly sự cố cấp khu vực | `ap-southeast-1` (Singapore) |
| **Availability Zone** | Một hoặc nhiều trung tâm dữ liệu có nguồn điện, mạng, cơ sở vật lý tách biệt trong một Region | Khả dụng khi một vị trí hạ tầng bị lỗi | `ap-southeast-1a` là tên AZ trong một tài khoản |
| **Edge location / PoP** | Điểm hiện diện thuộc mạng biên toàn cầu | Đưa nội dung và khả năng kết nối gần người dùng hơn | Điểm phục vụ yêu cầu CloudFront |
| **Regional edge cache** | Lớp bộ nhớ đệm lớn hơn giữa CloudFront PoP và origin trong các luồng phù hợp | Tăng khả năng tái sử dụng nội dung cache | Cache đối tượng ít phổ biến hơn |
| **Local Zone / Wavelength Zone / Outposts** | Các cách mở rộng hạ tầng AWS tới vị trí có yêu cầu đặc biệt | Độ trễ rất thấp, 5G hoặc triển khai tại cơ sở khách hàng | Phân tích ở mục 6 |

**Điểm mấu chốt:** Region và AZ giúp chọn nơi vận hành và thiết kế khả năng chịu lỗi; hạ tầng biên giúp cải thiện đường đi đến người dùng. Chúng giải quyết những phần khác nhau của kiến trúc.

## 3. AWS Region: chọn khu vực triển khai

### 3.1. Region là gì?

**AWS Region** là một khu vực địa lý riêng biệt mà AWS cung cấp hạ tầng và dịch vụ. Mỗi Region gồm nhiều AZ được thiết kế cách ly với nhau và kết nối qua mạng riêng có băng thông cao, độ trễ thấp. Mỗi Region có mã định danh, ví dụ:

- `ap-southeast-1`: Asia Pacific (Singapore).
- `ap-southeast-3`: Asia Pacific (Jakarta).
- `ap-northeast-1`: Asia Pacific (Tokyo).
- `eu-west-1`: Europe (Ireland).

Khi tạo một tài nguyên **theo Region**, người triển khai chọn Region của tài nguyên đó. Phần lớn dịch vụ không tự động nhân bản tài nguyên sang Region khác chỉ vì các Region đều thuộc AWS. Ví dụ: một cơ sở dữ liệu RDS ở Singapore không tự có bản sao tại Tokyo; muốn có khả năng khôi phục ở Tokyo cần thiết kế bản sao, sao lưu, quy trình chuyển đổi và quyền truy cập tương ứng.

Một số dịch vụ có giao diện hoặc phạm vi **toàn cầu** (chẳng hạn IAM, Route 53, CloudFront), trong khi nhiều tài nguyên khác bị ràng buộc theo Region hoặc AZ. Vì thế, không nên kết luận mọi dữ liệu và mọi chức năng của một ứng dụng đều nằm trong đúng một Region chỉ từ cấu hình của EC2.

### 3.2. Năm tiêu chí chọn Region

| Tiêu chí | Câu hỏi cần trả lời | Cách kiểm chứng |
| --- | --- | --- |
| **Độ trễ** | Người dùng và hệ thống phụ thuộc đang ở đâu? | Đo độ trễ thực tế từ các mạng, địa điểm và thời điểm đại diện; thử đường đi qua CDN nếu sử dụng |
| **Vị trí và quản trị dữ liệu** | Có yêu cầu dữ liệu phải lưu trữ hoặc xử lý trong lãnh thổ nhất định không? | Rà soát quy định, hợp đồng, luồng sao lưu, log, bản sao và cache ở edge |
| **Dịch vụ và tính năng** | Loại máy, database engine, tính năng hoặc quota cần dùng đã khả dụng trong Region chưa? | Kiểm tra trang dịch vụ và quota theo Region tại thời điểm triển khai |
| **Khả dụng và phục hồi** | Kịch bản lỗi phải chịu được là lỗi máy, lỗi AZ hay mất toàn bộ Region? | Xác định mục tiêu RTO/RPO và kiểm tra khả năng khôi phục thực tế |
| **Chi phí** | Giá tài nguyên, lưu lượng ra Internet và truyền dữ liệu có phù hợp không? | Lập dự toán theo Region với AWS Pricing Calculator và giá hiện hành |

**Ví dụ:** doanh nghiệp có khách hàng chủ yếu tại Việt Nam có thể đưa Singapore (`ap-southeast-1`) vào danh sách khảo sát vì khoảng cách địa lý tương đối gần. Tuy nhiên, **không thể kết luận Region này luôn có độ trễ thấp nhất**: nhà mạng, đường truyền, vị trí thiết bị, dịch vụ hỗ trợ và chính sách dữ liệu đều ảnh hưởng đến lựa chọn cuối cùng. Cần so sánh bằng số đo và yêu cầu thực tế.

### 3.3. Region là một ranh giới phục hồi quan trọng

Thiết kế nhiều AZ trong **một Region** có thể chịu được lỗi của một AZ, nhưng không phải chiến lược đầy đủ trước sự cố làm toàn bộ Region không khả dụng. Khi nghiệp vụ bắt buộc tiếp tục hoạt động sau sự cố cấp Region, phải xem xét một Region dự phòng và các thành phần như dữ liệu sao chép, cấu hình hạ tầng, DNS, danh tính/quyền, kiểm thử chuyển đổi.

Chiến lược nhiều Region thường phức tạp và tốn kém hơn. Với ứng dụng chưa có yêu cầu khôi phục cấp Region rõ ràng, thiết kế một Region và nhiều AZ có thể là điểm khởi đầu hợp lý.

## 4. Availability Zone: ranh giới lỗi bên trong Region

### 4.1. AZ hoạt động như thế nào?

Mỗi **Availability Zone** gồm một hoặc nhiều trung tâm dữ liệu với nguồn điện, kết nối mạng và cơ sở vận hành được thiết kế độc lập so với AZ khác. Các AZ trong cùng Region kết nối qua mạng riêng có độ trễ thấp, hỗ trợ kiến trúc phân tán giữa các AZ.

Ví dụ, nếu một ứng dụng chỉ có một máy chủ EC2 tại AZ A, sự cố mất AZ A có thể làm ứng dụng dừng phục vụ. Nếu ứng dụng có các bản sao hoạt động tại AZ A và AZ B, một bộ cân bằng tải có thể chuyển yêu cầu sang bản sao còn khỏe khi AZ A gặp lỗi, **với điều kiện** thành phần còn lại đủ năng lực xử lý và các phụ thuộc cũng sẵn sàng.

AWS thiết kế các Region với nhiều AZ, nhưng **số AZ có thể dùng trong tài khoản và khả năng cấp tài nguyên cụ thể vẫn phải được kiểm tra**. Không nên coi tất cả AZ đều có cùng loại máy, cùng hạn mức hay cùng mức dung lượng tại mọi thời điểm.

### 4.2. Tên AZ và AZ ID không hoàn toàn giống nhau

Tên AZ có dạng `ap-southeast-1a`, `ap-southeast-1b`; **AZ ID** có dạng `apse1-az1`, `apse1-az2`. AZ ID xác định nhất quán cùng một vị trí vật lý giữa các tài khoản. Trong một số Region và với các tài khoản AWS cũ, chữ cái trong tên AZ có thể được ánh xạ khác nhau giữa các tài khoản.

Do đó:

- Khi triển khai trong **một tài khoản**, có thể dùng tên AZ mà AWS trả về cho tài khoản đó.
- Khi đối chiếu vị trí vật lý giữa **nhiều tài khoản**, hãy dựa vào **AZ ID**; đừng giả định chữ “a” của hai tài khoản luôn chỉ cùng một AZ.
- Khi mô tả kiến trúc, nói rõ “hai AZ độc lập” quan trọng hơn việc cố định một cặp chữ cái.

### 4.3. Phạm vi tài nguyên: Region, AZ hay toàn cầu?

Không phải mọi tài nguyên trong một ứng dụng có cùng mức độ dự phòng. Cần biết dịch vụ nào triển khai theo AZ và dịch vụ nào tự quản lý khả dụng ở phạm vi Region.

| Tài nguyên / dịch vụ | Phạm vi cần nhớ | Hệ quả thiết kế |
| --- | --- | --- |
| **VPC** | Gắn với một Region; có thể chứa subnet ở nhiều AZ | Tạo một mạng logic cho ứng dụng trong Region |
| **Subnet** | Nằm trọn trong **một AZ**, không trải qua nhiều AZ | Cần subnet riêng tại từng AZ muốn triển khai |
| **EC2 instance** | Chạy trong một AZ | Muốn chịu lỗi AZ cần thêm instance/nhóm triển khai tại AZ khác |
| **EBS volume** | Gắn với một AZ | Volume không tự di chuyển sang AZ khác; xem xét snapshot, backup và phục hồi |
| **Application Load Balancer** | Cấu hình ở cấp Region và hoạt động tại các AZ được bật | Chỉ định subnet từ ít nhất hai AZ; đặt target khỏe tại nhiều AZ |
| **Amazon RDS Multi-AZ** | Triển khai cơ chế dự phòng qua AZ theo lựa chọn cấu hình | Giúp failover database; không đồng nghĩa ứng dụng tự chịu mọi lỗi |
| **Amazon S3 Standard** | Lưu trữ đối tượng ở cấp Region, có khả năng dự phòng qua nhiều AZ do dịch vụ quản lý | Không tự chọn AZ cho từng object; phân biệt với lớp lưu trữ một AZ như S3 One Zone-IA |
| **CloudFront / Route 53** | Dịch vụ vận hành trên hạ tầng toàn cầu | Không xem chúng như một EC2 instance đặt tại một AZ |

Ví dụ quan trọng với mạng: tạo VPC `10.20.0.0/16` **không** có nghĩa là tạo một subnet khổng lồ xuyên AZ. Có thể chia thành:

| Subnet ví dụ | CIDR | Vị trí | Vai trò |
| --- | --- | --- | --- |
| `public-a` | `10.20.0.0/24` | AZ A | Thành phần cần kết nối công khai theo thiết kế |
| `public-b` | `10.20.1.0/24` | AZ B | Dự phòng cho lớp public |
| `app-private-a` | `10.20.10.0/24` | AZ A | Máy chủ ứng dụng nội bộ |
| `app-private-b` | `10.20.11.0/24` | AZ B | Máy chủ ứng dụng nội bộ |
| `db-private-a` | `10.20.20.0/24` | AZ A | Subnet cho lớp dữ liệu |
| `db-private-b` | `10.20.21.0/24` | AZ B | Subnet cho lớp dữ liệu |

Đây chỉ là sơ đồ địa chỉ ví dụ; cấu hình thực tế còn cần route table, security group, network ACL (nếu áp dụng), Internet Gateway, NAT hoặc VPC endpoint và các quy tắc bảo mật phù hợp. **“Public subnet”** được xác định bằng tuyến đến Internet Gateway, không chỉ vì subnet có chữ “public” trong tên.

## 5. Hạ tầng biên: đưa trải nghiệm đến gần người dùng

### 5.1. Edge location và Point of Presence

Mạng biên AWS gồm các **Point of Presence (PoP)** phân bố tại nhiều khu vực mạng. Thay vì mọi yêu cầu đều đi đến máy chủ gốc ở một Region xa, một số dịch vụ có thể xử lý, phân phối hoặc tối ưu đường đi tại điểm gần người dùng hơn.

Một **edge location** không phải nơi mặc định để chạy mọi dịch vụ AWS. Nó cũng không thay thế Region, AZ hoặc yêu cầu dự phòng cho ứng dụng và cơ sở dữ liệu ở origin.

### 5.2. Ba dịch vụ dễ nhầm lẫn

| Dịch vụ | Việc chính | Tình huống phù hợp | Điều không nên hiểu nhầm |
| --- | --- | --- | --- |
| **Amazon CloudFront** | CDN phục vụ nội dung HTTP(S), sử dụng cache và mạng biên; có thể chuyển yêu cầu tới origin | Ảnh, CSS, JavaScript, video, trang web, một số API | Có CDN **không** đồng nghĩa database hoặc toàn bộ API chạy tại edge |
| **Amazon Route 53** | DNS được quản lý; hỗ trợ nhiều chính sách định tuyến và health check | Trả lời tên miền, định tuyến/đổi đích khi điều kiện thay đổi | DNS trả địa chỉ cho trình duyệt; bản thân DNS không truyền toàn bộ dữ liệu trang web |
| **AWS Global Accelerator** | Cung cấp địa chỉ IP anycast tĩnh và tối ưu tuyến mạng tới endpoint ứng dụng, hỗ trợ chuyển hướng khi endpoint lỗi | Dịch vụ TCP/UDP, ứng dụng cần kết nối toàn cầu ổn định | Không phải CDN lưu bản sao ảnh, HTML hoặc video |

**Luồng CloudFront đơn giản:**

1. Trình duyệt truy cập một URL; DNS giúp xác định đích kết nối phù hợp.
2. Yêu cầu đi tới một CloudFront PoP được mạng lựa chọn dựa trên điều kiện định tuyến.
3. Nếu đối tượng được phép cache và đang có bản hợp lệ (*cache hit*), PoP trả nội dung từ cache.
4. Nếu *cache miss*, CloudFront tìm nội dung ở lớp cache tiếp theo khi phù hợp hoặc chuyển yêu cầu đến **origin** (ví dụ S3, ALB, máy chủ web), rồi trả kết quả cho trình duyệt.
5. Dữ liệu cache có thể phục vụ các yêu cầu sau theo chính sách TTL, đường dẫn, header, cookie, query string và các cấu hình liên quan.

**Chú ý dữ liệu nhạy cảm:** Không được cấu hình cache dùng chung cho nội dung cá nhân hóa nếu chưa kiểm soát cache key, quyền truy cập và chính sách cache. Với API đặt hàng, thanh toán hoặc dữ liệu tài khoản, cần quyết định rõ yêu cầu nào được cache và yêu cầu nào phải đi đến origin.

**Regional edge cache** trong CloudFront là lớp cache lớn hơn nằm giữa PoP và origin đối với các luồng áp dụng được. Từ “regional” trong tên này **không biến nó thành AZ hay Region nơi bạn triển khai database**.

### 5.3. Có thể xử lý logic tại edge không?

Có, nhưng khả năng và giới hạn tùy dịch vụ:

- **CloudFront Functions** thích hợp cho thao tác nhẹ ở tầng HTTP như điều chỉnh URL, header hoặc cache key.
- **Lambda@Edge** hỗ trợ logic tùy biến phức tạp hơn trong các sự kiện của CloudFront, với ràng buộc riêng về runtime, quyền và triển khai.

Chỉ nên đưa phần logic phù hợp ra edge. Các giao dịch yêu cầu nhất quán dữ liệu, quyền truy cập cơ sở dữ liệu và quy trình nghiệp vụ chính vẫn cần một kiến trúc origin rõ ràng.

## 6. Local Zones, Wavelength Zones và AWS Outposts

Ngoài Region/AZ chuẩn và mạng CDN, AWS có những cách đưa hạ tầng tính toán, lưu trữ đến gần vị trí vận hành đặc thù.

| Mô hình | Vị trí và mục tiêu | Khi nào cân nhắc |
| --- | --- | --- |
| **AWS Local Zones** | Phần mở rộng của một Region tại khu vực gần người dùng hơn, cung cấp một tập con dịch vụ | Ứng dụng nhạy độ trễ trong một đô thị, xử lý tương tác thời gian thực |
| **AWS Wavelength** | Đưa một số dịch vụ AWS vào hạ tầng biên mạng 5G của nhà mạng | Ứng dụng thiết bị 5G có yêu cầu độ trễ rất thấp |
| **AWS Outposts** | Hạ tầng AWS được đặt tại trung tâm dữ liệu/cơ sở của khách hàng | Cần xử lý tại chỗ, kết nối hệ thống nội bộ, yêu cầu vị trí đặt thiết bị |

Đây **không phải ba tên gọi khác của CloudFront**. Chúng đặt năng lực tính toán/lưu trữ gần nơi cần xử lý, trong khi CloudFront chủ yếu giải quyết phân phối nội dung và đường đi HTTP(S). Tính năng khả dụng, khu vực hỗ trợ, kết nối về Region mẹ và chi phí phải được kiểm tra riêng trước khi chọn.

## 7. Thiết kế mẫu: website thương mại điện tử phục vụ khách hàng Việt Nam

Giả sử hệ thống có trang danh mục, ảnh sản phẩm, API giỏ hàng và đơn hàng. Nhóm chọn `ap-southeast-1` làm Region **minh họa** sau khi đánh giá độ trễ, tính năng, quy định và ngân sách; chọn hai AZ độc lập để triển khai ứng dụng.

~~~mermaid
flowchart TB
    U["Người dùng / trình duyệt"] -->|1. Tra cứu DNS| DNS["Route 53"]
    DNS -.->|Trả lời DNS| U
    U -->|2. HTTPS| CF["CloudFront PoP / cache"]
    CF -->|3. Cache miss: ảnh, tệp tĩnh| S3
    CF -->|3. API chuyển tới origin| ALB

    subgraph R["Region ap-southeast-1"]
        S3["S3 Standard - lưu trữ ở phạm vi Region"]
        ALB["Application Load Balancer"]
        subgraph A["Availability Zone A"]
            AppA["Ứng dụng A - private subnet"]
            DBA["RDS Primary - trạng thái ban đầu"]
        end
        subgraph B["Availability Zone B"]
            AppB["Ứng dụng B - private subnet"]
            DBB["RDS Standby - trạng thái ban đầu"]
        end
        ALB --> AppA
        ALB --> AppB
        AppA --> DBA
        AppB --> DBA
        DBA -.->|Đồng bộ Multi-AZ| DBB
    end
~~~

*Sơ đồ minh họa đường đi logic và mô hình RDS Multi-AZ DB instance có một standby; không biểu diễn đầy đủ NAT, routing, TLS, bảo mật hay mọi loại topology RDS. Sau failover, vai trò Primary có thể chuyển sang AZ khác.*

### 7.1. Cách các thành phần phối hợp

1. **Route 53** trả lời truy vấn DNS cho tên miền; trình duyệt sau đó kết nối HTTPS đến địa chỉ CloudFront phù hợp.
2. **CloudFront** phục vụ ảnh và tài nguyên tĩnh đã cache; yêu cầu cache miss đi về **S3 Standard**. Đối với API, policy chuyển đến **ALB** và có thể tắt cache cho nội dung động/riêng tư.
3. **ALB** nhận yêu cầu cho ứng dụng và phân phối đến những target khỏe tại **AZ A** và **AZ B**. Nhóm ứng dụng cần triển khai nhiều instance hoặc task ở các AZ và bật health check.
4. **RDS Multi-AZ** giữ một bản dự phòng đồng bộ ở AZ còn lại (đối với kiểu Multi-AZ DB instance một standby); khi lỗi điều kiện phù hợp, RDS có thể tự động failover. Ứng dụng vẫn cần xử lý kết nối bị gián đoạn và retry an toàn.
5. **CloudWatch, nhật ký và cảnh báo** cho biết tỷ lệ lỗi, thời gian đáp ứng, tình trạng target, database, hiệu suất cache; kiểm thử khôi phục xác nhận hệ thống đạt kỳ vọng.

### 7.2. Khi một AZ gặp sự cố

Giả sử AZ A không hoạt động:

- ALB ngừng gửi lưu lượng đến target không khỏe ở AZ A và tiếp tục với target AZ B, nếu AZ B còn đủ năng lực.
- Nếu Primary RDS ở AZ A và cơ chế Multi-AZ hoạt động theo thiết kế, RDS chuyển vai trò sang standby. Có thể xảy ra **gián đoạn ngắn** trong quá trình chuyển đổi, nên ứng dụng cần retry, timeout và quản lý kết nối hợp lý.
- CloudFront vẫn có thể trả những đối tượng đang được cache. Điều này **không đảm bảo** toàn bộ API hoạt động nếu origin hoặc dữ liệu không sẵn sàng.
- Cần xác minh các thành phần còn lại như NAT, dịch vụ nền, hàng đợi, cache, secret, định tuyến và dung lượng đều không tạo ra điểm lỗi đơn.

Nếu **cả Region** không thể phục vụ, hai AZ trong cùng Region không đủ. Muốn khôi phục ở Region thứ hai cần phương án **Disaster Recovery (DR)**, dữ liệu và khả năng triển khai tại đó.

### 7.3. RTO và RPO giúp chọn mức độ dự phòng

- **RTO (Recovery Time Objective):** thời gian gián đoạn tối đa mà nghiệp vụ có thể chấp nhận theo mục tiêu.
- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa cho phép tính theo thời gian theo mục tiêu.

Ví dụ, mục tiêu “khôi phục trong vài phút, mất tối đa vài phút dữ liệu” khác hoàn toàn với “khôi phục trong một ngày từ bản backup”. Không suy ra giá trị RTO/RPO thực tế chỉ từ nhãn **Multi-AZ** hoặc **Multi-Region**: phải đo qua diễn tập, cấu hình cụ thể và quy trình vận hành.

## 8. Chọn kiến trúc cho đúng loại rủi ro

| Nhu cầu thực tế | Mô hình cần xem xét | Lý do |
| --- | --- | --- |
| Thử nghiệm cá nhân, có thể dừng dịch vụ | Một Region, có thể một AZ cho một số thành phần | Đơn giản và ít chi phí hơn, chấp nhận mức chịu lỗi thấp |
| Ứng dụng cần tiếp tục khi một AZ mất | Một Region, **nhiều AZ** cho các tầng quan trọng | Giảm phụ thuộc vào một vị trí vật lý |
| Người dùng ở xa cần tải ảnh và tệp tĩnh nhanh | CloudFront trước origin | Giảm khoảng cách và số lần lấy lại nội dung phổ biến |
| API toàn cầu cần IP tĩnh và tối ưu đường truyền TCP/UDP | Đánh giá Global Accelerator | Tối ưu kết nối đến endpoint, không dựa vào cache nội dung |
| Phải chịu được sự cố mất toàn Region | Thiết kế DR **nhiều Region** theo RTO/RPO | Phục hồi ngoài phạm vi lỗi Region |
| Xử lý gần cơ sở vật lý hoặc mạng 5G | Local Zones, Wavelength hoặc Outposts tùy trường hợp | Đưa một số năng lực xử lý đến vị trí yêu cầu |

### 8.1. Ba hình thức DR cấp Region phổ biến

1. **Backup and restore:** lưu backup có thể phục hồi ở Region khác; chi phí vận hành thường thấp hơn, thời gian khôi phục có thể lâu.
2. **Pilot light / warm standby:** duy trì một phần hoặc phần lớn hạ tầng dự phòng và dữ liệu cần thiết; rút ngắn thời gian chuyển đổi nhưng tăng chi phí, độ phức tạp.
3. **Active-active:** nhiều Region cùng phục vụ; có thể giảm thời gian gián đoạn nhưng phức tạp về dữ liệu, nhất quán, ghi đồng thời, điều phối và vận hành.

Mô hình nào phù hợp phụ thuộc yêu cầu nghiệp vụ, không có một lựa chọn tốt nhất cho mọi ứng dụng.

## 9. Các hệ quả về bảo mật, chi phí và vận hành

**Bảo mật và dữ liệu**

- Kiểm tra IAM theo nguyên tắc đặc quyền tối thiểu, phân tách tài nguyên công khai/riêng tư, TLS, mã hóa và kiểm soát truy cập origin.
- CloudFront là mạng toàn cầu: với yêu cầu lưu trú dữ liệu nghiêm ngặt, phải kiểm tra vị trí cache, log, luồng dữ liệu, dịch vụ toàn cầu và điều khoản cụ thể. Chọn Region cho database **chưa tự giải quyết tất cả vấn đề lưu trú dữ liệu**.
- Không đưa database trực tiếp ra Internet chỉ vì người dùng ở xa; dùng dịch vụ công khai tại lớp tiếp nhận và bảo vệ mạng/lớp ứng dụng phù hợp.

**Chi phí**

- Mỗi bản sao EC2/task, database dự phòng và đường truyền đều có chi phí. **Multi-AZ** tăng khả năng chịu lỗi nhưng cần ngân sách tương ứng.
- Truyền dữ liệu giữa AZ, giữa Region, ra Internet và qua một số dịch vụ trung gian có thể phát sinh các khoản phí khác nhau; phải kiểm tra chính sách giá của từng dịch vụ và đường đi.
- CloudFront có chi phí lưu lượng, request và tính năng liên quan, đồng thời có thể giảm tải origin khi cache hiệu quả. Hãy đánh giá tổng chi phí theo lưu lượng thực tế.
- Nếu cần truy cập ra ngoài từ private subnet, xem xét thiết kế đường egress cho từng AZ và phương án VPC endpoint để giảm phụ thuộc/chi phí khi thích hợp.

**Giám sát và vận hành**

- Theo dõi trạng thái target ALB, tỷ lệ lỗi HTTP, độ trễ đầu cuối, kết nối/cảnh báo RDS, hiệu quả cache và chi phí.
- Tạo cảnh báo có chủ đích; giám sát từ vị trí đại diện người dùng để phát hiện sự cố mạng bên ngoài AWS.
- Diễn tập tình huống “mất một AZ”, “origin chậm”, “cache miss tăng vọt”, “database failover” và, nếu cần, “Region dự phòng tiếp quản”.
- Sử dụng Infrastructure as Code để mô tả subnet, AZ, định tuyến và cấu hình ứng dụng, giúp tái lập môi trường khi phục hồi.

## 10. Bài thực hành đọc hạ tầng (không tạo tài nguyên)

**Điều kiện:** đã cài AWS CLI, cấu hình thông tin xác thực có quyền `ec2:DescribeRegions` và `ec2:DescribeAvailabilityZones`. Các lệnh dưới đây chỉ đọc metadata hạ tầng; kết quả phụ thuộc vào tài khoản và Region.

**Bước 1 — Xem Region và trạng thái truy cập từ tài khoản:**

~~~bash
aws ec2 describe-regions --all-regions --region ap-southeast-1 --query "Regions[].{Region:RegionName,Access:OptInStatus}" --output table
~~~

**Bước 2 — Xem AZ name, AZ ID và trạng thái trong Singapore:**

~~~bash
aws ec2 describe-availability-zones --region ap-southeast-1 --query "AvailabilityZones[].{AZ:ZoneName,AZ_ID:ZoneId,State:State,Type:ZoneType}" --output table
~~~

**Bước 3 — Đọc kết quả:**

- Xác định mã Region thay vì dùng tên địa lý để cấu hình CLI/SDK/IaC.
- Ghi lại những AZ có trạng thái `available`; đối chiếu `AZ` và `AZ_ID`.
- Giả sử tạo subnet tại AZ thứ nhất: giải thích tại sao phải tạo **subnet thứ hai** ở AZ khác nếu cần chạy application theo mô hình Multi-AZ.
- So sánh AWS service availability, giá và độ trễ mạng trước khi quyết định Region cho một ứng dụng thật.

**Bài tập thiết kế trên giấy:** Từ VPC `10.20.0.0/16` ở mục 4, vẽ hai private subnet tại hai AZ, một ALB có target khỏe ở cả hai AZ và một RDS Multi-AZ. Đánh dấu từng điểm có thể khiến hệ thống ngừng phục vụ khi AZ A gặp sự cố; đề xuất cách xử lý từng điểm đó.

## 11. Những nhầm lẫn thường gặp

| Nhận định | Điều cần hiểu đúng |
| --- | --- |
| “Hai EC2 ở cùng AZ là Multi-AZ.” | Hai máy vẫn phụ thuộc cùng AZ; cần triển khai ở **những AZ khác nhau**. |
| “Có hai AZ thì chịu được mọi sự cố AWS.” | Multi-AZ không tự giải quyết sự cố cấp Region, lỗi logic, dữ liệu bị xóa hoặc cấu hình sai diện rộng. |
| “S3 Standard cần tự chọn ba AZ để lưu tệp.” | AWS quản lý sự dư thừa qua nhiều AZ cho lớp lưu trữ này; không đặt từng object vào một AZ cụ thể. |
| “AZ `1a` của hai tài khoản luôn trùng vị trí.” | Một số trường hợp ánh xạ tên khác nhau; dùng **AZ ID** khi cần đối chiếu vật lý giữa tài khoản. |
| “CloudFront làm ứng dụng chạy ở edge.” | Cache và một số hàm ở edge được xử lý gần người dùng; origin và database vẫn cần thiết kế riêng. |
| “Route 53 truyền mọi request đến backend.” | Route 53 phục vụ phân giải/định tuyến DNS; sau đó client kết nối theo kết quả DNS. |
| “CloudFront + hai AZ là đủ cho mọi yêu cầu DR.” | Nếu mục tiêu bao gồm lỗi cấp Region, phải bổ sung thiết kế phục hồi theo RTO/RPO. |
| “Đặt Region gần nhất luôn rẻ và nhanh nhất.” | Cần kiểm thử mạng thực tế, khảo sát giá, dịch vụ và quy định dữ liệu. |

## 12. Tổng kết

Hãy nhớ ba câu hỏi trước khi vẽ kiến trúc AWS:

1. **Region:** Đặt ứng dụng và dữ liệu ở khu vực địa lý nào để cân bằng độ trễ, dịch vụ, tuân thủ, chi phí và nhu cầu khôi phục?
2. **Availability Zone:** Các thành phần quan trọng đã có bản dự phòng tại những vị trí lỗi độc lập trong Region chưa?
3. **Hạ tầng biên:** Người dùng cần nội dung, DNS hay đường truyền được tối ưu như thế nào; phần nào vẫn phải quay về origin?

Một lựa chọn triển khai tốt không dừng ở việc chọn tên Region hoặc đánh dấu “Multi-AZ”. Cần xem **phạm vi lỗi của từng thành phần**, **đường đi của dữ liệu**, **cách giám sát và phục hồi**, rồi kiểm chứng bằng đo lường và diễn tập.

### Tài liệu AWS chính thức để đọc thêm

- [AWS Regions and Availability Zones](https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions-availability-zones.html) — định nghĩa Region, AZ, Local Zone và Wavelength Zone.
- [AWS Availability Zones](https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-availability-zones.html) và [AZ IDs](https://docs.aws.amazon.com/global-infrastructure/latest/regions/az-ids.html) — mã AZ và cách đối chiếu giữa tài khoản.
- [Subnets for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/configure-subnets.html) — phạm vi subnet trong một AZ.
- [How CloudFront delivers content](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/HowCloudFrontWorks.html) — cache tại PoP, regional edge cache và origin.
- [Regions and Zones for Amazon EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-regions-availability-zones.html) — Local Zones, Wavelength và Outposts.
- [Amazon RDS Multi-AZ DB instance deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html) — bản dự phòng và đồng bộ giữa AZ.
- [AWS Well-Architected: Disaster Recovery Strategies](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_planning_for_recovery_disaster_recovery.html) — chọn mức dự phòng theo RTO/RPO.
