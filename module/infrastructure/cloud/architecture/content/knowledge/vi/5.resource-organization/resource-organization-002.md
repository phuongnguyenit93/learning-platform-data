# Phân cấp tổ chức, tài khoản, subscription và project

Trong thiết kế kiến trúc ứng dụng trên đám mây, câu hỏi đầu tiên thường là ứng dụng cần mạng, máy chủ, container, cơ sở dữ liệu và dịch vụ nào. Nhưng trước khi triển khai những tài nguyên đó, nhóm cần trả lời một câu hỏi có ảnh hưởng lâu dài: **mỗi tài nguyên sẽ thuộc phạm vi quản trị nào?**

Cloud cung cấp nhiều tầng tổ chức như **organization**, **account**, **subscription**, **project**, **folder**, **management group** và **resource group**. Chúng giúp quản lý quyền truy cập, chính sách bảo mật, chi phí, hạn mức và vòng đời môi trường. Đặt tài nguyên đúng cấp từ đầu giúp ứng dụng mở rộng mà không biến việc phân quyền, kiểm toán và phân bổ ngân sách thành một tập hợp ngoại lệ khó kiểm soát.

Bài học thuộc chương **Tổ chức tài nguyên** của module **CLOUD_ARCHITECTURE**. Mục tiêu là thiết kế một hệ phân cấp phục vụ yêu cầu nghiệp vụ và lựa chọn hạ tầng cloud, hiểu các đánh đổi giữa độ tin cậy, bảo mật, mở rộng, chi phí và vận hành, rồi kiểm tra phương án bằng các câu hỏi Well-Architected.

## 1. Vì sao hệ phân cấp tài nguyên là một quyết định kiến trúc?

Giả sử một công ty có ứng dụng đặt chỗ trực tuyến với môi trường phát triển (**dev**), kiểm thử (**staging**) và sản xuất (**prod**). Nếu tất cả tài nguyên dùng chung một phạm vi quản trị, các rủi ro sau dễ xuất hiện:

- Người phát triển được cấp quyền rộng để thử nghiệm và vô tình sửa hoặc xóa cơ sở dữ liệu prod.
- Một hệ thống kiểm thử dùng tài nguyên quá mức, cạnh tranh hạn mức dịch vụ với hệ thống sản xuất.
- Chi phí compute, database và lưu lượng mạng khó phân bổ cho từng sản phẩm hoặc nhóm.
- Một chính sách mạng hoặc mã hóa áp dụng sai có thể ảnh hưởng đồng thời nhiều workload.
- Việc bàn giao quyền sở hữu, ngừng một môi trường hoặc đáp ứng yêu cầu kiểm toán trở nên phức tạp.

Tổ chức tài nguyên giúp thiết lập **ranh giới quản lý có chủ đích**. Chẳng hạn, tách prod khỏi dev ở cấp account, subscription hoặc project thích hợp thường tạo ranh giới mạnh hơn so với chỉ đặt tên tài nguyên khác nhau trong cùng một phạm vi.

Tuy nhiên, hệ phân cấp **không tự tạo ra tính an toàn hay khả dụng**. Nếu hai môi trường vẫn dùng chung bí mật, mạng, tài khoản quản trị hoặc hệ thống dữ liệu quan trọng, rủi ro vẫn có thể lan truyền. Các ranh giới tổ chức phải đi kèm phân quyền, thiết kế mạng, cấu hình chính sách và vận hành thực tế.

### Các từ khóa cần phân biệt

| Thuật ngữ | Ý nghĩa tổng quát | Không nên suy diễn |
|---|---|---|
| **Organization** | Cấp quản lý tổ chức, thường chứa nhiều đơn vị tài nguyên cấp thấp hơn và là nơi áp dụng quản trị tập trung | Không đồng nghĩa với một vùng triển khai hoặc một mạng duy nhất |
| **Account** | Trong AWS, tài khoản là phạm vi quan trọng của tài nguyên, danh tính, giới hạn và hóa đơn/chi phí | Không phải cùng khái niệm với tài khoản đăng nhập của một nhân viên |
| **Subscription** | Trong Azure, phạm vi triển khai, quản lý truy cập, chính sách, tiêu thụ và tính phí cho tài nguyên | Không tương đương một-một với Azure resource group |
| **Project** | Trong Google Cloud, phạm vi cơ bản chứa tài nguyên, bật API, cấp quyền và gắn thanh toán | Không phải chỉ là tên dự án phần mềm hoặc một nhánh Git |
| **Folder / Organizational Unit (OU)** | Nhóm các đơn vị trực thuộc để quản lý hoặc kế thừa chính sách, tùy nhà cung cấp | Thường không phải nơi trực tiếp chứa mọi loại tài nguyên workload |
| **Management group** | Cấp quản lý phía trên subscription của Azure để áp dụng quyền và chính sách nhất quán | Không phải nhóm máy ảo hoặc một hệ thống mạng |
| **Resource group** | Phạm vi gom và quản lý tài nguyên trong Azure, thường theo ứng dụng hoặc vòng đời | Không phải một tenant hay một subscription mới |

Điểm quan trọng: các thuật ngữ khác nhau giữa các nhà cung cấp. Không nên cố lập bảng quy đổi “một account = một subscription = một project” theo nghĩa tuyệt đối. Chúng có một số vai trò tương tự trong thiết kế cô lập workload, nhưng cấu trúc danh tính, billing, hạn mức và phạm vi chính sách không giống nhau.

## 2. Hệ phân cấp tiêu biểu của AWS, Azure và Google Cloud

### 2.1. AWS: Organization → OU → account → resources

AWS Organizations cho phép quản lý tập trung nhiều tài khoản AWS. Một tổ chức có **management account**, các **member account**, một **root** và tùy chọn các **organizational unit (OU)** lồng nhau. Account thuộc một vị trí trong cây tổ chức; các dịch vụ và tài nguyên chạy trong account đó, thường còn gắn với một Region hoặc Availability Zone tùy loại dịch vụ.

~~~mermaid
flowchart TD
    ORG["AWS Organization"] --> ROOT["Root"]
    ROOT --> SEC["OU: Security"]
    ROOT --> W["OU: Workloads"]
    ROOT --> S["OU: Sandbox"]
    SEC --> LOG["Account: Central logging"]
    SEC --> AUDIT["Account: Security audit"]
    W --> PROD["OU: Production"]
    W --> NONPROD["OU: Non-production"]
    PROD --> APPP["Account: Booking prod"]
    PROD --> PAYP["Account: Payment prod"]
    NONPROD --> APPD["Account: Booking dev/staging"]
    S --> EXP["Account: Experiments"]
    APPP --> R1["VPC, compute, database, logs..."]
~~~

**Tầng account** là ranh giới quan trọng để phân tách quyền, tài nguyên và nhiều hạn mức. **OU** chủ yếu giúp nhóm account và gắn chính sách quản trị; OU không tự trở thành một mạng hoặc một cơ sở dữ liệu. Các account có thể được quản lý thống nhất về quyền truy cập qua AWS IAM Identity Center, kiểm toán, logging và chính sách tổ chức.

Một số điểm cần nhớ:

- **Service Control Policy (SCP)** trong AWS Organizations giới hạn quyền tối đa có thể được sử dụng trong member account thuộc phạm vi áp dụng; SCP **không tự cấp quyền**. Quyền thực tế còn phụ thuộc IAM và các cơ chế đánh giá quyền liên quan.
- **Management account** có đặc quyền tổ chức và cần được bảo vệ nghiêm ngặt; thông thường tránh đặt workload ứng dụng hằng ngày trong account này.
- **Consolidated billing** giúp tổng hợp thanh toán trong organization, nhưng vẫn cần cấu trúc account, thẻ phân bổ chi phí và báo cáo để xác định chi phí từng workload.
- **Region** và **Availability Zone** là chiều triển khai hạ tầng, không phải các cấp thay thế OU hoặc account.

### 2.2. Microsoft Azure: tenant → management group → subscription → resource group → resources

Azure có nhiều cấp cần phân biệt. **Microsoft Entra tenant** là phạm vi danh tính và thư mục người dùng/ứng dụng. Trong quản lý tài nguyên bằng Azure Resource Manager, các **management group** tạo cây quản trị phía trên **subscription**, rồi đến **resource group** và tài nguyên. Subscription được liên kết với một Entra tenant tại một thời điểm; cấu trúc **billing account/billing profile** thuộc hệ thống thanh toán và không nhất thiết phản ánh cây management group.

~~~mermaid
flowchart TD
    TEN["Microsoft Entra tenant: danh tính"] -. "liên kết thư mục" .-> MG["Tenant root management group"]
    MG --> P["Management group: Production"]
    MG --> N["Management group: Non-production"]
    P --> SP1["Subscription: Booking prod"]
    P --> SP2["Subscription: Payments prod"]
    N --> SD["Subscription: Development"]
    N --> ST["Subscription: Staging"]
    SP1 --> RG1["Resource group: app"]
    SP1 --> RG2["Resource group: data"]
    RG1 --> APP["App service, container, network..."]
    RG2 --> DB["Database, storage..."]
~~~

Các scope quản lý quyền và chính sách thường kế thừa theo chiều **management group → subscription → resource group → resource**. Azure RBAC quy định ai có quyền thao tác; Azure Policy đặt ra các quy tắc quản trị như yêu cầu tag, giới hạn vị trí hoặc cấu hình được phép. Ngoài ra có các loại cơ chế khác như deny assignment và khóa tài nguyên, với hành vi riêng cần xác minh.

Một số điểm cần nhớ:

- **Subscription** thường là đơn vị quan trọng để phân tách môi trường, hạn mức và quản trị chi phí. Không phải mọi quota đều được tính giống nhau: phạm vi có thể là subscription, Region, loại dịch vụ hoặc tổ hợp của chúng.
- **Resource group** gom tài nguyên theo nhu cầu quản lý/vòng đời. Một resource group có trường location cho metadata, nhưng **tài nguyên trong nhóm có thể được tạo ở các Region khác nhau** khi loại tài nguyên cho phép.
- **Entra tenant** liên quan đến danh tính; **subscription** liên quan đến tài nguyên/tiêu thụ; **billing scopes** liên quan đến thanh toán. Chúng liên hệ với nhau nhưng không phải cùng một hệ phân cấp.
- Quyền gán ở scope cao có thể tác động rộng. Thay đổi ở root management group cần quy trình quản trị và thử nghiệm chặt chẽ.

### 2.3. Google Cloud: organization → folders → projects → resources

Google Cloud cung cấp **organization resource**, các **folder** tùy chọn để nhóm và quản lý dự án, rồi đến **project** chứa phần lớn tài nguyên dịch vụ. Nhiều dịch vụ phải được bật API trong project trước khi sử dụng. **Billing account** được liên kết với project theo mô hình thanh toán; billing account không phải một nhánh của cây organization → folder → project.

~~~mermaid
flowchart TD
    O["Google Cloud Organization"] --> F1["Folder: Production"]
    O --> F2["Folder: Non-production"]
    O --> FS["Folder: Security"]
    F1 --> BP["Project: booking-prod"]
    F1 --> PP["Project: payments-prod"]
    F2 --> BD["Project: booking-dev"]
    F2 --> BS["Project: booking-staging"]
    FS --> LP["Project: central-logging"]
    BP --> RES["Compute, VPC, database, storage..."]
    BILL["Cloud Billing account"] -. "liên kết thanh toán" .-> BP
    BILL -.-> PP
    BILL -.-> BD
~~~

Google Cloud IAM và Organization Policy hỗ trợ quản trị theo các scope phù hợp, với cơ chế kế thừa từ organization/folder xuống project và tài nguyên. Folder hữu ích để đặt chính sách dùng chung cho nhóm project. **Project** là đơn vị rất quan trọng cho IAM, bật API, giới hạn tài nguyên và phân bổ chi phí; **project ID** là định danh ổn định nên cần đặt theo quy ước từ đầu.

Một số điểm cần nhớ:

- **Organization Policy** đặt ràng buộc quản trị; việc có thể thực hiện một thao tác còn phụ thuộc quyền IAM và các hạn chế liên quan.
- **Cloud Billing account** thanh toán cho các project được liên kết. Một project cần liên kết với billing account hợp lệ để dùng các dịch vụ có tính phí theo yêu cầu của nền tảng.
- Cấu hình **Shared VPC** có thể cho các service project sử dụng mạng từ host project theo phân quyền, nhưng việc dùng chung mạng cần đánh giá cô lập và trách nhiệm vận hành.
- Một số project có thể tồn tại không nằm dưới organization trong các tình huống cụ thể; với doanh nghiệp, nên quản lý project thuộc organization được kiểm soát để có chính sách và khả năng kiểm kê nhất quán.

### 2.4. Đối chiếu đúng mục đích

| Nhu cầu kiến trúc | AWS | Azure | Google Cloud |
|---|---|---|---|
| Quản trị nhiều môi trường/workload | AWS Organizations | Management groups và subscriptions | Organization và folders |
| Phạm vi chính để cô lập workload | Account | Subscription | Project |
| Nhóm đơn vị con cho quản trị | OU | Management group | Folder |
| Nhóm tài nguyên liên quan ở cấp nhỏ | Thẻ tài nguyên, cấu trúc theo dịch vụ và công cụ quản lý; không có thực thể Resource Group tương đương hoàn toàn | Resource group | Project, labels, nhóm dịch vụ và cơ chế quản lý tài nguyên |
| Chính sách quản trị tập trung | SCP và các loại policy của Organizations | Azure Policy, Azure RBAC theo scope | Organization Policy, IAM theo scope |
| Quản lý thanh toán tập trung | Consolidated billing | Billing account/profile và subscription theo mô hình hợp đồng | Cloud Billing account liên kết project |

**Không dùng bảng này làm bản đồ chuyển đổi tự động.** Ví dụ, Azure resource group không là ranh giới cô lập tương đương một AWS account; Google Cloud project cũng có những hành vi IAM, networking và quota khác AWS account. Trước khi quyết định ranh giới, phải kiểm tra cơ chế cụ thể của nền tảng đang dùng.

## 3. Hệ phân cấp quản trị và sơ đồ triển khai là hai chiều khác nhau

Một hệ phân cấp có thể mô tả **ai sở hữu và kiểm soát tài nguyên**; sơ đồ triển khai mô tả **tài nguyên ở Region/AZ nào, kết nối mạng ra sao, phụ thuộc dịch vụ nào**. Cả hai liên quan nhưng không thay thế nhau.

Ví dụ, trong một AWS account dành cho Booking prod có thể có mạng riêng, các subnet ở nhiều Availability Zone, nhiều API instance và một database được quản lý. Ngược lại, một Azure subscription có thể chứa các resource group có tài nguyên ở nhiều Region. Google Cloud project có thể chứa tài nguyên khu vực, đa khu vực hoặc toàn cầu tùy dịch vụ.

Do đó, **tách account/subscription/project không tự động tách mạng**, và **triển khai ở nhiều Availability Zone không tự động tách quyền quản trị**. Khi đánh giá blast radius (phạm vi ảnh hưởng khi lỗi hoặc thao tác sai), cần xét đồng thời:

1. **Danh tính và phân quyền:** Ai có thể thay đổi tài nguyên hoặc dữ liệu nào?
2. **Mạng:** Workload có thể kết nối tới đâu? Có dùng chung DNS, NAT, endpoint hoặc mạng lõi không?
3. **Dữ liệu:** Database, backup, khóa mã hóa và secret nằm ở phạm vi nào?
4. **Hạn mức:** Một workload có thể dùng hết quota mà workload khác phụ thuộc không?
5. **Thay đổi:** Cùng một pipeline hoặc quyền quản trị có thể sửa đồng loạt bao nhiêu môi trường?
6. **Phụ thuộc vận hành:** Log, identity, CI/CD hoặc dịch vụ chia sẻ gặp sự cố có ảnh hưởng đến những hệ thống nào?

Đây là lý do phân cấp tài nguyên thuộc thiết kế kiến trúc, không chỉ là việc đặt tên folder cho gọn.

## 4. Chọn ranh giới cho môi trường, sản phẩm và nhóm

Quy tắc thường hiệu quả là ưu tiên **cô lập prod và non-prod**, sau đó cân nhắc tách theo sản phẩm, nhóm sở hữu, độ nhạy cảm dữ liệu và yêu cầu vận hành.

| Tiêu chí | Khi nên tách ở cấp account/subscription/project | Khi có thể nhóm chung có kiểm soát |
|---|---|---|
| **Môi trường** | Prod cần quyền, quota và thay đổi độc lập khỏi dev/test | Nhiều môi trường thử nghiệm nhỏ, cùng mức rủi ro và có chính sách rõ |
| **Chủ sở hữu** | Hai đội có trách nhiệm vận hành hoặc ngân sách độc lập | Một đội quản lý cùng vòng đời, cùng quy định và quy trình |
| **Dữ liệu** | Dữ liệu nhạy cảm hoặc phạm vi pháp lý khác nhau | Workload cùng phân loại dữ liệu và kiểm soát phù hợp |
| **Blast radius** | Một cấu hình sai có thể gây gián đoạn hệ thống trọng yếu khác | Hệ thống thử nghiệm có thể chấp nhận ảnh hưởng chung |
| **Quota/giới hạn** | Tải hoặc giới hạn theo phạm vi có nguy cơ cạnh tranh | Tải nhỏ, có giám sát và cơ chế kiểm soát |
| **Chi phí** | Cần ngân sách, chargeback hoặc trách nhiệm tài chính riêng | Chi phí nhỏ, đã có phân bổ bằng tag/label đủ chính xác |
| **Vòng đời** | Một sản phẩm/môi trường có lịch tạo, xóa và phát hành độc lập | Các tài nguyên luôn được triển khai và thu hồi cùng nhau |

### Ba mô hình thường gặp

**Mô hình A — Tách theo môi trường.** Một phạm vi prod, một staging, một dev. Phù hợp cho nhóm nhỏ có vài workload cùng chủ sở hữu. Ưu điểm là đơn giản; nhược điểm là các sản phẩm trong prod có thể còn chia sẻ quyền, quota và chính sách.

**Mô hình B — Tách theo sản phẩm × môi trường.** Ví dụ Booking-prod, Booking-dev, Payments-prod và Payments-dev. Tăng cô lập và khả năng phân bổ chi phí, phù hợp khi nhiều sản phẩm có quy mô hoặc yêu cầu bảo mật khác nhau. Đổi lại, số account/subscription/project, role, network và pipeline phải được tự động hóa để tránh quá tải vận hành.

**Mô hình C — Kết hợp khu vực chức năng và mức độ nhạy cảm.** Có phạm vi riêng cho security/logging, shared networking, sandbox và workload theo sản phẩm. Phù hợp với tổ chức lớn hoặc chịu ràng buộc kiểm toán, nhưng cần kiểm soát phụ thuộc vào dịch vụ dùng chung và tránh xây nền tảng quá phức tạp so với quy mô.

Không có mô hình duy nhất đúng. Quyết định phải cân đối **rủi ro cô lập** với **chi phí quản trị và vận hành**. Tách mỗi microservice sang một account mới không đương nhiên tốt hơn; cũng không nên giữ mọi hệ thống quan trọng trong một account chỉ để có ít tài nguyên quản lý.

## 5. Phân quyền và chính sách theo cấp: kiểm soát từ trên xuống

Hệ phân cấp phát huy giá trị khi có quy tắc chung được áp dụng nhất quán, và quyền thực thi ở cấp thấp được giao đúng trách nhiệm.

~~~mermaid
flowchart TD
    POL["Chính sách cấp tổ chức"] --> GRP["Nhóm account/subscription/project theo môi trường"]
    GRP --> U1["Workload prod"]
    GRP --> U2["Workload non-prod"]
    POL -. "guardrails chung" .-> U1
    POL -. "guardrails chung" .-> U2
    IAM["Danh tính, role và quyền tối thiểu"] --> U1
    IAM --> U2
    AUD["Kiểm toán và cảnh báo tập trung"] -. "thu nhận sự kiện" .-> U1
    AUD -. "thu nhận sự kiện" .-> U2
~~~

Một thiết kế quản trị thường phân biệt ba lớp:

- **Guardrails bắt buộc:** Ràng buộc vùng triển khai khi có yêu cầu lưu trú dữ liệu; ngăn dùng một số loại tài nguyên hoặc cấu hình không được phép; yêu cầu ghi audit, mã hóa và chính sách bảo vệ dữ liệu theo khả năng của nền tảng.
- **Quyền thao tác:** Nhân viên, nhóm vận hành, workload identity hoặc pipeline được tạo/sửa/đọc/xóa tài nguyên nào, tại scope nào và trong thời gian bao lâu.
- **Phát hiện và phản ứng:** Thu thập log, đánh giá cấu hình, phát hiện vi phạm và xử lý sai lệch, kể cả những vấn đề không thể hoặc không nên chặn ngay từ lúc tạo tài nguyên.

Ví dụ, trong một tổ chức có dịch vụ Booking:

1. Nhóm **platform** có quyền xây dựng template hạ tầng và vận hành cấu phần dùng chung.
2. Nhóm **Booking** có quyền triển khai dịch vụ trong phạm vi Booking-dev và quyền triển khai prod thông qua pipeline được phê duyệt.
3. Nhóm **security** kiểm tra cấu hình, sự kiện truy cập và chính sách chung; chỉ số ít tài khoản đặc quyền được thực hiện thao tác nhạy cảm.
4. Danh tính **ứng dụng** chỉ có quyền cần thiết để đọc secret, ghi log và truy cập dữ liệu được giao; quyền của ứng dụng tách khỏi quyền cá nhân của nhà phát triển.

**Nguyên tắc quyền tối thiểu (*least privilege*)** áp dụng cho cả người lẫn workload. Cấp quyền ở cấp organization/root rộng hơn nhiều so với cấp project hoặc resource; nên ưu tiên scope hẹp đủ để hoàn thành nhiệm vụ. Tăng quyền tạm thời cần thời hạn, ghi nhận và kiểm toán; tài khoản khẩn cấp (*break-glass*) cần bảo vệ, giám sát và diễn tập theo quy trình.

Lưu ý về cơ chế: SCP của AWS và Organization Policy của Google Cloud chủ yếu giới hạn hành vi được phép; chúng không thay thế các quyền IAM cần thiết. Trong Azure, Azure Policy và Azure RBAC cũng giải quyết những câu hỏi khác nhau. Không được suy rằng một chính sách “cho phép” là đã cấp quyền truy cập.

## 6. Mạng và dịch vụ dùng chung: chia sẻ có chủ đích

Tách scope quản trị dẫn đến câu hỏi tiếp theo: dùng mạng và dịch vụ chung hay mỗi workload tự sở hữu?

**Phương án phân tán:** Mỗi account/subscription/project tạo mạng, dịch vụ mạng phụ trợ, log và pipeline riêng. Ranh giới sở hữu rõ, nhưng tốn chi phí và công quản lý nếu lặp lại nhiều cấu phần.

**Phương án tập trung:** Một nhóm tài nguyên hoặc phạm vi trung tâm quản lý mạng lõi, DNS, kết nối tới hệ thống nội bộ, logging, bảo mật hoặc CI/CD. Các workload kết nối qua cơ chế được cho phép, như hub-spoke, peering, transit hoặc shared network tùy nhà cung cấp.

Ví dụ:

- AWS có thể dùng mô hình multi-account, VPC riêng cho workload và kết nối qua cơ chế mạng chung được quản trị.
- Azure có thể dùng hub-spoke virtual network với subscription mạng trung tâm và các subscription workload.
- Google Cloud có thể dùng Shared VPC với host project và các service project nếu cơ chế phân quyền và giới hạn đáp ứng yêu cầu.

Các lựa chọn này **không bắt buộc** và không phải cấu hình sẵn có tương đương tuyệt đối giữa các cloud. Cần thiết kế đường truyền và quyền truy cập thực tế, bao gồm route, DNS, private endpoint, firewall, logging, IP address plan và chi phí truyền dữ liệu.

### Đánh đổi về blast radius

Một dịch vụ DNS hoặc kết nối mạng trung tâm bị cấu hình sai có thể làm nhiều workload mất liên lạc cùng lúc, dù chúng nằm ở các account khác nhau. Ngược lại, nhân bản toàn bộ dịch vụ hạ tầng cho mỗi workload có thể gây lãng phí và tăng số điểm cần vá lỗi. Do đó cần phân biệt:

- **Thành phần có thể chia sẻ an toàn** nhờ khả năng cách ly, dự phòng và vận hành đủ tốt.
- **Thành phần nên tách** vì có dữ liệu nhạy cảm, quyền đặc biệt, tải lớn hoặc yêu cầu khả dụng khác biệt.
- **Thành phần buộc phải có dự phòng và kiểm thử khôi phục** vì là phụ thuộc của nhiều workload.

## 7. Billing, ngân sách, tag/label và quota

Hệ phân cấp cũng là một phần của kiến trúc chi phí. Nhưng **phạm vi thanh toán không đồng nhất với phạm vi tài nguyên**:

- AWS Organizations có thể thanh toán hợp nhất cho nhiều account; chi phí chi tiết cần được phân tích theo account, dịch vụ và thẻ phân bổ chi phí đủ điều kiện.
- Azure có nhiều cấp billing theo loại hợp đồng, trong khi subscription thường là đơn vị hữu ích để phân bổ ngân sách và trách nhiệm tiêu thụ.
- Google Cloud có Cloud Billing account liên kết với nhiều project; project là chiều quan trọng để theo dõi chi phí, kết hợp labels và các trường dữ liệu billing.

### Quy ước metadata tối thiểu

Với tài nguyên hỗ trợ tag/label, có thể áp dụng một bộ khóa được quản trị thống nhất:

| Khóa minh họa | Giá trị ví dụ | Mục đích |
|---|---|---|
| environment | dev, staging, prod | Phân loại môi trường và chính sách |
| application | booking-api | Tìm tài nguyên theo ứng dụng |
| owner | team-booking | Xác định người/nhóm chịu trách nhiệm |
| cost-center | product-platform | Phân bổ chi phí |
| data-classification | internal, confidential | Gắn yêu cầu bảo vệ dữ liệu |
| managed-by | terraform, platform | Nhận diện cơ chế quản lý |
| lifecycle | permanent, temporary | Xác định vòng đời |

Đây là **đề xuất quy ước**, không phải danh sách tag mặc định có sẵn và áp dụng y nguyên trên mọi nhà cung cấp. Một số tài nguyên hoặc dịch vụ không hỗ trợ metadata đầy đủ; tên khóa, chữ hoa/chữ thường và ràng buộc ký tự cũng có thể khác. Với tài nguyên không gắn được tag, cần cách quy thuộc chi phí khác, như phân tách phạm vi quản lý và quy tắc báo cáo.

### Quota không phải mọi thứ đều theo một cấp

Quota và rate limit có thể áp dụng ở cấp account, subscription, project, Region, loại dịch vụ, API hoặc tổ hợp phạm vi. Có giới hạn có thể yêu cầu tăng, có giới hạn cố định hoặc phụ thuộc điều kiện dịch vụ. Khi tách workload cần trả lời:

1. Mỗi hệ thống có bao nhiêu compute, địa chỉ IP, kết nối mạng, dung lượng lưu trữ và request dự kiến?
2. Giới hạn nào có thể cản trở scale-out vào giờ cao điểm?
3. Quota có được dùng chung với workload khác không?
4. Kịch bản failover sang Region khác có cần cấp trước hạn mức hoặc capacity không?
5. Có cảnh báo gần ngưỡng, quy trình xin tăng và phương án giảm tải không?

Ví dụ, việc đưa prod sang một subscription/project riêng có thể giúp quản trị và giảm cạnh tranh đối với **một số** quota, nhưng không bảo đảm mọi quota đều độc lập. Phải xem phạm vi của từng quota cụ thể.

## 8. Landing zone: chuẩn hóa từ lúc tạo phạm vi mới

Khi tổ chức có nhiều account/subscription/project, tạo thủ công từng nơi rất dễ dẫn tới sai lệch cấu hình. **Landing zone** là tập thiết kế và cơ chế khởi tạo môi trường cloud theo chuẩn quản trị. Nó thường bao gồm hệ phân cấp, danh tính, quyền, mạng, logging, bảo mật, billing, quota và tự động hóa.

Một quy trình khởi tạo workload có thể được mô tả như sau:

~~~mermaid
flowchart LR
    R["Yêu cầu tạo workload"] --> C["Phân loại: owner, dữ liệu, môi trường, RTO/RPO"]
    C --> H["Chọn account/subscription/project và nhóm cha"]
    H --> B["Áp baseline chính sách, IAM, audit, mạng"]
    B --> I["Triển khai tài nguyên bằng IaC"]
    I --> V["Kiểm tra policy, bảo mật, chi phí và hoạt động"]
    V --> O["Bàn giao cho team, theo dõi và cải tiến"]
~~~

**Baseline** nên bảo đảm điều kiện tối thiểu cho một môi trường mới:

- Cấu trúc và tên tài nguyên theo quy ước; nhận diện rõ chủ sở hữu, ứng dụng và môi trường.
- Danh tính liên kết với hệ thống đăng nhập tập trung khi phù hợp; role được cấp theo nhu cầu.
- Audit log và log bảo mật thiết yếu được thu thập, bảo vệ khỏi xóa/sửa trái phép và lưu theo chính sách.
- Cấu hình mạng mặc định an toàn; đường kết nối tới dịch vụ dùng chung được xác định rõ.
- Chính sách bảo vệ dữ liệu, mã hóa và quản lý secret ở những dịch vụ phù hợp.
- Budget, cảnh báo chi phí và giám sát quota gắn với đúng chủ sở hữu.
- Hạ tầng quản lý bằng mã (*infrastructure as code — IaC*) và quy trình review thay đổi.

Không nên biến baseline thành cấu hình “một cỡ cho tất cả”. Ví dụ, phòng lab có thể cần TTL ngắn, quota thấp và quyền tạo tài nguyên thử nghiệm; prod xử lý dữ liệu nhạy cảm cần kiểm soát thay đổi, logging và dự phòng cao hơn. Những ngoại lệ cần có lý do, người duyệt, hạn sử dụng và cách rà soát.

### Ví dụ khai báo cấu trúc ở mức logic

Tệp dưới đây chỉ minh họa ý tưởng **một bản thiết kế tổ chức độc lập nhà cung cấp**. Đây không phải cấu hình Terraform hoặc YAML được cloud nào nhận trực tiếp.

~~~yaml
organization: example-company
groups:
  - name: security
    purpose: centralized-audit-and-logging
    units:
      - id: security-logs
        owner: team-security
        environment: shared
  - name: production
    guardrails: restrictive
    units:
      - id: booking-prod
        owner: team-booking
        data_classification: confidential
        cost_center: commerce
      - id: payment-prod
        owner: team-payments
        data_classification: restricted
        cost_center: commerce
  - name: non-production
    guardrails: development
    units:
      - id: booking-dev
        owner: team-booking
        environment: dev
      - id: booking-staging
        owner: team-booking
        environment: staging
~~~

Khi chuyển thành hiện thực, **unit** có thể được ánh xạ sang AWS account, Azure subscription hoặc Google Cloud project với cấu trúc nhóm cha khác nhau. Các policy, network và billing phải được định nghĩa bằng cơ chế hỗ trợ của nền tảng đã chọn.

## 9. Ví dụ xuyên suốt: tổ chức tài nguyên cho nền tảng đặt chỗ

Giả sử một công ty đang phát triển nền tảng đặt chỗ có hai nhóm nghiệp vụ: **Booking** (tìm kiếm và đặt chỗ) và **Payments** (thu và hoàn tiền). Hệ thống hoạt động trên cloud, có mục tiêu bảo vệ dữ liệu cá nhân, triển khai nhiều phiên bản và theo dõi chi phí theo sản phẩm.

Yêu cầu kiến trúc:

1. Không để nhà phát triển môi trường dev có quyền trực tiếp thay đổi dữ liệu prod.
2. Có thể phát hành Booking và Payments độc lập, có kiểm soát thay đổi và rollback phù hợp.
3. Phân bổ chi phí cho từng nhóm sản phẩm, xác định được tài nguyên nào không có chủ sở hữu.
4. Audit log và các cảnh báo bảo mật quan trọng được lưu tập trung, có giới hạn quyền sửa/xóa.
5. Hệ thống thanh toán có quyền và mạng chặt hơn các dịch vụ nghiệp vụ thông thường.
6. Mỗi workload có hạn mức, dự toán và kế hoạch xử lý khi quá tải phù hợp.

Một **phân cấp đề xuất**:

~~~text
Company cloud organization / tenant
|
+-- Security / Audit
|   +-- Central logging and security monitoring
|
+-- Shared platform
|   +-- Network connectivity, DNS or CI/CD shared services
|
+-- Production
|   +-- Booking prod
|   +-- Payments prod
|
+-- Non-production
|   +-- Booking staging
|   +-- Booking dev
|   +-- Payments staging
|   +-- Payments dev
|
+-- Sandbox
    +-- Temporary experiments with budgets and expiry
~~~

Đây là **mô hình logic**; không yêu cầu tất cả các dòng đều là đơn vị vật lý trong mỗi nhà cung cấp. Ví dụ có thể hiện thực hóa như sau:

| Thành phần logic | AWS | Azure | Google Cloud |
|---|---|---|---|
| Production | OU Production | Management group Production | Folder Production |
| Booking prod | AWS member account | Azure subscription | Google Cloud project |
| Payments prod | AWS member account riêng | Azure subscription riêng | Google Cloud project riêng |
| Non-production | OU Non-production | Management group Non-production | Folder Non-production |
| Logging/security | Account chuyên trách trong OU Security | Subscription chuyên trách trong management group phù hợp | Project chuyên trách trong folder Security |
| Shared network/platform | Account Shared Services khi phù hợp | Subscription Connectivity/Platform khi phù hợp | Host project cho Shared VPC hoặc project dịch vụ chung khi phù hợp |

### Luồng quyền và vận hành mẫu

**Nhà phát triển Booking:** Có quyền làm việc ở Booking-dev theo nguyên tắc quyền tối thiểu. Với prod, họ mở pull request và triển khai qua pipeline/role được kiểm soát; không cần quyền quản trị thủ công toàn bộ phạm vi prod.

**Pipeline triển khai:** Có danh tính riêng cho từng môi trường; dùng token/role ngắn hạn hoặc cơ chế federation khi được hỗ trợ. Pipeline Booking-prod không mặc nhiên có quyền sửa Payment-prod.

**Security:** Có khả năng đọc thông tin kiểm toán và cấu hình cần thiết ở nhiều đơn vị; quyền thay đổi đặc quyền được giới hạn và ghi nhật ký. Cơ chế tập trung log không nên cho các workload tự ý xóa hoặc vô hiệu hóa log lịch sử.

**Platform:** Vận hành các cấu phần mạng và hệ thống quản trị chung; công bố cơ chế cấp kết nối và chính sách thay đổi để giảm phụ thuộc vào thao tác thủ công.

**Owner sản phẩm:** Theo dõi ngân sách, quota, availability và dữ liệu thuộc phạm vi mình quản lý. Nếu cần thay đổi mức bảo mật hoặc cấu trúc đơn vị, ghi nhận quyết định, người chịu trách nhiệm và tác động lan truyền.

### Quyết định nào cần được ghi lại?

Ví dụ một bản ghi quyết định kiến trúc (*Architecture Decision Record — ADR*):

> **Bối cảnh:** Booking và Payments có vòng đời triển khai độc lập. Payments xử lý dữ liệu nhạy cảm hơn và không được cấp quyền rộng cho các nhóm khác.
>
> **Quyết định:** Tách Booking-prod và Payments-prod thành hai đơn vị workload ở cấp account/subscription/project. Mỗi đơn vị có quyền, chính sách, quota và ngân sách được kiểm soát. Logging bảo mật tập trung trong đơn vị chuyên trách.
>
> **Lý do:** Giảm phạm vi ảnh hưởng của thay đổi sai; rõ quyền sở hữu, chi phí và trách nhiệm vận hành.
>
> **Đánh đổi:** Tăng số đơn vị cần cấp phát, mạng kết nối, role và pipeline; yêu cầu tự động hóa và theo dõi cấu hình nhất quán.
>
> **Kiểm chứng:** Thử tài khoản dev truy cập prod bị từ chối; kiểm tra quyền pipeline chéo; diễn tập lỗi dịch vụ dùng chung; xem báo cáo chi phí và log kiểm toán.

Về mạng và dữ liệu, có thể vẫn cần API hoặc sự kiện giữa Booking và Payments. **Tách đơn vị quản trị không thay thế hợp đồng API, xác thực dịch vụ, kiểm soát kết nối, idempotency hoặc thiết kế giao dịch**. Phải xem mỗi kết nối xuyên ranh giới là một tích hợp có quy tắc bảo mật và độ tin cậy cụ thể.

## 10. Đánh giá kiến trúc bằng nguyên tắc Well-Architected

Các nhóm câu hỏi Well-Architected giúp xem việc phân cấp có phục vụ hệ thống đang vận hành hay không:

| Khía cạnh | Câu hỏi cần đánh giá | Bằng chứng mong đợi |
|---|---|---|
| **Vận hành xuất sắc** | Có thể tạo, cập nhật, bàn giao hoặc thu hồi một phạm vi workload bằng quy trình nhất quán không? | IaC, pipeline, sơ đồ sở hữu, runbook, quy trình quản lý ngoại lệ |
| **Bảo mật** | Dev có thể ảnh hưởng prod không? Quyền cấp cao và truy cập chéo được kiểm soát thế nào? | IAM/RBAC review, policy test, audit log, kiểm soát danh tính khẩn cấp |
| **Độ tin cậy** | Một thay đổi sai ở workload hoặc dịch vụ chung có thể làm hỏng bao nhiêu chức năng? | Bản đồ phụ thuộc, phân tích blast radius, thử failover và phục hồi |
| **Hiệu quả hiệu năng** | Quota, đường truyền và dịch vụ dùng chung có đáp ứng tải không? | Load test, quota dashboard, p95/p99, metric kết nối và độ trễ |
| **Tối ưu chi phí** | Có biết chi phí từng sản phẩm, môi trường và tài nguyên không có chủ? | Báo cáo cost allocation, ngân sách, tag/label coverage, cảnh báo |
| **Bền vững** | Tài nguyên không dùng đến hoặc sandbox tồn tại quá lâu có được dọn dẹp? | TTL, lịch thu hồi, right-sizing, theo dõi mức sử dụng |

Ví dụ, yêu cầu “một lỗi cấu hình ở dev không được sửa tài nguyên prod” cần được kiểm chứng bằng **quyền thực tế** và bài kiểm tra truy cập bị từ chối; việc đặt tên khác nhau hoặc tách folder hiển thị chưa đủ. Yêu cầu “biết chi phí theo sản phẩm” phải được kiểm chứng bằng báo cáo billing có thể tái tạo, không chỉ nhìn thấy tag trong giao diện.

### Một số tiêu chí chấp nhận có thể đo

Các ngưỡng sau chỉ là **giả định minh họa**, phải điều chỉnh theo nhu cầu thực tế:

- **100%** phạm vi workload mới có owner, môi trường và đơn vị chịu chi phí rõ ràng ngay khi tạo.
- **100%** quyền đặc quyền ở prod có quy trình phê duyệt, ghi audit và đánh giá định kỳ.
- **100%** tài nguyên prod thuộc phạm vi bắt buộc thu thập audit log theo chính sách đã xác định.
- **Không có** quyền triển khai chéo Booking-dev sang Payments-prod khi không có ủy quyền.
- Có cảnh báo ngân sách và quota ở mức ngưỡng do từng nhóm sản phẩm thống nhất.

Đừng coi một biểu đồ quản trị đẹp là bằng chứng chính sách hoạt động. Các tiêu chí cần được đo bằng kiểm tra cấu hình, thử truy cập, truy vấn dữ liệu chi phí và diễn tập sự cố.

## 11. Sai lầm phổ biến và cách sửa

**Sai lầm 1 — Một account/subscription/project cho tất cả prod và dev.** Một quyền thao tác hoặc quota có thể ảnh hưởng cả hai. Giải pháp: tách các môi trường có rủi ro khác nhau ở phạm vi phù hợp và áp quyền độc lập.

**Sai lầm 2 — Cấp quyền quản trị ở cấp cao chỉ để tiết kiệm thời gian.** Quyền được kế thừa có thể mở rộng đến nhiều workload. Giải pháp: cấp tại scope nhỏ nhất, dùng role rõ nhiệm vụ, ưu tiên quyền tạm thời cho tác vụ đặc biệt.

**Sai lầm 3 — Xem OU, folder hoặc management group là mạng riêng.** Chúng hỗ trợ quản trị và chính sách, không tự đảm bảo phân đoạn mạng. Giải pháp: thiết kế topology, routing, firewall và quyền truy cập dịch vụ riêng.

**Sai lầm 4 — Xem resource group của Azure như một subscription.** Resource group cho phép gom vòng đời tài nguyên và quản lý ở scope thấp hơn, nhưng không tự có ranh giới billing và quota như subscription. Giải pháp: tách subscription khi cần ranh giới mạnh hơn, dùng resource group cho vòng đời ứng dụng.

**Sai lầm 5 — Dùng tag thay cho ranh giới bảo mật.** Metadata hữu ích để báo cáo hoặc điều kiện chính sách nhưng không tự cô lập quyền hay dữ liệu. Giải pháp: áp IAM, policy, mạng và kiểm tra quyền thực tế.

**Sai lầm 6 — Chia quá nhiều đơn vị mà không có tự động hóa.** Cấp phát thủ công gây chênh lệch IAM, log, mạng và ngân sách. Giải pháp: thiết kế landing zone, template, IaC và quy trình cấp phát/thu hồi.

**Sai lầm 7 — Tập trung mọi dịch vụ nền tảng mà bỏ qua blast radius.** Một thay đổi sai ở DNS, mạng hoặc identity chung có thể ảnh hưởng nhiều sản phẩm. Giải pháp: phân tích phụ thuộc, phân quyền thay đổi, dự phòng và thử phục hồi dịch vụ chung.

**Sai lầm 8 — Nghĩ tách project/account là đủ cho yêu cầu tuân thủ.** Dữ liệu vẫn có thể rò rỉ qua quyền IAM rộng, secret dùng chung hoặc tích hợp không kiểm soát. Giải pháp: kiểm tra toàn bộ luồng dữ liệu, quản lý khóa, audit và quy trình bảo mật.

**Sai lầm 9 — Đặt tên mà không có chủ sở hữu và vòng đời.** Không ai chịu trách nhiệm với tài nguyên cũ, chi phí tăng và rủi ro cấu hình sai tích tụ. Giải pháp: yêu cầu owner, ngân sách, thời hạn và định kỳ rà soát.

## 12. Quy trình thiết kế một hệ phân cấp thực tế

Có thể triển khai theo thứ tự:

1. **Liệt kê workload và dữ liệu:** Xác định sản phẩm, môi trường, nhóm chịu trách nhiệm, độ nhạy cảm và yêu cầu tuân thủ.
2. **Xác định ranh giới cần cô lập:** Tập trung vào prod/non-prod, quyền người dùng, dữ liệu, mức độ rủi ro, quota và vòng đời.
3. **Chọn cấu trúc cha-con theo cloud:** AWS root/OU/account, Azure management group/subscription/resource group hoặc Google Cloud organization/folder/project; giữ các khác biệt của nhà cung cấp trong thiết kế.
4. **Xây baseline:** Danh tính, IAM/RBAC, policy, logging, network, billing, tag/label và quota.
5. **Thiết kế dịch vụ chung:** Chỉ rõ cái gì tập trung, cái gì phân tán; xác định ảnh hưởng khi dịch vụ dùng chung lỗi.
6. **Tự động hóa:** Cấp phát và thu hồi đơn vị workload bằng cơ chế được review; quản lý cấu hình bằng IaC khi phù hợp.
7. **Kiểm chứng:** Thử truy cập bị từ chối, kiểm tra cấu hình và log, so sánh hóa đơn, đo quota, diễn tập sai cấu hình và sự cố.
8. **Duy trì:** Review định kỳ quyền truy cập, owner, ngân sách, cấu trúc nhóm cha và những ngoại lệ quá hạn.

**Không nên bắt đầu bằng cây có thật nhiều tầng.** Bắt đầu từ ranh giới có mục đích rõ ràng, đặt quy ước đơn giản, rồi mở rộng khi số workload và yêu cầu kiểm soát tăng. Mỗi nhánh mới phải giải thích được nó đem lại ranh giới quản trị, độ tin cậy, phân bổ chi phí hoặc vòng đời nào.

## 13. Bài tập thực hành và hướng giải quyết

### Tình huống

Một doanh nghiệp triển khai trên cloud và đang có:

- API đặt chỗ prod với database chứa thông tin khách hàng.
- API đặt chỗ dev của cùng nhóm, thường tạo/xóa tài nguyên thử nghiệm.
- Dịch vụ thanh toán prod do nhóm khác phụ trách, cần kiểm soát truy cập chặt.
- Dashboard quan sát và lưu audit log tập trung.
- Ba môi trường sandbox ngắn hạn cho thử nghiệm công nghệ.

Hiện mọi tài nguyên thuộc cùng một phạm vi quản trị. Nhà phát triển dev có quyền tạo/xóa rộng. Chi phí không phân biệt được sản phẩm và sandbox thường không được dọn dẹp.

**Yêu cầu:** Đề xuất hệ phân cấp tương ứng trên AWS, Azure hoặc Google Cloud; chỉ rõ ranh giới cô lập, quyền chủ sở hữu, chi phí và cấu phần dùng chung.

### Hướng giải quyết

1. Tách **Booking-prod**, **Payments-prod** và **Booking-dev** thành những đơn vị workload phù hợp ở cấp account/subscription/project. Khi nhu cầu tăng, bổ sung staging riêng.
2. Đặt các đơn vị dưới nhóm cha **Production**, **Non-production** và **Sandbox** nếu nền tảng hỗ trợ. Với Azure, cân nhắc dùng resource group để quản lý vòng đời ứng dụng bên trong subscription.
3. Đặt **logging/security** trong phạm vi chuyên trách. Quy định rõ ai được gửi log, ai được đọc, ai được quản lý chính sách và ai được xóa theo quy trình.
4. Tạo **role riêng** cho đội Booking, Payments, Platform và Security. Giới hạn nhà phát triển trong dev; dùng pipeline/role riêng để triển khai prod. Thử thao tác truy cập trái phép phải bị từ chối.
5. Thiết lập **owner, cost center, environment, data classification** và báo cáo billing theo sản phẩm. Đặt budget/alert và thời hạn thu hồi cho sandbox.
6. Xác định mạng chung cần thiết, ví dụ kết nối đến hệ thống thanh toán hoặc mạng nội bộ. Đánh giá routing, bảo mật, chi phí truyền dữ liệu và blast radius của cấu phần trung tâm.
7. Tạo baseline bằng công cụ tự động hóa và kiểm chứng: audit log đầy đủ, tài nguyên mới có owner, không có quyền chéo trái phép, báo cáo chi phí có thể kiểm tra, sandbox được thu hồi đúng hạn.

### Câu hỏi tự kiểm tra

1. Vì sao tách Booking-prod khỏi Booking-dev bằng tên resource chưa chắc giảm blast radius?
2. Điểm khác nhau giữa **AWS OU**, **Azure management group**, **Google Cloud folder** và các phạm vi triển khai workload bên dưới là gì?
3. Vì sao **Azure resource group** không nên được coi là tương đương một AWS account?
4. Quản trị tập trung quyền và logging đem lại lợi ích gì? Khi nào một cấu phần dùng chung lại tạo điểm lỗi chung?
5. Nếu lãnh đạo muốn báo cáo chi phí mỗi sản phẩm, cần kết hợp cấu trúc tài nguyên với những dữ liệu và quy trình nào?
6. Trong thiết kế đã đề xuất, ai có thể triển khai Payments-prod? Làm thế nào chứng minh Booking-dev không có quyền sửa Payments-prod?

Một hệ phân cấp cloud tốt là **bản đồ trách nhiệm có thể thực thi**: biết ai sở hữu workload, ai được thao tác, những chính sách nào áp dụng, dữ liệu và mạng được cô lập tới đâu, chi phí được tính cho ai, và sự cố có thể lan tới những thành phần nào. Từ bản đồ đó, nhóm kiến trúc mới lựa chọn mạng, compute, dữ liệu và mô hình triển khai phù hợp với yêu cầu nghiệp vụ và các đánh đổi Well-Architected.
