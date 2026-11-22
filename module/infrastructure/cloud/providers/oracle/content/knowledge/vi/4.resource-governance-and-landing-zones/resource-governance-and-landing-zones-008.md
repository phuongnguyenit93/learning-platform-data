# Quản lý nhiều tenancy với Organization Management

Khi doanh nghiệp sử dụng Oracle Cloud Infrastructure (OCI) cho nhiều đơn vị hoặc hệ thống cần cách ly mạnh, một tenancy có thể không đáp ứng hết mô hình quản trị. Tuy nhiên, tạo thêm tenancy cũng kéo theo nhiều công việc: quản trị danh tính, chuẩn hóa cấu hình, theo dõi hạn mức và tổng hợp chi phí.

**Organization Management** hỗ trợ quản lý các tenancy trong một organization: tạo hoặc mời child tenancy, quản lý subscription mapping và áp dụng governance rules. Đây là công cụ tổ chức quản trị nhiều tenancy, cần được kết hợp với landing zone trong từng tenancy. Xem [Organization Management Overview](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_management_overview.htm).

Bài học thuộc chương **Tổ chức tài nguyên và landing zone** của module Oracle Cloud Infrastructure. Sau bài này, người học có thể lựa chọn giữa compartment và tenancy, mô tả quan hệ parent–child, tổ chức quy trình onboarding và kiểm tra ba mặt độc lập: thành viên organization, nơi ghi nhận chi phí và trạng thái quản trị.

## 1. Mô hình parent tenancy, child tenancy và subscription

Trong Organization Management:

- **Parent tenancy** giữ vai trò quản lý organization và các subscription liên quan.
- **Child tenancy** tham gia organization qua việc được tạo mới hoặc nhận lời mời.
- **Subscription** cung cấp điều kiện tính phí và nguồn tiêu dùng tương ứng.
- **Subscription mapping** xác định subscription mà một tenancy sử dụng.

Một organization có thể có nhiều child tenancies và nhiều subscription. Parent có thể gán subscription cho các tenancy trong organization. Xem [Organization Management Overview](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_management_overview.htm).

Ví dụ thiết kế:

~~~text
Quan hệ tổ chức
==============

Parent tenancy: acmeplatform
├── Child tenancy: acmeorders
├── Child tenancy: acmeanalytics
└── Child tenancy: acmesandbox

Quan hệ subscription
====================

Subscription A  ← acmeplatform, acmeorders, acmesandbox
Subscription B  ← acmeanalytics
~~~

Hai phần của sơ đồ mô tả **hai quan hệ khác nhau**. Thêm acmeanalytics vào organization và chọn subscription cho nó là hai quyết định cần kiểm tra riêng.

Các tên trong bài chỉ minh họa. Không suy luận quyền, cấu hình mạng hoặc nghĩa vụ tài chính từ tên tenancy. Hồ sơ vận hành nên dùng OCID và thông tin subscription thực tế để định danh.

Child tenancy cũng không phải một compartment con nằm trong parent. Nó là một tenancy riêng tham gia một mô hình quản lý chung.

## 2. Khi nào dùng nhiều tenancy?

OCI khuyến nghị cân nhắc chi phí vận hành của mô hình nhiều tenancy. Mỗi tenancy có IAM, quản trị viên, service limits, VCN và cấu hình bảo mật riêng; nếu không cần mức cách ly đó, có thể dùng compartment. Xem [Planning Considerations](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_planning.htm).

Bảng dưới đây là cách đánh giá kiến trúc đề xuất:

| Nhu cầu | Một tenancy với compartment | Nhiều tenancy |
| --- | --- | --- |
| Các đội chia sẻ nền tảng IAM và vận hành | Thường đơn giản hơn | Cần giải thích lợi ích cách ly bổ sung |
| Phân chia ứng dụng hoặc môi trường thông thường | Có thể đáp ứng bằng thiết kế compartment và IAM | Không nên chọn chỉ vì có nhiều ứng dụng |
| Cần tách quản trị viên và cấu hình nền tảng | Cần đánh giá giới hạn của mô hình chung | Là phương án đáng xem xét |
| Tiếp nhận hệ thống đã ở tenancy riêng | Có thể cần dự án di chuyển nếu hợp nhất | Có thể đánh giá lời mời tham gia organization |
| Đội vận hành còn nhỏ | Ít cấu hình nền cần duy trì hơn | Cần năng lực quản lý nhiều bản landing zone |
| Tổng hợp chi phí nhiều đơn vị | Dùng compartment và tag theo quy ước | Dùng thêm tenancy và subscription làm chiều phân tích |

Ví dụ, tách dev và prod không tự động dẫn tới yêu cầu tạo hai tenancy. Nếu mục tiêu là phân quyền nhóm phát triển và giới hạn tài nguyên thử nghiệm, hãy đánh giá compartment trước.

Ngược lại, một đơn vị mới sáp nhập đã có tenancy, đội IAM và hệ thống cơ sở dữ liệu riêng có thể cần duy trì mức độc lập đó trong giai đoạn chuyển tiếp. Khi ấy, Organization Management cung cấp một phương án đưa quản lý chi phí và một số kiểm soát về trung tâm.

Việc chọn nhiều tenancy cũng không tự tạo khả năng khôi phục thảm họa. Khả năng phục hồi của ứng dụng còn phụ thuộc vị trí triển khai, dữ liệu sao lưu, kết nối và quy trình chuyển đổi.

## 3. Ranh giới quản trị cần làm rõ

Trong mô hình đề xuất của bài, chia trách nhiệm theo các vai trò:

| Nhóm phụ trách | Phạm vi trách nhiệm |
| --- | --- |
| Nhóm nền tảng ở parent | Danh mục tenancy, quy trình tạo hoặc mời, governance rules |
| Nhóm tài chính | Chọn subscription, đối soát chi phí, quản lý kỳ chuyển đổi |
| Quản trị viên child tenancy | IAM, cấu hình nền, tài nguyên và vận hành trong tenancy |
| Đội ứng dụng | VCN, Compute, lưu trữ, cơ sở dữ liệu và chất lượng dịch vụ |
| Nhóm bảo mật | Kiểm tra quyền, danh tính, nhật ký và ngoại lệ |

Đây là phân công của ví dụ, không phải các vai trò được OCI tự tạo.

Do IAM được quản lý riêng theo tenancy, không coi việc liên kết organization là bằng chứng rằng quản trị viên parent đã có quyền đọc bucket, đăng nhập máy chủ hoặc vận hành cơ sở dữ liệu trong child. Nếu đội nền tảng cần thao tác ở child, phải thiết kế và kiểm tra quyền truy cập tương ứng.

Tương tự, hợp nhất chi phí không tạo kết nối mạng giữa các VCN. Nếu order-api trong acmeorders cần đọc dữ liệu tại acmeanalytics, phải thiết kế cả kết nối, phân giải tên, kiểm soát mạng và quyền dịch vụ cần thiết.

Một bản ghi trong danh mục tenancy nên trả lời được:

~~~text
Tenancy nào?
Ai sở hữu?
Dùng subscription nào?
Ai có quyền quản trị?
Governance rules nào đã áp dụng thành công?
Landing zone nào đang được triển khai?
Ai chịu trách nhiệm khi phát sinh sự cố?
~~~

## 4. Điều kiện trước khi tạo hoặc mời tenancy

Trước khi triển khai mô hình, kiểm tra eligibility và hạn mức thực tế:

| Nội dung | Điều cần kiểm tra |
| --- | --- |
| Loại tài khoản | Free Tier/Trial cần chuyển sang trả phí trước khi tạo hoặc tham gia |
| Số child tenancies | Parent phải có đủ organization limits |
| Regions | Các region child đăng ký phải nằm trong tập parent đăng ký |
| Tạo child mới | Thao tác từ home region của parent |
| Mời tenancy có sẵn | Kiểm tra tài khoản trả phí, cùng realm và trạng thái standalone |

Điều kiện trả phí không đồng nghĩa đã được cấp đủ hạn mức. Xem [Child Tenancy Management](https://docs.oracle.com/en-us/iaas/Content/General/organization/child-tenancy-management.htm) và [Planning Considerations](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_planning.htm).

Không nhầm **home region** với tất cả region có thể triển khai tài nguyên. Hồ sơ onboarding nên ghi riêng home region, các region đã đăng ký và những region được tổ chức phê duyệt.

Ngoài điều kiện dịch vụ, đội triển khai cần thống nhất chủ sở hữu, tài khoản quản trị ban đầu, phương án truy cập khẩn cấp và subscription dự kiến. Các quyết định này nên có trước khi tạo một tenancy phục vụ sản xuất.

## 5. Tạo một child tenancy mới

Dùng luồng tạo mới khi cần một tenancy chưa có tài nguyên và muốn đưa nó vào organization ngay từ đầu.

Quy trình Console:

1. Đăng nhập parent và mở **Governance & Administration → Organization Management → Tenancies**.
2. Chọn **Create new tenancy**.
3. Nhập tên, home region và email quản trị viên.
4. Kiểm tra subscription; mặc định dùng subscription mặc định của organization, có thể chọn subscription đủ điều kiện khác.
5. Chọn governance rules cần gắn hoặc để cấu hình sau.
6. Xem lại thông tin, tạo tenancy và theo dõi hoàn tất.

Quản trị viên child nhận hướng dẫn kích hoạt, thiết lập mật khẩu và MFA. Xem [Creating a Child Tenancy](https://docs.oracle.com/en-us/iaas/Content/General/organization/child-tenancy-create.htm).

Ví dụ hồ sơ đề xuất trước khi tạo:

| Thuộc tính | Giá trị minh họa |
| --- | --- |
| Tên | acmesandbox |
| Mục đích | Thử nghiệm các bài thực hành OCI |
| Chủ sở hữu | Đội nền tảng |
| Người quản trị ban đầu | Tài khoản được tổ chức chỉ định |
| Subscription | Subscription A |
| Region được phép | Danh sách lab đã phê duyệt |
| Chính sách tài nguyên | Quota phù hợp với mục tiêu học tập |
| Điều kiện cho phép sử dụng | Hoàn tất baseline và cơ chế theo dõi chi phí |

Tenancy được tạo thành công chưa có nghĩa đã sẵn sàng cho workload. Nhóm nền tảng vẫn cần triển khai IAM, compartment, tag, cấu hình nhật ký và các thành phần mạng phù hợp.

Không nên xem tài khoản quản trị ban đầu là cơ chế truy cập hằng ngày cho toàn bộ đội. Thiết kế nhóm, danh tính tự động hóa và quyền theo công việc trong bước triển khai landing zone.

## 6. Mời một tenancy đang tồn tại

Dùng luồng mời khi cần giữ tenancy và tài nguyên hiện có, đồng thời đưa tenancy vào organization.

Từ parent, chọn **Invite tenancy**, nhập OCID tenancy đích cùng thông tin người nhận, kiểm tra lựa chọn governance và gửi lời mời. Ở tenancy đích, người có quyền mở lời mời, xác minh bên gửi và chấp nhận. Xem [Inviting a Tenancy to Join an Organization](https://docs.oracle.com/en-us/iaas/Content/General/organization/sender-invitation-create.htm) và [Accepting an Invitation](https://docs.oracle.com/en-us/iaas/Content/General/organization/recipient-invitation-accept.htm).

Cần chú ý ba điểm:

- Gửi lời mời chưa tạo ra quan hệ đã hoàn tất.
- Tenancy được mời tự động dùng default subscription khi gia nhập; nếu cần dùng subscription khác, phải kiểm tra mapping.
- Việc ghi nhận usage sang subscription mới có độ trễ xử lý.

Các hành vi trên được mô tả trong [luồng mời tenancy của OCI](https://docs.oracle.com/en-us/iaas/Content/General/organization/sender-invitation-create.htm).

Trước khi chấp nhận, nên có bản kiểm kê:

| Nhóm thông tin | Ví dụ cần ghi nhận |
| --- | --- |
| Tài nguyên quan trọng | Compute, database, bucket, volume, kết nối |
| Truy cập | Nhóm quản trị, tài khoản tự động hóa, quyền liên tenancy |
| Chi phí | Subscription hiện tại, subscription đích, kỳ đối soát |
| Governance | Namespace tag có sẵn, quota, region đã đăng ký |
| Vận hành | Sao lưu, cảnh báo, người trực, ngoại lệ đang áp dụng |

Việc gia nhập organization không phải một kế hoạch di chuyển ứng dụng. Với hệ thống đang phục vụ khách hàng, cần xác định thay đổi nào chỉ liên quan billing và thay đổi nào thực sự tác động đến cấu hình vận hành.

## 7. Subscription mapping và quản lý chi phí

### 7.1. Subscription mapping trả lời câu hỏi nào?

Mapping xác định subscription mà usage của tenancy được ghi nhận vào. Tenancy sử dụng rate card và điều kiện tương ứng; với Universal Credits Commitment, chi phí tiêu dùng từ credits của subscription. Remap làm tenancy ngừng dùng subscription trước và sử dụng subscription đích. Xem [Mapping Subscriptions to Tenancies](https://docs.oracle.com/en-us/iaas/Content/General/organization/subscription-mapping-create.htm).

Không coi mọi subscription đều có thể chia sẻ theo cùng cách. Tài liệu OCI phân biệt Universal Credits có thể chia sẻ với các loại SaaS hoặc Multicloud có giới hạn riêng. Xem [Planning Considerations](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_planning.htm).

Ví dụ quản lý nội bộ:

~~~text
acmeorders:
  Subscription dự kiến: A
  Chủ sở hữu chi phí: Đơn vị Orders
  CostCenter chuẩn: CC420

acmeanalytics:
  Subscription dự kiến: B
  Chủ sở hữu chi phí: Đơn vị Analytics
  CostCenter chuẩn: CC610
~~~

Đây là mô tả hồ sơ, không phải payload OCI API. Cần đối chiếu mapping thực tế bằng Console hoặc CLI.

Đổi mapping cũng không tự hoàn tất việc chuyển credits, thay đổi hợp đồng hoặc xử lý số dư. Những nội dung thương mại liên quan cần được đối soát với Oracle theo quy trình tương ứng. Xem [Inviting a Tenancy to Join an Organization](https://docs.oracle.com/en-us/iaas/Content/General/organization/sender-invitation-create.htm).

### 7.2. Tổng hợp ở parent, vận hành tại child

Parent có thể phân tích chi phí toàn organization; child xem chi phí của chính nó. Cost Analysis hỗ trợ chiều Tenant ID, Tenant Name và Subscription ID. Parent và child đều có thể tạo budget trong phạm vi được hỗ trợ; parent có thể đặt budget cho child. Dữ liệu trước và sau remap gắn với subscription tại từng thời điểm. Xem [Cost Reporting Integration](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_cost_reporting.htm).

Trong ví dụ, nhóm tài chính nên lưu mốc chuyển subscription của acmeanalytics và đối chiếu hai phần của kỳ báo cáo:

~~~text
Phần kỳ trước chuyển đổi → subscription cũ
Phần kỳ sau chuyển đổi   → subscription mới
~~~

Không lấy riêng subscription hiện tại rồi kết luận đó là toàn bộ chi phí của tenancy trong cả kỳ.

Một budget nên có chủ sở hữu và người nhận cảnh báo. Quy trình phản ứng có thể gồm kiểm tra tài nguyên mới, xem biến động usage và trao đổi với đội ứng dụng. Không dùng khái niệm budget như một lời bảo đảm tài nguyên sẽ tự dừng tại đúng một số tiền.

## 8. Governance rules: chuẩn chung cho nhiều tenancy

### 8.1. Các nhóm kiểm soát

Organization Management hỗ trợ ba nhóm governance rules:

| Nhóm rule | Mục đích |
| --- | --- |
| Allowed regions | Giới hạn region được phép đăng ký |
| Quota policies | Áp dụng quota tài nguyên hoặc hạn chế dịch vụ |
| Tags | Chia sẻ namespace và cấu hình tag default |

Khi rule được gắn, tài nguyên quản trị tương ứng được tạo và khóa ở tenancy đích. Người dùng child không tự sửa tài nguyên bị khóa đó. Xem [Adding Governance to Tenancies](https://docs.oracle.com/en-us/iaas/Content/General/organization/add-governance.htm).

Ví dụ baseline đề xuất:

- Sandbox có danh sách region phù hợp với hoạt động thử nghiệm.
- Quota được thiết kế theo tài nguyên thực sự cần cho lab.
- Namespace Governance chứa Environment, Service và OwnerTeam.
- Tài nguyên mới có metadata giúp tìm chủ sở hữu và phân tích chi phí.

Đây là thiết kế gợi ý. Cú pháp quota, dịch vụ được hỗ trợ và giá trị giới hạn phải được chọn theo workload thực tế; không dùng một quota mẫu cho mọi tenancy.

### 8.2. Thành viên organization khác với tham gia governance

Một tenancy có thể chia sẻ quản lý chi phí nhưng chưa tham gia organization governance. Cần kiểm tra trạng thái governance riêng. Với tenancy đang có sẵn, có thể thực hiện luồng opt-in hoặc yêu cầu child chấp thuận; sau khi tham gia, child không tự opt-out. Xem [Opting In Tenancies to Use Governance Rules](https://docs.oracle.com/en-us/iaas/Content/General/organization/add-governance-optinuserules.htm).

Vì vậy, danh sách quản trị nên có các cột độc lập:

~~~text
Tenancy OCID
Trạng thái thành viên
Subscription đang dùng
Trạng thái tham gia governance
Các rule được gắn
Kết quả áp dụng từng rule
~~~

Không dùng một ô “đã onboarding” để thay cho tất cả trạng thái trên.

### 8.3. Phạm vi gắn rule và hiệu lực thực tế

Rule có thể nhắm tới các tenancy được chọn hoặc toàn organization. Chế độ toàn organization áp dụng cho các tenancy hiện tại và tương lai tham gia governance. Khi gắn rule, cần theo dõi work request cho từng đích. Xem [Creating a Governance Rule and Attaching It to a Tenancy](https://docs.oracle.com/en-us/iaas/Content/General/organization/add-governance-createattachrule.htm).

Một thay đổi nhắm toàn organization có phạm vi rộng. Quy trình đề xuất là thử ở tenancy thử nghiệm, quan sát ảnh hưởng, xử lý xung đột và sau đó mới mở rộng.

Có hai giới hạn dễ hiểu sai:

- Allowed regions không tự gỡ region đã đăng ký ngoài danh sách; tenancy vẫn có thể triển khai tài nguyên trong region đã đăng ký đó.
- Sửa tài nguyên nguồn ở parent, chẳng hạn namespace tag, còn cần cập nhật governance rule để thay đổi được truyền sang child.

Xem [Adding Governance to Tenancies](https://docs.oracle.com/en-us/iaas/Content/General/organization/add-governance.htm).

Do đó, kiểm tra tuân thủ cần xem cả cấu hình rule lẫn trạng thái thực tế. Một tên rule như approved-regions chưa chứng minh mọi tài nguyên hiện tại đều nằm trong khu vực được phê duyệt.

## 9. IAM cho Organization Management

Các nhóm quản trị nên được cấp quyền theo nhiệm vụ. Ví dụ với identity domain Default:

~~~text
Allow group Default/OrgAdmins to manage organizations-family in tenancy
~~~

Nhóm chỉ cần chấp nhận lời mời tại tenancy nhận có thể dùng:

~~~text
Allow group Default/OrgInvitationAccepters to manage organizations-recipient-invitations in tenancy
~~~

Nhóm chỉ cần xem quan hệ liên kết:

~~~text
Allow group Default/OrgLinkViewers to read organizations-links in tenancy
~~~

Các mẫu dựa trên [Required IAM Policy](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_required_iam_policy.htm). Thay tên domain và nhóm cho phù hợp. Quyền xem links không bao gồm mọi quyền xem invitation hoặc dữ liệu billing.

Trong thiết kế thực tế, phân biệt:

- Người được phép tạo tenancy hoặc gửi lời mời.
- Người được phép chấp nhận ở tenancy đích.
- Người được phép thay subscription mapping.
- Người được phép thay governance rules.
- Người được xem chi phí nhưng không đổi cấu hình.

Không cấp nhóm ứng dụng quyền quản trị toàn bộ organizations-family chỉ để triển khai một Compute instance. Quyền với Organization Management và quyền với tài nguyên ứng dụng phục vụ những nhiệm vụ khác nhau.

## 10. Kiểm tra subscription mapping bằng OCI CLI

Ví dụ sau là **Bash** trong một môi trường đã cấu hình OCI CLI. Profile cần trỏ tới parent và principal có quyền đọc thông tin liên quan.

~~~bash
export PARENT_TENANCY_OCID='ocid1.tenancy.oc1..replace_parent'
export SUBSCRIPTION_OCID='replace_with_actual_subscription_ocid'

oci organizations subscription-mapping list \
  --profile ORG_PARENT \
  --compartment-id "$PARENT_TENANCY_OCID" \
  --subscription-id "$SUBSCRIPTION_OCID" \
  --all
~~~

Trong lệnh này:

- compartment-id dùng root compartment của parent, tức OCID tenancy.
- subscription-id nhận **OCID của subscription**, không phải tên hiển thị.
- all lấy tất cả trang kết quả.

Xem [OCI CLI: subscription-mapping list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/organizations/subscription-mapping/list.html).

Sau khi đọc kết quả, đối chiếu với danh mục tenancy đã phê duyệt. Nếu organization có nhiều subscription, cần kiểm tra từng subscription liên quan; một lần gọi không thay thế việc đối soát toàn bộ organization.

Khi tự động hóa, nên tách tác vụ thu thập inventory khỏi tác vụ thay mapping. Bản ghi đề xuất thay đổi nên thể hiện tenancy, subscription hiện tại, subscription đích và lý do trước khi quy trình được phép cập nhật.

## 11. Kết hợp Organization Management với landing zone từng tenancy

Organization Management hỗ trợ quản trị ở cấp tổ chức; baseline trong mỗi tenancy vẫn cần một quy trình riêng.

Bảng dưới là ma trận thiết kế cho ví dụ Acme:

| Thành phần | Chuẩn chung của tổ chức | Cấu hình theo từng child |
| --- | --- | --- |
| Danh tính | Quy tắc nhóm, MFA, quyền theo nhiệm vụ | Cấu hình IAM và kiểm tra đăng nhập |
| Compartment | Quy ước tách ứng dụng và môi trường | OCID, cấu trúc và người sở hữu |
| Tags | Namespace và định nghĩa metadata | Value của Service, OwnerTeam, CostCenter |
| Mạng | Nguyên tắc phân đoạn và quản lý địa chỉ | VCN, subnet, kết nối và quy tắc truy cập |
| Giám sát | Tiêu chí cảnh báo và lưu nhật ký | Nguồn log, alarm, người nhận |
| Sao lưu | Mục tiêu khôi phục theo loại workload | Chính sách và kết quả kiểm tra khôi phục |
| Chi phí | Quy trình đối soát và cảnh báo | Budget, trách nhiệm xử lý biến động |
| Tự động hóa | Mẫu triển khai có phiên bản | Tham số, danh tính chạy và quyền cần thiết |

Không phải mọi dòng trong bảng đều được governance rules tự cấu hình. Chẳng hạn, triển khai VCN, kiểm tra khôi phục database hoặc thiết lập kênh nhận cảnh báo cần công cụ và quy trình phù hợp.

Đối với IaC, có thể quản lý một bộ mẫu landing zone chung rồi truyền tham số cho từng tenancy. Hồ sơ mỗi lần triển khai nên ghi nhận phiên bản, đích triển khai và kết quả. Nếu tạo child mới nhưng quên chạy baseline, khoảng trống vận hành vẫn tồn tại dù organization đã nhận diện tenancy.

Đối với quyền tự động hóa, tránh dùng một tài khoản quản trị dùng chung cho mọi tenancy. Thiết kế danh tính và phạm vi thao tác để một lỗi trong sandbox không tự mở rộng thành thay đổi trên toàn bộ môi trường sản xuất.

## 12. Quy trình onboarding có thể vận hành

Một luồng đề xuất cho acmeanalytics:

~~~text
Yêu cầu tenancy
  ↓
Đánh giá nhu cầu cách ly và người sở hữu
  ↓
Kiểm tra eligibility, limits, region và subscription
  ↓
Tạo mới hoặc mời tenancy hiện có
  ↓
Xác minh quan hệ organization và subscription mapping
  ↓
Xác minh opt-in governance và áp dụng rule
  ↓
Triển khai baseline trong child
  ↓
Kiểm tra truy cập, giám sát, chi phí và khôi phục
  ↓
Bàn giao cho đội vận hành
~~~

Tại bước bàn giao, cần có bằng chứng cụ thể:

| Nội dung | Bằng chứng đề xuất |
| --- | --- |
| Thành viên organization | Tenancy OCID và quan hệ parent–child đúng |
| Subscription | Mapping thực tế khớp lựa chọn đã phê duyệt |
| Governance | Rule cần thiết được gắn thành công ở tenancy đích |
| Quyền truy cập | Nhóm đúng thực hiện được công việc được giao |
| Mạng | Kết nối cần thiết hoạt động, đường truy cập thừa được loại bỏ |
| Vận hành | Log, cảnh báo và người nhận được xác nhận |
| Dữ liệu | Phương án sao lưu, khôi phục phù hợp workload |
| Chi phí | Có người sở hữu budget và lịch đối soát |

Quy trình này có thể áp dụng cho môi trường lab bằng dữ liệu giả lập trước. Không cần tạo nhiều tenancy sản xuất chỉ để kiểm tra khả năng thiết kế hồ sơ và phân công trách nhiệm.

Với tenancy đã có hệ thống chạy, dùng bản kế hoạch thay đổi nêu rõ điểm bắt đầu, kiểm tra sau chuyển đổi và cách xử lý nếu mapping hoặc governance chưa đạt trạng thái mong muốn.

## 13. Remove, transfer và xóa tenancy là các việc khác nhau

Với **invited child tenancy**, OCI có luồng remove khỏi organization. Cần xử lý governance và mapping về subscription riêng phù hợp trước khi gỡ liên kết; cũng phải kiểm tra các subscription đang phụ thuộc. Parent sẽ mất khả năng quản lý chi phí tương lai và mapping của tenancy đã rời organization. Xem [Deleting Links to Invited Child Tenancies](https://docs.oracle.com/en-us/iaas/Content/General/organization/link-delete.htm).

Với **created child tenancy**, có luồng phê duyệt chuyển sang organization khác qua CLI/API, sau đó hoàn tất lời mời và mapping ở tổ chức đích. Xem [Approving a Created Child Tenancy for Transfer](https://docs.oracle.com/en-us/iaas/Content/General/organization/approve-createdchildtenancy-for-transfer.htm).

Không dùng thao tác xóa tenancy để thay cho việc chuyển đơn vị quản lý hoặc đổi nguồn tiêu dùng. Nếu chỉ cần chuyển sang subscription khác trong cùng organization, đánh giá subscription mapping trước.

Hồ sơ offboarding nên bao gồm:

1. Chủ sở hữu sau chuyển đổi và nguồn thanh toán tiếp theo.
2. Các rule hoặc quy trình trung tâm cần thay thế.
3. Danh tính tự động hóa và kết nối liên quan.
4. Bản đối soát chi phí tại mốc chuyển.
5. Xác nhận hệ thống vẫn có giám sát, sao lưu và người trực.

Không coi việc bỏ liên kết tổ chức là cách thu hồi mọi quyền hoặc mọi kết nối từng cấu hình. Các quan hệ truy cập và phụ thuộc ứng dụng cần được kiểm kê riêng.

## 14. Xử lý lỗi và sai lệch

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Không tạo được child | Loại tài khoản, organization limits, quyền và home region |
| Không chấp nhận được lời mời | Đúng tenancy nhận, quyền invitation và điều kiện tham gia |
| Child hiện trong organization nhưng chưa có rule | Trạng thái governance và danh sách rule được gắn |
| Rule tạo thành công nhưng chưa áp dụng | Work request tại từng tenancy đích |
| Chi phí lệch sau remap | Subscription trước/sau chuyển đổi và kỳ truy vấn |
| Tag rule không gắn được | Namespace cùng tên đã tồn tại ở đích |
| Quota rule không gắn được | Cú pháp, tên quota và thông báo lỗi của work request |

OCI nêu các tình huống như trùng namespace hoặc quota có cú pháp sai vẫn có thể dẫn đến rule được tạo nhưng attach thất bại. Cần đọc logs và error messages của work request để xác định nguyên nhân. Xem [Troubleshooting Organization Management](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization-troubleshooting.htm).

Với rule áp dụng cho nhiều tenancy, lưu kết quả riêng cho từng đích. Nếu acmeorders đã thành công nhưng acmeanalytics thất bại, không đánh dấu toàn bộ đợt triển khai đã hoàn tất.

Không xử lý mọi lỗi bằng cách cấp quyền quản trị rộng hơn. Trước hết xác định đang sai quyền, sai phạm vi, thiếu điều kiện dịch vụ hay xung đột cấu hình hiện có.

## 15. Tiêu chí hoàn thành mô hình nhiều tenancy

Một thiết kế đủ để bàn giao vận hành nên có:

- Lý do dùng nhiều tenancy thay cho chỉ dùng compartment.
- Danh mục OCID, người sở hữu và nhiệm vụ của từng tenancy.
- Subscription mapping đã được kiểm tra thực tế.
- Mô hình IAM của parent và từng child rõ ràng.
- Trạng thái tham gia governance và kết quả áp dụng rule theo từng tenancy.
- Baseline cho mạng, giám sát, dữ liệu và tự động hóa.
- Quy trình đối soát chi phí sau các thay đổi subscription.
- Kế hoạch xử lý ngoại lệ, transfer và offboarding.

Trong ví dụ Acme, kết quả mong đợi là nhóm trung tâm theo dõi được tenancy, nguồn tiêu dùng và các kiểm soát chung, còn mỗi đội ứng dụng vẫn có trách nhiệm vận hành rõ ràng trong tenancy của mình. Khi mở rộng thêm một tenancy, quy trình phải tạo ra đủ cấu hình và bằng chứng bàn giao để tenancy đó có thể vận hành ổn định.
