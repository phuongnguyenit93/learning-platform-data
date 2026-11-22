# Vai trò lưu trữ chính, bộ nhớ đệm, công cụ tìm kiếm và nguồn dữ liệu dẫn xuất

Một ứng dụng có thể sử dụng MongoDB, Redis, OpenSearch và một cơ sở dữ liệu NoSQL khác cùng lúc. Điều này không nhất thiết có nghĩa ứng dụng đang lưu bốn bản dữ liệu ngang hàng. Mỗi hệ thống có thể đảm nhận một **vai trò khác nhau**: giữ dữ liệu có thẩm quyền, tăng tốc đọc, phục vụ truy vấn tìm kiếm, hoặc xây dựng một cách nhìn dữ liệu được tính từ nguồn khác.

Đây là một phần quan trọng của **tư duy NoSQL**: chọn nơi lưu dữ liệu theo trách nhiệm và kiểu truy cập, không chỉ theo nhãn “document”, “key–value”, “wide-column” hay “graph”. **NoSQL là nhóm công nghệ/mô hình dữ liệu; vai trò kiến trúc do cách ứng dụng sử dụng hệ thống đó quyết định.** Một sản phẩm như Redis hoặc MongoDB có thể đảm nhiệm nhiều vai trò ở các hệ thống khác nhau.

## 1. Phân biệt bốn vai trò bằng quyền sở hữu dữ liệu

| Vai trò | Câu hỏi mà hệ thống trả lời | Dữ liệu có thẩm quyền không? | Khi mất dữ liệu, xử lý thế nào? | Yêu cầu nổi bật |
| --- | --- | --- | --- | --- |
| **Lưu trữ chính (primary store/system of record)** | Trạng thái nghiệp vụ hiện tại, đã được chấp nhận là gì? | **Có**, đối với dữ liệu mà nó sở hữu | Khôi phục từ bản sao, nhật ký và bản sao lưu; có thể phát sinh mất mát nghiệp vụ nếu không khôi phục được | Đúng đắn, tính bền vững, quy tắc cập nhật, khôi phục |
| **Bộ nhớ đệm (cache)** | Có thể trả lại một kết quả đã lưu nhanh hơn không? | Thông thường **không** | Xóa/làm ấm lại hoặc đọc từ nguồn chính | Độ trễ thấp, TTL, loại bỏ bản cũ, kiểm soát tải |
| **Công cụ tìm kiếm (search engine/index)** | Bản ghi nào khớp từ khóa, bộ lọc và độ liên quan? | Thông thường **không** đối với bản ghi nghiệp vụ gốc | Lập chỉ mục lại từ nguồn chính hoặc luồng sự kiện đủ tin cậy | Phân tích văn bản, lập chỉ mục, xếp hạng, truy vấn linh hoạt |
| **Nguồn dữ liệu dẫn xuất (derived store/read model)** | Dữ liệu đã được biến đổi, kết hợp hoặc tổng hợp để phục vụ một góc nhìn là gì? | Thông thường **không** đối với sự kiện/dữ liệu gốc | Tính lại, đồng bộ lại hoặc phát lại sự kiện từ nguồn | Mô hình đọc tối ưu, độ mới, đồng bộ, khả năng tái tạo |

Các câu hỏi sau giúp xác định vai trò trước khi chọn công nghệ:

1. **Ai có quyền quyết định giá trị đúng?** Nếu hai bản sao bất đồng về giá sản phẩm, số dư hoặc trạng thái đơn hàng, hệ thống nào thắng?
2. **Có thể xóa và dựng lại kho này không?** Nếu có, dựa vào nguồn nào và mất bao lâu?
3. **Đường ghi đi qua đâu?** Ghi nghiệp vụ phải thành công ở đâu trước khi ứng dụng xác nhận với người dùng?
4. **Cho phép chậm đồng bộ bao lâu?** Một kết quả cũ 200 ms, 30 giây hay vài phút có chấp nhận được với từng màn hình không?

“Chính” ở đây là **chính cho một miền dữ liệu cụ thể**. Hệ thống có thể dùng một kho chính cho danh mục sản phẩm, một kho chính khác cho giao dịch, và nhiều kho phụ để phục vụ đọc. Không nhất thiết có một cơ sở dữ liệu duy nhất là nguồn chân lý của toàn ứng dụng.

## 2. Lưu trữ chính: nơi quyết định trạng thái nghiệp vụ

### 2.1. Trách nhiệm

Kho lưu trữ chính giữ dữ liệu mà nghiệp vụ cần bảo toàn: hồ sơ khách hàng, sản phẩm, đơn hàng, sự kiện có thẩm quyền hoặc trạng thái thiết bị. Nó thường đảm bảo:

- **Ghi có kiểm soát:** xác thực điều kiện cập nhật, quyền truy cập, ràng buộc, phiên bản hoặc giao dịch phù hợp.
- **Tính bền vững:** một ghi đã xác nhận phải đáp ứng cam kết lưu trữ đã cấu hình; cần chiến lược replica, backup, restore và phục hồi thảm họa.
- **Khả năng truy vết:** biết ai thay đổi gì, khi nào, và xác định được dữ liệu nào là phiên bản được chấp nhận.
- **Đọc đúng ở điểm quyết định:** những thao tác như xác nhận giá cuối cùng, giữ chỗ hay trừ tồn kho phải đọc/ghi từ nguồn có đủ bảo đảm nhất quán.

Ví dụ, một dịch vụ danh mục có thể dùng **MongoDB** làm kho chính cho tài liệu sản phẩm:

~~~json
{
  "_id": "product-42",
  "name": "Bàn làm việc gỗ",
  "price": 1490000,
  "currency": "VND",
  "categoryId": "furniture",
  "version": 7,
  "updatedAt": "2026-10-01T09:00:00Z"
}
~~~

Khi người bán đổi giá, API ghi vào bản ghi có thẩm quyền; hệ thống chỉ thông báo cập nhật thành công sau khi thao tác ghi đáp ứng điều kiện nhất quán/bền vững đã định. Với ghi đồng thời, có thể dùng cập nhật có điều kiện theo **version** để tránh một yêu cầu cũ ghi đè yêu cầu mới:

~~~text
UPDATE product-42
SET price = 1390000, version = 8
ONLY IF version = 7

Nếu version hiện tại đã là 8 hoặc 9:
  → báo xung đột hoặc tải lại trước khi sửa.
~~~

Đây là **ý tưởng kiểm soát đồng thời**, không phải cú pháp chung cho mọi NoSQL. Cách thực hiện phụ thuộc vào khả năng của từng cơ sở dữ liệu (ví dụ conditional write, compare-and-set, giao dịch hoặc atomic update).

### 2.2. Chọn công nghệ theo quy tắc nghiệp vụ

- **Document database** như MongoDB phù hợp khi một thực thể có cấu trúc lồng nhau, hay được đọc theo tài liệu và có những cập nhật có thể được gom theo ranh giới tài liệu.
- **Key–value** như DynamoDB phù hợp khi access pattern, khóa truy cập, yêu cầu mở rộng và cơ chế ghi có điều kiện được thiết kế rõ từ đầu.
- **Wide-column** như Cassandra thường được cân nhắc cho khối lượng ghi lớn và truy cập theo partition/key đã dự kiến, với cách thiết kế nhất quán theo nhu cầu.
- **Graph database** như Neo4j có thể là kho chính của các quan hệ nếu nghiệp vụ thật sự sở hữu và cập nhật quan hệ ở đó.

Không nên suy luận rằng “NoSQL thì không có giao dịch” hoặc “NoSQL luôn eventual consistency”. Bảo đảm giao dịch, atomicity, nhất quán đọc/ghi và khả năng phục hồi **khác nhau theo sản phẩm, thao tác, cấu hình và cách triển khai**. Nếu một bất biến trải qua nhiều bản ghi, cần kiểm tra chính xác hệ thống có bảo vệ được bất biến đó hay không.

**Dấu hiệu nhận biết:** nếu xóa kho này mà không còn nguồn đáng tin cậy để dựng lại các giao dịch đã được chấp nhận, nó đang đóng vai trò lưu trữ chính.

## 3. Bộ nhớ đệm: tăng tốc đọc, chấp nhận dữ liệu tạm thời

Cache giữ những kết quả có thể lấy lại từ nơi khác, thường bằng khóa đơn giản. Ví dụ **Redis** lưu chi tiết sản phẩm đã truy vấn để giảm số lần đọc MongoDB:

~~~text
product:42 → {"name":"Bàn làm việc gỗ","price":1490000,"version":7}
TTL: 60 giây
~~~

Một request đọc điển hình theo mẫu **cache-aside**:

~~~text
getProduct(id):
    result = cache.get("product:" + id)
    if result tồn tại:
        return result

    product = primaryStore.get(id)
    if product không tồn tại:
        return NOT_FOUND

    cache.set("product:" + id, product, ttl = 60 giây)
    return product
~~~

Đối với cập nhật, một cách thường dùng là **ghi kho chính trước, sau đó vô hiệu hóa cache**:

~~~text
updateProduct(id, newPrice, expectedVersion):
    primaryStore.updateConditionally(id, newPrice, expectedVersion)
    phát tín hiệu/vô hiệu hóa cache["product:" + id]
    return kết quả ghi của primaryStore
~~~

Đoạn này mô tả luồng nghiệp vụ; **ghi chính và xóa cache không mặc nhiên nguyên tử**. Nếu bước xóa cache thất bại, cache có thể trả lại dữ liệu cũ cho đến khi TTL hết hoặc một cơ chế đồng bộ sửa lại. Cần chọn chiến lược theo mức độ chấp nhận dữ liệu cũ:

| Chiến lược | Hoạt động | Đánh đổi |
| --- | --- | --- |
| **Cache-aside** | Ứng dụng đọc cache, miss thì đọc nguồn chính và điền cache | Dễ áp dụng, nhưng cần xử lý miss và invalidation |
| **Read-through** | Lớp cache tự gọi loader khi miss | Đơn giản hóa phía ứng dụng nhưng phụ thuộc khả năng cache/adapter |
| **Write-through** | Ghi qua lớp cache đồng thời cập nhật kho bền vững theo hợp đồng triển khai | Tăng chi phí ghi; cần hiểu rõ trường hợp lỗi từng bên |
| **Write-behind/write-back** | Ghi vào cache trước, đẩy xuống kho bền vững sau | Có thể tăng tốc ghi nhưng tăng nguy cơ mất/chậm dữ liệu; không phù hợp mặc định cho giao dịch quan trọng |

Các vấn đề vận hành thường gặp:

- **Dữ liệu cũ (stale cache):** TTL là giới hạn hết hạn tương đối, không bảo đảm cập nhật tức thời. Invalidation bằng sự kiện, phiên bản hoặc đọc lại nguồn chính giúp giảm sai lệch.
- **Cache stampede:** nhiều request cùng miss một khóa phổ biến làm quá tải nguồn chính. Có thể dùng đồng bộ request, single-flight/lock ngắn, TTL phân tán (jitter), hoặc làm ấm cache.
- **Cache penetration:** liên tục hỏi khóa không tồn tại. Có thể dùng negative caching TTL ngắn và giới hạn lưu lượng, tùy trường hợp.
- **Cache eviction/outage:** bản ghi có thể biến mất trước TTL do chính sách bộ nhớ; ứng dụng cần đường đọc từ kho chính và giới hạn tải khi cache lỗi.
- **Thay đổi dữ liệu liên quan:** một giá trị nguồn có thể xuất hiện trong nhiều cache key; phải biết các key phụ thuộc hoặc dùng version/namespace để tránh sót.

**Một sản phẩm không bị khóa vào một vai trò:** Redis có cơ chế persistence và cấu trúc dữ liệu để làm kho chính trong một số bài toán. Khi Redis giữ dữ liệu không thể phục hồi từ nơi khác, phải đánh giá nó như **primary store** về độ bền, mất dữ liệu, backup và phục hồi; không được mặc định rằng cứ là Redis thì chỉ là cache.

## 4. Công cụ tìm kiếm: tối ưu câu hỏi “bản ghi nào liên quan?”

Kho chính thường xuất sắc với truy cập theo ID, khóa, partition hoặc tập điều kiện đã biết. Người dùng lại có thể muốn:

- Tìm “bàn gỗ nhỏ cho phòng ngủ” dù không gõ đúng tên sản phẩm.
- Lọc theo giá, danh mục, thuộc tính; sắp xếp theo độ liên quan.
- Tìm gần đúng, hỗ trợ tách từ, chuẩn hóa dấu, đồng nghĩa, gợi ý và facet.

Một **search engine** như Elasticsearch hoặc OpenSearch tổ chức dữ liệu để trả lời những truy vấn này. Nó xây dựng **inverted index** (ánh xạ token sang những tài liệu chứa token), cùng cấu trúc phục vụ lọc, tổng hợp và xếp hạng.

Ví dụ, từ nguồn chính:

~~~json
{
  "id": "product-42",
  "name": "Bàn làm việc gỗ",
  "description": "Bàn nhỏ gọn dùng trong phòng ngủ",
  "price": 1490000,
  "category": "furniture"
}
~~~

Hệ thống lập tài liệu tìm kiếm có những trường đã được chọn/mở rộng để phục vụ truy vấn. Khi người dùng tìm “bàn nhỏ phòng ngủ”, engine có thể trả về ID, điểm phù hợp và đoạn mô tả; API dùng ID đó để mở chi tiết.

**Điều cần tách bạch:** search index thường chỉ là **bản sao phục vụ truy vấn**, được cập nhật không đồng bộ sau khi kho chính thay đổi. Vì vậy:

1. Kết quả có thể còn hiển thị sản phẩm vừa bị ẩn/xóa hoặc giá cũ trong một khoảng ngắn.
2. Điểm relevance không phải quy tắc đúng/sai của nghiệp vụ.
3. Khi thao tác mua, đặt chỗ hoặc thanh toán, phải **xác nhận lại giá, quyền truy cập, trạng thái và tồn kho từ nguồn có thẩm quyền**.
4. Nếu index bị hỏng/mất, cần có khả năng **reindex** từ nguồn hoặc dữ liệu lịch sử còn giữ được.

Search engine vẫn có thể được thiết kế là kho chính cho một số dữ liệu tìm kiếm/log nhất định, nhưng khi ấy phải chủ động chịu trách nhiệm lưu trữ, sao lưu và nhất quán của **kho chính**. Việc engine hỗ trợ ghi/xóa tài liệu không tự biến nó thành nguồn chân lý của toàn miền nghiệp vụ.

## 5. Nguồn dữ liệu dẫn xuất: xây một cách nhìn mới từ dữ liệu gốc

**Dữ liệu dẫn xuất** là dữ liệu được **tạo ra từ một hoặc nhiều nguồn có thẩm quyền** bằng biến đổi, tổng hợp, làm giàu hoặc sắp xếp lại. “Nguồn dữ liệu dẫn xuất” trong kiến trúc thường được gọi là **derived store, materialized view, projection hoặc read model**, tùy cách thiết kế.

Ví dụ, danh mục sản phẩm có dữ liệu gốc theo từng sản phẩm nhưng trang người bán cần:

~~~json
{
  "sellerId": "seller-9",
  "activeProductCount": 132,
  "minimumPrice": 99000,
  "categories": ["furniture", "lighting"],
  "lastCatalogUpdate": "2026-10-01T09:00:00Z"
}
~~~

Bản tóm tắt này **không phải một sản phẩm gốc**. Nó được tính từ nhiều sản phẩm. Lưu riêng nó giúp trang người bán đọc một lần thay vì quét và tổng hợp hàng trăm tài liệu sau mỗi request.

Những dạng dẫn xuất thường gặp:

- **Read model cho CQRS:** mô hình chỉ để đọc, khác cấu trúc mô hình xử lý lệnh; ví dụ một tài liệu chứa sẵn thông tin đơn hàng, khách hàng và trạng thái giao hàng để vẽ màn hình theo dõi.
- **Bảng/tài liệu tổng hợp:** số lượng sản phẩm, doanh thu theo ngày, thống kê hoạt động theo người bán hoặc khu vực.
- **Bản sao phi chuẩn hóa:** gom dữ liệu từ nhiều nguồn nhằm tối ưu một truy vấn hoặc màn hình.
- **Đồ thị quan hệ hay gợi ý:** dựng cạnh quan hệ/gợi ý từ sự kiện và thực thể có thẩm quyền.

**Search index cũng là một loại dữ liệu dẫn xuất** nếu được xây từ dữ liệu nguồn. Ta vẫn thường gọi riêng “search” vì mục tiêu và cơ chế truy vấn của nó đặc thù. Tương tự, cache cũng có thể chứa giá trị tính sẵn nhưng được phân loại theo **hợp đồng vòng đời**: cache dễ bị loại bỏ, còn read model thường được duy trì lâu hơn, có quy trình cập nhật và tái tạo rõ ràng.

### 5.1. Cập nhật bản dẫn xuất như thế nào?

Có ba cách phổ biến:

| Cách cập nhật | Ví dụ | Giới hạn cần nhớ |
| --- | --- | --- |
| **Batch định kỳ** | Mỗi đêm tính lại số liệu bán hàng | Dễ triển khai; kết quả cũ giữa hai lần chạy |
| **Change Data Capture (CDC)** | Theo dõi thay đổi đã commit của kho chính | Cần theo dõi offset, thứ tự, schema và khởi tạo dữ liệu ban đầu |
| **Sự kiện nghiệp vụ** | ProductUpdated, OrderPaid được xử lý bởi consumer | Cần bảo đảm sự kiện được phát tin cậy và xử lý lại an toàn |

Lỗi kinh điển là:

~~~text
1. Ghi thành công vào primary store.
2. Gọi message broker để phát ProductUpdated.
3. Ứng dụng chết trước bước 2.
→ Primary đã đổi, nhưng search/read model không nhận được sự kiện.
~~~

Một giải pháp thường dùng là **transactional outbox**: ghi dữ liệu nghiệp vụ và một bản ghi outbox **trong cùng ranh giới giao dịch mà kho chính hỗ trợ**, sau đó tiến trình riêng phát outbox sang message broker. Cách này giải quyết khoảng trống giữa commit dữ liệu và lưu dấu ý định phát sự kiện; **không tự bảo đảm tiêu thụ đúng một lần**. Consumer phải xử lý bản tin lặp và các trường hợp mất thứ tự.

Ví dụ sự kiện có danh tính và phiên bản:

~~~json
{
  "eventId": "evt-901",
  "eventType": "ProductPriceChanged",
  "productId": "product-42",
  "version": 8,
  "price": 1390000,
  "occurredAt": "2026-10-01T09:01:00Z"
}
~~~

Một consumer có thể nhớ phiên bản đã áp dụng cho từng sản phẩm và bỏ qua sự kiện trùng/cũ. Nhưng với sự kiện kiểu **delta** (ví dụ “giảm 1 sản phẩm”), không thể tùy tiện bỏ qua phiên bản thiếu: phải phát hiện lỗ hổng, đọc lại snapshot hoặc phát lại lịch sử đầy đủ. Tính **idempotent**, thứ tự theo thực thể, retry có giới hạn, dead-letter queue và khả năng **backfill/rebuild** là phần thiết kế của kho dẫn xuất.

### 5.2. Tính nhất quán giữa nguồn chính và bản dẫn xuất

Nếu đơn hàng được ghi vào kho chính lúc **10:00:00** và read model nhận được sự kiện lúc **10:00:02**, màn hình tổng hợp có thể chậm hai giây. Khoảng chậm đó được gọi là **độ trễ đồng bộ** (replication/projection lag); đây là ví dụ minh họa, không phải cam kết cố định.

Cần quy định độ mới theo nghiệp vụ:

- Thống kê lượt xem: chậm vài phút có thể chấp nhận.
- Danh sách đơn vừa tạo: nên có cơ chế **read-your-writes** hoặc tạm đọc từ nguồn chính để người dùng thấy hành động của mình.
- Tồn kho/giữ chỗ/thanh toán: kiểm tra điều kiện ngay tại kho có thẩm quyền và với atomicity/transaction đủ mạnh.

Một read model nhanh nhưng chậm 3 giây có thể phù hợp cho dashboard, lại không phù hợp để quyết định bán món hàng cuối cùng.

## 6. Một luồng hoàn chỉnh: ứng dụng bán hàng

Giả sử ứng dụng dùng:

- **MongoDB** làm kho chính của danh mục sản phẩm.
- **Redis** lưu cache chi tiết sản phẩm hay được xem.
- **OpenSearch** cho tìm kiếm toàn văn, lọc và xếp hạng.
- **Một collection NoSQL dẫn xuất** lưu thống kê theo người bán và category.

~~~mermaid
flowchart TD
    W["API cập nhật sản phẩm"] --> P[("MongoDB\nKho chính")]
    P --> O["Outbox / CDC"]
    O --> E["Luồng thay đổi"]
    E --> S[("OpenSearch\nChỉ mục tìm kiếm")]
    E --> V[("NoSQL projection\nThống kê người bán")]
    E --> I["Thông báo vô hiệu hóa cache"]
    I --> C[("Redis\nCache chi tiết")]
    R["API đọc chi tiết"] --> C
    R -->|"Cache miss: đọc nguồn"| P
    Q["API tìm kiếm"] --> S
    D["API trang tổng hợp"] --> V
~~~

Diễn biến khi người bán đổi giá sản phẩm:

1. API xác thực điều kiện, ghi giá mới và phiên bản mới vào **MongoDB**. Đây là bước quyết định nghiệp vụ.
2. Outbox/CDC đưa thay đổi đã commit vào luồng xử lý. Bộ lập chỉ mục cập nhật **OpenSearch**, bộ xây projection cập nhật thống kê; sự kiện vô hiệu hóa khóa cache tương ứng.
3. Trong khoảng đồng bộ, một request **tìm kiếm** có thể còn thấy giá cũ, trong khi request **đọc trực tiếp từ kho chính** đã thấy giá mới.
4. Khi khách hàng bấm mua, ứng dụng lấy giá và điều kiện đặt hàng được chấp nhận từ **nguồn có thẩm quyền**, không dựa riêng vào nội dung index/cache.

Một cách chia trách nhiệm thực dụng là: **ghi chuẩn xác ở primary; đọc thường xuyên qua cache; truy vấn từ khóa qua search; màn hình tổng hợp qua projection**. Không yêu cầu mọi kho dùng cùng một kiểu dữ liệu hay cùng một cam kết nhất quán.

## 7. Thiết kế cho lỗi và khôi phục

| Sự cố | Tác động chính | Phản ứng phù hợp |
| --- | --- | --- |
| Cache hết hạn, bị eviction hoặc Redis tạm ngừng | Đọc chậm hơn; tải dồn về primary | Fallback có kiểm soát, hạn chế tải, làm ấm lại cache |
| Search index chậm cập nhật | Kết quả tìm kiếm cũ/thiếu trong một khoảng | Theo dõi indexing lag, retry/reindex, kiểm tra lại dữ liệu tại điểm giao dịch |
| Consumer projection dừng | Dashboard/read model bị trễ | Theo dõi consumer lag, xử lý retry/DLQ, replay từ checkpoint hoặc backfill |
| Sự kiện đến trùng hoặc lệch thứ tự | Có nguy cơ cộng đúp/ghi đè ngược trạng thái | Dùng event ID, version/offset, cập nhật idempotent, phục hồi khi thiếu sự kiện |
| Kho chính lỗi hoặc mất dữ liệu | Có thể ảnh hưởng trực tiếp tính đúng và toàn vẹn nghiệp vụ | Failover theo thiết kế, backup/restore, kiểm tra RPO/RTO và khả năng phục hồi |

**RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa được phép khi khôi phục; **RTO (Recovery Time Objective)** là thời gian phục hồi mục tiêu. Hai chỉ số này đặc biệt quan trọng với kho chính, vì cache, chỉ mục tìm kiếm hoặc projection **không mặc nhiên thay thế được** lịch sử gốc đã mất.

Đừng chỉ giám sát máy chủ “đang chạy”. Với những kho sao chép, cần theo dõi **tuổi dữ liệu mới nhất, queue/consumer lag, số lỗi retry, số bản tin vào dead-letter queue, thời gian reindex** và sự sai khác giữa projection với nguồn. Một hệ thống vẫn trả HTTP 200 nhưng dùng bản dữ liệu dẫn xuất quá cũ vẫn có thể sai yêu cầu sản phẩm.

## 8. Chọn vai trò trước, chọn cơ sở dữ liệu sau

Khi thiết kế một tính năng, có thể đi theo trình tự:

1. **Xác định thực thể và bất biến:** dữ liệu nào không được phép mất, những điều kiện nào phải luôn đúng?
2. **Chọn chủ sở hữu của từng dữ liệu:** dịch vụ/kho nào được phép chấp nhận lệnh thay đổi? Những kho còn lại nhận bản sao từ đâu?
3. **Liệt kê đường đọc:** đọc theo ID, tra cứu khóa, tìm văn bản, lọc nhiều thuộc tính, tổng hợp, truy vấn quan hệ?
4. **Định nghĩa mức độ mới cần thiết:** thao tác nào có thể eventual consistency, thao tác nào cần dữ liệu đã xác nhận mới nhất?
5. **Thiết kế đồng bộ và khôi phục:** cache invalidation, outbox/CDC, idempotency, reindex, rebuild, backup.
6. **Cuối cùng chọn sản phẩm:** MongoDB, DynamoDB, Redis, Cassandra, Neo4j, OpenSearch… dựa trên khả năng thực tế và tải dự kiến, không dựa vào “NoSQL nào nhanh nhất”.

### Những nhầm lẫn cần tránh

- **“Redis luôn là cache.”** Sai: vai trò phụ thuộc vào dữ liệu có thể tái tạo hay không và cam kết lưu trữ.
- **“OpenSearch chứa đủ mọi trường nên có thể bỏ kho gốc.”** Không suy ra được: khả năng truy vấn không thay thế các bất biến, giao dịch và chính sách phục hồi của nguồn có thẩm quyền.
- **“Đã ghi vào database thì mọi màn hình phải thấy ngay.”** Không đúng khi có cache, index hoặc projection cập nhật bất đồng bộ; cần quy định rõ độ mới.
- **“Dữ liệu dẫn xuất chỉ là dữ liệu tạm.”** Không nhất thiết: projection có thể được duy trì lâu dài và quan trọng cho sản phẩm, nhưng cần biết cách tái tạo và đối soát từ nguồn.
- **“Mỗi vai trò bắt buộc một công nghệ riêng.”** Không bắt buộc: một công nghệ có thể phục vụ nhiều vai trò, miễn ranh giới trách nhiệm và bảo đảm được hiểu rõ.
- **“Mọi bản sao đều phải nhất quán mạnh.”** Chi phí đồng bộ mạnh có thể không cần cho tìm kiếm/thống kê; nhưng không được dùng dữ liệu cũ để quyết định một giao dịch yêu cầu đúng tuyệt đối.

## 9. Bài tập tình huống

Một hệ thống đặt chỗ có ba màn hình: **(A)** xác nhận còn phòng và giữ phòng, **(B)** tìm phòng theo địa điểm và tiện nghi, **(C)** thống kê số lượt đặt theo tháng. Trang chi tiết phòng được xem rất thường xuyên.

Hãy xác định vai trò và mức độ nhất quán cho từng yêu cầu:

| Nhu cầu | Vai trò thích hợp | Lý do |
| --- | --- | --- |
| (A) Giữ phòng, ngăn hai khách đặt trùng | **Kho chính** với ghi có điều kiện/giao dịch phù hợp | Quyết định ràng buộc nghiệp vụ phải đúng tại lúc commit |
| (B) Tìm phòng theo câu mô tả và bộ lọc | **Search index** | Phục vụ token hóa, relevance, nhiều bộ lọc; xác thực lại khả dụng trước khi đặt |
| (C) Đếm lượt đặt theo tháng | **Projection/tổng hợp dẫn xuất** | Tính từ sự kiện đặt chỗ, tối ưu đọc dashboard; chấp nhận độ trễ đã công bố |
| Đọc trang chi tiết nhiều lần | **Cache** trước kho chính | Giảm độ trễ/tải; cần TTL và invalidation khi giá hoặc nội dung thay đổi |

Điểm quyết định nằm ở câu hỏi: **“Nếu các kho trả lời khác nhau, kho nào có quyền quyết định hành động nghiệp vụ này?”** Đáp án có thể khác nhau cho mỗi loại dữ liệu và mỗi luồng sử dụng. Nhận diện được ranh giới đó sẽ giúp tận dụng điểm mạnh của NoSQL mà vẫn giữ được tính đúng đắn của hệ thống.
