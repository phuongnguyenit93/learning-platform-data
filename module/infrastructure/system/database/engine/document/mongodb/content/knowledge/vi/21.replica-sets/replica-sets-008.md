# Priority, votes, arbiter và các đánh đổi về khả năng chịu lỗi

Một MongoDB **replica set** gồm nhiều thành viên cùng duy trì bản sao dữ liệu và phối hợp để chọn ra một **primary**. Ứng dụng thường ghi vào primary, trong khi các secondary sao chép dữ liệu qua replication. Khi primary mất kết nối hoặc gặp sự cố, các thành viên có quyền bỏ phiếu có thể tổ chức **election** để chọn primary mới.

Tuy nhiên, “có nhiều node” không đồng nghĩa với “có thể chịu lỗi tùy ý”. MongoDB phải phân biệt **quyền bỏ phiếu**, **khả năng trở thành primary**, **việc lưu bản sao dữ liệu** và **độ bền của một thao tác ghi**. Ba cấu hình thường bị nhầm lẫn là:

- `priority`: mức ưu tiên của một thành viên **khi tranh cử primary**;
- `votes`: thành viên đó có **đóng góp phiếu** vào quorum bầu cử hay không;
- `arbiterOnly`: thành viên chỉ **bỏ phiếu**, không lưu bản sao dữ liệu.

Chọn sai những thuộc tính này có thể tạo một hệ thống **vẫn bầu được primary nhưng không đáp ứng được write concern mong muốn**, hoặc có nhiều secondary nhưng không đủ phiếu để giữ primary hoạt động khi mạng bị chia cắt.

Bài học giải thích cách MongoDB tính đa số, ý nghĩa `priority` và `votes`, vai trò của arbiter, khác biệt giữa mô hình **PSS** và **PSA**, đánh đổi về tính sẵn sàng và độ bền, cũng như quy trình giám sát và thay đổi cấu hình an toàn.

> **Ý chính:** *Election quorum* quyết định một primary có được bầu và duy trì hay không. *Write concern majority* quyết định một thao tác ghi được các thành viên lưu dữ liệu xác nhận đủ mức hay chưa. **Arbiter tham gia bầu cử nhưng không thể xác nhận đã lưu dữ liệu.**

## 1. Các vai trò trong replica set

Giả sử triển khai ba máy:

```text
                  Replica set rs0
             ┌──────────────────────────┐
Client write ──►  mongo-a:27017 PRIMARY │
             │       │       │          │
             │       │ oplog │          │
             │       ▼       ▼          │
             │  mongo-b     mongo-c     │
             │  SECONDARY   SECONDARY   │
             └──────────────────────────┘
```

Ở trạng thái ổn định:

- **Primary (P)** nhận các thao tác ghi thông thường của client.
- **Secondary (S)** duy trì dữ liệu thông qua replication; tùy cấu hình, chúng cũng có thể phục vụ thao tác đọc.
- **Arbiter (A)** là thành viên đặc biệt **không có dữ liệu của collection**, không đồng bộ oplog như secondary và không trở thành primary; nó chỉ tham gia quá trình bầu cử.
- **Voting member** là thành viên có `votes: 1`. Một secondary có `priority: 0` vẫn có thể là voting member.
- **Non-voting member** có `votes: 0`, không tham gia quorum, không thể trở thành primary và phải có `priority: 0`.

Các ký hiệu topology:

| Ký hiệu | Ý nghĩa |
|---|---|
| **PSS** | Một primary và hai secondary lưu dữ liệu |
| **PSA** | Một primary, một secondary, một arbiter |
| **PS** | Một primary, một secondary, không có arbiter |
| **PSSS** | Một primary, ba secondary |
| **PSSSS** | Một primary, bốn secondary |
| **P + S + A** | Cách viết đầy đủ hơn để tránh nhầm số thành viên lưu dữ liệu |

**Role primary/secondary không gắn vĩnh viễn với một host.** Khi có election, một secondary đủ điều kiện có thể trở thành primary, và primary cũ có thể trở lại làm secondary.

## 2. Ba khái niệm cần tách riêng

Nhiều lỗi thiết kế bắt nguồn từ việc coi `priority`, `votes` và replication như một thứ.

| Khái niệm | Trả lời câu hỏi | Điều nó không tự bảo đảm |
|---|---|---|
| `priority` | Thành viên này có thể được ưu tiên làm primary đến mức nào? | Không tạo thêm phiếu, không tạo bản sao dữ liệu |
| `votes` | Thành viên có tham gia bầu cử/quorum không? | Không đồng nghĩa có dữ liệu |
| `arbiterOnly` | Node này chỉ biểu quyết hay còn lưu dữ liệu? | Arbiter không xác nhận `w: "majority"` như secondary |
| `writeConcern` | Ghi phải được xác nhận ở mức nào trước khi trả thành công? | Không tự quyết định node nào được bầu |
| `readConcern` | Lần đọc có những bảo đảm nào về dữ liệu đã commit? | Không thay cho cơ chế bầu primary |
| `replication lag` | Secondary đã theo kịp primary đến đâu? | Node có phiếu không có nghĩa đã có mọi ghi mới |

Ví dụ, một secondary cấu hình:

```javascript
{
  host: "mongo-b:27017",
  priority: 0,
  votes: 1
}
```

**không thể làm primary**, nhưng vẫn **bỏ phiếu** và **lưu dữ liệu**; các thao tác ghi được nó xác nhận có thể góp phần vào write concern phù hợp.

Ngược lại, một arbiter:

```javascript
{
  host: "mongo-arb:27017",
  arbiterOnly: true,
  priority: 0,
  votes: 1
}
```

**có phiếu nhưng không lưu bản sao dữ liệu**. Vì thế, dù cả hai đều có `priority: 0`, chúng hoàn toàn khác nhau về giá trị đối với durability.

## 3. Election majority: cách tính quorum

Để bầu primary, replica set cần **đa số phiếu của các voting members được cấu hình**.

Với `V` thành viên có `votes: 1`, số phiếu tối thiểu cho đa số là:

\[
Q = \left\lfloor\frac{V}{2}\right\rfloor + 1
\]

Ví dụ:

| Số voting members `V` | Majority `Q` | Tối đa số phiếu vắng mặt mà vẫn còn đủ quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

MongoDB replica set hỗ trợ tối đa **bảy voting members**. Một replica set có thể có các thành viên không bỏ phiếu, nhưng chúng **không làm tăng** số phiếu dùng để tính đa số.

Bảng chỉ cho biết **điều kiện toán học về số phiếu**; để có primary hoạt động còn cần một ứng viên đủ điều kiện, đủ cập nhật theo các quy tắc election, có khả năng giao tiếp với quorum và đáp ứng các điều kiện của MongoDB. Không thể chỉ đếm máy còn bật là kết luận chắc chắn đã có một primary dùng được.

### 3.1. Vì sao hai phiếu không chịu mất một node?

Topology gồm hai voting data-bearing nodes:

```text
mongo-a (P, votes=1) ─── mongo-b (S, votes=1)

V = 2, Q = 2
```

Nếu `mongo-a` ngừng hoạt động, `mongo-b` còn **một phiếu**, không đạt `Q=2`, nên không thể tự bầu làm primary. Nếu kết nối mạng giữa hai node bị đứt, bên nào chỉ nhìn thấy một phiếu cũng không thể tự duy trì khả năng làm primary một cách hợp lệ.

Như vậy, có **hai bản sao dữ liệu** nhưng không có tự động failover khi mất một voting member. Đây là lý do mô hình PS hai phiếu không cung cấp mức election availability mà nhiều người mặc định kỳ vọng.

### 3.2. Vì sao ba phiếu được dùng phổ biến?

Topology PSS:

```text
mongo-a (P, votes=1)
mongo-b (S, votes=1)
mongo-c (S, votes=1)

V = 3, Q = 2
```

Nếu mất một voting member, hai thành viên còn lại vẫn đủ phiếu. Khi primary mất, hai secondary còn lại có thể bầu một primary mới nếu các điều kiện election khác được đáp ứng.

Ở cấu hình PSS, cả ba thành viên đều **lưu dữ liệu**. Điều này tạo cơ sở tốt hơn để vừa giữ quorum bầu cử, vừa đạt những write concern yêu cầu sự xác nhận của nhiều bản sao dữ liệu.

### 3.3. Số lẻ không phải một phép màu

Quy tắc “dùng số node lẻ” là cách ghi nhớ, nhưng không phải một đặc tính bảo đảm mọi mức fault tolerance:

- Bốn voting members cần `Q=3`, nên chỉ chịu được **một phiếu** vắng mặt.
- Năm voting members cũng cần `Q=3`, nhưng có thể chịu **hai phiếu** vắng mặt.
- Sáu voting members cần `Q=4` và chịu được **hai phiếu** vắng mặt.

Vì vậy, **số phiếu được cấu hình và khả năng mất đồng thời những phiếu đó** mới là điều cần phân tích. Việc thêm một node chỉ để “thành số lẻ” có thể ảnh hưởng cả quorum, write concern, vị trí địa lý và chi phí vận hành.

## 4. Priority: ai được ưu tiên làm primary?

Trong cấu hình replica set, `priority` xác định mức ưu tiên tương đối của một member **khi bầu primary**.

Ví dụ:

```javascript
{
  _id: 0,
  host: "mongo-a:27017",
  priority: 3,
  votes: 1
}
```

Giá trị mặc định của priority đối với data-bearing member có thể bầu cử thường là `1`. Các giá trị cao hơn được dùng khi muốn ưu tiên một node nhất định; `priority: 0` nghĩa là node **không đủ điều kiện làm primary**.

### 4.1. Priority cao không cộng thêm phiếu

Giả sử:

```text
mongo-a: priority=10, votes=1
mongo-b: priority=1,  votes=1
mongo-c: priority=1,  votes=1
```

Quorum vẫn tính trên **ba phiếu**, nên cần **hai phiếu**. `priority=10` **không có nghĩa mongo-a có mười phiếu**. Node a có thể được ưu tiên trong election hoặc có cơ hội priority takeover khi phù hợp, nhưng nó không thể một mình giành quyền primary nếu bị cách ly khỏi đa số.

### 4.2. Priority là ưu tiên, không phải lịch phân công cứng

Giả sử node a có priority cao nhất, nhưng:

- a đang tắt;
- a không kết nối được quorum;
- a đang trễ replication và không đủ điều kiện làm primary;
- a đang khởi động/recovering;
- a bị lỗi hoặc không đáp ứng những điều kiện election;

khi đó node khác đủ điều kiện có thể làm primary. Không thể hứa “priority cao nhất luôn luôn là primary ở mọi thời điểm”.

Ở những điều kiện thích hợp, MongoDB có cơ chế **priority takeover** để một secondary ưu tiên cao hơn có thể thúc đẩy election sau khi đủ điều kiện. Nhưng takeover có thể gây **stepdown, đổi kết nối và gián đoạn ngắn**; không nên dùng priority để liên tục ép primary chạy trên một node đang chịu trễ hoặc mất ổn định.

### 4.3. Priority 0: chỉ lưu dữ liệu và bỏ phiếu

Ví dụ:

```javascript
{
  _id: 2,
  host: "mongo-report:27017",
  priority: 0,
  votes: 1
}
```

Node này:

- Đồng bộ dữ liệu như secondary khi ở trạng thái thích hợp;
- Có thể đóng góp **một phiếu** vào election quorum;
- Không thể trở thành primary;
- Có thể tham gia những xác nhận ghi liên quan tới data-bearing voting member;
- Có thể phục vụ đọc theo read preference phù hợp.

`priority: 0` thường hữu ích cho secondary chuyên phục vụ đọc, node ở địa điểm không muốn nhận lưu lượng ghi chính, hoặc member mà chính sách vận hành không cho phép làm primary.

**Quan trọng:** Một replica set không được cấu hình sao cho tất cả data-bearing voting members đều không đủ điều kiện primary rồi mong election vẫn hoạt động. Phải có ứng viên hợp lệ khi cần failover.

### 4.4. Priority trong môi trường đa vùng

Giả sử data center A có đường mạng ổn định, độ trễ thấp tới API write path:

```text
Region A:
  mongo-a1  priority=3, votes=1

Region B:
  mongo-b1  priority=1, votes=1

Region C:
  mongo-c1  priority=1, votes=1
```

Mục tiêu có thể là ưu tiên primary ở A khi mọi thứ khỏe mạnh, nhưng vẫn cho B/C failover khi A gặp sự cố. Điều này có thể hợp lý nếu latency từ ứng dụng tới primary tại A tốt hơn.

Tuy nhiên:

- Region A bị phân vùng mạng vẫn không thể giữ primary nếu không có quorum.
- Region B/C phải có latency và tài nguyên đủ để chạy ghi trong trường hợp failover.
- Chỉ một host ở A có priority cao không thay thế thiết kế network, disk và replication hợp lý.
- Chênh lệch priority quá lớn hoặc cấu hình chủ động gây takeover có thể dẫn tới biến động không cần thiết khi hệ thống không ổn định.

## 5. Votes: ai có quyền tham gia quorum?

Mỗi member trong cấu hình replica set có giá trị `votes` theo các quy tắc hỗ trợ của MongoDB, thông thường là `0` hoặc `1`.

```javascript
{
  host: "mongo-b:27017",
  votes: 1,
  priority: 1
}
```

Member có `votes: 1` góp một phiếu vào cơ chế bầu cử.

```javascript
{
  host: "mongo-d:27017",
  votes: 0,
  priority: 0
}
```

Member có `votes: 0` không tham gia quorum và không thể trở thành primary; `priority` phải bằng 0.

### 5.1. Một secondary không bỏ phiếu vẫn có thể chứa dữ liệu

Đặt `votes: 0` **không làm member ngừng replication**. Một non-voting secondary vẫn có thể chứa bản sao dữ liệu, dùng cho một số nhu cầu đọc/backup theo ràng buộc của MongoDB.

Nhưng:

- Nó không đóng góp phiếu để giữ primary.
- Nó không trở thành primary khi những voting members lỗi.
- Không được đánh đồng việc có một non-voting secondary với việc quorum được tăng cường.
- Nó không được tính giống một data-bearing **voting** secondary trong các quy tắc majority write concern.

Nếu mục tiêu chính là tăng khả năng failover, thêm member `votes: 0` có thể **không** giải quyết vấn đề.

### 5.2. Ví dụ hai voting members và hai non-voting secondaries

```text
mongo-a  P   votes=1
mongo-b  S   votes=1
mongo-c  S   votes=0, priority=0
mongo-d  S   votes=0, priority=0
```

Có bốn máy lưu dữ liệu nhưng **chỉ hai phiếu**, nên `Q=2`. Nếu mongo-a ngừng, ba secondary còn lại vẫn chỉ có **một phiếu** của mongo-b. Chúng không tự tạo thành quorum bầu cử ba-voting-member.

Số bản sao dữ liệu nhiều không thay thế cấu hình voting quorum thích hợp.

### 5.3. Tăng số phiếu cũng có thể làm khó tính sẵn sàng

Giả sử có ba member voting đang khỏe (`V=3`, `Q=2`), hệ thống chịu được một phiếu vắng mặt.

Nếu thêm voting member thứ tư (`V=4`, `Q=3`), quorum mới tăng lên ba. Bốn member voting vẫn chỉ chịu được một phiếu vắng mặt.

Vì vậy, thêm một voting member **không tự động cải thiện số lỗi đồng thời hệ thống chịu được**. Cần tính lại đa số **sau khi cấu hình đổi**, không chỉ nhìn tổng số host.

## 6. Arbiter là gì?

Arbiter là một thành viên replica set có cấu hình `arbiterOnly: true`. Vai trò chính của nó là **cung cấp một phiếu bầu** trong tình huống cần quorum, thường khi không thể triển khai thêm một node chứa dữ liệu.

Một arbiter:

- **Có phiếu** theo cấu hình arbiter thông thường;
- **Không chứa bản sao tập dữ liệu ứng dụng**;
- **Không replay dữ liệu như một data-bearing secondary**;
- **Không thể trở thành primary**;
- **Không phục vụ các truy vấn dữ liệu ứng dụng** như một secondary;
- **Không xác nhận write concern như một node lưu dữ liệu**;
- Vẫn cần tài nguyên, kết nối, giám sát và bảo vệ tương ứng.

Ví dụ cấu hình member:

```javascript
{
  _id: 2,
  host: "mongo-arb:27017",
  arbiterOnly: true,
  priority: 0,
  votes: 1
}
```

**Arbiter không phải bản sao thứ ba.** Nếu primary và secondary cùng mất dữ liệu, arbiter không thể khôi phục dữ liệu từ một bản copy không tồn tại.

### 6.1. Arbiter giải quyết bài toán nào?

Giả sử chỉ đủ chi phí chạy hai node lưu dữ liệu:

```text
mongo-a  Primary, data bearing
mongo-b  Secondary, data bearing
```

Nếu cả hai có phiếu, `V=2`, `Q=2`; mất một node khiến election không đạt đa số.

Có thể thêm arbiter:

```text
mongo-a  P   votes=1  data=yes
mongo-b  S   votes=1  data=yes
mongo-c  A   votes=1  data=no

V=3, Q=2
```

Giờ, khi một data-bearing member mất kết nối nhưng node còn lại vẫn nhìn thấy arbiter, có thể còn **hai phiếu**, đủ quorum election. Đây là điểm arbiter giúp ích.

**Nhưng arbiter không thêm một bản sao dữ liệu.** Đánh đổi đặc biệt nghiêm trọng với `w: "majority"` được phân tích ở phần tiếp.

### 6.2. Không coi arbiter là secondary rẻ hơn về mọi mặt

Arbiter thường có yêu cầu lưu trữ thấp hơn data-bearing secondary, nhưng:

- Vẫn là một thành phần quorum quan trọng;
- Lỗi mạng hoặc shutdown của arbiter thay đổi khả năng election;
- Vị trí arbiter có thể thiên lệch kết quả khi mạng phân vùng;
- Không cải thiện khả năng đọc, phân phối backup hay durability;
- Vẫn cần thiết kế an toàn, monitoring, hardening và nâng cấp.

Một arbiter đặt trên host không ổn định có thể khiến replica set dễ rơi vào những tình huống election khó dự đoán.

## 7. Hai loại majority thường bị nhầm

Phần quan trọng nhất của thiết kế replica set là **không đánh đồng đa số bầu cử với đa số xác nhận dữ liệu**.

### 7.1. Election majority

Election quorum được xác định từ số **voting members**:

```text
P + S + A:
V = 3
Election majority Q = 2
```

Vì arbiter có một phiếu, tổ hợp `P + A` có hai phiếu và có thể duy trì quorum trong điều kiện phù hợp.

### 7.2. Write concern majority

Trong MongoDB, `writeConcern: { w: "majority" }` yêu cầu thao tác ghi được xác nhận bởi **mức đa số các thành viên data-bearing voting** theo quy tắc của replica set. Arbiter **không chứa dữ liệu**, nên không thể xác nhận đã ghi vào một bản sao của nó.

Với topology **PSA** có hai thành viên data-bearing voting, để ghi đạt `w: "majority"` cần **cả hai bản sao dữ liệu đủ điều kiện** xác nhận, theo quy tắc majority write concern.

Điều này tạo một trường hợp gây nhầm:

```text
Primary P còn sống      ✓ có dữ liệu
Secondary S mất          ✗ không thể xác nhận
Arbiter A còn sống       ✓ bỏ phiếu, không có dữ liệu

Election quorum: P + A = 2/3           ĐỦ
w: "majority" từ data-bearing nodes:   KHÔNG ĐỦ
```

**Primary có thể vẫn tồn tại và quorum bầu cử vẫn có, nhưng thao tác ghi yêu cầu majority có thể chờ rồi timeout** vì chỉ còn một bản sao dữ liệu.

### 7.3. Ví dụ lệnh write concern tường minh

```javascript
db.orders.insertOne(
  {
    orderNo: "O-229",
    createdAt: new Date(),
    status: "CREATED"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

Ở PSA, nếu secondary lưu dữ liệu không sẵn sàng, yêu cầu majority có thể **không được đáp ứng trong `wtimeout`** dù primary và arbiter vẫn giao tiếp được.

**Không suy ra timeout có nghĩa thao tác ghi chắc chắn không tồn tại trên primary.** Có tình huống thao tác đã được primary áp dụng nhưng **chưa đạt mức write concern được yêu cầu**. Client phải xử lý kết quả lỗi/không chắc chắn bằng retryable writes, idempotency hoặc đối soát theo contract của ứng dụng.

### 7.4. `w: 1` khác gì?

```javascript
db.orders.insertOne(
  {
    orderNo: "O-230",
    createdAt: new Date()
  },
  {
    writeConcern: { w: 1 }
  }
);
```

`w: 1` yêu cầu primary xác nhận thao tác theo các quy tắc write concern tương ứng, **không chờ** xác nhận từ secondary data-bearing khác.

Trong PSA khi secondary down, `w: 1` có thể còn được primary đáp ứng nếu primary có quorum election và đang writable. Nhưng bản ghi chỉ ở một data-bearing node có rủi ro cao hơn khi primary hỏng trước khi bản ghi được sao chép.

Không thể coi một ghi `w: 1` đã ACK là tương đương một ghi `w: "majority"` về khả năng sống sót qua failover.

### 7.5. Journal và write concern

`w` nói về **số thành viên xác nhận**; `j` liên quan việc chờ journal trên node theo ngữ nghĩa write concern tương ứng. Độ bền còn phụ thuộc journaling và cấu hình storage/deployment.

Ví dụ:

```javascript
{
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  }
}
```

Không nên mô tả `j: true` là thay thế replication, hoặc replication là thay thế hoàn toàn mọi cơ chế lưu bền. Muốn giải thích durability cần xét **số bản sao, mức acknowledgement, journaling, topology và failover**.

## 8. PSA so với PSS: bề ngoài cùng ba node, thực chất khác nhau

Hai topology đều có **ba voting members** và cần đa số hai phiếu, nhưng số bản sao dữ liệu khác nhau.

### 8.1. Mô hình PSS: ba data-bearing nodes

```text
          PSS
   ┌───────────────┐
   │ P: data + vote│
   │ S: data + vote│
   │ S: data + vote│
   └───────────────┘

Voting members = 3
Election quorum = 2
Data-bearing voting members = 3
```

Nếu mất một data-bearing node:

- Vẫn có **hai phiếu**.
- Hai node còn lại vẫn **có dữ liệu**.
- `w: "majority"` thường có thể được đáp ứng bởi các bản sao dữ liệu còn lại nếu replication và các điều kiện write concern khỏe mạnh.
- Nếu primary bị mất, hai secondary có thể bầu primary mới khi đủ điều kiện.

### 8.2. Mô hình PSA: hai data-bearing nodes và một arbiter

```text
          PSA
   ┌───────────────┐
   │ P: data + vote│
   │ S: data + vote│
   │ A:      vote  │
   └───────────────┘

Voting members = 3
Election quorum = 2
Data-bearing voting members = 2
```

Nếu mất secondary:

- Primary và arbiter vẫn có **hai phiếu**.
- Chỉ còn **một** data-bearing member.
- Hệ thống có thể tiếp tục chấp nhận một số ghi ở mức `w: 1`, tùy trạng thái primary.
- **Không còn đủ data-bearing acknowledgement để hoàn tất ghi majority** như khi cả hai data-bearing members khỏe mạnh.

Nếu mất arbiter, P và S vẫn có hai phiếu, đồng thời có hai bản sao dữ liệu, nên PSA thường vẫn có thể giữ primary và đáp ứng majority writes khi replication khỏe.

### 8.3. Bảng quyết định nhanh

| Tình huống | PSS (3 data) | PSA (2 data + A) |
|---|---|---|
| Số phiếu | 3 | 3 |
| Election quorum | 2 | 2 |
| Số bản sao dữ liệu | 3 | 2 |
| Mất một secondary | Còn hai data-bearing, có thể majority-write | Chỉ còn một data-bearing, majority-write bị ảnh hưởng |
| Mất primary | Hai secondary bầu mới; còn hai bản sao | Secondary và arbiter có thể bầu; chỉ một bản sao dữ liệu còn hoạt động |
| Mất arbiter | Không có arbiter | Còn P + S, thường đủ quorum |
| Arbiter hỗ trợ acknowledgement ghi? | Không áp dụng | **Không** |
| Chi phí lưu trữ dữ liệu | Cao hơn | Thấp hơn |
| Phù hợp khi cần ghi majority liên tục sau mất một node | **Ưu tiên xem xét** | **Không tương đương PSS** |

Bảng giả định các node còn lại khỏe, có kết nối cần thiết và đáp ứng các quy tắc bầu cử/replication; nó không phải cam kết uptime tuyệt đối.

## 9. Ma trận sự cố của PSA

Xét ba member:

```text
P = mongo-a, data-bearing, vote=1
S = mongo-b, data-bearing, vote=1
A = mongo-c, arbiter, vote=1
```

Các tình huống thường gặp:

| Node còn kết nối/khỏe | Election quorum | Primary có thể hoạt động? | `w: "majority"` cho ghi mới? |
|---|---|---|---|
| P + S + A | 3/3 | Có | Có, khi P/S replication khỏe |
| P + S | 2/3 | Có | Có, khi P/S replication khỏe |
| P + A | 2/3 | Có, trong điều kiện phù hợp | **Không đủ bản sao dữ liệu** |
| S + A, P mất | 2/3 | S có thể được bầu nếu đủ điều kiện | **Không đủ hai data-bearing nodes** |
| P một mình | 1/3 | Không thể duy trì primary hợp lệ khi mất quorum | Không |
| S một mình | 1/3 | Không thể tự bầu primary | Không |
| A một mình | 1/3 | Không thể làm primary | Không |

Nếu chỉ còn `S + A`, secondary có thể trở thành primary mới, nhưng nó vẫn là **bản sao dữ liệu duy nhất đang hoạt động**. Phải phân biệt “vẫn có primary mới” và “mọi write concern có thể được đáp ứng”.

### 9.1. Nguy cơ dữ liệu chỉ có một bản sao

Trong trạng thái P + A, nếu ứng dụng hạ write concern xuống `w: 1` để tiếp tục ghi, những ghi mới có thể tồn tại **chỉ trên P** cho đến khi S trở lại và đồng bộ.

Nếu P sau đó mất dữ liệu hoặc không thể phục hồi mà S chưa kịp nhận các ghi, arbiter không có dữ liệu để cứu. Do đó, quyết định cho phép `w: 1` trong trạng thái suy giảm phải đi kèm **RPO được chấp nhận**, kế hoạch phục hồi và kiểm soát nghiệp vụ.

Không có chuyện “arbiter giữ phiếu cho primary” đồng nghĩa “arbiter bảo vệ bản ghi”.

## 10. PSA và implicit default write concern

Có một điểm vận hành rất quan trọng: **không được tự giả định driver luôn dùng `w: "majority"`** chỉ vì MongoDB hỗ trợ write concern majority.

Tùy phiên bản server và cấu hình cluster-wide default read/write concern, **implicit default write concern** có thể khác nhau theo topology. Ở một số triển khai chứa arbiter, các quy tắc về số voting members và non-arbiter data-bearing members có thể khiến mặc định suy ra là `w: 1`.

Vì vậy:

1. Kiểm tra **default read/write concern** thực tế của deployment.
2. Với các thao tác nghiệp vụ quan trọng, khai báo write concern **tường minh** theo yêu cầu độ bền.
3. Không thay đổi default write concern toàn cluster chỉ để làm một benchmark chạy thành công.
4. Khi thêm/bớt arbiter hoặc voting member, đánh giá lại quy tắc mặc định và mọi client đang dựa vào default.

Ví dụ kiểm tra trong môi trường có quyền quản trị phù hợp:

```javascript
db.adminCommand({ getDefaultRWConcern: 1 });
```

Lệnh và trường kết quả cụ thể phụ thuộc phiên bản/quyền truy cập. Nếu cần thay đổi default RW concern, phải có kế hoạch triển khai, hiểu các ảnh hưởng và sử dụng thao tác được tài liệu phiên bản server hỗ trợ.

**Quy tắc thực tế:** một hệ thống tài chính/đơn hàng không nên dựa vào suy đoán “MongoDB mặc định luôn ghi majority”; hãy đo/đọc cấu hình thật.

## 11. Đổi priority không giống đổi votes

Hai thao tác có mục tiêu khác nhau:

### 11.1. Hạ priority nhưng giữ vote

```javascript
{
  host: "mongo-c:27017",
  priority: 0,
  votes: 1
}
```

Node vẫn lưu dữ liệu, vẫn bỏ phiếu, không tranh cử primary.

Lựa chọn này có thể hữu ích nếu một secondary được đặt ở vị trí không mong muốn làm primary nhưng vẫn muốn đóng góp vào quorum/durability theo các điều kiện hỗ trợ.

### 11.2. Tắt quyền bỏ phiếu

```javascript
{
  host: "mongo-c:27017",
  priority: 0,
  votes: 0
}
```

Node vẫn có thể là secondary đồng bộ dữ liệu, nhưng không đóng góp phiếu và không trở thành primary.

Nếu replica set ban đầu có ba voting data members và bạn đặt một secondary thành `votes: 0`, số voting members còn **hai** và majority election chuyển thành **hai phiếu**. Mất một trong hai voting members khiến quorum không còn, dù secondary non-voting vẫn khỏe và có bản sao dữ liệu.

**Không nên thay `votes: 1` bằng `votes: 0` chỉ để “giảm ảnh hưởng một node ở xa” mà không tính lại khả năng chịu lỗi.**

## 12. Priority takeover và rủi ro election không cần thiết

Một ví dụ định hướng:

```text
mongo-a priority=5, votes=1
mongo-b priority=2, votes=1
mongo-c priority=1, votes=1
```

Giả sử mongo-a gặp sự cố, mongo-b được bầu làm primary. Sau khi mongo-a phục hồi, đạt trạng thái đủ khỏe/cập nhật và có kết nối phù hợp, hệ thống có thể kích hoạt **priority takeover** để ưu tiên primary tại mongo-a.

Lợi ích:

- Primary có xu hướng trở về node/vùng được tối ưu cho ứng dụng;
- Có thể giảm latency cho write traffic ở trạng thái ổn định.

Đánh đổi:

- Mỗi lần đổi primary có thể gây một khoảng gián đoạn write;
- Các transaction đang chạy có thể bị ảnh hưởng;
- Driver/client cần xử lý retryable errors;
- Nếu node ưu tiên cao liên tục mất ổn định, có thể gây biến động vai trò không cần thiết.

Đối với phần lớn ứng dụng, **tính ổn định primary** có giá trị lớn. Không nên tạo priority khác nhau quá mức nếu không có lý do nghiệp vụ/vận hành đủ rõ.

### 12.1. Priority không phải cơ chế health check nâng cao

Priority không đánh giá thay bạn toàn bộ điều kiện CPU, IOPS, replication lag, kết nối client và độ trễ vùng. Một node có priority cao nhưng disk chậm không được “tự nâng cấp hiệu năng” nhờ config.

Khi chọn priority, cần xem cả:

- Tài nguyên và độ ổn định của host;
- Khả năng đáp ứng write throughput;
- Vị trí của ứng dụng ghi;
- Network RTT tới secondary và quorum;
- Khả năng phục hồi sau failover.

## 13. Phân vùng mạng: tại sao quorum quan trọng?

Một replica set ba voting members có thể bị chia thành hai phía:

```text
Partition 1: mongo-a + mongo-b (2 votes)
Partition 2: mongo-c           (1 vote)

V = 3
Q = 2
```

Phía có hai phiếu có thể duy trì hoặc bầu primary nếu đủ điều kiện. Phía có một phiếu không thể tự bầu primary hợp lệ.

Mục tiêu là tránh việc hai phân vùng độc lập đều tin mình có quyền nhận ghi với đa số phiếu, qua đó giảm nguy cơ **split-brain sustained primary**.

Tuy nhiên, đây không phải phép bảo đảm “không có lỗi tạm thời”. Khi có partition/failover:

- Primary cũ có thể mất một khoảng thời gian để nhận ra đã mất quorum và step down;
- Driver có thể tạm thời kết nối tới một node chưa cập nhật trạng thái;
- Một số thao tác có thể trả lỗi “not primary”, timeout, transient transaction error;
- Ghi `w: 1` trước failover có thể bị rollback trong những tình huống thích hợp;
- Client cần xử lý retry/idempotency đúng cách.

**Quorum giảm nguy cơ có hai primary hợp lệ hoạt động đồng thời lâu dài; ứng dụng vẫn phải thiết kế cho lỗi chuyển trạng thái.**

### 13.1. Arbiter ở phân vùng nào có thể quyết định phía có primary

Trong PSA:

```text
Region A: P (data)
Region B: S (data)
Region C: A (arbiter)
```

Nếu đường mạng chia thành:

```text
Partition 1: P
Partition 2: S + A
```

phía `S + A` có hai phiếu, đủ điều kiện election, dù chỉ có **một node lưu dữ liệu** đang hoạt động ở phía đó. P đơn lẻ không thể duy trì primary hợp lệ.

Nếu phân vùng đổi thành:

```text
Partition 1: P + A
Partition 2: S
```

thì phía P + A có quorum, còn S đơn lẻ không có.

Vị trí của arbiter không chỉ là vấn đề giá thuê host; nó có thể quyết định **khu vực nào giữ được quyền ghi khi mạng bị chia cắt**. Phải xem topology mạng và ứng dụng đặt ở đâu.

## 14. Quorum vùng địa lý không đồng nghĩa durability vùng địa lý

Giả sử một replica set có ba member:

```text
DC Hà Nội:        P (data, vote)
DC Đà Nẵng:       S (data, vote)
DC TP. Hồ Chí Minh: A (vote only)
```

Từ góc độ election, ba địa điểm có ba phiếu. Nhưng dữ liệu thật chỉ tồn tại ở **hai nơi**.

Nếu DC chứa secondary mất kết nối, primary và arbiter vẫn có quorum; hệ thống có thể nhận ghi `w: 1` nhưng không thể có thêm bản sao dữ liệu của những ghi mới trên arbiter. Không có “ba vùng lưu dữ liệu”.

Một topology ba data-bearing members phân tán hợp lý có thể tăng khả năng duy trì một bản ghi đã được đa số data-bearing xác nhận qua một số loại sự cố; nhưng nó đòi hỏi chi phí storage/replication và độ trễ mạng tương ứng.

### 14.1. Không đặt arbiter trên cùng failure domain mà không tính toán

Nếu arbiter được đặt trên cùng host, rack, power domain hoặc network segment với một data-bearing member, một sự cố đơn lẻ có thể làm mất **hai phiếu cùng lúc**.

Ví dụ:

```text
Failure domain X: P + A
Failure domain Y: S
```

Khi X mất điện, S còn một phiếu, không thể tự bầu primary. Như vậy, arbiter không đạt mục tiêu tăng election availability đối với kiểu sự cố cần chịu.

Không chỉ đếm “ba process mongod”; hãy đếm **số failure domains độc lập** và số phiếu còn sống sau từng kiểu sự cố.

### 14.2. WAN latency ảnh hưởng replication và failover

Phân tán các data-bearing members qua nhiều vùng có lợi về khả năng chịu lỗi địa lý nhưng đánh đổi:

- WAN RTT tăng;
- Ghi majority có thể cần chờ acknowledgements qua mạng;
- Secondary có thể lag khi băng thông không đủ;
- Election/heartbeat nhạy với network partition;
- Backups và resync có thể tốn thời gian;
- Chi phí lưu trữ/truyền dữ liệu tăng.

Không có topology tối ưu tuyệt đối: thiết kế phải cân bằng **RTO, RPO, latency, cost và fault domain**.

## 15. Priority 0 và khả năng failover thực tế

Giả sử ba data-bearing voting members:

```text
mongo-a: priority=2, votes=1
mongo-b: priority=0, votes=1
mongo-c: priority=0, votes=1
```

Có ba phiếu và `Q=2`, nhưng **chỉ mongo-a đủ điều kiện thành primary**. Nếu mongo-a hỏng, hai secondary còn lại vẫn có đa số phiếu nhưng **không có candidate hợp lệ** vì cả hai đều priority 0.

Kết luận:

> **Có quorum chưa đủ**: cần ít nhất một candidate hợp lệ trong phân vùng có quorum.

Đây là một lỗi thiết kế dễ bỏ qua khi đội vận hành đặt priority 0 cho mọi secondary nhằm “ghim primary” trên một host.

### 15.1. Một cấu hình dễ failover hơn

```text
mongo-a: priority=2, votes=1
mongo-b: priority=1, votes=1
mongo-c: priority=0, votes=1
```

Nếu a mất, b có thể làm ứng viên primary với sự hỗ trợ phiếu của c trong điều kiện thích hợp.

Tuy vậy, nếu a và b cùng mất, chỉ còn c với một phiếu nên vẫn không đủ quorum. Không nên suy từ priority b=1 rằng c có thể tự cứu cụm nếu chỉ một node còn sống.

### 15.2. Đừng nhầm “non-voting” và “priority-zero”

`votes: 0` kéo theo `priority: 0`, nhưng `priority: 0` **không** nhất thiết kéo theo `votes: 0`.

Ví dụ:

```javascript
// Secondary vẫn có thể bỏ phiếu:
{ priority: 0, votes: 1 }

// Secondary không bỏ phiếu, cũng không làm primary:
{ priority: 0, votes: 0 }
```

Hai cấu hình có ảnh hưởng khác nhau đến quorum, write concern và mức fault tolerance.

## 16. Bài toán capacity sau failover

Tăng số bản sao dữ liệu không đảm bảo ứng dụng vẫn chạy tốt sau khi một node mất.

Giả sử:

```text
mongo-a: 16 CPU, 64 GB RAM, NVMe; priority=5
mongo-b: 2 CPU, 8 GB RAM, HDD; priority=1
mongo-c: arbiter; priority=0
```

Khi a mất, b có thể được bầu primary với phiếu của arbiter. Nhưng b có thể **không chịu nổi tải ghi** vốn do a xử lý.

Một primary mới phải có:

- CPU/RAM/IOPS đủ cho peak write workload;
- Disk space và oplog phù hợp;
- Network connectivity tới client;
- Khả năng duy trì replication;
- Cấu hình và phiên bản tương thích;
- Monitoring và alert khi chuyển vai trò.

Do đó, `priority` cần gắn với **khả năng phục vụ thật của node**, không chỉ vai trò mong muốn.

### 16.1. RTO và RPO phải được định nghĩa

- **RTO (Recovery Time Objective):** thời gian gián đoạn tối đa mong muốn trước khi khả năng ghi/đọc phù hợp trở lại.
- **RPO (Recovery Point Objective):** lượng dữ liệu có thể chấp nhận mất khi xảy ra sự cố.

Một PSA có thể giúp **election xảy ra** khi mất primary, nhưng nếu còn một data-bearing node, `w: "majority"` vẫn không được đáp ứng. Vì vậy, RTO cho **“có primary”** khác với RTO cho **“ghi majority thành công”**.

Nếu hạ xuống `w: 1` trong thời gian suy giảm, RPO về mặt rủi ro thay đổi. Phải ghi nhận đánh đổi này trong quy trình vận hành, không xử lý như một workaround vô hại.

## 17. Tương tác với writeConcern và readConcern

### 17.1. Write concern

Các ví dụ:

```javascript
// Xác nhận từ primary theo w=1.
db.orders.insertOne(
  { orderNo: "A-001" },
  { writeConcern: { w: 1 } }
);

// Yêu cầu majority acknowledgment.
db.orders.insertOne(
  { orderNo: "A-002" },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
```

`w: 1` thường có latency thấp hơn trong những điều kiện nhất định nhưng độ bền qua failover không tương đương majority. `w: "majority"` đòi đủ bản sao dữ liệu xác nhận; điều này có thể làm tăng latency khi secondary trễ hoặc mất kết nối.

`wtimeout` giới hạn thời gian chờ write concern, **không tự là timeout cho mọi giai đoạn xử lý lệnh ghi**; cần hiểu rõ kết quả lỗi và trạng thái không chắc chắn khi sử dụng.

### 17.2. Read concern majority

Một read với `readConcern: { level: "majority" }` có những bảo đảm về dữ liệu majority committed theo quy tắc của MongoDB.

Ví dụ ý tưởng:

```javascript
db.orders.find(
  { status: "PAID" }
).readConcern("majority");
```

Cú pháp thiết lập read concern trên cursor/API có thể khác theo shell/driver và phiên bản; với driver, thường cấu hình ở collection/database/client hoặc trong tùy chọn thao tác hỗ trợ. **Không coi read concern majority là snapshot cố định qua nhiều request**: các lần đọc ở thời điểm khác nhau vẫn có thể thấy dữ liệu majority committed mới.

Arbiter không giữ dữ liệu ứng dụng để phục vụ một truy vấn majority. Nó không phải nguồn dữ liệu đọc dự phòng.

### 17.3. Majority commit point

Khái niệm **majority commit point** giúp hiểu những thao tác ghi đã được xác nhận trên đa số data-bearing voting members theo cơ chế replication. Nếu chỉ có một bản sao dữ liệu đang hoạt động trong PSA, commit point có thể không tiến theo các ghi mới vì không có secondary data-bearing phù hợp để xác nhận chúng.

Hệ quả có thể ảnh hưởng tới read concern majority và các hoạt động phụ thuộc vào majority-committed state. Không nên suy từ “primary vẫn chạy và w:1 ghi thành công” rằng mọi khả năng đọc/ghi với majority vẫn hoàn toàn bình thường.

## 18. Arbiter và transaction

MongoDB hỗ trợ multi-document transactions trong những môi trường/version nhất định. Nhưng không phải cứ triển khai một replica set có arbiter là mọi transaction đều có hành vi giống một replica set toàn data-bearing.

**Đặc biệt ở PSA**, transaction có thể gặp hạn chế khi một số thao tác yêu cầu majority commit hoặc khi transaction liên quan đến sharding/DDL theo điều kiện hỗ trợ của phiên bản server. Trong sharded cluster, một shard có arbiter có những giới hạn riêng đối với giao dịch đa shard.

Điểm thiết kế quan trọng:

- Transaction không biến arbiter thành bản sao dữ liệu;
- Hệ thống có thể có quorum election mà vẫn thiếu data-bearing acknowledgments;
- Khi cần transaction cross-shard hoặc majority durability, phải kiểm tra topology và tài liệu chính xác của phiên bản MongoDB đang dùng;
- Không thêm arbiter để giải quyết thiếu quorum mà không kiểm tra tác động đến transaction workload.

Nếu ứng dụng có nghiệp vụ thanh toán, trừ kho hoặc tạo đơn hàng đa document, nên ưu tiên **kiến trúc data-bearing phù hợp** thay vì giả định arbiter là lựa chọn tương đương nhưng rẻ hơn.

## 19. Kiểm tra cấu hình hiện tại

Trong `mongosh`, có thể xem replica set config:

```javascript
rs.conf();
```

Một cấu hình minh họa:

```javascript
{
  _id: "rs0",
  version: 7,
  members: [
    {
      _id: 0,
      host: "mongo-a:27017",
      priority: 2,
      votes: 1
    },
    {
      _id: 1,
      host: "mongo-b:27017",
      priority: 1,
      votes: 1
    },
    {
      _id: 2,
      host: "mongo-c:27017",
      priority: 0,
      votes: 1
    }
  ]
}
```

Đây chỉ là **minh họa những field liên quan**, không phải output đầy đủ của `rs.conf()`. Config thực có thể chứa nhiều thuộc tính khác, như settings, horizons, tags, buildIndexes hoặc thông tin version.

Kiểm tra trạng thái member:

```javascript
rs.status();
```

Các thông tin thường hữu ích:

| Trường/trạng thái | Cần quan sát |
|---|---|
| `set` | Tên replica set |
| `members[].name` | Host/member |
| `members[].stateStr` | `PRIMARY`, `SECONDARY`, `ARBITER`, `RECOVERING`, ... |
| `members[].health` | Mức health theo quan sát của node |
| `members[].optime` | Tiến độ replication |
| `members[].lastHeartbeatMessage` | Thông tin sự cố kết nối/heartbeat |
| `election*` metadata | Thông tin election theo phiên bản |
| `syncSourceHost` / trường tương đương | Nguồn đồng bộ của secondary |

Cần kết hợp trạng thái, replication lag, network, operation latency và log. `health: 1` chỉ nói một phần, không đủ để khẳng định node có thể làm primary hoặc write majority sẽ luôn thành công.

### 19.1. Đọc cấu hình bằng một bảng rõ ràng

```javascript
const config = rs.conf();

config.members.forEach((m) => {
  printjson({
    host: m.host,
    priority: m.priority,
    votes: m.votes,
    arbiterOnly: m.arbiterOnly === true,
    hidden: m.hidden === true
  });
});
```

Nếu member không khai báo một số thuộc tính tường minh, cần hiểu **default của MongoDB** khi diễn giải; không đơn thuần xem undefined là 0. Với arbiter, hãy xem `arbiterOnly` và vai trò thật trong `rs.status()`.

## 20. Ví dụ thay đổi priority một cách có kiểm soát

Các lệnh `rs.reconfig()` có thể gây election hoặc làm primary step down. Vì vậy, **chỉ thực hiện khi có quyền quản trị, kế hoạch đổi cấu hình và đường rollback**. Các lệnh sau minh họa thao tác trên môi trường thử, không phải script chạy trực tiếp trên production.

Giả sử muốn chuyển mongo-b từ priority 1 sang 2:

```javascript
const cfg = rs.conf();

const member = cfg.members.find(
  (m) => m.host === "mongo-b:27017"
);

if (!member) {
  throw new Error("Member mongo-b not found");
}

member.priority = 2;

// Cẩn trọng: có thể gây election hoặc đổi primary.
rs.reconfig(cfg);
```

Sau đó:

```javascript
rs.conf();
rs.status();
```

Nên xác minh:

- MongoDB chấp nhận cấu hình;
- Các member trở về trạng thái khỏe;
- Vai trò primary phù hợp chính sách;
- Không có replication lag đáng kể;
- Các thao tác ghi với write concern mong muốn còn thành công;
- Driver/client hoạt động sau election nếu có.

### 20.1. Đổi `votes` phải tính quorum mới

Giả sử muốn đặt một member `votes: 0`, phải hiểu:

1. Số voting members sau thay đổi còn bao nhiêu;
2. Majority quorum mới là bao nhiêu;
3. Những partition/failure nào khiến mất quorum;
4. Những data-bearing voting members nào còn đáp ứng write majority;
5. Có đủ candidate có priority > 0 hay không.

MongoDB giới hạn cách thêm/bớt voting members trong một lần reconfiguration; thông thường **không được thay đổi tùy ý nhiều voting members trong một lệnh reconfig**. Khi thay đổi topology quan trọng, nên thực hiện theo các bước được tài liệu phiên bản MongoDB hướng dẫn, có xác minh sau mỗi bước.

### 20.2. Không dùng `force` để giải quyết mọi sự cố quorum

Một số thao tác reconfiguration hỗ trợ tùy chọn `force` cho các tình huống đặc biệt. Đây là công cụ khẩn cấp với rủi ro cấu hình/mất dữ liệu, **không** phải cách vận hành thông thường để “đặt primary bằng tay” khi hệ thống đang partition.

Nếu một replica set không có quorum, phải chẩn đoán failure domain và dữ liệu trước, tránh cố reconfig nhiều phía độc lập dẫn tới những trạng thái khó khôi phục.

## 21. Thêm arbiter: quy trình và cảnh báo

Trong môi trường thử có replica set đang hoạt động, ví dụ lệnh:

```javascript
rs.addArb("mongo-arb:27017");
```

Lệnh này có ý nghĩa thêm một arbiter vào replica set (khi topology và quyền hỗ trợ). Nhưng **thêm arbiter là thay đổi cơ chế voting quorum**, không chỉ thêm một process.

Trước khi thực hiện:

1. Xác nhận replica set đã được cấu hình, có primary hợp lệ và đủ quorum hiện tại.
2. Kiểm tra giới hạn số voting members.
3. Tính đa số trước/sau thay đổi.
4. Đánh giá ràng buộc liên quan đến `w: "majority"` và implicit default write concern.
5. Kiểm tra tác động đến các transaction/sharded workloads.
6. Chọn failure domain phù hợp cho arbiter.
7. Dự phòng kết nối, tài nguyên tối thiểu, monitoring và bảo mật.
8. Lập phương án quay lại topology cũ nếu cần.

**Không dùng arbiter chỉ để có “ba node trên sơ đồ”** khi nhu cầu thật là tăng số bản sao dữ liệu hoặc tiếp tục ghi majority sau khi một data-bearing node hỏng.

### 21.1. Vì sao ưu tiên secondary thật nếu có đủ tài nguyên?

Thay vì:

```text
P + S + A
```

nếu có thể triển khai:

```text
P + S + S
```

thì thành viên thứ ba vừa có phiếu, vừa chứa dữ liệu và có thể tham gia failover/majority replication theo đúng điều kiện. Điều này thường có giá trị cao hơn cho những ứng dụng ưu tiên durability và write availability.

Chi phí của secondary thật gồm storage, backup/replication bandwidth, CPU/RAM và vận hành; quyết định cần dựa vào yêu cầu RPO/RTO và ngân sách.

## 22. Ví dụ thiết kế theo mức chịu lỗi

### 22.1. Trường hợp A: môi trường học tập ít tài nguyên

Chỉ có hai máy data-bearing, cần hiểu election và thực hành failover:

```text
P + S + A
```

PSA có thể là một mô hình học tập hữu ích để thấy vai trò của arbiter. Nhưng phải ghi rõ:

- Chỉ có hai bản sao dữ liệu;
- Khi một data-bearing member mất, majority write bị ảnh hưởng;
- Không mặc nhiên đáp ứng SLA production về durability;
- Không dùng PSA để thay thế các yêu cầu DR/backup.

### 22.2. Trường hợp B: ứng dụng giao dịch cần chịu mất một node

```text
P + S + S
```

Với ba data-bearing voting members, khi mất một member, còn hai node lưu dữ liệu và hai phiếu. Trong điều kiện healthy replication, hệ thống có thể vừa giữ election quorum vừa đáp ứng majority writes.

Cần phân tán trên những failure domains đủ độc lập, kiểm tra latency và bảo đảm secondary có thể gánh tải primary.

### 22.3. Trường hợp C: ba data-bearing nhưng một secondary không được làm primary

```text
P:  priority=2, votes=1
S1: priority=1, votes=1
S2: priority=0, votes=1
```

S2 vẫn cung cấp bản sao dữ liệu và phiếu, nhưng không làm candidate. Nếu P mất, S1 có thể lên primary với phiếu của S2, khi đủ điều kiện.

Thiết kế này hợp lý hơn việc đặt cả S1 và S2 priority 0 nếu cần failover tự động.

### 22.4. Trường hợp D: bốn data-bearing voting members

```text
P + S + S + S
V = 4
Q = 3
```

Tăng từ ba lên bốn phiếu **không tăng số phiếu mất đồng thời vẫn đạt quorum**: cả hai đều chỉ chịu một phiếu vắng mặt. Tuy nhiên, có thêm một bản sao dữ liệu, tùy nhu cầu backup/read load và topology.

Muốn chịu mất hai voting members về election quorum thường phải có **ít nhất năm** voting members (`V=5`, `Q=3`), đồng thời phải bảo đảm có ứng viên hợp lệ và đủ data-bearing replicas cho write concern mong muốn.

### 22.5. Trường hợp E: nhiều secondary non-voting để đọc

Một số hệ thống cần thêm bản sao cho báo cáo, analytics hoặc backup:

```text
P + S + S    (3 voting)
    +
S + S        (2 non-voting, priority=0)
```

Các node non-voting có thể giúp tách workload đọc khi phù hợp read preference và độ trễ replication, nhưng **election quorum vẫn dựa trên ba voting members**. Cần tránh coi năm bản sao dữ liệu là năm phiếu bầu.

## 23. Rủi ro của cấu hình arbiter không cân bằng theo vùng

Giả sử:

```text
DC-A: Primary + Arbiter
DC-B: Secondary
```

Mất DC-A khiến cả primary lẫn arbiter biến mất, DC-B còn một phiếu nên không thể có primary mới. Nếu mục tiêu chính là **sống sót khi mất toàn bộ DC-A**, topology này không đạt.

Chuyển arbiter sang DC-C:

```text
DC-A: Primary
DC-B: Secondary
DC-C: Arbiter
```

có thể cải thiện **quorum phân tán theo vùng**, nhưng khi DC-A hoặc DC-B mất vẫn chỉ còn một data-bearing node, và write majority không thể hoạt động như khi cả hai khỏe.

Muốn vừa chịu mất một vùng, vừa đáp ứng majority writes, thường phải đánh giá cách bố trí **ba data-bearing voting members** trên các failure domains phù hợp. Tuy nhiên, ba vùng data-bearing kéo theo WAN replication latency; cần đo trước khi chọn.

### 23.1. Lập ma trận sự cố trước khi quyết định

Nên lập bảng:

| Sự cố giả định | Voting members còn? | Có candidate không? | Data-bearing members còn? | `w: "majority"` còn đáp ứng? |
|---|---|---|---|---|
| Mất primary | Tùy topology | Có/không | Bao nhiêu? | Có/không |
| Mất secondary | Tùy topology | Primary còn không? | Bao nhiêu? | Có/không |
| Mất arbiter | Tùy topology | Primary còn không? | Bao nhiêu? | Có/không |
| Mất cả rack | Những phiếu ở rack đó biến mất | Cần tính | Những bản sao ở rack đó mất | Cần tính |
| Mất cả vùng | Những phiếu ở vùng đó biến mất | Cần tính | Những bản sao ở vùng đó mất | Cần tính |
| Network partition 2/1 | Phía nào có đa số? | Ở phía nào? | Mỗi phía có bao nhiêu bản sao? | Tùy phía và write concern |

Việc phân tích **theo failure domain** có giá trị hơn quy tắc “số node lẻ là ổn” khi một rack/region có thể làm nhiều host cùng mất.

## 24. Kiểm tra failover phải đo bằng thao tác thật

Một buổi diễn tập failover nên có ít nhất ba phần:

1. **Election:** member nào được bầu primary? Mất bao lâu?
2. **Write availability:** các ghi `w: 1` và `w: "majority"` hoạt động ra sao trong giai đoạn suy giảm?
3. **Data durability:** có bản ghi nào ACK mà sau failover không còn? Kết quả có tương ứng với mức write concern không?

Ví dụ khung kiểm thử trong môi trường staging:

```javascript
// Đọc topology trước test.
rs.status();

// Ghi sample với majority.
db.failoverLab.insertOne(
  {
    _id: "before-failure",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);

// Sau khi gây một sự cố có kiểm soát:
// 1. Kiểm tra primary mới/quorum.
// 2. Thử ghi với cùng write concern.
// 3. Đọc lại sample, ghi log thời gian và lỗi.
```

**Không tự ngắt node production** chỉ để thử. Diễn tập phải có kế hoạch, phê duyệt vận hành, người giám sát, công cụ quan sát và phương án khôi phục.

### 24.1. Kết quả lỗi chưa chắc đồng nghĩa record không được ghi

Khi client nhận write concern timeout:

- Lệnh ghi có thể đã áp dụng trên primary nhưng chưa đạt mức ACK cần thiết;
- Retry có thể tạo trùng nếu ứng dụng không có ID cố định hoặc cơ chế idempotency;
- Một thao tác có thể đã được majority commit nhưng client mất response do lỗi mạng;
- Transaction/retryable-write behavior phụ thuộc driver, server và cách ứng dụng sử dụng.

Vì vậy, logic nghiệp vụ nên có **operation ID**, unique key phù hợp, retryable writes và đối soát. Không viết code “timeout thì cứ insert bản ghi mới với ID mới” nếu nó có thể tạo đơn hàng/thanh toán trùng.

## 25. Quan sát các chỉ số vận hành quan trọng

| Nhóm chỉ số | Điều cần xem |
|---|---|
| Election | Số lần election, primary stepdown, lý do đổi primary |
| Quorum | Member mất kết nối, ping/heartbeat, thời gian không có primary |
| Replication | Secondary replication lag, oplog window, sync errors |
| Write concern | Tỷ lệ `wtimeout`, write latency theo concern level |
| Durability | Majority commit lag, rollback events, journal/disk |
| Capacity | CPU, RAM, IOPS, network throughput và connection count |
| Arbiter | State ARBITER, heartbeat, network reachability |
| Application | Retry/error rate, latency p95/p99, transaction abort |
| Maintenance | Thay đổi config, version, member health và lịch backup |

Nếu có arbiter, nên cảnh báo khi **secondary data-bearing bị mất**, dù primary vẫn còn và arbiter vẫn đủ phiếu. Đây là trạng thái dễ tạo ảo giác “cluster healthy vì có primary” trong khi khả năng ghi majority đã suy giảm.

### 25.1. Hai loại alert khác nhau

**Alert A — Election quorum degradation**

> Replica set có nguy cơ không giữ được primary nếu mất thêm một voting member.

**Alert B — Majority write degradation**

> Không còn đủ data-bearing voting members khỏe/đồng bộ để hoàn tất thao tác ghi `w: "majority"` theo SLA.

Hai alert cần phân biệt vì trạng thái `P + A` trong PSA có thể **không** kích hoạt Alert A ở cùng nghĩa với “mất quorum”, nhưng phải kích hoạt Alert B.

## 26. Thay đổi cấu hình và nâng cấp: nguyên tắc an toàn

Khi đổi topology hoặc cấu hình replica set:

1. **Ghi lại cấu hình hiện tại** và trạng thái của từng member.
2. **Tính quorum trước và sau** thay đổi.
3. **Kiểm tra ứng viên primary**, nhất là những node có priority > 0 và votes = 1.
4. **Đánh giá durability**, gồm số data-bearing voting members và majority write availability.
5. **Đánh giá failure domains**, tránh mất nhiều phiếu bởi một sự cố.
6. **Kiểm tra read/write concern mặc định** và các lệnh/transaction của ứng dụng.
7. **Thực hiện từng bước** theo tài liệu phiên bản, không thay nhiều phiếu tùy ý.
8. **Quan sát replication catch-up** và tránh reconfig khi cụm đang mất ổn định.
9. **Xác minh sau thay đổi** bằng `rs.conf()`, `rs.status()`, các thao tác ghi/đọc thử hợp lệ.
10. **Có rollback plan** và điều kiện dừng nếu SLA bị ảnh hưởng.

Đặc biệt thận trọng khi làm những thay đổi như:

- Hạ `votes` của một member từ 1 xuống 0;
- Đặt quá nhiều candidate thành priority 0;
- Thêm arbiter;
- Chuyển priority cao nhất sang vùng mạng khác;
- Bỏ secondary duy nhất còn đóng góp majority acknowledgement;
- Thay nhiều voting members trong cùng giai đoạn.

Một cấu hình nhìn cân đối trên sơ đồ vẫn có thể trở nên kém chịu lỗi hơn sau khi cập nhật quorum.

## 27. Bài tập thực hành

### Bài 1 — Tính election quorum

Với `V = 1, 2, 3, 4, 5, 6, 7`, hãy tính:

1. Majority `Q`.
2. Số voting members tối đa có thể vắng mặt mà vẫn còn quorum.
3. Vì sao thêm voting member từ 3 lên 4 không làm tăng số phiếu có thể mất cùng lúc.
4. Vì sao non-voting secondary không làm thay đổi `Q`.

### Bài 2 — Phân biệt priority và votes

Giả sử:

```text
A: priority=4, votes=1
B: priority=1, votes=1
C: priority=0, votes=1
```

Trả lời:

- Node nào có thể làm primary?
- Node nào bỏ phiếu?
- Nếu A ngừng, B + C có đủ quorum không?
- Nếu chỉ còn C, có thể có primary không?
- Nếu đặt `votes=0` cho C, ảnh hưởng ra sao?

### Bài 3 — PSA và write majority

Một PSA có P, S và A. S bị mất kết nối nhưng P và A vẫn giao tiếp tốt.

1. Có đủ quorum election không?
2. Primary có thể còn hoạt động không?
3. Ghi `w: 1` có thể còn thành công không?
4. Ghi `w: "majority"` bị ảnh hưởng thế nào?
5. Nếu P hỏng tiếp trước khi S nhận các ghi `w: 1`, rủi ro dữ liệu là gì?

### Bài 4 — So sánh PSS với PSA

Lập bảng PSS và PSA theo các yếu tố:

- Số voting members;
- Số data-bearing members;
- Quorum election;
- Ảnh hưởng khi mất một secondary;
- Ảnh hưởng khi mất primary;
- Khả năng ghi majority sau một sự cố;
- Chi phí storage/replication;
- Khả năng phục vụ read ở secondary.

Nêu vì sao **cùng ba voting members không có nghĩa có cùng độ bền dữ liệu**.

### Bài 5 — Priority 0 gây lỗi failover

Cấu hình:

```text
A: priority=3, votes=1
B: priority=0, votes=1
C: priority=0, votes=1
```

Khi A mất, B và C có hai phiếu. Vì sao vẫn không bầu được primary? Đề xuất một cấu hình mới cho phép B có thể failover nhưng vẫn ưu tiên A trong điều kiện ổn định.

### Bài 6 — Arbiter và failure domain

Có hai data-bearing nodes tại DC-A và DC-B, một arbiter tại DC-A.

1. Mất DC-A để lại những phiếu nào?
2. DC-B có thể tự elect primary không?
3. Nếu chuyển arbiter sang DC-C, election availability thay đổi thế nào?
4. Vì sao phương án ba DC với arbiter vẫn chưa tương đương ba data-bearing DC?

### Bài 7 — Tính RTO/RPO theo write concern

Một ứng dụng đơn hàng dùng PSA. Khi mất secondary, đội vận hành đề xuất đổi từ `w: "majority"` sang `w: 1` để duy trì ghi.

Hãy nêu:

- Tác động lên write latency và availability;
- Tác động tới rủi ro rollback/mất dữ liệu;
- Các điều kiện phải được phê duyệt trước khi hạ write concern;
- Cách thiết kế idempotency/retry cho endpoint tạo đơn hàng;
- Khi nào phải từ chối tiếp tục nhận giao dịch thay vì chấp nhận ghi chưa đủ bản sao.

### Bài 8 — Phân tích network partition

Một PSS có:

```text
A: P
B: S
C: S
```

Mạng bị chia A riêng, B và C cùng một phía. Hỏi:

1. Phía nào còn quorum?
2. Phía nào có thể elect primary?
3. Điều gì xảy ra với primary cũ A sau khi nhận ra mất quorum?
4. Client kết nối trực tiếp A có thể gặp lỗi gì?
5. Vì sao vẫn cần retry logic dù election đã ngăn split-brain kéo dài?

### Bài 9 — Kiểm tra cấu hình bằng mongosh

Trong môi trường được phép, chạy:

```javascript
rs.conf();
rs.status();
```

Ghi lại cho từng member:

- Host;
- Role/state;
- `priority`;
- `votes`;
- `arbiterOnly`;
- Health và replication lag.

Tính `V` và `Q`, xác định những data-bearing candidate có thể trở thành primary. Không tự chỉnh sửa cấu hình production trong bài tập.

### Bài 10 — Thiết kế hệ thống chịu mất một vùng

Ứng dụng đặt tại hai vùng và cần:

- Không mất những bản ghi đã được majority acknowledged trong tình huống failover bình thường;
- Có thể tiếp tục ghi majority khi mất một data-bearing member;
- Primary ưu tiên gần write traffic;
- Có bản sao dữ liệu ở failure domains độc lập.

Hãy so sánh PSA với PSS và đề xuất bố trí node theo vùng. Giải thích trade-off network latency, replication bandwidth, chi phí và quorum.

## 28. Tài liệu MongoDB tham khảo

- [MongoDB Replication](https://www.mongodb.com/docs/manual/replication/)
- [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [Replica Set Member Priority](https://www.mongodb.com/docs/manual/core/replica-set-priority-0-member/)
- [Replica Set Arbiters](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/)
- [Replica Set Configuration](https://www.mongodb.com/docs/manual/reference/replica-configuration/)
- [Replica Set Member Votes](https://www.mongodb.com/docs/manual/core/replica-set-voting/)
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [Set Default RW Concern](https://www.mongodb.com/docs/manual/reference/command/setDefaultRWConcern/)
- [Reconfigure Replica Set](https://www.mongodb.com/docs/manual/reference/method/rs.reconfig/)
- [Replica Set Member States](https://www.mongodb.com/docs/manual/reference/replica-states/)

## Kết luận

Trong MongoDB replica set, **`priority`**, **`votes`** và **`arbiter`** giải quyết **ba vấn đề khác nhau**.

- **`priority`** xác định khả năng và mức ưu tiên trở thành primary; priority cao **không tạo thêm phiếu**, còn `priority: 0` khiến node không làm primary.
- **`votes`** xác định thành viên nào tham gia election quorum; thêm non-voting secondary không tăng quorum, còn đổi votes có thể thay đổi trực tiếp khả năng chịu lỗi.
- **Arbiter** cung cấp phiếu bầu nhưng **không lưu dữ liệu**, nên không thay thế secondary trong việc đáp ứng majority write concern hoặc phục hồi dữ liệu.

Hai topology **PSS** và **PSA** có cùng ba phiếu, cùng election quorum hai phiếu, nhưng khác căn bản về **số bản sao dữ liệu**. Với PSA, trạng thái **primary + arbiter** có thể còn đủ phiếu bầu trong khi **không đủ data-bearing members** để hoàn tất các ghi yêu cầu `w: "majority"`. Đây là lý do thiết kế replica set không được dừng ở câu hỏi “còn bao nhiêu node” mà phải hỏi **còn bao nhiêu phiếu, còn bao nhiêu bản sao dữ liệu, còn candidate primary nào và write concern nào thực sự đáp ứng được**.

Khi yêu cầu chịu mất một node mà vẫn tiếp tục ghi majority, **ba data-bearing voting members** thường là điểm khởi đầu phù hợp hơn hai data-bearing members cộng arbiter. Quyết định cuối cùng phải dựa trên RPO/RTO, phân vùng mạng, replication lag, tài nguyên của primary dự phòng, failure domains và kết quả diễn tập failover. **Quorum bảo vệ quyền lãnh đạo; bản sao dữ liệu và write concern mới bảo vệ nội dung đã ghi.**

