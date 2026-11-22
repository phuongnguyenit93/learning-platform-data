# Đánh đổi tính nhất quán, độ trễ và khả dụng khi mạng bị phân vùng

Một hệ thống MongoDB có thể chạy ổn định trong nhiều tháng rồi đột nhiên gặp tình huống: **primary vẫn còn chạy trên một máy**, nhưng ứng dụng nhận lỗi ghi; một **secondary vẫn phản hồi truy vấn**, nhưng dữ liệu người dùng vừa cập nhật chưa xuất hiện; hoặc một câu lệnh `insertOne()` báo timeout, dù document thực tế đã được ghi ở primary.

Những tình huống trên không nhất thiết là MongoDB “làm mất dữ liệu” hay “bị lỗi nhất quán”. Chúng phản ánh các **đánh đổi có chủ đích** trong hệ thống phân tán, đặc biệt khi các node mất khả năng giao tiếp hoặc replication bị trễ.

Bài học thuộc chương **Nhất quán đọc ghi** tập trung vào ba mục tiêu liên quan nhưng khác nhau:

1. **Tính nhất quán (consistency):** một lần đọc được phép nhìn thấy dữ liệu ở mức nào, các thao tác được quan sát theo thứ tự nào, và hệ thống có bảo vệ những ghi đã xác nhận hay không?
2. **Độ trễ (latency):** ứng dụng phải chờ bao lâu để một thao tác đọc hoặc ghi hoàn tất ở mức đảm bảo đã chọn?
3. **Tính khả dụng (availability):** khi mất node hoặc mạng bị phân vùng, ứng dụng còn thực hiện được thao tác nào, tại vùng nào và với mức đảm bảo nào?

MongoDB cho phép thiết kế mức đánh đổi qua **replica set quorum, write concern, read concern, read preference, session, transaction và cách xử lý lỗi của client**. Không có cấu hình duy nhất vừa cho phép mọi vùng độc lập luôn ghi thành công, vừa bảo đảm mọi lần đọc luôn thấy trạng thái mới nhất và mọi thao tác đều có độ trễ tối thiểu trong mọi tình huống mạng.

> **Nguyên tắc:** Khi mạng bị phân vùng, một phía không có đa số phiếu không thể tự duy trì quyền ghi primary hợp lệ. Điều đó có thể làm giảm khả dụng của một số request, nhưng giúp bảo vệ mô hình một primary hợp lệ và thứ tự ghi được hệ thống cam kết. Cho phép đọc từ secondary có thể tăng khả năng phục vụ đọc, nhưng còn phụ thuộc read concern và độ mới của dữ liệu.

## 1. Bối cảnh: một replica set ba thành viên

Xét replica set `rs0`:

```text
                 Ứng dụng
                     |
              MongoDB driver
                     |
          ┌──────────┴───────────┐
          |                      |
       node-a                  node-b               node-c
       PRIMARY                 SECONDARY            SECONDARY
       vote=1                  vote=1               vote=1
       data=yes                data=yes             data=yes
          |                       ^                    ^
          +------ replication ----+--------------------+
```

Trong trạng thái bình thường:

- Client ghi vào **primary**.
- Secondary nhận và áp dụng các thao tác ghi thông qua replication.
- Các thành viên có quyền bỏ phiếu phối hợp bầu primary.
- Mỗi node có thể có tốc độ apply dữ liệu khác nhau.
- Client dùng **read preference** để chọn nơi đọc và **read concern** để chọn mức đảm bảo dữ liệu đọc.
- Client dùng **write concern** để chọn mức xác nhận cần có trước khi coi thao tác ghi hoàn tất theo hợp đồng của mình.

Nếu `node-a` mất kết nối với `node-b` và `node-c`, replica set không còn một mạng kết nối đầy đủ. Hai nhóm có thể hình thành:

```text
Phân vùng A                       Phân vùng B
────────────                      ────────────
node-a                            node-b   node-c
  1 phiếu                           1       1
                                     └── 2 phiếu ──┘
```

Replica set có ba voting members, quorum là **hai phiếu**. Phân vùng B có quorum nên có thể bầu primary mới nếu ứng viên đủ điều kiện. Phân vùng A chỉ có một phiếu, không thể tiếp tục duy trì quyền primary hợp lệ một khi nhận ra mất đa số.

Điều này không có nghĩa mọi request đọc ở phân vùng A chắc chắn lập tức lỗi. Một số read từ node còn truy cập được vẫn có thể xảy ra theo role, trạng thái node, read preference và read concern. **Khả dụng cho đọc và khả dụng cho ghi không phải cùng một thứ.**

## 2. Định nghĩa rõ từng mục tiêu

### 2.1. Tính nhất quán không chỉ có một mức

Trong ứng dụng, từ “nhất quán” có thể chỉ nhiều yêu cầu:

- **Đọc sau khi ghi (read-your-writes):** sau khi người dùng đổi địa chỉ, lượt đọc tiếp theo của chính họ phải thấy địa chỉ mới.
- **Đọc theo thứ tự tăng dần (monotonic reads):** cùng một phiên không được thấy phiên bản dữ liệu cũ hơn sau khi đã thấy bản mới hơn.
- **Causal consistency:** các thao tác có quan hệ nhân quả được quan sát theo thứ tự phù hợp trong cùng session.
- **Majority-committed visibility:** lần đọc chỉ thấy dữ liệu đạt mức majority commit theo bảo đảm của MongoDB.
- **Linearizability:** một thao tác có vẻ xảy ra tại một thời điểm đơn lẻ giữa lúc bắt đầu và kết thúc, tôn trọng thứ tự thời gian thực của những thao tác đã hoàn tất.
- **Snapshot consistency:** nhiều lần đọc cùng quan sát một ảnh chụp dữ liệu logic tại một mốc, thay vì mỗi lần nhìn một trạng thái khác nhau.

Những yêu cầu này **không đồng nhất**. Một ứng dụng có thể cần causal consistency cho trang hồ sơ nhưng cần linearizable read cho một khóa trạng thái quan trọng; một báo cáo tài chính nhiều collection lại cần snapshot nhất quán.

### 2.2. Latency gồm nhiều thành phần

Thời gian hoàn tất một lệnh không chỉ là tốc độ index:

```text
Latency phía ứng dụng
  = thời gian chọn server/kết nối
  + network RTT tới node
  + chờ tài nguyên và thực thi query
  + chờ replication / write concern (nếu có)
  + chờ đủ điều kiện read concern (nếu có)
  + truyền kết quả và xử lý ở client
```

Khi replica set phân tán nhiều vùng, một lần ghi yêu cầu nhiều bản sao xác nhận thường tốn thời gian hơn một lần ghi chỉ chờ primary, đặc biệt khi bản sao cần thiết ở xa hoặc đang lag. Mức khác biệt thực tế phải được **đo trên topology và tải thật**.

### 2.3. Availability là khả dụng của thao tác nào?

Một node có thể:

- Còn phản hồi TCP;
- Vẫn trả thông tin `hello`;
- Có dữ liệu để đọc;
- Nhưng không phải primary;
- Không có quorum bầu cử;
- Hoặc không thể đáp ứng write concern mong muốn.

Vì vậy, trạng thái **“mongod vẫn chạy” không đồng nghĩa “ứng dụng còn ghi được đơn hàng an toàn”**.

Khi thiết kế SLA, hãy định nghĩa riêng:

| Khả năng | Câu hỏi cần trả lời |
|---|---|
| Read availability | Có thể đọc từ node nào khi primary mất? |
| Fresh-read availability | Có thể đọc trạng thái mới nhất theo mức yêu cầu không? |
| `w: 1` write availability | Có primary hợp lệ có thể nhận ghi không? |
| Majority-write availability | Có đủ data-bearing acknowledgements để hoàn tất ghi không? |
| Transaction availability | Có thể commit giao dịch với mức đảm bảo cần thiết không? |
| Business availability | Endpoint trả kết quả **đúng hợp đồng nghiệp vụ** hay chỉ trả HTTP 200? |

## 3. CAP theorem: hiểu đúng chữ C, A và P

CAP thường được tóm tắt thành: *khi mạng bị phân vùng, không thể đồng thời cung cấp đầy đủ consistency và availability theo định nghĩa của định lý*.

Ba chữ:

- **C — Consistency:** trong ngữ cảnh CAP là dạng nhất quán mạnh, thường biểu diễn bằng **linearizability**, không phải chỉ “schema luôn đúng” hoặc “dữ liệu không có lỗi”.
- **A — Availability:** mọi request tới một node không bị lỗi sẽ cuối cùng nhận **response thành công**, không phải luôn phải retry, timeout hay nhận lỗi từ chối.
- **P — Partition tolerance:** hệ thống vẫn có cách xử lý khi mạng làm các node không thể giao tiếp bình thường.

Khi một partition thật sự tồn tại, hệ thống không thể vừa:

1. Cho phép **mọi phía bị chia cắt đều nhận và xác nhận tất cả thao tác**;
2. Vừa bảo đảm các thao tác đó tuân theo **một thứ tự nhất quán mạnh theo thời gian thực**;

nếu các phía không thể trao đổi thông tin cần thiết.

### 3.1. Vì sao MongoDB có thể từ chối ghi ở phía thiểu số?

Giả sử:

```text
         NETWORK PARTITION
      ┌─────────────────────┐
      │                     │
  node-a                 node-b + node-c
  1 vote                   2 votes
      │                     │
  không đủ quorum       có thể bầu primary
```

Nếu cả hai phía đều tự cho phép primary nhận ghi độc lập, cùng một document có thể bị cập nhật theo hai lịch sử không thống nhất. Để duy trì mô hình một primary hợp lệ và bảo vệ những cam kết về ghi, MongoDB yêu cầu quorum bầu cử.

Hệ quả: phía chỉ có một phiếu **không duy trì quyền primary**. Client tại phía này có thể không ghi được. Đó là một **đánh đổi về write availability** nhằm bảo vệ các bảo đảm nhất quán của replica set.

### 3.2. Có nên gọi MongoDB là CP hay AP?

Không nên gắn một nhãn “MongoDB luôn CP” hoặc “MongoDB luôn AP” rồi bỏ qua cấu hình. Hành vi của một ứng dụng phụ thuộc vào:

- Replica set topology và quorum;
- Read preference;
- Read concern;
- Write concern;
- Trạng thái primary/secondary;
- Quy tắc retry;
- Việc ứng dụng có cho phép trả dữ liệu cũ hay không.

MongoDB replica set **không cho phép hai phía mất liên lạc cùng duy trì hai primary hợp lệ** theo quorum. Nhưng ứng dụng có thể đọc từ secondary với mức đảm bảo yếu hơn, chấp nhận stale data hoặc tạm ngừng ghi khi không có majority. Từng endpoint có thể có hành vi khác nhau.

**CAP không phải bảng chọn hai tính năng một lần rồi dùng mãi.** Nó chỉ ra giới hạn khi có partition; thiết kế thực tế phải mô tả **request nào tiếp tục và với ngữ nghĩa gì**.

### 3.3. Consistency trong CAP không giống chữ C của ACID

ACID nói về các thuộc tính của transaction, trong đó *Consistency* thường liên quan việc transaction giữ những ràng buộc/điều kiện hợp lệ của dữ liệu theo nghiệp vụ. CAP consistency tập trung vào khả năng quan sát một thứ tự thao tác mạnh trong hệ phân tán.

Một collection có schema validation và transaction đúng nghiệp vụ **không tự làm mọi secondary read thành linearizable**. Ngược lại, việc một read có linearizability không tự thay thế validation nghiệp vụ.

## 4. PACELC: độ trễ vẫn là đánh đổi ngay cả khi không có partition

CAP nhấn mạnh tình huống phân vùng mạng. Nhưng hệ thống phân tán phải chọn giữa latency và mức bảo đảm nhất quán **ngay cả lúc các node liên lạc bình thường**.

Một cách suy nghĩ là PACELC:

```text
Nếu xảy ra Partition (P):
    cân nhắc Availability (A) so với Consistency (C)

Else (E) khi hệ thống bình thường:
    cân nhắc Latency (L) so với Consistency (C)
```

Đây là **khung tư duy**, không phải một phép phân loại duy nhất áp lên mọi thao tác MongoDB.

Ví dụ:

- Ghi với `w: 1` có thể trả ACK sau khi primary chấp nhận theo điều kiện write concern; không cần đợi các secondary xác nhận.
- Ghi với `w: "majority"` phải chờ đủ acknowledgements theo quy tắc majority write concern, có thể tăng latency.
- Đọc từ secondary gần người dùng có thể giảm RTT tới node đọc nhưng trả dữ liệu **chưa theo kịp primary**.
- Đọc `readConcern: "linearizable"` có thể cần phối hợp để xác minh tính mới nhất, tăng latency hoặc không hoàn thành nếu điều kiện quorum không đáp ứng.
- Đọc snapshot nhiều document có thể cho một trạng thái nhất quán phục vụ báo cáo nhưng phải quản lý tuổi snapshot, tài nguyên và giới hạn transaction.

Vì vậy, câu hỏi tốt hơn “MongoDB thiên về consistency hay latency?” là:

> Với thao tác cụ thể này, chúng ta yêu cầu điều gì được bảo đảm, cần chờ những node nào, và điều gì xảy ra khi điều kiện đó không thể đạt được?

## 5. Quorum bầu cử và số bản sao dữ liệu

MongoDB replica set dùng phiếu của các thành viên voting để xác định primary hợp lệ.

Nếu có `V` voting members:

\[
\text{Election majority} = \left\lfloor \frac{V}{2} \right\rfloor + 1
\]

Ví dụ:

| Voting members | Phiếu cần cho election majority | Số phiếu có thể mất mà vẫn còn quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

Bảng trên chỉ nói về **số phiếu**, chưa bảo đảm có một candidate primary hợp lệ hoặc đủ data-bearing replicas để đáp ứng writes.

### 5.1. Ba data-bearing nodes (PSS)

```text
P: primary   vote=1   data=yes
S: secondary vote=1   data=yes
S: secondary vote=1   data=yes

V=3; Q=2
```

Nếu mất một secondary, còn primary và secondary kia:

- Đủ hai phiếu bầu;
- Còn hai bản sao dữ liệu;
- `w: "majority"` thường vẫn có thể hoàn tất khi hai member còn lại khỏe và replication theo kịp.

Nếu primary mất, hai secondary còn lại có thể bầu primary mới nếu các điều kiện election được đáp ứng. Quá trình chuyển vai trò có thể tạo một khoảng tạm thời **không ghi được**.

### 5.2. Hai data-bearing nodes (PS)

```text
P: vote=1, data=yes
S: vote=1, data=yes

V=2; Q=2
```

Mất một node sẽ làm node còn lại không đủ phiếu. Hai bản sao dữ liệu không tự bảo đảm failover khi không có quorum. Việc thêm một secondary không bỏ phiếu cũng không giải quyết việc thiếu phiếu.

### 5.3. Primary–Secondary–Arbiter (PSA)

```text
P: vote=1, data=yes
S: vote=1, data=yes
A: vote=1, data=no

V=3; Q=2
```

Nếu S mất, P và A còn **hai phiếu** nên có thể vẫn giữ primary hợp lệ. Nhưng chỉ còn **một bản sao dữ liệu**.

Điều quan trọng:

- **Arbiter bỏ phiếu**, không lưu document/oplog như secondary.
- Arbiter **không xác nhận một ghi đã được sao chép sang bản sao dữ liệu**.
- Một PSA có thể còn **election quorum** nhưng **không đáp ứng được các ghi cần `w: "majority"`** khi secondary data-bearing không khả dụng.

Đây là lý do đếm ba thành viên không đủ để đánh giá durability. Cần đếm cả **data-bearing voting members** và xem quy tắc majority write concern của topology.

### 5.4. Cùng ba phiếu, khả năng ghi majority khác nhau

| Mất một thành viên | PSS (ba data-bearing) | PSA (hai data-bearing + arbiter) |
|---|---|---|
| Mất secondary | Còn hai data-bearing, có thể ghi majority | Chỉ còn primary và arbiter, majority write không được xác nhận đủ |
| Mất primary | Hai data-bearing còn lại có thể bầu mới | Secondary + arbiter có thể bầu mới, nhưng chỉ còn một bản sao dữ liệu |
| Mất arbiter | Không áp dụng | P + S còn quorum và hai bản sao dữ liệu |

**Có primary** và **có khả năng commit majority** là hai trạng thái cần giám sát riêng.

## 6. Write concern: ACK ở cấp nào?

Write concern chỉ định mức xác nhận mà ứng dụng yêu cầu cho một thao tác ghi.

### 6.1. `w: 0`, `w: 1`, `w: "majority"`

| Write concern | Ý nghĩa thực tế | Đánh đổi |
|---|---|---|
| `w: 0` | Không chờ acknowledgement ở mức ghi thông thường | Ít thông tin về kết quả; khó xử lý lỗi/độ bền |
| `w: 1` | Chờ primary xác nhận ở mức được cấu hình | Có thể nhanh hơn, nhưng ghi chưa replicate có thể rollback khi failover |
| `w: "majority"` | Chờ đủ data-bearing acknowledgements theo majority write concern | Tăng độ bền trước một số sự cố; có thể chậm hoặc không hoàn tất khi replication/quorum suy giảm |
| `w: <number>` | Chờ số thành viên theo mức chỉ định | Phải hiểu số node data-bearing và topology; yêu cầu vượt khả năng có thể timeout |

Không nên dùng `w: 0` cho thao tác như tạo đơn hàng hoặc thanh toán chỉ để tối ưu một vài mili-giây; ứng dụng cần khả năng biết thao tác thành công/thất bại và xử lý retry đúng ngữ nghĩa.

### 6.2. Ví dụ ghi `w: 1`

```javascript
db.orders.insertOne(
  {
    _id: "ORDER-101",
    status: "NEW",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: 1
    }
  }
);
```

Khi nhận ACK, client biết primary đã chấp nhận thao tác theo write concern đó. Nhưng ACK **không có nghĩa** các secondary đã nhận bản ghi.

Nếu primary mất trước khi một ghi `w: 1` được replicate tới tập member cần thiết, ghi đó có thể bị rollback trong một số kịch bản failover. Đó là rủi ro phải cân nhắc theo **RPO** (Recovery Point Objective).

### 6.3. Ví dụ ghi `w: "majority"`

```javascript
db.orders.insertOne(
  {
    _id: "ORDER-102",
    status: "NEW",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

`wtimeout` tính bằng milliseconds, giới hạn thời gian chờ **đạt yêu cầu write concern** theo điều kiện của thao tác; nó không có nghĩa mọi giai đoạn từ client tới server đều bị giới hạn đúng 5 giây.

Nếu một secondary cần thiết không theo kịp hoặc mất mạng, write có thể:

- Đã được primary áp dụng;
- Chưa được đủ member xác nhận;
- Trả lỗi write concern timeout.

**Đừng suy từ `wtimeout` rằng document chắc chắn không tồn tại.** Có thể thao tác đã được áp dụng nhưng chưa đáp ứng yêu cầu xác nhận. Ứng dụng nên có định danh request ổn định và chiến lược retry/đối soát để không tạo giao dịch trùng.

### 6.4. Journal không thay thế replication

Một cấu hình:

```javascript
{
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  }
}
```

`j: true` liên quan việc chờ journal theo các quy tắc write concern/replica set tương ứng. Nó không tạo thêm bản sao dữ liệu, và một majority acknowledgement cũng không có nghĩa ứng dụng đã có backup độc lập.

Khi đánh giá durability, cần xét:

- Số member lưu dữ liệu;
- Mức write acknowledgement;
- Journaling/storage engine;
- Khả năng rollback;
- Fault domains;
- Backup và disaster recovery.

### 6.5. Không đoán default write concern

Driver/cluster có default write concern phụ thuộc cấu hình và phiên bản server. Với topology có arbiter, implicit default có thể không giống kỳ vọng.

Có thể kiểm tra default trong deployment phù hợp:

```javascript
db.adminCommand({ getDefaultRWConcern: 1 });
```

Với dữ liệu quan trọng, nên chỉ rõ write concern trong kiến trúc/driver hoặc chính sách cấp cụm, và kiểm tra **giá trị thực tế**. Đừng khẳng định “mọi MongoDB mặc định đều ghi majority” trong mọi topology.

## 7. Read concern: đọc ở mức nhất quán nào?

**Read concern** mô tả những bảo đảm của dữ liệu mà một read có thể nhìn thấy. Nó khác với read preference — lựa chọn node đọc.

| Read concern | Đặc trưng | Lưu ý quan trọng |
|---|---|---|
| `"local"` | Có thể đọc dữ liệu local đang hiện diện ở node | Dữ liệu chưa majority committed có thể bị rollback |
| `"available"` | Mức phù hợp cho một số kịch bản ưu tiên khả dụng, nhất là sharded reads | Có hạn chế riêng; trong sharded cluster có thể thấy orphaned documents |
| `"majority"` | Chỉ đọc dữ liệu đã majority committed theo cơ chế hỗ trợ | **Không** mặc nhiên là mới nhất trên mọi secondary hoặc linearizable |
| `"linearizable"` | Đọc với bảo đảm tuyến tính hóa trong phạm vi hỗ trợ | Yêu cầu đọc từ primary, có chi phí và rủi ro không hoàn tất khi quorum lỗi |
| `"snapshot"` | Đọc theo một snapshot nhất quán trong phạm vi được hỗ trợ | Không đồng nghĩa snapshot là mới nhất; có giới hạn thời gian/tài nguyên |

### 7.1. `readConcern: "local"`

Một secondary có thể đã áp dụng bản ghi mới nhưng bản ghi đó chưa đạt majority commit. Read local có thể nhìn thấy bản ghi này. Nếu sau đó xảy ra rollback, bản ghi có thể không còn.

Vì vậy, read local **không đủ** khi ứng dụng yêu cầu “một khi thấy dữ liệu thì dữ liệu đó phải thuộc lịch sử majority-committed”. Với feed hoặc analytics chấp nhận dữ liệu có thể thay đổi, local đôi khi là lựa chọn hợp lý; với thanh toán, cần yêu cầu rõ hơn.

### 7.2. `readConcern: "majority"`

Majority read dựa trên các bảo đảm về majority-committed data, giúp tránh đọc những ghi chưa đủ mức commit mà có thể bị rollback theo cơ chế replication bình thường.

Nhưng có khác biệt quan trọng:

```text
T1: P nhận và majority-commit giá trị version=10.
T2: Secondary S1 đã apply version=10.
T3: Secondary S2 mới apply đến version=9.
T4: Client đọc S2 với readConcern="majority".
```

Nếu S2 vẫn có một majority-committed view ở version 9, nó có thể trả **phiên bản cũ hơn** giá trị mới nhất ở primary. `"majority"` không tự ép một secondary đang lag phải trả ngay state mới nhất tại thời điểm real-time của request.

Kết luận:

> **Majority read bảo vệ thuộc tính của dữ liệu đọc, không tự bảo đảm dữ liệu đó là bản mới nhất toàn cluster.**

### 7.3. `readConcern: "linearizable"`

Đối với bài toán single-document quan trọng, MongoDB hỗ trợ read concern `"linearizable"` trong phạm vi và điều kiện được tài liệu quy định. Nó được dùng với **primary** và kết hợp mức ghi đủ mạnh để đạt ngữ nghĩa tuyến tính hóa trên một document.

Ví dụ một khóa trạng thái:

```javascript
{
  _id: "payment-gate",
  enabled: false
}
```

Sau khi một lệnh update majority-acknowledged đã hoàn tất, một linearizable read hợp lệ bắt đầu **sau** lệnh đó được thiết kế để quan sát trạng thái phù hợp với thứ tự thời gian thực.

Không đồng nghĩa mỗi lệnh `find()` trên secondary sẽ tuyến tính hóa. Linearizable read có điều kiện:

- Đọc từ primary;
- Phạm vi hỗ trợ chủ yếu cho **single-document read**;
- Đòi hỏi có thể xác nhận điều kiện liên quan tới majority;
- Có thể chậm hoặc chờ quá lâu khi quorum/partition bất thường;
- Nên dùng thời hạn hợp lý, ví dụ `maxTimeMS`.

Một ví dụ read command tường minh:

```javascript
db.runCommand({
  find: "systemFlags",
  filter: { _id: "payment-gate" },
  limit: 1,
  readConcern: { level: "linearizable" },
  maxTimeMS: 3000
});
```

Ví dụ yêu cầu chạy trên primary/topology hỗ trợ. Đừng dùng linearizable read cho truy vấn analytics lớn chỉ vì tên nghe “an toàn hơn”; nó được thiết kế cho những trường hợp có yêu cầu nhất quán mạnh cụ thể.

### 7.4. `readConcern: "snapshot"`

Snapshot read phục vụ tình huống cần nhiều document hoặc nhiều phép đọc thấy **một trạng thái logic nhất quán** tại một thời điểm.

Ví dụ báo cáo cần đếm đơn hàng và cộng tiền theo cùng tập dữ liệu, thay vì phép đếm chạy ở T1 còn tổng tiền chạy ở T2 sau khi hàng nghìn order đổi trạng thái.

Snapshot read có thể được sử dụng qua transaction hoặc những khả năng snapshot read ngoài transaction ở các phiên bản/topology hỗ trợ. Việc chọn cách nào phải xem thời gian chạy, giới hạn transaction, tuổi snapshot và lưu giữ lịch sử.

**Snapshot nhất quán tại một mốc không nhất thiết là snapshot mới nhất tại thời điểm client nhận phản hồi.** Không thay snapshot bằng linearizable, cũng không thay linearizable bằng snapshot trong mọi tình huống.

## 8. Read preference: đọc từ node nào?

Read preference quyết định **node được ưu tiên**:

| Read preference | Ý nghĩa khái quát |
|---|---|
| `primary` | Chỉ đọc từ primary |
| `primaryPreferred` | Ưu tiên primary, có thể chọn secondary khi điều kiện cho phép |
| `secondary` | Chỉ chọn secondary phù hợp |
| `secondaryPreferred` | Ưu tiên secondary, có thể fallback theo quy tắc chọn server |
| `nearest` | Chọn node có độ trễ mạng phù hợp, không đồng nghĩa dữ liệu mới nhất |

Read preference không biến một secondary thành bản sao đồng bộ tức thời.

Ví dụ:

```javascript
const orders = db.getCollection("orders");

orders.find(
  { customerId: "C-101" }
)
.readPref("secondaryPreferred");
```

Đây là ví dụ phong cách `mongosh`; API read preference trong Java/Spring Data/Node.js có thể được cấu hình trên client, database, collection hoặc thao tác tùy driver.

### 8.1. Secondary gần hơn chưa chắc phù hợp

Một người dùng ở khu vực gần secondary có thể nhận dữ liệu nhanh vì network RTT thấp, nhưng:

- Secondary có thể trễ oplog;
- Mức read concern không nhất thiết bảo đảm fresh state;
- Một index/query chậm vẫn chậm dù node gần;
- Nếu node chỉ có snapshot cũ, dữ liệu đọc có thể stale.

Nếu endpoint hiển thị số lượt xem có thể chấp nhận trễ vài giây, secondary read có thể hợp lý. Nếu endpoint xác nhận “đã khóa tài khoản hay chưa” với yêu cầu trạng thái mới nhất và thứ tự thời gian thực, lựa chọn node/concern phải mạnh hơn.

### 8.2. `maxStalenessSeconds` không phải chứng minh dữ liệu mới nhất

Một số driver hỗ trợ cấu hình chọn secondary theo mức staleness ước lượng. Đây là **server selection policy** với điều kiện/giới hạn riêng, không phải một giao thức tuyến tính hóa hoặc bằng chứng mọi lần đọc sẽ cách latest primary đúng không quá N giây trong mọi kiểu failure.

Muốn cam kết freshness chính xác, hãy thiết kế quy trình đo replication lag, phù hợp session/consistency và cách ứng dụng xử lý khi không đủ dữ liệu mới.

## 9. Majority không đồng nghĩa linearizable

Một hiểu lầm rất phổ biến:

> “Chỉ cần ghi `w: "majority"` và đọc `readConcern: "majority"` thì hệ thống luôn tuyến tính hóa mọi thao tác.”

Kết luận đó **quá mạnh**.

### 9.1. Majority write bảo vệ điều gì?

Giả sử PSS:

```text
P   đã ghi version=11
S1  đã ghi version=11
S2  đang ở version=10
```

Nếu P và S1 đã xác nhận theo quy tắc majority, ghi version 11 có thể được majority-acknowledged. Hệ thống có thể chịu một số sự cố node mà không mất trạng thái majority-committed theo những bảo đảm của replica set.

Tuy nhiên, S2 chưa bắt kịp. Một read từ S2 có read concern majority không tự biết rằng client đòi trạng thái latest tại P **ngay lúc đó**.

### 9.2. Khi nào cần linearizable read?

Giả sử một service quyết định có cho phép mở một “cổng thanh toán” hay không. Khi administrator đã **hoàn tất** thao tác khóa cổng bằng majority write, mọi read bắt đầu sau đó cần thấy trạng thái khóa.

Đây gần với yêu cầu **thứ tự thời gian thực**. Trên một document phù hợp, có thể dùng:

- Majority write cho state transition;
- Linearizable read từ primary để xác nhận trạng thái theo bảo đảm được hỗ trợ;
- Giới hạn thời gian đọc và xử lý lỗi khi không đáp ứng được quorum.

Nếu điều kiện không thể xác nhận trong lúc partition, thao tác đọc có thể **timeout** thay vì trả một câu trả lời cũ được giả làm mới nhất.

### 9.3. Không dùng linearizable read thay transaction nhiều document

Một query quan trọng về **một document** khác một quy trình chuyển tiền giữa hai tài khoản nằm trên hai document.

Đối với các invariant nhiều document, cần thiết kế transaction, unique constraint, mô hình dữ liệu, write concern và retry logic phù hợp. Linearizable read trên một document không tự đảm bảo rằng hai document khác đã được đọc trên cùng snapshot.

## 10. Causal consistency: giữ quan hệ nhân quả trong một session

Có những trường hợp không đòi hỏi mọi client toàn cầu thấy latest tức thì, nhưng người dùng **phải thấy kết quả của thao tác trước đó của chính mình**.

Ví dụ:

```text
T1: Người dùng đổi tên hiển thị thành "Minh".
T2: Server xác nhận thao tác ghi.
T3: Người dùng mở lại hồ sơ từ một secondary.
```

Nếu T3 đọc một secondary lag, hồ sơ có thể hiển thị tên cũ. Điều này gây trải nghiệm “vừa cập nhật xong nhưng mất thay đổi”.

MongoDB hỗ trợ **causally consistent sessions** để bảo vệ quan hệ giữa những thao tác trong cùng session khi đáp ứng các điều kiện đọc/ghi liên quan.

### 10.1. Các bảo đảm thường được nhắc tới

Trong một causally consistent session với các điều kiện phù hợp, có thể xây dựng:

- **Read-your-writes:** đọc sau ghi thấy tác động của ghi trước đó trong session;
- **Monotonic reads:** không nhìn phiên bản cũ hơn sau khi đã quan sát phiên bản mới hơn;
- **Monotonic writes:** các ghi trong session giữ thứ tự nhân quả;
- **Writes-follow-reads:** thao tác ghi sau một read có quan hệ với trạng thái đã đọc.

Một điều kiện quan trọng để có những bảo đảm causal mạnh là sử dụng **majority read concern và majority write concern** cho các thao tác liên quan, trên cùng session và theo cách driver hỗ trợ.

### 10.2. Causal consistency có thể làm tăng latency

Giả sử session đã ghi `version=12` ở primary và được majority-acknowledged. Khi read tiếp trên secondary S2:

```text
S2 mới apply đến version=11.
Session yêu cầu đọc ít nhất sau mốc nhân quả của version=12.
```

Read có thể phải **chờ S2 bắt kịp** hoặc không hoàn tất trong thời hạn đã chọn. Đây là đánh đổi latency để tránh trải nghiệm “read-your-writes bị lùi”.

Causal consistency **không tương đương** một linearizable read toàn cluster giữa mọi client không có quan hệ nhân quả.

### 10.3. Không chia sẻ một session tùy tiện giữa luồng độc lập

Các operation trong session phải được điều phối theo quy tắc của driver. Đừng dùng chung session một cách tùy tiện cho nhiều request song song hoặc nhiều người dùng độc lập, rồi kỳ vọng causal ordering sẽ tự sắp xếp.

Session còn liên quan đến lifecycle, authentication context và resource management. Trong API web, cần chủ động xác định phiên nào cần causal continuity và cách truyền/khôi phục context nếu yêu cầu trải nhiều request.

## 11. Snapshot và transaction: nhất quán nhiều thao tác

Giả sử nghiệp vụ cập nhật:

```text
orders.status = "PAID"
payments.status = "CAPTURED"
```

Nếu ghi hai collection bằng hai thao tác riêng không có transaction, client có thể nhìn thấy trạng thái “đơn hàng đã thanh toán nhưng payment chưa cập nhật” ở khoảng giữa.

MongoDB hỗ trợ **multi-document transactions** trong triển khai phù hợp. Một transaction có read concern snapshot và commit write concern phù hợp có thể cung cấp một đơn vị thao tác logic nhất quán hơn.

### 11.1. Ví dụ mongosh trong môi trường phù hợp

```javascript
const session = db.getMongo().startSession();

try {
  const sessionDb = session.getDatabase(db.getName());

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  sessionDb.orders.updateOne(
    { _id: "ORDER-201", status: "PENDING" },
    { $set: { status: "PAID" } }
  );

  sessionDb.payments.updateOne(
    { _id: "PAY-201", status: "AUTHORIZED" },
    { $set: { status: "CAPTURED" } }
  );

  session.commitTransaction();
} catch (error) {
  try {
    session.abortTransaction();
  } catch (ignored) {
    // Tình trạng transaction thực tế cần được xử lý theo lỗi nhận được.
  }
  throw error;
} finally {
  session.endSession();
}
```

Đây là ví dụ về phạm vi transaction, **không phải code xử lý retry đầy đủ**. Trong production phải kiểm tra update matched count, các điều kiện nghiệp vụ, transaction retry cho transient errors, unknown commit result và idempotency.

### 11.2. Transaction không loại bỏ mọi đánh đổi

Transaction có thể cần:

- Chờ các bước phối hợp và commit;
- Giữ tài nguyên/snapshot trong suốt transaction;
- Giải quyết write conflicts;
- Retry khi primary stepdown/partition;
- Với sharded transactions, chi phí điều phối thêm giữa nhiều shard.

Một transaction rất dài không phải giải pháp vô điều kiện cho một báo cáo chạy hàng giờ. Có thể phù hợp hơn với snapshot read có kiểm soát, materialized data hoặc thiết kế báo cáo theo kỳ.

### 11.3. Snapshot không thay thế chính sách commit

Chọn `readConcern: "snapshot"` cho transaction đọc/ghi mà không hiểu write concern ở **commit** có thể khiến kỳ vọng durability không đúng. Với transaction cần bảo đảm mạnh, phải xét đồng thời **read concern snapshot, write concern majority ở commit** và quy tắc của driver/server.

Không dùng hai chữ “ACID transaction” như một câu trả lời thay thế toàn bộ thiết kế failover và timeout.

## 12. Timeline: cùng một lỗi mạng, ba kết quả khác nhau

Xét PSS và các event theo thời gian:

```text
T0: P, S1, S2 đều khỏe.
T1: P nhận update: flag = true.
T2: S1 xác nhận update; S2 chưa kịp apply.
T3: Update được majority-acknowledged.
T4: Network partition khiến P bị cô lập.
T5: S1 + S2 tổ chức election; một node trở thành primary.
T6: Client thử đọc/ghi từ các phía.
```

### 12.1. Ghi tại T1 với `w: 1`

Nếu ghi được ACK ngay sau khi P áp dụng, rồi P bị cô lập **trước khi đủ bản sao nhận ghi**, record có thể chưa thuộc lịch sử majority committed. Nó có thể bị rollback nếu phía còn quorum bầu lịch sử không chứa thao tác đó.

**Write acknowledged at `w: 1` không phải một chứng chỉ majority durability.**

### 12.2. Ghi tại T3 với `w: "majority"`

Nếu thao tác đã được majority-acknowledged trước partition, một primary mới được bầu hợp lệ từ những data-bearing voting members có dữ liệu theo quy tắc replication/election phải bảo vệ những cam kết majority-committed trong phạm vi bảo đảm của MongoDB.

Điều này không xóa rủi ro trước các tai họa vượt mô hình: mất toàn bộ các bản sao cần thiết, hỏng storage, lỗi vận hành, xóa dữ liệu hoặc không có backup vẫn có thể dẫn tới mất dữ liệu.

### 12.3. Đọc tại T6 từ secondary đang lag

Ngay cả khi `flag=true` đã majority committed, một secondary chưa apply đến mốc đó có thể trả snapshot majority cũ hơn nếu không có yêu cầu causal/linearizable bổ sung phù hợp.

Với một endpoint cho phép eventual freshness, điều đó có thể chấp nhận. Với endpoint xác nhận quyền truy cập hoặc trạng thái khóa bảo mật, cần thiết kế khả năng từ chối/chờ thay vì trả kết luận cũ.

## 13. Ma trận phân vùng mạng theo topology

### 13.1. PSS: ba member đều chứa dữ liệu

| Tình huống | Election | Ghi `w: 1` | Ghi `w: "majority"` | Đọc từ secondary |
|---|---|---|---|---|
| Cả P, S1, S2 khỏe | Có primary | Có khi primary sẵn sàng | Có khi replication đủ khỏe | Có thể, tùy preference/concern |
| Một secondary mất | P + secondary còn lại đủ quorum | Có | Thường có | Có từ secondary còn lại, tùy trạng thái |
| Primary mất, S1 + S2 còn | Có thể elect primary mới | Gián đoạn tới khi có primary mới | Gián đoạn rồi có thể tiếp tục | Có thể đọc một số dữ liệu trước khi election xong |
| P cô lập, S1 + S2 liên lạc | P phía thiểu số phải step down; phía hai phiếu có thể elect | Phía P không ghi hợp lệ khi mất quorum; phía majority sau election có thể ghi | Phía majority sau election có thể ghi nếu hai bản sao dữ liệu khỏe | Có thể đọc theo giới hạn đã chọn |
| Cả ba bị cô lập thành 1 + 1 + 1 | Không phía nào có hai phiếu | Không có primary hợp lệ khi mất quorum được phát hiện | Không | Một số node có thể phục vụ read yếu hơn tùy role/trạng thái |

Các từ “có thể” là có chủ đích: tình trạng primary, freshness, candidate eligibility, heartbeat timeout, replication lag và server selection đều ảnh hưởng kết quả thực tế.

### 13.2. PSA: hai member data-bearing và một arbiter

| Node còn hoạt động/kết nối | Election quorum | Bản sao dữ liệu khả dụng | Majority write mới |
|---|---|---|---|
| P + S + A | 3/3 | 2 | Có thể đáp ứng |
| P + S | 2/3 | 2 | Có thể đáp ứng |
| P + A | 2/3 | 1 | **Không đủ acknowledgements dữ liệu** |
| S + A, P mất | 2/3 | 1 | **Không đủ acknowledgements dữ liệu**, dù S có thể được bầu |
| Chỉ P hoặc chỉ S | 1/3 | 1 | Không có quorum primary hợp lệ |
| Chỉ A | 1/3 | 0 | Không thể nhận ghi |

Điểm đau của PSA là **election availability và majority-write availability có thể khác nhau**. Hệ thống có primary nhưng các API bắt buộc `w: "majority"` vẫn có thể timeout.

### 13.3. Năm voting data-bearing members

```text
P + S + S + S + S
V = 5
Q = 3
```

Về số phiếu, hệ thống có thể chịu hai voting members không khả dụng mà vẫn còn ba phiếu. Nhưng:

- Phải còn một candidate đủ điều kiện;
- Phải còn đủ data-bearing members có thể xác nhận majority write;
- Network phải tạo thành phân vùng có thể giao tiếp;
- Phần còn lại phải đủ capacity để phục vụ tải.

Năm member không có nghĩa “mọi hai lỗi tùy ý đều an toàn” nếu hai lỗi thuộc cùng failure domain kéo theo lỗi thứ ba, hoặc các member còn lại không đạt điều kiện vận hành.

## 14. Đánh đổi ở hệ thống nhiều vùng địa lý

Giả sử ứng dụng có người dùng tại Hà Nội, Singapore và Frankfurt. Mục tiêu:

- Ghi đơn hàng không mất sau failover thông thường;
- Đọc danh mục nhanh ở gần người dùng;
- Chịu mất một vùng mà vẫn còn dịch vụ;
- Giảm độ trễ end-to-end.

Một cách bố trí PSS:

```text
Region A: Primary + app ghi chính
Region B: Secondary
Region C: Secondary
```

### 14.1. Ghi majority có thể phụ thuộc RTT xuyên vùng

Để ghi đạt majority ở PSS, primary cần acknowledgements từ **ít nhất một secondary** ngoài chính nó theo quy tắc majority. Nếu các secondary nằm ở xa, latency ghi có thể phụ thuộc RTT tới vùng đáp ứng đủ mức xác nhận.

Không cần chờ **mọi** secondary trong một PSS majority write, nhưng cần đủ số bản sao. Nếu secondary gần nhất chậm/mất, secondary xa có thể trở thành thành viên cần thiết, làm latency tăng.

Ví dụ minh họa, **không phải số đo thực tế**:

```text
Primary apply/journal:       3 ms
Secondary gần ACK:           8 ms
Secondary xa ACK:           70 ms

Ở trạng thái khỏe:
  majority write có thể hoàn tất sau ACK của secondary gần.

Khi secondary gần mất:
  majority write có thể phải chờ secondary xa.
```

Thời gian thực tế phụ thuộc network RTT, storage, replication scheduling, transaction, lưu lượng và phương thức journaling; không nên tính cứng bằng phép cộng vài con số lý thuyết mà bỏ qua xử lý song song.

### 14.2. Read secondary ở gần người dùng

Đọc từ secondary gần người dùng có thể giảm network latency và giảm tải primary. Nhưng nếu secondary lag, người dùng có thể thấy:

```text
Primary:   order.status = "PAID"
Secondary: order.status = "PENDING"
```

Một UX phù hợp có thể là:

- Trang danh sách/lịch sử cho phép refresh và biểu thị thời điểm đồng bộ;
- Màn hình xác nhận giao dịch đọc từ primary/qua session causal khi cần;
- Những thao tác quyết định trạng thái cuối phải có một nguồn xác nhận mạnh;
- Nếu không thể đáp ứng freshness, trả trạng thái “Đang đồng bộ” thay vì khẳng định sai.

### 14.3. Failure domain quan trọng hơn số host

Ba mongod cùng đặt trên một rack không cung cấp mức chịu lỗi điện/rack như ba mongod ở ba failure domains độc lập.

Nhưng trải node qua ba vùng tăng network RTT và độ phức tạp vận hành. Cần cân bằng **RPO, RTO, p95 latency, độ trễ replication, chi phí truyền dữ liệu và khả năng failover**.

## 15. Latency budget cho một thao tác

Để thiết kế SLA, nên chia thời gian theo loại công việc thay vì chỉ quan sát một số latency tổng.

Ví dụ đơn hàng:

```text
Client request timeout:        3000 ms
  ├─ Server selection / connect
  ├─ Ghi primary
  ├─ Chờ majority replication
  └─ Truyền response
```

Trong trạng thái bình thường, thao tác có thể đáp ứng SLA. Nhưng khi secondary cần thiết bị chậm:

```text
Ứng dụng yêu cầu w:majority
        ↓
Primary đã apply
        ↓
Secondary không ACK kịp
        ↓
wtimeout hoặc client timeout
```

Có hai loại timeout cần phân biệt:

- **`wtimeout`:** chờ mức write concern;
- **Timeout ở driver/client/network:** có thể xảy ra ở server selection, connection, read/write network hoặc các giai đoạn khác.

Thêm `wtimeout` **không biến một partition thành khả dụng**. Nó chỉ giúp thao tác không chờ vô hạn ở một phần của đường xử lý, để ứng dụng có thể đưa ra hành vi phù hợp.

### 15.1. Timeout ngắn không tạo consistency mạnh hơn

Đặt `wtimeout: 100` ms thay vì 5000 ms không tự làm dữ liệu an toàn hơn. Nó có thể khiến số lỗi timeout tăng trong mạng liên vùng. Đặt timeout quá dài cũng có thể vượt SLA của HTTP request, khiến client bỏ cuộc trong khi server vẫn xử lý.

Nên phân bổ budget cho:

1. Server selection;
2. Thực thi query/ghi primary;
3. Replication acknowledgement;
4. Retry nếu được phép;
5. Deadline tổng của request.

Cần kiểm tra sự tương thích giữa các timeout của driver, API gateway, load balancer và upstream service.

### 15.2. Đừng dùng latency trung bình để đại diện tình huống lỗi

Một môi trường có p50 ghi 12 ms nhưng p99 900 ms khi network chập chờn có thể ảnh hưởng nghiêm trọng tới checkout. Nên báo:

- p50, p95, p99;
- Tỷ lệ timeout;
- Tỷ lệ retry;
- Tần suất election;
- Secondary replication lag;
- Số request không đạt mức concern yêu cầu;
- Thời gian không có primary;
- Hành vi khi một vùng lỗi.

## 16. Phân biệt “trả dữ liệu cũ” với “ghi không bền”

Hai rủi ro thường bị gộp chung thành “eventual consistency”:

### 16.1. Stale read

Read trả phiên bản cũ:

```text
Primary:   version 12
Secondary: version 11

Read secondary → version 11
```

Nếu version 12 đã majority committed, read từ secondary chỉ là **chưa bắt kịp**, không đồng nghĩa version 12 bị mất.

Ứng dụng có thể khắc phục bằng causal session, chọn primary, chờ secondary theo mốc nhân quả hoặc hiển thị trạng thái đang cập nhật.

### 16.2. Rollback của ghi chưa majority-committed

Ghi `w: 1` đã được ACK trên primary nhưng chưa replicate đủ, sau đó primary mất và lịch sử mới không chứa ghi. Ghi có thể bị rollback. Đây là vấn đề **durability/commit**, không đơn giản là secondary chưa cập nhật giao diện.

Không thể sửa rollback bằng cách “refresh lại trang” nếu dữ liệu thực sự không còn trong lịch sử đã được chọn; ứng dụng cần xử lý theo chính sách nghiệp vụ.

### 16.3. Dữ liệu conflict trong mô hình multi-writer bên ngoài

Replica set MongoDB sử dụng một primary hợp lệ theo quorum trong điều kiện hoạt động chuẩn. Nếu ứng dụng tự tạo hai cơ sở dữ liệu độc lập cho hai vùng và cho phép mỗi vùng ghi riêng khi partition, đó trở thành **một kiến trúc multi-writer do ứng dụng thiết kế**, không phải khả năng tự có của một MongoDB replica set duy nhất.

Khi đó phải định nghĩa conflict resolution, event ordering, merge, duplicate handling và luật nghiệp vụ. Không thể dùng `w: 1` trên hai cluster độc lập rồi mong MongoDB tự hợp nhất mọi giao dịch một cách đúng đắn.

## 17. Thiết kế theo mức bảo đảm của từng nghiệp vụ

Không phải mọi dữ liệu đều cần linearizable read.

| Nghiệp vụ | Mức bảo đảm thường cân nhắc | Đánh đổi |
|---|---|---|
| Số lượt xem sản phẩm | Có thể chấp nhận đọc trễ và cập nhật sau | Ưu tiên latency/throughput, có thể stale |
| Danh sách bài viết công khai | Secondary read hoặc cache với TTL phù hợp | Chấp nhận item xuất hiện muộn |
| Hồ sơ vừa được chính người dùng sửa | Causal session hoặc đọc primary theo contract | Có thể chờ hoặc tăng latency |
| Trạng thái khóa tính năng quan trọng | Majority writes; linearizable single-doc read khi thực sự cần | Có thể fail/timeout khi partition |
| Đặt hàng cần chống trùng | Majority write + unique business key + retry/idempotency | Độ trễ ghi, xử lý lỗi phức tạp hơn |
| Trừ kho có điều kiện | Atomic single-document update với predicate, write concern phù hợp | Có thể từ chối khi không còn điều kiện đảm bảo |
| Chuyển tiền nhiều document | Transaction và chiến lược commit/retry đúng | Tốn phối hợp, giảm availability khi lỗi |
| Báo cáo tài chính kỳ chốt | Snapshot/materialized dataset bất biến | Độ trễ xuất báo cáo và chi phí lưu snapshot |
| Dashboard tổng hợp gần thời gian thực | Cache, materialized summary hoặc event processing | Có độ trễ đồng bộ được công bố |

Bảng là gợi ý thiết kế. Quyết định cuối phụ thuộc ràng buộc pháp lý, độ nhạy dữ liệu, mô hình failover và yêu cầu chính xác của từng sản phẩm.

### 17.1. Ưu tiên hợp đồng theo endpoint

Hai endpoint cùng đọc collection `orders` có thể khác yêu cầu:

```text
GET /orders?status=PAID
  Cho phép danh sách chậm cập nhật vài giây.

GET /orders/{id}/confirmation
  Chỉ hiển thị "đã thanh toán" sau trạng thái được xác nhận.
```

Nếu dùng chung một cấu hình read preference/concern cho mọi endpoint mà không cân nhắc nghiệp vụ, hệ thống có thể quá chậm ở nơi không cần thiết hoặc quá yếu ở chỗ quan trọng.

## 18. Atomic single-document update và tính nhất quán nghiệp vụ

Một số invariant có thể được bảo vệ trực tiếp bằng **atomic update trên một document** thay vì transaction nhiều document.

Ví dụ giữ tồn kho không âm:

```javascript
db.inventory.updateOne(
  {
    _id: "SKU-001",
    available: { $gte: 2 }
  },
  {
    $inc: { available: -2 }
  },
  {
    writeConcern: { w: "majority", wtimeout: 5000 }
  }
);
```

Ý nghĩa:

1. Điều kiện kiểm tra `available >= 2`;
2. Nếu khớp, cập nhật trừ 2 trong một thao tác atomic trên document;
3. Write concern yêu cầu mức xác nhận cần thiết.

Điều này tránh pattern nguy hiểm:

```text
Read available = 2
Hai client cùng quyết định mua 2
Cả hai ghi trừ 2 theo các bước không nguyên tử
```

Tuy nhiên:

- Atomicity của thao tác document không đồng nghĩa ghi đã majority committed nếu chỉ ACK `w: 1`.
- `matchedCount = 0` có thể nghĩa là không đủ tồn kho, không nên retry vô hạn.
- Write concern timeout có thể tạo kết quả **không chắc chắn**; nếu client gửi lại `$inc` mà không có idempotency, có thể trừ kho hai lần.
- Nếu cần phối hợp inventory và order ở hai document, phải thiết kế transaction hoặc saga phù hợp.

### 18.1. Idempotency key giúp xử lý uncertainty

Ví dụ một lệnh tạo đơn hàng có ID nghiệp vụ cố định:

```javascript
db.orders.updateOne(
  { _id: "ORDER-CLIENT-REQUEST-9931" },
  {
    $setOnInsert: {
      customerId: "C-101",
      status: "NEW",
      createdAt: new Date()
    }
  },
  {
    upsert: true,
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

Nếu cùng request được retry, `_id` ổn định giúp giảm nguy cơ tạo hai đơn hàng từ cùng một yêu cầu. Nhưng phải kiểm tra tính tương đương payload, quyền truy cập, xung đột update và khả năng trùng thao tác ở các bước downstream; `_id` cố định chỉ là một phần của idempotency.

Không tự cho rằng retryable writes của driver thay thế hoàn toàn **idempotency nghiệp vụ** cho mọi workflow đa thao tác.

## 19. Không tự hạ consistency khi gặp partition

Một phương án phản xạ:

```text
Khi majority write timeout:
  đổi toàn hệ thống sang w:1
  cho phép tiếp tục xử lý mọi giao dịch
```

Điều này có thể phục hồi một phần write availability **nếu vẫn còn một primary hợp lệ** và chỉ thiếu acknowledgements dữ liệu. Nhưng nó cũng:

- Giảm bảo đảm durability cho các ghi mới;
- Có thể làm tăng rủi ro rollback/lost acknowledged writes;
- Không giúp gì khi không còn primary có quorum;
- Thay đổi hợp đồng ghi trong lúc người dùng không biết;
- Có thể ảnh hưởng các transaction và điều kiện nghiệp vụ.

Vì vậy, không tự hạ write concern một cách âm thầm cho giao dịch quan trọng.

### 19.1. Chế độ suy giảm (degraded mode) có hợp đồng rõ

Một số hệ thống có thể hỗ trợ:

- **Chỉ đọc:** tạm khóa thao tác thay đổi dữ liệu khi không đạt mức ghi yêu cầu;
- **Đọc cache:** hiển thị dữ liệu cũ với thời gian cập nhật cuối;
- **Nhận yêu cầu nhưng chưa cam kết:** đưa yêu cầu vào hàng đợi bền vững độc lập nếu kiến trúc đã được thiết kế, trả trạng thái `PENDING` chứ không báo “Đã thanh toán”;
- **Từ chối nhanh:** trả lỗi service unavailable/retryable để tránh giữ HTTP connection vô hạn;
- **Giảm phạm vi tính năng:** cho đọc catalog nhưng tạm dừng checkout.

Một hàng đợi nhận yêu cầu **cũng cần phân tích độ bền và phân vùng của chính nó**. Không thể chuyển sang queue không có durability rồi coi như bài toán đã được giải quyết.

### 19.2. Khi nào fail closed?

Với các thao tác như khóa/mở quyền, chuyển tiền, trừ tồn kho có cam kết hoặc đảm bảo uniqueness trên toàn hệ thống, câu trả lời “không thể xác minh trạng thái mới nhất” có thể phải dẫn đến **từ chối/chờ**, thay vì trả một quyết định tích cực dựa trên stale read.

Đây là chính sách an toàn nghiệp vụ, không phải một cài đặt read concern duy nhất thay thế mọi logic.

## 20. Ví dụ `mongosh`: so sánh concern bằng lệnh tường minh

Các lệnh dưới đây có thể được thực hiện trên replica set thử nghiệm với quyền và phiên bản phù hợp. Chúng không cần gây network partition để hiểu sự khác biệt của cấu hình.

### 20.1. Đọc topology và trạng thái

```javascript
rs.conf();
rs.status();
```

Quan sát:

- Primary hiện tại;
- Secondary khỏe và replication lag;
- Các voting members và arbiter nếu có;
- Election history, heartbeat messages;
- Có đủ candidate primary và quorum không.

### 20.2. Ghi với majority concern

```javascript
db.runCommand({
  insert: "orders",
  documents: [
    {
      _id: "O-243-A",
      customerId: "C-101",
      status: "CREATED",
      createdAt: new Date()
    }
  ],
  writeConcern: {
    w: "majority",
    wtimeout: 5000
  }
});
```

Trong điều kiện khỏe mạnh, command có thể trả thành công sau khi ghi đạt concern yêu cầu. Khi replication bị gián đoạn, cần xem **write concern error**, error labels và kết quả lệnh; không suy rằng timeout tức là chưa từng có ghi.

### 20.3. Đọc với `majority`

```javascript
db.runCommand({
  find: "orders",
  filter: { _id: "O-243-A" },
  limit: 1,
  readConcern: { level: "majority" },
  maxTimeMS: 5000
});
```

Read concern majority yêu cầu dữ liệu đã đạt mức majority commit theo cơ chế hỗ trợ. Nó **không tạo bảo đảm tuyến tính hóa cho mọi client** chỉ vì đang đọc primary/secondary.

### 20.4. Đọc với `linearizable`

```javascript
db.runCommand({
  find: "orders",
  filter: { _id: "O-243-A" },
  limit: 1,
  readConcern: { level: "linearizable" },
  maxTimeMS: 5000
});
```

Lệnh này cần được gửi tới primary, dùng cho single-document read phù hợp. Nếu quorum không đáp ứng, nó có thể thất bại thay vì trả dữ liệu cũ. Không đo latency bằng một lần chạy duy nhất và không chạy benchmark gây tải trên primary production.

### 20.5. Kiểm tra default concern

```javascript
db.adminCommand({ getDefaultRWConcern: 1 });
```

Cần xác định cấu hình implicit/default của deployment và chính sách per-operation; đặc biệt chú ý topology có arbiter.

## 21. Java MongoDB Driver: cấu hình theo hợp đồng

Ví dụ Java Sync Driver dùng collection view với mức đọc/ghi rõ ràng:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

MongoDatabase database = mongoClient.getDatabase("app");

MongoCollection<Document> orders = database
    .getCollection("orders")
    .withReadPreference(ReadPreference.primary())
    .withReadConcern(ReadConcern.MAJORITY)
    .withWriteConcern(
        WriteConcern.MAJORITY.withWTimeout(5, TimeUnit.SECONDS)
    );

orders.insertOne(new Document("_id", "O-243-B")
    .append("status", "CREATED")
    .append("customerId", "C-102"));

Document order = orders.find(
    new Document("_id", "O-243-B")
).first();

System.out.println(order);
```

Mục tiêu là thể hiện **cấu hình theo collection và thao tác**. Trong ứng dụng thật cần quản lý MongoClient lifecycle, authentication, exception handling, retry và mapping DTO; không phải mọi thao tác đọc cần cùng mức concern.

### 21.1. Linearizable read cho một collection view riêng

Nếu có API cần kiểm tra một document trạng thái quan trọng:

```java
MongoCollection<Document> flags = database
    .getCollection("systemFlags")
    .withReadPreference(ReadPreference.primary())
    .withReadConcern(ReadConcern.LINEARIZABLE);
```

Ứng dụng vẫn cần giới hạn thời gian phù hợp ở driver/request và xử lý exception khi không thể đáp ứng read concern. Đừng tự áp dụng `ReadConcern.LINEARIZABLE` cho mọi truy vấn analytics hoặc đọc trên secondary.

### 21.2. Causal session trong Java

Ví dụ khái niệm:

```java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

ClientSessionOptions options = ClientSessionOptions.builder()
    .causallyConsistent(true)
    .build();

MongoCollection<Document> profiles = database
    .getCollection("profiles")
    .withReadPreference(ReadPreference.secondaryPreferred())
    .withReadConcern(ReadConcern.MAJORITY)
    .withWriteConcern(WriteConcern.MAJORITY);

try (ClientSession session = mongoClient.startSession(options)) {
    profiles.updateOne(
        session,
        new Document("_id", "USER-101"),
        new Document("$set",
            new Document("displayName", "Minh"))
    );

    Document profile = profiles.find(
        session,
        new Document("_id", "USER-101")
    ).first();

    System.out.println(profile);
}
```

Ví dụ thể hiện cùng một session được dùng cho update và read, với majority write/read concerns. Khi read từ secondary chưa bắt kịp mốc nhân quả, việc chờ hoặc lỗi do timeout là một phần của đánh đổi.

Cần kiểm tra driver/server version, context phân tán qua request, cách thực thi thao tác theo thứ tự và timeout thực tế. Causal session không phải công cụ dùng chung một đối tượng cho nhiều HTTP request song song mà không có kiểm soát.

## 22. Thí nghiệm phân vùng mạng: chỉ trong staging được kiểm soát

Một bài thực hành về CAP/PACELC đáng giá hơn khi đo hành vi của ứng dụng **trong điều kiện lỗi có chủ đích**. Tuy nhiên, không tự cắt mạng, tắt mongod hay ép election trên production.

### 22.1. Thiết lập thí nghiệm

Môi trường:

```text
Replica set thử nghiệm: PSS
P:  mongo-a
S1: mongo-b
S2: mongo-c

Client 1: dùng primary + w:majority
Client 2: dùng secondaryPreferred + readConcern:majority
Client 3: dùng primary + readConcern:linearizable
```

Trước test, tạo một document có version tăng:

```javascript
db.consistencyLab.updateOne(
  { _id: "counter-1" },
  {
    $setOnInsert: {
      version: 0,
      createdAt: new Date()
    }
  },
  {
    upsert: true,
    writeConcern: { w: "majority", wtimeout: 5000 }
  }
);
```

Lần cập nhật:

```javascript
db.consistencyLab.updateOne(
  { _id: "counter-1" },
  { $inc: { version: 1 } },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

Để kết luận về version được ghi, cần xác nhận đúng một writer hoặc có operation IDs; không tự dùng `$inc` retry thủ công nhiều lần khi kết quả trước chưa rõ vì có thể tăng hai lần.

### 22.2. Những pha cần đo

1. **Khỏe mạnh:** ghi và đọc với các concern, ghi p50/p95 latency.
2. **Một secondary trễ:** quan sát `replication lag`, majority write latency và khả năng đọc stale.
3. **Primary mất:** quan sát khoảng không có primary, election và lỗi phía client.
4. **Một partition 1/2:** xác định phía nào có quorum, node nào step down.
5. **Khôi phục kết nối:** quan sát secondary catch-up và ứng dụng phục hồi.
6. **So sánh read preference:** thử đọc primary so với secondary, ghi rõ ngữ nghĩa nhất quán đã chọn.

### 22.3. Các metric cần thu

| Metric | Lý do |
|---|---|
| Primary election duration | Ảnh hưởng write availability |
| Time without writable primary | Đo RTO phần ghi |
| Majority write p50/p95/p99 | Chi phí chờ replication |
| `wtimeout` rate | Mức không đáp ứng write concern |
| Read error/timeout rate | Khả năng đọc với concern mạnh |
| Secondary replication lag | Khả năng stale reads |
| Retry counts | Chi phí bổ sung và khả năng trùng |
| Data rollback events | Rủi ro dữ liệu ghi chưa majority committed |
| Version observed by reader | Kiểm tra causal/freshness |
| CPU/network/storage | Xác định lỗi tài nguyên hay partition |

Không thể từ một lần demo kết luận mọi phiên bản MongoDB và mọi multi-region topology có cùng latency. Cần ghi cấu hình, phiên bản, write/read concerns, failure injection method và trạng thái nền.

## 23. Các mô hình kết hợp để dung hòa hiệu năng và độ tin cậy

### 23.1. CQRS / tách luồng đọc và ghi

Một hệ thống có thể:

```text
Command / Write API
   └── MongoDB primary, majority write

Query / Read API
   ├── MongoDB secondary
   ├── materialized view
   └── cache
```

Ưu điểm: đọc scale độc lập và có thể trả nhanh.

Đánh đổi: read model/cache **có độ trễ đồng bộ**; không được hiển thị nó như cùng trạng thái ngay lập tức của transaction vừa commit. Có thể dùng version, “lastUpdatedAt”, refresh hoặc truy vấn primary cho các màn hình cần xác nhận.

### 23.2. Outbox pattern

Khi cần tạo order và phát event downstream, có thể ghi order và outbox record trong transaction phù hợp, commit với write concern cần thiết; worker sau đó đọc outbox và gửi event.

Cách này giảm nguy cơ “order đã tạo nhưng message gửi ra bị mất” nếu được thiết kế đúng. Tuy nhiên:

- Outbox vẫn phụ thuộc durability của MongoDB commit;
- Worker/event consumer cần idempotency;
- Khi replica set mất quorum, transaction/commit có thể không hoàn tất;
- Hệ thống không được coi event delivery là exactly-once chỉ nhờ có một outbox.

### 23.3. Bộ nhớ đệm và dữ liệu cũ có nhãn

Nếu mạng bị partition nhưng người dùng vẫn cần xem danh mục, có thể phục vụ từ cache:

```javascript
{
  items: [
    { sku: "SKU-101", name: "Bàn phím" }
  ],
  dataTimestamp: "2026-11-14T08:00:00Z",
  freshness: "STALE",
  actionsAllowed: ["VIEW"]
}
```

Đây là response **do ứng dụng thiết kế**, không phải metadata tự động của MongoDB. Nó rõ ràng hơn trả danh sách cache như thể luôn mới nhất.

Với thao tác có tác động tài chính, ứng dụng có thể phải cấm hành động cho tới khi nhận được trạng thái từ nguồn đáng tin cậy.

## 24. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Có ba mongod nghĩa là chịu được một lỗi và vẫn majority-write.” | Cần xem ba node có chứa dữ liệu không; PSA khác PSS. |
| “Arbiter giúp xác nhận dữ liệu đã sao chép.” | Arbiter chỉ có phiếu, không lưu bản sao dữ liệu. |
| “Primary vẫn sống thì ghi nào cũng được.” | Mất quorum có thể làm primary step down; write concern mạnh có thể không được đáp ứng. |
| “`w: 1` và `w: "majority"` khác nhau chỉ ở tốc độ.” | Khác cả durability và rollback risk. |
| “`wtimeout` nghĩa là insert thất bại hoàn toàn.” | Có thể primary đã áp dụng, chỉ chưa đạt acknowledgement yêu cầu. |
| “Ghi majority thì mọi secondary đọc tức thì thấy dữ liệu.” | Secondary có thể lag. |
| “Đọc majority là linearizable.” | Không; majority committed visibility khác thứ tự real-time. |
| “Linearizable read có thể chạy ở mọi secondary.” | Phải dùng primary trong phạm vi hỗ trợ. |
| “Snapshot luôn là latest.” | Snapshot nhất quán tại một mốc, không nhất thiết là mới nhất. |
| “Causal session đồng bộ mọi client toàn cầu.” | Bảo đảm theo quan hệ nhân quả và điều kiện session; không tự thành global linearizability. |
| “Read preference gần nhất là bản mới nhất.” | `nearest` nói về độ trễ chọn node, không phải freshness. |
| “Đổi sang `secondaryPreferred` là giải quyết toàn bộ partition.” | Có thể giúp một số read, nhưng không tạo primary/quorum cho write. |
| “Hạ mọi ghi xuống `w: 1` là không có rủi ro.” | Có thể tăng rollback/lost acknowledged writes và không giúp phía mất primary. |
| “Transaction loại bỏ nhu cầu write concern.” | Commit concern, retry và failover vẫn quan trọng. |
| “Có index tốt thì majority latency sẽ thấp.” | Index giảm chi phí query; replication/network vẫn có thể chi phối latency. |
| “CAP chọn C, A, P một lần cho cả database.” | Phải xác định contract theo thao tác, topology và trạng thái lỗi. |
| “Hệ thống còn HTTP 200 là còn available.” | Cần xét response có đúng freshness/durability theo nghiệp vụ hay không. |

## 25. Checklist thiết kế một API đọc ghi

Trước khi triển khai endpoint quan trọng, hãy trả lời:

1. **Dữ liệu này có thể mất bao nhiêu sau sự cố?** Định nghĩa RPO.
2. **Có thể ngừng ghi bao lâu?** Định nghĩa RTO/SLO.
3. **Client phải thấy bản mới nhất hay có thể stale?** Định nghĩa freshness/consistency.
4. **Write concern nào được áp dụng thực tế?** Per-operation, client hay cluster default.
5. **Read concern và read preference nào được dùng?** Primary, secondary, majority, linearizable, snapshot?
6. **Khi không còn quorum, API làm gì?** Timeout, retry, read-only, queue hay fail closed?
7. **Khi nhận timeout không chắc chắn, retry có tạo trùng không?** Idempotency key, unique constraint, reconciliation.
8. **Có data-bearing replicas đủ ở những failure domains độc lập không?** Đừng chỉ đếm phiếu.
9. **Có theo dõi replication lag và election không?** Cần alert phù hợp.
10. **Timeout tổng và từng thành phần có tương thích SLA không?** Không chờ vượt deadline upstream.
11. **Có khả năng rollback/recovery và backup không?** Replication không thay backup.
12. **Có diễn tập sự cố trên staging không?** Không chỉ kiểm tra đường đi khỏe mạnh.

## 26. Bài tập thực hành

### Bài 1 — CAP trong một partition 1/2

Một PSS có primary A, secondary B và C; A bị cô lập khỏi B+C.

1. Phía nào có majority election?
2. Vì sao A không thể tiếp tục duy trì quyền primary hợp lệ khi mất quorum?
3. B+C cần làm gì trước khi chấp nhận ghi?
4. Một secondary ở phía thiểu số có thể trả dữ liệu cũ theo những điều kiện nào?
5. Điều gì xảy ra nếu client đòi linearizable read nhưng không thể liên lạc quorum?

### Bài 2 — So sánh write concern

Ứng dụng viết một document với:

```javascript
{ writeConcern: { w: 1 } }
```

và:

```javascript
{ writeConcern: { w: "majority", wtimeout: 5000 } }
```

Giải thích sự khác nhau về ACK, rollback risk, latency và hành vi khi một secondary cần thiết không phản hồi. Vì sao `wtimeout` không cho phép kết luận chắc chắn record đã bị hủy?

### Bài 3 — Majority read có stale không?

PSS có P, S1, S2. `version=12` đã majority committed tại P+S1, nhưng S2 mới apply đến `version=11`.

1. Read `majority` tại S2 có thể nhìn gì?
2. Vì sao câu trả lời không tự linearizable?
3. Khi nào nên dùng causal session?
4. Nếu cần trạng thái mới nhất của một document sau một thao tác đã hoàn tất, nên xem xét read concern nào?

### Bài 4 — PSS và PSA

So sánh:

```text
PSS = P + S + S
PSA = P + S + A
```

Trong tình huống mất một secondary:

- Còn bao nhiêu phiếu?
- Còn bao nhiêu data-bearing members?
- Có thể bầu/duy trì primary không?
- `w: "majority"` có hoàn tất được không?
- Rủi ro khi hạ xuống `w: 1` là gì?

### Bài 5 — Priority và candidate

Một replica set có ba data-bearing voting members:

```text
A: priority=3, votes=1
B: priority=0, votes=1
C: priority=0, votes=1
```

Nếu A hỏng, B+C có đủ phiếu. Vì sao vẫn không có ứng viên primary? Đề xuất cấu hình priority khác để ưu tiên A nhưng vẫn có failover.

### Bài 6 — Thiết kế đọc sau ghi

Người dùng cập nhật avatar thành công, rồi đọc hồ sơ từ secondary ở vùng gần nhất và thấy avatar cũ.

1. Đây là stale read hay rollback?
2. Viết một hợp đồng API dùng causal session hoặc đọc primary.
3. Nêu chi phí latency khi secondary chưa bắt kịp mốc nhân quả.
4. Có nên dùng linearizable read cho mọi trang hồ sơ không? Vì sao?

### Bài 7 — Timeout của giao dịch đơn hàng

Một API tạo đơn hàng nhận write concern timeout. Client gửi lại `insertOne()` với một `_id` ngẫu nhiên khác.

1. Rủi ro nghiệp vụ là gì?
2. Vì sao timeout không có nghĩa thao tác đầu đã bị hủy?
3. Thiết kế idempotency key và unique constraint phù hợp.
4. Khi nào cần kiểm tra trạng thái trên database sau retry?
5. Hãy phân biệt retryable writes ở driver với idempotency của toàn workflow.

### Bài 8 — Đọc tuyến tính hóa hay snapshot?

Hai bài toán:

- A: kiểm tra cờ `paymentsEnabled` được cập nhật majority và yêu cầu mọi read sau khi thao tác khóa hoàn tất phải thấy trạng thái mới.
- B: lập báo cáo doanh thu và số đơn hàng trên nhiều collection tại cùng một mốc.

Bài nào phù hợp single-document linearizable read? Bài nào cần snapshot/transaction hoặc materialized dataset? Vì sao không thể dùng một mức concern thay thế tất cả?

### Bài 9 — Multi-region latency

PSS có primary ở Region A, secondary ở B và C. B gần A hơn C.

1. Khi B khỏe, majority write có thể bị chi phối bởi node nào?
2. Khi B down, latency majority write có thể thay đổi ra sao?
3. Đọc từ C gần người dùng cuối có thể cải thiện network RTT nhưng tạo rủi ro gì?
4. Nêu các metric cần đo trước khi tuyên bố topology đáp ứng SLA.

### Bài 10 — Thiết kế degraded mode

Một dịch vụ cho phép đọc danh mục và mua sản phẩm. Khi không thể xác nhận majority write:

- Endpoint nào có thể phục vụ dữ liệu cache?
- Endpoint nào phải trả lỗi/chờ hoặc trạng thái pending?
- Những trường nào cần bổ sung vào response để mô tả freshness?
- Vì sao không nên tự hạ write concern cho thao tác trừ kho và thanh toán?
- Nếu dùng queue để nhận yêu cầu chờ xử lý, phải đảm bảo durability của queue như thế nào?

### Bài 11 — Diễn tập failover có kiểm soát

Trên môi trường staging PSS:

1. Ghi document với `w: "majority"`, ghi thời gian ACK.
2. Quan sát trạng thái/lag ở `rs.status()`.
3. Gây một sự cố node có kiểm soát theo quy trình của nhóm vận hành.
4. Đo thời gian không có primary.
5. Thử lại write concern majority và majority read.
6. Ghi thời điểm phục hồi của application driver.
7. So sánh latency, timeout rate và dữ liệu trước/sau.

Không thực hiện thí nghiệm gây sự cố trên production nếu chưa được phép và chuẩn bị đầy đủ.

## 27. Tài liệu MongoDB tham khảo

- [Replication](https://www.mongodb.com/docs/manual/replication/)
- [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/)
- [Read Concern "linearizable"](https://www.mongodb.com/docs/manual/reference/read-concern-linearizable/)
- [Read Concern "snapshot"](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [Replica Set Arbiters](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/)
- [Replica Set Configuration](https://www.mongodb.com/docs/manual/reference/replica-configuration/)
- [Default Read/Write Concern](https://www.mongodb.com/docs/manual/reference/command/getDefaultRWConcern/)
- [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)

## Kết luận

Đánh đổi giữa **nhất quán, độ trễ và khả dụng** trong MongoDB không chỉ là câu hỏi “cluster có bao nhiêu node”. Khi mạng phân vùng, **đa số phiếu bầu** quyết định nơi có thể duy trì primary hợp lệ; **số bản sao dữ liệu thực sự** và write concern quyết định thao tác ghi có thể được xác nhận tới mức nào. PSA có thể còn primary nhờ arbiter nhưng **không đồng nghĩa** còn khả năng ghi `w: "majority"` khi secondary data-bearing mất.

Một ghi **`w: 1`** có thể giảm thời gian chờ nhưng tăng rủi ro rollback so với một ghi đã được majority-acknowledged trong phạm vi bảo đảm của replica set. Một read **`majority`** tránh những dữ liệu chưa đạt commit majority, nhưng **không tự bảo đảm latest/linearizable** khi đọc từ secondary đang lag. **Causal consistency** giúp bảo vệ quan hệ thao tác trong session; **linearizable read** phù hợp với một số single-document decisions theo thứ tự thời gian thực; **snapshot** phục vụ nhiều lần đọc trên một trạng thái logic nhất quán. Mỗi lựa chọn có chi phí và giới hạn riêng.

Khi sự cố xảy ra, một hệ thống đáng tin cậy không được lén thay đổi hợp đồng nghiệp vụ. Hãy xác định **RPO/RTO, độ mới dữ liệu cần thiết, read/write concerns, failure domains, timeout, retry/idempotency và chế độ suy giảm** ngay khi thiết kế. Đối với dữ liệu có thể chấp nhận cũ, hãy nói rõ nó cũ đến đâu; đối với thao tác không được phép sai, hãy chấp nhận chờ hoặc từ chối khi không thể đạt mức đảm bảo. **Khả dụng thật sự là khả năng trả kết quả đúng với lời hứa của API, chứ không phải chỉ là còn một node trả lời.**

