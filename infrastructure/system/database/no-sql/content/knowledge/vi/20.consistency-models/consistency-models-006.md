# Eventual consistency và các điều kiện để bản sao hội tụ

## 1. Vì sao hai người dùng có thể đọc hai kết quả khác nhau?

Một hệ thương mại điện tử lưu thông tin sản phẩm trên ba bản sao dữ liệu:

~~~text
Replica A: product P101, price = 100.000
Replica B: product P101, price = 100.000
Replica C: product P101, price = 100.000
~~~

Người quản trị sửa giá thành 120.000. Sau đó, hai khách hàng gọi cùng endpoint nhưng nhận các kết quả khác nhau:

~~~text
09:00:00.000   PUT price=120.000 tới replica A
09:00:00.020   A xác nhận ghi theo cấu hình hiện tại
09:00:00.040   Khách X đọc A -> price=120.000
09:00:00.050   Khách Y đọc B -> price=100.000
09:00:00.180   B nhận bản cập nhật -> 120.000
09:00:00.230   C nhận bản cập nhật -> 120.000
~~~

Trong khoảng ngắn, **các bản sao chưa đồng nhất**, nhưng về sau cùng trả 120.000. Đây là ví dụ trực quan về **eventual consistency (nhất quán cuối cùng)**.

Điểm khó không nằm ở việc “dữ liệu có thể trễ”. Câu hỏi quan trọng hơn là:

> **Điều kiện nào bảo đảm các bản sao cuối cùng thực sự hội tụ, thay vì tiếp tục lệch nhau hoặc làm dữ liệu cũ xuất hiện trở lại?**

Bài thuộc chương **Các mô hình nhất quán** của module **Database No SQL**. Các kỹ thuật và ví dụ đề cập đến hệ có leader, leaderless replication, active-active writes, Cassandra/ScyllaDB, MongoDB, DynamoDB, Redis và những read model như search index.

Sau bài học, bạn sẽ có thể:

1. Phát biểu đúng eventual consistency và những giả định ẩn sau chữ “eventually”.
2. Phân biệt **độ mới khi đọc**, **thứ tự thay đổi**, **tính hội tụ** và **tính đúng của nghiệp vụ**.
3. Nhận diện những điều kiện thiết yếu: mạng được khôi phục, mutation không bị mất, replica được sửa, xung đột được giải quyết và metadata xóa còn đủ lâu.
4. Giải thích concurrent writes, lost update, last-write-wins, logical version, vector clock và CRDT.
5. Phân tích quorum, read repair, hinted handoff, anti-entropy và những giới hạn của chúng.
6. Thiết kế read-your-writes, optimistic UX, event-driven projections, retry và reconciliation.
7. Đo replication lag, convergence delay, replica drift và kiểm thử khi mạng bị phân vùng hoặc node trở lại sau thời gian dài.

## 2. Định nghĩa eventual consistency chính xác hơn câu “sớm muộn cũng giống nhau”

### 2.1. Phát biểu theo trạng thái ổn định

Một cách diễn đạt thông dụng:

**Nếu ngừng phát sinh cập nhật mới cho một đối tượng và các điều kiện vận hành cần thiết được đáp ứng, các bản sao cuối cùng sẽ hội tụ về cùng một trạng thái có hiệu lực theo quy tắc của hệ.**

Viết ngắn gọn:

~~~text
Sau một thời điểm T, không có mutation mới của K.

Nếu các bản sao còn tham gia được đồng bộ đầy đủ
và cùng dùng một quy tắc giải quyết xung đột,
thì trạng thái của K tại các replica cuối cùng giống nhau.
~~~

Đây là **tính chất hội tụ khi hệ ngừng thay đổi**, không phải bảo đảm mọi replica bằng nhau ngay sau một lệnh PUT.

### 2.2. Các giả định không được bỏ qua

Chữ “cuối cùng” phụ thuộc vào những điều kiện thực:

- Các thay đổi đã được chấp nhận **không bị mất vĩnh viễn** trước khi được nhân bản hoặc khôi phục.
- Các node có liên quan còn hoạt động hoặc được thay thế/đưa trở lại đúng quy trình.
- Mạng và cơ chế truyền tin cuối cùng cho phép trao đổi thay đổi cần thiết.
- Những mutation bị bỏ lỡ được giao lại, hoặc có cơ chế anti-entropy/snapshot để sửa.
- Xung đột ghi đồng thời có quy tắc giải quyết tạo ra cùng kết quả ở mọi nơi.
- Dấu xóa, phiên bản hoặc causal metadata không bị xóa sớm đến mức không thể phân biệt trạng thái cũ với trạng thái đã xóa.
- Cấu hình và logic xử lý dữ liệu không khiến các replica liên tục diễn giải cùng mutation theo những cách khác nhau.

**Eventual consistency không phải lời hứa vô điều kiện rằng dữ liệu luôn tự sửa sau một khoảng thời gian cố định.**

### 2.3. Không nhất thiết có một giới hạn thời gian

Mô hình eventual consistency thuần túy thường **không hứa số giây tối đa** để hội tụ.

~~~text
Lag 100 ms -> có thể xảy ra.
Lag 5 s    -> có thể xảy ra.
Lag 2 giờ  -> vẫn có thể xảy ra khi sự cố kéo dài.
~~~

Một sản phẩm có thể công bố thêm SLO, cơ chế bounded staleness hoặc mức consistency mạnh hơn. Nhưng không thể lấy chữ eventual rồi suy ra “chắc chắn dưới 1 giây”.

### 2.4. Ngừng ghi là giả định phân tích, không phải yêu cầu vận hành

Hệ thực tế có thể nhận cập nhật liên tục, nên một giá trị có thể đang đuổi theo dòng mutation mới. Khi đó không dễ chỉ ra thời điểm **mọi bản sao bằng nhau** nếu mỗi khi chúng gần hội tụ lại có cập nhật mới.

Định nghĩa “nếu không còn update mới” giúp ta đánh giá tính hội tụ. Trong production, cần đo **độ trễ so với phiên bản nguồn** và trạng thái đồng bộ, chứ không chờ toàn hệ ngừng ghi.

## 3. Tách bốn câu hỏi thường bị trộn lẫn

### 3.1. Freshness: bản sao mới đến đâu?

~~~text
Nguồn version=12
Replica B version=10
~~~

B đang cũ hai phiên bản. Nếu API đọc B, nó có thể trả dữ liệu hợp lệ theo snapshot cũ nhưng chưa phản ánh những mutation gần nhất.

### 3.2. Convergence: các bản sao cuối cùng có giống nhau?

Nếu B và C sẽ nhận hoặc hòa giải đầy đủ các mutation đến version=12, chúng có thể hội tụ:

~~~text
A=12, B=12, C=12
~~~

Nhưng version bằng nhau không đủ trong mọi thiết kế nếu hai writer khác nhau tự cấp cùng số version. Cần một hệ version có **phạm vi và thứ tự được định nghĩa**.

### 3.3. Conflict semantics: “giống nhau” là giá trị nào?

Hai writer cùng cập nhật:

~~~text
Region A: displayName = "An"
Region B: displayName = "Anna"
~~~

Nếu hệ dùng last-write-wins, các replica có thể hội tụ về một trong hai giá trị. Điều đó không bảo đảm người dùng được giữ cả hai thay đổi.

**Hội tụ không đồng nghĩa không mất cập nhật nghiệp vụ.**

### 3.4. Business correctness: invariant có còn đúng?

Ví dụ tồn kho chỉ còn một chiếc, nhưng hai Region đồng thời nhận:

~~~text
Region A: xác nhận bán chiếc cuối cho Order O1.
Region B: xác nhận bán chiếc cuối cho Order O2.
~~~

Ngay cả khi dữ liệu cuối cùng hội tụ về quantity=0, **hai đơn hàng đã được xác nhận** vẫn có thể vi phạm quy tắc không bán quá tồn kho.

Eventual consistency là mô hình về quan sát/hội tụ dữ liệu. Nó **không tự bảo vệ mọi invariant xuyên nhiều thao tác hoặc nhiều Region**.

## 4. Ba dạng kiến trúc có thể tạo eventual consistency

### 4.1. Leader–follower với sao chép bất đồng bộ

~~~text
                Write
Client ----------> Leader A
                    | \
                    |  \ asynchronous replication
                    v   v
               Follower B  Follower C

Read B khi còn lag -> có thể thấy giá trị cũ.
~~~

Một leader thường quyết định thứ tự ghi chính. Follower phát lại mutation theo log/replication protocol.

Nếu leader ACK trước khi thay đổi đạt mức bền vững/replication cần thiết, failover có thể có rủi ro **mất những write đã ACK** theo cấu hình. Vì vậy khả năng hội tụ và độ bền của ghi đã nhận đều phụ thuộc hợp đồng của hệ.

### 4.2. Leaderless hoặc replicated writes với quorum

Một coordinator có thể gửi mutation tới nhiều replica, chấp nhận theo mức write consistency được cấu hình, rồi các bản sao còn thiếu sẽ nhận thay đổi qua repair/handoff.

~~~text
            Coordinator
            /    |    \
           v     v     v
           A     B     C
           ACK   ACK   Offline
~~~

Phần dữ liệu ở C có thể cũ cho đến khi C nhận thay đổi. Các hệ kiểu này phải có quy tắc giải quyết phiên bản/timestamp để xử lý mutation khác nhau trên những replica.

### 4.3. Active-active hoặc multi-leader

~~~text
Region A <------ async replication ------> Region B
  PUT K=red                                  PUT K=blue
~~~

Cả hai phía có thể nhận ghi trước khi biết về thay đổi bên kia. Vì vậy vấn đề không chỉ là **chuyển mutation** mà còn là **giải quyết xung đột đồng thời**.

### 4.4. Read model được cập nhật từ event

~~~text
Transactional source
       |
       v
CDC / Outbox / Event bus
       |
       +--> Search index
       +--> Redis cache
       +--> Dashboard projection
~~~

Đây cũng là một dạng hội tụ cuối cùng, nhưng **khác replication vật lý của database**. Worker có thể chuyển đổi schema, gộp dữ liệu, lọc trường hoặc xây index; vì vậy “hội tụ” nghĩa là projection phản ánh đúng phép chiếu của nguồn, không nhất thiết giữ dữ liệu byte-for-byte giống nguồn.

## 5. Điều kiện thứ nhất: mutation phải tồn tại đủ lâu để được truyền

### 5.1. ACK không tự chứng minh đã nhân bản đầy đủ

Giả sử:

~~~text
t1 Leader nhận PUT K=v2.
t2 Leader trả ACK.
t3 Leader bị mất dữ liệu trước khi follower nhận v2.
t4 Follower v1 được đưa lên làm leader.
~~~

Nếu ACK ở t2 không được bảo vệ bằng durability/replication thích hợp, v2 có thể **không còn nguồn để sao chép**, và hệ không thể hội tụ tới v2.

Điều kiện “không mất mutation đã được chấp nhận” phải được xác định theo **mức ghi đã ACK**: WAL/fsync, commit log, quorum, majority, consensus, failover policy hoặc cơ chế tương ứng.

### 5.2. Replication log hoặc changelog có retention

Nếu follower/consumer bị ngắt kết nối:

~~~text
Source versions: 100 -> 101 -> ... -> 500
Consumer còn ở: 100
Log chỉ giữ:    450 -> 500
~~~

Consumer không thể tiếp tục từ version=101 nếu log đã bị dọn. Cần **full snapshot, backfill hoặc reconciliation** để tái tạo trạng thái đúng.

### 5.3. “At least once” và duplicate events

Một worker có thể nhận cùng mutation nhiều lần khi retry:

~~~text
EVENT K version=12
EVENT K version=12 (giao lại)
~~~

Nếu xử lý bằng phép **gán trạng thái có version** thì duplicate có thể được bỏ qua an toàn. Nếu xử lý bằng:

~~~text
INCREMENT counter by 1
~~~

hai lần sẽ đếm thành 2 trừ khi có dedup hoặc cơ chế cộng dồn có semantics phù hợp.

### 5.4. “Exactly once” cần được hiểu theo phạm vi

Một connector/framework có thể cung cấp exactly-once processing trong một pipeline được định nghĩa. Điều đó không có nghĩa mọi side effect bên ngoài, database và message broker đã hình thành một transaction toàn cục.

Để kết quả cuối hội tụ đúng, phải xử lý **duplicate, retry và checkpoint** ở ranh giới thực mà ứng dụng sử dụng.

## 6. Điều kiện thứ hai: các bản sao phải liên lạc và sửa được chỗ thiếu

### 6.1. Network partition

~~~text
Cluster A | mạng bị chia | Cluster B

A nhận PUT K=v5.
B còn K=v4.
~~~

Nếu mạng bị chia mãi hoặc B bị loại khỏi cluster mà không được phục hồi/thay thế, không thể tự kỳ vọng B nhận v5.

Hội tụ cần một giai đoạn đủ lâu mà mạng và tài nguyên cho phép đồng bộ tiến triển.

### 6.2. Handoff khi replica tạm vắng mặt

Một số hệ có cơ chế giữ mutation cho node tạm mất kết nối, ví dụ **hinted handoff** trong các hệ họ Cassandra.

Hình dung:

~~~text
A nhận mutation M.
C offline.
Hệ lưu thông tin để thử chuyển M tới C sau.
~~~

Nhưng hint có giới hạn retention/cấu hình và không bảo đảm thay thế mọi trường hợp repair. Nếu C offline quá lâu, cần cách sửa dữ liệu đầy đủ hơn.

### 6.3. Anti-entropy

**Anti-entropy** là quá trình so sánh và hòa giải trạng thái giữa các replica, giúp phát hiện mutation thiếu hoặc khác nhau.

Các kỹ thuật có thể bao gồm:

- So sánh phạm vi khóa và hash.
- Merkle tree hoặc những cấu trúc tóm tắt tập dữ liệu.
- Truyền những phần khác biệt.
- Dùng version/timestamp để hòa giải.
- Rebuild snapshot ở nơi thiếu quá nhiều dữ liệu.

Không phải mọi database dùng cùng một thuật toán. Cần đọc tài liệu của engine trước khi vận hành repair.

### 6.4. Merkle tree giúp phát hiện lệch

Một cây hash tóm tắt các nhánh dữ liệu:

~~~text
              H(ALL)
             /      \
         H(A..M)    H(N..Z)
          /   \      /   \
         ...  ...   ...  ...
~~~

Hai replica có thể so sánh hash gốc và các nhánh để xác định vùng dữ liệu có khác biệt. Khi hash khác, quá trình repair cần đọc/truyền nội dung liên quan để hòa giải.

Merkle tree **không tự quyết định phiên bản nào đúng**. Nó chủ yếu hỗ trợ phát hiện/phân vùng chênh lệch; luật conflict resolution vẫn là thành phần riêng.

### 6.5. Read repair

Một số hệ có cơ chế **read repair**: một đường đọc nhận dữ liệu từ những replica với phiên bản khác nhau, rồi đồng bộ bản còn thiếu theo quy tắc engine.

Ưu điểm: Đường đọc có thể góp phần sửa replica.

Giới hạn: **Khóa không được đọc** vẫn có thể lệch. Không thể dựa hoàn toàn vào read repair để đảm bảo toàn bộ dữ liệu hội tụ nếu thiếu anti-entropy hoặc cơ chế truyền log khác.

### 6.6. Repair có thể bị chặn bởi tải hoặc nguồn lực

Nếu đồng bộ luôn thua tốc độ phát sinh mutation, backlog có thể tăng:

~~~text
Mutation mới tạo: 10.000 bản ghi/s
Repair thực hiện: 6.000 bản ghi/s tương đương công việc
Backlog: tăng theo thời gian
~~~

Đây là minh họa về chênh lệch năng lực, không phải phép tính năng suất repair chính xác vì kích thước và chi phí từng bản ghi khác nhau.

Một hệ có cơ chế hội tụ nhưng **không đủ năng lực hoàn tất repair** có thể mãi duy trì replication lag rất lớn trong production.

## 7. Điều kiện thứ ba: có luật giải quyết xung đột để mọi bản sao cho cùng kết quả

### 7.1. Ghi đồng thời không luôn có “ghi cuối” hiển nhiên

Hai Region nhận PUT K:

~~~text
Region A: K = red, localTime=10:00:00.100
Region B: K = blue, localTime=10:00:00.090
~~~

Nếu chúng chưa liên lạc, cả hai không biết chắc mutation nào là “sau” mutation nào trong thứ tự nhân quả. Đồng hồ hai máy có thể lệch.

Để hội tụ, hệ cần một quy tắc chung, chẳng hạn:

- Chọn mutation theo timestamp/sequence number có tiebreaker xác định.
- Chỉ chấp nhận ghi khi condition/version hợp lệ.
- Dùng vector clock để nhận diện hai phiên bản đồng thời và trả conflict cần giải quyết.
- Merge dữ liệu bằng phép toán có tính chất hội tụ như CRDT.
- Đưa mọi cập nhật của khóa về một leader/điểm serialize thống nhất.

### 7.2. Tất cả replica phải xử lý xung đột tương thích

Nếu A chọn phiên bản theo timestamp còn B chọn theo thứ tự arrival:

~~~text
A nhận: red rồi blue.
B nhận: blue rồi red.
~~~

thì chúng có thể giữ kết quả khác nhau. Ngay cả khi đã trao đổi mọi event, khác biệt có thể không tự biến mất.

Một rule hội tụ cần đảm bảo khi hai replica có **cùng tập thông tin**, cách merge tạo cùng kết quả hoặc chúng có cơ chế trao đổi tiếp để đạt trạng thái đó.

## 8. Last-write-wins (LWW): hội tụ nhưng có thể mất một thay đổi

### 8.1. Nguyên lý

**Last-write-wins** thường chọn một mutation có timestamp/ordering key thắng theo quy tắc xác định.

Ví dụ:

~~~text
PUT K="red", timestamp=100
PUT K="blue", timestamp=105
~~~

Nếu mọi replica cùng áp dụng luật chọn timestamp lớn hơn, chúng có thể hội tụ về blue.

### 8.2. Tên “last” dễ gây hiểu nhầm

Trong nhiều hệ, “last” là **lớn nhất theo timestamp hoặc thứ tự logic được dùng**, không nhất thiết là lệnh người dùng thực hiện muộn nhất theo đồng hồ thực.

Đồng hồ vật lý lệch có thể gây:

~~~text
Thời gian thực:
  A ghi red lúc 10:00:01.
  B ghi blue lúc 10:00:02.

Timestamp do client sinh:
  A = 10:00:05 (đồng hồ chạy nhanh).
  B = 10:00:02.

LWW theo timestamp:
  red có thể thắng dù người dùng B thao tác sau.
~~~

### 8.3. Tiebreaker

Nếu hai mutation có cùng timestamp, hệ cần quy tắc giải quyết hòa đủ xác định để không giữ kết quả ngẫu nhiên khác nhau trên mỗi replica.

Không nên tự sáng tạo tiebreaker ở phía ứng dụng mà mâu thuẫn với quy tắc nội bộ của database. Cần hiểu cách hệ xử lý tombstone, field, timestamp trùng và merge.

### 8.4. Lost update

Giả sử một document có:

~~~json
{"name":"An","phone":"090...","version":7}
~~~

Hai client đọc version 7:

- A sửa tên thành “Anna”.
- B sửa số điện thoại.

Nếu mỗi client PUT **cả document** với snapshot cũ, mutation đến sau có thể ghi đè field mà client khác đã thay đổi.

~~~text
A PUT {"name":"Anna","phone":"090..."}
B PUT {"name":"An","phone":"091..."}

Sau LWW: name có thể quay lại "An".
~~~

Các replica vẫn hội tụ, nhưng ý định sửa tên của A bị mất.

### 8.5. Cách bảo vệ

Tùy invariant:

- Field-level patch thay vì ghi đè cả document khi engine hỗ trợ đúng ngữ nghĩa.
- Optimistic concurrency với version/ETag/conditional write.
- Dùng transaction hoặc một leader cho những thao tác xung đột.
- Merge tại ứng dụng khi có đủ bối cảnh.
- CRDT cho các kiểu dữ liệu thích hợp.

Không nên xem LWW như giải pháp chung cho số dư, tồn kho hoặc quyền truy cập.

## 9. Logical clocks, Lamport clocks và version vectors

### 9.1. Physical time không đo chính xác quan hệ nhân quả

Hai sự kiện có timestamp gần nhau không chứng minh một sự kiện xảy ra sau khi đã quan sát sự kiện kia. Đồng hồ bị lệch, NTP điều chỉnh, mạng trễ và event được xử lý lại.

**Happens-before** mô tả quan hệ nhân quả: nếu B được tạo sau khi đã quan sát A, B có thể phụ thuộc A. Hai mutation sinh độc lập ở hai Region có thể là **concurrent**, không có thứ tự nhân quả xác định.

### 9.2. Lamport clock

Lamport clock gán số logic tăng theo các sự kiện và trao đổi tin nhắn, giúp bảo đảm:

\[
A \rightarrow B \implies L(A) < L(B)
\]

với ký hiệu \(A \rightarrow B\) là A xảy ra trước B theo quan hệ nhân quả.

Nhưng chiều ngược lại không luôn đúng:

\[
L(A) < L(B)
\not\implies A \rightarrow B.
\]

Do đó Lamport clock có thể giúp thiết lập thứ tự logic, nhưng một mình nó không xác định hoàn toàn hai thay đổi có **đồng thời về nhân quả** hay không.

### 9.3. Version vector

Một version vector mô tả tiến độ đã quan sát từ nhiều writer/replica:

~~~text
vA = {A:2, B:0}
vB = {A:1, B:1}
~~~

Ở ví dụ này, vA không lớn hơn hoặc bằng vB trên mọi thành phần, và vB cũng không lớn hơn hoặc bằng vA. Chúng được xem là **đồng thời** theo version vector.

Nếu:

~~~text
vC = {A:2, B:1}
~~~

thì vC bao trùm vA và vB theo quan hệ thành phần. Nó thể hiện đã quan sát những tiến độ đó.

### 9.4. Version vector không tự merge nội dung

Version vector giúp phát hiện:

- Bản nào cũ hơn.
- Bản nào đã bao gồm nhân quả của bản khác.
- Hai bản nào chưa thể sắp thứ tự nhân quả.

Nhưng khi hai phiên bản **concurrent**, ứng dụng hoặc engine vẫn phải quyết định:

- Giữ nhiều siblings?
- Merge field?
- Dùng một chính sách winner?
- Yêu cầu người dùng chọn?

Metadata giúp **phát hiện xung đột**, không tự giải quyết mọi xung đột nghiệp vụ.

### 9.5. Chi phí metadata

Version vector có thể tăng kích thước khi số actor/writer lớn. Các hệ thực tế dùng biến thể hoặc cách giới hạn metadata theo membership/phiên bản. Không nên coi ví dụ JSON đơn giản là mô tả chính xác mọi implementation.

## 10. CRDT: thiết kế phép hợp nhất để thứ tự tin nhắn ít quan trọng

### 10.1. Ý tưởng

**Conflict-free Replicated Data Types (CRDTs)** là các kiểu dữ liệu được xây dựng để các replica có thể cập nhật và hợp nhất theo quy tắc bảo đảm hội tụ dưới những giả định tương ứng.

Một số CRDT dạng state-based dùng phép **join** có các tính chất:

1. **Commutative:** \(merge(A,B)=merge(B,A)\).
2. **Associative:** \(merge(merge(A,B),C)=merge(A,merge(B,C))\).
3. **Idempotent:** \(merge(A,A)=A\).

Các tính chất giúp xử lý trường hợp message tới khác thứ tự hoặc gửi trùng mà kết quả cuối vẫn nhất quán.

### 10.2. Ví dụ grow-only counter

Hai replica lưu vector số đếm riêng:

~~~text
Replica A: {A:3, B:0}
Replica B: {A:0, B:5}
~~~

Hợp nhất bằng max từng thành phần:

~~~text
merge -> {A:3, B:5}
total = 3 + 5 = 8
~~~

Nếu gửi lại cùng trạng thái hai lần, max vẫn như cũ. Đây là một cách tránh việc event duplicate làm tăng số đếm không mong muốn trong mô hình CRDT phù hợp.

### 10.3. PN-counter

Một **PN-counter** có thể dùng hai thành phần grow-only: P cho increment và N cho decrement. Giá trị:

\[
value = \sum P_i - \sum N_i.
\]

Đây là công cụ hữu ích cho một số bộ đếm phân tán.

**Giới hạn:** PN-counter hội tụ không đồng nghĩa ngăn giá trị âm hoặc bảo đảm “không bán quá tồn kho” khi nhiều Region cùng decrement. Invariant cần ràng buộc riêng.

### 10.4. Set có thêm và xóa

Một tập:

~~~text
Cart = {itemA, itemB}
~~~

Nếu A thêm itemC và B xóa itemA trong lúc offline, một CRDT set có thể dùng metadata để merge theo semantics định nghĩa.

Nhưng “add thắng remove” hay “remove thắng add” là một lựa chọn thiết kế. Với **Observed-Remove Set (OR-Set)**, thao tác remove thường chỉ loại những instance/add-tag đã được quan sát theo mô hình của nó.

Không nên gộp set bằng cách lấy union đơn giản nếu yêu cầu DELETE có hiệu lực, vì union sẽ làm phần tử bị xóa xuất hiện lại.

### 10.5. CRDT không miễn phí

Chi phí:

- Metadata và tombstone/tag của add/remove.
- Giao thức truyền state hoặc operations.
- Giới hạn garbage collection an toàn.
- Cách phục hồi node offline dài ngày.
- Khó biểu diễn invariant chéo nhiều đối tượng.

CRDT phù hợp cho những kiểu dữ liệu có thể được phân rã và merge một cách có nghĩa, **không phải phép màu giải mọi xung đột nghiệp vụ**.

## 11. Thứ tự sự kiện và duplicate trong read model

### 11.1. Event đến sai thứ tự

Nguồn phát:

~~~text
v10: PRODUCT_UPDATED price=100
v11: PRODUCT_UPDATED price=120
v12: PRODUCT_DELETED
~~~

Worker search có thể nhận:

~~~text
v12 -> v10 -> v11
~~~

Nếu xử lý theo thứ tự arrival:

~~~text
DELETE v12
UPSERT v10
UPSERT v11
~~~

thì document đã xóa có thể **hồi sinh** trong search. Điều đó không chỉ tạo độ trễ nhất thời mà có thể làm trạng thái sai kéo dài nếu không còn event mới để sửa.

### 11.2. Version-aware projector

Một worker nên lưu version mới nhất đã áp dụng:

~~~text
ProjectionMetadata:
  entityId=P101
  lastAppliedVersion=12
  deleted=true
~~~

Sau đó từ chối event version 10/11:

~~~text
if incomingVersion <= lastAppliedVersion:
    ignore as stale-or-duplicate
~~~

**Điều kiện quan trọng:** Việc kiểm tra version và cập nhật projection/metadata phải **nguyên tử hoặc được phối hợp đúng**. Nếu hai worker đọc cùng một version cũ rồi ghi vô điều kiện, worker xử lý event cũ vẫn có thể thắng cuối cùng.

### 11.3. Một số phiên bản cần thứ tự toàn cục theo entity

Không được tự cho mỗi worker hoặc mỗi Region sinh:

~~~text
Event A: entityVersion=7
Event B: entityVersion=7
~~~

rồi tin rằng so sánh số 7 giải quyết xung đột. Version phải được tạo theo một quy tắc có thẩm quyền và phạm vi rõ; nếu là version vector hoặc timestamp thì cách so sánh khác.

### 11.4. Rebuild từ snapshot cũ

~~~text
t1 Snapshot source: P101 version 10
t2 Source updates P101 version 11
t3 Source deletes P101 version 12
t4 Search index rebuild từ snapshot t1
~~~

Nếu rebuild không phát lại events v11/v12 hoặc không đối chiếu trạng thái nguồn hiện hành, P101 có thể xuất hiện lại.

Để hội tụ, cần snapshot có **watermark**, stream thay đổi từ đúng mốc, xử lý event lặp/đảo thứ tự và reconciliation trước khi chuyển traffic sang index mới.

## 12. Tombstone: điều kiện không để dữ liệu đã xóa hồi sinh

### 12.1. Xóa là một mutation

Trong hệ nhiều replica:

~~~text
Replica A: K = ACTIVE, version 7
Replica B: K = ACTIVE, version 7
Replica C: K = ACTIVE, version 7
~~~

C offline, A/B nhận DELETE version 8:

~~~text
A: TOMBSTONE K, version 8
B: TOMBSTONE K, version 8
C: ACTIVE K, version 7
~~~

Nếu A/B chỉ **quên hoàn toàn K**, khi C trở lại, C có thể phát tán bản ACTIVE cũ. Cần giữ một dạng **bằng chứng đã xóa** đủ lâu theo quy tắc storage/replication.

### 12.2. Cassandra và gc_grace_seconds

Trong Cassandra, tombstone và **gc_grace_seconds** liên quan tới thời điểm dữ liệu xóa đủ điều kiện để garbage collect qua compaction, cùng các điều kiện an toàn khác.

Nếu tombstone bị purge trước khi replica offline được repair, có nguy cơ **zombie data/data resurrection**.

Các vấn đề cần phối hợp:

- Node có thể offline tối đa bao lâu?
- Hinted handoff có giới hạn gì?
- Anti-entropy repair đã bao phủ dữ liệu cần thiết chưa?
- Compaction có thể loại tombstone trong điều kiện nào?
- Replica mất quá lâu nên được rebuild hay đưa lại trực tiếp?

Không nên giảm grace period chỉ để giảm tombstone scan mà không kiểm soát repair.

### 12.3. Business tombstone

Trong outbox/search projection, storage engine có thể không giữ tombstone nghiệp vụ đủ để chặn event cũ. Ứng dụng có thể giữ metadata:

~~~json
{
  "entityId": "P101",
  "lastVersion": 12,
  "deleted": true,
  "generation": "G1"
}
~~~

Nó bảo vệ trước event UPDATE version 10/11 đến muộn.

### 12.4. Reuse ID và generation

~~~text
G1: P101 bị xóa ở version 12.
G2: Một sản phẩm mới tái sử dụng ID P101.
Event DELETE của G1 đến muộn.
~~~

Nếu chỉ kiểm tra ID, event cũ có thể xóa G2. Cần tránh tái sử dụng ID hoặc dùng **generation/epoch** và luật ownership rõ ràng.

### 12.5. TTL không phải đồng hồ xóa chính xác

TTL làm dữ liệu hết hiệu lực theo semantics engine, nhưng dọn vật lý có thể bất đồng bộ. Nếu API cần hết hạn token đúng thời điểm, phải kiểm tra expiration ở đường cấp quyền thay vì dựa hoàn toàn vào lúc TTL cleanup xảy ra.

Một replica chứa item đã qua hạn không được tự động coi là item còn hợp lệ nếu nghiệp vụ quy định token đã hết quyền.

## 13. Quorum và eventual consistency có mối liên hệ thế nào?

### 13.1. N, W và R

Trong một mô hình quorum đơn giản:

- \(N\): số replica trong tập dữ liệu liên quan.
- \(W\): số replica cần ACK ghi.
- \(R\): số replica được tham gia/đáp ứng đọc theo giao thức.

Một công thức thường được nhắc:

\[
W + R > N.
\]

Nếu tập read/write thật sự là các tập con của **cùng một nhóm N replica**, điều kiện trên buộc hai tập có ít nhất một replica giao nhau.

### 13.2. Ví dụ N=3

~~~text
N = 3
W = 2
R = 2

W + R = 4 > 3
~~~

Một write được ACK bởi hai replica và read từ hai replica sẽ có ít nhất một replica giao nhau trong mô hình lý tưởng.

### 13.3. Giao nhau không tự bảo đảm linearizability

Quorum intersection **không phải bằng chứng vô điều kiện** rằng mọi đọc luôn thấy phiên bản mới nhất:

- Hai writer có thể ghi đồng thời.
- Replica có thể dùng timestamp khác nhau để giải quyết xung đột.
- Read phải biết hòa giải và trả trạng thái đúng theo giao thức.
- Topology và tập replica có thể đổi khi failover/reconfiguration.
- Multi-datacenter có local quorum khác global quorum.
- Hinted handoff/sloppy quorum trong một số thiết kế có thể làm giao tập thay đổi.
- Đồng hồ bị lệch hoặc repair chưa hoàn tất có thể ảnh hưởng semantics.
- Một số hệ có bảo đảm serial/linearizable riêng thông qua consensus/LWT/transaction.

Vì vậy công thức W+R>N là **một điều kiện giao tập hữu ích dưới giả định nhất định**, không phải cam kết “mọi database quorum đều strong consistent”.

### 13.4. Quorum làm giảm stale reads nhưng không thay repair

Ngay cả khi đọc/ghi quorum giúp quan sát mutation mới, replica vắng mặt vẫn cần nhận dữ liệu. Nếu dữ liệu không bao giờ được đọc, chỉ dựa vào read repair có thể bỏ sót vùng dữ liệu cũ.

**Anti-entropy và cơ chế truyền mutation** vẫn có vai trò để mọi replica hội tụ, chứ không chỉ các request vừa được đọc.

### 13.5. Quorum cũng tạo đánh đổi availability và latency

Nếu số replica đang hoạt động không đủ cho W hoặc R, request có thể bị từ chối hoặc timeout. Chọn consistency level cao hơn thường tăng phạm vi phối hợp và giới hạn availability khi hỏng node, tùy hệ.

Không nên tăng toàn bộ query lên mức cao nhất nếu phần lớn workload chấp nhận dữ liệu trễ ngắn; hãy chọn theo invariant và trải nghiệm cần bảo vệ.

## 14. Eventual, strong, causal và các bảo đảm phiên người dùng

### 14.1. Eventual consistency

Reader có thể thấy giá trị cũ sau ghi, nhưng dưới điều kiện cần thiết các replica cuối cùng hội tụ.

### 14.2. Strong consistency

“Strong” là thuật ngữ có nhiều cấp, cần xác định chính xác: strong read, linearizable operation, serializable transaction hoặc snapshot isolation không đồng nghĩa nhau.

Nếu một API công bố **linearizable read/write** trong phạm vi xác định, thao tác phải phù hợp một thứ tự duy nhất tôn trọng thời gian thực của những thao tác không chồng lắp. Đây là bảo đảm mạnh hơn eventual consistency thuần túy.

### 14.3. Read-your-writes (RYW)

Người dùng vừa cập nhật hồ sơ và đọc lại phải thấy ít nhất chính thay đổi của mình:

~~~text
Client PUT profile version=12 -> success.
Client GET profile -> không được trả version 11 nếu hứa RYW.
~~~

Eventual consistency đơn thuần **không tự cung cấp RYW** khi request đọc được route sang replica cũ.

### 14.4. Monotonic reads

Nếu một session đã thấy version 12 thì không nên đọc lùi về version 11 ở lần sau:

~~~text
Read 1: version 12
Read 2: version 11  -> vi phạm monotonic reads.
~~~

Một load balancer chuyển request giữa các follower có độ trễ khác nhau có thể gây hiện tượng này nếu không có session routing/token phù hợp.

### 14.5. Monotonic writes

Những mutation của cùng client cần được áp dụng theo một thứ tự phù hợp, thay vì update sau bị update trước ghi đè khi event đến trễ.

### 14.6. Causal consistency

Nếu mutation B được tạo sau khi đã quan sát A, client có thể yêu cầu B không được hiển thị trước các phụ thuộc cần thiết theo mô hình causal của hệ.

Ví dụ:

~~~text
A: Tạo bài viết.
B: Bình luận vào bài viết sau khi đã đọc A.
~~~

Một viewer không nên thấy bình luận B nhưng chưa thấy bài viết A nếu hệ hứa causal consistency trong phạm vi đó.

### 14.7. Bảng nhu cầu người dùng

| Trải nghiệm | Bảo đảm cần xem |
|---|---|
Đếm lượt xem có thể cập nhật trễ | Eventual có thể đủ |
Vừa sửa profile phải thấy thay đổi | Read-your-writes |
Đã thấy trạng thái mới không đọc lùi | Monotonic reads |
Bình luận không xuất hiện trước bài viết gốc | Causal ordering/consistency |
Hai người không được mua cùng ghế | Conditional write/transaction/invariant protection |
Không chấp nhận token đã thu hồi | Đường auth có consistency/revocation phù hợp |

Không thể thay thế toàn bộ các yêu cầu này chỉ bằng việc nói hệ dùng “NoSQL eventual”.

## 15. Làm read-your-writes trên một hệ eventual

### 15.1. Đọc từ leader hoặc nguồn có thẩm quyền

Nếu kiến trúc hỗ trợ, sau ghi có thể đọc từ leader/primary hoặc một đường đọc được bảo đảm mới tương ứng. Cần biết write đã commit ở mức nào và read concern/consistency nào được dùng.

### 15.2. Session affinity

Client tạm thời được route tới replica đã nhận write:

~~~text
Write tới A.
Các read gần nhất của session cũng tới A.
~~~

Điều này có thể giảm stale reads, nhưng cần xử lý:

- Replica A lỗi hoặc bị thay.
- Load balancer đổi route.
- Write khác đi qua hệ khác.
- Session chuyển Region.

Affinity không phải bảo đảm mạnh vô điều kiện.

### 15.3. Version token

API write trả một token thể hiện version đã commit:

~~~json
{
  "entityId": "P101",
  "status": "UPDATED",
  "committedVersion": 12
}
~~~

Client gửi yêu cầu đọc yêu cầu ít nhất version đó:

~~~http
GET /products/P101
X-Min-Version: 12
~~~

Service có thể:

1. Đọc từ replica đủ mới.
2. Đợi replica bắt kịp trong deadline.
3. Fallback về nguồn có thẩm quyền.
4. Trả lỗi/tín hiệu retry nếu không đáp ứng mức mới yêu cầu.

Đây là **mẫu thiết kế API**, không phải HTTP header chuẩn của mọi NoSQL.

### 15.4. Optimistic UI

Ứng dụng có thể hiển thị dữ liệu người dùng vừa gửi ngay trong UI, sau đó chờ server xác nhận và đồng bộ. Phương án này cải thiện cảm giác phản hồi nhưng không tự giải quyết giao dịch:

- Nếu write bị từ chối, UI phải rollback/tái đồng bộ.
- Không được hiển thị “thanh toán thành công” chỉ vì đã cập nhật optimistic state.
- Một client khác vẫn có thể đọc bản cũ.

### 15.5. Caching và phiên bản

Cache-aside có thể bị điền lại giá trị cũ:

~~~text
t0 Request A đọc source version 10.
t1 Request B ghi version 11.
t2 Cache invalidation.
t3 Request A SET cache version 10.
~~~

Nếu cache hỗ trợ version-aware write, có thể từ chối việc ghi v10 sau v11. Nếu chỉ xóa cache một lần mà không điều phối nguồn dữ liệu, cache có thể **tái nhiễm dữ liệu cũ**.

## 16. Ví dụ Java: projection từ chối sự kiện cũ

### 16.1. Sự kiện có version

Một payload sự kiện:

~~~json
{
  "eventId": "EVT-1201",
  "entityId": "P101",
  "generation": "G1",
  "version": 12,
  "operation": "UPDATE",
  "payload": {
    "name": "Bút máy",
    "priceMinor": 120000
  }
}
~~~

Mỗi event phải có identity và version phù hợp với quy tắc nguồn. Với concurrent multi-writer, một số nguyên version do từng Region tự sinh là **không đủ** để so sánh toàn cục.

### 16.2. Thiết kế một projector

Giả mã gần Java:

~~~java
record ChangeEvent(
    String eventId,
    String entityId,
    String generation,
    long version,
    boolean deleted,
    String payloadJson
) {}

enum ApplyResult {
    APPLIED,
    STALE_OR_DUPLICATE,
    GENERATION_CONFLICT
}

ApplyResult apply(ChangeEvent incoming) {
    // repository phải hỗ trợ CAS/transaction cùng phạm vi
    // cho bước đọc/so sánh và ghi metadata + projection.
    return repository.compareVersionAndApplyAtomically(incoming);
}
~~~

Phần then chốt nằm ở **compareVersionAndApplyAtomically**. Một triển khai sai:

~~~java
if (incoming.version() > repository.findVersion(incoming.entityId())) {
    repository.savePayload(incoming);
    repository.saveVersion(incoming.entityId(), incoming.version());
}
~~~

vẫn có race nếu hai worker cùng đọc version cũ rồi ghi theo thứ tự khác nhau.

### 16.3. Giả mã atomic apply

~~~text
apply(event):
    atomic transaction/conditional mutation:
        current = getProjectionMetadata(event.entityId)

        if current.generation != event.generation:
            followExplicitGenerationPolicy()

        if event.version <= current.lastAppliedVersion:
            return STALE_OR_DUPLICATE

        if event.operation == DELETE:
            deleteVisiblePayload()
            retainMinimalTombstone(event.version)
        else:
            upsertPayload(event.payload)
            saveLastAppliedVersion(event.version)

    return APPLIED
~~~

Nếu payload ở search engine còn metadata version ở một database khác, chúng **không tự nằm trong cùng transaction**. Cần một cơ chế hỗ trợ conditional/versioned writes của search hoặc mô hình serialization/reconciliation thích hợp; không coi giả mã trên là transaction đa hệ có thật.

### 16.4. Idempotency

Sự kiện EVT-1201 có thể được gửi hai lần. Consumer phải nhận diện duplicate bằng eventId hoặc version/generation theo ngữ nghĩa thao tác.

Với phép SET “giá=120.000 ở v12”, replay thường có thể kiểm soát bằng version. Với phép **INCREMENT salesCount**, dedup từng event hoặc CRDT/counter semantics phù hợp là quan trọng để không đếm đôi.

### 16.5. Thứ tự trong partition/event stream

Một event bus có thể bảo đảm ordering **theo partition/key** nhưng không có thứ tự toàn cục trên mọi partition. Nên gắn các event của cùng entity vào một routing key nhất quán khi cần giảm reorder.

Tuy nhiên, event ordering không thay thế việc xử lý duplicate và việc consumer phục hồi từ checkpoint cũ.

## 17. Eventual consistency giữa nhiều bản ghi không phải transaction

### 17.1. Hai item cập nhật riêng

~~~text
Order O101.status = PAID
Payment P101.status = CAPTURED
~~~

Một projection có thể nhận event Order trước Payment:

~~~text
t1: Order read model -> PAID
t2: Payment read model -> PENDING
t3: Payment event đến -> CAPTURED
~~~

Cuối cùng cả hai projection hội tụ, nhưng trong khoảng t1–t3, người đọc thấy **trạng thái hỗn hợp**.

### 17.2. Atomic commit tại nguồn không tự tạo atomic visibility ở projection

Ngay cả nếu Order và Payment được cập nhật trong một transaction ACID ở nguồn, hai projector độc lập có thể áp dụng hai phần ở những thời điểm khác nhau.

Nếu dashboard cần hiển thị một snapshot logic nhất quán, có thể:

- Dùng một projection gộp nhận cùng transaction/event version.
- Công bố bản chiếu mới theo watermark khi các thành phần đủ dữ liệu.
- Đọc trực tiếp từ nguồn giao dịch cho thao tác nhạy cảm.
- Dùng snapshot/versioned read phù hợp với hệ.

### 17.3. Monotonic aggregate

Ví dụ dashboard tổng doanh thu của ngày có thể cập nhật trễ. Nếu dùng “latest event version” cho toàn aggregate mà nhiều shard tự tăng version, việc so sánh version có thể sai. Cần watermark theo partition, logical clock, transaction log position hoặc cơ chế gộp được thiết kế rõ.

### 17.4. Không suy ra global snapshot từ các replica độc lập

Việc từng key cuối cùng hội tụ không có nghĩa hệ cung cấp **một ảnh chụp đồng nhất của tất cả key tại một thời điểm**. Đó là bảo đảm mạnh hơn, liên quan transaction/snapshot isolation/causal consistency.

## 18. Cassandra/ScyllaDB: trạng thái mới nhất và anti-entropy

### 18.1. Replication factor và consistency level

Một bảng Cassandra RF=3 có thể chứa cùng partition trên ba replica. Tùy consistency level của read/write, coordinator có thể xác nhận thao tác khi một phần hoặc nhiều replica phản hồi.

~~~text
RF=3
Write ở mức ONE:
  Một replica xác nhận.
  Replica khác có thể cập nhật trễ.

Read ở mức ONE:
  Có thể đọc replica đang cũ.
~~~

Ví dụ có tính khái niệm, không thay thế hợp đồng của cấu hình/phiên bản cụ thể.

### 18.2. Timestamp và conflict resolution

Cassandra sử dụng timestamp của mutation khi hòa giải nhiều giá trị/cell tương ứng, với các quy tắc bổ sung liên quan tombstone và trường hợp hòa timestamp.

Vì thế:

- “Ghi tới coordinator cuối cùng” không nhất thiết thắng.
- Timestamp sai/lệch có thể khiến mutation cũ chiếm ưu tiên.
- Cập nhật nhiều cell độc lập không đồng nghĩa transaction serializable xuyên mọi partition.

### 18.3. Read repair và repair định kỳ

Một số kiểu đọc có thể tham gia sửa khác biệt, nhưng anti-entropy repair định kỳ vẫn có vai trò quan trọng để đồng bộ **những partition không được truy vấn thường xuyên**.

Khi một node offline lâu, đừng chỉ mở node lại và giả định mọi tombstone đều còn đủ để nó bắt kịp. Phải xem chính sách repair, gc grace và khả năng rebuild node.

### 18.4. LWT cho quyết định cần mạnh hơn eventual

Nếu hai client muốn giành cùng username, thao tác:

~~~sql
INSERT INTO usernames_by_tenant (
    tenant_id, username_canonical, user_id
) VALUES (
    'T17', 'alice', 550e8400-e29b-41d4-a716-446655440001
) IF NOT EXISTS;
~~~

sử dụng **lightweight transaction** trong phạm vi hệ hỗ trợ để bảo vệ create-if-absent. Đây là ví dụ chọn mức bảo đảm mạnh hơn khi invariant không thể chấp nhận hai người thắng.

Không dùng read ONE rồi INSERT thường nếu yêu cầu là unique ownership.

## 19. MongoDB: secondary lag, write concern và read concern

### 19.1. Primary và secondary

Trong MongoDB replica set, primary xử lý các ghi theo vai trò và secondary sao chép/áp dụng thay đổi theo cơ chế replication.

Nếu ứng dụng đọc secondary, giá trị có thể trễ so với primary:

~~~text
Primary:   profile version 12
Secondary: profile version 11
~~~

Độ trễ có thể biến thiên theo tải và trạng thái node.

### 19.2. Majority write concern

Một write với majority write concern được xác nhận theo mức sao chép/bền vững mà MongoDB định nghĩa trong cấu hình hiện hành. Điều đó giúp giảm một số rủi ro rollback so với write concern yếu hơn.

**Nhưng majority write không có nghĩa mọi secondary đã bắt kịp, hay mọi query từ bất cứ node nào tự có read-your-writes.**

### 19.3. Read concern và causal session

MongoDB có các lựa chọn read concern và causal consistency trong session theo điều kiện được hỗ trợ. Khi thiết kế RYW/monotonic reads, cần đồng bộ read preference, write concern, read concern và session token, thay vì chỉ bật “đọc secondary” rồi cho rằng client sẽ luôn thấy thay đổi của mình.

### 19.4. Change streams là pipeline riêng

Nếu dashboard/search được xây từ MongoDB change stream, đó là lớp có **consumer lag và retention log** riêng. Replication của secondary đã hội tụ **không chứng minh** projection bên ngoài đã cập nhật.

## 20. DynamoDB: strong read, eventual GSI và Global Tables

### 20.1. Eventual read và strongly consistent read

DynamoDB cho phép chọn strongly consistent read trong những phạm vi hỗ trợ, ví dụ đọc phù hợp trên bảng cơ sở tại một Region. Nhiều access path mặc định dùng eventually consistent reads.

Một query eventual có thể thấy dữ liệu cũ sau ghi.

### 20.2. Global Secondary Index

**GSI** được cập nhật bất đồng bộ và chỉ hỗ trợ eventually consistent reads. Vì vậy:

~~~text
PutItem vào bảng chính -> success.
Query GSI ngay sau đó  -> có thể chưa thấy item mới.
~~~

Nếu một API dùng GSI để quyết định “username chưa tồn tại” rồi tạo user, nó có thể bị race/stale read. Tính duy nhất cần bảo vệ bằng primary key/conditional write hoặc transaction claim thích hợp.

### 20.3. Global Tables

DynamoDB Global Tables có những chế độ với bảo đảm khác nhau theo tính năng/cấu hình, bao gồm chế độ multi-Region eventual và những lựa chọn consistency mạnh hơn ở những điều kiện được hỗ trợ.

Với cấu hình **multi-Region eventual replication**, hai Region có thể đồng thời nhận cập nhật cho cùng item trước khi thông tin hội tụ. Quy tắc conflict resolution của chế độ đó quyết định trạng thái cuối; không nên suy rằng transaction local hoặc conditional write local tạo global serializability trong mọi cấu hình.

### 20.4. TTL cũng không dọn tức thì

Item có expiresAt đã qua hạn có thể còn tồn tại đến khi TTL process dọn theo cơ chế bất đồng bộ. Với token/permission, phải kiểm tra thời điểm hết hiệu lực trong logic nghiệp vụ, không coi tồn tại vật lý là còn quyền.

### 20.5. DynamoDB Streams và projector

Streams có thể dùng cho việc đồng bộ cache/search. Worker phải quản lý checkpoint, duplicate, retry, retention và thứ tự của luồng theo phạm vi được dịch vụ định nghĩa. Không tự suy một event trên stream được xử lý đúng một lần trên mọi đích.

## 21. Redis: replication bất đồng bộ và cache hội tụ

### 21.1. Primary–replica

Trong nhiều cấu hình Redis, replica nhận thay đổi từ primary bất đồng bộ. Ngay sau một SET:

~~~text
Primary K=v2
Replica K=v1
~~~

Đọc replica có thể cũ cho đến khi đồng bộ. Failover và persistence còn ảnh hưởng mức durability của mutation đã ACK, tùy cấu hình.

### 21.2. WAIT không thay mọi loại bảo đảm

Redis có những cơ chế như WAIT để đợi xác nhận replication từ một số replica trong phạm vi lệnh được hỗ trợ. Tuy nhiên **replica ACK không tự đồng nghĩa một consensus-based transaction bền vững hoặc linearizable failover trên toàn cụm**.

Nếu cần bảo đảm không oversell hoặc không cấp quyền hai lần, dùng primitive/nguồn có contract đủ mạnh cho invariant đó.

### 21.3. Cache invalidation

Một thiết kế cache cần:

- Xác định source of truth.
- Invalidate hoặc update đúng key.
- Ngăn event cũ làm cache hồi sinh dữ liệu.
- Dùng TTL như giới hạn phụ, không thay conditional version.
- Có fallback khi cache đang chậm hoặc unavailable.

### 21.4. Negative cache và tombstone

Nếu một user đã bị xóa, negative cache có thể ngăn một số request tải lại dữ liệu cũ. Nhưng cần version/generation hoặc deletion gate ở đường phục vụ để chống race khi worker khác điền cache từ snapshot trước lúc xóa.

## 22. Search index: eventual projection khác replicated source

### 22.1. Pipeline

~~~text
Source commit v12
   |
   v
CDC/Outbox v12
   |
   v
Indexer xử lý v12
   |
   v
Search engine nhận update
   |
   v
Refresh -> search query quan sát v12
~~~

Một indexer nhận update chưa chắc query đã nhìn thấy thay đổi ngay; các search engine như Elasticsearch/OpenSearch có cơ chế **refresh** riêng.

### 22.2. Hai loại độ trễ

**Replication/ingestion lag:** Từ source commit đến khi worker/search write path nhận/applied mutation.

**Search visibility lag:** Từ khi search write được ACK đến khi search query có thể thấy thay đổi theo cấu hình refresh.

Tổng độ trễ của tính năng tìm kiếm có thể gồm cả hai.

### 22.3. Search và source có thể có biểu diễn khác

Một bảng nguồn lưu:

~~~json
{"productId":"P101","priceMinor":120000,"status":"ACTIVE"}
~~~

Search document có thể thêm:

~~~json
{
  "productId": "P101",
  "searchText": "bút máy",
  "priceBucket": "100k-200k",
  "status": "ACTIVE"
}
~~~

Hội tụ nghĩa document search phản ánh **projection đúng** của source v12, không phải giống từng byte.

### 22.4. Search–hydrate–validate

Nếu giá và tồn kho phải chính xác ở bước thanh toán:

1. Search tìm product IDs theo từ khóa.
2. API lấy thông tin hiện tại từ nguồn có thẩm quyền.
3. Kiểm tra trạng thái bán, tồn kho và giá tại bước giao dịch.

Một kết quả tìm kiếm eventual nên được xem là **ứng viên**, không là quyết định cuối cùng của invariant nhạy cảm.

## 23. Điều kiện hội tụ trong hệ đa tầng

Một nền tảng có:

~~~text
Operational NoSQL
   |
   +--> Replica khác Region
   +--> Cache
   +--> Search
   +--> Analytics
   +--> Notifications
~~~

Để người dùng thấy hệ “đã hội tụ”, cần xác định **phạm vi**:

- Replica nguồn có cùng phiên bản/trạng thái theo rule.
- Cache không còn phục vụ dữ liệu stale.
- Search thấy bản chiếu mới sau refresh.
- Analytics phản ánh event theo watermark hoặc kỳ tổng hợp.
- Notification là side effect bên ngoài; không thể đơn giản “hội tụ” bằng việc gửi lại nếu đã gửi trùng.

**Một hệ có thể hội tụ ở tầng database nhưng vẫn chưa hội tụ ở tầng API người dùng.**

### 23.1. Đồ thị phụ thuộc

~~~mermaid
flowchart TD
    A["Commit tại nguồn"] --> B["Replica cùng cụm"]
    A --> C["Outbox/CDC"]
    C --> D["Event bus"]
    D --> E["Search index"]
    D --> F["Cache invalidation"]
    D --> G["Analytics projection"]
    B --> H["Đường đọc API"]
    E --> H
    F --> H
    G --> I["Dashboard"]
~~~

Trên một đường đọc kết hợp nhiều nguồn, độ mới được quyết định bởi **những phụ thuộc cần thiết cho tính năng**, không chỉ metric replication lag thấp nhất.

### 23.2. Không đợi mọi thành phần cho mọi thao tác

Một API tạo order có thể chờ transaction nguồn nhưng không đợi analytics dashboard hoặc email để trả kết quả. Trong khi đó, API xác thực phải kiểm tra quyền truy cập với mức consistency cao hơn.

Mục tiêu là **phân loại nhu cầu consistency theo thao tác**, không ép mọi thứ mạnh nhất hoặc eventual yếu nhất.

## 24. Phân biệt consistency, availability và partition tolerance

### 24.1. Phân vùng mạng tạo lựa chọn khó

Nếu hai Region không liên lạc, hệ phải quyết định:

- Có tiếp tục nhận những ghi có thể xung đột không?
- Có từ chối một số mutation để bảo vệ invariant không?
- Có chỉ phục vụ đọc cũ không?

Những lựa chọn tùy contract. Không có cách cấu hình một flag eventual để tránh mọi đánh đổi.

### 24.2. CAP được hiểu theo phạm vi

Trong một network partition, một hệ không thể vừa bảo đảm mọi request đều có response thành công đúng hạn trên mọi phía **vừa** duy trì một dạng strong consistency như linearizability trên cùng dữ liệu xung đột.

Nhưng không nên đơn giản phân loại mọi NoSQL thành “AP” và mọi SQL thành “CP”. Một sản phẩm có nhiều consistency level, chế độ replication và transaction; từng loại operation có thể đánh đổi khác nhau.

### 24.3. Eventual không đồng nghĩa luôn available

Một hệ eventual vẫn có thể từ chối ghi vì:

- Không đủ replica sống.
- Write quorum không đạt.
- Disk full, throttling hoặc overload.
- Leader election chưa xong.
- Không có cách ghi dữ liệu bền vững theo hợp đồng.

Consistency model không tự đảm bảo availability trong mọi lỗi.

### 24.4. Strong không đồng nghĩa không bao giờ trễ

Một hệ strong có thể đợi phối hợp hoặc trả timeout khi mạng lỗi. Bảo đảm mạnh hơn thường gắn với chi phí latency/availability nhất định. Phải chọn theo **business consequence của stale data**, không phải chỉ theo tốc độ trung bình.

## 25. Phân biệt “stale nhưng chấp nhận” với “không được phép stale”

| Dữ liệu/tính năng | Ví dụ | Có thể dùng eventual? | Điều kiện |
|---|---|---|---|
Lượt xem | Count cập nhật chậm | Thường có thể | Chấp nhận lag và dedup |
Danh sách sản phẩm tìm kiếm | Kết quả search chưa cập nhật ngay | Thường có thể | Xác minh giá/tồn ở checkout |
Trang cá nhân sau khi sửa | User muốn thấy ngay thay đổi | Có thể, nếu thêm RYW | Session token/read leader/optimistic UI có rollback |
Dashboard tổng hợp | Doanh thu có watermark trễ | Thường có thể | Công bố “cập nhật đến” và đối soát |
Đặt một ghế cuối | Không bán trùng ghế | Eventual đơn thuần không đủ | Conditional reservation/transaction |
Chuyển tiền | Không mất cân đối số dư | Eventual projection có thể phụ trợ | Invariant ở ledger giao dịch |
Thu hồi quyền | Token/user bị khóa | Không nên dựa vào cache stale | Đường kiểm tra/revocation phù hợp |
Unique username | Một owner duy nhất | Không chỉ search/GSI eventual | Unique index/conditional claim |
Xóa dữ liệu cá nhân | Không phục vụ hồ sơ đã xóa | Projection eventual cần gate | Chặn đường đọc, deletion workflow |

**Quy tắc:** Có thể để bản sao hiển thị chậm, nhưng không được để một bản sao chậm trở thành **nơi quyết định giao dịch hoặc quyền** khi invariant đòi dữ liệu mới.

## 26. Đo thời gian hội tụ trong production

### 26.1. Replication lag

Một chỉ số đơn giản:

\[
\text{ReplicationLag}
= t_{\text{replica applied mutation}}
- t_{\text{source commit}}.
\]

Với hệ sử dụng log position/sequence number, có thể đo khoảng cách giữa vị trí được commit ở nguồn và vị trí replica đã phát lại.

Đừng chỉ nhìn **network latency**, vì consumer có thể bị backlog xử lý, disk chậm hoặc lỗi retry.

### 26.2. Visibility lag

Đối với search/dashboard:

\[
\text{VisibilityLag}
= t_{\text{first observable correct result}}
- t_{\text{source commit}}.
\]

Một sự kiện đã đến worker nhưng chưa được visible sau refresh thì metric “consumer lag=0” **chưa đủ** để đánh giá trải nghiệm người dùng.

### 26.3. Convergence delay

Với một mutation có version v:

\[
\text{ConvergenceDelay}(v)
= t_{\text{all in-scope replicas reflect v}}
- t_{\text{commit}(v)}.
\]

Thực tế khó quan sát chính xác mọi replica ngay tức thì, đặc biệt khi dữ liệu tiếp tục thay đổi. Có thể dùng watermark, health, reconciliation và sample probe. Cần định nghĩa rõ **in-scope replicas**: những node đang phục vụ, các Region, read models hay cả hệ lưu offline.

### 26.4. SLO không phải định nghĩa eventual

Ví dụ mục tiêu vận hành:

~~~text
99% product search updates visible trong 5 giây.
99,9% cache invalidations applied trong 2 giây.
Không phục vụ permission revoked sau khi revocation gate hoàn tất.
Các deletion jobs còn lại được theo dõi và đối soát.
~~~

Đây là **ví dụ SLO tự đặt**, không phải cam kết sẵn có của Cassandra, DynamoDB hay search engine. Hệ có thể vi phạm SLO nhưng vẫn được mô tả theo eventual consistency, hoặc có sự cố đủ nghiêm trọng khiến điều kiện hội tụ không còn được đáp ứng.

### 26.5. Các chỉ số cần kết hợp

| Metric | Ý nghĩa |
|---|---|
| Source commit rate | Tốc độ mutation mới |
| Replica apply lag / log offset lag | Replica còn thiếu bao nhiêu thay đổi |
| Oldest unapplied mutation age | Phần công việc bị kẹt lâu nhất |
| Anti-entropy repair backlog | Chênh lệch chưa hòa giải |
| Number of stale replicas | Số bản sao chậm |
| Conflict count / resolution type | Tần suất ghi đồng thời và cách xử lý |
| LWW overwrite count | Nguy cơ lost update |
| Tombstone/TTL metrics | Nguy cơ dữ liệu cũ hồi sinh |
| Outbox/CDC consumer lag | Projection chưa bắt kịp |
| DLQ/retry count | Event chưa xử lý thành công |
| Reconciliation mismatch count | Những bản sao khác nguồn |
| p95/p99 visibility lag | Độ trễ mà người dùng thực thấy |
| RYW violation rate | Người dùng đọc không thấy write của mình |
| Region failover/rejoin health | Khả năng phục hồi và hội tụ |

### 26.6. Watermark

Một projector có thể công bố:

~~~text
Source committed through eventId=1200.
Search processed through eventId=1180.
Analytics processed through eventId=1175.
~~~

Nhưng một **eventId tự tăng không phải watermark hợp lệ** nếu event được phát qua nhiều partition và các ID không có thứ tự tổng. Cần log offset/sequence theo đúng phạm vi, hoặc vector watermark mô tả nhiều shard.

### 26.7. Đối soát bằng version/hash

Một job có thể so sánh:

~~~text
Source  P101: version=12, hash=H12
Search  P101: version=11, hash=H11
~~~

và chủ động rebuild P101. Hash phải tính trên **phép chiếu dữ liệu tương ứng**, không so raw JSON của hai hệ có schema khác nhau.

## 27. Khi replica bị lỗi lâu: không chỉ tiếp tục đọc log

### 27.1. Node rời cụm nhiều ngày

~~~text
Ngày 1: Node C offline.
Ngày 2: K được cập nhật v10.
Ngày 3: K bị xóa v11.
Ngày 4: WAL/hints hoặc change log cũ dần hết retention.
Ngày 10: C trở lại với K v9.
~~~

Nếu không còn thông tin v10/v11 hoặc bằng chứng xóa để repair, C không thể đơn giản “bắt kịp” chỉ bằng cách đọc phần log còn lại.

### 27.2. Khi nào cần rebuild?

Tùy engine:

- Thời gian offline vượt ngưỡng an toàn.
- Replica có log gap không thể resume.
- SSTable/tombstone đã được GC theo chính sách.
- Membership/topology thay đổi.
- Dữ liệu bị hỏng hoặc snapshot không tương thích.

Trong các trường hợp đó, có thể phải **thay node/rebuild từ nguồn lành** bằng quy trình chính thức.

### 27.3. Không gắn node cũ trở lại tùy tiện

Với Cassandra hoặc hệ leaderless, việc cho node stale lâu ngày tham gia lại mà không theo hướng dẫn repair/rebuild có thể tăng nguy cơ zombie data hoặc dữ liệu sai. Tương tự với projection worker, resume từ checkpoint quá cũ có thể thất bại hoặc bỏ sót xóa.

**Phục hồi replica là một phần của điều kiện hội tụ**, không chỉ là bật lại process.

## 28. Sơ đồ tiến trình hội tụ và các điểm có thể hỏng

~~~mermaid
flowchart TD
    A["Mutation mới được chấp nhận"] --> B{"Mutation đủ bền vững?"}
    B -- "Không" --> X["Nguy cơ mất write đã ACK"]
    B -- "Có" --> C["Replication / Event log"]
    C --> D{"Replica nhận đầy đủ?"}
    D -- "Chưa" --> E["Retry, handoff, anti-entropy hoặc rebuild"]
    E --> D
    D -- "Rồi" --> F{"Có ghi đồng thời?"}
    F -- "Có" --> G["Quy tắc conflict resolution / merge"]
    F -- "Không" --> H["Áp dụng trạng thái nguồn"]
    G --> H
    H --> I{"Tombstone/causal metadata đủ?"}
    I -- "Không" --> Y["Nguy cơ hồi sinh hoặc mất update"]
    I -- "Có" --> J["Replica hội tụ trong phạm vi"]
    J --> K["Projection/cache/search visible theo SLO"]
~~~

Sơ đồ minh họa những điều kiện. Không phải engine nào cũng có từng thành phần y hệt; ví dụ một hệ dùng consensus sẽ có cách xác nhận và truyền trạng thái khác hệ anti-entropy.

Điểm chung là **không thể bỏ một khâu quan trọng rồi vẫn bảo đảm hội tụ đúng** chỉ bằng cách gắn nhãn eventual consistency.

## 29. Kiểm thử hội tụ: không chỉ test khi mạng bình thường

### 29.1. Test độ trễ replication

1. Ghi K version 1 rồi version 2.
2. Ngay lập tức đọc từ từng replica theo phạm vi được hỗ trợ.
3. Ghi lại phiên bản thấy được và thời điểm hội tụ.
4. Lặp lại dưới tải và với nhiều loại item/kích thước.

Mục tiêu là đo **staleness distribution**, không phải đòi mọi read trả version 2 khi hợp đồng chỉ eventual.

### 29.2. Test network partition

Giả lập node/Region bị cô lập trong môi trường thử nghiệm:

~~~text
Trước partition: A=B=C, K=v1
Trong partition: A nhận K=v2, B/C chưa nhận
Sau khôi phục: kiểm tra repair và K cuối cùng
~~~

Nếu hệ có multi-writer, thử hai mutation concurrent trên cùng key.

### 29.3. Test ghi đồng thời

~~~text
Writer A: set field x=10
Writer B: set field y=20
~~~

Quan sát:

- Mọi replica cuối cùng có cùng document không?
- Có lost update do whole-document overwrite không?
- Quy tắc merge được công bố là gì?
- Client có nhận conflict hay bị mất thay đổi âm thầm?

### 29.4. Test xóa trong lúc replica offline

1. Đưa một replica khỏi cụm theo quy trình test.
2. DELETE K ở các replica còn lại.
3. Khôi phục node trước và sau những mốc retention mô phỏng phù hợp.
4. Kiểm tra tombstone, repair, data resurrection và cách bảo đảm không phục vụ bản cũ.

**Không thực hiện fault injection phá dữ liệu trên production** nếu chưa có kế hoạch được phê duyệt và phương án phục hồi.

### 29.5. Test consumer crash

~~~text
Worker nhận event v11.
Worker ghi projection.
Worker crash trước khi lưu checkpoint.
Worker restart, nhận lại v11.
~~~

Kết quả phải không tạo duplicate side effect. Nếu event là INCREMENT, cần dedup; nếu là SET versioned, cần version check.

### 29.6. Test reorder

Cho projector nhận:

~~~text
v12 DELETE
v10 UPDATE
v11 UPDATE
~~~

Không được để v10/v11 hồi sinh bản ghi đã xóa. Nếu entityId được tái sử dụng ở generation mới, test thêm event DELETE cũ từ generation trước.

### 29.7. Test restore snapshot

Khôi phục snapshot trước thời điểm DELETE, sau đó kiểm tra replay deletion ledger và rebuild search/cache. Nếu dữ liệu đã xóa xuất hiện trong production path, kế hoạch restore chưa bảo toàn quyết định xóa.

### 29.8. Test RYW và monotonic reads

Một session:

~~~text
PUT K=v2 -> ACK
GET K -> v2
GET K -> v1  (không được nếu cam kết monotonic reads)
~~~

Chạy qua load balancer, Region và failover để bảo đảm session token/routing thật sự có hiệu lực trong phạm vi đã hứa.

## 30. Những hiểu lầm phổ biến

| Hiểu lầm | Vì sao sai | Hướng đúng |
|---|---|---|
| Eventual nghĩa mọi replica giống nhau sau đúng 1 giây | Mô hình không quy định bound mặc định | Định nghĩa SLO/replication lag riêng |
| Eventual nghĩa kết quả tùy ý mãi mãi vẫn đúng | Hội tụ có điều kiện là thuộc tính cốt lõi | Xác định giả định và kiểm tra hội tụ |
| Một PUT ACK nghĩa mọi replica đã nhận | ACK theo write concern/consistency cụ thể | Đọc hợp đồng write ACK |
| Có log nghĩa consumer không bao giờ bỏ lỡ event | Log có retention và worker có thể ngắt lâu | Snapshot/backfill/reconciliation |
| Quorum W+R>N luôn linearizable | Thiếu giả định về tập replica, conflict resolution, topology | Xem consistency level và giao thức thật |
| Strong read trước INSERT ngăn hai writer cùng tạo | Hai strong read có thể đều thấy absent | Atomic conditional create/unique constraint |
| LWW nghĩa ghi thực hiện sau cùng thắng | Timestamp có thể lệch và rule khác | Hiểu clock, ordering và tiebreaker |
| Các bản sao bằng nhau nghĩa không mất update | LWW có thể bỏ một mutation concurrent | CAS, transaction hoặc merge đúng |
| Version vector tự giải quyết xung đột | Chỉ nhận diện quan hệ nhân quả/concurrent | Cần policy merge/resolve |
| CRDT bảo đảm mọi invariant | Hội tụ không tự giữ số dư không âm | Bảo vệ invariant riêng |
| Read repair đồng bộ mọi key | Chỉ ảnh hưởng đường đọc được repair | Có anti-entropy/repair đầy đủ |
| Hinted handoff thay repair mãi mãi | Hint có giới hạn retention | Lịch repair/rebuild |
| Xóa tombstone nhanh là tiết kiệm vô hại | Replica cũ có thể làm dữ liệu hồi sinh | GC/repair/grace an toàn |
| TTL hết hạn là đã purge mọi nơi | Cleanup/storage/backup có lịch riêng | Phân biệt expiry và purge |
| Client RYW tự có trong eventual | Read có thể route sang replica cũ | Version token/leader/session |
| Transaction nguồn làm GSI/search cập nhật nguyên tử | Projection eventual có pipeline riêng | Watermark/fallback nguồn |
| Consumer lag=0 nghĩa search visible | Refresh còn có thể trễ | Đo end-to-end visibility |
| Cùng version number nghĩa luôn cùng trạng thái | Version có thể không unique toàn hệ | Định nghĩa nguồn version/generation |
| Replica online lại chắc chắn tự sửa | Có thể thiếu log hoặc tombstone | Repair/rebuild theo engine |
| Eventual thì hệ luôn available | Vẫn có quorum, disk, overload, failover | Đánh giá availability riêng |
| Một node đọc đúng chứng minh tất cả đã hội tụ | Những node khác có thể stale | Probe/metric/reconciliation theo phạm vi |
| Replica hội tụ là business invariant đúng | Có thể hội tụ về trạng thái oversell | Dùng transaction/CAS cho invariant |

## 31. Bài tập thực hành

### Bài 1. Mô tả eventual consistency

Một bản ghi K có:

~~~text
T0: A=B=C=v1.
T1: A nhận v2.
T2: A=v2, B=v1, C=v1.
T3: B=v2, C=v1.
T4: A=B=C=v2.
~~~

1. Khoảng nào thể hiện stale reads?
2. Tại T2, một GET trả v1 có luôn sai hợp đồng eventual không?
3. T4 chứng minh điều gì?
4. Nếu C mất kết nối vĩnh viễn và không bị thay thế, có thể tuyên bố mọi replica đã hội tụ không?
5. Điều gì thay đổi nếu writer vẫn liên tục tạo v3, v4, v5?

### Bài 2. Các điều kiện hội tụ

Liệt kê tối thiểu năm điều kiện cần thiết để replica cuối cùng hội tụ về trạng thái đúng.

**Gợi ý:** Xem durability, network, replica health, retry/repair, conflict resolution và tombstone.

### Bài 3. LWW với clock skew

~~~text
Thời gian thực:
  A update name="An" lúc 10:00:01.
  B update name="Anna" lúc 10:00:02.

Timestamp:
  A=10:00:05 vì clock nhanh.
  B=10:00:02.
~~~

1. Nếu chọn timestamp lớn nhất, giá trị cuối là gì?
2. Vì sao không tương đương “người sửa cuối”?
3. Nếu tên là thông tin không được phép mất cập nhật, nên dùng cơ chế nào?
4. Nếu hai timestamp bằng nhau, hệ cần điều kiện gì để mọi replica chọn cùng kết quả?

### Bài 4. Version vector

Cho:

~~~text
V1 = {A:3, B:1}
V2 = {A:2, B:2}
V3 = {A:3, B:2}
~~~

1. V1 và V2 có quan hệ dominates hay concurrent?
2. V3 so với V1 và V2 thế nào?
3. Nếu V1 và V2 chứa hai giá trị profile khác nhau, version vector tự chọn được winner chưa?
4. Nêu một policy merge hoặc conflict workflow hợp lý.

### Bài 5. Quorum

Hệ giả định N=5, W=3, R=3.

1. W+R>N không?
2. Các tập read và write tối thiểu giao nhau bao nhiêu replica trong mô hình cùng N?
3. Vì sao công thức không đủ để chứng minh serializable transaction hoặc linearizable read trong mọi tình huống?
4. Nếu Region chỉ dùng local quorum nhưng ghi đồng thời ở hai Region, cần xét vấn đề gì?

### Bài 6. DELETE và zombie data

~~~text
A/B nhận tombstone K version 9.
C offline và giữ K version 8.
Tombstone ở A/B bị purge trước khi C repair.
C trở lại sau nhiều ngày.
~~~

1. K có thể hồi sinh như thế nào?
2. Vai trò của gc_grace_seconds và anti-entropy repair?
3. Vì sao hinted handoff không bảo vệ mọi trường hợp?
4. Nếu ứng dụng có search index và event UPDATE cũ, phải có cơ chế gì ở projector?

### Bài 7. Read-your-writes

Người dùng đổi avatar rồi GET profile qua load balancer. Request PUT được ACK, nhưng GET được route sang follower còn cũ.

1. Eventual consistency thuần túy có vi phạm không?
2. UX của người dùng sẽ thế nào?
3. Đề xuất ít nhất ba biện pháp tăng RYW.
4. Nếu tất cả biện pháp tạm thời không đáp ứng mức mới, API nên làm gì thay vì âm thầm trả stale nhưng tuyên bố RYW?

### Bài 8. Eventual GSI của DynamoDB

Ứng dụng ghi item với email vào bảng chính, sau đó Query GSI email để quyết định email có bị trùng không.

1. Vì sao GSI chưa thấy item không chứng minh email chưa tồn tại?
2. Thiết kế một claim item có primary key là tenant+email.
3. Nêu conditional write cần dùng.
4. Khi tạo claim và user profile phải cùng thành công, có thể dùng API transaction nào?
5. Nếu hai Region eventual cùng ghi, có cần thêm điều kiện gì để bảo đảm global uniqueness?

### Bài 9. Search projection sai thứ tự

Source có:

~~~text
v11: Product updated.
v12: Product deleted.
~~~

Search worker nhận v12 trước rồi v11 sau.

1. Điều gì xảy ra nếu blindly upsert v11?
2. Thiết kế tombstone và version check.
3. So sánh consumer lag và search visibility lag.
4. Khi rebuild index từ snapshot trước v12, cần những bước nào để không hồi sinh product?

### Bài 10. Phân biệt dữ liệu có thể trễ và invariant cần mạnh

Một ứng dụng có:

- Lượt xem bài viết.
- Tổng doanh thu dashboard.
- Giá sản phẩm hiển thị trong search.
- Giá cuối ở checkout.
- Đặt ghế cuối cùng.
- Thu hồi quyền đăng nhập.

Hãy chọn consistency strategy cho từng trường hợp. Nêu dữ liệu nào được phép eventual, dữ liệu nào phải kiểm tra nguồn/conditional write hoặc dùng transaction, và vì sao.

### Bài 11. CRDT counter

Một G-counter hai replica có:

~~~text
A = {A:5, B:0}
B = {A:0, B:7}
~~~

1. Merge bằng max từng thành phần ra vector nào?
2. Tổng sau merge là bao nhiêu?
3. Nếu A nhận lại trạng thái từ B thêm lần nữa, giá trị có tăng sai không?
4. Vì sao G-counter không tự giải quyết bài toán số lượng tồn kho không được âm?

### Bài 12. Repair backlog

Một hệ xử lý mutation mới nhanh hơn tốc độ đồng bộ của một follower trong nhiều giờ.

1. Eventual consistency có tự cho biết thời gian follower sẽ bắt kịp không?
2. Metric nào cần đo?
3. Nếu changelog hết retention khi follower chưa bắt kịp, phải làm gì?
4. Nếu cần SLO “99% visible trong 5 giây”, cách đo end-to-end nên gồm những thành phần nào?

### Bài 13. Kiểm thử fault injection

Thiết kế một kế hoạch test:

~~~text
3 replica, 2 writer, 1 read model search.
Một replica offline trong lúc WRITE và DELETE.
Hai writer update cùng key.
Search worker restart và replay event.
~~~

Yêu cầu nêu:

- Điều kiện khi nào được đưa replica trở lại.
- Cách phân biệt update mới và cũ.
- Cách chống DELETE hồi sinh.
- Cách quan sát hội tụ.
- Kỳ vọng RYW và đọc từ replica.
- Hành vi khi log không còn đủ để replay.
- Những invariant nghiệp vụ nào không được chỉ dựa vào eventual consistency.

## 32. Tổng kết

**Eventual consistency** không có nghĩa “dữ liệu cũ luôn chấp nhận được” hoặc “database sẽ tự sửa một cách thần kỳ”. Nó phát biểu rằng **khi không còn cập nhật mới và những điều kiện cần thiết được duy trì, các bản sao cuối cùng có thể hội tụ về cùng trạng thái theo quy tắc của hệ**.

Muốn kết luận điều đó một cách đáng tin cậy, cần:

1. **Bảo vệ mutation đã ACK:** Có durability/replication contract phù hợp, không làm mất thay đổi trước khi đồng bộ.
2. **Truyền hoặc phục hồi đủ thay đổi:** Network được nối lại, replica hoạt động, retry/handoff/anti-entropy hoặc rebuild khi log bị thiếu.
3. **Giải quyết ghi đồng thời một cách xác định:** LWW/sequence, vector clock với conflict policy, CRDT hoặc serialization tại nguồn.
4. **Giữ đúng dữ liệu xóa và phiên bản:** Tombstone, TTL, generation và repair phải ngăn dữ liệu cũ hồi sinh.
5. **Không hiểu nhầm hội tụ là isolation/invariant:** Các bản sao có thể giống nhau nhưng vẫn mất update, oversell hoặc có trạng thái giao dịch không hợp lệ.
6. **Chọn bảo đảm theo tính năng:** Eventual cho search/dashboard khi chấp nhận trễ; read-your-writes cho tương tác vừa cập nhật; conditional write/transaction cho uniqueness, tồn kho, thanh toán và quyền.
7. **Đo độ trễ và đối soát theo phạm vi:** Replication lag, visibility lag, conflict count, repair backlog, RYW violation, deletion drift và watermark của những projection liên quan.

Câu hỏi cần đặt khi thiết kế không chỉ là **“Hệ này có eventual consistency không?”**, mà là:

> **“Nếu mọi writer dừng ngay bây giờ, liệu mọi bản sao còn tham gia có đủ thông tin, đủ cơ chế truyền và một luật giải quyết xung đột nhất quán để cuối cùng đạt cùng trạng thái đúng không — và trong khi chưa hội tụ, những thao tác nghiệp vụ nào vẫn phải được bảo vệ?”**
