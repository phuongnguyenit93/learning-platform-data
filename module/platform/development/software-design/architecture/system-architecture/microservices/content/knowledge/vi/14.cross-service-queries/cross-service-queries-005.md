# Độ trễ cập nhật, dữ liệu cũ và cách thể hiện cho người dùng

Trong hệ thống microservices, một thay đổi có thể đã được service sở hữu dữ liệu ghi nhận thành công nhưng màn hình đọc dữ liệu từ cache, read replica, search index hoặc CQRS read model vẫn hiển thị trạng thái trước đó. Hiện tượng này là hệ quả thường gặp của **đồng bộ bất đồng bộ và eventual consistency**, không đồng nghĩa thao tác vừa thực hiện đã thất bại.

Ví dụ: Payments xác nhận đã thu tiền, nhưng trang đơn hàng dùng projection của Ordering còn hiển thị “Chưa thanh toán” trong vài giây. Nếu UI không phân biệt việc thanh toán đã được xác nhận với việc danh sách chưa đồng bộ, người dùng có thể thanh toán lại và gây rủi ro giao dịch trùng.

Bài học này tập trung vào **độ trễ cập nhật**, **dữ liệu cũ (stale data)** và **cách diễn đạt trung thực cho người dùng** khi truy vấn liên dịch vụ. Mục tiêu là thiết kế backend, hợp đồng API, chỉ số quan sát và trạng thái UI giúp người dùng biết điều gì đã thành công, điều gì còn chờ và dữ liệu hiện tại có đủ mới để ra quyết định hay không.

## 1. Ba câu hỏi phải tách riêng

1. **Write/command đã hoàn tất chưa?** Service có thẩm quyền đã commit thay đổi hoặc mới chỉ accepted để xử lý sau?
2. **Bản sao đã nhận thay đổi chưa?** Read model, replica, cache hoặc search index đã bắt kịp chưa?
3. **Người dùng đang nhìn dữ liệu ở thời điểm nào?** Snapshot có thể phục vụ việc xem thông tin hay được phép dùng để thực hiện một hành động quan trọng?

~~~text
Người dùng                 Payments                Read model
    |                         |                         |
    |-- CapturePayment ------>|                         |
    |                         | commit CAPTURED         |
    |<-- CAPTURED ------------|                         |
    |                         |-- PaymentCaptured ----->|
    |                                                   | đang chờ event
    |-- GET /orders/1001 ------------------------------->|
    |<-- payment=PENDING (snapshot cũ) ------------------|
    |                                                   | áp dụng event
    |-- GET /orders/1001 ------------------------------->|
    |<-- payment=CAPTURED -------------------------------|
~~~

Thành công của một HTTP GET từ read model chỉ chứng minh yêu cầu đọc được phục vụ; nó không chứng minh snapshot phản ánh mọi sự kiện mới nhất. Ngược lại, trạng thái cũ ở read model không bác bỏ kết quả commit đã được owner xác nhận.

**Nguyên tắc:** các quyết định thay đổi tiền, tồn kho, quyền hay trạng thái nghiệp vụ phải dùng dữ liệu và luật của owner. Projection có thể phục vụ truy vấn nhanh, nhưng phải có hợp đồng về độ mới và cách xử lý khi chưa đồng bộ.

## 2. Các khái niệm cần phân biệt

| Thuật ngữ | Nghĩa chính xác | Dễ bị nhầm với |
| --- | --- | --- |
| Update propagation delay | Thời gian từ commit ở nguồn đến khi bản sao áp dụng thay đổi | Query latency |
| Staleness | Mức snapshot tụt so với trạng thái nguồn cần dùng | Thời gian kể từ khi API trả dữ liệu |
| Query latency | Thời gian API đáp ứng request đọc | Freshness |
| Consumer lag | Độ tụt tiến độ tiêu thụ record ở broker | Thời gian staleness end-to-end |
| Replica lag | Độ chậm sao chép dữ liệu từ primary sang replica | TTL cache |
| Cache age | Thời gian từ lúc cache entry được tạo hoặc refresh | Độ mới của source |
| Read-your-writes | Người dùng có thể thấy kết quả ghi thành công của chính mình trong những lần đọc tiếp theo | Eventual consistency thuần túy |
| Monotonic reads | Một phiên không thấy dữ liệu tụt về version cũ hơn đã quan sát | Query nhanh |
| Eventual consistency | Các bản sao cuối cùng hội tụ nếu không có thay đổi mới và hệ thống hoạt động bình thường | Cam kết hội tụ trong số giây cố định |
| Bounded staleness | Có giới hạn độ cũ rõ trong điều kiện được xác định | Ước lượng chung chung “gần realtime” |

Eventual consistency là mô hình nhất quán, không bảo đảm thời gian cụ thể chỉ từ tên gọi. Nếu hệ thống chỉ đặt mục tiêu 99% bản ghi xuất hiện trong 5 giây, phải gọi đó là **SLO**, không khẳng định mọi bản ghi luôn luôn dưới 5 giây.

### Bốn timestamp có ý nghĩa khác nhau

| Thời gian | Ai ghi nhận | Có thể nói với người dùng |
| --- | --- | --- |
| committedAt/sourceOccurredAt | Service owner khi nghiệp vụ được xác nhận | “Nguồn ghi nhận lúc…” nếu xác thực |
| projectedAt | Read model sau khi áp dụng event | “Bản tổng hợp xử lý sự kiện lúc…” |
| fetchedAt | Query API hoặc client khi lấy response | “Trang tải dữ liệu lúc…” |
| displayedAt | UI khi hiển thị | Không đại diện cho độ mới của nguồn |

Nếu GET được gửi lúc 10:10 và API trả snapshot từ source lúc 10:02, ghi “Dữ liệu cập nhật lúc 10:10” là gây hiểu nhầm. Nếu chỉ biết fetchedAt, ghi “Dữ liệu đã tải lúc 10:10”; nếu thật sự biết source watermark, có thể ghi “Dữ liệu đã đồng bộ đến…” theo phạm vi được chứng minh.

## 3. Nguồn phát sinh dữ liệu cũ trong truy vấn liên dịch vụ

### 3.1. Read replica

~~~text
Orders primary database
  -> replication bất đồng bộ
  -> read replica
  -> Order Query API
~~~

Ghi đã commit trên primary nhưng replica chưa nhận thay đổi. Nếu UI ghi rồi lập tức GET từ replica, có thể không thấy đơn mới. Với yêu cầu read-your-writes, có thể đọc trực tiếp primary trong thời gian nhất định hoặc dùng cơ chế session token có hỗ trợ từ database.

### 3.2. CQRS/read model

~~~text
Ordering transaction
  -> transactional outbox
  -> broker
  -> projection consumer
  -> query database
  -> API
  -> UI
~~~

Có thể trễ ở publisher, broker, partition nóng, consumer downtime, retry, database lock, backfill hay index update. API trả response trong 40 ms nhưng record lại trễ 8 giây.

### 3.3. Cache nhiều lớp

~~~text
Source -> read model -> service cache -> CDN -> browser cache -> UI
~~~

TTL 30 giây không có nghĩa data nguồn chỉ chậm tối đa 30 giây. Cache có thể vừa được làm mới từ read model đã trễ 60 giây. Phải đo end-to-end chứ không chỉ đo tuổi của cache entry.

### 3.4. Search index

Catalog thay sản phẩm thành inactive nhưng index tìm kiếm cập nhật muộn. Search vẫn hiển thị sản phẩm đã ẩn. Khi người dùng vào chi tiết hoặc đặt hàng, owner phải xác nhận trạng thái thực.

### 3.5. API composition

Trang tổng quan gọi Ordering, Payments và Shipping ở những thời điểm khác nhau. Mỗi response có thể mới nhất trong service của nó nhưng ghép lại không tạo một snapshot giao dịch nguyên tử toàn hệ thống. Điều này có thể là trạng thái trung gian hợp lệ hoặc sai lệch do event delay. UI cần phân biệt hai trường hợp theo domain state.

## 4. Dòng thời gian một thao tác đã thành công nhưng đọc vẫn cũ

Giả sử khách hủy đơn:

~~~text
10:00:00.000  Client gửi CancelOrder
10:00:00.080  Ordering commit CANCELLED, version=8
10:00:00.090  Ordering trả kết quả đã hủy, version=8
10:00:00.110  Outbox publisher bắt đầu gửi
10:00:00.200  Broker nhận OrderCancelled(version=8)
10:00:01.600  Projection consumer đọc event
10:00:02.320  Read model commit version=8
10:00:02.350  Query API trả version=8
~~~

Ở 10:00:00.300, GET read model có thể trả PROCESSING version=7. Response nhanh không làm nó đúng hơn. Theo ví dụ, **độ trễ lan truyền đến read model** là khoảng 2,24 giây. Trong khoảng này, UI đã có receipt version 8 từ owner nên không được chuyển ngược trạng thái hiển thị sang PROCESSING.

| Thời điểm | Owner | Read model | Cách diễn đạt UI |
| --- | --- | --- | --- |
| Trước cancel | PROCESSING v7 | PROCESSING v7 | “Đang xử lý” |
| Sau owner commit | CANCELLED v8 | PROCESSING v7 | “Đã hủy đơn; danh sách đang cập nhật” |
| Event chưa tới | CANCELLED v8 | PROCESSING v7 | Giữ receipt xác nhận; tiếp tục chờ |
| Projection bắt kịp | CANCELLED v8 | CANCELLED v8 | “Đã hủy” |
| Projection kẹt lâu | CANCELLED v8 | PROCESSING v7 | “Đã hủy nhưng chưa thể làm mới danh sách” |

Ví dụ này chỉ mô tả một command **hoàn tất ngay ở owner**. Nếu CancelOrder chỉ trả ACCEPTED rồi mới xử lý sau, không được hiển thị “Đã hủy”; phải nói “Đã nhận yêu cầu hủy, đang xử lý”.

## 5. Chọn mức nhất quán theo quyết định nghiệp vụ

Không nên gán cùng một freshness requirement cho mọi màn hình.

| Tình huống | Mức nhất quán/độ mới cần cân nhắc | Hướng UX |
| --- | --- | --- |
| Danh sách đơn gần đây | Có thể eventual, nhưng nên có read-your-writes | Hiển thị receipt sau thao tác, làm mới nền |
| Dashboard doanh thu | Cho phép cập nhật theo lô nếu công bố mốc | “Số liệu tính đến…” |
| Gợi ý sản phẩm | Có thể chấp nhận snapshot cũ | Không cần chặn UI |
| Tồn kho để tham khảo | Có thể ước tính | “Khả dụng sẽ được xác nhận khi đặt” |
| Tồn kho lúc giữ hàng | Quyết định authoritative tại Inventory | Nếu hết hàng thì từ chối rõ ràng |
| Giá lúc chốt đơn | Quote hợp lệ và owner xác nhận lại | Hiển thị thay đổi giá nếu quote hết hạn |
| Trạng thái thanh toán | Phải tra operation/payment owner khi trạng thái chưa rõ | Không tự khởi tạo charge mới |
| Số dư, hạn mức, phân quyền | Thường đòi bảo đảm chặt tại owner | Không quyết định từ cache không có kiểm chứng |
| Tracking vận chuyển | Chấp nhận update chậm từ đối tác | “Đối tác cập nhật lần cuối…” |

Sự chấp nhận stale cần được xác định **trên từng quyết định**. Ví dụ có thể hiển thị số tồn ước tính trong catalog, nhưng ReserveStock phải kiểm tra kho authoritative. Một service trả dữ liệu cũ cho mục đích tham khảo không được cho phép caller sử dụng dữ liệu đó như precondition giao dịch.

## 6. Read-your-writes: không để dữ liệu mới bị ghi đè bởi response cũ

Sau khi command commit, owner có thể trả resource và version:

~~~http
POST /orders/ord-1001/cancel
Idempotency-Key: cancel-ord-1001-attempt-1

HTTP/1.1 200 OK
Content-Type: application/json

{
  "orderId": "ord-1001",
  "status": "CANCELLED",
  "aggregateVersion": 8
}
~~~

Client lưu version tối thiểu đã biết: **8**. Lần GET sau có thể gửi minVersion:

~~~http
GET /orders/ord-1001?minVersion=8

HTTP/1.1 202 Accepted
Retry-After: 1
Content-Type: application/json

{
  "state": "PROJECTION_PENDING",
  "currentProjectionVersion": 7,
  "requiredVersion": 8
}
~~~

202 ở ví dụ là **lựa chọn hợp đồng minh họa**. Một thiết kế khác có thể dùng 200 với metadata pending, 409 có mã lỗi rõ hoặc route sang owner. Quan trọng là không trả v7 mà lại gọi nó FRESH so với yêu cầu v8, và không giữ HTTP connection chờ vô hạn.

### Cách thực hiện

1. Command response trả trạng thái xác nhận và aggregateVersion nếu đã commit.
2. UI cập nhật trạng thái trực tiếp từ response owner.
3. UI đặt minimumVisibleVersion cho aggregate trong session.
4. Query API trả snapshot đủ version hoặc một trạng thái pending rõ.
5. Client từ chối ghi đè state mới bằng snapshot version thấp hơn.
6. Khi read model đã đạt version yêu cầu, UI bỏ nhãn đồng bộ.

Không thể so version của Order với version Payment như một số đếm toàn cục. Mỗi token cần scope rõ: aggregateId, stream, tenant hoặc nguồn thích hợp. Với trang nhiều section, cần metadata theo section thay vì một version giả cho toàn trang.

### Monotonic reads

Ngoài read-your-writes, khi chuyển giữa replica A và B, có thể có response v10 rồi v8. Nếu trải nghiệm yêu cầu không lùi, giữ version watermark trong session và chỉ áp dụng response version phù hợp. Request đến sau không bảo đảm dữ liệu mới hơn nếu nó đọc replica chậm.

## 7. Các cách đạt trải nghiệm đọc sau ghi

**Cách A — Dùng write receipt:** Sau command hoàn tất, UI hiển thị kết quả owner trả và chờ read model hội tụ. Ít thêm tải, dễ triển khai. Không được áp dụng khi command mới accepted.

**Cách B — Chờ projection đạt minVersion:** Query service có bounded wait, ví dụ không quá một ngưỡng nhỏ, rồi trả pending khi chưa đạt. Cần hạn thời gian và kiểm soát concurrent requests.

**Cách C — Fallback đọc owner:** Khi projection chậm và dữ liệu có rủi ro cao, truy vấn nguồn authoritative. Tăng độ tin cậy nhưng có thể làm owner quá tải hoặc tăng runtime coupling; nên có rate limiting, timeout và circuit breaker.

**Cách D — Session affinity/causal token:** Dùng khả năng của database hoặc hệ thống lưu trữ để đọc từ replica đã bắt kịp write token. Cần kiểm tra hỗ trợ thực tế, không suy ra từ việc có load balancer.

**Cách E — Optimistic UI có rollback:** UI cập nhật tạm trước khi server xác nhận. Phù hợp thay đổi ít rủi ro như chỉnh draft. Nếu bị reject, rollback và thông báo. Với thanh toán/hoàn tiền/hủy không thể đảo ngược, thường không nên tự gọi optimistic state là completed.

Có thể kết hợp các cách. Lựa chọn phải dựa trên tính đúng đắn, latency, tải, UX và chi phí vận hành.

## 8. API nên trả thông tin freshness trung thực

Một response có thể tách dữ liệu và metadata:

~~~json
{
  "data": {
    "orderId": "ord-1001",
    "status": "PROCESSING"
  },
  "consistency": {
    "source": "order-read-model",
    "aggregateVersion": 7,
    "sourceOccurredAt": "2026-11-11T09:59:57Z",
    "projectedAt": "2026-11-11T10:00:01Z",
    "fetchedAt": "2026-11-11T10:00:02Z",
    "freshnessStatus": "UNKNOWN"
  }
}
~~~

Vì sao freshnessStatus là UNKNOWN? Query API biết phiên bản mà read model đã áp dụng, **không mặc nhiên biết owner có version 8 hoặc 9 chưa được publish**. Nó không thể cam kết snapshot đã mới nhất chỉ vì projectedAt gần đây.

Các field nên cân nhắc:

- **aggregateVersion:** version của entity/aggregate từ owner đã phản ánh.
- **sourceOccurredAt:** lúc business fact được ghi nhận theo nguồn.
- **projectedAt:** lúc consumer commit projection tương ứng.
- **fetchedAt:** lúc API lấy snapshot để trả.
- **sourceWatermark:** tiến độ nguồn đã được chứng minh trong một phạm vi rõ.
- **minimumRequiredVersion:** mức caller cần sau thao tác ghi.
- **freshnessStatus:** FRESH/STALE/UNKNOWN theo tiêu chí cụ thể.
- **warningCode:** PROJECTION_PENDING, SOURCE_UNAVAILABLE, PARTIAL_DATA, v.v.
- **pendingOperationId:** nhận diện một workflow đang chờ, không phải bằng chứng hoàn tất.

Không nhất thiết đưa tất cả vào public API. Thiết kế hợp đồng tối thiểu có thể diễn giải được, tránh lộ topology nội bộ hoặc dữ liệu nhạy cảm. Nếu chỉ biết thời điểm tải, dùng nhãn fetchedAt chứ không gọi là latestSourceUpdatedAt.

## 9. Timestamp không thay thế watermark

Nhận event có occurredAt = 10:02 không chứng minh mọi event đến 10:02 đã được xử lý. Có thể còn event 10:01 nằm trên partition khác hoặc outbox của producer chưa publish. Clock giữa các service cũng có thể lệch.

Với event-driven projection, nên lưu một version/sequence theo aggregate:

~~~text
OrderPlaced(orderId=1001, version=1)
OrderConfirmed(orderId=1001, version=2)
OrderCancelled(orderId=1001, version=3)
~~~

Read model:

~~~text
order_id = 1001
status = CANCELLED
last_applied_aggregate_version = 3
projected_at = 10:00:02
~~~

Nếu client có write receipt v3, snapshot v3 thỏa read-your-writes cho aggregate này. Nhưng v3 **không chứng minh** không có v4 ở owner. Với Kafka, offset là vị trí trong một partition và không cho một thứ tự toàn cục trên nhiều partition. Nếu dùng watermark qua nhiều partition, phải định nghĩa rõ phạm vi và cách xử lý message đang in-flight, event bị DLT hoặc replay.

### Những sai lầm về watermark

- Offset consumer commit tiến lên trước khi projection DB commit.
- Lấy offset lớn nhất dù còn record nhỏ hơn đang xử lý bất đồng bộ.
- Coi broker lag=0 nghĩa không có thay đổi nào đang nằm trong outbox.
- Dùng timestamp của event mới nhất như bằng chứng mọi event trước đó đã đến.
- Cộng offset của nhiều partition và diễn giải như một global version.
- So version của Order và Payment vốn thuộc hai miền khác nhau.
- Bỏ qua event bị lỗi vào DLQ mà vẫn đánh dấu read model “đầy đủ”.

Watermark đáng tin cậy là một **bảo đảm có giới hạn được mô tả rõ**, không chỉ một con số trong response.

## 10. Thiết kế sáu trạng thái giao diện

| UI state | Backend đã biết | Thông báo gợi ý |
| --- | --- | --- |
| LOADING | Chưa có dữ liệu để hiển thị | “Đang tải thông tin…” |
| FRESH | Snapshot thỏa tiêu chí freshness được kiểm chứng | Hiển thị thông thường hoặc “Đã cập nhật” |
| STALE_USABLE | Có snapshot cũ nhưng vẫn dùng được cho tác vụ tham khảo | “Thông tin có thể chưa mới. Đang làm mới…” |
| PENDING_WRITE | Command accepted nhưng chưa hoàn tất | “Đã nhận yêu cầu. Đang xử lý…” |
| CONFIRMED_BUT_PROJECTING | Owner đã xác nhận, projection chưa hội tụ | “Thao tác đã thành công. Danh sách đang cập nhật…” |
| UNKNOWN_OR_ERROR | Không tải/không xác minh được trạng thái | “Chưa thể kiểm tra thông tin mới nhất. Thử lại.” |

Với trang nhiều section còn cần PARTIAL: “Thông tin đơn hàng đã có, nhưng vận chuyển đang tạm gián đoạn.” Không thay một phần bị lỗi bằng giá trị mặc định như payment=UNPAID, revenue=0 hoặc inventory=0, vì **không có dữ liệu** khác với **dữ liệu có giá trị bằng không**.

### Mẫu câu rõ ràng

- “Đã nhận yêu cầu hủy đơn. Chúng tôi đang xử lý.”
- “Đã hủy đơn. Thông tin ở danh sách có thể cập nhật chậm.”
- “Thanh toán đang được xác minh. Vui lòng không thanh toán lại.”
- “Số liệu doanh thu tính đến 09:55; trang tải lúc 10:01.”
- “Thông tin vận chuyển được đối tác cập nhật lần cuối lúc 09:40.”
- “Không thể xác minh tồn kho hiện tại; chúng tôi sẽ kiểm tra lại trước khi xác nhận đơn.”

Những câu sau dễ gây hiểu nhầm:

- “Thanh toán thành công” khi provider mới trả ACCEPTED.
- “Thanh toán thất bại” vì read model còn PENDING.
- “Cập nhật realtime” khi pipeline analytics có độ trễ vài phút.
- “Không tìm thấy đơn” ngay sau 201 Created từ owner nhưng projection chưa được tạo.
- “Giá chắc chắn còn hiệu lực” chỉ vì catalog cache chưa hết TTL.

UX phải nói được **người dùng nên làm gì**, đặc biệt khi thao tác tiếp theo có thể gây tác động tài chính.

## 11. Phân biệt loading, refreshing và stale

Một trang có dữ liệu cached có thể hiện snapshot ngay rồi làm mới nền (stale-while-revalidate):

~~~text
1. Client có OrderList cũ trong cache.
2. Mở trang: render list với nhãn “Đang làm mới”.
3. Request tới Order Query API.
4. Nếu có response đủ mới, cập nhật list và bỏ nhãn.
5. Nếu network lỗi, giữ snapshot cũ nếu an toàn, hiển thị warning.
6. Nếu có write receipt version mới, không cho snapshot cũ ghi đè.
~~~

Trải nghiệm này hợp với danh sách sản phẩm, lịch sử, dashboard không quyết định giao dịch. Nó không cho phép frontend chốt payment hay cấp quyền dựa trên cache.

**TTL** là thời gian giữ entry, không phải freshness guarantee. Nếu cache vừa lấy từ projection chậm, cache age gần 0 nhưng nội dung có thể vẫn cũ. Nên đo freshness end-to-end và có version-aware update.

### Khi nào không nên hiển thị stale data?

- Quyết định mức tiền được capture/refund.
- Cấp, thu hồi hoặc kiểm tra quyền truy cập quan trọng.
- Đặt chỗ, giữ hàng, duyệt giao dịch ở trạng thái cạnh tranh.
- Thực hiện thao tác không thể đảo ngược dựa trên trạng thái chưa rõ.
- Hiển thị dữ liệu của tenant/user khác do cache key sai.

Trong những trường hợp ấy, nếu owner unavailable, nên chặn hoặc chuyển sang trạng thái không thể xác minh, không âm thầm dùng bản cũ.

## 12. Tránh UI bị “lùi” khi response đến ngược thứ tự

Tình huống:

~~~text
t0: GET A bắt đầu, đọc version 7
t1: người dùng gửi CancelOrder
t2: owner commit và trả CANCELLED version 8
t3: UI hiển thị “Đã hủy” version 8
t4: GET A trả PROCESSING version 7
t5: nếu frontend áp dụng response cũ, UI quay về PROCESSING
~~~

Để tránh:

- Giữ minimumVisibleVersion theo aggregate trong phiên.
- Chỉ chấp nhận snapshot có version không thấp hơn version đã hiển thị.
- Khi response cũ, bỏ qua hoặc hiển thị cảnh báo projection đang chậm.
- Với thao tác optimistic, lưu trạng thái pending/confirmed riêng, không chỉ một cờ status.
- Với request search/filter, có request sequence ID hoặc AbortController để bỏ response không còn phù hợp.

Mã giả:

~~~javascript
const versions = new Map();

function renderSnapshotIfCurrent(snapshot) {
  const key = snapshot.orderId;
  const floor = versions.get(key) ?? -1;

  if (snapshot.aggregateVersion < floor) {
    return { applied: false, reason: "STALE_RESPONSE" };
  }

  versions.set(key, snapshot.aggregateVersion);
  renderOrder(snapshot);
  return { applied: true };
}

function onCancelConfirmed(receipt) {
  const current = versions.get(receipt.orderId) ?? -1;
  versions.set(receipt.orderId, Math.max(current, receipt.aggregateVersion));
  renderOrderStatus(receipt.orderId, "CANCELLED");
}
~~~

Mã chỉ minh họa. Một API tổng hợp nhiều aggregate không có một version toàn cục, nên cần version/provenance theo trường hoặc section. Request chạy sau chưa chắc đọc dữ liệu mới hơn khi được route đến replica chậm; request sequence ID giúp tránh response lệch thứ tự nhưng không thay thế source version.

## 13. Ví dụ Java: query response có metadata

Một API có thể định nghĩa tách biệt dữ liệu và freshness:

~~~java
import java.time.Instant;

public record FreshnessMetadata(
    String source,
    Long aggregateVersion,
    Instant sourceOccurredAt,
    Instant projectedAt,
    Instant fetchedAt,
    String status
) {}

public record OrderView(
    String orderId,
    String status,
    long totalMinor,
    String currency
) {}

public record OrderQueryResponse(
    OrderView order,
    FreshnessMetadata consistency
) {}
~~~

Query service nhận minVersion:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderQueryController {
    private final OrderProjectionRepository repository;

    public OrderQueryController(OrderProjectionRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getOrder(
            @PathVariable String id,
            @RequestParam(required = false) Long minVersion) {

        OrderProjection p = repository.findByOrderId(id);

        if (p == null) {
            // Cần xử lý riêng trạng thái 404 sau write receipt:
            // có thể là pending projection thay vì không tồn tại thật.
            return ResponseEntity.notFound().build();
        }

        if (minVersion != null && p.version() < minVersion) {
            return ResponseEntity.status(202)
                .body(Map.of(
                    "state", "PROJECTION_PENDING",
                    "currentVersion", p.version(),
                    "requiredVersion", minVersion
                ));
        }

        var view = new OrderView(
            p.orderId(), p.status(), p.totalMinor(), p.currency());

        var freshness = new FreshnessMetadata(
            "order-read-model",
            p.version(),
            p.sourceOccurredAt(),
            p.projectedAt(),
            Instant.now(),
            "UNKNOWN"
        );

        return ResponseEntity.ok(new OrderQueryResponse(view, freshness));
    }
}
~~~

Cần thêm import các type Spring và Map; Repository/Projection là interface/model do ứng dụng cung cấp. Đoạn mã chưa xử lý auth/tenant, cache, bounded wait, negative caching hay lỗi owner. Đây là ví dụ ý tưởng, không phải dịch vụ hoàn chỉnh.

Điểm quan trọng: controller trả UNKNOWN vì chỉ có snapshot cục bộ. Nếu nhận minVersion=8 và có p.version()=8, có thể xác nhận yêu cầu **đủ phiên bản tối thiểu**; vẫn không tự tuyên bố đây là version mới nhất tuyệt đối.

## 14. Command bất đồng bộ: accepted khác completed

Một CancelOrder dài có thể trả:

~~~http
POST /orders/ord-1001/cancel

HTTP/1.1 202 Accepted
Location: /operations/op-cancel-1001

{
  "operationId": "op-cancel-1001",
  "status": "ACCEPTED"
}
~~~

Trong UI, “Đã nhận yêu cầu hủy” là chính xác; “Đã hủy đơn” là quá sớm. Client tra status của operation (polling, SSE, WebSocket hoặc webhook phù hợp) cho đến khi COMPLETED/REJECTED/FAILED theo owner.

Khi owner xác nhận COMPLETED nhưng read model chưa bắt kịp, UI có thêm trạng thái CONFIRMED_BUT_PROJECTING. Khi read model hội tụ, mới bỏ cảnh báo đồng bộ. Nếu owner chưa rõ kết quả do network timeout, cần tra operationId/idempotency key trước khi gửi lại.

### Tránh thao tác thanh toán trùng

Payment request timeout có thể xảy ra sau khi gateway đã capture tiền. Nếu read model vẫn hiển thị PENDING, UI phải nói “Đang xác minh” và tra Payment operation authoritative. Không tự mở một payment operation mới chỉ vì response HTTP bị mất. Idempotency key phải ổn định theo business operation; reconciliation cần xử lý trạng thái mơ hồ.

## 15. Trang tổng hợp có độ mới khác nhau theo từng phần

Một trang đơn hàng có thể dùng:

- Order status từ Ordering projection.
- Payment status từ Payments authoritative API.
- Shipment tracking từ Shipping cache.
- Product recommendations từ recommendation model.

Không nên đặt một nhãn “Đã cập nhật lúc 10:00” cho toàn trang khi mỗi phần có thời điểm khác nhau.

Ví dụ response:

~~~json
{
  "orderId": "ord-1001",
  "sections": {
    "order": {
      "data": {"status": "CONFIRMED"},
      "source": "ordering-projection",
      "aggregateVersion": 8
    },
    "payment": {
      "data": {"status": "CAPTURED"},
      "source": "payments",
      "fetchedAt": "2026-11-11T10:01:00Z"
    },
    "shipment": {
      "data": null,
      "warningCode": "UPSTREAM_UNAVAILABLE"
    }
  }
}
~~~

Trên UI: “Đơn đã xác nhận”, “Thanh toán thành công”, “Thông tin vận chuyển tạm chưa truy cập được”. Không thay shipment=null bằng “Chưa giao” vì đó là hai nghĩa khác nhau.

Nếu hệ thống thiếu một phần không quan trọng, có thể hiển thị phần còn lại. Nếu thiếu dữ liệu làm điều kiện bắt buộc để xác nhận thanh toán/giao hàng, không được giả định mặc định thuận lợi chỉ để trang hiển thị đầy đủ.

## 16. 404 từ projection không chắc bản ghi chưa tồn tại

Một tình huống:

~~~text
POST /orders -> owner trả 201 Created, orderId=1001
GET /orders/1001 -> read model trả 404
~~~

Điều này có thể xảy ra khi event tạo bản ghi chưa được áp dụng vào projection. 404 từ read model khi client đã có write receipt khác với 404 từ owner authoritative.

Thiết kế:

1. Nếu client có receipt xác nhận tạo Order và minVersion, xem 404 trong cửa sổ hợp lý là PROJECTION_PENDING.
2. Hiển thị “Đơn đã được tạo; đang cập nhật trang chi tiết”.
3. Poll có backoff/timeout hoặc fallback owner khi hết deadline.
4. Nếu sau đó owner xác nhận không có bản ghi, xử lý sự cố/nhất quán theo policy.
5. Không giữ 404 trong negative cache quá lâu mà không có invalidation.
6. Nếu client không có receipt, 404 vẫn có thể là kết quả hợp lệ; đừng mặc định tất cả 404 đều pending.

Ngoài eventual consistency, 404 có thể do sai quyền, sai tenant/region hoặc resource thực sự bị xóa. Không được để cơ chế fallback làm lộ dữ liệu của user khác.

## 17. Cache invalidation, ETag và stale-while-revalidate

Công cụ phổ biến:

**TTL:** giới hạn tuổi cache entry, không giới hạn source staleness.

**Event invalidation:** khi có OrderUpdated, xóa hoặc làm mới cache liên quan. Event có thể đến chậm nên cần retry, outbox và theo dõi.

**ETag/If-None-Match:** hỗ trợ revalidation và tiết kiệm băng thông. 304 Not Modified có nghĩa representation vẫn khớp validator theo nguồn được hỏi, không chứng minh mọi upstream đã hội tụ.

**Stale-while-revalidate:** trả snapshot cũ ngay rồi refresh nền. Cần nhãn hoặc trạng thái rõ, không áp dụng cho quyết định high-stakes khi không có recheck authoritative.

**Version-aware cache:** không để một update snapshot v7 ghi đè cache v8. Có thể dùng conditional write/compare-and-set theo version.

**Negative caching:** 404/empty result cần thời hạn ngắn hoặc invalidation phù hợp, đặc biệt với resource vừa tạo.

**Security-aware cache key:** xét tenant, user, role, locale, currency và policy. Không dùng một cache key chung cho dữ liệu cá nhân hoặc quyền riêng biệt.

**Backpressure và stampede control:** nhiều client cùng refresh khi TTL hết có thể làm owner quá tải. Dùng jitter, single-flight hoặc rate limit thích hợp.

## 18. Dữ liệu cũ và xung đột khi sửa form

Nếu user mở form từ version 7, một người khác lưu version 8, sau đó user submit bản v7 có thể ghi đè dữ liệu mới. Đây là **lost update**, nghiêm trọng hơn việc hiển thị chậm.

Có thể dùng optimistic concurrency với ETag/If-Match:

~~~http
GET /profiles/customer-71

HTTP/1.1 200 OK
ETag: "profile-v7"

{
  "customerId": "customer-71",
  "displayName": "An"
}
~~~

Lúc gửi chỉnh sửa:

~~~http
PATCH /profiles/customer-71
If-Match: "profile-v7"

{
  "displayName": "An Nguyễn"
}
~~~

Nếu owner đã lên v8:

~~~http
HTTP/1.1 412 Precondition Failed

{
  "code": "VERSION_CONFLICT",
  "message": "Thông tin đã thay đổi. Hãy tải dữ liệu mới."
}
~~~

UI nên gợi ý tải bản mới và so sánh trước khi lưu. Không tự retry toàn bộ form cũ bằng cách bỏ If-Match, vì có thể ghi đè thay đổi hợp lệ. ETag phải do owner có quyền ghi kiểm tra, không chỉ do một read model stale ước lượng.

## 19. Truy vấn tìm kiếm, sort và pagination

Kết quả search index có thể trễ so với owner. Một sản phẩm đã ẩn vẫn có thể xuất hiện trong danh sách; khi vào chi tiết, owner có thể trả 404/410 hoặc không khả dụng. UI nên nói “Mục này vừa thay đổi hoặc không còn khả dụng” và có đường trở về kết quả, thay vì coi hệ thống hỏng.

Pagination cũng chịu ảnh hưởng thay đổi đồng thời:

- Trang 1 được đọc trước một insert mới.
- Trang 2 được đọc sau insert, offset thay đổi.
- Item có thể bị lặp hoặc bỏ sót.

Cursor pagination gắn với snapshot/version có thể tăng tính ổn định, nhưng phải định nghĩa cụ thể snapshot semantics. Nếu sắp theo updatedAt từ nhiều service, clock skew và event delay có thể làm thứ tự không như người dùng mong đợi. Không xem timestamp đơn thuần là phiên bản có thứ tự tuyệt đối.

## 20. Đo độ trễ cập nhật end-to-end

Để đo, ghi các mốc với ID tương quan:

~~~text
t_commit   : owner commit business state
t_outbox   : publisher lấy event từ outbox
t_broker   : broker chấp nhận message
t_consume  : consumer nhận message
t_apply    : projection DB commit state mới
t_visible  : query API có thể trả version mới
t_render   : UI hiển thị trạng thái hội tụ
~~~

Độ trễ có thể tách:

- Publish delay = t_broker - t_commit.
- Queueing delay = t_consume - t_broker.
- Processing delay = t_apply - t_consume.
- Projection propagation = t_apply - t_commit.
- Query visibility lag = t_visible - t_commit.
- User-perceived lag = t_render - thời điểm người dùng nhận xác nhận.

Các timestamp từ nhiều máy chịu clock skew. Dùng tracing, đồng bộ đồng hồ phù hợp và các marker version/offset khi cần. Không coi chênh lệch timestamp chưa được chuẩn hóa là số đo tuyệt đối.

### Metric gợi ý

| Metric | Trả lời điều gì? |
| --- | --- |
| projection_delay_seconds p50/p95/p99 | Event mất bao lâu để xuất hiện ở projection? |
| outbox_oldest_pending_age | Có đang kẹt trước broker? |
| consumer_lag / queue_depth | Consumer có bắt kịp broker không? |
| projection_apply_errors | Có lỗi deserialize, transaction, schema không? |
| dlq_count / dlq_oldest_age | Có message không xử lý được lâu không? |
| stale_response_ratio | Có bao nhiêu request vượt freshness policy? |
| min_version_pending_ratio | Có bao nhiêu read-your-writes request phải chờ? |
| read_your_writes_violations | Có response thấp hơn version vừa xác nhận không? |
| reconciliation_backlog | Bao nhiêu entity đang sai lệch cần khôi phục? |
| api_query_latency p95/p99 | Query nhanh hay chậm? |
| business_completion_delay | Người dùng chờ workflow kết thúc bao lâu? |

Không dùng business ID như orderId làm label cho metric cardinality cao. Dùng trace/log có ID chi tiết, metric chia theo service, event type, environment, region trong giới hạn có kiểm soát.

## 21. SLI/SLO về độ mới

Một SLI:

~~~text
freshness_success_ratio =
  số thay đổi được phản ánh tại Order Query API trong 5 giây
  / tổng số thay đổi hợp lệ đã commit tại Ordering
~~~

Một SLO **minh họa**, không phải mức chuẩn: “99,5% thay đổi Order xuất hiện trong read model trong 5 giây ở điều kiện vận hành đã định”. Cần nói rõ cửa sổ tính toán, trường hợp bảo trì, các source quan sát, cách xử lý event thất bại và phép đo.

Sử dụng p95/p99, không chỉ average. Một pipeline trung bình 300 ms vẫn có thể khiến 1% người dùng chờ hơn 1 phút. Cần cân nhắc mức độ nghiêm trọng theo business operation và khả năng fallback.

Khi SLO vi phạm:

- Theo dõi outbox, broker, consumer, database, cache để xác định tầng chậm.
- Bật cảnh báo hoặc degraded UI nếu dữ liệu được phép hiển thị cũ.
- Với payment/authorization, chuyển sang trạng thái “Không thể xác minh” và tra owner thay vì đoán.
- Hạn chế số lượng fallback calls để không gây outage dây chuyền.
- Có runbook, owner xử lý và cách xác định đã phục hồi từ metric thật.

Một SLO chỉ có giá trị nếu đo end-to-end; consumer lag=0 không chứng minh publisher đã gửi hết event từ outbox.

## 22. Consumer lag và watermark không đồng nghĩa dữ liệu mới

Trong Kafka, offset lag cho biết group chậm so với record broker đang có theo partition. Nhưng có thể:

1. Outbox producer còn nhiều record chưa publish, broker chưa có gì để consumer tụt.
2. Consumer commit offset trước khi projection transaction hoàn tất.
3. Event của một aggregate nằm trên nhiều partition hoặc key đã đổi.
4. Consumer bỏ qua lỗi và đưa record vào DLT, nhưng offset vẫn tiến.
5. Replay event cũ khiến timestamp mới nhất không phản ánh trạng thái.
6. Một business event đến muộn, occurredAt nhỏ hơn event vừa xử lý.

Vì vậy, projection nên ghi lastAppliedAggregateVersion/sequence hoặc watermark có ngữ nghĩa cụ thể **cùng transaction áp dụng projection**. Đừng suy ra “đã xử lý tất cả” chỉ vì số lag từ broker hiện là 0.

### Reconciliation

Nếu event có thể bị thiếu hoặc projection không tin tiến độ, cần reconciliation job so sánh source authoritative với read model theo entity/version/partition và sửa sai lệch. Khi phải rebuild projection, cần nguồn replay còn dữ liệu: event log retention đủ dài, snapshot + change feed hoặc backfill từ owner. Không mặc định broker lưu mọi event mãi mãi.

## 23. Polling, SSE và WebSocket

Cập nhật UI có các lựa chọn:

| Cơ chế | Phù hợp | Điều cần xử lý |
| --- | --- | --- |
| Polling | Theo dõi operation vài giây/phút | Backoff, Retry-After, giới hạn thời gian |
| Server-Sent Events | Đẩy trạng thái một chiều từ server | Reconnect, Last-Event-ID, auth, timeout proxy |
| WebSocket | Tương tác hai chiều/cập nhật liên tục | Reconnect, ordering, backpressure, session |
| Manual refresh | Báo cáo ít thay đổi | Nhãn freshness và trạng thái lỗi rõ |
| Push/mobile notification | Quy trình dài khi user đã rời trang | Thông báo không mặc định giao đúng một lần |

Một push event “OrderUpdated” **có thể đến trước khi query projection bắt kịp**. Nếu client GET ngay và thấy dữ liệu cũ, có thể dùng minVersion đi cùng event, chờ projection đạt mốc hoặc tra owner ở những tác vụ quan trọng.

### Polling an toàn

1. Truy vấn theo operationId ổn định; **không gửi lại command mới** trên mỗi lần poll.
2. Backoff có jitter để tránh hàng nghìn client đồng loạt poll.
3. Dừng khi operation có trạng thái cuối theo hợp đồng.
4. Có deadline và fallback UX: “Chưa thể xác minh kết quả. Thử lại hoặc liên hệ hỗ trợ.”
5. Giảm/dừng polling khi tab nền nếu phù hợp và không mất khả năng hoàn tất.
6. Khi quay lại, đọc trạng thái từ owner trước khi tiếp tục hành động nguy hiểm.

Đổi công nghệ polling sang SSE không tự làm read model nhất quán mạnh hơn; nó chỉ đổi cách thông báo tới client.

## 24. Mẫu giao diện theo tình huống

### 24.1. Lịch sử đơn

~~~text
Đơn hàng của tôi

[Thông tin có thể cập nhật chậm.]
Đã tải lần gần nhất: 10:01.    [Làm mới]

#1001    Đang xử lý
         Đơn đã được xác nhận hủy; danh sách đang đồng bộ.
#1002    Đã giao
#1003    Đang hoàn tiền
~~~

Đơn #1001 vẫn có dòng trong projection version cũ nhưng receipt owner xác nhận version mới. UI nên ưu tiên confirmation vừa nhận và giải thích list đang chậm thay vì hoán đổi trạng thái gây hoang mang.

### 24.2. Thanh toán

~~~text
Thanh toán đơn #1001

Đang xác minh trạng thái thanh toán.
Vui lòng không thanh toán lại trong lúc kiểm tra.

[Kiểm tra lại trạng thái]  [Liên hệ hỗ trợ]
~~~

Khi Payments đã có kết quả CAPTURED, UI hiển thị thành công từ owner; không đợi Analytics/Order projection bắt kịp mới coi là thanh toán thành công. Khi chưa biết owner có commit hay không, không tự hiển thị thành công hay thất bại.

### 24.3. Dashboard

~~~text
Doanh thu hôm nay
159.900.000 ₫

Số liệu tổng hợp đến 09:55.
Trang tải dữ liệu lúc 10:01.
[Làm mới]
~~~

Nếu chưa có source watermark đáng tin, không ghi “tổng hợp đến 09:55” bằng timestamp của bản ghi mới nhất một cách tùy tiện. Chỉ hiển thị thời gian mà pipeline có thể chứng minh hoặc ghi một câu yếu hơn.

### 24.4. Tồn kho

~~~text
Sản phẩm A100
Tình trạng: Còn hàng (thông tin tham khảo)
Hệ thống sẽ kiểm tra khả dụng khi xác nhận đặt hàng.

[Thêm vào giỏ]
~~~

Quyết định ReserveStock thực sự phải được Inventory xử lý với invariant và kiểm soát đồng thời. Số tồn trên trang danh mục có thể dùng để định hướng, không phải cam kết giữ hàng.

## 25. Xử lý partial failure trong API composition

Một trang tổng hợp phụ thuộc ba service. Nếu Shipping timeout nhưng Ordering/Payments trả thành công, response có thể trả phần có dữ liệu và warning:

~~~json
{
  "orderId": "ord-1001",
  "data": {
    "orderStatus": "CONFIRMED",
    "paymentStatus": "CAPTURED",
    "shipmentStatus": null
  },
  "warnings": [
    {
      "section": "shipment",
      "code": "UPSTREAM_UNAVAILABLE",
      "message": "Không thể tải trạng thái vận chuyển."
    }
  ]
}
~~~

UI không được biến shipmentStatus=null thành NOT_SHIPPED và nói đơn chưa giao. Null do lỗi khác với trạng thái nghiệp vụ xác nhận chưa vận chuyển. Nếu payment data lỗi, cũng không được đổi thành UNPAID hoặc 0.

Khi nhiều section có phiên bản khác nhau, nên gắn source, fetchedAt và sourceVersion theo section quan trọng. Một “lastUpdated” chung cho toàn trang có thể làm người dùng hiểu sai.

## 26. Các lỗi thiết kế thường gặp

**Lỗi 1 — HTTP 200 đồng nghĩa “dữ liệu mới nhất”.** Query có thể phục vụ từ replica/cache. Cần freshness contract và sourceVersion khi cần.

**Lỗi 2 — Dùng fetchedAt làm mốc nguồn.** Ghi “Cập nhật 10:10” dù snapshot từ 10:02. Cần phân biệt thời điểm tải và thời điểm source.

**Lỗi 3 — Chỉ nhìn consumer lag.** Consumer lag=0 nhưng outbox chưa publish. Đo end-to-end propagation và source watermark.

**Lỗi 4 — GET cũ ghi đè receipt mới.** UI vừa hiển thị Cancelled v8 rồi trả về Processing v7. Giữ minimumVisibleVersion và bỏ response stale.

**Lỗi 5 — Timeout nghĩa command thất bại.** Gateway có thể đã commit nhưng response mất. Dùng idempotency key/operation status và reconciliation.

**Lỗi 6 — Trả 404 từ projection ngay sau 201.** Resource đã có ở owner nhưng bản sao chưa tạo. Dùng write receipt, pending state và fallback.

**Lỗi 7 — Giá trị mặc định biến unknown thành false/zero.** Payment source unavailable nhưng UI hiển thị UNPAID. Dùng trạng thái UNKNOWN và cảnh báo.

**Lỗi 8 — TTL cực ngắn được xem là giải pháp mọi thứ.** Tăng tải owner mà không sửa consumer lag. Cần version, invalidation và đo chuỗi.

**Lỗi 9 — Không giữ trạng thái trung gian.** Một command accepted bị UI gọi là completed. Xây state machine pending/confirmed/rejected.

**Lỗi 10 — Spinner vô hạn.** User không biết chuyện gì xảy ra. Có deadline, Retry-After/backoff, đường tra cứu và hỗ trợ.

**Lỗi 11 — Một freshness label cho mọi section.** Order và shipment không có cùng nguồn. Dùng provenance theo section.

**Lỗi 12 — Bảo mật cache sai.** Dữ liệu cũ của user/tenant khác xuất hiện sau chuyển phiên. Cache key và invalidation phải theo quyền.

**Lỗi 13 — Tự retry tác vụ tài chính bằng operation mới.** Độ cũ làm người dùng bị thu tiền hai lần. Kiểm tra owner và dùng idempotency.

**Lỗi 14 — Xử lý event đến sai thứ tự nhưng không so version.** Projection có thể lùi trạng thái. Dùng aggregateVersion và handler idempotent.

**Lỗi 15 — Dùng source timestamp như total ordering.** Clock khác nhau và event có thể đến muộn. Cần sequence/watermark với semantics phù hợp.

## 27. Kiểm thử tình huống dữ liệu cũ

### Unit/contract tests

- Query response có metadata version/timestamp nhất quán.
- minVersion cao hơn projection trả pending chứ không gán FRESH.
- Unknown source freshness không được tự động đổi thành FRESH.
- Consumer duplicate eventId không áp dụng side effect lần hai.
- Event version thấp hơn không ghi đè projection version cao.
- Command API phân biệt ACCEPTED với COMPLETED.
- Field không lấy được từ upstream được biểu diễn missing/warning chứ không dùng giá trị giả.

### Integration tests

- Owner commit xong, outbox delay: UI không hiểu nhầm command thất bại.
- Broker redelivery sau consumer DB commit: projection không tăng/giảm sai.
- Query ở read replica lag 10 giây: minVersion hoặc fallback hoạt động.
- Client nhận response v7 sau receipt v8: giao diện không lùi trạng thái.
- Event push đến trước projection apply: client chờ đúng minVersion.
- Payment timeout sau capture: retry không tạo charge mới.
- Projection trả 404 ngay sau tạo Order: UI hiển thị pending.
- Cache chứa 404 trước khi record xuất hiện: invalidation/TTL xử lý đúng.
- Shipping API timeout: trang vẫn hiển thị Order và Payment với warning.

### UX/chaos tests

- Người dùng thấy nhãn “Đang làm mới” khi dữ liệu cache hiển thị.
- Nếu có kết quả authoritative, màn hình không quay về trạng thái cũ.
- Khi SLO vượt giới hạn, warning xuất hiện; sau phục hồi warning biến mất theo metric.
- Spinner kết thúc hoặc chuyển sang trạng thái có thể thao tác tiếp.
- Nút “Thử lại” truy vấn status, không tạo command mới.
- Screen reader nhận biết trạng thái quan trọng mà không bị spam mỗi lần poll.
- Consumer ngừng 30 giây rồi phục hồi: projection hội tụ, backlog giảm, UI hết stale.
- Broker outage và outbox backlog: dashboard phân biệt nơi bị kẹt.

## 28. Bài tập: trang chi tiết đơn với thanh toán bất đồng bộ

Hệ thống có:

- Ordering sở hữu trạng thái Order.
- Payments sở hữu payment operation.
- Shipping sở hữu shipment.
- Order Query Service dựng projection từ event.
- PaymentCaptured đôi khi mất 6–10 giây để hiện trong projection.
- Khi consumer bị lỗi schema, lag có thể tăng vài phút.

Yêu cầu:

1. UI hiển thị đúng khi Payments xác nhận CAPTURED.
2. Không tạo charge thứ hai do projection còn PENDING.
3. Danh sách đơn có thể chậm nhưng có nhãn và hành động làm mới.
4. Khi projection chậm quá SLO, có trạng thái degraded và đường tra owner.
5. Những phần không có dữ liệu được phân biệt rõ với trạng thái business negative.
6. Vận hành biết lỗi nằm ở outbox, broker, consumer, DB hay cache.

Hướng giải:

**Bước 1 — Xác định owner.** Payments quyết định CAPTURED, Ordering quyết định Order status, Shipping quyết định shipment status.

**Bước 2 — Write receipt.** Payments trả paymentId, operationId, trạng thái và version có phạm vi rõ khi đã hoàn tất; UI lưu receipt.

**Bước 3 — Query contract.** Read model trả order snapshot và metadata; payment section có provenance riêng. Nếu projection chưa đạt expectedVersion, API trả pending.

**Bước 4 — UI.** Hiển thị “Thanh toán đã thành công. Thông tin đơn hàng đang cập nhật”, không hiển thị nút thanh toán mới.

**Bước 5 — SLO.** Đặt mục tiêu độ trễ propagation dựa trên product requirement và đo bằng end-to-end tracing. Ví dụ 99% cập nhật trong 10 giây, nhưng phải kiểm chứng số liệu.

**Bước 6 — Degraded mode.** Nếu quá deadline, tra Payments authoritative có rate limit và cảnh báo. Nếu source cũng unavailable, nói chưa thể xác minh và cung cấp đường hỗ trợ.

**Bước 7 — Thử lỗi.** Delay outbox, consumer crash, duplicate event, response sai thứ tự và payment timeout. Xác nhận UI không lùi state và không double charge.

~~~text
Payments authoritative CAPTURED
     |--------------------> UI biết kết quả thao tác
     |
     +-- outbox -> broker -> projection
                                |
                                v
                          Query API versioned
                                |
                                v
                     UI hội tụ khi đủ version
~~~

Đánh giá thành công không phải mọi màn hình luôn hiển thị tức thì, mà là người dùng có thông tin đúng về kết quả và không bị hướng sang hành động sai khi đọc dữ liệu cũ.

## 29. Checklist trước khi phát hành

1. **Owner:** Mỗi field và quyết định quan trọng do service nào sở hữu?
2. **Query path:** Có cache, replica, broker, projection hay search index?
3. **Freshness requirement:** Độ cũ nào có thể chấp nhận cho từng hành động?
4. **Write status:** Command trả ACCEPTED hay COMPLETED?
5. **Read-your-writes:** Có receipt/version token hoặc đường đọc owner?
6. **Watermark:** Tiến độ projection có bằng chứng và phạm vi rõ không?
7. **Timestamp:** occurredAt, projectedAt, fetchedAt được hiển thị đúng?
8. **Cache:** TTL, negative caching, invalidation và key theo quyền đã xét?
9. **UI:** Phân biệt loading, stale, pending, confirmed, error, partial?
10. **Copy:** Có nói đúng điều hệ thống thực sự biết không?
11. **CTA:** Những hành động nguy hiểm có bị giới hạn khi status chưa rõ?
12. **Polling/push:** Có backoff, deadline, reconnect và không nhân command?
13. **SLO:** Độ trễ end-to-end có được đo theo phân vị?
14. **Runbook:** Biết kiểm tra outbox, broker, consumer, DB, cache và replay?
15. **Recovery:** Khi mất event hoặc hết retention có reconciliation/backfill?
16. **Version:** Event đến trễ/trùng/sai thứ tự không làm state lùi?
17. **Concurrency:** Có optimistic lock/If-Match khi lưu form từ snapshot cũ?
18. **Security:** Cache và partial data không vượt tenant/permission?
19. **Tests:** Có kịch bản stale response, timeout, read-after-write và rollback?
20. **Ownership UX:** Ai quyết định thông báo degraded và escalation khi freshness SLO vi phạm?

---

**Nguyên tắc ghi nhớ:** Trong truy vấn liên dịch vụ, **đọc nhanh không đồng nghĩa dữ liệu mới**, và **dữ liệu cũ không chứng minh thao tác vừa làm đã thất bại**. Xác định owner, mô hình hóa trạng thái trung gian, trả version/freshness metadata có căn cứ, bảo vệ read-your-writes, đo độ trễ end-to-end và diễn đạt trung thực sự khác nhau giữa *đang xử lý*, *đã xác nhận nhưng chưa đồng bộ* và *không thể xác minh*. Nhờ đó hệ thống eventual consistency vẫn đem lại trải nghiệm đáng tin và không đánh đổi tính đúng đắn nghiệp vụ.