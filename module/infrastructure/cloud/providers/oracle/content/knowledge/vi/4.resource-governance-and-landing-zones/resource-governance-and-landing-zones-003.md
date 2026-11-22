# Defined tags, free-form tags và tag defaults

Trong một landing zone Oracle Cloud Infrastructure (OCI), compartment tổ chức phạm vi quản trị, còn tag bổ sung thông tin để nhận biết tài nguyên thuộc ứng dụng, môi trường, đội vận hành và trung tâm chi phí nào. Khi một ứng dụng sử dụng đồng thời VCN, Compute, Block Volume, Object Storage và cơ sở dữ liệu Oracle, bộ tag nhất quán giúp kết nối các thành phần đó theo góc nhìn nghiệp vụ.

Bài học thuộc chương **Tổ chức tài nguyên và landing zone** của module Oracle Cloud Infrastructure. Mục tiêu là chọn đúng loại tag, thiết kế bộ metadata dùng chung, áp dụng tag defaults theo compartment và kiểm soát quyền thay đổi tag để phục vụ vận hành, tự động hóa và phân bổ chi phí.

## 1. Tag giải quyết bài toán gì?

Giả sử đội Orders triển khai dịch vụ **order-api** trên OCI:

- VCN và các thành phần mạng phục vụ kết nối ứng dụng.
- Compute chạy ứng dụng; volume lưu dữ liệu xử lý.
- Bucket lưu báo cáo.
- Một dịch vụ cơ sở dữ liệu Oracle lưu dữ liệu nghiệp vụ.
- Một số tài nguyên dùng cho môi trường phát triển, một số phục vụ sản xuất.

Tên như vm-02 hoặc data-volume-01 thường chưa đủ để xác định ai chịu trách nhiệm, chi phí thuộc đội nào hoặc tài nguyên có được phép dừng cuối tuần hay không. Một hợp đồng metadata có thể bổ sung các thông tin đó:

| Thuộc tính | Giá trị ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| Dịch vụ | order-api | Tài nguyên phục vụ ứng dụng nào? |
| Môi trường | dev | Đây là tài nguyên phát triển hay sản xuất? |
| Đội phụ trách | orders-platform | Ai xử lý khi có sự cố? |
| Trung tâm chi phí | CC420 | Chi phí được phân bổ cho đơn vị nào? |
| Lịch vận hành | office-hours | Công cụ tự động hóa nên chọn tài nguyên nào? |

Đây là **quy ước thiết kế của ví dụ**, không phải bộ tag Oracle bắt buộc mọi tenancy phải có. Tổ chức nên chọn một tập nhỏ đủ dùng, định nghĩa rõ ý nghĩa và chỉ định người sở hữu từng thuộc tính.

Tag không tự triển khai giám sát hoặc tự động hóa. Muốn dừng Compute theo lịch, vẫn cần một quy trình đọc tag, kiểm tra điều kiện và gọi API với quyền thích hợp. Muốn đáp ứng tính sẵn sàng, vẫn cần kiến trúc, sao lưu và phương án khôi phục tương ứng.

## 2. Phân biệt ba khái niệm

**Free-form tag** là cặp key–value trực tiếp trên tài nguyên. **Defined tag** dùng namespace và key đã khai báo trong tenancy. **Tag default** là cấu hình áp dụng defined tag khi tạo tài nguyên trong phạm vi compartment. Tag default không phải một loại tag thứ ba được lưu trên tài nguyên; kết quả của nó là defined tag. Xem [Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Ví dụ cùng mô tả môi trường:

~~~json
{
  "freeformTags": {
    "Environment": "dev"
  },
  "definedTags": {
    "Governance": {
      "Environment": "dev"
    }
  }
}
~~~

Hai thuộc tính trên tồn tại độc lập. Environment trong free-form tags không trở thành Governance.Environment; việc sửa một bên không tự sửa bên còn lại. Trong quy ước của bài, **defined tag là nguồn dữ liệu chuẩn**, free-form tag phục vụ thông tin phụ trợ.

| Nhu cầu thiết kế | Cơ chế nên chọn |
| --- | --- |
| Gắn mã thử nghiệm hoặc ticket ngắn hạn | Free-form tag |
| Chuẩn hóa môi trường, dịch vụ, chủ sở hữu | Defined tag |
| Giới hạn môi trường trong dev, test, prod | Defined tag với danh sách giá trị |
| Điền môi trường theo compartment lúc tạo | Tag default |
| Yêu cầu người triển khai chọn giá trị hợp lệ | Defined tag có danh sách giá trị kết hợp default yêu cầu giá trị |

## 3. Free-form tags: linh hoạt nhưng dễ phân mảnh

Free-form tag không có namespace và không cần tạo key definition trước. Ví dụ:

~~~json
{
  "LabRun": "landing-zone-01",
  "Ticket": "CHG1042"
}
~~~

Key và value của free-form tags phân biệt chữ hoa, chữ thường. Owner và owner là hai key khác nhau; Prod và prod là hai value khác nhau. Thêm hoặc sửa tag cần quyền cập nhật tài nguyên tương ứng. Free-form tags không dùng được trong IAM policy, tag defaults, danh sách giá trị định sẵn hoặc tag variables. Xem [Understanding Free-form Tags](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingfreeformtags.htm).

Trong ví dụ Orders, Ticket=CHG1042 giúp liên hệ tài nguyên thử nghiệm với yêu cầu thay đổi. Tuy nhiên, dùng free-form tag cho thông tin chi phí dễ dẫn đến nhiều biến thể:

~~~text
CostCenter=CC420
costcenter=cc420
CostCentre=CC420
~~~

Đội tài chính phải chuẩn hóa các biến thể trước khi tổng hợp. Chi phí bảo trì tăng khi nhiều đội dùng các công cụ triển khai khác nhau.

Một quy tắc thực tế là chỉ dùng free-form tags cho thuộc tính có phạm vi hẹp, vòng đời ngắn và không quyết định cấp quyền. Khi một thuộc tính được nhiều đội sử dụng, hãy xem xét đưa nó vào schema defined tags.

## 4. Defined tags: namespace, key definition và value

Một defined tag có dạng:

~~~text
Governance.Environment = dev

Namespace: Governance
Key:       Environment
Value:     dev
~~~

Namespace nhóm các key liên quan. Key definition khai báo key được phép dùng; giá trị cụ thể nằm trên từng tài nguyên. Tên namespace và defined key không phân biệt hoa thường, nhưng value có phân biệt. Namespace cũng là phạm vi phân quyền sử dụng các key bên trong. Xem [Tags and Tag Namespace Concepts](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagsandtagnamespaces.htm) và [Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Bộ schema đề xuất cho landing zone trong bài:

| Namespace | Key | Giá trị ví dụ | Cách quản lý đề xuất |
| --- | --- | --- | --- |
| Governance | Environment | dev, test, prod | Danh sách định sẵn |
| Governance | Service | order-api | Mã trong danh mục dịch vụ |
| Governance | OwnerTeam | orders-platform | Mã đội trong danh bạ vận hành |
| FinOps | CostCenter | CC420 | Nhóm tài chính quản lý |
| Automation | Schedule | office-hours, always-on | Danh sách định sẵn |
| Automation | ExpiresOn | 2026-12-31 | Quy ước ngày do pipeline kiểm tra |

Bảng này thể hiện ba quyết định thiết kế:

1. OwnerTeam dùng mã đội để trách nhiệm không phụ thuộc một cá nhân.
2. CostCenter thuộc namespace riêng vì quyền thay đổi dữ liệu tài chính có thể khác quyền khai báo ứng dụng.
3. ExpiresOn là chuỗi theo quy ước. Tên key không khiến OCI tự xác thực ngày hoặc tự xóa tài nguyên.

Không đưa mật khẩu, token, khóa riêng hoặc thông tin cá nhân nhạy cảm vào tag. Người có quyền xem tài nguyên có thể thấy metadata liên quan. Oracle khuyến nghị tránh thông tin mật trong tag và mô tả tài nguyên. Xem [Resource Tags](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/resourcetags.htm).

### 4.1. Defined key chưa đủ để chuẩn hóa value

Nếu Environment nhận chuỗi tùy ý, người dùng vẫn có thể nhập production, PROD hoặc prd. Muốn chuẩn hóa value, cần cấu hình danh sách giá trị được phép.

Với danh sách dev, test, prod, yêu cầu gắn production không hợp lệ. Danh sách giới hạn lựa chọn khi áp dụng tag; nó không tự buộc mọi tài nguyên phải có key đó. Có thể kết hợp với tag default yêu cầu giá trị. Xem [Using Predefined Values](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/usingpredefinedvalues.htm).

Trong danh mục Orders, chỉ thêm staging sau khi thống nhất ý nghĩa và tác động đến báo cáo. Nếu một đội gọi kiểm thử là test, đội khác gọi là qa, hãy chọn một chuẩn trước khi mở rộng danh sách.

### 4.2. Ba lớp kiểm soát metadata

Khi thiết kế bộ tag, phân biệt:

- **Schema:** đã có key Environment trong namespace Governance chưa?
- **Miền giá trị:** những value nào được chấp nhận?
- **Sự hiện diện:** quy trình nào bảo đảm tài nguyên phải có tag?

Việc tạo key OwnerTeam không chứng minh người triển khai đã cung cấp đội phụ trách. Điền unknown cho mọi tài nguyên có thể làm báo cáo đầy đủ về hình thức nhưng vẫn không tìm được người xử lý sự cố.

## 5. Tag defaults: metadata tại thời điểm tạo

Tag defaults chỉ dùng defined tags và có hiệu lực với tài nguyên mới trong compartment cùng các compartment con. Chúng không tự gắn hồi tố; sửa hoặc xóa default không sửa hoặc xóa những tag đã áp dụng.

Có thể đặt sẵn default value hoặc yêu cầu giá trị khi tạo. Người có đủ quyền có thể ghi đè default và sửa tag sau đó. Vì vậy, default không tạo tính bất biến. Xem [Managing Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).

### 5.1. Bố trí default theo ý nghĩa compartment

Đề xuất cây compartment:

~~~text
Tenancy
├── WorkloadTagCatalog
│   ├── namespace Governance
│   └── namespace Automation
├── FinanceTagCatalog
│   └── namespace FinOps
└── Orders
    ├── OrdersDev
    └── OrdersProd
~~~

Các dòng namespace mô tả đối tượng được quản lý trong compartment, không phải compartment con.

Thiết kế quy ước cho ví dụ:

- Tại Orders: default FinOps.CostCenter=CC420.
- Tại OrdersDev: default Governance.Environment=dev.
- Tại OrdersProd: default Governance.Environment=prod.
- Governance.Service do pipeline ứng dụng cung cấp.
- Governance.OwnerTeam lấy từ danh mục đội được phê duyệt.

VCN mới phục vụ OrdersDev được kỳ vọng có cả thông tin chi phí của Orders và thông tin môi trường của OrdersDev. Tránh rải nhiều default cho cùng key ở nhiều cấp khi không cần thiết; thiết kế dễ đọc giúp các đội quản trị kiểm soát thay đổi.

Một tài nguyên mang Environment=prod chưa chứng minh nó ở đúng compartment, có đúng quyền IAM hoặc đạt yêu cầu sẵn sàng. Quy trình triển khai nên đối chiếu cả OCID compartment lẫn bộ tag.

### 5.2. Khi nào điền sẵn, khi nào yêu cầu giá trị?

Trong compartment dành riêng cho phát triển, Environment=dev suy ra được từ vị trí triển khai. Điền sẵn giúp giảm thao tác lặp.

Trong compartment chứa nhiều ứng dụng, Service cần được chọn theo ứng dụng đang triển khai. Một default yêu cầu giá trị kết hợp danh sách dịch vụ hợp lệ phù hợp hơn việc điền shared-service cho tất cả. OCI cho phép kết hợp predefined values với cơ chế yêu cầu giá trị. Xem [Using Predefined Values](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/usingpredefinedvalues.htm).

Pipeline nên kiểm tra metadata trước khi gọi API, chẳng hạn báo: “Thiếu Governance.OwnerTeam cho dịch vụ order-api”. Thông báo cụ thể giúp người triển khai sửa cấu hình ngay từ đầu.

### 5.3. Di chuyển tài nguyên cần đối soát metadata

Khi chuyển tài nguyên từ OrdersDev sang OrdersProd, đưa việc đối soát tag vào quy trình thay đổi. Không dùng thao tác move như một cơ chế tự sửa toàn bộ metadata.

Danh sách cần đối soát:

1. Compartment đích và quyền truy cập.
2. Environment, OwnerTeam, CostCenter hiện có.
3. Lịch tự động hóa đang đọc các tag đó.
4. Báo cáo và cấu hình bên ngoài tham chiếu tài nguyên.

Máy chủ sản xuất còn mang Automation.Schedule=office-hours có thể bị một công cụ nội bộ chọn nhầm. Cần xem cả trạng thái thực tế và metadata trước khi cho phép tự động hóa tác động.

## 6. Tag variables và metadata nguồn gốc

Tag variables cho phép OCI thay biểu thức bằng dữ liệu khi áp dụng defined tag:

| Biểu thức | Ý nghĩa |
| --- | --- |
| ${iam.principal.name} | Tên principal áp dụng tag |
| ${iam.principal.type} | Loại principal áp dụng tag |
| ${oci.datetime} | Thời điểm áp dụng tag |

Có thể dùng biến trong defined tags hoặc tag defaults; không dùng trong free-form tags hoặc danh sách predefined values. Giá trị được phân giải lúc áp dụng, không liên tục thay đổi theo đồng hồ. Xem [Using Tag Variables](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/usingtagvariables.htm).

Ví dụ đề xuất:

~~~text
Governance.TaggedBy = ${iam.principal.name}
Governance.TaggedAt = ${oci.datetime}
~~~

Cần tạo hai key tương ứng trước khi dùng. Nếu pipeline chạy bằng principal tự động hóa, TaggedBy nhận diện principal đó; nó không tự xác định người phê duyệt bản triển khai.

Một số tenancy có sẵn namespace Oracle-Tags cùng defaults CreatedBy và CreatedOn. Quản trị viên có thể thay đổi hoặc xóa chúng, nên kiểm tra cấu hình thực tế trước khi phụ thuộc vào hai tag này. Xem [Understanding Automatic Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingautomaticdefaulttags.htm).

Tag nguồn gốc hỗ trợ tra cứu, nhưng điều tra thay đổi vẫn nên đối chiếu OCI Audit và hồ sơ triển khai. Người có quyền có thể cập nhật tag, nên một value riêng lẻ chưa đủ chứng minh lịch sử.

## 7. Phân quyền: quản lý schema khác với gắn tag

Bộ phân quyền nên thể hiện ít nhất ba trách nhiệm:

| Vai trò | Trách nhiệm |
| --- | --- |
| Quản trị danh mục tag | Tạo namespace, key và danh sách giá trị |
| Quản trị landing zone | Cấu hình tag defaults tại compartment |
| Đội triển khai | Tạo tài nguyên, cung cấp metadata được phép |

Để áp dụng hoặc sửa defined tag, người dùng cần quyền thích hợp trên tài nguyên và quyền dùng namespace. Trong Console, quyền inspect namespace ở tenancy giúp hiển thị danh mục. Xem [Required Permissions for Working with Defined Tags](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagsandtagnamespaces.htm).

Ví dụ policy cho nhóm triển khai trong identity domain Default:

~~~text
Allow group Default/AppDeployers to inspect tag-namespaces in tenancy
Allow group Default/AppDeployers to use tag-namespaces in compartment WorkloadTagCatalog
~~~

Hai câu trên chỉ cấp quyền liên quan đến tag. Quyền tạo, đọc hoặc cập nhật VCN, Compute và các dịch vụ khác cần được cấp theo công việc. Thay domain, nhóm và compartment bằng đối tượng thực tế.

Trong thiết kế này, Governance và Automation nằm trong WorkloadTagCatalog. FinOps nằm trong FinanceTagCatalog, nên hai câu trên không cấp quyền dùng namespace tài chính. Cần kiểm tra các policy khác vì principal có thể nhận quyền từ nhiều nhóm.

Ví dụ quyền cho nhóm cấu hình default:

~~~text
Allow group Default/TagDefaultAdmins to inspect tag-namespaces in tenancy
Allow group Default/TagDefaultAdmins to use tag-namespaces in compartment WorkloadTagCatalog
Allow group Default/TagDefaultAdmins to use tag-namespaces in compartment FinanceTagCatalog
Allow group Default/TagDefaultAdmins to manage tag-defaults in compartment Orders
~~~

Mẫu kết hợp quyền quản lý default tại nơi áp dụng với quyền dùng namespace tại nơi quản lý schema, theo [Required Permissions for Working with Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).

Một lỗi thiết kế là dùng tag để quyết định quyền nhưng cũng cấp cho cùng người quyền sửa tag đó. Nếu một cơ chế coi OwnerTeam=finance là điều kiện được thao tác, cần xét ai có thể đổi OwnerTeam. Mọi luồng dùng tag làm đầu vào phân quyền phải đánh giá cả quyền thay đổi metadata.

## 8. Thực hành với OCI CLI

Các lệnh sau minh họa đường đi từ schema đến tài nguyên. Đây là **cú pháp Bash**, dùng trong phiên Bash đã cấu hình OCI CLI. Thực hiện trong compartment lab với quyền phù hợp. Bài thực hành tạo VCN để quan sát metadata, chưa triển khai Compute hoặc cơ sở dữ liệu.

Giả định:

- Có compartment quản lý danh mục tag và compartment lab tương đương OrdersDev.
- Principal có quyền tạo namespace, key, default và VCN tại các phạm vi tương ứng.
- Namespace Governance chưa tồn tại; nếu đã có, dùng namespace được giao thay vì tạo trùng.
- Nếu tenancy có yêu cầu tag khác, cung cấp đủ metadata đó khi tạo VCN.

### 8.1. Khai báo phạm vi và tạo namespace

Thay giá trị giữ chỗ bằng OCID thật:

~~~bash
export TAG_CATALOG_OCID='ocid1.compartment.oc1..replace_tag_catalog'
export APP_DEV_OCID='ocid1.compartment.oc1..replace_orders_dev'

NAMESPACE_OCID=$(oci iam tag-namespace create \
  --compartment-id "$TAG_CATALOG_OCID" \
  --name Governance \
  --description 'Metadata quan tri workload trong bai lab' \
  --query 'data.id' \
  --raw-output)
~~~

TAG_CATALOG_OCID là nơi quản lý namespace. APP_DEV_OCID là nơi tạo tài nguyên và đặt default. Hai OCID có vai trò khác nhau. Xem [OCI CLI: tag-namespace create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/tag-namespace/create.html).

### 8.2. Tạo các key definition

Tạo Environment với danh sách hợp lệ và lấy OCID của **key definition**:

~~~bash
ENVIRONMENT_KEY_OCID=$(oci iam tag create \
  --tag-namespace-id "$NAMESPACE_OCID" \
  --name Environment \
  --description 'Moi truong cua workload' \
  --validator '{"validatorType":"ENUM","values":["dev","test","prod"]}' \
  --query 'data.id' \
  --raw-output)
~~~

Tạo hai key nhận chuỗi do người triển khai cung cấp:

~~~bash
for TAG_KEY in Service OwnerTeam; do
  oci iam tag create \
    --tag-namespace-id "$NAMESPACE_OCID" \
    --name "$TAG_KEY" \
    --description "Metadata workload: $TAG_KEY"
done
~~~

Dùng chuỗi cho Service và OwnerTeam giúp ví dụ nhỏ gọn. Trong landing zone thực tế, có thể cấu hình danh sách mã được phép hoặc xác thực với danh mục tổ chức. Xem [OCI CLI: tag create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/tag/create.html).

### 8.3. Tạo default cho Environment

~~~bash
ENVIRONMENT_DEFAULT_OCID=$(oci iam tag-default create \
  --compartment-id "$APP_DEV_OCID" \
  --tag-definition-id "$ENVIRONMENT_KEY_OCID" \
  --value dev \
  --is-required false \
  --query 'data.id' \
  --raw-output)
~~~

Tham số tag-definition-id nhận OCID của key Environment, không nhận OCID namespace. Trong ví dụ, is-required=false chọn cách điền giá trị dev. Với chế độ yêu cầu giá trị, thao tác tạo tài nguyên bị chặn nếu không có giá trị được cung cấp. Xem [OCI CLI: tag-default create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/tag-default/create.html).

### 8.4. Tạo VCN có cả hai loại tag

~~~bash
VCN_OCID=$(oci network vcn create \
  --compartment-id "$APP_DEV_OCID" \
  --display-name orders-dev-tag-lab \
  --cidr-blocks '["10.42.0.0/16"]' \
  --defined-tags '{"Governance":{"Service":"order-api","OwnerTeam":"orders-platform"}}' \
  --freeform-tags '{"LabRun":"landing-zone-01","Ticket":"CHG1042"}' \
  --query 'data.id' \
  --raw-output)
~~~

Lệnh cố ý không truyền Governance.Environment để quan sát default. CIDR chỉ là ví dụ; chọn dải phù hợp kế hoạch mạng. Tham số cidr-blocks nhận mảng JSON. Xem [OCI CLI: VCN create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/vcn/create.html).

Đọc kết quả:

~~~bash
oci network vcn get \
  --vcn-id "$VCN_OCID" \
  --query 'data."defined-tags"'

oci network vcn get \
  --vcn-id "$VCN_OCID" \
  --query 'data."freeform-tags"'
~~~

Lệnh get nhận OCID VCN và đọc trạng thái sau khi tạo. Xem [OCI CLI: VCN get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/vcn/get.html).

Kết quả defined tags mong đợi tối thiểu:

~~~json
{
  "Governance": {
    "Environment": "dev",
    "Service": "order-api",
    "OwnerTeam": "orders-platform"
  }
}
~~~

Có thể có thêm tag do các default khác trong tenancy. Phần free-form tags cần chứa LabRun và Ticket đã truyền.

### 8.5. Quan sát default và xác thực value

Trong lab, tạo thêm một yêu cầu với Environment=production. Do enum chỉ có dev, test, prod, yêu cầu gắn giá trị này phải bị từ chối.

Tiếp theo, dùng giá trị hợp lệ nhưng khác mặc định, chẳng hạn test, với principal có quyền dùng namespace. Ghi nhận tag thực tế và đối chiếu quy ước compartment. Mục đích là nhận ra: danh sách hợp lệ cho toàn tenancy có thể rộng hơn những giá trị phù hợp tại một compartment.

Nếu OrdersDev phải luôn có môi trường dev, thiết kế cần xét quyền ghi đè, phạm vi namespace và kiểm tra pipeline. Việc đặt default dev chưa đủ diễn đạt toàn bộ yêu cầu đó.

Sau thực hành, dọn tài nguyên lab theo quy trình tenancy. Trước khi gỡ key hoặc namespace dùng chung, xác định chúng có đang được các default hoặc tài nguyên khác sử dụng hay không.

## 9. Dùng tag cho chi phí và vận hành

### 9.1. Phân bổ chi phí

Trong ví dụ, FinOps.CostCenter trả lời “đơn vị nào chịu chi phí”, còn Governance.Service trả lời “ứng dụng nào sử dụng tài nguyên”. Kết hợp chúng giúp phân biệt hạ tầng dùng chung với tài nguyên riêng của order-api.

Không nên mặc định chỉ tag được bật cost-tracking mới xuất hiện trong Cost Analysis hoặc Cost and Usage Reports. Tài liệu OCI cho biết không cần đánh dấu cost-tracking để tag được đưa vào các công cụ đó. Xem [Overview of Tagging — Cost Tracking](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Khi nghiệm thu, chọn nhóm tài nguyên đại diện và đối soát dữ liệu thực tế trong công cụ chi phí. Đặt rõ kỳ báo cáo, phạm vi compartment và quy tắc chia chi phí dùng chung. Không giả định rằng thêm tag hôm nay tự phân loại lại toàn bộ chi phí lịch sử.

Ví dụ quy tắc nội bộ:

~~~text
Chi phí trực tiếp của order-api
  = tổng chi phí tài nguyên có Service=order-api theo kỳ báo cáo

Chi phí dùng chung phân bổ cho Orders
  = tổng chi phí nhóm shared trong kỳ × tỷ lệ đã thống nhất
~~~

Tỷ lệ phân bổ là quyết định nghiệp vụ; tag cung cấp một phần dữ liệu đầu vào. Gắn CostCenter cũng không tự đặt ngân sách, giới hạn chi tiêu hoặc ngừng tài nguyên khi vượt mức.

### 9.2. Giám sát trách nhiệm và tự động hóa

Đội vận hành có thể xây dựng danh mục Service → OwnerTeam → kênh xử lý. Khi có cảnh báo, công cụ tra cứu metadata để tìm đội liên quan. Cần xác thực mã đội tồn tại và có người nhận việc; chỉ có key OwnerTeam chưa bảo đảm luồng xử lý hoạt động.

Với công cụ dừng tài nguyên phát triển, nên kết hợp nhiều điều kiện:

~~~text
Compartment nằm trong phạm vi được phép
AND Governance.Environment = dev
AND Automation.Schedule = office-hours
AND tài nguyên thuộc loại được hỗ trợ
AND không có ngoại lệ vận hành đang hiệu lực
~~~

Đây là logic thiết kế đề xuất, không phải policy OCI có thể dán trực tiếp. Công cụ còn cần danh sách loại trừ, ghi nhận thao tác và quyền IAM giới hạn theo phạm vi.

Đối với cơ sở dữ liệu và hệ thống yêu cầu sẵn sàng cao, kiểm tra sao lưu, khôi phục và phụ thuộc ứng dụng trước khi dùng tag để chọn mục tiêu tự động hóa.

## 10. Tài nguyên cũ và vòng đời schema

Khi bổ sung bộ tag vào tenancy đang vận hành, chia thành hai luồng công việc: cấu hình cho tài nguyên mới và bổ sung metadata cho tài nguyên hiện có.

Quy trình đề xuất cho tài nguyên cũ:

1. Lập danh sách theo loại dịch vụ và compartment.
2. Đối chiếu với chủ sở hữu thực tế.
3. Ánh xạ các biến thể cũ sang giá trị chuẩn.
4. Bổ sung key còn thiếu bằng API hoặc công cụ phù hợp.
5. Đọc lại kết quả, ghi nhận ngoại lệ chưa tìm được chủ sở hữu.

Ví dụ ánh xạ:

| Dữ liệu cũ | Giá trị chuẩn dự kiến | Cần xác nhận |
| --- | --- | --- |
| Free-form env=prd | Governance.Environment=prod | Tài nguyên thật sự phục vụ prod |
| Free-form team=orders | Governance.OwnerTeam=orders-platform | Đội còn nhận trách nhiệm |
| Chưa có cost center | FinOps.CostCenter=CC420 | Đơn vị tài chính chấp thuận |

Khi cập nhật bằng API hoặc IaC, đọc quy tắc của thao tác tương ứng: đừng mặc định một map mới sẽ được merge với tất cả tag cũ. Nên đọc hiện trạng, chuẩn bị bộ giá trị mong muốn, xem thay đổi rồi áp dụng trên tập đã xác định.

OCI phân biệt **retire** với xóa: retire ngăn áp dụng mới nhưng giữ tag đang có; xóa định nghĩa có thể loại bỏ tag khỏi các tài nguyên liên quan. Xem [Overview of Tagging — Retire](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Khi thay quy ước cũ, lập kế hoạch chuyển đổi: tạo key mới, cập nhật công cụ đọc dữ liệu, chuyển tài nguyên, theo dõi ngoại lệ rồi ngừng quy ước cũ. Tránh xóa schema dùng chung chỉ để sửa một tên gọi.

## 11. Những tình huống thường gây nhầm lẫn

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Không thấy namespace trong Console | Quyền inspect, domain/nhóm, nơi quản lý namespace |
| Tạo được VCN nhưng không gắn được defined tag | Quyền dùng namespace bên cạnh quyền trên VCN |
| production bị từ chối | Enum có chỉ cho phép prod hay không |
| Tài nguyên mới có tag nhưng tài nguyên cũ chưa có | Thời điểm tạo so với thời điểm đặt default |
| Chi phí chia thành nhiều nhóm gần giống | Biến thể chữ hoa thường và quy ước value |
| Đổi default nhưng tài nguyên hiện có vẫn giữ value cũ | Cần đợt cập nhật metadata riêng |
| Tự động hóa chọn nhầm tài nguyên | Đối chiếu compartment, defined tags và ngoại lệ |

Khi xử lý lỗi, ghi lại principal, OCID tài nguyên, compartment, namespace và value đã gửi. Những dữ liệu đó giúp phân biệt lỗi quyền với lỗi schema hoặc lỗi quy trình.

## 12. Tiêu chí hoàn thành thiết kế tagging

Một bộ tagging cho landing zone nên đạt các tiêu chí:

- Có danh mục namespace, key, ý nghĩa và người sở hữu schema.
- Thuộc tính quan trọng dùng defined tags với quy tắc value rõ ràng.
- Free-form tags có mục đích cụ thể, không tạo dữ liệu chuẩn song song.
- Tag defaults đặt ở cấp compartment phù hợp nghiệp vụ.
- Quyền tạo schema, quản lý default và gắn tag được cấp theo trách nhiệm.
- Có kế hoạch bổ sung metadata cho tài nguyên cũ.
- Luồng chi phí, giám sát và tự động hóa xác định rõ cách đọc tag.
- Có cách xử lý ngoại lệ, thay đổi chủ sở hữu và thay đổi schema.

Với ứng dụng Orders, kết quả mong đợi là tìm được đúng tài nguyên của order-api, xác định đội phụ trách và phân bổ chi phí theo quy ước. Quyết định tác động đến quyền, vòng đời hoặc tính sẵn sàng cần xét thêm trạng thái thực tế cùng điều kiện vận hành liên quan.
