# Thiết kế quyền tối thiểu và tách nhiệm vụ quản trị

Một hệ thống Google Cloud có thể được triển khai đúng trên Compute Engine, Google Kubernetes Engine (GKE), Cloud Run và các dịch vụ dữ liệu nhưng vẫn gặp sự cố nghiêm trọng nếu danh tính của ứng dụng hoặc con người được cấp quá nhiều quyền. Ví dụ, tài khoản dùng để phát hành một phiên bản Cloud Run chỉ cần cập nhật dịch vụ được giao, nhưng lại được cấp quyền Owner trên cả project: khi tài khoản này bị lộ, kẻ tấn công có thể thay đổi IAM, cấu hình hệ thống và nhiều tài nguyên không liên quan.

Trong chương **IAM và xác thực** thuộc module **CLOUD_PROVIDERS_GCP**, bài học này tập trung vào hai nguyên tắc:

- **Quyền tối thiểu (least privilege):** mỗi danh tính chỉ được phép thực hiện những thao tác cần cho công việc, đối với đúng tài nguyên, trong khoảng thời gian cần thiết.
- **Tách nhiệm vụ quản trị (separation of duties, SoD):** các hành động nhạy cảm như phê duyệt cấp quyền, triển khai production, quản lý thanh toán và kiểm toán được phân chia để một người hoặc một tài khoản không tự thực hiện toàn bộ quy trình có rủi ro cao.

Sau bài học, bạn có thể lập ma trận quyền IAM, chọn phạm vi cấp quyền hợp lý, phân biệt danh tính triển khai với danh tính chạy ứng dụng, phát hiện đường leo thang đặc quyền và xây dựng quy trình cấp, kiểm tra, thu hồi quyền. Những quyết định này hỗ trợ mục tiêu bảo vệ tài nguyên, tự động hóa phát hành và vận hành có kiểm soát của Google Cloud.

## 1. Hiểu cơ chế IAM trước khi thiết kế quyền

### 1.1. Xác thực và phân quyền là hai bước khác nhau

**Authentication (xác thực)** trả lời câu hỏi *ai đang gọi?* Danh tính có thể là người dùng, nhóm thông qua thành viên người dùng, service account, hoặc principal đại diện workload bên ngoài Google Cloud qua cơ chế liên kết danh tính.

**Authorization (phân quyền)** trả lời câu hỏi *danh tính đó được làm gì với tài nguyên nào?* Google Cloud IAM đánh giá những chính sách liên quan để quyết định có cho phép một thao tác cụ thể hay không.

Ví dụ, một lập trình viên đăng nhập bằng tài khoản công ty (đã xác thực) không mặc nhiên được xóa Cloud SQL instance. Người đó vẫn cần có quyền thích hợp trên tài nguyên. Tương tự, service account đã được Cloud Run sử dụng để lấy token không mặc nhiên có quyền đọc toàn bộ bucket trong project.

### 1.2. Các thành phần của một quyền truy cập

| Thành phần | Vai trò trong quyết định | Ví dụ |
| --- | --- | --- |
| **Principal** | Danh tính được xét quyền | \`user:dev@example.com\`, \`group:cloud-deploy@example.com\`, \`serviceAccount:api-runtime@PROJECT_ID.iam.gserviceaccount.com\` |
| **Permission** | Thao tác cụ thể trên API/tài nguyên | \`run.services.update\`, \`storage.objects.get\` |
| **Role** | Tập các permission được đóng gói | \`roles/run.developer\`, \`roles/storage.objectViewer\` |
| **Resource** | Đối tượng chịu chính sách | Organization, folder, project, Cloud Run service, bucket hoặc service account |
| **Allow policy / binding** | Liên kết principal với role ở một phạm vi | Gán nhóm triển khai role phù hợp trên project hoặc dịch vụ |
| **Condition (nếu có)** | Điều kiện giới hạn hiệu lực binding khi được hỗ trợ | Giới hạn theo thời điểm hoặc thuộc tính tài nguyên được hỗ trợ |

Nhóm role chính:

1. **Basic roles** như Owner, Editor, Viewer: có phạm vi rộng, khó kiểm soát chính xác; tránh sử dụng cho vận hành thường ngày nếu có role hẹp hơn.
2. **Predefined roles**: Google Cloud định nghĩa theo sản phẩm/chức năng, ví dụ Cloud Run Developer hoặc Storage Object Viewer; thường là lựa chọn đầu tiên.
3. **Custom roles**: tổ chức tự chọn tập permission khi role có sẵn cấp thừa hoặc thiếu quyền; cần bảo trì khi API và chức năng thay đổi.

Role chỉ là một tập permission. **Quyền thực tế** còn phụ thuộc nơi binding được gán, quan hệ kế thừa từ resource hierarchy và những chính sách giới hạn khác.

### 1.3. Phạm vi cấp quyền và kế thừa

Google Cloud sử dụng cấu trúc quản trị:

~~~text
Organization
└── Folder: Production
    ├── Project: shop-prod
    │   ├── Cloud Run: checkout-api
    │   ├── Cloud Storage: invoices
    │   └── Service account: checkout-runtime
    └── Project: analytics-prod
~~~

Một IAM allow binding được gán ở organization, folder hoặc project thường được kế thừa xuống các tài nguyên con, theo những quy tắc của IAM. Ví dụ, nhóm có role rộng tại folder Production có thể có quyền trên cả shop-prod lẫn analytics-prod. Gán quyền hẹp ở Cloud Run service hoặc bucket có thể giảm ảnh hưởng so với gán cùng role trên cả project, **nếu loại tài nguyên và role hỗ trợ cấp ở phạm vi đó**.

Điều cần nhớ:

- Không thể chỉ nhìn IAM policy gắn trực tiếp với một tài nguyên rồi kết luận toàn bộ quyền hữu hiệu; phải xét các binding kế thừa từ cha.
- Thêm binding hẹp ở project con thường **không xóa** quyền đã kế thừa từ folder/organization.
- Sự tồn tại của allow binding không đảm bảo thao tác sẽ thành công: IAM Deny, principal access boundary, Organization Policy, các điều kiện khác hoặc kiểm tra quyền ở sản phẩm có thể ảnh hưởng.
- Organization Policy thường kiểm soát việc cấu hình và sử dụng tài nguyên (ví dụ hạn chế loại hành động/cấu hình được phép), nên không được coi là bản thay thế của IAM.

**Quy tắc thiết kế:** gán ở phạm vi thấp nhất có thể đáp ứng nghiệp vụ; chỉ gán quyền ở folder hoặc organization khi nhiệm vụ thực sự xuyên nhiều project.

## 2. Thiết kế quyền tối thiểu theo thao tác thực tế

“Chỉ cấp quyền cần thiết” chưa đủ nếu không biết chính xác người dùng hoặc ứng dụng phải thực hiện việc gì. Hãy bắt đầu bằng danh sách tác vụ, thay vì bắt đầu từ tên role hoặc chức danh.

### 2.1. Lập bản đồ danh tính – thao tác – tài nguyên

Giả sử hệ thống bán hàng có Cloud Run API, Cloud SQL và Cloud Storage. Đội phát triển, pipeline CI/CD, API runtime, đội vận hành mạng và nhóm kiểm toán cần quyền rất khác nhau.

| Danh tính hoặc nhóm | Tác vụ bắt buộc | Tài nguyên | Cách giới hạn |
| --- | --- | --- | --- |
| Người phát triển | Xem log ứng dụng, kiểm tra trạng thái bản phát hành | Dịch vụ và log thuộc môi trường dev | Quyền đọc phù hợp, tránh quyền thay đổi IAM |
| Pipeline triển khai | Cập nhật một Cloud Run service và sử dụng runtime service account được chỉ định | Service production, runtime service account | Quyền triển khai có phạm vi + quyền actAs trên đúng service account |
| Runtime API | Đọc object đầu vào và kết nối database cần thiết | Bucket hoặc đường truy cập dữ liệu được phép, Cloud SQL | Role hẹp nhất; database còn có xác thực và phân quyền riêng |
| Nhóm mạng | Quản lý subnet, route hoặc cấu hình mạng theo nhiệm vụ | Project hoặc network được giao | Role mạng phù hợp; tách quản lý firewall nếu cần |
| Nhóm tài chính | Xem chi phí và ngân sách | Cloud Billing account | Quyền Billing phù hợp, không kèm quyền quản lý workload |
| Nhóm an toàn thông tin | Kiểm tra policy, đánh giá quyền và bằng chứng audit | Các project trong phạm vi giám sát | Vai trò kiểm toán chỉ đọc; quy trình riêng khi cần quyền sửa |

Không phải tác vụ nào cũng có một predefined role hoàn toàn vừa khít. Khi đó, cân nhắc cấp role ở tài nguyên cụ thể, tách bước công việc hoặc dùng custom role nếu danh sách permission hỗ trợ.

### 2.2. Chọn role theo trình tự

1. **Liệt kê thao tác cần có:** ví dụ chỉ đọc object, tải image, cập nhật Cloud Run revision hoặc kết nối Cloud SQL.
2. **Tìm permission tương ứng:** đối chiếu phương thức API và tài liệu IAM của dịch vụ; không suy diễn từ nhãn “Viewer” hoặc “Developer”.
3. **Ưu tiên predefined role hẹp:** như \`roles/storage.objectViewer\` cho nhu cầu đọc object hoặc \`roles/run.developer\` cho nhiệm vụ phát triển/triển khai Cloud Run phù hợp.
4. **Chọn phạm vi binding nhỏ nhất:** bucket cụ thể, service cụ thể hoặc project nếu không thể thu hẹp hơn mà vẫn vận hành được.
5. **Xem quyền phát sinh gián tiếp:** quyền sửa workload, gắn service account hoặc chỉnh pipeline có thể trao cơ hội sử dụng một danh tính đặc quyền hơn.
6. **Kiểm thử thao tác hợp lệ và không hợp lệ:** người dùng làm được việc được giao, nhưng không thể thay đổi tài nguyên ngoài phạm vi.
7. **Rà soát theo thời gian:** khi nhân sự chuyển nhóm, service đổi cách hoạt động hoặc quyền không còn sử dụng, thu hồi binding thừa.

**Ví dụ:** một tác vụ chỉ cần tải ảnh sản phẩm từ bucket \`shop-product-images\` thì không nên được cấp Storage Admin ở project. Một binding \`roles/storage.objectViewer\` trên đúng bucket thường gần nhu cầu hơn. Tuy vậy, việc đọc các object bên trong bucket vẫn có thể rộng hơn cần thiết: nếu dữ liệu chia thành nhiều nhóm nhạy cảm, hãy cân nhắc tách bucket hoặc thiết kế quyền và điều kiện phù hợp với mô hình dữ liệu.

### 2.3. Phân biệt quyền xem, quyền vận hành và quyền cấp quyền

Có ba loại thao tác cần thận trọng đặc biệt:

- **Quyền đọc dữ liệu nhạy cảm:** có thể trực tiếp làm lộ thông tin khách hàng dù không được sửa cấu hình.
- **Quyền thay đổi dịch vụ:** có thể sửa code, container image, cấu hình môi trường, network hoặc điểm xuất dữ liệu. Một quyền “Developer” vẫn có tác động bảo mật đáng kể trên production.
- **Quyền quản trị IAM hoặc danh tính:** có thể cấp vai trò, thay đổi policy, cho phép impersonation hoặc sửa đường phát hành. Đây là nguồn leo thang đặc quyền nếu không kiểm soát.

Tên role nghe “ít quyền” không đủ để đánh giá rủi ro; cần xem cả permission cụ thể lẫn hệ quả thực tế trên hệ thống.

## 3. Tách nhiệm vụ quản trị để ngăn tự cấp quyền và tự phê duyệt

Tách nhiệm vụ (SoD) nghĩa là những bước nhạy cảm có người chịu trách nhiệm khác nhau, với dấu vết phê duyệt và khả năng kiểm tra sau đó. Mục tiêu là giảm khả năng một lỗi vận hành, một tài khoản bị lộ hoặc một người có động cơ xấu gây hậu quả trên toàn hệ thống.

### 3.1. Những nhiệm vụ nên tách

| Quy trình | Vai trò đề xuất | Ranh giới quan trọng |
| --- | --- | --- |
| Đề nghị quyền IAM | Chủ hệ thống hoặc người cần quyền | Người đề nghị nêu tác vụ, tài nguyên và thời hạn; không tự phê duyệt quyền đặc biệt của mình. |
| Phê duyệt đặc quyền | Chủ tài nguyên / người chịu trách nhiệm bảo mật | Duyệt lý do và mức quyền; không phụ thuộc hoàn toàn vào người yêu cầu. |
| Thực thi thay đổi IAM | Đội quản lý IAM hoặc pipeline cấu hình được kiểm soát | Có quyền đặt policy trong phạm vi được giao, lưu lịch sử và nguồn phê duyệt. |
| Phát hành ứng dụng | Pipeline triển khai và nhóm release | Có quyền cập nhật workload cần thiết; không tự quản lý mọi service account hoặc IAM của tổ chức. |
| Quản trị mạng | Đội mạng | Quyền mạng phù hợp; các thay đổi chính sách firewall quan trọng có bước review riêng. |
| Quản trị Billing | Tài chính / FinOps | Xem hoặc quản lý Billing account, không mặc nhiên có quyền xóa database. |
| Kiểm tra và audit | Nhóm bảo mật/kiểm toán | Truy cập đọc bản ghi và policy; có kênh độc lập để báo cáo sai lệch. |
| Khôi phục khẩn cấp | Người trực sự cố có quyền tạm thời theo quy trình | Cấp quyền trong thời gian giới hạn, ghi nhận lý do và thu hồi sau sự cố. |

Không bắt buộc doanh nghiệp nhỏ phải có một bộ phận cho mỗi hàng. Điều quan trọng là **tách được các hành vi có xung đột lợi ích**, ví dụ tránh việc cùng một người vừa tự phê duyệt quyền Owner, vừa tự cấp quyền và tự xác nhận kiểm toán. Nếu ít nhân sự, có thể dùng phê duyệt chéo, review pull request, quyền tạm thời và nhật ký độc lập để tạo cơ chế kiểm soát thay thế.

### 3.2. Ví dụ quy trình phân quyền có phê duyệt

~~~mermaid
flowchart TD
    R["Người dùng đề nghị truy cập"] --> T["Chỉ rõ nhiệm vụ, tài nguyên,<br/>vai trò và thời hạn"]
    T --> A{"Chủ tài nguyên / bảo mật duyệt?"}
    A -->|Không| X["Từ chối hoặc yêu cầu chỉnh sửa"]
    A -->|Có| I["Quản trị IAM / pipeline áp binding"]
    I --> V["Kiểm thử quyền và ghi nhật ký"]
    V --> M["Theo dõi thời hạn và rà soát định kỳ"]
    M --> E["Thu hồi quyền khi hết nhu cầu"]
~~~

Một yêu cầu hợp lệ cần đủ thông tin để người duyệt trả lời: *Ai cần quyền, làm tác vụ nào, trên tài nguyên gì, trong bao lâu, hậu quả nếu bị lạm dụng là gì, ai chịu trách nhiệm?* Nếu câu trả lời chỉ là “cần Editor để thao tác cho tiện”, cần phân tích lại công việc.

### 3.3. Các đường leo thang đặc quyền dễ bị bỏ sót

1. **Gắn service account mạnh vào workload:** principal có quyền triển khai hoặc sửa workload và quyền \`iam.serviceAccounts.actAs\` trên service account đặc quyền có thể chạy code dưới danh tính đó. Vì vậy quyền **Service Account User** (\`roles/iam.serviceAccountUser\`) cần được giới hạn chặt.
2. **Impersonate service account:** \`roles/iam.serviceAccountTokenCreator\` cho phép tạo các loại thông tin xác thực đại diện theo quyền cụ thể của role; nếu đặt trên service account có nhiều quyền thì người được gán có thể thực hiện hành động với quyền của service account đó.
3. **Sửa pipeline hoặc kho mã được tin cậy:** ngay cả khi người sửa không trực tiếp có quyền production, pipeline tự động có thể đang được cấp quyền triển khai production. Phải bảo vệ nhánh phát hành, review code và cấu hình pipeline.
4. **Gán IAM ở phạm vi cha:** role đặt ở folder hoặc organization có thể cấp quyền trên những project hiện tại và những project được tạo sau này trong nhánh đó.
5. **Chia sẻ tài khoản quản trị:** nếu nhiều người dùng chung một tài khoản đăng nhập, khó quy trách nhiệm và thu hồi quyền của riêng từng người.

Trong các trường hợp này, chỉ kiểm tra xem principal có role Owner hay không là chưa đủ. Cần xét **khả năng điều khiển một danh tính hoặc quy trình có quyền cao hơn**.

## 4. Thiết kế danh tính workload và service account

Ứng dụng cần gọi API của Google Cloud bằng một danh tính, nhưng danh tính đó không nên là tài khoản cá nhân của lập trình viên. **Service account** đại diện cho ứng dụng hoặc thành phần tự động, giúp phân quyền theo chức năng và thay đổi người quản lý mà không làm đổi danh tính của workload.

### 4.1. Tách danh tính chạy ứng dụng và triển khai

Giả sử công ty có API đặt hàng chạy trên Cloud Run:

| Danh tính | Sử dụng khi nào? | Quyền phù hợp với nhiệm vụ |
| --- | --- | --- |
| \`checkout-runtime@...\` | API đang xử lý request | Đọc object cần thiết trong bucket; quyền kết nối Cloud SQL; quyền tương ứng cho dịch vụ phụ thuộc |
| \`checkout-deploy@...\` | Pipeline phát hành phiên bản Cloud Run | Quyền cập nhật dịch vụ; quyền sử dụng đúng runtime service account |
| Nhóm \`cloud-developers@...\` | Phát triển, kiểm tra và đề nghị phát hành | Quyền môi trường dev, quyền xem thông tin cần thiết; không tự cấp IAM production |
| Nhóm \`iam-reviewers@...\` | Xem policy và duyệt yêu cầu đặc quyền | Quyền đọc phục vụ đánh giá; quyền thay đổi IAM chỉ theo vai trò được phân công riêng |

**Runtime service account không cần quyền sửa Cloud Run**, vì nhiệm vụ của nó là xử lý giao dịch. **Deployment service account không cần đọc bảng đơn hàng production**, vì nhiệm vụ của nó là phát hành phiên bản ứng dụng. Đó là lợi ích của việc tách danh tính theo nhiệm vụ.

~~~mermaid
flowchart LR
    Dev["Lập trình viên"] --> Repo["Pull request đã review"]
    Repo --> CI["Pipeline CI/CD"]
    CI --> DSA["Service account triển khai"]
    DSA --> Run["Cập nhật Cloud Run service"]
    Run --> RSA["Runtime service account"]
    RSA --> CS[("Cloud SQL / dữ liệu cần thiết")]
    RSA --> ST[("Bucket giới hạn phạm vi")]
~~~

Đường từ pipeline tới workload cần được hiểu là **quyền cập nhật cấu hình/phiên bản**, không phải quyền tự do cấp thêm IAM cho toàn bộ project. Tuy nhiên, người có thể thay đổi code chạy dưới runtime service account vẫn có khả năng tận dụng các quyền mà runtime service account có. Vì vậy, review mã nguồn và kiểm soát phát hành là thành phần của thiết kế quyền tối thiểu.

### 4.2. Ba quyền dễ bị nhầm lẫn

| Quyền hoặc role liên quan | Cho phép điều gì? | Rủi ro nếu cấp rộng |
| --- | --- | --- |
| \`roles/iam.serviceAccountUser\` | Cho phép **actAs** service account, thường để gắn service account đó vào tài nguyên mà principal được quyền tạo/sửa. | Có thể chạy workload dưới danh tính mạnh hơn nếu đồng thời kiểm soát việc triển khai. |
| \`roles/iam.serviceAccountTokenCreator\` | Cho phép một số thao tác tạo token/credential và impersonation theo các permission của role. | Có thể gọi API với quyền của service account đích. |
| Quyền quản trị service account, ví dụ \`roles/iam.serviceAccountAdmin\` | Quản lý tài nguyên service account theo phạm vi và permission của role. | Có thể thay đổi vòng đời/cấu hình danh tính; không nên coi là quyền đọc đơn thuần. |

Các quyền này **không tương đương nhau**. Service Account User không mặc nhiên tạo được access token qua API impersonation; Token Creator không mặc nhiên có quyền tạo máy ảo. Nhưng cả hai đều cần kiểm soát theo đường leo thang đặc quyền mà người sở hữu có thể kết hợp với các quyền khác.

Khi một pipeline chỉ cần dùng \`checkout-runtime\`, hãy xét gán \`roles/iam.serviceAccountUser\` **trên đúng service account** thay vì ở cả project. Không sử dụng cùng một runtime service account mạnh cho mọi ứng dụng chỉ vì thuận tiện.

### 4.3. Hạn chế khóa service account tồn tại lâu

JSON key tải xuống có thể bị sao chép, vô tình commit lên repository, để lại trong log hoặc dùng lại sau khi nhân sự thay đổi. Với môi trường Google Cloud, ưu tiên **Application Default Credentials (ADC)** cùng danh tính do môi trường cung cấp, thay vì tạo khóa tĩnh không cần thiết.

- **Cloud Run:** gắn service account riêng cho service; thư viện Google Cloud có thể nhận credential từ môi trường chạy.
- **GKE:** cân nhắc **Workload Identity Federation for GKE** để workload Kubernetes truy cập tài nguyên Google Cloud theo danh tính được cấu hình, tránh phát tán file khóa vào pod.
- **Compute Engine:** gắn service account phù hợp cho VM, quản lý quyền IAM và các thiết lập quyền truy cập liên quan; tránh dùng service account có đặc quyền quá rộng.
- **CI/CD ngoài Google Cloud:** sử dụng **Workload Identity Federation** khi môi trường hỗ trợ, trao đổi credential ngắn hạn và thiết lập ràng buộc danh tính từ nguồn tin cậy.

Nếu trường hợp đặc biệt bắt buộc phải dùng khóa, cần có quy trình phát hành, lưu trữ an toàn, luân phiên, phát hiện lộ khóa và thu hồi. Một số tổ chức còn dùng Organization Policy để hạn chế tạo khóa service account.

**Lưu ý:** đối với Cloud Run, Cloud Build, GKE và những dịch vụ managed khác, cần phân biệt service account của **workload**, service account dùng **triển khai**, service agent do dịch vụ Google quản lý và các danh tính của hạ tầng. Không tùy ý gán quyền cho service agent hoặc dùng service agent làm tài khoản ứng dụng.

## 5. Ví dụ kiến trúc quyền cho hệ thống bán hàng trên Google Cloud

Một doanh nghiệp vận hành:

- **Project \`shop-dev\`:** môi trường phát triển và thử nghiệm.
- **Project \`shop-prod\`:** Cloud Run \`checkout-api\`, Cloud SQL lưu đơn hàng, Cloud Storage bucket \`shop-invoices\` và VPC.
- **Pipeline CI/CD:** chạy kiểm tra, lấy image đã kiểm soát và cập nhật Cloud Run production.
- **Nhóm vận hành và kiểm toán:** giám sát hiệu năng, tính tin cậy, quyền IAM, mạng và chi phí.

### 5.1. Ma trận phân quyền minh họa

| Principal | Tài nguyên/phạm vi | Quyền hoặc role gợi ý | Không nên có |
| --- | --- | --- | --- |
| Nhóm developers | Project \`shop-dev\` | Role phù hợp để phát triển và debug các dịch vụ dev | Owner tại organization, quyền sửa IAM production |
| Nhóm production readers | Log và trạng thái workload production cần kiểm tra | \`roles/logging.viewer\`, role đọc dịch vụ phù hợp | Quyền chỉnh policy, thay database |
| Pipeline deploy | Cloud Run \`checkout-api\` ở \`shop-prod\` | Quyền cập nhật dịch vụ theo phạm vi hỗ trợ của Cloud Run; ví dụ \`roles/run.developer\` khi phù hợp | Owner/Editor toàn project, quyền xem toàn bộ dữ liệu đơn hàng |
| Pipeline deploy | Service account \`checkout-runtime\` | \`roles/iam.serviceAccountUser\` trên **service account cụ thể** | Quyền actAs mọi service account production |
| Runtime checkout | Cloud SQL và bucket cần dùng | \`roles/cloudsql.client\` khi dùng kiểu kết nối yêu cầu quyền này; \`roles/storage.objectViewer\` trên bucket nếu chỉ đọc | Cloud SQL Admin, Storage Admin toàn project |
| Đội mạng | Các project hoặc tài nguyên mạng theo phân công | Ví dụ \`roles/compute.networkAdmin\` và role bổ sung khi nhiệm vụ yêu cầu | Quyền quản lý Billing, quyền đọc dữ liệu ứng dụng |
| Nhóm tài chính | Billing account của công ty | Role Billing phù hợp như \`roles/billing.viewer\` cho tác vụ xem | Quyền xóa dữ liệu hoặc triển khai dịch vụ |
| Nhóm kiểm toán | Các tài nguyên được kiểm toán | Ví dụ \`roles/iam.securityReviewer\` theo phạm vi; role xem log cần thiết | Quyền sửa IAM, trừ khi được giao riêng nhiệm vụ khắc phục |

Đây là **đề xuất để thảo luận**, không phải bảng role đầy đủ có thể áp nguyên xi. Quyền Cloud Run có thể còn cần truy cập Artifact Registry, danh tính triển khai có thể cần các permission bổ sung để cập nhật nguồn image, và kết nối Cloud SQL vẫn cần xác thực/phân quyền **bên trong database**. Trước khi triển khai, đối chiếu từng thao tác thực tế với permission và tài nguyên được dịch vụ hỗ trợ.

### 5.2. Luồng quyền từ code tới database

Khi một lập trình viên thay đổi API, quy trình phát hành có thể là:

1. **Code review:** người khác kiểm tra pull request và đặc biệt chú ý thay đổi IAM, secret, CI workflow và truy cập dữ liệu.
2. **Build/test:** hệ thống chạy kiểm thử với danh tính và quyền phù hợp cho build; không dùng runtime production để biên dịch.
3. **Phê duyệt production:** người có trách nhiệm duyệt bản phát hành sau khi kiểm tra kết quả build và rủi ro.
4. **Deploy:** service account của pipeline cập nhật đúng Cloud Run service và được phép actAs đúng runtime service account.
5. **Run:** \`checkout-runtime\` chỉ gọi API Google Cloud cần cho đơn hàng; quyền ở Cloud SQL database tiếp tục hạn chế truy vấn/bảng phù hợp.
6. **Audit:** IAM thay đổi, deployment và dữ liệu audit liên quan có thể được kiểm tra qua log, quy trình quản trị và công cụ giám sát.

Nếu lập trình viên tự sửa code, tự duyệt pull request và tự sửa quyền của runtime service account, việc tách nhóm IAM trên giấy sẽ không còn hiệu quả. Bảo mật quyền truy cập cần bao quát **đường đi của thay đổi**, không chỉ bảng role.

### 5.3. Tách production khỏi môi trường thử nghiệm

Tách project dev/prod giúp giảm khả năng cấp quyền nhầm và giới hạn ảnh hưởng của thử nghiệm. Tuy nhiên, nếu đội phát triển được gán Editor tại folder cha chứa cả hai project thì quyền kế thừa có thể làm mất ranh giới mong muốn.

Thiết kế nên kết hợp:

- Folder/project phân biệt theo môi trường hoặc mức nhạy cảm.
- IAM binding với nhóm thành viên rõ ràng, ưu tiên nhóm thay vì thêm từng người nếu tổ chức có cơ chế quản lý thành viên đáng tin cậy.
- Service account riêng theo workload và môi trường; không dùng chung khóa giữa dev và prod.
- Kiểm soát quyền quản trị IAM, đường phát hành, truy cập log nhạy cảm và dữ liệu.
- Rà soát các quyền được kế thừa từ cấp tổ chức trước khi đánh giá quyền thực tế của project.

## 6. Cơ chế hỗ trợ IAM để giảm quyền dư thừa

### 6.1. IAM Conditions

IAM Conditions cho phép ràng buộc binding theo thuộc tính **được dịch vụ hỗ trợ**, chẳng hạn thời điểm hoặc thuộc tính tài nguyên trong những trường hợp nhất định.

Ví dụ, nhóm hỗ trợ sự cố có thể được cấp quyền bổ sung chỉ đến một thời điểm nhất định. Cần kiểm tra role, loại tài nguyên, biểu thức và các thuộc tính được hỗ trợ. Điều kiện không giúp quyền hẹp hơn nếu biểu thức sai, policy bị gán quá rộng hoặc dịch vụ không hỗ trợ thuộc tính mong muốn.

Không dùng IAM Condition làm cách thay thế hoàn toàn việc chọn role và phạm vi chính xác. Quyền tạm thời cũng phải được thu hồi hoặc hết hiệu lực theo kế hoạch, có bản ghi phê duyệt và kiểm tra kết quả.

### 6.2. IAM Deny và principal access boundary

Ngoài allow policy, Google Cloud có các cơ chế quản lý truy cập ở cấp nâng cao:

| Cơ chế | Công dụng chung | Giới hạn cần hiểu |
| --- | --- | --- |
| **IAM Deny** | Ngăn một số principal thực hiện các permission được hỗ trợ, ngay cả khi có allow. | Chỉ áp dụng trong phạm vi permission, điều kiện và quy tắc mà IAM Deny hỗ trợ. |
| **Principal access boundary (PAB)** | Thiết lập giới hạn tài nguyên tối đa mà các principal trong phạm vi policy có thể truy cập, theo cơ chế được hỗ trợ. | Không cấp quyền mới và không thay thế allow policy; hiệu lực còn phụ thuộc loại tài nguyên/permission được hỗ trợ. |
| **Organization Policy** | Kiểm soát các ràng buộc cấu hình, tạo và sử dụng tài nguyên theo constraint. | Không phải một allow role hoặc cơ chế tự động hạn chế mọi permission IAM. |
| **VPC Service Controls** | Bổ sung lớp kiểm soát rủi ro rò rỉ dữ liệu cho dịch vụ/phạm vi hỗ trợ. | Không thay thế IAM, phân quyền cơ sở dữ liệu hoặc bảo vệ ứng dụng. |

Các cơ chế này cần được thiết kế cùng IAM, thử nghiệm với workload thực tế và tham chiếu tài liệu hiện hành của từng tính năng. Một policy chặn quá rộng có thể khiến cả hệ thống hợp lệ gặp lỗi truy cập.

### 6.3. Quyền đặc biệt theo nhu cầu và thời hạn

Với các quyền quản trị mạnh như thay đổi IAM ở cấp cao, cân nhắc quy trình truy cập theo yêu cầu (just-in-time), có người phê duyệt và thời hạn rõ ràng. **Privileged Access Manager (PAM)** của Google Cloud là một khả năng có thể dùng trong những kịch bản và phạm vi được hỗ trợ; việc dùng được hay không cần xác minh điều kiện sản phẩm, quyền quản trị và phạm vi truy cập hiện hành.

Đối với tài khoản khẩn cấp, cần có cơ chế bảo vệ xác thực mạnh, người chịu trách nhiệm giám sát, ghi nhận lý do sử dụng và rà soát sau sự cố. Tài khoản “break-glass” không nên là tài khoản dùng hàng ngày.

## 7. Quy trình cấp quyền, xác minh và thu hồi

### 7.1. Chuẩn bị trước khi thay đổi policy

Trước khi thêm một binding IAM vào production, tạo bản ghi thay đổi bao gồm:

1. **Principal:** địa chỉ nhóm hoặc service account chính xác; tránh nhầm project trong email service account.
2. **Tác vụ:** thao tác API cần làm, thời điểm và lý do cần thiết.
3. **Resource:** Project ID và tài nguyên cụ thể; xác định quyền nào có thể được kế thừa.
4. **Role và permission:** đối chiếu vai trò định cấp với các permission bắt buộc.
5. **Tính gián tiếp:** principal có thể impersonate danh tính khác, thay pipeline hay tạo workload sử dụng account mạnh không?
6. **Thời hạn:** quyền lâu dài, quyền phục vụ công việc tạm thời hay quyền khẩn cấp.
7. **Người duyệt và kịch bản kiểm thử:** ai xác nhận rủi ro, thao tác nào phải thành công và thao tác nào phải thất bại.

Với thay đổi IAM lớn hoặc nhạy cảm, quản lý policy bằng mã cấu hình, pull request và cơ chế review giúp theo dõi lịch sử. Cần tránh dùng hai cơ chế quản lý policy độc lập cùng ghi lên một binding mà không có nguyên tắc sở hữu rõ ràng.

### 7.2. Kiểm tra bằng Google Cloud CLI

Giả sử danh tính hiện tại có quyền xem policy trên project \`shop-prod\` và service account \`checkout-runtime\`. Các lệnh sau chỉ đọc:

~~~bash
# Xem các binding IAM gắn trực tiếp trên project
gcloud projects get-iam-policy shop-prod --format=json

# Xem các binding IAM trực tiếp trên service account cụ thể
gcloud iam service-accounts get-iam-policy \
  checkout-runtime@shop-prod.iam.gserviceaccount.com \
  --project=shop-prod

# Đọc các permission nằm trong predefined role
gcloud iam roles describe roles/run.developer
~~~

**Không kết luận người dùng không có quyền chỉ vì không thấy binding ở policy trực tiếp.** Quyền có thể được kế thừa từ folder hoặc organization; qua nhóm hoặc danh tính khác; hoặc bị ảnh hưởng bởi deny, điều kiện và các giới hạn bổ sung. Trường hợp cần xác định nguyên nhân chính xác cho một quyết định truy cập, sử dụng công cụ phân tích hiệu lực như **Policy Troubleshooter** và những công cụ IAM Policy Intelligence phù hợp.

Ví dụ binding trên Cloud Storage bucket dành cho runtime đọc object (lệnh minh họa có tác động ghi):

~~~bash
# Chỉ thực hiện sau khi đã duyệt phạm vi và danh tính
gcloud storage buckets add-iam-policy-binding gs://shop-invoices \
  --member="serviceAccount:checkout-runtime@shop-prod.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
~~~

Tình huống trên giới hạn vai trò đọc object ở bucket được chỉ định; việc gán ở project sẽ rộng hơn nếu project có nhiều bucket. Trước khi áp dụng thật, phải kiểm tra bucket đã tồn tại, principal đúng, IAM policy và các điều kiện sử dụng của bucket. Đối với dữ liệu có nhiều mức nhạy cảm trong cùng bucket, tiếp tục đánh giá xem phạm vi đọc tất cả object có quá rộng hay không.

**Ví dụ lỗi thiết kế:** thay vì role đọc object ở bucket, nhóm cấp \`roles/storage.admin\` trên \`shop-prod\` cho runtime để tránh lỗi Permission denied. Điều này có thể trao quyền quản lý nhiều tài nguyên lưu trữ ngoài nhu cầu nghiệp vụ. Phương án đúng là đọc thông báo lỗi, xác định permission bị thiếu và cấp quyền tối thiểu đúng chỗ.

### 7.3. Xác minh hai chiều

Một thay đổi IAM chỉ đạt yêu cầu khi chứng minh được cả hai điều:

- **Tác vụ cần thiết hoạt động:** ví dụ runtime API đọc được object được phép, kết nối Cloud SQL qua cơ chế đã thiết kế, còn pipeline deploy được revision đúng service.
- **Tác vụ ngoài phạm vi bị từ chối:** ví dụ runtime không xóa bucket, không sửa IAM project, không impersonate service account quản trị; pipeline không được cấp role cho chính mình.

Có thể dùng môi trường thử nghiệm, lệnh kiểm tra phù hợp và **Policy Troubleshooter** để phân tích permission trên tài nguyên cụ thể. Với thay đổi policy diện rộng, cân nhắc **Policy Simulator** khi tính năng và phạm vi tài nguyên được hỗ trợ để đánh giá ảnh hưởng trước khi áp dụng.

Kết quả mô phỏng hoặc thao tác API thành công không phải là bằng chứng duy nhất. Vẫn cần xét nhóm IAM, quyền kế thừa, các principal dùng chung đường phát hành và dữ liệu thực tế mà workload truy cập.

### 7.4. Rà soát và thu hồi

Đặc quyền nên gắn với **nhiệm vụ hiện tại**, không gắn vĩnh viễn với lịch sử của người dùng. Một quy trình quản trị định kỳ có thể gồm:

1. Đối soát danh sách nhóm và service account với nhân sự, chủ ứng dụng và pipeline đang hoạt động.
2. Xem gợi ý của IAM Recommender (nếu đủ điều kiện), lịch sử sử dụng quyền và bằng chứng nghiệp vụ để xác định role ít dùng.
3. Kiểm tra binding Owner/Editor, vai trò quản trị IAM, quyền Token Creator, quyền actAs và binding cấp ở organization/folder.
4. Rà soát principal công khai như \`allUsers\` hoặc \`allAuthenticatedUsers\`, đặc biệt trên tài nguyên chứa dữ liệu nhạy cảm. Các dịch vụ công khai có thể cần cấu hình riêng nhưng phải là quyết định có chủ đích.
5. Gỡ quyền người đã đổi nhóm, account thử nghiệm hết hạn và service account không còn workload sử dụng.
6. Thử lại luồng nghiệp vụ sau thu hồi, ghi nhận ai duyệt và lý do.

Recommender và thông tin usage chỉ là **gợi ý**, có thể không bao quát đường chạy hiếm nhưng quan trọng, chẳng hạn khôi phục thảm họa. Trước khi gỡ quyền, hãy đối chiếu runbook và nhu cầu nghiệp vụ ít xảy ra.

## 8. Theo dõi và điều tra truy cập

### 8.1. Audit logs và nguồn bằng chứng

**Cloud Audit Logs** giúp quan sát hoạt động truy cập hoặc quản lý tài nguyên theo loại log được cung cấp và cấu hình. Ví dụ:

| Loại thông tin | Câu hỏi điều tra |
| --- | --- |
| **Admin Activity** | Ai đã thay đổi IAM policy, cấu hình tài nguyên hoặc thông tin quản trị? |
| **Data Access** | Danh tính nào đã đọc/ghi dữ liệu qua API được log, nếu loại log này được bật và hỗ trợ? |
| **System Event** | Có thay đổi từ hoạt động hệ thống Google Cloud nào liên quan đến sự cố không? |
| **Policy Denied** | Có yêu cầu nào bị từ chối bởi một cơ chế policy được ghi log không? |

Khả năng ghi nhận dữ liệu audit, mặc định bật/tắt, quyền xem các loại log và thời gian lưu tùy sản phẩm, loại sự kiện và cấu hình. **Data Access logs** có thể cần được bật và có thể chứa thông tin nhạy cảm; người xem log cũng cần phân quyền phù hợp. Audit logs giúp điều tra nhưng không bảo đảm ghi lại mọi hoạt động bên trong một cơ sở dữ liệu hoặc ứng dụng mà không có cơ chế log riêng.

Nên thiết lập cảnh báo hoặc quy trình rà soát cho các sự kiện đáng chú ý: thay đổi IAM ở organization/folder, gán role đặc quyền, thay đổi service account, tạo khóa lâu dài, sửa cấu hình pipeline triển khai hoặc truy cập bất thường vào dữ liệu nhạy cảm.

### 8.2. Khi gặp lỗi Permission denied

Một lỗi 403 có thể xuất phát từ IAM, nhưng cũng có thể liên quan xác thực, quota, cấu hình API, Organization Policy hoặc phân quyền riêng trong sản phẩm. Phân tích theo thứ tự:

1. **Danh tính thực tế là ai?** Kiểm tra tài khoản đăng nhập, active gcloud configuration, service account attached, ADC và token mà workload dùng.
2. **Thao tác bị từ chối là gì?** Tìm permission được API yêu cầu; xác định tài nguyên mục tiêu và project chứa tài nguyên.
3. **Binding được cấp ở đâu?** Xem policy trực tiếp, quyền kế thừa, thành viên nhóm và điều kiện.
4. **Có ràng buộc phủ quyết không?** Kiểm tra IAM Deny, principal access boundary, Organization Policy, tình trạng API và các yêu cầu khác được dịch vụ hỗ trợ.
5. **Workload có đường truy cập dữ liệu riêng không?** Ví dụ Cloud SQL IAM/connector và user database là các lớp khác nhau; quyền kết nối không tự cấp quyền \`SELECT\` trên bảng.
6. **Đã cấp quyền nhưng chưa có hiệu lực?** Có thể cần thời gian lan truyền thay đổi IAM hoặc làm mới thông tin xác thực; kiểm tra lại có kiểm soát.

Không giải quyết mọi lỗi 403 bằng cách cấp Editor hoặc Owner. Nếu một tài khoản thật sự cần permission còn thiếu, cấp đúng permission thông qua role phù hợp và ghi lại nguyên nhân.

## 9. Bài tập thiết kế quyền

### Tình huống

Ứng dụng \`order-api\` chạy trên Cloud Run trong project \`orders-prod\`. Dữ liệu đơn hàng được lưu trong Cloud SQL; hóa đơn PDF đặt ở bucket \`orders-invoices\`. Một pipeline được phép phát hành mỗi tuần, nhóm hỗ trợ chỉ cần đọc log để xử lý sự cố, và đội tài chính theo dõi ngân sách qua Cloud Billing.

Ban đầu, cả bốn nhóm cùng dùng tài khoản \`team-admin\` với Owner trên project. Runtime của API sử dụng service account mặc định và nhóm phát triển có thể thay đổi trực tiếp pipeline production.

**Yêu cầu:** thiết kế lại quyền để giảm ảnh hưởng của một danh tính bị lộ, đồng thời duy trì được quá trình phát hành, vận hành, giám sát chi phí và khôi phục sự cố.

### Nhiệm vụ thực hành

1. Lập danh sách ít nhất **sáu danh tính** gồm nhóm phát triển, người duyệt release, pipeline, runtime API, nhóm tài chính và kiểm toán. Mô tả tác vụ của từng danh tính.
2. Lập **ma trận principal – permission/role – tài nguyên – thời hạn – người duyệt**. Chỉ ra role nào nên nằm ở bucket, service account, project hoặc Billing account.
3. Phân biệt quyền của pipeline cập nhật \`order-api\` với quyền của runtime đọc object/kết nối Cloud SQL. Nêu lý do không dùng chung một service account cho cả hai.
4. Vẽ một đường leo thang đặc quyền có thể xảy ra nếu pipeline có thể actAs mọi service account production; đề xuất hai lớp kiểm soát để chặn đường này.
5. Xây dựng cơ chế phê duyệt phát hành và IAM: người làm pull request, người review, người thay policy, người audit có thể trùng nhau ở điểm nào và không nên trùng nhau ở điểm nào?
6. Lập hai ca kiểm thử: một yêu cầu **phải được cho phép** và một yêu cầu **phải bị từ chối** đối với runtime API.
7. Viết quy trình thu hồi quyền khi nhân sự chuyển nhóm hoặc pipeline được thay thế; xác định dấu vết audit cần lưu.

### Gợi ý giải pháp

| Vấn đề ban đầu | Cách cải thiện |
| --- | --- |
| Tất cả dùng \`team-admin\` | Cấp danh tính riêng theo người, nhóm và workload; bảo vệ tài khoản đặc quyền bằng quy trình riêng. |
| Runtime dùng service account mặc định có quyền không rõ | Tạo runtime service account chuyên trách, chỉ gán role trên tài nguyên thực sự cần; kiểm tra quyền kế thừa. |
| Pipeline deploy với Owner | Cấp quyền cập nhật Cloud Run và quyền actAs **đúng runtime service account**, không cấp quyền sửa IAM project nếu không cần. |
| Tài chính cần xem ngân sách | Gán quyền Cloud Billing thích hợp tại Billing account, tách khỏi quyền truy cập dữ liệu đơn hàng. |
| Không kiểm soát được thay đổi production | Yêu cầu review, phê duyệt phù hợp, log thay đổi và giới hạn quyền trên pipeline. |
| Không có quy trình kiểm tra sau cấp quyền | Thử cả truy cập hợp lệ và truy cập phải bị từ chối; theo dõi audit và rà soát định kỳ. |

### Câu hỏi tự kiểm tra

**1. Vì sao vai trò \`roles/run.developer\` chưa đủ để khẳng định pipeline không thể truy cập dữ liệu production?**  
Vì pipeline có thể thay đổi code hoặc cấu hình workload chạy bằng runtime service account; cần đánh giá cả quyền sử dụng service account, quyền của runtime và cơ chế review phát hành.

**2. Vai trò Service Account User có đồng nghĩa với Token Creator không?**  
Không. Đây là những quyền khác nhau; nhưng cả hai có thể góp phần vào leo thang đặc quyền khi kết hợp với quyền quản lý workload hay khi được cấp trên danh tính quá mạnh.

**3. Vì sao không thể chỉ đọc IAM policy trực tiếp trên project để xác định toàn bộ quyền?**  
Vì IAM allow có thể kế thừa từ folder/organization và nhiều cơ chế kiểm soát khác ảnh hưởng đến quyết định truy cập.

**4. Vì sao chỉ tách project dev và prod chưa đủ?**  
Vì role cấp ở folder cha, group chung, service account chia sẻ hoặc pipeline có quyền vượt môi trường vẫn có thể phá vỡ ranh giới.

**5. Khi một permission cần cho quy trình khôi phục hiếm khi dùng, có nên gỡ ngay vì IAM Recommender cho rằng nó ít sử dụng không?**  
Không nên gỡ chỉ dựa vào thống kê. Cần đánh giá kịch bản khôi phục, cân nhắc cấp quyền khẩn cấp có thời hạn và kiểm thử runbook.

## Tài liệu Google Cloud để tra cứu khi triển khai

- **IAM overview:** https://cloud.google.com/iam/docs/overview — danh tính, permission, role và policy.
- **Resource hierarchy và IAM:** https://cloud.google.com/iam/docs/resource-hierarchy-access-control — phạm vi cấp quyền và kế thừa.
- **Use IAM securely:** https://cloud.google.com/iam/docs/using-iam-securely — thực hành quản lý quyền an toàn.
- **IAM Conditions:** https://cloud.google.com/iam/docs/conditions-overview — điều kiện và các trường hợp được hỗ trợ.
- **IAM Deny:** https://cloud.google.com/iam/docs/deny-overview — chính sách từ chối quyền truy cập.
- **Service accounts:** https://cloud.google.com/iam/docs/service-account-overview — danh tính workload, impersonation và cách quản lý.
- **Workload Identity Federation:** https://cloud.google.com/iam/docs/workload-identity-federation — liên kết danh tính workload bên ngoài Google Cloud.
- **Privileged Access Manager:** https://cloud.google.com/iam/docs/privileged-access-manager — quản lý quyền đặc biệt theo yêu cầu.
- **Cloud Audit Logs:** https://cloud.google.com/logging/docs/audit — các loại log và phạm vi thu thập.
- **IAM Policy Intelligence:** https://cloud.google.com/iam/docs/using-policy-intelligence — đánh giá và khắc phục những quyền không phù hợp.

Tên role, danh sách permission, phạm vi gán binding và khả năng hỗ trợ những cơ chế nâng cao có thể thay đổi. Khi triển khai thực tế, luôn đối chiếu tài liệu IAM theo dịch vụ, chính sách tổ chức và thao tác API đang sử dụng trước khi cấp quyền trên môi trường production.
