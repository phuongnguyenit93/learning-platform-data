# Điều kiện giao nhau R+W>N và giới hạn suy luận về linearizability

## 1. Tình huống mở đầu: hai quorum giao nhau nhưng vẫn có thể đọc sai

Một hệ NoSQL có ba replica A, B và C. Một thao tác ghi được xác nhận khi **hai replica** phản hồi; một thao tác đọc cũng hỏi **hai replica**:

~~~text
N = 3 replica
W = 2 replica xác nhận ghi
R = 2 replica tham gia đọc

R + W = 4 > 3
~~~

Phép tính cho biết **mọi tập đọc gồm 2 replica phải giao với mọi tập ghi gồm 2 replica** nếu cả hai được chọn từ **cùng một tập cố định A/B/C**.

Nhưng kết luận nào đúng?

- Đúng: hai tập đó có ít nhất một replica chung.
- Chưa đủ căn cứ: mọi lần đọc luôn trả về bản mới nhất theo thời gian thực.
- Chưa đủ căn cứ: hai ghi đồng thời được sắp thứ tự đúng.
- Chưa đủ căn cứ: một ghi chỉ vừa đến RAM đã bền sau mất điện.
- Chưa đủ căn cứ: transaction nhiều key luôn atomic.
- Chưa đủ căn cứ: read qua cache hoặc secondary index có cùng bảo đảm.
- Chưa đủ căn cứ: membership khi failover và khi reconfigure vẫn là một tập replica cố định.

Đó là trọng tâm của bài học này, thuộc chương **Sao chép và quorum** của Database NoSQL: phân biệt **bài toán giao nhau của các tập hợp** với **bài toán đúng đắn của giao thức đọc/ghi phân tán**.

### 1.1. Sau bài học cần nắm gì?

1. Hiểu chính xác các biến \(N\), \(R\) và \(W\).
2. Chứng minh điều kiện \(R+W>N\) bằng lý thuyết tập hợp.
3. Tính cận dưới số replica chung giữa một read quorum và một write quorum.
4. Phân biệt giao nhau đọc–ghi, ghi–ghi và đọc–đọc.
5. Hiểu vì sao quorum intersection **không tự là linearizability**.
6. Phân tích phản ví dụ với write chưa hoàn tất, đọc liên tiếp, xung đột write và clock skew.
7. Hiểu các thành phần bổ sung: version/tag, commit rule, read selection, write-back, leader/epoch và đồng thuận.
8. Xác định khi nào công thức bị áp sai do sloppy quorum, hinted handoff hoặc thay đổi membership.
9. Đọc đúng semantics của Cassandra, MongoDB, DynamoDB, Redis và các hệ dùng leader consensus.
10. Thiết kế test, phát biểu bảo đảm và lựa chọn consistency cho nghiệp vụ NoSQL.

---

## 2. Định nghĩa N, R và W trước khi làm phép tính

Trong một mô hình replication quorum đơn giản:

- **N** là số replica thuộc **tập replica có trách nhiệm lưu cùng một đối tượng/partition** đang được xét.
- **W** là số replica tối thiểu cần xác nhận trước khi thao tác ghi được coi là đạt điều kiện write quorum.
- **R** là số replica tối thiểu được hỏi/tham gia trước khi thao tác đọc được hoàn tất theo read quorum.

Ví dụ một partition có ba replica:

~~~text
Home replica set của key user:42:
  A, B, C

N = 3
Write ACK cần 2 replica  -> W = 2
Read hỏi 2 replica       -> R = 2
~~~

**N không nhất thiết là tổng số node trong cả cluster.** Một cụm có 100 node nhưng mỗi partition chỉ được nhân bản trên 3 node thì mô hình quorum của partition ấy thường xét **N=3**, không phải 100.

### 2.1. Một key khác có thể có tập replica khác

~~~text
Key user:42   -> replicas A, B, C
Key user:99   -> replicas C, D, E
Key order:17  -> replicas F, G, H
~~~

Không được lấy W của `user:42` cộng với R của `order:17` để chứng minh có một replica chung. Chúng là **hai tập vũ trụ khác nhau**.

### 2.2. W là “được ACK” chứ không mặc nhiên “đã fsync”

Trong các hệ khác nhau, ACK có thể xảy ra sau khi:

- Nhận write vào memory.
- Append vào commit log.
- Đồng bộ journal xuống storage.
- Áp dụng write trong replica.
- Được commit theo một giao thức leader/quorum.

Phép tính \(R+W>N\) chỉ dùng **số replica**; nó không định nghĩa **điều kiện nội bộ của một ACK**.

### 2.3. R là “các replica tham gia quyết định đọc”

Nếu coordinator gửi request tới hai replica nhưng chỉ lấy **kết quả đầu tiên** rồi trả về, không thể coi nó đã thực hiện một read quorum kết hợp hai phản hồi theo đúng giao thức. Phải phân biệt:

- Fan-out gửi tới bao nhiêu node.
- Chờ bao nhiêu phản hồi.
- Xử lý những phản hồi đó thế nào.
- Trường hợp node trả timeout/lỗi có được tính không.

Chỉ tính đúng số lượng request gửi đi không chứng minh cơ chế đọc hợp lệ.

### 2.4. Những giả định của mô hình tập hợp

Để dùng trực tiếp bất đẳng thức, ta tạm giả định:

1. Các replica được xác định trong **cùng một tập cố định** \(U\).
2. \(|U|=N\).
3. Tập xác nhận ghi \(Q_W\) có ít nhất W phần tử trong \(U\).
4. Tập tham gia đọc \(Q_R\) có ít nhất R phần tử trong \(U\).
5. Một replica chỉ được đếm một lần, kể cả có nhiều connection/process liên quan.
6. Tập replica không đổi âm thầm giữa write và read đang so sánh.
7. Các phản hồi có ngữ nghĩa phù hợp của giao thức, không phải số lượng message tùy ý.

Nếu bỏ những giả định này, kết luận giao nhau có thể không còn đúng như ta tưởng.

---

## 3. Chứng minh điều kiện R+W>N

Đặt:

- \(U\): tập N replica.
- \(Q_W\subseteq U\): tập replica đã xác nhận write.
- \(Q_R\subseteq U\): tập replica được dùng cho read.

Ta có công thức:

\[
|Q_R\cup Q_W|
=|Q_R|+|Q_W|-|Q_R\cap Q_W|.
\]

Vì \(Q_R\cup Q_W\subseteq U\):

\[
|Q_R\cup Q_W|\le N.
\]

Do đó:

\[
|Q_R\cap Q_W|
\ge |Q_R|+|Q_W|-N.
\]

Nếu mỗi tập đạt ít nhất số phần tử yêu cầu:

\[
|Q_R\cap Q_W|\ge R+W-N.
\]

Vậy khi:

\[
\boxed{R+W>N}
\]

ta có:

\[
\boxed{|Q_R\cap Q_W|\ge1.}
\]

**Ý nghĩa chính xác:** tập replica tham gia đọc và tập replica xác nhận ghi có **ít nhất một replica chung** trong mô hình đã nêu.

### 3.1. Ví dụ N=3, R=2, W=2

~~~text
U = {A, B, C}

Một write quorum:
  QW = {A, B}

Các read quorum có thể:
  QR1 = {A, B} -> giao {A, B}
  QR2 = {A, C} -> giao {A}
  QR3 = {B, C} -> giao {B}
~~~

Không có tập gồm 2 node nào trong A/B/C hoàn toàn tách khỏi `{A,B}`.

Cận dưới:

\[
R+W-N=2+2-3=1.
\]

### 3.2. Ví dụ N=5, R=3, W=3

~~~text
U  = {A, B, C, D, E}
QW = {A, B, C}
QR = {C, D, E}

Intersection = {C}
~~~

Vì \(3+3>5\), giao nhau ít nhất một node.

### 3.3. Khi R+W=N không đủ

Cho \(N=4\), \(W=2\), \(R=2\):

~~~text
U  = {A, B, C, D}
QW = {A, B}
QR = {C, D}
~~~

Hai tập **không giao nhau**.

Do đó điều kiện phải là **lớn hơn nghiêm ngặt**:

\[
R+W>N,
\]

không phải \(R+W\ge N\).

### 3.4. Khi R+W<N

Nếu tổng nhỏ hơn N, hai tập càng có thể hoàn toàn tách nhau.

Ví dụ \(N=5,W=2,R=2\):

~~~text
QW = {A, B}
QR = {C, D}
~~~

Read quorum không chứa replica nào đã ACK write.

### 3.5. Điều kiện đủ cho giao nhau, chưa phải điều kiện đầy đủ cho consistency

Kết quả trên chỉ thuộc **lý thuyết tập hợp**. Nó không nói replica giao nhau:

- Đã lưu version nào.
- Có còn giữ write sau crash không.
- Được phép trả về một write chưa commit không.
- Có bị ghi đè bởi write khác không.
- Có trả value cho coordinator hay chỉ ACK nhận request.
- Có cùng membership epoch với các replica còn lại không.

**Giao nhau là cơ hội trao đổi thông tin; một giao thức đúng phải sử dụng thông tin đó đúng cách.**

---

## 4. Bảng các cấu hình quorum phổ biến

| N | W | R | R+W>N? | Giao nhau tối thiểu | Ghi–ghi giao nhau chắc chắn? |
|---:|---:|---:|---|---:|---|
| 3 | 2 | 2 | Có | 1 | Có, vì \(2W=4>3\) |
| 3 | 3 | 1 | Có | 1 | Có |
| 3 | 1 | 3 | Có | 1 | Không |
| 4 | 2 | 2 | Không | 0 | Không |
| 4 | 2 | 3 | Có | 1 | Không |
| 5 | 3 | 3 | Có | 1 | Có |
| 5 | 4 | 2 | Có | 1 | Có |
| 5 | 2 | 4 | Có | 1 | Không |
| 5 | 5 | 1 | Có | 1 | Có |
| 5 | 1 | 5 | Có | 1 | Không |

Cột cuối kiểm tra **hai tập write quorum** cùng kích thước W có giao nhau không, dựa trên điều kiện:

\[
2W>N.
\]

Điều kiện \(R+W>N\) **khác** điều kiện \(2W>N\).

### 4.1. Cấu hình majority–majority

Một lựa chọn quen thuộc:

\[
W=R=\left\lfloor\frac N2\right\rfloor+1.
\]

Với N=3:

\[
W=R=2.
\]

Với N=5:

\[
W=R=3.
\]

Khi mọi quorum là majority trong cùng membership, bất kỳ hai majority quorum nào cũng giao nhau.

### 4.2. Đọc ít, ghi nhiều

Với \(N=5,W=5,R=1\):

\[
R+W=6>5.
\]

Sau một write đã được cả năm replica xác nhận đúng nghĩa, một read từ bất kỳ replica nào trong cùng tập cũng có cơ hội thấy version đó. Nhưng write availability thấp: chỉ cần một replica không phản hồi theo policy, write có thể không đạt W.

Tính đúng đắn vẫn đòi cách xử lý write đồng thời, write chưa hoàn tất và chọn version.

### 4.3. Ghi ít, đọc nhiều

Với \(N=5,W=1,R=5\), mọi read quorum giao mọi write quorum. Nhưng hai write quorums **có thể không giao nhau**:

~~~text
Write X ACK ở A.
Write Y ACK ở B.
Read hỏi A, B, C, D, E.
~~~

Read có thể thấy hai version mâu thuẫn; phép cộng không cho biết version nào phải thắng theo thứ tự thời gian thực.

### 4.4. Không tối ưu bằng công thức đơn lẻ

Một cấu hình có \(R+W>N\) có thể có chi phí rất cao:

- \(W=N\) yêu cầu mọi replica khi ghi.
- \(R=N\) yêu cầu mọi replica khi đọc.
- Majority yêu cầu đủ replica/quorum dù một số node mất liên lạc.

Cần xem tỷ lệ read/write, tail latency, network, topology và workload thực tế. **Không phải mọi hệ đều nên đặt R=W=majority**.

---

## 5. Ba loại giao nhau cần phân biệt

Một thiết kế quorum có thể cần phân tích **read–write**, **write–write** và **read–read**.

### 5.1. Read–write intersection

\[
R+W>N.
\]

Cung cấp ít nhất một replica chung giữa tập read và tập write của cùng đối tượng/membership.

Đây là điều kiện thường được nhắc nhất khi giải thích tại sao đọc sau ghi **có thể** thu được thông tin về write vừa xác nhận.

### 5.2. Write–write intersection

\[
W+W>N\quad\Leftrightarrow\quad 2W>N.
\]

Bảo đảm hai tập write quorum cùng kích thước W có giao nhau.

Điều này hữu ích khi giao thức cần replica chung để liên kết thứ tự của các write hoặc ngăn hai commit mâu thuẫn độc lập. Nhưng **write–write intersection tự nó vẫn chưa sắp thứ tự các write**; còn cần protocol/tag/leader/consensus.

### 5.3. Read–read intersection

\[
R+R>N\quad\Leftrightarrow\quad 2R>N.
\]

Nếu điều kiện đúng, hai read quorums luôn có node chung.

Tuy nhiên, read–read intersection **không tự bảo đảm monotonic reads**: node chung có thể trả response khác nhau, dữ liệu có thể bị rollback, read coordinator có thể bỏ qua version mới, hoặc read có thể quan sát write chưa hoàn tất.

Trong nhiều giao thức register, read–read intersection không nhất thiết là điều kiện phải dùng dưới đúng dạng này vì **read có pha write-back** hoặc cơ chế ổn định thứ tự khác.

### 5.4. Vì sao không chỉ nhìn một bất đẳng thức?

Xét \(N=5,W=2,R=4\):

\[
R+W=6>5,
\]

nên read–write giao nhau.

Nhưng:

\[
2W=4\le5,
\]

nên hai write quorums có thể không giao nhau:

~~~text
W1 ACK tại {A, B}
W2 ACK tại {C, D}
~~~

Để phát biểu linearizability, không thể chỉ dựa trên khả năng read chạm ít nhất một node của mỗi write. Phải có cơ chế quyết định **một thứ tự giá trị duy nhất, phù hợp các operation đã hoàn tất**.

---

## 6. Linearizability là gì trong bài toán đọc/ghi?

Một đối tượng đọc/ghi được gọi là **linearizable** nếu có thể xem mỗi operation như xảy ra nguyên tử tại một điểm giữa lúc **bắt đầu gọi (invocation)** và **trả kết quả (response)**, sao cho:

1. Lịch sử nhìn giống một thực thi tuần tự hợp lệ của đối tượng.
2. Nếu operation A **hoàn tất trước khi** operation B bắt đầu, A phải đứng trước B trong thứ tự ấy.
3. Operation chồng lấn nhau có thể được sắp thứ tự theo một cách hợp lệ phù hợp lịch sử và đặc tả.
4. Những operation chưa hoàn tất có thể cần được xem xét khi kiểm tra lịch sử, chứ không đơn giản bỏ qua mọi ảnh hưởng của chúng.

### 6.1. Ví dụ chắc chắn phải thấy write mới

Key `x` ban đầu bằng 0:

~~~text
Client A: W(x=1) -------- ACK
Client B:                    R(x) -> 0
~~~

Giả định read của B **bắt đầu sau** ACK của A, không có write khác, cùng đối tượng và contract hứa linearizability.

Read trả 0 là **vi phạm linearizability**.

### 6.2. Ví dụ read chồng lấn write

~~~text
Client A: W(x=1) -------------- ACK
Client B:      R(x) -> 0
~~~

Read của B có thể được tuyến tính hóa **trước** write nếu hai operation chồng lấn theo thời gian. Trả 0 không nhất thiết vi phạm.

Tương tự, read có thể thấy 1 khi write chưa ACK nếu giao thức cho phép một thứ tự phù hợp. Nhưng việc read nhìn thấy write đang dang dở đặt ra yêu cầu đối với **những read tiếp theo**, được phân tích ở phần sau.

### 6.3. Linearizable một key không tự là transaction nhiều key

Giả sử:

~~~text
A: atomic decrement inventory:sku42
B: insert reservation:res9001
~~~

Mỗi lệnh có thể linearizable trong phạm vi một key, nhưng **hai lệnh nối tiếp không tự atomic như một transaction**. Process có thể crash giữa chúng.

Muốn vừa giảm tồn kho vừa tạo reservation đúng đắn, cần transaction bao phủ cả hai hoặc giao thức điều phối/idempotency/reconciliation thích hợp.

### 6.4. Linearizability khác serializability

- **Linearizability** đặt yêu cầu thứ tự thời gian thực cho các operation trên đối tượng/phạm vi được xét.
- **Serializability** nói lịch sử transaction tương đương một lịch tuần tự, nhưng không nhất thiết tôn trọng thứ tự thời gian thực giữa những transaction không chồng lấn.
- **Strict serializability** kết hợp tính tuần tự hóa transaction với yêu cầu thời gian thực.

Cần nêu **đối tượng và transaction scope**. Không nên viết “strong consistent” mà không nói mạnh theo mô hình nào.

---

## 7. Phản ví dụ 1: R+W>N nhưng hai read liên tiếp đi lùi

Đây là tình huống quan trọng nhất để hiểu giới hạn của điều kiện giao nhau.

Giả sử:

~~~text
N = 3
W = 2
R = 2
A, B, C đều đang giữ x=v1.
~~~

Một client bắt đầu write `x=v2`, nhưng write **chỉ mới tới A** và chưa đạt W=2.

Trong lúc đó, hai read được thực hiện tuần tự:

~~~mermaid
sequenceDiagram
    participant Writer as Writer
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C
    participant Reader as Reader

    Writer->>A: Write x=v2
    Note over Writer,A: Write chưa đạt W=2, chưa ACK
    Reader->>A: Read x
    Reader->>B: Read x
    A-->>Reader: v2
    B-->>Reader: v1
    Note over Reader: Read 1 trả v2
    Reader->>B: Read x
    Reader->>C: Read x
    B-->>Reader: v1
    C-->>Reader: v1
    Note over Reader: Read 2 trả v1
~~~

Ta có:

~~~text
Write x=v2 chỉ nằm tại A, chưa được ACK.

Read 1:
  QR1 = {A, B}
  trả v2

Read 2 bắt đầu SAU Read 1 hoàn tất:
  QR2 = {B, C}
  trả v1
~~~

### 7.1. Tại sao điều này vẫn thỏa R+W>N?

Cả hai read đều hỏi 2/3 replica. Cấu hình vẫn là \(R+W=4>3\).

Nhưng **write v2 chưa có write quorum hoàn tất**. Điều kiện read–write intersection **chỉ nói về một tập write quorum đã thực sự tồn tại**. Nó không tự giải quyết việc read có được phép thấy một write mới nằm ở một replica hay không.

### 7.2. Tại sao vi phạm linearizability?

Read 1 đã trả **v2**. Nếu v2 là kết quả của một write đang dang dở, một lịch sử linearizable có thể chọn **đưa write dang dở ấy vào lịch sử** trước Read 1.

Khi đó Read 2 — bắt đầu sau Read 1 hoàn tất — không thể quay lại **v1** nếu không có một write hợp lệ khác đưa giá trị về v1.

Ngược lại, nếu loại bỏ write v2 khỏi lịch sử, Read 1 không có cơ sở trả v2.

Vì vậy không có một thứ tự tuyến tính hóa hợp lệ cho lịch sử này: **read–read đi lùi đã phơi bày một write chưa ổn định**.

### 7.3. Điều gì còn thiếu?

Một giao thức linearizable register cần quy tắc, ví dụ:

- Không cho phép read công bố dữ liệu chưa đủ điều kiện commit; **hoặc**
- Khi read nhìn thấy version v2, phải **ổn định/ghi lan truyền** v2 ở một quorum phù hợp trước khi trả kết quả; **hoặc**
- Dùng một leader/consensus protocol và quy tắc commit/read để bảo đảm mọi read hoàn tất có thứ tự nhất quán.

Không đủ nếu chỉ “hỏi R node, chọn version cao nhất rồi trả ngay”.

### 7.4. Read repair bất đồng bộ chưa chắc giải quyết

Nếu Read 1 trả v2 rồi **sau đó mới** gửi background repair, Read 2 có thể chạy trước khi repair hoàn tất và vẫn trả v1.

Với một protocol đòi write-back để bảo vệ linearizability, pha write-back thường phải được **hoàn tất theo điều kiện quorum của protocol trước khi read được coi là hoàn tất**, không chỉ khởi chạy task nền.

---

## 8. Phản ví dụ 2: hai write quorum không giao nhau

Xét cấu hình:

\[
N=5,\quad W=2,\quad R=4.
\]

Ta có:

\[
R+W=6>5
\]

nhưng:

\[
2W=4\le5.
\]

Hai write hoàn toàn có thể ACK trên những tập khác nhau:

~~~text
U = {A, B, C, D, E}

Write X = "blue":
  QW_X = {A, B}
  -> ACK

Sau ACK của X:
Write Y = "green":
  QW_Y = {C, D}
  -> ACK
~~~

Read quorum gồm bốn node sẽ giao với cả hai write quorum, nhưng nó có thể nhận:

~~~text
A -> blue
B -> blue
C -> green
D -> green
~~~

### 8.1. Giao nhau không tự trả lời giá trị nào mới hơn

Muốn tôn trọng thứ tự thời gian thực của hai write **không chồng lấn** trong ví dụ, read sau Y phải trả trạng thái phù hợp với Y, trừ khi có write khác.

Nhưng nếu coordinator chỉ dùng số lượng phản hồi, nó không biết X hay Y phải là giá trị cuối. Nó cần:

- Version/tag có thứ tự đúng.
- Cơ chế tạo tag phản ánh thứ tự hợp lệ.
- Protocol commit/write ordering.
- Conflict resolution có bảo đảm phù hợp.

### 8.2. Đồng hồ vật lý có thể làm tình hình tệ hơn

Giả sử:

~~~text
Write X hoàn tất lúc thời gian thực 10:00:00.
Node tạo X có clock chạy nhanh, timestamp=10:05:00.

Write Y bắt đầu sau X, lúc thời gian thực 10:00:01.
Node tạo Y có clock chậm, timestamp=09:59:00.
~~~

Một phép chọn **timestamp vật lý lớn nhất** sẽ chọn X, dù Y xảy ra sau X theo thứ tự thời gian thực.

Last-write-wins theo timestamp không tự là linearizable. Hệ cần biết semantics của timestamp và đồng bộ/order protocol; không thể suy từ “version mới nhất” nếu version được tạo tùy tiện bởi các clock không đồng bộ.

### 8.3. Write–write intersection vẫn chưa đủ

Kể cả nếu chọn \(W=3,N=5\) để các write quorum giao nhau, **node chung không tự tạo thứ tự đúng**. Hai coordinator vẫn cần một quy tắc update version và chấp nhận write có thứ tự, xử lý overlap và crash.

Vì vậy \(2W>N\) là một đặc tính giao nhau hữu ích trong nhiều thiết kế, không phải định lý đủ để có linearizability.

---

## 9. Phản ví dụ 3: read chọn một kết quả cũ dù đã có giao nhau

Giả sử write `x=v2` đã ACK trên `{A,B}` trong một cluster N=3.

~~~text
A: v2
B: v2
C: v1
~~~

Read quorum `{B,C}` giao với write quorum `{A,B}` tại B.

Nhưng coordinator có thể:

1. Gửi read tới B và C.
2. Chờ đủ hai phản hồi.
3. Lấy response từ C vì nó đến trước hoặc có timestamp lớn hơn do lỗi clock.
4. Trả v1.

**Đủ hai response không có nghĩa coordinator đã hợp nhất chúng đúng cách.**

Để suy ra một read “nhìn thấy” write, protocol phải quy định:

- Replica phản hồi thông tin gì (value, version, tag, commit status).
- Coordinator chọn ứng viên nào.
- Các version được so sánh theo thứ tự nào.
- Thao tác nào được phép xem là committed/visible.
- Có cần read repair/write-back hay barrier không.
- Kết quả của write concurrent được giải quyết ra sao.

Không có những quy tắc ấy, một replica chung chỉ là **đường truyền thông tin tiềm năng**, không phải lời bảo đảm rằng API sẽ sử dụng thông tin đúng.

---

## 10. Phản ví dụ 4: lost update dù từng read và write có thể mạnh

Giả sử số lượng vé còn lại là 1. Hai client đọc và ghi riêng lẻ:

~~~text
Client A: R(available) -> 1
Client B: R(available) -> 1

Client A: W(available=0)
Client B: W(available=0)

Client A: tạo Reservation A
Client B: tạo Reservation B
~~~

Từng thao tác đọc/ghi một key có thể được thực hiện với consistency mạnh, nhưng **chuỗi `read -> if -> write` không phải một thao tác nguyên tử**.

Cả hai client có thể tạo reservation, dẫn đến bán quá số lượng dù counter cuối vẫn bằng 0.

### 10.1. Linearizability của các operation nhỏ không tự atomic hóa workflow

Lịch sử vẫn có thể tuyến tính hóa:

~~~text
Read A -> 1
Read B -> 1
Write A -> 0
Write B -> 0
~~~

Không có vi phạm bắt buộc của **linearizability ở mức mỗi read/write**. Lỗi nằm ở invariant nghiệp vụ của **một thao tác cấp phát logic** chưa được bảo vệ bằng CAS/transaction.

### 10.2. Giải pháp đúng

Thực hiện một cập nhật có điều kiện:

~~~text
RESERVE(q):
  atomically:
    if available >= q:
      available -= q
      success
    else:
      out_of_capacity
~~~

Nếu counter và Reservation ở hai item, cần transaction hoặc protocol bảo đảm trạng thái phối hợp. Quorum chỉ quyết định số replica tham gia; nó **không thay thế điều kiện nghiệp vụ nguyên tử**.

---

## 11. Một protocol linearizable register cần những gì?

Có nhiều cách thiết kế một register đọc/ghi linearizable. Ví dụ dùng leader-based consensus hoặc quorum protocol có tag/pha ổn định. Các thành phần thường gồm:

1. **Danh tính và phạm vi đối tượng**: cùng key/partition.
2. **Membership/quorum hợp lệ**: biết replica nào tham gia.
3. **Version/tag có thứ tự đủ mạnh** để so sánh các candidate.
4. **Quy tắc write ordering**: các write đã hoàn tất trước nhau được phản ánh đúng.
5. **Read selection**: read dùng thông tin quorum theo protocol, không tùy chọn response đầu tiên.
6. **Xử lý write dang dở**: không để read thấy trạng thái rồi read sau bị lùi.
7. **Commit/visibility rule**: khi nào một write được công nhận là có thể trả cho read.
8. **Crash/recovery/epoch handling**: leader mới không quên write đã committed.
9. **Timeout/liveness policy**: khi nào request phải chờ hoặc thất bại.
10. **Data durability assumptions**: write ACK được lưu bền theo failure model nào.

Không phải mọi protocol cần đúng cùng các bước, nhưng **phải có một cơ chế tổng thể** giải thích vì sao mọi lịch sử được phục vụ thỏa linearizability.

### 11.1. Version phải mang thứ tự, không chỉ là một chuỗi bất kỳ

Một tag thường có dạng:

~~~text
(sequenceNumber, writerId)
~~~

với quy tắc so sánh từ điển (lexicographic), để hai writer không vô tình tạo cùng tag không phân giải được.

Tuy nhiên, **tag tăng đơn thuần không đủ** nếu writer không quan sát tag của những write trước đó hoặc commit protocol không ràng buộc thứ tự real-time.

### 11.2. Commit index và applied index khác nhau

Trong hệ leader/consensus, một entry có thể:

- Đã được leader nhận.
- Đã được một số replica lưu.
- Đã được commit theo giao thức.
- Đã được apply vào state machine.
- Đã hiển thị ở một read path.

Không phải mọi index/log entry đã xuất hiện trong memory đều là **committed state**. Read phải biết tại mốc nào nó được phép trả dữ liệu.

### 11.3. Read chỉ lấy “giá trị lớn nhất” có thể chưa đủ

Phản ví dụ Read 1 thấy v2 partial, Read 2 thấy v1 cho thấy chọn tag lớn nhất trong tập phản hồi rồi **trả ngay** chưa loại được một lịch sử không linearizable.

Một số protocol yêu cầu **write-back** để đảm bảo trạng thái đã đọc được phổ biến/ổn định trước khi trả.

---

## 12. Ví dụ protocol ABD: giao nhau cộng với nhiều pha

Một họ thuật toán nổi tiếng cho atomic register trong hệ message-passing với lỗi crash là **ABD (Attiya–Bar-Noy–Dolev)** và những biến thể multi-writer.

Mục đích ví dụ là cho thấy vì sao **quorum intersection phải đi cùng một protocol**, không phải hướng dẫn tự viết storage engine production.

### 12.1. Giả định khái quát

- Một tập N storage replicas với membership cố định trong mô hình.
- Replica có thể crash theo failure model của thuật toán.
- Có đủ replica sống để quorum tiếp tục hoạt động.
- Message có thể bị trễ hoặc sắp lại, nhưng protocol và kênh thỏa các giả định cần thiết.
- Các write/read sử dụng tag/value và quy tắc quorum cụ thể.
- Với multi-writer, tag phải được tạo để phân giải cạnh tranh.

Những chi tiết chính xác và bằng chứng đúng đắn phụ thuộc phiên bản ABD/biến thể được sử dụng.

### 12.2. Ghi với multi-writer tag

Một write có thể:

1. **Query phase:** hỏi một read quorum về tag lớn nhất đã biết.
2. Chọn tag mới lớn hơn, kèm writer ID để có thứ tự tổng trên tag.
3. **Write phase:** gửi `(tag,value)` tới một write quorum.
4. Chỉ kết thúc write khi quorum đủ điều kiện phản hồi.

~~~text
Write(v2):
  read tags from quorum
  newTag = greater than observed tags
  write (newTag, v2) to quorum
  await sufficient ACKs
~~~

Điều kiện read/write quorums và cách xử lý đồng thời đóng vai trò trong việc bảo đảm những write đã hoàn tất có thứ tự phù hợp.

### 12.3. Đọc với write-back

Một read có thể:

1. Query một quorum để nhận các `(tag,value)`.
2. Chọn entry có tag lớn nhất theo protocol.
3. **Write-back** entry đã chọn tới một write quorum.
4. Chỉ trả giá trị cho client sau khi write-back hoàn tất.

~~~text
Read():
  entries = query quorum
  candidate = maxTag(entries)
  writeBack(candidate) to quorum
  await sufficient ACKs
  return candidate.value
~~~

### 12.4. Vì sao write-back quan trọng?

Quay lại phản ví dụ ở phần 7:

~~~text
Write v2 dang dở, chỉ đến replica A.
Read 1 thấy v2 ở A/B.
~~~

Nếu Read 1 trả v2 **sau khi đã write-back v2 tới một quorum phù hợp**, những read tiếp theo có quorum giao với tập đã giữ v2, đồng thời phải tuân thủ quy tắc tag và protocol. Nhờ đó không đơn giản quay ngược về v1.

Đây là một cách biến **cơ hội giao nhau** thành **thứ tự quan sát có thể chứng minh**.

### 12.5. Không phải cứ thêm read repair là thành ABD

Một DB có asynchronous read repair hoặc anti-entropy không mặc nhiên cung cấp toàn bộ các pha, tag semantics và commit conditions của ABD.

Cũng không phải mọi hệ leader-based consensus dùng write-back cho read. Những hệ ấy có thể dùng một protocol khác để có linearizable reads.

**Điểm học được:** công thức giao nhau là một thành phần của chứng minh, không phải toàn bộ chứng minh.

---

## 13. Leader-based consensus: linearizability không chỉ đến từ R+W>N

Các hệ dùng Raft hoặc giao thức leader-based consensus tương tự thường có một thứ tự log được phối hợp bởi leader. Writer gửi request đến leader, leader replicate log entry và chỉ công bố commit khi những điều kiện giao thức được đáp ứng.

### 13.1. Majority commit

Giả sử N=3:

~~~text
Leader A
Follower B
Follower C

Write X:
  A append X
  B replicate X
  Majority {A,B} confirms
  Leader advances commit index by protocol
  Reply ACK
~~~

Trong Raft, tiêu chí commit còn có các quy tắc liên quan **term hiện tại, leader election và log matching**; không nên viết “cứ hai bản có entry là chắc chắn committed” mà bỏ qua protocol.

### 13.2. Read từ leader cũng cần bảo đảm nó còn là leader hợp lệ

Một leader cũ bị cô lập có thể vẫn có giá trị trong memory. Nếu nó trả read như thể vẫn là leader khi đã có leader mới và committed state mới ở nơi khác, có thể vi phạm linearizability.

Các cách xử lý strong read trong những hệ dùng consensus có thể bao gồm:

- **ReadIndex/quorum confirmation** để xác minh leader có quyền phục vụ read tại mốc phù hợp.
- **Leader lease** khi có những giả định về thời gian/clock phù hợp.
- Một cơ chế ghi/barrier trong log theo protocol.
- Yêu cầu state machine đã apply tới commit index cần thiết.

Không thể chỉ nói “read từ primary” mà bỏ qua tình trạng **stale leader sau partition**.

### 13.3. R=1 trên leader không bác bỏ linearizability

Một hệ leader consensus có thể thực hiện một linearizable read từ **một leader đã được xác minh bằng protocol**, không phải hỏi R replica theo kiểu Dynamo quorum read.

Khi đó \(R=1\) trong API **không tự làm nó yếu**. Bằng chứng linearizability đến từ **leader election, quorum commit, ReadIndex/lease và log ordering**, không phải áp thẳng công thức \(R+W>N\) vào số RPC mà client nhìn thấy.

### 13.4. R+W>N không phải điều kiện cần phổ quát

Đây là kết luận quan trọng:

> **R+W>N là một điều kiện giao nhau hữu ích trong một họ thiết kế quorum, nhưng không phải điều kiện cần hoặc đủ để tuyên bố linearizability của mọi hệ phân tán.**

Một hệ có thể dùng đường xác nhận read khác với quorum read. Ngược lại, một hệ thỏa bất đẳng thức vẫn có thể thiếu protocol cần thiết.

---

## 14. Sloppy quorum và hinted handoff: giao nhau có thể không còn đúng

Trong một số thiết kế kiểu Dynamo, khi home replica không khả dụng, coordinator có thể ghi tạm sang **fallback node** không thuộc tập replica gốc. Cơ chế này thường được gọi là **sloppy quorum**, kết hợp với **hinted handoff** để trả dữ liệu về home replicas sau đó.

### 14.1. Phản ví dụ

Home replica set của key:

~~~text
U = {A, B, C}
N = 3
W = 2
R = 2
~~~

Trong lúc B/C không sẵn sàng, write được xác nhận bởi:

~~~text
QW = {A, D}
~~~

trong đó **D là fallback node ngoài U**.

Sau đó read hỏi:

~~~text
QR = {B, C}
~~~

Ta có:

~~~text
QW ∩ QR = {}
~~~

Mặc dù con số khai báo vẫn là:

\[
R+W=2+2=4>3.
\]

### 14.2. Vì sao không mâu thuẫn định lý tập hợp?

Định lý ở phần 3 yêu cầu **cả QW lẫn QR là tập con của cùng U gồm N phần tử**.

Ở đây D **không thuộc U**. Giả định đã bị phá, nên không thể áp dụng kết luận.

Đây là một trong những lý do không nên nhìn vào các thông số “quorum R/W” rồi mặc định hệ tuyến tính hóa được mọi request.

### 14.3. Hinted handoff không phải ngay lập tức

Fallback node có thể giữ dữ liệu hoặc hint rồi chuyển về home replica khi nó trở lại. Quá trình này có độ trễ và giới hạn vận hành; một read tới home replicas trước khi hint hoàn tất có thể chưa có write mới.

### 14.4. “Quorum” phải định nghĩa trên tập nào

Với mỗi sản phẩm, cần hỏi:

- Là quorum của **home replica set** hay của **bất kỳ node sẵn sàng**?
- Fallback có được tính vào ACK không?
- Read có hỏi fallback nơi giữ hint không?
- Khi topology đổi, read/write quorum thuộc epoch nào?
- Mỗi ACK đảm bảo value/durable log tới đâu?

---

## 15. Membership thay đổi: hai quorum của hai tập khác nhau có thể tách nhau

Ngay cả khi không có sloppy quorum, cluster có thể reconfigure khi thêm/bớt node, thay replica hoặc chuyển partition owner.

Giả sử membership cũ:

~~~text
U_old = {A, B, C}
Write quorum cũ = {A, B}
~~~

Membership mới:

~~~text
U_new = {C, D, E}
Read quorum mới = {D, E}
~~~

Mỗi tập riêng đều có kích thước 2 trong một group N=3, nhưng:

~~~text
{A, B} ∩ {D, E} = {}
~~~

Nếu hệ chuyển membership mà không có giao thức bảo vệ, một write đã ACK trong cấu hình cũ có thể không hiện diện ở quorum mới.

### 15.1. Cách giao thức giải quyết

Các hệ dùng consensus/replication an toàn có thể:

- Quản lý **term/epoch/configuration version**.
- Sử dụng **joint consensus** hoặc điều kiện chuyển membership thích hợp.
- Chuyển dữ liệu/commit point trước khi cho phép config mới phục vụ.
- Ngăn leader cũ tiếp tục xác nhận write mâu thuẫn.
- Xác minh follower mới đã bắt kịp các entry cần thiết.

Không phải mọi hệ dùng đúng cùng kỹ thuật; điểm cốt lõi là **chứng minh giao nhau qua các giai đoạn cấu hình**, không chỉ trong từng giai đoạn.

### 15.2. Read và write phải cùng logical object và thế hệ

Một replica từng chịu trách nhiệm key X có thể bị chuyển sang keyspace/shard khác. Đếm node đó trong quorum cũ và mới không chứng minh nó giữ cùng lịch sử của X.

Version của **placement/routing metadata** là một phần thiết yếu khi đánh giá consistency dưới rebalancing.

### 15.3. Đồng thời reconfigure và failover

Khi vừa failover vừa thay membership, việc xác định commit point phức tạp hơn. Không được kết luận “majority N=3” từ dashboard đơn giản nếu hai request liên quan hai configuration epoch khác nhau.

---

## 16. Clock skew và xung đột write

Một số hệ giải quyết nhiều version bằng **last-write-wins (LWW)** dựa trên timestamp. Có thể đây là chính sách hợp lý cho workload nhất định, nhưng không phải bằng chứng linearizability.

### 16.1. Đồng hồ không đồng bộ

Hai node:

~~~text
Node A clock = +2 phút
Node B clock = -1 phút
~~~

Write X xảy ra trước Write Y theo thời gian thực. Nếu X được gắn timestamp lớn hơn Y do lệch clock, một bộ chọn max(timestamp) có thể giữ X và bỏ Y.

### 16.2. Đồng hồ có độ phân giải hạn chế

Hai write có thể nhận cùng timestamp. Nếu tie-break chỉ dựa trên node ID và không phản ánh thứ tự real-time, kết quả có thể khác kỳ vọng “write sau cùng thắng”.

### 16.3. Logical clock và hybrid logical clock

Lamport clock, vector clock hay hybrid logical clock có thể giúp biểu diễn thứ tự hoặc quan hệ nhân quả tốt hơn timestamp vật lý thuần. Nhưng:

- Lamport timestamp chỉ bảo đảm một chiều của quan hệ happens-before theo protocol.
- Vector clock có thể biểu diễn những write concurrent **không so sánh được**.
- Hybrid logical clock có giả định và ngữ nghĩa riêng.
- Một tag có thứ tự tổng **chưa đủ** nếu protocol chọn/gán tag không giữ các operation đã hoàn tất theo thứ tự cần thiết.

Vì vậy không nên thay một dòng `Date.now()` bằng “logicalVersion” rồi khẳng định linearizable.

---

## 17. Tombstone, TTL và read repair ảnh hưởng thế nào?

Quorum read còn có thể gặp dữ liệu bị xóa, TTL, hoặc replica chưa được repair.

### 17.1. Xóa có phiên bản

~~~text
Replica A: tombstone version 12
Replica B: value version 10
Replica C: value version 10
~~~

Nếu read quorum `{A,B}` trả về value v10 vì bỏ qua tombstone v12, một record đã xóa có thể “sống lại” trong kết quả.

**Delete marker cũng là trạng thái phải được xử lý trong ordering/conflict resolution.**

### 17.2. Garbage collection tombstone

Khi tombstone bị xóa vật lý trước lúc một replica cũ bắt kịp, các hệ dựa trên version/anti-entropy có thể gặp hiện tượng phục hồi record cũ hoặc thiếu thông tin xóa theo điều kiện của engine.

Các DBMS có các chính sách retention, repair và tombstone GC cụ thể. Không tự lấy \(R+W>N\) để kết luận mọi TTL/delete được nhìn nhận đúng vô thời hạn.

### 17.3. Read repair không đồng nghĩa linearizable read

Read repair có thể giúp đồng bộ bản cũ:

~~~text
Read A/B thấy v12 và v10
Coordinator chọn v12
Gửi repair v12 tới B
~~~

Nếu read trả kết quả **trước khi repair đủ điều kiện**, một read sau từ tập khác vẫn có thể thấy v10 trong những tình huống cần xem xét.

Một số engine có read-repair synchronous ở những đường đọc xác định; một số thực hiện nền; một số không hỗ trợ tương đương cho mọi query. **Phải biết semantics cụ thể.**

### 17.4. Hinted handoff và anti-entropy

Hints và repair giúp các replica dần hội tụ hoặc phục hồi sau lỗi, nhưng:

- Không tự định nghĩa một điểm tuyến tính hóa.
- Không tự đảm bảo mọi read sau write sẽ thấy mới ngay.
- Có thể bị giới hạn bởi retention, tải và consistency mode.
- Không thay thế transaction hoặc CAS.

---

## 18. Cassandra: QUORUM giúp giao nhau nhưng không tự hứa linearizability

Cassandra hỗ trợ nhiều **consistency level** với semantics phụ thuộc replication factor, topology và request.

### 18.1. Ví dụ RF=3, CL=QUORUM

~~~text
RF = 3
Write CL = QUORUM -> cần phản hồi theo quorum
Read CL  = QUORUM -> cần phản hồi theo quorum
~~~

Về số lượng, \(R=W=2\) và \(R+W>RF\), nếu đang xét cùng home replicas.

Đây là cơ sở để hiểu tại sao quorum read/write có thể tăng khả năng thấy write mới trong nhiều tình huống không có xung đột/độ trễ bất thường.

**Không nên suy ra “mọi thao tác Cassandra QUORUM đều linearizable”.**

### 18.2. Vì sao còn thiếu?

Cassandra có các đặc điểm liên quan:

- Timestamp-based reconciliation và conflict semantics.
- Concurrent writes.
- Read repair/repair theo đường và phiên bản.
- Tombstone/TTL.
- Consistency level theo datacenter như `LOCAL_QUORUM`.
- Kết quả timeout có thể không rõ.
- Commit-log persistence mode riêng.
- Các thao tác nhiều partition không tự là serializable transaction.
- Conditional updates dùng cơ chế khác với regular write.

### 18.3. Lightweight Transaction (LWT)

Khi cần kiểm tra một điều kiện và ghi **chỉ một bên thắng**, Cassandra có cơ chế LWT/Paxos cho conditional operations trong phạm vi hỗ trợ.

Ví dụ:

~~~sql
CREATE TABLE inventory_by_sku (
  sku text PRIMARY KEY,
  available int,
  version bigint
);
~~~

Giả sử đã đọc `available=1`, `version=7`, thử:

~~~sql
UPDATE inventory_by_sku
SET available = 0,
    version = 8
WHERE sku = 'sku-42'
IF version = 7;
~~~

Nếu hai client cùng thử với version 7, chỉ những thao tác thỏa điều kiện theo LWT protocol mới được áp dụng. Client phải kiểm tra kết quả **`[applied]`**, không chỉ sự thành công của việc gửi CQL.

### 18.4. SERIAL và LOCAL_SERIAL

Cassandra có những mức **serial consistency** liên quan tới LWT, với scope giữa các replica/datacenter theo cấu hình. Chúng không phải nhãn thay thế cho mọi consistency level của normal read/write.

Khi dùng LWT, cần đọc tài liệu của phiên bản Cassandra/driver cụ thể về serial CL, regular CL, Paxos contention và điều kiện read/commit.

### 18.5. CL=QUORUM không tự thay thế LWT

Sai:

~~~text
Đọc available=1 bằng QUORUM.
Hai client đều thấy 1.
Cả hai ghi available=0 bằng QUORUM.
Cả hai tạo reservation.
~~~

Quorum read/write **không biến chuỗi check-then-act của Java thành atomic CAS**. Cần một atomic conditional operation hoặc transaction/workflow có bảo vệ invariant.

### 18.6. LOCAL_QUORUM không tự là global quorum

Khi có nhiều datacenter, `LOCAL_QUORUM` tính quorum trong một DC theo topology. Hai operation ở hai DC khác nhau có thể không có giao nhau như khi giả định cùng một U cố định trên toàn hệ.

Cần chỉ rõ **local hay global**, RF theo DC và cách dữ liệu được reconcile.

---

## 19. MongoDB: majority write và linearizable read là hai cấu hình khác nhau

MongoDB cung cấp:

- Atomicity trong một document đối với thao tác phù hợp.
- Multi-document transactions trong phạm vi hỗ trợ.
- Write concern như `w:1` hoặc `"majority"`.
- Journaling qua `j` theo semantics sản phẩm.
- Read concern như `local`, `majority`, `linearizable` với những điều kiện khác nhau.
- Causal sessions khi được cấu hình phù hợp.

### 19.1. Majority write concern

~~~javascript
db.orders.insertOne(
  { _id: "order-9001", state: "CREATED" },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

Bảo đảm write acknowledgment được yêu cầu theo MongoDB majority/journaling semantics. Nhưng từ đây **không suy ngay rằng mọi `find()` ở mọi secondary đều linearizable**.

### 19.2. Read concern majority

Một read với `readConcern: "majority"` gắn với dữ liệu đã được majority committed theo semantics của MongoDB, nhưng **không nhất thiết luôn đọc được write mới nhất theo thời gian thực**.

Cần phân biệt snapshot dữ liệu majority-committed với **linearizable read**.

### 19.3. Read concern linearizable

Với những read operation được MongoDB hỗ trợ, `linearizable` read concern có thể dùng để yêu cầu semantics gần với linearizability cho **một document** trong những điều kiện xác định về primary/replica set/majority write.

Ví dụ minh họa:

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "order-9001" },
  limit: 1,
  singleBatch: true,
  readConcern: { level: "linearizable" },
  maxTimeMS: 2000
});
~~~

Phải kiểm tra phiên bản server/driver, điều kiện hỗ trợ, read preference, timeout và write concern phù hợp. Nếu cluster không thể đáp ứng trong partition, read có thể phải chờ/lỗi thay vì trả dữ liệu stale.

**Linearizable read một document không tự mở rộng sang aggregation nhiều collection, search index hoặc workflow thanh toán.**

### 19.4. Causal session

Nếu ứng dụng cần read-your-writes và monotonic reads trong cùng một session, MongoDB có causal consistency với các điều kiện về session, read concern majority, write concern majority và thứ tự operation phù hợp.

**Causal/session guarantees không tự tương đương linearizability toàn hệ.**

---

## 20. DynamoDB: strong reads và conditional writes không có API chỉnh R/W trực tiếp

DynamoDB là dịch vụ managed NoSQL. Ứng dụng không chỉnh \(R\), \(W\) theo đúng mô hình quorum kiểu Dynamo ở từng lời gọi theo cách trên.

### 20.1. Strongly consistent GetItem

~~~javascript
import { GetCommand } from "@aws-sdk/lib-dynamodb";

const result = await documentClient.send(new GetCommand({
  TableName: "Orders",
  Key: { orderId: "order-9001" },
  ConsistentRead: true
}));
~~~

Đối với base table và những đường đọc được hỗ trợ, DynamoDB cho phép yêu cầu strongly consistent read theo contract của dịch vụ trong phạm vi thích hợp.

Không nên cố suy ra giá trị R/W nội bộ từ một `ConsistentRead: true`, vì protocol replication do dịch vụ quản lý.

### 20.2. GSI eventual

Global Secondary Index chỉ hỗ trợ eventual-consistent reads. Một write vào bảng nguồn có thể đã được ACK, nhưng query GSI tạm thời chưa thấy record.

Điều này không mâu thuẫn với khả năng dùng strong read từ base table; **đường đọc khác nhau có phạm vi bảo đảm khác nhau**.

### 20.3. Conditional update

~~~javascript
import { UpdateCommand } from "@aws-sdk/lib-dynamodb";

await documentClient.send(new UpdateCommand({
  TableName: "Inventory",
  Key: { resourceId: "sku-42" },
  UpdateExpression:
    "SET available = available - :q, held = held + :q",
  ConditionExpression:
    "attribute_exists(resourceId) AND available >= :q",
  ExpressionAttributeValues: {
    ":q": 1
  }
}));
~~~

Điều kiện và update của **một item** là phạm vi phù hợp để bảo vệ counter khỏi bị trừ khi không đủ số lượng theo semantics DynamoDB.

Nếu phải tạo Reservation ở item khác, cần `TransactWriteItems` trong giới hạn hỗ trợ hoặc protocol khác.

### 20.4. Global tables và region

Một strong read trong Region A không tự bảo đảm một read ở Region B đã thấy ngay write mới trong mọi chế độ global replication. Cần xét loại global table, mode multi-region và conflict semantics hiện tại của dịch vụ.

### 20.5. Kết luận thực hành

Đối với DynamoDB, hãy hỏi: **đường API nào có strong read/transaction/conditional write**, thay vì cố áp công thức \(R+W>N\) lên các thông số mà ứng dụng không điều khiển trực tiếp.

---

## 21. Redis: lệnh nguyên tử, replica và WAIT

Redis có thể thực hiện các lệnh trên một primary theo mô hình xử lý tuần tự của server; Lua script có thể gom logic kiểm tra/cập nhật trong phạm vi một node.

### 21.1. Atomicity trong một node

Một Lua script có thể kiểm tra stock và giảm stock cùng lúc. Nhưng nó không tự là transaction trên mọi node trong Redis Cluster, và không tự bảo đảm không mất write khi primary chết.

### 21.2. Redis replication

Replica có thể theo sau primary bất đồng bộ. Một read từ replica chậm có thể thấy trạng thái cũ dù primary đã ACK.

### 21.3. WAIT không đồng nghĩa quorum protocol linearizable

~~~text
SET order:9001 "CREATED"
WAIT 1 1000
~~~

`WAIT` có thể chờ số replica xác nhận đã nhận write liên quan theo semantics Redis. Nó **không mặc nhiên** nghĩa replica đã fsync AOF, không biến mọi read replica thành linearizable và không tạo commit protocol tương đương một consensus-backed register.

### 21.4. Durability riêng

RDB/AOF và `appendfsync` quyết định một phần khả năng phục hồi local. Một lệnh atomic trên primary có thể mất sau failover nếu write chưa được bảo vệ theo failure model yêu cầu.

### 21.5. Kết luận

**Atomic operation, replication ACK, fsync và linearizable read là bốn thuộc tính khác nhau.** Không thể suy một thuộc tính từ thuộc tính còn lại chỉ vì Redis chạy rất nhanh.

---

## 22. Quorum và độ bền: ACK từ hai replica chưa chắc an toàn khi mất điện

Giả sử \(N=3,W=2\). Replica A và B ACK một write. Nhưng cần biết **ACK ở bước nào**:

~~~text
Replica A:
  append commit log vào OS buffer
  ACK

Replica B:
  cập nhật in-memory state
  ACK

Replica C:
  chưa nhận write
~~~

Nếu A và B cùng mất điện trước khi dữ liệu được lưu bền, acknowledged write có thể bị mất theo failure model.

### 22.1. Durability không được chứng minh bằng một phép cộng

Điều kiện \(R+W>N\) không quy định:

- Log đã fsync chưa.
- Replica ở miền lỗi độc lập không.
- Storage có power-loss protection không.
- Một node có được phép ACK trước journal flush không.
- Write đã commit theo epoch/leader chưa.
- Backup/PITR có bao phủ dữ liệu không.

### 22.2. Journal synced không thay thế replica

Một write được fsync chỉ trên A vẫn có thể mất khi ổ A bị phá hủy hoàn toàn nếu B/C chưa có bản phục hồi.

### 22.3. Quorum không thay thế backup

Lệnh DELETE nhầm có thể được replicate rất bền. Khi cần phục hồi trước thao tác sai, phải có snapshot/backup/PITR hoặc history phù hợp.

### 22.4. Linearizability cần được hiểu qua crash/recovery contract

Nếu một write đã hoàn tất được hứa bảo toàn, rồi failover làm nó biến mất và các read tiếp theo trả trạng thái cũ, lịch sử có thể vi phạm bảo đảm đã công bố.

Phải biết **mô hình lỗi** mà protocol chứng minh đúng: crash-stop, crash-recovery, Byzantine, mất node/zone hay network partition. Không tự mở rộng một chứng minh dưới crash-stop sang arbitrary data corruption.

---

## 23. Khi partition xảy ra: quorum và availability

Giả sử N=3, R=W=2, cluster bị chia:

~~~text
Partition 1: {A, B}
Partition 2: {C}
~~~

### 23.1. Bên có majority

Phía `{A,B}` có thể đạt quorum 2 nếu cả hai hoạt động và protocol cho phép; nó có thể tiếp tục phục vụ các operation yêu cầu quorum.

### 23.2. Bên thiểu số

Phía `{C}` không đạt quorum 2, nên write mạnh không nên được ACK như thể đã đủ quorum. Read yêu cầu hai phản hồi cũng không thể hoàn thành tại C nếu chỉ liên lạc được chính nó.

### 23.3. Có thể cho phép stale read

Một sản phẩm có thể chọn trả stale read tại C với một consistency mode yếu hơn nếu API hợp đồng cho phép.

Điều đó **không chứng minh linearizable read**, nhưng có thể hữu ích cho feed/danh mục không nhạy cảm.

### 23.4. Khi R=1, W=3

N=3,W=3,R=1 có R+W>N. Trong partition 2–1, read tại các node có thể được đáp ứng theo protocol, nhưng **write mới cần đủ 3 node** và có thể không đạt.

Quorum configuration có ảnh hưởng khác nhau tới **read availability** và **write availability**.

### 23.5. CAP không phải “chọn hai trong ba” theo mọi request

Định lý CAP tập trung vào đánh đổi giữa linearizability và availability khi mạng phân vùng. Một hệ có thể giữ C cho thao tác thanh toán và trả lỗi khi thiếu quorum, trong khi phục vụ eventual feed reads.

Cần nêu **operation, scope và failure mode**, không gắn nhãn CP/AP bất biến cho cả một sản phẩm.

---

## 24. Multi-datacenter: LOCAL_QUORUM không tự giao toàn cầu

Một cluster có hai datacenter:

~~~text
DC1: A1, A2, A3
DC2: B1, B2, B3
~~~

Nếu write được ACK bởi quorum trong DC1:

~~~text
QW = {A1, A2}
~~~

và read ở DC2 dùng local quorum:

~~~text
QR = {B1, B2}
~~~

thì:

~~~text
QW ∩ QR = {}
~~~

Các phép tính nội bộ theo từng DC có thể đều là majority, nhưng không thể dùng \(R+W>N\) với N=3 rồi suy có giao giữa hai nhóm ở **hai vũ trụ replica khác nhau**.

### 24.1. Cần hỏi “quorum của đâu?”

- Một partition trong DC1?
- Một partition trong DC2?
- Quorum trên mọi replica của nhiều DC?
- Majority voting nodes trong một consensus group?
- Home replicas hay fallback/sloppy nodes?
- Replica đã tồn tại ở configuration epoch nào?

### 24.2. Đọc sau ghi xuyên vùng

Nếu Region A ACK local write rồi Region B chưa nhận dữ liệu, B có thể trả stale. Muốn read-your-writes xuyên vùng cần:

- Route về nguồn có write.
- Chờ B đạt một watermark.
- Một consistency mode/global protocol đủ mạnh theo sản phẩm.
- Hoặc trả lỗi/chờ thay vì tự báo kết quả mới nhất.

### 24.3. Đánh đổi latency

Ghi đồng bộ xuyên vùng có thêm RTT và nhạy cảm với network partition. Một hệ có thể chọn local quorum cho feed, nhưng yêu cầu một home region/strong coordination cho reservation hoặc payment.

**Phạm vi chính sách phải được ghi trong contract, không chỉ tên consistency level.**

---

## 25. Read-your-writes và monotonic reads không tự đến từ giao nhau

Giả sử N=3, R=W=2, nhưng read đi qua cache.

~~~text
Database:
  x=v12 đã ACK quorum

Cache:
  x=v10

Client:
  GET x -> cache v10
~~~

Dù database read/write quorum có giao nhau theo toán học, **đường API không thực hiện read quorum** mà trả từ cache.

Đây là lỗi **phạm vi đường đọc**, không phải định lý toán học sai.

### 25.1. Session watermark

Một session đã thấy version 12 cần tránh đọc về version 10.

Có thể dùng:

- Version/session token do DBMS cung cấp.
- Read từ nguồn phù hợp.
- Chờ read model đạt mốc cần.
- Fallback nếu cache/index chưa bắt kịp.
- Trả lỗi nếu không thể đáp ứng trong deadline.

### 25.2. Session consistency khác linearizability toàn hệ

Read-your-writes chỉ đòi chính phiên nhìn thấy write đã hoàn tất của mình. Một client khác có thể thấy cũ nếu hợp đồng cho phép.

Monotonic reads chỉ đòi phiên **không đi lùi** so với mốc đã quan sát, không tự đảm bảo luôn thấy version mới nhất toàn cụm.

### 25.3. Quorum của database không mở rộng qua search index

Một write quorum trong source DB không có nghĩa secondary index, CDC, search hoặc Redis cache đã nhận write. Muốn RYW ở cấp ứng dụng phải đo và quản lý các đường read model ấy.

---

## 26. Những điều kiện khác biệt trong ba hướng thiết kế

| Hướng | Nguồn linearizability/consistency | Phạm vi điển hình | Điều cần kiểm tra |
|---|---|---|---|
| Dynamo-style quorum | Quorum giao nhau + version/reconciliation protocol | Key/partition tùy hệ | Sloppy quorum, concurrent writes, read repair |
| ABD-style register | Query quorum, ordered tags, write-back quorum | Một register; biến thể multi-writer | Đầy đủ các pha và failure assumptions |
| Leader-based consensus | Leader election, ordered log, majority commit, read barrier | State machine/consensus group | Term, commit index, stale leader, ReadIndex/lease |
| Conditional single-item write | CAS/condition trên item | Một item/document | Atomic match-and-update, durability |
| Serializable transaction | Transaction protocol/isolation | Tập item trong transaction | Commit, write conflict, snapshot/serialization |
| Session token | Causal/session watermark | Session và scope token | Token propagation, replica lag, failover |
| Eventual read model | Async replication/CDC | Cache/search/index | Freshness, rebuild, fallback |

Không nên ép mọi thiết kế vào một công thức R+W>N. Những hệ khác nhau có **protocol chứng minh tính đúng khác nhau**, đôi khi không expose R/W cho ứng dụng.

---

## 27. Tính latency và availability khi chọn R, W

Nếu các replica được hỏi song song, thời gian hoàn tất có thể phụ thuộc **phản hồi thứ R hoặc W** (và những bước protocol khác), không phải đơn giản là một RPC cố định.

### 27.1. Đổi W

- W lớn hơn thường khiến write cần chờ nhiều phản hồi.
- W quá lớn có thể giảm availability khi replica lỗi.
- W nhỏ hơn có thể giảm latency trong điều kiện bình thường, nhưng bảo đảm/độ an toàn phụ thuộc protocol và durability semantics.

### 27.2. Đổi R

- R lớn hơn có thể tăng chi phí read và độ nhạy với replica chậm.
- R nhỏ hơn có thể giảm chờ, nhưng read intersection có thể không còn đúng với W đã chọn.
- Nếu protocol read có thêm write-back/ReadIndex, chỉ đo R RPC là chưa đủ để đánh giá latency.

### 27.3. Mô hình availability xác suất đơn giản

Nếu mỗi replica độc lập sẵn sàng với xác suất \(p\), xác suất có **ít nhất q node** trong N node sẵn sàng là:

\[
P(\text{quorum available})
=
\sum_{k=q}^{N}
{N\choose k}p^k(1-p)^{N-k}.
\]

Đây là mô hình **giả định độc lập**. Trong thực tế, lỗi rack, zone, network và storage có thể tương quan nên con số thực khác đáng kể.

Với N=3, quorum 2:

\[
P(\ge 2)
=3p^2(1-p)+p^3.
\]

Nếu \(p=0.99\):

\[
P(\ge2)
=3(0.99)^2(0.01)+(0.99)^3
=0.999702.
\]

Con số này chỉ minh họa việc đòi hai node; **không phải SLA của DBMS** và không bao gồm coordinator, client network, latency deadline hoặc lỗi tương quan.

### 27.4. Thêm replica không tự tăng performance

Nhiều replica có thể cải thiện phân tán đọc nhưng tăng chi phí replication, repair, storage và membership management. Nếu mỗi read/write yêu cầu majority trên tập ngày càng lớn, latency/cost có thể tăng.

### 27.5. Đo tail latency

Với workload thực, cần đo:

- Read p50/p95/p99.
- Write p50/p95/p99.
- Quorum timeout và unavailable.
- Replica lag, commit lag và fsync latency.
- CAS/LWT contention.
- Read repair/write-back latency.
- Reconfiguration và failover time.
- Cross-region RTT.

---

## 28. Java: viết hàm kiểm tra toán học, không suy ra bảo đảm sản phẩm

Một utility Java có thể giúp tính cận dưới của giao nhau:

~~~java
public final class QuorumMath {

    private QuorumMath() {}

    public static int minIntersection(int n, int r, int w) {
        if (n <= 0 || r <= 0 || w <= 0 || r > n || w > n) {
            throw new IllegalArgumentException(
                "Require 1 <= r,w <= n"
            );
        }

        return Math.max(0, r + w - n);
    }

    public static boolean readWriteIntersect(int n, int r, int w) {
        return minIntersection(n, r, w) > 0;
    }

    public static boolean writeWriteIntersect(int n, int w) {
        return 2L * w > n;
    }
}
~~~

Ví dụ:

~~~java
System.out.println(QuorumMath.minIntersection(3, 2, 2));
// 1

System.out.println(QuorumMath.readWriteIntersect(5, 4, 2));
// true

System.out.println(QuorumMath.writeWriteIntersect(5, 2));
// false
~~~

**Lưu ý:** utility này **chỉ kiểm tra điều kiện tập hợp với N/R/W hợp lệ**. Nó không gọi database, không kiểm tra commit protocol và **không thể kết luận `linearizable=true`**.

### 28.1. Đừng viết hàm đánh giá linearizability bằng một if

Sai:

~~~java
boolean isLinearizable(int n, int r, int w) {
    return r + w > n;
}
~~~

Đúng về cách đặt tên:

~~~java
boolean readWriteQuorumsMustIntersect(
    int n, int r, int w
) {
    return r + w > n;
}
~~~

Một kiểm tra linearizability thật cần xét **lịch sử invocation/response và đặc tả operation**, không chỉ một cấu hình số học.

### 28.2. Scope của phép tính

Nếu một Cassandra cluster dùng RF khác nhau theo DC hoặc một Dynamo-style system có sloppy quorum, hàm trên chỉ có ý nghĩa khi caller đã xác định **N là cùng tập replica thực sự**.

Không dùng nó để chấm điểm những hệ không expose R/W như một contract trực tiếp.

---

## 29. Kiểm thử linearizability: cần ghi lịch sử thao tác

Khi kiểm tra một register/key, ghi đầy đủ:

- Client/session ID.
- Operation ID.
- Loại `read` hoặc `write`.
- Key/scope.
- Thời điểm invocation và response.
- Value, version/tag, commit status.
- Timeout hoặc lỗi.
- Replica/coordinator/region đã sử dụng.
- Membership epoch và điều kiện ACK.
- Fault injection xảy ra lúc nào.

### 29.1. Lịch sử cần điều tra

~~~text
Initial x=0

Client A:
  invoke W(x=1) at 00:00:00.000
  return ACK    at 00:00:00.050

Client B:
  invoke R(x)   at 00:00:00.100
  return x=0    at 00:00:00.130
~~~

Nếu read bắt đầu sau ACK, cùng key và contract hứa linearizability, không có write khác thì lịch sử này không hợp lệ.

### 29.2. Lịch sử chồng lấn có thể hợp lệ

~~~text
Client A:
  invoke W(x=1) at 00:00:00.000
  return ACK    at 00:00:00.100

Client B:
  invoke R(x)   at 00:00:00.050
  return x=0    at 00:00:00.070
~~~

Read có thể được tuyến tính hóa trước write vì chúng chồng lấn. Không được coi mọi read cũ khi write đang chạy là lỗi.

### 29.3. Test write chưa hoàn tất

Một bài thử đặc biệt quan trọng:

1. Bắt đầu write v2.
2. Cho một replica nhận v2 nhưng trì hoãn các replica còn lại trong test environment.
3. Chạy Read 1 ở tập có v2 và một replica cũ.
4. Chạy Read 2 sau Read 1, ở tập khác.
5. Kiểm tra có lịch sử trả v2 rồi v1 không.
6. Phân tích commit/visibility/write-back protocol.

Đây là lịch sử phản ví dụ đã phân tích ở phần 7.

### 29.4. Test membership và sloppy quorum

Trong staging:

- Thay đổi replica ownership giữa write và read.
- Thử failure và fallback/hinted handoff nếu sản phẩm hỗ trợ.
- Ghi nhận home replica set của từng operation.
- Kiểm tra giao nhau **thực tế**, không chỉ số W/R cấu hình.
- Đối soát kết quả đã ACK.

Không thực hiện fault injection phá hủy trên production khi chưa có quy trình phê duyệt.

### 29.5. Kiểm thử lịch sử nhiều client cần mốc thời gian đáng tin

Log wall-clock từ hai máy chưa đồng bộ có thể sai thứ tự real-time. Nên dùng một test coordinator có thể ghi invocation/response hoặc các cách đo/đồng bộ phù hợp, và không tự suy thứ tự từ timestamp client có clock skew.

Các hệ thống kiểm thử lịch sử phân tán có thể đánh giá tính linearizable dựa trên tập operation đã ghi, nhưng cần xác định phạm vi/đặc tả và xử lý timeout/incomplete operations đúng.

---

## 30. Những ngộ nhận phổ biến

| Ngộ nhận | Giải thích |
|---|---|
| “R+W>N chứng minh linearizable.” | Chỉ chứng minh giao nhau trong mô hình cùng tập replica cố định. |
| “R+W=N cũng đủ.” | Hai tập có thể hoàn toàn tách nhau; cần bất đẳng thức nghiêm ngặt cho giao nhau tất yếu. |
| “N là số server của cả cluster.” | Thường N là số replica của cùng partition/key trong scope đang xét. |
| “W=2 nghĩa hai ổ đã fsync.” | ACK semantics do DBMS/config quyết định. |
| “Đã gửi read tới R node là read quorum.” | Phải chờ/diễn giải đủ phản hồi theo protocol. |
| “Giao nhau là read luôn trả bản mới.” | Coordinator có thể chọn bản cũ hoặc bỏ qua thông tin từ node chung. |
| “Chọn max version là đủ.” | Tag phải có thứ tự đúng và read cần xử lý write dang dở. |
| “Read repair nền tạo linearizability.” | Nếu read hoàn tất trước repair, read sau có thể quay về bản cũ. |
| “Hai majority tự có transaction.” | Quorum không atomic hóa nhiều item/side effects. |
| “W+W>N là đủ cho linearizability.” | Còn cần write ordering/commit/read protocol. |
| “Read–read intersection tự cho monotonic reads.” | Cần version/visibility và thứ tự hợp lệ. |
| “Sloppy quorum vẫn giao vì R+W>N.” | Fallback node có thể nằm ngoài home replica set N. |
| “Majority của hai membership luôn giao.” | Reconfiguration cần protocol nối các epoch. |
| “CL=QUORUM của Cassandra là CAS.” | Conditional LWT là cơ chế khác. |
| “Cassandra LOCAL_QUORUM ở hai DC luôn giao nhau.” | Hai local quorum có thể nằm ở hai tập replica tách biệt. |
| “MongoDB majority read luôn linearizable.” | Majority snapshot khác read concern linearizable. |
| “DynamoDB ConsistentRead là R quorum tùy chỉnh.” | API là managed service contract, không expose R/W theo mô hình đó. |
| “Redis WAIT làm mọi read linearizable.” | WAIT có semantics replication, không tự là consensus/read barrier. |
| “Read primary luôn an toàn.” | Cần bảo vệ stale leader sau partition/epoch change. |
| “Đã ACK thì không thể mất.” | Durability/failure model độc lập với giao nhau số học. |
| “R+W>N ngăn oversell.” | Cần atomic conditional operation hoặc transaction. |
| “LWW timestamp đúng thứ tự real-time.” | Clock skew/concurrent writes có thể làm sai. |
| “Quorum luôn tăng availability.” | Quorum lớn có thể khiến operation không đạt khi replica mất. |
| “Có ba replica là chống mất region.” | Phải xem failure domain, topology và backup/DR. |
| “R+W>N là điều kiện cần cho mọi linearizable DB.” | Leader consensus có read protocol khác, không cần lộ R/W dưới dạng ấy. |

---

## 31. Bài tập 1: tính giao nhau và tìm cấu hình phản ví dụ

Với mỗi dòng, tính:

\[
I_{\min}=\max(0,R+W-N).
\]

Sau đó kiểm tra \(2W>N\).

| N | W | R | \(I_{\min}\) | R/W chắc chắn giao? | W/W chắc chắn giao? |
|---:|---:|---:|---|---|---|
| 3 | 2 | 2 | ? | ? | ? |
| 5 | 2 | 4 | ? | ? | ? |
| 5 | 3 | 3 | ? | ? | ? |
| 4 | 2 | 2 | ? | ? | ? |
| 7 | 4 | 4 | ? | ? | ? |
| 7 | 3 | 5 | ? | ? | ? |
| 3 | 1 | 3 | ? | ? | ? |

### Gợi ý đáp án

1. N3/W2/R2: \(I_{\min}=1\), R/W có, W/W có.
2. N5/W2/R4: \(I_{\min}=1\), R/W có, W/W không.
3. N5/W3/R3: \(I_{\min}=1\), R/W có, W/W có.
4. N4/W2/R2: \(I_{\min}=0\), R/W không, W/W không.
5. N7/W4/R4: \(I_{\min}=1\), R/W có, W/W có.
6. N7/W3/R5: \(I_{\min}=1\), R/W có, W/W không.
7. N3/W1/R3: \(I_{\min}=1\), R/W có, W/W không.

**Đừng ghi “linearizable” vào bảng**: những cột chỉ tính giao nhau của các tập.

## 32. Bài tập 2: đọc sau một write chưa hoàn tất

Trạng thái:

~~~text
N=3, W=2, R=2.
Ban đầu x=v1 trên A, B, C.
Write v2 chỉ tới A, chưa ACK.

Read 1 hỏi A+B -> v2.
Read 2 (sau Read 1) hỏi B+C -> v1.
~~~

Hãy trả lời:

1. \(R+W>N\) vẫn đúng về cấu hình không?
2. Write v2 đã tạo ra một write quorum hoàn tất chưa?
3. Tại sao lịch sử read trả v2 rồi v1 vi phạm linearizability?
4. Nếu Read 1 chỉ đọc max version rồi trả ngay, còn thiếu bước gì?
5. Một protocol read write-back có thể xử lý thế nào?
6. Nếu chỉ chạy background read repair sau ACK, liệu Read 2 có thể xảy ra trước repair không?
7. Nếu write v2 được abort, Read 1 đã trả v2 gây vấn đề gì cho thứ tự lịch sử?

**Gợi ý:** nhìn thấy write chưa được ổn định có thể buộc những read sau duy trì trạng thái đó. Giao nhau với một write quorum **chưa tồn tại** không giải quyết vấn đề.

## 33. Bài tập 3: hai write không giao nhau

Với:

~~~text
N=5, W=2, R=4
QW1={A,B}
QW2={C,D}
```

Giả sử W1 đã ACK trước khi W2 bắt đầu.

1. Hai write quorum có giao nhau không?
2. Một read quorum 4 node có giao với mỗi write quorum không?
3. Nếu A/B lưu X, C/D lưu Y, coordinator dựa vào gì để chọn đúng?
4. Nếu timestamp của X lớn hơn Y do clock skew, LWW có thể chọn sai không?
5. Thêm điều kiện \(2W>N\) có tự tạo linearizable không?
6. Hãy đề xuất một protocol version/commit/leader phù hợp để sắp thứ tự write.

## 34. Bài tập 4: sloppy quorum

Home replica set:

~~~text
U={A,B,C}
N=3, W=2, R=2

Write ACK from {A,D}, D is fallback.
Read from {B,C}.
~~~

Trả lời:

1. Tại sao \(2+2>3\) nhưng hai tập không giao?
2. Giả định nào của chứng minh ở phần 3 bị vi phạm?
3. Hinted handoff có làm read lập tức thấy write mới không?
4. Nếu client yêu cầu RYW, cần routing/watermark/fallback gì?
5. Sau khi D hỏng trước khi handoff, durability cần được xem xét ra sao?

## 35. Bài tập 5: lựa chọn cho hệ bán một vé cuối cùng

Một hệ giữ ghế:

~~~text
seat-42 = FREE
3 replicas trong cùng region
2 datacenters/regions cho frontend
1 Redis cache cho trang danh sách
Payment service nằm ngoài DB
~~~

Yêu cầu: **một seat chỉ được CONFIRMED tối đa một lần**.

Thiết kế:

1. Authoritative data/key là gì?
2. Thao tác reserve phải atomic/conditional thế nào?
3. Cần consensus/transaction scope nào?
4. Nếu phía thiểu số mất quorum, API trả gì?
5. Redis cache có thể báo “còn vé” khi nguồn đã hết không?
6. Nếu payment đến trễ sau hold expiry, xử lý thế nào?
7. Timeout sau commit phải dùng ID nào khi retry?
8. Nếu mất cả region, RPO/RTO và backup cần điều kiện gì?
9. Khi hai client cùng giữ seat cuối, test lịch sử thế nào?
10. Vì sao đặt \(R=W=2,N=3\) **một mình** chưa chứng minh business invariant?

**Hướng giải:** conditional grant trên nguồn authoritative, giữ reservation và state transition trong transaction/protocol phù hợp; timeout/retry idempotent; read model có thể eventual nhưng không có quyền cấp phát; lỗi thiếu quorum không được giả vờ thành công.

## 36. Bài tập 6: phân tích một tuyên bố kiến trúc

Nhóm phát triển nói:

> “Chúng tôi dùng Cassandra QUORUM, nên R+W>N. Vì vậy mọi write là linearizable, mọi read không bao giờ stale, counter không thể âm, failover không mất dữ liệu, và toàn hệ luôn hoạt động khi một datacenter mất.”

Hãy chỉ ra ít nhất mười giả định hoặc bảo đảm bị bỏ qua:

- RF và replica universe theo partition/DC.
- QUORUM hay LOCAL_QUORUM.
- Home replicas và fallback/sloppy behavior nếu có.
- Cơ chế version/timestamp/conflict resolution.
- Read repair hoặc write-back completion semantics.
- Write chưa hoàn tất được nhìn thấy thế nào.
- Conditional update/CAS hay read-modify-write.
- Transaction scope giữa counter và reservation.
- Commit log sync/durability ACK.
- Failure domain/datacenter placement.
- Read qua cache/index hay trực tiếp source.
- Failover/repair/membership behavior.
- Timeout và unknown commit outcome.
- Multi-region propagation.
- RPO/RTO/backup cho mất DC.
- Availability của read và write được định nghĩa khác nhau.

Viết lại thành một tập **bảo đảm có phạm vi**, ví dụ:

> “Với partition X có RF=3 trong DC Y, read/write CL=QUORUM yêu cầu số phản hồi tương ứng. Điều kiện giao nhau giúp lý luận về việc truy cập những bản sao đã phản hồi, nhưng business invariant phải dùng conditional operation và failover/durability/linearizability cần kiểm tra giao thức cụ thể.”

---

## 37. Mẫu consistency contract cho một thao tác

Trước khi đưa một quorum policy lên production, có thể ghi một tài liệu ngắn:

~~~yaml
operation: "ReadOrder(orderId)"
object_scope: "One Order in authoritative partition"
replication:
  factor: 3
  home_replicas: "Fixed set within region"
  dynamic_membership: "Requires explicit reconfiguration protocol"
read_policy:
  requested_responses: 2
  selection: "Defined by the actual DBMS protocol"
write_policy:
  acknowledged_responses: 2
  durability_condition: "Specify actual journal/commit semantics"
claimed_property:
  - "Read/write quorum sets intersect within same replica universe"
not_claimed:
  - "Linearizability without proof of read/write protocol"
  - "Atomic transaction across unrelated partitions"
  - "Immediate visibility in cache/search"
  - "Zero data loss for arbitrary region failure"
failure_behavior:
  minority_partition: "Reject or wait as required by consistency policy"
  timeout: "Outcome may be unknown; retry idempotently"
verification:
  - "Record invocation/response history"
  - "Test incomplete writes and overlapping reads"
  - "Test failover/reconfiguration in staging"
~~~

**Đây là mẫu tài liệu thiết kế, không phải file cấu hình dùng trực tiếp cho Cassandra, MongoDB, DynamoDB hay Redis.**

### 37.1. Checklist khi phát biểu linearizability

| Câu hỏi | Cần biết |
|---|---|
| **Đối tượng nào?** | Một key, một partition, một transaction hay nhiều dịch vụ? |
| **Thứ tự thật là gì?** | Invocation–response intervals, concurrent operations |
| **Replicas nào?** | Home set, RF, membership epoch |
| **Tập quorum có giao nhau?** | R+W>N, W+W nếu cần, hoặc protocol khác |
| **Tag/version có đáng tin?** | Total order/causal order và phương pháp tạo |
| **Read xử lý response ra sao?** | Max tag, commit visibility, read barrier, write-back |
| **Write concurrent ra sao?** | Leader/CAS/conflict resolution |
| **Write đang dang dở?** | Read có thể thấy không? Sau đó read khác ra sao? |
| **Leader đổi?** | Election/term/commit index/reconfiguration |
| **ACK bền tới đâu?** | Memory/log/fsync/replication/failure model |
| **Đường đọc nào?** | Primary, replica, cache, index, region |
| **Khi partition?** | Chờ, thất bại hay trả stale theo hợp đồng |
| **Test thế nào?** | Lịch sử đọc/ghi, fault injection, consistency checker |

---

## 38. Tổng kết

Bất đẳng thức:

\[
\boxed{R+W>N}
\]

có một ý nghĩa toán học rõ ràng: trong **cùng một tập N replica cố định**, mọi read quorum có ít nhất R phần tử phải giao mọi write quorum có ít nhất W phần tử.

Nó là một **điều kiện cấu trúc hữu ích** cho những giao thức replicated storage. Nhưng:

1. **Giao nhau không tự cho biết replica chung giữ version nào** hoặc write đã durable chưa.
2. **Read coordinator phải sử dụng thông tin quorum đúng cách**; chờ đủ số phản hồi nhưng chọn sai version vẫn có thể trả dữ liệu cũ.
3. **Write chưa hoàn tất là phản ví dụ quan trọng**: read thấy v2 partial rồi read sau thấy v1 có thể vi phạm linearizability dù R+W>N.
4. **Hai write cần một cơ chế ordering/commit**; điều kiện \(2W>N\) giúp quorum ghi giao nhau nhưng vẫn chưa phải chứng minh đầy đủ.
5. **Read write-back, tag protocol hoặc leader consensus** có thể biến quorum giao nhau thành bảo đảm linearizable trong những điều kiện riêng.
6. **Sloppy quorum, hinted handoff, local quorum và dynamic membership** có thể phá giả định “cùng tập N replica”.
7. **Quorum không thay thế CAS, transaction, journal, backup hay session consistency**. Mỗi thuộc tính giải quyết một bài toán khác.
8. **Linearizability phải được kiểm chứng bằng lịch sử invocation/response** và protocol của DBMS, không được suy ra từ một phép cộng.
9. **R+W>N không phải điều kiện cần hoặc đủ phổ quát** cho mọi hệ linearizable; nhiều hệ dùng leader/consensus với một read path khác.
10. **Phạm vi của bảo đảm luôn cần được nói rõ**: key/partition, region, read/write path, failure model, commit semantics, timeouts và availability.

**Câu cần nhớ: “R+W>N chứng minh có replica chung — còn linearizability đòi một giao thức đúng chứng minh các thao tác quan sát một lịch sử hợp lệ theo thời gian thực.”**
