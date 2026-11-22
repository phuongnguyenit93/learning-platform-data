# Cloud Billing account và liên kết project

Trong Google Cloud, tạo được một **project** chưa có nghĩa project đã sẵn sàng dùng các dịch vụ có tính phí. Để hệ thống triển khai Compute Engine, Google Kubernetes Engine (GKE), Cloud Run, Cloud Storage, cơ sở dữ liệu và các thành phần mạng hoạt động đúng, người quản trị phải hiểu ai chịu trách nhiệm thanh toán, project được liên kết với tài khoản nào và ai được phép thay đổi liên kết đó.

Bài học thuộc chương **Thanh toán và ngân sách** của module **CLOUD_PROVIDERS_GCP**. Đây là nền tảng cho các bước quản lý chi phí, đặt ngân sách và cảnh báo, bảo vệ tài nguyên bằng IAM, cũng như vận hành hệ thống tin cậy. Bạn sẽ biết cách phân biệt **Cloud Billing account** với **Google Cloud project**, liên kết và kiểm tra trạng thái thanh toán, quản lý quyền, chuyển tài khoản thanh toán và xử lý các rủi ro thường gặp.

## 1. Cloud Billing account là gì?

**Cloud Billing account** là tài khoản ghi nhận và thanh toán chi phí sử dụng các dịch vụ Google Cloud của những project được liên kết với nó. Đây là thực thể quản lý thanh toán và chi phí, không phải một máy chủ, một vùng triển khai hay một thư mục chứa tài nguyên ứng dụng.

Để hiểu đúng mô hình, cần phân biệt ba thành phần:

| Thành phần | Chức năng chính | Ví dụ |
| --- | --- | --- |
| **Google Cloud project** | Chứa, định danh và quản trị tài nguyên; là phạm vi của nhiều API, IAM, quota, log và chi phí. | Project production chạy Cloud Run, Cloud SQL và Cloud Storage. |
| **Cloud Billing account** | Xác định tài khoản chịu chi phí sử dụng từ các project được liên kết; cung cấp báo cáo, ngân sách và cấu hình thanh toán liên quan. | Tài khoản thanh toán của một doanh nghiệp, chịu chi phí của ba project. |
| **Google payments profile** | Lưu các thông tin thanh toán như thông tin bên thanh toán và phương thức thanh toán theo mô hình tài khoản. | Thông tin doanh nghiệp, địa chỉ và phương thức thanh toán gắn với Cloud Billing account. |

Cloud Billing account phục vụ chi phí của Google Cloud và các sản phẩm phù hợp dùng chung Cloud Billing. Tài khoản thanh toán Google Workspace là hệ thống riêng; không nên nhầm hai loại tài khoản.

### 1.1. Quan hệ giữa project và Cloud Billing account

- **Một Cloud Billing account có thể liên kết với nhiều project.** Ví dụ, project phát triển, kiểm thử và production cùng dùng một tài khoản thanh toán của công ty.
- **Tại một thời điểm, một project chỉ liên kết với tối đa một Cloud Billing account.** Muốn đổi bên chịu phí, bạn thay liên kết sang một tài khoản khác.
- **Cloud Billing account không thay thế project hoặc resource hierarchy.** Organization, folder và project vẫn là các thành phần quản trị tài nguyên; liên kết Billing là quan hệ chịu phí.
- **Liên kết thanh toán không tự cấp quyền thao tác lên ứng dụng.** Người được phép sử dụng tài khoản Billing để liên kết project không mặc nhiên được đọc database, sửa VM hay triển khai Cloud Run.

~~~mermaid
flowchart TB
    O["Organization / Folder"] --> P1["Project dev"]
    O --> P2["Project staging"]
    O --> P3["Project production"]
    B["Cloud Billing account<br/>BILLING-TEAM"] -. "Chi trả chi phí" .-> P1
    B -. "Chi trả chi phí" .-> P2
    B -. "Chi trả chi phí" .-> P3
    P1 --> R1["Tài nguyên dev"]
    P2 --> R2["Tài nguyên staging"]
    P3 --> R3["Tài nguyên production"]
~~~

Sơ đồ biểu thị quan hệ thanh toán cho ba project, không có nghĩa mọi tài nguyên bên trong project dùng chung IAM, VPC hoặc region. Cấu trúc project và quyền truy cập vẫn phải được thiết kế riêng.

### 1.2. Khi nào billing được bật?

Một project được xem là **billing enabled** khi có đủ **hai điều kiện**:

1. Project đang liên kết với một Cloud Billing account.
2. Cloud Billing account đó đang **hoạt động hợp lệ** (active, không bị đóng hoặc tạm ngưng).

Chỉ có một mã Billing account trong cấu hình là chưa đủ để kết luận project dùng dịch vụ bình thường. Nếu account đã đóng hoặc bị tạm ngừng, project có thể bị ảnh hưởng như trường hợp thanh toán bị vô hiệu hóa. Theo hướng dẫn hiện hành của Google Cloud, việc sử dụng các dịch vụ Google Cloud trong project yêu cầu liên kết với tài khoản Billing đang hoạt động, kể cả khi chỉ dùng các dịch vụ có mức sử dụng miễn phí.

**Phân biệt các trạng thái:**

| Trạng thái | Ý nghĩa | Hệ quả cần lưu ý |
| --- | --- | --- |
| Project chưa liên kết Billing account | Không có tài khoản chịu phí cho project. | Không đủ điều kiện vận hành các dịch vụ yêu cầu billing. |
| Project liên kết account đang active | Liên kết và trạng thái tài khoản đều hợp lệ. | Billing được bật; chi phí sử dụng có thể phát sinh theo sản phẩm và mức tiêu thụ. |
| Project liên kết account đã đóng/tạm ngưng | Có liên kết nhưng tài khoản không hoạt động hợp lệ. | Dịch vụ có thể bị dừng, truy cập tài nguyên bị ảnh hưởng. |
| Project được chuyển sang account active khác | Bên chịu chi phí của project được cập nhật. | Chi phí phát sinh sau chuyển liên kết được ghi nhận vào account mới, theo quá trình ghi nhận sử dụng. |

Một dịch vụ có giá sử dụng bằng 0 ở một mức nhất định không đồng nghĩa có thể bỏ qua bước thiết lập Cloud Billing account. Ngược lại, **bật billing không đồng nghĩa sẽ bị tính một khoản phí cố định ngay lập tức**: phí thực tế còn phụ thuộc sản phẩm, cấu hình, mức sử dụng và chính sách giá.

## 2. Cloud Billing account được tạo và quản lý ra sao?

Trước khi liên kết project, đội ngũ cần có một Cloud Billing account phù hợp với đơn vị chịu thanh toán. Tài khoản có **Billing account ID** riêng, khác với **Project ID** và **Project number**. Tên hiển thị có thể mang tính mô tả, nhưng khi thực hiện thao tác kỹ thuật phải kiểm tra chính xác ID để tránh gắn nhầm.

Thông thường, người có trách nhiệm thanh toán tạo tài khoản qua **Google Cloud Console → Billing**, chọn cấu hình thanh toán và hồ sơ thanh toán phù hợp. Tài khoản có thể thuộc mô hình **self-serve** (thanh toán tự động theo phương thức lưu trên hồ sơ thanh toán) hoặc **invoiced** (xuất hóa đơn định kỳ nếu được Google chấp thuận). Không phải mọi tổ chức đều có cùng hình thức thanh toán; điều kiện phụ thuộc quốc gia, pháp nhân và thỏa thuận thương mại.

Những thông tin cần xác định sớm:

1. **Bên chịu phí:** pháp nhân, nhóm hoặc đơn vị ngân sách chịu trách nhiệm cho tài khoản.
2. **Hình thức và hồ sơ thanh toán:** phương thức thanh toán, thông tin hóa đơn, quốc gia và loại tiền tệ áp dụng.
3. **Người quản trị Billing:** ai có quyền quản lý thông tin thanh toán, cấp quyền và xem báo cáo chi phí.
4. **Quy ước liên kết project:** project nào được phép sử dụng tài khoản này, ai duyệt khi tạo project mới hoặc đổi tài khoản.
5. **Ngân sách và cảnh báo:** cách theo dõi tiêu thụ từ sớm, nhất là với project production, thử nghiệm và các công việc dùng tài nguyên lớn.

Không nên giả định các thông tin như quốc gia thanh toán, đồng tiền hay kiểu tài khoản luôn thay đổi tùy ý sau khi tạo. Khi cần điều chỉnh thông tin thương mại quan trọng, hãy đối chiếu hướng dẫn Cloud Billing hiện hành và quy trình tài chính của tổ chức.

### 2.1. Một hay nhiều Billing account cho doanh nghiệp?

**Một tài khoản thanh toán cho nhiều project** giúp quản lý thanh toán tập trung. Đây là cách phù hợp khi cùng một đơn vị trả phí cho dev, staging, production và muốn tách chi phí bằng bộ lọc project hoặc nhãn.

**Nhiều tài khoản thanh toán** có thể phù hợp khi các pháp nhân, đơn vị nhận hóa đơn hoặc quy trình tài chính phải tách biệt. Tuy nhiên, tạo nhiều tài khoản hơn đồng nghĩa cần quản lý thêm quyền truy cập, báo cáo, ngân sách và quy trình di chuyển project. Quyết định nên dựa trên yêu cầu tài chính và quản trị thực tế.

Không cần tạo tài khoản Billing riêng cho từng project chỉ để biết project nào tốn nhiều tiền: Cloud Billing có khả năng xem và phân bổ chi phí theo project, dịch vụ và các chiều dữ liệu được hỗ trợ.

## 3. Quyền IAM để liên kết project

Thay đổi liên kết Billing là thao tác tác động đến trách nhiệm thanh toán và khả năng hoạt động của hệ thống. Người thực hiện cần có quyền ở **hai phía**: project cần liên kết và Cloud Billing account đích. Chỉ là Project Editor hoặc có quyền xem Billing chưa chắc thực hiện được.

| Vai trò IAM | Phạm vi gán thường gặp | Chức năng liên quan |
| --- | --- | --- |
| **Billing Account Administrator** — roles/billing.admin | Billing account hoặc phạm vi tổ chức thích hợp | Quản trị tài khoản Billing và quyền liên quan; là vai trò có đặc quyền rộng. |
| **Billing Account User** — roles/billing.user | Billing account | Cho phép sử dụng Billing account để gắn project khi có thêm quyền cần thiết ở project. |
| **Billing Account Viewer** — roles/billing.viewer | Billing account | Xem thông tin Billing account và các liên kết trong phạm vi cho phép. |
| **Project Billing Manager** — roles/billing.projectManager | Project hoặc phạm vi cha được hỗ trợ | Quản lý liên kết thanh toán của project mà không phải có quyền triển khai tài nguyên. |
| **Project Browser / Service Usage Viewer** | Project hoặc phạm vi cha phù hợp | Cung cấp một số quyền đọc/tra cứu bổ sung mà giao diện và quy trình thao tác có thể yêu cầu. |

Trong quy trình bật billing cho project đang có, một tổ hợp vai trò được tài liệu Google Cloud hướng dẫn là:

- **Trên project:** Project Billing Manager, Project Browser và Service Usage Viewer; **hoặc** Project Owner.
- **Trên Billing account đích:** Billing Account User và Billing Account Viewer; **hoặc** Billing Account Administrator.

Vai trò có thể được kế thừa từ organization hoặc folder tùy cách cấp IAM. Quyền thực tế và các điều kiện bổ sung như Organization Policy, hạn chế quyền theo điều kiện, xác thực lại hay khóa liên kết vẫn cần được kiểm tra. Không nên trao Project Owner hoặc Billing Account Administrator cho người chỉ cần gắn một project: dùng vai trò hẹp hơn sẽ dễ kiểm soát trách nhiệm và kiểm toán.

~~~mermaid
flowchart LR
    U["Người thực hiện"] --> P["Quyền quản lý liên kết<br/>trên project"]
    U --> B["Quyền sử dụng<br/>Billing account đích"]
    P --> L{"Đủ quyền và<br/>đáp ứng chính sách?"}
    B --> L
    L -->|Có| OK["Cho phép liên kết"]
    L -->|Không| NO["Kiểm tra IAM / policy"]
~~~

**Ví dụ phân công nhiệm vụ:** đội nền tảng có thể quản lý project và triển khai dịch vụ, đội tài chính có thể xem hóa đơn, còn một nhóm vận hành được cấp Billing Account User cùng Project Billing Manager để gắn đúng project vào tài khoản được duyệt. Cách này hạn chế trao quyền toàn bộ tài khoản cho mọi người lập trình.

## 4. Liên kết project với Cloud Billing account

### 4.1. Quy trình trên Google Cloud Console

Tên mục trên giao diện có thể thay đổi, nhưng trình tự phổ biến là:

1. Đăng nhập Google Cloud Console bằng tài khoản có quyền phù hợp và chọn **đúng project** từ danh sách project.
2. Mở **Billing**. Nếu chưa liên kết, giao diện có thể thông báo project chưa có Billing account và đưa ra lựa chọn **Link a billing account**.
3. Chọn **Billing account đang hoạt động** được phê duyệt cho project; kiểm tra tên hiển thị và ID, tránh chọn tài khoản của nhóm khác.
4. Xác nhận thao tác liên kết. Nếu giao diện yêu cầu xác thực lại cho hành động nhạy cảm, thực hiện theo chính sách của tổ chức.
5. Kiểm tra trang Billing của project hoặc mục **Account management / My projects** của Billing account để xác nhận project hiện liên kết đúng.

Nếu bắt đầu từ trang Billing account, người có quyền có thể xem danh sách **Projects linked to this billing account**, rồi kiểm tra project đã xuất hiện đúng danh sách hay chưa.

### 4.2. Kiểm tra bằng gcloud CLI

Các lệnh sau giúp xem trạng thái mà **không tạo tài nguyên mới**. Cần cài đặt gcloud CLI và đăng nhập vào tài khoản có quyền xem thông tin tương ứng.

~~~bash
# Liệt kê Billing account mà danh tính hiện tại có thể nhìn thấy
gcloud billing accounts list

# Xem thông tin Billing đang gắn với một project
gcloud billing projects describe PROJECT_ID
~~~

Ví dụ kết quả của lệnh describe có thể có dạng:

~~~yaml
billingAccountName: billingAccounts/01ABCD-02EFGH-03IJKL
billingEnabled: true
name: projects/shop-prod/billingInfo
projectId: shop-prod
~~~

Giải thích:

- **billingAccountName:** Billing account được liên kết với project.
- **billingEnabled: true:** cho biết billing được bật theo trạng thái hiện tại của project và tài khoản liên kết.
- **projectId:** Project ID, không phải Project number hay tên hiển thị.

Mẫu trên chỉ minh họa cấu trúc kết quả; không phải dữ liệu thực. Khi ứng dụng gặp lỗi liên quan Billing, cần kiểm tra cả tài khoản liên kết **và trạng thái active của Billing account**.

Để liên kết hoặc đổi sang account mới, lệnh chuẩn là:

~~~bash
# Thay PROJECT_ID và ACCOUNT_ID bằng giá trị thực đã được duyệt
gcloud billing projects link PROJECT_ID \
  --billing-account=ACCOUNT_ID
~~~

**Lệnh link là thao tác ghi có ảnh hưởng thanh toán.** Chỉ chạy sau khi đã xác nhận project, Billing account, quyền IAM, chính sách tổ chức và bên chịu chi phí. ACCOUNT_ID trong ví dụ là Billing account ID, không phải Project ID.

### 4.3. Kiểm tra kết quả sau thao tác

Sau khi liên kết, xác minh theo hai chiều:

~~~bash
# Xem project đang thuộc tài khoản Billing nào
gcloud billing projects describe PROJECT_ID

# Liệt kê project đang gắn với một Billing account
gcloud billing projects list --billing-account=ACCOUNT_ID
~~~

Phải kiểm tra project mong đợi xuất hiện ở account đúng và thông tin **billingEnabled** là **true**. Nếu project có thể truy cập nhưng không xuất hiện trong danh sách của người dùng hiện tại, nguyên nhân có thể là thiếu quyền xem, khác danh tính đăng nhập hoặc danh sách đang bị giới hạn bởi quyền truy cập; không nên vội kết luận project đã bị xóa.

## 5. Chuyển project sang Billing account khác

Có nhiều lý do hợp lệ để đổi liên kết: bộ phận khác tiếp nhận vận hành, doanh nghiệp tái cấu trúc pháp nhân, cần phân chia thanh toán cho khách hàng hoặc muốn thay thế tài khoản Billing cũ. **Đổi Billing account của project không phải di chuyển tài nguyên ứng dụng sang một project, region hoặc organization khác.** Project ID và các tài nguyên của project vẫn giữ nguyên trong quá trình thay liên kết thanh toán thông thường.

Ví dụ, project **shop-prod** đang gắn với tài khoản **BILLING-A** và cần chuyển sang **BILLING-B**. Khi liên kết sang BILLING-B được thực hiện thành công, tài khoản mới chịu phí cho mức sử dụng phát sinh sau thời điểm thay đổi theo cơ chế ghi nhận của Cloud Billing. Phần sử dụng đã phát sinh trước đó vẫn có thể được báo cáo và thanh toán trên tài khoản cũ; dữ liệu chi phí không nhất thiết xuất hiện ngay.

~~~mermaid
flowchart LR
    BA["BILLING-A<br/>tài khoản cũ"] -. "Liên kết trước khi chuyển" .-> P["Project shop-prod"]
    P --> R["Compute / Network / Database"]
    BB["BILLING-B<br/>tài khoản mới"] -->|"Liên kết sau khi chuyển"| P
~~~

Trước khi chuyển, cần đối chiếu:

1. **Tài khoản đích đang active:** xác minh tình trạng thanh toán và khả năng chi trả, tránh chuyển vào tài khoản bị đóng/tạm ngưng.
2. **Quyền trên các phía liên quan:** người đổi liên kết cần quyền thao tác trên project và các Billing account cũ, mới theo tài liệu hiện hành.
3. **Ràng buộc tổ chức:** xem có Organization Policy giới hạn Billing account được dùng hoặc có **khóa liên kết Billing** ngăn việc chuyển không.
4. **Các cam kết và sản phẩm liên quan:** rà soát committed-use discounts (CUD), hợp đồng, ưu đãi, ngân sách, thông báo và cách chi phí được tính sau chuyển.
5. **Báo cáo tài chính:** thống nhất thời điểm chuyển, cách đối soát hai tài khoản và trách nhiệm với các khoản phí được ghi nhận trễ.
6. **Khả năng theo dõi sau chuyển:** kiểm tra ngân sách, cảnh báo, export chi phí và quyền người quản trị của tài khoản mới.

Với gcloud CLI, **dùng trực tiếp lệnh link vào account mới** sau khi đã duyệt; không cần unlink trước:

~~~bash
gcloud billing projects link shop-prod \
  --billing-account=ACCOUNT_ID_MOI

gcloud billing projects describe shop-prod
~~~

Trong ví dụ, **ACCOUNT_ID_MOI** là chỗ điền ID thực của tài khoản đích. Lệnh đầu là thao tác thay đổi trách nhiệm thanh toán; lệnh sau dùng để xác nhận. Thực hiện unlink rồi link lại tạo ra khoảng thời gian project bị tắt billing, có nguy cơ làm dừng dịch vụ sản xuất.

### 5.1. Quyền khi chuyển khác gì lúc liên kết ban đầu?

Khi project chưa từng gắn với Billing account nào, thao tác chính là tạo liên kết đến account đích. Khi đang gắn với account cũ, thao tác chuyển cần đáp ứng cả khả năng bỏ liên kết cũ lẫn tạo liên kết mới. Google Cloud có các yêu cầu IAM cụ thể đối với project, account hiện tại và account đích; một số quyền đọc bổ sung cũng cần thiết để giao diện hoạt động đúng.

Nếu bạn xem được tài khoản mới nhưng không đổi được liên kết, hãy kiểm tra quyền trên **account hiện tại** và project, thay vì chỉ xin quyền cao hơn ở account mới. Nếu liên kết đang bị khóa, cần người có thẩm quyền xử lý khóa theo quy trình quản trị trước.

## 6. Vô hiệu hóa Billing khác với dừng tài nguyên

**Unlink** nghĩa là bỏ liên kết project khỏi Cloud Billing account đang dùng, dẫn tới **billing disabled**. Đây là thao tác có thể làm dừng các dịch vụ Google Cloud đang chạy, ảnh hưởng người dùng và khiến một số tài nguyên/dữ liệu không thể khôi phục đầy đủ. Google Cloud còn có những hạn chế đối với việc vô hiệu hóa Billing khi project có cam kết sử dụng đang hoạt động hoặc còn chờ.

~~~bash
# Lệnh minh họa có tác động lớn: KHÔNG dùng để thử nghiệm
gcloud billing projects unlink PROJECT_ID
~~~

Lệnh trên **không nên dùng như một cách tạm dừng chi phí thông thường**. Những khoản sử dụng đã phát sinh trước khi tắt Billing vẫn phải được thanh toán; một số khoản có thể xuất hiện muộn trong báo cáo. Bật Billing lại không bảo đảm mọi dịch vụ tự khởi động lại ngay, và một số tài nguyên có thể đã bị xóa.

| Mục tiêu | Hành động phù hợp hơn | Vì sao |
| --- | --- | --- |
| Muốn theo dõi nguy cơ vượt chi phí | Tạo budget, cảnh báo, phân tích chi phí theo project và dịch vụ. | Cung cấp tín hiệu để can thiệp sớm, không gián đoạn tùy tiện. |
| Muốn giảm chi phí thử nghiệm | Dừng/xóa những tài nguyên không cần thiết theo hướng dẫn riêng của từng dịch vụ, kiểm tra tài nguyên vẫn tính phí. | Kiểm soát cụ thể thành phần tạo chi phí. |
| Muốn chuyển project sang đơn vị chịu phí khác | Dùng **link** trực tiếp sang Billing account đích đang hoạt động. | Tránh khoảng trống billing khi unlink rồi link lại. |
| Muốn ngừng cung cấp toàn bộ dịch vụ và đóng project | Lập kế hoạch sao lưu, ngừng dịch vụ, thu hồi tài nguyên và xử lý Billing theo quy trình. | Giảm rủi ro mất dữ liệu và chi phí còn tồn. |

Trước mọi thao tác tắt Billing, phải hiểu tình trạng workload, trách nhiệm dữ liệu và cam kết tài chính. Sự kiện tắt Billing không xóa ngay nghĩa vụ thanh toán của những khoản sử dụng trước đó.

## 7. Liên kết Billing tạo nền tảng cho ngân sách và báo cáo chi phí

Khi nhiều project dùng một Billing account, nhà quản trị có thể phân tích mức tiêu thụ theo **project**, **service**, **SKU**, thời gian và các chiều dữ liệu được sản phẩm hỗ trợ. Điều này giúp chia chi phí cho nhóm phát triển, môi trường thử nghiệm và production dù cùng một tài khoản thanh toán.

### 7.1. Project là ranh giới phân bổ chi phí quan trọng

Giả sử một công ty có ba project:

| Project ID minh họa | Vai trò | Billing account liên kết | Cách theo dõi |
| --- | --- | --- | --- |
| store-dev | Môi trường phát triển | BILLING-COMPANY | Budget lọc theo project dev; theo dõi tài nguyên thử nghiệm. |
| store-staging | Kiểm thử phát hành | BILLING-COMPANY | Budget riêng theo project; chú ý các bài thử tải. |
| store-prod | Môi trường production | BILLING-COMPANY | Budget, cảnh báo nhiều ngưỡng, theo dõi chi phí theo dịch vụ và xu hướng tăng. |

Ba project dùng chung một Billing account nhưng có thể đặt budget với bộ lọc tương ứng. Nếu cần phân bổ chi phí chi tiết hơn bên trong một project, hãy xem xét labels/tags, cách ghi nhận trong báo cáo Billing và chuẩn đặt tên tài nguyên. Không nên mặc định mọi SKU đều hỗ trợ phân bổ theo nhãn hoặc cùng một mức độ chi tiết.

### 7.2. Budget và cảnh báo không phải giới hạn chi phí cứng

Cloud Billing cung cấp **Budgets & alerts** để theo dõi mức chi tiêu thực tế hoặc dự báo theo phạm vi được cấu hình. Ví dụ, tạo ngân sách minh họa **5.000.000 VND/tháng** cho project dev, với cảnh báo khi đạt 50%, 90% và 100% ngân sách.

| Ngưỡng | Tín hiệu sử dụng trong vận hành |
| --- | --- |
| 50% | Kiểm tra mức tăng so với dự báo và các tài nguyên thử nghiệm. |
| 90% | Xác định dịch vụ tăng bất thường, trao đổi với chủ project và xem xét giảm tải tài nguyên không thiết yếu. |
| 100% | Kích hoạt quy trình xử lý vượt ngân sách của đội ngũ; quyết định hành động có kiểm soát. |

**Budget thông thường gửi cảnh báo, không tự đặt trần chi tiêu hoặc tự dừng mọi tài nguyên khi đạt ngưỡng.** Thời điểm ghi nhận chi phí và gửi thông báo có thể trễ so với mức sử dụng thực tế. Do vậy, không nên khẳng định rằng ngân sách 5 triệu sẽ khiến hóa đơn không thể vượt 5 triệu.

Nếu thiết kế hệ thống tự động phản ứng với cảnh báo, cần kiểm soát quyền, xác nhận phạm vi và kiểm thử kỹ để tránh làm gián đoạn dịch vụ quan trọng. Việc quản lý chi phí còn cần quota, chính sách tài nguyên, lịch tắt môi trường thử nghiệm, kiểm tra cơ sở dữ liệu và giám sát bất thường.

### 7.3. Báo cáo và xuất dữ liệu Billing

Trong Cloud Console, chức năng **Billing Reports** giúp nhìn chi phí theo thời gian, project hoặc dịch vụ. Đối với nhu cầu đối soát chi tiết và phân tích lâu dài, có thể cấu hình **Cloud Billing export to BigQuery** nếu phù hợp với quyền và yêu cầu lưu trú dữ liệu.

Khi cấu hình export, cần quan tâm:

- **Địa điểm dataset BigQuery** và chính sách lưu trú dữ liệu áp dụng.
- **Quyền IAM** để cấu hình Billing export, truy cập dataset và xem dữ liệu chi phí.
- **Độ trễ ghi nhận dữ liệu:** dữ liệu sử dụng, điều chỉnh và chi phí có thể đến muộn; không đồng nhất một báo cáo tức thời với hóa đơn cuối kỳ.
- **Chi phí của hệ thống phân tích:** lưu dữ liệu và chạy truy vấn BigQuery có thể phát sinh phí.
- **Mô hình phân bổ:** những khoản giảm giá, credits, thuế, hỗ trợ, khoản điều chỉnh và mức chi tiết theo project/SKU cần được hiểu đúng trước khi kết luận chi phí thực.

Ví dụ, khi một project chuyển Billing account giữa tháng, người phụ trách tài chính cần tổng hợp dữ liệu từ **cả account cũ và account mới** để đối soát toàn bộ kỳ. Không thể suy ra chi phí của cả tháng từ báo cáo chỉ của account mới.

## 8. Những nguyên nhân thường gặp khi không liên kết được Billing

| Hiện tượng | Khả năng cần kiểm tra | Cách xác minh và hướng xử lý |
| --- | --- | --- |
| Không thấy Billing account mong muốn trong danh sách | Tài khoản chưa được cấp quyền xem/sử dụng; đăng nhập sai danh tính; account ở phạm vi khác. | Kiểm tra danh tính, IAM trên Billing account và ID mà bộ phận tài chính cung cấp. |
| Console báo không đủ quyền để link project | Thiếu quyền ở project hoặc Billing account đích. | Đối chiếu Project Billing Manager, các vai trò đọc cần thiết và Billing Account User/Viewer. |
| Không chuyển từ account cũ sang account mới được | Thiếu quyền trên account cũ, liên kết bị khóa hoặc tổ chức có chính sách hạn chế. | Kiểm tra quyền hai phía, khóa liên kết, Organization Policy và quy trình phê duyệt. |
| Project có Billing account ID nhưng vẫn bị lỗi billing | Account đã đóng, tạm ngừng hoặc không ở trạng thái hoạt động hợp lệ. | Kiểm tra trường billingEnabled và tình trạng account qua Console/tài liệu xác minh. |
| Project bị ngừng dịch vụ sau khi unlink | Billing đã bị tắt. | Xác nhận tình trạng dữ liệu, liên kết với account active; làm theo runbook phục hồi của từng dịch vụ. |
| Budget đạt 100% nhưng tài nguyên vẫn tiêu thụ | Cảnh báo ngân sách không phải cơ chế dừng cứng. | Phân tích báo cáo, kiểm tra tài nguyên, áp quy trình kiểm soát chi phí phù hợp. |
| Chi phí còn xuất hiện ở account cũ sau khi chuyển | Sử dụng trước thời điểm chuyển được ghi nhận chậm. | Đối chiếu mốc thời gian, chi tiết giao dịch, báo cáo và khoản điều chỉnh của cả hai account. |

Khi khắc phục lỗi, không nên xử lý bằng cách cấp vai trò Administrator cho mọi thành viên hoặc unlink project đang hoạt động. Trước tiên xác định rõ thiếu quyền đọc, thiếu quyền liên kết, sai trạng thái tài khoản hay ràng buộc chính sách.

## 9. Tình huống triển khai: tách môi trường nhưng thanh toán tập trung

Một nhóm triển khai dịch vụ thương mại điện tử trên Google Cloud: Cloud Run phục vụ API, Cloud SQL lưu đơn hàng, Cloud Storage lưu ảnh sản phẩm và một số công việc chạy trên Compute Engine/GKE. Nhóm tạo ba project **commerce-dev**, **commerce-test** và **commerce-prod** để tách IAM, API, hạn mức và vòng đời tài nguyên.

Đội tài chính xác định chỉ một pháp nhân chịu chi phí của cả ba môi trường. Nhóm có thể dùng một Cloud Billing account chung và thực hiện các bước sau:

1. Đội tài chính tạo/quản lý Billing account, hoàn thiện thông tin thanh toán và duyệt danh sách project được phép liên kết.
2. Đội nền tảng tạo các project theo cấu trúc organization/folder và đặt IAM đúng vai trò. Người quản lý liên kết được cấp quyền sử dụng Billing account cùng quyền quản lý Billing trên các project cần thiết.
3. Sau khi gắn Billing, nhóm xác minh từng project có **billingEnabled: true**, đúng Billing account ID và account vẫn đang active.
4. Đội kỹ thuật triển khai Cloud Run, Cloud SQL, Cloud Storage hoặc GKE theo từng project. Họ vẫn phải kiểm soát IAM, VPC, vị trí dữ liệu, bảo mật và độ tin cậy; liên kết Billing không giải quyết thay những thiết kế đó.
5. Đội FinOps/tài chính tạo budget cho từng project, thiết lập cảnh báo và dùng Reports hoặc export để xem chi phí theo môi trường, dịch vụ, thời điểm.
6. Trước khi nâng cấp hoặc chạy thử tải, nhóm kiểm tra quota, chi phí dự kiến, hạn mức hạ tầng và người chịu trách nhiệm khi chi phí vượt dự báo.

Sau một thời gian, sản phẩm production được chuyển cho công ty con với tài khoản Billing riêng. Đội quản trị kiểm tra điều kiện pháp lý, quyền ở hai account, khóa liên kết, CUD và khả năng đối soát rồi **link commerce-prod trực tiếp sang Billing account mới**. Việc này không yêu cầu tự động di chuyển Cloud SQL hay Cloud Run sang project khác. Tuy nhiên, ngân sách và quyền xem chi phí của phía tiếp nhận phải được chuẩn bị trước.

## 10. Bài thực hành không phát sinh tài nguyên

Giả sử bạn được cấp quyền đọc trong một tổ chức Google Cloud đang có sẵn project. Hãy hoàn thành bài thực hành theo thứ tự:

**Bước 1 — Nhận diện:** Ghi riêng Project ID, Project number (nếu cần), Billing account ID và tên đơn vị chịu thanh toán. Giải thích vì sao ba loại định danh không được dùng thay thế nhau.

**Bước 2 — Đọc trạng thái:** Sử dụng Console hoặc hai lệnh chỉ đọc:

~~~bash
gcloud billing accounts list
gcloud billing projects describe PROJECT_ID
~~~

Xác định project có liên kết account nào, trường **billingEnabled** là true/false, và cần thêm bằng chứng gì để xác minh account đang hoạt động.

**Bước 3 — Kiểm tra mô hình quyền:** Giả định một lập trình viên có quyền triển khai Cloud Run nhưng không nhìn thấy account được phòng tài chính chỉ định. Hãy chỉ ra những nhóm quyền cần kiểm tra trên **project** và **Billing account**; đề xuất cách cấp quyền đủ dùng mà không trao quyền admin không cần thiết.

**Bước 4 — Lập phương án chuyển account (trên giấy):** Công ty yêu cầu đưa project production sang tài khoản mới. Soạn checklist gồm ID hai tài khoản, trạng thái active, vai trò IAM, khóa liên kết, tổ chức chịu phí, thời điểm chuyển, CUD, ngân sách và cách đối soát báo cáo. Không thực hiện lệnh link/unlink nếu chưa có phê duyệt vận hành.

**Bước 5 — Phân tích ngân sách:** Ba project dev, test, prod có các ngân sách minh họa khác nhau. Đề xuất ngưỡng cảnh báo và hành động của người trực khi dev tăng tiêu thụ bất thường. Giải thích tại sao cảnh báo đạt 100% không có nghĩa phí tự dừng.

### Câu hỏi tự kiểm tra

1. Vì sao một project có Billing account ID vẫn có thể không ở trạng thái billing enabled?
2. Một Cloud Billing account có thể chịu phí cho bao nhiêu project? Một project có thể dùng đồng thời hai Billing account không?
3. Người có quyền xem hóa đơn có tự động được sửa VM, Cloud SQL hoặc Cloud Run trong project không?
4. Khi chuyển account chịu phí, có phải chuyển toàn bộ tài nguyên sang project mới không? Khoản sử dụng phát sinh trước thời điểm chuyển được xử lý ra sao?
5. Tại sao không nên unlink Billing để tạm dừng môi trường production, và tại sao budget alert không phải giới hạn tiền cứng?

**Gợi ý đáp án:** (1) Account có thể bị đóng/tạm ngừng; cần có liên kết và account active. (2) Một account có thể gắn nhiều project; mỗi project tối đa một account tại một thời điểm. (3) Không, quyền Billing và quyền tài nguyên tách biệt. (4) Không; chi phí trước chuyển vẫn thuộc account cũ theo thời điểm sử dụng và quá trình ghi nhận. (5) Unlink có thể dừng dịch vụ, ảnh hưởng dữ liệu; budget chỉ giám sát và cảnh báo trừ khi có cơ chế xử lý bổ sung được thiết kế riêng.

## Tài liệu Google Cloud để đối chiếu khi thao tác

- **Manage your Cloud Billing account:** https://cloud.google.com/billing/docs/how-to/manage-billing-account — cấu trúc Billing account, phương thức thanh toán và quản lý tài khoản.
- **Enable, disable, or change billing for a project:** https://cloud.google.com/billing/docs/how-to/modify-project — điều kiện IAM, liên kết, chuyển và tắt Billing.
- **Verify the billing status of your projects:** https://cloud.google.com/billing/docs/how-to/verify-billing-enabled — kiểm tra project có billing enabled hay không.
- **Cloud Billing access control:** https://cloud.google.com/billing/docs/how-to/billing-access — các vai trò IAM của Billing account và project.
- **Create and manage budgets:** https://cloud.google.com/billing/docs/how-to/budgets — phạm vi budget, ngưỡng và cảnh báo.
- **Export Cloud Billing data to BigQuery:** https://cloud.google.com/billing/docs/how-to/export-data-bigquery — xuất dữ liệu để phân tích chi phí.
- **gcloud billing projects:** https://cloud.google.com/sdk/gcloud/reference/billing/projects — cú pháp các lệnh describe, list, link và unlink.

Quyền IAM, hành vi của dịch vụ khi tắt Billing, điều kiện thanh toán và tính năng hỗ trợ có thể thay đổi. Trước khi áp dụng trên project thật, hãy đối chiếu tài liệu chính thức cùng chính sách quản trị và tài chính của tổ chức.
