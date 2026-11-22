# Mã hóa, encryption scope và khóa do khách hàng quản lý

Khi một ứng dụng ghi hóa đơn, hồ sơ nhân sự hoặc bản sao lưu vào Azure Storage, câu hỏi bảo mật không chỉ là “ai được đọc tệp?”. Doanh nghiệp còn muốn biết **dữ liệu được mã hóa ở đâu, ai kiểm soát khóa, có thể tách khóa cho từng nhóm dữ liệu hay không và điều gì xảy ra nếu khóa không còn sử dụng được**. Azure Storage cung cấp mã hóa phía máy chủ mặc định (server-side encryption), lựa chọn **encryption scope** cho dữ liệu blob và khả năng sử dụng **customer-managed keys (CMK)** được lưu trong Azure Key Vault hoặc Azure Key Vault Managed HSM tùy cấu hình được hỗ trợ.

Bài học thuộc chương **Nền tảng Azure Storage** của module `CLOUD_PROVIDERS_AZURE`. Trong module, bạn tìm hiểu hệ sinh thái Microsoft Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu; đồng thời học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Ở đây, trọng tâm là cách tổ chức chính sách mã hóa để vừa bảo vệ dữ liệu lưu trữ, vừa tránh làm mất khả năng truy cập do sai cấu hình khóa.

## 1. Sau bài học, bạn cần làm được gì?

- Giải thích **encryption at rest**, **encryption in transit** và **client-side encryption**.
- Hiểu mặc định Azure Storage mã hóa dữ liệu phía máy chủ và phân biệt **Microsoft-managed keys (MMK)** với **customer-managed keys (CMK)**.
- Mô tả cơ chế **envelope encryption**, dữ liệu mã hóa và khóa bao bọc khóa dữ liệu.
- Phân biệt chính sách mã hóa **cấp storage account** với **encryption scope cấp blob/container**.
- Thiết kế phân tách dữ liệu theo encryption scope và chọn chính sách khóa cho từng phạm vi.
- Hiểu vai trò của **managed identity**, Azure Key Vault/Managed HSM, quyền đối với khóa, rotation và khả năng khôi phục.
- Kiểm tra cấu hình bằng Azure Portal hoặc Azure CLI và nhận diện nguyên nhân thường gặp khi đọc/ghi blob thất bại.
- Chọn phương án phù hợp với yêu cầu bảo mật, kiểm toán, vận hành và chi phí.

## 2. Phân biệt ba lớp bảo vệ bằng mã hóa

| Lớp | Dữ liệu được bảo vệ khi nào? | Ví dụ trong Azure | Giới hạn cần nhớ |
|---|---|---|---|
| **Encryption at rest** | Dữ liệu đang được Azure Storage lưu trên phương tiện lưu trữ. | Azure Storage Service Encryption (SSE). | Người có quyền truy cập hợp lệ qua API vẫn có thể đọc dữ liệu đã được dịch vụ giải mã. |
| **Encryption in transit** | Dữ liệu di chuyển giữa client và dịch vụ hoặc giữa các thành phần mạng. | HTTPS/TLS khi ứng dụng gọi Blob Storage. | Không thay thế mã hóa dữ liệu đã ghi xuống đĩa. |
| **Client-side encryption** | Ứng dụng mã hóa dữ liệu trước khi gửi lên Azure. | SDK/ứng dụng quản lý quá trình mã hóa và khóa phía client. | Tăng trách nhiệm về quản lý khóa, tương thích SDK và khả năng xử lý dữ liệu. |

Ví dụ một hệ thống kế toán upload tệp `invoice.pdf`:

1. Ứng dụng dùng **HTTPS** để truyền tệp tới Blob Storage.
2. Azure Storage nhận tệp, mã hóa dữ liệu **at rest** trước khi lưu theo cơ chế SSE.
3. Khi một client đã được cấp quyền tải tệp, dịch vụ có thể giải mã phía máy chủ và trả nội dung qua HTTPS.
4. Nếu cần dữ liệu vẫn được mã hóa khi ngay cả Storage API trả kết quả, ứng dụng có thể áp dụng **client-side encryption** và tự quản lý khóa tương ứng.

**Mã hóa không thay thế phân quyền.** Một kẻ có quyền ghi/xóa hợp lệ có thể xóa hoặc ghi đè dữ liệu dù dữ liệu ở trạng thái nghỉ đã được mã hóa. Vì thế vẫn phải sử dụng Microsoft Entra ID, Azure RBAC, phân quyền dữ liệu, private networking, soft delete, versioning/immutability và kiểm soát hoạt động quản trị theo nhu cầu.

### Encryption at rest không đồng nghĩa “chỉ ai giữ khóa mới đọc được blob”

Khi dịch vụ Azure Storage quản lý việc mã hóa và giải mã, người dùng có quyền đọc blob được dịch vụ trả dữ liệu sau khi giải mã. Điều này đúng cả khi cơ chế dùng MMK hoặc CMK. CMK tăng **khả năng kiểm soát vòng đời và chính sách sử dụng khóa** của khách hàng, chứ không thay thế quyết định cấp quyền đọc blob.

## 3. Azure Storage Service Encryption (SSE) mặc định

Azure Storage tự động mã hóa dữ liệu **at rest** cho các storage account được hỗ trợ; SSE được bật mặc định và không phải là một tùy chọn “bật sau” cho từng blob thông thường. Dịch vụ sử dụng cơ chế mã hóa mạnh, phổ biến là **AES-256**, đồng thời quản lý việc mã hóa/giải mã trong hạ tầng lưu trữ.

Một luồng lưu trữ có thể được hiểu như sau:

```text
Ứng dụng
  │ Upload dữ liệu qua HTTPS/TLS
  ▼
Azure Storage API ── kiểm tra quyền truy cập ──> yêu cầu hợp lệ?
  │
  ▼
Storage Service Encryption
  │ Sử dụng khóa dữ liệu do dịch vụ quản lý
  ▼
Dữ liệu đã mã hóa được lưu tại tầng lưu trữ
```

Lợi ích:

- Dữ liệu không cần được ứng dụng tự mã hóa trước khi gửi để hưởng SSE.
- Ứng dụng đọc/ghi blob thường không cần thay đổi giao thức khi chuyển giữa MMK và CMK.
- Mã hóa hoạt động trong dịch vụ, giảm công việc cho nhóm phát triển ứng dụng.
- Có thể bổ sung chính sách khóa hoặc phạm vi mã hóa nếu yêu cầu kiểm soát chặt hơn.

### SSE hỗ trợ những dịch vụ nào?

Azure Storage có các dịch vụ như **Blob Storage, Azure Files, Queue Storage và Table Storage**. SSE mặc định áp dụng cho dữ liệu lưu trữ; tuy nhiên **tính năng dùng CMK và encryption scope không đồng nhất giữa tất cả dịch vụ hoặc loại storage account**.

Cụ thể, **encryption scope** là tính năng gắn với dữ liệu **Blob Storage** (bao gồm các tình huống Azure Data Lake Storage Gen2 được hỗ trợ). Không được xem nó là một cách chọn khóa riêng cho mỗi Azure Queue hay mỗi mục trong Azure Table. Với CMK cấp account cho Queue/Table hoặc các cấu hình đặc thù, phải kiểm tra tính năng đã được bật khi tạo tài khoản và giới hạn hiện hành của loại account.

## 4. Microsoft-managed keys và customer-managed keys

Trong SSE, cần phân biệt **ai quản lý khóa dùng để bảo vệ khóa dữ liệu**.

| Thuộc tính | Microsoft-managed keys (MMK) | Customer-managed keys (CMK) |
|---|---|---|
| Chủ thể quản lý khóa bao bọc | Microsoft/Azure Storage. | Khách hàng kiểm soát khóa trong Key Vault hoặc Managed HSM theo mô hình hỗ trợ. |
| Cấu hình ban đầu | Thường là mặc định. | Cần key vault/HSM, key, identity, permission và cấu hình storage. |
| Xoay vòng khóa | Azure quản lý theo cơ chế dịch vụ. | Khách hàng xác định chính sách vòng đời và rotation. |
| Khả năng thu hồi khóa | Không phải thao tác khách hàng trực tiếp quản lý khóa nền tảng. | Có thể ngăn dịch vụ sử dụng khóa; ảnh hưởng nghiêm trọng đến khả năng truy cập dữ liệu. |
| Chi phí và vận hành | Ít cấu hình quản lý khóa hơn. | Phát sinh trách nhiệm về vault/HSM, quyền, giám sát, khôi phục, giao dịch khóa. |
| Khi dùng | Dữ liệu thông thường không yêu cầu tự quản lý khóa. | Quy định kiểm toán, chính sách bảo mật hoặc yêu cầu quản lý khóa độc lập. |

**CMK không có nghĩa Azure Storage ngừng thực hiện mã hóa.** Azure Storage vẫn là thành phần mã hóa/giải mã dữ liệu, nhưng dịch vụ cần dùng khóa do khách hàng quản lý để bảo vệ các khóa mã hóa dữ liệu tương ứng.

### Envelope encryption: “khóa bao khóa”

Một cách hiểu hữu ích:

- **Data Encryption Key (DEK):** khóa dữ liệu dùng trong quá trình mã hóa dữ liệu.
- **Key Encryption Key (KEK):** khóa được dùng để bảo vệ/bao bọc DEK. Với CMK, KEK là khóa do khách hàng kiểm soát thông qua Key Vault hoặc Managed HSM.
- Dịch vụ dùng cơ chế **wrap/unwrap** khóa để bảo vệ hoặc khôi phục khả năng dùng DEK khi cần.

```text
                    Microsoft Entra / Managed Identity
                                │
                      Quyền dùng khóa phù hợp
                                │
                                ▼
                 Azure Key Vault / Managed HSM
                       CMK = Key Encryption Key
                         wrap / unwrap
                                ▲
                                │
Ứng dụng -- HTTPS --> Azure Storage Service
                                │
                       Data Encryption Key
                                │
                                ▼
                     Blob dữ liệu đã mã hóa
```

Đây là **sơ đồ khái niệm**. Dịch vụ có thể cache hoặc tối ưu quá trình xử lý khóa; không nên suy luận rằng mỗi yêu cầu đọc một blob đều bắt buộc gọi Key Vault đúng một lần.

**Không xuất khóa CMK về ứng dụng để gắn trong mã nguồn.** Ứng dụng bình thường chỉ gọi Storage API với quyền dữ liệu phù hợp. Cấu hình CMK và quyền truy cập Key Vault là trách nhiệm của lớp quản trị hạ tầng.

## 5. Hai cấp cấu hình: account encryption và encryption scope

Điểm dễ nhầm nhất là **CMK cấp storage account** và **encryption scope cấp blob**.

### Cấp storage account

Storage account có cấu hình mã hóa mặc định. Bạn có thể để Microsoft quản lý khóa hoặc, với tài khoản/cấu hình hỗ trợ, chuyển sang customer-managed key trong một vault/HSM phù hợp.

Ưu điểm: chính sách mã hóa **thống nhất cho phần dữ liệu sử dụng mã hóa cấp account**. Nếu một đơn vị kinh doanh sở hữu hoàn toàn storage account, đây có thể là lựa chọn đơn giản.

### Cấp encryption scope

**Encryption scope** là một đối tượng được tạo **bên trong storage account** để khai báo một **ranh giới mã hóa cho các blob được gán vào scope đó**. Mỗi scope có thể dùng:

- **Microsoft-managed keys**, hoặc
- **Customer-managed key** được liên kết với scope theo cấu hình được hỗ trợ.

Blob được ghi với scope nào sẽ sử dụng chính sách khóa của scope đó. Một storage account có thể có nhiều scope, giúp tổ chức các nhóm dữ liệu khác nhau mà không phải cấp riêng một storage account cho mọi nhóm.

```text
Storage account: stappdata001
│
├── Cấu hình mã hóa mặc định cấp account
│
├── Container: public-assets
│   └── Blob không gán scope riêng → dùng mặc định cấp account
│
├── Container: invoices
│   └── Default encryption scope = scope-finance
│       ├── invoice-001.pdf → scope-finance
│       └── invoice-002.pdf → scope-finance
│
└── Container: hr-documents
    └── Default encryption scope = scope-hr
        └── employees.csv → scope-hr

scope-finance → Customer-managed key của Finance
scope-hr      → Customer-managed key của HR
```

**Scope là ranh giới lựa chọn khóa, không phải ranh giới ủy quyền truy cập.** Nếu ai đó có quyền đọc blob ở cả hai container, việc dùng hai encryption scope không tự ngăn họ đọc các tệp đó qua Storage API. Cần phối hợp với Azure RBAC, ACL (khi hỗ trợ), cấu hình container và quyền truy cập mạng.

### So sánh nhanh

| Cấp chính sách | Phạm vi áp dụng | Trường hợp nên chọn |
|---|---|---|
| Storage account, MMK | Dữ liệu sử dụng mã hóa mặc định của account. | Đơn giản, ít quản lý khóa. |
| Storage account, CMK | Dữ liệu sử dụng mã hóa mặc định của account được bảo vệ bằng khóa khách hàng. | Toàn bộ account có cùng yêu cầu quản lý khóa. |
| Blob encryption scope, MMK | Các blob được gán scope đó. | Tách phạm vi mã hóa có quản lý bởi Microsoft. |
| Blob encryption scope, CMK | Các blob được gán scope đó với khóa cụ thể của scope. | Mỗi nhóm dữ liệu cần vòng đời khóa/chính sách riêng. |

Việc chọn scope phải diễn ra **ở thời điểm tạo hoặc ghi dữ liệu theo API được hỗ trợ**. Không nên cho rằng đổi mặc định của container sẽ tự chuyển toàn bộ dữ liệu đã tồn tại sang scope mới.

## 6. Default encryption scope và ngăn ghi đè

Ở **cấp container**, bạn có thể cấu hình:

1. **Default encryption scope:** scope được sử dụng mặc định khi tạo blob trong container.
2. **Prevent encryption scope override:** buộc các blob được tạo trong container tuân thủ default scope, thay vì cho client chỉ định một scope khác.

Ví dụ container `invoices` đặt default `scope-finance` và không cho override:

| Thao tác | Kết quả mong đợi |
|---|---|
| Upload blob không truyền encryption scope | Sử dụng `scope-finance` mặc định của container. |
| Upload blob có chỉ định `scope-finance` | Tuân thủ chính sách container nếu các điều kiện khác hợp lệ. |
| Upload blob có chỉ định `scope-hr` | Bị từ chối theo cấu hình ngăn override. |
| Đọc blob có quyền hợp lệ | Azure Storage giải mã trong dịch vụ theo khóa của blob. |

Lý do nên dùng mặc định có cưỡng chế: ứng dụng hoặc tác vụ ETL có thể quên truyền tham số encryption scope. Chính sách container giúp giảm khả năng ghi nhầm dữ liệu Finance bằng khóa của bộ phận khác.

### Vòng đời của blob đã tồn tại

Không giả định sửa default encryption scope, đổi scope của container hoặc chỉnh chính sách ở thời điểm hiện tại sẽ **tự động mã hóa lại mọi blob cũ**. Một blob đã được tạo với chính sách mã hóa cụ thể cần được xử lý theo cơ chế copy/rewrite/migration phù hợp nếu muốn chuyển sang phạm vi khác.

Trước khi chuyển dữ liệu, đánh giá các phiên bản blob, snapshot, đường dẫn ADLS Gen2, vòng đời sao lưu và hoạt động đọc/ghi đồng thời. Kiểm tra API và hạn chế của kiểu blob/loại account trong tình huống thực tế.

## 7. Chọn Key Vault hay Managed HSM

Azure cung cấp các dịch vụ quản lý khóa. Tính năng CMK của Azure Storage có thể tích hợp với **Azure Key Vault** và các lựa chọn Managed HSM được hỗ trợ.

| Tiêu chí | Azure Key Vault | Azure Key Vault Managed HSM |
|---|---|---|
| Vai trò | Lưu và quản lý key, secret, certificate theo phạm vi tính năng. | Dịch vụ quản lý khóa dựa trên HSM được quản lý, nhấn mạnh khả năng kiểm soát khóa. |
| Đối tượng quản lý | Key, secret và certificate trong vault. | Chủ yếu khóa mật mã theo mô hình HSM. |
| Phân quyền | Azure RBAC hoặc mô hình access policy được hỗ trợ; nên quản trị nhất quán. | Cơ chế quản trị/quyền HSM theo mô hình được hỗ trợ. |
| Chi phí, vận hành | Phù hợp với nhiều workload Azure. | Khác biệt về mức phí, quản trị và tiêu chuẩn tuân thủ. |
| Khi cân nhắc | Đa số kịch bản CMK thông thường. | Yêu cầu kiểm soát khóa/HSM và chính sách tổ chức đặc biệt. |

Không giả định mọi kiểu khóa, mọi phiên bản API hay mọi tính năng mã hóa Storage đều hỗ trợ tất cả cấu hình của Managed HSM. Cần kiểm tra **storage account kind, tính năng scope, loại key, SKU, region và tenant** theo yêu cầu hiện hành.

### Chọn khóa và chính sách vòng đời

Với CMK:

- Tạo khóa bằng thuật toán/kích thước được Azure Storage hỗ trợ.
- Bật **soft delete** và **purge protection** trên kho khóa theo yêu cầu hỗ trợ của dịch vụ và chính sách tổ chức.
- Quy định ai được **tạo, xoay vòng, vô hiệu hóa, xóa và khôi phục khóa**.
- Dùng tên khóa, version và ghi chú owner dễ nhận diện.
- Chuẩn bị quy trình backup/restore khóa phù hợp với vault/HSM và yêu cầu bảo vệ dữ liệu.
- Kiểm tra chính sách mạng cho phép Storage truy cập dịch vụ khóa theo phương thức hỗ trợ.
- Phân tách người quản trị Storage với người có quyền quản trị khóa ở mức hợp lý.

**Tắt, xóa hoặc không thể truy cập khóa CMK có thể khiến dữ liệu bị gián đoạn đọc/ghi.** Đây là quyền kiểm soát mạnh nhưng cũng là rủi ro vận hành. Không thử “thu hồi khóa để xem chuyện gì xảy ra” trên dữ liệu Production.

## 8. Managed identity và quyền truy cập khóa

Để Azure Storage sử dụng CMK, storage account hoặc cấu hình dịch vụ tương ứng cần một **managed identity** hợp lệ. Identity này được cấp quyền tối thiểu để dịch vụ truy cập khóa trong Key Vault/HSM.

Quy trình tổng quát:

1. Cấu hình **system-assigned** hoặc **user-assigned managed identity** theo kiểu mã hóa và tính năng được hỗ trợ.
2. Chọn Key Vault/Managed HSM và tạo key tương thích.
3. Cấp identity quyền sử dụng key để **đọc metadata và thực hiện wrap/unwrap** cần thiết.
4. Chọn khóa/Key URI trong cấu hình encryption của storage account hoặc encryption scope.
5. Kiểm tra storage có thể sử dụng khóa và tạo/đọc blob theo phạm vi dự kiến.

### Phân biệt control plane và data plane

| Quyền | Dùng để làm gì? | Ví dụ |
|---|---|---|
| **Quản trị Storage account** | Tạo/chỉnh encryption scope, identity, diagnostic settings, cấu hình account. | Azure RBAC phù hợp trên Storage account/resource group. |
| **Truy cập dữ liệu Blob** | Đọc/ghi/xóa blob qua data plane theo scope và quyền được cấp. | `Storage Blob Data Reader` hoặc `Storage Blob Data Contributor`. |
| **Sử dụng khóa** | Cho phép dịch vụ mã hóa sử dụng key để wrap/unwrap. | Quyền Key Vault tương ứng hoặc role như `Key Vault Crypto Service Encryption User` nếu mô hình RBAC áp dụng. |
| **Quản trị khóa** | Tạo, xoay vòng, vô hiệu hóa, xóa/khôi phục khóa. | Role/permission quản trị khóa riêng với quyền sử dụng khóa. |

Quyền truy cập Azure Resource Manager như `Contributor` trên storage account **không mặc nhiên cấp quyền đọc blob**. Tương tự, quyền đọc blob không cấp quyền quản trị khóa trong vault. Hãy kiểm tra đúng loại quyền và mô hình RBAC/access policy đang được vault sử dụng.

### Vì sao lỗi quyền khóa ảnh hưởng ứng dụng?

Khi storage account hoặc encryption scope sử dụng CMK, dịch vụ cần có quyền và đường truy cập tới kho khóa. Nếu managed identity bị xóa, quyền wrap/unwrap bị thu hồi hoặc khóa không còn khả dụng, các thao tác dữ liệu phụ thuộc vào khóa có thể thất bại dù ứng dụng vẫn giữ quyền Blob Data Contributor hợp lệ.

Điều tra lỗi phải tách hai lớp:

- **Lớp dữ liệu:** user/service principal có quyền truy cập blob không?
- **Lớp mã hóa:** Azure Storage có khả năng sử dụng CMK tương ứng không?

Sửa sai lớp có thể dẫn đến cấp quyền rộng quá mức mà vẫn không giải quyết lỗi.

## 9. Key rotation, version và khả năng khôi phục

**Key rotation** là thay khóa hoặc tạo phiên bản khóa mới theo chính sách, nhằm hạn chế rủi ro vòng đời khóa và đáp ứng yêu cầu tổ chức.

### Không nhầm rotation với mã hóa lại từng blob

Trong mô hình envelope encryption, CMK thường **bảo vệ khóa dữ liệu**, không phải trực tiếp mã hóa từng byte của mọi blob. Vì vậy, xoay vòng CMK thường **không yêu cầu ứng dụng tải lại tất cả blob để tự mã hóa**. Dịch vụ áp dụng cơ chế chuyển đổi/bao bọc khóa theo thiết kế hỗ trợ.

Tuy nhiên, điều này **không** có nghĩa tất cả dữ liệu cũ lập tức không còn phụ thuộc vào phiên bản khóa cũ. Phải quản lý phiên bản khóa và retention theo yêu cầu của Storage và vault; không vội xóa key version đang còn cần để đọc dữ liệu.

### Hai mô hình tham chiếu khóa

- **Theo phiên bản cố định:** cấu hình tham chiếu một version cụ thể; việc tạo version mới chưa chắc tự làm Storage chuyển sang version mới.
- **Theo cơ chế tự cập nhật phiên bản:** dịch vụ có thể theo dõi phiên bản mới theo khả năng hỗ trợ và áp dụng sau khoảng thời gian cập nhật. Cần kiểm tra hành vi thực tế của kiểu key, cấu hình và API.

Ví dụ biểu diễn URI:

```text
Key có version cụ thể:
https://kv-contoso.vault.azure.net/keys/blob-finance/<KEY_VERSION>

Key URI không gắn version:
https://kv-contoso.vault.azure.net/keys/blob-finance
```

Đây là ví dụ về cách biểu diễn định danh khóa; khả năng dùng URI versionless và chuyển đổi version phụ thuộc loại cấu hình CMK. Không tự động thay URL ở Production khi chưa kiểm tra hỗ trợ và đường rollback.

### Quy trình rotation an toàn

1. Kiểm tra **identity, permission, key status, network access** hiện tại đều hoạt động.
2. Xác nhận cơ chế auto-rotation hoặc manual rotation của cấu hình đang dùng.
3. Tạo key version mới theo chính sách, giữ lại phiên bản cũ trong thời gian cần thiết.
4. Để Storage cập nhật hoặc thực hiện thay đổi theo thủ tục đã được phê duyệt.
5. Xác minh một số blob cũ và mới đều đọc/ghi thành công.
6. Theo dõi lỗi truy cập key, Azure Monitor và log ứng dụng.
7. Chỉ lên kế hoạch ngừng sử dụng version cũ sau khi đã xác định không còn dữ liệu/phụ thuộc cần phiên bản đó.

### Nếu khóa hoặc vault gặp sự cố

Không phản ứng bằng cách tạo ngay một khóa mới **cùng tên** rồi kỳ vọng dữ liệu cũ sẽ đọc được. Tên giống nhau không có nghĩa material khóa giống nhau. Nếu key material/phiên bản cần thiết đã bị xóa, phải sử dụng quy trình **recover/restore** hợp lệ của dịch vụ khóa, trong giới hạn retention, backup và quyền tổ chức.

Chuẩn bị trước tình huống:

- Soft delete và purge protection đã được bật.
- Backup và khả năng khôi phục khóa được kiểm tra theo mô hình hỗ trợ.
- Thông tin owner/escalation của vault và storage account được ghi nhận.
- Cảnh báo khi khóa sắp hết hiệu lực, bị disabled hoặc khi ứng dụng không đọc/ghi dữ liệu.
- Hướng xử lý khi identity, RBAC, mạng hoặc vault bị thay đổi bởi nhóm khác.

## 10. Mã hóa hạ tầng hai lớp và các lựa chọn bổ sung

Azure Storage có lựa chọn **infrastructure encryption** (thường được gọi là double encryption) trong các cấu hình được hỗ trợ. Đây là lớp mã hóa bổ sung ở mức hạ tầng bên cạnh SSE cấp dịch vụ, dùng cơ chế/khóa độc lập theo thiết kế của Azure.

| Cơ chế | Phạm vi ý tưởng | Khi cân nhắc |
|---|---|---|
| SSE với MMK | Mã hóa dữ liệu at rest mặc định. | Nhiều workload thông thường. |
| SSE với CMK | Mã hóa at rest và khách hàng kiểm soát key wrapping. | Kiểm toán/quy định quản lý khóa. |
| Encryption scopes | Chọn chính sách khóa theo phạm vi blob. | Một account có nhiều nhóm dữ liệu yêu cầu phân tách. |
| Infrastructure encryption | Lớp mã hóa hạ tầng bổ sung khi cấu hình hỗ trợ. | Yêu cầu phòng vệ nhiều lớp. |
| Client-side encryption | Ứng dụng mã hóa trước khi gửi lên Storage. | Dữ liệu cần mã hóa theo khóa chỉ ứng dụng/khách hàng kiểm soát từ phía client. |

**Infrastructure encryption không thay thế CMK hay encryption scopes**, và không mặc nhiên được bật vì đã chọn CMK. Tùy chọn này thường được quyết định ở **thời điểm tạo storage account** và có những giới hạn thay đổi sau đó. Hãy chốt yêu cầu trước khi triển khai để tránh phải tạo lại tài khoản hoặc di chuyển dữ liệu.

### CMK khác customer-provided key (CPK)

**Customer-provided key** là kiểu sử dụng khóa mã hóa do client cung cấp cùng các yêu cầu Blob được hỗ trợ, theo cơ chế riêng của API. Nó khác **CMK lưu trong Key Vault** mà Azure Storage tham chiếu và sử dụng để bảo vệ khóa dữ liệu.

Không dùng hai thuật ngữ thay thế nhau: chúng có trách nhiệm quản lý khóa, vòng đời, hỗ trợ API và cách xử lý sự cố khác nhau.

## 11. Thiết kế encryption scope theo nhóm dữ liệu

Giả sử công ty sử dụng chung một storage account cho ba nhóm:

- **Assets công khai:** ảnh, CSS, dữ liệu không nhạy cảm.
- **Finance:** hóa đơn và bảng kê thanh toán.
- **HR:** tài liệu nhân sự và dữ liệu nhạy cảm.

Một thiết kế minh họa:

| Nhóm dữ liệu | Container | Chính sách mã hóa | Quyền dữ liệu |
|---|---|---|---|
| Public assets | `public-assets` | Mặc định của account, MMK hoặc theo chính sách account. | Chỉ cho phép quyền cần thiết; “public assets” không đồng nghĩa bật anonymous access. |
| Finance | `invoices` | Default `scope-finance` dùng CMK riêng; chặn override. | Nhóm/ứng dụng Finance theo least privilege. |
| HR | `hr-documents` | Default `scope-hr` dùng CMK riêng; chặn override. | Nhóm/ứng dụng HR với phân quyền riêng. |

Mục tiêu:

1. **Tách khóa và vòng đời khóa** giữa Finance và HR.
2. **Tách quyền đọc/ghi dữ liệu** bằng Entra ID/RBAC hoặc ACL phù hợp.
3. **Kiểm soát chi phí** khi cần chia sẻ account thay vì tạo rất nhiều account riêng.
4. **Đơn giản hóa giám sát** qua quy tắc tên scope, policy và owner rõ ràng.

Không được suy diễn rằng encryption scope tạo ra **biên giới cô lập hoàn toàn** giữa các nhóm. Storage account vẫn là một ranh giới quản trị chung với những giới hạn, quota, networking và một số cấu hình cấp account. Nếu yêu cầu pháp lý cần cô lập ở cấp tài khoản, subscription hoặc tenant, phải thiết kế các tài nguyên riêng.

### Quy ước quản trị nên có

| Thuộc tính IPAM/registry bảo mật | Giá trị minh họa |
|---|---|
| Storage account | `stappdata001` |
| Container | `invoices` |
| Encryption scope | `scope-finance` |
| Key owner | Team Finance Security |
| Key store | Key Vault đã được phê duyệt |
| Data owner | Finance Applications |
| Rotation policy | Theo chính sách nội bộ |
| Recovery contact | Nhóm Platform Security |
| Retention/immutability | Theo phân loại dữ liệu |
| Monitoring | Audit key, Storage error metrics và alert |

Đừng ghi giá trị khóa hoặc secret trong bảng đăng ký; chỉ ghi định danh tài nguyên và thông tin vận hành cần thiết.

## 12. Thực hành trên Azure Portal: thiết lập từ account đến container

Quy trình dưới đây là **mẫu triển khai** để hiểu các bước. Việc tạo Key Vault, storage account, encryption scope hoặc lưu trữ blob có thể tạo chi phí. Chỉ thực hiện trong subscription và resource group được phép.

### Bước 1: Xác định storage account và loại dịch vụ

1. Mở [Azure Portal](https://portal.azure.com/).
2. Chọn đúng tenant, subscription và resource group.
3. Mở storage account dự kiến dùng, kiểm tra loại account và loại dữ liệu (Blob/Azure Files/ADLS Gen2...).
4. Kiểm tra cấu hình **Encryption** của account để biết MMK hay CMK.
5. Xác minh tính năng **encryption scope** được hỗ trợ với loại account và operation bạn cần.

### Bước 2: Chuẩn bị CMK trong Key Vault

1. Tạo hoặc chọn Key Vault/Managed HSM phù hợp.
2. Xác nhận soft delete, purge protection, quyền và chính sách mạng.
3. Tạo khóa phù hợp để dùng với Azure Storage; ghi lại Key URI/ID theo quy trình của tổ chức.
4. Bật/chuẩn bị managed identity dùng cho CMK.
5. Cấp quyền cần thiết để Storage có thể wrap/unwrap khóa.

Ở bước này nên làm kiểm tra truy cập từ Storage tới kho khóa, không chỉ kiểm tra máy của quản trị viên có thể mở Key Vault bằng trình duyệt.

### Bước 3: Tạo encryption scope

1. Trong trang storage account, mở chức năng **Encryption scopes** thuộc nhóm quản lý dữ liệu/bảo mật tùy giao diện.
2. Tạo `scope-finance` và chọn nguồn khóa phù hợp:
   - Microsoft-managed key khi chỉ cần tách scope mà không tự quản lý key.
   - Customer-managed key khi Finance cần tự kiểm soát khóa.
3. Nếu dùng CMK, chọn key vault/key hoặc chỉ định URI theo cách Portal hỗ trợ.
4. Lưu và kiểm tra scope có trạng thái hoạt động, nguồn mã hóa và thông tin key đúng mong đợi.
5. Tạo `scope-hr` tương tự với key riêng nếu chính sách yêu cầu.

### Bước 4: Gắn scope với container

1. Tạo container `invoices` hoặc chọn container hỗ trợ cấu hình theo nhu cầu.
2. Chọn default encryption scope = `scope-finance`.
3. Bật **Prevent encryption scope override** nếu yêu cầu mọi blob trong container theo scope đó.
4. Kiểm tra quyền dữ liệu của ứng dụng dùng container.
5. Thử upload một blob lab và quan sát encryption scope được áp dụng.

Không áp dụng thử nghiệm xóa/disable key trên container chứa dữ liệu thật. Những bước gây mất khả năng đọc dữ liệu chỉ nên có trong kế hoạch kiểm thử riêng với bản sao an toàn.

## 13. Kiểm tra bằng Azure CLI

Azure CLI cho phép quan sát cấu hình trước khi tạo hoặc thay đổi scope. Các lệnh dưới đây dùng placeholder và trước hết là **read-only**.

### Xem subscription đang sử dụng

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Account:user.name}" \
  --output table
```

Nếu thao tác trên sai subscription, cần điều chỉnh context trước khi thay đổi Storage.

### Xem cấu hình mã hóa của account

```bash
az storage account show \
  --name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --query "{Name:name,Encryption:encryption,Identity:identity}" \
  --output json
```

Dữ liệu trả về giúp kiểm tra nguồn khóa, loại mã hóa và managed identity khi có. Không giả định mọi trường JSON đều có giá trị trong mọi SKU/cấu hình.

### Liệt kê encryption scopes

```bash
az storage account encryption-scope list \
  --account-name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output table
```

### Xem chi tiết một scope

```bash
az storage account encryption-scope show \
  --account-name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --name "scope-finance" \
  --output json
```

Hãy đối chiếu trạng thái scope, loại nguồn khóa và URI khóa với thông tin dự án. Nếu CLI báo quyền không đủ hoặc không tìm thấy scope, xác minh subscription, resource group, tên account và quyền control plane.

### Minh họa lệnh tạo một encryption scope với MMK

Lệnh sau **làm thay đổi tài nguyên** và chỉ nên dùng trong môi trường lab được phép:

```bash
az storage account encryption-scope create \
  --account-name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --name "scope-lab" \
  --source "Microsoft.Storage"
```

Với scope dùng CMK, cách cấu hình nguồn khóa thường dựa trên `Microsoft.KeyVault` và Key URI, cùng managed identity/permission đã chuẩn bị. Các tùy chọn cụ thể của lệnh tạo có thể khác theo phiên bản Azure CLI, loại tài khoản và yêu cầu key version; nên kiểm tra:

```bash
az storage account encryption-scope create --help
```

Tránh tự động hóa bước CMK trước khi xác minh đúng tùy chọn và quyền được cấp trong môi trường triển khai.

### Ghi blob có chỉ định scope

Ví dụ upload vào container khi scope đã tồn tại và policy cho phép:

```bash
az storage blob upload \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "lab-documents" \
  --name "sample.txt" \
  --file "./sample.txt" \
  --encryption-scope "scope-lab" \
  --auth-mode login
```

Lệnh này **ghi dữ liệu**. Tài khoản đăng nhập phải có quyền Blob data plane tương ứng; container và tệp nguồn phải tồn tại. Nếu container đặt default scope và chặn override, scope chỉ định phải phù hợp chính sách.

### Xác nhận blob sau khi upload

```bash
az storage blob show \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "lab-documents" \
  --name "sample.txt" \
  --auth-mode login \
  --output json
```

Đọc metadata/các thuộc tính hỗ trợ để xác nhận encryption scope. Tên trường có thể thay đổi theo phiên bản lệnh và API; khi cần, xem JSON đầy đủ thay vì chỉ dựa vào bảng tóm tắt.

## 14. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| Không tạo được encryption scope | Loại storage account không hỗ trợ, thiếu quyền hoặc tính năng không tương thích. | Kiểm tra SKU/kind, hỗ trợ API, quyền control plane và message lỗi. |
| Tạo scope với CMK thất bại | Key URI sai, identity chưa được cấu hình, quyền Key Vault thiếu hoặc network chặn. | Kiểm tra key status, managed identity, RBAC/access policy, firewall/private endpoint. |
| Upload vào container bị từ chối khi truyền scope khác | Container bật ngăn override mặc định. | Xem default scope và thuộc tính prevent override. |
| Ứng dụng có quyền Blob Data Contributor nhưng không đọc/ghi được | Lỗi key access, scope disabled hoặc dữ liệu/backend khác. | Tách kiểm tra quyền Blob data plane và trạng thái CMK/scope. |
| Blob cũ vẫn dùng chính sách mã hóa trước đây | Thay đổi default scope không tự chuyển blob tồn tại. | Kiểm tra scope của blob và kế hoạch rewrite/migration. |
| Dịch vụ mất khả năng đọc sau khi khóa bị disable | Storage không thể dùng CMK cần thiết. | Kiểm tra key status, version, quyền và phục hồi theo runbook. |
| Lỗi truy cập vault sau khi bật firewall | Storage không còn đường truy cập vault. | Kiểm tra routing, firewall, private endpoints và cơ chế trusted services được hỗ trợ. |
| Rotation xong vẫn thấy tham chiếu version cũ | Dịch vụ chưa áp dụng version mới hoặc cấu hình cố định version. | Kiểm tra rotation policy, version URI và thời gian cập nhật. |
| Phát sinh nhiều chi phí Key Vault/Managed HSM | Nhiều scope, thao tác khóa, vault/HSM hoặc log retention. | Phân tích billing, metrics và mức sử dụng thực tế. |
| Có CMK nhưng audit yêu cầu vẫn không đạt | Chưa có policy rotation/recovery, log và phân quyền đúng. | Đối chiếu bằng chứng quản trị khóa với yêu cầu kiểm toán. |

### Runbook: một ứng dụng đột ngột không truy cập được blob

1. Xác định storage account, container, blob, thời điểm UTC và request ID liên quan.
2. Kiểm tra trạng thái storage account, error code trả về và Azure Monitor/Storage logs.
3. Xác nhận caller có quyền dữ liệu phù hợp, token chưa hết hạn và network access không bị chặn.
4. Xem encryption scope của blob/container; xác định MMK hay CMK.
5. Nếu dùng CMK, kiểm tra managed identity, quyền wrap/unwrap, trạng thái key/version và connectivity tới vault.
6. Kiểm tra lịch thay đổi: role assignment, Key Vault firewall, key rotation, disable/delete key hoặc scope.
7. Nếu cần khôi phục key, làm theo runbook đã được tổ chức phê duyệt, ưu tiên recover/restore khóa gốc và phiên bản cần thiết.
8. Sau khi xử lý, thử đọc **blob cũ** và ghi/đọc **blob mới**; theo dõi lỗi và ghi lại bằng chứng.

Không vô hiệu hóa mã hóa hay cấp quyền Owner rộng cho mọi người để khắc phục tạm một lỗi chưa được xác định. Các quyền quản trị khóa có hậu quả lớn, đặc biệt với dữ liệu được dùng chung bởi nhiều ứng dụng.

## 15. Giám sát, kiểm toán và kiểm soát chi phí

Khi vận hành Azure Storage có CMK, cần quan sát cả **Storage** lẫn **Key Vault/HSM**:

- **Storage metrics và logs:** lỗi request, latency, khả năng đọc/ghi và các sự kiện thay đổi cấu hình.
- **Azure Activity Log:** thao tác quản trị storage account/encryption scope và một số thay đổi thuộc control plane.
- **Key Vault/HSM diagnostic logs:** thao tác với key, truy cập bị từ chối, thay đổi quyền/chính sách theo khả năng cung cấp của nguồn log.
- **Key lifecycle monitoring:** tình trạng enabled/disabled, ngày hết hạn, chính sách rotation và cảnh báo phục hồi.
- **Identity/RBAC changes:** thay đổi managed identity, nhóm quyền hoặc quyền trên vault.
- **Alert rules:** lỗi Storage tăng đột biến, mất khả năng truy cập key hoặc ứng dụng báo lỗi liên tục.

### Bảo vệ bằng phân chia trách nhiệm

Một quy trình quản trị có thể tách:

1. **Storage operator** quản lý container, scope và cấu hình storage.
2. **Security/key custodian** quản lý key policy, rotation, recovery và phê duyệt thay đổi quyền trên vault.
3. **Application identity** chỉ có quyền Blob data plane cần thiết.
4. **Storage managed identity** chỉ có quyền mật mã cần thiết đối với key được cấu hình.
5. **Auditor** có quyền đọc log, cấu hình và báo cáo theo phạm vi cho phép.

Quyền quản trị được cấp theo vai trò thực tế; vai trò trên là **mô hình trách nhiệm**, không phải tên role bắt buộc có sẵn trong Azure.

### Các chi phí cần xem

| Hạng mục | Phát sinh từ đâu? |
|---|---|
| Storage | Dung lượng, tier, giao dịch đọc/ghi, replication và các tính năng dữ liệu. |
| Key Vault | Loại vault, thao tác mật mã, số lượng key/certificate, logging tùy gói. |
| Managed HSM | Cấu hình dịch vụ, mức sử dụng và vận hành quản lý khóa. |
| Encryption scopes | Có thể có chi phí liên quan đến tính năng/scope theo mô hình giá và SKU hiện hành. |
| Diagnostic logs | Ingestion, retention và đích lưu trữ/Log Analytics. |
| Network/private endpoints | Thành phần networking và dữ liệu truyền, nếu triển khai. |

Dùng **Azure Pricing Calculator** và báo giá hiện hành của region/SKU để quyết định. Mỗi encryption scope CMK kéo theo khả năng phải quản lý thêm quyền, key và runbook, nên không tạo hàng trăm scope khi nhóm dữ liệu chỉ yêu cầu một chính sách chung.

## 16. Bài thực hành: xây chính sách mã hóa cho Finance và HR

**Bối cảnh:** Một ứng dụng lưu ảnh sản phẩm, hóa đơn và hồ sơ nhân sự trên Blob Storage. Finance và HR yêu cầu tự quản lý khóa riêng và có thể chứng minh dữ liệu dùng đúng khóa. Ảnh sản phẩm không có yêu cầu CMK riêng. Tổ chức muốn hạn chế chi phí nhưng vẫn phân tách quyền.

Thông tin giả định:

| Thành phần | Giá trị |
|---|---|
| Storage account | `stappdata001` |
| Container ảnh | `public-assets` |
| Container hóa đơn | `invoices` |
| Container nhân sự | `hr-documents` |
| Encryption scope Finance | `scope-finance`, CMK Finance |
| Encryption scope HR | `scope-hr`, CMK HR |
| Quyền ứng dụng | Mỗi ứng dụng chỉ được đọc/ghi container tương ứng |
| Chính sách container | Không cho phép override scope ở Finance và HR |

### Nhiệm vụ

1. Phân biệt phần mã hóa mặc định MMK với hai scope CMK.
2. Vẽ sơ đồ Key Vault/managed identity và Storage cho hai nhóm dữ liệu.
3. Đề xuất cấu hình default encryption scope và prevent override của mỗi container.
4. Nêu các quyền cần cấp cho **storage managed identity** và các identity ứng dụng.
5. Lập các bước kiểm tra khi tạo blob mới và đọc blob cũ.
6. Thiết kế quy trình rotation và phục hồi khi một key version gặp sự cố.
7. Nêu nguồn log cần giám sát và bằng chứng phải lưu cho kiểm toán.
8. Đánh giá khi nào cần tách Finance/HR thành các storage account khác nhau.

### Lời giải tham khảo

**Phân tách:**

```text
Storage account: stappdata001
|
|-- public-assets  ----------> account default encryption (MMK)
|
|-- invoices       ----------> scope-finance (CMK Finance)
|      |                          |
|      +-- no override           +--> Key Vault / key-finance
|
+-- hr-documents   ----------> scope-hr (CMK HR)
       |                          |
       +-- no override           +--> Key Vault / key-hr

Storage managed identity: quyền dùng key ở phạm vi cần thiết
Finance app identity: quyền dữ liệu Finance, không quản trị key
HR app identity:      quyền dữ liệu HR, không quản trị key
```

**Kiểm thử:** upload một blob thử trong `invoices` không truyền scope, xác nhận blob dùng `scope-finance`; thử chọn `scope-hr` phải bị từ chối khi override bị ngăn. Tài khoản Finance không thể đọc HR nếu phân quyền dữ liệu được cấu hình đúng. Không cần và không được vô hiệu hóa key thật chỉ để chứng minh chính sách.

**Rotation:** tạo version mới theo runbook, giám sát dịch vụ áp dụng version, kiểm tra đọc/ghi các blob cũ và mới, giữ key version cũ đến khi chắc chắn không còn cần. Có backup/recovery và người chịu trách nhiệm rõ ràng.

**Khi cần tách account:** nếu HR phải có firewall, private endpoint, quy định lưu giữ, quota, subscription/tenant hoặc trách nhiệm quản trị tách biệt hoàn toàn, encryption scope trong cùng account có thể chưa đủ. Khi đó hai storage account riêng là lựa chọn hợp lý hơn.

### Tiêu chí nghiệm thu

- Đã phân biệt **mã hóa** với **quyền đọc dữ liệu**.
- Mỗi container nhạy cảm có encryption scope và key đúng yêu cầu.
- Managed identity có quyền sử dụng key cần thiết, không có quyền rộng tùy tiện.
- Quy trình rotation và recovery bảo đảm có thể đọc dữ liệu hiện tại lẫn dữ liệu cũ.
- Có phương án kiểm tra lỗi, audit và giám sát chi phí trước khi đưa vào Production.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Với Azure Storage Service Encryption mặc định, ứng dụng có cần tự mã hóa dữ liệu trước khi upload để đạt encryption at rest không?

A. Có, nếu không Azure lưu plaintext.  
B. Không; Storage tự mã hóa at rest.  
C. Chỉ nếu upload bằng HTTPS.

**Đáp án: B.** SSE mã hóa dữ liệu ở lớp dịch vụ. HTTPS bảo vệ đường truyền, còn client-side encryption là tùy chọn riêng khi ứng dụng có yêu cầu cao hơn.

**Câu 2.** Khác biệt chính giữa MMK và CMK là gì?

**Đáp án:** Chủ thể quản lý vòng đời khóa dùng để bảo vệ khóa dữ liệu. CMK cho phép khách hàng kiểm soát key trong Key Vault/HSM theo cấu hình hỗ trợ, nhưng Storage vẫn đảm nhận mã hóa/giải mã SSE.

**Câu 3.** Encryption scope có tự động cấm người dùng của Finance đọc blob HR không?

**Đáp án:** Không. Scope tách chính sách khóa, không thay cho quyền truy cập dữ liệu. Phải cấu hình Entra ID, RBAC/ACL và network policies.

**Câu 4.** Container `invoices` có default `scope-finance` và prevent override. Client upload với `scope-hr` sẽ thế nào?

**Đáp án:** Yêu cầu phải bị từ chối vì scope được chỉ định trái chính sách container.

**Câu 5.** Đổi default encryption scope ở container có tự động chuyển tất cả blob cũ sang scope mới không?

**Đáp án:** Không. Phải đánh giá cơ chế rewrite/copy/migration phù hợp nếu muốn đổi scope của dữ liệu tồn tại.

**Câu 6.** Ứng dụng đã có Storage Blob Data Contributor nhưng vẫn bị lỗi đọc dữ liệu dùng CMK. Cần kiểm tra thêm điều gì?

**Đáp án:** Tình trạng khóa, version, managed identity, quyền sử dụng khóa và kết nối từ Storage tới Key Vault/HSM. Quyền Blob data plane không đủ nếu Storage không thể dùng CMK.

**Câu 7.** Có nên xóa ngay phiên bản khóa cũ khi vừa tạo version CMK mới?

**Đáp án:** Không. Cần xác minh phụ thuộc và khả năng đọc dữ liệu cũ; xóa/disable version còn cần thiết có thể gây mất khả năng truy cập dữ liệu.

**Câu 8.** Infrastructure encryption có đồng nghĩa với encryption scope không?

**Đáp án:** Không. Infrastructure encryption bổ sung lớp mã hóa hạ tầng; encryption scope chọn ranh giới/chính sách khóa cho blob.

**Câu 9.** Customer-managed key và customer-provided key có phải cùng một cơ chế không?

**Đáp án:** Không. CMK là khóa được Storage tham chiếu và quản lý vòng đời qua vault/HSM; CPK do client cung cấp trong các API hỗ trợ.

**Câu 10.** Vì sao cần theo dõi cả Storage log và Key Vault log?

**Đáp án:** Storage log giúp xác định yêu cầu dữ liệu bị lỗi, còn Key Vault log và thông tin vòng đời khóa giúp phân biệt lỗi quyền, mạng, rotation hoặc trạng thái khóa, từ đó xử lý đúng nguyên nhân.

Thiết kế mã hóa Azure Storage hiệu quả là lựa chọn đúng **ranh giới chính sách, quyền và vòng đời khóa**. MMK giúp đơn giản hóa vận hành; CMK tăng quyền kiểm soát khóa; encryption scope giúp phân nhóm dữ liệu ở cấp blob/container. Cả ba phải được kết hợp với phân quyền, giám sát, rotation và khôi phục để dữ liệu vừa được bảo vệ, vừa có thể truy cập ổn định khi ứng dụng cần.
