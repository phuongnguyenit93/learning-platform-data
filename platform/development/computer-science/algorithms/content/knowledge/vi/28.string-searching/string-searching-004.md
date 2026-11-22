# Hàm Z và cách so khớp bằng chuỗi ghép

**Hàm Z** (*Z-function, Z-array*) là một kỹ thuật tiền xử lý chuỗi cho biết, tại mỗi vị trí, bao nhiêu ký tự đầu của chuỗi **trùng với đoạn bắt đầu tại vị trí đó**. Khi tính Z bằng cách duy trì một đoạn khớp đã biết, ta đạt thời gian **O(n)**. Một ứng dụng quan trọng là tìm **tất cả vị trí xuất hiện của mẫu P trong văn bản T** bằng cách tính Z trên **chuỗi ghép P + dấu phân cách + T**.

Bài thuộc nhóm **Tìm kiếm chuỗi** trong Computer Science Algorithms. Ta đi từ định nghĩa chính xác, cách giữ cửa sổ `[L,R)`, chứng minh vì sao thuật toán tuyến tính, chuyển chỉ số trong chuỗi ghép, ví dụ nhiều lần khớp có chồng lấn, các trường hợp biên, đến chương trình **Java 17** dùng Unicode code point và bộ kiểm thử so sánh với cách duyệt trực tiếp.

Điều cần nắm là **ý nghĩa của Z[i]** và **vì sao phép kiểm tra Z[i] ≥ độ dài mẫu** tương đương với một lần khớp. Đừng chỉ học thuộc hai vòng lặp hoặc công thức trừ vị trí.

## 1. Định nghĩa Z[i]

Cho chuỗi `S` dài `n`, đánh số từ 0 đến n−1. Định nghĩa với `i>0`:

\[
Z[i]=\max\{k\mid 0\le k\le n-i,\ S[0..k-1]=S[i..i+k-1]\}.
\]

Nói bằng lời: **Z[i] là độ dài tiền tố dài nhất của S trùng với tiền tố của hậu tố S bắt đầu ở i**. Ta gọi một chuỗi bắt đầu ở i là một hậu tố; `Z[i]` so tiền tố của hậu tố đó với tiền tố của **toàn chuỗi**.

Ví dụ với `S="aabcaabxaaaz"`:

~~~text
S index: 0 1 2 3 4 5 6 7 8 9 10 11
S char:  a a b c a a b x a a  a  z
Z:       0 1 0 0 3 1 0 0 2 2  1  0
~~~

Ta có:
- `Z[1]=1`: chuỗi bắt đầu tại 1 mở đầu bằng a, nhưng ký tự kế tiếp là b khác a của tiền tố.
- `Z[4]=3`: `S[4..6]="aab"` trùng `S[0..2]="aab"`; ký tự sau đó x khác c.
- `Z[8]=2`: đoạn `"aa"` trùng hai ký tự đầu, tiếp theo a khác b.
- `Z[0]` được đặt bằng **0 theo quy ước của bài**. Một số tài liệu đặt `Z[0]=n`; hai lựa chọn không làm thay đổi `Z[i]` cho i>0. Phải biết chương trình dùng quy ước nào.

**Giới hạn:** với i>0 luôn có `0 ≤ Z[i] ≤ n−i`. Chuỗi có ký tự trùng lặp như `"aaaa"` sẽ có Z lớn: với quy ước Z[0]=0, Z là `[0,3,2,1]`.

### Z không phải độ dài khớp với ký tự ngay trước

Nếu ta xét `S="ababa"`, `Z[2]=3` vì `"aba"` ở vị trí 2 trùng ba ký tự đầu, dù ký tự ở vị trí 1 là b. Z luôn so với **tiền tố bắt đầu ở 0**, không so với tiền tố ở vị trí i−1.

### Tính Z khác với tìm một mẫu

Hàm Z nhận **một chuỗi duy nhất** và trả mảng cùng độ dài. Để dùng cho bài tìm mẫu P trong văn bản T, ta biến đổi bài toán thành tính Z của **một chuỗi kết hợp**; các vị trí trong phần văn bản sẽ phản ánh độ dài khớp với P.

## 2. Thuật toán Z cơ bản O(n²) và vấn đề tính lại

Một cách đúng nhưng có thể chậm:

~~~text
for i = 1 .. n-1:
    k = 0
    while i+k < n and S[k] == S[i+k]:
        k++
    Z[i] = k
~~~

Với `S="aaaaaaaa..."`, tại mỗi i ta so nhiều ký tự giống nhau. Tổng số lần so sánh có thể khoảng `(n−1)+(n−2)+...+1 = Θ(n²)`. Nếu phải tìm mẫu trong văn bản hàng triệu ký tự, cách này lãng phí.

Thuật toán tuyến tính dùng kết quả khớp trước đó để **không so lại những phần chắc chắn bằng nhau**.

## 3. Cửa sổ [L,R) trong thuật toán Z tuyến tính

Duy trì đoạn `[L,R)`, còn gọi là *Z-box*, sao cho:

\[
S[L..R-1]=S[0..R-L-1].
\]

Nghĩa là đoạn hiện tại **khớp với tiền tố S**, và `R` là biên phải **loại trừ**. Ta thường duy trì box có **biên phải xa nhất** đã xác nhận trong quá trình duyệt từ trái sang phải.

Ban đầu `L=R=0`. Với mỗi `i` từ 1 tới n−1, xét hai trường hợp.

### Trường hợp A — i nằm ngoài box: i ≥ R

Ta chưa biết một đoạn nào bắt đầu ở i khớp với tiền tố. Bắt đầu `Z[i]=0`, so trực tiếp:

~~~text
while i + Z[i] < n
      and S[Z[i]] == S[i + Z[i]]:
    Z[i]++
~~~

Nếu đạt biên phải mới xa hơn R, cập nhật:

~~~text
L = i
R = i + Z[i]
~~~

### Trường hợp B — i nằm trong box: i < R

Vì `[L,R)` đã biết trùng với tiền tố, phần ở vị trí `i` ứng với vị trí `k=i−L` trong tiền tố. Ta đã tính `Z[k]` trước đó vì `k<i`. Có thể khởi tạo:

\[
\boxed{Z[i]=\min(R-i,\ Z[i-L]).}
\]

Ý nghĩa của hai giá trị:
- `Z[i-L]`: độ dài trùng đã biết ở vị trí tương ứng bên trong tiền tố.
- `R−i`: lượng ký tự còn lại **bên trong box đã chứng minh khớp**.

Ta không được tự gán vượt `R-i` vì các ký tự sau R chưa có bảo đảm. Sau khởi tạo, tiếp tục so trực tiếp nếu có khả năng mở rộng ngoài box, rồi cập nhật `L=i, R=i+Z[i]` nếu biên phải được đẩy xa hơn.

### Giả mã chuẩn với đoạn nửa mở

~~~text
zFunction(S):
    n = length(S)
    Z = array[n] filled 0
    L = 0
    R = 0

    for i = 1 .. n-1:
        if i < R:
            Z[i] = min(R-i, Z[i-L])

        while i+Z[i] < n
              and S[Z[i]] == S[i+Z[i]]:
            Z[i]++

        if i+Z[i] > R:
            L = i
            R = i+Z[i]

    return Z
~~~

**Lưu ý:** đây là quy ước `[L,R)`. Một số tài liệu dùng đoạn **đóng** `[L,R]`; khi đó công thức thường xuất hiện dưới dạng `R−i+1`. Không được trộn hai biến thể.

Trong mã Java phía dưới, vòng lặp của Z làm việc trên mảng `int[]` (Unicode code point và sentinel) nhưng logic khớp hoàn toàn giống trên chuỗi ký tự.

## 4. Tại sao công thức trong Z-box đúng?

Giả sử i nằm trong `[L,R)`. Ta đã biết:

\[
S[L+t]=S[t]\quad\text{với mọi }0\le t<R-L.
\]

Đặt `k=i−L`. Với mỗi `t` sao cho `0≤t<R−i`, từ đẳng thức của box ta có:

\[
S[i+t]=S[k+t].
\]

Vì `Z[k]` là độ dài tiền tố khớp với hậu tố ở k, trong phạm vi cả hai còn ở box, số ký tự đầu chắc chắn khớp là:

\[
\min(Z[k],R-i).
\]

Nếu `Z[k]<R−i`, ta biết ngay ký tự sau đoạn này khác nhau **ở trong box**, nên Z[i] có thể dừng ở đó. Nếu `Z[k]≥R−i`, ta chỉ biết chắc khớp tới R−1, phải so thêm từ biên R. Vòng while mở rộng đúng phần chưa được chứng minh.

Vì thế việc dùng box **không tạo ra độ dài Z lớn giả**, và phần so thêm vẫn đi đến độ dài khớp lớn nhất có thể tại i.

### Vì sao tổng thời gian là O(n)?

Vòng for đi qua n−1 vị trí, mỗi lượt có O(1) phép khởi tạo bằng min. Trong vòng while, những lần so khớp **thành công để mở rộng ra ngoài box** sẽ đẩy biên phải `R` đi lên. Biên phải không giảm và không vượt n, nên tổng số lần mở rộng mới **O(n)**. Mỗi i có nhiều nhất một phép so thất bại kết thúc việc mở rộng. Do đó toàn bộ vòng while cũng có tổng O(n), thay vì O(n²).

Độ phức tạp:

\[
\boxed{\text{Z-function: }O(n)\text{ thời gian, }O(n)\text{ bộ nhớ cho mảng Z}.}
\]

Ngoài mảng Z, thuật toán chỉ cần vài biến chỉ số O(1); nếu đầu vào được giữ sẵn dưới dạng mảng thì không cần mảng sao chép riêng để tính Z.

## 5. Từ so khớp mẫu sang chuỗi ghép

Giả sử cần tìm **mọi vị trí bắt đầu** mà mẫu `P` (độ dài m) xuất hiện trong văn bản `T` (độ dài n). Ta tạo:

\[
\boxed{S=P+\# +T,}
\]

trong đó `#` là một ký hiệu phân cách được chọn **không xuất hiện trong P hoặc T** theo cách trình bày tiêu chuẩn.

Chuỗi ghép dài `m+1+n`. Vị trí:
- `[0,m)` là mẫu P;
- `m` là ký hiệu ngăn cách;
- `[m+1,m+1+n)` là văn bản T.

Tại vị trí `i=m+1+j`, phần hậu tố của S bắt đầu ở **vị trí j của văn bản**. Tiền tố của S bắt đầu bằng P. Do đó:

\[
\boxed{P\text{ khớp tại }T[j]\iff Z[m+1+j]\ge m.}
\]

Và khi tìm thấy một `i` trong phần văn bản có `Z[i]\ge m`, chuyển ngược về chỉ số văn bản:

\[
\boxed{j=i-(m+1).}
\]

Điều kiện khớp đúng khi đoạn văn bản từ j có ít nhất m ký tự trùng toàn bộ mẫu P.

### Vì sao nên dùng dấu phân cách không nằm trong hai chuỗi?

Nếu `#` không có trong P/T, sau khi khớp hết m ký tự của P, tiền tố S sẽ gặp `#` trong khi phần tiếp theo của văn bản không có `#`. Nhờ đó với một vị trí i bắt đầu trong T, `Z[i]≤m`, công thức trên thường được viết `Z[i]=m`.

Nếu ký hiệu phân cách tình cờ cũng có trong dữ liệu, Z có thể dài **vượt qua biên mẫu** và dễ gây hiểu lầm khi phân tích giá trị; tuy vậy điều kiện **Z[i]≥m ở các vị trí thuộc phần T** vẫn kiểm tra đủ m ký tự đầu của mẫu. Để giữ bất biến sạch, cách cài đặt thông dụng chọn ký hiệu **không có trong cả hai chuỗi**.

Nếu không tìm được một ký tự có thể bảo đảm vắng mặt, **không nên mặc định rằng '#' là an toàn**. Chương trình Java dùng một sentinel **số nguyên −1** đặt giữa hai mảng Unicode code point; code point của chuỗi Java không âm, nên −1 chắc chắn phân biệt được với mọi phần tử thực, kể cả dấu #, emoji và chữ tiếng Việt.

### Mẫu dài hơn văn bản

Nếu `m>n` thì không thể có khớp đầy đủ; trả danh sách rỗng. Nếu `m≤n`, chỉ những j thỏa `0≤j≤n−m` mới có thể khớp; ta có thể xét mọi j trong phần T và kiểm tra `Z[m+1+j]≥m` vì j quá gần cuối sẽ tự có Z nhỏ hơn m.

### Các lần xuất hiện chồng lấn

Không được nhảy j thêm m sau khi tìm thấy một lần khớp. Ví dụ:
- `P="aa"`,
- `T="aaaa"`.

Có **ba** vị trí khớp **0,1,2**, chứ không phải hai. Thuật toán Z duyệt từng vị trí trong phần T nên giữ được các lần khớp chồng lấn.

## 6. Ví dụ tính tay: P="aba", T="ababaaba"

Mẫu dài m=3; văn bản dài n=8. Ghép với `#` (không nằm trong hai chuỗi):

~~~text
S = "aba#ababaaba"

i:      0 1 2 3 4 5 6 7 8 9 10 11
S[i]:   a b a # a b a b a a  b  a
Z[i]:   0 0 1 0 3 0 3 0 1 3  0  1
~~~

Mẫu `P="aba"` ở vị trí 0..2 của S. Dấu phân cách ở vị trí 3. Văn bản T bắt đầu tại vị trí 4 của S. Ta chỉ kiểm tra các i từ 4 tới 11.

| i trong S | j=i−4 trong T | Z[i] | Có khớp P dài 3? |
| ---: | ---: | ---: | --- |
| 4 | 0 | 3 | Có |
| 5 | 1 | 0 | Không |
| 6 | 2 | 3 | Có |
| 7 | 3 | 0 | Không |
| 8 | 4 | 1 | Không |
| 9 | 5 | 3 | Có |
| 10 | 6 | 0 | Không |
| 11 | 7 | 1 | Không |

Kết luận:

\[
\boxed{\text{Vị trí khớp trong T}=[0,2,5].}
\]

Tại j=0, T[0..2] là `"aba"`. Tại j=2, T[2..4] cũng là `"aba"`, chồng lấn với lần đầu. Tại j=5, T[5..7] là `"aba"`.

**Lỗi chỉ số rất dễ gặp:** nếu lấy ngay i=4,6,9 làm vị trí trả về sẽ **sai**: đây là vị trí trong **chuỗi ghép**. Phải trừ đúng `m+1=4`, không phải trừ m, cũng không phải trả chỉ số bắt đầu từ 1 nếu đề yêu cầu 0-based.

### Ví dụ khác: P="ana", T="bananana"

Các lần xuất hiện tại **[1,3,5]**; chúng chồng lấn. Ví dụ này hữu ích để kiểm tra thuật toán thực sự trả **tất cả** vị trí, không chỉ vị trí đầu tiên.

## 7. Độ phức tạp của toàn phép so khớp

Với mẫu dài m và văn bản dài n:
1. Chuyển/ghép mẫu, dấu phân cách và văn bản: O(m+n).
2. Tính Z trên chuỗi ghép độ dài m+1+n: O(m+n).
3. Duyệt từng vị trí văn bản, lấy các j có Z đủ m: O(n).

Tổng:

\[
\boxed{O(m+n)\text{ thời gian, }O(m+n)\text{ bộ nhớ}.}
\]

Danh sách kết quả cần thêm O(k) phần tử với k là số lần khớp; `k≤n−m+1` nếu m>0. Vì Z vốn giữ m+1+n số nguyên nên bộ nhớ toàn lời giải là O(m+n), chưa tính chi phí đối tượng của danh sách boxing trong Java.

**Không nhầm với so khớp ngây thơ** O(mn) trong trường hợp xấu khi thử m ký tự tại từng vị trí. Z đạt tuyến tính cho **một mẫu**, tương tự KMP ở độ phức tạp tổng thể.

Nếu cần kiểm tra nhiều mẫu độc lập trên cùng T, cách trực tiếp chạy riêng mỗi mẫu sẽ tốn tổng độ dài các chuỗi ghép và các lượt quét văn bản; muốn xử lý hàng nghìn mẫu đồng thời cần cân nhắc Aho–Corasick, suffix array/automaton hoặc cấu trúc chuyên biệt thay vì tự gọi Z vô hạn lần.

## 8. Unicode, chỉ số code point và UTF-16 trong Java

Java `String` dùng chỉ số dựa trên **UTF-16 code unit**, còn người dùng thường nghĩ theo Unicode **code point**. Ký tự ngoài BMP, ví dụ emoji `"🍎"`, chiếm **hai char** UTF-16 nhưng một Unicode code point.

Bài chọn rõ ngữ nghĩa:
- Hàm `findCodePointPositions` trả vị trí **0-based theo code point**.
- Hàm `toUtf16Offsets` đổi mỗi vị trí ấy sang offset **0-based theo Java String/UTF-16**.
- Dữ liệu so sánh được lấy bằng `String.codePoints().toArray()`; một mảng int biểu diễn các điểm mã Unicode theo thứ tự.

Ví dụ:

~~~text
P = "🍎a"
T = "🍎a🍎a"

Code point của T: [🍎, a, 🍎, a]
Vị trí khớp theo code point: [0, 2]
Vị trí khớp theo UTF-16 char:  [0, 3]
~~~

Chỉ số 2 theo code point tương ứng offset 3 trong String vì emoji đầu chiếm 2 đơn vị UTF-16. Không được nhầm hai hệ chỉ số nếu lấy kết quả dùng trực tiếp với `substring` hoặc API Java dựa trên char offset.

**Giới hạn ngữ nghĩa:** Unicode code point không đồng nhất với “ký tự hiển thị” (*grapheme cluster*). Các chuỗi có chữ có dấu dựng sẵn và chữ cơ sở kết hợp dấu có thể có chuỗi code point khác dù nhìn giống nhau. Bài tìm **đúng dãy code point**, không tự chuẩn hóa, không tự bỏ dấu, không tự so không phân biệt hoa–thường. Nếu đề yêu cầu chuẩn hóa như NFC hoặc case folding, phải xử lý **cả P và T nhất quán** và xác định vị trí trả về thuộc văn bản gốc hay đã chuẩn hóa.

### Vì sao dùng dấu phân cách số nguyên −1?

Mảng code point chứa các số nguyên không âm. Đặt sentinel `-1` giữa mẫu và văn bản tạo:

~~~text
[int code points của P] [-1] [int code points của T]
~~~

Sentinel không thể trùng một code point thực nào. Như vậy không cần quét tìm một dấu phân cách hiếm, không phụ thuộc việc mẫu/văn bản có dấu `#`, `$` hay emoji.

Đây vẫn là **cùng thuật toán Z trên chuỗi ghép**, chỉ thay chuỗi kết hợp bằng một dãy số nguyên để bảo đảm phân cách chính xác.

## 9. Chương trình Java 17 độc lập

Mã gồm:
- `zValues(int[])` tính Z tuyến tính với box `[left,right)`, `Z[0]=0`.
- `findCodePointPositions(pattern,text)` xây dãy `P + [-1] + T` và thu các j có `Z[m+1+j]≥m`.
- `toUtf16Offsets` đổi vị trí code point sang offset UTF-16 trong Java String.
- `naiveMatches` là thuật toán tham chiếu O(mn), **độc lập với Z**, để so kiểm.
- `verifyZArrays` so hàm Z tuyến tính với cách so trực tiếp trên **3.280 chuỗi ngắn**.
- `verifyMatching` so Z-matching với naive trên **32.125 cặp mẫu–văn bản**, bao gồm Unicode, mẫu/văn bản rỗng và ký tự giống dấu phân cách thông dụng.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class ZFunctionMatchingDemo {
    // Quy uoc: Z[0]=0; box [left,right) nua mo.
    static int[] zValues(int[] a) {
        Objects.requireNonNull(a, "sequence");
        int n = a.length;
        int[] z = new int[n];
        int left = 0, right = 0;

        for (int i = 1; i < n; i++) {
            if (i < right) {
                z[i] = Math.min(right - i, z[i - left]);
            }
            while (i + z[i] < n
                    && a[z[i]] == a[i + z[i]]) {
                z[i]++;
            }
            if (i + z[i] > right) {
                left = i;
                right = i + z[i];
            }
        }
        return z;
    }

    // Ket qua: offset 0-based theo UNICODE CODE POINT.
    static List<Integer> findCodePointPositions(
            String pattern, String text) {
        Objects.requireNonNull(pattern, "pattern");
        Objects.requireNonNull(text, "text");
        int[] p = pattern.codePoints().toArray();
        int[] t = text.codePoints().toArray();
        int m = p.length, n = t.length;
        List<Integer> matches = new ArrayList<>();

        // Quy uoc: mau rong khop o n+1 ranh gioi.
        if (m == 0) {
            for (int j = 0; j <= n; j++) {
                matches.add(j);
            }
            return matches;
        }
        if (m > n) return matches;

        // -1 khong the trung mot Java Unicode code point.
        int[] joined = new int[m + 1 + n];
        System.arraycopy(p, 0, joined, 0, m);
        joined[m] = -1;
        System.arraycopy(t, 0, joined, m + 1, n);

        int[] z = zValues(joined);
        for (int j = 0; j < n; j++) {
            int indexInJoined = m + 1 + j;
            if (z[indexInJoined] >= m) {
                matches.add(j);
            }
        }
        return matches;
    }

    // Doi code point offset sang Java String UTF-16 offset.
    static List<Integer> toUtf16Offsets(
            String text, List<Integer> codePointPositions) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(
                codePointPositions, "codePointPositions");
        int[] cps = text.codePoints().toArray();
        int[] offsets = new int[cps.length + 1];
        for (int i = 0; i < cps.length; i++) {
            offsets[i + 1] = offsets[i]
                    + Character.charCount(cps[i]);
        }

        List<Integer> result = new ArrayList<>();
        for (int position : codePointPositions) {
            if (position < 0 || position > cps.length) {
                throw new IllegalArgumentException(
                        "Invalid code point offset");
            }
            result.add(offsets[position]);
        }
        return result;
    }

    // Oracle so khop NGAY THO, khong dung Z.
    static List<Integer> naiveMatches(
            String pattern, String text) {
        int[] p = pattern.codePoints().toArray();
        int[] t = text.codePoints().toArray();
        List<Integer> answer = new ArrayList<>();

        for (int start = 0;
                start + p.length <= t.length;
                start++) {
            boolean equal = true;
            for (int i = 0; i < p.length; i++) {
                if (p[i] != t[start + i]) {
                    equal = false;
                    break;
                }
            }
            if (equal) answer.add(start);
        }
        return answer;
    }

    // Oracle Z[i] O(n^2) bang so sanh truc tiep.
    static int[] slowZ(int[] a) {
        int[] z = new int[a.length];
        for (int i = 1; i < a.length; i++) {
            while (i + z[i] < a.length
                    && a[z[i]] == a[i + z[i]]) {
                z[i]++;
            }
        }
        return z;
    }

    static List<String> allWords(
            char[] alphabet, int maxLength) {
        List<String> all = new ArrayList<>();
        List<String> layer = new ArrayList<>();
        all.add("");
        layer.add("");

        for (int length = 1;
                length <= maxLength;
                length++) {
            List<String> next = new ArrayList<>();
            for (String prefix : layer) {
                for (char ch : alphabet) {
                    next.add(prefix + ch);
                }
            }
            all.addAll(next);
            layer = next;
        }
        return all;
    }

    static void assertMatches(String p, String t) {
        List<Integer> actual = findCodePointPositions(p, t);
        List<Integer> oracle = naiveMatches(p, t);
        if (!actual.equals(oracle)) {
            throw new AssertionError(
                    "Mismatch pattern=" + p + " text=" + t
                    + " actual=" + actual
                    + " oracle=" + oracle);
        }

        // Kiem tra offset UTF-16 danh cho String API.
        List<Integer> charOffsets = toUtf16Offsets(t, actual);
        for (int offset : charOffsets) {
            if (!t.startsWith(p, offset)) {
                throw new AssertionError(
                        "Bad UTF-16 offset=" + offset);
            }
        }
    }

    static int verifyZArrays() {
        int checked = 0;
        for (String word : allWords(
                new char[]{'a', 'b', 'c'}, 7)) {
            int[] a = word.codePoints().toArray();
            if (!Arrays.equals(zValues(a), slowZ(a))) {
                throw new AssertionError(
                        "Bad Z array for " + word);
            }
            checked++;
        }
        // 1+3+9+27+81+243+729+2187 = 3280.
        return checked;
    }

    static int randomState = 3692026;

    // Bo sinh so 32-bit xac dinh, dung gia tri unsigned.
    static int randomInt(int bound) {
        randomState = randomState * 1664525
                + 1013904223;
        return (int) (Integer.toUnsignedLong(randomState)
                % bound);
    }

    static int verifyMatching() {
        int checked = 0;

        List<String> patterns2 =
                allWords(new char[]{'a', 'b'}, 5);
        List<String> texts2 =
                allWords(new char[]{'a', 'b'}, 7);
        for (String p : patterns2) {
            for (String t : texts2) {
                assertMatches(p, t);
                checked++;
            }
        }

        List<String> patterns3 =
                allWords(new char[]{'a', 'b', 'c'}, 3);
        List<String> texts3 =
                allWords(new char[]{'a', 'b', 'c'}, 5);
        for (String p : patterns3) {
            for (String t : texts3) {
                assertMatches(p, t);
                checked++;
            }
        }

        String[] alphabet = {
            "a", "b", "#", "🙂", "🍎", "é", "ắ", "𝄞", "🧠"
        };
        for (int test = 0; test < 1500; test++) {
            int m = randomInt(7);
            int n = randomInt(15);
            StringBuilder p = new StringBuilder();
            StringBuilder t = new StringBuilder();

            for (int i = 0; i < m; i++) {
                p.append(alphabet[randomInt(alphabet.length)]);
            }
            for (int i = 0; i < n; i++) {
                t.append(alphabet[randomInt(alphabet.length)]);
            }
            assertMatches(p.toString(), t.toString());
            checked++;
        }

        // (63*255) + (40*364) + 1500 = 32125.
        return checked;
    }

    public static void main(String[] args) {
        System.out.println("Z(aabcaabxaaaz)="
                + Arrays.toString(zValues(
                    "aabcaabxaaaz".codePoints().toArray())));

        String joinedDemo = "aba#ababaaba";
        System.out.println("joined=" + joinedDemo);
        System.out.println("Z(joined)="
                + Arrays.toString(zValues(
                    joinedDemo.codePoints().toArray())));

        System.out.println("aba=" +
                findCodePointPositions("aba", "ababaaba"));
        System.out.println("ana=" +
                findCodePointPositions("ana", "bananana"));
        System.out.println("overlap=" +
                findCodePointPositions("aa", "aaaa"));
        System.out.println("middle=" +
                findCodePointPositions("abc", "zzabcab"));
        System.out.println("missing=" +
                findCodePointPositions("xy", "abc"));
        System.out.println("emptyPattern=" +
                findCodePointPositions("", "abc"));
        System.out.println("emptyText=" +
                findCodePointPositions("x", ""));
        System.out.println("bothEmpty=" +
                findCodePointPositions("", ""));

        String text = "🍎a🍎a";
        List<Integer> unicode =
                findCodePointPositions("🍎a", text);
        System.out.println("unicodeCodePoints=" + unicode);
        System.out.println("unicodeUtf16="
                + toUtf16Offsets(text, unicode));

        System.out.println("hashPattern=" +
                findCodePointPositions("#", "#a#"));

        System.out.println(
                "verifiedZStrings=" + verifyZArrays());
        System.out.println(
                "verifiedPatternTextPairs=" + verifyMatching());
    }
}
~~~

Lưu mã vào **ZFunctionMatchingDemo.java**, chạy bằng JDK 17 trở lên:

~~~bash
javac ZFunctionMatchingDemo.java
java ZFunctionMatchingDemo
~~~

**Đầu ra dự kiến, với danh sách vị trí 0-based:**

~~~text
Z(aabcaabxaaaz)=[0, 1, 0, 0, 3, 1, 0, 0, 2, 2, 1, 0]
joined=aba#ababaaba
Z(joined)=[0, 0, 1, 0, 3, 0, 3, 0, 1, 3, 0, 1]
aba=[0, 2, 5]
ana=[1, 3, 5]
overlap=[0, 1, 2]
middle=[2]
missing=[]
emptyPattern=[0, 1, 2, 3]
emptyText=[]
bothEmpty=[0]
unicodeCodePoints=[0, 2]
unicodeUtf16=[0, 3]
hashPattern=[0, 2]
verifiedZStrings=3280
verifiedPatternTextPairs=32125
~~~

### Cách đọc chương trình

Hàm `zValues` dùng cửa sổ **[left,right)**. Với mỗi i:
- Nếu `i<right`, dùng `min(right-i,z[i-left])` để tận dụng phần chắc chắn đã khớp.
- Vòng `while` chỉ so thêm khi cần.
- Nếu `i+z[i]>right`, đặt box mới từ i đến `i+z[i]`.

Hàm `findCodePointPositions` chuyển P và T sang `int[]` Unicode code point, chèn sentinel `-1`, rồi xét **chỉ phần văn bản**: với j trong T, kiểm tra `z[m+1+j]≥m`. Hàm trả **j**, không trả `m+1+j`.

**Mẫu rỗng** được xử lý riêng: với T có n code point, mẫu rỗng xuất hiện tại **n+1 ranh giới** `[0,1,...,n]`. Đây là quy ước được chọn rõ cho chương trình; một số bài thi quy định khác, vì vậy cần tuân thủ đề. Với cả P và T rỗng, kết quả là `[0]`. Với P không rỗng, T rỗng, kết quả `[]`.

**Không dùng String.length() làm số code point.** Ví dụ T có emoji, Java String.length() đếm UTF-16 char code units. Chương trình trả vị trí theo code point trước rồi đổi sang offset Java khi cần.

### Một chú ý về dữ liệu lớn

Mảng `int[] joined` cần `m+1+n` phần tử và mảng Z có kích thước tương đương. Trong bài thực tế, cần bảo đảm tổng độ dài đủ nhỏ để cấp phát và không tràn phép cộng độ dài kiểu `int`. Hàm minh họa giả định đầu vào có thể chứa trong mảng Java, không xử lý chuỗi dài vượt giới hạn mảng.

Bộ kiểm thử được tách khỏi thuật toán: `verifyZArrays` và `verifyMatching` chỉ chạy khi gọi trong `main` để học/kiểm chứng, không phải những bước cần thiết mỗi khi tìm một mẫu trong chương trình sản phẩm.

## 10. Kiểm thử độc lập thay vì chỉ nhìn ví dụ

Để kiểm tra **bản chất của Z**, `verifyZArrays` tạo mọi chuỗi trên bảng chữ cái `{a,b,c}` có độ dài 0..7. Số chuỗi:

\[
1+3+3^2+...+3^7=\boxed{3280}.
\]

Với từng chuỗi, so toàn bộ mảng Z tuyến tính với mảng Z tính bằng **so sánh ký tự trực tiếp** O(n²). Phép đối chiếu này bắt được lỗi khởi tạo `Z[i]`, lỗi biên box và lỗi cập nhật `right`.

Để kiểm tra **so khớp bằng chuỗi ghép**, `verifyMatching` dùng oracle khác: với từng vị trí bắt đầu j của T, so trực tiếp từng code point của P và T để xây danh sách khớp.

| Nhóm | Số mẫu P | Số văn bản T | Số phép đối chiếu |
| --- | ---: | ---: | ---: |
| Chữ cái {a,b}, P dài 0..5, T dài 0..7 | 63 | 255 | 16.065 |
| Chữ cái {a,b,c}, P dài 0..3, T dài 0..5 | 40 | 364 | 14.560 |
| Cặp Unicode sinh xác định, bao gồm # và emoji | — | — | 1.500 |
| **Tổng** | | | **32.125** |

Nhóm Unicode bổ sung gồm ký tự ASCII, dấu #, các chữ có dấu như `é, ắ`, emoji và ký tự ngoài BMP. Trên tất cả các cặp, danh sách kết quả của Z phải **bằng đúng** danh sách của oracle, bao gồm thứ tự và số lần khớp chồng lấn. Mỗi vị trí code point được chuyển sang UTF-16 offset, kiểm tra `text.startsWith(pattern, offset)`.

Các tập kiểm thử bao gồm **P rỗng, T rỗng, P dài hơn T, mẫu trùng lặp, chuỗi cùng ký tự, Unicode nhiều đơn vị UTF-16 và ký hiệu giống dấu phân cách**. Đây là kiểm thử hữu hạn; tính đúng tổng quát vẫn dựa vào chứng minh Z-box và điều kiện `Z[m+1+j]≥m`.

## 11. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Nhầm Z[i] với prefix-function pi[i] | Z so tiền tố với hậu tố bắt đầu ở i; pi đo border của tiền tố kết thúc ở i | Xác định đúng định nghĩa của mảng |
| Dùng Z[0]=n ở nơi yêu cầu 0 | Quy ước khác, dễ sai khi in/test | Chốt trước Z[0]=0 hoặc n |
| Nhầm [L,R) thành [L,R] | Sai độ dài R−i và lệch một biên | Dùng nhất quán nửa mở |
| Gán `Z[i]=Z[i-L]` mà quên min | Có thể vượt biên box đã chứng minh | Dùng `min(R-i,Z[i-L])` |
| Không so thêm khi i gần R | Bỏ mất khớp vượt box | Dùng vòng while mở rộng |
| Không cập nhật R khi mở rộng xa hơn | Mất lợi ích tuyến tính | Khi `i+Z[i]>R`, cập nhật L,R |
| Dùng dấu phân cách không phân biệt dữ liệu nhưng tưởng Z≤m | Có thể kéo Z qua biên mẫu | Chọn sentinel độc nhất như −1 |
| Kiểm tra Z trong vùng P | Đếm cả tiền tố bên trong mẫu là kết quả T | Chỉ xét i≥m+1 |
| Trả i thay vì i−m−1 | Kết quả lệch theo vị trí chuỗi ghép | Đổi về chỉ số văn bản j |
| Dùng `Z[i]>m` | Bỏ những khớp dài đúng m | Dùng `Z[i]≥m` |
| Dừng sau khớp đầu | Bỏ kết quả khác và chồng lấn | Duyệt mọi j hợp lệ |
| Dùng `String.length()` làm số code point | Emoji chiếm hai char | Chọn và công bố hệ chỉ số |
| Không định nghĩa mẫu rỗng | Kết quả khác nhau theo quy ước | Bài này trả mọi ranh giới |
| So khớp không phân biệt hoa thường dù code dùng so đúng | Hai ngữ nghĩa khác nhau | Chuẩn hóa trước nếu đề yêu cầu |
| Xem thời gian O(1) mỗi i vì Z[i] có thể dài | Bỏ qua tổng while | Dùng lập luận biên R tăng O(n) |
| Chia/dịch kết quả thành 1-based tùy tiện | Sai hợp đồng đầu ra | Bài trả 0-based; chỉ cộng 1 nếu đề yêu cầu |

### So sánh nhanh với KMP và tiền tố–hậu tố

**KMP** sử dụng *prefix function* hoặc bảng thất bại để không so lại những phần đã biết; có thể xử lý luồng văn bản theo ký tự và không cần lưu trọn `P + dấu + T` như bản Z xây mảng.

**Z** đo độ dài tiền tố trùng trực tiếp tại **mọi vị trí**, thích hợp để giải thích tiền tố khớp, tìm các lần xuất hiện, phát hiện chu kỳ hoặc bài toán trên chuỗi ghép. Hai kỹ thuật đều có thể giải một bài tìm mẫu với thời gian O(m+n), nhưng **định nghĩa mảng và cách cập nhật khác nhau**.

Nếu bài cần tất cả mẫu xuất hiện đồng thời trong văn bản, dùng riêng KMP/Z cho mỗi mẫu có thể không tối ưu tổng thể; nên xem xét Aho–Corasick hoặc những cấu trúc cho đa mẫu.

## 12. Bài tập tự luyện có đáp án

**Bài 1 — định nghĩa.** Với `S="aaaa"` và quy ước Z[0]=0, mảng Z là gì?

*Đáp án:* `[0,3,2,1]`. Từ i=1 còn ba ký tự a khớp, từ i=2 còn hai, từ i=3 còn một.

**Bài 2 — Z tại một vị trí.** Với `S="ababa"`, Z[2] bằng mấy?

*Đáp án:* 3, vì đoạn bắt đầu vị trí 2 là `"aba"` trùng ba ký tự đầu của S.

**Bài 3 — cửa sổ.** Nếu `[L,R)=[3,9)` và `i=6`, phần chắc chắn nằm trong box còn bao nhiêu ký tự?

*Đáp án:* `R−i=3`. Ta khởi tạo `Z[6]=min(3,Z[6−3])=min(3,Z[3])` rồi thử mở rộng.

**Bài 4 — đoạn nửa mở.** Tại sao công thức dùng `R−i` chứ không dùng `R−i+1`?

*Đáp án:* Vì R là vị trí **ngay sau** ký tự cuối của box; số phần tử từ i tới R−1 bằng R−i.

**Bài 5 — chuỗi ghép.** Với P dài 4, phần T bắt đầu ở vị trí nào của `P + # + T`?

*Đáp án:* 5 (=m+1).

**Bài 6 — đổi chỉ số.** P dài 4, thấy Z[12]≥4 tại một vị trí của phần văn bản. Vị trí trong T là gì?

*Đáp án:* `12−(4+1)=7`.

**Bài 7 — nhiều khớp.** Với P="aba", T="ababaaba", các vị trí khớp?

*Đáp án:* `[0,2,5]`, gồm một lần khớp chồng lấn.

**Bài 8 — khớp chồng lấn.** Với P="aa", T="aaaa", có mấy lần xuất hiện và ở đâu?

*Đáp án:* Ba lần: `[0,1,2]`.

**Bài 9 — dài hơn.** P="abcdef", T="abc" cho gì?

*Đáp án:* Danh sách rỗng vì mẫu dài hơn văn bản.

**Bài 10 — mẫu rỗng.** P="" và T="abc" trả gì theo quy ước bài?

*Đáp án:* `[0,1,2,3]`, bốn ranh giới của ba code point.

**Bài 11 — cả hai rỗng.** P="" và T="" trả gì?

*Đáp án:* `[0]`, vị trí ranh giới duy nhất.

**Bài 12 — Unicode.** P="🍎a", T="🍎a🍎a", offset theo code point và UTF-16 là gì?

*Đáp án:* Code point `[0,2]`, UTF-16 `[0,3]`.

**Bài 13 — dấu phân cách.** Vì sao mảng int code points với sentinel −1 mạnh hơn dùng ký tự '#' cố định?

*Đáp án:* −1 không thể bằng bất cứ code point thực nào; '#' có thể xuất hiện trong dữ liệu, khiến những diễn giải Z bị vượt biên mẫu.

**Bài 14 — độ phức tạp.** P dài m, T dài n. Thời gian tính một lần tất cả vị trí khớp bằng Z là gì?

*Đáp án:* O(m+n) cho ghép, tính Z và quét kết quả. Bộ nhớ O(m+n).

**Bài 15 — giải thích tối ưu.** Vì sao vòng while trong thuật toán Z không tự làm thời gian thành O(n²)?

*Đáp án:* Những lần mở rộng thành công ra ngoài box tăng biên phải R; R tăng tối đa n lần, cộng tối đa một phép so thất bại mỗi lượt i. Tổng so sánh O(n).

**Bài 16 — so quy ước.** Một thư viện đặt Z[0]=n nhưng chương trình bài đặt Z[0]=0. Có làm thay đổi vị trí khớp khi quét phần T hay không?

*Đáp án:* Không, nếu các Z[i] với i>0 được tính nhất quán; hai chương trình khác riêng giá trị Z[0], không ảnh hưởng kiểm tra các vị trí trong văn bản của chuỗi ghép.

## 13. Checklist khi triển khai

1. Xác định chuỗi nào là **mẫu P**, chuỗi nào là **văn bản T**, các chỉ số 0-based hay 1-based.
2. Hiểu `Z[i]` là độ dài tiền tố khớp bắt đầu ở i; ghi rõ `Z[0]`.
3. Dùng cửa sổ `[L,R)` nhất quán với `min(R-i,Z[i-L])`, chỉ mở rộng vượt phần đã biết.
4. Chuỗi ghép phải có dạng **P + sentinel + T**, không đảo P/T.
5. Chọn dấu phân cách chắc chắn phân biệt với dữ liệu; với Unicode code points có thể dùng int −1.
6. Chỉ xét Z ở **phần T** và trả đúng `j=i−m−1`.
7. Dùng `Z[i]≥m`, không đòi lớn hơn m.
8. Duyệt mọi vị trí để nhận cả những lần khớp **chồng lấn**.
9. Xử lý P rỗng, T rỗng, P dài hơn T, ký tự lặp và dữ liệu Unicode.
10. Không nhầm Java UTF-16 offset với code point offset; công bố quy ước kết quả.
11. Kiểm tra kích thước m+n+1 trước khi cấp phát mảng lớn.
12. Đối chiếu Z và vị trí mẫu với thuật toán ngây thơ trên chuỗi nhỏ và với dữ liệu bất kỳ.

## Tổng kết

**Hàm Z** biến câu hỏi “tiền tố của chuỗi khớp bao xa tại vị trí i?” thành một mảng tính được **O(n)** nhờ box `[L,R)`. Với bài tìm mẫu, dựng chuỗi ghép **P + dấu phân cách + T**. Khi `m=|P|`, mọi j thỏa `Z[m+1+j]≥m` là một vị trí xuất hiện của P trong T.

Thuật toán tìm tất cả vị trí, kể cả **khớp chồng lấn**, trong **O(m+n)** thời gian và bộ nhớ. Cài đặt Java 17 bằng **Unicode code points và sentinel −1** làm rõ dấu phân cách, đồng thời tránh nhầm chỉ số UTF-16. Với mẫu rỗng, bài dùng quy ước trả mọi ranh giới code point. Bộ kiểm thử đối chiếu độc lập **3.280 mảng Z** và **32.125 cặp mẫu–văn bản** giúp phát hiện lỗi biên, khóa phân cách và chuyển đổi chỉ số.
