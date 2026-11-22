# Dự án Spring Boot ba lớp với Load Balancer và private database

## 1. Đề bài và kết quả cần đạt

Trong chương **Dự án tích hợp và đánh giá** của module **CLOUD_PROVIDERS_ORACLE**, bạn triển khai một dịch vụ quản lý công việc trên Oracle Cloud Infrastructure (OCI). Người dùng gọi API qua HTTPS; Load Balancer phân phối yêu cầu đến hai máy chạy Spring Boot; dữ liệu được lưu trong cơ sở dữ liệu Oracle chỉ có điểm truy cập private.

Dự án kết nối các kiến thức về tenancy, compartment, IAM, VCN, Compute, lưu trữ, cơ sở dữ liệu Oracle, giám sát và tự động hóa thành một hệ thống có thể vận hành. Một trang API trả về HTTP 200 chưa đủ để hoàn thành: bạn cần chứng minh các đường mạng được giới hạn, dữ liệu tồn tại khi thay máy ứng dụng, và hệ thống tiếp tục phục vụ sau khi một backend ngừng hoạt động.

Sản phẩm tối thiểu gồm:

- API tạo và đọc công việc, có kiểm tra dữ liệu đầu vào và lưu thật vào Oracle Database.
- Public OCI Load Balancer nhận HTTPS trên cổng 443.
- Hai Compute instance không có public IP, chạy cùng một bản ứng dụng.
- Autonomous Database có private endpoint, không bật public access bổ sung.
- Quyền quản trị tách khỏi quyền chạy ứng dụng; mật khẩu database được lấy từ OCI Vault bằng instance principal.
- Bằng chứng kiểm thử chức năng, phân phối lưu lượng, cô lập mạng và lỗi một backend.
- Quy trình triển khai lại, rollback, giám sát và thu hồi tài nguyên kèm dự toán chi phí.

Đây là một API lab có phạm vi truy cập giới hạn cho người học và người đánh giá. Chỉ dùng dữ liệu giả lập. Mẫu mã nguồn chưa có xác thực người dùng cuối; chỉ mở listener cho CIDR được phép. Nếu mở API cho người dùng thật, cần bổ sung xác thực, phân quyền nghiệp vụ và các biện pháp bảo vệ phù hợp trước khi công khai rộng.

## 2. Hiểu đúng “ba lớp” trong dự án

Có hai cách phân lớp cùng xuất hiện nhưng phục vụ hai mục đích khác nhau:

| Góc nhìn | Thành phần | Trách nhiệm |
| --- | --- | --- |
| Hạ tầng: tiếp nhận yêu cầu | Public Load Balancer | Kết thúc TLS phía client, kiểm tra backend và phân phối HTTP |
| Hạ tầng: xử lý ứng dụng | Hai Compute instance private | Chạy Spring Boot, xử lý nghiệp vụ và kết nối database |
| Hạ tầng: dữ liệu | Autonomous Database private | Lưu dữ liệu, kiểm soát quyền SQL và cung cấp khả năng khôi phục |
| Mã nguồn: Controller | REST controller | Nhận HTTP, validate request và tạo response |
| Mã nguồn: Service | Spring service | Điều phối nghiệp vụ, xác định ranh giới transaction |
| Mã nguồn: Repository | JDBC repository | Thực hiện SQL có tham số và ánh xạ kết quả |

Load Balancer không chạy giao diện người dùng hay nghiệp vụ Java. Trong bài này, “ba lớp hạ tầng” mô tả đường đi tiếp nhận–xử lý–dữ liệu của một API; không giả định có một frontend web riêng.

Hai backend phải **stateless** đối với dữ liệu nghiệp vụ. Không lưu công việc vào một `Map` trong JVM, không dùng file cục bộ làm nguồn dữ liệu chính và không phụ thuộc HTTP session trên một máy. Các request liên tiếp có thể đến hai backend khác nhau.

## 3. Kiến trúc tham chiếu và các quyết định thiết kế

~~~mermaid
flowchart TB
    U["Người dùng / người đánh giá"]
    O["Người vận hành"]
    subgraph OCI["OCI: compartment capstone-oci"]
        subgraph VCN["VCN 10.40.0.0/16"]
            subgraph EDGE["Public subnet 10.40.10.0/24"]
                LB["Public OCI Load Balancer\nHTTPS 443 → HTTP 8080"]
            end
            subgraph APP["Private app subnet 10.40.20.0/24"]
                A1["Compute app-1\nSpring Boot :8080"]
                A2["Compute app-2\nSpring Boot :8080"]
                BE["Private endpoint của OCI Bastion"]
            end
            subgraph DATA["Private data subnet 10.40.30.0/24"]
                DB["Autonomous Database private endpoint\nTCPS / mTLS :1522"]
            end
            NG["NAT Gateway"]
            SG["Service Gateway"]
        end
        VAULT["OCI Vault / Secret Management"]
        OBJ["Object Storage private\nArtifact và bằng chứng đã làm sạch"]
        OBS["Logging / Monitoring / Alarms"]
        B["OCI Bastion"]
    end
    U -->|"HTTPS 443"| LB
    LB -->|"HTTP 8080"| A1
    LB -->|"HTTP 8080"| A2
    A1 -->|"mTLS 1522"| DB
    A2 -->|"mTLS 1522"| DB
    O -.->|"SSH session giới hạn thời gian"| B
    B -.-> BE
    BE -.->|"SSH 22"| A1
    BE -.->|"SSH 22"| A2
    A1 -.->|"Ra ngoài để cập nhật gói"| NG
    A2 -.->|"Ra ngoài để cập nhật gói"| NG
    A1 -.->|"Dịch vụ OCI được hỗ trợ"| SG
    A2 -.->|"Dịch vụ OCI được hỗ trợ"| SG
    SG -.-> OBJ
    A1 -.->|"HTTPS + instance principal"| VAULT
    A2 -.->|"HTTPS + instance principal"| VAULT
    A1 -.-> OBS
    A2 -.-> OBS
    LB -.-> OBS
~~~

Sơ đồ thể hiện các luồng logic; không phải mọi mũi tên đều là một route độc lập. Lưu lượng đến Vault, Logging hoặc các API OCI phải được đối chiếu với endpoint và danh sách dịch vụ hỗ trợ Service Gateway trong region. Nếu một endpoint cần truy cập Internet thì dùng NAT và egress phù hợp.

Các quyết định của bản tham chiếu:

1. **Dùng OCI Load Balancer có khả năng xử lý HTTP/HTTPS.** Không thay trực tiếp bằng Network Load Balancer khi vẫn yêu cầu kết thúc TLS và health check HTTP theo cấu hình trong bài.
2. **Hai instance cùng một regional app subnet.** Ưu tiên hai availability domain nếu region, shape và ngân sách cho phép. Trong region một availability domain, dùng hai fault domain khác nhau.
3. **Chọn Autonomous Database với workload giao dịch.** Cấu hình private endpoint và yêu cầu mTLS. Tài liệu Oracle hiện có thể gọi dịch vụ này là Autonomous AI Database; dự án chỉ sử dụng chức năng database giao dịch.
4. **Client → LB dùng HTTPS; LB → app dùng HTTP nội bộ.** Đây là đánh đổi cho lab. Private subnet không mã hóa lưu lượng thay bạn. Nếu yêu cầu mã hóa toàn tuyến, bật TLS ở Spring Boot hoặc reverse proxy và cấu hình SSL cho backend set, bao gồm xác minh chứng thư.
5. **App → database dùng mTLS cổng 1522.** Wallet và tài khoản SQL là hai yếu tố cấu hình riêng; vẫn cung cấp username/password cho tài khoản database theo mẫu trong bài.
6. **Object Storage chứa bản phát hành bất biến.** Wallet, mật khẩu, private key và log chứa thông tin nhạy cảm không nằm trong bucket artifact dùng chung.

Private endpoint của Autonomous Database là điểm đích trực tiếp trong mạng đã cấu hình; đường app → database của kiến trúc này không cần NAT hay Service Gateway. Tham khảo [kết nối độ trễ thấp của Autonomous Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/low-latency-connections.html).

## 4. Chuẩn bị môi trường và quy ước

### 4.1. Điều kiện đầu vào

Bạn cần:

- Một tenancy có quyền tạo tài nguyên trong compartment lab.
- Một region có đủ quota và dung lượng cho hai instance, Load Balancer, VCN và Autonomous Database private.
- Máy phát triển có JDK 21, Maven 3.6.3 trở lên và Git.
- Công cụ `curl`, `jq`, SSH và một công cụ SQL hỗ trợ kết nối Oracle.
- Tên DNS do bạn quản lý và chứng thư TLS hợp lệ cho listener HTTPS.
- Một CIDR quản trị và một CIDR client thử nghiệm, thường là public IP hiện tại kèm `/32`.
- Quyền tạo budget hoặc sự hỗ trợ của quản trị tenancy nếu quyền này được quản lý tập trung.

Đừng giả định Free Tier cung cấp đủ mọi tính năng, shape hoặc private endpoint cần dùng. Kiểm tra cấu hình khả dụng, quota và bảng giá trong tenancy trước khi cấp phát.

Các lệnh Bash trong bài chạy trên Linux VM hoặc môi trường Bash phù hợp. Đường dẫn `/opt/...` và `/etc/...` là đường dẫn trên VM của dự án. Chúng không phải yêu cầu tạo file tại thư mục bài học.

### 4.2. Danh mục tài nguyên dự kiến

| Tài nguyên | Tên gợi ý | Yêu cầu chính |
| --- | --- | --- |
| Compartment | `capstone-oci` | Chứa tài nguyên riêng của dự án |
| VCN | `vcn-capstone` | CIDR không chồng lấn mạng sẽ kết nối |
| Public subnet | `subnet-edge` | Chứa public LB |
| Private subnet | `subnet-app` | Cấm public IP cho Compute |
| Private subnet | `subnet-data` | Chứa private endpoint database |
| Compute | `app-1`, `app-2` | Cùng image, cùng release, khác miền lỗi |
| Load Balancer | `lb-taskapp` | Listener 443 và backend set HTTP 8080 |
| Autonomous Database | `adb-taskapp` | Private endpoint, workload giao dịch |
| NSG | `nsg-lb`, `nsg-app`, `nsg-db` | Áp dụng đúng cho từng tài nguyên |
| Vault secret | `taskapp-db-password` | Mật khẩu của SQL runtime user |
| Object Storage bucket | `taskapp-artifacts-<suffix>` | Private, lưu JAR theo release |
| Budget, alarm, log group | Theo tiền tố `taskapp` | Có chủ sở hữu và thời hạn lab |

Gắn tag như `project=oci-taskapp`, `environment=lab`, `owner=<nhóm>` và `expires-on=<ngày>`. Phân biệt tên hiển thị với OCID; lưu OCID cần dùng trong tài liệu vận hành không chứa secret.

## 5. Thiết kế VCN, route và luật mạng

### 5.1. Subnet và route table

| Subnet | CIDR ví dụ | Route cần có | Public IP |
| --- | --- | --- | --- |
| Edge | `10.40.10.0/24` | `0.0.0.0/0 → Internet Gateway` | Public LB |
| App | `10.40.20.0/24` | `0.0.0.0/0 → NAT Gateway`; service CIDR được chọn → Service Gateway | Cấm trên VNIC ứng dụng |
| Data | `10.40.30.0/24` | Không cần default route ra Internet cho luồng app → database | Không công bố public endpoint |

Lưu lượng giữa các subnet trong cùng VCN đi theo khả năng định tuyến nội bộ mặc định khi không có thiết kế route tùy chỉnh thay đổi đường đi. Route không tự cấp quyền kết nối; vẫn cần luật mạng ở hai đầu và firewall của hệ điều hành.

Bật DNS hostnames và dùng cấu hình resolver/DHCP phù hợp của VCN. Giữ nguyên hostname database lấy từ thông tin kết nối. Không thay hostname bằng IP cố định để “sửa” lỗi DNS: cách này làm mất tính linh hoạt và có thể phá xác minh chứng thư.

NAT cho phép instance private chủ động kết nối ra ngoài; nó không cung cấp cổng truy cập inbound từ Internet. Service Gateway chỉ phục vụ các dịch vụ OCI được hỗ trợ, không phải đường ra mọi website.

### 5.2. Ma trận NSG tối thiểu

Bảng dưới mô tả kết nối TCP mới. Khi giới hạn egress, cần cấu hình cả egress của nguồn và ingress của đích. Chọn rule **stateful** cho bản lab này.

| Nguồn | Đích | Cổng đích | Mục đích |
| --- | --- | --- | --- |
| CIDR client được phép | `nsg-lb` | TCP 443 | Gọi HTTPS |
| `nsg-lb` | `nsg-app` | TCP 8080 | Request và health check |
| Private IP của Bastion endpoint `/32` | `nsg-app` | TCP 22 | Quản trị VM qua Bastion |
| `nsg-app` | `nsg-db` | TCP 1522 | Kết nối database bằng mTLS |
| `nsg-app` | Endpoint OCI cần dùng | TCP 443 | Đọc secret, artifact và gửi telemetry |
| `nsg-app` | Repository gói được phép qua NAT | TCP 443 | Cài đặt hoặc cập nhật phần mềm |

Thêm DNS, đồng bộ thời gian và kết nối agent theo yêu cầu thực tế của image và dịch vụ. Nếu cho app egress HTTPS rộng trong lab, ghi nhận đây là một giới hạn của thiết kế và có kế hoạch thu hẹp. Không cho ingress `8080`, `22` hoặc `1522` từ `0.0.0.0/0`.

Với rule stateful, gói trả lời của kết nối đã được theo dõi không cần một rule mới cho cổng ephemeral. Cần phân biệt luồng trả lời với một kết nối mới do phía database chủ động mở.

NSG hỗ trợ tham chiếu NSG nguồn/đích trong cùng VCN, thuận tiện hơn việc cố định hai IP ứng dụng. Xem [Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

**Kiểm tra Security List song song với NSG.** Các allow rule có hiệu lực từ Security List và NSG được hợp lại trong mô hình thông thường. Một Security List cho phép quá rộng có thể khiến việc thu hẹp NSG không đạt mục đích. Loại bỏ rule dư thừa theo thiết kế, đồng thời giữ các rule hệ thống cần thiết. Nếu tenancy áp dụng thêm Zero Trust Packet Routing, phải đáp ứng cả chính sách đó. Xem [Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

### 5.3. Cấu hình truy cập quản trị

Dùng OCI Bastion với client CIDR allowlist và session có thời hạn. Với Managed SSH, kiểm tra OpenSSH, Oracle Cloud Agent và Bastion plugin trên VM trước khi tạo session. Cho phép cổng 22 từ private endpoint của Bastion, không nhầm với public IP của laptop.

Bản lab thực hiện thao tác SQL quản trị từ một app VM qua session quản trị được kiểm soát. Nếu tạo tunnel trực tiếp đến database, phải giữ đúng hostname và xác minh TLS theo hướng dẫn của công cụ; không tắt kiểm tra chứng thư để xử lý khác biệt giữa `localhost` và hostname database.

Tham khảo [OCI Bastion Overview](https://docs.oracle.com/en-us/iaas/Content/Bastion/Concepts/bastionoverview.htm).

## 6. Phân quyền IAM và quản lý bí mật

### 6.1. Tách các danh tính

| Danh tính | Quyền cần có | Phạm vi giới hạn |
| --- | --- | --- |
| Người dựng hạ tầng | Tạo, sửa và xóa tài nguyên cần thiết | Compartment lab và dependency liên quan |
| Người vận hành | Xem trạng thái, log và thực hiện quy trình triển khai | Tài nguyên của dự án |
| Compute runtime | Đọc đúng secret và artifact cần dùng | Hai instance đã xác định |
| SQL schema owner | Tạo bảng và quản lý object của ứng dụng | Schema ứng dụng |
| SQL runtime user | `CREATE SESSION` và DML được cấp | Chỉ các bảng cần dùng |

OCI IAM quản lý quyền gọi API OCI. Quyền kết nối SQL và quyền trên bảng là lớp phân quyền database riêng. Cấp quyền đọc secret bằng IAM không tự cấp quyền `SELECT` trong Oracle Database.

Người vận hành có quyền root trên app VM vẫn có thể tiếp cận bí mật của tiến trình. Vì vậy quyền SSH, sudo và quyền tạo Bastion session cũng là một phần của ranh giới bảo mật.

### 6.2. Dynamic group và policy minh họa

Ví dụ dynamic group chỉ khớp hai instance:

~~~text
ANY {
  instance.id = '<APP_1_INSTANCE_OCID>',
  instance.id = '<APP_2_INSTANCE_OCID>'
}
~~~

Policy cho dynamic group `dg-taskapp` đọc một secret:

~~~text
Allow dynamic-group dg-taskapp to read secret-bundles in compartment capstone-oci where target.secret.id = '<DB_PASSWORD_SECRET_OCID>'
~~~

Thay tên compartment, dynamic group, OCID và cú pháp tên có identity domain theo tenancy của bạn. Sau khi thay instance, cập nhật matching rule; hoặc dùng chiến lược tag được quản trị chặt chẽ. Không cho workload tự sửa tag giúp nó gia nhập nhóm có đặc quyền.

Đây là phần quyền **runtime**, không phải policy đầy đủ cho người dựng toàn bộ hạ tầng. Nếu runtime tải artifact từ Object Storage hoặc gửi custom log, thêm quyền đúng bucket hoặc log group; không giải quyết bằng `manage all-resources in tenancy`.

Mẫu giới hạn quyền đọc secret theo OCID được mô tả trong [hướng dẫn policy với Vault secret](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingpolicies.htm).

### 6.3. Luồng cấp secret

1. Quản trị database tạo SQL runtime user.
2. Mật khẩu runtime user được đưa vào Vault bằng kênh quản trị phù hợp.
3. Wallet của đúng database được chuyển an toàn đến `/opt/taskapp/wallet` trên hai VM.
4. Khi service khởi động, script dùng instance principal lấy secret phiên bản `CURRENT`.
5. Mật khẩu giải mã được ghi vào file quyền `0600` trong `/run/taskapp/secrets`.
6. Spring Boot nạp file này bằng configuration tree.

Không đưa mật khẩu, wallet, private key hay nội dung secret vào Git, cloud-init, Terraform variables công khai, ảnh chụp báo cáo hoặc log CI. Việc xóa secret khỏi commit mới không xóa nó khỏi lịch sử; nếu lộ thì phải thu hồi hoặc đổi secret.

## 7. Tạo private database và schema

### 7.1. Cấp phát Autonomous Database

Trong compartment lab:

1. Chọn Autonomous Database với workload giao dịch và dung lượng nhỏ phù hợp.
2. Chọn VCN `vcn-capstone`, private subnet `subnet-data` và `nsg-db`.
3. Chọn chế độ chỉ truy cập private; không bật tùy chọn `Allow public access` bổ sung.
4. Bật yêu cầu mTLS cho phương án tham chiếu.
5. Lấy hostname private, service name và wallet từ thông tin kết nối của chính database này.
6. Xác nhận app VM phân giải hostname thành private IP mong đợi và kết nối được TCP 1522.

Oracle cho phép một số cấu hình private endpoint kèm public access bổ sung. Vì vậy chỉ nhìn thấy chữ “private endpoint” chưa đủ để nghiệm thu; cần kiểm tra cả tùy chọn public access. mTLS của Autonomous Database dùng cổng 1522. Tham khảo [cấu hình private endpoint](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/private-endpoints-autonomous.html) và [các kiểu kết nối database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-introduction.html).

### 7.2. Tách owner và runtime user

Dùng tài khoản quản trị để tạo hai user. Ví dụ SQL sau có placeholder mật khẩu, không chạy nguyên trạng:

~~~sql
-- Chạy bằng tài khoản quản trị database, qua kết nối private.
CREATE USER TASK_OWNER IDENTIFIED BY "<OWNER_PASSWORD>";
GRANT CREATE SESSION, CREATE TABLE TO TASK_OWNER;
ALTER USER TASK_OWNER QUOTA 100M ON DATA;

CREATE USER TASK_APP IDENTIFIED BY "<RUNTIME_PASSWORD>";
GRANT CREATE SESSION TO TASK_APP;
~~~

`DATA` là tablespace thường dùng của Autonomous Database; xác nhận tên và quota theo môi trường. Nhập mật khẩu qua cơ chế an toàn của công cụ quản trị, không lưu script đã điền mật khẩu vào repository.

Kết nối bằng `TASK_OWNER` để tạo bảng:

~~~sql
CREATE TABLE TASKS (
    ID          VARCHAR2(36 CHAR) PRIMARY KEY,
    TITLE       VARCHAR2(200 CHAR) NOT NULL,
    STATUS      VARCHAR2(16 CHAR) DEFAULT 'OPEN' NOT NULL,
    CREATED_AT  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT CK_TASKS_STATUS CHECK (STATUS IN ('OPEN', 'DONE'))
);

GRANT SELECT, INSERT ON TASKS TO TASK_APP;
~~~

Runtime user chưa cần `UPDATE` hay `DELETE` vì API mẫu chỉ tạo và đọc. Khi bổ sung nghiệp vụ, cấp thêm quyền tương ứng bằng thay đổi được quản lý.

Ứng dụng sẽ dùng tên đầy đủ `TASK_OWNER.TASKS`. Không dùng tài khoản quản trị để chạy ứng dụng và không bật cơ chế tự sửa schema trong mỗi lần khởi động production.

### 7.3. Wallet và JDBC URL

Giải nén wallet vào thư mục chỉ người quản trị và service account có quyền đọc. Ví dụ JDBC URL:

~~~text
jdbc:oracle:thin:@<PRIVATE_TNS_ALIAS>?TNS_ADMIN=/opt/taskapp/wallet
~~~

Thay `<PRIVATE_TNS_ALIAS>` bằng alias private thực tế trong `tnsnames.ora`, chẳng hạn một service `_tp` phù hợp với tải của API. Không tự chế hostname hoặc service name từ tên hiển thị của database.

Mẫu dùng wallet Oracle, JDBC driver và các companion JAR cần thiết; giữ xác minh danh tính server. Wallet mTLS phải được xử lý như bí mật có thể thu hồi và cần kế hoạch thay thế. Xem [JDBC Thin với wallet](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-jdbc-thin-wallet.html).

## 8. Xây dựng ứng dụng Spring Boot ba lớp

### 8.1. Hợp đồng API

| Thao tác | Request | Kết quả |
| --- | --- | --- |
| Tạo công việc | `POST /api/tasks` với `{"title":"Học OCI"}` | `201 Created`, `Location` và dữ liệu đã lưu |
| Đọc công việc | `GET /api/tasks/{uuid}` | `200 OK` nếu tồn tại |
| ID không tồn tại | `GET` với UUID hợp lệ chưa được tạo | `404 Not Found` |
| Dữ liệu không hợp lệ | Title trắng, quá dài hoặc UUID sai dạng | `400 Bad Request` |
| Readiness | `GET /actuator/health/readiness` | `200` khi app và database sẵn sàng |
| Liveness | `GET /actuator/health/liveness` | Phản ánh trạng thái sống của ứng dụng |

Response nghiệp vụ có header `X-App-Instance` để quan sát backend phục vụ. Header này chỉ phục vụ bài lab; có thể bỏ hoặc làm mờ trong hệ thống thật.

### 8.2. Cấu trúc dự án

~~~text
taskapp/
  pom.xml
  src/main/java/vn/learning/ocicapstone/
    TaskApplication.java
    Task.java
    CreateTaskRequest.java
    TaskRepository.java
    TaskService.java
    TaskController.java
  src/main/resources/
    application.yml
~~~

Các class dưới đây cùng package `vn.learning.ocicapstone`. Tên file phải khớp tên public class hoặc record.

### 8.3. Maven và dependency

Ví dụ này cố định Spring Boot 3.5.16 và Java 21 để minh họa cấu hình có thể tái lập. Khi thực hiện dự án, chọn bản vá còn được hỗ trợ theo chính sách nhóm, khóa phiên bản và lưu kết quả build. Không dùng `LATEST` hoặc version range cho release.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>vn.learning</groupId>
    <artifactId>taskapp</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>com.oracle.database.jdbc</groupId>
            <artifactId>ojdbc11-production</artifactId>
            <type>pom</type>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Artifact `ojdbc11-production` là POM kéo JDBC driver cùng các thư viện đồng hành; `type=pom` là có chủ đích. Phiên bản Oracle được quản lý bởi dependency management của Spring Boot trong ví dụ. Kiểm tra cây dependency khi nâng phiên bản để không ghép driver và thư viện wallet không tương thích.

Tham khảo [dependency do Spring Boot 3.5 quản lý](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html) và [hướng dẫn Maven của Oracle JDBC](https://www.oracle.com/database/technologies/maven-central-guide.html). Spring JDBC vẫn dùng HikariCP theo cấu hình dưới đây; có UCP trong dependency không đồng nghĩa ứng dụng đang dùng UCP.

### 8.4. Entry point và các record

`TaskApplication.java`:

~~~java
package vn.learning.ocicapstone;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(TaskApplication.class, args);
    }
}
~~~

`Task.java`:

~~~java
package vn.learning.ocicapstone;

import java.util.UUID;

public record Task(UUID id, String title, String status) {
}
~~~

`CreateTaskRequest.java`:

~~~java
package vn.learning.ocicapstone;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateTaskRequest(
        @NotBlank @Size(max = 200) String title
) {
}
~~~

### 8.5. Repository: SQL có tham số

`TaskRepository.java`:

~~~java
package vn.learning.ocicapstone;

import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class TaskRepository {
    private final JdbcTemplate jdbc;

    public TaskRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(Task task) {
        jdbc.update("""
                INSERT INTO TASK_OWNER.TASKS (ID, TITLE, STATUS)
                VALUES (?, ?, ?)
                """, task.id().toString(), task.title(), task.status());
    }

    public Optional<Task> findById(UUID id) {
        return jdbc.query("""
                SELECT ID, TITLE, STATUS
                FROM TASK_OWNER.TASKS
                WHERE ID = ?
                """,
                (rs, rowNum) -> new Task(
                        UUID.fromString(rs.getString("ID")),
                        rs.getString("TITLE"),
                        rs.getString("STATUS")),
                id.toString())
                .stream()
                .findFirst();
    }
}
~~~

Dùng bind parameter cho dữ liệu đầu vào. Không nối title hoặc ID vào chuỗi SQL. UUID được tạo ở lớp service nên không phụ thuộc cơ chế lấy generated key đặc thù database.

### 8.6. Service: transaction và nghiệp vụ

`TaskService.java`:

~~~java
package vn.learning.ocicapstone;

import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class TaskService {
    private final TaskRepository repository;

    public TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Task create(String title) {
        Task task = new Task(UUID.randomUUID(), title.strip(), "OPEN");
        repository.insert(task);
        return task;
    }

    @Transactional(readOnly = true)
    public Task get(UUID id) {
        return repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Task not found"));
    }
}
~~~

Proxy transaction hoàn tất commit trước khi lời gọi service trả về controller. Nếu commit thất bại, API không được coi là tạo thành công. Với API tạo mới này, retry POST có thể tạo bản ghi trùng về nghiệp vụ; khi mở rộng, thiết kế idempotency key và unique constraint thay vì tự động retry mọi lỗi.

### 8.7. Controller: HTTP và nhận diện instance

`TaskController.java`:

~~~java
package vn.learning.ocicapstone;

import java.net.URI;
import java.util.UUID;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {
    private final TaskService service;
    private final String instanceId;

    public TaskController(
            TaskService service,
            @Value("${app.instance-id}") String instanceId) {
        this.service = service;
        this.instanceId = instanceId;
    }

    @PostMapping
    public ResponseEntity<Task> create(
            @Valid @RequestBody CreateTaskRequest request) {
        Task task = service.create(request.title());
        return ResponseEntity
                .created(URI.create("/api/tasks/" + task.id()))
                .header("X-App-Instance", instanceId)
                .body(task);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Task> get(@PathVariable UUID id) {
        return ResponseEntity.ok()
                .header("X-App-Instance", instanceId)
                .body(service.get(id));
    }
}
~~~

Controller không chứa SQL và repository không quyết định HTTP status. Phân lớp này giúp thay đổi giao thức hoặc cách truy cập dữ liệu mà không gom mọi trách nhiệm vào một class.

### 8.8. Cấu hình ứng dụng

`src/main/resources/application.yml`:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
  shutdown: graceful
  error:
    include-message: never
    include-stacktrace: never

spring:
  application:
    name: taskapp
  config:
    import: "configtree:/run/taskapp/secrets/"
  lifecycle:
    timeout-per-shutdown-phase: 30s
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      maximum-pool-size: 5
      minimum-idle: 1
      connection-timeout: 3000
      validation-timeout: 1000
      data-source-properties:
        oracle.net.CONNECT_TIMEOUT: 3000
        oracle.jdbc.ReadTimeout: 5000
        oracle.net.ssl_server_dn_match: true
  jdbc:
    template:
      query-timeout: 3s
  sql:
    init:
      mode: never

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db

app:
  instance-id: ${APP_INSTANCE_ID}
~~~

File `/run/taskapp/secrets/spring.datasource.password` cung cấp property password qua configuration tree. Không thêm `optional:` trong bản này: thiếu thư mục secret là lỗi triển khai cần dừng.

Chỉ đặt `db` trong readiness. Liveness không phụ thuộc database để tránh tình huống database ngừng hoạt động khiến mọi app bị restart liên tục. Việc đưa database vào readiness ở đây là quyết định có chủ đích vì mọi API nghiệp vụ đều cần database. Nếu database chung bị lỗi, cả hai backend có thể bị loại; Load Balancer không chữa được lỗi của dependency dùng chung.

Các timeout trên giới hạn những giai đoạn khác nhau, không cộng thành một cam kết thời gian đáp ứng chính xác. Hai instance có thể mở tối đa khoảng `2 × 5 = 10` connection từ hai pool chính; khi rolling có thêm instance hoặc có công cụ quản trị, tổng sẽ lớn hơn. Điều chỉnh theo giới hạn database và tải đo được.

Hành vi của health group, probe và lựa chọn dependency được giải thích trong [Spring Boot Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

## 9. Build, phân phối artifact và chạy trên Compute

### 9.1. Build một lần

Trong repository ứng dụng do bạn tạo cho dự án:

~~~bash
mvn clean verify
mvn dependency:tree
sha256sum target/taskapp-1.0.0.jar
~~~

`verify` chỉ chạy các test thực sự tồn tại; dependency test không tự sinh ra test. Tối thiểu hãy bổ sung kiểm thử validation, tạo/đọc dữ liệu trên Oracle và trường hợp không tìm thấy. Không dùng kết quả với H2 làm bằng chứng duy nhất cho SQL Oracle.

Đưa JAR vào Object Storage private theo đường dẫn bất biến, ví dụ `releases/1.0.0/taskapp.jar`. Ghi commit, JDK, phiên bản dependency và SHA-256. Hai VM phải chạy artifact có cùng checksum; không build riêng trên từng VM.

### 9.2. Chuẩn bị VM

Trên cả hai VM:

1. Cài JDK 21 và OCI CLI từ nguồn phù hợp với image; xác nhận CLI chạy được dưới service account.
2. Tạo user hệ thống `taskapp`, không cho đăng nhập tương tác.
3. Tạo thư mục release, script, wallet và cấu hình.
4. Chuyển wallet qua kênh quản trị an toàn, rồi giới hạn quyền.
5. Tải cùng JAR bằng danh tính được cấp quyền đọc bucket, kiểm tra checksum và đặt vào release directory.
6. Mở firewall hệ điều hành cho cổng 8080 từ subnet LB hoặc dải nguồn LB thực tế; NSG vẫn chỉ cho `nsg-lb`.
7. Giữ SSH chỉ cho đường Bastion được phép.

Cấu trúc trên VM:

~~~text
/opt/taskapp/
  releases/1.0.0/taskapp.jar
  current -> releases/1.0.0
  bin/load-db-password.sh
  wallet/...
/etc/taskapp/taskapp.env
/etc/systemd/system/taskapp.service
/run/taskapp/secrets/spring.datasource.password
~~~

Service account đọc được JAR và wallet nhưng không được sửa script hoặc artifact. Thư mục release, symlink và script do root quản lý. Ví dụ wallet dùng owner `root:taskapp`, thư mục `0750` và file `0640`; secret runtime trong `/run` dùng `0600`. Không đưa wallet vào cùng JAR.

### 9.3. File môi trường không chứa password

`/etc/taskapp/taskapp.env` trên `app-1`:

~~~ini
DB_URL="jdbc:oracle:thin:@<PRIVATE_TNS_ALIAS>?TNS_ADMIN=/opt/taskapp/wallet"
DB_USERNAME=TASK_APP
DB_PASSWORD_SECRET_OCID=<DB_PASSWORD_SECRET_OCID>
OCI_REGION=<REGION_IDENTIFIER>
APP_INSTANCE_ID=app-1
~~~

Trên `app-2` chỉ đổi `APP_INSTANCE_ID=app-2`. Điền placeholder bằng dữ liệu thực tế trước khi chạy. Đây là cú pháp `EnvironmentFile` của systemd, không phải file YAML hay một shell script để `source`.

### 9.4. Script nạp password từ Vault

`/opt/taskapp/bin/load-db-password.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${DB_PASSWORD_SECRET_OCID:?Missing DB_PASSWORD_SECRET_OCID}"
: "${OCI_REGION:?Missing OCI_REGION}"

secret_dir=/run/taskapp/secrets
mkdir -p "$secret_dir"

temp_file=$(mktemp "$secret_dir/.db-password.XXXXXX")
trap 'rm -f "$temp_file"' EXIT

oci secrets secret-bundle get \
  --secret-id "$DB_PASSWORD_SECRET_OCID" \
  --stage CURRENT \
  --region "$OCI_REGION" \
  --auth instance_principal \
  --query 'data."secret-bundle-content".content' \
  --raw-output |
  base64 --decode > "$temp_file"

test -s "$temp_file"
chmod 600 "$temp_file"
mv -f "$temp_file" "$secret_dir/spring.datasource.password"
~~~

Không bật `set -x`. Giá trị trong secret phải là đúng password runtime, không tự thêm newline khi nhập secret. Script dừng nếu truy xuất hoặc giải mã thất bại; ứng dụng không khởi động bằng một giá trị mặc định.

Lệnh truy xuất phụ thuộc IAM và đường HTTPS đến API secret của region. Nếu bị từ chối, xử lý policy hoặc network; không tạo API key quản trị rồi chép lên VM để vượt qua lỗi.

### 9.5. systemd unit

`/etc/systemd/system/taskapp.service`:

~~~ini
[Unit]
Description=OCI Task API
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=taskapp
Group=taskapp
WorkingDirectory=/opt/taskapp
EnvironmentFile=/etc/taskapp/taskapp.env
RuntimeDirectory=taskapp
RuntimeDirectoryMode=0700
ExecStartPre=/bin/bash /opt/taskapp/bin/load-db-password.sh
ExecStart=/usr/bin/java -XX:MaxRAMPercentage=60 -jar /opt/taskapp/current/taskapp.jar
Restart=on-failure
RestartSec=5
TimeoutStopSec=45
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/run/taskapp
UMask=0077

[Install]
WantedBy=multi-user.target
~~~

Cài OCI CLI ở đường dẫn hệ thống mà unit tìm được, hoặc dùng đường dẫn tuyệt đối trong script. Các cờ bảo vệ giả định CLI, JDK, wallet và artifact nằm ngoài home directory; cấu hình lại nếu image của bạn có bố trí khác.

Kích hoạt và kiểm tra:

~~~bash
sudo systemctl daemon-reload
sudo systemctl enable --now taskapp
sudo systemctl status taskapp --no-pager
sudo journalctl -u taskapp -n 100 --no-pager
curl --fail http://127.0.0.1:8080/actuator/health/liveness
curl --fail http://127.0.0.1:8080/actuator/health/readiness
~~~

Readiness phải lên `UP` trước khi thêm backend vào luồng phục vụ. Nếu JVM không khởi động, xem lỗi cấu hình và dependency trước khi kiểm tra Load Balancer.

## 10. Cấu hình Load Balancer và HTTPS

### 10.1. Backend set

Tạo backend set `bs-taskapp`:

| Thuộc tính | Giá trị của lab |
| --- | --- |
| Policy | Round Robin |
| Backend 1 | Private IP thực tế của `app-1`, port 8080 |
| Backend 2 | Private IP thực tế của `app-2`, port 8080 |
| Health check protocol | HTTP |
| Health check path | `/actuator/health/readiness` |
| Expected status | 200 |
| Interval | 10.000 ms |
| Timeout | 3.000 ms |
| Retries | 3 |
| Backend SSL | Tắt trong bản HTTP nội bộ của lab |
| Session persistence | Không bật cho API stateless này |

Không dùng health check TCP làm bằng chứng rằng database sẵn sàng. TCP chỉ chứng minh có thể tạo kết nối đến cổng; HTTP readiness mới kiểm tra trạng thái mà ứng dụng công bố.

Khi backend trả kết quả không phù hợp hoặc hết timeout theo chính sách, Load Balancer loại nó khỏi vòng phân phối rồi đưa lại khi phục hồi. Khoảng thời gian quan sát thực tế còn phụ thuộc chu kỳ kiểm tra và diễn biến lỗi; không cam kết chính xác ba lần interval. Tham khảo [health check của OCI Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/load_balancer_health_management.htm).

### 10.2. Listener và chứng thư

1. Tạo listener HTTPS cổng 443 gắn với chứng thư hợp lệ và backend set trên.
2. Cấu hình chuỗi chứng thư đúng; giữ private key trong cơ chế quản lý chứng thư được phép.
3. Tạo bản ghi DNS trỏ đến địa chỉ frontend của LB.
4. Chỉ cho ingress từ CIDR client lab đã chọn.
5. Kiểm tra bằng hostname khớp chứng thư; không nghiệm thu bằng `curl -k`.
6. Nếu bổ sung listener 80 để redirect sang HTTPS, khai báo rõ rule mạng và kiểm thử redirect tương ứng.

Health check đi trực tiếp từ LB đến backend; chứng thư listener phía client không thay cho mã hóa hoặc chứng thư phía backend. Khi bật backend TLS, đồng bộ cổng, SSL settings và health check. Tham khảo [tạo Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer_topic-Creating_Load_Balancers.htm).

Chỉ expose health với thông tin tổng quát theo cấu hình mẫu. Không expose `env`, `configprops`, `heapdump` hoặc endpoint quản trị có thông tin nhạy cảm qua LB.

## 11. Tự động hóa hạ tầng và triển khai

### 11.1. Phạm vi IaC

Quản lý ít nhất VCN, subnet, route table, NSG, Compute và Load Balancer bằng Terraform hoặc OCI Resource Manager. Nếu database, Vault hoặc chứng thư được quản trị riêng, lưu OCID tham chiếu và các bước cấp phát tương ứng để người khác tái lập được.

Các đầu vào nên gồm compartment OCID, region, CIDR, image OCID, shape, cấu hình CPU/RAM, public SSH key, CIDR client và artifact release. Không đặt private SSH key hoặc password ứng dụng trong `tfvars`.

Ví dụ sau chỉ là **trích đoạn** quản lý backend set của một LB và hai instance đã có, không phải bộ Terraform dựng toàn bộ kiến trúc:

~~~hcl
variable "lb_id" {
  type = string
}

variable "app_private_ips" {
  type = map(string)
}

resource "oci_load_balancer_backend_set" "taskapp" {
  load_balancer_id = var.lb_id
  name             = "bs-taskapp"
  policy           = "ROUND_ROBIN"

  health_checker {
    protocol           = "HTTP"
    port               = 8080
    url_path           = "/actuator/health/readiness"
    return_code        = 200
    interval_ms        = 10000
    timeout_in_millis  = 3000
    retries            = 3
  }
}

resource "oci_load_balancer_backend" "taskapp" {
  for_each         = var.app_private_ips
  load_balancer_id = var.lb_id
  backendset_name  = oci_load_balancer_backend_set.taskapp.name
  ip_address       = each.value
  port             = 8080
  weight           = 1
}
~~~

Ví dụ giá trị của `app_private_ips` là map `app-1` và `app-2` đến hai private IP thực tế. Khóa phiên bản provider và commit lockfile trong repository dự án. Các thuộc tính backend set được mô tả trong [OCI Terraform provider](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/load_balancer_backend_set.html).

Trước khi apply:

~~~bash
terraform fmt -check
terraform validate
terraform plan -out=lab.tfplan
terraform apply lab.tfplan
~~~

`init` cần chạy trước lần đầu để cài provider và khởi tạo backend state. Bảo vệ cả state và saved plan: đánh dấu `sensitive` chỉ che một số đầu ra, không bảo đảm dữ liệu đã bị loại khỏi state. Đặc biệt lưu ý mật khẩu quản trị database nếu tài nguyên cấp phát ghi nó vào state.

### 11.2. Triển khai từng backend

Quy trình cập nhật từ release `1.0.0` lên `1.0.1`:

1. Build và kiểm thử một lần; lưu JAR mới, commit và checksum.
2. Chọn `app-1`, bật trạng thái drain trên backend và chờ request đang chạy hoàn tất.
3. Chuyển symlink `current` đến release mới bằng thao tác được kiểm soát.
4. Restart service; kiểm tra liveness, readiness và một lần đọc/ghi nghiệp vụ trực tiếp trên VM.
5. Tắt drain, chờ backend healthy rồi kiểm tra qua LB.
6. Lặp lại với `app-2`.
7. Xác nhận hai backend chạy cùng release và checksum.

Nếu release mới thất bại, giữ backend đó ngoài luồng phục vụ, chuyển về artifact cũ và kiểm tra trước khi đưa lại. Migration schema phải tương thích với cả hai phiên bản trong thời gian rolling. Rollback JAR không tự đảo ngược một migration phá hủy dữ liệu.

Không dừng cả hai instance cùng lúc để triển khai thường lệ.

## 12. Kiểm thử nghiệm thu từ ngoài vào trong

### 12.1. Tạo và đọc dữ liệu qua HTTPS

Trên máy client có CIDR được cho phép:

~~~bash
BASE_URL='https://api.example.com'

curl --fail-with-body --silent --show-error \
  -D /tmp/task-create.headers \
  -o /tmp/task-create.json \
  -H 'Content-Type: application/json' \
  -d '{"title":"Hoàn thành capstone OCI"}' \
  "$BASE_URL/api/tasks"

cat /tmp/task-create.headers
cat /tmp/task-create.json

TASK_ID=$(jq -er '.id' /tmp/task-create.json)

curl --fail-with-body --silent --show-error -i \
  "$BASE_URL/api/tasks/$TASK_ID"
~~~

Thay hostname bằng DNS của bạn. Chấp nhận khi POST trả `201`, có `Location`, UUID hợp lệ, title đúng và status `OPEN`; GET trả `200` với cùng dữ liệu. `curl --fail-with-body` phù hợp với curl hỗ trợ tùy chọn này; nếu công cụ cũ hơn, nâng cấp hoặc kiểm tra HTTP status riêng.

Kiểm tra thêm:

~~~bash
curl --silent --show-error -i \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}' \
  "$BASE_URL/api/tasks"

curl --silent --show-error -i \
  "$BASE_URL/api/tasks/not-a-uuid"

curl --silent --show-error -i \
  "$BASE_URL/api/tasks/00000000-0000-0000-0000-000000000000"
~~~

Hai request đầu phải bị từ chối với `400`. Request cuối trả `404` nếu bản ghi đó không tồn tại. Không cần response body lỗi khớp từng ký tự với một phiên bản Spring Boot cụ thể.

### 12.2. Chứng minh có hai backend cùng phục vụ

~~~bash
for i in $(seq 1 30); do
  curl --fail --silent --show-error \
    --dump-header - \
    --output /dev/null \
    "$BASE_URL/api/tasks/$TASK_ID" |
    tr -d '\r' |
    awk 'tolower($1) == "x-app-instance:" { print $2 }'
done
~~~

Kết hợp header, trạng thái backend và log trên hai máy để chứng minh cả `app-1` và `app-2` xử lý request. Không yêu cầu số lượng bằng nhau tuyệt đối hoặc luân phiên đúng từng request. Kiểm tra rằng mỗi iteration thực sự trả `200`; một lần curl thất bại không được tính là mẫu thành công.

Nếu chỉ thấy một backend, kiểm tra health, drain/offline, cookie persistence và cấu hình backend set trước khi tăng tải.

### 12.3. Chứng minh dữ liệu dùng chung và bền vững

1. Tạo một công việc qua LB và lưu UUID.
2. Qua session quản trị, gọi GET trực tiếp trên localhost của `app-1` và `app-2` với cùng UUID.
3. Restart `app-1`, chờ readiness phục hồi, rồi GET lại.
4. Đưa `app-1` ra khỏi luồng phục vụ và GET qua LB.
5. Truy vấn database bằng tài khoản được cấp quyền để đối chiếu bản ghi.

Dữ liệu phải tồn tại ở mọi bước. Header giúp xác định backend; database dùng chung giải thích vì sao ứng dụng không cần đồng bộ file hoặc bộ nhớ giữa hai VM.

### 12.4. Chứng minh database private

Thu thập đồng thời bằng chứng cấu hình và thử nghiệm:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Database network configuration | Private endpoint, không bật public access bổ sung |
| App VNIC | Không có public IP |
| DNS từ app VM | Hostname database trỏ đến private endpoint đúng |
| Kết nối mới từ app VM | TCP và truy vấn SQL thành công |
| Kết nối trực tiếp từ Internet, không VPN/tunnel | Không thiết lập được phiên đến private endpoint |
| SQL runtime user tạo bảng | Bị từ chối do thiếu quyền DDL |
| Compute ngoài dynamic group đọc secret | Bị từ chối bởi IAM |

Một phép thử từ Internet timeout không đủ để chứng minh private database: lỗi có thể do DNS hoặc một nguyên nhân khác. Phải kết hợp network configuration, route, NSG/Security List và kiểm tra kết nối từ vị trí được phép.

Không đưa password vào tham số dòng lệnh hoặc ảnh chụp SQL client để làm bằng chứng.

## 13. Thử lỗi và đánh giá tính sẵn sàng

### 13.1. Dừng một app instance

Trước khi thử, xác nhận cả hai backend healthy và đã lưu ít nhất một công việc. Chạy một chuỗi GET có ghi thời gian, HTTP status và latency. Trên `app-1`:

~~~bash
sudo systemctl stop taskapp
~~~

Quan sát:

- Trong thời gian LB phát hiện lỗi, một số request có thể thất bại.
- Sau khi backend lỗi bị loại, request mới được phục vụ bởi `app-2`.
- Dữ liệu đã tạo vẫn đọc được.
- Alarm và log đủ giúp xác định thành phần lỗi.

Khôi phục:

~~~bash
sudo systemctl start taskapp
~~~

Đợi readiness và trạng thái backend phục hồi, sau đó xác nhận cả hai instance lại nhận lưu lượng. Ghi thời điểm gây lỗi, lần lỗi cuối, thời điểm phục vụ ổn định và thời điểm hồi phục hoàn toàn.

Đặt mục tiêu lab, chẳng hạn tiếp tục phục vụ ổn định trong vòng 90 giây khi mất một backend. Đây là mục tiêu cần đo, không phải SLA của OCI. Nếu không đạt, phân tích timeout, health check và dung lượng backend còn lại.

### 13.2. Mất đường kết nối database

Trong một cửa sổ thử nghiệm, chặn có kiểm soát kết nối mới từ một backend đến database hoặc dùng một cấu hình kết nối sai trên backend đã drain. Ghi lại cấu hình trước khi thay đổi để khôi phục chính xác.

Đối với thử nghiệm bằng NSG, phải kiểm tra các allow rule khác và connection đã tồn tại trong pool. Một connection cũ còn dùng được không chứng minh kết nối mới đang được cho phép. Dùng phép thử tạo kết nối mới trong phạm vi đã chuẩn bị.

Kỳ vọng:

- Readiness của backend bị ảnh hưởng chuyển sang lỗi hoặc không thể lên healthy.
- Liveness không tự thất bại chỉ vì database tạm thời không truy cập được.
- Thời gian chờ có giới hạn; không treo vô thời hạn.
- Khôi phục cấu hình giúp backend sẵn sàng trở lại.

Nếu cả hai backend mất database chung, dịch vụ nghiệp vụ không còn sẵn sàng dù hai JVM vẫn sống. Để thiết kế chịu lỗi database hoặc lỗi region, cần phương án HA/DR riêng, mục tiêu phục hồi và diễn tập phù hợp.

### 13.3. Giới hạn của kiến trúc

Hai instance trong một fault domain không đáp ứng cùng mức cô lập lỗi như hai fault domain. Hai fault domain trong một availability domain không tương đương hai availability domain. Hai app instance cũng không biến database thành một hệ thống DR đa region.

Với các giao dịch đã commit trước khi chỉ restart app, dữ liệu vẫn ở database. Điều đó không chứng minh RPO bằng 0 cho mất database hoặc mất region. RPO và RTO phải gắn với một kịch bản lỗi cụ thể.

Backup database không thay thế bản phát hành ứng dụng hay mã IaC. Kiểm tra chính sách backup và khả năng restore; nếu diễn tập restore sang database riêng, tính cả chi phí tạm thời, private endpoint, quyền truy cập và việc cập nhật cấu hình kết nối.

## 14. Giám sát và xử lý sự cố

### 14.1. Bộ tín hiệu tối thiểu

| Lớp | Tín hiệu cần quan sát | Hành động khi bất thường |
| --- | --- | --- |
| LB | Backend healthy, lỗi 5xx, thời gian xử lý | Kiểm tra backend và health check |
| Compute | CPU, bộ nhớ qua agent nếu đã cấu hình, dung lượng đĩa | Kiểm tra JVM, log và tải |
| Ứng dụng | Tỷ lệ lỗi, latency, pool connection, restart | Xác định lỗi tài nguyên hay dependency |
| Database | Session, tải, lỗi kết nối và dung lượng | Đối chiếu pool, SQL và cấu hình DB |
| Bảo mật | Thao tác IAM, đọc secret, Bastion session | Đối chiếu danh tính và thay đổi được phép |
| Chi phí | Chi phí theo compartment/tag và tài nguyên tồn dư | Thu hẹp, dừng hoặc thu hồi theo kế hoạch |

Bật access/error log cho LB theo nhu cầu, custom log cho ứng dụng và metric cần thiết. `journalctl` không tự xuất hiện trong OCI Logging: phải cấu hình agent hoặc một cơ chế chuyển log, kèm IAM ghi log phù hợp.

Mẫu chỉ expose health; nếu cần xuất Micrometer metrics, bổ sung dependency, endpoint và kênh thu thập có kiểm soát. Không mở toàn bộ Actuator chỉ để có dashboard.

Tạo alarm khi số backend healthy giảm dưới hai trong một khoảng quan sát phù hợp; khi giảm về không thì mức ưu tiên cao hơn. Thêm alarm cho lỗi và độ trễ theo mục tiêu của lab. Lấy tên metric, namespace và dimension thực tế từ Metrics Explorer của đúng tài nguyên thay vì suy tên.

Log nên có timestamp thống nhất, release, instance và request ID. Che dữ liệu nhạy cảm; không log header Authorization, nội dung secret, password hoặc toàn bộ JDBC URL nếu URL có chứa credential.

### 14.2. Khoanh vùng sự cố theo đường đi

| Hiện tượng | Kiểm tra trước | Nguyên nhân thường gặp |
| --- | --- | --- |
| Không bắt tay được HTTPS | DNS, chứng thư, listener 443, NSG LB | Sai hostname, thiếu intermediate CA, CIDR client đổi |
| LB báo không có backend khỏe | Health path, cổng và service trên VM | App chưa chạy, readiness lỗi, firewall chặn |
| TCP 8080 được nhưng readiness lỗi | Log ứng dụng và kết nối DB | Sai secret, wallet, alias hoặc quyền SQL |
| Không phân giải được DB hostname | Resolver/DHCP và private DNS | Dùng sai hostname hoặc cấu hình DNS |
| Lỗi chứng thư khi kết nối DB | Wallet, hostname và driver | Wallet sai DB/hết hạn, thư viện không phù hợp |
| SQL truy cập bảng bị từ chối | User và grant trên schema | Thiếu `SELECT`/`INSERT` hoặc tên schema sai |
| Oracle báo không phân giải alias | `TNS_ADMIN` và `tnsnames.ora` | Alias sai hoặc service account không đọc được file |
| Chỉ một VM đọc được secret | Dynamic group và principal | Matching rule thiếu instance hoặc policy chưa có hiệu lực |
| Sau khi thêm replica DB quá tải | Tổng connection pool và SQL | Mỗi replica nhân số connection, truy vấn chậm |
| Đã đóng NSG nhưng vẫn truy cập được | Security List, NSG khác, kết nối cũ | Allow rule khác còn hiệu lực |

Bắt đầu bằng kiểm tra tại VM: liveness → readiness → SQL đơn giản → gọi qua LB → HTTPS từ client. Không đổi đồng thời nhiều rule và timeout; mỗi thay đổi cần có giả thuyết và phép đo xác nhận.

OCI cũng cung cấp hướng dẫn [xử lý lỗi health của Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/troubleshooting_health.htm).

## 15. Kiểm soát chi phí và thu hồi tài nguyên

### 15.1. Dự toán trước khi tạo

Lập bảng theo giá hiện tại của region, shape, loại database và mô hình thanh toán đã chọn:

| Nhóm | Đơn vị cần kiểm tra | Cách kiểm soát |
| --- | --- | --- |
| Compute | CPU, RAM và giờ chạy | Bắt đầu nhỏ; đo khả năng một backend gánh tải |
| Boot/Block Volume | Dung lượng, mức hiệu năng, backup | Giới hạn dung lượng và retention |
| Load Balancer | Giờ hoạt động, cấu hình băng thông | Chọn min/max phù hợp cho lab |
| Autonomous Database | Compute, storage và tùy chọn mở rộng | Chọn cấu hình cần thiết, kiểm tra autoscaling |
| Object Storage | Dung lượng, request và retention | Chỉ giữ release/bằng chứng cần dùng |
| Logging/Monitoring | Ingest, lưu trữ và retention theo dịch vụ | Giới hạn log và thời gian giữ |
| Mạng và dịch vụ phụ trợ | Truyền dữ liệu và cách tính phí của dịch vụ | Kiểm tra biểu phí áp dụng thực tế |

Ước tính chi phí toàn lab bằng tổng chi phí từng tài nguyên theo thời gian dự kiến cộng phần lưu trữ, log và truyền dữ liệu. Không dùng một con số cố định không ghi ngày, region và giả định.

Tạo budget cho compartment hoặc tag dự án, với ngưỡng cảnh báo phù hợp như 50%, 80% và 100%. Budget là giới hạn mềm và cơ chế cảnh báo; không mặc định chặn tài nguyên hoặc ngắt chi tiêu. Xem [OCI Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm).

### 15.2. Thu hồi theo dependency

Sau khi lưu bằng chứng và dữ liệu cần giữ:

1. Ngừng tạo request thử nghiệm và chốt chi phí quan sát.
2. Gỡ listener/LB và backend theo cấu hình IaC.
3. Thu hồi Compute cùng volume, backup hoặc IP không còn cần.
4. Thu hồi database và các bản clone/backup theo chính sách giữ dữ liệu đã chọn.
5. Dọn artifact và log vượt thời hạn; xử lý secret và key theo vòng đời của dịch vụ.
6. Gỡ các thành phần mạng khi tài nguyên phụ thuộc đã được giải phóng.
7. Kiểm tra lại tài nguyên trong compartment và Cost Analysis sau độ trễ cập nhật.

Nếu dùng `terraform destroy`, xem plan và xác nhận scope là lab trước khi chạy. Tài nguyên được tạo ngoài state, backup giữ lại và object có retention có thể cần xử lý riêng. Dừng Compute không đồng nghĩa mọi thành phần khác đã ngừng tính phí.

## 16. Hồ sơ bàn giao và thang đánh giá

### 16.1. Bằng chứng cần nộp

Hồ sơ của dự án gồm:

- Sơ đồ kiến trúc, region, subnet, route table và ma trận NSG.
- Giải thích placement của hai app instance và giới hạn HA còn lại.
- Mã ứng dụng, dependency đã khóa, commit và checksum artifact.
- IaC hoặc cấu hình Resource Manager, cùng hướng dẫn cấp phát các phần quản trị riêng.
- Policy IAM, matching rule và grant SQL đã loại bỏ dữ liệu nhạy cảm.
- Kết quả API hợp lệ/không hợp lệ, dữ liệu dùng chung và thử lỗi backend.
- Bằng chứng private database kết hợp cấu hình và thử kết nối.
- Dashboard/ảnh alarm, log minh họa và runbook xử lý sự cố.
- Dự toán, chi phí quan sát và danh sách tài nguyên đã thu hồi hoặc còn giữ.

Ghi rõ phép thử nào đã chạy, môi trường, thời điểm, kết quả và giới hạn. Các response, lệnh và mục tiêu trong bài là mẫu hướng dẫn; chúng không phải bằng chứng rằng hệ thống của bạn đã được triển khai thành công.

### 16.2. Rubric 100 điểm

| Hạng mục | Điểm | Điều kiện đạt điểm tốt |
| --- | ---: | --- |
| Mạng và private database | 20 | Route đúng, app/DB private, có thử nghiệm cả cho phép và từ chối |
| IAM và bí mật | 15 | Runtime ít quyền, dùng instance principal, không lộ secret |
| Ứng dụng và dữ liệu | 20 | Ba lớp rõ, validate, bind parameter, transaction và dữ liệu bền vững |
| Load Balancer và tính sẵn sàng | 15 | HTTPS hợp lệ, hai backend phục vụ, có đo thử lỗi và phục hồi |
| Giám sát và vận hành | 10 | Có tín hiệu, alarm, log và runbook sử dụng được |
| Tự động hóa và release | 10 | Tái lập được, artifact bất biến, rolling và rollback rõ |
| Chi phí và bàn giao | 10 | Có giả định chi phí, budget và thu hồi tài nguyên |
| **Tổng** | **100** | |

Các điều kiện bắt buộc để công nhận hoàn thành dự án:

- Database không có public access ngoài thiết kế đã yêu cầu.
- Hai app instance đều không có public IP và đều phục vụ được qua LB.
- Dữ liệu đã tạo vẫn đọc được khi restart hoặc loại một app instance.
- Kết nối HTTPS được xác minh bằng chứng thư hợp lệ.
- Runtime không dùng tài khoản quản trị database.
- Không đưa password, wallet hoặc private key vào repository hay hồ sơ bàn giao.

Một bài đạt nhiều điểm tính năng nhưng vi phạm các điều kiện này cần khắc phục trước khi nghiệm thu.

## 17. Dấu hiệu bạn đã làm chủ dự án

Bạn có thể giải thích từ một request HTTPS đến câu SQL cụ thể: danh tính nào được dùng, route nào chuyển tiếp, luật nào cho phép kết nối, dữ liệu được commit ở đâu và tín hiệu nào cho thấy lỗi xảy ra. Bạn cũng có thể thay một app instance bằng bản triển khai mới, đưa nó trở lại backend set, đọc được dữ liệu cũ và chứng minh chi phí của môi trường đang được theo dõi.

Giá trị của capstone nằm ở khả năng dựng lại và kiểm chứng những hành vi đó bằng cấu hình, mã nguồn và phép đo của chính bạn.
