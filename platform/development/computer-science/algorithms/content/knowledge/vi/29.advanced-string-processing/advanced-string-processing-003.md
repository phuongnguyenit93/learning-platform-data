# Dựng mảng hậu tố bằng phương pháp nhân đôi

**Chủ đề:** Computer Science Algorithms · Xử lý chuỗi nâng cao

## 1. Bài toán và định nghĩa mảng hậu tố

Cho văn bản T gồm n ký hiệu. **Hậu tố (suffix) bắt đầu tại i** là phần dãy T[i..n), tức từ vị trí i đến hết văn bản. **Mảng hậu tố (suffix array, SA)** là một hoán vị của các vị trí 0,1,...,n−1 sao cho các hậu tố tương ứng được sắp theo **thứ tự từ điển**:

\[
T[SA[0]..n)<T[SA[1]..n)<\cdots<T[SA[n-1]..n).
\]

Với T="banana":

| i | Hậu tố |
|---:|---|
| 0 | banana |
| 1 | anana |
| 2 | nana |
| 3 | ana |
| 4 | na |
| 5 | a |

Sắp theo thứ tự từ điển:

| Thứ hạng r | SA[r] | Hậu tố |
|---:|---:|---|
| 0 | 5 | a |
| 1 | 3 | ana |
| 2 | 1 | anana |
| 3 | 0 | banana |
| 4 | 4 | na |
| 5 | 2 | nana |

Do đó:

~~~text
Text: banana
Suffix array: [5, 3, 1, 0, 4, 2]
~~~

**SA[r] là chỉ số bắt đầu của hậu tố thứ r theo từ điển.** Nó không phải ký tự hay độ dài hậu tố. Mảng nghịch đảo inverse[SA[r]]=r mới biểu diễn thứ hạng của hậu tố theo chỉ số bắt đầu.

Suffix array có ích cho việc tìm nhiều mẫu trong cùng văn bản, mảng LCP, tìm chuỗi con lặp dài nhất, đếm chuỗi con phân biệt, so các đoạn và xây những chỉ mục chuỗi khác.

Bài này trình bày **prefix doubling (nhân đôi tiền tố)** kết hợp **stable counting sort hai khóa** để dựng SA trong **O(n log n)**, chứ không sắp từng hậu tố bằng so sánh ký tự từ đầu. Phần Java 17 dùng Unicode code point làm đơn vị ký hiệu và giới thiệu truy vấn tìm mẫu cùng LCP/Kasai.

## 2. Quy tắc so từ điển và hậu tố ngắn

Khi so hai dãy A, B:
1. So từng ký hiệu từ trái sang phải.
2. Ký hiệu nhỏ hơn tại vị trí đầu tiên khác nhau quyết định thứ tự.
3. Nếu dãy ngắn hơn là tiền tố của dãy dài hơn, **dãy ngắn hơn đứng trước**.

Vì vậy:

~~~text
"a" < "ana" < "anana"
"na" < "nana"
"banana" < "na"
~~~

Quy ước của bài: SA chứa **n hậu tố không rỗng**, ứng với các vị trí 0..n−1. **Không đưa hậu tố rỗng tại n vào SA.** Một số tài liệu dùng sentinel và thêm hậu tố rỗng nên kết quả có thể khác một phần tử.

Các trường hợp nhỏ:
- T="" có n=0 nên SA=[].
- T="a" có SA=[0].
- T="aaaa" có SA=[3,2,1,0], lần lượt là "a","aa","aaa","aaaa".

### Ký hiệu canh gác khi hết chuỗi

Trong nhân đôi, khi so nửa thứ hai vượt khỏi vị trí cuối, ta dùng **rank canh gác −1**, nhỏ hơn mọi rank hợp lệ 0,1,2,...

Ví dụ cặp (0,−1) đại diện đoạn "a" ngắn hơn đoạn "an" có cặp (0,2), nên được sắp trước.

**Sai lầm nghiêm trọng:** dùng rank 0 cho nửa không tồn tại, vì 0 cũng là rank thật. Khi đó hậu tố ngắn có thể bị xem như có thêm một ký hiệu thật và thứ tự trở nên sai.

## 3. Vì sao không sort trực tiếp từng hậu tố?

Một cách thử là tạo mọi T.substring(i) và sort chúng:
- Có n hậu tố, tổng độ dài là n(n+1)/2, có thể chiếm O(n²) bộ nhớ nếu sao chép.
- Hai hậu tố có chung tiền tố dài có thể cần O(n) bước so sánh.
- Sort n mục bằng comparator có O(n log n) phép so, cho cận xấu O(n² log n) nếu mỗi phép so lại đi từ đầu hậu tố.

Một cải tiến là sort các **vị trí** theo cặp rank của tiền tố đã biết. Nếu dùng Arrays.sort với comparator so hai rank mỗi vòng, ta thường có O(n log² n): O(log n) vòng, mỗi vòng sort O(n log n). Để có **O(n log n)**, thuật toán ở bài dùng **radix sort ổn định hai khóa**, O(n) mỗi vòng.

## 4. Phương pháp nhân đôi

Giả sử đã biết thứ tự của tất cả đoạn dài tối đa k ký hiệu bắt đầu ở mỗi vị trí i. Gọi rank_k[i] là thứ hạng **nhóm tương đương** của đoạn ấy:
- Hai đoạn giống nhau trong phạm vi k ký hiệu nhận cùng rank.
- Nếu đoạn A nhỏ hơn đoạn B theo từ điển, rank(A) nhỏ hơn rank(B).
- Các rank được nén vào 0..classes−1.

Để so đoạn dài tối đa 2k ở i, chia làm hai nửa:

~~~text
T[i ... i+2k)
  nửa đầu k ký hiệu      nửa sau k ký hiệu
  T[i ... i+k)           T[i+k ... i+2k)
      rank_k[i]              rank_k[i+k]
~~~

Khóa mới là:

\[
\boxed{(rank_k[i],rank_k[i+k])}
\]

với rank_k[i+k]=**−1** khi i+k≥n.

So từ điển trên cặp này tương đương so hai đoạn 2k: nửa đầu quyết định trước, nếu bằng mới xét nửa sau. Sau khi sắp, ta **nén rank mới**:
- Cặp đầu có rank 0.
- Cặp bằng cặp trước giữ cùng rank.
- Cặp khác thì rank tăng một.

Lặp k=1,2,4,8,... cho đến khi đủ dài hoặc **classes==n**. Nếu mọi vị trí có rank khác nhau, thứ tự các hậu tố đã được quyết định hoàn toàn và có thể dừng sớm.

### Bước 1 trên "banana"

Thứ tự a<b<n, do đó a=0, b=1, n=2:

~~~text
Position: 0 1 2 3 4 5
Text:     b a n a n a
rank_1:   1 0 2 0 2 0
~~~

Ở k=1, các cặp rank của ký hiệu đầu và ký hiệu tiếp theo:

| i | Hậu tố | Cặp khóa |
|---:|---|---|
| 0 | banana | (1,0) |
| 1 | anana | (0,2) |
| 2 | nana | (2,0) |
| 3 | ana | (0,2) |
| 4 | na | (2,0) |
| 5 | a | (0,−1) |

Thứ tự nhóm:
- (0,−1): vị trí 5, rank 0.
- (0,2): vị trí 1 và 3, rank 1.
- (1,0): vị trí 0, rank 2.
- (2,0): vị trí 2 và 4, rank 3.

Rank mới theo vị trí gốc:

~~~text
rank_2: [2, 1, 3, 1, 3, 0]
~~~

Hai hậu tố "anana" và "ana" còn cùng nhóm do hai ký hiệu đầu giống nhau; tương tự "nana" và "na".

### Bước 2 trên "banana"

Ở k=2, khóa (rank_2[i],rank_2[i+2]):

| i | Cặp khóa |
|---:|---|
| 0 | (2,3) |
| 1 | (1,1) |
| 2 | (3,3) |
| 3 | (1,0) |
| 4 | (3,−1) |
| 5 | (0,−1) |

Sắp cặp:

~~~text
(0,-1) -> 5
(1, 0) -> 3
(1, 1) -> 1
(2, 3) -> 0
(3,-1) -> 4
(3, 3) -> 2

SA = [5, 3, 1, 0, 4, 2]
~~~

Mọi cặp đều khác nhau, tức số lớp đạt n=6. Không cần thực hiện bước k=4.

**Lưu ý:** nhân đôi không giống sắp cyclic shifts. Khi i+k≥n, dùng rank −1, **không dùng modulo n** để quay về đầu text. Nếu dùng modulo mà không có mô hình sentinel thích hợp, kết quả là thứ tự phép quay vòng, không phải thứ tự hậu tố.

## 5. Sắp cặp rank trong O(n) mỗi vòng

Ở mỗi bước, khóa của vị trí i là cặp:
- first=rank[i].
- second=rank[i+k] nếu còn trong text; nếu không thì −1.

Dùng **radix sort hai lượt**:
1. Stable counting sort theo **second**.
2. Stable counting sort theo **first**.

Lượt thứ hai giữ nguyên thứ tự second của những mục có first bằng nhau. Do đó kết quả là sắp từ điển đúng theo cặp (first,second).

**Stable** nghĩa là các phần tử có khóa bằng nhau giữ thứ tự tương đối đã có; nếu sort không ổn định, hai lượt không còn bảo đảm thứ tự cặp.

### Chuyển rank âm thành khóa bucket không âm

Mảng đếm cần chỉ số không âm. Đổi:

\[
key=\begin{cases}
0 & \text{nếu vị trí ngoài biên, rank=-1},\\
rank+1 & \text{nếu vị trí hợp lệ}.
\end{cases}
\]

Rank hợp lệ thuộc 0..classes−1, nên key thuộc 0..classes; mảng count chỉ cần **classes+1** ô.

Một stable counting sort:
- Đếm count[key] cho từng vị trí.
- Tính prefix sum để biến count thành chỉ số bắt đầu bucket.
- Duyệt input từ **trái sang phải**, ghi output[count[key]++] = vị trí.

Vì classes≤n, thời gian mỗi lượt O(n+classes)=O(n); hai lượt cùng nén rank mới vẫn O(n).

### Nén alphabet ban đầu

Với Unicode code point, mã có miền lớn và thưa. Có thể sao chép mảng ký hiệu, sort tăng, loại trùng thành mảng unique, rồi binary search rank của mỗi ký hiệu trong unique. Chi phí ban đầu O(n log n), không ảnh hưởng cận tổng.

Không nên cấp phát bảng tần suất kích thước theo toàn Unicode khi chỉ có n ký hiệu trong text.

## 6. Chứng minh tính đúng

**Bất biến:** Sau khi xử lý độ dài k, rank[i] biểu diễn thứ tự của đoạn dài tối đa k bắt đầu tại i. Các đoạn giống nhau có rank bằng nhau, các đoạn khác nhau có rank đúng thứ tự từ điển.

**Cơ sở k=1:** sort từng mã ký hiệu và nén; bất biến đúng.

**Bước quy nạp:** giả sử rank_k đúng. Đoạn 2k là phép nối hai đoạn k; nửa sau vắng mặt dùng canh gác nhỏ nhất. So cặp rank của hai nửa tương đương so từ điển các đoạn đã ghép. Hai stable counting sort sắp cặp đúng và nén rank bảo toàn đúng các nhóm. Vậy rank_2k đúng.

**Kết thúc:** khi độ dài đã xét bao phủ tất cả hậu tố, thứ tự rank đúng là thứ tự suffix. Nếu classes==n trước đó, các vị trí đã ở các nhóm khác nhau, nên thứ tự đầy đủ đã xác định. Độ dài k nhân hai mỗi vòng, do đó có O(log n) vòng.

**Độ phức tạp dựng SA:** nén alphabet O(n log n); mỗi vòng doubling O(n); tổng **O(n log n)** thời gian và **O(n)** bộ nhớ cho các mảng rank/SA/buffer/count. Với n=0,1 trả kết quả trực tiếp.

## 7. Mảng LCP và Kasai

**LCP (Longest Common Prefix)** lưu độ dài tiền tố chung của hai hậu tố kề nhau trong **thứ tự SA**. Quy ước:

\[
LCP[0]=0,\qquad
LCP[r]=lcp(T[SA[r-1]..n),T[SA[r]..n)),\ r\ge1.
\]

Với "banana":

~~~text
SA:  [5, 3, 1, 0, 4, 2]
LCP: [0, 1, 3, 0, 0, 2]
~~~

"a"/"ana" chung 1, "ana"/"anana" chung 3, "na"/"nana" chung 2. **LCP không đo hai hậu tố bắt đầu ở vị trí text r và r+1**.

### Kasai O(n)

Tạo mảng inverse[SA[r]]=r. Duyệt start từ 0 đến n−1. Nếu inverse[start]==0, đặt common=0. Ngược lại, so hậu tố start với hậu tố đứng ngay trước nó theo SA, bắt đầu từ chiều dài common có thể tái sử dụng. Sau khi ghi LCP[inverse[start]], giảm common đi 1 nếu nó dương.

Tính chất: nếu hai hậu tố có chung h ký hiệu đầu, khi bỏ ký hiệu đầu ta còn ít nhất h−1 ký hiệu chung. Nhờ tái sử dụng h, tổng số lần tăng/giảm common là O(n), nên Kasai O(n) thời gian, O(n) bộ nhớ.

### Ứng dụng 1: chuỗi con lặp dài nhất

Một chuỗi con xuất hiện ít nhất hai lần là tiền tố chung của hai hậu tố. Các hậu tố có cùng tiền tố tạo thành một đoạn liên tiếp trong SA; do đó:

\[
\text{độ dài lặp lớn nhất}=\max_r LCP[r].
\]

Với "banana", max LCP=3, chuỗi con lặp dài nhất **"ana"** ở các vị trí 1 và 3. Với "aaaa", SA=[3,2,1,0], LCP=[0,1,2,3], chuỗi con lặp dài nhất là **"aaa"**. Các lần lặp **được phép chồng lấn**; nếu đề cấm chồng lấn phải thêm điều kiện khác.

### Ứng dụng 2: đếm chuỗi con phân biệt

Tổng số chuỗi con không rỗng tính theo vị trí là n(n+1)/2. LCP[r] đếm số tiền tố của hậu tố thứ r đã xuất hiện trong hậu tố trước, nên:

\[
\boxed{\text{số chuỗi con phân biệt}=
\frac{n(n+1)}2-\sum_r LCP[r]}.
\]

"banana" có 21−6=**15** chuỗi con phân biệt. "aaaa" có 10−6=**4**.

## 8. Tìm mẫu bằng hai binary search trên SA

Các hậu tố có chung một tiền tố P nằm trong **một khoảng liên tiếp** của SA.

Ví dụ P="ana" trong "banana":
- Suffix "a" đứng trước P.
- Suffix "ana" và "anana" đều bắt đầu bằng P.
- Suffix "banana" đứng sau P.

Vùng match là SA[1..3)=[3,1] theo thứ tự hậu tố. Nếu muốn vị trí tăng dần trong text, sắp thành **[1,3]**.

Phép so compareSuffixWithPattern:
- Nếu có ký hiệu đầu tiên khác nhau, trả âm/dương theo thứ tự.
- Nếu suffix hết trước khi khớp hết P, trả âm.
- Nếu **toàn bộ P đã khớp**, trả 0 dù suffix còn dài hơn.

Hai binary search:
- **Lower bound:** phần tử đầu tiên với compare≥0.
- **Upper bound:** phần tử đầu tiên với compare>0.

Tất cả SA[lower..upper) đều là vị trí xuất hiện của P.

**Mẫu rỗng:** bài này quy định khớp mọi ranh giới 0..n, có n+1 kết quả. Vì SA chỉ chứa n hậu tố không rỗng, mã trả mẫu rỗng riêng, gồm cả vị trí n.

**Thời gian truy vấn:** với P dài m, mỗi phép so tối đa O(m); tìm hai cận O(m log(n+1)). Nếu có k match và muốn sắp theo vị trí text, thêm O(k log(k+1)). Không được tuyên bố truy vấn binary search cơ bản tự đạt O(m+log n) khi vẫn so lại tiền tố từ đầu mỗi lần.

## 9. Unicode code point so với UTF-16

Trong Java String, length() trả số **UTF-16 code unit**. Một emoji ngoài BMP thường dùng hai code unit nhưng một code point.

Với "A😀B😀":
- n=4 code point.
- Java String.length()=6.
- Emoji có code-point start [1,3].
- Cùng vị trí theo UTF-16 start [1,4].

Suffix array theo code point:

~~~text
SA:  [0, 2, 3, 1]
LCP: [0, 0, 0, 1]
~~~

Code tạo map từ ranh giới code point sang UTF-16 offset:

~~~text
cpToUtf16 = [0, 1, 3, 4, 6]
~~~

Vì vậy chuyển [1,3] code-point starts sang UTF-16 là [1,4]. Không nhân các chỉ số với hai hoặc bốn.

**Thứ tự code point có thể khác String.compareTo.** Ví dụ U+E000 nhỏ hơn 😀 U+1F600 về code point; nhưng UTF-16 high surrogate của 😀 có mã nhỏ hơn U+E000, nên so String trực tiếp có thể cho thứ tự đảo. Vì vậy code xây SA, truy vấn và oracle đều so **int code point**.

Java String có thể chứa surrogate đứng lẻ; code của bài từ chối dạng ấy để không coi nó là một Unicode scalar value hợp lệ. Nếu bài yêu cầu so **grapheme cluster** (ký tự hiển thị có thể gồm nhiều code point), phải phân đoạn thành token grapheme trước khi xây SA. Nếu cần so sau **NFC/NFD**, hãy chuẩn hóa cả text và pattern trước, đồng thời nhớ offset sau chuẩn hóa không tự là offset text gốc.

## 10. Java 17 hoàn chỉnh

Lưu file **SuffixArrayDoublingDemo.java**. Code dùng:
- Các mảng số nguyên code point.
- Nén alphabet bằng sort + binary search.
- Prefix doubling và hai stable counting sort mỗi vòng.
- Kasai dựng LCP.
- Hai cận binary search tìm mọi pattern, trả vị trí text tăng dần.
- Chuyển kết quả code point sang offset UTF-16.
- Chuỗi con lặp dài nhất và số chuỗi con phân biệt.

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class SuffixArrayDoublingDemo {
    private SuffixArrayDoublingDemo() {
    }

    private static void requireWellFormed(String s) {
        Objects.requireNonNull(s, "string");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (Character.isHighSurrogate(c)) {
                if (i + 1 >= s.length()
                        || !Character.isLowSurrogate(s.charAt(i + 1))) {
                    throw new IllegalArgumentException(
                            "Unpaired high surrogate");
                }
                i++;
            } else if (Character.isLowSurrogate(c)) {
                throw new IllegalArgumentException(
                        "Unpaired low surrogate");
            }
        }
    }

    // key=0 cho rank ngoài chuỗi; key=rank+1 nếu hợp lệ.
    private static int key(int i, int offset, int[] rank) {
        return i < rank.length - offset
                ? rank[i + offset] + 1 : 0;
    }

    // Counting sort ổn định một khóa.
    private static void stableCountingSort(
            int[] input, int[] output, int[] rank,
            int offset, int classes) {
        int[] count = new int[classes + 1];

        for (int index : input) {
            count[key(index, offset, rank)]++;
        }

        int pos = 0;
        for (int k = 0; k < count.length; k++) {
            int frequency = count[k];
            count[k] = pos;
            pos += frequency;
        }

        for (int index : input) {
            int k = key(index, offset, rank);
            output[count[k]++] = index;
        }
    }

    private static int[] buildSuffixArray(int[] symbols) {
        int n = symbols.length;
        int[] sa = new int[n];

        for (int i = 0; i < n; i++) {
            sa[i] = i;
        }
        if (n <= 1) {
            return sa;
        }

        int[] alphabet = symbols.clone();
        Arrays.sort(alphabet);
        int[] unique = new int[n];
        int classes = 0;

        for (int x : alphabet) {
            if (classes == 0 || x != unique[classes - 1]) {
                unique[classes++] = x;
            }
        }

        int[] rank = new int[n];
        for (int i = 0; i < n; i++) {
            rank[i] = Arrays.binarySearch(
                    unique, 0, classes, symbols[i]);
        }

        int[] nextRank = new int[n];
        int[] bySecond = new int[n];
        int[] sortedPair = new int[n];

        for (long width = 1; width < n; width *= 2) {
            int step = (int) width;

            stableCountingSort(
                    sa, bySecond, rank, step, classes);
            stableCountingSort(
                    bySecond, sortedPair, rank, 0, classes);

            nextRank[sortedPair[0]] = 0;
            int newClasses = 1;

            for (int j = 1; j < n; j++) {
                int a = sortedPair[j - 1];
                int b = sortedPair[j];
                int a2 = a < n - step
                        ? rank[a + step] : -1;
                int b2 = b < n - step
                        ? rank[b + step] : -1;

                if (rank[a] != rank[b] || a2 != b2) {
                    newClasses++;
                }
                nextRank[b] = newClasses - 1;
            }

            System.arraycopy(sortedPair, 0, sa, 0, n);
            int[] old = rank;
            rank = nextRank;
            nextRank = old;
            classes = newClasses;

            if (classes == n) {
                break;
            }
        }
        return sa;
    }

    // Kasai: lcp[r] giữa sa[r-1] và sa[r].
    private static int[] buildLcp(int[] symbols, int[] sa) {
        int n = symbols.length;
        int[] lcp = new int[n];
        int[] inverse = new int[n];

        for (int r = 0; r < n; r++) {
            inverse[sa[r]] = r;
        }

        int common = 0;
        for (int i = 0; i < n; i++) {
            int r = inverse[i];
            if (r == 0) {
                common = 0;
                continue;
            }

            int j = sa[r - 1];
            while (i + common < n
                    && j + common < n
                    && symbols[i + common]
                            == symbols[j + common]) {
                common++;
            }

            lcp[r] = common;
            if (common > 0) {
                common--;
            }
        }
        return lcp;
    }

    private static int[] mapCpToUtf16(String text) {
        int count = text.codePointCount(0, text.length());
        int[] result = new int[count + 1];
        int utf16 = 0;

        for (int i = 0; i < count; i++) {
            result[i] = utf16;
            utf16 += Character.charCount(
                    text.codePointAt(utf16));
        }
        result[count] = utf16;
        return result;
    }

    public static final class Index {
        private final int[] symbols;
        private final int[] sa;
        private final int[] lcp;
        private final int[] cpToUtf16;

        public Index(String text) {
            requireWellFormed(text);
            symbols = text.codePoints().toArray();
            sa = buildSuffixArray(symbols);
            lcp = buildLcp(symbols, sa);
            cpToUtf16 = mapCpToUtf16(text);
        }

        public int[] suffixArray() {
            return sa.clone();
        }

        public int[] lcpArray() {
            return lcp.clone();
        }

        public int length() {
            return symbols.length;
        }

        // Bằng 0 khi pattern là tiền tố của suffix.
        private int compare(int start, int[] pattern) {
            int size = Math.min(
                    symbols.length - start, pattern.length);

            for (int i = 0; i < size; i++) {
                int a = symbols[start + i];
                int b = pattern[i];

                if (a != b) {
                    return Integer.compare(a, b);
                }
            }
            return size < pattern.length ? -1 : 0;
        }

        private int bound(int[] p, boolean upper) {
            int low = 0;
            int high = sa.length;

            while (low < high) {
                int mid = low + (high - low) / 2;
                int cmp = compare(sa[mid], p);

                if (cmp < 0 || (upper && cmp == 0)) {
                    low = mid + 1;
                } else {
                    high = mid;
                }
            }
            return low;
        }

        // Mọi code-point start, sắp theo vị trí text.
        public int[] search(String pattern) {
            requireWellFormed(pattern);
            int[] p = pattern.codePoints().toArray();
            int n = symbols.length;

            if (p.length == 0) {
                int[] positions = new int[n + 1];
                for (int i = 0; i <= n; i++) {
                    positions[i] = i;
                }
                return positions;
            }

            int left = bound(p, false);
            int right = bound(p, true);
            int[] positions = Arrays.copyOfRange(
                    sa, left, right);
            Arrays.sort(positions);
            return positions;
        }

        public int[] searchUtf16(String pattern) {
            int[] cp = search(pattern);
            int[] answer = new int[cp.length];

            for (int i = 0; i < cp.length; i++) {
                answer[i] = cpToUtf16[cp[i]];
            }
            return answer;
        }

        public String longestRepeated() {
            int bestLength = 0;
            int bestStart = -1;

            for (int i = 1; i < lcp.length; i++) {
                if (lcp[i] > bestLength) {
                    bestLength = lcp[i];
                    bestStart = sa[i];
                }
            }

            return bestStart == -1 ? ""
                    : new String(symbols, bestStart, bestLength);
        }

        public long distinctSubstrings() {
            long n = symbols.length;
            long total = n * (n + 1) / 2;

            for (int x : lcp) {
                total -= x;
            }
            return total;
        }
    }

    public static void main(String[] args) {
        Index banana = new Index("banana");
        System.out.println("Banana SA: "
                + Arrays.toString(banana.suffixArray()));
        System.out.println("Banana LCP: "
                + Arrays.toString(banana.lcpArray()));
        System.out.println("Banana distinct: "
                + banana.distinctSubstrings());
        System.out.println("Banana longest: "
                + banana.longestRepeated());
        System.out.println("Banana ana: "
                + Arrays.toString(banana.search("ana")));
        System.out.println("Banana na: "
                + Arrays.toString(banana.search("na")));
        System.out.println("Banana xyz: "
                + Arrays.toString(banana.search("xyz")));
        System.out.println("Banana empty pattern: "
                + Arrays.toString(banana.search("")));

        Index repeat = new Index("aaaa");
        System.out.println("Aaaa SA: "
                + Arrays.toString(repeat.suffixArray()));
        System.out.println("Aaaa LCP: "
                + Arrays.toString(repeat.lcpArray()));
        System.out.println("Aaaa longest: "
                + repeat.longestRepeated());
        System.out.println("Aaaa aa: "
                + Arrays.toString(repeat.search("aa")));

        String emoji = new String(Character.toChars(0x1F600));
        Index unicode = new Index("A" + emoji + "B" + emoji);
        System.out.println("Unicode CP count: "
                + unicode.length());
        System.out.println("Unicode SA: "
                + Arrays.toString(unicode.suffixArray()));
        System.out.println("Unicode LCP: "
                + Arrays.toString(unicode.lcpArray()));
        System.out.println("Unicode emoji CP: "
                + Arrays.toString(unicode.search(emoji)));
        System.out.println("Unicode emoji UTF16: "
                + Arrays.toString(unicode.searchUtf16(emoji)));
        System.out.println("Unicode distinct: "
                + unicode.distinctSubstrings());

        Index empty = new Index("");
        System.out.println("Empty SA: "
                + Arrays.toString(empty.suffixArray()));
        System.out.println("Empty/empty: "
                + Arrays.toString(empty.search("")));
        System.out.println("Empty/a: "
                + Arrays.toString(empty.search("a")));

        Index one = new Index("a");
        System.out.println("Single SA: "
                + Arrays.toString(one.suffixArray()));
        System.out.println("Single LCP: "
                + Arrays.toString(one.lcpArray()));
        System.out.println("Single/aa: "
                + Arrays.toString(one.search("aa")));

        Index order = new Index("\uE000" + emoji);
        System.out.println("Code-point order: "
                + Arrays.toString(order.suffixArray()));

        try {
            new Index(String.valueOf('\uD800'));
            System.out.println("Invalid surrogate: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid surrogate: true");
        }
    }
}
~~~

### 10.1. Biên dịch và chạy

Dùng **JDK 17 trở lên**, lưu tệp đúng tên public class:

~~~bash
javac -encoding UTF-8 SuffixArrayDoublingDemo.java
java SuffixArrayDoublingDemo
~~~

**Kết quả stdout:**

~~~text
Banana SA: [5, 3, 1, 0, 4, 2]
Banana LCP: [0, 1, 3, 0, 0, 2]
Banana distinct: 15
Banana longest: ana
Banana ana: [1, 3]
Banana na: [2, 4]
Banana xyz: []
Banana empty pattern: [0, 1, 2, 3, 4, 5, 6]
Aaaa SA: [3, 2, 1, 0]
Aaaa LCP: [0, 1, 2, 3]
Aaaa longest: aaa
Aaaa aa: [0, 1, 2]
Unicode CP count: 4
Unicode SA: [0, 2, 3, 1]
Unicode LCP: [0, 0, 0, 1]
Unicode emoji CP: [1, 3]
Unicode emoji UTF16: [1, 4]
Unicode distinct: 9
Empty SA: []
Empty/empty: [0]
Empty/a: []
Single SA: [0]
Single LCP: [0]
Single/aa: []
Code-point order: [0, 1]
Invalid surrogate: true
~~~

### 10.2. Giải thích code

**requireWellFormed:** kiểm tra cặp surrogate theo chuẩn UTF-16, từ chối surrogate đứng lẻ. Điều này giữ ý nghĩa code-point index không bị pha dữ liệu Unicode lỗi.

**buildSuffixArray:** n≤1 trả ngay. Khi n≥2, nén mã Unicode thành rank, mỗi vòng nhân đôi dùng stableCountingSort hai lần theo second trước và first sau; nén rank mới và dừng nếu đủ n lớp.

**key:** trả 0 cho nửa sau vượt cuối; rank hợp lệ r trả r+1. Điều kiện i < length−offset còn tránh phép cộng index vượt int trước khi kiểm tra biên.

**buildLcp:** Kasai sử dụng inverse SA và biến common tái sử dụng, thời gian O(n).

**compare/bound:** so pattern như tiền tố theo code point; tìm hai cận của khối hậu tố có cùng tiền tố. Không dùng String.compareTo nên quan hệ thứ tự nhất quán với lúc xây SA.

**search:** mẫu rỗng trả n+1 ranh giới; mẫu không rỗng lấy đoạn SA rồi sắp theo vị trí text. Mọi lần chồng lấn được giữ.

**searchUtf16:** chuyển kết quả code-point index qua map ranh giới UTF-16; đây là kiểu offset phù hợp với String.substring trong Java.

**longestRepeated:** chọn một cặp hậu tố kề nhau có LCP lớn nhất và trả chuỗi con tương ứng. Nếu không có đoạn lặp không rỗng thì trả chuỗi rỗng.

**distinctSubstrings:** dùng n kiểu long ngay từ đầu để tính n(n+1)/2−sumLCP; không nhân hai int rồi mới ép long.

Các getter trả bản sao mảng để người gọi không sửa cấu trúc SA/LCP bên trong.

## 11. Độ phức tạp và chọn thuật toán

Với n code point:
- Nén alphabet O(n log n).
- Một vòng doubling O(n), có O(log n) vòng.
- **Dựng SA O(n log n), bộ nhớ O(n)**.
- Kasai LCP O(n), bộ nhớ O(n).
- Một truy vấn pattern dài m, có k vị trí: **O(m log(n+1)+k log(k+1))** nếu yêu cầu trả vị trí text tăng dần.
- Tìm max LCP/đếm chuỗi con phân biệt O(n) sau tiền xử lý.

Nếu chỉ cần tìm **một mẫu duy nhất**, KMP có thể chạy O(n+m) mà không cần tiền xử lý SA. SA có ích khi văn bản gần như cố định và phải tìm nhiều mẫu hoặc hỏi các bài toán lặp/tiền tố.

Với n rất lớn, nhiều mảng int và việc chuyển String sang code point tốn bộ nhớ; phải đánh giá giới hạn thực tế của JVM. Một số thuật toán dựng SA tuyến tính tồn tại, nhưng prefix doubling thường dễ giảng giải, chứng minh và triển khai hơn.

## 12. Kiểm thử độc lập

Để kiểm chứng với n nhỏ:
1. Tạo dãy 0..n−1 và sort theo comparator **trực tiếp so code point** của hai hậu tố; dãy ngắn hơn đứng trước khi là tiền tố.
2. So mảng đó với SA xây bằng nhân đôi.
3. Với từng cặp hậu tố kề SA, đếm LCP trực tiếp và so với Kasai.
4. Với từng mẫu, duyệt mọi vị trí text bằng naive matching, so toàn bộ danh sách với kết quả binary search trên SA.
5. Kiểm tra SA là hoán vị đúng; mọi LCP không vượt độ dài hậu tố ngắn hơn.

Những dữ liệu cần thử:
- Chuỗi rỗng, một ký hiệu, các ký hiệu giống nhau ("aaaa"), mẫu rỗng.
- Chuỗi tuần hoàn như "ababab" và mẫu chồng lấn.
- Các suffix có chung tiền tố dài, ví dụ "banana".
- Mẫu dài hơn text và mẫu hoàn toàn không xuất hiện.
- Dãy gồm ký hiệu Unicode BMP, emoji ngoài BMP, dấu kết hợp và U+E000.
- Nhiều random text ngắn từ alphabet nhỏ để tăng xác suất hậu tố trùng tiền tố.

**Oracle phải độc lập:** không dùng chính routine nhân đôi để làm oracle. Đặc biệt không dùng String.compareTo của Java như thể nó so code point, vì Unicode ngoài BMP có thể đảo thứ tự.

### Kiểm thử theo bất biến

Trong mỗi vòng nhân đôi:
- SA chứa đủ các vị trí, không lặp.
- Rank hợp lệ trong 0..classes−1.
- Hai cặp rank bằng nhau được nén chung.
- Cặp mới khác nhau làm rank tăng.
- Số lớp không giảm và không vượt n.

Trong LCP:
- LCP[0]=0.
- LCP[r] bằng số ký hiệu chung thực sự giữa hai hậu tố SA[r−1] và SA[r].
- LCP[r]≤min(n−SA[r−1],n−SA[r]).

Trong truy vấn:
- Mỗi vị trí trả về là một match đúng.
- Không bỏ match hợp lệ, kể cả overlap.
- Kết quả đã theo thứ tự vị trí text.
- Mẫu rỗng trả n+1 ranh giới.

## 13. Sai lầm phổ biến

1. Nhầm SA[r] với thứ hạng của hậu tố bắt đầu tại r.
2. Vô tình đưa hậu tố rỗng n vào SA đang quy định chỉ n hậu tố.
3. Dùng 0 làm sentinel, trùng rank hợp lệ.
4. Dùng modulo cho i+k vượt biên, biến hậu tố thành cyclic shifts.
5. Không nén rank sau mỗi vòng.
6. Hai cặp giống nhau nhận rank khác hoặc hai cặp khác nhận rank giống.
7. Sort hai khóa sai thứ tự hoặc dùng counting sort không ổn định.
8. Coi comparator sort từng vòng vẫn là O(n log n) cho cả thuật toán.
9. So từng ký tự toàn hậu tố trong comparator và tạo nhiều substring dư thừa.
10. Dùng int width nhân hai mà không xét overflow.
11. Không xử lý n=0, n=1 và truy cập sortedPair[0] khi rỗng.
12. Không xây inverse SA trong Kasai, so nhầm hậu tố.
13. Không giảm biến common khi Kasai dịch vị trí, mất cận O(n).
14. Nhầm LCP theo thứ tự text với LCP theo thứ tự SA.
15. Đếm distinct substrings mà không trừ tổng LCP.
16. Tìm chuỗi con lặp dài nhất chỉ bằng độ dài hậu tố thay vì max LCP.
17. Khi tìm pattern, so hậu tố với toàn bộ mẫu như hai chuỗi phải bằng chiều dài.
18. Chỉ tìm một cận binary search, mất match trùng.
19. Trả đoạn SA như vị trí text tăng dần dù SA theo thứ tự từ điển.
20. Không xử lý mẫu rỗng, chỉ trả n vị trí thay vì n+1.
21. Dùng String.compareTo để tìm trên SA code point, phá tính đơn điệu.
22. Dùng code-point index như UTF-16 offset của Java String.
23. Coi Unicode code point là grapheme cluster.
24. Chuẩn hóa văn bản xong nhưng vẫn dùng offset như text gốc.
25. Bỏ kiểm tra surrogate đứng lẻ dù tuyên bố nhận Unicode scalar hợp lệ.
26. Chỉ kiểm thử ASCII không lặp, bỏ qua emoji, chuỗi tuần hoàn và chồng lấn.
27. Đánh giá truy vấn mà không cộng chi phí xây index khi chỉ có một mẫu.

## 14. Bài tập tự kiểm tra

**Câu 1.** SA của "banana"?

**Đáp án:** [5,3,1,0,4,2].

**Câu 2.** Vì sao hậu tố "a" đứng trước "ana"?

**Đáp án:** "a" là tiền tố của "ana" và ngắn hơn.

**Câu 3.** Cặp rank của bước nhân đôi k?

**Đáp án:** (rank[i],rank[i+k]), dùng −1 nếu nửa sau vượt cuối.

**Câu 4.** Rank ban đầu của "banana" khi a<b<n?

**Đáp án:** [1,0,2,0,2,0].

**Câu 5.** Rank theo vị trí sau k=1?

**Đáp án:** [2,1,3,1,3,0].

**Câu 6.** Vì sao radix sort cặp phải sort second trước first?

**Đáp án:** Lượt stable theo first giữ thứ tự second giữa những mục có first bằng nhau.

**Câu 7.** Vì sao cần key=rank+1?

**Đáp án:** Chuyển sentinel −1 thành 0 và rank thật thành bucket dương.

**Câu 8.** Độ phức tạp prefix doubling với counting sort?

**Đáp án:** O(n log n) thời gian, O(n) bộ nhớ.

**Câu 9.** LCP của "banana"?

**Đáp án:** [0,1,3,0,0,2].

**Câu 10.** Kasai xây LCP mất bao lâu?

**Đáp án:** O(n) do tái sử dụng chiều dài tiền tố chung.

**Câu 11.** Chuỗi lặp dài nhất của "banana"?

**Đáp án:** "ana", dài 3; có thể có overlap.

**Câu 12.** Số chuỗi con phân biệt của "banana"?

**Đáp án:** 15, bằng 21−6.

**Câu 13.** Tìm "ana" trong "banana" bằng SA cho ra gì?

**Đáp án:** Binary search khoảng chứa [3,1] theo SA, rồi sắp theo vị trí text thành [1,3].

**Câu 14.** Mẫu rỗng trong "banana"?

**Đáp án:** [0,1,2,3,4,5,6] theo quy ước mọi ranh giới.

**Câu 15.** Hai emoji trong "A😀B😀" bắt đầu ở đâu?

**Đáp án:** [1,3] code point hoặc [1,4] UTF-16.

**Câu 16.** Nếu chỉ có một pattern và không cần LCP, có bắt buộc dựng SA?

**Đáp án:** Không. KMP tìm trực tiếp trong O(n+m) và thường đơn giản hơn.

**Tóm tắt:** Prefix doubling dựng rank độ dài 2k từ cặp rank độ dài k; sentinel −1 biểu diễn nửa sau rỗng. Hai stable counting sort và nén rank cho **O(n log n)** xây SA. Sau đó **Kasai** dựng LCP O(n) và hai binary search trên SA tìm mọi hậu tố có tiền tố bằng mẫu. Phải thống nhất **đơn vị ký hiệu và hệ tọa độ chỉ số** trong toàn bộ quá trình.
