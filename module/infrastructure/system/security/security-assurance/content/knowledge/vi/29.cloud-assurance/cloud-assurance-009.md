# Cloud configuration review: Rà soát cấu hình đám mây dựa trên bằng chứng

Trong môi trường cloud, một thay đổi cấu hình nhỏ có thể làm thay đổi đáng kể trạng thái bảo mật: một nhóm quyền IAM được mở rộng, một kho lưu trữ trở thành công khai, một endpoint quản trị bị đưa ra Internet hoặc một nguồn audit log bị tắt. Nhiều cấu hình có thể thay đổi qua giao diện quản trị, API, Infrastructure as Code (IaC), dịch vụ tự động hóa và cả hành động khẩn cấp của người vận hành. Vì vậy, tổ chức phải kiểm tra **trạng thái cấu hình đang có hiệu lực**, so sánh với yêu cầu bảo mật, xác minh phát hiện và lưu bằng chứng theo thời điểm.

**Cloud configuration review** là hoạt động đánh giá có phương pháp đối với cấu hình tài khoản, dịch vụ và tài nguyên cloud nhằm xác định cấu hình có đáp ứng các mục tiêu kiểm soát và mức rủi ro đã được chấp nhận hay không. Trong module **SECURITY_SECURITY_ASSURANCE**, đây là một phần của **security assurance liên tục**: kết nối yêu cầu và security controls với bằng chứng kỹ thuật, kết quả kiểm tra, phát hiện sai lệch và quá trình khắc phục.

Một cuộc review tốt phải trả lời được năm câu hỏi: **Đang kiểm tra tài nguyên nào? Cấu hình đúng phải là gì? Trạng thái thực tế là gì? Vì sao sai lệch gây rủi ro trong ngữ cảnh này? Bằng chứng nào chứng minh kết luận và việc khắc phục?**

## 1. Mục tiêu và ranh giới của Cloud configuration review

### 1.1. Những gì cần đạt

Sau bài học, người học có thể:

1. Xác định phạm vi review từ danh mục tài khoản, dịch vụ, tài nguyên và luồng dữ liệu.
2. Thiết lập baseline cấu hình gắn với mục tiêu bảo mật và mô hình trách nhiệm của dịch vụ cloud.
3. Thu thập trạng thái cấu hình bằng API, xuất cấu hình hoặc IaC; đánh giá quyền hiệu lực và điều kiện áp dụng thay vì chỉ đọc một thuộc tính riêng lẻ.
4. Phân loại phát hiện theo mức rủi ro, phân biệt sai lệch thật, ngoại lệ được duyệt và trường hợp chưa đủ bằng chứng.
5. Tạo báo cáo có thể truy vết và khép kín vòng xử lý bằng sửa lỗi, kiểm thử lại và theo dõi configuration drift.

### 1.2. Review cấu hình khác với những hoạt động nào?

| Hoạt động | Câu hỏi chính | Ví dụ bằng chứng |
|---|---|---|
| **Configuration review** | Cấu hình đang có hiệu lực có đáp ứng baseline và mục tiêu kiểm soát không? | Bản xuất policy/IAM, tham số mạng, tùy chọn mã hóa, cấu hình log, kết quả đối chiếu. |
| **Vulnerability assessment** | Workload hoặc phần mềm có lỗ hổng đã biết không? | Danh sách phiên bản, kết quả quét CVE và đánh giá khả năng khai thác. |
| **Penetration testing** | Có thể khai thác một chuỗi điểm yếu để gây ảnh hưởng gì trong phạm vi được cấp phép? | Chuỗi bằng chứng kỹ thuật và mức tác động đã xác minh. |
| **Architecture/security design review** | Thiết kế, phân vùng tin cậy và lựa chọn biện pháp có phù hợp rủi ro không? | Sơ đồ kiến trúc, data flow, threat model, quyết định thiết kế. |
| **Compliance audit** | Có đủ bằng chứng đáp ứng yêu cầu kiểm toán/quy định đã xác định không? | Quy trình, thực hiện kiểm soát theo kỳ, kết quả lấy mẫu và ngoại lệ. |
| **Cloud Security Posture Management (CSPM)** | Có thể liên tục phát hiện, tổng hợp và theo dõi sai lệch cấu hình ở quy mô lớn không? | Phát hiện tự động, tài nguyên chịu ảnh hưởng, lịch sử drift và remediation. |

Các hoạt động này hỗ trợ nhau nhưng không thay thế nhau. Công cụ báo “mã hóa đã bật” chưa chứng minh khóa được phân quyền đúng; cấu hình firewall không có cổng quản trị public chưa chứng minh ứng dụng không có lỗ hổng; chứng nhận của nhà cung cấp không chứng minh một tenant đã áp dụng baseline của khách hàng.

### 1.3. Shared responsibility quyết định phạm vi đánh giá

Rà soát phải dựa trên phần mà khách hàng có thể cấu hình và nghĩa vụ họ phải đáp ứng. Với máy ảo IaaS, khách hàng thường quản lý security group, hệ điều hành khách, tài khoản quản trị và phần mềm trong VM. Với managed database, nhà cung cấp có thể quản lý host và runtime nhưng khách hàng vẫn chịu trách nhiệm đối với kết nối, quyền database, policy, tùy chọn backup và một số tham số dịch vụ. Với SaaS, khách hàng tập trung vào tenant settings, SSO/MFA, vai trò người dùng, chia sẻ dữ liệu, tích hợp và retention khi được hỗ trợ.

Nếu một thiết lập thuộc quyền kiểm soát của CSP, cần yêu cầu bằng chứng assurance phù hợp với phạm vi dịch vụ. Không đánh dấu kiểm soát “đạt” chỉ vì khách hàng không nhìn thấy cài đặt đó. Ghi rõ phần việc của mỗi bên và đầu mối chịu trách nhiệm giải trình ở phía tổ chức.

## 2. Xây dựng baseline từ rủi ro và yêu cầu

**Configuration baseline** là tập điều kiện mong đợi cho từng loại tài nguyên hoặc môi trường. Baseline phải có phiên bản, chủ sở hữu, lý do bảo mật, điều kiện áp dụng và cách kiểm chứng. Nó có thể dựa trên chính sách nội bộ, threat model, yêu cầu hợp đồng, hướng dẫn hardening của CSP và các khung tham khảo như CIS Benchmarks, CSA Cloud Controls Matrix hoặc NIST SP 800-53. Không coi một baseline tham khảo là cấu hình bắt buộc áp dụng nguyên xi cho mọi môi trường.

Một control nên tách rõ:

- **Objective:** kết quả bảo mật cần bảo đảm, ví dụ “chỉ tài khoản được cấp quyền mới đọc dữ liệu khách hàng”.
- **Configuration requirement:** điều kiện cụ thể, ví dụ “public access bị chặn và quyền đọc chỉ dành cho danh tính được phê duyệt”.
- **Applicability:** tài nguyên nào, môi trường nào, ngoại lệ kỹ thuật nào.
- **Verification:** lấy dữ liệu từ đâu, kiểm tra điều kiện gì, bằng chứng nào là đủ.
- **Owner và response:** ai xử lý phát hiện, ai duyệt ngoại lệ, khi nào cần rà soát lại.

Ví dụ về một baseline được diễn đạt đủ cụ thể:

| ID | Đối tượng | Tiêu chí kỳ vọng | Cách xác minh |
|---|---|---|---|
| IAM-01 | Tài khoản quản trị tương tác | MFA được thực thi theo chính sách cho mọi principal thuộc phạm vi. | Export cấu hình IAM/SSO, danh sách principal, chính sách và đánh giá trạng thái hiệu lực. |
| IAM-02 | Vai trò máy và dịch vụ | Quyền được giới hạn theo nhiệm vụ; không có wildcard rộng trái phê duyệt. | Policy hiệu lực, trust relationship, phân tích quyền liên tài khoản. |
| NET-01 | Network ingress | Cổng quản trị không mở từ Internet trừ ngoại lệ có biện pháp bảo vệ. | Security group/NSG, firewall, route, IP public và đường kết nối thực. |
| DATA-01 | Object storage chứa dữ liệu nhạy cảm | Không thể truy cập công khai trái chính sách. | Public-access setting, bucket/container policy, ACL, chính sách kế thừa và thử truy cập an toàn nếu được cho phép. |
| DATA-02 | Database và storage | Mã hóa được bật theo yêu cầu; quyền sử dụng khóa được giới hạn. | Trạng thái encryption, metadata về key, key policy và quyền liên quan. |
| LOG-01 | Audit ở cấp tổ chức/tài khoản | Log quản trị cần thiết được bật, chuyển đến nơi bảo vệ và có retention phù hợp. | Cấu hình nguồn log, đích lưu, trạng thái ingest và sự kiện kiểm chứng. |
| RES-01 | Managed database | Chỉ cho phép kết nối cần thiết và sao lưu đáp ứng mục tiêu khôi phục đã phê duyệt. | Network endpoint, rule truy cập, backup policy và kết quả thử restore. |
| GOV-01 | Tài nguyên quan trọng | Có owner, phân loại dữ liệu và môi trường để xác định chính sách. | Inventory, tag/metadata, bản đồ ứng dụng và xác nhận của chủ hệ thống. |

Các câu trong bảng là **ví dụ định hướng**. Để triển khai thực tế, cần thay bằng control ID, quy tắc và ngưỡng do tổ chức phê duyệt. Ví dụ “mọi cổng quản trị đều phải đóng” có thể không phù hợp với một bastion được thiết kế riêng; review phải xem xét đường truy cập, điều kiện xác thực và ngoại lệ.

### Ma trận phạm vi

Không áp dụng mọi phép kiểm tra cho mọi tài nguyên. Có thể lập bảng như sau:

| Loại tài nguyên | Production chứa dữ liệu nhạy cảm | Development không chứa dữ liệu thật |
|---|---|---|
| Object storage | Chặn public access, quyền tối thiểu, encryption, audit, retention/backup phù hợp. | Chặn public access theo chính sách, quyền tối thiểu, mã hóa và logging tương ứng mức rủi ro. |
| VM/compute | Segmentation, quyền truy cập, khóa bí mật, cấu hình image, logging và bảo vệ host. | Kiểm tra exposure, IAM, image và log ở mức yêu cầu; loại bỏ tài nguyên không còn dùng. |
| Managed database | Private connectivity nếu yêu cầu, authentication, encryption, backup và khả năng restore. | Không kết nối tới dữ liệu thật nếu không được duyệt; tách biệt quyền và secrets. |
| Control plane | MFA/SSO, tách nhiệm vụ, audit, bảo vệ role có đặc quyền. | Vẫn cần kiểm soát quyền và audit; hạn chế quyền từ môi trường thử nghiệm sang production. |

**Điểm cốt lõi:** baseline dựa trên **nguy cơ và mục tiêu kiểm soát**; mức chặt chẽ thay đổi theo môi trường nhưng phải ghi rõ lý do và có phê duyệt phù hợp.

## 3. Xác định phạm vi và tạo inventory đáng tin cậy

Một review có chất lượng phụ thuộc vào khả năng trả lời “đã kiểm tra đủ những gì?”. Không thể lấy kết quả sạch từ một phần tài nguyên rồi kết luận toàn bộ hệ thống an toàn.

Tối thiểu cần xác định:

1. **Phạm vi tổ chức:** account/subscription/project, management group/organization, tenant, OU và các account liên kết.
2. **Phạm vi kỹ thuật:** region, VPC/VNet, subnet, identity provider, compute, container, serverless, database, storage, key management, logging và dịch vụ được quản lý.
3. **Phạm vi nghiệp vụ:** ứng dụng, mức nhạy cảm của dữ liệu, bên xử lý dữ liệu, kết nối Internet, hệ thống bên ngoài, mức độ quan trọng đối với vận hành.
4. **Nguồn tạo cấu hình:** console, API, IaC, policy cấp tổ chức, pipeline triển khai, automation, cấu hình runtime hoặc thay đổi thủ công.
5. **Thời gian:** thời điểm xuất dữ liệu, vòng đời tài nguyên, tần suất review, khoảng thời gian log hoặc lịch sử drift được bao phủ.

Nên lấy inventory từ nhiều nguồn phù hợp: API quản lý tài nguyên, hệ thống asset/CMDB, trạng thái IaC và thông tin của chủ ứng dụng. Nếu sử dụng API dưới một principal ít quyền, phải xác nhận rằng kết quả không bị thiếu tài nguyên vì permission, region, paging hoặc bộ lọc.

Ví dụ, kết quả xuất cấu hình của một region **không đại diện** cho những region chưa quét. Tương tự, kho dữ liệu được tạo trực tiếp trên console có thể không nằm trong mã IaC. Hai loại thiếu sót này phải được ghi thành *coverage gap* và xử lý riêng.

### Mô hình biểu diễn phạm vi

~~~text
Tổ chức / Tenant
  ├─ Chính sách cấp tổ chức và danh tính tập trung
  ├─ Tài khoản production
  │    ├─ Region A: VPC, Load Balancer, VM, Database, Storage
  │    └─ Region B: Backup, Logs, KMS
  ├─ Tài khoản development
  │    └─ Resources tạm thời và pipeline
  └─ SaaS / dịch vụ bên thứ ba
       └─ Tenant settings, SSO, sharing policy, audit
~~~

Sơ đồ chỉ mô tả những lớp cần kiểm kê. Với hệ thống hybrid hoặc multi-cloud, bổ sung kết nối giữa cloud và on-premises, federation, quyền xuyên account, đường truyền dữ liệu và nhà cung cấp dịch vụ vận hành.

## 4. Thu thập cấu hình và bằng chứng có thể tái kiểm tra

### 4.1. Chọn nguồn dữ liệu phù hợp

Có ba nguồn thường gặp:

- **Trạng thái thực tế qua API/control plane:** phản ánh cấu hình đang được hệ thống quản lý cloud công bố tại thời điểm thu thập. Đây là nguồn trọng yếu để xác minh điều gì đã triển khai.
- **Infrastructure as Code và policy-as-code:** phản ánh cấu hình dự kiến, lịch sử review và các chốt kiểm tra trước triển khai. Có thể thiếu tài nguyên tạo thủ công hoặc thay đổi sau deploy.
- **Audit logs và kết quả thực thi kiểm soát:** cho biết ai đã thay đổi, lúc nào, và phần nào chứng minh các kiểm soát vận hành. Log không nhất thiết bao gồm mọi cấu hình hoặc sự kiện nếu chưa được bật từ trước.

Đôi khi phải đọc cả **quyền hiệu lực**, bao gồm chính sách gắn vào tài nguyên, chính sách danh tính, kế thừa cấp tổ chức, trust relationship, ACL và các lớp chặn. Một thuộc tính đơn lẻ không đủ chứng minh khả năng truy cập thực tế.

Nên thực hiện phần lớn kiểm tra bằng quyền đọc với phạm vi tối thiểu cần thiết. Những phép thử có thể tạo lưu lượng, mở dữ liệu, thay đổi cấu hình hoặc ảnh hưởng dịch vụ phải có phê duyệt/phạm vi rõ ràng. Không đưa token, private key, dữ liệu cá nhân hay toàn bộ nội dung bí mật vào báo cáo.

### 4.2. Thuộc tính cần ghi cho một lần review

| Trường bằng chứng | Mục đích |
|---|---|
| Control ID, phiên bản baseline | Biết kỳ vọng đang được áp dụng là gì. |
| Tên CSP, service type, account/project, region | Biết kết luận áp dụng cho vị trí/tài nguyên nào. |
| Resource ID, môi trường, owner, mức phân loại | Biết mức độ quan trọng và người xử lý. |
| Nguồn dữ liệu, danh tính thu thập, thời điểm UTC | Đánh giá nguồn gốc và độ mới của bằng chứng. |
| Phép kiểm tra/phiên bản rule và giá trị quan sát | Có thể chạy lại và tái hiện kết quả. |
| Điều kiện kế thừa, liên quan, ngoại lệ | Tránh kết luận sai vì chỉ xem một lớp cấu hình. |
| Kết quả, mức rủi ro, mã phát hiện, bằng chứng retest | Theo dõi đến lúc đóng vòng khắc phục. |

Một **ảnh chụp màn hình** có thể giúp giải thích nhưng thường chưa đủ để truy xuất chính xác cấu hình. Ưu tiên bản xuất dữ liệu có timestamp và resource ID; giới hạn truy cập kho bằng chứng. Nếu cần chứng minh dữ liệu không bị sửa đổi, có thể dùng checksum và audit trail cho tệp bằng chứng theo chính sách tổ chức.

### 4.3. Khi cấu hình “mong muốn” khác trạng thái thực tế

Ví dụ, repository IaC mô tả một bucket private. Sau khi triển khai, quản trị viên sửa policy trên console để chia sẻ ra bên ngoài. Kết quả:

- Đọc mã nguồn IaC có thể cho kết quả **PASS về cấu hình dự kiến**.
- Đọc trạng thái control plane có thể cho kết quả **FAIL về trạng thái thực tế**.
- So sánh hai nguồn tạo một phát hiện **configuration drift**.
- Audit log có thể giúp xác định tác nhân và thời điểm thay đổi nếu ghi nhận đầy đủ.

Hai loại bằng chứng nên cùng được lưu, vì sửa trực tiếp trên console không tự sửa mã IaC, và sửa IaC chưa chắc đã triển khai thành công.

## 5. Những nhóm cấu hình cần review sâu

### 5.1. Identity, access và quyền quản trị

Kiểm tra root/break-glass account, MFA/SSO, lifecycle của người dùng, account dịch vụ, role có đặc quyền, wildcard permission, chính sách assume-role, quyền liên tài khoản, token/API key dài hạn và thời gian tồn tại của phiên. Đối với cloud, **một đường ủy quyền gián tiếp** có thể nguy hiểm hơn quyền gắn trực tiếp vào tài khoản.

Câu hỏi mẫu: Một workload ở tài khoản development có thể assume role để đọc dữ liệu production không? Nếu chính sách ở cả hai bên cho phép, chỉ nhìn policy của tài khoản production có thể bỏ sót khả năng leo thang đặc quyền.

Bằng chứng cần xem xét là **effective permissions**, các ràng buộc cấp tổ chức, điều kiện trong policy, trust policy, tài nguyên đích và các luồng truy cập thực tế. Khi tính hiệu lực của quyền không thể xác định tự động, ghi trạng thái cần xác minh thủ công.

### 5.2. Network exposure và segmentation

Review địa chỉ public, route, NAT/Internet gateway, firewall, security group/NSG, network ACL, private endpoint, peering, VPN, load balancer và đường quản trị. Không nên kết luận một cổng Internet-reachable chỉ từ một rule cho phép, vì còn có tuyến mạng, firewall, subnet, địa chỉ public và lớp chặn khác.

Ưu tiên những trường hợp endpoint quản trị được công khai, database phục vụ Internet trái thiết kế, rule “allow all” và kết nối giữa các vùng tin cậy không được phân tách. Khi cần xác minh khả năng reachability, sử dụng mô hình đường mạng hoặc phép thử được cấp phép, có giới hạn tác động.

### 5.3. Storage, database và bảo vệ dữ liệu

Kiểm tra khả năng public read/write, resource policy/ACL, encryption at rest, TLS, phân quyền quản trị khóa, phiên bản dữ liệu, logging, retention, backup và cấu hình xóa dữ liệu. Phân loại dữ liệu và mô hình chia sẻ quan trọng: một static website public có thể là chủ đích, trong khi bucket chứa hóa đơn cần private.

Không nhầm **tính năng mã hóa đã được cung cấp** với **đã cấu hình mã hóa phù hợp**. Cần đối chiếu kiểu khóa được chọn, ai được phép sử dụng/xóa khóa, dịch vụ nào sử dụng khóa và tác động khi khóa bị vô hiệu hóa. Với backup, phải xét cả khả năng khôi phục, quyền xóa bản sao và sự độc lập cần thiết theo yêu cầu rủi ro.

### 5.4. Logging, monitoring và cảnh báo

Review loại audit events được bật, vùng/account được bao phủ, thời gian lưu, đích log, quyền sửa/xóa log, tích hợp SIEM, cảnh báo các sự kiện quan trọng và xử lý phát hiện. Một log sink được cấu hình **không chứng minh** sự kiện đã tới hệ thống giám sát; cần xác nhận ingestion và một sự kiện thử nghiệm được phép.

Nếu chính nguồn log bị tắt ở tài khoản có quyền cao, đó có thể là rủi ro đáng ưu tiên ngay cả khi chưa ghi nhận bất kỳ hành vi bất thường nào.

### 5.5. Workload, containers và CI/CD

Với VM, đánh giá machine image, quyền truy cập vào metadata service, gắn IAM role, cổng mạng, managed identity và những thiết lập bảo vệ workload thuộc quyền khách hàng. Với Kubernetes, kiểm tra RBAC, admission policies, network policies, secret management, quyền service account, khả năng truy cập API server và logging của cluster; phạm vi trách nhiệm khác nhau giữa cụm tự quản và cụm managed.

Với serverless, cần rà soát quyền thực thi, trigger công khai, environment variables chứa secret, cấu hình mạng và nguồn log. Với CI/CD, xem quyền của pipeline để tạo/sửa tài nguyên cloud, liên kết danh tính OIDC và cách quản lý secrets. Một cấu hình triển khai an toàn nhưng pipeline có quyền quản trị quá rộng vẫn là đường rủi ro lớn.

### 5.6. Governance và cấu hình cấp tổ chức

Các cấu hình nền tảng gồm policy guardrail, giới hạn region, tài khoản chứa log tập trung, chính sách tạo tài nguyên, tag ownership, tách nhiệm vụ, chính sách key/secret và quy trình ngoại lệ. Cần kiểm tra cả **chính sách cấp tổ chức** lẫn thực tế cấu hình từng tài nguyên. Một guardrail chỉ ngăn thao tác mới có thể không tự sửa tài nguyên cũ; cần xác minh tác dụng thực tế.

## 6. Quy trình review từ lập kế hoạch đến kết luận

~~~mermaid
flowchart TD
    A["Xác định mục tiêu bảo mật và phạm vi"] --> B["Lập inventory và baseline có phiên bản"]
    B --> C["Thu thập cấu hình thực tế và nguồn IaC"]
    C --> D["Chạy kiểm tra và lưu bằng chứng"]
    D --> E["Xác minh ngữ cảnh, quyền hiệu lực và ngoại lệ"]
    E --> F{"Kết luận kiểm soát"}
    F -->|PASS| G["Lưu kết quả và lịch kiểm tra lại"]
    F -->|FAIL| H["Giao owner, đánh giá rủi ro và khắc phục"]
    F -->|INCONCLUSIVE| I["Bổ sung dữ liệu hoặc kiểm tra có kiểm soát"]
    F -->|NOT_APPLICABLE| J["Lưu lý do không áp dụng"]
    H --> K["Kiểm tra lại trên trạng thái thực tế"]
    I --> D
    K --> F
    G --> L["Theo dõi drift và thay đổi"]
    J --> L
    L --> C
~~~

Một vòng đánh giá có thể triển khai như sau:

**Bước 1 — Lập kế hoạch.** Gắn review với nghiệp vụ, data classification, threat model và yêu cầu kiểm soát. Chỉ định người sở hữu hệ thống, nhóm cloud/platform, security assurance và bên duyệt rủi ro. Chốt thời điểm lấy bằng chứng, phạm vi và phương pháp kiểm tra.

**Bước 2 — Xác minh completeness.** Đối chiếu danh mục account, region và resource với phạm vi được phê duyệt. Nêu rõ account không truy cập được, region không hỗ trợ hoặc loại tài nguyên chưa có rule; không gộp phần “chưa kiểm tra” vào tỷ lệ PASS.

**Bước 3 — Thu thập trạng thái.** Xuất cấu hình từ API và nguồn policy liên quan, kiểm tra cấu hình được kế thừa và so sánh với IaC nếu có. Ghi timestamp, bản rule, resource ID. Nếu kết quả từ API bị giới hạn quyền hoặc có lỗi phân trang, đánh dấu bằng chứng chưa hoàn chỉnh.

**Bước 4 — So sánh với baseline.** Chạy rule tự động cho điều kiện có thể máy kiểm; dùng review thủ công cho policy nhiều điều kiện, trust path, ngoại lệ nghiệp vụ hoặc hiệu lực thực tế không thể suy ra đơn giản.

**Bước 5 — Triage và xác nhận.** Kiểm tra context: loại dữ liệu, môi trường, Internet exposure, khả năng thực thi quyền, biện pháp bù trừ và phê duyệt ngoại lệ. Tránh tạo ticket cho một “lỗ hổng” chỉ tồn tại do cách scanner giải thích sai đối tượng.

**Bước 6 — Ghi nhận phát hiện.** Mỗi finding cần có điều kiện kỳ vọng, quan sát, rủi ro, tác động có thể xảy ra, bằng chứng và phương án sửa. Phân định trạng thái PASS, FAIL, INCONCLUSIVE và NOT_APPLICABLE.

**Bước 7 — Khắc phục và retest.** Thay đổi theo quy trình quản lý cấu hình; cập nhật IaC hoặc policy guardrail để tránh lặp lại; kiểm tra lại trạng thái sau triển khai và đóng ticket khi có bằng chứng. Nếu phải chấp nhận rủi ro, cần quyết định có thẩm quyền, thời hạn hiệu lực và kiểm soát thay thế.

**Bước 8 — Review liên tục.** Chạy kiểm tra khi tạo PR, trước triển khai, sau thay đổi quan trọng và theo lịch rủi ro. Cảnh báo drift cần đi tới owner có khả năng hành động, không chỉ tạo dashboard.

## 7. Kết luận dựa trên trạng thái kiểm soát

Một lược đồ kết quả rõ ràng giúp tránh tô xanh những gì chưa được kiểm chứng.

| Trạng thái | Định nghĩa | Cách xử lý |
|---|---|---|
| **PASS** | Phạm vi và bằng chứng đủ để xác nhận các tiêu chí của control đang được đáp ứng. | Lưu chứng cứ, timestamp và lịch rà soát lại. |
| **FAIL** | Có bằng chứng về điều kiện thực tế không đạt yêu cầu áp dụng. | Tạo finding, xác định ưu tiên và owner, sửa rồi retest. |
| **INCONCLUSIVE** | Thiếu dữ liệu, không thể xác định quyền hiệu lực, scan lỗi hoặc chưa đủ căn cứ để kết luận. | Thu thập bổ sung, xác nhận thủ công; không ghi PASS. |
| **NOT_APPLICABLE** | Control thực sự không thuộc phạm vi tài nguyên theo quy tắc applicability đã duyệt. | Ghi rõ lý do và người xác nhận; review lại khi thay đổi. |

Một **ngoại lệ được chấp nhận** là thuộc tính quản trị của một kết quả FAIL hoặc một sai lệch, không tự biến cấu hình thành PASS. Ví dụ, cổng quản trị public trái baseline nhưng có phê duyệt tạm thời và bù trừ: trạng thái kỹ thuật vẫn ghi sai lệch, kèm rủi ro đã được chấp nhận đến ngày hết hạn.

### Mức độ ưu tiên theo ngữ cảnh

Không nên xếp hạng chỉ dựa vào chữ “critical” của scanner. Đánh giá:

- **Tác động:** dữ liệu nhạy cảm, vai trò quản trị, độ quan trọng của ứng dụng, khả năng gây gián đoạn.
- **Khả năng bị lợi dụng:** Internet reachability thực tế, điều kiện xác thực, khả năng người ngoài hoặc principal khác sử dụng quyền.
- **Đường tấn công kết hợp:** misconfiguration cho phép truy cập secret, assume role hoặc di chuyển từ development sang production.
- **Phạm vi và tồn tại:** có bao nhiêu resource bị ảnh hưởng, cấu hình tồn tại bao lâu, có log hay không.
- **Kiểm soát bù trừ:** hiệu lực thực tế và độ tin cậy của biện pháp giảm thiểu đã được chứng minh.

Ví dụ, security group chứa rule mở cổng 22 từ mọi IP nhưng VM không có tuyến Internet vào có thể chưa trực tiếp reachable; vẫn cần xem xét vì thay đổi tuyến sau đó có thể gây lộ. Ngược lại, một database public chứa dữ liệu nhạy cảm và tài khoản quản trị yếu có thể cần ưu tiên cao hơn nhiều. Cần kết luận theo đường truy cập và bằng chứng, không phỏng đoán từ một thuộc tính.

## 8. Minh họa phát hiện, xác minh và khắc phục

Tình huống giả định: ứng dụng kế toán lưu hóa đơn trong object storage thuộc tài khoản production. Baseline cấm truy cập công khai. Một scanner phát hiện policy chứa quyền đọc cho principal rộng.

**Không nên kết luận ngay dữ liệu đã bị lộ.** Cần xác minh policy có hiệu lực hay bị chặn bởi lớp cấu hình khác, loại tài nguyên và object, điều kiện áp dụng, tài nguyên có dữ liệu nhạy cảm không, và liệu có bằng chứng về truy cập thực tế hay không. Đồng thời, không được bỏ qua cảnh báo chỉ vì một cờ “block public” đang bật nếu các đường cấp quyền khác vẫn tồn tại.

Ví dụ bản ghi review ở dạng YAML **minh họa**, không đại diện cho schema hoặc API của CSP:

~~~yaml
review:
  id: CLOUD-REV-2026-011
  baseline_version: "1.3"
  collected_at_utc: "2026-11-28T03:00:00Z"
  scope:
    account: "production-example"
    region: "region-a"
    resource_id: "object-storage/invoices-prod"

control:
  id: DATA-01
  objective: "Không cho phép truy cập công khai vào hóa đơn"
  applicability: "Object storage chứa dữ liệu confidential"
  expected: "Không có đường truy cập công khai hiệu lực"

observation:
  source: "Cloud configuration API"
  policy_allows_broad_read: true
  organization_level_block: "unknown"
  resource_level_block: false
  effective_public_access: "not_yet_confirmed"

assessment:
  result: "INCONCLUSIVE"
  reason: "Chưa xác minh đầy đủ chính sách kế thừa và quyền hiệu lực"
  next_action: "Đối chiếu policy kế thừa, principal và điều kiện truy cập"
  evidence_reference: "evidence-store/reviews/CLOUD-REV-2026-011"

ownership:
  accountable: "Accounting Service Owner"
  remediation_owner: "Cloud Platform Team"
  risk_approver: "Authorized Risk Owner"
~~~

Các giá trị ID, region, ngày giờ và kết quả là dữ liệu giả định để trình bày cấu trúc. Một điều kiện chưa biết phải giữ nguyên **INCONCLUSIVE**; không suy diễn thành FAIL hoặc PASS.

Nếu sau bước xác minh xác định một đường truy cập public trái chính sách đang có hiệu lực, tạo finding:

| Thuộc tính | Nội dung minh họa |
|---|---|
| **Finding** | DATA-01 — Object storage chứa hóa đơn có quyền đọc công khai hiệu lực |
| **Bằng chứng** | Resource ID, policy hiện tại, cấu hình chặn quyền công khai ở các lớp, thời điểm, kết quả kiểm tra đường truy cập được phép |
| **Tác động cần đánh giá** | Người ngoài có thể đọc dữ liệu; cần xác định phạm vi object, độ nhạy cảm và lịch sử truy cập |
| **Hành động ngay** | Giới hạn quyền về principal hợp lệ; bảo tồn log và đánh giá khả năng sự cố dữ liệu |
| **Hành động phòng ngừa** | Sửa policy IaC, guardrail và kiểm tra pipeline để không tái xuất hiện |
| **Điều kiện đóng** | Trạng thái thực tế đã chặn quyền trái chính sách, kiểm tra lại PASS, có ticket và evidence link |

Nếu review phát hiện nguy cơ nghiêm trọng đang diễn ra, quy trình xử lý sự cố và bảo vệ dữ liệu của tổ chức có thể phải được kích hoạt song song với sửa cấu hình. Không thực hiện phép thử bằng cách tải xuống dữ liệu khách hàng thực khi chưa được phép.

### Phân biệt kiểm tra cấu hình với chứng minh tác động

Một policy cho phép quyền rộng là bằng chứng về **cấu hình có khả năng gây rủi ro**. Để khẳng định “dữ liệu đã bị truy cập trái phép”, cần chứng cứ hoạt động như access log, sự kiện audit hoặc kết quả điều tra; nhiều môi trường không có đủ telemetry để đưa ra kết luận chắc chắn về quá khứ. Báo cáo phải tách **exposure**, **khả năng khai thác** và **truy cập đã quan sát được**.

## 9. Tự động hóa với policy-as-code và phát hiện drift

Công cụ CSPM hoặc các scanner cloud có thể thu thập cấu hình theo lịch và áp dụng rule. Kiểm tra trong CI/CD có thể chặn cấu hình sai trước khi triển khai. Cả hai cần sử dụng baseline đã được duyệt, có version và owner.

Ví dụ **mã giả**, chỉ minh họa logic kiểm soát, không phải chính sách dùng trực tiếp cho một CSP:

~~~text
FOR each resource IN inventory:
    baseline = applicable_baseline(resource)
    IF baseline is unknown:
        result = INCONCLUSIVE
    ELSE:
        observed = read_effective_configuration(resource)
        IF observed is incomplete:
            result = INCONCLUSIVE
        ELSE IF resource is outside applicability:
            result = NOT_APPLICABLE
        ELSE IF meets_all_requirements(observed, baseline):
            result = PASS
        ELSE:
            result = FAIL
            create_finding(resource, baseline, observed, owner)
    store_evidence(resource, result, timestamp, baseline.version)
~~~

Trong thực tế, kết quả `read_effective_configuration` phải xử lý chính sách kế thừa, IAM và rule phức tạp. Một scanner có thể chỉ đưa ra **candidate finding** để người có chuyên môn xác minh. Việc kiểm tra dựa trên trạng thái IaC phải phân biệt với đánh giá trạng thái đang chạy.

Một luồng kiểm soát có thể kết nối:

~~~text
Pull request IaC
  -> Kiểm tra định dạng, policy-as-code và peer review
  -> Phê duyệt thay đổi
  -> Triển khai qua pipeline
  -> Quét cấu hình đã triển khai qua API
  -> Phát hiện sai lệch / gửi alert có owner
  -> Sửa nguồn cấu hình và retest
  -> Lưu evidence vào control register
~~~

Đối với tài nguyên tồn tại ngắn, quét mỗi tuần có thể bỏ lỡ toàn bộ vòng đời. Cần kết hợp kiểm soát ở thời điểm tạo tài nguyên, guardrail phòng ngừa, sự kiện thay đổi và các cuộc quét đủ thường xuyên theo rủi ro. Với drift, cần lưu lịch sử baseline và policy để phân biệt thay đổi tiêu chí với thay đổi tài nguyên.

### Nguy cơ của tự động sửa lỗi

Auto-remediation có thể giảm thời gian phơi nhiễm nhưng cũng có thể gây gián đoạn, ví dụ tự động chặn endpoint đang phục vụ người dùng hoặc thay key policy khiến ứng dụng mất quyền giải mã. Chỉ tự sửa các trường hợp được phê duyệt trước, có quy tắc, ghi log, rollback và cơ chế xử lý lỗi. Các trường hợp ảnh hưởng lớn cần có xác minh và kế hoạch thay đổi phù hợp.

## 10. Bảo đảm chất lượng của cuộc review

### 10.1. Tránh các kết luận sai thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| **False positive** | Rule nhìn thấy một quyền rộng nhưng lớp tổ chức thực sự chặn mọi đường truy cập liên quan. | Kiểm tra quyền hiệu lực; lưu bằng chứng của lớp chặn. |
| **False negative** | Chỉ quét IaC trong khi cấu hình đã được sửa trên console. | Đối chiếu trạng thái API, audit log và drift. |
| **Phạm vi thiếu** | Scanner không có quyền đọc một account hoặc bỏ một region. | Đánh dấu coverage gap, bổ sung quyền đọc phù hợp và chạy lại. |
| **Ngoại lệ trôi nổi** | Sai lệch được bỏ qua mà không có owner hoặc ngày hết hạn. | Quản lý ngoại lệ với lý do, rủi ro, biện pháp bù trừ và lịch review. |
| **Bằng chứng cũ** | Snapshot được lấy trước thay đổi quan trọng. | Rà soát lại sau change; lưu thời điểm và liên kết tới phiên bản tài nguyên. |
| **Chỉ đếm alerts** | Một rule tạo nhiều finding trùng nhau hoặc finding đã hết hạn. | Nhóm theo control, tài nguyên, root cause và trạng thái đã xác nhận. |
| **Chỉ xem trạng thái “enabled”** | Dịch vụ log/backup bật nhưng không hoạt động đầy đủ. | Kiểm tra hiệu quả bằng sự kiện thử/restore và dữ liệu quan sát được. |

### 10.2. Đo lường coverage và hiệu quả

Các chỉ số hữu ích gồm:

- **Inventory coverage:** tỷ lệ tài nguyên trong phạm vi đã được phát hiện và định danh.
- **Assessment coverage:** tỷ lệ cặp (tài nguyên, control áp dụng) đã được đánh giá bằng bằng chứng đủ mới.
- **Evidence freshness:** tỷ lệ bằng chứng còn trong khoảng thời gian được chính sách chấp nhận.
- **Open findings theo mức ưu tiên:** số phát hiện được xác nhận chưa xử lý, phân theo tuổi và owner.
- **Mean time to remediate (MTTR):** thời gian trung bình từ xác nhận finding đến khi khắc phục được kiểm chứng.
- **Recurrence/drift rate:** tỷ lệ lỗi cùng nguyên nhân tái xuất hiện sau khi đã sửa.

Ví dụ, nếu có 100 cặp tài nguyên–kiểm soát trong phạm vi, 8 cặp không thu thập được dữ liệu và 5 cặp có dữ liệu nhưng chưa thể xác minh, thì **assessment coverage có bằng chứng đủ để kết luận là 87/100 = 87%**. Không được chuyển 13 cặp chưa xác nhận sang PASS để làm đẹp báo cáo.

Mỗi chỉ số cần định nghĩa rõ mẫu số, kỳ đo, phạm vi và cách xử lý tài nguyên mới hoặc bị xóa. Việc giảm số cảnh báo có thể phản ánh cải thiện thực tế hoặc **mất khả năng quan sát**; nên xem coverage cùng số findings.

### 10.3. Kiểm tra độ tin cậy của nguồn

Đối với mỗi lần review, xác minh được rằng người thu thập có quyền đọc đủ, API không trả lỗi/thiếu trang, các dữ liệu kế thừa đã được xét, baseline đúng phiên bản và thời điểm, mẫu resource đại diện cho toàn bộ phạm vi, điều kiện áp dụng rõ ràng. Nếu có biến động quá nhanh giữa các API call, cần ghi khoảng thời gian thu thập và kiểm tra lại các tài nguyên liên quan.

Báo cáo chính thức phải ghi **giới hạn của cuộc review**. Chẳng hạn “không có finding trong các account đã quét” khác với “toàn bộ môi trường cloud đáp ứng baseline”.

## 11. Bàn giao và vòng đời phát hiện

Một bản báo cáo review nên có: mục tiêu, phạm vi, ngày/giờ và phương pháp thu thập, baseline version, mapping control, coverage và gaps, kết quả PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE, danh sách finding đã xác nhận, chủ sở hữu, rủi ro, ngoại lệ, bằng chứng, kế hoạch sửa và retest.

Mô hình trách nhiệm thực hành:

| Vai trò | Trách nhiệm chính |
|---|---|
| **Service/Application Owner** | Xác định nhu cầu nghiệp vụ, phân loại dữ liệu, chịu trách nhiệm giải trình về rủi ro dịch vụ. |
| **Cloud Platform/Operations** | Duy trì tài nguyên, baseline kỹ thuật, IaC và thực hiện sửa cấu hình trong phạm vi mình quản lý. |
| **Security Assurance/Cloud Security** | Xác định phương pháp kiểm tra, rà soát kết quả, xác minh finding và chất lượng bằng chứng. |
| **Risk/Compliance** | Đối chiếu nghĩa vụ liên quan, theo dõi ngoại lệ và quá trình chấp nhận rủi ro có thẩm quyền. |
| **CSP/Managed Service Provider** | Cung cấp trách nhiệm, tính năng, bằng chứng và hỗ trợ theo phạm vi dịch vụ/hợp đồng. |

Người **thực hiện** có thể khác người **chịu trách nhiệm giải trình**. Đặc biệt với môi trường managed service, phải phân ranh giới giữa cấu hình khách hàng tự quản lý và cấu hình do nhà cung cấp vận hành.

## 12. Bài tập tình huống

Một doanh nghiệp chuyển hệ thống đặt hàng lên cloud. Lần review đầu tiên ghi nhận:

- Một security group mở cổng quản trị từ mọi địa chỉ IP, nhưng VM liên quan hiện không có public IP.
- Một bucket chứa chứng từ được cấu hình private trong IaC, nhưng policy thực tế đã thay đổi thủ công sau lần triển khai gần nhất.
- Audit logging của tài khoản production đang bật; tuy nhiên, nhóm vận hành không tìm thấy bản ghi nào được chuyển đến SIEM trong hai ngày gần đây.
- Công cụ CSPM báo 100% PASS trên 60 tài nguyên nó nhìn thấy, trong khi inventory nghiệp vụ ghi 75 tài nguyên trong phạm vi.

**Câu hỏi:** Có thể kết luận môi trường đạt chuẩn bảo mật cấu hình không? Cần hành động và bằng chứng gì trước tiên?

**Gợi ý giải quyết:**

1. **Chưa thể kết luận toàn bộ môi trường đạt.** Mười lăm tài nguyên chưa được bao phủ; cần xác minh nguyên nhân (quyền đọc, region, loại dịch vụ hoặc thiếu inventory) và đánh dấu coverage gap.
2. Với **security group**, xác định route, public endpoint và đường truy cập hiệu lực; không tự khẳng định VM Internet-reachable. Đánh giá mức rủi ro còn lại, khả năng thay đổi tuyến và nhu cầu thật sự của cổng quản trị.
3. Với **bucket**, xuất trạng thái policy có hiệu lực và so sánh với IaC; rà soát điều kiện kế thừa, các quyền public và nội dung dữ liệu. Nếu sai lệch trái baseline, sửa policy thực tế **và** nguồn IaC, điều tra log thay đổi, rồi retest.
4. Với **logging**, kiểm tra đường dữ liệu từ nguồn tới nơi ingest: cấu hình sink, quyền, lỗi truyền, quota, retention và quy tắc lọc. Tạo sự kiện kiểm thử an toàn nếu được phép và xác nhận nó xuất hiện trong hệ thống giám sát.
5. Cập nhật báo cáo với phạm vi thực quét, thời điểm, từng trạng thái kiểm soát, bằng chứng kỹ thuật, mức ưu tiên, owner và thời hạn xử lý. Chỉ đóng finding khi đã xác minh bằng chứng sau sửa.

Bài học quan trọng của **Cloud configuration review** là chất lượng bảo đảm không phụ thuộc vào một con số “compliant” do công cụ hiển thị. Kết luận phải được xây dựng từ **baseline phù hợp, phạm vi đủ, cấu hình hiệu lực được xác minh, bằng chứng truy vết được và quy trình khắc phục có kiểm tra lại**.
