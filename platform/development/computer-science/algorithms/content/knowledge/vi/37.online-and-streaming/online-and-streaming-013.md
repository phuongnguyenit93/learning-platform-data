# Trạng thái có thể gộp và xử lý dữ liệu theo nhiều phần

Trong thuật toán **trực tuyến và luồng (online/streaming algorithms)**, dữ liệu có thể quá lớn để đưa vào một mảng, đến dần theo thời gian hoặc được chia thành hàng nghìn khối trên nhiều máy. Ta thường muốn xử lý từng phần và chỉ giữ lại một **trạng thái tóm tắt**, sau đó **gộp các trạng thái** để có kết quả như khi xử lý toàn bộ dữ liệu.

Ví dụ: thay vì đọc tất cả hóa đơn rồi tính tổng, mỗi worker có thể lưu `(số lượng, tổng tiền)` cho một phần dữ liệu; các trạng thái được cộng lại để cho tổng toàn cục. Nhưng không phải mọi thống kê đều gộp được bằng cách lấy **trung bình các trung bình**; không phải mọi phép gộp đều cho phép **đảo thứ tự các khối**; và không phải cứ chia luồng thành nhiều phần thì bộ nhớ sẽ tự động giảm.

Bài thuộc nhóm **Trực tuyến và luồng** của **Computer Science Algorithms**, tập trung vào **trạng thái có thể gộp (mergeable state/summary)** và phương pháp **chunked processing, streaming, parallel reduction, MapReduce**. Ta sẽ xây dựng đại số gộp từ **phần tử đơn vị và tính kết hợp**, phân biệt **tính giao hoán với bảo toàn thứ tự**, rồi áp dụng cho:
- Đếm, tổng, min/max, trung bình và phương sai chính xác;
- Bảng tần suất/đếm phần tử khác nhau;
- **Top-k** có giới hạn bộ nhớ và bảo toàn số lần xuất hiện;
- **Độ dài đoạn liên tiếp** (prefix/suffix/best) phụ thuộc thứ tự dữ liệu;
- Các sketch xấp xỉ, độ bất định, tính đúng khi chunk bị gửi lại hoặc đến muộn.

Bài có chương trình **Java 17 chạy độc lập**, sử dụng `BigInteger` cho các phép cộng/bình phương số nguyên để tránh tràn số, có code gộp trạng thái và stdout dự kiến. Phần kiểm chứng độc lập duyệt **1.093 chuỗi độ dài 0..6** trên tập giá trị `{-1,0,1}`, tương ứng **27.064 cách chia thành ba phần**, kiểm tra hai cách đặt ngoặc gộp và đối chiếu kết quả duyệt trực tiếp. Những thử nghiệm hữu hạn giúp phát hiện sai cài đặt; **chứng minh tính kết hợp** mới là cơ sở để dùng phép gộp cho mọi số lượng khối hợp lệ.

## 1. Vấn đề: dữ liệu một luồng, nhiều phần, nhiều worker

Cho chuỗi đầu vào:

\[
X=[x_0,x_1,\ldots,x_{n-1}].
\]

Ta có thể nhận dữ liệu từng phần:

\[
X=A\mathbin{\|}B\mathbin{\|}C,
\]

trong đó `\|` ký hiệu **nối chuỗi theo thứ tự**, không phải phép OR logic. Một hàm tóm tắt `h` là **có thể gộp** nếu tồn tại phép `\oplus` sao cho:

\[
\boxed{h(A\mathbin{\|}B)=h(A)\oplus h(B).}
\]

Nếu có một **trạng thái rỗng** `e=h([])` thỏa:

\[
e\oplus s=s\oplus e=s
\]

và phép gộp **kết hợp**:

\[
(a\oplus b)\oplus c=a\oplus(b\oplus c),
\]

thì ta có thể xử lý từng chunk rồi gộp theo nhiều cây reduction khác nhau mà không thay đổi kết quả toán học — miễn là vẫn giữ thứ tự khi phép gộp không giao hoán.

**Hai cấp độ quan trọng:**
1. **Thuật toán streaming:** cập nhật trạng thái khi mỗi bản ghi đến; không cần giữ toàn bộ dữ liệu gốc.
2. **Thuật toán mergeable:** hai trạng thái đã tính riêng có thể gộp mà không phải phát lại từng bản ghi; điều này thuận lợi cho song song hóa, checkpoint, distributed aggregation và xử lý dữ liệu chia phần.

Một thuật toán cập nhật trực tuyến **không nhất thiết** có trạng thái nhỏ có thể gộp. Ví dụ, một cấu trúc phải giữ toàn bộ lịch sử vẫn có thể nhận item từng bước nhưng không đem lại lợi ích bộ nhớ.

## 2. Đại số cần thiết: monoid, không phải “cộng tùy ý”

Một **monoid** gồm tập trạng thái `S`, phép toán hai ngôi `\oplus:S×S→S` và phần tử đơn vị `e`, với:
- **Đóng:** gộp hai trạng thái hợp lệ được một trạng thái hợp lệ;
- **Kết hợp:** `(a⊕b)⊕c=a⊕(b⊕c)`;
- **Đơn vị:** `e⊕a=a⊕e=a`.

**Giao hoán** `a⊕b=b⊕a` là một tính chất **bổ sung**, không bắt buộc để là monoid.

| Trạng thái | Phép gộp | Đơn vị | Kết hợp | Giao hoán |
| --- | --- | --- | --- | --- |
| Count | `a+b` | 0 | Có nếu không tràn | Có |
| Sum số nguyên chính xác | `a+b` | 0 | Có | Có |
| Min / max | `min(a,b)` / `max(a,b)` | +∞ / −∞ theo mô hình | Có | Có |
| Tập giá trị đã gặp | Hợp tập hợp | Tập rỗng | Có | Có |
| Bảng tần suất | Cộng đếm theo khóa | Bản đồ rỗng | Có | Có |
| Chuỗi ký tự | Ghép `a||b` | Chuỗi rỗng | Có | **Không** |
| Top-k đa tập | Lấy top-k của hợp đa tập | Danh sách rỗng | Có | Có nếu định nghĩa thứ tự/ties phù hợp |
| Đoạn 1 liên tiếp | Ghép trạng thái `len,prefix,suffix,best` | Trạng thái rỗng | Có | **Không** |

**Định lý gộp cơ bản:** nếu `h([x])` là trạng thái của phần tử đơn và `h([])=e`, với phép gộp kết hợp thì:

\[
h([x_0,\ldots,x_{n-1}])
=h([x_0])\oplus\cdots\oplus h([x_{n-1}]).
\]

Chia nhóm các số hạng theo chunk và đặt ngoặc khác nhau vẫn được **cùng trạng thái** trong đại số chính xác.

**Không được nhầm “đặt ngoặc lại” với “đổi thứ tự”:** tính kết hợp cho phép `(A⊕B)⊕C=A⊕(B⊕C)`, nhưng chỉ khi có giao hoán mới có thể tự đổi `A⊕B` thành `B⊕A`. Dữ liệu theo thời gian thường đòi **giữ nguyên thứ tự chunk**.

## 3. Từ một lượt đọc tới MapReduce

Một quy trình xử lý theo phần:

1. **Partition:** chia dữ liệu thành các chunk `C_0,C_1,\ldots,C_{p-1}` theo quy tắc rõ ràng.
2. **Map/summarize:** mỗi worker nhận một chunk, tính trạng thái `S_i=h(C_i)`.
3. **Combine/reduce:** tính `S=S_0\oplus S_1\oplus\cdots\oplus S_{p-1}`.
4. **Finalize/query:** chuyển `S` thành kết quả cần trả, ví dụ `mean=sum/count` hoặc danh sách top-k.

Sơ đồ:

~~~text
Input stream
      |
  partition by offset / chunk ID
      |
   +--+------+-----------+
   |         |           |
 Chunk A   Chunk B     Chunk C
   |         |           |
 state A   state B     state C
   |         |           |
   +---- merge tree -----+
             |
      merged summary
             |
       finalize/query
~~~

Nếu phép gộp **giao hoán**, các chunk có thể đến theo thứ tự bất kỳ mà không ảnh hưởng ý nghĩa đại số. Nếu chỉ **kết hợp**, reduction tree được phép đổi cách đặt ngoặc nhưng **phải bảo toàn thứ tự nối chunk**. Ví dụ trạng thái “đoạn liên tiếp dài nhất” bắt buộc biết chunk nào đứng trước.

Việc worker có thể gửi lại thông điệp do retry cũng quan trọng: tính kết hợp/giao hoán **không bảo đảm gộp lặp không bị đếm hai lần**. Cần phân biệt **data aggregation** với **delivery semantics**.

## 4. Các trạng thái đơn giản: count, sum, min, max

Với chuỗi số nguyên, dùng:

\[
S=(n,\Sigma,\min,\max).
\]

Trạng thái một phần dữ liệu:
- `n`: số bản ghi;
- `\Sigma`: tổng giá trị;
- `min` và `max`: giá trị nhỏ nhất/lớn nhất.

Gộp hai trạng thái không rỗng:

\[
(n_A,\Sigma_A,m_A,M_A)\oplus(n_B,\Sigma_B,m_B,M_B)
=(n_A+n_B,\Sigma_A+\Sigma_B,\min(m_A,m_B),\max(M_A,M_B)).
\]

**Trạng thái rỗng** dùng `n=0,\Sigma=0` và **min/max chưa xác định**. Trong Java, bài dùng `Integer min,max` có thể là `null` cho luồng rỗng. Gộp rỗng với trạng thái không rỗng trả trạng thái không rỗng; không lấy `min(0,...)` vì như vậy sẽ sai nếu mọi giá trị đều dương.

Ví dụ:

~~~text
A = [4,-2,7]        n=3  sum=9   min=-2 max=7
B = [7,0,3,-5]      n=4  sum=5   min=-5 max=7
C = [9,1,9]         n=3  sum=19  min=1  max=9

Gop A+B+C:          n=10 sum=33  min=-5 max=9
~~~

Các giá trị này không phụ thuộc vào cách đặt ngoặc gộp. Tổng/tần suất phải giữ đúng số lần xuất hiện; số 7 và 9 xuất hiện **hai lần**, không được tự loại trùng nếu mục tiêu là thống kê bản ghi.

**Độ phức tạp:** tóm tắt n phần tử bằng các bộ đếm O(n) phép cập nhật, lưu O(1) trường số học. Tuy nhiên, số nguyên có độ dài bit lớn dần nếu muốn chính xác tuyệt đối; O(1) trạng thái theo **số trường** không đồng nghĩa O(1) byte không giới hạn.

## 5. Trung bình: không lấy trung bình của các trung bình một cách ngây thơ

**Sai phổ biến:**

~~~text
A = [0]          mean(A)=0
B = [10,20,30]   mean(B)=20

(mean(A)+mean(B))/2 = 10     // SAI
mean(A||B) = 60/4 = 15      // DUNG
~~~

Nguyên nhân: hai chunk có **kích thước khác nhau**. Trung bình không được gộp bằng cách lấy trung bình cộng không trọng số của các trung bình chunk.

Lưu `(n,sum)`, rồi tính:

\[
\mu=\frac{\Sigma}{n},\quad n>0.
\]

Nếu chỉ có `(n,\mu)`, công thức đúng là:

\[
\mu_{A\cup B}=\frac{n_A\mu_A+n_B\mu_B}{n_A+n_B}.
\]

**Chú ý:** công thức có trung bình dạng double có thể tích lũy lỗi làm tròn. Với dữ liệu nguyên, lưu `sum` dạng `BigInteger` rồi chia ở cuối cho phép chọn rõ quy tắc rounding là một cách kiểm thử chính xác hơn.

**Luồng rỗng** có count0: `mean` **không xác định**, không nên tự trả 0 rồi coi đó là trung bình thật. API nên ném lỗi hoặc trả `Optional`/giá trị báo thiếu theo hợp đồng.

## 6. Phương sai chính xác với count, sum và sum of squares

Với dữ liệu nguyên `x_1,\ldots,x_n`, lưu thêm:

\[
Q=\sum_{i=1}^{n}x_i^2.
\]

Trạng thái:

\[
S=(n,\Sigma,Q,\min,\max).
\]

`n`, `\Sigma` và `Q` đều gộp bằng **cộng**, vì tập dữ liệu nối khối là hợp các phần tử có số lần xuất hiện. Sau khi gộp, phương sai tổng thể (*population variance*) là:

\[
\sigma^2=\frac{Q}{n}-\left(\frac{\Sigma}{n}\right)^2
=\frac{nQ-\Sigma^2}{n^2},\qquad n>0.
\]

Phương sai mẫu (*sample variance*) với hiệu chỉnh Bessel:

\[
s^2=\frac{nQ-\Sigma^2}{n(n-1)},\qquad n>1.
\]

Bài sử dụng `BigInteger` lưu `\Sigma` và `Q`, tính tử số `nQ−\Sigma^2` **chính xác**, chỉ làm tròn thành `BigDecimal` khi **finalize**.

Ví dụ toàn dữ liệu:

~~~text
X = [4,-2,7,7,0,3,-5,9,1,9]
n=10
sum=33
sumSquares=315
n*sumSquares - sum^2 = 10*315 - 33^2 = 2061

mean=33/10=3.3
populationVariance=2061/100=20.61
sampleVariance=2061/90=22.9
~~~

Nếu tính trực tiếp `x*x` bằng int trước khi ép kiểu lớn, có thể **tràn số**. Trong code, `BigInteger.valueOf(x)` được tạo **trước** phép nhân `b.multiply(b)`. `Math.addExact` được dùng cho count long để phát hiện overflow thay vì âm thầm đổi dấu.

### Cảnh báo: sumSquares bằng double dễ mất ổn định số

Công thức `Q/n-(sum/n)^2` có thể gây **catastrophic cancellation** với dữ liệu có trung bình rất lớn nhưng phương sai rất nhỏ. Lưu `BigInteger` giải quyết vấn đề **đúng số học nguyên** trong bài minh họa, nhưng không phù hợp cho mọi luồng số thực hoặc trường hợp đòi độ chính xác tương đối mà không thể biểu diễn chính xác từng mẫu.

Với số thực, có thể dùng **Welford** cho một lượt và **Chan–Golub–LeVeque** để gộp trạng thái:

\[
S=(n,\mu,M_2),\qquad M_2=\sum_i(x_i-\mu)^2.
\]

Với hai nhóm không rỗng A,B:

\[
\delta=\mu_B-\mu_A,\quad n=n_A+n_B,
\]

\[
\mu=\mu_A+\delta\frac{n_B}{n},
\]

\[
M_2=M_{2,A}+M_{2,B}+
\delta^2\frac{n_An_B}{n}.
\]

Công thức này thường **ổn định số** hơn trừ hai số gần nhau. Tuy nhiên phép cộng số dấu phẩy động **không kết hợp bit-by-bit**; gộp theo cây khác có thể cho kết quả double khác vài ULP dù các công thức toán học tương đương.

## 7. Top-k: giữ rất ít phần tử nhưng vẫn gộp đúng

Nếu chỉ muốn biết **k giá trị lớn nhất** và cho phép giá trị trùng nhau, mỗi chunk không cần giữ tất cả phần tử. Ta lưu danh sách **top-k lớn nhất dưới dạng đa tập**, không loại trùng.

Định nghĩa:

\[
Top_k(A\mathbin{\|}B)
=Top_k(Top_k(A)\uplus Top_k(B)),
\]

trong đó `\uplus` là hợp **đa tập** (giữ số lần xuất hiện). Mỗi phần tử bị loại khỏi top-k của chunk A đã có ít nhất k phần tử trong A lớn hơn hoặc bằng nó theo thứ tự chuẩn; thêm dữ liệu từ B không thể khiến phần tử bị loại đó **bắt buộc** xuất hiện trong top-k toàn cục. Vì vậy chỉ cần gộp hai danh sách ngắn.

**Ví dụ:**

~~~text
A = [4,-2,7]       top3(A)=[7,4,-2]
B = [7,0,3,-5]     top3(B)=[7,3,0]
C = [9,1,9]        top3(C)=[9,9,1]

top3(A||B||C) = [9,9,7]
~~~

Hai số 9 cùng có mặt: nếu dùng `Set` để lưu top-k, ta sẽ **làm mất số lần xuất hiện** và có thể ra câu trả lời sai.

**Độ phức tạp:** quét m phần tử một chunk bằng min-heap k phần tử mất O(m log k) nếu k>0; chỉ lưu O(k). Gộp hai top-k có tối đa 2k phần tử, tốn O(k log k) với min-heap và sorting cuối. `k=0` được định nghĩa trả danh sách rỗng.

**Trạng thái phải tương thích:** cùng k, cùng bộ so sánh, cùng quy tắc xử lý trùng và tie. Với bản ghi có điểm số bằng nhau, muốn output **deterministic** nên dùng khóa tie-break ổn định như ID duy nhất; không để thứ tự scheduling quyết định người thắng.

## 8. Bảng tần suất và distinct count

Với mỗi chunk, lưu map:

\[
F_A(v)=\#\{i\in A:x_i=v\}.
\]

Gộp:

\[
F_{A\cup B}(v)=F_A(v)+F_B(v).
\]

Ví dụ dữ liệu chính:

~~~text
X = [4,-2,7,7,0,3,-5,9,1,9]

frequency =
{-5=1, -2=1, 0=1, 1=1, 3=1, 4=1, 7=2, 9=2}

distinct = 8
~~~

**Phân biệt distinct với count:**
- Tổng bản ghi = 10;
- Số khóa có đếm dương = 8;
- Map lưu các đếm, không phải chỉ một số `distinct(A)`.

Nếu chỉ biết `distinct(A)` và `distinct(B)` thì **không thể** lấy `distinct(A∪B)` chính xác bằng phép cộng đơn giản, vì hai chunk có thể trùng khóa. Ví dụ `A=[1,2]`, `B=[2,3]`: distinct(A)=2, distinct(B)=2 nhưng distinct(A∪B)=3, không phải 4.

Một **set các khóa** là trạng thái exact gộp được bằng hợp tập hợp; map tần suất còn giữ cả số lần. Nhưng bộ nhớ là O(D) với D khóa phân biệt, **không phải một summary constant-size**. Đây là ví dụ quan trọng: “mergeable” không đồng nghĩa “nhỏ”.

### Khi cần bộ nhớ nhỏ hơn O(D)

Có các sketch xấp xỉ:
- **HyperLogLog (HLL):** trạng thái một tập thanh ghi dựa trên hash, có thể hợp bằng `max` từng thanh ghi nếu **cùng precision, hash và cấu hình**. Kết quả distinct là **ước lượng** có sai số thống kê; không gọi là exact.
- **Count–Min Sketch:** cộng các bảng đếm tương ứng nếu **cùng kích thước và cùng họ hash**, dùng cho ước lượng frequency dưới giả thiết tương ứng. Có sai số do hash collision; không lưu được mọi tần suất exact với bộ nhớ hằng cho miền khóa không giới hạn.
- **Bloom filter:** OR các bitset tương thích có thể biểu diễn membership đã kết hợp, nhưng có **false positive** và không trực tiếp cho distinct chính xác.
- **Quantile sketches** như KLL/t-digest: có thiết kế hỗ trợ merge nhưng chất lượng và điều kiện phụ thuộc từng sketch/triển khai; không được tự gọi mọi sketch là mergeable hoặc có cùng bảo đảm.

Nếu dùng hai sketch với **hash seed/precision khác nhau** rồi gộp byte thô hoặc cộng thanh ghi sai quy tắc, kết quả có thể vô nghĩa. Cần ghi cả **phiên bản định dạng và cấu hình** của state.

## 9. Một trạng thái không giao hoán: độ dài dãy 1 liên tiếp

Không phải mọi bài toán streaming là tổng, min hay max. Giả sử dữ liệu là chuỗi 0/1 và cần tìm **đoạn liên tiếp gồm các số 1 dài nhất**.

Mỗi chunk cần lưu:

\[
S=(len,prefix,suffix,best),
\]

trong đó:
- `len`: chiều dài chunk;
- `prefix`: số lượng 1 liên tiếp từ **đầu** chunk;
- `suffix`: số lượng 1 liên tiếp tới **cuối** chunk;
- `best`: dãy 1 liên tiếp dài nhất ở đâu đó trong chunk.

Gộp chunk **trái** A và **phải** B:

\[
len=len_A+len_B,
\]

\[
prefix=
\begin{cases}
len_A+prefix_B & \text{nếu }prefix_A=len_A,\\
prefix_A & \text{ngược lại},
\end{cases}
\]

\[
suffix=
\begin{cases}
len_B+suffix_A & \text{nếu }suffix_B=len_B,\\
suffix_B & \text{ngược lại},
\end{cases}
\]

\[
\boxed{best=\max(best_A,best_B,suffix_A+prefix_B).}
\]

**Lý do:** đoạn 1 dài nhất của chuỗi nối A||B có thể nằm hoàn toàn trong A, hoàn toàn trong B, hoặc **đi qua ranh giới** giữa suffix của A và prefix của B. Đó là ba trường hợp đã được xét hết.

Ví dụ:

~~~text
A = [1,1,0,1]   len=4 prefix=2 suffix=1 best=2
B = [1,1,1]     len=3 prefix=3 suffix=3 best=3
C = [0,1]       len=2 prefix=0 suffix=1 best=1

A||B||C = [1,1,0,1,1,1,1,0,1]
best = 4
~~~

Dãy 1 dài nhất **bắt qua ranh giới A/B**: một số 1 cuối A + ba số 1 đầu B = 4. Nếu chỉ gộp `max(best_A,best_B,best_C)` thì trả 3 và **bỏ mất** đoạn cắt ranh giới.

### Kết hợp nhưng không giao hoán

Lấy `A=[1,1]` và `B=[1,0]`:

~~~text
A||B = [1,1,1,0]    best=3
B||A = [1,0,1,1]    best=2
~~~

Trạng thái `Runs` vẫn **kết hợp** khi gộp đúng thứ tự chuỗi, nhưng **không giao hoán**. Không được shuffle các chunk theo thứ tự hoàn thành worker nếu output phụ thuộc thứ tự thời gian.

**Trạng thái rỗng** là `(0,0,0,0)` và phải là đơn vị hai phía. Với chiều dài rất lớn, dùng `Math.addExact` hoặc kiểu số phù hợp để không tràn count/prefix/suffix.

## 10. Sửa hoặc đảo ngược: mergeable chưa chắc xóa được dữ liệu

Nếu cửa sổ thời gian cuộn và một chunk cũ rời khỏi cửa sổ, phép gộp không tự cho phép “trừ chunk”:
- **Count/sum:** có thể trừ theo đại số nếu giữ đủ số và xử lý chính xác.
- **Min/max:** không có phép trừ tổng quát từ một số min duy nhất; nếu phần tử min bị xóa, cần cấu trúc bổ sung (deque đơn điệu, multiset, các block).
- **Top-k:** nếu một phần tử top-k bị xóa, có thể cần phần tử thứ k+1 đã bị loại; state top-k một mình **không đủ** để khôi phục kết quả.
- **Distinct exact set:** xóa một phần tử khi nó còn xuất hiện ở chunk khác đòi **đếm tham chiếu**, không chỉ set union.
- **Runs:** xóa phần giữa khác với bỏ đi một prefix/suffix; phép merge của các chunk liên tiếp không tự xử lý xóa tùy ý.

Tính **mergeable** là hợp đồng **thêm/gộp dữ liệu**, không mặc nhiên là **invertible**, hỗ trợ range update, sliding window hoặc retraction.

Với event streaming, cần phân biệt:
- **Event time** (thời điểm sự kiện) và **processing time** (lúc hệ thống nhận/đọc);
- **Late events** và watermark/window policy;
- **Checkpoint/restart** và chunk đã xử lý;
- **Dữ liệu được gửi lại** và idempotency.

Nếu nhận cùng chunk **hai lần**, gộp count/sum hai lần sẽ **đếm trùng**. Một hệ thống cần ID chunk/offset, dedup, transactional sink hoặc cơ chế exactly-once theo kiến trúc; **associativity không giải quyết bài toán delivery**.

## 11. Các trạng thái không thể gộp ngây thơ

| Muốn tính | Trạng thái sai/thiếu | Trạng thái hoặc phương án phù hợp |
| --- | --- | --- |
| Mean | Chỉ mỗi mean của chunk, rồi lấy trung bình các mean | `(count,sum)` hoặc `(count,mean)` có trọng số |
| Variance | Trung bình các variance chunk | `(n,sum,sumSquares)` exact cho số nguyên; Chan/Welford cho floating |
| Exact distinct | Chỉ mỗi số distinct chunk rồi cộng | Set union hoặc map frequency, O(D) |
| Global top-k | Chỉ max mỗi chunk khi k>1 | Top-k từng chunk cùng k, hợp đa tập |
| Longest run | Chỉ `max run` mỗi chunk | `len,prefix,suffix,best` |
| Exact median | Chỉ median từng chunk | Thường cần nhiều thông tin hơn, có thể dùng quantile sketch xấp xỉ |
| Uniform reservoir sample | Ghép các mẫu cùng kích thước, rồi chọn đều một mẫu | Phải cân theo kích thước chunk/cơ chế reservoir có chứng minh |
| Sliding window min | Chỉ lưu min toàn bộ lịch sử | Cấu trúc cửa sổ/deque hoặc block có tái tính |
| Ordered output | Gộp chunk theo thứ tự hoàn tất bất kỳ | Lưu offset và gộp theo thứ tự logic |
| Đếm bản ghi sau retry | Cộng lại summary nhận trùng | Dedup chunk/offset, semantics nhất quán |

**Phản ví dụ reservoir k=1:** chunk A có 1 phần tử, chunk B có 99 phần tử. Nếu chọn một mẫu uniform từ A và một mẫu uniform từ B rồi **chọn một trong hai mẫu với xác suất 1/2**, phần tử A được xác suất 1/2, trong khi sampling đồng đều trên 100 bản ghi cần xác suất 1/100. Nếu chỉ chọn k=1 từ mỗi chunk, phải chọn **chunk theo trọng số số bản ghi** rồi chọn mẫu của chunk đó, hoặc dùng một thiết kế reservoir mergeable có chứng minh.

**Median:** chỉ giữ một số median per chunk không đủ để tái tạo median của hợp dữ liệu khi kích thước và phân phối khác nhau. Nếu muốn **exact quantiles** cho miền không giới hạn, bộ nhớ có thể lớn; sketch xấp xỉ phải nêu cận sai số, giả thiết và cấu hình gộp.

## 12. Chọn độ chính xác: số nguyên, số thực, dữ liệu cực trị

Lựa chọn kiểu số là một phần của hợp đồng gộp.

**Số nguyên tràn:** với giá trị `Integer.MAX_VALUE=2147483647`, bình phương đã lớn hơn int. Ba giá trị như vậy cho:

~~~text
input=[2147483647,2147483647,2147483647]
sum=6442450941
sumSquares=13835058042397261827
~~~

`sumSquares` còn **lớn hơn Long.MAX_VALUE**. Nếu cộng hoặc nhân vào long trước khi chuyển thành BigInteger, kết quả đã sai không thể cứu bằng cast sau đó. Code xây dựng `BigInteger b=BigInteger.valueOf(x)` rồi tính `b.multiply(b)`.

**Count long tràn:** dùng `Math.addExact` để phát hiện thay vì âm thầm chuyển dương thành âm. Nếu trạng thái có thể chứa hơn `Long.MAX_VALUE` bản ghi, nên cân nhắc BigInteger count hoặc giới hạn hệ thống phù hợp.

**Double không kết hợp bitwise:** ví dụ số thực IEEE-754 double:

~~~text
(1e16 + (-1e16)) + 1.0 = 1.0
1e16 + ((-1e16) + 1.0) = 0.0
~~~

Vì `(-1e16)+1.0` được làm tròn thành `-1e16`. Điều này không phủ nhận tính kết hợp **toán học của cộng số thực lý tưởng**; nó nói rằng **phép cộng floating-point trên máy** có thể cho kết quả khác theo cây merge. Để replay chính xác, cần **thứ tự reduction cố định**, thuật toán số ổn định, hoặc phép tổng chính xác/compensated phù hợp yêu cầu.

**BigInteger và BigDecimal:** BigInteger tính chính xác trên số nguyên; BigDecimal giúp kiểm soát làm tròn lúc finalize. Không nhầm `new BigDecimal(double)` với biểu diễn thập phân gốc mà trước đó đã bị làm tròn thành double.

## 13. Tính kết hợp, tính giao hoán, tính lặp lại và an toàn song song

Để thiết kế một `merge` thật sự sử dụng được trong phân tán, đặt các câu hỏi:

**Tính đóng:** gộp trạng thái phải cùng phiên bản schema và tham số. Không ghép top3 với top5 rồi lặng lẽ trả một bên; code bài này ném lỗi nếu k khác.

**Tính kết hợp:** với mọi A,B,C hợp lệ, `merge(merge(A,B),C)` phải bằng `merge(A,merge(B,C))` theo chuẩn kết quả đã định. Đây là điều kiện cốt lõi cho reduction tree.

**Tính đơn vị:** trạng thái của chunk rỗng phải không làm thay đổi kết quả. Chunk rỗng là tình huống thường gặp khi partition dữ liệu không đều hoặc có worker không nhận bản ghi.

**Tính giao hoán:** nếu hệ thống đổi thứ tự chunk, có được phép không? Numeric stats, frequency và top-k (với tie chuẩn) là giao hoán; Runs và nối chuỗi **không** giao hoán.

**Tính idempotent:** `merge(s,s)=s` có đúng không? Với sum/count/frequency thì **không**; dữ liệu bị gộp hai lần sẽ bị đếm đôi. Với set union thì `A∪A=A`, nhưng không phải điều này làm toàn pipeline tự exactly-once.

**Độ ổn định thứ tự:** gộp bằng Java parallel stream hoặc worker hoàn thành bất kỳ có thể làm thay đổi thứ tự reduction. Với phép không giao hoán, phải giữ encounter order; với floating-point ngay cả phép toán trừu tượng giao hoán cũng có thể khác bit do rounding.

**Độ tương thích sketch:** hash functions, seeds, precision, comparator, schema version phải khớp. “Có hàm merge” trong API không tự chứng minh rằng mọi trạng thái khác phiên bản có thể gộp.

## 14. Chương trình Java 17: bốn trạng thái gộp được

Chương trình **MergeableStreamStatesDemo.java** gồm bốn reducer:

1. **Numeric** — `(count,sum,sumSquares,min,max)`, chính xác bằng BigInteger.
2. **TopK** — giữ k giá trị lớn nhất theo đa tập, cho phép k=0.
3. **Frequencies** — bảng tần suất exact, có thể gộp theo khóa.
4. **Runs** — `(length,prefix,suffix,best)` cho chuỗi 1 liên tiếp, **phải giữ thứ tự**.

Mỗi reducer có phép `merge`; `State` gộp bốn reducer tương ứng. Dữ liệu `int[]` được dùng như một nguồn mẫu cho ví dụ; trong ứng dụng thật, `fromRange` có thể được thay bằng bộ đọc chunk từ file, socket, Kafka partition hoặc một Iterator để không cần lưu toàn bộ luồng.

**Quy tắc thiết kế:** trạng thái là bất biến theo API record (đối với list/map có copy bất biến). Điều này giúp giảm lỗi worker vô tình sửa trạng thái đã được sử dụng ở nhánh merge khác. Tuy nhiên bản thực hành tạo một số đối tượng trung gian để rõ logic; triển khai hiệu năng cao có thể dùng accumulator mutable nội bộ rồi **freeze** trạng thái ở ranh giới chunk.

### Toàn bộ mã Java 17

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.TreeMap;

public class MergeableStreamStatesDemo {
    static void range(int[] a, int from, int to) {
        Objects.requireNonNull(a, "data");
        if (from < 0 || to < from || to > a.length)
            throw new IllegalArgumentException("Invalid range");
    }

    // Exact numeric summary. min/max = null only if count == 0.
    record Numeric(long count, BigInteger sum,
                   BigInteger sumSquares,
                   Integer min, Integer max) {
        static Numeric empty() {
            return new Numeric(0L, BigInteger.ZERO,
                    BigInteger.ZERO, null, null);
        }

        static Numeric ofRange(int[] a, int from, int to) {
            range(a, from, to);
            long count = 0L;
            BigInteger sum = BigInteger.ZERO;
            BigInteger sq = BigInteger.ZERO;
            Integer min = null, max = null;
            for (int i = from; i < to; i++) {
                int x = a[i];
                BigInteger b = BigInteger.valueOf(x);
                count = Math.addExact(count, 1L);
                sum = sum.add(b);
                sq = sq.add(b.multiply(b));
                min = min == null ? x : Math.min(min, x);
                max = max == null ? x : Math.max(max, x);
            }
            return new Numeric(count, sum, sq, min, max);
        }

        Numeric merge(Numeric other) {
            Objects.requireNonNull(other);
            if (count == 0) return other;
            if (other.count == 0) return this;
            return new Numeric(
                    Math.addExact(count, other.count),
                    sum.add(other.sum),
                    sumSquares.add(other.sumSquares),
                    Math.min(min, other.min),
                    Math.max(max, other.max));
        }

        BigInteger varianceNumerator() {
            return BigInteger.valueOf(count)
                    .multiply(sumSquares)
                    .subtract(sum.multiply(sum));
        }

        BigDecimal mean(int scale) {
            if (count == 0)
                throw new IllegalStateException(
                        "Mean undefined for empty stream");
            return new BigDecimal(sum).divide(
                    BigDecimal.valueOf(count),
                    scale, RoundingMode.HALF_UP);
        }

        BigDecimal populationVariance(int scale) {
            if (count == 0)
                throw new IllegalStateException(
                        "Population variance undefined");
            BigInteger n = BigInteger.valueOf(count);
            return new BigDecimal(varianceNumerator())
                    .divide(new BigDecimal(n.multiply(n)),
                            scale, RoundingMode.HALF_UP);
        }

        BigDecimal sampleVariance(int scale) {
            if (count < 2)
                throw new IllegalStateException(
                        "Sample variance requires n >= 2");
            BigInteger n = BigInteger.valueOf(count);
            return new BigDecimal(varianceNumerator())
                    .divide(new BigDecimal(
                            n.multiply(n.subtract(BigInteger.ONE))),
                            scale, RoundingMode.HALF_UP);
        }
    }

    // Top-k of a MULTISET: duplicates count as occurrences.
    record TopK(int k, List<Integer> values) {
        TopK {
            if (k < 0) throw new IllegalArgumentException("k < 0");
            values = List.copyOf(values);
            if (values.size() > k)
                throw new IllegalArgumentException("Too many values");
        }

        static void offer(PriorityQueue<Integer> pq,
                          int k, int x) {
            if (k == 0) return;
            pq.offer(x);
            if (pq.size() > k) pq.poll();
        }

        static TopK fromHeap(int k, PriorityQueue<Integer> pq) {
            List<Integer> vals = new ArrayList<>(pq);
            vals.sort(Comparator.reverseOrder());
            return new TopK(k, vals);
        }

        static TopK ofRange(int[] a, int from, int to, int k) {
            range(a, from, to);
            if (k < 0) throw new IllegalArgumentException("k < 0");
            PriorityQueue<Integer> pq = new PriorityQueue<>();
            for (int i = from; i < to; i++)
                offer(pq, k, a[i]);
            return fromHeap(k, pq);
        }

        TopK merge(TopK other) {
            Objects.requireNonNull(other);
            if (k != other.k)
                throw new IllegalArgumentException(
                        "TopK parameter mismatch");
            PriorityQueue<Integer> pq = new PriorityQueue<>();
            for (int v : values) offer(pq, k, v);
            for (int v : other.values) offer(pq, k, v);
            return fromHeap(k, pq);
        }
    }

    // Exact frequency table. Uses O(number of distinct keys).
    record Frequencies(Map<Integer, Long> counts) {
        Frequencies {
            counts = Map.copyOf(counts);
        }

        static Frequencies ofRange(int[] a, int from, int to) {
            range(a, from, to);
            Map<Integer, Long> freq = new TreeMap<>();
            for (int i = from; i < to; i++) {
                freq.merge(a[i], 1L,
                        (left, right) -> Math.addExact(left, right));
            }
            return new Frequencies(freq);
        }

        Frequencies merge(Frequencies other) {
            Objects.requireNonNull(other);
            Map<Integer, Long> result = new TreeMap<>(counts);
            for (Map.Entry<Integer, Long> e
                    : other.counts.entrySet()) {
                result.merge(e.getKey(), e.getValue(),
                        (left, right) -> Math.addExact(left, right));
            }
            return new Frequencies(result);
        }

        int distinct() {
            return counts.size();
        }
    }

    // Longest consecutive run of value == 1.
    // Order matters: left.merge(right) means left || right.
    record Runs(long length, long prefix,
                long suffix, long best) {
        static Runs empty() {
            return new Runs(0, 0, 0, 0);
        }

        static Runs ofRange(int[] a, int from, int to) {
            range(a, from, to);
            Runs result = empty();
            for (int i = from; i < to; i++) {
                long bit = a[i] == 1 ? 1L : 0L;
                result = result.merge(new Runs(1, bit, bit, bit));
            }
            return result;
        }

        Runs merge(Runs right) {
            Objects.requireNonNull(right);
            long newLength = Math.addExact(length, right.length);
            long newPrefix = prefix == length
                    ? Math.addExact(length, right.prefix)
                    : prefix;
            long newSuffix = right.suffix == right.length
                    ? Math.addExact(right.length, suffix)
                    : right.suffix;
            long across = Math.addExact(suffix, right.prefix);
            long newBest = Math.max(
                    Math.max(best, right.best), across);
            return new Runs(newLength, newPrefix,
                            newSuffix, newBest);
        }
    }

    // Product of four mergeable summaries.
    record State(Numeric numeric, TopK top,
                 Frequencies frequency, Runs runs) {
        static State ofRange(int[] a, int from,
                             int to, int k) {
            range(a, from, to);
            return new State(
                    Numeric.ofRange(a, from, to),
                    TopK.ofRange(a, from, to, k),
                    Frequencies.ofRange(a, from, to),
                    Runs.ofRange(a, from, to));
        }

        State merge(State other) {
            Objects.requireNonNull(other);
            return new State(
                    numeric.merge(other.numeric),
                    top.merge(other.top),
                    frequency.merge(other.frequency),
                    runs.merge(other.runs));
        }
    }

    static int bruteBestRun(int[] a) {
        int best = 0, current = 0;
        for (int x : a) {
            current = x == 1 ? current + 1 : 0;
            best = Math.max(best, current);
        }
        return best;
    }

    static List<Integer> bruteTop3(int[] a) {
        int[] sorted = a.clone();
        Arrays.sort(sorted);
        List<Integer> out = new ArrayList<>();
        for (int i = sorted.length - 1;
                i >= 0 && out.size() < 3; i--)
            out.add(sorted[i]);
        return out;
    }

    static Map<Integer, Long> bruteFrequency(int[] a) {
        Map<Integer, Long> out = new TreeMap<>();
        for (int x : a)
            out.merge(x, 1L, (u, v) -> Math.addExact(u, v));
        return out;
    }

    static void assertDirectOracles(int[] a, State s) {
        long n = 0L;
        BigInteger sum = BigInteger.ZERO;
        BigInteger sq = BigInteger.ZERO;
        Integer min = null, max = null;
        for (int x : a) {
            n++;
            BigInteger b = BigInteger.valueOf(x);
            sum = sum.add(b);
            sq = sq.add(b.multiply(b));
            min = min == null ? x : Math.min(min, x);
            max = max == null ? x : Math.max(max, x);
        }
        Numeric expected = new Numeric(n, sum, sq, min, max);
        if (!s.numeric.equals(expected)
                || !s.top.values.equals(bruteTop3(a))
                || !s.frequency.counts.equals(bruteFrequency(a))
                || s.runs.best != bruteBestRun(a))
            throw new AssertionError("Direct oracle mismatch");
    }

    static class Checked {
        int arrays;
        int partitions;
    }

    // All arrays length 0..6 over {-1,0,1};
    // all ordered 3-way partitions, including empty chunks.
    static void enumerate(int[] a, int at, Checked checked) {
        if (at == a.length) {
            checked.arrays++;
            State full = State.ofRange(a, 0, a.length, 3);
            assertDirectOracles(a, full);

            for (int cut1 = 0; cut1 <= a.length; cut1++) {
                for (int cut2 = cut1;
                        cut2 <= a.length; cut2++) {
                    State left = State.ofRange(a, 0, cut1, 3);
                    State mid = State.ofRange(
                            a, cut1, cut2, 3);
                    State right = State.ofRange(
                            a, cut2, a.length, 3);

                    State leftGrouped =
                            left.merge(mid).merge(right);
                    State rightGrouped =
                            left.merge(mid.merge(right));
                    if (!leftGrouped.equals(rightGrouped)
                            || !leftGrouped.equals(full))
                        throw new AssertionError(
                                "Associativity/direct mismatch");
                    checked.partitions++;
                }
            }
            return;
        }

        for (int x = -1; x <= 1; x++) {
            a[at] = x;
            enumerate(a, at + 1, checked);
        }
    }

    static Checked verify() {
        Checked checked = new Checked();
        for (int n = 0; n <= 6; n++)
            enumerate(new int[n], 0, checked);

        if (checked.arrays != 1093
                || checked.partitions != 27064)
            throw new AssertionError("Unexpected case count");
        return checked;
    }

    public static void main(String[] args) {
        int[] data = {4,-2,7,7,0,3,-5,9,1,9};
        State a = State.ofRange(data, 0, 3, 3);
        State b = State.ofRange(data, 3, 7, 3);
        State c = State.ofRange(data, 7, 10, 3);
        State merged = a.merge(b).merge(c);
        State regrouped = a.merge(b.merge(c));
        State whole = State.ofRange(data, 0, data.length, 3);

        Numeric n = merged.numeric();
        System.out.println("data=" + Arrays.toString(data));
        System.out.println("chunks.counts="
                + Arrays.toString(new long[]{
                    a.numeric().count(),
                    b.numeric().count(),
                    c.numeric().count()}));
        System.out.println("chunks.sums="
                + Arrays.asList(
                    a.numeric().sum(),
                    b.numeric().sum(),
                    c.numeric().sum()));
        System.out.println("merge.equalDirect="
                + merged.equals(whole));
        System.out.println("merge.associativeExample="
                + merged.equals(regrouped));
        System.out.println("numeric.count=" + n.count());
        System.out.println("numeric.sum=" + n.sum());
        System.out.println("numeric.sumSquares=" + n.sumSquares());
        System.out.println("numeric.min=" + n.min());
        System.out.println("numeric.max=" + n.max());
        System.out.println("numeric.mean4="
                + n.mean(4).toPlainString());
        System.out.println("numeric.populationVariance4="
                + n.populationVariance(4).toPlainString());
        System.out.println("numeric.sampleVariance4="
                + n.sampleVariance(4).toPlainString());
        System.out.println("top3=" + merged.top().values());
        System.out.println("frequency="
                + new TreeMap<>(merged.frequency().counts()));
        System.out.println("distinct="
                + merged.frequency().distinct());

        State empty = State.ofRange(data, 0, 0, 3);
        System.out.println("empty.identity="
                + empty.merge(merged).equals(merged)
                + ","
                + merged.merge(empty).equals(merged));
        System.out.println("empty.meanUndefined="
                + (empty.numeric().count() == 0));

        int[] bits = {1,1,0,1,1,1,1,0,1};
        Runs ra = Runs.ofRange(bits, 0, 4);
        Runs rb = Runs.ofRange(bits, 4, 7);
        Runs rc = Runs.ofRange(bits, 7, 9);
        Runs combined = ra.merge(rb).merge(rc);
        System.out.println("runs.chunkBest="
                + Arrays.toString(new long[]{
                    ra.best(), rb.best(), rc.best()}));
        System.out.println("runs.combinedBest="
                + combined.best());
        System.out.println("runs.associative="
                + combined.equals(ra.merge(rb.merge(rc))));

        Runs x = Runs.ofRange(new int[]{1,1}, 0, 2);
        Runs y = Runs.ofRange(new int[]{1,0}, 0, 2);
        System.out.println("runs.orderMatters="
                + !x.merge(y).equals(y.merge(x)));
        System.out.println("runs.AB.best=" + x.merge(y).best());
        System.out.println("runs.BA.best=" + y.merge(x).best());

        int high = Integer.MAX_VALUE;
        Numeric extreme = Numeric.ofRange(
                new int[]{high,high,high}, 0, 3);
        System.out.println("extreme.sum=" + extreme.sum());
        System.out.println("extreme.sumSquares="
                + extreme.sumSquares());

        Checked checked = verify();
        System.out.println("verified.arrays=" + checked.arrays);
        System.out.println("verified.partitions="
                + checked.partitions);
        System.out.println("verification=PASS");
    }
}
~~~

Lưu file tên **MergeableStreamStatesDemo.java**, biên dịch và chạy trên **JDK 17 trở lên**:

~~~bash
javac MergeableStreamStatesDemo.java
java MergeableStreamStatesDemo
~~~

### Đầu ra dự kiến

~~~text
data=[4, -2, 7, 7, 0, 3, -5, 9, 1, 9]
chunks.counts=[3, 4, 3]
chunks.sums=[9, 5, 19]
merge.equalDirect=true
merge.associativeExample=true
numeric.count=10
numeric.sum=33
numeric.sumSquares=315
numeric.min=-5
numeric.max=9
numeric.mean4=3.3000
numeric.populationVariance4=20.6100
numeric.sampleVariance4=22.9000
top3=[9, 9, 7]
frequency={-5=1, -2=1, 0=1, 1=1, 3=1, 4=1, 7=2, 9=2}
distinct=8
empty.identity=true,true
empty.meanUndefined=true
runs.chunkBest=[2, 3, 1]
runs.combinedBest=4
runs.associative=true
runs.orderMatters=true
runs.AB.best=3
runs.BA.best=2
extreme.sum=6442450941
extreme.sumSquares=13835058042397261827
verified.arrays=1093
verified.partitions=27064
verification=PASS
~~~

### Đọc kết quả đúng ý nghĩa

- `merge.equalDirect=true` xác nhận ba trạng thái chunk được gộp thành cùng kết quả với xử lý toàn bộ mảng mẫu. Đây là **một ví dụ**, không tự là định lý cho mọi chunk.
- `merge.associativeExample=true` kiểm hai cách đặt ngoặc trên bộ dữ liệu mẫu.
- `numeric.mean4=3.3000` là `33/10` được làm tròn đến bốn chữ số thập phân; không phải “trung bình của ba mean chunk”.
- `numeric.populationVariance4=20.6100` khác `numeric.sampleVariance4=22.9000` vì mẫu số khác nhau.
- `top3=[9,9,7]` giữ **hai lần xuất hiện của số 9**, đúng multiset.
- `frequency` cho 8 giá trị phân biệt, nhưng tổng các count bằng 10.
- `empty.identity=true,true` xác nhận state rỗng là đơn vị gộp **hai phía** trong ví dụ.
- `runs.chunkBest=[2,3,1]` không đủ nếu lấy max riêng lẻ: kết quả toàn chuỗi **4** do nối qua ranh giới chunk.
- `runs.orderMatters=true` nhấn mạnh **không giao hoán**, dù gộp có tính kết hợp.
- `extreme.sumSquares` lớn hơn Long.MAX_VALUE, cho thấy vì sao code dùng BigInteger.
- `verified.partitions=27064` là số cách chia ba khối được thử trên toàn bộ 1.093 mảng nhỏ; nó không tuyên bố đã kiểm mọi chuỗi vô hạn hay mọi cấu hình phân tán.

## 15. Kiểm thử vét cạn 27.064 phân hoạch

Bộ `verify()` tạo **mọi** chuỗi dài `n=0..6` trên miền ba giá trị `{-1,0,1}`:

\[
\sum_{n=0}^6 3^n
=1+3+9+27+81+243+729
=\boxed{1093}.
\]

Với một chuỗi độ dài n, chọn hai điểm cắt thỏa `0≤cut1≤cut2≤n` để chia thành **ba chunk liên tiếp**, cho phép chunk rỗng. Số cách là:

\[
\binom{n+2}{2}.
\]

Tổng số phân hoạch của tất cả chuỗi:

\[
\sum_{n=0}^{6}3^n\binom{n+2}{2}
=1+9+54+270+1215+5103+20412
=\boxed{27064}.
\]

Với mỗi phân hoạch A||B||C:
1. Xây state A,B,C độc lập.
2. So `(A⊕B)⊕C` và `A⊕(B⊕C)` theo **record equality**.
3. So trạng thái đó với state xây dựng bằng **một lượt đọc toàn bộ dữ liệu**.
4. Đối chiếu thêm top-3, bảng tần suất và chuỗi 1 liên tiếp bằng oracle duyệt trực tiếp/chuẩn sắp xếp.
5. Bao phủ **n=0**, chunk rỗng ở đầu/giữa/cuối, trùng giá trị, số âm, số 0, mọi số 1, số 1 rải rác và chạy dài qua ranh giới.

Kết quả độc lập: **1.093 chuỗi**, **27.064 phân hoạch**, **0 sai khác** cho phép gộp đúng và bảo toàn thứ tự.

Đây là một bộ **property-based exhaustive test trên miền nhỏ**. Nó mạnh hơn việc kiểm vài ví dụ ngẫu nhiên, nhưng không thay cho **chứng minh đại số** đối với mọi n, mọi giá trị int, hay một hệ phân tán thật có lỗi mạng.

### Kiểm thử cực trị riêng

Ba số nguyên cực đại kiểm tra độ chính xác của `sumSquares` vượt long. Trường hợp **top-k có giá trị trùng** kiểm tra không loại trùng; state rỗng kiểm tra phần tử đơn vị. Với triển khai sản xuất, còn phải kiểm tra count overflow, serialization, nhiều node/JDK, retry, input cực lớn và nhất quán schema.

## 16. Vì sao các phép gộp này đúng?

### 16.1. Count, sum, sumSquares

Chuỗi nối có số bản ghi là tổng hai chunk. Tổng giá trị và tổng bình phương cũng là **tổng của các phần tử ở hai phần rời nhau**, nên phép cộng trên từng trường là hợp lệ. Phép cộng số nguyên chính xác kết hợp và giao hoán, tạo monoid với zero. `BigInteger` bảo đảm không overflow trên các trường tổng; count dùng long có kiểm tra `Math.addExact`.

Min/max tương tự vì min/min và max/max có tính kết hợp. Chunk rỗng phải được xử lý riêng để tránh nhầm “min rỗng là 0”.

### 16.2. Top-k

Giả sử một phần tử x bị loại khỏi top-k chunk A. Trong A có ít nhất k lần xuất hiện có thứ tự lớn hơn hoặc bằng x (với tie-break chuẩn nếu cần), nên x không thể là phần tử **bắt buộc** của top-k toàn cục khi thêm B. Vì vậy chỉ cần top-k A và top-k B để tìm top-k hợp dữ liệu. Quy tắc lặp `Top_k(Top_k(A)⊎Top_k(B))` áp dụng cho nhiều chunk; trạng thái rỗng là list rỗng.

### 16.3. Frequencies

Với từng khóa v, số lần xuất hiện ở A||B bằng số lần ở A cộng số lần ở B. Vì vậy map gộp theo khóa bằng cộng, exact và giao hoán. Số distinct sau gộp là **số khóa có count dương**, không phải tổng distinct count của các chunk.

### 16.4. Runs

Mọi đoạn liên tiếp toàn số 1 nằm hoàn toàn trong A, nằm hoàn toàn trong B, hoặc vượt ranh giới bằng `suffix_A+prefix_B`. Công thức merge xét đủ ba trường hợp. Trạng thái `(len,prefix,suffix,best)` mô tả đầy đủ những gì cần biết khi nối thêm một đoạn; vì hai cách đặt ngoặc đều đại diện cùng chuỗi A||B||C, kết quả toán học là như nhau. Đảo A và B thì đại diện một **chuỗi khác**, nên không được tự đổi thứ tự.

## 17. Độ phức tạp và đánh đổi bộ nhớ

| Trạng thái | Xây trên m phần tử | Gộp hai trạng thái | Bộ nhớ một state |
| --- | --- | --- | --- |
| Count/sum/min/max/sumSquares | O(m) phép cập nhật số học | O(1) số trường và phép cộng số lớn | O(1) trường, bit-length tăng |
| Mean qua `(n,sum)` | O(m) | O(1) phép toán lớn | O(1) trường |
| Top-k bằng heap | O(m log k), k>0 | O(k log k) | O(k) |
| Exact frequency map | O(m log D) với TreeMap | O(D log D) điển hình | O(D) |
| Exact distinct set | O(m log D) với TreeSet | O(D log D) điển hình | O(D) |
| Runs `len,prefix,suffix,best` | O(m) | O(1) | O(1) trường |
| Exact oracle lưu toàn bộ dữ liệu | O(m) đọc | Có thể cần O(m) để nối | O(m) |
| HLL/sketch compatible | Phụ thuộc sketch | Phụ thuộc số thanh ghi | Nhỏ/cố định theo cấu hình, **xấp xỉ** |

**Phân biệt chi phí số học bit:** với `BigInteger`, các phép cộng/nhân không O(1) theo độ dài bit; bảng ghi O(1) theo **số trường/tính chất cấu trúc**. Trong code minh họa, xây `Runs` từ singleton record và `TopK` từ heap rõ ràng ưu tiên **dễ kiểm chứng** hơn tối ưu allocation; triển khai performance-critical nên benchmark, giảm object churn và áp dụng reducer phù hợp.

**Không phải mọi thống kê đều có summary kích thước hằng**. Median exact, exact distinct hay bảng tần suất có thể cần thêm bộ nhớ theo số bản ghi/khóa; hãy phát biểu rõ yêu cầu **exact hay approximate** và ngân sách bộ nhớ.

## 18. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Lấy trung bình của trung bình chunk | Sai khi kích thước chunk khác | Gộp count và sum |
| Tính variance bằng trung bình các variance | Thiếu chênh lệch giữa mean nhóm | Gộp raw moments exact hoặc Chan |
| Tính `x*x` với int trước khi ép kiểu | Overflow ngay từ phép nhân | BigInteger trước khi nhân |
| Count long không kiểm tràn | Đếm âm/sai | Math.addExact hoặc BigInteger count |
| Dùng min=0 cho state rỗng | Sai với dãy toàn dương | null/Optional hoặc identity đúng |
| Gộp top-k bằng Set | Mất phần tử trùng | Multiset/min-heap k |
| Gộp top3 với top5 tùy tiện | Sai đặc tả | Kiểm tham số k/schema |
| Lấy distinct(A)+distinct(B) | Đếm trùng các khóa ở hai chunk | Set/map union |
| Coi count map O(1) bộ nhớ | Tăng theo số khóa | Đếm O(D) hoặc sketch approximate |
| Chỉ lưu best run mỗi chunk | Mất run xuyên ranh giới | len,prefix,suffix,best |
| Đảo thứ tự chunk khi gộp Runs | Sai chuỗi cần tính | Giữ offset và thứ tự |
| Coi kết hợp là giao hoán | Đảo dữ liệu có thứ tự | Kiểm riêng commutativity |
| Nghĩ merge cho phép xóa | Min/top-k khó đảo ngược | Thiết kế sliding-window riêng |
| Gộp chunk retry hai lần | Count/sum double count | Dedup/idempotency/offset |
| HLL khác seed/precision đem merge | State không tương thích | Kiểm version/hash/precision |
| Tự gộp hai reservoir bằng chọn 50/50 | Sai với chunk kích thước khác | Cân theo chunk sizes/cơ chế có chứng minh |
| Coi double cộng có kết hợp bitwise | Output có thể khác theo reduction tree | Thứ tự cố định hoặc số học thích hợp |
| Kết quả test nhỏ = chứng minh tổng quát | Không bao phủ mọi input | Chứng minh invariant + test |
| Không xử lý empty chunk | Null/mean chia 0 hoặc mất identity | Định nghĩa state rỗng |
| Chỉ benchmark một máy | Không phát hiện overhead phân tán | Đo CPU, memory, network, GC và throughput |

## 19. Bài tập có đáp án

**Bài 1.** Khi nào một summary được xem là mergeable?

*Đáp án:* Khi có phép gộp trạng thái hợp lệ sao cho `h(A||B)=h(A)⊕h(B)`; để giảm theo nhiều cây ổn định cần tính kết hợp và phần tử đơn vị.

**Bài 2.** Tính kết hợp và giao hoán khác nhau ra sao?

*Đáp án:* Kết hợp thay **cách đặt ngoặc** mà không đổi thứ tự; giao hoán cho phép **đảo hai toán hạng**.

**Bài 3.** Phép ghép chuỗi có kết hợp không? Có giao hoán không?

*Đáp án:* Có kết hợp, không giao hoán. `"ab"+"cd"` khác `"cd"+"ab"`.

**Bài 4.** Trạng thái rỗng cho count/sum nên là gì?

*Đáp án:* `(0,0)`, là đơn vị của phép cộng theo trường.

**Bài 5.** Với min trên luồng rỗng, dùng min=0 có đúng không?

*Đáp án:* Không với dữ liệu toàn dương; cần biểu diễn chưa có giá trị hoặc +∞ theo kiểu phù hợp.

**Bài 6.** A=[0], B=[10,20,30]. Trung bình hai mean không trọng số ra bao nhiêu và đúng là bao nhiêu?

*Đáp án:* Sai ra 10; mean toàn dữ liệu =15.

**Bài 7.** Trạng thái tối thiểu để mean exact cho dữ liệu nguyên là gì?

*Đáp án:* Count và tổng exact; chia ở cuối.

**Bài 8.** Với dữ liệu `[4,-2,7,7,0,3,-5,9,1,9]`, n và sum?

*Đáp án:* n=10, sum=33.

**Bài 9.** SumSquares của dữ liệu bài 8 bằng bao nhiêu?

*Đáp án:* 315.

**Bài 10.** Population variance của bài 8?

*Đáp án:* `(10·315−33²)/10²=20,61`.

**Bài 11.** Sample variance của bài 8?

*Đáp án:* `2061/(10·9)=22,9`.

**Bài 12.** Tại sao không gộp variance bằng trung bình variance chunk?

*Đáp án:* Thiếu phần sai khác trung bình giữa các nhóm; dùng raw moments exact hoặc công thức Chan.

**Bài 13.** Với dữ liệu ba số Integer.MAX_VALUE, sumSquares?

*Đáp án:* `13835058042397261827`, vượt long max.

**Bài 14.** Top3 của dữ liệu bài 8 là gì nếu giữ số lần xuất hiện?

*Đáp án:* `[9,9,7]`.

**Bài 15.** Nếu dùng HashSet để tính top3 có thể sai vì sao?

*Đáp án:* Set bỏ giá trị trùng, trong khi top-k theo occurrence phải giữ chúng.

**Bài 16.** Distinct count của bài 8?

*Đáp án:* 8.

**Bài 17.** Vì sao `distinct(A)+distinct(B)` không phải distinct hợp?

*Đáp án:* Một khóa có thể xuất hiện ở cả A và B; cần xử lý trùng/union.

**Bài 18.** Map frequency merge bằng phép gì?

*Đáp án:* Cộng số lần theo từng khóa, giữ các khóa xuất hiện ở một bên.

**Bài 19.** Exact frequency map có bộ nhớ O(1) không?

*Đáp án:* Không; O(D) với D khóa phân biệt.

**Bài 20.** Khi nào HLL states có thể merge?

*Đáp án:* Khi cùng hash seed/algorithm, precision và định dạng tương thích; kết quả vẫn là ước lượng.

**Bài 21.** Để tính longest consecutive ones có đủ lưu best từng chunk không?

*Đáp án:* Không; cần thêm len,prefix,suffix để nhận diện run vượt ranh giới.

**Bài 22.** Với A=[1,1,0,1], B=[1,1,1], C=[0,1], best toàn chuỗi?

*Đáp án:* 4, do suffix A một số 1 nối prefix B ba số 1.

**Bài 23.** Trạng thái Runs có giao hoán không?

*Đáp án:* Không; A||B và B||A có thể cho best khác nhau.

**Bài 24.** Với A=[1,1], B=[1,0], best(A||B) và best(B||A)?

*Đáp án:* 3 và 2.

**Bài 25.** Tại sao một chunk rỗng phải có summary hợp lệ?

*Đáp án:* Partition không đều có thể tạo chunk rỗng; state rỗng là phần tử đơn vị, không làm thay đổi reduction.

**Bài 26.** Gộp một summary count hai lần có idempotent không?

*Đáp án:* Không; count bị nhân đôi. Retry cần dedup hoặc exactly-once semantics.

**Bài 27.** Vì sao không trừ được min của chunk cũ từ min toàn cục?

*Đáp án:* Nếu chunk cũ chứa min thì state không giữ ứng viên kế tiếp; cần cấu trúc bổ sung.

**Bài 28.** Reservoir k=1 từ chunk kích thước 1 và 99, chọn một trong hai mẫu với xác suất 1/2 có đều không?

*Đáp án:* Không; phần tử chunk nhỏ được xác suất 1/2 thay vì 1/100. Phải cân theo kích thước chunk hoặc dùng thuật toán merge đúng.

**Bài 29.** Trong số thực double, vì sao `(a+b)+c` có thể khác `a+(b+c)`?

*Đáp án:* Làm tròn ở mỗi phép cộng; ví dụ `a=1e16,b=-1e16,c=1` cho 1 hoặc 0.

**Bài 30.** Dùng BigInteger cho sumSquares được gì và mất gì?

*Đáp án:* Tránh overflow, kết quả số nguyên exact; phép tính/độ dài số tăng theo kích thước dữ liệu và độ lớn bit.

**Bài 31.** Có bao nhiêu chuỗi độ dài 0..6 trên ba giá trị?

*Đáp án:* `1+3+...+3^6=1093`.

**Bài 32.** Một chuỗi độ dài n có bao nhiêu cách chia thành ba chunk liên tiếp (cho phép rỗng)?

*Đáp án:* `C(n+2,2)`, vì chọn hai vị trí cắt không giảm.

**Bài 33.** Tổng số partition thử trên 1.093 chuỗi của bài?

*Đáp án:* 27.064.

**Bài 34.** 27.064 thử nghiệm đều pass có thay thế chứng minh tính kết hợp tổng quát không?

*Đáp án:* Không; chỉ xác nhận các input nhỏ đã kiểm. Chứng minh algebra mới áp dụng tổng quát.

**Bài 35.** Khi nào cần giữ thứ tự chunk trong parallel reduction?

*Đáp án:* Khi phép gộp không giao hoán hoặc bài toán đòi encounter order; ví dụ Runs hoặc ghép chuỗi.

**Bài 36.** Cùng cấu hình sketch có bảo đảm hai chunk retry gộp hai lần không sai không?

*Đáp án:* Không mặc nhiên; phải xét idempotency của phép merge và semantics delivery. Sum/count bị double count.

**Bài 37.** Vì sao exact median khó tóm tắt bằng một số median per chunk?

*Đáp án:* Median từng chunk không giữ đủ thông tin về vị trí thứ hạng khi nối; cần thêm thông tin hoặc dùng sketch xấp xỉ với cận.

**Bài 38.** Phương sai mẫu cần tối thiểu bao nhiêu dữ liệu?

*Đáp án:* n≥2; nếu n<2, sample variance theo công thức n−1 không xác định.

## 20. Checklist trước khi triển khai

1. Xác định kết quả cần tính và trạng thái tóm tắt **thực sự đủ thông tin**.
2. Viết công thức `h(A||B)=h(A)⊕h(B)` trước khi viết code.
3. Chứng minh **tính kết hợp** và định nghĩa **trạng thái rỗng**.
4. Kiểm tra **tính giao hoán** riêng; nếu không có, giữ thứ tự chunk/offset.
5. Xác định gộp lặp có idempotent hay cần dedup exactly-once.
6. Với mean, lưu count+sum; với variance, dùng raw moments exact hoặc Chan/Welford phù hợp.
7. Với top-k, giữ trùng occurrence, cùng k, comparator và tie-break ổn định.
8. Với exact distinct/frequency, ghi rõ bộ nhớ phụ thuộc D.
9. Với sketch, kiểm seed/hash/precision và mô tả **xấp xỉ + sai số**.
10. Với dữ liệu số nguyên lớn, tránh overflow trước khi cast; sử dụng kiểu đúng.
11. Với floating-point, tránh giả định tính kết hợp bitwise giữa các cây reduction.
12. Kiểm thử input rỗng, all-equal, negatives, duplicates, chunks có độ dài khác và ranh giới dài.
13. Với ordered state, kiểm thử nối khác thứ tự phải có thể cho kết quả khác.
14. Với sliding window, phân biệt merge với inverse/retract.
15. Với retry, late event, checkpoint, thiết kế delivery semantics và watermark.
16. Benchmark memory, throughput, latency, network và chi phí serialization thực tế.
17. Dùng oracle độc lập/vét cạn trên miền nhỏ bên cạnh chứng minh tổng quát.
18. Công bố assumptions, cấu hình reducer, định dạng state và phiên bản triển khai.

## Tổng kết

Một **trạng thái có thể gộp** là cách biến dữ liệu lớn thành những summary mà phép gộp **bảo toàn ý nghĩa của việc nối dữ liệu**. Tính **kết hợp** và phần tử **đơn vị** giúp song song hóa reduction; tính **giao hoán** chỉ cần khi muốn đổi thứ tự chunk. Cộng count/sum, hợp map tần suất, top-k của hợp đa tập và trạng thái prefix/suffix cho longest run là các ví dụ có cấu trúc khác nhau nhưng cùng tư duy.

Cách triển khai an toàn cần phân biệt **trạng thái exact** với **sketch approximate**, **mergeable** với **invertible**, **kết hợp** với **giao hoán**, và **đúng phép gộp** với **đúng delivery semantics**. Chương trình Java 17 minh họa cả trạng thái số nguyên chính xác qua BigInteger, top-k giữ trùng, exact frequency, và trạng thái Runs có thứ tự; **27.064 cách chia chunk** được kiểm chứng độc lập, còn tính đúng tổng quát được giải thích bằng đại số.

Khi thiết kế một thuật toán luồng hay hệ thống MapReduce, câu hỏi đầu tiên nên là: **“Tôi cần giữ lại chính xác thông tin gì để kết quả sau khi gộp giống xử lý toàn bộ dữ liệu?”** — rồi mới chọn cách partition, cấu trúc trạng thái, giao thức merge và cơ chế vận hành.
