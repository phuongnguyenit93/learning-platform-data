# Phạm vi tenant, địa lý, vùng triển khai và nơi lưu dữ liệu

Khi thiết kế một hệ thống NoSQL, câu hỏi “lưu dữ liệu theo khóa nào?” chưa đủ. Hệ thống còn cần biết **dữ liệu thuộc khách hàng/tổ chức nào (tenant)**, **người dùng và lưu lượng ở đâu**, **ứng dụng và cơ sở dữ liệu chạy tại vùng nào**, cùng **những nơi được phép lưu, xử lý, sao chép và khôi phục dữ liệu**.

Các quyết định này gắn trực tiếp với yêu cầu và tải dữ liệu: độ trễ, phân phối lưu lượng, khả năng cô lập khách hàng, phân vùng, replication, chi phí truyền dữ liệu, khả năng chịu lỗi và chính sách dữ liệu. Một thiết kế truy vấn rất nhanh trong một vùng có thể không đáp ứng yêu cầu khi người dùng trải trên nhiều châu lục hoặc khi một tenant bắt buộc giữ dữ liệu trong một phạm vi địa lý xác định.

Bài này trình bày cách xác định các phạm vi đó và chuyển chúng thành các quyết định thiết kế NoSQL có thể kiểm chứng.

## 1. Bốn khái niệm cần phân biệt

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Tenant scope – phạm vi tenant** | Ai sở hữu dữ liệu và ai được phép đọc, ghi, chia sẻ dữ liệu đó? | Công ty A chỉ xem đơn hàng của A, dù các công ty khác dùng chung một cluster |
| **Geographic scope – phạm vi địa lý** | Người dùng, thiết bị, nguồn phát sinh dữ liệu và thao tác truy cập phân bố ở đâu? | Phần lớn người dùng ở Đông Nam Á; thiết bị đo có mặt tại nhiều quốc gia |
| **Deployment region – vùng triển khai** | Ứng dụng, dịch vụ phụ trợ, database và các replica thực sự chạy ở vùng hạ tầng nào? | Dịch vụ API và database primary triển khai tại vùng R1 |
| **Data location / residency – nơi lưu dữ liệu** | Bản gốc, bản sao, backup, log, cache và bản xuất dữ liệu nằm ở đâu; có ràng buộc về vị trí không? | Hồ sơ của tenant B chỉ được lưu trong danh sách vùng được phê duyệt |

**Tenant không đồng nghĩa quốc gia.** Một tenant có thể có nhân viên ở nhiều quốc gia. Một quốc gia có thể chứa hàng nghìn tenant. **Vùng triển khai không đồng nghĩa nơi cư trú của người dùng**: người dùng tại Việt Nam có thể truy cập dịch vụ đặt ở một vùng khác. Và **đặt database chính trong một vùng không đủ để kết luận mọi dữ liệu đều ở vùng ấy** nếu hệ thống còn có replica, backup, log, chỉ mục tìm kiếm hoặc dịch vụ phân tích đặt nơi khác.

Hãy coi bốn khía cạnh là **bốn chiều của cùng một bài toán thiết kế**, không phải bốn nhãn thay thế cho nhau:

~~~mermaid
flowchart TB
    R["Yêu cầu sản phẩm, bảo mật, hợp đồng và tải thực tế"]
    R --> T["Phạm vi tenant<br/>Quyền sở hữu và cô lập"]
    R --> G["Phạm vi địa lý<br/>Nguồn truy cập và độ trễ"]
    R --> D["Vùng triển khai<br/>Tính sẵn sàng và topology"]
    R --> L["Nơi lưu dữ liệu<br/>Residency, replica, backup"]
    T --> N["Mô hình NoSQL: khóa, phân vùng, chỉ mục, replica"]
    G --> N
    D --> N
    L --> N
    N --> O["Vận hành: hiệu năng, chi phí, phục hồi, đối soát"]
~~~

### 1.1. Tenant là ranh giới nghiệp vụ và quyền truy cập

Trong phần mềm SaaS nhiều khách hàng, một **tenant** thường đại diện cho một tổ chức hoặc một không gian dữ liệu độc lập. Tenant có thể chứa nhiều người dùng, dự án, cửa hàng và ứng dụng con. Quan hệ này cần được xác định rõ trước khi chọn khóa lưu trữ.

Ví dụ:

~~~text
Tenant: T-100 (Công ty A)
  ├── User: U-1, U-2
  ├── Store: S-1, S-2
  └── Orders: O-1, O-2, ...

Tenant: T-200 (Công ty B)
  ├── User: U-8
  └── Orders: O-9, ...
~~~

Nếu một người có thể tham gia cả hai tenant, việc xác định tenant cho **từng request** vẫn cần tường minh. Chỉ có **userId** không phải lúc nào cũng đủ để xác định phạm vi dữ liệu.

### 1.2. Địa lý bao gồm cả nơi phát sinh tải lẫn yêu cầu xử lý

Phạm vi địa lý có ít nhất ba mặt:

- **Người dùng ở đâu:** ảnh hưởng round-trip time, thời gian phản hồi, khả năng truy cập từ các mạng khác nhau.
- **Dữ liệu phát sinh ở đâu:** thiết bị IoT, giao dịch tại chi nhánh, đơn hàng, vị trí GPS, file tải lên; ảnh hưởng nơi tiếp nhận ghi.
- **Dữ liệu được phép đi đâu:** chịu ràng buộc từ hợp đồng, phân loại dữ liệu, chính sách tổ chức và quy định áp dụng.

Ba mặt này có thể khác nhau. Ví dụ một nhân viên đang du lịch vẫn truy cập dữ liệu công ty được lưu trong vùng chính của tenant. Không nên tự động di chuyển hoặc sao chép dữ liệu công ty tới vùng gần vị trí tạm thời của nhân viên.

### 1.3. Region, zone và vị trí logic

**Region** là một khu vực triển khai do nhà cung cấp hạ tầng hoặc tổ chức tự định nghĩa. **Availability zone / failure domain** thường là miền lỗi riêng trong một region, nhưng mô hình cụ thể phụ thuộc nhà cung cấp. Một region có thể có nhiều zone; hai zone trong cùng region không tạo thành hệ thống đa region.

Ngoài vị trí vật lý còn có vị trí **logic**:

- **Home region:** vùng có thẩm quyền ghi chính của một tenant hoặc một tập dữ liệu.
- **Read region:** vùng có thể phục vụ đọc, có thể từ replica hoặc cache.
- **Allowed regions:** các vùng được chính sách cho phép chứa hoặc xử lý loại dữ liệu cụ thể.
- **Failover region:** vùng dự phòng được phép tiếp quản khi vùng chính lỗi.

Các khái niệm này phải được mô tả thành cấu hình và kiểm soát triển khai, không chỉ ghi trong tài liệu kiến trúc.

## 2. Thu thập yêu cầu về tenant, địa lý và tải dữ liệu

Trước khi thiết kế collection, bảng hay partition key, cần thu thập các câu trả lời dưới đây.

### 2.1. Hồ sơ tenant và độ lệch quy mô

| Câu hỏi | Tại sao cần hỏi? |
|---|---|
| Có bao nhiêu tenant hiện tại và dự kiến trong 1–3 năm? | Xác định số lượng cấu trúc lưu trữ, cơ chế provisioning và khả năng quản trị |
| Mỗi tenant có bao nhiêu bản ghi, bao nhiêu GB/TB? | Dự đoán dung lượng và quy mô partition |
| Tenant lớn nhất chiếm bao nhiêu phần trăm lưu lượng? | Phát hiện khả năng **noisy neighbor**, hot key, hot partition |
| Một tenant có bao nhiêu user hoạt động đồng thời? | Tính toán giới hạn kết nối, concurrency và quota |
| Có tenant cần cách ly riêng hoặc cấu hình vùng riêng không? | Chọn shared database, database riêng hoặc cluster riêng |
| Tenant có cần tự xuất, xóa, phục hồi hay chuyển vùng dữ liệu không? | Ảnh hưởng data ownership, backup và migration |

Không thể chỉ dùng trung bình. Ví dụ có 10.000 tenant, mỗi tenant trung bình 2 request/giây, nhưng một tenant lớn có thể tạo 3.000 request/giây vào giờ cao điểm. Thiết kế dựa trên giá trị trung bình dễ bỏ sót điểm nóng.

### 2.2. Bản đồ phân bố truy cập

Với từng nhóm người dùng hoặc tenant, ghi nhận:

- Khu vực có người dùng, thiết bị hoặc chi nhánh phát sinh ghi.
- Tỷ lệ request đọc/ghi theo khu vực và theo khung giờ.
- Truy vấn thường gặp: theo tenant, theo người dùng, theo thời gian, theo vị trí, hay truy vấn toàn hệ thống.
- Kích thước payload, số bản ghi trả về, độ trễ mục tiêu **p95/p99** và throughput giờ cao điểm.
- Dữ liệu nào phải đọc được ngay sau khi ghi, dữ liệu nào có thể trễ.
- Mức phụ thuộc vào dịch vụ ngoài region: xác thực, message broker, object storage, search và analytics.

Một bảng khảo sát mẫu:

| Workload | Phạm vi tenant | Phân bố địa lý | Độ trễ và nhất quán mong muốn |
|---|---|---|---|
| Xem đơn hàng | Một tenant, một đơn | Người dùng tại nhiều quốc gia | Đọc nhanh, trạng thái đơn đáng tin cậy |
| Tạo giao dịch | Một tenant, có thể nhiều bản ghi | Tập trung gần chi nhánh vận hành | Bảo vệ bất biến, tránh ghi trùng |
| Tổng hợp doanh thu | Một tenant hoặc toàn hệ thống | Job nền tại region được phép | Chấp nhận trễ theo lịch |
| Tìm điểm bán gần vị trí | Có thể một tenant hoặc phạm vi công khai | Phụ thuộc tọa độ người truy vấn | Truy vấn không gian trong vùng dữ liệu được phép |

### 2.3. Ràng buộc vị trí phải theo từng loại dữ liệu

Không phải mọi dữ liệu của cùng một tenant có yêu cầu giống nhau. Một hợp đồng có thể phân biệt dữ liệu khách hàng, log kỹ thuật, số liệu đã tổng hợp, backup và metadata vận hành.

Nên lập **data inventory**:

| Loại dữ liệu | Chủ sở hữu | Vùng được phép lưu/xử lý | Thời gian giữ | Đường truy cập chính |
|---|---|---|---|---|
| Hồ sơ khách hàng | Tenant | Theo chính sách tenant | Theo chính sách áp dụng | tenantId + customerId |
| Giao dịch | Tenant | Home region được phê duyệt | Theo nghĩa vụ nghiệp vụ | tenantId + orderId |
| Sự kiện click | Tenant/sản phẩm, cần xác định | Theo phân loại và chính sách | Ngắn hoặc phân tầng | tenantId + thời gian |
| Log vận hành | Đơn vị vận hành; có thể chứa dữ liệu tenant | Theo nội dung thực tế của log | Theo chính sách log | service + timestamp |
| Backup | Theo dataset nguồn | Vùng được phép và chính sách DR | Theo lịch backup | snapshot/time |

Các ví dụ trên chỉ là cách tổ chức thông tin, không thay thế việc rà soát chính sách pháp lý, hợp đồng và tiêu chuẩn áp dụng cho từng hệ thống.

## 3. Phạm vi tenant quyết định mô hình đa thuê (multi-tenancy)

NoSQL có thể phục vụ nhiều tenant bằng các mức dùng chung tài nguyên khác nhau. Mỗi lựa chọn ảnh hưởng đến khóa truy cập, isolation, khả năng vận hành và chi phí.

### 3.1. Các chiến lược lưu trữ tenant

| Mô hình | Cách triển khai | Lợi ích | Đánh đổi |
|---|---|---|---|
| **Shared collection/table** | Nhiều tenant trong cùng collection, mỗi record có tenantId | Ít đối tượng phải quản trị, tận dụng tài nguyên tốt | Mọi truy vấn phải giới hạn tenant; tranh chấp tài nguyên; khó chuyển riêng từng tenant |
| **Collection/table riêng cho tenant** | Một database/cluster chứa nhiều collection | Ranh giới dữ liệu rõ hơn, có thể tùy chỉnh một phần | Nhiều index, schema migration và đối tượng cần quản trị |
| **Database riêng cho tenant** | Một database logic cho từng tenant | Dễ áp dụng chính sách, quota hoặc backup riêng khi DB hỗ trợ | Chi phí quản lý, kết nối và tài nguyên tăng theo số tenant |
| **Cluster/instance riêng cho tenant** | Tenant có tài nguyên vật lý hoặc logic chuyên biệt | Isolation và tùy biến vùng/quy mô tốt hơn | Chi phí provisioning, giám sát, vận hành cao |
| **Hybrid / tiered** | Tenant nhỏ dùng chung, tenant lớn hoặc có yêu cầu đặc biệt dùng riêng | Cân bằng hiệu quả tài nguyên và yêu cầu cô lập | Cần cơ chế định tuyến và chuyển tenant giữa các tầng |

Đây là các **mẫu thiết kế**, không phải mức bảo đảm bảo mật mặc định. Mỗi sản phẩm NoSQL có cơ chế authorization, phân vùng, transaction, encryption, backup và quản trị khác nhau. Database riêng cũng chưa chắc là tài nguyên tính toán riêng; cluster riêng vẫn phải cấu hình kiểm soát quyền thích hợp.

### 3.2. Khóa tenant trong mô hình shared

Giả sử một document đơn hàng có dạng:

~~~json
{
  "tenantId": "T-100",
  "orderId": "O-1042",
  "customerId": "C-27",
  "createdAt": "2026-11-14T08:00:00Z",
  "status": "CONFIRMED",
  "total": 530000
}
~~~

Một đường truy cập phổ biến:

~~~text
primary key: (tenantId, orderId)
query:       Lấy đơn O-1042 thuộc tenant T-100

secondary access path:
  partition: (tenantId, customerId)
  sort:      createdAt DESC
query:       Lấy 20 đơn mới nhất của khách C-27 trong tenant T-100
~~~

Cách biểu diễn khóa cụ thể tùy hệ NoSQL. Điều quan trọng là cả **định danh tài nguyên** lẫn **truy vấn** đều có phạm vi tenant. Nếu chỉ truy vấn theo **orderId** mà mã đơn không unique toàn hệ thống hoặc thiếu kiểm tra quyền, dữ liệu có thể bị trả sai tenant.

Một API nên xác định tenant từ **ngữ cảnh xác thực và quyền đã được kiểm tra**. Giá trị tenantId do client gửi lên chỉ là yêu cầu lựa chọn tenant; không được tin tưởng nếu người dùng chưa được xác nhận có quyền với tenant đó.

~~~text
Ví dụ logic xử lý request (mã giả):

principal = verifyAuthentication(request)
tenantId = resolveAuthorizedTenant(principal, request.tenantSelection)
assert principal.canRead(tenantId, orderId)

order = orders.get(key=(tenantId, orderId))
return order
~~~

Thêm tenantId vào khóa giúp giới hạn đường truy cập, nhưng **bản thân partition key không phải cơ chế phân quyền**. Cần kiểm soát tenant ở API, truy vấn, dịch vụ nền, export và tác vụ quản trị. Với collection dùng chung, index phụ và job batch cũng phải tôn trọng phạm vi tương ứng.

### 3.3. Cẩn thận khi dùng tenantId làm partition key duy nhất

Nếu mọi bản ghi của một tenant nằm trên một khóa phân vùng logic duy nhất:

~~~text
partition key = tenantId
sort key      = createdAt
~~~

thì các tenant nhỏ có thể hoạt động tốt, nhưng một tenant lớn có thể tạo partition rất rộng hoặc dồn quá nhiều ghi vào một phân vùng. Phân phối workload **lệch** mới là yếu tố nguy hiểm, không chỉ tổng số tenant.

Tùy pattern truy vấn, có thể phân tách:

~~~text
partition key = (tenantId, yearMonth)
sort key      = (createdAt, eventId)
~~~

hoặc:

~~~text
partition key = (tenantId, shardNo)
sort key      = (createdAt, eventId)
~~~

Tháng và shard có thể giảm kích thước hoặc tải trên một khóa, nhưng truy vấn toàn lịch sử phải đọc nhiều nhóm và gộp kết quả. Cần xác định cách tìm shard, phân trang, sắp xếp toàn cục và xử lý tenant tăng quy mô. **Phân vùng tốt cho ghi có thể khiến đọc khó hơn**, nên phải đánh giá cả hai chiều.

### 3.4. Noisy neighbor và quota theo tenant

Trong mô hình shared, tenant A chạy import hàng triệu bản ghi có thể làm tăng độ trễ truy vấn của tenant B. Một số biện pháp:

- Theo dõi request rate, dung lượng, lỗi và p95/p99 latency **theo tenant**.
- Áp dụng rate limit và concurrency limit theo tenant/workload.
- Dùng queue để làm mượt các công việc nhập hoặc xử lý nền.
- Tách nhóm tenant lớn, noisy hoặc có SLO cao sang tài nguyên riêng khi cần.
- Quy hoạch quota theo cả dung lượng, throughput và chỉ số hot key.

Quota ở tầng ứng dụng giúp kiểm soát công bằng nhưng không bảo đảm tránh mọi tranh chấp ở tầng database. Cần đối chiếu với cơ chế giới hạn thực tế của hệ NoSQL.

## 4. Phạm vi địa lý: đặt tải gần dữ liệu hay đặt dữ liệu gần tải?

### 4.1. Độ trễ mạng là một phần của đường truy cập

Giả sử người dùng tại khu vực A truy cập API ở region B, API lại đọc database tại region C. Một yêu cầu có thể phải trả nhiều lần chi phí round trip:

~~~text
Client A
    |
    | RTT đến API
    v
API region B
    |
    | RTT đến database
    v
Database region C
~~~

Độ trễ end-to-end có thể nhìn theo mô hình:

~~~text
T_response ≈ T_network_client_api
           + T_api_processing
           + T_network_api_db
           + T_db_execution
           + T_serialization_and_return
~~~

Đây là mô hình đơn giản hóa để tìm nguồn trễ, không phải công thức dự báo chính xác. Các bước có thể chồng lấn, cache có thể bỏ qua lần đọc DB, và độ trễ đuôi còn chịu ảnh hưởng của retry, queue, congestion hay replica lag.

Vì vậy, triển khai API gần người dùng nhưng để mọi truy vấn database đi qua khoảng cách xa có thể không cải thiện nhiều. Ngược lại, đưa dữ liệu tới nơi gần người dùng cần cân nhắc residency, replication cost và tính nhất quán.

### 4.2. Phạm vi địa lý của người dùng khác với phạm vi truy vấn địa lý

Hai trường hợp thường bị nhầm:

1. **Người dùng ở nhiều quốc gia**: đặt câu hỏi về routing, local latency, replica và home region.
2. **Dữ liệu chứa tọa độ**: đặt câu hỏi về geospatial index, lọc theo bán kính, bounding box, geohash/cell và độ chính xác.

Ví dụ ứng dụng tìm cửa hàng gần khách có thể có truy vấn:

~~~text
findStores(
  tenantId = "T-100",
  point = (latitude, longitude),
  radiusKm = 5
)
~~~

Đường truy cập cần dùng geospatial index hoặc phân vùng không gian thích hợp. Nếu dùng ô lưới/geohash để lấy ứng viên, thường phải tính lại khoảng cách chính xác và lọc biên của vùng tìm kiếm. **Geospatial key không tự xác định dữ liệu được phép nằm ở region nào**. Có thể lưu dữ liệu vị trí trong một home region và phục vụ truy vấn địa lý tại đó, hoặc xây replica được phép để giảm độ trễ.

### 4.3. Geo-routing phải biết tenant và quyền lưu dữ liệu

Chiến lược đơn giản “định tuyến tới vùng gần IP nhất” có thể sai. Người dùng của tenant B đang công tác ở nơi khác vẫn cần đọc dữ liệu tại vùng của tenant B. Một edge node gần người dùng có thể nhận request, nhưng backend phải định tuyến theo **home region của tenant hoặc dataset**.

Luồng logic:

~~~mermaid
flowchart LR
    U["Người dùng"] --> E["Gateway / edge"]
    E --> A["Xác thực và tenant context"]
    A --> R["Tra cứu mapping tenant → home region"]
    R --> B["API vùng có thẩm quyền"]
    B --> DB[("NoSQL data tại vùng được phép")]
~~~

Mapping vùng cần đủ sẵn sàng để không trở thành điểm lỗi đơn. Nếu mapping chứa thông tin nhạy cảm, chính nó cũng cần chính sách lưu trữ và truy cập tương ứng. Bộ nhớ đệm mapping có thể tăng tốc nhưng phải xử lý trường hợp tenant vừa được chuyển vùng.

## 5. Vùng triển khai: chọn topology theo độ trễ và khả năng chịu lỗi

Cách phân phối dữ liệu giữa các region quyết định nơi đọc/ghi có thẩm quyền, mức trễ khi mạng lỗi và khả năng failover.

### 5.1. Một region, nhiều miền lỗi

**Mẫu:** API và database tại một region; database dùng nhiều zone hoặc replica trong region khi dịch vụ hỗ trợ.

**Phù hợp khi:** lưu lượng tập trung, residency giới hạn trong một region, mức sẵn sàng yêu cầu chưa cần chịu mất toàn bộ region.

**Ưu điểm:** đường ghi ngắn, ít phức tạp đồng bộ vùng xa, chính sách dữ liệu đơn giản hơn.

**Giới hạn:** nếu cả region không khả dụng thì cần kế hoạch DR khác; nhiều zone không thay thế backup và không bảo đảm sống sót khi lỗi toàn region.

### 5.2. Một home region, replica đọc ở các region khác

**Mẫu:** ghi vào home region, sao chép tới các read region được cho phép.

**Phù hợp khi:** nhiều người dùng địa lý khác nhau, tỷ lệ đọc cao, chấp nhận replica chậm hơn primary đối với một số màn hình.

**Ưu điểm:** đọc gần người dùng hơn, có thể giảm tải home region.

**Đánh đổi:** dữ liệu đọc tại replica có thể trễ; đồng bộ xuyên vùng tiêu tốn băng thông; replica và cache đều phải nằm trong vùng được phép. Nếu cần **read-your-writes** sau khi sửa, ứng dụng có thể phải đọc từ home region hoặc sử dụng cơ chế consistency/session token mà hệ quản trị hỗ trợ.

### 5.3. Multi-region active–passive

**Mẫu:** region chính nhận ghi; region dự phòng chuẩn bị nhận hoạt động khi sự cố.

**Phù hợp khi:** cần khả năng tiếp tục dịch vụ khi mất region, nhưng muốn có nơi ghi chính rõ ràng.

Cần định nghĩa **RPO** (mức dữ liệu có thể mất khi phục hồi) và **RTO** (thời gian khôi phục mục tiêu). Replication bất đồng bộ có thể tạo khoảng trống dữ liệu khi failover, nên không thể tuyên bố RPO bằng 0 nếu chưa có cơ chế bảo đảm. Failover còn phải giải quyết DNS/routing, token, job nền, queue, dữ liệu chưa replicate, chuyển vai trò ghi và nguy cơ hai phía cùng nhận ghi (**split brain**).

### 5.4. Multi-region active–active

**Mẫu:** nhiều region cùng nhận ghi, dữ liệu được đồng bộ giữa chúng.

**Phù hợp khi:** ứng dụng thực sự cần ghi gần nhiều nhóm người dùng hoặc yêu cầu availability đặc biệt và chấp nhận độ phức tạp.

**Đánh đổi lớn:** hai region có thể cùng sửa một thực thể khi bị mất kết nối. Cần chọn semantics cho concurrent writes:

- Một tenant hoặc thực thể có **home writer** cố định, các region khác chuyển ghi về đó.
- Chấp nhận nhiều writer với cơ chế phát hiện và xử lý conflict.
- Giới hạn dữ liệu nào có thể merge theo tính chất nghiệp vụ; ví dụ counter hoặc tập hợp có thể có thiết kế đặc biệt, nhưng trạng thái đơn hàng hoặc tồn kho không thể tùy tiện dùng “ghi cuối thắng” mà không xét bất biến.

Khả năng multi-region/active–active, thứ tự xung đột, mức nhất quán và mô hình transaction là **tính năng cụ thể của sản phẩm**. Không được suy từ tên “global database” rằng mọi thao tác ghi đều serializable trên toàn thế giới.

### 5.5. Bảng so sánh topology

| Topology | Điểm mạnh | Cần làm rõ trước khi chọn |
|---|---|---|
| Single-region, multi-zone | Đơn giản, latency giữa các thành phần thấp | DR khi mất region; backup và restore |
| Home region + remote read | Đọc gần người dùng; giữ một nguồn ghi | Replica lag; read-your-writes; vùng được phép sao chép |
| Active–passive multi-region | Có lộ trình DR cho lỗi region | RPO/RTO, chuyển vai trò, split brain, quy trình diễn tập |
| Active–active multi-region | Có thể nhận ghi tại nhiều nơi | Conflict, giao dịch xuyên vùng, chi phí và yêu cầu nhất quán |
| Mỗi tenant một home region | Kiểm soát locality, residency và tách tải theo tenant | Tenant routing, provisioning, migration, global reporting |

Không có topology phù hợp mọi doanh nghiệp. Quyết định nên dựa trên **workload theo vùng**, **độ trễ cần thiết**, **RPO/RTO**, **mức chấp nhận conflict**, **allowed regions** và ngân sách vận hành.

## 6. Nơi lưu dữ liệu: nhìn toàn bộ vòng đời, không chỉ database chính

### 6.1. Data residency, data sovereignty và deployment khác nhau

- **Data residency:** yêu cầu hoặc lựa chọn về nơi dữ liệu được lưu và đôi khi nơi được xử lý, theo định nghĩa cụ thể của chính sách.
- **Data sovereignty:** vấn đề dữ liệu và hoạt động liên quan chịu sự điều chỉnh của thẩm quyền pháp lý nào; không thể giải quyết chỉ bằng chọn một region.
- **Deployment location:** nơi dịch vụ chạy trên hạ tầng.
- **Access location:** nơi người dùng hoặc nhân sự vận hành truy cập dữ liệu.

Một database lưu tại region R1 không tự động đáp ứng mọi nghĩa vụ về dữ liệu nếu có export sang R2, log chứa payload ở R3 hoặc nhà cung cấp khác xử lý dữ liệu tại địa điểm không nằm trong phạm vi đã chấp thuận. Các yêu cầu cụ thể phải được diễn giải từ hợp đồng, chính sách và quy định áp dụng; không nên tự suy ra một luật chung cho mọi quốc gia.

### 6.2. Kiểm kê mọi bản sao và đường đi dữ liệu

| Thành phần | Nội dung có thể tồn tại | Câu hỏi phải kiểm tra |
|---|---|---|
| **Primary database** | Dữ liệu gốc, index | Region thực tế; vùng của partition/replica |
| **Replica** | Bản sao đầy đủ hoặc một phần | Có nhân bản xuyên vùng? Lag bao lâu? |
| **Backup / snapshot / archive** | Bản sao lịch sử, có thể có dữ liệu đã xóa ở primary | Lưu ở đâu? Retention? Restore được vào vùng nào? |
| **Search index** | Nội dung và trường có thể nhạy cảm | Hệ search ở vùng nào? Có tự động sao chép? |
| **Cache** | Kết quả truy vấn, session, token, profile | Cache ở edge hay nhiều region? TTL và invalidation? |
| **Queue / event stream** | Payload sự kiện, thông tin thay đổi | Broker ở đâu? DLQ và log sự kiện có chứa dữ liệu gốc? |
| **Application / audit logs** | ID, header, query, lỗi, đôi khi cả payload | Pipeline log đi đâu? Ai có quyền đọc? |
| **Analytics / warehouse** | Dữ liệu export, tổng hợp, dữ liệu lịch sử | Export có đưa bản ghi tenant sang vùng khác? |
| **Object storage** | File đính kèm, ảnh, bản xuất | Bucket region, replication, lifecycle |
| **Monitoring / support tools** | Trace, metric với nhãn tenant và metadata | Có chứa thông tin nhạy cảm hoặc bản sao ngoài phạm vi? |

Cần phân biệt **mã định danh kỹ thuật** và dữ liệu được bảo vệ: ID có thể vẫn được coi là nhạy cảm trong ngữ cảnh cụ thể. Đừng mặc định “chỉ là metadata” nên được gửi đến bất kỳ đâu.

### 6.3. Encryption không thay thế yêu cầu về vị trí

Mã hóa khi truyền và khi lưu, tách khóa theo vùng, phân quyền và audit là các lớp bảo vệ cần thiết. Nhưng nếu một chính sách yêu cầu dữ liệu không được lưu ở ngoài phạm vi đã định, thì **bản mã nằm ngoài phạm vi đó** có thể vẫn không đáp ứng chính sách. Phải kiểm tra định nghĩa được áp dụng cho dữ liệu mã hóa, bản sao, khóa và các quy trình vận hành.

### 6.4. Xóa dữ liệu, retention và phục hồi

Xóa một document khỏi primary không nhất thiết xóa ngay khỏi replica, cache, search index, backup hoặc file export. Hệ thống cần thiết kế:

1. **Nguồn dữ liệu có thẩm quyền** và danh sách bản sao/phát sinh có thể truy vết.
2. **Quy trình xóa/tombstone** hoặc hạn sử dụng để bản sao không hồi sinh dữ liệu cũ.
3. **Đồng bộ xóa sang projection, cache và index** theo độ trễ mục tiêu.
4. **Quy tắc retention cho backup và lưu trữ bất biến** theo nghĩa vụ thực tế.
5. **Quy trình restore** có thể áp dụng lại các lệnh xóa hợp lệ phát sinh sau bản snapshot.
6. **Audit** để chứng minh từng bước được thực hiện trong phạm vi hệ thống kiểm soát.

Thời gian giữ dữ liệu khác nhau giữa transaction, log, snapshot và sự kiện có thể quyết định cần bao nhiêu tầng storage, ở những region nào, và chi phí dài hạn ra sao.

## 7. Kết nối chính sách tenant với chiến lược định tuyến và lưu trữ

Một kiến trúc nhiều region thường cần một **tenant registry** nhỏ để biết tenant có home region nào, database nào và chính sách nào đang áp dụng.

Ví dụ cấu hình **minh họa**, không phải schema của một sản phẩm cụ thể:

~~~yaml
tenantId: T-100
homeRegion: R1
allowedDataRegions: [R1, R2]
readReplicaRegions: [R2]
writeMode: single-writer
isolationTier: shared
dataPlacementVersion: 7
datasets:
  orders:
    primaryRegion: R1
    backupRegions: [R1]
  customerProfiles:
    primaryRegion: R1
    backupRegions: [R1]
~~~

Trong ví dụ này, dù **R2** nằm trong danh sách vùng được phép, không có nghĩa mọi loại dữ liệu được phép sao chép tới đó theo cấu hình hiện hành. **allowedDataRegions** là điều kiện trần; các dataset có thể có cấu hình hẹp hơn.

Một cấu trúc logic:

~~~mermaid
flowchart TD
    C["Client"]
    C --> GW["API gateway"]
    GW --> AUTH["Xác thực + kiểm tra quyền tenant"]
    AUTH --> MAP["Tenant registry / routing metadata"]
    MAP --> RA["API vùng R1"]
    MAP --> RB["API vùng R2"]
    RA --> D1[("NoSQL tại R1")]
    RB --> D2[("NoSQL tại R2")]
    D1 -. "Replication nếu chính sách cho phép" .-> D2
~~~

Đây là hình nguyên lý. Hệ thống thực tế có thể có control plane khác data plane, cache mapping, routing qua gateway vùng, cơ chế failover và nhiều dataset có home region khác nhau. **Mũi tên replication không mặc định được bật**.

### 7.1. Một request nên được quyết định như thế nào?

~~~text
1. Xác thực user/service và tenant được chọn.
2. Kiểm tra quyền thực hiện hành động với tenant và tài nguyên.
3. Xác định dataset mà hành động sẽ đọc hoặc ghi.
4. Tra cứu home region/allowed regions của dataset.
5. Chọn endpoint phục vụ thao tác:
   - Ghi quan trọng: route tới writer có thẩm quyền.
   - Đọc: chọn replica được phép nếu mức nhất quán phù hợp.
6. Áp dụng tenant-scoped key/query và quota.
7. Ghi log/metric đã phân loại, tránh phát sinh dữ liệu ở vùng cấm.
~~~

Nên xác định rõ hành vi khi registry không truy cập được: có thể tiếp tục dùng mapping cache còn hiệu lực hay phải tạm từ chối ghi? Dùng mapping đã lỗi thời sau migration có thể làm ghi nhầm vùng. Quyết định này cần theo mức độ rủi ro và cơ chế version/cutover.

### 7.2. Cross-tenant analytics là một đường truy cập riêng

Truy vấn nghiệp vụ thường yêu cầu phạm vi một tenant, nhưng hệ thống vận hành có thể cần thống kê toàn bộ tenant. Không nên biến một truy vấn tổng hợp xuyên tenant thành lý do cho phép API thông thường đọc dữ liệu mọi tenant.

Các hướng triển khai có thể gồm:

- Tổng hợp số liệu theo tenant ngay tại vùng được phép, rồi chuyển **chỉ số tổng hợp được cho phép** tới hệ báo cáo chung.
- Chạy analytics tại vùng lưu trữ của từng tập dữ liệu, sau đó hợp nhất kết quả đã được phân loại.
- Có cơ chế batch/stream riêng với quyền, audit, retention và dữ liệu đầu ra được mô tả rõ.

Quyết định **dữ liệu tổng hợp đã đủ giảm rủi ro để chuyển vùng hay chưa** phải dựa trên chính sách thực tế, khả năng tái nhận dạng và mức chi tiết của dữ liệu; không thể giả định mọi dữ liệu đã aggregation đều tự do chuyển vùng.

## 8. Mapping yêu cầu vào partition key và data placement

Hai câu hỏi cần trả lời riêng:

1. **Placement:** bản ghi thuộc region/database/cluster nào?
2. **Access path:** trong vùng lưu trữ đó, truy vấn dùng khóa/chỉ mục gì?

Ví dụ hệ quản lý giao dịch có tenant ở nhiều region:

~~~text
Tenant registry:
    T-100 → R1
    T-200 → R2

R1 / Orders:
    partition key = (tenantId, month)
    sort key      = (createdAt, orderId)

R2 / Orders:
    partition key = (tenantId, month)
    sort key      = (createdAt, orderId)
~~~

Chỉ có trường **region** bên trong document không đủ để bảo đảm dữ liệu được lưu trong vùng đã chọn. Nếu cả R1 và R2 dùng chung một cluster có replication toàn cầu, dữ liệu vẫn có thể được lưu ở cả hai nơi. Chính sách placement phải kiểm soát **hạ tầng, tài nguyên và replication**; trường region chỉ là metadata.

### 8.1. Dữ liệu chung và dữ liệu tenant-specific

Không phải mọi tập dữ liệu đều có cùng phạm vi. Ví dụ:

| Dataset | Phạm vi phù hợp | Đường truy cập điển hình |
|---|---|---|
| Hồ sơ và đơn hàng | Tenant-specific | tenantId + recordId / thời gian |
| Catalog sản phẩm công khai | Có thể dùng chung nếu nghiệp vụ cho phép | productId, category |
| Bảng cấu hình tenant | Tenant-specific và ít thay đổi | tenantId |
| Tenant registry | Control plane; chứa mapping tối thiểu | tenantId |
| Mẫu tỷ giá hoặc mã quốc gia | Dữ liệu tham chiếu dùng chung | code, version |

Không nên đưa tenantId vào mọi khóa một cách máy móc. Với dữ liệu công khai dùng chung, tenant key có thể gây trùng bản sao không cần thiết. Ngược lại, dữ liệu có quyền sở hữu tenant phải bảo đảm cô lập ngay cả khi dùng chung collection.

### 8.2. Tách đường đọc và đường ghi giữa các vùng

Một tenant có nhân viên ở R1 và R2; bản ghi gốc ở R1:

~~~text
Write from R2 --> writer R1 --> commit tại R1
Read in R1  --> data R1
Read in R2  --> replica R2 (nếu được phép và UI chấp nhận độ trễ)
~~~

Nếu sau cập nhật bắt buộc nhìn thấy trạng thái mới, đọc từ replica R2 có thể chưa phù hợp. Có thể định tuyến đọc theo writer, chờ một mốc replication/causal token do hệ hỗ trợ, hoặc hiển thị trạng thái đang đồng bộ. Không có một cơ chế nhất quán giống nhau cho mọi hệ NoSQL.

## 9. Bài toán minh họa: SaaS quản lý cửa hàng đa khu vực

Giả sử một nền tảng phục vụ ba nhóm tenant. Các vùng **R1, R2, R3** chỉ là nhãn ví dụ; mọi yêu cầu vị trí bên dưới đều là **giả định của bài toán**, không diễn giải nghĩa vụ pháp lý của quốc gia nào.

| Nhóm tenant | Phân bố người dùng | Yêu cầu dữ liệu | Áp lực tải |
|---|---|---|---|
| **Nhóm A** – cửa hàng nhỏ | Chủ yếu tại khu vực gần R1 | Dữ liệu chỉ cần ở R1 theo hợp đồng giả định | Rất nhiều tenant nhỏ, tải mỗi tenant thấp |
| **Nhóm B** – chuỗi lớn | Người dùng tại R1, R2 | Primary ở R1, được phép có read replica R2 | Một tenant có write burst rất lớn |
| **Nhóm C** – tenant yêu cầu vùng riêng | Người dùng ở nhiều nơi | Chỉ R3 được lưu và xử lý dữ liệu khách hàng | Tải vừa nhưng yêu cầu cô lập và residency chặt |

### 9.1. Đề xuất phân tầng

**Nhóm A:** shared database/collection tại R1, khóa có tenantId. Dùng quota và metric theo tenant để xử lý noisy neighbor. Không cần tạo một cluster cho từng cửa hàng.

**Nhóm B:** cân nhắc database/cluster chuyên biệt, hoặc một nhóm tài nguyên tách riêng nếu phân bố tải và SLO cho thấy shared infrastructure không đáp ứng. Giữ writer tại R1. Nếu cho phép về chính sách và có lợi về độ trễ, cung cấp replica đọc tại R2; chỉ bật cho loại dữ liệu được chấp thuận.

**Nhóm C:** định tuyến mọi thao tác truy cập dữ liệu liên quan tới R3; kiểm tra cả backup, search, queue, audit log và dịch vụ hỗ trợ. Có thể dùng tài nguyên riêng tại R3 nếu yêu cầu cô lập hoặc khả năng cấu hình chính sách đòi hỏi.

### 9.2. Vì sao không nên route mọi thứ theo vị trí IP?

Nhân viên nhóm C đang ở gần R1 có thể truy cập gateway tại R1 để giảm độ trễ kết nối đầu tiên. Nhưng nếu API xử lý hoặc cache dữ liệu tenant tại R1 trái chính sách, hệ thống đã vi phạm mô hình placement giả định. Request có thể cần được chuyển tới dịch vụ R3 để thực thi và dữ liệu phản hồi chỉ đi qua các thành phần được phép.

Tương tự, nhóm B có read replica ở R2 không có nghĩa mọi thao tác ghi được commit tại R2. Chức năng tạo đơn và cập nhật tồn kho phải đi theo đường ghi có bảo đảm nhất quán đã chọn.

### 9.3. Tính tải theo khu vực, theo tenant và theo loại truy vấn

Giả sử toàn hệ thống có 4.000 request/giây ở đỉnh, nhưng phân bố:

~~~text
R1:  2.600 req/s (đa số tenant A)
R2:    900 req/s (người dùng nhóm B)
R3:    500 req/s (tenant nhóm C)

Trong R1:
  1 tenant B đóng góp 1.500 req/s vào cùng nhóm khóa.
~~~

Chỉ nhìn con số 2.600 req/s tại R1 không cho thấy một hot key tạo 1.500 req/s. Cần phân tách thêm:

~~~text
region × tenant × operation × partition-key distribution
~~~

Ví dụ các lớp metric nên có là **region/request**, **tenant/request**, **tenant/write-conflict**, **partition/throttle**, **replica lag**, **cross-region transfer** và **quota/tenant**. Khi số tenant rất lớn, lưu metric chi tiết cho mọi tenant có thể gây bùng nổ cardinality; cần kết hợp aggregation, top-N, sampling, logs/traces hoặc cơ chế theo dõi tenant trọng điểm.

### 9.4. Những tình huống phải diễn tập

1. **Region R1 chậm:** có tenant nào chỉ được ở R1 và không được tự động chuyển dữ liệu? Cần thể hiện trạng thái suy giảm thay vì failover sai chính sách.
2. **Tenant B bị hot partition:** quota, retry, tách shard và đọc lịch sử có còn đáp ứng mục tiêu?
3. **Replica R2 trễ 30 giây:** tính năng nào được đọc dữ liệu cũ, tính năng nào bắt buộc đọc từ writer R1?
4. **Dữ liệu nhóm C lọt vào log chung:** pipeline log, support tool và retention có phát hiện và xử lý được không?
5. **Chuyển nhóm A thành tenant lớn:** có quy trình chuyển từ shared sang dedicated mà giữ đúng dữ liệu, quyền truy cập và downtime mục tiêu không?

## 10. Di chuyển tenant và thay đổi home region

Migration giữa vùng hoặc giữa shared/dedicated là tình huống thường gặp khi tenant tăng trưởng, khách hàng thay đổi yêu cầu hợp đồng hoặc công ty mở thêm thị trường.

Không nên coi migration chỉ là thao tác copy collection. Ít nhất cần xử lý:

- **Xác định phạm vi:** những dataset, index, file, event, cache, log và backup nào thuộc tenant.
- **Chọn đích hợp lệ:** vùng mới phải được phép chứa từng loại dữ liệu; vùng cũ có phải xóa sau migration không?
- **Backfill có kiểm soát:** sao chép snapshot rồi đồng bộ các thay đổi phát sinh, hoặc bảo trì tạm dừng ghi với thời gian được thỏa thuận.
- **Giữ idempotency và phiên bản:** tránh tạo bản ghi trùng hoặc mất cập nhật khi đồng bộ.
- **Cutover định tuyến:** cập nhật mapping tenant với version, kiểm soát request đang chạy và chuyển writer một cách rõ ràng.
- **Kiểm tra đầy đủ:** so sánh số lượng bản ghi, checksum/đối soát nghiệp vụ, trạng thái index và projection.
- **Rollback và cleanup:** biết khi nào có thể trở lại nguồn cũ và khi nào phải xóa dữ liệu cũ theo chính sách.

Luồng tổng quát:

~~~mermaid
flowchart LR
    P["Chuẩn bị vùng đích + chính sách"] --> S["Snapshot / backfill"]
    S --> C["Đồng bộ phần thay đổi"]
    C --> V["Đối soát dữ liệu"]
    V --> W["Chặn / chuyển writer an toàn"]
    W --> R["Đổi tenant routing"]
    R --> M["Theo dõi, xác nhận cutover"]
    M --> K["Thu hồi dữ liệu nguồn theo chính sách"]
~~~

Các bước thực tế có thể khác nhau theo cơ chế cơ sở dữ liệu. Nếu không có CDC hoặc giao dịch phù hợp, cần kế hoạch tạm dừng ghi hoặc đồng bộ bằng log nghiệp vụ đáng tin cậy; **dual-write đơn thuần không bảo đảm hai bên luôn nhất quán**.

## 11. Vận hành: đặt mục tiêu đo lường và quyền kiểm soát

### 11.1. SLO theo loại tenant, đường truy cập và region

SLO chung của toàn dịch vụ có thể che giấu trải nghiệm xấu của một nhóm tenant. Nên làm rõ:

| Nhóm chỉ số | Ví dụ câu hỏi |
|---|---|
| **Latency** | p95/p99 đọc và ghi của tenant tại home region và từ region xa là bao nhiêu? |
| **Throughput** | Peak request, peak ghi theo tenant/partition có vượt giới hạn không? |
| **Consistency** | Replica lag, projection lag, số lần đọc stale ảnh hưởng sản phẩm thế nào? |
| **Availability** | Khi mất zone/region, tenant nào còn hoạt động và ở mức nào? |
| **DR** | RPO/RTO thực đo khi diễn tập phục hồi từng dataset và tenant? |
| **Residency** | Có bản sao, export, queue hoặc backup nào được tạo ngoài allowed regions không? |
| **Costs** | Dung lượng, I/O, index, replica và băng thông xuyên vùng theo tenant ra sao? |
| **Security** | Có truy vấn bị chặn vì sai tenant hoặc quyền không? Hệ thống phát hiện cross-tenant access thế nào? |

Trạng thái **“mọi node đều healthy”** không đồng nghĩa ứng dụng đáp ứng SLO cho tenant đang dùng phân vùng quá nóng hoặc đang truy cập xuyên vùng.

### 11.2. Chi phí đa vùng

Chi phí không chỉ là dung lượng bản gốc:

~~~text
Chi phí liên quan đến placement
    ≈ lưu dữ liệu gốc
    + chỉ mục
    + replica và backup
    + I/O và throughput theo vùng
    + truyền dữ liệu xuyên vùng
    + compute / dịch vụ nền
    + lưu trữ log, search, analytics
    + công vận hành và diễn tập DR
~~~

Đây là cấu trúc tính toán, không phải bảng giá của nhà cung cấp. Một lựa chọn giảm 50 ms độ trễ đọc có thể làm tăng chi phí replication hoặc write amplification. Cần đo lợi ích sản phẩm so với chi phí thực tế.

### 11.3. Các chính sách nên biến thành kiểm soát kỹ thuật

- **Region allowlist** cho provision database, storage, broker và backup.
- **Tenant-scoped access control** tại API, service và thao tác dữ liệu.
- **Provisioning template** bảo đảm tenant mới được tạo đúng vùng và isolation tier.
- **Audit** cho thay đổi tenant routing, replication, export và quyền đọc.
- **Quota/rate limit** để tenant lớn không làm tenant nhỏ bị ảnh hưởng nghiêm trọng.
- **Reconciliation và restore drill** nhằm phát hiện bản sao thiếu dữ liệu hoặc sai vùng.
- **Data lifecycle** rõ ràng cho retention, xóa, archive và migration.

Kiểm soát nên được thực thi tự động tại điểm provisioning/định tuyến khi có thể. Tài liệu chỉ ghi “không lưu ngoài R3” mà cấu hình replication mặc định vẫn sao chép sang R1 là một khoảng trống thiết kế.

## 12. Những nhầm lẫn phổ biến

### “Đã có tenantId thì dữ liệu đã được cô lập”

TenantId trong document chỉ là nhãn. Nếu truy vấn thiếu điều kiện tenant, quyền DB quá rộng hoặc một API export bỏ qua kiểm tra quyền, dữ liệu vẫn có thể bị lộ. Cần bảo vệ từ xác thực đến đường truy cập và tác vụ nền.

### “Một tenant tương ứng một region”

Một tenant có thể có user ở nhiều quốc gia và nhiều loại dữ liệu có chính sách khác nhau. Home region có thể là quyết định theo **dataset hoặc aggregate**, không nhất thiết áp dụng đơn giản cho mọi dữ liệu.

### “Đặt ứng dụng gần người dùng là đủ để giảm độ trễ”

Nếu API đặt gần user nhưng mọi thao tác phải đọc/ghi database ở xa qua nhiều round trip, thời gian phản hồi vẫn có thể cao. Phải phân tích toàn đường request, số lần gọi DB và lựa chọn đọc từ replica phù hợp.

### “Có backup tại region khác nên luôn an toàn hơn”

Backup khác vùng có thể cải thiện kịch bản DR nhưng đồng thời có thể trái residency policy. Backup còn phải được thử restore; chỉ tồn tại file snapshot không chứng minh phục hồi được ứng dụng trong RTO.

### “Bật global replication là có strong consistency toàn cầu”

Replication không nói đủ về mức nhất quán, thứ tự ghi, xung đột, failover hay transaction xuyên region. Phải kiểm tra semantics cụ thể và thiết kế nghiệp vụ dựa trên những gì hệ thật sự bảo đảm.

### “Đã mã hóa thì lưu ở đâu cũng được”

Encryption hỗ trợ bảo vệ bí mật và kiểm soát truy cập, nhưng không tự giải quyết các điều khoản về vị trí, xử lý, quyền truy cập hoặc bản sao lưu. Data inventory phải bao phủ cả dữ liệu mã hóa.

### “Region thuộc quốc gia đó nên tự động tuân thủ mọi quy định”

Vị trí hạ tầng chỉ là một yếu tố. Còn có phạm vi xử lý, người vận hành, nhà cung cấp phụ, backup, export, truy cập từ xa, quyền pháp lý và điều khoản hợp đồng. Việc xác nhận tuân thủ phải dựa trên yêu cầu cụ thể, không thể kết luận từ tên region.

## 13. Phương pháp quyết định thiết kế

Một quy trình thực hành có thể dùng cho dự án NoSQL mới:

1. **Xác định tenant scope:** định nghĩa tenant, user membership, dữ liệu chung và dữ liệu riêng; mô tả yêu cầu isolation.
2. **Đo workload:** truy vấn quan trọng, tỷ lệ đọc/ghi, tenant lớn, key nóng, dữ liệu tăng trưởng và vị trí phát sinh request.
3. **Lập data inventory và chính sách vị trí:** từng dataset và các bản sao được phép ở đâu, ai có quyền, giữ bao lâu.
4. **Chọn home region và topology:** single-region, read replica, active–passive, hoặc active–active theo latency, SLO, RPO/RTO và residency.
5. **Chọn mô hình multi-tenancy:** shared, dedicated hoặc hybrid theo quy mô và độ cô lập; định nghĩa cách nâng cấp tenant.
6. **Thiết kế khóa và đường truy cập:** tenant-scoped key, partition/shard, chỉ mục và truy vấn đa tenant; tránh hotspot.
7. **Thiết kế consistency và failover:** writer có thẩm quyền, đường đọc được phép stale, cơ chế ghi cạnh tranh và hành vi khi region mất kết nối.
8. **Bao phủ đường dữ liệu phụ:** cache, queue, log, search, analytics, backup và export phải tuân theo placement tương ứng.
9. **Kiểm chứng bằng tải và lỗi giả lập:** peak theo tenant/region, skew theo partition, replica lag, lỗi vùng, cutover và restore.
10. **Ghi lại quyết định và giới hạn:** mục tiêu đo được, giả định chính sách, người sở hữu quyết định và cơ chế thay đổi về sau.

Có thể dùng một ma trận quyết định ngắn cho mỗi dataset:

| Thuộc tính | Giá trị cần chốt |
|---|---|
| Dataset và owner | Dữ liệu gì, thuộc tenant hay dùng chung? |
| Allowed regions | Nơi được lưu/xử lý, bao gồm replica và backup |
| Home region / writer | Nơi ghi có thẩm quyền |
| Access pattern | Khóa truy vấn, độ trễ và số bản ghi |
| Partition strategy | TenantId, thời gian, shard hay kết hợp |
| Consistency | Đọc/ghi cần bảo đảm gì; đâu có thể trễ |
| Isolation tier | Dùng chung hay chuyên biệt |
| DR plan | RPO/RTO, failover region hợp lệ, restore |
| Lifecycle | Retention, xóa, export, migration |
| Observability | Metric và audit theo tenant/region |

## 14. Bài tập tư duy

**Bài 1 – Tenant lớn trong cluster dùng chung.** Một nền tảng có 2.000 tenant. Một tenant dùng 60% throughput và thường xuyên ghi vào cùng khóa tenantId. Hãy phân tích vì sao chỉ tăng số node có thể chưa giải quyết được hot partition; đề xuất cách đổi partition key và nói rõ truy vấn nào sẽ phức tạp hơn.

**Bài 2 – Người dùng đi công tác.** Tenant A yêu cầu mọi dữ liệu khách hàng chỉ ở R1. Một nhân viên của A đăng nhập từ gần R2. Hãy phác họa đường request có thể đáp ứng yêu cầu, và liệt kê các điểm mà cache, log hoặc proxy có thể tạo bản sao ngoài vùng mong muốn.

**Bài 3 – Đọc từ region gần nhất.** Tenant B ghi đơn tại R1 và có replica tại R2. Người dùng ở R2 vừa cập nhật trạng thái đơn nhưng đọc lại vẫn thấy trạng thái cũ. Hãy phân biệt replication lag và lỗi mất dữ liệu, đồng thời đề xuất hai cách xử lý để đạt kỳ vọng đọc lại ngay.

**Bài 4 – Thảm họa cả region.** Hệ thống có primary ở R1 và backup ở R2. Chính sách của một số tenant chỉ cho phép dữ liệu ở R1. Hãy xác định vì sao kế hoạch DR hiện tại có xung đột, và nêu các lựa chọn cần được thỏa thuận về phạm vi dịch vụ, vị trí backup và mục tiêu phục hồi.

**Bài 5 – Di chuyển tenant.** Một tenant tăng từ 5 GB lên 10 TB và cần chuyển từ shared collection ở R1 sang dedicated cluster tại R3. Hãy thiết kế chuỗi bước snapshot, đồng bộ thay đổi, đối soát, cutover định tuyến, kiểm tra rollback và thu hồi dữ liệu cũ.

Với mỗi bài, câu trả lời có cơ sở cần làm rõ **phạm vi tenant**, **đường truy cập**, **vị trí dữ liệu thật sự**, **bảo đảm nhất quán** và **chi phí/giới hạn vận hành**.

---

**Kết luận:** Trong NoSQL, tenant quyết định ranh giới sở hữu và cô lập; địa lý cho biết tải phát sinh ở đâu; region quyết định topology phục vụ và chịu lỗi; còn data residency quyết định bản gốc và mọi bản sao được phép tồn tại ở đâu. Bốn quyết định phải được đưa vào mô hình dữ liệu, khóa truy cập, cơ chế định tuyến, replication và quy trình vận hành ngay từ đầu, rồi kiểm chứng bằng workload và kịch bản lỗi thực tế.
