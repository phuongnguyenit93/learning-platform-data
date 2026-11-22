# Phép rút gọn song song và yêu cầu tính kết hợp

**Phép rút gọn song song (parallel reduction)** biến một dãy phần tử thành **một kết quả tổng hợp** bằng cách cho nhiều tác vụ xử lý các phần dữ liệu độc lập rồi **kết hợp các kết quả trung gian**. Các ví dụ gồm tổng, tích, giá trị nhỏ nhất/lớn nhất, đếm số phần tử, tổng hợp thống kê và nhân một dãy ma trận theo đúng thứ tự.

Điều kiện toán học quan trọng nhất để **tự do thay đổi cách đặt ngoặc** khi rút gọn là **tính kết hợp (associativity)** của phép toán. Khi dùng các kết quả cục bộ bắt đầu từ một giá trị khởi tạo, ta còn cần **phần tử đơn vị (identity)** phù hợp. Nếu thuật toán được phép **đổi thứ tự các phần tử**, chỉ tính kết hợp **chưa đủ**: phép toán còn cần **tính giao hoán (commutativity)** hoặc hệ thống phải giữ thứ tự ban đầu. Với số thực dấu phẩy động, ngay cả phép cộng cũng **không hoàn toàn kết hợp** theo ngữ nghĩa IEEE 754 vì phép làm tròn.

Bài thuộc nhóm **Thuật toán song song** của Computer Science Algorithms, với đề bài **“Phép rút gọn song song và yêu cầu tính kết hợp”**. Nội dung đi từ mô hình reduce tuần tự và cây rút gọn, nêu điều kiện chính xác để đổi nhóm hoặc đổi thứ tự, chứng minh tính đúng, phân biệt `reduce`/`scan`/`collect`, phân tích work–span và chi phí fork/join, minh họa với Java 17+ và những phản ví dụ dễ sai. Phần cuối có bộ kiểm thử thuộc tính và bài tập có lời giải.

## 1. Rút gọn nghĩa là gì?

Cho dãy có thứ tự:

\[
x_0,x_1,\ldots,x_{n-1}
\]

và phép toán nhị phân \(\otimes\). Một phép rút gọn thường có dạng:

\[
x_0\otimes x_1\otimes\cdots\otimes x_{n-1}.
\]

Nếu có phần tử đơn vị \(e\), rút gọn của dãy rỗng được định nghĩa là \(e\).

**Ví dụ:**

| Dữ liệu | Phép toán | Phần tử đơn vị | Kết quả |
| --- | --- | --- | --- |
| [3,−2,7,4] | Cộng chính xác | 0 | 12 |
| [2,3,4] | Nhân chính xác | 1 | 24 |
| ["An"," ","Binh","!"] | Nối chuỗi theo thứ tự | Chuỗi rỗng | "An Binh!" |
| [5,2,7] | Minimum | \(+\infty\) theo miền phù hợp | 2 |
| [5,2,7] | Maximum | \(-\infty\) theo miền phù hợp | 7 |
| Các bản ghi | Hợp nhất (count,sum,min,max) | Thống kê rỗng | Một bản ghi thống kê |

Có thể rút gọn dữ liệu bằng nhiều luồng, nhiều lõi CPU, nhiều nút phân tán hay GPU. Tuy nhiên **chia việc được** chưa đồng nghĩa **gộp kết quả được đúng**. Phép toán gộp phải thỏa những điều kiện cụ thể.

### Tại sao cần nhìn từ góc đại số?

Một đoạn dữ liệu có thể được xử lý thành một kết quả tạm \(a\), đoạn tiếp theo thành \(b\). Để hợp nhất hai đoạn, ta cần phép `combine(a,b)` cho ra đúng kết quả của toàn bộ dãy ghép lại.

Nếu phép toán này sai khi thay đổi vị trí đặt ngoặc, kết quả sẽ phụ thuộc lịch chạy của các tác vụ hoặc hình dạng cây rút gọn. Khi đó có thể cho ra giá trị khác kết quả tuần tự, dù không có race condition.

## 2. Rút gọn tuần tự (sequential fold)

Với phép toán \(\otimes\) và giá trị khởi đầu \(e\), vòng lặp trái là:

~~~text
acc = e
for x in input in original order:
    acc = acc ⊗ x
return acc
~~~

Nó tương ứng với:

\[
(((e\otimes x_0)\otimes x_1)\otimes\cdots)
\otimes x_{n-1}.
\]

Ví dụ cộng các số 3,−2,7,4 từ e=0:

\[
((((0+3)+(-2))+7)+4)=12.
\]

Độ phức tạp với phép gộp O(1):

- **Work**: \(\Theta(n)\) phép gộp.
- **Span/critical path**: \(\Theta(n)\), vì phép tính tiếp theo phải đợi accumulator trước.
- **Bộ nhớ phụ**: O(1) nếu accumulator là giá trị kích thước cố định.

Cách này dễ hiểu, dễ debug và có thể nhanh hơn parallel reduction đối với dữ liệu nhỏ vì **không phải tạo task, fork, join, đồng bộ và chia khối**.

## 3. Rút gọn theo cây (tree reduction)

Chia dãy thành **hai đoạn liên tiếp**:

\[
X=L\mathbin{\|}R.
\]

Rút gọn L và R **độc lập**, rồi kết hợp kết quả:

\[
\operatorname{reduce}(X)=
\operatorname{reduce}(L)\otimes\operatorname{reduce}(R).
\]

Hai nửa có thể chạy trên hai worker khác nhau. Đệ quy tới đoạn ngắn rồi thực hiện fold tuần tự cho mỗi đoạn lá.

Ví dụ với dữ liệu `[3,−2,7,4]` và phép cộng:

~~~text
             12
           /    \
          1      11
         / \    /  \
        3  -2  7    4
~~~

Dạng toán học:

\[
(3+(-2))+(7+4)=1+11=12.
\]

Cách đặt ngoặc đã khác vòng lặp tuần tự, nhưng phép cộng số nguyên chính xác **có tính kết hợp** nên kết quả không đổi.

### Giữ thứ tự trái–phải

Trong cây trên, **nửa trái phải đứng trước nửa phải** trong phép gộp. Nếu một task phải hoàn thành sau, việc nó **chạy chậm hơn không cho phép** đổi `combine(right,left)` thành công thức chung.

Khi cố định thứ tự `combine(leftResult,rightResult)`, ta có thể hỗ trợ cả phép toán **kết hợp nhưng không giao hoán**, ví dụ nối chuỗi hoặc nhân ma trận.

### Rút gọn không phải sắp xếp

Rút gọn không thay đổi vị trí các phần tử trong dãy, cũng không trả một dãy đã sắp. Nó tính ra **một kết quả**. Việc đưa dữ liệu vào các task không có nghĩa ta được đảo thứ tự nếu phép gộp không giao hoán.

## 4. Tính kết hợp (associativity)

Một phép toán \(\otimes\) là **kết hợp** trên miền S khi:

\[
\forall a,b,c\in S:\quad
(a\otimes b)\otimes c
=a\otimes(b\otimes c).
\]

Đây là điều kiện cho phép **thay đổi vị trí ngoặc**.

Với dãy dài, có thể chuyển từ fold trái sang cây nhị phân cân bằng thông qua các phép đổi ngoặc liên tiếp, nhưng vẫn giữ thứ tự các phần tử.

### Phép toán có tính kết hợp

- **Cộng số nguyên toán học**: \((a+b)+c=a+(b+c)\).
- **Nhân số nguyên toán học**: \((ab)c=a(bc)\).
- **Min/max** trên một miền được định nghĩa nhất quán.
- **Nối chuỗi**: `("a"+"b")+"c" == "a"+("b"+"c")`; thứ tự ký tự không đổi.
- **Nhân ma trận** cùng kích thước phù hợp: \((AB)C=A(BC)\), nhưng thường \(AB\ne BA\).
- **Hợp nhất các tập hợp** bằng union: kết hợp, giao hoán, có tập rỗng làm đơn vị.
- **Tổng hợp (count,sum,min,max)** bằng phép gộp các thành phần đúng cách.

### Các phép toán không kết hợp

**Phép trừ:**

\[
(20-5)-2=13,\quad
20-(5-2)=17.
\]

**Phép chia:**

\[
(24/6)/2=2,\quad
24/(6/2)=8.
\]

**Trung bình cộng của hai số:**

\[
\operatorname{avg}(\operatorname{avg}(1,3),9)=5.5,
\]

nhưng:

\[
\operatorname{avg}(1,\operatorname{avg}(3,9))=3.5.
\]

Vì phép `avg(a,b)=(a+b)/2` không kết hợp, **không thể** tùy ý lấy “trung bình của hai trung bình” nếu hai nhóm có quy mô khác nhau.

**Cách đúng** là mỗi đoạn trả về `(sum,count)`; gộp bằng:

\[
(s_1,c_1)\oplus(s_2,c_2)
=(s_1+s_2,c_1+c_2),
\]

rồi cuối cùng tính `mean=sum/count` nếu count>0.

## 5. Phần tử đơn vị (identity) và cấu trúc monoid

Một giá trị \(e\in S\) là **đơn vị hai phía** của \(\otimes\) nếu:

\[
e\otimes x=x\otimes e=x
\quad\forall x\in S.
\]

Nếu miền S đóng với phép toán, phép toán kết hợp và có đơn vị hai phía, cặp \((S,\otimes,e)\) là một **monoid**.

Monoid đặc biệt hữu ích cho parallel reduction vì mỗi đoạn con có thể trả về identity khi rỗng. Gộp các đoạn không bị thay đổi bởi những đoạn rỗng.

| Phép toán | Đơn vị hợp lệ | Lý do |
| --- | --- | --- |
| Cộng | 0 | 0+x=x+0=x |
| Nhân | 1 | 1×x=x×1=x |
| Nối chuỗi | "" | ""+s=s+""=s |
| Min | \(+\infty\) hoặc sentinel an toàn | min(+∞,x)=x |
| Max | \(-\infty\) hoặc sentinel an toàn | max(−∞,x)=x |
| Hợp các tập | Tập rỗng | ∅∪X=X∪∅=X |
| Nhân ma trận vuông | Ma trận đơn vị I | IA=AI=A |
| Thống kê đếm/tổng | (count=0,sum=0) | Cộng từng thành phần |

**Lưu ý:** identity của phép nhân **không phải 0**. Nếu mỗi task khởi tạo tích từ 0, mọi tích cục bộ sẽ thành 0, bất kể input.

### Ví dụ empty reduction

- Reduce tổng của [] → 0.
- Reduce tích của [] → 1.
- Reduce nối chuỗi của [] → "".
- Reduce thống kê của [] → count=0, sum=0, min/max **không có giá trị thực tế**.

Với min trên `long` trong Java có thể dùng `Long.MAX_VALUE` làm sentinel, nhưng khi không có phần tử, nên kèm **count=0** để biểu thị rõ “min không tồn tại” thay vì trưng sentinel như một kết quả nghiệp vụ.

### Tại sao phải cần identity ở cả bên trái và bên phải?

Trong chia để trị, một đoạn con có thể rỗng. Khi hợp nhất kết quả:

\[
\operatorname{reduce}(L)\otimes
\operatorname{reduce}(\varnothing)
\]

phải bằng reduce(L); ở chiều ngược lại cũng vậy. Một giá trị chỉ là **đơn vị trái** chưa chắc đủ cho mọi cách nhóm và ghép.

## 6. Tính giao hoán (commutativity) khác tính kết hợp

Phép toán giao hoán nếu:

\[
a\otimes b=b\otimes a.
\]

Hai thuộc tính **độc lập về ý nghĩa**:

- **Kết hợp**: đổi **ngoặc**.
- **Giao hoán**: đổi **vị trí phần tử**.

Phép cộng số nguyên chính xác vừa kết hợp vừa giao hoán. **Nối chuỗi** kết hợp nhưng **không giao hoán**:

`"ab"+"CD" = "abCD"`, trong khi `"CD"+"ab" = "CDab"`.

**Nhân ma trận** kết hợp nhưng không giao hoán.

### Quy tắc thiết kế song song

Nếu bạn chỉ chia **các đoạn liên tiếp** và khi ghép luôn giữ kết quả **trái trước, phải sau**, **associativity + identity** là đủ để đổi ngoặc mà vẫn giữ kết quả.

Nếu các worker có thể trả về theo bất kỳ thứ tự và hệ thống gộp “ai xong trước gộp trước”, bạn cần:

1. Phép toán vừa kết hợp vừa giao hoán; **hoặc**
2. Một cơ chế bảo toàn **encounter order**, số thứ tự khối và thứ tự gộp.

**Ví dụ:** ghép các chuỗi `["An"," ","Binh","!"]`. Hình dạng cây cân bằng hợp lệ trả `"An Binh!"`. Nếu gộp nửa phải trước nửa trái, kết quả có thể là `"Binh!An "`, dù `String::concat` có tính kết hợp.

## 7. Chứng minh parallel reduction đúng

Giả sử \((S,\otimes,e)\) là monoid và thuật toán chia dãy thành **những đoạn liên tiếp**, luôn gọi:

\[
\operatorname{combine}(
\operatorname{reduce}(L),
\operatorname{reduce}(R))
\]

theo đúng thứ tự L rồi R.

**Cơ sở:** đoạn rỗng trả e; đoạn một phần tử x có fold `e⊗x=x`, nên đúng.

**Bước quy nạp:** giả sử mỗi nửa L và R được rút gọn đúng thành kết quả của các phần tử trong nửa đó **theo thứ tự ban đầu**. Do kết hợp, ta có thể bỏ đi hoặc đổi ngoặc giữa kết quả của hai nửa mà không thay đổi giá trị của dãy ghép L∥R. Gộp trái rồi phải cho đúng kết quả toàn đoạn.

**Kết luận:** với mọi kích thước dãy, mọi cách chia đoạn liên tiếp và ghép đúng trái–phải, parallel reduction cho cùng kết quả đại số như fold tuần tự.

**Giới hạn của chứng minh:** nó giả định phép toán thực sự kết hợp, identity đúng, xử lý phần tử không làm hỏng trạng thái dùng chung, và các lời gọi `combine` hoạt động như một hàm theo giá trị. Với phép toán có side effect hoặc số thực làm tròn, phải phân tích lại.

## 8. Phép trừ: kết quả thay đổi dù không có race

Xét:

`[20,5,2,1]` và identity giả định 0 với phép trừ `a−b`.

Fold tuần tự:

\[
(((0-20)-5)-2)-1=-28.
\]

Một cây chia thành hai lá, mỗi lá tự bắt đầu từ 0:

- Lá trái [20,5] → `(0−20)−5=−25`.
- Lá phải [2,1] → `(0−2)−1=−3`.
- Ghép hai kết quả → `−25−(−3)=−22`.

Hai kết quả **−28 và −22 khác nhau**, mặc dù các task chỉ đọc input và không chia sẻ accumulator.

Thực tế 0 **không phải đơn vị hai phía của phép trừ** vì `0−x≠x` nói chung. Phép trừ cũng không kết hợp, nên ví dụ vi phạm **cả hai** tiền đề của monoid.

**Không sửa bằng cách chỉ đặt threshold=1**: khi đổi cây hoặc đổi cách chia, kết quả vẫn không được bảo đảm. Nếu thật sự cần một biểu thức “trừ tuần tự”, hãy giữ thứ tự và cách ngoặc; nếu nghiệp vụ là `x₀−x₁−⋯`, có thể biểu diễn bằng tổng với dấu phù hợp sau khi định nghĩa chính xác phép biến đổi, thay vì đem phép trừ thô đi reduce tùy ý.

## 9. Số thực IEEE 754: cộng cũng có thể không kết hợp

Trên số thực toán học, phép cộng kết hợp. Nhưng Java `double` thực hiện các phép làm tròn và không bảo đảm:

\[
(a+b)+c=a+(b+c)
\]

cho mọi a,b,c dưới IEEE 754.

Ví dụ:

`a=1e16`, `b=−1e16`, `c=1.0`.

Theo cách nhóm:

\[
(1e16+(-1e16))+1=1.0.
\]

Nhưng:

\[
1e16+((-1e16)+1)=0.0,
\]

vì `(-1e16)+1` bị làm tròn trở lại gần `−1e16` ở độ chính xác double.

Vì vậy:

- Fold tuần tự [1e16,−1e16,1.0] với accumulator 0.0 trả **1.0**.
- Cây chia nửa trái [1e16], nửa phải [−1e16,1.0] có thể trả **0.0**.

Đây là **khác biệt số học có hệ thống**, không phải race condition. Dùng `Double::sum` không tự biến double thành monoid cộng chính xác.

### Cách ứng xử thực tế

1. Chấp nhận sai số làm tròn có kiểm soát và kiểm thử với tolerance hợp lý cho miền dữ liệu.
2. Nếu yêu cầu **kết quả byte-for-byte tái lập**, cố định hình dạng cây, thứ tự dữ liệu, thuật toán và môi trường số học; đừng phụ thuộc một thứ tự gộp không được bảo đảm.
3. Với số tiền hoặc số nguyên cần cộng chính xác, dùng `BigInteger`/`BigDecimal` với chính sách scale và MathContext rõ ràng, phù hợp nghiệp vụ.
4. Với khoa học số, cân nhắc pairwise summation, compensated summation/Kahan, binned/superaccumulator, nhưng không khẳng định chúng luôn giống fold trái hoặc làm phép cộng double trở thành kết hợp.
5. Lưu ý `NaN`, `+∞`, `−∞` và `+0.0/−0.0` có thể làm định nghĩa min/max, equality và identity phức tạp; phát biểu rõ miền input.

**Một kết quả khác không nhất thiết là “lỗi đồng bộ”; một kết quả giống nhau trên vài test cũng không chứng minh associativity.**

## 10. Tổng số nguyên: tràn số và ngữ nghĩa mong muốn

Trong toán học, cộng các số nguyên là kết hợp. Với Java `long`, phép cộng có thể **tràn và vòng lại theo hai bù (two's complement)**. Phép cộng modulo \(2^{64}\) vẫn kết hợp, nên các cách nhóm thường cho cùng **bit pattern**, nhưng kết quả có thể **không còn là tổng toán học đúng**.

Ví dụ:

`Long.MAX_VALUE + 1` không cho số nguyên toán học \(2^{63}\); nó vòng thành `Long.MIN_VALUE`.

Nếu nghiệp vụ cần tổng chính xác, dùng `BigInteger::add` (như trong demo) hoặc chứng minh tổng nằm trong miền long. Nếu dùng `Math.addExact`, một cây khác có thể kiểm tra overflow ở các bước trung gian khác, dẫn đến việc có nhánh ném ngoại lệ trong khi cách nhóm khác có thể có tổng cuối hợp lệ; hãy quy định rõ chính sách overflow.

**Tính kết hợp theo một đại số cụ thể** không thay thế việc kiểm tra yêu cầu chính xác của sản phẩm.

## 11. Hàm kết hợp phải thuần (pure) và thread-safe

Một phép `combine(a,b)` lý tưởng:

- Không sửa `a`, `b` hoặc dữ liệu input.
- Không chạm trạng thái dùng chung mà không đồng bộ.
- Trả kết quả chỉ phụ thuộc hai đối số.
- Tuân thủ associativity và identity.
- Có cùng ý nghĩa khi gọi trên thread khác nhau.

**Hợp lệ:** `BigInteger::add`, `String::concat`, record `Summary.merge` không sửa đối số, phép nhân ma trận bất biến trong ví dụ nhỏ.

**Không an toàn khi dùng như reduce accumulator chia sẻ:** một `ArrayList` mutable được tạo làm identity rồi `add` trực tiếp trong accumulator; nhiều task có thể cùng sửa object ấy. Dù `List.addAll` có vẻ kết hợp về mặt ý tưởng, một **object mutable dùng chung** không phải một giá trị đơn vị độc lập cho mỗi nhánh.

Nếu cần gom tập hợp/list lớn, cân nhắc `Collector` với supplier tạo container **riêng cho mỗi worker**, accumulator và combiner có hợp đồng phù hợp; không dùng một container identity duy nhất cho mọi nhánh rồi mặc định nó thread-safe.

### Side effect và external I/O

Nếu `combine` gửi email, ghi file hay cập nhật counter toàn cục, thay cây reduce có thể thay **số lần hoặc thứ tự hiệu ứng**. Ngay cả khi giá trị trả về đúng, hệ thống có thể sai nghiệp vụ. Nên tách **tính tổng hợp thuần** khỏi **thực thi side effects**.

Với hệ thống phân tán, retry và at-least-once delivery còn có thể xử lý **cùng input hai lần**. Associativity **không đồng nghĩa idempotence**: `x+x≠x` nói chung. Một bộ đếm kết hợp bằng cộng vẫn bị đếm trùng nếu sự kiện bị phát lại. Cần đảm bảo exactly-once hoặc khử trùng thích hợp.

## 12. Ví dụ kết hợp nhưng không giao hoán: nhân ma trận

Xét hai ma trận 2×2:

\[
A=\begin{pmatrix}1&2\\0&1\end{pmatrix},
\quad
B=\begin{pmatrix}1&0\\3&1\end{pmatrix}.
\]

Khi đó:

\[
AB=\begin{pmatrix}7&2\\3&1\end{pmatrix},
\quad
BA=\begin{pmatrix}1&2\\3&7\end{pmatrix}.
\]

Rõ ràng \(AB\ne BA\); phép nhân ma trận **không giao hoán**.

Nhưng nó **kết hợp**:

\[
(AB)A=A(BA)=
\begin{pmatrix}7&16\\3&7\end{pmatrix}.
\]

Vì vậy rút gọn dãy [A,B,A] có thể chia:

- Trái [A], phải [B,A] rồi nhân trái×phải; **hoặc**
- Trái [A,B], phải [A] rồi nhân trái×phải.

Cả hai trả kết quả như nhau, miễn giữ **A rồi B rồi A**. Đổi thứ tự thành [B,A,A] không được chứng minh hợp lệ.

Identity của phép nhân ma trận là:

\[
I=\begin{pmatrix}1&0\\0&1\end{pmatrix}.
\]

Bài học quan trọng: **cây chia để trị không bắt buộc phép gộp giao hoán**; yêu cầu giao hoán chỉ phát sinh nếu thuật toán hoặc API **được phép hoán vị input hoặc trộn kết quả không theo thứ tự nguồn**.

## 13. Rút gọn nhiều chỉ số thống kê cùng lúc

Một tình huống thực tế: với mỗi đoạn số, tính:

- `count`: số phần tử;
- `sum`: tổng chính xác;
- `min`: nhỏ nhất;
- `max`: lớn nhất.

Tạo kiểu dữ liệu bất biến:

`Summary(count,sum,min,max)`.

Phần tử đơn vị:

`Summary(0,0,+∞,−∞)`.

Một giá trị x được map thành:

`Summary(1,x,x,x)`.

Gộp:

\[
(c_1,s_1,m_1,M_1)\oplus(c_2,s_2,m_2,M_2)
=(c_1+c_2,s_1+s_2,\min(m_1,m_2),\max(M_1,M_2)).
\]

Cộng count và sum, min và max đều kết hợp trong miền được chọn, nên phép gộp Summary cũng kết hợp. Phép gộp có identity nói trên; vì vậy cả Summary tạo thành monoid.

Sau rút gọn, nếu count>0 có thể tính trung bình:

\[
\mathrm{mean}=\frac{\mathrm{sum}}{\mathrm{count}}.
\]

Nếu count=0, **không chia cho 0** và **không in min/max sentinel như giá trị thật**.

Với dãy [3,−2,7,4], kết quả:

`count=4, sum=12, min=−2, max=7`.

Đây là cách đúng để tính nhiều thống kê song song thay vì liên tục tính “average of averages” mà không biết kích thước từng nhóm.

## 14. Work, span và khả năng tăng tốc

Giả sử mỗi phép gộp có chi phí O(1), input có n phần tử, mỗi lá xử lý tuần tự nhiều nhất t phần tử và cây chia cân bằng.

### Work W(n)

Tổng số thao tác phần tử vẫn là:

\[
W(n)=\Theta(n),
\]

cộng overhead tạo task và gộp nhánh cỡ \(O(n/t)\). Nếu t là hằng số dương, tổng work vẫn \(\Theta(n)\).

**Parallel reduction không làm mất việc tính tổng các phần tử**: nó thay đổi cách phân chia việc lên nhiều worker để rút đường phụ thuộc.

### Span S(n)

Lá tốn O(t), mỗi tầng cây cần một lần gộp sau khi hai nửa xong. Số tầng cỡ \(\log_2(n/t)\), nên với n>t:

\[
S(n)=O(t+\log(n/t)).
\]

Nếu t=1 và n lớn, span khoảng O(log n) thay vì O(n). Đây là phần **parallelism** có thể khai thác.

### Trên p processor

Với mô hình scheduling lý tưởng và overhead hạn chế, cận kiểu work–span/Brent gợi ý:

\[
T_p=O(W/p+S).
\]

Không có nghĩa runtime thực tế luôn bằng công thức: fork/join, cấp phát object, cache misses, scheduler, memory bandwidth, NUMA và GC có thể chiếm phần lớn thời gian.

**Work efficiency:** phép gộp dữ liệu dạng BigInteger/string/matrix có chi phí không nhất thiết O(1). Với `String::concat`, mỗi lần nối có thể sao chép dữ liệu; tổng work theo cây có thể tăng theo kích thước output. Đối với chuỗi lớn, nên dùng cấu trúc dữ liệu/collector phù hợp thay vì cộng rất nhiều chuỗi bằng một biểu thức reduce đơn giản.

### Vì sao chọn threshold?

- t quá nhỏ: tạo nhiều task, nhiều fork/join và object.
- t quá lớn: ít task, không sử dụng đủ lõi.
- Giá trị tối ưu phụ thuộc kích cỡ input, chi phí combine, số lõi và phần cứng.

Để đánh giá hiệu năng, so cùng dữ liệu, cùng JVM warmup, cùng số thread, đo thời gian xử lý và GC trên nhiều lượt; không tuyên bố “parallel luôn nhanh hơn sequential”.

## 15. Java 17: ForkJoinPool và RecursiveTask

Để nhìn rõ cây rút gọn và thứ tự ghép, chương trình **`ParallelReductionDemo.java`** tự xây `RecursiveTask<T>`:

1. Nếu đoạn [lo,hi) có độ dài ≤threshold, dùng fold tuần tự từ identity.
2. Nếu lớn hơn, chia tại mid thành [lo,mid) và [mid,hi).
3. Fork nhánh trái, tính nhánh phải, rồi join nhánh trái.
4. Trả về **`op.apply(leftResult,rightResult)`**, không đổi thứ tự theo nhánh nào hoàn thành trước.

Tất cả task chỉ đọc `List<T>` không bị thay đổi trong suốt quá trình, accumulator là giá trị **bất biến**. `ForkJoinPool` được chia sẻ cho nhiều lượt kiểm thử, thay vì tạo pool mới trong mỗi thao tác.

### Vì sao fork một nhánh và compute một nhánh?

Nếu fork cả hai nhánh cho mọi nút, số task được đưa vào hàng đợi có thể tăng mạnh. Mẫu `left.fork(); right.compute(); left.join()` cho worker hiện tại tham gia làm việc trên nhánh phải, nhánh trái có thể được thread khác đánh cắp. Điều này **không** ảnh hưởng thứ tự ghép cuối vì code luôn gọi `combine(left,right)`.

### Hai cách Java API cần phân biệt

- `Stream.reduce(identity, accumulator)`: phù hợp với phép giảm dùng toán tử kết hợp, identity đúng, không side effect.
- `Stream.collect(supplier, accumulator, combiner)`: phù hợp khi cần xây container mutable độc lập cho các tác vụ. Phải tuân thủ contract của Collector.

Đặc biệt, `parallelStream().forEach(...)` không bảo đảm thứ tự gọi trên các phần tử. Nếu cần encounter order, dùng API thích hợp hoặc tự bảo đảm thứ tự của cây; không giả định vì phép toán kết hợp nên mọi hoán vị đều đúng.

## 16. Chương trình Java 17+ hoàn chỉnh

File **`ParallelReductionDemo.java`** sau dùng chỉ thư viện JDK. Nó thực hiện:

- Reduce tổng `BigInteger` chính xác và đối chiếu fold tuần tự cùng `parallelStream().reduce`.
- Reduce tích với identity đúng là 1.
- Reduce nối chuỗi có tính kết hợp nhưng không giao hoán, giữ thứ tự nguồn.
- Reduce nhân ma trận 2×2, biểu diễn bằng record bất biến.
- Reduce Summary(count,sum,min,max) và kiểm input rỗng.
- **Cố ý** minh họa phép trừ và cộng double có thể lệch kết quả giữa fold trái và cây chia.
- Kiểm thử 500 trường hợp ngẫu nhiên với oracle độc lập cho tổng, nối chuỗi, Summary và ma trận, nhiều kích thước input và threshold.
- Từ chối threshold không hợp lệ.

### Mã nguồn

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.function.BinaryOperator;

public class ParallelReductionDemo {

    // Immutable values and pure operators are expected.
    static final class ReduceTask<T> extends RecursiveTask<T> {
        private final List<T> values;
        private final int lo, hi, threshold;
        private final T identity;
        private final BinaryOperator<T> op;

        ReduceTask(List<T> values, int lo, int hi,
                T identity, BinaryOperator<T> op,
                int threshold) {
            this.values = values;
            this.lo = lo;
            this.hi = hi;
            this.identity = identity;
            this.op = op;
            this.threshold = threshold;
        }

        @Override
        protected T compute() {
            if (hi - lo <= threshold) {
                T acc = identity;
                for (int i = lo; i < hi; i++)
                    acc = op.apply(acc, values.get(i));
                return acc;
            }

            int mid = lo + (hi - lo) / 2;
            ReduceTask<T> left = new ReduceTask<>(
                    values, lo, mid, identity, op, threshold);
            ReduceTask<T> right = new ReduceTask<>(
                    values, mid, hi, identity, op, threshold);

            left.fork();
            T rightResult = right.compute();
            T leftResult = left.join();

            // Encounter order is left before right.
            return op.apply(leftResult, rightResult);
        }
    }

    static <T> T parallelReduce(ForkJoinPool pool,
            List<T> values, T identity,
            BinaryOperator<T> op, int threshold) {
        Objects.requireNonNull(pool, "pool");
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(identity, "identity");
        Objects.requireNonNull(op, "op");
        if (threshold < 1)
            throw new IllegalArgumentException(
                    "threshold must be >= 1");

        return pool.invoke(new ReduceTask<>(
                values, 0, values.size(),
                identity, op, threshold));
    }

    static <T> T sequentialFold(List<T> values,
            T identity, BinaryOperator<T> op) {
        T acc = identity;
        for (T value : values)
            acc = op.apply(acc, value);
        return acc;
    }

    record Mat2(long a, long b, long c, long d) {
        static Mat2 identity() {
            return new Mat2(1, 0, 0, 1);
        }

        static Mat2 multiply(Mat2 x, Mat2 y) {
            return new Mat2(
                    x.a * y.a + x.b * y.c,
                    x.a * y.b + x.b * y.d,
                    x.c * y.a + x.d * y.c,
                    x.c * y.b + x.d * y.d);
        }

        String pretty() {
            return "[" + a + "," + b
                    + ";" + c + "," + d + "]";
        }
    }

    record Summary(long count, BigInteger sum,
            long min, long max) {
        static Summary empty() {
            return new Summary(0, BigInteger.ZERO,
                    Long.MAX_VALUE, Long.MIN_VALUE);
        }

        static Summary of(long x) {
            return new Summary(
                    1, BigInteger.valueOf(x), x, x);
        }

        static Summary merge(Summary x, Summary y) {
            return new Summary(
                    x.count + y.count,
                    x.sum.add(y.sum),
                    Math.min(x.min, y.min),
                    Math.max(x.max, y.max));
        }

        String describe() {
            return "count=" + count
                    + " sum=" + sum
                    + " min="
                    + (count == 0 ? "empty"
                            : Long.toString(min))
                    + " max="
                    + (count == 0 ? "empty"
                            : Long.toString(max));
        }
    }

    static <T> void requireSame(T got, T expected,
            String label) {
        if (!Objects.equals(got, expected))
            throw new AssertionError(
                    label + ": expected=" + expected
                    + ", got=" + got);
    }

    static void randomizedChecks(ForkJoinPool pool) {
        Random random = new Random(5242026L);

        for (int test = 0; test < 500; test++) {
            int n = random.nextInt(65);
            int threshold = 1 + random.nextInt(8);

            List<BigInteger> numbers = new ArrayList<>();
            List<Summary> partial = new ArrayList<>();
            List<String> words = new ArrayList<>();

            BigInteger exactSum = BigInteger.ZERO;
            StringBuilder expectedText = new StringBuilder();
            long minimum = Long.MAX_VALUE;
            long maximum = Long.MIN_VALUE;

            for (int i = 0; i < n; i++) {
                int value = random.nextInt(201) - 100;
                numbers.add(BigInteger.valueOf(value));
                partial.add(Summary.of(value));

                String token = value + "|";
                words.add(token);
                expectedText.append(token);

                exactSum = exactSum.add(
                        BigInteger.valueOf(value));
                minimum = Math.min(minimum, value);
                maximum = Math.max(maximum, value);
            }

            requireSame(
                    parallelReduce(pool, numbers,
                            BigInteger.ZERO,
                            BigInteger::add, threshold),
                    exactSum, "BigInteger sum");

            requireSame(
                    parallelReduce(pool, words, "",
                            String::concat, threshold),
                    expectedText.toString(),
                    "Ordered concatenation");

            Summary expectedSummary = new Summary(
                    n, exactSum, minimum, maximum);
            requireSame(
                    parallelReduce(pool, partial,
                            Summary.empty(),
                            Summary::merge, threshold),
                    expectedSummary, "Statistics monoid");

            Mat2 upper = new Mat2(1, 1, 0, 1);
            Mat2 lower = new Mat2(1, 0, 1, 1);
            Mat2 diagonal = new Mat2(2, 0, 0, 1);
            List<Mat2> matrices = new ArrayList<>();
            Mat2 expectedMatrix = Mat2.identity();

            int count = random.nextInt(10);
            for (int i = 0; i < count; i++) {
                Mat2 item = switch (random.nextInt(3)) {
                    case 0 -> upper;
                    case 1 -> lower;
                    default -> diagonal;
                };
                matrices.add(item);
                expectedMatrix =
                        Mat2.multiply(expectedMatrix, item);
            }

            requireSame(
                    parallelReduce(pool, matrices,
                            Mat2.identity(),
                            Mat2::multiply, threshold),
                    expectedMatrix, "Ordered matrix product");
        }

        System.out.println(
                "randomProperties=PASS (500 cases)");
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            List<BigInteger> numbers = List.of(
                    BigInteger.valueOf(3),
                    BigInteger.valueOf(-2),
                    BigInteger.valueOf(7),
                    BigInteger.valueOf(4));

            BigInteger sequential = sequentialFold(
                    numbers, BigInteger.ZERO, BigInteger::add);
            BigInteger parallel = parallelReduce(
                    pool, numbers, BigInteger.ZERO,
                    BigInteger::add, 2);
            BigInteger stream = numbers.parallelStream()
                    .reduce(BigInteger.ZERO, BigInteger::add);

            System.out.println("input=[3, -2, 7, 4]");
            System.out.println("sum sequential=" + sequential
                    + " parallel=" + parallel
                    + " stream=" + stream);

            BigInteger product = parallelReduce(
                    pool,
                    List.of(BigInteger.valueOf(2),
                            BigInteger.valueOf(3),
                            BigInteger.valueOf(4)),
                    BigInteger.ONE, BigInteger::multiply, 2);
            System.out.println("product parallel=" + product);

            List<String> texts =
                    List.of("An", " ", "Binh", "!");
            String textSequential = sequentialFold(
                    texts, "", String::concat);
            String textParallel = parallelReduce(
                    pool, texts, "", String::concat, 2);
            System.out.println("text sequential="
                    + textSequential
                    + " parallel=" + textParallel);

            Mat2 a = new Mat2(1, 2, 0, 1);
            Mat2 b = new Mat2(1, 0, 3, 1);
            Mat2 ab = Mat2.multiply(a, b);
            Mat2 ba = Mat2.multiply(b, a);
            Mat2 aba = parallelReduce(
                    pool, List.of(a, b, a),
                    Mat2.identity(), Mat2::multiply, 1);
            System.out.println("matrix AB=" + ab.pretty()
                    + " BA=" + ba.pretty()
                    + " ABA=" + aba.pretty());

            List<Summary> mapped = List.of(
                    Summary.of(3), Summary.of(-2),
                    Summary.of(7), Summary.of(4));
            Summary summary = parallelReduce(
                    pool, mapped, Summary.empty(),
                    Summary::merge, 2);
            System.out.println("summary " + summary.describe());

            BigInteger emptySum = parallelReduce(
                    pool, List.<BigInteger>of(),
                    BigInteger.ZERO, BigInteger::add, 2);
            BigInteger emptyProduct = parallelReduce(
                    pool, List.<BigInteger>of(),
                    BigInteger.ONE, BigInteger::multiply, 2);
            String emptyText = parallelReduce(
                    pool, List.<String>of(),
                    "", String::concat, 2);
            Summary emptySummary = parallelReduce(
                    pool, List.<Summary>of(), Summary.empty(),
                    Summary::merge, 2);
            System.out.println("empty sum=" + emptySum
                    + " product=" + emptyProduct
                    + " text=\"" + emptyText + "\""
                    + " summary=" + emptySummary.describe());

            // Intentionally INVALID reduction operator.
            List<Long> subtract = List.of(20L, 5L, 2L, 1L);
            BinaryOperator<Long> subtraction = (x, y) -> x - y;
            long subSequential = sequentialFold(
                    subtract, 0L, subtraction);
            long subTree = parallelReduce(
                    pool, subtract, 0L, subtraction, 2);
            System.out.println("subtraction sequential="
                    + subSequential + " tree=" + subTree);

            // Double arithmetic is not truly associative.
            List<Double> decimals =
                    List.of(1e16, -1e16, 1.0);
            double doubleSequential = sequentialFold(
                    decimals, 0.0, Double::sum);
            double doubleTree = parallelReduce(
                    pool, decimals, 0.0, Double::sum, 1);
            System.out.println("floating sequential="
                    + doubleSequential + " tree=" + doubleTree);

            try {
                parallelReduce(pool, numbers,
                        BigInteger.ZERO, BigInteger::add, 0);
                throw new AssertionError(
                        "Expected bad threshold");
            } catch (IllegalArgumentException expected) {
                System.out.println("invalidThreshold=rejected");
            }

            randomizedChecks(pool);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 ParallelReductionDemo.java
java ParallelReductionDemo
~~~

### Đầu ra dự kiến

~~~text
input=[3, -2, 7, 4]
sum sequential=12 parallel=12 stream=12
product parallel=24
text sequential=An Binh! parallel=An Binh!
matrix AB=[7,2;3,1] BA=[1,2;3,7] ABA=[7,16;3,7]
summary count=4 sum=12 min=-2 max=7
empty sum=0 product=1 text="" summary=count=0 sum=0 min=empty max=empty
subtraction sequential=-28 tree=-22
floating sequential=1.0 tree=0.0
invalidThreshold=rejected
randomProperties=PASS (500 cases)
~~~

### Giải thích đầu ra

**sum:** fold tuần tự, cây ForkJoin và `parallelStream().reduce` đều dùng phép cộng `BigInteger` chính xác với identity 0, nên cùng trả 12.

**product:** dùng `BigInteger.ONE` thay vì ZERO, kết quả 2×3×4=24.

**text:** nối chuỗi có tính kết hợp nhưng không giao hoán. Vì cây chia **đoạn liên tiếp** và gộp trái trước phải, kết quả vẫn là `An Binh!`.

**matrix:** \(AB\ne BA\), nhưng kết quả \(ABA\) khớp giữa các cách đặt ngoặc. Việc chạy song song không cho phép tráo đổi A và B.

**summary:** các phép count/sum/min/max được gộp theo monoid, trả count=4,sum=12,min=−2,max=7.

**empty:** các identity vẫn đúng cho input rỗng. Không in sentinel min/max như một thống kê có nghĩa; in `empty`.

**subtraction:** biểu diễn sai monoid cho ra −28 với fold trái nhưng −22 khi chia cây. Đây là **phản ví dụ có chủ đích**, không phải kết quả mong muốn của một phép reduction đúng.

**floating:** cách đặt ngoặc thay đổi làm tròn double, nên fold trái ra 1.0 còn cây cân bằng ra 0.0. Không suy kết quả double phải luôn giống từng bit giữa các hình dạng cây.

**invalidThreshold:** threshold phải ít nhất 1; hàm từ chối giá trị 0 trước khi fork task.

**randomProperties:** 500 input được tạo với seed cố định, có kích thước 0..64 và threshold 1..8. Đối chiếu tổng với phép cộng tuần tự chính xác, nối chuỗi với `StringBuilder`, thống kê với vòng lặp trực tiếp, ma trận với phép nhân tuần tự theo thứ tự phần tử. Các property này giúp phát hiện sai sót cài đặt, nhưng **không thay thế chứng minh đại số cho mọi input**.

## 17. Kiểm thử thuộc tính kết hợp và identity

Một bộ kiểm thử parallel reduce nên chia thành **hai lớp**:

### 17.1. Kiểm tra luật đại số

Với nhiều bộ ba giá trị trong miền S:

\[
\operatorname{op}(\operatorname{op}(a,b),c)
=\operatorname{op}(a,\operatorname{op}(b,c)).
\]

Kiểm identity:

\[
\operatorname{op}(e,a)=a,\quad
\operatorname{op}(a,e)=a.
\]

Nếu không đúng, **đừng** cho rằng đổi cây giảm sẽ giữ kết quả.

Ví dụ:

- Cộng `BigInteger` luôn thỏa theo toán học.
- Nối chuỗi thỏa kết hợp và identity rỗng nhưng không thỏa giao hoán.
- Nhân ma trận vuông thỏa kết hợp, identity I nhưng không giao hoán.
- Trừ và chia không thỏa kết hợp.
- Cộng double chỉ “gần kết hợp” về sai số trong một số miền, không thỏa đẳng thức bitwise nói chung.

**Kiểm thử hữu hạn không thể chứng minh một luật với vô số giá trị**, nhưng một phản ví dụ đã đủ bác bỏ tính đúng tổng quát.

### 17.2. Kiểm tra reduction với oracle độc lập

Với mỗi dãy ngắn và nhiều giá trị threshold:

1. Tính kết quả mong đợi bằng một thủ tục tuần tự rõ ràng hoặc công thức chính xác độc lập.
2. Chạy cây reduce với threshold=1,2,3,... để thay hình dạng cây.
3. Kiểm dãy rỗng, một phần tử, số phần tử lẻ, trùng giá trị, giá trị âm/cực trị.
4. Kiểm output và đảm bảo input không bị sửa.
5. Kiểm operator có side effect/race thông qua thiết kế (pure, immutable), không chỉ bằng test.

Nếu API chạy với nhiều worker, có thể lặp lại cùng input để kiểm **tính tái lập**, nhưng với floating point phải phân biệt việc khác kết quả giữa các kiểu nhóm với data race.

**Không đồng nhất** “same result in many random runs” với “mathematically associative”. Cần giải thích bằng luật đại số và tài liệu kiểu dữ liệu.

## 18. Reduce, map-reduce, scan và collect khác nhau ở đâu?

### Reduce

Từ n phần tử tạo **một giá trị**:

`[3,−2,7,4] → 12`.

### Map rồi reduce

Chuyển từng phần tử thành một giá trị trung gian, rồi gộp:

`x → Summary(1,x,x,x)`, sau đó reduce bằng `Summary.merge`.

Cách này phù hợp cho thống kê, histogram và nhiều bài xử lý dữ liệu. Phép map phải có tính độc lập thích hợp nếu muốn chạy trên các phần tử song song.

### Scan (prefix reduction)

Scan trả **mọi kết quả tiền tố**, không chỉ kết quả cuối:

`[3,−2,7,4] → [3,1,8,12]`

với phép cộng và kiểu exclusive/inclusive được định nghĩa rõ. Thuật toán scan song song thường gồm nhiều pha (upsweep/downsweep hoặc biến thể) và xử lý chi tiết vị trí output; **không phải** chỉ đổi tên reduce.

### Collect

Thu thập các phần tử thành một container mutable, ví dụ list, map hoặc bảng đếm. Java `Collector` định nghĩa supplier, accumulator và combiner. Đừng nhét một `ArrayList` dùng chung vào `Stream.reduce` rồi sửa nó từ các worker.

### All-reduce trong hệ phân tán

All-reduce không chỉ tính một giá trị tổng hợp mà còn **phân phối kết quả tới các participant**. Về mặt đại số vẫn cần operator phù hợp, nhưng còn có chi phí mạng, đồng bộ và lỗi nút. Một thuật toán tree reduce nội bộ JVM không tự bao hàm tính đúng của cơ chế retry trong hệ phân tán.

## 19. Cách thiết kế phép gộp đúng từ bài toán

Trước khi chọn `parallelStream` hoặc `ForkJoinPool`, hãy viết rõ:

1. **Miền S** của kết quả từng đoạn là gì?
2. **Identity e** là gì, có đúng ở hai phía không?
3. **Combine op** có kết hợp không?
4. Có bắt buộc giữ **thứ tự input** không?
5. Nếu có phép map từ input thành S, map có xử lý độc lập được không?
6. Phép toán có **side effect** hoặc sửa object đầu vào không?
7. Dữ liệu rỗng xử lý ra sao?
8. Kết quả yêu cầu chính xác toán học hay chỉ gần đúng trong sai số?
9. Nếu chạy phân tán hoặc GPU, engine có thể hoán vị phần tử không?
10. Chi phí combine có hằng số không hay tỷ lệ với kích thước dữ liệu?

### Ví dụ: trung bình và phương sai

**Trung bình** không nên gộp bằng avg(avg(a),avg(b)) nếu số lượng phần tử mỗi nhóm khác nhau. Dùng `(sum,count)` rồi chia cuối.

**Phương sai** cũng cần một trạng thái tổng hợp có luật kết hợp đúng, ví dụ giữ `(count,sum,sumSquares)` khi miền số học và độ ổn định số cho phép, hoặc dùng phép gộp thống kê trực tuyến có trọng số như thuật toán Chan–Golub–LeVeque với phân tích làm tròn phù hợp. Không tự gộp hai phương sai bằng trung bình cộng đơn giản nếu nhóm có kích thước/mean khác nhau.

### Ví dụ: top-k

Một trạng thái đoạn có thể là danh sách k phần tử lớn nhất; combiner lấy top-k của hợp hai danh sách. Có thể xây luật kết hợp nếu **thứ tự ưu tiên và xử lý tie được xác định nhất quán**, nhưng chi phí combine là O(k log k) hay O(k) tùy cách cài, không phải O(1).

### Ví dụ: boolean

Phép AND có identity `true`, OR có identity `false`; cả hai kết hợp và giao hoán. Trong một số chương trình, short-circuit và side effects có thể khiến “evaluate every operand in parallel” khác hành vi tuần tự mặc dù **giá trị boolean cuối** như nhau. Điều kiện đúng về **giá trị** không tự đảm bảo số lần thực thi mọi hiệu ứng phụ.

## 20. Các lỗi thường gặp

1. Gọi phép trừ là kết hợp vì nó là phép toán nhị phân.
2. Dùng identity=0 cho tích thay vì identity=1.
3. Dùng identity không thỏa cả bên trái và bên phải.
4. Quên xử lý dãy rỗng.
5. Nhầm associativity với commutativity.
6. Gộp nửa phải trước nửa trái khi dùng phép nối chuỗi.
7. Gộp theo thứ tự task hoàn thành dù operator không giao hoán.
8. Giả định `String::concat` giao hoán.
9. Giả định nhân ma trận giao hoán.
10. Tính trung bình bằng trung bình hai trung bình mà bỏ qua trọng số.
11. Dùng state mutable chia sẻ giữa nhiều worker làm accumulator.
12. Sửa input từ combine mà không đồng bộ.
13. Cho side effect vào combine, rồi ngạc nhiên khi số lần gọi/thứ tự thay đổi.
14. Từ kết quả thử vài lần suy ra phép toán kết hợp cho mọi input.
15. Dùng phép cộng double và yêu cầu luôn giống fold trái từng bit.
16. Không xét NaN, Infinity và ±0 khi làm reduction số thực.
17. Dùng long cho tổng vượt miền nhưng báo “tổng chính xác toán học”.
18. Cho `Math.addExact` vào cây nhưng không phân tích overflow ở bước trung gian.
19. Dùng `parallelStream().forEach` rồi giả định nó giữ encounter order.
20. Gọi reduce tạo một output là prefix scan.
21. Dùng `Stream.reduce` để xây một `ArrayList` mutable identity dùng chung.
22. Kết hợp hai accumulator có cùng tham chiếu mà tưởng là hai giá trị độc lập.
23. Chia task quá nhỏ, để overhead vượt thời gian tính hữu ích.
24. Chia quá ít task, không khai thác được nhiều lõi.
25. Đo speedup không có warmup, đo lệch vì JIT/GC.
26. Chỉ đo CPU mà bỏ memory bandwidth, cache misses và allocation.
27. Dùng phép nối chuỗi tốn O(length) nhưng tính span theo phép gộp O(1).
28. Cho rằng parallel reduction làm work giảm xuống O(log n).
29. Không kiểm chứng lại thứ tự ghép sau khi thay scheduler.
30. Không có oracle độc lập cho kết quả nhóm khác.
31. Không thử input kích thước 0,1,2 và kích thước lẻ.
32. Trong hệ phân tán, cho rằng associativity cũng bảo đảm không đếm trùng sau retry.
33. Không định nghĩa rõ kiểu/miền mà phép toán thực sự kết hợp.
34. Đổi cách nhóm làm số thực lệch rồi vội kết luận có race.
35. Dùng một kết quả benchmark làm bảo đảm nhanh hơn cho mọi máy.
36. Không ghi rõ threshold, số worker và kiểu accumulator khi so sánh kết quả.

## 21. Bài tập có lời giải

**Bài 1.** Reduce làm gì? **Đáp án:** gộp dãy nhiều phần tử thành một kết quả tổng hợp.

**Bài 2.** Fold tuần tự khác tree reduction ở điểm nào? **Đáp án:** fold có chuỗi phụ thuộc tuyến tính, tree có thể tính hai nửa độc lập rồi gộp.

**Bài 3.** Tính kết hợp có công thức gì? **Đáp án:** `(a⊗b)⊗c=a⊗(b⊗c)`.

**Bài 4.** Giao hoán có công thức gì? **Đáp án:** `a⊗b=b⊗a`.

**Bài 5.** Cần giao hoán để đổi vị trí hai phần tử không? **Đáp án:** cần, hoặc phải chứng minh một đặc tính khác bảo toàn kết quả.

**Bài 6.** Chia dãy thành hai đoạn liên tiếp, ghép trái trước phải, có bắt buộc giao hoán không? **Đáp án:** không; kết hợp với identity đủ cho đổi nhóm.

**Bài 7.** Identity cho phép cộng? **Đáp án:** 0.

**Bài 8.** Identity cho phép nhân? **Đáp án:** 1.

**Bài 9.** Identity cho nối chuỗi? **Đáp án:** chuỗi rỗng.

**Bài 10.** Identity của nhân ma trận vuông? **Đáp án:** ma trận đơn vị I.

**Bài 11.** Một monoid cần điều kiện nào? **Đáp án:** miền đóng, operator kết hợp, tồn tại identity hai phía.

**Bài 12.** Kết quả reduce tổng của []? **Đáp án:** 0.

**Bài 13.** Kết quả reduce tích của []? **Đáp án:** 1.

**Bài 14.** Vì sao min của [] không được in như một giá trị thật? **Đáp án:** không có phần tử nhỏ nhất; sentinel chỉ là identity kỹ thuật.

**Bài 15.** Tổng [3,−2,7,4]? **Đáp án:** 12.

**Bài 16.** Tích [2,3,4]? **Đáp án:** 24.

**Bài 17.** Rút gọn nối ["An"," ","Binh","!"] giữ thứ tự? **Đáp án:** "An Binh!".

**Bài 18.** Nối chuỗi có kết hợp không? **Đáp án:** có, nếu giữ thứ tự.

**Bài 19.** Nối chuỗi có giao hoán không? **Đáp án:** không.

**Bài 20.** `(20−5)−2` bằng bao nhiêu? **Đáp án:** 13.

**Bài 21.** `20−(5−2)` bằng bao nhiêu? **Đáp án:** 17.

**Bài 22.** Fold từ 0 phép trừ trên [20,5,2,1]? **Đáp án:** −28.

**Bài 23.** Cây hai lá [20,5] và [2,1] với identity giả 0 và phép trừ? **Đáp án:** −22, minh họa sai điều kiện reduce.

**Bài 24.** Cách đúng để parallelize average? **Đáp án:** reduce (sum,count), chia sau khi gộp và kiểm count>0.

**Bài 25.** `avg(avg(1,3),9)` bằng gì? **Đáp án:** 5.5, khác avg thật của [1,3,9] là 13/3.

**Bài 26.** Nguyên nhân `1e16+(-1e16+1)` khác cách nhóm trái? **Đáp án:** mất 1 do làm tròn double ở nhánh trong.

**Bài 27.** Fold trái double [1e16,−1e16,1.0] thường cho gì trên Java? **Đáp án:** 1.0.

**Bài 28.** Cây chia nửa như demo cho gì? **Đáp án:** 0.0.

**Bài 29.** `BigInteger::add` hữu ích ở điểm nào? **Đáp án:** tổng số nguyên không overflow theo miền BigInteger, nên associativity toán học được giữ.

**Bài 30.** Long overflow có làm phép cộng Java không kết hợp về bit pattern không? **Đáp án:** không; phép cộng modulo \(2^{64}\) vẫn kết hợp, nhưng có thể sai tổng toán học mong muốn.

**Bài 31.** Với A=[[1,2],[0,1]] và B=[[1,0],[3,1]], AB là gì? **Đáp án:** [[7,2],[3,1]].

**Bài 32.** BA là gì? **Đáp án:** [[1,2],[3,7]]; AB≠BA.

**Bài 33.** ABA là gì? **Đáp án:** [[7,16],[3,7]].

**Bài 34.** Summary của [3,−2,7,4]? **Đáp án:** count4,sum12,min−2,max7.

**Bài 35.** Summary empty có count? **Đáp án:** 0, cần phân biệt min/max sentinel với dữ liệu thật.

**Bài 36.** Với n lớn, mỗi combine O(1), work của balanced reduction? **Đáp án:** Θ(n).

**Bài 37.** Span lý tưởng của tree reduction với leaf size1? **Đáp án:** Θ(log n).

**Bài 38.** Với leaf threshold t, span lý tưởng cỡ gì? **Đáp án:** O(t+log(n/t)) khi n>t.

**Bài 39.** Vì sao nhiều task chưa chắc nhanh hơn? **Đáp án:** overhead fork/join, allocation, contention và memory bandwidth.

**Bài 40.** `reduce` và `scan` khác nhau thế nào? **Đáp án:** reduce cho một aggregate; scan trả các aggregate tiền tố.

**Bài 41.** `parallelStream().forEach` có bảo đảm encounter order? **Đáp án:** không.

**Bài 42.** Có nên dùng cùng một mutable ArrayList identity cho parallel reduce? **Đáp án:** không; có nguy cơ aliasing, race và vi phạm identity.

**Bài 43.** Associativity có loại trùng sự kiện khi retry trong hệ phân tán không? **Đáp án:** không; cần idempotence/dedup/exactly-once riêng.

**Bài 44.** Kiểm thử 500 input chứng minh operator kết hợp cho mọi giá trị chưa? **Đáp án:** chưa; phải chứng minh luật hoặc nêu phạm vi bảo đảm.

## 22. Checklist trước khi triển khai parallel reduction

1. Đã xác định chính xác miền giá trị S và phép gộp chưa?
2. Phép gộp có đóng trên S và kết hợp thật sự không?
3. Identity e có đúng ở **cả bên trái và bên phải**?
4. Dãy rỗng và dãy một phần tử có kết quả đúng?
5. Có cần giữ **encounter order** của input?
6. Nếu không giữ thứ tự, phép toán có giao hoán không?
7. Mọi task có chỉ đọc input bất biến trong lúc chạy?
8. Accumulator và kết quả cục bộ có độc lập, không bị chia sẻ mutable object?
9. Combine có pure/thread-safe, không side effect ngoài ý muốn?
10. Đã tách average ra thành `(sum,count)` hay một summary kết hợp đúng?
11. Có xử lý min/max rỗng mà không lộ sentinel giả?
12. Có hiểu giới hạn associativity của double/float IEEE 754?
13. Có chính sách rõ về NaN, ±∞ và ±0?
14. Tổng có thể overflow kiểu số nguyên đang dùng không?
15. Nếu yêu cầu chính xác, đã dùng BigInteger/BigDecimal hoặc chứng minh giới hạn?
16. Cây có ghép **trái trước phải** khi phép toán không giao hoán?
17. Threshold có ≥1 và tránh tạo quá nhiều task nhỏ?
18. Có kiểm tra fork/join không deadlock hoặc giữ tham chiếu mutable?
19. Có kiểm thử với oracle độc lập và nhiều threshold?
20. Có test input rỗng, số lẻ, số âm, cực trị và các thứ tự xấu?
21. Có tách unit test đại số khỏi benchmark hiệu năng?
22. Có so work, span, overhead thực tế thay vì chỉ đếm task?
23. Nếu chạy Java Stream, đã dùng đúng contract reduce/collect?
24. Nếu chạy phân tán, đã tính đến lỗi nút, retry, duplicate và thứ tự merge?
25. Đã phân biệt reduce một giá trị với scan prefix nhiều giá trị?
26. Có mô tả rõ khi nào kết quả chỉ gần đúng do floating point?

**Kết luận:** parallel reduction có thể đổi một chuỗi phụ thuộc tuyến tính thành cây có span \(O(\log n)\) khi combine O(1) và các lá đủ nhỏ. Điều kiện đảm bảo tính đúng theo phép đổi ngoặc là **tính kết hợp**, cùng **identity hai phía** để xử lý nhánh rỗng. **Giao hoán chỉ cần khi cho phép đổi thứ tự phần tử**; nếu ghép đúng trái–phải thì nối chuỗi và nhân ma trận vẫn có thể rút gọn song song. Phép trừ, trung bình hai nhóm không có trọng số và phép cộng double làm tròn là những cảnh báo điển hình. Cần thiết kế operator theo đại số, tách side effect, dùng oracle để test và đo hiệu năng thực tế trước khi kết luận về speedup.
