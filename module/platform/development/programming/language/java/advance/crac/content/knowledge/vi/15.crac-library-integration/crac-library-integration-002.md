# Redis client, cache phân tán và việc tái lập kết nối

Redis thường được dùng làm cache phân tán, kho dữ liệu tạm thời, message broker hoặc nơi lưu trạng thái phục vụ nhiều instance Java. Ứng dụng truy cập Redis thông qua client như Lettuce, Jedis hoặc Redisson. Client có thể quản lý socket, connection pool, event loop, topology, authentication, Pub/Sub subscription và các tác vụ nền.

Khi ứng dụng sử dụng CRaC (Coordinated Restore at Checkpoint), các object client và cache trong heap có thể được khôi phục cùng tiến trình. Tuy nhiên, kết nối mạng và trạng thái ở Redis server vẫn thay đổi độc lập trong thời gian checkpoint. Redis có thể restart, failover, đổi primary, cập nhật topology hoặc thu hồi connection idle. Một subscription có thể bị ngắt và các invalidation event có thể bị bỏ lỡ.

Vì vậy, ứng dụng cần quản lý vòng đời Redis client một cách chủ động: dừng công việc đang dùng client trước checkpoint, giải phóng hoặc chuẩn bị lại kết nối theo hướng dẫn của thư viện, rồi tạo kết nối mới, xác thực, khám phá topology và khôi phục subscription sau restore. Chỉ mở traffic khi Redis cùng các chức năng thiết yếu đã sẵn sàng.

## 1. Redis client và cache phân tán

Redis là một kho dữ liệu chạy độc lập với tiến trình Java. Ứng dụng giao tiếp với Redis qua giao thức mạng RESP. Client Java che giấu phần lớn chi tiết giao thức và cung cấp API để đọc, ghi, quản lý key, transaction, Pub/Sub, Streams và các cấu trúc dữ liệu khác.

Một ứng dụng có thể dùng Redis theo nhiều cách:

- **Cache-aside:** ứng dụng đọc cache trước; nếu miss thì đọc nguồn dữ liệu và ghi kết quả vào Redis.
- **Distributed cache:** nhiều instance dùng chung một tập key và TTL.
- **Session store:** lưu session hoặc trạng thái người dùng.
- **Rate limiter:** đếm request và giới hạn tốc độ.
- **Distributed lock:** phối hợp quyền truy cập giữa nhiều instance.
- **Pub/Sub:** gửi sự kiện đến subscriber đang hoạt động.
- **Redis Streams:** lưu message có ID, consumer group và trạng thái pending.
- **Client-side caching:** giữ bản sao L1 trong bộ nhớ ứng dụng và nhận invalidation từ Redis.

Những cách dùng này có yêu cầu phục hồi khác nhau. Một lệnh GET có thể được gửi lại tương đối đơn giản; một lệnh ghi, thao tác lock, transaction hoặc xử lý message cần xác định kết quả trước khi retry.

### 1.1. Các thành phần do Redis client quản lý

Tùy thư viện, một Redis client có thể sở hữu hoặc tham chiếu đến:

| Thành phần | Vai trò | Rủi ro quanh checkpoint |
|---|---|---|
| Client object | Cấu hình và tạo kết nối | Có thể đã bị đóng hoặc giữ cấu hình cũ |
| TCP connection | Truyền lệnh và response | Peer hoặc network path có thể đã hết hạn |
| Connection pool | Quản lý nhiều kết nối | Connection trong pool có thể stale; connection đang mượn cần được trả |
| Event loop / Netty resources | Xử lý I/O bất đồng bộ | Thread và channel cần lifecycle phù hợp |
| Cluster topology | Biết node và slot mapping | Primary hoặc node có thể đã thay đổi |
| Pub/Sub connection | Nhận sự kiện liên tục | Subscription có thể mất khi disconnect |
| Stream consumer | Đọc message theo consumer group | Message có thể còn pending hoặc cần reclaim |
| Client-side cache | Giữ bản sao trong heap | Có thể bỏ lỡ invalidation khi client ngắt kết nối |

Không phải thư viện nào cũng dùng cùng mô hình. Một số client quản lý kết nối tự động và có khả năng reconnect khi mạng bị gián đoạn trong lúc JVM đang chạy. Một số client dùng pool để cấp kết nối ngắn hạn. Một số client dùng event loop và connection dùng chung. Hãy xác định rõ thư viện, phiên bản và thành phần nào sở hữu từng resource.

### 1.2. Cache phân tán không đồng nghĩa với local cache

Redis thường là L2 cache dùng chung giữa nhiều instance. Local cache trong heap là L1 cache của từng tiến trình.

~~~text
Instance A: L1 cache ─┐
                     ├── Redis (L2) ─── Database / source of truth
Instance B: L1 cache ─┘
~~~

Sau restore, local cache của instance A có thể chứa dữ liệu cũ, trong khi Redis đã được instance B cập nhật. Kết nối đến Redis có thể hoạt động trở lại nhưng điều đó không tự làm local cache đồng bộ.

Ứng dụng cần có chính sách TTL, version, invalidation hoặc refresh để đảm bảo dữ liệu L1 phù hợp với dữ liệu có thẩm quyền.

## 2. Điều gì thay đổi trong thời gian checkpoint?

Giả sử ứng dụng tạo checkpoint lúc 09:00 và restore lúc 09:30. Trong 30 phút đó, Redis và hệ thống mạng vẫn hoạt động:

- Redis server có thể restart hoặc được nâng cấp.
- Redis Sentinel có thể bầu primary mới.
- Redis Cluster có thể thay đổi slot ownership.
- Load balancer, firewall hoặc NAT có thể xóa connection idle.
- ACL user hoặc password có thể được thay đổi.
- TLS certificate có thể được thay thế hoặc hết hạn.
- Pub/Sub subscriber có thể mất kết nối và bỏ lỡ message.
- Consumer group của Redis Streams có thể có message mới hoặc pending message cũ.
- Key trong cache có thể hết TTL hoặc bị xóa.
- Local cache có thể bỏ lỡ invalidation event.

Object Redis client vẫn có thể còn trong heap sau restore. Nhưng object đó không chứng minh socket còn dùng được, server vẫn ở cùng node, subscription còn tồn tại hoặc dữ liệu local còn mới.

~~~mermaid
sequenceDiagram
    participant A as Java application
    participant C as Redis client
    participant R as Redis server
    A->>C: GET / SET / SUBSCRIBE
    C->>R: TCP connection
    Note over A: Create checkpoint
    Note over C: Process is checkpointed
    Note over R: Redis continues running
    R->>R: Restart / failover / topology change
    Note over A: Restore process
    A->>C: Reuse restored client state
    C-->>A: Reconnect, error or stale state
    A->>R: Re-authenticate and discover topology
    R-->>A: Current server state
~~~

Một số client có thể tự reconnect sau lỗi mạng thông thường. Tuy nhiên, reconnect ở tầng TCP không tự phục hồi mọi trạng thái ứng dụng. Cần phân biệt transport connection, Redis protocol state, subscription, consumer progress và cache consistency.

## 3. Automatic reconnect có giải quyết toàn bộ vấn đề không?

Nhiều Redis client hỗ trợ reconnect tự động. Khi socket bị ngắt trong lúc ứng dụng đang chạy, client có thể thử mở kết nối mới và tiếp tục xử lý lệnh theo chính sách của thư viện.

Điều này hữu ích nhưng không phải bảo đảm rằng mọi hoạt động sẽ tiếp tục đúng sau CRaC restore.

Automatic reconnect thường không tự quyết định được:

- Một lệnh ghi trước checkpoint đã được Redis thực thi hay chưa.
- Một Pub/Sub message bị gửi trong lúc subscriber offline có cần xử lý lại không.
- Một subscription có cần tạo lại với handler và trạng thái ứng dụng hiện tại không.
- Local cache có bỏ lỡ invalidation hay không.
- Một Redis lock còn thuộc quyền sở hữu của client hay đã hết lease.
- Một transaction hoặc pipeline đang dang dở có thể tiếp tục hay không.
- Cluster topology đã thay đổi và mọi route đã được cập nhật hay chưa.
- Credential hoặc certificate hiện tại còn hợp lệ hay không.

Nếu client có CRaC integration chính thức, hãy xem hướng dẫn của phiên bản đó. Integration có thể đã đăng ký resource và xử lý event loop, connection hoặc pool. Tránh tự đóng cùng resource lần thứ hai nếu thư viện đã quản lý nó.

Nếu client không hỗ trợ rõ ràng việc checkpoint/restore, chiến lược dễ kiểm soát thường là dừng hoạt động, đóng client hoặc connection theo đúng API của thư viện trước checkpoint, rồi tạo client mới sau restore.

### 3.1. Phân biệt reconnect và recreate

| Hành động | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Reconnect | Client hiện tại thử thiết lập lại transport connection | Thư viện hỗ trợ reconnect và trạng thái nội bộ còn hợp lệ |
| Recreate connection | Đóng connection cũ, tạo connection mới | Socket cũ hoặc protocol state không đáng tin cậy |
| Recreate client | Tạo client object và resource manager mới | Client đã shutdown hoặc event loop/pool cần khởi tạo lại |
| Refresh topology | Cập nhật node, slot hoặc primary hiện tại | Redis Cluster/Sentinel thay đổi |
| Resubscribe | Đăng ký lại channel/pattern | Pub/Sub hoặc invalidation listener bị disconnect |
| Reconcile data | Đối chiếu cache local với dữ liệu có thẩm quyền | Có thể bỏ lỡ invalidation trong thời gian offline |

Không nên gọi một phương thức reconnect chung nếu thư viện không cung cấp hoặc client đã được shutdown hoàn toàn. Một client đã đóng có thể không thể sử dụng lại; lúc đó cần tạo instance mới.

## 4. Quản lý connection pool

Một connection pool giữ nhiều connection để tái sử dụng và giảm chi phí mở TCP/TLS connection. Các ứng dụng dùng Jedis thường gặp mô hình pool cấp một Jedis connection cho mỗi thao tác hoặc scope. Lettuce thường hỗ trợ connection bất đồng bộ và có thể dùng một connection thread-safe cho nhiều lệnh trong các trường hợp được thư viện hỗ trợ. Redisson quản lý connection và resource nội bộ theo cấu hình của nó.

### 4.1. Connection đang được mượn

Trước checkpoint, pool có thể có connection đang được một thread mượn để thực hiện lệnh. Nếu đóng pool trong lúc connection vẫn đang được dùng, request có thể thất bại giữa chừng.

Cần:

1. Ngừng nhận request mới dùng Redis.
2. Dừng worker và scheduled task đang gửi lệnh.
3. Chờ thao tác Redis đang chạy hoàn tất.
4. Đảm bảo connection đã được trả về pool.
5. Đóng pool/client theo lifecycle của thư viện.

Không nên đóng pool trước khi các borrower kết thúc. Với connection pool, theo dõi số connection active, idle và số borrower đang chờ sẽ giúp xác định thời điểm có thể đóng an toàn.

### 4.2. Không giữ connection mượn xuyên qua checkpoint

Một connection được mượn từ pool nên có phạm vi sử dụng rõ ràng. Không giữ connection trong field của singleton hoặc trong một task chờ lâu nếu thư viện kỳ vọng connection được trả lại sau mỗi thao tác.

Với Jedis, một Jedis instance thường không được chia sẻ đồng thời giữa nhiều thread; hãy dùng pool theo cách thư viện hướng dẫn và trả connection về pool trong finally hoặc try-with-resources.

Ví dụ minh họa:

~~~java
try (Jedis jedis = jedisPool.getResource()) {
    return jedis.get("product:42");
}
~~~

Trong mô hình này, close trên Jedis được mượn thường trả resource về pool theo contract của thư viện. Hãy xác nhận hành vi của phiên bản đang dùng; việc đóng toàn bộ pool là thao tác lifecycle khác.

### 4.3. Tạo pool mới sau restore

Nếu pool đã bị shutdown trước checkpoint, không nên cố dùng lại pool đó. Tạo pool mới từ cấu hình hiện tại:

- Hostname hoặc seed node.
- Port.
- TLS và trust configuration.
- ACL username/password hoặc credential provider.
- Connection timeout và command timeout.
- Pool size và giới hạn chờ.
- Cluster/Sentinel discovery.
- Retry và health-check policy.

Không lưu credential cố định trong checkpoint nếu nền tảng có thể rotate secret. Sau restore, nên đọc lại secret từ nguồn được quản lý và khởi tạo client theo cấu hình hiện tại.

## 5. Redis Standalone, Sentinel và Cluster

Chiến lược kết nối lại phụ thuộc topology Redis.

### 5.1. Standalone

Với Redis standalone, client thường kết nối đến một hostname và port. Sau restore, client cần:

- Phân giải hostname theo DNS hiện tại.
- Mở TCP connection mới nếu connection cũ đã đóng hoặc stale.
- Xác thực lại.
- Kiểm tra server phản hồi.
- Xác nhận lệnh cần thiết được phép thực hiện.

Nếu Redis được đặt sau proxy hoặc managed endpoint, endpoint có thể vẫn giữ nguyên trong khi backend đã đổi. Client cần dùng cơ chế reconnect và health check phù hợp.

### 5.2. Redis Sentinel

Sentinel giám sát Redis và có thể điều phối failover để chọn primary mới. Một client giữ địa chỉ primary cũ có thể tiếp tục gửi write đến node không còn là primary.

Sau restore, client cần lấy thông tin primary hiện tại từ Sentinel hoặc cơ chế discovery của thư viện. Không nên hard-code địa chỉ node đã được biết trước checkpoint nếu hệ thống dùng failover.

Các thao tác cần kiểm tra:

- Kết nối được đến Sentinel endpoint.
- Khám phá primary hiện tại theo master name.
- Tạo connection đến primary mới.
- Xử lý replica nếu ứng dụng đọc từ replica.
- Cập nhật pool và retry các lệnh có thể gửi lại an toàn.

### 5.3. Redis Cluster

Redis Cluster phân chia keyspace thành hash slot và phân phối slot cho các node. Client thường cần topology map để định tuyến lệnh đến node sở hữu slot.

Trong thời gian checkpoint, cluster có thể reshard hoặc failover. Client cũ có thể giữ topology map đã lỗi thời. Redis có thể trả redirect như MOVED hoặc ASK; client cần xử lý theo protocol và cập nhật topology.

Sau restore:

- Kết nối seed node hoặc endpoint cluster.
- Refresh topology.
- Cập nhật slot map.
- Recreate hoặc refresh connection pool cho node cần thiết.
- Xử lý redirect và node không còn khả dụng.

API refresh topology và cách xử lý redirect phụ thuộc client. Hãy dùng tính năng cluster-aware của thư viện thay vì tự xây dựng routing nếu không có yêu cầu đặc biệt.

## 6. Authentication, TLS và secret rotation

Kết nối Redis có thể dùng ACL username/password, TLS certificate hoặc một cơ chế xác thực do nền tảng quản lý.

Trong thời gian checkpoint:

- Password có thể được rotate.
- ACL user có thể bị disable hoặc thay đổi quyền.
- Client certificate có thể hết hạn.
- Trust store có thể thay đổi.
- Secret provider có thể trả về giá trị mới.

Sau restore, client cần xác thực theo cấu hình hiện tại. Nếu vẫn dùng credential cũ được lưu trong heap, reconnect có thể thất bại.

Một số nguyên tắc:

- Đọc secret từ provider khi tạo client hoặc khi refresh credential.
- Không ghi password, token hoặc certificate private key vào log.
- Đặt connect timeout và auth timeout.
- Phân biệt lỗi authentication với lỗi mạng.
- Không retry vô hạn với credential sai.
- Nếu client không hỗ trợ đổi credential trên connection hiện có, tạo connection hoặc client mới theo hướng dẫn.

TLS cũng cần handshake mới khi tạo transport connection. Việc object client còn trong heap không chứng minh certificate hoặc TLS session cũ còn hợp lệ.

## 7. Pub/Sub và subscription sau restore

Redis Pub/Sub gửi message đến subscriber đang hoạt động tại thời điểm message được publish. Pub/Sub không phải hàng đợi bền vững: message được publish khi subscriber offline không tự động được phát lại khi subscriber kết nối lại.

Đây là điểm rất quan trọng khi dùng CRaC.

### 7.1. Điều gì xảy ra khi subscriber bị checkpoint?

Giả sử một instance subscribe channel `cache:invalidate`. Khi instance bị checkpoint:

- TCP connection có thể bị đóng hoặc mất.
- Subscription có thể bị server loại bỏ.
- Các message publish trong thời gian offline không được lưu chờ cho subscriber.
- Local cache có thể giữ entry cũ.
- Sau restore, client reconnect nhưng không tự biết các message đã bị bỏ lỡ.

Vì vậy, resubscribe là chưa đủ để bảo đảm cache nhất quán. Ứng dụng cần reconcile hoặc invalidate cache sau khi reconnect.

### 7.2. Trình tự khôi phục Pub/Sub

1. Dừng xử lý message mới trước checkpoint.
2. Chờ handler đang chạy hoàn tất.
3. Đóng Pub/Sub connection hoặc dùng CRaC integration của client.
4. Sau restore, tạo connection/subscriber mới.
5. Subscribe lại channel và pattern cần thiết.
6. Đối chiếu version hoặc invalidate local cache để xử lý message bị bỏ lỡ.
7. Chỉ mở traffic khi trạng thái cache phù hợp với chính sách.

### 7.3. Khi cần message bền vững, cân nhắc Redis Streams

Nếu ứng dụng cần đọc lại message sau thời gian offline, Redis Streams với consumer group phù hợp hơn Pub/Sub trong nhiều trường hợp. Streams lưu message theo ID và theo dõi pending entries.

Sau restore, consumer cần:

- Kết nối lại và tham gia consumer group.
- Đọc message mới theo offset phù hợp.
- Kiểm tra pending entries của consumer cũ.
- Reclaim message đã idle đủ lâu theo chính sách.
- Chỉ ACK sau khi xử lý nghiệp vụ thành công.
- Dùng idempotency để chịu được message được giao lại.

Không nên ACK message trước khi side effect nghiệp vụ đã được ghi nhận bền vững. Nếu tiến trình bị checkpoint sau khi ACK nhưng trước khi commit nghiệp vụ, message có thể bị mất khỏi góc nhìn của consumer.

## 8. Client-side caching và invalidation tracking

Một số client hoặc integration hỗ trợ client-side caching: ứng dụng giữ bản sao key trong local memory và Redis gửi invalidation khi key thay đổi.

Cơ chế này có thể giảm round trip nhưng phụ thuộc vào một kết nối tracking và việc nhận đủ invalidation.

Nếu tiến trình bị checkpoint hoặc connection tracking bị ngắt:

- Redis có thể không gửi invalidation trong thời gian client offline.
- Local cache vẫn giữ giá trị trước checkpoint.
- Sau reconnect, client có thể cần đăng ký tracking lại.
- Những invalidation đã bị bỏ lỡ không nhất thiết được phát lại.

Vì vậy, nếu không thể chứng minh client library có cơ chế resync đầy đủ, hãy xóa hoặc invalidate L1 cache sau restore trước khi dùng lại. Hoặc đối chiếu generation/version từ một nguồn đáng tin cậy.

Một chiến lược đơn giản là tăng generation khi local cache được tái lập:

~~~java
public final class LocalCacheState {
    private final AtomicLong generation = new AtomicLong();

    public long currentGeneration() {
        return generation.get();
    }

    public void invalidateAllAfterReconnect() {
        generation.incrementAndGet();
    }
}
~~~

Các entry có thể mang generation lúc được nạp. Khi đọc, ứng dụng chỉ dùng entry nếu generation của entry khớp với generation hiện tại. Đây là ví dụ về versioning trong ứng dụng; cần phối hợp với cấu trúc cache thực tế để xóa hoặc bỏ qua entry cũ.

## 9. Redis lock, transaction và lệnh có kết quả chưa xác định

Không phải mọi thao tác Redis đều có thể retry giống nhau.

### 9.1. Distributed lock

Một lock thường có lease hoặc TTL. Nếu ứng dụng bị checkpoint lâu hơn lease, lock có thể hết hạn và một instance khác có thể lấy lock. Sau restore, tiến trình cũ có thể tưởng rằng mình vẫn sở hữu lock.

Không nên tiếp tục critical section chỉ dựa trên object lock còn trong heap. Cần kiểm tra quyền sở hữu bằng token/fencing mechanism phù hợp. Với thao tác quan trọng, fencing token giúp hệ thống đích từ chối writer cũ khi đã có owner mới.

Trước checkpoint, nên kết thúc critical section và giải phóng lock nếu có thể. Nếu lock không thể giải phóng do kết nối đã mất, đợi lease hết hạn và không tiếp tục công việc dựa trên quyền sở hữu cũ.

### 9.2. MULTI/EXEC và transaction

Một transaction Redis đang mở hoặc pipeline có command chưa nhận response có thể có kết quả không xác định khi connection mất. Không nên giữ trạng thái transaction cũ qua restore và giả định có thể tiếp tục.

Trước checkpoint, hoàn tất hoặc hủy transaction theo API của client. Nếu không biết EXEC đã được Redis thực thi hay chưa, hãy kiểm tra trạng thái dữ liệu bằng operation ID hoặc thiết kế idempotent.

### 9.3. Retry lệnh ghi

Nếu client gửi SET, INCR hoặc một Lua script nhưng connection bị reset trước khi nhận response, server có thể đã thực hiện lệnh. Retry có thể tạo tác dụng phụ lần thứ hai, đặc biệt với INCR, LPUSH hoặc thao tác cập nhật không idempotent.

Ví dụ:

1. Client gửi INCR `counter`.
2. Redis thực hiện và tăng counter.
3. Response bị mất trước khi client nhận.
4. Client reconnect và gửi lại INCR.
5. Counter tăng hai lần.

Với thao tác có thể lặp, dùng request ID, idempotency key, Lua script có kiểm tra ID hoặc một mô hình dữ liệu cho phép deduplication.

## 10. Chiến lược retry và backoff

Sau restore, Redis có thể chưa sẵn sàng ngay. Có thể đang failover, khởi động lại hoặc cập nhật topology. Retry cần có giới hạn và không tạo một đợt reconnect đồng loạt quá lớn.

### 10.1. Exponential backoff và jitter

Một lịch retry minh họa:

| Lần thử | Khoảng chờ |
|---|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.6 s |
| 5 | 3.2 s |

Nên đặt mức chờ tối đa và thêm jitter ngẫu nhiên. Nếu nhiều instance restore cùng lúc, jitter giúp tránh tất cả client cùng reconnect trong một thời điểm.

### 10.2. Phân loại lỗi

| Lỗi | Cách xử lý |
|---|---|
| Connection refused hoặc timeout | Retry có backoff |
| Connection reset | Tạo connection mới; đánh giá kết quả lệnh trước |
| MOVED hoặc ASK | Dùng cluster-aware client để cập nhật routing |
| Authentication failure | Refresh credential hoặc báo lỗi cấu hình |
| TLS handshake failure | Kiểm tra certificate, trust store và thời hạn |
| NOAUTH / NOPERM | Kiểm tra ACL và quyền command |
| OOM hoặc giới hạn tài nguyên Redis | Không retry dồn dập; xử lý capacity |
| Wrong type hoặc lỗi dữ liệu | Sửa logic hoặc dữ liệu; retry không giải quyết nguyên nhân |

Không nên retry vô hạn các lỗi cấu hình, ACL hoặc dữ liệu. Circuit breaker và giới hạn thời gian phục hồi giúp bảo vệ Redis khỏi một vòng lặp request thất bại.

### 10.3. Fallback khi Redis chưa sẵn sàng

Fallback có thể là:

- Trả dữ liệu từ database.
- Dùng local cache còn hợp lệ.
- Trả lỗi tạm thời.
- Giữ readiness NOT_READY.
- Tạm ngừng xử lý job cần Redis.

Không phải ứng dụng nào cũng nên fallback sang database. Nếu Redis được dùng để giảm tải cho database, việc mọi instance cùng fallback sau restore có thể tạo database stampede. Với dữ liệu permission, session hoặc distributed lock, fallback sai có thể gây lỗi bảo mật hoặc tính nhất quán.

## 11. Tích hợp Redis client với CRaC Resource

Một cách tổ chức là dùng một resource sở hữu Redis runtime. Resource chịu trách nhiệm dừng hoạt động, đóng runtime cũ và tạo runtime mới sau restore.

Ví dụ dưới đây sử dụng abstraction do ứng dụng định nghĩa để tránh gắn lifecycle vào API riêng của một thư viện:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RedisCheckpointResource implements Resource {

    private final RedisRuntimeFactory runtimeFactory;
    private final RedisWorkCoordinator workCoordinator;
    private final CacheReconciler cacheReconciler;

    private volatile RedisRuntime runtime;

    public RedisCheckpointResource(
            RedisRuntimeFactory runtimeFactory,
            RedisWorkCoordinator workCoordinator,
            CacheReconciler cacheReconciler) throws Exception {

        this.runtimeFactory = runtimeFactory;
        this.workCoordinator = workCoordinator;
        this.cacheReconciler = cacheReconciler;

        this.runtime = runtimeFactory.createAndConnect();
        this.runtime.verifyReady();

        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        // Không nhận thêm công việc dùng Redis.
        workCoordinator.stopAccepting();

        // Hoàn tất command đang chạy và xử lý message theo policy.
        workCoordinator.drainInFlight();

        // Dừng Pub/Sub listener và consumer trước khi đóng transport.
        workCoordinator.stopListenersAndConsumers();

        RedisRuntime oldRuntime = runtime;
        runtime = null;

        if (oldRuntime != null) {
            oldRuntime.close();
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        RedisRuntime newRuntime = runtimeFactory.createAndConnect();

        try {
            newRuntime.verifyReady();

            // Reconcile local cache vì có thể bỏ lỡ invalidation.
            cacheReconciler.reconcile(newRuntime);

            // Khôi phục subscription/consumer sau khi connection sẵn sàng.
            newRuntime.restoreSubscriptionsAndConsumers();

            runtime = newRuntime;
            workCoordinator.attach(newRuntime);
            workCoordinator.resumeAccepting();

        } catch (Exception e) {
            newRuntime.close();
            workCoordinator.markUnavailable();
            throw e;
        }
    }
}
~~~

Các kiểu RedisRuntimeFactory, RedisWorkCoordinator, CacheReconciler và RedisRuntime là abstraction do ứng dụng định nghĩa, không phải class của Lettuce, Jedis hay CRaC.

Ví dụ thể hiện thứ tự trách nhiệm:

1. Dừng nhận công việc mới.
2. Drain lệnh và handler đang chạy.
3. Dừng listener và consumer.
4. Đóng client runtime cũ.
5. Sau restore, tạo runtime mới và xác nhận kết nối.
6. Reconcile local cache.
7. Khôi phục subscription/consumer.
8. Mở lại admission.

Trong production, các bước cần timeout và xử lý lỗi cụ thể. Nếu reconnect thất bại, ứng dụng không được mở traffic dùng Redis. Cần có readiness hoặc trạng thái degraded tương ứng.

### 11.1. Lưu ý về lỗi trong beforeCheckpoint()

Nếu một bước chuẩn bị thất bại sau khi admission đã dừng hoặc listener đã đóng, ứng dụng phải có đường phục hồi. CRaC Resource cung cấp callback trước checkpoint và sau restore; không nên giả định có callback afterCheckpoint tự động mở lại các thành phần nếu quá trình tạo checkpoint bị hủy.

Nếu ứng dụng chủ động yêu cầu checkpoint, coordinator ở tầng gọi có thể bắt lỗi và thực hiện rollback: tạo lại Redis runtime, resubscribe, reconcile cache rồi mới mở admission. Nếu không thể phục hồi, giữ instance ở trạng thái unavailable.

### 11.2. Tránh đóng trùng resource

Nếu thư viện đã có CRaC integration, nó có thể tự đăng ký resource cho connection hoặc event loop. Không nên tạo một resource khác đóng cùng connection và pool nếu không có ownership rõ ràng.

Hãy chọn một owner duy nhất cho từng thành phần:

- Client runtime sở hữu event loop.
- Pool sở hữu các connection pooled.
- Subscription manager sở hữu listener.
- Cache manager sở hữu local cache.
- Lifecycle coordinator điều phối thứ tự tổng thể.

## 12. Ví dụ với Lettuce và Jedis

Hai thư viện phổ biến có mô hình sử dụng khác nhau. Chi tiết API có thể thay đổi theo phiên bản, vì vậy cần đối chiếu tài liệu đúng version.

### 12.1. Lettuce

Lettuce sử dụng Netty và hỗ trợ API đồng bộ, bất đồng bộ và reactive. Một số connection của Lettuce có thể được chia sẻ giữa nhiều thread theo contract của thư viện. ClientResources quản lý các resource nền như event loop.

Khi tích hợp CRaC, cần xem xét:

- Stateful connection có đang được dùng bởi request nào không.
- ClientResources và event loop được sở hữu bởi ai.
- Có thể đóng connection riêng hay cần shutdown client.
- Reconnect được bật và cấu hình như thế nào.
- Cluster topology refresh hoạt động ra sao.
- Pub/Sub connection có cần tạo lại và subscribe lại không.
- Client-side caching có cần invalidate sau khi tracking connection bị mất không.

Nếu shutdown RedisClient hoặc ClientResources, không nên giả định có thể gọi lại connect trên cùng object đã shutdown. Có thể cần factory tạo client và resource manager mới sau restore.

### 12.2. Jedis

Jedis thường được dùng theo mô hình connection pool. Jedis instance được mượn từ pool cho một thao tác hoặc một scope ngắn và không nên chia sẻ đồng thời giữa nhiều thread.

Cần xem xét:

- Không có connection nào đang được mượn khi đóng pool.
- Borrower luôn trả connection về pool.
- Pool được tạo mới sau khi shutdown nếu implementation không hỗ trợ reopen.
- Sentinel hoặc Cluster configuration được dùng để khám phá topology hiện tại.
- Pub/Sub listener được dừng và tạo lại.
- Các connection stale được loại bỏ theo chính sách của pool.

Ví dụ lấy connection theo scope:

~~~java
try (Jedis jedis = jedisPool.getResource()) {
    jedis.set("warmup:status", "ready");
}
~~~

Đoạn code minh họa việc mượn và trả resource. Không dùng một Jedis instance làm field dùng chung cho nhiều thread. Việc đóng JedisPool là thao tác lifecycle cấp pool, cần được điều phối riêng.

### 12.3. Redisson và các client khác

Redisson cung cấp abstraction cao hơn cho map, lock, topic, semaphore và nhiều cấu trúc phân tán. Các object như RMap hoặc RLock thường phụ thuộc vào RedissonClient và kết nối nền.

Sau restore, cần xác định:

- RedissonClient có CRaC integration tương ứng không.
- Netty/event loop có được phục hồi đúng không.
- Lock lease còn hợp lệ không.
- Topic listener cần đăng ký lại không.
- Local cached map có cần invalidate không.
- Client shutdown có thể được thay bằng client mới thế nào.

Không nên giả định một API object như RMap có thể tiếp tục hoạt động chỉ vì reference của nó còn trong heap.

## 13. Khôi phục Pub/Sub, Streams và cache listener

Các loại hoạt động liên tục cần quy trình riêng.

| Chức năng | Trước checkpoint | Sau restore |
|---|---|---|
| Pub/Sub | Dừng handler, unsubscribe/close connection | Subscribe lại; reconcile event bị bỏ lỡ |
| Keyspace notifications | Dừng subscriber | Subscribe lại; không coi notification là durable log |
| Redis Streams | Dừng đọc, xử lý và ACK theo policy | Join consumer group, kiểm tra pending và reclaim |
| Client-side invalidation | Dừng tracking listener | Recreate tracking; invalidate hoặc resync L1 |
| Scheduled refresh | Pause scheduler và drain task | Tính lại lịch, tạo scheduler mới nếu cần |

### 13.1. Pub/Sub không lưu message cho subscriber offline

Nếu ứng dụng cần đảm bảo xử lý mọi sự kiện trong lúc checkpoint, Pub/Sub có thể không đáp ứng yêu cầu. Cân nhắc Streams hoặc một message broker bền vững. Nếu vẫn dùng Pub/Sub để invalidation, hãy kết hợp version hoặc invalidate toàn bộ nhóm key khi reconnect.

### 13.2. Streams và pending entries

Redis Streams consumer group theo dõi message đã được giao nhưng chưa ACK. Sau restore, message có thể còn trong pending entries của consumer cũ.

Cần có quy trình:

- Xem pending count.
- Xác định consumer nào giữ message.
- Reclaim message đã idle đủ lâu.
- Xử lý lại bằng handler idempotent.
- ACK sau khi nghiệp vụ đã hoàn tất bền vững.

Không nên chỉ tạo consumer mới và đọc message mới mà bỏ qua pending entries cũ.

## 14. Tính nhất quán cache sau khi reconnect

Kết nối Redis đã sẵn sàng không có nghĩa local cache đã đồng bộ. Ứng dụng cần chọn một trong các cách:

### 14.1. Invalidate toàn bộ L1

Đơn giản và an toàn khi cache nhỏ, dữ liệu có thể nạp lại và không có version đáng tin cậy. Sau restore, xóa local cache rồi tải lại theo nhu cầu.

### 14.2. Invalidate theo namespace

Nếu chỉ một nhóm dữ liệu nhận invalidation event bị bỏ lỡ, xóa namespace tương ứng. Cách này giảm cache miss so với xóa toàn bộ.

### 14.3. Version hoặc generation

Lưu version của dữ liệu trong Redis hoặc database. Sau restore, đọc generation hiện tại và so sánh với generation cache. Nếu khác, bỏ qua entry cũ.

### 14.4. TTL và lazy refresh

Giữ entry còn TTL nếu chính sách freshness cho phép. Entry hết hạn sẽ được refresh khi có request. Cần single-flight để tránh nhiều request cùng refresh một key.

### 14.5. Không dùng cache stale cho quyết định nhạy cảm

Permission, token, session, số dư hoặc trạng thái lock cần chính sách nghiêm ngặt. Nếu không xác định được dữ liệu còn hợp lệ, hãy kiểm tra nguồn hoặc từ chối thao tác thay vì dùng stale value.

## 15. Quan sát và kiểm thử

Nên ghi nhận các trạng thái sau:

- Redis checkpoint preparation started.
- Redis work drained.
- Pool borrowers returned.
- Client runtime closed.
- Redis reconnect started/completed.
- Authentication và TLS thành công.
- Cluster/Sentinel topology refreshed.
- Pub/Sub resubscribed.
- Streams pending entries reconciled.
- Local cache invalidated hoặc version verified.
- Redis readiness changed.

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| Connection active/idle | Quan sát pool và connection đang dùng |
| Reconnect attempts | Theo dõi phục hồi transport |
| Reconnect duration | Đo thời gian thiết lập lại kết nối |
| Command timeout/error rate | Phát hiện lệnh thất bại |
| Pool borrow wait | Phát hiện pool thiếu connection |
| Topology refresh count | Theo dõi Sentinel/Cluster thay đổi |
| Pub/Sub reconnect count | Phát hiện subscriber bị ngắt |
| Stream pending count | Theo dõi message chưa ACK |
| Cache invalidation count | Đo dữ liệu L1 bị xóa |
| Time to Redis ready | Đo thời gian đến khi Redis sẵn sàng |
| Restore-to-application-ready | Đo thời gian từ restore đến nhận traffic |

Nên kiểm thử:

1. Restore ngay sau checkpoint khi Redis không thay đổi.
2. Restore sau thời gian dài hơn idle timeout.
3. Redis restart trong thời gian checkpoint.
4. Sentinel failover sang primary mới.
5. Cluster topology thay đổi hoặc slot được chuyển.
6. ACL password hoặc TLS certificate được rotate.
7. Pub/Sub message được publish khi subscriber offline.
8. Client-side invalidation bị gián đoạn.
9. Stream consumer có pending entries.
10. Một lệnh ghi đã được thực thi nhưng response bị mất.
11. Reconnect thất bại tạm thời rồi thành công.
12. Nhiều instance restore đồng thời và cùng reconnect.
13. Redis không sẵn sàng trong thời gian vượt timeout.
14. Cache local chứa version cũ sau khi Redis đã cập nhật.

Mục tiêu là chứng minh ứng dụng reconnect đúng endpoint, xác thực đúng, khôi phục subscription, không bỏ qua pending work và không phục vụ local cache stale ngoài chính sách.

## 16. Quy trình triển khai đề xuất

### Trước checkpoint

1. Chuyển readiness sang NOT_READY nếu request cần Redis.
2. Ngừng nhận request và job mới dùng Redis.
3. Pause cache refresh scheduler.
4. Dừng Pub/Sub handler và Streams consumer.
5. Drain lệnh đang chạy và trả connection đã mượn về pool.
6. Hoàn tất transaction hoặc xử lý trạng thái command chưa xác định.
7. Đóng Redis client/pool/resource theo hướng dẫn của thư viện hoặc CRaC integration.
8. Để CRaC tiếp tục tạo checkpoint.

### Sau restore

1. Đọc cấu hình và secret hiện tại.
2. Tạo client, event loop và connection pool mới nếu cần.
3. Kết nối và xác thực với Redis.
4. Refresh Sentinel/Cluster topology.
5. Kiểm tra khả năng thực hiện command thiết yếu.
6. Khôi phục Pub/Sub subscription và Streams consumer.
7. Reconcile hoặc invalidate local cache.
8. Khởi động lại scheduler và background refresh.
9. Chuyển readiness sang READY.

Nếu Redis là dependency tùy chọn cho một số endpoint, có thể dùng readiness theo capability hoặc degraded mode. Nhưng những request cần Redis phải có fallback rõ ràng và an toàn.

## 17. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng lại socket cũ mà không kiểm tra | Command timeout hoặc reset | Reconnect/recreate theo client lifecycle |
| Đóng pool khi borrower còn hoạt động | Request thất bại giữa chừng | Ngừng admission và drain borrower |
| Dùng lại client đã shutdown | Không tạo được connection mới | Tạo client runtime mới |
| Chỉ dựa vào auto reconnect | Mất subscription hoặc stale cache | Resubscribe và reconcile state |
| Không refresh Cluster topology | Gửi command đến node cũ | Dùng cluster-aware topology refresh |
| Dùng credential lưu trong heap quá lâu | Authentication failure | Đọc secret mới và xác thực lại |
| Bỏ qua Pub/Sub message khi offline | Local cache không được invalidate | Version check hoặc invalidate L1 |
| Không xử lý Streams pending | Message bị treo hoặc xử lý thiếu | Reclaim và xử lý idempotent |
| Retry INCR hoặc write mù quáng | Tác dụng phụ bị lặp | Idempotency key hoặc kiểm tra kết quả |
| Dùng lock cũ sau restore | Critical section chạy khi đã mất lease | Kiểm tra ownership/fencing token |
| Mở traffic trước khi Redis sẵn sàng | Request lỗi hàng loạt | Readiness gate và timeout |
| Tất cả instance reconnect cùng lúc | Redis quá tải | Backoff, jitter và giới hạn concurrency |

## 18. Checklist Redis client cho CRaC

### Ownership và connection

- [ ] Xác định Redis client, pool, event loop và listener do ai sở hữu.
- [ ] Không còn connection đang được mượn khi đóng pool.
- [ ] Client đã shutdown được tạo lại thay vì cố dùng lại.
- [ ] Đã kiểm tra CRaC integration của đúng phiên bản thư viện.
- [ ] Có timeout cho connect, command và pool borrow.

### Reconnect và topology

- [ ] Hostname được resolve theo cấu hình hiện tại.
- [ ] Sentinel primary hoặc Cluster topology được refresh.
- [ ] ACL và TLS được xác thực lại.
- [ ] Retry có giới hạn, backoff và jitter.
- [ ] Lỗi cấu hình/authentication được phân loại riêng.

### Subscription và dữ liệu

- [ ] Pub/Sub listener được đăng ký lại.
- [ ] Cache invalidation bị bỏ lỡ được reconcile.
- [ ] Streams pending entries được kiểm tra và reclaim theo policy.
- [ ] Local cache được invalidate hoặc kiểm tra version.
- [ ] Redis lock không được coi là còn sở hữu chỉ vì object còn trong heap.
- [ ] Lệnh ghi có cơ chế idempotency khi cần.

### Readiness và vận hành

- [ ] Không nhận traffic trước khi Redis dependency thiết yếu sẵn sàng.
- [ ] Có metric reconnect, pool, command error và readiness.
- [ ] Có chính sách fallback không gây database stampede.
- [ ] Đã thử failover, restart, credential rotation và restore dài hạn.
- [ ] Đã thử nhiều instance reconnect đồng thời.

## 19. Câu hỏi thường gặp

### Redis client object còn trong heap sau restore có nghĩa kết nối còn hoạt động không?

Không. Object còn tồn tại chỉ phản ánh trạng thái trong tiến trình. TCP socket, Redis server, proxy, network path và protocol state có thể đã thay đổi. Cần xác nhận kết nối hoặc tạo lại theo lifecycle của client.

### Automatic reconnect của Lettuce hoặc client khác có đủ không?

Không nên mặc định như vậy. Automatic reconnect có thể xử lý transport interruption, nhưng subscription, topology, pending command, client-side cache invalidation và nghiệp vụ cần được phục hồi theo chính sách riêng. Hãy kiểm tra đúng phiên bản và CRaC support của thư viện.

### Có nên shutdown RedisClient trong beforeCheckpoint() không?

Nếu ứng dụng sở hữu client và thư viện yêu cầu tạo instance mới sau shutdown, đây có thể là chiến lược phù hợp. Trước đó cần drain mọi lệnh và listener đang sử dụng client. Nếu thư viện có CRaC integration, hãy theo đúng lifecycle mà integration quy định để tránh đóng trùng.

### Pub/Sub có gửi lại message bị bỏ lỡ khi reconnect không?

Không. Redis Pub/Sub không lưu message cho subscriber offline. Nếu cần xử lý sự kiện sau khi reconnect, dùng Streams hoặc một nguồn event bền vững; với invalidation, có thể đối chiếu version hoặc xóa local cache.

### Redis Streams có cần xử lý gì sau restore không?

Có. Consumer cần tham gia lại group, kiểm tra pending entries và reclaim message đã idle theo chính sách. Chỉ ACK sau khi công việc nghiệp vụ đã hoàn tất bền vững và handler nên idempotent.

### Có nên giữ local cache sau khi Redis reconnect?

Chỉ khi có thể chứng minh entry còn hợp lệ bằng TTL, version hoặc một cơ chế invalidation đáng tin cậy. Nếu tracking connection bị mất và có thể bỏ lỡ event, invalidate hoặc reconcile L1 trước khi dùng lại.

### Nếu Redis chưa sẵn sàng sau restore thì ứng dụng nên làm gì?

Giữ readiness ở trạng thái không sẵn sàng cho các chức năng phụ thuộc Redis, retry có giới hạn và ghi nhận lỗi. Chỉ dùng fallback nếu dữ liệu và nghiệp vụ cho phép; tránh dồn toàn bộ tải sang database.

### Có thể retry mọi lệnh Redis sau Connection reset không?

Không. Một lệnh có thể đã được Redis thực thi nhưng response bị mất. Retry INCR, LPUSH hoặc một thao tác không idempotent có thể tạo tác dụng phụ hai lần. Cần idempotency key, operation ID hoặc kiểm tra trạng thái trước khi gửi lại.

### Distributed lock có còn hợp lệ sau restore không?

Không nên giả định. Lease có thể đã hết và một instance khác có thể đã lấy lock. Cần xác minh ownership hoặc dùng fencing token trước khi tiếp tục critical section.

## Kết luận

Redis client là một tập hợp resource gồm connection, pool, event loop, topology, subscription và trạng thái cache. Sau CRaC restore, các object này có thể còn trong heap trong khi Redis server, network path, credential, subscription hoặc dữ liệu đã thay đổi.

Một quy trình an toàn là dừng công việc dùng Redis và drain connection trước checkpoint, sau đó tạo hoặc reconnect client theo đúng contract của thư viện, xác thực lại, refresh topology, resubscribe và reconcile local cache. Pub/Sub message có thể bị bỏ lỡ; Streams cần xử lý pending entries; lệnh ghi cần idempotency; distributed lock cần xác minh lease. Chỉ mở readiness khi Redis và các chức năng thiết yếu đã sẵn sàng.
