# Data residency và thiết kế kiểm soát theo yêu cầu tuân thủ

## 1. Mục tiêu và phạm vi

Trong chương **An toàn thông tin và kiểm toán** của module **CLOUD_PROVIDERS_ORACLE**, data residency là một yêu cầu kiến trúc xuyên suốt tenancy, IAM, mạng, Compute, lưu trữ, cơ sở dữ liệu và vận hành. Chọn region cho database mới chỉ xác định vị trí của một thành phần. Bản sao, backup, log, dữ liệu định danh và đường hỗ trợ kỹ thuật cũng cần được xem xét.

Bài học hướng dẫn cách chuyển yêu cầu tuân thủ thành quyết định triển khai có thể kiểm tra trên Oracle Cloud Infrastructure. Sau bài học, người học có thể:

- Phân biệt vị trí lưu dữ liệu, vị trí xử lý, quyền truy cập và quyền tài phán.
- Lập danh mục dữ liệu cùng sơ đồ luồng đi qua các dịch vụ và bên thứ ba.
- Đánh giá region, realm, home region và identity domain theo phạm vi dữ liệu.
- Thiết kế kiểm soát cho triển khai, sao chép, backup, log, khóa mã hóa và hỗ trợ.
- Gắn mỗi yêu cầu với người chịu trách nhiệm, cách kiểm tra và bằng chứng.
- Cân bằng giới hạn vị trí dữ liệu với tính sẵn sàng, khả năng khôi phục và chi phí.

Các điều kiện địa lý, thời hạn lưu và mục tiêu khôi phục trong ví dụ là **giả định của dự án**, không phải kết luận về pháp luật của một quốc gia. Khi triển khai thật, phải lấy yêu cầu đã được chủ dữ liệu và bộ phận phụ trách tuân thủ xác nhận làm đầu vào.

## 2. Phân biệt những yêu cầu thường bị gộp chung

### 2.1. Các khái niệm cần tách riêng

| Khái niệm | Câu hỏi thiết kế cần trả lời |
| --- | --- |
| Data residency | Dữ liệu được lưu ở những vị trí địa lý nào? |
| Vị trí xử lý | Ứng dụng, phân tích, quét nội dung hoặc tác vụ AI xử lý dữ liệu ở đâu? |
| Data localization | Có yêu cầu phải giữ hoặc xử lý một phạm vi dữ liệu trong lãnh thổ xác định không? |
| Data sovereignty | Quyền tài phán và quyền kiểm soát dữ liệu, vận hành được yêu cầu như thế nào? |
| Kiểm soát truy cập | Danh tính nào được đọc, xuất, sửa hoặc quản trị dữ liệu? |
| Kiểm soát chuyển dữ liệu | Những luồng nào được phép đưa dữ liệu sang địa điểm hoặc bên nhận khác? |

Đây là cách phân rã yêu cầu phục vụ thiết kế kỹ thuật. Ý nghĩa ràng buộc của từng thuật ngữ phải được xác định trong văn bản áp dụng cho dự án.

Một hệ thống có thể lưu database tại region được phép nhưng vẫn gửi toàn bộ nội dung request đến nền tảng quan sát ngoài phạm vi đó. Một hệ thống khác không sao chép database sang region khác, nhưng nhân viên hỗ trợ có thể tải bản export về máy cá nhân. Cả hai tình huống đều cần được kiểm tra trong bản đồ dữ liệu.

Mã hóa giúp bảo vệ tính bí mật và kiểm soát việc sử dụng khóa. Nó không thay đổi địa điểm vật lý của bản ciphertext. Vì vậy, “đã mã hóa” không đủ để xác nhận một yêu cầu về nơi lưu bản sao đã được đáp ứng.

### 2.2. Năm chiều của một yêu cầu có thể triển khai

Một phát biểu như “dữ liệu phải ở trong khu vực được phép” còn quá rộng. Hãy chuyển nó thành năm chiều:

1. **Đối tượng:** dữ liệu nào, gồm những thuộc tính và bản dẫn xuất nào?
2. **Hoạt động:** lưu trữ, xử lý, sao chép, truy cập, truyền tải hay xóa?
3. **Địa điểm:** region, quốc gia, nhóm địa lý hoặc loại môi trường nào?
4. **Chủ thể:** ứng dụng, người vận hành, nhà cung cấp và bên nhận nào?
5. **Bằng chứng:** cấu hình, log, tài liệu dịch vụ hoặc hồ sơ phê duyệt nào chứng minh?

Ví dụ, thay vì chỉ ghi “dữ liệu khách hàng ở châu Âu”, một dự án giả định có thể quy định:

> Payload hồ sơ khách hàng, bản backup và file export chỉ được lưu hoặc xử lý trong hai region thương mại OCI eu-frankfurt-1 và eu-amsterdam-1. Log không được chứa payload hồ sơ. Các luồng dữ liệu định danh, metadata vận hành và hỗ trợ kỹ thuật phải được đánh giá riêng trước khi đưa hệ thống vào vận hành.

Điều kiện trên vẫn cần xác minh tính khả thi cho từng dịch vụ. Nó không tự khẳng định rằng hai region đã đáp ứng mọi yêu cầu pháp lý, quyền tài phán hay chủ quyền vận hành của dự án.

## 3. Hiểu đúng các ranh giới của OCI

### 3.1. Region, availability domain và fault domain

Region là một khu vực địa lý cục bộ. Availability domain nằm trong region; fault domain hỗ trợ phân tách hạ tầng bên trong availability domain. Phân bố workload giữa các fault domain hoặc availability domain không đồng nghĩa đã triển khai sang region khác. Số lượng availability domain và mức sẵn có của dịch vụ phải được kiểm tra cho region được chọn. [Region và availability domain của OCI](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm).

Khi đánh giá cư trú dữ liệu, cần phân biệt:

- Vị trí tài nguyên chính.
- Vị trí các bản sao cùng region.
- Vị trí bản sao khác region.
- Vị trí máy hoặc dịch vụ xử lý dữ liệu.
- Đường truyền và địa điểm của các bên nhận.

Một ứng dụng chạy tại region được phép vẫn có thể đọc database ngoài phạm vi cho phép. Ngược lại, database đúng region không ngăn ứng dụng gửi dữ liệu ra một API bên ngoài.

### 3.2. Compartment là phạm vi quản trị

Compartment dùng để tổ chức tài nguyên và cấp quyền, không phải một địa điểm địa lý. Cùng một compartment có thể chứa tài nguyên ở nhiều region.

Tên như `EU-Production` hoặc tag `Residency=EU` hữu ích cho phân loại nhưng không tự tạo rào cản địa lý. Muốn coi đó là một kiểm soát, phải có cơ chế đọc giá trị, kiểm tra điều kiện và ngăn hoặc phát hiện cấu hình sai.

Tương tự, tenancy riêng giúp tách phạm vi quản trị và trách nhiệm. Việc tách tenancy không tự chứng minh rằng tất cả dịch vụ, identity domain và bản sao của tenancy đều nằm trong địa điểm mong muốn.

### 3.3. Home region cần được quyết định sớm

Home region của tenancy chứa các định nghĩa IAM và thông tin tài khoản liên quan; không thể đổi home region của tenancy sau khi đã được cấp phát. Nhiều tài nguyên IAM có phạm vi xuyên region và thay đổi được truyền tới các region của tenancy. [Quản lý region và home region](https://docs.oracle.com/en-us/iaas/Content/Identity/regions/managingregions.htm).

Vì vậy, không chọn home region chỉ theo độ trễ đến máy của quản trị viên. Trước khi tạo tenancy, cần đánh giá dữ liệu quản trị và định danh, mô hình region dự kiến, yêu cầu vận hành và khả năng đáp ứng của dịch vụ.

Home region cũng không phải một chỉ thị bắt mọi tài nguyên nghiệp vụ chạy tại đó. Tài nguyên như Compute, bucket hoặc database có vị trí triển khai riêng theo dịch vụ.

### 3.4. Identity domain có replication và DR riêng

Default identity domain tự động replicate đến các region mà tenancy đã subscribe. Các identity domain bổ sung có home region được chọn khi tạo và chỉ replicate sang region khác khi được bật. Việc bật hoặc tắt replication không thay đổi cơ chế disaster recovery của identity domain. [Replication của identity domain](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/to-manage-regions-for-domains.htm).

Với các region có cross-region DR của identity domains, Oracle quản lý các cặp region DR. Đây là cơ chế phải xem xét riêng với replication do khách hàng cấu hình. [Disaster recovery và identity domains](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/disaster_recovery_and_domains.htm).

Hệ quả đối với thiết kế là:

- Đăng ký thêm region có thể ảnh hưởng phạm vi dữ liệu của Default domain.
- Một domain bổ sung hỗ trợ lựa chọn replication có chủ đích, nhưng không đủ để kết luận mọi dữ liệu định danh chỉ tồn tại trong một region.
- Cần xác minh region DR, dữ liệu được bảo vệ và hành vi của loại domain thực tế.
- Nhu cầu “payload nghiệp vụ ở hai region được phép” và “mọi dữ liệu định danh chỉ ở một quốc gia” phải được đánh giá thành hai yêu cầu riêng.

Không giải quyết một yêu cầu chặt về định danh bằng cách chỉ nhìn vào region của database.

### 3.5. Realm và lựa chọn môi trường sovereign

Các region OCI được nhóm thành realm. Oracle EU Sovereign Cloud hoạt động trong realm tách biệt với các region thương mại thông thường và có mô hình vận hành riêng. Chọn một region thương mại nằm trong EU không có nghĩa đang sử dụng EU Sovereign Cloud. [Oracle EU Sovereign Cloud](https://docs.oracle.com/en-us/iaas/Content/sovereign-cloud/eu-sovereign-cloud.htm).

Khi đánh giá một môi trường sovereign, cần kiểm tra đủ địa điểm, mô hình pháp nhân/vận hành, nhân sự hỗ trợ, dịch vụ sẵn có, kết nối, hợp đồng và trách nhiệm phía khách hàng.

Ngay cả khi có ranh giới realm, ứng dụng vẫn cần kiểm soát những luồng xuất dữ liệu do người dùng hoặc chương trình được cấp quyền thực hiện. Không dùng tên sản phẩm làm bằng chứng thay cho sơ đồ luồng và cấu hình triển khai.

## 4. Lập danh mục dữ liệu và sơ đồ luồng

### 4.1. Đừng chỉ kiểm kê bảng dữ liệu chính

Một danh mục đủ dùng cho thiết kế nên gồm:

| Nhóm dữ liệu | Những nơi cần kiểm tra |
| --- | --- |
| Payload nghiệp vụ | Database, Object Storage, file, message, cache |
| Bản dẫn xuất | Báo cáo, index tìm kiếm, dữ liệu phân tích, embedding |
| Bản phục hồi | Backup, snapshot, bản standby, bản phục vụ restore |
| Dữ liệu vận hành | Log, trace, lỗi ứng dụng, crash dump |
| Dữ liệu định danh | Hồ sơ người dùng, thuộc tính xác thực, cấu hình federation |
| Khóa và secret | Vault, bản replica, hệ thống quản lý secret liên quan |
| Dữ liệu hỗ trợ | File đính kèm ticket, gói chẩn đoán, phiên truy cập |
| Dữ liệu phát triển | Fixture, bản export, bản sao test, artifact CI/CD |

Cache hoặc file tạm vẫn là bản sao trong thời gian tồn tại. Bản ghi log chỉ chứa một phần payload vẫn có thể mang thông tin cần bảo vệ. Việc đổi tên trường hoặc bỏ tên người dùng không tự chứng minh dữ liệu đã được ẩn danh.

### 4.2. Mỗi luồng phải có nguồn, đích và mục đích

Với mỗi luồng, ghi ít nhất:

~~~text
Mã luồng:
Chủ dữ liệu và người phê duyệt:
Nhóm dữ liệu / thuộc tính:
Nguồn: dịch vụ, tenancy, region:
Đích: dịch vụ, bên nhận, địa điểm:
Mục đích xử lý:
Cơ chế truyền và danh tính thực hiện:
Bản lưu trung gian / cache:
Thời hạn lưu và cách xóa:
Cơ chế kiểm soát:
Bằng chứng cần thu thập:
Điểm chưa xác minh:
~~~

Ví dụ, luồng “database → dịch vụ gửi email” cần xem email có chứa hồ sơ khách hàng hay chỉ mã thông báo nghiệp vụ. Hai payload này có thể tạo yêu cầu kiểm soát khác nhau. Không phân loại cả luồng bằng tên dịch vụ mà bỏ qua nội dung thực sự được gửi.

### 4.3. Sơ đồ tham khảo cho workload được giới hạn vị trí

~~~mermaid
flowchart LR
    U["Người dùng / bên tích hợp"] --> A["API ứng dụng"]
    subgraph P["Region chính được phê duyệt"]
        A --> DB["Database"]
        A --> O["Object Storage"]
        A --> L["Log đã loại payload"]
        K["Khóa / secret"] --> A
    end
    subgraph S["Region DR được phê duyệt"]
        DBR["Bản phục hồi database"]
        OR["Bản sao object được phép"]
        KR["Khóa cần cho phục hồi"]
    end
    DB -->|"Luồng phục hồi đã xác minh"| DBR
    O -->|"Replication được phê duyệt"| OR
    K -->|"Theo cơ chế dịch vụ hỗ trợ"| KR
    A --> X["Tích hợp ngoài: cần đánh giá dữ liệu"]
    L --> E["Kho bằng chứng có vị trí được duyệt"]
~~~

Sơ đồ là mô hình thiết kế, không khẳng định mọi dịch vụ Oracle Database hay mọi loại Vault hỗ trợ cùng một cách replication. Mỗi mũi tên phải được thay bằng cơ chế cụ thể, vị trí thật và bằng chứng xác minh trước khi triển khai.

## 5. Chuyển yêu cầu thành ma trận kiểm soát

### 5.1. Bắt đầu từ điều kiện chấp nhận được

Mỗi yêu cầu cần có tiêu chí đạt rõ ràng. Ví dụ sau tiếp tục dùng giả định chỉ hai region thương mại `eu-frankfurt-1` và `eu-amsterdam-1` được phê duyệt cho payload nghiệp vụ.

| Mã | Yêu cầu giả định | Kiểm soát đề xuất | Bằng chứng |
| --- | --- | --- | --- |
| RES-01 | Payload chính ở region được phép | Cấu hình IaC và quyền triển khai theo region | Plan, inventory, kết quả thử quyền |
| RES-02 | Bản sao và backup cũng nằm trong phạm vi | Kiểm tra đích replication, backup và restore | Cấu hình nguồn/đích, danh mục bản sao |
| RES-03 | Log không chứa payload hồ sơ | Thiết kế logging theo allowlist thuộc tính | Cấu hình logger, mẫu log đã kiểm tra |
| RES-04 | Chỉ nhóm được phép được export dữ liệu | Phân quyền đọc/xuất và kiểm soát kênh tải xuống | IAM, log truy cập phù hợp, hồ sơ phê duyệt |
| RES-05 | Hỗ trợ không nhận dữ liệu thật qua ticket thường | Quy trình tạo gói chẩn đoán đã xử lý | Mẫu gói, ticket và xác nhận kiểm tra |
| RES-06 | Khôi phục trong địa điểm được duyệt | Kịch bản restore/failover đã kiểm tra | Biên bản diễn tập, tài nguyên đích |
| RES-07 | Có thể phát hiện cấu hình lệch | Kiểm kê định kỳ và theo dõi thay đổi | Kết quả đối chiếu, cảnh báo và xử lý |

Ma trận này là thiết kế của dự án, không phải danh sách tính năng tự động được OCI bật sẵn.

Cột bằng chứng giúp phát hiện yêu cầu chưa triển khai được. Nếu nhóm chỉ có câu trả lời “đã chọn đúng region” cho RES-02 nhưng không biết backup ở đâu, yêu cầu đó chưa có đủ bằng chứng.

### 5.2. Xác định chủ sở hữu

Chủ dữ liệu xác định dữ liệu nào thuộc phạm vi. Nhóm tuân thủ xác nhận điều kiện áp dụng. Nhóm nền tảng triển khai IAM, region và cấu hình dùng chung. Nhóm ứng dụng chịu trách nhiệm payload, logging và tích hợp. Nhóm vận hành giữ bằng chứng, kiểm tra drift và diễn tập phục hồi.

Oracle và khách hàng chia sẻ trách nhiệm bảo mật: Oracle chịu trách nhiệm hạ tầng và vận hành nền tảng theo phạm vi dịch vụ; khách hàng chịu trách nhiệm cấu hình và sử dụng workload phù hợp. [Mô hình trách nhiệm chia sẻ của OCI](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/security.htm).

Một chứng nhận hoặc báo cáo của nhà cung cấp có thể là bằng chứng cho kiểm soát phía nhà cung cấp. Nó không chứng minh ứng dụng của khách hàng đã cấu hình đúng backup, loại payload khỏi log hoặc ngăn người dùng xuất dữ liệu.

## 6. Thiết kế kiểm soát nhiều lớp

### 6.1. Hạn chế quyền triển khai theo region

OCI IAM có thể dùng điều kiện `request.region` để giới hạn nơi một câu cấp quyền áp dụng. Ví dụ minh họa cho nhóm quản trị Compute:

~~~text
Allow group 'Default'/'ResidencyComputeOps' to manage instance-family in compartment RegulatedProd where any {request.region = 'fra', request.region = 'ams'}
~~~

Ở đây, `fra` và `ams` là region key, khác với region identifier `eu-frankfurt-1` và `eu-amsterdam-1` dùng trong cấu hình CLI/provider. Cần đối chiếu bảng region của môi trường thực tế, nhất là khi chuyển realm. [Cách giới hạn quyền theo region](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm).

Ví dụ giả định domain `Default`, group và compartment đã tồn tại. Nó chỉ minh họa quyền trên `instance-family`; quyền network, volume hoặc tài nguyên phụ thuộc phải được thiết kế riêng.

Có hai giới hạn quan trọng:

1. Các câu `Allow` cấp quyền theo hướng cộng dồn. Một policy có điều kiện region không hủy quyền rộng mà principal đã được cấp qua policy hoặc group khác. [Cách OCI IAM policy hoạt động](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policies.htm).
2. Region của request không tự đại diện cho mọi nơi nhận dữ liệu. Với API sao chép, replication hoặc export, phải kiểm tra tham số đích và quyền riêng mà dịch vụ sử dụng.

Không suy ra rằng một câu `request.region='fra'` sẽ chặn mọi bản sao từ Frankfurt đi nơi khác. Dịch vụ có thể đánh giá quyền ở nguồn, ở đích hoặc có biến điều kiện chuyên biệt.

Ví dụ, việc copy Block Volume backup có các quyền ở source và destination; Oracle mô tả cách giới hạn theo `request.region` và `target.region` cho trường hợp này. Chỉ dùng điều kiện được API tương ứng hỗ trợ. [Copy volume backup giữa các region](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/copy-bv-backup.htm).

Ngoài policy của người dùng, cần rà soát dynamic group, workload principal, service principal và quyền cross-tenancy nếu có. Một pipeline không chịu kiểm soát phù hợp có thể tạo đường đi dữ liệu khác với tài khoản quản trị thường dùng.

### 6.2. Kiểm tra cấu hình trước khi triển khai

Một pipeline IaC nên kiểm tra các trường liên quan đến vị trí dữ liệu, không chỉ biến provider region:

- Region của tài nguyên chính.
- Region và bucket đích của replication.
- Vị trí backup, standby và tài nguyên được tạo khi restore.
- Region của khóa, secret và bản replica.
- Đích của connector chuyển log, trace hoặc thông điệp.
- Endpoint bên ngoài và dữ liệu dự định gửi.
- Provider alias hoặc module có thể triển khai ở region khác.

Một allowlist có thể được thể hiện dưới dạng dữ liệu thiết kế:

~~~json
{
  "policyVersion": "example-1",
  "dataClass": "customer-profile",
  "allowedStorageRegions": [
    "eu-frankfurt-1",
    "eu-amsterdam-1"
  ],
  "allowedProcessingRegions": [
    "eu-frankfurt-1",
    "eu-amsterdam-1"
  ],
  "allowedReplicaRegions": [
    "eu-frankfurt-1",
    "eu-amsterdam-1"
  ],
  "payloadInApplicationLogs": false,
  "externalExportRequiresApproval": true,
  "identityResidencyReview": "required"
}
~~~

Đây là **schema minh họa do dự án định nghĩa**, không phải một tài nguyên hay policy OCI có thể gửi thẳng lên API. Nhóm triển khai phải xây dựng bộ kiểm tra đọc nó, xác định cách ánh xạ với plan và xử lý các trường chưa biết.

Đặt điều kiện kiểm tra trong pipeline có quản lý phiên bản và hạn chế quyền bỏ qua. Kiểm tra biến đầu vào đơn lẻ chỉ hữu ích nếu mọi tài nguyên và mọi đường triển khai đều dùng đúng biến đó.

### 6.3. Ngăn đường đi dữ liệu ngoài dự kiến

Đối với VCN và workload, xem xét egress tới API công cộng, SaaS, hệ thống email, kho artifact, máy quản trị và mạng on-premises. Chọn cơ chế mạng cùng chính sách ứng dụng phù hợp với các đích đã được duyệt.

Cần phân biệt quyền **kết nối** với quyền **đọc dữ liệu**. Một ứng dụng bị hạn chế egress vẫn có thể gửi dữ liệu đến đích hợp lệ nếu đích đó chấp nhận payload không phù hợp. Một người được quyền tải object có thể tạo bản sao trên thiết bị bên ngoài dù bucket vẫn ở đúng region.

Private endpoint hoặc kết nối riêng hỗ trợ kiểm soát đường truy cập. Chúng không tự chứng minh địa điểm lưu trữ, xử lý và vận hành của hệ thống ở đầu bên kia. Với yêu cầu ràng buộc đường truyền vật lý, cần xác minh cả tuyến và phạm vi cam kết của bên cung cấp kết nối.

Đối với truy cập quản trị từ xa, xác định thiết bị được phép, nơi lưu file tải xuống, khả năng sao chép nội dung, thời gian cấp quyền và nhật ký phiên khi cần. Đây là phần của thiết kế luồng dữ liệu, không chỉ là cấu hình firewall.

### 6.4. Dùng Security Zones đúng phạm vi

Security Zones kiểm tra những thao tác tài nguyên thuộc phạm vi policy của recipe và từ chối thao tác vi phạm. Các nhóm kiểm soát có thể bao gồm hạn chế public access, yêu cầu mã hóa và hạn chế một số hoạt động di chuyển/liên kết tài nguyên. [Security Zone policies](https://docs.oracle.com/en-us/iaas/Content/security-zone/using/security-zone-policies.htm).

Khi áp dụng, phải xem recipe cụ thể, loại tài nguyên và API được bao phủ. Security zone là ranh giới kiểm soát cấu hình; không được đồng nhất nó với một quốc gia hoặc một danh sách region được phép.

Trong ma trận tuân thủ, ghi chính xác policy nào bảo vệ đường đi nào. Không ghi chung “đã có Security Zones nên mọi dữ liệu không thể rời khu vực”.

### 6.5. Phát hiện cấu hình lệch và thay đổi quyền

Kết hợp kiểm kê định kỳ với theo dõi thay đổi để phát hiện:

- Tài nguyên hoặc bản sao xuất hiện ở region ngoài danh sách.
- Thay đổi replication, backup target, connector hoặc endpoint.
- Policy mới cấp quyền rộng hơn điều kiện đã duyệt.
- Thêm group membership hoặc đổi dynamic group làm principal có thêm quyền.
- Thay đổi log khiến payload nhạy cảm bị ghi nhận.
- Ngoại lệ hết hạn nhưng cấu hình vẫn còn hiệu lực.

Tag và tên tài nguyên giúp tìm kiếm, nhưng đối chiếu phải dựa trên vị trí và cấu hình thật. Công cụ phát hiện cần có đủ quyền quan sát; một inventory bị giới hạn quyền không chứng minh phần còn lại của tenancy không có tài nguyên.

## 7. Kiểm soát theo từng lớp dữ liệu

### 7.1. Database, backup và khôi phục

Với Oracle Database trên OCI, hãy chốt sản phẩm và mô hình triển khai cụ thể trước khi quyết định cơ chế dự phòng. Database trên Compute, DB System, Exadata và Autonomous Database có tính năng, giới hạn và cách quản trị khác nhau.

Danh mục cần xác minh gồm:

| Hạng mục | Câu hỏi phải trả lời |
| --- | --- |
| Database chính | Dịch vụ, region, nơi xử lý, khóa và đường truy cập là gì? |
| Backup | Nơi lưu, lịch tạo, thời hạn giữ, cơ chế copy là gì? |
| Standby hoặc replica | Region nào, dữ liệu gì được đồng bộ, ai được đổi đích? |
| Restore/clone | Hệ thống sẽ được tạo ở đâu, ai có thể chọn region? |
| Export | File được ghi ra bucket/máy nào và còn lưu ở đâu? |
| Dữ liệu chẩn đoán | Trace, dump hoặc gói hỗ trợ có chứa dữ liệu thật không? |

Đừng gán cùng một hành vi backup cho mọi dịch vụ cơ sở dữ liệu. Lưu tài liệu và cấu hình của đúng loại dịch vụ đang dùng làm bằng chứng.

Một kịch bản restore phải xem cả database, khóa, secret, identity, mạng và đích log. Nếu restore đúng region nhưng khóa cần thiết chỉ ở một nơi không khả dụng hoặc không được phép truy cập, phương án phục hồi chưa hoàn chỉnh.

### 7.2. Object Storage và các bản sao

Replication của Object Storage có region và bucket đích được chỉ định. Việc tạo replication policy là một điểm thay đổi cấu hình cần được kiểm soát, không chỉ thao tác tạo bucket ban đầu. [Tạo Object Storage replication policy](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication_topic-To_create_a_replication_policy.htm).

Khi kiểm kê, xem cả:

- Bucket nguồn, bucket đích và region tương ứng.
- Quyền của bên tạo hoặc sửa replication.
- Các luồng copy thủ công hoặc chương trình tải/xuất object.
- Phiên bản object, bản lưu trong quá trình xử lý và chính sách retention.
- Bản dùng cho kiểm thử, phân tích hoặc tích hợp với bên thứ ba.

Việc tắt một luồng replication không có nghĩa mọi dữ liệu đã được sao chép trước đó đã bị xóa. Cần kiểm tra trạng thái đích, thời hạn lưu và bằng chứng xử lý bản sao theo yêu cầu.

### 7.3. Block Volume, image và file

Volume backup, bản copy sang region khác, custom image và file export có thể chứa dữ liệu ứng dụng hoặc secret đã ghi lên đĩa. Không phân loại chúng là “chỉ hạ tầng” khi bên trong có dữ liệu thật.

Khi kiểm soát bản sao phục hồi, đánh giá toàn bộ nội dung đĩa, không chỉ thư mục dữ liệu chính. File tạm, swap, log cục bộ và cache có thể làm phạm vi dữ liệu lớn hơn dự kiến.

### 7.4. Log, trace và dữ liệu chẩn đoán

Thiết kế logging theo các thuộc tính đã cho phép. Ví dụ, dùng mã tham chiếu nghiệp vụ và mã lỗi thay vì ghi toàn bộ request body, tài liệu đính kèm hoặc chuỗi kết nối.

Trước khi chuyển log tới Object Storage, SIEM hoặc nền tảng quan sát bên ngoài, kiểm tra payload, vị trí đích và quyền truy cập. Audit hoặc log chuyển sang kho điều tra cũng trở thành dữ liệu cần phân loại.

Việc loại bỏ payload tại nguồn thường dễ kiểm soát hơn trông chờ mọi hệ thống phía sau cùng che dữ liệu đúng cách. Tuy nhiên, chỉ được coi kiểm soát này là có hiệu lực sau khi đã quan sát mẫu log thực tế cho cả đường thành công lẫn đường lỗi.

### 7.5. Khóa mã hóa và secret

Đặt khóa tại địa điểm được phê duyệt là một quyết định riêng với đặt database hoặc bucket. Xác minh region của khóa, quyền sử dụng, cơ chế replica và các phụ thuộc khi failover.

Vault có cơ chế replication giữa các region trong cùng realm; khả năng hỗ trợ phụ thuộc loại và tình trạng vault. Không tự giả định mọi vault hiện có đều replicate được hoặc việc replicate vault đồng nghĩa secret đã có cùng cơ chế. [Replication của vault và key](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Tasks/replicatingvaults.htm).

Mã hóa và quản lý khóa hỗ trợ kiểm soát bí mật dữ liệu. Chúng phải được kết hợp với kiểm soát vị trí bản sao, quyền giải mã và luồng xử lý sau giải mã.

### 7.6. Dữ liệu hỗ trợ và metadata dịch vụ

Trước khi gửi gói chẩn đoán, xem có payload thật, token, khóa, tên khách hàng, IP hoặc đường dẫn nhạy cảm không. Dùng quy trình đã phê duyệt để tạo dữ liệu tái hiện và gói hỗ trợ tối thiểu cần thiết.

Đối với dữ liệu do nhà cung cấp xử lý để cung cấp dịch vụ, cần kiểm tra thỏa thuận và mô tả dịch vụ tương ứng. Tài liệu Oracle lưu ý việc xử lý dữ liệu có thể phụ thuộc điều khoản dịch vụ, thay vì chỉ phụ thuộc region do khách hàng chọn. [Các đặc tính bảo vệ dữ liệu của OCI](https://docs.oracle.com/en-us/iaas/Content/Resources/Assets/whitepapers/oci-privacy-features.pdf).

Trong hồ sơ kiến trúc, tách rõ customer content, dữ liệu định danh, metadata vận hành và thông tin thương mại theo phạm vi áp dụng. Trường hợp chưa rõ phải được ghi thành mục cần xác minh, không đổi thành lời bảo đảm “mọi dữ liệu đều ở một region”.

## 8. Cân bằng data residency với tính sẵn sàng và chi phí

### 8.1. Làm rõ mô hình sự cố cần chịu được

Phương án chỉ dùng một region có thể vẫn triển khai nhiều lớp dự phòng nội vùng. Tuy nhiên, phương án đó không tự giải quyết một sự cố làm toàn region không khả dụng.

Hãy đối chiếu ba lựa chọn với yêu cầu của dự án:

| Lựa chọn | Giá trị chính | Điều cần chấp nhận hoặc xác minh |
| --- | --- | --- |
| Một region, dự phòng nội vùng | Giới hạn phạm vi vị trí, giảm phụ thuộc liên region | Rủi ro mất toàn region và thời gian phục hồi |
| Hai region đều được phép | Có thể phục hồi khi mất region chính | Dịch vụ hỗ trợ, luồng replica, khóa và chi phí |
| Không có region DR phù hợp | Giữ đúng giới hạn địa lý hiện có | Cần đổi mục tiêu, đổi mô hình triển khai hoặc đánh giá lựa chọn khác |

Một mục tiêu như **RPO 15 phút, RTO 4 giờ** chỉ là yêu cầu giả định cho đến khi có kiến trúc và kết quả diễn tập chứng minh. RPO liên quan lượng dữ liệu có thể mất; RTO liên quan thời gian khôi phục khả năng cung cấp dịch vụ. Không dùng số liệu của riêng database replica để khẳng định toàn ứng dụng đạt cùng mục tiêu.

Nếu phạm vi cư trú không có địa điểm dự phòng đáp ứng yêu cầu, ghi rõ xung đột. Không âm thầm chọn region ngoài phạm vi chỉ để hoàn thành sơ đồ DR.

### 8.2. Kiểm tra mọi phụ thuộc trong failover

Kịch bản failover cần trả lời:

- Ứng dụng mới xử lý payload ở region nào?
- Database, object, file và cache được phục hồi từ đâu?
- Khóa giải mã, secret và danh tính có khả dụng không?
- Kênh log và hệ thống hỗ trợ có giữ đúng phạm vi không?
- DNS, cấu hình client và endpoint có trỏ tới đích đã duyệt không?
- Khi failback, các bản dữ liệu tạm và tài nguyên DR được xử lý ra sao?

Diễn tập bằng dữ liệu tổng hợp hoặc dữ liệu đã được phép sử dụng. Ghi lại tài nguyên thực tế được tạo và các luồng thực sự phát sinh, không chỉ kiểm tra rằng một nút “failover” đã hoàn tất.

### 8.3. Đánh giá chi phí theo vòng đời dữ liệu

Dự trù cả compute dự phòng, dung lượng bản sao, backup, phiên bản object, lưu log, truy vấn phân tích, khóa và kết nối cần thiết. Một bản sao nhỏ ban đầu có thể tăng theo thời gian lưu và tốc độ thay đổi dữ liệu.

Giảm dữ liệu không cần thiết trước khi replicate hoặc chuyển log có thể giảm đồng thời chi phí và phạm vi kiểm soát. Tuy nhiên, thời hạn xóa phải thống nhất với yêu cầu nghiệp vụ, phục hồi và giữ bằng chứng.

Giới hạn chi tiêu, quota và cảnh báo ngân sách phục vụ quản lý tài nguyên. Nếu muốn dùng chúng trong thiết kế tuân thủ, phải xác minh phạm vi thực thi cụ thể; cảnh báo chi phí không tự ngăn dữ liệu rời một địa điểm.

## 9. Thực hành: kiểm kê và phát hiện đích nằm ngoài danh sách

Bài thực hành này có thể bắt đầu bằng tra cứu và dữ liệu giả lập. Không cần đưa dữ liệu thật sang region ngoài phạm vi để chứng minh rằng một thiết kế chưa đạt yêu cầu.

### 9.1. Chuẩn bị

Giả định dự án đã phê duyệt hai region cho payload:

~~~text
eu-frankfurt-1
eu-amsterdam-1
~~~

Người học cần:

- Một danh tính có quyền đọc cấu hình cần kiểm tra.
- Profile OCI CLI `RESIDENCY_READER` trỏ đúng tenancy và endpoint phù hợp.
- Danh sách compartment, dịch vụ và nhóm dữ liệu thuộc phạm vi.
- Quyền xem cấu hình replication/backup hoặc bản xuất cấu hình do người quản trị cung cấp.

Đọc thiếu quyền phải được ghi thành giới hạn quan sát. Không coi một lỗi authorization là bằng chứng không có tài nguyên hoặc không có replication.

### 9.2. Liệt kê region subscription của tenancy

Ví dụ PowerShell:

~~~powershell
$residencyTenancy = '<TENANCY_OCID>'

$residencyOutput = & oci iam region-subscription list `
    --profile RESIDENCY_READER `
    --tenancy-id $residencyTenancy `
    --all `
    --output json

if ($LASTEXITCODE -ne 0) {
    throw 'Không đọc được region subscription; cần kiểm tra profile và quyền.'
}

$residencyJson = [string]::Join(
    [Environment]::NewLine,
    [string[]]$residencyOutput
)
$residencySubscriptions = $residencyJson |
    ConvertFrom-Json -ErrorAction Stop

if ($null -eq $residencySubscriptions.data) {
    throw 'Không có trường data trong kết quả tra cứu.'
}

$residencySubscriptions.data | Select-Object `
    @{Name = 'Region'; Expression = { $_.'region-name' }}, `
    @{Name = 'HomeRegion'; Expression = { $_.'is-home-region' }}, `
    status
~~~

Lệnh liệt kê các region subscription của tenancy; `--all` lấy mọi trang kết quả của thao tác này. [Tham chiếu CLI region subscription](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/region-subscription/list.html).

Kết quả chỉ là bước kiểm kê tenancy. Một region đã subscribe không có nghĩa mọi dữ liệu được phép triển khai tại đó; một resource không xuất hiện trong màn hình hiện tại cũng chưa chứng minh toàn tenancy không có resource tương ứng.

Sau đó, đối chiếu home region và các region subscription với đánh giá IAM/identity domain. Không thay đổi subscription trong bài kiểm kê chỉ để làm danh sách trông phù hợp hơn.

### 9.3. Kiểm kê đường sao chép thay vì chỉ tài nguyên chính

Chọn một workload được giao và lập bảng:

| Thành phần | Dữ liệu | Region nguồn | Region đích | Cấu hình đã quan sát |
| --- | --- | --- | --- | --- |
| Database chính | Hồ sơ khách hàng | Region chính | Không áp dụng | Dịch vụ và OCID |
| Phương án phục hồi database | Bản phục hồi | Region chính | Region DR | Cơ chế của đúng dịch vụ |
| Bucket tài liệu | File nghiệp vụ | Region chính | Nếu có replication | Policy và bucket đích |
| Log ứng dụng | Trường đã cho phép | Region xử lý | Kho tập trung | Connector hoặc agent |
| Khóa | Khóa cần cho workload | Region khóa | Nếu có replica | Metadata vault/key |
| Export hỗ trợ | Dữ liệu đã xử lý | Nơi tạo | Nơi nhận | Quy trình và bản phê duyệt |

Nếu một đích chưa được xác định, ghi `UNKNOWN` và giữ nó trong danh sách cần xử lý. Không thay bằng region nguồn theo suy đoán.

### 9.4. Kiểm tra một bản thiết kế giả lập

Đoạn PowerShell sau chỉ kiểm tra một danh sách giả lập trong bộ nhớ. Nó không gọi API hay thay đổi tài nguyên:

~~~powershell
$allowedDataRegions = @(
    'eu-frankfurt-1',
    'eu-amsterdam-1'
)

$designLocations = @(
    [pscustomobject]@{
        Component = 'Primary database'
        Region = 'eu-frankfurt-1'
    },
    [pscustomobject]@{
        Component = 'Object replica'
        Region = 'us-ashburn-1'
    },
    [pscustomobject]@{
        Component = 'Recovery environment'
        Region = 'eu-amsterdam-1'
    }
)

$residencyViolations = @(
    $designLocations | Where-Object {
        $allowedDataRegions -notcontains $_.Region
    }
)

if ($residencyViolations.Count -gt 0) {
    $residencyViolations | Format-Table Component, Region
    throw 'Thiết kế có địa điểm ngoài danh sách được phê duyệt.'
}
~~~

Kết quả mong đợi là phát hiện `Object replica` tại `us-ashburn-1` và báo lỗi. Đây là điều kiện của ví dụ, không phải kết luận rằng Ashburn bị cấm đối với mọi dự án.

Để áp dụng trong pipeline thật, phải trích xuất địa điểm từ plan hoặc cấu hình thực tế, bao phủ module/provider alias, tham số đích và những thành phần chưa biết. Một danh sách tự nhập chỉ kiểm tra chính danh sách đó.

### 9.5. Xác minh quyền và đường triển khai trong môi trường thử

Nếu có môi trường thử được quản trị viên cung cấp, dùng danh tính đại diện cho pipeline để kiểm tra các thao tác thuộc phạm vi:

- Thao tác cần thiết tại region được phép có đủ quyền không?
- Thao tác tương ứng ngoài phạm vi có bị chặn bởi kiểm soát dự kiến không?
- Có group hoặc policy khác khiến principal nhận quyền rộng hơn không?
- API copy/replication có kiểm tra đúng source và destination không?
- Thay đổi qua Console hoặc API trực tiếp có tạo đường bỏ qua pipeline không?

Dùng tài nguyên rỗng hoặc dữ liệu tổng hợp, thao tác được phê duyệt và cơ chế xác minh phù hợp. Đừng dùng dữ liệu thật để thử một đường truyền vốn đang được kiểm tra xem có hợp lệ hay không.

Kết quả bài thực hành là danh mục có phạm vi rõ ràng, một luồng chưa đạt yêu cầu được nhận diện và phương án kiểm soát có thể kiểm tra lại. Kết quả này chưa thay thế đánh giá toàn bộ dịch vụ và hợp đồng của hệ thống sản xuất.

## 10. Bằng chứng và vận hành liên tục

### 10.1. Bộ bằng chứng cần đủ để tái hiện kết luận

Một bộ hồ sơ có thể bao gồm:

- Yêu cầu đã phê duyệt và phiên bản danh sách địa điểm cho phép.
- Sơ đồ dữ liệu có nguồn, đích, nhóm dữ liệu và chủ sở hữu.
- Region subscription, home region và đánh giá identity domain/DR.
- Cấu hình thực tế của tài nguyên, replica, backup và khóa.
- Policy hiệu lực, phạm vi kiểm tra quyền và kết quả xác minh.
- Kết quả kiểm tra pipeline cùng những đường triển khai trực tiếp.
- Bằng chứng loại payload khỏi log và kiểm soát đích chuyển log.
- Biên bản restore/failover/failback và xử lý bản sao tạm.
- Tài liệu dịch vụ, điều khoản và những xác nhận cần thiết từ nhà cung cấp.

Mỗi bản ghi nên có thời điểm thu thập, nguồn, tenancy, region, compartment và danh tính thu thập khi phù hợp. Lưu bản xuất cấu hình đủ để kiểm tra lại, đồng thời bảo vệ chính hồ sơ vì nó có thể chứa metadata nhạy cảm.

Phân biệt ba loại bằng chứng: tài liệu mô tả khả năng dịch vụ, cấu hình đã bật và kết quả quan sát thực tế. Một trang tài liệu nói “hỗ trợ giới hạn region” chưa chứng minh giới hạn đã có hiệu lực với principal của dự án.

### 10.2. Tái đánh giá khi có thay đổi

Các sự kiện nên kích hoạt việc rà soát gồm:

- Subscribe region mới hoặc tạo identity domain mới.
- Bổ sung dịch vụ database, AI, phân tích hoặc bên tích hợp.
- Đổi region replica, backup target hoặc endpoint.
- Chuyển log sang kho tập trung hoặc đổi nội dung logger.
- Cấp quyền export, service principal hoặc cross-tenancy mới.
- Thay đổi nhà cung cấp hỗ trợ hoặc quy trình chẩn đoán.
- Thay đổi phạm vi dữ liệu, hợp đồng hoặc thời hạn lưu.

Đồng thời đối chiếu định kỳ cấu hình thực tế với thiết kế. Tài nguyên được tạo ngoài pipeline hoặc thay đổi gấp khi xử lý sự cố có thể làm hai phía lệch nhau.

### 10.3. Quản lý ngoại lệ có thời hạn

Một ngoại lệ cần ghi rõ dữ liệu, luồng, địa điểm, lý do, chủ sở hữu, người phê duyệt, thời hạn, biện pháp bù và cách kết thúc. Nếu điều kiện nền tảng không cho phép phê duyệt ngoại lệ, phải đổi phương án thay vì chỉ ghi nhận rủi ro.

Khi ngoại lệ kết thúc, kiểm tra cả việc dừng luồng và xử lý dữ liệu đã tạo: file export, bucket đích, backup, bản cache, dữ liệu trên hệ thống bên nhận và quyền tạm thời.

Trong tình huống khẩn cấp, quy trình break-glass vẫn cần quy định phạm vi hành động, ghi nhận bằng chứng và rà soát sau sự cố. Nhu cầu khôi phục nhanh phải được đưa vào thiết kế từ trước.

## 11. Những kết luận cần tránh

| Kết luận vội | Cách xác minh phù hợp |
| --- | --- |
| “Database đúng region nên toàn hệ thống đạt residency” | Kiểm kê mọi bản sao, luồng xử lý và bên nhận |
| “Tên compartment đã ghi khu vực” | Kiểm tra địa điểm thực tế và cơ chế thực thi |
| “Đã mã hóa nên có thể sao chép đi đâu cũng được” | Đối chiếu riêng vị trí bản sao và yêu cầu khóa |
| “Có policy region nên mọi đường xuất bị chặn” | Kiểm tra quyền cộng dồn, API đích và export |
| “Một domain chỉ replicate ở nơi đã chọn nên không có DR nơi khác” | Đánh giá riêng replication và DR của dịch vụ |
| “Dùng region tại EU là đang dùng EU Sovereign Cloud” | Xác minh realm, loại môi trường và thỏa thuận |
| “Chưa thấy tài nguyên nên không có dữ liệu ngoài phạm vi” | Kiểm tra quyền quan sát, region và phạm vi inventory |
| “Tắt replication là dữ liệu cũ đã được xóa” | Kiểm tra bản sao còn lại và quy trình xử lý |
| “Nhà cung cấp có chứng nhận nên ứng dụng đã tuân thủ” | Ánh xạ trách nhiệm và kiểm tra cấu hình workload |

Một quyết định triển khai có cơ sở phải gắn được **dữ liệu nào, hoạt động nào, địa điểm nào, chủ thể nào và bằng chứng nào**. Trong OCI, phương pháp này giúp nối yêu cầu tuân thủ với region, IAM, backup, mạng và vận hành, đồng thời làm rõ những điều kiện chưa được xác minh trước khi hệ thống xử lý dữ liệu thật.
