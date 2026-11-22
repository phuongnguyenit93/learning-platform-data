# Đánh giá độ bền khi dùng làm nguồn dữ liệu chính

## 1. Vì sao hệ khóa–giá trị cần được đánh giá độ bền riêng?

Trong mô hình **khóa–giá trị (key–value)**, ứng dụng tìm dữ liệu qua một khóa định danh:

~~~text
user:U102:profile    -> {"name":"An","status":"ACTIVE"}
cart:U102            -> {"items":[{"sku":"P10","qty":2}]}
order:O9001          -> {"userId":"U102","status":"PAID"}
~~~

Thao tác đọc/ghi theo khóa thường đơn giản, nhanh và có thể mở rộng tốt. Vì vậy, nhiều nhóm phát triển cân nhắc đưa key–value store từ vai trò **cache** sang vai trò **nguồn dữ liệu chính (system of record/source of truth)**.

Nhưng “đọc nhanh” và “có dữ liệu sau khi khởi động lại” không đủ để kết luận rằng một cơ sở dữ liệu có độ bền phù hợp với nghiệp vụ. Khi là nguồn dữ liệu chính, hệ thống cần trả lời:

> Sau khi ứng dụng nhận được xác nhận ghi thành công, dữ liệu đó còn tồn tại khi tiến trình chết, máy chủ hỏng, mạng bị chia cắt hoặc một vùng hạ tầng ngừng hoạt động không? Nếu xảy ra mất dữ liệu hoặc xóa nhầm, hệ thống khôi phục được đến thời điểm nào, trong bao lâu và bằng chứng nào xác nhận kết quả?

Không có một câu trả lời chung cho mọi NoSQL/key–value store. Một **cache in-memory không lưu bền vững**, một **Redis có RDB/AOF**, một **engine key–value ghi trực tiếp xuống đĩa**, và một **dịch vụ key–value được quản lý có lưu trữ nhân bản** có các hợp đồng xác nhận ghi và khôi phục rất khác nhau.

### 1.1. Cache khác nguồn dữ liệu chính ở chỗ nào?

Xét cùng một giỏ hàng:

- Nếu cơ sở dữ liệu quan hệ lưu giỏ hàng gốc và key–value chỉ lưu bản cache, mất một khóa cache có thể khôi phục từ hệ nguồn. Người dùng có thể thấy chậm tạm thời nhưng dữ liệu gốc vẫn còn.
- Nếu key–value là nơi **duy nhất** lưu giỏ hàng, việc mất khóa có nghĩa là mất dữ liệu nghiệp vụ, trừ khi còn bản sao lưu có thể phục hồi.

Với đơn đã thanh toán, sổ cái, hạn mức tín dụng hay quyền truy cập có thu phí, hậu quả của mất một bản ghi thường lớn hơn việc phải tạo lại một phiên truy cập. **Mức độ nghiêm trọng của mất dữ liệu** mới quyết định độ bền cần có, chứ không phải tên hệ quản trị.

## 2. Phân biệt các thuộc tính thường bị gộp làm một

| Thuộc tính | Câu hỏi kiểm chứng | Ví dụ |
| --- | --- | --- |
| **Durability (độ bền)** | Ghi đã xác nhận có sống sót qua những loại sự cố đã cam kết không? | Máy chủ khởi động lại nhưng đơn hàng đã commit vẫn có |
| **Consistency (nhất quán)** | Một lần đọc sẽ thấy phiên bản nào và các bất biến có được giữ không? | Không cho hai cập nhật đồng thời ghi đè sai số dư |
| **Availability (sẵn sàng)** | Dịch vụ có tiếp tục trả lời khi thành phần bị lỗi không? | Mất một node, hệ vẫn phục vụ yêu cầu |
| **Recoverability (khả năng phục hồi)** | Có thể đưa dữ liệu và ứng dụng trở lại sau sự cố hay xóa nhầm không? | Phục hồi bản ghi về thời điểm trước khi xóa |
| **Integrity (toàn vẹn)** | Dữ liệu có đúng quan hệ và quy tắc nghiệp vụ không? | Không tồn tại trạng thái PAID thiếu mã giao dịch |
| **Persistence (lưu bền vững)** | Có cơ chế ghi trạng thái từ bộ nhớ xuống vật liệu lưu trữ không? | Append log được đồng bộ xuống đĩa |

**Lưu bền vững là một cơ chế góp phần tạo độ bền, không phải toàn bộ bảo đảm độ bền.** Có file trên đĩa nhưng file nằm cùng một máy bị phá hủy vẫn có thể mất hết. Có nhiều replica nhưng chúng cùng nhận lệnh xóa nhầm thì dữ liệu vẫn biến mất. Có backup nhưng chưa thử restore thì chưa biết chắc phục hồi được.

Tương tự, đọc nhất quán mạnh không tự bảo đảm bản ghi bền qua lỗi đĩa; ghi bền cũng không tự giải quyết cập nhật đồng thời hoặc giao dịch nhiều khóa.

## 3. Định nghĩa hợp đồng độ bền của một lần ghi

Trước khi đánh giá sản phẩm, xác định rõ **thành công** nghĩa là gì. Một lần ghi có thể đi qua các lớp sau:

~~~mermaid
flowchart TD
    A["Ứng dụng gửi PUT(key, value)"] --> B["Nút nhận yêu cầu"]
    B --> C["Cập nhật trạng thái trong bộ nhớ"]
    C --> D["Ghi log / cấu trúc lưu trữ"]
    D --> E["Đồng bộ xuống thiết bị lưu trữ"]
    E --> F["Nhân bản tới các nút khác"]
    F --> G["Xác nhận ghi cho ứng dụng"]
~~~

Sơ đồ này chỉ minh họa các giai đoạn có thể có; **thứ tự thật và giai đoạn nào phải hoàn tất trước khi trả ACK phụ thuộc hệ quản trị, cấu hình và loại thao tác**. Có sản phẩm trả ACK sau khi cập nhật bộ nhớ. Có sản phẩm chờ log cục bộ. Có sản phẩm chờ một tập replica xác nhận theo quorum/consensus. Không nên suy diễn điều đó từ việc cơ sở dữ liệu có ba node.

### Ví dụ cửa sổ mất dữ liệu

Giả sử một cache store sử dụng ghi vào bộ nhớ và định kỳ đồng bộ log xuống đĩa:

~~~text
10:00:00.000  Client ghi order:O9001 = PAID
10:00:00.010  Server trả OK
10:00:00.350  Máy chủ mất điện
10:00:01.000  Lần đồng bộ log dự kiến chưa kịp diễn ra
~~~

Nếu ACK ở **10:00:00.010** không đợi dữ liệu được lưu bền vững, bản ghi có thể mất sau khi máy chủ khởi động lại. Khoảng thời gian giữa việc trả ACK và việc dữ liệu đạt đến lớp lưu trữ được cam kết là một **cửa sổ mất dữ liệu**.

Ngay cả khi ghi đã đồng bộ xuống đĩa, vẫn phải xem lỗi cả ổ đĩa, lỗi cả máy, lỗi trung tâm dữ liệu và cơ chế chuyển leader. Lời hứa “ghi thành công” chỉ có ý nghĩa khi **loại lỗi được bảo vệ** và **điều kiện ACK** được nói rõ.

## 4. Lập ma trận sự cố trước khi chọn sản phẩm

Các lỗi sau có tác động rất khác nhau:

| Sự cố | Điều cần xác minh | Rủi ro nếu không được bảo vệ |
| --- | --- | --- |
| Ứng dụng restart | Cơ sở dữ liệu tồn tại độc lập với ứng dụng? | Mất trạng thái đặt trong bộ nhớ tiến trình |
| Tiến trình database crash | Log/trạng thái đã flush và recovery có đúng? | Mất các ghi chưa bền; log bị lỗi hoặc khởi động lại chậm |
| Node mất điện đột ngột | ACK có đợi durable write không? | Mất ghi đã trả thành công |
| Mất ổ đĩa/máy chủ | Dữ liệu có replica trên miền lỗi khác không? | Mất toàn bộ dữ liệu nằm trên máy đó |
| Leader fail, replica lên thay | Replica được chọn có đủ các ghi đã ACK không? | Ghi đã được xác nhận có thể biến mất sau failover |
| Network partition | Chính sách quorum và khả dụng ra sao? | Hai phía ghi xung đột, từ chối ghi hoặc đọc dữ liệu cũ |
| Sự cố cả vùng hạ tầng | Có sao chép và phục hồi liên vùng đúng yêu cầu không? | Ngừng dịch vụ hoặc mất dữ liệu phạm vi vùng |
| Xóa nhầm/bug ghi đè | Có lịch sử phiên bản, PITR, bản backup độc lập không? | Replica cũng xóa/ghi đè theo dữ liệu sai |
| Dữ liệu hỏng logic | Có cách phát hiện và phục hồi một tập khóa không? | Giá trị sai vẫn được nhân bản thành công |
| Sai thao tác vận hành | Restore có được diễn tập và kiểm soát quyền không? | Có backup nhưng không phục hồi được đúng cách |

Không phải tất cả ứng dụng đều cần chống chịu tất cả các sự cố với cùng mức bảo đảm. Một bộ đếm tương tác có thể chấp nhận mất vài giây; sổ cái không thể tự ý mất một khoản ghi đã xác nhận.

## 5. RPO và RTO: chuyển yêu cầu mơ hồ thành chỉ tiêu

Hai khái niệm quan trọng khi đánh giá nguồn dữ liệu chính:

**RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa có thể chấp nhận, thường biểu diễn bằng thời gian. Ví dụ RPO 5 phút nghĩa là trong tình huống sự cố thuộc phạm vi thiết kế, tổ chức chấp nhận khả năng phải quay về một điểm dữ liệu cũ tối đa 5 phút. **RPO = 0** có nghĩa là mục tiêu không mất bản ghi đã được cam kết trong phạm vi sự cố tương ứng.

**RTO (Recovery Time Objective)** là mục tiêu thời gian khôi phục dịch vụ tới mức vận hành chấp nhận được sau sự cố.

Ví dụ đặt yêu cầu cho ba tập dữ liệu:

| Tập dữ liệu | Đặc điểm | Mục tiêu giả định để thảo luận |
| --- | --- | --- |
| Cache gợi ý sản phẩm | Tạo lại được từ nguồn chính | Có thể mất toàn bộ cache; RTO là thời gian warm-up |
| Giỏ hàng chưa thanh toán | Người dùng khó chịu nếu mất | RPO nhỏ; RTO đủ ngắn cho trải nghiệm mua hàng |
| Đơn hàng đã thanh toán | Có nghĩa vụ tài chính và kiểm toán | Cần bảo đảm ghi rất chặt; mục tiêu RPO thường phải gần hoặc bằng 0 cho lỗi đã định nghĩa |

Đây là **ví dụ về cách phân loại**, không phải con số SLA mặc định cho mọi doanh nghiệp. RPO/RTO phải được chủ sở hữu nghiệp vụ phê duyệt và kiểm chứng bằng diễn tập.

Ngoài RPO/RTO, cần nêu:

- Phạm vi lỗi: mất tiến trình, node, availability zone hay cả region?
- “Dữ liệu không mất” là các ghi đã ACK, hay cả yêu cầu đang xử lý khi kết nối đứt?
- Mục tiêu được đo trên môi trường nào, với kích thước dữ liệu bao nhiêu?
- Ai chịu trách nhiệm phát hiện mất dữ liệu, thực hiện restore và đối soát?

Không thể đánh giá RPO bằng cách chỉ đọc thông số tần suất backup. Tính bền của bản ghi trong vận hành bình thường, khả năng mất ghi khi failover và khả năng phục hồi sau xóa nhầm là ba khía cạnh khác nhau.

## 6. Các cách lưu dữ liệu của hệ key–value và đánh đổi

### 6.1. Chỉ lưu trong bộ nhớ

Một hệ giữ toàn bộ dữ liệu trong RAM và không bật persistence có độ trễ thấp, nhưng khi tiến trình/máy mất trạng thái thì dữ liệu biến mất. Cách này có thể hợp cho cache, phiên ngắn hạn hoặc dữ liệu tính lại được.

Nếu dùng làm nguồn chính, cần bảo đảm độ bền ở tầng khác, chẳng hạn ghi đồng bộ sang một hệ bền hơn trước khi ACK. Nếu không, bản chất của hệ là **volatile store**.

### 6.2. Snapshot định kỳ

Snapshot ghi trạng thái cơ sở dữ liệu tại một thời điểm ra file. Nếu snapshot gần nhất ở **10:00** và máy mất điện lúc **10:07**, những thay đổi sau mốc snapshot có thể không được phục hồi nếu không có cơ chế ghi bổ sung.

Snapshot hữu ích cho khởi động lại, sao lưu theo điểm thời gian và giảm lượng log phải phát lại. Nhưng lịch snapshot càng thưa thì cửa sổ mất dữ liệu có thể càng lớn. Việc tạo snapshot cũng có chi phí CPU, bộ nhớ, I/O và không nhất thiết phù hợp cho mọi kích thước dữ liệu.

### 6.3. Append-only log / write-ahead log

Một cách khác là ghi lịch sử lệnh hoặc thay đổi xuống log. Khi khởi động lại, hệ phát lại log để dựng trạng thái. Cần phân biệt:

1. Ghi vào bộ đệm hệ điều hành.
2. Yêu cầu hệ điều hành đồng bộ dữ liệu xuống thiết bị lưu trữ (ví dụ fsync).
3. Bảo đảm của ổ đĩa, hệ thống file và môi trường lưu trữ về dữ liệu đã đồng bộ.

Nếu chỉ ghi vào bộ đệm mà chưa fsync, một sự cố mất điện vẫn có thể làm mất dữ liệu. Đồng bộ thường xuyên giảm cửa sổ mất dữ liệu nhưng tăng độ trễ hoặc chi phí I/O. Cũng cần tính cơ chế kiểm tra/cắt phần log lỗi, replay, compact/rewrite và tránh log đầy đĩa.

### 6.4. Engine lưu bền vững trên đĩa

Một số key–value engine được thiết kế như kho lưu trữ bền vững từ đầu, với WAL, SSTable/B-tree/LSM-tree hoặc cơ chế riêng. Chúng có thể đặt bảo đảm ghi bền ở đường đi của write ACK và hỗ trợ crash recovery.

Dù vậy, **engine bền trên một đĩa** chưa tự đủ để chống lỗi toàn máy hoặc sự cố vùng. Cần đánh giá replication, giao dịch, checksum, backup, khả năng phục hồi và vận hành toàn hệ thống.

### 6.5. Dịch vụ key–value được quản lý

Dịch vụ được quản lý có thể cung cấp lưu trữ nhân bản, tự động failover, backup hoặc point-in-time recovery. Nhưng “managed” không đồng nghĩa tự động RPO = 0, không có mất dữ liệu do lỗi thao tác hoặc không cần cấu hình.

Phải đọc tài liệu chính thức của **đúng sản phẩm, vùng triển khai và chế độ cấu hình** về:

- Điều kiện xác nhận một lần ghi.
- Mô hình consistency và replication.
- Giới hạn transaction/conditional write.
- Chính sách lưu backup, PITR, retention, restore.
- Các sự cố được bảo vệ và ngoại lệ của SLA.
- Hành vi khi không đủ tài nguyên hoặc không đạt quorum.

## 7. Ví dụ: đánh giá Redis khi cân nhắc làm nguồn dữ liệu chính

Redis là một ví dụ dễ thấy sự khác biệt giữa **hệ key–value có persistence** và **mức độ bền mà nghiệp vụ đòi hỏi**. Những chế độ lưu bền quen thuộc:

| Cơ chế | Ý nghĩa | Rủi ro cần cân nhắc |
| --- | --- | --- |
| Không bật persistence | Dữ liệu chủ yếu ở bộ nhớ | Restart/crash có thể mất toàn bộ dữ liệu |
| RDB snapshot | Lưu ảnh chụp dữ liệu theo lịch/điều kiện | Có thể mất phần ghi sau snapshot gần nhất |
| AOF, đồng bộ theo chu kỳ | Ghi lịch sử thay đổi và đồng bộ định kỳ | Có cửa sổ ghi đã ACK nhưng chưa xuống đĩa |
| AOF, đồng bộ mỗi lần ghi | Giảm cửa sổ mất dữ liệu do crash cục bộ | Thêm chi phí I/O/độ trễ; vẫn phải đánh giá lỗi cả máy, nhân bản và môi trường lưu trữ |
| RDB kết hợp AOF | Có các cơ chế phục hồi bổ trợ | Không loại bỏ lỗi cấu hình, lỗi đĩa, failover và xóa nhầm |

Ví dụ minh họa dạng cấu hình Redis:

~~~conf
# Chỉ minh họa ý nghĩa tùy chọn; không phải cấu hình triển khai hoàn chỉnh.
appendonly yes
appendfsync everysec
~~~

Thiết lập này thường nhằm đồng bộ AOF định kỳ (ví dụ theo giây), cân bằng hiệu năng và mức mất dữ liệu cục bộ có thể xảy ra. Không nên diễn giải rằng mọi ghi trả OK đã được fsync ngay lập tức, hay rằng chắc chắn chỉ mất tối đa đúng một giây trong mọi tình huống.

Khi sử dụng Redis replication, bản sao có thể nhận dữ liệu **bất đồng bộ**. Nếu primary đã trả OK nhưng replica dự kiến lên leader chưa nhận thay đổi, một failover có thể làm mất ghi đó. Việc chờ replica xác nhận nhận dữ liệu có thể giảm rủi ro mất ghi, nhưng **nhận được dữ liệu trong bộ nhớ replica khác với đã lưu bền vững xuống đĩa**; mỗi lệnh/cơ chế cần được hiểu đúng hợp đồng bảo đảm.

Ngoài ra:

- Redis có cơ chế **expire/TTL**. Gắn TTL nhầm lên dữ liệu chính có thể khiến bản ghi biến mất đúng theo cấu hình.
- Redis có các chính sách **eviction** khi chạm giới hạn bộ nhớ. Nếu dữ liệu chính phải giữ đầy đủ, cần một chính sách không chủ động loại bỏ khóa theo kiểu cache; chọn không eviction sẽ có nguy cơ **ghi thất bại** khi hết bộ nhớ và cần kế hoạch dung lượng.
- Các thao tác đơn khóa có thể atomic trong phạm vi Redis, nhưng một quy trình nghiệp vụ nhiều khóa cần thiết kế transaction hoặc cơ chế điều kiện phù hợp; không thể lấy tính atomic của một lệnh đơn suy ra toàn bộ workflow atomic.
- Khi phục hồi từ AOF/RDB, phải kiểm tra thời gian khởi động, lượng bộ nhớ cần thiết và cách xử lý file hỏng/dữ liệu không đầy đủ.

Vì vậy, Redis có thể phục vụ nhiều trạng thái quan trọng khi được thiết kế đúng, nhưng **không nên mặc định cấu hình phù hợp cho cache cũng phù hợp cho sổ cái, đơn đã thanh toán hoặc dữ liệu duy nhất không thể tái tạo**.

## 8. Replication không đồng nghĩa với ghi đã bền vững

Giả sử có primary P và hai replica R1, R2:

~~~mermaid
sequenceDiagram
    participant C as Ứng dụng
    participant P as Primary P
    participant R1 as Replica R1
    participant R2 as Replica R2
    C->>P: PUT(K, V2)
    P-->>C: OK
    P-->>R1: Gửi thay đổi V2
    Note over P,R2: Primary mất trước khi R2 nhận V2
    Note over R1,R2: Kết quả failover tùy replica được chọn và cơ chế xác nhận
~~~

Nếu ACK cho ứng dụng xảy ra trước khi bản ghi được nhân bản hoặc trước khi replica được chọn trong failover có phiên bản mới, ghi đã ACK có thể không hiện diện sau chuyển leader.

Các yếu tố cần đọc rõ trong tài liệu hệ quản trị:

**Synchronous hay asynchronous replication?** Ghi có chờ replica không? Chờ replica nhận dữ liệu hay chờ nó durable?

**Bao nhiêu bản sao phải xác nhận?** Một nút, đa số/quorum hay tất cả? Một con số quorum chỉ có ý nghĩa nếu quorum đọc, ghi, cơ chế chuyển leader và quy tắc phục hồi được thiết kế thống nhất.

**Failover bảo vệ đến mốc nào?** Nút nào được quyền thành leader? Khi mạng chia cắt, có ngăn hai leader chấp nhận các ghi xung đột không? Bản ghi đã xác nhận có được cam kết không bị rollback?

**Replica nằm ở đâu?** Ba replica trên một máy vật lý không bảo vệ tốt trước lỗi máy; ba replica cùng một vùng không mặc định bảo vệ sự cố toàn vùng.

**Độ trễ đọc là bao nhiêu?** Ứng dụng có thể cần đọc phiên bản vừa ghi, nhưng đọc từ replica trễ sẽ trả phiên bản cũ. Đây là yêu cầu consistency riêng, dù dữ liệu trên primary đã durable.

Các hệ dùng consensus hoặc durable quorum có thể mang lại hợp đồng bền vững mạnh hơn trong một phạm vi lỗi nhất định, với điều kiện cấu hình đúng và quorum còn hoạt động. Khi không đủ quorum, một thiết kế bảo vệ dữ liệu có thể **từ chối ghi**, tức đánh đổi một phần availability để tránh trả ACK không thể bảo đảm.

## 9. Các cách mất dữ liệu không liên quan đến crash

Lỗi cơ sở hạ tầng chỉ là một nguồn rủi ro. Khi key–value là nguồn dữ liệu chính, các lỗi sau đặc biệt quan trọng:

### 9.1. Hết hạn hoặc tự loại bỏ dữ liệu

Một lập trình viên thêm TTL 24 giờ cho khóa **order:O9001** để tối ưu bộ nhớ; hôm sau đơn biến mất đúng theo chính sách expire. Mọi replica khỏe mạnh cũng có thể đồng bộ việc xóa đó. Đây là **mất dữ liệu do logic**, không phải do ổ đĩa.

Với dữ liệu nguồn, TTL phải là yêu cầu nghiệp vụ có chủ đích, gắn với chính sách lưu giữ và kiểm toán. Đừng dùng TTL như cách dọn dữ liệu chính tùy tiện.

### 9.2. Ghi đè từ thao tác đồng thời

Hai yêu cầu cùng đọc bộ đếm 5:

~~~text
Client A: GET counter -> 5
Client B: GET counter -> 5
Client A: PUT counter = 6
Client B: PUT counter = 6
~~~

Kết quả là 6 thay vì 7, dù cả hai PUT đều bền vững trên đĩa. Độ bền không giải quyết **lost update**.

Nếu hệ có lệnh tăng atomic, compare-and-set (CAS), conditional write hoặc optimistic versioning, hãy dùng cơ chế đó phù hợp với nghiệp vụ. Với nhiều khóa, cần xem atomicity nhiều item và giới hạn của transaction.

### 9.3. Xóa nhầm và migration lỗi

Lệnh xóa hàng loạt sai tiền tố, script migration cập nhật sai giá trị, hoặc ghi đè dữ liệu cũ bằng version không tương thích đều có thể được replication chuyển đến tất cả các bản sao.

Replica giữ dịch vụ sẵn sàng trước lỗi node; **backup có lịch sử thời điểm** và kế hoạch phục hồi giúp xử lý thao tác sai ở tầng ứng dụng. Không nên nhầm hai vai trò này.

### 9.4. Khóa có vòng đời không rõ ràng

Nếu một bản ghi vừa được cập nhật trạng thái, vừa được hệ TTL tự xóa, vừa có background job tái tạo từ event, rất dễ xuất hiện dữ liệu “sống lại” sau khi xóa hoặc phiên bản cũ ghi đè phiên bản mới.

Nguồn dữ liệu chính cần chính sách sở hữu, version, thứ tự cập nhật, idempotency và lifecycle rõ ràng.

## 10. Tính nguyên tử và bất biến nghiệp vụ khi lưu nhiều khóa

Một hệ key–value có thể bảo đảm một lần **PUT(key, value)** atomic, nhưng không vì thế tự bảo đảm:

~~~text
PUT(order:O9001, {status: "PAID"})
PUT(inventory:P10, {quantity: 8})
PUT(payment:TX100, {status: "CAPTURED"})
~~~

Nếu ba thao tác trên đều liên quan đến một giao dịch đặt hàng, hệ thống phải xử lý trường hợp ghi đầu thành công nhưng ghi tiếp thất bại. Thêm bền vững cho từng PUT chỉ khiến trạng thái **dở dang** tồn tại bền vững hơn.

Có ba hướng thiết kế tùy bài toán:

1. **Gom dữ liệu có cùng ranh giới giao dịch vào một value/aggregate** nếu kích thước và cách truy cập cho phép, rồi cập nhật với version/CAS. Cách này không giải quyết các bất biến vượt ngoài aggregate.
2. **Sử dụng transaction nhiều khóa** nếu sản phẩm hỗ trợ và bảo đảm phạm vi, điều kiện lỗi, giới hạn kích thước, độ bền phù hợp.
3. **Thiết kế quy trình nhiều bước có trạng thái, idempotency và bù trừ** khi thao tác đi qua nhiều database hoặc dịch vụ. Ví dụ thanh toán qua cổng ngoài không thể tự động được bao phủ bởi transaction của key–value store.

### Ví dụ cập nhật có điều kiện

Giả sử mỗi giỏ hàng có version:

~~~json
{
  "cartId": "CART-72",
  "version": 7,
  "items": [
    {"sku": "P10", "quantity": 2}
  ]
}
~~~

Ứng dụng đọc version 7 rồi muốn thay đổi item:

~~~text
CAS(
  key = "cart:CART-72",
  expectedVersion = 7,
  newValue = { version: 8, items: [...] }
)
~~~

Nếu một yêu cầu khác đã cập nhật lên version 8, lệnh cập nhật có điều kiện phải thất bại và yêu cầu thứ hai cần đọc lại/tính lại. Đây là **mẫu hành vi**, không phải cú pháp chung của mọi kho key–value; khả năng thực hiện atomic điều kiện phụ thuộc sản phẩm.

Nhớ rằng version/CAS bảo vệ trước ghi đè đồng thời trong phạm vi bản ghi, còn khả năng sống sót qua crash vẫn là yêu cầu durability riêng.

## 11. Giao thức ghi và xử lý retry cần phù hợp với nguồn dữ liệu chính

Khi client gửi một lệnh ghi rồi mất kết nối trước khi nhận kết quả, có hai khả năng:

- Server chưa áp dụng lệnh.
- Server đã áp dụng và lưu bền lệnh nhưng ACK bị mất trên đường truyền.

Ứng dụng **không thể suy ra “thất bại” chỉ từ timeout**. Nếu retry một lệnh “trừ tiền 100.000 đồng” không có idempotency, có thể trừ hai lần.

Ví dụ sơ đồ xử lý có **idempotency key**:

~~~text
Request: paymentId=TX100, idempotencyKey=PAY#TX100, amount=100000

1. Kiểm tra kết quả đã xử lý của PAY#TX100.
2. Nếu chưa xử lý, thực hiện cập nhật bằng giao dịch/điều kiện atomic phù hợp.
3. Ghi trạng thái và kết quả tương ứng với PAY#TX100.
4. Nếu retry cùng khóa, trả lại kết quả đã có thay vì thực hiện lần hai.
~~~

Điểm khó nằm ở **bước 2 và bước 3 phải có quan hệ nhất quán đủ mạnh**. Nếu lưu khóa idempotency ở một hệ nhưng xử lý tiền ở hệ khác mà không có thiết kế phối hợp, vẫn có thể xuất hiện lỗi giữa hai bước.

Với dữ liệu tài chính, điều này là lý do phải xem toàn bộ **transaction boundary và hệ thống đối soát**, không chỉ lệnh PUT.

## 12. Backup, point-in-time recovery và phục hồi có kiểm chứng

Nếu key–value là nguồn sự thật, phải có khả năng phục hồi khỏi **hỏng logic hoặc xóa nhầm**, không chỉ lỗi một node.

### 12.1. Cần những loại bảo vệ nào?

| Biện pháp | Bảo vệ tốt nhất trước | Giới hạn |
| --- | --- | --- |
| Replica | Hỏng node, mở rộng đọc và chuyển leader tùy cơ chế | Có thể sao chép ghi sai/xóa nhầm |
| Snapshot/backup | Phục hồi một thời điểm đã lưu | Có thể mất thay đổi sau điểm lưu |
| Point-in-time recovery (PITR) | Khôi phục gần một thời điểm trước lỗi logic | Cần retention, log đầy đủ và quy trình restore phù hợp |
| Lưu bản backup ngoài miền lỗi | Mất hạ tầng, tài khoản hoặc vùng chính | Có chi phí, quản lý khóa mã hóa và thời gian khôi phục |
| Versioning/audit log | Truy nguyên thay đổi và khôi phục bản ghi cụ thể | Tốn dung lượng và cần bảo vệ log khỏi sửa/xóa |
| Kiểm tra restore định kỳ | Phát hiện backup lỗi và quy trình không chạy được | Cần môi trường, thời gian và dữ liệu đại diện |

**Không được coi “đã tạo backup” là “đã kiểm chứng khả năng phục hồi”.** Khôi phục cần thử trên môi trường tách biệt, kiểm tra số lượng khóa, checksum hoặc bất biến nghiệp vụ, quyền truy cập, cấu hình và thời gian khởi động.

### 12.2. Các câu hỏi cần trả lời về backup

- Dữ liệu được sao lưu theo **snapshot nhất quán** hay có thể ghi được giữa chừng?
- Backup gồm cấu hình, định nghĩa index, TTL, metadata và lịch sử phiên bản hay chỉ gồm value?
- Dữ liệu được mã hóa ra sao; khóa giải mã có được bảo vệ và khôi phục được không?
- Backup lưu bao lâu, có phiên bản độc lập với tài khoản production và chống xóa nhầm không?
- Có thể khôi phục **một khóa**, **một tenant**, **toàn bộ cluster** hay chỉ toàn bộ dataset?
- PITR cho phép về gần thời điểm nào, với độ trễ và giới hạn gì?
- Khôi phục xong, làm sao ngăn consumer hoặc job cũ ghi đè dữ liệu vừa phục hồi?

Một kế hoạch restore tốt còn nêu rõ thời điểm **đóng băng ghi**, cách kiểm tra tính nhất quán, thứ tự khởi động các thành phần và cách cho người dùng truy cập trở lại.

### 12.3. Ví dụ thao tác xóa nhầm

~~~text
09:00  Backup đã có
10:10  Hệ thống ghi 2.000 đơn hàng hợp lệ mới
10:15  Script lỗi xóa nhóm key "order:*"
10:20  Phát hiện sai sót
~~~

Nếu chỉ restore snapshot 09:00, 2.000 đơn hợp lệ sau đó cũng không còn trong bản restore. Nếu có PITR đến trước **10:15**, khả năng mất dữ liệu có thể giảm đáng kể, nhưng vẫn phải cân nhắc các yêu cầu ghi hợp lệ xảy ra sau thời điểm đó.

Trong thực tế, có thể cần restore sang môi trường riêng, trích xuất bản ghi bị xóa và hợp nhất có kiểm soát với dữ liệu mới, rồi đối soát. Đây là lý do **khả năng khôi phục một phần và nhật ký thay đổi** có giá trị đối với nguồn dữ liệu chính.

## 13. Sức chứa và vòng đời dữ liệu cũng là vấn đề độ bền

Một hệ key–value chủ yếu in-memory có thể hết RAM khi dữ liệu tăng. Nếu cấu hình như cache, hệ có thể loại bỏ khóa; nếu cấu hình không eviction, các thao tác ghi có thể bắt đầu bị từ chối. **Cả hai trạng thái đều phải được dự báo**, giám sát và kiểm thử.

Khi dự toán dung lượng, đừng chỉ cộng kích thước JSON/value:

~~~text
Dung lượng tổng ≈
  dữ liệu key + dữ liệu value
  + metadata/overhead của engine
  + index, log, snapshot
  + replica
  + vùng đệm và headroom khi rewrite/compact/restore
~~~

Đây là công thức định tính. Chi phí thực tế cần đo bằng dữ liệu đại diện vì key nhỏ có thể có overhead đáng kể, còn snapshot/compaction có thể đòi hỏi thêm dung lượng đột biến.

### TTL và retention phải là quyết định nghiệp vụ

| Dữ liệu | TTL/retention gợi ý về nguyên tắc |
| --- | --- |
| Cache kết quả truy vấn | Có thể hết hạn, tạo lại từ nguồn |
| Token phiên | Hết hạn theo chính sách an toàn/đăng nhập |
| Giỏ hàng | Chính sách hết hạn cần được thông báo và cân nhắc phục hồi |
| Đơn hàng, hóa đơn | Phải theo thời hạn lưu giữ, kiểm toán và quy định liên quan |
| Nhật ký giao dịch | Cần lưu đủ để đối soát, điều tra và phục hồi theo yêu cầu |

Với dữ liệu chính, khóa cần **không hết hạn ngoài ý muốn** và hành vi xóa phải có quy trình rõ ràng. Nếu có yêu cầu xóa dữ liệu vì quyền riêng tư hoặc thời hạn lưu trữ, backup và replica cũng phải có chính sách phù hợp.

## 14. Kiến trúc minh họa: key–value làm cache và làm nguồn chính

### 14.1. Key–value làm cache

~~~mermaid
flowchart LR
    A[API] --> K[(Key–value cache)]
    A --> DB[(Cơ sở dữ liệu nguồn)]
    K -. "cache miss" .-> A
    DB --> A
~~~

Khi cache mất dữ liệu, ứng dụng có thể đọc lại từ DB nguồn. Cần thiết kế invalidation, TTL, cache stampede và xử lý trường hợp nguồn chậm, nhưng **mất cache không phải mất thông tin nghiệp vụ gốc**.

### 14.2. Key–value làm nguồn chính

~~~mermaid
flowchart TD
    A["API"] --> B["Ghi có điều kiện / transaction phù hợp"]
    B --> K[("Key–value nguồn chính")]
    K --> R[("Replica / lưu trữ chịu lỗi")]
    K --> L["Log/backup/PITR"]
    L --> S[("Kho backup độc lập")]
    O["Giám sát và diễn tập restore"] --> K
    O --> S
~~~

Sơ đồ mô tả những **năng lực cần đánh giá**, không phải kiến trúc bảo đảm độ bền tự động. Lưu trữ nhân bản, log và backup chỉ hữu ích nếu hợp đồng ACK, cấu hình, phạm vi sự cố và quy trình khôi phục đáp ứng yêu cầu đã nêu.

Một dịch vụ key–value managed chuyên lưu bền có thể đã cung cấp nhiều phần trong sơ đồ; không cần tự xây từng thành phần. Nhưng trách nhiệm xác định RPO/RTO, mô hình truy cập, quyền và thử restore vẫn thuộc về đội sử dụng.

## 15. Ba tình huống lựa chọn thực tế

### Tình huống A: Dữ liệu tạo lại được

**Bài toán:** Lưu điểm xếp hạng đề xuất, cache hồ sơ đọc nhiều và bộ đếm tạm thời.

**Đánh giá:** Nếu mất dữ liệu, ứng dụng có thể dựng lại từ nguồn. Hệ in-memory key–value với TTL thường phù hợp. Nên quan tâm availability, tốc độ warm-up và giới hạn bộ nhớ hơn là yêu cầu ghi bền sau từng lần cập nhật.

**Quyết định:** Key–value làm tầng đọc hoặc dữ liệu dẫn xuất. Không cần biến cache thành nguồn sự thật.

### Tình huống B: Dữ liệu nghiệp vụ theo khóa, ghi đơn lẻ nhưng phải bền

**Bài toán:** Lưu cấu hình người dùng hoặc trạng thái thiết bị mà ứng dụng chủ yếu đọc/ghi qua ID. Mỗi lần cập nhật thường gói gọn trong một item. Mất bản ghi đã ACK có hậu quả đáng kể, nhưng các ràng buộc tham chiếu giữa item ít.

**Đánh giá:** Một kho key–value/document được thiết kế cho lưu trữ bền, hỗ trợ conditional write, replica có hợp đồng rõ ràng, backup/PITR và quan sát vận hành có thể là **nguồn chính hợp lý**.

**Điều kiện:** Phải kiểm chứng loại sự cố được bảo vệ, retry/idempotency, khả năng phục hồi dữ liệu lỗi, quota, chi phí và mức nhất quán đọc. Nếu một chỉ mục phụ cập nhật bất đồng bộ thì ứng dụng cần chấp nhận hoặc xử lý trạng thái chưa cập nhật.

### Tình huống C: Đơn hàng, tồn kho và sổ cái

**Bài toán:** Một đơn có nhiều dòng hàng, cần trừ tồn kho và đối soát thanh toán. Tính đúng đắn của nhiều bản ghi trong một giao dịch là quan trọng.

**Đánh giá:** Ngoài durability, bài toán có **giao dịch, bất biến xuyên bản ghi, truy vấn quan hệ và kiểm toán**. Nếu hệ key–value không cung cấp các bảo đảm cần thiết một cách trực tiếp và dễ vận hành, dùng nó làm nguồn chính sẽ đẩy nhiều logic phức tạp sang ứng dụng.

**Quyết định thường phù hợp:** Ưu tiên hệ quan hệ làm nguồn chính cho đơn hàng, tồn kho và các sổ nghiệp vụ; key–value có thể phục vụ cache, session, chỉ mục phụ hoặc dữ liệu đọc có thể tạo lại. Đây là định hướng, không phải quy tắc cấm mọi hệ key–value tham gia giao dịch quan trọng.

## 16. Quy trình đánh giá trước khi cho key–value trở thành nguồn sự thật

### Bước 1: Phân loại dữ liệu và hậu quả mất mát

Viết cho từng loại khóa:

~~~text
Tên dữ liệu: DeviceState
Nguồn gốc: sự kiện từ thiết bị
Có thể tạo lại: một phần
Hậu quả nếu mất 1 lần cập nhật: có thể sai trạng thái cảnh báo
Yêu cầu đọc ngay sau ghi: có
Yêu cầu cập nhật nhiều khóa: không
Thời hạn lưu: theo chính sách sản phẩm
~~~

Đừng gộp mọi khóa trong cùng database thành một mức độ quan trọng. **Cache phiên**, **cấu hình**, **lệnh đã xử lý** và **sổ giao dịch** có thể đòi hỏi các bảo đảm khác nhau.

### Bước 2: Định nghĩa rõ RPO/RTO và miền lỗi

Ví dụ: “Với một node mất đột ngột, không mất lần ghi đã trả thành công; phục vụ trở lại trong khoảng thời gian vận hành đã duyệt”. Nếu yêu cầu chống sự cố cả vùng, phải bổ sung thiết kế và thử nghiệm ở phạm vi vùng.

### Bước 3: Xác minh đường đi của ACK

Kiểm tra tài liệu kỹ thuật và cấu hình thực tế:

- ACK trước hay sau durable write?
- Có replica xác nhận không, và xác nhận ở mức nào?
- Có mất bản ghi đã ACK khi failover trong một tình huống đã công bố không?
- Khi mất quorum hoặc hết dung lượng, hệ trả lỗi hay vẫn trả OK?

Nếu không tìm được câu trả lời rõ ràng, **chưa đủ cơ sở** tuyên bố nguồn dữ liệu bền cho loại nghiệp vụ tương ứng.

### Bước 4: Kiểm tra atomicity và cách cập nhật đồng thời

Liệt kê các bất biến nghiệp vụ, ví dụ:

~~~text
- Không xử lý cùng paymentId quá một lần.
- Version của document phải tăng theo cập nhật thành công.
- Xóa parent không được để lại reference vô hiệu.
- Trạng thái CONFIRMED phải tương ứng với thông tin xác nhận thực tế.
~~~

Xác định bất biến nào bảo vệ được bằng một thao tác atomic, CAS/conditional write hoặc transaction; bất biến nào cần quy trình phân tán và đối soát. Cần đánh giá cả ngữ nghĩa timeout/retry.

### Bước 5: Thiết kế backup, restore và bảo vệ khỏi lỗi thao tác

Xác định retention, lịch backup, PITR, vị trí backup, phân quyền, khóa mã hóa và tiêu chí hoàn thành restore. Thực hiện diễn tập với dataset đại diện để đo thời gian thực tế và xác minh dữ liệu phục hồi.

### Bước 6: Đánh giá giới hạn dung lượng và tải

Đo kích thước dữ liệu khi đầy, write amplification, CPU/I/O khi persistence, độ trễ p95/p99, tần suất full snapshot/compaction, replica lag, quá trình failover và khả năng phục hồi khi log lớn. Tạo tải có **phân bố khóa nóng** gần thực tế.

### Bước 7: Quy định trách nhiệm vận hành và chỉ báo cảnh báo

Các tín hiệu nên quan sát gồm:

| Nhóm | Tín hiệu gợi ý |
| --- | --- |
| Ghi | Tỷ lệ lỗi/timeout, latency, retry, conditional-write conflict |
| Persistence | Log flush/fsync delay, lỗi ghi đĩa, backlog hoặc thời gian snapshot |
| Replication | Replica lag, số replica khỏe, trạng thái leader/quorum |
| Dung lượng | Bộ nhớ sử dụng, disk free, eviction, tốc độ tăng dataset |
| Khôi phục | Backup gần nhất hợp lệ, kết quả diễn tập restore, thời gian phục hồi |
| Toàn vẹn | Số bản ghi bất thường, đối soát, phát hiện trùng/lạc phiên bản |

Không phải sản phẩm nào cũng cung cấp đúng tên metric này. Chọn những metric hiện có mà phản ánh được rủi ro của hệ thực tế.

## 17. Ma trận quyết định mẫu

| Tiêu chí | Key–value như cache | Key–value làm nguồn chính | Hệ quan hệ làm nguồn chính |
| --- | --- | --- | --- |
| Có thể tạo lại khi mất toàn bộ dữ liệu? | Thường có | Thường không | Thường không |
| Cần chính sách durability theo ACK? | Có thể nới lỏng | **Bắt buộc đánh giá** | **Bắt buộc đánh giá** |
| Hỗ trợ cập nhật đơn khóa nhanh | Thường mạnh | Thường mạnh | Có, tùy mô hình/chỉ mục |
| Giao dịch nhiều thực thể | Thường không cần | Phải kiểm tra phạm vi hỗ trợ | Thường là thế mạnh |
| Khóa ngoại/JOIN và báo cáo linh hoạt | Không phải mục tiêu | Tùy sản phẩm, thường có giới hạn | Thường là thế mạnh |
| Xóa nhầm và khôi phục theo thời điểm | Có thể dựng lại từ nguồn | Cần backup/PITR đã kiểm chứng | Cần backup/PITR đã kiểm chứng |
| Failover và mất ghi đã ACK | Thường chấp nhận nếu cache tái tạo được | Phải được xử lý theo hợp đồng rõ | Phải được xử lý theo hợp đồng rõ |
| TTL/eviction tự động | Thường hợp lý | Chỉ dùng nếu nghiệp vụ cho phép | Theo chính sách dữ liệu |

Bảng không khẳng định mọi sản phẩm trong cùng nhóm có tính năng giống nhau. Điều cần so sánh là **cấu hình triển khai cụ thể** cộng với yêu cầu nghiệp vụ.

## 18. Kịch bản kiểm thử khả năng bền và phục hồi

Khi thử một ứng viên làm nguồn chính, dùng môi trường thử nghiệm an toàn và dữ liệu giả lập. Một quy trình kiểm chứng có thể gồm:

1. Ghi một tập khóa có **ID duy nhất, version và checksum**; chỉ tính các lệnh đã nhận ACK thành công vào tập kỳ vọng.
2. Tạo tải ghi/đọc đồng thời, trong đó có cập nhật version có điều kiện và retry sau timeout.
3. Chủ động dừng tiến trình database đột ngột trong môi trường thử; sau khởi động, đối chiếu các bản ghi đã ACK thuộc loại sự cố mà sản phẩm tuyên bố bảo vệ.
4. Lặp lại với tình huống mất node/leader, chặn một đường mạng trong môi trường thử hoặc chuyển leader theo công cụ của sản phẩm.
5. Kiểm tra hành vi khi hết dung lượng hoặc replication không khỏe: ứng dụng phải nhận trạng thái thất bại rõ, không đánh đồng timeout với chưa ghi.
6. Xóa hoặc ghi đè có chủ ý một nhóm khóa thử, thực hiện restore vào môi trường riêng; đo **điểm phục hồi, thời gian phục hồi và tính đầy đủ**.
7. Ghi nhận giới hạn, cấu hình, loại sự cố, số ghi đã ACK, số ghi còn thiếu và các bất biến bị vi phạm.

Ví dụ bảng kết quả cần thu thập:

| Kịch bản | Bản ghi đã ACK còn đủ? | Thời gian phục hồi | Ghi chú cần phân tích |
| --- | --- | --- | --- |
| Crash tiến trình | Đo thực tế | Đo thực tế | Thời điểm flush/log, lỗi recovery |
| Mất node primary | Đo thực tế | Đo thực tế | Replica được chọn, lost ACK, lag |
| Partition mạng | Đo thực tế | Đo thực tế | Ghi được hay bị từ chối; xung đột |
| Xóa nhầm | Đối chiếu sau restore | Đo thực tế | PITR, bản ghi hợp lệ sau mốc xóa |
| Hết disk/RAM | Quan sát lệnh thất bại | Đo thực tế | Eviction, write error, backlog |

Những thử nghiệm này giúp kiểm chứng triển khai trong môi trường đo, **không chứng minh tuyệt đối rằng không thể mất dữ liệu** dưới mọi loại sự cố. Kết quả phải được đối chiếu với bảo đảm chính thức của sản phẩm và mục tiêu RPO/RTO đã thống nhất.

## 19. Bài tập suy luận

### Bài 1: Có snapshot nhưng vẫn mất giao dịch?

Một hệ key–value tạo snapshot mỗi 15 phút. Ứng dụng lưu đơn hàng mới vào lúc 10:12 và nhận OK. Máy chủ hỏng hẳn lúc 10:13; snapshot gần nhất là 10:00, không có log/replica nào khác.

**Câu hỏi:** Dữ liệu đã ACK có chắc còn không? Có phù hợp với nghiệp vụ không mất đơn hàng đã xác nhận?

**Gợi ý:** Không có bảo đảm giữ các ghi từ 10:00 đến lúc crash nếu chỉ dựa vào snapshot đó. Đây là tình huống không phù hợp với yêu cầu không mất giao dịch, trừ khi có cơ chế lưu bền khác.

### Bài 2: Ba replica có thay cho backup?

Một kỹ sư cho rằng cluster có ba bản sao nên không cần backup. Sau đó một script quản trị xóa nhầm một nhóm key, lệnh xóa lan sang cả ba bản sao.

**Câu hỏi:** Cần bổ sung loại bảo vệ nào?

**Gợi ý:** Backup độc lập, lịch sử phiên bản/PITR, quy trình restore và kiểm soát quyền/thao tác nguy hiểm. Replica chủ yếu giúp duy trì dịch vụ khi nút lỗi; nó có thể sao chép cả cập nhật sai.

### Bài 3: Dữ liệu bền nhưng số dư sai?

Hai request cùng đọc số dư 500, rồi mỗi request tự tính và PUT lại giá trị 400 sau thao tác trừ 100. Cả hai PUT đều durable.

**Câu hỏi:** Sai ở đâu?

**Gợi ý:** Lost update do đọc–sửa–ghi không có điều kiện atomic; kết quả đúng sau hai lần trừ phải là 300. Durability của từng PUT không đảm bảo tính đúng đắn của cập nhật đồng thời.

### Bài 4: Timeout nghĩa là có thể ghi lại?

Client gửi lệnh tạo đơn, server xử lý thành công nhưng phản hồi bị mất. Client timeout và tạo lại đơn với ID mới.

**Câu hỏi:** Làm sao tránh tạo hai đơn?

**Gợi ý:** Sử dụng một định danh yêu cầu ổn định/idempotency key và lưu kết quả xử lý theo cơ chế nhất quán; khi retry phải nhận lại kết quả cũ hoặc thất bại có kiểm soát. Cần xử lý đúng ranh giới transaction.

### Bài 5: Chọn cơ sở dữ liệu nguồn

Một nền tảng lưu ba loại dữ liệu: (a) phiên đăng nhập hết hạn sau 30 phút, (b) cấu hình thiết bị cần tồn tại nhiều năm và thường truy cập theo ID, (c) sổ cái thanh toán nhiều bút toán liên quan.

**Gợi ý phân tích:** (a) hợp với key–value ngắn hạn; (b) có thể dùng key–value bền nếu đáp ứng ACK, backup/restore, version và quyền; (c) cần xem giao dịch nhiều bản ghi, bất biến, kiểm toán và đối soát, thường ưu tiên đánh giá hệ quan hệ hoặc hệ giao dịch chuyên dụng.

## 20. Kết luận

Key–value store có thể làm **nguồn dữ liệu chính** khi loại dữ liệu, mô hình thao tác và **bảo đảm độ bền của chính sản phẩm/cấu hình** phù hợp với hậu quả của việc mất dữ liệu. Cần xác định rõ thế nào là ghi thành công, loại sự cố nào được chịu đựng, dữ liệu nào có thể mất, phục hồi đến đâu, mất bao lâu và cách chứng minh các bảo đảm đó.

Khi đánh giá, hãy xem **ACK và persistence**, **replication/failover**, **TTL/eviction**, **transaction và idempotency**, **backup/PITR**, **RPO/RTO**, cùng **thử nghiệm khôi phục thực tế** như một tập yêu cầu thống nhất. Một hệ chỉ được xem là đủ bền khi các bảo đảm ấy phù hợp với dữ liệu nghiệp vụ mà nó chịu trách nhiệm, không chỉ vì có tốc độ đọc cao hoặc nhiều bản sao.
