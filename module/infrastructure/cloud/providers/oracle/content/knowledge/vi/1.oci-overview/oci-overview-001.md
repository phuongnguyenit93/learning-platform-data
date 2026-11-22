# OCI là gì và các nhóm dịch vụ cốt lõi

## Mục tiêu bài học

Sau bài học này, bạn có thể giải thích Oracle Cloud Infrastructure (OCI) cung cấp những gì, phân biệt các nhóm dịch vụ chính và mô tả cách chúng phối hợp trong một hệ thống. Bạn cũng có thể nhận diện các quyết định ban đầu về quyền truy cập, vị trí triển khai, dữ liệu, giám sát, chi phí và khả năng phục hồi.

Bài học thuộc phần **Tổng quan Oracle Cloud Infrastructure** của module CLOUD_PROVIDERS_ORACLE. Ví dụ xuyên suốt là một ứng dụng Java quản lý đơn hàng: có API phục vụ người dùng, cơ sở dữ liệu lưu giao dịch và nơi lưu hóa đơn PDF. Đây là ví dụ thiết kế để hiểu dịch vụ; không cần tạo tài nguyên trả phí để theo dõi bài.

## 1. OCI cung cấp điều gì?

**Oracle Cloud Infrastructure** là nền tảng đám mây của Oracle, cung cấp tài nguyên hạ tầng và các dịch vụ nền tảng để xây dựng, triển khai, vận hành ứng dụng. Bạn có thể cấp phát máy chủ, mạng riêng, dung lượng lưu trữ và cơ sở dữ liệu thông qua giao diện web hoặc công cụ tự động hóa.

Một ứng dụng Java chạy trên máy cá nhân thường cần JVM, cấu hình kết nối cơ sở dữ liệu và một thư mục dữ liệu. Khi phục vụ người dùng thật, hệ thống còn cần địa chỉ truy cập ổn định, phân quyền, quản lý bí mật, theo dõi lỗi, sao lưu và khả năng mở rộng. OCI cung cấp các thành phần để đáp ứng những nhu cầu đó; kiến trúc của hệ thống quyết định cách kết hợp chúng.

Có thể hình dung hai mức sử dụng:

| Mức sử dụng | Ví dụ trên OCI | Công việc đội phát triển cần quan tâm |
| --- | --- | --- |
| Hạ tầng như một dịch vụ, IaaS | Máy ảo Compute, mạng VCN, Block Volume | Chọn cấu hình, cài đặt và vận hành phần mềm trên tài nguyên được cấp |
| Nền tảng được quản lý, thường thuộc PaaS | Cơ sở dữ liệu được quản lý, Kubernetes Engine, Functions | Phát triển ứng dụng và cấu hình dịch vụ trong phạm vi trách nhiệm của từng sản phẩm |

Mức độ quản lý không giống nhau giữa các dịch vụ. Chẳng hạn, thuê một VM để tự cài Oracle Database tạo ra khối lượng vận hành khác với dùng một dịch vụ cơ sở dữ liệu có tự động hóa. Vì vậy, khi đánh giá một dịch vụ, hãy xác định **Oracle vận hành phần nào và đội của bạn còn vận hành phần nào**.

OCI hỗ trợ nhiều loại ứng dụng, gồm ứng dụng Java, dịch vụ container, xử lý dữ liệu và hệ thống dùng Oracle Database. Các ứng dụng nghiệp vụ SaaS của Oracle như ERP hoặc HCM thuộc hệ sinh thái Oracle Cloud rộng hơn; lựa chọn OCI để tự triển khai ứng dụng là một quyết định ở lớp hạ tầng và nền tảng.

## 2. Bản đồ các nhóm dịch vụ cốt lõi

Bảng sau phân nhóm theo nhu cầu thiết kế. Đây là bản đồ học tập, không phải danh mục đầy đủ mọi sản phẩm hoặc cách sắp xếp cố định trong Console.

| Nhu cầu | Nhóm dịch vụ | Thành phần tiêu biểu | Ví dụ cho ứng dụng đơn hàng |
| --- | --- | --- | --- |
| Tổ chức tài nguyên, kiểm soát quyền | Quản trị và danh tính | Tenancy, Compartment, IAM | Tách môi trường học tập và production; phân quyền theo nhóm |
| Kết nối các thành phần | Mạng | VCN, subnet, gateway, Load Balancer | Nhận HTTPS từ người dùng và chuyển tới API |
| Thực thi ứng dụng | Tính toán | Compute, Kubernetes Engine, Functions | Chạy dịch vụ Java hoặc tác vụ xử lý hóa đơn |
| Lưu dữ liệu dạng đĩa, tệp và đối tượng | Lưu trữ | Block Volume, File Storage, Object Storage | Lưu dữ liệu đĩa, thư mục dùng chung, hóa đơn PDF |
| Lưu dữ liệu có cấu trúc | Cơ sở dữ liệu | Base Database, Autonomous, Exadata Database Service | Lưu đơn hàng và trạng thái thanh toán |
| Theo dõi hoạt động | Giám sát và quan sát | Monitoring, Logging, Audit | Phát hiện API chậm và truy tìm thay đổi cấu hình |
| Bảo vệ cấu hình và dữ liệu | Bảo mật | IAM, quản lý khóa và secret, Cloud Guard | Giới hạn quyền, bảo vệ thông tin kết nối |
| Tái tạo và thay đổi hạ tầng | Tự động hóa | API, CLI, SDK, Terraform, Resource Manager | Tạo lại môi trường từ cấu hình |
| Theo dõi sử dụng và chi tiêu | Quản trị chi phí | Cost Analysis, Budgets, tags, quotas | Gắn chi phí cho môi trường lab và đặt cảnh báo |

Một dịch vụ có thể phục vụ nhiều mục tiêu. IAM vừa hỗ trợ quản trị vừa là nền tảng bảo mật; tags vừa giúp tổ chức vừa phục vụ phân tích chi phí. Khi đọc tài liệu, hãy liên hệ dịch vụ với yêu cầu cụ thể của hệ thống thay vì chỉ ghi nhớ tên.

## 3. Các khái niệm tổ chức tài nguyên

### 3.1. Tenancy, compartment và tài nguyên

**Tenancy** là phạm vi tài khoản và quản trị của tổ chức trên OCI. Bên trong tenancy, **compartment** nhóm các tài nguyên liên quan để tổ chức và áp dụng quyền truy cập. Compartment là nhóm logic, không phải máy chủ hay mạng riêng. Xem định nghĩa tại [Account and Access Concepts](https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/concepts-account.htm).

Ví dụ tổ chức môi trường:

~~~text
Tenancy của tổ chức
├── learning
│   ├── ứng dụng Java thử nghiệm
│   └── dữ liệu giả lập
├── staging
│   └── hệ thống kiểm thử tích hợp
└── production
    └── hệ thống phục vụ người dùng thật
~~~

Thiết kế này giúp người học xác định nơi được phép tạo tài nguyên và nơi cần bảo vệ chặt hơn. Tuy nhiên, việc tạo compartment chưa tự hoàn thành phân quyền; cần chính sách IAM phù hợp. Compartment cũng không tự chặn lưu lượng mạng giữa hai ứng dụng.

Compartment có phạm vi xuyên region trong tenancy. Cùng một compartment có thể chứa tài nguyên nằm ở các region khác nhau; mỗi tài nguyên vẫn có phạm vi triển khai riêng. Tham khảo [Working with Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/Working_with_Compartments.htm).

### 3.2. IAM trả lời ai được làm gì

**Identity and Access Management (IAM)** quản lý danh tính và quyền truy cập. Cần phân biệt:

- **Xác thực:** danh tính nào đang gửi yêu cầu?
- **Phân quyền:** danh tính đó được phép thực hiện thao tác nào?
- **Phạm vi quyền:** thao tác được áp dụng lên những tài nguyên nào?

Ví dụ, nhóm học viên được quan sát và thao tác tài nguyên trong learning, còn nhóm vận hành được quản lý production. Identity domain hỗ trợ quản lý người dùng và các cấu hình danh tính; policy biểu đạt quyền đối với tài nguyên OCI. Tài liệu nền tảng là [Overview of IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/overview.htm).

Trong thực tế, quyền cần bám sát công việc. Người chỉ đọc chỉ số giám sát không cần quyền xóa cơ sở dữ liệu. Ứng dụng cần ghi hóa đơn vào một nơi lưu trữ cũng không cần quyền quản trị toàn tenancy.

### 3.3. OCID giúp định danh tài nguyên

Nhiều tài nguyên OCI có mã định danh **Oracle Cloud Identifier (OCID)**. Tên hiển thị giúp con người nhận biết; OCID giúp API và công cụ tự động hóa tham chiếu chính xác tài nguyên.

Trong một hồ sơ triển khai, nên ghi rõ tài nguyên nào thuộc compartment nào và được dùng ở region nào. Nếu chỉ ghi tên “order-api”, người vận hành có thể nhầm giữa môi trường staging và production.

## 4. Vị trí triển khai: region, availability domain và fault domain

Ba khái niệm này mô tả các mức vị trí và phân tách hạ tầng:

| Khái niệm | Ý nghĩa | Câu hỏi cần đặt ra |
| --- | --- | --- |
| Region | Khu vực địa lý triển khai các dịch vụ OCI | Độ trễ đến người dùng và yêu cầu vị trí dữ liệu có phù hợp không? |
| Availability Domain, AD | Một hoặc nhiều trung tâm dữ liệu có mức cách ly hạ tầng trong region | Hệ thống chịu được sự cố ở phạm vi AD như thế nào? |
| Fault Domain, FD | Nhóm phần cứng và hạ tầng bên trong AD | Các bản sao ứng dụng có bị tập trung vào cùng nhóm hạ tầng không? |

Mỗi region có số AD và danh mục dịch vụ cần kiểm tra cụ thể. Phạm vi tài nguyên cũng khác nhau: chẳng hạn VCN thuộc region, trong khi Compute instance gắn với AD. Không nên giả định mọi region có cùng cách bố trí hoặc mọi dịch vụ đều triển khai giống nhau. Xem [Regions and Availability Domains](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm).

Đối với ứng dụng đơn hàng, lựa chọn region là quyết định chung cho các thành phần tương tác thường xuyên: API, cơ sở dữ liệu và nơi lưu hóa đơn. Nếu đặt chúng xa nhau mà không có lý do rõ ràng, thời gian kết nối, truyền dữ liệu và xử lý lỗi có thể phức tạp hơn.

Đối với khả năng phục hồi, cần xem phạm vi sự cố. Hai tiến trình trên cùng một VM có thể cùng dừng khi VM gặp lỗi. Hai VM cũng chưa chắc bảo vệ được hệ thống nếu dữ liệu quan trọng chỉ tồn tại ở một thành phần duy nhất. Thiết kế phải xét toàn bộ chuỗi phụ thuộc.

## 5. Networking: tạo đường đi cho yêu cầu

### 5.1. VCN và subnet

**Virtual Cloud Network (VCN)** là mạng riêng ảo trong một region. Subnet chia VCN thành các dải địa chỉ và phạm vi cấu hình mạng.

Ví dụ thiết kế IPv4 cho bài học:

~~~text
VCN: 10.20.0.0/16
├── subnet tiếp nhận: 10.20.1.0/24
│   └── Load Balancer công khai
├── subnet ứng dụng: 10.20.2.0/24
│   └── các VM chạy Java, không gán public IP
└── subnet dữ liệu: 10.20.3.0/24
    └── endpoint riêng của cơ sở dữ liệu đã chọn
~~~

Đây là sơ đồ địa chỉ minh họa. Khi triển khai thật, cần kiểm tra cách đặt endpoint và yêu cầu subnet của dịch vụ cơ sở dữ liệu cụ thể.

Một luồng mạng hoạt động cần đồng thời có địa chỉ phù hợp, đường định tuyến, quy tắc cho phép lưu lượng và dịch vụ đích đang lắng nghe. Có quyền tạo VM trong IAM chưa đủ để gửi HTTP tới ứng dụng trên VM.

### 5.2. Những thành phần thường gặp

| Thành phần | Vai trò chính |
| --- | --- |
| Route table | Xác định đích chuyển tiếp của lưu lượng theo tuyến |
| Internet Gateway | Cung cấp đường kết nối internet cho tài nguyên có cấu hình phù hợp |
| NAT Gateway | Cho tài nguyên không có public IP khởi tạo kết nối ra internet |
| Service Gateway | Cung cấp đường riêng tới các dịch vụ được hỗ trợ trong Oracle Services Network |
| Network Security Group, NSG | Áp dụng quy tắc lưu lượng cho các tài nguyên được đưa vào nhóm |
| Security list | Áp dụng quy tắc lưu lượng ở phạm vi các subnet sử dụng danh sách |
| Load Balancer | Nhận kết nối và phân phối tới các backend của ứng dụng |

Các định nghĩa mạng cơ bản được trình bày tại [Networking Overview](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm?elqak=8AF5B9E30B6DFC7B703A4F11B64785A066DAC37240E40E50CDD8B7F404B9023FB4EF).

Ví dụ, VM riêng cần tải bản cập nhật có thể dùng NAT Gateway. Kết nối do VM khởi tạo có thể nhận phản hồi; NAT Gateway không biến VM thành một máy chủ nhận kết nối tùy ý từ internet. Xem [NAT Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/NATgateway.htm?source=%3Aso%3Afb%3Aor%3Aawr%3Aodv%3A%3A).

Trong ví dụ đơn hàng, chỉ lớp tiếp nhận cần công khai. API và cơ sở dữ liệu giao tiếp qua các đường riêng được giới hạn theo nhu cầu. Chẳng hạn, lớp ứng dụng nhận yêu cầu từ Load Balancer, còn cơ sở dữ liệu nhận kết nối từ lớp ứng dụng.

## 6. Compute, container và serverless: chọn nơi chạy mã

### 6.1. Compute instance

Compute cung cấp máy ảo và máy chủ bare metal. **Image** xác định nền tảng hệ điều hành, còn **shape** xác định cấu hình tài nguyên. Với VM chạy Java, đội vận hành thường quản lý hệ điều hành khách, JVM, bản triển khai và cấu hình ứng dụng. Xem [Overview of the Compute Service](https://docs.oracle.com/en-us/iaas/Content/Compute/Concepts/computeoverview.htm).

Một VM là lựa chọn dễ hình dung khi học cách ứng dụng sử dụng hạ tầng:

~~~text
Compute VM
├── hệ điều hành
├── JVM
├── order-api.jar
├── cấu hình kết nối dữ liệu
└── tiến trình gửi log và metric
~~~

Chọn cấu hình cần dựa vào tải thực tế. CPU cao, thiếu bộ nhớ và chờ cơ sở dữ liệu là những vấn đề khác nhau; tăng kích thước VM có thể chỉ giải quyết một phần. Với Java, cần dành tài nguyên cho cả heap, bộ nhớ ngoài heap, luồng và hệ điều hành.

### 6.2. Kubernetes Engine, OKE

**Oracle Kubernetes Engine (OKE)** cung cấp Kubernetes được quản lý để triển khai và điều phối ứng dụng container. Phạm vi trách nhiệm còn tùy kiểu node và cấu hình cluster. Người dùng vẫn cần thiết kế workload, quyền truy cập và vận hành ứng dụng. Xem [Overview of Kubernetes Engine](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengoverview.htm).

OKE phù hợp khi hệ thống cần khả năng điều phối container và đội có năng lực Kubernetes. Một dịch vụ Java nhỏ chưa nhất thiết cần cluster; quyết định nên dựa vào yêu cầu triển khai, số lượng dịch vụ và khả năng vận hành.

### 6.3. Functions

**OCI Functions** thực thi logic theo mô hình Functions as a Service. Người dùng tập trung vào hàm và cấu hình thực thi thay vì tự cấp phát VM cho từng tác vụ. Ví dụ là xử lý sự kiện xuất hiện hóa đơn mới hoặc biến đổi một tệp. Xem [Overview of Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsoverview.htm).

Tác vụ cần được thiết kế theo giới hạn thực thi, cách kích hoạt và cách xử lý lỗi của nền tảng. Nếu một sự kiện được xử lý lại, ứng dụng cần tránh tạo hai hóa đơn hoặc ghi nhận hai lần cùng một nghiệp vụ.

| Lựa chọn | Khi cân nhắc |
| --- | --- |
| Compute VM | Cần kiểm soát hệ điều hành và môi trường chạy; muốn bắt đầu từ mô hình máy chủ quen thuộc |
| OKE | Cần điều phối nhiều workload container với mô hình vận hành Kubernetes |
| Functions | Có tác vụ theo sự kiện hoặc lời gọi, phù hợp với giới hạn thực thi của dịch vụ |

## 7. Storage: dữ liệu cần cách truy cập nào?

Không nên chọn lưu trữ chỉ theo dung lượng. Cần xác định ứng dụng đọc và ghi dữ liệu dưới dạng khối, tệp hay đối tượng.

| Dịch vụ | Cách sử dụng | Ví dụ |
| --- | --- | --- |
| Block Volume | Gắn volume vào instance, sử dụng như thiết bị đĩa | Đĩa dữ liệu cho phần mềm chạy trên VM |
| File Storage | Truy cập hệ thống tệp chia sẻ qua mạng | Thư mục dùng chung cho các máy cần thao tác tệp |
| Object Storage | Đọc và ghi object trong bucket bằng API hoặc công cụ phù hợp | Hóa đơn PDF, ảnh, tệp xuất báo cáo |

**Block Volume** cung cấp lưu trữ khối có thể gắn với instance. Dữ liệu có thể được giữ độc lập với vòng đời instance khi quản lý volume đúng cách. Độ bền lưu trữ không thay thế kế hoạch sao lưu trước lỗi thao tác hoặc lỗi ứng dụng. Xem [Overview of Block Volume](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/overview.htm).

**File Storage** cung cấp hệ thống tệp qua mạng, hỗ trợ NFS. Dịch vụ phù hợp khi phần mềm cần thao tác theo đường dẫn và chia sẻ dữ liệu giữa các máy. Quyền truy cập mạng và quyền trên tệp đều cần được xem xét. Xem [Overview of File Storage](https://docs.oracle.com/en-us/iaas/Content/File/Concepts/filestorageoverview.htm).

**Object Storage** lưu các object trong bucket. Trong ứng dụng đơn hàng, cơ sở dữ liệu có thể giữ mã đơn và khóa tham chiếu hóa đơn; nội dung PDF nằm trong một bucket riêng tư. Xem [Overview of Object Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/objectstorageoverview.htm).

Không nên mặc định coi Object Storage là thư mục đĩa của ứng dụng. Khi chuyển mã từ đọc tệp cục bộ sang đọc object, cần xét API, xác thực, lỗi mạng và cách truy cập đồng thời.

Một câu hỏi thiết kế hữu ích là: **nếu thay máy chạy ứng dụng, dữ liệu nào phải còn tồn tại?** Với ví dụ đơn hàng, đơn hàng và hóa đơn cần tồn tại độc lập; tệp tạm để tạo PDF có thể được tạo lại.

## 8. Database: chọn mức quản lý và yêu cầu dữ liệu

OCI có nhiều lựa chọn cơ sở dữ liệu. Trong module này, trọng tâm bao gồm các dịch vụ Oracle Database; lựa chọn cần dựa vào loại tải, khả năng tương thích, quyền quản trị và trách nhiệm vận hành.

| Nhóm lựa chọn | Đặc điểm cần hiểu | Câu hỏi khi lựa chọn |
| --- | --- | --- |
| Base Database Service | Triển khai Oracle Database với các khả năng quản lý và tự động hóa của dịch vụ | Ứng dụng cần cấu hình, phiên bản và quyền quản trị nào? |
| Autonomous AI Database, thường gặp dưới tên Autonomous Database | Tự động hóa nhiều công việc quản trị cơ sở dữ liệu | Ứng dụng có phù hợp với khả năng và giới hạn của mô hình được quản lý không? |
| Exadata Database Service | Dịch vụ Oracle Database trên nền tảng Exadata | Tải công việc có cần đặc tính và quy mô của Exadata không? |
| Tự cài cơ sở dữ liệu trên Compute | Đội của bạn quản lý phần mềm trên hạ tầng thuê | Có đủ năng lực vá lỗi, sao lưu, phục hồi và vận hành không? |

Các họ dịch vụ và tài liệu liên quan được liệt kê tại [OCI Database](https://docs.oracle.com/en-us/iaas/Content/Database/home.htm). Tên sản phẩm và lựa chọn triển khai có thể phát triển theo thời gian; khi thực hành cần dùng tài liệu của đúng dịch vụ.

Đối với hệ thống đơn hàng, hãy bắt đầu từ yêu cầu dữ liệu:

- Các thay đổi nào cần nằm trong cùng một giao dịch?
- Bao nhiêu kết nối đồng thời và độ trễ nào chấp nhận được?
- Có cần tương thích với Oracle Database đang dùng tại doanh nghiệp không?
- Mất tối đa bao nhiêu dữ liệu và ngừng dịch vụ bao lâu là chấp nhận được?
- Ai chịu trách nhiệm kiểm tra bản sao lưu và phục hồi?

Dùng dịch vụ được quản lý không tự giải quyết thiết kế schema, SQL, chỉ mục, giới hạn connection pool hoặc quyền của tài khoản ứng dụng. Một ứng dụng có thể làm quá tải cơ sở dữ liệu nếu mỗi bản sao API mở quá nhiều kết nối.

## 9. Bảo mật và trách nhiệm chia sẻ

OCI sử dụng mô hình trách nhiệm chia sẻ. Oracle bảo vệ hạ tầng đám mây bên dưới; khách hàng bảo vệ workload, danh tính, dữ liệu và cấu hình tài nguyên trong phạm vi của mình. Mức phân chia cụ thể phụ thuộc dịch vụ. Xem [Security Overview](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_overview.htm).

Áp dụng cho ví dụ đơn hàng:

| Nội dung | Quyết định của đội triển khai |
| --- | --- |
| Danh tính | Ai được đăng nhập, ai cần MFA, quyền nào cần thu hồi khi đổi vai trò |
| Truy cập quản trị | Ai được sửa mạng, thay cấu hình, xóa tài nguyên |
| Kết nối ứng dụng | Cách ứng dụng nhận secret và quyền truy cập dịch vụ |
| Dữ liệu | Ai được xem đơn hàng, tải hóa đơn, truy cập bản sao lưu |
| Phần mềm | Cách cập nhật ứng dụng và các thành phần đội tự quản lý |

Không đưa mật khẩu hoặc khóa riêng vào mã nguồn, image hay log. Hãy dùng cơ chế quản lý secret và danh tính của workload phù hợp với nền tảng thực thi. Quyền của ứng dụng cũng cần được giới hạn riêng với quyền của người triển khai.

Một bucket hóa đơn có thể được cấu hình riêng tư nhưng ứng dụng vẫn làm lộ nội dung nếu kiểm tra quyền nghiệp vụ không đúng. Do đó, IAM của OCI và phân quyền người dùng trong ứng dụng là hai lớp cần phối hợp.

## 10. Giám sát: biết hệ thống đang làm việc thế nào

Một hệ thống cần cả dữ liệu về trạng thái lẫn dữ liệu giải thích sự cố.

| Thành phần | Câu hỏi được hỗ trợ |
| --- | --- |
| Monitoring và alarm | CPU, lỗi hoặc độ trễ có vượt ngưỡng đã đặt không? |
| Logging | Yêu cầu nào lỗi và ứng dụng ghi nhận điều gì? |
| Audit | Hoạt động quản trị hoặc lời gọi API được ghi nhận đã thay đổi tài nguyên nào? |
| Theo dõi ứng dụng và trace | Yêu cầu mất thời gian ở thành phần nào trong chuỗi xử lý? |

Monitoring sử dụng metric và alarm; đích thông báo phải được cấu hình để người vận hành nhận được cảnh báo. Xem [Overview of Monitoring](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm).

Ví dụ, API có thể trả lỗi vì không lấy được kết nối cơ sở dữ liệu trong khi CPU của VM vẫn thấp. Chỉ quan sát CPU sẽ không phản ánh đầy đủ tình trạng ứng dụng. Đội cần bổ sung metric nghiệp vụ và log có mã tương quan cho yêu cầu.

Theo [Monitoring and Observability](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/monitoring-and-observability.htm), dữ liệu như metric, log và sự kiện hỗ trợ quan sát và xử lý vấn đề của hệ thống. Trong thực hành, có thể bắt đầu bằng số yêu cầu, tỷ lệ lỗi, thời gian phản hồi và trạng thái kết nối dữ liệu.

Log cần đủ ngữ cảnh để điều tra, đồng thời tránh chứa token, mật khẩu, thông tin thanh toán hoặc toàn bộ dữ liệu nhạy cảm của khách hàng.

## 11. Tự động hóa: từ thao tác đến cấu hình tái tạo được

Có nhiều cách làm việc với OCI:

| Cách tiếp cận | Vai trò điển hình |
| --- | --- |
| Console | Khám phá dịch vụ và quan sát tài nguyên bằng giao diện web |
| CLI | Thực hiện thao tác lặp lại hoặc truy vấn tài nguyên từ dòng lệnh |
| REST API, SDK | Tích hợp OCI vào công cụ và ứng dụng; SDK có lựa chọn cho Java |
| Terraform | Mô tả trạng thái hạ tầng mong muốn bằng cấu hình |
| Resource Manager | Chạy và quản lý công việc hạ tầng từ cấu hình được hỗ trợ trên OCI |

Resource Manager hỗ trợ quản lý cấu hình và trạng thái Terraform, với các công việc như lập kế hoạch và áp dụng thay đổi. Xem [Overview of Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm).

Đối với môi trường đơn hàng, cấu hình tái tạo nên biểu đạt được mạng, nơi chạy ứng dụng, các liên kết cần thiết và giá trị cấu hình theo môi trường. Bí mật cần được xử lý bằng cơ chế phù hợp, không ghi nguyên văn vào cấu hình công khai.

Tự động hóa giúp giảm thao tác thủ công, nhưng cần quan sát thay đổi dự kiến trước khi áp dụng. Một cấu hình sai có thể tạo ra nhiều tài nguyên sai rất nhanh. Quyền của công cụ tự động hóa vì thế cũng cần được giới hạn theo nhiệm vụ.

## 12. Chi phí và tính sẵn sàng phải đi cùng thiết kế

### 12.1. Kiểm soát chi phí

Chi phí hệ thống gồm nhiều thành phần: năng lực tính toán, lưu trữ, cơ sở dữ liệu, truyền dữ liệu và các dịch vụ vận hành liên quan. Một công thức tư duy là:

~~~text
Chi phí dự kiến
  = tài nguyên tính toán theo thời gian
  + lưu trữ và bản sao lưu
  + dịch vụ cơ sở dữ liệu
  + lưu lượng có tính phí
  + dịch vụ hỗ trợ khác
~~~

Đây là cách liệt kê nguồn chi phí, không phải công thức tính giá của Oracle. Đơn vị đo và chính sách giá cần kiểm tra ở đúng dịch vụ trước khi tạo tài nguyên.

**Budgets đặt ngưỡng chi tiêu mềm và cảnh báo.** Budget không tự bảo đảm việc dừng tài nguyên khi chạm ngưỡng; dữ liệu và cảnh báo cũng có chu kỳ đánh giá. Xem [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm?source=%3Apm%3Amz%3A%3A%3Arc_wwmk170417p00028%3Aprofitsummersmbenterprise).

Trong môi trường học tập, nên xác định trước compartment, thời gian sử dụng, người chịu trách nhiệm và kế hoạch dọn tài nguyên. Khi kết thúc, cần kiểm tra cả volume, backup và dịch vụ đi kèm; dừng một VM chưa đủ để kết luận toàn bộ hệ thống hết phát sinh chi phí.

Service limit, quota và ngân sách có mục đích khác nhau. Giới hạn số lượng tài nguyên không tương đương giới hạn tổng tiền. Việc tài nguyên đáp ứng hạn mức cũng chưa bảo đảm nhà cung cấp còn năng lực cấp phát tại vị trí bạn chọn.

### 12.2. Tính sẵn sàng và phục hồi

**High availability, HA** hướng đến duy trì dịch vụ khi một thành phần gặp lỗi. **Disaster recovery, DR** hướng đến khôi phục hoạt động sau sự cố lớn hơn. Hai mục tiêu cần thiết kế và kiểm tra riêng.

Hai khái niệm thường dùng để diễn đạt yêu cầu phục hồi:

- **RTO:** mục tiêu thời gian để khôi phục hoạt động.
- **RPO:** mục tiêu về khoảng dữ liệu có thể mất, tính theo thời gian.

Ví dụ giả định, đội đặt RTO là một giờ và RPO là mười lăm phút. Kiến trúc cần có quy trình và cơ chế dữ liệu đáp ứng các mục tiêu đó; chỉ ghi hai con số vào tài liệu chưa chứng minh hệ thống phục hồi được.

Một Load Balancer với hai API không bảo vệ giao dịch nếu cơ sở dữ liệu vẫn là điểm lỗi chưa được xử lý. Tương tự, có bản sao lưu chưa có nghĩa là đã biết thời gian khôi phục. Kiểm tra phục hồi là một phần của vận hành.

## 13. Ghép các nhóm dịch vụ thành hệ thống đơn hàng

Sơ đồ dưới đây là **kiến trúc minh họa**, chưa phải cấu hình triển khai hoàn chỉnh. Bucket thuộc Object Storage, không nằm trong subnet; đường đi riêng tới dịch vụ cần cấu hình mạng và quyền tương ứng.

~~~mermaid
flowchart TB
    U["Người dùng"] -->|"HTTPS"| LB

    subgraph R["Region được lựa chọn"]
        subgraph V["VCN"]
            LB["Load Balancer công khai"]
            A["API Java - bản sao A"]
            B["API Java - bản sao B"]
            DB["Endpoint riêng của dịch vụ cơ sở dữ liệu"]
            SG["Service Gateway"]
            LB --> A
            LB --> B
            A --> DB
            B --> DB
            A --> SG
            B --> SG
        end
        SG --> O["Object Storage - bucket hóa đơn riêng tư"]
    end

    A -.-> T["Metric và log"]
    B -.-> T
    T --> M["Monitoring, Logging và cảnh báo"]
~~~

Một yêu cầu tạo đơn có thể đi qua các bước:

1. Người dùng gửi HTTPS tới Load Balancer.
2. Một bản sao API xác thực người dùng và kiểm tra quyền nghiệp vụ.
3. API ghi đơn hàng vào cơ sở dữ liệu.
4. Tác vụ tạo hóa đơn ghi PDF vào Object Storage.
5. Ứng dụng lưu khóa tham chiếu hóa đơn, đồng thời phát log và metric cần thiết.
6. Khi người dùng yêu cầu tải hóa đơn, ứng dụng kiểm tra quyền rồi cung cấp dữ liệu theo cơ chế đã thiết kế.

Cần xử lý trường hợp bước ghi cơ sở dữ liệu thành công nhưng tạo hóa đơn thất bại. Một thiết kế có thể ghi trạng thái chờ xử lý và cho phép thử lại an toàn, thay vì coi mọi bước là một giao dịch tự động xuyên các dịch vụ.

Hai bản sao API nên hạn chế giữ trạng thái quan trọng trên đĩa cục bộ. Nếu phiên đăng nhập hoặc hóa đơn chỉ tồn tại ở bản sao A, người dùng được chuyển sang bản sao B có thể gặp lỗi dù cả hai VM vẫn hoạt động.

Sơ đồ chưa thể hiện cấu hình HA của cơ sở dữ liệu, sao lưu, quản lý secret, quy tắc mạng hoặc bố trí AD/FD. Khi triển khai thật, đội phải bổ sung các quyết định đó theo mục tiêu và dịch vụ đã chọn.

## 14. Thực hành nhận diện dịch vụ, không cần cấp phát tài nguyên

Hãy chuẩn bị một bản thiết kế ngắn cho ứng dụng Java theo trình tự sau:

1. **Xác định phạm vi:** một môi trường học tập, dữ liệu giả lập, một region dự kiến.
2. **Tổ chức tài nguyên:** chọn compartment và các vai trò cần có.
3. **Chọn nơi chạy mã:** bắt đầu với VM nếu mục tiêu là học hạ tầng; ghi lý do nếu chọn OKE hoặc Functions.
4. **Phân loại dữ liệu:** giao dịch vào cơ sở dữ liệu, PDF vào Object Storage, tệp tạm có thể tạo lại.
5. **Vẽ đường truy cập:** chỉ rõ thành phần công khai và các kết nối riêng cần thiết.
6. **Đặt tín hiệu vận hành:** xác định metric, log, người nhận cảnh báo và cách kiểm tra ứng dụng còn phục vụ được.
7. **Đặt giới hạn thực hành:** dự kiến nguồn chi phí, thời gian sử dụng và danh sách cần kiểm tra khi dọn tài nguyên.
8. **Xác định phục hồi:** ghi dữ liệu phải bảo vệ và cách kiểm tra việc khôi phục.

Kết quả mong đợi là một sơ đồ và bảng quyết định có lý do. Ví dụ: “Hóa đơn nằm trong Object Storage vì ứng dụng cần lưu và lấy từng tài liệu theo khóa; VM chỉ giữ tệp tạm khi xử lý”.

Nếu đã có quyền quan sát Console, bạn có thể nhận diện region, compartment và thông tin tài nguyên tương ứng. Danh sách trống cần được kiểm tra theo đúng phạm vi và quyền trước khi kết luận tài nguyên chưa tồn tại.

## 15. Những nhầm lẫn cần sửa ngay từ đầu

| Nhầm lẫn | Cách hiểu đúng để thiết kế |
| --- | --- |
| OCI chỉ dành cho Oracle Database | OCI còn cung cấp mạng, tính toán, lưu trữ và nhiều dịch vụ nền tảng |
| Compartment chính là một subnet | Compartment tổ chức và phân quyền; subnet thuộc cấu trúc mạng |
| Có IAM là đã kiểm soát mọi truy cập | Còn cần quy tắc mạng, quyền dữ liệu và phân quyền trong ứng dụng |
| Dịch vụ được quản lý nghĩa là không còn việc vận hành | Trách nhiệm còn lại phụ thuộc dịch vụ và cấu hình sử dụng |
| Có hai API là hệ thống đã HA | Cần xét Load Balancer, dữ liệu, phụ thuộc và phạm vi sự cố |
| Lưu trữ bền vững đồng nghĩa có thể phục hồi mọi lỗi | Cần sao lưu, thời hạn giữ dữ liệu và kiểm tra phục hồi |
| Budget là trần tiền tự động | Budget cung cấp ngưỡng mềm và cảnh báo |
| Dừng VM là xong phần chi phí | Cần kiểm tra cả lưu trữ, backup và các tài nguyên đi kèm |

Khi chuyển sang các bài chuyên sâu, hãy luôn gắn tên dịch vụ với bốn câu hỏi: **dịch vụ giải quyết nhu cầu nào, kết nối với ai, ai được quyền sử dụng và đội của bạn phải vận hành phần nào**. Từ đó, việc học tenancy, IAM, VCN, Compute, lưu trữ và cơ sở dữ liệu trở thành các quyết định liên quan trong cùng một hệ thống.