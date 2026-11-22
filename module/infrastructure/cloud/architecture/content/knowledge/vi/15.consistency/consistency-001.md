# Nhất quán mạnh, nhất quán cuối cùng và yêu cầu nghiệp vụ

Trong hệ thống phân tán, cùng một dữ liệu có thể được lưu ở nhiều node, database replica, cache hoặc region. Khi một người dùng cập nhật dữ liệu, các bản sao không nhất thiết nhìn thấy thay đổi cùng một thời điểm. Một request đọc ngay sau đó có thể nhận giá trị mới, giá trị cũ hoặc một kết quả được ghép từ nhiều phiên bản. Đây là bài toán **tính nhất quán (consistency)**.

Chọn mô hình nhất quán không đơn thuần là chọn database có tốc độ nhanh. Đó là quyết định về **những gì nghiệp vụ cho phép người dùng quan sát, các bất biến nào phải luôn được bảo vệ và hệ thống được phép phản ứng ra sao khi mạng bị phân vùng hoặc một replica chậm**. Một ứng dụng đặt chỗ có thể chấp nhận số lượt xem tăng chậm vài giây, nhưng không thể tùy tiện xác nhận hai khách hàng cùng giữ một chỗ duy nhất.

Trong module **CLOUD_ARCHITECTURE**, bài học này kết nối thiết kế dữ liệu với độ tin cậy, hiệu năng, bảo mật, chi phí và vận hành theo tư duy Well-Architected. Trọng tâm là phân biệt **nhất quán mạnh (strong consistency)** với **nhất quán cuối cùng (eventual consistency)**, hiểu các mức bảo đảm trung gian và ánh xạ chúng vào yêu cầu nghiệp vụ.

## 1. Tính nhất quán có nghĩa gì?

Ở mức khái quát, consistency mô tả những kết quả đọc/ghi mà hệ thống cho phép người dùng quan sát khi dữ liệu được cập nhật, sao chép hoặc truy cập đồng thời. Nhưng từ "consistency" có nhiều nghĩa:

| Ngữ cảnh | Ý nghĩa |
| --- | --- |
| **Consistency trong ACID** | Một transaction đưa database từ trạng thái hợp lệ sang trạng thái hợp lệ theo các constraint và quy tắc được định nghĩa |
| **Consistency model của hệ phân tán** | Quy định quan hệ giữa thao tác đọc/ghi trên nhiều replica hoặc node |
| **Eventual consistency** | Nếu không có cập nhật mới và việc truyền thông tin tiếp tục thành công, các replica cuối cùng hội tụ về cùng trạng thái |
| **Strong consistency / linearizability** | Mỗi thao tác có thể được xem như xảy ra tại một thời điểm duy nhất giữa lúc bắt đầu và hoàn tất, đồng thời tôn trọng thứ tự thời gian thực của các thao tác đã hoàn thành |
| **Causal consistency** | Các thao tác có quan hệ nhân quả được quan sát theo thứ tự tương ứng; các thao tác không có quan hệ nhân quả có thể được quan sát theo thứ tự khác |

Không nên đồng nhất consistency trong ACID với strong consistency giữa nhiều region. Một database đơn node có transaction ACID vẫn có thể có cache hoặc read replica trả dữ liệu cũ. Ngược lại, một hệ thống replica mạnh có thể cung cấp linearizable read/write cho một key nhưng không bảo đảm một chuỗi cập nhật nhiều bảng là một transaction ACID.

### Ví dụ đơn giản

Một tài khoản có số dư 1.000.000 đồng. Người dùng chuyển 200.000 đồng:

1. Hệ thống ghi số dư mới 800.000 đồng.
2. Một bản sao đọc ở region khác chưa nhận bản cập nhật và trả 1.000.000 đồng.
3. Người dùng thấy số dư cũ dù giao dịch đã báo thành công.

Với một ứng dụng hiển thị báo cáo chậm vài giây, điều đó có thể chấp nhận được. Với thao tác cho phép chi tiêu, trả lại số dư cũ có thể dẫn đến quyết định sai. Mô hình nhất quán cần được chọn theo **ý nghĩa của dữ liệu và hành động dựa trên dữ liệu đó**.

## 2. Strong consistency và eventual consistency

### Nhất quán mạnh

Strong consistency thường được dùng để mô tả bảo đảm mạnh như linearizability: sau khi một thao tác ghi thành công, các lần đọc bắt đầu sau đó nhìn thấy thao tác ghi đó (hoặc một giá trị mới hơn), theo một thứ tự toàn cục phù hợp với thời gian thực.

Ví dụ, một giao dịch giữ chỗ được xác nhận thành công. Một request tra cứu bắt đầu sau thời điểm xác nhận cần nhìn thấy chỗ đó đã được giữ. Điều này giúp các client không đưa ra quyết định dựa trên trạng thái cũ đối với dữ liệu quan trọng.

Lợi ích:

- Dễ suy luận về thứ tự đọc/ghi và xây dựng invariant nghiệp vụ.
- Giảm tình huống client đọc lại ngay sau write nhưng nhận kết quả cũ.
- Phù hợp với thao tác cần quyết định dựa trên trạng thái mới nhất, như phân bổ tài nguyên duy nhất hoặc ghi sổ giao dịch.

Đánh đổi:

- Có thể cần phối hợp giữa replica/quorum, làm tăng latency.
- Khi network partition hoặc không đủ replica cần thiết, hệ thống có thể từ chối hoặc chờ một số thao tác để giữ bảo đảm.
- Strong consistency trên nhiều region có thể chịu ảnh hưởng rõ bởi khoảng cách mạng và thời gian round trip.
- Chi phí vận hành, capacity và thiết kế failover có thể cao hơn.

### Nhất quán cuối cùng

Eventual consistency cho phép các bản sao tạm thời khác nhau. Hệ thống truyền thay đổi bất đồng bộ, rồi các replica hội tụ khi quá trình đồng bộ hoàn tất và không có cập nhật mới cạnh tranh.

Ví dụ, người dùng đổi ảnh đại diện. API lưu thông tin mới vào nguồn dữ liệu, sau đó event cập nhật cache và search index. Trong vài giây đầu, một số trang có thể vẫn hiển thị ảnh cũ. Nếu nghiệp vụ chấp nhận độ trễ đó, không cần chờ tất cả projection cập nhật xong mới trả thành công.

Lợi ích:

- Giảm thời gian chờ đồng bộ giữa các thành phần và region.
- Duy trì khả năng tiếp nhận một số loại cập nhật khi kết nối với replica khác không sẵn sàng.
- Phù hợp với projection, cache, analytics, feed, search index và dữ liệu có thể tái tạo.

Đánh đổi:

- Client có thể đọc giá trị cũ sau khi ghi.
- Nhiều thao tác đồng thời có thể tạo xung đột hoặc thứ tự khác nhau.
- Cần giải quyết duplicate, out-of-order event, retry, replay và reconcile.
- Ứng dụng phải diễn đạt trạng thái đang đồng bộ hoặc dữ liệu có thời điểm cập nhật.

### So sánh nhanh

| Tiêu chí | Strong consistency | Eventual consistency |
| --- | --- | --- |
| Đọc ngay sau ghi | Theo bảo đảm mạnh có thể thấy write đã xác nhận | Có thể thấy giá trị cũ trong thời gian hội tụ |
| Phối hợp replica | Thường cần coordination/quorum theo mô hình | Có thể truyền bất đồng bộ |
| Latency | Có thể cao hơn, nhất là liên vùng | Thường giảm thời gian chờ trên đường ghi |
| Khả năng ghi khi partition | Có thể hạn chế ở một số mô hình | Có thể chấp nhận ghi cục bộ nếu quy tắc xung đột cho phép |
| Xử lý xung đột | Có thể tránh một số xung đột bằng serialization/locking | Cần merge, versioning, conflict policy hoặc chấp nhận ghi đè |
| Use case | Số dư, reservation, uniqueness, quyền truy cập quan trọng | Feed, search projection, analytics, cache, view tổng hợp |

Không nên coi hai lựa chọn là một công tắc cho toàn hệ thống. Một sản phẩm thường cần **strong consistency ở nơi bảo vệ invariant**, đồng thời dùng eventual consistency cho các bản chiếu và chức năng phụ.

## 3. Các bảo đảm trung gian: read-your-writes, monotonic reads và causal consistency

Strong và eventual không phải toàn bộ không gian mô hình nhất quán. Nhiều hệ thống cung cấp hoặc cần các bảo đảm theo phiên và theo quan hệ nhân quả.

| Bảo đảm | Ý nghĩa | Ví dụ trải nghiệm |
| --- | --- | --- |
| **Read-your-writes** | Một client sau khi ghi thành công sẽ thấy ghi của chính mình ở những lần đọc sau theo phạm vi đã cam kết | Người dùng vừa đổi tên hồ sơ rồi tải lại vẫn thấy tên mới |
| **Monotonic reads** | Một client không quan sát dữ liệu quay ngược về phiên bản cũ hơn trong cùng phiên | Sau khi đã thấy trạng thái đơn là "đang giao", không quay về "đã xác nhận" |
| **Monotonic writes** | Các ghi của cùng một client được áp dụng theo thứ tự đã gửi | Thay đổi địa chỉ rồi cập nhật hướng dẫn giao hàng không bị đảo thứ tự |
| **Causal consistency** | Nếu thao tác B phụ thuộc vào A, người quan sát không thấy B trước khi thấy A | Bình luận trả lời chỉ xuất hiện sau bài viết gốc |
| **Session consistency** | Kết hợp một số bảo đảm nhất quán trong phạm vi phiên người dùng | Một phiên đọc thấy các cập nhật trước đó của chính phiên |

Các tên gọi và mức bảo đảm có thể khác nhau giữa database/cache/framework. Phải xem contract chính xác: phạm vi một key, một transaction, một session, một client hay toàn cluster.

### Ví dụ read-your-writes

Người dùng sửa hồ sơ qua API ở region A. Write thành công ở primary, nhưng request tải lại được route tới read replica ở region B còn trễ. Người dùng thấy tên cũ và nghĩ thao tác không được lưu.

Một số cách xử lý:

- Sau write, giữ sticky routing tới primary trong một khoảng thời gian phù hợp.
- Trả version/commit token để lần đọc sau yêu cầu replica đạt ít nhất version đó.
- Tạm đọc từ nguồn mạnh hơn cho chính client đó.
- Cập nhật UI từ response write và hiển thị trạng thái đồng bộ nếu projection còn trễ.

Mỗi cách có chi phí và giới hạn khác nhau. Sticky session có thể làm giảm khả năng cân bằng tải; đọc primary tăng tải; token cần được hỗ trợ xuyên suốt query layer.

## 4. Không nhầm consistency với availability và durability

Ba thuộc tính có liên quan nhưng trả lời các câu hỏi khác nhau:

- **Consistency:** các thao tác đọc/ghi được phép quan sát theo quy tắc nào?
- **Availability:** hệ thống có trả lời yêu cầu trong thời hạn xác định hay không?
- **Durability:** dữ liệu đã được xác nhận có được bảo toàn sau những loại sự cố đã định hay không?

Một database có thể có strong consistency nhưng từ chối ghi khi không đủ quorum. Một store eventual consistency có thể nhận ghi ở nhiều nơi trong partition, nhưng cần reconcile sau đó. Một lần write được trả success nhưng không có durability phù hợp vẫn có thể mất sau crash nếu cấu hình commit/replication không đạt yêu cầu.

Vì vậy, không nên nói "strong consistency nghĩa là dữ liệu không bao giờ mất" hoặc "eventual consistency nghĩa là database luôn sẵn sàng". Cần mô tả riêng semantics đọc/ghi, availability mục tiêu và durability/backup.

## 5. CAP theorem: hiểu đúng khi mạng bị phân vùng

CAP là một cách nhìn về hệ thống phân tán khi xảy ra **network partition**:

- **Consistency (C)** trong phát biểu CAP thường gần với linearizability: mọi node hoạt động như một bản sao dữ liệu đơn nhất.
- **Availability (A)** là mọi request tới node không lỗi đều nhận được response hợp lệ (không nhất thiết là giá trị mới nhất).
- **Partition tolerance (P)** là hệ thống tiếp tục được xem xét trong điều kiện mạng bị chia cắt khiến các node không thể trao đổi thông tin.

Khi partition xảy ra, một hệ thống không thể đồng thời bảo đảm cả strong consistency theo nghĩa linearizability và availability cho mọi request ở mọi phía của partition. Nó phải chọn một số thao tác chờ/từ chối để giữ consistency, hoặc tiếp tục trả lời với khả năng các phía có trạng thái khác nhau.

~~~mermaid
flowchart TD
    P["Network partition xảy ra"]
    P --> DEC{"Ưu tiên nào cho thao tác?"}
    DEC -->|Giữ linearizability| C["Chờ / từ chối một số request\nđể không trả dữ liệu mâu thuẫn"]
    DEC -->|Tiếp tục trả lời| A["Có thể nhận dữ liệu cục bộ\nvà xử lý reconcile sau"]
~~~

CAP **không** có nghĩa một hệ thống chọn đúng hai trong ba chữ C, A, P trong mọi tình huống. Partition tolerance là điều kiện thực tế mà hệ thống phân tán phải tính đến; lựa chọn đáng quan tâm là hành vi của từng thao tác khi partition xảy ra. Khi mạng bình thường, thiết kế vẫn có thể tối ưu cả consistency và availability theo những cách khác nhau.

CAP cũng không thay thế các quyết định về latency, durability, transaction isolation, backup hoặc chất lượng dữ liệu. Không nên dùng nhãn CP/AP đơn lẻ để đánh giá một database mà không nói rõ thao tác, failure mode và semantics.

## 6. PACELC: đánh đổi cả khi mạng bình thường

PACELC mở rộng cách thảo luận CAP bằng cách hỏi thêm: **nếu không có partition, hệ thống vẫn phải đánh đổi gì giữa latency và consistency?**

- Khi có **P** (partition), hệ thống thường phải chọn giữa **A** (availability) và **C** (consistency).
- **E** (else), khi không có partition, hệ thống thường đánh đổi **L** (latency) và **C** (consistency).

Ví dụ, một lần ghi được yêu cầu xác nhận sau khi nhiều replica đã nhận dữ liệu có thể nhất quán mạnh hơn, nhưng cần chờ round trip. Một lần ghi chỉ chờ local replica có thể nhanh hơn, nhưng các replica khác nhìn thấy chậm. PACELC là khung tư duy, không phải nhãn phân loại đầy đủ cho mọi dịch vụ.

### Vì sao multi-region thường làm lộ rõ đánh đổi?

Khoảng cách địa lý làm tăng thời gian truyền thông. Nếu mỗi transaction phải chờ một quorum trải trên nhiều region, p95/p99 write latency có thể tăng. Nếu ghi tại một region rồi sao chép bất đồng bộ, người dùng ở region khác có thể đọc trạng thái cũ. Thiết kế cần trả lời:

- Người dùng có cần đọc ngay dữ liệu vừa ghi không?
- Có thể route người dùng về region sở hữu dữ liệu không?
- Region phụ có thể phục vụ read-only khi mất kết nối không?
- Khi region mất, dữ liệu chưa sao chép được xử lý thế nào?
- Có yêu cầu dữ liệu nằm trong một khu vực cụ thể không?

Không có lựa chọn "multi-region luôn tốt hơn". Với một số nghiệp vụ, single-writer theo region cộng read projection ở nơi khác đơn giản và an toàn hơn active-active multi-writer.

## 7. Replication, quorum và ý nghĩa xác nhận ghi

Replication tạo nhiều bản sao để tăng khả năng đọc, độ tin cậy hoặc khả năng phục hồi. Nhưng **có bao nhiêu replica không nói lên chính xác write đã được bảo đảm tới đâu**. Phải hiểu replica nào được xác nhận, replication đồng bộ hay bất đồng bộ, và điều gì xảy ra khi một node/region mất kết nối.

### Synchronous và asynchronous replication

| Cách sao chép | Khi nào write được xác nhận? | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| **Synchronous** | Theo contract, chờ một hoặc nhiều replica xác nhận trước khi trả thành công | Giảm khả năng mất các ghi đã xác nhận trong failure mode được thiết kế | Thêm round trip, phụ thuộc replica/quorum; có thể từ chối ghi khi không đủ thành phần |
| **Asynchronous** | Primary xác nhận trước khi bản sao nhận thay đổi | Giảm latency của write và giảm phụ thuộc tức thời vào replica xa | Replica lag; failover có thể mất các ghi chưa sao chép |
| **Semi-synchronous / quorum-based** | Chờ số thành viên hoặc điều kiện xác nhận nhất định | Cân bằng giữa độ trễ và bảo vệ dữ liệu theo cấu hình | Cần hiểu chính xác điều kiện quorum, member voting và tình huống mất node |

Tên gọi không bảo đảm giống nhau giữa các sản phẩm. Có hệ thống "synchronous" chờ flush log tới disk; hệ thống khác chờ replica nhận hoặc commit. Hãy kiểm tra rõ điểm nào được xác nhận: received, written, flushed hay committed.

### Quorum đọc/ghi

Trong một số hệ thống replicated key-value store, quorum được mô hình hóa bằng:

- \(N\): số replica lưu một key.
- \(W\): số replica cần xác nhận một lần ghi.
- \(R\): số replica được hỏi trong một lần đọc.

Nếu \(R+W>N\), tập replica được đọc và tập replica xác nhận ghi có giao nhau theo mô hình đơn giản. Nếu \(W>N/2\), hai tập ghi quorum cũng giao nhau. Tuy nhiên, **điều kiện giao nhau không tự chứng minh linearizability**: còn phụ thuộc versioning, thứ tự ghi, read repair, hinted handoff, sloppy quorum, concurrent write và thuật toán đồng thuận.

Ví dụ \(N=3, W=2, R=2\) cho thấy số replica tối thiểu tham gia. Nhưng nếu replica chưa đồng bộ, client đọc hai bản có version khác nhau và hệ thống chọn giá trị theo timestamp không đáng tin, kết quả vẫn có thể sai với invariant nghiệp vụ. Cần xem consistency semantics của engine thay vì suy luận chỉ từ ba con số.

### Read repair và anti-entropy

Một số hệ thống phát hiện replica trả dữ liệu khác nhau khi đọc, rồi cập nhật bản cũ hơn (read repair). Một tiến trình anti-entropy so sánh dữ liệu theo lô để phát hiện và sửa sai lệch mà không cần chờ client đọc đúng key đó. Những cơ chế này hỗ trợ hội tụ nhưng không thay thế backup và không nhất thiết sửa được mọi xung đột logic.

## 8. Transaction isolation không giống replica consistency

Một hệ thống có thể sao chép mạnh giữa replica nhưng transaction vẫn cho phép anomaly nếu isolation level thấp hơn yêu cầu. Ngược lại, transaction serializable trên một database primary không tự bảo đảm read replica ở region khác trả dữ liệu mới nhất.

Các isolation level thường gặp:

| Isolation level | Ý nghĩa khái quát | Rủi ro/anomaly cần biết |
| --- | --- | --- |
| **Read uncommitted** | Có thể đọc dữ liệu chưa commit trong hệ hỗ trợ mức này | Dirty read và các anomaly khác |
| **Read committed** | Chỉ đọc dữ liệu đã commit; mỗi statement có thể thấy snapshot khác nhau | Non-repeatable read, phantom tùy hệ quản trị |
| **Repeatable read** | Các lần đọc cùng dữ liệu trong transaction có bảo đảm ổn định hơn | Phantom hoặc anomaly phụ thuộc database implementation |
| **Serializable** | Kết quả tương đương một thứ tự thực thi tuần tự hợp lệ | Có thể cần retry transaction, giảm concurrency hoặc tăng chi phí |

Tên isolation level được chuẩn hóa ở mức khái niệm nhưng triển khai thực tế khác nhau giữa engine. Cần đọc tài liệu database và test anomaly liên quan. Ví dụ, thao tác "kiểm tra còn một chỗ rồi giảm số chỗ đi một" không an toàn nếu hai transaction cùng đọc giá trị cũ rồi cùng cập nhật mà thiếu atomic conditional update, lock hoặc constraint phù hợp.

### Ví dụ atomic conditional update

Giả sử bảng inventory có một dòng với cột available. Có thể thực hiện cập nhật có điều kiện trong một statement:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE item_id = :item_id
  AND available > 0;
~~~

Ứng dụng kiểm tra số dòng bị ảnh hưởng. Nếu là một, lượt giữ chỗ đã giảm số lượng thành công trong cơ chế concurrency của database; nếu không, không còn hàng/chỗ hoặc item không tồn tại. Ví dụ cần transaction và constraint phù hợp cho toàn bộ booking; nó minh họa cách chuyển invariant vào thao tác atomic thay vì tách read và write không an toàn.

### Lost update và write skew

- **Lost update:** hai transaction đọc cùng giá trị, mỗi bên tính kết quả từ giá trị cũ, lần ghi sau ghi đè lần ghi trước.
- **Write skew:** hai transaction đọc một snapshot hợp lệ rồi cập nhật các dòng khác nhau, nhưng kết quả kết hợp vi phạm một constraint nghiệp vụ.

Ví dụ write skew: hệ thống trực ca yêu cầu luôn có ít nhất một nhân viên trực. Hai transaction cùng đọc rằng có hai người đang trực; mỗi transaction tắt lịch trực của một người khác nhau. Nếu không có constraint/serializable coordination, sau cả hai commit sẽ không còn ai trực.

## 9. Ánh xạ consistency vào yêu cầu nghiệp vụ

Không nên chọn strong consistency cho tất cả dữ liệu chỉ vì dễ mô tả, cũng không nên chọn eventual consistency chỉ để tăng thông lượng. Bắt đầu từ **invariant nghiệp vụ** và hành động mà người dùng/hệ thống thực hiện trên dữ liệu.

| Dữ liệu/hành trình | Invariant hoặc kỳ vọng | Mô hình thường cân nhắc |
| --- | --- | --- |
| Số dư tài khoản | Không chi tiêu vượt số dư; ledger không được nhân đôi | Transaction và kiểm soát ghi mạnh ở nguồn sự thật |
| Đặt chỗ cuối cùng | Tối đa một booking được xác nhận cho một slot | Atomic transaction/constraint/serialization |
| Kho hàng | Không bán vượt số lượng cho phép trong nghiệp vụ | Atomic conditional update hoặc transaction |
| Quyền truy cập và thu hồi quyền | Không tiếp tục cho phép truy cập nhạy cảm dựa trên cache cũ quá lâu | Strong read hoặc cache invalidation/short TTL tùy risk |
| Trạng thái đơn hàng | Không lùi về trạng thái nghiệp vụ cũ hơn | Transition validation, versioning, causal/order guarantee |
| Danh mục sản phẩm | Có thể chậm vài giây khi cập nhật mô tả | Eventual consistency/cache |
| Search index | Có thể trễ so với nguồn transaction | Projection/eventual consistency, hiển thị độ mới khi cần |
| Dashboard analytics | Có thể tổng hợp theo batch hoặc stream | Eventual consistency |
| Số lượt xem/feed | Có thể chấp nhận đếm gần đúng hoặc cập nhật trễ | Eventual/approximate aggregation |

### Đặt câu hỏi theo tác động thay vì nhãn kỹ thuật

Với từng dữ liệu, hỏi:

1. Điều gì xảy ra nếu người dùng đọc phiên bản cũ trong 100 ms, 5 giây hoặc 5 phút?
2. Có thao tác nào tạo thiệt hại tài chính, pháp lý, bảo mật hoặc phân bổ tài nguyên nếu dữ liệu cũ?
3. Hai người dùng có thể cập nhật cùng một thực thể cùng lúc không?
4. Có thể merge hai cập nhật hay phải từ chối một bên?
5. Client có cần read-your-writes hoặc monotonic reads không?
6. Khi region mất kết nối, có thể tạm dừng một loại ghi hay phải tiếp tục nhận mọi cập nhật?
7. Ai và hệ thống nào chịu trách nhiệm reconcile sai lệch?

Không nên dùng "dữ liệu này không quan trọng" làm lý do chọn eventual consistency. Cần nói rõ **độ trễ tối đa chấp nhận, hành vi UI, quy trình phát hiện sai lệch và cách phục hồi**.

## 10. Xử lý xung đột trong hệ thống eventual consistency

Khi nhiều node có thể nhận ghi trước khi đồng bộ, cùng một thực thể có thể bị thay đổi ở nhiều nơi. Khi các thay đổi gặp nhau, hệ thống phải có quy tắc giải quyết.

### Các chiến lược phổ biến

| Chiến lược | Cách xử lý | Phù hợp khi | Hạn chế |
| --- | --- | --- | --- |
| **Last-write-wins (LWW)** | Chọn phiên bản có timestamp/version được xem là mới nhất | Trạng thái đơn giản, ghi đè được chấp nhận | Đồng hồ lệch có thể chọn sai; mất cập nhật đồng thời |
| **Version/vector clock** | Theo dõi quan hệ phiên bản hoặc quan hệ nhân quả để phát hiện concurrent update | Cần nhận diện xung đột thật sự | Metadata và logic merge phức tạp |
| **Application-level merge** | Gộp theo quy tắc nghiệp vụ | Hồ sơ, tài liệu, cấu hình có quy tắc hợp nhất rõ | Phải xử lý từng loại dữ liệu |
| **CRDT** | Dùng cấu trúc dữ liệu có phép toán được thiết kế để hội tụ khi merge | Bộ đếm, tập hợp, trạng thái phân tán có semantics phù hợp | Không phải mọi invariant nghiệp vụ đều biểu diễn được |
| **Single-writer/leader** | Chỉ một node có quyền ghi cho một key/partition tại một thời điểm | Dữ liệu cần thứ tự ghi rõ ràng | Phụ thuộc leader, failover và routing |
| **Reject-and-retry** | Phát hiện version cũ/xung đột rồi yêu cầu caller tải lại hoặc thử lại | Cập nhật nhạy cảm, người dùng có thể chọn cách giải quyết | Trải nghiệm có thể phải xử lý conflict |

### Last-write-wins và vấn đề đồng hồ

Nếu hai region ghi hai giá trị cùng lúc, hệ thống có thể chọn timestamp lớn hơn. Nhưng đồng hồ máy không nhất thiết đồng bộ tuyệt đối; clock skew có thể khiến một ghi cũ bị đánh giá là mới hơn. Trong dữ liệu quan trọng, cần timestamp/version từ nguồn có semantics rõ hoặc cơ chế thứ tự khác. LWW chỉ đúng khi **quy tắc ghi đè** phù hợp nghiệp vụ.

### CRDT không phải phép màu

Conflict-free Replicated Data Type (CRDT) là các cấu trúc có phép cập nhật và merge được thiết kế để hội tụ mà không cần coordination cho mọi thao tác. Ví dụ, một grow-only counter có thể gộp số đếm từ nhiều node bằng cách cộng các thành phần đếm riêng; một grow-only set có thể hợp nhất phần tử theo phép union.

Nhưng CRDT không tự giải quyết mọi bài toán. Ví dụ "không được bán quá 10 vé" không thể chỉ dùng bộ đếm tăng độc lập ở nhiều region mà không có cơ chế phân bổ quota hoặc coordination; các region có thể cùng bán vượt tổng. CRDT cần được chọn theo cấu trúc dữ liệu và invariant có thể bảo toàn bằng phép merge.

### Conflict resolution phải có audit

Khi hệ thống tự merge hoặc bỏ một phiên bản, nên ghi nhận:

- Entity/key bị conflict và version liên quan.
- Nguồn/region hoặc actor tạo các phiên bản.
- Thuật toán/phiên bản quy tắc merge đã áp dụng.
- Giá trị trước/sau merge và lý do.
- Có cần người vận hành/người dùng xử lý thủ công không.

Với dữ liệu tài chính, quyền truy cập hoặc dữ liệu theo quy định, không nên âm thầm ghi đè mà thiếu audit trail và quy trình đối soát.

## 11. Eventual consistency trong kiến trúc event-driven

Một cách phổ biến để xây read model eventual consistent là ghi dữ liệu vào nguồn sự thật rồi phát event cho các consumer cập nhật projection, cache hoặc search index.

~~~mermaid
flowchart LR
    API["Booking API"] --> DB["Booking database"]
    DB --> OUTBOX["Transactional outbox"]
    OUTBOX --> BROKER["Message broker"]
    BROKER --> SEARCH["Search indexer"]
    BROKER --> CACHE["Cache updater"]
    BROKER --> ANALYTICS["Analytics consumer"]
~~~

Luồng này giảm phụ thuộc đồng bộ giữa booking và các read model. Booking có thể trả thành công sau khi transaction và outbox đã commit; search/cache/analytics cập nhật sau. Cần đảm bảo publisher không bỏ mất event và consumer xử lý an toàn khi event lặp hoặc đến sai thứ tự.

### Transactional outbox

Nếu ứng dụng commit booking trong database rồi publish message độc lập, có hai khoảng lỗi:

1. Database commit thành công nhưng process chết trước khi publish: dữ liệu có nhưng event mất.
2. Publish thành công nhưng process chết trước khi ghi nhận đã publish: event có thể được gửi lặp.

Transactional outbox giải quyết khoảng mất event bằng cách ghi booking và outbox record trong **cùng transaction database**. Một relay đọc record chưa gửi và publish lên broker; relay có thể gửi lặp nên consumer vẫn phải idempotent.

### Consumer idempotent và event ordering

Consumer có thể lưu event ID đã xử lý cùng thay đổi projection trong một transaction. Nếu nhận lại cùng event ID, bỏ qua side effect lần hai. Với event của cùng một entity, có thể dùng aggregate version/sequence để phát hiện sự kiện cũ hoặc thiếu thứ tự:

- Nếu version nhận được nhỏ hơn hoặc bằng version đã áp dụng, cân nhắc bỏ qua duplicate/stale event theo contract.
- Nếu version nhảy có khoảng trống, có thể cần chờ, replay hoặc tải snapshot từ nguồn.
- Nếu hai event concurrent thực sự, áp dụng quy tắc conflict đã định nghĩa.

Chỉ dùng timestamp để sắp thứ tự có thể không an toàn nếu đồng hồ không đồng bộ; version tăng tại nguồn sở hữu entity thường dễ diễn giải hơn. Broker partitioning theo entity key có thể giúp ordering trong phạm vi partition, nhưng không tự đảm bảo thứ tự toàn cục giữa nhiều partition.

### Độ trễ hội tụ (convergence lag)

Đặt mục tiêu cho độ trễ từ lúc write commit tới lúc projection được cập nhật:

- p50/p95/p99 event lag.
- Thời gian từ outbox creation tới publish.
- Thời gian queue wait và consumer processing.
- Số event retry/dead-letter.
- Độ tuổi projection và version so với nguồn.

Một eventual consistency contract cần nêu **hội tụ trong điều kiện nào**: ví dụ 99% cập nhật search index có trong 5 giây khi tải bình thường; event quá hạn được cảnh báo và replay. Không nên tuyên bố "cuối cùng sẽ nhất quán" mà không có cơ chế bảo đảm event được giao, consumer hoạt động và lỗi được phát hiện.

## 12. Cache consistency và invalidation

Cache giúp giảm latency và tải database, nhưng tạo thêm một bản sao dữ liệu có thể cũ. Khi write cập nhật nguồn, cache phải được cập nhật, xóa hoặc hết hạn theo policy.

### Các chiến lược

| Chiến lược | Luồng | Rủi ro |
| --- | --- | --- |
| **Cache-aside** | Đọc cache; miss thì đọc database và ghi cache. Khi write, cập nhật DB rồi invalidate cache | Có race giữa read cũ và cache fill; cache có thể stale |
| **Write-through** | Ghi qua cache layer và cập nhật nguồn theo cơ chế của hệ thống | Thêm latency; semantics phụ thuộc cache implementation |
| **Write-behind/write-back** | Cache nhận write trước rồi flush về store sau | Cache trở thành nơi giữ dữ liệu chưa bền; nguy cơ mất khi crash |
| **TTL-based** | Dữ liệu hết hạn sau thời gian định trước | Stale tối đa có thể gần TTL cộng thời gian propagation |
| **Event-driven invalidation** | Event từ nguồn làm cache evict/update | Event có thể trễ, lặp hoặc mất nếu không có outbox/replay |

### Race condition trong cache-aside

1. Request A đọc cache miss và lấy giá trị cũ từ DB.
2. Request B cập nhật DB sang giá trị mới, rồi xóa cache.
3. Request A hoàn tất chậm và ghi giá trị cũ vào cache.
4. Các request tiếp theo đọc lại giá trị cũ cho tới khi TTL hết hoặc cache bị invalidate.

Có thể giảm rủi ro bằng version/fencing token khi cache fill, cập nhật cache có điều kiện, dùng TTL ngắn theo mức chấp nhận stale, hoặc đọc trực tiếp nguồn mạnh cho hành trình quan trọng. Không có cách invalidate nào miễn nhiễm race; phải hiểu write/read concurrency.

### Cache không nên quyết định invariant quan trọng

Cache của số lượng chỗ trống có thể phục vụ hiển thị danh sách, nhưng booking cuối cùng phải được xác nhận bằng thao tác atomic/transaction ở nguồn dữ liệu sở hữu. Cache của quyền truy cập có thể cần TTL ngắn hoặc invalidation mạnh để thu hồi quyền đúng hạn. Mức stale chấp nhận được phụ thuộc thiệt hại khi ra quyết định từ dữ liệu cũ.

## 13. CQRS và read model có độ nhất quán khác nhau

Command Query Responsibility Segregation (CQRS) tách mô hình ghi (command/write model) khỏi mô hình đọc (query/read model). Write model bảo vệ invariant và transaction; event/projection cập nhật read model tối ưu cho tìm kiếm hoặc dashboard.

Ví dụ:

- Booking write model lưu reservation, kiểm soát uniqueness và trạng thái giao dịch.
- Search read model lưu dữ liệu phục vụ lọc/tìm kiếm, có thể cập nhật trễ.
- Dashboard read model tổng hợp số booking và doanh thu theo phút.

CQRS có thể giảm tải cho nguồn ghi và cho phép query model được tối ưu độc lập. Nhưng nó làm hệ thống có **nhiều bản sao dữ liệu và nhiều trạng thái đồng bộ**; cần outbox, replay, versioning, reconciliation, quan sát lag và giải thích trải nghiệm khi read model chưa cập nhật.

Không phải mọi ứng dụng đều cần CQRS. Nếu một bảng và vài query đơn giản đáp ứng tốt, thêm event broker và projection chỉ làm tăng độ phức tạp.

### Read-your-writes trong CQRS

Người dùng vừa tạo booking có thể được trả response chứa booking ID và trạng thái từ write model. Nếu ngay sau đó vào search list mà projection chưa cập nhật, booking có vẻ như biến mất. Có thể:

- Hiển thị kết quả tạo từ write response trong UI.
- Có endpoint đọc chi tiết trực tiếp từ write model theo ID ngay sau khi tạo.
- Trả projection version/consistency token và chờ read model đạt version đó.
- Giữ dữ liệu mới tạo trong client session cho tới khi search index hội tụ.

Không nên chặn mọi lệnh write cho tới khi toàn bộ search/analytics projection cập nhật nếu nghiệp vụ không yêu cầu.

## 14. Saga và quy trình nhiều bước

Khi nghiệp vụ đi qua nhiều service/database, một transaction ACID toàn cục có thể không khả thi hoặc không phù hợp. Saga chia quy trình thành các transaction cục bộ, mỗi bước có thể có hành động bù nếu bước sau thất bại.

Ví dụ đặt lịch:

1. Booking service giữ chỗ.
2. Payment service yêu cầu thu tiền.
3. Khi thanh toán thành công, Booking chuyển trạng thái confirmed.
4. Nếu thanh toán thất bại, Booking giải phóng chỗ bằng hành động bù.

~~~mermaid
sequenceDiagram
    participant B as Booking
    participant I as Inventory
    participant P as Payment
    B->>I: Reserve slot
    I-->>B: Reserved
    B->>P: Charge payment
    alt Payment success
        P-->>B: Paid
        B->>I: Confirm reservation
    else Payment failure
        P-->>B: Failed
        B->>I: Release reservation (compensation)
    end
~~~

Hành động bù không phải rollback tức thời như transaction trong một database. Payment có thể đã thu tiền nhưng callback đến chậm; hoàn tiền có thể mất thời gian; reservation release cũng có thể thất bại và cần retry. Saga cần state machine bền vững, idempotent command, timeout, deadline, retry policy, compensation và manual reconciliation.

Nếu hai thay đổi luôn phải commit cùng nhau với invariant chặt và nằm trong một database, giữ chung transaction có thể đơn giản, chính xác hơn. Chỉ tách saga khi ranh giới nghiệp vụ và lợi ích vận hành đủ rõ.

## 15. Case study: nền tảng đặt chỗ và tồn kho giới hạn

Một nền tảng đặt chỗ bán 100 suất cho một khung giờ. Trong chiến dịch, hàng nghìn người có thể cùng gửi request trong vài giây. Hệ thống có ba nhu cầu:

- Không được xác nhận quá 100 booking.
- Người đặt cần thấy booking của mình ngay sau khi API báo thành công.
- Search, danh sách phổ biến và dashboard có thể cập nhật chậm vài giây.

Đây là một ví dụ tốt để chọn mô hình nhất quán **theo chức năng**, thay vì ép toàn bộ nền tảng dùng một model.

### Bước 1 — Đặt invariant

Gọi \(A\) là số suất còn khả dụng, \(B\) là số booking đã xác nhận. Bất biến cần giữ:

\[
A\geq0,\qquad A+B=100
\]

Trong thực tế còn các trạng thái giữ chỗ tạm thời, hết hạn, hủy và thanh toán chưa xác định. Cần đưa các trạng thái đó vào mô hình nghiệp vụ và quy định khi nào một suất được tính là đã bán.

### Bước 2 — Giữ ghi giao dịch tại nguồn sở hữu

Booking/Inventory dùng transaction và atomic conditional update để giảm số suất nếu vẫn còn. Constraint hoặc khóa thích hợp bảo vệ invariant khi nhiều request đồng thời. Một request có idempotency key để client retry không tạo booking trùng.

Search index và dashboard nhận event sau khi transaction ghi thành công. Chúng có thể trễ nhưng không được dùng làm nguồn quyết định cuối cùng cho việc bán suất cuối.

### Bước 3 — Cập nhật projection bất đồng bộ

~~~mermaid
flowchart TB
    CLIENT["Client"]
    API["Booking API"]
    DB["Booking / Inventory database"]
    OUTBOX["Outbox event"]
    BROKER["Message broker"]
    SEARCH["Search projection"]
    DASH["Dashboard aggregate"]
    CLIENT --> API
    API --> DB
    DB -->|Commit booking + outbox| OUTBOX
    OUTBOX --> BROKER
    BROKER --> SEARCH
    BROKER --> DASH
~~~

Sau commit, Booking API trả kết quả và ID. Search projection được cập nhật theo event; dashboard có thể tổng hợp theo batch. Nếu message bị lặp, consumer dùng event ID/version để không cộng doanh thu hoặc số booking hai lần.

### Bước 4 — Xử lý trải nghiệm người dùng

Ngay sau khi tạo booking, client hiển thị trạng thái từ response write model. Nếu người dùng mở search list và kết quả chưa cập nhật, UI có thể:

- Hiển thị booking vừa tạo trong khu vực "Gần đây" từ response.
- Đánh dấu danh sách đang cập nhật hoặc hiển thị thời điểm đồng bộ.
- Khi người dùng mở chi tiết theo booking ID, đọc từ write model hoặc endpoint có read-your-writes.

Không nên trì hoãn xác nhận booking cho đến khi analytics/dashboard cập nhật, vì đây không phải điều kiện nghiệp vụ bắt buộc.

### Bước 5 — Khi replica hoặc event bị trễ

Nếu read replica trễ, hệ thống có thể chuyển một số request cần read-your-writes về primary hoặc dùng consistency token nếu database hỗ trợ. Nếu search event bị trễ, đo queue lag và hiển thị trạng thái projection cũ; nếu event lỗi, retry/DLQ rồi replay sau khi sửa.

### Bước 6 — Khi hai người cùng đặt suất cuối

Hai request cùng đọc thấy một suất có thể xảy ra nếu ứng dụng tách read và write. Vì vậy không dùng kết quả đọc để tự quyết định. Cả hai gửi conditional update:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE slot_id = :slot_id
  AND available > 0;
~~~

Chỉ transaction có update thành công mới được đi tiếp tới bước tạo reservation theo cùng transaction hoặc theo protocol đảm bảo atomicity. Request còn lại nhận kết quả hết chỗ. Cần kiểm tra unique constraint, idempotency, transaction boundary và trạng thái khi commit thành công nhưng response bị mất.

### Kết quả kiến trúc

| Thành phần | Mức nhất quán cần thiết | Lý do |
| --- | --- | --- |
| Inventory/booking write | Strong/transactional theo invariant | Ngăn bán vượt và booking trùng |
| Booking detail của chính người dùng | Read-your-writes hoặc đọc từ nguồn mạnh | Tránh người dùng vừa đặt xong lại thấy chưa có |
| Search index | Eventual | Chấp nhận độ trễ trong vài giây |
| Dashboard | Eventual/batch | Số tổng hợp không quyết định giao dịch |
| Cache danh sách chỗ trống | Có thể stale có giới hạn | Chỉ dùng để hiển thị, không xác nhận giữ chỗ |

## 16. Case study: cập nhật hồ sơ ở nhiều region

Một ứng dụng toàn cầu cho phép người dùng sửa tên hiển thị và ảnh đại diện từ nhiều region. Nếu hai thiết bị sửa cùng một hồ sơ khi offline rồi đồng bộ, hệ thống phải giải quyết xung đột.

### Phân biệt các trường dữ liệu

- **Tên hiển thị:** có thể dùng optimistic concurrency với version; nếu phát hiện xung đột, yêu cầu người dùng chọn hoặc dùng quy tắc merge được công bố.
- **Ảnh đại diện:** file mới lưu object theo key/version; metadata pointer cập nhật bằng version. Nếu ghi đồng thời, chọn phiên bản theo quy tắc nghiệp vụ, không chỉ timestamp từ hai đồng hồ tùy tiện.
- **Email/định danh đăng nhập:** thường cần uniqueness và xác minh; không để hai region tự nhận cùng email rồi merge về sau mà thiếu coordination.
- **Lịch sử thay đổi:** lưu audit/event để người dùng hoặc support có thể tra cứu.

### Optimistic concurrency control

Một client đọc hồ sơ version 12, rồi gửi cập nhật với version hiện tại:

~~~http
PUT /profiles/123
If-Match: "12"
Content-Type: application/json

{"displayName":"Linh"}
~~~

Server chỉ áp dụng nếu version vẫn là 12; nếu một thiết bị khác đã cập nhật version 13, server trả conflict (ví dụ HTTP 412 theo contract). Client tải lại, hiển thị khác biệt hoặc gửi lại thay đổi theo quy tắc được xác định.

Mẫu này tránh ghi đè âm thầm khi hai người cùng sửa. Nó không tự giải quyết mọi xung đột nhiều vùng; cần nơi sở hữu version hoặc cơ chế đồng bộ/merge có thứ tự.

## 17. Thiết kế API khi dữ liệu có thể chưa hội tụ

API cần làm rõ **điều gì đã được commit** và **điều gì vẫn đang được đồng bộ**.

### Trả version và thời điểm cập nhật

Response có thể gồm:

~~~json
{
  "bookingId": "bkg_123",
  "status": "CONFIRMED",
  "version": 42,
  "committedAt": "2026-11-18T10:20:30Z"
}
~~~

Ví dụ là schema minh họa. Version có thể dùng để đối chiếu projection; timestamp giúp hiển thị thời điểm nhưng không nhất thiết là thứ tự nhân quả toàn cục. Không công bố internal database LSN hoặc token nhạy cảm nếu API contract không yêu cầu.

### Trạng thái đồng bộ của projection

Một API đọc/search có thể trả metadata:

~~~json
{
  "items": [],
  "projectionVersion": 40,
  "sourceVersion": 42,
  "asOf": "2026-11-18T10:20:28Z",
  "consistency": "EVENTUAL"
}
~~~

Điều này giúp client hiểu projection đang trễ hai version theo ví dụ. Trong thực tế, version source/projection chỉ so sánh được khi chúng cùng một phạm vi và semantics. Nếu dữ liệu gồm nhiều aggregate, cần watermark hoặc checkpoint theo partition thay vì một số version duy nhất.

### Command và query nên có contract khác nhau

- Command trả lời thao tác đã được tiếp nhận/commit ở nguồn ghi hay chưa.
- Query nêu nguồn đọc, độ mới hoặc mức consistency mà caller nhận được.
- Nếu cần read-your-writes, client truyền consistency token/version theo contract.
- Nếu một thao tác bất đồng bộ, trả job/operation ID và endpoint theo dõi.
- Nếu conflict, trả lỗi có thể xử lý thay vì ghi đè âm thầm.

Không nên gắn nhãn EVENTUAL vào mọi API response nếu consumer không biết độ trễ tối đa, hoặc trả CONFIRMED trước khi transaction thực sự được commit.

## 18. Quan sát và vận hành tính nhất quán

Eventual consistency chỉ vận hành được khi đội ngũ biết replica/projection đang trễ bao lâu và có cách khôi phục. Strong consistency cũng cần quan sát latency/quorum để nhận biết coordination đang trở thành điểm nghẽn.

| Tín hiệu | Ý nghĩa | Cảnh báo khi |
| --- | --- | --- |
| Replication lag | Độ trễ replica so với nguồn | Vượt ngưỡng read-your-writes hoặc RPO |
| Quorum failure / unavailable writes | Không đủ thành viên đáp ứng write policy | Transaction quan trọng không thể commit |
| Conflict rate | Số phiên bản concurrent cần giải quyết | Tăng bất thường hoặc merge liên tục thất bại |
| Event delivery lag | Outbox/broker/consumer chậm | Projection vượt stale budget |
| Dead-letter count | Event không xử lý được | Tăng hoặc tồn tại quá hạn |
| Projection version lag | Read model chậm hơn nguồn bao nhiêu | Consumer nhìn thấy trạng thái cũ vượt cam kết |
| Cache stale rate | Cache trả version cũ hoặc invalidation trễ | Hành trình nhạy cảm vượt stale tolerance |
| Reconciliation mismatch | Chênh lệch giữa nguồn và projection/tổng hợp | Có sai lệch kéo dài hoặc dữ liệu tài chính không khớp |
| Read-your-writes fallback rate | Tần suất buộc đọc từ nguồn mạnh | Cao bất thường, tăng tải primary |

### Dashboard và trace

Theo dõi theo database/region/keyspace/consumer, nhưng tránh đưa user ID hoặc entity ID có cardinality rất lớn thành metric label. Dùng trace/log có kiểm soát quyền để điều tra từng event hoặc operation. Correlation ID, aggregate ID, event ID và version giúp nối write với projection.

### Quy trình reconcile

1. Xác định nguồn dữ liệu có thẩm quyền cho từng loại thông tin.
2. Chọn khoảng thời gian/partition có lag hoặc mismatch.
3. So sánh version/checksum/count theo cách không làm quá tải nguồn.
4. Phát lại event hoặc rebuild projection từ nguồn khi cần.
5. Xác minh không tạo duplicate side effect.
6. Ghi audit, cập nhật metric và thông báo tới chủ sở hữu nghiệp vụ.

Với dữ liệu tài chính, đối soát phải sử dụng ledger hoặc nguồn sổ cái có thẩm quyền; không sửa tổng doanh thu chỉ bằng cách cộng lại dashboard nếu chưa xác định giao dịch nào thiếu/trùng.

## 19. Quy trình chọn consistency model

Một quyết định nhất quán có thể được thực hiện theo các bước:

### Bước 1 — Liệt kê dữ liệu và chủ sở hữu

Ghi rõ entity, nguồn sự thật, các bản sao, cache, read model, region, consumer và hệ thống bên ngoài. Mỗi loại dữ liệu cần một chủ sở hữu có trách nhiệm định nghĩa invariant và xử lý reconcile.

### Bước 2 — Viết invariant nghiệp vụ

Ví dụ:

- Số lượng hàng không âm.
- Một slot không có hai booking được xác nhận.
- Một payment operation chỉ được ghi nhận một lần.
- Trạng thái đơn không quay ngược từ DELIVERED về PROCESSING.
- Chỉ người có quyền mới đọc được dữ liệu hồ sơ.

Viết invariant theo điều kiện có thể kiểm tra, không chỉ mô tả chung chung như "dữ liệu luôn đúng".

### Bước 3 — Xác định độ stale được chấp nhận

Với mỗi read path, nêu rõ có thể cũ bao lâu: không chấp nhận cũ, tối đa 100 ms, 5 giây, vài phút hay chỉ cần hội tụ trước báo cáo cuối ngày. Độ stale phải được liên hệ với hành động người dùng thực hiện trên kết quả đó.

### Bước 4 — Chọn consistency boundary

Đặt strong/transactional consistency ở nơi bảo vệ invariant; chọn read-your-writes hoặc causal consistency cho trải nghiệm phiên; chọn eventual cho projection/cache/analytics nếu nghiệp vụ chấp nhận. Tránh transaction phân tán nếu có thể giữ invariant trong một ranh giới dữ liệu.

### Bước 5 — Chọn cơ chế dữ liệu và replication

Xác định primary/single-writer hay multi-writer, replication sync/async, quorum, transaction isolation, conditional update, unique constraint, versioning và conflict resolution. Kiểm tra contract thực của database.

### Bước 6 — Thiết kế event và khôi phục

Nếu có projection, dùng outbox/CDC hoặc phương pháp phát event đáng tin; consumer idempotent, version/order, retry, DLQ, replay, reconciliation và backup.

### Bước 7 — Thiết kế API và trải nghiệm

Trả operation ID, version, trạng thái pending hoặc metadata độ mới khi cần. Định nghĩa hành vi khi đọc stale, conflict, timeout hoặc một region mất liên lạc.

### Bước 8 — Đo, test và xem lại

Đo latency, replication lag, event lag, conflict rate, duplicate, mismatch và cost. Diễn tập partition, node loss, out-of-order event, retry, replay và restore. Đặt ngưỡng khi nào cần thay mô hình hoặc tăng capacity.

~~~mermaid
flowchart TD
    DATA["Dữ liệu + chủ sở hữu"] --> INV["Invariant nghiệp vụ"]
    INV --> STALE["Độ stale chấp nhận"]
    STALE --> BOUNDARY["Consistency boundary"]
    BOUNDARY --> MECH["Replication / transaction / event"]
    MECH --> API["API contract + UX"]
    API --> TEST["Test + quan sát + reconcile"]
    TEST --> REVIEW["Review SLO / chi phí / rủi ro"]
    REVIEW --> STALE
~~~

## 20. Kiểm thử tính nhất quán

Test happy path với một client đơn lẻ không đủ. Cần tạo tình huống cạnh tranh và lỗi mạng để xác minh semantics.

| Bài thử | Mô phỏng | Điều cần chứng minh |
| --- | --- | --- |
| Concurrent write | Nhiều client cùng cập nhật một entity | Invariant không bị vi phạm; conflict được phát hiện |
| Read-after-write | Đọc ngay sau khi write thành công ở replica khác | Bảo đảm read-your-writes đúng theo contract |
| Partition | Chặn giao tiếp giữa replica/region | Hành vi CP/AP hoặc policy theo thao tác đúng cam kết |
| Replica lag | Cố ý làm chậm replication | Stale read được phát hiện hoặc giới hạn đúng |
| Out-of-order event | Gửi event version N+1 trước N | Projection không quay lùi hoặc sai trạng thái |
| Duplicate delivery | Gửi cùng event nhiều lần | Consumer không tạo side effect lặp |
| Missing event | Làm publisher/consumer gián đoạn | Outbox/replay/DLQ phục hồi được |
| Cache race | Xen kẽ read cũ, write mới, cache invalidation | Giá trị cũ không vượt stale tolerance |
| Region failover | Mất region primary | RPO thực tế và nguồn writer sau failover rõ |
| Restore/rebuild | Khôi phục database/projection từ backup/event | Dữ liệu và invariant được xác minh |

### Invariant-based testing

Thay vì chỉ kiểm tra response HTTP, test liên tục các điều kiện nghiệp vụ:

- Tổng số booking confirmed không vượt capacity.
- Số dư ledger không được giảm sai theo các giao dịch được xác nhận.
- Mỗi idempotency key chỉ tạo một kết quả nghiệp vụ.
- Projection version không vượt qua source version chưa được commit.
- Trạng thái entity chỉ chuyển theo các transition được phép.
- Dữ liệu nhạy cảm không xuất hiện trong read model không có quyền.

Có thể sử dụng property-based test, concurrency test hoặc fault injection để sinh nhiều thứ tự thao tác. Sau mỗi lượt, đọc dữ liệu từ nguồn authoritative và kiểm tra invariant.

### Test consistency cần test recovery

Một hệ thống có thể xử lý đúng partition nhưng sau khi mạng phục hồi không hội tụ do event bị mất hoặc conflict không được merge. Vì vậy test phải chạy qua cả ba pha:

1. **Trước lỗi:** tạo dữ liệu và trạng thái nền.
2. **Trong lỗi:** tạo cập nhật cạnh tranh hoặc tách mạng; quan sát các node trả gì.
3. **Sau lỗi:** khôi phục kết nối, đợi replication/replay, so sánh trạng thái cuối và xác minh invariant.

## 21. Những sai lầm thường gặp

1. **Đồng nhất ACID consistency với strong consistency giữa replica:** hai bảo đảm nằm ở các tầng khác nhau.
2. **Dùng eventual consistency cho invariant tài chính/đặt chỗ mà không có coordination:** có thể tạo oversell, double spend hoặc trạng thái không hợp lệ.
3. **Dùng strong consistency cho mọi read model:** làm tăng latency và coordination dù báo cáo/search có thể chấp nhận trễ.
4. **Nói eventual sẽ tự hội tụ mà thiếu event delivery/replay:** message mất hoặc consumer lỗi có thể khiến projection lệch mãi.
5. **Coi CAP là lựa chọn cố định hai trong ba:** bỏ qua điều kiện partition và semantics cụ thể của từng thao tác.
6. **Giả định quorum giao nhau là đủ cho linearizability:** còn phụ thuộc versioning, ordering, leader và thuật toán.
7. **Dùng timestamp LWW khi đồng hồ không đáng tin:** có thể loại bỏ cập nhật hợp lệ.
8. **Chia nguồn dữ liệu rồi dual-write không atomic:** một service cập nhật thành công trong khi service kia thất bại.
9. **Không xử lý duplicate/out-of-order event:** projection sai, số liệu bị cộng hai lần hoặc trạng thái quay lùi.
10. **Cache invalidation sau commit mà không xét race:** request cũ có thể ghi lại cache cũ sau khi đã xóa.
11. **Dùng search/cache làm nguồn xác nhận giao dịch:** read model trễ có thể đưa ra quyết định sai.
12. **Không công bố độ stale cho client:** người dùng nhìn thấy dữ liệu cũ mà không hiểu trạng thái đồng bộ.
13. **Không có reconciliation:** sai lệch nhỏ tích tụ thành lỗi lớn mà không ai phát hiện.
14. **Không test partition và recovery:** mô hình hoạt động khi mạng ổn định nhưng thất bại khi replica chậm hoặc mất kết nối.
15. **Tách saga cho mọi transaction:** làm tăng trạng thái trung gian và compensation dù transaction local có thể đủ.

## 22. Bài tập thực hành và đáp án định hướng

Một nền tảng thương mại điện tử có các yêu cầu:

- Tồn kho một sản phẩm chỉ còn 1 đơn vị.
- Hai khách hàng ở hai region cùng bấm mua gần như đồng thời.
- Màn hình danh sách sản phẩm có thể cập nhật chậm tối đa 10 giây.
- Sau khi khách hàng nhận xác nhận đơn hàng, trang chi tiết phải hiển thị đơn vừa tạo.
- Dashboard doanh thu chấp nhận cập nhật theo phút.
- Khi mạng liên vùng bị phân vùng, hệ thống phải ưu tiên không bán vượt số lượng.

### Câu 1 — Chọn consistency cho tồn kho

**Đáp án định hướng:** Strong/transactional consistency ở nguồn ghi tồn kho, với conditional update/locking/unique invariant. Khi partition, có thể từ chối hoặc giữ một số lệnh mua ở region không sở hữu writer thay vì tiếp tục bán bằng bản sao cũ.

### Câu 2 — Chọn consistency cho danh sách sản phẩm

**Đáp án:** Eventual consistency có thể phù hợp vì nghiệp vụ cho phép trễ tới 10 giây. Cần metric projection/cache lag, cảnh báo khi vượt stale budget và đảm bảo thao tác mua cuối cùng kiểm tra lại nguồn tồn kho.

### Câu 3 — Vì sao không dùng dashboard để xác nhận đơn?

**Đáp án:** Dashboard là projection tổng hợp theo phút; nó có thể chưa cập nhật sau commit hoặc làm tròn/gom dữ liệu. Trang chi tiết đơn nên đọc từ write model hoặc hỗ trợ read-your-writes bằng version/token.

### Câu 4 — Hai region cùng ghi tồn kho khi partition có thể gây gì?

**Đáp án:** Mỗi region có thể thấy còn một đơn vị và cùng xác nhận một đơn, dẫn tới oversell. Nếu nghiệp vụ ưu tiên không oversell, cần single-writer/ownership hoặc coordination/quorum; vùng không đủ điều kiện ghi phải chờ, từ chối hoặc nhận request dưới trạng thái pending có kiểm soát.

### Câu 5 — Event OrderCreated được giao hai lần, dashboard có tăng doanh thu hai lần không?

**Đáp án:** Không nếu consumer idempotent. Lưu event ID/processed marker và cập nhật projection trong cùng transaction hoặc cơ chế bảo đảm tương đương. Nếu event có version, bỏ duplicate/stale theo contract.

### Câu 6 — Sau khi region phục hồi, làm sao biết các projection đã hội tụ?

**Đáp án định hướng:** So sánh source version/watermark, event lag, checksum/count hoặc đối soát theo partition. Replay event bị thiếu, xử lý conflict và xác minh invariant; không chỉ chờ một khoảng thời gian cố định rồi coi là đồng bộ.

### Câu 7 — Nêu một trường hợp strong consistency không cần thiết

**Đáp án:** Dashboard doanh thu hoặc danh sách sản phẩm có thể dùng projection/eventual consistency nếu độ stale tối đa được nghiệp vụ chấp nhận và có cách thể hiện độ mới. Không cần block giao dịch mua để đợi dashboard cập nhật.

## 23. Checklist review kiến trúc

- Mỗi dữ liệu có nguồn sự thật và owner rõ ràng chưa?
- Invariant nghiệp vụ đã được viết thành điều kiện kiểm tra chưa?
- Đã phân loại read path nào cần strong, read-your-writes, causal hay eventual chưa?
- Có chỉ rõ độ stale tối đa theo từng hành trình không?
- Transaction isolation và replica consistency có được đánh giá riêng không?
- Replication sync/async, commit acknowledgement, quorum và failure mode đã hiểu rõ chưa?
- Partition xảy ra thì thao tác nào chờ, từ chối, đọc stale hoặc tiếp tục ghi?
- Xung đột được phát hiện/merge/reject theo quy tắc nào? Có audit không?
- Event có outbox/replay, idempotent consumer, version/order và DLQ không?
- Cache invalidation có race và stale window nào?
- API có hỗ trợ version, conflict, operation status hoặc read-your-writes khi cần không?
- Có metric replication lag, projection lag, conflict, duplicate và reconciliation mismatch không?
- Có test concurrent write, partition, failover, replay và restore chưa?
- Chi phí latency, network, replica, broker và vận hành có phù hợp SLO/ngân sách không?

## 24. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi chính | Bằng chứng |
| --- | --- | --- |
| **Độ tin cậy** | Khi partition, replica lag hoặc duplicate event xảy ra, invariant có còn đúng và hệ thống có phục hồi được không? | Quorum policy, RPO/RTO, outbox, idempotency, fault test |
| **Bảo mật** | Read model/cache có làm lộ dữ liệu hoặc giữ quyền đã bị thu hồi quá lâu không? | IAM, authorization, cache invalidation, audit |
| **Hiệu năng** | Strong consistency có làm latency vượt SLO? Eventual projection có lag quá dài? | p95/p99, replication lag, queue lag, read/write throughput |
| **Tối ưu chi phí** | Replica, coordination, event, storage và reconcile có hợp lý với giá trị nghiệp vụ? | Cost per operation, network transfer, broker/storage bill |
| **Vận hành xuất sắc** | Đội có phát hiện mismatch, replay và đối soát được không? | Dashboard, alert, runbook, ownership, restore/reconcile drill |
| **Tính bền vững** | Có tránh duy trì replica/copy không cần thiết và xử lý dữ liệu hết hạn đúng cách không? | Retention, right-sizing, data lifecycle |

Một quyết định consistency tốt nói rõ **điều gì phải đúng ngay, điều gì có thể đúng sau, người dùng nhìn thấy gì trong khoảng chuyển tiếp và hệ thống chứng minh hội tụ bằng cách nào**. Đó là nền tảng để chọn database, replication và kiến trúc event-driven theo yêu cầu nghiệp vụ thay vì theo nhãn công nghệ.
