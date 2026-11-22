# PACELC và cách đặt câu hỏi về đánh đổi nhất quán/độ trễ

Khi chọn cơ sở dữ liệu NoSQL, câu hỏi “hệ này là CP hay AP?” mới chỉ bao quát một phần nhỏ bài toán. Phần lớn thời gian hệ thống **không gặp phân vùng mạng**, nhưng vẫn cần quyết định: một lượt đọc có phải thấy ngay dữ liệu vừa ghi ở vùng khác hay được phép cũ vài giây; ghi có cần đợi nhiều bản sao xác nhận hay có thể trả nhanh; nếu mạng bị chia cắt thì tiếp tục phục vụ đến đâu mà không phá bất biến nghiệp vụ?

**PACELC** là khung đặt hai nhóm câu hỏi:

> **Nếu có Partition (P), đánh đổi Availability (A) với Consistency (C); Else (E), khi không có partition, đánh đổi Latency (L) với Consistency (C).**

Bài học thuộc chương **CAP và các đánh đổi** của module Database No SQL. Mục tiêu không phải gắn một nhãn bất biến cho từng sản phẩm, mà là **biết hỏi đúng về tính đúng đắn, độ mới, thời gian phản hồi, phạm vi replication và cách xử lý lỗi mạng** trước khi thiết kế API, cấu hình read/write hoặc chọn topology.

Các ví dụ dùng catalog, tồn kho, đơn hàng, thanh toán và hệ thống đa vùng. Số liệu thời gian nếu có chỉ là **giả định minh họa**, không phải benchmark đã thực hiện hay cam kết của nhà cung cấp.

## 1. Vì sao CAP chưa đủ cho bài toán thực tế?

CAP tập trung vào một tình huống đặc biệt: các node **không thể giao tiếp với nhau do network partition**. Nhưng ứng dụng có thể chậm mỗi ngày vì một truy vấn phải chờ replica ở vùng địa lý xa, dù không có phân vùng mạng.

Một số câu hỏi thực tế:

- Khi mạng bình thường, có cần đợi thêm RTT để nhìn thấy dữ liệu mới nhất không?
- Khi mạng bị chia cắt, có cho phép cả hai phía cùng quyết định cấp vé cuối không?
- Dữ liệu nào có thể cũ vài giây mà không gây thiệt hại?
- Dữ liệu nào phải có kiểm tra nguyên tử tại nguồn trước khi trả “thành công”?
- Người dùng có cần **đọc thấy chính ghi của mình** không?
- p95/p99 của GET/POST bị ảnh hưởng thế nào khi đổi write concern/read consistency?

PACELC bổ sung câu hỏi thường ngày về **L/C**, thay vì chỉ hỏi về **A/C** lúc xảy ra partition.

## 2. CAP được hiểu như thế nào?

| Ký hiệu | Ý nghĩa trong CAP | Không nên nhầm với |
|---|---|---|
| **C — Consistency** | Theo mô hình CAP tiêu chuẩn, các thao tác có tính nhất quán như một bản sao nguyên tử, thường diễn đạt bằng **linearizability** | “Consistency” của ACID là bất biến hợp lệ |
| **A — Availability** | Mỗi request tới node không hỏng nhận phản hồi hợp lệ theo mô hình | Uptime 99,99% hoặc HTTP luôn trả bất kỳ mã lỗi nào |
| **P — Partition** | Có thể xảy ra tình huống các nhóm node không trao đổi message được | Một tính năng có thể tùy tiện tắt trong thế giới thực |

Khi xảy ra phân vùng mạng và cả hai phía đều phải phục vụ yêu cầu, không thể đồng thời bảo đảm CAP consistency mạnh và availability cho mọi thao tác trong mô hình CAP. Một hướng **thiên về C** có thể chặn/từ chối thao tác ở phía không đủ thẩm quyền. Một hướng **thiên về A** có thể chấp nhận thao tác ở nhiều phía, nhưng phải tính cách hòa giải những kết quả mâu thuẫn.

**P không phải một nút chọn “bỏ partition tolerance”**: partition vẫn có thể xảy ra. Cần thiết kế hành vi dưới điều kiện lỗi đó.

### 2.1. “C” của CAP khác “C” của ACID

Trong ACID, chữ Consistency thường nói về ràng buộc trạng thái nghiệp vụ, ví dụ `availableStock >= 0`. Trong CAP/PACELC, chữ C nói về **mức nhất quán trong quan sát/thứ tự thao tác của bản sao phân tán**.

Một GET linearizable của Stock không tự làm Order và Payment provider nằm trong cùng transaction. Ngược lại, một workflow eventual-consistent vẫn có thể dùng conditional writes, reservation state machine và reconciliation để không cấp thừa hàng. Vì vậy cần nói rõ cả **mô hình consistency** lẫn **bất biến nghiệp vụ**.

## 3. PACELC có hai nhánh

~~~mermaid
flowchart TD
    A["Hệ phân tán"] --> B{"Có network partition?"}
    B -->|Partition P| C["Đánh đổi Availability và Consistency"]
    B -->|Else E| D["Đánh đổi Latency và Consistency"]
    C --> F["Hành vi khi các nhóm không liên lạc"]
    D --> G["Hành vi bình thường: chờ phối hợp đến đâu?"]
~~~

Ý nghĩa những nhãn thường gặp:

- **PA**: trong partition, ưu tiên tiếp tục phục vụ một số operation dù các bản sao có thể tạm khác nhau.
- **PC**: trong partition, bảo vệ consistency nên một số request có thể bị chặn/từ chối.
- **EL**: khi không partition, ưu tiên latency thấp hơn, có thể dùng replica/cache chưa bắt kịp.
- **EC**: khi không partition, ưu tiên consistency mạnh hơn và chấp nhận chi phí phối hợp.

Các cặp như `PA/EL`, `PC/EC` chỉ nên xem là **mô tả định hướng cho một cấu hình, workload và loại thao tác**, không phải “chứng minh” rằng mọi read/write trên một database luôn cùng hành vi.

**E = Else**, tức không có network partition đang xét, **không phải Eventual consistency**. Ngay trong ngày bình thường, network RTT, disk sync, queue, replication và quorum vẫn tốn thời gian.

## 4. Ví dụ khi partition: chỉ còn một vé cuối

~~~text
Trước phân vùng:
  Region A: available=1
  Region B: available=1
  Bản sao đã đồng bộ

Sau phân vùng:
  Region A  <---X--->  Region B
  Client A: reserve 1
  Client B: reserve 1
~~~

Nếu hai region đều tự quyết định “HELD thành công” mà không có protocol phân quyền capacity, quota escrow, quorum hoặc owner thích hợp, hệ có thể giữ **hai lần cho một vé**. Khi mạng phục hồi, hợp nhất dữ liệu không thể tự sửa lời hứa đã đưa cho cả hai khách.

Một hướng thiên về C: chỉ nơi có thẩm quyền/quorum cần thiết được quyền commit, phía còn lại từ chối hoặc chờ.

Một hướng thiên về A của **API tiếp nhận ý định**: cả hai vùng có thể nhận yêu cầu ở trạng thái `PENDING`, nhưng chưa hứa cấp được vé. Sau khi mạng lành, nguồn có thẩm quyền xử lý và một yêu cầu có thể bị từ chối. Đây là **đổi hợp đồng API**, không phải làm biến mất trade-off.

Phải phân biệt:

| Trạng thái | Điều đã được hứa |
|---|---|
| ACCEPTED/PENDING | Đã nhận yêu cầu, chưa cấp được tài nguyên |
| HELD | Đã giữ được theo bất biến quota |
| CONFIRMED | Các điều kiện xác nhận tiếp theo đã đạt |
| REJECTED | Yêu cầu không được cấp |

Một response `202 Accepted` không tương đương lời hứa `201 Reserved`.

## 5. Khi không partition vẫn phải chọn L hoặc C

Giả sử Product source nằm ở một vùng và client ở vùng khác. Có một replica gần client vừa nhận replication chậm hơn một nhịp.

| Đường đọc | Lợi ích | Đánh đổi |
|---|---|---|
| Local replica không chờ | Network RTT thấp | Có thể thấy bản cũ |
| Leader/nguồn có thẩm quyền ở xa | Dễ cung cấp consistency mạnh theo protocol | Cross-region RTT và p99 cao hơn |
| Cache hoặc search projection | Đọc nhanh, scale tốt | TTL/invalidation/index lag |
| Local replica chờ version token | Có thể đáp ứng read-your-writes | Chờ đồng bộ hoặc fallback |

Không có partition **không có nghĩa replicas lập tức giống nhau**. Mạng luôn có latency, các hàng đợi và ghi disk có thể trì hoãn việc bản sao bắt kịp.

Đánh đổi EL/EC thường nằm ở **read/write path**: có chờ quorum/leader, có dùng read preference tới replica gần, có phải đợi một version nhất định, hay trả kết quả nhanh khi bản sao chưa kịp cập nhật.

## 6. Độ trễ phải được mô tả bằng loại thao tác và percentile

Đừng chỉ hỏi “mất bao nhiêu mili-giây?”. Cần hỏi:

- GET, POST hay transaction nào?
- p50, p95, p99 end-to-end hay server-side?
- Thử ở local region hay cross-region?
- Cache hit hay miss; dữ liệu lớn hay nhỏ?
- Read consistency/write concern nào?
- Lượt retry/timeout có được tính vào latency không?
- Quorum có đợi node chậm nhất hay một tập node nhất định?
- Khi compaction, failover hoặc congestion, độ trễ đổi ra sao?

Số giả định để minh họa, **không phải benchmark**:

| Đường đọc minh họa | p50 | p99 | Freshness |
|---|---:|---:|---|
| Cache gần user | 3 ms | 22 ms | Tùy invalidation/TTL |
| Replica local không chờ | 8 ms | 35 ms | Có thể stale |
| Đọc cần phối hợp vùng xa | 68 ms | 230 ms | Mạnh hơn theo protocol |

Không cộng p99 của các components một cách máy móc để kết luận p99 toàn request; phụ thuộc các bước song song, tuần tự và tương quan giữa độ trễ.

## 7. Linearizability: “ghi xong rồi, đọc có thấy không?”

Một lịch sử **linearizable** có thể được giải thích như mỗi thao tác có một thời điểm hiệu lực giữa lúc được gọi và lúc trả lời, đồng thời tuân thủ thứ tự thời gian thực của những thao tác không chồng lấp.

~~~text
10:00:01  Client A: PUT x=2 -> success
10:00:02  Client B: GET x (bắt đầu sau PUT hoàn tất)
~~~

Nếu không có write mới, một GET linearizable trên cùng object phải quan sát `x=2`. Nếu GET từ replica chậm vẫn thấy `x=1`, đường đọc đó không đáp ứng linearizability trong lịch sử này.

Linearizability là **mức nhất quán quan sát** với phạm vi được định nghĩa. Nó không tự đảm bảo mọi record trong nhiều hệ cùng commit; cũng không đồng nghĩa valid JSON hoặc “không mất dữ liệu sau crash”.

## 8. Linearizability và serializability không giống nhau

- **Linearizability:** nhấn mạnh tính nguyên tử và thứ tự thời gian thực của các operation trên phạm vi object/system được định nghĩa.
- **Serializability:** lịch sử nhiều transaction tương đương một thứ tự thực thi tuần tự nào đó.
- **Strict serializability:** kết hợp serializability với ràng buộc thứ tự thời gian thực phù hợp.

Ví dụ:

- “Người dùng vừa đổi password phải được kiểm tra với giá trị mới ngay” → freshness/linearizability và auth contract.
- “Hai giao dịch không được cùng bán vé cuối” → atomic conditional write/transaction isolation bảo vệ invariant.
- “Đơn và payment provider phải đúng dù response mất” → idempotency, state machine và reconciliation thêm vào.

Chỉ nói “strong consistency” chưa đủ để quyết định transaction scope hoặc điều kiện bảo toàn business outcome.

## 9. Những mô hình nhất quán khác cũng hữu ích

| Mô hình/yêu cầu | Ý nghĩa | Tình huống |
|---|---|---|
| Eventual consistency | Khi ngừng update và hệ hội tụ theo điều kiện, replica cuối cùng đồng nhất | Feed, search projection |
| Read-your-writes | Session đọc thấy các ghi đã hoàn tất của mình theo contract | Trang vừa sửa profile |
| Monotonic reads | Session không quay ngược sang version cũ hơn nó đã thấy | Điều hướng nhiều replicas |
| Causal consistency | Các thao tác có quan hệ nhân quả được thấy theo thứ tự phù hợp | Comment và reply |
| Bounded staleness | Độ cũ có giới hạn được công bố | Analytics cho phép chậm 5 giây |
| Linearizable operations | Tôn trọng thứ tự thực đối với object/operations | Một số quyết định quyền/quota |
| Serializable transactions | Kết quả tương đương transaction tuần tự | Invariants đa record |

Eventual không có nghĩa dữ liệu luôn trễ “khoảng 1 giây”; nếu sản phẩm không đưa ra upper bound thì không hứa freshness dưới một giá trị cố định.

Read-your-writes thường có thể đạt bằng session stickiness, version token, causal session hoặc chờ replica bắt kịp theo khả năng engine. Không đồng nghĩa mọi client ở mọi region đều linearizable.

## 10. Không phải dữ liệu nào cũng cần cùng consistency

| Dữ liệu | Rủi ro khi stale | Câu hỏi cần hỏi |
|---|---|---|
| Mô tả/ảnh catalog | Thường thấp | Chấp nhận cache vài phút? |
| Bộ đếm lượt xem | Thường thấp | Có thể tổng hợp eventual? |
| Search result | Có thể chấp nhận chậm cập nhật | Checkout có validate lại nguồn không? |
| Giá dùng để thu tiền | Cao hơn | Giá cuối được chốt theo version nào? |
| Tồn kho/vé cuối | Cao | Conditional commit ở nguồn có ngăn oversell? |
| Ledger thanh toán | Rất cao | Nguồn chuẩn và transaction phạm vi nào? |
| Quyền truy cập bị thu hồi | Có thể rất cao | Stale permission tối đa được phép bao lâu? |
| Dashboard | Phụ thuộc người dùng | Có gắn nhãn thời điểm cập nhật không? |

Cùng sản phẩm có thể dùng cache eventual cho catalog, search projection cho discovery và conditional writes/transactions mạnh cho checkout. Không cần áp một consistency level cho toàn bộ ứng dụng nếu hợp đồng endpoint được phân định rõ.

## 11. “Strong consistency” phải gắn với phạm vi dữ liệu

Một câu “inventory cần strong consistency” vẫn thiếu:

- Một SKU/một warehouse, hay tổng quota của nhiều warehouses?
- Chỉ cập nhật Stock document, hay phải commit cả Order và Reservation?
- Một primary region hay multi-region multi-writer?
- “Success” là đã nhận intent hay đã giữ hàng?
- Ai là nguồn quyết định capacity cuối cùng?
- Có cần mọi region đọc ngay version mới, hay chỉ client vừa ghi?
- Nếu primary mất liên lạc, được từ chối checkout không?
- Nếu ghi thành công nhưng response mất, truy vấn lại outcome bằng ID nào?

Một thiết kế thường phù hợp: hiển thị số lượng tồn kho ước tính trên cache để giao diện nhanh; **khi checkout phải xác minh và giữ hàng có điều kiện tại nguồn chuẩn**. Đây là quyết định theo business invariant, không chỉ lựa chọn “CP database”.

## 12. Availability trong partition là availability của operation nào?

Một hệ có thể tiếp tục trả catalog từ cache trong khi không còn quyền quyết định chính xác tồn kho khi mạng chia cắt.

~~~text
Trong network partition:
  GET catalog cached       -> có thể trả
  GET exact inventory      -> có thể đợi hoặc lỗi
  POST reserve confirmed   -> có thể từ chối nếu thiếu owner/quorum
  POST reserve intent      -> có thể nhận PENDING để xử lý sau
~~~

Cần tách **API vẫn reachable** khỏi **operation thành công theo đúng hợp đồng**. Trong CAP, một error response do không thể hoàn tất consistent operation không đồng nghĩa availability của operation đó theo định nghĩa lý thuyết.

Khi bàn “dịch vụ phải vẫn hoạt động”, hãy hỏi cụ thể: GET nào, POST nào, trả `200` hay `202` hay `503`, có được phép mất write không, và người dùng được thông báo trạng thái nào.

## 13. Khởi đầu bằng câu hỏi nghiệp vụ, không phải tên database

Một cuộc họp kiến trúc dễ đi sai khi bắt đầu bằng “Cassandra là AP nên dùng cho mọi thứ cần availability”. Hãy bắt đầu bằng một chuỗi câu hỏi:

1. **Ai đang làm gì?** Người dùng đọc profile, sửa địa chỉ, đặt vé hay chuyển tiền?
2. **Đơn vị dữ liệu là gì?** Một document/key, nhiều records, nhiều partitions hay service?
3. **Tác hại của dữ liệu cũ là gì?** Hiển thị sai vài giây, cấp vượt quota, chuyển nhầm tiền hay lộ quyền?
4. **Trễ tối đa bao nhiêu?** p95/p99 read, write và full workflow SLO như thế nào?
5. **Consistency chính xác là gì?** Read-your-writes, bounded staleness, causal, linearizable hay transaction serializable?
6. **Trong partition sẽ làm gì?** Từ chối, đợi có deadline, trả cache, nhận pending, hay tiếp tục ghi có conflict resolution?
7. **Khi dữ liệu hội tụ sẽ xử lý gì?** LWW, version/CAS, CRDT, manual reconciliation, compensation hay domain merge?
8. **Ai là nguồn chuẩn?** Primary/key owner, transaction log, event stream hay một external provider?
9. **Retry/timeout có thể lặp không?** Có idempotency key và outcome query không?
10. **Làm sao đo và chứng minh?** Thử lỗi/lag, xem tracing, kiểm tra invariant và phục hồi?

Mười câu này không tạo ngay lựa chọn “đúng”, nhưng buộc yêu cầu **có thể kiểm chứng** thay vì đánh đổi trừu tượng.

## 14. Viết hợp đồng nhất quán có thể đo được

Câu mơ hồ:

> Ứng dụng phải phản hồi nhanh và luôn hiển thị dữ liệu mới.

Không thể dùng câu đó để lựa chọn PACELC vì “nhanh” và “mới” không có phạm vi.

Một ví dụ yêu cầu tốt hơn:

| Operation | Consistency contract | Latency SLO minh họa | Khi partition |
|---|---|---|---|
| Đọc catalog | Có thể chậm tới 60 s | p95 dưới 100 ms tại vùng khách | Trả cache, kèm thời điểm cập nhật |
| Xem Order vừa tạo | Read-your-writes theo session | p95 dưới 250 ms | Đọc nguồn chuẩn hoặc hiển thị PENDING |
| Giữ vé | Không oversell; conditional commit | p99 dưới 500 ms khi khỏe | Nếu thiếu thẩm quyền, không trả HELD |
| Cập nhật profile | CAS chống lost update | p95 dưới 300 ms | Trả retryable unavailable nếu không thể commit |
| Analytics dashboard | Bản tổng hợp chậm tối đa 5 phút | p95 dưới 500 ms | Trả snapshot cuối và tuổi dữ liệu |
| Thu tiền | Không charge trùng cùng business ID | Tách API acceptance và settlement SLA | Đối soát provider nếu unknown |

Tất cả con số trong bảng **chỉ minh họa**, phải được thay bằng yêu cầu thực của hệ thống.

Ở mỗi dòng, thêm bốn trường không nên bỏ sót: **scope**, **freshness**, **failure behavior**, **validation**. Ví dụ “stale tối đa 60 s” phải nói cách đo từ event/source commit timestamp đến lúc response được tạo; nếu không có hard bound dưới partition, mô tả nó là **SLO theo điều kiện** chứ không phải guarantee tuyệt đối.

## 15. Hai trục Latency và Consistency cần có deadline cụ thể

Một lựa chọn đọc mạnh có thể chờ replica bắt kịp phiên bản hoặc truy vấn leader. Vậy “chờ bao lâu”?

Mẫu câu nên hỏi:

- Nếu đọc mạnh không hoàn tất trong 200 ms, trả lỗi hay fallback?
- Fallback sang dữ liệu cũ có được **khai báo rõ** với caller không?
- Có thể trả `PENDING` rồi poll thay vì giữ HTTP request hàng giây không?
- Có cần read-your-writes cho đúng session, hay toàn cục?
- Một reader nhìn version 12 rồi chuyển sang replica chỉ có version 11 có được phép không?
- Nếu dữ liệu cũ, API có trả `lastUpdatedAt`/`observedVersion` hay freshness header?
- Thao tác ghi cần chờ bao nhiêu replicas/regions?
- Chọn cấu hình có vượt p99 budget ở lúc compaction hoặc failover không?

Độ trễ có thể phân rã khái niệm:

\[
T_{\mathrm{request}}
\approx
T_{\mathrm{routing}} + T_{\mathrm{read/write}} +
T_{\mathrm{coordination}} + T_{\mathrm{queue}} + T_{\mathrm{response}}
\]

Các bước thực tế có thể song song nên công thức là **mô hình tìm nguyên nhân**, không phải phép cộng để ước lượng chính xác p99. “Consistency mạnh hơn làm chậm hơn” là xu hướng hay gặp khi cần phối hợp thêm, nhưng không phải định luật rằng mọi query ở mọi cấu hình sẽ chậm.

## 16. Quorum: một công cụ suy luận, không phải nhãn consistency tuyệt đối

Giả sử một khóa có `N=3` replicas, một thiết kế dùng:

- `W=2` acknowledgments để ghi hoàn tất.
- `R=2` replicas tham gia đọc.

Trong mô hình đơn giản với cùng một replica set và cơ chế version/repair đúng, ta thấy:

\[
R + W > N
\]

Điều kiện giao nhau cho thấy tập đọc và tập ghi **phải có ít nhất một replica chung** trong những giả định của mô hình. Nhưng **quorum intersection không tự bảo đảm linearizability** trong mọi hệ; còn phải xem concurrent writes, version selection, read repair, failure handling, sloppy quorum, clock behavior và giao thức commit/leader.

Ví dụ:

~~~text
N=3, W=2, R=2  -> các tập quorum giao nhau
N=3, W=1, R=1  -> có thể đọc một replica chưa được ghi
N=3, W=3       -> ghi phải đợi toàn bộ 3 replica theo giả định
~~~

Khi một node chậm, W=3 có thể kéo latency hoặc khiến write không thể hoàn tất theo deadline. W=1 có thể trả nhanh hơn nhưng chấp nhận rủi ro mất ghi/freshness theo hệ và topology.

Không áp công thức này tùy tiện cho multi-region replication, quorums không cùng tập, managed APIs, multi-leader hoặc engine có cơ chế riêng. **Phải dùng consistency contract của sản phẩm, không tự thiết kế bảo đảm chỉ từ một bất đẳng thức.**

### 16.1. Quorum và Durability không phải cùng thuộc tính

Một số lượng replicas ACK không luôn có nghĩa mỗi bản sao đã fsync dữ liệu xuống thiết bị lưu trữ; write concern/commit log/sync policy mới xác định độ bền trong failure model. Quorum có thể liên quan consistency/availability; durability còn cần phân tích ACK, log, replica retention và backup.

## 17. Đọc theo session: trung gian giữa local nhanh và global linearizable

Người dùng cập nhật tên hiển thị:

~~~text
PUT /profile -> version=42, ACK
GET /profile (sau đó, cùng người dùng) -> không được thấy version=41
~~~

Không nhất thiết mọi client trên thế giới đều phải thấy version 42 ngay để đáp ứng trải nghiệm này. Một số cơ chế có thể cung cấp **read-your-writes/monotonic reads**:

- Giữ session đọc ở một nguồn/replica đã thấy phiên bản cần thiết.
- Truyền **causal/session token** nếu sản phẩm hỗ trợ.
- Đọc từ leader/primary khi cần.
- Đợi local replica bắt kịp một version, có deadline/fallback.
- Hiển thị optimistic UI nhưng phải xác minh nếu dữ liệu cần độ đúng tuyệt đối.

Optimistic UI không phải consistency guarantee của database: UI có thể hiển thị giá trị mới ngay nhưng server chưa commit. Khi write bị từ chối, cần rollback/hiển thị conflict.

Đặt câu hỏi đúng: **“Người đã sửa có phải đọc thấy ngay không?”** thường cụ thể và ít tốn kém hơn “mọi replica luôn phải linearizable”.

## 18. MongoDB: hỏi theo read concern, write concern, read preference

MongoDB cho phép chọn những thuộc tính khác nhau cho read/write. Khái niệm cần tách:

| Thuộc tính | Điều cần hỏi |
|---|---|
| **Read preference** | Đọc primary hay secondary/nearest? |
| **Read concern** | Tập dữ liệu có những bảo đảm visibility/snapshot nào? |
| **Write concern** | Ghi cần được xác nhận bởi mức nào của replica set? |
| **Session/causal consistency** | Các thao tác trong session có quan hệ nhân quả/read-your-writes theo cấu hình nào? |
| **Transaction** | Những document/shard nào được commit atomically và isolation gì? |

Ví dụ mongosh ở mức minh họa khái niệm:

~~~javascript
// Ghi, cần kiểm tra write concern tương ứng topology.
db.getCollection("products").updateOne(
  { _id: "p100", version: 7 },
  {
    $set: { name: "Mouse V2" },
    $inc: { version: 1 }
  },
  { writeConcern: { w: "majority" } }
);

// Query từ source có thẩm quyền theo request path phù hợp.
db.products.findOne({ _id: "p100" });
~~~

Không suy rằng một read từ primary với read concern mặc định luôn tương đương **linearizable read**, hoặc majority write tự làm mọi secondary read ngay lập tức thấy bản mới. Nếu yêu cầu linearizable, cần xem đúng điều kiện hỗ trợ read concern `linearizable`, primary/read path, majority write và giới hạn/timeouts theo phiên bản; transaction snapshot và linearizable read cũng không phải một mode chung.

**Câu hỏi PACELC:** khi người dùng ở region xa primary, chấp nhận đọc secondary gần người dùng và stale bao lâu, hay chờ nguồn mạnh hơn? Khi mất kết nối với primary/majority, operation nào phải từ chối thay vì tạo trạng thái mâu thuẫn?

## 19. Cassandra/ScyllaDB: consistency level phải gắn với topology và operation

Trong những triển khai họ Cassandra, client có thể chọn consistency level như `ONE`, `LOCAL_QUORUM` hoặc `ALL` theo khả năng/phiên bản. Chúng điều chỉnh số replica cần xác nhận/tương tác, từ đó ảnh hưởng latency, availability và độ mới theo giao thức.

Bài toán cần hỏi:

- Replication factor của mỗi data center là bao nhiêu?
- `LOCAL_QUORUM` đang nói tới replica nào và data center nào?
- Request có chạm một partition hay nhiều partition?
- Hệ xử lý concurrent writes, timestamp, read repair, hinted handoff và repair thế nào?
- Các client có cần serializability/linearizability cho conditional update không?
- Khi nào phải dùng **LWT/conditional write** theo phạm vi được hỗ trợ, với chi phí coordination riêng?
- Nếu một region không liên lạc được, local reads/writes còn được phục vụ theo mức nào?

Quorum reads/writes thường **không thể được quảng bá là linearizable chỉ dựa trên R+W>N**. Với business rule như không bán quá vé, hãy đặt điều kiện tại source hoặc dùng một protocol có phạm vi và semantics phù hợp, không dùng read-then-write yếu rồi hy vọng read quorum luôn thấy đúng.

## 20. DynamoDB: strong read ở đâu và index khác nhau thế nào?

Trong DynamoDB, cần phân biệt **đọc từ bảng gốc**, **LSI**, **GSI**, replication giữa regions và transactional operations. Một số đường đọc có tùy chọn strongly consistent reads trong phạm vi dịch vụ hỗ trợ; **GSI có semantics eventual consistency**, không thể suy GSI có cùng read consistency như bảng gốc. Với multi-region replication, local strong read (nếu có) không tự là global linearizable across regions.

Ví dụ pseudocode ý tưởng:

~~~text
GetItem(
  TableName = "Products",
  Key = {"PK":"TENANT#t01", "SK":"PRODUCT#p100"},
  ConsistentRead = true  // chỉ trên đường đọc được hỗ trợ
)
~~~

Những câu hỏi thực tế:

1. Khi user vừa ghi, GET ngay sau đó đọc table hay index?
2. Có cần regional/global consistency, hay chỉ strong trong một vùng?
3. GSI projection lag có ảnh hưởng quyết định checkout không?
4. Conditional `UpdateItem` có đủ bảo vệ một item quota, hay cần transaction nhiều items?
5. Khi lỗi vùng, routing/failover và conflict resolution được định nghĩa như thế nào?
6. Chế độ đọc/ghi mạnh hơn ảnh hưởng latency/capacity/cost ra sao?

Không dùng một GSI/search projection có thể stale làm nguồn cuối cùng để trừ stock hoặc xác nhận số tiền.

## 21. Redis: latency thấp không tự đồng nghĩa consistency mạnh

Redis thường có response rất nhanh ở mô hình phù hợp và nhiều thao tác atomic trên một server/key. Nhưng khi dùng primary–replica với replication bất đồng bộ theo cấu hình, đọc replica có thể cũ, còn failover có thể đặt ra câu hỏi về writes chưa được sao chép đủ.

Một số câu hỏi:

- Redis là **cache** hay nguồn có thẩm quyền?
- Client đọc primary hay replica?
- Lệnh atomic/script có bảo vệ đúng một key hay nhiều keys cùng slot?
- ACK tới client nói gì về persistence (RDB/AOF), replica state và failover?
- Có dùng `WAIT` hoặc một cơ chế chờ bản sao, và bảo đảm thực tế của nó là gì?
- Khi cache invalidation chậm, có thể hiển thị sai gì?
- Khi split-brain hoặc failover, idempotency/business state được bảo vệ ở đâu?

Lệnh chờ replication như `WAIT` không nên bị đồng nhất với một cam kết durable/linearizable toàn hệ qua mọi sự cố. Nếu Redis chỉ là cache, nên xác định **nguồn chuẩn** để retry, reconcile và refetch khi cache cũ.

## 22. Search/index/cache: một ứng dụng có nhiều mức nhất quán

Một pipeline:

~~~mermaid
flowchart LR
    A["Product database: source of truth"] --> B["Outbox / CDC"]
    B --> C["Search index"]
    B --> D["Cache"]
    C --> E["Search API"]
    D --> F["Catalog API"]
    A --> G["Checkout validation"]
~~~

Một khách tìm sản phẩm trong search index đã stale. Khi bấm mua, **Checkout validation** đọc/ghi tại nguồn có thẩm quyền và kiểm tra điều kiện về giá/stock. Thiết kế này có thể đạt latency thấp cho discovery mà không hy sinh invariant giữ hàng.

Cần hỏi rõ:

- Tốc độ đồng bộ search/cache là SLO hay hard bound?
- Làm sao đo replication/index lag?
- Khi Product chuyển INACTIVE, search còn hiện tối đa bao lâu?
- Nếu cache lỗi, fallback đọc source có làm quá tải primary không?
- Event đến lại hoặc sai thứ tự, projection có CAS theo version không?
- Khi partition, search/cached catalog có thể tiếp tục, nhưng checkout có được phép hứa hàng không?

Đó là cách dùng PACELC **theo từng đường dữ liệu**, thay vì chọn một database “AP” cho cả ứng dụng.

## 23. Không nên phân loại một hệ bằng nhãn PC/PA/EC/EL tuyệt đối

Một bảng xếp loại có thể thuận tiện khi nhập môn, nhưng dễ đánh lừa người ra quyết định nếu không đi kèm các giả định.

Một sản phẩm có thể:

- Dùng một kiểu đọc từ leader cho checkout, nhưng đọc replica local cho catalog.
- Cho phép consistency level khác nhau theo request.
- Dùng replication bất đồng bộ cho read projection, nhưng conditional write ở nguồn chuẩn.
- Chấp nhận các update CRDT khi partition, nhưng từ chối một giao dịch cấp vé không thể merge.
- Có transaction một partition, trong khi transaction xuyên partition cần cơ chế khác.
- Có chế độ cấu hình khác nhau cho single-region và multi-region.

Vì vậy nhãn PACELC chỉ hữu ích khi điền đủ **operation + key scope + data model + topology + read/write config + failure assumptions**.

Ví dụ thay vì nói:

> Database X là PA/EL.

Hãy mô tả:

> Với GET catalog từ replica gần user, ta chấp nhận eventual consistency để giữ p95 thấp; với POST reserve trên một pool có thẩm quyền, khi không liên lạc được nguồn ghi thì trả unavailable thay vì cấp hai lần. Các bảo đảm này phải được kiểm chứng theo cấu hình của database X.

Câu thứ hai dài hơn nhưng có thể dẫn tới thiết kế và kiểm thử cụ thể.

## 24. Partition không chỉ là “mạng giữa hai region đứt hoàn toàn”

Những dạng lỗi liên quan:

| Dạng lỗi | Hiện tượng | Câu hỏi |
|---|---|---|
| Mất liên lạc giữa DC A/B | Hai nhóm node không thấy nhau | Bên nào có quyền nhận write? |
| Một node cô lập khỏi quorum | Node còn chạy nhưng không phối hợp được | Read cũ có được phục vụ không? |
| Packet loss/latency tăng cao | Có lúc thành công, có lúc timeout | Deadline bao lâu? Khi nào fail fast? |
| Leader đổi, client dùng route cũ | Request tới owner cũ | Fencing/version giúp gì? |
| Đồng hồ lệch | Timestamp conflicts/order không phản ánh thực | Có cần causal/sequence tokens? |
| DNS/routing sai | User bị đưa tới vùng không có dữ liệu mới | Session token và failover ra sao? |
| Process GC hoặc node quá tải | Trông giống timeout dù mạng không phân vùng | Metric phân biệt thế nào? |

Không phải mọi timeout đều là network partition theo định nghĩa CAP. Nhưng ứng dụng vẫn phải xử lý **không biết yêu cầu đã commit hay chưa**. Nếu client timeout sau ghi, retry phải có idempotency key/outcome tracking, độc lập với việc database được gọi là CP hay AP.

### 24.1. Bảo vệ leader/owner cũ bằng fencing

Trong failover, một owner cũ có thể tiếp tục chạy sau khi quyền sở hữu đã chuyển cho owner mới. Nếu nó vẫn có thể ghi nguồn, có nguy cơ split-brain.

Cần cơ chế owner epoch/term/version hoặc **fencing token** được kiểm tra ở nguồn có thẩm quyền. Không đủ nếu chỉ dựa vào một lease TTL trong memory và kỳ vọng worker cũ tự dừng đúng thời điểm. Cơ chế cụ thể phải theo consensus/replication protocol của hệ thống.

## 25. Khi nhận ghi ở nhiều phía: conflict resolution là vấn đề nghiệp vụ

Giả sử profile có field `nickname`: user sửa ở hai thiết bị khi offline. Last-write-wins có thể là lựa chọn chấp nhận được nếu sản phẩm quy định rõ.

Nhưng hai giao dịch bán cùng chiếc vé cuối không thể merge bằng quy tắc “lấy write có timestamp mới hơn” mà không hủy cam kết trước đó. Một số chiến lược:

| Dữ liệu/thao tác | Chiến lược có thể cân nhắc | Điều cần kiểm soát |
|---|---|---|
| Bộ đếm lượt xem | Counter/CRDT phù hợp, aggregation | Dedupe event, eventual convergence |
| Giỏ hàng đơn giản | Merge theo item ID, set semantics | Remove/add và xung đột ý định |
| Tài liệu cộng tác | CRDT/OT nếu phù hợp | Thứ tự sửa, tombstones, permission |
| Profile field cá nhân | Version/LWW theo contract | Ghi đè ngoài ý muốn |
| Vé có định danh duy nhất | Owner/conditional allocation, escrow | Không cấp hai lần |
| Thanh toán | Ledger/payment provider source + idempotency | Không nhân đôi tiền |
| Quyền truy cập | Thu hồi theo mức bảo mật yêu cầu | Cache stale window và enforcement |

**Có thể merge dữ liệu không đồng nghĩa có thể merge lời hứa nghiệp vụ.** Khi một write trả “đã cấp vé”, conflict resolution sau đó có thể không bảo vệ được trải nghiệm nếu có hai kết quả cùng được cam kết.

### 25.1. CRDT không phải lựa chọn miễn phí

CRDT giúp một số loại dữ liệu hội tụ dưới quy tắc toán học rõ, nhưng:

- Không bảo vệ mọi invariant xuyên nhiều object.
- Có metadata, tombstone, storage và merge costs.
- Phải định nghĩa đúng semantics add/remove và event ordering.
- Không tự giải bài toán thanh toán hoặc uniqueness của một tài nguyên khan hiếm.
- Phải phân biệt “giỏ hàng eventual” với “Order đã thanh toán”.

Với counter monotonic có thể merge, latency và availability có thể tốt; với quota bị giới hạn cứng, cần giao thức cấp quyền hoặc điều kiện chặn ở nguồn.

## 26. Escrow quota: một ví dụ giảm phối hợp trên đường nóng

Một pool tổng cộng 1.000 vé, hai vùng độc lập phục vụ khách:

~~~text
Global capacity = 1000

Region A được quyền cấp tối đa 600
Region B được quyền cấp tối đa 300
Reserve unallocated = 100
~~~

Nếu từng vùng chỉ được cấp trong quyền được phân bổ, nhiều yêu cầu không cần phối hợp xuyên vùng tại từng thao tác. Khi cần chuyển 100 quyền từ A sang B, việc chuyển phải bảo đảm:

1. A dừng cấp các quyền đã chuyển.
2. B chỉ bắt đầu cấp sau khi quyền chuyển được xác nhận.
3. Một transfer ID không được áp dụng hai lần khi retry.
4. Timeout phải được đối soát; không chuyển thêm khi kết quả không rõ.
5. Tổng quyền đã cấp cộng chưa cấp không vượt invariant global.

Escrow giảm **chi phí phối hợp theo từng request** bằng cách phân chia quyền trước. Đổi lại, một vùng có thể tạm hết quota dù vùng khác còn; lúc partition không thể luôn chuyển quota theo ý muốn. Đây là một đánh đổi PACELC có thể mô tả rõ về latency, consistency, flexibility và availability.

## 27. Lựa chọn theo SLO thay vì dùng “mạnh hơn là tốt hơn”

Giả sử yêu cầu giả định:

- Trang catalog p95 dưới 100 ms cho khách toàn cầu.
- Checkout p99 dưới 700 ms trong trạng thái hệ khỏe.
- Tồn kho **không âm**, không có hai confirmed holds cho vé định danh.
- Người vừa sửa địa chỉ phải thấy bản mới ở trang chi tiết.
- Khi mất một region, catalog vẫn xem được nhưng checkout có thể bị trì hoãn.

Phân chia:

| Đường truy cập | Yêu cầu chính | Phương án để đánh giá |
|---|---|---|
| Catalog GET | Latency thấp và freshness mềm | Cache/replica gần, TTL/version |
| Search | Query linh hoạt, dữ liệu có thể chậm cập nhật | Async index projection |
| Profile GET sau PUT | Session read-your-writes | Session token/primary read |
| Reserve POST | Business invariant cứng | Conditional write/transaction có thẩm quyền |
| Order status | Hiển thị tiến trình đáng tin | State machine, monotonic/causal reads |
| Payment | Không double charge | Stable attempt ID, provider reconciliation |

Không nhất thiết một datastore duy nhất là tối ưu mọi đường. Nhưng **thêm nhiều datastore** kéo theo chi phí CDC/outbox, schema evolution, cache invalidation và recovery. Chỉ thêm projection khi lợi ích về latency/query thực sự đủ lớn.

## 28. Không được che business failure bằng eventual consistency

Một pattern dễ sai:

~~~text
Search replica báo: còn 1 vé.
Checkout dựa ngay vào kết quả search để trả HELD.
Search replica chưa nhận event đã bán hết ở primary.
Hai khách cùng được hứa giữ vé cuối.
~~~

Cách phân biệt đúng:

~~~text
Search/Catalog: "có thể còn hàng" (ước tính, để khám phá)
Checkout: atomic check-and-reserve tại nguồn có thẩm quyền
Response:
  HELD hoặc REJECTED hoặc PENDING/UNKNOWN theo contract
~~~

Nếu tất cả conditional writes của stock pool được điều phối đúng trong một consistency boundary, dù UI stale thì checkout vẫn có thể từ chối yêu cầu không đủ hàng. Đây là sự tách **eventual read model** khỏi **strong business decision**.

Ngay cả khi Stock update là nguyên tử, Order/Reservation ở nhiều documents vẫn cần transaction hoặc durable workflow để tránh trạng thái đã trừ hàng mà chưa ghi hold. PACELC không thay thế thiết kế atomicity và idempotency.

## 29. Unknown commit outcome: đánh đổi A/C không giải quyết mọi lỗi client

Một request:

~~~text
Client -> Coordinator -> DB commit success
Client <-- X response lost

Client không biết commit thành công chưa.
~~~

Cần có:

- Business intent ID ổn định, ví dụ `reservationId=R1001`.
- Unique/conditional result ledger.
- Có cách đọc kết quả đã quyết định từ nguồn có thẩm quyền.
- Retry bounded backoff và không tạo intent ID mới.
- Trạng thái `UNKNOWN/PENDING_RECONCILIATION` khi cần.
- Compensation hoặc manual reconciliation khi external systems không rõ.

Một API “available” nhưng trả kết quả nhầm sau timeout không có giá trị. Không dùng timeout làm bằng chứng write đã rollback. Những guarantee này độc lập với nhãn PA/PC.

## 30. Cross-region latency không chỉ là vấn đề khoảng cách

RTT liên vùng đặt một giới hạn vật lý cho những giao thức phải trao đổi message trước khi commit. Nhưng còn:

- Số round trips của coordination protocol.
- Waiting for quorum, straggler replica hoặc leader transfer.
- Disk/journal sync và compaction.
- Shard fan-out, network congestion hoặc packet loss.
- TLS/session connection setup.
- Transaction retries, contention và queue.
- Request timeout/cancellation.
- Sự chồng lấp hay phụ thuộc giữa các bước.

Nếu ghi cần đợi một round trip liên vùng, không thể “tối ưu JSON serialization 1 ms” để xóa RTT đó. Câu hỏi tốt hơn: **Có cần global commit cho operation này không?** Nếu không, liệu có thể chuyển trách nhiệm sang local projection, session guarantee, quota escrow hoặc workflow có trạng thái trung gian không?

Cũng không nên cố loại bỏ mọi lượt phối hợp nếu việc đó làm mất invariant “không bán quá vé”. Hiệu năng phải được tối ưu trong **ràng buộc tính đúng đắn** đã định.

## 31. Tách consistency khỏi durability, backup và security

PACELC không bao quát mọi khía cạnh chất lượng:

| Thuộc tính | Câu hỏi |
|---|---|
| Consistency | Read nhìn version nào, các writes có thứ tự nào? |
| Durability | Write ACK sống qua loại crash nào? |
| Availability | Trong failure scenario, operation nào còn thành công? |
| Latency | p95/p99 end-to-end bao nhiêu? |
| Isolation | Hai transaction concurrent có thể tạo anomaly nào? |
| Security | Ai được đọc/ghi và khi quyền bị thu hồi có hiệu lực? |
| Recoverability | Có backup/PITR, restore RPO/RTO thế nào? |
| Cost | Network cross-region, index/replication/compute chi phí gì? |

Một replica đọc mới nhất nhưng chưa ghi bền có thể không đáp ứng yêu cầu durability. Một hệ có majority write nhưng cache quyền truy cập stale vẫn có thể vi phạm security. Một hệ có backup tốt nhưng mất vùng phải phục hồi nhiều giờ không đáp ứng availability SLO.

Cần xây một **ma trận thuộc tính**, không dùng PACELC như thay thế mọi quyết định hệ thống.

## 32. Failure contract theo từng endpoint

Một bảng mẫu cho cùng sản phẩm:

| Kịch bản | Catalog GET | Stock reserve POST | Order GET | Payment |
|---|---|---|---|---|
| Normal | Cache/replica, có freshness metadata | Commit điều kiện tại nguồn | Read-your-writes hoặc source | Provider idempotency |
| Secondary lag | Có thể vẫn trả stale | Không dùng secondary làm quyết định | Chờ version/fallback nếu cần | Không phụ thuộc secondary |
| Primary/quorum unavailable | Trả cached catalog nếu còn hợp lệ | Unavailable hoặc nhận PENDING không cam kết | Trả trạng thái cuối có nhãn freshness | Đối soát, không double charge |
| Region partition | Đọc cục bộ theo contract | Chỉ nơi có thẩm quyền cấp | Có thể delayed/partial | Không tự tạo charge mới |
| Response lost after commit | GET vẫn bình thường | Retry cùng business ID | Tra outcome | Query provider by attempt ID |
| Recovered link | Reconcile stale data | Hoàn tất intents pending theo thứ tự an toàn | Refresh projections | Đối soát callbacks |

Bảng này không chứng minh một topology cụ thể luôn đạt tất cả trạng thái, mà là **hợp đồng mong muốn để kiểm thử**. Nếu implementation không đáp ứng, cần thay thiết kế hoặc nêu giới hạn thay vì coi đó là bất ngờ production.

## 33. Quy trình ra quyết định PACELC từng bước

Thay vì chọn database ngay, đi từ câu hỏi đến một **hợp đồng đo được**:

~~~mermaid
flowchart TD
    A["Chọn một business operation"] --> B["Xác định invariant và data owner"]
    B --> C{"Nếu đọc bản cũ có gây sai nghiệp vụ?"}
    C -->|Có| D["Chọn freshness / consistency guarantee cụ thể"]
    C -->|Không| E["Chọn staleness budget có thể đo"]
    D --> F["Đặt SLO latency trong chế độ bình thường"]
    E --> F
    F --> G{"Nếu partition, tiếp tục thao tác có an toàn?"}
    G -->|Không| H["Fail closed / pending không cam kết"]
    G -->|Có| I["Serve local / conflict resolution có quy tắc"]
    H --> J["Kiểm thử concurrency, failover, lag và timeout"]
    I --> J
    J --> K["Quyết định topology, read/write config, cost"]
~~~

Quy trình có thể tóm gọn thành bốn quyết định:

1. **Safety:** điều gì tuyệt đối không được vi phạm?
2. **Freshness:** ai cần thấy dữ liệu mới tới mức nào?
3. **Failure behavior:** nếu không liên lạc được data owner, nhận gì và từ chối gì?
4. **Performance:** khi đã giữ đúng ba điều trên, còn budget latency/cost nào?

Cần diễn đạt rõ ràng khi có đánh đổi không thể giải quyết với điều kiện đã cho. Ví dụ yêu cầu “mọi region đều tiếp tục cấp duy nhất một vé cuối ngay khi partition, không có trao đổi và không có phân chia quyền trước” là tập yêu cầu mâu thuẫn trong mô hình phân tán phù hợp. Không nên hứa bằng cách thêm cache.

## 34. Mẫu phiếu quyết định kiến trúc

Có thể ghi mỗi operation thành một “decision record” nhỏ:

~~~yaml
operation: reserve-seat
owner: inventory-service
scope:
  aggregate: event-42/seat-A10
  regions: [region-a, region-b]
businessInvariant:
  - "Một seat ID chỉ có một reservation hợp lệ tại một thời điểm"
consistency:
  write: "Conditional commit tại owner hoặc protocol tương đương"
  read: "Display may be stale; checkout must revalidate"
latencySlo:
  healthyP95Ms: 250
  healthyP99Ms: 700
partitionBehavior:
  - "Không trả HELD nếu không xác minh được quyền cấp vé"
  - "Có thể trả PENDING nhưng không được nói đã giữ thành công"
retryContract:
  key: reservationId
  duplicate: "Replay stored outcome"
  unknownCommit: "Query outcome by reservationId"
observability:
  - "Oversell invariant violations"
  - "Reservation conflict rate"
  - "p95/p99 latency"
  - "Replica/read lag"
validation:
  - "Concurrent writes to final seat"
  - "Network partition"
  - "Commit-success-response-lost"
~~~

Đây là **YAML mẫu cho thảo luận**, không phải file cấu hình của một database. Các vùng, giá trị SLO và schema đều minh họa. Giá trị của bản ghi nằm ở chỗ người khác có thể hỏi “bảo đảm nào được kiểm tra ở đâu?” thay vì tranh luận bằng nhãn.

### 34.1. Câu hỏi reviewer nên đặt

- Invariant có nằm ở một owner hoặc protocol nào được triển khai thật không?
- Dữ liệu đã được replicate bất đồng bộ có làm caller quyết định sai không?
- Deadline cho request chờ consistency mạnh là bao nhiêu?
- Nếu không trả được thành công, caller có biết cách retry không?
- Retry có thể double-commit side effect ngoài database không?
- Một region có thể chuyển quyền owner khi mất mạng theo giao thức nào?
- Reconciliation sau partition có cần hủy lời hứa trước đó không?
- SLO latency đã bao gồm lỗi, cache miss, cross-region RTT và retry chưa?
- Có metric đủ để chứng minh staleness bound không?
- Có đường rollback/migration nếu lựa chọn này không đạt yêu cầu không?

## 35. Case study A — Profile vừa sửa nhưng replica còn cũ

**Yêu cầu:** người dùng bấm Save profile và mở ngay trang chi tiết; cần thấy tên mới. Những người khác có thể thấy tên cũ trong một thời gian rất ngắn.

### Hợp đồng gợi ý

- Write: trả success sau khi nguồn chuẩn xác nhận theo durability contract.
- Response chứa `version=42` hoặc session token phù hợp.
- GET ngay sau PUT trong cùng session: trả version ít nhất 42, hoặc chờ/fallback trong deadline.
- GET từ người khác: có thể trả replica local với freshness SLO đã công bố.
- Khi partition: vẫn có thể xem bản cached với nhãn phù hợp; sửa profile có thể bị từ chối khi thiếu nguồn có thẩm quyền.

### Những câu hỏi cần hỏi

1. Client có truyền causal/version token được không?
2. Replica local bắt kịp trong p99 bao nhiêu?
3. Khi replica không đạt version cần, fallback tới primary có ảnh hưởng SLO không?
4. Nếu failover, monotonic reads được duy trì theo session ra sao?
5. Nếu PUT timeout sau commit, API có tra được kết quả theo version/intent ID không?

Đây là ví dụ không cần yêu cầu **mọi người ở mọi region đọc linearizable** để bảo vệ trải nghiệm của chính người vừa sửa.

## 36. Case study B — Vé cuối cùng và yêu cầu không oversell

**Yêu cầu:** tổng số seat IDs hoặc quota cấp ra không vượt số lượng được bán.

### Bất biến

\[
\text{confirmed} + \text{held hợp lệ} \leq \text{capacity}
\]

Với vé có mã ghế duy nhất, còn cần uniqueness của `seatId` trong các reservation/confirmation hợp lệ.

### Đường ghi

~~~text
Client Reserve(seatId, reservationId)
  |
Authoritative conditional check
  |
Commit reservation + seat claim theo consistency boundary
  |
Trả HELD / REJECTED / PENDING theo trạng thái thật
~~~

**Câu hỏi PACELC:**

- Nếu mạng A–B bị chia cắt, cả hai có quyền cấp **cùng** seat A10 không? Nếu có thì ai ngăn trùng?
- Nếu nguồn có thẩm quyền ở A không reachable từ B, B có được cấp không, hay phải fail closed?
- Nếu muốn B vẫn phục vụ, có thể phân sẵn **những seat IDs không giao nhau** cho B không?
- Có chấp nhận chỉ trả PENDING để không hứa sai không?
- Đọc số lượng tồn trên UI có thể stale bao lâu, và checkout có revalidate không?

**Điểm mấu chốt:** UX vẫn có thể nhanh nhờ search/cache, nhưng lời hứa `HELD` phải được bảo vệ bằng một protocol đúng. CAP/PACELC mô tả trade-off; nó không thay thế transaction, idempotency và kiểm soát uniqueness.

## 37. Case study C — Analytics và bộ đếm có thể hội tụ

Giả sử dashboard hiển thị số lượt xem:

~~~text
Region A đếm 120 lượt trong partition.
Region B đếm 80 lượt trong partition.
Sau khi mạng phục hồi, cần tổng hợp hợp lệ.
~~~

Nếu nghiệp vụ cho phép kết quả hiển thị tạm cũ, có thể dùng counters/events được hợp nhất theo mô hình có chứng minh tính đúng. Ví dụ cùng một `viewEventId` được giao hai lần thì không nên đếm hai lần nếu metric cần exactly-once effect. Những bộ đếm gần đúng có thể công bố mức sai số chấp nhận được.

Câu hỏi:

- Chỉ cần xu hướng tương đối hay số liệu quyết toán?
- Dữ liệu có thể trễ tối đa bao lâu trong trạng thái khỏe?
- Khi partition, dashboard có được hiển thị số cũ với timestamp không?
- Nếu event được replay hoặc hai bên cùng tăng, merge bằng phép gì?
- Có cần watermark/chốt số liệu theo thời điểm?
- Kết quả này có được dùng để **quyết định thanh toán/quota** hay chỉ để quan sát?

Cùng một trường “count”, nhưng bộ đếm view và số dư tài khoản cần các hợp đồng khác hẳn. Tránh chọn AP/EL cho một **financial ledger** chỉ vì nó cũng là con số.

## 38. Case study D — Thu hồi quyền truy cập

**Yêu cầu:** quản trị viên thu hồi quyền của người dùng; các API nhạy cảm không được tiếp tục cho phép truy cập quá một khoảng chấp nhận được.

Một cache permission toàn cầu có thể đạt latency thấp, nhưng khi admin revoke, replica ở một vùng có thể chưa nhận event. Câu hỏi:

1. Đối với thao tác nào phải có enforcement gần như ngay lập tức?
2. Có cần kiểm tra permission version/token TTL ngắn tại nguồn mạnh hơn không?
3. JWT đã cấp có còn hiệu lực trong bao lâu?
4. Nếu policy store/quorum không reachable, API nhạy cảm **fail open** hay **fail closed**?
5. Nếu cho phép stale permissions 30 giây, tác hại tối đa là gì?
6. Đo propagation lag và các lần request dùng permission version cũ thế nào?

Không coi “đọc quyền truy cập từ cache rất nhanh” là đủ nếu yêu cầu bảo mật không cho stale authorization. Ngược lại, các hoạt động không nhạy cảm có thể chấp nhận trade-off khác. **Consistency cần phân loại theo mức độ rủi ro**, không chỉ read throughput.

## 39. Thực nghiệm: đo độ trễ và độ cũ lúc bình thường

Một môi trường lab có nguồn dữ liệu và replica/đường đọc khác nhau, với chính sách replication mà bạn có thể quan sát. Đừng suy từ tên chức năng rằng kết quả sẽ giống nhau trên mọi engine.

### 39.1. Chuẩn bị

- Tạo một record `profile:u42` chứa version tăng dần và giá trị mới.
- Có một writer nối tới nguồn được công bố là có thẩm quyền.
- Có hai readers: một đọc theo đường mạnh hơn, một đọc replica/đường eventual nếu hệ hỗ trợ.
- Dùng clock và tracing phù hợp để tương quan các request; tránh suy chính xác sub-ms từ đồng hồ giữa các máy chưa đồng bộ.
- Ghi setup: version database, topology, replication, consistency levels, read preference, vùng địa lý và tải nền.

### 39.2. Quy trình

1. Writer ghi version `v+1` và nhận ACK.
2. Ngay sau ACK, mỗi reader GET trong một vòng lặp có giới hạn.
3. Ghi version đọc được, latency, số lần stale và thời gian/điều kiện bắt kịp.
4. Lặp qua nhiều lần ở các mức tải khác nhau.
5. Với từng config, đo p50/p95/p99 read/write, stale-read rate và age/version lag.
6. Thêm điều kiện read-your-writes/session token nếu hỗ trợ, đo chi phí chờ/fallback.
7. Tách dữ liệu healthy, high-load và post-failover, không gộp thành một trung bình.

### 39.3. Metric cần báo cáo

| Metric | Diễn giải |
|---|---|
| Read p95/p99 | Độ trễ reader cảm nhận |
| Write p95/p99 | Độ trễ đến mốc ACK được quy định |
| Stale read fraction | Bao nhiêu lượt đọc không thấy version kỳ vọng |
| Observed version lag | Chênh lệch version theo cùng record |
| Age of last applied update | Độ cũ theo nguồn thời gian đáng tin |
| Read-your-writes failures | Vi phạm session contract |
| Retry/timeout | Tải bổ sung hoặc kết quả không rõ |
| Cross-region bytes | Chi phí dữ liệu qua vùng |

**Mục tiêu** là vẽ một đường đánh đổi giữa latency và freshness theo config thật, không phải chứng minh trước rằng mạnh hơn lúc nào cũng chậm hơn chính xác một tỷ lệ cố định.

## 40. Thực nghiệm network partition và phục hồi

Chỉ thực hiện trong **môi trường thử nghiệm có quyền gây gián đoạn**, không tự tạo partition ở production. Có thể dùng network fault injection hoặc thao tác ngắt replica theo công cụ phù hợp với hệ.

~~~text
T0: Các replica đồng bộ.
T1: Tách nhóm node A và B không trao đổi được.
T2: Gửi read/write ở cả A và B.
T3: Ghi tất cả response: HELD/PENDING/ERROR/STALE.
T4: Phục hồi kết nối.
T5: Theo dõi recovery, merge, replication, reconciliation.
T6: Kiểm tra invariants và dữ liệu cuối.
~~~

Những câu hỏi kiểm thử:

- Phía không có thẩm quyền có trả lỗi/đợi như thiết kế không?
- Phía có quorum/owner còn commit được không?
- Các GET stale có được đánh dấu freshness không?
- Có hai commit xung đột cho cùng seat ID không?
- Nếu viết ở cả hai phía được cho phép, merge policy có bảo toàn data semantics không?
- Có request timeout nhưng đã commit không? Client dùng business ID xác minh thế nào?
- Sau khi mạng lành, dữ liệu có hội tụ theo model được công bố không?
- Compaction/repair/replay có làm p99 tăng, và có được tính trong SLO không?
- Khi failover leader, owner epoch/fencing có ngăn node cũ ghi sai không?

Khi đánh giá kết quả, **tách business safety, consistency, availability và latency**. Một hệ từ chối tất cả writes có thể giữ safety nhưng không đạt availability mục tiêu; một hệ trả 200 rất nhanh nhưng cấp trùng vé không đáp ứng correctness.

## 41. Cách hỏi product team để làm rõ đánh đổi

Một yêu cầu thường xuất hiện:

> “Hệ thống phải luôn hoạt động, phản hồi tức thì và mọi người luôn nhìn cùng một dữ liệu.”

Nếu không làm rõ, đội kỹ thuật có thể chọn replication/consistency sai hoặc hứa một SLO không khả thi dưới partition. Hãy chuyển yêu cầu thành hội thoại cụ thể.

**Product:** “Khách cần thấy số vé còn lại ngay.”

**Kỹ thuật:** “Ý là số vé hiển thị trên trang có thể chậm 1–5 giây, hay khi nhấn giữ vé phải biết chắc còn vé?”

**Product:** “Danh sách có thể trễ, nhưng đã bấm giữ thành công thì không được cấp trùng.”

**Kỹ thuật:** “Nếu region của khách không liên lạc được nguồn xác nhận, có được hiển thị PENDING hoặc thông báo thử lại không?”

**Product:** “Được, miễn không báo đã giữ nếu chưa chắc.”

**Kỹ thuật:** “SLO khi khỏe là p95 200 ms hay p99 1 giây? Có cần mọi region đọc trạng thái HELD tức thì hay chỉ người vừa giữ?”

**Product:** “Người vừa giữ phải thấy ngay; người khác có thể đợi cập nhật.”

Khi đó ta có contract:

~~~text
Catalog/availability preview:
  eventual, có thể stale trong phạm vi SLO

Reserve decision:
  conditional commit, không oversell
  nếu không xác minh được -> PENDING hoặc unavailable

Same-user Order status:
  read-your-writes / query authoritative outcome

Operational target:
  đo p95/p99 ở healthy và failure scenario riêng
~~~

Câu hỏi tốt không bắt đầu bằng “Anh/chị muốn CP hay AP?”, vì người phụ trách sản phẩm không nhất thiết biết thuật ngữ. Nó bắt đầu bằng **hậu quả khi sai, thời gian được chấp nhận và hành vi khi không thể xác minh**.

## 42. Những câu hỏi để phỏng vấn/thiết kế hệ thống

Hãy dùng mẫu này khi đánh giá một yêu cầu NoSQL:

### Về dữ liệu và bất biến

1. Đâu là nguồn dữ liệu có thẩm quyền?
2. Khóa/record nào quyết định invariant?
3. Một update có chạm nhiều partition/service không?
4. Nếu hai người cùng ghi, kết quả nào là hợp lệ?
5. Có thể merge những update đó bằng toán tử có tính giao hoán/kết hợp không?
6. “Đã thành công” có nghĩa commit, accept intent hay hoàn thành workflow?

### Về consistency/freshness

7. Người vừa ghi có phải đọc thấy ngay không?
8. Hai session khác nhau có phải thấy cùng version tại cùng thời điểm không?
9. Có thể đọc snapshot trễ bao lâu khi hệ khỏe?
10. Có bắt buộc monotonic reads khi client đổi vùng không?
11. Có quan hệ nhân quả giữa các event cần giữ không?
12. Khi version chưa tới replica, caller chờ hay đọc nguồn khác?

### Về latency/cost

13. p95/p99 SLO cho mỗi operation là gì?
14. Khách và data owner ở vùng nào?
15. Những bước nào có cross-region RTT?
16. Đọc/ghi có đợi quorum/leader/log sync không?
17. Cache hit/miss, fan-out và retries ảnh hưởng tail latency thế nào?
18. Có thể dùng projection bất đồng bộ mà vẫn bảo vệ invariant không?

### Về partition/failover

19. Hai nhóm node không liên lạc thì phía nào có quyền ghi?
20. Một request không thể commit được trả mã/trạng thái nào?
21. Có chấp nhận PENDING thay vì SUCCESS tức thời không?
22. Nếu hai phía cùng nhận ghi, conflicts được merge/compensate thế nào?
23. Khi owner cũ hồi phục, làm sao tránh stale writer?
24. Client timeout sau commit thì tra outcome bằng key nào?

### Về khả năng kiểm chứng

25. Metric nào đo stale read, replica lag, p99, conflict và invariant violations?
26. Fault injection nào chứng minh điều đã hứa?
27. RPO/RTO và restore có tách khỏi consistency contract không?
28. Khi dữ liệu không thể xác định, ai vận hành reconciliation?
29. Có tài liệu contract API để client biết cách retry/fallback không?
30. Những giả định nào khiến quyết định phải xem lại khi scale/đổi vùng?

Các câu trả lời thường đáng giá hơn một bảng xếp hạng sản phẩm theo “strong/eventual”.

## 43. Các hiểu nhầm cần tránh

| Hiểu nhầm | Vì sao sai | Cách tiếp cận |
|---|---|---|
| “CAP bắt buộc chọn hai trong ba mọi lúc” | Trade-off A/C nổi bật khi partition xảy ra | Xác định failure scenario và operation |
| “P có thể bỏ đi vì mạng tốt” | Partition vẫn có thể xảy ra | Thiết kế phân vùng và recovery |
| “PACELC là tên consistency level của DB” | Đây là framework đánh đổi | Đọc guarantee theo API/config |
| “E là eventual consistency” | E = Else | Xét vận hành bình thường |
| “C trong CAP giống ACID C” | Khác định nghĩa | Nêu linearizability và invariant riêng |
| “Hệ CP thì mọi GET đều chậm” | Đường đọc/leader/cache/config khác nhau | Đo theo workload |
| “Hệ AP thì không thể giữ invariant nào” | Có thể giữ invariant cục bộ/escrow | Xác định phạm vi và giao thức |
| “Eventual nghĩa chắc chắn trễ dưới 1 giây” | Không tự có bound | Đo lag và công bố SLO |
| “Quorum R+W>N bảo đảm linearizable mọi nơi” | Cần thêm giả định và protocol | Dùng contract engine |
| “Majority write thì secondary read luôn mới ngay” | Replication/read mode có thể khác | Chọn đường đọc theo nhu cầu |
| “Read-your-writes nghĩa mọi session đều linearizable” | Bảo đảm session hẹp hơn | Dùng token/owner theo scope |
| “Latency trung bình thấp là đủ” | p99 có thể lớn lúc conflict/failover | Đo percentile |
| “Replica gần user luôn có dữ liệu mới nhất” | Propagation lag vẫn xảy ra | Freshness metadata/version |
| “Nếu API trả 200 là available và correct” | Có thể trả stale/sai business invariant | Kiểm tra outcome |
| “Cache có thể làm checkout bảo đảm không oversell” | Cache không phải nguồn quyết định | Conditional write ở owner |
| “Timeout nghĩa DB chưa commit” | ACK có thể mất sau commit | Idempotency/outcome query |
| “Conflict merge luôn sửa được hậu quả” | Lời hứa cấp vé/thu tiền có thể không merge được | Domain safety trước khi commit |
| “Strong consistency tự cho durability và backup” | Đây là thuộc tính khác | Đặt write concern/RPO/RTO riêng |
| “Một database nên có cùng consistency mode cho mọi API” | Dữ liệu khác rủi ro và SLA | Quyết định theo operation |
| “Muốn nhanh phải bỏ hết consistency” | Có thể dùng session guarantees, projections, escrow | Tối ưu trong invariant |
| “Global active-active luôn nhanh và không conflict” | Multi-writer cần ordering/merge | Mô tả conflict protocol |
| “Mọi loại failure đều là CAP partition” | Có cả overload, GC, client timeout | Phân loại failure và test |

## 44. Bài tập thực hành A — Phân tích PACELC từ các yêu cầu

Một ứng dụng có bốn API:

~~~text
GET /products/search
GET /orders/{id}
POST /seats/{id}/reserve
GET /analytics/views
~~~

Yêu cầu giả định:

- Search được phép chậm cập nhật 30 giây.
- Người vừa tạo Order phải đọc thấy trạng thái của chính mình.
- Không một seat ID nào được xác nhận giữ cho hai Reservation.
- Analytics có thể chậm 5 phút nhưng cần hiển thị watermark.
- Ở tình huống một region mất liên lạc, trang catalog vẫn cần xem được.

Hãy hoàn thành bảng:

| API | Consistency cụ thể | Latency SLO giả định | Partition behavior | Source of truth | Cách đo |
|---|---|---|---|---|---|
| Search | Tự điền | Tự điền | Tự điền | Tự điền | Tự điền |
| Order GET | Tự điền | Tự điền | Tự điền | Tự điền | Tự điền |
| Reserve | Tự điền | Tự điền | Tự điền | Tự điền | Tự điền |
| Analytics | Tự điền | Tự điền | Tự điền | Tự điền | Tự điền |

Đề xuất ba thiết kế khác nhau: (1) chỉ có một vùng ghi, (2) có replicas đọc toàn cầu, (3) có phân bổ seat IDs/escrow theo vùng. Với mỗi thiết kế, chỉ rõ thứ gì nhanh hơn, thứ gì không còn đảm bảo lúc partition và công việc recovery nào cần có.

## 45. Bài tập thực hành B — Sự cố partition và quan sát

Giả sử cụm có ba replicas A, B, C. Một thí nghiệm **theo mô hình giản lược** sử dụng `N=3` và quy tắc đọc/ghi R/W với cùng tập replica; không coi đây là mô tả một engine thực.

1. Tính giao nhau lý thuyết khi `R=2, W=2`.
2. So với `R=1, W=1`.
3. Nếu B và C bị cách ly khỏi A, ở phía nào có thể hoàn tất request theo các quorums được chọn?
4. Vì sao có quorum giao nhau không đủ tự chứng minh linearizability?
5. Nếu một write ở A trả timeout sau khi commit, client cần làm gì?
6. Khi phục hồi kết nối, cần kiểm tra những versions/replication lag nào?
7. Thêm một yêu cầu “không bán quá một vé” vào hệ: chỉ điều chỉnh R/W có đủ bảo đảm transactional invariant không?
8. Nếu chấp nhận PENDING ở phía thiếu quorum, API cần thay response semantics ra sao?

**Yêu cầu bài làm:** tách câu trả lời theo consistency, availability, latency, durability và business safety; không chỉ kết luận “CP” hay “AP”.

## 46. Bài tập thực hành C — Viết quyết định kiến trúc

Một công ty muốn chạy hệ thống nhiều vùng địa lý. Giao diện có thể đọc cache nhưng các thao tác chuyển quyền sở hữu tài nguyên phải có tính đúng đắn mạnh.

Hãy viết một Architecture Decision Record gồm:

- **Context:** vị trí users, số vùng, dữ liệu cần đồng bộ, workload đọc/ghi.
- **Decision:** nguồn chuẩn, đường đọc/ghi, consistency mode và partition behavior.
- **Rejected options:** ví dụ cho tất cả regions cùng ghi không có conflict protocol.
- **SLO:** p95/p99, freshness, pending age và lỗi được phép.
- **Safety invariant:** những điều không được vi phạm dù có timeout/failover.
- **Retry contract:** business ID, idempotency, unknown commit.
- **Validation:** test concurrency, lag, network isolation, owner failover, recovery.
- **Rollback:** cách trở lại một vùng ghi hoặc đổi read preference khi SLO không đạt.

Sau đó giải thích vì sao “dùng database nhanh nhất” không phải một tiêu chí đủ để chấp nhận quyết định.

## 47. Câu hỏi tự kiểm tra

1. PACELC giải quyết thiếu sót nào trong thảo luận chỉ dùng CAP?
2. P, A, C, E, L là viết tắt của những gì?
3. C trong CAP khác ACID consistency ra sao?
4. Vì sao không thể tùy ý bỏ tình huống network partition?
5. Nhánh “Else” của PACELC áp dụng khi nào?
6. PA và PC mô tả hành vi nào khi partition?
7. EL và EC mô tả xu hướng nào trong vận hành bình thường?
8. Vì sao không nên gắn một nhãn PACELC bất biến cho toàn bộ database?
9. Linearizability yêu cầu gì khi GET bắt đầu sau một PUT đã hoàn tất?
10. Serializability và strict serializability có giống linearizability không?
11. Read-your-writes khác yêu cầu global linearizability ở đâu?
12. Eventual consistency có tự giới hạn stale dưới một số giây không?
13. Khi nào bounded staleness có ý nghĩa hơn eventual chung chung?
14. Vì sao replica local có thể nhanh nhưng stale?
15. Vì sao một read leader ở vùng xa có thể tăng p99?
16. Công thức `R+W>N` cho biết gì và chưa chứng minh điều gì?
17. Majority ACK liên quan thế nào tới durability?
18. GSI và bảng gốc có thể có consistency contract khác nhau không?
19. Redis atomic command có tự bảo vệ read freshness trên replicas không?
20. Vì sao search result không được là nguồn chốt vé cuối?
21. Khi partition, có được trả PENDING thay vì HELD không?
22. Nếu cho cả hai vùng nhận ghi, cần conflict resolution/fencing ở đâu?
23. CRDT hợp với loại dữ liệu nào nhưng không tự bảo vệ invariant gì?
24. Escrow quota giúp giảm cross-region coordination bằng cách nào?
25. p95/p99, stale-read rate và version lag cần được đo cùng nhau vì sao?
26. Timeout sau commit có nghĩa write chắc chắn không xảy ra không?
27. Đọc sau ghi của cùng user có thể được xử lý bằng session token ra sao?
28. Tại sao availability của catalog khác availability của checkout?
29. Một yêu cầu “nhanh và mới” cần bổ sung những tham số nào?
30. Vì sao PACELC không thay thế security, backup và RPO/RTO?

## 48. Tổng kết: PACELC là cách hỏi, không phải khẩu hiệu phân loại

**CAP** giúp ta không bỏ qua sự thật rằng phân vùng mạng có thể xảy ra và một hệ phân tán phải chọn phản ứng phù hợp trước xung đột giữa availability và consistency mạnh. **PACELC** đi tiếp: ngay cả khi mạng hoạt động bình thường, ứng dụng vẫn có thể đánh đổi **latency** để nhận được mức consistency cần thiết.

Bài học quan trọng nhất là **hỏi theo business operation**, không phải chọn một nhãn CP/AP cho toàn hệ. Hãy xác định nguồn có thẩm quyền, invariant, yêu cầu freshness, deadline, p95/p99 SLO, quyền ghi khi partition, hợp đồng khi timeout và cách kiểm chứng bằng test.

Khi catalog, search, analytics, profile, stock và payment có những rủi ro khác nhau, chúng có thể cần các đường đọc/ghi khác nhau. Một đường đọc eventual nhanh cho discovery có thể hoàn toàn phù hợp nếu checkout vẫn dùng conditional commit bảo vệ kho. Một API giữ vé không thể hứa thành công trên hai vùng bị chia cắt nếu không có protocol cấp quyền an toàn.

Câu hỏi quyết định là: **“Nếu phải chọn giữa chờ thêm để biết chắc, trả nhanh với dữ liệu có thể cũ, hoặc từ chối khi không có thẩm quyền, chính xác thao tác nào được phép đánh đổi điều gì, trong bao lâu, và chúng ta đo/bảo vệ kết quả đó bằng cách nào?”** Trả lời được câu này là đã dùng PACELC đúng mục đích để thiết kế NoSQL có tính đúng đắn, khả năng vận hành và trải nghiệm phù hợp.









