# Bảng lựa chọn read concern, write concern và read preference trong MongoDB

## 1. Ba nút cấu hình — ba câu hỏi khác nhau

Trong MongoDB, một thao tác đọc hoặc ghi trên replica set/sharded cluster chịu ảnh hưởng của ba khái niệm:

1. **Read concern**: dữ liệu được trả về có những bảo đảm nào về khả năng được duy trì, ảnh chụp nhất quán và thứ tự quan sát?
2. **Write concern**: MongoDB phải nhận được xác nhận ghi từ bao nhiêu thành viên, và có yêu cầu ghi journal hay không, trước khi trả kết quả?
3. **Read preference**: driver **chọn thành viên nào** để thực hiện lệnh đọc — primary hay secondary nào?

Chúng giải quyết **ba chiều khác nhau**. Ví dụ:

```text
                     Java / mongosh client
                              |
                              v
                    Read preference
                 (chọn server để đọc)
                              |
                +-------------+-------------+
                |                           |
             PRIMARY                    SECONDARY
                |                           |
                +-------------+-------------+
                              |
                              v
                       Read concern
               (loại dữ liệu được quan sát)

Client -- write operation --> PRIMARY
                               |
                               v
                          Apply write
                               |
                               v
                         Write concern
                    (mức xác nhận ghi)
                               |
                        Acknowledgment
```

**Ví dụ thường gây nhầm:** `readPreference=secondary` không đồng nghĩa `readConcern=majority`. Đọc từ secondary không tự bảo đảm dữ liệu mới nhất. Ngược lại, `readConcern=majority` không bắt buộc đọc từ secondary; nó có thể dùng trên primary.

### 1.1. Bối cảnh xuyên suốt

Hệ thống quản lý tài khoản trên replica set ba data-bearing members:

```text
              Replica set rsOrders

          +---------- PRIMARY P ----------+
          |  nhận writes                  |
          |  phát oplog                   |
          +-------------------------------+
                       |        |
                 replicate   replicate
                       v        v
                SECONDARY S1  SECONDARY S2

               Java service / mongosh
```

Ứng dụng có các yêu cầu khác nhau:

- Đọc trang danh sách sản phẩm: muốn độ trễ thấp và chấp nhận hơi chậm dữ liệu.
- Hiển thị số dư sau khi vừa chuyển tiền: không chấp nhận thấy số dư cũ.
- Ghi một khoản thanh toán: muốn kết quả bền vững trước failover.
- Báo cáo phân tích: muốn một ảnh chụp nhất quán, không trộn nhiều thời điểm.
- Health dashboard: có thể chấp nhận dữ liệu gần đúng để giảm tải primary.

Không nên dùng một cấu hình read concern/write concern/read preference cho tất cả các trường hợp mà chưa xét business semantics.

### 1.2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện ý nghĩa và giới hạn của từng mức read concern.
2. Giải thích các mức `w:0`, `w:1`, `w:"majority"`, `w:n`, custom tag write concern và `j`.
3. Chọn read preference `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred` hoặc `nearest`.
4. Phân biệt **majority-committed** với **mới nhất**, **read-your-writes**, **causal consistency**, **linearizability** và **snapshot consistency**.
5. Thiết kế cấu hình thích hợp cho CRUD, reporting, audit, payment, background jobs và consumer.
6. Dùng Java Sync Driver và mongosh đặt concerns/preferences ở mức client, database, collection và transaction.
7. Hiểu tác động của replication lag, election, network partition, journal, timeout và sharded cluster.
8. Tạo ma trận kiểm thử, metrics/runbook và quyết định đánh đổi độ trễ–độ sẵn sàng–độ bền.

**Phạm vi:** tập trung vào MongoDB replica sets và sharded clusters trong những phiên bản hiện đại. Tính năng/mức concern hỗ trợ có khác biệt theo phiên bản, storage engine và loại lệnh; cần kiểm tra lệnh cụ thể và deployment mục tiêu. Các ví dụ ghi/xóa chỉ chạy trong database thử nghiệm được sở hữu.

## 2. Bảng tra nhanh: read concern

| Read concern | Đọc trên | Ý nghĩa chính | Có thể thấy dữ liệu rollback? | Có phải mới nhất? | Ứng dụng thường dùng |
|---|---|---|---|---|---|
| `local` | Primary/secondary phù hợp | Trả dữ liệu hiện có trên thành viên đang đọc, không chờ majority commit | **Có thể** | **Không bảo đảm** | Truy vấn thông thường, ưu tiên latency |
| `available` | Một số ngữ cảnh, nổi bật sharded | Ưu tiên availability, không bảo đảm majority; trên sharded có caveat orphaned data | **Có thể** | **Không** | Trường hợp chuyên biệt, hiểu rõ trade-off |
| `majority` | Primary/secondary hỗ trợ | Trả dữ liệu đã majority-committed theo semantics tương ứng | Không theo đường rollback thông thường của majority-committed data | **Không** | Dữ liệu cần tránh nhìn thấy write dễ rollback |
| `linearizable` | **Primary** | Đọc một document với tính chất tuyến tính hóa dưới các điều kiện MongoDB hỗ trợ | Không theo điều kiện linearizable | Mạnh nhất cho real-time single-document reads, nhưng có thể đợi/lỗi | Đọc trạng thái khóa/quyết định nghiệp vụ cực nhạy |
| `snapshot` | Transaction, và một số lệnh đọc ngoài transaction ở server được hỗ trợ | Cùng một snapshot nhất quán tại một thời điểm logic | Theo semantics snapshot/commit áp dụng | **Không mặc định là hiện tại tuyệt đối** | Transaction, đối soát/báo cáo cần consistent snapshot |

**Đọc bảng đúng cách:** “không thấy dữ liệu rollback” không đồng nghĩa “đã thấy write mới nhất”. Một secondary có thể đang đứng sau primary, dù đọc bằng `majority`. Và một `snapshot` có thể hoàn toàn nhất quán **ở một thời điểm quá khứ**.

### 2.1. Các câu hỏi mở đầu

- Có cần ngăn đọc dữ liệu từ một write sau đó bị rollback không?
- Có phải thấy kết quả của chính request vừa ghi không?
- Có cần phản ánh **mọi** write đã thành công trước khi read bắt đầu không?
- Có cần nhiều lệnh trong cùng transaction cùng nhìn một snapshot?
- Có chấp nhận đợi hoặc thất bại trong failover/partition không?

## 3. Bảng tra nhanh: write concern

| Write concern | Điều kiện trả acknowledgment | Điều không bảo đảm | Đánh đổi |
|---|---|---|---|
| `w:0` | Không yêu cầu acknowledgment cho write | Không biết lệnh thành công, validation errors, durability | Ít chờ phản hồi nhưng rủi ro lớn |
| `w:1` | Primary xác nhận đã áp dụng lệnh | Không bảo đảm bản ghi đã được replicate/majority committed | Latency thấp hơn, có nguy cơ rollback sau failover |
| `w:"majority"` | Số thành viên voting/data-bearing theo majority semantics xác nhận | Không phải đồng bộ mọi member, không phải exactly-once business outcome | Bền vững hơn trước một số failover, latency/availability cost |
| `w:2` hoặc `w:n` | Số lượng thành viên phù hợp xác nhận | Không tự đồng nghĩa majority trong mọi topology | Ràng buộc topology/số members |
| Custom tag write concern | Đạt write concern mode tùy chỉnh theo replica set tag configuration | Không đúng nếu mode/replica set config không tương thích | Dành cho placement/policy chuyên biệt |
| `j:true` | Yêu cầu acknowledgment theo journal option được hỗ trợ | Không tự yêu cầu nhiều bản sao nếu `w:1` | Durability/disk cost |
| `wtimeout` | Giới hạn thời gian chờ các yêu cầu write concern | **Không** tự hủy write đã áp dụng | Đưa về trạng thái uncertain cần xử lý |

**Nhớ:** `wtimeout` (hay URI `wtimeoutMS`) chỉ giới hạn **thời gian đợi điều kiện write concern**; khi timeout, thao tác có thể đã áp dụng trên primary. Không tự retry bằng một business action **không idempotent** như chuyển tiền hai lần.

## 4. Bảng tra nhanh: read preference

| Read preference | Chọn server | Fallback | Khi nên cân nhắc | Cạm bẫy |
|---|---|---|---|---|
| `primary` | Chỉ primary | Không dùng secondary | Writes, read-after-write đơn giản, transaction | Primary quá tải hoặc unavailable thì read fail |
| `primaryPreferred` | Primary nếu phù hợp | Secondary khi không có primary | Read availability có kiểm soát | Trong failover có thể đột ngột đọc dữ liệu cũ |
| `secondary` | Chỉ secondary phù hợp | **Không** fallback primary | Reporting/batch read offload | Không có secondary thì fail |
| `secondaryPreferred` | Secondary nếu có | Primary khi không có secondary phù hợp | Offload với fallback | Test có thể tưởng đọc secondary nhưng thực tế đọc primary |
| `nearest` | Thành viên phù hợp có latency gần nhất theo driver server selection | Không phân biệt primary/secondary cứng | Workload chịu stale read, latency-optimized | Không có nghĩa “mới nhất”, không nhất thiết cùng region |

Read preference còn có:

- **Tag sets** để lọc/chọn members có labels như region, workload.
- **`maxStalenessSeconds`** để giới hạn mức ước lượng chậm trễ tương đối của secondary (không phải guarantee dữ liệu mới tuyệt đối).
- **`localThresholdMS`** để chọn trong nhóm servers có độ trễ gần nhau, tùy driver settings.

## 5. Đọc ba bảng trong một ma trận mục tiêu

| Mục tiêu nghiệp vụ | Read concern | Read preference | Write concern của write liên quan | Ghi chú |
|---|---|---|---|---|
| Danh mục sản phẩm không quá nhạy độ mới | `local` hoặc `majority` theo rủi ro rollback | `secondaryPreferred` nếu chấp nhận stale | `w:1`/`majority` theo độ bền cần | Fallback có thể đổi server |
| Đọc order theo ID, muốn ưu tiên latest trên primary | `local`/`majority` theo chính sách | `primary` | `majority` nếu cần chịu failover | Primary không tự cho linearizable guarantee |
| Đọc sau khi vừa ghi, cùng session theo causal consistency | `majority` | `primary` hoặc secondary đủ điều kiện causal | `majority` | Cần client session và thứ tự operations |
| Payment/audit record phải tránh rollback đã ack | `majority` cho reads nhạy | `primary` | `majority`, journaling theo deployment | Cần business idempotency |
| Một document chứa trạng thái khóa/quyết định cần linearizable read | `linearizable` | `primary` | Các writes liên quan `majority` | Có thể chậm/lỗi trong partition; giới hạn single-document semantics |
| Report nhiều reads phải nhất quán cùng snapshot | `snapshot` trong transaction / supported snapshot reads | `primary` trong transaction | Transaction commit `majority` | Chú ý giới hạn tuổi/thời gian transaction |
| Báo cáo phụ trợ chấp nhận lag | `majority` nếu tránh rollback, hoặc `local` nếu chấp nhận | `secondary`/`nearest` với tags | `majority` cho source writes quan trọng | Theo dõi lag, maxStaleness |
| Change stream consumer | Semantics stream theo MongoDB, không dùng bảng như `find` thường | Theo hỗ trợ stream/server | Source writes `majority` nếu cần durable acknowledgment | Resume tokens, oplog window, idempotency |
| Bảo vệ nguồn dữ liệu trước primary failover | Theo read requirement | Thường `primary` cho critical reads | `majority` | Majority không có nghĩa mọi secondary đã thấy |

Bảng là **điểm bắt đầu**, không phải cấu hình duy nhất. Đặc biệt phải xác nhận version/feature constraints của lệnh và SLA business trước khi áp dụng.

## 6. Defaults: đừng suy từ code không đặt option

### 6.1. Những mặc định thường gặp

- Read preference mặc định của driver thông thường là **`primary`**.
- Read concern mặc định của phần lớn operations là **`local`** nếu không bị override bằng cấu hình tương ứng.
- Write concern mặc định **không luôn là `w:1`**. MongoDB server hiện đại có quy tắc implicit default write concern phụ thuộc topology (đặc biệt cấu hình có arbiter), và cluster có thể đặt default read/write concerns qua quản trị.

### 6.2. Dấu hiệu nguy hiểm

```java
MongoClient client = MongoClients.create(uri);
collection.insertOne(doc);
```

Bạn không thể kết luận chính xác write durability chỉ từ hai dòng này. Cần kiểm tra URI, client/database/collection settings, transaction options, server default RW concern, phiên bản/topology.

### 6.3. Cấu hình kế thừa và override

```text
MongoDB deployment defaults
            |
MongoClientSettings / connection string
            |
MongoDatabase overrides
            |
MongoCollection overrides
            |
Operation / session / transaction-specific options
```

Không phải mọi operation đều cho override cùng cách; transaction có phạm vi riêng. Tài liệu driver/server cho operation được dùng là nguồn xác nhận cuối.

### 6.4. Mặc định write concern có thể đổi khi topology đổi

Nếu từ replica set ba data-bearing members chuyển sang primary-secondary-arbiter (PSA), implicit default write concern và majority availability có thể khác. Vì vậy với giao dịch nhạy cảm, **đặt tường minh requirement** rồi kiểm tra deployment đáp ứng.

## 7. Read concern `local`: đọc nhanh nhưng chưa majority-committed

`local` cho phép đọc dữ liệu hiện tại trên server được chọn, không đòi dữ liệu đó đã được ghi nhận bởi majority.

Ví dụ:

```text
T0: primary P áp dụng order.status="PAID"
T1: client đọc P với readConcern local -> thấy "PAID"
T2: P mất majority và bước ghi chưa replicate đủ
T3: một secondary thành primary, write cũ có thể rollback
```

Client đã nhìn thấy một trạng thái có thể không trở thành lịch sử committed của replica set.

### 7.1. Tác động trên secondary

`readPreference=secondary` + `readConcern=local` có thể đọc dữ liệu ở secondary đã apply nhưng chưa majority-committed, và thường chậm dữ liệu so với primary.

### 7.2. Khi nào hợp lý?

- UI tra cứu không nhạy với một thay đổi chưa majority.
- Telemetry/report tạm thời, có thể chịu kết quả chưa final.
- Workload đã có cơ chế reconcile hoặc eventual consistency.
- Khi ưu tiên tốc độ và business chấp nhận rollback/stale view.

### 7.3. Không dùng `local` làm bằng chứng write đã bền

Đọc thấy giá trị trên primary không đồng nghĩa write đó đã replicate đủ để sống qua failover.

### 7.4. So với `w:1`

`w:1` mô tả **acknowledgment của write**; `local` mô tả **dữ liệu một read có thể nhìn thấy**. Chúng thường đi cùng về latency nhưng là hai cấu hình độc lập.

## 8. Read concern `available`: dùng có ý thức

`available` không chờ dữ liệu majority-committed và chú trọng availability. Trong **sharded clusters**, MongoDB có caveat quan trọng: truy vấn `available` có thể trả về **orphaned documents** trong một số tình huống chunk migration.

### 8.1. Orphaned document là gì?

Khi một chunk chuyển shard, dữ liệu cũ có thể tồn tại tạm trên shard nguồn trong quá trình cleanup. Dữ liệu bản sao này không được coi là tài liệu thuộc shard nguồn khi định tuyến chuẩn.

### 8.2. Vì sao nguy hiểm với báo cáo?

Nếu query nhìn cả bản cũ và bản mới trong một thời điểm không phù hợp, báo cáo có thể đếm trùng hoặc phản ánh dữ liệu không mong đợi.

### 8.3. Phạm vi sử dụng

Chỉ dùng khi **hiểu rõ** vì sao cần behavior khác `local`, deployment hỗ trợ và rủi ro orphaned results được chấp nhận. Không chọn `available` đơn thuần vì tên nghe “luôn hoạt động”.

### 8.4. Trên replica set

Trong nhiều tác vụ replica set bình thường, `available` có tính chất gần `local` về mức dữ liệu được thấy; vẫn phải kiểm tra support và semantics theo phiên bản.

## 9. Read concern `majority`: committed nhưng chưa chắc mới nhất

`majority` trả về dữ liệu đã được **majority-committed** theo quy tắc replication/commit point của deployment.

### 9.1. Timeline minh họa

```text
P  : v1 ---- v2 ---- v3
S1 : v1 ---- v2
S2 : v1

Committed point hiện tại có thể ở v2 (tùy acknowledgments).

Read majority trên S2:
  có thể vẫn trả v1 vì S2 chưa apply v2.
```

Tính chất cần ghi nhớ: **majority không có nghĩa newest**. Một secondary có thể trả majority-committed data cũ hơn trạng thái mới trên primary.

### 9.2. Khi nào ưu tiên?

- Không muốn báo cáo dựa vào một write có thể bị rollback theo cơ chế thường gặp.
- Dữ liệu audit/critical read cần một mức chắc chắn cao hơn `local` về lịch sử committed.
- Causal consistency cùng session khi kết hợp `w:"majority"`.
- Reads trước khi đưa quyết định phải dựa trên stable/committed state, nhưng không bắt buộc tuyến tính hóa real-time.

### 9.3. Không đủ để đảm bảo read-your-writes xuyên các thành viên

Một client ghi `w:majority`, rồi đọc trên secondary với `readConcern=majority` nhưng **không** dùng causal session/afterClusterTime có thể thấy giá trị cũ nếu secondary đã bị tụt.

### 9.4. Không chứng minh toàn bộ write đã được mọi secondary apply

Trong replica set ba data-bearing members, majority là 2. Thành viên thứ ba có thể chưa nhận được dữ liệu.

### 9.5. Error/latency

Read majority có thể cần đợi commit point, đặc biệt khi replication bị lag hoặc majority không available. Cần timeout/deadline rõ và SLO thích hợp.

## 10. Read concern `linearizable`: một document theo thứ tự thời gian thực

Mục tiêu của linearizable read là: với những **single-document read operations** được hỗ trợ trên primary, một read bắt đầu sau khi write liên quan đã hoàn tất và được majority acknowledged không trả lịch sử “trước write” theo cách phá thứ tự thực tế.

### 10.1. So sánh trực quan

```text
Client A: write lock.owner="A" with majority
             |---------- completed ----------|

Client B:                                  |--- read begins ---|

Linearizable read:
  must be consistent with completed majority write
  or may wait/fail if guarantee cannot be met.
```

### 10.2. Khác `majority` ở điểm nào?

- `majority` tập trung vào lịch sử đã majority committed.
- `linearizable` bổ sung ràng buộc về **real-time ordering** của single-document read với majority writes.

### 10.3. Điều kiện thiết yếu

- Thực hiện trên **primary**.
- Chỉ áp dụng các dạng **single-document read** được hỗ trợ.
- Các writes cần thiết cho linearizable guarantee phải dùng `w:"majority"`.
- Không xem linearizable read như một multi-document transaction snapshot.
- Cần `maxTimeMS` để tránh chờ vô hạn khi majority unavailable.

### 10.4. Ví dụ

Một ứng dụng kiểm tra document:

```javascript
{
  _id: "leader-lock:billing",
  owner: "worker-17",
  leaseEpoch: NumberLong("42")
}
```

Nếu quyết định nhạy với một lock đã được majority-acknowledged, linearizable read có thể phù hợp. Tuy nhiên để chống stale worker, **lease fencing và compare-and-set khi write** vẫn cần: read linearizable riêng không biến logic read-then-write thành atomic transaction.

### 10.5. Không dùng cho mọi UI

Linearizable read có thể tăng latency và giảm availability trong partition. Dùng mặc định cho danh sách 100.000 sản phẩm có thể là chi phí không cần thiết.

## 11. Read concern `snapshot`: nhiều operations nhìn một thời điểm logic

`snapshot` hỗ trợ việc đọc một ảnh chụp nhất quán theo khả năng của MongoDB.

### 11.1. Trong transaction

```text
T0 transaction starts
T1 reads account A
T2 concurrent writer changes account B
T3 transaction reads account B

Snapshot semantics:
  transaction sees a consistent snapshot,
  not an arbitrary mixture of unrelated times.
```

### 11.2. Ngoài transaction

Trong MongoDB server versions hỗ trợ (ví dụ các phiên bản từ 5.0 cho những operations được liệt kê), read concern `snapshot` còn dùng được với **một số read commands ngoài transaction** như `find`/`aggregate`/`distinct` theo semantics của server. Không suy rằng tất cả lệnh/versions đều hỗ trợ.

### 11.3. AtClusterTime và snapshot time

Khi cần đọc một snapshot thời điểm cụ thể và phiên bản/operation hỗ trợ, có cơ chế `atClusterTime`. Đây là một timestamp logic trong cửa sổ snapshot/history mà server có thể cung cấp; không chọn tùy ý timestamp quá cũ rồi mong server giữ mọi phiên bản mãi.

### 11.4. Snapshot không phải newest

Một snapshot chính xác tại T0 vẫn có thể không có writes được commit tại T1. Nó giải bài toán **nhất quán giữa dữ liệu quan sát**, không tự giải bài toán “phải mới nhất”.

### 11.5. Giới hạn tuổi transaction

Transaction lâu có thể giữ lịch sử dữ liệu, tăng áp lực WiredTiger/cache và bị hủy khi quá thời gian cấu hình. Không mở một transaction kéo dài nhiều giờ để scan toàn database chỉ vì muốn báo cáo toàn bộ không đổi.

### 11.6. Snapshot read concern và write concern commit

Trong transaction, mức độ bền vững/majority semantics cần được xem cùng write concern **ở commit**. Không giả định transaction `readConcern:"snapshot"` với commit `w:1` tạo ra mọi guarantee như transaction commit majority.

## 12. Viết quyết định về read concern theo dữ liệu

| Câu hỏi | Câu trả lời | Hướng chọn |
|---|---|---|
| Có chấp nhận kết quả của write sau này bị rollback? | Có | `local` có thể phù hợp |
| Có yêu cầu dữ liệu đã commit bởi majority? | Có | `majority` |
| Có yêu cầu real-time single-document ordering? | Có | `linearizable` + majority writes + primary |
| Cần nhiều tài liệu cùng ảnh chụp logic? | Có | `snapshot` với transaction/supported operation |
| Chỉ muốn giảm độ trễ dưới mọi điều kiện? | Có nhưng chấp nhận rủi ro | Cân nhắc `local`/`available` theo deployment |
| Đọc từ secondary nhất định phải mới nhất? | Có | Không thể bảo đảm bằng `secondary` đơn thuần |

**Phân biệt mục tiêu:** bảo đảm **freshness**, **durability** và **consistency** không có cùng một nút cấu hình giải quyết tất cả.

## 13. Write concern `w:0`: không xác nhận không có nghĩa thành công

`w:0` là unacknowledged write. Client không chờ server xác nhận kết quả theo cùng cách acknowledged writes.

```text
Client sends write
      |
      +--> does not wait for normal write acknowledgment
      |
      v
Client continues
```

### 13.1. Rủi ro

- Không chắc server đã nhận/applied write.
- Không có write result đáng tin để phân biệt duplicate key hoặc validation failure theo đường acknowledgment thông thường.
- Không thích hợp cho orders/payments/audits cần biết kết quả.
- Có thể gây khó khi recovery vì ứng dụng đã xử lý bước tiếp theo.

### 13.2. Không tương đương fire-and-forget an toàn

Một event/log không quan trọng có thể chọn mức đảm bảo thấp theo kiến trúc, nhưng nếu dữ liệu vẫn cần lưu, nên cân nhắc một queue/telemetry pipeline phù hợp hơn thay vì ngầm dùng `w:0`.

### 13.3. Khả năng tương thích

Các lệnh/session/retryable writes có điều kiện hỗ trợ riêng. Không giả định mọi operation dùng `w:0` có thể kết hợp transaction hoặc retry semantics tương đương acknowledged writes.

## 14. Write concern `w:1`: primary đã chấp nhận, chưa bảo đảm không rollback

`w:1` yêu cầu primary xác nhận write đã áp dụng, nhưng không đòi đủ replica set members theo majority.

### 14.1. Timeline

```text
T0 client sends write to P
T1 P applies write
T2 P returns w:1 success
T3 P fails before S1/S2 replicate
T4 election chooses new P
T5 old unreplicated write may be rolled back
```

Ứng dụng đã nhận success tại T2 nhưng vẫn có thể mất write sau election.

### 14.2. Khi nào chấp nhận?

- Data có thể tái tạo/reconcile.
- Workload có mức durability SLA thấp hơn.
- Có event log/source-of-truth khác được bảo vệ.
- Latency là ưu tiên lớn và business hiểu rủi ro.

### 14.3. `j:true` với `w:1`

Yêu cầu acknowledgment sau journal theo khả năng storage engine **không** buộc write replicate sang majority. Nó giúp với một số crash local, nhưng failover tới secondary khác vẫn có thể rollback write chưa majority committed.

### 14.4. Không gộp mọi ack vào “đã bền”

Mức độ “bền” phải chỉ rõ trước lỗi nào: process crash, power loss, primary election, mất cả region, human error, logical corruption? Write concern giải quyết **một phần**; còn cần topology, backups, app idempotency và disaster recovery.

## 15. Write concern `w:"majority"`: cam kết của đa số

Ví dụ replica set ba data-bearing members, hai thành viên cần thiết cho majority.

```text
P  applied + acknowledged  ---> 1
S1 applied + acknowledged  ---> 2
S2 still behind            ---> not needed for majority

writeConcern w:majority satisfied
```

### 15.1. Bảo đảm được gì?

Một write đã majority-acknowledged được thiết kế để không bị rollback theo quy tắc bầu cử/replication bình thường, với các giả định về durability, cấu hình journal/storage engine và hành vi hệ thống.

### 15.2. Không có nghĩa tất cả secondary đã thấy

Secondary S2 vẫn có thể lag. Đọc S2 ngay sau write có thể thấy bản cũ; `w:"majority"` không đồng thời là yêu cầu “mọi reads sẽ thấy giá trị vừa ghi”.

### 15.3. Không có nghĩa ứng dụng exactly-once

Nếu server đã ghi nhưng response bị mất, caller có thể retry business request. Nếu dùng một `$inc` mới với transaction ID khác, vẫn có nguy cơ thực hiện nghiệp vụ nhiều lần. Cần idempotency key/unique constraint/transaction protocol.

### 15.4. Latency

Độ trễ acknowledgment bao gồm thời gian chờ đủ replica set members theo topology, network, journal và workload. Khi secondary lag hoặc mất majority, lệnh có thể chờ, timeout hoặc thất bại.

### 15.5. Default majority không phải số 2 cố định

Với 5 voting members, majority là 3. Với có arbiters, data-bearing votes và khả năng nhận acknowledgment cần phân tích kỹ; không tính bằng “chỉ nhìn số containers”.

## 16. Write concern `w:n`, tag modes và topology

MongoDB cho phép mức write concern đếm số members (ví dụ `w:2`) và custom modes dựa trên replica set tags trong những điều kiện được hỗ trợ.

### 16.1. Đếm members không luôn tương đương majority

| Voting members | Majority votes | `w:2` có phải majority? |
|---:|---:|---|
| 3 | 2 | Có thể tương ứng về số lượng, còn xem semantics/config |
| 5 | 3 | **Không** |
| 7 | 4 | **Không** |

Chọn `w:"majority"` khi mục tiêu thật sự là majority semantics, thay vì hardcode `w:2` theo topology tạm thời.

### 16.2. Tag-aware write concern

Ví dụ các nodes có tags `region=apac`, `region=eu`, `region=us`. Một custom write concern mode có thể yêu cầu acknowledgment theo tập tag mong muốn, khi được định nghĩa trong replica set configuration.

### 16.3. Không tự hứa đa-region durability

Tag policy phải được kiểm thử với replica set votes, number of data-bearing members, configuration và network partitions. Đáp ứng tag write concern không đồng nghĩa toàn bộ application có DR và regional failover hoàn chỉnh.

### 16.4. Indexing không liên quan trực tiếp

Write concern không phải index option; nó đặt ở client/operation/transaction/server default. Dùng unique index để bảo vệ business identity là một cơ chế **khác**.

## 17. Journal option `j` và khái niệm durable

Trong MongoDB với WiredTiger, journal giúp ghi nhận các thay đổi để phục hồi trong các điều kiện nhất định khi tiến trình hoặc máy gặp sự cố.

### 17.1. Kết hợp `w` và `j`

| Cấu hình | Điều bạn yêu cầu | Điều không nên suy |
|---|---|---|
| `{w:1}` | Primary xác nhận apply | Không chắc journal/replica copy như mong muốn |
| `{w:1,j:true}` | Primary xác nhận theo journal semantics | Chưa có majority replication |
| `{w:"majority"}` | Majority acknowledgment theo server configuration | Không mặc định mọi node hay region đều còn dữ liệu |
| `{w:"majority",j:true}` | Majority acknowledgment và yêu cầu journal theo trường hợp hỗ trợ | Không thay backups, không có business exactly-once |

### 17.2. `writeConcernMajorityJournalDefault`

Độ bền liên quan tới majority journaling còn phụ thuộc server/storage-engine configuration. Một số deployment có ngoại lệ và tùy chọn thay đổi journal behavior. Khi thiết kế SLA cần kiểm tra **giá trị thực tế**, không chỉ đọc connection string.

### 17.3. `j:true` có thể tăng latency

Journal I/O có chi phí; workload write-heavy cần đo cùng hệ thống storage, replication, network và ổ đĩa thật.

### 17.4. Không xem `j:true` là RAID/backup

Journal không bảo vệ khỏi người dùng xóa nhầm collection, ransomware, buggy deployment hoặc mất toàn bộ bản sao/region theo một kịch bản disaster. Phải dùng backup/PITR, versioning, guardrails và tests.

## 18. `wtimeout` và kết quả ghi chưa rõ

Ví dụ command:

```javascript
db.runCommand({
  insert: "orders",
  documents: [
    {
      _id: "W471-01",
      status: "CREATED"
    }
  ],
  writeConcern: {
    w: "majority",
    wtimeout: 5000
  }
});
```

Trong `writeConcern` của command, `wtimeout` tính bằng **milliseconds**.

### 18.1. Timeout của write concern là gì?

Primary có thể đã áp dụng write, nhưng chưa nhận đủ acknowledgments theo write concern trong thời gian giới hạn. Result có thể chứa `writeConcernError` hoặc driver ném exception tương ứng.

### 18.2. Không đồng nghĩa write bị rollback

```text
T0 primary applies insert
T1 no majority confirmation within budget
T2 write concern timeout returned
T3 secondaries catch up later

Final state:
  record may exist.
```

### 18.3. Business retry

Nếu thao tác là “tạo đơn hàng”, dùng deterministic request ID:

```javascript
{
  _id: "order:client-request-471",
  requestId: "client-request-471",
  status: "CREATED"
}
```

Với unique index trên business request identity, retry có thể kiểm tra operation cũ rồi quyết định. Không tạo một ObjectId mới để insert lần hai mà không kiểm tra.

### 18.4. Phân biệt các timeout

| Timeout | Phạm vi | Hệ quả |
|---|---|---|
| `wtimeout`/`wtimeoutMS` | Chờ điều kiện write concern | Write có thể đã áp dụng |
| Server selection timeout | Driver chọn primary/eligible member | Có thể chưa gửi lệnh; phải phân biệt từng attempt |
| Socket timeout | Network wait/IO | Kết quả có thể unknown sau khi gửi request |
| `maxTimeMS` | Server-side operation time limit khi lệnh hỗ trợ | Phải hiểu command cụ thể, không suy auto-rollback mọi side effects |
| Transaction timeout | Giới hạn lifetime/behavior transaction | Commit outcome cần xét riêng |

### 18.5. Không retry mọi exception

Phân loại error labels, error codes và business invariants. Duplicate key có thể biểu thị idempotent request trước đã thành công hoặc một conflict thật; không tự đổi thành success nếu payload không tương đương.

## 19. Write concern trong replica set có arbiter

Một replica set **P–S–A**:

```text
P  = primary, lưu dữ liệu
S  = secondary, lưu dữ liệu
A  = arbiter, bỏ phiếu nhưng không lưu dữ liệu

Votes: 3; election majority: 2
Data-bearing members: P, S
```

### 19.1. Tại sao một arbiter không thay một bản sao dữ liệu?

Arbiter không nhận/giữ data replication như secondary. Khi S offline, P + A có thể đủ votes cho một số election circumstances, nhưng **không** làm cho dữ liệu mới được ghi trên P đạt majority-data acknowledgment cần thiết theo MongoDB semantics.

### 19.2. Điều bất ngờ

Một PSA cluster có thể còn khả năng nhận `w:1` writes trong một số phân vùng nhưng không đáp ứng `w:"majority"` writes khi data-bearing S không khả dụng. Các lệnh majority có thể bị block/timeout.

### 19.3. Default write concern thay đổi theo topology

Implicit default write concern của MongoDB phiên bản hiện đại có quy tắc phụ thuộc số arbiter và data-bearing voting members; với một số cấu hình có arbiter, default có thể là `w:1` thay vì `majority`. Do đó không dựa vào mặc định như một SLA.

### 19.4. Thiết kế production

Replica set ba **data-bearing** members thường thuận lợi hơn cho majority data availability và failover so với P–S–A khi có đủ hạ tầng. Tuy nhiên sizing, voting, regions và write concern cần được đánh giá theo deployment cụ thể.

## 20. Read preference `primary`: ưu tiên đường đọc chính

`primary` chỉ đọc primary. Đây thường là mặc định và là mode nên chọn khi:

- Read sau write cần tránh secondary lag, nếu contract không yêu cầu linearizable vượt mức đó.
- Transaction/session có các yêu cầu lựa chọn primary.
- Administrative operations cần primary.
- Dữ liệu quan trọng, hệ thống không muốn fallback sang secondary vô thức.

### 20.1. Có primary không đồng nghĩa read linearizable

Đọc `local` trên primary có thể nhìn một write chưa majority committed và sau này rollback. Đọc `majority` trên primary có thể chưa có real-time guarantee như `linearizable`.

### 20.2. Failover

Khi không có primary đang được driver nhận diện, read `primary` có thể chờ server selection rồi lỗi. Không nên tự “sửa” bằng `secondaryPreferred` nếu business không chấp nhận stale view.

### 20.3. Load

Đẩy toàn bộ reporting reads vào primary làm tăng contention với writes. Có thể tách analytical read path có SLA khác.

## 21. Read preference `primaryPreferred`: ưu tiên primary, có fallback

`primaryPreferred` thường chọn primary; khi primary không có, có thể dùng secondary phù hợp.

### 21.1. Lợi ích

Ứng dụng có thể tiếp tục đọc một số dữ liệu trong cửa sổ election/network disruption nếu secondary reachable.

### 21.2. Rủi ro

Một request vừa trước failover đọc primary mới hơn, request sau đó fallback secondary cũ hơn; ứng dụng có thể quan sát dữ liệu “đi lùi” nếu không có causal coordination.

### 21.3. Không dùng cho authorization quyết định nhạy

Nếu ứng dụng quyết định cấp quyền/giải ngân dựa trên state mà secondary có thể chậm, fallback silent có thể nguy hiểm.

### 21.4. Observability

Command monitoring/SDAM metrics nên cho biết lệnh thực sự chạy trên host nào và role nào, thay vì suy từ configured preference.

## 22. Read preference `secondary`: offload nhưng không fallback

Chỉ chọn các secondaries đáp ứng topology/tags/staleness selection. Nếu không tìm thấy server phù hợp trong timeout, thao tác đọc có thể thất bại.

### 22.1. Use cases

- Báo cáo hoặc export chịu được replication lag.
- Một số read-heavy workloads muốn bảo vệ primary.
- Batch phân tích có retry/backoff và freshness policy.

### 22.2. Không bắt buộc trả phiên bản mới nhất

`readConcern=majority` trên secondary tránh những dữ liệu chưa majority committed theo semantics, nhưng không buộc secondary bắt kịp một write mới nhất đã majority ack.

### 22.3. Max staleness và tags

Có thể lọc secondaries theo ước lượng staleness và tags, nhưng không có guarantee “không chậm hơn 2 giây” chỉ bằng việc đặt một con số nhỏ tùy ý. Driver/server có giới hạn tối thiểu và cách ước lượng riêng.

### 22.4. Test secondary thật

Một test dùng `secondary()` trên single-node replica set **không có secondary** sẽ lỗi; đó không phải bug read concern. Muốn kiểm tra secondary reads cần replica set nhiều data-bearing members.

## 23. Read preference `secondaryPreferred`: offload có fallback primary

Mặc định cố chọn secondary phù hợp; nếu không có secondary khả dụng, có thể chọn primary.

### 23.1. Phù hợp

- Dashboard/reporting ưu tiên offload.
- Chấp nhận primary fallback để giảm read failures.
- Không cần bảo đảm read luôn tránh primary.

### 23.2. Không phù hợp

- SLA yêu cầu **không** chạy heavy report trên primary.
- Kiểm thử khẳng định query phải chạy trên secondary.
- Data correctness yêu cầu một policy freshness rõ hơn là implicit fallback.

### 23.3. Tags có thể ảnh hưởng fallback

Khi cấu hình tag sets và server selection, cần xem rules cụ thể của driver/read preference; primary không mang tag selection giống secondary trong mọi mode. Đừng giả định tag cấu hình luôn được áp dụng cho fallback primary theo cùng cách.

## 24. Read preference `nearest`: độ trễ mạng, không phải thời gian ghi

`nearest` chọn member đủ điều kiện có latency đo được gần nhóm nhanh nhất theo driver selection, không nhất thiết primary, không nhất thiết geographic nearest hoặc most up-to-date.

### 24.1. Ví dụ

```text
P  RTT 20 ms
S1 RTT 7 ms
S2 RTT 8 ms

nearest may pick S1/S2
depending on tags/local threshold/selection state.
```

### 24.2. Freshness

`nearest` không quan tâm dữ liệu nào vừa được ghi nếu không có additional causal/consistency mechanism. Member có RTT thấp có thể lag dữ liệu.

### 24.3. Local threshold

Driver có cơ chế lựa chọn trong tập các servers có latency đủ gần server nhanh nhất. Thay đổi `localThresholdMS` không tự thay bảo đảm consistency.

### 24.4. Khi nào hợp lý?

Đọc event history/metadata ít nhạy freshness và phân tán nhiều regions, sau khi đã kiểm tra tags/freshness/tier policy; tránh cho payment state.

## 25. Max staleness: một bộ lọc lựa chọn secondary, không là consistency level

`maxStalenessSeconds` giới hạn ước lượng mức chậm của secondary so với các mốc mà driver xác định; nó giúp loại một số secondaries quá lag khỏi tập ứng viên.

### 25.1. Không phải read concern

`readConcern=majority` nói về majority-committed data. `maxStalenessSeconds` nói về **server selection**. Không thay nhau.

### 25.2. Không phải SLA độ mới tuyệt đối

Nếu mọi servers đều đã chậm so với nguồn external event, max staleness relative không chứng minh trả giá trị “không cũ hơn N giây wall clock”.

### 25.3. Có mức tối thiểu được hỗ trợ

MongoDB drivers áp ràng buộc `maxStalenessSeconds` (trong driver/versions hiện đại, mức tối thiểu thông thường là khoảng **90 giây**, trừ chế độ disabled). Không đặt `maxStalenessSeconds=2` rồi tưởng driver sẽ bảo đảm dữ liệu mới trong 2 giây.

### 25.4. Monitoring

Cần đo replication lag thực và read freshness end-to-end. Nếu ứng dụng đòi read-your-writes ở mốc cụ thể, dùng session/primary/causal protocol thay vì chỉ max staleness.

## 26. Read preference tag sets và topology placement

Replica set members có tags (ví dụ `region=apac`, `workload=reporting`) trong cấu hình.

```text
P:  region=apac, workload=oltp
S1: region=apac, workload=reporting
S2: region=eu,   workload=reporting
```

### 26.1. Use cases

- Ưu tiên secondaries ở khu vực gần application.
- Phân nhóm reporting nodes.
- Tránh một số data centers trong read workload.

### 26.2. Tag sets là một chuỗi ưu tiên

Driver hỗ trợ danh sách các tag sets được ưu tiên theo read preference specification. Nếu set đầu không có eligible member, driver có thể xét set tiếp theo tùy mode/điều kiện.

### 26.3. Tags không tự cưỡng chế data residency

Data residency/compliance yêu cầu kiểm tra storage placement, backups, logs, exports, failover, access control và quy định thực tế. Tag-based read routing đơn lẻ không tạo một boundary tuân thủ đầy đủ.

### 26.4. Đừng chọn tag theo user input

API client không nên được tự cung cấp arbitrary replica set tag để điều khiển data source. Chọn theo service policy đã được kiểm chứng.

## 27. Causal consistency: bảo đảm theo thứ tự hành động trong session

Causal consistency giúp những thao tác liên quan trong một session giữ các bảo đảm như:

- **Read-your-writes**: sau một write, read tiếp theo trong causal session nhìn thấy tác động đã ghi khi điều kiện được đáp ứng.
- **Monotonic reads**: không quan sát dữ liệu lùi về trước trong trình tự có tính nhân quả.
- **Monotonic writes**: thứ tự ghi liên quan được duy trì theo semantics.
- **Writes-follow-reads**: write theo sau read phản ánh quan hệ nhân quả tương ứng.

### 27.1. Điều kiện thông thường để có đầy đủ causal guarantees

Dùng **causally consistent sessions** với **`readConcern:"majority"`** và **`writeConcern:"majority"`**, và thực hiện operations trong session có **thứ tự** phù hợp.

### 27.2. Timeline

```text
Session S:
  1) write order.status="PAID" with w:majority
  2) read order from eligible member with readConcern majority
     and causal time tracking

Driver/server coordinate causal position:
  read should not silently return state prior to own
  successful majority write.
```

### 27.3. Vì sao đọc một secondary bình thường chưa đủ?

Nếu không có session/causal timing, driver chỉ biết secondary có thể trả majority data, nhưng không tự ràng buộc với cluster time của write trước đó do client thực hiện.

### 27.4. Không mặc định mọi thứ qua cùng user token là một MongoDB session

HTTP session/JWT không phải `ClientSession` MongoDB. Một request qua pod A và request tiếp theo qua pod B có thể dùng MongoClient/ClientSession khác. Nếu cần causal continuation xuyên requests, phải thiết kế giao thức truyền causal token/operation time theo cách driver và hệ thống hỗ trợ, không đưa raw client session objects vào JWT.

### 27.5. Session không thể truyền concurrent vô thức

Java `ClientSession` không nên dùng đồng thời trên nhiều threads nếu driver không hỗ trợ. Giữ operations tuần tự hoặc một session cho một transaction/công việc theo API.

## 28. Snapshot khác causal: hai mục đích

### 28.1. Snapshot

Muốn nhiều reads nhìn cùng một thời điểm logic:

```text
Report:
  totalAssets at snapshot T
  totalLiabilities at same snapshot T
```

### 28.2. Causal

Muốn read tiếp theo phản ánh write đã hoàn tất trước đó trong cùng causal chain:

```text
User changes address
Then checks profile
Read must not go backwards before own update
```

### 28.3. Khác linearizable

Linearizable là một real-time ordering guarantee mạnh cho single-document reads/writes phù hợp. Causal consistency tập trung vào quan hệ nhân quả của một chuỗi operations; không bắt buộc mọi client độc lập thấy toàn bộ writes theo real-time ordering.

### 28.4. Không “nâng” consistency bằng cách chọn nearest

`nearest`/secondary latency không bổ sung snapshot hay causal guarantees. Các layers phải được chọn riêng.

## 29. Transaction: lựa chọn concerns/preferences khác ngoài transaction

Trong multi-document transaction, concerns/preferences thường đặt qua **TransactionOptions** / session transaction configuration.

### 29.1. Read concern

`snapshot` thường được dùng khi nghiệp vụ cần transaction thấy một snapshot nhất quán. `local`/`majority` có semantics riêng; không lấy default ngoài transaction áp cho transaction mà không kiểm tra.

### 29.2. Write concern

Write concern gắn với **commit transaction**, không gắn riêng từng write operation trong transaction theo cách outside-transaction writes. Cần cấu hình write concern phù hợp ở transaction/session level.

### 29.3. Read preference

Transactions có yêu cầu đọc/ghi qua primary theo cấu hình được hỗ trợ. Không đặt `readPreference.secondary()` vào transaction rồi kỳ vọng MongoDB tự định tuyến toàn bộ transaction sang secondary.

### 29.4. Rủi ro callback retry

Driver transaction callback có thể được retry đối với một số transient failures. Không trực tiếp gửi email/charge payment bên trong callback nếu side effect đó không được bảo vệ bằng outbox/idempotency.

### 29.5. Long-running transaction

Snapshot history và locks/resources có chi phí. Đừng bọc một báo cáo 12 giờ vào một transaction khổng lồ.

## 30. Cơ chế read/write concern trên sharded cluster

```text
Java driver
     |
     v
   mongos
   /   \
  v     v
Shard A RS      Shard B RS
```

### 30.1. Mongos định tuyến

Shard key và query shape quyết định targeted vs scatter/gather. Read preference/read concern ảnh hưởng server selection/data view, nhưng không tự chữa query thiếu shard key.

### 30.2. Read concern `available`

Cần đặc biệt nhớ caveat về orphaned documents/chunk migration. Không dùng chỉ vì “chắc nhanh hơn”.

### 30.3. Majority và snapshot xuyên shards

Một aggregate trả dữ liệu nhiều shards có requirements nhất quán theo time riêng; `readConcern:"majority"` không luôn đồng nghĩa toàn bộ output là một **single point-in-time snapshot**. Khi cần consistent snapshot, dùng cơ chế `snapshot`/transaction được hỗ trợ.

### 30.4. Sharded transactions

Commit and write concern có điều kiện khác single shard, có thể tốn nhiều thời gian khi transaction chạm nhiều shards. Cần đo performance và transaction retry patterns.

### 30.5. Read preference không đảm bảo shard cùng replica member role

Với scatter query, mỗi shard có thể chọn member khác theo preference/tags. Không suy cả query “đọc một secondary duy nhất” trên một server.

### 30.6. Failover theo shard

Một shard mất primary không đồng nghĩa mongos hoàn toàn chết; các operations chạm shard đó có thể bị chậm/lỗi trong khi operations shard khác vẫn chạy.

## 31. Đặt concerns/preferences trong connection string

Ví dụ URI minh họa:

```text
mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/
  ?replicaSet=rsOrders
  &readPreference=primary
  &readConcernLevel=majority
  &w=majority
  &journal=true
  &wtimeoutMS=5000
```

Trong application config thực tế viết URI trên **một dòng** và encode secrets/tags đúng.

### 31.1. Ý nghĩa tham số

| Tham số | Loại | Ý nghĩa |
|---|---|---|
| `replicaSet` | Topology/SDAM | Chỉ định replica set name |
| `readPreference` | Server selection | Chọn role cho reads |
| `readConcernLevel` | Read concern | Mức đảm bảo read |
| `w` | Write concern | Số lượng/mode acknowledgment |
| `journal` | Write concern | Journal requirement |
| `wtimeoutMS` | Write concern | Timeout đợi acknowledgment |
| `maxStalenessSeconds` | Read preference | Loại secondaries theo staleness estimate |
| `readPreferenceTags` | Read preference | Server tags khi được hỗ trợ |

### 31.2. Không viết URI trực tiếp trong logs

URI có thể chứa username/password và thông tin hạ tầng. Redact credentials; không log full connection string trong production.

### 31.3. Không tự sửa advertised hostnames

Trong replica set, driver khám phá members qua `hello`; nếu hostnames trong replica set config không reachable từ ứng dụng, seed URI trông đúng vẫn có thể lỗi server selection. Điều này tách biệt concerns/preferences.

### 31.4. Option precedence

`MongoClientSettings` và URI có thể tương tác theo builder/config process. Dùng cấu hình tập trung, tránh viết conflicting values nhiều nơi rồi suy sai precedence.

## 32. Java Sync Driver: cấu hình mặc định ở MongoClient

Ví dụ minh họa cho driver hiện đại:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

public final class ConcernClient471 {

    public static MongoClient create(String uri) {
        WriteConcern acknowledgedMajority =
            WriteConcern.MAJORITY
                .withJournal(true)
                .withWTimeout(5, TimeUnit.SECONDS);

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .readPreference(ReadPreference.primary())
            .readConcern(ReadConcern.MAJORITY)
            .writeConcern(acknowledgedMajority)
            .build();

        return MongoClients.create(settings);
    }
}
```

### 32.1. Cấu hình trên client có tác động rộng

Các collections/databases lấy từ client có thể kế thừa default settings, trừ khi override ở cấp phù hợp. Không áp `linearizable` cho toàn bộ client chỉ vì một endpoint lock check cần.

### 32.2. `MongoClient` dùng lâu dài

Thường tạo một `MongoClient` cho mỗi cụm connection configuration và dùng chung pools; không tạo một MongoClient mới chỉ để chạy một query bằng `secondary`.

### 32.3. Đặt write concern majority vì ý nghĩa business

`w:"majority"` có thể là lựa chọn hợp lý với orders/payments, nhưng nếu server không có đủ data-bearing majority hoặc workload không chịu được latency, cần xử lý vấn đề topology/SLA thay vì âm thầm hạ yêu cầu.

### 32.4. Tài liệu và version

Imports/class names ở đây theo Java Sync Driver 5.x. Dự án dùng phiên bản khác cần đối chiếu đúng API/dependency; không tự assume cùng import cho mọi driver generations.

## 33. Java Sync Driver: override ở database/collection

Có thể tạo các handles với settings riêng:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

MongoDatabase db = client.getDatabase("consistency_lab_471");

MongoCollection<Document> criticalOrders =
    db.getCollection("orders")
      .withReadPreference(ReadPreference.primary())
      .withReadConcern(ReadConcern.MAJORITY)
      .withWriteConcern(WriteConcern.MAJORITY);

MongoCollection<Document> reportingOrders =
    db.getCollection("orders")
      .withReadPreference(ReadPreference.secondaryPreferred())
      .withReadConcern(ReadConcern.MAJORITY);
```

### 33.1. Hai handles, một namespace

Cả hai biến truy cập cùng collection `orders`, chỉ khác các option ở phía driver. Không tạo dữ liệu bản sao nào chỉ vì gọi `withReadPreference`.

### 33.2. Đọc báo cáo

```java
import static com.mongodb.client.model.Filters.eq;

var reports = reportingOrders
    .find(eq("status", "PAID"))
    .maxTime(5, java.util.concurrent.TimeUnit.SECONDS)
    .limit(100);

for (Document order : reports) {
    System.out.println(order.getString("status"));
}
```

Khi dùng `secondaryPreferred`, driver có thể fallback primary. Không coi `reportingOrders` là bằng chứng mọi lệnh đọc luôn ở secondary.

### 33.3. Không truyền raw business updates không idempotent

`withWriteConcern(MAJORITY)` không bảo vệ khỏi việc API tự gọi `$inc` hai lần. Application cần request id, transaction/policy và unique indexes.

## 34. Java Sync Driver: dùng `linearizable` cho một document

Ví dụ lấy một key trạng thái của hệ thống:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;

MongoCollection<Document> lockState =
    client.getDatabase("consistency_lab_471")
        .getCollection("locks")
        .withReadConcern(ReadConcern.LINEARIZABLE)
        .withReadPreference(ReadPreference.primary());

Document lock = lockState
    .find(eq("_id", "leader-lock:billing"))
    .maxTime(3, java.util.concurrent.TimeUnit.SECONDS)
    .first();
```

### 34.1. Single-document semantics

Filter `_id` là một single-document lookup được hỗ trợ theo design của ví dụ. Không áp dụng `linearizable` bừa cho toàn aggregation/pagination.

### 34.2. Write side

Nếu linearizable read phải quan sát một số trạng thái đã hoàn tất, writes liên quan cần `w:"majority"` và protocol điều khiển đồng bộ rõ.

### 34.3. Cần timeout

Nếu primary không xác minh được majority/current leadership, linearizable read có thể block. `maxTime` giúp client tránh treo vô hạn, rồi xử lý lỗi theo policy.

### 34.4. Read-check-write race

Ngay cả read linearizable thành công, một writer khác có thể đổi lock ngay sau đó. Muốn cập nhật phải dùng `findOneAndUpdate`/conditional update/transaction và fencing token để kiểm soát race.

## 35. Java Sync Driver: causal session

Đoạn test tạo và đọc tài liệu trong **cùng một causally consistent session**:

```java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.ObjectId;

import static com.mongodb.client.model.Filters.eq;

MongoCollection<Document> orders =
    client.getDatabase("consistency_lab_471")
        .getCollection("orders")
        .withReadConcern(ReadConcern.MAJORITY)
        .withWriteConcern(WriteConcern.MAJORITY)
        .withReadPreference(ReadPreference.secondaryPreferred());

ObjectId id = new ObjectId();

ClientSessionOptions options = ClientSessionOptions.builder()
    .causallyConsistent(true)
    .build();

try (ClientSession session = client.startSession(options)) {
    orders.insertOne(session,
        new Document("_id", id)
            .append("status", "CREATED")
            .append("amountMinor", 100000L));

    Document found = orders
        .find(session, eq("_id", id))
        .maxTime(5, java.util.concurrent.TimeUnit.SECONDS)
        .first();

    if (found == null) {
        throw new IllegalStateException("Expected own write");
    }
}
```

### 35.1. Session mang theo causal metadata

Driver theo dõi cluster/operation time tương ứng, phối hợp với server để reads sau không đứng trước operations đã biết trong causal chain. Đây là reason dùng explicit session.

### 35.2. Chọn secondaryPreferred không có nghĩa luôn secondary

Nếu replica set chỉ có một node hoặc không có eligible secondary, driver có thể đọc primary. Để chứng minh read-your-writes **qua secondary** thật, cần multi-node replica set và instrument server selection.

### 35.3. Majority cần đặt trên cả hai phía

Để đạt các causal guarantees chính thức đầy đủ, operations phải được cấu hình readConcern majority và writeConcern majority theo quy tắc; không chỉ bật `causallyConsistent(true)` rồi để writes `w:1`.

### 35.4. Đừng chạy song song trên session

Đoạn trên tuần tự. Không truyền cùng session cho 20 tasks đồng thời khi API không hỗ trợ thread safety.

## 36. Java Sync Driver: transaction với snapshot

Ví dụ đọc và cập nhật hai account documents trong một transaction:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.inc;

MongoCollection<Document> accounts =
    client.getDatabase("consistency_lab_471")
        .getCollection("accounts");

TransactionOptions txOptions = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();

try (ClientSession session = client.startSession()) {
    session.startTransaction(txOptions);
    try {
        accounts.updateOne(session,
            eq("_id", "A"),
            inc("balanceMinor", -30000L));
        accounts.updateOne(session,
            eq("_id", "B"),
            inc("balanceMinor", 30000L));

        // Production: validate matchedCount and funds constraints.
        session.commitTransaction();
    } catch (RuntimeException ex) {
        try {
            session.abortTransaction();
        } catch (RuntimeException abortError) {
            ex.addSuppressed(abortError);
        }
        throw ex;
    }
}
```

### 36.1. Ví dụ chưa là payment engine

Nó minh họa concerns/preferences trên transaction, không giải quyết overdraft, idempotency, unknown commit result, transient transaction error, business ledger hay audit/outbox.

### 36.2. Không đặt `w` trên từng operation trong transaction

MongoDB transaction write concern được xử lý ở transaction commit. Nếu service có nhiều collection handles với write concern riêng, phải hiểu transaction options override/semantics, không giả định mỗi `updateOne` bên trong transaction tự majority-acknowledged riêng rẽ.

### 36.3. Không retry transaction body tùy tiện

Transaction body có thể được chạy lại khi transient error và đúng API giúp retry theo labels; phải ngăn side effects ngoài MongoDB trùng và giới hạn retry budget.

### 36.4. Snapshot không giải quyết write skew mà không có guard

Transactions có snapshot isolation semantics, không tự suy mọi invariants đa-document được serialize hoàn toàn. Nếu hai transactions đọc chung một điều kiện và ghi khác documents, cần đánh giá write skew/constraint design.

## 37. mongosh: chạy read với read concern tường minh

Trong database lab:

```javascript
use consistency_lab_471;

db.runCommand({
  find: "orders",
  filter: {
    status: "PAID"
  },
  limit: 10,
  readConcern: {
    level: "majority"
  },
  maxTimeMS: 5000
});
```

### 37.1. Read concern gắn trên read command

Ví dụ trên không tự chọn secondary; read preference là một chính sách riêng của client/server selection.

### 37.2. Dùng database thử nghiệm

Không thực hiện dữ liệu ghi nguy hiểm trên production chỉ để minh họa. Với lệnh `find`, vẫn cần query scope, index và giới hạn results để tránh scan lớn.

### 37.3. Kết quả trả cursor

Raw `find` command trả cursor document/result structure; `getMore` có quy tắc cursor/lifecycle tương ứng. Đừng in toàn bộ dữ liệu nhạy cảm lên terminal.

## 38. mongosh: ghi với write concern tường minh

```javascript
use consistency_lab_471;

db.runCommand({
  insert: "orders",
  documents: [
    {
      _id: "req-471-001",
      status: "CREATED",
      amountMinor: NumberLong("350000")
    }
  ],
  ordered: true,
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 5000
  }
});
```

### 38.1. Các trường

- `w`: acknowledgment mode.
- `j`: journal acknowledgment option nếu deployment hỗ trợ.
- `wtimeout`: milliseconds đợi write concern, không hủy write.

### 38.2. Upsert/retry

Lặp insert cùng `_id` có thể gặp duplicate key. Đó không tự là lỗi production nếu request ID cũ đã thành công, nhưng ứng dụng phải xác minh payload/ownership trước khi coi là idempotent success.

### 38.3. Result có thể bao gồm writeConcernError

Không chỉ nhìn số documents inserted: inspect command result/error path và kiểm tra outcome theo business policy khi có uncertainty.

## 39. mongosh: đặt read preference

Trong interactive shell, có thể cấu hình read preference cho connection theo API shell tương ứng:

```javascript
db.getMongo().setReadPref("secondary");

// Query này sẽ theo read preference của connection:
db.orders.find({ status: "PAID" }).limit(10).toArray();

// Khi muốn quay lại primary:
db.getMongo().setReadPref("primary");
```

### 39.1. Không đồng nghĩa readConcern

`setReadPref("secondary")` chỉ chọn member; nếu không đặt read concern, lệnh không tự có majority guarantee.

### 39.2. Test trên nhiều member

Nếu chỉ có một-node replica set, `secondary` thường không tìm được eligible server. Đừng coi đó là bằng chứng read preference cấu hình sai.

### 39.3. Quyền/commands

Một số admin commands hoặc transaction operations có primary requirements bất kể đọc thông thường; driver/server có thể từ chối secondary readPreference cho những lệnh đó.

### 39.4. Shell APIs thay đổi

`mongosh` và legacy `mongo` shell có khác biệt. Khi viết script production, kiểm tra options theo phiên bản shell chính thức, tránh dùng legacy `rs.slaveOk()` hay `slaveOk()`.

## 40. Bảng so sánh “majority” khi nằm ở hai phía

| Trường hợp | Tác động | Không đủ cho |
|---|---|---|
| `writeConcern:majority` | Write được majority ack theo topology | Đảm bảo mọi secondary đọc tức thì |
| `readConcern:majority` | Chỉ đọc majority-committed data | Đảm bảo chính là latest write |
| Cả hai, **không** causal session | Tăng tính bền/stable read | Read-your-writes trên mọi secondary |
| Cả hai, **có** causally consistent session | Thêm causal order khi thực hiện đúng | Real-time linearizability của mọi client |
| `readConcern:linearizable` + majority writes | Single-document real-time semantics theo điều kiện | Multi-document snapshot/atomicity |
| `readConcern:snapshot` trong transaction + majority commit | Consistent transaction snapshot và commit durability tương ứng | Thời gian thực của mọi lệnh độc lập |

### 40.1. Một câu hỏi thử

> Ghi đơn hàng với `w:majority`, sau đó ở request khác không dùng session đọc secondary với `readConcern:majority`. Có bắt buộc thấy đơn vừa ghi không?

**Không.** Secondary có thể lag và lệnh không có causal context ràng buộc điểm đọc với operation time của write.

### 40.2. Muốn đơn giản và mới hơn?

Với cùng một service khi cần read-after-write ngay, đọc primary có thể là lựa chọn thực dụng; nếu yêu cầu guarantee mạnh xuyên failover/clients, xác định rõ có cần causal session hay linearizable read và điều kiện tương ứng.

## 41. Bảng “có thể bị rollback”, “có thể stale”, “có thể timeout”

| Cấu hình | Có thể quan sát write chưa majority? | Có thể stale do secondary? | Có thể đợi majority? |
|---|---|---|---|
| `local + primary` | Có | Không do secondary, nhưng có race/failover | Không do majority-read requirement |
| `local + secondary` | Có | Có | Không do majority-read requirement |
| `majority + primary` | Không theo majority semantics | Có thể không là newest nếu commit point/lag | Có |
| `majority + secondary` | Không theo majority semantics | **Có** | Có |
| `linearizable + primary` | Không theo điều kiện supported | Bảo đảm real-time single-doc với majority writes | **Có thể đáng kể** |
| `snapshot + transaction primary` | Theo snapshot/commit semantics | Snapshot không mặc định current | Có thể |

### 41.1. Dùng bảng cẩn thận

“Không” trong bảng có nghĩa **không do cơ chế nêu ở cột**, không phải bảo đảm toàn hệ thống không có thay đổi concurrent, không có lỗi hay không bị mất điện toàn cụm.

### 41.2. Stale vẫn có thể chấp nhận

Một báo cáo cuối ngày có thể chỉ cần dữ liệu tới 23:59 hôm qua. Dùng snapshot/secondary có thể phù hợp hơn việc buộc xem latest state của tất cả operations trong thời gian thực.

## 42. Phân biệt read preference với consistency contract

Hai API:

```text
GET /catalog/products
GET /wallet/balance
```

### 42.1. Product catalog

Tối ưu throughput/latency, chấp nhận một update giá chưa xuất hiện ngay ở secondary theo business policy. Có thể dùng `secondaryPreferred` với readConcern `local`/`majority` dựa trên rủi ro và cách hiển thị.

**Nhưng:** nếu hiển thị giá để thanh toán, backend checkout phải xác thực giá authoritative; không tin catalog cache như nguồn chốt thanh toán.

### 42.2. Wallet balance

Đọc số dư trước authorize một khoản thanh toán cần transaction/invariant design, không chỉ readConcern. Có thể dùng primary + majority writes và atomic conditional update/ledger.

### 42.3. Không copy cấu hình cho mọi collection

Cùng một MongoDB cluster có thể lưu cả catalog và ledger; ứng dụng nên tách repository handles/service policies thay vì một global read preference mạnh/yếu cho tất cả.

## 43. Decision flow: ưu tiên business correctness trước performance

```text
Đây là WRITE?
    |
    +-- Yes --> Write cần sống qua normal failover?
    |              |
    |              +-- Yes --> w:majority (và journaling policy)
    |              |
    |              +-- No  --> w:1 may be acceptable
    |                         (document risk/compensation)
    |
    +-- No --> Đây là READ
                  |
                  +-- Phải thấy real-time completed
                  |   single-doc majority write?
                  |         -> linearizable + primary
                  |
                  +-- Phải thấy một snapshot nhất quán?
                  |         -> snapshot transaction / supported read
                  |
                  +-- Phải tránh uncommitted-to-majority state?
                  |         -> majority
                  |
                  +-- Có thể chịu rollback/stale?
                            -> local where suitable

Với mọi READ:
  Chọn preference riêng:
    primary (freshness/consistency path)
    secondary/nearest (offload/lag accepted)
  Nếu cần causal order:
    session + majority read/write
```

**Đây là flow sơ bộ.** Không có một lựa chọn read concern tự thay cho unique constraints, transactions, idempotency hoặc business reconciliation.

## 44. Kịch bản A — Tạo order và đọc lại ngay

### 44.1. Yêu cầu

Client gửi:

```text
POST /orders requestId=req-471-a
GET  /orders/order-471-a
```

Sau khi POST trả thành công, người dùng muốn nhìn thấy order.

### 44.2. Lựa chọn

- POST: `writeConcern=majority` nếu business đòi write không rollback theo normal failover.
- GET ngay: `readPreference=primary` là lựa chọn đơn giản hơn secondary.
- Nếu GET có thể qua secondary hoặc khác service/request: thiết kế causal continuation/causal session ở nơi cần.
- Data access dùng unique requestId/`_id` để retry an toàn.

### 44.3. Nếu chọn secondaryPreferred?

Tùy topology, GET có thể đọc secondary chưa bắt kịp. Người dùng vừa tạo order nhưng UI báo 404. Đó là **stale read**, không nhất thiết write fail.

### 44.4. Không tự sửa bằng retry vô hạn

Nếu API yêu cầu read-your-writes, quy định route/quy tắc causal ngay từ đầu. Bọc GET polling vô hạn chỉ che vấn đề consistency contract và có thể làm xấu latency.

## 45. Kịch bản B — Chuyển tiền giữa hai tài khoản

### 45.1. Yêu cầu

```text
Before:
  A.balance = 100000
  B.balance = 40000

Transfer:
  A -> B: 30000

After:
  A.balance = 70000
  B.balance = 70000
```

### 45.2. Cấu hình nền

- Multi-document transaction nếu hai account documents phải thay đổi atomically.
- `readConcern=snapshot` cho transaction nếu cần view nhất quán.
- `writeConcern=majority` ở **transaction commit** để bảo vệ durability theo policy.
- `readPreference=primary` trong transaction.
- Unique business transaction ID và ledger/audit/outbox để retry không double transfer.

### 45.3. Vì sao chỉ `majority` không đủ?

Hai `updateOne` riêng với `w:majority` vẫn có thể tạo trạng thái nửa chuyển tiền nếu process crash giữa hai lệnh. Majority không biến chúng thành atomic unit.

### 45.4. Vì sao chỉ snapshot không đủ?

Snapshot cung cấp nhất quán dữ liệu đọc trong transaction; vẫn cần kiểm tra số dư, concurrency conflicts, commit, idempotency và xử lý unknown outcome.

## 46. Kịch bản C — Đọc khóa điều phối leader

### 46.1. Yêu cầu

Một scheduler cần xác định lock holder và tránh hai workers cùng thực hiện job quan trọng.

### 46.2. Lựa chọn

- Single-document state lưu `owner`, `leaseEpoch`, `leaseUntil`.
- Majority-acknowledged updates cho lock.
- Primary + linearizable read khi cần quyết định phụ thuộc real-time completed writes.
- Atomic conditional update / `findOneAndUpdate` để claim/renew.
- Fencing token `leaseEpoch` để ngăn worker cũ gửi side effects.

### 46.3. Tại sao read concern không thay CAS?

```text
Worker A reads: lock free
Worker B reads: lock free
Worker A tries claim
Worker B tries claim
```

Nếu hai operations chỉ là read rồi blind write, ngay cả linearizable reads cũng không đảm bảo chỉ một worker claim. **Atomic conditional write** là cơ chế chặn race.

### 46.4. Timeout

Linearizable read phải có `maxTimeMS` và operation timeout tương ứng; khi không thể xác nhận state, worker nên fail closed/standby, không tự lấy lock vì “đọc chậm”.

## 47. Kịch bản D — Product catalog và reporting

### 47.1. Khác biệt business

Trang catalog có thể chịu một vài giây replication lag theo SLA. Báo cáo doanh số cuối tháng muốn dữ liệu trong một phạm vi thời điểm nhất quán.

### 47.2. Catalog

Ứng viên: `readPreference=secondaryPreferred`, `readConcern=local` hoặc `majority` tùy rủi ro rollback. Cache TTL và invalidation vẫn quyết định freshness mà client nhìn thấy.

### 47.3. Report

Nếu report chỉ là aggregation đơn lẻ và không yêu cầu đối chiếu nhiều lần đọc, `majority` có thể đủ để tránh uncommitted-to-majority state, nhưng không tạo same-time snapshot cho chuỗi operations.

Nếu nhiều reads/collections phải cùng một snapshot logic, dùng `snapshot` theo APIs hỗ trợ và giới hạn duration/resource.

### 47.4. Không đẩy heavy reports lên primary khi thiếu đánh giá

Read preference primary cho mọi report có thể tăng p99 write latency do contention. Cân bằng SLO, index/aggregation, secondary resources và consistency nhu cầu.

## 48. Kịch bản E — Audit log và regulatory reporting

### 48.1. Câu hỏi cần trả lời

Audit log có là source-of-truth không? Có được phép mất một event sau failover không? Có cần hash chain hoặc tamper-evident storage? Retention/backup bao lâu?

### 48.2. Gợi ý

- Writes: majority acknowledgment, journaling policy và idempotent event IDs.
- Reads nhạy: majority hoặc snapshot tùy báo cáo.
- Immutable/audit-only application permissions.
- Backup/PITR, retention, access audit và đối soát external systems.

### 48.3. Write concern không tạo immutability

Một user có quyền delete vẫn có thể xóa audit documents. Bảo vệ cần RBAC, write authorization, storage retention và operational controls riêng.

### 48.4. Change streams không là archival audit log vô hạn

Resume token cần lịch sử oplog đủ; nếu consumer bị offline vượt oplog window, có thể mất khả năng resume. Cần durable outbox/event store theo yêu cầu nghiệp vụ.

## 49. Kịch bản F — API đang mất primary

### 49.1. Timeline

```text
T0 P healthy, S1/S2 healthy
T1 P unavailable
T2 election in progress: no primary
T3 S1 elected new P
T4 driver detects new topology
```

### 49.2. Với `readPreference=primary`

Reads có thể block trong server selection hoặc trả lỗi trong cửa sổ không có primary; sau election có thể phục hồi.

### 49.3. Với `primaryPreferred`

Một số reads có thể fallback secondary khi không có primary, chấp nhận khả năng stale. Không áp cho những quyết định cần trạng thái mới nhất.

### 49.4. Với writes `w:majority`

Trong khi không có primary hoặc đủ majority, writes có thể chờ/lỗi. Sau election, retry semantics phải xử lý uncertain outcomes.

### 49.5. Không “fix” bằng `w:1` tự động

Khi outage, hạ write concern có thể làm hệ thống trả success cho writes dễ rollback. Đây là thay đổi business durability SLA, không là một toggling vô hại.

## 50. Kịch bản G — Secondary lag 30 giây

Giả sử:

```text
P  latest order revision = 18
S1 latest order revision = 17 (lag 30s)
S2 latest order revision = 18
```

### 50.1. `readPreference=secondary`

Driver có thể chọn S1 hoặc S2 theo eligibility/tags/latency. Nếu S1 được chọn, read có thể thấy rev17.

### 50.2. Thêm `readConcern=majority`

Không bắt S1 trả rev18 chỉ vì rev18 đã majority committed ở P/S2. Nếu S1 chưa apply, nó không thể trả state đó ngay.

### 50.3. Thêm `maxStalenessSeconds`

Driver có thể loại một số secondary quá chậm dựa trên staleness estimate và ràng buộc version. Đây không phải exact guarantee mới nhất.

### 50.4. Causal session

Nếu client vừa ghi rev18 và cần đọc kết quả trong cùng causal chain, dùng majority writes/reads và session. Read có thể phải chờ S1 bắt kịp hoặc chọn member phù hợp.

### 50.5. Business fallback

Nếu SLA freshness bắt buộc thấp hơn mức khả năng staleness filtering, thường chọn primary hoặc một materialized view/CDC với explicit lag gate thay vì cố đặt `maxStalenessSeconds=1`.

## 51. Kịch bản H — BI dashboard dùng `nearest`

### 51.1. Yêu cầu

Người dùng ở nhiều vùng xem biểu đồ tổng hợp. Dashboard chấp nhận delayed data.

### 51.2. Cấu hình ứng viên

- `readPreference=nearest` và tags có chủ đích.
- `readConcern=majority` nếu chỉ muốn committed values.
- Caching, indexed/materialized reports.
- Dashboard hiển thị `dataAsOf` hoặc lag indicator nếu hợp lý.

### 51.3. Không dùng `nearest` để giấu freshness lag

Một chart “doanh số theo phút” mà người dùng cần quyết định realtime nên công khai staleness/refresh budget. Độ trễ mạng thấp không chứng minh dữ liệu mới.

### 51.4. Không mặc định nearest cùng region

Driver lựa chọn dựa trên latency measurements và tags; network topology có thể khác vị trí địa lý. Nếu data residency quan trọng, thiết kế storage/placement policy riêng.

## 52. Kịch bản I — Change stream event và committed writes

### 52.1. Mục tiêu

Consumer theo dõi `orders` và gửi email sau khi trạng thái đổi `PAID`.

### 52.2. Cần hiểu

Change streams hoạt động trên replica set/sharded topology được hỗ trợ; stream events phản ánh những thay đổi đáp ứng semantics liên quan majority commit/oplog. Không phải mỗi write `w:1` mà primary trả ack là một event bền vững không thể mất.

### 52.3. Không phụ thuộc chỉ vào read concern

Consumer cần:

- Resume token bền vững.
- Xử lý idempotent.
- Không checkpoint token trước side effect khi không có atomicity.
- Oplog history window đủ hoặc recovery khi history lost.
- Outbox nếu cần đảm bảo giao email/external side effects.

### 52.4. Khi write ack unknown

Một client có thể nhận write timeout nhưng event sau đó vẫn xuất hiện vì write cuối cùng đã commit. Idempotent consumer và request identity là bắt buộc nếu không muốn hai emails.

## 53. Kịch bản J — Đọc dữ liệu thời điểm T0 để đối soát

### 53.1. Mục tiêu

Đối chiếu balance ledger và account snapshots tại cùng một thời điểm, không muốn đọc ledger sau transaction A nhưng account trước transaction A.

### 53.2. Vì sao majority riêng lẻ chưa đủ?

Hai reads `majority` độc lập có thể xảy ra ở **hai thời điểm majority-committed khác nhau**.

### 53.3. Chọn snapshot phù hợp

Một transaction với readConcern snapshot có thể lấy consistent snapshot xuyên các reads trong phạm vi được hỗ trợ. Với workloads rất lớn có thể cần snapshot reads và pagination/CDC architecture khác để tránh long transactions.

### 53.4. Quan sát snapshot timestamp

Phải định nghĩa rõ “as-of” là cluster logical time, business cutoff hay wall-clock của ứng dụng. Chúng không luôn đồng nhất.

### 53.5. Không quét 500 triệu documents trong một transaction

Với báo cáo rất lớn, giữ transaction lâu có thể gây áp lực snapshot history. Thiết kế batch consistent snapshots/historical materialization hoặc analytical pipeline riêng với trade-offs đã được xác nhận.

## 54. Kịch bản K — Search và cache

### 54.1. MongoDB read concern không ràng buộc cache

Nếu service đọc từ Redis cache hoặc Atlas Search index, consistency của MongoDB document không tự lan sang cache/search. Một read `linearizable` từ MongoDB có thể không được gọi nếu cache hit.

### 54.2. Cần consistency contract end-to-end

- Business critical reads: bypass/validate cache hoặc dùng version guard.
- Secondary search: chấp nhận indexing lag với `dataAsOf`/version.
- Checkout: validate authoritative current state trước commit.

### 54.3. Không hứa read-your-writes chỉ dựa vào `w:majority`

Nếu read path qua cache không invalidated hoặc search chưa reindex, người dùng vẫn thấy dữ liệu cũ. Định nghĩa contract phải bao gồm data sinks ngoài MongoDB.

## 55. Kịch bản L — Config/feature flag

### 55.1. Mục tiêu

Ứng dụng đọc feature flag bật/tắt quyền chuyển tiền hoặc emergency stop.

### 55.2. Phân loại

- Flag thông thường có thể chấp nhận propagation delay.
- Emergency kill switch có thể cần strong reads/centralized policy.
- Nếu flag được dùng làm authorization, hãy xem như dữ liệu security-sensitive.

### 55.3. Lựa chọn

Primary và majority writes, có thể linearizable read cho một single-document state nếu real-time ordering là requirement. Tuy nhiên caching/refresh interval cũng phải theo cùng contract.

### 55.4. Availability trade-off

Trong partition, fail closed (tạm từ chối action) có thể đúng hơn trả stale “enabled” rồi gây rủi ro. Quyết định thuộc business/security policy.

## 56. Sai lầm phổ biến: “mạnh hơn” luôn tốt hơn

Một số cặp đánh đổi:

```text
Higher consistency:
  may require waiting, lower availability in partitions

Stronger write acknowledgment:
  may increase latency or fail when majority unavailable

Read offloading to secondary:
  may increase apparent data staleness

Long snapshots:
  may retain history and consume resources
```

### 56.1. Đừng tối ưu trên giấy

Benchmark trên topology, network, journal/storage engine và workload thực; độ trễ majority và read preference phụ thuộc nhiều yếu tố.

### 56.2. Contract có thể khác theo endpoint

`POST /payments` cần khác `GET /catalog`. Không dùng một global switch cho tất cả khi nghiệp vụ có yêu cầu khác nhau.

### 56.3. Không chọn `local` chỉ để “hết timeout”

Nếu nguyên nhân là primary failover hoặc majority health, hạ read concern không luôn giải quyết server selection hoặc may return potentially rolled-back data.

### 56.4. Đổi write concern cần change review

Thay `w:majority` bằng `w:1` là thay đổi durability guarantee. Phải có owner/business approval, không là một performance tweak thuần túy.

## 57. Kiểm tra cấu hình thực tế đang dùng

### 57.1. Ở application

Log/config snapshot không chứa secrets:

```text
service=orders-api
clusterAlias=mongo-orders-prod
driverVersion=...
readPreference=primary
readConcern=majority
writeConcern=majority
journal=true
writeConcernTimeoutMs=5000
```

### 57.2. Ở MongoDB

Với quyền quản trị phù hợp, xem replica set topology/status và cluster default concerns:

```javascript
rs.status();
rs.conf();
db.adminCommand({ getDefaultRWConcern: 1 });
```

Một số commands yêu cầu deployment/version/privileges tương ứng. Không chạy `rs.reconfig`, `setDefaultRWConcern` hoặc thay votes chỉ để đọc trạng thái.

### 57.3. Không chỉ dựa vào URI

Application có thể override ở collection/transaction. Server-side default concerns có thể khác. Muốn xác định một operation thật dùng gì, kiểm tra client config path và command instrumentation phù hợp.

### 57.4. Read preference thực tế

Command monitoring cùng SDAM topology events giúp thấy host nhận read command; không ghi full BSON request/response chứa PII.

## 58. Metrics khi chọn concerns/preferences

| Metric | Vì sao cần |
|---|---|
| MongoDB command p50/p95/p99 latency | Đo read/write real latency |
| Server selection timeouts | Không có eligible server, primary election, tags sai |
| Pool checkout wait | Connection pool saturation |
| Primary and secondary CPU/IO | Kiểm tra offload đúng mục tiêu |
| Replication lag per secondary | Read staleness và majority write latency |
| Majority commit point progress | Majority read/write health |
| Journal latency/I/O | `j:true` và durability cost |
| Write concern errors/timeouts | Majority không đạt trong budget |
| Retryable write/transaction retry counts | Network/election pressure |
| Change stream consumer lag | Phụ thuộc oplog/history và event processing |
| Oplog window | Khả năng resume, catch-up |
| Read routing role/host distribution | Xác nhận preference theo actual selection |
| Business stale-read incidents | Kết quả thực quan trọng hơn config name |

### 58.1. Histogram

`p99` latency cần đo ở application endpoint và MongoDB commands. Một read concern majority có thể tăng command latency trong failover, nhưng request retries/cache có thể làm user latency khác.

### 58.2. Labels an toàn

Gắn service, command, read preference, read concern, write concern class, error family, cluster alias. Tránh raw connection URI, user ID, document ID, tenantId cardinality quá cao, query payload.

### 58.3. Không coi success rate 100% là đúng dữ liệu

Một service đọc secondary và trả HTTP 200 có thể vẫn trả stale data. Đo domain-specific freshness/invariant, không chỉ HTTP statuses.

## 59. Preflight khi đổi read/write policy

Trước khi rollout một thay đổi, ghi lại:

1. **Business invariant**: read mới nhất? không rollback? snapshot? availability priority?
2. **Endpoint scope**: những APIs/jobs/tenants nào chịu tác động?
3. **Server topology**: votes, arbiters, secondaries, replication lag, regions.
4. **Current defaults**: explicit client/database/collection/transaction settings và server default RW concern.
5. **Version support**: readConcern level hợp lệ với command/storage engine.
6. **Timeout**: server selection, maxTimeMS, socket, write concern timeouts, retry budget.
7. **Latency baseline**: p95/p99 read/write theo workload.
8. **Failure model**: primary election, majority unavailable, one-secondary lag.
9. **Rollback plan**: hiểu policy thay đổi trước khi đảo về config cũ.
10. **Monitoring**: command, journal, commit point, business stale reads.

### 59.1. Mỗi policy phải có owner

Nếu team Platform đổi cluster defaults nhưng service Payments kỳ vọng `w:majority`, thay đổi có thể ảnh hưởng nghiệp vụ. Đặt write concern explicit ở code critical, có config registry/owner và runtime verification.

### 59.2. Chạy canary

Đổi cấu hình trên một tập service/tenant được phê duyệt, so p99 latency, error rate, replication pressure và business invariants trước khi mở rộng.

### 59.3. Do not downgrade silently

Nếu áp SLA mới gây timeout, điều tra nguyên nhân và có quyết định business; không âm thầm fallback `w:1` hay `local` trong retry handler khi error xảy ra.

## 60. Runbook 1 — Write trả write concern timeout

### Dấu hiệu

```text
insertOne/updateOne reached MongoDB
writeConcern: majority
error: write concern could not be satisfied within timeout
```

### Điều cần biết ngay

**Write có thể đã áp dụng.** Đây không phải bằng chứng write bị rollback hoặc chưa chạy.

### Cách xử lý

1. Ghi lại `requestId`/business identity an toàn.
2. Kiểm tra primary/majority/replication lag và write concern metrics.
3. Không gửi lại một non-idempotent effect với ID mới.
4. Truy vấn trạng thái theo key do business kiểm soát và read concern thích hợp.
5. Nếu trạng thái chưa rõ, retry bằng cùng identity/idempotent protocol hoặc xử lý reconciliation.
6. Điều tra hạ tầng: majority members, replication lag, journal, network.
7. Ghi incident evidence và test failover/retry regression.

### Không làm

Không mặc định `wtimeout` làm server hủy write. Không tự hạ `w:"majority"` xuống `w:1` để tránh lỗi nếu business chưa chấp thuận.

## 61. Runbook 2 — Đọc secondary không thấy order vừa tạo

### Dấu hiệu

```text
POST /orders -> 201
GET  /orders/{id} -> 404
readPreference: secondaryPreferred
```

### Khả năng

- Secondary bị replication lag.
- Client/session không có causal context.
- GET đọc cache cũ.
- Query thiếu/sai tenant filter.
- Order đã rollback nếu write ack chưa đủ và failover xảy ra.

### Cách xử lý

1. Xác định write concern của POST và outcome chính xác.
2. Kiểm tra server/role thực hiện GET, có dùng secondary không.
3. Đọc primary theo policy để phân biệt stale secondary với dữ liệu thực sự thiếu.
4. Kiểm tra session/causal requirement.
5. Kiểm tra cache invalidation và search/materialized view.
6. Sửa endpoint contract: primary read hoặc causal session nếu phải thấy own write.

### Không làm

Không kết luận “MongoDB mất dữ liệu” chỉ vì secondary trả 404; cũng không kết luận “chỉ lag” mà bỏ qua possibility write rollback/authorization/cache issue.

## 62. Runbook 3 — `linearizable` read treo khi partition

### Dấu hiệu

Một single-document read với `readConcern:linearizable` bị chậm và cuối cùng timeout, trong khi một số reads `local` có thể trả dữ liệu.

### Giải thích

Linearizable read yêu cầu xác nhận strong real-time semantics đối với primary/majority. Khi không thể xác nhận đủ điều kiện, đọc phải chờ/lỗi thay vì trả một giá trị không có bảo đảm yêu cầu.

### Xử lý

1. Xem health/quorum/primary election.
2. Đảm bảo `maxTimeMS` và client timeout có hạn.
3. Giữ fail-closed policy cho dữ liệu security/coordination-critical.
4. Kiểm tra liệu endpoint thật sự cần linearizable hay một `majority`/causal contract đủ.
5. Nếu muốn downgrade, thực hiện thay đổi policy có approval, không tự động.

### Không làm

Không tắt read concern ở chính một leader-lock authorization path chỉ để endpoint trả HTTP 200.

## 63. Runbook 4 — Primary failover sau `w:1` success

### Dấu hiệu

Application đã nhận success từ write với `w:1`, nhưng sau election document không còn thấy và rollback logs cho thấy write chưa majority commit.

### Xử lý

1. Xác nhận write acknowledgment level và timeline.
2. Kiểm tra replica set topology, rollback indicators và new primary state.
3. Reconcile với durable business request IDs/outbox/source-of-truth.
4. Nếu data là critical, nâng write requirement theo change plan và đảm bảo đủ data-bearing majority.
5. Thêm chaos/failover integration tests có assertion business outcome.

### Không làm

Không sửa readConcern thành `majority` rồi coi đã giải quyết write durability; read concern không thay acknowledgement của write trước đó.

## 64. Runbook 5 — Driver không tìm được secondary đủ điều kiện

### Dấu hiệu

```text
readPreference=secondary
server selection timeout
secondary nodes exist but none eligible
```

### Khả năng

- Một secondary lag vượt max staleness threshold.
- Tag sets không khớp configuration thực.
- Secondary unreachable / recovering / down.
- Replica set chỉ có một member.
- Advertised hostnames/DNS không reachable.

### Xử lý

1. Kiểm tra `rs.status()` và `hello` trên members.
2. Kiểm tra tags, max staleness, latency policy, driver logs.
3. Xác minh application network tới advertised hosts.
4. Giảm tải/khôi phục secondary health.
5. Nếu business chấp nhận primary fallback, cân nhắc `secondaryPreferred` qua change review; nếu không, giữ fail rõ ràng.

### Không làm

Không đổi `secondary` sang `nearest` rồi cho rằng vẫn chỉ đọc secondaries.

## 65. Runbook 6 — Majority writes chậm trên PSA

### Dấu hiệu

Replica set có primary, secondary, arbiter; khi secondary bị mất kết nối, `w:majority` writes bị timeout dù primary còn nhận `w:1` writes.

### Giải thích

Arbiter bỏ phiếu nhưng không lưu data; không thể thay việc replication tới data-bearing node cho các majority write requirements.

### Xử lý

1. Kiểm tra voting/data-bearing member topology.
2. Khôi phục secondary health/network.
3. Đánh giá triển khai thêm data-bearing member phù hợp.
4. Kiểm tra implicit default write concern trên topology này.
5. Giữ business durability SLA; nếu thay policy phải có quyết định được phê duyệt.

### Không làm

Không coi arbiter là “secondary thứ hai”, và không giảm `w:majority` vô điều kiện vì mục tiêu “có write”.

## 66. Runbook 7 — Report trả tổng khác giữa hai lần đọc

### Dấu hiệu

Một report thực hiện hai aggregations:

```text
read A at T1
read B at T2
```

Nếu có writes giữa T1/T2, kết quả có thể không tương ứng cùng snapshot dù cả hai reads có `readConcern:"majority"`.

### Xử lý

1. Xác định report cần snapshot logic hay chỉ eventually consistent metrics.
2. Nếu cần snapshot, dùng transaction/supported snapshot reads phù hợp duration.
3. Với báo cáo dài, cân nhắc materialized report theo cut-off/as-of timestamp.
4. Đảm bảo indexes/performance, tránh transaction quá lâu.
5. Test concurrent writer trong lúc report đọc.

### Không làm

Không chỉ đổi read preference thành primary rồi tuyên bố hai reads đã cùng một snapshot.

## 67. Runbook 8 — Read gần nhất nhưng dữ liệu cũ

### Dấu hiệu

Client dùng `nearest`, nhận request nhanh nhưng trả version cũ.

### Xử lý

1. Xác định actual host/role, replication lag và latency selection.
2. Xác nhận read concern đang dùng.
3. Nếu business yêu cầu latest/causal, sửa read path bằng primary/causal session policy.
4. Nếu business cho phép eventual, hiển thị freshness/time-as-of và đặt lag SLO.
5. Kiểm tra cache/search vì có thể không phải do MongoDB secondary.

### Không làm

Không coi `nearest` là “lấy primary ở khu vực gần nhất” hoặc “lấy document mới nhất”.

## 68. Runbook 9 — Transaction commit trả kết quả chưa chắc chắn

### Dấu hiệu

Transaction commit kết thúc bằng lỗi có label `UnknownTransactionCommitResult` hoặc network/socket exception sau khi commit đã được gửi.

### Giải thích

Client không biết commit đã thành công hay chưa; **không được** tự chạy lại toàn business workflow mà có thể double side effects.

### Xử lý

1. Phân biệt transient transaction body retry và unknown commit result.
2. Dùng driver transaction retry pattern đúng loại lỗi, trong retry budget.
3. Kiểm tra business transaction ID/ledger state nếu chưa thể xác nhận.
4. Không gửi email/payment trực tiếp trong retryable callback nếu không có outbox/idempotency.
5. Kiểm tra majority/journal, election timeline, timeout config.

### Không làm

Không coi `UnknownTransactionCommitResult` giống `abortTransaction` đã chạy hoặc “chắc chắn chưa commit”.

## 69. Runbook 10 — Default RW concern bị đổi ngoài dự kiến

### Dấu hiệu

Sau đổi replica set membership/cluster config, latency hoặc rollback exposure thay đổi dù application code không sửa.

### Khả năng

- Server implicit write concern thay theo topology.
- `setDefaultRWConcern` được thay bởi admin.
- Service mới override client/database settings.
- Một URI/environment profile khác đã được deploy.
- Transactions có options riêng.

### Xử lý

1. Đọc effective config path của service (không tiết lộ secrets).
2. Kiểm tra `getDefaultRWConcern`, `rs.conf()` với quyền thích hợp.
3. Xác định ngày giờ/config change/version change.
4. So sánh p95/p99, write concern errors và business outcomes.
5. Đặt explicit options cho critical paths khi cần.
6. Thực hiện config change review và regression testing.

### Không làm

Không chỉ khẳng định “MongoDB mặc định luôn w:1” hoặc “luôn majority” cho mọi topology và phiên bản.

## 70. Test matrix cho concerns/preferences

| Test | Topology | Options | Điều cần kiểm tra |
|---|---|---|---|
| Local read basic | Single-node RS | `local+primary` | Read thành công |
| Majority write/read | Multi-node RS | `w:majority,rc:majority` | Write ack/read stable |
| Secondary stale | Three-node RS | `rc:majority,rp:secondary` | Có thể lag, không tự assume latest |
| PrimaryPreference | Multi-node RS | `rp:primary` | Server selection chỉ primary |
| SecondaryPreferred fallback | Multi-node RS | `rp:secondaryPreferred` | Dùng secondary hoặc fallback theo health |
| Secondary unavailable | Single-node RS | `rp:secondary` | Server selection timeout theo budget |
| Election | Three-node RS | `w:majority,rp:primary` | No primary window, retry/recovery |
| `w:1` rollback exposure | Multi-node with controlled fault | `w:1` | Không hứa write sống qua failover |
| `wtimeout` | Multi-node with controlled lag | `w:majority,wtimeout` | Outcome có thể unknown |
| Linearizable | Multi-node RS | `rc:linearizable,rp:primary` | Real-time ordering/timeout |
| Causal session | Multi-node RS | Majority read/write + session | Read-your-writes |
| Snapshot transaction | Supported topology | `rc:snapshot,commit w:majority` | Coherent view |
| PSA outage | P–S–A test setup | `w:majority` | Loss of S affects majority ack |
| Sharded read | Sharded cluster | `majority/available` | Routing/orphan caveats |
| Tags/max staleness | Multi-node tagged RS | `rp:secondary,tags` | Eligible server filtering |

### 70.1. Vì sao single-node replica set không đủ?

Nó có thể test transactions/readConcern majority basic semantics, nhưng không có secondary để tái tạo replication lag/election/secondary selection. Không báo test failover “passed” chỉ vì container restart sau khi bị dừng.

### 70.2. Cần test hạ tầng chấp nhận được

Thực hiện failure injection trên disposable Testcontainers/multi-node test cluster; không stop primary production để test lý thuyết.

### 70.3. Không assert thời gian election cố định

Theo dõi state có deadline và SLO window. CI/local có scheduling khác nhau, không dùng `Thread.sleep(2000)` như bằng chứng election xong.

## 71. JUnit 5 + Testcontainers: kiểm thử cấu hình cơ bản

Một integration test có thể dùng MongoDB container thật, thay vì mock driver:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import static com.mongodb.client.model.Filters.eq;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class ConcernSmoke471IT {
    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @Test
    void majorityWriteThenMajorityPrimaryRead() {
        try (MongoClient client =
                 MongoClients.create(mongo.getReplicaSetUrl())) {

            var collection = client
                .getDatabase("consistency_lab_471")
                .getCollection("orders")
                .withWriteConcern(WriteConcern.MAJORITY)
                .withReadConcern(ReadConcern.MAJORITY)
                .withReadPreference(ReadPreference.primary());

            collection.insertOne(new Document("_id", "T471")
                .append("status", "PAID"));

            Document result = collection
                .find(eq("_id", "T471"))
                .first();

            assertNotNull(result);
            assertEquals("PAID", result.getString("status"));
        }
    }
}
```

### 71.1. Nó chứng minh gì?

Integration test dùng MongoDB thật và hai concerns có thể chạy với topology hỗ trợ.

### 71.2. Nó **không** chứng minh gì?

Single-node replica set majority chỉ cần một member; test này **không** chứng minh replication qua máy thứ hai hay độ bền khi mất primary và bầu secondary. Để test những điều đó cần nhiều data-bearing members.

### 71.3. Test read preference secondary cần topology khác

Nếu bạn thêm `withReadPreference(ReadPreference.secondary())` vào sample single-node, không có eligible secondary. Hãy chạy multi-node RS với hostnames reachable và xác minh actual selected host.

### 71.4. Fault injection

Muốn test failover, phải:

1. Start three-node RS với majority.
2. Đợi một primary, hai secondaries.
3. Gửi majority write.
4. Dừng primary hiện tại (không mặc định node A).
5. Đợi election.
6. Đọc/ghi với driver đã khám phá primary mới.
7. Assert dữ liệu majority-acknowledged còn và business identity không double apply.

### 71.5. Thời gian và isolation

Không test primary failure trên production. Tránh hardcode port 27017 trên host vì Testcontainers dùng dynamic mapped ports. Test timeout cần đủ cho CI, nhưng bounded.

## 72. Phân biệt consistency của một thao tác và của cả workflow

Một endpoint tạo đơn hàng thường làm:

```text
1. Authorize user
2. Validate stock and price
3. Insert order
4. Reserve inventory
5. Publish event
6. Read order back
7. Respond HTTP 201
```

### 72.1. Mỗi bước có nguồn consistency khác nhau

| Bước | Cơ chế chính |
|---|---|
| Authorize | Identity, role, tenant policy, policy freshness |
| Validate stock | Domain invariants, conditional write/transaction |
| Insert order | Unique keys, write concern, idempotency |
| Reserve inventory | Atomic filter/transaction, concurrency control |
| Publish event | Outbox/event delivery semantics |
| Read back | Read concern, preference, causal/session/cache |
| HTTP response | Deadline, unknown outcomes, retry contract |

### 72.2. Không có “one setting to rule them all”

`w:"majority"` không thay transaction; `readConcern:"linearizable"` không thay authorization/atomic conditional update; `readPreference:"primary"` không tự invalidate Redis cache.

### 72.3. End-to-end SLAs

Các câu hỏi cần ghi thành contract:

- HTTP 201 có nghĩa order đã majority acknowledged?
- Nếu client timeout sau POST, có thể POST lại cùng requestId không?
- GET ngay sau POST phải đọc primary hay có causal token?
- External search/email được phép lag bao lâu?
- Khi majority unavailable, hệ thống trả error hay chấp nhận reduced durability?

### 72.4. Không báo “consistency strong” chung chung

Tốt hơn là: “Ghi order majority-acknowledged; GET cùng operation chain sử dụng primary + majority; asynchronous search có SLA 30 giây; payments có idempotency key.” Đây là requirement có thể kiểm thử.

## 73. Anti-patterns và cách thay

| Anti-pattern | Vấn đề | Cách sửa |
|---|---|---|
| Coi read concern = read preference | Nhầm data guarantee với server selection | Chọn riêng |
| Coi `majority` = latest | Secondary lag dù majority data | Primary/causal/linearizable theo yêu cầu |
| Coi `w:majority` = mọi nodes đã apply | Third secondary có thể lag | Theo dõi replication / causal read |
| Coi `w:2` luôn majority | Với 5 voters majority là 3 | Dùng `w:"majority"` |
| Coi `w:1` là không rollback | Unreplicated write có thể rollback | Majority nếu critical |
| Coi `j:true,w:1` = multi-node durability | Journal không phải replica confirmation | Chọn write concern phù hợp |
| Coi `wtimeout` hủy write | Write có thể đã áp dụng | Idempotent recovery |
| Retry transfer với request ID mới | Double business effect | Stable idempotency key |
| `readPreference=secondary` trong one-node RS | Không có eligible secondary | Multi-node hoặc primary |
| `secondaryPreferred` để bắt buộc offload | Có fallback primary | `secondary` nếu phải avoid primary |
| `primaryPreferred` cho security decisions | Silent fallback stale | Strong path/fail closed |
| `nearest` = newest | Latency không là version | Define freshness separately |
| `maxStalenessSeconds=1` cho SLA 1s | Driver constraints, estimate only | Primary/causal/lag gate |
| Chỉ đổi read concern để chữa cache lag | Không ảnh hưởng cache | Invalidate/version cache |
| Chỉ đổi preference để chữa write rollback | Read routing không thay write ack | Set write concern |
| Chỉ chọn `snapshot` để chữa lost update | Snapshot không thay domain guard | CAS/transaction constraints |
| `linearizable` cho mọi list/report | Cost cao, scope limited | Select targeted strong reads |
| `majority` hai queries = cùng snapshot | Hai lần đọc khác thời điểm | Snapshot/transaction |
| Không có `maxTimeMS` với linearizable | Có thể chờ rất lâu | Deadline và fail-closed policy |
| Transaction đọc secondary | Role restriction/conflict | ReadPreference.primary theo API |
| Per-operation `w` trong transaction | Commit semantics bị hiểu sai | TransactionOptions |
| Retry whole txn body khi commit unknown | Double side effects | Correct commit retry + outbox |
| Causal session bật nhưng w:1/rc:local | Thiếu guarantees mong muốn | Majority read/write |
| Dùng một session trên nhiều threads | Không an toàn theo driver API | Sequential session operations |
| Dùng HTTP cookie như MongoDB session | Không có causal time tự động | Explicit causal protocol |
| Hạ `w` trong outage tự động | Thay đổi durability SLA | Approved fallback/fail |
| PSA arbiter được tính như secondary data | Majority write ack không đủ | Data-bearing topology |
| Tin implicit defaults cố định | Thay theo server/topology/overrides | Inspect/explicit critical options |
| Query missing shard key gây slow, sửa concern | Không giải quyết scatter/gather | Shard-aware query/index |
| Dùng `available` trên sharded mà quên orphaned | Potential duplicate/inconsistent reads | Use correct concern |
| Xem `readConcern:majority` là “sao lưu” | Không bảo vệ xóa nhầm | Backups/PITR/RBAC |
| Đo chỉ command p99, không đo staleness | HTTP 200 vẫn data cũ | Domain freshness metrics |
| Không theo dõi actual read server | Preference khác actual role | SDAM/command monitoring |
| Log URI đầy đủ | Lộ credentials | Redact secrets |
| Chạy failover test trên prod | Rủi ro outage | Disposable test cluster |
| Đổi server default mà không review services | Silent policy drift | Config ownership/canary |

## 74. Bảng điền cấu hình cho từng API

Một artifact thiết kế đơn giản trước khi code:

| Endpoint/job | Freshness contract | Durability contract | Read concern | Write concern | Read preference | Session/transaction | Fallback |
|---|---|---|---|---|---|---|---|
| GET catalog | Có thể stale theo SLA | Không ghi | `local`/`majority` | — | `secondaryPreferred` | Không nếu không yêu cầu | Show cached timestamp |
| GET order vừa tạo | Read-your-writes | Order majority committed | `majority` | — | `primary`/causal | Có nếu cross-secondary causal | Retry bounded/read primary |
| POST order | Response có durable ack | Majority | — | `majority` | — | Idempotency + optional txn | Unknown outcome reconcile |
| POST transfer | Atomic business transaction | Majority commit | `snapshot` | `majority` | `primary` | Transaction + request ID | Retry protocol |
| GET leader lock | Real-time single doc | Lock majority acknowledged | `linearizable` | — | `primary` | CAS/fencing for write | Fail closed |
| Generate finance report | Consistent as-of view | Source committed | `snapshot` | — | Theo txn/API | Snapshot mechanism | Delay report |
| Dashboard telemetry | Eventual | N/A | `local` | — | `nearest`/`secondary` | None | Show as-of timestamp |
| Analytics export | Snapshot/timestamp if required | N/A | `snapshot`/`majority` | — | Theo scope | Bounded jobs | Defer |

**Điền bảng theo từng hệ thống:** không copy các ô mang dạng “A/B” như cấu hình chính thức nếu chưa chọn một option và nêu rõ điều kiện.

### 74.1. Viết một câu “acceptance criterion”

Ví dụ:

> Khi API tạo order trả 201, dữ liệu đã được majority-acknowledged và GET cùng luồng tương tác có thể thấy order qua read path đã định. Nếu response bị mất, client retry cùng requestId không tạo order thứ hai.

Đây là tiêu chí kiểm thử được; câu “dùng consistency mạnh” thì chưa đủ.

### 74.2. Cập nhật khi đổi topology

Các cột `w:majority` và read preference có thể cần re-evaluate nếu replica set đổi số members, thêm arbiter, đổi region hoặc shard. Không coi quyết định một lần là bất biến.

## 75. Bài tập thực hành

### Bài 1 — Phân loại ba concern/preference

Phân biệt `readConcern`, `writeConcern` và `readPreference` bằng ba câu hỏi riêng. Đưa một ví dụ khi readPreference đã đúng nhưng read concern chưa phù hợp.

### Bài 2 — Majority không đồng nghĩa latest

Replica set P, S1, S2. P và S1 đã apply revision=9; S2 mới apply revision=8. `readConcern=majority` trên S2 có thể trả revision nào? Giải thích.

### Bài 3 — Read concern local

Một client đọc trạng thái “PAID” từ primary với `local`, sau đó primary bị failover và write đó rollback. Vì sao client từng thấy “PAID”?

### Bài 4 — Available trên sharded cluster

Chunk chuyển từ shard A sang B, còn orphaned document tạm thời. Đọc `available` có caveat gì? Có nên dùng cho financial aggregates không?

### Bài 5 — Linearizable

Một lock record đã được majority-acknowledged trước khi GET bắt đầu. Chọn read concern/preference cho real-time ordering; nêu lý do cần `maxTimeMS`.

### Bài 6 — Snapshot

Một báo cáo đọc accounts và ledger trong hai queries; có writes concurrent. Tại sao `majority` cho cả hai chưa tự bảo đảm cùng một snapshot?

### Bài 7 — Single-node vs multi-node

Single-node replica set có thể đáp ứng `w:majority` bằng một member. Điều gì chưa được test về durability/replication nếu integration test chỉ chạy một container?

### Bài 8 — w:0

Một service ghi audit events với `w:0`. Những thông tin lỗi/kết quả nào có thể không nhận được? Đề xuất phương án phù hợp hơn nếu audit cần bảo đảm.

### Bài 9 — w:1 failover

Ghi với `w:1` đã trả success rồi primary chết trước replication. Viết timeline rollback và business recovery strategy.

### Bài 10 — w:majority

Replica set năm voters có ba data-bearing members và hai arbiters. Tại sao tính majority/data acknowledgment cần phân biệt arbiter với secondary?

### Bài 11 — w:n

Replica set năm voting data-bearing members. `w:2` có tương đương `w:"majority"` không? Majority yêu cầu bao nhiêu?

### Bài 12 — Journal

So sánh `{w:1,j:true}` và `{w:"majority"}` trên hai kiểu sự cố: process crash primary và primary election. Đưa ra giới hạn của từng case.

### Bài 13 — Timeout

`wtimeout=5000` sau insert, application nhận lỗi. Có thể khẳng định document chưa tồn tại không? Cần truy vấn/identity protocol nào để retry an toàn?

### Bài 14 — Error classification

Phân biệt MongoDB server selection timeout, socket timeout và write concern timeout về thời điểm lệnh có thể đã được gửi/thực thi.

### Bài 15 — Read preference primary

Trong cửa sổ election không có primary, `readPreference=primary` có thể xảy ra điều gì? Tại sao không tự đổi sang secondary cho một API payment?

### Bài 16 — PrimaryPreferred

Viết một tình huống primaryPreferred đọc revision=20 ở P, rồi revision=19 ở secondary khi failover. Causal monotonicity bị ảnh hưởng ra sao?

### Bài 17 — Secondary

Một test dùng `ReadPreference.secondary()` trên single-node replica set. Dự kiến hiện tượng gì? Hãy chỉnh test topology để thực sự test secondary.

### Bài 18 — SecondaryPreferred

Một hệ thống muốn *tuyệt đối không* chạy heavy report trên primary, nhưng đang dùng secondaryPreferred. Chỗ sai ở đâu?

### Bài 19 — Nearest

Primary RTT=18 ms, secondary RTT=5 ms nhưng lag 40 giây. Chọn nearest có thể trả gì? Khi nào cấu hình này phù hợp?

### Bài 20 — Max staleness

Tại sao đặt `maxStalenessSeconds=2` không tạo SLA freshness 2 giây? Nêu server-selection estimate, minimum/version constraints và business read path thay thế.

### Bài 21 — Tag sets

Replica set ở APAC và EU. Thiết kế preference/tags cho reporting ở APAC, nêu fallback và giới hạn của tags đối với data residency.

### Bài 22 — Causal session

Viết Java pseudocode dùng `ClientSessionOptions.causallyConsistent(true)`, majority write/read để đọc own write.

### Bài 23 — HTTP vs MongoDB session

User đăng nhập bằng JWT và request A ghi vào pod 1, request B đọc qua pod 2. Vì sao JWT không tự có causal metadata cho MongoDB?

### Bài 24 — Transaction

Viết `TransactionOptions` với read concern snapshot, commit majority và primary read preference. Giải thích tại sao không đặt `w` riêng cho từng update trong transaction.

### Bài 25 — UnknownTransactionCommitResult

Commit trả unknown result. Phân biệt retry commit với retry transaction body; thiết kế idempotency/outbox cho một lệnh chuyển tiền.

### Bài 26 — Sharded majority

Một report đọc nhiều shards với `readConcern=majority`. Vì sao điều này không nhất thiết tạo cùng một point-in-time snapshot?

### Bài 27 — Sharding và available

Đánh giá readConcern available trong lúc chunk migration; giải thích nguy cơ orphaned documents.

### Bài 28 — URI

Viết MongoDB connection string có `readPreference=primary`, `readConcernLevel=majority`, `w=majority`, `journal=true` và `wtimeoutMS=5000`.

### Bài 29 — Client vs collection overrides

MongoClient đặt majority/primary, collection báo cáo đặt secondaryPreferred. Làm sao xác định operation thực tế đọc server nào?

### Bài 30 — Java linearizable

Viết một find theo `_id` với `ReadConcern.LINEARIZABLE`, `ReadPreference.primary()` và bounded `maxTime`.

### Bài 31 — Mongosh command

Viết `db.runCommand` cho insert có write concern majority/j:true/wtimeout; giải thích result/error có thể chứa gì.

### Bài 32 — Read-your-writes

POST order dùng w:majority, GET đọc majority trên secondary không có session. Có bắt buộc thấy order không? Đề xuất hai giải pháp.

### Bài 33 — Cache/search

Một endpoint đọc Redis cache rồi Atlas Search và cuối cùng MongoDB. Vì sao chỉ đặt readConcern majority ở MongoDB không tạo nhất quán toàn endpoint?

### Bài 34 — Defaults

Một service không chỉ định write concern và cluster chuyển sang topology có arbiter. Nêu bước kiểm tra implicit/explicit defaults và những rủi ro.

### Bài 35 — PSA

Replica set P–S–A mất S; P và A còn kết nối. Vì sao majority write concern có thể không hoàn tất? Arbiter có lưu dữ liệu không?

### Bài 36 — Monitoring

Thiết kế dashboard có command latency p99, write concern errors, replication lag, secondary read routing, server selection timeouts và domain stale-read rate.

### Bài 37 — Chaos test

Thiết kế multi-node replica set test: majority write, stop actual primary, elect new primary, verify committed data; xác định unsafe assumptions.

### Bài 38 — Incident

Sau deploy, `w:majority` timeout tăng và API p99 xấu. Lập runbook mà **không** hạ `w` tự động.

### Bài 39 — Business SLA matrix

Chọn concerns/preferences/session cho bốn endpoints: `GET /catalog`, `POST /orders`, `POST /transfer`, `GET /leader-lock`. Nêu chính xác trade-offs.

### Bài 40 — Capstone

Một SaaS B2B MongoDB có:

1. Replica set ba data-bearing members qua hai regions.
2. 10.000 writes/giây catalog, 1.000 writes/giây orders.
3. Payments không được double charge.
4. Reports nặng và dashboard chấp nhận lag.
5. Failover diễn ra vài lần/năm.
6. Client Java Sync Driver và Spring Data.
7. Atlas Search với indexing delay.
8. Yêu cầu track sự cố uncertain write.

Thiết kế:

- Read/write consistency contracts theo từng endpoint.
- Concerns/preferences và timeout levels.
- Causal sessions/transactions ở nơi cần.
- Unique business keys/idempotency/outbox.
- Separate reporting handles và safety rules.
- Replica set topology, majority/journal policy.
- Metrics/alerts và test matrix.
- Canary rollout, failure recovery và runbooks.

## 76. Mẫu kiểm tra nhanh trước khi chọn cấu hình

Khi đọc một yêu cầu mới, đi theo thứ tự:

```text
1) Operation:
   read / write / transaction / stream?

2) Business meaning:
   stale allowed?
   rollback-ack allowed?
   read-your-writes required?
   real-time single-document?
   snapshot across documents?

3) Deployment:
   standalone / replica set / sharded?
   voting/data-bearing members?
   arbiter?
   secondary lag?
   region/network?

4) Correctness:
   read concern
   write concern
   read preference
   sessions/transactions/atomic filters

5) Reliability:
   timeout and retry budget
   idempotency key
   unknown outcomes
   backup and disaster recovery

6) Verification:
   functional tests
   failover tests
   actual server selection metrics
   business freshness checks
```

### 76.1. Không có yêu cầu dữ liệu mới nhất?

Đừng mặc định `linearizable`. Có thể dùng `majority` hoặc `local` với read preference phù hợp và giải thích dữ liệu có thể stale bao lâu.

### 76.2. Phải tránh rollback sau write success?

Ưu tiên `w:"majority"` trên topology đáp ứng, kèm durability/journal policy và idempotency. Không chỉ nâng read concern.

### 76.3. Phải thấy chính write vừa hoàn tất?

Chọn primary read hoặc causal session với majority read/write khi cần theo semantics hỗ trợ; kiểm tra cache/search còn giữ dữ liệu cũ không.

### 76.4. Phải đọc nhiều documents nhất quán?

Cân nhắc snapshot transaction/supported snapshot reads, nhưng không dùng transaction lâu khi data volume lớn.

### 76.5. Phải sống qua failover?

Thiết kế retryability/primary discovery và quan sát uncertainty; write concern không tự làm endpoint luôn available khi không có primary/quorum.

## 77. Checklist vận hành an toàn

### Trước rollout

- [ ] Business owner đã định nghĩa chính xác consistency/durability SLA.
- [ ] Đã phân biệt read concern, write concern, read preference, không đặt một từ “strong” chung chung.
- [ ] Replica set topology, votes, arbiters và secondaries được ghi nhận.
- [ ] Đã kiểm tra implicit/server default RW concern và explicit overrides.
- [ ] Có read concern phù hợp với operation/server version.
- [ ] Có write concern explicit cho critical writes.
- [ ] Có timeout rõ cho server selection, linearizable, writes và transactions.
- [ ] Có unique business keys, retries/idempotency.
- [ ] Có policy causal session/transaction nếu nghiệp vụ cần.
- [ ] Có dashboard lag, commit point, command duration, write concern errors.
- [ ] Có canary và rollback plan.

### Khi vận hành

- [ ] Không hạ `w:majority` xuống `w:1` vô điều kiện khi outage.
- [ ] Không cho rằng `majority` trên secondary là latest.
- [ ] Không coi `wtimeout` là write chưa xảy ra.
- [ ] Không chạy transactions dài để lấy snapshot vô hạn.
- [ ] Không truyền raw URI/credentials trong logs.
- [ ] Không dùng performance tuning để vô hiệu hóa business guards.
- [ ] Theo dõi actual read server/role, không chỉ configured readPreference.
- [ ] Theo dõi replication lag và staleness ngoài p99 latency.
- [ ] Có reconciliation khi outcome unknown.
- [ ] Kiểm thử failover trên môi trường disposable.

## 78. Tổng kết

**Read concern, write concern và read preference là ba chiều độc lập cần chọn cùng nhau**:

- **Read concern** trả lời “đọc loại trạng thái nào và có bảo đảm gì?”; `local` cho phép đọc state chưa majority committed, `majority` giới hạn về majority-committed, `linearizable` tăng yêu cầu real-time ordering cho single-document reads, `snapshot` giúp giữ view nhất quán và `available` có caveats đặc biệt trong sharded deployment.
- **Write concern** trả lời “server phải xác nhận write ở mức nào trước khi trả về?”; `w:1` có nguy cơ rollback sau failover, `w:majority` tăng durability/availability trade-offs, `j` liên quan journal và `wtimeout` không có nghĩa write đã bị hủy.
- **Read preference** trả lời “driver đọc ở đâu?”; `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred` và `nearest` quyết định server selection, không tự quyết định majority commit, causal semantics hay freshness tuyệt đối.

**Những điều quan trọng cần nhớ:** `majority` không đồng nghĩa “mới nhất”; `nearest` không đồng nghĩa “secondary mới nhất”; `secondaryPreferred` không bắt buộc tránh primary; majority-acknowledged write không đảm bảo mọi secondary đã apply; snapshot không tự tạo real-time freshness; và linearizable read không thay atomic conditional updates.

Với mỗi nghiệp vụ, hãy viết **contract có thể test** về freshness, durability, atomicity và availability; sau đó chọn concerns/preferences, sessions/transactions, timeout/retry, idempotency và topology tương ứng. Một sự cố phải được xử lý theo outcome uncertainty, không bằng cách tự hạ mức bảo đảm hoặc đoán thao tác chắc chắn chưa xảy ra.

## 79. Tài liệu tham khảo

- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): tổng quan levels và semantics.
- [MongoDB Manual — Read Concern "local"](https://www.mongodb.com/docs/manual/reference/read-concern-local/): local read behavior.
- [MongoDB Manual — Read Concern "available"](https://www.mongodb.com/docs/manual/reference/read-concern-available/): available read và sharding caveats.
- [MongoDB Manual — Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/): majority-committed reads.
- [MongoDB Manual — Read Concern "linearizable"](https://www.mongodb.com/docs/manual/reference/read-concern-linearizable/): linearizable single-document read semantics.
- [MongoDB Manual — Read Concern "snapshot"](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/): transactions và snapshot reads.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): w, j, wtimeout, defaults.
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): primary/secondary/nearest.
- [MongoDB Manual — Read Preference Tags](https://www.mongodb.com/docs/manual/core/read-preference-tags/): tags trong server selection.
- [MongoDB Manual — Max Staleness](https://www.mongodb.com/docs/manual/core/read-preference-staleness/): staleness constraints.
- [MongoDB Manual — Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/): sessions và ordering guarantees.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): transaction concern semantics.
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/): primary election/votes.
- [MongoDB Manual — Replica Set Arbiter](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/): arbiter restrictions.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): acknowledged retry semantics.
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/): mongos và consistency.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): oplog/resume tokens.
- [MongoDB Java Sync Driver — Read Concern](https://www.mongodb.com/docs/drivers/java/sync/current/read/read-concern/): driver configuration.
- [MongoDB Java Sync Driver — Write Concern](https://www.mongodb.com/docs/drivers/java/sync/current/write/write-concern/): driver write options.
- [MongoDB Java Sync Driver — Read Preference](https://www.mongodb.com/docs/drivers/java/sync/current/read/read-preference/): driver server selection.
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/): transaction options and retry examples.
- [Testcontainers Java — MongoDB](https://java.testcontainers.org/modules/databases/mongodb/): integration test topology.







