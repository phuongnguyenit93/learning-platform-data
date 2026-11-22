# Nguy cơ dữ liệu cũ xuất hiện lại khi bản sao bị bỏ sót xóa trong Apache Cassandra

> **Chương:** Tombstone và thu hồi  
> **Phạm vi:** Apache Cassandra phân tán với nhiều replica, ghi/xóa bằng CQL, tombstone, `gc_grace_seconds`, hinted handoff, repair, compaction, TTL và các trường hợp mất node. Đích học tập là hiểu **zombie data** (dữ liệu bị xóa nhưng xuất hiện lại) và cách phòng ngừa trong thực tế vận hành.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Giải thích vì sao Cassandra **ghi một dấu xóa (tombstone)** thay vì xóa vật lý ngay tại mọi replica.
2. Dựng lại chuỗi sự kiện khiến một bản sao bỏ lỡ DELETE và về sau phát tán **dữ liệu cũ** sang các replica khác.
3. Phân biệt **stale read trước khi đồng bộ** với **zombie data sau khi tombstone đã được thu hồi**.
4. Nắm vai trò và giới hạn của **consistency level (CL), hinted handoff, anti-entropy repair, gc_grace_seconds và compaction**.
5. Biết khi nào một node vắng mặt quá lâu **không nên được đưa trở lại cluster với dữ liệu cũ mà không có kế hoạch khôi phục**.
6. Thiết kế runbook và bài thực hành CQL/Java để kiểm tra xóa trên cluster, quan sát tombstone và phòng ngừa zombie.

Đây là một tình huống đặc thù của cơ sở dữ liệu **wide-column phân tán**: cùng partition có thể nằm trên nhiều node, dữ liệu được thiết kế theo truy vấn và các replica không nhất thiết nhận mutation cùng thời điểm. Vì vậy hiểu tombstone là điều kiện để vận hành Cassandra an toàn, bên cạnh replication, consistency, repair và compaction.

## 2. Điều gì thực sự xảy ra khi DELETE?

Khi ứng dụng gửi:

~~~sql
DELETE FROM shop.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Cassandra không mở tất cả SSTable hiện có để xóa hàng tại chỗ. Nó ghi một **tombstone**, tức metadata mang ý nghĩa “dữ liệu tại vị trí này đã bị xóa ở một timestamp cụ thể”.

Ở một replica, dữ liệu đi qua **commit log và memtable**, rồi được flush thành **SSTable bất biến**. SSTable chứa phiên bản cũ vẫn có thể còn trên đĩa. Khi đọc, Cassandra hòa giải dữ liệu và tombstone theo quy tắc timestamp, TTL và phạm vi xóa để quyết định cái gì còn sống.

~~~text
Tại replica A:

SSTable cũ                     Memtable / SSTable mới
order-111 -> state='PAID'       order-111 -> TOMBSTONE (ts=200)
             ts=100
                  \                /
                   \  hòa giải    /
                    v            v
                      Không trả hàng
~~~

Hai ý quan trọng:

- **Xóa logic**: từ góc nhìn CQL, tombstone có timestamp mới hơn sẽ che dữ liệu cũ. Người dùng không còn thấy hàng đó ở replica đã nhận xóa.
- **Thu hồi vật lý**: chỉ trong những điều kiện an toàn, compaction mới bỏ tombstone và dữ liệu cũ đã bị che, giải phóng đĩa. Thu hồi không đồng nghĩa diễn ra ngay sau DELETE.

Tombstone không chỉ được tạo bởi DELETE toàn hàng; DELETE cột, xóa tập con dữ liệu và **TTL hết hạn** cũng dẫn đến trạng thái xóa theo phạm vi tương ứng.

### 2.1. Những loại tombstone thường gặp

| Loại | Trường hợp tạo điển hình | Phạm vi che dữ liệu |
|---|---|---|
| Cell tombstone | `DELETE state ...`, ghi `null` cho cột | Một ô/cột cụ thể |
| Row tombstone | `DELETE FROM ... WHERE` với đầy đủ khóa hàng | Các cell thuộc hàng đó |
| Range tombstone | Xóa nhiều clustering rows trong một khoảng khóa | Một dải row của partition |
| Partition tombstone | Xóa toàn bộ partition bằng partition key | Dữ liệu trong partition |
| TTL-expired tombstone | Cell có TTL hết hạn | Giá trị đã hết thời hạn |

Mọi ví dụ trên đều phải xét **timestamp**. Một ghi mới với timestamp lớn hơn dấu xóa có thể hợp lệ xuất hiện lại vì đó là **mutation mới**, khác với zombie do replica giữ dữ liệu **cũ** mà đã mất tombstone bảo vệ.

## 3. Tình huống zombie data: ba replica, một replica bỏ lỡ DELETE

Xét một keyspace ở một datacenter với **RF=3**, các natural replica của partition `tenant-a` là A, B, C. Ban đầu cả ba chứa bản ghi `order-111` với timestamp `t=100`.

### 3.1. Diễn tiến từng giai đoạn

~~~text
                       RF = 3, partition tenant-a

T0: Trước DELETE
    A: [order-111, ts=100]
    B: [order-111, ts=100]
    C: [order-111, ts=100]

T1: Node C mất kết nối
    DELETE order-111 (tombstone ts=200), CL=QUORUM
    A: [tombstone ts=200]    ACK
    B: [tombstone ts=200]    ACK
    C: [order-111, ts=100]   KHÔNG nhận xóa
    => Client được báo DELETE thành công vì QUORUM=2/3.

T2: C vắng mặt lâu, không nhận được tombstone qua
    hinted handoff, repair hoặc cơ chế đồng bộ phù hợp.
    A và B vẫn dùng tombstone để che giá trị cũ.

T3: Sau khi gc_grace_seconds đã trôi qua, nếu compaction
    đủ điều kiện dọn tombstone và dữ liệu bị che trên A/B:
    A: [không còn tombstone]
    B: [không còn tombstone]
    C: [order-111, ts=100]   <-- bản sao cũ vẫn còn

T4: C trở lại; read/repair/streaming có thể nhìn thấy
    [order-111, ts=100] mà KHÔNG còn tombstone ts=200
    để phủ định nó. Dữ liệu cũ có thể được truyền lại.
    => ZOMBIE DATA: order-111 xuất hiện trở lại.
~~~

Đây là **kịch bản có điều kiện**, không có nghĩa cứ qua đúng `gc_grace_seconds` thì mọi tombstone lập tức biến mất. Việc purge thực tế còn phụ thuộc **compaction** và quy tắc kiểm tra các SSTable có dữ liệu/tombstone chồng lấn. Nguy cơ xảy ra khi **tất cả bản sao chứa tombstone có ích đã loại bỏ nó**, trong khi còn một replica giữ dữ liệu cũ chưa được xóa.

### 3.2. Bảng thời gian: trạng thái cục bộ và kết quả client

| Mốc | A | B | C | Điều client có thể quan sát |
|---|---|---|---|---|
| Trước DELETE | Dữ liệu sống | Dữ liệu sống | Dữ liệu sống | Đọc thấy hàng |
| Sau DELETE QUORUM thành công | Tombstone | Tombstone | Dữ liệu cũ, chưa nhận DELETE | Đọc `ONE` có thể thấy kết quả cũ nếu chạm C |
| Trước khi purge, sau repair thành công | Tombstone | Tombstone | Tombstone | Đọc nhất quán nhìn thấy xóa |
| Không repair và tombstone trên A/B bị purge | Không còn dấu xóa | Không còn dấu xóa | Dữ liệu cũ | Rủi ro zombie thực sự |
| Sau khi C tái phát tán dữ liệu | Có thể có dữ liệu cũ | Có thể có dữ liệu cũ | Dữ liệu cũ | Hàng bị xóa có thể xuất hiện trở lại |

**Phân biệt hai hiện tượng:**

1. **Stale read**: C chưa nhận tombstone, nên một lần đọc từ C có thể trả giá trị cũ, *trong lúc A/B vẫn giữ dấu xóa*. Một repair kịp thời vẫn có thể sửa tình trạng này.
2. **Zombie resurrection**: dấu xóa đã bị loại khỏi các bản sao có thể dùng để chữa C; giá trị cũ trên C không còn bị chặn và có thể lây sang replica khác. Khi đó repair thông thường **không thể biết đó từng là dữ liệu đã xóa**.

Đây là lý do câu “DELETE với QUORUM thành công nên vĩnh viễn không thể có dữ liệu cũ” là sai: QUORUM cho biết đủ số replica xác nhận thao tác ở thời điểm ghi, **không chứng minh tất cả replica đã nhận mutation**.

## 4. Vì sao Cassandra cần tombstone và khoảng grace?

SSTable immutable và replication bất đồng bộ có nghĩa một node tạm mất liên lạc vẫn có thể giữ dữ liệu phiên bản cũ. Tombstone là **bằng chứng xóa mang timestamp** để khi node trở lại, replica mới hơn có thể thông báo cho replica cũ rằng giá trị đó không còn hợp lệ.

Nếu xóa ngay dữ liệu lẫn tombstone tại A/B ở T1, cluster mất bằng chứng mà C cần nhận. Vì vậy Cassandra giữ tombstone trong một khoảng thời gian cấu hình.

### 4.1. `gc_grace_seconds` là gì?

`gc_grace_seconds` là thuộc tính **từng bảng** quy định khoảng grace trước khi tombstone *có thể* được garbage collect trong quá trình compaction. Giá trị mặc định thường là **864000 giây (10 ngày)** trên Apache Cassandra; hãy kiểm tra thực tế bằng `DESCRIBE TABLE` vì cấu hình bảng có thể đã được thay đổi.

~~~sql
DESCRIBE TABLE shop.orders;

-- Tham số cấu hình bảng, ví dụ:
-- ... WITH gc_grace_seconds = 864000 ...
~~~

Một cách hình dung:

~~~text
DELETE ghi tombstone
      |
      |<---- gc_grace_seconds ---->|
      v                            v
   Tombstone được giữ         Tombstone BẮT ĐẦU
   để replica khác học xóa    đủ tuổi để CÂN NHẮC purge
                                    |
                                    v
                      Chỉ khi compaction và điều kiện
                      an toàn cho SSTable thỏa mãn
~~~

**Không diễn giải sai:** `gc_grace_seconds=864000` không hứa “dữ liệu được xóa vật lý chính xác sau 10 ngày”, không là thời hạn bảo lưu dữ liệu cho người dùng, và **không tự thực hiện repair**. Đây là một phần cơ chế an toàn **trước khi** compaction có thể thu hồi dấu xóa.

### 4.2. Khi nào tombstone mới được purge?

Ngoài việc tombstone đã qua grace, compaction phải bảo đảm việc bỏ nó **không để dữ liệu cũ trong SSTable khác của cùng node sống lại**. Cassandra kiểm tra quan hệ giữa những SSTable được compact và các SSTable có dữ liệu/token range chồng lấn ngoài tập compaction.

Ví dụ tại A:

~~~text
SSTable-A1: order-111 = 'PAID' (ts=100)
SSTable-A2: tombstone order-111 (ts=200)

Compaction chỉ xử lý A2:
  Không thể tùy ý bỏ tombstone nếu A1 vẫn chứa hàng cũ.

Compaction đủ điều kiện xử lý dữ liệu bị che:
  Có thể loại cả tombstone lẫn giá trị cũ khi quy tắc
  thời gian/grace và overlapping SSTable cho phép.
~~~

Điều kiện purge giúp **an toàn cục bộ** trên node. Nhưng Cassandra không thể luôn biết rằng C đang mất mạng vẫn còn dữ liệu cũ. Vì vậy **repair kịp thời trên toàn bộ replica** là yếu tố vận hành quan trọng để ngăn zombie giữa các node.

### 4.3. Giảm `gc_grace_seconds` có tác dụng và rủi ro gì?

| Cấu hình | Lợi ích có thể đạt | Rủi ro/điều kiện |
|---|---|---|
| Giá trị mặc định (thường 10 ngày) | Cho thêm thời gian để repair và node lỗi trở lại | Tombstone giữ lâu, ảnh hưởng đĩa và đọc |
| Grace ngắn hơn | Tombstone có thể được purge sớm hơn khi compaction đủ điều kiện | **Ít thời gian hơn** để sửa replica bỏ lỡ DELETE |
| `gc_grace_seconds=0` | Có thể dọn dấu xóa nhanh hơn | **Rủi ro zombie cao** nếu replica có thể bỏ lỡ xóa; không nên áp dụng đại trà |
| Grace rất dài | Cho thêm thời gian repair | Tombstone tích tụ, làm tăng tombstone scan/compaction burden |

Không nên hạ grace chỉ vì báo cáo có nhiều tombstone. Trước hết tìm **nguồn sinh tombstone**, điều kiện lọc truy vấn, lịch repair, trạng thái replica, pattern TTL và compaction strategy.

## 5. Hinted handoff và repair: hai cơ chế khác nhau

Tại T1, coordinator có thể giữ **hint** cho C khi C đang không phản hồi, để thử gửi lại mutation khi node hồi phục. Hinted handoff là cơ chế giúp khắc phục các lần ghi bỏ lỡ **ngắn hạn**.

~~~text
DELETE được gửi tới A/B/C
                 |
           C không trả lời
                 |
         Coordinator lưu hint (nếu được bật/hợp lệ)
                 |
         C trở lại đủ sớm
                 |
         Gửi lại hint => C có tombstone
~~~

Nhưng hint **không phải kho lưu vĩnh viễn**:

- Bị giới hạn bởi cấu hình, khoảng thời gian giữ hint và dung lượng/khả năng lưu trên coordinator.
- Không thể bảo đảm mọi lần ghi lỗi đều có hint hoặc hint đã được giao thành công.
- Thời gian giữ hint thông thường **ngắn hơn** `gc_grace_seconds`; cấu hình như `max_hint_window` cần kiểm tra theo phiên bản.
- Việc một lần DELETE thành công với CL đã chọn không chứng minh bản sao bị lỗi sẽ được chữa chỉ bằng hints.

**Anti-entropy repair** là cơ chế đối chiếu dữ liệu giữa replica theo token range, thường dùng Merkle tree và streaming những khác biệt. Khi A/B vẫn giữ tombstone, repair có thể truyền dấu xóa cho C để nó loại bản ghi cũ.

| Cơ chế | Mục đích | Có thể ngăn zombie trong ví dụ không? | Giới hạn |
|---|---|---|---|
| Hinted handoff | Phát lại mutation tạm bỏ lỡ | Có, nếu tombstone đến C trước khi mất dấu xóa | Không bao phủ mọi downtime |
| Read repair | Sửa một số khác biệt phát hiện trong quá trình đọc | Có thể, khi đọc và reconciliation thực sự thấy tombstone | Chỉ các key/đường đọc được chạm tới; phiên bản Cassandra khác nhau |
| Anti-entropy repair | Đối chiếu replica theo range có kế hoạch | **Biện pháp chủ đạo** để bảo đảm mọi dữ liệu/tombstone đã đồng bộ trong phạm vi dự kiến | Phải hoàn tất trên mọi range/replica trước khi hết grace |
| Compaction | Hợp nhất SSTable và thu hồi dữ liệu đủ điều kiện | Không tự sửa replica C đang mất mạng | Có thể làm mất tombstone cần cho C nếu repair bị bỏ lỡ |
| Backup/snapshot | Cung cấp bản phục hồi | Hỗ trợ khôi phục khi đã lệch | Snapshot không tự biết bản ghi nào đã xóa |

**Repair định kỳ không phải lời hứa suông:** cần giám sát *repair đã thực sự thành công, bao phủ tất cả token range cần thiết*. Nếu repair chạy nhưng thất bại ở C, không được coi C đã được chữa.

## 6. Consistency level bảo vệ điều gì?

Với ba bản sao đầy đủ trong một DC:

- `ONE`: thao tác ghi hoặc đọc cần một phản hồi phù hợp.
- `QUORUM`: cần hai phản hồi trong RF=3.
- `ALL`: cần cả ba phản hồi để thao tác ở mức ALL thành công.
- `LOCAL_QUORUM`: tính quorum **trong datacenter cục bộ** khi dùng nhiều DC; khác `QUORUM` tính trên tổng RF.

Quan hệ quen thuộc `R + W > RF` giúp hai tập phản hồi đọc/ghi giao nhau **trong các giả định phù hợp về replica, topology và mutation**. Nhưng nó không đảm bảo rằng một replica vắng mặt đã nhận tombstone, và **không ngăn zombie sau khi tombstone đã bị purge**.

Trong ví dụ RF=3:

| DELETE CL | Có thể thành công khi C down? | Có giúp xóa vĩnh viễn mà không cần repair? |
|---|---|---|
| `ONE` | Có, nếu A phản hồi | Không |
| `QUORUM` | Có, nếu A và B phản hồi | Không |
| `ALL` | **Không**, nếu C không phản hồi | Không thể dùng khi replica down; ngay cả khi thành công cũng cần lịch bảo trì/repair cho lỗi tương lai |

Tăng CL của DELETE có thể thu hẹp tình huống ghi được xác nhận nhưng nhiều replica chưa nhận, song đánh đổi bằng **độ sẵn sàng**. Đó không phải giải pháp thay cho anti-entropy repair hoặc xử lý node mất kết nối.

### 6.1. Vì sao `SELECT QUORUM` cũng chưa đủ?

Ngay sau DELETE ở A/B, một đọc QUORUM theo đúng điều kiện có thể hòa giải tombstone với dữ liệu C và trả kết quả đúng. Nhưng khi tất cả bản sao khỏe còn lại đã purge tombstone, **không còn giá trị mới hơn để hòa giải với dữ liệu cũ từ C**. Tăng CL lúc đó không khôi phục được thông tin xóa đã mất.

Nếu chạy một vòng repair **sau khi** tombstone cần thiết đã bị purge, dữ liệu cũ có thể được coi là bản hợp lệ và nhân sang nơi khác. Repair không có nhật ký vĩnh viễn ghi lại mọi DELETE để phân biệt zombie.

## 7. Thiết kế lịch repair an toàn theo grace period

Nguyên tắc vận hành là: **mọi replica có thể giữ dữ liệu cũ phải có cơ hội nhận tombstone trước khi tombstone ở những replica khỏe bị thu hồi**. Do đó, thông lệ là hoàn tất repair toàn bộ phạm vi cần thiết **thường xuyên hơn `gc_grace_seconds`**, với đủ khoảng đệm cho lịch chậm, node lỗi và repair retry.

Ví dụ một bảng có `gc_grace_seconds=864000` (10 ngày):

~~~text
Ngày 0: DELETE ở A/B; C bỏ lỡ.
Ngày 2: repair được lên lịch nhưng thất bại ở range của C.
Ngày 4: retry repair thành công; C nhận tombstone.
Ngày 10+: compaction có thể purge tombstone đủ điều kiện.

=> Đã sửa C kịp thời, nguy cơ zombie từ mutation này giảm.
~~~

Ngược lại:

~~~text
Ngày 0: DELETE ở A/B; C bỏ lỡ.
Ngày 8: repair thất bại nhưng monitoring không báo động.
Ngày 10+: compaction đủ điều kiện làm mất tombstone ở A/B.
Ngày 15: C mới trở lại và repair chạy.

=> Repair ngày 15 có thể đã quá muộn.
~~~

Không thiết kế lịch kiểu “repair đúng ngày thứ 10” khi grace là 10 ngày. Hãy dành **khoảng đệm lớn** cho sự cố kéo dài và thời gian repair đầy đủ của một cluster lớn.

### 7.1. Repair phải phủ toàn bộ dữ liệu có nguy cơ

Trong cluster dùng **NetworkTopologyStrategy**, mỗi DC có RF riêng. Lịch repair cần bảo đảm các khoảng token, bảng và replica liên quan đều được đồng bộ, kể cả các DC có thể không phải DC mà ứng dụng Java đặt làm local datacenter.

~~~bash
# Minh họa lệnh repair theo primary ranges.
# Điều phối chạy lần lượt trên các node/DC liên quan.
nodetool repair --full -pr zombie_lab orders
~~~

Chạy `-pr` trên **một node** chỉ sửa primary ranges được giao cho node/lệnh đó, **không** khẳng định keyspace đã repair toàn cluster. Muốn dùng full repair, incremental repair hay công cụ điều phối repair chuyên dụng phải dựa vào phiên bản Cassandra và chính sách vận hành thực tế; điểm bắt buộc là **coverage đã thực sự đạt**.

| Tín hiệu cần theo dõi | Vì sao ảnh hưởng zombie? |
|---|---|
| Thời điểm repair thành công cuối cùng của **mọi range** | Biết range nào có thể đã quá lâu không đồng bộ |
| Node down/unreachable theo DC | Replica thiếu tombstone có thể nằm ngoài tầm repair |
| Repair failure, timeout, streaming error | Job được lên lịch nhưng dữ liệu chưa đến replica lỗi |
| `gc_grace_seconds` của **từng bảng** | Mỗi bảng có thời gian cho phép thu hồi khác nhau |
| Trạng thái hinted handoff | Hint không giao được thì không thể coi replica đã nhận DELETE |
| Compaction backlog và tombstone metrics | Ảnh hưởng thời điểm purge và chi phí đọc |
| Snapshot/backup cùng tuổi dữ liệu | Restore snapshot quá cũ có thể mang dữ liệu trước DELETE trở lại |

### 7.2. Phải định nghĩa tình trạng “repair thành công”

Một lịch tự động chạy mỗi ngày nhưng có 20% range fail **không** đủ bảo đảm. Với mỗi lần repair nên lưu:

1. Phạm vi keyspace/table, token range, DC/node.
2. Thời điểm bắt đầu/kết thúc, kiểu repair và phiên bản Cassandra.
3. Kết quả thành công/thất bại theo phạm vi, log lỗi và hành động retry.
4. Tuổi repair lâu nhất so với grace nhỏ nhất của các bảng quan trọng.
5. Các node bị cô lập hoặc vừa phục hồi sau downtime.

Đặt cảnh báo **trước khi** tuổi repair chạm grace. Nếu một DC bị cô lập trong khi DC khác vẫn nhận xóa, ưu tiên xử lý khả năng đồng bộ liên DC, không chỉ xem các node trong local DC đã hoạt động trở lại.

## 8. Node vắng mặt quá lâu: vì sao không nên đưa dữ liệu cũ trở lại tùy tiện?

Giả sử C down 14 ngày nhưng bảng có grace 10 ngày. Khi C trở lại, có thể nó vẫn giữ giá trị `order-111` trong SSTable cũ. A/B có thể đã purge dấu xóa.

**Hành động nguy hiểm:** Khởi động C với dữ liệu cũ, để nó tham gia đọc/repair/streaming bình thường rồi mới xem có lỗi hay không. Nếu tombstone đã biến mất ở các replica khác, việc đưa C trở lại có thể làm tăng khả năng zombie.

**Cách ra quyết định an toàn hơn:**

1. **Cô lập tình huống:** Ghi nhận thời gian node mất kết nối, tables/ranges nó phụ trách, grace của từng bảng và liệu có DELETE/TTL trong khoảng đó.
2. **Kiểm tra bằng chứng:** Các bản sao còn lại còn giữ tombstone không? Repair nào đã hoàn thành trong thời gian C vắng mặt? Hints còn đủ không? Có bản ghi xóa ở nguồn sự thật của ứng dụng không?
3. **Không tin dữ liệu cũ của node là chính xác:** Nếu node đã qua grace hoặc trạng thái không thể xác minh, cân nhắc **thay node/rebuild/bootstrap từ các replica khỏe** theo runbook topology/version hiện hành, thay vì đưa trực tiếp SSTable cũ vào vòng hòa giải.
4. **Kiểm chứng hậu phục hồi:** Đọc dữ liệu từng bị xóa theo danh sách kiểm tra, xác minh range và chạy repair thích hợp sau khi topology ổn định.
5. **Điều tra sai lệch đã xảy ra:** Nếu zombie đã xuất hiện, dùng log nghiệp vụ hoặc hệ thống ghi nhận xóa độc lập để xác định bản nào đúng, rồi sửa có kiểm soát.

Quyết định cụ thể giữa `replace_address`, rebuild, bootstrap, loại node khỏi ring và nạp dữ liệu mới **phụ thuộc phiên bản, topology và tình trạng cluster**. Đừng áp dụng một lệnh “xóa dữ liệu node” chung khi chưa chắc node, token ranges và nguồn phục hồi. Với RF thấp hoặc nhiều replica cùng lỗi, bản sao còn lại cũng có thể không đủ dữ liệu để khôi phục.

### 8.1. Dữ liệu zombie đã xuất hiện thì repair có sửa được không?

Không thể trông chờ repair tự biết ý định xóa. Nếu tombstone `ts=200` đã mất ở mọi nơi, dữ liệu cũ `ts=100` nhìn giống một giá trị đang sống. Repair có thể đồng bộ **sai trạng thái** này sang nhiều replica.

Các bước điều tra khi phát hiện bản ghi đã xóa tái xuất hiện:

| Câu hỏi | Bằng chứng đáng tin |
|---|---|
| DELETE thật sự đã được thực thi và ACK chưa? | Log ứng dụng, sự kiện nghiệp vụ, idempotency key, write audit |
| Thời gian mutation so với grace? | Cấu hình bảng tại thời điểm đó, timeline node/repair |
| Node nào chưa nhận tombstone? | Repair/streaming/hints log và trạng thái replica |
| Dữ liệu xuất hiện lại là zombie hay ghi mới? | Mutation timestamp, sự kiện tạo mới, audit trail |
| Mức ảnh hưởng bao rộng? | Danh sách primary key liên quan, token ranges và DC |
| Có thể khôi phục ý định xóa? | Nguồn sự thật độc lập, CDC hoặc sổ sự kiện ứng dụng |

Sau khi xác minh, có thể cần **ghi một DELETE mới** trên dữ liệu zombie qua CQL, phân phối nó tới các replica liên quan, repair và xác minh kết quả. Không ghi DELETE mù trên phạm vi lớn: có thể xóa nhầm các cập nhật hợp lệ mới hơn. Nếu hệ thống không có log ý định xóa thì **không phải lúc nào có thể suy ra 100%** hàng nào cần xóa từ dữ liệu Cassandra còn lại.

## 9. TTL, compaction và các trường hợp dễ ngộ nhận

### 9.1. TTL cũng tạo trạng thái xóa

~~~sql
INSERT INTO zombie_lab.orders
    (tenant_id, order_id, status)
VALUES ('tenant-a',
        22222222-2222-2222-2222-222222222222,
        'TEMPORARY')
USING TTL 300;
~~~

Sau 300 giây, giá trị có TTL hết hiệu lực và về mặt CQL không còn sống. Tombstone/metadata hết hạn vẫn cần đi qua các quy tắc storage và compaction; điều đó không có nghĩa file SSTable bị xóa ngay ở giây thứ 300.

**Tình huống nguy hiểm cần hiểu:** TTL và DELETE đều cần được áp dụng nhất quán giữa replica. Với dữ liệu TTL, thời gian hết hạn đã được ghi cùng giá trị, nên replica giữ bản sao có TTL vẫn biết thời hạn đó; tuy nhiên các mutation bổ sung, timestamp, repair và tổ hợp TTL/DELETE có thể tạo trạng thái phức tạp. Không dùng suy luận “mọi replica đều tự biết TTL nên mọi trường hợp zombie đã được giải quyết” để bỏ repair.

### 9.2. Range tombstone có thể che nhiều row

Giả sử bảng có partition `tenant_id` và clustering `created_at`:

~~~sql
CREATE TABLE zombie_lab.events_by_tenant (
    tenant_id text,
    created_at timestamp,
    event_id uuid,
    details text,
    PRIMARY KEY ((tenant_id), created_at, event_id)
);

-- Xóa các row thuộc một khoảng clustering trong partition.
DELETE FROM zombie_lab.events_by_tenant
WHERE tenant_id = 'tenant-a'
  AND created_at >= '2026-01-01T00:00:00Z'
  AND created_at < '2026-02-01T00:00:00Z';
~~~

Câu lệnh này chỉ mang tính minh họa cho **xóa theo clustering range**; cú pháp/ràng buộc WHERE DELETE phụ thuộc primary key và phiên bản CQL. Trong trường hợp khóa clustering có thêm `event_id`, có thể cần điều chỉnh phép xóa theo quy tắc range được phiên bản hỗ trợ. Điểm cần nhớ là **một range tombstone có thể che nhiều row**, nên bản sao bỏ lỡ nó có thể khiến một tập lớn hàng cũ xuất hiện lại.

### 9.3. Những yếu tố vận hành ảnh hưởng thời điểm purge

| Yếu tố | Tác động |
|---|---|
| `gc_grace_seconds` | Quy định thời gian tối thiểu trước khi tombstone đủ điều kiện thu hồi |
| Compaction strategy | Quyết định SSTable nào được hợp nhất và khi nào |
| Overlapping SSTables | Có thể ngăn purge tombstone nếu SSTable chưa compact còn chứa dữ liệu cũ |
| Tombstone ở nhiều phiên bản | Cần hòa giải đúng timestamp/deletion time |
| Repair state và chính sách purge của phiên bản | Có thể ảnh hưởng điều kiện thu hồi ở cấu hình nâng cao |
| Snapshot | Có thể giữ file vật lý cũ trên đĩa, dù dữ liệu sống đã được thay thế |
| Tình trạng replica khác | Không phải luôn được compaction cục bộ xác nhận; vì thế lịch repair vẫn quan trọng |

### 9.4. Đồng hồ và timestamp không thể bỏ qua

Cassandra dùng **write timestamp** để hòa giải mutation. Nếu ứng dụng tự cấp timestamp sai lệch lớn, một DELETE có timestamp thấp hơn bản ghi khác có thể không che được bản ghi đó. Đó là **lỗi thứ tự timestamp** chứ không nhất thiết là zombie do tombstone bị thu hồi.

Trong production, cần giám sát đồng bộ đồng hồ node và hạn chế cấp timestamp thủ công từ nhiều nguồn không phối hợp. Phân tích hiện tượng hàng “xuất hiện lại” phải kiểm tra cả **source of timestamps** và lịch sử mutation, không chỉ nhìn `gc_grace_seconds`.

## 10. Bài thực hành CQL có kiểm soát

Thực hành dùng **cluster lab ít nhất ba node** cùng DC `dc1`, tất cả node hoạt động và cho phép repair/flush/compaction có kiểm soát. Không chủ động tạo zombie trên production, không hạ grace về 0 để chứng minh nguy cơ.

### Bước 1 — Tạo bảng có RF=3

~~~sql
CREATE KEYSPACE IF NOT EXISTS zombie_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': '3'
};

CREATE TABLE IF NOT EXISTS zombie_lab.orders (
    tenant_id text,
    order_id uuid,
    status text,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id), order_id)
) WITH gc_grace_seconds = 86400;
~~~

**Chỉ dùng tên `dc1` nếu đúng tên DC thực tế**. Grace 86400 giây (một ngày) chỉ để rút ngắn khung thời gian thảo luận trong lab, **không phải giá trị khuyến nghị production**. Cluster lab phải có ít nhất ba node đủ điều kiện trong DC. Với cluster nhiều DC, lệnh ALTER/CREATE cần phản ánh đầy đủ các DC; ví dụ này chỉ dùng một DC.

### Bước 2 — Ghi dữ liệu và đọc trước khi xóa

~~~sql
CONSISTENCY QUORUM;

INSERT INTO zombie_lab.orders
    (tenant_id, order_id, status, updated_at)
VALUES ('tenant-a',
        11111111-1111-1111-1111-111111111111,
        'PAID', '2026-11-21T00:00:00Z');

SELECT order_id, status, updated_at
FROM zombie_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Quorum trong lab RF=3 cần hai phản hồi. Cần kiểm tra cả bảng đang có dữ liệu đúng và các node ở trạng thái **Up/Normal** trước bài thực hành tiếp.

### Bước 3 — Xóa rồi xác nhận kết quả logic

~~~sql
DELETE FROM zombie_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT order_id, status
FROM zombie_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Nếu DELETE QUORUM thành công và replica hoạt động bình thường, SELECT QUORUM phải không trả hàng sống ở khóa đó. **Đó là kiểm tra trạng thái hiện thời**, không chứng minh tombstone đã được giao cho cả ba replica hoặc sẽ tồn tại đủ lâu nếu một node vắng mặt.

### Bước 4 — Quan sát tombstone và trạng thái node

~~~bash
nodetool status
nodetool tablestats zombie_lab.orders
nodetool compactionstats
~~~

`tablestats` có chỉ số về SSTable, tombstone trung bình của các lần đọc/metric liên quan tùy phiên bản; một bảng ít dữ liệu có thể không hiện số đáng kể. Dùng metrics/log/tracing để quan sát **chi phí** của tombstone, không dựa vào một counter để suy ra mọi replica đã nhận xóa.

Trong lab, có thể bật tracing khi cần kiểm tra một truy vấn:

~~~sql
TRACING ON;

SELECT order_id, status
FROM zombie_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

TRACING OFF;
~~~

Tracing tăng overhead, chỉ bật cho truy vấn kiểm tra chọn lọc. Các công cụ `sstablemetadata`/reader offline có thể giúp nhìn metadata tombstone nhưng phải tuân thủ yêu cầu về dừng daemon theo phiên bản và chỉ dùng trên node lab.

### Bước 5 — Giả lập bỏ lỡ DELETE (chỉ lab cô lập)

Nếu môi trường lab có công cụ điều khiển node an toàn, thiết kế kịch bản kiểm tra:

1. Ghi dữ liệu đầy đủ trên ba replica, xác minh RF và token range.
2. Ngắt **một** node C trong lab, giữ A/B hoạt động.
3. Gửi DELETE với CL QUORUM, ghi lại kết quả ACK.
4. Khôi phục C **trước khi grace hết hạn**, theo dõi hinted handoff.
5. Thực hiện **repair có phạm vi đầy đủ** để kiểm tra C nhận tombstone.
6. Đọc lại khóa ở các node theo phương pháp kiểm chứng đã thiết kế; ghi nhận không còn dữ liệu sống.

**Không cần cố tình giữ node down qua grace và ép compaction để làm zombie xảy ra.** Điều quan trọng của bài là hiểu vì sao bước 5 (repair kịp thời) ngăn nguy cơ, và vì sao kết quả DELETE QUORUM ở bước 3 chưa đủ.

### Bước 6 — Repair và xác minh phạm vi

~~~bash
# Minh họa, chạy theo lịch trên TỪNG node của cluster lab
# để phủ primary ranges liên quan; không chạy đồng thời tùy tiện.
nodetool repair --full -pr zombie_lab orders
~~~

Đối chiếu output của tất cả lần chạy, ghi rõ node/range nào hoàn tất. Sau repair, kiểm tra lại:

~~~sql
CONSISTENCY QUORUM;

SELECT order_id, status
FROM zombie_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Nếu không có node nào bị cô lập quá lâu và repair thành công, kết quả mong đợi vẫn là không có hàng sống. **Không chạy repair rồi suy ra ngay toàn bộ nguy cơ zombie lịch sử đã biến mất**: điều đó chỉ đúng với phạm vi và tombstone còn đủ dữ liệu để repair.

## 11. Ứng dụng Java nên xử lý DELETE thế nào?

Java Driver 4.x cho phép gán CL cho từng câu lệnh. Trong ví dụ này, client có thể kiểm soát DELETE QUORUM và sau đó đọc QUORUM để kiểm tra trạng thái; nhưng việc client nhận ACK **không thay thế lịch repair của cluster**.

~~~java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderDeletion {
    // CqlSession đã được tạo với local datacenter chính xác và được tái sử dụng.
    public static boolean deleteAndCheck(
            CqlSession session, String tenantId, UUID orderId) {
        PreparedStatement delete = session.prepare(
                "DELETE FROM zombie_lab.orders " +
                "WHERE tenant_id = ? AND order_id = ?");

        BoundStatement del = delete.bind(tenantId, orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        session.execute(del);

        PreparedStatement select = session.prepare(
                "SELECT order_id FROM zombie_lab.orders " +
                "WHERE tenant_id = ? AND order_id = ?");

        Row row = session.execute(
                select.bind(tenantId, orderId)
                      .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM))
                .one();
        return row == null;
    }
}
~~~

**Phạm vi của `deleteAndCheck`:** `true` chỉ phản ánh rằng câu SELECT ngay sau đó **không nhìn thấy hàng** theo CL của request. Nó không chứng minh C đã nhận tombstone, tất cả DC đã repair hay hàng sẽ không bao giờ bị zombie.

Với ứng dụng cần kiểm soát việc xóa vì yêu cầu nghiệp vụ/bảo mật, nên cân nhắc:

- **Audit log hoặc event ID xóa độc lập:** giữ bằng chứng ý định xóa, key và thời điểm; hỗ trợ phát hiện/khắc phục zombie sau lỗi kéo dài.
- **Idempotency và retry rõ ràng:** DELETE gửi lại sau timeout có thể đã được áp dụng một phần; ghi nhận kết quả và retry theo chính sách phù hợp.
- **CL phù hợp topology:** `LOCAL_QUORUM` chỉ yêu cầu quorum DC cục bộ, không xác nhận DC xa đã nhận DELETE.
- **Giám sát của dịch vụ:** thống kê node down, tuổi repair, kết quả truy vấn trước/sau xóa; không chỉ dựa vào trạng thái HTTP 200 của API.
- **Dữ liệu được mô hình hóa theo truy vấn:** nếu một entity được nhân bản ra **nhiều bảng do ứng dụng duy trì**, xóa trong một bảng không tự động tạo tombstone ở bảng còn lại. Đó là một lớp lỗi khác với zombie giữa replica của **cùng bảng**.

Tránh dùng timestamp CQL được client tự cấp một cách thiếu điều phối, nhất là khi nhiều service viết cùng partition. Một DELETE với timestamp cũ hơn một INSERT/UPDATE hợp lệ sẽ không che giá trị mới hơn; đây là vấn đề thứ tự ghi cần phân tích tách biệt.

## 12. Runbook phòng ngừa và ứng phó trên production

### 12.1. Trước khi có sự cố

1. **Inventory bảng:** lấy `gc_grace_seconds`, RF, DC, compaction strategy, các bảng có TTL/delete dày, các nguồn CDC/audit.
2. **Repair schedule:** bảo đảm repair phủ range theo chu kỳ **ngắn đáng kể hơn grace**, có cảnh báo khi job fail hoặc node unavailable.
3. **Node outage SLA:** xác định thời gian vắng mặt tối đa trước khi bắt buộc điều tra lại dữ liệu node thay vì cho join bình thường.
4. **Backup/restore:** thử phục hồi từng bảng và cả topology; tránh restore snapshot cũ rồi trộn với dữ liệu mới mà không xét deletion.
5. **Quan sát:** collect logs của DELETE errors, hints, repair, streaming và tombstone warnings; đo read p95/p99, tombstones scanned, compaction.
6. **Cân nhắc giới hạn grace:** chỉ thay sau khi chứng minh repair coverage, failure window và tính chất workload; ghi lại lý do thay đổi.

### 12.2. Khi node không liên lạc được

**Trong thời gian grace và trước khi mất bằng chứng xóa:** ưu tiên đưa node trở lại bằng quy trình vận hành được hỗ trợ, xác nhận hints/repair và lưu kết quả. Nếu node đã mất lâu gần grace, cần quyết định hành động **trước khi** tombstone có thể được purge; không coi “node Up/Normal” là bằng chứng replica đã đồng bộ.

**Nếu downtime vượt grace hoặc không thể xác minh lịch sử:** cô lập nguy cơ dữ liệu cũ, thu thập thông tin và xem xét khôi phục node bằng dữ liệu hiện hành từ replica đáng tin cậy. Không tự làm sạch tất cả snapshot, không xóa SSTable bằng tay và không mở traffic trước khi phạm vi dữ liệu được đánh giá.

### 12.3. Sau khi phát hiện zombie

1. **Khoanh vùng:** keyspace, table, primary key, DC, mốc DELETE, node tham gia, token ranges.
2. **Phân biệt nguyên nhân:** tombstone GC quá sớm, repair fail, snapshot restore cũ, timestamp sai, write mới hợp lệ, hay duplication ở nhiều bảng.
3. **Tìm nguồn sự thật:** event xóa, log audit, metadata nghiệp vụ; không giả định bản ghi đang có trong Cassandra là trạng thái đúng.
4. **Khắc phục:** tạo mutation xóa/sửa mới theo danh sách bản ghi đã xác minh, phân phối tới replica, repair và kiểm tra trên nhiều CL/DC.
5. **Ngăn tái diễn:** điều chỉnh lịch repair, node replacement policy, grace, hints và quy trình nâng cấp/khôi phục.
6. **Kiểm chứng lâu dài:** theo dõi cùng tập khóa qua chu kỳ compaction và repair sau khắc phục.

Đối với dữ liệu nhạy cảm đã được yêu cầu xóa, đừng khẳng định việc xóa đã hoàn tất ở toàn hệ thống nếu mới chỉ xác nhận một SELECT từ một DC. Việc xóa ở backup, CDC, data lake hoặc bảng denormalized cũng là các quy trình riêng cần theo dõi.

## 13. Những ngộ nhận thường dẫn tới zombie data

| Nhận định sai | Điều đúng |
|---|---|
| “DELETE là xóa dữ liệu vật lý trên mọi node ngay lập tức.” | DELETE tạo tombstone; SSTable cũ vẫn có thể chứa dữ liệu. |
| “QUORUM thành công nghĩa là cả 3 replica đã xóa.” | RF=3, quorum chỉ yêu cầu 2 phản hồi. |
| “Hints sẽ được giữ đến khi node quay lại dù mất nhiều tuần.” | Hints có giới hạn lưu giữ, không thay thế repair. |
| “Một lần repair trên một node là đủ cho mọi token range.” | Phải bảo đảm **toàn bộ phạm vi được repair**. |
| “Hết 10 ngày là tombstone lập tức biến mất.” | Grace chỉ quyết định đủ tuổi; purge phụ thuộc compaction và điều kiện dữ liệu chồng lấn. |
| “Nếu compaction đã purge tombstone thì repair luôn sửa được.” | Repair không còn biết DELETE cũ khi dấu xóa mất. |
| “Tombstone và dữ liệu cũ cùng nằm trên một SSTable thì không có rủi ro.” | Cần xét SSTable khác và các replica khác, không chỉ file cục bộ. |
| “`gc_grace_seconds=0` luôn an toàn nếu đọc với QUORUM.” | Replica bị mất xóa vẫn có thể gây zombie sau purge. |
| “Node Down hơn grace cứ restart cho join rồi chạy repair.” | Node có thể mang dữ liệu đã xóa trở lại; cần đánh giá/khôi phục phù hợp. |
| “Mọi dữ liệu xuất hiện sau DELETE đều là zombie.” | Có thể là UPDATE hợp lệ mới hơn hoặc lỗi timestamp của ứng dụng. |
| “TTL loại dữ liệu khỏi ổ đĩa đúng tại giây hết hạn.” | TTL kết thúc tính sống; thu hồi vật lý xảy ra sau theo compaction. |
| “Xóa một entity trong Cassandra cũng tự xóa mọi bảng khác.” | Mỗi bảng denormalized có vòng đời mutation riêng nếu ứng dụng tự nhân bản dữ liệu. |

## 14. Câu hỏi tự đánh giá

**Câu 1.** Với RF=3, C down, DELETE QUORUM trả thành công. Điều gì đã được xác nhận và điều gì chưa?  
**Gợi ý:** A/B ACK; chưa chứng minh C nhận tombstone.

**Câu 2.** Sau một ngày, SELECT ONE từ C trả hàng đã xóa nhưng A/B vẫn có tombstone. Đây đã là zombie chưa?  
**Gợi ý:** Trước hết đó là **stale read**; repair có thể còn sửa được C.

**Câu 3.** Tại sao ngày thứ 11 mới chạy repair có thể quá muộn khi grace=10 ngày?  
**Gợi ý:** Compaction ở A/B có thể đã purge dấu xóa trước đó.

**Câu 4.** Đặt `gc_grace_seconds=0` và tăng DELETE CL lên ALL có đủ thay repair không?  
**Gợi ý:** Không có bảo đảm dài hạn trong điều kiện node lỗi và thời điểm purge khác nhau; ALL cũng làm ghi không khả dụng khi một replica down.

**Câu 5.** Hinted handoff khác anti-entropy repair ở điểm nào?  
**Gợi ý:** Hints phát lại mutation lỗi tạm thời; repair đối chiếu dữ liệu theo token range.

**Câu 6.** Vì sao compaction có thể giữ tombstone dù đã quá grace?  
**Gợi ý:** Một SSTable chồng lấn ngoài tập compaction có thể vẫn chứa dữ liệu cũ bị che.

**Câu 7.** Khi node cũ trở lại sau 15 ngày với grace 10 ngày, hành động nào nên tránh?  
**Gợi ý:** Không cho node mang SSTable cũ tham gia repair/đọc ngay mà chưa đánh giá nguy cơ.

**Câu 8.** `LOCAL_QUORUM` DELETE trên cluster hai DC có chứng minh DC còn lại nhận xóa không?  
**Gợi ý:** Không, nó chỉ yêu cầu quorum của DC cục bộ.

**Câu 9.** Tại sao repair đã thành công sau khi zombie lan rộng không đủ chứng minh dữ liệu đúng?  
**Gợi ý:** Repair đồng bộ dữ liệu hiện thấy, không phục hồi ý định xóa đã mất.

**Câu 10.** Khi SELECT trả hàng sau DELETE, cần so sánh những thông tin gì trước khi xóa lại?  
**Gợi ý:** Mutation timestamp, audit DELETE, lịch sử ghi mới, trạng thái replica, repair, snapshot/restore.

## 15. Tổng kết

~~~text
                     DELETE
                        |
              Ghi tombstone ở replica
                   /          \
         Replica nhận       Replica bỏ lỡ
          tombstone           DELETE
             |                  |
     Grace period đang chạy     |
             |                  |
   Repair/hints truyền dấu xóa--+
             |
       Mọi replica hội tụ
             |
        Compaction đủ điều kiện
             |
     Tombstone có thể được purge
             |
        [Đường đi an toàn]

Ngược lại:
   Replica bỏ lỡ xóa + không repair kịp
                 +
   Tombstone đã bị purge ở replica khỏe
                 |
      Replica cũ trở lại / streaming
                 |
        ZOMBIE DATA có thể xuất hiện
~~~

**Nguyên tắc trọng tâm:** Tombstone là bằng chứng xóa trong một hệ thống nhiều bản sao; `gc_grace_seconds` cho thời gian để đồng bộ dấu xóa, còn **repair có coverage và node recovery đúng hạn** mới giữ cho các replica cùng biết điều đó. Khi bằng chứng xóa đã biến mất trước khi replica cũ được chữa, dữ liệu bị xóa có thể xuất hiện lại và không thể phân biệt khỏi dữ liệu hợp lệ chỉ bằng repair.

## Tài liệu tham khảo

- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — zombie data, grace period, TTL và thu hồi tombstone.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy repair, incremental/full repair, primary range và lịch vận hành.
- [Apache Cassandra — CQL data manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — DELETE, TTL, mutation timestamp và tính nhất quán của ghi.
- [Apache Cassandra — Storage engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtable, SSTable bất biến và compaction.
- [Apache Cassandra — cassandra.yaml configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — hinted handoff và các tham số vận hành cần đối chiếu đúng phiên bản.
- [Apache Cassandra — CREATE TABLE](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) — thuộc tính bảng, `gc_grace_seconds` và compaction.
