# Lease, đồng hồ và các giả định về thời gian

Trong cơ sở dữ liệu NoSQL phân tán, một phần dữ liệu có thể tồn tại trên nhiều replica, nhưng **không phải mọi replica đều có quyền quyết định một write**. Một hệ thống cần cơ chế xác định **ai có thẩm quyền ghi**, nhất là khi leader mất liên lạc, mạng bị chia cắt hoặc node từng tạm ngừng rồi hoạt động trở lại.

**Lease** là một hình thức cấp quyền **có giới hạn thời gian**. Ví dụ, coordinator cấp quyền xử lý một nhóm khóa cho Node A trong 30 giây. Nhưng nếu Node A bị GC pause 45 giây, Node B nhận quyền mới và sau đó A chạy lại, điều gì ngăn A tiếp tục ghi bằng quyền đã cũ?

Câu hỏi ấy đòi hỏi hiểu đồng thời:

- **Thời hạn lease:** ai cấp, ai đo và ai xác nhận quyền còn hiệu lực?
- **Đồng hồ:** wall clock, monotonic clock, logical clock; clock skew, drift, uncertainty.
- **Giao thức quyền ghi:** quorum, term, epoch, fencing, renewal, failover.
- **Giả định về thời gian:** độ trễ mạng có giới hạn hay không, process có thể bị tạm dừng bao lâu, clock rate sai lệch tới mức nào.
- **Tác động nghiệp vụ:** write có thể đến muộn sau expiry, timeout sau commit, retry tạo tác động lặp.

Chủ đề thuộc chương **Đồng thuận và quyền ghi** của module **Database No SQL**. Mục tiêu của bài là giải thích bằng lịch sử sự kiện, mô hình toán học đơn giản, ví dụ Java và các tình huống vận hành để phân biệt **safety của dữ liệu** với **liveness của hệ thống**.

> **Nguyên tắc cốt lõi:** “Node A còn lease theo đồng hồ của A” **không tự chứng minh** A vẫn có quyền ghi. Lease chỉ an toàn trong phạm vi **giao thức cấp quyền, điều kiện thời gian đã được chứng minh, và cơ chế từ chối thao tác lỗi thời tại nơi thực sự commit**.

## 1. Lease là gì?

Một **lease** là lời cấp quyền hoặc cam kết có thời hạn. Trong một ví dụ giả lập:

~~~text
Resource:    order-partition-17
Grantor:     coordination quorum
Holder:      Node A
Permission:  authoritative write
Lease ID:    lease-801
Epoch:       105
Duration:    30 seconds
~~~

Holder được phép thực hiện một nhóm thao tác **nếu các điều kiện của lease protocol còn đúng**. Khi lease hết hạn hoặc quyền bị chuyển một cách an toàn, holder cũ phải ngừng các thao tác yêu cầu thẩm quyền ấy.

### Các trường phải làm rõ

| Thành phần | Câu hỏi |
| --- | --- |
| Resource scope | Quyền áp dụng cho một key, partition, shard, tenant hay job? |
| Grant authority | Một node hay một quorum được phép cấp quyền? |
| Holder | Node nào hoặc process nào thực sự giữ quyền? |
| Lease duration | Bắt đầu tính từ sự kiện nào? |
| Clock | Clock nào đo elapsed hoặc absolute expiry? |
| Term/epoch | Cách nhận biết thế hệ quyền cũ/mới? |
| Renewal | Gia hạn được commit thế nào? |
| Revocation | Có thu hồi trước expiry được không? |
| Fencing | Nơi nào bác stale writes? |

Lease khác một khóa vĩnh viễn ở chỗ quyền **có thể tự hết hiệu lực theo thời gian được protocol công nhận**. Nó giúp phục hồi khi holder mất liên lạc, nhưng đồng hồ và lease-grant state phải được quản lý đúng.

## 2. Lease không đồng nghĩa TTL hay transaction

Một số khái niệm thường bị nhầm:

| Khái niệm | Ý nghĩa | Có bảo đảm single-writer không? |
| --- | --- | --- |
| **Leader lease** | Quyền leadership được grant trong thời hạn | Chỉ nếu protocol chứng minh đúng |
| **Distributed lock có TTL** | Một holder giữ khóa có hạn | Chưa đủ nếu thiếu fencing/side-effect guards |
| **Cache TTL** | Dữ liệu cache có thể được coi hết hạn | Không |
| **Document expiration** | Document hết hạn theo cơ chế storage | Không |
| **Session expiration** | Phiên xác thực không còn hợp lệ | Không mặc định |
| **Election term/epoch** | Thế hệ leadership có thứ tự | Có thể không dựa thời gian |
| **Transaction timeout** | Giới hạn thời gian chờ/xử lý | Không tự quyết định quyền ghi |

Ví dụ một app dùng lock TTL trong Redis:

~~~text
SET lock:job:42 worker-A NX PX 30000
~~~

Trong một mô hình deployment phù hợp, lệnh có thể giúp worker A nhận lock 30 giây. Nhưng **Redis key hết TTL không tự ngăn Java process A thực hiện một HTTP POST tới payment provider sau 30 giây**.

Quyền ở tầng application và quyền được chấp nhận tại **điểm gây tác động** là hai vấn đề.

## 3. Safety và liveness trong quyền ghi

Hệ phân tán có hai loại bảo đảm:

- **Safety:** trạng thái xấu bị cấm không bao giờ được commit, ví dụ hai request không được cùng sở hữu ghế A12.
- **Liveness:** hệ có thể tiếp tục tiến lên, ví dụ cuối cùng bầu được leader mới sau lỗi phù hợp.

Giả sử Node A không phản hồi:

~~~text
Node A: leader hiện tại
Node B: follower

B không nhận heartbeat từ A trong 5s.
~~~

B không thể kết luận chắc A đã chết. A có thể chỉ bị partition, GC pause, I/O stall hoặc packet bị mất. Nếu B tự cấp quyền rồi ghi trong khi A vẫn nhận write, safety có thể hỏng.

Ngược lại, nếu luôn chờ A trả lời trong mọi trường hợp, cluster có thể ngừng tiến triển. **Giao thức đồng thuận** cân bằng các yêu cầu này bằng điều kiện quorum/term; lease chỉ là một công cụ bổ sung trong một số thiết kế.

## 4. Timeout không phải bằng chứng node đã chết

Một request RPC không phản hồi sau 3 giây có thể do:

1. Node đích crash trước khi nhận request.
2. Node nhận, xử lý và commit nhưng ACK mất.
3. Request bị mất trên đường gửi.
4. Response bị mất trên đường về.
5. Node bị pause hoặc overload.
6. Đường mạng bị chia cắt một hoặc hai chiều.

Trong mô hình **asynchronous**, không có giới hạn thời gian xử lý/truyền thông điệp được bảo đảm. Một node rất chậm có thể không phân biệt được với node đã chết chỉ bằng một timeout hữu hạn.

### Timeout giúp gì?

Timeout hữu ích cho:

- Khởi động election/retry.
- Trả lỗi có giới hạn thời gian cho client.
- Phát hiện bất thường vận hành.
- Thay đổi route khi một endpoint có vẻ không khỏe.

Nhưng **không đủ để cấp quyền ghi xung đột** nếu quyền cũ chưa được vô hiệu hóa theo protocol.

## 5. Wall clock: đồng hồ thời gian lịch

Wall clock trả timestamp như:

~~~text
2026-11-14T09:30:00.000Z
~~~

Thường dùng cho audit, ngày thanh toán, hạn hợp đồng hoặc thời điểm UTC của sự kiện. Trong Java, `System.currentTimeMillis()` trả thời gian lịch theo epoch.

Nhưng wall clock có thể:

- Được điều chỉnh tiến/lùi do đồng bộ thời gian.
- Bị ảnh hưởng bởi cấu hình/ảo hóa.
- Không tiến đều theo thời gian thực.
- Bị biểu diễn mơ hồ nếu dùng giờ địa phương không có timezone/offset trong những khu vực đổi DST.

### Lỗi khi đo lease duration bằng wall time

~~~java
long expiresAt =
        System.currentTimeMillis() + 30_000L;

if (System.currentTimeMillis() < expiresAt) {
    performWrite();
}
~~~

Nếu wall clock bị **chỉnh lùi 60 giây**, phép so có thể cho rằng lease vẫn còn hạn dù đã trôi hơn 30 giây thực. Nếu clock bị chỉnh tiến, lease có thể bị đánh dấu hết sớm.

**Đo thời gian trôi qua cục bộ bằng wall clock có thể chịu bước nhảy không mong muốn.**

## 6. Monotonic clock: đồng hồ đo elapsed time

Một monotonic time source được thiết kế để các lần đọc trong phạm vi hỗ trợ **không đi lùi vì điều chỉnh thời gian lịch**, phù hợp đo duration và deadline cục bộ.

Java thường dùng:

~~~java
long startNanos = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - startNanos;
~~~

`System.nanoTime()` không phải UTC timestamp; giá trị của nó có một gốc tùy ý. Chỉ dùng để tính chênh lệch trong **cùng phạm vi thời gian của JVM**, không so trực tiếp nanoTime của hai máy.

### Hai điều monotonic không tự bảo đảm

1. Đồng hồ A/B chạy **cùng tốc độ thực**.
2. Đồng hồ có semantics giống nhau khi OS/VM suspend, host migration hoặc process restart.

**Monotonic clock giúp tránh một lớp lỗi elapsed time, không tự tạo distributed lease an toàn.**

## 7. Logical clock khác đồng hồ vật lý

Các loại logical time thường gặp:

- **Lamport clock:** counter giúp phản ánh quan hệ xảy ra-trước theo quy tắc.
- **Vector clock:** hỗ trợ phân biệt một số mối quan hệ nhân quả/concurrent.
- **Hybrid Logical Clock (HLC):** kết hợp thành phần physical time và logical ordering trong mô hình cụ thể.

Ví dụ:

~~~text
Event A: logical timestamp 100
Event B: logical timestamp 101
~~~

Không có nghĩa hai event cách nhau đúng 1 mili giây thực.

Một HLC có thể được biểu diễn:

~~~text
(physical_millis, logical_counter)
~~~

Nhưng logical counter tăng **không tự chứng minh lease 30 giây đã trôi qua**. Không dùng version/timestamp logic thay cho một cơ chế expiry đã được phân tích clock uncertainty.

## 8. Offset, skew, drift và uncertainty

**Clock offset:** chênh lệch giữa clock và một tham chiếu thời gian ở một thời điểm.

~~~text
Reference: 12:00:00.000
Clock A:   12:00:00.100
Offset A: +100 ms
~~~

**Clock skew:** chênh lệch hai clock, ví dụ A nhanh hơn B 150 ms.

**Clock drift / rate error:** tốc độ clock chạy hơi nhanh hoặc chậm so với thời gian thực.

**Clock uncertainty:** khoảng sai số mà hệ có cơ sở tin là còn phù hợp, ví dụ thời gian thực nằm trong một đoạn `[earliest,latest]`.

| Thuật ngữ | Câu hỏi |
| --- | --- |
| Offset | Clock hiện lệch mốc chuẩn bao nhiêu? |
| Skew | Clock A khác Clock B bao nhiêu? |
| Drift | Clock sai tốc độ bao nhiêu qua thời gian? |
| Uncertainty | Khoảng sai số nào được bảo đảm/ước lượng? |

**Skew nhỏ tại thời điểm t không đảm bảo skew nhỏ mãi.** Nếu clock rates khác nhau, sai lệch có thể tích lũy khi mất nguồn đồng bộ.

## 9. Tính drift bằng ppm

Nếu clock có sai lệch tốc độ tối đa 100 ppm:

\[
100\,\mathrm{ppm}=100\times10^{-6}=0.0001
\]

Trong 3.600 giây thực, sai lệch elapsed tối đa **một chiều** theo giả định đó là:

\[
3600\times0.0001=0.36\ \mathrm{giây}
\]

Hai clock ở hai cực đối nghịch có thể chênh lệch tích lũy lớn hơn một clock so với real time.

**Số 100 ppm chỉ là giả định minh họa**, không phải bound mặc định được Java, NTP hoặc mọi VM bảo đảm. Khi dùng bound để chứng minh một lease, phải nêu:

- Nguồn cung cấp bound.
- Phạm vi hardware/OS/time source.
- Cách giám sát bound bị vi phạm.
- Hành vi fail-closed khi không còn tin được bound.

## 10. Vì sao hai monotonic clocks vẫn có thể làm lease overlap?

Giả sử coordinator và holder cùng tự đếm 30 giây theo clock monotonic, nhưng:

~~~text
Grantor clock: nhanh hơn real time một chút.
Holder clock:  chậm hơn real time một chút.
~~~

Grantor đạt 30 đơn vị local **sớm hơn** holder. Nếu grantor lúc đó cấp quyền mới cho B, còn A vẫn tin lease cũ chưa hết, hai quyền có thể chồng lấn:

~~~text
Real time ─────────────────────────────────────────>

Grantor:  [--- lease A ---] [--- lease B ---]
Holder A: [--------- thinks lease A valid --------]
~~~

Lỗi này **không yêu cầu clock đi lùi**. Chỉ cần clock rates khác nhau và không có biên an toàn.

### Kết luận

Một lease protocol nghiêm túc phải quy định điều kiện về **drift**, mốc bắt đầu tính thời hạn, grant/renewal, quorum và fencing. Không thể chỉ nói “dùng monotonic là xong”.

## 11. Mô hình thời gian: synchronous, asynchronous, partially synchronous

### Synchronous model

Có giới hạn đã biết và được bảo đảm đối với độ trễ thông điệp/xử lý. Những bound đó cho phép lập luận về deadline, nhưng hiếm khi mô tả chính xác mọi lỗi thực tế của một cloud cluster.

### Asynchronous model

Không giả định giới hạn hữu hạn đã biết cho message delay hoặc process speed. Timeout không phân biệt chắc node crash và node chậm.

Kết quả FLP nhắc tới giới hạn bảo đảm tiến triển của consensus xác định trong môi trường bất đồng bộ có khả năng một process crash. **Nó không nói hệ thực tế không thể dùng consensus**; thực tế thêm những điều kiện liveness, failure detector hoặc partial synchrony.

### Partial synchrony

Hệ có thể trải qua giai đoạn rất chậm, nhưng sau một thời điểm trở nên đủ ổn định để các node liên lạc/tiến triển theo giao thức.

**Safety** của consensus thường được thiết kế không phụ thuộc “network phải dưới 50 ms”. **Liveness** có thể cần đủ thời gian kết nối ổn định, quorums reachable và timers phù hợp.

## 12. Leader election, term và lease không phải một

~~~text
Election:
  Node nào được bầu làm leader?

Term / epoch:
  Nhiệm kỳ/phiên bản quyền điều phối nào đang hợp lệ?

Lease:
  Quyền có thời hạn được grant theo protocol nào?
~~~

Một thuật toán consensus có thể dùng election terms và quorum để giữ log/commit safety **mà không cần dựa vào đồng hồ vật lý chính xác**. Một implementation khác có thể thêm **leader lease cho fast read** hoặc một tối ưu được chứng minh dưới clock assumptions.

### Ví dụ

~~~text
T0: A leader, term=7.
T1: A bị cô lập khỏi majority.
T2: B/C bầu leader B, term=8.
T3: A khôi phục mạng và nhận một write cũ.
~~~

Nếu A tiếp tục áp dụng write không kiểm term/quyền, hệ có nguy cơ sai. Phải có cơ chế kiểm quyền tại commit path, không chỉ dựa heartbeat local.

## 13. Split-brain và quyền ghi lỗi thời

Một lịch đơn giản:

~~~text
T=0s:  A nhận lease 30s.
T=10s: A bị GC pause.
T=20s: B được cấp lease mới vì "A không phản hồi".
T=25s: B thực hiện write.
T=45s: A thức dậy và thực hiện write.
~~~

Nếu B được cấp quyền **trước khi grant của A chắc chắn hết hiệu lực** và hệ không có fencing, cả hai có thể có tác động xung đột.

### Điều nguy hiểm của “không nhận heartbeat”

Heartbeat mất không nhất thiết nghĩa:

- A đã ngừng chạy.
- A đã hoàn tất các write đang bay trên mạng.
- A đã nhận thông báo thu hồi.
- A sẽ không chạy tiếp sau pause.

**Lease expiration và leader replacement phải được phối hợp bởi protocol bảo đảm không có hai quyền xung đột hợp lệ.**

## 14. Thời hạn tuyệt đối giữa hai host cần clock contract

Giả sử grantor trả:

~~~json
{
  "resource": "partition-17",
  "expiresAtMillis": 1900000030000,
  "epoch": 42
}
~~~

Holder nhận và so `expiresAtMillis` với đồng hồ của mình. Nếu holder chậm hơn grantor 5 giây, nó có thể nghĩ lease còn hạn quá lâu.

Không nên so absolute expiry giữa các host nếu:

- Clock offset chưa được giới hạn.
- Không có uncertainty/safety margin.
- Thời điểm grant/commit không được định nghĩa.

**Thời gian lịch có thể đồng bộ hữu ích cho audit và nhiều expiry contracts, nhưng không tự cung cấp sự tương đương hoàn hảo giữa các máy.**

## 15. Mô hình tính duration bảo thủ có drift bound

Xét một mô hình **giáo dục** với các giả định rất cụ thể:

1. Clock holder và grantor đều monotonic và có tốc độ trong `[1-\rho,1+\rho]` so với real time.
2. Holder bắt đầu đếm **trước hoặc đúng lúc gửi** yêu cầu grant.
3. Grantor bắt đầu đếm thời hạn **không sớm hơn lúc nhận request**.
4. Grantor giữ grant tối thiểu `D` đơn vị **clock grantor** và không cấp grant xung đột trước khi nó hết hạn.
5. Holder chỉ hoạt động khi nhận được grant hợp lệ.
6. State grant/epoch không bị mất do reboot, và không có grantor khác phá quyền.

Khi đó holder có thể tự ngừng sớm ở ngưỡng elapsed local:

\[
H=D\frac{1-\rho}{1+\rho}
\]

Lý do:

- Nếu holder chạy chậm nhất `1-\rho`, đạt `H` không muộn hơn `H/(1-\rho)=D/(1+\rho)` giây thực kể từ khi bắt đầu.
- Nếu grantor chạy nhanh nhất `1+\rho`, grantor không thể đạt `D` trước `D/(1+\rho)` giây thực kể từ grant.
- Holder bắt đầu đếm trước khi grantor bắt đầu, nên holder tự ngừng **không muộn hơn** thời điểm sớm nhất grantor có thể hết hạn.

Với `D=30` và `\rho=0.0001`:

\[
H=30\frac{0.9999}{1.0001}
\approx29.9940006\ \mathrm{giây}
\]

### Giới hạn quan trọng

Đây **không phải distributed lock algorithm hoàn chỉnh**. Nó chưa chứng minh:

- Nhiều grantors/quorum cấp lease đúng.
- Grant/renewal response tới muộn.
- Process/VM suspend làm clock không theo drift bound.
- Grantor reboot mất state.
- Holder gửi write trước expiry nhưng packet đến sau expiry.
- Side effect ngoài database chấp nhận stale holder.

Không triển khai production chỉ bằng công thức H và hai timer. Bài toán lease thực còn cần **đồng thuận, cấp quyền có thứ tự và fencing**.

## 16. Một write gửi trước expiry vẫn có thể commit sau

~~~text
T0: A còn lease, gửi write W.
T1: Network delay giữ packet W.
T2: Lease A hết.
T3: B nhận quyền mới.
T4: Write W của A đến resource.
~~~

Kiểm tra `leaseValid()` trước khi A gọi gửi request **không đủ**. Packet đã rời A có thể được nhận và xử lý lâu sau khi quyền của A hết.

**Thời điểm gửi và thời điểm commit là hai thời điểm khác nhau.** Resource hoặc commit authority phải kiểm tra quyền hợp lệ theo protocol khi áp dụng side effect.

## 17. Fencing token: dấu thế hệ quyền ghi

**Fencing token** là một số/giá trị phiên bản có thứ tự tăng theo những lần cấp quyền hợp lệ.

~~~text
Owner A: epoch=41
Owner B: epoch=42

Resource đã cài current epoch=42:
  write(epoch=41) → REJECT
  write(epoch=42) → ACCEPT nếu điều kiện dữ liệu hợp lệ
~~~

Token cần được tạo bởi **nguồn có thẩm quyền đáng tin**, không phải:

~~~java
long fencingToken = System.currentTimeMillis();
~~~

Clock lệch, step lùi hoặc hai lệnh cùng timestamp có thể khiến thứ tự sai. Một coordinator/consensus-backed revision hoặc generation được commit theo protocol phù hợp là hướng phổ biến hơn.

### Fencing phải có tác dụng ở nơi write thực sự xảy ra

Một service có thể log `epoch=42` nhưng nếu kho dữ liệu đích không hề kiểm epoch, stale holder vẫn có thể ghi.

Tương tự, leader fence của DB không tự fence:

- Payment gateway.
- Email/notification provider.
- Object storage.
- Thiết bị hoặc hệ thống bên ngoài.

Cần **conditional write, idempotency, transaction/outbox hoặc cơ chế bảo vệ side effect riêng** tương ứng.

## 18. Một bẫy tinh tế: chỉ nhớ token lớn nhất từng thấy chưa luôn đủ

Xét:

~~~text
T0: Coordinator cấp epoch 42 cho B.
T1: Resource X chưa biết epoch 42.
T2: Write cũ epoch 41 của A tới X.
T3: X chỉ biết maxSeen=41, chấp nhận write.
T4: Write của B epoch 42 mới tới X.
~~~

Nếu yêu cầu **không có write nào từ A được commit sau lúc B đã nhận quyền**, một bộ lọc “giá trị lớn nhất từng thấy tại resource” **chưa đủ** khi việc cấp quyền và cài quyền ở resource không được đồng bộ đúng.

Giao thức phải định nghĩa:

1. Điểm nào đánh dấu epoch 42 đã có hiệu lực với resource?
2. Resource kiểm tra current authority thế nào?
3. B chỉ được ghi sau khi fencing của 42 thực sự có hiệu lực hay không?
4. Có transaction/consensus boundary bảo vệ chuyển quyền và write không?

**Fencing token chỉ hữu ích trong một giao thức có thứ tự cấp, cài và thực thi quyền rõ ràng.**

## 19. Quorum lease cần tập cấp quyền giao nhau

Một cluster có 5 grantors:

~~~text
N1 N2 N3 N4 N5
Quorum majority = 3
~~~

Hai tập ba grantors luôn có ít nhất một phần tử chung:

~~~text
Q_A = {N1,N2,N3}
Q_B = {N3,N4,N5}
Intersection = {N3}
~~~

Nếu mỗi grantor không cấp **hai leases xung đột còn hiệu lực** và các quy tắc expiry/recovery đúng, thành viên giao nhau có thể giúp ngăn hai holder cùng sở hữu quyền qua hai quorums.

### Điều kiện “có majority ACK” vẫn chưa đủ

Cần nêu:

- ACK xác nhận **grant gì**, trong term nào?
- Grantor dùng clock nào và expiry được tính thế nào?
- Grant state có bền qua crash không?
- Request renewal bị lặp/đảo thứ tự được xử lý sao?
- Khi membership đổi, quorum giao nhau còn đúng không?
- Holder hành động sau khi có đủ grants thật hay chỉ sau khi gửi?

Quorum intersection là **một phần của chứng minh**, không phải toàn bộ protocol.

## 20. Leader lease và consensus không đồng nhất

Một consensus algorithm có thể dùng term, log matching, leader election và majority commit để bảo vệ safety. Đồng hồ/timeout giúp **khởi động bầu cử và phục hồi tiến triển**, không nhất thiết tạo safety của log.

Một số implementation có thể dùng **leader lease** cho:

- Tối ưu local strong read khi còn quyền.
- Giảm round trips đến quorum trên read path.
- Hạn chế election churn trong điều kiện bình thường.

Khi thêm lease optimization, phải chứng minh **clock assumptions và failover conditions** phù hợp. Không nên khẳng định “mọi Raft deployment cần NTP chính xác mới giữ được log safety”, hoặc “có term thì không cần fencing cho external side effects”.

### Safety và liveness

| Tính chất | Ví dụ |
| --- | --- |
| Safety | Hai leaders không được commit hai lịch sử xung đột trái protocol |
| Liveness | Khi majority reachable đủ lâu, hệ cuối cùng phục vụ được write |
| Performance | Leader read có thể tiết kiệm round trip nhờ lease hợp lệ |

Ba điều này liên quan nhưng không thể thay thế nhau.

## 21. Read lease khác write authority

Giả sử A được phép trả strong read từ local state trong khoảng **leader lease** theo protocol:

~~~text
Client → A → read(x)
~~~

Nếu A mất liên lạc majority, lease hết và B commit một giá trị mới, A không được tiếp tục trả stale value như một **linearizable read**.

### Một lịch phản ví dụ

~~~text
Initial x=0

B: write(x,1) → OK
A: read(x)    → 0  (bắt đầu sau write B hoàn thành)
~~~

Nếu read A được hứa linearizable và không có write khác, lịch này vi phạm thứ tự thời gian thực.

Đường đọc có thể:

- Dùng read-index/quorum theo protocol.
- Chỉ trả local strong read khi lease còn được chứng minh hợp lệ.
- Đợi replica bắt kịp.
- Trả stale read **theo contract khác** nếu nghiệp vụ cho phép.

**Quyền được tối ưu read không tự mở rộng thành quyền thực hiện mọi external write.**

## 22. Renewal: gửi request không đồng nghĩa đã gia hạn

Giả sử lease 30 giây, holder gửi renewal khi còn 10 giây.

~~~text
T0: Holder gửi renew.
T1: Grantor có thể nhận hoặc không.
T2: ACK có thể bị mất hoặc đến muộn.
T3: Lease cũ có thể hết.
~~~

Holder **không được tự gia hạn** chỉ vì đã gửi request.

Một chính sách thường cần:

- Gửi renew đủ sớm với biên an toàn.
- Chỉ xem lease kéo dài sau ACK/commit hợp lệ theo term/lease ID.
- Nếu không chắc renewal thành công, **ngừng authoritative work trước conservative expiry**.
- Xử lý kết quả renewal đến muộn theo state machine.

### Late renewal reply

~~~text
A: renew(term 10) sent
Lease A expires
B: granted term 11
A: delayed ACK for old term arrives
~~~

ACK cũ không được “hồi sinh” quyền A nếu quyền đã bị thay và renewal không còn hợp lệ. Cần ràng buộc epoch/grant identity và thứ tự commit.

## 23. Lease duration ảnh hưởng failover

Lease quá ngắn:

- Gia hạn thường xuyên.
- Dễ gặp renewal timeout/false-expiry khi network jitter, GC.
- Leadership churn và giảm hiệu năng.

Lease quá dài:

- Phải chờ quyền cũ hết hạn mới cấp quyền mới trong một số protocol.
- Failover có thể chậm.
- Holder treo lâu giữ quyền danh nghĩa lâu hơn.

Một khoảng như “30 giây” không phải luôn đúng. Chọn lease duration dựa trên:

- Giới hạn/giả định của clock và network.
- SLO liveness/failover.
- Thời gian GC/pause được quan sát, nhưng không lấy p99 làm bound tuyệt đối.
- Renewal overhead.
- Rủi ro nghiệp vụ nếu holder cũ ghi muộn.

**Không có TTL hữu hạn nào chống được pause dài bất kỳ nếu resource không có cơ chế kiểm quyền.**

## 24. GC pause: kiểm tra rồi bị ngắt ngay sau đó

Đoạn code:

~~~java
if (leaseValid()) {
    // Stop-the-world GC pause 45 giây tại đây.
    performExternalWrite();
}
~~~

Nếu lease chỉ 30 giây và holder bị pause 45 giây, câu lệnh `performExternalWrite()` có thể chạy khi quyền đã hết. Đây là một dạng **time-of-check/time-of-use (TOCTOU)**.

Việc thêm một lần check ngay trước write cũng chưa hoàn toàn giải quyết, vì process có thể bị pause **ngay sau lần check cuối** hoặc packet bị delay trên mạng.

### Hướng bảo vệ

- Conditional update/CAS tại storage boundary.
- Epoch/fencing ở nơi ghi.
- Dedupe/idempotency cho API ngoài.
- Revalidation sau pause bất thường.
- Đường commit có thẩm quyền bảo vệ invariant.

## 25. Suspend, restart và mất trạng thái lease

### VM suspend

Một VM có thể tạm ngủ rồi hoạt động lại. Monotonic time source của mỗi OS/hypervisor có **quy tắc khác nhau về khoảng suspend**. Không mặc định mọi clock tính giây bị suspend giống nhau.

Khi holder resume, thiết kế an toàn nên **revalidate** quyền hoặc fail-closed nếu không thể chứng minh clock assumptions vẫn đúng.

### Grantor restart

~~~text
T0: Grantor cấp A lease đến thời hạn X.
T1: Grantor crash.
T2: Grantor restart nhưng quên grant.
T3: Grantor cấp B lease xung đột.
~~~

Nếu A vẫn hoạt động, hai grants có thể overlap. Giải pháp tùy giao thức:

- Persist grant/epoch qua crash.
- Khôi phục từ consensus state.
- Đợi một khoảng phục hồi an toàn nếu không thể biết quyền cũ.

**Không được coi reboot là reset quyền đã cấp cho các node khác.**

## 26. NTP, chrony và PTP giúp gì?

- **NTP** là giao thức đồng bộ thời gian qua mạng.
- **chrony** là một phần mềm phổ biến hỗ trợ đồng bộ/giám sát đồng hồ trên hệ điều hành.
- **PTP** là giao thức có thể cung cấp đồng bộ độ chính xác cao trong môi trường mạng/hardware phù hợp.

Trong production nên giám sát:

~~~text
clock offset
frequency correction
estimated uncertainty
last successful sync
source health
clock step or slew events
~~~

### Đồng bộ không có nghĩa hai clock tuyệt đối giống nhau

NTP/chrony/PTP có thể giúp giảm lệch nhưng:

- Đồng bộ có thể mất.
- Offset không nhất thiết bằng 0.
- Clock có thể bị step hoặc rate-adjust.
- Hạ tầng ảo hóa có thể tác động time source.

Do đó, **NTP không thay thế quorum/epoch/fencing** khi mục tiêu là quyền ghi độc quyền.

## 27. DST, timezone và leap second

Đối với thời hạn theo lịch như:

~~~text
Hợp đồng hết hạn lúc 2026-12-01T00:00:00+07:00
~~~

phải ghi timezone/offset rõ ràng. Một timestamp local không có timezone có thể mơ hồ ở những vùng chuyển giờ DST.

Với elapsed lease duration, timezone và DST **không nên quyết định thời lượng**. Cũng cần hiểu leap seconds, leap smear và wall-clock adjustment có thể khiến các host biểu diễn thời gian vật lý khác nhau.

### Phân biệt

- **Business expiry:** mốc UTC/lịch rõ ràng, có thể phụ thuộc clock accuracy.
- **Local RPC timeout:** elapsed monotonic.
- **Distributed leader lease:** elapsed/uncertainty theo giao thức cấp quyền và giới hạn drift.

Không dùng một kiểu timestamp cho cả ba vấn đề mà không nêu ngữ nghĩa.

## 28. Physical-time uncertainty và TrueTime-like API

Một số hệ biểu diễn thời gian thực theo **khoảng**:

~~~text
real time ∈ [earliest, latest]
~~~

Khi uncertainty có bound, giao thức giao dịch có thể chọn commit timestamp và **chờ qua uncertainty interval** để hỗ trợ thứ tự thời gian thực, theo thiết kế.

### TrueTime là một ví dụ về contract thời gian

Các hệ dùng cơ chế kiểu TrueTime không chỉ “đồng bộ NTP tốt hơn”: chúng còn có:

- API cung cấp uncertainty.
- Quy tắc transaction ordering.
- Điều kiện commit/visibility.
- Cơ chế xử lý khi uncertainty thay đổi.

**Không suy rằng HLC, NTP hay timestamp chính xác một mình tạo strictly serializable transactions.** Timestamp là một phần của protocol, không phải toàn bộ consistency guarantee.

## 29. Local lock TTL có đủ cho workflow không?

Một job lấy lock trong 30 giây:

~~~text
T0: A acquire lock.
T1: A gọi external API.
T2: A bị suspend 45s.
T3: TTL hết, B acquire lock.
T4: B gọi API.
T5: A resume, retry API.
~~~

Nếu API ngoài không có idempotency key/fencing, job có thể tạo hai side effects.

Ví dụ gửi hóa đơn:

- Lock chỉ giảm khả năng có nhiều worker chạy cùng lúc.
- Request ID ổn định bảo vệ ý định lặp.
- Outbox/workflow state cho phép tra hiệu ứng đã commit.
- External provider idempotency giúp tránh tạo hai hóa đơn/email/thanh toán nếu hỗ trợ.

**Single scheduler owner không tương đương exactly-once business effect.**

## 30. Epoch không thay thế conditional business invariant

Giả sử một leader có epoch mới và ghi:

~~~text
inventory.available = -3
~~~

Nếu giao thức thừa nhận nó là leader hợp lệ, write có thể hợp lệ **về quyền** nhưng vẫn phá invariant **tồn kho không âm**.

Cần phân biệt:

| Bảo vệ | Câu hỏi |
| --- | --- |
| Leader/epoch | Ai được phép đề xuất/commit write? |
| Fencing | Owner cũ có bị bác không? |
| Conditional write/CAS | State hiện tại có thỏa precondition không? |
| Transaction | Những thay đổi nhiều bản ghi có atomic/isolation phù hợp không? |
| Idempotency | Retry có tạo hiệu ứng lặp không? |
| Audit | Có giải thích được lịch sử thao tác không? |

Không viết “đã có lease nên không cần transaction”. Hai cơ chế giải quyết những rủi ro khác nhau.

## 31. Ví dụ nghiệp vụ: cập nhật giá sản phẩm

Hai workers đồng bộ bảng giá:

~~~text
A lấy lease(epoch=17) cho feed X.
A đọc snapshot giá version=100.
A bị pause.

B nhận epoch=18.
B ghi giá version=102.

A thức dậy, ghi version=100.
~~~

Nếu database cho ghi không điều kiện, giá cũ có thể ghi đè mới. Một thiết kế hợp lý:

1. Mỗi bản giá mang `sourceVersion`.
2. Write ở đích chỉ thành công nếu version mới hơn.
3. Epoch của worker được kiểm tra tại commit boundary nếu có quyền đơn chủ.
4. Retry dùng request ID ổn định.
5. Worker resume phải revalidate quyền và version.

**Quyền ghi hợp lệ và nội dung ghi đúng là hai điều cần kiểm tra riêng.**

## 32. Java: mô phỏng wall clock lùi và monotonic elapsed

Mã dưới đây dùng fake clock để tách ý nghĩa wall time và elapsed time. Đây không phải một distributed lease implementation.

Tạo file `LeaseClockDemo.java`:

~~~java
public final class LeaseClockDemo {

    static final class FakeClock {
        long wallMillis = 1_000_000L;
        long monotonicNanos = 0L;

        void elapseMillis(long millis) {
            wallMillis += millis;
            monotonicNanos += millis * 1_000_000L;
        }

        void stepWallClock(long deltaMillis) {
            wallMillis += deltaMillis;
        }
    }

    public static void main(String[] args) {
        FakeClock clock = new FakeClock();
        long ttlMillis = 30_000L;

        long wallExpiry = clock.wallMillis + ttlMillis;
        long monoStart = clock.monotonicNanos;

        clock.elapseMillis(20_000L);
        System.out.println("Elapsed 20s:");
        System.out.println("  wall active = "
                + (clock.wallMillis < wallExpiry));

        clock.stepWallClock(-60_000L);
        clock.elapseMillis(20_000L);

        long elapsedMillis =
                (clock.monotonicNanos - monoStart)
                / 1_000_000L;

        System.out.println("Elapsed 40s, wall stepped back:");
        System.out.println("  wall active = "
                + (clock.wallMillis < wallExpiry));
        System.out.println("  mono elapsed millis = "
                + elapsedMillis);
        System.out.println("  monotonic expired = "
                + (elapsedMillis >= ttlMillis));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac LeaseClockDemo.java
java LeaseClockDemo
~~~

Output dự kiến:

~~~text
Elapsed 20s:
  wall active = true
Elapsed 40s, wall stepped back:
  wall active = true
  mono elapsed millis = 40000
  monotonic expired = true
~~~

### Ý nghĩa

- Đồng hồ lịch bị lùi có thể báo một expiry giả.
- Monotonic elapsed trong mô hình vẫn ghi nhận thời lượng.
- Điều này **không chứng minh** clock A và B đồng tốc, cũng chưa chứng minh leader lease an toàn khi partition.

## 33. Java: fencing tại ranh giới ghi

Mô phỏng một resource được cài **epoch hiện hành**, chỉ nhận write có epoch khớp. Ví dụ sử dụng `synchronized` để cho thấy kiểm và cập nhật là nguyên tử **trong một JVM**.

File `FencingDemo.java`:

~~~java
public final class FencingDemo {

    static final class FencedResource {
        private long currentEpoch = 0L;
        private String value = "initial";

        synchronized void installEpoch(long epoch) {
            if (epoch <= currentEpoch) {
                throw new IllegalArgumentException(
                        "Epoch must increase");
            }
            currentEpoch = epoch;
        }

        synchronized void write(long epoch, String next) {
            if (epoch != currentEpoch) {
                throw new IllegalStateException(
                        "Stale epoch: " + epoch);
            }
            value = next;
        }

        synchronized String value() {
            return value;
        }
    }

    public static void main(String[] args) {
        FencedResource store = new FencedResource();

        store.installEpoch(41L);
        store.write(41L, "from-A");

        // Quyền thế hệ mới đã được cài ở điểm ghi.
        store.installEpoch(42L);
        store.write(42L, "from-B");

        try {
            store.write(41L, "late-from-A");
        } catch (IllegalStateException expected) {
            System.out.println(expected.getMessage());
        }

        System.out.println(store.value());
    }
}
~~~

Chạy:

~~~bash
javac FencingDemo.java
java FencingDemo
~~~

Output:

~~~text
Stale epoch: 41
from-B
~~~

### Giới hạn của ví dụ

- `installEpoch` **không được** cho bất kỳ client nào tự gọi với số lớn trong hệ thật.
- Quyền cài epoch phải đến từ coordinator/consensus có thẩm quyền.
- Thứ tự **grant epoch 42 → cài fence vào resource → cho B ghi** phải được bảo vệ. Nếu B đã được grant nhưng resource chưa cài epoch 42, write cũ của A vẫn có thể vượt qua guard theo epoch 41.
- Ví dụ không mô phỏng quorum, mạng, packet delay hoặc transaction.

Đoạn code chỉ minh họa việc **resource phải kiểm epoch lúc áp dụng write**.

## 34. Linearizable read có thể bị phá bởi leader cũ

Lịch:

~~~text
Initial x=0

Leader B: write(x,1) → OK
Old leader A: read(x) → 0
~~~

Nếu read A bắt đầu **sau** write B đã trả OK, không có write nào khác và API hứa linearizability, lịch là phản ví dụ.

Để tránh điều này, đường đọc có thể:

- Dùng read-index/quorum.
- Chỉ tối ưu local read khi leader lease hợp lệ theo assumptions.
- Chờ follower bắt kịp commit index/version.
- Hoặc khai báo rõ đó là **eventual/stale read**.

**Lease cho read cũng cần một contract về thời gian và authority**, không chỉ lease cho write.

## 35. Timeout, request deadline và lease expiry

Ba loại thời hạn:

~~~yaml
client:
  requestDeadline: "2 seconds"
server:
  rpcTimeout: "1 second per attempt"
leadership:
  nominalLeaseDuration: "30 seconds"
  epoch: 42
~~~

- **Client deadline:** người gọi ngừng chờ kết quả.
- **RPC timeout:** một lần trao đổi mạng không hoàn tất đúng hạn.
- **Lease expiry:** holder mất quyền theo giao thức.

Client hết deadline **không chứng minh write chưa commit**. RPC timeout **không tự thu hồi quyền**. Lease expiry **không đảm bảo packet đã gửi trước đó bị hủy**.

Với write quan trọng cần API tra cứu **unknown outcome** và một idempotency key cho mỗi ý định.

## 36. Giám sát đồng hồ và lease trong production

| Nhóm | Metric/log hữu ích |
| --- | --- |
| Clock | Offset, frequency correction, sync status, clock steps |
| Lease | Resource, lease ID, holder, epoch, grant/expiry |
| Renewal | Attempts, latency, rejections, late ACK, expired count |
| Leader | Term transitions, leader churn, election duration |
| Quorum | Reachability, majority status, commit index lag |
| Fencing | Stale epoch rejections, unauthorized side effects |
| Runtime | GC pause, process restart, VM suspend |
| Network | RTT, drops, partitions, retransmissions |
| API | Client timeouts, unknown commits, duplicate request IDs |

Ví dụ log sự cố:

~~~text
12:00:00 A elected term 10
12:00:04 A GC pause starts
12:00:10 B starts election term 11
12:00:11 B elected
12:00:45 A resumes
12:00:46 resource rejects write(epoch=10)
~~~

Không chỉ dựa vào UTC timestamp trong log để suy thứ tự giữa những máy có skew. Cần **term/epoch, operation IDs, commit revision** để xác định điều gì thực sự được chấp nhận.

## 37. Fault injection và invariant

Các thử nghiệm giá trị:

1. Holder wall clock step lùi 60 giây.
2. Grantor wall clock step tiến.
3. Hai monotonic clocks có rate drift trái chiều.
4. Holder GC pause dài hơn lease.
5. VM suspend rồi resume.
6. Grantor reboot làm mất hoặc khôi phục state.
7. Renewal request bị mất.
8. Renewal ACK đến sau expiry.
9. Hai nhóm mạng bị partition.
10. Old leader gửi packet, packet đến sau new epoch.
11. Hai holders cạnh tranh acquire đồng thời.
12. Client timeout sau commit rồi retry.
13. Clock synchronization bị gián đoạn.
14. New leader được bầu trong lúc old leader có in-flight writes.

Một invariant để kiểm:

~~~text
Không có hai thế hệ quyền xung đột cùng commit
những transition bị business contract cấm.
~~~

Ví dụ giữ ghế:

~~~text
Seat A12 không được có hai owners CONFIRMED khác nhau.
~~~

Một test tạo được history vi phạm là bằng chứng có bug. **Nhiều test pass không phải chứng minh toán học mọi interleaving đều an toàn.**

## 38. Ma trận sự cố

| Sự cố | Nguy cơ | Hướng bảo vệ |
| --- | --- | --- |
| Wall clock lùi | Lease local hết muộn | Monotonic elapsed và expiry protocol |
| Wall clock tiến | Expiry sớm | Clock sync monitoring, renew policy |
| Grantor clock nhanh | Grants có thể overlap | Drift bound và conservative holder expiry |
| GC pause | Owner cũ resume rồi ghi | Revalidation, fencing |
| Packet cũ đến muộn | Stale write sau handoff | Commit-boundary guard |
| Renewal ACK mất | Không rõ quyền đã gia hạn | Lease ID/epoch và fail-closed |
| Grantor restart | Quên grant chưa hết | Durable state hoặc recovery protocol |
| Network partition | Hai bên cùng tưởng có quyền | Quorum intersection/term |
| NTP unavailable | Bound không còn chắc | Alert và fail-safe theo contract |
| HLC tăng | Ngộ nhận elapsed time | Phân biệt logical ordering |
| Client timeout | Unknown commit, duplicate | Stable idempotency key |
| External API call | Side effect ngoài DB không bị fence | Provider idempotency/transactional workflow |

## 39. Mẫu đặc tả quyền ghi

Giả sử hệ đặt vé có một ghế `event42:A12`, chỉ được xác nhận cho một người.

~~~yaml
resource:
  type: "seat"
  id: "event42:A12"
invariants:
  - "At most one confirmed owner"
authority:
  type: "Consensus-backed or transactional source"
  generation: "Monotonic committed epoch"
lease:
  enabled: "Only if protocol explicitly supports"
  duration: "Based on validated time assumptions"
  localClock: "Monotonic elapsed"
  driftBound: "Specified, monitored, and enforced if required"
  renewal: "Must be committed by authority"
  onUncertainExpiry: "Stop authoritative operations"
fencing:
  location: "Authoritative write commit boundary"
  reject: "Stale or unauthorized epochs"
write:
  method: "Conditional update if seat still available"
  requestId: "Stable idempotency key"
  onTimeout: "Lookup outcome by requestId"
networkPartition:
  withoutQuorum: "Do not confirm new owner"
read:
  strong: "Use supported authoritative path"
  informational: "May use stale cache if contract permits"
tests:
  - "Concurrent claims in disconnected groups"
  - "Old holder resumes after pause"
  - "In-flight write arrives after handoff"
  - "Renewal ACK is delayed"
  - "Clock drift exceeds bound"
  - "Timeout after successful commit"
~~~

Đây là **mẫu tài liệu thiết kế**, không phải cấu hình chạy trực tiếp. Mỗi mục cần được xác nhận bằng khả năng của DBMS/coordination service và đường API cụ thể.

## 40. Bài tập thực hành

### Bài 1 — Chọn đồng hồ

Cho các tác vụ: ghi audit timestamp, đo RPC latency, sắp thứ tự sự kiện nhân quả, đo 30 giây elapsed của một worker. Hãy chọn wall, monotonic hoặc logical clock phù hợp và nêu giới hạn của từng loại.

**Gợi ý:** thời gian lịch khác duration; logical ordering không xác định số giây trôi.

### Bài 2 — Clock lùi

Một lease dựa vào wall clock bắt đầu 10:00:00, expiresAt 10:00:30. Sau 20 giây thực clock lùi 60 giây. Sau tổng 40 giây thực, check wall có thể báo gì?

**Gợi ý:** có thể báo còn hạn sai.

### Bài 3 — Monotonic vẫn có drift

Vì sao hai monotonic clocks không đi lùi vẫn có thể khiến holder và grantor thấy lease hết ở thời điểm thực khác nhau?

**Gợi ý:** clock rates có sai số.

### Bài 4 — Ppm

Với drift bound 100 ppm, tính sai lệch tối đa của một clock so với real time sau một giờ theo mô hình.

**Gợi ý:** 0,36 giây.

### Bài 5 — Ngưỡng lease bảo thủ

Cho `D=20s` và `\rho=0.001` trong mô hình phần 15. Tính `H=D(1-\rho)/(1+\rho)` và liệt kê ba assumptions thiết yếu.

**Gợi ý:** gần 19,96004 giây; clocks bounded rate và thứ tự start/grant.

### Bài 6 — Timeout

Node A không trả RPC trong năm giây. Liệt kê năm nguyên nhân ngoài crash; giải thích vì sao timeout không cho phép cấp một lease xung đột vô điều kiện.

**Gợi ý:** packet loss, partition, GC, I/O stall, scheduler pause.

### Bài 7 — GC pause

Holder A có lock TTL=30s, tạm dừng 50s; B lấy lock ở giây 35. Viết history mà A tiếp tục tạo side effect sau khi resume.

**Gợi ý:** TOCTOU.

### Bài 8 — Packet đến muộn

A gửi write khi lease còn hiệu lực, packet tới storage sau khi B nhận epoch mới. Tại sao check ở A trước khi gửi không đủ?

**Gợi ý:** commit time khác send time.

### Bài 9 — Fencing token

Một team lấy `System.currentTimeMillis()` làm fencing token. Hãy chỉ ra rủi ro step, skew và collision.

**Gợi ý:** token phải có thứ tự được quyết định bởi authority.

### Bài 10 — Majority

Với năm grantors và mỗi quorum ba node, chứng minh hai quorums bất kỳ giao nhau. Node ở giao cần cam kết gì về grants?

**Gợi ý:** không cấp leases xung đột còn hiệu lực.

### Bài 11 — Grantor restart

Grantor đã cấp A một lease, sau đó reboot và quên state. Grantor cấp B lease mới. Điều gì có thể sai? Nêu hai hướng phục hồi.

**Gợi ý:** persistent grant/epoch state hoặc waiting/recovery protocol được chứng minh.

### Bài 12 — Renewal response muộn

ACK gia hạn term 10 đến sau khi term 11 đã được cấp cho B. A có được dùng ACK để tự phục sinh quyền không?

**Gợi ý:** không; state machine phải bác grant/response lỗi thời.

### Bài 13 — Read leader cũ

B write x=1 ACK, sau đó A trả strong read x=0. Vì sao lịch này có thể vi phạm linearizability?

**Gợi ý:** thứ tự thời gian thực.

### Bài 14 — NTP và TrueTime

Vì sao một server chạy NTP không đồng nghĩa toàn bộ transaction có external consistency? Cần những bảo đảm nào ngoài clock sync?

**Gợi ý:** uncertainty bounds, commit ordering, transaction protocol.

### Bài 15 — HLC

HLC timestamp `(1000,3)` và `(1000,4)` có nghĩa cách nhau một mili giây thực không? Có đủ để đo lease 30 giây không?

**Gợi ý:** logical counter không phải elapsed.

### Bài 16 — Client timeout

Client gửi write, timeout sau 2s nhưng DB đã commit. Retry cùng ý định với request ID khác có thể gây lỗi gì?

**Gợi ý:** duplicate side effect, cần idempotency key ổn định.

### Bài 17 — Dữ liệu giá

Hai worker update giá, worker cũ thức dậy sau pause và ghi sourceVersion thấp hơn. Bên cạnh lease, cần điều kiện nào tại write boundary?

**Gợi ý:** conditional version/CAS và guard epoch.

### Bài 18 — Hệ hai DC

Hai DC mất liên lạc, một DC có quorum còn DC kia không. Mô tả policy cho `reserveSeat`, `getCatalog` và `getSeatOwnerStrong`.

**Gợi ý:** không cần chung availability policy cho mọi operation.

### Bài 19 — Suspend

VM holder bị suspend 1 phút. Cần kiểm tra gì về monotonic source, drift assumption và revalidation trước khi viết tiếp?

**Gợi ý:** không tự tin lease còn hạn sau resume.

### Bài 20 — Fencing high-water mark

B được grant epoch 42, nhưng resource chưa biết 42. Write cũ epoch 41 đến trước. Vì sao `maxSeenToken` đơn giản có thể chấp nhận nó? Đề xuất protocol cài authority trước khi mở đường write mới.

**Gợi ý:** install epoch/guard phải ở cùng điểm commit có thẩm quyền.

### Bài 21 — Điều tra lỗi

Hãy đề xuất tám log fields/metrics để điều tra “A vẫn ghi sau khi B được bầu”: clock offset, GC pause, lease ID, epoch, request ID, commit index, retry, fencing rejection...

**Gợi ý:** không dựa duy nhất vào thời gian log của host.

### Bài 22 — Chạy Java

Chạy `LeaseClockDemo` và `FencingDemo`. Giải thích sự khác nhau giữa điều chỉnh clock local và kiểm quyền tại resource. Tại sao hai ví dụ không tạo distributed consensus?

**Gợi ý:** thiếu mạng, quorum và protocol grant.

### Bài 23 — Job gửi hóa đơn

Job thường 3 giây nhưng có lúc kéo dài 90 giây, nhiều instance cùng retry. Thiết kế lease, trạng thái job và idempotency để không gửi hóa đơn trùng.

**Gợi ý:** lock TTL không fence external provider.

### Bài 24 — Voucher giới hạn

Thiết kế API nhận voucher tối đa 100 lượt với:

~~~yaml
resource: "campaign:42"
invariant: "At most 100 confirmed claims"
authority: "..."
leaseClockAssumptions: "..."
epochAndFencing: "..."
conditionalCommit: "..."
idempotencyKey: "..."
onPartition: "..."
unknownOutcome: "..."
faultTests:
  - "..."
~~~

**Gợi ý:** không quyết định cấp voucher chỉ dựa trên stale count từ cache.

## 41. Checklist review lease/clock

Trước khi sử dụng lease để bảo vệ write, hãy trả lời:

1. Resource nào đang được bảo vệ?
2. Ai có quyền grant và grant có cần quorum không?
3. Hai grantors có thể cấp quyền xung đột không?
4. Có term/epoch tăng và state bền qua crash không?
5. Thời gian lease bắt đầu ở sự kiện nào?
6. Grantor và holder dùng đồng hồ nào?
7. Bounded drift/uncertainty có thực sự được bảo đảm và giám sát không?
8. Holder có tự hết hạn sớm hơn grantor với biên an toàn không?
9. Renewal thất bại/ACK muộn được xử lý thế nào?
10. Holder pause, suspend hoặc restart có phải revalidate không?
11. Một packet cũ đến sau khi chuyển quyền bị bác tại đâu?
12. Resource kiểm current epoch từ authority đáng tin hay chỉ max-seen?
13. Việc cài epoch mới và mở đường write của holder mới có thứ tự an toàn không?
14. API có idempotency và unknown-outcome lookup không?
15. Business invariant có conditional update/transaction phù hợp không?
16. Khi network partition, bên không có quyền có ngừng strong writes không?
17. Read có hứa linearizability hay được phép stale?
18. Có monitor clock drift, election churn và stale write rejection không?
19. Có fault injection cho pause, restart, partition, late ACK không?
20. Có tài liệu tách safety guarantee khỏi heuristic vận hành không?

Nếu thiết kế chỉ ghi `leaseTTL=30000` mà chưa giải quyết các câu hỏi này, **chưa đủ để tuyên bố quyền ghi độc quyền an toàn trong hệ phân tán**.

## 42. Những hiểu nhầm thường gặp

| Nhận định | Vì sao sai hoặc thiếu | Cách hiểu đúng |
| --- | --- | --- |
| “Lease là lock có TTL nên an toàn tuyệt đối.” | Holder có thể pause và write muộn | Cần protocol/fencing |
| “Monotonic không bao giờ sai.” | Clock vẫn drift và khác host | Dùng cho elapsed local |
| “Offset nhỏ bây giờ nên luôn đúng.” | Drift có thể tích lũy | Theo dõi bound |
| “Timeout chứng minh node chết.” | Delay/partition/GC có biểu hiện giống nhau | Timeout chỉ là nghi ngờ |
| “Gửi renew nghĩa đã renew.” | Request/ACK có thể mất | Chờ grant commit |
| “ACK renew cũ đến muộn vẫn hợp lệ.” | Epoch có thể đã chuyển | Kiểm term/lease ID |
| “Tăng TTL thì không có stale owner.” | Pause có thể kéo dài bất kỳ | Fencing tại resource |
| “Packet gửi khi còn lease luôn hợp lệ.” | Có thể commit sau expiry | Guard tại commit |
| “Fencing token bằng milliseconds.” | Skew/step/collision | Generation từ authority |
| “Max token đã thấy luôn đủ.” | Resource có thể chưa cài thế hệ mới | Bảo vệ handoff/install |
| “NTP làm mọi đồng hồ giống nhau.” | Offset/uncertainty vẫn tồn tại | Clock contract, không thay consensus |
| “HLC counter đo duration.” | Logical order không bằng thời gian thực | Đúng loại clock |
| “Consensus safety cần NTP hoàn hảo.” | Safety của nhiều protocol dựa trên quorum/term | Phân biệt thuật toán và lease optimization |
| “Có majority ACK thì mọi lease an toàn.” | Grantor expiry/reboot/race cần đúng | Chứng minh toàn giao thức |
| “Lease giải quyết CAP.” | Partition vẫn gây trade-off | Chọn policy theo operation |
| “Lease ngăn mọi duplicate payment.” | Client retry/outcome không rõ | Idempotency và đối soát |
| “Leader lease chứng minh ACID invariant.” | Quyền ghi khác ràng buộc dữ liệu | Transaction/CAS riêng |

## 43. Tổng kết

1. **Lease là quyền có thời hạn** và phải chỉ rõ resource, grant authority, holder, epoch, expiry và renewal.
2. **Wall clock, monotonic clock và logical clock khác mục đích.** Wall clock phục vụ thời gian lịch; monotonic đo elapsed cục bộ; logical clock hỗ trợ ordering, không tự đo real-time duration.
3. **Clock skew và drift không phải lỗi trang trí.** Một monotonic clock chậm vẫn có thể khiến holder tin lease còn hạn sau khi grantor đã hết hạn nếu giao thức không có biên thời gian phù hợp.
4. **Timeout không chứng minh node chết.** Mạng, GC, pause và mất ACK có thể tạo tình huống không phân biệt được.
5. **Quorum, term và epoch là những công cụ bảo vệ quyền.** Hai nhóm bị partition không được tùy ý cấp hai quyền ghi độc lập khi nghiệp vụ đòi single-writer semantics.
6. **Fencing cần được kiểm ở điểm commit** và phải có protocol chuyển quyền/cài thế hệ an toàn. Write gửi trước expiry vẫn có thể tới sau expiry.
7. **Renewal, reboot và pause phải được xem như tình huống bình thường cần xử lý**, không phải trường hợp quá hiếm để bỏ qua.
8. **Clock sync hỗ trợ vận hành nhưng không thay consensus.** NTP/chrony/PTP, HLC và TrueTime-like APIs có phạm vi bảo đảm khác nhau.
9. **Lease không thay transaction, idempotency và business invariant.** Một owner hợp lệ vẫn có thể ghi dữ liệu sai; một retry vẫn có thể tạo side effect lặp.

**Nguyên tắc thực hành:** khi tài liệu nói “A được ghi vì có lease 30 giây”, hãy hỏi **“ai cấp lease, clock nào định thời hạn, giả định drift nào được bảo đảm, quyền cũ bị fence ở đâu, và write cũ đến muộn có thể còn tác dụng không?”**. Chỉ khi các câu hỏi này được giải quyết trong một giao thức nhất quán thì lease mới là một công cụ bảo vệ quyền ghi đáng tin cậy cho hệ NoSQL phân tán.
