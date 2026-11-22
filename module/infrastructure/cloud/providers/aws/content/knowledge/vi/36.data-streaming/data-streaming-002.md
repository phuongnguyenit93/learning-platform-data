# Kinesis Data Streams, shard và partition key

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, Amazon Kinesis Data Streams (KDS) là dịch vụ thu nhận và phân phối dữ liệu streaming theo thời gian thực. Ứng dụng producer ghi các data record vào một stream; Kinesis phân phối record vào các shard; consumer đọc và xử lý dữ liệu theo nhu cầu. Thiết kế shard và partition key quyết định phần lớn khả năng mở rộng, độ cân bằng tải và thứ tự xử lý của stream.

Partition key không chỉ là một trường bắt buộc trong lệnh ghi dữ liệu. Nó là quyết định kiến trúc: các record có cùng key được ánh xạ tới cùng shard, nhờ đó có thể xử lý theo thứ tự trong phạm vi shard và giữ trạng thái theo một thực thể như khách hàng, thiết bị hoặc đơn hàng. Nếu chọn key có độ tập trung cao, một shard có thể quá tải dù toàn stream còn nhiều capacity. Nếu chọn key quá phân tán, ứng dụng có thể mất tính cục bộ và thứ tự cần thiết.

Sau bài học, người học có thể:

- Giải thích quan hệ giữa stream, data record, shard, hash key range và sequence number.
- Mô tả cách Kinesis dùng MD5 để ánh xạ partition key vào shard.
- Chọn partition key dựa trên cardinality, phân bố tải, thứ tự nghiệp vụ và mô hình consumer.
- Tính số shard provisioned sơ bộ theo throughput ghi, số record và throughput đọc.
- Phân biệt Provisioned, On-demand Standard và On-demand Advantage.
- Nhận diện hot shard, hot partition key và data skew.
- Giải thích split, merge, UpdateShardCount và ảnh hưởng của resharding tới consumer.
- Chọn shared-throughput consumer, Enhanced Fan-Out, KCL hoặc Lambda event source mapping.
- Dùng AWS CLI và AWS SDK for Java để tạo stream, ghi record và quan sát shard.
- Giám sát throughput, throttling, iterator age và consumer lag để vận hành stream ổn định.

## 1. Kinesis Data Streams trong kiến trúc streaming

Kinesis Data Streams thu nhận, lưu trữ tạm thời và cung cấp record cho một hoặc nhiều consumer. Dữ liệu thường đến từ web application, thiết bị IoT, log agent, clickstream, CDC pipeline hoặc hệ thống giao dịch. Consumer có thể tính toán aggregate, phát hiện bất thường, cập nhật database, gửi dữ liệu sang analytics platform hoặc kích hoạt workflow.

Một luồng tổng quát:

~~~mermaid
flowchart LR
    P1[Web and mobile producers] --> S[Kinesis Data Stream]
    P2[IoT devices and services] --> S
    P3[Logs and CDC producers] --> S
    S --> H1[Shard 1]
    S --> H2[Shard 2]
    S --> H3[Shard 3]
    H1 --> C1[Consumer application A]
    H2 --> C1
    H3 --> C1
    H1 --> C2[Consumer application B]
    H2 --> C2
    H3 --> C2
    C1 --> D1[DynamoDB or OpenSearch]
    C2 --> D2[S3 or analytics]
~~~

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| Producer | Gửi data record vào stream bằng API, SDK, Kinesis Producer Library hoặc tích hợp AWS |
| Data stream | Tập hợp các shard, là ranh giới lưu trữ và phân phối record |
| Data record | Đơn vị dữ liệu bất biến gồm sequence number, partition key và payload |
| Shard | Chuỗi record có thứ tự, đồng thời là đơn vị capacity cơ bản |
| Partition key | Giá trị dùng để ánh xạ record tới shard |
| Hash key range | Khoảng giá trị hash mà shard phụ trách |
| Sequence number | Vị trí record do Kinesis cấp trong shard |
| Consumer | Đọc record và xử lý theo logic ứng dụng |

Kinesis không diễn giải nội dung payload. Payload là một dãy byte bất biến; ứng dụng producer và consumer phải thống nhất schema, encoding, version và cách xử lý dữ liệu.

Kinesis Data Streams khác Amazon Data Firehose. Data Streams cung cấp stream và shard để ứng dụng tự kiểm soát consumer, ordering, replay trong retention window và processing topology. Firehose là dịch vụ delivery được quản lý để chuyển dữ liệu tới các destination được hỗ trợ với ít mã consumer hơn. Hai dịch vụ có thể bổ trợ nhau trong cùng pipeline.

## 2. Data record, stream và shard

Một stream gồm một hoặc nhiều shard. Mỗi shard giữ một chuỗi record và cung cấp một đơn vị throughput. Trong Provisioned mode, tổng capacity của stream là tổng capacity của các shard đã cấp phát. Trong On-demand mode, Kinesis quản lý số shard theo nhu cầu và capacity mode của stream.

Một data record có ba thành phần logic:

- Sequence number: do Kinesis cấp sau khi ghi thành công.
- Partition key: xác định cách record được phân phối.
- Data blob: payload dạng byte do ứng dụng cung cấp.

Minh họa stream gồm ba shard:

| Shard | Hash key range | Một số sequence number minh họa |
|---|---|---|
| Shard 1 | Range A | 101, 102, 103 |
| Shard 2 | Range B | 201, 202, 203 |
| Shard 3 | Range C | 301, 302, 303 |

Sequence number của các shard độc lập với nhau; không thể so sánh số 103 với 201 để suy ra thứ tự toàn stream.

Mỗi shard trong Kinesis Data Streams có giới hạn throughput cơ bản:

| Hướng | Giới hạn theo shard | Ý nghĩa |
|---|---:|---|
| Ghi | 1 MB/giây hoặc 1.000 record/giây, tùy giới hạn nào chạm trước | Producer phải phân phối tải trên nhiều shard |
| Đọc qua GetRecords | Tổng cộng 2 MB/giây và tối đa 5 giao dịch đọc/giây | Các shared-throughput consumers cùng chia sẻ capacity đọc |

Các giới hạn này áp dụng cho shard trong cả Provisioned và On-demand capacity mode. Khi một record lớn, số byte có thể chạm giới hạn trước số record; với record nhỏ, giới hạn record/giây có thể chạm trước.

Kích thước record mặc định tối đa là 1 MiB. Có thể cấu hình stream để hỗ trợ record lớn tới 10 MiB ở những trường hợp được hỗ trợ; giới hạn record tính cả partition key và data payload. Khả năng nhận record lớn không làm tăng giới hạn throughput ghi cơ bản của shard. Hãy cân nhắc nén, chia nhỏ payload hoặc lưu nội dung lớn ở S3 rồi chỉ gửi reference vào stream.

## 3. Partition key và cách ánh xạ vào shard

Với chiến lược phân phối mặc định USER_PARTITION_KEY, producer cung cấp partition key cho mỗi record. Kinesis dùng hàm băm MD5 để chuyển partition key thành một số nguyên 128-bit. Sau đó, dịch vụ tìm shard có hash key range chứa giá trị này.

~~~mermaid
flowchart TD
    A[Data record] --> B[Partition key]
    B --> C[MD5 hash 128-bit]
    C --> D{Hash key nằm trong range nào?}
    D -->|Range A| E[Shard 1]
    D -->|Range B| F[Shard 2]
    D -->|Range C| G[Shard 3]
~~~

Các quy tắc quan trọng:

- Partition key là chuỗi Unicode, tối đa 256 ký tự.
- Mỗi shard phụ trách một hash key range liên tục trong không gian hash.
- Các record có cùng partition key có cùng giá trị MD5 hash và được ánh xạ vào cùng shard theo shard map hiện tại.
- Các partition key khác nhau có thể rơi vào cùng một shard nếu hash của chúng nằm trong cùng range.
- Partition key không phải tên shard và không trực tiếp chỉ định shard ID.
- Có thể dùng ExplicitHashKey để ghi đè giá trị hash do partition key tạo ra và chọn vị trí hash cụ thể, nhưng phải hiểu tác động tới phân phối và ordering.

Ví dụ:

| Record | Partition key | Kết quả ánh xạ |
|---|---|---|
| Event A | customer-101 | Shard 1 |
| Event B | customer-202 | Shard 2 |
| Event C | customer-101 | Shard 1 |
| Event D | customer-303 | Shard 3 |

Bảng chỉ minh họa. Vị trí shard thực tế phụ thuộc hash key ranges hiện tại của stream. Không thể suy ra shard từ tên key bằng mắt hoặc giả định customer-101 luôn nằm ở shard 1 sau khi stream reshard.

Partition key có hai vai trò gắn liền: phân phối tải và gom các record liên quan vào cùng shard. Thiết kế key phải cân bằng cả hai mục tiêu.

## 4. Sequence number và phạm vi ordering

Kinesis cấp sequence number cho mỗi record được ghi thành công. Sequence number thể hiện vị trí record trong shard và tăng theo thời gian trong phạm vi shard; không phải số thứ tự toàn stream và không nên dùng làm khóa nghiệp vụ.

Ordering cần được hiểu chính xác:

- Các record trong cùng shard được đọc theo thứ tự của shard.
- Với USER_PARTITION_KEY, các record có cùng partition key được đưa vào cùng shard, nhờ đó có thể xử lý theo thứ tự shard cho thực thể đó.
- Không có thứ tự tổng thể giữa các shard khác nhau.
- Sequence number của shard này không thể so sánh trực tiếp với sequence number của shard khác.
- PutRecords xử lý từng record trong batch độc lập; API không bảo đảm thứ tự record như thứ tự mảng đầu vào.
- PutRecord có tham số SequenceNumberForOrdering để bảo đảm sequence number tăng nghiêm ngặt cho các lần ghi tuần tự từ cùng client tới cùng partition key khi truyền sequence number trước đó.

Nếu nghiệp vụ yêu cầu thứ tự theo order ID, device ID hoặc account ID, hãy dùng thực thể đó làm partition key hoặc tạo một key có giữ được cùng nhóm record. Nếu nghiệp vụ cần thứ tự toàn cục, Kinesis nhiều shard không tự cung cấp một total order; cần thiết kế một luồng tuần tự riêng hoặc cơ chế điều phối phù hợp.

Producer retry cũng có thể tạo duplicate. Ví dụ, PutRecord đã được Kinesis nhận nhưng ACK bị mất trên đường về. Producer không biết record đã được ghi hay chưa và retry; cả hai lần có thể tạo hai record có sequence number khác nhau. Hãy đặt event ID hoặc business ID ổn định trong payload để consumer deduplicate.

## 5. Chọn partition key theo nghiệp vụ

Một partition key tốt cần đáp ứng ba điều kiện:

1. Có đủ cardinality để phân phối record trên nhiều shard.
2. Giữ các record cần xử lý cùng thứ tự ở cùng một nhóm.
3. Phân bố tải tương đối đều theo cả số record và kích thước payload.

Ví dụ chọn key:

| Workload | Key thường phù hợp | Lý do |
|---|---|---|
| Clickstream | sessionId hoặc visitorId | Gom hành vi trong cùng phiên |
| IoT telemetry | deviceId | Giữ chuỗi dữ liệu theo thiết bị |
| Đơn hàng | orderId | Xử lý các event của một đơn theo thứ tự |
| Số dư tài khoản | accountId | Gom giao dịch cùng tài khoản để kiểm tra thứ tự |
| Log đa tenant | tenantId kết hợp sourceId | Tránh dồn toàn bộ dữ liệu vào một tenant key |
| Dữ liệu địa lý | geohash hoặc cellId | Gom dữ liệu theo vùng không gian nếu nghiệp vụ cần |

Không có một key tốt cho mọi workload. Ví dụ tenantId có thể hợp lý khi có hàng nghìn tenant tương đối đồng đều, nhưng sẽ gây hot key nếu một tenant lớn tạo phần lớn traffic. Tương tự, key theo country chỉ có vài giá trị và dễ dồn tải vào một số shard.

### 5.1. Cardinality và độ phân bố

Cardinality là số lượng giá trị key khác nhau trong tập dữ liệu. Nếu stream có 16 shard nhưng chỉ có 3 partition key, tối đa chỉ một vài shard có thể nhận tải. Ngược lại, hàng triệu key có thể giúp phân bố đều hơn, nhưng nếu phần lớn traffic tập trung vào một vài key thì vẫn có hot shard.

Nên phân tích phân bố theo:

- Số record trên mỗi key trong một khoảng thời gian.
- Tổng byte trên mỗi key, không chỉ số record.
- Tỷ lệ của key lớn nhất so với tổng traffic.
- Tính ổn định của phân bố theo giờ, ngày, mùa vụ và chiến dịch.
- Tác động của một tenant, thiết bị hoặc tài khoản tăng đột biến.

Có thể lấy mẫu traffic ở producer, tính top-N key theo record count và bytes, rồi so sánh với shard-level IncomingBytes và IncomingRecords.

### 5.2. Composite partition key

Nếu một trường có cardinality thấp hoặc một tenant có tải lớn, có thể kết hợp nhiều trường:

- tenantId#deviceId
- tenantId#sessionId
- region#customerId
- accountId#eventCategory

Composite key làm tăng số lượng key khác nhau và có thể giảm skew. Tuy nhiên, nó cũng chia các event của cùng một entity sang nhiều key nếu thành phần bổ sung thay đổi. Chỉ thêm trường khi vẫn giữ được nhóm ordering mà ứng dụng cần.

Ví dụ, accountId#eventType sẽ đưa deposit và withdrawal của cùng tài khoản sang các key khác nhau. Nếu cần xử lý mọi giao dịch theo thứ tự tài khoản, key này không phù hợp.

## 6. Hot shard, hot partition key và data skew

Hot shard xảy ra khi một shard nhận tải cao hơn các shard còn lại. Nguyên nhân có thể là:

- Một partition key chiếm tỷ lệ lớn traffic.
- Số lượng key thấp hoặc key phân bố không đều.
- Một số key có payload lớn hơn đáng kể.
- Producer gửi burst vào cùng một nhóm key.
- Số shard provisioned chưa đủ cho workload.
- Một key cụ thể bị tăng đột biến trong thời gian ngắn.

Ví dụ stream có 8 shard và tổng write throughput là 4 MB/s. Nếu traffic phân bố đều, mỗi shard nhận khoảng 0,5 MB/s. Nhưng nếu 40% traffic đến từ một customerId, shard chứa key đó có thể nhận hơn 1,6 MB/s và bị throttling dù tổng throughput của stream còn thấp hơn capacity tổng.

Cần phân biệt:

| Vấn đề | Dấu hiệu | Cách xử lý |
|---|---|---|
| Thiếu tổng shard capacity | Nhiều shard đều gần giới hạn | Tăng shard count hoặc chuyển On-demand |
| Hot shard do skew | Một vài shard cao hơn rõ rệt | Phân tích key và hash range; thiết kế lại key |
| Hot partition key đơn lẻ | Một key vượt giới hạn shard | Bucket/salt key nếu chấp nhận thay đổi ordering; cân nhắc AUTO cho workload stateless |
| Consumer bottleneck | Iterator age tăng dù write không bị throttle | Tăng consumer capacity, tối ưu xử lý hoặc dùng EFO |
| Read contention | Nhiều consumer chia sẻ 2 MB/s/shard | Dùng Enhanced Fan-Out cho consumer cần throughput riêng |

### 6.1. Shard split có giải quyết hot key không?

Split shard chia hash key range của một shard thành hai range nhỏ hơn. Nó có thể giảm tải nếu nhiều partition key khác nhau đang phân bố trong range đó. Nhưng nếu một partition key duy nhất tạo phần lớn traffic, tất cả record của key đó vẫn có cùng hash và sẽ đi vào một child shard sau split. Vì vậy, split không tự chia một key nóng thành nhiều shard.

Nếu cần chia tải của một thực thể nóng, có thể thêm bucket hoặc suffix:

~~~text
customer-101#bucket-0
customer-101#bucket-1
customer-101#bucket-2
customer-101#bucket-3
~~~

Producer phân phối record qua các bucket. Cách này tăng khả năng song song nhưng phá vỡ thứ tự duy nhất theo customer-101. Consumer phải ghép lại theo sequence nghiệp vụ, version, timestamp đáng tin cậy hoặc một quy tắc merge. Nếu không thể xử lý thứ tự sau khi chia bucket, không dùng cách này cho dữ liệu yêu cầu tuần tự tuyệt đối.

### 6.2. ExplicitHashKey và service-managed distribution

ExplicitHashKey cho phép producer chỉ định giá trị hash thay cho hash được tạo từ partition key. Có thể dùng để kiểm soát vị trí record hoặc phân phối nhiều bucket của cùng entity. Nhưng khi cùng logical key được ghi vào các hash range khác nhau, record không còn cùng shard và không còn thứ tự theo key như trước.

Kinesis cũng hỗ trợ service-managed record distribution strategy AUTO. Với chế độ này, dịch vụ tự phân phối record qua các shard; partition key và ExplicitHashKey do producer truyền vào bị bỏ qua. Cách này phù hợp với workload stateless khi record có thể xử lý độc lập và không cần ordering theo partition key. Chiến lược mặc định USER_PARTITION_KEY phù hợp khi cần kiểm soát nhóm record và thứ tự theo key.

Không chuyển sang AUTO chỉ để né hot key nếu consumer phụ thuộc vào ordering. Hãy kiểm tra lại các API producer và hành vi ứng dụng trước khi đổi distribution strategy.

## 7. Tính số shard trong Provisioned mode

Trong Provisioned capacity mode, người vận hành chỉ định số shard. Cần tính cả throughput theo byte và theo record, vì shard có hai giới hạn ghi độc lập.

Với ước lượng ban đầu:

\[
N_{write} =
\max\left(
\left\lceil \frac{W_{MB/s}}{1} \right\rceil,
\left\lceil \frac{W_{records/s}}{1000} \right\rceil
\right)
\]

Nếu shared-throughput consumers đọc tổng cộng R MB/s:

\[
N_{read} = \left\lceil \frac{R_{MB/s}}{2} \right\rceil
\]

Số shard sơ bộ:

\[
N = \max(N_{write}, N_{read})
\]

Sau đó cộng headroom cho peak, burst, skew và tăng trưởng. Đây là phép tính capacity ban đầu; cần xác minh bằng tải thử và shard-level metrics.

### 7.1. Ví dụ sizing

Giả sử hệ thống có:

- Write throughput trung bình cực đại: 6 MB/s.
- Tốc độ ghi: 4.500 record/s.
- Tổng read throughput của các shared consumers: 3 MB/s.

Tính:

- Theo byte ghi: ceil(6 / 1) = 6 shard.
- Theo số record: ceil(4.500 / 1.000) = 5 shard.
- Theo đọc: ceil(3 / 2) = 2 shard.

Vậy cần ít nhất 6 shard theo capacity lý thuyết. Nếu dự phòng 30% headroom, chọn khoảng 8 shard rồi kiểm thử phân bố thực tế.

Nếu có ba shared consumers cùng đọc toàn stream, không được nhân 2 MB/s cho mỗi consumer. Họ chia sẻ tổng read throughput 2 MB/s trên mỗi shard. Nếu mỗi consumer cần throughput riêng và độ trễ thấp, hãy đánh giá Enhanced Fan-Out.

### 7.2. Vì sao không chỉ dùng tổng MB/s?

Hai workload có cùng tổng byte nhưng kích thước record khác nhau có thể cần số shard khác nhau. Ví dụ:

- 500 record/s, mỗi record 2 KB: khoảng 1 MB/s, giới hạn byte gần chạm trước.
- 1.500 record/s, mỗi record 200 byte: khoảng 0,3 MB/s, giới hạn 1.000 record/s chạm trước.

Do đó, phải tính cả IncomingBytes và IncomingRecords. Cũng cần xét burst ngắn, key skew và throughput đọc của consumer.

## 8. Capacity modes: Provisioned, On-demand Standard và On-demand Advantage

Kinesis Data Streams có ba lựa chọn capacity mode:

| Mode | Cách quản lý capacity | Khi phù hợp |
|---|---|---|
| Provisioned | Người vận hành chỉ định shard count và thay đổi khi cần | Traffic dễ dự báo, cần kiểm soát shard/hash range |
| On-demand Standard | Kinesis tự quản lý số shard theo throughput thực tế | Traffic biến động hoặc khó dự báo |
| On-demand Advantage | Chế độ account-level cho On-demand, có warm throughput và cấu trúc giá riêng | Workload on-demand ổn định ở mức lớn hoặc cần chuẩn bị capacity trước peak |

### 8.1. Provisioned

Provisioned phù hợp khi traffic có thể dự báo và cần kiểm soát chính xác shard count. Người vận hành có thể dùng UpdateShardCount để tăng/giảm đều số shard, hoặc SplitShard/MergeShards để điều chỉnh một hash range cụ thể. Việc điều chỉnh cần được theo dõi vì shard map và consumer topology thay đổi.

### 8.2. On-demand Standard

On-demand Standard loại bỏ nhu cầu chỉ định shard count. Stream tự điều chỉnh capacity theo mức sử dụng. Theo tài liệu AWS hiện hành, stream có thể đáp ứng tới gấp đôi peak write throughput quan sát trong 30 ngày trước đó. Nếu traffic tăng vượt gấp đôi peak cũ trong khoảng 15 phút, có thể xuất hiện throttling trong thời gian dịch vụ mở rộng; producer cần retry có backoff.

On-demand tự chia shard khi phát hiện tải tăng, nhưng không phải lúc nào cũng nhận diện và tách riêng một partition key gây skew. Một key đơn lẻ vẫn có thể vượt giới hạn của shard. Nếu workload có hot key nghiêm trọng và cần split hash range có chủ đích, Provisioned mode có thể phù hợp hơn.

### 8.3. On-demand Advantage

On-demand Advantage là thiết lập cấp account trong Region, áp dụng cho các On-demand streams. Chế độ này bổ sung khả năng warm throughput chủ động, cấu trúc giá đơn giản hơn và giới hạn registered consumers cao hơn ở các Region được hỗ trợ. Trước khi bật, hãy kiểm tra minimum usage commitment, pricing, Region support và mức sử dụng thực tế của account. Không nên chọn chỉ vì stream có một đợt burst ngắn.

## 9. Resharding: split, merge và thay đổi shard count

Resharding là thay đổi số lượng shard để điều chỉnh capacity và mức song song. Trong Provisioned mode, có ba thao tác quan trọng:

- **SplitShard:** chia một shard thành hai child shards theo một hash key boundary.
- **MergeShards:** gộp hai shard liền kề thành một shard.
- **UpdateShardCount:** điều chỉnh shard count theo kiểu uniform scaling.

Khi split, hash key range của parent được chia thành hai range liên tục. Các record mới sẽ được ánh xạ theo shard map mới. Khi merge, hai range liền kề được kết hợp thành một range mới.

~~~mermaid
flowchart TD
    P[Parent shard: range 0-999] --> C1[Child shard A: range 0-499]
    P --> C2[Child shard B: range 500-999]
    C1 --> N1[Consumer processes child A]
    C2 --> N2[Consumer processes child B]
~~~

Các lưu ý:

- SplitShard và MergeShards là thao tác bất đồng bộ; stream có thể ở trạng thái UPDATING rồi trở lại ACTIVE.
- Shard cũ không bị biến mất khỏi lịch sử ngay lập tức; nó có lineage tới child shard.
- Record đã ghi vào parent vẫn thuộc parent; record mới theo hash range mới có thể vào child.
- Consumer phải xử lý parent-child lineage để không bỏ sót hoặc xử lý sai thứ tự.
- KCL theo dõi shard leases và checkpoint trong DynamoDB, tự phát hiện shard mới và phân phối processor.
- Consumer tự triển khai bằng GetRecords cần theo dõi parent shard, child shard và checkpoint khi resharding.

### 9.1. Chọn thao tác phù hợp

| Tình huống | Hành động |
|---|---|
| Toàn stream tăng đều | UpdateShardCount tăng số shard |
| Một hash range cụ thể bị nóng do nhiều key | SplitShard có chủ đích |
| Hai shard liền kề ít tải | MergeShards |
| On-demand stream tăng tải tổng thể | Để Kinesis tự quản lý capacity, theo dõi throttling |
| Một partition key duy nhất bị nóng | Xem lại key design; split đơn thuần có thể không giải quyết |

Resharding làm thay đổi shard map, không làm thay đổi payload đã ghi. Nó cũng không tự tăng khả năng xử lý của consumer nếu số worker, database connection hoặc downstream service vẫn là bottleneck.

## 10. Producer: ghi record vào stream

Producer có thể ghi từng record bằng PutRecord hoặc ghi batch bằng PutRecords.

| API | Đặc điểm | Lưu ý |
|---|---|---|
| PutRecord | Gửi một record và nhận shard ID, sequence number | Có thể dùng SequenceNumberForOrdering cho ghi tuần tự cùng key |
| PutRecords | Gửi tối đa 500 record trong một request | Có thể thành công một phần; phải kiểm tra từng response record |
| Kinesis Producer Library (KPL) | Hỗ trợ batching, aggregation và retry | Giảm số API call; consumer cần deaggregate user records, có thể dùng KCL hoặc utility tương thích |

PutRecords không bảo đảm ordering theo thứ tự record trong request. Một số record có thể thành công trong khi record khác thất bại. Producer cần kiểm tra FailedRecordCount và retry đúng những record thất bại, không gửi lại toàn batch nếu không cần. Retry có thể tạo duplicate nếu lần ghi trước thực ra đã thành công nhưng ACK bị mất; payload nên có event ID ổn định.

### 10.1. Ghi record bằng AWS CLI

Tạo stream Provisioned với bốn shard:

~~~bash
aws kinesis create-stream \
  --stream-name orders-events \
  --shard-count 4 \
  --region ap-southeast-1
~~~

Tạo stream On-demand Standard:

~~~bash
aws kinesis create-stream \
  --stream-name telemetry-events \
  --stream-mode-details StreamMode=ON_DEMAND \
  --region ap-southeast-1
~~~

Kiểm tra trạng thái và capacity mode:

~~~bash
aws kinesis describe-stream-summary \
  --stream-name orders-events \
  --region ap-southeast-1
~~~

Liệt kê shard:

~~~bash
aws kinesis list-shards \
  --stream-name orders-events \
  --region ap-southeast-1
~~~

Ghi record bằng partition key là customer ID:

~~~bash
aws kinesis put-record \
  --stream-name orders-events \
  --partition-key customer-101 \
  --data fileb://order-event.json \
  --region ap-southeast-1
~~~

Trong file order-event.json, payload có thể chứa eventId, orderId, customerId, eventType, eventVersion và occurredAt. Hãy dùng một event ID ổn định để consumer deduplicate khi producer retry.

### 10.2. Ghi record bằng AWS SDK for Java 2.x

Ví dụ producer Java dùng customerId làm partition key:

~~~java
import java.util.UUID;

import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.kinesis.KinesisClient;
import software.amazon.awssdk.services.kinesis.model.PutRecordRequest;
import software.amazon.awssdk.services.kinesis.model.PutRecordResponse;

public class OrderEventProducer {
    public static void main(String[] args) {
        String streamName = "orders-events";
        String customerId = "customer-101";
        String eventId = UUID.randomUUID().toString();

        String payload = """
            {
              "eventId": "%s",
              "eventType": "OrderPlaced",
              "orderId": "order-1001",
              "customerId": "%s",
              "eventVersion": 1
            }
            """.formatted(eventId, customerId);

        try (KinesisClient kinesis = KinesisClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            PutRecordRequest request = PutRecordRequest.builder()
                    .streamName(streamName)
                    .partitionKey(customerId)
                    .data(SdkBytes.fromUtf8String(payload))
                    .build();

            PutRecordResponse response = kinesis.putRecord(request);

            System.out.println("Shard: " + response.shardId());
            System.out.println("Sequence: " + response.sequenceNumber());
        }
    }
}
~~~

Trong ứng dụng production, không tạo event ID mới khi retry cùng một nghiệp vụ. Tạo ID ở ranh giới nghiệp vụ rồi giữ nguyên qua mọi lần gửi lại. Bổ sung retry policy có exponential backoff và jitter cho throttling hoặc lỗi tạm thời; log shard ID, sequence number và event ID để điều tra.

## 11. Consumer và mô hình đọc dữ liệu

Consumer có thể đọc trực tiếp shard hoặc sử dụng queue consumer trong các trường hợp được hỗ trợ. Với stream consumer, mỗi shard là một đơn vị đọc có ordering và checkpoint riêng.

### 11.1. Shared-throughput consumer

GetRecords dùng mô hình pull. Các consumer không dùng Enhanced Fan-Out cùng chia sẻ tối đa 2 MB/s đọc trên mỗi shard và giới hạn 5 GetRecords calls/giây/shard. Nếu nhiều consumer cùng đọc toàn stream, chúng có thể cạnh tranh throughput và làm tăng độ trễ.

Shared throughput phù hợp khi:

- Có ít consumer application.
- Throughput đọc không quá lớn.
- Có thể chấp nhận các consumer chia sẻ capacity.
- Muốn tối ưu chi phí retrieval.

### 11.2. Enhanced Fan-Out

Enhanced Fan-Out (EFO) cấp throughput đọc riêng cho mỗi registered consumer, tối đa 2 MB/s trên mỗi shard cho từng consumer. Kinesis push record tới consumer qua HTTP/2 bằng SubscribeToShard, giảm tranh chấp với các consumer khác.

Thông thường, On-demand Standard và Provisioned hỗ trợ tối đa 20 registered consumers mỗi stream; On-demand Advantage hỗ trợ tối đa 50 ở các Region được AWS liệt kê. Registered consumers và queues chia sẻ quota tương ứng. EFO có chi phí retrieval/consumer-shard-hour riêng theo pricing model.

EFO phù hợp khi nhiều ứng dụng độc lập cần đọc toàn bộ stream, hoặc một consumer cần độ trễ thấp và throughput riêng.

### 11.3. Kinesis Client Library

Kinesis Client Library (KCL) quản lý shard discovery, lease, checkpoint, load balancing và record processor. KCL lưu metadata consumer trong DynamoDB. Khi shard split/merge, KCL theo dõi parent-child lineage để xử lý dữ liệu của parent trước khi chuyển sang child theo cơ chế của thư viện.

KCL phù hợp khi xây dựng consumer Java hoặc ứng dụng cần xử lý trạng thái theo shard. Hãy dùng phiên bản KCL được hỗ trợ hiện hành; không khởi tạo consumer chỉ bằng cách poll shard tùy tiện nếu ứng dụng cần quản lý resharding và checkpoint bền vững.

### 11.4. Lambda event source mapping

AWS Lambda có thể đọc Kinesis Data Streams thông qua event source mapping. Lambda quản lý polling, batch và checkpoint theo cấu hình. Consumer cần xử lý record lặp an toàn vì invocation có thể được retry. Với batch lớn, cân nhắc partial batch response để không phát lại các record đã xử lý thành công khi chỉ một record lỗi.

Dù dùng KCL hay Lambda, hãy theo dõi consumer lag và thiết kế idempotency cho side effect. Kinesis retention chỉ là khoảng thời gian record còn có thể đọc lại; consumer chậm quá retention window có nguy cơ mất khả năng replay record cũ.

## 12. Retention period và replay

Kinesis Data Streams lưu record trong một khoảng thời gian hữu hạn. Retention mặc định là 24 giờ và có thể tăng tới 365 ngày. Record cũ hơn retention sẽ không còn khả dụng để consumer đọc.

Retention period là safety window để consumer phục hồi khi downstream bị gián đoạn, không phải kho lưu trữ dài hạn. Nếu cần lưu dữ liệu lâu dài, hãy chuyển dữ liệu sang S3, data lake hoặc kho lưu trữ phù hợp.

Khi tăng retention, các record chưa hết hạn theo retention cũ có thể tiếp tục khả dụng lâu hơn; dữ liệu đã hết hạn trước khi tăng không được khôi phục. Khi giảm retention, record cũ hơn thời hạn mới có thể trở nên không truy cập được gần như ngay lập tức. Thao tác giảm retention cần được kiểm soát.

Retention trên 24 giờ phát sinh chi phí bổ sung. Chọn retention dựa trên thời gian phát hiện sự cố, thời gian sửa consumer, thời gian replay và yêu cầu kiểm toán.

## 13. Theo dõi và chẩn đoán shard

CloudWatch cung cấp metrics ở stream level và tùy chọn shard level. Metrics stream-level cơ bản được gửi tự động; shard-level enhanced monitoring cần bật riêng và có chi phí CloudWatch metrics.

Các metric nên theo dõi:

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| IncomingBytes | Byte được ghi vào stream/shard | Tăng nhanh hoặc phân bố không đều |
| IncomingRecords | Số record được ghi | Một shard có record rate cao bất thường |
| WriteProvisionedThroughputExceeded | Record bị throttle khi ghi | Producer không ghi được hết dữ liệu |
| ReadProvisionedThroughputExceeded | GetRecords bị throttle | Shared consumers tranh chấp read capacity |
| GetRecords.IteratorAgeMilliseconds | Độ tuổi record cuối consumer đọc được | Consumer bị tụt lại phía sau |
| SubscribeToShardEvent.MillisBehindLatest | Consumer EFO chậm bao xa so với latest | Xử lý consumer không theo kịp |
| PutRecords.FailedRecords | Số record thất bại trong batch | Cần retry đúng từng record |
| PutRecords.ThrottledRecords | Record bị throttle trong PutRecords | Cần capacity hoặc key strategy phù hợp |

Nếu stream-level IncomingBytes thấp nhưng một shard-level IncomingBytes cao, có thể có hot shard. Bật enhanced monitoring để xác định shard cụ thể, rồi đối chiếu hash range và phân bố partition key tại producer.

Cảnh báo nên tập trung vào:

- WriteProvisionedThroughputExceeded tăng liên tục.
- ReadProvisionedThroughputExceeded tăng liên tục.
- Iterator age tiến gần một phần đáng kể retention period.
- PutRecords.FailedRecords hoặc ThrottledRecords tăng.
- Shard-level IncomingBytes/IncomingRecords lệch xa giữa các shard.
- Consumer processing latency hoặc downstream error tăng.

Không chỉ nhìn tổng throughput. Tổng stream có thể thấp nhưng một shard vẫn bị throttle do hot key.

## 14. Bảo mật và chi phí

Kinesis Data Streams hỗ trợ mã hóa server-side bằng AWS KMS. Có thể dùng AWS owned key hoặc customer managed key theo yêu cầu kiểm soát. Dữ liệu truyền qua AWS SDK/API cần sử dụng TLS. IAM policy nên giới hạn producer chỉ có quyền ghi và consumer chỉ có quyền đọc đúng stream cần thiết.

Một số action thường dùng:

- Producer: kinesis:PutRecord, kinesis:PutRecords.
- Consumer shared: kinesis:GetShardIterator, kinesis:GetRecords, kinesis:DescribeStreamSummary, kinesis:ListShards.
- Consumer EFO: kinesis:RegisterStreamConsumer, kinesis:SubscribeToShard, kinesis:DescribeStreamConsumer.
- Operations: kinesis:DescribeStreamSummary, kinesis:UpdateShardCount, kinesis:SplitShard, kinesis:MergeShards và các action monitoring tương ứng.

Với customer managed KMS key, cần cấp quyền sử dụng key cho principal liên quan. Không cấp quyền quản trị stream cho producer chỉ để họ có thể ghi record.

Các khoản chi phí chính phụ thuộc capacity mode và cách tiêu thụ:

- Provisioned: shard-hours và các thành phần tính phí liên quan.
- On-demand Standard: dữ liệu ghi/đọc và các chiều giá theo pricing hiện hành.
- On-demand Advantage: cấu trúc giá và minimum usage commitment riêng.
- Extended retention: phần retention vượt 24 giờ.
- Enhanced Fan-Out: consumer-shard-hours và data retrieval theo pricing.
- Enhanced shard-level metrics: CloudWatch custom metrics.
- KMS: các thao tác sử dụng customer managed key theo bảng giá KMS.

Trước khi chọn mode, hãy ước tính write bytes, write records, read throughput, số consumer, retention và mức burst. Giá thực tế thay đổi theo Region và mode; dùng AWS Pricing Calculator và trang giá Kinesis tại thời điểm triển khai.

## 15. Các lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| ProvisionedThroughputExceededException khi ghi | Một shard vượt giới hạn byte hoặc record | Kiểm tra shard metrics, tăng shard count hoặc điều chỉnh partition key |
| Một shard nóng dù stream còn capacity | Hot partition key hoặc key skew | Phân tích top key; composite/bucket key nếu chấp nhận ordering thay đổi |
| PutRecords trả HTTP thành công nhưng có record lỗi | Batch có partial failure | Kiểm tra từng response record và retry đúng record lỗi |
| Consumer đọc chậm | Consumer CPU/downstream bottleneck hoặc shared read contention | Tăng worker/throughput, tối ưu xử lý hoặc dùng EFO |
| IteratorAgeMilliseconds tăng | Consumer không theo kịp producer | Tăng capacity xử lý, giảm thời gian xử lý record, kiểm tra throttling |
| Consumer bỏ qua dữ liệu sau resharding | Không theo dõi parent-child lineage | Dùng KCL hoặc triển khai shard discovery/checkpoint đúng |
| Sequence number không theo thứ tự mong muốn | Đọc nhiều shard hoặc dùng PutRecords | Xác định ordering scope; dùng cùng key/shard và PutRecord khi cần tuần tự |
| Record không thể replay | Retention đã hết hạn | Tăng retention phù hợp và lưu archive dài hạn ở S3 |
| On-demand vẫn bị throttle | Traffic tăng quá nhanh hoặc một key vượt shard limit | Retry có backoff, kiểm tra peak history và hot key; cân nhắc warm throughput/Provisioned |
| Chi phí tăng mạnh | Quá nhiều shard, EFO consumers, extended retention hoặc metrics | Rà soát capacity mode, consumer count, retention và enhanced monitoring |

## 16. Bài thực hành: thiết kế stream telemetry cho IoT

Một nền tảng IoT nhận telemetry từ 50.000 thiết bị. Mỗi thiết bị gửi trung bình một record mỗi giây, payload trung bình 500 byte. Hệ thống cần hai consumer:

- Consumer A tổng hợp trạng thái thiết bị theo thời gian thực.
- Consumer B phát hiện bất thường và gửi cảnh báo.

Yêu cầu nghiệp vụ: record của cùng một thiết bị cần được xử lý theo thứ tự; hai consumer cần đọc độc lập.

### 16.1. Chọn partition key

Dùng deviceId làm partition key để mọi record của một thiết bị đi cùng shard. Không dùng một key cố định như telemetry hoặc iot vì toàn bộ traffic sẽ dồn vào một shard. Nếu một thiết bị hoặc gateway gửi lượng dữ liệu bất thường, cần theo dõi hot key riêng.

### 16.2. Ước lượng write throughput

- Tổng record rate: 50.000 record/s.
- Payload rate: 50.000 × 500 byte = 25.000.000 byte/s, khoảng 25 MB/s.
- Theo giới hạn 1 MB/s/shard: cần ít nhất 25 shard theo byte.
- Theo giới hạn 1.000 record/s/shard: cần ít nhất 50 shard theo số record.

Số shard sơ bộ phải theo giới hạn lớn hơn: tối thiểu 50 shard. Sau đó cộng headroom cho burst, kích thước key và traffic tăng trưởng. Ví dụ chọn 65–70 shard để thử nghiệm nếu dùng Provisioned mode, rồi điều chỉnh theo metrics thực tế.

### 16.3. Chọn consumer mode

Hai consumer cùng đọc toàn stream. Ở mức tối thiểu 50 shard, shared GetRecords có tổng read capacity lý thuyết tối đa khoảng 100 MB/s cho tất cả shared consumers cộng lại; hai consumer chia sẻ capacity này và còn chịu giới hạn số lần gọi đọc trên từng shard. Nếu mỗi consumer cần throughput riêng, độ trễ ổn định hoặc không muốn tranh chấp với consumer khác, EFO cấp tối đa 2 MB/s/shard cho từng consumer. Cần tính thêm chi phí và registered consumer quota.

### 16.4. Vận hành

1. Tạo stream với capacity mode phù hợp.
2. Ghi record với partition key deviceId.
3. Bật shard-level monitoring.
4. Theo dõi IncomingBytes, IncomingRecords và write throttling theo shard.
5. Dùng EFO nếu hai consumer cần throughput độc lập.
6. Theo dõi iterator age hoặc MillisBehindLatest của từng consumer.
7. Kiểm thử một thiết bị gửi burst để xác định hot-key behavior.
8. Kiểm thử resharding và xác nhận consumer xử lý parent/child shard đúng.
9. Tăng retention nếu consumer cần cửa sổ phục hồi dài hơn 24 giờ.
10. Archive dữ liệu cần lưu lâu dài sang S3.

Bài thực hành cần chứng minh rằng traffic được phân phối đủ đều, ordering theo deviceId được giữ trong phạm vi yêu cầu và cả hai consumer có thể bắt kịp stream sau một lần gián đoạn.

## Kết luận

Shard là đơn vị capacity và thứ tự cơ bản của Kinesis Data Streams. Partition key được băm bằng MD5 thành hash key rồi ánh xạ vào hash range của shard. Các record cùng key đi vào cùng shard theo shard map hiện tại, giúp xử lý theo thứ tự của thực thể. Đổi lại, key có phân bố không đều có thể tạo hot shard và throttling.

Thiết kế tốt bắt đầu từ mô hình nghiệp vụ: chọn key có cardinality phù hợp, giữ đúng phạm vi ordering, đo cả bytes và records, chọn capacity mode và consumer model theo tải thực tế. Provisioned cho phép kiểm soát shard và resharding chi tiết; On-demand giảm quản trị capacity nhưng không loại bỏ giới hạn của hot key. Consumer cần xử lý duplicate, checkpoint và shard lineage; retention cần đủ dài để phục hồi nhưng không thay thế lưu trữ dài hạn.

## Tài liệu tham khảo

- [Amazon Kinesis Data Streams terminology and concepts](https://docs.aws.amazon.com/streams/latest/dev/key-concepts.html)
- [Kinesis Data Streams quotas and limits](https://docs.aws.amazon.com/streams/latest/dev/service-sizes-and-limits.html)
- [Choose the right mode to stream in](https://docs.aws.amazon.com/streams/latest/dev/how-do-i-size-a-stream.html)
- [Create and manage Kinesis data streams](https://docs.aws.amazon.com/streams/latest/dev/working-with-streams.html)
- [PutRecord API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_PutRecord.html)
- [PutRecords API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_PutRecords.html)
- [Service-managed record distribution strategy](https://docs.aws.amazon.com/streams/latest/dev/service-managed-record-distribution.html)
- [Split a shard](https://docs.aws.amazon.com/streams/latest/dev/kinesis-using-sdk-java-resharding-split.html)
- [MergeShards API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_MergeShards.html)
- [Resharding, scaling, and parallel processing](https://docs.aws.amazon.com/streams/latest/dev/kinesis-record-processor-scaling.html)
- [Read data from Kinesis data streams](https://docs.aws.amazon.com/streams/latest/dev/building-consumers.html)
- [Enhanced Fan-Out consumers](https://docs.aws.amazon.com/streams/latest/dev/enhanced-consumers.html)
- [Change the data retention period](https://docs.aws.amazon.com/streams/latest/dev/kinesis-extended-retention.html)
- [Monitor Kinesis Data Streams with CloudWatch](https://docs.aws.amazon.com/streams/latest/dev/monitoring-with-cloudwatch.html)
- [Develop producers using Kinesis Producer Library](https://docs.aws.amazon.com/streams/latest/dev/developing-producers-with-kpl.html)
- [AWS SDK for Java 2.x Kinesis client](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/kinesis/KinesisClient.html)
- [Amazon Kinesis Data Streams pricing](https://aws.amazon.com/kinesis/data-streams/pricing/)

