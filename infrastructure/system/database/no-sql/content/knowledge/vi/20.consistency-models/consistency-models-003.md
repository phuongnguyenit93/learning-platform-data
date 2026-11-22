# Linearizability và thứ tự theo thời gian thực của thao tác

Một người dùng bấm **“Đặt ghế A12”** và nhận thông báo **“Đặt thành công”**. Sau khi thông báo ấy đã xuất hiện, một người khác kiểm tra cùng ghế và vẫn thấy **“Còn trống”**, rồi tiếp tục đặt. Nếu hệ thống hứa rằng trạng thái ghế được đọc và cập nhật với **nhất quán tuyến tính (linearizability)**, trường hợp đọc một trạng thái cũ như vậy — khi không có thao tác đổi trạng thái hợp lệ khác ở giữa — không được phép xảy ra.

Tình huống này cho thấy một đặc điểm của hệ phân tán: **thứ tự thao tác được quan sát theo thời gian thực** cũng quan trọng như giá trị cuối cùng lưu trong database. Một bản sao có thể nhận ghi muộn, mạng có thể mất phản hồi, client có thể retry, và hai thao tác có thể diễn ra chồng lấn. Khi đó, cần một tiêu chuẩn để trả lời: *Có thể xem mọi thao tác như đã xảy ra lần lượt tại một thời điểm duy nhất, theo thứ tự không mâu thuẫn với những gì người dùng đã quan sát hay không?*

**Linearizability** chính là tiêu chuẩn như vậy. Nó được dùng để suy luận về tính đúng đắn của các đối tượng được chia sẻ: khóa, thanh ghi giá trị, bộ đếm, hàng đợi, trạng thái ghế, lease, danh sách quyền sở hữu, v.v. Trong NoSQL, tiêu chuẩn này thường được đặt cạnh các lựa chọn như đọc nhất quán mạnh, đọc eventual, quorum, transaction và các cơ chế compare-and-set.

Bài học giải thích định nghĩa bằng lịch sử thao tác, phân biệt **thao tác nối tiếp** và **thao tác chồng lấn**, hướng dẫn đọc một history, so sánh với **sequential consistency**, **causal consistency**, **serializability** và **strict serializability**, sau đó khảo sát ví dụ MongoDB, DynamoDB, Cassandra, Redis và etcd. Trọng tâm là **bảo đảm có thể kiểm chứng theo đúng phạm vi**, không gắn nhãn một hệ NoSQL là “luôn linearizable” chỉ dựa vào tên sản phẩm.

## 1. Từ một lần đọc cũ đến câu hỏi về thứ tự thực

Giả sử key **seat:show-07:A12** ban đầu có giá trị **AVAILABLE**.

~~~text
T1: Client A gửi đặt ghế A12.
T2: Database ghi HELD thành công.
T3: Client A nhận phản hồi "đã giữ ghế".
T4: Client B bắt đầu đọc trạng thái A12.
T5: Client B nhận AVAILABLE.
~~~

Trong giả thiết không có thao tác hợp lệ nào đưa ghế từ HELD trở lại AVAILABLE giữa T3 và T4, kết quả của B rõ ràng mâu thuẫn với trải nghiệm đã hoàn thành của A.

Với một đối tượng **thanh ghi (register)** đơn giản có thao tác **write(value)** và **read()**, lịch sử phù hợp tuyến tính hóa phải đặt lần ghi **HELD** trước lần đọc bắt đầu sau phản hồi của ghi ấy. Lần đọc không thể trả giá trị AVAILABLE cũ.

Ngược lại, nếu B **bắt đầu đọc trước khi A hoàn tất ghi**, hai thao tác chồng lấn và B có thể thấy một trong các trạng thái theo những thứ tự tuyến tính hợp lệ. Không thể lấy riêng việc B đọc giá trị cũ để khẳng định hệ đã vi phạm linearizability.

Sự khác biệt quan trọng không phải “có bao nhiêu mili giây chênh lệch”, mà là **mối quan hệ giữa thời điểm thao tác bắt đầu và kết thúc**.

## 2. Linearizability là gì?

**Linearizability** có thể được diễn đạt như sau:

> Mỗi thao tác trên một đối tượng chia sẻ có thể được xem như đã có hiệu lực tại **một điểm** nằm trong khoảng từ lúc thao tác được gọi đến lúc trả kết quả; các điểm ấy tạo thành một thứ tự tuần tự hợp lệ và **không đảo ngược thứ tự thực của các thao tác đã hoàn tất trước khi thao tác khác bắt đầu**.

Ba ý nằm trong định nghĩa:

1. **Mỗi thao tác có khoảng thời gian thực thi:** invocation → response.
2. **Có thể chọn một điểm tuyến tính hóa** trong khoảng đó để giải thích hiệu ứng của thao tác.
3. **Thứ tự được chọn phải hợp lệ theo đặc tả đối tượng**, đồng thời tôn trọng quan hệ *response của A xảy ra trước invocation của B*.

Không nhất thiết database phải ghi một timestamp vật lý gọi là linearizationPoint. Đây là **một cách chứng minh ngữ nghĩa**: toàn bộ những điều client quan sát có thể được giải thích bằng một lịch sử tuần tự không mâu thuẫn với thời gian thực hay không.

Định nghĩa thường được áp dụng **theo đối tượng hoặc theo tập thao tác được hệ cam kết**. Không được tự chuyển lời hứa “read/write một item là tuyến tính” thành “một quy trình thay đổi ba item luôn là transaction nguyên tử”.

## 3. Invocation, response và một lịch sử thao tác (history)

Một thao tác có hai sự kiện biên:

~~~text
invoke(op)      Client bắt đầu gọi thao tác.
response(op)    Client nhận kết quả hoàn tất của thao tác.
~~~

Ví dụ:

~~~text
op W1: write(1)
  invoke tại mốc 10
  response tại mốc 30

op R1: read() -> 1
  invoke tại mốc 40
  response tại mốc 55
~~~

Ta nói **W1 đứng trước R1 theo thời gian thực**, ký hiệu:

\[
W1 \prec_{\mathrm{rt}} R1
\]

khi **response(W1)** xảy ra trước **invoke(R1)**.

Nếu hai khoảng thời gian giao nhau, chúng **overlap**. Thứ tự hoàn tất riêng lẻ hoặc thứ tự bắt đầu riêng lẻ chưa đủ để buộc chúng có cùng thứ tự tuyến tính.

Đối với một lịch sử **H**, ta cần tìm một thứ tự tuần tự **S** sao cho:

- **S hợp lệ theo đặc tả của đối tượng.** Chẳng hạn, read của register trả về giá trị của write gần nhất đứng trước trong S, hoặc giá trị khởi tạo nếu chưa có write.
- **S giữ nguyên thứ tự thời gian thực** của mọi cặp thao tác không chồng lấn.
- Những thao tác **đang chờ hoặc kết quả chưa rõ** được xử lý cẩn thận theo mô hình lịch sử; không tùy tiện xem timeout là chắc chắn không có hiệu ứng.

Một lịch sử có thể có nhiều thứ tự S hợp lệ. Linearizability yêu cầu **tồn tại ít nhất một thứ tự hợp lệ**, không yêu cầu tất cả client biết được thứ tự nội bộ mà database đã chọn.

## 4. Nhìn trực quan điểm tuyến tính hóa

Giả sử register có giá trị ban đầu 0.

~~~text
Thời gian   0       10       20       30       40       50

Client A    |---- write(1) ---------| 
            invoke                 response
                    ^
                    một điểm tuyến tính hóa có thể nằm
                    trong khoảng invoke..response

Client B                                        |-- read() -> 1 --|
                                                invoke          response
~~~

Vì write của A đã trả kết quả trước khi read của B bắt đầu, mọi lịch sử tuyến tính hợp lệ phải đặt **write(1)** trước **read() -> 1**, giả sử không có write khác can thiệp.

Một cách hình dung:

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant DB as Đối tượng dữ liệu
    participant B as Client B
    A->>DB: invoke write(1)
    Note over DB: Điểm có hiệu lực logic của write
    DB-->>A: response OK
    B->>DB: invoke read()
    DB-->>B: response 1
~~~

Lưu ý: **điểm tuyến tính hóa là điểm logic nằm giữa invocation và response**, không nhất thiết trùng thời điểm disk flush, nhận một network packet hay timestamp bên trong document. Thuật toán cụ thể phải có cơ sở để chứng minh một điểm như vậy tồn tại.

## 5. Thao tác không chồng lấn: thứ tự bắt buộc

Giả sử key K ban đầu 0:

| Mốc | Client | Sự kiện |
|---|---|---|
| 1 | A | invoke write(K, 1) |
| 2 | A | response OK |
| 3 | B | invoke read(K) |
| 4 | B | response 0 |

Không có write khác trong ví dụ. Đây là **lịch sử không linearizable**, vì mọi thứ tự tuân theo thời gian thực đều buộc write(1) đứng trước read; read trả 0 không khớp đặc tả register.

Nếu đổi phản hồi ở mốc 4 thành **1**, lịch sử có thể linearizable.

Thêm một write khác:

~~~text
A: write(K, 1) -> OK    hoàn tất
C: write(K, 2) -> OK    hoàn tất
B: read(K) -> 2        bắt đầu sau cả hai write
~~~

Read trả 2 phù hợp. Không được phát biểu quá cứng rằng “mọi read sau write(1) phải thấy 1”: nếu **write(2)** hợp lệ đã được tuyến tính hóa ở giữa, read phải nhìn hiệu ứng write mới hơn theo thứ tự đó.

Quy tắc đúng là **không được quay về một trạng thái cũ hơn thao tác đã hoàn tất trước read**, trừ khi có một thao tác hợp lệ tiếp theo thực sự ghi lại chính giá trị đó.

## 6. Thao tác chồng lấn: có nhiều thứ tự hợp lệ

Giá trị đầu K = 0:

~~~text
Mốc thời gian:  10         20         30         40

Write W:       |----------- write(1) -----------|
Read R:                    |-- read() --|
~~~

Read R **bắt đầu sau W bắt đầu nhưng kết thúc trước W hoàn tất**. Chúng chồng lấn. Có thể chọn:

- **R trước W** → R trả 0.
- **W trước R** → R trả 1.

Cả hai có thể phù hợp linearizability đối với register đơn giản, miễn là **những thao tác khác trong lịch sử** không tạo ra mâu thuẫn.

Thứ tự phản hồi không quyết định toàn bộ thứ tự tuyến tính của hai thao tác chồng lấn. Ví dụ R trả trước W không nhất thiết buộc R được tuyến tính hóa trước W; điểm logic của W vẫn có thể nằm trong khoảng của W trước điểm logic R.

**Không kết luận vi phạm chỉ vì một read chồng lấn với write trả giá trị cũ.** Phải xét cả lịch sử và các ràng buộc thời gian.

## 7. Một lịch sử chồng lấn vẫn có thể không tuyến tính hóa được

Giả sử ban đầu K=0 và chỉ có một write(K,1). Hai read hoàn toàn không chồng lấn nhau:

~~~text
Write W:   |------------------- write(1) -------------------|
Read R1:       |-- read() -> 1 --|
Read R2:                                  |-- read() -> 0 --|
~~~

R1 đã trả **1**, trong khi R2 bắt đầu **sau khi R1 kết thúc** nhưng lại trả **0**. Trong một register với chỉ một write(K,1) và không có thao tác ghi về 0, không có thứ tự tuyến tính nào giải thích được:

1. R1 trả 1 → W phải đứng trước R1 trong thứ tự S.
2. R1 kết thúc trước R2 bắt đầu → R1 phải đứng trước R2 trong S.
3. R2 trả 0 → R2 phải đứng trước W trong S.

Ba điều kiện tạo vòng mâu thuẫn:

\[
W < R1 < R2 < W
\]

Vậy lịch sử **không linearizable**, dù cả R1 và R2 đều diễn ra trong khoảng W chưa hoàn tất.

Từ đây thấy rằng **linearizability không phải xét riêng từng cặp read–write**, mà là tìm **một thứ tự nhất quán cho toàn bộ lịch sử**.

## 8. Phân biệt thứ tự thời gian thực với đồng hồ tường

Trong định nghĩa linearizability, **thời gian thực** chủ yếu là quan hệ:

~~~text
response(A) xảy ra trước invoke(B)
~~~

Không bắt buộc hai server có đồng hồ UTC đồng bộ đến từng microsecond để thực thi một thuật toán linearizable. Nhiều thuật toán dùng **consensus, leader, log index, revision hoặc coordination protocol**, thay vì tin vào giá trị thời gian tường do máy khách gửi.

Các timestamp có thể gây nhầm:

~~~text
Client A clock: 09:00:00.500
Client B clock: 09:00:00.300
~~~

Nếu B có đồng hồ lệch, timestamp B nhỏ hơn A **không chứng minh** thao tác B thực sự xảy ra trước. Cũng không thể đơn giản dùng **last-write-wins theo client timestamp** rồi tuyên bố toàn bộ ghi/read là linearizable.

Đối với kiểm thử, việc ghi thời điểm invoke/response cần đủ thông tin để xác định các khoảng thao tác; tốt nhất đo bằng đồng hồ phù hợp và môi trường kiểm soát, hoặc dùng thứ tự sự kiện đáng tin. Lịch sử phân tán có đồng hồ lệch phải được phân tích thận trọng; không bịa một quan hệ thời gian thực từ timestamp không đáng tin.

## 9. Linearizability là thuộc tính an toàn, không phải cam kết luôn trả lời nhanh

Trong lý thuyết hệ phân tán, linearizability được xem là một **safety property**: nếu hệ trả về những kết quả, chúng không được mâu thuẫn với một thứ tự tuần tự hợp lệ và thời gian thực.

Nó không tự hứa:

- Mọi request đều hoàn tất trong một thời gian hữu hạn.
- Request sẽ được phục vụ ngay khi mạng bị chia cắt.
- Độ trễ p99 luôn nhỏ.
- Database không thể timeout hoặc từ chối ghi.
- Liveness/progress được đảm bảo dưới mọi số node lỗi.

Một hệ có thể **giữ tính đúng bằng cách không trả kết quả cho một số request** khi chưa đủ quorum hoặc chưa xác định leader. Đây là một đánh đổi thực tế giữa tính sẵn sàng và tính nhất quán mạnh trong những điều kiện phân hoạch mạng cụ thể.

**Một request timeout không đồng nghĩa bằng chứng linearizability bị vi phạm**; nhưng cũng không đồng nghĩa request chắc chắn không có hiệu ứng.

## 10. Thao tác chưa hoàn tất và kết quả chưa rõ

Timeline:

~~~text
Client A                  Database
   |---- write(K,1) ------->|
   |                       | có thể đã commit
   |<--- response --X      | mạng làm mất phản hồi
   |
   | timeout
~~~

Trong history của client, thao tác write có **invoke nhưng không có response hoàn tất được quan sát**. Nó có thể đã tác động vào dữ liệu hoặc chưa.

Khi phân tích linearizability, những thao tác đang chờ cần được xử lý theo quy tắc của mô hình: một thao tác pending có thể được hoàn tất trong một phần mở rộng lịch sử hoặc bị bỏ qua khi đánh giá, tùy cách chứng minh. Không được tự động coi mọi request timeout là **write thất bại chắc chắn**.

Trong thiết kế ứng dụng:

1. Dùng **logical operation ID** ổn định (orderId, reservationId, paymentIntentId).
2. Khi outcome là UNKNOWN, đọc/kiểm chứng ở nguồn có thẩm quyền.
3. Nếu retry, dùng thao tác **idempotent** hoặc conditional write để tránh hiệu ứng kép.
4. Phân biệt **request chưa tạo hiệu ứng** với **request đã thành công nhưng mất phản hồi**.
5. Lưu trạng thái chờ hoặc reconciliation nếu không thể xác định ngay.

Đặc biệt đối với **$inc**, **DECRBY** hoặc gửi thanh toán, lặp một thao tác nguyên tử vẫn có thể tạo hiệu ứng nghiệp vụ hai lần.

## 11. Định nghĩa trên một register: đọc, ghi và tuyến tính hóa

Một đối tượng dễ học là **read–write register**:

~~~text
State:
  value = 0

Operations:
  write(v):
    đặt value = v
    trả OK

  read():
    trả value
~~~

Một lịch sử tuần tự hợp lệ:

~~~text
write(1) -> OK
read()   -> 1
write(2) -> OK
read()   -> 2
~~~

Một lịch sử tuần tự không hợp lệ:

~~~text
write(1) -> OK
read()   -> 0       // Không có write(0) xen giữa
~~~

Với lịch sử có thao tác chồng lấn, ta tìm thứ tự tương đương với một lịch sử tuần tự hợp lệ, đồng thời giữ quan hệ **response-before-invocation**.

Đối tượng khác có đặc tả khác:

- **Counter:** increment tạo giá trị tăng theo quy tắc, read trả trạng thái tương ứng.
- **Set:** add/remove/contains có quy tắc phần tử.
- **Queue:** enqueue/dequeue có quy tắc lấy phần tử, trong đó thứ tự và concurrency quan trọng.
- **Lock:** acquire/release có điều kiện sở hữu và fencing.
- **Seat claim:** claim chỉ thành công một lần nếu ghế chưa thuộc người khác.

Không thể kiểm chứng linearizability của một đối tượng chỉ bằng so sánh “giá trị cuối giống nhau”. Phải định nghĩa **các phép toán hợp lệ và phản hồi của chúng**.

## 12. Compare-and-set giúp biến quyết định thành một thao tác

Một nguyên nhân thường gặp của lỗi concurrency là:

~~~text
GET state
IF state == AVAILABLE:
    SET state = HELD
~~~

Hai client có thể cùng GET AVAILABLE, rồi cả hai SET HELD và đều trả “thành công”, mặc dù chỉ có một ghế.

Một thao tác **compare-and-set (CAS)** hoặc conditional update có ngữ nghĩa:

\[
\mathrm{CAS}(K,\ expected,\ newValue)
\]

Chỉ ghi newValue nếu giá trị hiện tại khớp expected, và thông báo chính xác liệu điều kiện đã được áp dụng hay không, trong phạm vi atomicity được engine hỗ trợ.

Ví dụ khái niệm:

~~~text
K = AVAILABLE

Client A: CAS(K, AVAILABLE, HELD_BY_A) -> success
Client B: CAS(K, AVAILABLE, HELD_BY_B) -> false

K cuối:
  HELD_BY_A
~~~

Khi CAS tuyến tính hóa được trên cùng đối tượng, hai request tranh chấp có thể được xếp vào một thứ tự, và **chỉ request đầu tiên thỏa điều kiện được công nhận**. Sau đó client còn cần idempotency để phân biệt retry cùng request với một yêu cầu mới.

**CAS là một cách xây thao tác đúng trên một đối tượng, không phải bằng chứng mọi giao dịch qua nhiều đối tượng tự thành linearizable/strict serializable.**

## 13. Linearizability và các cấp độ nhất quán khác

Các mô hình nhất quán trả lời những câu hỏi khác nhau, nên cần phân biệt ngắn gọn:

| Mô hình/thuộc tính | Điểm chính | Điều không được suy ra |
|---|---|---|
| **Eventual consistency** | Khi ngừng cập nhật và có các điều kiện hội tụ phù hợp, replica cuối cùng đạt trạng thái thống nhất | Read ngay sau write đã hoàn tất luôn thấy giá trị mới |
| **Read-your-writes** | Một session/client thấy các ghi trước của chính mình theo hợp đồng | Client khác ngay sau đó cũng thấy giá trị mới |
| **Monotonic reads** | Session không lùi về phiên bản cũ hơn những gì đã thấy | Mọi session chung một thứ tự thực tuyệt đối |
| **Causal consistency** | Giữ những quan hệ nhân quả thuộc phạm vi bảo đảm | Mọi cặp thao tác không liên quan nhân quả có thứ tự tuyến tính toàn cục |
| **Sequential consistency** | Có thứ tự tuần tự hợp lệ giữ thứ tự chương trình mỗi client | Giữ thứ tự thời gian thực giữa các client |
| **Linearizability** | Có thứ tự tuần tự hợp lệ **và** tôn trọng thứ tự response-before-invocation | Một giao dịch nhiều object là atomic hay serializable chỉ nhờ các object riêng |
| **Serializability** | Những transaction đồng thời tương đương một thứ tự tuần tự các transaction | Thứ tự ấy nhất thiết phù hợp thời gian thực bên ngoài |
| **Strict serializability** | Transaction serializable **và** tôn trọng thứ tự thời gian thực | Giao dịch ở dịch vụ ngoài tự tham gia nếu không có cơ chế |

Đừng chỉ nhìn tên mức đọc như **strong**, **quorum**, **majority**, **snapshot** rồi tự động gán chúng vào bảng. Những tên này có ngữ nghĩa kỹ thuật khác nhau giữa hệ và đôi khi chỉ định một phần của protocol cần dùng.

## 14. Linearizability khác sequential consistency ở đâu?

**Sequential consistency** yêu cầu một lịch sử tương đương với một thứ tự tuần tự **giữ nguyên thứ tự chương trình của mỗi client**. Nó không bắt buộc giữ mọi quan hệ thời gian thực giữa các client.

Ví dụ:

~~~text
Ban đầu K=0.

Client A:
  write(K,1) -> OK
  ... A đã hoàn tất ...

Client B:
  bắt đầu read(K) sau khi A đã nhận OK
  read(K) -> 0
~~~

Nếu hai client không có ràng buộc chương trình chung, một thứ tự tuần tự đặt **read của B trước write của A** vẫn có thể thỏa sequential consistency của riêng hai client. Nhưng nó **không thỏa linearizability**, vì thực tế response(A) xảy ra trước invocation(B).

**Nhớ:** sequential consistency bảo toàn **program order**; linearizability bổ sung **real-time precedence giữa các client**.

Điều này đặc biệt có ý nghĩa khi hai người dùng liên hệ **ngoài database**: A nhắn cho B “tôi đã đặt vé thành công”, rồi B mở trang đọc trạng thái. Dù B chưa đọc dữ liệu A đã đọc, hoàn tất của A xảy ra trước lần đọc B theo thời gian thực. Một lời hứa linearizability phải xét quan hệ đó.

## 15. Linearizability khác serializability ở đâu?

**Serializability** là thuộc tính thường áp dụng cho **transaction**. Nó đòi kết quả tương đương một thứ tự transaction tuần tự hợp lệ.

Giả sử hai transaction không chồng lấn:

~~~text
T1: tăng giá trị K từ 0 thành 1 -> COMMIT

Sau khi T1 hoàn tất:

T2: đọc K -> 0 -> COMMIT
~~~

Một cách giải thích đặt T2 trước T1 có thể vẫn phù hợp **serializability thuần túy** nếu không có ràng buộc thời gian thực bổ sung, nhưng không phù hợp **strict serializability**, vì T1 đã kết thúc trước khi T2 bắt đầu.

Trong khi đó, **linearizability** thường được phát biểu về các **operation riêng** trên một hoặc nhiều đối tượng; **strict serializability** kết hợp tư duy tuyến tính hóa với **transaction nhiều thao tác**.

| Khái niệm | Đơn vị được sắp thứ tự | Cần real-time order? |
|---|---|---|
| Linearizability | Thao tác trên đối tượng theo ngữ nghĩa công bố | Có, cho thao tác không chồng lấn |
| Serializability | Transaction | Không phải mặc định |
| Strict serializability | Transaction | Có |

Một database có thể có **atomic single-document operations** mà không tự có một transaction **strict serializable trên nhiều document**. Cần kiểm tra giới hạn isolation và transaction cụ thể.

## 16. Các đối tượng riêng linearizable không tự bảo vệ bất biến xuyên đối tượng

Giả sử **A** và **B** là hai key độc lập, mỗi key có CAS linearizable:

~~~text
A = 0
B = 0

Quy tắc nghiệp vụ:
  A + B <= 1
~~~

Hai request:

~~~text
Request X:
  read B -> 0
  CAS(A, 0, 1) -> success

Request Y:
  read A -> 0
  CAS(B, 0, 1) -> success
~~~

Nếu các lần đọc diễn ra trước khi các CAS của request còn lại có hiệu lực, cả hai request có thể cập nhật key riêng thành công:

~~~text
A = 1
B = 1
~~~

Mỗi **đối tượng riêng** vẫn có thể linearizable, nhưng invariant **A+B<=1** bị vi phạm vì ứng dụng thực hiện một quyết định **nhiều key** qua nhiều operation không được phối hợp trong một transaction.

Điều này không mâu thuẫn với tính **compositional/locality** của linearizability: các đối tượng riêng có lịch sử tuyến tính hóa được thì có thể tổ hợp thành lịch sử tuyến tính hóa được cho **những thao tác riêng lẻ**. Nó **không biến nhiều thao tác ứng dụng thành một operation nguyên tử có precondition xuyên đối tượng**.

Để bảo vệ invariant, có thể:

- Gom điều kiện và cập nhật vào **một item/document** phù hợp nếu quy mô cho phép.
- Dùng transaction có isolation/kiểm tra điều kiện thích hợp.
- Dùng một **đối tượng quota/claim trung tâm** với CAS.
- Dùng reservation workflow có trạng thái và đối soát nếu không có transaction xuyên hệ.

## 17. Linearizable register không tự ngăn ghi đè bởi client cũ

Một trường hợp dễ nhầm:

~~~text
K = {stock: 10, version: 5}

A đọc version 5.
B đọc version 5.

A ghi stock = 9, version = 6.
B ghi stock = 8, version = 6 bằng SET không điều kiện.
~~~

Hai lần SET có thể được xếp theo một thứ tự tuyến tính hợp lệ và thao tác của B vẫn có thể ghi đè A. **Linearizability không tự quyết định giá trị của B có hợp lệ về nghiệp vụ hay không.**

Muốn ngăn stale writer, phải dùng CAS:

~~~text
A: CAS(version 5 -> 6, stock 9) -> success
B: CAS(version 5 -> 6, stock 8) -> false
~~~

Tương tự, một khóa giữ lease đã hết hạn không đủ ngăn worker cũ vẫn gửi ghi nếu đích không kiểm tra **fencing token** hoặc version. Linearizability là nền tảng để thực thi CAS đúng; **logic nghiệp vụ vẫn phải đặt điều kiện đúng**.

## 18. Linearizability có liên hệ gì với read-your-writes?

Trong một đối tượng linearizable:

~~~text
Client A:
  write(K,1) -> OK
  read(K)    -> ?
~~~

Nếu read bắt đầu sau write hoàn tất và không có write khác chen giữa, read phải trả 1. Đó là một hệ quả tương tự **read-your-writes**.

Nhưng yêu cầu linearizability còn mạnh hơn:

~~~text
Client A:
  write(K,1) -> OK

Client B:
  bắt đầu read(K) sau response OK của A
~~~

Client B cũng phải nhìn thấy ít nhất hiệu ứng ghi đã hoàn tất của A theo thứ tự hợp lệ, không chỉ riêng session A.

**Read-your-writes** theo session có thể đạt được bằng stickiness, session token hoặc cơ chế causal/session consistency mà các client khác vẫn đọc stale. Vì vậy không thể chứng minh hệ linearizable chỉ bằng test “một user tự ghi rồi tự đọc”.

## 19. Đọc từ replica: nguy cơ stale read sau khi write đã ACK

Một kiến trúc thường gặp:

~~~mermaid
flowchart LR
    W["Client A ghi K=1"] --> L["Leader/Primary"]
    L --> R1["Replica 1 đã nhận K=1"]
    L -.-> R2["Replica 2 đang trễ, K=0"]
    B["Client B đọc K"] --> R2
~~~

Giả sử A đã nhận **write OK**, rồi B mới bắt đầu read. Nếu B đọc replica R2 còn giữ K=0, hệ có thể vi phạm lời hứa linearizability trên đối tượng K.

Đây là lý do cần phân biệt:

- **Leader acknowledged** so với **durable/replicated acknowledgement**.
- Đọc từ primary/leader so với đọc từ follower có thể trễ.
- Đọc **strongly consistent/linearizable** so với **eventual/stale**.
- Replica đã có giá trị mới nhưng chưa chắc biết mình có đủ quyền trả lời read theo thứ tự hợp lệ khi leader đổi.

Không phải cứ **đọc từ leader** là bảo đảm tuyệt đối trong mọi tình huống. Thuật toán còn cần xử lý **quyền lãnh đạo, epoch/term, quorum, failover và các ghi chưa hoàn tất**.

## 20. Quorum không phải một câu thần chú bảo đảm linearizability

Một công thức thường được nhắc trong replication:

\[
R + W > N
\]

trong đó **N** là số replica, **W** số replica tham gia xác nhận ghi, **R** số replica tham gia đọc. Nếu cả hai tập quorum giao nhau, về lý thuyết có cơ sở để read tiếp xúc với ít nhất một replica đã liên quan đến write.

Nhưng **giao nhau** chỉ là một thành phần của thuật toán, **không tự chứng minh toàn bộ hệ linearizable**.

Còn những câu hỏi:

1. Replica nào được chọn, và đọc giá trị nào khi các replica trả version khác nhau?
2. Một write đang dang dở có thể đã tới một số replica trước khi client timeout không?
3. Một read có thể thấy giá trị của write chưa hoàn tất và read sau đó lại thấy cũ không?
4. Có cơ chế **read repair/write-back, fencing, epoch hoặc protocol** để bảo đảm thứ tự nhất quán không?
5. Hai write cạnh tranh được xếp thứ tự ra sao?
6. Khi failover, dữ liệu đã ACK có còn được commit/duy trì theo quy tắc?
7. Mức consistency được áp dụng cho **cả đường đọc lẫn đường ghi** hay chỉ một phía?

Với hệ leader-based, consensus và giao thức quorum, cách bảo vệ khác nhau. Không nên suy rằng **QUORUM read + QUORUM write** của bất kỳ NoSQL nào tự tương đương với một thao tác tuyến tính hóa được.

Đặc biệt, **read repair** xảy ra sau khi phát hiện stale không tự sửa việc client đã nhận một giá trị cũ trái cam kết trong chính request ấy.

## 21. Leader, consensus và việc chọn một thứ tự hợp lệ

Những hệ dùng consensus (như Raft hoặc Paxos theo thiết kế cụ thể) thường cố gắng có một **log/thứ tự quyết định chung** cho các thao tác được cam kết:

~~~text
Client A write(K,1)
        |
        v
Leader đề xuất log entry
        |
        v
Quorum tham gia commit theo protocol
        |
        v
Write được ACK theo chính sách
~~~

Đối với linearizable read, chỉ nhìn **state trong bộ nhớ của leader** đôi khi chưa đủ. Leader phải biết mình còn hợp lệ hoặc có cơ chế bảo đảm read không bỏ qua commit từ một leader mới. Các thuật toán dùng **read index, lease có điều kiện đúng, quorum confirmation** hoặc cách khác tùy hệ.

Sau network partition:

- Phía thiếu quorum có thể không được phép quyết định ghi mới hoặc trả những read được công bố là linearizable.
- Một node cũ vẫn tưởng mình là leader không được tạo ra những xác nhận mâu thuẫn với leader mới.
- Retry sau khi leader đổi phải xử lý ID operation và dữ liệu đã commit.

**Consensus** là một công cụ xây thứ tự, không có nghĩa mọi endpoint và mọi loại read của sản phẩm dùng consensus đều linearizable theo mặc định. Cần kiểm tra mode đọc, dữ liệu đi qua cache và phạm vi đối tượng được bảo vệ.

## 22. MongoDB: read concern linearizable và write concern

MongoDB có nhiều read concerns và write concerns. Khi cần lời hứa tuyến tính hóa cho thao tác đọc thích hợp trên **một document**, MongoDB cung cấp **readConcern: "linearizable"** trong các điều kiện/giới hạn được tài liệu phiên bản hỗ trợ. Nó cần được hiểu cùng **write concern**, topology và cách định tuyến read.

Ví dụ trong **mongosh** trên deployment phù hợp:

~~~javascript
// Ghi trạng thái có điều kiện lên một document.
// Majority acknowledgement nhằm bảo vệ tính bền vững
// theo chính sách replica set.
const update = db.seats.updateOne(
  {
    _id: "show-07:A12",
    state: "AVAILABLE"
  },
  {
    $set: {
      state: "HELD",
      heldBy: "reservation-9001"
    }
  },
  {
    writeConcern: { w: "majority" }
  }
);

printjson(update);
~~~

Để đọc trên primary với linearizable read concern khi API/phiên bản hỗ trợ:

~~~javascript
db.runCommand({
  find: "seats",
  filter: { _id: "show-07:A12" },
  readConcern: { level: "linearizable" },
  maxTimeMS: 5000
});
~~~

Các điểm cần hiểu:

- **Một updateOne** trên một document được áp dụng nguyên tử theo phạm vi document, nhưng không tự tạo transaction nhiều document.
- **writeConcern majority** và **readConcern linearizable** có vai trò khác nhau: ACK của ghi và bảo đảm đọc theo thời gian thực trong điều kiện phù hợp.
- Linearizable reads có **giới hạn về loại thao tác, topology và phiên bản**; phải xem tài liệu sản phẩm thay vì gán cho mọi aggregation, mọi secondary read hoặc multi-document transaction.
- Read từ một **secondary replica eventual** không tự có bảo đảm linearizable chỉ vì lần ghi trước đã ACK.
- Khi node không thể xác nhận trạng thái/khả năng trả lời, linearizable read có thể **chờ hoặc timeout**. Đặt giới hạn thời gian thích hợp để không treo request vô hạn.
- **Read concern "majority"** không đơn giản đồng nghĩa **read concern "linearizable"**; chúng có mục đích/đảm bảo khác nhau.

Nếu nghiệp vụ là “chỉ một người giữ ghế”, **conditional update** chính là chốt bảo vệ quan trọng. Không nên dùng một lần **findOne** rồi **updateOne không có điều kiện trạng thái**, dù findOne dùng read concern mạnh.

## 23. DynamoDB: strongly consistent reads và conditional writes

DynamoDB hỗ trợ lựa chọn **strongly consistent reads** đối với những thao tác đọc trên base table hoặc local secondary index theo phạm vi sản phẩm, trong khi **Global Secondary Index (GSI)** có cơ chế **eventually consistent reads**.

Ví dụ một item:

~~~text
Table: Seats
PK = "SHOW#07#SEAT#A12"
state = "AVAILABLE"
version = 3
~~~

Ghi có điều kiện:

~~~text
UpdateItem
Key:
  PK = "SHOW#07#SEAT#A12"

ConditionExpression:
  #state = :available AND #version = :expected

UpdateExpression:
  SET #state = :held, #version = :newVersion

ExpressionAttributeNames:
  #state = "state"
  #version = "version"

ExpressionAttributeValues:
  :available = "AVAILABLE"
  :held = "HELD"
  :expected = 3
  :newVersion = 4
~~~

Đoạn trên mô tả **ý nghĩa API**; lời gọi SDK thật cần typed AttributeValue, xử lý lỗi điều kiện và thông tin tenant/owner.

Đường đọc cần giá trị mới nhất:

~~~text
GetItem
Key: PK = "SHOW#07#SEAT#A12"
ConsistentRead: true
~~~

Trong phạm vi được hỗ trợ, strongly consistent read cung cấp ngữ nghĩa đọc trạng thái mới nhất phù hợp cam kết của DynamoDB, còn conditional write giúp chặn hai client cùng claim thành công.

Các giới hạn cần phân biệt:

- **GSI không hỗ trợ strong consistent reads** theo ngữ nghĩa thông thường của DynamoDB; query từ GSI có thể trễ so với base table.
- Strongly consistent **GetItem** cho từng item không làm một chuỗi hai GetItem trở thành snapshot transaction nhiều item.
- **TransactWriteItems/TransactGetItems** có những bảo đảm và giới hạn riêng đối với nhiều item; phải dùng đúng API.
- Với kiến trúc **đa Region**, mô hình replication/conflict resolution và những chế độ toàn cục cụ thể có thể khác. Không tự suy tính tuyến tính toàn cầu từ strong read trong một Region.
- Cache, DAX hoặc read model do ứng dụng duy trì có hợp đồng khác và có thể trả stale.

Nếu một API dùng GSI để hiển thị ghế AVAILABLE rồi gửi conditional update trên **base item**, kết quả hiển thị có thể trễ, nhưng **quyết định chốt ghế** vẫn phải dựa trên điều kiện nguyên tử ở item nguồn. UI stale không được coi là bằng chứng ghế còn giữ được.

## 24. Cassandra: QUORUM và LWT không phải cùng một lời hứa

Apache Cassandra cho phép cấu hình consistency level đối với các thao tác đọc/ghi thông thường, chẳng hạn ONE, QUORUM hoặc LOCAL_QUORUM. Nhưng các mức quorum thông thường **không tự biến mọi chuỗi read–modify–write thành linearizable CAS**.

Giả sử hai người cùng giữ ghế. Nếu ứng dụng:

~~~text
SELECT state WHERE show_id='show-07' AND seat_id='A12'

Nếu AVAILABLE:
  UPDATE state='HELD'
~~~

hai client vẫn có thể cùng thấy AVAILABLE trước khi một bên ghi. Dù SELECT/UPDATE sử dụng một consistency level mạnh hơn, việc **đọc rồi ghi tách rời** không trở thành một thao tác CAS duy nhất.

Với **lightweight transactions (LWT)**, Cassandra dùng cơ chế đồng thuận cho điều kiện ghi:

~~~sql
CREATE TABLE seat_claims (
    show_id text,
    seat_id text,
    state text,
    reservation_id text,
    PRIMARY KEY ((show_id), seat_id)
);

-- Giả sử row đã được khởi tạo với state='AVAILABLE'.
UPDATE seat_claims
SET state = 'HELD',
    reservation_id = 'res-9001'
WHERE show_id = 'show-07'
  AND seat_id = 'A12'
IF state = 'AVAILABLE';
~~~

Ứng dụng phải kiểm tra **[applied]** và xử lý trường hợp false. LWT được thiết kế để hỗ trợ conditional compare-and-set/linearizable consistency theo ranh giới/điều kiện Cassandra công bố, nhưng có **chi phí phối hợp và tranh chấp**. Cần xem consistency level SERIAL/LOCAL_SERIAL cùng read/write consistency và cấu hình thực tế.

**Không kết luận mọi CQL BATCH hay mọi partition read đều tuyến tính hóa được chỉ vì cùng partition key.** BATCH, LWT, ordinary writes và read repair là các cơ chế khác nhau với phạm vi bảo đảm riêng.

## 25. Redis: nguyên tử của command và giới hạn của failover

Trên một Redis server chịu trách nhiệm thực thi các lệnh cho key, một command như **SET**, **INCR** hoặc **DECRBY** có ngữ nghĩa thực thi nguyên tử đối với dữ liệu Redis theo cơ chế của nó.

~~~redis
SET counter:orders 0
INCR counter:orders
GET counter:orders
~~~

Trong một chuỗi command được thực thi tuần tự trên cùng instance, kết quả có thể được giải thích bằng một thứ tự các command. Nhưng khi hệ có **replication bất đồng bộ, failover, persistence policy, Redis Cluster hoặc client đọc từ replica**, phải kiểm tra phạm vi lời hứa:

- Lệnh ghi được primary ACK có thể chưa tới replica khi replica trả read.
- Failover theo topology/configuration có thể ảnh hưởng việc một ghi đã ACK còn tồn tại sau leader switch.
- Một script hoặc MULTI/EXEC bảo vệ việc không chen lệnh trong phạm vi Redis hỗ trợ, nhưng **không có rollback kiểu SQL** nếu một lệnh nội bộ gặp runtime error.
- Một Lua script tính toán tốt vẫn cần ID operation để tránh **$inc-like double effect** khi retry.
- Redis Cluster hạn chế thao tác nhiều key trên các hash slot khác nhau.
- TTL/expiration thay đổi trạng thái key theo cơ chế riêng, phải đưa vào đặc tả nếu kiểm tra linearizability của key có thời hạn.

Vì vậy, phát biểu chính xác là **“thao tác đơn trên một instance Redis có ngữ nghĩa nguyên tử/thứ tự xử lý phù hợp, nhưng không được suy ra bảo đảm linearizable bền vững xuyên mọi failover/replica”**.

Nếu ứng dụng cần quyết định quyền sở hữu không được mất sau failover, cần đánh giá kỹ **durability, replication acknowledgement, fencing và nguồn thẩm quyền**, thay vì chỉ dựa vào việc SET NX đã trả OK.

## 26. etcd: ví dụ về một kho key–value dùng consensus

**etcd** thường được dùng cho metadata, service coordination và trạng thái có quy mô nhỏ nhưng yêu cầu tính nhất quán mạnh. Nó dùng cơ chế consensus để thống nhất revision của key–value operations.

Các API đọc của etcd có thể có chế độ **linearizable** và **serializable** theo hợp đồng của sản phẩm. Đọc linearizable đảm bảo không trả giá trị cũ trái thứ tự thực trong phạm vi đã cam kết; đọc serializable có thể nhanh hơn ở một số đường đi nhưng có thể trả dữ liệu cũ.

Ví dụ logic:

~~~text
Key:
  /locks/order-9001

Transaction:
  Compare createRevision(key) == 0
  If true:
    Put key = worker-17
  Else:
    thất bại / kiểm tra owner hiện tại
~~~

Ở đây, **revision và compare-then-put trong cùng Txn** giúp bảo vệ một claim theo điều kiện. Nhưng tạo một lock key chưa đủ bảo vệ mọi side effect bên ngoài:

- Nếu lease hết hạn rồi worker cũ vẫn tiếp tục, đích cần **fencing token** hoặc kiểm soát version.
- Một thao tác thanh toán ở provider không tự tham gia transaction etcd.
- Watch stream có đặc tả event/revision riêng; không nên xem callback watch là một linearizable read của mọi dữ liệu liên quan.
- Các thao tác có nhiều key phải nằm trong giới hạn transaction và namespace/protocol phù hợp.

**Không dùng một kho coordination làm kho dữ liệu kinh doanh khổng lồ chỉ vì nó có cơ chế consensus.** Chi phí quorum, kích thước dữ liệu và write throughput phải phù hợp workload.

## 27. Bảng đối chiếu: hỏi đúng phạm vi trước khi gọi một hệ là “mạnh”

| Hệ | Cơ chế liên quan | Lời hứa cần kiểm tra trong triển khai |
|---|---|---|
| **MongoDB** | Atomic document update, majority writes, linearizable read concern | Đọc một document trên primary, topology, write concern, timeout, phạm vi transaction |
| **DynamoDB** | Strongly consistent base table/LSI reads, conditional writes, transactions | Một item hay nhiều item; GSI eventual; đa Region/cache |
| **Cassandra** | Ordinary consistency levels, LWT/Paxos, SERIAL/LOCAL_SERIAL | Conditional write trong phạm vi nào; ordinary QUORUM không tự thay LWT |
| **Redis** | Single-command execution, Lua/MULTI, replication/persistence | Single instance vs replicas/failover; script nhiều key; TTL |
| **etcd** | Consensus revision, linearizable read, Txn/CAS, leases | Mode đọc, quorum, fencing, watch semantics, hiệu ứng ngoài etcd |
| **Ứng dụng dùng nhiều NoSQL** | Local transaction + event/outbox/saga | Không có global linearizability/strict serializability tự phát qua các dịch vụ |

Một ứng dụng dùng nhiều database vẫn có thể xây bất biến mạnh theo thiết kế phù hợp, nhưng **không được cộng những guarantee cục bộ rồi xem thành transaction xuyên hệ**.

## 28. Linearizability và network partition: vì sao có khi phải từ chối đọc?

Giả sử cluster có leader L và hai follower F1, F2. Mạng bị phân đôi:

~~~text
Nhóm A:
  L (một mình, không liên hệ được quorum)

Nhóm B:
  F1 + F2 (có thể bầu leader theo protocol)
~~~

Nếu L vẫn chấp nhận **write OK linearizable** cho một client, đồng thời nhóm B bầu leader mới và xác nhận những ghi khác trên cùng key, hai phía có nguy cơ tạo hai lịch sử mâu thuẫn.

Hệ thống có cơ chế consensus phù hợp sẽ phải hạn chế khả năng commit hoặc trả lời những thao tác đòi linearizability ở phía không đủ điều kiện. Một request có thể **timeout/không sẵn sàng** thay vì trả dữ liệu không có căn cứ.

~~~mermaid
flowchart TD
    A["Client yêu cầu read/write mạnh"] --> B{"Node có bằng chứng đủ theo protocol?"}
    B -->|"Có"| C["Đọc/commit và trả kết quả hợp lệ"]
    B -->|"Không"| D["Chờ, chuyển tuyến hoặc báo unavailable/timeout"]
    D --> E["Không khẳng định kết quả cũ là linearizable"]
~~~

Điều đó **không có nghĩa hệ CP luôn ngừng mọi hoạt động khi mạng lỗi**, hoặc AP luôn trả kết quả sai. Các API/mode có thể cho phép stale reads để tăng tính sẵn sàng nếu người dùng chấp nhận. Cần công bố rõ endpoint nào là **strong** và endpoint nào là **eventual**.

## 29. Đánh đổi về độ trễ và khả năng phục vụ

Đọc mạnh theo thời gian thực có thể cần:

- Liên hệ leader/quorum hoặc xác nhận quyền của leader.
- Chờ apply các log entries cần thiết.
- Chờ một transaction/conditional operation đang tranh chấp.
- Từ chối trả stale data khi không thể xác minh thứ tự.

Vì vậy, có những workload phù hợp với linearizability:

| Workload | Giá trị của linearizability | Đánh đổi ứng viên |
|---|---|---|
| Giành một ghế duy nhất | Rất cao cho thao tác claim | Chấp nhận conflict/timeout khi tranh chấp |
| Trừ stock có điều kiện | Cao ở nguồn stock | Chi phí hot item/conditional write |
| Cấp quyền sở hữu/lease | Cao cho quyết định quyền, kèm fencing | Cần consensus/coordination |
| Hiển thị số lượt xem | Thường không cần trên mọi read | Counter có thể được cập nhật bất đồng bộ |
| Dashboard doanh thu mỗi phút | Có thể chấp nhận độ trễ đã công bố | Read model eventual, dễ mở rộng hơn |
| Gợi ý sản phẩm | Thường không cần thứ tự thực của mọi update | Cache/index/search có độ trễ |
| Xác nhận thanh toán | Cần nguồn trạng thái có thẩm quyền và idempotency | Phải đối soát provider; không có transaction toàn cục |

Đừng chọn consistency mode bằng cảm tính “mạnh nhất luôn tốt nhất”. Chọn theo **bất biến**, **rủi ro đọc stale** và **độ trễ/availability SLO** của từng thao tác.

## 30. Một API có thể có hai lời hứa nhất quán khác nhau

Ví dụ bán vé:

~~~text
GET /shows/07/seats
  dùng cache/read model
  trạng thái có thể trễ tối đa theo SLO

POST /shows/07/seats/A12/claim
  dùng conditional write tại nguồn
  chỉ một claim hợp lệ thành công

GET /reservations/res-9001/authoritative-status
  dùng đường đọc mạnh theo hợp đồng
~~~

Một màn hình hiển thị **AVAILABLE** khi ghế đã được giữ có thể là độ trễ UI được chấp nhận nếu sản phẩm công bố như vậy. Nhưng **POST claim** phải từ chối request thứ hai khi ghế không còn hợp lệ. Không được dùng dữ liệu cache làm quyết định cuối cùng.

Đây là cách thiết kế phổ biến: **read model nhanh và có thể stale**, nhưng **quyết định nghiệp vụ bắt buộc nhất quán mạnh ở nguồn có thẩm quyền**.

Cần phân biệt “toàn ứng dụng linearizable” với “một API claim được bảo vệ bằng conditional write tuyến tính trên item nguồn”. Phát biểu thứ hai thường thực tế và kiểm chứng được hơn.

## 31. Một lịch sử không thể xác định chỉ từ giá trị cuối

Hai hệ đều có K cuối = 2:

**Hệ A:**

~~~text
write(K,1) -> OK
read(K)    -> 1
write(K,2) -> OK
read(K)    -> 2
~~~

**Hệ B:**

~~~text
write(K,1) -> OK
read(K)    -> 0
write(K,2) -> OK
read(K)    -> 2
~~~

Không có write trả lại 0 trong ví dụ. Giá trị cuối giống nhau nhưng **Hệ B vi phạm linearizability** nếu read(K)->0 bắt đầu sau response của write(K,1).

Vì vậy, kiểm thử chỉ đọc database ở cuối rồi so final state **không đủ**. Phải ghi nhận **invocation/response, return values, lỗi và kết quả chưa rõ** của từng thao tác.

## 32. Cách kiểm tra một lịch sử ngắn bằng tay

Giả sử register K ban đầu 0:

| Operation | Invoke | Response | Kết quả |
|---|---:|---:|---|
| W1 | 1 | 4 | write(1) OK |
| R1 | 2 | 3 | read() → 0 |
| W2 | 5 | 7 | write(2) OK |
| R2 | 8 | 9 | read() → 2 |

Có thể chọn thứ tự:

~~~text
R1 -> W1 -> W2 -> R2
~~~

**R1 và W1 chồng lấn**, nên R1 có thể đứng trước W1. W1 hoàn tất trước W2 bắt đầu, và W2 hoàn tất trước R2 bắt đầu. Thứ tự trên hợp lệ → lịch sử có thể linearizable.

Thay R2 trả **1**:

| Operation | Invoke | Response | Kết quả |
|---|---:|---:|---|
| R2 | 8 | 9 | read() → 1 |

W2 đã hoàn tất ở mốc 7, trước khi R2 bắt đầu ở mốc 8; không có write mới đưa K về 1. R2 không thể đứng trước W2 → **không linearizable**.

### Quy trình kiểm tra bằng tay

1. Xác định giá trị khởi tạo và **đặc tả tuần tự** của đối tượng.
2. Liệt kê mọi invocation, response, lỗi và pending operation.
3. Vẽ cạnh **A → B** nếu response(A) trước invoke(B).
4. Thêm những ràng buộc từ giá trị đọc/trả về và điều kiện thao tác.
5. Tìm một thứ tự tuần tự **không vi phạm các cạnh** và hợp lệ theo đặc tả.
6. Nếu tồn tại, history này **có thể linearizable**; nếu không tồn tại, history **vi phạm**.
7. Với pending/unknown, chỉ đưa ra kết luận có căn cứ theo mô hình kiểm tra, không gán tùy tiện thất bại.

Với lịch sử nhiều nghìn thao tác chồng lấn, tìm thứ tự hợp lệ có thể khó về tính toán. Cần công cụ kiểm thử và các kỹ thuật thu hẹp mô hình, thay vì thử xếp thủ công.

## 33. Kiểm thử linearizability trong hệ phân tán

Một test thực tế cần **tạo concurrency và failure**, không chỉ gọi tuần tự:

~~~text
Client A: CAS key từ 0 -> 1
Client B: CAS key từ 0 -> 2
Client C: read key
Client D: read key
Client E: update/read ở thời điểm khác
~~~

Trong quá trình test:

- Ghi **thời điểm bắt đầu/kết thúc** của từng operation.
- Ghi **clientId, operationId, key, arguments, response/value**.
- Phân biệt **OK**, **condition failed**, **definite error** và **unknown timeout**.
- Chạy nhiều client cạnh tranh trên cùng key để kiểm tra conflict.
- Chủ động tạo network delay, partition, leader restart hoặc failover trong môi trường kiểm soát.
- Kiểm tra cả **reads sau ACK**, **reads chồng lấn** và **request timeout**.
- Không bỏ các lỗi/timeout khó xử lý khỏi history theo cách làm sai lệch kết luận.
- Đối chiếu history với **mô hình tuần tự** của register, set hoặc queue.

Các công cụ và phương pháp kiểm thử hệ phân tán theo kiểu **Jepsen/Knossos** thường nhấn mạnh việc ghi nhận một **history** rồi chạy checker để xem có thể tuyến tính hóa hay không. Tên công cụ không tự bảo đảm phép đo đúng; đặc tả, cấu hình test và nguồn thời gian/operation phải được kiểm soát.

### Mẫu một operation log

~~~json
{
  "clientId": "client-B",
  "operationId": "op-203",
  "object": "seat:show-07:A12",
  "operation": "read",
  "invokedAtMonotonicNs": 1000000000,
  "respondedAtMonotonicNs": 1200000000,
  "outcome": "OK",
  "value": "HELD"
}
~~~

Đây là schema log minh họa. Trong hệ nhiều máy, những giá trị monotonic clock trên máy khác nhau **không thể so sánh trực tiếp tuyệt đối** nếu không có cơ chế đồng bộ hoặc quan hệ sự kiện đáng tin. Test harness cần phương pháp ghi history cho phép suy luận quan hệ thời gian đúng, thay vì đơn giản ghép timestamp từ các đồng hồ không chung gốc.

## 34. Những kịch bản lỗi cần kiểm tra

| Kịch bản | Điều quan trọng cần quan sát |
|---|---|
| Read ngay sau write ACK trên cùng key | Không trả stale state trái real-time order |
| Hai CAS tranh chấp | Không cùng thành công khi chỉ một claim được phép |
| Write timeout nhưng thực tế đã commit | Retry/verification không tạo hiệu ứng thứ hai |
| Read từ replica đang lag | API có công bố stale read hay đang hứa linearizable? |
| Leader chết sau commit | Ghi ACK trước đó có còn được phản ánh theo hợp đồng durability/consistency? |
| Network partition | Có node nào trả kết quả mạnh không đủ bằng chứng không? |
| Leader cũ tiếp tục hoạt động | Fencing/epoch có chặn stale writer không? |
| Hai read liên tiếp sau một write | Không lùi về giá trị cũ nếu không có write hợp lệ xen giữa |
| Nhiều key cùng một nghiệp vụ | Có transaction/invariant riêng hay chỉ từng key atomic? |
| Cache bị stale | API hiển thị và API quyết định nghiệp vụ có phân biệt không? |
| TTL làm key biến mất | Đặc tả đối tượng có bao gồm expiration như một transition không? |
| Event replay/out-of-order | Version/CAS có chặn trạng thái cũ ghi đè mới không? |

Trong thử nghiệm, một lỗi **“không trả response vì mất quorum”** có thể là hành vi giữ an toàn, trong khi một lần read trả stale data **với lời hứa strong** mới là điều cần điều tra.

## 35. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “Linearizability nghĩa là mọi thao tác thực thi tuần tự, không overlap” | Các thao tác thật có thể overlap | Chỉ yêu cầu tồn tại một thứ tự tuyến tính hợp lệ |
| “Ai gọi trước thì phải tuyến tính hóa trước” | Hai thao tác có thể overlap | Chỉ bắt buộc response-before-invocation giữa thao tác không chồng lấn |
| “Read overlap trả giá trị cũ là vi phạm” | Read có thể tuyến tính hóa trước write | Xét toàn lịch sử và thứ tự hợp lệ |
| “Write ACK rồi read mới bắt đầu trả cũ vẫn được” | Trái real-time order nếu không có write hợp lệ khác | Read mạnh phải phản ánh write đã hoàn tất |
| “Linearizability cần đồng hồ UTC tuyệt đối chính xác” | Thứ tự được xác định bằng thao tác và protocol | Dùng quorum/consensus/epoch theo thuật toán |
| “QUORUM + QUORUM luôn linearizable” | Quorum intersection chưa đủ | Xem toàn bộ protocol read/write/failover |
| “Read-your-writes chứng minh linearizable” | Chỉ có thể là session guarantee | Cần tôn trọng cả client khác |
| “Sequential consistency giống linearizability” | Không bắt buộc cross-client real-time order | Phân biệt program order và real-time precedence |
| “Serializability mặc định giữ thời gian thực” | Không nhất thiết | Strict serializability mới thêm ràng buộc ấy |
| “Một key linearizable thì hai key cập nhật cùng nguyên tử” | Hai operation không phải một transaction | Dùng transaction/coordination cho invariant nhiều key |
| “Atomic SET ngăn lost update” | Read–modify–write có thể ghi snapshot cũ | CAS/conditional update |
| “Strong read trên GSI DynamoDB” | GSI có mô hình eventual read | Đọc base table/LSI theo API được hỗ trợ |
| “MongoDB majority read là linearizable read” | Hai read concerns có ngữ nghĩa khác | Chọn đúng read concern và điều kiện |
| “Redis primary ACK đảm bảo mọi replica/failover thấy ngay” | Replication và persistence có giới hạn | Đánh giá topology và durability |
| “Timeout là write không xảy ra” | Response có thể mất sau commit | UNKNOWN, stable ID, verification |
| “Có consensus thì mọi endpoint là linearizable” | Có thể tồn tại stale-read modes, cache, watch | Kiểm tra mode từng API |
| “Một test cuối cùng đúng là đủ” | Không phát hiện read cũ giữa quá trình | Ghi invoke/response và kiểm tra history |
| “Một read mạnh là snapshot nhiều read” | Các thao tác khác có thể diễn ra giữa những read | Cần transaction/snapshot nếu nghiệp vụ yêu cầu |

## 36. Quy trình quyết định có cần linearizability hay không

~~~mermaid
flowchart TD
    A["Xác định thao tác nghiệp vụ"] --> B["Bất biến nào cần giữ?"]
    B --> C{"Nếu đọc stale sau ACK có gây sai không?"}
    C -->|"Không, có SLO độ trễ rõ"| D["Đọc eventual/session/causal theo hợp đồng"]
    C -->|"Có"| E["Xác định key/object nguồn thẩm quyền"]
    E --> F{"Quyết định nằm trong một object?"}
    F -->|"Có"| G["Conditional write/CAS + read mode phù hợp"]
    F -->|"Không"| H["Transaction/isolation hoặc coordination xuyên object"]
    G --> I["Xem replica, failover, quorum, durability"]
    H --> I
    D --> J["Đặt SLO stale và reconciliation"]
    I --> K["Test histories, overlap, failover, UNKNOWN"]
    J --> K
    K --> L["Đo latency, conflict, unavailability và correctness"]
~~~

### Các bước dùng được trong dự án

1. **Viết thao tác cụ thể:** read, write, CAS, acquire, release, reserve, confirm.
2. **Xác định phạm vi đối tượng:** một key/item/document hay nhiều thực thể.
3. **Viết một lịch sử sai không được phép:** ví dụ write HELD ACK rồi read AVAILABLE mới bắt đầu.
4. **Định nghĩa đặc tả tuần tự** và response nào biểu thị thành công.
5. **Chọn nguồn có thẩm quyền:** không dùng cache làm bằng chứng quyết định.
6. **Chọn write primitive:** atomic/conditional write, unique constraint, CAS, transaction, fencing.
7. **Chọn read mode:** linearizable/strong theo API thực tế nếu cần, eventual/session nếu chấp nhận stale.
8. **Xác định durability, failure và timeout:** failover có thể làm mất ACK không, request UNKNOWN xử lý thế nào.
9. **Thiết kế retry/idempotency:** không áp dụng cùng hiệu ứng hai lần.
10. **Kiểm thử history thực tế:** nonoverlap, overlap, failover, partition, read từ nhiều node.
11. **Đo SLO:** p95/p99, số conflict/timeout/unavailable và độ trễ replica.
12. **Công bố hợp đồng API:** endpoint nào quyết định mạnh và endpoint nào có thể trễ.

## 37. Bài tập thực hành

### Bài tập 1 — Lịch sử đơn giản

Register K ban đầu 0:

~~~text
W1 invoke t=1, response t=3: write(1) OK
R1 invoke t=4, response t=5: read() -> 0
~~~

Hỏi history có linearizable không nếu không có write khác? Hãy chỉ ra cạnh thứ tự thực bắt buộc.

### Bài tập 2 — Read chồng lấn

~~~text
K ban đầu 0
W1: invoke 1, response 5, write(1)
R1: invoke 2, response 3, read() -> 0
~~~

Hãy tìm một thứ tự tuần tự hợp lệ. Nếu R1 trả 1 thì có thể tuyến tính hóa không? Giải thích điều gì thay đổi khi thêm một read khác sau R1.

### Bài tập 3 — Hai read tạo mâu thuẫn

~~~text
K ban đầu 0
W1: invoke 1, response 9, write(1)
R1: invoke 2, response 4, read() -> 1
R2: invoke 5, response 7, read() -> 0
~~~

Không có write khác. Hãy chứng minh hoặc bác bỏ linearizability bằng chuỗi quan hệ W1, R1, R2.

### Bài tập 4 — Thời gian thực so với program order

Client A đã nhận OK của write(1) trước khi Client B gọi read() và nhận 0. Hãy giải thích vì sao một history có thể phù hợp **sequential consistency** nhưng không phù hợp **linearizability**.

### Bài tập 5 — Thao tác pending

Client gửi write(K,1) nhưng timeout. Client khác đọc K=1. Có thể kết luận write timeout chắc chắn thất bại không? Hãy thiết kế một cách kiểm chứng theo operationId và nêu cách retry không làm tăng counter hai lần.

### Bài tập 6 — CAS giữ ghế

Hai khách cùng giữ ghế A12 đang AVAILABLE. Hãy mô tả CAS/conditional update nào được dùng, kết quả nào được chấp nhận và điều gì cần xảy ra khi client thua cuộc. Vì sao **GET rồi SET** không đủ?

### Bài tập 7 — Linearizable từng key nhưng sai invariant

Có A=0, B=0 và quy tắc A+B<=1. Hai request đọc key đối diện rồi CAS key riêng từ 0 thành 1. Hãy trình bày một lịch sử mà mỗi key tuyến tính hóa được nhưng invariant vẫn bị vi phạm. Đề xuất cách bảo vệ xuyên key.

### Bài tập 8 — MongoDB

Viết một conditional update giữ ghế trên một document, dùng writeConcern phù hợp. Sau đó viết một find command có readConcern linearizable trong điều kiện hỗ trợ. Hãy giải thích vì sao đọc từ secondary với chế độ eventual có thể không đáp ứng cùng lời hứa.

### Bài tập 9 — DynamoDB

Thiết kế item **Seats** với PK theo showId/seatId và ConditionExpression state=AVAILABLE. Mô tả GetItem ConsistentRead=true. Vì sao Query GSI theo status không được dùng làm bằng chứng cuối để quyết định claim?

### Bài tập 10 — Cassandra LWT

Viết UPDATE ... IF state='AVAILABLE' cho ghế A12. So sánh với SELECT tại QUORUM rồi UPDATE thông thường. Điều kiện nào được đánh giá nguyên tử và ứng dụng cần kiểm tra trường phản hồi nào?

### Bài tập 11 — Redis failover

Primary Redis trả OK cho SET K=1; replica chưa nhận ghi. Client khác đọc replica thấy K=0. Hãy đánh giá lời hứa tuyến tính hóa của **đường đọc cụ thể**. Nếu primary lỗi ngay sau ACK, cần hỏi thêm điều gì về persistence và failover?

### Bài tập 12 — etсd/coordination

Thiết kế compare-createRevision=0 để giành một lock key. Khi lease cũ hết hạn và worker mới nhận quyền, hãy giải thích vì sao cần fencing token để chặn worker cũ cập nhật hệ đích.

### Bài tập 13 — Quorum

Hệ có N=3, W=2, R=2. Tính R+W và giải thích ý nghĩa tập quorum giao nhau. Tại sao công thức này **chưa phải chứng minh linearizability** khi có concurrent writes, pending writes và failover?

### Bài tập 14 — API có hai consistency contracts

Thiết kế **GET seats** từ cache eventual, **POST claim** dùng CAS ở nguồn, và **GET authoritative reservation** dùng strong read. Ghi rõ người dùng có thể thấy stale ở endpoint nào và endpoint nào phải bảo vệ bất biến.

### Bài tập 15 — Transaction và thời gian thực

Phân biệt một giao dịch **serializable** với **strict serializable** bằng ví dụ T1 đã commit trước khi T2 bắt đầu nhưng T2 quan sát trạng thái cũ. Vì sao linearizable single-item reads không đủ cho transaction nhiều item có invariant?

### Bài tập 16 — Phân tích history có hai write

~~~text
K ban đầu 0
W1: invoke 1, response 3, write(1)
W2: invoke 2, response 6, write(2)
R1: invoke 4, response 5, read() -> 1
R2: invoke 7, response 8, read() -> 2
~~~

Hãy tìm thứ tự tuyến tính hợp lệ hoặc chứng minh không có. Chú ý W1 và W2 overlap, còn R2 bắt đầu sau W2 hoàn tất.

### Bài tập 17 — Phản ví dụ theo timestamp

Hai server có đồng hồ lệch 500 ms. Hệ dùng client timestamp để giải quyết last-write-wins. Hãy tạo một timeline mà write hoàn tất sau có timestamp nhỏ hơn write cũ và giải thích vì sao timestamp không tự bảo đảm real-time order.

### Bài tập 18 — Kiểm thử Jepsen-style

Viết kế hoạch kiểm thử một register key–value gồm clients concurrent, operation IDs, invoke/response, CAS, read sau ACK, node kill, network partition, failover, timeout và checker lịch sử. Nêu những kết luận **không được đưa ra** khi thiếu thông tin thời gian hoặc pending operations.

### Bài tập 19 — Đánh đổi latency

Một dashboard xem lượt xem chấp nhận trễ 5 giây, trong khi thao tác cấp quyền admin không được đọc stale. Hãy chọn consistency mode và mức bảo vệ cho từng API, đồng thời nêu metric p95/p99, replication lag, conflict/timeout cần theo dõi.

### Bài tập 20 — Viết hợp đồng tuyến tính hóa

Chọn API **ClaimSeat** và viết một tài liệu ngắn gồm: **object/key identity, sequential specification, success response, real-time order guarantee, CAS predicate, read mode, write durability, retry/idempotency, outcome UNKNOWN, failover behavior và bộ test vi phạm điển hình**. Đừng chỉ viết “database đảm bảo strong consistency” mà không nêu phạm vi.

---

**Kết luận:** Linearizability là lời hứa rằng **có thể nhìn mỗi thao tác như xảy ra tại một điểm nằm giữa lúc gọi và lúc trả lời**, và thứ tự những điểm ấy **không được đảo ngược quan hệ hoàn tất trước–bắt đầu sau của thời gian thực**. Thao tác **chồng lấn** có thể được sắp theo nhiều cách, nhưng tất cả kết quả phải phù hợp **một lịch sử tuần tự hợp lệ duy nhất** cho đối tượng. Để áp dụng trong NoSQL, phải xác định **đúng key/item/document và API được bảo đảm**, đặt quyết định vào **conditional write/CAS** khi cần, hiểu **replication, quorum, leader và failover**, phân biệt với **sequential consistency, serializability và strict serializability**, rồi kiểm chứng qua **histories có invocation/response, concurrency và fault injection**. Một hệ thống đáng tin không chỉ lưu được giá trị đúng cuối cùng; nó còn phải **trả lời đúng với thứ tự những việc mà người dùng đã thực sự thấy hoàn tất**.
