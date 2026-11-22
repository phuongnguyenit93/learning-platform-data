# Hierarchical namespace, ACL và phân quyền dữ liệu

> **Chương:** Nền tảng dữ liệu và phân tích  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau khi hoàn thành, bạn có thể:

1. Giải thích **Hierarchical Namespace (HNS)** là gì, tại sao nó quan trọng đối với **Azure Data Lake Storage Gen2 (ADLS Gen2)** và nó khác cách mô phỏng thư mục bằng tên blob.
2. Thiết kế cây **storage account → file system/container → directory → file** cho luồng dữ liệu landing, curated và analytics.
3. Đọc, thiết lập và kiểm tra **POSIX-like access ACL** và **default ACL**, bao gồm quyền `r`, `w`, `x`, owner, owning group, named user/group, mask và other.
4. Phân biệt **Azure RBAC data roles**, management-plane roles và **ACL theo đường dẫn**, đặc biệt khi cả RBAC và ACL cùng tồn tại.
5. Tính quyền thực tế khi đi qua nhiều thư mục, kiểm tra hành vi tạo, đọc, ghi, liệt kê, rename và xóa một đối tượng.
6. Dùng Azure Portal, **Azure CLI** và **Python Azure Storage Data Lake SDK** để xác minh HNS, xem ACL, cấp quyền trong lab và thử negative cases.
7. Thiết kế quyền cho data engineer, ingestion service, analyst và auditor bằng Microsoft Entra groups/managed identities.
8. Kết hợp ACL với **Private Endpoint, TLS, Shared Key policy, SAS, encryption, audit và lifecycle** để bảo vệ dữ liệu.
9. Chẩn đoán lỗi 403, thiếu quyền `x`, ACL mask, RBAC quá rộng, token/identity sai, đường DFS/Blob và permission drift.
10. Xây dựng runbook, kiểm tra định kỳ và phương án rollback cho môi trường dữ liệu production.

## 1. Bối cảnh: một data lake có nhiều nhóm sử dụng

Một công ty thu thập dữ liệu đơn hàng, đối soát thanh toán và nhật ký ứng dụng lên Azure để phân tích. Cùng một storage account có nhiều nhóm:

- **Ingestion service** ghi các tệp nguồn vào `landing`.
- **Data engineer** làm sạch, chuẩn hóa và chuyển dữ liệu sang `curated`.
- **Finance analyst** chỉ đọc dữ liệu đã kiểm duyệt thuộc mảng tài chính.
- **BI/reporting** đọc tập dữ liệu tổng hợp nhưng không sửa tệp nguồn.
- **Auditor** xem dữ liệu theo phạm vi đã duyệt; không được ghi hoặc xóa.
- **Platform administrator** quản lý account, networking, observability và những thay đổi về quyền.

Nếu mọi nhóm đều được cấp `Storage Blob Data Contributor` trên **toàn storage account**, việc vô tình sửa/xóa hoặc đọc ngoài phạm vi trở nên dễ xảy ra. Nếu chỉ dùng tên blob có dấu `/`, những thao tác thư mục như rename, quản trị ACL theo directory và di chuyển dữ liệu có thể không có cùng semantics của một hệ thống phân cấp thực.

**Azure Data Lake Storage Gen2** là mô hình lưu trữ dữ liệu cho phân tích dựa trên **Azure Blob Storage có bật Hierarchical Namespace**. HNS cho phép thư mục là thực thể thực trong namespace, hỗ trợ thao tác trên directories và **ACL chi tiết theo path** trong phạm vi được hỗ trợ.

~~~mermaid
flowchart TB
    ACC["Storage account\nHNS enabled"]
    FS["File system: lake"]
    LAND["landing/\nRaw ingest"]
    CUR["curated/\nValidated datasets"]
    FIN["curated/finance/\nFinance data"]
    SALES["curated/sales/\nSales data"]
    ANA["analytics/\nShared aggregates"]
    ING["Ingestion identity"]
    ENG["Data engineer group"]
    FUSER["Finance analyst group"]
    BI["BI service"]
    ACC --> FS
    FS --> LAND
    FS --> CUR
    CUR --> FIN
    CUR --> SALES
    FS --> ANA
    ING -.->|"Write via ACL"| LAND
    ENG -.->|"Read/write selected paths"| CUR
    FUSER -.->|"Read only"| FIN
    BI -.->|"Read only"| ANA
~~~

**Sơ đồ chỉ là thiết kế quyền mục tiêu**, không phải Azure tự cấp các quyền này khi tạo storage account. RBAC, access ACL, default ACL, network và identity phải được cấu hình, kiểm thử riêng.

### 1.1. Hai câu hỏi thiết kế bắt buộc

1. **Ai được phép làm gì trên dữ liệu?** Tách data-plane RBAC, ACL và định danh người/ứng dụng.
2. **Từ đâu được phép kết nối?** Dùng firewall, Private Endpoint, Private DNS và policy truyền tải; có quyền dữ liệu vẫn có thể bị chặn bởi mạng.

Một giải pháp an toàn phải trả lời **cả hai**. HNS/ACL không thay thế mạng riêng, key management hoặc ứng dụng kiểm soát dữ liệu nhạy cảm.

## 2. Hierarchical Namespace hoạt động như thế nào?

### 2.1. Blob phẳng và hệ phân cấp thật

Với Blob Storage namespace phẳng, tên blob có thể là:

~~~text
raw/2026/11/20/orders-01.parquet
raw/2026/11/20/orders-02.parquet
~~~

Ký tự `/` trong tên giúp công cụ hiển thị “thư mục” ảo. Nhưng cấu trúc lưu trữ của một blob namespace phẳng không đồng nghĩa từng thành phần `raw`, `2026`, `11`, `20` là các directory objects với ACL riêng.

Khi **HNS được bật**, service có directory semantics:

~~~text
Storage account: stlakeprod001
  File system (= Blob container): lake
    /landing/
      /orders/
        /2026/
          /11/
            /orders-01.parquet
    /curated/
      /finance/
        /orders.parquet
      /sales/
        /revenue.parquet
    /analytics/
      /daily/
        /sales_summary.parquet
~~~

Thư mục `curated/finance` là một đường dẫn phân cấp thực, có owner, group và ACL để kiểm soát các thao tác. HNS hỗ trợ các thao tác file-system-oriented như **rename/move trên namespace** theo khả năng của dịch vụ, giúp những data processing engines cần đổi tên thư mục khi commit kết quả.

### 2.2. Lợi ích với Spark và data platforms

Trong một data pipeline, một Spark job có thể:

1. Ghi dữ liệu ra thư mục staging `/tmp/job-42`.
2. Kiểm tra dữ liệu, schema, row count.
3. Đổi tên/move directory về `/curated/orders/day=2026-11-20` theo chiến lược commit phù hợp.
4. Cho nhóm analytics đọc thư mục mới qua ACL.

Với hệ phân cấp, directory operations có semantics và hiệu năng khác với việc phải liệt kê rồi sao chép hàng nghìn blobs giả lập một thư mục. Tuy nhiên, **atomic rename không phải transaction ACID nhiều container/hệ thống**. Không giả định đổi tên thư mục sẽ tự commit cả Azure SQL, Cosmos DB và Event Hubs.

### 2.3. Cấu trúc tài nguyên

| Khái niệm | ADLS Gen2 với HNS | Ý nghĩa |
| --- | --- | --- |
| Storage account | Azure Storage account bật HNS | Cấu hình vùng, replication, networking, keys |
| File system | Blob container | Gốc dữ liệu được quản trị trong account |
| Directory | Đối tượng đường dẫn phân cấp | Có owner/group và ACL |
| File | Tệp trong file system | Có owner/group và ACL |
| Path | Chuỗi thành phần từ root tới file | Dùng để kiểm tra quyền đi qua cây |
| Access ACL | Quyền trên object hiện tại | Được xét khi thao tác path |
| Default ACL | Mẫu quyền dành cho object con mới | Chỉ có trên directory; không sửa retroactively |
| Azure RBAC | Role assignment tại resource scope | Có thể cấp data access độc lập với ACL |

### 2.4. DFS endpoint và Blob endpoint

Một HNS-enabled account có thể có những endpoint:

~~~text
https://stlakeprod001.dfs.core.windows.net/
https://stlakeprod001.blob.core.windows.net/
~~~

- **DFS endpoint** dành cho các Data Lake Storage Gen2 filesystem/path operations và ACL.
- **Blob endpoint** dùng cho các Blob APIs/clients được hỗ trợ.
- Một file system tương ứng một Blob container, **không phải hai bản sao dữ liệu độc lập**.
- Cần xem compatibility của API/SDK và tính năng HNS; không mặc định mọi Blob API hoạt động hoàn toàn giống namespace phẳng.
- Với **Private Endpoint**, có thể cần Private Endpoint và Private DNS phù hợp cho **cả blob và dfs subresources** khi workflow có operation hoặc redirect qua hai endpoints. Không kết luận “DFS đã private thì Blob chắc chắn private”.

### 2.5. Những giới hạn HNS cần tính từ đầu

- **Không phải mọi tài khoản/storage configuration đều hỗ trợ bật HNS hoặc mọi tính năng Blob**. Kiểm tra eligibility, SKU, feature matrix và migration constraints.
- **Bật HNS có thể là quyết định không đảo ngược bằng một thao tác tắt cờ đơn giản**. Phải xem quy trình hỗ trợ và test compatibility trước khi dùng với tài khoản đang có dữ liệu.
- Cách tính phí, operations, features, lifecycle và công cụ quản trị có thể khác giữa HNS enabled/disabled.
- Không xem HNS như database quan hệ hoặc POSIX filesystem 100%: đây là object storage có file-system semantics được cung cấp, cần đọc phạm vi API.

## 3. Cách tổ chức data lake theo lớp dữ liệu

### 3.1. Mẫu cây dữ liệu

~~~text
lake/
  landing/
    orders/
      yyyy=2026/mm=11/dd=20/
    payments/
      yyyy=2026/mm=11/dd=20/
  quarantined/
    invalid/
  curated/
    finance/
      invoices/
      reconciliations/
    sales/
      orders/
      customers/
  analytics/
    dashboards/
    machine-learning/
  tmp/
    pipeline-runs/
~~~

**Mục tiêu:** ngăn người dùng báo cáo sửa raw ingest; cho phép data engineer xử lý `curated`; nhóm tài chính chỉ đọc đúng nhánh finance. Nên có vùng `quarantined` riêng cho dữ liệu lỗi; tránh cho mọi analysts truy cập dữ liệu chưa kiểm duyệt.

### 3.2. Dùng container hay directory để tạo ranh giới?

| Tiêu chí | Tách file systems/containers | Một file system, nhiều directories |
| --- | --- | --- |
| Azure RBAC scope | Dễ gán quyền theo container | Không có RBAC role assignment trực tiếp tới mọi thư mục như container |
| ACL tinh chỉnh theo path | Có thể dùng | Là điểm mạnh |
| Network/account boundary | Cùng account vẫn chia chung nhiều chính sách | Cùng account |
| Vòng đời, workload ownership | Dễ tổ chức theo container với chính sách khả dụng | Cần ACL/IaC và naming standards |
| Security audit | Đơn giản hơn với ownership rành mạch | Nhiều ACE/path cần kiểm tra drift |
| Tenant isolation nghiêm ngặt | Có thể cần account/container riêng | ACL directory có thể chưa đủ theo threat model |
| Hành vi ứng dụng | Có thể đổi URI khi tách | Dữ liệu cùng filesystem, nhiều paths |

Không dùng **ACL thư mục** làm giải pháp cô lập cho workload được cấp quyền **data-plane Contributor tại account scope**: role rộng có thể làm ACL hạn chế không có tác dụng đối với người giữ role ấy.

### 3.3. Quy ước đặt tên và đường dẫn

- Dùng tên có mục đích rõ: `landing/orders`, `curated/finance`.
- Tránh tên chứa thông tin cá nhân hoặc access tokens.
- Tách `dev/staging/prod` qua accounts hoặc môi trường đủ độc lập theo chính sách.
- Với partition-style paths như `year=2026/month=11`, tính đến cả số lượng directories/files, query engine metadata scans và chi phí operations.
- Không dùng quyền `other::rwx` để sửa lỗi truy cập tạm.
- Có nhóm owner và retention/archival policy cho mỗi dataset.

## 4. Access ACL và default ACL

### 4.1. Access ACL: quyền trên object đang tồn tại

**Access ACL** là tập Access Control Entries (ACE) trên **directory hoặc file hiện tại**, ví dụ:

~~~text
user::rwx
user:<analyst-object-id>:r-x
group::r-x
group:<engineer-group-object-id>:rwx
mask::rwx
other::---
~~~

Đây là ACL của một **directory**: named analyst đọc/đi qua, named engineer group có thể tạo/sửa entries theo quyền thực; `other` không có quyền.

**Các GUID đặt trong dấu <> là placeholders**, người triển khai phải thay bằng **Microsoft Entra object IDs** thực của users/groups/service principals được hỗ trợ, không lấy display name hoặc email tùy ý.

### 4.2. Default ACL: mẫu kế thừa cho con mới

**Default ACL chỉ được đặt trên directory**. Ví dụ trên `/curated/finance`:

~~~text
default:user::rwx
default:group::r-x
default:group:<finance-readers-group-object-id>:r-x
default:mask::r-x
default:other::---
~~~

Khi tạo tệp hoặc directory bên dưới, ACL của object mới được xác định từ parent default ACL theo quy tắc inheritance của dịch vụ; **không phải mọi permission mặc định đều biến thành quyền truy cập thực tế nếu mask/creation semantics hạn chế**.

Với **directory mới**, default ACL có thể tiếp tục được kế thừa để tạo ra các thế hệ con sau. Với **file**, không có default ACL cho con vì file không chứa objects bên trong.

### 4.3. So sánh hai loại ACL

| Câu hỏi | Access ACL | Default ACL |
| --- | --- | --- |
| Đặt trên file? | Có | Không |
| Đặt trên directory? | Có | Có |
| Kiểm soát thao tác với object hiện tại? | Có | Không trực tiếp |
| Con đã tồn tại có tự thay đổi khi sửa ACL này? | Không | Không |
| Con mới có thể nhận quyền từ đây? | Không phải mẫu inheritance | Có, theo quy tắc của service |
| Có thể dùng để bảo đảm quyền owner hiện tại? | Kiểm tra access ACL và ownership | Phải kiểm tra ACL hiện tại riêng |
| Phù hợp cho đường dẫn mới theo pipeline? | Quyền trên path hiện tại | Mẫu cho tệp/thư mục tương lai |

**Lỗi phổ biến:** thêm `default:group:finance-readers:r-x` nhưng quên **access ACL của directory hiện tại**, khiến nhóm Finance vẫn không đi vào được parent.

### 4.4. Access ACL không phải toàn bộ authorization

Khi request dùng **Microsoft Entra authorization**, dịch vụ đánh giá khả năng truy cập dựa trên **RBAC data actions và ACL** theo cơ chế ADLS Gen2. Một RBAC data role **đủ rộng** có thể cho phép thao tác dù access ACL hạn chế. Khi request được cấp đủ quyền qua RBAC, ACL không nhất thiết là bước giới hạn bổ sung.

Vì vậy:

- Không cấp `Storage Blob Data Contributor` tại account scope cho một user rồi mong `other::---` ngăn họ ghi ở nhánh khác.
- Nếu chọn ACL làm **cơ chế giới hạn chi tiết**, phải rà soát mọi RBAC data grants của principal tại account/container/ancestor scopes.
- Account keys/SAS có authorization semantics riêng: đừng giả định POSIX ACL luôn hạn chế quyền của một client dùng key mạnh.

## 5. Ý nghĩa r, w, x trên directory và file

### 5.1. Quyền trên file

| Ký tự | Với file trong ADLS Gen2 | Ví dụ |
| --- | --- | --- |
| `r` | Đọc nội dung/file | Phân tích tệp Parquet |
| `w` | Ghi/sửa nội dung file theo API được hỗ trợ | Pipeline cập nhật tệp |
| `x` | Không có ý nghĩa thực thi chương trình như trên hệ điều hành Linux thông thường | Không dùng `x` để chạy binary trong data lake |

### 5.2. Quyền trên directory

| Quyền directory | Ý nghĩa thực tế |
| --- | --- |
| `r` | Đọc danh sách các entries trong directory khi các điều kiện khác cũng cho phép |
| `w` | Tạo/xóa/đổi entries trong directory khi có thêm quyền `x` và các điều kiện khác |
| `x` | **Traverse/search**: đi qua directory để truy cập object con khi biết path |
| `r-x` | Liệt kê và đi vào thư mục; không tạo/xóa mục |
| `-wx` | Có thể tạo/xóa mục khi có các điều kiện cần thiết, nhưng không thể liệt kê toàn bộ |
| `--x` | Đi qua đường dẫn đã biết; không đủ để liệt kê directory |
| `r--` | Có thể không truy cập hữu ích tới con do thiếu `x` |
| `rwx` | Đọc/liệt kê, đi qua và sửa entries trong directory |
| `---` | Không có quyền ACL trên directory |

Khi cần **đọc file theo đường dẫn**, identity phải có khả năng đi qua tất cả directories cha bằng `x` và có `r` trên file đích, trừ khi một cơ chế authorization khác cấp đủ quyền.

### 5.3. Ví dụ traversal chi tiết

File:

~~~text
/lake/curated/finance/2026/invoices.parquet
~~~

Đối với user chỉ dùng ACL để truy cập, các bước phải được xét:

~~~text
/                    require x
/curated             require x
/curated/finance     require x
/curated/finance/2026 require x
/invoices.parquet    require r
~~~

Muốn **liệt kê** folder `/curated/finance/2026`, cần cả `r` lẫn `x` trên folder đó và `x` trên ancestors theo trường hợp. Nếu biết path chính xác, user có thể đọc file khi có `x` trên directories cha và `r` trên file **mà không được liệt kê toàn bộ các sibling files**.

### 5.4. Tạo và xóa tệp

- Để **tạo child entry** ở một directory, thường cần `w+x` trên parent và quyền traversal ở ancestors.
- Để **xóa hoặc rename một entry** trong directory, directory permissions (thường `w+x` trên parent) quan trọng; không dựa vào giả định có `w` trên file đích là đủ.
- Quyền `r` trên file không cho phép xóa entry.
- Quyền `w` trên file có thể cho phép sửa nội dung nhưng không tự tạo quyền đọc nội dung hay liệt kê folder.
- Các thao tác rename/move directory, ownership, lease, immutable policies hoặc API-specific limitations có thể thêm ràng buộc. Cần thử chính operation sẽ dùng.

**Điểm an toàn:** một người có `w+x` trên parent có thể xóa child entry ngay cả khi ACL trên bản thân file không cấp `w`, theo ngữ nghĩa directory được hỗ trợ. Vì vậy không để thư mục “đọc báo cáo” có `w` chỉ vì người dùng cần upload tệp ở nhánh khác.

## 6. Các thành phần của một ACL entry

### 6.1. Base entries

Một ACL điển hình có các mục:

~~~text
user::rwx       # owner of path
group::r-x      # owning group
other::---      # identities not otherwise matched
~~~

Ở đây `user::` không phải “mọi user”; đó là **owning user**. Tương tự `group::` là **owning group**. `other::` là fallback cho những identity không có quyền qua entries phù hợp.

### 6.2. Named user và named group

~~~text
user:<principal-object-id>:r--
group:<finance-group-object-id>:r-x
~~~

Các entries này cấp quyền cho một user/group cụ thể, không thay ownership hiện tại. Để quản trị ổn định, nên gán cho **Microsoft Entra security groups** với ownership rõ thay vì từng cá nhân nếu bài toán là quyền của team.

### 6.3. Mask: quyền được cấp có thể bị cắt bớt

Mask là giới hạn trên quyền hiệu dụng của **named users, named groups và owning group class**. Mask thường **không giới hạn owning user hoặc other** trong mô hình POSIX ACL.

Ví dụ:

~~~text
user::rwx
user:<analyst-oid>:rwx
group::r-x
mask::r-x
other::---
~~~

Người analyst có entry `rwx` nhưng **effective ACL permission** chỉ tối đa `r-x` do mask không có `w`. Người dùng có thể thấy trong ACL một mục named user là `rwx` mà vẫn bị từ chối thao tác cần `w`.

Ví dụ thứ hai:

~~~text
group:<etl-group-oid>:rwx
mask::r--
~~~

Nhóm ETL bị giới hạn hiệu dụng còn `r--`. Trên directory, thiếu `x` có thể khiến ngay cả đọc đối tượng bên trong theo path cũng thất bại. **Không sửa lỗi bằng cách cấp data-plane Owner trên toàn account**; phải tính lại access ACL/mask theo mục tiêu.

### 6.4. Quyền hiệu dụng không phải phép cộng ngẫu nhiên

Đối với POSIX-style ACL, trình tự đánh giá identity/owner, named user, group class và other có quy tắc. Không được mặc định mọi ACE khớp sẽ được cộng tất cả `rwx` theo kiểu “union không điều kiện”, hoặc một deny ACL riêng có thể đảo RBAC.

Trong ADLS Gen2 ACL, **không có một deny ACE POSIX tổng quát** giống một số NTFS ACL; `other::---` không là deny override đối với quyền cao hơn được RBAC cấp.

### 6.5. ACL owner và quyền thay ACL

- **Owning user** của path và các principals có **quyền quản trị ACL phù hợp** (ví dụ role/data action đặc quyền được hỗ trợ) có thể quản lý ACL theo khả năng dịch vụ.
- Có `rwx` trên một directory **không tự đồng nghĩa** được sửa ACL/ownership của mọi objects con.
- **Storage Blob Data Owner** là data-plane role đặc quyền, thích hợp cho những operators được phê duyệt để quản lý ACL; không cấp cho jobs ingestion thông thường.
- Đổi owner/group có thể yêu cầu quyền riêng và thay đổi security boundary; phải audit.

Trong thực tế, owner/owning group có thể được xác định khi object được tạo và khác với nhóm business owner được liệt kê trong runbook. Cần kiểm tra owner thực, không suy từ tên folder.

## 7. Default ACL và cơ chế kế thừa qua cây dữ liệu

### 7.1. Tệp mới nhận quyền thế nào?

Giả sử directory `/curated/finance` có access ACL cho ETL và default ACL dành cho Finance readers. Khi ETL tạo `q4.csv`:

~~~text
/curated/finance/
  [access ACL]  hiện hành
  [default ACL] mẫu cấp quyền cho con

/curated/finance/q4.csv
  [access ACL]  được xác định khi tạo từ quy tắc inheritance
~~~

**Quyền trên file mới** có thể được suy ra từ default ACL của thư mục cha theo các quy tắc file creation và mask, nhưng cần kiểm tra kết quả bằng `get-access-control`/`az storage fs access show`. File không nhận một default ACL cho grandchildren.

### 7.2. Thư mục con mới nhận cả hai loại ACL

Directory mới như `/curated/finance/2026` có thể nhận:

- **Access ACL** áp dụng cho bản thân directory con.
- **Default ACL** tiếp tục làm mẫu cho files/subdirectories mới bên trong nó.

Cấu trúc:

~~~text
/curated/finance        default group:finance-readers:r-x
  /2026                 access / default inherited by rules
    /11                 access / default inherited by rules
      report.parquet     access inherited by rules
~~~

Nếu hệ thống vận hành nhiều services tạo files, phải test end-to-end để không xuất hiện thư mục với default ACL ngoài ý muốn.

### 7.3. Sửa default ACL không sửa dữ liệu cũ

Đây là lỗi quản trị thường gặp:

1. Ban đầu tạo `/curated/finance/old-report.parquet`.
2. Sau đó thêm default ACL cho `finance-readers` trên parent.
3. User finance vẫn không đọc được `old-report.parquet`.

**Đây là hành vi đúng**: default ACL chủ yếu tác động khi **tạo object mới**, không cập nhật retroactively. Muốn sửa data cũ, cần thao tác cập nhật ACL trên các paths đã tồn tại, có thể dùng recursive operation **được đánh giá rủi ro** trước.

### 7.4. Mẫu cấu hình directory an toàn hơn

Ví dụ logic:

~~~text
/curated/finance/
  Access ACL:
    user::rwx
    group::r-x
    group:<finance-readers-oid>:r-x
    mask::r-x
    other::---

  Default ACL:
    default:user::rwx
    default:group::r-x
    default:group:<finance-readers-oid>:r-x
    default:mask::r-x
    default:other::---
~~~

**Phải cấp `x` trên các directories cha** của `/curated/finance` cho group phù hợp, có thể chỉ là `--x` nếu không muốn cho phép liệt kê toàn cây. Trên file mới, default permissions được áp dụng theo ngữ nghĩa tạo file; tránh giả định quyền `x` cho file có ý nghĩa thực thi chương trình.


## 8. Azure RBAC và ACL: hai cơ chế cần hiểu cùng nhau

### 8.1. Azure RBAC theo resource scope

Microsoft Entra ID xác thực principal; **Azure RBAC** gán role ở subscription, resource group, storage account hoặc Blob container/file system và các scope phù hợp.

| Azure role | Ý nghĩa chính | Lưu ý |
| --- | --- | --- |
| **Storage Blob Data Reader** | Đọc blob data ở phạm vi role | Có thể rộng hơn một nhánh ACL |
| **Storage Blob Data Contributor** | Đọc/ghi/xóa blob data trong phạm vi role | Không phù hợp với analyst chỉ đọc một folder |
| **Storage Blob Data Owner** | Data privilege rộng và có khả năng quản lý ACL | Chỉ cấp cho operator được phê duyệt |
| **Storage Blob Data Delegator** | Quyền liên quan user delegation key | Không tự cấp mọi quyền đọc/ghi tệp |
| **Reader** (management plane) | Xem metadata resource | Không trực tiếp là Data Reader |
| **Contributor** (management plane) | Quản lý nhiều Azure resources | Có thể lấy account keys nếu policy/role cho phép |
| **Owner** (management plane) | Quyền quản trị và role assignments rất rộng | Cần kiểm soát đặc quyền |

**Control-plane Contributor không trực tiếp đồng nghĩa Data Contributor khi app dùng Entra token**, nhưng nếu principal có `listKeys`, họ có thể lấy Shared Key và truy cập dữ liệu khi Storage account cho phép key authorization. Đánh giá toàn bộ các đường truy cập.

### 8.2. ACL theo đường dẫn

ACL tinh chỉnh quyền trên:

~~~text
lake/curated/finance/
lake/curated/sales/
lake/analytics/daily/
~~~

Nếu nhóm Finance chỉ cần đọc `finance`, cấp ACL cho nhánh đó cùng traversal trên ancestors; không cấp `Storage Blob Data Reader` cho toàn account nếu không muốn họ đọc `sales`.

### 8.3. Quan hệ RBAC – ACL

Với request data-plane dùng Microsoft Entra trên HNS-enabled account:

1. Kiểm tra authentication, network và những service policies liên quan.
2. Nếu **RBAC data actions** tại resource scope đã cho phép operation, ACL hạn chế ở path **không nhất thiết chặn request**.
3. Nếu RBAC không cấp đủ data permission, ACL có thể được xét để cho phép thao tác theo owner/group/named entries và mask.
4. Authorization bằng Shared Key/SAS có semantics khác; không áp dụng sơ đồ này như một thuật toán phổ quát cho mọi credential.

~~~mermaid
flowchart TD
    REQ["Entra-authenticated data request"]
    NET{"Network and auth OK?"}
    RB{"RBAC data actions\npermit operation?"}
    ACL{"Path ACL and\ntraversal permit?"}
    YES["Allow"]
    NO["Deny"]
    REQ --> NET
    NET -->|"No"| NO
    NET -->|"Yes"| RB
    RB -->|"Yes"| YES
    RB -->|"No"| ACL
    ACL -->|"Yes"| YES
    ACL -->|"No"| NO
~~~

**ACL không có deny ACE đủ để override một RBAC data role rộng**. Ví dụ `other::---` trên `curated/sales` không ngăn principal có `Storage Blob Data Contributor` tại account scope thao tác dữ liệu đã được role ấy cấp.

### 8.4. Ba cách phân ranh giới

- **Azure RBAC** khi toàn container/account là tập dữ liệu cùng trust boundary.
- **ACL** khi nhiều nhóm cùng file system nhưng cần giới hạn theo directory/file.
- **Account hoặc container riêng** khi cần isolation mạnh, region/network policy, billing ownership hoặc data lifecycle độc lập.

Một người có thể đồng thời là thành viên nhiều groups, dùng nhiều credentials hoặc có RBAC inherited. Muốn biết quyền thực tế phải xem **tất cả các đường cấp quyền** và test bằng identity thật.

## 9. Entra groups và managed identities cho data lake

### 9.1. Người và dịch vụ truy cập

- Data engineer user qua Azure Storage Explorer.
- Managed identity của ETL compute/analytics service.
- Workload identity của AKS/Container Apps.
- Service principal của CI/CD pipeline.
- Microsoft Entra security group gồm Finance, BI và Auditors.

ACL named users/groups thường tham chiếu **Entra object ID GUID**, không phải display name. Khi lệnh yêu cầu `principal ID`, đừng lấy app registration client ID thay cho object ID mà không xác minh.

### 9.2. Ma trận nhóm theo chức năng

| Identity/group | Dữ liệu cần | Quyền đề xuất |
| --- | --- | --- |
| `grp-lake-ingestion` | `landing/orders` | Tạo và ghi files |
| `grp-lake-engineers` | `landing`, `curated` | Đọc landing, đọc/ghi curated |
| `grp-lake-finance` | `curated/finance` | Chỉ đọc |
| `grp-lake-bi` | `analytics` | Chỉ đọc |
| `grp-lake-auditors` | Nhánh được phê duyệt | Chỉ đọc |
| `mi-etl-prod` | Paths cụ thể của pipeline | Quyền tối thiểu runtime |
| `grp-lake-acl-admins` | ACL administration | Data-owner/ACL privilege có kiểm toán |

Gán quyền theo groups giúp tránh sửa ACL của hàng nghìn files khi nhân viên đổi team. Tuy nhiên cần **group owner, review membership và quy trình approval**; nhóm Finance tự ý thêm người có thể mở rộng quyền ngoài dự kiến.

### 9.3. Không trộn identity quản trị và runtime

ETL runtime thường không cần `Storage Blob Data Owner` toàn account. Khi phải cấp lại ACL hàng loạt, dùng operator hoặc identity tạm có permission quản trị, change ticket và logs; không phát Shared Key lâu dài cho notebook chỉ để “chạy được”.

### 9.4. Token refresh và membership

Khi role/group mới được cấp, quyền có thể cần thời gian propagation hoặc token refresh. Kiểm tra đúng principal, group object ID, token và account policy trước khi sửa ACL. **Không test bằng tài khoản Platform Admin rồi suy ra runtime identity của một pipeline cũng có cùng quyền.**

## 10. Shared Key, SAS và rủi ro vượt quyền ACL

### 10.1. Shared Key authorization

Storage account keys là shared secrets có khả năng data access rộng. Request được ký bằng Shared Key **không giống Entra user access dựa trên POSIX ACL**. Giới hạn group bằng ACL không đủ nếu workload vẫn giữ account key.

### 10.2. SAS được ủy quyền như thế nào?

- **Account SAS/service SAS** thường dựa trên account key và scope/permissions/expiry được ký.
- **User delegation SAS** dựa trên Entra authorization và user delegation key theo khả năng API hỗ trợ.
- SAS URI là bearer credential, cần giảm phạm vi, thời hạn và lưu an toàn.

Không phát biểu chung “mọi SAS đều bỏ qua ACL” hoặc “mọi SAS đều bị ACL giới hạn”; phải xét loại SAS, API, permissions và model ký.

### 10.3. Policy hạn chế Shared Key

Một số Azure Storage configurations có property `allowSharedKeyAccess` (Allow storage account key access). Vô hiệu hóa Shared Key có thể ảnh hưởng các ứng dụng dùng connection strings, account/service SAS và tool cũ.

Quy trình:

1. Kiểm kê key-based workloads và automation.
2. Thử Entra OAuth trong SDK/tool.
3. Gán role/ACL đủ, không quá rộng.
4. Kiểm tra user delegation SAS nếu ứng dụng cần SAS.
5. Thay policy trên staging, đo 401/403 và hiệu năng.
6. Có approval và rollback trước khi áp dụng production.

Đừng vô hiệu hóa Shared Key trên account đang chạy chỉ để “kiểm thử ACL”, vì có thể dừng pipelines không liên quan.

## 11. Read-only preflight: kiểm tra HNS và ACL bằng Azure CLI

### 11.1. Chuẩn bị

- Subscription/resource group/storage account được phép.
- HNS đã bật và file system `lake` tồn tại.
- CLI version hỗ trợ `az storage fs` và `--auth-mode login`.
- Identity có quyền đọc metadata liên quan, network path tới DFS endpoint.
- Không in account keys ra terminal/chat để debug.

### 11.2. Đọc cấu hình HNS

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-data-lake-lab"
STORAGE="stlakeunique001"
FILESYSTEM="lake"

az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE" \
  --query "{name:name, kind:kind, sku:sku, hns:isHnsEnabled, allowSharedKey:allowSharedKeyAccess, publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

Nếu `hns: false`, **đừng** tiếp tục với giả định có Data Lake filesystem ACL. Việc bật HNS cho account đang có dữ liệu có eligibility, compatibility và khả năng không dễ đảo ngược; cần migration plan riêng.

### 11.3. Danh sách file systems

~~~bash
az storage fs list \
  --account-name "$STORAGE" \
  --auth-mode login \
  --output table
~~~

`--auth-mode login` dùng Entra identity của CLI, không dùng key được truy tìm ngầm. Quyền **liệt kê containers** có thể khác quyền đọc một file theo path đã biết; đừng kết luận từ một lỗi list rằng mọi ACL path đều sai.

### 11.4. Đọc ACL của đường dẫn

~~~bash
az storage fs access show \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --path "curated/finance" \
  --auth-mode login \
  --output json
~~~

Kết quả có thể gồm owner/group/ACL permissions. Nếu fail, kiểm tra path tồn tại, parent traversal, RBAC/ACL và network. Muốn xem root hoặc parent dùng `az storage fs access show --help` theo CLI version, không tự giả định mọi version dùng cùng cú pháp path root.

### 11.5. Đọc Azure RBAC assignments

~~~bash
STORAGE_ID=$(az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE" \
  --query id --output tsv)

az role assignment list \
  --scope "$STORAGE_ID" \
  --include-inherited \
  --output table
~~~

Đây là lệnh read-only. Đồng thời xem assignments ở **container scope**, management ancestors và group memberships phù hợp; một snapshot account-scope riêng không phải full effective-permission audit.

### 11.6. Bộ kiểm tra tối thiểu

| Kiểm tra | Bằng chứng |
| --- | --- |
| Azure context | Subscription/tenant và identity đúng |
| HNS state | `isHnsEnabled=true` |
| Shared Key policy | Có cho phép key bypass ACL intent không |
| DFS endpoint/network | DNS, TLS và route phù hợp |
| Access ACL | Owner, named entries, mask và other |
| Default ACL | Được đặt trên directory mong muốn |
| Parent traversal | Identity có `x` trên từng ancestor |
| Data-plane RBAC | Không có inherited role quá rộng |
| Negative test | User chỉ đọc không thể ghi/xóa |


## 12. Ghi ACL có kiểm soát bằng Azure CLI

### 12.1. Không thử trên production root

**Những lệnh trong mục này thay đổi data path và security.** Chỉ thực hành trong một file system hoặc nhánh lab tách biệt đã được phê duyệt. Không chạy `set` hoặc `set-recursive` trên root data lake production vì một sai sót có thể cắt quyền của nhiều pipelines và users.

Khi thao tác ACL bằng CLI, phải xác minh CLI version, identity của người thực hiện và khả năng thay ACL được hỗ trợ:

~~~bash
az storage fs directory create --help
az storage fs access show --help
az storage fs access set --help
az storage fs access update --help
~~~

### 12.2. Tạo một directory lab

~~~bash
RG="rg-data-lake-lab"
STORAGE="stlakeunique001"
FILESYSTEM="lake"

az storage fs directory create \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --name "acl-lab" \
  --auth-mode login

az storage fs directory create \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --name "acl-lab/finance" \
  --auth-mode login
~~~

Trên parent của path cần có authorization phù hợp (thường `w+x` theo ACL, hoặc data permission từ RBAC). Đường dẫn `acl-lab` là môi trường test, không phải alias cho `curated/finance` production.

### 12.3. Chuẩn bị group object ID

~~~bash
FINANCE_GROUP_ID="<ENTRA_FINANCE_GROUP_OBJECT_ID>"
~~~

Placeholder phải được thay bằng một **GUID thực**, lấy từ Entra group object ID đã được xác minh; không tự lấy client ID hoặc tên hiển thị. Không cần in danh sách tất cả Entra users cho bài tập nhỏ.

### 12.4. Set access ACL trên directory lab

~~~bash
# GHI ACL: command set có thể thay thế ACL hiện hành!
az storage fs access set \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --path "acl-lab/finance" \
  --acl "user::rwx,group::r-x,group:$FINANCE_GROUP_ID:r-x,mask::r-x,other::---" \
  --auth-mode login
~~~

Đây là **một ACL string đầy đủ cho directory lab**. Với existing production directory, không được chạy `set` chỉ để thêm một group rồi vô tình loại bỏ các named users/groups đã tồn tại. Cân nhắc `update` nếu API hỗ trợ merge ACEs theo cấu hình, và luôn lưu baseline trước thay đổi.

`user::rwx` cấp cho **owning user**, không phải mặc định cho CLI principal đang chạy.

### 12.5. Access ACL và default ACL trên cùng directory

Một directory có thể có cả hai lớp:

~~~text
Access entries:
  user::rwx
  group::r-x
  group:<finance-group-id>:r-x
  mask::r-x
  other::---

Default entries:
  default:user::rwx
  default:group::r-x
  default:group:<finance-group-id>:r-x
  default:mask::r-x
  default:other::---
~~~

Ví dụ khi CLI version hỗ trợ chuỗi ACL gồm cả hai loại ACE:

~~~bash
# Chỉ trong directory lab đã chuẩn bị.
az storage fs access set \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --path "acl-lab/finance" \
  --acl "user::rwx,group::r-x,group:$FINANCE_GROUP_ID:r-x,mask::r-x,other::---,default:user::rwx,default:group::r-x,default:group:$FINANCE_GROUP_ID:r-x,default:mask::r-x,default:other::---" \
  --auth-mode login
~~~

Vì `set` có thể **thay toàn ACL** và các CLI versions có thể thay behavior, cần xem `--help`, đọc lại ACL và test một directory/file mới. Nếu lệnh lỗi parse/authorization, dừng thử nghiệm, không chỉnh ngẫu nhiên trên production.

### 12.6. Xử lý ancestor traversal

Nhóm Finance có `r-x` tại `acl-lab/finance` nhưng vẫn cần `x` ở parent `acl-lab` và filesystem root trong đường đi ACL.

Ví dụ logical requirement:

~~~text
/ (root)           FINANCE: --x
/acl-lab           FINANCE: --x
/acl-lab/finance   FINANCE: r-x
file in finance    FINANCE: r--
~~~

**Không đặt `other::--x` lên root chỉ để cho Finance đi qua** nếu chính sách yêu cầu chỉ nhóm Finance có quyền. Sử dụng named group và xem mask effect.

### 12.7. Readback sau khi đặt ACL

~~~bash
az storage fs access show \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --path "acl-lab/finance" \
  --auth-mode login \
  --output json
~~~

Đọc lại cấu hình là bắt buộc nhưng **không đủ**: hãy thử quyền đọc và thao tác ghi/tạo bằng identity Finance thật, kiểm tra chúng thành công/thất bại đúng ma trận.

## 13. Recursive ACL operations và blast radius

### 13.1. Khi nào cần đệ quy?

Nếu default ACL trên `/curated/finance` vừa thay đổi nhưng 5 triệu files đã tồn tại **không thừa hưởng ngược**, operator có thể phải cập nhật ACL của các objects cũ.

Các command families thường có ở công cụ quản trị:

~~~bash
az storage fs access set-recursive --help
az storage fs access update-recursive --help
az storage fs access remove-recursive --help
~~~

**Chưa chạy những lệnh này** chỉ vì nội dung bài cung cấp tên command; phải kiểm tra cú pháp, privileges và phạm vi trước.

### 13.2. Khác biệt set và update

- **Set-recursive** thường hướng tới thay toàn ACL theo path, có rủi ro loại named entries hiện có.
- **Update-recursive** nhằm sửa/cập nhật entries được chỉ định; cần xem API semantics cụ thể.
- **Remove-recursive** có thể thu hồi một số entries, làm mất quyền truy cập ngoài dự kiến.

Các lệnh cập nhật đệ quy trên số lượng objects lớn có thể là **long-running operation**, gặp partial failures, 429/throttling hoặc interruptions. Không có gì bảo đảm một command áp dụng atomically cho hàng triệu paths.

### 13.3. Runbook triển khai ACL đệ quy

1. Xác định chính xác **filesystem/path prefix** và business owner.
2. Kiểm kê tổng số files/directories cùng dữ liệu nhạy cảm trong nhánh.
3. Xuất/lưu ACL baseline bằng quy trình được phép.
4. So sánh desired ACL với hiện trạng, tìm owners/ACE cần giữ.
5. Thử trên một **subtree nhỏ**, không chứa production data.
6. Chọn phương pháp set/update/remove có ý nghĩa chính xác.
7. Lập maintenance window, retries, continuation/failure-list handling và budget operations.
8. Thực hiện với identity đặc quyền tạm thời, ghi logs/approvals.
9. Đọc lại ACL một số paths đại diện **và thực hiện functional tests**.
10. Xử lý từng batch lỗi, khôi phục baseline nếu cần.
11. Bảo đảm các directories mới vẫn có default ACL thích hợp.

### 13.4. Không chỉnh toàn bộ ACL khi chỉ thiếu execute ở parent

Khi một người chỉ có `r` trên tệp nhưng bị 403 vì thiếu `x` ở `/curated`, sửa parent traversal được phê duyệt có thể đủ; không cần chạy recursive update qua hàng triệu files. Tìm **điểm chặn nhỏ nhất** để giảm blast radius.

### 13.5. Recursive update không thay vai trò RBAC

Dù cập nhật toàn bộ ACEs trong filesystem, một principal vẫn có thể truy cập nhánh bị “chặn” nếu được cấp **Storage Blob Data Contributor ở account scope** hoặc giữ Shared Key. Sửa ACL không thay audit RBAC/keys.

## 14. Azure Storage Data Lake SDK với Python

### 14.1. Vì sao dùng SDK?

Dùng SDK khi:

- Xây ACL audit/reconciliation tự động.
- Xem path ownership, permissions và default ACL.
- Thử nghiệm tạo file và kiểm tra kế thừa.
- Tích hợp identity-based access vào data processing.
- Điều phối recursive ACL updates với kiểm soát lỗi, retries và partial failures.

**Không dùng account key để đo quyền ACL của một Entra group.** Key-based auth là đường truy cập khác và có thể cho kết quả sai mục tiêu.

### 14.2. Dependencies

Trong một **project local của người học**, không thêm file mới vào module:

~~~text
azure-storage-file-datalake
azure-identity
~~~

~~~bash
python -m pip install azure-storage-file-datalake azure-identity
~~~

Production nên pin package versions và kiểm tra runtime compatibility.

### 14.3. Python: đọc ACL bằng DefaultAzureCredential

~~~python
import os

from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

account_name = os.environ["ADLS_ACCOUNT"]
file_system_name = os.environ.get("ADLS_FILESYSTEM", "lake")

service = DataLakeServiceClient(
    account_url=f"https://{account_name}.dfs.core.windows.net",
    credential=DefaultAzureCredential(),
)

fs = service.get_file_system_client(file_system_name)
directory = fs.get_directory_client("curated/finance")

acl = directory.get_access_control()

print("owner:", acl.get("owner"))
print("group:", acl.get("group"))
print("permissions:", acl.get("permissions"))
print("acl:", acl.get("acl"))
~~~

Điều kiện chạy được: account bật HNS, Entra principal có permission xem ACL metadata, network/TLS đúng và SDK version hỗ trợ. `DefaultAzureCredential` trên laptop có thể dùng developer identity; trên Azure runtime là managed/workload identity khác. Phải xác minh principal thực tế.

### 14.4. Đọc file bằng id đường dẫn

~~~python
file_client = fs.get_file_client(
    "curated/finance/2026/invoices.parquet"
)

# Chỉ phù hợp file nhỏ trong lab.
contents = file_client.download_file().readall()
print("bytes received:", len(contents))
~~~

Với file lớn, dùng streaming/chunks/Spark Parquet reader. Nếu 403, kiểm tra `x` trên ancestors và `r` trên file, RBAC/ACL và identity; không chuyển sang account key để test.

### 14.5. Thao tác ghi ACL bằng SDK (chỉ minh họa)

~~~python
# THAO TÁC GHI - KHÔNG chạy trên production:
# directory.set_access_control(
#     acl="user::rwx,group::r-x,other::---"
# )
~~~

Lệnh set ACL có thể làm mất named entries hiện có. Với một application, dùng SDK để **đọc và diff ACL** theo desired state trước khi sửa; role quản lý ACL phải được cấp có kiểm toán.

### 14.6. Identity và client lifecycle

Tạo `DataLakeServiceClient` hợp lý, tận dụng connection pooling của SDK theo lifecycle, không tạo client mới cho mỗi file trong một ETL job lớn. Không in token, Shared Key, user delegation SAS hoặc full signed URL vào logs.

## 15. Ma trận phân quyền và kiểm thử hiệu dụng

### 15.1. Mục tiêu của các nhóm

Một file system:

~~~text
lake/
  landing/orders/
  curated/finance/
  curated/sales/
  analytics/daily/
  tmp/jobs/
~~~

| Path | Ingestion | ETL | Finance | BI | Auditor |
| --- | --- | --- | --- | --- | --- |
| `landing/orders` | Tạo/ghi | Đọc | Không | Không | Không |
| `curated/finance` | Không | Đọc/ghi | Đọc | Không | Đọc theo scope |
| `curated/sales` | Không | Đọc/ghi | Không | Không | Không |
| `analytics/daily` | Không | Đọc/ghi | Không | Đọc | Đọc theo scope |
| `tmp/jobs` | Không | Tạo/ghi/xóa tạm | Không | Không | Không |

**“Không” là mục tiêu security**, không phải ACL deny override. Muốn đạt mục tiêu, không được có RBAC data role rộng, Shared Key/SAS ngoài thiết kế hay named ACL không chủ đích.

### 15.2. Quyền cần trên ancestors

Ví dụ Finance đọc file `/curated/finance/2026/report.parquet`:

~~~text
/                        Finance: --x
/curated                 Finance: --x
/curated/finance         Finance: r-x
/curated/finance/2026    Finance: r-x
/report.parquet          Finance: r--
~~~

Trong thực hành, root path là thư mục gốc của **file system**; filesystem name `lake` không phải một directory con. Những ACL entries minh họa ở đây cần chuyển thành entries named group/user có **object ID thật**.

### 15.3. Một mask sai làm mất quyền

~~~text
group:<etl-group-id>:rwx
mask::r-x
~~~

Mặc dù ETL có entry `rwx`, mask không có `w` nên quyền hiệu dụng theo ACL không cho viết. Nếu sửa mask, phải đảm bảo nó không mở thêm quyền cho named entries khác ngoài chủ đích; xem toàn bộ ACL trước khi chỉnh.

### 15.4. Bộ kiểm thử

| Phép thử | Kỳ vọng |
| --- | --- |
| Finance đọc file finance theo path | Thành công |
| Finance liệt kê directory finance | Thành công nếu có `r+x` |
| Finance tạo file trong finance | Bị từ chối |
| Finance truy cập sales | Bị từ chối |
| BI đọc analytics/daily | Thành công |
| BI đọc landing/orders | Bị từ chối |
| ETL tạo file trong curated/sales | Thành công |
| ETL xóa file trong thư mục write đã cấp | Theo policy mong muốn |
| Finance có ACL đúng nhưng network chặn | Vẫn thất bại vì network |
| Finance bất ngờ có Data Contributor account-wide | Negative tests có thể fail vì RBAC quá rộng |
| Client dùng account key thay vì Entra identity | Không chứng minh ACL của Finance |

### 15.5. Test default ACL với file mới và file cũ

1. Đọc baseline ACL của directory `acl-lab/finance`.
2. Tạo `newdir` và `newfile` bằng identity ETL/owner được phép.
3. Đọc access/default ACL thực tế của `newdir` và access ACL của `newfile`.
4. Thử Finance đọc file mới.
5. Thử Finance ghi/xóa file mới; phải bị chặn nếu read-only.
6. Kiểm tra một file tạo **trước khi thêm default ACL** — nó không tự thay quyền.
7. Kiểm tra default mask có làm permission khác kỳ vọng.
8. Test bằng **đúng principal và credential**, không phải administrator.

**ACL textual readback là cần thiết nhưng chưa đủ**. Quyền hiệu dụng còn phụ thuộc RBAC, token, Shared Key/SAS, network và operation cụ thể.


## 16. Ứng dụng HNS/ACL trong Azure Data Factory, Spark và analytics

### 16.1. Truy cập từ data processing engines

Một giải pháp analytics thường có:

~~~mermaid
flowchart LR
    SRC["Business systems"]
    ADF["Data Factory\nManaged identity"]
    LAND["ADLS Gen2\nlanding"]
    SPARK["Spark / Databricks\nWorkload identity"]
    CUR["ADLS Gen2\ncurated"]
    BI["BI / analytics\nRead-only identity"]
    REP["ADLS Gen2\nanalytics"]
    SRC --> ADF --> LAND
    LAND --> SPARK --> CUR
    CUR --> REP --> BI
~~~

Những engines này cần storage access **đúng identity và credential mode**. Không giả định một pipeline dùng managed identity của Data Factory thì Spark cluster tự dùng cùng identity; mỗi dịch vụ có cơ chế identity integration riêng.

### 16.2. Mapping thao tác với ACL

| Operation | ACL theo ngữ nghĩa path cần kiểm tra |
| --- | --- |
| ADF ghi file mới vào `landing/orders` | `x` ancestors, `w+x` parent |
| Spark đọc file Parquet | `x` ancestors, `r` trên file |
| Spark liệt kê partition folders | `x` parents, `r+x` directory cần list |
| Spark tạo output directory | `w+x` trên parent cùng đường đi |
| Spark commit qua rename/move | Permissions trên source/destination parents theo operation |
| BI đọc dữ liệu tổng hợp | `x` ancestors và `r` trên files, `r+x` nếu list folders |
| Pipeline xóa temporary files | `w+x` ở directory chứa entries, cùng policy/constraints |

Một số query engines cần **liệt kê partition directories** trước khi mở files. Vì vậy ACL `--x` có thể đủ cho point-read path đã biết nhưng **không đủ** cho Spark discovery hoặc BI browsing.

### 16.3. Rename và inheritance

Giả sử data engineer tạo file trong `/tmp/job-42` rồi **move** sang `/curated/finance`. **Không mặc định file được move sẽ kế thừa default ACL của thư mục đích** như một file mới được tạo trực tiếp ở đó; ACL/ownership của đối tượng đã tồn tại có thể được giữ theo rename semantics.

Runbook đúng:

1. Xác định cách ETL output được tạo và commit (create vs rename/move/copy).
2. Đọc access ACL của file sau commit.
3. So sánh với policy của curated zone.
4. Nếu cần, cập nhật ACL có kiểm soát **sau move**, không assume inheritance.
5. Thử Finance đọc, ETL ghi và groups khác bị từ chối.

Đây là nguyên nhân thường gặp khiến **files mới do pipeline tạo** không thể đọc được, dù default ACL ở `curated/finance` nhìn đúng.

### 16.4. ACL và các dataset frameworks

Với Parquet/Delta-like dataset, một “bảng dữ liệu” thường gồm **nhiều tệp metadata và data files**. Nếu analyst được `r` trên files dữ liệu mà thiếu `r+x` trên metadata directories, query có thể vẫn 403. Khi tạo dataset, đặt policy trên **cả thư mục gốc dataset và những tệp con cần thiết**, kiểm thử bằng chính công cụ truy vấn (Spark SQL, Power BI, Synapse hoặc engine được sử dụng).

Không gán `other::rwx` cho metadata folders để chữa lỗi một notebook; thường nguyên nhân là missing traverse, mask, ownership hoặc credential mode.

### 16.5. Tách write staging khỏi published data

Một mẫu vận hành:

~~~text
/landing       ingestion writes
/tmp/jobs      ETL temporary write
/curated       ETL writes; business readers read
/analytics     BI reads, publish identity writes
~~~

Reader không được phép ghi vào staging và ETL không được cấp `Storage Blob Data Owner` toàn account chỉ để đổi tên thư mục. Với dữ liệu nhiều team, có thể dùng một **publish pipeline identity** riêng chịu trách nhiệm chuyển dữ liệu sang nhánh được kiểm soát.

## 17. Network, TLS, encryption và bảo vệ access paths

### 17.1. Private Endpoint cho Blob và DFS

HNS-enabled Storage account có thể được truy cập qua:

~~~text
<account>.dfs.core.windows.net
<account>.blob.core.windows.net
~~~

Khi dùng **Azure Private Link**, cần thiết kế DNS/private endpoints theo những endpoints mà clients thực sự sử dụng. Các công cụ Data Lake có thể truy cập cả DFS/Blob endpoints hoặc được redirect trong một số operations. Nếu chỉ cấu hình một endpoint, có thể gặp timeout hoặc đi qua đường public ngoài dự kiến.

Các Private DNS Zones thường liên quan:

~~~text
privatelink.dfs.core.windows.net
privatelink.blob.core.windows.net
~~~

**Cần kiểm tra chính xác API/network model của account**, VNet links, DNS forwarding từ on-premises và SDK mode. Đừng sửa bằng cách dùng private IP trực tiếp trong URL, vì TLS xác minh hostname.

### 17.2. Cấu trúc defense in depth

| Lớp | Bảo vệ | Không thay thế |
| --- | --- | --- |
| Firewall/Private Endpoint | Hạn chế nguồn và đường mạng | User identity và quyền file |
| TLS | Mã hóa in transit và xác minh server | ACL hoặc RBAC |
| Entra ID/managed identity | Xác thực người gọi | Data permissions nếu chưa cấp |
| Azure RBAC | Data permissions theo resource scope | ACL path fine-grained khi role quá rộng |
| Access/default ACL | Path-level permissions và inheritance | Không phải deny override Shared Key/Contributor |
| Account key policy/SAS | Giới hạn các loại credentials | Network security và data governance |
| Encryption at rest/CMK khi hỗ trợ | Bảo vệ dữ liệu lưu trữ | Không ngăn authorized delete |
| Audit/alerts | Phát hiện và điều tra | Không tự sửa quyền hoặc khôi phục file |

### 17.3. Kiểm tra DNS và TLS từ đúng máy

Linux/macOS:

~~~bash
STORAGE="stlakeunique001"
nslookup "$STORAGE.dfs.core.windows.net"
nslookup "$STORAGE.blob.core.windows.net"

nc -vz "$STORAGE.dfs.core.windows.net" 443
nc -vz "$STORAGE.blob.core.windows.net" 443
~~~

PowerShell:

~~~powershell
Resolve-DnsName stlakeunique001.dfs.core.windows.net
Resolve-DnsName stlakeunique001.blob.core.windows.net

Test-NetConnection stlakeunique001.dfs.core.windows.net -Port 443
Test-NetConnection stlakeunique001.blob.core.windows.net -Port 443
~~~

Các lệnh này chỉ kiểm tra DNS/TCP, **không chứng minh access ACL đúng**. Cũng không suy từ kết quả laptop rằng Spark cluster dùng DNS/route tương tự.

### 17.4. TLS và public access

Azure Storage endpoints dùng HTTPS/TLS. Không tắt certificate validation khi Private DNS lỗi. Có thể cấu hình policy như **secure transfer required** trong account theo khả năng hỗ trợ; cần kiểm tra accounts/clients legacy trước khi thay đổi.

Dù TLS đúng, Shared Key bị lộ vẫn là rủi ro. Ngược lại, managed identity đúng quyền nhưng public network access bị chặn sẽ không kết nối được.

### 17.5. Encryption, CMK và data residency

Azure Storage cung cấp mã hóa at rest; một số account hỗ trợ **customer-managed keys** qua Key Vault/managed identity và các điều kiện riêng. Khi dùng CMK phải thiết kế key lifecycle, quyền truy cập, rotation, backup/restore, soft-delete và quy trình khi key unavailable.

ACL không thay thế **encryption**, và encryption không ngăn một user có quyền data-plane xóa files. Với dữ liệu tài chính/PII, cân nhắc storage account boundary, region, retention, network restriction và audit theo policy.

### 17.6. Security cho các tools dùng key

Không đưa account key hoặc SAS có hạn dài vào notebooks public, build logs hoặc browser client. Ưu tiên managed identity + Entra data permissions khi SDK/workload hỗ trợ. Nếu cần SAS, phải giới hạn expiry, resource scope và operations, bảo vệ URL như secret.

## 18. Observability, audit và permission drift

### 18.1. Tại sao chỉ xem ACL snapshot chưa đủ?

ACL trên `/curated/finance` hôm nay có thể đúng, nhưng ngày mai:

- Một IaC deploy cấp Data Contributor toàn account cho nhóm báo cáo.
- Một ETL move file mới không kế thừa intended ACL.
- Một thành viên được thêm vào nhóm sai.
- Một recursive operation thay mask ngoài dự kiến.
- Một notebook bắt đầu sử dụng account key.
- Private Endpoint/DNS bị sửa khiến client dùng network path khác.
- Auditor có quyền trên một container khác không đúng business scope.

Vì vậy cần **periodic effective-access tests và RBAC/ACL audit**, không chỉ chụp ảnh bảng quyền ban đầu.

### 18.2. Những nguồn tín hiệu

| Nguồn | Theo dõi |
| --- | --- |
| Azure Activity Log | Thay đổi resource, Azure role assignments, network settings |
| Azure Storage diagnostic settings | Các operation logs được hỗ trợ, 401/403, request IDs, latency |
| Storage metrics | Transactions, ingress/egress, availability, latency và error patterns |
| Application/pipeline logs | Dataset path, job ID, principal, operation, result |
| Entra audit | Nhóm/role membership và identity lifecycle |
| IaC drift checks | Resource/permission settings khác desired state |
| Security alerts | Shared Key use, anomalous access, privilege changes theo khả năng |
| FinOps | Operations/storage/retention/replication cost |

**Không mặc định Storage diagnostic logs ghi đủ mọi ACL ACE hoặc nội dung file**. Muốn audit thay ACL cần phối hợp activity/data-plane events được dịch vụ hỗ trợ, change-management logs và snapshot ACL có quyền đọc phù hợp.

### 18.3. Metric definitions bằng Azure CLI

~~~bash
STORAGE_ID=$(az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE" \
  --query id --output tsv)

az monitor metrics list-definitions \
  --resource "$STORAGE_ID" \
  --output table
~~~

Metric names và dimensions có thể khác theo resource/provider/region. Dùng definitions thực của account, không copy một metric từ tài khoản không bật HNS mà coi là có sẵn.

### 18.4. Log mẫu khi access bị từ chối

~~~json
{
  "timeUtc": "2026-11-20T12:00:00Z",
  "pipeline": "finance-curation",
  "path": "lake/curated/finance/2026/report.parquet",
  "operation": "ReadFile",
  "authMode": "MicrosoftEntra",
  "principalId": "<object-id>",
  "result": "AuthorizationPermissionMismatch",
  "correlationId": "job-42"
}
~~~

Đây là **log schema minh họa do pipeline định nghĩa**, không phải Azure bắt buộc phát ra chính xác tất cả fields. Trong production hạn chế log PII, account keys, SAS URLs hoặc contents của file.

### 18.5. Alerts hữu ích

- 403/authorization failures tăng sau deploy.
- Đột ngột có nhiều data DELETE/rename hoặc recursive ACL changes.
- RBAC Data Owner/Contributor mới ở account scope ngoài change window.
- Storage account Shared Key policy bị bật lại bất thường.
- Public network access/firewall được nới rộng không có approval.
- Finance analyst bất ngờ đọc được sales path trong access test.
- Mức giao dịch/data processing tăng không phù hợp business workload.
- Diagnostic logs bị tắt hoặc không có dữ liệu.
- Chi phí operations tăng khi chạy ACL remediation hàng loạt.

Mỗi alert cần owner, severity, ngưỡng và runbook. Chỉ số 403 tăng có thể do một test từ chối truy cập hợp lệ; phải xem context trước khi nâng severity.

## 19. Playbook: xử lý 403, thiếu ACL và sai quyền

### 19.1. Các triệu chứng thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Bằng chứng cần tìm |
| --- | --- | --- |
| `AuthorizationPermissionMismatch` | Thiếu role data action hoặc ACL permission/mask | RBAC, path ACL, ancestors |
| `AuthorizationFailure` hoặc 403 network | Firewall/VNet rules/credential | Network configuration và request error |
| DNS endpoint sai | Private DNS/forwarding | DNS resolution từ client thật |
| TCP 443 timeout | NSG/UDR/firewall/Private Endpoint | Route và connectivity |
| CLI có quyền, Spark job 403 | Khác principal hoặc credential mode | Entra object ID, account key/SAS, workload identity |
| Read file thất bại, file ACL là `r--` | Ancestor thiếu `x` | Root/parent access ACL |
| Có named group `rwx` nhưng không ghi được | `mask::r-x` hoặc parent permissions thiếu | Effective ACE, parent `w+x` |
| Thêm default ACL nhưng file cũ vẫn 403 | Default không retroactive | Creation time và current access ACL |
| Finance đọc được cả sales | Inherited Data Reader/Contributor role hoặc Shared Key | Role assignments/credential |
| Spark rename sang curated làm Finance mất quyền | Moved path giữ ACL khác kỳ vọng | ACL sau rename và publish workflow |
| List directory fail nhưng point-read được | Directory thiếu `r` nhưng có `x` | Operation-specific ACL |
| Data Lake SDK hoạt động qua DFS nhưng Blob tool lỗi | Private endpoints/DNS hoặc API compatibility | DFS + Blob network paths |
| Recursive ACL chạy xong nhưng có files lỗi | Partial failures, throttling, continuation | Operation logs/failure list |
| 404 path not found | Sai filesystem/path/casing hoặc đã move | Path existence, namespace |
| User vừa vào group vẫn 403 | Token/cache/propagation, sai object ID | Group membership và identity token |
| Dữ liệu bị xóa sau khi cấp write cho parent | `w+x` parent cho quyền xóa entry | Parent ACL và data-plane RBAC |

### 19.2. Bước 1 — Xác minh môi trường và identity

Ghi lại Azure subscription, tenant, account, filesystem, path và principal object ID. **Không in secrets**. Kiểm tra client đang dùng Entra OAuth, account key hay SAS; vì các kiểu credential không được đánh giá ACL giống nhau.

### 19.3. Bước 2 — Phân biệt network với data permissions

Nếu DNS/TCP/TLS không thông, sửa mạng trước. Nếu nhận 401, kiểm tra authentication và token/credential. Nếu 403, thu thập **HTTP error code, storage substatus, x-ms-request-id** (nếu có) và operation cụ thể rồi phân loại network ACL hay path authorization.

Không giải quyết 403 bằng `other::rwx`, account key hoặc Data Owner account-wide khi chưa biết nguyên nhân.

### 19.4. Bước 3 — Phân tích ACL theo từng thành phần path

Với `/curated/finance/2026/report.parquet`:

~~~text
root            : x
curated         : x
finance         : x
2026            : x
report.parquet  : r
~~~

Nếu cần list `2026`, yêu cầu `r+x` tại directory ấy. Nếu cần tạo/xóa dưới `2026`, thường `w+x` trên parent. Xem mask và effective group permissions.

### 19.5. Bước 4 — Phân tích RBAC và bypass paths

Kiểm tra inherited roles ở subscription/resource group/account, roles tại container scope, memberships và quyền lấy storage account keys. Nếu người dùng đang được cấp Data Contributor account-wide, sửa ACL sẽ không thu hồi quyền rộng đó; phải **sửa role assignment/credential** theo security review.

### 19.6. Bước 5 — Đối chiếu với thay đổi gần nhất

- File được tạo mới hay move từ staging?
- Default ACL đã tồn tại lúc tạo object chưa?
- Có recursive ACL job đang chạy không?
- Pipeline vừa đổi managed identity/service principal?
- Group membership/owner vừa thay đổi?
- Network/Private DNS đã được sửa?
- Có account key/SAS cũ bị rotate hoặc policy bị vô hiệu hóa?

Lưu timeline và đánh giá rollback trước khi chạy remediation.

### 19.7. Bước 6 — Sửa tối thiểu và kiểm thử lại

Chỉ sửa path/ACE/mask hoặc RBAC scope cần thiết; chạy positive và negative tests bằng identity thật. Đọc lại ACL, đo request 403/latency và kiểm tra không tạo quyền ngoài dự kiến. Nếu change lớn, có approver và rollback kế hoạch.


## 20. Quản trị thay đổi, chi phí và kiểm toán quyền

### 20.1. Quy trình phân quyền production

Một yêu cầu “cho team Finance đọc báo cáo doanh thu” nên đi theo quy trình:

1. Business/data owner phê duyệt **mục đích sử dụng** và dataset.
2. Security xác minh dữ liệu cá nhân, retention, region và phạm vi pháp lý.
3. Platform team xác định identity/group object ID, RBAC scope và credential mode.
4. Data engineer xác định filesystem/path, directory hierarchy và operations thực tế (list/read/write/rename).
5. Thiết kế access ACL, default ACL, mask và ancestor traverse.
6. Kiểm tra existing inherited RBAC roles, group memberships và Shared Key/SAS.
7. Thực hành trên staging với **positive và negative access tests**.
8. Review IaC/config change, approve, deploy trong maintenance window nếu cần.
9. Readback ACL/RBAC và test bằng người/ứng dụng sử dụng thật.
10. Lưu owner, ticket, expiry/review date, evidence và rollback instructions.

**Không chỉ gửi một ảnh chụp ACL rồi kết luận audit PASS**. Test phải chứng minh cả quyền được cấp đúng và quyền không mong muốn bị từ chối.

### 20.2. Permission drift

Các thay đổi dễ làm drift:

- Named user đã nghỉ việc nhưng vẫn có ACE.
- Group bị đổi ownership hoặc thêm thành viên ngoài quy trình.
- New ETL job tạo files với owner/default ACL khác.
- Recursive ACL job sửa mask hoặc other permissions.
- RBAC Contributor được gán ở phạm vi cha.
- Account key được phát tán hoặc Shared Key bị bật lại.
- Một container mới có ACL không giống policy.
- Data export được đưa sang account không có cùng security controls.

Thiết kế **desired-state ACL matrix**, định kỳ đọc actual RBAC/ACL và so sánh, nhưng không tự động sửa khi không có approval nếu có nguy cơ mất quyền.

### 20.3. Version hóa chính sách ACL

Ví dụ metadata cấu hình mong muốn trong hệ thống IaC/policy repository (minh họa, **không phải tệp được tạo trong module**):

~~~yaml
dataset: finance-orders
filesystem: lake
path: curated/finance
ownerTeam: finance-platform
environment: production
allowed:
  finance-readers:
    directory: r-x
    file: r--
  finance-publisher:
    directory: rwx
    file: rw-
defaults:
  inheritReadForNewFiles: true
denyOtherByDefault: true
reviewCadence: quarterly
~~~

Đây là **đặc tả chính sách của đội**, không phải cú pháp ARM/Bicep/Terraform/ACL có thể đưa thẳng cho Azure CLI. Khi chuyển thành Azure ACEs, phải thêm owner/group/mask/other, Entra object IDs và traverse trên ancestors, đồng thời kiểm tra RBAC/key paths. Đặt tên `denyOtherByDefault` chỉ là mục tiêu không cấp `other` access, không có nghĩa Azure POSIX ACL có explicit deny.

### 20.4. Mô hình chi phí

| Nguồn chi phí | Nguyên nhân |
| --- | --- |
| Dữ liệu lưu trữ | Dung lượng, replication, tier và region |
| File/path operations | Directory create/list/rename, reads/writes |
| Recursive ACL updates | Quét và cập nhật số lượng paths lớn |
| ETL compute | Data Factory, Spark, Databricks, Synapse workloads |
| Logging/Monitoring | Diagnostic logs, Log Analytics ingestion/retention |
| Networking | Private Endpoints, egress, hybrid connectivity |
| Backup/retention | Soft delete, versioning, retention features được hỗ trợ |
| Data duplication | Copy sang staging/curated/accounts khác |
| Security operations | Key Vault/CMK và governance automation |

**Không sử dụng số giá cố định cho mọi region/SKU**. HNS-enabled account, số files và operations pattern ảnh hưởng chi phí. Dùng Azure Pricing Calculator và Cost Management theo tài khoản/tier/region thật.

### 20.5. Tránh small-file explosion

Một pipeline tạo 10 triệu files 1 KiB có thể gây metadata operations lớn khi list/rename/update ACL, dù tổng dung lượng chỉ khoảng 10 GiB raw payload.

Đối với data analytics:

- Gộp các files nhỏ thành những files Parquet có kích cỡ phù hợp workload.
- Tổ chức partitions theo truy vấn thực, tránh quá nhiều directories không cần.
- Dùng file compaction có kiểm soát và bảo đảm ACL của files sau compaction.
- Tránh cập nhật ACL đệ quy thường xuyên nếu policy có thể được đặt đúng **trước khi tạo data** qua default ACL.
- Gắn cost budget cho automation và theo dõi activity spikes.

### 20.6. Rollback khi sửa ACL sai

Nếu một deployment cấp nhầm quyền:

1. Cô lập access không mong muốn nếu có rủi ro lộ dữ liệu.
2. Thu thập evidence trước thay đổi (ACL/RBAC snapshot và approval).
3. Thu hồi role/data permission quá rộng hoặc sửa đúng ACE/parent mask.
4. Với recursive changes, xử lý từng batch theo failure lists và baseline.
5. Chạy negative test bằng principal bị ảnh hưởng.
6. Xác minh pipeline hợp lệ vẫn chạy.
7. Đánh giá khả năng data đã bị đọc/ghi/xóa trái quyền, không chỉ xem quyền hiện tại.
8. Ghi postmortem và sửa guardrails.

**Rollback ACL không phục hồi file đã bị xóa**. Khôi phục dữ liệu là quy trình riêng qua soft delete/versioning/backup/recovery features được cấu hình và hỗ trợ.

## 21. Thực hành tổng hợp: dựng mô hình phân quyền

### 21.1. Bài toán

Một công ty sử dụng ADLS Gen2 cho dữ liệu thương mại điện tử:

~~~text
Storage account: stlakeunique001
HNS: enabled
File system: lake

Paths:
  landing/orders/2026/11/
  curated/finance/2026/
  curated/sales/2026/
  analytics/daily/
~~~

Yêu cầu:

- `mi-ingestion` chỉ được nạp dữ liệu raw vào `landing/orders`.
- `grp-engineers` đọc raw và xuất dữ liệu sạch sang `curated`.
- `grp-finance` liệt kê và đọc `curated/finance`, không ghi/xóa và không xem `sales`.
- `grp-bi` chỉ đọc `analytics`.
- `grp-acl-admin` được quản trị ACL theo ticket.
- Dữ liệu production không được truy cập qua account keys phân phát rộng.
- Truy cập phải đi qua networking policy phù hợp, audit và cost budget.

### 21.2. Bài A — Thiết kế cây ACL

**Yêu cầu:** liệt kê quyền tối thiểu cho `grp-finance` để đọc `/curated/finance/2026/orders.parquet` và liệt kê folder `2026`.

**Đáp án:**

~~~text
/                         --x
/curated                  --x
/curated/finance          r-x
/curated/finance/2026     r-x
/orders.parquet           r--
~~~

Những ký hiệu này là **permissions của named Finance group** ở mỗi path tương ứng, không phải full ACL strings. Phải xét mask, owner/group/other và RBAC effective access. Để files mới được đọc theo policy, đặt default ACL thích hợp trên directories sẽ tạo files.

### 21.3. Bài B — Vì sao r-- trên file vẫn 403?

Finance có access ACE `user:FIN:r--` trên file, nhưng `/curated` không cho traverse `x`.

**Đáp án:** thiếu `x` ở một ancestor, nên không đi tới file bằng đường ACL. Thêm permission traversal phù hợp trên parent được phép, không cần cấp data owner account-wide.

### 21.4. Bài C — Vì sao named group rwx nhưng không ghi được?

ACL directory:

~~~text
user::rwx
group::r-x
group:<etl-group-id>:rwx
mask::r-x
other::---
~~~

**Đáp án:** mask cắt `w` của named group, effective chỉ còn `r-x`. Kiểm tra mask và mọi named entries trước khi thay đổi.

### 21.5. Bài D — Default ACL có tác động file cũ không?

`/curated/finance` được thêm default ACL cho Finance sau khi `old.csv` đã tồn tại. Người dùng vẫn không đọc được `old.csv`.

**Đáp án:** default ACL không thay ACL của object cũ. Cần xem access ACL hiện tại trên file và tổ chức update có kiểm soát; không chạy recursive set cả container production.

### 21.6. Bài E — ACL từ chối nhưng user vẫn đọc được Sales

Finance có `other::---` ở Sales nhưng được cấp `Storage Blob Data Reader` toàn storage account.

**Đáp án:** RBAC data role có thể cấp quyền đọc dù ACL hạn chế. Cần giảm RBAC role/scope hoặc chia container/account, sau đó chạy negative test.

### 21.7. Bài F — Pipeline dùng account key

ETL job dùng Shared Key, đọc toàn account được; group ETL chưa có ACL thích hợp.

**Đáp án:** đây **không phải bằng chứng ACL của ETL đã hoạt động**. Chuyển lab job sang Entra identity, kiểm tra ACL/RBAC và loại key theo kế hoạch bảo mật.

### 21.8. Bài G — Rename khiến BI mất quyền đọc

Pipeline xuất file vào `/tmp` rồi move sang `/analytics`. BI vẫn 403 dù default ACL ở `analytics` cấp quyền đọc.

**Đáp án:** file được **move** chứ không tạo mới dưới parent, nên không tự bảo đảm kế thừa default ACL đích. Xem ACL sau rename và xử lý bằng publish workflow phù hợp.

### 21.9. Bài H — Folder có r--, thiếu x

BI biết đường dẫn tệp chính xác nhưng parent `/analytics` có `r--` trên directory.

**Đáp án:** thiếu traverse `x`. `r` trên directory dùng cho listing, không thay `x` để truy cập child. Cấp `r-x` khi BI cần list và traverse, hoặc `--x` nếu chỉ cho known path access theo yêu cầu.

### 21.10. Bài I — Lệnh set thay vì update

Một operator chạy `az storage fs access set` với chỉ ba base entries trên `curated/finance` và mất các named ACEs.

**Đáp án:** lệnh set có thể thay ACL hiện có. Restore baseline/ACE đầy đủ theo runbook, dùng API update được hỗ trợ khi thích hợp và test trước ở subtree nhỏ.

### 21.11. Bài J — Private Endpoint chỉ có DFS

Spark đọc qua DFS hoạt động, nhưng công cụ Blob API timeout trong mạng private-only.

**Đáp án:** kiểm tra Private Endpoint/DNS/routing cho `blob.core.windows.net` ngoài `dfs.core.windows.net`; không tắt TLS hoặc mở Internet rộng để khắc phục.

### 21.12. Bài K — Recursive ACL và chi phí

Job cập nhật ACL đệ quy trên 8 triệu files nhưng chỉ muốn cấp `x` trên một ancestor.

**Đáp án:** dừng/đánh giá lại phương án; có thể chỉ cần sửa permission tại ancestor và những paths liên quan. Recursive operation làm tăng chi phí, rủi ro partial failure và blast radius.

### 21.13. Bài L — Tính quyền ghi khi parent w+x

Một user có `w+x` ở thư mục chứa tệp, nhưng không có `w` trên file.

**Câu hỏi:** có thể xóa file không?

**Đáp án:** trong mô hình directory permissions, thao tác xóa entry thường dựa vào quyền `w+x` trên parent (cùng những constraints khác), không chỉ vào `w` trên file. Phải test operation cụ thể và bảo vệ directory permissions phù hợp.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Hierarchical Namespace có nghĩa gì?

**Trả lời:** HNS làm directories thành thực thể trong namespace của Blob Storage, hỗ trợ thao tác directory/file-system-oriented và ACL theo path trên ADLS Gen2.

**Câu 2.** File system trong ADLS Gen2 tương ứng với gì?

**Trả lời:** Blob container của HNS-enabled storage account.

**Câu 3.** DFS endpoint khác Blob endpoint như thế nào?

**Trả lời:** DFS dùng cho filesystem/path và ACL operations; Blob endpoint cho Blob APIs được hỗ trợ. Cùng dữ liệu storage account nhưng workflows/Private Endpoints có thể dùng cả hai.

**Câu 4.** Access ACL và default ACL khác nhau?

**Trả lời:** Access ACL điều khiển object hiện tại; default ACL trên directory làm mẫu inheritance cho objects mới, không sửa retroactively data cũ.

**Câu 5.** Tại sao file có `r--` vẫn bị 403?

**Trả lời:** Có thể thiếu `x` trên một trong các directories cha, hoặc thiếu authorization khác; cũng phải kiểm tra RBAC, network và credential.

**Câu 6.** `r-x` trên directory dùng để làm gì?

**Trả lời:** Liệt kê và traverse directory, không tạo/xóa entries như khi có `w+x`.

**Câu 7.** Mask có ảnh hưởng named user `rwx` không?

**Trả lời:** Có. Ví dụ `mask::r-x` có thể cắt `w`, khiến effective ACL không thể ghi.

**Câu 8.** Một user đã có Storage Blob Data Contributor ở account scope có bị ACL `other::---` ngăn ghi không?

**Trả lời:** Không nên giả định. Data-plane RBAC rộng có thể cho phép operation độc lập restrictive ACL.

**Câu 9.** Azure Reader management role có tự cho phép đọc file trong ADLS không?

**Trả lời:** Không trực tiếp; cần data access bằng RBAC data role, ACL hoặc credential khác được hỗ trợ.

**Câu 10.** Control-plane Contributor có hoàn toàn không thể lấy dữ liệu không?

**Trả lời:** Không thể kết luận như vậy: quyền lấy storage account keys và Shared Key policy có thể tạo đường truy cập gián tiếp.

**Câu 11.** Khi nào dùng Entra group để cấp ACL?

**Trả lời:** Khi nhiều users cần cùng quyền theo chức năng, với quản trị membership và audit rõ ràng.

**Câu 12.** Tại sao không dùng Shared Key để chứng minh ACL Finance?

**Trả lời:** Key-based authorization khác Entra/ACL, có thể cấp quyền rộng và bỏ qua phạm vi ACL mà bạn định test.

**Câu 13.** Tại sao default ACL của thư mục đích không tự làm file đã move kế thừa?

**Trả lời:** File là object đã tồn tại; rename/move không mặc định là tạo object mới theo quy tắc default ACL. Cần kiểm tra ACL sau operation.

**Câu 14.** `set-recursive` có rủi ro gì?

**Trả lời:** Có thể thay nhiều ACL, loại ACE quan trọng, gây 403/privilege escalation, partial failures và chi phí operations lớn.

**Câu 15.** Một đường dẫn tài chính có tên group `Finance` là đủ để set ACL không?

**Trả lời:** Không. Cần Entra group object ID phù hợp, quyền ancestor và mask; display name không là principal ID an toàn.

**Câu 16.** `--x` trên directory có đủ để liệt kê file names không?

**Trả lời:** Không. Nó cho traversal với path đã biết, còn liệt kê thường cần `r+x`.

**Câu 17.** Private Endpoint cho DFS có bảo đảm mọi Blob API calls private không?

**Trả lời:** Không mặc định. Cần xem path thực của client và cấu hình Private Endpoint/DNS cho Blob endpoint nếu workload dùng.

**Câu 18.** Đổi ACL trên hàng triệu objects có phải transaction nguyên tử không?

**Trả lời:** Không nên giả định. Recursive operations có thể dài, có partial failures và yêu cầu retry/continuation/verification.

**Câu 19.** Dùng `other::---` có bảo đảm tuyệt đối user không truy cập dữ liệu không?

**Trả lời:** Không. RBAC data roles, owner/named ACE, account keys/SAS và credential type đều phải được xét.

**Câu 20.** Một principal có `w+x` ở parent nhưng không có `w` trên file, điều gì đáng chú ý?

**Trả lời:** Có thể xóa/rename entry trong directory theo operation semantics dù không được phép sửa nội dung file; cần bảo vệ parent ACL.

**Câu 21.** Cần kiểm tra gì sau khi cấp quyền đọc Finance?

**Trả lời:** Đọc được file đúng, liệt kê folder đúng, không ghi/xóa được và không đọc được Sales; dùng identity và auth mode thật.

**Câu 22.** Khi nào nên tách container hoặc storage account thay vì chỉ ACL thư mục?

**Trả lời:** Khi yêu cầu isolation mạnh, policies/lifecycle/network độc lập hoặc RBAC theo resource scope là biện pháp kiểm soát phù hợp hơn.

## Ghi nhớ

- **ADLS Gen2 = Azure Blob Storage có Hierarchical Namespace (HNS)**, hỗ trợ directories thật, file-system operations và ACL theo path.
- **Access ACL** điều khiển object hiện tại; **default ACL** giúp con mới kế thừa theo quy tắc dịch vụ, không cập nhật files cũ.
- Với directories, **`x` = traverse**, `r+x` cho liệt kê/đi qua, `w+x` có thể cho phép tạo/xóa entries; cần hiểu cả quyền trên parent.
- **ACL mask có thể giảm quyền hiệu dụng** của owning group và named users/groups dù entries hiển thị `rwx`.
- **Azure RBAC data permissions và ACL không phải hai tầng deny bắt buộc**. Role Reader/Contributor quá rộng hoặc Shared Key có thể phá ý định giới hạn ACL.
- **Managed identity + Entra groups + least privilege** giúp giảm phụ thuộc keys; kiểm thử bằng principal thật, không chỉ tài khoản admin.
- **DFS/Blob Private Endpoints, DNS, TLS, RBAC và ACL** là những lớp bảo vệ bổ sung, không thay thế lẫn nhau.
- **Recursive ACL changes và data moves** phải được review, kiểm thử và readback; rename/move không nên mặc định kế thừa default ACL của nơi đến.
- Production data lake cần **RBAC/ACL inventory, negative access tests, audit, permission drift monitoring, rollback plan, cost budget và owner của từng dataset**.
