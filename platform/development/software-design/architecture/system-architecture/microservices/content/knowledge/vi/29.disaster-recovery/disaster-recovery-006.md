# Chuyển vùng, failover và nguy cơ nhiều bên cùng nhận quyền ghi

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Khôi phục thảm họa.  
> **Mục tiêu:** thiết kế chuyển vùng an toàn khi hạ tầng gặp sự cố, hiểu sự khác biệt giữa chuyển traffic và chuyển quyền ghi, ngăn **split-brain** bằng quorum/fencing, kiểm soát replication lag, RPO/RTO, và thực hiện failover, đối soát, failback có bằng chứng.

## 1. Bài toán: hai vùng đều tưởng mình là primary

Một hệ thống thương mại điện tử có hai vùng triển khai:

- **Region A:** vùng chính chạy Order Service, Payment Service, Inventory Service và các database writer.
- **Region B:** vùng dự phòng với replica dữ liệu, compute, broker và hạ tầng cần thiết.
- **Global routing:** DNS hoặc global load balancer đưa request đến vùng được phép phục vụ.
- **Data replication:** dữ liệu từ A được gửi sang B qua cơ chế replication của database.

Lúc 10:00, kết nối giữa A và B gặp sự cố. B không thấy heartbeat từ A và cho rằng A đã ngừng hoạt động. Hệ thống promote replica ở B lên writer, rồi chuyển traffic sang B.

Nhưng A thực sự vẫn chạy: một số client giữ DNS cache cũ, kết nối TCP còn mở, webhook của đối tác vẫn đến URL A, và background worker còn tiếp tục xử lý. Nếu A và B đều có quyền ghi vào bản sao dữ liệu riêng, hệ thống có thể xuất hiện:

- Hai Order cùng dùng idempotency key nhưng payload hoặc trạng thái khác nhau.
- Một sản phẩm còn 1 chiếc nhưng hai vùng đều xác nhận giữ hàng.
- Payment đã charge ở A nhưng B không có record do replication lag.
- Hai event streams phát ra các sự kiện mâu thuẫn.
- Một người dùng được báo thành công ở cả hai vùng nhưng không thể hòa giải bằng timestamp.

Đây là **split-brain**: nhiều thành phần cùng hành động như leader/writer hợp lệ cho cùng dữ liệu khi không có sự phối hợp hoặc fencing đủ mạnh.

**Thông điệp chính:** Không liên lạc được với Region A **không chứng minh A đã chết**. Thay traffic sang B không bảo đảm old writer ở A đã mất quyền. Khôi phục an toàn phải xét quyền ghi, độ mới dữ liệu và side effects.

## 2. Thuật ngữ quan trọng

| Thuật ngữ | Giải thích | Điều dễ nhầm |
| --- | --- | --- |
| **Region** | Vùng triển khai hạ tầng tương đối độc lập | Hai region không mặc định đồng bộ dữ liệu |
| **AZ / failure domain** | Một miền có thể lỗi độc lập | Mất node/AZ khác với mất cả region |
| **Failover** | Chuyển phục vụ từ nơi lỗi sang nơi thay thế | Không chỉ là cập nhật DNS |
| **Failback** | Đưa quyền phục vụ về nơi cũ sau khi phục hồi | Cần chuyển quyền ghi như một đợt mới |
| **Active-passive** | Một primary, vùng còn lại dự phòng | Passive vẫn có thể chạy replica/read |
| **Active-active** | Hai hay nhiều vùng cùng phục vụ | Không nhất thiết cùng ghi mọi record |
| **Single writer** | Một authority ghi một tập dữ liệu tại một thời điểm | Có thể có nhiều read replicas |
| **Multi-writer** | Nhiều vùng ghi đồng thời theo thiết kế | Phải giải quyết consistency/conflicts |
| **Split-brain** | Nhiều phía cùng tin mình là writer hợp lệ | Có thể tạo dữ liệu phân kỳ |
| **Quorum** | Nhóm đủ phiếu để quyết định theo giao thức | Health check không thay quorum |
| **Fencing** | Vô hiệu hóa khả năng ghi của writer cũ | Đổi route không phải fencing |
| **Epoch/term** | Thế hệ tăng đơn điệu của quyền lãnh đạo | Storage phải từ chối epoch cũ |
| **Replication lag** | Độ trễ bản sao theo log/transaction | Follower Ready chưa chắc đủ dữ liệu |
| **RPO** | Mức mất dữ liệu tối đa có thể chấp nhận | Không tự bằng 0 nếu có replica |
| **RTO** | Thời gian phục hồi mục tiêu | Phải đo qua diễn tập thật |

## 3. Mục tiêu: safety, availability và recoverability

Có ba mục tiêu cần phân biệt:

**Safety (an toàn):** không có hai writer cam kết những thay đổi mâu thuẫn trên cùng phạm vi dữ liệu. Một payment không được charge hai lần chỉ vì retry sang region khác.

**Availability (khả dụng):** service còn có thể nhận và hoàn thành request trong giới hạn SLO khi một phần hạ tầng lỗi.

**Recoverability (khả năng khôi phục):** có thể đưa dịch vụ và dữ liệu về trạng thái nghiệp vụ hợp lệ, kể cả khi phải restore, replay hoặc bù trừ.

Trong network partition, một hệ thống cần **single-writer consistency** có thể buộc vùng không có quorum hoặc authority dừng nhận write. Đây là lựa chọn bảo vệ dữ liệu, dù làm giảm availability của vùng đó.

Nếu muốn cả hai vùng tiếp tục ghi khi partition, dữ liệu phải có cơ chế phân quyền theo shard hoặc mô hình multi-writer giải quyết xung đột được thiết kế rõ. Không thể nhận đồng thời ba lời hứa: luôn writable ở cả hai nơi khi mất mạng, không có phối hợp, và luôn giữ bất biến chung tuyệt đối.

## 4. RPO và RTO phải xuất phát từ nghiệp vụ

**Recovery Point Objective (RPO)** là độ lùi dữ liệu có thể chấp nhận sau sự cố. **Recovery Time Objective (RTO)** là thời gian mục tiêu để khôi phục chức năng.

Ví dụ minh họa:

| Luồng | RTO mục tiêu | RPO cần cân nhắc |
| --- | --- | --- |
| Nội dung sản phẩm và gợi ý | Vài chục phút đến vài giờ | Có thể tái tạo từ nguồn gốc |
| Checkout API | Mục tiêu ngắn theo hoạt động kinh doanh | Dữ liệu tạo đơn cần đối soát |
| Payment ledger | Phục hồi theo quy trình kiểm soát tài chính | Không tự chấp nhận mất giao dịch |
| Analytics read model | Có thể chịu chậm lâu hơn | Rebuild từ event/source |
| Search index | Tùy UX | Có thể tái tạo nếu nguồn còn |

Các giá trị là định hướng; tổ chức phải đặt con số cụ thể theo nhu cầu. Không được tuyên bố RPO=0 chỉ vì replication bật hoặc có ba replica.

Khi diễn tập, đo **RTO thực tế** từ lúc chức năng mất phục vụ đến lúc phục vụ đúng trở lại, và **RPO thực tế** theo log position hoặc record thực sự thiếu. Một HTTP health endpoint trả 200 không chứng minh dữ liệu hoàn chỉnh.

## 5. Kiến trúc multi-region cơ bản

Sơ đồ logic:

    Client / Partner
            |
     Global DNS / LB
        /         \
    Region A     Region B
      API A        API B
        |            |
    DB Primary A <-> DB Replica B
        |            |
    Broker A      Broker B
        \            /
       External payments
       
    Coordination / authority / cluster manager
       -> quản lý leader, term, fencing
       
    Backup tách failure domain
       -> khả năng restore/PITR

Sơ đồ không nói rằng mọi database đều cần một coordination service bên ngoài. Một số distributed databases có consensus tích hợp; một số relational HA setups cần cluster manager. Điều quan trọng là **giao thức cụ thể** có bảo đảm một writer hợp lệ trong phạm vi được định nghĩa.

Đừng gộp các lớp:

- Routing quyết định request đi vùng nào.
- Scheduler quyết định process chạy ở đâu.
- Database authority quyết định write nào được commit.
- Replication quyết định dữ liệu nào được sao chép.
- Backup quyết định điểm lịch sử nào có thể khôi phục.

Một lớp không tự hoàn thành trách nhiệm của lớp khác.

## 6. Các mô hình triển khai DR

### Cold standby

Region B chỉ giữ backup, image và hạ tầng tối thiểu. Khi outage, phải dựng compute, restore database và cấu hình routing. Chi phí thường thấp hơn nhưng RTO có thể dài, phụ thuộc thời gian khôi phục và quota cấp phát.

### Warm standby

Region B có một số service và replica dữ liệu, cần promote và scale. RTO thường ngắn hơn cold standby, nhưng replication lag, việc tạo writer và traffic switch vẫn có rủi ro.

### Hot standby

Region B gần sẵn sàng nhận traffic; compute và data replica hoạt động. Tuy nhiên **hot standby không tự loại split-brain**. Vẫn phải quản lý quyền writer.

### Active-active reads, single-writer writes

A/B có thể cùng trả dữ liệu đọc với freshness phù hợp, nhưng writes của cùng một dữ liệu đi tới writer duy nhất. Phải xử lý stale reads, read-your-writes và partition.

### Active-active multi-writer

Hai vùng được phép tạo thay đổi ở cùng hoặc các phần dữ liệu theo thiết kế. Cần định nghĩa consistency, conflict resolution, uniqueness, quota và side effects. Đây là mô hình khác về cả domain lẫn vận hành, không phải chỉ tăng một số replica.

## 7. Network partition khác region outage hoàn toàn

Khi region thật sự tắt, process cũ không còn chạy. Khi **network partition**, region có thể vẫn khỏe đối với client của nó nhưng không liên lạc với region khác. Tín hiệu như ping timeout hoặc heartbeat missing chỉ là quan sát từ một vị trí, không phải bằng chứng process đã dừng.

Kịch bản:

    10:00 A và B mất liên lạc.
    10:01 Client X vẫn gọi A.
    10:02 Client Y chỉ gọi được B.
    10:03 Hệ thống B nghĩ A đã chết.
    10:04 Nếu B tự promote mà không fence A,
          cả A và B có thể nhận write.

Một failure detector nhạy có thể rút ngắn thời gian phát hiện outage thật nhưng tăng false positives khi mạng nhiễu. Quorum/fencing tách **quyết định cấp quyền** khỏi một tín hiệu sức khỏe không đáng tin.

## 8. Những nguồn gây split-brain

1. **Partition:** A còn sống nhưng B không thấy.
2. **Leader lease stale:** A mất lease nhưng vẫn ghi vào database.
3. **GC pause:** A kiểm tra quyền rồi bị pause, B nhận quyền mới, A tỉnh lại và ghi tiếp.
4. **Restart từ disk:** A phục hồi đọc cấu hình local còn isPrimary=true.
5. **Manual và automation cùng promote:** hai quy trình không chia sẻ state machine.
6. **Two independent databases:** mỗi bên tự giữ bảng writer_authority local.
7. **Stale DNS/cache:** client tiếp tục gửi request đến A.
8. **Background jobs:** job scheduler hoặc consumer ở A tiếp tục chạy dù request traffic đã chuyển.
9. **Failback không có quy trình:** khi A hồi phục, nó tự nhận lại writer.
10. **Uncontrolled multi-master replication:** dữ liệu nhận từ nhiều writer không có conflict model.

Điểm chung là **thẩm quyền ghi không được bảo vệ tại nơi thực sự commit data**.

## 9. Quorum và majority

Trong mô hình majority quorum với N voters:

\[
Q = \left\lfloor\frac{N}{2}\right\rfloor + 1
\]

- N=3 cần 2 phiếu.
- N=5 cần 3 phiếu.
- N=2 cần 2 phiếu theo majority thông thường.

Hai region, mỗi region có một voter, khi partition sẽ không bên nào tự đạt majority. Có thể dùng voter thứ ba/witness ở failure domain độc lập, tùy giao thức.

    Region A voter --- Third-domain witness
           \               /
            \             /
             Region B voter

Witness phải tham gia consensus/leader protocol; một service chỉ trả lời “A đang sống” chưa đủ. Việc bố trí voter phải xét mất zone, mất region và network partition, không chỉ số node chẵn hay lẻ.

**Quorum không tự chặn ghi tại database ngoài giao thức.** Nếu A không còn majority nhưng vẫn có thể ghi trực tiếp vào một database độc lập, phải thêm fencing hoặc bảo vệ tương đương.

## 10. Fencing là gì?

**Fencing** ngăn writer đã mất quyền tiếp tục ảnh hưởng tới dữ liệu quan trọng:

- **Storage fencing:** backend từ chối một node/process đã mất quyền.
- **Database cluster semantics:** chỉ writer được leader/quorum cấp quyền mới commit theo giao thức.
- **STONITH/power fencing:** cách ly hoặc tắt node cũ theo cơ chế được hỗ trợ.
- **Credential/network fencing:** thu hồi đường ghi khi có thể chứng minh hiệu lực.
- **Fencing token:** mỗi lần chuyển quyền cấp epoch tăng đơn điệu; nơi ghi từ chối token cũ.

Không coi việc xóa Pod hoặc chuyển DNS là fencing nếu old region unreachable. Có thể lệnh điều khiển chưa tới Pod, process vẫn chạy, hoặc client còn dùng connection cũ.

### 10.1. Epoch tăng đơn điệu

    Epoch 41: A có quyền ghi.
    Epoch 42: B được cấp quyền ghi.
    Write mang epoch 41 -> bị chặn tại storage.
    Write mang epoch 42 -> được xét theo contract.

Điều kiện an toàn:

1. Authority cấp epoch phải **nhất quán và bền**, không tự tăng riêng từng region.
2. Epoch tăng theo lần chuyển owner.
3. Mọi đường ghi có hiệu lực đều bị ràng buộc bởi epoch.
4. Check epoch và write phải atomic hoặc có cơ chế storage/database tương đương.
5. Writer cũ không thể tự nâng epoch.
6. Không có thẩm quyền/quorum thì không nhận writes yêu cầu single-writer safety.

Một biến boolean **isLeader** trong RAM không phải fencing.

## 11. Ví dụ Java: contract bắt buộc tại write boundary

Một abstraction Java giúp thể hiện yêu cầu:

    public record WriterPermit(
        String partitionId,
        String regionId,
        long epoch
    ) {}

    public record CreateOrder(
        String orderId,
        long totalMinor,
        String currency
    ) {}

    public interface FencedOrderStore {
        // Check authority và commit phải được bảo vệ atomic
        // tại authoritative storage, không chỉ kiểm tra local.
        void insertOrder(WriterPermit permit, CreateOrder command);
    }

    public final class OrderWriter {
        private final FencedOrderStore store;

        public OrderWriter(FencedOrderStore store) {
            this.store = store;
        }

        public void create(WriterPermit permit, CreateOrder command) {
            store.insertOrder(permit, command);
        }
    }

Đây là code minh họa interface; chưa có implementation. Nếu insertOrder chỉ kiểm tra local permit rồi gửi SQL vào database không có fencing, vẫn có **time-of-check/time-of-use race**.

Trong một **database authoritative duy nhất**, check epoch có thể nằm cùng transaction với write; mẫu SQL khái niệm:

    BEGIN;
    SELECT epoch FROM writer_authority
    WHERE partition_id = :partition_id FOR UPDATE;

    -- Nếu epoch khác :caller_epoch, ROLLBACK.
    -- Chỉ sau đó mới ghi trong cùng transaction.

    INSERT INTO orders(id, amount_minor, currency)
    VALUES (:order_id, :amount_minor, :currency);
    COMMIT;

SQL chỉ minh họa ý tưởng; phải dùng isolation/locking đúng công nghệ và kiểm soát quyền, transaction failures. **Hai bảng writer_authority ở hai database đang partition không tạo ra một thẩm quyền toàn cục**.

## 12. Leader lease và lỗi process bị pause

Một lease thường có thời hạn, nhưng thời hạn có thể tạo race:

    A check lease: còn hợp lệ.
    A bị GC pause 20 giây.
    Lease A hết hạn; B nhận lease mới.
    A tỉnh dậy và thực hiện write cũ.

Nếu storage không kiểm tra epoch, A vẫn có thể commit dù đã mất quyền. Do đó leader lease ở tầng app không đủ nếu thiếu **data-plane fencing**.

Kubernetes có đối tượng **Lease** và có thể dùng cho leader election, nhưng dùng Lease object không tự làm database hay hệ thống ngoài cluster từ chối process cũ.

## 13. Async replication và mất commit đã ACK

Với asynchronous replication:

    10:00:00.000 A commit order O123.
    10:00:00.020 A trả HTTP 201.
    10:00:00.050 Kết nối A-B bị đứt.
    10:00:00.100 B chưa nhận WAL chứa O123.
    10:00:05.000 B được promote.

Order O123 không có tại B dù client nhận thành công. Đây là loại mất dữ liệu hoặc divergence phải dự phòng theo RPO và reconciliation.

**Ưu điểm async:** không phải đợi WAN replica trên mọi commit, latency write có thể thấp hơn.  
**Đánh đổi:** có cửa sổ các acknowledged writes chưa được sao chép.

Cần xác minh last sent, received, flushed và applied log positions/LSN theo database thực tế; một metric lag bị stale không chứng minh replica đã bắt kịp.

## 14. Sync replication và trade-off availability

Synchronous replication có thể yêu cầu follower/quorum xác nhận log theo một mức durability nhất định trước khi primary trả commit thành công.

- Có thể giảm khả năng mất acknowledged writes trong failure model được bảo đảm.
- Tăng latency vì phụ thuộc network/replica.
- Khi mất quorum hoặc replication target, phải quyết định ngừng ghi hay giảm durability.
- Cần biết log đã nhận vào memory hay đã flush bền.
- Có thể có chế độ semi-sync với mức bảo đảm khác.

Không kết luận tự động “sync replication = RPO 0 trong mọi sự cố”. Phải hiểu commit semantics, data durability, failover election và timeline của hệ quản trị.

## 15. Khi nào nên promote replica?

Trước promotion, cần biết:

- Replica đã có đến LSN/offset nào?
- Log đã received, flushed và applied đến đâu?
- Schema/data format có tương thích app đang chạy?
- Có primary/replica khác mang log mới hơn?
- Có transaction đã ACK tại A nhưng chưa tới B?
- Có khả năng old writer A còn nhận client?
- Có thể fencing A bằng cơ chế đáng tin không?
- RPO tiềm năng có nằm trong giới hạn đã phê duyệt?
- Kế hoạch xử lý pending payments/outbox/events sau promote?

**Readiness check ở B không đủ bằng chứng**. B có thể khởi động tốt nhưng dữ liệu quá cũ, hoặc được promote trong khi A vẫn ghi.

Với PostgreSQL, log sequence number/timeline có ý nghĩa quan trọng, nhưng thao tác promote/rejoin phải tuân thủ PostgreSQL HA manager/operator và version đang dùng; không viết lệnh thủ công chỉ dựa trên một dashboard.

## 16. Chuyển traffic và chuyển authority là hai việc khác nhau

Global routing thường sử dụng DNS failover, global load balancer, anycast, Gateway hoặc client-side region selection. Nhưng có nhiều nguồn traffic cũ:

- DNS resolver cache vượt dự kiến.
- HTTP keep-alive hoặc connection pool chưa đóng.
- Mobile app lưu regional endpoint.
- Đối tác gọi callback URL cố định.
- Background job không đi qua public load balancer.
- Event consumer ở A vẫn chạy.
- Internal service gọi thẳng DNS nội vùng.

TTL=30 giây không bảo đảm toàn bộ client chuyển trong 30 giây. **Traffic switch không phải write fencing**.

Khi writer đã chuyển sang B, A phải từ chối ghi hoặc được cô lập theo giao thức; những client còn đến A cần nhận redirect/error có ý nghĩa, không được tạo record mới vào timeline cũ.

## 17. Read-only/degraded mode khi authority chưa rõ

Nếu network partition khiến không thể biết vùng nào được quyền single-writer, có thể giảm chức năng:

- Catalog mô tả sản phẩm có thể đọc cache stale theo policy.
- Lịch sử order có thể hiển thị dữ liệu đến recovery point và thông báo trạng thái đồng bộ.
- Checkout/payment cần từ chối hoặc đưa vào trạng thái tạm dừng khi không thể xác định write authority.
- Các thao tác thay đổi quyền/tiền/tồn kho không nên được ghi tại hai nơi chỉ để giữ tỷ lệ HTTP 200.

Phân biệt response **UNAVAILABLE**, **READ_ONLY**, **PENDING** và **SUCCESS**. Không đánh dấu thành công một giao dịch chưa được commit authoritative.

### 17.1. Read-your-writes

Nếu client vừa tạo order ở A rồi đọc từ B còn lag, nó có thể không thấy record. Giải pháp phụ thuộc backend:

- Route đọc tới writer hoặc replica đã theo kịp commit version.
- Dùng consistency token/log position khi hỗ trợ.
- Chờ catch-up trong deadline.
- Trả trạng thái pending rõ ràng.

Đừng suy ra “payment chưa xảy ra” chỉ vì read replica stale chưa thấy record rồi charge lần nữa.

## 18. Idempotency xuyên vùng trong Payment

Giả sử client gửi:

    POST /api/payments
    Idempotency-Key: pay-order-123
    Authorization: Bearer <access-token>

A đã charge tiền nhưng response mất. Client retry sang B sau failover. Nếu B chưa có idempotency record của A, B có thể tạo charge thứ hai.

Biện pháp:

1. Xác định logical operation theo merchant/tenant, orderId và payload được phép.
2. Lưu idempotency key và kết quả theo consistency đáp ứng RPO nghiệp vụ.
3. Tra cứu trạng thái từ provider qua transaction ID/reference nếu kết quả UNKNOWN.
4. Không cấp một key mới để charge lại khi attempt cũ chưa được xác minh.
5. Bảo vệ race giữa các region và concurrent requests.
6. Giữ key đủ lâu cho retry, failover, reconciliation.
7. Audit và đối soát transaction đã ACK nhưng thiếu record cục bộ.

**Idempotency không chỉ là một header.** Nó là contract về nhận diện một nghiệp vụ duy nhất qua nhiều attempts và nhiều vùng.

## 19. Inventory và oversell khi hai writer

Kho có một sản phẩm SKU-1, nhưng do split-brain:

    Region A đọc available=1 -> reserve cho Order OA.
    Region B đọc available=1 -> reserve cho Order OB.

Khi mạng phục hồi, cả hai đều đã hứa giao cùng một món hàng. Last-write-wins không làm hai lời hứa trở nên đúng.

Các chiến lược phù hợp có thể gồm:

- Một writer theo SKU/warehouse.
- Database transaction/quorum bảo vệ invariant số lượng.
- Phân ownership theo warehouse để mỗi vùng dùng một pool riêng.
- **Escrow quota:** cấp trước số lượng riêng cho từng vùng, không vượt quota local; điều chuyển quota cần protocol.
- Compensation khi đã oversell, nhưng đó chỉ là xử lý hậu quả.

Với tiền và hàng hữu hạn, quyết định consistency phải được đưa ra **trước** khi định nghĩa active-active routing.

## 20. Active-active multi-writer và xung đột

Multi-writer có thể phù hợp cho dữ liệu có phép merge được thiết kế:

- Một số loại counter hoặc tập hợp theo CRDT.
- Metadata có thể chấp nhận eventual consistency.
- Draft/Preference với conflict resolution rõ.

Nhưng một CRDT counter cộng dồn không tự bảo vệ quota toàn cục nếu các vùng đều tiêu cùng một tài nguyên hữu hạn. Last-write-wins có thể làm mất một thao tác người dùng đã được xác nhận.

Trước khi dùng multi-writer, phải trả lời:

1. Invariant nào cần đúng tuyệt đối?
2. Operation có commutative/associative/idempotent không?
3. Uniqueness và ID generation quản lý thế nào?
4. Conflict được lưu và giải quyết ở đâu?
5. Khi partition, có cho phép write hay dừng?
6. Người dùng thấy trạng thái tạm không nhất quán thế nào?
7. Audit và compensation xử lý khi merge ra kết quả khác thế nào?

**Active-active không phải đồng nghĩa mọi nơi ghi vào cùng bảng một cách tự do.**

## 21. Ownership theo tenant hoặc shard

Một mô hình khác cho phép hai vùng đều active nhưng sở hữu các partition khác nhau:

    Tenant 1-500     -> Region A writer
    Tenant 501-1000  -> Region B writer

Khi cần chuyển một tenant từ A sang B:

1. Định danh partition/tenant và epoch.
2. Chặn hoặc drain write mới tại owner cũ.
3. Fence A cho partition đó.
4. Đồng bộ dữ liệu tới recovery point được chấp nhận.
5. Cấp epoch mới và quyền writer cho B.
6. Cập nhật routing theo owner map.
7. Xử lý retry bằng idempotency.
8. Theo dõi stale requests và báo lỗi/redirect.
9. Ghi audit và thiết kế failback tương tự.

Ownership map cũng phải được quản lý bởi nguồn thẩm quyền nhất quán. Hai bản đồ ownership độc lập bị partition có thể cùng cấp một tenant cho hai vùng.

## 22. Queue, Kafka và event processing

Trong event-driven systems, quyền xử lý message và side effect cũng quan trọng như quyền ghi database.

Ví dụ:

1. Consumer tại A đọc PaymentRequested.
2. A gọi payment provider thành công.
3. A lỗi trước khi ack/commit offset.
4. B nhận lại message sau consumer failover.
5. Nếu không dedup, B gọi charge một lần nữa.

Cần idempotent consumer, inbox/dedup, transaction state, outbox/reconciliation. Consumer group assignment không đảm bảo side effect ngoài broker được thực hiện đúng một lần.

Với hai broker clusters cross-region, còn phải xác định:

- Producer nào được phép phát event?
- Offset/sequence được ánh xạ khi chuyển cluster ra sao?
- Có duplicate/gap do replication async không?
- Message nào đã được consumer xử lý?
- Event schema mới có tương thích consumer cũ không?
- DLQ và backlog sẽ được replay thế nào?

Không phát lại mọi message mù khi reconnect; Payment, Notification hoặc Inventory có thể đã thực hiện side effect.

## 23. Những dependency khác cần kế hoạch DR

### Cache

Region B có thể có cache lạnh, gây cache miss storm xuống database mới promote. Cần cache warmup, request coalescing, bounded concurrency, rate limiting và circuit breaker.

### Search/read model

Projection có thể rebuild từ nguồn, nhưng phải có event log và replay semantics. Định nghĩa freshness/lag; không dùng search index stale để cam kết tồn kho.

### Object storage

Replication cross-region có thể asynchronous. Object vừa upload ở A chưa chắc có ở B. Kiểm tra IAM, metadata, versioning, encryption keys, data residency và công cụ đối soát.

### Identity và secrets

Nếu B phụ thuộc KMS, secret manager hoặc identity provider chỉ có ở A, failover có thể thất bại ngay cả khi compute/DB đã sẵn sàng. Thiết kế key recovery và hạn chế access theo threat model.

### External providers

Payment, shipping, webhook callback có thể gắn endpoint/region. Đảm bảo các provider nhận cùng transaction reference và không tạo duplicate effect khi callback được gửi tới cả hai vùng.

## 24. Runbook: phát hiện, cô lập, chuyển writer

### Pha A — Detect và declare

1. Thu thập alert, SLO, synthetic probes từ nhiều vị trí.
2. Phân biệt outage hoàn toàn với network partition.
3. Ghi incident ID, timeline, affected region và owner.
4. Xác định workflow ghi quan trọng, pending operations và event backlog.
5. Tạm dừng rollout/change không thiết yếu.
6. Đưa các write rủi ro vào degraded/read-only mode nếu authority chưa rõ.

### Pha B — Authority và fencing

1. Từ database cluster manager/consensus, xác định leader/epoch hiện tại.
2. Không suy ra old writer chết từ heartbeat timeout.
3. Thực hiện hoặc xác minh **fencing** theo cơ chế được hỗ trợ.
4. Kiểm tra process/connection cũ không thể ghi.
5. Ghi bằng chứng và người phê duyệt promotion.
6. Nếu fencing/quorum chưa đạt, không tự promote single-writer database.

### Pha C — Kiểm tra dữ liệu B

1. Xem received/flushed/applied log positions.
2. Xác định replication lag và cửa sổ dữ liệu thiếu.
3. Đánh giá RPO tiềm năng so với mức đã phê duyệt.
4. Kiểm tra schema, version ứng dụng, event contracts.
5. Xác định outbox, pending payment, idempotency và queue gaps.
6. Chọn promote, đợi thêm hoặc recovery strategy khác.

## 25. Runbook: promote, route, reconcile

### Pha D — Promote

1. Promote B bằng phương pháp chính thức của database/operator.
2. Cấp epoch/term mới nếu kiến trúc cần.
3. Xác nhận **chỉ một writable authority hợp lệ**.
4. Thử ghi/đọc synthetic operation an toàn.
5. Kiểm tra stale epoch bị từ chối.
6. Không chạy lệnh thủ công bypass cluster manager.

### Pha E — Traffic

1. Bảo đảm B có compute, connections, quota và capacity.
2. Kiểm tra TLS/KMS/identity/secrets/downstream.
3. Chuyển global routing theo runbook.
4. Theo dõi connections và requests còn đến A.
5. Kiểm soát retries, idempotency và side effects.
6. Quan sát p95/p99, error rate, backlog, DB writes và cache miss.

### Pha F — Reconciliation

1. So sánh log/data timeline khi A có thể truy cập an toàn.
2. Xác định commits chưa replicate.
3. Đối soát Order, Payment, Inventory, outbox, event IDs.
4. Repair hoặc compensation bằng job idempotent có checkpoint.
5. Ghi actual RTO/RPO và unresolved records.
6. Giữ A fenced cho đến khi có rejoin/failback plan riêng.

**Failover không hoàn thành chỉ vì một trang đã trả 200 tại B.** Nó hoàn thành khi authority, dữ liệu và giao dịch đã đạt điều kiện chấp nhận.

## 26. Failback: vùng cũ hồi phục không được tự nhận primary

Giả sử B được promote ở epoch 42 và nhận 10.000 write mới. A quay về với dữ liệu cũ và có thể chứa vài write chưa replicate.

Nếu A tự chạy với cấu hình isPrimary=true cũ, sẽ tạo một nhánh lịch sử mới hoặc ghi đè trạng thái đúng.

Quy trình:

1. Giữ A fenced/read-only.
2. Xác định timeline và những write chỉ có ở A.
3. Không gộp payment/inventory theo updatedAt lớn hơn.
4. Rebuild/rewind/reseed A từ nguồn authoritative B theo cơ chế database hỗ trợ.
5. Reconcile những transaction cần bù trừ hoặc đưa vào dữ liệu chuẩn.
6. Cho A tham gia như follower và chờ catch-up.
7. Kiểm tra schema, data integrity và consumer compatibility.
8. Nếu thật sự cần, chuyển quyền từ B về A bằng **planned handoff** mới: fence B, cấp epoch, verify writer, chuyển route.
9. Theo dõi stale client, workers và logs.
10. Ghi audit và postmortem.

Không nhất thiết phải failback ngay khi A có lại mạng. Giữ B làm primary tạm thời có thể an toàn hơn.

## 27. Reconciliation khi đã có dữ liệu phân kỳ

Một sự cố có thể tạo hai timeline:

    Region A:
      O100 created
      P100 charged
      O101 created

    Region B:
      O100 created with different payload
      P100 charged again
      O102 created

Không có thuật toán merge chung cho mọi nghiệp vụ. Quy trình điều tra:

- Bảo toàn WAL/log, backup, event IDs và transaction references.
- Xác định authoritative state của payment từ provider/ledger.
- Phân loại records thành replayable, compensatable hoặc manual review.
- Không tự charge lại khi trạng thái cũ UNKNOWN.
- Chạy repair idempotent có checkpoint, optimistic locking và audit before/after.
- Phát correction events nếu cần, không xóa history cần đối soát.
- Xác nhận business invariants như không double charge và không oversell.

**RTO của API và thời gian hoàn tất data repair là hai đại lượng khác nhau.** Giao dịch cần xử lý hậu sự cố có thể tồn tại sau khi traffic đã ổn định.

## 28. Backup, restore và PITR

Replication không thay backup. Một DELETE nhầm hoặc corruption có thể propagate sang mọi replica.

Cần:

- Backup ở failure domain phù hợp, tách quyền xóa.
- Encryption, KMS/key recovery và retention rõ.
- WAL/transaction log archiving và PITR nếu công nghệ hỗ trợ.
- Restore drill định kỳ, kiểm tra checksum/invariants.
- Xem mốc khôi phục của từng database; restore Order mà không restore Payment có thể tạo lệch trạng thái.
- Reconcile transactions và outbox/events sau recovery point.
- Đo RPO/RTO thực tế thay vì chỉ tin vào lịch backup.

Backup job báo thành công chưa chứng minh bản backup có thể restore. Cần thử khôi phục vào môi trường cô lập và xác minh dữ liệu.

## 29. Kubernetes và giới hạn của controller

Kubernetes hỗ trợ Deployments, StatefulSets, PVC, Service, Ingress/Gateway, Lease, PodDisruptionBudget và operators. Nhưng tự nó không bảo đảm:

- Database replication xuyên region an toàn.
- Global single-writer authority cho hai database độc lập.
- Fencing old process khi control plane không truy cập được.
- Data conflict resolution cho active-active writes.
- Exactly-once external side effects.
- Cross-service reconciliation và DR objectives.

Một StatefulSet có ba Pod PostgreSQL chưa chắc là PostgreSQL HA: replication, leader election, quorum, failover và fencing cần cơ chế database/cluster manager cụ thể.

Pod Ready không đồng nghĩa Pod có quyền ghi. Trong mô hình DR, nên có **read health**, **write health** và authority validation phù hợp.

## 30. Bảo mật khi failover

Sự cố khẩn không phải lý do bỏ các kiểm soát bắt buộc:

- Region B có IAM/service accounts phù hợp và least privilege.
- TLS/mTLS, certificates và secret rotation vẫn hoạt động.
- Backup và replication được mã hóa.
- KMS/identity không phụ thuộc duy nhất vùng hỏng.
- Quyền promote, failback, restore có owner/approval/audit.
- Không lưu plaintext credential trong runbook.
- Không dùng flag bỏ qua authentication hoặc authorization để “khôi phục nhanh”.
- Kiểm tra data residency, tenant isolation và quyền truy cập dữ liệu tại vùng dự phòng.
- Cảnh báo khi API hoặc storage ghi nhận stale epoch/double-writer attempts.

Một kế hoạch DR giúp API nhanh phục vụ lại nhưng làm lộ dữ liệu hoặc mất kiểm soát quyền ghi chưa thể gọi là thành công.

## 31. Metrics và tracing để biết thực sự đã khôi phục

| Nhóm | Cần đo |
| --- | --- |
| Routing | Traffic theo region, old-region requests, connection drain |
| Authority | Leader/epoch/quorum, fencing state, stale writer rejections |
| Database | Log sent/received/flushed/applied, replication lag, commit errors |
| Service | 5xx, p95/p99, timeout, queue, overloaded/downstream errors |
| Payments | Pending/UNKNOWN, duplicate attempts, reconciliation backlog |
| Inventory | Oversell candidates, stuck reservations |
| Events | Outbox backlog, consumer lag, DLQ, duplicate deliveries |
| Security | Unexpected write permission, stale credentials, audit changes |
| DR | Detect time, fence time, promote time, traffic convergence, actual RPO/RTO |
| Backup | Age, successful restore drills, missing WAL/log |

Không đặt raw orderId, userId hoặc token vào high-cardinality metrics labels. Điều tra từng transaction bằng tracing và audit có kiểm soát.

Một **dual-writer attempt** cần cảnh báo nghiêm trọng, kể cả khi request hiện vẫn trả 200. Nếu monitor chỉ theo dõi availability mà bỏ qua quyền ghi, có thể phát hiện split-brain quá muộn.

## 32. Diễn tập các failure mode

Các bài DR drill nên thử:

1. A thực sự down hoàn toàn.
2. A↔B partition nhưng A vẫn nhận client.
3. A mất leader lease rồi tỉnh sau GC pause.
4. B bị replication lag 10 phút.
5. DNS cache/long-lived connection tiếp tục gửi tới A.
6. Payment đã charge nhưng response timeout.
7. Control plane/witness unavailable.
8. A hồi phục đột ngột và thử nhận lại quyền.
9. Automation và manual failover được gọi gần đồng thời.
10. Cache lạnh tại B gây cache stampede.
11. Broker replay event và consumer tạo side effect trùng.
12. Backup cần restore vào vùng khác khi KMS/secret manager ở A lỗi.
13. Region B hết compute quota lúc cần scale.
14. Ownership một tenant/shard chuyển khi đang có concurrent requests.

Mỗi drill phải có owner, phạm vi test, expected invariants, abort conditions, telemetry và postmortem. Không chạy payment thật lặp lại để kiểm thử.

**Đặc biệt phải thử network partition khi old region còn sống**, không chỉ mô phỏng tắt hẳn cluster A.

## 33. Những sai lầm thường gặp

1. Dựa vào ping để tuyên bố primary đã chết.
2. Chỉ đổi DNS mà không fence writer cũ.
3. Hai DB độc lập đều writable rồi gọi đó là HA.
4. Dùng Kubernetes Lease nhưng storage không chặn stale epoch.
5. Cho old region tự nhận primary sau restart.
6. Promote follower async không kiểm tra lag và RPO.
7. Tin metric lag=0 nhưng không xác định log position/cửa sổ đo.
8. Dùng last-write-wins cho tiền hoặc inventory.
9. Không có idempotency xuyên failover.
10. Retry charge khi timeout mà không tra trạng thái.
11. Quên workers, webhooks, mobile endpoint và partner direct URLs.
12. Cho cả hai regions xử lý cùng event gây side effect trùng.
13. Không backup vì đã có replica.
14. Restore DB riêng lẻ mà không reconcile service khác.
15. Không kiểm tra schema/event version trước khi promote.
16. Không dự phòng cache cold-start và quota vùng B.
17. Failback bằng cách đổi DNS ngay khi A lên lại.
18. Trộn auto/manual failover thiếu audit/state machine.
19. Không kiểm tra KMS/identity ở vùng dự phòng.
20. Tạm tắt authorization để tăng availability.
21. Chỉ nhìn HTTP 200 thay vì business correctness.
22. Không diễn tập partition với old writer còn sống.
23. Không ghi actual RPO/RTO và unresolved records sau incident.

## 34. Checklist triển khai

### Data safety

- [ ] Xác định authoritative writer của mỗi partition/dataset.
- [ ] Có single-writer protocol hoặc multi-writer conflict model.
- [ ] Quorum/fencing thực thi tại write boundary.
- [ ] Old region không tự lấy lại quyền.
- [ ] Replication lag và log positions đo được.
- [ ] RPO/RTO có chủ sở hữu và được kiểm chứng.
- [ ] Idempotency, uniqueness và ledger invariants đúng qua failover.
- [ ] Backup/restore/reconciliation đã thiết kế.

### Routing và dependencies

- [ ] Biết tất cả routes: DNS, regional URLs, webhook, workers.
- [ ] Có degraded/read-only mode khi authority chưa rõ.
- [ ] Region B đủ compute, quota, storage và network.
- [ ] KMS, TLS, identity, secrets dùng được tại B.
- [ ] Broker, object storage, search/cache có DR plan.
- [ ] Schema và application version tương thích.
- [ ] Có metric traffic cũ và stale-epoch rejections.

### Vận hành

- [ ] Runbook detect → fence → promote → route → reconcile rõ.
- [ ] Manual và automation dùng một source of truth.
- [ ] Owner/approval/audit cho promotion và restore.
- [ ] Failback có kế hoạch riêng, không tự đảo DNS.
- [ ] Có chaos test network partition và old region recovery.
- [ ] Đo actual RPO/RTO và ghi bài học từ drill.

## 35. Câu hỏi tự kiểm tra

**1. Region B không ping được A có chứng minh A chết không?**  
Không; có thể là network partition.

**2. Đổi DNS sang B có chặn A ghi không?**  
Không; stale clients, connections và background jobs vẫn có thể gọi A.

**3. Split-brain là gì?**  
Nhiều phía cùng hành động như writer/leader hợp lệ cho cùng dữ liệu, tạo lịch sử ghi mâu thuẫn.

**4. Fencing token giúp gì khi A bị GC pause?**  
A thức dậy với epoch cũ và bị write boundary từ chối, dù process còn sống.

**5. Quorum có đủ nếu database vẫn chấp nhận old writer?**  
Không. Phải có enforcement ở nơi dữ liệu thật được ghi.

**6. Async replication có thể mất record nào?**  
Record primary đã ACK nhưng chưa replicate tới vùng được promote.

**7. Synchronous replication luôn bảo đảm RPO=0?**  
Không thể chỉ suy từ tên; phải xét cơ chế commit, durability và failover cụ thể.

**8. Active-active có nghĩa cả hai cùng ghi payment ledger?**  
Không. Có thể active-active reads nhưng single-writer writes; multi-writer cần thiết kế riêng.

**9. Vì sao last-write-wins nguy hiểm cho inventory?**  
Vì nó có thể loại bỏ một reservation đã được xác nhận, vi phạm lời hứa giao hàng.

**10. A hồi phục sau failover sang B thì làm gì?**  
Giữ A fenced, đồng bộ/reconcile, rồi mới chuyển quyền theo planned failback nếu cần.

**11. Vì sao Payment cần idempotency xuyên vùng?**  
Retry sang B có thể xảy ra sau charge thành công ở A nhưng record chưa replicate.

**12. Replication thay thế backup?**  
Không; xóa/corruption có thể lan theo replication.

**13. Nếu không xác định được writer khi partition, có nên cho cả hai ghi?**  
Không đối với dữ liệu cần single-writer safety; có thể tạm dừng write.

**14. Vì sao chỉ test tắt toàn A chưa đủ?**  
Vì split-brain thường xuất hiện khi A còn sống nhưng bị partition.

**15. Khi nào failover được coi là thực sự hoàn thành?**  
Khi authority duy nhất, route, RPO/RTO, tính đúng đắn dữ liệu và reconciliation đạt điều kiện nghiệp vụ, không chỉ API trả 200.

## 36. Tài liệu tham khảo

- Google SRE Workbook — Disaster Recovery Planning: https://sre.google/workbook/disaster-recovery/
- Google SRE Book — Addressing Cascading Failures: https://sre.google/sre-book/addressing-cascading-failures/
- Martin Kleppmann — Designing Data-Intensive Applications: https://dataintensive.net/
- Kubernetes — Leases: https://kubernetes.io/docs/concepts/architecture/leases/
- Kubernetes — StatefulSets: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/
- PostgreSQL — High Availability, Load Balancing and Replication: https://www.postgresql.org/docs/current/high-availability.html
- PostgreSQL — Continuous Archiving and Point-in-Time Recovery: https://www.postgresql.org/docs/current/continuous-archiving.html
- PostgreSQL — Replication Protocol: https://www.postgresql.org/docs/current/protocol-replication.html
- Apache Kafka — Documentation: https://kafka.apache.org/documentation/
- Microsoft — Compensating Transaction Pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction
- AWS Well-Architected Reliability Pillar: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html

**Ghi nhớ:** Failover multi-region an toàn đòi hỏi **chuyển quyền ghi có bằng chứng**, **fencing old writer**, xác minh dữ liệu theo **RPO**, giữ **idempotency** xuyên vùng và đối soát side effects. Chuyển traffic nhanh không thể thay thế những bảo đảm này; failback cũng phải là một quá trình chuyển quyền mới có kiểm soát.
