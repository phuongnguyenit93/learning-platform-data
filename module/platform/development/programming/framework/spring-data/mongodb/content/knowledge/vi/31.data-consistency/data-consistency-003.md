# Write concern, majority, journal và xác nhận ghi

> **Chương:** Nhất quán dữ liệu  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Giải thích chính xác khi nào MongoDB xác nhận một thao tác ghi; so sánh `w:0`, `w:1`, `w:"majority"` và `j:true`; hiểu journal, replication, rollback, `wtimeout` và write concern error; cấu hình qua MongoDB Java Driver, `MongoTemplate`/repository/reactive; chọn chính sách phù hợp với tính bền vững dữ liệu và kiểm thử hành vi.

## 1. Câu hỏi cốt lõi: `insert` thành công thì dữ liệu đã an toàn chưa?

Giả sử ứng dụng nhận thanh toán và ghi một document:

~~~javascript
{
  _id: "pay301",
  tenant_id: "t01",
  order_id: "o301",
  state: "PAID",
  amount_vnd: NumberLong(850000)
}
~~~

MongoDB trả kết quả thành công. Nhưng **“thành công” ở đây nghĩa là gì**?

- Primary đã xử lý lệnh ghi?
- Journal trên primary đã được đồng bộ xuống đĩa?
- Một hay nhiều secondary đã nhận và xác nhận oplog?
- Dữ liệu có được giữ lại khi primary mất điện hoặc bị bầu lại?
- Reader trên secondary ngay lập tức nhìn thấy document mới?

Các câu hỏi này **không đồng nghĩa**. MongoDB dùng **write concern** để quyết định mức **xác nhận ghi** mà client cần trước khi kết thúc một thao tác. Mức xác nhận đó ảnh hưởng tới độ bền trước failover, thời gian đáp ứng và khả năng tiếp tục ghi khi cluster có lỗi.

> **Quy tắc quan trọng:** `acknowledged` không tự đồng nghĩa với “không thể rollback”, `j:true` không tự đồng nghĩa với “đã được replicate tới majority”, và `wtimeout` không tự đồng nghĩa với “ghi chưa xảy ra”.

### 1.1. Các thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Write acknowledged** | Server xác nhận thao tác thỏa write concern mà client yêu cầu |
| **Applied on primary** | Primary đã chấp nhận/thực hiện thay đổi ở cấp dữ liệu |
| **Replicated** | Các thành viên replica set khác đã nhận tiến trình ghi/oplog theo quy tắc |
| **Journaled** | Ghi đã được đồng bộ vào journal trên đĩa ở những thành viên được yêu cầu |
| **Majority committed** | Ghi đã đạt mốc xác nhận majority, theo cơ chế phiên bản MongoDB |
| **Durable** | Có mức bảo đảm chống mất dữ liệu theo replication/journaling đã chọn, không phải tuyệt đối trước mọi thảm họa |
| **Visible to reader** | Một query cụ thể đã nhìn thấy giá trị, phụ thuộc read concern, read preference và thời điểm secondary apply |
| **Atomic** | Một hoặc một tập thay đổi có tính tất-cả-hoặc-không ở mức được MongoDB hỗ trợ; khác write concern |

**Không dùng write concern thay cho business transaction.** Ví dụ hai collection `payments` và `orders` đều ghi với majority **không tự tạo giao dịch nguyên tử giữa chúng**. Muốn đảm bảo all-or-nothing trên nhiều document phải thiết kế transaction hoặc mô hình nghiệp vụ tương đương.

## 2. Cấu trúc của write concern

MongoDB biểu diễn write concern bằng document:

~~~javascript
{
  w: "majority",
  j: true,
  wtimeout: 5000
}
~~~

| Tùy chọn | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `w` | Số thành viên phải xác nhận, hoặc majority/custom concern | `0`, `1`, `2`, `"majority"` |
| `j` | Yêu cầu xác nhận liên quan đến journal trên đĩa | `true`, `false`, không chỉ định |
| `wtimeout` | Giới hạn thời gian đợi đạt mức `w`, đơn vị mili giây | `5000` |

Trong URI của Java Driver, option timeout thường được viết là `wTimeoutMS`; trong write concern document của MongoDB command/mongosh là `wtimeout`. Phân biệt **đơn vị thời gian** và **tên thuộc tính theo API**, không tự đổi tên bừa giữa chúng.

### 2.1. Ba trục độc lập

~~~mermaid
flowchart LR
    A["Client gửi insert/update"] --> B["Primary xử lý ghi"]
    B --> C["Replication tới thành viên khác"]
    B --> D["Journal trên đĩa"]
    C --> E["Đạt điều kiện w"]
    D --> F["Đạt yêu cầu j"]
    E --> G["Gửi xác nhận về client"]
    F --> G
~~~

Sơ đồ là mô hình khái niệm. Thứ tự/chi tiết thực thi và mốc journal/commit thay đổi theo phiên bản MongoDB, storage engine, cấu hình replica set và loại write concern. Không suy ra rằng replication và journal luôn xảy ra theo đúng một chuỗi tuyến tính.

### 2.2. Những gì write concern không kiểm soát

Write concern **không** tự quy định:

- Tập document nào sẽ bị cập nhật: đó là trách nhiệm của query predicate.
- Kiểm tra tính hợp lệ nghiệp vụ: thuộc validation và ràng buộc dữ liệu.
- Chọn primary hay secondary để **đọc**: đó là `readPreference`.
- Mức ổn định/nhất quán khi **đọc**: đó là `readConcern`.
- Mọi write trên nhiều document có rollback cùng nhau hay không: thuộc transaction semantics.
- Một request bị timeout có thể chạy lại vô hạn an toàn hay không: thuộc retry/idempotency.

## 3. Replica set và majority được tính thế nào?

Giả sử replica set có **ba thành viên mang dữ liệu và có quyền vote**:

~~~text
               Replica set (3 data-bearing voting members)

           Primary P
          (xử lý write)
              |
     +--------+--------+
     |                 |
 Secondary S1      Secondary S2

w:1             -> P xác nhận là đủ.
w:"majority"    -> P và ít nhất một trong S1/S2 đạt mốc majority.
w:3             -> Cả P, S1 và S2 xác nhận.
~~~

Với ba voting members, **đa số là 2**. Với năm voting members, đa số là **3**. Một tag set/custom write concern có các quy tắc riêng ngoài phạm vi ví dụ cơ bản.

### 3.1. `w:1`

~~~javascript
{ w: 1 }
~~~

Primary có thể trả xác nhận sau khi thực hiện thay đổi tại chính nó. Nó **không phải chờ secondary** để đáp ứng write concern. Nếu primary gặp sự cố trước khi ghi kịp replicate tới thành viên sẽ được bầu làm primary mới, write `w:1` đã được xác nhận **có thể bị rollback**.

Đối với dữ liệu có thể tái tạo và tác vụ ít quan trọng, lựa chọn này có thể được cân nhắc sau khi chấp nhận rủi ro. Đối với thanh toán, ledger hoặc order state có ảnh hưởng tài chính, cần đánh giá kỹ thay vì chỉ tối ưu latency.

### 3.2. `w:"majority"`

~~~javascript
{ w: "majority" }
~~~

MongoDB đợi mức xác nhận từ **đa số thành viên voting có dữ liệu phù hợp** theo quy tắc replica set. Điều này giảm đáng kể nguy cơ một write đã được xác nhận bị rollback khi có election/failover.

**Không phải:** “tất cả secondary đã thấy dữ liệu”. Đạt majority trong ba node chỉ cần hai thành viên; node thứ ba vẫn có thể trễ.

### 3.3. `w:2` không luôn bằng majority

Trong một replica set ba voting members mang dữ liệu, `w:2` tương ứng số lượng với majority = 2. Nhưng trong replica set năm voting members:

~~~text
w:2        -> 2 thành viên có dữ liệu xác nhận
w:majority -> ít nhất 3 voting members theo ngưỡng majority
~~~

`w:2` không có nghĩa cố định là majority. Khi topology thay đổi, ngưỡng majority thay đổi theo; một số `w` kiểu số còn có thể được đáp ứng bởi thành viên **không có quyền vote**, trong khi majority dùng quy tắc voting.

### 3.4. Arbiter không lưu dữ liệu

Một replica set kiểu **P-S-A** (primary, secondary, arbiter):

~~~text
P: Primary, data-bearing, voting
S: Secondary, data-bearing, voting
A: Arbiter, voting nhưng KHÔNG lưu dữ liệu

Voting majority = 2.
Arbiter không thể đóng góp bản sao dữ liệu để xác nhận write majority.
~~~

Với mô hình này, `w:"majority"` muốn đạt ngưỡng 2 phải có sự tham gia của **cả P và S**. Nếu S không sẵn sàng, write có thể không đạt majority dù arbiter vẫn vote giúp bầu primary.

Đó là một trong các lý do **không mặc định xem P-S-A giống P-S-S** về tính sẵn sàng ghi với majority.

## 4. `w:0`, `w:1`, `w:"majority"` và `w:n`

| Write concern | Mức xác nhận | Rủi ro/chú ý |
| --- | --- | --- |
| `w:0` | Không yêu cầu server xác nhận write | Không biết chắc duplicate key, validation failure hoặc kết quả ghi |
| `w:1` | Một thành viên, thường là primary | Có thể rollback khi primary mất quyền và write chưa majority |
| `w:2` | Hai thành viên đủ điều kiện | Có thể không bằng majority; phụ thuộc topology |
| `w:"majority"` | Đa số voting data-bearing members theo quy tắc | Chống rollback trong điều kiện chuẩn tốt hơn; tăng thời gian chờ/giảm availability khi thiếu quorum |
| `w:3` | Ba thành viên đủ điều kiện | Không phù hợp nếu deployment không đủ thành viên có dữ liệu hoặc member trễ |

### 4.1. `w:0` — unacknowledged write

~~~javascript
{ w: 0 }
~~~

Đây không phải “ghi nhanh hơn nhưng chắc chắn vẫn thành công”. Client **không nhận bảo đảm server đã thực hiện thành công**. Driver thường không thể cung cấp kết quả `matchedCount`/`modifiedCount` tin cậy từ một unacknowledged write.

`w:0` không phù hợp với những thao tác cần báo cho người dùng “đã đăng ký thành công”, “đã nhận tiền” hoặc “đã đổi trạng thái”. Nó cũng không cung cấp tín hiệu đáng tin cậy để biết có duplicate key hay lỗi schema.

### 4.2. `w:1` — đã được primary xác nhận nhưng chưa chắc bền qua failover

~~~javascript
{ w: 1 }
~~~

Điều này **không có nghĩa dữ liệu chỉ ở RAM mãi mãi**; journal và replication có thể vẫn xảy ra sau đó. Nó chỉ nói rằng client **không chờ** các điều kiện ấy để được xác nhận, trừ khi yêu cầu `j` thay đổi.

### 4.3. `w:"majority"` — ưu tiên durability ở replica set

~~~javascript
{ w: "majority", wtimeout: 5000 }
~~~

Client chờ đủ thành viên và trả write concern error nếu không đạt trong giới hạn chờ. **Lỗi chờ này không tự hủy write** đã được thực hiện tại primary.

### 4.4. `w:n` — đừng chọn số mà không khảo sát topology

Một `w` số cao có thể không đạt được khi secondary trễ, mất kết nối hoặc không đủ data-bearing members. Nếu không đặt timeout thích hợp, một write concern không thể đạt có thể chờ rất lâu.

Tách rõ hai chỉ tiêu vận hành: **độ trễ xác nhận** và **mức khả dụng khi mất thành viên**. Không có một `w` tối ưu cho mọi workload.

## 5. Journal: `j:true` nghĩa là gì?

MongoDB dùng **write-ahead logging/journaling** ở những storage engine có journal, ví dụ WiredTiger, để hỗ trợ phục hồi sau sự cố tiến trình hoặc máy chủ.

### 5.1. Không chỉ định `j`

~~~javascript
{ w: 1 }
~~~

Với write concern kiểu số và `j` không chỉ định, MongoDB thường **không cần chờ** đồng bộ journal trước khi trả acknowledgment. Journal có thể được ghi sau theo cơ chế bình thường.

### 5.2. `j:true`

~~~javascript
{ w: 1, j: true }
~~~

Client yêu cầu acknowledgment liên quan tới việc **đồng bộ journal xuống đĩa** trước khi xem write đạt write concern. Điều này tăng khả năng phục hồi trước crash trên **những thành viên được yêu cầu**, nhưng:

> **`w:1,j:true` vẫn không phải `w:"majority"`.**

Ngay cả khi primary đã journal, nếu thao tác chưa được ghi lên majority mà primary bị loại khỏi lịch sử được chọn sau failover, write vẫn có thể bị rollback theo cơ chế replica set. **Journal chống một loại mất mát, còn majority chống loại rủi ro khác**.

### 5.3. `w:"majority"` và journal mặc định

Với replica set dùng journaling, `w:"majority"` và `j` không chỉ định chịu ảnh hưởng của server parameter `writeConcernMajorityJournalDefault`:

- **`true` (mặc định thông thường):** majority acknowledgment chờ các write được journal bền vững theo quy tắc majority.
- **`false`:** majority acknowledgment có thể được trả dựa trên trạng thái memory, chưa chờ journal; khi đồng thời nhiều node crash/restart, rủi ro mất/rollback dữ liệu lớn hơn.

Thay vì nói `majority` “luôn luôn đồng nghĩa j:true” hoặc “không liên quan journal”, hãy **kiểm cấu hình deployment**.

### 5.4. Không suy giản đơn rằng `j:false` luôn tắt mọi journal wait

Tài liệu MongoDB phân biệt `j` cụ thể, majority journaling default và engine/storage behavior. Trên replica set mặc định có `writeConcernMajorityJournalDefault:true`, `w:"majority"` vẫn có cơ chế journal/majority snapshot ảnh hưởng tới thời điểm acknowledgment ngay cả khi một write khai báo `j:false`.

Chính sách vận hành nên dùng **mức durability muốn đạt** làm đầu vào, không sử dụng `j:false` như một “công tắc chắc chắn bỏ hết disk sync” trong mọi topology.

### 5.5. Ghi không có journal

Một số storage engine/configuration không có journal theo nghĩa của WiredTiger. Yêu cầu `j:true` có thể không khả dụng hoặc được xử lý khác theo engine; MongoDB có quy tắc riêng với in-memory storage engine. Khi hạ tầng không dùng WiredTiger/journaling thông thường, kiểm tra khả năng hỗ trợ và tài liệu theo phiên bản.

## 6. Bảng quyết định `w` × `j`

Đây là **mô hình thực hành cho replica set WiredTiger thông thường**; không thay thế tài liệu theo phiên bản hoặc các tùy chọn server đặc biệt.

| Cấu hình | Client chờ điều gì? | Chịu crash/failover |
| --- | --- | --- |
| `{w:0}` | Không chờ write acknowledgment | Không có bảo đảm xác nhận từ server |
| `{w:1}` | Primary xử lý write | Có nguy cơ rollback sau election |
| `{w:1,j:true}` | Primary ghi journal trước acknowledgment | Bền hơn trước crash primary, **vẫn có rollback** khi chưa replicate majority |
| `{w:"majority"}` | Đa số đạt write acknowledgment; journal phụ thuộc `writeConcernMajorityJournalDefault` | Giảm nguy cơ rollback khi majority bền vững |
| `{w:"majority",j:true}` | Đa số đạt điều kiện ghi và journal theo cơ chế server | Phù hợp write nhạy cảm cần cả majority lẫn journal |
| `{w:3,j:true}` | Số thành viên yêu cầu và journal | Có thể chờ lâu/không thể đạt nếu topology thiếu member |

### 6.1. Ví dụ `w:1,j:true` không phải đa số

~~~text
Timeline:

t0  P ghi order o301, flush journal.
t1  Client nhận ACK với w:1,j:true.
t2  S1/S2 CHƯA nhận được write.
t3  P bị cô lập; S1 được bầu primary mới.
t4  Lịch sử write của P không nằm trong lịch sử majority.

Kết quả có thể xảy ra: order o301 bị rollback khi P nhập lại replica set.
~~~

### 6.2. Ví dụ `w:"majority"` giúp an toàn hơn

~~~text
t0  P xử lý order o301.
t1  S1 đạt mốc majority acknowledgment cùng P.
t2  Client nhận ACK w:"majority".
t3  P bị mất kết nối; replica set bầu primary mới.

Write đã majority-committed theo cơ chế replica set, không giống
write chỉ được P ghi cục bộ; dù S2 có thể vẫn chưa apply,
write có mức bảo vệ trước failover cao hơn.
~~~

Mô hình ví dụ giả định replica set bình thường và majority journaling đúng cấu hình; không phải bảo đảm trước mọi thiên tai làm mất đồng thời nhiều bản sao lưu trữ.

## 7. Default write concern: đừng đoán từ phiên bản driver

### 7.1. MongoDB 5.0 trở đi

Đối với **phần lớn deployment MongoDB 5.0+**, implicit default write concern là `{w:"majority"}`. **Có ngoại lệ đáng chú ý với replica set chứa arbiter**: trong một số topology, default thực tế là `{w:1}`.

Ví dụ P-S-A có ngưỡng voting majority 2 nhưng chỉ hai data-bearing voting members và có arbiter — đây là kiểu topology cần kiểm kỹ giá trị default.

Ngoài implicit default, hệ thống có thể thiết lập **cluster-wide default read/write concern** bằng cơ chế quản trị riêng. Driver/client/application cũng có thể đặt write concern explicit. Vì vậy:

> Không kết luận write concern hiệu lực bằng cách chỉ đọc rằng “MongoDB version >= 5” hoặc “Java Driver mặc định acknowledged”.

### 7.2. Kiểm default tại server

Trong `mongosh` có quyền quản trị phù hợp:

~~~javascript
db.adminCommand({ getDefaultRWConcern: 1 });
~~~

Lệnh giúp quan sát default read/write concern cấu hình và một số thông tin nguồn mặc định tùy phiên bản. Một application có thể dùng **write concern override** nên command này **không chứng minh** một method Spring Data cụ thể đang dùng mức nào.

### 7.3. Kiểm đường đi cấu hình

~~~text
Application policy / MongoTemplate WriteConcernResolver
                   |
          MongoTemplate default
                   |
           Driver MongoClient/DB/Collection
                   |
       Cluster-wide / implicit server default
~~~

Sơ đồ mang tính kiểm tra **nguồn cấu hình**, không phải một chuỗi ưu tiên tuyệt đối cho mọi API. Khi write concern explicit ở operation/collection thì server default không còn là mức được chọn. Trong production, cần xác nhận **writeConcern thực được gửi** bằng command monitoring/log an toàn và metadata cấu hình.

### 7.4. Tách version server và version driver

Java Driver cung cấp các giá trị như `WriteConcern.ACKNOWLEDGED`, `MAJORITY`, `JOURNALED`; chúng mô tả một chính sách phía client/driver. Nếu driver gửi `w:1` explicit, việc server MongoDB 5.0+ có implicit default majority **không tự biến write đó thành majority**.

Kiểm phiên bản driver, Spring Data, connection string, bean config và deployment để tránh so sánh sai.

## 8. `wtimeout`: lỗi xác nhận không đồng nghĩa với rollback

### 8.1. Ví dụ lệnh ghi có timeout

~~~javascript
use spring_data_mongodb_lab

db.payments_write_concern_demo_003.insertOne(
  {
    _id: "pay301",
    tenant_id: "t01",
    order_id: "o301",
    state: "PAID",
    amount_vnd: NumberLong(850000)
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

Chỉ chạy trong **database thử nghiệm và replica set hỗ trợ majority**, không dùng ID fixture trên dữ liệu thật. Nếu đã insert thành công, chạy lại cùng `_id` sẽ phát sinh duplicate key; đó không phải bằng chứng riêng về write concern.

Giả sử write đã được **primary apply**, nhưng secondary bị mất mạng và không đạt majority trong 5 giây. MongoDB có thể trả **write concern error**.

Điều xảy ra sau đó có thể là:

1. Document đã có trên primary.
2. Sau khi lệnh trả lỗi, secondary có thể **tiếp tục replicate** và đạt majority.
3. Hoặc dữ liệu chưa majority có thể bị rollback nếu primary cũ mất quyền và lịch sử không được chọn.

**Không suy luận “nhận timeout thì insert chưa xảy ra”.**

### 8.2. `wtimeout` khác `maxTimeMS` và socket timeout

| Giới hạn | Điều nó kiểm soát |
| --- | --- |
| `wtimeout` | Thời gian đợi đáp ứng write concern `w` sau khi primary xử lý |
| `maxTimeMS` | Giới hạn thời gian server cho một thao tác hỗ trợ option tương ứng |
| Client socket/read timeout | Thời gian chờ phản hồi mạng từ phía driver |
| Application/request deadline | Tổng thời gian nghiệp vụ chấp nhận, có thể bao gồm nhiều bước |

`wtimeout` chỉ có ý nghĩa khi `w > 1` hoặc `w:"majority"`/concern tương đương. Nó không phải giới hạn tổng thời gian từ đầu đến cuối của mọi write và **không bảo đảm ghi bị hủy khi hết hạn**.

### 8.3. `wtimeout:0` không phải “timeout ngay”

Trong write concern, `wtimeout:0` có nghĩa **không đặt giới hạn chờ write concern**. Nếu mức `w` không khả thi trong một thời gian dài, request có thể chờ rất lâu, tùy các timeout khác và tình trạng hệ thống.

Đối với API thời gian thực, chọn deadline dựa trên SLO và rủi ro, nhưng không “chữa” timeout bằng cách im lặng hạ `w` từ majority xuống 1 cho mọi dữ liệu nhạy cảm.

### 8.4. Một câu trả lời đúng cho người dùng khi write outcome chưa rõ

Sai:

> “Thanh toán thất bại, bạn hãy bấm thanh toán lại” — dù document có thể đã ghi thành công.

Nên xử lý bằng một **idempotency key hoặc ID nghiệp vụ ổn định**, kiểm trạng thái bằng read phù hợp rồi quyết định retry/đối soát:

~~~text
Payment request (idempotencyKey = pay301)
       |
       +-- confirmed majority --> trả thành công
       |
       +-- duplicate key / prior result --> đối chiếu payload, trả kết quả cũ
       |
       +-- write concern/network unknown --> trạng thái PENDING_CONFIRMATION
                                       kiểm tra/đối soát trước retry
~~~

Không được coi lỗi xác nhận majority là một phép rollback tự động.

## 9. Write error và write concern error: khác nhau

MongoDB trả thông tin lỗi ở nhiều lớp:

| Nhóm | Ví dụ | Kết luận có thể rút ra |
| --- | --- | --- |
| **Write error** | Duplicate key `E11000`, schema validation fail | Primary từ chối thao tác tương ứng; cần sửa dữ liệu/lệnh |
| **Write concern error** | Không đạt majority trong `wtimeout` | Ghi có thể đã được primary apply; trạng thái bền vững chưa được xác nhận ở mức yêu cầu |
| **Network/socket timeout** | Client mất kết nối trước phản hồi | Kết quả thao tác **không xác định** chỉ từ exception |
| **Server selection timeout** | Không tìm được server phù hợp | Có thể chưa gửi được thao tác; cần chẩn đoán topology/driver, không suy đoán từ tên lỗi |
| **Transaction commit uncertainty** | Không xác định commit đã thành công hay chưa | Dùng cơ chế retry commit/đối soát được driver hỗ trợ |

### 9.1. `DuplicateKeyException` khác `wtimeout`

Spring Data có thể dịch lỗi duplicate key qua `org.springframework.dao.DuplicateKeyException` khi gọi repository/`MongoTemplate`. Nhưng một lỗi không đạt write concern có thể xuất hiện dưới kiểu exception khác từ driver/Spring Data.

Không viết:

~~~java
// SAI:
// catch (Exception ex) {
//     repository.insert(payment); // retry mọi lỗi
// }
~~~

Vì:

- Duplicate key là ràng buộc dữ liệu; retry nguyên lệnh thường không giúp.
- `$inc` hoặc `$push` có thể áp hai lần nếu retry thủ công khi lần đầu đã ghi.
- Lỗi do mạng/write concern có thể để kết quả **unknown**.
- Một giao dịch tài chính cần khóa/idempotency và trạng thái đối soát độc lập.

### 9.2. Lỗi không có nghĩa phần dữ liệu đã được ghi bị xóa

Ví dụ `wtimeout` xảy ra khi primary đã insert `pay301`. Client nhận lỗi, nhưng:

~~~javascript
db.payments_write_concern_demo_003.findOne({
  _id: "pay301"
});
~~~

có thể trả document. Tuy nhiên nếu query này chạy trên primary cũ hoặc dùng read concern yếu, nó cũng **không đủ chứng minh** write đã majority committed. Cần thiết kế read concern/causal session và quy trình đối soát phù hợp.

## 10. Write concern và rollback khi bầu primary mới

Một replica set có thể gặp phân vùng mạng:

~~~text
Trước lỗi:
P  -- S1 -- S2

P xử lý write W với w:1 -> trả ACK.
W chưa kịp có trên S1, S2.

Sau lỗi:
P bị cô lập.
S1 + S2 bầu primary mới.

W của P không thuộc lịch sử majority -> có thể rollback khi P nhập lại.
~~~

### 10.1. Vì sao majority giảm nguy cơ rollback?

Khi write đạt majority commit point theo cơ chế replica set, các cuộc bầu cử hợp lệ dùng majority không thể đơn giản “bỏ quên” toàn bộ lịch sử committed đó như một write chỉ nằm trên primary đơn độc. Vì vậy MongoDB khuyến nghị `w:"majority"` cùng journaling phù hợp để tránh rollback của những write đã được báo thành công.

**Ngoại lệ cần hiểu:** Nếu `writeConcernMajorityJournalDefault:false` và xảy ra crash/restart của nhiều node, một write majority-acknowledged chỉ ở memory có thể vẫn gặp rủi ro. Không dùng chữ “tuyệt đối” khi nói về durability của hệ phân tán.

### 10.2. Rollback không phải undo theo nghiệp vụ

Rollback replica set là sự kiện đồng bộ lịch sử giữa các thành viên. Nó không đồng nghĩa với thao tác `rollback transaction` do ứng dụng chủ động.

Một write `w:1` đã trả HTTP 200 cho client nhưng bị rollback sau failover có thể tạo trạng thái **khách hàng tin đã hoàn tất, dữ liệu chính chưa còn**. Đây là lý do dữ liệu có giá trị nghiệp vụ cao cần chiến lược xác nhận phù hợp, idempotency và giám sát failover.

## 11. Write concern khác read concern và read preference

| Khái niệm | Câu hỏi nó trả lời |
| --- | --- |
| `writeConcern` | Khi nào server trả ACK cho một write? |
| `readConcern` | Query đọc dữ liệu với mức nhất quán/ổn định nào? |
| `readPreference` | Driver ưu tiên đọc từ primary hay secondary nào? |
| Causally consistent session | Một chuỗi read/write liên hệ nhân quả được đảm bảo ra sao? |

### 11.1. Không suy ra “majority write ⇒ mọi secondary đọc thấy ngay”

**Từ MongoDB 8.0**, `{w:"majority"}` có thể được xác nhận sau khi **oplog entry** đã được ghi bền vững trên majority, trong khi secondary tiếp tục **apply** nội dung vào collection một cách bất đồng bộ.

Vì vậy một query trực tiếp tới một secondary ngay sau ACK majority có thể chưa đọc được dữ liệu mới từ collection của secondary đó. Trước MongoDB 8.0, thời điểm ACK có khác biệt do server đợi thao tác được apply theo cơ chế cũ.

Muốn read-after-write trên secondary theo chuỗi nghiệp vụ, dùng **causally consistent session**, kết hợp `readConcern:"majority"` và `writeConcern:"majority"` theo hợp đồng MongoDB.

### 11.2. Read concern `majority` không phải write concern `majority`

~~~javascript
// Hai cấu hình độc lập:
{ readConcern: { level: "majority" } }
{ writeConcern: { w: "majority" } }
~~~

Đặt `readConcern:"majority"` **không tự làm các write dùng majority**, và ngược lại. Khi service cần read-your-writes qua secondary trong một session, cấu hình cả hai phía cùng session.

### 11.3. Read preference `secondary` có thể đọc dữ liệu trễ

~~~text
write ở primary -> replica ghi oplog -> secondary apply -> secondary trả read
~~~

Secondary có thể trễ vì mạng, I/O, apply queue hoặc phân vùng. `readPreference.secondary()` chỉ nói driver chọn nơi đọc; nó không bảo đảm dữ liệu gần nhất. Với nghiệp vụ cần trạng thái vừa ghi, xác định rõ use case có cần causal session, đọc primary hay mức isolation mạnh hơn.

### 11.4. Majority write không tự tạo linearizability

“Đọc trạng thái mới nhất tuyệt đối” là hợp đồng mạnh hơn chỉ một `w:"majority"`. MongoDB còn có `readConcern:"linearizable"` trên những thao tác phù hợp, với điều kiện về write concern/topology. Không đánh đồng các mức:

~~~text
ACK majority ≠ mọi reader ở mọi node nhìn thấy ngay
ACK majority ≠ multi-document transaction
ACK majority ≠ read linearizable trong mọi tình huống
~~~

## 12. Cấu hình qua `mongosh` và connection string

### 12.1. Một write cụ thể

~~~javascript
db.payments_write_concern_demo_003.updateOne(
  {
    _id: "pay301",
    tenant_id: "t01",
    state: "PENDING"
  },
  {
    $set: { state: "PAID" }
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

**Lưu ý:** Ví dụ này cập nhật từ `PENDING` sang `PAID` nên chỉ tác động nếu document có đúng trạng thái dự kiến. Nếu bạn đã chạy fixture `pay301` với `state:"PAID"` ở mục 8, `matchedCount=0` là bình thường. Hãy tạo một document `PENDING` riêng khi thực hành tình huống chuyển trạng thái.

### 12.2. Đặt write concern cho kết nối `mongosh`

~~~javascript
db.getMongo().setWriteConcern({
  w: "majority",
  j: true,
  wtimeout: 5000
});

db.payments_write_concern_demo_003.insertOne({
  _id: "pay302",
  tenant_id: "t01",
  order_id: "o302",
  state: "PENDING",
  amount_vnd: NumberLong(250000)
});
~~~

Đây là cấu hình trên **kết nối shell đang dùng**. Nó không nhất thiết thay đổi default toàn cluster hoặc cấu hình của một `MongoClient` Java khác.

### 12.3. MongoDB URI trong Java/Spring Boot

Ví dụ:

~~~properties
# Ví dụ cấu hình, thay host và credential theo môi trường thực.
spring.data.mongodb.uri=mongodb://mongo1:27017,mongo2:27017,mongo3:27017/payments_lab?replicaSet=rs0&w=majority&journal=true&wTimeoutMS=5000
~~~

Trong trường hợp triển khai replica set thực, URI phải chứa các host/topology đúng. Không hardcode password vào code hoặc commit secret trong file properties; dùng secret manager hoặc biến môi trường.

**Chú ý:** `w=majority` trong URI là **write concern của driver/connection** theo quy tắc áp dụng của driver. Một `MongoTemplate` hoặc operation cụ thể có thể có write concern riêng ghi đè. Đừng suy từ `spring.data.mongodb.uri` rằng tất cả các client khác nhau trong ứng dụng đều tự động dùng cùng chính sách.

### 12.4. Bảo vệ ý nghĩa của timeout

Nếu API đặt request deadline 2 giây nhưng `wTimeoutMS=5000`, bạn phải hiểu **client có thể ngắt chờ trước khi server kết luận write concern**. Ngược lại, giảm `wtimeout` không biến lần ghi đầu tiên thành thao tác có thể retry mù. Policy cần kết hợp deadline, idempotency và cách thông báo trạng thái chưa chắc chắn.

## 13. MongoDB Java Driver: cấu hình theo client/collection

### 13.1. Các hằng `WriteConcern` thông dụng

~~~java
import com.mongodb.WriteConcern;
import java.util.concurrent.TimeUnit;

WriteConcern unacknowledged = WriteConcern.UNACKNOWLEDGED; // w:0
WriteConcern primaryOnly   = WriteConcern.ACKNOWLEDGED;   // w:1
WriteConcern journaled     = WriteConcern.JOURNALED;      // w:1,j:true
WriteConcern majority      = WriteConcern.MAJORITY;       // w:"majority"

WriteConcern critical =
    WriteConcern.MAJORITY
        .withJournal(true)
        .withWTimeout(5, TimeUnit.SECONDS);
~~~

Lưu ý `WriteConcern.JOURNALED` thường tương ứng `w:1,j:true` — **không phải majority**. Tên `JOURNALED` diễn đạt journal durability ở cấp cấu hình đó; muốn majority và journal hãy ghép rõ như `critical`.

### 13.2. Collection-specific write concern

~~~java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.InsertOneResult;
import java.util.concurrent.TimeUnit;
import org.bson.Document;

// mongoClient là com.mongodb.client.MongoClient đã cấu hình.
MongoDatabase database = mongoClient.getDatabase(
    "spring_data_mongodb_lab"
);

MongoCollection<Document> collection = database
    .getCollection("payments_write_concern_demo_003")
    .withWriteConcern(
        WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(5, TimeUnit.SECONDS)
    );

InsertOneResult result = collection.insertOne(
    new Document("_id", "pay303")
        .append("tenant_id", "t01")
        .append("state", "PENDING")
);

if (!result.wasAcknowledged()) {
    throw new IllegalStateException("Write was unacknowledged");
}
~~~

`withWriteConcern(...)` trả một **collection handle được cấu hình**. Nó không tự sửa cấu hình vĩnh viễn trên MongoDB collection hay tạo server-level policy; thay đổi áp dụng cho những thao tác đi qua handle đó.

### 13.3. `wasAcknowledged()` có nghĩa chính xác thế nào?

`result.wasAcknowledged() == true` nghĩa là operation nhận acknowledgment theo write concern **đã được dùng**. Nếu collection handle đang dùng `w:1` thì `true` **không chứng minh majority**.

Vì vậy:

~~~java
// Cách suy luận SAI:
// if (result.wasAcknowledged()) { assertMajorityDurable(); }
~~~

Phải kiểm **cấu hình write concern hiệu lực** và topology ngoài boolean result. Một test trên single-node replica set có `MAJORITY` cũng **không chứng minh** khả năng chờ nhiều thành viên, vì majority của một voting member là một.

### 13.4. Kiểu số kết quả cập nhật khác write concern

~~~java
var result = collection.updateOne(
    new Document("_id", "pay303"),
    new Document("$set", new Document("state", "PAID"))
);

if (result.wasAcknowledged()) {
    long matched = result.getMatchedCount();
    long modified = result.getModifiedCount();
}
~~~

`matchedCount` và `modifiedCount` trả lời “bao nhiêu document khớp/thay đổi”, **không** trả lời “đã majority journaled chưa”. Một operation có thể `matched=1, modified=0` (ghi lại giá trị giống cũ) nhưng vẫn là acknowledged write. Với `w:0`, nhiều accessor của result không có ý nghĩa và có thể ném exception khi cố đọc.

## 14. Spring Data `MongoTemplate`: thiết lập write concern

Spring Data MongoDB cho phép cấu hình `com.mongodb.WriteConcern` trên `MongoTemplate`. Nếu không cấu hình ở template, nó thường dùng write concern từ database factory/driver/collection tương ứng.

### 14.1. Một `MongoTemplate` dùng majority + journal

~~~java
package com.example.consistency;

import com.mongodb.WriteConcern;
import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration
public class ConsistencyMongoConfig {

    @Bean("criticalMongoTemplate")
    MongoTemplate criticalMongoTemplate(
            MongoDatabaseFactory factory) {

        MongoTemplate template = new MongoTemplate(factory);
        template.setWriteConcern(
            WriteConcern.MAJORITY
                .withJournal(true)
                .withWTimeout(5, TimeUnit.SECONDS)
        );
        return template;
    }
}
~~~

Khi service inject bean này:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.core.MongoTemplate;

@Service
public class PaymentWriteService {
    private final MongoTemplate criticalTemplate;

    public PaymentWriteService(
            @Qualifier("criticalMongoTemplate")
            MongoTemplate criticalTemplate) {
        this.criticalTemplate = criticalTemplate;
    }

    public PaymentDocument save(PaymentDocument payment) {
        return criticalTemplate.insert(payment);
    }
}
~~~

`PaymentDocument` là entity nghiệp vụ ví dụ, được định nghĩa ở mục 16.1. Đây là đường ghi qua **template đã chọn**, không phải khẳng định mọi repository trong ứng dụng đều tự dùng template đó.

**Cảnh báo tích hợp Spring Boot:** Tạo thêm `MongoTemplate` có thể ảnh hưởng tới auto-configuration và việc inject template mặc định. Với nhiều bean, phải dùng `@Qualifier`, cấu hình repository factory phù hợp và kiểm đường ghi thực trước khi cho rằng repository cũng dùng policy mới.

### 14.2. `WriteConcernResolver`: chọn theo loại thao tác/aggregate

Nếu một ứng dụng có chính sách khác nhau cho entity quan trọng và entity tái tạo được, có thể dùng `WriteConcernResolver`:

~~~java
import com.mongodb.WriteConcern;
import org.springframework.data.mongodb.core.MongoTemplate;

// Cấu hình trước khi template bắt đầu phục vụ request:
template.setWriteConcernResolver(action -> {
    Class<?> type = action.getEntityType();

    if (type != null
            && PaymentDocument.class.isAssignableFrom(type)) {
        return WriteConcern.MAJORITY.withJournal(true);
    }

    return action.getDefaultWriteConcern();
});
~~~

`MongoAction` cung cấp thông tin entity type, collection, loại thao tác và default concern để resolver quyết định. Không kiểm dữ liệu bí mật trực tiếp từ document rồi viết log; cũng không tạo quy tắc khiến một collection thanh toán có nhiều mức durability không được giải thích.

**Giới hạn:** Một operation có thể được thực hiện bằng driver trực tiếp hoặc template khác; resolver của **template này** không điều khiển những đường ghi đó.

### 14.3. Repository đi qua đường nào?

`MongoRepository` chuẩn dùng hạ tầng Spring Data tương ứng (thường dựa trên `MongoOperations`) để thực hiện CRUD. Nó **không có một annotation `@WriteConcern` mặc định cho từng method CRUD** tương đương việc đặt `Query.collation(...)`.

Để cấu hình ổn định:

1. Chọn write concern tại MongoClient/URI nếu đó là policy chung.
2. Cấu hình template/repository factory nếu các repository phải dùng policy riêng.
3. Dùng `MongoTemplate`/custom fragment cho những use case cần kiểm soát rõ concern.
4. Kiểm command monitoring hoặc integration test cấu hình để đảm bảo write thật đi qua đường dự kiến.

Không suy từ `@Document` hoặc tên repository rằng write đã majority-acknowledged.

### 14.4. `WriteResultChecking` khác write concern

`MongoTemplate.setWriteResultChecking(WriteResultChecking.EXCEPTION)` liên quan cách Spring Data kiểm tra/báo lỗi ghi ở những luồng phù hợp. Nó **không đặt `w:"majority"`** và không biến `w:0` thành write có ACK.

~~~java
import org.springframework.data.mongodb.core.WriteResultChecking;

template.setWriteResultChecking(
    WriteResultChecking.EXCEPTION
);
~~~

Đây là policy kiểm lỗi ở phía template, **không** là lựa chọn durability thay cho `setWriteConcern`.

## 15. Reactive Spring Data: publisher không phải ACK

`ReactiveMongoTemplate` cũng hỗ trợ đặt write concern:

~~~java
import com.mongodb.WriteConcern;
import java.util.concurrent.TimeUnit;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

// reactiveTemplate đã được tạo với ReactiveMongoDatabaseFactory.
reactiveTemplate.setWriteConcern(
    WriteConcern.MAJORITY
        .withJournal(true)
        .withWTimeout(5, TimeUnit.SECONDS)
);
~~~

Một service reactive:

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;

public class ReactivePaymentWriteService {
    private final ReactiveMongoTemplate reactiveTemplate;

    public ReactivePaymentWriteService(
            ReactiveMongoTemplate reactiveTemplate) {
        this.reactiveTemplate = reactiveTemplate;
    }

    public Mono<PaymentDocument> insert(PaymentDocument payment) {
        return reactiveTemplate.insert(payment);
    }
}
~~~

**Một `Mono<PaymentDocument>` phát một item không đồng nghĩa `w:1` hoặc `w:"majority"`.** Cardinality của publisher nói về số item ở API reactive; độ bền ghi do write concern hiệu lực của driver/template quyết định.

Publisher thường **chưa thực thi** nếu không có subscriber. Trong WebFlux, ghép kết quả vào reactive chain; không gọi `block()` trên event loop để “đợi majority” theo cách blocking.

### 15.1. Một lỗi write concern trong reactive chain

~~~java
Mono<PaymentDocument> write = service.insert(payment)
    .doOnSuccess(saved -> {
        // Thành công theo write concern được cấu hình.
        // Không suy luận thêm nếu chưa kiểm policy thực.
    })
    .doOnError(error -> {
        // Phân loại lỗi. Không retry mù nếu outcome có thể unknown.
    });
~~~

Với retryable business operation, sử dụng khóa idempotency và truy vấn đối soát; không chỉ thêm `.retry(3)` cho mọi `MongoException`, nhất là khi dùng `$inc`/`$push` hoặc giao dịch có side effect ngoài MongoDB.

## 16. Ví dụ miền: ghi thanh toán có ID ổn định

### 16.1. Entity và index

~~~java
// PaymentDocument.java
package com.example.consistency;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "payments_write_concern_demo_003")
public class PaymentDocument {
    @MongoId(FieldType.STRING)
    private String id; // idempotency key ổn định

    @Field("tenant_id")
    private String tenantId;

    @Field("order_id")
    private String orderId;

    private String state;

    @Field("amount_vnd")
    private long amountVnd;

    private Instant createdAt;

    protected PaymentDocument() { }

    public PaymentDocument(
            String id,
            String tenantId,
            String orderId,
            long amountVnd,
            Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.amountVnd = amountVnd;
        this.state = "PENDING";
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOrderId() { return orderId; }
    public String getState() { return state; }
    public long getAmountVnd() { return amountVnd; }
}
~~~

`_id` đã được MongoDB index duy nhất mặc định, giúp cùng `idempotency key` không tạo hai document khác nhau. **Không** coi `_id` duy nhất là cơ chế tự động “chỉ thu tiền một lần” với cổng thanh toán bên ngoài — cần thiết kế state machine, lưu request fingerprint và đối soát side effects.

### 16.2. Repository

~~~java
// PaymentRepository.java
package com.example.consistency;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface PaymentRepository
        extends MongoRepository<PaymentDocument, String> {
}
~~~

### 16.3. Service với write concern đa số

~~~java
import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class PaymentCreationService {
    private final MongoTemplate criticalTemplate;

    public PaymentCreationService(
            @Qualifier("criticalMongoTemplate")
            MongoTemplate criticalTemplate) {
        this.criticalTemplate = criticalTemplate;
    }

    public PaymentDocument register(
            String requestId,
            String tenantId,
            String orderId,
            long amountVnd) {
        PaymentDocument next = new PaymentDocument(
            requestId,
            tenantId,
            orderId,
            amountVnd,
            Instant.now()
        );

        try {
            return criticalTemplate.insert(next);
        } catch (DuplicateKeyException duplicate) {
            PaymentDocument prior = criticalTemplate.findById(
                requestId, PaymentDocument.class
            );
            if (prior == null) {
                // Đã có duplicate nhưng read hiện chưa xác nhận được.
                throw duplicate;
            }
            if (!tenantId.equals(prior.getTenantId())
                    || !orderId.equals(prior.getOrderId())
                    || amountVnd != prior.getAmountVnd()) {
                throw new IllegalStateException(
                    "Idempotency key reused with different request");
            }
            return prior; // Trả lại bản ghi cùng request đã có.
        }
    }
}
~~~

Đoạn code trên minh họa **đường happy-path của idempotency** và xử lý duplicate. Nó **chưa hoàn chỉnh cho sản phẩm thanh toán**:

- Khi write concern/network outcome unknown, exception không nhất thiết là `DuplicateKeyException`; cần job/API đối soát độc lập.
- `findById` có read concern/read preference riêng; nó có thể chưa chứng minh majority commit trong mọi tình huống.
- Phải ràng buộc tenant từ security context, không tin input giả mạo.
- Có thể có trùng `_id` do lỗi khác; không che mọi duplicate bằng trả bản ghi cũ mà không so fingerprint.
- Chưa xử lý cập nhật trạng thái thanh toán bên thứ ba hoặc outbox/transaction.

### 16.4. Tại sao `save` không thay thế idempotency?

`repository.save(entity)` có semantics insert/replace tùy trạng thái identifier; nếu request được gửi lại với cùng ID nhưng payload khác, save có thể ghi đè thông tin cũ theo cách không phù hợp. Với hành vi **“tạo đúng một payment cho một requestId”**, `insert` + unique ID + kiểm fingerprint thường rõ hơn.

Không áp dụng `$inc` cho số dư tài khoản chỉ dựa vào “đã chờ majority” mà không có guard/idempotency: majority giải quyết **độ bền ACK**, không giải quyết **lặp một nghiệp vụ**.

## 17. Retryable writes và outcome chưa xác định

MongoDB Java Driver hỗ trợ **retryable writes** cho các thao tác đủ điều kiện, trên topology và phiên bản hỗ trợ. Nhưng cơ chế driver retry **không** là giấy phép để ứng dụng retry tùy tiện tất cả lệnh ghi.

### 17.1. Ba tầng cần tách

| Tầng | Vai trò |
| --- | --- |
| **Driver retry** | Có thể thử lại một số write đủ điều kiện sau lỗi tạm thời, giữ nhận dạng thao tác/session theo cơ chế driver |
| **Application retry** | Có thể gọi lại workflow khi request timeout hoặc dependency lỗi |
| **Business idempotency** | Bảo đảm một yêu cầu nghiệp vụ không bị thực thi side effect hai lần, dù request lặp |

### 17.2. Tránh retry mù `$inc`

~~~javascript
db.wallets_write_concern_demo_003.updateOne(
  { _id: "wallet301" },
  { $inc: { balance_vnd: -100000 } },
  { writeConcern: { w: "majority", wtimeout: 2000 } }
);
~~~

Nếu request nhận network timeout sau khi server đã trừ tiền, một application retry **như lệnh mới** có thể trừ thêm 100.000. Write concern majority không khiến phép `$inc` idempotent.

**Mô hình an toàn hơn:** lập transaction/ledger entry bằng request ID duy nhất, kiểm trạng thái của entry, trừ số dư có điều kiện hoặc dùng transaction phù hợp và trả kết quả dựa trên trạng thái persisted. Không chỉ tăng timeout để che lỗi lặp tiền.

### 17.3. `$set` có idempotent tuyệt đối không?

~~~javascript
{ $set: { state: "PAID" } }
~~~

Việc gán một field sang cùng giá trị có thể có tính idempotent **ở cấp giá trị field**, nhưng nếu cùng operation còn cập nhật `updatedAt`, version, counter, audit event hoặc side effect khác thì **không còn idempotent ở cấp workflow**.

Thiết kế retry phải xét **toàn bộ thao tác nghiệp vụ**, không chỉ một operator MongoDB.

### 17.4. Tình trạng không xác định cần API riêng

Một response API có thể dùng các trạng thái:

~~~text
CONFIRMED         : write đã đáp ứng durability policy.
PENDING_CONFIRM   : chưa biết chắc, đang kiểm tra/đối soát.
REJECTED          : business validation hoặc unique constraint từ chối.
FAILED_RETRYABLE  : lỗi tạm thời đã xác định và retry an toàn.
~~~

Đây là **state machine ví dụ**, không phải enum do MongoDB cung cấp. Cần chuyển trạng thái dựa trên bằng chứng, không map mọi exception thành FAILED rồi yêu cầu người dùng gửi lại payment.

## 18. Transaction: write concern đặt tại commit

MongoDB transaction có thể thực hiện nhiều write một cách nguyên tử trong phạm vi được hỗ trợ. **Đối với multi-document transaction, write concern phải được xác định ở cấp transaction, không gắn write concern riêng vào từng operation bên trong transaction.**

### 18.1. Tại sao `w:1` trên commit vẫn có rủi ro?

Ngay cả transaction đã commit với `w:1`, dữ liệu có thể bị rollback sau failover nếu commit chưa được replicate majority. MongoDB nêu rõ rủi ro rollback của transaction khi dùng write concern `w:1`.

Nếu transaction ghi order + payment cùng nhau và API cần durability cao, đặt write concern phù hợp **cho commit**, thường cân nhắc majority và journal.

### 18.2. Spring Data transaction manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTxConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentWorkflowService {
    private final MongoTemplate template;

    public PaymentWorkflowService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager",
        label = {
            "mongo:readConcern=SNAPSHOT",
            "mongo:writeConcern=MAJORITY"
        }
    )
    public void transitionOrderAndRecordPayment(
            OrderDocument order,
            PaymentDocument payment) {
        // Chỉ minh họa hai write trong cùng transaction.
        // Cần đủ validation và điều kiện trạng thái thực tế.
        template.save(order);
        template.insert(payment);
    }
}
~~~

`OrderDocument` là aggregate minh họa của phần dữ liệu đơn hàng, chưa định nghĩa cụ thể trong bài. Khi chuyển thành ví dụ chạy được trong dự án, phải khai báo entity/order mapping, bảo đảm `template` sử dụng **cùng `MongoDatabaseFactory`** với transaction manager, và có replica set/sharded deployment hỗ trợ transactions.

Các label `mongo:writeConcern=MAJORITY` và `mongo:readConcern=SNAPSHOT` được Spring Data MongoDB các phiên bản gần đây hỗ trợ qua transaction option resolver. Với phiên bản cũ, cấu hình transaction options qua transaction manager/API tương ứng; không giả định annotation label sẽ được mọi phiên bản hiểu.

### 18.3. Lưu ý với commit và retry

Khi `commitTransaction` gặp lỗi mạng, không được kết luận ngay rằng transaction đã rollback. MongoDB/driver dùng error labels như `UnknownTransactionCommitResult` và `TransientTransactionError` để hướng dẫn logic retry phù hợp trong các tình huống nhất định.

Nếu có side effect **ngoài** MongoDB (gửi email, gọi payment gateway), transaction MongoDB không rollback được side effect ấy. Với workflow nhiều hệ thống, cân nhắc **outbox**, saga, idempotency và kiểm soát delivery.

### 18.4. Transaction không nâng cấp mọi API khi không có manager

Chỉ gắn `@Transactional` lên method Spring **không bảo đảm** có MongoDB multi-document transaction nếu dự án chưa cấu hình `MongoTransactionManager`/`ReactiveMongoTransactionManager` và topology phù hợp.

Spring Data có các yêu cầu khác về session, collection đã tồn tại và cấu hình driver; kiểm chứng trong integration test.

## 19. Vận hành: chọn concern dựa trên SLO và độ quan trọng

Không chọn `w:1` cho mọi write chỉ vì latency thấp, và cũng không đặt `w:3,j:true` cứng cho mọi workload mà không xem cluster có bao nhiêu data-bearing members.

| Workload | Rủi ro mất dữ liệu | Chính sách gợi ý để đánh giá |
| --- | --- | --- |
| Thanh toán, ledger, trạng thái đơn đã chốt | Cao | `w:"majority"` với journaling đúng cấu hình, idempotency, audit/outbox |
| Lịch sử sự kiện không thể tái tạo | Cao | Majority + bảo đảm phục hồi, backup và quy trình đối soát |
| Cấu hình nghiệp vụ quan trọng | Trung bình–cao | Cân nhắc majority, version guard và kiểm tra sau ghi |
| Cache có thể xây lại | Thấp hơn | Có thể cân nhắc mức xác nhận yếu hơn nếu chấp nhận rollback |
| Counter/telemetry tần suất cao | Tùy use case | Batching, phân loại mức quan trọng; không dùng unack khi cần kết quả chính xác |
| Job queue/claim | Trung bình–cao | Atomic update/`findAndModify` có state predicate và durability policy phù hợp |

**Đây là khung quyết định, không phải cấu hình mặc định bắt buộc.** Cần xét lượng ghi, replication lag, quorum, chi phí đĩa, deadline, tỉ lệ timeout và khả năng khôi phục.

### 19.1. Tín hiệu vận hành nên theo dõi

- Latency của write theo p50/p95/p99 và concern.
- Tỉ lệ write concern error, timeout và retry.
- Replication lag, majority commit point, trạng thái member.
- Election/stepdown, rollback events.
- Journal/storage latency, I/O bottlenecks.
- Số request có outcome unknown và thời gian đối soát.
- Tỉ lệ duplicate key/idempotency conflict.
- Driver command duration và connection pool health.

Nếu majority write đột nhiên chậm, không mặc định hạ concern. Hãy kiểm mạng giữa members, secondary lag, storage/journal, election và write load.

### 19.2. Khi majority không thể đạt

Ví dụ replica set P-S-S chỉ còn P có thể truy cập, hai secondary đều mất kết nối:

~~~text
w:1           -> primary có thể tiếp tục ACK một số write.
w:"majority"  -> không đạt ngưỡng, có thể timeout hoặc lỗi.
~~~

Sự giảm availability này là **đánh đổi có chủ đích** khi muốn write được majority xác nhận. Nếu dữ liệu nhạy cảm, không tự “fail open” thành `w:1` chỉ để API trả thành công — vì có thể tăng rủi ro mất write sau failover.

### 19.3. Backups vẫn cần thiết

Majority + journal **không thay thế backup**. Chúng không bảo vệ hoàn toàn khỏi thao tác xóa nhầm đã majority-committed, lỗi ứng dụng, tham nhũng dữ liệu do code, mất toàn vùng hạ tầng hoặc yêu cầu phục hồi về một thời điểm trong quá khứ.

## 20. Integration test: chứng minh điều gì và không chứng minh điều gì?

### 20.1. Kiểm thử với replica set thật

Để kiểm phần lớn API Spring Data và write concern, dùng MongoDB **test replica set** (ví dụ Testcontainers với cấu hình replSet). Một MongoDB standalone có thể giúp kiểm basic insert, nhưng **không mô phỏng đa số replica set nhiều member**.

| Test | Điều xác minh được |
| --- | --- |
| Driver collection handle `withWriteConcern(MAJORITY)` | Driver handle giữ policy dự kiến |
| `insertOne` với majority trên single-node replica set | Operation ACK theo majority của **một** member; không kiểm replicated to secondaries |
| `MongoTemplate` với policy majority | Đường ghi qua template hoạt động |
| `InsertOneResult.wasAcknowledged()` | Write ACK theo concern được áp dụng; không chứng minh topology cụ thể |
| Duplicate `_id` | Database từ chối duplicate, Spring Data dịch exception phù hợp |
| Write timeout trong topology mô phỏng lỗi | Cần nhiều data-bearing members và môi trường test điều khiển được |
| Primary stepdown trước/sau majority | Cần chaos/integration test **riêng**, không tạo lỗi trên cluster dùng chung |
| Read secondary sau majority ACK trên MongoDB 8+ | Kiểm causal session/lag theo phiên bản |
| Transaction commit write concern | Dùng transaction manager, kiểm cả result lẫn resilience |

### 20.2. Test cấu hình và acknowledged write

~~~java
package com.example.consistency;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.WriteConcern;
import com.mongodb.client.result.InsertOneResult;
import java.util.concurrent.TimeUnit;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class WriteConcernAcknowledgmentTest {
    @Autowired MongoTemplate template;

    @Test
    void majorityWriteHasAcknowledgedResult() {
        String id = "fixture-wc003";
        var base = template.getDb().getCollection(
            "payments_write_concern_it_003"
        );

        var majority = WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(5, TimeUnit.SECONDS);

        var collection = base.withWriteConcern(majority);

        // Dữ liệu kiểm thử thuộc database test biệt lập.
        base.deleteOne(new Document("_id", id));
        try {
            InsertOneResult result = collection.insertOne(
                new Document("_id", id)
                    .append("tenant_id", "test-tenant")
                    .append("state", "PENDING")
            );

            assertThat(collection.getWriteConcern())
                .isEqualTo(majority);
            assertThat(result.wasAcknowledged()).isTrue();
            assertThat(base.countDocuments(
                new Document("_id", id)
            )).isEqualTo(1L);
        } finally {
            base.deleteOne(new Document("_id", id));
        }
    }
}
~~~

**Giới hạn của test:** nó **không** mô phỏng secondary failover hay chứng minh thực tế hai/trên ba thành viên đã journal. Nếu chạy với single-node replica set, majority chỉ cần một node; nếu chạy standalone, semantics cũng khác với một replica set nhiều nodes. Cần test chaos riêng trong topology phù hợp.

### 20.3. Test Spring Data `DuplicateKeyException`

Thêm trong test class có `template`:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.dao.DuplicateKeyException;

@Test
void duplicateIdIsRejected() {
    String id = "fixture-wc003-dup";
    var collection = template.getDb().getCollection(
        "payments_write_concern_it_003"
    );

    collection.deleteOne(new Document("_id", id));
    try {
        template.insert(
            new org.bson.Document("_id", id)
                .append("state", "PENDING"),
            "payments_write_concern_it_003"
        );

        assertThatThrownBy(() -> template.insert(
            new org.bson.Document("_id", id)
                .append("state", "PAID"),
            "payments_write_concern_it_003"
        )).isInstanceOf(DuplicateKeyException.class);
    } finally {
        collection.deleteOne(new Document("_id", id));
    }
}
~~~

Test phải chạy khi driver/template dùng **acknowledged write**; nếu cố dùng `w:0`, kỳ vọng nhận `DuplicateKeyException` tại client không còn đáng tin cậy. Test này kiểm ràng buộc `_id` và exception translation, không kiểm majority journaling.

### 20.4. Chaos test cho timeout — chỉ trong cluster được phép phá hỏng

Trong một môi trường **ba-node replica set do test sở hữu**, có thể:

1. Tạo một write với `w:"majority"` và `wtimeout` hữu hạn.
2. Có kiểm soát, làm các secondary tạm thời không thể xác nhận.
3. Gửi write tới primary, ghi nhận write concern error.
4. Kiểm primary có thể đã lưu document dù client báo lỗi.
5. Khôi phục secondary và đối soát write bằng read concern phù hợp.
6. Lặp trên một kịch bản có election để kiểm rủi ro rollback của `w:1`.

**Không thực hiện các thao tác ngắt replica/stepdown trên production hoặc MongoDB test dùng chung.** Không có tài liệu nào cho phép gây disruption chỉ để học. Có thể bắt đầu bằng kiểm thử logic xử lý **mô phỏng exception** trong service và đặt test failover thật vào môi trường chaos riêng.

### 20.5. Kiểm tính nhất quán của config

Một application có thể đồng thời có:

- `MongoRepository` mặc định.
- `MongoTemplate` riêng cho payments.
- `ReactiveMongoTemplate` cho WebFlux.
- Java Driver `MongoCollection` dùng trực tiếp.

Hãy kiểm từng đường ghi và **write concern thực tế**. Test một template **không chứng minh** repository hoặc reactive template khác có cùng policy.

## 21. Những lỗi thường gặp

| Giả định hoặc triệu chứng | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “Đã ACK thì không thể mất dữ liệu” | `w:1` có thể rollback sau election | Chọn concern theo yêu cầu durability, kiểm journaling |
| “`j:true` tương đương majority” | Primary journal không chứng minh replica majority | Dùng `w:"majority"` khi cần chống rollback do failover |
| “`w:"majority"` nghĩa mọi secondary đã apply” | Majority cần tập con, MongoDB 8+ có thể ACK oplog trước khi secondary apply | Causal session với majority read/write khi cần read-after-write |
| “`w:2` luôn là majority” | Topology 5 voting members cần đa số 3 | Chọn `w:"majority"` theo mức nghiệp vụ |
| “Arbiter giúp ACK write majority” | Arbiter không chứa dữ liệu | Kiểm thành viên data-bearing voting và default concern |
| “MongoDB 5+ luôn dùng majority mặc định” | Có trường hợp arbiter và explicit client/cluster defaults | Xem `getDefaultRWConcern` và command thực tế |
| “`wtimeout` nghĩa server chưa ghi” | Primary có thể đã apply, tiếp tục replicate sau lỗi | Đối soát/idempotency, không retry mù |
| “`wtimeout:0` là timeout tức thì” | 0 là không đặt timeout cho write concern | Đặt timeout phù hợp SLO |
| “Socket timeout nghĩa insert thất bại” | Kết quả có thể unknown | Kiểm khóa/idempotency, phân loại lỗi |
| “`wasAcknowledged()==true` chứng minh majority” | Có thể chỉ ACK theo `w:1` | Kiểm write concern áp dụng, topology và driver |
| “`matchedCount=0` là lỗi durability” | Là kết quả predicate; document có thể không khớp | Phân biệt matched/modified với ACK |
| “`@Transactional` luôn tạo MongoDB transaction” | Thiếu manager/topology hoặc config session | Cấu hình đúng transaction manager và test |
| “Trong transaction đặt `w` riêng từng write” | MongoDB yêu cầu write concern ở cấp transaction | Đặt transaction write concern khi commit |
| “Driver retry cho phép ứng dụng retry mọi `$inc`” | Retry thủ công thành operation mới có thể tăng hai lần | Idempotency và retry policy phân loại |
| “Read concern majority tự nâng write concern” | Hai thiết lập khác nhau | Cấu hình cả read/write phù hợp use case |
| “Reactive `Mono` chỉ một giá trị nghĩa w:1” | Publisher cardinality không liên quan write concern | Xem template/driver config |
| “Majority write nhanh chậm do Java mapping” | Có thể đợi replication/journal/topology | Theo dõi secondary lag và journal I/O |
| “Majority + journal thay thế backup” | Không bảo vệ khỏi xóa nhầm/bug đã commit | Backup, PITR, kế hoạch phục hồi |

## 22. Checklist trước khi phát hành nghiệp vụ ghi

1. **Phân loại dữ liệu** theo mức chấp nhận mất ghi: payment, order, audit, cache hay telemetry.
2. **Kiểm topology**: P-S-S, P-S-A, số voting data-bearing members, replica lag, journaling.
3. **Không suy từ default**: xác nhận write concern ở MongoClient/URI, template, resolver và server.
4. **Chọn `w` rõ ràng**: `w:1`, `w:"majority"` hoặc numeric theo yêu cầu thực.
5. **Xem `j` cùng `writeConcernMajorityJournalDefault`**, không tách journal khỏi durability.
6. **Đặt `wtimeout` phù hợp** và phân biệt với deadline tổng/request/socket.
7. **Thiết kế outcome unknown**: không map timeout thành chắc chắn thất bại.
8. **Dùng idempotency key** và trạng thái đối soát cho nghiệp vụ không được lặp.
9. **Phân biệt ACK với result count**: `matchedCount`/`modifiedCount` không phải durability proof.
10. **Định nghĩa read-after-write**: đọc primary, read concern/causal session nếu dùng secondary.
11. **Đặt write concern ở commit** nếu dùng multi-document transaction.
12. **Kiểm mọi đường ghi**: repository, template, reactive và driver trực tiếp.
13. **Test exception translation** và lỗi business như duplicate key.
14. **Chaos-test riêng** cho failover, replication lag và write concern timeout.
15. **Theo dõi metric**: errors, majority lag, journal latency, rollback events.
16. **Có backup/restore** và quy trình vận hành khi majority không khả dụng.

## 23. Bài thực hành và đáp án

Các câu hỏi là những kịch bản độc lập. Không cần phá replica set production để trả lời.

### Bài 1 — ACK từ primary

MongoDB nhận `{w:1}`, primary xác nhận insert. Có thể nói dữ liệu đã bền vững qua failover không?

**Đáp án:** Không. Write có thể chưa replicate; nếu primary mất quyền và lịch sử write không thuộc majority, write đã ACK vẫn có thể rollback.

### Bài 2 — `w:1,j:true`

Đã journal trên primary thì vì sao vẫn có thể rollback?

**Đáp án:** Journal giúp phục hồi sau crash của primary nhưng không đảm bảo history được đa số replica set chấp nhận. Một primary mới có thể được bầu từ các thành viên chưa có write đó.

### Bài 3 — Majority trong ba-node replica set

Replica set P-S1-S2, cả ba voting và chứa dữ liệu. `w:"majority"` cần bao nhiêu member?

**Đáp án:** Hai trong ba voting data-bearing members đủ điều kiện, thường là P và ít nhất một secondary.

### Bài 4 — Majority trong năm-node replica set

`w:2` có giống `w:"majority"` không?

**Đáp án:** Không. Majority của năm voting members là ba, còn `w:2` yêu cầu hai member phù hợp.

### Bài 5 — P-S-A

Arbiter có thể thay secondary đang mất kết nối để xác nhận write majority không?

**Đáp án:** Không. Arbiter vote trong election nhưng không lưu dữ liệu/oplog; nó không thể đóng góp data-bearing acknowledgment. Trong P-S-A, cần secondary có dữ liệu để đạt majority write.

### Bài 6 — Default MongoDB 5+

Có thể luôn tin không cấu hình gì thì `w:"majority"` không?

**Đáp án:** Không. Phần lớn deployment 5+ dùng majority implicit default, nhưng một số topology chứa arbiter có thể mặc định `w:1`, và cấu hình client/cluster explicit có thể ghi đè.

### Bài 7 — Journal default

`w:"majority"` nhưng `j` không chỉ định. MongoDB có luôn đợi journal không?

**Đáp án:** Phụ thuộc `writeConcernMajorityJournalDefault` và storage engine/topology. Với mặc định thông thường true, majority acknowledgment có cơ chế journal durability; nếu false, có thể ACK khi dữ liệu mới ở memory.

### Bài 8 — `wtimeout`

Write majority timeout sau 5 giây. Có thể khẳng định collection chưa có document không?

**Đáp án:** Không. Primary có thể đã apply; secondary còn có thể tiếp tục replicate sau lỗi. Cần đối soát thay vì retry không kiểm soát.

### Bài 9 — `wtimeout:0`

Đây có phải “không chờ” không?

**Đáp án:** Không. Nó biểu thị không đặt giới hạn thời gian chờ riêng cho write concern.

### Bài 10 — `matchedCount=0`

`UpdateResult.wasAcknowledged()==true`, `matchedCount==0`. Durability có thất bại?

**Đáp án:** Không nhất thiết. ACK là mức xác nhận write, còn matched count cho biết filter không khớp document nào; hai trục khác nhau.

### Bài 11 — Driver Java

Viết cấu hình majority + journal + timeout 5 giây.

**Đáp án:**

~~~java
WriteConcern concern = WriteConcern.MAJORITY
    .withJournal(true)
    .withWTimeout(5, TimeUnit.SECONDS);
~~~

### Bài 12 — Spring Data template

Làm sao đặt chính sách này cho một `MongoTemplate`?

**Đáp án:**

~~~java
template.setWriteConcern(
    WriteConcern.MAJORITY.withJournal(true)
);
~~~

Phải kiểm service/repository **thực sự dùng template đó**, không chỉ có bean ở application context.

### Bài 13 — Secondary read

MongoDB 8+ đã ACK `w:"majority"`, vậy một read ngay trên secondary chắc chắn có document chưa?

**Đáp án:** Chưa chắc. Secondary có thể đã durably written oplog entry nhưng chưa apply vào collection. Dùng causally consistent session kết hợp majority read/write khi cần read-your-writes qua secondary.

### Bài 14 — Retry `$inc`

Ví trừ 100.000 bằng `$inc:-100000`, client timeout. Có nên chạy lại y hệt như một request mới không?

**Đáp án:** Không. Có thể đã trừ lần đầu. Thiết kế ledger/idempotency key và kiểm kết quả trước khi thử lại.

### Bài 15 — Transaction commit

Transaction cập nhật hai collection. Nên đặt write concern ở mỗi `updateOne` hay cấp transaction?

**Đáp án:** **Cấp transaction/commit**, theo yêu cầu MongoDB. Nếu commit chỉ ACK `w:1` vẫn có rủi ro rollback sau failover.

### Bài 16 — Performance

Sau khi chuyển từ `w:1` sang majority, p95 write latency tăng. Nên hạ về `w:1` ngay không?

**Đáp án:** Không mặc định. Cần đo replication lag, disk/journal latency, topology và workload; cân nhắc yêu cầu durability/SLO trước khi thay chính sách.

### Bài 17 — Kiểm thử

Test trên replica set có đúng một node, `WriteConcern.MAJORITY` thành công. Có chứng minh hai replica đã ACK không?

**Đáp án:** Không. Majority của single-node là một. Muốn test replication acknowledgment phải có topology nhiều data-bearing voting members và kiểm lỗi trong môi trường chuyên dụng.

### Bài 18 — Idempotency và duplicate key

Gửi lại request `paymentId=pay301` và nhận duplicate key. Có chắc retry này vô hại không?

**Đáp án:** Chưa đủ. Phải kiểm tenant, order, số tiền và fingerprint request có **giống lần trước** không; nếu khác, báo conflict thay vì trả thành công.

### Bài 19 — Unacknowledged

`w:0` có thể giúp biết insert thất bại do E11000 để trả HTTP 409 ngay không?

**Đáp án:** Không. Khi không yêu cầu server acknowledgment, client không có tín hiệu tin cậy về duplicate key. Dùng acknowledged write cho nghiệp vụ cần phản hồi chính xác.

### Bài 20 — Backup

Ứng dụng dùng `w:"majority",j:true`. Có còn cần backup không?

**Đáp án:** Có. Majority/journal không phục hồi được xóa nhầm đã được majority-committed hoặc nhiều loại lỗi vận hành; cần backup và kiểm tra khả năng restore.

## Tài liệu tham khảo

- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): `w`, `j`, `wtimeout`, acknowledgment, implicit default, majority journaling và sự khác biệt MongoDB 8+.
- [MongoDB Manual — Write Concern for Replica Sets](https://www.mongodb.com/docs/manual/core/replica-set-write-concern/): majority, numeric write concern, replica members và timeout.
- [MongoDB Manual — Rollbacks During Replica Set Failover](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/): rollback của `w:1`, durability majority và journaling.
- [MongoDB Manual — Journaling](https://www.mongodb.com/docs/manual/core/journaling/): đồng bộ journal và sự khác biệt storage engine.
- [MongoDB Manual — Causal Consistency and Read/Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/): majority write/read concern và các bảo đảm nhân quả.
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): đọc từ primary/secondary và rủi ro stale data.
- [MongoDB Manual — Default Read and Write Concerns](https://www.mongodb.com/docs/manual/reference/mongodb-defaults/): default theo topology và trường hợp arbiter.
- [MongoDB Java Sync Driver — Configure Client-level CRUD Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/configure-crud/): `w`, `journal`, `wTimeoutMS` và các tùy chọn URI/driver.
- [MongoDB Java Sync Driver — Configure Replica Set Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/read-write-config/): `withWriteConcern`, `ReadConcern` và `ReadPreference`.
- [Spring Data MongoDB — Configuration](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-config.html): `MongoTemplate.setWriteConcern`, `WriteConcernResolver` và write result checking.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): transaction managers, write concern tại commit, transaction options và error labels.
- [Spring Data MongoDB — `MongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): các thiết lập write concern và write result handling.
- [Spring Data MongoDB — `ReactiveMongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): cấu hình write concern trong reactive template.
