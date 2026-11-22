# Redundancy LRS, ZRS, GRS và GZRS

Khi triển khai một ứng dụng trên Microsoft Azure, việc lưu tệp, hình ảnh, nhật ký, bản sao lưu và dữ liệu giao dịch thường phụ thuộc vào Azure Storage. Nếu một ổ đĩa, máy chủ, trung tâm dữ liệu hoặc cả khu vực Azure gặp sự cố, dữ liệu có còn tồn tại không? Ứng dụng có đọc/ghi được ngay không? Nếu phải chuyển sang khu vực dự phòng, có thể mất bao nhiêu dữ liệu vừa ghi?

Các câu hỏi đó liên quan đến **storage redundancy** — cách Azure duy trì nhiều bản sao dữ liệu để hạn chế mất dữ liệu do hỏng hóc hạ tầng. Với Storage Account tiêu chuẩn (Standard), bốn mô hình quan trọng là:

- **LRS — Locally Redundant Storage:** sao chép trong một vị trí vật lý tại region chính.
- **ZRS — Zone-Redundant Storage:** sao chép đồng bộ qua các availability zone tại region chính.
- **GRS — Geo-Redundant Storage:** sao chép trong region chính và bất đồng bộ sang region thứ hai.
- **GZRS — Geo-Zone-Redundant Storage:** kết hợp sao chép qua zone ở region chính với sao chép bất đồng bộ sang region thứ hai.

Bài học thuộc chương **Nền tảng Azure Storage** của module **CLOUD_PROVIDERS_AZURE**. Trong bối cảnh một kiến trúc ứng dụng Azure sử dụng subscription, resource group, mạng, compute, lưu trữ và dữ liệu, việc chọn redundancy ảnh hưởng trực tiếp đến khả năng chịu lỗi, thiết kế khôi phục thảm họa, hiệu năng, chi phí và kế hoạch vận hành.

> **Ý chính:** Redundancy tăng khả năng bảo toàn dữ liệu trước sự cố hạ tầng, nhưng **không đồng nghĩa với backup**, không tự bảo đảm ứng dụng luôn hoạt động và không loại bỏ nhu cầu thiết kế disaster recovery.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **durability** (độ bền dữ liệu), **availability** (khả năng truy cập), **RPO** và **RTO**.
2. Giải thích phạm vi sao chép và cách hoạt động của LRS, ZRS, GRS và GZRS.
3. Đánh giá khả năng chịu lỗi ổ đĩa, zone và region cho từng phương án.
4. Hiểu **đồng bộ trong region**, **bất đồng bộ giữa region**, nguy cơ dữ liệu chưa kịp sao chép khi failover.
5. Phân biệt GRS/GZRS với **RA-GRS/RA-GZRS**, đặc biệt quyền đọc ở region phụ.
6. Chọn redundancy dựa vào SLA/SLO, yêu cầu phục hồi, loại dữ liệu, khu vực hỗ trợ và ngân sách.
7. Tạo và kiểm tra Storage Account bằng Azure Portal, Azure CLI hoặc Bicep.
8. Lập kế hoạch failover, kiểm tra dữ liệu và bổ sung backup, versioning, soft delete, monitoring.

## 2. Các khái niệm nền tảng cần tách bạch

### 2.1. Region và availability zone

**Azure region** là một khu vực địa lý triển khai dịch vụ, ví dụ **Southeast Asia**. Nhiều region cung cấp **availability zone**: các vị trí hạ tầng vật lý được tách biệt trong cùng một region, có nguồn điện, làm mát và mạng riêng ở mức phù hợp với kiến trúc zone.

Sơ đồ khái niệm:

~~~text
Azure Region A (primary)
├── Availability Zone 1
├── Availability Zone 2
└── Availability Zone 3

Azure Region B (secondary)
└── Vị trí sao chép địa lý theo cơ chế dịch vụ
~~~

Không phải region nào cũng hỗ trợ mọi kiểu redundancy, mọi loại Storage Account và mọi SKU như nhau. Region phụ của geo-redundant storage được Azure xác định theo cơ chế ghép vùng/địa lý được hỗ trợ; không thể suy luận rằng bạn được tùy ý chọn một region phụ bất kỳ.

### 2.2. Durability khác availability

- **Durability:** xác suất dữ liệu đã được ghi thành công vẫn được lưu giữ, ngay cả khi một số thành phần lưu trữ hỏng.
- **Availability:** khả năng dịch vụ chấp nhận yêu cầu đọc hoặc ghi ở thời điểm người dùng truy cập.
- **Resiliency:** khả năng tiếp tục hoặc khôi phục hoạt động khi xảy ra lỗi.
- **Disaster recovery (DR):** quy trình khôi phục hệ thống khi sự cố vượt quá phạm vi vận hành thông thường.

Ví dụ: các bản sao dữ liệu vẫn còn nguyên sau một sự cố region, nhưng ứng dụng không thể ghi vào endpoint chính cho đến khi có failover hoặc phục hồi. Lúc đó **durability** có thể cao nhưng **availability ghi** vẫn bị gián đoạn.

Ngược lại, hệ thống có endpoint đang hoạt động nhưng ứng dụng vô tình ghi đè một tệp đúng bằng nội dung sai: redundancy có thể nhân bản chính nội dung sai đó. Đây không phải lỗi vật lý mà redundancy được thiết kế để khắc phục.

### 2.3. RPO và RTO

Hai chỉ tiêu thường được dùng trong thiết kế khôi phục:

| Chỉ tiêu | Câu hỏi cần trả lời | Ví dụ yêu cầu nghiệp vụ |
|---|---|---|
| **RPO — Recovery Point Objective** | Có thể chấp nhận mất tối đa bao nhiêu dữ liệu mới nhất? | “Không được mất quá 15 phút giao dịch.” |
| **RTO — Recovery Time Objective** | Sau sự cố, hệ thống phải hoạt động trở lại trong bao lâu? | “Ứng dụng phải khôi phục trong 2 giờ.” |

Các con số trên **chỉ là yêu cầu ví dụ**, không phải cam kết của Azure Storage. Với geo-redundant storage, sao chép giữa hai region là **bất đồng bộ**: dữ liệu được xác nhận ghi ở primary có thể chưa đến secondary khi primary mất hoàn toàn.

Redundancy không tự chứng minh hệ thống đáp ứng RPO/RTO. Phải xét replication lag, thủ tục failover, DNS/client retry, mạng, compute, database, quyền truy cập và kiểm thử phục hồi thực tế.

### 2.4. Sao chép đồng bộ và bất đồng bộ

**Sao chép đồng bộ (synchronous):** thao tác ghi chỉ được xác nhận hoàn tất sau khi đáp ứng điều kiện ghi tới các bản sao bắt buộc trong phạm vi đồng bộ của dịch vụ. Mô hình này hạn chế mất dữ liệu đã được xác nhận khi xảy ra một số lỗi thành phần hoặc zone.

**Sao chép bất đồng bộ (asynchronous):** phía primary có thể xác nhận ghi trước khi phiên bản dữ liệu đó đã hoàn tất truyền sang secondary. Cách này hỗ trợ khoảng cách địa lý lớn, nhưng phát sinh **replication lag** và khả năng mất những thay đổi chưa được đồng bộ nếu phải chuyển sang secondary đột ngột.

Trong Azure Storage:

- LRS và ZRS sử dụng sao chép đồng bộ theo phạm vi tương ứng trong **primary region**.
- GRS có bản sao LRS ở primary và sao chép **bất đồng bộ** đến secondary region.
- GZRS có bản sao ZRS ở primary và sao chép **bất đồng bộ** đến secondary region.

## 3. LRS — Locally Redundant Storage

### 3.1. Cơ chế hoạt động

LRS duy trì **ba bản sao dữ liệu** bên trong **một vị trí vật lý** tại primary region.

~~~mermaid
flowchart TB
    C["Ứng dụng"] --> A
    subgraph PrimarySite["Một vị trí vật lý của primary region"]
      A["Bản sao 1"] --- B["Bản sao 2"]
      B --- D["Bản sao 3"]
    end
~~~

Các bản sao được ghi đồng bộ theo thiết kế LRS. Khi một ổ đĩa hoặc phần cứng lưu trữ hỏng, hệ thống có thể sử dụng các bản sao còn lại để duy trì dữ liệu.

Tuy nhiên, vì các bản sao tập trung trong một vị trí vật lý, LRS **không được thiết kế để chịu được việc mất toàn bộ vị trí đó hoặc primary region** như một mô hình có nhiều zone hoặc region.

### 3.2. Khi nào chọn LRS?

LRS phù hợp khi:

- Dữ liệu có thể được tái tạo từ nguồn khác.
- Workload development, testing hoặc sandbox có yêu cầu sẵn sàng thấp hơn.
- Ứng dụng có một cơ chế DR/backup khác đã được kiểm thử.
- Ngân sách là yếu tố đáng kể và rủi ro mất toàn bộ vị trí có thể được chấp nhận theo quyết định nghiệp vụ.

Ví dụ: một hệ thống build sinh ra các tệp trung gian có thể tái tạo từ repository và pipeline. LRS có thể là lựa chọn hợp lý nếu mất dữ liệu tạm thời không ảnh hưởng cam kết dịch vụ.

**Không nên suy luận** rằng LRS phù hợp với mọi dữ liệu ít truy cập. Tần suất đọc thấp không có nghĩa dữ liệu không quan trọng.

### 3.3. Giới hạn

- Không cung cấp bản sao độc lập ở nhiều availability zone.
- Không có bản sao secondary region từ cơ chế LRS.
- Nếu region ngừng hoạt động, chỉ chọn LRS không tạo sẵn một nơi để failover sang khu vực khác.
- Các lỗi logic như xóa nhầm, ghi đè hoặc phần mềm độc hại vẫn cần biện pháp bảo vệ dữ liệu khác.

## 4. ZRS — Zone-Redundant Storage

### 4.1. Cơ chế hoạt động

ZRS duy trì các bản sao dữ liệu **đồng bộ trên ba availability zone** trong cùng primary region ở những region/dịch vụ được hỗ trợ.

~~~mermaid
flowchart TB
    C["Ứng dụng"] --> Z1
    subgraph PrimaryZones["Primary region — nhiều Availability Zones"]
      Z1["Zone 1<br/>Bản sao"]
      Z2["Zone 2<br/>Bản sao"]
      Z3["Zone 3<br/>Bản sao"]
    end
    Z1 <--> Z2
    Z2 <--> Z3
~~~

Khi một zone gặp sự cố, những bản sao tại các zone khác giúp dịch vụ tiếp tục hoạt động trong phạm vi khả năng của ZRS. ZRS vì vậy thích hợp cho dữ liệu cần chống lỗi cấp zone.

Với ghi đã được xác nhận thành công theo cơ chế đồng bộ ZRS, sự cố một zone đơn lẻ thông thường không tạo ra replication lag giữa các zone theo cách geo-replication bất đồng bộ có thể gặp.

### 4.2. Khi nào chọn ZRS?

ZRS đáng cân nhắc khi:

- Workload production cần tăng khả năng sẵn sàng trước sự cố một availability zone.
- Compute hoặc ứng dụng đã triển khai đa zone, và lớp lưu trữ cũng cần mô hình chịu lỗi zone.
- Dữ liệu phải ở lại một region theo chính sách hoặc không cần bản sao địa lý.
- Tổ chức muốn tăng độ bền so với LRS mà chưa cần geo-redundancy.

Ví dụ: web API chạy trên nhiều availability zone, dùng Blob Storage cho tệp đính kèm. Nếu lớp compute phân tán nhiều zone nhưng storage chỉ dùng LRS, lỗi vị trí của storage vẫn có thể trở thành điểm yếu của kiến trúc.

### 4.3. Giới hạn

- ZRS **không có bản sao ở region khác** chỉ nhờ ZRS.
- Nếu toàn bộ primary region mất khả năng cung cấp dịch vụ, ZRS không tự giải quyết yêu cầu DR đa region.
- Không phải region, account kind, access tier hoặc dịch vụ lưu trữ nào cũng cho phép cấu hình ZRS.
- Dù storage chịu lỗi zone, workload vẫn có thể ngừng hoạt động nếu VM, database, DNS hoặc mạng không được thiết kế đa zone.

## 5. GRS — Geo-Redundant Storage

### 5.1. Cơ chế hoạt động

GRS kết hợp:

1. **LRS ở primary region:** dữ liệu được sao chép đồng bộ thành ba bản sao trong một vị trí vật lý.
2. **Geo-replication bất đồng bộ:** thay đổi từ primary được chuyển sang secondary region do Azure xác định.
3. **LRS ở secondary region:** dữ liệu nhận được tiếp tục có các bản sao LRS tại secondary.

Như vậy GRS dùng **sáu bản sao** về mặt mô hình (ba ở primary và ba ở secondary) khi sao chép địa lý đã hoàn tất.

~~~mermaid
flowchart LR
    A["Ứng dụng ghi"] --> P["Primary region<br/>LRS: 3 bản sao"]
    P -. "Geo replication<br/>bất đồng bộ" .-> S["Secondary region<br/>LRS: 3 bản sao"]
~~~

**Điều cốt lõi:** một lệnh ghi được primary xác nhận thành công **không có nghĩa** secondary đã nhận được ngay.

### 5.2. Giá trị của GRS

GRS cung cấp thêm khả năng bảo toàn dữ liệu trước **sự cố nghiêm trọng ở primary region**, vì có bản sao tại một khu vực thứ hai.

Phù hợp khi:

- Có yêu cầu DR đa region.
- Rủi ro mất primary region được xem là đáng kể.
- Workload chấp nhận một mức RPO khác 0 do replication bất đồng bộ hoặc có biện pháp bổ sung cho dữ liệu cực kỳ quan trọng.
- Khả năng chống lỗi zone ở primary không phải yêu cầu bắt buộc, hoặc đã được xử lý ở lớp kiến trúc khác.

### 5.3. GRS không tự tạo ứng dụng active–active

Với **GRS thông thường**, ứng dụng không tự được phép ghi vào secondary. Secondary là bản sao phục vụ khôi phục theo cơ chế dịch vụ, chứ không phải một Storage Account ghi độc lập mà ứng dụng có thể xem là multi-master.

Khi primary region ngừng hoạt động, cần xem xét **quy trình failover** theo loại Storage Account, khả năng hỗ trợ và cơ chế điều phối của Azure. Có thể có gián đoạn dịch vụ, thay đổi vai trò region và nguy cơ mất những ghi chưa kịp tới secondary.

Nếu ứng dụng đòi hỏi phục vụ người dùng liên tục ở hai region, GRS **một mình** chưa đủ: cần thiết kế compute, DNS/traffic routing, identity, database, kết nối và quản lý trạng thái phù hợp.

## 6. GZRS — Geo-Zone-Redundant Storage

### 6.1. Cơ chế hoạt động

GZRS kết hợp hai tầng bảo vệ:

- **ZRS tại primary region:** dữ liệu đồng bộ qua các availability zone của region chính.
- **Geo-replication bất đồng bộ** sang secondary region.
- **LRS tại secondary region:** bản sao thứ hai được lưu theo cơ chế local redundancy trong region phụ.

~~~mermaid
flowchart LR
    C["Ứng dụng"] --> P["Primary region<br/>ZRS: Zone 1, 2, 3"]
    P -. "Geo replication<br/>bất đồng bộ" .-> S["Secondary region<br/>LRS: 3 bản sao"]
~~~

GZRS vì vậy kết hợp khả năng chịu lỗi **một zone ở primary** với sự tồn tại của **bản sao địa lý** khi có thảm họa region.

### 6.2. Khi nào chọn GZRS?

GZRS phù hợp với workload quan trọng khi cả hai yêu cầu sau cùng tồn tại:

1. Muốn tăng khả năng tiếp tục truy cập dữ liệu nếu một availability zone ở primary không hoạt động.
2. Cần một bản sao tại secondary region để xây dựng kế hoạch khôi phục thảm họa.

Ví dụ: hệ thống đặt hàng production trải trên nhiều zone và lưu tài liệu giao dịch, đồng thời tổ chức muốn có khả năng DR đa region. GZRS thường là ứng viên tốt hơn LRS hoặc GRS nếu primary zone resilience là điều kiện bắt buộc.

### 6.3. Giới hạn cần ghi nhớ

- Chỉ **primary** có ZRS trong cơ chế GZRS thông dụng; **secondary** sử dụng LRS, không phải ZRS.
- Replication giữa hai region vẫn **bất đồng bộ**, nên nguy cơ mất dữ liệu khi failover vùng vẫn tồn tại.
- Không phải mọi region và Storage Account đều hỗ trợ GZRS/RA-GZRS.
- Chi phí có thể cao hơn các lựa chọn chỉ bảo vệ một khu vực; cần so sánh bảng giá thực tế theo SKU và dịch vụ.

## 7. Bảng so sánh LRS, ZRS, GRS, GZRS

| Đặc tính | LRS | ZRS | GRS | GZRS |
|---|---|---|---|---|
| Phạm vi primary | Một vị trí vật lý | Ba availability zone | Một vị trí vật lý | Ba availability zone |
| Cơ chế tại primary | Đồng bộ, 3 bản sao | Đồng bộ qua zone | Đồng bộ, 3 bản sao | Đồng bộ qua zone |
| Có secondary region | Không | Không | Có | Có |
| Kiểu bản sao secondary | — | — | LRS | LRS |
| Đồng bộ giữa region | — | — | **Bất đồng bộ** | **Bất đồng bộ** |
| Chịu lỗi một zone tại primary theo thiết kế | Không phải mục tiêu của LRS | Có | Không phải mục tiêu của primary LRS | Có |
| Có bản sao cho DR cấp region | Không | Không | Có | Có |
| Rủi ro mất ghi chưa geo-replicate khi failover | Không áp dụng geo | Không áp dụng geo | Có | Có |
| Hỗ trợ đọc secondary trực tiếp theo cấu hình cơ bản | Không | Không | Không; xem RA-GRS | Không; xem RA-GZRS |
| Trường hợp thường gặp | Lab, dữ liệu tái tạo được | Production ưu tiên chịu lỗi zone | DR đa region | Production cần zone + DR region |

**Cần hiểu đúng:** “có bản sao cho DR cấp region” không đồng nghĩa “region còn lại luôn sẵn sàng ghi ngay” hoặc “RPO bằng 0”. Bảng mô tả mục tiêu bảo vệ dữ liệu, không cam kết tình trạng của toàn bộ ứng dụng.

### 7.1. Nếu xảy ra các dạng sự cố khác nhau

| Loại sự cố | LRS | ZRS | GRS | GZRS |
|---|---|---|---|---|
| Một ổ đĩa hoặc phần cứng lưu trữ hỏng | Có bản sao cục bộ | Có bản sao qua zone | Có bản sao cục bộ và địa lý | Có bản sao qua zone và địa lý |
| Một availability zone mất hoạt động | Không có thiết kế cross-zone | Có khả năng chịu lỗi theo ZRS | Primary vẫn là LRS tại một vị trí | Có khả năng chịu lỗi tại primary theo ZRS |
| Toàn bộ primary region bị sự cố nghiêm trọng | Không có secondary | Không có secondary | Có dữ liệu sao chép ở region phụ, cần quy trình failover | Có dữ liệu sao chép ở region phụ, cần quy trình failover |
| Tệp bị xóa nhầm hoặc ghi đè bằng nội dung sai | Không bảo vệ chỉ bằng redundancy | Tương tự | Lỗi logic có thể được sao chép | Tương tự |
| Danh tính bị chiếm quyền và xóa dữ liệu | Cần kiểm soát/backup riêng | Cần kiểm soát/backup riêng | Cần kiểm soát/backup riêng | Cần kiểm soát/backup riêng |

## 8. RA-GRS và RA-GZRS: đọc ở secondary

Trong những loại tài khoản và dịch vụ hỗ trợ, Azure có hai biến thể:

- **RA-GRS — Read-Access Geo-Redundant Storage.**
- **RA-GZRS — Read-Access Geo-Zone-Redundant Storage.**

Chữ **RA** nghĩa là **read access** tại secondary endpoint, không có nghĩa ứng dụng được ghi bình thường vào secondary khi primary vẫn đang hoạt động.

~~~mermaid
flowchart LR
    W["Client ghi"] --> P["Primary endpoint<br/>Read / Write"]
    P -. "Async replication" .-> S["Secondary endpoint<br/>Read-only"]
    R["Client đọc dự phòng"] --> S
~~~

### 8.1. Khi nào cần RA?

RA-GRS hoặc RA-GZRS có thể hữu ích khi ứng dụng có một số tác vụ **đọc được dữ liệu cũ** và muốn tiếp tục truy vấn bản sao secondary trong các tình huống phù hợp, ví dụ:

- Đọc tài liệu lưu trữ hoặc thông tin ít thay đổi.
- Thử nghiệm đường đọc dự phòng mà không thực hiện account failover.
- Đọc dữ liệu khi primary tạm thời không khả dụng, nếu secondary endpoint còn hoạt động và được loại dịch vụ hỗ trợ.

Tuy nhiên, bản sao secondary **có thể chậm hơn primary**. Không nên dùng secondary cho nghiệp vụ yêu cầu **read-after-write consistency** ngay sau khi ghi vào primary.

### 8.2. Endpoint của secondary

Với Blob Storage, endpoint secondary thường có dạng:

~~~text
Primary:   https://<storage-account-name>.blob.core.windows.net/
Secondary: https://<storage-account-name>-secondary.blob.core.windows.net/
~~~

Đây là ví dụ mẫu của **Blob service**, không phải mọi loại tài nguyên Storage đều dùng cùng hostname. Trước khi triển khai, cần kiểm tra endpoint được trả về cho loại tài khoản và dịch vụ, quyền truy cập mạng, xác thực và các điều kiện hỗ trợ tại secondary.

RA không biến replication thành đồng bộ, và không tự chuyển read traffic của ứng dụng. Ứng dụng hoặc SDK phải có logic chọn secondary/đọc dự phòng đúng nghiệp vụ. Nếu dùng endpoint phụ, ứng dụng nên hiển thị hoặc xử lý khả năng dữ liệu chưa mới nhất.

### 8.3. GRS khác RA-GRS thế nào?

GRS vẫn duy trì bản sao địa lý nhưng không cung cấp quyền đọc trực tiếp thông thường tại secondary khi chưa có failover. RA-GRS bổ sung khả năng đọc secondary theo điều kiện hỗ trợ. Tương tự, GZRS và RA-GZRS khác nhau ở quyền đọc secondary, không phải ở việc secondary sử dụng ZRS.

## 9. Geo-replication, replication lag và failover

### 9.1. Hành trình của một thao tác ghi

Giả sử người dùng tải lên tệp **invoice-1042.pdf**:

1. Client gửi yêu cầu ghi đến primary endpoint.
2. Azure xác nhận khi bản ghi đáp ứng điều kiện sao chép **đồng bộ tại primary** (LRS hoặc ZRS tùy SKU).
3. Quá trình **geo-replication bất đồng bộ** tiếp tục đưa dữ liệu sang secondary nếu dùng GRS/GZRS.
4. Khi secondary nhận và áp dụng thay đổi, bản sao địa lý mới có trạng thái gần với primary hơn.

Nếu primary region bị mất hoàn toàn ngay sau bước 2, tệp có thể **chưa** nằm tại secondary. Rủi ro này là lý do không được coi GRS/GZRS là giải pháp RPO=0 cho mọi sự cố region.

### 9.2. Last Sync Time

Azure cung cấp thông tin trạng thái geo-replication, trong đó có **Last Sync Time** khi áp dụng. Thông số này giúp nhận biết mốc dữ liệu đã đồng bộ theo cách dịch vụ công bố.

Khi diễn giải:

- Nếu mốc đồng bộ gần hiện tại, lượng dữ liệu có nguy cơ chưa tới secondary có thể nhỏ hơn.
- Nếu mốc cách xa hiện tại, cần cảnh giác replication lag hoặc trạng thái sao chép gặp vấn đề.
- **Last Sync Time không phải SLA RPO cố định** và không bảo đảm chính xác lượng dữ liệu có thể mất trong mọi kịch bản.
- Tính khả dụng của trường trạng thái phụ thuộc loại redundancy, dịch vụ và khả năng hiển thị tương ứng.

Để đánh giá RPO thực tế, ngoài mốc đồng bộ cần theo dõi lưu lượng ghi, cơ chế ứng dụng, ghi log giao dịch và cách đối chiếu dữ liệu sau failover.

### 9.3. Account failover là gì?

**Failover** thay đổi vai trò primary sang region phụ trong những loại tài khoản, dịch vụ và tình huống được Azure hỗ trợ. Mục tiêu là cho phép ứng dụng tiếp tục sử dụng Storage Account sau một sự cố ở primary.

Các điểm quan trọng:

1. Failover **không phải thao tác đọc secondary** qua RA endpoint.
2. Failover có thể khiến dữ liệu ghi chưa kịp geo-replicate **không có ở primary mới**.
3. Thời gian chuyển đổi, khả năng dùng lại endpoint, DNS caching và client retry cần được dự tính.
4. Sau failover, **cấu hình redundancy có thể thay đổi**; phải kiểm tra trạng thái mới và kế hoạch tái thiết lập geo-redundancy theo tài liệu.
5. Không phải mọi kiểu Storage Account hoặc mọi tính năng đều hỗ trợ các loại failover giống nhau.
6. Một số tình huống có cơ chế planned failover hoặc unplanned failover; yêu cầu primary còn khả dụng, khả năng tránh mất dữ liệu và hệ quả vận hành khác nhau. Phải đối chiếu tài liệu hiện hành trước khi chọn.

Một lựa chọn DR tốt phải có **runbook** rõ ràng, không phải chỉ có lựa chọn “GRS” ở màn hình tạo tài khoản.

### 9.4. Điều gì xảy ra với ứng dụng khi failover?

Ngay cả khi lưu trữ chuyển vai trò thành công, ứng dụng có thể vẫn lỗi vì:

- VM, AKS, App Service hoặc database của ứng dụng chưa được phục hồi tại region mới.
- DNS, private endpoint, firewall, VNet và routing chưa sẵn sàng.
- Client còn cache thông tin endpoint cũ hoặc chưa có retry/backoff phù hợp.
- Danh tính, managed identity, RBAC, key/secret và phụ thuộc ứng dụng chưa được cấu hình cho DR.
- Dữ liệu của Storage Account và database có **mốc khôi phục khác nhau**, dẫn đến sai lệch nghiệp vụ.

Vì vậy, hãy thiết kế **khôi phục toàn bộ workload** chứ không chỉ chọn redundancy cho storage.

## 10. Redundancy không phải backup

Đây là phần thường bị nhầm lẫn nhất khi đưa hệ thống lên cloud.

**Replication** nhằm bảo vệ trước lỗi hạ tầng hoặc duy trì bản sao gần hiện tại. **Backup** nhằm cho phép khôi phục dữ liệu về phiên bản/thời điểm trước, phù hợp với rủi ro xóa nhầm, ghi đè, mã độc hoặc lỗi ứng dụng.

Ví dụ:

- Nhân viên xóa nhầm một blob.
- Một lỗi trong API ghi đè tệp hợp lệ bằng nội dung rỗng.
- Một danh tính bị xâm nhập xóa hoặc sửa dữ liệu qua API có quyền.
- Đoạn mã triển khai thay đổi metadata và lifecycle không đúng.

LRS, ZRS, GRS và GZRS **không tự khôi phục phiên bản cũ** trong những trường hợp này. Thay đổi logic có thể được sao chép sang những bản sao khác, kể cả secondary region.

### 10.1. Biện pháp bổ sung cho Blob Storage

Tùy loại dữ liệu và dịch vụ, có thể xem xét:

| Biện pháp | Mục tiêu |
|---|---|
| Blob soft delete | Cho phép khôi phục blob bị xóa trong thời gian lưu giữ được cấu hình |
| Container soft delete | Hỗ trợ khôi phục container bị xóa trong thời gian phù hợp |
| Blob versioning | Giữ các phiên bản blob để có thể quay lại bản cũ theo quy tắc |
| Point-in-time restore | Khôi phục dữ liệu tới thời điểm trước trong phạm vi dịch vụ/điều kiện hỗ trợ |
| Immutable storage | Bảo vệ dữ liệu khỏi xóa/sửa trái phép trong thời hạn lưu giữ đã cấu hình |
| Backup độc lập | Có bản phục hồi được quản lý với mục tiêu retention và phạm vi cô lập phù hợp |
| Least privilege và logging | Hạn chế quyền xóa/sửa và điều tra các thay đổi bất thường |

Không phải mọi tính năng bảo vệ dữ liệu đều khả dụng trên mọi loại Blob, account kind, redundancy hay access tier. Thiết kế phải căn cứ dịch vụ đang dùng và mục tiêu phục hồi; tránh mặc định tính năng đã bật chỉ vì Storage Account tồn tại.

### 10.2. Ví dụ một chính sách dữ liệu

Ứng dụng Orders lưu hóa đơn cần:

- Chịu được lỗi một availability zone.
- Có bản sao cho DR cấp region.
- Khôi phục tệp bị xóa nhầm trong thời gian retention nội bộ.
- Có bằng chứng audit và hạn chế ai được quyền xóa.

**GZRS hoặc RA-GZRS** có thể đáp ứng phần chịu lỗi hạ tầng, trong khi **soft delete/versioning/backup/immutability và RBAC** xử lý phần khôi phục phiên bản và rủi ro xóa/sửa. Không thể thay thế toàn bộ bằng một lựa chọn redundancy duy nhất.

## 11. Lựa chọn mô hình theo yêu cầu nghiệp vụ

Hãy quyết định theo ba câu hỏi lớn:

1. **Sự cố lớn nhất cần chịu là gì?** Ổ đĩa, vị trí lưu trữ, một availability zone hay cả region?
2. **Workload có thể chấp nhận mất bao nhiêu dữ liệu và ngừng hoạt động bao lâu?** Đặt RPO/RTO cụ thể.
3. **Dịch vụ/region có hỗ trợ SKU đó và chi phí hợp lý không?**

### 11.1. Cây quyết định nhanh

~~~mermaid
flowchart TD
    A["Bắt đầu: yêu cầu lưu trữ"] --> B{"Cần bản sao<br/>ở region thứ hai?"}
    B -->|Không| C{"Cần chịu lỗi<br/>availability zone?"}
    C -->|Không| L["Xem xét LRS"]
    C -->|Có| Z["Xem xét ZRS"]
    B -->|Có| D{"Primary cần<br/>chịu lỗi zone?"}
    D -->|Không| G["Xem xét GRS"]
    D -->|Có| GZ["Xem xét GZRS"]
    G --> E{"Cần đọc secondary<br/>trước failover?"}
    GZ --> E
    E -->|Có| RA["Xem xét biến thể RA-GRS / RA-GZRS"]
    E -->|Không| F["Giữ GRS / GZRS"]
~~~

Cây này **không thay thế kiểm tra hỗ trợ SKU, yêu cầu compliance, RPO/RTO và chi phí**. Nếu cần RPO=0 qua toàn bộ sự cố region hoặc ghi active–active đa region, phải thiết kế thêm giải pháp ở lớp dữ liệu/ứng dụng phù hợp, thay vì coi GRS/GZRS đơn lẻ là đủ.

### 11.2. Bốn tình huống minh họa

| Workload | Yêu cầu | Lựa chọn gợi ý | Lý do |
|---|---|---|---|
| Cache build có thể tái tạo | Chi phí thấp, không cần DR địa lý | **LRS** | Bản sao cục bộ đủ theo mức rủi ro chấp nhận |
| Tệp đính kèm của ứng dụng chạy đa zone | Bảo vệ trước lỗi một zone, không cần region DR | **ZRS** | Sao chép đồng bộ giữa các zone |
| Dữ liệu báo cáo cần bản sao ở region phụ | Có DR đa region, chấp nhận lag địa lý | **GRS** | Sao chép bất đồng bộ sang secondary region |
| Tài liệu giao dịch của hệ thống Orders | Cần zone resilience và DR region | **GZRS** | Kết hợp ZRS primary với bản sao địa lý |

Đối với hệ thống giao dịch có RPO rất nghiêm ngặt, phải bổ sung cơ chế ứng dụng/database/backup để thỏa mục tiêu. Không nói rằng “GZRS bảo đảm không mất giao dịch” trong mọi thảm họa.

## 12. Khả năng hỗ trợ theo region, loại tài khoản và dịch vụ

Trước khi tạo Storage Account, cần phân biệt **redundancy của Storage Account** với các cơ chế độ bền của sản phẩm lưu trữ khác.

### 12.1. Standard GPv2 không đồng nghĩa mọi dịch vụ đều có cùng hỗ trợ

Đối với **general-purpose v2 Storage Account (StorageV2)**, các lựa chọn Standard redundancy thường được sử dụng cho Azure Blob Storage và những dịch vụ được hỗ trợ. Nhưng:

- Một số access tier, account kind hoặc tính năng có hạn chế khi kết hợp với ZRS, GZRS, RA variants.
- **Azure Files** có điều kiện hỗ trợ SKU và tính năng riêng.
- **Premium storage** có danh sách SKU khác và có thể không cung cấp toàn bộ bốn mô hình như tài khoản Standard.
- **Managed disks** là loại tài nguyên khác với Storage Account GPv2; không suy ra redundancy hoặc khả năng failover của đĩa quản lý từ bảng Blob Storage.
- Những dịch vụ có cơ chế lưu dữ liệu riêng có thể công bố chính sách redundancy riêng.

Khi gặp lỗi “SKU not available”, hãy kiểm tra **region, account kind, dịch vụ, access tier, tính năng hiện có và subscription** trước khi thay đổi kiến trúc. Không chuyển sang một SKU thấp hơn một cách tự động nếu điều đó vi phạm yêu cầu DR.

### 12.2. Region chính và region phụ

Với GRS/GZRS, Azure dùng một secondary region theo cách dịch vụ hỗ trợ. Khu vực phụ có thể có ràng buộc về dữ liệu, tuân thủ hoặc thiết kế nghiệp vụ. Đánh giá:

- Yêu cầu data residency và jurisdiction.
- Khả năng mạng và khôi phục ứng dụng ở secondary.
- Phí truyền dữ liệu, lưu trữ, phục hồi và lưu lượng qua region.
- Vị trí hệ thống backup hoặc hệ thống phân tích dữ liệu.
- Khả năng hỗ trợ RA hoặc customer-managed failover cho account kind cụ thể.

Không phải mọi tổ hợp primary region và yêu cầu residency đều phù hợp với lựa chọn geo-redundancy mặc định. Hãy xác nhận thứ tự ưu tiên giữa yêu cầu pháp lý, độ bền và DR.

## 13. Thực hành Azure CLI: tạo và kiểm tra Storage Account

**Môi trường giả định:** bạn có subscription được phép dùng cho lab, Azure CLI đã đăng nhập, resource group chưa có dữ liệu production, và muốn thử một Storage Account loại **StorageV2**. Các lệnh dưới đây là ví dụ Bash/Azure Cloud Shell; **không tự thực thi các lệnh từ nội dung bài học trên tài khoản thật nếu chưa kiểm tra chi phí và quyền**.

### 13.1. Tạo resource group cho lab

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-storage-redundancy-lab"
LOCATION="southeastasia"

az group create \
  --name "$RG" \
  --location "$LOCATION"
~~~

Resource group chỉ là vùng quản lý tài nguyên. Đặt region cho resource group **không buộc** mọi tài nguyên bên trong phải đặt đúng region đó; hãy chỉ định region rõ ràng cho Storage Account.

### 13.2. Tạo Storage Account với LRS

Tên Storage Account phải **duy nhất toàn cầu**, dài từ 3 đến 24 ký tự và chỉ gồm chữ thường cùng chữ số. Hãy thay tên minh họa bằng giá trị hợp lệ chưa được sử dụng.

~~~bash
STORAGE_NAME="<yourgloballyuniquestorageaccount>"

az storage account create \
  --name "$STORAGE_NAME" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --kind StorageV2 \
  --sku Standard_LRS
~~~

Ví dụ dùng **Standard_LRS** để tránh yêu cầu zone/geo khi học thao tác cơ bản. Khi tạo một Storage Account mới khác trong region và với dịch vụ hỗ trợ, bạn có thể lựa chọn các SKU tương ứng, chẳng hạn:

~~~text
Standard_LRS
Standard_ZRS
Standard_GRS
Standard_GZRS
~~~

Đối với biến thể cho phép đọc secondary, tên SKU liên quan thường là **Standard_RAGRS** hoặc **Standard_RAGZRS** theo cú pháp Azure CLI/API. Đừng suy đoán sự hỗ trợ chỉ từ tên SKU: hãy xác minh region, tính năng và loại tài khoản.

### 13.3. Đọc cấu hình redundancy đã được áp dụng

~~~bash
az storage account show \
  --name "$STORAGE_NAME" \
  --resource-group "$RG" \
  --query "{name:name,kind:kind,sku:sku.name,location:primaryLocation,secondary:secondaryLocation,primaryStatus:statusOfPrimary,secondaryStatus:statusOfSecondary}" \
  --output json
~~~

Ví dụ đầu ra **minh họa, không phải kết quả chạy thật**:

~~~json
{
  "name": "storderslabexample",
  "kind": "StorageV2",
  "sku": "Standard_LRS",
  "location": "southeastasia",
  "secondary": null,
  "primaryStatus": "available",
  "secondaryStatus": null
}
~~~

Với LRS, không có secondary region từ geo-redundancy. Nếu tạo GRS/GZRS, trường secondary và trạng thái có thể hiển thị thông tin tương ứng tùy dịch vụ và thời điểm kiểm tra.

Kết quả này xác minh cấu hình quản lý, **không kiểm chứng rằng ứng dụng đã có backup hoặc đã được thử failover**.

### 13.4. Liệt kê tài khoản trong resource group

~~~bash
az storage account list \
  --resource-group "$RG" \
  --query "[].{name:name,sku:sku.name,kind:kind,primary:primaryLocation,secondary:secondaryLocation}" \
  --output table
~~~

Bảng trên hữu ích khi kiểm toán sự phân bố redundancy theo nhiều ứng dụng. Trong production, có thể kết hợp tag **application**, **environment**, **owner**, **dataClassification** với Azure Policy hoặc script kiểm tra chuẩn tổ chức.

### 13.5. Đổi redundancy có phải một lệnh update đơn giản?

**Không nên giả định như vậy.** Khả năng chuyển đổi phụ thuộc tổ hợp nguồn–đích, region, account type, dịch vụ, tính năng đang bật và điều kiện di chuyển dữ liệu.

Một số thay đổi redundancy được phép thực hiện trực tiếp ở những tình huống hỗ trợ. Một số thay đổi khác yêu cầu tiến trình migration, kiểm tra điều kiện hoặc tạo Storage Account mới rồi chuyển dữ liệu theo kế hoạch.

Trước khi chuyển LRS → ZRS, GRS → GZRS hoặc bất kỳ kiểu nào:

1. Kiểm tra **đường chuyển đổi được hỗ trợ** với loại tài khoản và region cụ thể.
2. Xem quy trình migration, thời gian, giới hạn, điều kiện về object/feature.
3. Kiểm tra ứng dụng, private endpoint, identity, access policy, lifecycle và backup.
4. Xem khả năng ảnh hưởng availability, giá mới và rollback.
5. Thực hiện trong môi trường thử nghiệm hoặc theo change window đã duyệt.
6. Xác minh SKU và trạng thái replication sau khi chuyển đổi.

Không chạy lệnh **az storage account update --sku** trên production chỉ dựa trên giả định rằng mọi cặp SKU đều chuyển đổi tức thời hoặc không ảnh hưởng dịch vụ.

## 14. Khai báo redundancy bằng Bicep

IaC giúp cấu hình redundancy nhất quán khi triển khai qua pipeline. Mẫu Bicep dưới đây tạo Storage Account mới, chọn SKU qua tham số, đồng thời đặt một số tùy chọn bảo mật cơ bản.

~~~bicep
@description('Tên Storage Account hợp lệ và duy nhất toàn cầu')
param storageAccountName string

@description('Azure region của Storage Account')
param location string = resourceGroup().location

@description('Kiểu redundancy Standard của tài khoản')
@allowed([
  'Standard_LRS'
  'Standard_ZRS'
  'Standard_GRS'
  'Standard_GZRS'
])
param redundancy string = 'Standard_ZRS'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: redundancy
  }
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
  tags: {
    application: 'orders'
    environment: 'lab'
  }
}

output storageAccountId string = storage.id
~~~

Các lựa chọn **@allowed** là ràng buộc của **ví dụ**, không phải bảng liệt kê đầy đủ SKU Azure. Tùy loại workload, hãy kiểm tra điều kiện hỗ trợ và yêu cầu bảo mật khác như Key Vault, network access, private endpoint và identity.

Lưu nội dung vào **storage-redundancy.bicep**, sau đó xem trước thay đổi:

~~~bash
az deployment group what-if \
  --resource-group "$RG" \
  --template-file storage-redundancy.bicep \
  --parameters storageAccountName="<uniquename>" redundancy="Standard_ZRS"
~~~

Sau khi kiểm tra region hỗ trợ và kết quả what-if, triển khai trong lab:

~~~bash
az deployment group create \
  --resource-group "$RG" \
  --name "deploy-storage-redundancy-lab" \
  --template-file storage-redundancy.bicep \
  --parameters storageAccountName="<uniquename>" redundancy="Standard_ZRS"
~~~

**Cảnh báo về cấu hình hiện hữu:** mẫu Bicep là ví dụ để tạo mới. Nếu trỏ vào Storage Account đang chạy, deployment có thể cập nhật thuộc tính ngoài ý muốn hoặc bị từ chối do thay đổi SKU không hỗ trợ. Hãy quản lý **toàn bộ trạng thái mong muốn** của tài nguyên, kiểm tra what-if và chạy quy trình thay đổi có kiểm soát.

## 15. Thực hành qua Azure Portal

### 15.1. Khi tạo Storage Account

1. Mở Azure Portal và chọn **Storage accounts → Create**.
2. Chọn đúng subscription, resource group và Storage Account name.
3. Chọn primary region phù hợp với nơi chạy workload và yêu cầu residency.
4. Chọn loại tài khoản, performance tier và **redundancy** trong những tùy chọn Portal cho phép.
5. Đọc mô tả về LRS, ZRS, GRS, GZRS và các tùy chọn read-access geo-redundancy nếu có.
6. Kiểm tra tab về bảo mật, networking, bảo vệ dữ liệu và mã hóa theo chính sách tổ chức.
7. Xem cấu hình trong bước review, kiểm tra chi phí/giới hạn rồi triển khai.
8. Sau khi tài nguyên được tạo, mở Storage Account để kiểm tra **Redundancy** và trạng thái liên quan.

Tên và vị trí các mục có thể thay đổi theo phiên bản Portal. Nếu một SKU không xuất hiện, nguyên nhân có thể là loại tài khoản, region hoặc cấu hình chưa hỗ trợ; đừng suy luận rằng Azure đã loại bỏ toàn bộ tính năng đó.

### 15.2. Theo dõi geo-replication

Với tài khoản dùng GRS/GZRS hoặc RA variants, tìm trạng thái replication, primary/secondary region và thông tin **Last Sync Time** nếu Portal hiển thị. Dùng chúng để:

- Phát hiện replication lag bất thường.
- Ghi nhận bằng chứng trong diễn tập DR.
- Xác nhận vị trí bản sao phù hợp yêu cầu dữ liệu.
- Hỗ trợ quyết định rủi ro trước một thao tác failover được kiểm soát.

Không dùng một ảnh chụp trạng thái “available” để kết luận RPO, RTO đã được kiểm thử. Phải có thử nghiệm phục hồi thực tế và xác minh dữ liệu.

## 16. Kịch bản DR: primary region gặp sự cố

Giả sử ứng dụng Orders sử dụng **GZRS** cho Blob Storage ở primary region. Một sự cố region nghiêm trọng xảy ra và hoạt động lưu trữ primary bị gián đoạn.

### 16.1. Trước khi có sự cố

Nhóm vận hành cần chuẩn bị:

1. Xác nhận Storage Account hỗ trợ cơ chế failover dự kiến.
2. Hiểu tài nguyên nào sẽ tiếp tục dùng được khi lỗi **zone**, tài nguyên nào cần **region failover**.
3. Thiết kế compute, networking, identity, DNS và các phụ thuộc ứng dụng ở region dự phòng.
4. Xác định RPO/RTO nghiệp vụ và mức replication lag chấp nhận.
5. Bật monitoring, logging và bảo vệ dữ liệu chống lỗi logic.
6. Lập runbook diễn tập, rollback/recovery và quy trình phê duyệt failover.
7. Dự toán phí vận hành của hai vùng và chi phí phục hồi.

### 16.2. Khi xảy ra lỗi một availability zone

Với ZRS hoặc primary của GZRS, Storage Account được thiết kế để chịu sự cố một zone trong phạm vi hỗ trợ. Tuy nhiên:

- Azure Storage có thể tiếp tục phục vụ yêu cầu nhưng ứng dụng vẫn có thể gián đoạn vì compute/database/network của chính ứng dụng.
- Phải kiểm tra telemetry của ứng dụng, timeout/retry, endpoint và vùng triển khai các thành phần khác.
- Không cần mặc định kích hoạt region failover chỉ vì một VM ở một zone bị lỗi.

### 16.3. Khi primary region không còn khả dụng

Với GRS/GZRS:

1. Xác minh phạm vi sự cố và các thông báo dịch vụ chính thức.
2. Thu thập thời điểm ghi gần nhất ở primary, thông tin Last Sync Time nếu có và trạng thái geo-replication.
3. Ước lượng rủi ro mất dữ liệu chưa tới secondary.
4. Quyết định failover theo runbook, quyền và cơ chế mà loại tài khoản hỗ trợ.
5. Phối hợp chuyển compute, ứng dụng, mạng, DNS, identity và phụ thuộc dữ liệu.
6. Sau failover, xác minh dữ liệu, quyền đọc/ghi, integrity và tính nhất quán nghiệp vụ.
7. Kiểm tra redundancy đã trở thành loại nào sau failover và lập kế hoạch tái lập bảo vệ địa lý.
8. Ghi lại thời gian phục hồi thực tế, dữ liệu không sẵn có và các bước cải tiến.

**Không kích hoạt account failover cho Storage Account production như một bài thực hành đơn giản.** Đây có thể là thay đổi gây gián đoạn và mất dữ liệu chưa đồng bộ. Hãy diễn tập ở môi trường phù hợp với quy trình hỗ trợ hiện hành của Azure.

### 16.4. Vì sao phải đối chiếu dữ liệu sau failover?

Giả sử hệ thống có:

- Một cơ sở dữ liệu lưu trạng thái “đã tạo hóa đơn”.
- Một Blob Storage lưu tệp PDF của hóa đơn.
- Một hàng đợi xử lý các thao tác gửi email.

Nếu ba thành phần được sao chép và failover theo các cơ chế khác nhau, có thể xuất hiện trạng thái “database có bản ghi nhưng blob chưa tới region phụ”. Ứng dụng cần cơ chế đối chiếu, retry hoặc tái tạo tệp có idempotency phù hợp.

Redundancy của một Storage Account không tự bảo đảm **transactional consistency** giữa nhiều dịch vụ.

## 17. Bảo mật và tuân thủ khi chọn redundancy

Khi đánh giá mô hình sao chép dữ liệu, cần kết hợp yêu cầu lưu trữ với bảo mật:

### 17.1. Data residency

Geo-redundancy tạo bản sao dữ liệu ở một region khác theo cơ chế Azure. Trước khi bật, phải kiểm tra chính sách tổ chức về dữ liệu được phép sao chép ngoài khu vực chính, các nghĩa vụ pháp lý và việc lưu trữ thông tin nhạy cảm.

Nếu dữ liệu phải nằm trong một region cụ thể, việc dùng GRS/GZRS có thể không phù hợp; khi đó cần một phương án DR/backup đáp ứng yêu cầu lưu trữ và quản trị dữ liệu của tổ chức.

### 17.2. Mã hóa và quyền truy cập

Redundancy không thay thế:

- Azure RBAC và quyền data plane cho Blob, File, Queue hoặc Table phù hợp.
- Cơ chế xác thực, managed identity và quản lý secret.
- Mã hóa dữ liệu theo dịch vụ/loại khóa được chọn.
- HTTPS/TLS và kiểm soát public network access.
- Firewall, private endpoint, DNS và NSG theo kiến trúc được hỗ trợ.
- Audit log và quy trình review quyền.

Nếu ứng dụng cần truy cập secondary endpoint của RA-GRS/RA-GZRS, cần xác nhận chính sách mạng, token/quyền và cách ứng dụng truy cập dữ liệu ở secondary; đừng tự cho rằng một quy tắc mạng ở primary sẽ giải quyết tất cả tình huống.

### 17.3. Backup và chống mất dữ liệu do con người

Dữ liệu giao dịch có giá trị cao nên xem xét retention, versioning, soft delete, immutable storage, backup/restore và kiểm thử khôi phục. Trách nhiệm phê duyệt xóa hoặc thay đổi chính sách bảo vệ dữ liệu cần được phân tách khỏi tài khoản vận hành ứng dụng khi khả thi.

## 18. Chi phí và tác động đến hiệu năng

### 18.1. Chi phí không chỉ là dung lượng

Azure Storage có thể tính phí theo nhiều yếu tố:

- Dung lượng lưu trữ (GB/tháng) với từng redundancy/SKU và access tier.
- Số lượng và loại thao tác (đọc, ghi, liệt kê, thay đổi tier).
- Data retrieval và lifecycle trong những access tier tương ứng.
- Geo-replication hoặc chuyển đổi redundancy theo điều kiện dịch vụ.
- Lưu lượng network/egress và các tác vụ khôi phục.
- Backup, versioning, logging và monitoring được bật bổ sung.

Nhìn chung, phương án có phạm vi bảo vệ lớn hơn thường phát sinh chi phí lưu trữ cao hơn lựa chọn cục bộ tương ứng, nhưng **không nên viết một thứ tự giá tuyệt đối** áp dụng cho mọi region, tier và loại dịch vụ. Hãy dùng Azure Pricing Calculator và bảng giá của tài khoản/dịch vụ thật.

### 18.2. Tác động hiệu năng và latency

LRS và ZRS có phạm vi sao chép đồng bộ khác nhau; ZRS ghi qua các zone trong primary, vì vậy đặc tính latency cần được kiểm tra theo SLA và workload cụ thể. GRS/GZRS có replication bất đồng bộ sang secondary nên không đợi toàn bộ geo-replication hoàn thành mới xác nhận từng thao tác ghi primary.

Tuy nhiên, hiệu năng ứng dụng còn phụ thuộc vào:

- Kích thước request, concurrency và loại Blob/File/Queue/Table.
- Account limits, access tier và khả năng phân vùng dữ liệu.
- Vùng của compute so với vùng của Storage Account.
- Mạng, private endpoint, DNS và client retry.
- Số lượng request ghi nhỏ hoặc thao tác cập nhật metadata.

Đừng dựa vào tên redundancy để cam kết IOPS, latency hoặc throughput. Hãy benchmark theo loại dữ liệu, region và cấu hình thực tế.

## 19. Giám sát, kiểm thử và vận hành

Một Storage Account “đã chọn GZRS” không tự động đồng nghĩa bài toán khả dụng đã hoàn thành. Cần duy trì các kiểm tra vận hành.

### 19.1. Chỉ số nên theo dõi

| Tín hiệu | Mục tiêu |
|---|---|
| Availability và tỉ lệ request thành công | Phát hiện truy cập lưu trữ bị gián đoạn |
| Latency/end-to-end latency | Phát hiện độ trễ tăng bất thường |
| Server errors, throttling | Xác định lỗi nền tảng, client hoặc giới hạn dịch vụ |
| Storage capacity và transaction count | Theo dõi tăng trưởng và tải |
| Replication status / Last Sync Time (nếu có) | Quan sát rủi ro geo-replication lag |
| Thay đổi SKU, mạng và RBAC | Phát hiện thay đổi ngoài quy trình |
| Soft delete/versioning/backup status | Xác minh khả năng phục hồi lỗi logic |
| Cost Management | Kiểm soát phí phát sinh theo SKU và workload |

Có thể dùng Azure Monitor, diagnostic settings, Activity Log và những tính năng theo dõi phù hợp với Azure Storage. Chọn retention và nơi lưu log theo chính sách tổ chức; tránh dùng cùng một Storage Account không được bảo vệ để lưu toàn bộ bản sao duy nhất của nhật ký quan trọng.

### 19.2. Diễn tập lỗi theo mức độ an toàn

- **Unit/integration test:** thử ứng dụng xử lý lỗi 429/5xx, timeout và retry với exponential backoff phù hợp.
- **Zone failure planning:** xác nhận các thành phần của ứng dụng đều có kiến trúc zone-resilient nếu cần.
- **Read-secondary drill:** với RA-GRS/RA-GZRS và dịch vụ hỗ trợ, kiểm tra ứng dụng đọc secondary và phát hiện dữ liệu cũ.
- **Data recovery drill:** khôi phục một Blob đã xóa/phiên bản cũ bằng tính năng bảo vệ được bật.
- **DR runbook tabletop:** mô phỏng quyết định failover, các bước chuyển workload và đối chiếu dữ liệu.
- **Failover exercise có kiểm soát:** chỉ ở môi trường và account type phù hợp, theo hướng dẫn hiện hành và được phê duyệt.

Không cố mô phỏng lỗi region bằng cách xóa dữ liệu thật hoặc kích hoạt failover production ngoài quy trình thay đổi.

## 20. Những hiểu lầm thường gặp

1. **“LRS chỉ có một bản sao.”** Sai. LRS duy trì **ba bản sao**, nhưng ở **một vị trí vật lý**.
2. **“ZRS tự bảo vệ được khi toàn bộ region mất.”** Sai. ZRS bảo vệ qua zone **trong một region**, không có secondary region chỉ từ ZRS.
3. **“GRS đồng bộ dữ liệu ngay đến region phụ.”** Sai. Geo-replication là **bất đồng bộ**.
4. **“GZRS có ba zone ở cả primary và secondary.”** Sai trong mô hình thông dụng: ZRS ở primary, **LRS** ở secondary.
5. **“GRS cho phép ghi vào secondary bình thường.”** Sai. GRS không phải mô hình multi-master ghi hai region.
6. **“RA-GRS có nghĩa hai region có dữ liệu mới tức thì.”** Sai. RA cho phép đọc secondary trong phạm vi hỗ trợ nhưng dữ liệu có thể trễ.
7. **“Chọn geo-redundancy là không còn mất dữ liệu.”** Sai. Có nguy cơ mất các ghi chưa replicate khi failover vùng.
8. **“Có 6 bản sao là không cần backup.”** Sai. Lỗi xóa/ghi đè logic có thể được sao chép đến cả các bản sao.
9. **“Storage Account có GZRS thì ứng dụng tự có HA và DR.”** Sai. Compute, database, mạng, DNS, identity và runbook phải được thiết kế riêng.
10. **“Có thể chuyển mọi SKU chỉ bằng một lệnh.”** Sai. Hỗ trợ thay đổi redundancy phụ thuộc dịch vụ, region và tính năng đang dùng.
11. **“RPO của GRS luôn bằng 0.”** Sai. Không nên đưa cam kết như vậy cho geo-replication bất đồng bộ.
12. **“Càng nhiều bản sao thì luôn luôn tốt nhất.”** Chưa chắc. Cần cân bằng yêu cầu chịu lỗi, residency, region hỗ trợ, tính năng và ngân sách.

## 21. Checklist chọn redundancy cho production

- [ ] Xác định dữ liệu quan trọng hay có thể tái tạo.
- [ ] Xác định sự cố cần chịu: thiết bị, zone, region hay lỗi logic.
- [ ] Ghi rõ RPO/RTO và độ sẵn sàng mong muốn; không suy diễn từ tên SKU.
- [ ] Quyết định có cần bản sao ở secondary region không.
- [ ] Quyết định có cần chịu lỗi zone tại primary không.
- [ ] Đánh giá có cần **đọc secondary trước failover** hay không.
- [ ] Kiểm tra region chính/phụ, data residency và yêu cầu pháp lý.
- [ ] Xác nhận Storage Account kind, service, access tier và SKU được hỗ trợ.
- [ ] Đánh giá replication lag và nguy cơ mất dữ liệu khi unplanned failover.
- [ ] Có kế hoạch backup, retention, versioning, soft delete/immutability phù hợp.
- [ ] Có bản đồ phụ thuộc của compute, database, mạng, DNS và identity.
- [ ] Đã thiết kế quy trình DR, failover và tái lập geo-redundancy.
- [ ] Đã kiểm thử phục hồi dữ liệu và đánh giá tính nhất quán giữa các dịch vụ.
- [ ] Đã xem giá hiện hành, quota/giới hạn và chi phí vận hành.
- [ ] Đã đặt owner, giám sát và lịch rà soát cấu hình.

## 22. Bài tập thực hành

### Bài 1: Chọn redundancy theo kịch bản

Chọn phương án LRS/ZRS/GRS/GZRS cho bốn tình huống và giải thích:

1. Thư mục build artifact của hệ thống thử nghiệm có thể tạo lại.
2. Ứng dụng web sản xuất chạy đa zone, lưu ảnh người dùng, tổ chức không cần DR vùng.
3. Hệ thống lưu hồ sơ cần bản sao địa lý, primary zone resilience không bắt buộc.
4. Hệ thống hóa đơn production cần tiếp tục khi một zone hỏng và có kế hoạch DR region.

Với tình huống 4, giải thích vì sao vẫn cần versioning/backup và kiểm thử failover.

### Bài 2: So sánh GRS với GZRS

Vẽ hai sơ đồ luồng ghi từ ứng dụng đến primary và secondary, ghi rõ:

- Primary là LRS hay ZRS.
- Secondary dùng LRS.
- Đường nào đồng bộ, đường nào bất đồng bộ.
- Điều gì xảy ra với ghi chưa đến secondary khi phải failover đột ngột.

### Bài 3: RA-GRS có phục vụ dashboard được không?

Một dashboard thống kê đọc dữ liệu mỗi 15 phút. Nhóm vận hành cân nhắc RA-GRS để có thể đọc secondary. Hãy phân tích:

- Dữ liệu secondary có thể cũ ra sao.
- Trường hợp nào cho phép hiển thị số liệu cũ.
- Cách ứng dụng phát hiện và thông báo dữ liệu không mới.
- Khi nào cần thiết kế khả dụng ở mức ứng dụng thay vì chỉ dựa vào RA endpoint.

### Bài 4: Thao tác CLI trong lab

Tạo một Storage Account Standard_LRS trong resource group thực hành, sau đó:

1. Đọc lại SKU bằng **az storage account show**.
2. Ghi nhận primary region và trường secondary.
3. Mô tả các điều kiện cần kiểm tra trước khi muốn dùng ZRS/GZRS.
4. Thêm phương án bảo vệ Blob khỏi xóa nhầm theo khả năng dịch vụ.
5. Lập kế hoạch dọn tài nguyên lab mà không ảnh hưởng tài nguyên khác.

### Bài 5: Thiết kế DR toàn ứng dụng

Hệ thống Orders lưu trạng thái đơn hàng trong database và hóa đơn PDF trong Blob Storage GZRS. Khi region chính mất hoàn toàn, hãy liệt kê:

- Các bước phục hồi Storage Account.
- Những thành phần ứng dụng phải phục hồi riêng.
- Cách đo rủi ro mất dữ liệu chưa geo-replicate.
- Cách đối chiếu giao dịch có database record nhưng thiếu PDF.
- Điều kiện để tuyên bố workload đã phục hồi đạt RPO/RTO.

### Câu hỏi tự kiểm tra

1. Vì sao 3 bản sao LRS khác 3 bản sao ZRS?
2. ZRS có tạo secondary region không?
3. Có bao nhiêu bản sao trong mô hình GRS khi cả hai region đã đồng bộ hoàn tất?
4. Điểm khác biệt quan trọng nhất giữa GRS và GZRS tại primary là gì?
5. Vì sao geo-replication tạo nguy cơ mất các ghi gần nhất khi failover?
6. RA-GZRS khác GZRS ở điểm nào?
7. Khi nào Last Sync Time hữu ích, và vì sao không được coi nó là SLA RPO?
8. Vì sao redundancy không bảo vệ được trước xóa nhầm hoặc ransomware?
9. Tại sao phải kiểm tra account kind/region trước khi chọn SKU?
10. RTO của toàn hệ thống có được bảo đảm chỉ nhờ Storage Account GZRS không?

## 23. Tài liệu tham khảo

- [Azure Storage redundancy — Microsoft Learn](https://learn.microsoft.com/azure/storage/common/storage-redundancy)
- [Azure Storage account overview](https://learn.microsoft.com/azure/storage/common/storage-account-overview)
- [Azure Storage disaster recovery guidance](https://learn.microsoft.com/azure/storage/common/storage-disaster-recovery-guidance)
- [Initiate a storage account failover](https://learn.microsoft.com/azure/storage/common/storage-initiate-account-failover)
- [Change how a storage account is replicated](https://learn.microsoft.com/azure/storage/common/redundancy-migration)
- [Blob data protection overview](https://learn.microsoft.com/azure/storage/blobs/data-protection-overview)
- [Azure Storage pricing](https://azure.microsoft.com/pricing/details/storage/)
- [Azure Well-Architected Framework — Reliability](https://learn.microsoft.com/azure/well-architected/reliability/)

