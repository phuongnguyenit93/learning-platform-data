# Assured Workloads và kiểm soát theo yêu cầu tuân thủ

Khi triển khai hệ thống trên Google Cloud, tổ chức có thể phải đáp ứng các yêu cầu về nơi lưu trữ dữ liệu, vị trí nhân sự hỗ trợ, loại dịch vụ được phép sử dụng, quản lý khóa mã hóa và khả năng chứng minh rằng các quy tắc đó luôn được thực thi. **Assured Workloads** giúp tổ chức thiết lập một ranh giới kiểm soát cho các workload nhạy cảm bằng cách áp dụng những gói kiểm soát được định nghĩa sẵn vào một folder trong Google Cloud. Các chính sách và cơ chế giám sát đi kèm giúp hạn chế cấu hình không phù hợp, theo dõi vi phạm và cung cấp thông tin để xử lý.

Trong module `CLOUD_PROVIDERS_GCP`, nội dung này kết nối việc tổ chức project và IAM với thiết kế VPC, lựa chọn Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Khi một workload phải tuân thủ yêu cầu khu vực hoặc quy định cụ thể, kiến trúc không chỉ cần chọn đúng dịch vụ. Nhóm còn phải xác định dịch vụ đó có được hỗ trợ trong gói kiểm soát hay không, dữ liệu được lưu ở đâu, ai có thể truy cập, khóa được quản lý thế nào và cách phát hiện cấu hình lệch chuẩn.

Assured Workloads cung cấp các biện pháp kỹ thuật để hỗ trợ đáp ứng yêu cầu tuân thủ. Việc sử dụng sản phẩm không tự động chứng nhận toàn bộ ứng dụng hoặc tổ chức tuân thủ một đạo luật hay tiêu chuẩn. Khách hàng vẫn chịu trách nhiệm phân loại dữ liệu, thiết kế ứng dụng, quản lý danh tính, vận hành quy trình, kiểm soát các hệ thống bên ngoài và thu thập bằng chứng theo phạm vi đánh giá của mình.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò của Assured Workloads và cách control package tạo ranh giới kiểm soát cho một workload.
- Phân biệt regional data boundaries, regulatory data boundaries và Sovereign Controls by Partners.
- Hiểu mối quan hệ giữa folder, project, organization policy, data residency, kiểm soát nhân sự và quản lý khóa.
- Xác định các điều kiện IAM, billing, vị trí và dịch vụ được hỗ trợ trước khi tạo Assured Workloads folder.
- Tạo và kiểm tra một workload mẫu bằng Google Cloud Console hoặc `gcloud`.
- Theo dõi vi phạm, xử lý ngoại lệ, cập nhật control package và phối hợp trách nhiệm giữa Google Cloud với khách hàng.

## 1. Assured Workloads trong kiến trúc Google Cloud

### Assured Workloads giải quyết vấn đề gì?

Một organization trên Google Cloud có thể chứa nhiều folder và project phục vụ các nhóm ứng dụng khác nhau. Nếu tất cả project dùng chung một tập chính sách, nhóm vận hành có thể khó áp dụng yêu cầu nghiêm ngặt cho một workload mà không ảnh hưởng đến các hệ thống thông thường. Ngược lại, nếu mỗi nhóm tự xây dựng chính sách riêng, cấu hình dễ không đồng nhất và khó chứng minh.

Assured Workloads cung cấp một folder được cấu hình theo một **control package**. Control package chứa tập hợp các biện pháp như giới hạn vị trí tài nguyên, giới hạn sản phẩm/dịch vụ, yêu cầu về quyền truy cập của nhân sự hỗ trợ và các lựa chọn quản lý khóa. Những chính sách này được áp dụng lên folder và các project, tài nguyên nằm bên dưới theo phạm vi hỗ trợ của từng cơ chế.

Ví dụ, một tổ chức có thể đặt workload xử lý hồ sơ y tế trong một folder dành cho Healthcare and Life Sciences, trong khi các ứng dụng phân tích nội bộ thông thường tiếp tục nằm trong folder khác. Các project mới được tạo trong folder tuân thủ sẽ kế thừa những giới hạn phù hợp với control package. Khi muốn chuyển project hiện có vào folder, nhóm phải kiểm tra tài nguyên, location, dịch vụ và cấu hình hiện tại trước khi di chuyển.

### Vị trí của Assured Workloads trong cây tài nguyên

```text
Organization
├── Folder: ứng dụng nội bộ
│   └── Project: reporting
│       └── BigQuery, Cloud Storage, Cloud Run
│
└── Folder: Assured Workloads
    ├── Control package: ví dụ Data Boundary for FedRAMP High
    ├── Organization policies và các biện pháp kiểm soát liên quan
    ├── Project: hồ sơ nhạy cảm
    │   ├── Compute Engine / GKE
    │   ├── Cloud Storage / BigQuery (nếu được hỗ trợ)
    │   └── Cloud KMS / CMEK theo yêu cầu của gói
    └── Project: dịch vụ xử lý dữ liệu
```

Folder là ranh giới tổ chức và áp dụng chính sách. Project tiếp tục là ranh giới quản lý API, billing, IAM và tài nguyên. Một folder Assured Workloads không tự tạo ra mọi project hoặc khóa cần thiết; nhóm triển khai vẫn phải tạo project, bật dịch vụ được phép, cấp IAM và cấu hình ứng dụng.

### Các lớp kiểm soát chính

| Lớp kiểm soát | Câu hỏi cần trả lời | Cơ chế thường gặp |
|---|---|---|
| Vị trí dữ liệu | Tài nguyên và dữ liệu được lưu ở vùng nào? | Resource Locations organization policy, regional data boundary. |
| Dịch vụ được phép | Workload được dùng sản phẩm/API nào? | Resource Usage Restriction và danh sách supported products theo control package. |
| Nhân sự của nhà cung cấp | Ai trong Google có thể truy cập dữ liệu khi hỗ trợ? | Personnel access controls, Assured Support, Access Transparency, Access Approval tùy gói và dịch vụ. |
| Mã hóa và khóa | Ai kiểm soát khóa, khóa được lưu ở đâu? | Google-managed keys, CMEK, Cloud EKM, key import hoặc cơ chế theo control package. |
| Giám sát | Làm sao phát hiện cấu hình vi phạm? | Assured Workloads violation monitoring, Cloud Audit Logs và quy trình khắc phục. |

Các lớp này bổ sung cho IAM, VPC, firewall, bảo vệ workload, quản lý lỗ hổng và quy trình ứng cứu sự cố. Assured Workloads không thay thế những cơ chế bảo mật nền tảng đó.

## 2. Control package và các nhóm yêu cầu tuân thủ

Control package là nền tảng của Assured Workloads. Mỗi gói kết hợp các kiểm soát nhằm hỗ trợ một loại yêu cầu pháp lý, quy định, khu vực hoặc chủ quyền dữ liệu. Google Cloud tổ chức các gói theo ba nhóm chính.

### Regional data boundaries

Regional data boundaries tập trung vào yêu cầu dữ liệu phải được lưu trữ trong một khu vực hoặc nhóm quốc gia xác định. Tổ chức chọn data boundary phù hợp, sau đó cấu hình vị trí tài nguyên được phép. Một số gói khu vực còn cung cấp kiểm soát về nhân sự hỗ trợ hoặc quyền truy cập của nhà cung cấp.

Ví dụ về yêu cầu khu vực có thể gồm EU Data Boundary, US Data Boundary, Canada Data Boundary, Japan Data Boundary, Australia Data Boundary hoặc các gói cho những khu vực khác được Google Cloud hỗ trợ. Tên gói, khu vực và danh sách dịch vụ có thể thay đổi theo thời gian; phải tra cứu danh sách hiện hành trước khi thiết kế.

Regional data boundary phù hợp khi yêu cầu cốt lõi là giới hạn vị trí dữ liệu hoặc vận hành theo một ranh giới địa lý. Nếu quy định của tổ chức còn yêu cầu chứng minh các kiểm soát chuyên ngành như CJIS, FedRAMP hay ITAR, cần chọn đúng regulatory data boundary thay vì chỉ dựa vào một gói khu vực.

### Regulatory data boundaries

Regulatory data boundaries tập hợp các kiểm soát phục vụ một quy định hoặc chương trình tuân thủ cụ thể. Một số ví dụ gồm:

- **FedRAMP Moderate và FedRAMP High**: các yêu cầu cho hệ thống xử lý thông tin của cơ quan liên bang Hoa Kỳ theo mức kiểm soát tương ứng.
- **CJIS**: các yêu cầu bảo vệ thông tin tư pháp hình sự.
- **IL2, IL4 và IL5**: các mức Impact Level dùng trong môi trường xử lý thông tin của Bộ Quốc phòng Hoa Kỳ.
- **ITAR**: yêu cầu liên quan đến dữ liệu và công nghệ thuộc phạm vi International Traffic in Arms Regulations.
- **IRS Publication 1075**: yêu cầu bảo vệ thông tin thuế liên bang.
- **Healthcare and Life Sciences**: các kiểm soát hỗ trợ yêu cầu trong lĩnh vực y tế, bao gồm các nhu cầu liên quan HIPAA và HITRUST theo phạm vi của gói.
- **Canada Controlled Goods Program (CGP)** và các gói bảo vệ dữ liệu khác theo khu vực.

Không nên suy luận rằng mọi gói đều có cùng giới hạn vị trí, yêu cầu nhân sự hoặc cơ chế khóa. Hai gói cùng thuộc nhóm regulatory có thể áp dụng những tập kiểm soát và danh sách sản phẩm khác nhau. Phải đọc mô tả gói cụ thể và đối chiếu với nghĩa vụ mà tổ chức cần đáp ứng.

### Sovereign Controls by Partners

Sovereign Controls by Partners cho phép sử dụng một đối tác địa phương được hỗ trợ để vận hành hoặc quản lý một số thành phần kiểm soát chủ quyền. Tùy gói và đối tác, phạm vi có thể gồm quản lý khóa mã hóa, access justification, audit và kiểm soát dữ liệu theo khu vực.

Nhóm này hữu ích khi tổ chức cần một đối tác tin cậy tại địa phương tham gia quản lý các thành phần quan trọng của môi trường cloud. Cần đánh giá hợp đồng, vai trò của đối tác, quyền trên tài nguyên, quy trình hỗ trợ, billing và trách nhiệm xử lý sự cố. Không phải mọi đối tác hoặc mọi gói đều cung cấp cùng một bộ dịch vụ.

### Chọn đúng control package

| Nhu cầu | Nhóm gói cần xem xét | Câu hỏi xác minh |
|---|---|---|
| Dữ liệu phải ở trong EU hoặc một quốc gia/khu vực cụ thể | Regional data boundary | Dữ liệu nào được bao phủ? Vùng nào được phép? Có yêu cầu nhân sự hỗ trợ theo khu vực không? |
| Phải đáp ứng một chương trình như FedRAMP, CJIS, IL4, ITAR hoặc IRS 1075 | Regulatory data boundary | Gói có đúng mức/chương trình không? Dịch vụ và tính năng nào được hỗ trợ? |
| Cần đối tác địa phương quản lý khóa hoặc kiểm soát chủ quyền | Sovereign Controls by Partners | Đối tác nào được hỗ trợ? Ai giữ khóa? Quy trình phê duyệt và audit hoạt động thế nào? |

Một control package là tập hợp biện pháp kỹ thuật hỗ trợ một baseline. Nó không thay thế đánh giá pháp lý, kiểm toán độc lập, quy trình nội bộ hoặc bằng chứng về cách tổ chức thực sự sử dụng dịch vụ.

## 3. Data residency và ranh giới dữ liệu

### Data residency nghĩa là gì?

Data residency mô tả nơi dữ liệu được lưu trữ khi ở trạng thái nghỉ (*at rest*). Google Cloud cung cấp các lựa chọn vị trí cho những dịch vụ hỗ trợ cấu hình data location. Assured Workloads sử dụng các giới hạn về vị trí để giúp tổ chức kiểm soát nơi tạo hoặc sử dụng tài nguyên thuộc phạm vi.

Trong quá trình tạo folder, tổ chức chọn control package và cấu hình vị trí tài nguyên được phép theo yêu cầu của gói. Resource Locations organization policy có thể hạn chế việc tạo tài nguyên mới ở các location ngoài danh sách được phép. Một số dịch vụ hoặc loại tài nguyên không nằm trong phạm vi mà constraint này có thể kiểm soát; vì vậy phải kiểm tra danh sách tài nguyên được hỗ trợ thay vì giả định mọi tài nguyên đều bị giới hạn tự động.

### Phân biệt ba loại location

Trong thiết kế Assured Workloads, cần phân biệt:

1. **Vị trí trong cây tài nguyên**: folder được đặt dưới organization hoặc folder cha nào. Đây là lựa chọn cấu trúc quản trị.
2. **Location của Assured Workloads environment**: trường location của workload trong dịch vụ Assured Workloads, được chỉ định khi tạo workload qua Console hoặc CLI. Chọn một location được hỗ trợ cho control package.
3. **Resource location**: vùng hoặc multi-region mà tài nguyên Google Cloud thực tế được phép tạo và sử dụng. Resource Locations organization policy thực thi giới hạn này đối với các tài nguyên được hỗ trợ.

Ba khái niệm này liên quan với nhau nhưng không đồng nghĩa. Ví dụ, folder nằm dưới một folder quản trị ở organization không có nghĩa dữ liệu được phép lưu ở mọi region. Location của Assured Workloads environment cũng không tự động là danh sách location của mọi tài nguyên bên dưới.

### Phạm vi dữ liệu và metadata

Không phải mọi thông tin xuất hiện trong project đều được xem là Customer Data thuộc cam kết data residency. Theo tài liệu Google Cloud, các cam kết vị trí dữ liệu áp dụng cho Customer Data at rest của dịch vụ có thể cấu hình vị trí; metadata vận hành hay Service Data được xử lý theo các điều khoản và tài liệu riêng.

Các trường thông tin phổ biến cần đặc biệt thận trọng gồm:

- Tên và ID của resource, project hoặc folder.
- Mô tả tài nguyên, labels, tags và các thuộc tính cấu hình.
- URI, đường dẫn tệp, tên bucket hoặc tên dataset.
- User ID, timestamp, log-based metrics và nội dung rule cấu hình.
- Tên firewall rule, cấu hình quét bảo mật hoặc chính sách IAM.

Không đưa dữ liệu nhạy cảm, thông tin nhận dạng cá nhân hoặc nội dung được quản lý vào các trường metadata này nếu không có căn cứ rằng trường đó nằm trong ranh giới bảo vệ tương ứng. Hãy phân loại dữ liệu trước khi thiết kế tên tài nguyên, labels, log và mô tả.

### Ví dụ về giới hạn vị trí

Giả sử một tổ chức chọn gói EU Data Boundary. Nhóm triển khai cần:

1. Chọn location và resource location phù hợp với danh sách EU mà control package hỗ trợ.
2. Tạo project trong Assured Workloads folder.
3. Chỉ tạo các tài nguyên có location nằm trong danh sách cho phép.
4. Xác minh dịch vụ cụ thể có hỗ trợ location và có nằm trong danh sách supported products hay không.
5. Kiểm tra các tài nguyên không được Resource Locations constraint bao phủ và xử lý chúng bằng biện pháp quản trị hoặc kỹ thuật phù hợp.

Policy vị trí không di chuyển dữ liệu đã tồn tại từ region này sang region khác. Khi onboarding một project cũ, nhóm phải đánh giá và di chuyển hoặc tái tạo các tài nguyên cần thiết theo quy trình của từng dịch vụ.

## 4. Supported products và giới hạn của control package

### Không phải mọi dịch vụ GCP đều được hỗ trợ trong mọi gói

Danh sách supported products được công bố theo từng control package. Một dịch vụ được hỗ trợ trong FedRAMP High có thể không được hỗ trợ trong CJIS hoặc một regional data boundary khác. Nếu một sản phẩm không xuất hiện trong danh sách của gói, không được mặc định rằng sản phẩm đã đáp ứng đầy đủ các kiểm soát khu vực, quy định hoặc chủ quyền của gói đó.

Một số folder có thể bật Resource Usage Restriction organization policy để giới hạn API/service được phép sử dụng. Tuy nhiên, có những API endpoint được chia sẻ giữa sản phẩm được phép và sản phẩm không được phép; việc endpoint được bật không chứng minh mọi sản phẩm dùng endpoint đó đều nằm trong phạm vi được hỗ trợ.

Trước khi chọn dịch vụ cho workload, hãy kiểm tra:

- Tên sản phẩm và API service có được liệt kê cho đúng control package không.
- Tính năng hoặc SKU cụ thể có nằm trong phạm vi hỗ trợ không.
- Region, multi-region và các tùy chọn location của dịch vụ có tương thích không.
- Có tính năng nào cần bật hoặc cấu hình riêng sau khi tạo folder không.
- Dữ liệu có được truyền sang một dịch vụ, API hoặc project nằm ngoài folder không.

### Áp dụng vào Compute, container, lưu trữ và cơ sở dữ liệu

| Nhóm dịch vụ | Việc cần kiểm tra trước khi triển khai |
|---|---|
| Compute Engine | Region của VM, disk, snapshot và image; loại dịch vụ hỗ trợ; luồng dữ liệu đến hệ thống quản trị bên ngoài. |
| Google Kubernetes Engine (GKE) | Region/zone của cluster và node; dịch vụ tích hợp; image registry; logging, monitoring và add-on có nằm trong phạm vi được hỗ trợ không. |
| Cloud Run | Region của service, dữ liệu đầu vào/đầu ra, secret, log và các dịch vụ phụ thuộc. |
| Cloud Storage | Location của bucket, loại storage, replication và CMEK nếu control package yêu cầu. |
| BigQuery | Location của dataset, dịch vụ API, tính năng được phép và nơi lưu kết quả truy vấn. |
| Cơ sở dữ liệu | Location của instance/cluster, backup, replica, export, kết nối liên vùng và loại mã hóa được hỗ trợ. |

Bảng trên là danh sách câu hỏi kiến trúc, không phải xác nhận rằng tất cả dịch vụ đều được hỗ trợ trong mọi gói. Danh sách chính thức theo control package mới là căn cứ để quyết định.

### Khi một dịch vụ chưa được hỗ trợ

Nếu dịch vụ cần thiết không được hỗ trợ:

1. Kiểm tra xem có dịch vụ thay thế được hỗ trợ và đáp ứng yêu cầu nghiệp vụ không.
2. Xác định dữ liệu có thể được xử lý ở một workload riêng, nằm ngoài ranh giới tuân thủ, hay không.
3. Đánh giá việc tích hợp giữa hai ranh giới: dữ liệu nào đi qua, danh tính nào có quyền và kênh truyền được bảo vệ ra sao.
4. Nếu quy định cho phép ngoại lệ, lấy phê duyệt chính thức từ bộ phận tuân thủ/pháp chế và cơ quan có thẩm quyền khi cần.
5. Ghi nhận lý do, phạm vi, chủ sở hữu và biện pháp bù trừ; không coi ngoại lệ là bằng chứng rằng dịch vụ đã được chứng nhận.

## 5. Quyền truy cập nhân sự và kiểm soát quản trị của Google

Assured Workloads có thể áp dụng yêu cầu đối với nhân sự Google được phép truy cập dữ liệu khi thực hiện hỗ trợ. Tùy control package, yêu cầu có thể xét vị trí làm việc, quốc tịch hoặc tình trạng adjudication, xác minh nhân sự, background check và vai trò hỗ trợ. Ví dụ, một số gói FedRAMP High yêu cầu nhân sự hỗ trợ tuyến đầu và tuyến hai cùng subprocessors đáp ứng điều kiện về vị trí tại Hoa Kỳ và kiểm tra lý lịch nâng cao.

### Access Transparency

Access Transparency cung cấp log về một số hành động của nhân sự Google khi truy cập Customer Data để thực hiện nghĩa vụ hỗ trợ hoặc xử lý sự cố. Ví dụ, log có thể ghi nhận hành động của Cloud Customer Care khi xử lý support case hoặc hoạt động điều tra outage.

Access Transparency mang lại khả năng quan sát và đối chiếu. Nhóm bảo mật có thể chuyển log vào SIEM, liên kết với support case và kiểm tra lý do truy cập, thời gian, người thực hiện cùng tài nguyên liên quan. Log chỉ bao phủ các dịch vụ và loại truy cập được hỗ trợ; cần kiểm tra danh sách hỗ trợ hiện hành.

### Access Approval

Access Approval cho phép khách hàng xem xét và phê duyệt yêu cầu truy cập Customer Data của nhân sự Google trong các trường hợp được hỗ trợ. Khi cần truy cập, nhân sự Google gửi một request kèm lý do nghiệp vụ. Quản trị viên được ủy quyền có thể phê duyệt hoặc từ chối trong Console hoặc API. Request đã được phê duyệt được ghi nhận và có thể liên kết với Access Transparency logs.

Access Approval là lớp kiểm soát bổ sung trên cơ chế truy cập có đặc quyền của Google. Việc khách hàng phê duyệt không tự cấp quyền IAM cho nhân viên Google; nhân viên vẫn phải có quyền phù hợp ở phía Google trước khi truy cập. Các điều kiện nhân sự của Assured Workloads được áp dụng trước khi đánh giá request Access Approval. Cần xác minh dịch vụ đích hỗ trợ Access Approval và các trường hợp truy cập nằm ngoài phạm vi thông báo.

### Assured Support

Assured Support là tùy chọn hỗ trợ bổ sung dành cho workload có yêu cầu về nhân sự hỗ trợ. Có thể tạo và sử dụng Assured Workloads folder mà không cần đăng ký support subscription. Tuy nhiên, để nhận hỗ trợ từ nhân sự đáp ứng các yêu cầu của control package, tổ chức cần subscription **Enhanced Support** hoặc **Premium Support** đang hoạt động. Gói hỗ trợ phù hợp sẽ định tuyến case đến nhân sự đáp ứng các tiêu chí liên quan như vị trí làm việc, kiểm tra nhân sự và quyền truy cập dữ liệu.

### Phân biệt ba cơ chế

| Cơ chế | Vai trò | Câu hỏi trả lời |
|---|---|---|
| Assured Workloads personnel controls | Giới hạn nhóm nhân sự có thể được phép hỗ trợ workload theo control package. | Ai đủ điều kiện để được xem xét truy cập? |
| Access Transparency | Ghi nhận một số hành động truy cập Customer Data của nhân sự Google. | Nhân sự Google đã truy cập dữ liệu khi nào và trong ngữ cảnh nào? |
| Access Approval | Yêu cầu phê duyệt trước cho các loại truy cập được hỗ trợ. | Tổ chức có đồng ý cho request truy cập này không? |

Ba cơ chế bổ sung cho nhau, không phải ba tên gọi của cùng một tính năng. Cần phối hợp thêm quy trình trực vận hành để xử lý yêu cầu phê duyệt kịp thời, đặc biệt khi hệ thống đang gặp sự cố.

## 6. Quản lý khóa và mã hóa

Yêu cầu về khóa phụ thuộc control package. Một số gói hỗ trợ Google-owned and Google-managed encryption keys; các gói khác cho phép hoặc yêu cầu Customer-Managed Encryption Keys (CMEK), Cloud External Key Manager (Cloud EKM) hoặc nhập khóa từ bên ngoài. Không nên suy luận rằng mọi workload trong Assured Workloads đều bắt buộc dùng CMEK.

### CMEK và phân tách nhiệm vụ

CMEK cho phép khách hàng kiểm soát CryptoKey trong Cloud Key Management Service (Cloud KMS). Quyền dùng khóa được cấp riêng cho service agent của dịch vụ cần mã hóa dữ liệu. Nhóm quản trị khóa có thể được tách khỏi nhóm vận hành ứng dụng để giảm nguy cơ một danh tính vừa quản trị dữ liệu vừa tự ý thay đổi hoặc hủy khóa.

Trong một số control package, Google khuyến nghị hoặc yêu cầu đặt project quản lý khóa riêng với project chứa workload. Ví dụ, Data Boundary for ITAR yêu cầu sử dụng CMEK và dùng project quản lý khóa tách biệt cùng key ring ở location tuân thủ. Cách tổ chức này hỗ trợ separation of duties và giúp giới hạn quyền của nhóm phát triển.

### Tạo folder không đồng nghĩa tạo khóa

Trong quy trình tạo Assured Workloads folder, giao diện có thể cho phép tạo project quản lý CMEK và key ring. Bước này chỉ chuẩn bị project và key ring theo cấu hình đã chọn. **Assured Workloads không tự động tạo cryptographic key**. Nhóm phải tạo khóa, chọn thuật toán và protection level phù hợp, cấp IAM cho service agent và kiểm tra tích hợp trước khi đưa dữ liệu vào sử dụng.

### Cloud EKM và Key Access Justifications

Nếu control package và đối tác hỗ trợ Cloud EKM, vật liệu khóa chính có thể được giữ trong hệ thống EKM bên ngoài Google Cloud. Cloud KMS tham chiếu khóa và chuyển yêu cầu mật mã theo kết nối đã cấu hình. Cách này có thể đáp ứng yêu cầu kiểm soát khóa ở bên ngoài Google Cloud, nhưng làm tăng phụ thuộc vào endpoint, mạng và tính sẵn sàng của đối tác.

Key Access Justifications (KAJ) bổ sung thông tin về lý do của yêu cầu sử dụng khóa bên ngoài. Với EKM hỗ trợ KAJ, đối tác có thể đánh giá justification để cho phép hoặc từ chối thao tác theo chính sách. KAJ không thay thế IAM, Access Approval hay audit log; cần phân biệt yêu cầu truy cập dữ liệu của nhân sự Google với yêu cầu sử dụng khóa bên ngoài.

## 7. IAM, billing và điều kiện triển khai

### Điều kiện cấp quyền

Để tạo Assured Workloads folder, người thực hiện cần các quyền tối thiểu phù hợp ở organization và billing account. Vai trò được tài liệu Google Cloud nêu gồm:

- **Assured Workloads Administrator** (`roles/assuredworkloads.admin`): tạo và quản lý Assured Workloads folder.
- **Resource Manager Organization Viewer** (`roles/resourcemanager.organizationViewer`): xem các tài nguyên thuộc organization.
- **Quyền Cloud Billing phù hợp**: liên kết hoặc sử dụng billing account cho workload theo quy trình tạo.

Organization cần có billing account hợp lệ và đang hoạt động. Để gán các vai trò, người quản trị cần quyền IAM thích hợp ở organization. Trong vận hành thường ngày, nên dùng các vai trò hẹp hơn như Assured Workloads Reader hoặc Editor cho người chỉ cần xem hoặc cập nhật workload; không cấp vai trò Admin rộng cho toàn bộ đội phát triển.

Các tác vụ khác có thể cần quyền riêng:

| Tác vụ | Vai trò/quyền cần xem xét |
|---|---|
| Xem workload và trạng thái | `roles/assuredworkloads.reader` hoặc vai trò có quyền tương đương. |
| Tạo/xóa workload folder | `roles/assuredworkloads.admin` và các quyền organization/billing cần thiết. |
| Sửa control package hoặc cập nhật workload | `assuredworkloads.workload.update`, thường có trong Assured Workloads Editor/Admin. |
| Xem vi phạm | `assuredworkloads.violations.get` và `assuredworkloads.violations.list`. |
| Sửa organization policy | Vai trò Organization Policy Administrator (`roles/orgpolicy.policyAdmin`) hoặc quyền tương ứng. |
| Quản lý IAM của folder | Quyền Resource Manager phù hợp trên resource hierarchy. |

Hãy kiểm tra IAM roles documentation theo đúng thao tác; một vai trò đọc dữ liệu không mặc nhiên có quyền sửa organization policy hoặc cấp ngoại lệ.

### Billing và chi phí

Assured Workloads cần một billing account hợp lệ. Một số control package, tùy chọn support hoặc dịch vụ do partner cung cấp có thể đi kèm điều kiện và chi phí riêng. Trước khi triển khai, cần xác định:

- Billing account nào chịu chi phí của workload.
- Có cần Enhanced Support hoặc Premium Support để đáp ứng yêu cầu nhân sự hỗ trợ không.
- Có dịch vụ partner nào yêu cầu partner services billing account riêng không.
- Các dịch vụ Google Cloud được chọn có mức giá, quota và giới hạn theo region tương ứng ra sao.

Không ước lượng chi phí chỉ từ việc tạo folder. Hãy lập ngân sách cho compute, storage, network, logging, KMS, support và dịch vụ đối tác dựa trên lưu lượng thực tế.

## 8. Tạo và sử dụng Assured Workloads folder

### Quy trình chuẩn bị

Trước khi tạo folder, nhóm kiến trúc và tuân thủ nên thống nhất:

1. Loại dữ liệu được xử lý và quy định áp dụng.
2. Control package đáp ứng đúng yêu cầu về khu vực, quy định và nhân sự.
3. Location của Assured Workloads environment và danh sách resource location được phép.
4. Các sản phẩm, API và tính năng workload cần dùng có nằm trong supported products không.
5. Project nào cần tạo mới, project nào có thể onboarding sau khi đánh giá.
6. Cách quản lý khóa, logging, Access Transparency, Access Approval và support.
7. Nhóm chịu trách nhiệm vận hành, người phê duyệt ngoại lệ và quy trình ứng cứu.

Folder có thể được tạo dưới organization hoặc một folder cha phù hợp. Vị trí folder trong cây tài nguyên không nên chọn tùy tiện vì cấu trúc folder ảnh hưởng đến quyền IAM và chính sách được kế thừa. Organization được chọn khi tạo folder không thể thay đổi sau này; hãy xác nhận đúng organization và folder cha trước khi tiếp tục.

### Tạo folder bằng Google Cloud Console

Quy trình tổng quát trong Google Cloud Console:

1. Mở trang **Assured Workloads** trong Google Cloud Console và chọn đúng organization.
2. Chọn **Create** để bắt đầu tạo folder.
3. Nhập tên folder không chứa dữ liệu nhạy cảm hoặc PII; có thể dùng tiền tố `aw-` để dễ nhận diện.
4. Chọn organization và vị trí folder trong resource hierarchy.
5. Chọn nhóm control package, sau đó chọn gói cụ thể như Data Boundary for FedRAMP High, EU Data Boundary hoặc gói phù hợp khác.
6. Chọn resource location được phép theo yêu cầu của workload và control package.
7. Đọc lại phần mô tả các kiểm soát, sản phẩm được hỗ trợ và yêu cầu bổ sung.
8. Nếu cần, cấu hình project quản lý CMEK và key ring; nhớ rằng bước này không tạo khóa mã hóa.
9. Xem lại cấu hình, billing và xác nhận tạo folder.

Sau khi folder được tạo, hãy tạo project bên dưới hoặc di chuyển project hiện có đã được kiểm tra. Không đưa workload production vào folder chỉ vì thao tác tạo folder hoàn tất; cần xác minh policy, dịch vụ, IAM và vị trí tài nguyên trước.

### Ví dụ tạo workload bằng gcloud CLI (API v1)

Ví dụ dưới đây tạo một Assured Workloads environment theo mô hình control package v1. Thay các placeholder bằng organization ID và billing account thật. `us-central1` chỉ là location minh họa cho workload Hoa Kỳ; hãy chọn location hợp lệ theo control package và yêu cầu dữ liệu của tổ chức.

```bash
# Chọn project quản trị dùng để gọi Assured Workloads API.
gcloud config set project ADMIN_PROJECT_ID

# Chỉ bật API trong project quản trị đã chọn nếu API chưa được bật.
gcloud services enable assuredworkloads.googleapis.com

gcloud assured workloads create aw-fedramp-high-prod \
  --organization=ORGANIZATION_ID \
  --location=us-central1 \
  --display-name="FedRAMP High - production" \
  --compliance-regime=data-boundary-for-fedramp-high \
  --billing-account=billingAccounts/BILLING_ACCOUNT_ID \
  --version=v1
```

Trong ví dụ:

- `ORGANIZATION_ID` là ID organization cha.
- `--location` là location của Assured Workloads environment và phải nằm trong danh sách location được hỗ trợ.
- `--compliance-regime` chọn control package; giá trị phải là một regime hợp lệ mà CLI hiện tại hỗ trợ.
- `BILLING_ACCOUNT_ID` là mã billing account đang hoạt động.
- `--version=v1` chỉ rõ mô hình API v1 dùng control package cho Assured Workloads folder.

Lệnh tạo workload không thay thế bước chọn resource location phù hợp, kiểm tra supported products hoặc cấu hình IAM cho ứng dụng. Với những gói cần tùy chọn riêng, hãy làm theo tài liệu tạo folder của chính gói đó.

Có thể liệt kê các workload v1 trong organization và location đã chọn:

```bash
gcloud assured workloads list \
  --organization=ORGANIZATION_ID \
  --location=us-central1 \
  --version=v1
```

### Onboard project hiện có

Một project đang chạy có thể được chuyển vào Assured Workloads folder sau khi đánh giá. Quy trình nên gồm:

1. Lập danh sách tài nguyên, dịch vụ, API, location, backup, snapshot, replica và kết nối ra ngoài.
2. So sánh từng dịch vụ với supported products của control package.
3. Xác minh mọi tài nguyên có location tương thích; lên kế hoạch di chuyển dữ liệu nếu cần.
4. Kiểm tra IAM, service account, service agent, quyền KMS, log và dữ liệu metadata.
5. Đánh giá tác động của Resource Usage Restriction và các organization policy lên triển khai hiện tại.
6. Thử nghiệm trên môi trường staging hoặc project đại diện trước khi chuyển production.
7. Di chuyển project theo hướng dẫn Resource Manager và theo dõi các vi phạm phát sinh.

Di chuyển project vào folder không tự chuyển dữ liệu giữa các region, không tự thay thế dịch vụ không được hỗ trợ và không tự tạo CMEK. Một project có thể cần thay đổi kiến trúc trước khi đáp ứng control package.

## 9. Giám sát và xử lý vi phạm

Assured Workloads giám sát cấu hình workload bằng cách đối chiếu yêu cầu của control package với organization policy và tài nguyên thực tế.

### Hai nhóm vi phạm chính

**Organization policy violations** xuất hiện khi cấu hình organization policy bị thay đổi theo cách không phù hợp với yêu cầu của folder. Ví dụ, một người có quyền quản trị thay đổi policy vị trí hoặc policy giới hạn dịch vụ làm giảm mức kiểm soát đã áp dụng.

**Resource violations** xuất hiện khi một tài nguyên vi phạm các giới hạn được áp dụng. Ví dụ, một resource được tạo ở location không được phép hoặc dùng một loại tài nguyên không đáp ứng giới hạn dịch vụ. Phạm vi theo dõi phụ thuộc vào các constraint và loại tài nguyên được hỗ trợ. Kiểm tra xem resource violation monitoring đã được bật cho folder hay chưa; việc theo dõi policy violations và resource violations có cấu hình/điều kiện riêng.

### Trạng thái vi phạm

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| `UNRESOLVED` | Vi phạm chưa được xử lý hoặc cấu hình lại đã tạo ra vi phạm mới sau ngoại lệ trước đó. | Điều tra nguyên nhân, xác định chủ sở hữu và lập kế hoạch khắc phục. |
| `RESOLVED` | Vi phạm đã được xử lý bằng cách khôi phục cấu hình phù hợp. | Lưu bằng chứng và xác minh không tái diễn. |
| `EXCEPTION` | Vi phạm được ghi nhận ngoại lệ cùng lý do nghiệp vụ theo quyền được cấp. | Theo dõi phạm vi, người phê duyệt và thời hạn/điều kiện rà soát theo quy trình nội bộ. |

Ngoại lệ không có nghĩa là tài nguyên đã trở nên tuân thủ. Đây là một quyết định quản trị rủi ro phải có lý do, phê duyệt và biện pháp bù trừ khi cần. Nếu cấu hình tiếp tục thay đổi sau ngoại lệ, violation có thể xuất hiện lại và cần được đánh giá lần nữa.

### Xem vi phạm bằng gcloud

Ví dụ liệt kê vi phạm của một workload:

```bash
gcloud assured workloads violations list \
  --location=us-central1 \
  --organization=ORGANIZATION_ID \
  --workload=WORKLOAD_ID
```

Kết quả có thể bao gồm violation ID, loại vi phạm, mô tả, thời điểm phát sinh đầu tiên, policy constraint bị ảnh hưởng, trạng thái hiện tại và liên kết đến audit log. Dùng các thông tin đó để tìm người thay đổi cấu hình, tài nguyên bị ảnh hưởng và hướng dẫn remediation.

Trong Console, nhóm vận hành có thể xem tổng quan trên trang Assured Workloads và mở trang Monitoring để lọc theo folder, trạng thái, loại vi phạm, constraint hoặc resource type. Có thể bật thông báo email cho organization policy violations hoặc khi ngoại lệ được thêm vào để đội phụ trách phản hồi kịp thời.

### Quy trình khắc phục

1. Mở chi tiết violation và xác định folder, project, resource hoặc organization policy bị ảnh hưởng.
2. Kiểm tra audit log để tìm thay đổi dẫn tới vi phạm và danh tính thực hiện.
3. Xác định nguyên nhân gốc: cấu hình sai, thay đổi ngoài quy trình, dịch vụ mới, tài nguyên cũ chưa di chuyển hay giới hạn chưa được hiểu đúng.
4. Chọn remediation phù hợp, chẳng hạn khôi phục policy, di chuyển hoặc tái tạo tài nguyên ở location hợp lệ, thay dịch vụ bằng sản phẩm được hỗ trợ hoặc sửa IAM.
5. Nếu cần ngoại lệ, yêu cầu người có thẩm quyền phê duyệt và ghi rõ phạm vi, lý do cùng biện pháp bù trừ.
6. Xác minh trạng thái chuyển sang `RESOLVED` hoặc `EXCEPTION` như mong đợi; lưu bằng chứng và cập nhật runbook.

Không nên chỉ tắt cảnh báo để làm sạch dashboard. Mục tiêu là xử lý nguyên nhân và duy trì trạng thái kiểm soát có thể giải thích được.

## 10. Cập nhật control package và duy trì cấu hình

Control package có thể được cập nhật khi Google Cloud bổ sung dịch vụ được hỗ trợ, thay đổi policy hoặc cải thiện kiểm soát. Assured Workloads cung cấp workload updates để so sánh cấu hình folder hiện tại với phiên bản mới nhất có sẵn.

Quy trình cập nhật nên gồm:

1. Mở chi tiết Assured Workloads folder và xem có bản cập nhật nào khả dụng.
2. Đọc danh sách thay đổi: organization policy, allowed services, location, key management hoặc các yêu cầu nhân sự.
3. Đánh giá tác động tới project, deployment pipeline, API, tài nguyên và tích hợp hiện có.
4. Thử cập nhật trên môi trường đại diện nếu quy trình tổ chức cho phép.
5. Phê duyệt thay đổi theo quy trình change management.
6. Áp dụng update, kiểm tra lại workload và theo dõi violation sau cập nhật.
7. Lưu phiên bản control package, ngày cập nhật, người phê duyệt và kết quả xác minh.

Không nên trì hoãn cập nhật vô thời hạn vì folder có thể thiếu kiểm soát mới hoặc không có danh sách dịch vụ hiện hành. Đồng thời, không áp dụng update trong production mà chưa đánh giá tác động đến các workload đang chạy.

### Assured Workloads frameworks

Google Cloud cũng có tính năng **Assured Workloads frameworks** để định nghĩa và đánh giá các cloud controls ở cấp folder hoặc project. Tài liệu hiện hành đánh dấu frameworks là Preview và yêu cầu điều kiện truy cập/allowlist. Frameworks dùng khái niệm cloud control, rule, enforcement mode như Preventive, Detective và Audit, và có thể hỗ trợ dashboard cùng báo cáo đánh giá.

Frameworks là hướng mở rộng khác với control package v1 của Assured Workloads folder. Khi triển khai thực tế, cần kiểm tra trạng thái phát hành, điều kiện truy cập và tài liệu phiên bản hiện hành; không giả định một tính năng Preview đã sẵn sàng hoặc có cùng bảo đảm với gói GA.

## 11. Shared responsibility và các giới hạn cần hiểu rõ

### Trách nhiệm của Google Cloud

Google Cloud cung cấp hạ tầng, dịch vụ và các control package được định nghĩa; vận hành những thành phần thuộc phạm vi dịch vụ; duy trì cơ chế giới hạn vị trí, nhân sự và quyền truy cập theo gói; cung cấp thông tin hỗ trợ như Access Transparency, violation monitoring và tài liệu về dịch vụ được hỗ trợ.

### Trách nhiệm của khách hàng

Khách hàng vẫn phải:

- Chọn đúng control package và location theo yêu cầu pháp lý/nghiệp vụ.
- Chỉ sử dụng dịch vụ, tính năng và location được hỗ trợ trong phạm vi cần tuân thủ.
- Thiết kế IAM, service account, VPC, firewall, workload identity và quy trình quản trị an toàn.
- Phân loại dữ liệu và tránh đưa thông tin nhạy cảm vào metadata hoặc dịch vụ ngoài phạm vi.
- Cấu hình CMEK/Cloud EKM nếu yêu cầu, quản lý vòng đời khóa và giữ khả năng khôi phục dữ liệu.
- Bật, lưu trữ và phân tích audit logs; giám sát violation và xử lý ngoại lệ.
- Quản lý nhà cung cấp phụ, endpoint bên ngoài, pipeline phát hành, người dùng và thiết bị truy cập.
- Thu thập bằng chứng và thực hiện đánh giá tuân thủ theo yêu cầu của cơ quan quản lý hoặc kiểm toán.

### Các giới hạn thường bị hiểu nhầm

1. **Có folder Assured Workloads không đồng nghĩa ứng dụng tự động compliant.** Cần kiểm tra kiến trúc và vận hành ở cả bên trong lẫn bên ngoài folder.
2. **Data residency không bao phủ mọi metadata.** Resource name, ID, labels, description và Service Data có phạm vi điều khoản riêng.
3. **Không phải mọi tài nguyên đều bị Resource Locations constraint kiểm soát.** Phải kiểm tra danh sách supported resources.
4. **Không phải mọi dịch vụ GCP đều được hỗ trợ trong mọi package.** Dùng đúng danh sách supported products theo gói.
5. **Access Transparency không phải Access Approval.** Một tính năng ghi log, tính năng kia yêu cầu phê duyệt trước cho truy cập được hỗ trợ.
6. **Folder setup không tạo sẵn cryptographic key.** CMEK project/key ring có thể được chuẩn bị, nhưng khóa cần được tạo và cấu hình riêng.
7. **Support subscription có điều kiện riêng.** Để nhận hỗ trợ từ nhân sự đáp ứng control package, cần Enhanced Support hoặc Premium Support đang hoạt động.
8. **Ngoại lệ không xóa bỏ rủi ro.** Cần lý do, thẩm quyền, biện pháp bù trừ và rà soát định kỳ.

## 12. Tình huống triển khai

### Tình huống A: Hệ thống y tế cần bảo vệ dữ liệu trong phạm vi Hoa Kỳ

Một đơn vị y tế triển khai ứng dụng hồ sơ bệnh nhân trên Cloud Run, lưu tệp trong Cloud Storage và phân tích dữ liệu trong BigQuery. Đội tuân thủ yêu cầu data boundary tại Hoa Kỳ cùng các kiểm soát phù hợp cho Healthcare and Life Sciences.

Nhóm kiến trúc cần chọn đúng control package Healthcare and Life Sciences, xác nhận các dịch vụ và tính năng cụ thể được hỗ trợ, chọn resource location hợp lệ, cấu hình CMEK nếu chính sách nội bộ yêu cầu và cấp quyền KMS cho service agent. Nhóm cũng đánh giá Assured Support nếu cần nhân sự hỗ trợ đáp ứng tiêu chí của gói, bật Access Transparency và xây dựng quy trình Access Approval cho dịch vụ được hỗ trợ.

Khi triển khai, đội dự án kiểm tra vị trí của Cloud Run service, bucket, dataset, backup và log; đồng thời tránh đưa thông tin bệnh nhân vào resource name hoặc label. Sau khi go-live, nhóm theo dõi violation và định kỳ kiểm tra supported products.

### Tình huống B: Workload cơ quan cần Data Boundary for FedRAMP High

Một nhóm triển khai workload xử lý dữ liệu thuộc phạm vi FedRAMP High. Nhóm chọn Data Boundary for FedRAMP High và resource location tại Hoa Kỳ theo danh sách được hỗ trợ. Các project chạy Compute Engine và dịch vụ lưu trữ chỉ được tạo khi sản phẩm, API, location và tính năng nằm trong danh sách cho phép.

Control package áp dụng giới hạn đối với vị trí và nhân sự hỗ trợ theo phạm vi của gói. Đội bảo mật tách nhóm quản trị folder, nhóm quản trị khóa và nhóm vận hành ứng dụng. Nếu cần hỗ trợ đáp ứng điều kiện nhân sự, tổ chức đăng ký Enhanced Support hoặc Premium Support. Các thay đổi organization policy và tài nguyên được theo dõi để phát hiện cấu hình lệch chuẩn.

### Tình huống C: Tổ chức cần đối tác địa phương tham gia kiểm soát chủ quyền

Một tổ chức tại một quốc gia có yêu cầu quản lý khóa và audit bởi đối tác địa phương. Nhóm đánh giá các Sovereign Controls by Partners được hỗ trợ tại khu vực đó, lựa chọn đối tác và kiểm tra hợp đồng, vai trò, billing, phạm vi dữ liệu, quyền quản lý khóa, access justification và quy trình sự cố.

Nhóm triển khai workload trong folder theo control package của partner, tạo project và tài nguyên được hỗ trợ, cấu hình kết nối đến các dịch vụ quản lý khóa và audit theo yêu cầu. Trước khi production, nhóm diễn tập tình huống đối tác không sẵn sàng, không phê duyệt truy cập hoặc cần khôi phục quyền sử dụng khóa.

## 13. Checklist trước khi đưa workload vào sử dụng

- [ ] Đã xác định dữ liệu, nghĩa vụ pháp lý và control package phù hợp.
- [ ] Đã kiểm tra location của Assured Workloads environment và resource location được phép.
- [ ] Đã kiểm tra supported products, API, tính năng và loại tài nguyên theo đúng package.
- [ ] Đã chọn folder cha và cấu trúc organization/project phù hợp.
- [ ] Đã xác minh IAM cho Assured Workloads Admin, Organization Viewer, billing và các nhóm vận hành.
- [ ] Đã đánh giá project hiện có trước khi onboarding; không còn tài nguyên/location chưa xử lý.
- [ ] Đã cấu hình service account, IAM, VPC, firewall và các dịch vụ phụ thuộc.
- [ ] Đã xác định yêu cầu Google-managed keys, CMEK, Cloud EKM hoặc key import.
- [ ] Đã tạo và kiểm thử khóa nếu cần; không nhầm key ring với cryptographic key.
- [ ] Đã đánh giá Access Transparency, Access Approval và Assured Support theo package.
- [ ] Đã bật và kiểm tra policy/resource violation monitoring.
- [ ] Đã định nghĩa quy trình remediation, exception, escalation và lưu bằng chứng.
- [ ] Đã lập lịch rà soát supported products và workload updates.
- [ ] Đã kiểm tra billing, support subscription, partner services và ngân sách vận hành.

## 14. Kết luận

Assured Workloads giúp tổ chức thiết lập một ranh giới kiểm soát cho workload nhạy cảm bằng các control package được định nghĩa theo khu vực, quy định hoặc chủ quyền dữ liệu. Folder và các policy liên quan tạo nền tảng để giới hạn vị trí, dịch vụ, nhân sự hỗ trợ và một số yêu cầu quản lý khóa. Việc theo dõi violation và cập nhật control package giúp đội vận hành nhận biết khi cấu hình thay đổi hoặc yêu cầu kiểm soát được cải thiện.

Để triển khai thành công, nhóm cần kết hợp Assured Workloads với thiết kế organization/folder/project, IAM, VPC, dịch vụ được hỗ trợ, quản lý khóa, logging và quy trình change management. Hãy kiểm tra từng dịch vụ và từng loại dữ liệu theo phạm vi control package, diễn tập cách khắc phục vi phạm và lưu bằng chứng vận hành. Đây là cách biến yêu cầu tuân thủ thành những kiểm soát kỹ thuật có thể kiểm tra và duy trì trong suốt vòng đời workload.

## Tài liệu tham khảo

- [Overview of Assured Workloads](https://docs.cloud.google.com/assured-workloads/docs/overview)
- [Control packages](https://docs.cloud.google.com/assured-workloads/docs/control-packages)
- [Create an Assured Workloads folder](https://docs.cloud.google.com/assured-workloads/docs/create-folder)
- [Supported products by control package](https://docs.cloud.google.com/assured-workloads/docs/supported-products)
- [Assured Workloads locations](https://docs.cloud.google.com/assured-workloads/docs/locations)
- [Data residency](https://docs.cloud.google.com/assured-workloads/docs/data-residency)
- [Shared responsibility in Assured Workloads](https://docs.cloud.google.com/assured-workloads/docs/shared-responsibility)
- [IAM roles](https://docs.cloud.google.com/assured-workloads/docs/iam-roles)
- [Monitor an Assured Workloads folder for violations](https://docs.cloud.google.com/assured-workloads/docs/monitor-folder)
- [Apply workload updates](https://docs.cloud.google.com/assured-workloads/docs/apply-updates)
- [Getting support](https://docs.cloud.google.com/assured-workloads/docs/getting-support)
- [Access Transparency overview](https://docs.cloud.google.com/assured-workloads/access-transparency/docs/overview)
- [Access Approval overview](https://docs.cloud.google.com/assured-workloads/access-approval/docs/overview)
- [gcloud assured workloads create](https://docs.cloud.google.com/sdk/gcloud/reference/assured/workloads/create)
- [Assured Workloads frameworks overview (Preview)](https://docs.cloud.google.com/assured-workloads/docs/frameworks-overview)
