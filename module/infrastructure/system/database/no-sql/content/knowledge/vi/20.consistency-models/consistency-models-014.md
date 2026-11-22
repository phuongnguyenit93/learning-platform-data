# Thiết kế lịch sử tối thiểu để phân biệt hai mô hình

Trong một hệ thống NoSQL phân tán, hai mô hình nhất quán có thể cho kết quả **giống nhau trong phần lớn các lần chạy bình thường** nhưng khác nhau ở một lịch sử rất ngắn: chỉ một lần ghi, một lần đọc từ client khác, hoặc hai thao tác đọc–ghi xảy ra đồng thời. Nếu chỉ chạy một luồng liên tục theo thứ tự, hệ thống có thể luôn trả về kết quả “đúng” mà ta vẫn không biết nó bảo đảm **linearizability**, **sequential consistency**, **causal consistency** hay chỉ **eventual consistency**.

Ví dụ: Client A ghi **x = 1** và nhận OK. Sau đó Client B mới bắt đầu đọc **x** nhưng nhận **0**. Nếu không có phép ghi hợp lệ nào đưa x về 0, lịch sử đó không thể giải thích bằng linearizability. Tuy nhiên, với hai client độc lập, nó vẫn có thể được xếp thành một lịch sử tuần tự theo mô hình **sequential consistency**: đọc của B đứng trước ghi của A trong thứ tự logic, dù thứ tự ấy trái thời gian thực.

Chìa khóa ở đây là **thiết kế một lịch sử phân biệt (distinguishing history)**: một tập thao tác đủ nhỏ để mô hình yếu hơn **cho phép**, trong khi mô hình mạnh hơn **bắt buộc bác bỏ**. Đây là kỹ thuật rất hữu ích khi học lý thuyết nhất quán, viết đặc tả API, xây bài kiểm thử cạnh tranh hoặc điều tra một kết quả “lạ” sau failover.

Bài học này tập trung vào **phương pháp dựng và chứng minh lịch sử tối thiểu**, không chỉ liệt kê tên các mô hình. Ta sẽ dùng thanh ghi key–value, session, các mối quan hệ thứ tự và giao dịch để tạo những phản ví dụ giữa linearizability/sequential consistency, causal/sequential consistency, causal/PRAM, causal/eventual, serializability/strict serializability và snapshot isolation/serializability. Sau đó là cách instrument, kiểm thử, thu nhỏ lỗi và tránh các kết luận sai về MongoDB, DynamoDB, Cassandra, Redis hoặc read model phân tán.

## 1. Mục tiêu của một lịch sử phân biệt

Giả sử **M_mạnh** và **M_yếu** là hai mô hình áp dụng cho cùng loại đối tượng và cùng tập thao tác. Nếu:

\[
\mathcal{H}(M_{\mathrm{mạnh}})
\subseteq
\mathcal{H}(M_{\mathrm{yếu}})
\]

thì mọi lịch sử được M_mạnh chấp nhận cũng được M_yếu chấp nhận, nhưng chiều ngược lại không nhất thiết đúng. **Lịch sử phân biệt** H cần thỏa:

\[
H \in \mathcal{H}(M_{\mathrm{yếu}})
\quad\text{và}\quad
H \notin \mathcal{H}(M_{\mathrm{mạnh}})
\]

Trong đó **\(\mathcal{H}(M)\)** là tập lịch sử được mô hình M cho phép theo một đặc tả đã xác định.

Để chứng minh đúng, phải hoàn thành **hai nửa**:

1. **Nửa chấp nhận:** chỉ ra vì sao M_yếu cho phép các kết quả, ví dụ dựng được một thứ tự tuần tự giữ program order nhưng không giữ real-time order.
2. **Nửa bác bỏ:** chỉ ra vì sao M_mạnh không cho phép, thường bằng một chuỗi ràng buộc dẫn đến mâu thuẫn hoặc một bất biến bị phá.

Chỉ nói “đọc thấy giá trị cũ nên mô hình A yếu hơn mô hình B” là chưa đủ. Giá trị cũ có thể hợp lệ do hai thao tác **chồng lấn**, do một ghi **chưa hoàn tất**, do có **ghi khác** xen vào, hoặc do mô hình chưa công bố bảo đảm cho chính đường đọc đó.

### Nếu hai mô hình không có quan hệ bao hàm

Một số bảo đảm **không so sánh được trực tiếp**. Ví dụ **read-your-writes** và **monotonic reads** là hai tính chất session khác nhau: mô hình đáp ứng cái thứ nhất không tự động đáp ứng cái thứ hai, và ngược lại.

Trong trường hợp đó, cần hai witness:

~~~text
H1: được A cho phép, B bác bỏ
H2: được B cho phép, A bác bỏ
~~~

Không được dựng một lịch sử rồi tự tuyên bố A mạnh hơn B nếu hai mô hình thực ra bảo vệ **hai chiều khác nhau**.

## 2. Định nghĩa một history trước khi tranh luận về kết quả

Một **history** ghi lại những sự kiện liên quan đến các thao tác client yêu cầu trên một hoặc nhiều đối tượng.

~~~text
invoke(P, op)    Client/process P bắt đầu gọi op
return(P, op, r) Client/process P nhận kết quả r
~~~

Ví dụ register **x** có giá trị khởi tạo bằng 0:

~~~text
A: invoke write(x, 1)
A: return write(x, 1) -> OK
B: invoke read(x)
B: return read(x) -> 0
~~~

Một lịch sử dùng để kiểm tra cần khai báo ít nhất:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Object/key** | Đối tượng đang xét | x |
| **Initial state** | Giá trị trước các thao tác thử | x = 0 |
| **Client/session** | Nguồn phát lệnh và program order | A, B |
| **Operation** | read, write, CAS, transaction… | write(x,1) |
| **Invocation** | Mốc bắt đầu thao tác | t = 1 |
| **Response** | Mốc hoàn tất, giá trị hoặc lỗi | t = 3, OK |
| **Operation ID** | Phân biệt lệnh gốc và retry | op-101 |
| **Known dependencies** | Quan hệ thời gian thực/nhân quả chắc chắn | A hoàn tất trước B bắt đầu |

Đối với API write có thể trả **accepted** nhưng thực hiện bất đồng bộ, phải nói rõ response ấy là **ACK nhận yêu cầu** hay **ACK hiệu ứng đã có hiệu lực**. Linearizability được xét theo hợp đồng của operation được công bố; không được đánh tráo “đã enqueue” với “đã ghi vào nguồn sự thật”.

## 3. Chọn một đặc tả tuần tự thật đơn giản

Một lịch sử không thể được đánh giá nếu chưa biết đối tượng **phải hành xử ra sao khi các thao tác chạy tuần tự**.

Ta bắt đầu bằng một **single-value register**:

~~~text
State:
  x = 0

write(x, v):
  x := v
  return OK

read(x):
  return x
~~~

Với lịch sử tuần tự:

~~~text
write(x, 1) -> OK
read(x)     -> 1
write(x, 2) -> OK
read(x)     -> 2
~~~

đặc tả được thỏa.

Với:

~~~text
write(x, 1) -> OK
read(x)     -> 0
~~~

đặc tả không được thỏa nếu không có write(x,0) khác ở giữa.

**Không phải mọi đối tượng đều là register.** Với counter, increment có ngữ nghĩa khác write; với set, add/remove/contains khác đọc giá trị số; với queue, enqueue/dequeue cần xét thứ tự phần tử. Bài kiểm thử phải dùng **mô hình tuần tự trùng với API thật**.

## 4. Ba loại thứ tự không được trộn lẫn

### 4.1. Program order (thứ tự chương trình/session)

Một client thực hiện xong lệnh A rồi mới gọi B:

~~~text
Client P:
  write(x,1) -> OK
  read(y)    -> 0
~~~

Ta viết:

\[
W_x \prec_{\mathrm{po}} R_y
\]

Đây là thứ tự mà mô hình **sequential consistency** bắt buộc bảo toàn cho các thao tác cùng process.

### 4.2. Real-time order (thứ tự thời gian thực)

Hai client khác nhau:

~~~text
Client A: write(x,1) ---------> OK

                                   Client B: read(x) -> 0
~~~

Nếu **response(A)** xảy ra trước **invocation(B)**, ta có:

\[
A \prec_{\mathrm{rt}} B
\]

Đây là ràng buộc được **linearizability** và **strict serializability** bổ sung. Nó không đồng nghĩa “timestamp của A nhỏ hơn timestamp của B” trên hai đồng hồ máy chủ có thể lệch.

### 4.3. Causal order (thứ tự nhân quả)

Ví dụ:

~~~text
P: write(x,1)
Q: read(x) -> 1
Q: write(y,1)
~~~

Q đọc hiệu ứng của P trước khi viết y. Vì vậy:

\[
W_x \rightarrow R_x \rightarrow W_y
\]

Quan hệ nhân quả gồm **thứ tự trong một process**, **đọc một giá trị do write tạo ra**, và **tính bắc cầu**. Hai write ở hai process không có đường phụ thuộc như vậy có thể là **concurrent** về mặt nhân quả dù chúng có một thứ tự xảy ra nào đó trong thời gian vật lý.

**Lỗi thường gặp:** một bài phân biệt causal/sequential lại vô tình thêm thông điệp giữa hai client, khiến hai write trước đó độc lập trở thành có quan hệ nhân quả. Khi ấy kết quả cần tạo có thể không còn hợp lệ dưới causal consistency.

## 5. “Tối thiểu” nghĩa là tối thiểu theo tiêu chí nào?

Một witness nhỏ có thể được tối ưu theo nhiều tiêu chí:

| Tiêu chí | Câu hỏi |
|---|---|
| **Số operation** | Ít read/write/CAS/transaction nhất có thể? |
| **Số client/session** | Cần bao nhiêu nguồn thao tác độc lập? |
| **Số object/key** | Một key đã đủ, hay phải có hai key? |
| **Số transaction** | Cần một hay hai giao dịch tương tác? |
| **Số kết quả quan sát** | Có thể bỏ một read mà vẫn chứng minh mâu thuẫn không? |
| **Số quan hệ thứ tự** | Có thêm rào cản hoặc message không cần thiết không? |
| **Số lỗi được tiêm** | Có cần failover/partition hay concurrency thuần đã đủ? |

Một bài gồm bốn operation có thể ngắn nhất về **số operation** nhưng dùng nhiều client hơn một biến thể khác. Do đó, nên viết rõ:

> “Lịch sử này nhỏ theo số operation và đủ để phân biệt trong mô hình register/session đã nêu.”

Chỉ tuyên bố **“tối thiểu tuyệt đối”** khi đã có lập luận giới hạn dưới hoặc kiểm chứng đầy đủ không tồn tại lịch sử nhỏ hơn dưới **cùng giả thiết**.

Mục tiêu học tập thường là một **witness nhỏ, minh bạch, dễ chứng minh và dễ tái hiện**, không phải cuộc thi rút ngắn một ký tự bằng cách thay đổi ý nghĩa mô hình.

## 6. Công thức thiết kế lịch sử phân biệt

~~~mermaid
flowchart TD
    A["Chọn hai mô hình và phạm vi"] --> B["Xác định bảo đảm mạnh hơn"]
    B --> C["Chọn object và các operation đơn giản"]
    C --> D["Viết initial state và program order"]
    D --> E["Dựng một kết quả mô hình yếu cho phép"]
    E --> F["Thêm real-time/causal/transaction constraints cần thiết"]
    F --> G{"Mô hình mạnh có thể giải thích?"}
    G -->|"Có"| H["Chỉnh lịch sử; chưa phân biệt"]
    G -->|"Không"| I["Chứng minh chu trình hoặc bất biến"]
    I --> J["Chỉ ra lịch sử hợp lệ cho mô hình yếu"]
    J --> K["Loại operation/cạnh thừa"]
    K --> L["Kiểm thử và ghi nhận invocation/response"]
~~~

Quy trình thực hành:

1. **Nêu cặp mô hình chính xác**, ví dụ sequential consistency so với linearizability, cùng kiểu dữ liệu register.
2. **Chỉ ra ràng buộc bổ sung của mô hình mạnh**: real-time, causal dependency, transaction serial order hoặc snapshot.
3. **Dùng số key và operation ít nhất có thể** để tạo ràng buộc đó.
4. **Khóa initial state và loại trừ hidden writes** để không có lời giải thích thay thế.
5. **Dựng timeline có invocation/response rõ**, không chỉ viết các dòng log không biết thời gian.
6. **Đưa ra response cố ý tạo mâu thuẫn** với mô hình mạnh.
7. **Chứng minh tính hợp lệ dưới mô hình yếu**, bằng một thứ tự cụ thể hoặc một tầm nhìn replica/session hợp lệ.
8. **Chứng minh bất khả dưới mô hình mạnh**, ví dụ chu trình quan hệ bắt buộc.
9. **Rút gọn** nhưng giữ nguyên hai nửa chứng minh.
10. **Chỉ sau đó mới chạy hệ thống thực** và tìm một execution giống witness.

## 7. Ví dụ A: Sequential consistency và linearizability

### Lịch sử gồm hai operation

Ban đầu **x = 0**. Có đúng hai client, một write và một read:

~~~text
Thời gian  1       2       3       4       5

Client A   |-- write(x,1) --|
                            OK

Client B                              |-- read(x) -> 0 --|
~~~

Dạng bảng:

| Operation | Client | Invoke | Response | Kết quả |
|---|---|---:|---:|---|
| W1 | A | 1 | 2 | write(x,1) → OK |
| R1 | B | 3 | 4 | read(x) → 0 |

**Điều kiện cốt lõi:** response(W1) trước invoke(R1), và không có write khác.

### Vì sao sequential consistency cho phép?

Sequential consistency yêu cầu một **thứ tự tuần tự hợp lệ giữ program order của mỗi client**. Ở đây mỗi client chỉ có một operation, nên không có ràng buộc program order nào buộc W1 trước R1.

Chọn:

~~~text
R1: read(x) -> 0
W1: write(x,1) -> OK
~~~

Thứ tự logic này hợp lệ theo register và program order mỗi client. Vì vậy lịch sử **có thể phù hợp sequential consistency**, mặc dù việc read xảy ra muộn hơn ngoài đời.

### Vì sao linearizability bác bỏ?

Linearizability phải giữ:

\[
W1 \prec_{\mathrm{rt}} R1
\]

Nên mọi thứ tự tuyến tính hợp lệ phải có **W1 trước R1**. Không có write về 0 sau đó, nên read phải trả **1**, trái với kết quả **0**.

Do đó:

\[
H \in SC,\qquad H \notin LIN
\]

Đây là một witness **hai operation, hai client, một key**. Chỉ một operation đơn độc không tạo đủ mâu thuẫn về **thứ tự hai thao tác**; dưới đặc tả register này, hai operation là một giới hạn dưới tự nhiên cho cặp mô hình.

### Một cách viết sai khiến witness không còn phân biệt

Nếu dùng **cùng client**:

~~~text
Client A:
  write(x,1) -> OK
  read(x) -> 0
~~~

thì **program order** đã buộc write trước read; cả sequential consistency lẫn linearizability đều bác bỏ. Lịch sử này phân biệt read-your-writes với một bảo đảm yếu hơn, nhưng **không phân biệt riêng SC và linearizability**.

## 8. Cẩn thận với thao tác chồng lấn

Ban đầu x = 0:

~~~text
Write W:  |---------------- write(x,1) ----------------|
Read R:             |-- read(x) -> 0 --|
~~~

W và R **overlap**. Chọn điểm tuyến tính hóa của R trước điểm W:

~~~text
R -> W
~~~

Lịch sử này **có thể linearizable**. R trả 0 chưa phải bằng chứng stale read vi phạm linearizability.

Một witness SC-vs-LIN phải có **quan hệ thời gian thực không thể đảo ngược**: write hoàn tất trước khi read bắt đầu.

### Một phép kiểm tra bổ sung

~~~text
W1: write(x,1), invoke=1, response=8
R1: read(x)->1, invoke=2, response=3
R2: read(x)->0, invoke=4, response=5
~~~

R1 và R2 đều overlap W1, nhưng **R1 kết thúc trước khi R2 bắt đầu**. Để R1 thấy 1, W1 phải đứng trước R1; R2 thấy 0 buộc R2 đứng trước W1. Real-time buộc R1 trước R2:

\[
W1 < R1 < R2 < W1
\]

Đó là chu trình, nên lịch sử **không linearizable**. Một read overlap đơn lẻ có thể hợp lệ; **nhiều read kết hợp** có thể tạo mâu thuẫn.

## 9. Ví dụ B: Eventual consistency và read-your-writes

**Read-your-writes (RYW)** là bảo đảm session: sau một write của chính client đã được công nhận, các read tiếp theo của session đó không được lùi về trạng thái trước write ấy, theo hợp đồng đối tượng.

Ban đầu x = 0:

~~~text
Client A:
  write(x,1) -> OK
  read(x)    -> 0
~~~

Đây là lịch sử chỉ **hai operation, một client, một key**.

**RYW bác bỏ:** program order buộc read sau write đã hoàn tất; không có ghi khác, nên read 0 không phản ánh write của chính session.

**Eventual consistency có thể cho phép:** write được primary nhận nhưng read tiếp theo đi qua replica còn trễ, trả giá trị 0. Nếu ngừng cập nhật, hệ vẫn có thể hội tụ về 1 về sau.

Phải phân biệt:

- Lịch sử hữu hạn trên **tương thích với eventual consistency**, không tự chứng minh một triển khai thật sự **sẽ hội tụ** sau khi hết ghi.
- Nếu write chỉ được **enqueue** mà chưa đạt mức ACK công bố, việc read trả 0 có thể là đúng theo API; hãy xác định chính xác hợp đồng.
- Nếu có write(x,0) hợp lệ sau write(x,1), read trả 0 có thể phù hợp một mô hình mạnh hơn; vì vậy khóa bối cảnh **không có write khác**.

### Cách kiểm thử

Cho cùng client ghi bằng đường nguồn rồi lập tức đọc qua đúng đường đang được quảng cáo có **RYW**. Nếu đọc từ cache được công bố eventual, việc trả 0 không vi phạm hợp đồng eventual của cache.

## 10. Ví dụ C: Eventual consistency và monotonic reads

**Monotonic reads** nghĩa là trong một session, khi client đã quan sát một phiên bản dữ liệu, những read tiếp theo không được quay về phiên bản cũ hơn theo thứ tự phiên bản được mô hình thừa nhận.

Giả sử có một write **x = 1** từ nguồn khác, ban đầu x = 0:

~~~text
Client W:
  write(x,1) -> OK

Client R:
  read(x) -> 1
  read(x) -> 0
~~~

Không có write(x,0) sau đó.

**Monotonic reads bác bỏ:** R đã thấy giá trị sau update, rồi bị chuyển sang bản replica cũ và thấy 0.

**Eventual consistency có thể cho phép:** R đọc lần đầu từ replica đã đồng bộ, lần sau từ replica chưa đồng bộ. Các replica vẫn có thể hội tụ về 1 khi hệ ổn định.

Hai cách giảm khả năng này ở tầng API:

- Giữ **session token/version watermark** và chỉ trả read đáp ứng watermark.
- Dùng đường read nhất quán mạnh hoặc stickiness có điều kiện được thiết kế đúng.

Không nên coi stickiness một cách máy móc là bảo đảm tuyệt đối: failover, cache eviction, thay đổi node và ranh giới session vẫn cần được xử lý.

## 11. Read-your-writes và monotonic reads không bao hàm nhau

Đây là ví dụ quan trọng khi hai mô hình **không mạnh–yếu theo một trục duy nhất**.

| Lịch sử | RYW | Monotonic reads |
|---|---|---|
| Client tự write(x,1) OK rồi read(x)=0 | **Vi phạm** | Không có hai read để vi phạm |
| Client chỉ read(x)=1 rồi read(x)=0, không tự write | Không có write của session để vi phạm | **Vi phạm** |

Trong bảng, mỗi lịch sử được hiểu là có initial state và các write bên ngoài thích hợp; không có write hợp lệ nào đưa x trở lại 0 ở giữa.

Vì vậy **RYW không tự suy ra monotonic reads**, và **monotonic reads không tự suy ra RYW**. Nếu một mô hình “session guarantees” bao gồm cả hai, đó là một **hợp đồng kết hợp**; phải kiểm tra từng tính chất riêng.

Khi yêu cầu “phân biệt hai mô hình”, trước tiên phải biết chúng có **quan hệ bao hàm** hay phải dùng **hai witness theo hai hướng**.

## 12. Ví dụ D: Causal consistency và sequential consistency

Một lịch sử ngắn nổi tiếng là **store buffering**. Có hai key **x=0, y=0** và hai client P, Q:

~~~text
Client P:                     Client Q:
  W(x,1) -> OK                 W(y,1) -> OK
  R(y)   -> 0                  R(x)   -> 0
~~~

Mỗi client write một key rồi đọc key của client còn lại. Hai write **không có quan hệ nhân quả với nhau** theo giả thiết: không có thông điệp hay read-from nối W(x,1) với W(y,1) trước khi chúng được thực hiện.

### Causal consistency có thể cho phép như thế nào?

Client P nhìn thấy **write của chính mình** x=1 nhưng chưa thấy y=1 của Q, nên R(y)=0. Client Q nhìn thấy write y=1 của chính mình nhưng chưa thấy x=1 của P, nên R(x)=0.

Nếu hai write độc lập nhân quả, causal consistency không bắt buộc tất cả client quan sát chúng theo một **thứ tự toàn cục duy nhất**.

### Sequential consistency bác bỏ ra sao?

Ký hiệu:

~~~text
Wx  = P viết x := 1
Ry0 = P đọc y và nhận 0
Wy  = Q viết y := 1
Rx0 = Q đọc x và nhận 0
~~~

Program order:

\[
Wx < Ry0,\qquad Wy < Rx0
\]

Để R(y)=0 trong một register có giá trị đầu 0 và chỉ một write y:=1:

\[
Ry0 < Wy
\]

Để R(x)=0:

\[
Rx0 < Wx
\]

Ghép lại:

\[
Wx < Ry0 < Wy < Rx0 < Wx
\]

Ta có một **chu trình thứ tự**: Wx phải đứng trước chính Wx, là điều không thể trong một thứ tự tuần tự. Vì thế:

\[
H \in CAUSAL,\qquad H \notin SC
\]

theo định nghĩa causal consistency giữ causal order nhưng không áp đặt thứ tự toàn cục cho các write độc lập.

Đây là witness **bốn operation, hai client, hai key**; ngắn hơn nhiều bài dựng nhiều replica và nhiều read, đồng thời đã tạo được ràng buộc mâu thuẫn rõ ràng.

### Điều kiện rất quan trọng

Không được thêm:

~~~text
P gửi thông điệp chứa x=1 cho Q,
Q nhận được rồi mới write(y,1).
~~~

Khi ấy **Wx → Wy** thành quan hệ nhân quả, và lịch sử cũ có thể không còn được causal consistency cho phép. Một witness phân biệt phải kiểm soát **không chỉ timestamp mà cả dependency**.

## 13. IRIW: ví dụ khác để nhìn rõ hai thứ tự quan sát

**Independent Reads of Independent Writes (IRIW)** dùng hai write độc lập và hai reader:

~~~text
Initial: x=0, y=0

Writer P:  W(x,1) -> OK
Writer Q:  W(y,1) -> OK

Reader A:  R(x) -> 1;  R(y) -> 0
Reader B:  R(y) -> 1;  R(x) -> 0
~~~

Hai reader quan sát **hai thứ tự trái ngược** của hai write độc lập:

- A thấy x mới nhưng y cũ.
- B thấy y mới nhưng x cũ.

Trong một thứ tự tuần tự toàn cục:

~~~text
W(x,1) < R_A(x)=1 < R_A(y)=0 < W(y,1)
W(y,1) < R_B(y)=1 < R_B(x)=0 < W(x,1)
~~~

Suy ra:

\[
W_x < W_y < W_x
\]

vô lý. Vì vậy lịch sử không sequentially consistent.

Với causal consistency, vì **Wx và Wy độc lập nhân quả**, hai reader có thể tạm quan sát những tập update khác nhau mà không phá quan hệ nhân quả nào.

**IRIW cần nhiều operation hơn store buffering**, nên thường không phải witness nhỏ nhất theo số thao tác. Nó rất hữu ích để minh họa hiện tượng **mỗi client có một thứ tự quan sát khác nhau**.

## 14. Ví dụ E: PRAM/FIFO và causal consistency

**PRAM/FIFO consistency** theo cách định nghĩa phổ biến yêu cầu các write của **cùng một process** được những process khác quan sát theo đúng thứ tự phát sinh, nhưng không nhất thiết bảo toàn **quan hệ nhân quả xuyên nhiều writer**.

Hãy tạo dependency đi qua một read:

~~~text
Initial: x=0, y=0

Client A:
  W(x,1) -> OK

Client B:
  R(x) -> 1
  W(y,1) -> OK

Client C:
  R(y) -> 1
  R(x) -> 0
~~~

### Vì sao causal consistency bác bỏ?

Các quan hệ:

\[
W_x \rightarrow R_B(x)=1
\rightarrow W_y
\rightarrow R_C(y)=1
\]

Nghĩa là **Wy phụ thuộc nhân quả vào Wx**. C đã quan sát y=1, nên một session đọc sau đó không được “quên” causal predecessor x=1 và trả x=0 nếu không có write hợp lệ khác.

### Vì sao PRAM/FIFO có thể cho phép?

Chỉ xét thứ tự write từ từng writer:

- A chỉ có một write x=1.
- B chỉ có một write y=1.

Không có **hai write cùng writer** để đặt ràng buộc FIFO giữa chúng. Một triển khai chỉ giữ per-writer order có thể để C nhìn thấy write của B trước khi thấy write của A. Nhưng causal consistency phải xét **đường read-from xuyên writer**.

Đây là minh họa cho một ràng buộc mạnh hơn được tạo bởi **communication/observed dependency**. Tên PRAM, FIFO hoặc processor consistency có thể được dùng khác nhau trong từng tài liệu; khi so sánh phải nêu **định nghĩa chính xác** chứ không chỉ dựa vào nhãn.

## 15. Ví dụ F: Eventual consistency và causal consistency

Một lịch sử ngắn hơn có thể phân biệt **causal** với **eventual** mà không cần ba client:

~~~text
Initial: x=0, y=0

Client A:
  W(x,1) -> OK
  W(y,1) -> OK

Client B:
  R(y) -> 1
  R(x) -> 0
~~~

Vì hai write trong cùng session A có:

\[
W_x \rightarrow W_y
\]

nên B đã quan sát hậu quả **y=1** phải có tầm nhìn không bỏ qua nguyên nhân **x=1** khi đọc tiếp x. Trả x=0 là vi phạm causal consistency, giả sử không có write mới hợp lệ đưa x về 0.

Một hệ eventual không bảo đảm causal visibility có thể đã cập nhật y ở replica B đọc nhưng chưa áp dụng x. Nếu ngừng ghi và replica về sau hội tụ đầy đủ, history hữu hạn này vẫn **tương thích với eventual consistency**.

### Không được nhầm “eventual cho phép” với “đã chứng minh eventual”

Eventual consistency thường bao gồm yêu cầu **hội tụ về sau khi không còn update và có điều kiện liveness phù hợp**. Một history ngắn chỉ cho thấy một kết quả chưa bị eventual consistency cấm; nó không thể chứng minh quá trình hội tụ vô hạn trong tương lai.

Muốn kiểm thử eventual convergence phải có phần riêng: dừng ghi, chờ theo chính sách và đo độ hội tụ. Phần đó **khác** nhiệm vụ dựng một witness bác bỏ causal consistency.

## 16. Ví dụ G: Serializability và strict serializability

Trong các chương về NoSQL transaction, cần phân biệt **operation** và **transaction**. Hai transaction:

~~~text
Initial: x=0

Transaction T1 (Client A):
  write(x,1)
  COMMIT -> OK

Chỉ sau khi T1 đã commit:

Transaction T2 (Client B):
  read(x) -> 0
  COMMIT -> OK
~~~

### Serializability thuần túy có thể cho phép

Serializability chỉ yêu cầu các transaction tương đương một lịch sử **tuần tự**, không nhất thiết theo thứ tự thời gian thực giữa những transaction thuộc client khác nhau.

Chọn thứ tự:

~~~text
T2: read(x) -> 0
T1: write(x,1)
~~~

Theo initial state, thứ tự ấy hợp lệ nếu chỉ xét yêu cầu serializability.

### Strict serializability bác bỏ

Strict serializability bổ sung:

\[
\mathrm{commit/response}(T1)
\prec_{\mathrm{rt}}
\mathrm{begin}(T2)
\]

Do đó T1 phải đứng trước T2 trong thứ tự serial, khiến T2 phải thấy x=1 khi không có transaction khác ghi x=0.

Lịch sử có **hai transaction trên một key** đủ để minh họa khác biệt:

\[
H \in SERIALIZABLE,\qquad H \notin STRICT\_SERIALIZABLE
\]

Đừng suy từ ví dụ rằng mọi database gắn nhãn “serializable” trên thực tế đều sẽ trả stale read kiểu này. Nó là **lịch sử được mô hình serializability thuần túy cho phép**, không phải khẳng định một engine cụ thể chắc chắn tạo ra kết quả đó.

## 17. Linearizability trên từng key không tự tạo transaction đa key

Giả sử:

~~~text
Initial: x=0, y=0
Invariant nghiệp vụ: x+y <= 1
~~~

Hai client:

~~~text
Client A:
  read(y) -> 0
  CAS(x, 0, 1) -> success

Client B:
  read(x) -> 0
  CAS(y, 0, 1) -> success
~~~

Nếu hai lần read diễn ra trước khi các CAS bên kia có hiệu lực, **mỗi key riêng** vẫn có thể linearizable, nhưng:

~~~text
x=1, y=1
~~~

vi phạm bất biến tổng.

Đây **không phải** witness chứng minh các single-key operation không linearizable. Nó chứng minh một điều khác: **độ mạnh của nhất quán từng key không thay thế giao dịch nguyên tử hoặc điều kiện phối hợp xuyên key**.

Để phân biệt hai lời hứa kỹ thuật, cần định nghĩa đúng đối tượng:

- **Lời hứa A:** từng CAS trên x/y linearizable.
- **Lời hứa B:** toàn bộ thao tác nghiệp vụ “đặt một trong hai suất” là một transaction strict serializable/atomic.

Một bài test chỉ thấy x+y=2 không được kết luận engine “vi phạm linearizability của CAS”; có thể là **ứng dụng đã ghép nhiều thao tác đúng thành một workflow sai**.

## 18. Ví dụ H: Snapshot isolation và serializability

**Write skew** là một witness kinh điển phân biệt snapshot isolation (SI) với serializability.

Giả sử luôn phải có ít nhất một bác sĩ trực:

~~~text
doctor_A.onDuty = true
doctor_B.onDuty = true
Invariant:
  A.onDuty OR B.onDuty = true
~~~

Hai transaction đồng thời đọc snapshot ban đầu:

~~~text
Transaction T1:                 Transaction T2:
  read A -> true                  read A -> true
  read B -> true                  read B -> true
  write A := false                write B := false
  COMMIT                          COMMIT
~~~

### Vì sao SI có thể cho phép?

Nếu T1 và T2 cùng thấy snapshot ban đầu và **ghi lên hai row khác nhau**, một cơ chế snapshot isolation chỉ phát hiện xung đột write–write trên cùng object có thể cho cả hai commit.

Kết quả:

~~~text
A = false
B = false
~~~

Bất biến đã bị phá, dù từng transaction được áp dụng nguyên tử trên những row nó ghi.

### Vì sao không serializable?

Nếu T1 đứng trước T2, thì T2 phải thấy **A=false**, trái kết quả đã đọc A=true.

Nếu T2 đứng trước T1, thì T1 phải thấy **B=false**, trái kết quả đã đọc B=true.

Không tồn tại một thứ tự transaction tuần tự giải thích hai kết quả đọc ban đầu và hai lần commit. Đây là chu trình **read–write antidependency**.

**SI không mặc nhiên serializable.** Tuy nhiên, một engine có thêm kiểm soát serializability, predicate locking hoặc quy tắc nghiệp vụ khác có thể chặn lịch sử này; không được lấy nhãn “snapshot read” của một API rồi tự kết luận mọi hành vi transaction của engine.

## 19. Phép thử read committed và repeatable read

Không phải mọi cặp so sánh đều là mô hình nhất quán replication. Có những cặp là **isolation level** cho transaction:

~~~text
Initial: x=0

Transaction T1:
  read(x) -> 0

Transaction T2:
  write(x,1)
  COMMIT

Transaction T1:
  read(x) -> 1
  COMMIT
~~~

Một biến thể **read committed** có thể cho phép **non-repeatable read** này: hai statement của T1 thấy hai trạng thái đã commit khác nhau. Trong một mô hình **repeatable read** bảo đảm đọc lại cùng row ổn định suốt transaction, lịch sử bị bác bỏ.

Cần nêu rõ định nghĩa isolation của sản phẩm, vì **repeatable read**, **snapshot isolation**, **serializable** và cách xử lý phantom có thể khác nhau giữa các engine. Không dùng một lịch sử transaction để chứng minh thuộc tính session/replica nếu hai mô hình không cùng loại operation.

### Lưu ý phạm vi

Một lịch sử đọc x hai lần **ngoài transaction** không chứng minh isolation level của một transaction. Phải đánh dấu **BEGIN/COMMIT**, transaction IDs và các lần đọc thuộc transaction nào.

## 20. Tại sao cần chỉ ra mâu thuẫn bằng đồ thị?

Với nhiều operation, cách chứng minh dễ kiểm tra nhất là tạo **đồ thị ràng buộc thứ tự**.

Mỗi node đại diện một operation hoặc transaction; một cạnh **A → B** nghĩa là mọi thứ tự hợp lệ của mô hình đang xét phải đặt A trước B.

Nguồn cạnh:

- **Program order:** cùng client thực hiện A rồi B.
- **Real-time order:** A trả response trước khi B invoke.
- **Reads-from:** read nhận giá trị chỉ do write cụ thể tạo ra.
- **Read-old constraint:** nếu chỉ có một write đổi 0 thành 1, read trả 0 phải đứng trước write đó trong một thứ tự register tuần tự.
- **Transaction conflict:** các read/write quan sát phiên bản cũ và sự ghi của transaction khác.

Ví dụ store buffering:

~~~mermaid
flowchart LR
    Wx["W(x)=1"] -->|"program order"| Ry["R(y)=0"]
    Ry -->|"read old y"| Wy["W(y)=1"]
    Wy -->|"program order"| Rx["R(x)=0"]
    Rx -->|"read old x"| Wx
~~~

Một đồ thị ràng buộc toàn thứ tự có **chu trình** nghĩa là không có total order thỏa mọi cạnh, nên mô hình yêu cầu total order tương ứng sẽ bác bỏ.

Tuy nhiên, **không có chu trình chưa tự động chứng minh mọi đặc tả phức tạp được thỏa**. Với queue, CAS, transaction nhiều bước hoặc pending operations, cần kiểm tra thêm tính hợp lệ của giá trị trả về/transition trong thứ tự được chọn.

## 21. Ma trận các cặp mô hình và witness ứng viên

| Cặp cần phân biệt | Witness nhỏ gọn | Mô hình cho phép | Mô hình bác bỏ |
|---|---|---|---|
| Linearizability vs sequential | A write x=1 OK; B bắt đầu sau đó, read x=0 | Sequential | Linearizable |
| RYW vs eventual | Cùng session write x=1 OK rồi read x=0 | Eventual có thể | RYW |
| Monotonic reads vs eventual | Session read x=1 rồi read x=0, không có write về 0 | Eventual có thể | Monotonic reads |
| Sequential vs causal | P W(x)=1; R(y)=0 và Q W(y)=1; R(x)=0 | Causal | Sequential |
| Causal vs PRAM/FIFO | A W(x); B đọc x rồi W(y); C đọc y mới, x cũ | PRAM/FIFO theo định nghĩa nêu | Causal |
| Causal vs eventual | Một session W(x)=1; W(y)=1; client khác thấy y=1 rồi x=0 | Eventual có thể | Causal |
| Strict serializable vs serializable | T1 commit write x=1; T2 bắt đầu sau nhưng read x=0 | Serializable | Strict serializable |
| Serializable vs snapshot isolation | Hai transaction đọc cả A,B rồi mỗi bên tắt một người trực | SI có thể | Serializable |
| Repeatable read vs read committed | T1 đọc x=0; T2 commit x=1; T1 đọc x=1 | Read committed có thể | Repeatable read theo định nghĩa |

**“Có thể” là từ quan trọng.** Nó mô tả các kết quả không bị mô hình yếu cấm trong kịch bản đã nêu, không khẳng định mọi engine triển khai mô hình ấy chắc chắn tạo ra history đó.

Một bảng so sánh tốt còn cần nêu **phạm vi operation**, **kiểu đối tượng**, **session boundaries**, **các write khác bị loại trừ** và **điều kiện tài nguyên/độ mới**.

## 22. Một witness phải loại được lời giải thích thay thế

Giả sử bạn quan sát:

~~~text
write(x,1) -> OK
read(x) -> 0
~~~

Trước khi kết luận, hỏi:

1. **Có cùng logical key không?** Hai tenant hoặc hai partition khác nhau có thể dùng tên x giống nhau.
2. **Write ACK có nghĩa gì?** Accepted/queued khác committed/visible.
3. **Read có bắt đầu sau response write không?** Nếu overlap, kết quả cũ có thể hợp lệ.
4. **Có thao tác write(x,0) hợp lệ xen giữa không?** Nếu có, read 0 có thể đúng.
5. **Read đi qua đường nào?** Base table, GSI, cache, read replica, search index hay source-of-truth?
6. **Có đọc từ một snapshot thời gian cũ theo yêu cầu không?** Snapshot historical read không nhất thiết hứa latest.
7. **Operation có timeout/unknown không?** Chưa biết write đã có hiệu ứng hay chưa.
8. **Có người/worker khác sửa dữ liệu ngoài test harness không?**
9. **Có TTL/expiration hoặc tombstone làm state thay đổi không?**
10. **Các session có đúng danh tính và cùng phạm vi cam kết không?**

Một phản ví dụ mạnh thường dùng **test key riêng, initial state được kiểm chứng, payload có version, một writer thử nghiệm và không có job nền khác**.

## 23. Chọn giá trị dễ phân biệt và không bị ABA

Nếu chỉ dùng hai giá trị 0 và 1, một chuỗi:

~~~text
x = 0
write x := 1
write x := 0
read x -> 0
~~~

có thể hợp lệ dưới linearizability dù thoạt nhìn giống stale read.

Hiện tượng **ABA**: giá trị hiện tại trở lại A sau khi từng đổi sang B. Chỉ nhìn value không biết đã có bao nhiêu lần chuyển trạng thái.

Khi instrument lịch sử, nên dùng:

~~~json
{
  "logicalKey": "seat:show-07:A12",
  "state": "HELD",
  "version": 17,
  "operationId": "claim-9001"
}
~~~

Version hoặc operation ID giúp phân biệt phiên bản có cùng giá trị. Tuy nhiên, chỉ thêm version trong response không khiến hệ tự có consistency guarantee; version phải được phát sinh và bảo vệ theo một cơ chế đúng, chẳng hạn CAS hoặc số thứ tự commit đáng tin.

Nếu mục tiêu test là register đơn giản, **loại bỏ write về giá trị cũ** thường giúp witness nhỏ và chứng minh rõ nhất.

## 24. Không gắn mọi chuyện vào timestamp tường

Một lịch sử có thể được ghi trên nhiều máy:

~~~text
Client A local time: 10:00:00.500  -> write OK
Client B local time: 10:00:00.300  -> read invoke
~~~

Không thể kết luận B bắt đầu trước A hoàn tất chỉ vì timestamp B nhỏ hơn. Đồng hồ của A/B có thể lệch hoặc được điều chỉnh.

Đối với một witness về real-time order, có thể dựng **barrier có kiểm chứng**:

~~~text
Coordinator:
  1. gửi phép write cho A
  2. đợi A trả OK và ghi nhận response
  3. sau đó mới cho B bắt đầu read
~~~

Quan hệ response(A) trước invoke(B) khi đó được xác lập bằng **luồng điều phối**, không phụ thuộc so sánh hai đồng hồ không chung gốc.

Với những thao tác cần overlap, coordinator có thể phát hai tín hiệu bắt đầu và cố ý tạo network delay, rồi lưu các quan hệ thực sự biết được. Không nên tự thêm cạnh real-time giữa các thao tác mà hệ đo không chứng minh được.

### Sự kiện log nên được giữ riêng khỏi dữ liệu nghiệp vụ

~~~json
{
  "operationId": "op-1007",
  "clientId": "client-B",
  "sessionId": "session-B",
  "key": "test:x",
  "type": "read",
  "invokedAt": "monotonic-counter-or-harness-event-15",
  "respondedAt": "monotonic-counter-or-harness-event-16",
  "outcome": "OK",
  "value": 0
}
~~~

Trên một test harness tập trung, các mốc event có thể tạo được quan hệ thời gian đáng tin. Trên nhiều máy, nên ghi thêm **barrier/communication edges**, không coi các con số monotonic nanoseconds từ các máy khác nhau là có cùng mốc gốc.

## 25. Lỗi xác định, timeout và pending operation

Một history checker không nên coi mọi response đều thuộc một trong hai nhóm “OK” và “FAIL” chung chung.

| Outcome | Ý nghĩa | Cách đưa vào phân tích |
|---|---|---|
| **OK** | Thao tác có kết quả đã xác nhận theo hợp đồng | Kiểm tra giá trị/trạng thái trả về |
| **CONDITION_FAILED** | CAS/update có điều kiện thất bại xác định | Đưa kết quả thất bại vào đặc tả CAS |
| **DEFINITE_NO_EFFECT** | Hệ bảo đảm không áp dụng hiệu ứng | Có thể loại tác động tương ứng theo đặc tả |
| **UNKNOWN_TIMEOUT** | Client không nhận phản hồi xác định | Không tự giả định không có effect |
| **PENDING** | Có invocation nhưng chưa có response | Cần quy tắc completion/extension |
| **TRANSPORT_ERROR** | Mạng gặp lỗi, không chắc request đã đến server | Thường cần đối chiếu outcome |

Trong định nghĩa linearizability, thao tác pending có thể được **hoàn tất trong một phần mở rộng history** hoặc không có mặt trong lịch sử hoàn tất tương ứng, tùy quy tắc. Việc “làm sạch log” bằng cách xóa hết timeout có thể che giấu một write thực sự đã có hiệu ứng và làm checker kết luận sai.

Ví dụ:

~~~text
A: invoke write(x,1)
A: timeout (không biết ghi xong chưa)
B: read(x) -> 1
~~~

Không được lấy việc A timeout làm bằng chứng B đọc một giá trị “chưa từng được viết”. Có thể A đã được tuyến tính hóa thành công nhưng response bị mất.

## 26. Từ phản ví dụ lý thuyết đến bài kiểm thử NoSQL thật

Một bài test tốt có hai thành phần tách biệt:

**Đặc tả:** một history nếu xảy ra sẽ phân biệt hai mô hình.

**Kịch bản thực nghiệm:** cách tạo điều kiện để hệ phân tán có thể sinh ra một history như vậy.

Ví dụ với SC vs LIN:

~~~text
Setup:
  Tạo key test:x = 0.

Writer:
  Ghi test:x = 1 bằng API được công bố.
  Đợi response thành công thật sự.

Reader:
  Chỉ bắt đầu khi writer đã báo response.
  Đọc qua API muốn kiểm chứng.

Observation:
  Nếu read -> 0, không có write mới về 0
  thì phản ví dụ bác bỏ linearizability của
  chính hợp đồng write/read đó.
~~~

**Không bao giờ khẳng định một hệ chỉ “sequential consistency” vì test chưa gặp stale read.** Việc không tìm thấy phản ví dụ không chứng minh một property. Một hệ mạnh hơn cũng chấp nhận mọi history hợp lệ của mô hình yếu hơn.

Để ép lộ lỗi cần các tình huống như replica lag, leader change, network partition, tải ghi cao hoặc cache stale — nhưng chỉ chạy fault injection trong môi trường kiểm soát và với quyền phù hợp.

## 27. Ví dụ MongoDB: phân biệt đường đọc mạnh và đọc replica

Với MongoDB, tính nguyên tử của một **updateOne trên một document**, **write concern**, **read concern** và **read preference** là những khái niệm riêng.

Giả sử ghi trạng thái:

~~~javascript
db.seats.updateOne(
  {
    _id: "show-07:A12",
    state: "AVAILABLE"
  },
  {
    $set: {
      state: "HELD",
      heldBy: "res-9001"
    }
  },
  {
    writeConcern: { w: "majority" }
  }
);
~~~

Sau khi nhận kết quả thành công, một client khác đọc từ **secondary với mode có thể stale**:

~~~text
Write W trên primary -> ACK
Read R trên secondary bắt đầu sau W -> AVAILABLE
~~~

Lịch sử này có thể bác bỏ một lời hứa **linearizable end-to-end** cho cặp API ấy nếu ứng dụng đã công bố read trả trạng thái mới nhất của cùng đối tượng. Nó **không chứng minh** MongoDB đang vi phạm read concern linearizable, bởi đường đọc secondary eventual **không phải đường đọc linearizable**.

Khi muốn một read có linearizable semantics trong phạm vi MongoDB hỗ trợ, phải dùng đúng **readConcern "linearizable"**, đọc trên topology/mode thích hợp và kết hợp write concern theo tài liệu. Không suy rằng **readConcern "majority"** có cùng ý nghĩa.

Nếu bài kiểm thử ghi qua primary rồi đọc qua cache Redis của ứng dụng, chính **hợp đồng tổng thể của API** cần được đánh giá; không được đổ trực tiếp kết quả cache stale cho một operation MongoDB mà client chưa gọi.

## 28. Ví dụ DynamoDB: base table và GSI là hai đường đọc khác nhau

DynamoDB cho phép strongly consistent read ở những API/phạm vi được hỗ trợ trên **base table/LSI**, trong khi **GSI** có cơ chế eventual consistency.

Giả sử item:

~~~text
PK = SHOW#07#SEAT#A12
state = AVAILABLE
~~~

Client A thực hiện conditional update:

~~~text
UpdateItem:
  chỉ đặt state = HELD nếu state = AVAILABLE
  kết quả: success
~~~

Client B bắt đầu Query trên một **GSI theo state** sau response của A và vẫn thấy ghế thuộc nhóm AVAILABLE trong lúc index chưa theo kịp.

Nếu GSI chỉ hứa eventual, đây không phải bằng chứng GSI vi phạm một lời hứa linearizable vốn không tồn tại. Nhưng nếu ứng dụng lấy Query GSI làm **quyết định cuối để bán ghế**, nghiệp vụ có thể gửi yêu cầu sai. Giải pháp là đưa quyết định vào **conditional update ở base item** và xem GSI là đường gợi ý/hiển thị có thể stale.

Một lịch sử phân biệt phải ghi rõ:

~~~text
Đường ghi: UpdateItem base table
Đường đọc: Query GSI
Phạm vi mô hình: end-to-end API hoặc từng thành phần?
~~~

Không dùng mô hình của base table để chứng minh GSI có strong read.

## 29. Ví dụ Cassandra: ordinary quorum không tự biến read–then–write thành CAS

Cassandra có các consistency levels cho ordinary read/write, và **LWT** cho conditional write trong phạm vi hỗ trợ.

Hai client cùng làm:

~~~text
Read state seat A12 -> AVAILABLE
Nếu AVAILABLE:
  UPDATE state = HELD, reservationId = ...
~~~

Ngay cả khi từng read/write được gửi với một quorum level phù hợp, **hai thao tác tách rời** không tự trở thành một compare-and-set. Hai client có thể cùng đọc AVAILABLE rồi ghi đè claim của nhau theo quy tắc xung đột của engine.

Nếu mục tiêu test là **“chỉ một claim thành công”**, operation cần là **LWT/conditional update** tương ứng:

~~~sql
UPDATE seat_claims
SET state = 'HELD',
    reservation_id = 'res-9001'
WHERE show_id = 'show-07'
  AND seat_id = 'A12'
IF state = 'AVAILABLE';
~~~

Ứng dụng phải kiểm tra **[applied]**, consistency scope và trạng thái trả về. Một history cho thấy hai read đều AVAILABLE **không tự chứng minh** LWT vi phạm tính tuyến tính, vì cả hai read có thể đã xảy ra trước lần claim đầu tiên được áp dụng.

Muốn phân biệt bảo đảm của **claim operation**, phải kiểm thử chính những response **success/condition-failed** của thao tác conditional, không chỉ các read tiền kiểm.

## 30. Ví dụ Redis: lệnh nguyên tử, replica và failover

Redis xử lý những command như SET, INCR và DECRBY theo thứ tự thực thi trên instance chịu trách nhiệm key. Nhưng đường đọc từ replica có thể trễ, và cấu hình replication/persistence/failover ảnh hưởng cam kết toàn hệ.

~~~text
Primary:
  SET test:x 1 -> OK

Replica:
  chưa nhận write, vẫn x=0

Client khác:
  GET test:x trên replica -> 0
~~~

Đây là witness SC-vs-LIN **nếu** write đã ACK trước read bắt đầu và cặp API được kỳ vọng linearizable. Trong thực tế, nếu read replica được công bố eventual thì history đó phù hợp hợp đồng yếu.

Một Lua script hoặc MULTI/EXEC có thể tránh những lệnh client khác chen giữa các bước trên instance thích hợp, nhưng **không tự cung cấp rollback kiểu SQL khi script có runtime error**, cũng không tự bảo đảm mọi replica/failover giữ ACK theo một mô hình nhất quán tuyến tính toàn cục.

Đừng nhầm **atomicity của một command trên một instance** với **linearizability/durability của dịch vụ nhiều node qua mọi lỗi**.

## 31. Một checker đơn giản cho register

Với các history nhỏ, có thể dùng **backtracking** trên các operation đã hoàn tất để tìm một thứ tự tuyến tính hợp lệ.

Giả sử mỗi operation có:

~~~typescript
type Operation = {
  id: string;
  clientId: string;
  kind: "read" | "write";
  value?: number;            // Đối số write hoặc response read
  invokeOrder: number;
  responseOrder: number;
};
~~~

Thuật toán ý tưởng:

~~~text
function isLinearizable(ops, initialValue):
    constraints = {
      A -> B
      nếu response(A) xảy ra trước invoke(B)
    }

    function search(prefix, remaining, currentValue):
        if remaining empty:
            return true

        candidates =
            mọi op trong remaining
            mà tất cả predecessor bắt buộc đã ở prefix

        for op in candidates:
            if op là read:
                nếu op.returnValue != currentValue:
                    continue
                nextValue = currentValue

            nếu op là write:
                nếu op.response không phù hợp đặc tả:
                    continue
                nextValue = op.argument

            if search(prefix + op, remaining - op, nextValue):
                return true

        return false

    return search([], ops, initialValue)
~~~

Một thứ tự phù hợp trả **true**. Nếu mọi cách đặt candidate đều mâu thuẫn return value hoặc precedence, history trả **false**.

Đây là **pseudocode giải thích logic**, không phải một checker production: chưa xử lý đầy đủ các operation pending, lỗi có hiệu ứng chưa rõ, CAS, realtime measurement uncertainty, transactions, tối ưu tìm kiếm hoặc quy tắc completion của linearizability. Với history lớn, backtracking có thể bùng nổ tổ hợp.

### Kiểm tra sequential consistency khác gì?

Đối với register đơn giản trong cùng giả thiết, thay bộ ràng buộc đầu vào bằng:

~~~text
A -> B chỉ khi A, B cùng process
và program order đặt A trước B
~~~

Nếu có thứ tự thỏa **program order + register spec**, nhưng không có thứ tự thỏa **real-time order + register spec**, đó là witness cho SC nhưng không LIN.

Trong một implementation checker, nên thể hiện **model constraints** như một phần của đặc tả, không hard-code mọi lỗi đọc cũ thành “vi phạm linearizability”.

## 32. Tự động rút gọn một history lỗi

Khi chạy test thực tế, history có thể chứa 100.000 operation. Một checker phát hiện không linearizable, nhưng rất khó giải thích. Ta cần **history minimization** hay **delta debugging**.

Quy trình:

1. **Lưu toàn bộ raw history**, không sửa bản gốc.
2. Xác định **đối tượng/key** liên quan và một khoảng thời gian có lỗi.
3. Loại các operation trên key không liên quan **nếu tính đúng của mô hình cho phép phân tách như vậy**.
4. Thử bỏ một phần operation.
5. Chạy lại predicate: **mô hình mạnh vẫn bác bỏ? mô hình yếu vẫn cho phép?**
6. Nếu còn là witness, giữ bản rút gọn; nếu mất, phục hồi những operation vừa bỏ.
7. Lặp đến khi không dễ bỏ thêm operation.
8. Giữ lại các **quan hệ invocation/response, session và causal edges** thiết yếu.

Điều kiện rút gọn:

\[
\mathrm{Distinguishes}(H)
= \mathrm{Allowed}(M_{\mathrm{yếu}},H)
\land \neg\mathrm{Allowed}(M_{\mathrm{mạnh}},H)
\]

Một thuật toán giảm chỉ kiểm tra **\(\neg Allowed(M_{\mathrm{mạnh}},H)\)** mà không kiểm tra tính hợp lệ ở mô hình yếu có thể cho kết quả “cực ngắn” nhưng **không còn phân biệt đúng hai mô hình**.

Không được xóa **initial-state setup write** nếu việc xóa đó khiến value đọc trở thành không rõ nguồn gốc. Không được bỏ một message read-from tạo dependency nếu đang chứng minh causal consistency.

## 33. Từ lý thuyết tối thiểu đến lịch kiểm thử có barrier

Một bài test SC-vs-LIN có thể được điều phối như sau:

~~~typescript
// Pseudocode: các lời gọi DB và barrier tùy driver.
async function testReadAfterRemoteWrite(db) {
  const key = uniqueTestKey();
  await initializeAndVerify(key, 0);

  const writeResult = await db.write(key, 1);
  assertCommittedSuccess(writeResult);

  // Barrier rõ: chỉ bắt đầu read sau khi write đã trả OK.
  const readResult = await db.readFromAdvertisedPath(key);

  recordHistory({
    key,
    writeResult,
    readResult,
    order: "write-response-before-read-invoke"
  });
}
~~~

Đây không phải một stress test tối ưu cho mọi engine; nó mô tả quan hệ thứ tự **cần có để lịch sử, nếu read trả 0, thực sự phân biệt SC và LIN**.

Với store buffering cần cố ý **overlap những thao tác phù hợp**:

~~~text
Setup x=y=0.

Barrier START:
  Client P write x=1.
  Client Q write y=1.

Client P sau khi write x ACK:
  read y.

Client Q sau khi write y ACK:
  read x.

Collect:
  P read y = ?
  Q read x = ?
~~~

Nếu cả hai read đều 0, và không có dependency ngoài ý muốn, đó là witness **causal có thể nhưng sequential không thể** theo đặc tả đã nêu.

Nếu các write lần lượt đến một primary tuyến tính duy nhất và reads không stale, test có thể **không** tạo được witness. Điều đó không biến mô hình causal thành sequential về mặt định nghĩa; nó chỉ cho thấy execution quan sát được phù hợp với một mô hình mạnh hơn.

## 34. Điều kiện kiểm thử ảnh hưởng trực tiếp đến kết luận

| Thiết kế test | Nếu không kiểm soát | Hậu quả |
|---|---|---|
| Initial state | Có dữ liệu cũ/tombstone | Không biết read 0 từ đâu |
| Key identity | Hai request khác tenant/key | So nhầm hai đối tượng |
| Operation ACK | Chỉ accepted, chưa commit | Đặt sai real-time constraint |
| Client session | Session thay đổi vô tình | Test RYW/monotonic không hợp lệ |
| Read path | Cache, GSI hoặc replica eventual | Gán sai guarantee cho source DB |
| Concurrent writers | Có hidden write về 0 | “Stale read” có thể hợp lệ |
| Clock | Hai máy lệch thời gian | Suy ra cạnh real-time giả |
| Timeout | Bỏ pending write khỏi history | Checker hiểu sai giá trị |
| Retries | Một ý định trở thành hai operation | Hiểu sai idempotency và thứ tự |
| TTL | Key hết hạn giữa các read | Giá trị cũ có thể do transition hợp lệ |
| Transactions | Không ghi begin/commit | Không phân biệt SI/serializability |
| Failover | Không biết ACK/durability | Trộn lỗi mất ghi với stale read |

### Ghi nhận kết quả “không tìm thấy phản ví dụ”

Một chuỗi 10.000 test đều hợp lệ **không chứng minh mô hình mạnh được bảo đảm**. Có thể lỗi chỉ lộ khi leader đổi, một replica chậm, một session bị chuyển node hoặc khi có race hiếm.

Mô tả đúng:

> “Trong workload và failure schedule đã thử, chưa quan sát lịch sử vi phạm mô hình X.”

Không nên viết:

> “Database X đã được chứng minh luôn linearizable vì không có lỗi trong 10.000 lần chạy.”

Tính đúng tổng quát cần bảo đảm từ thuật toán/đặc tả và kiểm chứng phù hợp, không thể suy ra chỉ từ một tập thử hữu hạn.

## 35. Phân biệt mô hình với bất biến nghiệp vụ

Một history có thể hoàn toàn linearizable nhưng vẫn sai nghiệp vụ:

~~~text
Stock ban đầu 5.

Client A:
  read stock -> 5

Client B:
  read stock -> 5

Client A:
  write stock := 1 -> OK

Client B:
  write stock := 1 -> OK
~~~

Các thao tác read/write đơn lẻ có thể được xếp thành một thứ tự linearizable; nhưng nếu cả hai request đều báo **“giữ 4 sản phẩm thành công”**, hệ đã bán vượt tồn.

Để bảo vệ bất biến, cần biến thao tác nghiệp vụ thành **conditional atomic update/CAS**:

~~~text
Reserve(4):
  nếu stock >= 4, trừ 4 và trả success
  ngược lại, không trừ và trả insufficient
~~~

Lịch sử mới phải kiểm tra **hai response Reserve**: không thể cả hai cùng success khi stock ban đầu chỉ có 5, không có replenishment.

Vì vậy, hãy phân biệt:

- **Consistency model:** những lịch sử operation nào được phép.
- **Sequential specification:** một operation có ý nghĩa gì.
- **Business invariant:** trạng thái nào được coi là hợp lệ.
- **Atomicity/transaction scope:** nhiều thay đổi thuộc cùng một operation hay không.

Một bài test nhất quán không thay thế kiểm thử điều kiện nghiệp vụ; một bài test nghiệp vụ pass cũng chưa chứng minh mọi read linearizable.

## 36. Chọn mô hình có ý nghĩa cho API thật

| API | Mô hình/bảo đảm ứng viên | Witness cần quan tâm |
|---|---|---|
| **GET ghế theo cache** | Eventual với SLO độ trễ | Read có thể stale sau claim; UI phải xử lý |
| **POST claim ghế** | Conditional atomic operation tại nguồn | Hai claim tranh chấp không cùng success |
| **GET trạng thái claim authoritative** | Strong/linearizable read trong phạm vi hỗ trợ | Read bắt đầu sau ACK claim không được thấy AVAILABLE cũ |
| **GET dashboard báo cáo** | Eventual hoặc causal theo hợp đồng | Hội tụ sau khi nguồn ngừng thay đổi |
| **PUT preferences rồi GET trong session** | RYW | Cùng session write OK rồi read cũ |
| **Đọc newsfeed qua nhiều node** | Monotonic reads/causal tùy UX | Đã thấy bài mới rồi không lùi về snapshot cũ |
| **Chuyển ownership qua hai item** | Transaction/isolation hoặc coordinator | Write skew, lost update, claim trùng |
| **Đọc transaction tổng hợp** | Snapshot/serializability nếu cần | Hai read trong transaction quan sát trạng thái không hợp lệ |

Chọn witness theo **lỗi người dùng thực sự không thể chấp nhận**, không chọn một mô hình mạnh làm nhãn trang trí rồi cố ép mọi màn hình dùng cùng read concern.

## 37. Quy trình tự chứng minh một witness bằng hai cột

Trước khi đưa một history vào bài kiểm thử, điền:

| Cột A — Mô hình yếu cho phép | Cột B — Mô hình mạnh bác bỏ |
|---|---|
| Mô hình yêu cầu giữ những quan hệ nào? | Mô hình yêu cầu thêm quan hệ nào? |
| Có thể chọn một thứ tự/visibility nào? | Cạnh bổ sung dẫn tới mâu thuẫn nào? |
| Giá trị đọc hợp lệ theo trạng thái nào? | Giá trị ấy trái đặc tả ở vị trí nào? |
| Các write có độc lập nhân quả không? | Có causal/real-time dependency nào bắt buộc? |
| Có cần thêm giả thiết triển khai không? | Có hidden write/timeout giải thích lại được không? |

Ví dụ SC vs LIN:

~~~text
Yếu (SC):
  chọn R(x)=0 trước W(x)=1.
  mỗi client chỉ có một operation -> giữ program order.

Mạnh (LIN):
  W(x)=1 đã trả OK trước khi R bắt đầu
  -> phải đặt W trước R
  -> read 0 không hợp lệ.
~~~

Ví dụ causal vs sequential:

~~~text
Yếu (causal):
  Wx và Wy độc lập; hai client thấy write của mình,
  chưa thấy write còn lại.

Mạnh (SC):
  Wx < Ry0 < Wy < Rx0 < Wx
  -> chu trình; không có thứ tự tuần tự.
~~~

Nếu **không hoàn thành được một trong hai cột**, lịch sử chưa sẵn sàng để dùng làm lời giải thích về sự khác biệt mô hình.

## 38. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hậu quả | Cách làm đúng |
|---|---|---|
| “Đọc giá trị cũ luôn là vi phạm linearizability” | Kết luận sai khi read overlap write | Kiểm tra response-before-invocation |
| “Hai model khác tên thì luôn có witness một key” | Không dựng được phân biệt SI/serializability | Chọn đúng object/transaction scope |
| “Witness được model mạnh bác bỏ là đủ” | Có thể model yếu cũng bác bỏ | Chứng minh cả hai nửa |
| “Một operation là đủ phân biệt mọi mô hình” | Thiếu ràng buộc thứ tự/quan sát | Xác định giới hạn dưới theo cặp mô hình |
| “SC giữ thứ tự thời gian giữa tất cả client” | Nhầm với linearizability | SC giữ program order trong một thứ tự toàn cục |
| “Causal buộc mọi write concurrent có thứ tự chung” | Bác nhầm store buffering/IRIW | Causal chỉ bắt buộc dependency |
| “PRAM giữ mọi dependency xuyên writer” | Nhầm per-writer order với causality | Thêm read-from chain để phân biệt |
| “RYW và monotonic reads là một” | Đánh giá session guarantee sai | Dựng hai witness theo hai hướng |
| “Serializable luôn strict serializable” | Bỏ qua real-time order | Dùng transaction T1 commit trước T2 bắt đầu |
| “SI ngăn mọi write skew” | Bất biến nhiều row có thể sai | Thiết kế transaction/isolation phù hợp |
| “Một key CAS mạnh nghĩa là workflow nhiều key nguyên tử” | Claim trùng hoặc sai tổng | Phân biệt operation và transaction |
| “Có QUORUM là tự linearizable” | Bỏ qua protocol/read mode | Xem guarantee cụ thể của engine |
| “GSI DynamoDB có same strong semantics như base table” | Test nhầm endpoint | Ghi rõ read path và consistency mode |
| “Mỗi retry là một operation mới vô hại” | $inc hoặc payment bị nhân đôi | Dùng operationId/idempotency |
| “Timeout chắc chắn không có write” | Bỏ nhầm completed effect | Đánh dấu UNKNOWN/pending |
| “Hai đồng hồ local cho thứ tự toàn hệ” | Thêm cạnh real-time giả | Dùng barrier/causal message đáng tin |
| “Một lịch sử hữu hạn chứng minh eventual consistency” | Không kiểm tra hội tụ | Phân biệt compatibility với liveness |
| “Test không ra lỗi chứng minh property” | Quá tự tin vào kiểm thử hữu hạn | Kết luận giới hạn theo workload |
| “Read cuối cùng đúng là đủ” | Bỏ qua stale reads trong quá trình | Lưu cả invocation và response |
| “Một cycle trong mọi graph đều bác tất cả mô hình” | Nhầm loại ràng buộc và phạm vi | Chỉ dùng cạnh thuộc model đang kiểm |

## 39. Bài tập thực hành

### Bài tập 1 — Chứng minh witness hai operation

Ban đầu x=0. A write(x,1) trả OK ở t=3; B bắt đầu read ở t=4 và nhận 0 ở t=5. Hãy dựng thứ tự chứng minh sequential consistency cho phép, rồi chỉ ra cạnh real-time khiến linearizability bác bỏ.

### Bài tập 2 — Chỉ đổi một cạnh

Giữ hai operation của bài 1 nhưng chuyển B bắt đầu read ở t=2, trước khi A nhận OK. Read vẫn trả 0. Giải thích vì sao lịch sử mới **có thể linearizable** và chỉ ra điểm tuyến tính hóa ứng viên.

### Bài tập 3 — Cùng client

Client A ghi x=1 OK rồi đọc x=0, không có write khác. Vì sao cả SC và LIN đều bác bỏ? Cặp mô hình nào phù hợp hơn để dùng lịch sử này làm witness?

### Bài tập 4 — Hai read chồng lấn write

W(x,1) hoạt động từ t=1 đến t=10. R1 đọc 1 trong t=2..3; R2 đọc 0 trong t=4..5. Chứng minh chu trình và cho biết history có linearizable không.

### Bài tập 5 — RYW và monotonic reads

Viết hai lịch sử: một vi phạm RYW nhưng chưa vi phạm monotonic reads, một vi phạm monotonic reads nhưng chưa vi phạm RYW. Giải thích vì sao hai bảo đảm này không bao hàm nhau.

### Bài tập 6 — Store buffering

Ban đầu x=y=0. P write x=1 rồi read y=0; Q write y=1 rồi read x=0. Dựng đồ thị bốn node và chứng minh không thể sequentially consistent. Tại sao causal consistency vẫn có thể cho phép?

### Bài tập 7 — Thêm dependency

Trong bài 6, thêm việc Q nhận thông điệp do P gửi sau write x trước khi Q write y. Quan hệ nhân quả nào xuất hiện và liệu lập luận “hai write độc lập” còn đúng không?

### Bài tập 8 — IRIW

Hai writer tạo x=1, y=1 độc lập. Reader A thấy x=1 rồi y=0; reader B thấy y=1 rồi x=0. Viết chuỗi bất đẳng thức thứ tự dẫn tới chu trình, và giải thích vì sao kết quả này chưa chắc vi phạm causal consistency.

### Bài tập 9 — PRAM so với causal

Client A write x=1, Client B read x=1 rồi write y=1, Client C read y=1 rồi read x=0. Vẽ causal edges và chỉ ra vì sao per-writer write order chưa đủ bảo vệ dependency xuyên writer.

### Bài tập 10 — Eventual và causal

Một client viết x=1 rồi y=1; client khác đọc y=1 rồi x=0. Hãy giải thích hai nửa của witness và tại sao history này không tự chứng minh replica sẽ hội tụ về sau.

### Bài tập 11 — Serializability và strict serializability

T1 write x=1 commit xong, T2 mới bắt đầu nhưng đọc x=0. Viết serial order mà serializability thuần túy cho phép và lý do strict serializability không cho phép.

### Bài tập 12 — Write skew

Hai bác sĩ cùng đang trực. T1 và T2 cùng thấy cả hai trực rồi lần lượt cho A và B nghỉ trên hai row khác nhau. Hãy chỉ ra vì sao SI có thể cho cả hai commit, nhưng không có serial transaction order hợp lệ.

### Bài tập 13 — Không nhầm consistency với invariant

Hai client đọc stock=5 rồi mỗi bên SET stock=1 và báo đã giữ 4 đơn vị. Viết một linearization order cho các read/write đơn lẻ, rồi đề xuất một CAS/conditional reserve operation để bảo vệ invariant không oversell.

### Bài tập 14 — Pending write

Write(x,1) timeout, sau đó một read trả 1. Hãy giải thích cách đưa pending operation vào chứng minh, và tại sao xóa thao tác timeout khỏi history có thể khiến checker báo sai.

### Bài tập 15 — Redis và replica

Primary nhận SET x=1, trả OK; một read bắt đầu sau đó trên replica trả 0. Hãy phân tích **hợp đồng đường đọc** chứ không chỉ tên Redis, và nêu các câu hỏi thêm về replication/failover/durability.

### Bài tập 16 — MongoDB

Thiết kế test read sau write ở cùng document với writeConcern phù hợp. So sánh một read có readConcern linearizable trong phạm vi hỗ trợ với read từ secondary eventual. Kết quả cũ vi phạm lời hứa nào, không vi phạm lời hứa nào?

### Bài tập 17 — DynamoDB

Một item được cập nhật bằng UpdateItem, sau đó Query GSI theo status chưa thấy giá trị mới. Vì sao không được coi đây là phản ví dụ chống strong read trên base table? Nếu API claim cần quyết định duy nhất, phải dùng điều kiện nào?

### Bài tập 18 — Minimize history

Một test có 1.000 operation và một checker phát hiện không linearizable. Hãy mô tả cách loại các operation không liên quan, giữ invocation/response constraints, và kiểm tra cả hai điều kiện **weak allowed** lẫn **strong rejected** sau mỗi lần rút gọn.

### Bài tập 19 — Tạo harness không dựa vào clock lệch

Viết kịch bản coordinator bảo đảm write response của A xảy ra trước read invoke của B, rồi ghi history theo operationId. Nêu vì sao chỉ so hai timestamp lấy từ đồng hồ local khác nhau chưa đủ.

### Bài tập 20 — Thiết kế witness của riêng bạn

Chọn **một cặp mô hình** trong bài và viết trọn bộ:

1. Đặc tả đối tượng và initial state.
2. Danh sách client, operation, invocation, response.
3. Những thứ tự bắt buộc theo program order/real-time/causal.
4. Thứ tự/visibility chứng minh mô hình yếu cho phép.
5. Mâu thuẫn chứng minh mô hình mạnh bác bỏ.
6. Một phương án bỏ operation thừa và lý do vẫn giữ witness.
7. Cách triển khai test, kiểm soát hidden writes và outcome UNKNOWN.

### Bài tập 21 — Một mô hình không so sánh được

Giả sử hệ A bảo đảm RYW nhưng không monotonic reads, còn hệ B bảo đảm monotonic reads nhưng không RYW. Hãy viết hai history phân biệt theo hai hướng. Tại sao không thể kết luận A “mạnh hơn” B chỉ bằng một phép đọc?

### Bài tập 22 — Mức hội tụ và thời hạn

Một read model được công bố eventual, không có cam kết thời hạn hội tụ; sản phẩm lại muốn nói “dữ liệu không trễ quá 2 giây”. Hãy phân biệt một history hữu hạn tương thích eventual với một bài test **bounded staleness**. Cần đo thêm thời gian/độ mới nào để xác minh cam kết 2 giây?

---

**Kết luận:** Muốn phân biệt hai mô hình nhất quán trong NoSQL, hãy bắt đầu từ **đặc tả thao tác và những ràng buộc thứ tự mà mô hình mạnh hơn bổ sung**, rồi tạo một **history nhỏ nhưng đủ ràng buộc** để kết quả của nó **được mô hình yếu cho phép và bị mô hình mạnh bác bỏ**. Đối với linearizability, cạnh quyết định thường là **write đã trả OK trước khi read bắt đầu**; đối với sequential consistency, các **program-order và read-value constraints** có thể tạo chu trình; đối với causal consistency, phải theo dõi **read-from và các dependency xuyên client**; đối với transaction, phải xét **serial order, real-time order và xung đột nhiều row**. Một witness đáng tin phải khai báo **initial state, key, client, invocation/response, kết quả, pending operation và phạm vi API**, đồng thời loại được hidden writes hoặc diễn giải thay thế. Sau khi chứng minh trên giấy, mới chuyển nó thành bài kiểm thử có barrier, history log và checker. **Lịch sử càng nhỏ và chứng minh càng rõ, sự khác biệt giữa hai mô hình càng khó bị che khuất bởi chi tiết triển khai.**
