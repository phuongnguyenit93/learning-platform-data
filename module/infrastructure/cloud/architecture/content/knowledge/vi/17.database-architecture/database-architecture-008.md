# Thiết kế đa khu vực và đánh đổi độ trễ với tính nhất quán

## 1. Vì sao database đa khu vực khó hơn việc nhân bản máy chủ?

Một ứng dụng cloud có thể phục vụ người dùng ở nhiều quốc gia, cần tiếp tục hoạt động khi một region gặp sự cố, hoặc phải đặt dữ liệu gần nơi phát sinh để giảm độ trễ. Khi đó, kiến trúc sư thường cân nhắc chạy database ở nhiều khu vực địa lý và sao chép dữ liệu giữa chúng.

Nhưng dữ liệu giao dịch không giống một file tĩnh có thể copy theo lịch. Hai khu vực có thể cùng nhận thao tác ghi trên một tài khoản, đơn hàng hoặc lượng tồn kho. Nếu một lần ghi đã được xác nhận ở khu vực A nhưng chưa tới khu vực B, người dùng đọc từ B có thể thấy trạng thái cũ. Nếu cả A và B cùng nhận lệnh cập nhật, hệ thống phải xác định cách xử lý xung đột và thứ tự. Nếu đường truyền liên vùng bị gián đoạn, hệ thống phải quyết định tiếp tục ghi cục bộ với rủi ro phân kỳ hay chờ đồng bộ với độ trễ cao hơn.

**Multi-region database là quyết định về ngữ nghĩa dữ liệu, không chỉ là topology triển khai.** Nó ảnh hưởng tới độ trễ, tính nhất quán, khả năng sẵn sàng, RPO/RTO, tính đúng đắn của giao dịch, bảo mật, chi phí truyền dữ liệu và độ phức tạp vận hành.

Trong module **CLOUD_ARCHITECTURE**, thiết kế đa khu vực phải xuất phát từ yêu cầu nghiệp vụ: hành trình nào cần phục vụ gần người dùng, loại dữ liệu nào cần nhất quán chặt, thời gian gián đoạn có thể chấp nhận và lượng dữ liệu có thể mất khi thảm họa xảy ra. Sau đó mới chọn replication đồng bộ hay bất đồng bộ, mô hình primary/replica hay multi-writer, cách định tuyến đọc/ghi và quy trình failover.

Sau bài học, bạn có thể:

- Phân biệt region, availability zone, replica, primary, follower và multi-writer.
- Giải thích tác động của khoảng cách địa lý lên latency và xác nhận giao dịch.
- Phân biệt replication đồng bộ, bất đồng bộ và bán đồng bộ.
- Chọn consistency model theo yêu cầu nghiệp vụ và access pattern.
- Phân tích quorum, split-brain, replication lag, conflict và failover.
- Thiết kế read/write routing, recovery, RPO/RTO và kiểm thử thảm họa.
- Đánh giá đánh đổi đa khu vực theo các trụ cột Well-Architected.

## 2. Phân biệt region, availability zone và replica

**Region** là một khu vực địa lý mà nhà cung cấp cloud vận hành một tập hạ tầng riêng. Trong một region thường có nhiều **availability zone (AZ)** hoặc miền lỗi tương đương. AZ được thiết kế để giảm một số dạng phụ thuộc chung, nhưng vẫn có thể có tương quan sự cố ở cấp region, nhà cung cấp, dịch vụ điều khiển hoặc kết nối.

Một database có thể được triển khai:

- Một instance/cluster trong một AZ.
- Nhiều node hoặc replica trong cùng region nhưng khác AZ.
- Replica ở hai hoặc nhiều region.
- Nhiều region cùng nhận ghi.
- Dịch vụ database phân tán toàn cầu với cơ chế replication và consistency do nền tảng quản lý.

| Phạm vi | Mục tiêu điển hình | Rủi ro còn lại |
| --- | --- | --- |
| Nhiều node cùng AZ | Chịu lỗi process hoặc instance | Có thể mất cả AZ |
| Multi-AZ trong một region | Chịu lỗi node/AZ, tăng khả năng phục hồi | Sự cố region có thể ảnh hưởng toàn bộ |
| Primary và replica khác region | DR, đọc gần người dùng hoặc standby | Replication lag, promotion và routing phức tạp |
| Multi-writer nhiều region | Nhận ghi tại nhiều vị trí, giảm phụ thuộc một writer trung tâm | Conflict, transaction xuyên vùng và consistency khó hơn |
| Distributed database toàn cầu | Phân phối dữ liệu, điều phối consistency và failover ở nền tảng | Phụ thuộc semantics, quota, chi phí và giới hạn dịch vụ |

**Multi-AZ không đồng nghĩa multi-region.** Một hệ thống có ba AZ trong một region vẫn có thể bị ảnh hưởng bởi mất region, lỗi dịch vụ điều khiển dùng chung hoặc sự cố mạng diện rộng.

## 3. Độ trễ địa lý và chi phí của một lần ghi

Một thao tác ghi thường gồm client-to-service network, xử lý tại database, log/commit và replication tới các node khác theo chính sách. Khi dữ liệu phải được xác nhận ở vùng xa, thời gian truyền qua mạng liên vùng có thể trở thành phần đáng kể của latency.

### 3.1. Round-trip time và khoảng cách

Để một giao dịch ghi đồng bộ chờ replica ở region khác xác nhận, hệ thống cần ít nhất thời gian truyền thông tin qua đường liên vùng và nhận phản hồi, ngoài thời gian xử lý ở hai phía. Tốc độ truyền tín hiệu, đường mạng thực tế, định tuyến và hàng đợi đều ảnh hưởng. Khoảng cách địa lý càng lớn thường làm giới hạn latency thấp nhất càng cao.

Do đó một giao dịch ghi đồng bộ liên vùng không thể có latency bằng một ghi cục bộ cùng vùng trong mọi tình huống. Tối ưu compute hoặc tăng IOPS không loại bỏ được round-trip vật lý tới region xa.

### 3.2. Mô hình latency đơn giản

**Latency ghi ≈ xử lý cục bộ + thời gian log/commit + thời gian chờ replication/quorum + queueing.**

Đây là mô hình khái niệm. Các sản phẩm có thể song song hóa bước ghi log, gửi replication và xử lý quorum khác nhau. Cần đọc semantics của database cụ thể và đo p50/p95/p99 từ ứng dụng.

### 3.3. Đọc gần, ghi xa

Một thiết kế thường gặp là đặt read replica ở nhiều region để người dùng đọc từ region gần, trong khi tất cả ghi đi về primary region. Cách này có thể giảm latency đọc nhưng không tự làm dữ liệu đọc là mới nhất. Nếu replica bất đồng bộ, client vừa ghi ở A rồi chuyển sang đọc tại B có thể chưa thấy thay đổi.

Ứng dụng cần chính sách read-after-write như:

- Gửi các lần đọc tiếp theo về primary trong một khoảng thời gian hoặc theo session.
- Dùng token/version/commit position để chờ replica bắt kịp trước khi đọc.
- Dùng read-your-writes routing hoặc session consistency nếu sản phẩm hỗ trợ.
- Chấp nhận eventual consistency cho màn hình hoặc dữ liệu không quan trọng về độ mới.

Không nên để client đổi region ngẫu nhiên sau một lần ghi nếu nghiệp vụ đòi hỏi nhìn thấy kết quả ngay.

## 4. Các mô hình replication

Replication sao chép thay đổi dữ liệu hoặc log từ một node/region tới node/region khác. Từ góc nhìn ứng dụng, quyết định quan trọng là lúc nào database trả lời rằng một lần ghi đã được xác nhận.

### 4.1. Synchronous replication

Trong replication đồng bộ, primary chỉ xác nhận commit khi điều kiện xác nhận từ replica hoặc quorum đã thỏa mãn theo cấu hình. Một số hệ thống yêu cầu mọi replica đồng bộ xác nhận; số khác chỉ yêu cầu một tập đủ điều kiện.

**Ưu điểm:**

- Giảm cửa sổ mất dữ liệu khi primary gặp sự cố, nếu commit acknowledgement bảo đảm log đã được lưu ở miền lỗi độc lập.
- Có thể hỗ trợ failover với RPO gần 0 hoặc bằng 0 trong các điều kiện và semantics được thiết kế.
- Phù hợp dữ liệu cần durability cao và không chấp nhận mất giao dịch đã xác nhận.

**Đánh đổi:**

- Ghi phải chờ round-trip hoặc điều kiện quorum, nên latency cao hơn.
- Mạng liên vùng bị chậm có thể kéo chậm write throughput.
- Mất kết nối tới quorum có thể khiến hệ thống từ chối hoặc chặn ghi để bảo toàn consistency.
- Tăng chi phí network, replica và vận hành.

Synchronous không tự bảo đảm RPO=0 trong mọi tình huống. Phải xem replica nằm ở đâu, commit ACK có nghĩa gì, transaction log được flush đến đâu, failover chọn node nào và các bản sao có thực sự độc lập failure domain hay không.

### 4.2. Asynchronous replication

Trong replication bất đồng bộ, primary xác nhận ghi sau khi commit cục bộ mà không chờ replica xa hoàn tất. Thay đổi được gửi tới replica sau đó.

**Ưu điểm:**

- Latency ghi thường thấp hơn vì không chờ region xa.
- Primary tiếp tục ghi khi replica xa chậm hoặc tạm mất kết nối, tùy chính sách.
- Phù hợp DR standby hoặc dữ liệu cho phép stale read/mất một cửa sổ nhỏ khi thảm họa.

**Đánh đổi:**

- Replica có thể bị trễ; read có thể stale.
- Primary mất trước khi log được chuyển tới replica có thể làm mất các giao dịch đã xác nhận tại primary.
- Failover có thể cần đo lag, chọn replica, chấp nhận hoặc đối soát dữ liệu thiếu.
- Replica xa có thể cần thời gian catch-up trước khi phục vụ đủ tải.

### 4.3. Semi-synchronous và quorum replication

Semi-synchronous thường chờ ít nhất một số replica xác nhận nhưng không nhất thiết chờ tất cả. Quorum-based replication yêu cầu một ngưỡng thành viên xác nhận để quyết định commit/read, tùy thuật toán và sản phẩm.

| Mô hình | Khi trả ACK | Đánh đổi thường gặp |
| --- | --- | --- |
| Local commit + async ship | Sau commit tại primary | Latency thấp; có cửa sổ mất dữ liệu ở DR |
| Semi-sync | Sau khi một hoặc một số replica xác nhận điều kiện được cấu hình | Cân bằng durability và latency; phụ thuộc vị trí replica |
| Sync quorum | Sau khi quorum xác nhận | Durability/consistency mạnh hơn theo protocol; có thể giảm availability ghi khi thiếu quorum |
| Sync tới mọi replica | Sau mọi replica bắt buộc xác nhận | Latency cao và bị chặn bởi replica chậm hoặc mất kết nối |

Đừng chỉ đọc tên mode. Hãy kiểm tra chính xác ACK xác nhận điều gì: nhận log ở RAM, ghi log bền vững, flush xuống storage hay áp dụng thay đổi để đọc được. Các điều kiện này khác nhau.

### 4.4. So sánh luồng ghi

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant A as Primary region A
    participant B as Replica region B
    App->>A: COMMIT
    A->>A: Ghi log cục bộ
    alt Replication bất đồng bộ
        A-->>App: ACK sau commit cục bộ
        A-->>B: Gửi log sau đó
        B-->>A: Xác nhận đã nhận/áp dụng
    else Replication đồng bộ
        A->>B: Gửi log cần xác nhận
        B-->>A: ACK theo điều kiện sync
        A-->>App: ACK sau khi đủ điều kiện
    end
~~~

Sơ đồ đơn giản hóa; một số hệ thống gửi log song song tới nhiều replica hoặc dùng quorum. Điều cốt lõi là **điểm ACK quyết định mức dữ liệu mà hệ thống cam kết đã được bảo vệ**.

## 5. Consistency: ứng dụng phải nhìn thấy điều gì?

Consistency là tập quy tắc xác định dữ liệu có thể được quan sát như thế nào giữa các client, replica và thời điểm. Không phải ứng dụng nào cũng cần cùng một mức nhất quán.

### 5.1. Strong consistency / linearizability

Một thao tác đọc có tính linearizable thường quan sát được trạng thái phù hợp với một thứ tự toàn cục tôn trọng thời gian thực của các thao tác hoàn tất. Với người dùng, một lần ghi đã thành công thì lần đọc sau theo hợp đồng strong consistency sẽ thấy giá trị mới nhất phù hợp với thứ tự đó.

Mức bảo đảm này hữu ích với số dư, quota, quyền sở hữu, reservation hoặc dữ liệu mà hai người dùng đồng thời thay đổi có thể gây thiệt hại. Nó thường cần coordination, quorum hoặc primary routing, từ đó có thể tăng latency và giảm khả năng ghi khi mạng phân vùng.

### 5.2. Eventual consistency

Với eventual consistency, nếu không có ghi mới và mạng cuối cùng hoạt động, các replica sẽ hội tụ về cùng trạng thái. Trong thời gian chưa hội tụ, các client có thể đọc giá trị khác nhau hoặc thấy dữ liệu cũ.

Phù hợp với một số trường hợp như view đếm lượt xem, feed, dashboard, catalog cache hoặc dữ liệu phân tích có thể chấp nhận độ trễ cập nhật. Không tự áp dụng cho số dư hoặc trừ tồn kho nếu chưa có cơ chế nghiệp vụ chống ghi vượt.

### 5.3. Session guarantees và consistency ở mức ứng dụng

| Bảo đảm | Ý nghĩa |
| --- | --- |
| Read-your-writes | Một client nhìn thấy các ghi do chính nó đã hoàn tất |
| Monotonic reads | Các lần đọc liên tiếp của một session không quay lùi về phiên bản cũ hơn |
| Monotonic writes | Các lần ghi của một session được áp dụng theo thứ tự |
| Causal consistency | Các thao tác có quan hệ nhân quả được quan sát theo đúng thứ tự nhân quả |
| Bounded staleness | Dữ liệu đọc có thể cũ nhưng bị giới hạn theo thời gian hoặc số version, theo semantics dịch vụ |

Các bảo đảm này giúp giảm nhu cầu strong consistency toàn cục nhưng đòi hỏi session/token/routing và ứng dụng hiểu cách sử dụng. Không gọi mọi mô hình có read-your-writes là globally linearizable.

### 5.4. Consistency ở database và consistency của nghiệp vụ

Database có thể bảo đảm ACID trong một transaction tại một region, nhưng toàn hệ thống vẫn có thể eventual khi transaction phát event sang queue, cập nhật search index hoặc replicate sang region khác. Tương tự, strong consistency của một bảng không bảo đảm workflow thanh toán và kho hàng cùng cập nhật nguyên tử nếu chúng nằm ở hai service/database.

Hãy nêu rõ consistency cần thiết **theo use case và dữ liệu**, thay vì gắn một nhãn cho toàn bộ hệ thống.

## 6. Quorum và giới hạn khi mạng phân vùng

Trong hệ thống replicated, quorum là số thành viên cần tham gia để một thao tác được xác nhận hoặc một quyết định được đưa ra. Với một nhóm gồm N replica và protocol đơn giản dùng majority, quorum thường là:

**Q = floor(N / 2) + 1.**

Ví dụ 3 replica cần 2 phiếu để có majority; 5 replica cần 3. Hai quorum majority của cùng một nhóm sẽ giao nhau, giúp ngăn hai phía độc lập cùng đạt đa số trong cùng một epoch theo các giả định của protocol.

Đây chỉ là minh họa số học, không phải cấu hình đủ cho mọi database. Các hệ thống có weighted quorum, joint consensus khi thay membership, witness hoặc quy tắc lease/epoch riêng. Số replica và vị trí địa lý phải được thiết kế cùng protocol cụ thể.

### 6.1. Ba region và tình huống mất liên kết

Giả sử có ba region A, B, C với một bản sao mỗi nơi. Majority là hai. Nếu A mất liên kết với B và C nhưng B/C vẫn liên lạc, phía B/C có thể giữ quorum theo protocol; phía A không đạt majority nên không được tiếp tục ghi như một leader hợp lệ nếu muốn giữ single history.

Nếu chỉ có hai region, khi đường truyền giữa hai bên đứt, không bên nào tự biết bên kia thực sự đã hỏng hay chỉ bị cô lập. Cho phép cả hai tiếp tục ghi có thể tạo hai lịch sử xung đột. Chọn một bên có quyền ghi thường cần witness, quorum, fencing hoặc cơ chế điều phối đáng tin cậy khác.

### 6.2. CAP không phải công thức chọn database

Định lý CAP nói rằng khi xảy ra network partition trong một hệ thống phân tán, không thể đồng thời bảo đảm availability và strong consistency theo định nghĩa tương ứng cho mọi thao tác. Trong thời gian mạng hoạt động bình thường, hệ thống vẫn có thể cung cấp cả consistency và availability với latency phù hợp. CAP không nói rằng chỉ được chọn hai trong ba tính chất mọi lúc, cũng không thay thế phân tích latency, durability, failure detection và nghiệp vụ.

Một lựa chọn kiến trúc thực tế là quyết định hành vi khi mất liên lạc:

- **Ưu tiên consistency:** ngừng hoặc từ chối ghi ở phía không có quorum/primary hợp lệ; bảo vệ single history nhưng một số người dùng không thao tác được.
- **Ưu tiên availability cục bộ:** tiếp tục nhận ghi ở nhiều phía; ứng dụng phải xử lý conflict, merge hoặc reconciliation và có thể có kết quả tạm thời khác nhau.
- **Phân loại theo dữ liệu:** dữ liệu quan trọng dùng single-writer/quorum; dữ liệu ít rủi ro có thể cho ghi cục bộ và hợp nhất sau.

### 6.3. Split-brain và fencing

Split-brain xảy ra khi hai phía cùng tin mình có quyền primary/leader và nhận các thao tác ghi độc lập. Hậu quả có thể là hai lịch sử dữ liệu khác nhau, ghi đè hoặc mất giao dịch sau khi hội tụ.

Các biện pháp:

- Dùng quorum/leader election theo protocol được hỗ trợ.
- Gắn **epoch/term/generation** vào quyền leader; node cũ không được ghi khi lease/term đã hết hiệu lực.
- Fencing token hoặc cơ chế storage-level fencing ngăn writer cũ tiếp tục cập nhật tài nguyên.
- Dùng witness ở failure domain phù hợp nếu kiến trúc cần thành viên phân xử thứ ba.
- Không tự promote replica chỉ vì health check của primary timeout; cần xác minh quyền lãnh đạo và trạng thái replication.

## 7. Primary/standby, read replica và multi-writer

### 7.1. Single-writer primary/standby

Một region giữ quyền ghi; region còn lại nhận replication và sẵn sàng được promote khi thảm họa.

**Lợi ích:** semantics ghi đơn giản hơn, ít conflict, dễ giữ transaction ordering ở primary và dễ xác định owner dữ liệu.

**Hạn chế:** ghi từ region xa phải đi về primary; failover cần promote, đổi endpoint/DNS/routing và có thể mất dữ liệu nếu async lag; primary là miền phụ thuộc cho write availability.

Phù hợp hệ thống giao dịch cần quy tắc ghi rõ, ứng dụng có thể chấp nhận write latency từ xa hoặc chỉ cần region thứ hai làm DR.

### 7.2. Primary với read replica nhiều region

Read replica phục vụ truy vấn đọc gần người dùng. Cần xác định:

- Replica có thể stale bao lâu và metric lag nào đại diện?
- Truy vấn nào buộc đọc primary, truy vấn nào cho phép đọc replica?
- Có session consistency hoặc read-after-write routing không?
- Khi replica bị chậm, ứng dụng fallback về primary hay trả dữ liệu cũ?
- Read replica có đủ capacity cho truy vấn cao điểm không?

Read replica không phải writer độc lập. Nếu người dùng được định tuyến ghi trực tiếp vào endpoint read-only, thao tác sẽ thất bại hoặc không tuân thủ hợp đồng.

### 7.3. Active-active / multi-writer

Nhiều region cùng nhận ghi giúp giảm round-trip tới writer trung tâm và có thể duy trì ghi cục bộ khi liên vùng bị gián đoạn, tùy database. Tuy nhiên, hai region có thể cập nhật cùng entity đồng thời.

| Chiến lược | Cơ chế | Rủi ro / giới hạn |
| --- | --- | --- |
| Single-writer theo entity | Một region/owner nhận ghi cho mỗi account/order/tenant | Cần routing và failover owner; writer xa có thể tăng latency |
| Last-write-wins | Chọn phiên bản theo timestamp/version rule | Có thể mất cập nhật hợp lệ; clock skew và tie-break cần xử lý |
| Version vector / causal metadata | Phát hiện hai cập nhật concurrent và xác định quan hệ | Phức tạp cho ứng dụng và người vận hành |
| Merge function | Hợp nhất các thao tác theo quy tắc dữ liệu | Chỉ áp dụng cho kiểu dữ liệu/nghiệp vụ có phép merge đúng |
| Conflict queue/manual resolution | Giữ cả hai biến thể để xử lý sau | Tăng backlog và cần quy trình phục hồi |

Không thể dùng last-write-wins cho mọi dữ liệu. Hai lần cập nhật địa chỉ có thể chấp nhận chọn một phiên bản mới hơn; hai lần trừ tiền hoặc giảm tồn kho không thể đơn giản bỏ một bản ghi mà vẫn bảo toàn số dư.

## 8. Chọn theo đặc tính nghiệp vụ

Một hệ thống có thể dùng nhiều consistency model hoặc nhiều database topology cho từng miền dữ liệu.

| Dữ liệu / nghiệp vụ | Mức yêu cầu thường gặp | Mô hình có thể cân nhắc |
| --- | --- | --- |
| Số dư tài khoản, ledger | Không được ghi đè hoặc mất giao dịch đã xác nhận | Single-writer/quorum, transaction mạnh, audit và fencing |
| Reservation tồn kho hữu hạn | Không được bán vượt số lượng | Atomic conditional update, owner theo SKU/kho hoặc coordination mạnh |
| Trạng thái đơn hàng | Thứ tự chuyển trạng thái phải hợp lệ | Partition/owner theo order, version check, idempotency |
| Catalog sản phẩm | Có thể chấp nhận trễ cập nhật ngắn | Primary + read replica hoặc cache/eventual consistency |
| Số lượt xem, thống kê | Có thể hợp nhất sau | Async replication, aggregation và dedup |
| Session/user preference | Thường cần read-your-writes | Session routing, regional ownership hoặc version token |
| Search index | Có thể trễ so với nguồn giao dịch | Rebuild/replay từ source of truth, event-driven projection |

Hãy tránh lựa chọn consistency chỉ theo tên sản phẩm. Kiểm tra database hỗ trợ transaction xuyên partition/region hay không, read/write isolation, conflict policy, failover semantics và giới hạn region.

## 9. Định tuyến đọc và ghi

Một kiến trúc multi-region cần quyết định mỗi request đi tới đâu. DNS hoặc global load balancer có thể đưa người dùng tới ứng dụng gần nhất, nhưng **không tự quyết định endpoint database phù hợp với consistency**.

### 9.1. Single-writer với read replicas

~~~mermaid
flowchart TB
    UsersA["Người dùng region A"] --> AppA["Application A"]
    UsersB["Người dùng region B"] --> AppB["Application B"]
    AppA -->|Write| Primary["Primary database A"]
    AppB -->|Write qua WAN| Primary
    Primary -->|Async replication| ReplicaB["Read replica B"]
    AppA -->|Read/write| Primary
    AppB -->|Read cho phép stale| ReplicaB
~~~

Ứng dụng ở B có thể đọc replica B để giảm latency cho dữ liệu cho phép stale, nhưng các thao tác cần read-after-write hoặc consistency mạnh phải dùng primary hoặc cơ chế token/consistency phù hợp.

### 9.2. Phân loại query

| Query | Route gợi ý | Lý do |
| --- | --- | --- |
| Ghi số dư hoặc reservation | Primary/leader của partition dữ liệu | Cần tuần tự hóa và kiểm soát concurrency |
| Đọc ngay sau một lần ghi | Primary hoặc session-consistent endpoint | Tránh đọc phiên bản cũ |
| Đọc catalog công khai | Replica gần người dùng nếu staleness được chấp nhận | Giảm latency và phân tải |
| Dashboard tổng hợp | Replica/warehouse/projection bất đồng bộ | Có thể chấp nhận dữ liệu trễ |
| Admin/audit cần xác nhận giao dịch | Nguồn nhất quán theo hợp đồng và log bền vững | Tránh báo sai kết quả xác nhận |

### 9.3. Read fallback khi replica lỗi

Khi replica vùng B bị lag hoặc không sẵn sàng, ứng dụng cần quyết định:

- Fallback sang primary A và chấp nhận latency liên vùng.
- Dùng cache nếu dữ liệu cho phép stale và có TTL/version rõ.
- Trả lỗi hoặc thông báo dữ liệu tạm thời không sẵn sàng nếu yêu cầu consistency nghiêm.

Không tự động fallback mọi truy vấn về nguồn cũ mà không theo dõi tải: hàng nghìn client chuyển về primary có thể gây overload đúng lúc replica đang lỗi.

## 10. Transaction và invariant xuyên vùng

Transaction ACID trong một database không đồng nghĩa có transaction nguyên tử trên hai region hoặc hai service độc lập. Độ trễ và khả năng mất kết nối làm transaction phân tán khó hơn.

### 10.1. Đặt dữ liệu theo aggregate hoặc ownership

Thiết kế một vùng có quyền ghi cho từng aggregate có thể giảm giao dịch xuyên region. Ví dụ:

- Order ID được gán home region, mọi chuyển trạng thái của order được xử lý tại region đó.
- Account có owner region, chuyển tiền giữa các account cần một workflow/ledger có coordination rõ.
- Inventory được chia theo warehouse hoặc SKU-location, mỗi đơn vị có một nơi quyết định reservation.

Đây là sharding/ownership theo nghiệp vụ. Cần cơ chế di chuyển ownership, xử lý khi home region lỗi và ngăn hai owner cùng ghi.

### 10.2. Saga thay cho transaction xuyên service

Nếu quy trình gồm nhiều bước ở nhiều region/service, có thể dùng Saga với trạng thái bền vững và compensation. Ví dụ đặt hàng, reservation kho, payment và vận chuyển. Saga không làm toàn bộ bước thành atomic; nó định nghĩa tiến trình, lỗi, timeout và hành động bù.

Mỗi bước cần idempotency, correlation ID, timeout, retry và reconciliation. Compensation như hoàn tiền hoặc hủy reservation là một thao tác nghiệp vụ thực sự, không phải rollback database tự động.

### 10.3. Outbox và sự kiện replication

Khi transaction ghi database phải phát event, transactional outbox giúp ghi dữ liệu nghiệp vụ và outbox record trong cùng transaction cục bộ. Relay phát sự kiện sau commit; consumer cần idempotent vì có thể nhận lặp.

Outbox không thay thế replication của database và không làm transaction nguyên tử giữa database với broker ở region khác. Cần xác định event được publish tại region nào, duplicate/cross-region ordering ra sao và consumer đang đọc source of truth nào.

## 11. Failover, failback và RPO/RTO

Failover là chuyển vai trò phục vụ sang miền dự phòng. Failback là đưa hệ thống trở lại mô hình vận hành mong muốn sau khi vùng chính phục hồi. Hai thao tác cần kế hoạch về dữ liệu, quyền writer, endpoint, DNS, connection pool và traffic ứng dụng.

### 11.1. RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, đo theo thời gian hoặc mốc transaction.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ sau sự cố.

Với async replication, RPO phụ thuộc replication lag tại thời điểm lỗi và cách xác định log đã được chuyển bền vững. Không cam kết một RPO cố định chỉ dựa trên lag trung bình; phải xét tail, burst, link outage và quy trình promotion.

RTO không chỉ là thời gian promote DB. Nó còn gồm xác định sự cố, ngăn writer cũ, chọn replica, khôi phục endpoint, cập nhật routing/DNS, thiết lập connection mới, warm cache và xác minh luồng nghiệp vụ.

### 11.2. Checklist failover

1. Xác định failure domain thực sự và đánh giá primary còn hoạt động hay chỉ mất liên lạc.
2. Chặn hoặc fence writer cũ nếu có nguy cơ nó tiếp tục nhận ghi.
3. Kiểm tra replication position/lag và xác định lượng dữ liệu có thể mất.
4. Chọn replica hợp lệ và promote theo quy trình database/provider.
5. Cập nhật endpoint/service discovery và quyền truy cập.
6. Điều hướng write về đúng writer; read replica khác phải được nối lại theo topology mới.
7. Kiểm tra connection pool, prepared statement, transaction dangling và worker đang retry.
8. Chạy health check và kiểm tra nghiệp vụ như tạo đơn, đọc lại đơn và đối soát giao dịch.
9. Theo dõi lỗi/latency/lag sau chuyển vùng; thông báo trạng thái theo quy trình.

### 11.3. Failback

Không đơn giản bật lại region cũ làm primary. Trước failback phải:

- Đồng bộ dữ liệu và xác nhận node cũ đã theo kịp nguồn hiện tại.
- Chọn cửa sổ chuyển writer và cách ngăn hai phía cùng ghi.
- Xác minh schema, extension, parameter, key và phiên bản tương thích.
- Chuyển read/write traffic theo kế hoạch, có rollback.
- Kiểm tra replica topology và backup sau khi trở lại trạng thái bình thường.

## 12. Backup, restore và DR độc lập với replication

Replication không thay backup. Nếu người dùng xóa nhầm dữ liệu hoặc ứng dụng ghi sai logic, thay đổi có thể replicate nhanh sang mọi region.

Một chiến lược bảo vệ dữ liệu đa khu vực cần:

- Backup định kỳ hoặc continuous log archive/PITR theo yêu cầu.
- Bản sao backup ở failure domain/account/region thích hợp.
- Quyền xóa backup độc lập hoặc retention lock/immutability theo chính sách.
- Mã hóa và quản lý key có khả năng phục hồi ở region DR.
- Restore test để chứng minh database có thể khởi động, dữ liệu nhất quán và ứng dụng thực sự đọc/ghi được.
- Kiểm tra thời gian truyền/restore lượng dữ liệu lớn, network bandwidth và chi phí.

Nếu encryption key chỉ nằm ở region chính và không thể truy cập từ region DR, bản backup có thể tồn tại nhưng không khôi phục được. Kế hoạch DR phải gồm key, identity, network, secret và cấu hình.

## 13. Bảo mật và quản trị dữ liệu đa khu vực

### 13.1. Data residency và phân loại dữ liệu

Một số dữ liệu có yêu cầu lưu trữ theo quốc gia/khu vực hoặc hạn chế cross-border transfer. Cần xác định:

- Dữ liệu nào được phép replicate sang region khác?
- Backup, log, snapshot, analytics và replica có cùng quy định với dữ liệu gốc không?
- Có cần tách tenant/dataset theo jurisdiction không?
- Metadata có chứa dữ liệu cá nhân hoặc thông tin nhạy cảm không?
- Khi xóa dữ liệu theo yêu cầu, xóa ở replica, backup và cache theo quy trình nào?

Đừng giả định chỉ database primary mới là dữ liệu được quản lý. Replica, log và backup cũng có thể mang cùng dữ liệu nhạy cảm.

### 13.2. Identity, encryption và key management

- Dùng identity riêng cho ứng dụng, replication agent, admin và automation.
- Mã hóa traffic giữa region bằng TLS hoặc kênh riêng được phê duyệt.
- Mã hóa at rest cho primary, replica, snapshot, backup và log.
- Quản lý customer-managed key với chính sách rotation, quyền sử dụng và khả năng DR.
- Giới hạn quyền promote, thay đổi writer endpoint, tạo replica và xóa backup.
- Ghi audit cho thao tác dữ liệu và thao tác quản trị liên vùng.

### 13.3. Replication link và least privilege

Replica cần quyền đọc log/stream và thiết lập kết nối tới nguồn. Chỉ mở network path và port cần thiết; không mở database listener công khai cho mọi vùng. Tách quyền replication khỏi quyền query ứng dụng nếu nền tảng hỗ trợ. Theo dõi certificate/token expiration và khả năng rotation mà không làm đứt replication.

## 14. Các kiểu database và mức phù hợp đa khu vực

| Loại database | Kiểu triển khai đa vùng thường thấy | Điểm cần kiểm tra |
| --- | --- | --- |
| Relational primary/replica | Một writer, async hoặc sync standby/read replica | Transaction semantics, lag, promotion, sequence/identity và write routing |
| Distributed SQL | Replication/consensus trên nhiều node/region, có thể cung cấp SQL và transaction phân tán | Quorum placement, latency commit, geo-partitioning, transaction contention |
| Global key-value/document | Replication đa vùng, một số sản phẩm hỗ trợ multi-region write và conflict resolution | Consistency mode, item conflict, conditional write, hot partition và quota |
| Managed relational cluster | Cluster trong một region với replica/DR region theo dịch vụ | RPO, promotion time, endpoint change, version compatibility |
| Data warehouse/analytics | Copy/replication hoặc ingest event theo vùng | Freshness, batch lag, data governance và egress |

Tên gọi “global database” không đảm bảo mọi truy vấn đều strong-consistent ở mọi region hoặc mọi thao tác ghi đều local. Đọc kỹ mode consistency, placement, transaction scope, failure behavior và giá theo request/replication.

## 15. Ví dụ thiết kế: nền tảng thương mại điện tử hai khu vực

Giả sử doanh nghiệp có người dùng ở khu vực A và B. API, catalog và worker có thể chạy ở cả hai. Đơn hàng, payment ledger và reservation tồn kho là dữ liệu quan trọng; catalog và nội dung ảnh có thể chấp nhận trễ cập nhật ngắn.

### 15.1. Phương án single-writer có read replica

~~~mermaid
flowchart TB
    UsersA["Users region A"] --> AppA["Application A"]
    UsersB["Users region B"] --> AppB["Application B"]
    AppA --> Primary[("Primary DB region A")]
    AppB -->|Write qua private WAN| Primary
    Primary -->|Async replication| Replica[("Read replica region B")]
    AppA -->|Read/write| Primary
    AppB -->|Read stale-tolerant| Replica
    AppB -->|Read-after-write| Primary
~~~

Thiết kế này giữ một nơi ghi cho transaction quan trọng. Người dùng ở B có thể thấy latency ghi cao hơn. Catalog có thể đọc từ replica nếu stale trong giới hạn chấp nhận; màn hình xác nhận order đọc primary hoặc dùng session token để bảo đảm read-your-writes.

### 15.2. Phân loại consistency

| Miền dữ liệu | Quy tắc đề xuất | Vì sao |
| --- | --- | --- |
| Payment ledger | Writer có thẩm quyền duy nhất, commit bền vững theo yêu cầu | Không thể hợp nhất hai lần ghi trùng bằng last-write-wins |
| Order state | Định tuyến theo order owner; version/transition validation | Chặn chuyển trạng thái sai thứ tự |
| Inventory reservation | Atomic conditional update hoặc partition owner theo warehouse/SKU | Tránh oversell |
| Catalog | Read replica/cache với bounded staleness nếu nghiệp vụ duyệt | Tối ưu latency đọc |
| Product media | Object storage/CDN nhiều vùng | Nội dung bất biến hoặc versioned dễ phân phối |
| Analytics | Async pipeline và warehouse | Có thể chấp nhận lag, không ảnh hưởng giao dịch |

### 15.3. Khi primary region A mất

Đội cần xác minh liệu A thực sự mất hay chỉ mất liên lạc với B. Nếu B được chọn làm DR writer, cần fence A, kiểm tra replication lag, xác định transaction có thể thiếu, promote B, đổi write endpoint và kiểm tra dữ liệu nghiệp vụ. Khi A trở lại, không cho A tự nhận ghi; phải đồng bộ theo topology hiện tại rồi mới xem xét failback.

## 16. Đo lường và kiểm thử kiến trúc đa khu vực

Không thể xác nhận thiết kế multi-region chỉ bằng việc nhìn thấy replica ở console. Cần đo cả database và hành trình nghiệp vụ.

### 16.1. Chỉ số quan sát

| Nhóm | Chỉ số |
| --- | --- |
| Replication | Lag theo thời gian/bytes/log position, apply rate, errors, queue/backlog |
| Database | Commit latency, p95/p99 read/write latency, lock waits, transaction aborts |
| Availability | Connection errors, health, failover state, quorum members và leader changes |
| Application | Error rate, request latency theo region, read-after-write failure, stale response |
| Recovery | RPO thực đo, failover duration, failback duration, restore duration |
| Network | RTT liên vùng, packet loss, throughput, reconnect và TLS errors |
| Cost | Replication traffic, cross-region reads/writes, backup, storage và idle standby |

Theo dõi lag trung bình có thể che giấu một đợt lag dài. Nên có percentile/max, tuổi của log chưa áp dụng và khoảng thời gian replica không theo kịp.

### 16.2. Kịch bản fault injection/chaos test

1. Tăng latency hoặc packet loss liên vùng trong thời gian có tải ghi.
2. Ngắt kết nối replication và quan sát behavior: block write, continue write hay queue log.
3. Dừng primary hoặc một replica; kiểm tra quorum, leader election và fencing.
4. Tạo tải đọc lớn ở region replica và xem ảnh hưởng tới replication apply.
5. Tạo một thao tác ghi rồi ngay lập tức đọc ở region khác để đo read-after-write behavior.
6. Thực hiện duplicate/retry hoặc client timeout sau commit để xác minh idempotency.
7. Diễn tập failover và failback, đo RPO/RTO end-to-end.
8. Khôi phục backup trong môi trường cô lập, xác minh encryption key và dữ liệu nghiệp vụ.

Thử nghiệm cần giới hạn blast radius, có người chịu trách nhiệm, tiêu chí dừng và kế hoạch rollback. Không thử cắt mạng hoặc promote tùy tiện trên production.

### 16.3. Tiêu chí chấp nhận

- Latency đọc/ghi theo region nằm trong SLO.
- Replication lag không vượt ngưỡng staleness/RPO đã phê duyệt trong điều kiện tải bình thường và burst.
- Hệ thống có hành vi xác định khi mất quorum hoặc link liên vùng.
- Không xuất hiện hai writer hợp lệ cho cùng ownership domain.
- Read-after-write được bảo đảm hoặc lỗi stale được xử lý theo hợp đồng.
- Failover/failback hoàn thành trong RTO và RPO mục tiêu.
- Backup restore thành công, bao gồm key, identity, network và cấu hình.
- Chi phí replication, cross-region traffic và standby phù hợp ngân sách.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi multi-AZ là multi-region DR | Mất region vẫn làm dịch vụ ngừng | Xác định failure domain và topology DR riêng |
| Dùng async replica nhưng hứa RPO=0 | Có thể mất log chưa replicate khi primary hỏng | Định nghĩa RPO từ semantics ACK và lag đo được |
| Dùng sync liên vùng cho mọi thao tác | Write latency cao, giảm khả năng ghi khi WAN lỗi | Phân loại dữ liệu và chỉ sync nơi cần |
| Đọc replica ngay sau ghi mà không có policy | Người dùng thấy dữ liệu cũ | Read-your-writes routing/token hoặc primary read |
| Cho hai region ghi cùng row không conflict rule | Lost update hoặc dữ liệu không hội tụ đúng nghiệp vụ | Single-writer ownership hoặc merge/version strategy |
| Promote replica khi primary chỉ mất liên lạc | Split-brain, hai lịch sử ghi | Quorum, fencing, lease/epoch và runbook |
| Chỉ theo dõi replication lag trung bình | Bỏ lỡ tail lag và thời điểm mất dữ liệu | Theo dõi max/percentile, bytes và log age |
| Coi replication là backup | Xóa nhầm/ghi sai lan sang replica | Backup độc lập, immutability, PITR và restore test |
| Chỉ test database failover | API, DNS, secret, pool và worker vẫn lỗi | Diễn tập end-to-end theo hành trình nghiệp vụ |
| Chuyển traffic về region cũ ngay khi phục hồi | Hai writer hoặc dữ liệu chưa đồng bộ | Reconcile, catch-up, fence và planned failback |
| Đặt mọi dữ liệu ở mọi region | Vi phạm data residency và tăng chi phí | Phân loại dữ liệu, residency và replication scope |

## 18. Bài thực hành: thiết kế database cho dịch vụ đặt hàng đa khu vực

Một nền tảng đặt hàng phục vụ khách hàng ở hai region. API chạy tại cả hai, mỗi region có database endpoint gần ứng dụng. Dữ liệu gồm payment ledger, trạng thái order, inventory theo warehouse, catalog và analytics. Doanh nghiệp muốn region còn lại có thể tiếp tục phục vụ khi một region gặp sự cố.

**Yêu cầu bài làm:**

1. Xác định RPO/RTO theo từng miền dữ liệu và giải thích tại sao không nhất thiết giống nhau.
2. Vẽ sơ đồ single-writer/standby và một phương án multi-writer; chỉ rõ luồng replication và read/write routing.
3. Chọn synchronous, asynchronous hoặc semi-synchronous cho từng luồng dữ liệu; nêu tác động latency và failure behavior.
4. Định nghĩa consistency cần thiết cho payment, order, inventory, catalog và analytics.
5. Xác định quorum/witness/fencing để tránh split-brain khi hai region mất liên lạc.
6. Thiết kế read-after-write cho người dùng vừa tạo order ở region A nhưng request tiếp theo tới region B.
7. Mô tả failover và failback, gồm promotion, replication lag, endpoint, connection pool, worker retry và reconciliation.
8. Xây dựng kế hoạch backup/restore đa vùng, key recovery và data residency.
9. Đề xuất dashboard/alert và ít nhất năm kịch bản chaos test.
10. Viết ADR so sánh chi phí, độ trễ, durability, availability và complexity của hai phương án.

### Gợi ý đánh giá

Một phương án tốt không áp cùng một consistency model cho mọi dữ liệu. Payment ledger và reservation cần kiểm soát ghi chặt hơn catalog/analytics. Nếu dùng single-writer, phải thừa nhận latency ghi từ region xa và chuẩn bị failover. Nếu dùng multi-writer, bài làm phải mô tả rõ conflict semantics theo từng entity, cách đảm bảo idempotency/version và điều gì xảy ra khi network partition.

RPO/RTO phải có thể đo và diễn tập; “có replica” hoặc “có backup” chưa đủ. Bài làm cần chỉ rõ ai quyết định promote, làm thế nào ngăn writer cũ, dữ liệu nào có thể mất và cách xác minh sau chuyển vùng.

## 19. Checklist trước khi đưa database đa khu vực vào production

- [ ] Đã xác định failure domain: node, AZ, region, provider và network dependency.
- [ ] RPO/RTO được chủ nghiệp vụ phê duyệt theo từng miền dữ liệu.
- [ ] Chọn primary/standby, read replica hay multi-writer dựa trên workload và semantics.
- [ ] Đã đo latency liên vùng và commit/read p95/p99 dưới tải thực.
- [ ] Replication sync/async/semi-sync có định nghĩa ACK và durability rõ.
- [ ] Consistency model được mô tả theo use case; không gắn một nhãn chung cho toàn hệ thống.
- [ ] Read-after-write và stale-read behavior có hợp đồng, routing và kiểm thử.
- [ ] Partition key/ownership domain và conflict resolution được thiết kế nếu multi-writer.
- [ ] Quorum, leader election, lease/epoch và fencing chống split-brain được xác minh.
- [ ] Failover/failback có runbook, owner, điều kiện promote và rollback.
- [ ] Replication lag được giám sát theo max/percentile/bytes/log age.
- [ ] Backup độc lập, PITR, retention, immutability và restore test được thiết lập.
- [ ] Encryption, identity, key recovery, data residency và cross-region access được phê duyệt.
- [ ] Transaction xuyên service có Saga/outbox/idempotency/reconciliation phù hợp.
- [ ] Ứng dụng, DNS, endpoint, connection pool, secret và worker đều được kiểm thử trong DR.
- [ ] Chaos test có giới hạn, tiêu chí dừng và đo RPO/RTO end-to-end.
- [ ] Tổng chi phí replica, network, backup, standby capacity và vận hành được đánh giá.

**Ghi nhớ:** Database đa khu vực luôn phải cân bằng khoảng cách vật lý, thời điểm xác nhận giao dịch và cách các replica hội tụ. Replication đồng bộ có thể bảo vệ dữ liệu tốt hơn nhưng làm write latency phụ thuộc liên vùng; replication bất đồng bộ giảm độ trễ ghi nhưng tạo staleness và cửa sổ mất dữ liệu khi failover. Hãy chọn consistency theo từng yêu cầu nghiệp vụ, thiết kế quorum/fencing và conflict handling rõ ràng, rồi chứng minh RPO/RTO bằng diễn tập thực tế.
