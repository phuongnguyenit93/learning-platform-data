# Các nguyên nhân khiến dữ liệu giữa các replica khác nhau

## Mục tiêu bài học

Apache Cassandra là cơ sở dữ liệu **phân tán, wide-column**, nơi một partition thường được sao chép tới nhiều node để duy trì khả năng phục vụ khi máy hoặc mạng gặp sự cố. Trong một khoảng thời gian, các replica của cùng partition **có thể chứa phiên bản khác nhau**: một node đã nhận cập nhật mới, node khác chưa nhận; một replica còn dữ liệu đã xóa; hoặc các bản ghi cạnh tranh được gán timestamp khác nhau.

Đó không nhất thiết là lỗi hỏng dữ liệu: mức nhất quán đọc/ghi (*consistency level – CL*) của Cassandra cho phép lựa chọn giữa số xác nhận cần chờ, độ trễ và khả năng sẵn sàng. Tuy nhiên, nếu độ lệch kéo dài, tiến trình sửa chữa không chạy đúng hoặc tombstone bị dọn quá sớm, dữ liệu có thể bị thiếu, đọc cũ hoặc thậm chí xuất hiện lại sau khi đã xóa.

Bài thuộc chương **Đồng bộ bản sao** trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nội dung đi từ đường ghi/đọc, replication, consistency tới hinted handoff, read repair, anti-entropy repair, compaction, TTL và xử lý lỗi; ví dụ dùng CQL và Java Driver 4.x.

Sau bài học, bạn có thể:

1. Mô tả vì sao **RF = 3 không có nghĩa ba replica luôn giống nhau tại mọi thời điểm**.
2. Phân biệt dữ liệu lệch tạm thời, xung đột timestamp, lỗi xóa/tombstone và dữ liệu sai do ứng dụng ghi vào **những bảng khác nhau**.
3. Giải thích ảnh hưởng của `ONE`, `LOCAL_QUORUM`, `ALL` và vị trí datacenter đối với khả năng nhìn thấy cập nhật.
4. Nêu nguyên nhân, giới hạn và vai trò riêng của **hinted handoff**, **read repair**, **repair** và **streaming**.
5. Kiểm chứng một tình huống bằng CQL, quan sát timestamp ghi, log, chỉ số replica và code Java.
6. Thiết kế quy trình chẩn đoán, thử lỗi và vận hành nhằm giảm độ lệch mà không gây hại cho dữ liệu sản xuất.

## 1. Replica là gì, và “khác nhau” nghĩa là gì?

Giả sử keyspace dùng `NetworkTopologyStrategy` với **RF = 3** trong một datacenter có đủ node. Một partition với khóa `(tenant_id, order_id)` được lưu tại ba replica theo chiến lược đặt dữ liệu.

```text
                 Client Java / cqlsh
                         |
                    Coordinator
                         |
             +-----------+-----------+
             |           |           |
          Replica A    Replica B   Replica C
          status=PAID   PENDING     PAID
          rev=12        rev=11      rev=12
```

Trong hình, A và C đã có phiên bản mới hơn B. Điều này có thể xảy ra nếu B bị chậm/mất kết nối khi ghi, nếu phản hồi của client chỉ cần một phần replica xác nhận, hoặc quá trình đồng bộ chưa hoàn tất.

**Phân biệt ba loại “khác nhau”:**

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Khác trạng thái dữ liệu của cùng partition** | A có `PAID`, B còn `PENDING` ở cùng cell | Độ lệch giữa replica cần được phân tích |
| **Khác dữ liệu vật lý trên SSTable** | A có nhiều SSTable mới hơn B nhưng truy vấn logic trả cùng giá trị | Chưa đủ để kết luận lỗi nhất quán; compaction/flush khác thời điểm |
| **Khác giữa các projection nghiệp vụ** | `orders_by_id` có `PAID`, `orders_by_status_day` còn hàng `PENDING` | Hai bảng/partition phục vụ query shape khác nhau; **repair replica không tự sửa** việc ứng dụng thiếu mutation |

Trong Cassandra, mỗi cell còn có thông tin như **write timestamp** và có thể có TTL/tombstone. Hai replica có thể nhận mutation vào các thời điểm khác nhau nhưng sau khi áp dụng cùng các mutation hợp lệ sẽ hội tụ theo các quy tắc giải quyết xung đột. Tuy nhiên, một sự kiện nghiệp vụ đến muộn hoặc clock skew có thể làm **cả ba replica cùng hội tụ về giá trị sai nghiệp vụ**; đó là vấn đề khác với một replica chưa bắt kịp.

### 1.1. “Đã ghi thành công” không đồng nghĩa mọi replica đã nhận

Replication factor quyết định tập replica dự kiến, còn **consistency level của thao tác** quyết định số phản hồi cần thiết trước khi báo thành công cho client. Với RF = 3, một ghi `ONE` có thể hoàn tất khi một replica xác nhận, trong khi các replica khác đang tiếp tục nhận hoặc chờ áp dụng thay đổi.

Coordinator vẫn có thể gửi mutation tới **nhiều hoặc tất cả replica phù hợp**, kể cả khi client chỉ yêu cầu `ONE`. Do đó không nên nói “ghi ONE chỉ ghi một node”; chính xác là **client chỉ phải chờ số xác nhận của CL đó**.

## 2. Đường ghi và đường đọc của một partition

### 2.1. Đường ghi khái niệm

Một request ghi tới coordinator, node này xác định các replica chịu trách nhiệm theo token/replication strategy rồi chuyển mutation:

```text
t0   Client gửi UPDATE(status=PAID) với CL=ONE
     |
t1   Coordinator định tuyến mutation tới A, B, C
     |
t2   A áp dụng mutation và ACK
     |             B chậm / mất kết nối
     |             C vẫn đang xử lý
t3   Coordinator đủ điều kiện CL=ONE -> trả success
     |
t4   C áp dụng mutation
     |
t5   B có thể nhận lại qua cơ chế phục hồi phù hợp
```

Khoảng từ `t3` đến `t5` là một cửa sổ có thể có replica lệch. Diễn biến thực tế phụ thuộc topology, network, quá tải, phiên bản Cassandra và các cơ chế hỗ trợ đang bật. Một client không thể suy ra thời điểm `t5` chỉ từ kết quả thành công của lệnh ghi `ONE`.

### 2.2. Đường đọc khái niệm

Khi đọc, coordinator liên hệ những replica theo CL và thuật toán đọc. Cassandra có thể dùng **data response** và **digest response** để phát hiện không khớp giữa những replica được tham gia vào một lần đọc; cách xử lý cụ thể, read repair và mức blocking phụ thuộc phiên bản/cấu hình.

Ví dụ hai lần đọc `ONE` ở hai thời điểm có thể được phục vụ từ các replica khác nhau, nên một lần đọc nhìn thấy `PAID`, lần khác lại nhìn thấy `PENDING` nếu dữ liệu vẫn lệch. Đây là **khả năng**, không phải kết quả bắt buộc: routing, speculative retry, replica selection và việc một replica đã bắt kịp làm kết quả không hoàn toàn xác định.

Một lần đọc `LOCAL_QUORUM` trong cùng DC có nhiều cơ hội phát hiện/chọn dữ liệu mới hơn khi dữ liệu của nhóm replica tham gia khác nhau, nhưng nó **không thay cho anti-entropy repair trên toàn bộ các replica**.

## 3. Nguyên nhân 1: ghi và đọc ở consistency level thấp hơn ALL

Cassandra cho phép điều chỉnh mức xác nhận để cân bằng khả năng sẵn sàng và độ trễ.

| CL | Ý nghĩa cấp cao trong một DC RF=3 | Rủi ro/đánh đổi |
| --- | --- | --- |
| `ONE` | Một replica xác nhận theo CL | Ghi/đọc thường tiếp tục được khi một số replica không đáp ứng; đọc có thể thấy bản cũ |
| `LOCAL_QUORUM` | Đa số replica trong local DC, với RF=3 thường là 2 | Đòi hai replica đáp ứng; giúp bảo đảm giao thoa quorum phù hợp |
| `ALL` | Mọi replica được yêu cầu trong phạm vi consistency tương ứng | Kém sẵn sàng khi replica lỗi/chậm; không phải cách thay thế repair |
| `LOCAL_ONE` | Một replica tại local DC | Ưu tiên local latency/availability, có thể đọc cũ |
| `EACH_QUORUM` | Quorum tại từng DC theo cấu hình | Chi phí và khả năng sẵn sàng phụ thuộc nhiều DC; không chọn tùy tiện |

**Lưu ý:** `ALL` và `EACH_QUORUM` có ngữ nghĩa theo cách replica/DC được yêu cầu; bảng trên không thay cho tài liệu phiên bản. Nếu dùng nhiều datacenter, phải tính RF từng DC và hiểu rõ khi nào request chỉ chờ replica local.

### 3.1. Vì sao LOCAL_QUORUM có ích?

Với `RF = 3` tại một DC, quorum là 2. Hai tập replica bất kỳ, mỗi tập có 2 trong tổng 3, **phải giao nhau ít nhất 1 replica**:

```text
Write LOCAL_QUORUM: A, B xác nhận
Read  LOCAL_QUORUM: B, C tham gia
Giao nhau: B

W + R > RF
2 + 2 > 3
```

Giao thoa quorum là nền tảng để đạt tính chất đọc thấy cập nhật đã hoàn tất trong những giả định phù hợp của hệ thống. Nhưng đừng suy rộng thành “mọi SELECT là transaction tuyến tính hóa toàn cục”: còn những write đồng thời, timestamp xung đột, TTL/tombstone, lỗi và những read qua nhiều bảng/partition. **Không có một snapshot SQL xuyên nhiều partition chỉ nhờ chọn LOCAL_QUORUM.**

### 3.2. Ghi LOCAL_QUORUM, đọc ONE

Nếu write đã đạt quorum nhưng read sau đó chỉ dùng `ONE` và chọn đúng replica chưa kịp nhận cập nhật, read **vẫn có thể trả giá trị cũ**. Đây là lý do phải xét **cặp mức ghi/đọc**, không chỉ chọn mức ghi cao rồi giả định mọi reader đều đọc mới.

### 3.3. Ghi ở local DC, đọc từ DC khác

Với `NetworkTopologyStrategy` và `LOCAL_QUORUM`, write hoàn tất dựa trên quorum **local DC**, không nhất thiết đợi đủ các replica trong DC khác. Một read `LOCAL_ONE` hoặc `LOCAL_QUORUM` ở DC từ xa có thể có cửa sổ nhìn dữ liệu cũ nếu các replica tại đó chưa nhận cập nhật.

Đây là **độ lệch giữa các datacenter** của cùng partition, khác với việc application quên viết một bảng projection. Khi yêu cầu đọc xuyên DC ngay sau ghi, phải lập hợp đồng về DC sử dụng, CL và độ trễ hội tụ phù hợp; không suy rằng RF tại DC chính đã tự bảo đảm tính mới ở mọi vùng.

## 4. Nguyên nhân 2: node mất kết nối, chết hoặc quá chậm

Một replica có thể bỏ lỡ mutation vì:

- Node tắt máy, restart, gặp lỗi ổ đĩa hoặc hết tài nguyên.
- Mạng bị partition hoặc latency/jitter lớn, khiến thông điệp đến muộn.
- CPU, heap/GC, thread pool, disk I/O hoặc compaction backlog làm replica xử lý chậm.
- Quá nhiều request đồng thời làm hàng đợi quá dài, timeout hoặc bị từ chối.
- Một replica gặp lỗi khi ghi trong lúc các replica khác vẫn hoàn tất.

Nếu CL chỉ cần một phần replica xác nhận, coordinator có thể trả thành công dù một replica đang không khả dụng. Khi node quay lại, nó **không tự biết mọi mutation đã bỏ lỡ** chỉ vì quá trình restart hoàn tất. Cassandra có những cơ chế bắt kịp dữ liệu, nhưng từng cơ chế có điều kiện và phạm vi riêng.

### 4.1. Timeout không nói chắc mutation đã thất bại

Giả sử client gửi `UPDATE`, coordinator hoặc replica thực tế đã xử lý, nhưng ACK không đến client trước timeout. Client thấy lỗi timeout song mutation **có thể đã được áp dụng ở một hoặc nhiều replica**.

Đối với thao tác idempotent theo khóa cố định, ứng dụng có thể retry theo chính sách và đối soát kết quả. Nhưng retry **không an toàn mặc định** nếu nó:

- Tạo một `event_id` mới cho cùng sự kiện.
- Thay đổi partition key hoặc bucket do dùng thời điểm retry.
- Dùng timestamp mới làm một giá trị nghiệp vụ cũ thắng cập nhật mới.
- Làm mới TTL ngoài ý định hoặc tác động khác biệt tới thao tác collection/counter.

Phải phân biệt **client không nhận ACK** với **database chắc chắn chưa nhận mutation**.

## 5. Nguyên nhân 3: hinted handoff có phạm vi giới hạn

Khi coordinator biết một replica tạm thời không đáp ứng, Cassandra có thể lưu **hint** chứa mutation để chuyển lại cho replica ấy về sau, nếu tính năng và điều kiện của phiên bản/cấu hình cho phép.

```text
      Coordinator
          |
          +--> Replica A: ghi thành công
          +--> Replica B: ghi thành công
          +--> Replica C: đang down
                    |
             Coordinator giữ hint (nếu được phép)
                    |
             C trở lại -> phát lại hint
```

**Hinted handoff là cơ chế phục hồi nhanh kiểu best effort**, không phải một hàng đợi bền vững vô hạn và cũng **không thay thế repair**. Những điều kiện khiến hint có thể không đủ:

1. Replica vắng mặt lâu hơn cửa sổ hint được cấu hình.
2. Coordinator không còn giữ hint hoặc gặp sự cố trước khi phát.
3. Tính năng bị tắt, bị giới hạn, hoặc topology/loại replica có hạn chế.
4. Có những mutation không đi qua một coordinator còn giữ đủ thông tin để tạo hint.
5. Hints được chuyển nhưng vẫn còn sai khác cần đối chiếu ở cấp dữ liệu.

Không nên thiết kế SLA với giả định “mọi write bị bỏ lỡ chắc chắn sẽ được hints tự khôi phục”. Sau sự cố kéo dài cần đánh giá **repair có kế hoạch**, trạng thái replica và khả năng khôi phục thực tế.

## 6. Nguyên nhân 4: read repair chỉ phát hiện những gì lần đọc nhìn thấy

Khi một lần đọc tham chiếu tới các replica có dữ liệu khác nhau, Cassandra có thể đối chiếu digest/data và sửa sai khác được phát hiện trong **phạm vi đọc** theo cơ chế read repair của phiên bản/cấu hình.

Ví dụ:

```text
Replica A: status = PAID    (write timestamp mới hơn)
Replica B: status = PENDING (write timestamp cũ hơn)
Replica C: status = PAID

Read với nhiều replica:
  -> có thể phát hiện digest mismatch
  -> đối chiếu dữ liệu theo quy tắc Cassandra
  -> sửa dữ liệu có liên quan trên các replica tham gia
```

Điều cần nhớ:

- Read repair **không quét toàn bộ keyspace**; nó chỉ xuất phát từ những dữ liệu/cột/partition liên quan đến lần đọc.
- Một partition hoặc row **không bao giờ được đọc** có thể tiếp tục lệch nếu thiếu các cơ chế đồng bộ khác.
- Một số chiến lược read repair có thể **blocking** và ảnh hưởng độ trễ đọc; cấu hình và ngữ nghĩa cụ thể khác theo phiên bản Cassandra.
- Không phải lúc nào mọi replica đều tham gia một lần đọc, nhất là khi CL thấp.
- Read repair không thể tự tạo ra mutation của **một bảng nghiệp vụ khác** mà ứng dụng chưa từng gửi.

Vì vậy, đọc nhiều lần một vài key “thấy đều giống nhau” **không chứng minh** toàn bộ replica của mọi token range đã hội tụ.

## 7. Nguyên nhân 5: xung đột timestamp và đồng hồ không đồng bộ

Cassandra giải quyết các cập nhật tới cùng một cell thông thường dựa trên **write timestamp**, cùng những quy tắc xử lý tombstone và tie-break khi cần. Một write đến server **muộn hơn về thời gian thực** nhưng mang write timestamp **cũ hơn** có thể không thắng dữ liệu đang có.

Ngược lại, một event **cũ hơn về nghiệp vụ** nhưng đến sau và được gán timestamp mới có thể ghi đè giá trị hiện hành.

### 7.1. Ví dụ: cập nhật nghiệp vụ tới sai thứ tự

```text
Revision 10: order = PENDING (sự kiện xảy ra trước)
Revision 11: order = PAID    (sự kiện xảy ra sau)

Consumer áp dụng revision 11 trước.
Sau đó retry revision 10, gán write timestamp mới.

Kết quả có thể thành PENDING dù nghiệp vụ cần PAID.
Các replica còn có thể đồng bộ hoàn toàn về giá trị PENDING sai.
```

Đây là ví dụ quan trọng: **replica cùng một giá trị không đồng nghĩa nghiệp vụ đúng**. Một cột `revision bigint` được ghi kèm dữ liệu **không tự biến Cassandra thành bộ so sánh revision**. Ứng dụng cần nguồn trạng thái, quy tắc xử lý theo thứ tự ID, hoặc điều kiện cập nhật phù hợp.

### 7.2. Ảnh hưởng của clock skew

Timestamp có thể được sinh theo cơ chế phối hợp giữa client/driver và Cassandra tùy cấu hình. Nếu những writer có đồng hồ lệch đáng kể, một writer có đồng hồ **đi trước** có thể tạo timestamp rất lớn làm dữ liệu của writer khác khó ghi đè trong một khoảng thời gian.

Những triệu chứng có thể gặp:

- Thao tác mới hơn về nghiệp vụ không xuất hiện vì mang timestamp nhỏ hơn giá trị đã lưu.
- Một số replica có mutation tới chậm nhưng cuối cùng cùng hội tụ về winner theo timestamp.
- TTL và xóa có hành vi khó giải thích khi phối hợp với timestamp/clock lệch.

Đồng bộ thời gian node/client và giám sát clock drift là việc vận hành quan trọng. Tuy nhiên **đồng hồ đồng bộ không thay thế kiểm soát thứ tự nghiệp vụ** nếu sự kiện có thể được gửi lại sau khi đã có revision mới.

### 7.3. Dùng WRITETIME để điều tra

Với một regular column không phải counter, `WRITETIME(column)` có thể cho biết write timestamp Cassandra lưu cho ô đó, theo **microsecond**:

```sql
SELECT status, revision, WRITETIME(status) AS status_write_time
FROM replica_lab.orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

`WRITETIME` giúp phát hiện timestamp bất thường, nhưng không cho biết **thời gian nghiệp vụ** hay “node nào đã nhận trước”. Một giá trị timestamp mới không bảo đảm event mới về nghiệp vụ. Các quy tắc chức năng như `revision` vẫn phải được thiết kế và kiểm chứng riêng.

## 8. Nguyên nhân 6: DELETE, TTL, tombstone và nguy cơ dữ liệu xuất hiện lại

Trong hệ phân tán, xóa dữ liệu không chỉ là loại bỏ byte ở một replica. Cassandra dùng **tombstone** để biểu thị dữ liệu đã bị xóa/hết hạn và ngăn một replica còn dữ liệu cũ làm giá trị ấy xuất hiện trở lại.

### 8.1. Kịch bản xóa khi một replica đang down

```text
t0  A, B, C đều có row X.
t1  Replica C mất kết nối.
t2  Client DELETE X; A và B nhận tombstone, write đạt CL yêu cầu.
t3  C vẫn giữ giá trị X vì không nhận DELETE.
t4  C vắng mặt rất lâu; tombstone trên A/B có thể đủ điều kiện dọn.
t5  C quay lại với giá trị X cũ.
```

Nếu hệ thống **dọn tombstone trước khi replica bỏ lỡ delete được đồng bộ an toàn** và không có cơ chế khác bảo vệ, có nguy cơ **zombie/resurrection**: dữ liệu đã xóa xuất hiện lại.

Vì vậy:

- Lập lịch **repair** phù hợp để các replica không bỏ lỡ delete quá lâu.
- Giữ quy trình vận hành với node offline kéo dài, thay node và kiểm tra repair.
- Không giảm `gc_grace_seconds` tùy tiện chỉ để giảm số tombstone.
- Theo dõi TTL, tombstone, compaction và tuổi dữ liệu theo chính sách.

Chi tiết thời điểm có thể dọn tombstone phụ thuộc Cassandra version, compaction strategy, cấu hình và tình trạng repair/replica; không suy rằng chỉ cần chờ đúng một tham số là file SSTable sẽ lập tức biến mất.

### 8.2. TTL không giống xóa vật lý tức thì

Một ô có TTL sẽ hết hạn logic sau khoảng thời gian quy định. Dữ liệu hết hạn không nên được trả về như giá trị sống sau khi expiry có hiệu lực, nhưng SSTable/tombstone có thể còn nằm trên disk cho tới khi compaction và các điều kiện an toàn dọn được đáp ứng.

Hai replica có trạng thái SSTable khác nhau không nhất thiết có giá trị query khác nhau. Ngược lại, **clock skew** và các mutation liên quan tới TTL/ghi lại có thể khiến việc kiểm chứng khó hơn, cần thu cả timestamp, TTL, thời gian máy và log.

### 8.3. Compaction không phải repair giữa replica

**Compaction** chủ yếu tổ chức, hợp nhất và dọn SSTable trên node theo chính sách và điều kiện. Nó không tự liên hệ các replica khác để phát hiện mọi mutation bị thiếu.

**Repair** so sánh dữ liệu giữa các replica chịu trách nhiệm cho token ranges và đồng bộ sai khác theo thuật toán anti-entropy. Hai nhiệm vụ khác nhau; một node có thể compaction tốt mà vẫn thiếu mutation từng bị bỏ lỡ khi mạng lỗi.

## 9. Nguyên nhân 7: repair chưa đủ, bị gián đoạn hoặc lịch vận hành không phù hợp

Repair là cơ chế quan trọng để giảm sai lệch giữa các replica trong Cassandra. Tùy phiên bản và cấu hình, có thể dùng cơ chế **full/incremental repair** với những khác biệt về dữ liệu được bao phủ, trạng thái đã sửa và vận hành.

Những lý do replica vẫn lệch:

1. Repair chưa chạy cho token range/keyspace/table liên quan.
2. Repair bị lỗi, bị hủy giữa chừng hoặc không hoàn thành mọi phiên cần thiết.
3. Lịch repair dài hơn khoảng thời gian an toàn cho dữ liệu bị xóa/TTL, đặc biệt với node lâu không hoạt động.
4. Replica mới hoặc node phục hồi chưa được streaming/repair đầy đủ.
5. Đội vận hành chỉ nhìn một kết quả “repair thành công” nhưng không kiểm tra phạm vi, các job khác hoặc metric lỗi.
6. Nhầm **read repair** của một số truy vấn với **repair toàn bộ dữ liệu cần đồng bộ**.

### 9.1. Anti-entropy repair làm gì?

Ở mức khái niệm:

```text
Chọn token ranges + các replica liên quan
       |
       v
So sánh trạng thái dữ liệu (ví dụ Merkle trees/digest theo cơ chế)
       |
       +--> Đồng nhất: không cần truyền phần dữ liệu đó
       |
       +--> Khác nhau: đồng bộ dữ liệu liên quan
       |
       v
Hoàn tất, theo dõi trạng thái và lỗi từng phiên
```

Repair có thể gây tải CPU, disk I/O, network và compaction; không nên chạy đồng loạt toàn cụm sản xuất mà không có kế hoạch. Với version/topology cụ thể, chọn lịch, phạm vi và cách chạy theo quy trình vận hành đã được kiểm thử.

### 9.2. Repair không thay thế nguồn sự thật nghiệp vụ

Giả sử ứng dụng duy trì:

```text
orders_by_id               -> trạng thái đơn hiện tại
orders_by_customer_month   -> danh sách theo khách/tháng
orders_by_status_day       -> hàng đợi trạng thái
```

Nếu consumer quên ghi `orders_by_status_day` sau khi `orders_by_id` đã cập nhật, các replica của **bảng trạng thái** có thể hoàn toàn đồng nhất về dữ liệu **thiếu**. Repair sẽ không biết phải tự tạo thêm hàng nào dựa trên bảng ID.

Đây là **projection consistency** cần durable event, retry/idempotency và reconciliation ở ứng dụng. Không gán mọi sai khác giữa hai API cho “replica Cassandra chưa đồng bộ”.

## 10. Nguyên nhân 8: thay đổi topology, streaming và khoảng thời gian chuyển quyền

Khi thêm node, thay node, decommission hoặc di chuyển token ranges, dữ liệu phải được **stream** tới những node mới chịu trách nhiệm. Trong quá trình chuyển đổi, có thể có pending ranges, replica cũ/mới và các giai đoạn dữ liệu chưa được phân bổ hoàn chỉnh.

Những điểm cần kiểm:

- Token/range nào đang đổi chủ và những replica nào chịu trách nhiệm sau thao tác?
- Streaming đã hoàn tất thành công chưa? Có lỗi/timeout hoặc node đích thiếu tài nguyên không?
- Có thể có những ghi mới phát sinh trong khi topology thay đổi; cơ chế hệ thống phải bảo đảm chúng được xử lý theo trạng thái ring hiện hành.
- Repair hoặc bước kiểm tra bổ sung có cần sau khi thay node không, theo phiên bản/quy trình của cụm?
- Ứng dụng có đang dùng topology/datacenter cũ trong driver, hoặc route qua DC không dự kiến không?

Không nên tự di chuyển token, xóa SSTable hay thao tác ring để “ép replica giống nhau” trên production khi chưa xác định nguyên nhân và kế hoạch. Streaming và repair là các thao tác vận hành có thể tốn nhiều I/O/network, cần đặt giới hạn và quan sát.

## 11. Nguyên nhân 9: hiểu sai về LWT, BATCH, counter và denormalization

Một số tình huống nhìn giống “replica khác nhau” nhưng thực chất do **ngữ nghĩa thao tác** hoặc **mô hình ứng dụng**:

| Tình huống | Nhầm lẫn phổ biến | Cách hiểu đúng |
| --- | --- | --- |
| Hai writer update cùng một status | Nghĩ write đến cuối theo đồng hồ thực luôn thắng | Cassandra giải quyết theo write timestamp và quy tắc cell; cần kiểm soát version nghiệp vụ |
| `IF revision = ?` bằng LWT | Nghĩ mọi bảng của đơn cũng được update giao dịch | LWT kiểm soát điều kiện trong phạm vi áp dụng; không tạo SQL transaction xuyên projection |
| Logged `BATCH` qua nhiều partition | Nghĩ mọi reader thấy snapshot tất cả hoặc không có gì | Batch có ngữ nghĩa atomicity phục hồi nhưng **không có isolation SQL xuyên partition** |
| Counter tăng và bị retry sau timeout | Nghĩ an toàn như upsert cùng một giá trị | Counter có ngữ nghĩa đặc biệt; retry không tùy tiện như ghi idempotent |
| Ghi theo ID, đọc theo status từ bảng khác | Nghĩ CL mạnh sẽ làm bảng status tự có dữ liệu | Hai representation có đường mutation riêng, cần pipeline và đối soát |
| `WRITETIME` lớn hơn | Nghĩ đây chắc là event nghiệp vụ mới | Đây là timestamp ghi cell; không suy ra trình tự nghiệp vụ |

Khi cần tính nhất quán mạnh hơn cho một hàng có điều kiện, **LWT/CAS** có thể phù hợp nhưng có chi phí và giới hạn. Không dùng LWT hoặc batch làm “thuốc chữa mọi độ lệch” mà bỏ qua mapping partition, dữ liệu đến muộn và lỗi từng phần.

## 12. Ma trận nguyên nhân – triệu chứng – cơ chế xử lý

| Nguyên nhân | Quan sát thường gặp | Cơ chế/kiểm tra phù hợp |
| --- | --- | --- |
| CL ghi/đọc thấp, cập nhật đang lan truyền | Đọc ONE có lúc mới, lúc cũ | Xem CL/RF/topology, thử readback theo hợp đồng |
| Node down khi ghi | Một replica giữ giá trị cũ | Trạng thái node, hints, repair và thời gian offline |
| Mạng timeout, ACK mất | Client báo timeout nhưng dữ liệu có thể đã đổi | Readback, idempotency, log và retry policy |
| Hints hết hạn hoặc không đầy đủ | Node trở lại nhưng vẫn thiếu nhiều ghi | Đánh giá lịch repair và trạng thái dữ liệu |
| Read repair chưa chạm partition | Key ít đọc vẫn có replica lệch | Anti-entropy repair thay vì chỉ đọc thử vài key |
| Timestamp/clock skew | Update mới về nghiệp vụ không thắng | `WRITETIME`, đồng hồ, source revision và writer |
| Tombstone bị dọn khi replica chưa nhận delete | Dữ liệu xóa có nguy cơ hiện lại | Kiểm tra downtime, grace, repair, TTL và compaction |
| Repair thiếu phạm vi hoặc lỗi | Sai khác tồn tại lâu | Repair history, token ranges, failures và metrics |
| Streaming/topology thay đổi chưa hoàn tất | Node mới thiếu dữ liệu hoặc lỗi read/write | `nodetool status/netstats`, ring và kế hoạch recovery |
| App thiếu mutation ở bảng phụ | Hai API trả trạng thái khác nhau | Outbox/event log, reconciliation theo nguồn nghiệp vụ |

## 13. Phòng thí nghiệm CQL an toàn để quan sát

Thí nghiệm nên chạy trong **cluster lab riêng**, không tạo lỗi node/mạng hoặc thay consistency trên production tùy tiện. Dưới đây là schema ví dụ của một DC có **ít nhất ba node** và tên DC thực tế cần thay cho `dc1`.

### 13.1. Khởi tạo keyspace và bảng

```sql
-- Chỉ dùng trong cluster thử nghiệm; thay dc1 bằng tên DC thực.
CREATE KEYSPACE replica_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE replica_lab.orders_by_id (
    tenant_id text,
    order_id uuid,
    status text,
    revision bigint,
    changed_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
```

Một hàng dễ đối chiếu:

```sql
INSERT INTO replica_lab.orders_by_id (
    tenant_id, order_id, status, revision, changed_at
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    'PENDING', 1, '2026-11-21T09:00:00Z'
);
```

### 13.2. Quan sát mức nhất quán của cqlsh

Trong **cqlsh**, `CONSISTENCY` là lệnh cấu hình consistency level của phiên làm việc; nó **không** phải câu CQL chạy bên trong Java driver:

```sql
CONSISTENCY ONE;

SELECT status, revision, changed_at, WRITETIME(status) AS write_ts
FROM replica_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;

CONSISTENCY LOCAL_QUORUM;

SELECT status, revision, changed_at, WRITETIME(status) AS write_ts
FROM replica_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;
```

Trên một cluster khỏe, cả hai truy vấn có thể trả **cùng dữ liệu**. Đó là kết quả bình thường. Độ lệch phải được tạo ra bằng tình huống node/mạng phù hợp trong lab và **không bảo đảm xuất hiện ở mọi lần đọc ONE**.

### 13.3. Kịch bản node vắng mặt có kiểm soát

Kế hoạch thí nghiệm khái niệm:

1. Xác định ba replica thật của partition bằng công cụ cluster phù hợp với phiên bản; ghi lại topology và CL.
2. Bảo đảm dữ liệu ban đầu đọc nhất quán, thu timestamp và metric.
3. Trong môi trường thử **có quyền kiểm soát node**, làm một replica tạm thời không thể nhận mutation; ghi lại thời điểm bắt đầu.
4. Gửi update `status = PAID` với CL đủ thấp để thao tác vẫn có thể thành công trên replica còn khả dụng.
5. Đọc bằng `ONE` và `LOCAL_QUORUM` ở những thời điểm được ghi nhận, so kết quả và latency. Không kỳ vọng ONE phải thấy cũ hay quorum lúc nào cũng thành công khi thiếu replica.
6. Cho replica trở lại; quan sát hinted handoff nếu có, read behavior, và quy trình repair theo hướng dẫn phiên bản.
7. Đối chiếu kết quả sau phục hồi, log/metric và loại bỏ mọi cấu hình thử nghiệm.

Đặt timeout và tải thấp, không tắt nhiều replica cùng lúc khiến cluster lab không thể đáp ứng CL cần thử. Thí nghiệm có quyền kiểm soát lỗi node **không phải lời khuyên gây gián đoạn trên production**.

### 13.4. Minh họa xung đột write timestamp tách biệt với replica lag

Trong một bảng thử **khác key** để tránh nhiễu, ghi hai bản với write timestamp CQL do lab quy định:

```sql
-- Timestamp CQL là microsecond; chỉ minh họa trên một key thử.
UPDATE replica_lab.orders_by_id
USING TIMESTAMP 1700000001000000
SET status = 'PAID', revision = 2
WHERE tenant_id = 'tenant-lab'
  AND order_id = 00000000-0000-4000-8000-000000000099;

-- Ghi đến sau nhưng mang timestamp thấp hơn.
UPDATE replica_lab.orders_by_id
USING TIMESTAMP 1700000000000000
SET status = 'PENDING', revision = 1
WHERE tenant_id = 'tenant-lab'
  AND order_id = 00000000-0000-4000-8000-000000000099;

SELECT status, revision, WRITETIME(status)
FROM replica_lab.orders_by_id
WHERE tenant_id = 'tenant-lab'
  AND order_id = 00000000-0000-4000-8000-000000000099;
```

Kỳ vọng status vẫn là `PAID` và revision vẫn là 2, bởi timestamp ghi `PAID` lớn hơn, dù lệnh `PENDING` chạy sau. Điều này **không kiểm tra replica lag**; nó chỉ cho thấy thứ tự apply và timestamp nghiệp vụ là hai khái niệm khác nhau.

Không dùng `USING TIMESTAMP` kiểu tùy ý trong production để “ép” dữ liệu thắng xung đột. Timestamp không thay thế một giao thức kiểm soát revision/chuyển trạng thái.

## 14. Java Driver 4.x: ghi/đọc với CL rõ ràng

Trong Java, consistency level nên được đặt bằng API của driver trên từng statement hoặc profile, không dựa vào lệnh `CONSISTENCY` của cqlsh. Ví dụ minh họa sử dụng **DataStax Java Driver 4.x**:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.util.UUID;

public final class ReplicaConsistencyProbe {
    private final CqlSession session;
    private final PreparedStatement upsert;
    private final PreparedStatement read;

    public ReplicaConsistencyProbe(CqlSession session) {
        this.session = session;
        this.upsert = session.prepare(
            "INSERT INTO replica_lab.orders_by_id (" +
            "tenant_id, order_id, status, revision, changed_at) " +
            "VALUES (?, ?, ?, ?, ?)"
        );
        this.read = session.prepare(
            "SELECT status, revision, changed_at, " +
            "WRITETIME(status) AS status_write_time " +
            "FROM replica_lab.orders_by_id " +
            "WHERE tenant_id = ? AND order_id = ?"
        );
    }

    public void writeWithLocalQuorum(
        String tenantId, UUID orderId,
        String status, long revision, Instant changedAt
    ) {
        session.execute(
            upsert.bind(tenantId, orderId, status, revision, changedAt)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        );
    }

    public Row readWithOne(String tenantId, UUID orderId) {
        return session.execute(
            read.bind(tenantId, orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
        ).one();
    }

    public Row readWithLocalQuorum(String tenantId, UUID orderId) {
        return session.execute(
            read.bind(tenantId, orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        ).one();
    }
}
```

**Phạm vi của ví dụ:** đây là mã thăm dò một bảng ở lab, không phải cơ chế transaction hay hệ thống xử lý lỗi hoàn chỉnh.

- `CqlSession` nên được tạo theo vòng đời dịch vụ, dùng chung thay vì mở kết nối mỗi request.
- `UUID` ánh xạ kiểu CQL `uuid`, `Instant` ánh xạ `timestamp`; `Row` có thể là `null` nếu key không tồn tại.
- Nếu cluster không có đủ replica đáp ứng `LOCAL_QUORUM` tại local DC, write/read có thể thất bại; không tự diễn giải timeout là “chưa ghi”.
- Retry cùng key là upsert, nhưng nếu tạo revision/status mới từ stale source có thể gây ghi lùi nghiệp vụ. Phải có source revision và chính sách idempotency.
- Khi cần khảo sát divergence giữa replica, cần quan sát topology/routing và server metrics; hai lần gọi method `readWithOne` không bảo đảm hai request chạm hai replica khác nhau.
- Hãy đo latency, lỗi, thời điểm gọi và kết quả cùng nhau; không chỉ log `status` rồi tự kết luận replica nào sai.

### 14.1. Lỗi network và retry

Một client thấy timeout có thể đang ở trạng thái **unknown outcome**. Ví dụ handler:

```text
write(order, version, stableKey)
    |
    +-- success -> xác nhận theo CL
    |
    +-- timeout -> KHÔNG tự tạo version/event_id mới
                    ghi metric + đối soát readback
                    retry có kiểm soát theo idempotency contract
                    tránh ghi lùi khi đã có version mới
```

Driver có retry policy, nhưng ứng dụng vẫn chịu trách nhiệm về ngữ nghĩa nghiệp vụ, đặc biệt với counter, collection, TTL và nhiều bảng projection. Không retry vô hạn hoặc cho request lỗi tạo bão ghi trong thời gian node đang phục hồi.

## 15. Runbook chẩn đoán replica khác nhau

Khi có báo cáo “đọc cùng khóa nhưng kết quả khác” hoặc “dữ liệu đã xóa lại xuất hiện”, nên đi theo thứ tự để tránh xử lý sai:

### 15.1. Bước 1 — xác định cùng một dữ liệu hay hai projection

Ghi:

```text
keyspace
table
full partition key
clustering key (nếu có)
column/value
requested consistency level
datacenter / client location
query timestamp
source event ID / business revision
```

Nếu hai màn hình đọc hai bảng khác nhau, trước tiên kiểm tra **đường ghi và độ trễ đồng bộ projection**. Không chạy repair toàn cụm chỉ vì hai bảng không khớp.

### 15.2. Bước 2 — kiểm tra topology và khả dụng

Thu trạng thái ring/node theo phiên bản Cassandra:

```text
nodetool status
nodetool netstats
nodetool tpstats
nodetool compactionstats
```

`nodetool` trên là tên công cụ/thao tác gợi ý, không phải một script tự chạy. Kiểm tra DC, RF, các replica đang UP/DOWN, streaming/hints, pending tasks, disk saturation, CPU/GC và network. Với một key cụ thể, cần xác định đúng **tập replica của token range** thay vì suy từ thứ tự node trong dashboard.

### 15.3. Bước 3 — xác định lớp lỗi

| Câu hỏi | Nếu có | Hướng tiếp |
| --- | --- | --- |
| Có node/down hoặc network lỗi trong thời gian ghi? | Có | Xem hints, repair window, readback sau hồi phục |
| Client có write timeout/unknown outcome? | Có | Không kết luận write thất bại; đối chiếu key/version |
| Đọc ONE và QUORUM khác nhau trên cùng key? | Có thể | Xem replica lag, thời điểm và CL, không bỏ qua write đang chạy |
| `WRITETIME` bất thường so với event version? | Có | Điều tra clock drift và producer timestamps |
| Dữ liệu DELETE/TTL từng bị bỏ lỡ? | Có | Tombstone/grace/repair, nguy cơ resurrection |
| Có thay node/streaming chưa hoàn tất? | Có | Kiểm tra topology, streaming/repair |
| Hai API đọc hai bảng projection? | Có | Durable event log/reconciliation, không chỉ replica repair |

### 15.4. Bước 4 — chọn phục hồi phù hợp

- Replica chỉ chậm ngắn hạn, hints còn hiệu lực: quan sát quá trình bắt kịp theo cấu hình, xác nhận dữ liệu sau đó.
- Node down dài hoặc bỏ lỡ mutation: đánh giá **repair/restore/replace** theo runbook phiên bản, trước hết kiểm tra dung lượng và phạm vi.
- Timestamp nghiệp vụ sai: sửa **nguồn phát mutation và quy tắc version**; repair chỉ làm các replica cùng nhìn winner theo timestamp.
- Tombstone có nguy cơ dọn sai: **ưu tiên bảo toàn dữ liệu và điều tra**, không tự ép compaction hoặc giảm grace.
- Bảng phụ thiếu hàng: replay/reconcile từ nguồn được tin cậy, không dựa vào repair replica.

Tránh chạy cùng lúc repair, full compaction, streaming và backfill nặng mà không tính CPU, disk, I/O và network. Những thao tác này có thể làm sự cố tải hiện tại nặng hơn.

### 15.5. Bước 5 — xác nhận đã phục hồi

Không chỉ xác nhận một `SELECT` trả đúng một lần. Cần bằng chứng:

1. Tập node/replica ổn định; streaming/repair liên quan đã hoàn tất và không còn lỗi quan trọng.
2. Đọc theo CL được yêu cầu trong những khoảng thời gian xác định, đối chiếu cùng key/column/timestamp và phiên bản.
3. Không còn backlog bất thường của hints/repair, timeout hoặc dropped mutations.
4. Dữ liệu đã xóa/TTL không xuất hiện lại trong ca kiểm thử có liên quan.
5. Nếu ứng dụng có projection, các invariant nghiệp vụ đã được đối soát riêng.

## 16. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| “RF=3 nên mọi node luôn giống nhau” | Không nhận diện cửa sổ lệch và lỗi replica | Phân biệt RF với CL và cơ chế hội tụ |
| “ONE chỉ ghi một replica” | Hiểu sai đường ghi | ONE xác định số ACK cần chờ, coordinator có thể gửi rộng hơn |
| “Write QUORUM thì read ONE luôn mới” | Có thể đọc replica chưa nhận write | Xem cặp R/W và giao thoa quorum |
| “Read repair sẽ sửa cả cluster” | Các partition chưa đọc vẫn có thể lệch | Repair theo token ranges, có lịch vận hành |
| “Hints bảo đảm mọi mutation bị mất đều được trả lại” | Node offline lâu vẫn thiếu dữ liệu | Hints là best effort, không thay repair |
| “Timeout nghĩa là write chưa xảy ra” | Retry sai làm dữ liệu trùng/ghi lùi | Unknown outcome, idempotency và readback |
| “Cell có revision cao sẽ tự thắng” | Cassandra không tự so revision nghiệp vụ | CAS/sequence/source of truth |
| “Giảm grace để tiết kiệm disk” | Nguy cơ zombie/resurrection | Xây lịch repair/xóa an toàn |
| “Compaction sẽ đồng bộ replica” | Mutation thiếu vẫn có thể tồn tại | Phân biệt compaction vs anti-entropy repair |
| “LWT hoặc logged batch làm mọi bảng atomic/isolated” | Quan sát dữ liệu nghiệp vụ cập nhật từng phần | Hiểu phạm vi giao dịch, dùng retry/reconcile |
| “Hai SSTable khác byte = dữ liệu sai” | Báo động giả do flush/compaction khác thời điểm | So giá trị logic, timestamp, tombstone |
| “Quorum là consistent snapshot của nhiều partition” | Ứng dụng đọc trạng thái không đồng thời | Định nghĩa transaction/business invariant riêng |

## 17. Bài tập thực hành

Một cụm Cassandra lab có keyspace một DC, **RF=3** với replica A/B/C. Dữ liệu nguồn là trạng thái đơn:

```text
tenant_id = T
order_id = O1
status = PENDING
revision = 9
```

Giả sử:

- A, B, C ban đầu cùng giữ revision 9.
- Khi C bị mất kết nối, ứng dụng ghi revision 10 với `status = PAID` bằng `LOCAL_QUORUM`.
- A và B xác nhận; client nhận thành công.
- Một thời gian sau, C trở lại, nhưng chưa chắc đã nhận đủ thay đổi trong lúc mất kết nối.
- Ứng dụng còn có bảng `orders_by_status_day` được cập nhật bằng consumer bất đồng bộ.

**Yêu cầu:**

1. Giải thích vì sao write `LOCAL_QUORUM` có thể thành công khi C không đáp ứng. Số ACK tối thiểu là bao nhiêu nếu RF local = 3?
2. Một read `ONE` trên cùng row có thể thấy revision 9 hay 10 không? Vì sao không thể khẳng định chắc chắn nó sẽ thấy một giá trị cụ thể?
3. Một read `LOCAL_QUORUM` có điều kiện giao thoa thế nào với write thành công ở A/B? Điều này có chứng minh C đã đồng bộ không?
4. Nếu C offline rất lâu và hinted handoff không còn đủ, cơ chế nào cần được lên kế hoạch để đồng bộ replica?
5. Giả sử một `DELETE` cũng bị C bỏ lỡ. Hãy nêu vai trò tombstone, grace và lịch repair; chuyện gì có thể xảy ra nếu dấu xóa bị thu hồi trước khi C nhận thông tin xóa?
6. Một consumer xử lý revision 11 (`SHIPPED`) trước, rồi xử lý muộn revision 10 (`PAID`) với write timestamp mới. Các replica cuối cùng có thể hoàn toàn giống nhau nhưng **sai nghiệp vụ** không? Cần sửa bằng gì?
7. Bảng `orders_by_id` hiển thị `PAID` nhưng bảng `orders_by_status_day` vẫn có hàng `PENDING`. Vì sao anti-entropy repair Cassandra không tự giải quyết việc này?
8. Viết CQL tạo keyspace/table lab và hai truy vấn readback dưới `ONE` và `LOCAL_QUORUM`. Nêu những metric/log cần thu trước khi kết luận.

**Gợi ý đối chiếu:**

- Với RF=3 tại một DC, local quorum là **2 ACK**. A+B có thể đủ để write hoàn tất dù C không phản hồi.
- Read `ONE` có thể được định tuyến tới replica đã nhận hoặc chưa nhận mutation; kết quả phụ thuộc thời điểm, routing và tình trạng hội tụ.
- Hai tập quorum size 2 giao nhau ít nhất một replica, nhưng không có nghĩa replica C chắc chắn đã bắt kịp hay các bảng phụ đồng bộ tức thì.
- Hinted handoff là best effort trong một cửa sổ/điều kiện giới hạn; repair là cơ chế anti-entropy cần được lập lịch khi replica có thể bỏ lỡ dữ liệu.
- Tombstone bảo vệ xóa; nếu dấu xóa mất khi một replica còn dữ liệu cũ, có nguy cơ dữ liệu đã xóa xuất hiện lại.
- Revision nghiệp vụ phải được kiểm soát ở nguồn, ví dụ xử lý tuần tự hoặc CAS/LWT phù hợp. Timestamp write không tự biết event nào xảy ra sau.
- Bảng theo ID và bảng theo status là **hai projection có mutation riêng**; cần durable event, retry/idempotency và reconciliation cấp nghiệp vụ, khác với repair giữa replica của một partition.

## Kết luận

Replica Cassandra có thể khác nhau do **đường ghi chưa lan truyền xong, consistency level, node/mạng lỗi, hints không đầy đủ, read repair chưa chạm dữ liệu, timestamp xung đột, TTL/DELETE/tombstone, repair thiếu phạm vi hoặc thay đổi topology**. RF quyết định số bản sao; CL quyết định mức xác nhận cần chờ; còn hinted handoff, read repair, anti-entropy repair và streaming giúp hội tụ theo những phạm vi khác nhau. Điều quan trọng là luôn tách **độ lệch giữa replica của cùng partition** khỏi **dữ liệu sai nghiệp vụ hoặc thiếu mutation giữa các bảng query-driven**. Chẩn đoán đúng khóa, timestamp, CL, topology và log trước khi sửa; duy trì repair, an toàn tombstone, retry có kiểm soát và đối soát nghiệp vụ để hệ thống vừa phục vụ được khi lỗi vừa giữ dữ liệu đáng tin cậy.
