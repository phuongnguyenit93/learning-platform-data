# Database Management và quản lý database tập trung

Khi số lượng cơ sở dữ liệu tăng, công việc vận hành không còn chỉ là đăng nhập từng database rồi kiểm tra CPU hoặc dung lượng. Người quản trị cần biết database nào đang có vấn đề, dữ liệu giám sát còn được thu thập hay không, ai được phép điều tra và tác vụ nào có thể thực hiện trên nhiều database.

**OCI Database Management** cung cấp một console thống nhất cho giám sát, quản lý hiệu năng, chẩn đoán và quản trị các đối tượng được hỗ trợ. Bài học này tập trung vào **Diagnostics & Management cho Oracle Database**, đặt trong bối cảnh tenancy, compartment, IAM, VCN, secret và kiểm soát chi phí của Oracle Cloud Infrastructure. Tham khảo [trang tài liệu Database Management](https://docs.oracle.com/en-us/iaas/database-management/home.htm).

Sau bài học, người học có thể:

- Phân biệt database thực tế, Managed Database, fleet và Database Group.
- Chọn đường kết nối, loại credential và quyền phù hợp khi đưa database vào quản lý.
- Đọc màn hình tổng quan để ưu tiên điều tra mà không nhầm thiếu dữ liệu với database ngừng hoạt động.
- Thực hành enable dịch vụ, kiểm tra dữ liệu và tổ chức database thành nhóm.
- Nhận diện giới hạn của quản lý tập trung về region, tính năng, chi phí và phạm vi tác động.

## 1. Vì sao cần quản lý tập trung?

Giả sử một tổ chức có các database phục vụ bán hàng, báo cáo và tích hợp. Chúng thuộc nhiều compartment, có chủ sở hữu khác nhau và không sử dụng chung lịch bảo trì.

Nếu chỉ quản lý bằng các kết nối thủ công, những câu hỏi sau khó trả lời nhất quán:

- Trong số các database quan trọng, database nào mất kết nối giám sát?
- Dung lượng đang tăng ở database nào và mức tăng có khác thường so với baseline?
- Cảnh báo xuất hiện riêng lẻ hay cùng thời điểm trên nhiều hệ thống?
- Người trực ca có thể xem tổng quan mà không được phép sửa cấu hình không?
- Một tác vụ kiểm tra đã chạy thành công trên bao nhiêu database?

Quản lý tập trung tạo một cách quan sát và điều phối chung. Database vẫn chạy tại nơi triển khai của nó; việc đăng ký hoặc enable giám sát không di chuyển datafile, hợp nhất schema hoặc chuyển workload sang một database khác.

Ví dụ tổ chức vận hành:

| Database | Nơi triển khai minh họa | Mức quan trọng | Nhóm chịu trách nhiệm |
| --- | --- | --- | --- |
| Sales CDB | Base Database Service | Cao | DBA giao dịch |
| Reporting DB | Một triển khai Oracle Database khác được hỗ trợ | Trung bình | DBA phân tích |
| Integration DB | Hệ thống bên ngoài OCI | Cao | DBA tích hợp |

Tên ở bảng là dữ liệu giả định. Một fleet hữu ích phải có cả thông tin kỹ thuật lẫn thông tin vận hành như owner, môi trường và mức độ quan trọng. Chỉ gom tất cả database vào một màn hình chưa đủ để xác định thứ tự xử lý sự cố.

## 2. Các khái niệm cần phân biệt

### 2.1. Database, CDB, PDB và instance

| Khái niệm | Cách hiểu trong vận hành |
| --- | --- |
| Oracle Database | Hệ thống cơ sở dữ liệu được giám sát hoặc quản trị |
| CDB | Container Database, chứa root và các PDB trong kiến trúc multitenant |
| PDB | Pluggable Database, có ngữ cảnh dữ liệu và tài khoản riêng theo mô hình multitenant |
| Instance | Bộ nhớ và các tiến trình phục vụ database |
| RAC database | Một database có nhiều instance cùng truy cập, theo cấu hình RAC |
| DB system hoặc VM cluster | Tài nguyên triển khai hạ tầng của dịch vụ database tương ứng |
| Managed Database | Database đã được enable Diagnostics & Management |

Oracle sử dụng thuật ngữ **Managed Database** cho database đã enable Diagnostics & Management. Thuật ngữ này không có nghĩa database được chuyển thành Autonomous Database hoặc mọi công việc DBA đã được tự động hóa. Xem [Monitor and Manage a Specific Managed Database](https://docs.oracle.com/en-us/iaas/database-management/doc/monitor-manage-specific-managed-database.html).

Ví dụ quan hệ:

~~~text
Tài nguyên triển khai database
└── Oracle Database dạng CDB
    ├── CDB root
    ├── PDB SALES
    └── PDB REPORTING

Database Management
├── Đối tượng quản lý tương ứng với CDB đã enable
└── Các PDB đã được enable theo điều kiện hỗ trợ
~~~

Không đếm CDB, PDB và RAC instance như những bản sao độc lập của cùng một đơn vị nghiệp vụ. Khi đối chiếu số lượng hoặc tổng hợp metric, phải biết đang nhìn cấp nào.

### 2.2. Fleet và Database Group

**Fleet** là tập database đang được quan sát trong phạm vi và bộ lọc hiện tại. **Database Group** là một tài nguyên OCI dùng gom các Managed Database, kể cả database thuộc các compartment khác nhau.

Database Group hữu ích cho việc xem một nhóm database cùng mục đích vận hành và thực hiện tác vụ nhóm khi được hỗ trợ. Xem [Create and Use Database Groups](https://docs.oracle.com/en-us/iaas/database-management/doc/create-use-database-groups.html).

Phân biệt ba cơ chế tổ chức:

| Cơ chế | Vai trò chính | Ví dụ |
| --- | --- | --- |
| Compartment | Tổ chức tài nguyên và xác định phạm vi policy IAM | `ProductionDatabases` |
| Tag | Gắn metadata để phân loại, lọc và quản trị | `Environment=Prod`, `Owner=SalesDBA` |
| Database Group | Gom Managed Database phục vụ giám sát và thao tác nhóm | `sales-production-fleet` |

Thêm database vào group không đổi compartment của database, không tạo replica, không thiết lập Data Guard và không tự cấp quyền cho người xem group.

Đối với group chứa database thuộc nhiều compartment, quyền trên group và quyền trên các thành viên là hai phạm vi cần xem xét riêng. Một nhóm dùng để theo dõi chung cũng không nhất thiết phù hợp để chạy cùng một tác vụ thay đổi.

### 2.3. Quản lý tập trung có phạm vi region

Khi enable Oracle Cloud Database hoặc External Database, phải chọn đúng region. Tài liệu Oracle hiện nêu **không hỗ trợ giám sát và quản lý Oracle Database xuyên region** trong luồng này.

Vì vậy, cần thiết kế inventory và quy trình trực ca theo region; không giả định chọn root compartment sẽ tạo được một fleet toàn cầu. Xem [enable Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/enable-database-management-oracle-cloud-databases.html) và [enable External Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/enable-database-management-external-databases.html).

## 3. Database nào có thể được đưa vào quản lý?

Diagnostics & Management bao gồm các nhóm triển khai Oracle Database như:

- Oracle Cloud Databases trên Base Database Service và các hình thức Exadata được hỗ trợ.
- External Databases đã được kết nối với tài nguyên External Database.
- Autonomous AI Databases theo quy trình và điều kiện riêng.
- Một số mô hình multicloud được Oracle công bố hỗ trợ.

Khả năng còn phụ thuộc loại database, phiên bản, edition và tính năng. Xem [Diagnostics & Management for Oracle Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/database-management-oracle-databases.html).

Database Management còn có các phần dành cho HeatWave và External MySQL. Bài này không áp dụng cấu hình Oracle Database cho mọi database engine. Trước khi triển khai, đối chiếu đúng đối tượng trong [feature support matrix](https://docs.oracle.com/en-us/iaas/database-management/doc/database-management-feature-support-matrix.html).

### 3.1. Basic và Full không tương đương

Đối với Oracle Cloud Databases trên Base Database Service, ExaDB-D và ExaDB-XS:

| Management option | Định hướng sử dụng | Điều cần chú ý |
| --- | --- | --- |
| Basic management | Bộ metric cơ bản và một số khả năng được công bố | Không thay cho bộ tính năng fleet đầy đủ |
| Full management | Fleet monitoring và các khả năng chẩn đoán, quản trị rộng hơn | Có thêm chi phí dịch vụ; tính năng vẫn phụ thuộc edition và loại database |

Basic không có chi phí dịch vụ bổ sung trong phạm vi được Oracle nêu. Full không làm cho mọi tính năng khả dụng trên mọi edition; chẳng hạn Standard Edition có những hạn chế về Performance Hub và các công cụ khác. ExaDB-C@C không có lựa chọn Basic như các triển khai nêu trên.

Khi mục tiêu là thực hành fleet và Database Group, cần chọn option hỗ trợ các khả năng đó. Xem [About Management Options](https://docs.oracle.com/en-us/iaas/database-management/doc/enable-database-management-oracle-cloud-databases.html).

Không dùng bảng này làm giả định về tính phí hoặc quyền sử dụng tính năng cho External Database hay Autonomous Database. Các nhóm đó có quy trình enablement và điều kiện riêng.

### 3.2. Các dịch vụ liên quan giải quyết những nhu cầu khác nhau

| Thành phần | Câu hỏi phù hợp |
| --- | --- |
| Database Management | Database nào cần chú ý; theo dõi và điều tra database cụ thể như thế nào? |
| OCI Monitoring và Alarms | Metric nào vượt điều kiện cảnh báo và thông báo đến đâu? |
| Ops Insights | Xu hướng sử dụng, năng lực và hiệu năng dài hạn thay đổi thế nào? |
| Log Analytics hoặc pipeline log đã cấu hình | Log database ghi lại sự kiện gì? |
| APM | Request ứng dụng chậm ở đâu trên hành trình xuyên dịch vụ? |
| Dịch vụ database và công cụ backup/HA | Backup, restore, patching, scale và bảo vệ dữ liệu được thực hiện thế nào? |

Ops Insights bổ sung phân tích xu hướng và năng lực dài hạn cho Database Management. Hai dịch vụ có thể liên kết từ giao diện nhưng cần enable và quyền phù hợp; không coi dữ liệu của dịch vụ này tự xuất hiện trong dịch vụ kia. Tham khảo [Accessing Related Services](https://docs.oracle.com/en-us/iaas/operations-insights/doc/accessing-related-services.html).

## 4. Kiến trúc kết nối và thu thập dữ liệu

Hai câu hỏi phải giải quyết độc lập:

1. Database Management có được phép sử dụng tài nguyên và credential không?
2. Thành phần thu thập có kết nối được đến database không?

Quyền IAM đúng không khắc phục được một listener không thể truy cập; đường mạng thông suốt cũng không thay cho quyền database.

### 4.1. Đường private endpoint

Đối với lab Base Database Service, Database Management sử dụng private endpoint trong VCN có thể truy cập database:

~~~mermaid
flowchart LR
    O["Người vận hành"] --> IAM["OCI IAM"]
    IAM --> DBM["Database Management"]
    DBM --> PE["Private endpoint trong VCN"]
    PE --> L["Database listener"]
    L --> DB["Oracle Database"]
    DBM -. "Đọc secret theo quyền" .-> V["OCI Vault secret"]
~~~

Private endpoint đại diện cho Database Management trong VCN và sử dụng địa chỉ IP riêng. Nó không bắt buộc cùng subnet với database nhưng phải có khả năng giao tiếp đến database. Đối với loại private endpoint Oracle Cloud Database đang xét, Oracle quy định endpoint theo VCN; không giả định một endpoint quản lý được database ở mọi VCN.

Có loại endpoint cho single instance và cho RAC; chọn đúng loại. Xem [Create a Database Management Private Endpoint for Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/create-database-management-private-endpoint.html).

Private endpoint này khác với private endpoint của một dịch vụ OCI khác. Việc một tài nguyên có địa chỉ private không đồng nghĩa nó đã có kết nối phù hợp với Database Management.

### 4.2. Đường Management Agent

Với External Database, quy trình thông thường gồm:

~~~text
Database ngoài OCI
   ↑ kết nối database từ agent
Management Agent có khả năng truy cập database
   ↓ kết nối đến dịch vụ OCI theo yêu cầu
External Database connection + Database Management
~~~

Cần đăng ký database, thiết lập connection qua Management Agent và chỉ enable khi database đã connected. Một resource handle chỉ biểu diễn tài nguyên bên ngoài; nó không tạo bản sao dữ liệu trong OCI. Tham khảo [External Database-related Prerequisite Tasks](https://docs.oracle.com/en-us/iaas/database-management/doc/external-database-related-prerequisite-tasks.html).

Một số triển khai Exadata cũng có lựa chọn Management Agent; không suy rộng rằng tất cả Oracle Cloud Databases sử dụng chung một đường agent hoặc private endpoint. Hãy kiểm tra [prerequisites theo triển khai Oracle Cloud Database](https://docs.oracle.com/en-us/iaas/database-management/doc/oracle-cloud-database-related-prerequisite-tasks.html).

### 4.3. Kiểm soát mạng theo nguồn và đích thực tế

Ghi lại các thông tin:

| Thông tin | Ý nghĩa khi kiểm tra |
| --- | --- |
| Hostname hoặc SCAN name | Tên mà thành phần thu thập cần phân giải |
| Listener port | Cổng kết nối thực tế |
| Service name | Dịch vụ database cần kết nối, có thể gắn với CDB hoặc PDB |
| Protocol | TCP hoặc TCPS theo cấu hình |
| Source | IP/NSG của private endpoint hoặc máy agent |
| Destination | Listener và các đích liên quan của cấu hình database |

Mở ingress ở phía database và egress ở phía nguồn theo đường kết nối cần thiết. Kiểm tra cả NSG/security list, host firewall, DNS và listener. Với TCPS, còn có cấu hình wallet, chứng thư và thông tin xác thực tương ứng. Xem [Enable Communication Between Database Management and Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/enable-communication-between-database-management-oracle-cloud-databases.html).

Không mở listener cho `0.0.0.0/0` chỉ để xử lý lỗi enablement. Kết nối thành công từ laptop hoặc bastion cũng chưa chứng minh private endpoint có cùng đường truy cập: nguồn lưu lượng và rule có thể khác nhau.

## 5. Phân quyền theo từng lớp

### 5.1. Bốn lớp quyền độc lập

| Lớp | Cho phép điều gì? | Lỗi thường gặp |
| --- | --- | --- |
| IAM của người vận hành | Liệt kê tài nguyên, mở fleet, enable dịch vụ hoặc tạo job | Có database nhưng không thấy nút thao tác |
| IAM của tài nguyên dịch vụ | Đọc secret cần thiết bằng resource principal | Người dùng thấy secret nhưng dịch vụ không đọc được |
| Quyền trong Oracle Database | Đăng nhập, đọc thông tin giám sát hoặc thực hiện tác vụ cụ thể | Kết nối được nhưng chức năng báo thiếu privilege |
| Kết nối mạng và TLS | Truy cập listener và thiết lập phiên | Timeout, service không được nhận diện, wallet không hợp lệ |

Các lớp trên đều cần đúng cho tác vụ tương ứng. Tài khoản IAM được quyền quản trị tài nguyên OCI không tự trở thành `SYSDBA` bên trong Oracle Database.

### 5.2. Tách người xem fleet với người thay đổi hệ thống

Ví dụ policy khởi điểm cho nhóm chỉ xem tổng quan tại compartment lab:

~~~text
Allow group Default/DbFleetReaders to read dbmgmt-managed-databases in compartment ObservabilityLab
Allow group Default/DbFleetReaders to read dbmgmt-managed-database-groups in compartment ObservabilityLab
Allow group Default/DbFleetReaders to read metrics in compartment ObservabilityLab
Allow group Default/DbFleetReaders to read alarms in compartment ObservabilityLab
~~~

Thay `Default`, tên group và compartment bằng giá trị thực. Nếu group và database thuộc các compartment khác nhau, phải cấp quyền ở đúng phạm vi tài nguyên tương ứng.

Đây không phải bộ quyền đầy đủ để dùng mọi công cụ chẩn đoán. Một số API thuộc mức `use` hoặc cần credential khác; mức `use` cũng có thể bao gồm thao tác thay đổi. Khi mở thêm chức năng, đối chiếu API và permission, thay vì nâng toàn bộ nhóm đọc lên `manage dbmgmt-family`. Xem [Policy Details for Database Management](https://docs.oracle.com/en-us/iaas/database-management/doc/policy-details-database-management.html).

Có thể phân công:

- **Fleet readers**: theo dõi tổng quan, xem cảnh báo và chuyển sự cố.
- **Onboarding administrators**: enable database, chuẩn bị endpoint và cấu hình kết nối.
- **Diagnostic operators**: sử dụng công cụ chẩn đoán được phân quyền.
- **Database administrators**: thực hiện thay đổi đã được phê duyệt theo quy trình của tổ chức.

### 5.3. Quyền onboarding còn liên quan dịch vụ khác

Người enable Oracle Cloud Database cần quyền Database Management cùng các quyền tương ứng trên tài nguyên database, networking và secret. Việc tạo endpoint có thể cần thao tác VNIC, subnet và NSG; việc xem tiến độ có thể cần quyền work request.

Ngoài quyền người dùng, Managed Database resource principal cần được phép đọc secret chứa password và wallet nếu được sử dụng. Có thể giới hạn policy đến secret cụ thể. Xem [Permissions Required to Enable Diagnostics & Management for Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/permissions-required-enable-database-management-oracle-cloud-databases.html).

Nếu Console hỗ trợ sinh policy, đọc các statement trước khi áp dụng vào tenancy: phạm vi nào, principal nào và secret nào được phép truy cập. Không suy luận rằng người dùng chọn được secret thì mọi thành phần của pipeline đã có quyền đọc nó.

## 6. Credential và secret trong quản lý tập trung

### 6.1. Tài khoản monitoring khác tài khoản administration

Oracle phân biệt các preferred credential phục vụ:

- **Basic monitoring**: thu thập metric và quan sát fleet.
- **Advanced diagnostics**: dùng các công cụ chẩn đoán phù hợp.
- **Administration**: thực hiện tác vụ quản trị.

Monitoring user cần đúng bộ privilege cho mục đích giám sát; không cấp mặc định toàn bộ quyền DBA để xử lý mọi lỗi. Các script và điều kiện privilege chính thức được dẫn tại [Database User Privileges Required for Diagnostics & Management](https://docs.oracle.com/en-us/iaas/database-management/doc/database-user-privileges-required-database-management.html).

Tên database user, container nơi user tồn tại và service dùng để kết nối phải khớp với đối tượng đang enable. Một user local trong PDB không tự có vai trò monitoring cho CDB root.

### 6.2. Preferred, named và session credential

| Credential | Vai trò |
| --- | --- |
| Preferred credential | Cấu hình kết nối mặc định theo loại nhiệm vụ |
| Named credential | Tài nguyên chứa thông tin user và tham chiếu secret password, có thể quản lý tập trung |
| Session credential | Credential được thiết lập cho phiên thao tác tương ứng |

Credential dùng khi thu thập nền và credential dùng cho một tác vụ quản trị có thể khác nhau. Chọn credential có quyền tương ứng với nhiệm vụ; không đặt một tài khoản mạnh làm mặc định cho mọi người. Xem [Set and Use Credentials](https://docs.oracle.com/en-us/iaas/database-management/doc/use-credentials.html).

Đối với named credential, cần quản lý cả quyền sử dụng tài nguyên credential, quyền trên Managed Database và quyền truy cập secret cần thiết. Named credential không phải cơ chế tự động cấp privilege mới bên trong database. Tham khảo [Create and Manage Named Credentials](https://docs.oracle.com/en-us/iaas/database-management/doc/create-manage-named-credentials.html).

### 6.3. Password rotation là một thay đổi của pipeline

Với database password lưu trong OCI Vault secret, phải cập nhật secret khi đổi password. Nếu chỉ đổi một phía, kết nối giám sát hoặc job có thể thất bại.

Quy trình vận hành đề xuất:

1. Xác định database user, secret và những kết nối đang sử dụng.
2. Chọn cửa sổ thay đổi và cơ chế rollover nếu phiên bản, cấu hình hỗ trợ.
3. Cập nhật password và secret version theo kế hoạch.
4. Kiểm tra kết nối monitoring và một tác vụ phù hợp.
5. Theo dõi thời điểm thu thập dữ liệu gần nhất sau thay đổi.

Lưu metadata như secret OCID và owner; không chép password vào inventory, ticket hoặc script dùng chung.

## 7. Lab: đưa một Base Database vào fleet quản lý

### 7.1. Phạm vi thực hành

Lab sử dụng **một Oracle Database Enterprise Edition 19c dạng CDB, single instance, trên Base Database Service đã có sẵn**, trong môi trường non-production. Chọn Full management để thực hành các khả năng fleet tương ứng.

Không cần tạo database mới cho bài này. Nếu chưa có môi trường phù hợp, có thể khảo sát demo mode ở trang Overview để hiểu giao diện; dữ liệu demo không chứng minh đường kết nối thật hoạt động. Trang [Database Management Overview](https://docs.oracle.com/en-us/iaas/database-management/doc/access-database-management-overview.html) mô tả điểm vào và demo mode.

Bảng chuẩn bị minh họa:

| Thông tin | Giá trị minh họa hoặc nơi lấy |
| --- | --- |
| Region | Region chứa database thực hành |
| Database compartment | `ObservabilityLab` |
| Database | CDB thử nghiệm đã có |
| Management option | Full management |
| Connection mode | Private endpoint cho single instance |
| Host, port, service | Từ cấu hình listener và dịch vụ database thực tế |
| Monitoring user | User được DBA chuẩn bị đúng privilege cho CDB |
| Password secret | OCI Vault secret của monitoring user |
| Group | `database-operations-lab` |
| Tags | `Environment=Lab` và owner của bài thực hành |

Tên ở bảng là ví dụ; không dùng một chuỗi display name thay cho OCID khi thao tác API.

### 7.2. Bước 1: xác minh điều kiện database

Kiểm tra database đang hoạt động và xác định đúng CDB cần enable. Yêu cầu DBA xác minh:

- Monitoring user không bị khóa hoặc hết hạn password.
- User tồn tại ở container phù hợp và có bộ privilege theo tài liệu.
- Service name được listener nhận diện.
- Hostname và listener port đúng với đường kết nối dự kiến.
- Secret đang chứa password tương ứng.

Nếu có SQL client trên máy được phép kết nối, có thể kiểm tra ngữ cảnh phiên:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')      AS db_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')     AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYSTIMESTAMP                         AS captured_at
FROM dual;
~~~

Đây là câu truy vấn nhận diện phiên cho môi trường 19c của lab. Nó không cấp privilege và không chứng minh Database Management private endpoint có cùng khả năng truy cập như SQL client.

Nếu kết quả cho thấy đang ở PDB trong khi mục tiêu là CDB, sửa cấu hình kết nối trước khi tiếp tục. Không chạy thêm lệnh cấp quyền rộng chỉ vì một kết nối được chọn sai.

### 7.3. Bước 2: chuẩn bị secret và quyền sử dụng

Tạo hoặc chọn Vault secret dành cho monitoring user. Đặt secret trong compartment có chủ sở hữu rõ ràng và kiểm tra quyền của:

1. Người thực hiện onboarding.
2. Managed Database resource principal.
3. Các tác vụ khác dự kiến dùng cùng credential, nếu có.

Nếu dùng TCPS, chuẩn bị thêm wallet secret đúng định dạng được hỗ trợ. TCP trong mạng private không tự đồng nghĩa kết nối đã được mã hóa bằng TLS; lựa chọn protocol phải phù hợp cấu hình bảo mật của môi trường.

Không ghi password vào bảng chuẩn bị. Nếu Console có thông báo thiếu resource principal policy, xem statement và phạm vi trước khi bổ sung.

### 7.4. Bước 3: tạo hoặc chọn private endpoint

Trong Console:

1. Chọn region chứa database.
2. Mở **Observability & Management → Database Management → Administration**.
3. Vào **Private Endpoints**.
4. Chọn endpoint single instance đã phù hợp, hoặc tạo endpoint mới theo VCN/subnet dự kiến.
5. Gắn NSG và cấu hình đường truy cập cần thiết đến listener.
6. Ghi lại endpoint, VCN, subnet và các địa chỉ liên quan để hỗ trợ điều tra.

Một endpoint có thể phục vụ nhiều database theo điều kiện hỗ trợ; không tạo endpoint mới cho từng database nếu endpoint hiện có đã phù hợp. Đồng thời, kiểm tra service limit của region trước khi thiết kế quy mô lớn.

Chỉ tiếp tục khi endpoint và rule đã sẵn sàng. Việc lưu một rule chưa chứng minh kết nối database thành công.

### 7.5. Bước 4: enable Diagnostics & Management

Từ Database Management Administration hoặc phần Database Management của tài nguyên Base Database:

1. Chọn đúng database system, database home và database.
2. Với lab này, chọn phạm vi **CDB only**, tránh vô tình enable toàn bộ PDB.
3. Kiểm tra service name, protocol và port.
4. Chọn monitoring user, password secret và wallet secret nếu dùng TCPS.
5. Chọn private endpoint phù hợp.
6. Chọn **Full management** và xác nhận lựa chọn dịch vụ, chi phí của môi trường.
7. Gửi yêu cầu, theo dõi progress/work request và đọc lỗi nếu có.

Quy trình từ tài nguyên Base Database được mô tả trong [Manage Database Management for Base Database Service Resources](https://docs.oracle.com/en/cloud/paas/base-database/dbm-manage/).

Nếu panel hiển thị thêm dịch vụ như Ops Insights, chỉ chọn dịch vụ thuộc phạm vi thực hành. Kết quả enable của từng dịch vụ phải được đọc riêng; không suy luận tất cả đều thành công từ một trạng thái tổng quát.

### 7.6. Bước 5: kiểm tra cả enablement và dữ liệu thu thập

Sau khi enable thành công:

- Xác nhận database có trong danh sách Managed Databases.
- Mở chi tiết và kiểm tra Monitoring status.
- Chọn khoảng thời gian bao gồm thời điểm enable.
- Kiểm tra có điểm dữ liệu mới, đúng database và đúng cấp CDB.
- Đối chiếu monitoring user/connection nếu có lỗi.

Có hai bằng chứng riêng:

~~~text
Enablement thành công
    → cấu hình dịch vụ đã được chấp nhận

Metric mới được thu thập
    → pipeline đang hoạt động tại thời điểm quan sát
~~~

Một nhãn Enabled không bảo đảm pipeline sẽ luôn khỏe sau khi password đổi, rule mạng thay đổi hoặc listener chuyển cấu hình.

### 7.7. Bước 6: tạo Database Group

Vào **Diagnostics & Management → Database Groups**:

1. Chọn compartment chứa tài nguyên group.
2. Tạo `database-operations-lab`, mô tả mục đích và thêm tag phù hợp.
3. Mở group, chọn **Add managed database**.
4. Chọn compartment chứa Managed Database và thêm database vừa enable.
5. Mở **Fleet summary** của group.

Các thao tác tạo và thêm thành viên được mô tả tại [Create a Database Group](https://docs.oracle.com/en-us/iaas/database-management/doc/create-database-group.html) và [Add Managed Databases to a Database Group](https://docs.oracle.com/en-us/iaas/database-management/doc/add-managed-database-database-group.html).

Một group chỉ có một database vẫn đủ để kiểm tra cách tổ chức. Nếu có database non-production thứ hai đã được phép sử dụng, thêm nó rồi xác minh danh sách; không cần tạo database chỉ để tăng số thành viên.

Nếu không thấy thành viên, kiểm tra region, compartment, management option và quyền trên từng tài nguyên trước khi thay đổi IAM.

### 7.8. Bước 7: đối chiếu bằng OCI CLI

Các lệnh Bash dưới đây là thao tác đọc. Cần có OCI CLI đã cấu hình profile và IAM phù hợp.

Ví dụ liệt kê Managed Database thuộc triển khai VM với management option `ADVANCED`:

~~~bash
dbm_compartment_id='<compartment-ocid>'
dbm_region='<oci-region>'

oci database-management managed-database list \
  --compartment-id "$dbm_compartment_id" \
  --deployment-type VM \
  --management-option ADVANCED \
  --region "$dbm_region" \
  --all \
  --output json
~~~

`ADVANCED` là giá trị enum của CLI dùng cho phạm vi quản lý nâng cao; không thay bằng chuỗi nhãn `Full management` của Console. Lệnh trên có bộ lọc cụ thể và không phải inventory cho mọi loại triển khai. Xem [CLI managed-database list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/database-management/managed-database/list.html).

Dùng Managed Database OCID trả về để đọc chi tiết:

~~~bash
dbm_database_id='<managed-database-ocid>'

oci database-management managed-database get \
  --managed-database-id "$dbm_database_id" \
  --region "$dbm_region" \
  --output json
~~~

Đối chiếu kết quả với đối tượng trên Console. Không đoán OCID từ tên database hoặc tự thay loại OCID giữa các API. Tham khảo [CLI managed-database get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/database-management/managed-database/get.html).

Không cần chạy lệnh thay đổi dữ liệu để chứng minh database đã được đưa vào quản lý tập trung.

## 8. Đọc fleet để ưu tiên điều tra

### 8.1. Đi từ phạm vi đến từng database

Trong **Diagnostics & Management**, chọn compartment hoặc Database Group, khoảng thời gian và kỳ so sánh phù hợp. Fleet summary cung cấp inventory, monitoring status, resource usage, alarms và danh sách thành viên.

Các bộ lọc như deployment, database type, lifecycle state, tag và cấp CDB/PDB giúp thu hẹp phạm vi. Từ danh sách thành viên, mở database cần điều tra. Xem [Monitor the Health of Your Oracle Database Fleet](https://docs.oracle.com/en-us/iaas/database-management/doc/monitor-health-your-oracle-database-fleet.html).

Một thứ tự đọc hữu ích:

~~~text
Đúng phạm vi?
→ Dữ liệu còn mới?
→ Database nào quan trọng và có dấu hiệu bất thường?
→ Bất thường bắt đầu từ lúc nào?
→ Có database khác cùng chịu ảnh hưởng?
→ Mở database cụ thể để kiểm tra sâu
~~~

Đặt cùng khoảng thời gian khi so sánh các database. Nếu một màn hình đang xem giờ cao điểm còn màn hình khác xem trung bình cả ngày, kết luận về mức độ bất thường có thể sai.

### 8.2. Monitoring status không phải toàn bộ trạng thái phục vụ

Cần phân biệt:

1. **Lifecycle/availability** của database.
2. **Khả năng thu thập** của Database Management.
3. **Khả năng phục vụ nghiệp vụ** của ứng dụng.

Database có thể vẫn phục vụ ứng dụng trong khi giám sát mất kết nối vì password hoặc rule mạng thay đổi. Ngược lại, metric CPU bình thường không chứng minh giao dịch nghiệp vụ đang thành công.

Khi có khoảng trống dữ liệu, xem Monitoring status timeline và lỗi liên quan nếu có. Cơ chế cảnh báo mất thu thập và nguồn availability cũng khác nhau theo loại database; không áp dụng một metric hoặc một alarm mẫu cho mọi triển khai. Xem [Monitor Database Availability](https://docs.oracle.com/en-us/iaas/database-management/doc/monitor-database-availability.html).

### 8.3. Đọc metric theo ngữ cảnh

| Quan sát | Câu hỏi cần đặt tiếp |
| --- | --- |
| CPU tăng | Tải tăng, số CPU thay đổi hay SQL có hành vi khác? |
| Average Active Sessions tăng | Thời gian chủ yếu trên CPU hay chờ tài nguyên? |
| I/O tăng | Nhiều dữ liệu hơn, thay đổi pattern truy cập hay latency cao? |
| Storage usage tăng | Tốc độ tăng có bình thường và còn bao nhiêu headroom? |
| Một RAC instance khác biệt | Có mất cân bằng tải, thay đổi service hoặc instance gặp vấn đề? |
| Nhiều database cùng bất thường | Có thay đổi hạ tầng hoặc dependency dùng chung? |

Average Active Sessions là số phiên đang hoạt động trung bình, khác với tổng số session đang kết nối. Một connection pool có nhiều kết nối nhàn rỗi không đồng nghĩa database có tải xử lý cao.

Không cộng trực tiếp phần trăm CPU của các database có mẫu số khác nhau. Cũng cần tránh đếm lặp metric ở cấp CDB và PDB hoặc giữa tổng RAC với từng instance. Đọc đơn vị, phạm vi và aggregation trước khi tạo báo cáo fleet.

### 8.4. Ưu tiên theo tác động và độ tin cậy của dữ liệu

Ví dụ số liệu giả định trong một ca trực:

| Database | Dữ liệu thu thập | Dấu hiệu | Hướng xử lý đầu tiên |
| --- | --- | --- | --- |
| Sales | Mới | Hoạt động tăng và ứng dụng báo chậm | Kiểm tra database trong khoảng sự cố |
| Reporting | Mới | CPU tăng đúng lịch batch | Đối chiếu baseline và mục tiêu thời gian batch |
| Integration | Không có dữ liệu mới | Vừa thay secret | Kiểm tra pipeline và credential, đồng thời xác minh ứng dụng |

Không nhất thiết xử lý database có CPU cao nhất trước. Sales có tác động trực tiếp đến người dùng; Reporting có thể đang chạy workload đã biết; Integration cần xác định trạng thái thực vì dữ liệu giám sát thiếu.

Kết luận ban đầu nên phân biệt bằng chứng với giả thuyết:

~~~text
Bằng chứng:
- Sales có dữ liệu đến 10:20.
- Ứng dụng ghi nhận latency tăng trong 10:10–10:20.
- Hoạt động database tăng trong cùng khoảng.

Giả thuyết:
- Một thay đổi workload hoặc dependency làm tăng thời gian xử lý.

Bước tiếp:
- Mở chi tiết database, đối chiếu activity và thay đổi gần thời điểm đó.
~~~

Một màn hình tổng hợp giúp chọn điểm bắt đầu; cần thêm dữ liệu trước khi kết luận nguyên nhân hoặc chạy tuning.

## 9. Cảnh báo gắn với đúng database

OCI Monitoring Alarms đánh giá metric và điều kiện đã cấu hình. Để alarm xuất hiện liên kết trong Diagnostics & Management, Oracle yêu cầu xác định OCID database qua dimension `resourceId`, cùng quyền Monitoring cần thiết. Xem [Monitor Alarms for Managed Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/monitor-alarms-managed-databases.html).

Khi thiết kế một alarm, ghi rõ:

- Database hoặc phạm vi tài nguyên được theo dõi.
- Namespace, metric, dimension và aggregation.
- Ngưỡng, thời gian duy trì điều kiện và mức nghiêm trọng.
- Người nhận và hành động đầu tiên.
- Cách xử lý maintenance window và thiếu dữ liệu.

Ví dụ chính sách vận hành có thể yêu cầu điều tra khi dung lượng vượt ngưỡng liên tục, thay vì gửi thông báo cho mọi điểm dữ liệu tăng ngắn. Ngưỡng thực tế phải dựa vào headroom, tốc độ tăng và thời gian cần để mở rộng tài nguyên.

Không dùng một tên metric đoán từ giao diện cho mọi loại database. Chọn metric được phát ra thực tế trong môi trường và đối chiếu tài liệu theo deployment.

Alarm không thay thế runbook. Một cảnh báo chỉ ghi “database lỗi” sẽ khó sử dụng nếu thiếu database OCID, region, thời gian và hướng dẫn phân biệt lỗi database với lỗi thu thập.

## 10. Tác vụ tập trung và phạm vi ảnh hưởng

### 10.1. Database Management job là gì?

Database Management hỗ trợ SQL job chạy bất đồng bộ trên một Managed Database hoặc các database trong Database Group. **Job definition**, **run** và **execution** cần được phân biệt: một lần chạy nhóm có thể có nhiều execution, mỗi execution gắn với một database.

Job hỗ trợ nhiều loại SQL; Query job có kết quả lưu vào Object Storage và cần các quyền tương ứng. Xem [Create and Monitor Jobs](https://docs.oracle.com/en-us/iaas/database-management/doc/create-monitor-jobs.html).

Database Management job cũng khác với một Oracle Scheduler job nằm bên trong database. Giao diện Database Management có khả năng quản lý Scheduler jobs trong phạm vi được hỗ trợ, nhưng đó là đối tượng và vòng đời khác. Xem [Monitor and Manage Scheduler Jobs](https://docs.oracle.com/en-us/iaas/database-management/doc/monitor-manage-scheduler-jobs.html).

### 10.2. Thực hành tùy chọn bằng Query job trên một database

Chỉ thực hiện phần này khi môi trường có quyền tạo job, credential phù hợp và Object Storage bucket dành cho kết quả. Giữ target ở **một Managed Database non-production**.

Trong trang database:

1. Mở **Management → Jobs → Definitions → Create job**.
2. Chọn nguồn tạo mới, SQL type **Query**.
3. Chọn chạy một lần ngay lập tức.
4. Chọn credential và bucket kết quả theo cấu hình được phép sử dụng.
5. Nhập truy vấn nhỏ sau, không có dấu chấm phẩy cuối:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYSTIMESTAMP AS checked_at
FROM dual
~~~

Sau khi submit, mở run và execution để xác nhận target, trạng thái và kết quả. Chạy thành công câu truy vấn nhỏ chứng minh credential và đường thực thi của tác vụ đó; nó không chứng minh mọi tác vụ quản trị đều có quyền hoặc sẽ thành công.

Bucket kết quả cần quyền truy cập và chính sách lưu giữ phù hợp. Query lấy dữ liệu nghiệp vụ có thể tạo bản sao thông tin nhạy cảm ngoài database, nên phải kiểm soát cả truy vấn lẫn output.

### 10.3. Group monitoring và group execution có điều kiện khác nhau

Có thể gom các database không dùng chung credential để quan sát. Tuy nhiên, tài liệu job hiện nêu khi chạy job cho Database Group:

- Không dùng named credential cho job nhóm.
- Credential được cung cấp phải áp dụng cho tất cả database trong group.

Vì vậy, không mở rộng quyền hoặc đồng bộ password giữa nhiều hệ thống chỉ để thuận tiện chạy một group job. Nếu thành viên có chính sách truy cập khác nhau, dùng tác vụ riêng hoặc chia nhóm thực thi phù hợp.

Một kết quả “đã submit” chưa phải bằng chứng tất cả database đã chạy thành công. Đọc từng execution và xử lý riêng các target lỗi, timeout hoặc chưa hoàn thành.

### 10.4. Không coi group job là transaction xuyên database

Giả sử một tác vụ thay đổi chạy trên ba database:

~~~text
Database A: thành công
Database B: thất bại
Database C: timeout, chưa xác định trạng thái cuối
~~~

Không được suy luận rằng A tự rollback vì B thất bại. Một bộ tác vụ điều phối không tự tạo transaction nguyên tử xuyên các database.

Trước khi tự động hóa thao tác thay đổi:

1. Chốt danh sách target và điều kiện áp dụng.
2. Chạy thử trên phạm vi nhỏ.
3. Xác định cách kiểm tra kết quả tại từng database.
4. Thiết kế khả năng chạy lại hoặc rollback/bù trừ phù hợp.
5. Phân biệt lỗi trước thực thi với trạng thái chưa xác định sau timeout.
6. Kiểm tra group membership trước mỗi đợt chạy.

Đối với lịch chạy lặp, còn phải quản lý việc đổi credential, thay thành viên và chấm dứt lịch khi không còn nhu cầu. Một group được tạo để giám sát không mặc nhiên là phạm vi an toàn cho DDL hoặc DML.

## 11. Vận hành fleet ổn định và kiểm soát chi phí

### 11.1. Duy trì inventory có thể sử dụng được

Các trường nên có trong sổ vận hành:

| Trường | Mục đích |
| --- | --- |
| Database/Managed Database identifier | Tránh nhầm đối tượng trùng display name |
| Region và compartment | Tìm đúng phạm vi quản lý |
| CDB/PDB, RAC/single instance, primary/standby | Hiểu cấp quan sát và vai trò |
| Management option | Biết tập tính năng và phạm vi chi phí |
| Owner, environment, criticality | Ưu tiên xử lý và chuyển giao |
| Endpoint hoặc agent/connection | Tìm đường thu thập dữ liệu |
| Credential reference, secret OCID | Điều phối rotation, không ghi giá trị password |
| Group membership | Biết phạm vi giám sát và tác vụ nhóm |
| Ngày kiểm tra gần nhất | Đánh giá độ mới của inventory |

Inventory phải được cập nhật khi database di chuyển compartment, đổi kết nối, thêm PDB, chuyển vai trò hoặc ngừng sử dụng. Một danh sách cũ có thể khiến job chạy sai target hoặc alarm gửi sai người.

### 11.2. Kiểm tra sau các thay đổi có liên quan

Theo dõi lại pipeline sau khi:

- Thay monitoring password hoặc secret version.
- Đổi NSG, security list, firewall, DNS hoặc listener.
- Thay service name hoặc cấu hình TCPS.
- Restart, patch hoặc nâng cấp agent.
- Thay cấu hình CDB/PDB hoặc database role.
- Bổ sung hoặc loại database khỏi group.

Với Data Guard, cần kiểm tra điều kiện giám sát theo role và trạng thái standby trong tài liệu tương ứng. Không dùng việc primary đã được theo dõi để suy luận mọi trạng thái sau switchover đều được hỗ trợ bởi cùng cấu hình.

Nếu nhiều database mất metric cùng lúc, kiểm tra thành phần chung như endpoint, agent, secret policy hoặc mạng trước khi xử lý từng database độc lập.

### 11.3. Theo dõi chi phí theo phạm vi thực tế

Tách các nhóm chi phí:

| Nhóm | Ví dụ cần theo dõi |
| --- | --- |
| Dịch vụ quản lý | Management option và các dịch vụ bổ sung đã enable |
| Database | Compute, storage và lựa chọn triển khai database |
| Thành phần hỗ trợ | Máy chạy agent, secret, Object Storage kết quả và networking liên quan |
| Vận hành | Bảo trì credential, xử lý cảnh báo và hỗ trợ fleet |

Không coi disable một tính năng giám sát là đã dừng mọi chi phí database. Cũng không suy luận chi phí được tính theo số database chỉ từ số hàng trên fleet, vì cấp CDB/PDB, loại triển khai và điều khoản dịch vụ có thể khác nhau.

Trước khi mở rộng Full management hoặc bật thêm dịch vụ, kiểm tra trang pricing hiện hành từ Overview, phạm vi tài nguyên và báo cáo sử dụng thực tế của tenancy. Dùng tag owner/môi trường để phân bổ và rà soát phần tài nguyên không còn được sử dụng.

### 11.4. Offboarding có kiểm soát

Khi đưa database ra khỏi phạm vi quản lý:

1. Xác định những group, job, alarm và credential còn tham chiếu.
2. Dừng hoặc chỉnh lịch tác vụ không còn phù hợp.
3. Loại thành viên khỏi group khi cần.
4. Disable Diagnostics & Management theo phạm vi đã chọn.
5. Chỉ xóa endpoint, secret hoặc agent khi chắc chắn không còn tài nguyên khác dùng chung.
6. Cập nhật inventory và lưu bằng chứng cần thiết.

Không xóa database thực tế để thay cho thao tác ngừng giám sát. Đối với lab, database có sẵn là tài nguyên của môi trường; chỉ dọn các thành phần được tạo riêng và được phép dọn.

## 12. Các lỗi thường gặp khi quản lý tập trung

| Triệu chứng | Kiểm tra đầu tiên |
| --- | --- |
| Không thấy database trong Console | Region, compartment, bộ lọc, quyền và trạng thái enablement |
| Có database nhưng thiếu tính năng fleet | Management option, edition và feature support matrix |
| Endpoint đã tạo nhưng kết nối timeout | Đúng VCN/loại endpoint, source rule, listener và firewall |
| Secret chọn được nhưng enable thất bại | Quyền người dùng khác với resource principal; kiểm tra secret và policy |
| Kết nối bị từ chối sau rotation | Password mới, secret version, user lock/expiry và thời điểm đổi |
| Service name không được nhận diện | Service đã đăng ký với listener và đúng CDB/PDB |
| TCPS thất bại | Port, wallet, chứng thư và cấu hình TLS thực tế |
| Database Enabled nhưng metric ngừng cập nhật | Monitoring status, credential, mạng và thành phần thu thập |
| Xem được fleet nhưng một công cụ báo thiếu quyền | API IAM tương ứng và preferred/session credential |
| Group không đủ thành viên | Compartment của thành viên, quyền và điều kiện hỗ trợ |
| Query job lỗi phần output | Bucket, quyền Object Storage và policy của principal thực thi |
| Alarm có trong Monitoring nhưng không thấy ở database | Dimension `resourceId`, OCID, bộ lọc và quyền |
| Một job nhóm chỉ thành công một phần | Trạng thái từng execution, credential và đặc điểm từng target |

Oracle cung cấp hướng dẫn theo từng lỗi enablement tại [Errors Encountered When Enabling Diagnostics & Management for Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/errors-encountered-when-enabling-database-management-oracle-cloud-databases.html).

Khi ghi nhận một sự cố, tối thiểu lưu:

~~~text
Region:
Compartment:
Database hoặc Managed Database identifier:
Thời điểm và khoảng thời gian quan sát:
Tác vụ đang thực hiện:
Trạng thái enablement và monitoring:
Work request / request identifier nếu có:
Mã lỗi và thông báo đã loại thông tin nhạy cảm:
Thay đổi gần nhất:
Bằng chứng ứng dụng còn hoặc không còn phục vụ:
~~~

Thông tin này giúp tách ba hướng xử lý: quyền truy cập, đường thu thập và trạng thái database. Không đưa password, wallet content hoặc secret value vào báo cáo.

## 13. Kết quả cần đạt sau thực hành

Hoàn tất lab khi có thể chỉ ra:

- Database thực tế nào đã trở thành Managed Database, tại region và compartment nào.
- Đường private endpoint hoặc agent nào phục vụ việc thu thập.
- User và secret reference nào được sử dụng, cùng phạm vi quyền tương ứng.
- Dữ liệu mới trên màn hình chi tiết và database nằm đúng Database Group.
- Kết quả đối chiếu bằng CLI hoặc Query job nếu thực hiện phần tùy chọn.
- Cách phân biệt thiếu dữ liệu, vấn đề hiệu năng và vấn đề phục vụ ứng dụng.
- Những thành phần có chi phí hoặc được dùng chung nên phải kiểm tra trước khi dọn lab.

Giá trị của quản lý tập trung nằm ở một fleet có phạm vi rõ ràng, dữ liệu đáng tin cậy và cách thao tác có kiểm soát. Từ đó, người vận hành mới có cơ sở chọn database cần điều tra sâu, mở rộng giám sát và tự động hóa công việc phù hợp.
