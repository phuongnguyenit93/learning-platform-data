# Nhất quán là tập các lịch sử đọc/ghi được phép quan sát

Một câu hỏi thường gặp khi học cơ sở dữ liệu NoSQL là: **“Hệ này nhất quán mạnh hay nhất quán cuối cùng?”**. Nếu chỉ trả lời “đọc luôn thấy dữ liệu mới” hoặc “đọc có thể hơi cũ”, ta mới mô tả trực giác, chưa mô tả chính xác **những hành vi nào hệ thống được phép trả về** khi nhiều client đọc và ghi đồng thời.

Cách tư duy chặt chẽ hơn là:

> **Một mô hình nhất quán (*consistency model*) xác định tập các lịch sử thao tác đọc/ghi mà client được phép quan sát.** Một lịch sử nằm ngoài tập đó là hành vi vi phạm mô hình; một lịch sử nằm trong tập đó là hành vi được phép, dù có thể khác kỳ vọng trực giác của người dùng.

Đây là trọng tâm của bài **“Nhất quán là tập các lịch sử đọc/ghi được phép quan sát”** trong chương **Các mô hình nhất quán** của module **Database No SQL**.

Ví dụ, giả sử khóa `x` ban đầu bằng `0`. Client A ghi `x = 1` và nhận phản hồi thành công, rồi client B mới bắt đầu đọc `x`:

~~~text
Thời gian ────────────────────────────────────────────────>

Client A: WRITE x=1 ─────── OK
                              |
Client B:                     |── READ x ───> 0
~~~

Một hệ có bảo đảm **linearizability cho khóa x** không được trả `0` ở lần đọc B này nếu không có thao tác hợp lệ khác làm `x` trở lại `0`. Nhưng một hệ có **eventual consistency** có thể cho B đọc bản sao chậm và trả `0` trong thời gian đồng bộ, miễn các điều kiện hội tụ của mô hình cuối cùng được đáp ứng.

Từ **cùng một lịch sử**, ta có thể phân loại mô hình, tìm điểm sai, viết kiểm thử và chọn đường đọc phù hợp cho ứng dụng. Bài này sẽ hướng dẫn từ ký hiệu lịch sử cơ bản tới linearizability, sequential consistency, causal consistency, eventual consistency, các bảo đảm theo phiên và tương tác với transaction.

## 1. Vì sao phải bắt đầu bằng lịch sử thay vì tên sản phẩm?

Một cơ sở dữ liệu phân tán có thể có:

~~~text
Client A ───> Node P (primary/leader)
                      |
                 replication
                      |
Client B ───> Node R (replica/follower)
~~~

A ghi một giá trị tại P; thay đổi cần một khoảng thời gian để tới R. Nếu B đọc R quá sớm, B có thể nhận giá trị cũ.

Tuy nhiên, chỉ biết “hệ có replication bất đồng bộ” chưa trả lời hết:

- B đọc cũ có được phép **sau khi A đã nhận ACK** không?
- B có được đọc giá trị **mới rồi lại đọc giá trị cũ** khi chuyển replica không?
- Chính A có được đọc lại và thấy **chính ghi của mình** không?
- Nếu A ghi `x = 1` rồi `y = 1`, B có thể thấy `y = 1` nhưng `x = 0` không?
- Nếu hai người cùng ghi, mọi client có phải nhìn thấy **cùng một thứ tự** không?
- Nếu không có ghi mới, hệ có được giữ các bản sao khác nhau mãi không?

Mỗi câu hỏi tương ứng với **một ràng buộc lên lịch sử quan sát**.

Một mô hình nhất quán không đơn thuần gắn nhãn lên database. Nó phải chỉ rõ:

1. **Đối tượng** được bảo vệ: một key, một document, một tập key hay một transaction.
2. **Thao tác** thuộc mô hình: `read`, `write`, `compareAndSet`, `delete`, transaction commit…
3. **Quan hệ thứ tự** cần tôn trọng: thứ tự của một client, thứ tự thời gian thực, quan hệ nhân quả…
4. **Kết quả đọc hợp lệ** tương ứng với trạng thái và những lần ghi.
5. **Giả định** về lỗi, mạng, replica, phiên và thời điểm hoàn thành thao tác.

Nếu thiếu các chi tiết trên, một câu quảng bá “strongly consistent” có thể gây hiểu nhầm khi áp dụng vào đường đọc cụ thể.

## 2. Lịch sử (*history*) là gì?

Xét một key `balance` ban đầu bằng `100`. Hai client thực hiện thao tác:

~~~text
Client A: write(balance, 80) → OK
Client B: read(balance)      → 80
~~~

Để phân tích chính xác, ta cần ghi **thời điểm lời gọi bắt đầu và kết quả được trả**. Một phép toán không phải chỉ là “dòng dữ liệu đã được sửa”; nó là một **khoảng thời gian hoạt động**.

### 2.1. Invocation và response

Một thao tác thường gồm:

- **Invocation:** client gọi `write(x, 1)` hoặc `read(x)`.
- **Response:** server trả `OK`, giá trị, lỗi, timeout hoặc một kết quả được định nghĩa.

Ký hiệu đơn giản:

~~~text
invoke_A(write, x=1)
return_A(OK)
invoke_B(read, x)
return_B(1)
~~~

Một **history H** là chuỗi các sự kiện invocation/response, cùng định danh client và đối tượng liên quan.

Ví dụ:

~~~text
H1:
  A: inv write(x,1)
  A: ret OK
  B: inv read(x)
  B: ret 1
~~~

Khác với:

~~~text
H2:
  A: inv write(x,1)
  B: inv read(x)
  B: ret 0
  A: ret OK
~~~

Ở H2, thao tác đọc B **chồng lấn thời gian** với thao tác ghi A. Nếu mô hình yêu cầu linearizability, B vẫn có thể đọc `0` vì ta có thể đặt điểm hiệu lực của đọc trước điểm hiệu lực của ghi trong khoảng hai thao tác đang chồng lấn.

### 2.2. Operation hoàn thành và operation đang chờ

Một lời gọi có invocation nhưng chưa có response được gọi là **pending operation**.

~~~text
Client A: write(x,1) ────────── ?
Client B:        read(x) ───> 1
~~~

Client A timeout không có nghĩa ghi chắc chắn thất bại. DBMS có thể đã xử lý ghi nhưng ACK thất lạc. Khi phân tích history, các thao tác pending phải được xử lý theo quy tắc của mô hình và phương pháp kiểm tra; không được tùy tiện coi mọi timeout như một write chưa xảy ra.

**Đây cũng là lý do retry cần idempotency**, dù trọng tâm của bài là mô hình nhất quán.

## 3. Ba trật tự quan trọng trong một history

Khi phân loại lịch sử, cần tách ba loại quan hệ.

### 3.1. Program order — thứ tự trong một client

Một client thực hiện tuần tự:

~~~text
Client A:
  write(x,1) → OK
  write(y,1) → OK
~~~

**Program order** yêu cầu thao tác đầu tiên của A đứng trước thao tác thứ hai trong thứ tự hoạt động của chính client đó.

Nếu code có nhiều request bất đồng bộ chồng lên nhau, phải xem **thứ tự mà ứng dụng thật sự phát lời gọi**, chứ không tự giả định tất cả hoạt động của process có một thứ tự tuần tự tuyệt đối.

### 3.2. Real-time order — thứ tự không chồng lấn

Nếu thao tác A hoàn thành **trước** khi thao tác B bắt đầu:

~~~text
A: [ write x=1 ] OK
                      B: [ read x ] → ?
~~~

thì ta nói A **đứng trước B theo thời gian thực**.

Ký hiệu:

\[
A \prec_{rt} B
\]

Ở đây `rt` là viết tắt của *real time*. Quan hệ này mạnh hơn việc A và B có timestamp “gần nhau”: nó dựa trên hai khoảng thao tác **không chồng lấn**.

Nếu A và B chồng lấn, thứ tự thời gian thực **không buộc** phải đặt A trước B hay ngược lại chỉ từ thông tin hai khoảng đó.

### 3.3. Causal order — thứ tự nhân quả

Quan hệ nhân quả (*happens-before*) có thể được tạo bởi:

1. Thứ tự thao tác trong cùng một client.
2. Một client **đọc được kết quả** của write rồi thực hiện thao tác phụ thuộc vào kết quả đó.
3. Quan hệ bắc cầu của những phụ thuộc trên.

Ví dụ:

~~~text
Client A: write(order.status = PAID)
                |
                | B đọc thấy PAID
                v
Client B: read(order.status) = PAID
          write(notification.status = READY)
~~~

Ghi `notification.status = READY` của B **phụ thuộc nhân quả** vào write `PAID` của A, vì B chỉ thực hiện nó sau khi đọc thấy PAID.

Quan hệ nhân quả có thể tồn tại **dù hai thao tác đến từ các máy khác nhau**, và nó không nhất thiết cần đồng hồ vật lý được đồng bộ chính xác.

**Không nhầm quan hệ nhân quả với “xảy ra trước trên đồng hồ”.** Hai write từ hai client độc lập có thể có timestamp khác nhau nhưng không có thông tin về sự phụ thuộc; chúng vẫn có thể **concurrent theo quan hệ nhân quả**.

## 4. Hợp lệ về mặt giá trị khác hợp lệ về mặt thứ tự

Giả sử thanh ghi `x` bắt đầu bằng 0. Ta chỉ cho phép:

~~~text
write(x,v) : thay giá trị hiện tại của x bằng v
read(x)    : trả giá trị hiện tại của x
~~~

Theo đặc tả tuần tự:

~~~text
write(x,1)
read(x)    → 1
write(x,2)
read(x)    → 2
~~~

là một lịch hợp lệ.

Nhưng:

~~~text
write(x,1)
read(x)    → 7
~~~

là không hợp lệ **nếu không có write 7 hoặc nguồn trạng thái hợp lệ nào khác**, dù mô hình nhất quán cho phép đọc chậm đến đâu. Eventual consistency **không có nghĩa client được nhận giá trị tùy ý không xuất phát từ lịch cập nhật hợp lệ**.

### Một lịch sử có thể hợp lệ dưới mô hình này và sai dưới mô hình khác

~~~text
Ban đầu x=0
A: write(x,1) → OK
B: read(x)    → 0
~~~

Trong tình huống B bắt đầu **sau** khi A hoàn thành:

- **Linearizability:** không cho phép, vì vi phạm thứ tự thời gian thực.
- **Sequential consistency:** có thể cho phép, vì có thể sắp B đọc 0 trước A ghi 1 trong một thứ tự tuần tự tôn trọng thứ tự riêng của mỗi client.
- **Eventual consistency:** có thể cho phép trong giai đoạn replica chưa bắt kịp, nếu điều kiện hội tụ về sau được đáp ứng.

Đây là lý do quan trọng nhất để diễn đạt nhất quán bằng **tập lịch sử được phép**, thay vì dùng từ “mạnh/yếu” mà không chỉ ra quy tắc.

## 5. Ký hiệu một tập lịch sử được phép

Gọi:

\[
\mathcal{H}
\]

là tập mọi lịch sử có thể xét theo đặc tả thao tác. Một mô hình nhất quán `M` chọn ra tập:

\[
\mathcal{H}_M \subseteq \mathcal{H}
\]

Một hệ thống tuân thủ `M` trong phạm vi cam kết nếu **mọi history thực tế mà hệ có thể sinh ra trong các điều kiện đó đều nằm trong** `\mathcal{H}_M`.

Ví dụ:

~~~text
Tập tất cả lịch sử có thể diễn đạt
┌─────────────────────────────────────────────────────┐
│                                                     │
│   Tập lịch sử hợp lệ với mô hình yếu hơn             │
│   ┌─────────────────────────────────────────────┐   │
│   │                                             │   │
│   │   Tập lịch sử hợp lệ với mô hình mạnh hơn    │   │
│   │   ┌─────────────────────────────────────┐   │   │
│   │   │                                     │   │   │
│   │   └─────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
~~~

Một mô hình có **nhiều ràng buộc hơn** thường cho phép **ít lịch sử hơn**.

Nếu `M1` thực sự mạnh hơn `M2` trong cùng phạm vi và cùng đặc tả đối tượng, ta có thể hình dung:

\[
\mathcal{H}_{M1}\subseteq\mathcal{H}_{M2}
\]

Nhưng **không phải mọi cặp mô hình đều xếp được thành một đường thẳng từ mạnh tới yếu**. Một mô hình có thể bảo vệ session order nhưng không bảo vệ một thuộc tính của transaction; mô hình khác có thể bảo vệ atomic visibility trên nhiều key nhưng cho đọc chậm. Chúng có thể **không so sánh trực tiếp** nếu bảo đảm nằm ở các chiều khác nhau.

## 6. Linearizability: phải tôn trọng thời gian thực

**Linearizability** thường được diễn đạt cho những thao tác trên đối tượng như một thanh ghi, map, counter hoặc key-value operation. Một lịch sử linearizable nếu có thể sắp các thao tác thành **một thứ tự tuần tự hợp lệ** sao cho:

1. Mỗi thao tác có hiệu lực như thể xảy ra tại **một điểm** nằm giữa invocation và response.
2. Thứ tự tuần tự đó **tôn trọng thứ tự thời gian thực** của những thao tác không chồng lấn.
3. Kết quả của thao tác thỏa đặc tả tuần tự của đối tượng.

Điểm giả định trong khoảng thao tác được gọi là **linearization point**. Ta không bắt buộc phải biết chính xác CPU instruction nào thực thi điểm đó; điều cần là **có tồn tại cách sắp xếp hợp lệ**.

### 6.1. Ví dụ linearizable

~~~text
Ban đầu x=0

Time ──────────────────────────────────────────>
A: [------ write(x,1) ------] OK
B:                              [-- read(x) --] 1
~~~

Ta có thể xếp:

~~~text
write(x,1) ; read(x)=1
~~~

và cả giá trị lẫn thời gian thực đều phù hợp.

### 6.2. Ví dụ vi phạm linearizability

~~~text
Ban đầu x=0

A: [------ write(x,1) ------] OK
B:                              [-- read(x) --] 0
~~~

Write hoàn thành trước read bắt đầu, nên write phải đứng trước read trong lịch tuần tự. Với thanh ghi không có write khác, kết quả đọc `0` là **không thể giải thích bằng một thứ tự linearizable**.

### 6.3. Hai thao tác chồng lấn có thể có nhiều kết quả hợp lệ

~~~text
Ban đầu x=0

A: [------ write(x,1) --------] OK
B:        [--- read(x) ---] 0
~~~

Vì hai khoảng chồng nhau, ta có thể chọn thứ tự:

~~~text
read(x)=0 ; write(x,1)
~~~

để giải thích history, nên đọc 0 **có thể hợp lệ**.

Nếu B trả 1 trong lịch chồng lấn đó, ta cũng có thể chọn:

~~~text
write(x,1) ; read(x)=1
~~~

và kết quả có thể hợp lệ.

**Linearizability không có nghĩa read đang chồng với write bắt buộc phải thấy giá trị mới.** Nó yêu cầu tồn tại một thứ tự tuần tự phù hợp với ràng buộc thời gian thực.

## 7. Khi nào linearizability hữu ích?

Những thao tác cần một quyết định “ngay tại thời điểm được chấp nhận” thường là ứng viên:

- Kiểm tra và chiếm một tên đăng nhập duy nhất.
- Compare-and-set trên một version/token.
- Cấp một số thứ tự duy nhất.
- Cập nhật một bộ đếm quota có giới hạn chặt.
- Đổi trạng thái tài nguyên chỉ một người được giữ.

Tuy nhiên, **một key linearizable chưa đủ bảo đảm một thao tác gồm nhiều key nguyên tử**.

Ví dụ:

~~~text
inventory:SKU-1.available = 5
reservation:R-1           = NOT_FOUND
~~~

Nếu ứng dụng phải vừa giảm inventory vừa tạo reservation, linearizability **riêng rẽ** của từng key không tự ngăn trạng thái:

~~~text
available = 2
reservation:R-1 = NOT_FOUND
~~~

được một client nhìn thấy giữa **hai thao tác ghi riêng biệt**. Muốn chúng cùng commit, cần ranh giới transaction/aggregate phù hợp.

Đặc tả nhất quán phải luôn ghi rõ **đối tượng và phạm vi**: per-key, per-document, một batch, một collection, hay toàn bộ transaction.

## 8. Sequential consistency: một thứ tự chung, không ràng buộc thời gian thực giữa client

**Sequential consistency** yêu cầu tồn tại **một thứ tự tuần tự chung** của các thao tác:

1. Tôn trọng **program order** của mỗi client.
2. Đọc trả giá trị phù hợp với trạng thái trong thứ tự chung đó.

Khác với linearizability, sequential consistency **không bắt buộc tôn trọng real-time order giữa các client độc lập**.

### 8.1. Lịch hợp lệ với sequential nhưng không linearizable

~~~text
Ban đầu x=0

A: write(x,1) → OK
                      B: read(x) → 0
~~~

Trong thời gian thực, B đọc sau khi A đã hoàn tất ghi. Linearizability cấm đọc cũ. Nhưng nếu không có quan hệ program order nào buộc A và B, sequential consistency có thể giải thích history bằng:

~~~text
Thứ tự tuần tự giả định:

1. B: read(x) → 0
2. A: write(x,1) → OK
~~~

Thứ tự đó **khác thứ tự thời gian thực**, nhưng vẫn tôn trọng thứ tự riêng của A và B.

### 8.2. Vì sao sequential không phải “đọc bất kỳ”

Giả sử cùng một client:

~~~text
A:
  write(x,1) → OK
  read(x)    → 0
~~~

Nếu không có writer khác, không có cách nào tạo thứ tự tuần tự giữ `write` trước `read` của A mà read trả `0`. History này **vi phạm sequential consistency**.

Nói cách khác, sequential consistency có ràng buộc thực sự; nó chỉ **không bắt buộc bảo toàn trật tự thời gian thực xuyên client**.

### Bảng so sánh

| Câu hỏi | Linearizability | Sequential consistency |
| --- | --- | --- |
| Có một thứ tự tuần tự hợp lệ không? | Có | Có |
| Tôn trọng program order? | Có trong trường hợp thao tác tuần tự | Có |
| Tôn trọng thứ tự thời gian thực giữa các client? | **Có** | **Không bắt buộc** |
| A ghi x=1 xong, B mới đọc x=0 có thể hợp lệ không? | **Không** nếu không có write khác hợp lệ | **Có thể** |
| Một client ghi x=1 rồi tự đọc x=0 có hợp lệ không? | Không trong ví dụ không có write khác | Không trong ví dụ đó |

Ta có:

\[
\mathcal{H}_{linearizable}\subseteq\mathcal{H}_{sequential}
\]

đối với cùng đối tượng và ngữ nghĩa áp dụng tương ứng.

## 9. Causal consistency: giữ đúng những phụ thuộc nhân quả

**Causal consistency** tập trung bảo đảm rằng những thao tác **có quan hệ nhân quả** được quan sát theo một thứ tự phù hợp. Những ghi **độc lập, concurrent theo quan hệ nhân quả** có thể được các client thấy theo thứ tự khác nhau, tùy mô hình/triển khai.

### 9.1. Ví dụ nhân quả

Client A:

~~~text
W1: write(order:O-1.status = PAID)
W2: write(notification:O-1 = READY)
~~~

Nếu W2 được thực hiện sau W1 trong cùng một chương trình tuần tự, có quan hệ:

\[
W1 \rightarrow W2
\]

Client B đọc thấy notification `READY`, rồi đọc order. Một lịch sử như:

~~~text
B: read(notification) → READY
B: read(order.status) → PENDING
~~~

có thể là dấu hiệu **vi phạm causal visibility** nếu phiên đọc B có bảo đảm causal consistency cho hai key, phiên bản `READY` phụ thuộc vào `PAID` và không có ghi hợp lệ sau đó khiến order trở lại `PENDING`.

Nếu hệ chỉ cung cấp eventual consistency riêng cho từng key, replica có thể đồng bộ notification trước order và tạm tạo ra quan sát này.

### 9.2. Nhân quả không chỉ là cùng client ghi

~~~text
Client A: write(x=1)
                  |
                  v
Client B: read(x)=1
          write(y=1)
~~~

Write `y=1` của B phụ thuộc vào việc B đã đọc thấy `x=1` của A. Dù hai writer nằm trên hai máy, `x=1` phải được coi là nguyên nhân của `y=1` khi diễn đạt mô hình causal.

Quan hệ này có thể được lan truyền bằng **session context, logical clocks, version vectors hoặc metadata** tùy hệ thống; không bắt buộc một timestamp vật lý chính xác tuyệt đối.

### 9.3. Những ghi độc lập có thể được thấy khác thứ tự

~~~text
Client A: write(x=1)
Client B: write(y=1)
~~~

Không có bằng chứng A thấy kết quả của B hoặc ngược lại. Hai ghi có thể là **concurrent theo quan hệ nhân quả**.

Một hệ causal có thể cho:

~~~text
Client C thấy x=1 trước, y vẫn =0
Client D thấy y=1 trước, x vẫn =0
~~~

miễn không vi phạm những bảo đảm causal/session được định nghĩa. Causal consistency **không đòi mọi client đồng ý một thứ tự toàn phần cho mọi ghi độc lập** như sequential consistency.

## 10. Một lịch sử causal có thể chấp nhận nhưng sequential không thể

Để nhìn rõ khác biệt, dùng hai key `x` và `y`, ban đầu đều bằng 0:

~~~text
Client A: write(x,1) → OK
Client B: write(y,1) → OK

Client C:
  read(x) → 1
  read(y) → 0

Client D:
  read(y) → 1
  read(x) → 0
~~~

Giả sử hai write của A và B **không có quan hệ nhân quả**; đây là ví dụ các bản sao truyền cập nhật theo thứ tự khác nhau.

Để giải thích bằng **một thứ tự sequential chung**, ta cần:

~~~text
Từ Client C:
  write(x=1) phải trước C.read(x=1)
  C.read(x=1) trước C.read(y=0)
  C.read(y=0) phải trước write(y=1)

Suy ra: write(x=1) trước write(y=1)
~~~

Trong khi từ Client D:

~~~text
write(y=1) trước D.read(y=1)
D.read(y=1) trước D.read(x=0)
D.read(x=0) trước write(x=1)

Suy ra: write(y=1) trước write(x=1)
~~~

Hai thứ tự suy ra **mâu thuẫn**, nên không thể có một thứ tự tuần tự chung thỏa cả hai client.

Nhưng vì hai write độc lập về nhân quả, các client causal có thể tạm thấy chúng theo **hai thứ tự khác nhau**, nếu hệ có bảo đảm và lịch triển khai tương ứng.

Đây là cách dùng history để phân biệt mô hình:

- **Sequential consistency:** một thứ tự toàn phần được mọi client giải thích chung.
- **Causal consistency:** tôn trọng quan hệ nhân quả, nhưng không bắt buộc một thứ tự chung cho tất cả những write độc lập.

## 11. Eventual consistency: cho phép chậm, yêu cầu hội tụ trong điều kiện thích hợp

**Eventual consistency** thường được mô tả: nếu không còn cập nhật mới và các điều kiện đồng bộ/phục hồi được đáp ứng, các replica cuối cùng sẽ **hội tụ** về trạng thái phù hợp.

Ví dụ:

~~~text
             WRITE x=1
                 |
                 v
Primary P: x=1 ------------------------------->
                 \ 
                  \ replication delay
                   \__________________________
                                              \
Replica R: x=0 ───────────────> x=1 -----------> 

Client B đọc R:
  ngay sau write → có thể nhận 0
  sau khi R bắt kịp → nhận 1
~~~

Đây là trực giác về eventual consistency: **trong lúc chưa hội tụ, có thể đọc trạng thái cũ**.

### Những điều eventual consistency không tự hứa

Nếu chỉ có bảo đảm eventual ở mức tổng quát, nó thường **không tự cam kết**:

- Ngay sau khi writer nhận ACK, mọi replica đã thấy giá trị mới.
- Một client chuyển replica sẽ luôn đọc thấy giá trị **không cũ hơn lần trước**.
- Client chắc chắn đọc thấy chính ghi của mình lập tức.
- Hai key có quan hệ nghiệp vụ được quan sát theo một snapshot nguyên tử.
- Thời gian hội tụ có một giới hạn cố định như 10 ms hay 1 giây.
- Không có xung đột giữa hai ghi concurrent; engine phải có conflict resolution thích hợp.

Tùy hệ, eventual consistency có thể đi kèm những bảo đảm mạnh hơn như session consistency, causal delivery hoặc điều kiện staleness có giới hạn.

### “Cuối cùng” cần giả định tiến triển

Nếu mạng bị chia cắt vĩnh viễn hoặc một replica không bao giờ nhận update, không thể đòi replica hội tụ bất kể điều kiện thực tế. Phát biểu eventual consistency có ý nghĩa dưới những điều kiện như:

- Không có ghi mới trong khoảng xét.
- Các bản sao cần thiết còn khả năng trao đổi.
- Cơ chế đồng bộ/repair được tiếp tục thực hiện công bằng.
- Conflict resolution có quy tắc đưa hệ về trạng thái hội tụ.

**Eventual không có nghĩa “sẽ hội tụ dù mạng và tiến trình mãi mãi không hoạt động”.**

### Safety và liveness

Mô hình linearizability có các ràng buộc **safety**: một lần đọc trả sai thứ tự sau write hoàn thành có thể là bằng chứng hữu hạn của vi phạm.

Eventual convergence còn có tính chất **liveness/progress**: các replica cần đạt hội tụ trong tương lai khi điều kiện thích hợp tồn tại. Một vài giây đọc cũ **chưa đủ** chứng minh eventual consistency bị vi phạm nếu chưa biết deadline hoặc giả định môi trường.

Đây là lý do kiểm tra eventual consistency khác với việc tìm một history ngắn vi phạm linearizability.

## 12. Eventual consistency không có nghĩa một thứ tự “mạnh/yếu” đơn giản

Xét hai loại bảo đảm:

**Bảo đảm A:** các replica cuối cùng hội tụ, nhưng trong khoảng đồng bộ chưa bắt kịp, một client có thể thấy `x=1` rồi `x=0`.

**Bảo đảm B:** client luôn thấy kết quả đọc không đi lùi trong session, nhưng hệ vẫn có thể mất thời gian để cập nhật tất cả replica.

B tốt hơn A ở chiều **monotonic reads**, nhưng chưa chắc B cung cấp linearizability hay một giới hạn hội tụ theo thời gian.

Tương tự, một hệ có thể bảo đảm **atomic visibility của một transaction nhiều key** nhưng cho phép đọc một snapshot cũ; hệ khác có thể có linearizable point reads trên từng key nhưng không cho snapshot nguyên tử nhiều key.

Vì vậy:

> **Mô hình nhất quán là tập các điều kiện lên history, thường có nhiều chiều; không phải một thanh trượt duy nhất từ “mạnh” sang “yếu”.**

Muốn so sánh hai hệ, cần áp dụng **cùng đặc tả thao tác, cùng phạm vi key/transaction và cùng mô hình lỗi**.

## 13. Session guarantees: bảo vệ trải nghiệm của một người dùng

Trong ứng dụng web/mobile, người dùng có thể đi qua nhiều backend instance hoặc replica trong một phiên. Bốn bảo đảm thường được dùng để mô tả tính nhất quán theo phiên:

| Bảo đảm | Điều cần giữ | Ví dụ |
| --- | --- | --- |
| **Read-your-writes (RYW)** | Sau khi ghi thành công, phiên đọc lại thấy tác động ghi của mình hoặc trạng thái phù hợp mới hơn | Sửa avatar rồi refresh vẫn thấy ảnh mới |
| **Monotonic reads** | Một phiên không thấy lịch sử dữ liệu đi lùi | Đã thấy trạng thái SHIPPED thì không quay về PENDING chỉ vì đổi replica |
| **Monotonic writes** | Những ghi liên tiếp của cùng phiên được áp dụng theo thứ tự phù hợp | Ghi tên mới rồi cập nhật mô tả, không đảo thứ tự tác động phụ thuộc |
| **Writes-follow-reads** | Ghi sau một lần đọc được sắp/áp dụng phù hợp với những thay đổi đã được phiên quan sát | Đọc tài liệu phiên bản 7 rồi thêm bình luận phụ thuộc bản đó |

Các khái niệm này là **những bảo đảm có thể kết hợp**, không phải mặc định mọi DBMS đều cung cấp cùng lúc.

### 13.1. Read-your-writes

~~~text
Client A:
  write(profile.name="An Nguyen") → OK
  read(profile.name) → "An"
~~~

Nếu không có write hợp lệ khác, đây là vi phạm RYW trong một session được bảo đảm RYW.

Giải pháp tùy hệ:

- Đọc từ leader/primary sau khi ghi.
- Dùng session token hoặc version bookmark yêu cầu replica đã bắt kịp.
- Sticky routing tới replica phù hợp trong phiên.
- Chỉ trả kết quả UI sau khi nhận đúng acknowledgment cần thiết.

**Đọc từ cùng process API** không tự bảo đảm RYW nếu process mỗi lần lại gọi một replica khác.

### 13.2. Monotonic reads

~~~text
Client A:
  read(order.status) → SHIPPED
  read(order.status) → PAID
~~~

Nếu không có thao tác hợp lệ nào chuyển trạng thái ngược trở lại PAID, người dùng đang thấy dữ liệu **đi lùi**. Một ứng dụng có monotonic reads không được cho lịch này trong cùng session, dù các replica có tốc độ đồng bộ khác nhau.

### 13.3. Monotonic writes

~~~text
Client A:
  write(document.version=2)
  write(document.version=3)
~~~

Các update của A phải được áp dụng theo thứ tự bảo đảm; replica nhận version 3 rồi bị một write version 2 cũ ghi đè có thể vi phạm nếu hệ không xử lý version/order.

### 13.4. Writes-follow-reads

~~~text
Client A:
  read(task.status) → APPROVED
  write(invoice.ready) → true
~~~

Ghi `invoice.ready=true` phụ thuộc vào việc A đã quan sát `task.status=APPROVED`. Bảo đảm writes-follow-reads giúp không bỏ qua quan hệ nhân quả được hình thành bởi thao tác đọc trước đó.

## 14. Causal consistency và session consistency liên hệ thế nào?

Các session guarantees có thể phối hợp để xây một mô hình theo quan hệ nhân quả.

Ví dụ:

~~~text
Writer A:
  W1: publish(article)

Reader B:
  R1: read(article) = published
  W2: addComment(article)

Reader C:
  R2: read(comment) = visible
  R3: read(article) = missing
~~~

Nếu comment được tạo **vì** B thấy article đã published, quan sát comment mà không thấy article có thể vi phạm causal visibility. Khi chọn mô hình, cần hỏi **session context của các client được truyền như thế nào** giữa các service và replica.

Điều này giải thích vì sao một hệ có thể cần:

- Token biểu diễn version đã quan sát.
- Context phụ thuộc nhân quả kèm request.
- Cơ chế chỉ phục vụ read khi replica đủ mới.
- Metadata đảm bảo causal delivery theo đúng thứ tự.

Không phải ứng dụng nào cũng cần metadata phức tạp. Nếu toàn bộ request đi qua leader có bảo đảm thích hợp, yêu cầu có thể được giải quyết bằng con đường đơn giản hơn với đánh đổi khác về availability/latency.

## 15. Bounded staleness: cho phép cũ nhưng đến mức nào?

Một mô hình khác là **bounded staleness**: cho phép dữ liệu cũ trong một giới hạn được xác định rõ.

Có thể diễn đạt giới hạn theo:

- **Thời gian:** kết quả không được tụt sau write đã hoàn tất quá `Δ` giây theo ngữ nghĩa được định nghĩa.
- **Số phiên bản:** dữ liệu không được lùi quá `k` cập nhật so với một trạng thái tham chiếu.
- **Session watermark:** read phải đạt ít nhất version mà client đã nhìn thấy.

Ví dụ yêu cầu:

~~~text
Dashboard chỉ cần thống kê có thể cũ tối đa 5 giây.
~~~

Đó là một **hợp đồng độ mới đo được**, không phải chỉ nói “eventually consistent”.

### Vì sao giới hạn phải được phát biểu cụ thể?

Một cơ chế replication bình thường có lag trung bình 100 ms không đồng nghĩa nó **cam kết** kết quả luôn cũ dưới 5 giây. Khi tắc nghẽn hoặc partition mạng, lag có thể tăng lớn.

Để hứa bounded staleness, hệ phải có cơ chế:

- Nhận biết mốc version/timestamp đáng tin cậy.
- Từ chối/chờ hoặc chuyển đường đọc khi replica quá cũ.
- Công bố giới hạn áp dụng trong điều kiện lỗi nào.
- Đo và cảnh báo khi không thể đáp ứng giới hạn.

**SLO độ trễ đồng bộ quan sát được** khác **bảo đảm nhất quán bắt buộc** của mô hình.

## 16. Consistency của một key khác atomic visibility của nhiều key

Giả sử một ứng dụng chuyển tiền bằng hai bản ghi:

~~~text
wallet:A.balance = 1000
wallet:B.balance = 500
total = 1500
~~~

Ứng dụng muốn chuyển 200:

~~~text
wallet:A.balance = 800
wallet:B.balance = 700
~~~

Nếu có hai lệnh ghi riêng:

~~~text
T1: write(wallet:A.balance,800)
T2: read(A)=800; read(B)=500
T3: write(wallet:B.balance,700)
~~~

Đọc từng key có thể **linearizable** theo thứ tự thời gian thực, nhưng cặp kết quả ở T2 vẫn cho tổng `1300` — một trạng thái trung gian **không phù hợp nếu nghiệp vụ yêu cầu chuyển tiền nguyên tử**.

Nguyên nhân không phải per-key linearizability thất bại. Nguyên nhân là **toàn bộ chuyển tiền chưa được định nghĩa như một transaction nguyên tử nhiều key**.

### Transaction atomicity là một trục khác

Nếu chuyển tiền phải là một đơn vị:

~~~text
BEGIN TRANSACTION
  Debit A by 200 if sufficient
  Credit B by 200
  Insert ledger record
COMMIT
~~~

ta phải đánh giá:

- Tất cả thay đổi có cùng commit hay không?
- Transaction có ngăn mất cập nhật/overspend không?
- Reader có thấy snapshot hợp lệ hay có thể thấy một phần?
- Kết quả commit được phản ánh tới các replica/read models thế nào?

Một tuyên bố “read key strong” không trả lời tự động các câu hỏi đó.

## 17. ACID Consistency khác consistency model của hệ phân tán

Chữ **C** trong ACID và “consistency” trong mô hình phân tán cùng tên nhưng khác câu hỏi.

| Khái niệm | Câu hỏi chính |
| --- | --- |
| **ACID Consistency** | Transaction có bảo toàn schema constraint và các invariant đã biểu diễn không? |
| **Linearizability/causal/eventual consistency** | Client có thể quan sát **những lịch sử đọc/ghi nào**? |
| **Isolation/serializability** | Nhiều transaction đồng thời có kết quả tương đương một thứ tự hợp lệ không? |
| **Durability** | Sau khi ACK commit, dữ liệu tồn tại qua những lỗi nào? |

Ví dụ, mỗi transaction cập nhật một document chính xác theo invariant, nhưng client đọc từ replica trễ và thấy dữ liệu cũ. **C của ACID tại nguồn không tự làm mọi replica trở thành linearizable**.

Ngược lại, một database có linearizable reads/writes trên từng key nhưng ứng dụng ghi `available=-5` do không validate input vẫn phá invariant nghiệp vụ. **Linearizability không tự biết số tồn không được âm**.

### Không dùng “consistent” thay cho một hợp đồng cụ thể

Trong tài liệu thiết kế, thay vì:

> “Dữ liệu luôn nhất quán.”

hãy viết:

> “Lệnh conditional update trên inventory được thực hiện nguyên tử ở primary; request nhận success chỉ khi điều kiện đủ hàng khớp; màn hình catalog được phép đọc read model trễ tối đa theo SLO đã thống nhất.”

Câu thứ hai giúp kiểm thử và vận hành vì mỗi thành phần có một bảo đảm cụ thể.

## 18. Serializability của transaction khác linearizability của operation

**Serializability** là một tính chất cô lập transaction: kết quả của các transaction đồng thời tương đương một **lịch transaction tuần tự** hợp lệ.

**Linearizability** thường xét một operation và ràng buộc **real-time order** giữa các operation.

Khi cần cả transaction serializable lẫn tôn trọng thứ tự thời gian thực giữa các transaction, ta thường nói tới **strict serializability**.

### Ví dụ về transaction không serializable

Một hệ yêu cầu luôn có ít nhất một bác sĩ trực:

~~~text
Ban đầu:
  doctorA.onCall = true
  doctorB.onCall = true
~~~

Hai transaction:

~~~text
T1:
  read A=true, B=true
  write A=false

T2:
  read A=true, B=true
  write B=false
~~~

Nếu cả hai cùng commit sau khi đọc một snapshot cũ, kết quả:

~~~text
A=false, B=false
~~~

vi phạm invariant dù T1 và T2 viết hai document khác nhau. Đây là **write skew** dưới một số mô hình snapshot isolation.

Một hệ có **serializable transactions** phải có cơ chế ngăn lịch không thể tuần tự hóa này, chẳng hạn abort một transaction hoặc phối hợp thích hợp.

**Điều quan trọng:** consistency của các thao tác trên từng key và isolation của một transaction nhiều key không được đánh đồng. Khi đọc tài liệu DBMS, cần tìm cả **read consistency** lẫn **transaction isolation**.

## 19. Replication lag tạo ra history đọc cũ thế nào?

Một hệ replica đơn giản:

~~~text
                   write(x=1)
Client A ────────────────> Leader L
                            x=1
                             |
                            ACK
                             |
                     async replication
                             |
                             v
Client B ────────────────> Replica R
                            x=0 (chưa cập nhật)
~~~

Lịch:

~~~text
T1: A invokes write(x,1)
T2: L applies write
T3: A receives OK
T4: B invokes read(x) on R
T5: B receives 0
T6: R applies replication x=1
~~~

Trong ví dụ không có write khác:

- B đọc tại T4–T5 **vi phạm linearizability** trên key nếu hệ hứa tuyến đọc đó linearizable.
- B đọc cũ có thể phù hợp với một mô hình **eventual consistency** trên read replica.
- Sau T6, R có thể trả 1 nếu không còn cập nhật hoặc lỗi mới; đó là hội tụ trong mô hình minh họa.

### Một hệ có thể hỗ trợ nhiều đường đọc

~~~text
GET key from leader    → có thể được thiết kế theo bảo đảm mạnh hơn
GET key from follower  → có thể cho phép stale reads
GET key via GSI/search → có thể dùng index bất đồng bộ riêng
~~~

Không nên nói “DBMS X luôn linearizable” chỉ vì **một API** của nó có tùy chọn strong read. Phải ghi rõ:

- Đọc từ đâu?
- Có dùng transaction không?
- Có cần session token không?
- Read concern/consistency level là gì?
- Index/read model có được cập nhật đồng bộ không?

## 20. Quorum reads/writes giúp gì, không tự đảm bảo gì?

Trong một hệ leaderless replication, giả sử một key có **N replica**:

~~~text
N = 3
Write quorum W = 2
Read quorum  R = 2
~~~

Ta có:

\[
R+W>N
\]

Nghĩa là bất kỳ tập 2 replica được dùng để đọc và tập 2 replica đã ACK ghi đều **có ít nhất một replica giao nhau** trong mô hình tập hợp đơn giản.

Ví dụ:

~~~text
Replica A: x=1  (đã ACK write)
Replica B: x=1  (đã ACK write)
Replica C: x=0  (chưa bắt kịp)

Read từ B,C:
  B trả 1
  C trả 0
~~~

Nếu hệ có quy tắc chọn phiên bản phù hợp, read từ quorum có thể tìm được version mới trên B. Nhưng cần hiểu:

- **Quorum giao nhau** giúp tăng cơ hội nhìn thấy thay đổi đã ACK.
- Nó **không tự là bằng chứng linearizability cho toàn bộ hệ**.

### Vì sao điều kiện R+W>N chưa đủ?

Phải xét thêm:

1. **Write concurrent**: hai client cập nhật cùng key, hệ quyết định thứ tự và xung đột ra sao?
2. **Phiên bản/metadata**: làm sao xác định bản nào mới đúng?
3. **Topology và membership**: tập N replica có ổn định không hay có sloppy quorum/hinted handoff?
4. **Read repair và incomplete write**: các bản ghi chưa đủ ACK có thể được thấy thế nào?
5. **Clock skew và timestamp**: nếu dùng LWW, timestamp từ nhiều node có thể tạo thứ tự không tương ứng thời gian thực.
6. **Fault model**: có partition mạng, replica lỗi, thay leader hoặc thay thế replica không?

Một hệ muốn có linearizable read/write cần thêm **giao thức phối hợp phù hợp**, không chỉ cấu hình số `R` và `W`. Trong một hệ cụ thể, cấu hình quorum có thể có bảo đảm nhất quán riêng; cần dựa vào tài liệu và cơ chế thực, không suy từ bất đẳng thức đơn thuần.

## 21. Network partition đặt ra đánh đổi gì?

Giả sử cụm được chia hai nhóm không liên lạc:

~~~text
  Group A                X                Group B
  replica 1           network             replica 2
  replica 3          partition
~~~

Trong thời gian phân vùng:

- Một phía có thể từ chối ghi/đọc theo chính sách để giữ bảo đảm mạnh.
- Một phía có thể chấp nhận thao tác và chấp nhận đồng bộ/xung đột về sau.
- Một số thao tác có thể thành công, một số thất bại tùy quorum, leader và topology.

Một câu thường thấy:

> “Có partition thì chọn consistency hay availability.”

Đây là trực giác từ **CAP**, nhưng không được dùng nó để kết luận mọi DBMS chỉ thuộc một trong hai ô “CP/AP” cho mọi API. Bảo đảm còn phụ thuộc operation, phạm vi key, cách xử lý lỗi và cấu hình. CAP không đồng nghĩa với ACID Consistency, cũng không xếp toàn bộ lịch sử đọc/ghi thành một bảng một chiều.

### Hướng tư duy bằng history

Khi mạng phân vùng, hỏi:

1. Client ở hai phía có được **cùng ghi một key** không?
2. Nếu cùng ghi, hệ có thể tạo **hai lịch sử xung đột** không?
3. Khi kết nối phục hồi, xung đột được giải quyết thế nào?
4. Trước khi phục hồi, những lần đọc có được trả giá trị cũ không?
5. Một thao tác đã nhận ACK có thể bị ghi khác “làm biến mất” không?

Những câu hỏi này kiểm tra chính xác **tập history được phép**, hữu ích hơn chỉ đọc nhãn AP/CP.

## 22. Last-write-wins không đồng nghĩa một thứ tự duy nhất theo thời gian thực

Một số hệ giải quyết xung đột bằng **last-write-wins (LWW)** theo timestamp/version được chọn.

Ví dụ:

~~~text
Client A: write(profile.city = "Ha Noi")
Client B: write(profile.city = "Da Nang")
~~~

Nếu hai write concurrent, một giá trị có thể thắng theo quy tắc LWW. Nhưng cần phân biệt:

- **Last theo timestamp** không nhất thiết là write hoàn thành cuối theo đồng hồ thực tế.
- Một replica có thể tạm trả bản cũ cho tới khi được cập nhật.
- LWW chọn **một giá trị**, không tự gộp hai hiệu ứng.

Với counter:

~~~text
A đọc count=10 rồi write count=11
B đọc count=10 rồi write count=11
~~~

LWW có thể trả 11, nhưng nếu hai request độc lập đều muốn +1, kết quả nghiệp vụ đúng là 12. Đây là **lost update** ở tầng ứng dụng, không được sửa chỉ bằng cách thay chiến lược replication metadata.

Giải pháp có thể là atomic increment, compare-and-set, giao dịch hoặc một kiểu dữ liệu hợp nhất phù hợp như CRDT counter, tùy invariant.

**Mô hình nhất quán và ngữ nghĩa của operation phải đi cùng nhau.** Nếu operation là `set(value)` thì hai lần set 11 khác với hai lần `increment(1)`.

## 23. Khi nào một lịch có vẻ “đọc cũ” nhưng vẫn linearizable?

Phân tích hai lịch gần giống:

### Lịch A — chồng lấn

~~~text
x=0

Time ───────────────────────────────────────────────>
Writer: [-------- write(x,1) ----------------] OK
Reader:       [------ read(x) ------] 0
~~~

Vì read chồng với write, **đọc 0 có thể hợp lệ** với linearizability nếu ta đặt read trước write trong thứ tự tuyến tính.

### Lịch B — không chồng lấn

~~~text
x=0

Time ───────────────────────────────────────────────>
Writer: [--- write(x,1) ---] OK
Reader:                         [--- read(x) ---] 0
~~~

Đây là **vi phạm** vì write đã kết thúc trước read bắt đầu.

**Bài học quan trọng:** trong kiểm thử, ghi “read trả 0 sau khi tôi gửi write 1” chưa đủ. Phải biết **write đã trả ACK chưa trước khi read được gọi**, không chỉ biết lệnh nào được gọi đầu tiên.

## 24. History có lỗi và timeout cần được đọc thận trọng

Giả sử:

~~~text
Client A:
  write(x,1) → timeout

Client B:
  read(x) → 1
~~~

Có ít nhất hai khả năng:

1. Write A đã thực hiện nhưng phản hồi mất.
2. Có write hợp lệ khác tạo `x=1`.

Nếu không có write khác, B đọc 1 là bằng chứng ghi A có thể đã tác động; nhưng **timeout của A không tự xác nhận thành công hay thất bại**.

Ngược lại:

~~~text
Client A:
  write(x,1) → timeout
Client B:
  read(x) → 0
~~~

B đọc 0 cũng không chứng minh A chắc chắn thất bại nếu B đang đọc replica trễ hoặc write A chưa hoàn tất.

### Khi cần phân tích linearizability

Với pending operations, trình kiểm tra history phải xem có thể **hoàn tất hoặc loại bỏ những operation pending theo quy tắc của định nghĩa và bằng chứng** để tạo một lịch hợp lệ hay không. Không nên tự đánh dấu tất cả operation timeout là `write=failed`.

Ở tầng ứng dụng, để chống hiệu ứng lặp:

- Dùng `requestId`/idempotency key ổn định.
- Tra cứu trạng thái đã commit bằng key có thẩm quyền.
- Retry với cùng ID trong phạm vi giao thức.
- Không tự tạo request ID mới chỉ vì mất ACK.

Đây là vấn đề **unknown outcome**, khác với việc định nghĩa mô hình nhất quán nhưng ảnh hưởng lớn tới những history thực tế được ghi nhận.

## 25. Một history thường có nhiều key, nhiều client, nhiều phiên

Một file log đơn giản:

~~~json
[
  {
    "op": "write",
    "client": "A",
    "key": "x",
    "input": 1,
    "invocation": 10,
    "response": 20,
    "result": "OK"
  },
  {
    "op": "read",
    "client": "B",
    "key": "x",
    "invocation": 30,
    "response": 40,
    "result": 0
  }
]
~~~

Ví dụ trên minh họa thời điểm logic trên **một thang thời gian đáng tin cậy trong bài thử**. Trong hệ nhiều máy, timestamp do từng host tự tạo có thể bị lệch đồng hồ, làm việc tái dựng thứ tự thực tế khó hơn.

Một bản ghi history hữu ích nên có:

| Trường | Mục đích |
| --- | --- |
| `operationId` | Ghép invocation và response của một lần gọi |
| `clientId/sessionId` | Khôi phục thứ tự chương trình/session |
| `key / transactionId` | Xác định phạm vi đối tượng |
| `operation type` | Read, write, CAS, transaction… |
| `arguments` | Giá trị ghi, điều kiện, revision dự kiến |
| `returned value / error` | Kết quả mà client quan sát |
| `start/end interval` | Xét chồng lấn và real-time precedence |
| `requestId` | Phát hiện retry/duplicate ý định |
| `read path` | Leader, follower, cache, GSI, read model… |
| `version / token` | Phân tích thứ tự và độ mới nếu có |

Để phân tích chính xác, **không được chỉ lưu giá trị cuối cùng**. Hai lịch sử rất khác nhau có thể dẫn đến cùng một giá trị cuối nhưng khác bảo đảm nhất quán.

## 26. Thực hành: mô phỏng replica lag bằng Java

Ví dụ Java sau cố ý giữ **hai bản sao dữ liệu trong bộ nhớ** để minh họa rằng write đã ACK ở primary nhưng một read từ replica vẫn trả giá trị cũ.

Nó **không phải mô phỏng đầy đủ một NoSQL DBMS**, không có mạng, WAL, transaction hay failure recovery. Mục đích chỉ là tạo một **lịch sử quan sát có kiểm soát**.

Tạo file `ReplicaHistoryDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ReplicaHistoryDemo {

    public static void main(String[] args) {
        Map<String, Integer> primary = new HashMap<>();
        Map<String, Integer> replica = new HashMap<>();

        // Trạng thái ban đầu được đồng bộ.
        primary.put("x", 0);
        replica.put("x", 0);

        // A thực hiện write ở primary và nhận ACK.
        System.out.println("A INVOKE write(x,1)");
        primary.put("x", 1);
        System.out.println("A RETURN OK");

        // B bắt đầu đọc SAU khi A nhận ACK.
        System.out.println("B INVOKE read(x) on replica");
        int stale = replica.get("x");
        System.out.println("B RETURN " + stale);

        // Mô phỏng replication bắt kịp.
        System.out.println("REPLICATE x from primary");
        replica.put("x", primary.get("x"));

        System.out.println("B INVOKE read(x) on replica");
        int fresh = replica.get("x");
        System.out.println("B RETURN " + fresh);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ReplicaHistoryDemo.java
java ReplicaHistoryDemo
~~~

Kết quả dự kiến:

~~~text
A INVOKE write(x,1)
A RETURN OK
B INVOKE read(x) on replica
B RETURN 0
REPLICATE x from primary
B INVOKE read(x) on replica
B RETURN 1
~~~

### Phân tích lịch sử

Hai lần đọc của B lần lượt trả `0` và `1`. Vì **lần đọc đầu diễn ra sau ACK của write**:

- Nếu đường đọc replica này hứa **linearizability**, history không hợp lệ.
- Nếu chỉ hứa **eventual consistency**, lịch có thể hợp lệ trong khoảng chưa hội tụ; sau bước replication, replica trả giá trị mới.
- B thấy 0 rồi 1 **không vi phạm monotonic reads**. Nhưng nếu sau khi thấy 1, B chuyển sang một replica cũ khác và lại thấy 0, đó là vấn đề cho session có cam kết monotonic reads.

**Không dùng ví dụ này để khẳng định một sản phẩm cụ thể luôn trả stale read.** Hành vi thực tùy giao thức, read concern, replication, topology và cấu hình.

## 27. Thực hành: phân loại lịch sử bằng điều kiện thời gian thực

Đối với một thanh ghi đơn, ta có thể thực hiện một bài kiểm tra rất nhỏ:

~~~text
Initial x=0
Write W: [start=10, end=20], writes x=1, result OK
Read  R: [start=30, end=40], returns x=0
~~~

Vì:

\[
end(W)<start(R)
\]

W phải đứng trước R trong mọi lịch tuyến tính hợp lệ. Nếu không có write nào khác, R trả 0 **vi phạm linearizability**.

Ngược lại:

~~~text
Write W: [start=10, end=40], writes x=1
Read  R: [start=20, end=30], returns x=0
~~~

Hai thao tác chồng lấn. Ta có thể đặt R trước W trong thứ tự tuyến tính; kết quả đọc 0 **không tự là bằng chứng vi phạm**.

### Bài kiểm tra nhỏ không thay thế checker đầy đủ

Những quy tắc trên là **kiểm tra cần thiết cho các lịch đơn giản**, không phải thuật toán kiểm chứng linearizability cho lịch sử nhiều client phức tạp.

Một checker đúng nghĩa cần:

1. Ghép invocation/response và xử lý pending operations.
2. Tạo các ràng buộc thứ tự từ real-time precedence.
3. Xét những thứ tự có thể của thao tác concurrent.
4. Áp đặc tả tuần tự của object để kiểm tra kết quả read/CAS/write.
5. Tìm một thứ tự hợp lệ hoặc chứng minh không tồn tại.

Đối với lịch có nhiều thao tác concurrent, việc chỉ kiểm “write cuối cùng theo timestamp” rất dễ đưa ra kết luận sai.

## 28. Vì sao không được chỉ so timestamp để kiểm chứng?

Giả sử hai máy có đồng hồ lệch:

~~~text
Host A clock:  10:00:05
Host B clock:  10:00:03
~~~

Một write ở A có thể hoàn thành trước một read ở B bắt đầu theo thời gian thực nhưng log timestamps trông như read xảy ra trước.

Ngoài ra:

- Request network có thời gian chuyển đi/về.
- Server nhận thao tác khác thời điểm client gọi.
- Đồng hồ hệ điều hành có thể chỉnh lại.
- Timestamp của document có thể do **client cung cấp** chứ không phản ánh thứ tự commit.
- Một kết quả từ cache có thể mang timestamp của dữ liệu nguồn, không phải thời điểm đọc.

Vì vậy khi cần lịch sử đáng tin:

- Dùng một **driver kiểm thử** có khả năng ghi khoảng invocation/response theo đồng hồ monotonic trong một nguồn thời gian chung, nếu cấu trúc test cho phép.
- Hoặc dùng metadata/version và cơ chế đồng bộ để suy ra quan hệ thứ tự.
- Không suy diễn thứ tự toàn hệ chỉ từ timestamp tường của các máy chưa đồng bộ và không có thông tin sai số.

**Linearizability nói về quan hệ thực tế giữa thao tác**, không phải chọn giá trị có timestamp lớn nhất.

## 29. Những lịch nào không thể phân loại chỉ từ một lần read?

Quan sát:

~~~text
GET x → 0
~~~

Không đủ để kết luận gì về linearizability, sequential consistency hoặc eventual consistency vì ta chưa biết:

- Giá trị ban đầu của `x`.
- Có write nào đã xảy ra?
- Write hoàn thành khi nào?
- Có write nào đặt lại `x=0`?
- Đọc từ replica/cache nào?
- Thao tác đang chồng lấn hay đã kết thúc?
- Mô hình xét cho key hay transaction?

Một giá trị có vẻ cũ chỉ thành **vi phạm** khi được đặt trong **đầy đủ bối cảnh history và cam kết nhất quán**.

Tương tự:

~~~text
PUT x=1 → OK
GET x  → 1
~~~

không đủ chứng minh toàn hệ linearizable: chỉ một lịch “đẹp” nằm trong tập hợp hợp lệ không chứng minh **mọi lịch có thể xảy ra** đều hợp lệ.

Trong kiểm thử hệ phân tán, mục tiêu thường là **tìm phản ví dụ** (một history không được phép) bằng nhiều workload, crash, failover và partition mạng có kiểm soát. Không tìm thấy phản ví dụ trong một đợt test **không phải chứng minh toán học hệ luôn đúng**.

## 30. Nhất quán ảnh hưởng trực tiếp tới thiết kế UI và nghiệp vụ

Hai endpoint có thể dùng **khác mô hình quan sát** mà vẫn đúng sản phẩm.

### 30.1. Trang danh sách sản phẩm

~~~text
Nguồn: Product database
Đường đọc: Cache hoặc search index bất đồng bộ
Yêu cầu: chấp nhận dữ liệu hơi cũ theo chính sách
~~~

Trang danh sách có thể chấp nhận giá hoặc mô tả trễ trong một giới hạn, **nhưng khi thanh toán phải xác nhận lại dữ liệu có thẩm quyền**.

### 30.2. Màn hình trạng thái đơn của chính người vừa đặt

~~~text
Client: tạo đơn O-501 → success
Client: GET /orders/O-501 → NOT_FOUND
~~~

Đây là một lịch có thể xảy ra nếu GET được phục vụ từ read model chưa bắt kịp. Nhưng trải nghiệm đó có thể không chấp nhận được. Ứng dụng có thể cần **read-your-writes** bằng đường đọc có token phiên bản/leader hoặc cơ chế chờ read model bắt kịp.

### 30.3. Cấp mã giảm giá có quota chặt

~~~text
Quota ban đầu = 100
Hai request cùng xin lượt thứ 100
~~~

Một read eventual từ replica để kiểm tra “còn lượt” **không đủ** cho quyết định cấp phát chặt. Cần một đường ghi có điều kiện nguyên tử, transaction hoặc cơ chế phối hợp tương đương tại nguồn có thẩm quyền.

### 30.4. Dashboard tổng hợp

~~~text
Số đơn đã bán theo giờ
Yêu cầu: có thể trễ vài phút
~~~

Một materialized view/event pipeline hội tụ dần có thể phù hợp nếu UI hiển thị rõ **thời điểm dữ liệu được cập nhật**, người dùng hiểu số liệu tạm và có quy trình đối soát.

**Nhất quán không phải mục tiêu càng mạnh càng tốt trong mọi nơi**. Đó là quyết định dựa trên invariant, latency, availability, chi phí và trải nghiệm.

## 31. Đường đọc từ cache tạo thêm một lịch sử quan sát

Một hệ thống thường không chỉ có database và replica:

~~~text
Browser
   |
   v
API backend
   |
   +---- Redis cache
   |
   +---- Authoritative database
   |
   +---- Search/read model
~~~

Giả sử database chính đã ghi `price=120000`, nhưng cache vẫn có `price=100000`. Một GET từ API trả 100000 tạo một **history của hệ thống ứng dụng**, dù cơ sở dữ liệu chính có thể đang cung cấp linearizable reads trên chính nó.

### Hai lớp bảo đảm khác nhau

**Đường DB trực tiếp:**

~~~text
write DB price=120000 → ACK
read DB price          → 120000
~~~

**Đường API qua cache:**

~~~text
write DB price=120000 → ACK
read API /product      → cached price=100000
~~~

Không có mâu thuẫn nếu cam kết consistency của API **cho phép cache cũ**. Nhưng nếu sản phẩm hứa “giá mới phải thấy ngay sau chỉnh sửa”, API đã vi phạm lời hứa dù DBMS bên dưới hoạt động đúng.

### Những quyết định cần ghi rõ

- Cache có TTL bao lâu, có invalidation khi ghi không?
- Có thể bị eviction và nạp lại bất kỳ lúc nào không?
- Search index/read model lag được phép bao nhiêu?
- Người vừa ghi có đường **read-your-writes** riêng không?
- Các bước quan trọng như thanh toán có bypass cache không?

**Đánh giá consistency ở ranh giới mà người dùng thật sự quan sát**, không chỉ dựa trên nhãn của database trung tâm.

## 32. Consistency và yêu cầu độ sẵn sàng khi lỗi

Một hệ có thể chọn không trả một giá trị cũ khi không thể xác nhận trạng thái mới:

~~~text
Client GET
   |
   v
Không liên hệ được leader/quorum
   |
   v
Trả lỗi / timeout thay vì dữ liệu không chắc mới
~~~

Hệ khác có thể ưu tiên trả dữ liệu cũ từ replica/cache:

~~~text
Client GET
   |
   v
Leader không truy cập được
   |
   v
Trả replica snapshot đã biết
~~~

Đó là **đánh đổi theo operation**. Với màn hình tin tức, đọc cũ có thể tốt hơn lỗi. Với xác nhận số dư có thể chi, trả dữ liệu cũ và cho phép giao dịch có thể rất nguy hiểm.

### Tách thông tin “stale” khỏi quyền thao tác

Nếu API có thể phục vụ dữ liệu cũ, hãy xem xét:

~~~json
{
  "value": 120,
  "version": 47,
  "asOf": "2026-11-14T09:00:00Z",
  "freshness": "possibly_stale"
}
~~~

Đây là **mẫu payload tùy biến của ứng dụng**, không phải định dạng chuẩn của mọi NoSQL DBMS. Thông tin phiên bản/mốc dữ liệu giúp client ra quyết định đúng nếu có cơ chế xác định độ mới đáng tin.

Một UI có thể hiển thị số liệu tạm, nhưng nghiệp vụ có invariant chặt phải xác nhận tại nguồn có bảo đảm phù hợp trước commit.

## 33. Khi đọc tài liệu DBMS, nên xác định chính xác phạm vi

Trong thực tế các hệ khác nhau cung cấp những tùy chọn đọc/ghi và giao dịch khác nhau. Đừng suy từ tên sản phẩm rằng mọi thao tác có cùng bảo đảm.

### MongoDB

Khi thiết kế, cần phân biệt **read preference**, **read concern**, **write concern** và transaction options. Đọc từ secondary có thể có độ mới khác đọc từ primary; một số read concern cung cấp bảo đảm riêng trong phạm vi cụ thể.

Ví dụ câu hỏi:

~~~text
After write with chosen write concern:
  Does a read from this route observe the acknowledged write?
  Is the guarantee for one document or a transaction?
~~~

### DynamoDB

Cần phân biệt các đường đọc trên bảng chính, secondary index và các tùy chọn consistency mà dịch vụ hỗ trợ. Đặc biệt, **GSI thường được cập nhật bất đồng bộ và dùng eventually consistent reads**; không nên dùng nó làm bằng chứng duy nhất về một lần ghi vừa xảy ra khi nghiệp vụ đòi kiểm tra mạnh.

### Cassandra

Cassandra có các **consistency levels** cho read/write, replication và cơ chế **lightweight transaction** cho điều kiện compare-and-set. Một cấu hình `QUORUM` không nên được diễn giải giản đơn là serializability hay linearizability cho mọi operation.

### Redis

Trên primary, các lệnh đơn có ngữ nghĩa thực thi phù hợp với một instance; đọc từ replica có thể phản ánh replication lag. Các cơ chế `WAIT`, persistence và failover liên quan tới các bảo đảm khác nhau; không thể coi chúng là một nhãn chung “mọi read luôn mới”.

### Một nguyên tắc kiểm tra chung

Đối với từng hệ, hãy ghi:

~~~yaml
database: "Name and version"
operation: "Read / Write / CAS / Transaction"
scope: "Key / document / partition / multi-record"
readRoute: "Leader / follower / cache / index"
writeAcknowledgment: "Exact configured behavior"
consistencyGuarantee: "Specific model and conditions"
failureModel: "What failures are tolerated"
sessionRequirement: "Read-your-writes, monotonic reads, ..."
~~~

Đây là **mẫu phân tích**, không phải cấu hình cho một sản phẩm. Cấu hình dịch vụ và tính năng phiên bản cụ thể cần được đối chiếu với tài liệu của DBMS đang triển khai.

## 34. Không nhầm độ mới dữ liệu, linearizability và tốc độ response

Ba đại lượng khác nhau:

1. **Latency:** một request mất bao lâu để trả kết quả?
2. **Freshness/staleness:** kết quả cách trạng thái mới nhất theo thời gian hoặc version bao xa?
3. **Consistency guarantee:** những lịch sử quan sát nào được phép?

Một read có thể nhanh nhưng trả dữ liệu cũ. Một read có thể chậm vì chờ quorum nhưng trả dữ liệu phù hợp với bảo đảm mạnh. Một read trả kết quả “mới” trong hầu hết trường hợp vẫn có thể vi phạm linearizability trong một lịch hiếm.

### Ví dụ hai tuyến API

| Đường đọc | p95 latency giả định | Kết quả | Điều chưa được chứng minh |
| --- | ---: | --- | --- |
| Cache | 3 ms | Thường rất nhanh, có thể stale | Không thể tự suy ra linearizability |
| Read replica | 12 ms | Có thể chậm vài version | Cần xác định session guarantee |
| Coordinated read | 45 ms | Có thể hứa mức mạnh hơn | Cần đọc đúng giao thức và phạm vi |

Các con số chỉ là **minh họa giả định**, không phải benchmark một sản phẩm.

Một SLO kiểu:

> “p95 latency dưới 50 ms.”

chưa phát biểu consistency. Một yêu cầu:

> “Sau khi tạo đơn nhận success, lần đọc đơn từ cùng phiên không được trả NOT_FOUND do replication lag.”

mới là một **ràng buộc history** có thể kiểm thử.

## 35. Một bảng so sánh các mô hình theo history

| Mô hình/bảo đảm | History phải giữ điều gì? | Điều có thể vẫn được phép |
| --- | --- | --- |
| **Linearizability** | Có thứ tự tuần tự hợp lệ và tôn trọng real-time precedence | Read chồng lấn write có thể thấy cũ hoặc mới theo thứ tự hợp lệ |
| **Sequential consistency** | Có một thứ tự tuần tự chung tôn trọng program order | Đọc sau write của client khác theo thời gian thực có thể thấy cũ |
| **Causal consistency** | Những thao tác có phụ thuộc nhân quả được quan sát theo thứ tự phù hợp | Ghi độc lập có thể được nhìn theo thứ tự khác nhau |
| **Eventual consistency** | Khi đủ điều kiện và ngừng ghi, các bản sao cuối cùng hội tụ | Đọc cũ, đi lùi trong giai đoạn đồng bộ nếu không có bảo đảm khác |
| **Read-your-writes** | Một session thấy tác động các ghi đã hoàn tất của chính nó | Session khác vẫn có thể đọc cũ |
| **Monotonic reads** | Một session không quan sát dữ liệu đi lùi | Không nhất thiết thấy write mới của client khác ngay |
| **Bounded staleness** | Giá trị không cũ hơn giới hạn đã định nghĩa theo thời gian/version | Vẫn có thể không phải giá trị mới nhất tức thời |
| **Serializable transactions** | Các transaction có thể được sắp như một lịch tuần tự hợp lệ | Có thể không ràng buộc real-time precedence nếu không strict |
| **Strict serializability** | Serializable cộng ràng buộc thứ tự thời gian thực của transaction | Transaction concurrent vẫn có thể có thứ tự hợp lệ khác nhau |

**Đọc bảng theo phạm vi:** không phải mọi dòng đều nói về cùng loại đối tượng. Session guarantees, transactional isolation và single-key consistency là những **chiều khác nhau**; một hệ có thể kết hợp nhiều điều kiện.

## 36. Bài tập thực hành

### Bài 1 — Viết history từ câu chuyện

Khóa `x` ban đầu bằng 0. Client A gọi `write(x,1)`, nhận `OK`. Sau đó client B gọi `read(x)` và nhận 0.

Hãy ghi history bằng invocation/response, chỉ ra real-time precedence và kết luận history có linearizable không.

**Gợi ý:** write A hoàn thành trước read B bắt đầu; không có write khác nên không có thứ tự tuyến tính hợp lệ cho read 0.

### Bài 2 — Chồng lấn khác không chồng lấn

Cho:

~~~text
W: [10, 40], write x=1
R: [20, 30], read x→0
~~~

Vì sao đọc 0 **có thể** linearizable? Nếu đổi R thành `[50,60]` mà vẫn đọc 0, kết luận thay đổi thế nào?

**Gợi ý:** ở lịch đầu có thể đặt R trước W; ở lịch sau, W đã hoàn thành trước R.

### Bài 3 — Sequential nhưng không linearizable

Hãy xây một thứ tự tuần tự hợp lệ cho history:

~~~text
A: write(x,1) → OK
B: read(x) → 0
~~~

trong đó B gọi read sau ACK của A, nhưng A/B là hai client khác nhau, mỗi client chỉ có một thao tác.

**Gợi ý:** đặt read B trước write A trong thứ tự sequential giả định; phân tích vì sao điều đó không thỏa real-time order.

### Bài 4 — Program order

Một client:

~~~text
write(x,1) → OK
read(x) → 0
~~~

Không có write khác. History có sequential consistency không? Vì sao?

**Gợi ý:** thứ tự chương trình yêu cầu write trước read; read 0 không thể giải thích hợp lệ.

### Bài 5 — Quan hệ nhân quả

Client A viết bài báo, rồi Client B đọc thấy bài và tạo bình luận. Client C đọc thấy bình luận nhưng đọc bài báo lại nhận NOT_FOUND.

Hãy vẽ causal edges và xác định điều kiện nào khiến history này vi phạm causal consistency.

**Gợi ý:** viết bài → B đọc bài → B viết bình luận → C đọc bình luận; cần bảo đảm context nhân quả của phiên C và giả định không có xóa bài hợp lệ.

### Bài 6 — Ghi độc lập và thứ tự khác nhau

Hai client độc lập ghi `x=1` và `y=1`. C đọc `x=1,y=0`; D đọc `y=1,x=0` trong các session tuần tự như ví dụ ở bài.

Giải thích vì sao không có một thứ tự tuần tự chung, nhưng hệ causal có thể chấp nhận nếu hai write độc lập.

**Gợi ý:** C buộc `write x` trước `write y`; D buộc thứ tự ngược lại.

### Bài 7 — Eventual consistency và hội tụ

Replica R giữ `x=0` trong 2 giây sau khi primary đã ACK `x=1`; sau đó R nhận update và trả `1`. Điều này có chứng minh hệ vi phạm eventual consistency không? Có vi phạm linearizability nếu đọc cũ sau ACK được hứa linearizable không?

**Gợi ý:** đọc cũ tạm thời có thể phù hợp eventual; nhưng vi phạm đường đọc linearizable theo ví dụ đơn key.

### Bài 8 — Monotonic reads

Ứng dụng đọc trạng thái đơn `SHIPPED` ở replica A, sau đó chuyển sang replica B và thấy `PAID`. Không có state transition hợp lệ nào từ SHIPPED về PAID.

Điều gì bị vi phạm nếu ứng dụng hứa monotonic reads? Hãy đề xuất một cơ chế session version.

**Gợi ý:** ghi nhớ version đã quan sát và chỉ đọc replica đạt ít nhất version đó hoặc chuyển sang đường đọc mạnh hơn.

### Bài 9 — Read-your-writes

Sau khi người dùng cập nhật tên hiển thị, màn hình tiếp theo vẫn hiện tên cũ từ search index. Hãy mô tả hai cách bảo đảm read-your-writes mà không cần giả định mọi user đều phải đọc primary.

**Gợi ý:** session token/read watermark, sticky routing/read-after-write path hoặc UI sử dụng kết quả đã xác nhận kết hợp refresh đúng nguồn.

### Bài 10 — Quorum

Với `N=5`, `W=3`, `R=3`, hãy kiểm tra `R+W>N`. Vì sao điều kiện đó chưa đủ chứng minh mọi lịch read/write linearizable?

**Gợi ý:** write concurrency, conflict version order, membership, sloppy quorum, lỗi mạng và cơ chế read repair.

### Bài 11 — Per-key và multi-key

Chuyển 200 từ A sang B bằng hai write độc lập. Một reader thấy A mới nhưng B cũ. Vì sao điều này không nhất thiết vi phạm **per-key linearizability**, nhưng lại sai với lời hứa “chuyển tiền nguyên tử”?

**Gợi ý:** nhất quán của mỗi key khác atomicity/snapshot trên cặp key.

### Bài 12 — Unknown outcome

Client gọi `write(x,1)`, timeout; một client khác đọc `x=1`. Có thể khẳng định write A đã được ACK hoặc transaction đã trả success cho A không?

**Gợi ý:** timeout không có nghĩa rollback hoặc ACK; cần request ID, biết writer nào tác động và phân biệt kết quả quan sát.

### Bài 13 — Chọn consistency cho nghiệp vụ

Xét:

1. Danh sách sản phẩm được phép cũ vài giây.
2. Người dùng vừa tạo đơn phải đọc thấy đơn của chính mình.
3. Cấp voucher tổng cộng không quá 100 lượt.
4. Dashboard tổng đơn theo giờ, cập nhật trễ tối đa theo SLO.

Hãy nêu ràng buộc history tối thiểu và đường đọc/ghi cần cân nhắc cho từng trường hợp.

**Gợi ý:** eventual/bounded staleness; RYW; conditional atomic update hoặc transaction; read model với watermark/lag monitor.

### Bài 14 — Phân loại nguyên nhân

Một hệ có linearizable reads trên primary nhưng API đọc cache và trả giá cũ sau write. Lỗi nằm ở DBMS hay ở **consistency contract của API**?

**Gợi ý:** có thể DBMS vẫn đúng; API phải xác định và thực thi freshness/invalidation của cache.

### Bài 15 — Lịch kiểm thử

Hãy thiết kế một log định dạng JSON cho `write(x,1)` và `read(x)`, gồm client ID, operation ID, thời điểm gọi/trả, giá trị trả, route và request ID. Vì sao cần cả thời điểm bắt đầu và kết thúc, không chỉ timestamp “log entry”?

**Gợi ý:** để biết hai thao tác có chồng lấn hay không; phải tính tới đồng hồ giữa các máy.

### Bài 16 — Tuyên bố consistency mơ hồ

Tài liệu dự án ghi:

> “Database NoSQL của chúng ta strong consistent, còn cache eventually consistent.”

Hãy viết lại thành các câu **có thể kiểm chứng**, xác định phạm vi read/write, phiên, ack, stale reads, TTL/index lag và thời điểm nào nghiệp vụ bắt buộc phải kiểm tra nguồn.

**Gợi ý:** viết theo từng endpoint/access pattern, không gắn một nhãn chung cho mọi đường dữ liệu.

## 37. Một phương pháp 6 bước để đánh giá history

Khi gặp câu hỏi “lịch đọc/ghi này có đúng không?”, hãy làm theo thứ tự:

### Bước 1 — Nêu đối tượng và trạng thái ban đầu

~~~text
Object: key x
Initial value: 0
Operations: read(x), write(x,v)
~~~

Không bỏ qua trạng thái ban đầu; nếu không biết `x` bắt đầu ở đâu, việc đánh giá một read 0 có thể thiếu dữ kiện.

### Bước 2 — Ghi đầy đủ invocation và response

~~~text
A: inv write(x,1)
A: ret OK
B: inv read(x)
B: ret 0
~~~

Nếu có timeout, giữ trạng thái pending/unknown thay vì giả định thành công hoặc thất bại.

### Bước 3 — Xác định quan hệ thứ tự phải giữ

~~~text
Program order: trong mỗi client
Real-time order: thao tác kết thúc trước thao tác khác bắt đầu
Causal order: phụ thuộc từ write/read và thứ tự chương trình
~~~

Không dùng thứ tự timestamp toàn cụm nếu chưa có cơ sở đáng tin.

### Bước 4 — Áp đặc tả thao tác

Với thanh ghi:

~~~text
read trả giá trị của write mới nhất trong
thứ tự tuần tự đang được xét, hoặc giá trị ban đầu
nếu chưa có write phù hợp.
~~~

Với counter hoặc transaction, đặc tả có thể khác; phải dùng semantics đúng của operation.

### Bước 5 — Thử tìm lịch hợp lệ theo mô hình

- Với **linearizability**, tìm một thứ tự tuần tự hợp lệ **và** tôn trọng real-time precedence.
- Với **sequential consistency**, tìm một thứ tự tuần tự chung tôn trọng program order.
- Với **causal consistency**, kiểm tra sự bảo toàn phụ thuộc nhân quả và điều kiện quan sát của phiên.
- Với **eventual consistency**, xét khả năng đọc cũ trong giai đoạn đồng bộ và yêu cầu hội tụ khi đủ điều kiện.

### Bước 6 — Kết luận đúng phạm vi

Thay vì:

> “Database này sai.”

hãy ghi:

> “Trong lịch H, write trên khóa x đã ACK trước khi read từ route R được gọi, nhưng read trả giá trị cũ. Nếu route R có cam kết linearizable reads cho x và không có write hợp lệ khác, đây là một phản ví dụ vi phạm.”

Cách kết luận này nêu rõ **history, mô hình, phạm vi, giả định và bằng chứng**.

## 38. Checklist thiết kế một consistency contract

Một hệ thống có thể ghi rõ:

~~~yaml
feature: "Order detail after create"
sourceOfTruth: "Orders database"
operations:
  - "createOrder(requestId)"
  - "getOrder(orderId)"
scope:
  write: "One authoritative order aggregate"
  read: "Order by primary key"
historyGuarantees:
  - "A user who receives create success can read own order"
  - "Reads in one session must not regress behind observed version"
writeAcknowledgment:
  meaning: "Defined commit/durability condition"
readRouting:
  default: "Replica or read model when fresh enough"
  afterWrite: "Route with minimum version watermark"
staleness:
  otherUsers: "Define whether stale data is acceptable"
  maxDelay: "SLO if guaranteed/monitored"
failures:
  ifRequiredVersionUnavailable: "Wait, reroute or return explicit error"
  unknownCommitOutcome: "Resolve using stable requestId"
authorization:
  scope: "Authenticated tenant and resource ownership"
verification:
  - "Write success followed by immediate read"
  - "Switch replica between consecutive session reads"
  - "Replication lag during failover"
  - "Network partition with read route fallback"
  - "Retry after lost response"
metrics:
  - "Observed version versus required watermark"
  - "Replica/index lag"
  - "Stale reads and reroutes"
  - "p95/p99 latency under failure"
~~~

Đây là **mẫu tài liệu thiết kế**, không phải cấu hình của một DBMS cụ thể. Các yêu cầu phải được ánh xạ thành API, consistency level, read/write concern, session token hoặc transaction tương ứng với hệ được dùng.

## 39. Những nhầm lẫn thường gặp

| Nhận định dễ sai | Cách hiểu đúng |
| --- | --- |
| “Consistency nghĩa là mọi read luôn thấy mới nhất.” | Đó chỉ gần một số bảo đảm mạnh; từng mô hình cho phép tập history khác nhau. |
| “Write gọi trước read nên read phải thấy write.” | Cần xem write **đã hoàn thành** chưa và hai operation có chồng lấn không. |
| “Linearizable read đang chồng write phải thấy giá trị mới.” | Có thể thấy cũ hoặc mới nếu tồn tại thứ tự tuyến tính hợp lệ. |
| “Sequential consistency giống linearizability.” | Sequential không bắt buộc real-time order xuyên client. |
| “Causal consistency buộc mọi client thấy mọi write cùng thứ tự.” | Chỉ cần giữ phụ thuộc nhân quả; write độc lập có thể khác thứ tự. |
| “Eventual consistency cho phép trả giá trị tùy ý.” | Vẫn phải có semantics và cơ chế hội tụ hợp lệ; không đồng nghĩa dữ liệu bịa. |
| “Eventual nghĩa chắc chắn hội tụ sau đúng 1 giây.” | Nếu không có bounded staleness/SLO riêng, không có hạn thời gian cố định. |
| “Quorum R+W>N tự động tạo linearizability.” | Cần giao thức, versioning và fault assumptions phù hợp. |
| “Một key linearizable thì giao dịch chuyển tiền hai key nguyên tử.” | Cần transaction/aggregate bảo vệ đa key. |
| “ACID Consistency là eventual/strong consistency.” | ACID C nói về invariant, khác mô hình quan sát phân tán. |
| “Serializable luôn tôn trọng thời gian thực.” | Strict serializability thêm ràng buộc real-time. |
| “Đọc một giá trị mới rồi cũ vẫn là monotonic reads.” | Nếu không có ghi hợp lệ làm quay lại, đó là read regression. |
| “Leader strong nên mọi API đều strong.” | Cache, follower, search index và route API có bảo đảm riêng. |
| “Timeout của write nghĩa là write thất bại.” | Có thể đã commit nhưng ACK mất; cần xử lý unknown outcome. |
| “Một test không thấy stale read là bằng chứng hệ linearizable.” | Một history hợp lệ không chứng minh mọi lịch hệ có thể tạo đều hợp lệ. |
| “Dùng timestamp giữa các máy là biết chính xác thứ tự.” | Clock skew, network delay và timestamp semantics có thể gây nhầm. |

## 40. Tổng kết

Khi nói **“nhất quán là tập các lịch sử đọc/ghi được phép quan sát”**, ta đang thay cách nghĩ mơ hồ “dữ liệu có mới không?” bằng một đặc tả **có thể lập luận và kiểm thử**.

Các ý quan trọng:

1. **History gồm invocation và response của từng thao tác.** Muốn phân tích consistency phải biết client nào gọi gì, lúc nào hoàn tất và kết quả đọc/ghi ra sao.
2. **Thứ tự là trọng tâm.** Program order, real-time precedence và causal order tạo ra những ràng buộc khác nhau cho các mô hình.
3. **Linearizability đòi thứ tự tuần tự hợp lệ tôn trọng real time.** Read bắt đầu sau một write đã ACK không được thấy trạng thái trước write khi không có ghi hợp lệ khác làm thay đổi trạng thái.
4. **Sequential consistency chỉ đòi một thứ tự tuần tự chung tôn trọng program order.** Nó có thể cho phép một read từ client khác trả dữ liệu cũ dù write đã hoàn thành trước đó theo thời gian thực.
5. **Causal consistency giữ đúng những phụ thuộc nhân quả**, nhưng không bắt mọi client thống nhất thứ tự cho các write thực sự độc lập.
6. **Eventual consistency cho phép replica tạm khác nhau và yêu cầu hội tụ khi có điều kiện tiến triển thích hợp.** Nó không tự hứa read-your-writes, monotonic reads hay một thời hạn hội tụ cố định.
7. **Bảo đảm cần gắn với phạm vi.** Per-key linearizability, transaction serializability, session guarantees, replica freshness và invariant nghiệp vụ là các chiều liên quan nhưng không thay thế nhau.
8. **Kiểm tra bằng phản ví dụ lịch sử.** Một read cũ chỉ chứng minh vi phạm khi nó mâu thuẫn với mô hình được hứa trong một lịch đầy đủ; một đợt test thành công chưa chứng minh toàn hệ luôn đúng.

**Nguyên tắc thực hành:** trước khi viết “strong consistency” hay “eventual consistency” trong tài liệu kiến trúc, hãy viết ít nhất **một lịch sử đọc/ghi được phép** và **một lịch sử phải bị cấm** cho đúng thao tác và đường truy cập mà ứng dụng dùng. Nếu nhóm không thống nhất được hai lịch đó, nhóm vẫn chưa phát biểu đủ rõ consistency contract của hệ thống.
