# Đọc dữ liệu cũ và các giới hạn về độ trễ nếu có

Trong một hệ NoSQL phân tán, API có thể xác nhận một lệnh ghi thành công nhưng ngay sau đó một request đọc vẫn trả **phiên bản dữ liệu cũ**. Trường hợp đó gọi là **stale read**. Nó có thể là hành vi được phép bởi mô hình nhất quán, không nhất thiết là lỗi kỹ thuật. Tuy nhiên, nếu bản cũ được dùng để quyết định thanh toán, tồn kho hoặc phân quyền, hậu quả có thể nghiêm trọng.

Giả sử khách hàng đổi địa chỉ từ `Hà Nội` sang `Đà Nẵng`. Server cập nhật xong, nhưng trang chi tiết vẫn hiện địa chỉ trước đó. Nguyên nhân có thể là replica chưa nhận cập nhật, cache chưa bị vô hiệu hóa hoặc một read model được đồng bộ bất đồng bộ.

Bài học thuộc chương **Các mô hình nhất quán** trong **Database No SQL**. Trọng tâm là cách nhận diện đọc cũ, giới hạn về độ trễ **nếu có**, các session guarantees, khác biệt giữa eventual consistency và bounded staleness, cùng đánh đổi về thời gian phản hồi, độ mới và khả dụng.

## 1. Mốc nào xác định một lần đọc là cũ?

Document ban đầu:

~~~javascript
{
  _id: "customer-101",
  tenantId: "shop-17",
  address: "Hà Nội",
  version: NumberLong("10")
}
~~~

Ứng dụng cập nhật:

~~~javascript
{
  _id: "customer-101",
  tenantId: "shop-17",
  address: "Đà Nẵng",
  version: NumberLong("11")
}
~~~

Request đọc sau đó trả `version=10`. Nếu ứng dụng đã ghi thành công version 11 và API hứa người dùng thấy cập nhật của mình, đây là một stale read vi phạm hợp đồng.

Nhưng nếu client đang xem **báo cáo chốt tại thời điểm cũ**, lấy một snapshot version 10 có thể là hành vi đúng. Độ cũ cần được đánh giá theo **mốc dữ liệu mà request có quyền yêu cầu**, không chỉ theo tuổi của trường `updatedAt`.

## 2. Những hiện tượng liên quan nhưng không giống nhau

| Hiện tượng | Đặc điểm | Ví dụ |
|---|---|---|
| Stale read | Trả bản cũ hơn mốc cần quan sát | GET v10 sau khi phải thấy v11 |
| Replication lag | Follower chưa áp đủ thay đổi từ nguồn | Secondary còn v10 |
| Read-your-writes violation | Client không thấy write của chính mình | PATCH v11 rồi GET v10 |
| Monotonic-reads violation | Client đã thấy bản mới rồi lại thấy bản cũ | GET v11 sau đó GET v10 |
| Cache stale | Cache chứa dữ liệu nguồn cũ | Redis vẫn còn giá cũ |
| Search/index lag | Search projection chưa theo kịp source | Search còn ACTIVE sau khi đã khóa |
| Lost update | Một write ghi đè thay đổi của write khác | Hai người cùng lưu form |
| Dirty read | Thấy thay đổi chưa commit | Nhìn giá trị sẽ bị rollback |
| Non-repeatable read | Read lặp trong transaction thấy giá trị đổi | Cùng row đổi giữa hai lần đọc |
| Phantom read | Tập kết quả query thay đổi | Có thêm Order thỏa điều kiện |

Không được dùng một cơ chế cho tất cả: CAS có thể ngăn lost update, nhưng không tự làm cache bắt kịp; invalidation cache giúp freshness nhưng không thay thế transaction tại nguồn.

## 3. Ba replica và một stale read

Sơ đồ:

~~~mermaid
flowchart TD
    Client --> Leader["Leader: version 11"]
    Leader --> A["Follower A: version 11"]
    Leader -. "Đang replication" .-> B["Follower B: version 10"]
    Client --> Router["Read router"]
    Router --> B
~~~

Dòng thời gian:

~~~text
t0 Leader, A, B cùng version 10
t1 Client gửi write version 11
t2 Leader xác nhận ghi theo write policy
t3 Follower A nhận version 11
t4 Follower B chưa nhận, vẫn version 10
t5 GET được route đến Follower B
t6 GET trả version 10
t7 B bắt kịp, sau đó GET mới có thể trả version 11
~~~

Một replica chậm có thể do network, CPU, disk I/O, apply backlog, restart hoặc mất kết nối giữa vùng. **Độ trễ replication** và **đường read routing** cùng ảnh hưởng kết quả: nếu router đọc từ node khác, request có thể thấy dữ liệu mới.

## 4. Đọc cũ có thể được chấp nhận khi nào?

| Use case | Mức chấp nhận | Lý do |
|---|---|---|
| Danh sách bài viết phổ biến | Có thể chịu stale | Thông tin mang tính khám phá |
| Lượt xem và biểu đồ | Có thể trễ theo SLO | Thống kê gần thời gian thực |
| Tìm kiếm dịch vụ | Có thể dùng projection eventual | Cần kiểm tra nguồn khi hành động |
| Hồ sơ vừa sửa xong | Thường cần read-your-writes | Tránh UX nhảy ngược |
| Hàng tồn kho để checkout | Không dùng stale preview để quyết định | Cần conditional write |
| Số dư, giao dịch thanh toán | Yêu cầu mạnh hơn | Invariant nghiệp vụ |
| Thu hồi quyền truy cập | Rủi ro cao khi stale | Đòi đường authorization có thẩm quyền |
| Báo cáo lịch sử đã khóa | Có thể dùng snapshot | Ưu tiên tính nhất quán theo mốc |

Không phải toàn bộ hệ thống đều cần một consistency level duy nhất. Có thể dùng read model nhẹ cho tìm kiếm và dùng nguồn có điều kiện ghi mạnh cho thanh toán.

## 5. Eventual consistency là gì?

Một mô tả tổng quát:

> Nếu không có thay đổi mới, các bản sao còn sống có thể trao đổi/khắc phục chênh lệch và các cơ chế đồng bộ hoạt động lại bình thường, cuối cùng chúng hội tụ theo quy tắc giải quyết xung đột của hệ thống.

Ví dụ:

~~~text
Thời điểm  Source  Replica
t0          v10     v10
t1          v11     v10
t2          v12     v10
t3          v12     v11
t4          v12     v12
~~~

Các lần đọc ở t1–t3 có thể thấy bản cũ. Mô hình eventual **không tự hứa**:

- Thấy ngay write của chính client.
- Không bao giờ đọc lùi version.
- Trễ tối đa 100 ms, 5 giây hoặc 1 phút.
- Không xuất hiện conflict khi nhiều region cùng write.
- Search index/cache đồng bộ đồng thời với source.
- Read từ một replica bất kỳ luôn thấy latest value.

Hội tụ cũng không bảo đảm giá trị cuối cùng là giá trị mọi writer đều mong muốn; một cơ chế conflict resolution có thể quyết định bản thắng theo thứ tự hoặc timestamp cụ thể.

## 6. Không có cận thời gian mặc định cho eventual consistency

Giả sử:

~~~text
Region A: v10 -> v11 -> v12 -> v13
Region B: v10, không nhận được dữ liệu từ A
Network partition kéo dài 2 giờ
~~~

Một client ở B vẫn có thể đọc v10 trong 2 giờ nếu hệ cho phép phục vụ từ bản sao bị cô lập. Chỉ khi mạng và cơ chế đồng bộ hồi phục, dữ liệu mới có cơ hội hội tụ.

Vì thế, việc p99 replication lag thường ngày bằng 200 ms **không chứng minh hard bound 200 ms** khi có outage. Thống kê bình thường và bảo đảm dưới mọi tình huống là hai khái niệm khác nhau.

## 7. Read latency khác staleness

- **Read latency:** thời gian từ lúc client gửi request đến khi nhận phản hồi.
- **Staleness:** mức cũ của dữ liệu trong phản hồi so với phiên bản hoặc write cần quan sát.

Ví dụ:

| Nguồn đọc | Latency minh họa | Phiên bản | Lag so với v12 |
|---|---:|---:|---:|
| Follower B | 5 ms | v10 | 2 version |
| Follower A | 12 ms | v12 | 0 version |
| Leader | 60 ms | v12 | 0 version |
| Search projection | 8 ms | v9 | 3 version |

Một read rất nhanh có thể trả dữ liệu rất cũ. Bảo đảm freshness thường làm thay đổi lựa chọn route/chờ/timeout và có thể ảnh hưởng latency hoặc availability.

## 8. Độ cũ theo version và theo thời gian

### Version-based staleness

Nếu cùng một entity có version tăng đơn điệu:

~~~text
Source customer-101: version 24
Response:            version 22
Lag:                 2 versions
~~~

Có thể tính:

\[
\Delta_v = v_{\text{latest known}} - v_{\text{read}}
\]

Nhưng version chênh 2 có thể xảy ra trong 1 ms hoặc nhiều ngày. Version theo document cũng không so sánh trực tiếp được với version của document khác.

### Time-based staleness

Một read có thể thiếu một write đã commit cách đây 10 giây. Khi đó về mặt thời gian, read đã bỏ qua một cập nhật hợp lệ từ 10 giây trước.

Tuy nhiên `now - updatedAt` **không đo chắc độ cũ**: record không được sửa suốt hai năm vẫn có thể là latest, còn record có `updatedAt` cách 1 giây có thể stale nếu source đã commit thêm write mới.

Muốn đo độ cũ theo thời gian cần mốc commit/checkpoint đáng tin, đồng hồ có sai số được kiểm soát, và khả năng đối chiếu với nguồn.

## 9. Bounded staleness

**Bounded staleness** là nhóm bảo đảm giới hạn mức cũ của một read thành công. Các hệ có thể định nghĩa bound bằng:

- **Số phiên bản K:** không cũ quá K versions.
- **Thời gian T:** không bỏ qua một write đã commit quá T thời gian.
- Quy tắc phối hợp K/T được chính hệ quản trị quy định.

Ví dụ K=2:

~~~text
Source latest v108
Allowed results: v106, v107, v108
Disallowed: v105 hoặc cũ hơn
~~~

Một hợp đồng time-bound có thể ghi: “GET thành công không được thiếu một write đã commit hơn 5 giây trước lúc đọc”.

Những câu này đòi **phạm vi**, **semantics**, **khả năng thực thi** và **hành vi khi không thể đáp ứng**. Không được tự hiểu từ nhãn bounded staleness rằng mọi sản phẩm dùng cùng cách kết hợp K/T.

### Nếu replica không theo kịp

Hệ có thể chờ, chuyển sang nguồn mới hơn hoặc trả lỗi/timeout. Nếu vẫn trả bản quá cũ và báo thành công như thể đáp ứng bound, guarantee đã bị phá.

## 10. Hard guarantee, SLO và thống kê

| Phát biểu | Loại |
|---|---|
| “P99 lag 300 ms trong tuần qua” | Metric quan sát |
| “99,9% GET có dữ liệu mới dưới 2 giây” | SLO |
| “Mọi GET thành công không lùi quá 2 version” | Guarantee nếu engine thực thi |
| “Read trung bình 10 ms” | Latency |
| “Thường cập nhật vài giây là thấy” | Kỳ vọng, không là bound |

SLO cho phép một tỷ lệ vi phạm theo định nghĩa. Guarantee của successful read là thuộc tính chính xác theo mô hình. **Không thay thế một cận cứng bằng biểu đồ percentile**.

## 11. Linearizability và strong reads

Một operation **linearizable** có thể được coi như xảy ra tại một điểm nằm giữa lúc nó bắt đầu và kết thúc, và tôn trọng thứ tự thời gian thực của những operation không chồng lấn.

~~~text
Write W11: [---------- successful]
                                Read R: [----- result]
=> Nếu read linearizable, R không trả v10
   khi W11 là write gần nhất phù hợp.
~~~

Nhưng bảo đảm có phạm vi:

- Có thể chỉ một item/key/document.
- Không tự tạo transaction snapshot cho nhiều document.
- Một “strong read” trong một region không tự là strong toàn bộ các region.
- Cache/search index khác có thể không dùng cùng mô hình.
- Dưới network partition, hệ có thể phải chờ hoặc từ chối read thay vì trả stale.

**Strong read không giữ chỗ cho tương lai**. Nếu GET báo còn 1 hàng, request khác có thể mua sau GET; checkout vẫn phải ghi có điều kiện tại nguồn.

## 12. Read-your-writes

**Read-your-writes (RYW)** bảo đảm client/session thấy các write đã hoàn tất của chính mình trong những read sau.

~~~text
Client A:
  PATCH address="Đà Nẵng" -> success v11
  GET profile             -> phải trả v11 hoặc mới hơn
~~~

Các phương pháp có thể gồm đọc authoritative source, giữ session context, mang causal token hoặc chờ follower có applied version đủ mới.

RYW **cho A không đồng nghĩa B ở region khác thấy ngay v11**. Nó là bảo đảm trong phạm vi client/session cụ thể.

## 13. Monotonic reads

Client đọc:

~~~text
GET qua Follower A -> v11
GET qua Follower B -> v10
~~~

Đây là **monotonic-reads violation**. Cùng client đã thấy phiên bản mới nhưng sau đó lại thấy bản cũ.

Một session có thể giữ:

~~~text
minimumObservedVersion(customer-101) = 11
~~~

Các read tiếp theo phải trả version ≥ 11 hoặc chờ/route/timeout theo policy. Khác RYW, monotonic reads cũng bảo vệ phiên bản mới **do người khác** ghi mà client đã nhìn thấy.

## 14. Causal consistency

Một ví dụ phụ thuộc nhân quả:

~~~text
W1: A đăng bài
R1: B đọc bài đó
W2: B bình luận
R2: C thấy bình luận nhưng không thấy bài gốc
~~~

Nếu cần causal consistency, việc thấy W2 có thể đòi nhìn thấy W1 vì W2 phụ thuộc vào W1. Mô hình này bảo vệ quan hệ nhân quả trong phạm vi áp dụng; không đồng nghĩa mọi write độc lập được xếp vào thứ tự toàn cục.

Các session guarantees thường được thảo luận gồm read-your-writes, monotonic reads, monotonic writes và writes-follow-reads. Cách engine thực thi và token phiên đọc/ghi cần được hiểu từ contract.

## 15. Consistent prefix và snapshot

Giả sử:

~~~text
W1 Tạo Order
W2 Xác nhận Order
W3 Đánh dấu đã giao
~~~

Một read nhìn thấy W3 mà không thấy các bước nền liên quan có thể tạo lịch sử không hợp lý. Consistent prefix bảo vệ tính liên tục một tiền tố hợp lệ của lịch sử theo định nghĩa mô hình.

Snapshot consistency giúp đọc một tập dữ liệu nhất quán tại một mốc logic. **Snapshot có thể cố ý ở quá khứ**: nhất quán tại mốc đó không có nghĩa latest.

## 16. Đường đọc có nhiều lớp gây stale

Một ứng dụng có thể lấy dữ liệu qua CDN, browser cache, Redis, database follower, materialized view hoặc search index. Ngay cả khi replication giữa các node database đã hoàn tất, một lớp khác vẫn có thể giữ bản cũ.

Có ít nhất các loại độ trễ:

- **Replication lag:** follower áp dụng chậm so với nguồn.
- **Indexing lag:** read model chưa xử lý thay đổi đã commit.
- **Search visibility delay:** index đã nhận thay đổi nhưng searcher chưa refresh.
- **Cache invalidation delay:** bản cache cũ chưa hết hạn hoặc chưa bị xóa.
- **End-to-end visibility lag:** thời gian từ write được xác nhận tới lúc đúng API nhìn thấy nó.
- **UX lag:** thời gian từ người dùng bấm lưu tới khi giao diện hiển thị phiên bản mới.

Cần ghi nhận **read path thực tế** trước khi điều tra. Dashboard replica lag = 0 không chứng minh cache/search đã cập nhật.

## 17. Cache TTL không phải freshness bound

Giả sử cache TTL là 30 giây. Điều đó **không tự bảo đảm dữ liệu stale tối đa 30 giây**, bởi:

1. Cache có thể được fill từ follower đã chậm 40 giây.
2. CDN và Redis có các TTL chồng nhau.
3. Chế độ stale-while-revalidate tiếp tục trả bản cũ.
4. Refresh cache có thể thất bại hoặc bị retry.
5. Invalidation event có thể mất hoặc đến sai thứ tự.
6. Browser có thể giữ cache riêng.

**Soft TTL** có thể là mốc bắt đầu refresh; **hard TTL** có thể là mốc không được trả một cache entry nữa. Nhưng hard TTL của entry không đồng nghĩa hard bound từ write nguồn, trừ khi hệ thống biết entry chứa trạng thái nguồn tới đâu.

Trong hệ cho phép stale-while-revalidate, người dùng có thể được trả ngay một bản đã quá thời hạn mềm để giảm latency. Hành vi này phù hợp với feed và số liệu gần đúng, nhưng không nên dùng để quyết định giao dịch hoặc phân quyền nhạy cảm.

## 18. Replication lag metric không phải guarantee từng request

Một dashboard báo lag trung bình 100 ms, nhưng:

- Một replica có thể lag 5 giây.
- Router có thể chọn đúng replica đó.
- Metric chỉ được lấy mẫu mỗi vài giây.
- Node đang bị cô lập có thể không còn phát metric mới.
- Write acknowledgment và apply checkpoint có semantics khác nhau.
- Request có thể được phục vụ từ cache, không phải replica.

Muốn cam kết mọi read thành công đều không cũ quá giới hạn, cần một mechanism **enforce ở đường read**, hoặc một consistency level của engine có guarantee tương đương. Cảnh báo khi lag cao là công cụ vận hành, không tự chặn read sai hợp đồng.

## 19. Quorum: giao nhau chưa đủ để chứng minh linearizability

Trong một số thiết kế replicated, người ta xét điều kiện `R + W > N`, với `N` số replica của một key, `W` số replica xác nhận ghi và `R` số replica tham gia đọc.

Ví dụ `N=3, W=2, R=2` tạo giao nhau giữa các tập quorum hai node. Đây là trực giác quan trọng nhưng **không tự chứng minh mọi hệ NoSQL linearizable**:

- Hệ có thể dùng sloppy quorum hoặc hinted handoff.
- Replica có thể ack trước khi apply/durable theo một mức cụ thể.
- Concurrent writes cần cơ chế ordering/conflict resolution đúng.
- Last-write-wins có thể dùng timestamp chịu ảnh hưởng clock skew.
- Repair/anti-entropy có thể chưa hoàn tất.
- Quorum có thể chỉ trong từng datacenter/region.
- Multi-key transaction không tự có từ quorum của một key.

Vì vậy phải đọc đúng mô hình nhất quán, write/read concerns và điều kiện lỗi của sản phẩm cụ thể.

## 20. MongoDB: read preference quyết định đọc ở đâu

MongoDB replica set cho phép driver định tuyến read theo các preference như `primary`, `secondary`, `primaryPreferred`, `secondaryPreferred` và `nearest` theo giới hạn topology và khả năng driver.

- Đọc `primary` hướng tới primary, nhưng vẫn phải xét read concern.
- Đọc `secondary` có thể chịu replication lag.
- `nearest` tập trung vào latency/topology phù hợp, **không có nghĩa tìm bản mới nhất**.
- Các chế độ preferred/fallback có thể tạo hành vi khác nhau khi node lỗi.

Một write được xác nhận ở primary không tự làm read ngay lập tức trên secondary thấy write đó.

Ba câu hỏi phải phân biệt:

- **Read preference:** chọn node đọc nào?
- **Read concern:** dữ liệu được phép quan sát có guarantee gì?
- **Write concern:** write đã được xác nhận/durable theo phạm vi nào?

Ngoài ra còn session/causal context: đọc từ một node đúng không có nghĩa read-your-writes tự được bảo vệ nếu context bị mất.

## 21. MongoDB: majority read khác latest read

MongoDB có read concern như `local`, `majority`, `snapshot` và `linearizable` trong những operation/topology được hỗ trợ.

Một lần đọc `majority` liên quan trạng thái đã được majority committed theo semantics MongoDB. Nhưng **majority-committed không có nghĩa latest toàn hệ tại thời điểm request**. Một replica có thể chưa thấy write mới hơn, dù bản nó trả đã từng majority-committed.

`snapshot` giúp đọc trạng thái nhất quán theo một mốc được hỗ trợ, nhưng mốc này có thể cố ý là quá khứ.

`linearizable` read concern có điều kiện và phạm vi chặt hơn, thường liên quan single-document read trên primary cùng với các yêu cầu write acknowledgment phù hợp. Nó không tự áp cho read từ secondary hoặc transaction nhiều document. Khi không xác minh được trạng thái nguồn trong network partition, read có thể chờ/timeout; cần cấu hình giới hạn thời gian thích hợp.

## 22. MongoDB: causal sessions và read-your-writes

Với một causally consistent session và read/write concerns phù hợp, MongoDB có thể bảo vệ những quan hệ nhân quả như read-your-writes trong phạm vi hỗ trợ.

Hình dung client ghi Customer v11, server trả causal operation/cluster time; lần đọc sau mang session context để hệ không đưa ra trạng thái trước mốc cần thấy.

Những điểm dễ sai:

- Request HTTP sau tạo một session mới và làm mất causal context.
- App có nhiều service nhưng không truyền token phù hợp.
- Read/write concern không đáp ứng điều kiện để có guarantee.
- Follower chưa bắt kịp nên request phải chờ.
- Operation song song dùng cùng session trái yêu cầu driver.
- Session guarantee bị nhầm với atomic multi-document transaction.

Không nên chỉ bật đọc secondary rồi tuyên bố người dùng luôn thấy ghi của mình.

## 23. MongoDB maxStalenessSeconds

Một read preference MongoDB có thể dùng `maxStalenessSeconds` trong server selection để loại secondary **được ước lượng quá stale** theo cơ chế của driver/server, với các ràng buộc cấu hình.

Nhưng đây không tự là bằng chứng mọi response HTTP có dữ liệu không cũ quá chính xác N giây so với source. Nó là một **chính sách lựa chọn node** dựa trên metadata/ước lượng, không tự có session causal hoặc linearizability.

Nếu không còn node đủ điều kiện, driver có thể chờ server selection hoặc báo lỗi theo cấu hình. Không nên quảng cáo một hard freshness bound chỉ vì tên tham số có chữ staleness.

## 24. DynamoDB: eventual và strongly consistent read

DynamoDB có eventually consistent reads có thể chưa phản ánh write mới ngay. Nó cũng hỗ trợ strongly consistent reads cho những loại request/index và phạm vi nhất định.

Ở base table và local secondary index, chế độ strong read có thể được yêu cầu theo khả năng DynamoDB. **Global Secondary Index (GSI)** có đồng bộ bất đồng bộ và không hỗ trợ cùng strong-read semantics như table/LSI.

Do đó sau khi cập nhật item:

- `GetItem` eventual từ table có thể thấy bản cũ.
- `GetItem` strong theo API/table được hỗ trợ có guarantee mạnh hơn trong scope đó.
- `Query` qua GSI có thể chưa tìm thấy item mới hoặc còn secondary attribute cũ.

Nếu phải xác nhận trạng thái mới nhất của item, nên đọc base table bằng key/chế độ phù hợp, hoặc tốt hơn đặt invariant vào chính conditional write.

## 25. DynamoDB Global Tables và multi-region

Với Global Tables, write ở region A không tự xuất hiện tức thì ở region B trong mọi chế độ replication.

Ví dụ region A đã có Order v11, region B còn v10. Một read “strong” trong vùng B không được tự hiểu là “thấy mọi write vừa commit ở mọi vùng trên thế giới”.

Cần xác định:

1. Chế độ Global Tables và cơ chế conflict resolution.
2. Region nào nhận write, region nào phục vụ read.
3. Cần session sticky region hoặc causal token không.
4. Nếu cùng lúc ghi một item ở nhiều vùng, semantics nào quyết định thắng.
5. Nếu read region bị partition, API chờ hay trả stale.
6. Invariant nghiệp vụ là region-local hay global.

**Tính nhất quán luôn cần phạm vi**; một tên consistency level không thể thay thế hiểu biết về topology.

## 26. Cassandra: consistency levels

Cassandra cung cấp các consistency levels như `ONE`, `QUORUM`, `LOCAL_QUORUM`, `ALL` theo khả năng và topology.

Với replication factor 3, một write ở CL=ONE và một read ở CL=ONE có thể tiếp xúc các replica chưa cùng trạng thái. Quorum read/write phù hợp có thể cải thiện tính quan sát write, nhưng còn:

- Concurrent writes và quy tắc giải quyết conflict.
- Timestamp và clock skew.
- Repair, hinted handoff và anti-entropy.
- Datacenter/partition scope.
- Semantics của read/write CL cụ thể.
- Những yêu cầu CAS cần Lightweight Transactions (`IF`).

Không nên tuyên bố `QUORUM` luôn linearizable, cũng không dùng read quorum thông thường thay cho conditional update nếu nghiệp vụ cần insert-if-absent.

## 27. Managed NoSQL có mức bounded staleness

Một số dịch vụ managed như Azure Cosmos DB cung cấp các tên consistency levels gồm strong, bounded staleness, session, consistent prefix và eventual theo cấu hình được hỗ trợ.

Để dùng mức bounded staleness đúng, phải đọc tài liệu của **phiên bản và chế độ triển khai cụ thể**:

- Cận là K phiên bản, T thời gian hay quy tắc kết hợp?
- Phạm vi bảo đảm theo partition, region hoặc account nào?
- Khi replication trễ vượt ngưỡng, hệ chờ, giảm throughput hay trả lỗi?
- Các ngưỡng K/T được phép cấu hình là gì?
- Session token được duy trì thế nào?
- Multi-region writes có ảnh hưởng tới guarantee không?
- Read latency/availability đổi ra sao dưới tải và sự cố?

Không nên tự gắn một con số phổ quát cho mọi dịch vụ có chữ “bounded”.

## 28. Search projection có thể stale dù source strong

Một hệ Catalog có source DB và Search index nhận thay đổi qua CDC/outbox/queue.

Dòng thời gian:

- `t0`: Source `Service ACTIVE, version 10`.
- `t1`: Source commit `Service INACTIVE, version 11`.
- `t2`: Search index chưa xử lý event, vẫn `ACTIVE v10`.
- `t3`: Indexer áp event v11.
- `t4`: Searcher refresh và query thấy `INACTIVE v11`.

Một read strong từ source ở t2 có thể thấy INACTIVE, trong khi Search API vẫn trả ACTIVE. Không có mâu thuẫn: hai đường đọc có **nguồn và consistency semantics khác nhau**.

Với quyết định booking hoặc cấp quyền, không nên chỉ tin một search hit eventual mà phải kiểm tra lại nguồn có thẩm quyền.

## 29. Event out-of-order làm read model lùi version

Source:

- v10: PENDING.
- v11: CONFIRMED.
- v12: CANCELLED.

Indexer nhận event v12 rồi event v11 đến muộn. Nếu update projection vô điều kiện, trạng thái Search bị lùi từ CANCELLED về CONFIRMED.

Consumer cần conditional apply dựa trên `sourceVersion`: chỉ nhận event có version mới hơn. Điều kiện và cập nhật phải nguyên tử **ngay ở projection**, tránh hai consumer đọc rồi ghi race.

Với xóa, có thể cần tombstone mang version để một event cũ không tạo lại document. CAS ở source không tự ngăn lỗi ordering ở các bản sao async.

## 30. Security: stale authorization

Thu hồi quyền truy cập hoặc khóa tài khoản là tình huống nhạy cảm. Nếu cache ACL hoặc Search projection còn thông tin cũ, API có thể cho truy cập trái phép.

Cần cân nhắc:

- Authorization dựa trên source có thẩm quyền cho thao tác nhạy cảm.
- Cache invalidation/revocation có quy trình rõ.
- Khi không kiểm tra được quyền hiện hành, có thể phải fail closed.
- Tenant isolation ở query và ở nguồn.
- Session token không được dùng như bằng chứng cấp quyền.
- Audit các quyết định truy cập và trạng thái source version.

Freshness có thể là **một yêu cầu bảo mật**, không chỉ mục tiêu UX.

## 31. Đọc mạnh không thay thế conditional write

Ngay cả một GET linearizable thấy còn đúng một sản phẩm tại 10:00:00, một request khác có thể mua ở 10:00:01. Đến 10:00:02, checkout vẫn cần bảo vệ điều kiện tại nguồn ghi.

Ví dụ MongoDB:

~~~javascript
db.inventory.updateOne(
  {
    _id: "shop-17#sku-A",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1 }
  }
);
~~~

Trong một single-document atomic update, điều kiện tồn kho và phép trừ được kiểm tra/áp cùng nhau. Strong read cho trạng thái tại một thời điểm **không khóa các thay đổi ở tương lai**.

## 32. Xây dựng API read-your-writes bằng minimum version

Giả sử người dùng PATCH hồ sơ, server trả:

~~~http
HTTP/1.1 200 OK
ETag: "v11"
Content-Type: application/json

{"id":"customer-101","version":11}
~~~

Lần GET kế tiếp có thể gửi:

~~~http
GET /customers/customer-101
X-Min-Version: 11
~~~

`X-Min-Version` là **header ứng dụng tự định nghĩa**, không phải primitive được mọi NoSQL hỗ trợ tự động.

Một server có thể:

1. Chọn replica đã áp dụng version ít nhất 11.
2. Nếu replica chậm, chờ trong giới hạn thời gian.
3. Thử đọc authoritative source hoặc một replica đủ mới.
4. Nếu không thể đáp ứng trước deadline, trả lỗi/timeout.
5. Không âm thầm trả v10 nhưng tuyên bố đã đạt RYW.

Mã giả:

~~~text
getCustomer(id, minVersion, deadline):
    while before deadline:
        result = readFromPermittedSource(id)
        if result.version >= minVersion:
            return result
        waitOrRouteToNewerSource()
    return FRESHNESS_UNAVAILABLE
~~~

### Giới hạn

- Version phải tăng đúng trong toàn bộ đường ghi của entity.
- Xóa document có thể tạo trạng thái “not found” mới hơn; cần version/tombstone semantics.
- Recreate cùng ID mà reset version có thể gây ABA, cần generation/epoch.
- Version theo document không tự tạo snapshot đa document.
- MinVersion quá lớn do client gửi có thể gây chờ vô hạn nếu không validate.
- Session token không thay thế authentication và tenant authorization.
- Một response từ cache có version đủ mới chưa chắc đã giữ đủ invariant của một transaction nhiều tài nguyên.

Đây là mẫu API, cần mapping vào read concerns/session capability của database thật.

## 33. Session giữa các request HTTP

Một flow:

~~~text
PATCH /profile -> success version 18
Client giữ minimumVersion=18
GET /profile -> gửi minimumVersion=18
Server chỉ trả bản >=18 hoặc báo chưa thể đáp ứng
~~~

Cần xử lý:

- Browser reload, nhiều tab, app mobile đóng/mở.
- HTTP load balancer chuyển API instance.
- Chuyển region khi di động thay network.
- Session token hết hạn hoặc bị mất.
- Một entity bị xóa/tái tạo.
- User đăng xuất/chuyển account.
- Token bị giả mạo hoặc dùng sai scope tenant.

Sticky routing có thể giảm việc chuyển follower, nhưng không tự bảo đảm replica sticky đã theo kịp mọi write cần thấy. **Session guarantee cần được thực thi**, không chỉ trông chờ routing.

## 34. Timestamp cũ không chứng minh stale

Document:

~~~javascript
{
  _id: "product-101",
  name: "Bàn phím cơ",
  updatedAt: ISODate("2024-01-01T00:00:00Z")
}
~~~

Nếu sau năm 2024 không có write nào, read năm 2026 vẫn có thể là latest. Tuổi của bản ghi lớn không đồng nghĩa đang thiếu cập nhật.

Ngược lại một bản có `updatedAt` cách đây một giây vẫn có thể stale nếu source đã có write mới trong 100 ms gần đây.

Muốn đo stale phải so với **một write đã commit mà read chưa phản ánh** hoặc một checkpoint/version nguồn, không chỉ trừ `Date.now() - updatedAt`.

## 35. Clock skew và thời gian commit

Độ cũ theo thời gian có thể được đo qua nhiều mốc:

- Client gửi write.
- Server nhận write.
- Source commit.
- Replica apply.
- Search index refresh.
- API response.

Những mốc trên thường thuộc các đồng hồ khác nhau. Nếu lệch, phép trừ có thể âm hoặc quá nhỏ so với thực tế.

Nên:

- Dùng commit/checkpoint time có nghĩa và nguồn đáng tin.
- Theo dõi clock skew nếu cần thời gian tuyệt đối.
- Dùng monotonic clock khi đo duration trên cùng process.
- Phân biệt event time, ingest time và commit time.
- Dùng log position/sequence nếu timestamp không đủ.
- Công bố sai số khi không thể đo chính xác theo mili giây.

**Time-bound consistency không được suy ra chỉ bằng cách nhìn một timestamp do client gửi.**

## 36. Đo search/replica visibility lag bằng probe

Một kỹ thuật là tạo một probe record với version tăng:

1. Ghi version N vào source.
2. Chờ write được xác nhận theo write concern được chọn.
3. Ghi mốc T0 bằng monotonic clock của test process.
4. Đọc qua đúng API/read route muốn kiểm tra.
5. Lặp đến khi thấy version N hoặc hết deadline.
6. Ghi elapsed time, node/region/route, timeout, lỗi.
7. Không loại những lần timeout khỏi thống kê.

Pseudocode:

~~~text
sequence = nextProbeSequence()
writeProbe(sequence)
awaitAcknowledgment()
t0 = monotonicNow()
seen = false

while monotonicNow() - t0 < timeout:
    r = readProbeThroughTargetRoute()
    if r.sequence >= sequence:
        recordVisibilityDelay(monotonicNow() - t0)
        seen = true
        break

if not seen:
    recordTimeoutAndRoute()
~~~

### Tại sao probe chưa chứng minh hard guarantee?

- Probe có thể nằm trên partition ít tải hơn dữ liệu thật.
- Cache key/route của probe có thể khác.
- Một số path có thể bypass Search hoặc CDN trong test.
- Write acknowledgment chưa chắc bằng commit time theo định nghĩa đang đo.
- Probe đo một phân bố **quan sát**, chưa kiểm chứng mọi read.
- Bỏ các kết quả timeout tạo **survivorship bias**.

Cần bổ sung checkpoint/lag theo node, test lỗi và kiểm soát chất lượng dữ liệu.

## 37. Kiểm thử read-your-writes và đọc không lùi

### Test RYW

~~~text
Session S:
  GET Customer -> version 10
  PATCH Customer -> success version 11
  GET Customer cùng session
  ASSERT version >= 11
~~~

Nên cố tình route GET tới follower chưa bắt kịp; kiểm tra app chờ/route/timeout theo hợp đồng.

### Test monotonic reads

~~~text
Session S:
  GET qua Follower A -> version 20
  GET qua Follower B -> version 19
  ASSERT no successful result below version 20
~~~

Nếu API hứa monotonic reads, response v19 thành công là vi phạm. Có thể phải chờ hoặc từ chối đọc khi không đủ mới.

Test thêm trường hợp:

- API đổi instance/server.
- Follower restart.
- Leader failover.
- Session token bị mất.
- Client đọc từ region khác.
- Document bị xóa và tái tạo.
- Token hết hạn hoặc dùng sai tenant.

## 38. Fault injection cho consistency

| Tình huống | Điều cần quan sát |
|---|---|
| Replication bị chặn | Độ cũ kéo dài và read behavior |
| Follower restart | Có phục vụ read trước khi catch-up không |
| Leader failover | RYW, acknowledgement và error handling |
| Router đổi node liên tục | Monotonic-reads violations |
| Cache invalidation bị mất | Bản cũ được trả bao lâu |
| Search indexer dừng | Index visibility lag và hồi phục |
| Event đến sai thứ tự | Projection có lùi sourceVersion không |
| Clock lệch | Dashboard freshness có báo sai không |
| Network xuyên region chậm | Latency vs freshness trade-off |
| Replica không đủ mới | Wait, fallback hay timeout? |

Không thực hiện fault injection phá production nếu chưa có quy trình cô lập và phê duyệt.

## 39. Metric cần đo

### Replication

- Lag theo node/region và apply log position.
- Catch-up duration.
- Read routing/read preference thực tế.
- Write concern/quorum failures.
- Leader election.
- Server selection timeout.

### Cache và projection

- Cache hit/miss và số lần serve stale.
- Soft/hard TTL expiration.
- CDC/outbox/queue lag.
- Indexer sourceVersion và Search visibility delay.
- Event retry/dead letter/out-of-order.
- Chênh lệch dữ liệu nguồn với projection.

### API/session

- Read latency p50/p95/p99.
- Read-your-writes violation count.
- Monotonic read violation count.
- Freshness wait và timeout rate.
- Version lag distribution khi có mốc nguồn.
- Tỷ lệ fallback sang authoritative source.
- Số request không thể đạt hard-bound consistency.

**Không gom read latency và freshness vào một chỉ số.** Một API có thể trả rất nhanh nhưng nhiều version cũ.

## 40. Data-as-of và watermark cho báo cáo

Một API báo cáo:

~~~json
{
  "reportDate": "2026-11-14",
  "confirmedOrders": 12540,
  "dataAsOf": "2026-11-14T09:00:00Z",
  "generatedAt": "2026-11-14T09:05:00Z"
}
~~~

`generatedAt` là thời điểm báo cáo được dựng; `dataAsOf` phải là mốc dữ liệu được pipeline xử lý đầy đủ **theo định nghĩa của pipeline**.

Nếu có nhiều partition, không được lấy timestamp mới nhất của một partition rồi tuyên bố mọi partition đã tới mốc đó. Watermark xử lý event time còn có semantics về late arrivals, khác commit log position.

## 41. Thiết kế API nhiều chế độ freshness

| Chế độ | Đường đọc ví dụ | Hợp đồng |
|---|---|---|
| `FAST` | Cache/follower | Best-effort, có thể stale |
| `SESSION` | Session-aware replica/source | Read-your-writes/minVersion |
| `AUTHORITATIVE` | Strong/source path theo engine | Mạnh hơn hoặc lỗi khi không đạt |

Request ứng dụng có thể cho phép:

~~~http
GET /customers/customer-101
X-Read-Mode: SESSION
X-Min-Version: 11
~~~

Response:

~~~http
HTTP/1.1 200 OK
ETag: "v11"
X-Data-Version: 11
Cache-Control: private, no-store
~~~

`X-Read-Mode` và `X-Data-Version` là header tự thiết kế, không phải chuẩn chung của NoSQL. App phải kiểm tra quyền tenant, giới hạn tải và không cho client yêu cầu tùy ý một chế độ mà backend không hỗ trợ.

## 42. Khi hard bound không thể được đáp ứng

Hợp đồng: “Mọi GET thành công không cũ quá 5 giây”. Region B bị cô lập hai phút, nguồn ở A vẫn tiếp tục write.

B có các lựa chọn:

- Chờ mạng phục hồi.
- Route sang nguồn đủ mới nếu vẫn liên lạc được.
- Trả timeout/unavailable.
- Có một endpoint khác được công bố là **best-effort stale** nếu sản phẩm muốn UX degrade.

Không thể tiếp tục trả v10 thành công theo hard-bound mode khi những write mới hơn đã vượt mốc cho phép. Việc trả stale rồi đặt tên là bounded không biến nó thành guarantee.

Dưới partition, freshness mạnh có thể làm tăng latency hoặc giảm availability. Không nên giản lược tất cả engine NoSQL vào một nhãn AP/CP cho toàn hệ, vì nhiều API và level có phạm vi khác nhau.

## 43. Những sai lầm thường gặp

**“Eventual consistency là dữ liệu trễ tối đa vài giây.”** Không có hard bound mặc định.

**“Replica lag bằng 0 nên mọi GET mới nhất.”** Cache, read routing và Search có thể stale.

**“Đọc rất nhanh nghĩa là dữ liệu mới.”** Read latency và staleness khác nhau.

**“updatedAt cũ chứng minh replica chậm.”** Record có thể không thay đổi trong nhiều năm.

**“Cache TTL 30 giây bảo đảm stale tối đa 30 giây.”** Cache có thể được fill từ source stale hoặc serve stale quá TTL mềm.

**“R+W>N tự chứng minh linearizability.”** Cần xét conflict/order và implementation.

**“MongoDB majority read luôn latest.”** Majority-committed và latest read là các thuộc tính khác.

**“MongoDB maxStalenessSeconds là hard-bound per HTTP response.”** Nó có semantics server selection riêng.

**“DynamoDB GSI có strong read giống table.”** GSI đồng bộ bất đồng bộ.

**“Strong read trong một region thấy mọi write toàn cầu.”** Phải xét cross-region replication.

**“Cassandra QUORUM là serializable cho mọi transaction.”** Consistency level khác LWT/transaction semantics.

**“Read-your-writes cho A cũng bảo đảm B thấy ngay.”** RYW theo session/client.

**“Causal consistency nghĩa là snapshot mới nhất toàn hệ.”** Nó bảo vệ causal order, không tự latest.

**“SLO p99 lag tốt chứng minh bounded guarantee.”** Observation và hard guarantee khác nhau.

**“GET strong bảo vệ checkout sau đó.”** Cần conditional write vì state có thể đổi sau GET.

**“CAS ở nguồn khiến Search không thể stale.”** Projection còn pipeline riêng, có lag/out-of-order.

**“Nếu không đạt bound, trả stale nhưng vẫn gọi thành công cũng được.”** Không đúng với hard guarantee đã công bố.

## 44. Bài tập thực hành

### Bài A — Latency và freshness

Follower trả GET trong 8 ms với v10, source đã commit v12 trước request.

**Hỏi:** có mới vì GET rất nhanh không?

**Hướng giải:** không. Độ trễ phản hồi 8 ms, độ cũ hai version; chưa biết số giây nếu thiếu commit times.

### Bài B — Eventual

Region B bị partition 15 phút, tiếp tục đọc bản cũ.

**Hỏi:** chỉ vậy có chứng minh eventual consistency bị vi phạm không?

**Hướng giải:** không; eventual không tự có cận thời gian. Cần xem hợp đồng và hội tụ sau khi kết nối hồi phục.

### Bài C — RYW

Client PATCH thành v11 rồi GET cùng session v10.

**Hỏi:** nếu API hứa RYW thì sao?

**Hướng giải:** vi phạm read-your-writes.

### Bài D — Monotonic reads

Một session đọc v20 rồi từ replica khác đọc v19.

**Hỏi:** vấn đề gì?

**Hướng giải:** vi phạm monotonic reads nếu API có guarantee này.

### Bài E — Version-bound

Source v108, allowed lag tối đa 2 versions.

**Hỏi:** v105 có hợp lệ không?

**Hướng giải:** không; v106 trở lên mới đủ.

### Bài F — Partition và hard bound

API hứa không cũ quá 5 giây nhưng read region cô lập trong hai phút, source vẫn cập nhật.

**Hỏi:** có thể luôn trả bản cũ thành công và giữ promise không?

**Hướng giải:** không; phải chờ/route/error hoặc công bố một chế độ khác.

### Bài G — Cache TTL

Cache TTL 30 giây, fill từ replica trễ 40 giây.

**Hỏi:** stale có thể vượt 30 giây không?

**Hướng giải:** có. TTL tính tuổi entry, không đo age của missing source updates.

### Bài H — MongoDB secondary

PATCH profile thành công trên primary, GET secondary trả cũ.

**Hỏi:** cách cải thiện RYW?

**Hướng giải:** đọc nguồn phù hợp, dùng causal session/token và read/write concern đáp ứng yêu cầu; xử lý wait/timeout.

### Bài I — DynamoDB GSI

PutItem thành công, Query GSI ngay sau đó không thấy item.

**Hỏi:** write chắc chắn thất bại?

**Hướng giải:** không; GSI có thể chưa cập nhật.

### Bài J — Cassandra quorum

RF=3, R=2, W=2. Nhóm vận hành kết luận mọi concurrent write đều linearizable.

**Hỏi:** đủ chưa?

**Hướng giải:** chưa; còn semantics timestamp/conflict resolution, quorum implementation và fault model.

### Bài K — Inventory

GET strong cho biết còn một sản phẩm; request khác mua trước khi checkout hiện tại ghi.

**Hỏi:** GET strong đã đủ ngăn bán quá chưa?

**Hướng giải:** chưa, phải conditional decrement/transaction tại nguồn.

### Bài L — Search index

Source có `status=INACTIVE v11`; Search còn `ACTIVE v10`. Người dùng nhấn booking.

**Hỏi:** kiểm tra tại đâu?

**Hướng giải:** source-of-truth của nghiệp vụ khi commit, không chỉ Search hit.

### Bài M — Timestamp

Một document có updatedAt từ năm ngoái và không có write mới.

**Hỏi:** read có stale không?

**Hướng giải:** không mặc nhiên; đó có thể là phiên bản mới nhất.

### Bài N — Probe timeout

1.000 probe, 950 thấy update trong 1 giây, 50 probe timeout. Dashboard chỉ giữ 950 kết quả rồi tuyên bố 100% đạt dưới 1 giây.

**Hỏi:** sai ở đâu?

**Hướng giải:** loại mẫu thất bại làm sai thống kê và không chứng minh hard guarantee.

## 45. Checklist thiết kế consistency cho một endpoint

1. Xác định source-of-truth của entity.
2. Mô tả read path: primary, secondary, cache, GSI, Search hay báo cáo.
3. Ghi rõ stale gây hại ở trường hợp nào.
4. Chọn guarantee: eventual, session, RYW, monotonic, causal, bounded hoặc strong.
5. Chỉ rõ scope: key, partition, region, transaction hay session.
6. Nếu có bound, định nghĩa K/T, mốc đo, điều kiện và behavior khi không đạt.
7. Có version/session token và cách duy trì qua các request.
8. Có timeout, retry/fallback được công bố.
9. Dùng conditional write cho invariant, không dựa vào read mạnh trước đó.
10. Có authorization và tenant isolation.
11. Đo read latency **và** freshness.
12. Kiểm thử partition, failover, cache stale, event out-of-order.
13. Quan sát sourceVersion, lag và violation metrics.
14. Tài liệu UX cho biết thời điểm dữ liệu được cập nhật và hành vi chưa đồng bộ.

Ví dụ hợp đồng:

~~~yaml
endpoint: GetOwnProfile
owner: CustomerService
sourceOfTruth: CustomerDocument
consistency:
  guarantee: readYourWrites
  scope: authenticatedClientSession
  token: lastSuccessfulWriteVersion
  ifUnavailable: timeoutOrError
readPath:
  preferred: sessionAwareReplica
  fallback: authoritativeSource
freshness:
  metric: perEntityVersion
  hardTimeBound: unspecified
response:
  includeVersion: true
security:
  tenantIsolation: required
  authorization: authoritative
observability:
  - readYourWritesViolations
  - monotonicReadViolations
  - replicationLag
  - freshnessWaitDuration
  - freshnessTimeouts
~~~

YAML là tài liệu thiết kế minh họa, **không phải cấu hình được MongoDB, DynamoDB hay Cassandra tự áp dụng**. Cần hiện thực bằng API, driver, session token, read/write concern và routing thật.

## 46. Kết luận

**Đọc dữ liệu cũ** có thể xảy ra khi follower, cache, Search hoặc read projection chưa theo kịp source. Đó có thể là đánh đổi hợp lý cho việc giảm latency và tăng khả dụng, nhưng chỉ khi nghiệp vụ thật sự chấp nhận.

**Eventual consistency không tự cung cấp giới hạn thời gian**. **Bounded staleness** chỉ có nghĩa khi bound, phạm vi và hành vi không đáp ứng được mô tả và thực thi. **Session/causal guarantees** bảo vệ những quan hệ theo client và thứ tự nhân quả. **Linearizability** bảo vệ thứ tự thời gian thực trong phạm vi operation được hỗ trợ, thường có đánh đổi khi mạng hoặc node lỗi.

> **Đọc nhanh chưa chắc là đọc mới. Replica khỏe chưa chắc cache đã mới. Một biểu đồ lag đẹp chưa tự là hard guarantee. Và một GET mới nhất chưa bảo vệ quyết định ghi sẽ xảy ra sau đó.**

Hãy xuất phát từ invariant nghiệp vụ, ghi freshness contract theo từng API, bảo vệ các điều kiện ghi ở nguồn có thẩm quyền, đo cả latency lẫn độ cũ và kiểm thử khi hệ gặp sự cố. Nhờ vậy, việc dữ liệu có thể bị trễ trở thành một đánh đổi được quản lý, thay vì một bất ngờ làm sai hành vi của ứng dụng.
