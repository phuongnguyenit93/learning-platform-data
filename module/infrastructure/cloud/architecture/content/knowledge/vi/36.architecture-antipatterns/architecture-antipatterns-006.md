# Phản mẫu kiến trúc: Sử dụng đa khu vực khi chưa giải quyết quyền ghi và xung đột dữ liệu

## 1. Bối cảnh: nhiều khu vực chưa đồng nghĩa với độ tin cậy cao

Một hệ thống cloud có thể chạy ứng dụng ở hai hay nhiều khu vực địa lý (region) nhằm phục vụ người dùng gần hơn, duy trì dịch vụ khi một khu vực gặp sự cố hoặc đáp ứng quy định lưu trữ dữ liệu. Tuy nhiên, **triển khai nhiều bản sao ứng dụng và cơ sở dữ liệu không tự động biến chúng thành một hệ thống ghi nhất quán**.

Phản mẫu xuất hiện khi nhóm thiết kế bật chế độ **active-active**, cho phép người dùng ghi cùng một tập dữ liệu ở nhiều region, nhưng chưa trả lời được:

- **Ai có quyền ghi?** Một thực thể như đơn hàng, số dư ví hoặc số lượng tồn kho thuộc quyền ghi của region nào tại một thời điểm?
- **Ghi nào thắng?** Hai bản cập nhật đồng thời trong hai khu vực được sắp thứ tự, hợp nhất hay từ chối như thế nào?
- **Khi đứt kết nối giữa các region,** hệ thống ưu tiên tiếp tục chấp nhận ghi hay duy trì bất biến dữ liệu?
- **Sau khi mạng phục hồi,** dữ liệu phân kỳ được phát hiện, đối soát và sửa theo quy tắc nghiệp vụ nào?
- **Khi chuyển region ghi chính,** điều gì ngăn region cũ vẫn tiếp tục chấp nhận ghi?

Đây là chủ đề thuộc nhóm **phản mẫu kiến trúc** của học phần **Cloud Architecture**: đánh giá thiết kế ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Trọng tâm là đánh đổi giữa **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành**, đồng thời áp dụng tư duy **Well-Architected** để kiểm tra các quyết định.

**Thông điệp cốt lõi:** Trước khi phân tán khả năng **ghi**, hãy xác định những bất biến nghiệp vụ phải đúng ở mọi thời điểm, phạm vi của một giao dịch, chủ sở hữu quyền ghi và giao thức xử lý khi các khu vực bất đồng.

## 2. Nhận diện phản mẫu

### 2.1. Hình dạng thường thấy

~~~mermaid
flowchart TB
    C[Người dùng / Global DNS] --> GLB[Global Traffic Manager]
    GLB --> A[Ứng dụng tại Region A]
    GLB --> B[Ứng dụng tại Region B]

    subgraph Ra["Region A"]
        A --> DA[(Database A: cho phép ghi)]
    end

    subgraph Rb["Region B"]
        B --> DB[(Database B: cho phép ghi)]
    end

    DA <-->|Sao chép bất đồng bộ| DB

    classDef bad fill:#fde9e7,stroke:#c04d45,color:#6b1f1f
    class DA,DB bad
~~~

Với sơ đồ trên, cả Database A và B nhận ghi độc lập, rồi trao đổi dữ liệu qua replication bất đồng bộ. Khi kết nối bình thường, phần lớn bản ghi có thể hội tụ sau một thời gian. Nhưng nếu hai region cập nhật **cùng một đối tượng** trước khi nhận bản cập nhật của nhau, sẽ xuất hiện xung đột.

Ví dụ một gian hàng chỉ còn **1 sản phẩm**:

| Thời điểm | Region A | Region B |
| --- | --- | --- |
| T0 | Bản sao đọc tồn kho = 1 | Bản sao đọc tồn kho = 1 |
| T1 | Khách X đặt 1 sản phẩm | Khách Y đặt 1 sản phẩm |
| T2 | Ghi cục bộ: tồn kho từ 1 xuống 0; báo đặt hàng thành công | Ghi cục bộ: tồn kho từ 1 xuống 0; báo đặt hàng thành công |
| T3 | Sao chép trạng thái sang B | Sao chép trạng thái sang A |
| T4 | Cả hai đơn đã được xác nhận | Chỉ có 1 sản phẩm thật để giao |

Nếu cơ chế merge dùng **last-write-wins (LWW)**, có thể chỉ còn một giá trị tồn kho bằng 0; con số này trông hợp lệ nhưng **hai khách đã nhận xác nhận cho cùng một đơn vị hàng**. Chọn bản cập nhật “mới nhất” không sửa được sai phạm nghiệp vụ đã xảy ra.

Lỗi này có thể xuất hiện ngay cả khi không có sự cố mạng hoàn toàn: chỉ cần replication delay đủ dài để hai bên cùng ra quyết định từ dữ liệu cũ.

### 2.2. Triệu chứng trong hệ thống thật

| Triệu chứng | Nguồn gốc có thể |
| --- | --- |
| Đơn hàng, thanh toán hoặc giao dịch trùng khi người dùng chuyển khu vực | Yêu cầu retry không có idempotency toàn cục; hai nơi cùng xử lý |
| Tồn kho âm, bán vượt tồn, dùng mã khuyến mại quá lượt | Bất biến được kiểm tra riêng trong từng region |
| Tên người dùng/mã đơn “unique” nhưng vẫn trùng xuyên region | Unique constraint chỉ có hiệu lực trong một DB cục bộ |
| Dữ liệu vừa sửa lại quay về giá trị cũ | Write conflict, stale read hoặc failback từ replica chưa đồng bộ |
| Sau failover xuất hiện bản ghi “mồ côi” | Ghi đã xác nhận ở region cũ chưa được replicate sang region mới |
| Hai cụm đều tự nhận là primary | Split-brain, thiếu cơ chế fencing/quorum và quyền sở hữu ghi |
| Hệ thống không báo lỗi nhưng số liệu tổng hợp lệch | Merge theo thời gian ghi làm mất update; xử lý event lặp hoặc sai thứ tự |

**Dấu hiệu nguy hiểm nhất** là mọi service có vẻ đang hoạt động và độ trễ thấp nhưng dữ liệu nghiệp vụ không còn thỏa bất biến. Vì vậy, sức khỏe của load balancer hay database không đủ để kết luận kiến trúc đang an toàn.

## 3. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa đối với đa khu vực |
| --- | --- |
| **Multi-AZ** | Chạy qua nhiều availability zone trong cùng khu vực, thường có độ trễ thấp hơn kết nối liên region. Không đồng nhất với multi-region. |
| **Multi-region** | Ứng dụng/dữ liệu có mặt tại nhiều region; chưa nói gì về quyền ghi hoặc mức nhất quán. |
| **Active-passive** | Một khu vực đảm nhiệm ghi; khu vực dự phòng được kích hoạt khi cần. |
| **Active-active** | Nhiều khu vực phục vụ lưu lượng đồng thời; cần hỏi kỹ liệu chúng chỉ cùng **đọc**, ghi vào **các key khác nhau**, hay cùng ghi **một key**. |
| **Single-writer** | Mỗi thực thể tại một thời điểm có đúng một bên được ủy quyền ghi. Có thể chỉ có một writer toàn hệ thống hoặc mỗi key có owner riêng. |
| **Multi-writer** | Nhiều nơi có thể ghi đồng thời; nếu cùng một key, cần cơ chế giải quyết xung đột và bảo vệ bất biến. |
| **Synchronous replication** | Ghi chỉ được xác nhận sau khi đáp ứng chính sách xác nhận của nhiều replica/quorum; ảnh hưởng độ trễ và khả năng ghi khi partition. |
| **Asynchronous replication** | Ghi được xác nhận ở nguồn trước khi replica nhận đủ; có độ trễ sao chép và nguy cơ mất ghi đã xác nhận khi chuyển vùng. |
| **RPO** | Mức mất dữ liệu tối đa có thể chấp nhận khi khôi phục, đo bằng khoảng cách dữ liệu/thời gian. |
| **RTO** | Khoảng thời gian tối đa chấp nhận để phục hồi chức năng dịch vụ sau sự cố. |
| **Split-brain** | Hai hoặc nhiều bên đồng thời tin rằng mình có quyền ghi chính đối với cùng tập dữ liệu. |
| **Fencing** | Cơ chế bảo đảm writer cũ mất quyền và các thao tác của nó bị từ chối tại điểm thực thi ghi. |

Không thể suy ra **active-active = mạnh hơn active-passive** trong mọi khía cạnh. Nếu workflow cần một giao dịch nhất quán xuyên khu vực, một phương án active-active có thể tạo thêm điểm phụ thuộc mạng và làm giảm khả năng ghi khi partition.

### 3.1. Vì sao phân vùng mạng khiến kiến trúc phải chọn?

Khi hai region không liên lạc được, hệ thống không thể vừa cho **mọi** region tiếp tục tự do ghi **cùng một dữ liệu**, vừa bảo đảm **mọi thao tác đều có thứ tự và bất biến mạnh** mà không cần cơ chế phối hợp. Nhìn qua lăng kính CAP, trong một phân vùng mạng, thiết kế phải xác định hành vi giữa khả năng tiếp nhận thao tác và tính nhất quán của trạng thái chung.

Nói chính xác hơn, khả năng ghi **vẫn có thể duy trì** cho các key hoặc thao tác độc lập, nhưng không thể hứa hẹn quyền ghi xung đột sẽ đều được chấp nhận mà vẫn bảo toàn bất biến chặt chẽ. Với mạng liên vùng hoạt động bình thường, đồng bộ chặt hơn cũng tăng độ trễ so với ghi cục bộ; đây là một đánh đổi thường được bàn cùng mô hình PACELC.

Ví dụ:

- Nội dung hồ sơ chỉ cập nhật trường không liên quan có thể được hợp nhất theo quy tắc rõ ràng.
- Bộ đếm lượt xem có thể dùng cơ chế cộng dồn hỗ trợ hợp nhất (chấp nhận đọc trễ).
- **Trừ số dư, giữ chỗ hàng, mua vé cuối cùng** không nên để hai region quyết định độc lập chỉ từ bản sao dữ liệu trễ.

## 4. Phân tích lỗi dưới góc độ tính đúng đắn

### 4.1. Lost update và xung đột cùng bản ghi

Giả sử người dùng sửa địa chỉ giao hàng ở A và B gần như đồng thời. Nếu A nhận phiên bản “Đường 1”, B nhận phiên bản “Đường 2”, một bộ so sánh timestamp cuối cùng sẽ chọn một phiên bản. Việc chọn phiên bản nào phụ thuộc clock và quy tắc merge, và bản cập nhật còn lại có thể biến mất. Đồng hồ hệ thống giữa hai region có thể lệch; timestamp vật lý không phải bằng chứng chắc chắn về thứ tự nhân quả.

Ngay cả **last-write-wins** có cơ chế clock tốt hơn cũng chỉ là **chính sách giải quyết cạnh tranh**, không phải giải pháp chung cho mọi dữ liệu. Nếu một update bị bỏ, cần xác định trước rằng việc mất update đó có được phép hay không.

### 4.2. Vi phạm unique constraint xuyên region

Hai người tạo cùng một mã khuyến mại duy nhất tại A và B. Cả hai DB local đều thấy chưa có mã và đều commit. Unique index ở từng region không thể bảo đảm tính duy nhất **toàn cục** nếu không có điểm điều phối hoặc cách phân vùng namespace độc lập.

Cách giải quyết phụ thuộc yêu cầu: khóa duy nhất toàn cục qua một dịch vụ sở hữu namespace; sinh ID có phân vùng/tiền tố region để tránh va chạm; hoặc dùng cơ sở dữ liệu có khả năng giao dịch nhất quán tương ứng. Phân tán ID tránh đụng khóa kỹ thuật **không** bảo vệ tính duy nhất của tên đăng nhập hay voucher theo nghiệp vụ.

### 4.3. Split-brain khi failover

Region A là writer hiện tại. Health check tại B mất liên lạc với A rồi tự promote B thành writer. Tuy nhiên, A vẫn phục vụ một nhóm client và vẫn có thể commit. Hai cụm cùng nhận ghi:

~~~mermaid
sequenceDiagram
    autonumber
    participant CA as Client tại A
    participant A as Region A (writer cũ)
    participant N as Mạng liên region
    participant B as Region B (writer mới)
    participant CB as Client tại B

    N--xA: Mất kết nối
    N--xB: Mất kết nối
    Note over A,B: B không thể phân biệt A chết hay chỉ mất liên lạc
    CA->>A: Ghi bản X
    A-->>CA: Commit OK
    CB->>B: Ghi bản Y cùng một entity
    B-->>CB: Commit OK
    Note over A,B: Hai lời hứa ghi cùng lúc gây split-brain
~~~

Một health check báo “không thấy primary” không có nghĩa primary đã **mất quyền ghi**. Muốn tự động chuyển quyền an toàn, cần một cơ chế bầu chọn/lease/quorum phù hợp **và** khả năng ngăn writer cũ commit về sau.

### 4.4. RPO khác 0: xác nhận thành công nhưng mất sau chuyển vùng

Với replication bất đồng bộ, tại thời điểm A trả “thành công”, một số thay đổi có thể còn trong hàng đợi replication. Nếu A bị mất hoàn toàn và B trở thành writer, B có thể không có những thay đổi đó. Điều này không chỉ là “dữ liệu đọc chưa kịp cập nhật”: có thể là **mất một ghi mà người dùng đã được xác nhận**.

Vì vậy, cần định nghĩa rõ:

1. Ghi được xem là **durable** sau loại xác nhận nào (local commit, đa replica trong vùng hay quorum liên vùng)?
2. RPO thiết kế và RPO quan sát được tại lúc failover là bao nhiêu?
3. Dữ liệu thiếu được tìm, bổ sung hoặc bù trừ bằng cách nào nếu region cũ quay lại?
4. Client retry trên B có idempotency key bền vững và đúng phạm vi hay không?

Không được quảng bá “zero data loss” nếu thực tế chỉ sao chép bất đồng bộ và không có giải pháp bảo đảm RPO bằng 0 trong những loại sự cố đã cam kết.

### 4.5. Đọc trễ và “read-your-writes”

Một khách cập nhật hồ sơ tại A, sau đó request kế tiếp được route đến B trước khi replication kịp cập nhật. Khách thấy dữ liệu cũ và có thể gửi lại thao tác. Đây là vấn đề nhất quán phiên (*session consistency*), ngay cả khi chỉ có một writer.

Cách khắc phục thường là:

- Route session về writer hoặc replica đã theo kịp một mốc version/commit token nhất định.
- Đọc từ writer trong những thao tác cần **read-your-writes**.
- Hiển thị trạng thái chờ đồng bộ đối với nghiệp vụ chấp nhận dữ liệu trễ.
- Dùng consistency level do database hỗ trợ, kiểm tra rõ phạm vi bảo đảm.

Không nên mặc định rằng “đọc từ region gần nhất” phù hợp cho mọi màn hình, đặc biệt là sau thanh toán, thay đổi quyền truy cập hoặc xác nhận đặt hàng.

## 5. Bắt đầu từ bất biến và phạm vi quyền ghi

### 5.1. Phân loại dữ liệu trước khi chọn active-active

| Loại dữ liệu/nghiệp vụ | Bất biến điển hình | Chiến lược phù hợp hơn |
| --- | --- | --- |
| Số dư, sổ cái giao dịch | Không chi vượt hạn mức; không ghi trùng bút toán | Quyền ghi tập trung theo tài khoản, transaction mạnh, ledger bất biến |
| Tồn kho theo SKU/kho | Không bán vượt số lượng khả dụng | Một owner cho mỗi bucket tồn hoặc escrow/phân bổ hạn ngạch có kiểm soát |
| Ghế/vé/suất đặt trước | Một chỗ chỉ được cấp phát một lần | Owner/khóa giao dịch cho mỗi tài nguyên, xác nhận nhất quán |
| Mã người dùng duy nhất | Không trùng trong toàn namespace | Dịch vụ cấp phát global hoặc namespace phân vùng có quy tắc |
| Giỏ hàng, ghi chú cá nhân | Có thể chấp nhận hợp nhất một số thay đổi | Thiết kế merge theo nghiệp vụ, có thể dùng CRDT ở trường phù hợp |
| Bộ đếm tương tác/telemetry | Ưu tiên tổng hợp, cho phép trễ | Counter dạng cộng dồn, eventual consistency, deduplication |
| Danh mục sản phẩm ít thay đổi | Cho phép đọc trễ có giới hạn | Một nơi ghi, cache/replica nhiều nơi đọc |

Một entity có thể chứa **các trường với mức nhất quán khác nhau**. Không nên chuyển toàn bộ database sang chế độ ghi đa vùng chỉ vì một vài tập dữ liệu có thể hợp nhất dễ dàng.

### 5.2. Định nghĩa write owner

Đối với mỗi **consistency boundary** (đơn vị cần bảo vệ bất biến), phải biết:

- **Key sở hữu:** ví dụ accountId, orderId, sku + warehouseId hoặc seatId.
- **Chủ sở hữu hiện hành:** region, partition leader hoặc một nhóm quorum.
- **Cách tra cứu owner:** định tuyến tĩnh theo key, metadata nhất quán hoặc API của nền tảng dữ liệu.
- **Điều kiện ghi hợp lệ:** token/epoch/term, version hoặc transaction do owner được ủy quyền xử lý.
- **Cách chuyển quyền:** fencing writer cũ, phục hồi dữ liệu, xác minh trạng thái và ghi nhận owner mới.

**Single-writer không nhất thiết là một region cho toàn bộ hệ thống.** Có thể chia write owner theo account hoặc theo warehouse: region A sở hữu các account nhóm A, region B sở hữu nhóm B. Hai khu vực đều nhận ghi, nhưng **không đồng thời ghi cùng một consistency boundary**. Khi một transaction cần động tới tài nguyên ở nhiều owner, vẫn phải thiết kế điều phối, chấp nhận trễ hoặc thay đổi ranh giới dữ liệu.

### 5.3. Fencing token và quyền ghi cũ

Một mẫu quản lý writer dùng **generation/epoch** tăng đơn điệu:

1. Owner A được cấp **epoch 41**.
2. Sau một quy trình chuyển quyền hợp lệ, owner B được cấp **epoch 42**.
3. Nơi thực thi ghi chỉ chấp nhận request từ owner có epoch hiện hành; request epoch 41 bị từ chối, dù A hồi phục và nghĩ mình vẫn là leader.

~~~text
request:
  resource_key: SKU-123|Warehouse-1
  write_epoch: 42
  operation_id: reserve-order-879
  expected_version: 7

authoritative write path:
  verify current_owner and write_epoch
  atomically validate invariant and expected_version
  apply mutation and persist operation_id
  commit
~~~

**Cảnh báo thiết kế:** Nếu mỗi region chỉ lưu một bảng owner/epoch trong DB **sao chép bất đồng bộ**, hai bên vẫn có thể cùng chấp nhận epoch riêng của mình. Token chỉ an toàn khi **điểm thực thi ghi thực sự kiểm tra được epoch hợp lệ**, thông qua cơ chế nhất quán đủ mạnh (chẳng hạn consensus/quorum hoặc một leader database được fencing). Token truyền trong request nhưng không được enforce ở storage chỉ là metadata.

Lease dựa trên thời gian cũng cần xử lý sai lệch đồng hồ, chậm lịch chạy và pause của tiến trình. Khi nghi ngờ lease đã mất, writer phải ngừng ghi; không dựa duy nhất vào việc nó “chưa thấy leader mới”.

## 6. Các kiến trúc thay thế và điều kiện áp dụng

### 6.1. Phương án A — Một vùng ghi, nhiều vùng phục vụ đọc

~~~mermaid
flowchart LR
    U[Client đa khu vực] --> R[Global Router / CDN / WAF]
    R --> AA[App Region A]
    R --> AB[App Region B]
    AA --> P[(Primary DB: ghi tại A)]
    AB --> P
    P -->|Replication có độ trễ| RP[(Read Replica tại B)]
    AB -->|Đọc chấp nhận trễ| RP
    AB -->|Đọc cần mới nhất| P
~~~

- Chỉ **primary** được ghi; các application instance ở B phải chuyển request ghi về A.
- Read replica có thể giúp giảm độ trễ đọc nhưng cần phân loại truy vấn cần tính mới.
- Khi A hỏng, B **chưa tự động** trở thành writer chỉ vì có replica. Cần quy trình promotion, fencing và xử lý replication lag.
- Dữ liệu và log chạy qua ranh giới khu vực; tính chi phí truyền dữ liệu, bảo mật và cư trú dữ liệu.

**Phù hợp** khi nhiều nghiệp vụ cần consistency mạnh và nhu cầu cross-region write latency chưa phải ràng buộc quan trọng nhất. Phương án này thường dễ vận hành và dễ chứng minh bất biến hơn so với multi-writer trên cùng key.

### 6.2. Phương án B — Phân vùng owner theo thực thể

~~~mermaid
flowchart TD
    C[Global API] --> OW[Ownership / Routing Service]
    OW -->|account A hoặc bucket X| RA[Region A: Owner của partition A]
    OW -->|account B hoặc bucket Y| RB[Region B: Owner của partition B]
    RA --> DA[(DB A)]
    RB --> DB[(DB B)]
    RA -.->|Read projection / event| DB
    RB -.->|Read projection / event| DA
~~~

Ưu điểm là có thể ghi ở nhiều khu vực mà vẫn tránh concurrent write trên **cùng một entity**. Đổi lại, phải quản lý di chuyển owner, directory nhất quán, routing stale, hotspot và nghiệp vụ xuyên partition.

Ví dụ: mọi thao tác thay đổi hạn mức của account X đều được route tới owner của account X; hai account khác nhau có thể được xử lý ở hai region đồng thời. Nếu một chuyển khoản ảnh hưởng cả X và Y nằm ở hai owner, cần giao thức nghiệp vụ riêng (ví dụ reservation và saga) hoặc chuyển phần ledger yêu cầu nguyên tử vào cùng consistency boundary.

### 6.3. Phương án C — Multi-writer với xung đột được định nghĩa

Nhiều region có thể ghi lên cùng tập dữ liệu khi nghiệp vụ **đã thiết kế rõ merge semantics**. Các lựa chọn:

- **CRDT:** phù hợp với một số loại dữ liệu có phép hợp nhất hội tụ (counter, set theo semantics cụ thể). Không tự biến thao tác trừ số dư hoặc giành chỗ cuối thành an toàn; cần kiểm tra bất biến còn đúng dưới mọi thứ tự merge.
- **Application-level merge:** dùng version, lịch sử thay đổi và quy tắc cụ thể theo trường/đối tượng, đôi khi cần người dùng chọn xung đột.
- **Escrow/quota allocation:** chia trước quyền tiêu thụ (ví dụ từng region được cấp tối đa N đơn vị hàng); mỗi vùng chỉ dùng quota đã được cấp, rồi tái phân bổ qua giao thức nhất quán.
- **Globally consistent database:** sử dụng hệ quản trị có giao dịch/quorum được thiết kế cho liên vùng, kiểm tra đúng mô hình isolation, phạm vi transaction và hành vi khi mất quorum.

Không phải sản phẩm mang nhãn “global”, “multi-master” hay “active-active” đều bảo đảm serializability, global uniqueness hoặc RPO bằng 0. Phải đọc hợp đồng consistency của **đúng dịch vụ, phiên bản và chế độ triển khai**; sau đó kiểm thử với mẫu tải và failure mode dự kiến.

### 6.4. Bảng quyết định

| Mô hình | Quyền ghi cùng một entity | Độ trễ ghi điển hình | Độ phức tạp và đánh đổi |
| --- | --- | --- | --- |
| Một primary + replica khác vùng | Một writer | Client xa phải đi đến primary | Khá đơn giản; cần giải bài toán failover và RPO với async replication |
| Single-writer theo key/partition | Một writer cho mỗi key | Ghi tại owner, có thể qua vùng khác | Routing/ownership phức tạp hơn; cross-partition transaction khó |
| Multi-writer + merge theo nghiệp vụ | Nhiều writer | Có thể ghi cục bộ nhanh | Phải chứng minh bất biến vẫn đúng hoặc chấp nhận sửa sai |
| Database đồng thuận liên vùng | Leader/quorum theo hợp đồng DB | Có thể thêm RTT mạng liên vùng | Đổi latency/availability/chi phí lấy consistency; cần hiểu quorum placement |
| Chỉ đọc đa vùng, ghi tại primary | Một writer | Đọc gần, ghi xa | Dễ cache; xử lý read-your-writes rõ ràng |

Chọn mô hình dựa vào **RPO/RTO, latency mục tiêu, tần suất ghi cạnh tranh, bất biến, residency và năng lực vận hành**, không dựa vào số region như một chỉ số thành công.

## 7. Xung đột dữ liệu: giải theo nghiệp vụ, không chỉ theo đồng hồ

### 7.1. Những chiến lược hay bị dùng sai

**Last-write-wins**:

- Có thể dùng cho một vài thuộc tính mà mất cập nhật là chấp nhận được, ví dụ trạng thái hiển thị tạm thời.
- **Không** phù hợp cho ledger, tồn kho hay số lượng voucher nếu thao tác cạnh tranh có tác động vật lý/tài chính.
- Dựa vào physical timestamp dễ chịu ảnh hưởng clock skew; ngay cả logical clock hay hybrid logical clock cũng không tự bảo vệ mọi bất biến nghiệp vụ.

**Blind merge JSON**: ghi đè từng trường hoặc union toàn đối tượng có thể tạo trạng thái không tồn tại ở bất kỳ bản ghi hợp lệ nào. Phải định nghĩa semantics và version cho từng trường liên quan.

**“Để replication tự giải quyết”**: replication chỉ chuyển dữ liệu; việc phát hiện và giải quyết xung đột tùy cơ chế của database, không đồng nghĩa với một giao dịch nghiệp vụ hợp lệ.

**“Retry đến khi thành công”**: khi mất phản hồi, retry có thể làm lại tác động tài chính hoặc bán vượt tồn nếu thiếu operation ID ổn định và deduplication.

### 7.2. Bảng chính sách xử lý xung đột

| Nghiệp vụ | Khi hai vùng cùng yêu cầu | Quy tắc nên định nghĩa |
| --- | --- | --- |
| Trừ 1 sản phẩm cuối | Cả hai thấy còn 1 | Chỉ owner/quorum được cấp quyền; hoặc quota tách sẵn. Yêu cầu còn lại bị từ chối/chờ. |
| Thay đổi số dư | Hai giao dịch rút tiền đồng thời | Một ledger/serialization boundary cho số dư liên quan, không LWW. |
| Giỏ hàng “thêm sản phẩm” | Cả hai thêm các dòng khác nhau | Có thể hợp nhất theo operation identity và semantics của giỏ; tránh cộng lại cùng event retry. |
| Sửa hai trường profile độc lập | Hai trường không ảnh hưởng nhau | Merge theo trường/version; nếu cùng trường thì hiển thị/xử lý xung đột. |
| Tạo username | Hai nơi lấy cùng tên | Cần đặt chỗ/unique global hoặc namespace phân vùng. |
| Bộ đếm lượt xem | Hai nơi tăng độc lập | Cộng theo CRDT/counter, dùng unique operation nếu sự kiện được giao ít nhất một lần. |

### 7.3. Version, idempotency và thứ tự sự kiện

Một phần quan trọng là phân biệt **cập nhật đồng thời** với **nhận lại cùng thao tác**:

- **Idempotency key** xác định cùng một yêu cầu nghiệp vụ được retry. Key phải ổn định qua đổi region; vùng mới phải đọc được bằng chứng request đã được xử lý hoặc có quy trình phục hồi thích hợp.
- **Entity version** hoặc điều kiện compare-and-swap giúp phát hiện lost update tại nơi có quyền ghi.
- **Operation ID** được lưu với kết quả nghiệp vụ để không nhân đôi tác động.
- **Event ID / aggregate version** giúp consumer bỏ trùng, nhận biết event cũ hoặc sắp xếp lại theo quy tắc.
- **Transactional Outbox** giúp commit trạng thái cục bộ cùng ý định phát event, nhưng không giải quyết quyền ghi đồng thời ở hai region.

Ví dụ SQL sau **chỉ đúng khi nó chạy trên một owner nhất quán của SKU**; thực hiện câu lệnh giống nhau ở hai database đa chủ sao chép bất đồng bộ vẫn có thể bán vượt tồn:

~~~sql
-- Các thao tác thuộc cùng một transaction tại DB của owner hiện hành.
-- Bước kiểm tra quyền sở hữu/epoch phải được enforce bởi write path.
UPDATE sku_inventory
SET available = available - :quantity,
    reserved = reserved + :quantity,
    version = version + 1
WHERE sku = :sku
  AND warehouse_id = :warehouse_id
  AND available >= :quantity
  AND version = :expected_version
RETURNING version;
~~~

Nếu không có dòng nào được cập nhật, ứng dụng phải phân biệt thiếu hàng, version cũ hoặc chuyển owner; không tự động gửi lại vô hạn. Reservation, deduplication record và outbox event phải được lưu **cùng giao dịch cục bộ** khi sử dụng pattern đó.

## 8. Kiến trúc sửa phản mẫu: ví dụ hệ thống đơn hàng

### 8.1. Yêu cầu giả định

Một doanh nghiệp bán lẻ phục vụ khách ở nhiều châu lục:

- API cần sẵn sàng khi một region ứng dụng hỏng.
- Không được bán vượt tồn kho thực tế của cùng **SKU + warehouse**.
- Yêu cầu đặt hàng được gửi lại do timeout không tạo hai đơn hoặc hai lần thanh toán.
- Trang danh mục có thể đọc từ replica/cache trễ; màn hình xác nhận thanh toán cần dữ liệu mới.
- Độ trễ đặt hàng, mức mất dữ liệu chấp nhận và thời gian khôi phục phải được chốt với nghiệp vụ trước khi chọn công nghệ.

Một phương án có thể bắt đầu bằng **multi-region application + single-owner cho từng stock bucket**:

~~~mermaid
flowchart TB
    U[Người mua] --> EDGE[Global Edge / WAF / DNS]
    EDGE --> APP_A[Order API - Region A]
    EDGE --> APP_B[Order API - Region B]

    APP_A --> DIR[Ownership Directory / Routing]
    APP_B --> DIR
    DIR -->|SKU/warehouse thuộc owner A| INV_A[Inventory Write Owner A]
    DIR -->|SKU/warehouse thuộc owner B| INV_B[Inventory Write Owner B]

    INV_A --> DB_A[(Transactional Store A)]
    INV_B --> DB_B[(Transactional Store B)]
    DB_A --> OB_A[Outbox A]
    DB_B --> OB_B[Outbox B]
    OB_A --> BUS[(Event Bus)]
    OB_B --> BUS
    BUS --> SAGA[Saga / Reconciliation]
    SAGA --> PAY[Payment Service với idempotency]
    PAY --> PSP[Payment Provider]
~~~

**Chú ý về sơ đồ:** Ownership Directory phải được xây trên một cơ chế có quy tắc nhất quán đủ mạnh cho quyền ghi. Mũi tên từ directory tới owner diễn tả logic định tuyến; ứng dụng thực tế phải **enforce quyền ở nơi ghi**, không chỉ kiểm tra routing tại gateway.

### 8.2. Luồng ghi an toàn

1. Khách gửi yêu cầu tạo đơn với **Idempotency-Key**.
2. Order API tra cứu hoặc tạo định danh đơn theo một cơ chế sở hữu thống nhất; khi retry phải trả về cùng kết quả hoặc thông báo tiến trình đã nhận.
3. Saga xác định stock bucket và owner hiện hành cho mỗi yêu cầu giữ hàng.
4. Inventory owner kiểm tra quyền/epoch và số tồn còn lại trong transaction, lưu reservation cùng outbox event.
5. Payment Service ủy quyền thanh toán với khóa idempotency ổn định tại cổng thanh toán.
6. Chỉ sau khi giữ hàng và thanh toán đã thành công theo chính sách, Order Service xác nhận đơn.
7. Nếu một bước thất bại, saga chạy hành động bù trừ tương ứng; nếu trạng thái PSP chưa rõ, tiến hành đối soát trước khi thử lại.

Đối với đơn có nhiều stock bucket thuộc các owner khác nhau, không có transaction toàn cục miễn phí. Có thể dùng saga giữ từng phần và giải phóng khi một phần thất bại; cần chấp nhận khoảng thời gian trung gian. Nếu nghiệp vụ yêu cầu **hoặc giữ tất cả ngay lập tức hoặc không giữ gì** theo isolation mạnh, phải thay đổi boundary hoặc dùng cơ sở dữ liệu/điều phối có bảo đảm tương ứng.

### 8.3. Những giới hạn vẫn cần thừa nhận

Mô hình trên ngăn hai region cùng ghi một stock bucket khi ownership được enforce đúng. Nhưng ứng dụng có thể vẫn bị ảnh hưởng bởi:

- Region owner hỏng làm ghi của partition đó chậm/không khả dụng trước khi failover.
- Directory chưa cập nhật ở client khiến request phải được redirect/retry.
- Replica đọc trễ khiến khách nhìn số lượng khác với lúc checkout.
- Saga nhiều bước phải có compensation khi payment thất bại.
- Quá trình chuyển owner cần xử lý các operation đang chạy và kết quả không rõ ràng.

Đó là các đánh đổi phải ghi trong kiến trúc; không thể loại bỏ chúng chỉ bằng thêm load balancer hay database replica.

## 9. Failover: chuyển quyền ghi trước khi chuyển traffic

### 9.1. Phân biệt cơ chế định tuyến và cơ chế quyền ghi

**Traffic failover** chỉ chuyển request tới endpoint khác. **Data failover** là quá trình xác định dữ liệu đủ điều kiện để phục vụ và ai có quyền commit. Nếu chuyển traffic trước khi cô lập writer cũ, hệ thống dễ rơi vào split-brain.

Quy trình tham chiếu cho single-writer:

~~~mermaid
flowchart TD
    D[Phát hiện sự cố / tín hiệu nhiều nguồn] --> H{Có bằng chứng writer cũ đã bị fencing?}
    H -->|Chưa| STOP[Giữ thao tác ghi nhạy cảm ở chế độ chờ / read-only]
    STOP --> F[Cô lập hoặc fencing writer cũ bằng cơ chế có thẩm quyền]
    H -->|Có| R[Kiểm tra lag và tính toàn vẹn của replica]
    F --> R
    R --> Q{Dữ liệu đáp ứng RPO và điều kiện promote?}
    Q -->|Không| DEC[Quyết định phục hồi / mất dữ liệu theo runbook và thẩm quyền]
    Q -->|Có| P[Promote writer mới, tăng epoch]
    DEC --> P
    P --> T[Đổi routing và kiểm tra reject stale epoch]
    T --> V[Kiểm tra giao dịch thử, idempotency và monitor]
    V --> REC[Đối soát những thao tác trạng thái chưa rõ]
~~~

Sơ đồ mang tính nguyên tắc. Thực tế không được promote một replica chỉ vì “thời gian chờ đã hết” nếu không chứng minh rằng writer cũ đã bị fencing hoặc cơ chế consensus bảo đảm không có hai writer có thẩm quyền.

### 9.2. Runbook vận hành chi tiết

| Giai đoạn | Hành động | Điều kiện tiếp tục |
| --- | --- | --- |
| **Detect** | Kết hợp health app, DB, mạng và replication; xác định phạm vi ảnh hưởng | Loại trừ lỗi gateway cục bộ gây false positive |
| **Decide** | So sánh gián đoạn, độ trễ và RPO/RTO với mức chấp nhận | Có người/cơ chế có thẩm quyền quyết định chế độ failover |
| **Fence** | Thu hồi lease/epoch hoặc chặn writer cũ ở storage; có thể đưa write path sang read-only | Có bằng chứng writer cũ không còn commit hợp lệ |
| **Catch up / Assess** | Kiểm tra replica lag, commit position, thao tác chưa ack | Biết mức RPO thực tế và rủi ro các operation chưa rõ |
| **Promote** | Cấp epoch/owner mới và khởi tạo read/write path | Region mới đáp ứng bất biến/consistency cần thiết |
| **Route** | Đổi traffic manager, làm mới client routing, xử lý retry | Request ghi nhạy cảm được route đúng owner |
| **Verify** | Canaries, giao dịch thử, cảnh báo lặp, outbox/queue lag | Các phép đo và bất biến ổn định |
| **Reconcile** | Đối soát order, payment, inventory, event chưa đồng bộ | Không có tác động tài chính bị nhân đôi hoặc bỏ sót |
| **Failback** | Khôi phục region cũ như replica, đồng bộ và chuyển quyền có kiểm soát | Không bật lại quyền ghi cũ khi còn epoch lỗi thời |

Khi không thể fencing an toàn, phương án đúng có thể là **tạm ngừng ghi vào dữ liệu nhạy cảm** hoặc degraded mode: cho phép xem danh mục, xem nội dung đã cache, nhưng tạm khóa checkout/chuyển tiền. Giữ bất biến tài chính thường quan trọng hơn “API luôn trả 200”.

### 9.3. Failback cũng là một lần chuyển owner

Region A trở lại không có nghĩa tự động cho A nhận ghi. Trước khi failback:

1. Rebuild A từ nguồn có thẩm quyền và đưa A theo kịp writer hiện hành.
2. Xử lý các transaction chưa rõ, message bị lặp và dữ liệu phân kỳ còn lại.
3. Tạo epoch mới, fence writer hiện hành theo quy trình, chuyển owner rồi chuyển routing.
4. Xác minh A chấp nhận epoch mới và B từ chối ghi từ epoch cũ.

Không thực hiện “failback ngầm” chỉ dựa vào trọng số DNS mặc định.

## 10. Thiết kế nhất quán có chủ đích

### 10.1. Đọc và ghi không nhất thiết cùng SLA

Một ứng dụng có thể chia yêu cầu theo mức nhất quán:

| Tác vụ | Mức nhất quán cần xem xét | Hành vi khi region gần nhất chỉ có dữ liệu cũ |
| --- | --- | --- |
| Xem danh mục | Eventual consistency với giới hạn trễ | Dùng cache/replica và hiển thị thời điểm cập nhật khi cần |
| Xem trạng thái đơn vừa tạo | Read-your-writes / session consistency | Đọc từ owner hoặc chờ replica bắt kịp commit token |
| Giữ hàng tồn | Atomic conditional write trên owner của bucket | Chuyển tới owner; nếu unavailable thì chờ/từ chối tạm |
| Chuyển số dư | Transaction/isolation phù hợp ledger | Không chấp nhận ghi ở replica thiếu dữ liệu |
| Cập nhật sở thích UI | Có thể cho phép merge theo trường | Áp dụng quy tắc giải quyết xung đột đã thống nhất |

**Sự rõ ràng của API quan trọng:** kết quả “đã tiếp nhận để xử lý” khác với “đã commit” và khác với “đã đồng bộ trên các vùng”. Trả về một trạng thái mơ hồ có thể khiến client retry gây tác động lặp.

### 10.2. Quorum và khả năng chịu lỗi

Một nền tảng dùng consensus/quorum để chọn leader có thể giảm nguy cơ split-brain nếu cơ chế ghi yêu cầu quorum có thẩm quyền. Tuy nhiên, quorum ở đâu ảnh hưởng khả năng ghi:

- Nếu phần lớn voting replicas ở cùng Region A, mất A có thể làm cụm mất quorum dù B còn ứng dụng chạy.
- Phân bố quorum giữa nhiều failure domain hỗ trợ khả năng chịu lỗi nhưng tăng chi phí và độ trễ mạng.
- Một witness không chứa dữ liệu không nhất thiết thay thế được replica dữ liệu đủ điều kiện promote; phải hiểu chính xác vai trò của nó trong sản phẩm.
- Quorum có thể cố ý từ chối ghi trong một số dạng partition, đổi availability để duy trì nhất quán.

Không nên tự thiết kế hệ consensus từ một bảng “leader=true” trên hai DB bất đồng bộ. Nếu không có nhu cầu đặc biệt, sử dụng khả năng quản trị leader/replication đã được kiểm chứng của nền tảng dữ liệu.

### 10.3. Sao chép dữ liệu không thay thế backup

Lỗi logic như xóa nhầm bảng, cập nhật sai hàng loạt hoặc ransomware có thể nhanh chóng lan sang mọi region thông qua replication. Cần backup với retention và quyền truy cập độc lập, kiểm tra khôi phục, bảo vệ key/secret, và xác định khả năng phục hồi tới thời điểm cụ thể. Multi-region HA và disaster recovery backup giải quyết những lớp rủi ro khác nhau.

## 11. Sizing, chi phí và độ trễ

Giả sử hệ thống xử lý **W ghi/giây**, kích thước dữ liệu phải nhân bản bình quân **S byte/ghi**, số đích replica khác khu vực là **N**. Băng thông replication thô ước tính:

~~~text
replication_egress_bytes_per_second ≈ W × S × N
~~~

Đây chỉ là điểm bắt đầu: phải cộng WAL/metadata, indexes, retry, snapshot, compression, độ trễ network, dữ liệu đọc và lưu lượng đối soát. Chưa thể dùng biểu thức này làm hóa đơn thực tế.

Độ trễ của một commit đồng bộ liên vùng thường chịu thêm **network round-trip** đến các participant cần xác nhận. Vị trí các region, quorum policy và vị trí client ảnh hưởng latency p95/p99. Nếu giữ mọi thứ ở chế độ local write rồi đồng bộ sau, latency có thể thấp nhưng rủi ro conflict/RPO khác 0 tăng. Không thể đánh giá một phương án chỉ bằng latency trung bình lúc mạng khỏe.

Đặt ngân sách cho những yếu tố thường bị bỏ quên:

- Phí truyền dữ liệu liên vùng và lưu lượng cross-region synchronous writes.
- Nhân bản database, broker, cache, storage, backup và log.
- Năng lực vận hành 24/7: failover drill, incident response, đối soát dữ liệu, hỗ trợ xung đột.
- Chi phí tài nguyên dự phòng đủ tải khi một khu vực ngừng hoạt động.
- Gia tăng độ phức tạp của deployment, schema migration và kiểm soát thay đổi theo nhiều region.

**Kiểm chứng bằng tải đại diện:** ghi nóng trên cùng một SKU/ledger account có thể bị tranh chấp dù tổng throughput hệ thống còn thấp. Benchmark chỉ có các key phân tán đồng đều dễ che giấu vấn đề.

## 12. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cần trả lời | Biện pháp thiết kế |
| --- | --- | --- |
| **Reliability** | Khi mất 1 region hoặc 1 đường mạng, có hai writer không? RPO/RTO có được đo không? | Ownership, fencing, quorum phù hợp, backup, failover drill, reconciliation |
| **Security** | Dữ liệu và key có được phép rời quốc gia/khu vực? Ai có quyền promote writer? | IAM tối thiểu, encryption, audit, data residency, quyền failover có kiểm soát |
| **Operational Excellence** | Có phát hiện split-brain, mất replication và dữ liệu phân kỳ trước khi khách báo không? | Runbook, SLO, trace, dashboard, canary, chaos drill, điều tra sự cố |
| **Performance Efficiency** | Ghi xuyên vùng tăng latency đến mức nào? Hot key xử lý ra sao? | Routing theo owner, tách đọc/ghi, cache và partition hợp lý, đo p95/p99 |
| **Cost Optimization** | Nhiều region tạo thêm replica, egress và chi phí nhân lực bao nhiêu? | Chỉ đa vùng với workload có yêu cầu rõ, tối ưu replication và retention |
| **Sustainability** | Các region dự phòng được sử dụng và scale hợp lý chưa? | Giảm nhân bản không cần thiết, theo dõi hiệu suất tài nguyên, scale theo tải thực |

### 12.1. Bảo mật và tuân thủ khi sao chép nhiều khu vực

Một bản sao dữ liệu sang region khác có thể thay đổi phạm vi xử lý dữ liệu theo quy định, hợp đồng và yêu cầu khách hàng. Cần lập bản đồ những nơi dữ liệu ở trạng thái lưu trữ, log, backup, cache, DR snapshot và event; tránh chỉ kiểm tra database chính.

Xem xét:

- Mã hóa dữ liệu khi truyền và khi lưu; quản lý khóa, phạm vi key và tình huống mất quyền truy cập KMS ở một region.
- Danh tính dịch vụ và quyền ghi riêng theo owner; quyền promote hoặc đổi routing là quyền nhạy cảm.
- Kiểm soát egress, firewall, private connectivity và bảo vệ endpoint nội bộ.
- Audit các quyết định failover, thay owner, truy cập snapshot và thao tác sửa xung đột.
- Phân tách thông tin định danh, dữ liệu tài chính và log; chỉ sao chép dữ liệu cần thiết cho mục tiêu nghiệp vụ.

### 12.2. Observability để thấy sự cố logic

Các metric khuyến nghị:

| Nhóm | Metric / tín hiệu | Mục đích |
| --- | --- | --- |
| Ownership | Số owner đồng thời cho cùng key, stale epoch rejection | Phát hiện nguy cơ split-brain |
| Replication | Lag theo thời gian/commit position, backlog, apply errors | Đánh giá độ trễ và RPO trước failover |
| Consistency | Conflict rate, divergence rate, kết quả đối soát | Phát hiện dữ liệu phân kỳ, mất cập nhật |
| Business invariants | Số tồn âm, duplicate payment, cấp phát trùng, lệch sổ cái | Đo tính đúng đắn nghiệp vụ |
| Traffic | Cross-region write hops, routing retry, p95/p99 latency | Hiểu tác động latency và failover |
| Recovery | Thời gian fencing, promotion, converged replication, failback | Kiểm chứng RTO thay vì chỉ diễn tập bằng lý thuyết |
| Reliability | Số request rejected do partition/quorum, số write ở degraded mode | Đánh giá lựa chọn availability-consistency |

Ghi log cấu trúc kèm **entity key, owner region, epoch/term, operation ID, correlation ID, entity version và replication position** ở mức không làm lộ dữ liệu nhạy cảm. Log chỉ có “success” mà thiếu thông tin quyền ghi sẽ khó điều tra split-brain.

## 13. Thực hành đánh giá kiến trúc

### 13.1. Bài toán

Một đội phát triển đề xuất chạy checkout ở Region A và B, hai database đều writable. Dữ liệu hai bên sao chép hai chiều bất đồng bộ; xung đột được đặt là **LWW theo updated_at**. Họ lập luận rằng nếu một vùng mất thì vùng còn lại vẫn có thể bán hàng ngay, nên độ tin cậy tăng.

Yêu cầu:

1. Liệt kê ít nhất **ba bất biến** mà LWW có thể không bảo vệ.
2. Mô tả hai request đồng thời mua sản phẩm cuối cùng ở hai region; tại sao cả hai đều có thể thành công?
3. Thiết kế quyền ghi cho **SKU + warehouse**, chỉ rõ vùng nào quyết định lượng tồn khả dụng.
4. Xác định hành vi khi một region mất kết nối nhưng chưa chắc đã chết: dừng loại thao tác nào, có thể tiếp tục loại thao tác nào?
5. Xác định ai/điều gì có quyền promote và cơ chế nào chặn writer cũ ghi tiếp.
6. Chọn RPO/RTO mục tiêu theo nghiệp vụ rồi kiểm tra replication mode có đáp ứng thật hay không.
7. Đề xuất cách phát hiện sự khác nhau giữa “bản ghi mới chưa đến” với “hai cập nhật cạnh tranh đã được xác nhận”.

**Hướng xử lý mẫu:** Giữ owner đơn nhất cho mỗi stock bucket hoặc dùng cơ chế reservation/escrow nhất quán. Bảo vệ idempotency của tạo đơn và thanh toán, không dùng LWW cho tồn kho. Với network partition, chỉ vùng còn quyền sở hữu hợp lệ được commit thao tác giữ hàng; vùng còn lại trả trạng thái chờ/tạm từ chối hoặc chuyển đến owner nếu có thể. Nếu chuyển owner, phải fencing và biết rủi ro RPO trước khi promote.

### 13.2. Ma trận kiểm thử lỗi

| Fault injection | Kết quả cần quan sát |
| --- | --- |
| Cắt đường mạng giữa A và B nhưng client vẫn truy cập cả hai | Không có hai write owner cùng commit một key |
| Cho A nhận ghi, làm B chậm replication, sau đó route client sang B | Đọc mới nhất theo chính sách; không tái phát hành tác động đã xử lý |
| Làm leader cũ pause rồi promote leader mới | Lệnh write mang epoch cũ bị từ chối tại điểm thực thi |
| Kill process sau commit local nhưng trước khi trả HTTP | Retry cùng operation ID không tạo tác động thứ hai |
| Cho hai khách đặt SKU cuối cùng đồng thời ở hai region | Tối đa một reservation được xác nhận hợp lệ |
| Tắt một thành viên quorum quan trọng | Hành vi ghi đúng tài liệu consistency và failure model; không tự mở ghi sai |
| Cho replication lag tăng rồi yêu cầu failover | Cơ chế xét điều kiện RPO hoạt động; không âm thầm coi dữ liệu đã đồng bộ |
| Khôi phục region cũ sau failover | Region cũ bắt đầu là replica/standby, không tự trở lại writer |
| Gửi lại hoặc đảo thứ tự event | Consumer xử lý idempotent và kiểm tra version |
| Khôi phục từ backup với thiếu giao dịch mới | Có đối soát payment/order và quy trình xác định dữ liệu chênh |

Kiểm thử nên dùng môi trường được cô lập, dữ liệu giả lập và kịch bản có khả năng phục hồi. Đo đồng thời **độ sẵn sàng được cảm nhận** và **tính đúng đắn của bất biến**; chỉ đo số HTTP 200 là thiếu.

### 13.3. Checklist trước khi phê duyệt triển khai

- [ ] Nêu rõ bài toán cần multi-region (DR, độ trễ, residency) và SLO nghiệp vụ.
- [ ] Phân loại dữ liệu được ghi: key nào độc lập, key nào có bất biến cần bảo vệ?
- [ ] Mỗi consistency boundary có mô hình quyền ghi được mô tả và enforce tại storage.
- [ ] Có chính sách xử lý concurrent write, duplicate, stale read và out-of-order event.
- [ ] Không dùng timestamp/LWW cho dữ liệu tài chính hoặc cấp phát tài nguyên nếu chưa chứng minh an toàn nghiệp vụ.
- [ ] Replication mode, phạm vi durability và RPO thực tế được hiểu đúng.
- [ ] Failover bao gồm fencing, kiểm tra replica, promotion, routing và reconciliation.
- [ ] Failback không tự mở quyền ghi cũ; có epoch/term/owner mới hợp lệ.
- [ ] Idempotency được giữ xuyên region cho API và các hệ thống ngoài như payment.
- [ ] Có metrics phát hiện sai bất biến, conflict và replication lag.
- [ ] Kiểm thử network partition, lost ack, duplicate, delayed replication và failback.
- [ ] Ước tính độ trễ liên vùng, chi phí egress, dữ liệu cư trú và năng lực vận hành.

## 14. Kết luận

**Phản mẫu không nằm ở việc dùng nhiều khu vực, mà ở việc cho nhiều khu vực cùng ra quyết định ghi trên một tập dữ liệu mà chưa định nghĩa ai có thẩm quyền và xử lý xung đột thế nào.** Hậu quả có thể là mất cập nhật, bán vượt tồn, thanh toán lặp, split-brain hoặc mất các ghi từng được xác nhận thành công.

Thiết kế vững phải bắt đầu từ **bất biến nghiệp vụ → ranh giới nhất quán → quyền ghi → replication/failover → cơ chế phát hiện và xử lý sai lệch**. Sau đó mới chọn mô hình single-writer, partitioned owner, multi-writer có merge semantics, hay database đồng thuận toàn cầu phù hợp. Một hệ thống đáng tin cậy là hệ thống biết **khi nào được phép ghi, khi nào phải từ chối/chờ và làm sao phục hồi mà không phá vỡ dữ liệu**.
