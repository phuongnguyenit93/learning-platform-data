# Định danh duy nhất khi dữ liệu được tạo tại nhiều nơi

## 1. Vấn đề: nhiều nơi tạo dữ liệu, một không gian định danh

Trong module **DATABASE_DATA_MODELING**, nhiệm vụ không chỉ là chọn kiểu dữ liệu cho một cột ID. Khi chuyển yêu cầu nghiệp vụ thành mô hình quan hệ, khóa, ràng buộc và lược đồ vật lý, cần xác định **một đối tượng được nhận diện như thế nào khi các bản ghi được tạo đồng thời ở nhiều nơi**.

Xét công ty có ba nơi ghi đơn hàng:

- Cửa hàng Hà Nội có database PostgreSQL độc lập.
- Cửa hàng TP.HCM có database PostgreSQL độc lập.
- Ứng dụng trên máy tính bảng có thể bán hàng **ngoại tuyến**, đồng bộ khi có mạng.

Mỗi nơi đang có bảng đơn với khóa tự tăng. Hai database đầu tiên đều có thể sinh ID 1001:

~~~text
Hà Nội                            TP.HCM
orders:                            orders:
  id 1001 -> đơn của An              id 1001 -> đơn của Bình
  id 1002 -> đơn của Chi             id 1002 -> đơn của Dũng

               Đồng bộ dữ liệu
                      ↓
         id = 1001 là đơn nào?
~~~

Mỗi database bảo đảm **khóa chính không trùng trong chính database ấy**. Điều đó không có nghĩa ID không trùng khi các bản ghi được nhập vào một nguồn phân tích hoặc dịch vụ trung tâm.

Ta có thể cấp **UUID toàn cục**, dùng **khóa ghép (vùng tạo, ID cục bộ)**, chia dải số hoặc cấp ID dựa trên thời gian và node. Nhưng lựa chọn nào cũng phải giải quyết những điều kiện khác: thiết bị có thể mất mạng, đồng hồ có thể sai, vùng có thể bị clone, lệnh có thể được gửi lại và hệ thống có thể chia thành nhiều shard.

Chủ đề **“Định danh duy nhất khi dữ liệu được tạo tại nhiều nơi”** thuộc chương **Phân tán và phân vùng**. Bài học giải thích cách thiết kế danh tính, so sánh các thuật toán, xây ràng buộc trong PostgreSQL và kiểm chứng quá trình đồng bộ đa nguồn. Các khái niệm cũng áp dụng khi chọn cách lưu quan hệ, document, graph hoặc dữ liệu phân tích.

### Kết quả học tập

Sau bài này, người học có thể:

1. Định nghĩa phạm vi duy nhất: **một bảng, một tenant, một nguồn, một shard hay toàn hệ thống**.
2. Phân biệt **business key, surrogate/global ID, event ID, idempotency key** và mã hiển thị.
3. So sánh sequence, cấp dải số, khóa ghép có namespace, UUIDv4, UUIDv7, ULID, Snowflake và ID service.
4. Nêu rõ những gì được bảo đảm bằng **điều phối** và những gì chỉ có **xác suất va chạm cực thấp**.
5. Thiết kế mô hình PostgreSQL có PRIMARY KEY, UNIQUE, bảng ánh xạ nguồn, registry và cơ chế phát hiện retry.
6. Giải thích giới hạn uniqueness của bảng phân vùng và database độc lập.
7. Thiết kế đồng bộ offline, migration, quản lý khóa ngoại và kiểm thử lỗi phân tán.

## 2. “Duy nhất” phải kèm theo một phạm vi

Không có một định nghĩa ID duy nhất chung cho mọi nghiệp vụ.

| Phạm vi | Ví dụ khóa | Ý nghĩa |
|---|---|---|
| Một bảng | PRIMARY KEY(id) | Mỗi hàng trong bảng không trùng id |
| Một tenant | (tenant_id, order_code) | Cùng tenant không có hai mã đơn như nhau |
| Một nguồn | (source_system, source_order_key) | Mã nguồn được phân biệt theo hệ phát hành |
| Một vùng | (origin_region, local_id) | Hai vùng được phép dùng cùng local_id |
| Toàn hệ thống | global_order_id | Một ID nhận diện một đối tượng trên mọi vùng |
| Một yêu cầu | (tenant_id, client_id, request_id) | Retry không tạo tác dụng nghiệp vụ lặp |
| Một luồng sự kiện | (aggregate_id, version) | Không có hai sự kiện cùng số phiên bản của aggregate |

Một UNIQUE trong PostgreSQL bảo vệ phạm vi **database đang áp ràng buộc ấy**. Khi hai vùng cùng ghi vào hai database độc lập, không có phép màu nào khiến hai constraint cục bộ thành một constraint toàn hệ thống.

### 2.1. Cùng số không chắc cùng đối tượng

~~~text
(origin_region = HN, local_id = 1001)
(origin_region = HCM, local_id = 1001)
~~~

Có thể đây là hai đơn hoàn toàn khác nhau. Cũng có thể HCM lưu **bản sao** của đơn tạo tại HN. Cần biết **nơi khởi tạo bản ghi** và quy tắc nghiệp vụ, không chỉ so sánh số 1001.

### 2.2. Khác ID chưa chắc khác đối tượng

Hai hệ CRM có thể tạo hai UUID khác nhau cho cùng một khách hàng. Không có ID collision, nhưng có khả năng **duplicate business entity**. Việc hợp nhất hai hồ sơ là bài toán **identity resolution** và cần bằng chứng, không phải bài toán bộ sinh UUID.

### 2.3. Duy nhất không đồng nghĩa liên tục hoặc tăng theo commit

Một dãy 1, 2, 5, 9 vẫn có thể là ID duy nhất. Sequence có thể bỏ số khi transaction rollback, cache bị bỏ hoặc dải được cấp nhưng không sử dụng.

Thứ tự **cấp ID** cũng không đồng nghĩa thứ tự **COMMIT**. Transaction nhận ID 1002 có thể commit trước transaction nhận 1001. Nếu nghiệp vụ cần số chứng từ liên tục hoặc thứ tự ghi sổ, hãy mô hình hóa **số chứng từ/sequence nghiệp vụ riêng**, với quy trình chốt và quy định liên quan. Không ép primary key phân tán phải kiêm nhiệm mọi vai trò.

## 3. Một đối tượng có thể cần nhiều loại khóa

Một đơn tạo trên tablet có thể có:

| Trường | Chức năng | Có thể thay đổi? |
|---|---|---|
| **global_order_id** | Định danh đơn hàng ở mọi nơi | Nên ổn định sau khi cấp |
| **source_order_key** | Mã đơn mà POS/ERP dùng | Có thể đổi do migration nguồn, cần giữ dấu vết |
| **client_request_id** | Định danh lệnh CreateOrder để chống retry | Phải giữ nguyên qua các lần gửi lại cùng lệnh |
| **order_number** | Mã hiển thị cho khách, in trên chứng từ | Có quy tắc pháp lý/nghiệp vụ riêng |
| **event_id** | Định danh một sự kiện như OrderCreated | Giữ nguyên qua các lần phát lại event |
| **aggregate_version** | Số thứ tự thay đổi của một đơn | Tăng theo quy tắc của luồng đơn |

**Global ID** nhận diện bản ghi, **business key** nhận diện đối tượng theo nguồn, **idempotency key** nhận diện yêu cầu, còn **event ID** nhận diện sự kiện. Một đơn có thể có nhiều event khác nhau; một request có thể sinh nhiều event.

Không dùng order_id làm khóa dedup cho tất cả thao tác: cùng một đơn có thể có hai lần thanh toán hoặc hai sự kiện vận chuyển hợp lệ. Cũng không được sinh order_id mới mỗi lần gửi lại cùng yêu cầu rồi cho rằng vì UUID không trùng nên hệ thống đã an toàn.

### 3.1. Namespace là một phần của danh tính nguồn

Nếu ERP-VN và ERP-TH đều có mã P01, hai mã chưa chắc cùng một sản phẩm. Khóa đầy đủ có thể là:

~~~text
(tenant_id, source_system, business_key)

(1, ERP-VN, P01) != (1, ERP-TH, P01)
(1, ERP-VN, P01) != (2, ERP-VN, P01)
~~~

Nếu mã đơn cục bộ được tái sử dụng mỗi ngày tại từng quầy, namespace có thể còn gồm **store_id, register_id, business_date**. Phải lấy đúng quy tắc của hệ nguồn; không tùy tiện thêm hoặc bỏ thành phần chỉ để làm UNIQUE chạy được.

Đối với chuỗi mã, đừng tự bỏ số 0 ở đầu hay đổi chữ hoa/thường nếu nguồn phân biệt chúng.

## 4. Những kiểu va chạm và trùng lặp cần xử lý

| Vấn đề | Triệu chứng | Biện pháp chính |
|---|---|---|
| **ID collision** | Hai đối tượng khác nhau có cùng global ID | Thuật toán/namespace đúng, UNIQUE và xử lý lỗi |
| **Local ID collision** | Hai shard có id=1001 | Giữ origin namespace hoặc cấp global ID |
| **Retry duplicate** | Một yêu cầu tạo hai đơn có ID khác nhau | Idempotency key và kết quả xử lý bền vững |
| **Duplicate entity** | Hai ID khác nhau mô tả cùng một khách | Identity resolution/canonical mapping |
| **Duplicate event delivery** | Một event được broker giao hai lần | Stable event_id và consumer idempotent |
| **Concurrent conflict** | Hai writer cùng chọn một business key | Điều phối quyền ghi, UNIQUE/transaction, reconciliation |
| **Identity reuse** | Một mã cũ được cấp lại cho đối tượng mới | Kiểm soát vòng đời mã và khóa namespace |
| **Cross-tenant mismatch** | Dòng con của tenant A trỏ đơn tenant B | FK phù hợp hoặc kiểm tra tenant/authorization |

Bộ sinh ID giải quyết **một phần** của bảng trên. Một ID ngẫu nhiên rất khó trùng vẫn không ngăn người dùng nhấn nút đặt hàng hai lần hoặc mạng phát lại cùng request.

## 5. Database sequence: đơn giản nhưng phạm vi cục bộ

Trong một PostgreSQL database, cột identity thường là lựa chọn hợp lý:

~~~sql
CREATE TABLE local_order (
    local_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
);
~~~

Nếu mọi writer dùng **cùng database/sequence**, hệ quản trị cấp các giá trị sequence khác nhau. Nhưng hai database có sequence độc lập đều có thể cấp local_id = 1.

### 5.1. Sequence có những điều không bảo đảm

- Không bảo đảm dãy không có khoảng trống.
- Không bảo đảm thứ tự ID đúng thứ tự COMMIT.
- Không tự đồng bộ giữa database hoặc vùng độc lập.
- Nếu clone/restore database rồi cho hai bản cùng nhận ghi, có thể cấp lại những ID đã tồn tại ở bản còn lại.
- Không giải quyết idempotency của một yêu cầu nghiệp vụ.

### 5.2. Cấp dải số độc quyền

Có thể cấp:

~~~text
HN:  [1,       1.000.000)
HCM: [1.000.000, 2.000.000)
DN:  [2.000.000, 3.000.000)
~~~

Mỗi nơi sinh ID trong dải mình sở hữu. Điều kiện để đúng là **không hai nơi cùng sở hữu một dải tại bất kỳ thời điểm có thể ghi nào**.

Cần một **range allocator** và metadata bền vững: dải đã cấp, owner, trạng thái cấp phát, ngày hết hạn/thu hồi nếu có và lịch sử phục hồi. Khi node bị clone hoặc mất mạng, không được cấp lại dải cho node mới trong khi node cũ còn quyền tạo ID.

Ưu điểm là ID vẫn dạng số và không cần gọi trung tâm cho mỗi bản ghi. Nhược điểm là quản trị dải, hết dải, chuyển vùng và phục hồi phức tạp.

### 5.3. Odd/even hoặc bước nhảy

Hai vùng có thể dùng số lẻ và số chẵn. Cách này chỉ an toàn khi số vùng, offset và bước nhảy được cấp **độc quyền và không thay đổi tùy tiện**. Thêm vùng thứ ba, tái tạo node hoặc backup có thể phá giả định.

Không nên dùng giải pháp bước nhảy nếu chưa có bảng đăng ký/qui trình thay đổi cấu hình và kiểm chứng giới hạn số lượng vùng.

## 6. Khóa ghép có namespace: giữ local ID nhưng tránh xung đột

Khi dữ liệu đã có local_id và nguồn có namespace ổn định, có thể sử dụng:

~~~text
PRIMARY KEY(origin_region, local_id)
~~~

Ví dụ:

~~~sql
CREATE TABLE regional_order (
    origin_region text NOT NULL,
    local_order_id bigint NOT NULL,
    tenant_id bigint NOT NULL,
    created_at timestamptz NOT NULL,

    PRIMARY KEY (origin_region, local_order_id)
);
~~~

**origin_region** nên là mã nơi khởi tạo **không đổi**, không phải tên vùng đang lưu bản ghi. Nếu dữ liệu được chuyển từ shard HN sang shard HCM, identity vẫn là (HN, 1001).

### 6.1. Khi nào hợp lý?

- Cần tích hợp legacy database có số tự tăng cục bộ.
- Có thể bảo đảm namespace của từng nguồn không trùng hoặc tái sử dụng sai.
- API, query và FK có thể xử lý khóa ghép.
- Không nhất thiết cần một ID dạng đơn nhất cho mọi hệ thống ngoài.

### 6.2. Đánh đổi

- Mọi child table phải lưu **đủ hai thành phần**; chỉ lưu local_id vẫn có nguy cơ trỏ sai.
- Chỉ mục và JOIN có thể lớn hơn khóa bigint đơn.
- Không được đổi origin_region theo tên hiển thị hoặc vị trí vật lý hiện tại.
- Một vùng được clone để cả hai cùng ghi với cùng namespace sẽ gây trùng dù cấu trúc khóa đúng.
- Nếu một bản ghi đã được sao chép sang vùng thứ hai, cần biết đó là bản sao cùng đối tượng hay một bản ghi mới.

Có thể giữ khóa ghép nguồn làm **UNIQUE** và thêm global UUID làm **PRIMARY KEY** tại trung tâm để đơn giản hóa FK.

## 7. UUIDv4: phát ID phân tán bằng tính ngẫu nhiên

UUID phiên bản 4 có khoảng **122 bit ngẫu nhiên**, số bit còn lại phục vụ version/variant. Mỗi nút có thể tạo ID độc lập nếu dùng **bộ sinh ngẫu nhiên mật mã đáng tin**.

### 7.1. Vì sao hữu ích?

- Thiết bị di động có thể tạo ID khi không có mạng.
- Nhiều vùng không cần xin worker ID hoặc dải số trước mỗi lần tạo.
- Không phụ thuộc vào clock để xác định phần ngẫu nhiên của ID.
- Định dạng UUID 128 bit được nhiều ngôn ngữ, API và database hỗ trợ.
- Dữ liệu có thể đồng bộ sau mà không đổi khóa cha–con nếu client giữ nguyên UUID.

### 7.2. Xác suất va chạm

Nếu có N giá trị ngẫu nhiên có thể tạo và n lần tạo độc lập, xấp xỉ xác suất có cặp trùng khi n nhỏ so với căn N là:

~~~text
P(collision) ≈ n(n - 1) / (2N)

UUIDv4:
N ≈ 2^122
n = 1.000.000.000
P ≈ 9,4 × 10^-20
~~~

Đây là xác suất **rất nhỏ** trong mô hình có nguồn ngẫu nhiên chuẩn, không phải một chứng minh toán học rằng không thể trùng. Nếu triển khai dùng seed cố định, RNG yếu, clone trạng thái bộ sinh hoặc cắt ngắn UUID, đánh giá trên không còn hợp lệ.

Vì vậy:

1. Dùng thư viện UUID uy tín với nguồn entropy phù hợp.
2. Không rút bớt bit chỉ để có mã ngắn mà không đánh giá lại rủi ro.
3. Lưu ID một lần khi tạo, dùng lại khi retry.
4. Vẫn để database áp PRIMARY KEY/UNIQUE.
5. Định nghĩa cách xử lý nếu hiếm khi có xung đột: không ghi đè bản ghi khác.

### 7.3. UUIDv4 không cho biết thứ tự

UUIDv4 không thể dùng để suy ra ngày tạo, thứ tự COMMIT hoặc thứ tự sự kiện. Nếu API cần tìm đơn mới nhất, lưu **created_at** và các thông tin thứ tự phù hợp, không dùng MAX(order_id).

## 8. UUIDv7 và ULID: có yếu tố thời gian nhưng không phải đồng hồ toàn cục

UUIDv7 dùng **timestamp Unix millisecond** ở phần đầu cùng phần random/counter. ULID dùng một bố cục có **48 bit timestamp millisecond** và **80 bit ngẫu nhiên**, thường biểu diễn dạng **26 ký tự base32**.

Chúng đều có thể sinh tại nhiều nơi, thường cho ID có khả năng **sắp xếp gần theo thời gian** và có locality tốt hơn UUIDv4 trong chỉ mục B-tree.

| Tính chất | UUIDv4 | UUIDv7 | ULID |
|---|---|---|---|
| Kích thước dữ liệu logic | 128 bit | 128 bit | 128 bit |
| Có phần timestamp | Không | Có | Có |
| Có thể sinh offline | Có | Có nếu bộ sinh đúng | Có nếu bộ sinh đúng |
| Thứ tự gần thời gian | Không | Có, tùy clock/counter | Có, tùy clock/counter |
| Phụ thuộc clock cho bố cục | Không | Có | Có |
| Bảo đảm thứ tự COMMIT toàn cục | Không | Không | Không |

### 8.1. Những gì timestamp trong ID không chứng minh

- Hai server có thể có đồng hồ lệch.
- Một server có thể quay lùi đồng hồ.
- Nhiều ID có thể được tạo cùng một millisecond.
- Transaction tạo ID trước nhưng COMMIT sau transaction khác.
- Một sự kiện có hiệu lực hồi tố không mang thời gian hiệu lực trong phần timestamp của ID.
- Một thiết bị offline có thể có clock sai ngày, dù ID vẫn không trùng.

Một số bộ sinh hỗ trợ **monotonic** trong cùng tiến trình hoặc cùng millisecond. Cần đọc phạm vi cam kết của thư viện; **monotonic cục bộ không đồng nghĩa monotonic qua mọi vùng**.

### 8.2. Tiêu chí chọn

Nếu API/database hỗ trợ kiểu UUID và muốn ID gần sắp xếp theo thời gian, UUIDv7 là một lựa chọn đáng cân nhắc. Nếu dùng ULID dạng chuỗi, phải thống nhất cách viết hoa/thường, encoding và cách lưu/so sánh.

Không mặc định mọi phiên bản PostgreSQL đều có sẵn hàm tạo UUIDv7. Trong ví dụ dưới đây, **ID do ứng dụng hoặc thành phần phát ID đã được kiểm chứng cấp**, sau đó bind vào tham số SQL.

**Mốc thời gian nghiệp vụ và commit** phải lưu/định nghĩa riêng, không phân tích từ ID rồi coi đó là sự thật có thẩm quyền.

## 9. Snowflake ID: số nguyên từ timestamp, worker và sequence

Một biến thể Snowflake có thể phân 64 bit như sau:

~~~text
| 1 bit dấu | 41 bit elapsed milliseconds | 10 bit worker | 12 bit sequence |
~~~

Ví dụ này cho khả năng biểu diễn:

- Khoảng **69,7 năm** thời gian từ custom epoch với 41 bit.
- Tối đa **1.024 worker ID** với 10 bit.
- Tối đa **4.096 sequence value** trong một millisecond trên từng worker với 12 bit.

Công thức ghép bit:

~~~text
id = (elapsed_ms << 22)
   | (worker_id << 12)
   | sequence
~~~

Các con số là **giới hạn logic của bố cục bit**, không phải thông lượng đảm bảo ở database hay hạ tầng.

### 9.1. Worker ID phải độc quyền

Nếu HN và HCM cùng phát ID bằng **worker_id = 17**, đồng hồ cùng millisecond và sequence cùng giá trị, hai ID có thể trùng.

Một hostname, PID hoặc địa chỉ IP không tự là worker ID độc quyền. Container có thể clone, VM restore, IP bị tái sử dụng hoặc nhiều datacenter đặt cùng cấu hình.

Cần registry/allocator với cơ chế:

- Cấp worker ID không giao nhau.
- Lease, gia hạn và trạng thái owner khi phù hợp.
- **Fencing** để node đã mất lease không tiếp tục ghi bằng quyền cũ.
- Xử lý khi lease hết hạn nhưng node cũ vẫn chạy.
- Phục hồi sau restart không dùng lại tổ hợp timestamp/worker/sequence đã phát.

### 9.2. Clock rollback và sequence overflow

**Clock rollback:** worker sinh ID ở millisecond T rồi hệ thống lùi về T−10. Nếu thuật toán đặt lại sequence và dùng timestamp cũ, tổ hợp thời gian/worker/sequence có thể lặp.

Các lựa chọn: tạm ngừng đến khi clock bắt kịp, sử dụng đồng hồ logic đơn điệu trong giới hạn đã xác minh, hoặc từ chối cấp ID và cảnh báo. Không âm thầm phát lại ID cũ.

**Sequence overflow:** hết 4.096 giá trị trong một millisecond/worker thì chờ millisecond tiếp theo hoặc áp cơ chế an toàn; **không wrap về 0** trong cùng timestamp.

### 9.3. ID Snowflake gần tăng theo thời gian, không theo COMMIT

Một transaction sinh ID trước có thể commit sau. Clock các node cũng có thể lệch. Không dùng **MAX(snowflake_id)** làm bằng chứng về lần cập nhật đã COMMIT cuối cùng hoặc event có hiệu lực muộn nhất.

Snowflake thường hợp khi cần **bigint gọn** với lưu lượng cao và sẵn sàng đầu tư cho việc quản trị worker/clock. Với mobile offline không có cách cấp worker ID an toàn, UUID thường thuận tiện hơn.

## 10. Dịch vụ cấp ID trung tâm và tính sẵn sàng

Một ID service có thể cấp một ID mới trên mỗi request hoặc cấp dải cho từng worker.

~~~mermaid
flowchart TD
    HN["Writer HN"] --> G["ID service / range allocator"]
    HCM["Writer HCM"] --> G
    ETL["ETL importer"] --> G
    G --> R["Registry cấp phát bền vững"]
    HN --> D1["Lưu đơn tại HN"]
    HCM --> D2["Lưu đơn tại HCM"]
~~~

Ưu điểm là có thể phối hợp không gian khóa và cấp ID dạng số. Nhưng phải cân nhắc:

- Độ trễ network trên đường tạo bản ghi.
- Khi service lỗi, worker chưa có dải có thể phải dừng tạo ID.
- State cấp phát, failover và restore có thể gây cấp lại dải nếu thiết kế sai.
- Lease phải ngăn owner cũ và mới cùng cấp trong một thời điểm.
- ID đã cấp nhưng giao dịch rollback có thể trở thành lỗ hổng số.
- Service cấp ID **không tự bảo đảm** lệnh nghiệp vụ được chấp nhận hoặc giao dịch đã commit.

Nếu yêu cầu hoạt động ngoại tuyến lâu, có thể cấp dải từ trước, nhưng cần quản trị thiết bị bị mất, bản sao backup, dải hết và thời điểm thu hồi.

## 11. Bảng quyết định chọn chiến lược ID

| Yêu cầu | Lựa chọn thường phù hợp | Lưu ý kiểm chứng |
|---|---|---|
| Một database ghi tập trung | Identity/sequence | Không giả định liên tục hoặc đúng commit order |
| Nhiều hệ cũ có sequence riêng | (origin_id, local_id) hoặc crosswalk | Namespace ổn định, không tái dùng sai |
| Nhiều client offline tự tạo đơn | UUIDv4/UUIDv7/ULID | RNG, clock và lưu ID bền qua retry |
| Phải dùng số nguyên 64 bit | Snowflake hoặc allocator | Cấp worker/dải, clock rollback |
| Cấp số có thẩm quyền trung tâm | ID service | HA, delay, fencing và phục hồi |
| Cần chống lặp request | Idempotency key | Payload, scope và response replay |
| Cần sequence sự kiện của một đơn | (aggregate_id, version) | Expected-version và transaction |
| Cần canonical ID qua nhiều CRM | Identity mapping | Không suy trùng thực thể từ trùng tên |
| Bảng phân vùng theo ngày | PK có partition key, registry khi cần | Kiểm tra giới hạn unique toàn cục |

Không chọn công nghệ trước khi thống nhất **phạm vi uniqueness, khả năng mất kết nối, tần suất ghi, loại truy vấn, độ dài khóa và quy trình migration**.

## 12. Mô hình PostgreSQL: order ID toàn cục và mã nguồn

Ví dụ hệ thống nhận đơn từ nhiều POS/ERP/mobile; mỗi nơi tạo global UUID đã xác minh.

~~~sql
CREATE TABLE customer_order (
    order_id uuid PRIMARY KEY,
    tenant_id bigint NOT NULL,
    source_system text NOT NULL,
    source_order_key text NOT NULL,
    status_code text NOT NULL
        CHECK (status_code IN (
            'CREATED', 'CONFIRMED', 'CANCELLED', 'COMPLETED'
        )),
    created_at timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT uq_order_source_key
        UNIQUE (tenant_id, source_system, source_order_key),

    CONSTRAINT ck_source_not_blank
        CHECK (length(btrim(source_system)) > 0),

    CONSTRAINT ck_order_key_not_blank
        CHECK (length(btrim(source_order_key)) > 0)
);

CREATE INDEX idx_order_tenant_created
    ON customer_order (tenant_id, created_at DESC);
~~~

| Thành phần | Bảo vệ |
|---|---|
| **PRIMARY KEY(order_id)** | Không có hai hàng cùng UUID trong database này |
| **UNIQUE(tenant_id, source_system, source_order_key)** | Một mã đơn nguồn tương ứng tối đa một hàng trong cùng tenant/nguồn |
| **NOT NULL** | Khóa nguồn không bỏ trống bằng NULL |
| **CHECK** | Ngăn chuỗi rỗng chỉ có khoảng trắng và trạng thái ngoài tập |
| **INDEX(tenant_id, created_at)** | Truy vấn đơn theo tenant/khoảng thời gian |

Cả PK và UNIQUE chỉ có phạm vi **database chứa bảng**. Nếu hai vùng lưu đơn trên hai database riêng, mỗi database đều có thể chấp nhận cùng source key trước khi đồng bộ. UUID độc lập làm rủi ro trùng ID rất thấp nhưng **không ngăn trùng request nghiệp vụ xuyên vùng**.

### 12.1. Khóa ghép theo tenant có đủ không?

~~~sql
CREATE TABLE tenant_local_order (
    tenant_id bigint NOT NULL,
    local_id bigint NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, local_id)
);
~~~

Khóa trên chỉ an toàn khi mọi writer của cùng tenant được **phối hợp cấp local_id**. Nếu HN và HCM cùng ghi cho tenant 1 với hai sequence đều bắt đầu từ 1, cặp (tenant_id=1, local_id=1) vẫn bị trùng khi hợp nhất.

### 12.2. ID không thay thế phân quyền

API phải kiểm tra tenant và quyền đối tượng:

~~~sql
SELECT order_id, status_code
FROM customer_order
WHERE tenant_id = :tenant_id
  AND order_id = :order_id;
~~~

Các dấu hai chấm là tham số ứng dụng. UUID khó đoán không phải token quyền truy cập, không thể thay kiểm tra authorization.

## 13. Idempotency: UUID không giải quyết retry duplicate

Giả sử mobile gửi **CreateOrder**, database commit nhưng response bị mất. Mobile gửi lại. Nếu server tạo UUID khác và lưu đơn thứ hai, cả hai UUID đều không trùng, nhưng **một yêu cầu đã tạo hai đơn**.

Cần **request_id** do client phát một lần cho mỗi thao tác, giữ nguyên qua các lần gửi lại.

~~~sql
CREATE TABLE order_create_request (
    tenant_id bigint NOT NULL,
    client_id text NOT NULL,
    request_id uuid NOT NULL,
    payload_fingerprint text NOT NULL,
    order_id uuid NOT NULL UNIQUE
        REFERENCES customer_order(order_id),
    created_at timestamptz NOT NULL DEFAULT statement_timestamp(),

    PRIMARY KEY (tenant_id, client_id, request_id)
);
~~~

Một request ID phải có **phạm vi và thời gian giữ**. Cùng một request_id nhưng payload khác cần báo **conflict**, không âm thầm coi là cùng lệnh; fingerprint phải được tính từ những trường nghiệp vụ đã chuẩn hóa.

### 13.1. Giao thức ghi phải nguyên tử

1. Kiểm tra tenant, actor, nguồn và request_id.
2. Trong transaction, chiếm khóa idempotency hoặc khóa business key theo giao thức cạnh tranh.
3. Tạo một order với global_order_id mới khi request thực sự chưa được xử lý.
4. Lưu kết quả idempotency liên kết cùng order_id.
5. Commit nguyên tử nếu cả hai bảng ở cùng database.
6. Nếu key đã tồn tại, kiểm tra payload rồi trả lại **order_id/kết quả cũ**, không INSERT đơn khác.
7. Nếu có workflow nhiều giai đoạn, lưu trạng thái xử lý và quy tắc retry phù hợp.

Với nguồn có **source_order_key** đáng tin, có thể dùng:

~~~sql
INSERT INTO customer_order (
    order_id, tenant_id, source_system, source_order_key, status_code
)
VALUES (
    :generated_order_id, :tenant_id, :source_system,
    :source_order_key, 'CREATED'
)
ON CONFLICT (tenant_id, source_system, source_order_key)
DO NOTHING
RETURNING order_id;
~~~

Khi không trả hàng, thực hiện **SELECT ở lệnh tiếp theo** để lấy bản ghi đã tồn tại và so khớp nghiệp vụ. Không coi mọi unique conflict đều là một retry hợp lệ; có thể là lỗi mapping hoặc client dùng lại mã cho đơn khác.

### 13.2. Đồng bộ đa vùng cần ràng buộc cùng phạm vi

Nếu cùng request_id được gửi tới HN và HCM lúc mạng hai vùng đứt, mỗi vùng có thể **tự chấp nhận** vì UNIQUE của mình không nhìn thấy vùng kia. Muốn bảo đảm chỉ một đơn có thẩm quyền, cần:

- Route request về một **single writer** của phạm vi khóa.
- Phối hợp qua global registry/consensus khi kết nối cho phép.
- Hoặc cho phép ghi **provisional** và reconcile sau; không quảng cáo tính duy nhất mạnh tại mọi thời điểm.

Chọn UUIDv7 thay vì UUIDv4 không tự giải quyết cuộc đua nghiệp vụ ấy.

## 14. Event ID, aggregate version và phát lại thông điệp

Một đơn có thể phát các sự kiện:

~~~text
order_id = UUID-ORDER

event_id=UUID-E1, aggregate_version=1: OrderCreated
event_id=UUID-E2, aggregate_version=2: PaymentConfirmed
event_id=UUID-E3, aggregate_version=3: OrderShipped
~~~

Cùng một event được broker giao lại phải **giữ nguyên event_id**, khác với việc tạo event mới cho lần thay đổi nghiệp vụ mới.

~~~sql
CREATE TABLE order_domain_event (
    event_id uuid PRIMARY KEY,
    order_id uuid NOT NULL REFERENCES customer_order(order_id),
    aggregate_version bigint NOT NULL
        CHECK (aggregate_version >= 1),
    event_type text NOT NULL,
    event_payload jsonb NOT NULL,
    accepted_at timestamptz NOT NULL DEFAULT statement_timestamp(),

    UNIQUE (order_id, aggregate_version)
);
~~~

**UNIQUE(order_id, aggregate_version)** ngăn hai thay đổi chiếm cùng version trong database. Nó không tự bảo đảm mọi version liên tiếp 1, 2, 3 không thiếu; phải có giao thức append theo expected_version và kiểm tra replay.

### 14.1. Outbox và consumer idempotent

Nếu transaction nghiệp vụ commit rồi việc gửi message qua broker thất bại, một hệ thống có thể mất event nếu chỉ gửi trực tiếp sau commit mà không có retry bền.

**Transactional outbox** ghi dữ liệu nghiệp vụ và thông điệp cần gửi trong cùng transaction của database có thẩm quyền. Publisher gửi lại khi lỗi. Vì message có thể giao nhiều lần, consumer dùng event_id hoặc khóa nghiệp vụ phù hợp để deduplicate.

Không tạo event_id mới mỗi lần publisher retry; điều đó biến một sự kiện thành nhiều danh tính và phá khả năng chống trùng.

## 15. Partitioning: UNIQUE trên mỗi phân vùng chưa chắc là toàn cục

Bảng event có thể được **PARTITION BY RANGE(event_ts)** để tối ưu retention. PostgreSQL yêu cầu khóa UNIQUE/PRIMARY KEY trên bảng partitioned gồm khóa phân vùng trong các cấu hình hỗ trợ.

~~~sql
CREATE TABLE partitioned_order_event (
    event_id uuid NOT NULL,
    order_id uuid NOT NULL,
    event_ts timestamptz NOT NULL,
    event_type text NOT NULL,

    PRIMARY KEY (event_ts, event_id)
)
PARTITION BY RANGE (event_ts);

CREATE TABLE order_event_2026_07
PARTITION OF partitioned_order_event
FOR VALUES FROM (
    TIMESTAMPTZ '2026-07-01 00:00:00+00'
) TO (
    TIMESTAMPTZ '2026-08-01 00:00:00+00'
);

CREATE TABLE order_event_2026_08
PARTITION OF partitioned_order_event
FOR VALUES FROM (
    TIMESTAMPTZ '2026-08-01 00:00:00+00'
) TO (
    TIMESTAMPTZ '2026-09-01 00:00:00+00'
);
~~~

**(event_ts, event_id)** là duy nhất trong phạm vi bảng logic được partition đúng. Nhưng event_id đơn lẻ có thể xuất hiện lại với một event_ts khác ở tháng khác.

Tạo UNIQUE(event_id) **riêng trong mỗi partition** chỉ bảo vệ uniqueness **nội bộ partition**. Nó không thể thay một unique constraint toàn cục trên các partition nếu dữ liệu được phép nằm ở kỳ khác nhau.

### 15.1. Registry ID ngoài partition

~~~sql
CREATE TABLE event_identity_registry (
    event_id uuid PRIMARY KEY,
    first_event_ts timestamptz NOT NULL,
    first_order_id uuid NOT NULL,
    payload_fingerprint text NOT NULL
);
~~~

Nếu yêu cầu **event_id duy nhất trong toàn database**, dùng transaction:

1. Thử INSERT event_id vào registry.
2. Nếu trùng, xác nhận metadata/payload rồi trả về trạng thái retry hoặc conflict.
3. Nếu mới, INSERT event vào partitioned_order_event.
4. COMMIT cả hai hoặc ROLLBACK cả hai.

Registry không phân vùng theo event_ts bảo vệ event_id **trong database ấy**, kể cả khi event raw được lưu theo nhiều tháng. Tuy nhiên registry có chi phí ghi/lưu trữ và chính sách retention riêng.

### 15.2. Retention làm thay đổi phạm vi dedup

Nếu raw chỉ giữ 90 ngày, xóa registry cùng kỳ có thể khiến một event gửi lại sau 90 ngày bị nhận như mới. Phải đặt **cửa sổ idempotency** rõ ràng, xem khả năng phát lại của nguồn và giữ registry lâu hơn raw nếu cần.

Một registry cục bộ cũng không tự bảo vệ tất cả database ở những vùng không kết nối. Nếu cần ràng buộc toàn cầu mạnh, phải có cơ chế điều phối hoặc chính sách routing thích hợp.

## 16. Sharding và nhất quán khi nhiều nơi cùng ghi

Nếu toàn bộ dữ liệu của một tenant được route về **một writer có thẩm quyền**, database đó có thể giữ UNIQUE theo tenant + business key. Nhưng nếu hai vùng cùng được ghi cho **cùng phạm vi khóa**, không có UNIQUE cục bộ nào ngăn cả hai cùng chấp nhận một mã khi mất kết nối.

| Mô hình | Cách bảo vệ | Đánh đổi |
|---|---|---|
| **Single writer / owner** | Một nơi chịu trách nhiệm cho khóa | Routing, failover, độ trễ vùng xa |
| **Các namespace không giao nhau** | Mỗi nơi chỉ tạo ID thuộc miền được cấp | Registry namespace/dải và phục hồi |
| **UUID phân tán** | Xác suất va chạm rất nhỏ | Không chứng minh không có duplicate business |
| **Global registry/coordination** | Check-and-reserve khóa ở nơi có thẩm quyền chung | Availability và độ trễ khi phân hoạch mạng |
| **Local provisional + reconciliation** | Chấp nhận cục bộ, xử lý xung đột khi nối lại | Trạng thái tạm, bồi hoàn/xung đột nghiệp vụ |

Không thể cam kết đồng thời **mọi vùng luôn ghi thành công khi bị cô lập** và **mọi yêu cầu trùng cùng business key luôn bị từ chối ngay tại mọi vùng** nếu chúng không có cách phân chia quyền sở hữu khóa trước đó.

### 16.1. Vị trí shard không nên là danh tính bất biến

Một đơn có thể chuyển từ shard A sang shard B để cân bằng tải. **Global_order_id nên giữ nguyên**, còn bảng routing/placement được cập nhật. Nếu mã chứa “current_shard_id” và bị sửa khi chuyển, child FK, log và API có thể mất tham chiếu.

Có thể nhúng **origin namespace** cố định để giúp truy vết, nhưng không dùng vị trí vật lý hiện tại như định danh bất biến.

## 17. Thiết bị offline: tạo một lần, đồng bộ nhiều lần

Một ứng dụng offline cần tạo đơn và dòng đơn trước khi server cấp khóa. Hai mẫu phổ biến:

### 17.1. Client cấp global UUID

~~~text
Mobile:
  order_id = UUID-A
  line_id  = UUID-L1, order_id = UUID-A
  line_id  = UUID-L2, order_id = UUID-A

Server:
  Lưu nguyên order_id = UUID-A
  Lưu child references tới UUID-A
~~~

Ưu điểm là không cần remap FK. Điều kiện:

- Sinh ID bằng thư viện đáng tin.
- **Lưu bền ID vào local storage trước khi gửi**.
- Khi retry, gửi lại cùng ID và request_id.
- Server kiểm tra tenant, quyền, payload và unique constraints.
- ID do client đưa không đồng nghĩa client có quyền truy cập bản ghi.

### 17.2. Client dùng khóa tạm, server cấp global ID

~~~text
(local_installation_id, local_counter=42) -> global_order_id UUID-B
~~~

Server phải lưu bảng ánh xạ ổn định. Khi retry với cùng local key, trả về cùng global ID; mọi dòng đơn, thanh toán, file đính kèm và event liên quan phải được remap đúng.

Nếu app được clone hoặc restore khiến hai thiết bị dùng cùng installation_id và counter, có thể trùng local key. Cần chính sách cấp installation namespace độc lập hoặc chọn UUID sinh cho từng đối tượng.

### 17.3. Không dùng đồng hồ client làm sự thật tuyệt đối

UUIDv7/ULID sinh offline có thể chứa timestamp của máy khách sai ngày. **event_occurred_at**, **server_received_at** và **business_effective_at** nên được định nghĩa riêng khi cần. Không tự đổi global ID sau khi đồng bộ chỉ vì timestamp trong ID có vẻ sai.

## 18. Tính duy nhất của ID và canonical identity là hai lớp khác nhau

Giả sử:

~~~text
CRM-A: customer_id = UUID-1, source_key = C-501
CRM-B: customer_id = UUID-2, source_key = X-118
~~~

Nếu hai nguồn mô tả cùng một khách, việc có hai UUID riêng **không phải collision**, mà là hai biểu diễn của cùng đối tượng nghiệp vụ.

Một bảng ánh xạ:

~~~sql
CREATE TABLE canonical_customer (
    customer_id uuid PRIMARY KEY,
    display_name text
);

CREATE TABLE customer_source_map (
    tenant_id bigint NOT NULL,
    source_system text NOT NULL,
    source_customer_key text NOT NULL,
    customer_id uuid NOT NULL REFERENCES canonical_customer(customer_id),

    PRIMARY KEY (
        tenant_id, source_system, source_customer_key
    )
);
~~~

Nhiều source key có thể trỏ một canonical_customer khi **đã được xác minh**. Nhưng không tự gộp hai hồ sơ chỉ vì họ tên hay email trùng; có thể là người khác nhau hoặc tài khoản dùng chung.

Khi hợp nhất/tách identity, cần giữ quyết định, nguồn, lịch sử mapping và ảnh hưởng tới fact/quan hệ. Khóa kỹ thuật unique chỉ nói “hai hàng khác nhau”; nó không quyết định liệu chúng thực sự thuộc cùng một thực thể.

## 19. Tham chiếu cha–con và ràng buộc xuyên shard

Trong một PostgreSQL database:

~~~sql
CREATE TABLE order_line (
    line_id uuid PRIMARY KEY,
    order_id uuid NOT NULL REFERENCES customer_order(order_id),
    line_no integer NOT NULL CHECK (line_no >= 1),
    quantity integer NOT NULL CHECK (quantity > 0),

    UNIQUE (order_id, line_no)
);
~~~

FK bảo đảm order_id tham chiếu đơn đã tồn tại **trong database chứa constraint**. Nó chưa bảo đảm tenant của line trùng tenant của order nếu schema không kiểm tra, và không tự kiểm tra được một order nằm ở **database khác**.

Khi dữ liệu bị shard:

- **Colocate** order và order_line trong cùng shard theo order_id/tenant để dùng FK cục bộ.
- Dùng validation qua service có thẩm quyền nếu child ở shard khác.
- Cho phép trạng thái pending, rồi reconciliation nếu hệ thống chấp nhận eventual consistency.
- Lưu bảng ánh xạ/routing bền vững để không mất tham chiếu khi chuyển shard.

Một UUID unique không tự giải quyết **referential integrity** hay phân quyền đa tenant. Cần kiểm tra các quan hệ theo đúng phạm vi.

## 20. Hiệu năng, bảo mật và quy tắc thứ tự

| Tính chất | Bigint sequence | UUIDv4 | UUIDv7 / ULID | Snowflake bigint |
|---|---|---|---|---|
| Kích thước logic | 64 bit | 128 bit | 128 bit | 64 bit |
| Sinh độc lập không xin số | Không nếu dùng chung sequence | Có | Có | Có điều kiện worker ID |
| Gần sắp theo thời gian | Thứ tự cấp cục bộ | Không | Thường có | Thường có |
| Phụ thuộc clock | Không ở generator | Không | Có | Có |
| Đánh đổi chính | Điều phối và chuyển vùng | B-tree insert phân tán | Clock/RNG/counter | Node lease, clock, sequence |
| Chứng minh commit order | Không | Không | Không | Không |

### 20.1. Kích thước và index

Trong PostgreSQL, kiểu **uuid** biểu diễn dữ liệu UUID 16 byte; text dạng 36 ký tự khác với lưu UUID native. **bigint** thường gọn hơn. Tuy nhiên kích thước một index entry còn gồm overhead và các cột khác.

UUIDv4 ngẫu nhiên khiến B-tree chèn phân tán, có thể tạo page split/cache miss. UUIDv7 thường có locality tốt hơn, nhưng một khóa tăng dần cũng có thể dồn ghi vào mép phải của index hoặc shard mới nhất. Phải đo trên workload thực tế, không coi “ID có thứ tự” luôn nhanh trong mọi cấu hình.

### 20.2. ID không phải bảo mật

Sequence tăng dần có thể khiến số lượng bản ghi dễ ước đoán. UUIDv7 và Snowflake có thể làm lộ gần đúng **thời gian sinh**, Snowflake còn có thể mã hóa worker ID. UUID khó đoán **không phải token truy cập**; API luôn kiểm tra authorization và tenant.

Không đưa thông tin nhạy cảm (email, số điện thoại, danh tính thiết bị) trực tiếp vào khóa nếu không có lý do và chính sách bảo vệ. Mã nguồn hiện hành có thể bị thay, tái sử dụng hoặc coi là dữ liệu cá nhân.

## 21. Migration từ sequence cục bộ sang global ID

Giả sử hệ thống cũ có hai bảng orders ở HN/HCM, mỗi nơi đã phát local_id = 1001. Không nên “cộng một tỷ vào ID HCM” một cách tùy ý: dải có thể bị vượt, hệ thống thứ ba xuất hiện, bản sao backup được import lại hoặc FK con chưa remap.

Dùng bảng crosswalk:

~~~sql
CREATE TABLE legacy_order_id_map (
    origin_region text NOT NULL,
    legacy_order_id bigint NOT NULL,
    global_order_id uuid NOT NULL UNIQUE,

    PRIMARY KEY (origin_region, legacy_order_id)
);
~~~

Quy trình:

1. **Chốt namespace nguồn**; origin_region phải là nơi tạo ban đầu, không đổi theo vị trí đang lưu.
2. **Kiểm tra local key** và đánh dấu những mã đã bị tái sử dụng.
3. **Phát global ID cho từng danh tính nguồn** bằng generator đã chọn.
4. **Ghi crosswalk** với UNIQUE để retry không tạo mapping mới.
5. **Backfill orders** và tất cả bảng con bằng mapping.
6. **Đối soát FK** cho order lines, payment, shipment, audit và event.
7. **Kiểm tra đơn trùng nghiệp vụ** giữa nguồn: đây là bước identity resolution, không tự gộp theo local_id.
8. **Chuyển đường ghi mới** sang global ID; giữ legacy ID để giải thích chứng từ/API cũ.
9. **Chuyển dần đường đọc**; theo dõi unmatched IDs, duplicates và dữ liệu đến muộn.
10. **Giữ bản mapping bền vững** trong suốt vòng đời các tham chiếu cũ.

Nếu migration cần dual-write sang database khác, phải xử lý thất bại một phía bằng outbox/CDC/retry và reconciliation, không giả định hai database tự có transaction nguyên tử.

### 21.1. Kiểm tra mapping đầy đủ

Bên cạnh đếm số hàng, cần đối soát:

- Mỗi cặp (origin, legacy_id) có đúng một global_id.
- Không có hai cặp nguồn khác đối tượng bị gán cùng global_id ngoài chính sách hợp nhất được duyệt.
- Các dòng con trỏ đúng global_id.
- Giá trị tiền, số dòng đơn và các chứng từ đã chốt không thay đổi sai.
- Retry/backfill nhiều lần không tạo mapping mới.
- Dữ liệu nguồn đến muộn vẫn nhận được mapping phù hợp.

## 22. Kiểm thử concurrency, phân hoạch mạng và lỗi đồng hồ

| Trường hợp | Kết quả mong đợi |
|---|---|
| HN/HCM cùng tạo local_id=1001 | Hai global ID khác nhau hoặc hai cặp origin/local khác nhau |
| Cùng tenant/source/key được gửi lại | Chỉ một kết quả CreateOrder được chấp nhận |
| Cùng request_id nhưng payload khác | Báo conflict, không sửa đơn cũ |
| Hai tenant cùng mã nguồn | Cho phép nếu rule chỉ unique theo tenant |
| UUID trùng với PK đã tồn tại | Từ chối INSERT, không ghi đè |
| Clone thiết bị và counter | Phát hiện namespace trùng hoặc dùng UUID cho mỗi đối tượng |
| Hai Snowflake worker cùng node ID | Fencing/lease ngăn đồng thời phát |
| Snowflake clock lùi | Chờ/fail an toàn, không phát tổ hợp ID đã dùng |
| Tràn 12-bit sequence trong một millisecond | Không wrap, áp chính sách chờ hoặc từ chối |
| Event_id giống nhau khác event_ts trên partition tháng khác | Registry/giao thức dedup ngăn nếu cần global event ID |
| Consumer nhận cùng event hai lần | Không tạo hai thanh toán hoặc hai side effects |
| Chuyển order sang shard khác | Global ID không đổi, routing/FK còn hợp lệ |
| Restore database từ backup | Không tái sử dụng dải/worker state gây collision |
| Cùng khách được nhập ở hai CRM | Identity resolution tách biệt với uniqueness ID |

### 22.1. Kiểm thử bộ sinh

Bộ kiểm thử cần kiểm tra format/version/bit layout, tạo đồng thời với nhiều tiến trình, worker restart, clock drift, rollback, sequence overflow, khả năng cấp lại worker ID và serialize/deserialize qua API/database.

**Không phát hiện duplicate trong một triệu ID không chứng minh tuyệt đối rằng UUIDv4 sẽ không bao giờ trùng.** Độ tin cậy đến từ thuật toán, entropy, điều phối khi cần, ràng buộc và giám sát.

### 22.2. Kiểm thử giao dịch

- Hai transaction cạnh tranh cùng business key: chỉ một kết quả theo UNIQUE hoặc policy.
- Timeout sau COMMIT: retry lấy lại kết quả cũ.
- INSERT registry thành công nhưng INSERT vào bảng partition lỗi: rollback cả hai.
- Khi thay tenant hoặc permission, truy vấn không rò dữ liệu sang tenant khác.
- Khi source gửi cùng event_id với timestamp/payload khác, không tự coi đó là retry giống hệt.

## 23. Vận hành và quan sát lỗi định danh

| Chỉ số | Mục đích |
|---|---|
| ID generated/sec theo node | Dự đoán tải/counter |
| UUID generator errors | Phát hiện nguồn random/implementation lỗi |
| Unique violations theo constraint | Phân biệt collision với retry/mapping sai |
| Idempotency replay và conflict | Nhận biết retry hợp lệ và payload mismatch |
| Clock rollback/skew | Ngăn Snowflake lỗi và timestamp sai |
| Worker lease expiration/fencing | Ngăn trùng worker ID |
| Dải số còn lại | Cảnh báo trước khi hết |
| Registry/dedup size | Quản lý retention và tốc độ ghi |
| Legacy mapping unmapped | Phát hiện lỗi migration |
| Cross-shard invalid references | Phát hiện ràng buộc logic bị phá |
| Provisional records chưa đồng bộ | Độ trễ offline và xung đột chờ giải quyết |
| Event consumer dedup rate | Theo dõi giao message lặp |

Một **unique violation** thường là retry hoặc business key collision hơn là UUID collision ngẫu nhiên. Nên ghi **tên constraint, nguồn và mã yêu cầu** ở mức an toàn để điều tra, không log payload nhạy cảm.

### 23.1. Capacity và rollover

Với Snowflake, số bit timestamp cùng epoch quyết định thời điểm hết không gian thời gian. Phải có kế hoạch nâng định dạng/trạng thái trước mốc đó. Không cho timestamp tự wrap về 0.

Với allocator theo dải, đo số ID còn lại và chuẩn bị dải mới. Với UUID, theo dõi chất lượng bộ sinh và các phiên bản thư viện, đặc biệt khi code chạy trên thiết bị client không do đội vận hành kiểm soát hoàn toàn.

## 24. Bài thực hành: ba nơi tạo đơn, hai database và tablet offline

Một hệ thống bán lẻ hoạt động ở HN, HCM và trên tablet ngoại tuyến. Yêu cầu:

- Đơn có ID ổn định ngay từ lúc tạo.
- Không xung đột ID khi hợp nhất dữ liệu.
- Retry không tạo đơn hoặc thanh toán nhân đôi.
- Đơn và dòng đơn giữ đúng quan hệ.
- Tenant và mã đơn nguồn được lưu để truy vết.
- Có thể phân vùng dữ liệu event theo tháng và giữ raw 90 ngày.
- Một khách hàng có thể có hồ sơ ở hai hệ CRM.
- Trong tương lai có thể di chuyển đơn từ shard này sang shard khác.

### 24.1. Thiết kế tham khảo

Một phương án là:

~~~mermaid
flowchart TD
    A["Tablet offline"] --> U["Global UUID được tạo một lần"]
    HN["POS HN"] --> U
    HCM["POS HCM"] --> U
    U --> L["Lưu order + child với stable ID"]
    L --> X["Đồng bộ kèm idempotency key"]
    X --> C["Kiểm tra namespace / request"]
    C --> O["Nguồn order có thẩm quyền"]
    O --> E["Outbox event giữ nguyên event_id"]
    E --> P["Consumer idempotent / báo cáo"]
~~~

Mô hình có thể dùng:

- **order_id UUIDv4/UUIDv7** tạo một lần và lưu bền.
- **(tenant_id, origin_system, source_order_key)** làm unique business identity trong phạm vi có thẩm quyền.
- **(tenant_id, client_id, request_id)** cho idempotency.
- **line_id UUID** cho từng dòng, FK đến order_id.
- **event_id UUID** riêng cho mỗi event, cùng aggregate_version để bảo vệ thứ tự trong đơn.
- **Source crosswalk** cho ID bigint cũ.
- **Event identity registry** nếu bảng partitioned cần bảo đảm event_id duy nhất xuyên tháng trong cùng database.
- **Canonical customer ID** và bảng source mapping cho duplicate CRM.

Đây là phương án thích hợp cho offline-first nhưng **không tự bảo đảm business uniqueness mạnh khi HN/HCM cùng ghi một source key trong lúc mất kết nối**. Phải có single authority, phân vùng quyền cấp khóa hoặc trạng thái provisional/reconciliation.

### 24.2. Câu hỏi thực hành

1. Viết riêng invariant cho global_order_id, source_order_key, request_id, event_id và order_number.
2. Giải thích vì sao hai local_id 1001 không đồng nghĩa hai đơn trùng nhau.
3. Chọn UUIDv4, UUIDv7, Snowflake hoặc composite key; phân tích offline, index và điều phối.
4. Nếu dùng Snowflake, phân chia worker ID thế nào và node mất lease phải làm gì?
5. Thiết kế bảng orders/lines cùng UNIQUE/FK và khóa tenant thích hợp.
6. Mô tả retry CreateOrder năm lần với cùng request_id nhưng response bị mất lần đầu; phải có một đơn.
7. Xử lý tình huống request_id trùng nhưng payload khác, và tình huống cùng nguồn tạo hai request khác nhau cho một mã đơn.
8. Giải thích vì sao PK UUID không ngăn hai hồ sơ cùng khách.
9. Nếu vùng HN và HCM cùng nhận một đơn khi phân hoạch mạng, chính sách nguồn có thẩm quyền là gì?
10. Khi partition event theo event_ts, UNIQUE(event_id) toàn kỳ được bảo vệ thế nào?
11. Khi đồng bộ tablet, order_line trỏ order_id nào và cần remap trong trường hợp nào?
12. Khi chuyển shard, vì sao global_order_id nên giữ nguyên?
13. Thiết kế crosswalk cho hai nguồn legacy đều có local_id 1001.
14. Đề xuất ma trận kiểm thử clock rollback, node ID duplicate, retry, partition, consumer replay và migration.
15. Trình bày cách phân quyền tenant; giải thích vì sao ID khó đoán không đủ bảo vệ API.

**Tiêu chí đạt:** phạm vi unique được tuyên bố; chiến lược ID phù hợp offline và đồng bộ; phân biệt collision với retry/duplicate entity; có ràng buộc kiểm tra ở nơi có thẩm quyền; tham chiếu và idempotency không bị phá khi phân vùng hoặc chuyển shard.

## 25. Checklist phê duyệt thiết kế

- **Phạm vi:** ID phải unique trong một database, tenant, nguồn, vùng hay toàn hệ thống?
- **Danh tính:** business key, global ID, request ID, event ID và mã chứng từ có vai trò riêng chưa?
- **Nơi cấp ID:** mọi writer có quyền phát từ cùng một không gian mà không trùng chưa?
- **Offline:** ID và request key được sinh một lần rồi lưu bền trước khi gửi chưa?
- **UUID:** RNG và format đúng, không cắt bit không kiểm soát, có xử lý lỗi PK không?
- **Snowflake:** worker lease/fencing, clock rollback, sequence overflow và rollover đã được định nghĩa chưa?
- **Namespace:** origin/tenant/source có độc quyền, ổn định, không bị tái sử dụng ngoài chính sách không?
- **Database:** PRIMARY KEY/UNIQUE thực thi tại phạm vi thực tế nào?
- **Partition:** event_id có cần registry toàn database, hay uniqueness của (event_ts,event_id) là đủ?
- **Idempotency:** payload giống trả kết quả cũ, payload khác báo conflict, retry consumer không gây side effect kép?
- **Phân tán:** nếu hai vùng cùng ghi khi mất kết nối, business-key conflict được điều phối hay reconciled thế nào?
- **Quan hệ:** FK/order_line và tenant isolation đúng cả khi dữ liệu ở nhiều shard?
- **Identity resolution:** nhiều hệ cùng tạo hồ sơ một đối tượng có canonical mapping và quyết định hợp nhất có chứng cứ không?
- **Migration:** legacy ID có crosswalk, mọi child FK được remap, dữ liệu đến muộn được xử lý?
- **Thứ tự:** không dùng số ID làm commit order hoặc thời gian hiệu lực khi thuật toán không bảo đảm?
- **Bảo mật:** API kiểm tra tenant/authorization, không coi ID ngẫu nhiên là access token?
- **Vận hành:** quan sát unique violations, worker leases, clock skew, dải số, registry và lỗi đồng bộ?

**Kết luận:** định danh được tạo tại nhiều nơi chỉ đáng tin khi có **phạm vi duy nhất, cơ chế cấp phát, ràng buộc kiểm tra, chính sách đồng bộ và cách phục hồi** rõ ràng. UUID giúp tạo ID độc lập với xác suất va chạm rất thấp; Snowflake giúp tạo số nguyên gọn nhưng cần quản trị worker và đồng hồ; khóa ghép hay cấp dải số dựa vào namespace không giao nhau. Dù chọn cách nào, **ID không trùng vẫn không tự ngăn retry tạo tác dụng lặp, không giải quyết hồ sơ cùng đối tượng và không thay thế ràng buộc giao dịch hoặc phân quyền**. Đây là những phần phải được mô hình hóa và kiểm chứng độc lập.
