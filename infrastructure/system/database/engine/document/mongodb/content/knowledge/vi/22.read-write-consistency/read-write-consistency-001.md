# Write concern: `w`, `j`, `wtimeout` và mức xác nhận ghi trong MongoDB

Khi ứng dụng gọi `insertOne()`, `updateOne()` hoặc `deleteOne()`, điều gì được bảo đảm vào thời điểm MongoDB trả lời “thành công”? Dữ liệu đã được primary nhận? Đã có secondary sao chép? Đã được ghi vào journal trên đĩa? Hay chỉ mới được gửi qua kết nối mà client không đợi phản hồi?

Trong MongoDB, câu trả lời phụ thuộc một phần quan trọng vào **write concern**. Đây là cấu hình quy định **mức xác nhận mà ứng dụng yêu cầu trước khi coi một thao tác ghi đã được acknowledged**. Một write concern thường được biểu diễn dưới dạng:

```javascript
{
  w: "majority",
  j: true,
  wtimeout: 5000
}
```

Ba thành phần có ý nghĩa khác nhau:

- **`w`**: yêu cầu bao nhiêu thành viên sao chép dữ liệu xác nhận, hoặc yêu cầu đa số bằng `"majority"`.
- **`j`**: có yêu cầu xác nhận ghi vào **on-disk journal** hay không, trong cấu hình/storage engine hỗ trợ journaling.
- **`wtimeout`**: giới hạn **thời gian chờ đạt write concern**, tính bằng mili giây.

Write concern thuộc chủ đề **Nhất quán đọc ghi**. Nó liên quan đến độ bền dữ liệu và ý nghĩa của phản hồi ghi, nhưng **không giống read concern, read preference, transaction hoặc quorum bầu cử primary**. Bài học đi từ cấu trúc replica set đến các trường hợp lỗi, rồi thực hành trong `mongosh` và MongoDB Java Sync Driver.

## 1. Các giai đoạn của một thao tác ghi

Giả sử replica set có một primary P và hai secondary S1, S2. Ứng dụng gửi một lệnh chèn document:

```text
                  ỨNG DỤNG
                     |
                     | insertOne(document)
                     v
                 PRIMARY P
                     |
          Áp dụng thay đổi trên P
                     |
          +----------+----------+
          |                     |
          v                     v
     Secondary S1          Secondary S2
     sao chép oplog        sao chép oplog
          |                     |
          v                     v
     Áp dụng bản ghi       Áp dụng bản ghi

          ----> Primary quyết định khi nào
                gửi acknowledgment theo write concern
```

Một thao tác ghi có thể trải qua các giai đoạn không đồng thời:

1. Client gửi yêu cầu đến server được xác định là writable primary.
2. Primary kiểm tra lệnh, áp dụng thay đổi và ghi nhận thay đổi phục vụ replication.
3. Các secondary sao chép và áp dụng những thay đổi tương ứng.
4. Theo journaling và write concern, các member liên quan có thể cần ghi thay đổi vào journal.
5. Khi điều kiện xác nhận được đáp ứng, server trả lời client; nếu không đáp ứng trong thời gian chờ, kết quả có thể chứa **write concern error/timeout**.

**Điểm then chốt:** “Primary đã áp dụng ghi”, “đủ bản sao xác nhận” và “journal đã ghi bền vững” là ba khái niệm khác nhau. Write concern cho ứng dụng lựa chọn **khi nào nhận được một phản hồi xác nhận đủ mạnh cho nhu cầu của mình**.

### Phản hồi ghi không biến tất cả công việc thành tức thời

Ngay cả khi dùng `w: "majority"`, vẫn có thể còn secondary đang lag hoặc chưa nhận được cập nhật. `majority` không có nghĩa **mọi** node trong replica set đã đồng bộ xong. Ngược lại, một thao tác `w: 1` được primary xác nhận không bảo đảm các secondary đã có bản sao.

## 2. Cú pháp write concern

Trong `mongosh`, có thể đặt write concern theo thao tác:

```javascript
db.orders.insertOne(
  {
    _id: "ord-1001",
    customerId: "C001",
    total: 250,
    status: "pending"
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
)
```

Ở ví dụ trên, `wtimeout: 5000` nghĩa là **5.000 mili giây**, không phải 5 giây viết trực tiếp trong cú pháp. Tùy môi trường, lệnh sẽ thành công khi đạt điều kiện write concern hoặc trả lỗi khi không đạt mức xác nhận yêu cầu.

| Tham số | Giá trị thường gặp | Ý nghĩa |
| --- | --- | --- |
| `w` | `0`, `1`, `2`, `3`, `"majority"` | Số member cần xác nhận, hoặc majority theo cấu hình |
| `j` | `true`, `false` | Có yêu cầu xác nhận journal hay không |
| `wtimeout` | `0`, số nguyên mili giây dương | Giới hạn thời gian chờ đáp ứng write concern |

Không nhất thiết phải chỉ rõ cả ba trường trong mọi lệnh. Khi một tùy chọn không được cung cấp, hành vi dựa trên **write concern mặc định có hiệu lực** và quy tắc server/driver tương ứng. Vì mặc định có thể khác theo topology và cấu hình, không nên suy đoán mức độ bền chỉ từ việc code không truyền `writeConcern`.

### Cú pháp trong database command

Thao tác ghi có thể được diễn đạt bằng lệnh `insert` trực tiếp:

```javascript
db.runCommand({
  insert: "orders",
  documents: [
    {
      _id: "ord-1002",
      customerId: "C002",
      total: 100,
      status: "pending"
    }
  ],
  writeConcern: {
    w: 2,
    j: true,
    wtimeout: 3000
  }
})
```

Ở lệnh này, `writeConcern` nằm trong command `insert`, không phải một field của document được chèn. Đây là điểm khác biệt giữa **cấu hình thao tác ghi** và **dữ liệu nghiệp vụ**.

## 3. `w: 0` — ghi không chờ xác nhận từ server

`w: 0` là mức **unacknowledged write concern**. Ứng dụng không yêu cầu server trả một xác nhận kết quả ghi theo cơ chế write concern thông thường:

```javascript
db.events.insertOne(
  { _id: "evt-01", kind: "page-view" },
  { writeConcern: { w: 0 } }
)
```

Với `w: 0`, không nên suy từ việc lời gọi phía client không báo lỗi rằng server chắc chắn đã lưu document. Lỗi ràng buộc dữ liệu, duplicate key hoặc lỗi ở phía server có thể không được phản hồi theo cách mà ghi acknowledged cung cấp.

**Không đồng nghĩa với không có lỗi ở phía client.** Một lỗi tạo command, đóng kết nối hoặc gửi dữ liệu vẫn có thể xuất hiện tùy driver và thời điểm xảy ra. Điều `w:0` loại bỏ là yêu cầu **chờ xác nhận ghi từ server**.

### Khi nào không nên dùng `w: 0`?

Đối với đơn hàng, thanh toán, điều chỉnh số dư, ghi nhận quyền truy cập hoặc sự kiện cần kiểm toán, `w: 0` thường không phù hợp. Ứng dụng cần biết liệu thao tác có được server nhận và xác nhận theo mức bền mong muốn hay không.

Ngay cả đối với telemetry có thể chấp nhận mất một số sự kiện, vẫn phải đánh giá xem client/driver, batch processing và cơ chế retry có hỗ trợ cách vận hành đó hay không. Không nên mặc định `w: 0` luôn làm hệ thống nhanh hơn về tổng thể hoặc an toàn để thay thế một hàng đợi sự kiện.

### `w: 0` và `j: true` không phải tổ hợp hợp lý

`j: true` yêu cầu chờ xác nhận journal, trong khi `w: 0` không chờ acknowledgment. Vì mục tiêu hai cấu hình mâu thuẫn, không dùng tổ hợp này; các phiên bản/driver có thể từ chối cấu hình không hợp lệ. Nếu ứng dụng cần biết dữ liệu đã ghi journal, phải chọn một mức `w` có xác nhận.

## 4. `w: 1` — primary xác nhận thao tác

`w: 1` yêu cầu **primary** xác nhận đã chấp nhận và áp dụng thao tác ghi theo quy tắc của server:

```javascript
db.orders.insertOne(
  {
    _id: "ord-1101",
    status: "pending",
    total: 75
  },
  { writeConcern: { w: 1 } }
)
```

Với replica set P–S–S:

```text
Client ---> P áp dụng ghi ---> ACK cho client
               |
               +----> S1 có thể chưa sao chép xong
               |
               +----> S2 có thể chưa sao chép xong
```

Khi ứng dụng nhận acknowledgment `w: 1`, thao tác đã được primary xác nhận, **không cần chờ secondary**. Tuy nhiên, nếu primary hỏng trước khi thay đổi được sao chép đến những thành viên cần thiết và một primary mới được bầu, một số thay đổi chưa majority commit có thể bị **rollback**.

### `w: 1` có luôn bền trên đĩa không?

Không nên khẳng định như vậy nếu không xét `j` và cấu hình journaling. Với `w: 1`, yêu cầu xác nhận dữ liệu đã được áp dụng trên primary không tự bằng yêu cầu **đã ghi on-disk journal**.

Nếu cần xác nhận journal của primary nhưng chưa cần chờ secondary, có thể dùng `w: 1, j: true`; tuy vậy mức đó **vẫn không có bảo đảm majority replication**. Độ bền trước một lỗi tiến trình/khởi động lại node và tính tồn tại sau **failover sang primary khác** là hai vấn đề khác nhau.

## 5. `w: 2`, `w: 3` và các giá trị số

Với `w` là số dương `n`, MongoDB yêu cầu thao tác ghi được xác nhận bởi **`n` data-bearing members phù hợp**, bao gồm primary, trước khi trả kết quả đáp ứng write concern.

Ví dụ replica set có P, S1 và S2:

```javascript
db.orders.updateOne(
  { _id: "ord-1101" },
  { $set: { status: "paid" } },
  { writeConcern: { w: 2, wtimeout: 5000 } }
)
```

Mức `w: 2` thường đòi hỏi primary và **ít nhất một secondary** đã nhận/áp dụng thay đổi phù hợp. Không cần cả S1 và S2 đều xong.

```text
P + S1 + S2 (ba data-bearing members)

w: 1  -> P
w: 2  -> P + ít nhất một secondary
w: 3  -> P + S1 + S2
```

Một vài điều cần nhớ:

- **`w: 2` không luôn tương đương majority.** Trong replica set có năm voters, election majority là ba phiếu, không phải hai.
- **`w: 3` không luôn có nghĩa ghi tới toàn bộ replica set.** Nếu có năm data-bearing members, vẫn có thể còn hai member chưa hoàn tất.
- **`w: n` không chọn cố định secondary nào** theo tên host. MongoDB xử lý xác nhận theo khả năng và trạng thái các member đủ điều kiện.
- **Arbiter không phải data-bearing member** nên không thể được tính như một nơi ghi dữ liệu để đáp ứng `w: 2` hoặc `w: 3`.

### Khi `w` lớn hơn khả năng sao chép thực tế

Nếu replica set chỉ có hai data-bearing members mà ứng dụng yêu cầu `w: 3`, write concern này không thể được đáp ứng trong topology hiện tại. Tùy trạng thái và phiên bản, thao tác có thể bị từ chối hoặc chờ rồi báo write concern error/timeout. Không để yêu cầu như vậy chờ vô hạn; cần cấu hình phù hợp với topology và đặt giới hạn thời gian chờ khi cần.

Không nên dùng `w: 3` chỉ vì “ba là số lớn nên an toàn”. Mức phù hợp phải gắn với **số member và mô hình lỗi** của replica set.

## 6. `w: "majority"` — xác nhận theo đa số phù hợp

`w: "majority"` yêu cầu thao tác ghi được xác nhận theo **write majority** của replica set. Đây là mức thường dùng khi ứng dụng muốn giảm rủi ro mất các ghi đã được acknowledged trong quá trình failover.

```javascript
db.orders.insertOne(
  {
    _id: "ord-1201",
    status: "paid",
    total: 300
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
)
```

Trong replica set ba **data-bearing voting members** P–S1–S2, yêu cầu majority thông thường đạt được khi thay đổi đã được xác nhận trên **hai trong ba member** phù hợp. Một secondary chậm không nhất thiết ngăn mọi thao tác `majority`, miễn là đủ member còn lại đáp ứng.

```text
P -- S1 -- S2

Voters = 3, election majority = 2
Data-bearing voting members = 3

w: "majority" -> cần mức xác nhận majority
                 thường tương ứng 2 data-bearing members
```

### Vì sao majority giúp bảo vệ trong failover?

Các tập đa số luôn có giao nhau. Khi một ghi đã đạt majority commit phù hợp và một primary mới được bầu đúng giao thức replica set, lịch sử đã majority commit được bảo vệ bởi các quy tắc replication/election. Điều này mạnh hơn một thao tác chỉ được primary cũ xác nhận bằng `w: 1`.

Tuy vậy, phải phân biệt:

- **Đã được primary áp dụng:** bản ghi tồn tại trên primary hiện tại.
- **Đã được majority acknowledged/committed:** trạng thái theo yêu cầu `w: "majority"` đã đạt.
- **Đã được journaled:** phụ thuộc `j` và cấu hình journal; majority replication không phải một từ đồng nghĩa cho journal trong mọi chế độ.
- **Đã được mọi member đồng bộ:** yêu cầu mạnh hơn majority và thường không cần thiết cho mỗi thao tác.

Không nên hứa “majority bảo đảm dữ liệu không thể mất trong mọi thảm họa”: hư hỏng đồng thời của phần cứng, lỗi vận hành, mất toàn bộ failure domains hoặc quy trình khôi phục không đúng vẫn là những rủi ro cần có backup và thiết kế hệ thống riêng.

## 7. Election quorum và write majority khác nhau như thế nào?

Trong replica set, từ “majority” có thể nói về **bầu cử primary** hoặc **xác nhận ghi**.

**Election quorum** trả lời: có đủ phiếu của voting members để duy trì/bầu primary không? Nếu `V` là số voting members trong cấu hình bầu cử có hiệu lực:

```text
electionMajority = floor(V / 2) + 1
```

**Write majority** trả lời: số **data-bearing voting members** cần thiết đã xác nhận ghi theo cơ chế majority chưa? Một arbiter có thể giúp bầu primary nhưng **không giữ dữ liệu để xác nhận ghi**.

### So sánh các topology

| Topology | Thành viên bỏ phiếu | Election quorum | Số data-bearing members | Yêu cầu majority write thường gặp |
| --- | ---: | ---: | ---: | --- |
| P–S–S | 3 | 2 | 3 | Hai data-bearing voting members |
| P–S–A (A = arbiter) | 3 | 2 | 2 | Hai data-bearing voting members |
| P và một S, cả hai có phiếu | 2 | 2 | 2 | Cần cả hai |
| Ba data voter và hai non-voting secondary | 3 | 2 | 5 | Majority được tính theo voting members, không đơn giản theo 5 data nodes |

Đối với các cấu hình có arbiter, cách MongoDB xác định **write majority count** có quy tắc riêng; hãy đọc thông tin server như `writeMajorityCount` khi được cung cấp, thay vì suy từ số process online hoặc đếm mọi secondary.

### Tình huống P–S–A bị mất S

```text
          P (primary, dữ liệu)
          |
          A (arbiter, bỏ phiếu)

          S (secondary, dữ liệu): mất kết nối
```

- **Bầu cử/giữ primary:** P + A có 2/3 phiếu, đủ election quorum.
- **`w: 1`:** primary P có thể xác nhận nếu lệnh được xử lý thành công.
- **`w: "majority"`:** arbiter không lưu dữ liệu; chỉ có P không đủ các bản sao dữ liệu cần thiết, nên lệnh có thể chờ hoặc báo write concern timeout.

Đây là lý do topology P–S–A không hoàn toàn tương đương P–S–S về độ bền ghi. Khi yêu cầu ghi bền theo majority, cần đánh giá số **data-bearing** members còn liên lạc, không chỉ số phiếu bầu.

## 8. `j: true` — xác nhận ghi journal trên đĩa

MongoDB sử dụng **write-ahead journal** với storage engine hỗ trợ để phục vụ phục hồi sau một số loại sự cố tiến trình/máy. Thay đổi có thể được áp dụng trong bộ nhớ và sau đó ghi ra journal theo cơ chế storage engine.

`j: true` là yêu cầu rằng acknowledgment phải đáp ứng điều kiện journal trước khi được coi là hoàn tất:

```javascript
db.orders.insertOne(
  {
    _id: "ord-1301",
    status: "pending",
    total: 400
  },
  {
    writeConcern: {
      w: 1,
      j: true,
      wtimeout: 5000
    }
  }
)
```

Trong ví dụ `w: 1, j: true`, ứng dụng yêu cầu xác nhận ghi trên primary **và điều kiện journal**, không yêu cầu một secondary phải sao chép xong.

### `j` không thay thế `w`

| Cấu hình | Điều được yêu cầu | Điều chưa được bảo đảm bởi riêng cấu hình này |
| --- | --- | --- |
| `{w:1}` | Primary xác nhận | Secondary đã sao chép, journal nếu không yêu cầu |
| `{w:1,j:true}` | Primary xác nhận cùng yêu cầu journal | Đủ bản sao majority để chống mất ghi khi failover |
| `{w:2,j:false}` | Hai data-bearing members xác nhận, không yêu cầu journal tường minh | Journal durability của các member |
| `{w:"majority",j:true}` | Majority write acknowledgment và journal theo ngữ nghĩa triển khai | Mọi secondary đã cập nhật, hay mọi rủi ro hạ tầng đều được loại bỏ |

Một thay đổi **đã journaled trên primary** vẫn có thể chưa được majority replicated. Nếu primary gặp sự cố và primary mới chọn lịch sử oplog khác, những ghi chưa majority committed có thể bị rollback theo cơ chế replication. Vì vậy, `j:true` và `w:"majority"` bảo vệ trước **những lớp rủi ro khác nhau**.

### `j: false` có nghĩa gì?

`j: false` nghĩa là thao tác **không yêu cầu điều kiện journal** trong acknowledgment. Nó **không tắt journaling của toàn bộ MongoDB** và không khẳng định journal sẽ không được ghi; storage engine vẫn có thể journal theo lịch riêng.

Nếu không chỉ rõ `j`, hành vi thực tế có thể phụ thuộc write concern, `writeConcernMajorityJournalDefault` và những thiết lập server/phiên bản khác. Không nên suy rằng `j` không xuất hiện luôn bằng `j:false` trong mọi tình huống.

### Majority và cấu hình journal mặc định

Trên replica set dùng storage engine có journaling, cơ chế `writeConcernMajorityJournalDefault` ảnh hưởng việc `w:"majority"` chờ ghi journal trước khi acknowledgment. Giá trị cấu hình và các quy tắc liên quan cần được đối chiếu trên server thực tế.

Khi ứng dụng có yêu cầu độ bền rõ ràng, hãy **xác định mức write concern/journal tường minh theo kiến trúc** và kiểm tra phiên bản, thay vì mô tả chung chung “majority là đã xuống đĩa” mà không xét cấu hình.

### Những giới hạn của yêu cầu journal

- Journal durability giảm rủi ro mất dữ liệu khi tiến trình hoặc máy bị sự cố theo cơ chế phục hồi được hỗ trợ.
- Nó không tương đương với sao lưu định kỳ, replication sang một site độc lập hoặc phòng vệ trước mọi lỗi ổ cứng.
- Việc bật journaling tường minh cho write concern có thể tăng độ trễ acknowledgment.
- Hành vi cụ thể phụ thuộc storage engine, phiên bản và cách MongoDB ghi/flush journal.

## 9. `wtimeout` — chờ xác nhận tối đa bao lâu?

`wtimeout` đặt giới hạn thời gian **chờ đạt write concern**, tính bằng **mili giây**:

```javascript
db.orders.updateOne(
  { _id: "ord-1301" },
  { $set: { status: "paid" } },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 4000
    }
  }
)
```

Trong ví dụ, nếu MongoDB không đáp ứng đủ điều kiện xác nhận majority/journal trong khoảng chờ, ứng dụng có thể nhận **write concern timeout/error**. Điều này **không có nghĩa MongoDB tự rollback thao tác đã áp dụng trên primary**.

### Timeout không đồng nghĩa thao tác chưa ghi

```text
Thời điểm 0 ms:
  Client gửi update
         |
         v
  Primary áp dụng update
         |
         v
  Secondary chưa xác nhận kịp
         |
         v
  Hết wtimeout
         |
         v
  Client nhận write concern error/timeout

Trạng thái thực tế:
  Update có thể đang tồn tại trên primary.
  Một số secondary có thể đã nhận.
  Một secondary có thể nhận sau thời điểm timeout.
```

Một write concern error phản ánh rằng **mức xác nhận được yêu cầu chưa được thỏa mãn trong điều kiện quan sát**, không đơn giản là “lệnh cập nhật chưa hề xảy ra”. Vì thế retry mù quáng có thể gây **tác dụng lặp**.

### Ví dụ lỗi retry với `$inc`

```javascript
db.wallets.updateOne(
  { _id: "wallet-01" },
  { $inc: { balance: 100 } },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 2000
    }
  }
)
```

Nếu client nhận timeout rồi phát lại **một thao tác `$inc` mới** mà không có cơ chế chống trùng, `balance` có thể tăng **hai lần** nếu thao tác đầu đã áp dụng. Đây là rủi ro nghiệp vụ, bất kể request thứ hai có cùng nội dung với request thứ nhất.

Đối với ghi không idempotent, cần thiết kế **operation ID duy nhất, điều kiện cập nhật, retryable writes tương thích, hoặc transaction/ledger đúng nghiệp vụ**. Retryable writes của driver có các quy tắc riêng về session, retry và tính đủ điều kiện; **không được hiểu** rằng bất kỳ lần gọi lại thủ công nào cũng tự động an toàn.

### `wtimeout: 0`

`wtimeout: 0` thường biểu thị **không đặt giới hạn thời gian write concern riêng**. Điều đó không bảo đảm request sẽ chờ vô hạn trong mọi hoàn cảnh: kết nối, server selection, thời hạn lệnh hoặc giới hạn khác vẫn có thể ngắt hoạt động.

Trong production, nên đặt timeout có chủ đích theo yêu cầu độ trễ, khả năng failover và chiến lược xử lý trạng thái ghi chưa rõ ràng; không chọn một con số quá thấp chỉ để API trả lời nhanh hơn.

## 10. Phân biệt `wtimeout`, connection timeout và server selection timeout

Một request ghi có thể gặp nhiều loại timeout ở các tầng khác nhau:

| Loại timeout | Xảy ra ở đâu? | Ý nghĩa gần đúng |
| --- | --- | --- |
| `wtimeout` | MongoDB chờ đáp ứng write concern | Lệnh ghi có thể đã được áp dụng nhưng chưa đủ xác nhận |
| Server selection timeout | Driver tìm server phù hợp, ví dụ writable primary | Có thể không chọn được primary để gửi lệnh |
| Connect timeout | Thiết lập kết nối mạng | Không thiết lập kết nối trong thời hạn |
| Socket/read timeout | Chờ dữ liệu phản hồi trên kết nối | Trạng thái thực thi trên server có thể chưa rõ |
| `maxTimeMS` hoặc các giới hạn thực thi khác khi được hỗ trợ | Thời hạn xử lý lệnh phía server | Khác với điều kiện chờ replication/journal |

Không nên chuyển tất cả loại timeout thành một thông báo nội bộ “MongoDB chưa ghi”. Một số lỗi xảy ra **trước khi gửi lệnh**, một số xảy ra **sau khi primary đã sửa dữ liệu**. Mỗi loại cần chính sách theo dõi và retry riêng.

### Phản hồi vẫn có thể chứa kết quả ghi kèm write concern error

Ở mức database command, một response có thể cho biết số document đã được insert/update thành công ở bước áp dụng lệnh, **đồng thời** có `writeConcernError` khi chưa đạt mức xác nhận yêu cầu.

```javascript
// Sơ đồ cấu trúc minh họa, không phải output thực tế
{
  ok: 1,
  n: 1,
  writeConcernError: {
    code: 64,
    errmsg: "waiting for replication timed out"
  }
}
```

Đừng kiểm tra duy nhất `ok: 1` rồi kết luận đã thỏa mọi điều kiện write concern. Ngược lại, cũng đừng xem `writeConcernError` như bằng chứng thao tác đã bị server hoàn tác.

Trong driver, lỗi write concern có thể được biểu diễn thành exception tương ứng; ứng dụng cần phân biệt nó với **write error** như duplicate key hoặc vi phạm schema validation.

## 11. Bảng quyết định mức xác nhận ghi

| Yêu cầu nghiệp vụ | Write concern có thể cân nhắc | Điểm phải đánh giá |
| --- | --- | --- |
| Telemetry có thể chấp nhận mất một số sự kiện | `w:0` trong trường hợp phù hợp | Không biết chắc server đã ghi; cần cơ chế xử lý mất/sót và hỗ trợ của driver |
| Ghi thao tác thường, chỉ cần primary ack | `w:1` | Rủi ro rollback khi failover |
| Primary ack và yêu cầu journal trên primary | `w:1,j:true` | Chưa có majority replication |
| Cần xác nhận trên hai data-bearing members | `w:2` | Không đồng nghĩa majority ở mọi topology |
| Ghi nghiệp vụ quan trọng, cần bảo vệ trước failover | `w:"majority"` | Độ trễ replication, data-bearing majority, chính sách journal |
| Ghi quan trọng và muốn yêu cầu journal rõ ràng | `w:"majority",j:true` | Đánh giá latency, journaling và hạ tầng |
| Không muốn chờ write concern quá lâu | Thêm `wtimeout` phù hợp | Timeout không tự rollback; cần xử lý unknown outcome |

Không có một cấu hình “mạnh nhất và luôn tốt nhất” cho mọi nghiệp vụ. Mức xác nhận cao hơn có thể làm tăng độ trễ hoặc giảm khả năng hoàn tất ghi khi replica set đang suy giảm. Mức quá thấp lại tăng rủi ro mất dữ liệu đã được ứng dụng coi là thành công.

### Một ví dụ đối chiếu độ trễ và mức bền

Giả sử primary ở khu vực A, secondary ở khu vực B và C. Khi độ trễ mạng từ A sang B/C tăng:

- `w: 1` có thể vẫn nhận acknowledgment sớm hơn vì không đợi secondary.
- `w: "majority"` có thể phải đợi một secondary trong topology ba voting data members, nên phản hồi chậm hơn.
- Nếu cả B và C không thể sao chép, primary có thể mất quorum bầu cử tùy khả năng liên lạc; nếu không còn writable primary, **không mức `w` nào biến một secondary thành primary hợp lệ**.

Độ trễ lớn không tự chứng minh cluster sai cấu hình. Cần đặt mục tiêu latency và durability rồi chọn cách phân bố member, write concern và timeout phù hợp.

## 12. Write concern mặc định và mức ưu tiên cấu hình

Một thao tác không ghi rõ `writeConcern` vẫn có **effective write concern**. Giá trị này có thể đến từ cấu hình mặc định của server/replica set, thiết lập client/driver, database hoặc collection, hoặc lựa chọn tường minh cho thao tác.

Ở góc nhìn ứng dụng, nên nhớ:

1. Một **write concern được chỉ rõ cho thao tác** thường được dùng cho thao tác đó.
2. Khi thao tác không chỉ rõ, nó có thể kế thừa cấu hình đặt ở collection/database/client hoặc mặc định cluster.
3. Khi server có **default write concern** được cấu hình ở cấp cluster, phải xét giá trị đó thay vì giả định một default cố định.
4. Những driver/framework khác nhau có cách truyền thừa tùy chọn riêng; cần đọc cấu hình đang được sử dụng và phiên bản thư viện.

### Mặc định có thể phụ thuộc arbiter và topology

Các phiên bản MongoDB hiện đại hỗ trợ **implicit default write concern**; nó thường là `w:"majority"` trong nhiều replica set, nhưng có trường hợp dùng `w:1` khi topology có arbiter và số data-bearing voting members hạn chế.

Vì vậy, không nên tuyên bố “MongoDB mặc định luôn `w:1`” hoặc “MongoDB mặc định luôn `w:majority`” mà không biết phiên bản và cấu hình cụ thể.

Trên các triển khai hỗ trợ và với quyền phù hợp, có thể kiểm tra:

```javascript
db.adminCommand({ getDefaultRWConcern: 1 })
```

Kết quả có thể hiển thị default write concern cùng nguồn cấu hình tùy phiên bản. Đây là lệnh **đọc thông tin cấu hình**, không thay đổi mặc định. Nếu ứng dụng có yêu cầu durability nghiêm ngặt, vẫn nên xác định mức xác nhận mong muốn một cách rõ ràng trong tài liệu thiết kế và cấu hình triển khai.

### Không nhầm với read concern và read preference

- **Write concern:** lệnh ghi phải được xác nhận đến mức nào.
- **Read concern:** mức nhất quán/độ mới được bảo đảm cho dữ liệu được đọc trong điều kiện tương ứng.
- **Read preference:** driver ưu tiên gửi thao tác đọc đến primary hay secondary nào.

Chọn `readPreference: secondary` không làm write concern cao hơn. Chọn `readConcern: "majority"` không bắt primary đợi journaling cho mọi thao tác ghi. Mỗi lựa chọn giải quyết một lớp yêu cầu khác nhau.

## 13. Bộ dữ liệu thực hành an toàn trong `mongosh`

Ví dụ bên dưới chỉ nên chạy trên replica set thực hành với dữ liệu riêng. Nếu chạy trên standalone MongoDB, khả năng dùng `w:"majority"`, `w:2` hoặc failover có thể không có ý nghĩa như trong replica set. Không ngắt mạng hoặc dừng member của hệ thống đang phục vụ dữ liệu thật để thử nghiệm.

Chọn database:

```javascript
use mongo_write_concern_lab
```

Tạo một document bằng insert với primary acknowledgment:

```javascript
db.orders.insertOne(
  {
    _id: "order-WC-01",
    customerId: "C01",
    status: "pending",
    total: 200,
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: 1,
      wtimeout: 5000
    }
  }
)
```

Nếu lệnh này thành công và server có writable primary, document đã được xác nhận ở mức `w:1`. Ví dụ không chứng minh các secondary đã sao chép.

### Cập nhật với majority

```javascript
db.orders.updateOne(
  {
    _id: "order-WC-01",
    status: "pending"
  },
  {
    $set: { status: "paid" },
    $currentDate: { paidAt: true }
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
)
```

Lệnh dùng điều kiện `status: "pending"` để tránh vô tình chuyển một đơn đã hủy sang `paid`. Nếu lệnh được acknowledged với write concern yêu cầu, ứng dụng có mức xác nhận mạnh hơn so với `w:1`. Nếu `matchedCount = 0`, cần kiểm tra trạng thái nghiệp vụ; không tự động kết luận đó là lỗi replication.

### Xóa với write concern

```javascript
db.orders.deleteOne(
  { _id: "order-WC-01", status: "paid" },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
)
```

Write concern áp dụng cho **các thao tác ghi** như insert/update/delete, không chỉ insert. Một lệnh xóa được majority acknowledged cũng có ý nghĩa xác nhận tương ứng. Không thử xóa document nếu đang dùng dữ liệu cần giữ; ví dụ này chỉ dành cho lab.

### Không chạy các ví dụ theo thứ tự ngẫu nhiên

Nếu chạy lệnh `deleteOne()` trước, các ví dụ update sau đó không tìm thấy document. Khi chạy lại `insertOne()` trên cùng `_id`, MongoDB có thể trả duplicate key. Những phản hồi đó thuộc **ngữ nghĩa thao tác dữ liệu**, không phải bằng chứng write concern thất bại.

## 14. Xem trạng thái replication trước khi kết luận về write concern

Trên replica set, dùng các lệnh đọc:

```javascript
rs.status()
```

```javascript
rs.conf()
```

```javascript
db.adminCommand({ hello: 1 })
```

Trong nhiều phiên bản MongoDB, `rs.status()` có các trường mô tả thành viên, trạng thái `PRIMARY`/`SECONDARY`/`ARBITER`, tiến độ replication và một số bộ đếm majority:

| Thông tin cần đọc | Vì sao quan trọng? |
| --- | --- |
| `members[].stateStr` | Có writable primary và secondary có thể sao chép không? |
| `members[].health` | Primary có nhìn thấy member khác không? |
| `members[].optime` hoặc thông tin tương đương | Các secondary có bị chậm so với primary không? |
| `votingMembersCount` | Quy mô nhóm bỏ phiếu theo server, khi trường này có |
| `majorityVoteCount` | Majority bầu cử theo server, khi có |
| `writeMajorityCount` | Ngưỡng xác nhận majority write theo server, khi có |
| `members[].arbiterOnly` hoặc `rs.conf().members` | Phân biệt node có phiếu với node giữ dữ liệu |

Không nhất thiết mọi version trả đúng tất cả trường trên cùng đường dẫn; đây là danh sách **các thông tin cần tìm**, không phải schema JSON bắt buộc.

### Tính số voters không đồng nghĩa tính write majority

```javascript
const cfg = rs.conf();
const voters = cfg.members.filter(m => m.votes === 1);
const electionQuorum = Math.floor(voters.length / 2) + 1;

printjson({
  votingMembers: voters.length,
  electionQuorum,
  arbiters: cfg.members.filter(m => m.arbiterOnly === true)
                       .map(m => m.host)
});
```

Đoạn này minh họa **election quorum** của một cấu hình ổn định thông thường. Nó **không phải** thuật toán thay thế việc server tính `writeMajorityCount` trong mọi cấu hình đặc biệt, reconfiguration hoặc newly added member.

### Khi `w:"majority"` chậm bất thường

Kiểm tra các nhóm nguyên nhân:

1. Secondary bị lag hoặc mất kết nối nên chưa xác nhận đủ.
2. Độ trễ mạng/journal/I/O làm thời gian acknowledgment tăng.
3. Cấu hình có arbiter nhưng không còn đủ data-bearing voters để đạt majority write.
4. Hệ thống đang failover hoặc không có writable primary.
5. `wtimeout` đặt quá thấp so với mục tiêu latency và tình trạng hạ tầng.

Đừng chữa bằng cách tự động hạ `w` xuống 1 cho mọi ghi quan trọng mà chưa xem xét rủi ro rollback và mục tiêu độ bền.

## 15. Java MongoDB Sync Driver: khai báo write concern

MongoDB Java Sync Driver hỗ trợ lớp `com.mongodb.WriteConcern`. Có thể xây mức xác nhận cho một collection để các thao tác ghi trên collection đó dùng cấu hình đã chọn.

```java
import com.mongodb.MongoWriteConcernException;
import com.mongodb.MongoWriteException;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class WriteConcernDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        WriteConcern durableMajority = WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(5000, TimeUnit.MILLISECONDS);

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("mongo_write_concern_lab");

            MongoCollection<Document> orders =
                db.getCollection("orders")
                  .withWriteConcern(durableMajority);

            orders.insertOne(
                new Document("_id", "order-java-WC-01")
                    .append("status", "pending")
                    .append("total", 350)
            );

            orders.updateOne(
                Filters.and(
                    Filters.eq("_id", "order-java-WC-01"),
                    Filters.eq("status", "pending")
                ),
                Updates.set("status", "paid")
            );

            System.out.println(
                "Đã hoàn tất các lệnh theo write concern cấu hình"
            );
        } catch (MongoWriteConcernException e) {
            System.err.println(
                "Chưa đạt mức xác nhận ghi yêu cầu: " + e.getMessage()
            );
            System.err.println(
                "Không được coi đây là bằng chứng ghi đã bị rollback"
            );
        } catch (MongoWriteException e) {
            System.err.println(
                "Lỗi thao tác ghi (ví dụ duplicate key): "
                + e.getMessage()
            );
        }
    }
}
```

Ví dụ yêu cầu dependency **MongoDB Java Sync Driver** phù hợp, một replica set có primary và biến môi trường `MONGODB_URI`. `withWriteConcern()` trả về một collection handle có cấu hình mới; nó không sửa mọi collection đang có trong database.

`MongoWriteConcernException` và `MongoWriteException` được nêu để phân biệt hai nhóm lỗi chính; ứng dụng thật còn cần xử lý lỗi kết nối, lựa chọn server, timeout và các loại `MongoException` khác theo chiến lược đã chọn.

### Các kiểu write concern trong Java

```java
// Primary acknowledgment
WriteConcern primaryAck = WriteConcern.ACKNOWLEDGED;

// Không yêu cầu server acknowledgment (thận trọng khi sử dụng)
WriteConcern unacknowledged = WriteConcern.UNACKNOWLEDGED;

// Yêu cầu số member cụ thể
WriteConcern twoMembers = new WriteConcern(2);

// Majority và journal, có thời gian chờ write concern
WriteConcern strict = WriteConcern.MAJORITY
    .withJournal(true)
    .withWTimeout(5, TimeUnit.SECONDS);
```

Không đặt `WriteConcern.UNACKNOWLEDGED` cho các giao dịch/tác vụ cần xác nhận thành công; việc có thể cấu hình `w:0` không có nghĩa nó phù hợp với mọi thao tác của Java Driver.

### Thứ tự kế thừa trong driver

Trong Java, có thể đặt write concern ở nhiều cấp:

```java
MongoDatabase dbWithConcern = client
    .getDatabase("mongo_write_concern_lab")
    .withWriteConcern(WriteConcern.MAJORITY);

MongoCollection<Document> orders = dbWithConcern
    .getCollection("orders")
    .withWriteConcern(
        WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(5, TimeUnit.SECONDS)
    );
```

Cấu hình collection handle được dùng cho các thao tác thực hiện qua handle đó; không được suy rằng nó tự động thay đổi mọi đường truy cập collection khác trong ứng dụng.

### Với transaction

Đối với multi-document transaction, write concern là yếu tố quan trọng tại **commit**, không phải một tùy chọn tùy ý gắn vào từng câu lệnh bên trong transaction. Ứng dụng cần cấu hình **TransactionOptions** và bảo đảm mức xác nhận phù hợp với mục tiêu durability; không cố đặt `w:0` hoặc giải quyết vấn đề giao dịch bằng một write concern per-operation bên trong transaction.

Một transaction đã `commitTransaction()` nhưng client nhận lỗi mạng hoặc timeout có thể có trạng thái commit chưa rõ đối với client; cần xử lý theo **error labels và transaction retry guidance** của driver. Write concern không tự thay thế cơ chế retry commit và xử lý idempotency.

## 16. Mối liên hệ giữa write concern, rollback và retry

Xem ba tình huống theo dòng thời gian:

### Tình huống A: `w:1`, primary lỗi trước khi secondary nhận dữ liệu

```text
Client -> P ghi X -> P ack w:1 -> client báo thành công
                  |
                  +-- S1 chưa có X
                  +-- S2 chưa có X
                  |
                  v
                P lỗi
```

Khi S1 hoặc S2 được bầu làm primary mới, ghi X chưa majority commit trên primary cũ **có thể bị rollback**. Việc client từng nhận `w:1` không ngăn được khả năng này.

### Tình huống B: `w:"majority"`, đủ secondary xác nhận

```text
Client -> P ghi X
          |
          +--> S1 đã sao chép X
          |
          +--> đủ majority -> ACK
```

Với yêu cầu majority và những điều kiện journaling/commit cần thiết, ghi X có mức bảo vệ tốt hơn trước failover. Không đòi hỏi S2 phải hoàn tất nếu đã đủ majority; S2 có thể tiếp tục đồng bộ sau.

### Tình huống C: `w:"majority"` hết hạn chờ

```text
Client -> P ghi X
          |
          +--> S1 chậm / mất kết nối
          |
          +--> wtimeout -> write concern error
          |
          +--> sau đó S1 có thể nhận X
```

Ứng dụng **không biết chỉ từ timeout** liệu X đã đạt majority ngay sau đó hay chưa. Nếu tự tạo một thao tác ghi mới giống X, hậu quả phụ thuộc tính idempotent của thao tác.

### Hướng thiết kế để giảm rủi ro ghi lặp

- Ghi document với một `_id` hoặc business operation ID duy nhất, áp dụng unique index phù hợp.
- Dùng điều kiện cập nhật theo trạng thái hoặc version khi có thể.
- Với `$inc`, trừ tiền hoặc tạo giao dịch, dùng cơ chế **ledger/operation ID** để phát hiện thao tác đã áp dụng.
- Sử dụng retryable writes/transactions theo khả năng của driver và version server, phân biệt một retry driver của **cùng logical write** với một lời gọi ghi mới.
- Khi không rõ kết quả, kiểm tra trạng thái nghiệp vụ trước khi khởi tạo thao tác mới; đọc lại không luôn giải quyết mọi cạnh tranh nếu không có khóa/idempotency rõ ràng.

Write concern xác định mức xác nhận, còn **chống xử lý trùng là một vấn đề nghiệp vụ độc lập**.

## 17. Thời điểm ghi “thành công” chưa nói hết về tính nhất quán đọc

Giả sử ứng dụng ghi document bằng `w:"majority"`, rồi một màn hình khác đọc từ secondary:

```text
          Ghi majority thành công
                    |
        Client B đọc secondary S2
                    |
          S2 có thể đang lag
```

Write concern mạnh không tự bảo đảm **mọi lần đọc ở mọi secondary đều thấy ngay dữ liệu mới**, bởi còn có read preference và read concern. Một secondary có thể phục vụ dữ liệu cũ hơn tùy cấu hình đọc và trạng thái replication.

Các yêu cầu như:

- **Read-your-writes:** cùng một luồng nghiệp vụ phải thấy thay đổi vừa ghi.
- **Monotonic reads:** lần đọc sau không thấy trạng thái cũ hơn lần đọc trước.
- **Causal consistency:** nhiều thao tác cùng session được quan sát đúng quan hệ nhân quả.

cần xem xét phối hợp **write concern, read concern, session** và điều kiện topology. Không nên dùng mỗi `w:"majority"` làm lời giải cho mọi dạng nhất quán đọc.

Đặc biệt, `readConcern: "majority"` liên quan đến dữ liệu đã majority committed mà thao tác đọc được phép quan sát; nó không đồng nghĩa “đọc từ mọi secondary luôn là bản cập nhật mới nhất” và không thay thế `linearizable` read khi yêu cầu tương ứng.

## 18. Những lỗi và nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “`w:1` chắc chắn dữ liệu đã được lưu ở secondary” | Chỉ đòi primary xác nhận | Muốn replication acknowledgment cần mức `w` tương ứng |
| “`w:2` luôn là majority” | Phụ thuộc số voting members và topology | Dùng `"majority"` khi mục tiêu là majority |
| “`w:3` nghĩa là ghi lên tất cả node” | Replica set có thể có hơn ba data-bearing members | Số `w` là ngưỡng xác nhận, không phải số node tổng |
| “Arbiter tính là một data-bearing acknowledgment” | Arbiter không lưu dữ liệu | Arbiter chỉ giúp bầu cử |
| “P–S–A còn P+A nên majority write vẫn chắc thành công” | Chỉ còn một data-bearing member | Election quorum khác majority write |
| “`j:true` nghĩa là mọi secondary đã nhận dữ liệu” | Journal và replication là hai lớp khác nhau | Kết hợp `w` và `j` tùy mục tiêu |
| “`j:false` tắt journaling của server” | Chỉ không yêu cầu xác nhận journal trong write concern | Journaling của storage engine là cấu hình riêng |
| “`wtimeout` là toàn bộ thời hạn kết nối từ client” | Chỉ giới hạn chờ write concern | Phân biệt socket/connect/server selection timeout |
| “Timeout đồng nghĩa MongoDB đã rollback ghi” | Ghi có thể đã áp dụng trên primary | Xử lý trạng thái chưa rõ và idempotency |
| “Lệnh trả `ok:1` là mọi điều kiện write concern đã đạt” | Response có thể kèm `writeConcernError` | Đọc đủ kết quả và lỗi |
| “Bật retry là mọi `$inc` đều không bị lặp” | Retry thủ công tạo logical write mới có thể áp dụng lại | Dùng operation ID, conditional update và driver retry đúng cách |
| “MongoDB mặc định luôn cùng một write concern” | Default phụ thuộc version, topology và cấu hình | Kiểm tra effective write concern |
| “Ghi majority thì đọc bất kỳ secondary nào cũng luôn mới nhất” | Secondary có thể lag; read policy khác | Thiết kế read concern/read preference/session |
| “`w:0` nghĩa là lệnh đã được server chấp nhận chắc chắn” | Không đợi acknowledgment | Không suy ra trạng thái server từ thành công phía client |
| “Có primary thì mọi `w:majority` đều ack được” | Có thể thiếu data-bearing members để đạt majority | Kiểm tra replication và write majority |
| “`wtimeout:0` bảo đảm client sẽ không bao giờ timeout” | Các giới hạn khác vẫn tồn tại | Phân biệt timeout theo tầng |

## 19. Bài tập thực hành

### Bài 1. So sánh `w:1` và `w:"majority"`

Replica set P–S1–S2 có ba voting data-bearing members. Primary P đã áp dụng một lệnh ghi nhưng S1 và S2 chưa sao chép xong.

Hỏi `w:1` có thể ack chưa? `w:"majority"` đã đạt chưa?

**Đáp án:** `w:1` có thể được P xác nhận theo điều kiện của cấu hình; `w:"majority"` chưa đạt nếu chỉ P có thay đổi và chưa đủ data-bearing members cần thiết. Khi ít nhất một secondary phù hợp xác nhận theo cơ chế majority, yêu cầu này mới có thể hoàn tất.

### Bài 2. `j:true` không thay replication

Một ứng dụng dùng `{w:1,j:true}` và nhận thành công. Có thể kết luận ghi đã ở ít nhất hai node không?

**Đáp án:** Không. Mức này yêu cầu primary acknowledgment cùng điều kiện journal, không yêu cầu một secondary xác nhận. Vẫn có rủi ro rollback của những ghi chưa majority committed khi failover.

### Bài 3. P–S–A khi secondary mất kết nối

Replica set có P (primary), S (secondary) và A (arbiter), cả ba có phiếu. S lỗi, P và A liên lạc được. Hỏi:

1. P có thể còn election quorum không?
2. `w:1` có thể được P xác nhận không?
3. `w:"majority"` có thể được đáp ứng chỉ nhờ P và A không?

**Đáp án:** (1) Có, P+A đủ 2/3 phiếu. (2) Có thể, nếu P vẫn là writable primary và thao tác không lỗi. (3) Không, vì A không giữ dữ liệu; majority write của topology này cần sự tham gia của data-bearing secondary.

### Bài 4. `wtimeout` và kết quả không rõ

Chạy:

```javascript
db.counters.updateOne(
  { _id: "visits" },
  { $inc: { count: 1 } },
  { writeConcern: { w: "majority", wtimeout: 1000 } }
)
```

Lệnh báo write concern timeout. Có nên gửi một `$inc` mới ngay để “chắc chắn ghi đã diễn ra”?

**Đáp án:** Không nên retry mù quáng. Primary có thể đã áp dụng lần tăng đầu. Nếu gửi một logical write khác, `count` có thể tăng hai lần. Cần cơ chế nhận diện operation/idempotency hoặc retryable writes phù hợp, và xử lý trạng thái chưa rõ.

### Bài 5. Viết lệnh `insertOne` có majority và journal

Yêu cầu chèn document có `_id: "tx-001"` vào `db.payments`, xác nhận majority, journal và giới hạn chờ 8 giây.

**Đáp án:**

```javascript
db.payments.insertOne(
  {
    _id: "tx-001",
    amount: NumberDecimal("150.00"),
    status: "recorded"
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 8000
    }
  }
)
```

Nếu chạy lại với cùng `_id` sau khi thao tác trước đã thành công, có thể nhận duplicate key. Đây có thể là tín hiệu cần **đối chiếu trạng thái của giao dịch**, không nên coi duplicate key đơn giản như một thao tác thành công mới.

### Bài 6. Chọn `w` theo topology

Một replica set có năm voting data-bearing members. Ứng dụng yêu cầu `w:2`. Hỏi có tương đương `w:"majority"` không?

**Đáp án:** Không. Election majority của năm voters là ba; majority write trong topology này cần ngưỡng tương ứng ba data-bearing voting members. `w:2` chỉ đòi hai member xác nhận, nên yếu hơn `w:"majority"` trong ví dụ.

### Bài 7. Đọc lỗi `writeConcernError`

Một database command trả:

```javascript
{
  ok: 1,
  n: 1,
  writeConcernError: {
    errmsg: "waiting for replication timed out"
  }
}
```

Có thể suy ra document chắc chắn chưa được tạo không?

**Đáp án:** Không. Phản hồi cho thấy lệnh ghi có thể đã được áp dụng, nhưng mức replication/journal acknowledgment chưa được thỏa mãn theo yêu cầu. Cần đối chiếu dữ liệu và chính sách retry theo nghiệp vụ; không dựa vào write concern timeout để khẳng định thao tác bị rollback.

### Bài 8. Khi nào `w:"majority"` vẫn chưa đủ cho nhất quán đọc?

Ứng dụng ghi một document với majority write concern rồi đọc từ một secondary lag và không thấy document mới. Có mâu thuẫn không?

**Đáp án:** Không nhất thiết. Majority write acknowledgment không bảo đảm **mọi secondary đã áp dụng thay đổi ngay lập tức**. Cần cân nhắc read concern, read preference và causal consistency/session theo nhu cầu, thay vì coi `w:"majority"` là lệnh buộc mọi secondary đọc mới nhất.

### Bài 9. Đọc write concern mặc định

Một dịch vụ không chỉ rõ `writeConcern` khi gọi `insertOne()`. Có thể kết luận chắc chắn đó là `w:1` không?

**Đáp án:** Không. Mức có hiệu lực còn phụ thuộc topology, version, default write concern của cluster và cấu hình driver/collection. Khi cần mức bền cụ thể, cấu hình có chủ đích và kiểm tra những giá trị mặc định được áp dụng.

### Bài 10. Một lỗi không liên quan đến write concern

Collection có unique index trên `orderCode`. Một thao tác insert dùng `{w:"majority",j:true}` nhưng giá trị `orderCode` bị trùng. Tăng `wtimeout` có sửa được không?

**Đáp án:** Không. Duplicate key là lỗi **thực thi thao tác ghi do ràng buộc dữ liệu**, không phải lỗi chưa đủ thời gian chờ replication/journal. Phải sửa dữ liệu hoặc xử lý trường hợp trùng khóa theo nghiệp vụ.

## 20. Quy trình chọn write concern trong dự án

Khi triển khai một dịch vụ ghi dữ liệu MongoDB, nên trả lời các câu hỏi theo thứ tự:

1. **Mức độ quan trọng của dữ liệu:** có thể mất một số log không, hay đây là đơn hàng/giao dịch không được mất xác nhận?
2. **Topology thật:** có bao nhiêu data-bearing voting members? Có arbiter? Các member đặt ở failure domains nào?
3. **Mục tiêu sau failover:** có cần bảo vệ những ghi đã được ứng dụng báo thành công khỏi rollback trong failover thông thường không?
4. **Journal durability:** có cần yêu cầu journal một cách tường minh? Mặc định journaling của môi trường là gì?
5. **Độ trễ cho phép:** muốn chờ tối đa bao lâu để đạt acknowledgment? Timeout nào thuộc write concern và timeout nào thuộc mạng/driver?
6. **Hành vi khi lỗi:** write concern error được xử lý thế nào? Có operation ID hoặc cách retry an toàn cho ghi không idempotent không?
7. **Chính sách đọc tiếp theo:** ứng dụng cần read-your-writes hay causal consistency? Có đọc từ secondary không?
8. **Quan sát vận hành:** có theo dõi replication lag, primary availability, write concern errors và số lần retry không?

Với nghiệp vụ quan trọng, một thiết kế phổ biến là dùng **`w:"majority"` với chính sách journal phù hợp**, timeout đủ hợp lý cho hạ tầng và cơ chế xử lý trạng thái chưa rõ. Tuy nhiên, lựa chọn cuối cùng phải dựa trên dữ liệu thực, yêu cầu độ bền, chấp nhận độ trễ và kiến trúc replica set.

## 21. Tổng kết

Write concern mô tả **mức xác nhận của thao tác ghi**:

- **`w:0`**: không chờ server acknowledgment; không suy ra ghi đã thành công.
- **`w:1`**: primary xác nhận; secondary có thể chưa sao chép và ghi chưa majority committed có thể bị rollback.
- **`w:n`**: yêu cầu `n` data-bearing members xác nhận; không tự đồng nghĩa majority.
- **`w:"majority"`**: yêu cầu xác nhận ở mức majority của replica set, giúp bảo vệ các ghi đã commit trước những failover thông thường theo giao thức.
- **`j:true`**: yêu cầu điều kiện journal; **journal durability không thay replication majority**.
- **`wtimeout`**: giới hạn thời gian chờ xác nhận; **timeout không đồng nghĩa thao tác chưa được áp dụng hoặc đã bị rollback**.

Để vận dụng đúng, hãy phân biệt **primary acknowledgment**, **replica acknowledgment**, **journal acknowledgment**, **quorum bầu cử** và **tính nhất quán của thao tác đọc**. Kết hợp write concern phù hợp với topology, cơ chế chống ghi lặp, theo dõi replication và chính sách đọc sẽ giúp ứng dụng MongoDB đưa ra những lời hứa đáng tin cậy về trạng thái ghi và độ bền dữ liệu.
