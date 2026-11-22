# Phân rã căn bậc hai và xử lý theo khối

**Phân rã căn bậc hai (square-root decomposition)** chia một dãy hoặc không gian trạng thái thành các **khối liên tiếp**, mỗi khối có khoảng \(\sqrt n\) phần tử. Thay vì đọc từng phần tử của một đoạn dài, ta dùng **thông tin tổng hợp của các khối nằm trọn trong đoạn**, chỉ xử lý trực tiếp hai phần biên. Đây là kỹ thuật trung gian giữa duyệt tuyến tính \(O(n)\) và những cấu trúc phức tạp hơn như Fenwick tree, segment tree. Kỹ thuật cũng tạo nền tảng cho **Mo's algorithm**, cách **sắp xếp lại các truy vấn offline theo khối** để tái sử dụng một cửa sổ [L,R) đang được duy trì.

Bài thuộc nhóm **Truy vấn và ngoại tuyến** của Computer Science Algorithms, trọng tâm là **“Phân rã căn bậc hai và xử lý theo khối”**. Ta sẽ học: cách chọn kích thước khối; đánh số chỉ số và xử lý khối cuối; tổng đoạn + cập nhật điểm; cộng đoạn + tổng đoạn bằng **lazy tag trên từng khối**; bất biến, chứng minh tính đúng và độ phức tạp; **Mo's algorithm cho truy vấn số lượng giá trị phân biệt**; nén tọa độ, sắp xếp zíc-zắc, phân biệt online/offline; chọn kỹ thuật theo kiểu truy vấn; mã **Java 17+** chạy độc lập và các bộ kiểm thử ngẫu nhiên có oracle vét cạn.

## 1. Mô hình bài toán và ký hiệu

Cho mảng \(a[0],a[1],\dots,a[n-1]\), có thể chứa số âm và giá trị lặp lại. Các thao tác thường gặp:

- **Range sum:** tính \(\sum_{i=l}^{r-1} a[i]\).
- **Point set:** gán \(a[p]=x\).
- **Point add:** tăng \(a[p]\) thêm \(\Delta\).
- **Range add:** tăng mọi \(a[i]\), \(l\le i<r\), thêm \(\Delta\).
- **Distinct count:** đếm bao nhiêu giá trị khác nhau trong đoạn.

Trong bài này **mọi đoạn dùng quy ước nửa mở [l,r)**, nghĩa là có l nhưng **không có r**:

\[
0\le l\le r\le n.
\]

Đoạn rỗng \([l,l)\) có tổng bằng 0 và số giá trị phân biệt bằng 0. Đây là một quy ước rất hữu ích vì **độ dài đoạn = r−l**. Nếu đề dùng đoạn đóng [l,r], hãy chuyển sang [l,r+1) sau khi xác nhận \(r<n\).

### Online và offline trong ngữ cảnh này

**Online queries:** nhận một thao tác, phải trả lời ngay trước khi biết các thao tác sau. Ví dụ: truy vấn tổng, rồi gán một phần tử, rồi truy vấn tiếp. Phân rã khối lưu tổng và lazy tag hỗ trợ kiểu này.

**Offline queries:** biết trước **toàn bộ danh sách truy vấn**, được phép **sắp xếp lại thứ tự tính toán**, miễn kết quả cuối trả về đúng vị trí truy vấn ban đầu. **Mo's algorithm** thuộc nhóm này. Nếu có cập nhật chen giữa các truy vấn, không được tùy ý đổi thứ tự truy vấn trên **các phiên bản mảng khác nhau** mà bỏ qua thời điểm cập nhật.

## 2. Ý tưởng phân khối với kích thước B

Chọn kích thước khối nguyên \(B\ge1\). Mỗi chỉ số i thuộc khối:

\[
\operatorname{block}(i)=\left\lfloor\frac i B\right\rfloor.
\]

Khối b chứa đoạn chỉ số:

\[
[bB,\ \min(n,(b+1)B)).
\]

Số khối:

\[
K=\left\lceil\frac nB\right\rceil.
\]

Nếu n=0, không có khối nào; đặt B=1 trong mã để tránh chia cho 0. Nếu n>0, một lựa chọn tiêu chuẩn là \(B=\max(1,\lfloor\sqrt n\rfloor)\). Chọn \(\lceil\sqrt n\rceil\) cũng hợp lệ; số thao tác thực tế có thể khác một chút.

### Ví dụ n=10, B=3

| Khối | Chỉ số được chứa | Độ dài |
| --- | --- | ---: |
| 0 | 0,1,2 | 3 |
| 1 | 3,4,5 | 3 |
| 2 | 6,7,8 | 3 |
| 3 | 9 | 1 |

Khối cuối **chỉ có một phần tử**, không phải ba. Không được đọc hoặc cập nhật vượt n chỉ vì công thức \((b+1)B\) vượt khỏi mảng.

Với đoạn [2,9), ta có thể xử lý:

- Phần đầu chưa đủ khối: chỉ số 2.
- Hai khối đầy đủ: [3,6) và [6,9).
- Không có phần cuối vì r=9 đúng biên khối.

Mọi phần tử trong [2,9) được tính **đúng một lần**; không có phần tử nào nằm ngoài đoạn bị đưa vào tổng.

## 3. Vì sao B≈√n?

Giả sử mỗi khối lưu tổng của các phần tử. Để trả lời một đoạn:

- Có nhiều nhất khoảng \(n/B\) khối trọn vẹn cần gộp.
- Hai phần biên chưa trọn khối tổng cộng xử lý nhiều nhất \(O(B)\) phần tử.

Vì vậy:

\[
T_{\text{range query}}=O(B+n/B).
\]

Chọn B cân bằng hai thành phần \(B\) và \(n/B\): \(B\approx\sqrt n\), suy ra \(O(\sqrt n)\) cho mỗi truy vấn.

Ví dụ n=10.000:

- B=1: có thể phải xem tới 10.000 khối.
- B=100: tối đa khoảng 100 khối đầy đủ và khoảng 200 phần tử biên.
- B=10.000: gần như chỉ có một khối và có thể phải đọc nhiều phần tử biên cho đoạn ngắn.

**Đây là cách cân bằng một cận trên**, không phải khẳng định mọi truy vấn luôn tốn đúng \(\sqrt n\) bước. Nếu đoạn rất ngắn, chỉ cần duyệt vài phần tử; nếu là toàn mảng và khối khớp hoàn toàn, dùng tổng khối rất nhanh.

Với dữ liệu cụ thể, kích thước 128, 256, 512… đôi khi nhanh hơn \(\lfloor\sqrt n\rfloor\) vì cache CPU và kiểu thao tác, nhưng phải benchmark trước khi kết luận.

## 4. Phương án cơ bản: tổng đoạn và cập nhật một điểm

Lưu hai mảng:

- `value[i]`: giá trị thực của phần tử i.
- `blockSum[b]`: tổng mọi phần tử trong khối b.

Bất biến là:

\[
\operatorname{blockSum}[b]=
\sum_{i=bB}^{\min(n,(b+1)B)-1}\operatorname{value}[i].
\]

### Tiền xử lý

Duyệt i=0..n−1, cộng `value[i]` vào `blockSum[i/B]`. Thời gian O(n), bộ nhớ O(n) nếu lưu cả bản sao value và tổng khối, trong đó riêng tổng khối cần \(O(n/B)\).

### Truy vấn tổng [l,r)

Đi từ i=l. Nếu i là **đầu khối** và khối đó nằm trọn trong [i,r), cộng `blockSum[i/B]` rồi nhảy qua cuối khối. Nếu không, cộng `value[i]` và tăng i một.

Giả mã:

~~~text
RANGE_SUM(l,r):
    require 0 <= l <= r <= n
    ans = 0
    i = l
    while i < r:
        b = i / B
        end = min(n, (b + 1) * B)
        if i == b * B and end <= r:
            ans += blockSum[b]
            i = end
        else:
            ans += value[i]
            i++
    return ans
~~~

Với khối cuối thiếu phần tử, **end phải lấy min(n,...)**; như vậy có thể dùng cả tổng khối cuối khi [l,r) bao trọn khối ấy.

### Cập nhật điểm

Để gán `value[p]=x`:

\[
\Delta=x-\operatorname{value}[p].
\]

Sau đó:

- `value[p]=x`.
- `blockSum[p/B]+=Δ`.

Thời gian O(1), vì chỉ một khối bị ảnh hưởng. Với **point add**, trực tiếp cộng Δ vào value và blockSum tương ứng, cũng O(1).

### Chứng minh tính đúng

**Khởi tạo:** mỗi phần tử i được cộng đúng một lần vào blockSum của khối chứa i, nên bất biến tổng khối đúng.

**Cập nhật điểm:** chỉ có giá trị tại p đổi một lượng Δ; khối của p đổi tổng đúng Δ, các khối khác không đổi, nên bất biến được duy trì.

**Truy vấn:** vòng lặp duy trì rằng ans là tổng của đoạn [l,i) đã xử lý. Mỗi bước hoặc cộng một phần tử i, hoặc cộng cả khối [i,end) nằm trọn trong truy vấn. Các khoảng ấy không chồng lấn và tiến dần tới r. Khi i=r, ans chính là tổng [l,r).

## 5. Cập nhật cả đoạn: lazy tag theo khối

Giả sử thao tác chuyển thành:

- `rangeAdd(l,r,delta)`: tăng tất cả phần tử trong [l,r) thêm delta.
- `rangeSum(l,r)`: tính tổng các phần tử hiện tại.

Nếu với mỗi rangeAdd đều sửa từng phần tử, một cập nhật trên đoạn dài có thể tốn O(n). Ta có thể lưu **lazy tag** cho từng khối để không sửa trực tiếp các phần tử bên trong khối đầy đủ.

### Ba mảng trạng thái

- `base[i]`: giá trị cơ sở của phần tử i.
- `lazy[b]`: lượng tăng chung đang được gắn với **toàn bộ** khối b.
- `total[b]`: **tổng các giá trị thực** trong khối b.

Với i thuộc khối b:

\[
\operatorname{actual}[i]=\operatorname{base}[i]+\operatorname{lazy}[b].
\]

Với khối b có độ dài \(\operatorname{len}_b\):

\[
\operatorname{total}[b]
=\sum_{i\in b}\operatorname{base}[i]
+\operatorname{lazy}[b]\cdot\operatorname{len}_b.
\]

**Bất biến này là trung tâm của thuật toán.**

### Cập nhật một khối trọn vẹn

Nếu toàn bộ khối b nằm trong [l,r), ta không cần chạm từng phần tử:

- `lazy[b] += delta`.
- `total[b] += delta * len_b`.

Lý do: mọi phần tử của khối tăng delta nên tổng tăng chính xác \(\operatorname{len}_b\cdot\Delta\).

### Cập nhật phần biên

Nếu chỉ sửa một phần của khối b, ta **không được tăng lazy[b]**, vì làm vậy sẽ tác động lên cả phần tử nằm ngoài đoạn. Thay vào đó, với từng i được sửa:

- `base[i] += delta`.
- `total[b] += delta`.

**Không cần push lazy trước** trong biến thể này: actual[i] vẫn là base[i]+lazy[b], còn cập nhật một phần tử bằng cách tăng base[i] trực tiếp. Đây là một thiết kế nhất quán; không được trộn nó với một thiết kế khác đòi hỏi push lazy mà quên cập nhật lại tổng khối.

### Truy vấn

Nếu khối trọn vẹn được bao phủ, cộng `total[b]`. Nếu chỉ chạm một phần tử biên, cộng `base[i]+lazy[b]`.

Vẫn có \(O(B+n/B)=O(\sqrt n)\) thời gian cho rangeAdd và rangeSum, và O(n) bộ nhớ tổng nếu lưu base cùng các mảng tổng khối/lazy.

## 6. Vì sao lazy theo khối hoạt động đúng?

Có thể chứng minh bằng quy nạp theo dãy thao tác.

**Trạng thái ban đầu:** mọi lazy bằng 0, base chính là input, total là tổng input trong khối. Hai bất biến đúng.

**Range add vào khối trọn vẹn:** lazy tăng Δ, mọi actual[i] trong khối tăng Δ. Total tăng Δ×độ dài, đúng bằng tổng các actual mới.

**Range add vào một phần khối:** chỉ base[i] của những chỉ số được chọn tăng Δ, lazy giữ nguyên. Do đó actual[i] tăng đúng Δ ở các vị trí ấy và không đổi ở các vị trí khác. Total cộng Δ cho mỗi phần tử được sửa.

**Range sum:** các khối trọn vẹn dùng total; các phần biên dùng base+lazy. Vì các khoảng không chồng lấn và phủ hết [l,r), tổng trả về đúng.

### Ví dụ có hai cập nhật chồng lấn

Mảng:

`[5,1,5,2,3,2,4,5,1,3]`.

Tổng ban đầu 31.

Cập nhật `add([2,9),+4)`: 7 phần tử tăng 4, nên tổng là \(31+7\cdot4=59\). Giá trị ở chỉ số 2 đổi từ 5 thành 9, tổng [1,6) đổi từ 13 thành 29.

Tiếp theo `add([0,3),−2)`: ba phần tử đầu giảm 2, tổng mới là \(59-3\cdot2=53\). Giá trị ở chỉ số 2 bây giờ bằng \(5+4-2=7\). Tổng [0,3) là \(5+1+5+4-6=9\). Tổng [5,10) là 31.

Nếu chương trình dùng total của khối trọn vẹn nhưng quên cộng lazy khi đọc **phần biên**, các kết quả sẽ sai sau những cập nhật kiểu này.

## 7. Phân khối không đồng nghĩa với mọi bài đều O(√n)

Kỹ thuật trên phù hợp vì phép toán **tổng** có khả năng gộp các khối độc lập. Một số đại lượng khác cũng hỗ trợ:

- **Min/max đoạn:** lưu min/max của khối và quét phần biên. Nhưng nếu cập nhật điểm làm mất phần tử nhỏ nhất/lớn nhất, có thể phải quét lại cả khối O(B).
- **Số phần tử đáp ứng điều kiện:** lưu số đếm theo khối; một số truy vấn có thể gộp bằng phép cộng.
- **Tổng bình phương hoặc mômen:** lưu thêm tổng cần thiết và cập nhật các tổng theo công thức đại số.
- **Đếm giá trị phân biệt trong đoạn:** **không thể** chỉ cộng số distinct của từng khối vì cùng một giá trị có thể xuất hiện ở nhiều khối. Cần một cấu trúc thích hợp hoặc thuật toán khác như Mo.

**Không có phép biến đổi “chia khối rồi cộng trực tiếp” tổng quát** cho mọi hàm truy vấn. Trước hết phải trả lời: **các kết quả khối có gộp được chính xác không, và cần lưu trạng thái gì để cập nhật?**

## 8. Mo's algorithm: chuyển bài sang truy vấn offline

Một trường hợp quan trọng của xử lý theo khối là **Mo's algorithm**. Nó không lưu tổng độc lập cho từng khối theo nghĩa trên. Thay vào đó, nó:

1. Nhận **toàn bộ danh sách truy vấn** [l,r) trước khi tính.
2. Chia miền các **đầu trái l** thành các khối dài khoảng B.
3. **Sắp xếp truy vấn** theo khối của l và theo r trong từng nhóm.
4. Duy trì một **cửa sổ hiện tại [L,R)** bằng cách thêm/bớt phần tử ở bốn đầu.
5. Trả đáp án về **thứ tự truy vấn ban đầu**, không phải thứ tự đã sắp xếp.

Mo phù hợp khi có thể cập nhật đáp án của cửa sổ bằng các phép thêm/bớt phần tử nhanh, nhưng không có phép gộp đáp án khối đơn giản.

### Bài toán mẫu: distinct count trên mảng tĩnh

Với mỗi [l,r), hãy đếm số **giá trị khác nhau** trong a[l..r−1].

Ta giữ:

- `frequency[v]`: số lần giá trị v xuất hiện trong cửa sổ hiện tại.
- `distinct`: số v có frequency[v]>0.

Khi **thêm** phần tử x:
- Nếu frequency[x] đang bằng 0, tăng distinct.
- Tăng frequency[x].

Khi **xóa** phần tử x:
- Giảm frequency[x].
- Nếu frequency[x] còn 0, giảm distinct.

Bốn thao tác con đều O(1) khi giá trị được mã hóa thành chỉ số mảng tần suất.

### Cửa sổ nửa mở [L,R)

Để chuyển từ [L,R) hiện tại sang một truy vấn [l,r):

~~~text
while L > l:
    L--
    ADD(a[L])
while R < r:
    ADD(a[R])
    R++
while L < l:
    REMOVE(a[L])
    L++
while R > r:
    R--
    REMOVE(a[R])

answer[id] = distinct
~~~

Thứ tự mở rộng trái/phải trước khi thu hẹp giúp cửa sổ luôn hợp lệ, kể cả khi chuyển giữa những truy vấn rỗng và không rỗng.

**Bất biến:** sau mỗi thao tác, frequency mô tả chính xác số lần xuất hiện của từng giá trị trong [L,R), còn distinct là số giá trị có frequency>0. Khi L=l và R=r, distinct chính là đáp án truy vấn.

## 9. Sắp xếp truy vấn theo khối của l

Mỗi truy vấn có chỉ số gốc id, đầu l và đầu r. Với B≈√n:

- Khóa chính: \(\lfloor l/B\rfloor\).
- Trong cùng một khối trái, sắp r **tăng dần**.

Một tối ưu thực tiễn gọi là **zigzag/alternating order**:

- Khối trái chẵn: sắp r tăng dần.
- Khối trái lẻ: sắp r giảm dần.

Mục tiêu là giảm đoạn đường mà con trỏ R phải chạy ngược lại khi đổi nhóm. Vẫn phải trả kết quả theo id gốc.

### Vì sao không sắp theo l rồi r thông thường?

Nếu chỉ đi theo l nhưng r nhảy liên tục, con trỏ R có thể phải di chuyển gần n phần tử ở mỗi truy vấn, dẫn tới O(nq) thời gian. Mo nhóm các truy vấn để các cửa sổ gần nhau theo một trật tự có kiểm soát.

### Phân tích số bước di chuyển

Đặt q là số truy vấn, B là kích thước khối trái.

- **L** di chuyển tối đa O(B) giữa hai truy vấn cùng khối và O(n) tổng cộng khi chuyển qua các khối theo thứ tự, nên O(qB+n).
- **R** chạy qua tối đa O(n) vị trí trong mỗi nhóm khối trái (với sắp tăng/giảm có thứ tự), có khoảng n/B nhóm, nên O(n²/B).
- Mỗi bước thêm/xóa tốn O(1) cho ví dụ distinct count.

Vậy:

\[
T_{\text{moves}}=O(qB+n+n^2/B).
\]

Với \(B\approx\sqrt n\):

\[
T_{\text{moves}}=O((n+q)\sqrt n).
\]

Còn có chi phí sắp xếp q truy vấn O(q log q) và **nén tọa độ** O(n log n). Tổng:

\[
O(n\log n+q\log q+(n+q)\sqrt n).
\]

Bộ nhớ O(n+q+u), với u là số giá trị phân biệt trong mảng (u≤n).

**Lưu ý:** độ phức tạp này nói về mảng **tĩnh**, không có cập nhật dữ liệu giữa các truy vấn. Bản Mo mở rộng theo trục thời gian để xử lý update là một thuật toán khác, cần rollback/apply update và một thứ tự ba chiều, không được lẫn với bản hai chiều ở đây.

## 10. Nén tọa độ và giá trị âm

Giá trị mảng có thể là:

`[-1000000000, 5, 5, 2147483647, -1000000000]`.

Không thể tạo trực tiếp mảng frequency có chỉ số −1000000000 hoặc kích thước hơn hai tỷ. Hãy:

1. Tạo bản sao mảng, sắp xếp tăng dần.
2. Loại trùng để có dãy giá trị phân biệt.
3. Với mỗi a[i], dùng binary search để tìm **rank từ 0 đến u−1**.
4. Thực hiện frequency[rank] thay vì frequency[a[i]].

Nén tọa độ **giữ nguyên quan hệ bằng nhau**, nên **không thay** distinct count. Dù có số âm hoặc `Integer.MIN_VALUE` / `Integer.MAX_VALUE`, rank vẫn là số nguyên không âm nhỏ.

Nếu so các giá trị lớn trong comparator, nên dùng `Integer.compare(x,y)` thay vì `x-y` có thể tràn int.

## 11. Ví dụ Mo bằng tay

Mảng:

`a=[5,1,5,2,3,2,4,5,1,3]`.

Các truy vấn và đáp án:

| id | [l,r) | Các giá trị trong đoạn | Số giá trị khác nhau |
| ---: | --- | --- | ---: |
| 0 | [0,10) | 5,1,5,2,3,2,4,5,1,3 | 5 |
| 1 | [0,3) | 5,1,5 | 2 |
| 2 | [2,7) | 5,2,3,2,4 | 4 |
| 3 | [4,9) | 3,2,4,5,1 | 5 |
| 4 | [5,5) | Rỗng | 0 |
| 5 | [7,10) | 5,1,3 | 3 |

Dù Mo thực thi theo thứ tự sắp xếp khối, kết quả vẫn trả:

`[5,2,4,5,0,3]`.

**Không** cộng distinct của các khối riêng lẻ. Ví dụ các khối [0,3) và [3,6) cùng chứa 5 hoặc 2 tùy dữ liệu; tổng số distinct của từng khối có thể đếm trùng giá trị.

## 12. Nên dùng phân khối, Mo, Fenwick hay segment tree?

| Bài toán | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Range sum + point set/add online | Fenwick tree, segment tree, hoặc sqrt decomposition | Fenwick O(log n); sqrt O(√n) query và O(1) point update |
| Range add + range sum online | Lazy segment tree, Fenwick đôi hoặc lazy sqrt blocks | Lazy sqrt blocks có O(√n) hai thao tác, dễ quan sát bất biến |
| Static range distinct với nhiều query biết trước | Mo hoặc các phương án offline chuyên biệt | Không gộp trực tiếp distinct từ block sums |
| Static range minimum | Sparse table / segment tree / sqrt blocks | Sparse table O(1) query sau tiền xử lý cho dữ liệu không cập nhật |
| Nhiều cập nhật xen kẽ distinct queries | Cấu trúc động phù hợp hoặc Mo có modifications | Không được áp Mo tĩnh rồi đổi thứ tự qua các cập nhật |
| q rất ít, n nhỏ | Duyệt trực tiếp | Overhead chia khối/sort/nén có thể không đáng |

**Độ phức tạp không phải yếu tố duy nhất:** dạng cập nhật, mức phức tạp triển khai, bộ nhớ, tính khả thi của phép gộp, nhu cầu trả lời tức thời, phân bố kích thước đoạn và ràng buộc thời gian đều ảnh hưởng lựa chọn.

## 13. Chương trình Java 17+ hoàn chỉnh

Lưu thành **`SqrtDecompositionDemo.java`**. Chương trình chứa ba mô-đun:

1. `BlockSum`: tiền xử lý tổng khối; `rangeSum(l,r)`, `pointSet(index,value)`, `pointAdd(index,delta)`. Các truy vấn là **online**.
2. `LazyRangeAddSum`: giữ base, lazy, total theo khối; hỗ trợ `rangeAdd(l,r,delta)`, `rangeSum(l,r)` và `valueAt(i)`, cũng **online**.
3. `moDistinct`: nhận toàn bộ query [l,r), nén tọa độ, sắp xếp zigzag theo \(\lfloor l/B\rfloor\), duy trì cửa sổ và trả kết quả theo id gốc. Đây là xử lý **offline** trên mảng tĩnh.

Mỗi lớp kiểm tra chỉ số, hỗ trợ đoạn rỗng và mảng rỗng trong các truy vấn hợp lệ. Các phép tính tổng dùng `long` để giảm nguy cơ tràn so với int cho dữ liệu lớn vừa phải; vẫn phải cân nhắc overflow long nếu n và giá trị quá lớn.

### Mã Java đầy đủ

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Random;
import java.util.Set;

public class SqrtDecompositionDemo {

    static void checkRange(int left, int right, int n) {
        if (left < 0 || right < left || right > n) {
            throw new IllegalArgumentException(
                    "Require 0 <= left <= right <= n");
        }
    }

    static void checkIndex(int index, int n) {
        if (index < 0 || index >= n) {
            throw new IllegalArgumentException(
                    "Index outside array");
        }
    }

    static int blockSize(int n) {
        return Math.max(1, (int) Math.sqrt(n));
    }

    // Online range sums and point assignments/additions.
    static final class BlockSum {
        final int n;
        final int size;
        final long[] value;
        final long[] blockTotal;

        BlockSum(int[] input) {
            if (input == null)
                throw new IllegalArgumentException("Null input");
            n = input.length;
            size = blockSize(n);
            value = new long[n];
            blockTotal = new long[(n + size - 1) / size];

            for (int i = 0; i < n; i++) {
                value[i] = input[i];
                blockTotal[i / size] += value[i];
            }
        }

        long rangeSum(int left, int right) {
            checkRange(left, right, n);
            long result = 0;
            int i = left;

            while (i < right) {
                int b = i / size;
                int end = Math.min(n, (b + 1) * size);
                if (i == b * size && end <= right) {
                    result += blockTotal[b];
                    i = end;
                } else {
                    result += value[i];
                    i++;
                }
            }
            return result;
        }

        void pointSet(int index, long newValue) {
            checkIndex(index, n);
            long delta = newValue - value[index];
            value[index] = newValue;
            blockTotal[index / size] += delta;
        }

        void pointAdd(int index, long delta) {
            checkIndex(index, n);
            pointSet(index, value[index] + delta);
        }

        int blockCount() {
            return blockTotal.length;
        }
    }

    // Online range additions and range sums with block lazy tags.
    static final class LazyRangeAddSum {
        final int n;
        final int size;
        final long[] base;
        final long[] lazy;
        final long[] blockTotal;

        LazyRangeAddSum(int[] input) {
            if (input == null)
                throw new IllegalArgumentException("Null input");
            n = input.length;
            size = blockSize(n);
            base = new long[n];
            int blocks = (n + size - 1) / size;
            lazy = new long[blocks];
            blockTotal = new long[blocks];

            for (int i = 0; i < n; i++) {
                base[i] = input[i];
                blockTotal[i / size] += base[i];
            }
        }

        void rangeAdd(int left, int right, long delta) {
            checkRange(left, right, n);
            int i = left;

            while (i < right) {
                int b = i / size;
                int end = Math.min(n, (b + 1) * size);

                if (i == b * size && end <= right) {
                    // Every element in this block changes.
                    lazy[b] += delta;
                    blockTotal[b] += delta * (end - i);
                    i = end;
                } else {
                    // Only this border element changes.
                    base[i] += delta;
                    blockTotal[b] += delta;
                    i++;
                }
            }
        }

        long rangeSum(int left, int right) {
            checkRange(left, right, n);
            long result = 0;
            int i = left;

            while (i < right) {
                int b = i / size;
                int end = Math.min(n, (b + 1) * size);

                if (i == b * size && end <= right) {
                    result += blockTotal[b];
                    i = end;
                } else {
                    result += base[i] + lazy[b];
                    i++;
                }
            }
            return result;
        }

        long valueAt(int index) {
            checkIndex(index, n);
            return base[index] + lazy[index / size];
        }
    }

    record Query(int left, int right, int id) {}

    // Mo's algorithm for DISTINCT values in STATIC ranges [l,r).
    static int[] moDistinct(int[] input, int[][] ranges) {
        if (input == null || ranges == null)
            throw new IllegalArgumentException("Null Mo input");

        int n = input.length;
        int q = ranges.length;
        int size = blockSize(n);

        // Coordinate compression handles negatives and huge ints.
        int[] sorted = input.clone();
        Arrays.sort(sorted);
        int unique = 0;
        for (int v : sorted) {
            if (unique == 0 || sorted[unique - 1] != v)
                sorted[unique++] = v;
        }

        int[] compressed = new int[n];
        for (int i = 0; i < n; i++) {
            compressed[i] = Arrays.binarySearch(
                    sorted, 0, unique, input[i]);
        }

        Query[] order = new Query[q];
        for (int id = 0; id < q; id++) {
            if (ranges[id] == null || ranges[id].length != 2)
                throw new IllegalArgumentException("Invalid query");
            int left = ranges[id][0];
            int right = ranges[id][1];
            checkRange(left, right, n);
            order[id] = new Query(left, right, id);
        }

        // Alternating right-end direction reduces pointer resets.
        Arrays.sort(order, (x, y) -> {
            int bx = x.left() / size;
            int by = y.left() / size;
            if (bx != by) return Integer.compare(bx, by);
            if ((bx & 1) == 0)
                return Integer.compare(x.right(), y.right());
            return Integer.compare(y.right(), x.right());
        });

        int[] freq = new int[unique];
        int[] answer = new int[q];
        int left = 0;
        int right = 0;
        int distinct = 0;

        for (Query query : order) {
            while (left > query.left()) {
                int code = compressed[--left];
                if (freq[code]++ == 0) distinct++;
            }
            while (right < query.right()) {
                int code = compressed[right++];
                if (freq[code]++ == 0) distinct++;
            }
            while (left < query.left()) {
                int code = compressed[left++];
                if (--freq[code] == 0) distinct--;
            }
            while (right > query.right()) {
                int code = compressed[--right];
                if (--freq[code] == 0) distinct--;
            }
            answer[query.id()] = distinct;
        }
        return answer;
    }

    // Slow independent oracles for randomized QA.
    static long bruteSum(long[] a, int left, int right) {
        long result = 0;
        for (int i = left; i < right; i++) result += a[i];
        return result;
    }

    static int bruteDistinct(int[] a, int left, int right) {
        Set<Integer> seen = new HashSet<>();
        for (int i = left; i < right; i++) seen.add(a[i]);
        return seen.size();
    }

    static void randomPointTests(Random random) {
        for (int test = 0; test < 550; test++) {
            int n = random.nextInt(101); // Include n=0.
            int[] initial = new int[n];
            long[] brute = new long[n];

            for (int i = 0; i < n; i++) {
                initial[i] = random.nextInt(201) - 100;
                brute[i] = initial[i];
            }

            BlockSum ds = new BlockSum(initial);
            for (int op = 0; op < 140; op++) {
                int type = random.nextInt(3);
                if (type == 0 && n > 0) {
                    int index = random.nextInt(n);
                    long value = random.nextInt(301) - 150;
                    ds.pointSet(index, value);
                    brute[index] = value;
                } else if (type == 1 && n > 0) {
                    int index = random.nextInt(n);
                    long delta = random.nextInt(301) - 150;
                    ds.pointAdd(index, delta);
                    brute[index] += delta;
                } else {
                    int left = random.nextInt(n + 1);
                    int right = left + random.nextInt(n - left + 1);
                    long actual = ds.rangeSum(left, right);
                    long expected = bruteSum(brute, left, right);
                    if (actual != expected)
                        throw new AssertionError(
                                "Point model mismatch at "
                                + test + ":" + op);
                }
            }
        }
        System.out.println("pointRandom=PASS (550 cases)");
    }

    static void randomLazyTests(Random random) {
        for (int test = 0; test < 550; test++) {
            int n = random.nextInt(101);
            int[] initial = new int[n];
            long[] brute = new long[n];

            for (int i = 0; i < n; i++) {
                initial[i] = random.nextInt(201) - 100;
                brute[i] = initial[i];
            }

            LazyRangeAddSum ds = new LazyRangeAddSum(initial);
            for (int op = 0; op < 140; op++) {
                int type = random.nextInt(3);
                if (type == 0) {
                    int left = random.nextInt(n + 1);
                    int right = left + random.nextInt(n - left + 1);
                    long delta = random.nextInt(201) - 100;
                    ds.rangeAdd(left, right, delta);
                    for (int i = left; i < right; i++)
                        brute[i] += delta;
                } else if (type == 1 && n > 0) {
                    int index = random.nextInt(n);
                    if (ds.valueAt(index) != brute[index])
                        throw new AssertionError(
                                "Lazy point mismatch at "
                                + test + ":" + op);
                } else {
                    int left = random.nextInt(n + 1);
                    int right = left + random.nextInt(n - left + 1);
                    if (ds.rangeSum(left, right)
                            != bruteSum(brute, left, right))
                        throw new AssertionError(
                                "Lazy range mismatch at "
                                + test + ":" + op);
                }
            }
        }
        System.out.println("lazyRandom=PASS (550 cases)");
    }

    static void randomMoTests(Random random) {
        for (int test = 0; test < 420; test++) {
            int n = random.nextInt(81);
            int[] input = new int[n];

            for (int i = 0; i < n; i++) {
                int kind = random.nextInt(31);
                if (kind == 0)
                    input[i] = Integer.MIN_VALUE;
                else if (kind == 1)
                    input[i] = Integer.MAX_VALUE;
                else
                    input[i] = random.nextInt(31) - 15;
            }

            int q = random.nextInt(101);
            int[][] ranges = new int[q][2];
            for (int id = 0; id < q; id++) {
                int left = random.nextInt(n + 1);
                int right = left + random.nextInt(n - left + 1);
                ranges[id][0] = left;
                ranges[id][1] = right;
            }

            int[] actual = moDistinct(input, ranges);
            for (int id = 0; id < q; id++) {
                int expected = bruteDistinct(
                        input, ranges[id][0], ranges[id][1]);
                if (actual[id] != expected)
                    throw new AssertionError(
                            "Mo mismatch at " + test + ":" + id);
            }
        }
        System.out.println("moRandom=PASS (420 cases)");
    }

    public static void main(String[] args) {
        int[] a = {5, 1, 5, 2, 3, 2, 4, 5, 1, 3};
        BlockSum point = new BlockSum(a);
        System.out.println("array=" + Arrays.toString(a));
        System.out.println("blockSize=" + point.size
                + " blockCount=" + point.blockCount());
        System.out.println("point initial total="
                + point.rangeSum(0, 10)
                + " middle=" + point.rangeSum(2, 8)
                + " empty=" + point.rangeSum(5, 5));

        point.pointSet(3, 9);
        point.pointAdd(9, -5);
        System.out.println("point after total="
                + point.rangeSum(0, 10)
                + " middle=" + point.rangeSum(2, 8)
                + " local=" + point.rangeSum(3, 6)
                + " index9=" + point.value[9]);

        LazyRangeAddSum lazy = new LazyRangeAddSum(a);
        System.out.println("lazy initial total="
                + lazy.rangeSum(0, 10));
        lazy.rangeAdd(2, 9, 4);
        System.out.println("lazy after first total="
                + lazy.rangeSum(0, 10)
                + " sub[1,6)=" + lazy.rangeSum(1, 6)
                + " value[2]=" + lazy.valueAt(2));
        lazy.rangeAdd(0, 3, -2);
        System.out.println("lazy after second total="
                + lazy.rangeSum(0, 10)
                + " head[0,3)=" + lazy.rangeSum(0, 3)
                + " tail[5,10)=" + lazy.rangeSum(5, 10)
                + " value[2]=" + lazy.valueAt(2));

        int[][] queries = {
            {0, 10}, {0, 3}, {2, 7},
            {4, 9}, {5, 5}, {7, 10}
        };
        System.out.println("mo distinct="
                + Arrays.toString(moDistinct(a, queries)));

        BlockSum emptyPoint = new BlockSum(new int[0]);
        LazyRangeAddSum emptyLazy =
                new LazyRangeAddSum(new int[0]);
        System.out.println("empty sum="
                + emptyPoint.rangeSum(0, 0)
                + " lazy=" + emptyLazy.rangeSum(0, 0)
                + " mo=" + Arrays.toString(
                    moDistinct(new int[0],
                        new int[][]{{0, 0}})));

        try {
            lazy.rangeAdd(7, 5, 1);
            throw new AssertionError("Expected invalid range");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidRange=rejected");
        }
        try {
            point.pointSet(10, 1);
            throw new AssertionError("Expected invalid point");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidPoint=rejected");
        }
        try {
            moDistinct(a, new int[][]{{-1, 2}});
            throw new AssertionError("Expected invalid Mo query");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidMoQuery=rejected");
        }

        Random random = new Random(5042026L);
        randomPointTests(random);
        randomLazyTests(random);
        randomMoTests(random);
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 SqrtDecompositionDemo.java
java SqrtDecompositionDemo
~~~

### Đầu ra dự kiến

~~~text
array=[5, 1, 5, 2, 3, 2, 4, 5, 1, 3]
blockSize=3 blockCount=4
point initial total=31 middle=21 empty=0
point after total=33 middle=28 local=14 index9=-2
lazy initial total=31
lazy after first total=59 sub[1,6)=29 value[2]=9
lazy after second total=53 head[0,3)=9 tail[5,10)=31 value[2]=7
mo distinct=[5, 2, 4, 5, 0, 3]
empty sum=0 lazy=0 mo=[0]
invalidRange=rejected
invalidPoint=rejected
invalidMoQuery=rejected
pointRandom=PASS (550 cases)
lazyRandom=PASS (550 cases)
moRandom=PASS (420 cases)
~~~

### Đọc output

**blockSize=3, blockCount=4:** \(\lfloor\sqrt{10}\rfloor=3\), tạo bốn khối có độ dài [3,3,3,1].

**point initial:** tổng toàn dãy là 31, tổng [2,8) là 21, đoạn [5,5) rỗng có tổng 0.

**point after:** gán vị trí 3 từ 2 thành 9 (tăng 7), rồi tăng vị trí 9 thêm −5 (3→−2). Tổng cuối là \(31+7−5=33\). Tổng [2,8) đổi thành 28 vì chứa vị trí 3 nhưng không chứa vị trí 9. Tổng [3,6) là 9+3+2=14.

**lazy after first:** [2,9) có 7 phần tử tăng 4, tổng \(31+28=59\); [1,6) có bốn phần tử được tăng, từ 13 thành 29. Giá trị a[2] từ 5 thành 9.

**lazy after second:** ba phần tử đầu giảm 2, tổng mới \(59−6=53\). Tổng [0,3) là 9, tổng [5,10) là 31, a[2] thành 7.

**mo distinct:** sáu kết quả ở vị trí truy vấn ban đầu lần lượt là 5,2,4,5,0,3. Dù thứ tự thực thi đã bị Mo thay đổi, thứ tự trả kết quả không đổi.

**empty:** cả ba cấu trúc xử lý hợp lệ mảng rỗng và đoạn [0,0) mà không chia cho 0.

**invalidRange/invalidPoint/invalidMoQuery:** chỉ số ngoài miền hoặc l>r bị từ chối, không trả tổng từ những ô nhớ không hợp lệ.

**Các dòng PASS:** các thuật toán được đối chiếu với oracle duyệt trực tiếp trên nhiều mảng/query ngẫu nhiên, gồm cả số âm, trùng lặp, chỉ số biên, khoảng rỗng, và `Integer.MIN_VALUE`/`Integer.MAX_VALUE` trong Mo. Đây là kiểm thử cài đặt; chứng minh tính đúng tổng quát vẫn là các bất biến đã trình bày.

## 14. Các bẫy về chỉ số và khối cuối

### 14.1. Chia khối bằng phép chia nguyên

Chỉ số i từ 0..n−1 thuộc khối i/B. Nếu dùng i/B khi B=0, chương trình lỗi; luôn chọn B≥1. Nếu n=0, không có phần tử nào để chia khối, nhưng có thể vẫn có truy vấn rỗng.

### 14.2. Khối cuối không đầy

Với n=10, B=3, khối cuối chỉ có chỉ số 9. Công thức end phải là:

`min(n, (b+1)*B)`.

Nếu tăng cả khối cuối bằng delta nhưng lại cộng `delta*B` vào tổng, bạn đã đếm **hai phần tử không tồn tại**.

### 14.3. Nhầm đoạn đóng và nửa mở

Đề hỏi tổng từ l đến r **bao gồm r** cần chuyển sang [l,r+1). Với l=r, đoạn đóng có một phần tử; đoạn nửa mở [l,l) **rỗng**. Phải thống nhất từ đầu tới cuối, kể cả oracle kiểm thử.

### 14.4. Không tái tính thông tin khối sau cập nhật

Nếu pointSet thay value[i] nhưng không đổi blockSum[i/B], một query qua khối đầy đủ sẽ trả tổng cũ.

### 14.5. Đếm lazy hai lần

Khi rangeAdd toàn khối, **chỉ cập nhật lazy và total**, không phải vừa cộng delta vào toàn bộ base[i] vừa cộng delta vào lazy mà không có quy tắc bù trừ. Khi query phần biên, đọc base+lazy. Khi query khối đầy đủ, chỉ đọc total, không cộng lazy thêm lần nữa.

### 14.6. Chỉnh sửa dữ liệu trong lúc chạy Mo tĩnh

Mo tĩnh dựa trên việc mọi query nhìn **cùng một mảng**. Nếu chen một lệnh cập nhật giữa query 1 và query 2, rồi sắp query 2 lên trước query 1, các câu trả lời có thể bị tính trên sai phiên bản mảng. Dùng cấu trúc online, tách phase hoặc nghiên cứu Mo có modifications.

## 15. Lợi và hại của các biến thể

**Phân khối bình thường** rất dễ cài, đặc biệt khi point update O(1) là quan trọng và range query O(√n) đáp ứng giới hạn. Nhưng với tổng đoạn, **Fenwick tree** thường đạt \(O(\log n)\) cho cả point update và range sum, nên có thể nhanh hơn khi n lớn.

**Lazy block decomposition** cho range add và range sum là lựa chọn dễ chứng minh; với số lượng truy vấn/cập nhật lớn, **lazy segment tree** thường cung cấp \(O(\log n)\) mỗi thao tác. Nếu chỉ cần range add + point query, có thể dùng difference array cho truy vấn offline sau toàn bộ update, hoặc Fenwick theo cách thích hợp.

**Mo's algorithm** hữu dụng khi:
- Mảng không cập nhật trong toàn bộ danh sách query.
- Có rất nhiều truy vấn đoạn.
- Có phép thêm/bớt phần tử ở hai đầu với chi phí thấp.
- Kết quả không dễ gộp từ các khối độc lập.
- Được phép trả kết quả sau khi biết toàn bộ query.

Nó có overhead sort query và nén tọa độ, tốn số bước con trỏ có thể lớn. Với q nhỏ, duyệt trực tiếp hoặc một thuật toán chuyên biệt thường đơn giản và nhanh hơn.

### Chọn kích thước B trong Mo

Đặt B≈√n là một điểm khởi đầu dễ hiểu và có bound chuẩn. Nếu q khác n rất xa, việc cân bằng hai hạng \(qB+n^2/B\) gợi ý B có thể thay đổi theo n và q, nhưng không được bỏ qua chi phí sắp xếp, chi phí ADD/REMOVE và hành vi cache thực tế. Các tối ưu như **Hilbert order** cũng được dùng trong thực hành để giảm số bước con trỏ, nhưng cần cài đặt đúng và kiểm thử độc lập.

## 16. Kiểm thử và đối chiếu độc lập

Một hệ thống tự chấm các thuật toán xử lý khối nên xây **oracle đơn giản, chậm nhưng rõ ràng** cho dữ liệu nhỏ.

### Oracle tổng đoạn

Giữ một mảng `brute`. Mỗi lần pointSet, pointAdd hoặc rangeAdd thì sửa trực tiếp các phần tử đúng phạm vi. Khi có query [l,r), tính:

\[
\operatorname{expected}=\sum_{i=l}^{r-1}\operatorname{brute}[i].
\]

So với `BlockSum.rangeSum` hoặc `LazyRangeAddSum.rangeSum`. Không chỉ so giữa hai triển khai phân khối vì chúng có thể cùng mắc một lỗi index.

### Oracle distinct

Dùng `HashSet<Integer>`. Với query [l,r), đưa từng a[i] vào Set rồi lấy `size()`. Đây là cách O(r−l) cho một query nhưng đúng nghĩa số giá trị phân biệt, không dựa trên cách Mo sắp xếp.

### Bộ kiểm thử được nhúng trong mã

| Nhóm | Số bộ dữ liệu | Nội dung |
| --- | ---: | --- |
| Point set/add + range sum | 550 | Mảng kích thước 0..100; 140 thao tác/bộ, oracle long[] |
| Range add + range sum/point get | 550 | Mảng kích thước 0..100; 140 thao tác/bộ, cập nhật chồng lấn và delta âm |
| Mo distinct | 420 | Mảng kích thước 0..80; 0..100 truy vấn/bộ, giá trị trùng lặp và cực trị int |

Kiểm tra **mảng rỗng**, **đoạn rỗng**, **l=r=n**, **chỉ số 0 và n−1**, khối cuối không đủ B, số âm, nhiều cập nhật chồng lấn, phần tử có giá trị lớn và truy vấn lặp lại. Cần thêm các test stress lớn để đo hiệu năng; test nhỏ có oracle không chứng minh tự động không vượt thời gian ở n hàng triệu.

**Phân biệt:** kiểm thử 1.520 bộ dữ liệu không phải là chứng minh cho **mọi input**. Tính đúng tổng quát đến từ bất biến của blockSum/lazy/frequency và lập luận các đoạn được phủ không trùng.

## 17. Phân tích và tối ưu hiệu năng

### Chi phí khởi tạo

BlockSum và LazyRangeAddSum tiền xử lý O(n). Mo cần nén tọa độ O(n log n), sắp query O(q log q), rồi dịch con trỏ theo cận \(O((n+q)\sqrt n)\). Nếu phải tạo nhiều lần cho nhiều danh sách query khác nhau trên cùng mảng, có thể cân nhắc tái sử dụng phần nén tọa độ.

### Chi phí bộ nhớ

- `BlockSum`: value O(n), blockTotal O(n/B).
- `LazyRangeAddSum`: base O(n), lazy và total O(n/B).
- `moDistinct`: compressed và sorted O(n), Query[] và answer O(q), freq O(u).

Với đầu vào rất lớn, lưu cùng lúc nhiều bản sao mảng có thể là chi phí đáng kể. Trong ứng dụng thật, chỉ khởi tạo cấu trúc cần thiết.

### Tràn số và miền giá trị

Các tổng dùng `long` nhưng nếu cộng quá giới hạn 64-bit vẫn có thể tràn. Với input yêu cầu an toàn tuyệt đối, cân nhắc kiểm tra overflow bằng `Math.addExact`/`Math.multiplyExact` hoặc dùng `BigInteger` với đánh đổi hiệu năng. Mã minh họa giả định tổng vẫn trong miền long.

Giá trị mảng ở Mo được nén thành rank, nên kể cả `Integer.MIN_VALUE` cũng không trở thành chỉ số âm. Chỉ được đưa rank vào freq, không đưa trực tiếp giá trị gốc.

### Khi nào không nên phân khối?

- Cần hỗ trợ nhiều loại update/query kết hợp phức tạp, block summary khó duy trì.
- Cần truy vấn trả lời ngay và dạng truy vấn phù hợp với Fenwick/segment tree O(log n).
- Chỉ có vài truy vấn, quét trực tiếp đủ nhanh và giảm độ phức tạp triển khai.
- Dữ liệu cập nhật liên tục nhưng lại định dùng Mo tĩnh.
- Phép ADD/REMOVE trong Mo quá tốn kém hoặc không có hàm nghịch REMOVE đúng.

## 18. Các lỗi thường gặp

1. Chọn B=0 khi n=0 và gặp phép chia cho 0.
2. Đọc quá n vì giả định khối cuối luôn có đúng B phần tử.
3. Dùng khoảng [l,r] ở một nơi và [l,r) ở nơi khác.
4. Cộng phần tử biên hai lần sau khi đã cộng khối trọn.
5. Bỏ sót phần tử cuối vì điều kiện vòng lặp sai.
6. Không cập nhật blockSum khi pointSet/pointAdd.
7. Cộng delta vào blockTotal mà không nhân độ dài khi update toàn khối.
8. Nhân delta với B thay vì độ dài khối cuối.
9. Tăng lazy của cả khối dù chỉ cập nhật một phần nhỏ.
10. Quên cộng lazy khi truy vấn phần biên.
11. Cộng lazy thêm vào total đã bao gồm lazy, dẫn tới đếm hai lần.
12. Trộn mô hình base+lazy với mô hình push lazy mà không giữ nhất quán.
13. Cho rằng mọi phép gộp kết quả khối đều đúng, kể cả distinct count.
14. Lấy tổng số distinct từng khối làm distinct toàn đoạn.
15. Chọn B=1 hoặc B=n mà không hiểu công thức O(B+n/B).
16. Cho Mo xử lý online một truy vấn một mà vẫn hy vọng đạt bound offline.
17. Sắp query bằng Mo nhưng không lưu id gốc để trả đúng thứ tự.
18. Sắp bằng `l/B` nhưng dùng B=0 khi n=0.
19. Lẫn lộn R là đầu phải **không bao gồm** trong [L,R).
20. Khi ADD, tăng distinct dù freq đã >0.
21. Khi REMOVE, giảm distinct khi freq vẫn >0.
22. Xóa phần tử chưa có trong cửa sổ, làm frequency âm.
23. Sắp query rồi giữ nguyên kết quả theo thứ tự sắp, không phục hồi id.
24. Không nén tọa độ khi giá trị âm/lớn, rồi index freq sai.
25. Viết comparator bằng `x-y` gây tràn số nguyên.
26. Sắp lại query băng qua các update, khiến phiên bản mảng sai.
27. Nhầm số bước dịch con trỏ với số truy vấn q mà bỏ chi phí R.
28. Gọi Mo là O(√n) **cho mỗi query** mà không nói chi phí tổng và tiền xử lý.
29. Giả định thuật toán Mo nào cũng dùng được phép REMOVE dễ dàng.
30. Không test những khoảng trống [n,n) và [0,0).
31. Không kiểm n=1, B=1, đoạn bao toàn bộ.
32. Dùng int để lưu tổng lớn gây tràn dù phần tử là int.
33. Chỉ kiểm hai triển khai có cùng logic, không dùng brute-force oracle.
34. Thấy 500 test pass rồi coi đó là chứng minh mọi trường hợp.
35. Dùng data structure nặng hơn nhu cầu dù q rất ít.
36. Không phân tích chi phí bộ nhớ khi nén tọa độ và sort query trên dữ liệu lớn.

## 19. Bài tập có lời giải

**Bài 1.** Với n=10, B=3, có bao nhiêu khối? **Đáp án:** \(\lceil10/3\rceil=4\).

**Bài 2.** Khối cuối của bài 1 chứa chỉ số nào? **Đáp án:** chỉ số 9, độ dài 1.

**Bài 3.** Phần tử i=7 thuộc khối nào với B=3? **Đáp án:** \(\lfloor7/3\rfloor=2\).

**Bài 4.** Công thức end của khối b? **Đáp án:** `min(n,(b+1)*B)`.

**Bài 5.** Vì sao B≈√n? **Đáp án:** cân bằng O(B) biên và O(n/B) khối đầy đủ.

**Bài 6.** Độ dài đoạn [l,r)? **Đáp án:** r−l.

**Bài 7.** Đoạn [4,4) có tổng bao nhiêu? **Đáp án:** 0.

**Bài 8.** Đoạn đóng [2,5] đổi sang nửa mở thế nào? **Đáp án:** [2,6).

**Bài 9.** Bất biến BlockSum là gì? **Đáp án:** blockTotal[b] bằng tổng mọi value[i] trong khối b.

**Bài 10.** pointSet tăng giá trị tại p từ x lên y phải sửa blockTotal thế nào? **Đáp án:** cộng y−x vào blockTotal[p/B].

**Bài 11.** Độ phức tạp pointSet của BlockSum? **Đáp án:** O(1).

**Bài 12.** Độ phức tạp rangeSum của BlockSum với B≈√n? **Đáp án:** O(√n).

**Bài 13.** Với mảng [5,1,5,2,3,2,4,5,1,3], tổng toàn dãy? **Đáp án:** 31.

**Bài 14.** Tổng [2,8) trên dãy đó? **Đáp án:** 21.

**Bài 15.** Gán a[3]=9 từ a[3]=2, tổng tăng bao nhiêu? **Đáp án:** 7.

**Bài 16.** Sau bài 15, tăng a[9] thêm −5, tổng cuối? **Đáp án:** 31+7−5=33.

**Bài 17.** LazyRangeAddSum lưu ba loại trạng thái gì? **Đáp án:** base[i], lazy[b], blockTotal[b].

**Bài 18.** Giá trị thực tại i khi dùng lazy? **Đáp án:** base[i]+lazy[i/B].

**Bài 19.** Cập nhật toàn bộ khối dài len bằng +delta làm total tăng bao nhiêu? **Đáp án:** len×delta.

**Bài 20.** Cập nhật một phần khối có được tăng lazy của cả khối không? **Đáp án:** không; tăng base của từng phần tử biên.

**Bài 21.** Vì sao query phần biên phải đọc base+lazy? **Đáp án:** base không phản ánh những full-block updates chưa đẩy xuống từng phần tử.

**Bài 22.** Với update [2,9) cộng 4 trên dãy n=10, tổng tăng bao nhiêu? **Đáp án:** 7×4=28.

**Bài 23.** Sau update ấy, tổng toàn dãy? **Đáp án:** 59.

**Bài 24.** Tiếp tục update [0,3) giảm 2, tổng thành gì? **Đáp án:** 53.

**Bài 25.** Sau hai update ở trên, a[2] bằng mấy? **Đáp án:** 7.

**Bài 26.** Distinct count có thể cộng số distinct của từng khối không? **Đáp án:** không; giá trị trùng ở các khối sẽ bị đếm nhiều lần.

**Bài 27.** Vì sao Mo là thuật toán offline? **Đáp án:** cần biết danh sách query trước để sắp lại thứ tự thực thi.

**Bài 28.** Mo có phải trả đáp án theo thứ tự đã sắp xếp không? **Đáp án:** không; lưu id gốc và trả theo id ban đầu.

**Bài 29.** ADD một giá trị x có freq[x]=0 làm distinct thay đổi thế nào? **Đáp án:** distinct tăng 1.

**Bài 30.** ADD x đang có freq[x]=3 làm distinct tăng không? **Đáp án:** không, chỉ freq tăng lên 4.

**Bài 31.** REMOVE x từ freq[x]=1 xuống 0 làm gì? **Đáp án:** distinct giảm 1.

**Bài 32.** REMOVE x từ freq[x]=3 xuống 2 làm gì? **Đáp án:** distinct giữ nguyên.

**Bài 33.** Với mảng [5,1,5], distinct count là gì? **Đáp án:** 2.

**Bài 34.** Với [5,1,5,2,3,2,4,5,1,3], distinct [2,7)? **Đáp án:** 4 (5,2,3,4).

**Bài 35.** Nén tọa độ có làm mất quan hệ bằng nhau giữa các giá trị không? **Đáp án:** không; các giá trị bằng nhau có cùng rank.

**Bài 36.** Vì sao dùng Integer.compare thay vì x−y trong comparator? **Đáp án:** trừ hai int lớn có thể overflow.

**Bài 37.** Mỗi bước ADD/REMOVE O(1), độ phức tạp tổng di chuyển con trỏ Mo với B≈√n? **Đáp án:** O((n+q)√n).

**Bài 38.** Mo còn có overhead nào? **Đáp án:** sort query O(q log q) và nén tọa độ O(n log n).

**Bài 39.** Nếu có update xen giữa các query, có thể dùng nguyên bản Mo tĩnh không? **Đáp án:** không; query sẽ không còn cùng phiên bản mảng.

**Bài 40.** Khi q rất nhỏ, nên cân nhắc gì? **Đáp án:** duyệt trực tiếp có thể rẻ hơn chi phí xây khối, sort và compress.

**Bài 41.** Với n=0, đoạn hợp lệ là gì? **Đáp án:** chỉ [0,0), tổng và distinct đều 0.

**Bài 42.** Khi test BlockSum, oracle nên dùng gì? **Đáp án:** mảng brute cập nhật trực tiếp và vòng lặp cộng từng phần tử trong query.

**Bài 43.** Khi test Mo distinct, oracle nên dùng gì? **Đáp án:** HashSet chứa giá trị trong đoạn.

**Bài 44.** Nếu tổng các giá trị vượt long, giải pháp là gì? **Đáp án:** kiểm tra overflow hoặc dùng BigInteger phù hợp với ràng buộc.

## 20. Checklist

1. Đề bài dùng đoạn đóng hay nửa mở?
2. Đã thống nhất [l,r) trong code, ví dụ và oracle?
3. B có luôn ≥1, kể cả n=0?
4. Đã tính chính xác K=ceil(n/B) và khối cuối thiếu phần tử?
5. end của khối có cắt tại n?
6. Phép gộp block summary có đúng với loại truy vấn?
7. Point update có cập nhật đúng tổng khối?
8. Range add toàn khối có tăng tổng bằng delta×độ dài thật?
9. Range add biên có tránh thay lazy của cả khối?
10. Khi query biên có cộng cả base và lazy?
11. Khi query khối đầy đủ có dùng total đã bao gồm lazy, không đếm hai lần?
12. Có chặn l<0, r>n, l>r và index ngoài mảng?
13. Đã test n=0, n=1, B=1, r=n, l=r?
14. Với Mo, mọi query có áp dụng trên **cùng mảng tĩnh**?
15. Mo có lưu id gốc trước khi sort?
16. Mo có giữ cửa sổ [L,R) nhất quán trong các phép ADD/REMOVE?
17. Freq có giảm distinct chính xác khi số đếm về 0?
18. Có nén tọa độ nếu a[i] âm hoặc quá lớn?
19. Có dùng comparator tránh overflow?
20. Có phân biệt chi phí khởi tạo, query, update và bộ nhớ?
21. Có so kết quả với oracle độc lập trên nhiều dữ liệu nhỏ?
22. Có test cực trị int, trùng lặp, số âm và nhiều cập nhật chồng lấn?
23. Có cân nhắc Fenwick/segment tree nếu cần bảo đảm O(log n)?
24. Có tránh nhầm kết quả test thực nghiệm với chứng minh bất biến?

**Ghi nhớ:** phân rã căn bậc hai chia n phần tử thành khối dài khoảng \(\sqrt n\), kết hợp **phần biên quét trực tiếp** với **khối trọn vẹn dùng summary**, đạt O(√n) cho nhiều truy vấn/cập nhật đoạn. Lazy theo khối phải giữ nhất quán `actual=base+lazy` và `total=sum(actual)`. **Mo's algorithm** tận dụng cùng ý tưởng phân khối **để sắp lại các truy vấn offline**, duy trì cửa sổ bằng ADD/REMOVE và có tổng bước khoảng \(O((n+q)\sqrt n)\) với B≈√n. Kết quả đúng phụ thuộc vào **bất biến, chỉ số và mô hình online/offline**, không chỉ vào việc chọn B gần \(\sqrt n\).
