# Tenancy, compartment, OCID, region và OCI IAM policy

Khi triển khai ứng dụng Spring Boot trên Oracle Cloud Infrastructure (OCI), bốn câu hỏi cần trả lời trước khi gọi API là: tài nguyên thuộc tenancy nào, nằm trong compartment nào, được định danh bằng OCID nào và nằm ở region nào? Sau đó IAM policy quyết định workload hoặc người dùng được phép thực hiện hành động nào trên tài nguyên đó.

Các khái niệm này liên kết với nhau nhưng không thay thế nhau:

- **Tenancy** là ranh giới tài khoản/tổ chức OCI, chứa root compartment, identity và tài nguyên của tổ chức.
- **Compartment** là ranh giới logic để tổ chức tài nguyên, phân quyền và quản lý chi phí.
- **OCID** là định danh duy nhất do Oracle cấp cho hầu hết tài nguyên OCI.
- **Region** là khu vực địa lý triển khai dịch vụ; tenancy phải đăng ký region trước khi sử dụng.
- **OCI IAM policy** là tập các statement cấp quyền cho user, group, dynamic group hoặc workload principal trên resource type trong tenancy/compartment.

Một lỗi phổ biến là dùng đúng API endpoint nhưng sai compartment OCID, hoặc tạo đúng compartment nhưng chưa có policy cho workload. Kết quả thường là không tìm thấy tài nguyên, lỗi authorization hoặc ứng dụng chỉ chạy được bằng tài khoản quản trị. Bài học này xây dựng mô hình từ tenancy tới policy rồi nối với OCI Java SDK trong Spring Boot.

Bài thuộc chương **Oracle Cloud** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Trọng tâm bài là hiểu cấu trúc tenancy, compartment, OCID và region, thiết kế OCI IAM policy theo least privilege và cấu hình danh tính OCI SDK phù hợp với môi trường chạy.

## 1. Mục tiêu học tập và tình huống xuyên suốt

Sau bài học, bạn có thể:

1. Giải thích tenancy, root compartment, compartment hierarchy và policy inheritance.
2. Phân biệt compartment với region, availability domain và fault domain.
3. Đọc cấu trúc OCID, tìm đúng OCID và dùng OCID trong cấu hình/API/policy.
4. Hiểu home region, realm và region subscription.
5. Viết policy statement theo subject, verb, resource type, location và condition.
6. Chọn đúng verb inspect, read, use hoặc manage.
7. Tạo dynamic group cho Compute instance principal và policy cho workload.
8. Phân biệt API key authentication, instance principal, resource principal và OKE workload identity.
9. Cấu hình OCI Java SDK client trong Spring Boot theo local development và production.
10. Kiểm tra lỗi authorization, sai OCID, sai region và policy scope.

Tình huống xuyên suốt: **document-service** chạy trên OCI Compute hoặc Oracle Kubernetes Engine (OKE), đọc hợp đồng từ Object Storage và ghi metadata vào database. Bucket nằm trong compartment AppData, compute workload nằm trong compartment AppRuntime, còn nhóm vận hành được quản lý riêng. Ứng dụng cần đọc đúng bucket/object mà không phải dùng API key của quản trị viên.

~~~mermaid
flowchart TD
    T["Tenancy / Root Compartment"] --> P["Platform"]
    P --> R["AppRuntime"]
    P --> D["AppData"]
    P --> O["Observability"]
    R --> W["Spring Boot workload"]
    D --> S["Object Storage bucket"]
    W --> I["OCI IAM principal"]
    I --> G["Group / Dynamic Group / Workload Identity"]
    G --> POL["OCI IAM policy"]
    POL --> S
    W --> SDK["OCI Java SDK"]
    SDK --> S
~~~

**Quyền không đến từ việc ứng dụng biết OCID.** OCID xác định tài nguyên; IAM policy mới cấp quyền cho principal thao tác trên tài nguyên đó.

## 2. Tenancy và root compartment

### 2.1. Tenancy là gì?

Tenancy là tài khoản OCI của một tổ chức hoặc khách hàng. Khi đăng ký OCI, Oracle tạo tenancy và gán một tenancy OCID. Tenancy là phạm vi quản lý identity, subscription region, quota/service limits, compartment và tài nguyên.

Một tenancy có các thành phần chính:

- Root compartment đại diện cho toàn tenancy.
- Compartment con để phân vùng tài nguyên theo môi trường, sản phẩm hoặc đội nhóm.
- Identity domain, user, group, dynamic group và federation.
- IAM policy quy định quyền.
- Region subscription cho các khu vực mà tenancy được phép sử dụng.
- Tài nguyên compute, network, storage, database, observability và các dịch vụ khác.

Tenancy OCID được dùng trong nhiều API và cấu hình SDK. Không nên nhầm tenancy OCID với user OCID, compartment OCID hoặc OCID của một resource.

### 2.2. Root compartment

Khi tenancy được tạo, OCI có một root compartment. Root compartment chính là tenancy và có thể chứa tài nguyên trực tiếp, nhưng thông thường nên tạo compartment con để phân chia trách nhiệm.

Ví dụ:

~~~text
Tenancy (root)
└── Platform
    ├── Shared-Network
    ├── AppRuntime
    ├── AppData
    └── Observability
~~~

Trong thiết kế thực tế, có thể tổ chức theo môi trường trước:

~~~text
Tenancy
├── Network
├── Development
│   ├── Runtime
│   └── Data
├── Staging
│   ├── Runtime
│   └── Data
└── Production
    ├── Runtime
    ├── Data
    └── Security
~~~

Hoặc tổ chức theo sản phẩm/đội sở hữu:

~~~text
Tenancy
├── Shared-Services
├── Finance
│   ├── Runtime
│   └── Data
└── Documents
    ├── Runtime
    └── Data
~~~

Không có một cây compartment tối ưu cho mọi tổ chức. Hãy chọn cấu trúc phản ánh ranh giới quyền, ownership, chi phí và yêu cầu vận hành.

### 2.3. Tenancy và compartment không phải region

Compartment là tài nguyên IAM có phạm vi toàn tenancy. Một compartment có thể chứa tài nguyên ở nhiều region đã đăng ký. Khi chuyển region trên Console, cùng một compartment vẫn tồn tại; chỉ danh sách resource theo region đang chọn thay đổi.

Điều này có nghĩa:

- Một compartment AppData có thể chứa bucket ở Singapore và database ở một region khác.
- IAM policy áp dụng cho compartment có thể được thực thi tại các region đã đăng ký.
- Region của bucket/database được xác định theo dịch vụ và cấu hình resource, không phải tên compartment.
- Compartment không tự sao chép dữ liệu hoặc tạo disaster recovery.

### 2.4. Giới hạn và vận hành compartment

OCI hỗ trợ hierarchy nhiều tầng; tài liệu hiện hành nêu giới hạn tối đa sáu cấp lồng nhau. Cần giữ cây đơn giản để dễ hiểu policy inheritance và ownership.

Một compartment thường có tên duy nhất trong phạm vi parent phù hợp, description và OCID. Tên giúp con người đọc; OCID dùng để tham chiếu chính xác qua API. Đổi display name không biến OCID thành một định danh khác.

Trước khi xóa compartment:

- Di chuyển hoặc xóa resource bên trong theo quy trình.
- Kiểm tra policy gắn với compartment.
- Kiểm tra service dependency và backup.
- Xem xét resource có đang được workload hoặc automation tham chiếu không.

Xóa compartment là thao tác bất đồng bộ và compartment phải rỗng. Không xem việc đổi tên hoặc xóa compartment như cách thu hồi một quyền duy nhất; hãy sửa policy đúng phạm vi.

## 3. Compartment hierarchy và policy inheritance

### 3.1. Compartment là ranh giới logic

Compartment giúp nhóm resource theo:

- Môi trường: dev, staging, production.
- Sản phẩm: document, payment, analytics.
- Đội sở hữu: platform, security, finance.
- Mức phân loại dữ liệu.
- Ranh giới quản trị và ngân sách.

Một resource OCI thường được tạo trong một compartment. Policy có thể được đặt ở tenancy/root hoặc ở compartment phù hợp.

### 3.2. Policy inheritance

Compartment con kế thừa quyền được cấp bởi policy ở compartment cha. Ví dụ:

~~~text
Tenancy
└── Production
    ├── Documents
    └── Payments
~~~

Nếu policy có scope ở Production, quyền được cấp có thể áp dụng xuống Documents và Payments. Nếu policy chỉ có scope Documents, quyền không tự mở rộng ngược lên Production hoặc sang Payments.

Minh họa:

~~~text
Allow group PlatformAuditors to inspect all-resources in compartment Production
~~~

Policy trên được đặt ở phạm vi Production sẽ cho nhóm auditor quyền inspect resource trong Production và các compartment con theo cơ chế kế thừa.

Kế thừa giúp tránh lặp policy nhưng cũng có thể làm quyền rộng hơn dự kiến. Trước khi đặt policy ở root hoặc compartment cha, hãy kiểm tra tất cả nhánh con chịu ảnh hưởng.

### 3.3. Policy đặt ở đâu và location ghi gì?

Một policy có hai khía cạnh:

- **Nơi lưu policy:** tenancy/root hoặc một compartment.
- **Location trong statement:** tenancy hoặc compartment mà quyền áp dụng.

Với policy tạo ở tenancy, location có thể là tenancy hoặc compartment cụ thể. Với policy tạo ở compartment, location mặc định thường là compartment đó; nếu tham chiếu compartment khác trong cây, có thể cần đường dẫn compartment theo cú pháp OCI.

Ví dụ minh họa policy scope hẹp:

~~~text
Allow group <identity-domain>/<DocumentReaders> to read objects in compartment AppData
~~~

Ví dụ policy ở root nhưng giới hạn resource ở compartment Production:

~~~text
Allow group <identity-domain>/<ProductionAuditors> to inspect all-resources in compartment Production
~~~

Không dùng scope tenancy nếu chỉ cần một compartment.

### 3.4. Compartment có thể di chuyển

Di chuyển compartment sang parent khác có thể làm thay đổi các policy được kế thừa. Quyền trước đó có thể biến mất hoặc được mở rộng bởi parent mới. Hãy xem việc move compartment là thay đổi bảo mật:

1. Xác định parent cũ và parent đích.
2. So sánh policy được kế thừa ở hai nhánh.
3. Kiểm tra các policy tham chiếu tên/OCID compartment.
4. Thực hiện change có phê duyệt.
5. Kiểm tra quyền sau khi di chuyển bằng principal thực tế.
6. Ghi audit và cập nhật sơ đồ ownership.

## 4. OCID: Oracle Cloud Identifier

### 4.1. OCID dùng để làm gì?

OCID là định danh duy nhất do OCI cấp cho hầu hết tài nguyên. Ví dụ:

- Tenancy OCID.
- Compartment OCID.
- User/group/dynamic group OCID.
- Compute instance OCID.
- VCN, subnet, bucket, database và key OCID.

OCID xuất hiện trong Console và API response. Nhiều thao tác API cần OCID để chỉ rõ tài nguyên đích. Một số policy cho phép dùng tên thay OCID; khi tên có thể trùng ở các nhánh compartment hoặc identity domain, OCID giúp tham chiếu chính xác hơn.

### 4.2. Cấu trúc OCID

Cấu trúc tổng quát:

~~~text
ocid1.<RESOURCE_TYPE>.<REALM>.[REGION][.FUTURE_USE].<UNIQUE_ID>
~~~

Các phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| ocid1 | Phiên bản định dạng OCID |
| RESOURCE_TYPE | Loại resource, ví dụ tenancy, compartment, instance, volume |
| REALM | Realm mà resource thuộc về |
| REGION | Region nếu resource có phạm vi region/availability domain |
| FUTURE_USE | Phần dành cho sử dụng trong tương lai; hiện có thể để trống |
| UNIQUE_ID | Phần định danh duy nhất do Oracle cấp |

Ví dụ cấu trúc:

~~~text
Tenancy:
ocid1.tenancy.oc1..<unique-id>

Compartment:
ocid1.compartment.oc1..<unique-id>

Instance:
ocid1.instance.oc1.phx.<unique-id>
~~~

Các chuỗi trên chỉ minh họa cấu trúc, không phải OCID hợp lệ để gọi API. Hãy sao chép OCID thật từ Console/API.

### 4.3. Realm và region trong OCID

Realm là tập hợp region chia sẻ một số thực thể và endpoint domain. Ví dụ realm thương mại thường có key OC1; các realm Government có key khác. Tenancy thuộc một realm và không thể truy cập region nằm ngoài realm của tenancy.

Một số OCID có phần region, nhưng không phải tất cả. Tenancy, compartment và một số IAM resource có phạm vi toàn tenancy nên phần region có thể trống. Vì vậy không được suy luận mọi resource location chỉ bằng cách tách chuỗi OCID.

### 4.4. Tìm OCID trong Console

Có thể tìm OCID trong trang chi tiết resource:

- Tenancy: Profile menu → Tenancy details.
- Compartment: Identity & Security → Compartments → chọn compartment.
- Compute instance: Compute → Instances → chọn instance.
- VCN: Networking → Virtual Cloud Networks.
- Bucket: Object Storage → Buckets → chọn bucket.

Sao chép toàn bộ OCID, không cắt bớt. Khi đưa vào cấu hình, kiểm tra resource type và tenancy/region đúng với môi trường.

### 4.5. OCID và tên hiển thị

| Thuộc tính | Tên/display name | OCID |
| --- | --- | --- |
| Dễ đọc | Có | Ít dễ đọc |
| Có thể đổi | Nhiều resource cho phép đổi tên/description | Được Oracle cấp làm định danh |
| Dùng trong API | Tùy operation | Rất thường xuyên |
| Dùng trong policy | Có thể dùng nếu đúng scope | Có thể dùng bằng cú pháp id |
| Là secret? | Không | Không phải secret, nhưng nên bảo vệ inventory/config |

OCID không phải credential. Biết OCID không tự cấp quyền truy cập. Tuy vậy, tránh đưa toàn bộ resource inventory vào log công khai hoặc response không cần thiết.

### 4.6. Lưu OCID trong Spring Boot

OCID và region là cấu hình môi trường, không nên hard-code vào business logic:

~~~yaml
oci:
  tenancy-ocid: OCI_TENANCY_OCID
  compartment-ocid: OCI_COMPARTMENT_OCID
  region: ap-singapore-1
  auth-profile: DEFAULT
~~~

Đây là tên biến cấu hình minh họa. Tách config theo profile/environment. Không dùng OCID của dev trong production hoặc ngược lại. Khi ứng dụng cần nhiều compartment, lưu map theo domain/service và validate OCID ở startup hoặc khi provision.

## 5. Region, realm và home region

### 5.1. Region là gì?

Region là khu vực địa lý có một hoặc nhiều availability domain. Tài nguyên regional được tạo trong region cụ thể; API client cần gửi request tới endpoint đúng region.

Ví dụ region identifier có dạng:

~~~text
ap-singapore-1
ap-tokyo-1
us-ashburn-1
eu-frankfurt-1
~~~

Tên region có thể khác region key viết tắt. Trong Java SDK nên dùng region identifier chính thức hoặc enum có sẵn trong SDK.

### 5.2. Realm

Realm là nhóm region chia sẻ domain/identity boundary. Một tenancy thuộc một realm. Region trong realm khác không thể được thêm vào tenancy chỉ bằng cách đổi endpoint.

Khi tích hợp endpoint riêng hoặc region mới, phải xác minh:

- Realm của tenancy.
- Region có thuộc realm đó không.
- SDK version có nhận diện region không.
- Service có được cung cấp ở region đó không.
- Endpoint domain đúng realm và region.

### 5.3. Home region

Khi tạo tenancy, OCI chỉ định một home region. Home region chứa master definitions của các IAM resource như:

- Users.
- Groups.
- Policies.
- Compartments.
- Dynamic groups.
- Federation resources.

Home region không thể thay đổi sau khi tenancy được provision. Khi gọi API để tạo/cập nhật IAM resource, cần dùng endpoint home region; thay đổi được IAM propagate tới các region đã đăng ký. Console thường xử lý việc gửi request về home region giúp người dùng.

Điểm quan trọng: home region không có nghĩa mọi resource application phải nằm tại đó. Compute, VCN, bucket và database có thể được triển khai ở region khác trong realm nếu tenancy đã subscribe và service hỗ trợ.

### 5.4. Region subscription

Region subscription được thực hiện ở cấp tenancy:

1. Mở Region menu trong OCI Console.
2. Chọn Manage Regions.
3. Chọn region cần sử dụng.
4. Subscribe và chờ trạng thái kích hoạt.

Khi subscribe region mới, các IAM policy hiện có được áp dụng ở region đó. OCI không cho unsubscribe một infrastructure region sau khi đã đăng ký. Vì vậy, lựa chọn region cần được xem là quyết định quản trị và residency, không phải thao tác bật/tắt tùy ý.

### 5.5. IAM resource và service resource khác phạm vi

| Loại resource | Phạm vi thường gặp |
| --- | --- |
| Compartments, users, groups, policies | Cross-region / tenancy-wide |
| Object Storage bucket | Regional |
| VCN | Regional |
| Compute instance | Availability-domain-specific |
| Block volume | Availability-domain-specific |
| Một số dịch vụ chuyên biệt | Theo service documentation |

Không giả định tất cả resource đều regional hoặc đều global. Luôn kiểm tra service availability và resource scope của dịch vụ cụ thể.

## 6. Availability Domain và Fault Domain

### 6.1. Availability Domain (AD)

Availability Domain là một hoặc nhiều data center trong một region. Các AD trong cùng region được thiết kế độc lập về hạ tầng quan trọng như nguồn điện, làm mát và mạng nội bộ. Nếu một AD gặp sự cố, AD khác trong cùng region có thể tiếp tục hoạt động.

Một region có thể có một hoặc nhiều AD. Các region mới có thể chỉ có một AD; không nên giả định mọi region đều có ba AD.

### 6.2. Tên AD được gắn theo tenancy

OCI randomizes ánh xạ AD name theo tenancy để cân bằng capacity. Ví dụ tên PHX-AD-1 trong tenancy A không nhất thiết chỉ cùng data center vật lý với PHX-AD-1 trong tenancy B.

Lấy danh sách AD của tenancy qua IAM API ListAvailabilityDomains hoặc Console. Không hard-code tên AD của một tenancy vào tài liệu dùng chung cho tenancy khác.

### 6.3. Fault Domain (FD)

Mỗi AD có ba fault domain. Fault domain là nhóm phần cứng/hạ tầng bên trong AD, giúp phân tán instance để tránh đặt các workload quan trọng trên cùng một nhóm phần cứng.

Thiết kế HA:

- Nếu region có nhiều AD, phân tán ứng dụng qua nhiều AD.
- Trong một AD, dùng nhiều FD để giảm rủi ro lỗi phần cứng chung.
- Nếu region chỉ có một AD, cân nhắc DR ở region khác.
- Kiểm tra database, volume, subnet và service dependency có cùng khả năng phân tán hay không.

### 6.4. Region và policy

Region là nơi đặt resource; compartment là scope logic của policy. Nếu cần giới hạn thao tác vào region cụ thể, OCI policy có thể dùng condition như request.region hoặc request.ad trong những policy/service hỗ trợ.

Ví dụ minh họa:

~~~text
Allow group RegionAuditors to inspect all-resources in tenancy
where request.region = 'ap-singapore-1'
~~~

Kiểm tra điều kiện và resource type có hỗ trợ trong service policy reference. Region condition không thay thế việc chọn đúng endpoint khi tạo SDK client.

## 7. OCI IAM: principal, group và policy

### 7.1. Principal là ai?

Principal là danh tính thực hiện request. Trong OCI, các subject phổ biến gồm:

- User: người dùng Console/API.
- Group: tập user được gán cùng quyền.
- Dynamic group: tập resource/workload được xác định bằng matching rule.
- Instance principal: Compute instance được xác thực bằng identity certificate.
- Resource principal: tài nguyên OCI như Function có thể gọi service khác bằng identity của chính resource.
- OKE workload identity: workload Kubernetes được xác định bằng cluster, namespace và Kubernetes service account.
- Service principal hoặc các principal được hỗ trợ khác tùy dịch vụ.

Hãy phân biệt principal của ứng dụng với user cuối cùng. Spring Boot có thể xác thực end user bằng OAuth/JWT, nhưng khi gọi Object Storage, OCI nhìn thấy OCI workload principal của service.

### 7.2. Identity domain và group

OCI Identity Domains quản lý user, group và federation. Policy subject có thể tham chiếu group trong identity domain:

~~~text
Allow group <identity-domain-name>/<group-name> to read objects in compartment AppData
~~~

Với default identity domain hoặc tenancy chưa chuyển sang identity domains, cú pháp/hiển thị có thể khác. Dùng đúng tên domain và group trong Console của tenancy; không sao chép tên group giữa hai tenancy rồi giả định chúng giống nhau.

Group chỉ gom principal. Group không tự có quyền cho tới khi có policy cấp quyền tương ứng.

### 7.3. Policy là gì?

OCI IAM policy là tài liệu chứa một hoặc nhiều policy statement. Policy xác định:

- Subject: principal nào được cấp quyền.
- Verb: mức quyền.
- Resource type: loại tài nguyên.
- Location: tenancy hoặc compartment.
- Condition: giới hạn bổ sung nếu cần.

Cú pháp cơ bản:

~~~text
Allow <subject> to <verb> <resource-type> in <location>
~~~

Cú pháp có điều kiện:

~~~text
Allow <subject> to <verb> <resource-type> in <location> where <conditions>
~~~

Ví dụ:

~~~text
Allow group <identity-domain>/DocumentReaders to read objects in compartment AppData
~~~

Các policy cấp quyền thông thường bắt đầu bằng Allow. Nếu principal không có grant phù hợp cho thao tác/resource/location thì request không được cấp quyền. OCI hiện cũng có tính năng **Deny Policies** dạng opt-in: mặc định chưa bật, phải được tenancy administrator chủ động bật và việc bật không thể đảo ngược bằng cách tắt feature. Khi đã bật, deny statement có thể chặn quyền được cấp bởi allow policy và có mức ưu tiên cao hơn. Chỉ bật khi tổ chức có mô hình quản trị, kiểm thử và quy trình break-glass rõ ràng; một deny statement quá rộng có thể khóa người dùng khỏi resource. Nhóm administrator mặc định được miễn trừ theo cơ chế bảo vệ account lockout. Các ví dụ trong bài tập trung vào allow policy thông thường.

### 7.4. Bốn policy verb

Các verb theo thứ tự từ ít đến nhiều quyền:

| Verb | Ý nghĩa tổng quát | Dùng khi |
| --- | --- | --- |
| inspect | Liệt kê và xem thông tin cơ bản theo resource type | Auditor bên ngoài, inventory |
| read | Bao gồm inspect và đọc metadata/nội dung theo resource type | Auditor nội bộ, reader |
| use | Bao gồm read và thao tác với resource hiện có; tùy resource type | Người dùng vận hành resource đã tạo |
| manage | Quyền đầy đủ trên resource type trong scope | Admin/owner có trách nhiệm quản trị |

Verb là khái niệm tổng quát. API operation thực tế phụ thuộc resource type.

Ví dụ Object Storage:

- inspect objects cho phép list object và HEAD object; không có nghĩa tải nội dung.
- read objects bao gồm khả năng tải object.
- read buckets cho phép đọc thông tin bucket/list bucket trong scope.
- manage objects có thể bao gồm tạo, đọc, sửa/xóa object theo policy và condition.

Vì vậy không chọn verb chỉ theo tên tiếng Anh. Hãy tra bảng verb + resource type cho API operation cần gọi.

### 7.5. Resource type và family

OCI định nghĩa resource type riêng và resource family gom nhiều loại liên quan. Ví dụ Object Storage có buckets, objects và object-family. Compute có instance-family; Networking có virtual-network-family.

Dùng family có thể tiện nhưng thường rộng hơn nhu cầu. Nếu chỉ cần đọc object, hãy xem xét read objects và read buckets thay vì manage object-family.

Một số API cần quyền trên nhiều resource type. Ví dụ launch instance có thể cần quyền cho instance, volume và network. Khi gặp lỗi authorization, kiểm tra operation-specific permission matrix thay vì tăng mọi quyền lên manage all-resources.

## 8. Viết policy theo least privilege

### 8.1. Policy cho người đọc tài liệu

Giả sử bucket hợp đồng nằm trong compartment AppData. Nhóm DocumentReaders chỉ cần liệt kê bucket và tải object:

~~~text
Allow group <identity-domain>/DocumentReaders to read buckets in compartment AppData
Allow group <identity-domain>/DocumentReaders to read objects in compartment AppData
~~~

Nếu chỉ cho phép một bucket, giới hạn object access bằng condition:

~~~text
Allow group <identity-domain>/DocumentReaders to read buckets in compartment AppData

Allow group <identity-domain>/DocumentReaders to read objects in compartment AppData
where target.bucket.name = 'contracts-prod'
~~~

Tùy use case, việc liệt kê bucket và đọc object là hai quyền riêng. Không cấp quyền list toàn bộ bucket nếu ứng dụng chỉ biết sẵn tên bucket và không cần liệt kê.

### 8.2. Policy cho uploader

Nếu service chỉ cần tạo object mới trong một bucket, có thể dùng condition theo bucket và request permission để tránh cấp quyền đọc/xóa/ghi đè rộng:

~~~text
Allow dynamic-group DocumentService to manage objects in compartment AppData
where all {
  target.bucket.name = 'contract-inbox',
  request.permission = 'OBJECT_CREATE'
}
~~~

Ví dụ này dùng resource permission cụ thể. Kiểm tra operation và condition support trong policy reference của Object Storage trước khi dùng. Với upload multipart hoặc operation khác, có thể cần thêm permission liên quan.

### 8.3. Policy cho auditor

Auditor chỉ cần inventory:

~~~text
Allow group <identity-domain>/CloudAuditors to inspect compartments in tenancy
Allow group <identity-domain>/CloudAuditors to inspect all-resources in compartment Production
~~~

Cẩn trọng: inspect không luôn có nghĩa chỉ thấy tên. Với policy resource type như policies hoặc networking, một số list/get operation có thể trả về nội dung nhạy cảm như policy statements hoặc network rule. Kiểm tra operation mapping trước khi cấp.

### 8.4. Policy cho compartment admin

Một nhóm quản trị compartment có thể cần quản lý resource trong một compartment cụ thể:

~~~text
Allow group <identity-domain>/AppDataAdmins to manage all-resources in compartment AppData
~~~

Đây là quyền rộng trong compartment. Chỉ dùng khi nhóm thật sự chịu trách nhiệm quản trị mọi resource type ở đó. Nếu họ chỉ quản lý bucket, cấp manage buckets/objects phù hợp thay vì all-resources.

### 8.5. Condition theo bucket/tag/region

Condition giúp giới hạn policy theo thuộc tính target hoặc request. Ví dụ:

~~~text
Allow group <identity-domain>/ContractReaders to read objects in compartment AppData
where target.bucket.name = 'contracts-prod'
~~~

Có thể dùng tag condition nếu bucket được gắn defined tag:

~~~text
Allow group <identity-domain>/TaggedReaders to read objects in compartment AppData
where target.bucket.tag.Security.Classification = 'Confidential'
~~~

Condition theo request region:

~~~text
Allow group <identity-domain>/RegionalAuditors to inspect all-resources in tenancy
where request.region = 'ap-singapore-1'
~~~

Tên tag namespace/key phải đúng định nghĩa thực tế. Condition được hỗ trợ khác nhau theo resource type và API operation; policy builder hoặc policy reference giúp xác nhận.

### 8.6. Tránh any-user quá rộng

any-user là subject rộng, có thể bao gồm nhiều loại principal trong tenancy. Không dùng statement rộng như:

~~~text
Allow any-user to manage all-resources in tenancy
~~~

Với OKE workload identity, OCI yêu cầu dùng any-user kết hợp condition nhận diện chính xác principal type, namespace, service account và cluster OCID. Condition là phần bắt buộc để giới hạn workload cụ thể, không được bỏ đi.

### 8.7. Policy inheritance và quyền cộng dồn

Một principal có thể nhận quyền từ nhiều group hoặc policy. Nếu user nằm trong hai group, quyền của cả hai group có thể cùng áp dụng. Policy ở parent compartment cũng được kế thừa xuống child.

Vì vậy, review policy cần kiểm tra:

- Membership của user trong mọi group.
- Dynamic group matching rules.
- Policy ở tenancy/root.
- Policy ở parent compartment.
- Policy ở compartment hiện tại.
- Policy condition và resource type.
- Principal type thực sự dùng để gọi API.

Không chỉ đọc một policy statement rồi kết luận user có hoặc không có quyền.

## 9. Dynamic group và instance principal

### 9.1. Instance principal là gì?

Instance principal cho phép Compute instance xác thực với OCI bằng identity certificate do nền tảng cấp và xoay vòng. Ứng dụng không cần mang API private key của user vào máy.

Luồng khái quát:

1. Tạo dynamic group.
2. Định nghĩa matching rule cho instance được phép.
3. Viết policy cấp quyền cho dynamic group.
4. Cấu hình OCI Java SDK dùng Instance Principals provider.
5. SDK ký request bằng identity của instance.

Dynamic group không tự cấp quyền. Policy vẫn cần được tạo riêng.

### 9.2. Matching rule theo compartment

Ví dụ đưa instance trong AppRuntime vào dynamic group:

~~~text
ALL {
  instance.compartment.id = '<APP_RUNTIME_COMPARTMENT_OCID>'
}
~~~

Có thể thu hẹp bằng instance OCID hoặc tag. Ví dụ minh họa theo tag:

~~~text
ALL {
  instance.compartment.id = '<APP_RUNTIME_COMPARTMENT_OCID>',
  tag.Application.Role.value = 'document-service'
}
~~~

Nếu dùng tag để quyết định quyền, hãy kiểm soát ai có quyền gắn/thay đổi tag. Nếu principal có thể tự gắn tag được dùng trong matching rule, họ có thể tự đưa instance vào nhóm được cấp quyền.

### 9.3. Policy cho dynamic group

~~~text
Allow dynamic-group DocumentServiceInstances to read buckets in compartment AppData
Allow dynamic-group DocumentServiceInstances to read objects in compartment AppData
~~~

Đây là quyền read-only cho workload. Nếu service chỉ cần một bucket, bổ sung condition target.bucket.name.

### 9.4. Java SDK với instance principal

~~~java
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.InstancePrincipalsAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.ObjectStorageClient;

public final class OciObjectStorageFactory {

    public ObjectStorage create(String regionId) {
        var provider =
                InstancePrincipalsAuthenticationDetailsProvider.builder().build();

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(regionId))
                .build(provider);
    }
}
~~~

SDK dùng identity của Compute instance. Không cần user OCID, fingerprint hoặc private key path trong application config. Hãy bảo vệ quyền SSH/OS access vào instance vì người có quyền truy cập máy có thể sử dụng quyền mà instance principal được cấp.

### 9.5. Bảo mật dynamic group

- Tránh matching rule bao trùm toàn bộ tenancy nếu không cần.
- Ưu tiên compartment, instance OCID hoặc tag được quản lý chặt.
- Tách dynamic group theo workload/service.
- Cấp policy trên compartment đích, không mặc định tenancy.
- Review matching rule khi move instance hoặc đổi tag.
- Audit request bằng principal ID của instance.
- Khi instance bị compromise, loại nó khỏi dynamic group hoặc thay đổi policy phù hợp.

Thay đổi matching rule có thể cần thời gian để membership/policy cập nhật. Tài liệu OCI lưu ý có thể mất khoảng một giờ để thay đổi matching rule có hiệu lực; hãy tính đến độ trễ này trong quy trình incident response.

## 10. Resource principal và OKE workload identity

### 10.1. Resource principal

Resource principal cho phép một số resource OCI, ví dụ Functions, hoạt động như principal để gọi service khác. Đây là identity của resource, không phải user API key.

Quy trình tổng quát:

1. Xác định resource hỗ trợ resource principal.
2. Tạo dynamic group/matching rule phù hợp theo resource.
3. Cấp policy cho dynamic group.
4. Cấu hình OCI SDK bằng Resource Principal provider.
5. Audit request để xác minh principal và resource scope.

Java SDK cung cấp ResourcePrincipalAuthenticationDetailsProvider. Cách khởi tạo phụ thuộc resource runtime và phiên bản resource principal protocol. Không tự đặt environment variables giả để giả lập resource principal trên máy developer.

### 10.2. OKE workload identity

Với OKE enhanced cluster, workload identity xác định workload bằng bộ ba:

- Cluster.
- Kubernetes namespace.
- Kubernetes service account.

OCI IAM policy có thể giới hạn quyền dựa trên principal type, namespace, service account và cluster OCID. Đây là identity riêng của workload, giúp không phải cấp cùng quyền cho toàn bộ node hoặc mọi pod trong cluster.

### 10.3. Policy cho OKE workload

Ví dụ workload tên document-service chạy trong namespace documents:

~~~text
Allow any-user to read objects in compartment AppData where all {
  request.principal.type = 'workload',
  request.principal.namespace = 'documents',
  request.principal.service_account = 'document-service',
  request.principal.cluster_id = '<OKE_CLUSTER_OCID>'
}
~~~

Nếu cần list bucket, thêm statement riêng cho buckets với cùng điều kiện. Không bỏ điều kiện principal chỉ vì subject dùng any-user.

### 10.4. Java SDK cho OKE

~~~java
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.okeworkloadidentity
        .OkeWorkloadIdentityAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.ObjectStorageClient;

public final class OkeOciClientFactory {

    public ObjectStorage create(String regionId) {
        var provider =
                new OkeWorkloadIdentityAuthenticationDetailsProvider
                        .OkeWorkloadIdentityAuthenticationDetailsProviderBuilder()
                        .build();

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(regionId))
                .build(provider);
    }
}
~~~

Chỉ tạo một instance provider và tái sử dụng trong ứng dụng để tận dụng token cache. Dùng OCI Java SDK version hỗ trợ OKE workload identity; tài liệu hiện hành nêu Java SDK legacy từ 2.93.0 và standard SDK từ 3.88.0. Workload identity yêu cầu OKE enhanced cluster và hiện không dùng dynamic group.

## 11. API key authentication và local development

### 11.1. Khi nào dùng API key?

API key-based authentication phù hợp cho developer workstation, công cụ CLI hoặc automation có kiểm soát khi chưa thể dùng workload identity. Cấu hình thường chứa:

- User OCID.
- Tenancy OCID.
- Fingerprint của public key đã đăng ký.
- Đường dẫn private key PEM.
- Region.
- Passphrase nếu private key được mã hóa.

API key không phải lựa chọn mặc định cho production workload nếu instance/resource/workload identity có thể dùng được.

### 11.2. OCI config file

Ví dụ profile local:

~~~ini
[DEFAULT]
user=ocid1.user.oc1..REPLACE_WITH_USER_OCID
fingerprint=REPLACE_WITH_KEY_FINGERPRINT
key_file=C:\\Users\\developer\\.oci\\oci_api_key.pem
tenancy=ocid1.tenancy.oc1..REPLACE_WITH_TENANCY_OCID
region=ap-singapore-1
~~~

Đây là cấu trúc minh họa. Thay các giá trị bằng thông tin trong tenancy của bạn. Private key phải được bảo vệ bằng file permission và passphrase phù hợp; không commit file config hoặc PEM vào Git.

Có thể tạo nhiều profile, ví dụ DEFAULT, DEV_USER hoặc READ_ONLY_USER. Không dùng profile admin cho mọi tác vụ.

### 11.3. Java SDK với config profile

~~~java
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.ConfigFileAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.ObjectStorageClient;

public final class LocalOciClientFactory {

    public ObjectStorage create(String profile, String regionId)
            throws java.io.IOException {

        var provider =
                new ConfigFileAuthenticationDetailsProvider(profile);

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(regionId))
                .build(provider);
    }
}
~~~

Profile cung cấp danh tính user và thông tin ký request. User vẫn cần thuộc group có policy phù hợp với resource/compartment.

### 11.4. Session token

OCI SDK/CLI cũng hỗ trợ session token-based authentication. Session token thường được dùng với phiên đăng nhập ngắn hạn từ CLI và tránh sử dụng API private key trực tiếp trong một số quy trình. Token có thời hạn và cần refresh theo cơ chế phiên.

Không copy session token vào application.yml hoặc log. Khi session hết hạn, tạo phiên mới thay vì cố kéo dài token bằng cách thay thời gian trong config.

## 12. Tích hợp OCI Java SDK trong Spring Boot

### 12.1. Chọn authentication provider theo môi trường

| Môi trường | Provider khuyến nghị |
| --- | --- |
| Developer laptop | Config file profile hoặc session token |
| Compute instance | Instance principal |
| OCI Functions | Resource principal |
| OKE enhanced cluster | OKE workload identity |
| CI/CD ngoài OCI | Workload identity federation nếu được cấu hình; API key chỉ là phương án có kiểm soát |
| Local integration test | Test double hoặc provider test riêng; tránh dùng quyền production |

Tách authentication provider khỏi business service. Service chỉ cần một Object Storage client hoặc interface của ứng dụng, không cần biết private key nằm ở đâu.

### 12.2. Spring configuration properties

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "oci")
public record OciProperties(
        String region,
        String compartmentOcid,
        String authMode,
        String profile) {
}
~~~

Cấu hình local:

~~~yaml
oci:
  region: ap-singapore-1
  compartment-ocid: OCI_COMPARTMENT_OCID
  auth-mode: config-file
  profile: DEFAULT
~~~

Production nên chọn auth-mode từ deployment configuration và validate rõ. Không tự động fallback sang API key nếu instance/workload principal không hoạt động; fallback có thể che giấu lỗi IAM và vô tình mở một danh tính mạnh hơn.

### 12.3. Spring bean cho local profile

~~~java
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.ConfigFileAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.ObjectStorageClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OciLocalConfiguration {

    @Bean(destroyMethod = "close")
    ObjectStorage objectStorage(OciProperties properties)
            throws java.io.IOException {

        var provider =
                new ConfigFileAuthenticationDetailsProvider(
                        properties.profile());

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(properties.region()))
                .build(provider);
    }
}
~~~

Bean quản lý vòng đời client và đóng tài nguyên khi Spring context dừng. Cần cấu hình dependency OCI Java SDK Object Storage tương thích và quản lý version thống nhất bằng OCI SDK BOM hoặc version catalog của dự án.

### 12.4. Spring bean cho Compute instance principal

~~~java
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.InstancePrincipalsAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.ObjectStorageClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OciInstanceConfiguration {

    @Bean(destroyMethod = "close")
    ObjectStorage objectStorage(OciProperties properties) {
        var provider =
                InstancePrincipalsAuthenticationDetailsProvider.builder().build();

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(properties.region()))
                .build(provider);
    }
}
~~~

Chỉ dùng cấu hình này trên môi trường OCI Compute đã có dynamic group và policy. Không chạy bean này trên laptop rồi mong SDK tự có instance certificate.

### 12.5. Dùng Object Storage client

Ví dụ liệt kê bucket trong compartment được cấu hình:

~~~java
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.requests.ListBucketsRequest;
import org.springframework.stereotype.Service;

@Service
public class BucketCatalogService {
    private final ObjectStorage objectStorage;
    private final OciProperties properties;

    public BucketCatalogService(
            ObjectStorage objectStorage,
            OciProperties properties) {
        this.objectStorage = objectStorage;
        this.properties = properties;
    }

    public int countBuckets(String namespace) {
        var response = objectStorage.listBuckets(
                ListBucketsRequest.builder()
                        .namespaceName(namespace)
                        .compartmentId(properties.compartmentOcid())
                        .build());

        return response.getItems().size();
    }
}
~~~

Operation này cần quyền list/read bucket phù hợp trong compartment. Namespace Object Storage là thông tin riêng của tenancy; có thể lấy qua GetNamespace API. Không dùng namespace như compartment OCID.

### 12.6. Đóng client và xử lý lỗi

OCI SDK client dùng HTTP connection pool và nên được tái sử dụng, không tạo mới cho từng request HTTP của Spring. Quản lý vòng đời bằng Spring bean.

Khi xử lý lỗi:

- Ghi request ID do OCI trả về để hỗ trợ điều tra.
- Không log Authorization header, private key, session token hoặc nội dung tài liệu.
- Phân biệt lỗi xác thực với lỗi policy.
- Kiểm tra region endpoint và compartment OCID.
- Áp dụng timeout/retry có giới hạn theo tính chất operation.
- Với retry upload/create, dùng idempotency hoặc kiểm tra trạng thái để tránh tạo duplicate.

## 13. Thiết kế compartment và policy cho document-service

### 13.1. Cây compartment đề xuất

~~~text
Tenancy
└── Platform
    ├── AppRuntime
    │   └── document-service instances / OKE cluster
    ├── AppData
    │   └── contract bucket / database
    └── Security
        └── audit and key resources
~~~

Resource runtime và data tách compartment để quyền compute không tự động trở thành quyền quản trị dữ liệu. Nhóm vận hành, nhóm đọc dữ liệu và workload có policy khác nhau.

### 13.2. Nhóm và quyền

| Principal | Scope | Quyền mong muốn |
| --- | --- | --- |
| PlatformAdmins | Platform | Quản trị resource theo trách nhiệm |
| DocumentReaders | AppData | Đọc bucket/object được phép |
| DocumentServiceInstances | AppData | Đọc object hoặc upload object theo use case |
| SecurityAuditors | Tenancy/AppData | Inspect/audit theo scope |
| NetworkAdmins | Shared-Network | Quản trị VCN và network resource |

Không cấp PlatformAdmins cho runtime workload. Nếu một service cần đọc object, nó không cần quyền tạo bucket, sửa IAM policy hoặc xóa compartment.

### 13.3. Policy mẫu cho read-only

~~~text
Allow group <identity-domain>/DocumentReaders to read buckets in compartment AppData

Allow group <identity-domain>/DocumentReaders to read objects in compartment AppData
where target.bucket.name = 'contracts-prod'
~~~

### 13.4. Policy mẫu cho Compute workload

Matching rule:

~~~text
ALL {
  instance.compartment.id = '<APP_RUNTIME_COMPARTMENT_OCID>',
  tag.Application.Role.value = 'document-service'
}
~~~

Policy:

~~~text
Allow dynamic-group DocumentServiceInstances to read buckets in compartment AppData

Allow dynamic-group DocumentServiceInstances to read objects in compartment AppData
where target.bucket.name = 'contracts-prod'
~~~

### 13.5. Policy mẫu cho OKE workload

~~~text
Allow any-user to read objects in compartment AppData where all {
  request.principal.type = 'workload',
  request.principal.namespace = 'documents',
  request.principal.service_account = 'document-service',
  request.principal.cluster_id = '<OKE_CLUSTER_OCID>',
  target.bucket.name = 'contracts-prod'
}
~~~

Policy trên gắn quyền với đúng workload identity và bucket. OKE workload identity không dùng dynamic group; phải dùng policy condition nhận diện workload.

### 13.6. Kiểm tra quyền trước khi triển khai

Trước khi deploy production:

1. Xác minh OCID của tenancy, compartment, instance/cluster và bucket.
2. Xác minh region của bucket và region endpoint của client.
3. Xác minh principal runtime đúng loại.
4. Kiểm tra dynamic group matching rule hoặc OKE workload identity.
5. Kiểm tra policy statement ở đúng scope.
6. Thử read-only operation trước.
7. Thử một request bị từ chối để xác nhận quyền không vượt phạm vi.
8. Kiểm tra Audit log để xác nhận principal OCID/workload identity.

## 14. Troubleshooting lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| 401 NotAuthenticated | API key/fingerprint sai, key chưa đăng ký, token hết hạn hoặc certificate rotation đúng lúc request | Kiểm tra provider, fingerprint, token refresh và thử lại có kiểm soát |
| 403 NotAuthorizedOrNotFound | Principal thiếu policy hoặc scope sai | Kiểm tra group/dynamic group, verb, resource type, compartment và condition |
| Không thấy bucket | Đang chọn sai region, sai namespace hoặc compartment OCID | Xác minh region endpoint, namespace và compartment |
| Policy đúng nhưng instance vẫn bị từ chối | Instance chưa thuộc dynamic group hoặc matching rule sai | Kiểm tra instance OCID/compartment/tag và thời gian propagation |
| Workload OKE bị từ chối | Cluster không phải enhanced, service account sai hoặc condition cluster OCID sai | Kiểm tra OKE workload identity setup và SDK version |
| API gọi đúng region nhưng resource không tồn tại | Tenancy chưa subscribe region hoặc service không có ở region đó | Kiểm tra region subscription và service availability |
| SDK gọi nhầm endpoint | Config file region hoặc builder region không đúng | Đặt region identifier rõ ràng |
| Một thao tác cần nhiều quyền | API operation phụ thuộc nhiều resource type | Tra detailed policy reference và thêm statement cụ thể |
| Có quyền ở parent compartment ngoài dự kiến | Policy inheritance | Review policy ở tenancy và parent compartments |
| Thay đổi dynamic group chưa có hiệu lực | Matching rule propagation | Chờ propagation theo tài liệu và kiểm tra membership |
| Không list được object dù đọc object được | Thiếu quyền inspect/list hoặc operation khác cần permission riêng | Xem chính xác API operation và verb-resource mapping |
| Local chạy nhưng production lỗi | Local dùng API key mạnh hơn workload principal | Kiểm tra principal production và policy least privilege |

### 14.1. Dùng request ID để điều tra

OCI response thường cung cấp request ID, ví dụ opc-request-id. Khi gặp lỗi:

- Lưu request ID cùng timestamp, service, region và environment.
- Không ghi private key, token hoặc request body nhạy cảm.
- Kiểm tra Audit event với principalId.
- Đối chiếu operation API và resource OCID.
- Xác minh policy được áp dụng tại home region và compartment scope đúng.

### 14.2. Kiểm tra policy bằng Console và SDK

Console giúp xem policy, group, dynamic group và compartment hierarchy. Với SDK/CLI, lấy compartment, group và resource metadata để so sánh OCID. Khi kiểm tra quyền, sử dụng đúng principal của workload; thử bằng tài khoản administrator không chứng minh ứng dụng có quyền.

## 15. Bài tập thực hành tổng hợp

Bạn được giao triển khai document-service trên OCI. Compute chạy trong AppRuntime, hợp đồng lưu trong bucket contracts-prod thuộc AppData. Ứng dụng cần đọc object, trong khi đội vận hành có quyền quản lý bucket. Môi trường thử nghiệm dùng API key profile, còn production dùng instance principal hoặc OKE workload identity.

**Nhiệm vụ:**

1. Vẽ tenancy root và tạo compartment Platform, AppRuntime, AppData, Security.
2. Ghi lại tenancy OCID và compartment OCID từ Console.
3. Xác định home region, realm và subscribe một region cần triển khai.
4. Lấy region identifier và danh sách availability domain của tenancy.
5. Thiết kế dynamic group cho Compute instance theo compartment và tag.
6. Viết policy cho workload chỉ đọc bucket/object trong AppData.
7. Tạo OKE workload identity policy giới hạn namespace, service account và cluster OCID.
8. Cấu hình OCI Java SDK profile local và client instance principal production.
9. Tạo Spring bean ObjectStorage client và gọi ListBuckets/GetObject theo scope.
10. Kiểm tra request ID và Audit event để xác nhận principal.
11. Thử request ngoài compartment/bucket được cấp và xác nhận bị từ chối.
12. Viết tài liệu vận hành cho đổi region, move compartment, thay matching rule và review policy.

**Câu hỏi tự đánh giá:**

- Tenancy khác compartment ở điểm nào?
- Vì sao compartment được xem là global qua nhiều region?
- Policy ở parent compartment ảnh hưởng child compartment như thế nào?
- OCID có những thành phần nào và vì sao không phải OCID nào cũng chứa region?
- Home region có thể đổi sau khi tenancy được tạo không?
- Region subscription áp dụng ở cấp user hay tenancy?
- Availability domain và fault domain khác nhau như thế nào?
- Bốn verb inspect/read/use/manage khác nhau ra sao?
- Vì sao inspect objects không tương đương read objects?
- Vì sao API operation có thể cần policy cho nhiều resource type?
- Dynamic group khác user group như thế nào?
- Instance principal lấy danh tính từ đâu?
- OKE workload identity được xác định bằng những thuộc tính nào?
- Vì sao OKE workload identity không dùng dynamic group?
- Khi nào dùng API key profile và khi nào dùng instance principal?
- Vì sao không dùng manage all-resources để xử lý nhanh lỗi 403?

**Đáp án định hướng:** tenancy là ranh giới tài khoản/root, compartment là ranh giới logic; compartment và IAM policy là tài nguyên cross-region; policy parent được kế thừa xuống child; OCID gồm version/resource type/realm/region tùy resource/unique ID; home region không đổi được; region subscription ở cấp tenancy và không thể unsubscribe; AD là nhóm data center trong region, FD là nhóm hạ tầng trong AD; verb tăng dần quyền; inspect objects không tải nội dung; operation có thể cần quyền trên nhiều resource type; dynamic group xác định membership theo matching rule; instance principal dùng certificate do OCI cấp/rotate; OKE workload identity dùng cluster, namespace và service account; OKE workload identity không dùng dynamic group; API key phù hợp local có kiểm soát, instance/workload identity phù hợp runtime; quyền manage all-resources làm tăng blast radius và che giấu policy thiếu chính xác.

## 16. Tài liệu tham khảo chính thức

- [OCI – Managing Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcompartments.htm): tạo, quản lý và di chuyển compartment; quyền kế thừa.
- [OCI – Policy Inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Inheritance.htm): cách compartment con kế thừa policy từ parent.
- [OCI – Resource Identifiers](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/identifiers.htm): cấu trúc OCID, realm, region và cách tìm tenancy OCID.
- [OCI – Regions and Availability Domains](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm): region, realm, AD, FD và phạm vi resource.
- [OCI – Managing Regions](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingregions.htm): home region và region subscription.
- [OCI – IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm): policy grammar, subject, verb, resource, location và condition.
- [OCI – Deny Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/denypolicies.htm): tính năng deny opt-in, mức ưu tiên so với allow và cảnh báo account lockout.
- [OCI – Verbs](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Verbs.htm): inspect, read, use, manage và các ngoại lệ.
- [OCI – Common Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm): ví dụ policy cho Object Storage và các resource.
- [OCI – Managing Dynamic Groups](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingdynamicgroups.htm): dynamic group và matching rules.
- [OCI – Calling Services from an Instance](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm): instance principal, dynamic group và Java SDK.
- [OCI – SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm): profile, tenancy/user OCID, fingerprint, key file và region.
- [OCI – Java SDK Getting Started](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkgettingstarted.htm): AuthenticationDetailsProvider, config profile và client setup.
- [OCI – Granting Workloads Access to OCI Resources](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm): OKE workload identity, policy condition và Java SDK support.
- [OCI Java SDK – ObjectStorageClient](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/ObjectStorageClient.html): builder và service client.
- [OCI – SDK Authentication Methods](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdk_authentication_methods.htm): API key, session token, instance principal và resource principal.

**Ghi nhớ:** Tenancy xác định ranh giới tài khoản; compartment tổ chức tài nguyên và kế thừa policy; OCID xác định chính xác resource; region quyết định endpoint và vị trí triển khai; IAM policy nối principal với verb, resource type và scope. Trong Spring Boot production, ưu tiên instance principal, resource principal hoặc OKE workload identity phù hợp runtime, sau đó cấp policy hẹp nhất để ứng dụng chỉ thao tác đúng compartment và resource cần thiết.
