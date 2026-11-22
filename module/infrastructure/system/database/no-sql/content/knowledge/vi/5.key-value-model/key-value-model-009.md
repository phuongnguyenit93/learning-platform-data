# Điểm nóng trên một khóa và cách chia tải theo nghiệp vụ trong mô hình khóa–giá trị

## 1. Tình huống: hệ thống có nhiều khóa nhưng vẫn bị quá tải

Giả sử một dịch vụ xem video lưu số lượt xem trong cơ sở dữ liệu khóa–giá trị (key–value):

```text
video:V101:views  ->  12_345
video:V102:views  ->   8_200
video:V999:views  -> 825_000
```

Mỗi lượt xem video `V999` gọi lệnh tăng bộ đếm:

```redis
INCR video:V999:views
```

Nếu video `V999` bất ngờ nổi tiếng và nhận hàng chục nghìn lượt xem mỗi giây, **phần lớn thao tác ghi dồn vào đúng một khóa**. Dù hệ thống lưu hàng triệu khóa khác nhau và có nhiều nút (node), thao tác trên `video:V999:views` vẫn phải đi tới nơi đang sở hữu khóa đó. Nút sở hữu khóa có thể trở thành nút quá tải trong khi những nút khác còn dư tài nguyên.

Hiện tượng này gọi là **hot key (khóa nóng)**. Khi áp lực tập trung vào phân vùng hoặc nút lưu khóa, người ta cũng nói tới **hot partition** hoặc **hot shard**. Ba khái niệm có liên quan nhưng không hoàn toàn đồng nghĩa:

- **Hot key:** một khóa được truy cập với tần suất, độ đồng thời hoặc chi phí xử lý vượt trội.
- **Hot partition:** một phân vùng chịu tải lớn; có thể do một khóa rất nóng hoặc do nhiều khóa cùng thuộc phân vùng đó.
- **Hot node:** một máy chủ quá tải; nguyên nhân có thể là một hoặc nhiều phân vùng, truy vấn nặng, dung lượng, mạng hoặc tình trạng phân bố tài nguyên không cân bằng.

Trong mô hình key–value, thiết kế khóa tốt phải trả lời được hai câu hỏi: **làm sao tìm đúng dữ liệu bằng khóa**, và **làm sao phân bố khối lượng công việc nếu một đối tượng nghiệp vụ trở nên đặc biệt phổ biến**.

## 2. Vì sao nhiều node không tự động giải quyết một khóa nóng?

Một hệ key–value phân tán thường dùng thuật toán băm (hash) hoặc quy tắc phân vùng để ánh xạ khóa sang một phần của cụm máy.

```text
                  hash(key)
                      |
                      v
                partition/slot
                      |
                      v
                  owner node

client A ─┐
client B ─┼──> video:V999:views ───> shard 7 ───> node B
client C ─┘

video:V101:views ───> shard 2 ───> node A
video:V102:views ───> shard 9 ───> node C
```

Phân phối nhiều khóa theo hash thường giúp cân bằng **số lượng khóa**, nhưng không đảm bảo cân bằng **số yêu cầu mỗi giây**. Nếu 80% lưu lượng cùng truy cập một khóa, thì dữ liệu đó vẫn chỉ có một giá trị khóa logic. Việc thêm node không đồng nghĩa thao tác ghi lên khóa ấy được chia đều sang tất cả node.

Một replica có thể hỗ trợ đọc tùy cách cấu hình hệ thống, nhưng **ghi vào một giá trị duy nhất** vẫn bị ràng buộc bởi cơ chế ghi và nhất quán của hệ. Ví dụ, ở một cụm Redis Cluster, mỗi key được gán vào một hash slot; theo cấu hình thông thường, thao tác ghi trên key đó đi tới primary đang sở hữu slot. Tăng số primary mà không đổi cách đặt khóa không tự động chia một key thành nhiều nơi ghi độc lập.

### Đọc nóng và ghi nóng khác nhau

| Kiểu tải | Ví dụ | Rủi ro chính | Hướng xử lý nổi bật |
|---|---|---|---|
| **Đọc nóng** | Mọi người xem hồ sơ một ngôi sao | QPS đọc vào một khóa/nút cao, tăng độ trễ | Cache gần ứng dụng, bản sao phục vụ đọc, giới hạn yêu cầu lặp |
| **Ghi nóng** | Mọi lượt xem tăng một bộ đếm | Nhiều lệnh ghi tranh chấp cùng khóa, dồn lên owner | Chia bộ đếm thành nhiều khóa, gom sự kiện, cập nhật theo lô |
| **Đọc và ghi đều nóng** | Số lượng hàng còn lại của vé đang mở bán | Vừa quá tải vừa có yêu cầu nhất quán | Điều tiết tải, tách luồng đọc, thiết kế điều phối ghi chặt chẽ |
| **Nóng theo khách hàng (tenant)** | Một doanh nghiệp có lượng giao dịch vượt trội | Khóa hoặc phân vùng theo tenant bị lệch tải | Chia tiếp theo đơn hàng, miền nghiệp vụ hoặc thời gian |

Vì giải pháp cho đọc và ghi khác nhau, cần xác định thành phần nào đang thực sự bão hòa trước khi thay đổi mô hình dữ liệu.

## 3. Nhận biết điểm nóng bằng số liệu

Một số dấu hiệu thường gặp:

1. Độ trễ p95/p99 tăng mạnh trên một nhóm request, trong khi tổng tài nguyên của cụm chưa đầy.
2. CPU, băng thông mạng, số lệnh hoặc hàng đợi của một node cao hơn đáng kể so với các node còn lại.
3. Một vài khóa xuất hiện rất nhiều lần trong log/tracing hoặc trong thống kê top keys theo tần suất.
4. Có nhiều timeout hoặc retry đến cùng một partition; retry tự động có thể làm hiện tượng quá tải nặng hơn.
5. Những thao tác như tăng counter, cập nhật trạng thái hoặc đọc giá trị lớn tập trung quanh cùng một đối tượng nghiệp vụ.

Hãy phân biệt **hot key** với **big key**:

- *Hot key* là khóa có lưu lượng cao; giá trị có thể rất nhỏ, ví dụ một số nguyên.
- *Big key* là khóa chứa giá trị lớn, ví dụ một danh sách khổng lồ; dù ít request, mỗi request vẫn có thể tốn CPU, RAM hoặc mạng.
- Một khóa có thể vừa nóng vừa lớn, khiến vấn đề nghiêm trọng hơn.

Thông số cần quan sát gồm request/giây theo khóa hoặc nhóm khóa, tỷ lệ đọc/ghi, số thao tác đồng thời, kích thước giá trị, thời gian xử lý lệnh, phân bố tải theo node/partition, tỷ lệ cache hit, timeout và độ trễ cuối đuôi.

**Không nên đưa toàn bộ tên khóa hay dữ liệu nhạy cảm lên log sản xuất.** Có thể ghi nhãn nhóm khóa, định danh đã băm và các thống kê lấy mẫu đủ để phát hiện điểm nóng.

## 4. Lựa chọn cách chia tải dựa trên nghiệp vụ

Không phải khóa nào cũng được phép chia. Cần xem **ý nghĩa của giá trị** và **mức nhất quán nghiệp vụ yêu cầu**.

| Kiểu giá trị | Có thể chia như thế nào? | Điều kiện cần lưu ý |
|---|---|---|
| Số lượt xem, số click, bộ đếm thống kê | Nhiều shard counter, tổng hợp khi đọc | Cho phép độ trễ thống kê, có cơ chế xử lý sự kiện trùng |
| Bản tin cấu hình được đọc liên tục | Bản sao/cache tại vùng hoặc tiến trình | Chấp nhận dữ liệu cũ trong thời gian ngắn, có invalidation |
| Danh sách hoạt động của một khách hàng | Chia theo khách hàng + thời gian hoặc nhóm sự kiện | Cần biết cách lấy nhiều phân vùng và sắp thứ tự |
| Dữ liệu từng đơn hàng | Chia theo `orderId` thay vì gom mọi đơn vào một khóa tenant | Truy vấn theo tenant cần index hoặc phương án truy cập khác |
| Số dư tài khoản phải chính xác tức thời | Chỉ chia ghi nếu có giao thức kiểm soát nhất quán rõ ràng | Không được cộng trừ tùy ý trên các bản sao độc lập |
| Vé còn lại hoặc hàng tồn giới hạn | Có thể cấp phát quota theo vùng/nhóm nếu bảo toàn tổng | Phải ngăn bán vượt số lượng khi cạnh tranh đồng thời |

Một quy tắc thực dụng: **tách đọc đối với dữ liệu hay được xem; tách phần ghi độc lập đối với dữ liệu có thể phân tán; giữ một cơ chế điều phối rõ ràng đối với bất biến mạnh của nghiệp vụ**.

## 5. Xử lý khóa nóng do đọc: đưa dữ liệu lại gần người dùng

### 5.1. Cache nhiều lớp

Giả sử `product:P100:detail` được đọc liên tục nhưng chỉ thay đổi vài lần mỗi ngày. Có thể thiết kế:

```text
Client
  |
  v
Application instance ──> Local in-memory cache (TTL ngắn)
  | cache miss
  v
Distributed cache / read replica
  | cache miss
  v
Source of truth
```

Cache trong tiến trình của từng instance giúp nhiều lượt xem sản phẩm không phải đồng loạt hỏi cùng một khóa Redis. CDN/edge cache phù hợp cho dữ liệu công khai, có thể cache theo HTTP; read replica có thể hỗ trợ một số hệ thống, nhưng phải hiểu độ trễ đồng bộ và quy tắc đọc của hệ đang dùng.

Ví dụ mô tả luồng đọc:

```text
readProduct("P100"):
    if localCache.containsFresh("P100"):
        return localCache.get("P100")

    value = distributedCache.get("product:P100:detail")
    if value is absent:
        value = sourceDatabase.loadProduct("P100")
        distributedCache.put("product:P100:detail", value, ttl)

    localCache.put("P100", value, shortTtl)
    return value
```

Đây là pseudocode; hệ thống thực tế cần xử lý lỗi, giới hạn thời gian và tính nhất quán phù hợp.

### 5.2. Chống cache stampede

Khi dữ liệu phổ biến hết TTL, hàng nghìn request có thể cùng thấy cache miss và đồng loạt truy cập nguồn. Đây là **cache stampede**.

Các cách giảm:

- **Request coalescing / single-flight:** với cùng một key, trong một instance chỉ một request tải lại, các request còn lại dùng chung kết quả.
- **TTL jitter:** thêm độ lệch ngẫu nhiên vào TTL của các khóa để nhiều khóa không hết hạn đồng loạt. Với một khóa cực nóng, jitter riêng lẻ không đủ; cần phối hợp thêm cơ chế gộp yêu cầu hoặc tái làm mới chủ động.
- **Refresh ahead:** làm mới các khóa phổ biến trước khi hết hạn.
- **Stale-while-revalidate:** tạm trả giá trị cũ trong cửa sổ cho phép rồi làm mới bất đồng bộ; chỉ áp dụng khi nghiệp vụ chấp nhận dữ liệu cũ.
- **Rate limiting và backpressure:** kiểm soát tải vào khi hệ thống gần quá tải, tránh retry vô hạn.

**Lưu ý nhất quán:** cache hồ sơ sản phẩm có thể chịu trễ vài giây, nhưng không thể tùy tiện cache kết quả kiểm tra quyền truy cập, số dư hoặc số ghế cuối cùng mà không đánh giá quy tắc nghiệp vụ.

### 5.3. Nhân bản khóa để phân tán lượt đọc?

Một số hệ thống có thể lưu nhiều **bản sao logic** của dữ liệu ít thay đổi:

```text
product:P100:detail:replica:0
product:P100:detail:replica:1
product:P100:detail:replica:2
product:P100:detail:replica:3
```

Ứng dụng chọn một bản sao cho mỗi lần đọc, ví dụ theo hash của request/session để phân tán truy cập. Cách này phát sinh trách nhiệm **đồng bộ, phiên bản hóa và vô hiệu hóa tất cả bản sao khi ghi**. Chỉ nên dùng khi cache tại ứng dụng hoặc khả năng đọc replica sẵn có chưa đáp ứng, và đã có cơ chế tránh trả dữ liệu cũ quá mức cho phép.

## 6. Xử lý khóa nóng do ghi: chia một bộ đếm thành nhiều khóa

Đây là ví dụ điển hình của **write sharding theo nghiệp vụ**.

Giả sử số lượt xem video `V999` được cập nhật bằng một khóa:

```text
video:V999:views -> 825000
```

Ta đổi thành **16 bộ đếm con**:

```text
video:V999:views:shard:00 -> 51840
video:V999:views:shard:01 -> 50921
video:V999:views:shard:02 -> 51684
...
video:V999:views:shard:15 -> 51244
```

Mỗi sự kiện hợp lệ chọn một bucket rồi tăng bộ đếm tương ứng. Giá trị logic là:

\[
\text{totalViews}(V999)=\sum_{b=0}^{15}\text{views}(V999,b)
\]

### 6.1. Chọn bucket có thể tái lập

Một phương án là băm `eventId` của lượt xem để chọn shard:

```java
// Ví dụ minh họa: cùng eventId luôn về một shard nếu số shard không đổi.
int shardCount = 16;
int bucket = Math.floorMod(eventId.hashCode(), shardCount);
String key = "video:" + videoId + ":views:shard:"
           + String.format("%02d", bucket);
```

Lệnh Redis tương ứng cho bucket `03`:

```redis
INCRBY video:V999:views:shard:03 1
```

Để phân phối gần đều, `eventId` phải có tính đa dạng và hàm băm phải đủ tốt. `String.hashCode()` minh họa cách chọn bucket trong Java; khi nhiều dịch vụ/ngôn ngữ cùng ghi, nên quy định **thuật toán băm ổn định chung**, chuẩn hóa ID và quản lý phiên bản cách chia shard.

Không nên dùng `videoId` làm dữ liệu duy nhất để chọn bucket, vì tất cả sự kiện của `V999` sẽ lại rơi vào **cùng một bucket**. Nếu yêu cầu chỉ đếm xấp xỉ, có thể phân phối ngẫu nhiên; nếu cần retry tái lập cùng tuyến, chọn bucket xác định theo `eventId` hoặc một định danh sự kiện ổn định sẽ dễ vận hành hơn.

### 6.2. Đọc tổng

Khi yêu cầu tổng số lượt xem, ứng dụng lấy giá trị của các shard rồi cộng:

```text
GET video:V999:views:shard:00
GET video:V999:views:shard:01
...
GET video:V999:views:shard:15
```

Nếu một shard chưa từng có lượt xem, coi khóa vắng mặt là 0. Tại hệ phân tán, các khóa có thể nằm ở những node khác nhau; client cần đọc phù hợp với cơ chế cluster. Đọc các shard lần lượt có thể chậm; có thể đọc song song có giới hạn hoặc **tổng hợp định kỳ** thành một giá trị đọc nhanh:

```text
video:V999:views:materialized -> 825000
```

**Không được hiểu việc đọc lần lượt 16 shard là một ảnh chụp nguyên tử.** Khi sự kiện vẫn được ghi, các shard có thể được đọc ở thời điểm khác nhau. Nếu hiển thị số lượt xem, số liệu chậm hoặc gần đúng thường chấp nhận được; nếu nghiệp vụ đòi một tổng chính xác tại cùng một thời điểm, cần cơ chế đồng bộ hoặc snapshot nhất quán phù hợp.

### 6.3. Lượng tải sau khi chia

Nếu một khóa nhận khoảng **80.000 lần ghi/giây**, chia đều lý tưởng vào 16 shard sẽ là khoảng **5.000 lần ghi/giây cho mỗi shard**:

\[
\text{QPS mỗi shard (lý tưởng)} \approx \frac{80\,000}{16}=5\,000
\]

Đây chỉ là ước lượng phân bố logic, **không phải cam kết thông lượng**. Shard có thể không đều; nhiều khóa shard có thể vẫn cùng nằm trên một node; mạng, CPU, tần suất đọc tổng và khả năng thực tế của từng hệ dữ liệu cũng tác động mạnh. Nếu tất cả khóa đều được buộc vào một phân vùng, chia thành 16 tên khóa sẽ không giải quyết điểm nóng vật lý.

### 6.4. Những đánh đổi phải chấp nhận

- **Đọc tổng phức tạp hơn:** thay một lần đọc bằng nhiều lần đọc hoặc đọc từ kết quả tổng hợp.
- **Idempotency:** nếu một sự kiện được xử lý lại, `INCRBY` thêm lần nữa sẽ đếm trùng. Việc hash `eventId` về cùng shard **không tự động chống đếm trùng**; cần cơ chế deduplication theo `eventId` với phạm vi và thời hạn phù hợp.
- **Thay đổi số shard:** nếu đổi từ 16 thành 32, cùng `eventId` có thể đổi bucket. Cần ghi nhận phiên bản hoặc giữ các thế hệ shard để đọc tổng và xử lý retry đúng.
- **Khả năng mất cập nhật:** phải thiết kế theo độ bền và semantics ghi của datastore; với ghi thống kê lớn, thường dùng log sự kiện/batch để có đường tái tạo khi cần.

## 7. Chia tải theo miền nghiệp vụ, không chỉ thêm hậu tố ngẫu nhiên

Việc thêm `:shard:01` thường hiệu quả với bộ đếm cộng dồn, nhưng không giải quyết được mọi kiểu dữ liệu. Một thiết kế tốt ưu tiên cách chia theo **đơn vị nghiệp vụ có thể xử lý độc lập**.

### 7.1. Từ khóa tenant lớn sang khóa theo thực thể

Thiết kế dễ gây nóng:

```text
tenant:T1:orders -> [toàn bộ danh sách đơn hàng của T1]
```

Mọi đơn mới, yêu cầu xem danh sách và sửa trạng thái đều chạm một khóa lớn. Có thể chuyển thành:

```text
order:O1001 -> { tenantId: T1, ... }
order:O1002 -> { tenantId: T1, ... }
order:O1003 -> { tenantId: T1, ... }
```

Mỗi đơn có khóa riêng. Nếu cần lấy danh sách đơn theo tenant, phải bổ sung **cấu trúc truy cập** như index phù hợp, các trang danh sách theo thời gian hoặc một hệ truy vấn khác. Chia khóa theo `orderId` giúp phân tán thao tác từng đơn, nhưng sẽ làm thao tác "lấy mọi đơn của tenant" phức tạp hơn.

### 7.2. Thêm time bucket khi dữ liệu phát sinh liên tục

Lưu mọi sự kiện của tenant dưới một khóa:

```text
tenant:T1:events -> growing list
```

có thể tạo khóa vừa nóng vừa lớn. Thay vào đó:

```text
tenant:T1:events:2026-11-13
tenant:T1:events:2026-11-14
tenant:T1:events:2026-11-15
```

Khi dữ liệu một ngày vẫn quá lớn, tiếp tục chia bằng giờ hoặc theo bucket trong ngày:

```text
tenant:T1:events:2026-11-14:hour:09:bucket:00
tenant:T1:events:2026-11-14:hour:09:bucket:01
...
```

Time bucket làm việc xóa dữ liệu hết hạn theo thời gian thuận tiện hơn, nhưng **không tự xử lý nóng theo thời điểm hiện tại**: toàn bộ lưu lượng ngay lúc này có thể cùng đổ vào bucket của giờ hiện tại. Khi đó cần thêm chiều chia có phân bố tốt (chẳng hạn event bucket). Đừng giả định chỉ thêm ngày/giờ là đã phân tán đủ tải ghi.

### 7.3. Phân vùng theo khách hàng hoặc đối tượng liên quan

Một số hệ thống có nhiều luồng nghiệp vụ tự nhiên độc lập: từng giỏ hàng, từng đơn, từng cuộc trò chuyện, từng sản phẩm hoặc từng máy đo. Có thể đặt khóa theo các thực thể đó để mỗi thao tác chỉ cần chạm tập khóa nhỏ.

```text
cart:customer:C42                 -> cart state
conversation:CN100:message:M001   -> one message
inventory:warehouse:W1:sku:P100   -> stock at one warehouse
```

Tuy nhiên, nếu **một thực thể đơn lẻ** quá nóng, ví dụ livestream với hàng triệu sự kiện, phân vùng theo `conversationId` hay `videoId` vẫn gom toàn bộ tải vào một khóa/phân vùng. Khi đó cần chia **bên trong thực thể** theo substream hoặc shard được thiết kế cụ thể.

## 8. Redis Cluster: cẩn thận với hash tag

Redis Cluster ánh xạ key vào **16.384 hash slot**; theo cơ chế mặc định, slot được quyết định từ hash của khóa. Redis còn có **hash tag**: khi khóa chứa phần `{...}` hợp lệ, phần bên trong dấu ngoặc nhọn được dùng để tính slot.

Ví dụ:

```text
video:{V999}:views:shard:00
video:{V999}:views:shard:01
video:{V999}:views:shard:02
```

Ba khóa trên cùng hash tag `{V999}` nên **cùng một slot**. Điều đó hữu ích nếu cần thao tác nhiều khóa trong cùng một slot, nhưng **phản tác dụng** khi mục tiêu là chia tải ghi trên nhiều node.

Để các shard có khả năng phân bố vào các slot khác nhau, có thể đặt tên mà không dùng chung hash tag:

```text
video:V999:views:shard:00
video:V999:views:shard:01
video:V999:views:shard:02
```

Hoặc, nếu có lý do sử dụng hash tag, dùng các tag **khác nhau** cho từng bucket, ví dụ `video:{V999:00}:views` và `video:{V999:01}:views`.

Một số thao tác nhiều key ở Redis Cluster yêu cầu các key cùng slot; vì vậy, **chia shard ra nhiều slot có thể khiến các lệnh nhiều key không còn thực hiện trực tiếp như trước**. Chẳng hạn, không nên mặc nhiên gọi `MGET` xuyên các slot trong Redis Cluster và kỳ vọng server xử lý như trên một Redis đơn. Ứng dụng cần dùng client cluster-aware để gửi các lượt đọc phù hợp đến từng node rồi cộng kết quả.

Kết luận thiết kế ở đây là **tên khóa có tác động đến cách dữ liệu được đặt vào cluster**; hãy kiểm tra quy tắc hashing của datastore đang dùng thay vì chỉ nhìn tên khóa.

## 9. Các nghiệp vụ không thể chia ghi một cách tùy tiện

### 9.1. Số dư hoặc hạn mức có bất biến mạnh

Giả sử tài khoản có 1.000.000 VND và hai yêu cầu rút tiền đồng thời. Nếu chia số dư thành 8 counter rồi để mỗi worker trừ một phần, hệ thống có thể cho phép tổng rút vượt số dư dù mỗi shard nhìn riêng vẫn có số dương.

Với bất biến như **số dư không âm**, **hạn mức tối đa**, **không bán vượt tồn kho**, cần một cơ chế kiểm soát xuyên các phần dữ liệu liên quan. Các lựa chọn tùy bài toán gồm:

- Một chủ thể xử lý ghi theo thứ tự cho từng tài khoản hoặc tài nguyên (single writer/actor).
- Transaction hoặc kiểm tra điều kiện có tính nguyên tử trên phạm vi mà datastore hỗ trợ.
- **Escrow/quota partitioning:** cấp phát trước một phần hạn mức cho các vùng hoặc worker; tổng quota không vượt tài nguyên thật, có cơ chế thu hồi/tái cân bằng.
- Log sự kiện có thứ tự và quy trình tái dựng trạng thái, kèm kiểm tra bất biến tại nơi quyết định giao dịch.

Không có cách nào "thêm `:shard:N`" mà tự động bảo toàn những điều kiện này.

### 9.2. Một khóa trạng thái có tính duy nhất

Ví dụ `order:O1001:status` cần chuyển từ `PENDING` sang `PAID` đúng một lần, hoặc một job chỉ được một worker nhận. Khi nhiều bản sao trạng thái được cập nhật độc lập, có thể xuất hiện xung đột. Những trạng thái quyết định duy nhất thường cần **compare-and-set**, transaction, lease có quy tắc xử lý thất bại hoặc coordinator phù hợp, thay vì ghi vào shard ngẫu nhiên.

### 9.3. Tổng hợp dữ liệu không phải lúc nào cũng đọc tức thì

Số liệu phân tích có thể dùng **eventual consistency** và cập nhật định kỳ, nhưng các quyết định cấp quyền, phát tiền, chốt đơn hoặc xuất hóa đơn có thể cần dữ liệu chính xác ở thời điểm xác định. Phải phân loại yêu cầu trước khi chọn mô hình tổng hợp.

## 10. Bảo vệ hệ thống ngoài việc chia khóa

Ngay cả sau khi shard một bộ đếm, một sự kiện nóng bất thường vẫn có thể gây quá tải toàn cụm. Hệ thống nên có cơ chế bảo vệ phù hợp:

1. **Rate limiting:** giới hạn lượng yêu cầu từ khách hàng, IP, API token hoặc loại nghiệp vụ; quy tắc phải tránh cản trở nhu cầu hợp lệ.
2. **Backpressure:** khi hàng đợi hoặc datastore quá tải, giảm tốc nhận việc và trả lỗi có khả năng retry theo chính sách thay vì tiếp tục dồn tải.
3. **Bounded queue và batch:** gom sự kiện thành lô có kích thước hữu hạn, cập nhật theo đợt khi nghiệp vụ cho phép.
4. **Retry có exponential backoff và jitter:** tránh tất cả client retry cùng thời điểm; dùng giới hạn tổng số lần retry và đảm bảo xử lý trùng khi cần.
5. **Load shedding có chủ đích:** bỏ hoặc lấy mẫu các sự kiện thống kê ít quan trọng khi chính sách nghiệp vụ chấp nhận; không bỏ giao dịch cần bảo đảm.
6. **Autoscaling có quan sát:** thêm tài nguyên đọc/ghi khi nút và hạ tầng hỗ trợ, nhưng đừng dùng autoscale thay thế thiết kế partition đúng.

Ví dụ, hệ thống đếm lượt xem có thể nhận event vào hàng đợi rồi gom các lượt xem theo `(videoId, bucket)` trước khi tăng counter bằng `INCRBY key delta`. Cách này giảm số request vào cache/database, đổi lại số hiển thị cập nhật chậm hơn và phải xử lý trường hợp consumer nhận trùng sự kiện.

## 11. Chọn số shard và thay đổi số shard khi tải tăng

Số bucket là một thông số thiết kế, không nên chọn theo cảm tính. Giả sử mức tải ghi cực đại dự kiến cho một đối tượng là \(Q\) request/giây, và mỗi shard nên nhận không quá \(C\) request/giây ở mức vận hành mục tiêu:

\[
N_{\min}\approx\left\lceil\frac{Q}{C}\right\rceil
\]

Ví dụ \(Q=60\,000\) và mục tiêu \(C=5\,000\), phép chia lý tưởng gợi ý **ít nhất 12 shard**. Sau đó cần dự phòng chênh lệch phân bố, tình trạng cùng node, tải đọc, sai số dự báo và suy giảm hiệu năng khi có sự cố. Công thức là điểm bắt đầu để ước lượng, **không thay thế đo tải thực tế**.

Tăng shard giúp phân tán ghi nhưng kéo theo:

- Số key và metadata tăng.
- Chi phí đọc/tổng hợp tăng nếu phải đọc tất cả shard.
- Cần quản lý phiên bản mapping khi tăng/giảm số bucket.
- Có thể xảy ra cùng slot/node dù key khác nhau, tùy hàm băm.

### Chuyển từ 16 sang 32 shard an toàn hơn với thế hệ khóa

Thay vì đổi ngay phép `hash(eventId) % 16` thành `% 32` trên cùng cấu trúc mà không quản lý, hãy dùng **generation/version**:

```text
video:V999:views:g1:shard:00..15
video:V999:views:g2:shard:00..31
```

Một quy trình khả thi:

1. Ghi nhận version đang nhận sự kiện mới (ví dụ `g1`) trong cấu hình được quản lý nhất quán.
2. Chuyển các sự kiện mới sang `g2` tại điểm cắt có kiểm soát; xử lý event trễ/retry bằng định danh sự kiện và thông tin version thích hợp.
3. Trong giai đoạn chuyển tiếp, tính tổng từ cả `g1` và `g2` để không mất dữ liệu lịch sử.
4. Sau khi hệ thống thống kê/khôi phục có thể chứng minh dữ liệu đã được hợp nhất, mới ngừng đọc thế hệ cũ hoặc tạo snapshot tổng.

Phương án cụ thể phụ thuộc vào cơ chế phát sự kiện, deduplication, replay và mức chính xác cần thiết. Điều cốt lõi là **đổi cách chọn shard không được vô tình bỏ sót hoặc đếm hai lần dữ liệu**.

## 12. Phân tích trade-off: có nên chia khóa không?

| Giải pháp | Hiệu quả chủ yếu | Chi phí/đánh đổi | Phù hợp khi |
|---|---|---|---|
| Cache cục bộ/CDN | Giảm đọc vào hot key | Dữ liệu có thể cũ; cần invalidation | Đọc nhiều, ghi ít |
| Read replica | Tách bớt tải đọc | Replication lag, giới hạn cách đọc | Datastore hỗ trợ phân tải đọc |
| Gộp yêu cầu cùng key | Giảm request trùng khi cache miss | Quản lý chờ, timeout, lỗi | Nhiều request đồng thời cùng hỏi một dữ liệu |
| Sharded counter | Phân tán cập nhật cộng dồn | Đọc tổng phức tạp, cần idempotency | Lượt xem, lượt click, số liệu có thể trễ |
| Phân vùng theo thực thể | Chia tải tự nhiên giữa các object | Truy vấn qua nhiều thực thể cần index | Đơn hàng, thông điệp, giỏ hàng |
| Phân vùng theo thời gian | Giảm kích thước một khóa, thuận tiện lưu trữ | Bucket hiện tại vẫn có thể nóng | Dữ liệu sự kiện/lịch sử tăng liên tục |
| Hàng đợi + batch | Giảm số lệnh ghi tức thời | Độ trễ, vận hành queue và replay | Ghi thống kê theo luồng |
| Single writer/quota có kiểm soát | Giữ bất biến mạnh của nghiệp vụ | Có điểm tuần tự hoặc giao thức phức tạp | Số dư, vé, tồn kho, hạn mức |

## 13. Quy trình xử lý hot key trong một hệ key–value

Khi nhận cảnh báo một khóa quá tải, nên đi theo trình tự có bằng chứng:

**Bước 1 — Xác định hot key hay hot partition.** Thu thập lưu lượng đọc/ghi, node owner, phân bố slot/partition, kích thước value, latency và tỷ lệ retry. Đừng chẩn đoán chỉ từ CPU tổng của cluster.

**Bước 2 — Xác định mục tiêu nghiệp vụ.** Đây là dữ liệu được đọc lặp lại, bộ đếm cộng dồn, danh sách tăng liên tục hay trạng thái buộc chính xác? Chấp nhận độ trễ cập nhật bao nhiêu?

**Bước 3 — Chọn đơn vị chia tải.** Có thể chia theo `orderId`, `conversationId`, thời gian, nhóm địa lý, source event, hay shard nhân tạo? Một chiều chia có tạo fan-out lớn khi đọc không?

**Bước 4 — Kiểm tra ánh xạ vật lý.** Các key mới có thực sự phân bố sang nhiều partition/node không? Có hash tag, khóa phân vùng cố định hay cấu hình khiến các key vẫn ở cùng nơi?

**Bước 5 — Thiết kế lại đường đọc/ghi đi cùng nhau.** Nếu ghi vào 16 shard, ai cộng số? Kết quả được cập nhật ở tần suất nào? Khi một shard lỗi, API trả kết quả gì? Retry có đếm trùng?

**Bước 6 — Chuyển đổi có kiểm soát.** Đảm bảo dữ liệu lịch sử, event đến muộn, version shard, TTL và rollback không gây mất dữ liệu hoặc phá bất biến nghiệp vụ.

**Bước 7 — Đo lại dưới tải đại diện.** Quan sát QPS cao nhất mỗi shard/node, p95/p99, CPU, mạng, độ trễ tổng hợp, chi phí và sai số thống kê. Tải tổng cao nhưng phân bố lệch vẫn có thể khiến hệ thống nghẽn.

## 14. Bài tập tình huống

Một hệ thống bán vé trực tuyến lưu:

```text
concert:C55:detail     -> thông tin sự kiện
concert:C55:likes      -> số lượt yêu thích
concert:C55:remaining  -> số vé còn lại
concert:C55:orders     -> danh sách tất cả đơn vé
```

Khi bán vé, cả bốn khóa đều bị truy cập lớn. Hãy tự trả lời:

1. Khóa nào là ứng viên tốt cho **local cache/CDN**? Khi mô tả sự kiện thay đổi, cache được làm mới thế nào?
2. Khóa nào có thể đổi thành **sharded counter** nếu ứng dụng chấp nhận tổng hiển thị trễ vài giây? Làm sao tránh đếm trùng khi retry?
3. Khóa nào cần giữ điều kiện **không bán quá số vé**? Có thể cấp quota theo vùng hay cần điều phối tập trung?
4. Khóa nào nên đổi từ một danh sách chung sang **mỗi đơn một khóa** và thêm chỉ mục hoặc cấu trúc danh sách riêng? Khi đó lấy lịch sử đơn của sự kiện như thế nào?

Gợi ý: `detail` thường thiên về đọc; `likes` thường là thống kê cộng dồn; `remaining` gắn với bất biến tồn kho; `orders` có xu hướng tăng kích thước và cần tách đơn vị lưu. Cùng một sự kiện có thể cần **bốn giải pháp khác nhau** vì mỗi giá trị mang ngữ nghĩa và yêu cầu nhất quán khác nhau.

## 15. Kết luận

**Điểm nóng trên một khóa xuất hiện khi tải tập trung vào một định danh**, dù hệ key–value có nhiều khóa và nhiều node. Để xử lý hiệu quả, trước hết cần phân biệt đọc nóng với ghi nóng, hiểu cách datastore ánh xạ khóa sang partition, rồi chọn cách phân tán phù hợp với nghiệp vụ:

- Dữ liệu chủ yếu để **đọc**: cache, bản sao phục vụ đọc, gom yêu cầu và quản lý TTL.
- Dữ liệu **cộng dồn độc lập**: chia counter theo bucket, đọc tổng hoặc duy trì giá trị tổng hợp, quản lý idempotency.
- Dữ liệu **tăng trưởng theo thực thể/thời gian**: chia theo đơn vị nghiệp vụ và bổ sung đường truy vấn tổng hợp.
- Dữ liệu có **bất biến mạnh**: cần cơ chế điều phối, transaction hoặc phân bổ quota an toàn; không thể tùy ý phân mảnh các quyết định giao dịch.

Mục tiêu không phải chỉ tạo thêm tên khóa, mà là **phân tán được công việc thực tế giữa các tài nguyên vật lý** đồng thời giữ đúng hành vi nghiệp vụ khi đọc, ghi, retry và khôi phục.
