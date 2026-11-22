# Kiểm thử tính chất và quan hệ biến đổi bảo toàn đáp án

**Chủ đề:** Computer Science Algorithms · Cài đặt và kiểm thử

## 1. Kiểm thử thuật toán không chỉ là so một đáp án mẫu

Giả sử một hàm nhận mảng số nguyên và trả về độ dài **dãy con tăng nghiêm ngặt dài nhất** (strict Longest Increasing Subsequence, LIS). Với mảng:

~~~text
[3, 1, 2, 2, 5, 4]
~~~

đáp án đúng là 3, ví dụ chọn dãy con [1,2,5] hoặc [1,2,4]. Một unit test so kết quả với 3 là cần thiết nhưng chưa đủ. Chương trình còn phải xử lý mảng rỗng, một phần tử, nhiều giá trị bằng nhau, âm/dương, các dữ liệu ở biên kiểu số, dãy tăng/giảm và nhiều trường hợp ngoài những ví dụ được viết tay.

Một vấn đề khác là **oracle problem**: khi input có hàng triệu phần tử, ta có thể chạy thuật toán nhanh nhưng không đủ khả năng tính một expected output độc lập cho mỗi dữ liệu thật. Nếu chỉ so kết quả với chính nó, một lỗi nhất quán có thể đi qua tất cả test.

Trong nhóm **Cài đặt và kiểm thử**, ba ý tưởng quan trọng là:
1. **Kiểm thử tính chất (property-based testing):** phát biểu những bất biến phải đúng cho mọi input hợp lệ, sinh nhiều input để kiểm chúng.
2. **Kiểm thử quan hệ biến đổi (metamorphic testing):** từ input x tạo input mới T(x), rồi kiểm quan hệ toán học bắt buộc giữa f(x) và f(T(x)).
3. **Kiểm thử đối chiếu (differential testing):** trên input nhỏ, so thuật toán nhanh với một oracle tham chiếu độc lập, thường chậm hơn nhưng dễ kiểm chứng.

Bài này tập trung vào những phép biến đổi **bảo toàn đáp án**, đồng thời phân biệt chúng với phép biến đổi làm đáp án **thay đổi theo quy luật xác định**. Mọi quan hệ được dùng đều cần **chứng minh và tiền điều kiện**; nếu viết một quan hệ sai, test có thể báo lỗi cho một thuật toán hoàn toàn đúng.

## 2. Bốn kiểu test và vai trò của mỗi kiểu

### 2.1. Unit test với đáp án đã biết

Một test truyền thống là một cặp input/expected:

\[
f(x)=y.
\]

Ví dụ strict LIS:

| Input | Đáp án |
|---|---:|
| [] | 0 |
| [7] | 1 |
| [1,1] | 1 |
| [1,2,3,4] | 4 |
| [4,3,2,1] | 1 |
| [3,1,2,2,5,4] | 3 |

Tác dụng: dễ hiểu, tái lập, tốt cho hồi quy. Hạn chế: số ví dụ được chuẩn bị thủ công thường rất nhỏ so với miền input.

### 2.2. Property-based testing

Một **property** là một mệnh đề phải đúng với một lớp input. Với strict LIS L(a):

- \(0\le L(a)\le |a|\).
- Nếu a rỗng, L(a)=0.
- Nếu a không rỗng, L(a)≥1.
- L(a) không lớn hơn số giá trị khác nhau.
- Nếu a tăng nghiêm ngặt, L(a)=|a|.
- Nếu a không tăng, L(a)=1 khi a không rỗng.

Bộ kiểm thử sinh nhiều mảng và thực hiện assertions trên những mệnh đề đó. Một bộ sinh tốt không chỉ dùng số ngẫu nhiên lớn; nó phải có input rỗng, nhiều giá trị bằng nhau, nhiều số âm, các độ dài sát ranh giới, mảng đã sorted và reverse-sorted.

**Đơn thuần sinh dữ liệu rồi in kết quả không phải kiểm thử tính chất.** Test chỉ có giá trị khi biết phải assert điều gì.

### 2.3. Differential testing

Tạo hai lời giải độc lập cho **cùng một đặc tả**:
- Bản nhanh strict LIS O(n log n) bằng mảng tails và lower_bound.
- Bản đơn giản strict LIS O(n²) bằng quy hoạch động dp[i].

Với input nhỏ, nếu hai đáp án khác nhau, ta có phản ví dụ cần điều tra. Một oracle độc lập nên sử dụng ý tưởng khác thuật toán được kiểm: viết hai bản giống hệt logic và lỗi chỉ tạo **cảm giác an toàn giả**.

Differential testing không phải chứng minh hình thức; cả hai thuật toán vẫn có thể cùng mắc một bug hoặc áp dụng khác đặc tả. Vì vậy cần kết hợp chứng minh, unit tests và các quan hệ biến đổi.

### 2.4. Metamorphic testing

Khi khó biết y chính xác, thay vì chỉ hỏi “f(x)=bao nhiêu?”, ta hỏi:

> Khi biến x thành T(x), đầu ra mới **bắt buộc** liên hệ thế nào với đầu ra cũ?

Một quan hệ biến đổi tổng quát là:

\[
P(x)\Longrightarrow
R(x,T(x),f(x),f(T(x))),
\]

với:
- P là tiền điều kiện để biến đổi hợp lệ.
- T là phép biến đổi input.
- f là hàm cần test.
- R là điều kiện bắt buộc giữa input/output trước và sau.

Hai dạng quan trọng:

**Bảo toàn đáp án:**

\[
\boxed{f(T(x))=f(x).}
\]

**Đáp án thay đổi có thể dự đoán:**

\[
\boxed{f(T(x))=g(f(x)).}
\]

Không phải mọi metamorphic relation đều bất biến. Đôi khi đáp án phải tăng đúng một, nhân theo một hệ số, biến đổi nhãn hoặc thỏa một bất đẳng thức. Ngược lại, một quan hệ “tưởng đúng” nhưng chưa chứng minh có thể là **lỗi của test**.

## 3. Đặc tả của bài toán minh họa: strict LIS

Cho dãy \(a[0],\ldots,a[n-1]\). Ta cần chọn các chỉ số:

\[
0\le i_1<i_2<\cdots<i_k<n
\]

với:

\[
a[i_1]<a[i_2]<\cdots<a[i_k],
\]

sao cho k lớn nhất. Gọi đáp án là L(a); nếu n=0 thì L(a)=0.

**Dãy con (subsequence) không phải đoạn con (subarray):**
- Subsequence giữ nguyên thứ tự nhưng được phép bỏ vị trí.
- Subarray phải có vị trí liên tiếp.
- Strict tăng dùng **<**, không phải ≤.
- Dãy con không giảm cho phép các phần tử bằng nhau, là bài toán khác.

Ví dụ:

~~~text
Input:     [3, 1, 2, 2, 5, 4]
Valid LIS: [1, 2, 5]   (length 3)
Valid LIS: [1, 2, 4]   (length 3)
Invalid:   [1, 2, 2, 5]  vì 2 không nhỏ hơn 2
~~~

### 3.1. Thuật toán nhanh O(n log n)

Duy trì tails[len−1] là giá trị kết thúc **nhỏ nhất có thể** của một dãy con tăng nghiêm ngặt độ dài len trong tiền tố đã duyệt.

Với mỗi x:
1. Binary search **vị trí đầu tiên** tails[pos]≥x, gọi là lower_bound.
2. Gán tails[pos]=x.
3. Nếu pos bằng size hiện tại thì tăng size.
4. Sau khi duyệt mọi x, trả size.

Tails là bảng các **giá trị kết thúc tối ưu** theo độ dài, không nhất thiết chính là một subsequence dài nhất trong input.

~~~text
strict LIS:
  if tails[mid] < x:
      lo = mid + 1
  else:
      hi = mid
~~~

Dấu so sánh rất quan trọng. Nếu thay bằng tails[mid]≤x, chương trình chuyển thành **longest non-decreasing subsequence**; trên [1,1] nó trả 2 thay vì strict LIS bằng 1.

### 3.2. Oracle chậm O(n²) độc lập

Đặt dp[i] là độ dài strict LIS **kết thúc tại i**:

\[
dp[i]=1+
\max_{\substack{j<i\\a[j]<a[i]}}dp[j],
\]

với max của tập rỗng bằng 0. Đáp án là \(\max_i dp[i]\), riêng mảng rỗng trả 0.

Oracle dùng hai vòng lặp và điều kiện so sánh trực tiếp, không dùng binary search. Nó đơn giản để kiểm trên n nhỏ nhưng không nên chạy trên dữ liệu quá lớn trong pipeline production.

## 4. Quan hệ biến đổi thứ nhất: dịch mọi giá trị cùng một hằng số

Định nghĩa:

\[
T_c(a)=[a_0+c,a_1+c,\ldots,a_{n-1}+c].
\]

Nếu các phép cộng **không overflow** và cùng kiểu thứ tự:

\[
a_i<a_j\iff a_i+c<a_j+c.
\]

Vì mọi cặp giá trị giữ quan hệ < và các vị trí không đổi, tập các subsequence tăng hợp lệ giữ nguyên. Do đó:

\[
\boxed{L(T_c(a))=L(a).}
\]

Ví dụ:

~~~text
Original: [3, 1, 2, 2, 5, 4]         LIS = 3
Add +10:  [13, 11, 12, 12, 15, 14]  LIS = 3
~~~

**Tiền điều kiện không được bỏ:** nếu int overflow, thứ tự có thể bị đảo. Trong Java, Math.addExact phát hiện overflow và test phải phân biệt “transform không hợp lệ” với “thuật toán tính sai”. Cộng những offset khác nhau theo vị trí **không** có bảo đảm tương tự.

## 5. Quan hệ thứ hai: phép affine có hệ số dương

Với k>0, b bất kỳ:

\[
T(a_i)=k\,a_i+b.
\]

Khi số học biểu diễn chính xác:

\[
a_i<a_j\iff ka_i+b<ka_j+b.
\]

Nên:

\[
\boxed{L([ka_i+b]_i)=L(a)}.
\]

Demo dùng k=3, b=7:

~~~text
Original: [3, 1, 2, 2, 5, 4]       LIS = 3
3x + 7:   [16, 10, 13, 13, 22, 19] LIS = 3
~~~

Tổng quát, mọi ánh xạ **tăng nghiêm ngặt** trên tập giá trị của input đều bảo toàn strict LIS length.

Những trường hợp không thể tự suy rộng:
- k=0 làm mọi giá trị bằng nhau, nên mảng không rỗng có strict LIS length 1.
- k<0 đảo chiều so sánh, có thể thay LIS length.
- Làm tròn hoặc ép kiểu có thể biến hai giá trị khác nhau thành bằng nhau.
- Arithmetic overflow làm hỏng phép biến đổi.

Phản ví dụ cho hệ số âm: [1,2,3] có LIS length 3; [-1,-2,-3] có LIS length 1. **Không được dùng negative scaling như một phép bảo toàn LIS.**

## 6. Quan hệ thứ ba: nén tọa độ bảo toàn thứ tự

**Coordinate compression** ánh xạ các giá trị phân biệt theo thứ tự tăng thành các thứ hạng 0,1,2,...

~~~text
Original:          [3, 1, 2, 2, 5, 4]
Unique sorted:     [1, 2, 3, 4, 5]
Compressed ranks:  [2, 0, 1, 1, 4, 3]
LIS length: 3 -> 3
~~~

Vì các giá trị bằng nhau nhận cùng rank và thứ tự của các giá trị khác nhau được giữ:

\[
a_i<a_j\iff rank(a_i)<rank(a_j).
\]

Suy ra:

\[
\boxed{L(compress(a))=L(a).}
\]

Quan hệ này kiểm liệu implementation có phụ thuộc sai vào giá trị tuyệt đối, dấu hay khoảng cách giữa các khóa không. Nó cũng giúp rút một input lớn về các giá trị nhỏ dễ đọc **mà vẫn bảo toàn cấu trúc so sánh**.

Cần phân biệt:
- Xếp hạng theo **giá trị**: đúng.
- Gán rank theo **thứ tự xuất hiện đầu tiên**: không nhất thiết bảo toàn <.
- Gán rank riêng cho hai giá trị bằng nhau: làm hỏng strict relation.

## 7. Quan hệ thứ tư: nhân đôi từng phần tử ngay cạnh nó

Tạo:

\[
duplicateAdjacent(a)=
[a_0,a_0,a_1,a_1,\ldots,a_{n-1},a_{n-1}].
\]

Với strict LIS:

\[
\boxed{L(duplicateAdjacent(a))=L(a).}
\]

Ví dụ:

~~~text
Original: [3, 1, 2, 2, 5, 4]
Doubled:  [3, 3, 1, 1, 2, 2, 2, 2, 5, 5, 4, 4]
Length:   3 -> 3
~~~

### 7.1. Chứng minh bằng hai bất đẳng thức

**Cận dưới:** lấy một bản sao của mỗi vị trí được chọn trong bất kỳ strict LIS nào của dãy gốc. Chúng vẫn xuất hiện đúng thứ tự và có cùng giá trị, nên:

\[
L(new)\ge L(old).
\]

**Cận trên:** trong một subsequence tăng nghiêm ngặt của dãy mới, không thể chọn cả hai bản sao bằng nhau của cùng một vị trí. Thay các bản sao được chọn bằng index gốc tạo một subsequence tăng nghiêm ngặt của dãy gốc có cùng độ dài. Do đó:

\[
L(new)\le L(old).
\]

Hai cận suy ra bằng nhau.

**Quan hệ này đặc biệt hữu ích để bắt nhầm strict LIS với non-decreasing LIS**, vì thuật toán non-decreasing có thể dùng cả hai giá trị bằng nhau và kéo dài đáp án.

Không suy rộng rằng **mọi phép chèn** đều bảo toàn LIS. Ví dụ [1,3] có LIS2, chèn 2 giữa thành [1,2,3] có LIS3.

## 8. Quan hệ thứ năm: thêm một giá trị nhỏ nhất ở đầu

Nếu a không rỗng, chọn z<min(a). Tạo:

\[
T_{\mathrm{left}}(a)=[z]\mathbin{+\!\!+}a.
\]

Mọi strict LIS của a có thể được mở rộng bằng z ở đầu, nên L(new)≥L(old)+1.

Ngược lại, một subsequence tăng của dãy mới:
- Hoặc không dùng z, nên dài không quá L(old).
- Hoặc có dùng z; bỏ z thì còn một subsequence của a dài không quá L(old), nên tổng dài không quá L(old)+1.

Suy ra:

\[
\boxed{L(T_{\mathrm{left}}(a))=L(a)+1.}
\]

Ví dụ:

~~~text
Before: [3, 1, 2, 2, 5, 4]     LIS = 3
After:  [0, 3, 1, 2, 2, 5, 4]  LIS = 4
~~~

Với a rỗng, thêm một phần tử bất kỳ tạo dãy singleton, nên 0→1 và công thức vẫn đúng.

**Tiền điều kiện:** z<min(a), không chỉ z≤min(a). Với input chứa Integer.MIN_VALUE không tồn tại int nhỏ hơn min; Math.subtractExact phát hiện không thể thực hiện phép biến đổi như đã định nghĩa.

## 9. Quan hệ thứ sáu: thêm một giá trị lớn nhất ở cuối

Chọn z>max(a), tạo:

\[
T_{\mathrm{right}}(a)=a\mathbin{+\!\!+}[z].
\]

Bất kỳ strict LIS nào của a có thể thêm z ở cuối, nên chiều dài tăng ít nhất 1. Mọi subsequence của dãy mới dùng nhiều nhất **một** phần tử mới, nên chiều dài tăng nhiều nhất 1:

\[
\boxed{L(T_{\mathrm{right}}(a))=L(a)+1.}
\]

Ví dụ:

~~~text
Before: [3, 1, 2, 2, 5, 4]     LIS = 3
After:  [3, 1, 2, 2, 5, 4, 6]  LIS = 4
~~~

Nếu input rỗng, chọn singleton [0] và length tăng 0→1. Nếu input chứa Integer.MAX_VALUE, việc tạo z=max+1 trên int **không hợp lệ**.

**Hai quan hệ thêm sentinel không bảo toàn đáp án**; chúng **biến đổi đáp án theo quy luật +1**. Việc kiểm cả quan hệ bất biến và quan hệ tăng 1 giúp bộ test mạnh hơn.

## 10. Sáu quan hệ trong cùng một bộ test

Với một input a, gọi L=fastLIS(a):

| Biến đổi T(a) | Kết quả bắt buộc | Điều kiện |
|---|---|---|
| Cộng cùng +10 | L | Không overflow |
| Nhân 3 rồi cộng 7 | L | Hệ số dương, không overflow |
| Nhân đôi mỗi phần tử sát nhau | L | strict LIS; đủ chỗ cho mảng kết quả |
| Coordinate compression | L | Giữ thứ tự và equality |
| Prepend min−1 | L+1 | Không overflow; empty dùng singleton |
| Append max+1 | L+1 | Không overflow; empty dùng singleton |

Một vòng kiểm thử điển hình:
1. Sinh input a và tính fastLIS(a).
2. Với input nhỏ, tính oracle O(n²) và đòi hai kết quả bằng nhau.
3. Tạo **sáu transformed inputs**.
4. Kiểm từng metamorphic relation so với L.
5. Tính oracle cho **từng transformed input** để phát hiện cả lỗi fast implementation lẫn lỗi cài phép biến đổi.
6. Khi lỗi, xuất seed, chỉ số test, tên quan hệ, input gốc, input mới, expected và actual.

Với 1.200 mảng:
- 1.200×6=**7.200 metamorphic assertions**.
- 1.200×7=**8.400 oracle comparisons** (gốc và sáu input biến đổi).

**Không nhầm “đã chạy nhiều assertions” với “đã chứng minh đúng cho mọi input”.** Test chỉ khảo sát những input được sinh; thêm proofs, boundary cases và mutant tests vẫn cần thiết.

## 11. Một mutant: dùng upper_bound thay vì lower_bound

Trong strict LIS dùng tails:
- **Đúng:** tìm vị trí đầu tiên tails[pos]≥x.
- **Sai cho strict LIS:** tìm vị trí đầu tiên tails[pos]>x.

Nếu dùng phép so sánh sai, các phần tử bằng nhau có thể được đưa vào những vị trí mới và thuật toán tính **non-decreasing LIS**.

~~~text
Input: [1, 1]
Correct strict LIS:       1
Buggy non-decreasing LIS: 2
~~~

Bản code Java có hàm **nonDecreasingBug** cố ý sai để minh họa mutation testing, không sử dụng làm lời giải.

### 11.1. Vì sao một MR đơn lẻ có thể bỏ sót lỗi?

Mutant vừa nêu vẫn có thể bảo toàn:
- Phép dịch mọi giá trị cùng c.
- Phép affine tăng.
- Coordinate compression.

Vì nó đang giải một bài toán khác nhưng vẫn phụ thuộc vào thứ tự tương đối của giá trị, những MR ấy có thể PASS khi base đã sai. Cần:
- Unit test [1,1] với expected 1.
- Oracle O(n²) sử dụng điều kiện < độc lập.
- Quan hệ duplicateAdjacent và các kiểm thử strict semantics.

**Metamorphic testing bổ sung cho oracle, không tự thay thế oracle.** Một implementation sai nhất quán đôi khi cũng thỏa nhiều quan hệ hợp lệ.

## 12. Sinh dữ liệu kiểm thử có chủ đích

### 12.1. Seed tái lập

Dùng một seed cố định cho những bài hồi quy:

~~~java
Random random = new Random(5452026L);
~~~

Với lỗi xảy ra trên test số 417, ghi đủ seed=5452026, test index=417, mảng gốc, mảng biến đổi, tên MR và hai đáp án. Cùng JDK và cùng cách gọi Random sẽ tạo lại chuỗi input.

Nếu chạy random seed mới trong CI, cũng phải **lưu seed thực tế**. Không nên để test thất bại một lần rồi không thể tái lập.

### 12.2. Phân phối có nhiều duplicate

Một mảng với n giá trị lấy từ miền rất lớn có thể hiếm khi trùng. Trong khi đó, lỗi strict/non-decreasing thường chỉ lộ ra khi có phần tử bằng nhau.

Demo sinh n trong [0,25] và các giá trị trong [-15,15]. Cách chọn này:
- Có nhiều duplicate.
- Có số âm, 0 và dương.
- Có mảng rỗng và rất ngắn.
- Cho phép affine(3x+7), dịch +10, min−1/max+1 mà không overflow.
- Giữ transformed arrays đủ nhỏ cho oracle O(n²).

Nên bổ sung các test thủ công: toàn tăng, toàn giảm, toàn bằng nhau, nhiều plateau, high-low alternating, Integer.MIN_VALUE và Integer.MAX_VALUE (chỉ dùng những MR hợp lệ trên các cực trị).

### 12.3. Generator phải tôn trọng tiền điều kiện

Thuật toán LIS phải làm việc với mọi int[] không null. Nhưng một **transform cụ thể** có thể không hợp lệ nếu cộng/nhân bị overflow, hoặc không tồn tại giá trị sentinel nhỏ hơn min/lớn hơn max.

Cần tách:
- **Kiểm thuật toán trên miền tổng quát:** gồm số cực trị, dữ liệu dài và các trường hợp khó.
- **Kiểm quan hệ có số học:** dùng input an toàn, hoặc bỏ qua phép biến đổi khi không thỏa tiền điều kiện.

Không được tính một phép biến đổi đã overflow là “phát hiện lỗi LIS”.

## 13. Shrinking: thu nhỏ phản ví dụ

Nếu một test random với 200 phần tử thất bại, chẩn đoán nguyên nhân rất khó. **Shrinking** tìm một input nhỏ hơn vẫn gây cùng lỗi.

Quy trình đơn giản:
1. Thử xóa một nửa mảng.
2. Nếu lỗi còn, giữ nửa nhỏ hơn.
3. Thử xóa từng đoạn hoặc từng phần tử.
4. Thử thay giá trị lớn bằng 0, ±1 hoặc các giá trị gần nhau.
5. **Tính lại T(x)** từ input đã shrink, không cắt transformed input tùy tiện.
6. Chỉ chấp nhận một bước shrink khi tiền điều kiện vẫn thỏa và lỗi còn tái hiện.

Với mutant non-decreasing, một phản ví dụ rất nhỏ là:

~~~text
Input: [1, 1]
Expected: strict LIS = 1
Actual buggy result: 2
~~~

Sau khi sửa bug, giữ input này làm **regression test cố định**.

### 13.1. Tại sao cần giữ tiền điều kiện khi shrink?

Nếu quan hệ yêu cầu z<min(a), việc xóa phần tử có thể thay đổi min. z cũ có thể không còn đúng hoặc transform mới phải chọn lại z. Nếu không tái tạo transformed input, một test không hợp lệ sẽ bị báo như lỗi thuật toán (false positive).

Tương tự với đồ thị, shrinker phải bảo toàn điều kiện cần kiểm như kết nối, không âm của trọng số, hoặc quy tắc labeling.

## 14. Java 17 hoàn chỉnh: MetamorphicLISDemo.java

Chương trình chạy độc lập bằng Java standard library; không dùng framework test ngoài. Các phần:
- strictLisFast: O(n log n), lower_bound.
- lisQuadratic: O(n²) làm independent oracle.
- translate, affinePositive, duplicateAdjacent, compressRanks.
- prependSmaller, appendLarger.
- nonDecreasingBug: **mã cố ý sai** dùng để kiểm độ mạnh của test.
- require: ném AssertionError nếu assertion sai; không dùng từ khóa assert cần bật riêng.
- runRandomTests: 1.200 input, mỗi input có 6 MR và 7 oracle checks.
- main: ví dụ cụ thể, mutation check, test ngẫu nhiên và stdout xác định.

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;

public final class MetamorphicLISDemo {
    private MetamorphicLISDemo() {
    }

    // O(n log n); strict LIS needs lower_bound (first >= x).
    public static int strictLisFast(int[] a) {
        Objects.requireNonNull(a, "array");
        int[] tails = new int[a.length];
        int size = 0;

        for (int x : a) {
            int lo = 0;
            int hi = size;

            while (lo < hi) {
                int mid = lo + ((hi - lo) >>> 1);
                if (tails[mid] < x) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }

            tails[lo] = x;
            if (lo == size) {
                size++;
            }
        }
        return size;
    }

    // Independent O(n^2) oracle, no tails/binary search.
    public static int lisQuadratic(int[] a) {
        Objects.requireNonNull(a, "array");
        int[] dp = new int[a.length];
        int best = 0;

        for (int i = 0; i < a.length; i++) {
            dp[i] = 1;
            for (int j = 0; j < i; j++) {
                if (a[j] < a[i]) {
                    dp[i] = Math.max(dp[i], dp[j] + 1);
                }
            }
            best = Math.max(best, dp[i]);
        }
        return best;
    }

    public static int[] translate(int[] a, int offset) {
        int[] b = a.clone();
        for (int i = 0; i < b.length; i++) {
            b[i] = Math.addExact(b[i], offset);
        }
        return b;
    }

    public static int[] affinePositive(
            int[] a, int k, int offset) {
        if (k <= 0) {
            throw new IllegalArgumentException(
                    "Multiplier must be positive");
        }
        int[] b = a.clone();
        for (int i = 0; i < b.length; i++) {
            b[i] = Math.addExact(
                    Math.multiplyExact(b[i], k), offset);
        }
        return b;
    }

    public static int[] duplicateAdjacent(int[] a) {
        int[] b = new int[Math.multiplyExact(a.length, 2)];
        for (int i = 0; i < a.length; i++) {
            b[2 * i] = a[i];
            b[2 * i + 1] = a[i];
        }
        return b;
    }

    // Compress each distinct value to its increasing rank.
    public static int[] compressRanks(int[] a) {
        int[] sorted = a.clone();
        Arrays.sort(sorted);

        int unique = 0;
        int[] untouched = sorted.clone();
        for (int x : untouched) {
            if (unique == 0 || sorted[unique - 1] != x) {
                sorted[unique++] = x;
            }
        }

        int[] b = new int[a.length];
        for (int i = 0; i < a.length; i++) {
            int position = Arrays.binarySearch(
                    sorted, 0, unique, a[i]);
            if (position < 0) {
                throw new AssertionError("Missing compressed rank");
            }
            b[i] = position;
        }
        return b;
    }

    public static int[] prependSmaller(int[] a) {
        int smaller = 0;
        if (a.length > 0) {
            int min = a[0];
            for (int x : a) {
                min = Math.min(min, x);
            }
            smaller = Math.subtractExact(min, 1);
        }

        int[] b = new int[a.length + 1];
        b[0] = smaller;
        System.arraycopy(a, 0, b, 1, a.length);
        return b;
    }

    public static int[] appendLarger(int[] a) {
        int larger = 0;
        if (a.length > 0) {
            int max = a[0];
            for (int x : a) {
                max = Math.max(max, x);
            }
            larger = Math.addExact(max, 1);
        }

        int[] b = Arrays.copyOf(a, a.length + 1);
        b[a.length] = larger;
        return b;
    }

    // Intentionally WRONG for strict LIS: this is upper_bound.
    public static int nonDecreasingBug(int[] a) {
        int[] tails = new int[a.length];
        int size = 0;

        for (int x : a) {
            int lo = 0;
            int hi = size;
            while (lo < hi) {
                int mid = lo + ((hi - lo) >>> 1);
                if (tails[mid] <= x) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            tails[lo] = x;
            if (lo == size) {
                size++;
            }
        }
        return size;
    }

    private static void require(boolean ok, String info) {
        if (!ok) {
            throw new AssertionError(info);
        }
    }

    // 1200 * 6 = 7200 MRs.
    // 1200 * 7 = 8400 independent oracle comparisons.
    private static void runRandomTests() {
        Random random = new Random(5452026L);
        String[] names = {
            "translate", "affine", "duplicate",
            "compress", "prepend", "append"
        };

        for (int test = 0; test < 1200; test++) {
            int n = random.nextInt(26);
            int[] input = new int[n];
            for (int i = 0; i < n; i++) {
                input[i] = random.nextInt(31) - 15;
            }

            int base = strictLisFast(input);
            require(base == lisQuadratic(input),
                    "Base oracle mismatch: test=" + test
                    + " input=" + Arrays.toString(input));

            int[][] changed = {
                translate(input, 10),
                affinePositive(input, 3, 7),
                duplicateAdjacent(input),
                compressRanks(input),
                prependSmaller(input),
                appendLarger(input)
            };

            int[] expected = {
                base, base, base, base, base + 1, base + 1
            };

            for (int i = 0; i < changed.length; i++) {
                int actual = strictLisFast(changed[i]);
                String report = "seed=5452026"
                        + " test=" + test
                        + " relation=" + names[i]
                        + " input=" + Arrays.toString(input)
                        + " transformed="
                        + Arrays.toString(changed[i])
                        + " expected=" + expected[i]
                        + " actual=" + actual;

                require(actual == expected[i],
                        "Metamorphic violation: " + report);
                require(actual == lisQuadratic(changed[i]),
                        "Oracle violation: " + report);
            }
        }
    }

    public static void main(String[] args) {
        int[] sample = {3, 1, 2, 2, 5, 4};

        System.out.println(
                "Input: " + Arrays.toString(sample));
        System.out.println(
                "Strict LIS: " + strictLisFast(sample));
        System.out.println(
                "Quadratic oracle: " + lisQuadratic(sample));
        System.out.println(
                "Translate(+10): "
                + strictLisFast(translate(sample, 10)));
        System.out.println(
                "Affine(3x+7): "
                + strictLisFast(
                    affinePositive(sample, 3, 7)));
        System.out.println(
                "Adjacent duplicates: "
                + strictLisFast(duplicateAdjacent(sample)));
        System.out.println(
                "Coordinate compression: "
                + strictLisFast(compressRanks(sample)));
        System.out.println(
                "Prepend smaller: "
                + strictLisFast(prependSmaller(sample)));
        System.out.println(
                "Append larger: "
                + strictLisFast(appendLarger(sample)));

        int[] sorted = sample.clone();
        Arrays.sort(sorted);
        System.out.println(
                "Sorted input: " + strictLisFast(sorted));

        int[] equal = {1, 1};
        int wrong = nonDecreasingBug(equal);
        int right = strictLisFast(equal);
        boolean caught = wrong != right
                && lisQuadratic(equal) == right;

        System.out.println(
                "Nondecreasing bug [1, 1]: " + wrong);
        System.out.println(
                "Strict correct [1, 1]: " + right);
        System.out.println(
                "Mutation caught: " + caught);
        require(caught, "Mutation was not detected");
        System.out.println(
                "Empty LIS: " + strictLisFast(new int[0]));

        runRandomTests();
        System.out.println("Random seed: 5452026");
        System.out.println("Random cases: 1200");
        System.out.println("Metamorphic assertions: 7200");
        System.out.println("Oracle comparisons: 8400");
        System.out.println("ALL TESTS PASS");
    }
}
~~~

### 14.1. Biên dịch và chạy

Yêu cầu **JDK 17 trở lên**, tệp đúng tên **MetamorphicLISDemo.java**:

~~~bash
javac -encoding UTF-8 MetamorphicLISDemo.java
java MetamorphicLISDemo
~~~

**Stdout dự kiến:**

~~~text
Input: [3, 1, 2, 2, 5, 4]
Strict LIS: 3
Quadratic oracle: 3
Translate(+10): 3
Affine(3x+7): 3
Adjacent duplicates: 3
Coordinate compression: 3
Prepend smaller: 4
Append larger: 4
Sorted input: 5
Nondecreasing bug [1, 1]: 2
Strict correct [1, 1]: 1
Mutation caught: true
Empty LIS: 0
Random seed: 5452026
Random cases: 1200
Metamorphic assertions: 7200
Oracle comparisons: 8400
ALL TESTS PASS
~~~

### 14.2. Giải thích stdout

**Strict LIS 3 và Oracle 3:** thuật toán nhanh và DP đồng ý với kết quả đã biết của mảng mẫu.

**Translate/Affine/Adjacent duplicates/Coordinate compression đều 3:** bốn phép biến đổi bảo toàn strict LIS length vì giữ đúng các quan hệ so sánh cần thiết.

**Prepend smaller/Append larger đều 4:** một phần tử mới có thể nối vào mọi LIS cũ, và không thể tăng quá một vì chỉ thêm một phần tử.

**Sorted input 5:** mảng mẫu có năm giá trị phân biệt; sau sort tăng, strict LIS có độ dài 5. **Hoán vị/sort input không phải metamorphic relation bảo toàn LIS**.

**Nondecreasing bug 2 / Strict correct 1:** bản upper_bound dùng sai dấu; test [1,1] phát hiện lỗi khác semantics.

**Mutation caught true:** oracle và bản strict fast đồng ý là 1, khác 2 của mutant. Đây là minh họa kiểm độ mạnh của test, không phải phần lời giải.

**Empty LIS 0:** mảng không có phần tử trả 0.

**Random seed 5452026 / 1200 cases:** bộ sinh có thể tái lập; input dài 0..25 và giá trị [-15,15] có nhiều duplicate.

**7200 metamorphic assertions:** sáu quan hệ cho mỗi mảng. **8400 oracle comparisons:** oracle cho cả input gốc và sáu mảng biến đổi.

**ALL TESTS PASS:** chỉ được in nếu mọi require thành công; nếu lỗi, chương trình ném AssertionError có thông tin seed, input, phép biến đổi và expected/actual.

### 14.3. Những chi tiết triển khai cần kiểm tra

- **strictLisFast:** tails[mid]<x quyết định nhánh tăng lo; đây là lower_bound cho strict LIS. Thay bằng ≤ sẽ tạo mutant.
- **lisQuadratic:** dùng điều kiện a[j]<a[i] trong hai vòng lặp, không phụ thuộc mảng tails.
- **translate:** Math.addExact tránh wrap.
- **affinePositive:** Math.multiplyExact + Math.addExact, kiểm k>0.
- **duplicateAdjacent:** mỗi a[i] được đặt tại b[2i] và b[2i+1], không đảo vị trí phần tử gốc.
- **compressRanks:** sort bản sao rồi tạo prefix unique; các khóa bằng nhau nhận cùng rank.
- **prependSmaller/appendLarger:** giá trị mới nằm nghiêm ngặt ngoài min/max; dùng Math.subtractExact/addExact.
- **runRandomTests:** kiểm oracle **trước và sau** biến đổi, không chỉ so hai output của một implementation.
- **require:** dùng AssertionError thay từ khóa assert, vì Java assertions có thể bị tắt nếu không chạy với -ea.

Bộ code mang tính giáo dục, không phụ thuộc timing hay trạng thái shared memory; tất cả output mẫu là deterministic với cùng code.

## 15. Những biến đổi KHÔNG bảo toàn LIS

Đây là phần không thể bỏ qua khi thiết kế metamorphic tests: **quan hệ sai tạo false positive cho một thuật toán đúng**.

| Biến đổi | Bảo toàn strict LIS? | Ví dụ/giải thích |
|---|---|---|
| Cộng cùng c, không overflow | Có | Giữ mọi so sánh < |
| Nhân với k>0 và dịch, không overflow | Có | Ánh xạ tăng nghiêm ngặt |
| Coordinate compression | Có | Giữ so sánh và equality |
| Duplicate adjacent | Có | Không thể dùng hai bản sao bằng nhau |
| Prepend giá trị nhỏ hơn mọi phần tử | **Không**, đáp án tăng 1 | MR có quy luật L+1 |
| Append giá trị lớn hơn mọi phần tử | **Không**, đáp án tăng 1 | MR có quy luật L+1 |
| Hoán vị các vị trí tùy ý | Không | Sample L=3; sau sort L=5 |
| Đảo ngược mảng | Không | [1,2,3] L=3; [3,2,1] L=1 |
| Nhân với hệ số âm | Không | Thứ tự giá trị đảo |
| Chèn một số bất kỳ | Không | [1,3] L=2; chèn 2 giữa cho L=3 |
| Xóa một phần tử bất kỳ | Không | [1,2,3] L=3; xóa 2 còn L=2 |
| Thay mọi giá trị thành hằng số | Không | Mảng không rỗng còn L=1 |

Không được lấy một MR đúng cho **sorting** rồi gán cho **LIS**. Sorting không phụ thuộc thứ tự input cuối cùng nếu chỉ hỏi output sorted values; LIS lại phụ thuộc thứ tự **vị trí** của những phần tử trong input.

## 16. Một số metamorphic relations ở thuật toán khác

### 16.1. Sorting

Với sort theo giá trị:
- **Hoán vị input:** sorted values output giữ nguyên (multiset không đổi).
- **Tịnh tiến các khóa cùng c:** sorted output cũng được tịnh tiến, khi không overflow.
- **Idempotence:** sort(sort(a))=sort(a).
- **Thêm một phần tử:** output mới có đúng một occurrence mới và vẫn sorted.

Nếu sort yêu cầu **stable**, phải kiểm thứ tự tương đối của những records có **cùng key** bằng original IDs/payload; chỉ so sorted keys không đủ.

### 16.2. Binary search

Với input sorted và query về **sự tồn tại** của khóa x:
- Dịch cả mảng và query x cùng c, không overflow ⇒ boolean exists bảo toàn.
- Scale tất cả giá trị và query bằng k>0 ⇒ boolean exists bảo toàn.

Nhưng nếu output là **index**, thêm một phần tử trước target có thể làm index thay đổi. MR phải nêu đúng contract: first index, last index hay exists, không dùng một boolean property để bảo đảm index đúng.

### 16.3. Shortest path

Với graph có trọng số **không âm** dùng Dijkstra:
- Hoán vị nhãn đỉnh một-một và đổi source/target tương ứng ⇒ distance không đổi.
- Nhân mọi trọng số với k>0 ⇒ khoảng cách hữu hạn nhân k, khi không overflow.
- Thêm một đỉnh cô lập không thay đổi distance giữa các đỉnh cũ.
- Thêm cạnh có thể **giảm** khoảng cách, không phải bảo toàn.

Với đỉnh không thể tới, cần giữ trạng thái unreachable thay vì nhân một giá trị infinity/sentinel gây overflow.

### 16.4. Minimum spanning tree

Trong graph vô hướng liên thông:
- Đổi tên các đỉnh bằng một hoán vị bijective ⇒ tổng trọng số MST không đổi.
- Nhân mọi trọng số với k>0 ⇒ tổng trọng số MST nhân k.
- Cộng c vào **mọi cạnh** ⇒ tổng trọng số mỗi cây khung tăng \((n-1)c\), vì tất cả spanning trees có đúng n−1 cạnh. Đây là MR **thay đổi output theo công thức**, không phải bảo toàn.

Nếu graph không liên thông, cần xác định bài toán muốn kiểm là minimum spanning forest hay báo không có MST.

### 16.5. Bài toán đếm

- Đếm tần suất từng khóa: hoán vị thứ tự input giữ tần suất; nhân đôi input làm tần suất nhân hai.
- Đếm **số khóa phân biệt**: nhân đôi input **không đổi** kết quả.

Cùng một biến đổi duplicate nhưng tác động khác nhau lên **đầu ra khác nhau**. Do đó phải đọc đặc tả chính xác trước khi viết MR.

### 16.6. Hình học và số học

- Khoảng cách Euclid: dịch tất cả điểm cùng một vector bảo toàn khoảng cách; phép quay trong mô hình số thực cũng bảo toàn khoảng cách.
- Diện tích đa giác: scale mọi tọa độ bởi k>0 làm diện tích tăng theo \(k^2\), không bất biến.
- GCD của một dãy số nguyên: hoán vị input không đổi gcd; nhân tất cả phần tử với số nguyên k khác 0 làm gcd không âm nhân |k|, chú ý cực trị kiểu số và định nghĩa gcd của số 0.

Một metamorphic relation cần xác định **đầu ra muốn đo**, không chỉ nói chung “chất lượng thuật toán”.

## 17. Kiểm thử trên output xấp xỉ và số thực

Với double:
- Phép cộng không associative tuyệt đối về bit do rounding.
- Hai thuật toán toán học tương đương có thể trả giá trị lệch nhau vài ulp.
- Có thể kiểm \(|actual-expected|\le atol+rtol\cdot|expected|\) khi tolerance có cơ sở, kết hợp xử lý NaN/infinity/signed zero.
- Tolerance quá lớn có thể che bug, quá nhỏ có thể tạo flaky test.

Trong demo strict LIS, kết quả int và biến đổi số học được kiểm overflow, nên dùng **equality chính xác**. Không cần tolerance cho độ dài LIS.

## 18. Test dữ liệu có state và concurrency

Với hàm thuần f(x), quan hệ biến đổi dễ định nghĩa. Với API stateful hay distributed, cần tính cả:
- Lịch sử thao tác trước khi gọi.
- Thứ tự và phụ thuộc giữa insert/delete/update.
- Side effects ngoài output.
- Timeout, retry và eventual consistency.
- Metadata như timestamp/request ID không thuộc cùng semantics.
- Snapshot và các race conditions.

Ví dụ một set có thao tác insert idempotent thì gọi insert(x) hai lần giữ state logic như một lần, nhưng **không nhất thiết** giữ nguyên metric “number of requests processed”. Không được tuyên bố mọi trường output cũng bất biến.

Với queue có thứ tự, hoán đổi hai enqueue không giữ output dequeue. Với một hệ thống được thiết kế commutative, phép hoán đổi có thể hợp lệ trong phạm vi đã mô tả.

## 19. Checklist để MR đáng tin cậy

Trước khi đưa vào CI, nên trả lời:

1. **Đặc tả f là gì?** Chính xác output nào đang được kiểm?
2. **Input hợp lệ gồm những gì?** Có sortedness, connectivity, không âm, no overflow không?
3. **Phép T là gì?** Có dễ hiểu và cài đặt độc lập không?
4. **Quan hệ R có chứng minh không?** Hay chỉ là trực giác?
5. **Output phải giữ nguyên hay đổi theo công thức?**
6. **Có counterexample làm R sai không?** Nếu có, phải sửa tiền điều kiện hoặc loại R.
7. **Có oracle trên input nhỏ không?** Kết hợp differential testing khi được.
8. **Có đủ duplicate, empty và giá trị biên không?**
9. **Có lưu seed, input và transformed input khi fail không?**
10. **Shrinker có giữ tiền điều kiện không?**
11. **Có kiểm transform không mutate input gốc ngoài ý muốn không?**
12. **Kiểm số thực có tolerance hợp lý không?**
13. **Một mutant đơn giản có qua relation này không?**
14. **Chi phí test có nằm trong ngân sách CI không?**
15. **Lỗi được giữ lại làm regression test chưa?**

Một MR nên được viết thành phát biểu đầy đủ: “Với mọi input x thỏa điều kiện P, sau biến đổi T, kết quả phải thỏa R”. Cách viết này giúp reviewer kiểm tra **chất lượng của test** trước khi test chạy.

## 20. Lỗi phổ biến

1. **Chỉ sinh random rồi in output** mà không assert bất kỳ property nào.
2. **Gọi mọi property là MR** dù không có input biến đổi.
3. **Cho rằng mọi MR đều bảo toàn đáp án**.
4. **Không ghi tiền điều kiện P**, khiến transform đôi khi vô nghĩa.
5. **Hoán vị tùy ý input của strict LIS rồi đòi output không đổi**.
6. **Nhân với k âm và đòi LIS length giữ nguyên**.
7. **Để int overflow trong affine/translate**, phá trật tự giá trị.
8. **Dùng upper_bound cho strict LIS**, đếm giá trị bằng nhau.
9. **Dùng cùng thuật toán tails làm cả oracle và implementation**, hai bản có thể cùng bug.
10. **Quên mảng rỗng**, assert LIS length luôn dương.
11. **Nhầm subsequence với subarray**, kiểm bài toán khác.
12. **Tự ý chèn giá trị và đòi LIS bảo toàn** mà không chứng minh.
13. **Đôi khi duplicate không kề nhau**, áp một chứng minh không còn phù hợp.
14. **Nén tọa độ theo thứ tự xuất hiện**, không giữ <.
15. **Dùng min−1 khi min=Integer.MIN_VALUE**, overflow.
16. **Coi MR PASS là proof correctness tuyệt đối**, bỏ oracle.
17. **Không lưu seed/input thất bại**, mất khả năng tái lập.
18. **Shrinking làm mất tiền điều kiện**, tạo false positive.
19. **Sinh phạm vi quá rộng nên hiếm duplicate**, bỏ bug strict/non-decreasing.
20. **Không kiểm mảng độ dài 0/1 và các biên 2^k**.
21. **Kiểm sorted keys nhưng không kiểm stability của records**.
22. **Đòi binary-search index bất biến sau khi chèn phần tử phía trước**, sai.
23. **Dùng Dijkstra với graph trọng số âm**, vi phạm tiền điều kiện.
24. **Tăng trọng số rồi bỏ overflow**, tính distance sai.
25. **Dùng tolerance quá lỏng**, che lỗi số học.
26. **So equality bit cho double khi rounding khác nhau là hợp lệ**, tạo false failure.
27. **Transform sửa trực tiếp mảng gốc**, khiến lần so trước/sau không còn độc lập.
28. **Chạy oracle O(n²) trên input rất lớn**, làm CI quá chậm.
29. **Coi số lượng assertions là coverage 100%**, không phải.
30. **Không giữ counterexample làm regression test**, bug dễ quay lại.
31. **Chỉ dùng một MR**, mutant có thể tình cờ vẫn thỏa.
32. **Không thử mutation lỗi dấu so sánh**, bỏ qua kiểm sức mạnh test.
33. **Nhầm idempotence của phép toán với idempotence của API có side effects**.
34. **Đảo thứ tự các thao tác phụ thuộc trong hệ stateful** rồi đòi invariant.
35. **Không phân biệt deterministic và nondeterministic metadata**, so sai output.
36. **Không cách ly môi trường khi test hệ thống**, dễ flaky.
37. **Không kiểm transform bằng oracle**, có thể lỗi ở chính T.
38. **Bỏ điều kiện sorted/connected/nonnegative trong transformed input**.
39. **Trộn strict với non-decreasing**, expected thuộc bài khác.
40. **Coi kiểm thử hữu hạn như chứng minh toán học**, suy diễn quá mức.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Property-based testing kiểm điều gì?

**Đáp án:** Các tính chất bắt buộc đúng trên nhiều input được sinh, không chỉ expected cho vài ví dụ.

**Câu 2.** Metamorphic testing khác unit test thế nào?

**Đáp án:** Nó kiểm quan hệ giữa outputs của input gốc và input biến đổi; có thể không cần biết output chính xác ban đầu.

**Câu 3.** Oracle problem là gì?

**Đáp án:** Khó biết đáp án chính xác để so output với input lớn hoặc phức tạp.

**Câu 4.** Differential testing là gì?

**Đáp án:** So một implementation với lời giải độc lập của cùng đặc tả, thường dùng oracle chậm trên input nhỏ.

**Câu 5.** MR có bắt buộc giữ nguyên output không?

**Đáp án:** Không; có thể đổi theo công thức như +1 hoặc nhân k.

**Câu 6.** Strict LIS khác non-decreasing LIS thế nào?

**Đáp án:** Strict dùng <, non-decreasing cho phép ≤.

**Câu 7.** Strict LIS của [1,1] là bao nhiêu?

**Đáp án:** 1.

**Câu 8.** Dịch mọi giá trị cùng c bảo toàn LIS vì sao?

**Đáp án:** Giữ quan hệ < của mọi cặp, khi không overflow.

**Câu 9.** Nhân với k>0 bảo toàn LIS vì sao?

**Đáp án:** Phép affine tăng nghiêm ngặt giữ trật tự giá trị.

**Câu 10.** Nhân với k<0 bảo toàn LIS không?

**Đáp án:** Không; [1,2,3] chuyển [-1,-2,-3], 3 thành 1.

**Câu 11.** Coordinate compression giữ điều gì?

**Đáp án:** Quan hệ < và =, nên strict LIS length không đổi.

**Câu 12.** Nhân đôi mỗi phần tử kề nhau tác động strict LIS thế nào?

**Đáp án:** Không đổi độ dài, vì không thể lấy hai bản sao bằng nhau trong subsequence tăng nghiêm ngặt.

**Câu 13.** Prepend min−1 tác động LIS ra sao?

**Đáp án:** Tăng đúng 1 nếu có thể biểu diễn giá trị mới.

**Câu 14.** Append max+1 tác động LIS ra sao?

**Đáp án:** Tăng đúng 1 nếu có thể biểu diễn giá trị mới.

**Câu 15.** Sort input có bảo toàn strict LIS length không?

**Đáp án:** Không; mảng mẫu có LIS3 nhưng sau sort có LIS5.

**Câu 16.** Tại sao phải có oracle O(n²)?

**Đáp án:** Để phát hiện lỗi của bản fast bằng một cách tính độc lập trên input nhỏ.

**Câu 17.** Vì sao translation MR chưa đủ phát hiện mutant non-decreasing?

**Đáp án:** Mutant cũng có thể giữ cùng output khi mọi giá trị được dịch, dù output ban đầu sai.

**Câu 18.** Seed có ích gì?

**Đáp án:** Tái lập input random gây lỗi.

**Câu 19.** Shrinking là gì?

**Đáp án:** Thu nhỏ counterexample nhưng giữ nguyên lỗi và tiền điều kiện.

**Câu 20.** Vì sao phải kiểm overflow trong MR?

**Đáp án:** Overflow có thể phá thứ tự, làm quan hệ toán học không còn hợp lệ.

**Câu 21.** 1.200 test có sáu MR thì có bao nhiêu assertions quan hệ?

**Đáp án:** 7.200.

**Câu 22.** Nếu kiểm oracle cho gốc và sáu input mới thì bao nhiêu comparisons?

**Đáp án:** 8.400.

**Câu 23.** MR nào hữu ích cho shortest path không âm?

**Đáp án:** Hoán vị bijective các nhãn đỉnh và đổi source/target tương ứng bảo toàn distance.

**Câu 24.** Một chương trình vượt qua mọi MR có chắc chắn đúng không?

**Đáp án:** Không; mọi MR chỉ kiểm các quan hệ nhất định trên input hữu hạn.

**Câu 25.** Nên làm gì với counterexample đã được shrink?

**Đáp án:** Giữ làm regression test cố định.

## 22. Bài tập thực hành

**Bài 1 — Chứng minh:** tự chứng minh translation và coordinate compression bảo toàn strict LIS với mọi input thỏa tiền điều kiện.

**Bài 2 — Phản ví dụ:** tìm ba input rất ngắn bác bỏ các quan hệ “reverse/permutation/negative scale bảo toàn strict LIS”.

**Bài 3 — Mutation:** thay tails[mid]<x bằng tails[mid]<=x. Tìm phản ví dụ nhỏ nhất và chỉ ra các MR vẫn PASS với mutant này.

**Bài 4 — Shrinking:** tự cài shrinker xóa từng đoạn cho input làm mutant fail, mỗi lần sinh lại transformed input.

**Bài 5 — Sort testing:** sinh mảng random, kiểm sortedness, bảo toàn multiset, idempotence và permutation invariance; thêm stable test nếu record có payload.

**Bài 6 — Graph relabel:** tạo graph không âm và kiểm Dijkstra trước/sau bijective vertex renaming, giữ nguyên khoảng cách source–target.

**Bài 7 — Binary search:** dịch mảng sorted và query target cùng c, kiểm boolean existence không đổi, đồng thời tìm phản ví dụ với MR sai cho index sau khi chèn.

**Bài 8 — Số thực:** thiết kế tolerance có căn cứ cho một thuật toán hình học; kiểm NaN, infinity, input lớn và các trường hợp rounding khó.

**Bài 9 — CI:** tích hợp fixed examples, seed cố định, vài seed biến đổi có lưu lại, oracle nhỏ, shrinker và mutation tests.

## 23. Kết luận

**Kiểm thử tính chất** đặt câu hỏi “điều gì bắt buộc đúng với mọi input hợp lệ?”, còn **kiểm thử quan hệ biến đổi** đặt câu hỏi “sau khi input đổi theo cách có chứng minh, output phải đổi thế nào?”. Chúng đặc biệt hữu ích khi expected output khó tính trực tiếp.

Với **strict LIS**, translation, affine tăng, coordinate compression và adjacent duplication **bảo toàn độ dài**. Thêm phần tử nhỏ hơn tất cả ở đầu hoặc lớn hơn tất cả ở cuối làm độ dài **tăng đúng một**. Hoán vị input, đảo mảng hoặc nhân hệ số âm **không bảo toàn** nói chung.

Một bộ kiểm thử đáng tin không chỉ có nhiều assertions: nó phải có **đặc tả và tiền điều kiện rõ, chứng minh MR, oracle độc lập khi khả thi, random seeds tái lập, shrinking và counterexamples regression, kiểm mutation và dữ liệu biên**. Metamorphic testing là một nguồn bằng chứng mạnh, nhưng không phải sự thay thế tuyệt đối cho chứng minh tính đúng hoặc thử nghiệm độc lập.
