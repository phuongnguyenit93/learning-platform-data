# Integration Runtime và kết nối nguồn dữ liệu tại chỗ

Một doanh nghiệp lưu đơn hàng trên SQL Server đặt trong trung tâm dữ liệu riêng, file CSV trên Windows file share và muốn chuyển dữ liệu mỗi đêm sang Azure Data Lake Storage Gen2 (ADLS Gen2) để phân tích. Nguồn dữ liệu không có public IP; chính sách bảo mật không cho phép mở SQL Server từ Internet. Nhóm triển khai **Azure Data Factory (ADF)** hoặc **Azure Synapse Analytics pipelines** nhưng pipeline có thể báo không kết nối được, dù tài nguyên Azure vẫn hoạt động bình thường.

**Integration Runtime (IR)** là lớp hạ tầng tính toán và kết nối mà ADF/Synapse dùng để chuyển dữ liệu và thực hiện một số hoạt động tích hợp được hỗ trợ. Với nguồn dữ liệu nằm trong mạng riêng, giải pháp thường gặp là **Self-hosted Integration Runtime (SHIR)**: một dịch vụ cài trên máy Windows có quyền truy cập nguồn nội bộ, sau đó kết nối outbound tới Azure để nhận công việc, đọc dữ liệu từ nguồn và gửi tới đích.

Bài học thuộc chương **Nền tảng dữ liệu và phân tích** trong module **CLOUD_PROVIDERS_AZURE**. Nội dung kết nối subscription/resource group, Microsoft Entra ID, VNet, Private Endpoint, SQL Server, Azure Storage, pipelines, monitoring, backup và kiểm soát chi phí khi thiết kế nền tảng dữ liệu trên Azure.

> **Giới hạn:** bài tập trung vào Azure Data Factory và Synapse pipelines, nhất là **Copy Activity**. Khả năng IR theo connector/activity, network endpoints, giới hạn số node, quyền xác thực, Azure-SSIS IR và đơn giá khác nhau theo dịch vụ, vùng và phiên bản. Các ví dụ có placeholder để minh họa; trước khi chạy production phải kiểm tra support matrix, yêu cầu network và cú pháp thực tế của công cụ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Azure IR**, **Self-hosted IR** và **Azure-SSIS IR**, biết khi nào chọn mỗi loại.
2. Vẽ được **control plane** và **data movement path** giữa on-premises, máy SHIR và Azure sink.
3. Lựa chọn máy chủ Windows, cấu hình DNS, proxy, firewall, VPN/ExpressRoute và private endpoints phù hợp.
4. Cài đặt, đăng ký, bảo vệ registration key và vận hành SHIR theo nguyên tắc least privilege.
5. Tạo linked service/dataset dùng `connectVia` và thực hiện Copy Activity SQL Server → ADLS Gen2.
6. Thiết kế nhiều SHIR nodes để tăng availability và điều chỉnh concurrency mà không làm nghẽn hệ thống nguồn.
7. Phân biệt lỗi **network**, **TLS**, **authentication**, **authorization**, **driver** và **query**.
8. Thiết kế incremental loads bằng watermark/CDC, staging và retry idempotent.
9. Thiết lập metrics, logs, alerts, runbooks và đánh giá chi phí/tính đúng đắn dữ liệu.
10. Triển khai một lab kết nối dữ liệu tại chỗ lên Azure và chứng minh kết quả bằng số dòng, checksum, thời gian.

## 2. Vị trí của Integration Runtime trong pipeline

Pipeline là bản thiết kế điều phối: hoạt động nào chạy, theo thứ tự nào, khi nào retry hoặc chuyển nhánh khi lỗi. **Integration Runtime** cung cấp môi trường thực thi/kết nối cho những activity mà nó hỗ trợ.

~~~mermaid
flowchart LR
  T["Trigger / Schedule"] --> P["ADF / Synapse Pipeline"]
  P -.-> IR["Integration Runtime"]
  SQL["SQL Server on-prem"] --> SH["Self-hosted IR Windows host"]
  IR -.-> SH
  SH -->|Transfer data| DL["ADLS Gen2 landing zone"]
  DL --> X["Analytics / transformation"]
  M["Azure Monitor"] -.-> P
  M -.-> SH
~~~

Phân biệt:

| Thành phần | Chức năng | Không nên nhầm với |
|---|---|---|
| Pipeline | Điều phối activities và dependency | Máy chủ đọc dữ liệu |
| Trigger | Kích hoạt theo lịch/sự kiện hoặc thủ công | Công cụ đảm bảo exactly-once |
| Activity | Một bước như Copy, Lookup, stored procedure | Dữ liệu hoặc server thực thi cố định |
| Linked service | Endpoint, authentication, runtime reference | Bảng hoặc file |
| Dataset | Mô tả bảng/file/path và cấu trúc | Đường mạng hoặc credentials riêng |
| Integration Runtime | Môi trường thực thi/kết nối | SQL Server, data warehouse |
| Azure Monitor | Trạng thái, lỗi, metrics | Hệ thống kiểm tra nội dung dữ liệu tự động |

**Điểm cốt lõi:** pipeline orchestration chạy trên dịch vụ Azure, nhưng **data movement của Copy Activity có thể được thực hiện qua SHIR node** trong mạng riêng. Không phải toàn bộ payload luôn đi qua một máy chủ điều phối của ADF.

## 3. Ba loại Integration Runtime

| Loại IR | Nơi thực thi | Workload phù hợp | Cần lưu ý |
|---|---|---|---|
| **Azure Integration Runtime** | Compute do Azure quản lý | Cloud-to-cloud Copy, một số hoạt động chuyển đổi/dispatch tương ứng | Network reachability, region, Managed VNet nếu hỗ trợ |
| **Self-hosted Integration Runtime** | Windows host on-prem hoặc Azure VM có route tới nguồn | Copy từ SQL/Oracle/SMB trong mạng riêng và một số activities hỗ trợ | Khách hàng quản lý host, connector prerequisites, egress, HA |
| **Azure-SSIS Integration Runtime** | Compute Azure cho SSIS package execution | Lift-and-shift SQL Server Integration Services packages | Không phải thay thế SHIR cho mọi Copy Activity |

**Azure IR:** thích hợp khi nguồn và đích reachable từ compute do Azure quản lý. Azure IR trong Managed VNet có khả năng kết nối qua managed private endpoints **tới một số Azure services được hỗ trợ**; không biến Azure IR thành máy có quyền truy cập tùy ý vào toàn bộ LAN doanh nghiệp.

**SHIR:** được cài trên máy Windows có network route tới on-premises database/file server. Nó chủ động kết nối tới control endpoints Azure theo cơ chế sản phẩm và mở kết nối data tới nguồn/đích.

**Azure-SSIS IR:** chạy những SSIS packages được hỗ trợ. Package có thể cần dependencies, drivers và network riêng; có những tích hợp đặc thù giữa SSIS/SHIR trong cấu hình hỗ trợ, nhưng **hai runtime không đồng nghĩa**.

### Đừng coi Mapping Data Flow là Copy Activity

ADF Mapping Data Flows dùng managed compute/Azure IR tương ứng; **không chạy trực tiếp Spark/data-flow engine trên SHIR host** chỉ vì nguồn dữ liệu kết nối qua SHIR. Khi thiết kế workflow, phải xem từng activity có hỗ trợ IR nào và có thể đặt staging intermediate nếu cần.

## 4. Chọn IR theo đường đi thực tế

| Nguồn | Đích | Hướng đầu tiên nên đánh giá |
|---|---|---|
| Azure Blob accessible | ADLS Gen2 accessible | Azure IR |
| SQL Server trong LAN | ADLS Gen2 | **SHIR** |
| Windows file share nội bộ | Azure Blob | **SHIR** |
| Oracle private network | Azure SQL Database | **SHIR** + driver/connector phù hợp |
| Azure SQL/Storage qua managed private endpoints | Azure destinations | Azure IR trong Managed VNet, nếu hoạt động hỗ trợ |
| Cloud data | SQL Server trong LAN | **SHIR** cho đường ghi tới SQL nội bộ |
| Legacy SSIS package | Data lake/Azure SQL | **Azure-SSIS IR** sau compatibility assessment |
| Hai datacenters không kết nối nhau | Cloud sink | Thiết kế network/SHIR theo từng chặng, có thể cần staging |

Câu hỏi quyết định:

1. **Máy chạy Copy Activity** có thể kết nối đến source qua DNS/route/firewall không?
2. Có thể kết nối đến sink qua network/auth tương ứng không?
3. Connector/activity đó có hỗ trợ IR này và những drivers cần thiết không?
4. Đường dữ liệu có tuân thủ yêu cầu quyền riêng tư, residency và chi phí không?
5. Nếu một node hỏng, có node khác đáp ứng cùng source/sink và SLA không?

Một Copy Activity có hai linked services sử dụng **hai SHIR riêng không thông nhau** có thể không thực hiện trực tiếp như mong muốn. Kiểm tra IR selection và connector support; nếu cần, tách luồng qua staging bảo mật với batch checkpoints.

## 5. Sơ đồ control plane và data plane

~~~mermaid
flowchart TD
  A["ADF / Synapse control plane"] -.->|Dispatch / status| H["SHIR Windows host"]
  H -.->|Outbound service channel| A
  H -->|SQL TCP trong LAN| S["SQL Server ERP"]
  H -->|HTTPS / private route| L["ADLS Gen2"]
  S -.->|Không phải mở inbound Internet| H
  L --> O["Data processing / BI"]
~~~

**Control plane:** ADF giữ definition/trigger/pipeline state, điều phối và nhận trạng thái từ runtime. **Data plane:** máy SHIR có thể truyền dữ liệu từ SQL tới ADLS. Luồng dữ liệu không tự đi qua endpoint public của SQL.

Ưu điểm bảo mật: không phải tạo inbound NAT công khai cho SQL Server. Nhưng **máy SHIR vẫn cần outbound service connectivity và network route tới cả source lẫn sink**. Không phải tất cả traffic đều chỉ dùng một port hay một endpoint duy nhất.

### Ba loại kiểm tra độc lập

- **SHIR ↔ Azure control endpoints:** runtime có Online và nhận job được không?
- **SHIR → SQL on-prem:** DNS, port, TLS, login và SELECT có hoạt động không?
- **SHIR → ADLS sink:** route, TLS, Azure identity, storage RBAC/ACL có cho upload không?

IR hiển thị **Online** chỉ chứng minh một phần đường control, **không đảm bảo** query SQL hoặc ghi file lên data lake sẽ thành công.

## 6. Chọn vị trí đặt SHIR

### Phương án A — SHIR trên máy tại chỗ

Phù hợp khi SQL Server và SMB share ở cùng LAN; giảm nhu cầu đưa kết nối nguồn xuyên WAN trước khi đọc. Node kết nối outbound tới Azure service endpoints và upload dữ liệu tới Azure sink.

Điểm cần quản lý: Windows, proxy, corporate firewall, EDR, domain credentials, disk/temp, độ ổn định đường Internet/VPN.

### Phương án B — SHIR trên Azure VM

Phù hợp khi đã có **VPN/ExpressRoute**, các nguồn nội bộ reachable từ VNet và muốn vận hành Windows host trong Azure.

Không có VPN/ExpressRoute/route, Azure VM **không tự nhìn thấy mạng tại chỗ**. Cần thêm VNet/subnet, private DNS và NSG/firewall đúng.

### Phương án C — Nhiều nodes trong logical SHIR

Phù hợp workload production cần high availability hoặc khả năng xử lý song song. Mỗi node phải tới được **cùng data endpoints** và có drivers/credentials được hỗ trợ.

Đừng cài SHIR trên một laptop người dùng có thể sleep hoặc tắt tùy ý. Với production, ưu tiên máy được quản trị có patch windows, resource monitoring, backup config và owner rõ ràng.

## 7. Yêu cầu Windows host và sizing

Các yêu cầu tối thiểu do Microsoft công bố phụ thuộc IR version. Trước khi cài:

- Xác nhận OS Windows và architecture được hỗ trợ.
- Có quyền local administrator để cài đăng ký agent theo quy trình.
- CPU/RAM/disk đủ cho concurrency, encryption, compression và logging.
- Có network ổn định tới SQL/file share và cloud endpoints.
- EDR/antivirus không chặn service executable hoặc thư mục làm việc.
- Clock/time sync và certificate trust store đúng.
- Các connector cần driver chuyên dụng được cài đúng version/architecture.
- Không để data copy cạnh tranh tài nguyên với critical database engine trên cùng máy trừ khi đã kiểm thử.
- Có bản ghi inventory OS, runtime version, drivers, hostname, subnet, owner.

### CPU/RAM/network không thể tách rời

Một host nhiều vCPU vẫn có thể chậm nếu SQL query đọc dữ liệu chậm hoặc đường WAN 200 Mbps. Một link 1 Gbps không bảo đảm 1 Gbps useful throughput nếu VPN, TLS, packet loss, sink throttling hoặc SQL blocking đang giới hạn.

### Capacity là ngân sách chung

Nếu có 20 Copy Activities đồng thời nhưng SHIR chỉ đủ memory cho 4 jobs lớn, tăng activity concurrency có thể **giảm** thông lượng tổng. Đặt giới hạn theo loại nguồn, thời gian, job size và SLO.

## 8. Firewall, DNS, proxy và ports

Lập **network connectivity matrix** trước khi thay firewall:

| From | To | Protocol điển hình | Mục đích |
|---|---|---|---|
| SHIR node | SQL Server | TCP tới port instance, ví dụ 1433 nếu đã cấu hình | Đọc ERP |
| SHIR node | Windows file server | SMB TCP 445 nếu dùng File System connector | Đọc UNC share |
| SHIR node | Microsoft control/relay endpoints | Outbound HTTPS và các endpoints/ports được hỗ trợ | Đăng ký, jobs, telemetry |
| SHIR node | ADLS/Blob | HTTPS 443, hoặc private route tới endpoint | Upload |
| SHIR node | Internal DNS/AD | Ports theo domain/network policy | Name resolution và auth |
| Admin workstation | SHIR host | RDP/VPN/Bastion theo chính sách | Bảo trì |

**TCP 443** thường quan trọng với Azure service connectivity, nhưng các requirements có thể còn Azure Relay endpoints/protocols và điều kiện theo runtime version. Không phát biểu rằng **chỉ mở 443 chắc chắn đủ cho mọi mode**. Lấy FQDN/port allowlist hiện hành của đúng dịch vụ; không mở toàn Internet hoặc inbound SQL public để “thử nhanh”.

### SQL Server port

Default instance có thể dùng TCP 1433 khi được cấu hình, nhưng **named instance** có thể dùng dynamic ports. Hỏi DBA lấy port thực tế, cấu hình listener/FQDN khi cần và tránh mở dải port rộng không cần thiết.

### Proxy

SHIR Windows service có thể không dùng proxy settings của user đang RDP. Phải kiểm tra proxy config **của service/process** và quy tắc bypass với private endpoints. Một proxy bắt auth hoặc TLS interception sai có thể làm SHIR Offline hoặc gây handshake errors.

## 9. Kiểm tra kết nối từ máy SHIR

Ví dụ PowerShell trên **Windows SHIR host lab**:

~~~powershell
# FQDN nội bộ và port thực tế
Resolve-DnsName sql01.corp.example
Test-NetConnection -ComputerName sql01.corp.example -Port 1433

# File share khi sử dụng SMB
Test-NetConnection -ComputerName fileserver.corp.example -Port 445
Test-Path '\\fileserver.corp.example\exports\sales'

# Cloud storage endpoint; nếu Private Endpoint thì kiểm tra private IP
Resolve-DnsName datalakeaccount.dfs.core.windows.net
Test-NetConnection -ComputerName datalakeaccount.dfs.core.windows.net -Port 443
~~~

**Giới hạn của kiểm tra:**

- `Resolve-DnsName` đúng không chứng minh route/firewall.
- `TcpTestSucceeded: True` không chứng minh SQL login/certificate/SQL permissions.
- `Test-Path` dưới tài khoản admin RDP không chứng minh service account/linked service có quyền trên UNC.
- Kết nối HTTPS tới ADLS thành công không chứng minh quyền Storage Blob Data Contributor hoặc ADLS ACL.
- Nếu Azure sink có Private Endpoint, hostname phải resolve private address **và private IP phải reachable** qua VPN/ExpressRoute.
- Thử egress tới control/relay endpoints theo danh sách sản phẩm hiện hành; không tự chế endpoint names.

### Kiểm tra bằng identity thực

Nếu linked service dùng Windows authentication hoặc file share cần AD account, hãy chạy thử theo cơ chế xác thực tương ứng. Không dùng admin domain full-access để tạo “kết nối thành công” khi pipeline production dự kiến chạy bằng account least privilege.

## 10. Các bước tạo Self-hosted Integration Runtime

Quy trình Portal (tên mục có thể khác ở ADF/Synapse version):

1. Xác nhận subscription/resource group và Data Factory hoặc Synapse workspace.
2. Vào **Manage → Integration runtimes** (hoặc mục tương đương).
3. Chọn **New**, chọn loại **Self-hosted**.
4. Đặt tên ổn định, ví dụ `IR_Corp_ERP_Prod`, ghi owner và network scope.
5. Trên Windows host, tải **SHIR installer từ nguồn chính thức** được Portal/Docs chỉ định.
6. Kiểm tra publisher/signature, OS support, version và security approval.
7. Cài ứng dụng theo quyền hạn cho phép.
8. Trong **Integration Runtime Configuration Manager**, đăng ký runtime bằng **authentication/registration key** tương ứng.
9. Kiểm tra node hiển thị **Online/Connected** và có phiên bản hỗ trợ.
10. Kiểm tra service status, outbound connectivity và Windows Event Logs.
11. Tạo SQL Server linked service gắn đúng IR.
12. Thử Test connection, sau đó tạo Copy Activity dữ liệu lab nhỏ.
13. Thiết lập alerts, HA và maintenance/rotation runbook trước production.

### Registration key không phải password SQL

Một registration key cho phép kết nối node với logical SHIR resource. Nó **không** cấp quyền SELECT trong SQL, đọc file share hay ghi ADLS. Quản lý key như secret; không commit vào repo, pipeline parameters, ticket công khai hoặc screenshot.

Nếu nghi lộ key, thực hiện rotation theo quy trình được hỗ trợ. Có thể có nhiều key để phục vụ rotation, nhưng tránh regenerate cả hai keys cùng lúc khi chưa biết tác động lên nodes đang đăng ký.

## 11. Linked service và `connectVia`

**Linked service** lưu endpoint, authentication/config và tham chiếu Integration Runtime. Với SQL Server on-prem, linked service cần trỏ đúng SHIR.

Ví dụ **minh họa cấu trúc** ADF linked service; connector version hiện hành có thể yêu cầu trường auth/connection khác:

~~~json
{
  "name": "LS_OnPremSql",
  "properties": {
    "type": "SqlServer",
    "typeProperties": {
      "connectionString": "Server=sql01.corp.example;Database=ERP;Encrypt=True;TrustServerCertificate=False",
      "password": {
        "type": "AzureKeyVaultSecret",
        "store": {
          "referenceName": "LS_KeyVault",
          "type": "LinkedServiceReference"
        },
        "secretName": "erp-etl-password"
      }
    },
    "connectVia": {
      "referenceName": "IR_Corp_ERP_Prod",
      "type": "IntegrationRuntimeReference"
    }
  }
}
~~~

**Không coi đoạn JSON trên là cấu hình deploy nguyên vẹn**: version connector SQL Server có thể đòi `userName`, `authenticationType` hoặc connection string khác. Hãy tạo linked service trong UI hoặc theo schema hiện hành, rồi xem JSON được sản phẩm sinh ra. Điểm chính là `connectVia.referenceName` tham chiếu SHIR.

### Dataset chỉ mô tả đối tượng dữ liệu

Ví dụ dataset trong một connector/schema tương thích:

~~~json
{
  "name": "DS_ERP_Orders",
  "properties": {
    "type": "SqlServerTable",
    "linkedServiceName": {
      "referenceName": "LS_OnPremSql",
      "type": "LinkedServiceReference"
    },
    "typeProperties": {
      "schema": "dbo",
      "table": "Orders"
    }
  }
}
~~~

Dataset và linked service **không tự copy** bất kỳ dữ liệu nào. Pipeline cần Copy Activity hoặc activity tương ứng, sink dataset, mapping và schedule.

### Test connection từ đâu?

Test connection của linked service dùng cơ chế connection/IR đã cấu hình, khác với việc bạn tự chạy SQL client từ laptop. Kiểm tra error messages trong Monitor/linked service theo đúng node và identity.

## 12. Kết nối nguồn SQL Server tại chỗ

Một source setup tốt gồm:

- FQDN (hoặc AG listener) ổn định và port chính xác.
- Database name, connector version và TLS đúng.
- Credential least privilege: SQL login chỉ có `SELECT` trên bảng/view ETL.
- Index/filter để không full scan bảng lớn vô ý.
- Cho phép truy cập từ đúng SHIR hosts/subnets.
- Query timeout phù hợp và lịch ETL không ảnh hưởng OLTP.
- Timestamps timezone/precision được tài liệu hóa.
- Có owner DBA duyệt cấu trúc các trường được trích xuất.

### Xác thực SQL

**SQL authentication:** dùng read-only login, mật khẩu quản lý trong Key Vault/credential store theo connector support; không ghi plaintext vào JSON.

**Windows/AD authentication:** cần domain, service identity/impersonation/connector support phù hợp. Đừng nghĩ machine SHIR được domain join là pipeline tự dùng đúng user DBA đang RDP.

**Microsoft Entra identity:** một số sản phẩm SQL Server/configuration có thể hỗ trợ Entra auth nhưng không được giả định mọi SQL Server on-prem mặc nhiên chấp nhận managed identity của ADF.

### TLS

Đảm bảo CA chain được host tin cậy, hostname khớp certificate Subject Alternative Name, không dùng `TrustServerCertificate=True` chỉ để vượt một lỗi production. Nếu dùng AG listener, certificate/name phải phù hợp endpoint mà client kết nối.

## 13. Windows file share/SMB và các nguồn legacy

Ví dụ đường dẫn UNC:

~~~text
\\fileserver.corp.example\exports\sales\2026\11\
~~~

Khi dùng File System connector với SHIR:

1. Xác nhận hostname/port 445 và SMB version theo policy.
2. Kiểm tra Share permissions + NTFS ACL cho identity được linked service dùng.
3. Dùng **UNC path** thay mapped drive `Z:` của một user session; Windows service thường không có cùng mappings.
4. Kiểm tra file encoding, delimiter, quote/escape, file locks và schema.
5. Không tự copy file đang được producer ghi dở nếu chưa có handoff marker hoặc atomic rename.
6. Không log full path hoặc file contents có PII nếu vi phạm chính sách.

### Oracle, PostgreSQL hoặc SAP

SHIR giúp đường mạng, nhưng từng connector có thể cần drivers, client libraries, port, certificates hoặc license riêng. SHIR Online **không có nghĩa** connector Oracle/SAP hoạt động. Xác minh support matrix, prerequisites và source-specific permissions.

## 14. Đường ghi tới ADLS Gen2 hoặc Blob

Khi SHIR đọc SQL Server và upload lên ADLS Gen2, host phải có network route và quyền ghi tại Storage.

Nếu dùng **Private Endpoint**:

1. Private Endpoint được tạo cho đúng Storage subresource (ví dụ `dfs` và các endpoints khác khi cần).
2. DNS từ SHIR resolve Storage FQDN sang private IP phù hợp.
3. VPN/ExpressRoute hoặc đường định tuyến đã được phê duyệt kết nối on-prem ↔ Azure VNet.
4. Firewall/NSG không chặn HTTPS tới endpoint.
5. Credential/managed identity/service principal hoặc auth khác được connector hỗ trợ.
6. Azure Storage RBAC và ADLS ACL (nếu dùng hierarchical namespace) cho đúng filesystem/path.

**Không nhầm Azure Storage Contributor ở control-plane với quyền ghi data-plane**. Quyền tạo storage account không tự tương đương quyền ghi blob/file.

Nếu dùng public endpoint với firewall allowlist theo chính sách, cần đánh giá NAT outbound IP, TLS, security posture và rủi ro thay đổi IP. Không mở `Allow access from all networks` tùy tiện chỉ để chạy pipeline.

## 15. Copy Activity: dữ liệu thật đi qua SHIR

Ví dụ workflow:

~~~text
Pipeline: PL_ERP_Orders_To_Lake
  Source linked service: LS_OnPremSql, connectVia=IR_Corp_ERP_Prod
  Source dataset:        DS_ERP_Orders
  Sink linked service:   LS_AdlsLanding
  Sink dataset:          DS_OrdersLanding
  Activity:              Copy_Orders
  Trigger:               01:00 mỗi đêm theo lịch đã phê duyệt
~~~

Các bước:

1. Chọn SQL Server linked service qua SHIR.
2. Chọn bảng hoặc query có filter cụ thể, giới hạn cột.
3. Chọn ADLS sink và định dạng CSV/Parquet theo khả năng activity.
4. Cấu hình mapping source-to-target; xác minh kiểu decimal/datetime.
5. Chọn partitioning/parallelism theo giới hạn connector và source.
6. Đặt activity timeout, retries có giới hạn và failure handling.
7. Chạy debug với ít rows, không dùng dữ liệu PII thật nếu không được phép.
8. Xem output rows/bytes, duration và throughput.
9. Validate data quality, keys và số dòng sau copy.
10. Publish pipeline và enable trigger sau phê duyệt.

### Ví dụ SQL trích xuất theo khoảng thời gian

~~~sql
SELECT
    OrderId,
    CustomerRef,
    CreatedUtc,
    ModifiedUtc,
    AmountMinor,
    CurrencyCode
FROM dbo.Orders
WHERE ModifiedUtc >= @WindowStart
  AND ModifiedUtc < @WindowEnd;
~~~

`@WindowStart` và `@WindowEnd` là **SQL parameters** phải được connector/pipeline binding đúng; không tự được thay từ mọi ADF expression syntax. Tránh nối raw user input vào SQL query.

## 16. Full load và incremental load

**Full load** đọc toàn bộ bảng, phù hợp lần đầu hoặc bảng nhỏ. **Incremental load** chỉ lấy dữ liệu mới/thay đổi, giảm áp lực SQL, mạng, storage và chi phí.

Ví dụ control record:

~~~json
{
  "source": "ERP",
  "entity": "dbo.Orders",
  "lastCommittedWatermarkUtc": "2026-11-19T00:00:00Z",
  "lastSuccessfulBatchId": "erp-orders-20261119"
}
~~~

Một batch mới:

1. Đọc watermark đã commit.
2. Xác định **upper bound** an toàn theo source semantics.
3. Query khoảng `[start, end)` với ranh giới rõ.
4. Ghi vào **staging folder/batchId**.
5. Validate row count/schema/checksum/keys.
6. Publish kết quả cho downstream bằng cơ chế được data format hỗ trợ.
7. **Chỉ sau khi publish thành công** mới cập nhật watermark.

### Tại sao không cập nhật watermark trước?

Nếu pipeline đã ghi watermark mới nhưng copy thất bại, lần sau sẽ nhảy qua records chưa được lưu. Ngược lại, retry cùng window có thể tạo bản sao dữ liệu nếu sink chỉ append vô điều kiện.

### Late arrivals và deletes

`ModifiedUtc` có thể không ghi nhận hard deletes, transactions bị commit muộn hoặc độ chính xác timestamp thấp. Cân nhắc **overlap window + upsert/dedup** hoặc SQL Server **CDC/Change Tracking** khi thích hợp và được DBA hỗ trợ. CDC có retention/permissions/jobs riêng; không phải SHIR tự kích hoạt CDC.

## 17. Idempotency và staging khi Copy Activity retry

Một lần copy lớn có thể ghi 70% rồi timeout. Nếu retry tạo file khác hoặc append không kiểm soát, data lake có thể có bản sao/partial output.

~~~mermaid
flowchart LR
  SRC["SQL ERP"] --> COPY["Copy batch B"]
  COPY --> ST["ADLS staging/runId"]
  ST --> V{"Validate count + schema + keys"}
  V -->|PASS| PUB["Publish partition / table commit"]
  V -->|FAIL| Q["Quarantine + alert"]
  PUB --> WM["Commit watermark B"]
~~~

Các kỹ thuật:

- Dùng **batchId và data window ổn định**.
- Ghi output vào staging path tách khỏi production views.
- Validate trước khi publish.
- Dùng overwrite/merge/upsert theo semantics và công cụ đã chọn.
- Không cho downstream đọc file dở nếu chưa có marker/table commit.
- Nếu dùng lake transactional table format, dựa vào transaction protocol được hỗ trợ; **không mặc định ADLS rename nhiều files là transaction atomic**.
- Retry cùng batch không làm thay đổi kết quả nghiệp vụ.
- Có runbook reprocess và xử lý bad records.

**Copy Succeeded về kỹ thuật không bảo đảm dữ liệu nghiệp vụ đúng**. Cần thêm data quality tests.

## 18. Source consistency và tránh làm nghẽn ERP

Khi copy từ bảng OLTP đang có writes:

- Query có thể đọc các versions ở thời điểm khác nhau nếu nhiều partitions/queries.
- Full scans có thể gây locks hoặc I/O contention.
- Isolations như Snapshot/RCSI có trade-offs và yêu cầu DBA đánh giá; **không bật tùy tiện trên production**.
- Dùng `NOLOCK` để “không chặn” có thể cho dirty/missing/duplicated reads, không phù hợp dữ liệu tài chính cần đúng.
- Nhiều Copy Activities song song có thể làm SQL CPU và transaction log I/O tăng cao.
- Recovery/backup jobs và ETL có thể tranh resources.

### Cần đo gì?

| Nhóm | Ví dụ metric |
|---|---|
| Source SQL | Query duration, CPU, waits, read IOPS, active sessions, blocking |
| SHIR | CPU/RAM, active copy jobs, node available, disk temp |
| Network | Throughput, packet loss, VPN/ExpressRoute utilization |
| Sink | Write latency, throttling, upload failures |
| Pipeline | Rows/s, MiB/s, duration, queue time, retries |
| Business | Data freshness, duplicate rate, validation failures |

Tăng parallel copy chỉ khi **source, network, SHIR và sink còn headroom**.

## 19. Nhiều nodes: high availability và scale-out

Một SHIR node có thể hỏng khi Windows update, VM restart hoặc proxy lỗi. Có thể đăng ký **nhiều nodes cùng một logical SHIR** theo giới hạn sản phẩm để tăng HA và capacity.

~~~mermaid
flowchart TD
  ADF["ADF logical SHIR"] --> N1["SHIR node 1"]
  ADF --> N2["SHIR node 2"]
  N1 --> SQL["On-prem SQL"]
  N2 --> SQL
  N1 --> LAKE["ADLS"]
  N2 --> LAKE
  MON["Health / versions / concurrency"] -.-> ADF
~~~

### HA thật cần gì?

1. Các nodes cùng logical IR và đăng ký hợp lệ.
2. Mỗi node thấy cùng SQL/SMB source, cloud sink, DNS, proxy.
3. Driver versions và certificates nhất quán.
4. Credentials/service identities hoạt động từ cả hai.
5. Nodes nằm trên failure domains khác nhau nếu có thể.
6. Capacity còn lại đủ gánh workload khi một node dừng.
7. Có alerts node Offline, rolling patching và failover drills.
8. Không nhầm Online state với chứng minh data path thành công.

### Scale-out không tự động vô hạn

SHIR không đơn thuần là một Azure serverless pool: bạn quản lý Windows host capacity và số nodes theo giới hạn. Để tăng throughput, kiểm thử parallel copy; **điểm nghẽn có thể ở SQL hoặc WAN**, nên số nodes tăng không làm thông lượng tăng tuyến tính.

## 20. Managed VNet Azure IR không thay VPN tới nguồn tại chỗ

Azure IR trong **Managed Virtual Network** có thể dùng **Managed Private Endpoints** tới các Azure PaaS destinations theo features hỗ trợ. Điều này giúp truy cập private resources trong Azure nhưng **không tự cung cấp route tới bất kỳ datacenter nào**.

So sánh:

| Đường truyền | Lựa chọn cần đánh giá |
|---|---|
| Azure IR → supported Azure resource có Managed Private Endpoint | Azure IR Managed VNet |
| On-prem SQL → Azure sink qua SHIR đặt tại chỗ | SHIR + outbound cloud access |
| On-prem SQL → Azure sink private endpoint | SHIR + VPN/ExpressRoute + private DNS/routes |
| SHIR đặt trên Azure VM → On-prem SQL | SHIR + VNet + VPN/ExpressRoute + firewall |
| SSIS package đang dùng share nội bộ | Azure-SSIS IR + network/dependency assessment |

Managed private endpoint có thể cần **approval** từ chủ resource. Trạng thái Pending/Rejected khiến connection thất bại dù endpoint đã được tạo trong Portal.

## 21. Azure-SSIS IR dành cho trường hợp nào?

Nếu doanh nghiệp có hàng trăm **SQL Server Integration Services** packages, có thể đánh giá Azure-SSIS IR để chạy packages trên compute Azure được quản lý theo mô hình phù hợp.

Điểm cần kiểm tra:

- Compatibility SQL Server/SSIS version và package deployment model.
- Custom components, drivers, license và secret stores.
- SSISDB/catalog hoặc model quản lý packages được hỗ trợ.
- Truy cập on-prem SQL/SMB bằng private networking.
- Dung lượng compute, startup/shutdown, run schedule và chi phí.
- Environment configuration, package logging và failure recovery.

**Không chuyển `Execute SSIS package` thành `Copy Activity` chỉ bằng cách chọn SHIR**. Chúng là hai kiểu workload khác nhau. Trong một số kiến trúc SSIS IR/SHIR có integration đặc biệt, nhưng phải làm theo tài liệu tương ứng chứ không suy rằng chúng thay thế nhau.

## 22. Authentication, Key Vault và phân quyền tối thiểu

Có ít nhất bốn biên xác thực:

1. **Data Factory ↔ SHIR:** registration key/identity của runtime.
2. **SHIR ↔ nguồn on-prem:** SQL login, Windows integrated authentication hoặc cơ chế connector hỗ trợ.
3. **SHIR ↔ Azure sink:** managed identity/Entra token, service principal, SAS hoặc cơ chế được connector hỗ trợ.
4. **Operator ↔ tài nguyên quản trị:** Azure RBAC, Key Vault permissions, pipeline authoring rights.

Microsoft Entra managed identity **không tự** cấp SELECT vào SQL Server on-prem hoặc quyền đọc SMB. Control-plane Contributor không đồng nghĩa có Storage data-plane RBAC.

### Azure Key Vault

- Lưu database passwords/secrets có lifecycle và rotation.
- Linked service tham chiếu secret theo connector support.
- Identity đọc Key Vault được cấp quyền `get` ở scope phù hợp.
- Key Vault networking/private endpoint cũng phải reachable theo đường truy xuất secrets.
- Không để secrets trong JSON pipeline, run outputs hoặc source control.
- Người có quyền publish pipeline không nên tự có quyền đọc mọi secrets production.

### SQL Server

- Tạo principal **chỉ đọc** theo views/bảng cần ETL.
- Tránh `sysadmin` hoặc `db_owner` cho linked service.
- Bật TLS/certificate validation phù hợp FQDN.
- Audit access và data classification.
- Chỉ mở port nguồn tới SHIR subnet/hosts.

### ADLS Gen2

- Principal chỉ ghi vào filesystem/folder cần thiết.
- Xem **Storage Blob Data** roles và ADLS ACL/execute permissions khi bật hierarchical namespace.
- Cấu hình retention, encryption và private networking theo compliance.

## 23. Giám sát runtime và pipeline

| Lớp | Telemetry cần xem |
|---|---|
| Trigger | Chạy đúng lịch, disabled state, trigger failures |
| Pipeline | Run ID, status, duration, parameters được log an toàn |
| Copy Activity | Source/sink, rows/bytes, throughput, elapsed time, retries |
| SHIR | Node online/offline, version, CPU/RAM, concurrency, queued work |
| Windows host | Windows service, Event Logs, proxy/DNS/firewall, disk space |
| SQL source | Query latency, locks, CPU, sessions, resource pressure |
| Storage sink | Upload success/failure, throttling, write latency |
| Data quality | Row counts, schema drift, watermark age, duplicates |
| Security | Auth failures, privilege changes, secret expiry |
| Cost | Activity charges, VM/host, network, storage, Log Analytics |

### Runbook ngắn cho lỗi

1. Lấy Pipeline Run ID/Activity Run ID và thời điểm UTC.
2. Xem runtime type và node thực thi.
3. Nếu node Offline: kiểm tra Windows service + outbound endpoints/proxy.
4. Nếu node Online: xác minh source DNS/TCP/auth/TLS.
5. Kiểm tra sink DNS/route/permissions/ACL.
6. Nếu kết nối tốt: xem SQL query/driver, memory, parallelism, timeout.
7. Đối chiếu rows/bytes và staging để đảm bảo không partial data.
8. Sửa lỗi, **retry idempotent batch**, không nâng watermark nếu chưa complete.
9. Đo lại duration, business freshness và ảnh hưởng nguồn.
10. Ghi nguyên nhân và preventive action.

## 24. Azure CLI: đọc cấu hình Data Factory/IR

Ví dụ Bash trên Azure Cloud Shell hoặc CLI có `az datafactory` commands:

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  --output table

RG="rg-data-lab"
FACTORY="adf-corp-lab"
IR="IR_Corp_ERP_Prod"

az datafactory integration-runtime list \
  --resource-group "$RG" \
  --factory-name "$FACTORY" \
  --output table

az datafactory integration-runtime show \
  --resource-group "$RG" \
  --factory-name "$FACTORY" \
  --name "$IR" \
  --output json
~~~

Xem linked services/pipelines ở mức metadata:

~~~bash
az datafactory linked-service list \
  --resource-group "$RG" \
  --factory-name "$FACTORY" \
  --query "[].name" \
  --output table

az datafactory pipeline list \
  --resource-group "$RG" \
  --factory-name "$FACTORY" \
  --query "[].name" \
  --output table
~~~

Cú pháp CLI/extension, tên properties và phản hồi khác nhau theo version; xác minh bằng `--help` hiện hành. Chỉ dùng read-only operations; **không list authentication keys hoặc in credentials** cho mục đích kiểm tra thông thường.

### Diagnostic settings

~~~bash
FACTORY_ID=$(az datafactory show \
  --resource-group "$RG" \
  --factory-name "$FACTORY" \
  --query id -o tsv)

az monitor diagnostic-settings list \
  --resource "$FACTORY_ID" \
  --output json
~~~

Lệnh đọc diagnostic settings không tự chứng minh logs đã gửi tới workspace. Phải kiểm tra categories, destination, retention và dữ liệu thực tế.

## 25. Log Analytics và KQL

ADF logs có thể nằm trong **AzureDiagnostics** hoặc resource-specific tables như `ADFActivityRun`, `ADFPipelineRun` và `ADFTriggerRun` nếu môi trường đã cấu hình xuất logs. Tên bảng/columns phụ thuộc diagnostic mode; **không giả định một KQL áp dụng cho mọi workspace**.

Ví dụ trên workspace dùng AzureDiagnostics:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.DATAFACTORY"
| where Category =~ "ActivityRuns"
| summarize ActivityLogEntries = count()
  by bin(TimeGenerated, 1h), Resource
| order by TimeGenerated asc
~~~

Với resource-specific table, bắt đầu bằng schema discovery:

~~~kusto
ADFActivityRun
| where TimeGenerated >= ago(24h)
| take 20
~~~

Sau khi xem columns thực, thêm filter Status/Activity/Pipeline/IntegrationRuntime tương ứng. Không bịa cột hoặc coi bảng rỗng là bằng chứng pipeline không chạy khi diagnostic categories chưa bật.

### Tránh log secrets

Activity output có thể chứa query, connection endpoints, file paths, error messages và các parameters nhạy cảm. Khi gửi incident report, dùng **run ID/error code và nội dung đã làm sạch** thay vì toàn bộ raw JSON.

## 26. Troubleshooting theo nhóm lỗi

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| SHIR Offline | Windows service, proxy/egress, host crash | Service status, network diagnostics, Event Logs |
| SHIR Online nhưng SQL timeout | SQL TCP port/DNS/firewall, query block | Test-NetConnection, SQL health |
| SQL login failed | Sai credential, account lock, auth mode | DBA logs, linked service config |
| TLS certificate error | FQDN/SAN/CA mismatch, expired cert | Certificate validation, SQL TLS |
| UNC path không thấy | SMB 445, path sai, service identity permissions | UNC Test-Path dưới identity phù hợp |
| Oracle connector fail | Thiếu driver/provider, architecture mismatch | Connector prerequisites |
| Sink 403 | Storage RBAC/ACL/SAS expiry, firewall policy | Identity và Storage diagnostics |
| Sink DNS public khi cần private | Private DNS/VPN chưa đúng | Resolve-DnsName từ SHIR |
| Copy chậm | SQL scan, WAN, SHIR CPU/RAM, sink throttling | Copy metrics và source monitoring |
| Job queued lâu | SHIR capacity/concurrency, nodes Offline | IR monitoring, active jobs |
| Dữ liệu trùng sau retry | Append không có batch idempotency | Batch/partition staging, dedup |
| Thiếu rows | Watermark, snapshot consistency, late updates | SQL query boundaries, data validation |
| Key registration fail | Sai IR/key, proxy hoặc time sync | IR config, rotation procedure |
| Activity Succeeded nhưng số liệu sai | Mapping, decimal/timezone, schema drift | Data quality checks |
| Logs không thấy | Chưa bật diagnostics hoặc sai bảng | Diagnostic settings và table schema |
| Chi phí tăng | Full copies, retries, host/network/storage/logging | Cost Management + run history |

**Không chữa mọi lỗi bằng cách mở public SQL Server 1433, tắt TLS validation hoặc cấp sysadmin**. Phân biệt lỗi kỹ thuật tại từng hop rồi sửa đúng nguyên nhân.

## 27. Performance: parallelism, compression và WAN

Tốc độ thực chịu giới hạn thấp nhất giữa SQL query, SHIR host, network và sink.

~~~text
Source SQL → LAN → SHIR CPU/RAM → VPN/Internet → Azure Storage
                ↑                    ↑
            Driver/serialization   Bandwidth/latency
~~~

Ví dụ 600 GiB dữ liệu và **80 MiB/s effective throughput**:

~~~text
Transfer lower bound ≈ 600 × 1024 / 80 giây
                     ≈ 7.680 giây
                     ≈ 2 giờ 8 phút
~~~

Đây chưa tính query, staging, retries, validation, sink commit và setup overhead.

### Tăng parallel copy thế nào?

- Đo baseline 1 activity trước.
- Kiểm tra SQL index, WHERE clause/partition ranges và thực tế source reads.
- Chia partition theo key/date hợp lý, không làm mất/đúp rows tại biên.
- Tăng concurrency từng bước, quan sát SQL CPU/locks và network.
- Kiểm tra SHIR resource utilization và sink throttling.
- Tránh nhiều output files rất nhỏ nếu analytics engine chịu metadata overhead.
- Nếu workload ban ngày nhạy, giới hạn concurrency và schedule sau giờ peak.
- Chọn compression phù hợp: ít bytes trên WAN nhưng tốn CPU ở SHIR/source.

**Không phải cứ thêm SHIR node hoặc tăng numberOfParallelCopies là tải nhanh hơn** nếu source SQL đã bão hòa.

## 28. Chi phí của SHIR và pipeline

Một hiểu nhầm phổ biến: “SHIR chạy trong datacenter nên ADF miễn phí”. Cần kiểm tra pricing model hiện hành của **ADF/Synapse activities, data movement, execution, compute** cùng các chi phí liên quan.

| Khoản | Ví dụ |
|---|---|
| Pipeline/orchestration | Activity/trigger executions theo meter |
| Copy/data movement | Thời gian và loại execution/runtime theo biểu giá |
| Windows SHIR host | On-prem server hoặc Azure VM compute/OS/storage |
| HA nodes | Host dự phòng, patching và quản trị |
| Network | VPN/ExpressRoute, egress, Firewall/NAT, cross-region |
| Source DB | CPU/IOPS và tác động OLTP |
| Azure sink | ADLS storage, write transactions, replication |
| Monitoring | Azure Monitor/Log Analytics ingestion/retention |
| Reliability | Retry, validation, staging, reprocessing |

Mô hình:

~~~text
Cost per valid GiB =
  (Data integration charges
   + SHIR host/network cost
   + storage & monitoring
   + reprocessing overhead)
  / GiB dữ liệu đã validate và publish
~~~

Ưu tiên **incremental extraction** thay vì full scan hàng đêm khi đúng nghiệp vụ; chọn cột cần thiết; kiểm tra business outcome và thời gian kết thúc. Chỉ nhìn giá per-GB truyền tải bỏ qua nguồn dữ liệu và pipeline failures là chưa đủ.

## 29. Bảo mật toàn tuyến

Một SHIR node có thể thấy mạng on-prem và Azure destination; nếu host bị xâm nhập, quyền truy cập dữ liệu có thể bị lạm dụng. Các lớp phòng vệ:

1. **Least privilege** cho SQL login, SMB account và ADLS principal.
2. **Private endpoints/VPN** theo chính sách, không mở SQL public inbound.
3. **TLS/certificate validation** với mọi endpoint được hỗ trợ.
4. **Windows hardening**, EDR, patching, hạn chế local admins.
5. **Key Vault/secrets lifecycle**, rotation và audit.
6. **IR registration key protection**, quản trị ai có quyền list/regenerate keys.
7. **Segregation** prod/non-prod và network zones; tránh một SHIR quá quyền.
8. **Data minimization**: nguồn ETL views che cột PII không cần.
9. **Staging retention**: xóa dữ liệu tạm theo policy, bảo vệ path và audit downloads.
10. **Pipeline changes** qua review/Git/IaC, không publish tùy tiện.
11. **Monitoring** privilege changes, auth failures, offline nodes và unusual exports.
12. **Incident runbook** để disable triggers, revoke credentials và kiểm tra data impact.

Một managed identity dùng để ghi ADLS **không** tự có quyền đọc SQL on-prem. Mỗi ranh giới cần authentication + authorization riêng.

## 30. Quản lý nhiều môi trường và CI/CD

Nên có naming conventions:

~~~text
DEV:  IR_Corp_ERP_Dev
TEST: IR_Corp_ERP_Test
PROD: IR_Corp_ERP_Prod
~~~

Nếu có thể, cô lập host/credential/permissions theo môi trường. Không cho dev jobs đọc production ERP chỉ vì có thể chia sẻ IR.

### Checklist triển khai

1. Definition pipeline/linked service được version trong Git/IaC theo workflow được hỗ trợ.
2. Endpoint và IR name được parameterize theo environment.
3. Secrets không nằm trong repository, templates hoặc build logs.
4. Runtime nodes/driver versions kiểm kê như hạ tầng.
5. Trigger production không bật trước test connection + data validation.
6. Patch SHIR theo rolling plan, thử staging trước.
7. Có rollback/forward-fix khi change schema/source credential.
8. Có quy trình alert & on-call, tránh silent failures.
9. Có backup/config recovery cho hạ tầng liên quan.
10. Kiểm tra drift giữa Portal và IaC.

Các tính năng **SHIR sharing** qua data factories/workspaces có thể được hỗ trợ trong những điều kiện nhất định; đừng dùng chúng để bỏ qua phân vùng bảo mật hoặc quota/concurrency.

## 31. Case study: ERP on-prem → ADLS → analytics

### Bối cảnh

Một doanh nghiệp có ERP SQL Server trong LAN, dữ liệu bảng Orders khoảng 1 TiB và tăng 15 GiB/ngày. Báo cáo cần sẵn sàng trước 06:00; không được mở SQL công khai; phía vận hành muốn chịu được hỏng một SHIR node.

### Thiết kế đề xuất

- **SHIR:** hai Windows nodes trong datacenter, mỗi node kết nối được SQL/SMB và ADLS. Với sink private, dùng VPN/ExpressRoute/private DNS.
- **Source:** read-only SQL views, index trên ModifiedUtc/primary key nếu phù hợp.
- **Extraction:** full load ban đầu có lịch riêng; hằng đêm dùng watermark/CDC hoặc overlap + dedup.
- **Sink:** ADLS staging theo run/batch; validation trước khi publish.
- **Reliability:** watermark chỉ commit sau sink publish; retries idempotent; node failover drill.
- **Security:** Entra/RBAC/Key Vault theo connector support, SQL least-privileged account, private networking và PII minimization.
- **Monitoring:** IR health, pipeline freshness, SQL impact, ADLS write errors và cost.

### Giả lập sự cố

Lúc 02:00 node 1 restart. Node 2 vẫn Online nhưng thiếu route tới ADLS Private Endpoint. Pipeline thất bại. Root cause không phải “ADF ở Azure lỗi” mà là **SHIR node dự phòng chưa được kiểm thử data path đầy đủ**. Sau khi sửa route/DNS, retry **cùng batch ID**, đảm bảo watermark vẫn ở phiên bản trước và output không duplicate.

## 32. Bài thực hành tổng hợp

> **An toàn:** chỉ thực hiện trên môi trường lab được cấp quyền; việc tạo Azure resources/copy dữ liệu có thể phát sinh chi phí. Không chạy trên ERP production, không dùng PII thật hoặc publicize registration key.

### Phần A — Kiến trúc và network

1. Vẽ SQL Server on-prem, Windows SHIR, ADF, ADLS Gen2 và analytics compute.
2. Chỉ ra control plane khác data plane.
3. Tạo network matrix: SHIR → SQL, SHIR → control endpoints, SHIR → ADLS.
4. Đo DNS/TCP từ đúng máy SHIR.
5. Nếu sink có Private Endpoint, xác nhận private DNS route.
6. Liệt kê quyền SQL, Storage và Key Vault cần thiết.
7. Đặt freshness SLO và batch window cho dữ liệu.

### Phần B — Tạo runtime và linked services

1. Chọn ADF/Synapse lab đúng resource group/subscription.
2. Tạo SHIR logical resource.
3. Cài installer chính thức trên Windows lab host.
4. Đăng ký node bằng key qua kênh bí mật, xem trạng thái Online.
5. Tạo SQL Server linked service, chọn SHIR bằng `connectVia`.
6. Tạo ADLS linked service/dataset với auth phù hợp.
7. Thử Test connection, giải quyết driver/TLS/port issues nếu có.
8. Chạy Copy Activity trên bảng lab 1.000 records.
9. Xem rows/bytes và xác minh data count/schema/checksum ở ADLS.

### Phần C — Incremental và retry

1. Tạo watermark control record.
2. Copy một khoảng `[start, end)`.
3. Tạo thêm records và chạy incremental lần tiếp theo.
4. Mô phỏng failure giữa chừng trong lab.
5. Xác minh watermark **không tiến** khi sink publish thất bại.
6. Retry cùng batch và kiểm tra không duplicated output.
7. Thử thay schema/nullable field để đánh giá schema drift.
8. Ghi run IDs và validation metrics.

### Phần D — Vận hành

1. Thử thêm node SHIR dự phòng (nếu lab cho phép).
2. Xác minh node 2 thấy đủ source/sink/driver/credentials.
3. Mô phỏng node 1 Offline, đo recovery.
4. Chạy CLI chỉ đọc để xem IR resource/linked service names.
5. Kiểm tra diagnostic settings và log table thực tế.
6. Xây alert khi SHIR offline hoặc data freshness vượt deadline.
7. Đánh giá source CPU/locks và network throughput khi chạy song song.
8. Ước lượng chi phí Copy Activity/host/network/storage/monitoring.
9. Dọn tài nguyên lab theo phê duyệt, không xóa shared resources.

### Câu hỏi tự kiểm tra

**Câu 1.** Integration Runtime là gì và khác pipeline, linked service, dataset ở đâu?

**Câu 2.** Khi nào nên dùng Azure IR, SHIR và Azure-SSIS IR?

**Câu 3.** Azure IR trong Managed VNet có tự nhìn thấy mọi SQL Server trong LAN không? Vì sao?

**Câu 4.** Vì sao SHIR không cần mở inbound SQL port từ public Internet?

**Câu 5.** SHIR Online có chứng minh có thể SELECT từ SQL và upload ADLS không?

**Câu 6.** Những network/identity paths nào cần kiểm tra riêng?

**Câu 7.** Vì sao TCP port 1433 không áp dụng cho mọi SQL Server named instance?

**Câu 8.** Khi File System connector đọc UNC, vì sao tài khoản RDP admin và service identity có thể cho kết quả khác nhau?

**Câu 9.** `connectVia` trong linked service thể hiện thông tin gì?

**Câu 10.** Key đăng ký SHIR có đồng nghĩa với SQL password hoặc managed identity không?

**Câu 11.** Khi thêm SHIR node thứ hai, cần kiểm tra gì để thực sự có HA?

**Câu 12.** Tại sao tăng nhiều Copy Activities có thể làm nguồn ERP chậm hơn?

**Câu 13.** Vì sao watermark phải commit sau khi validate/publish output?

**Câu 14.** ModifiedUtc có thể bỏ sót trường hợp dữ liệu nào? CDC có thể giúp gì?

**Câu 15.** Nếu Copy đã ghi 70% file rồi retry, cần làm gì để tránh duplicate/partial data?

**Câu 16.** Azure Storage Private Endpoint có tự cấp network route từ on-prem không?

**Câu 17.** AuthN/AuthZ tới SQL Server và ADLS có giống nhau không?

**Câu 18.** Azure-SSIS IR có thay thế Copy Activity chạy trên SHIR không?

**Câu 19.** Những telemetry nào giúp phân biệt IR host Offline với SQL query timeout?

**Câu 20.** Khi KQL bảng AzureDiagnostics rỗng, có thể kết luận không có activity logs không?

**Câu 21.** Có những khoản chi phí nào ngoài máy chủ SHIR?

**Câu 22.** Vì sao Copy Activity Succeeded chưa đủ chứng minh data quality?

**Câu 23.** Làm thế nào triển khai prod/dev SHIR mà không chia sẻ credentials hoặc network quá quyền?

**Câu 24.** Vì sao kế hoạch reprocess/replay phải được viết trước production?

**Tiêu chí hoàn thành:** người học chọn được đúng IR theo network và loại activity, mô tả đường dữ liệu on-prem → SHIR → Azure, biết thiết kế linked service, cài và giám sát SHIR, xử lý auth/network lỗi, xây incremental/idempotent copy, lập HA/SLO và phân tích chi phí.

## Kết luận

**Integration Runtime** là thành phần thiết yếu để dữ liệu đi từ nguồn đến đích trong Azure Data Factory và Synapse pipelines. **Azure IR** phục vụ nhiều công việc cloud-accessible; **Self-hosted IR** là cầu nối qua máy Windows có quyền truy cập tài nguyên tại chỗ/private network; **Azure-SSIS IR** tập trung chạy SSIS packages. Chọn loại IR phải dựa trên khả năng **truy cập source, sink và activity execution model**, không chỉ tên dịch vụ đang dùng.

Một pipeline production bền vững cần hơn một node SHIR Online: cần **route/DNS/firewall đúng, source/sink authentication, credential protection, HA được kiểm thử trên từng node, sizing theo SQL/WAN/storage, incremental watermark/CDC, staging và retry idempotent, giám sát freshness/quality cùng cost controls**. Khi phân biệt chính xác control plane và data plane, đội ngũ có thể di chuyển và tích hợp dữ liệu tại chỗ lên Azure mà không phải hy sinh an toàn mạng hoặc độ tin cậy của hệ thống ERP.

