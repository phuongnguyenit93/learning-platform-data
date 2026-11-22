# Quorum, thành viên bỏ phiếu và điều kiện có primary trong MongoDB Replica Set

Một **replica set** là nhóm các tiến trình `mongod` cùng duy trì bản sao của một tập dữ liệu. Trong trạng thái hoạt động thông thường, replica set có **một primary** nhận các thao tác ghi, còn các **secondary** sao chép thay đổi từ primary và có thể trở thành primary khi xảy ra sự cố. Để hệ thống không tùy tiện tạo hai primary độc lập khi mạng bị chia cắt, MongoDB sử dụng **bầu cử dựa trên đa số phiếu**.

Ba câu hỏi cốt lõi của bài học là:

1. **Quorum là bao nhiêu?** Bao nhiêu phiếu cần có để bầu được primary?
2. **Ai có phiếu bầu?** Data-bearing member, non-voting secondary và arbiter đóng vai trò gì?
3. **Khi nào có primary?** Điều kiện đa số là cần thiết, nhưng vì sao đôi khi vẫn không bầu được primary dù còn đủ số node?

Hiểu ba câu hỏi này giúp giải thích những tình huống quen thuộc: replica set hai node mất một node thì ngừng có primary; replica set ba node thường chịu được một node lỗi; cấu hình hai data node và một arbiter vẫn có hạn chế với ghi `w: "majority"`; một node `priority: 0` có thể bỏ phiếu nhưng không được làm primary.

## 1. Primary, secondary, arbiter và phiếu bầu

Các member trong replica set không nhất thiết có cùng quyền bầu cử và khả năng trở thành primary.

| Loại member | Chứa dữ liệu? | Có thể bỏ phiếu? | Có thể thành primary? |
| --- | --- | --- | --- |
| Data-bearing member thông thường, `votes: 1, priority > 0` | Có | Có | Có, nếu đủ điều kiện và thắng bầu cử |
| Data-bearing member `votes: 1, priority: 0` | Có | Có | Không |
| Non-voting secondary `votes: 0, priority: 0` | Có | Không | Không |
| Arbiter `arbiterOnly: true` | Không lưu bản sao dữ liệu ứng dụng | Có, trong cấu hình thông thường | Không |

**Primary** bản thân cũng là một data-bearing voting member đang giữ vai trò lãnh đạo; nó có thể mất vai trò khi không còn đủ đa số, lỗi tiến trình, bị cấu hình lại hoặc có cuộc bầu cử mới.

**Secondary** sao chép oplog và duy trì dữ liệu. Một secondary có thể được chỉ định không đủ điều kiện để trở thành primary, nhưng vẫn hữu ích cho đọc, sao lưu hoặc xử lý dữ liệu theo thiết kế hệ thống.

**Arbiter** tham gia bỏ phiếu nhưng không chứa dữ liệu và không thể nhận dữ liệu để xác nhận ghi như một secondary. Vì vậy, việc thêm arbiter không tương đương thêm một bản sao dữ liệu an toàn.

### Hai thuộc tính cần phân biệt: `votes` và `priority`

Trong replica set configuration, một data-bearing member có thể có:

```javascript
{
  _id: 1,
  host: "mongo-b.example.net:27017",
  votes: 1,
  priority: 0
}
```

Đây là **voting secondary**, không được ứng cử primary. Nếu ngược lại:

```javascript
{
  _id: 2,
  host: "mongo-c.example.net:27017",
  votes: 0,
  priority: 0
}
```

thành viên vẫn có thể lưu và sao chép dữ liệu, nhưng **không có phiếu bầu** và **không trở thành primary**. Trong cấu hình MongoDB, member có `votes: 0` phải có `priority: 0`; không thể đặt `votes: 0, priority: 1` rồi mong nó trở thành primary.

`priority` cho biết mức ưu tiên làm primary giữa các member có thể ứng cử. **Priority không biến một phiếu thành hai phiếu**, không thay đổi công thức quorum và không giúp một phía thiểu số thắng bầu cử.

## 2. Quorum bầu cử là đa số phiếu của cấu hình

Giả sử replica set có `V` **voting members**, mỗi member có một phiếu hoặc không có phiếu. Số phiếu tối thiểu để đạt đa số là:

```text
majorityVotes = floor(V / 2) + 1
```

Đây là **đa số nghiêm ngặt**, nghĩa là **lớn hơn một nửa**, không phải “bằng một nửa”.

| Số voting members `V` | Quorum tối thiểu | Có thể mất tối đa bao nhiêu voting members mà vẫn còn đủ phiếu? |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

Bảng giả định các member còn lại **có thể liên lạc với nhau** và có **ít nhất một data-bearing voting member đủ điều kiện ứng cử**. Số node còn chạy không tự bảo đảm có primary nếu các node bị tách thành các nhóm không liên lạc được hoặc các ứng viên đều có `priority: 0`.

### Điểm cần nhớ: mẫu số không tự giảm khi node bị lỗi

Với cấu hình ba voting members, quorum là **2**. Nếu một node hỏng, số phiếu cần vẫn là **2**, không trở thành một vì hiện chỉ còn hai node sống. Với cấu hình năm voting members, quorum vẫn là **3** khi hai node lỗi.

Điều kiện quorum dựa trên **cấu hình bầu cử có hiệu lực**, không phải số tiến trình `mongod` bạn tình cờ nhìn thấy đang online. Việc thay đổi cấu hình voting members là một thao tác quản trị riêng, không phải phép điều chỉnh tự động sau mỗi lỗi mạng.

### Vì sao đa số ngăn hai phe cùng giành quyền?

Một tính chất quan trọng của hai tập đa số là **chúng luôn có ít nhất một phiếu chung**.

```text
Replica set có 5 phiếu, quorum = 3

Phe A có 3 phiếu: A, B, C
Phe B có 3 phiếu: C, D, E

Hai tập đa số giao nhau ở C.
```

Trong giao thức bầu cử, member kiểm soát việc bỏ phiếu theo term và trạng thái hiện tại. Tính chất giao nhau của quorum cùng với cơ chế term/vote giúp replica set tránh duy trì hai primary hợp lệ cho cùng một nhiệm kỳ bầu cử trong các trường hợp mạng phân vùng thông thường.

**Không nên diễn giải thành “không bao giờ có giai đoạn một primary cũ chưa kịp biết mình đã mất đa số”.** Khi mạng biến động, một node có thể tạm thời mang trạng thái cũ trước khi phát hiện thất bại và step down. Ứng dụng phải xử lý lỗi/retry và dùng write concern thích hợp; cơ chế đa số là nền tảng giữ tính nhất quán, không phải cam kết rằng mọi client sẽ thấy chuyển đổi vai trò tức thời.

## 3. Điều kiện để một replica set có primary

Đa số phiếu bầu là **điều kiện cần**, nhưng không phải điều kiện duy nhất. Để một cuộc bầu cử thành công, cần:

1. **Có một data-bearing member đủ điều kiện ứng cử**: member được phép trở thành primary, thông thường có `votes: 1`, `priority > 0`, đang ở trạng thái phù hợp và đủ điều kiện theo giao thức bầu cử.
2. **Ứng viên liên lạc và nhận được số phiếu đa số** từ các voting members theo cấu hình có hiệu lực.
3. **Ứng viên đáp ứng các quy tắc bầu cử về trạng thái và độ cập nhật dữ liệu**; một secondary quá lạc hậu, không ở trạng thái thích hợp hoặc đang initial sync không thể tùy tiện trở thành primary chỉ vì nó nhận được tín hiệu mạng.
4. **Không có rào cản bầu cử tương ứng** như cấu hình/term không hợp lệ, member đang bị hạn chế ứng cử, hoặc những thành viên đủ phiếu không thể liên lạc.

Trong hoạt động bình thường, primary phải duy trì khả năng liên lạc với **đa số voting members**. Nếu primary bị tách khỏi quorum trong thời gian phát hiện lỗi, nó không thể tiếp tục giữ vai trò primary một cách hợp lệ và sẽ step down.

```text
Replica set 3 voting data members

      A (primary)
      /           \
 B (secondary)  C (secondary)

Quorum = 2:
  A + B: đủ
  A + C: đủ
  B + C: đủ để bầu primary mới nếu có ứng viên hợp lệ
  A đơn lẻ: không đủ
```

**Một node có kết nối TCP đến client không đồng nghĩa replica set đang có writable primary.** Trong ứng dụng, trạng thái writeable được xác định bởi giao thức replica set và kết quả chọn server của driver, không phải chỉ bằng việc ping được một cổng mạng.

### Quyền ứng cử khác với quyền bỏ phiếu

Giả sử cấu hình:

```text
A: votes=1, priority=2
B: votes=1, priority=0
C: votes=1, priority=0
```

Quorum vẫn là **2**. Nhưng **chỉ A** đủ điều kiện trở thành primary vì B và C có `priority: 0`. Nếu A ngừng hoạt động, B và C còn hai phiếu, nghĩa là **còn quorum về số học**, nhưng **không có ứng viên hợp lệ**. Kết quả là replica set không thể tự bầu primary mới.

Đây là ví dụ trực quan cho câu nói: **“Còn quorum” không luôn đồng nghĩa “sẽ có primary”.**

## 4. Thực hành tính quorum của các topology thường gặp

### 4.1. Một voting data member

```text
A (voting, electable)

V = 1, quorum = 1
```

A có thể tự bầu mình làm primary trong cấu hình phù hợp. Tuy nhiên, đây **không phải high availability**: khi A lỗi, không có bản thay thế nào có thể làm primary. Một secondary `votes: 0` thêm vào cũng không giải quyết failover bầu cử nếu A là voting member duy nhất.

### 4.2. Hai data-bearing voting members

```text
A (primary) <----> B (secondary)

V = 2, quorum = 2
```

Nếu cả A và B còn liên lạc, có thể duy trì primary. Nếu A lỗi, B chỉ có **một trong hai phiếu**, không thể tự bầu primary. Nếu B lỗi, A không còn nhìn thấy đa số phiếu nên cũng không thể tiếp tục giữ primary ổn định.

Đây là lý do **replica set hai voting members không chịu được việc mất một voting member về mặt quorum**. Cấu hình này dễ tạo cảm giác “đã có sao chép nên sẵn sàng cao”, nhưng sao chép dữ liệu và khả năng bầu cử là hai thuộc tính khác nhau.

### 4.3. Ba data-bearing voting members: P–S–S

```text
               A (primary)
               /         \
    B (secondary) --- C (secondary)

V = 3, quorum = 2
```

Một node lỗi hoặc bị tách khỏi hai node còn lại:

- Nếu **C lỗi**, A và B còn hai phiếu; primary A có thể tiếp tục hoạt động khi vẫn đáp ứng các điều kiện khác.
- Nếu **A lỗi**, B và C còn hai phiếu; một trong hai có thể được bầu làm primary **nếu có ứng viên đủ điều kiện và dữ liệu/trạng thái phù hợp**.
- Nếu **chỉ A còn**, A không có đa số, nên không thể giữ primary hợp lệ.

P–S–S là một topology nền tảng để hiểu high availability: ba data-bearing voting members vừa cho khả năng bầu cử đa số khi một node mất, vừa có thêm bản sao dữ liệu.

### 4.4. Bốn voting members

```text
A, B, C, D
V = 4, quorum = 3
```

Nếu hai member cùng lỗi hoặc mạng chia 2–2, **không phe nào đạt quorum 3**. Việc thêm member thứ tư từ topology ba voter làm tăng chi phí số node, nhưng **không tăng số voting-member failures có thể chịu được** từ 1 lên 2. Vì vậy, số voting members lẻ thường được ưu tiên khi thiết kế quorum, nếu các yêu cầu khác cũng phù hợp.

### 4.5. Năm voting members

```text
A, B, C, D, E
V = 5, quorum = 3
```

Replica set có thể vẫn đạt quorum khi **hai voting members không còn kết nối** với phe còn lại, với điều kiện ba member còn lại liên lạc được và có ứng viên phù hợp. Đây là một ví dụ topology chịu được nhiều lỗi voting members hơn cấu hình ba node, nhưng không có nghĩa mọi cách bố trí năm node đều chịu được hai lỗi **ở bất kỳ failure domain nào**.

Nếu ba voting members được đặt cùng một vùng hạ tầng và vùng đó hỏng, chỉ còn hai phiếu ở vùng khác thì không còn quorum. Số member và cách đặt chúng qua các failure domain phải được xem cùng nhau.

## 5. Chia cắt mạng: phe đa số và phe thiểu số

Giả sử replica set năm voting members chia thành hai phe:

```text
Khu vực 1: A --- B --- C      (3 phiếu)

           MẤT KẾT NỐI

Khu vực 2: D --- E            (2 phiếu)
```

Với quorum = 3:

- Phe A–B–C **có quorum** và có thể duy trì/bầu primary nếu có ứng viên hợp lệ.
- Phe D–E **không có quorum**, nên không được tự bầu primary dù cả hai member vẫn chạy bình thường.
- Nếu primary cũ nằm ở phe D–E, nó phải step down khi nhận biết mình mất đa số; phe ba node có thể tiến hành bầu cử sau khi đáp ứng các điều kiện.

Điểm quan trọng của **quorum** không phải là “cứ hỏng ít hơn nửa node thì mọi thứ chạy”, mà là **phải có một nhóm đủ đa số còn trao đổi thông tin và thực hiện bầu cử được**.

### Network partition không giống node shutdown

Node `mongod` vẫn hoạt động nhưng:

- Không nhận heartbeat từ một số member khác.
- Không trao đổi thông tin bầu cử đúng hạn.
- Có thể không liên lạc được với các data-bearing member cần thiết cho write concern.

Nhìn vào dashboard chỉ thấy tiến trình sống sẽ không đủ để kết luận replica set khỏe. Cần kiểm tra **kết nối giữa các member**, không chỉ trạng thái tiến trình hoặc cổng `27017`.

### Sự chuyển đổi vai trò không xảy ra tại một thời điểm toàn cục

Quá trình phát hiện lỗi, timeout heartbeat, bầu cử và cập nhật topology có độ trễ. Một số yêu cầu ghi có thể tạm thời lỗi với thông báo liên quan đến primary/replication; driver có thể phải khám phá lại primary và retry theo cấu hình.

Không nên khẳng định mất một node thì primary mới sẽ xuất hiện **ngay lập tức** hoặc luôn đúng một số giây cố định. Thời gian còn tùy topology, tình trạng network, replication lag, `electionTimeoutMillis` và cơ chế lựa chọn ứng viên.

## 6. Majority không có nghĩa toàn bộ member phải online

Hai điều kiện sau khác nhau:

```text
Tất cả member online:
    5/5 online

Đủ quorum để bầu primary:
    3/5 voting members trao đổi được phiếu
```

Replica set không cần mọi secondary online mới có primary. Một replica set ba voting members có thể hoạt động với hai thành viên; một replica set năm voting members có thể hoạt động với ba thành viên, trong giới hạn điều kiện bầu cử.

Nhưng quorum cũng không phải một cách để “bỏ qua mọi rủi ro”: nếu chỉ còn tối thiểu số phiếu cần thiết, một lỗi tiếp theo có thể khiến hệ thống mất primary. Khi ở trạng thái suy giảm, cần ưu tiên khôi phục kết nối/sao chép và giảm các thao tác bảo trì có nguy cơ làm mất phiếu.

### Bỏ phiếu không tương đương với đồng bộ dữ liệu

Node `votes: 1` có quyền tham gia quyết định ai làm primary. Điều đó không tự nói rằng:

- Node ấy đang có dữ liệu mới nhất.
- Node ấy có thể nhận ghi của client.
- Node ấy lưu một bản sao dữ liệu.
- Một thao tác ghi đã được xác nhận bền vững trên đa số data-bearing members.

Những thuộc tính này cần được phân tích riêng, đặc biệt khi trong cấu hình có arbiter hoặc secondary bị lag.

## 7. Vai trò của `priority` trong bầu cử

MongoDB cho phép đặt độ ưu tiên cao hơn cho member thường được mong muốn làm primary:

```javascript
{
  _id: 0,
  host: "mongo-a.example.net:27017",
  votes: 1,
  priority: 2
}
```

So với:

```javascript
{
  _id: 1,
  host: "mongo-b.example.net:27017",
  votes: 1,
  priority: 1
}
```

Trong bối cảnh phù hợp, replica set có thể ưu tiên member A làm primary hơn B. Tuy nhiên:

- A vẫn cần **đa số phiếu**; priority 2 không tương đương hai votes.
- A phải **đủ điều kiện bầu cử**, không thể đang initial sync rồi tự trở thành primary.
- B vẫn có thể được bầu khi A không khả dụng và B thỏa điều kiện.
- Sự ưu tiên có thể tạo ra các chuyển đổi primary ngoài ý muốn nếu cấu hình không phù hợp với chất lượng network và vị trí các node.

### `priority: 0` vẫn có thể bỏ phiếu

Ví dụ:

```text
A: votes=1, priority=2    ứng cử được
B: votes=1, priority=1    ứng cử được
C: votes=1, priority=0    chỉ bỏ phiếu, không ứng cử
```

Quorum = 2. Nếu A lỗi, B và C có thể bỏ phiếu để B trở thành primary, dù C không bao giờ làm primary. Điều này khác với cấu hình `B: votes=0`; khi đó B không giúp cung cấp phiếu bầu.

Khi thiết kế một member chỉ phục vụ đọc hoặc sao lưu, nên cân nhắc nó có nên bỏ phiếu hay không, thay vì chỉ đặt `priority: 0` và nghĩ rằng nó đã bị loại khỏi tính quorum.

## 8. `votes: 0`: một bản sao dữ liệu không giúp đạt quorum

Giả sử có ba data-bearing members:

```text
A: votes=1, priority=1
B: votes=1, priority=1
C: votes=0, priority=0

Tổng voting members V = 2
Quorum = 2
```

Mặc dù có **ba bản sao dữ liệu**, replica set vẫn chỉ có **hai phiếu**. Nếu A mất, B và C còn hai data-bearing nodes nhưng chỉ **một phiếu** (B), nên không thể bầu primary.

Điều này minh họa hai trục độc lập:

| Trục | Câu hỏi |
| --- | --- |
| **Sao chép dữ liệu** | Có bao nhiêu data-bearing members đang lưu và đồng bộ dữ liệu? |
| **Quyền bầu cử** | Có bao nhiêu voting members, và còn bao nhiêu phiếu có thể liên lạc? |

Một non-voting secondary có thể rất có ích cho nhu cầu đọc, phân tích hoặc backup theo thiết kế, nhưng **không khắc phục thiếu quorum** của một cấu hình chỉ có hai voting members.

### Số voting members tối đa

MongoDB có giới hạn về số voting members của một replica set: **tối đa bảy voting members**; replica set có thể có thêm các non-voting members trong phạm vi số member tổng thể mà phiên bản hỗ trợ. Hãy phân biệt tổng số thành viên trong `rs.conf().members` với số thành viên có `votes: 1`.

Không nên biến tất cả node đọc phụ thành voting members chỉ để “tăng an toàn”. Nhiều voter hơn làm thay đổi quorum, độ phức tạp bầu cử và yêu cầu phân bố failure domains; cần chọn thành viên bỏ phiếu theo thiết kế khả dụng thật sự.

## 9. Arbiter: thêm một phiếu nhưng không thêm bản sao

Arbiter thường được nhắc đến trong topology **P–S–A**:

```text
        P (primary, data)
        /                \
S (secondary, data) --- A (arbiter)

P: votes=1
S: votes=1
A: votes=1

V = 3, quorum = 2
```

Arbiter tham gia bầu cử, không lưu dữ liệu người dùng và không thể trở thành primary. Khi không muốn hoặc chưa thể bổ sung data-bearing third member, arbiter giúp một nhóm ba phiếu có khả năng đạt quorum với hai member còn kết nối.

### Các tình huống trong P–S–A

| Tình huống | Phiếu còn liên lạc | Có quorum bầu cử? | Điều cần nhớ |
| --- | --- | --- | --- |
| P, S, A đều khỏe | 3 | Có | Có hai bản sao dữ liệu và một arbiter |
| A lỗi; P và S còn | 2 | Có | P và S vẫn đủ phiếu |
| S lỗi; P và A còn | 2 | Có | Có thể giữ primary, nhưng chỉ P chứa bản dữ liệu đang hoạt động |
| P lỗi; S và A còn | 2 | Có | S có thể được bầu nếu đủ điều kiện |
| Chỉ P còn | 1 | Không | Không giữ primary hợp lệ |
| Chỉ S còn | 1 | Không | Không bầu được primary |

**Tình huống P + A rất dễ gây nhầm lẫn:** hai phiếu đủ bầu cử, nên có thể có primary, **nhưng chưa đủ bản sao dữ liệu để xác nhận ghi với `w: "majority"`** trong topology P–S–A thông thường. Arbiter không có dữ liệu để nhận và ghi các thay đổi.

Trong tình huống chỉ một data-bearing node còn hoạt động, ghi `w: 1` có thể được primary xác nhận nhưng dễ gặp rủi ro mất/rollback dữ liệu nếu node đó lỗi trước khi các bản sao khác đồng bộ. Với `w: "majority"`, các thao tác ghi có thể phải chờ hoặc gặp lỗi timeout khi không đủ data-bearing members đáp ứng yêu cầu.

### P–S–A không tương đương P–S–S

| Thuộc tính | P–S–S | P–S–A |
| --- | --- | --- |
| Tổng voting members | 3 | 3 |
| Election quorum | 2 | 2 |
| Data-bearing members | 3 | 2 |
| Có một member không lưu dữ liệu | Không | Có, arbiter |
| Khi mất một data-bearing secondary | Vẫn còn P và S khác để nhân bản/ack majority | Có thể chỉ còn P và A, không đủ data-bearing để ack majority |
| Chịu được mất một voting member về mặt quorum | Có | Có |
| Mức dự phòng dữ liệu | Cao hơn trong cấu hình này | Thấp hơn |

Arbiter không phải một giải pháp mặc định tương đương secondary thật. Với nhu cầu độ bền dữ liệu cao, nên cân nhắc **ba data-bearing voting members** khi hạ tầng cho phép.

### Không suy luận write concern mặc định chỉ từ số node

MongoDB có các quy tắc **implicit default write concern** phụ thuộc phiên bản và cấu hình, đặc biệt khi replica set có arbiter. Vì vậy không được mặc định rằng mọi hệ P–S–A luôn dùng `w: "majority"` nếu client không ghi rõ.

Ứng dụng quan trọng cần **khai báo write concern có chủ đích**, kiểm tra cấu hình thực tế và hiểu tác động khi một secondary hoặc arbiter không khả dụng.

## 10. Election majority khác với write concern `majority`

Hai từ `majority` xuất hiện trong hai tình huống khác nhau:

**A. Election majority (quorum):**

> Có đủ phiếu của voting members để duy trì hoặc bầu một primary không?

**B. Write concern `w: "majority"`:**

> Một thao tác ghi có được xác nhận theo yêu cầu sao chép đến số data-bearing voting members cần thiết không?

Điểm khác nhau là **arbiter có phiếu bầu nhưng không sao chép dữ liệu**. Với topology chỉ có data-bearing voting members, hai loại đa số này có thể dễ bị coi là cùng một điều. Với P–S–A, sự khác biệt rất quan trọng.

```text
P - S - A

P online, S mất kết nối, A online

Phiếu bầu:
  P + A = 2/3      -> còn quorum

Bản sao có thể xác nhận ghi:
  P có dữ liệu
  A không giữ dữ liệu
  S đang mất kết nối
                    -> w:"majority" không thể hoàn tất bình thường
```

### Ví dụ yêu cầu ghi với majority

Trong `mongosh` trên một replica set phù hợp:

```javascript
db.orders.insertOne(
  {
    orderCode: "ORD-1001",
    status: "paid",
    total: 150
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
)
```

`wtimeout: 5000` yêu cầu không chờ vô hạn nếu điều kiện xác nhận ghi chưa hoàn tất trong khoảng thời gian đó. **Write concern timeout không tự chứng minh thao tác chưa được ghi trên primary.** Nó có thể đã được áp dụng ở một số node nhưng chưa đạt mức xác nhận yêu cầu; ứng dụng cần xử lý phản hồi, retry và tính idempotency của nghiệp vụ phù hợp.

Ví dụ chỉ phù hợp với một collection `orders` và môi trường lab có primary. Trong môi trường production, không dùng mã chèn minh họa một cách vô ý và không thay đổi write concern của ứng dụng chỉ để thử failover.

### So sánh `w: 1` và `w: "majority"`

| Thuộc tính | `w: 1` | `w: "majority"` |
| --- | --- | --- |
| Mức xác nhận chính | Primary xác nhận theo write concern | Số data-bearing voting members cần thiết xác nhận |
| Phụ thuộc secondary để ack | Không yêu cầu ack từ secondary | Thường có, tùy topology và điều kiện majority |
| Khi primary ghi xong nhưng secondary bị mất | Có thể ack | Có thể chờ hoặc timeout |
| Bảo vệ trước rollback trong failover | Yếu hơn | Mạnh hơn đối với những ghi đã đạt majority |
| Chi phí/độ trễ | Có thể thấp hơn | Có thể cao hơn vì đợi replication |

`w: "majority"` **không bảo đảm các thao tác ghi trên toàn bộ replica set xảy ra tức thì**, và không thay thế transaction khi cần thay đổi nhiều document như một đơn vị. Cần thêm chính sách journaling, timeout và xử lý lỗi ở phía client cho yêu cầu độ bền thực tế.

### Read concern không phải điều kiện bầu cử

`readConcern: "majority"` liên quan đến tính chất dữ liệu có thể được đọc và mức commit majority, **không cấp thêm phiếu bầu** và không khiến secondary trở thành primary. Cũng vậy, `readPreference: "secondary"` chỉ là lựa chọn nơi đọc khi ứng dụng cho phép, không giải quyết mất quorum cho các thao tác ghi.

## 11. Điều gì xảy ra khi primary mất liên lạc với đa số?

Giả sử replica set ba voting members `A, B, C`, primary ban đầu là A. Mạng bị chia:

```text
A (primary cũ)       |       B --- C
 1 phiếu             |       2 phiếu
                     |
               mất kết nối
```

Diễn biến khái quát:

1. A có thể còn tự nhận mình là primary trong một khoảng ngắn trước khi nhận biết mất quorum.
2. A không thể duy trì quyền primary hợp lệ khi không liên lạc với đa số; nó sẽ step down theo cơ chế replica set.
3. B và C có quorum 2/3. Một member đủ điều kiện có thể thắng cuộc bầu cử và trở thành primary mới.
4. Khi mạng nối lại, A phải hội nhập với trạng thái/term mới. Các thao tác ghi cũ **chưa được majority commit** có thể cần rollback nếu xung đột với lịch sử đã được chọn.

Do đó, yêu cầu nghiệp vụ không nên chỉ dựa vào phản hồi `w: 1` rồi coi dữ liệu chắc chắn tồn tại sau failover. Với ghi quan trọng, hãy chọn write concern thích hợp và thiết kế retry/idempotency.

### Không phải mọi lần mất primary đều có cùng nguyên nhân

Không có primary có thể do:

- **Thiếu quorum** vì mất hoặc tách mạng các voting members.
- **Có quorum nhưng không có ứng viên eligible**: tất cả node còn lại có `priority: 0`, đang initial sync hoặc không đáp ứng yêu cầu bầu cử.
- **Ứng viên không đủ điều kiện độ mới/trạng thái** theo cơ chế bầu cử.
- **Đang trong khoảng bầu cử**, chưa chọn xong primary mới.
- **Cấu hình không mong muốn**: số voter, priority, arbiter hoặc reconfiguration làm thay đổi điều kiện cần.

Vì vậy, cần phân tích **trạng thái từng member** và **cấu hình voting members**, không chỉ đếm bao nhiêu `mongod` vẫn chạy.

## 12. Thời gian bầu cử, heartbeat và term

Các thành viên replica set trao đổi **heartbeat** để theo dõi trạng thái và khả năng liên lạc. Khi primary mất hoặc không còn đáp ứng, các node đủ điều kiện có thể bắt đầu quá trình bầu cử theo timeout và những quy tắc giao thức hiện hành.

Trong cấu hình replica set có thuộc tính `settings.electionTimeoutMillis`, giá trị mặc định thường là **10.000 ms** nếu không thay đổi. Tuy nhiên, **không nên biến con số đó thành SLA failover 10 giây**: việc phát hiện lỗi, thử bầu cử, đánh giá dữ liệu và kết nối của driver đều có thể làm thời gian thực tế khác đi.

### Term giúp phân biệt nhiệm kỳ bầu cử

Replica set dùng **term** để biểu diễn các nhiệm kỳ bầu cử. Một term mới giúp member nhận biết trạng thái lãnh đạo mới và ngăn các phiếu cũ được dùng như thể còn hiệu lực. Khi chẩn đoán, thông tin `term`, `electionDate` hoặc các lý do chuyển state có thể xuất hiện tùy API và phiên bản.

Không cần học thuộc từng biến nội bộ để trả lời “vì sao không có primary”: trước hết kiểm tra quorum, candidate eligibility và tình trạng liên lạc. Sau đó mới đi sâu vào heartbeat, term và log bầu cử khi vấn đề không rõ.

### Replication lag cũng cần quan tâm

Một secondary vừa khởi động hoặc đang lag không nhất thiết được bầu ngay khi primary lỗi. Tính an toàn của bầu cử yêu cầu candidate phù hợp với điều kiện dữ liệu và trạng thái do MongoDB đặt ra. Vì vậy, bố trí đủ số voting members trên giấy chưa đủ; cần theo dõi **sức khỏe sao chép** để biết khi failover xảy ra sẽ có ứng viên đủ điều kiện.

## 13. Cấu hình replica set minh họa

Các ví dụ trong mục này là **cấu hình học tập**, không phải lệnh được khuyến nghị chạy thẳng trên replica set đang hoạt động. Các hostname phải có thật, phân giải DNS được, các tiến trình `mongod` phải được khởi chạy với cùng tên replica set, kết nối giữa member phải thông suốt và thiết lập bảo mật phù hợp.

### 13.1. Ba data-bearing voting members

```javascript
// Chỉ dành cho môi trường lab CHƯA được initiate
rs.initiate({
  _id: "rsLearning",
  members: [
    {
      _id: 0,
      host: "mongo-a.example.net:27017",
      votes: 1,
      priority: 2
    },
    {
      _id: 1,
      host: "mongo-b.example.net:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 2,
      host: "mongo-c.example.net:27017",
      votes: 1,
      priority: 1
    }
  ]
})
```

Ý nghĩa:

- **Ba voting members** → quorum = 2.
- **Cả ba chứa dữ liệu** → ba data-bearing members.
- **Cả ba có priority dương** → có thể ứng cử khi đáp ứng điều kiện.
- A được ưu tiên hơn theo `priority: 2`, nhưng **không có hai phiếu**.

Cấu hình này là một ví dụ về việc có ít nhất hai secondary **đủ điều kiện ứng cử** khi primary mất. Trong sản xuất, việc phân bố qua các vùng mạng/availability zones và chính sách độ trễ là yếu tố quyết định khả năng chịu lỗi thực.

### 13.2. Hai data-bearing và một arbiter

```javascript
// Chỉ minh họa cấu trúc, không initiate thêm vào cùng cluster
{
  _id: "rsWithArbiter",
  members: [
    {
      _id: 0,
      host: "mongo-a.example.net:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 1,
      host: "mongo-b.example.net:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 2,
      host: "mongo-arb.example.net:27017",
      arbiterOnly: true,
      votes: 1,
      priority: 0
    }
  ]
}
```

Đây là cấu trúc P–S–A gồm ba phiếu nhưng chỉ **hai bản sao dữ liệu**. Nếu một data-bearing member mất, phần còn lại có thể đủ election quorum với arbiter nhưng không bảo đảm khả năng xác nhận ghi `majority`.

### 13.3. Một secondary có phiếu nhưng không được primary

```javascript
{
  _id: 2,
  host: "mongo-report.example.net:27017",
  votes: 1,
  priority: 0
}
```

Thành viên này **có thể góp phiếu để bầu member khác**. Nếu cần loại hẳn khỏi voting quorum:

```javascript
{
  _id: 2,
  host: "mongo-report.example.net:27017",
  votes: 0,
  priority: 0
}
```

Hai cấu hình dẫn đến **số voting members khác nhau**, nên không thể chỉ đổi `votes` trên một replica set hoạt động mà không lập kế hoạch quorum và tác động reconfiguration.

## 14. Kiểm tra số phiếu và primary trong `mongosh`

Các lệnh đọc cấu hình/trạng thái sau hữu ích khi điều tra, miễn là tài khoản có quyền phù hợp.

### 14.1. Xem cấu hình và những member có phiếu

```javascript
rs.conf()
```

Chỉ lấy những trường quan trọng:

```javascript
const cfg = rs.conf();

const members = cfg.members.map(member => ({
  id: member._id,
  host: member.host,
  votes: member.votes,
  priority: member.priority,
  arbiterOnly: member.arbiterOnly === true
}));

printjson(members);
```

Để tính quorum từ cấu hình thông thường:

```javascript
const config = rs.conf();

const votingMembers = config.members.reduce(
  (count, member) => count + (member.votes === 1 ? 1 : 0),
  0
);

const electionQuorum = Math.floor(votingMembers / 2) + 1;

printjson({
  configuredMembers: config.members.length,
  votingMembers,
  electionQuorum
});
```

Đoạn này giả định các member đã có giá trị `votes` tường minh từ cấu hình và đang xét một cấu hình ổn định thông thường. Nếu server đang trong **giai đoạn reconfiguration hoặc newly added member**, hãy đối chiếu thêm các trường majority/count được server báo ở trạng thái hiện hành; không xem phép cộng tự viết là nguồn chân lý duy nhất trong mọi tình huống chuyển tiếp.

### 14.2. Xem trạng thái replica set

```javascript
rs.status()
```

Trong nhiều phiên bản, `rs.status()` cung cấp những thông tin như:

| Trường | Cách hiểu |
| --- | --- |
| `set` | Tên replica set |
| `myState` | Trạng thái của member nơi chạy lệnh |
| `members[].name` | Host/port của member |
| `members[].stateStr` | Vai trò/trạng thái như `PRIMARY`, `SECONDARY`, `ARBITER`, `RECOVERING` |
| `members[].health` | Dấu hiệu sức khỏe/kết nối từ góc nhìn node đang hỏi |
| `members[].optime` | Thông tin tiến độ replication theo dạng được server báo |
| `term` | Nhiệm kỳ bầu cử, khi được báo |
| `majorityVoteCount` | Số phiếu majority theo server ở phiên bản có trường này |
| `writeMajorityCount` | Ngưỡng write majority được server báo, khi có |
| `votingMembersCount` | Số voting members theo server, khi có |

Hình dạng JSON và tên trường có thể khác theo phiên bản; không nên dựa vào sự tồn tại của mọi trường trong mọi hệ thống.

Để xem một bảng gọn:

```javascript
const state = rs.status();

printjson(state.members.map(member => ({
  name: member.name,
  state: member.stateStr,
  health: member.health,
  optimeDate: member.optimeDate
})));
```

`health` thể hiện góc nhìn của node đang được hỏi, không phải một phép xác minh toàn mạng từ mọi member. Khi có partition, các node ở hai phía có thể có **những góc nhìn khác nhau về kết nối**.

### 14.3. Hỏi node có phải writable primary không

```javascript
db.adminCommand({ hello: 1 })
```

Phản hồi có thể có các trường như `setName`, `isWritablePrimary`, `secondary`, `primary` và `hosts`. Trường `isWritablePrimary: true` cho biết node đang tự báo là writable primary theo trạng thái của nó.

Khi driver kết nối replica set, việc chọn primary thông thường dựa trên cơ chế khám phá topology/monitoring của driver, không nên cài đặt bằng cách tự ping một node ngẫu nhiên rồi hard-code rằng nó sẽ mãi là primary.

### 14.4. Nhận biết không có primary

Nếu tất cả member mà client kết nối được đều không có `isWritablePrimary: true`, hoặc driver báo không tìm thấy writable primary trong khoảng lựa chọn server, các khả năng cần kiểm tra gồm:

1. Mất đa số voting members hoặc chia mạng.
2. Không có ứng viên đủ điều kiện làm primary.
3. Hệ thống đang trong kỳ bầu cử.
4. Kết nối giữa client và primary bị chặn dù replica set nội bộ vẫn có primary.
5. Thiết lập URI/hostnames/replica set name không đúng làm driver khám phá topology sai.

Đừng chỉ kết luận “database down” vì một secondary vẫn trả lời truy vấn `hello` nhưng không nhận ghi. Vấn đề có thể nằm ở quyền primary/quorum chứ không phải toàn bộ tiến trình MongoDB dừng.

## 15. Thiết kế voting topology theo vùng lỗi

Giả sử ba voting members được đặt ở ba availability zones:

```text
Zone A: mongo-a (1 vote)
Zone B: mongo-b (1 vote)
Zone C: mongo-c (1 vote)

Quorum = 2
```

Mất một zone vẫn có thể để lại hai phiếu liên lạc được, nếu network giữa hai zone còn lại hoạt động và có ứng viên phù hợp.

Ngược lại:

```text
Zone A: mongo-a, mongo-b, mongo-c   (3 votes)
Zone B: mongo-d                      (1 vote)
Zone C: mongo-e                      (1 vote)

Quorum = 3
```

Mặc dù có năm voting members, nếu cả Zone A mất, chỉ còn hai phiếu ở B và C, không đạt quorum. Vì vậy, “năm node chịu được hai node lỗi” **không đồng nghĩa** “bất kỳ một zone nào lỗi cũng chịu được”.

### Lựa chọn topology theo failure domain

Một số nguyên tắc:

- Bố trí voting members ở các failure domains độc lập khi có thể.
- Không đặt đa số votes trên một hạ tầng có cùng điểm lỗi nếu yêu cầu chịu được lỗi hạ tầng đó.
- Đánh giá **độ trễ và độ tin cậy đường mạng** giữa các member: một node ở xa có thể giúp phân tán rủi ro nhưng cũng tăng nguy cơ timeout và replication lag.
- Kiểm tra liệu **phe đa số sau lỗi** còn **một ứng viên electable** và đủ data-bearing members cho write concern mục tiêu không.
- Đừng đánh đồng arbiter với một data-bearing vote khi tính mức dự phòng dữ liệu.

Thực tế, thiết kế tốt cần thỏa **cả quorum, bầu cử, sao chép dữ liệu và mục tiêu nghiệp vụ**, không chỉ phép tính `floor(V/2)+1`.

## 16. Reconfiguration: thay đổi phiếu bầu là thao tác nhạy cảm

Khi cần thêm, bớt hoặc đổi thuộc tính voting members, MongoDB có cơ chế reconfiguration của replica set. Những thay đổi này tác động trực tiếp đến:

- Số voting members và ngưỡng majority.
- Những node đủ điều kiện được bầu primary.
- Khả năng failover khi một vùng lỗi mất.
- Yêu cầu xác nhận write concern và trạng thái dữ liệu.
- Khả năng xuất hiện bầu cử hoặc chuyển primary trong thời gian bảo trì.

Không nên thay đổi `votes`, `priority` hoặc dùng chế độ **force reconfiguration** chỉ để làm một node đang mất quorum trở thành primary mà chưa đánh giá tác động an toàn dữ liệu. Những thao tác cưỡng bức hoặc cấu hình sai có thể tạo nguy cơ rollback, mất các ghi chưa majority commit, hoặc thay đổi topology ngoài dự định.

Một kế hoạch thay đổi thường cần:

1. Ghi lại cấu hình và trạng thái hiện tại.
2. Xác định số voters và quorum **trước/sau**.
3. Kiểm tra các node cần thiết đang đồng bộ và đủ điều kiện.
4. Thiết kế thứ tự thay đổi phù hợp với giới hạn reconfiguration của phiên bản MongoDB.
5. Chuẩn bị phương án khôi phục và thời gian bảo trì nếu cần.
6. Theo dõi bầu cử, replication lag và write concern sau thay đổi.

Trong bài học này, các ví dụ cấu hình chỉ dùng để hiểu quorum. **Không thực hành force reconfig, xóa member hay ngắt node trên replica set đang phục vụ dữ liệu thật.**

## 17. Checklist đọc trạng thái khi replica set mất primary

Khi nhận thông báo kiểu “no primary available”, có thể lần lượt trả lời:

| Câu hỏi | Cách kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Có bao nhiêu member được cấu hình? | `rs.conf().members` | Tổng số node không đồng nhất với số voters |
| Ai có phiếu? | `votes` trong `rs.conf()` | Tính quorum |
| Quorum là bao nhiêu? | `floor(V/2)+1` và đối chiếu server status | Ngưỡng phiếu phải đạt |
| Các voting members có liên lạc được với nhau không? | `rs.status()`, heartbeat/network logs | Node online chưa chắc cùng một quorum |
| Có ứng viên electable? | `votes`, `priority`, trạng thái replication | Có quorum vẫn có thể thiếu ứng viên |
| Có arbiter không? | `arbiterOnly` | Phiếu không đồng nghĩa với bản sao dữ liệu |
| Primary cũ đã step down chưa? | `rs.status()`, `hello`, logs, term | Phát hiện chuyển vai trò/đang bầu cử |
| Secondary có bị lag hoặc initial sync? | `rs.status()`, replication metrics | Ảnh hưởng ứng viên và khả năng ack |
| Ghi `w:"majority"` có hoàn tất được? | Write concern, `writeMajorityCount` khi có, tình trạng data-bearing | Khác với election quorum |
| Client có tìm đúng topology? | URI, replica set name, DNS, connectivity | Không phải lỗi nào cũng do bầu cử nội bộ |

Ưu tiên **lệnh đọc và quan sát** trước. Việc thay cấu hình bầu cử hoặc ép node làm primary nên thuộc một quy trình vận hành được phê duyệt, không phải phản xạ đầu tiên khi xuất hiện lỗi.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao không đúng? | Cách hiểu đúng |
| --- | --- | --- |
| “Replica set hai node chịu được một node lỗi vì đã có bản sao” | Hai voter cần quorum 2/2 | Tách số bản sao dữ liệu khỏi số phiếu |
| “Quorum tính theo node đang online” | Member chết không tự bị xóa khỏi cấu hình | Đa số tính trên số voting members trong cấu hình có hiệu lực |
| “Chỉ cần còn nhiều hơn nửa tổng node” | Non-voter không có phiếu, các node có thể không liên lạc được | Đếm voting members và các phiếu liên lạc được |
| “Có quorum là chắc chắn có primary” | Có thể không còn member eligible hoặc đang bầu cử | Cần cả quorum lẫn ứng viên phù hợp |
| “`priority: 0` nghĩa là không bỏ phiếu” | Có thể vẫn `votes: 1` | `votes` và `priority` là hai cấu hình khác nhau |
| “`priority: 2` có hai phiếu” | Priority không phải votes | Member voting thông thường có một phiếu |
| “`votes: 0` nhưng `priority: 1` vẫn có thể primary” | Non-voter không đủ điều kiện ứng cử | `votes: 0` yêu cầu `priority: 0` |
| “Arbiter là bản sao dữ liệu thứ ba” | Arbiter không lưu dữ liệu | Nó chỉ đóng góp bầu cử |
| “P + arbiter đủ hai phiếu nên ghi majority chắc thành công” | Arbiter không sao chép ghi | Election majority khác majority write acknowledgement |
| “Cứ thêm một voting member là tăng chịu lỗi” | Ba voter quorum 2, bốn voter quorum 3; cả hai chịu mất 1 voter | Xem bảng majority theo topology |
| “Mất primary thì thứ cấp sẽ thành primary ngay” | Cần election, heartbeat, đủ điều kiện | Failover có độ trễ và có thể chưa thành công |
| “Có thể sửa votes tùy ý để hệ thống có primary trở lại” | Reconfig tác động an toàn và nhất quán dữ liệu | Dùng quy trình thay đổi topology |
| “`rs.status()` của một node phản ánh mọi phía mạng như nhau” | Các node trong partition có góc nhìn khác nhau | Đối chiếu node, logs và topology thực |
| “`w: 1` ghi thành công thì không thể rollback” | Ghi chưa majority commit có thể mất khi failover | Chọn write concern theo độ bền mong muốn |

## 19. Bài tập thực hành và đáp án

### Bài 1. Tính quorum cơ bản

Tính số phiếu tối thiểu khi replica set có 2, 3, 4, 5 và 7 voting members.

**Đáp án:**

```text
V = 2 -> quorum = 2
V = 3 -> quorum = 2
V = 4 -> quorum = 3
V = 5 -> quorum = 3
V = 7 -> quorum = 4
```

Quy tắc chung: `floor(V/2)+1`.

### Bài 2. Còn ba node nhưng không còn quorum?

Topology:

```text
A: votes=1, priority=1
B: votes=1, priority=1
C: votes=0, priority=0
```

A mất kết nối hoàn toàn. B và C vẫn hoạt động. Hỏi B có thể được bầu primary chỉ nhờ C không?

**Đáp án:** Không. Chỉ A và B có phiếu nên `V = 2`, quorum = 2. Phe B–C có **một phiếu** từ B, C không bỏ phiếu. Dù còn hai data-bearing members và B có priority dương, quorum vẫn không đạt.

### Bài 3. Đủ quorum nhưng không có primary

Topology:

```text
A: votes=1, priority=1
B: votes=1, priority=0
C: votes=1, priority=0
```

A bị lỗi, B và C liên lạc với nhau. Có thể bầu primary mới không?

**Đáp án:** B và C có hai phiếu trên ba (đủ quorum), nhưng cả hai đều có `priority: 0` nên không được làm primary. **Không có ứng viên electable**, do đó không bầu được primary.

### Bài 4. Phân vùng mạng 3–2

Một replica set năm voting members chia thành nhóm X có ba node và nhóm Y có hai node. Mỗi nhóm nội bộ liên lạc được, hai nhóm không liên lạc với nhau. Phe nào có thể có primary?

**Đáp án:** Quorum = 3. Nhóm X đạt đa số và có thể duy trì/bầu primary nếu có ứng viên phù hợp. Nhóm Y không đủ đa số và không được bầu primary. Nếu primary cũ thuộc nhóm Y, nó phải step down khi mất quorum.

### Bài 5. Arbiter và majority write

Replica set `P–S–A`: P là primary, S là secondary, A là arbiter, cả ba có một phiếu. S mất kết nối, P và A vẫn liên lạc.

1. Có còn election quorum không?
2. Có bảo đảm được ghi `w: "majority"` không?

**Đáp án:** (1) Có, P và A có 2/3 phiếu. (2) Không; A không lưu dữ liệu, nên chỉ còn P có thể nhận ghi. Yêu cầu majority write trong P–S–A thông thường không thể được xác nhận đầy đủ chỉ nhờ P và A; có thể chờ/timeout.

### Bài 6. Một node bỏ phiếu nhưng không được ứng cử

Cho member:

```javascript
{
  host: "mongo-report.example.net:27017",
  votes: 1,
  priority: 0
}
```

Member này có đóng góp vào quorum? Có thể thành primary?

**Đáp án:** Có phiếu nên đóng góp vào quorum; không thể thành primary vì `priority: 0`.

### Bài 7. Vì sao thêm voter thứ tư không tăng chịu lỗi?

So sánh một replica set ba voters và một replica set bốn voters, tất cả còn khỏe. Một voting member bất kỳ mất kết nối trong mỗi set. Tính quorum và số phiếu còn lại.

**Đáp án:**

| Topology | Quorum | Phiếu còn sau một lỗi | Còn quorum? |
| --- | ---: | ---: | --- |
| 3 voters | 2 | 2 | Có |
| 4 voters | 3 | 3 | Có |

Cả hai đều chỉ chịu được **một voting member lỗi** nếu không có điều kiện khác. Với bốn voters, mất hai còn hai, thiếu quorum 3.

### Bài 8. Bố trí trên ba vùng

Replica set năm voting members phân bố `3–1–1` trên ba zones. Một zone chứa ba members bị hỏng hoàn toàn. Vì sao topology vẫn không có primary dù còn hai zones?

**Đáp án:** Quorum = 3, nhưng hai zones còn lại chỉ có hai phiếu. Khả năng chịu lỗi phải tính theo **số phiếu mất cùng failure domain**, không chỉ số vùng hoặc tổng số node.

### Bài 9. Đọc cấu hình

Cho:

```javascript
members: [
  { _id: 0, votes: 1, priority: 2 },
  { _id: 1, votes: 1, priority: 1 },
  { _id: 2, votes: 1, priority: 0 },
  { _id: 3, votes: 0, priority: 0 }
]
```

Tính tổng members, voters, quorum và số member có quyền ứng cử theo cấu hình.

**Đáp án:** Tổng members = 4, voters = 3, quorum = 2. Member `_id: 0` và `_id: 1` có `votes: 1, priority > 0`, nên là hai **ứng viên có khả năng ứng cử theo cấu hình**, với điều kiện trạng thái/độ cập nhật khi bầu cử đều hợp lệ. `_id: 2` chỉ bỏ phiếu; `_id: 3` không bỏ phiếu.

### Bài 10. Phân biệt hai phản hồi

Ứng dụng có thể kết nối và đọc từ một secondary, nhưng một thao tác ghi trả lỗi không tìm thấy primary. Điều này có mâu thuẫn không?

**Đáp án:** Không. Secondary có thể online, phục vụ những yêu cầu đọc được cấu hình phù hợp, trong khi replica set thiếu quorum hoặc chưa bầu được primary. Khả năng truy cập một tiến trình không đồng nghĩa khả năng ghi qua primary. Cần kiểm tra topology, voting configuration, network, trạng thái election và server selection của driver.

## 20. Tổng kết

Trong MongoDB replica set, **quorum bầu cử** là đa số phiếu của các voting members theo cấu hình có hiệu lực:

```text
quorum = floor(numberOfVotingMembers / 2) + 1
```

Muốn có primary, replica set không chỉ cần **đủ phiếu liên lạc được**, mà còn cần **ít nhất một data-bearing voting member đủ điều kiện ứng cử** và cuộc bầu cử hợp lệ. `votes` quyết định quyền tham gia quorum; `priority` quyết định khả năng/mức ưu tiên ứng cử; `priority: 0` vẫn có thể bỏ phiếu; `votes: 0` không góp phiếu và không thể làm primary. Arbiter góp phiếu nhưng không sao chép dữ liệu.

Khi thiết kế tính sẵn sàng cao, phải xét **cả election quorum và write concern `majority`**. Một phe đủ phiếu để có primary chưa chắc còn đủ data-bearing members để xác nhận ghi an toàn theo yêu cầu. Đồng thời, sự phân bố các phiếu trên các failure domains độc lập và tình trạng replication của ứng viên có ý nghĩa không kém phép tính quorum. Hiểu đúng những khác biệt này giúp dự đoán hậu quả khi node lỗi, giải thích vì sao một replica set không có primary và lựa chọn topology phù hợp cho ứng dụng MongoDB.
