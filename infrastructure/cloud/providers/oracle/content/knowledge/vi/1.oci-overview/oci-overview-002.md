# Phân biệt OCI, Oracle Cloud Applications và Oracle Database

## Mục tiêu bài học

Sau bài học, bạn có thể xác định một yêu cầu thuộc nền tảng hạ tầng OCI, ứng dụng nghiệp vụ Oracle Cloud Applications hay hệ quản trị Oracle Database. Bạn cũng có thể giải thích cách ba nhóm này phối hợp, phân biệt các lớp quyền truy cập và nhận diện trách nhiệm vận hành trước khi triển khai.

Bài học nằm trong phần **Tổng quan Oracle Cloud Infrastructure** của module CLOUD_PROVIDERS_ORACLE. Trọng tâm là đọc đúng kiến trúc và chọn đúng phạm vi công việc trước khi học tenancy, compartment, IAM, VCN, Compute, lưu trữ và các dịch vụ cơ sở dữ liệu.

## 1. Ba khái niệm trả lời ba câu hỏi khác nhau

Một doanh nghiệp có thể dùng cả ba nhóm sản phẩm trong cùng hệ thống:

- **OCI — Oracle Cloud Infrastructure:** dùng tài nguyên và dịch vụ nền tảng nào để triển khai, kết nối và vận hành hệ thống?
- **Oracle Cloud Applications:** dùng ứng dụng nghiệp vụ nào để thực hiện công việc như kế toán, nhân sự hoặc quản lý chuỗi cung ứng?
- **Oracle Database:** dùng hệ quản trị nào để tổ chức, truy vấn và bảo vệ dữ liệu của ứng dụng?

Ví dụ, doanh nghiệp có một cổng nhà cung cấp viết bằng Java:

1. Cổng chạy trên OCI Compute và sử dụng mạng VCN.
2. Dữ liệu riêng của cổng được lưu trong Oracle Database.
3. Cổng trao đổi thông tin nghiệp vụ với Oracle Fusion Cloud ERP qua giao diện tích hợp được hỗ trợ.

Ba lựa chọn trên cùng xuất hiện nhưng có vai trò khác nhau. Thay đổi nơi chạy cổng Java không tự thay đổi phần mềm ERP; thay đổi hệ quản trị dữ liệu của cổng cũng không tự chuyển đổi ứng dụng nghiệp vụ của doanh nghiệp.

| Tiêu chí | OCI | Oracle Cloud Applications | Oracle Database |
| --- | --- | --- | --- |
| Bản chất | Nền tảng hạ tầng và dịch vụ đám mây | Các ứng dụng nghiệp vụ được cung cấp dưới dạng dịch vụ | Hệ quản trị cơ sở dữ liệu và các lựa chọn triển khai liên quan |
| Đối tượng sử dụng chính | Kỹ sư cloud, nền tảng, phát triển và vận hành | Người dùng nghiệp vụ, chuyên viên triển khai và quản trị ứng dụng | Lập trình viên, DBA, kỹ sư dữ liệu |
| Đối tượng thường thao tác | Compartment, mạng, VM, bucket, tài nguyên dịch vụ | Chứng từ, nhân viên, quy trình, vai trò nghiệp vụ | Bảng, chỉ mục, giao dịch, user và quyền dữ liệu |
| Công việc tiêu biểu | Tạo môi trường chạy API | Cấu hình quy trình phê duyệt mua hàng | Thiết kế bảng và truy vấn đơn hàng |
| Phạm vi kiến thức | Hạ tầng và nền tảng | Nghiệp vụ và cấu hình ứng dụng | Quản lý và truy cập dữ liệu |

Trong bài này, các ví dụ về Oracle Cloud Applications chủ yếu dùng **Oracle Fusion Cloud Applications**, một bộ ứng dụng SaaS tiêu biểu. Khi gặp tên sản phẩm cụ thể, luôn kiểm tra đúng sản phẩm và hình thức cung cấp; cụm “Oracle Applications” có phạm vi rộng hơn một bộ SaaS duy nhất.

## 2. OCI: nền tảng để xây dựng và vận hành hệ thống

### 2.1. Giá trị mà OCI cung cấp

OCI cung cấp các thành phần như tính toán, mạng, lưu trữ và dịch vụ nền tảng. Bạn kết hợp chúng để chạy ứng dụng tự phát triển, phần mềm doanh nghiệp hoặc workload dữ liệu. Danh mục tổng quan được trình bày tại [Oracle Cloud Infrastructure](https://www.oracle.com/cloud/).

Với cổng nhà cung cấp Java, các quyết định ở lớp OCI gồm:

| Quyết định | Thành phần liên quan |
| --- | --- |
| Đặt tài nguyên ở phạm vi quản trị nào? | Tenancy, compartment |
| Ai được tạo, sửa hoặc xóa tài nguyên? | IAM |
| Ứng dụng nhận kết nối theo đường nào? | VCN, subnet, định tuyến và quy tắc mạng |
| Mã Java chạy ở đâu? | Compute, container hoặc mô hình thực thi phù hợp |
| Tệp đính kèm được lưu ở đâu? | Object Storage hoặc dịch vụ lưu trữ phù hợp |
| Theo dõi và tái tạo hạ tầng bằng cách nào? | Dịch vụ giám sát, API và công cụ tự động hóa |

Việc tạo một VM mới chỉ tạo môi trường tính toán. Để có cổng nhà cung cấp, đội dự án còn phải triển khai mã, cấu hình xác thực, kết nối dữ liệu và xây dựng quy trình nghiệp vụ.

### 2.2. OCI bao gồm nhiều mức dịch vụ

Không nên xem mọi tài nguyên OCI là máy ảo tự quản lý. Nền tảng còn có các dịch vụ được quản lý, chẳng hạn dịch vụ cơ sở dữ liệu. Mức tự động hóa và quyền kiểm soát tùy từng dịch vụ.

Ví dụ:

~~~text
Lựa chọn A
OCI Compute
└── đội của bạn cài và vận hành phần mềm cơ sở dữ liệu

Lựa chọn B
Dịch vụ cơ sở dữ liệu trên OCI
└── dùng các khả năng quản lý của dịch vụ đã chọn
~~~

Hai lựa chọn đều sử dụng OCI, nhưng trách nhiệm vá lỗi, sao lưu và quản lý phần mềm có thể khác nhau. Khi lập kế hoạch, cần ghi tên dịch vụ cụ thể thay vì chỉ viết “database trên cloud”.

## 3. Oracle Cloud Applications: ứng dụng phục vụ nghiệp vụ

### 3.1. Tập trung vào quy trình của tổ chức

Oracle Fusion Cloud Applications cung cấp chức năng cho các lĩnh vực như ERP, HCM, chuỗi cung ứng và trải nghiệm khách hàng. Người dùng làm việc với những đối tượng nghiệp vụ và quy trình đã được sản phẩm cung cấp. Xem [Oracle Fusion Cloud Applications](https://www.oracle.com/applications/).

Ví dụ:

| Nhu cầu nghiệp vụ | Nhóm ứng dụng thường được xem xét |
| --- | --- |
| Quản lý hoạt động tài chính và quy trình liên quan | ERP |
| Quản lý nhân sự và vòng đời nhân viên | HCM |
| Quản lý các hoạt động chuỗi cung ứng | SCM |
| Hỗ trợ bán hàng, dịch vụ và tương tác khách hàng | CX |

Đây là cách nhận diện lĩnh vực, không khẳng định mọi chức năng đều có sẵn trong mọi gói. Phạm vi thực tế phụ thuộc module và cấu hình của sản phẩm.

Trong mô hình SaaS, nhà cung cấp vận hành phần mềm dịch vụ; khách hàng vẫn cần triển khai nghiệp vụ, phân quyền, chuẩn bị dữ liệu và kiểm tra tích hợp. Oracle trình bày mô hình này tại [SaaS Comparison — Oracle Cloud Applications](https://www.oracle.com/applications/what-is-saas/comparison-saas/).

### 3.2. Những việc khách hàng thường cấu hình

Một dự án SaaS có thể cần xác định cơ cấu tổ chức, nhóm người dùng, quy trình phê duyệt và cách chuyển dữ liệu từ hệ thống cũ. Công việc triển khai tập trung vào cách doanh nghiệp sử dụng sản phẩm.

Ví dụ giả định: bộ phận mua hàng muốn đơn mua vượt ngưỡng nội bộ phải qua một cấp phê duyệt bổ sung. Đây trước hết là yêu cầu về quy trình và phân quyền nghiệp vụ trong ứng dụng. Việc tăng CPU cho một VM không tự tạo ra quy trình đó.

Ngược lại, nếu doanh nghiệp xây thêm một cổng riêng cho nhà cung cấp, cổng có thể cần hạ tầng chạy mã, lưu trữ và giám sát. Phần mở rộng này tạo ra công việc ở lớp OCI, dù ứng dụng SaaS vẫn do nhà cung cấp vận hành.

### 3.3. Ứng dụng SaaS chạy trên hạ tầng không đồng nghĩa khách hàng quản trị hạ tầng ấy

Oracle mô tả Fusion Cloud Applications được xây dựng trên hạ tầng đám mây của Oracle. Tuy nhiên, quyền sử dụng ứng dụng SaaS và quyền quản trị tài nguyên hạ tầng là các phạm vi khác nhau.

Người quản trị nghiệp vụ không vì thế tự có quyền SSH vào máy chủ của dịch vụ SaaS. Tương tự, việc một tổ chức có OCI tenancy không có nghĩa mọi tài nguyên bên trong dịch vụ SaaS trở thành VM hoặc database do tổ chức trực tiếp quản lý.

Nếu một giao diện OCI hỗ trợ quản lý môi trường Fusion, cần phân biệt thao tác quản lý môi trường được sản phẩm cho phép với quyền truy cập hệ điều hành hoặc dữ liệu bên dưới. Mỗi thao tác vẫn chịu phạm vi dịch vụ và phân quyền tương ứng.

## 4. Oracle Database: hệ quản trị dữ liệu, có nhiều cách triển khai

### 4.1. Vai trò của hệ quản trị cơ sở dữ liệu

Oracle Database quản lý dữ liệu, cung cấp truy vấn, giao dịch và kiểm soát truy cập. Ứng dụng có thể sử dụng SQL và các giao diện phù hợp để làm việc với dữ liệu. Khái niệm nền tảng được giải thích tại [Introduction to Oracle Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/introduction-to-oracle-database.html).

Trong cổng nhà cung cấp tự phát triển, đội dự án có thể thiết kế bảng lưu yêu cầu đăng ký:

~~~sql
SELECT request_id, supplier_code, approval_status
FROM supplier_requests
WHERE approval_status = 'PENDING';
~~~

Đoạn SQL chỉ minh họa một schema giả định do đội dự án quản lý. Nó không phải truy vấn vào bảng nội bộ của Fusion và không phải lệnh được chạy trong bài học này.

Hệ quản trị cung cấp cơ chế lưu và truy vấn; đội ứng dụng vẫn cần xác định trạng thái hợp lệ, quy tắc chuyển trạng thái và ai được phê duyệt. Một bảng có cột approval_status chưa tạo thành một hệ thống mua hàng hoàn chỉnh.

### 4.2. Oracle Database có thể xuất hiện ngoài OCI

Oracle Database có những lựa chọn triển khai trong trung tâm dữ liệu của doanh nghiệp và trên các môi trường đám mây được hỗ trợ. Vì vậy, thông tin “ứng dụng dùng Oracle Database” chưa cho biết ứng dụng hay database đang chạy ở đâu. Xem các mô hình triển khai tại [Oracle Database](https://www.oracle.com/database/).

Cần tách hai trục:

| Trục quyết định | Ví dụ câu trả lời |
| --- | --- |
| Công nghệ dữ liệu | Oracle Database |
| Nơi triển khai và mô hình quản lý | Máy chủ tại doanh nghiệp; tự quản lý trên Compute; dịch vụ cơ sở dữ liệu được quản lý |

Một thay đổi ở trục vị trí có thể giữ nguyên công nghệ cơ sở dữ liệu. Một thay đổi ở trục công nghệ có thể đòi hỏi sửa SQL, driver, kiểu dữ liệu và quy trình vận hành dù nơi triển khai không đổi.

### 4.3. Oracle Database và dịch vụ Oracle Database trên OCI

**Oracle Database** là công nghệ hệ quản trị. **Dịch vụ Oracle Database trên OCI** là cách cung cấp và vận hành công nghệ đó với các khả năng của nền tảng.

Các lựa chọn như Base Database, Autonomous và Exadata Database Service có phạm vi quản lý khác nhau. Tài liệu khởi đầu nằm tại [OCI Database](https://docs.oracle.com/en-us/iaas/Content/Database/home.htm).

Ngay cả khi một dịch vụ tự động hóa nhiều công việc quản trị, ứng dụng vẫn cần schema phù hợp, tài khoản đúng quyền và truy vấn hiệu quả. Dịch vụ cơ sở dữ liệu không tự cung cấp các quy trình ERP hoặc HCM như một bộ ứng dụng nghiệp vụ.

## 5. Quan hệ giữa ba nhóm: kết hợp theo nhu cầu

Sơ đồ dưới đây mô tả một ví dụ tích hợp, không phải cấu trúc bắt buộc của mọi hệ thống Oracle.

~~~mermaid
flowchart LR
    U["Người dùng cổng nhà cung cấp"] --> J

    subgraph C["Phần hệ thống khách hàng triển khai trên OCI"]
        J["Ứng dụng Java tự phát triển"]
        D["Oracle Database của cổng"]
        S["Object Storage của cổng"]
        J -->|"SQL qua JDBC"| D
        J -->|"API lưu trữ"| S
    end

    J -->|"HTTPS qua API được hỗ trợ"| F["Oracle Fusion Cloud Applications SaaS"]
    B["Người dùng nghiệp vụ"] --> F
~~~

Ý nghĩa của sơ đồ:

- OCI cung cấp nền tảng cho phần hệ thống do khách hàng triển khai.
- Oracle Database giữ dữ liệu thuộc cổng trong ví dụ.
- Fusion cung cấp chức năng nghiệp vụ SaaS và giao diện tích hợp.
- Một người dùng có thể làm việc với nhiều ứng dụng nhưng quyền ở từng ứng dụng cần được xác định.

Sơ đồ chủ ý đặt Fusion ngoài phạm vi tài nguyên mà đội cổng trực tiếp quản lý. Nó không khẳng định Fusion chạy ngoài hạ tầng Oracle hoặc mọi kết nối tích hợp đều có cùng đường mạng.

Trong kiến trúc thực tế, còn cần xác định nơi lưu dữ liệu chính thức. Chẳng hạn, nếu hồ sơ nhà cung cấp do ERP quản lý, bản ghi ở cổng có thể chỉ là dữ liệu chờ duyệt hoặc bản sao phục vụ giao diện. Hai phía không nên cùng cập nhật độc lập mà thiếu quy tắc đối soát.

## 6. Ba lớp quyền truy cập cần phân biệt

Đăng nhập thành công vào một hệ thống không tự tạo quyền ở các hệ thống còn lại. Ngay cả khi có SSO, cần phân biệt **xác thực danh tính** với **phân quyền thao tác**.

| Lớp quyền | Đối tượng được bảo vệ | Ví dụ thao tác cần quyền |
| --- | --- | --- |
| OCI IAM | Tài nguyên và thao tác quản trị cloud | Tạo VM, thay cấu hình mạng, quản lý tài nguyên cơ sở dữ liệu |
| Vai trò trong ứng dụng SaaS | Chức năng và dữ liệu nghiệp vụ | Xem chứng từ, phê duyệt giao dịch, gọi API nghiệp vụ |
| Quyền trong Oracle Database | Phiên kết nối và đối tượng dữ liệu | Kết nối database, đọc bảng, thực thi thủ tục |

OCI IAM kiểm soát ai được thao tác với tài nguyên OCI trong phạm vi được cấp. Cơ sở của mô hình này là các danh tính, nhóm và policy; xem [Overview of IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/overview.htm).

Oracle Database kiểm soát truy cập đối tượng dữ liệu thông qua user, role và privilege. Xem [Protecting Database Objects by Using Schemas](https://docs.oracle.com/en/database/oracle/oracle-database/26/dbseg/protecting-database-objects-using-schemas.html).

Với Fusion, quyền gọi REST API còn phụ thuộc các vai trò và quyền của ứng dụng. Hướng dẫn [Quick Start cho Oracle Fusion Cloud Financials REST API](https://docs.oracle.com/en/cloud/saas/financials/26d/farfa/Quick_Start.html) yêu cầu kiểm tra quyền của tài nguyên và thao tác tương ứng.

### 6.1. Ví dụ phân quyền cho một nhóm dự án

Giả định một dự án có ba người:

- **An — kỹ sư nền tảng:** tạo mạng và VM cho cổng.
- **Bình — chuyên viên nghiệp vụ:** cấu hình và kiểm tra quy trình mua hàng.
- **Chi — DBA:** quản lý schema dữ liệu riêng của cổng.

Thiết kế quyền có thể là:

| Người | Công việc được giao | Quyền không nên mặc định suy ra |
| --- | --- | --- |
| An | Quản lý hạ tầng ở compartment của cổng | Quyền phê duyệt mua hàng trong Fusion |
| Bình | Thực hiện nghiệp vụ được phân công | Quyền thay route hoặc xóa VM |
| Chi | Quản lý dữ liệu của cổng theo nhiệm vụ | Quyền quản trị toàn tenancy hoặc mọi dữ liệu trong SaaS |

Quyền quản trị hạ tầng rộng có thể ảnh hưởng gián tiếp đến tính bí mật và toàn vẹn của dữ liệu, chẳng hạn qua thay đổi cấu hình hoặc thao tác vòng đời tài nguyên. Vì vậy, việc tách ba lớp quyền còn phải đi cùng kiểm soát tài khoản đặc quyền và phân tách nhiệm vụ.

### 6.2. Các điều kiện để ứng dụng đọc dữ liệu

Với Oracle Database riêng của cổng, một kết nối thường cần đồng thời đáp ứng:

1. Ứng dụng có đường mạng đến endpoint cơ sở dữ liệu.
2. Cấu hình kết nối và bảo mật truyền thông phù hợp.
3. Danh tính kết nối được xác thực.
4. Danh tính đó có quyền truy cập đối tượng dữ liệu cần dùng.

Quyền OCI để xem tài nguyên database không thay thế các điều kiện trên. Ngược lại, tài khoản đọc một bảng cũng không tự được quyền thay cấu hình mạng của tài nguyên cloud.

Các dịch vụ có thể hỗ trợ tích hợp danh tính để đơn giản hóa xác thực. Dù có tích hợp, phạm vi quyền và điều kiện truy cập vẫn cần được cấu hình theo tài liệu của đúng dịch vụ.

## 7. Phân biệt ba loại giao diện lập trình

Đối với lập trình viên Java, cùng là “gọi Oracle” nhưng có thể là ba công việc khác nhau.

| Công việc | Giao diện thường dùng | Đối tượng kết quả |
| --- | --- | --- |
| Quản lý tài nguyên cloud | OCI API, OCI SDK hoặc CLI | Thông tin tài nguyên, trạng thái cấp phát, cấu hình dịch vụ |
| Trao đổi nghiệp vụ với Fusion | API và cơ chế tích hợp được ứng dụng hỗ trợ | Dữ liệu nghiệp vụ như chứng từ hoặc hồ sơ |
| Đọc và ghi dữ liệu của ứng dụng tự quản lý | JDBC và SQL phù hợp | Hàng dữ liệu, kết quả truy vấn, kết quả giao dịch |

Ví dụ mô tả cấu hình của một dịch vụ Java:

~~~text
OCI_SCOPE
  tenancy
  compartment
  region
  phương thức xác thực OCI phù hợp

PORTAL_DATABASE
  endpoint của database riêng
  service name và cấu hình kết nối
  danh tính database hoặc cơ chế xác thực được hỗ trợ

FUSION_INTEGRATION
  URL môi trường SaaS
  đường dẫn API được tài liệu hóa
  phương thức xác thực và quyền nghiệp vụ tương ứng
~~~

Đây là bản mô tả khái niệm, không phải tệp cấu hình có thể chạy nguyên trạng. Trong một ứng dụng thật, mỗi nhóm cần cấu hình, quản lý bí mật và xử lý lỗi riêng.

### 7.1. Không suy ra quyền SQL từ quyền sử dụng SaaS

Khi tích hợp Fusion, hãy bắt đầu từ API, công cụ nhập/xuất hoặc cơ chế mở rộng được sản phẩm hỗ trợ. Không thiết kế dựa trên giả định rằng đội dự án có thể mở kết nối JDBC vào cơ sở dữ liệu nội bộ của SaaS.

Một số sản phẩm có công cụ báo cáo hoặc trích xuất dữ liệu riêng. Quyền dùng các công cụ đó không đồng nghĩa quyền quản trị database hoặc quyền sửa trực tiếp bảng nội bộ.

Ví dụ cụ thể về ranh giới SaaS: [Understanding Access Limits của Cloud EPM](https://docs.oracle.com/en/cloud/saas/enterprise-performance-management-common/tsepm/7_tips_and_tricks_understand_access_limits.html) nêu rằng dịch vụ này không cung cấp truy cập SQL trực tiếp vào database bên dưới. Khi làm với sản phẩm khác, cần đọc tài liệu của đúng sản phẩm thay vì suy rộng chi tiết này thành một giao diện chung cho mọi SaaS.

### 7.2. Không coi trạng thái kỹ thuật là kết quả nghiệp vụ cuối cùng

Giả sử cổng gửi một hồ sơ sang ERP:

~~~text
Cổng tiếp nhận hồ sơ
→ lưu trạng thái chờ gửi
→ gọi API tích hợp
→ ghi nhận kết quả phía dịch vụ
→ theo dõi trạng thái nghiệp vụ và đối soát
~~~

Cấp phát VM thành công chỉ cho biết một tài nguyên hạ tầng đã được tạo. Ghi một hàng vào database chỉ phản ánh kết quả của thao tác dữ liệu tương ứng. Phía ERP còn có kiểm tra và quy trình nghiệp vụ cần theo dõi.

Nếu một API sử dụng xử lý bất đồng bộ, ứng dụng cần phân biệt việc yêu cầu đã được tiếp nhận với việc nghiệp vụ đã hoàn thành. Cách xác định phải dựa vào tài liệu của endpoint cụ thể.

Khi thử lại sau lỗi mạng, cần tránh tạo hồ sơ trùng. Có thể thiết kế mã tham chiếu nghiệp vụ, trạng thái gửi và cơ chế đối soát phù hợp với khả năng của API được dùng.

## 8. Chuyển ứng dụng lên OCI và chuyển sang SaaS là hai loại dự án

### 8.1. Đưa E-Business Suite hiện có lên OCI

Một doanh nghiệp đang vận hành Oracle E-Business Suite có thể chuyển hệ thống sang hạ tầng OCI theo cấu hình được hỗ trợ. Ứng dụng vẫn là E-Business Suite; dự án thay đổi nơi triển khai và có thể thay đổi cách quản lý một số thành phần.

Oracle xác nhận sự phân biệt này trong [Oracle E-Business Suite on Oracle Cloud FAQ](https://docs.oracle.com/cd/E72030_01/infoportal/ebscfaq.html).

Các công việc cần xem xét có thể gồm:

- Kiểm tra cấu hình ứng dụng, hệ điều hành và database được chứng nhận.
- Thiết kế mạng và kết nối với hệ thống hiện có.
- Di chuyển dữ liệu và thành phần ứng dụng.
- Kiểm tra tích hợp, hiệu năng và phục hồi.
- Xác định đội hoặc đối tác chịu trách nhiệm vận hành sau chuyển đổi.

Mức độ tự quản lý có thể khác nhau nếu doanh nghiệp sử dụng thêm dịch vụ quản lý. Việc thuê một đơn vị vận hành vẫn cần phân biệt với việc chuyển sang một sản phẩm SaaS khác.

### 8.2. Chuyển nghiệp vụ sang Fusion Cloud Applications

Chuyển từ một ứng dụng hiện có sang Fusion SaaS thường cần đánh giá quy trình, cấu hình, dữ liệu và tích hợp theo sản phẩm đích.

Ví dụ, một tùy biến trong hệ thống cũ có thể cần được thay bằng khả năng cấu hình sẵn có hoặc phần mở rộng được hỗ trợ. Dữ liệu có thể phải được làm sạch và ánh xạ sang cấu trúc đích. Người dùng cũng cần được kiểm tra quyền và đào tạo theo quy trình mới.

| Nội dung | Chuyển ứng dụng hiện có lên OCI | Chuyển sang Fusion SaaS |
| --- | --- | --- |
| Trọng tâm | Nơi triển khai và kiến trúc vận hành | Ứng dụng nghiệp vụ và cách triển khai quy trình |
| Phần mềm ứng dụng | Có thể giữ ứng dụng hiện có trong cấu hình được hỗ trợ | Sử dụng chức năng của sản phẩm SaaS đích |
| Dữ liệu | Di chuyển và kiểm tra theo kiến trúc đã chọn | Làm sạch, ánh xạ và nạp theo khả năng sản phẩm |
| Tích hợp | Kiểm tra lại kết nối và tương thích | Có thể cần thiết kế lại giao diện và luồng nghiệp vụ |
| Vận hành | Xác định trách nhiệm ở các lớp hạ tầng, ứng dụng và dữ liệu | Quản trị nghiệp vụ, quyền, tích hợp và các trách nhiệm của khách hàng SaaS |

Không nên ước lượng dự án chuyển sang SaaS chỉ bằng thời gian sao chép VM hoặc database. Hai loại dự án có đối tượng chuyển đổi và tiêu chí hoàn thành khác nhau.

## 9. Trách nhiệm vận hành thay đổi theo lựa chọn dịch vụ

Mô hình trách nhiệm chia sẻ của OCI yêu cầu khách hàng hiểu phần việc của mình về workload, quyền và cấu hình. Xem [Security Overview](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_overview.htm).

Bảng sau dùng để phân tích trách nhiệm, không thay thế tài liệu vận hành của từng dịch vụ:

| Lựa chọn | Phần đội dự án cần xác định rõ |
| --- | --- |
| Java và database tự cài trên Compute | Quản lý hệ điều hành khách, phần mềm, vá lỗi, sao lưu và phục hồi |
| Java kết nối dịch vụ database được quản lý | Trách nhiệm còn lại về schema, truy vấn, quyền, kết nối và cấu hình bảo vệ dữ liệu |
| Sử dụng Fusion SaaS | Cấu hình nghiệp vụ, người dùng, phân quyền, dữ liệu và kiểm tra tích hợp |
| Cổng Java tích hợp Fusion | Vận hành cổng, đồng bộ dữ liệu, xử lý lỗi tích hợp và phân tách danh tính |

Một hệ thống kết hợp có thể cần nhiều nhóm cùng xử lý một sự cố. Ví dụ “không tạo được nhà cung cấp” có thể bắt nguồn từ mất kết nối, lỗi dữ liệu gửi đi, thiếu quyền API hoặc quy tắc nghiệp vụ của ERP.

Cách điều tra nên theo luồng:

1. Xác định thao tác nghiệp vụ và người dùng bị ảnh hưởng.
2. Kiểm tra yêu cầu đã đến cổng chưa.
3. Kiểm tra cổng đã lưu dữ liệu và gửi tích hợp chưa.
4. Kiểm tra kết quả mà dịch vụ đích trả về.
5. Đối chiếu trạng thái hai phía trước khi thử lại hoặc sửa dữ liệu.

Mã tương quan và mã tham chiếu nghiệp vụ giúp nối thông tin giữa các lớp. Log cần tránh ghi mật khẩu, token hoặc dữ liệu nhạy cảm không cần thiết.

## 10. Chi phí và tính sẵn sàng phải được xem theo từng lớp

### 10.1. Tách các nguồn chi phí

Không thể suy ra toàn bộ chi phí chỉ từ một tên gọi như “Oracle Cloud”.

| Phạm vi | Thành phần cần đưa vào dự toán |
| --- | --- |
| OCI cho ứng dụng tự triển khai | Tính toán, mạng, lưu trữ và các dịch vụ sử dụng |
| Oracle Database | Lựa chọn triển khai, năng lực và lưu trữ, bảo vệ dữ liệu, mô hình sử dụng phần mềm áp dụng |
| Oracle Cloud Applications | Module, phạm vi thuê bao và thước đo sử dụng theo dịch vụ đã chọn |
| Hệ thống tích hợp | Môi trường chạy phần mở rộng, lưu dữ liệu, truyền dữ liệu và công sức vận hành |

Bảng chỉ chỉ ra phạm vi cần kiểm tra, không đưa ra điều khoản hoặc mức giá. Khi lập dự toán thực tế, cần đối chiếu đúng dịch vụ và thỏa thuận sử dụng.

Một thuê bao SaaS và tài nguyên OCI cho cổng mở rộng có thể cùng tồn tại. Vì vậy, cần theo dõi cả hai phần thay vì giả định chi phí của phần mở rộng đã nằm trong mọi thuê bao ứng dụng.

### 10.2. Tính sẵn sàng của từng thành phần chưa phản ánh toàn bộ quy trình

Giả sử cổng Java vẫn hoạt động và database riêng vẫn truy cập được, nhưng API đích tạm thời không phục vụ. Người dùng có thể gửi hồ sơ mới nhưng việc đăng ký trong ERP chưa hoàn tất.

Thiết kế có thể cho phép:

- Tiếp nhận hồ sơ và hiển thị rõ trạng thái chờ xử lý.
- Lưu dấu vết yêu cầu để thử lại có kiểm soát.
- Ngăn gửi trùng khi phía đích đã tiếp nhận nhưng phản hồi bị mất.
- Đối soát trạng thái sau khi kết nối phục hồi.

Đây là quyết định của kiến trúc tích hợp và nghiệp vụ. Việc tăng số VM chỉ hỗ trợ phần ứng dụng chạy trên chúng; khả năng hoàn thành quy trình còn phụ thuộc database, dịch vụ SaaS và các kết nối liên quan.

## 11. Cách đọc một yêu cầu còn mơ hồ

Khi nhận yêu cầu “triển khai Oracle”, hãy làm rõ đối tượng cần bàn giao trước khi chọn dịch vụ.

| Câu nói ban đầu | Thông tin cần xác định | Hướng phân loại |
| --- | --- | --- |
| “Cần một máy Oracle để chạy Java” | Cần máy chạy mã, hệ điều hành hay một sản phẩm ứng dụng cụ thể? | Thường bắt đầu ở hạ tầng OCI nếu mục tiêu là chạy ứng dụng tự phát triển |
| “Cần hệ thống nhân sự Oracle” | Cần chức năng nhân sự nào và lựa chọn sản phẩm nào? | Ứng dụng nghiệp vụ, có thể là Fusion HCM |
| “Đưa Oracle lên cloud” | Chuyển database, ứng dụng hiện có hay chuyển nghiệp vụ sang SaaS? | Chưa đủ thông tin để kết luận |
| “Java cần kết nối Oracle” | Kết nối database bằng JDBC hay gọi API của ứng dụng? | Cần xác định endpoint và loại danh tính |
| “Cho nhóm quyền Oracle” | Quyền quản lý tài nguyên, quyền nghiệp vụ hay quyền SQL? | Tách các lớp phân quyền |
| “Lấy dữ liệu từ ERP” | Dữ liệu nào, mục đích nào và giao diện nào được hỗ trợ? | Tích hợp ứng dụng và quản trị dữ liệu |

Một mô tả cụ thể hơn có thể là:

~~~text
Xây dựng cổng nhà cung cấp bằng Java.

Phần triển khai:
- chạy trên OCI trong compartment của dự án;
- lưu dữ liệu riêng trong một dịch vụ Oracle Database được lựa chọn;
- lưu tệp đính kèm ở dịch vụ lưu trữ phù hợp;
- tích hợp Fusion qua API được hỗ trợ.

Phần vận hành:
- giới hạn quyền theo công việc;
- theo dõi trạng thái tích hợp và xử lý thử lại;
- xác định nguồn dữ liệu chính thức, chi phí và cách phục hồi.
~~~

Mô tả này tách được nơi chạy mã, công nghệ dữ liệu, ứng dụng nghiệp vụ và phần việc vận hành. Đội dự án có thể tiếp tục chọn dịch vụ chi tiết mà ít nhầm phạm vi hơn.

## 12. Những tình huống nhận diện nhanh

### Tình huống A: học Java và Oracle SQL trên máy cá nhân

Người học chạy ứng dụng Java và Oracle Database trong môi trường phát triển phù hợp. Tình huống có công nghệ Oracle Database; chưa có thông tin cho thấy đang sử dụng OCI hoặc một bộ ứng dụng SaaS.

### Tình huống B: đưa API Java lên OCI

Ứng dụng được triển khai lên Compute và dùng dịch vụ lưu trữ của OCI. Đây là công việc trên nền tảng OCI. Chưa thể kết luận ứng dụng dùng Oracle Database hoặc Fusion nếu kiến trúc chưa nêu các lựa chọn đó.

### Tình huống C: nhân viên tạo chứng từ trong Fusion

Nhân viên sử dụng chức năng nghiệp vụ được phân quyền trong ứng dụng SaaS. Công việc chính là quy trình nghiệp vụ. Người dùng không cần tự tạo VM cho mỗi chứng từ và không vì thao tác đó mà trở thành DBA.

### Tình huống D: giữ database tại doanh nghiệp, chuyển lớp Java lên OCI

Hệ thống kết hợp ứng dụng trên OCI với Oracle Database ở vị trí khác. Cần thiết kế kết nối, độ trễ, bảo mật và xử lý gián đoạn. Tên công nghệ cơ sở dữ liệu không tự xác định nơi triển khai của nó.

### Tình huống E: cổng Java trên OCI tích hợp Fusion

Cả ba nhóm cùng có thể xuất hiện nếu cổng sử dụng Oracle Database riêng. Đội cần quản lý các ranh giới: tài nguyên OCI, dữ liệu của cổng và chức năng nghiệp vụ được cung cấp bởi Fusion.

## 13. Bảng kiểm nhận diện trước khi triển khai

Trước khi chọn dịch vụ hoặc đề nghị cấp quyền, hãy hoàn thiện các thông tin sau:

| Nội dung | Kết quả cần ghi rõ |
| --- | --- |
| Sản phẩm | OCI, tên ứng dụng nghiệp vụ, tên hệ quản trị hoặc dịch vụ dữ liệu |
| Đối tượng bàn giao | Môi trường chạy mã, chức năng nghiệp vụ, dữ liệu hay luồng tích hợp |
| Nơi triển khai | Phần nào ở OCI, SaaS hoặc môi trường doanh nghiệp |
| Quyền | Danh tính quản trị cloud, danh tính ứng dụng và danh tính dữ liệu |
| Trách nhiệm | Ai cấu hình, vá lỗi, sao lưu, theo dõi và xử lý sự cố ở mỗi phần |
| Nguồn dữ liệu chính thức | Hệ thống nào được quyền quyết định giá trị nghiệp vụ |
| Chi phí | Những dịch vụ và thuê bao cần được đưa vào phạm vi theo dõi |
| Phục hồi | Quy trình nào phải tiếp tục hoạt động và cách xử lý dữ liệu khi có gián đoạn |

Trong module này, các bài về tenancy, IAM, VCN, Compute và lưu trữ phát triển năng lực triển khai trên OCI. Các bài cơ sở dữ liệu giải thích lựa chọn và vận hành dịch vụ dữ liệu liên quan. Khi kết nối với Oracle Cloud Applications, cần bổ sung kiến thức sản phẩm và nghiệp vụ tương ứng để thiết kế đúng giao diện, quyền và trách nhiệm.
