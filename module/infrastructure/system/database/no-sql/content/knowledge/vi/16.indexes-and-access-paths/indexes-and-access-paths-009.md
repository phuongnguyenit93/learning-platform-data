# Độ mới của chỉ mục đồng bộ so với bất đồng bộ

Một ứng dụng thương mại điện tử có thể lưu sản phẩm trong **Product Store** và dùng các chỉ mục để tìm sản phẩm theo tên, danh mục, giá hoặc trạng thái còn hàng. Khi người bán cập nhật giá từ 1.500.000 VND xuống 1.390.000 VND, thao tác ghi ở Product Store có thể đã thành công nhưng kết quả tìm kiếm vẫn hiển thị mức giá cũ trong một khoảng thời gian.

Tình huống này dẫn đến câu hỏi quan trọng trong thiết kế **chỉ mục và đường truy cập** của NoSQL:

> Sau khi dữ liệu nguồn được ghi thành công, **bao lâu thì một truy vấn qua chỉ mục có thể nhìn thấy thay đổi**, và điều gì xảy ra nếu nó chưa nhìn thấy?

Chỉ mục **đồng bộ (synchronous index maintenance)** thường cập nhật như một phần của đường ghi, giúp một số truy vấn nhìn thấy trạng thái mới với hợp đồng nhất quán chặt hơn, nhưng có thể tăng độ trễ và chi phí ghi. Chỉ mục **bất đồng bộ (asynchronous index maintenance)** được cập nhật qua queue, CDC, stream hoặc pipeline nền, giúp tách tải nhưng làm xuất hiện **độ trễ giữa dữ liệu nguồn và đường truy vấn**.

Điểm cốt lõi không phải là đồng bộ luôn đúng hay bất đồng bộ luôn nhanh. Cần thiết kế **mức độ mới cần thiết theo từng API**, đo **thời gian commit đến khi truy vấn thực sự thấy dữ liệu**, và có phương án bảo vệ các quyết định nghiệp vụ không được dựa vào dữ liệu cũ.

> Các giới hạn thời gian, khối lượng và kết quả benchmark trong bài là **ví dụ giả định**, không phải cam kết của MongoDB, DynamoDB, Cassandra, OpenSearch hay các sản phẩm khác. Tính nhất quán phụ thuộc cấu hình index, bản sao, kiểu đọc, transaction và phiên bản công nghệ cụ thể.

## 1. Chỉ mục làm gì trong đường truy cập NoSQL?

**Chỉ mục (index)** là cấu trúc phụ giúp xác định vị trí dữ liệu cần đọc mà không phải quét tất cả bản ghi. Chẳng hạn, document chứa:

~~~json
{
  "productId": "P-42",
  "category": "office",
  "name": "Bàn làm việc",
  "priceMinor": 1500000,
  "active": true,
  "version": 17
}
~~~

Đường truy vấn có thể gồm:

- **Point lookup theo khóa chính**: lấy P-42 bằng định danh.
- **Index theo category**: tìm sản phẩm office.
- **Index theo priceMinor**: lọc hoặc sắp xếp theo giá.
- **Full-text/search index**: tìm “bàn làm việc”, hỗ trợ tokenization và ranking.
- **Read model dẫn xuất**: danh sách sản phẩm bán chạy theo từng danh mục.

Không phải mọi index đều có cùng cơ chế cập nhật. Có index được duy trì bên trong database, có index nằm tại một dịch vụ khác như search engine; có loại phản ánh ngay cùng transaction, có loại nhận thay đổi sau qua stream.

### 1.1. Ba đường truy cập, ba yêu cầu về độ mới

| Đường truy cập | Câu hỏi chính | Hợp đồng độ mới có thể cần |
| --- | --- | --- |
| Đọc sản phẩm theo productId | Giá hiện tại của P-42 là bao nhiêu? | Có thể cần đọc từ nguồn có thẩm quyền |
| Danh sách sản phẩm theo danh mục | Những sản phẩm nào nên hiện trên trang listing? | Có thể chấp nhận chỉ mục trễ vài giây |
| Xác nhận thanh toán | Giá và tồn kho đã chốt có hợp lệ không? | Phải kiểm tra và ghi ở điểm quyết định đáng tin |

Nếu một kết quả tìm kiếm cũ hiển thị P-42 ở giá 1.500.000 VND trong hai giây, đây là vấn đề trải nghiệm. Nếu **checkout lấy luôn giá cũ từ search index để quyết định số tiền thanh toán**, đó là lỗi thiết kế nghiêm trọng hơn.

**Index là đường tối ưu truy vấn, không tự động là nguồn có thẩm quyền để quyết định mọi bất biến nghiệp vụ.**

## 2. Phân biệt đồng bộ, bất đồng bộ và nhất quán bản sao

Một số thuật ngữ thường bị trộn lẫn:

| Khái niệm | Trả lời câu hỏi nào? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| **Synchronous index maintenance** | Index có được cập nhật trong đường ghi hay cùng ranh giới commit theo hợp đồng engine? | Một replica đọc xa luôn đã bắt kịp |
| **Asynchronous index maintenance** | Có pipeline cập nhật index sau ghi nguồn không? | Thời gian trễ tối đa có giới hạn cứng |
| **Synchronous replication** | Khi nào replica được xác nhận đã tham gia ghi? | Search index ngoài database đã searchable |
| **Eventual consistency** | Các bản sao có thể hội tụ khi không có lỗi kéo dài? | Bản sẽ mới trong chính xác 5 giây |
| **Strongly consistent read** | Read có bảo đảm nhất quán nào so với ghi đã commit? | Mọi index hoặc mọi dịch vụ đều hỗ trợ cùng chế độ |
| **Read-your-writes** | Người vừa ghi có nhìn thấy lần ghi của mình? | Người đọc khác hoặc index ngoài hệ đã bắt kịp |
| **Index visibility/refresh** | Dữ liệu đã được đường search thực tế trả về chưa? | Source đã ghi thành công theo đúng transaction nghiệp vụ |

Ví dụ, **một index được cập nhật đồng bộ trong primary database** nhưng API lại đọc qua **secondary replica đang trễ**. Khi đó người dùng vẫn có thể thấy dữ liệu cũ. Ngược lại, một search index nhận event bất đồng bộ nhưng hỗ trợ cơ chế chờ refresh có thể giúp một thao tác cụ thể biết khi nào bản vừa ghi đã searchable; điều đó không biến toàn bộ pipeline từ source thành một transaction nguyên tử.

### 2.1. Đồng bộ theo nghĩa nào?

Không nên dùng cụm “index đồng bộ” mà không nói rõ:

1. **Ghi nguồn và index có cùng transaction atomic không?**
2. **Lệnh ghi trả success sau khi những bước nào xong?**
3. **Read được gửi tới primary, replica hay một hệ search tách biệt?**
4. **Index đã bền vững nhưng query có thấy ngay không?**
5. **Nếu cập nhật index thất bại, ghi nguồn rollback hay chỉ ghi lại lỗi để thử sau?**

Câu trả lời quyết định mức độ bảo đảm thực tế.

## 3. Dòng thời gian của một lần ghi

Giả sử cập nhật giá P-42 từ version 17 lên version 18:

~~~text
T0: Client gọi updateProduct(P-42, price=1390000)
T1: Product Store commit version 18
T2: Sự kiện ProductUpdated v18 được publish
T3: Indexer nhận sự kiện
T4: Indexer áp dụng version 18 vào index
T5: Truy vấn qua index thật sự trả version 18
~~~

Trong pipeline bất đồng bộ, **T1 đến T5** có thể kéo dài từ mili giây tới nhiều phút khi có lỗi, retry hoặc backlog.

Trong đường duy trì index đồng bộ, các bước viết vào index có thể xảy ra **trước khi commit nguồn được xác nhận**; nhưng T5 vẫn cần kiểm tra theo hợp đồng query/replica/refresh.

### 3.1. Từ commit tới query-visible

Định nghĩa:

- **t_commit**: thời điểm source commit phiên bản mới.
- **t_publish**: thời điểm change/outbox được publish.
- **t_consume**: thời điểm indexer nhận thay đổi.
- **t_applied**: thời điểm indexer xác nhận cập nhật index.
- **t_visible**: thời điểm đường query thật trả dữ liệu mới.

Độ trễ người dùng quan tâm:

\[
L_{\text{freshness}}=t_{\text{visible}}-t_{\text{commit}}
\]

Khi các timestamp đáng tin cậy, có thể phân rã:

\[
\begin{aligned}
L_{\text{freshness}} = {} &
(t_{\text{publish}}-t_{\text{commit}})\\
&+(t_{\text{consume}}-t_{\text{publish}})\\
&+(t_{\text{applied}}-t_{\text{consume}})\\
&+(t_{\text{visible}}-t_{\text{applied}})
\end{aligned}
\]

**Một consumer đã ACK không có nghĩa query đã nhìn thấy phiên bản mới.** Một số công cụ search cần refresh hoặc một bước publish snapshot nội bộ trước khi phiên bản được nhìn thấy qua truy vấn.

### 3.2. Đồng hồ và phiên bản

Khi commit timestamp được lấy ở máy A, consume timestamp ở máy B, query timestamp ở máy C, **độ lệch đồng hồ** có thể làm số đo sai. Với mục tiêu vài chục mili giây, cần:

- Đồng bộ đồng hồ và theo dõi clock skew.
- Đo bằng probe ở cùng nơi khi khả thi.
- Truyền **aggregateVersion** hoặc **sequence** để so sánh tính mới mà không dựa hoàn toàn vào thời gian.
- Phân biệt **eventTime** của khách/thiết bị với **commit time** của database.

Một event sinh lúc 09:00 nhưng tới server 09:30 không chứng minh indexer chậm 30 phút. Muốn đo độ trễ sau commit phải lấy **mốc commit**, không lấy timestamp nguồn thiếu tin cậy.

## 4. Chỉ mục cập nhật đồng bộ: lợi ích và chi phí

Mô hình khái niệm:

~~~mermaid
sequenceDiagram
    participant Client
    participant DB as NoSQL database
    participant Data as Primary record
    participant Index as Internal index
    Client->>DB: Update P-42 to version 18
    DB->>Data: Write new record
    DB->>Index: Maintain index entries
    DB-->>Client: Commit / write acknowledgment
    Client->>DB: Query via index
    DB-->>Client: Result subject to read contract
~~~

Khi source và index nằm trong **cùng ranh giới nguyên tử được engine bảo đảm**, write không thể thành công một nửa theo hợp đồng đó: nếu update bị rollback thì index cũng không được phản ánh bản commit thất bại.

Những ưu điểm thường có:

- Dữ liệu và index được quản lý cùng đường write.
- Ít cần pipeline, queue, projector và quá trình reconcile riêng.
- Một số đường đọc có thể bảo đảm nhất quán ngay sau commit với mức đọc phù hợp.
- Truy vấn theo index sẵn có thể có ngữ nghĩa rõ hơn trong transaction.

Những chi phí:

- **Write amplification:** một thay đổi có thể sửa primary data và nhiều index entry.
- **Tăng write latency:** phải duy trì index trước khi phản hồi success.
- **CPU/RAM/IOPS:** index theo nhiều trường, array hoặc nested data có thể tạo nhiều entry.
- **Tranh chấp cập nhật:** index hot hoặc update nhiều khóa có thể ảnh hưởng throughput.
- **Chi phí schema/index:** tạo index mới, rebuild hoặc backfill có thể tốn I/O.

### 4.1. Ví dụ index theo danh mục và giá

Một document:

~~~json
{
  "_id": "P-42",
  "category": "office",
  "priceMinor": 1500000
}
~~~

Giả sử database duy trì index cho cặp (category, priceMinor). Khi giá đổi từ 1.500.000 xuống 1.390.000:

~~~text
Index entry cũ:
  ("office", 1500000) -> P-42

Index entry mới:
  ("office", 1390000) -> P-42
~~~

Mục tiêu là sau commit, một truy vấn phù hợp không trả index entry cũ như trạng thái hiện hành. Nếu engine bảo đảm index update nằm trong transaction, truy vấn với mức nhất quán cần thiết có thể dựa trên điều đó; **đọc từ bản sao trễ vẫn là một câu chuyện riêng**.

### 4.2. Càng nhiều index, write path càng nặng

Giả sử một sản phẩm có năm index phụ. Đổi giá có thể:

- Cập nhật document gốc.
- Thay entry trong index theo category/price.
- Thay entry trong index theo active/price nếu có.
- Giữ nguyên index không chứa trường bị đổi nếu engine không cần sửa.
- Ghi log/replication metadata.

Không nên tính cứng “5 index = 5 lần I/O” vì công việc phụ thuộc field đổi và thiết kế engine. Nhưng **mỗi index có chi phí duy trì và lưu trữ**, nên index không được tạo vô hạn chỉ để tăng tốc mọi truy vấn hiếm.

## 5. Chỉ mục bất đồng bộ: tách write path, thêm bài toán hội tụ

Mô hình thường gặp:

~~~mermaid
flowchart LR
    W["Product write API"] --> S[("Primary store")]
    S --> O[("Outbox / CDC stream")]
    O --> Q["Message broker / change log"]
    Q --> C["Indexer / projector"]
    C --> I[("Search index / read model")]
    R["Search API"] --> I
    V["Checkout"] --> S
~~~

Sau khi source commit, indexer đọc thay đổi rồi cập nhật bản dẫn xuất. Indexer có thể được triển khai độc lập và mở rộng riêng.

Ưu điểm:

- Giảm việc chờ index ngoài hệ trên đường ghi nguồn.
- Dễ dùng công cụ chuyên biệt cho full-text, ranking, geo-search hoặc analytics.
- Có thể batch, retry, throttle và xây nhiều read model từ cùng nguồn.
- Pipeline nền có thể được mở rộng theo số partition/consumer nếu thiết kế cho phép.

Chi phí:

- Search index có thể cũ sau khi source commit.
- Phải quản lý **độ trễ, retry, message trùng, sai thứ tự và thiếu event**.
- Cần giám sát health/lag và có cơ chế **reconciliation/backfill**.
- Việc thay schema hoặc rebuild index đòi phối hợp snapshot với change stream.
- Hệ thống có thêm thành phần và điểm lỗi vận hành.

### 5.1. Eventual consistency không phải giới hạn thời gian

Nếu hệ thống nói “index eventual consistent”, nó có thể hội tụ sau một khoảng ngắn **khi pipeline hoạt động bình thường**, nhưng không suy ra rằng index luôn cập nhật trong hai giây.

Ví dụ:

~~~text
10:00  Source commit v18
10:01  Broker nhận v18
10:02  Consumer crash
10:03  Search vẫn ở v17
10:30  Consumer được khôi phục
10:31  Search bắt kịp v18
~~~

Hệ vẫn có thể hội tụ về trạng thái đúng sau khi khôi phục, nhưng **độ cũ 31 phút** có thể không chấp nhận được. Cần đặt **freshness SLO** và hành vi khi vượt ngưỡng.

## 6. Ví dụ sản phẩm: MongoDB, DynamoDB, công cụ search

### 6.1. MongoDB: index nội bộ và độ trễ đọc bản sao

Ví dụ tạo index trên collection:

~~~javascript
db.products.createIndex(
  { category: 1, priceMinor: 1 },
  { name: "category_price_idx" }
);

db.products.updateOne(
  { _id: "P-42", version: 17 },
  {
    $set: { priceMinor: 1390000 },
    $inc: { version: 1 }
  }
);

db.products.find({
  category: "office",
  priceMinor: { $lte: 1400000 }
});
~~~

Đây là các thao tác minh họa trên **index thông thường của MongoDB**. Với các thao tác ghi được commit theo hợp đồng và đọc từ **primary** ở mức phù hợp, index thông thường được duy trì như một phần cơ chế ghi của database.

Nhưng nếu query được định tuyến đến **secondary replica đang lag**, nó có thể nhìn thấy trạng thái cũ. Không được kết luận “MongoDB index đồng bộ nên mọi request qua mọi replica luôn read-your-writes”.

**Phân biệt rõ:** index thông thường trong MongoDB không đồng nghĩa với **MongoDB Search/Atlas Search** được vận hành qua cơ chế lập chỉ mục tìm kiếm khác và có thể có độ trễ đồng bộ riêng. Cần đọc hợp đồng sản phẩm cụ thể.

### 6.2. DynamoDB: bảng chính và Global Secondary Index

Một bảng có primary key theo productId và GSI theo category:

~~~text
Table Products:
  PK = PRODUCT#P-42
  category = office
  priceMinor = 1390000
  version = 18

GSI CategoryPrice:
  GSI_PK = CATEGORY#office
  GSI_SK = PRICE#0000001390000#PRODUCT#P-42
~~~

Đây là ví dụ mô hình khóa do ứng dụng thiết kế; cần chú ý nếu lưu giá trong sort key dạng chuỗi thì **format có độ rộng chuẩn hóa và xử lý miền số**.

**DynamoDB Global Secondary Index (GSI)** được duy trì **bất đồng bộ** so với bảng chính; query trên GSI dùng **eventually consistent reads**. Không thể yêu cầu GSI query trở thành strongly consistent chỉ bằng cách bật cùng một cờ dùng cho đọc bảng.

**Local Secondary Index (LSI)** có mô hình khác và hỗ trợ strongly consistent read theo khả năng của dịch vụ, nhưng phải đáp ứng những điều kiện/giới hạn của LSI và cách đọc. Không được coi GSI và LSI là hai tên gọi có cùng consistency semantics.

Một quy trình cần kết quả mới:

~~~text
1. Query GSI để tìm danh sách candidate productId.
2. Với hành động cần chắc chắn, GetItem từ bảng chính
   bằng key có thẩm quyền và consistency phù hợp.
3. Kiểm tra price/active/inventory trước khi commit nghiệp vụ.
~~~

Nếu một sản phẩm **mới thêm** chưa xuất hiện trên GSI, bước GetItem ở bảng chính không thể tự tìm ra candidate bị thiếu. Fallback này chỉ **xác minh các kết quả đã tìm được**, không đảm bảo **độ đầy đủ của tập kết quả search**.

### 6.3. OpenSearch/Elasticsearch: applied không đồng nghĩa searchable

Một search engine gần thời gian thực thường có khái niệm **refresh** để dữ liệu đã index trở nên tìm kiếm được. Ví dụ API khái niệm:

~~~http
PUT /products/_doc/P-42?refresh=wait_for
Content-Type: application/json

{
  "productId": "P-42",
  "name": "Bàn làm việc",
  "priceMinor": 1390000,
  "version": 18
}
~~~

Tham số refresh/refresh=wait_for phụ thuộc phiên bản và API; ý tưởng là **một thao tác ghi trực tiếp vào search engine có thể chờ refresh thích hợp**.

Nhưng khi kiến trúc là:

~~~text
Product Store commit
   -> outbox
   -> broker
   -> consumer
   -> search index write
   -> search refresh
~~~

thì chờ refresh chỉ giải quyết **chặng cuối sau khi consumer gửi index write**. Nó **không bảo đảm** event chưa publish, đang kẹt broker hoặc bị retry đã xuất hiện ở search.

Một số API tìm kiếm theo ID bằng realtime get có thể có ngữ nghĩa visibility khác so với full-text search. **Hãy thử đúng đường truy vấn mà người dùng sử dụng**, thay vì coi việc get được document theo ID là bằng chứng mọi query term/range đã thấy nó.

### 6.4. Cassandra và index phục vụ truy vấn

Ở Cassandra, primary key/partition key, clustering columns, secondary index truyền thống và các cơ chế chỉ mục khác có đặc điểm khác nhau về định tuyến, phạm vi truy vấn, ghi và nhất quán. Một index gắn với storage engine không tự đồng nghĩa có một global transactional search view.

Khi dùng chỉ mục của Cassandra hoặc read model materialized/denormalized:

- Xác định index cập nhật ở đâu và khi nào.
- Xác định consistency level của write/read và tình trạng replica.
- Kiểm tra truy vấn có phải fan-out nhiều node/partition không.
- Đo p99 và kết quả trong tình huống replica/repair chậm.
- Không suy diễn semantic của DynamoDB GSI hoặc MongoDB index sang Cassandra.

**Tài liệu và thực nghiệm của đúng engine/version** là nguồn để xác nhận các bảo đảm chi tiết.

## 7. Một bản ghi thay đổi có thể ảnh hưởng nhiều index entry

Giả sử P-42 đổi category từ **office** sang **home**. Một projection kiểu danh sách theo danh mục có thể lưu:

~~~text
products_by_category["office"] chứa P-42
products_by_category["home"] chưa chứa P-42
~~~

Khi cập nhật, consumer cần:

1. Bỏ P-42 khỏi office.
2. Thêm P-42 vào home.
3. Ghi lại version đã áp dụng.

Nếu hai bước đầu không nằm trong cùng transaction, có thể xuất hiện **khoảng thời gian sản phẩm nằm ở cả hai danh mục hoặc không ở danh mục nào**.

Một read model thay thế có thể lưu **một document theo productId** với category hiện hành rồi dùng index nội bộ theo category, nếu yêu cầu truy vấn và công nghệ phù hợp. Cách này giảm số bản ghi dẫn xuất phải thay đổi nhưng không loại bỏ mọi vấn đề freshness.

Điều cần xác định:

- Bản dẫn xuất phải **hội tụ về trạng thái cuối** hay phải bảo đảm **không bao giờ** có khoảng giao nhau?
- Search dùng để khám phá hay là bước quyết định có giá trị tài chính?
- Có thể hiển thị một danh sách cũ vài giây không?
- Khi đổi danh mục, việc xóa entry cũ có được kiểm chứng không?

## 8. Freshness SLO khác bảo đảm cứng

Giả sử Product Search có mục tiêu:

> **99,9%** thay đổi hợp lệ đã commit được nhìn thấy qua đường search trong vòng **5 giây**.

Đây là **SLO thống kê**, không phải bảo đảm rằng mọi truy vấn luôn trả dữ liệu mới tối đa 5 giây. Nếu có 100.000 thay đổi trong kỳ đánh giá và tất cả thay đổi được theo dõi, mục tiêu 99,9% cho phép tối đa **100 thay đổi** không đạt trong 5 giây ở kỳ đó.

Nếu nghiệp vụ yêu cầu:

> **Không bao giờ** cho phép cấp phát một sản phẩm đã hết tồn kho.

thì search freshness SLO không đủ. Cần **điểm ghi có thẩm quyền** với update/đặt giữ có điều kiện. Đây là yêu cầu **bất biến nghiệp vụ**, không phải bài toán làm giảm lag từ 5 giây xuống 500 ms.

### 8.1. Ví dụ ngân sách độ mới theo API

| Đường dùng index | Mức trễ minh họa | Khi vượt ngưỡng | Mức bảo đảm thực |
| --- | --- | --- | --- |
| Search sản phẩm theo từ khóa | p99 dưới 5 giây | Cảnh báo lag, kiểm tra nguồn ở trang chi tiết | SLO eventual freshness |
| Trang quản trị vừa sửa | Phải thấy version vừa ghi | Đọc source hoặc chờ version với timeout | Read-your-writes |
| Gợi ý sản phẩm | Có thể trễ vài phút | Hiển thị dữ liệu đã biết thời điểm cập nhật | Eventual, ít nhạy |
| Listing tình trạng còn hàng | p99 dưới 3 giây | Gắn thông tin ước lượng | Không dùng để cấp phát |
| Checkout xác nhận giá và tồn kho | Theo transaction tại nguồn | Từ chối nếu kiểm tra/giữ không thành công | Bảo vệ bất biến |
| Thu hồi quyền truy cập | Theo chính sách bảo mật, có thể phải ngay | Kiểm tra nguồn/từ chối an toàn | Không được tin index cũ |
| Báo cáo phân tích | Có thể trễ 10 phút | Hiển thị last-updated và lag | Eventual theo batch/stream |

Các ngưỡng chỉ là ví dụ thiết kế. Cần lựa chọn theo hậu quả dữ liệu cũ, năng lực hệ thống và chi phí.

### 8.2. Một chỉ mục có thể cũ theo hai cách

**Sai khác giá trị:** source P-42 version 18 giá 1.390.000, search còn v17 giá 1.500.000.

**Thiếu hoặc thừa phần tử:** một sản phẩm mới đã được tạo nhưng chưa xuất hiện trên search, hoặc sản phẩm đã xóa vẫn còn trong kết quả.

Không chỉ theo dõi việc **document theo ID chứa đúng field**, còn phải kiểm tra **membership của kết quả truy vấn**, ví dụ lọc theo category, active, price range và search terms.

### 8.3. Freshness theo thời gian và theo version

Hai metric độc lập:

~~~text
Source version: 18
Search version: 16
Version lag: 2

Committed at: 10:00:00.000
Searchable at: 10:00:02.400
Freshness lag: 2,4 giây
~~~

**Version lag** giúp nhận biết thứ tự/trạng thái nhưng không cho biết thời gian nếu tần suất update không đều. **Time lag** cho biết trải nghiệm theo thời gian nhưng cần mốc đo tin cậy. Cả hai đều hữu ích.

## 9. Đo độ mới từ chính đường query

Một mô hình đo end-to-end:

1. Ghi một thay đổi có **ID và version duy nhất** vào source.
2. Ghi nhận thời điểm commit.
3. Truy vấn đúng API/index được người dùng sử dụng cho đến khi thấy version cần thiết hoặc kết quả membership chính xác.
4. Tính **commit-to-visible latency**.
5. Tính những thay đổi **không visible trước deadline** là thất bại SLO.

Pseudocode:

~~~text
probeIndexVisibility(productId, targetVersion, committedAt, deadline):
    while now() < deadline:
        result = searchApi.queryByExpectedFilter(productId)
        if result.contains(productId)
           and result[productId].version >= targetVersion:
            return VISIBLE(now() - committedAt)
        sleep(probeInterval)

    return NOT_VISIBLE_WITHIN_DEADLINE
~~~

Đây là logic minh họa. Khi thay đổi loại **DELETE**, điều kiện probe phải là **không còn xuất hiện**; với đổi category, phải kiểm tra cả **biến mất khỏi category cũ** và **xuất hiện ở category mới**. Việc query theo ID có thể có đường đọc khác query full-text nên phải chọn loại probe đúng.

### 9.1. Tránh đo thiên lệch

Sai lầm phổ biến:

- Chỉ tính latency của event **đã xử lý thành công**, bỏ event bị kẹt hoặc mất.
- Lấy timestamp **consumer ACK** thay cho thời điểm query-visible.
- Dùng eventTime từ client thay vì commit time.
- Probe một ID ngẫu nhiên rồi suy ra mọi category/filter đều mới.
- Chỉ nhìn trung bình, bỏ p99/p99.9 và oldest pending update.
- Đồng nhất **message lag theo số lượng** với lag tính bằng giây.

Nếu một event chưa visible quá 5 phút, nó không nên biến mất khỏi bộ đo chỉ vì không có điểm kết thúc để tính latency. Cần metric **age of oldest pending** và **deadline miss count**.

### 9.2. Ví dụ SLI

\[
\text{Freshness}_{5s} =
\frac{\text{Số thay đổi đáp ứng query-visible trong 5 giây}}
{\text{Tổng thay đổi hợp lệ đã commit trong tập đánh giá}}
\]

Một SLO có thể là:

~~~text
Trong rolling window 7 ngày:
  freshness_5s >= 99,9%
  oldest_pending_age có cảnh báo riêng
  không mất event do log retention
~~~

Phải định nghĩa rõ:

- Có tính DELETE và thay đổi làm item rời khỏi bộ lọc không?
- Một event bị supersede rất nhanh bởi version mới có cần từng visible không?
- Nếu source rollback hoặc update liên tiếp, tiêu chí “đã thấy event” là gì?
- Một query ở node search nào được coi là representative?
- Bộ đếm và thời gian đánh giá có xử lý những thay đổi chưa kết thúc không?

Ví dụ index thường chỉ yêu cầu **phản ánh trạng thái mới nhất**. Nếu P-42 đổi v17→v18→v19 nhanh hơn chu kỳ refresh, v18 có thể không bao giờ xuất hiện trong search, nhưng v19 đã đúng. SLI phải dựa trên hợp đồng **hội tụ trạng thái cuối**, không đòi một trạng thái trung gian không cần thiết phải xuất hiện.

## 10. Bảo vệ read-your-writes

Một người bán sửa giá rồi quay lại trang tìm kiếm:

~~~text
10:00:00  Product API commit v18 và trả success
10:00:01  Trang admin tìm P-42 qua index -> v17
10:00:03  Index cập nhật v18
~~~

Search có thể đạt mục tiêu freshness 5 giây nhưng **trải nghiệm người vừa ghi** vẫn không tốt. Một cách xử lý là API ghi trả phiên bản commit:

~~~json
{
  "productId": "P-42",
  "committedVersion": 18,
  "priceMinor": 1390000
}
~~~

Client mang **requiredVersion=18** khi đọc tiếp.

~~~text
getForEditor(productId, requiredVersion):
    indexed = searchReadModel.get(productId)
    if indexed != null && indexed.version >= requiredVersion:
        return indexed

    authoritative = productStore.get(
        productId,
        readConsistency = requiredConsistency
    )
    return authoritative
~~~

Đây là mã giả. Đọc source phải dùng consistency phù hợp; đọc một source replica đang trễ cũng có thể trả v17.

Các phương án:

1. **Đọc nguồn ngay sau ghi** cho trang quản trị.
2. **Chờ index đạt version yêu cầu** trong một timeout ngắn, sau đó fallback.
3. **Hiển thị bản đã commit từ response** khi điều đó phù hợp, không nhầm lẫn trạng thái optimistic chưa được xác nhận.
4. **Session version token** để không cho các lần đọc trong phiên quay ngược.

Không được dùng **sleep cố định 5 giây** rồi mặc định index chắc chắn đã mới. Consumer có thể crash hoặc backlog 30 phút.

### 10.1. Monotonic reads qua nhiều replica

Nếu người dùng đã nhìn thấy v18 từ node A, request tiếp theo tới node B chỉ có v17, UI có thể “quay lùi”.

Một cơ chế có thể giữ **maxObservedVersion** theo từng productId:

~~~text
requiredVersion[P-42] = 18
Nếu read trả version < 18:
    chờ / thử node khác / đọc nguồn / trả trạng thái đang đồng bộ
~~~

**Version theo aggregate** không thể dùng như một số thứ tự toàn cục giữa hai sản phẩm khác nhau.

## 11. Vì sao dual write trực tiếp dễ mất bản cập nhật index?

Giả sử API thực hiện:

~~~text
1. Ghi Product Store
2. Ghi Search Index
3. Invalidate cache
4. Trả success
~~~

Nếu process chết sau bước 1 và trước bước 2:

~~~text
Source P-42: version 18 (đã commit)
Search P-42: version 17
Không có sự kiện bền vững nào ghi nhớ update bị bỏ dở
~~~

Đổi thứ tự thành ghi search trước source cũng có rủi ro: search hiển thị thay đổi **chưa hề commit ở nguồn**. Một request báo lỗi rồi client retry có thể tạo event trùng.

### 11.1. Transactional outbox

Khi database cho phép, ghi **source update + outbox event trong cùng transaction**:

~~~mermaid
sequenceDiagram
    participant API as Product API
    participant DB as Product DB
    participant Relay as Outbox relay
    participant Bus as Event bus
    participant Indexer as Indexer
    participant Search as Search Index
    API->>DB: Begin transaction
    API->>DB: Update product to v18
    API->>DB: Insert ProductUpdated v18 into outbox
    API->>DB: Commit both
    DB-->>API: Success
    Relay->>DB: Read pending outbox
    Relay->>Bus: Publish event
    Bus->>Indexer: Deliver event (may repeat)
    Indexer->>Search: Conditional index update
    Indexer-->>Bus: Ack after durable apply
~~~

Outbox giảm nguy cơ mất thông tin thay đổi khi API chết sau commit. Nhưng:

- Relay có thể publish xong rồi crash trước khi đánh dấu sent → **publish trùng**.
- Indexer có thể ghi index xong rồi crash trước ACK → **delivery trùng**.
- Search engine có thể ghi thành công nhưng query chưa thấy do refresh.

Vì vậy cần **idempotency, retry, versioning và visibility monitoring**. Outbox không tự tạo transaction ACID xuyên Product DB, broker và search engine.

### 11.2. Change Data Capture (CDC)

CDC lấy thay đổi từ log của source và đưa vào pipeline. Nó có thể giảm việc application quên phát event, nhưng phải xem:

- Event có đầy đủ trường phục vụ index không?
- Transaction boundary và delete được biểu diễn thế nào?
- Thứ tự trong một aggregate/key có được bảo vệ không?
- Log giữ đủ lâu khi consumer dừng?
- Khi schema đổi, consumer cũ có hiểu event không?

Một mô hình có thể dùng **outbox ghi trong transaction**, rồi **CDC phát các dòng outbox**. Cần theo dõi checkpoint và khả năng replay.

## 12. Idempotency và sai thứ tự: index mới không được quay về version cũ

Giả sử:

~~~text
Product P-42:
  v16 = price 1590000
  v17 = price 1500000
  v18 = price 1390000

Consumer nhận:
  v18 trước
  v17 đến sau do retry
~~~

Nếu indexer chỉ ghi **theo thứ tự nhận**, search có thể kết thúc ở giá 1.500.000 dù source đã lên v18.

Một event nên có:

~~~json
{
  "eventId": "evt-8f9d",
  "eventType": "ProductUpdated",
  "schemaVersion": 2,
  "aggregateType": "Product",
  "aggregateId": "P-42",
  "aggregateVersion": 18,
  "committedAt": "2026-11-14T10:00:00Z",
  "payload": {
    "productId": "P-42",
    "name": "Bàn làm việc",
    "priceMinor": 1390000,
    "category": "office",
    "active": true
  }
}
~~~

Trong đó:

- **eventId** để nhận diện bản tin trùng.
- **aggregateId** để xác định thực thể.
- **aggregateVersion** là số thứ tự thay đổi do nguồn có thẩm quyền phát hành.
- **schemaVersion** để diễn giải định dạng event.
- **committedAt** để quan sát lag khi timestamp tin cậy.

### 12.1. Event mang trạng thái đầy đủ

Nếu payload là **full-state**, quy tắc có thể là:

~~~text
apply(event):
    current = index.getMetadata(event.aggregateId)

    if current exists and event.version <= current.version:
        return ALREADY_APPLIED_OR_STALE

    atomicUpsertIfNewer(
        id = event.aggregateId,
        version = event.version,
        document = event.payload
    )
~~~

**atomicUpsertIfNewer** phải thật sự có bảo đảm nguyên tử hoặc so sánh version ở phía storage. Không được chỉ read version rồi write vô điều kiện vì hai consumer có thể tranh nhau. Với full-state event, áp dụng v18 có thể bỏ qua v17 nếu toàn bộ trạng thái cần cho index đã nằm trong v18 và không có side effect bắt buộc ở phiên bản trung gian.

### 12.2. Event dạng delta

Nếu event chỉ chứa:

~~~json
{
  "aggregateId": "inventory:SKU-8",
  "aggregateVersion": 18,
  "quantityDelta": -1
}
~~~

và projection đang ở v16, **không thể luôn nhảy thẳng lên v18**. Version 17 có thể chứa một delta -2 chưa tới. Cần phát hiện gap, đợi/replay event v17 hoặc tải lại snapshot nguồn.

**Version cao hơn chưa đủ để chứng minh delta có thể áp dụng ngay**; phải xem ngữ nghĩa payload.

### 12.3. Delete và tombstone

~~~text
10:00  ProductUpdated v17
10:01  ProductDeleted v18
10:02  Index xóa P-42
10:03  Retry ProductUpdated v17 đến
~~~

Nếu indexer insert lại v17, dữ liệu đã xóa **hồi sinh**. Cần lưu **metadata version/tombstone đã xóa** hoặc cơ chế tương đương để từ chối event cũ.

Một lựa chọn:

~~~text
P-42:
  version: 18
  deleted: true

Khi event v17 đến:
  17 <= 18 -> bỏ qua
~~~

Nếu index xóa vật lý document cùng version metadata, phải giữ phiên bản ở nơi khác hoặc dùng cơ chế versioning/retention phù hợp. Đừng đặt tombstone TTL ngắn hơn khoảng thời gian event cũ còn có thể replay.

## 13. Search index cập nhật trễ có những hậu quả nào?

### 13.1. Stale price

Search hiển thị giá cũ. Giải pháp không phải buộc toàn bộ search thành strong consistency với chi phí bất kỳ, mà là:

- Hiển thị giá có thể thay đổi nếu nghiệp vụ cho phép.
- Đọc lại giá từ source khi người dùng vào chi tiết hoặc checkout.
- Ghi snapshot giá đã chốt trong đơn hàng theo quy tắc nghiệp vụ.
- Theo dõi lỗi trải nghiệm và thời gian search lag.

### 13.2. Stale stock

Search còn chỉ báo “còn hàng” sau khi tồn kho đã hết. Người dùng có thể nhấn mua nhưng **Inventory Authority** phải làm conditional reserve/allocate, không được lấy boolean trong search để cấp phát.

### 13.3. Stale permissions

Một index quyền hoặc kết quả được cache có thể giữ thông tin **đã thu hồi**. Với đường quyết định bảo mật, không nên dựa vào eventual index như nguồn duy nhất nếu chính sách yêu cầu quyền thu hồi có hiệu lực ngay. Phải dùng quyền có thẩm quyền, cơ chế xác thực token với hợp đồng revocation rõ, hoặc fail closed khi không kiểm tra được.

### 13.4. Stale search membership

Sản phẩm P-42 chuyển từ office sang home, nhưng search:

- Có thể vẫn xuất hiện ở office.
- Chưa xuất hiện ở home.
- Có thể có hai representation nếu projection không xóa entry cũ đúng.

Kiểm tra chỉ giá trị theo productId là **chưa đủ**; phải kiểm tra kết quả lọc theo **category, active và range**.

## 14. Fallback khi index chưa đủ mới

Một nguyên tắc là **đường quyết định quan trọng phải tự bảo vệ mình**, không chỉ trông chờ SLO của search.

| Đường sử dụng | Khi index quá cũ | Cách xử lý có thể chọn |
| --- | --- | --- |
| Trang tìm kiếm | Consumer lag cao | Gắn nhãn độ mới, giảm chức năng nhạy cảm, thông báo đang cập nhật |
| Trang quản trị sau cập nhật | Chưa có requiredVersion | Chờ ngắn với timeout rồi đọc nguồn |
| Chi tiết sản phẩm | Search/cached projection cũ | Đọc dữ liệu chính theo ID |
| Checkout | Giá hoặc tồn kho trên index cũ | Bắt buộc kiểm tra/giao dịch tại nguồn |
| Dashboard | Index trễ 15 phút | Hiển thị last-updated, tránh báo cáo như thời gian thực |
| Phân quyền | Index chưa đáp ứng chính sách thu hồi | Kiểm tra nguồn hoặc từ chối an toàn |

### 14.1. Fallback không giải quyết mọi query

Nếu search GSI/index chưa có P-99 vừa mới tạo, API không thể xác minh P-99 bằng GetItem nếu **không biết ID của nó**. Fallback theo ID chỉ kiểm chứng **candidate hiện có**, không bảo đảm toàn bộ kết quả search đầy đủ.

Muốn tìm đầy đủ “mọi sản phẩm trong danh mục vừa được tạo”, có thể cần:

- Chờ index bắt kịp một checkpoint được xác định.
- Đọc từ một đường truy vấn có chỉ mục đồng bộ khác.
- Dùng một read model thích hợp với consistency requirement.
- Tạm báo kết quả có thể chưa hoàn chỉnh thay vì khẳng định đủ.

### 14.2. Tránh thác tải về nguồn

Nếu indexer dừng và mọi request search đồng loạt fallback sang Product Store, source có thể quá tải. Cần kết hợp:

- Timeout và retry có backoff/jitter hợp lý.
- Rate limiting/admission control.
- Request coalescing/single-flight cho cùng ID.
- Circuit breaker và trạng thái suy giảm được nêu rõ.
- Headroom nguồn cho những thao tác cần kiểm tra thật.

Đường fallback phải được **benchmark riêng trong điều kiện index lỗi**, không chỉ kiểm tra nó đúng với một request đơn lẻ.

## 15. Backlog và khả năng bắt kịp

Giả sử Product Store phát 1.000 thay đổi/giây, indexer chỉ xử lý được 700 thay đổi/giây trong 10 phút.

\[
B_{\text{backlog}}=(1000-700)\times600=180.000\text{ event}
\]

Sau đó tăng năng lực indexer lên 1.500 event/giây, trong khi source vẫn tạo 1.000 event/giây.

\[
R_{\text{net drain}}=1500-1000=500\text{ event/giây}
\]

Thời gian lý tưởng để dọn backlog:

\[
T_{\text{catch-up}}=\frac{180.000}{500}=360\text{ giây}=6\text{ phút}
\]

Số liệu giả định và chưa tính retry, lỗi schema, index refresh, hot key hoặc ghi lại file. Trong 6 phút catch-up ấy, một số kết quả vẫn có thể cũ.

**Consumer đã khởi động lại không đồng nghĩa chỉ mục đã đạt freshness SLO.**

### 15.1. Theo dõi số event và tuổi event

Hai queue cùng chứa 1.000 event nhưng:

- Queue A có 1.000 event vừa phát trong một giây.
- Queue B có một event bị kẹt 2 giờ và 999 event mới.

Đếm queue depth bằng nhau nhưng **mức độ lệch về thời gian khác hẳn**.

Nên đo:

- Oldest unprocessed update age.
- Broker lag/offset theo từng partition stream.
- Source-to-index throughput.
- Retry và dead-letter queue (DLQ).
- Tỷ lệ missing/version gap.
- Commit-to-query-visible p95/p99 và deadline misses.
- Chênh lệch source/index version trên tập bản ghi được đối soát.

### 15.2. Heartbeat và nguồn ít sự kiện

Nếu không có product update trong một giờ, “lag = 0 event” không chứng minh indexer vẫn sống. Một consumer chết khi queue rỗng có thể không bị phát hiện cho tới khi có event mới.

Có thể dùng **heartbeat, synthetic writes/probes, checkpoint health** và giám sát tiến trình để phân biệt **không có công việc** với **pipeline mất khả năng xử lý**.

## 16. Khi build lại index: snapshot và catch-up

Một index bị hỏng hoặc phải đổi mapping có thể cần rebuild. Nếu chỉ duyệt Product Store rồi ghi toàn bộ sang index mới trong khi người bán vẫn cập nhật giá, có khả năng:

~~~text
T0: Rebuild đọc P-42 v17
T1: Người bán cập nhật P-42 v18
T2: Stream đã áp dụng v18 vào index mới
T3: Rebuild ghi lại P-42 v17 từ snapshot cũ
=> Index mới bị quay về v17
~~~

Một quy trình an toàn hơn về mặt khái niệm:

1. Lấy snapshot hoặc xác định **source checkpoint** đủ để biết phạm vi cần rebuild.
2. Tạo **index mới** với mapping/version mới, không ghi đè mù lên index đang phục vụ.
3. Backfill dữ liệu nguồn theo batch từ snapshot.
4. Thu thập các thay đổi sau checkpoint qua CDC/outbox, áp dụng version-aware.
5. Đảm bảo các sự kiện đến trong lúc backfill không bị mất.
6. Đối soát count, version, delete và những query mẫu.
7. Chờ index mới bắt kịp tới checkpoint/độ mới yêu cầu.
8. Chuyển đường đọc/alias sang index mới khi đủ điều kiện; giữ khả năng rollback.

### 16.1. Rebuild không được ghi đè bằng snapshot cũ

Cho cả backfill và consumer dùng cơ chế **upsert-if-newer** với version nguồn có thể giúp tránh trường hợp snapshot v17 ghi sau event v18. Nhưng với event delta, vẫn phải giữ thứ tự/gap theo ngữ nghĩa.

### 16.2. Delete cần được kiểm tra riêng

Nếu P-42 đã bị xóa sau checkpoint nhưng vẫn có trong bản snapshot, rebuild có thể làm nó xuất hiện lại. Phải replay delete và giữ tombstone/version theo quy tắc, kiểm tra **không hồi sinh dữ liệu xóa** sau khi switch index.

### 16.3. Chi phí rebuild

Reindex có thể tiêu thụ:

- CPU/tokenization và I/O ghi search.
- Băng thông đọc Product Store.
- Dung lượng lưu **hai index** trong thời gian chuyển đổi.
- Capacity cho consumer catch-up.
- Cơ chế kiểm soát lỗi/timeout khi snapshot hoặc stream đổi phiên bản.

Rebuild là một workload nền lớn cần tính **headroom và p99 của API** tương tự compaction/repair.

## 17. Đối soát (reconciliation) để phát hiện index không hội tụ

Ngay cả khi đã có outbox/CDC, lỗi mapping, ACK sai hoặc event mất do retention có thể khiến một phần index sai mãi.

Ví dụ:

~~~text
Product Store:
  P-42 v18 price=1390000
  P-43 v11 category=home
  P-44 v9 deleted=true

Search Index:
  P-42 v18 price=1390000    -> OK
  P-43 v10 category=office  -> STALE
  P-44 v8 active=true       -> MISSED DELETE
~~~

Job đối soát có thể:

- So sánh version/field checksum theo ID.
- So sánh membership danh mục/active/filter.
- Lấy mẫu thường xuyên và chạy full reconciliation theo lịch nếu phù hợp.
- Sửa những bản stale bằng **update phiên bản mới hơn**.
- Báo số bản lệch, tuổi lệch, nguyên nhân và kết quả repair.

### 17.1. Reconciliation phải tránh false positive

Nếu source thay đổi ngay trong lúc scan, đọc source và index không cùng checkpoint có thể cho kết quả lệch tạm thời. Cần dùng snapshot/checkpoint hoặc chấp nhận “pending freshness window” trước khi gắn nhãn lỗi.

Ngoài ra, job repair không được lấy snapshot v17 để **ghi đè** index v18 vừa được consumer cập nhật. Phải có điều kiện version.

## 18. Độ mới liên quan cả query routing và replica

Một database có index đồng bộ ở node primary nhưng query qua replica khác có thể trả dữ liệu cũ. Một search cluster có nhiều shard và replica cũng có thể có khác biệt visibility theo thời điểm.

Những câu hỏi cần đặt:

- Request read có thể được định tuyến sang replica nào?
- Một write success đã được replica nào xác nhận theo write concern?
- Read concern/consistency level có ý nghĩa gì trên đúng sản phẩm?
- Nếu index mới trên shard A nhưng shard B chưa bắt kịp, truy vấn fan-out có thể trả kết quả hỗn hợp không?
- Pagination qua nhiều request có thể nhìn thấy thứ tự hoặc membership thay đổi không?

### 18.1. Phân trang kết quả có thể thay đổi khi index cập nhật

Giả sử người dùng xem trang 1, rồi trong một giây search index cập nhật thêm nhiều sản phẩm. Trang 2 có thể bị trùng hoặc bỏ sót item nếu dùng offset pagination trên tập kết quả biến động.

Các giải pháp tùy yêu cầu:

- Dùng keyset/cursor có tie-breaker ổn định.
- Dùng snapshot/search context khi engine hỗ trợ.
- Chấp nhận tính thời gian thực và thông báo kết quả có thể đổi.
- Không coi một cursor thường là bảo đảm snapshot toàn cục.

**Freshness và tính ổn định của phân trang** có thể là hai mục tiêu khác nhau: muốn dữ liệu mới liên tục và muốn cùng một snapshot bất biến thường cần một lựa chọn/đánh đổi rõ ràng.

## 19. Chi phí: synchronous write latency và asynchronous operational complexity

Giả sử một API có:

~~~text
10.000 product updates/giây ở đỉnh
5 truy vấn search trên mỗi lần cập nhật
3 index/read model phục vụ đường đọc khác nhau
~~~

Phương án **cập nhật index đồng bộ** có thể kéo dài đường ghi nhưng giảm lag giữa data/index trong cùng ranh giới commit. Phương án **đẩy event bất đồng bộ** rút gọn đường commit nguồn nhưng phải chi trả cho queue, consumer, retry, index refresh, reconciliation và fallback.

| Tiêu chí | Synchronous index maintenance | Asynchronous index maintenance |
| --- | --- | --- |
| Ghi vào source | Có thể phải duy trì index cùng thao tác | Thường có thể commit trước khi projection bắt kịp |
| Write latency | Có thể tăng theo index và contention | Thường ít phụ thuộc tiến trình index ngoài hệ |
| Freshness của index | Có thể chặt theo transaction/read semantics | Có lag và cần SLO + giám sát |
| Failure handling | Lỗi index có thể khiến write rollback/thất bại trong ranh giới atomic | Retry, DLQ, outbox/CDC, reconciliation |
| Scale thành phần | Gắn với storage/index của engine | Có thể scale consumer/search riêng |
| Full-text/ranking chuyên biệt | Phụ thuộc engine tích hợp | Dễ dùng search engine ngoài |
| Operational complexity | Ít thành phần hơn ở kiến trúc đơn giản | Nhiều thành phần và trạng thái hội tụ |
| Sửa index hỏng | Theo công cụ rebuild/index engine | Snapshot, catch-up, versioning và switch index |
| Chi phí đọc | Thường tối ưu theo index nội bộ | Có thể nhanh qua projection chuyên biệt |

**Không mặc định async luôn có throughput ghi lớn hơn.** Nếu source vẫn phải ghi outbox, hệ bị giới hạn broker/consumer hoặc một GSI nóng, bottleneck có thể chuyển chỗ. Phải đo cả đường ghi và đường đọc end-to-end.

### 19.1. Write amplification của index đồng bộ

Nếu cập nhật một document buộc sửa nhiều index entry, chi phí ghi tăng. Một index theo cặp (category, price) có thể tạo thao tác xóa entry cũ và thêm entry mới khi price đổi.

Chi phí cần đo:

- p50/p95/p99 write latency.
- CPU, disk I/O, index bytes và write amplification.
- Lock contention hoặc retry.
- Throughput tối đa khi nhiều khóa/index nóng.

### 19.2. Chi phí của index bất đồng bộ

Ngoài write cost của source:

- Outbox/CDC/broker storage và traffic.
- Compute của indexer và số lần retry.
- Search storage, index refresh/segment merge.
- Backfill/rebuild và dual-index tạm.
- Fallback đọc source khi lag.
- Monitoring, DLQ triage, reconciliation và incident response.

Đừng so hai thiết kế chỉ bằng **p99 của API cập nhật sản phẩm**, mà bỏ **thời gian query-visible, chi phí vận hành và tính đúng**.

## 20. Thiết kế benchmark cho độ mới index

Một phép thử tốt phải phát tải ghi **đồng thời** với truy vấn search thực tế và các sự cố nền, không chỉ gọi update rồi query một bản ghi.

### 20.1. Workload mẫu

~~~yaml
experiment: synchronous-vs-asynchronous-index
dataset:
  products: 10000000
  categories: 120
  hotCategoryWriteSharePercent: 35
  activeProductsPercent: 85
workload:
  peakWritesPerSecond: 5000
  readsPerSecond: 20000
  updates:
    - price
    - category
    - active
    - delete
  queries:
    - by_product_id
    - by_category_and_price
    - full_text
    - newly_created_products
exampleSlo:
  indexVisibleWithinSeconds: 5
  targetPercent: 99.9
  adminReadYourWrites: required
failureScenarios:
  - consumer_pause
  - broker_replay
  - out_of_order_events
  - missing_event
  - index_rebuild
  - slow_replica
  - write_burst
measure:
  - commit_to_query_visible_p50_p95_p99
  - oldest_pending_update_age
  - deadline_miss_ratio
  - index_source_version_mismatch
  - query_membership_errors
  - API_read_write_p99
  - offered_achieved_RPS
  - queue_depth_retry_DLQ
  - indexer_CPU_IO_storage
  - fallback_rate_and_latency
~~~

Đây là **đặc tả minh họa**, không phải file cấu hình chạy được trực tiếp. Cần bổ sung engine/version, topology, shard/index layout, read/write consistency, máy/đĩa/mạng và phương pháp xác minh.

### 20.2. Ma trận kịch bản

| Kịch bản | Cách tạo | Điều cần quan sát |
| --- | --- | --- |
| Baseline | Ghi/đọc đều, không lỗi | Commit-to-visible, write p99, query p99 |
| Burst | Tăng ghi 3 lần trong một phút | Index backlog và thời gian bắt kịp |
| Hot category | 35% update một category | Index hot key/shard, p99 |
| Consumer pause | Dừng indexer 2 phút trong môi trường thử | Freshness violation và fallback |
| Out-of-order | Gửi v18 trước v17 | Index không quay ngược |
| Duplicates | Giao một event nhiều lần | Idempotency, không tạo bản sao thừa |
| Delete then replay | Xóa v18, gửi lại update v17 | Không hồi sinh tài liệu |
| Category move | office → home | Không còn ở office, có ở home khi hội tụ |
| Search refresh lag | Đã index nhưng chưa searchable | Phân biệt apply và visibility |
| Replica lag | Read qua replica chậm | Read-your-writes/monotonic reads |
| Rebuild index | Snapshot + change stream cùng lúc | Không mất update và không ghi lùi |
| Backpressure | Indexer xử lý chậm hơn producer | Queue age, tài nguyên, recovery time |

Đo **cùng một tập query** trên các phương án đồng bộ và bất đồng bộ để so sánh. Phải ghi nhận **lỗi và timeout**, không loại chúng khỏi kết quả p99 như thể request chưa từng xảy ra.

### 20.3. Bộ dữ liệu kiểm chứng tính đúng

Một chuỗi thay đổi đơn giản:

~~~text
P-42 v17: category=office, price=1500000, active=true
P-42 v18: category=office, price=1390000, active=true
P-42 v19: category=home,   price=1390000, active=true
P-42 v20: deleted=true
~~~

Kiểm tra:

1. Source được cập nhật theo version hợp lệ.
2. Search không kết thúc ở v18 sau khi v19 đã được áp dụng.
3. P-42 biến mất khỏi office khi category đổi.
4. P-42 xuất hiện trong home sau v19.
5. Sau delete v20, P-42 không hồi sinh khi replay v18/v19.
6. Checkout không coi search v17 là giá có thẩm quyền.
7. Read-your-writes với requiredVersion không trả version thấp hơn.

### 20.4. Kết quả minh họa

Giả sử hệ thống có mục tiêu **99,9% update searchable trong 5 giây**, checkout phải xác minh giá ở nguồn:

| Thiết kế giả định | p99 write | p99 commit→query-visible | p99 search | Hành vi khi indexer dừng |
| --- | ---: | ---: | ---: | --- |
| Index nội bộ cập nhật trong write path, đọc primary | 110 ms | 120 ms | 80 ms | Không có consumer ngoài cho index này |
| Outbox → search, tải bình thường | 55 ms | 1,8 giây | 45 ms | Index giữ trạng thái cũ, lag tăng |
| Outbox → search, burst 3× | 60 ms | 8,5 giây | 75 ms | Backlog phải rút sau burst |
| Outbox → search với fallback admin | 65 ms | 1,8 giây cho search | 55 ms | Admin đọc nguồn; search có thể stale |

**Số liệu hoàn toàn giả định**, không dùng để xếp hạng sản phẩm thật. Nếu yêu cầu search p99 dưới 5 giây thì thiết kế burst có thể không đạt dù write p99 tốt. Nếu tính nhất quán checkout được bảo vệ tại source, search trễ ngắn có thể chấp nhận được cho trải nghiệm khám phá.

## 21. Runbook khi chỉ mục chậm cập nhật

### Bước 1 — Xác định phạm vi ảnh hưởng

- Tất cả sản phẩm hay chỉ một category/tenant?
- Chỉ giá cũ, hay cả delete và thay đổi quyền?
- Đường query nào: primary index, GSI, full-text, replica hay cache?
- Truy vấn có đang trả **phiên bản cũ**, **thiếu item** hay **item đã xóa**?

### Bước 2 — Xác minh source và checkpoint

- Source commit version nào?
- Outbox/CDC có bản ghi tương ứng không?
- Broker đã nhận chưa, consumer checkpoint ở đâu?
- Có event trong retry queue/DLQ?
- Event schema có bị reject không?

### Bước 3 — Phân biệt applied với visible

- Indexer đã lưu version mới?
- Search engine đã refresh và query được chưa?
- Đọc có đang tới replica/shard chậm?
- Query filter/mapping có loại item mới hay tạo kết quả sai?

### Bước 4 — Bảo vệ đường sử dụng nhạy cảm

- Checkout xác minh giá và tồn kho tại nguồn.
- Admin read-your-writes dùng source/fallback.
- Đường quyền truy cập fail closed hoặc kiểm tra nguồn theo chính sách.
- Search thông báo hạn chế/độ mới nếu phù hợp, không giả vờ kết quả đầy đủ.

### Bước 5 — Khôi phục và đối soát

- Sửa nguyên nhân ở relay, broker, consumer, indexer hoặc refresh.
- Tăng năng lực xử lý phù hợp để rút backlog, không để retry storm.
- Replay những event thiếu với idempotency và version.
- Chạy reconciliation với source và kiểm tra delete/membership.
- Xác nhận **oldest pending age giảm**, query-visible p99 đạt SLO và không còn mismatch kéo dài.

## 22. Những nhầm lẫn phổ biến

1. **“Index đồng bộ nên mọi bản sao đọc ngay thấy dữ liệu mới.”** Sai nếu đường đọc đến replica trễ hoặc có lớp visibility riêng.
2. **“GSI chỉ là index nội bộ nên strong read nào cũng áp dụng.”** Sai: DynamoDB GSI có quy tắc consistency riêng.
3. **“Consumer ACK nghĩa là search đã thấy.”** Chưa chắc; query visibility/refresh có thể xảy ra sau.
4. **“Eventual consistent nghĩa là tối đa 5 giây.”** Không có giới hạn cứng nếu không có hợp đồng/kiểm tra phù hợp.
5. **“Chờ cố định vài giây sẽ hết stale.”** Consumer có thể chết hoặc backlog tăng.
6. **“Đọc lại source cho mọi search candidate đảm bảo đầy đủ kết quả.”** Không phát hiện được item bị thiếu trong index nếu chưa biết ID.
7. **“Độ trễ index chỉ là thời gian broker delivery.”** Còn publish, processing, apply và visibility.
8. **“Đếm số message còn trong queue đủ đo lag.”** Cần tuổi pending event và deadline misses.
9. **“Indexer có thể ghi event theo thứ tự nhận.”** Retry/reorder có thể làm version đi lùi.
10. **“DELETE xong có thể bỏ mọi version metadata.”** Event cũ có thể hồi sinh document nếu replay.
11. **“Rebuild index từ snapshot luôn đủ.”** Thay đổi trong lúc rebuild có thể bị mất hoặc ghi đè.
12. **“Search có thể quyết định tồn kho vì gần như luôn đúng.”** Bất biến cấp phát cần điểm ghi có thẩm quyền.
13. **“Async write API nhanh hơn nghĩa là toàn hệ ít tốn tài nguyên hơn.”** Có thêm queue, indexer, reconciliation và fallback.
14. **“p99 lag tốt chứng minh không còn bản ghi sai.”** Bug mapping hoặc event mất có thể gây sai vĩnh viễn; phải đối soát.

## 23. Bài tập tình huống: tìm kiếm sản phẩm và xác nhận đơn hàng

Một nền tảng bán hàng có:

- **10 triệu sản phẩm**, 120 danh mục.
- **5.000 cập nhật/giây** ở giờ cao điểm.
- **20.000 truy vấn/giây** phục vụ tìm kiếm và listing.
- Product Store là nguồn có thẩm quyền cho giá và trạng thái sản phẩm.
- Search Index hỗ trợ full-text và lọc theo category/price.
- Người bán cần nhìn thấy giá vừa sửa trong trang quản trị.
- Khách hàng có thể xem kết quả tìm kiếm trễ vài giây, nhưng checkout không được chốt giá/tồn kho cũ trái hợp đồng.
- Có consumer retry, một số event đến sai thứ tự và khả năng indexer dừng 2 phút.

### Phần A — Chọn đường truy cập

Phân loại nhu cầu:

1. Query theo productId và cần giá chính xác.
2. Full-text search trên hàng triệu sản phẩm.
3. Listing theo category + price.
4. Checkout giữ tồn kho.
5. Admin đọc ngay sau khi sửa giá.

Với từng đường, chỉ ra nên đọc từ source/index nào, liệu đồng bộ/bất đồng bộ có hợp lý và khi nào cần fallback.

### Phần B — Thiết kế freshness contract

Đặt một freshness SLO cho search, ví dụ 99,9% cập nhật visible trong 5 giây. Ghi rõ **cách lấy t_commit, cách probe t_visible, thời điểm delete/đổi category được coi là đã visible**, và cách xử lý update bị kẹt.

Giải thích sự khác nhau giữa **p99 lag dưới 5 giây** và yêu cầu **không bao giờ cấp phát vượt tồn kho**.

### Phần C — Thiết kế pipeline

Phác thảo:

~~~text
Product API
  -> Product Store + Outbox (cùng transaction nếu hỗ trợ)
  -> Relay / CDC
  -> Broker
  -> Indexer có idempotency/version
  -> Search Index
  -> Query visibility probe
~~~

Thêm trường eventId, aggregateId, aggregateVersion, schemaVersion và dữ liệu cần dựng index. Giải thích vì sao cần **đánh dấu tombstone** khi xóa và cách xử lý event v18 đến trước v17.

### Phần D — Tính toán backlog

Nguồn tạo 1.000 event/giây, indexer xử lý 700 event/giây trong 10 phút. Sau khi tăng năng lực lên 1.500 event/giây, nguồn vẫn tạo 1.000 event/giây.

Tính backlog mới phát sinh và thời gian lý tưởng để indexer bắt kịp. Nêu những yếu tố có thể khiến thời gian thực dài hơn: retry, index refresh, hot shard, schema failures, compaction/merge và network.

### Phần E — Sự cố và kiểm thử

Thử các tình huống:

1. Source commit thành công nhưng tiến trình API chết trước publish.
2. Consumer nhận event trùng hai lần.
3. v18 đến trước v17.
4. ProductDeleted v20 đến trước event update v19 retry.
5. Search indexer dừng 2 phút.
6. Rebuild index trong khi người bán vẫn thay giá.
7. Search đã ghi document nhưng full-text query chưa thấy.
8. Search trả candidate giá cũ trong lúc checkout.

Với từng kịch bản, ghi **bất biến không được vi phạm**, cách quan sát, phương án khôi phục và thời gian lệch chấp nhận được.

### Gợi ý hướng giải

Sử dụng **source có thẩm quyền cho giá/tồn kho**, chỉ mục bên trong database cho những truy vấn được hỗ trợ với hợp đồng read thích hợp, và search index bất đồng bộ cho full-text/listing khi nghiệp vụ chấp nhận độ trễ. Áp dụng outbox/CDC, version/idempotency, theo dõi commit-to-query-visible lag, fallback read-your-writes, reconciliation và quy trình rebuild snapshot + catch-up. **Không biến việc “search gần như mới” thành bảo đảm đúng đắn cho thanh toán hoặc cấp phát**.

**Kết luận:** Độ mới của một chỉ mục NoSQL không được quyết định chỉ bởi nhãn “đồng bộ” hay “bất đồng bộ”, mà bởi **ranh giới commit, đường nhân bản, cơ chế duy trì index, thời điểm query-visible, đường định tuyến đọc và cách ứng dụng xử lý dữ liệu cũ**. Chỉ mục đồng bộ thường đưa thêm chi phí vào đường ghi để có hợp đồng nhất quán chặt hơn trong phạm vi hỗ trợ; chỉ mục bất đồng bộ tách tải nhưng cần **freshness SLO, version/idempotency, giám sát lag, fallback và đối soát**. Hãy chọn theo truy vấn và bất biến nghiệp vụ, rồi kiểm chứng độ mới **ở chính API mà người dùng thực sự gọi**.
