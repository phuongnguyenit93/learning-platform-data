# Phân quyền quản lý thanh toán và đối soát chi phí trên Google Cloud

> **Chương:** Thanh toán và ngân sách  
> **Bài học:** Phân quyền quản lý thanh toán và đối soát chi phí

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM, VPC đến Compute Engine, GKE, Cloud Run, các dịch vụ lưu trữ và cơ sở dữ liệu; đồng thời học lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Một hệ thống hoạt động tốt về kỹ thuật vẫn cần trả lời được **ai được xem hoặc thay đổi thông tin thanh toán, chi phí thuộc về đội nào và tổng chi phí nội bộ có đối chiếu được với chứng từ thanh toán hay không**.

Bài này đi từ cấu trúc Cloud Billing, IAM và phân tách nhiệm vụ, đến quy trình đối soát hóa đơn, phân bổ chi phí và thiết lập dữ liệu phục vụ FinOps. Các ví dụ dùng tên tổ chức, số tiền và mã định danh **giả định**; không cần truy cập billing account thật để hiểu quy trình.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Cloud Billing account**, **Google Cloud project**, **Google payments profile**, người thanh toán và chủ sở hữu chi phí.
2. Chọn đúng phạm vi IAM và vai trò cho quản trị billing, kế toán, FinOps, chủ project, người quản lý ngân sách và người phụ trách dữ liệu xuất sang BigQuery.
3. Phân biệt **xem chi phí**, **quản lý ngân sách**, **liên kết project với billing account**, **quản lý phương thức thanh toán** và **truy cập chứng từ**.
4. Đối chiếu **chi phí theo ngày sử dụng** với **kỳ hóa đơn**, nhận biết credit, discount, thuế, adjustment, giao dịch theo tài khoản và chi phí dùng chung.
5. Thiết kế **showback/chargeback** theo project, nhãn, nhóm sản phẩm và quy tắc phân bổ chi phí chung; xử lý phần chưa thể quy thuộc.
6. Dùng Cloud Billing Reports/Cost table và dữ liệu export BigQuery để điều tra chênh lệch, báo cáo đúng kỳ và đưa ra biện pháp kiểm soát chi tiêu.

## 2. Bản đồ các đối tượng và ranh giới quyền

Một **Cloud Billing account** thu thập chi phí sử dụng của các project liên kết và chịu trách nhiệm thanh toán theo mô hình tài khoản. Một **Google Cloud project** chứa hoặc định danh phạm vi nhiều tài nguyên kỹ thuật. Một project chỉ liên kết với **một** Cloud Billing account tại một thời điểm, nhưng một billing account có thể thanh toán cho **nhiều** project.

**Google payments profile** là hệ thống thông tin và phương thức thanh toán liên quan. Quyền trên payments profile và vai trò IAM của Cloud Billing **không hoàn toàn đồng nhất**. Tùy loại tài khoản, một số quyền trên Cloud Billing account cũng cho phép thao tác thanh toán qua Console, nhưng quyền quản trị đầy đủ payments profile có thể cần cấu hình quyền riêng trong Google payments.

~~~mermaid
flowchart TB
    Org["Organization / Folder"] --> Dev["Project: development"]
    Org --> Prod["Project: production"]
    Org --> Data["Project: data-analytics"]
    Dev --> B["Cloud Billing account"]
    Prod --> B
    Data --> B
    B --> Pay["Google payments profile / quy trình thanh toán"]
    B --> Reports["Reports, Cost table, Budgets"]
    B --> Export["Billing export → BigQuery dataset"]
    Admin["IAM trên Billing account"] -. "Cho phép xem/quản lý" .-> B
    ProjectIAM["IAM trên Project"] -. "Quyền theo project" .-> Prod
    DatasetIAM["IAM trên BigQuery dataset"] -. "Quyền đọc dữ liệu xuất" .-> Export
~~~

Sơ đồ cho thấy **ba lớp quyền khác nhau**:

- **Billing-account IAM**: ai xem chi phí trên toàn billing account, ai quản lý ngân sách/cấu hình xuất dữ liệu và ai quản trị tài khoản.
- **Project IAM**: ai được quản lý tài nguyên, xem chi phí trong phạm vi project hoặc thao tác liên kết thanh toán theo quyền tương ứng.
- **BigQuery dataset IAM và payments permissions**: ai đọc dữ liệu chi phí đã xuất, ai xem chứng từ và quản lý thông tin thanh toán trong hệ thống tài chính.

**Cảnh báo quan trọng:** Cấp quyền chỉ xem billing tại một project không tự động cấp quyền xem chi phí của tất cả project, và có quyền truy cập dữ liệu xuất BigQuery cũng không đồng nghĩa với quyền quản trị Cloud Billing account.

### 2.1. Ba trách nhiệm thường bị nhầm

| Câu hỏi | Đối tượng / phạm vi quyết định | Người chịu trách nhiệm điển hình |
|---|---|---|
| Ai thanh toán cho tài nguyên? | Billing account và cấu hình payments liên quan | Tài chính / billing admin |
| Ai tạo ra chi phí? | Workload trong project, service, SKU, vùng, tài nguyên | Đội phát triển / vận hành |
| Chi phí được ghi cho trung tâm nào? | Quy tắc phân bổ nội bộ dựa trên project, nhãn, cost center và khoản dùng chung | FinOps + tài chính + chủ dịch vụ |

Project là điểm bắt đầu hữu ích để quy thuộc, nhưng một khoản **network egress**, phí hỗ trợ, tài nguyên chia sẻ hoặc khoản ở cấp billing account có thể không nằm gọn trong một project/nhóm theo cách doanh nghiệp muốn hạch toán.

## 3. IAM Cloud Billing: vai trò, phạm vi và quyền tối thiểu

Google Cloud cung cấp nhiều vai trò IAM chuyên biệt. Chọn vai trò theo **tác vụ cần thực hiện**, kiểm tra phạm vi tài nguyên hỗ trợ vai trò đó và các quyền đi kèm tại thời điểm cấp.

| Vai trò IAM | ID | Phạm vi và năng lực chính | Không nên dùng thay cho |
|---|---|---|---|
| Billing Account Administrator | `roles/billing.admin` | Quản trị rộng billing account, quyền tài khoản, cấu hình và thông tin chi phí | Vai trò xem báo cáo hằng ngày |
| Billing Account Costs Manager | `roles/billing.costsManager` | Xem chi phí, quản lý ngân sách và xuất **cost data**; không phải toàn quyền tài khoản | Quản lý phương thức thanh toán hoặc liên kết project |
| Billing Account Viewer | `roles/billing.viewer` | Đọc dữ liệu chi phí/giao dịch tài khoản; thích hợp đối soát | Sửa cấu hình billing và gán role |
| Project Billing Costs Manager | `roles/billing.projectCostsManager` | Hỗ trợ xem/phân tích dữ liệu billing có giới hạn theo các project đã được cấp quyền xem chi phí | Quyền xem chi phí toàn billing account |
| Billing Account User | `roles/billing.user` | Cho phép sử dụng billing account để liên kết project khi có quyền ở project thích hợp | Xem toàn bộ chi phí hoặc quản trị billing account |
| Project Billing Manager | `roles/billing.projectManager` | Quản lý việc gắn/bỏ gắn billing account cho project, kết hợp quyền billing account cần thiết | Quản lý VM, DB hoặc code ứng dụng |
| Billing Account Creator | `roles/billing.creator` | Cho phép tạo billing account loại được hỗ trợ ở phạm vi tổ chức | Quyền mặc định cho mọi kỹ sư |

**Đọc theo điều kiện, không theo tên gần giống:** để liên kết một project hiện có với billing account, người thực hiện thường cần **quyền ở cả project và billing account** (ví dụ `roles/billing.projectManager` trên project **và** `roles/billing.user` trên billing account đích). Chỉ một trong hai role có thể chưa đủ. Quyền mở/tạo project, chính sách tổ chức và trạng thái billing account cũng có thể ảnh hưởng.

Vai trò **Project Billing Costs Manager** cần kết hợp với quyền xem chi phí trên project tương ứng; chỉ gán role tại billing account chưa bảo đảm người dùng nhìn thấy chi phí mọi project. Tương tự, quyền xem trang billing không mặc nhiên cho phép thay đổi phương thức thanh toán.

> **Nguyên tắc:** Tránh dùng `roles/owner`, `roles/editor` hoặc `roles/billing.admin` chỉ để cho phép xem bảng chi phí. Chọn role có quyền nhỏ nhất đáp ứng công việc và rà soát lại định kỳ.

### 3.1. Ma trận phân tách nhiệm vụ (SoD)

Một tổ chức nhỏ có ba project `dev`, `prod`, `analytics`, cùng một billing account, có thể phân chia như sau:

| Nhóm | Quyền cần thiết | Phạm vi nên giới hạn | Việc không giao mặc định |
|---|---|---|---|
| **Billing admin** | Quản lý tài khoản và chính sách IAM billing | Billing account được phụ trách | Quyền deploy application nếu không cần |
| **Tài chính/kế toán** | Xem giao dịch, hóa đơn và chi phí để đối soát | Billing account; payments profile theo nghiệp vụ | Chỉnh VM/GKE/IAM kỹ thuật |
| **FinOps** | Xem xu hướng, tạo ngân sách, quản lý cost export khi được phân công | Billing account liên quan, dataset phân tích | Thay đổi phương thức thanh toán hoặc tài nguyên sản xuất |
| **Chủ dịch vụ/đội ứng dụng** | Xem chi phí của project mình; nhận cảnh báo ngân sách | Project được giao | Xem chi phí project khác và chứng từ thanh toán |
| **Nhóm phân tích dữ liệu** | Đọc view/dataset chi phí đã được giới hạn | Dataset/view BigQuery | IAM admin billing account hoặc toàn bộ payments |
| **Kiểm toán** | Quyền đọc trong thời gian kiểm tra | Báo cáo/chứng từ cần đối chiếu | Quyền ghi, đóng tài khoản hoặc gỡ liên kết project |

Các nhóm nên được cấp quyền thông qua **Google Groups** khi phù hợp, có người sở hữu nhóm và có quy trình phê duyệt. Nếu cần quyền cấp cao để xử lý sự cố, dùng cơ chế truy cập khẩn cấp có thời hạn và ghi dấu kiểm toán.

### 3.2. Quy trình cấp quyền có kiểm soát

1. **Mô tả nhu cầu:** người yêu cầu cần xem báo cáo, sửa budget, tạo export, liên kết project hay quản lý thanh toán?
2. **Xác định đối tượng:** billing account, project, BigQuery dataset và/hoặc payments profile.
3. **Chọn vai trò thấp nhất:** dùng bảng trên và đối chiếu danh sách permission chính thức, tránh chọn theo tên role suy đoán.
4. **Phê duyệt bởi chủ tài nguyên:** xác thực billing account ID, project ID, nhóm nhận quyền, thời hạn và mục đích.
5. **Cấp đúng scope:** trên trang **Billing → Account management / Permissions** hoặc IAM của tài nguyên thích hợp; tên menu có thể thay đổi.
6. **Xác minh:** người nhận thử đúng tác vụ đã được duyệt, kiểm tra chức năng không được phép vẫn bị giới hạn.
7. **Theo dõi và thu hồi:** xem lại thành viên, nhóm, IAM policy, audit log và quyền tạm thời theo kỳ.

Phân biệt **IAM cho cloud** và **quyền Google payments**. Một nhân viên cần sửa thẻ/địa chỉ thanh toán có thể phải được cấp quyền trong Google payments; gán một role kỹ thuật trên project không giải quyết nhu cầu đó.

## 4. Tình huống phân quyền: hai nhóm, một billing account

Giả sử công ty `ExampleCo` có:

- `project-web-prod`: Cloud Run chạy API và Cloud SQL chứa dữ liệu giao dịch.
- `project-data-batch`: BigQuery và jobs phân tích.
- `project-shared`: tài nguyên mạng, monitoring hoặc pipeline chung.
- Billing account `BA-EXAMPLE`: thanh toán cho cả ba project.

Nhóm tài chính cần tổng chi phí và chứng từ. Đội web chỉ cần biết chi phí `project-web-prod`. FinOps cần quản lý ngân sách và nhận dữ liệu chi phí để lập dashboard. Kỹ sư hạ tầng đôi khi cần chuyển project mới sang billing account.

**Thiết kế đề xuất:**

1. Tài chính: quyền đọc billing account theo nhu cầu; quyền payments riêng nếu xử lý chứng từ/thanh toán.
2. Đội web: quyền xem chi phí scoped tới `project-web-prod`, không cho xem tất cả project.
3. FinOps: vai trò quản lý cost/budgets trên billing account và quyền phù hợp trên BigQuery dataset; chỉ giao quyền export nếu cần vận hành pipeline.
4. Kỹ sư hạ tầng: quyền `Project Billing Manager` trên project được giao và `Billing Account User` trên billing account cần liên kết; thu hồi khi hết nhiệm vụ.
5. Billing admin: nhóm nhỏ được phê duyệt quản lý IAM và cấu hình account. Không cấp quyền admin cho tài khoản dịch vụ triển khai Cloud Run/GKE.

**Kiểm thử quyền:** người trong đội web đăng nhập và chỉ xem được chi phí phạm vi được phép; không thể chỉnh payments hoặc quyền IAM billing. Kế toán xem đủ dữ liệu đối soát; không thể dừng VM sản xuất. Kỹ sư hạ tầng kiểm tra trạng thái liên kết đúng project trước khi thay đổi.

## 5. Hiểu các khái niệm chi phí để đối soát đúng

### 5.1. Usage/charge period và billing/invoice period

**Thời điểm sử dụng** và **kỳ đưa chi phí vào hóa đơn** có thể khác nhau. Dữ liệu tính phí của một workload chạy vào cuối tháng có thể được hệ thống ghi nhận muộn hoặc nằm trong kỳ hóa đơn khác. Báo cáo theo ngày sử dụng hữu ích cho phân tích xu hướng; báo cáo theo **billing/invoice period** mới là điểm bắt đầu để đối chiếu tổng hóa đơn theo kỳ.

| Góc nhìn | Dùng để trả lời | Rủi ro nếu nhầm |
|---|---|---|
| Usage date / charge period | Workload phát sinh chi phí khi nào? | Tổng tháng có thể lệch tổng invoice của tháng |
| Billing period / invoice month | Khoản nào được ghi vào hóa đơn kỳ này? | Chưa phân tích tốt thời điểm workload thực sự chạy |
| Project / service / SKU | Ai và dịch vụ nào tạo chi phí? | Không phải mọi khoản đều quy về project |
| Invoice number | Chứng từ cụ thể nào được phát hành? | Một billing period có thể có nhiều invoice/chứng từ, tùy mô hình thanh toán |
| Gross cost, savings/credits, tax, adjustments | Tổng cuối kỳ được hình thành thế nào? | Lấy gross rồi coi là số phải thanh toán có thể sai |

**SKU** là đơn vị sản phẩm/giá cụ thể (ví dụ loại compute, dung lượng lưu trữ hoặc lưu lượng mạng). Khi điều tra bất thường, drill down từ **billing account → project → service → SKU → location/resource** nếu dữ liệu và quyền cho phép.

### 5.2. Các thành phần trên báo cáo tài chính

- **Usage cost / gross usage**: chi phí tiêu thụ trước một số khoản giảm trừ; cách biểu diễn tùy báo cáo.
- **Discount, credit, CUD, promotion**: giảm chi phí hoặc ghi có theo điều kiện; cần kiểm tra là khoản nào đã tính vào số tổng và khoản nào là bản ghi riêng.
- **Tax, surcharge, adjustment**: có thể xuất hiện ở **cấp invoice**, không phân bổ sẵn xuống project.
- **Payment / transaction**: việc thanh toán tiền hoặc điều chỉnh số dư không nhất thiết đồng nghĩa với chi phí tiêu thụ kỳ đó.
- **Currency**: dùng đơn vị tiền ghi trên billing account; khi tổng hợp nhiều tài khoản khác tiền tệ phải có quy tắc tỷ giá và ngày quy đổi được phê duyệt.

Ví dụ **giả định**, trong một kỳ hóa đơn chỉ có các khoản sau:

| Khoản mục | Giá trị minh họa (USD) |
|---|---:|
| Compute Engine / Cloud Run | 120,00 |
| Cloud SQL | 240,00 |
| Cloud Storage | 40,00 |
| Network egress | 30,00 |
| **Tổng usage trước giảm trừ** | **430,00** |
| Credits/discounts áp dụng | -35,00 |
| **Usage sau giảm trừ** | **395,00** |
| Thuế giả định | +39,50 |
| Adjustment giả định | -5,00 |
| **Tổng chứng từ minh họa** | **429,50** |

Đây là bài tập số học để hiểu **thành phần đối soát**, không phải biểu thuế hay giá dịch vụ thực tế. Chỉ cộng những khoản có trong chứng từ và theo cách nguồn dữ liệu định nghĩa; đừng trừ credit lần thứ hai nếu báo cáo đã hiển thị chi phí ròng.

## 6. Các công cụ Google Cloud cho phân tích và đối soát

### 6.1. Cloud Billing Reports

Trong Google Cloud Console, chọn đúng **Cloud Billing account** rồi vào khu vực **Billing → Reports**. Tùy quyền và giao diện hiện hành, bạn có thể:

- Chọn kỳ theo **charge period/usage date** hoặc **billing period/invoice month**.
- Nhóm theo project, service, SKU hoặc chiều phân tích được hỗ trợ.
- Lọc project, service, label hoặc các điều kiện thích hợp.
- Kiểm tra xu hướng chi phí và khoản tiết kiệm/credit theo phạm vi đã chọn.

Để đối soát hóa đơn, hãy bắt đầu với **billing period đầy đủ**, **tất cả project, service, SKU và khoản giảm trừ** phù hợp; sau đó mới lọc để truy nguyên. Một báo cáo chỉ lọc `project-web-prod` không thể được kỳ vọng khớp tổng chứng từ của billing account.

### 6.2. Cost table và chứng từ

**Cost table report** phục vụ xem chi phí theo invoice, có thể xuất **CSV** để kiểm tra. **Billing Reports** ở chế độ billing period có thể hiển thị tổng hợp chi phí của kỳ đó; nếu kỳ có nhiều invoice, tổng báo cáo có thể là tổng gộp và **không** bằng riêng một invoice.

Đối với kỳ có thuế, credit cấp invoice, khoản điều chỉnh hoặc phụ phí, cần mở đúng báo cáo theo kỳ hóa đơn và xem đủ các dòng liên quan. Chế độ theo thời điểm sử dụng hoặc các bộ lọc project/service có thể không hiển thị đầy đủ thuế và adjustment ở cấp invoice.

### 6.3. Billing export sang BigQuery

Khi cần báo cáo nhiều tháng, phân bổ theo team hay tự động hóa FinOps, có thể bật **Cloud Billing export to BigQuery**:

| Loại export | Mục đích | Lưu ý |
|---|---|---|
| **Standard usage cost** | Xu hướng theo billing account, project, service, SKU, location, labels, credits | Nhiều tình huống showback có thể bắt đầu ở đây |
| **Detailed usage cost** | Tìm nguồn chi phí theo resource ở những dịch vụ hỗ trợ | Dữ liệu lớn hơn, không phải mọi SKU đều có đủ resource ID |
| **Pricing data** | Phân tích danh mục giá thực tế theo tài khoản | Có quyền riêng để cấu hình/đọc, không thay cho hóa đơn |
| **FOCUS usage cost** (tùy tính sẵn có và trạng thái phát hành) | Phân tích theo chuẩn FinOps Open Cost and Usage Specification | Kiểm tra trạng thái hỗ trợ và quy tắc dữ liệu tại thời điểm triển khai |

Export **không phải dữ liệu thời gian thực**. Có độ trễ, hạn chế backfill và khác biệt theo vị trí dataset; dữ liệu chỉ bắt đầu được thu thập theo chính sách của từng loại export. Hãy bật sớm nếu doanh nghiệp cần lịch sử lâu dài, ghi rõ thời điểm bắt đầu và giám sát pipeline.

**Tách quyền:** quyền cấu hình export trên billing account khác quyền tạo/đọc dataset BigQuery. Nên dùng một project/dataset dành cho FinOps, thiết kế quyền đọc giới hạn, audit, retention, chia sẻ view có kiểm soát và theo dõi phí lưu trữ/truy vấn BigQuery.

### 6.4. Theo dõi ngân sách và bất thường

**Alerts-only budget** cho biết chi phí thực tế hoặc dự báo đang tiến gần ngưỡng; mặc định **không tự dừng dịch vụ hoặc chặn phát sinh hóa đơn**. Một số trường hợp/dịch vụ có thể hỗ trợ **spend cap budget** theo điều kiện riêng; cần kiểm tra tính khả dụng, hành vi và ảnh hưởng workload trước khi xem đó là giới hạn cứng.

Ví dụ, budget 1.000 USD/tháng cho production có thể cảnh báo khi đạt 50%, 80%, 100% và theo dự báo vượt 110%. Đây chỉ là các **mức minh họa**. Quy trình phản ứng cần người nhận và người xử lý rõ ràng, kết hợp báo cáo theo SKU, anomaly detection và kiểm tra tài nguyên ít sử dụng.

## 7. Quy trình đối soát chi phí cuối kỳ

Đối soát có hai mục tiêu tách biệt:

1. **Đối soát tài chính:** tổng chứng từ và giao dịch hợp lệ được giải thích bởi các khoản trên báo cáo billing.
2. **Đối soát quản trị:** khoản chi phí đó được quy về project, đội, sản phẩm và cost center theo một chính sách nhất quán.

Một khoản có thể đã được kế toán xác nhận **đúng hóa đơn** nhưng vẫn chưa được phân bổ **đúng đội**.

~~~mermaid
flowchart TD
    A["Chọn billing account + kỳ invoice"] --> B["Lấy invoice/chứng từ + Cost table"]
    B --> C["Đối chiếu tổng: usage, credits, taxes, adjustments"]
    C --> D{"Chênh lệch?"}
    D -->|Có| E["Kiểm tra filter, invoice number, timing, loại phí, currency"]
    E --> C
    D -->|Không / đã giải thích| F["Phân bổ theo project, service, nhãn"]
    F --> G["Xác định chi phí chung và chưa gán"]
    G --> H["Áp dụng quy tắc showback/chargeback"]
    H --> I["Duyệt, lưu bằng chứng, khóa số liệu báo cáo"]
~~~

### Bước 1. Chốt nguồn dữ liệu và phạm vi

Ghi rõ **billing account ID, tên tổ chức, đơn vị tiền, billing period**, danh sách invoice/chứng từ và thời điểm chốt dữ liệu. Thống nhất mục tiêu: đối chiếu **tổng kỳ**, **từng invoice** hay **từng project**. Chọn quyền xem phù hợp; không chép số tài khoản/thông tin thanh toán nhạy cảm vào ticket kỹ thuật.

### Bước 2. Truy xuất đúng kỳ hóa đơn

Trong Billing Reports/Cost table:

- Chọn chế độ kỳ hóa đơn, bao gồm **mọi invoice** nếu đối chiếu tổng tháng, hoặc chọn đúng invoice nếu đối chiếu từng chứng từ.
- Đảm bảo bộ lọc project, service, SKU và savings **không vô tình loại khoản phí**.
- Ghi lại usage subtotal, các khoản savings/credits, tax, adjustment, surcharge và tổng sau tất cả thành phần.
- Với khoản phí tài khoản không gắn project, giữ trong danh mục **shared/unallocated** thay vì tự gán nhầm cho project lớn nhất.

### Bước 3. Điều tra chênh lệch

| Chênh lệch xuất hiện | Khả năng cần kiểm tra | Cách xử lý |
|---|---|---|
| Usage month lệch invoice month | Ghi nhận usage muộn hoặc kỳ hóa đơn khác | Đối chiếu theo invoice period; dùng charge date để giải thích |
| Chỉ ra được tổng project, thiếu tổng tài khoản | Tax, adjustment, phí chung, khoản không có project | Giữ nhóm unallocated và so với Cost table đủ bộ lọc |
| Net cost không khớp | Credits đã trừ hai lần, bỏ CUD/promotion hoặc chênh cách biểu diễn | Tách gross, credit, net theo nguồn; không trộn cách tính |
| Kỳ có hơn một invoice | Báo cáo tháng cộng nhiều chứng từ | So từng invoice number rồi cộng kiểm tra |
| BigQuery mới có một phần dữ liệu | Export trễ, backfill chưa xong, thay dataset hoặc mới bật | Đợi pipeline cập nhật theo SLA nội bộ, đối soát với Console |
| Chi phí không thuộc đội dự kiến | Sai project, thiếu label, tài nguyên chung, chuyển project | Điều tra owner/nhật ký thay đổi, xác nhận quy tắc phân bổ |
| Lệch tiền tệ hoặc làm tròn | Nhiều currency, tỷ giá, làm tròn từng dòng | Không cộng đơn vị tiền khác nhau; công bố quy tắc quy đổi |

**Đừng xóa khoản chênh bằng cách đặt một dòng “khác” vô thời hạn.** Dòng chênh cần lý do, người phụ trách, trạng thái và bằng chứng. Khoản chưa rõ thì **chưa quy thuộc**, không tự suy đoán nguồn.

### Bước 4. Phân bổ theo trung tâm chi phí

Quy tắc ưu tiên thường là:

1. **Project riêng cho sản phẩm/đội:** có owner và cost center rõ.
2. **Label/tag hữu ích:** chẳng hạn `team`, `env`, `app`, `cost-center`, nếu dịch vụ hỗ trợ và dữ liệu export có trường tương ứng.
3. **Ánh xạ service/SKU/resource:** dùng khi tài nguyên hoặc phí không có label nhưng có danh mục chủ sở hữu tin cậy.
4. **Chi phí chung:** phân bổ theo thước đo được phê duyệt, ví dụ tỉ lệ usage, số request hoặc mức chia cố định.
5. **Chưa phân bổ:** tạo danh sách ngoại lệ để hoàn thiện metadata và chính sách.

Label mới gán **không nhất thiết gán ngược** cho các chi phí lịch sử. Không nên giả định mọi loại phí hỗ trợ truy nguyên đến từng resource hoặc label. Hãy ghi rõ tỷ lệ “unallocated” như một KPI chất lượng dữ liệu FinOps.

### Bước 5. Phê duyệt và lưu dấu vết

Tách người **lập bảng phân bổ**, người **duyệt số liệu** và người **quản trị quyền billing** nếu quy mô tổ chức cho phép. Lưu phiên bản số liệu, kỳ chốt, link nguồn được kiểm soát, bộ lọc đã dùng, truy vấn BigQuery đã chạy, quy tắc phân bổ và các ngoại lệ tồn đọng.

Khi xuất CSV hoặc bảng đối soát, áp dụng quyền chỉ xem cho người liên quan; hạn chế chia sẻ thông tin invoice, payments profile và dữ liệu cost của project không thuộc phạm vi người nhận.

## 8. Ví dụ phân bổ chi phí dùng chung

Giả sử ba project sản phẩm có chi phí trực tiếp sau giảm trừ (chưa thuế) như sau:

| Nhóm | Chi phí trực tiếp (USD) | Tỉ lệ tiêu thụ tài nguyên chung |
|---|---:|---:|
| Team A — API | 500 | 60% |
| Team B — Batch | 300 | 40% |
| **Tổng** | **800** | **100%** |

Một project nền tảng dùng chung tốn thêm **200 USD**. Chính sách nội bộ phê duyệt phân bổ theo tỉ lệ giờ CPU thực đo ở hai đội. Khi đó:

- Team A nhận **200 × 60% = 120 USD**, tổng showback **620 USD**.
- Team B nhận **200 × 40% = 80 USD**, tổng showback **380 USD**.
- Tổng sau phân bổ vẫn bằng **1.000 USD**. Không được tính thêm 200 USD cho project shared sau khi đã phân bổ cho hai đội, nếu không sẽ đếm kép.

Đây là **showback**: các đội xem phần chi phí quy thuộc. **Chargeback** chỉ xảy ra khi doanh nghiệp dùng kết quả đó để ghi nhận/chuyển chi phí thực sự vào ngân sách nội bộ theo chính sách tài chính. Hai khái niệm có thể dùng chung dữ liệu nhưng quy trình phê duyệt khác nhau.

Nếu chưa có CPU-hour đáng tin cậy, đừng tự tạo tỉ lệ 60/40. Có thể dùng chia đều như một **quy tắc tạm thời đã được phê duyệt**, công bố rõ sai số, rồi thay bằng cơ chế đo thực tế sau.

## 9. BigQuery: truy vấn minh họa chi phí theo invoice month

Giả sử billing export kiểu **Standard usage cost** đã được bật và dataset có bảng `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>`. Truy vấn minh họa dưới đây tổng hợp chi phí theo **project**, **service** và **invoice month**.

~~~sql
-- Chỉ là ví dụ: thay BILLING_DATASET và BILLING_ACCOUNT_ID.
-- Chọn tháng YYYYMM đúng với kỳ hóa đơn cần phân tích.
WITH usage_cost AS (
  SELECT
    invoice.month AS invoice_month,
    COALESCE(project.id, 'UNALLOCATED') AS project_id,
    service.description AS service_name,
    cost AS gross_cost,
    COALESCE((
      SELECT SUM(c.amount)
      FROM UNNEST(credits) AS c
    ), 0) AS credit_amount,
    currency
  FROM `billing-project.BILLING_DATASET.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE invoice.month = '202611'
)
SELECT
  invoice_month,
  currency,
  project_id,
  service_name,
  ROUND(SUM(gross_cost), 2) AS gross_cost,
  ROUND(SUM(credit_amount), 2) AS credits,
  ROUND(SUM(gross_cost + credit_amount), 2) AS net_usage_cost
FROM usage_cost
GROUP BY invoice_month, currency, project_id, service_name
ORDER BY net_usage_cost DESC;
~~~

**Cách đọc:**

- `invoice.month` có định dạng `YYYYMM`, khác với việc lọc theo ngày `usage_start_time`.
- Trường `cost` và các dòng trong mảng `credits` có cách biểu diễn riêng. Credits thường là giá trị âm; cần quan sát dữ liệu thực tế trước khi xây dựng công thức tài chính.
- Các dòng không có `project.id` vẫn quan trọng, nên được giữ thành `UNALLOCATED`.
- `currency` xuất hiện trong nhóm kết quả nhằm tránh gộp số tiền khác đơn vị.
- Truy vấn tổng hợp usage/credits **không đủ để bảo đảm khớp chứng từ** khi có thuế, adjustment, phí cấp invoice, nhiều invoice hay chênh độ trễ export. Sử dụng Cost table và invoice làm nguồn đối chiếu cuối cùng.
- Dataset BigQuery có phí lưu trữ/truy vấn tùy cấu hình; cần xem lượng dữ liệu quét, phân vùng và phạm vi dữ liệu truy cập.

**Lưu ý kỹ thuật:** Tên bảng xuất có cấu trúc phụ thuộc loại export và billing account; dấu gạch nối trong project ID được bao bằng dấu backtick của BigQuery ở ví dụ. Không chép nguyên mã `BILLING_ACCOUNT_ID` hoặc `202611` để dùng cho môi trường thật.

### 9.1. Khi nào dùng Detailed export?

Nếu giá tăng ở **Compute Engine** hoặc **GKE**, dữ liệu chi tiết có thể giúp tìm resource, cluster hoặc thông tin phân bổ khi sản phẩm hỗ trợ. Nhưng resource-level coverage **không hoàn toàn giống nhau giữa các dịch vụ**. Với GKE, cần kiểm tra yêu cầu bật **cost allocation** để nhận một số trường chi phí workload/cluster.

Hãy dùng **Standard export** cho xu hướng trên diện rộng và **Detailed export** để đào sâu khu vực phát sinh bất thường. Với dashboard chia sẻ rộng, nên tạo BigQuery view đã giới hạn project và trường cần thiết, thay vì cho mọi đội quyền đọc bảng raw toàn tài khoản.

## 10. Tình huống điều tra: phí Cloud Run và Cloud SQL tăng bất thường

Một tháng, đội sản phẩm nhận thấy chi phí `project-web-prod` cao hơn dự toán 30%. Kế toán xác nhận hóa đơn tổng tài khoản đã khớp, nhưng FinOps cần xác định nguyên nhân để phân bổ và xử lý.

**Các bước hợp lý:**

1. Chọn đúng billing account và project; lọc kỳ **charge period** để biết ngày biến động, đồng thời giữ báo cáo **invoice period** cho đối soát cuối kỳ.
2. Nhóm theo **service/SKU**: kiểm tra Cloud Run compute, Cloud SQL instance/storage/backup và network egress.
3. So sánh thay đổi triển khai: min instances của Cloud Run, concurrency, instance count, cấu hình Cloud SQL, tăng dung lượng backup, request và dữ liệu truyền ra ngoài.
4. Xem Cloud Monitoring/Logging: traffic, latency, error rate, DB connections, CPU/storage; đối chiếu mốc deploy và chiến dịch.
5. Nếu số liệu gốc khớp, phân loại **chi phí do tăng workload hợp lệ** và **chi phí do cấu hình/không hiệu quả**; tạo hành động khắc phục có owner.
6. Cập nhật forecast/budget alert và đưa ảnh hưởng vào báo cáo showback của đội; giữ dấu vết nếu cần giải thích cho kế toán.

**Không quy mọi khoản tăng ở Cloud Run thành “autoscaling lỗi”.** Phí có thể đến từ truy vấn Cloud SQL nặng, backup, kết nối mạng hoặc tài nguyên chung. Điều tra theo SKU và metric thực tế.

## 11. Quy trình vận hành tài chính hằng tháng

| Thời điểm | Công việc | Người chủ trì | Kết quả đầu ra |
|---|---|---|---|
| Hằng ngày/tuần | Theo dõi budget alert, anomaly, thay đổi SKU lớn | FinOps + chủ dịch vụ | Ticket điều tra, dự báo |
| Cuối kỳ / khi chứng từ sẵn có | Thu thập invoice, Cost table, giao dịch tương ứng | Tài chính | Bảng đối soát chứng từ |
| Sau khi export đủ dữ liệu | Tổng hợp theo project/label, phân bổ shared | FinOps | Bảng showback tạm |
| Trước khi khóa số liệu | Xác nhận credit, thuế, adjustment, chênh lệch, ngoại lệ | Tài chính + FinOps | Bảng chốt kỳ, log giải trình |
| Định kỳ | Rà IAM, chủ project, nhãn và ngân sách | Billing admin + chủ dịch vụ | Báo cáo quyền và cải tiến phân bổ |

**Kiểm soát thay đổi:** thay đổi billing account của project hoặc phương thức thanh toán có thể gây gián đoạn vận hành/khác nguồn ghi nhận hóa đơn. Thực hiện theo quy trình được duyệt, ghi trước/sau và phối hợp nhóm tài chính.

### 11.1. Bộ dữ liệu cần lưu trong một kỳ đối soát

Mỗi kỳ nên có một bản ghi quản trị gồm:

- Billing account (mã nội bộ hoặc ID được kiểm soát), kỳ hóa đơn, đơn vị tiền và danh sách invoice.
- Tổng usage trước/ sau credits theo định nghĩa rõ ràng, thuế, adjustments và tổng chứng từ.
- Số tiền đã phân bổ trực tiếp, phân bổ dùng chung, chưa phân bổ và quy tắc áp dụng.
- Tệp CSV/bảng export hoặc link kiểm soát truy cập tới nguồn; thời điểm dữ liệu được chốt.
- Danh sách chênh lệch, giả định, người xử lý, ngày xác nhận và người phê duyệt.

Không chia sẻ bản sao invoice hoặc thông tin payments profile trong những kênh không được doanh nghiệp phê duyệt.

## 12. Các lỗi thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Cho mọi kỹ sư `roles/billing.admin` để xem chi phí | Vượt quyền, khó kiểm toán | Sử dụng viewer/project-scoped cost role |
| Nghĩ quyền Project Owner bao gồm quyền quản trị mọi billing account | Sai ranh giới IAM | Kiểm tra cả project IAM và billing account IAM |
| Dùng Project Billing Manager mà không có quyền trên account đích | Không liên kết được project | Kiểm tra bộ quyền ở cả hai tài nguyên |
| Cho đội ứng dụng truy cập raw billing dataset toàn công ty | Lộ chi phí của các đội khác | Dùng view/dataset scoped và IAM phù hợp |
| So invoice month với tổng usage date cùng tháng | Chênh kỳ và hiểu sai hóa đơn | Tách hai cách xem, ghi rõ period |
| Cộng credits hai lần hoặc bỏ qua tax/adjustment | Sai tổng tài chính | Phân biệt gross, net, invoice-level charges |
| Áp label mới và coi dữ liệu lịch sử tự được cập nhật | Sai showback | Ghi rõ ngày hiệu lực, giữ unallocated |
| Bỏ qua khoản không gắn project | Tổng phân bổ không khớp | Theo dõi shared/unallocated đến khi xử lý |
| Dùng alerts-only budget như “van chặn chi phí” | Vượt ngân sách | Thiết kế phản ứng, kiểm tra spend cap nếu được hỗ trợ |
| Coi BigQuery export là hóa đơn cuối cùng | Bỏ sót thuế, adjustment hoặc dữ liệu trễ | Chốt cuối dựa trên invoice/Cost table |

## 13. Bài thực hành theo vai trò (không cần thay đổi billing thật)

Một tổ chức đào tạo có ba project:

| Project | Chủ sở hữu | Dịch vụ | Chi phí kỳ giả định |
|---|---|---|---:|
| `academy-web` | Team Web | Cloud Run, Cloud SQL | 360 USD |
| `academy-data` | Team Data | BigQuery, Cloud Storage | 240 USD |
| `academy-shared` | Platform | Network/Monitoring | 100 USD |

Có thêm **20 USD credit**, **70 USD thuế giả định** và **10 USD adjustment tăng chi phí**. Chính sách nội bộ yêu cầu phân bổ project shared theo **70% Team Web / 30% Team Data**, còn thuế và adjustment do tài chính theo dõi tách khỏi showback kỹ thuật.

**Câu hỏi:**

1. Tổng chi phí trực tiếp, chi phí sau credits và tổng hóa đơn minh họa là bao nhiêu?
2. Mỗi team nhận bao nhiêu phần chi phí **shared**? Tổng showback kỹ thuật trước xử lý credits là bao nhiêu cho mỗi team?
3. Đội Web chỉ cần xem chi phí `academy-web`. Tại sao không cấp Billing Account Administrator?
4. Một nhân viên cần liên kết một project mới vào billing account. Hãy xác định hai phạm vi quyền phải kiểm tra.
5. Tài chính thấy dữ liệu theo `usage date` lệch invoice. Nêu ít nhất ba nguyên nhân có thể.
6. Nếu FinOps bật Standard export hôm nay, có được giả định mọi dữ liệu lịch sử sẽ tự xuất đầy đủ hay không?
7. Nếu budget gửi cảnh báo 100%, có thể kết luận mọi dịch vụ tự dừng không? Giải thích.

**Gợi ý kiểm tra:**

- Chi phí sử dụng trực tiếp và chung trước giảm trừ: **700 USD**; trừ 20 USD credit còn **680 USD**; cộng 70 USD thuế và 10 USD adjustment thành **760 USD** theo dữ kiện giả định.
- Phần shared: **Team Web 70 USD**, **Team Data 30 USD**. Showback kỹ thuật trước credits/thuế/adjustment: **Team Web 430 USD**, **Team Data 270 USD**; tổng vẫn là **700 USD**.
- Các câu còn lại cần nhắc tới quyền tối thiểu; IAM riêng ở project/account; độ trễ ghi nhận/điều chỉnh kỳ; giới hạn backfill; khác biệt giữa cảnh báo và spend cap có điều kiện.

## 14. Checklist quản trị billing và đối soát

- [ ] Có danh sách billing account, payments profile, project được gắn và chủ sở hữu rõ ràng.
- [ ] Đã phân quyền theo đúng scope: billing account, project, dataset, payments profile.
- [ ] Đã tách quyền xem, sửa budget/export, liên kết project và quản trị thanh toán.
- [ ] Có nhóm nhận budget alert, người xử lý bất thường và hạn mức vận hành được duyệt.
- [ ] Đã thống nhất kỳ đối soát, đơn vị tiền, invoice number và các khoản phải cộng/trừ.
- [ ] Đã kiểm tra credit, discount, thuế, adjustment và dòng không gắn project.
- [ ] Có chính sách phân bổ chi phí shared, nhãn, cost center và xử lý unallocated.
- [ ] Đã ghi thời điểm bật billing export, giới hạn dữ liệu và quyền truy cập dataset.
- [ ] Có lịch chốt kỳ, người lập, người duyệt, bằng chứng và quy trình xử lý chênh lệch.

## 15. Tài liệu tham khảo chính thức

Các quyền IAM, khả năng của budget và cấu trúc export có thể thay đổi. Khi triển khai trên Google Cloud thật, kiểm tra phiên bản tài liệu và quyền hiện hành:

- [Cloud Billing access control and permissions](https://docs.cloud.google.com/billing/docs/how-to/billing-access)
- [Cloud Billing roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/billing)
- [Billing reports: View the charges on your invoices](https://docs.cloud.google.com/billing/docs/how-to/reports/charges-on-invoices)
- [Create, edit, or delete budgets and budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Export Cloud Billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Set up Cloud Billing data export to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)
- [Understand the Cloud Billing data tables in BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables)

**Điểm cần nhớ:** Đối soát Google Cloud phải kết nối **quyền truy cập**, **số liệu sử dụng**, **kỳ hóa đơn** và **quy tắc phân bổ nội bộ**. Khi mỗi khoản chi phí đều có nguồn, phạm vi, người phụ trách và cách giải thích rõ ràng, đội ngũ có thể vừa bảo vệ tài nguyên vừa theo dõi độ tin cậy và chi phí trong suốt quá trình triển khai dịch vụ.
