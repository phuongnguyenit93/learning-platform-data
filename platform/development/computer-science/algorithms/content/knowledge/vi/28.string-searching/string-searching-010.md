# Đếm lần xuất hiện có chồng lấn hoặc không chồng lấn

Khi tìm một **chuỗi mẫu** P (*pattern*) trong **văn bản** T (*text*), câu hỏi “P xuất hiện bao nhiêu lần?” chưa hoàn toàn rõ ràng nếu một lần khớp có thể sử dụng chung ký tự với lần khớp khác. Hai ngữ nghĩa thường gặp là **đếm có chồng lấn** (*overlapping occurrences*) và **đếm không chồng lấn** (*non-overlapping occurrences*). Hai kết quả có thể khác nhau dù T và P không thay đổi.

Ví dụ T=`"aaaaa"`, P=`"aaa"`: mẫu xuất hiện tại các vị trí bắt đầu **0, 1, 2**. Nếu **cho phép chồng lấn**, ta đếm **3** lần. Nếu **cấm chồng lấn**, các khoảng dài ba ký tự này giao nhau; tối đa chỉ chọn được **1** lần.

Ví dụ T=`"abababa"`, P=`"aba"`: có ba vị trí khớp **0, 2, 4**, nhưng có thể chọn hai đoạn rời nhau tại **0 và 4**. Vì vậy kết quả lần lượt là **3** và **2**.

Bài học làm rõ cách định nghĩa các khoảng khớp, hai quy tắc cập nhật vị trí tìm tiếp, vì sao chiến lược **tham lam chọn lần xuất hiện sớm nhất** là tối ưu khi cấm chồng lấn một mẫu cố định, phương pháp **KMP** với hai trạng thái sau khi khớp, việc xử lý văn bản dạng **stream**, vấn đề **Unicode/UTF-16**, cách phân biệt các bài toán đếm khác nhau và chương trình **Java 17+ hoàn chỉnh** với đầu ra đã đối chiếu.

## 1. Một lần xuất hiện được biểu diễn như thế nào?

Giả sử văn bản T dài n ký tự và mẫu P dài m ký tự, với **m>0**. Chỉ số bắt đầu i hợp lệ khi:

\[
0\le i\le n-m
\]

và đoạn T từ i tới i+m−1 bằng P.

Dùng quy ước **khoảng nửa mở**:

\[
\boxed{T[i,i+m)=P}.
\]

Một lần khớp tại vị trí i chiếm khoảng:

\[
\boxed{I_i=[i,i+m)}.
\]

Khoảng nửa mở chứa i nhưng **không chứa i+m**. Nhờ quy ước này, hai đoạn `[0,3)` và `[3,6)` **không** giao nhau, dù đoạn sau bắt đầu đúng nơi đoạn trước kết thúc.

Tập tất cả các vị trí bắt đầu khớp:

\[
O(T,P)=\{i\mid 0\le i\le n-m,\ T[i,i+m)=P\}.
\]

### Có chồng lấn

Mọi vị trí bắt đầu khác nhau đều được tính, kể cả nếu các khoảng giao nhau:

\[
\boxed{count_{\mathrm{overlap}}=|O(T,P)|}.
\]

Chẳng hạn:

~~~text
T   = a a a a a
idx = 0 1 2 3 4
P   = a a a

start 0: [a a a] . .
start 1: . [a a a] .
start 2: . . [a a a]

overlap starts = [0,1,2]
overlap count = 3
~~~

### Không chồng lấn

Chọn một tập con A của O sao cho mọi đôi lần khớp trong A không dùng chung vị trí ký tự. Với i<j, hai khoảng không chồng lấn khi:

\[
[i,i+m)\cap[j,j+m)=\varnothing
\iff \boxed{j\ge i+m}.
\]

Nếu đề hỏi **số lần không chồng lấn tối đa**, ta tìm:

\[
\boxed{count_{\mathrm{nonoverlap}}=
\max_{\substack{A\subseteq O(T,P)\\ I_i\cap I_j=\varnothing\ (i\ne j)}}|A|}.
\]

Đối với **một mẫu P có độ dài cố định**, việc chọn các lần khớp từ trái sang phải, nhận ngay lần sớm nhất không giao với đoạn đã chọn, đạt đúng số lượng tối đa ấy. Đây là ý nghĩa “không chồng lấn” của bài và chương trình Java.

**Không nhầm** câu hỏi “tối đa chọn được bao nhiêu đoạn?” với “có bao nhiêu cách chọn một tập đoạn rời nhau?”. Câu hỏi thứ hai là bài tổ hợp khác.

## 2. Các ví dụ làm rõ ngữ nghĩa

### Ví dụ A — "banana" và "ana"

~~~text
text:   b a n a n a
index:  0 1 2 3 4 5

match at 1: . [a n a] . .
match at 3: . . . [a n a]

overlapping positions:     [1,3] => 2
non-overlapping positions: [1]   => 1
~~~

Hai lần khớp tại `[1,4)` và `[3,6)` cùng dùng ký tự ở chỉ số 3 nên **chồng lấn**.

### Ví dụ B — "abababa" và "aba"

~~~text
index: 0 1 2 3 4 5 6
text:  a b a b a b a

match [0,3)  : a b a
match [2,5)  :     a b a
match [4,7)  :         a b a

tất cả: [0,2,4]
không chồng lấn: [0,4]
~~~

Đoạn [0,3) và [4,7) rời nhau. Đoạn [2,5) giao với cả hai, nên không thể chọn thêm.

### Ví dụ C — "aaaaaa" và "aa"

~~~text
text length = 6
pattern length = 2

all starts: [0,1,2,3,4] => 5
chosen:     [0,2,4]     => 3
~~~

Đây là trường hợp cả hai cận trên đều đạt:

\[
n-m+1=5,\qquad \lfloor n/m\rfloor=3.
\]

### Ví dụ D — các đoạn sát cạnh nhau

Với T=`"abcabc"` và P=`"abc"`, các khoảng là `[0,3)` và `[3,6)`. Chúng **không giao nhau**; cả hai chế độ đều đếm **2**.

Không được dùng điều kiện `nextStart > previousEnd`. Điều kiện đúng là **`nextStart >= previousEnd`**.

### Ví dụ E — mẫu dài một ký tự

Với T=`"aaaa"`, P=`"a"`, các vị trí [0,1,2,3] đều độc lập. Hai cách đếm đều là **4**. Nói chung khi m=1, **không thể có hai khớp ở các vị trí khác nhau dùng chung ký tự**.

## 3. Vòng tìm kiếm dùng String.indexOf: chỉ khác bước nhảy

Trong Java, `String.indexOf(pattern,fromIndex)` tìm vị trí xuất hiện đầu tiên của P bắt đầu **không trước** `fromIndex`. Nếu không thấy, trả về -1.

Sau khi tìm được một khớp bắt đầu tại **i**, phải cập nhật:

\[
\boxed{
nextFrom =
\begin{cases}
i+1,&\text{cho phép chồng lấn},\\
i+m,&\text{cấm chồng lấn}.
\end{cases}
}
\]

**Chú ý lấy i là vị trí vừa khớp thật sự**, không phải giá trị `fromIndex` trước khi gọi `indexOf`.

Đây là phương thức Java minh họa (chương trình độc lập đầy đủ ở phần 9):

~~~java
static int countWithIndexOf(
    String text, String pattern, boolean allowOverlap
) {
    if (pattern.isEmpty()) {
        throw new IllegalArgumentException(
            "pattern must not be empty"
        );
    }
    int count = 0;
    int from = 0;

    while (true) {
        int index = text.indexOf(pattern, from);
        if (index == -1) {
            break;
        }
        count++;

        from = index + (allowOverlap ? 1 : pattern.length());
    }
    return count;
}
~~~

Cách này rất dễ hiểu và phù hợp với nhiều bài thực hành. Nhưng nếu phải chứng minh cận thời gian **O(n+m)** trong mọi trường hợp, nên chọn một thuật toán có cận rõ ràng như **KMP** thay vì tự khẳng định chi phí của một lời gọi `String.indexOf` không phụ thuộc bản triển khai JVM.

### Tại sao m phải lớn hơn 0?

Nếu P rỗng, nó có thể được xem như khớp ở các **ranh giới** giữa ký tự, nhưng độ dài khớp bằng 0 nên quy tắc `i+m` không tiến con trỏ và có thể gây vòng lặp vô hạn. Bài này chọn hợp đồng **từ chối P rỗng**. Nếu đề khác quy định P rỗng xuất hiện n+1 lần ở n+1 ranh giới, cần xử lý riêng.

## 4. Tham lam không chồng lấn: chứng minh tối đa

Giả sử tất cả lần khớp của **cùng một mẫu P cố định** có chiều dài m. Ta liệt kê các vị trí khớp tăng dần:

\[
p_1<p_2<\cdots<p_k.
\]

Thuật toán tham lam:

1. Chọn vị trí khớp **sớm nhất** p1.
2. Đặt `nextAllowed=p1+m`.
3. Chọn vị trí nhỏ nhất tiếp theo có `start>=nextAllowed`.
4. Lặp cho tới khi hết vị trí.

Vì mọi lần khớp dài bằng nhau, chọn **vị trí bắt đầu sớm nhất** cũng chính là chọn **vị trí kết thúc sớm nhất** trong các khoảng hiện còn khả thi.

### Chứng minh bằng phép trao đổi

Gọi A là một tập vị trí khớp rời nhau có số lượng tối đa K, và q là vị trí khớp được chọn đầu tiên trong A. Vị trí khớp sớm nhất toàn bộ là p1 nên `p1<=q`.

Ta thay q bằng p1. Hai lần khớp đều dài m, nên:

\[
p_1+m\le q+m.
\]

Mọi khớp được chọn sau q trong A đều bắt đầu ít nhất ở q+m, do đó vẫn bắt đầu ít nhất ở p1+m; chúng **không giao** với đoạn mới tại p1. Số lượng K không đổi và vẫn là tập hợp lệ.

Vì thế **tồn tại một phương án tối ưu bắt đầu tại p1**. Sau khi chọn p1, phần còn lại chỉ được xét từ p1+m trở đi; áp dụng lập luận tương tự cho phần đuôi. Quy nạp cho thấy tham lam chọn lần khớp sớm nhất hợp lệ **tối đa hóa số lần không chồng lấn**.

### Khi nào không được áp dụng chứng minh này?

- Có **nhiều mẫu với độ dài khác nhau**, nên khớp bắt đầu sớm nhất có thể kết thúc rất muộn; khi đó bài chọn nhiều khoảng nhất thường ưu tiên **kết thúc sớm nhất**.
- Mỗi lần khớp mang trọng số/điểm khác nhau, muốn tối đa **tổng điểm**; bài chọn khoảng có trọng số cần quy hoạch động hoặc thuật toán phù hợp.
- Yêu cầu **đếm số tập hợp khớp rời nhau**, không phải số lượng lớn nhất.
- Có thêm giới hạn tài nguyên, thời điểm, khoảng cách tối thiểu giữa các khớp hoặc mỗi khớp được chọn ảnh hưởng trạng thái tương lai.
- Mẫu là regex có độ dài khớp biến đổi, nên không còn cùng m.

Với **một chuỗi mẫu cố định** được tìm chính xác, thuật toán tham lam vẫn là lựa chọn đúng và đơn giản nhất.

## 5. Cận trên và quan hệ giữa hai kết quả

Nếu m>0 và n là chiều dài văn bản:

\[
0\le count_{\mathrm{overlap}}
\le\max(0,n-m+1).
\]

Bởi vì không thể bắt đầu một khớp hợp lệ ở vị trí >n−m.

Với các khoảng không chồng lấn, tổng chiều dài các đoạn đã chọn bằng số khớp nhân m và không thể vượt n:

\[
0\le count_{\mathrm{nonoverlap}}
\le \left\lfloor\frac{n}{m}\right\rfloor.
\]

Vì các vị trí chọn không chồng lấn đều là **vị trí khớp thật sự** nên:

\[
\boxed{count_{\mathrm{nonoverlap}}\le count_{\mathrm{overlap}}}.
\]

Hai kết quả có thể bằng nhau khi:

- Không có khớp nào.
- Mẫu chỉ dài 1.
- Các vị trí xuất hiện vốn đã cách nhau ít nhất m.
- Mẫu không có khả năng tự chồng lấn (xem phần 8).

Hai kết quả không nhất thiết khác nhau chỉ vì P lặp ký tự. Điều quyết định vẫn là **các vị trí thực sự tồn tại trong T**.

## 6. KMP: tìm khớp trong O(n+m)

KMP (*Knuth–Morris–Pratt*) tiền xử lý mẫu P để không phải thử lại mọi vị trí bắt đầu trong T. Thuật toán lưu **prefix function** `pi[i]`:

\[
\pi[i] =
\text{độ dài tiền tố đúng dài nhất của }P[0..i]
\text{cũng là hậu tố của }P[0..i].
\]

“Tiền tố đúng” là tiền tố ngắn hơn toàn bộ đoạn đang xét, nên \(\pi[0]=0\).

Với mẫu `"ababaca"`:

~~~text
i       0 1 2 3 4 5 6
P[i]    a b a b a c a
pi[i]   0 0 1 2 3 0 1
~~~

Ở i=4, đoạn `"ababa"` có tiền tố và hậu tố `"aba"` dài 3, vì vậy pi[4]=3. Ở i=5 không có biên dương.

### Tính bảng pi

Giữ `j` là độ dài biên hiện tại. Với i từ 1 tới m−1:

~~~text
while j>0 and P[i] != P[j]:
    j = pi[j-1]

if P[i] == P[j]:
    j++

pi[i] = j
~~~

Mỗi lần mismatch, KMP dùng một **biên ngắn hơn** đã được xác định; không cần thử lại toàn bộ tiền tố. Phân tích amortized cho thấy tính pi mất **O(m)** thời gian và **O(m)** bộ nhớ.

### Quét văn bản

Giữ `j` là độ dài tiền tố P đang khớp với hậu tố phần T đã đọc. Với từng ký tự T[i]:

~~~text
while j>0 and T[i]!=P[j]:
    j=pi[j-1]

if T[i]==P[j]:
    j++

if j==m:
    record match start i-m+1
    update j according to overlap policy
~~~

Cả hai chế độ đều duyệt **từng ký tự T đúng một lần theo i tăng**, không cần điều khiển i nhảy lùi. Phần quan trọng nhất là cách **cập nhật j ngay sau khi vừa nhận một lần khớp đủ m ký tự**.

## 7. Một dòng khác biệt quyết định chồng lấn

Sau khi KMP nhận một khớp kết thúc ở i, vị trí bắt đầu là:

\[
start=i-m+1.
\]

Khi đó j=m. Để chuẩn bị đọc T[i+1]:

### Cho phép chồng lấn

\[
\boxed{j=\pi[m-1]}.
\]

Ta giữ độ dài **hậu tố dài nhất của mẫu vừa khớp cũng là tiền tố của mẫu**. Phần đã dùng ở khớp trước có thể hợp lệ làm phần mở đầu của một khớp **chồng lấn** mới.

### Không cho phép chồng lấn

\[
\boxed{j=0}.
\]

Ta vừa chọn toàn bộ đoạn `[start,i+1)`. Nếu giữ một hậu tố không rỗng, phần đó nằm trong đoạn đã chọn; một khớp mới bắt đầu từ phần suffix sẽ **giao** với lần trước. Reset j=0 buộc mọi khớp mới bắt đầu từ **sau i**, đúng quy tắc không chồng lấn.

### Ví dụ KMP cho mẫu "aaa"

Với P=`"aaa"`:

~~~text
pi = [0,1,2]
T = "aaaaa"

KMP đọc i=0,1,2: j=3 -> khớp ở start=0

Overlap:
    j=pi[2]=2
    đọc i=3 -> j=3 -> khớp ở start=1
    j=2
    đọc i=4 -> j=3 -> khớp ở start=2
    kết quả [0,1,2]

Non-overlap:
    j=0 sau lần khớp start=0
    chỉ còn hai ký tự T[3],T[4], không đủ "aaa"
    kết quả [0]
~~~

### Ví dụ KMP cho mẫu "aba"

Với P=`"aba"`, pi=[0,0,1]. Sau khi khớp đầu ở `start=0` của T=`"abababa"`:

- Overlap giữ j=1; có thể nhận khớp ở 2 và 4.
- Non-overlap reset j=0; khớp ở 2 không được phép dùng vì giao với `[0,3)`, chỉ nhận tiếp vị trí 4.

Kết quả:

~~~text
Overlap starts:     [0,2,4]
Non-overlap starts: [0,4]
~~~

### Nếu mẫu không có biên dương thì sao?

Khi \(\pi[m-1]=0\), hai chế độ KMP **đều reset j=0 sau mỗi khớp**. Đây không phải ngẫu nhiên: nếu hai lần xuất hiện của P chồng lấn, phần chung phải đồng thời là **hậu tố** của khớp trước và **tiền tố** của khớp sau. Nó tạo một **biên dương của P**.

Vì vậy với \(\pi[m-1]=0\), **không thể có hai lần xuất hiện của P chồng lấn**, và hai cách đếm luôn bằng nhau. Chiều ngược không bắt buộc: \(\pi[m-1]>0\) chỉ cho biết P có **khả năng** tự chồng lấn, chứ không bảo đảm T thực sự có các khớp chồng lấn.

## 8. Đếm trực tiếp, KMP, và cách kiểm tra độc lập

Có ba lựa chọn triển khai:

| Phương pháp | Nguyên lý | Thời gian | Ghi chú |
|---|---|---|---|
| Quét mọi vị trí | So sánh T[i..i+m) với P | O(nm) xấu nhất | Rất tốt làm oracle |
| `String.indexOf` lặp lại | Lấy vị trí khớp kế, nhảy i+1 hoặc i+m | Phụ thuộc triển khai thư viện | Code ngắn và dễ đọc |
| **KMP** | Prefix function + quét T một lần | **O(n+m)** | Rõ ràng cận và hỗ trợ stream |

Cả ba đều có thể trả **danh sách vị trí khớp** hoặc chỉ số lượng.

Nếu chỉ cần số lần xuất hiện, giữ một biến đếm, không lưu mọi vị trí. Với KMP:

- Xây pi **O(m)**.
- Duyệt T **O(n)** amortized.
- **O(m)** bộ nhớ cho pi, **O(1)** cho biến đếm.
- Nếu lưu k vị trí, thêm **O(k)** bộ nhớ.

Dù không chồng lấn, KMP vẫn quét toàn văn bản từng ký tự; reset j=0 **không làm tăng độ phức tạp**. Khác nhau chỉ là tập vị trí được nhận sau mỗi khớp.

## 9. Chương trình Java 17+ hoàn chỉnh

Tệp **SubstringOccurrenceDemo.java** sau cài:

- `prefixFunction`: tính `pi[]`.
- `kmpStarts`: lấy các vị trí bắt đầu bằng KMP, tham số `allowOverlap`.
- `indexOfStarts`: hiện thực ngắn hơn để kiểm tra lại cùng dữ liệu.
- `StreamingCounter`: duy trì trạng thái KMP khi văn bản được cung cấp thành nhiều **chunk** mà không cần nối sẵn toàn bộ chuỗi.
- `main`: chạy các ví dụ có/không chồng lấn, trường hợp mẫu dài hơn văn bản, text rỗng, chuỗi Unicode, stream nhiều chunk và từ chối mẫu rỗng.

**Chương trình hoàn chỉnh:**

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class SubstringOccurrenceDemo {
    private static void requirePattern(String pattern) {
        Objects.requireNonNull(pattern, "pattern");
        if (pattern.isEmpty()) {
            throw new IllegalArgumentException(
                "pattern must not be empty"
            );
        }
    }

    static int[] prefixFunction(String pattern) {
        requirePattern(pattern);
        int m = pattern.length();
        int[] pi = new int[m];

        for (int i = 1, j = 0; i < m; i++) {
            while (j > 0 && pattern.charAt(i) != pattern.charAt(j)) {
                j = pi[j - 1];
            }
            if (pattern.charAt(i) == pattern.charAt(j)) {
                j++;
            }
            pi[i] = j;
        }
        return pi;
    }

    static List<Integer> kmpStarts(
        String text, String pattern, boolean allowOverlap
    ) {
        Objects.requireNonNull(text, "text");
        requirePattern(pattern);

        int m = pattern.length();
        int[] pi = prefixFunction(pattern);
        List<Integer> starts = new ArrayList<>();
        int j = 0;

        for (int i = 0; i < text.length(); i++) {
            char current = text.charAt(i);

            while (j > 0 && current != pattern.charAt(j)) {
                j = pi[j - 1];
            }
            if (current == pattern.charAt(j)) {
                j++;
            }

            if (j == m) {
                starts.add(i - m + 1);
                j = allowOverlap ? pi[m - 1] : 0;
            }
        }

        return List.copyOf(starts);
    }

    // An independent formulation using String.indexOf.
    static List<Integer> indexOfStarts(
        String text, String pattern, boolean allowOverlap
    ) {
        Objects.requireNonNull(text, "text");
        requirePattern(pattern);
        List<Integer> starts = new ArrayList<>();
        int from = 0;

        while (true) {
            int i = text.indexOf(pattern, from);
            if (i < 0) {
                break;
            }

            starts.add(i);
            from = i + (allowOverlap ? 1 : pattern.length());
        }

        return List.copyOf(starts);
    }

    // KMP carries its state across consecutive chunks.
    static final class StreamingCounter {
        final String pattern;
        final int[] pi;
        final boolean allowOverlap;
        int matched = 0;
        long consumed = 0L;
        final List<Long> starts = new ArrayList<>();

        StreamingCounter(String pattern, boolean allowOverlap) {
            requirePattern(pattern);
            this.pattern = pattern;
            this.pi = prefixFunction(pattern);
            this.allowOverlap = allowOverlap;
        }

        void feed(String chunk) {
            Objects.requireNonNull(chunk, "chunk");

            for (int i = 0; i < chunk.length(); i++) {
                char current = chunk.charAt(i);

                while (matched > 0
                        && current != pattern.charAt(matched)) {
                    matched = pi[matched - 1];
                }
                if (current == pattern.charAt(matched)) {
                    matched++;
                }

                if (matched == pattern.length()) {
                    starts.add(
                        consumed - pattern.length() + 1
                    );
                    matched = allowOverlap
                        ? pi[pattern.length() - 1] : 0;
                }
                consumed++;
            }
        }

        List<Long> starts() {
            return List.copyOf(starts);
        }

        long count() {
            return starts.size();
        }
    }

    private static void show(String text, String pattern) {
        List<Integer> overlapping =
            kmpStarts(text, pattern, true);
        List<Integer> nonOverlapping =
            kmpStarts(text, pattern, false);

        if (!overlapping.equals(indexOfStarts(text, pattern, true))
                || !nonOverlapping.equals(
                    indexOfStarts(text, pattern, false)
                )) {
            throw new AssertionError("KMP / indexOf disagree");
        }

        System.out.println(
            "text=\"" + text + "\", pattern=\"" + pattern
            + "\" -> overlap=" + overlapping.size() + " " + overlapping
            + "; nonOverlap=" + nonOverlapping.size() + " "
            + nonOverlapping
        );
    }

    public static void main(String[] args) {
        System.out.println("pi(ababaca): "
            + Arrays.toString(prefixFunction("ababaca")));

        show("aaaaa", "aaa");
        show("banana", "ana");
        show("abababa", "aba");
        show("aaaaaa", "aa");
        show("abc", "d");
        show("", "a");
        show("a", "aa");
        show("a😀😀", "😀");
        show("😀😀😀", "😀😀");
        show("aaaa", "a");
        show("aaaa", "aa");

        List<String> chunks = List.of("ab", "aba", "ba");
        StreamingCounter over = new StreamingCounter("aba", true);
        StreamingCounter nonOver = new StreamingCounter("aba", false);
        for (String chunk : chunks) {
            over.feed(chunk);
            nonOver.feed(chunk);
        }
        System.out.println("Chunks: " + chunks);
        System.out.println("Stream overlap: "
            + over.count() + " " + over.starts());
        System.out.println("Stream nonOverlap: "
            + nonOver.count() + " " + nonOver.starts());

        try {
            kmpStarts("abc", "", true);
        } catch (IllegalArgumentException e) {
            System.out.println("Empty pattern rejected: "
                + e.getMessage());
        }
        System.out.println("Sample cross-check: PASS");
    }
}
~~~

Lưu đúng tên tệp và chạy bằng **JDK 17 trở lên**, trong terminal hỗ trợ Unicode. Chỉ rõ mã nguồn UTF-8 để tránh phụ thuộc bảng mã mặc định của trình biên dịch:

~~~bash
javac -encoding UTF-8 SubstringOccurrenceDemo.java
java SubstringOccurrenceDemo
~~~

**Stdout chính xác:**

~~~text
pi(ababaca): [0, 0, 1, 2, 3, 0, 1]
text="aaaaa", pattern="aaa" -> overlap=3 [0, 1, 2]; nonOverlap=1 [0]
text="banana", pattern="ana" -> overlap=2 [1, 3]; nonOverlap=1 [1]
text="abababa", pattern="aba" -> overlap=3 [0, 2, 4]; nonOverlap=2 [0, 4]
text="aaaaaa", pattern="aa" -> overlap=5 [0, 1, 2, 3, 4]; nonOverlap=3 [0, 2, 4]
text="abc", pattern="d" -> overlap=0 []; nonOverlap=0 []
text="", pattern="a" -> overlap=0 []; nonOverlap=0 []
text="a", pattern="aa" -> overlap=0 []; nonOverlap=0 []
text="a😀😀", pattern="😀" -> overlap=2 [1, 3]; nonOverlap=2 [1, 3]
text="😀😀😀", pattern="😀😀" -> overlap=2 [0, 2]; nonOverlap=1 [0]
text="aaaa", pattern="a" -> overlap=4 [0, 1, 2, 3]; nonOverlap=4 [0, 1, 2, 3]
text="aaaa", pattern="aa" -> overlap=3 [0, 1, 2]; nonOverlap=2 [0, 2]
Chunks: [ab, aba, ba]
Stream overlap: 3 [0, 2, 4]
Stream nonOverlap: 2 [0, 4]
Empty pattern rejected: pattern must not be empty
Sample cross-check: PASS
~~~

### Vì sao mã chạy được và không bỏ sót khớp?

Ở **đầu mỗi lượt quét** một ký tự T[i], `j<m`. Nếu `j==m` sau khi so sánh, chương trình luôn đặt lại j **trước khi đọc ký tự tiếp theo**, nên `pattern.charAt(j)` không truy cập ngoài mảng.

Trong chế độ overlap, j được đặt thành `pi[m-1]`, luôn nhỏ hơn m. Trong chế độ non-overlap, j trở về 0. Điều này vừa an toàn chỉ số vừa thể hiện đúng chính sách chọn các khoảng.

`indexOfStarts` không dùng bảng pi, nên so sánh kết quả của nó với `kmpStarts` là một kiểm tra hữu ích giữa hai cơ chế khác nhau. `List.copyOf` đóng băng danh sách vị trí trả về trước thay đổi ngẫu nhiên từ bên gọi.

`StreamingCounter` xử lý từng ký tự của chunk, không reset `matched` khi bắt đầu chunk mới. `consumed` đếm **số đơn vị UTF-16** của toàn bộ luồng đã đọc, nên chỉ số bắt đầu một khớp kết thúc tại ký tự hiện tại bằng `consumed-m+1`.

## 10. Streaming: khớp qua biên chunk

Ví dụ chuỗi T=`"abababa"` được đưa tới thành ba phần:

~~~text
chunk 1 = "ab"
chunk 2 = "aba"
chunk 3 = "ba"
pattern = "aba"
~~~

Nếu tìm riêng `"aba"` trong `"ab"`, ta chưa có kết quả. Nhưng hai ký tự `ab` đã khớp tiền tố dài 2 của mẫu. Khi đọc ký tự đầu của chunk 2 là `a`, KMP hoàn thành mẫu và báo vị trí **0**. Đây là một lần khớp **băng qua ranh giới chunk**.

Tiếp tục duy trì cùng trạng thái:

~~~text
overlap positions    = [0,2,4]
non-overlap positions= [0,4]
~~~

Vì cả hai chế độ xử lý chuỗi **logic liên tục** theo đúng thứ tự ký tự, kết quả streaming phải giống kết quả tìm kiếm trên `String.join("",chunks)` — không cần tạo chuỗi nối đó trong triển khai thực tế.

### Điều gì sai nếu khởi tạo KMP lại ở mỗi chunk?

Ta sẽ bỏ sót những lần khớp bắt đầu trong chunk trước nhưng kết thúc ở chunk sau. Nếu cố ghép phần đuôi chunk trước vào chunk sau, phải bảo đảm:

- Không tính lại khớp đã báo trước đó.
- Chuyển đúng chỉ số tương đối sang chỉ số toàn luồng.
- Với non-overlap, giữ thông tin **lần khớp đã chọn gần nhất** để không nhận đoạn giao nhau.
- Không cắt sai đơn vị mã Unicode nếu đầu vào có surrogate pair.

Giữ `matched` xuyên chunk đơn giản hơn và dùng **O(m)** bộ nhớ cho mẫu/pi. Nếu chỉ muốn **số lần** chứ không cần vị trí, có thể bỏ danh sách `starts` và chỉ tăng một biến đếm `long`.

### Bộ nhớ khi chỉ đếm

Mã demo lưu mọi vị trí để minh họa. Nếu T rất lớn và mẫu xuất hiện hàng triệu lần, lưu toàn bộ vị trí tốn O(k) bộ nhớ. Bản count-only cần:

~~~text
int matched;
long count;
int[] pi;
String pattern;
~~~

Nó không cần lưu bất kỳ phần nào của văn bản đã đọc. Khi j==m, tăng `count`, cập nhật j theo chính sách rồi xử lý ký tự tiếp theo. Tổng bộ nhớ phụ là **O(m)**.

## 11. Đúng đắn của hai chế độ KMP

### KMP cho phép chồng lấn tìm đủ mọi vị trí

Bất biến của KMP: sau khi xử lý phần T đã đọc, j mô tả độ dài tiền tố P phù hợp với hậu tố phần văn bản ở trạng thái hiện tại. Khi sai ký tự, việc rút j theo `pi[j-1]` chỉ loại những độ dài tiền tố **không thể tiếp tục**; các khả năng còn hợp lệ được bảo toàn bởi các biên của mẫu.

Khi j=m, đúng m ký tự văn bản kết thúc tại i bằng P, nên báo vị trí i−m+1. Sau đó `j=pi[m-1]` lưu phần hậu tố của chính lần khớp vừa xong có thể làm **tiền tố của lần khớp tiếp theo**. Đây là cơ chế cho phép phát hiện mọi sự chồng lấn hợp lệ mà không đọc lại văn bản.

Mỗi vị trí kết thúc được xử lý đúng một lần. Vì thế mỗi lần xuất hiện được đếm một lần và không bỏ sót.

### KMP không chồng lấn luôn nhận các khoảng rời nhau

Giả sử KMP vừa nhận khớp bắt đầu tại `start=i-m+1`, kết thúc trước vị trí `i+1`. Reset j=0 xóa mọi tiền tố đang dựa trên ký tự **bên trong đoạn đã chọn**. Lần khớp sau phải bắt đầu ở **i+1 hoặc muộn hơn**, nên các khoảng không giao nhau.

KMP vẫn tìm lần khớp sớm nhất trong phần T còn lại vì nó duyệt ký tự theo thứ tự và không bỏ sót khớp trong phần chưa dùng. Theo chứng minh tham lam phần 4, số đoạn được chọn là **lớn nhất có thể**.

### Thời gian và bộ nhớ

Với n là số đơn vị UTF-16 của T và m của P:

- Tính pi: **O(m)**.
- Tìm khớp bằng KMP: **O(n)** amortized.
- Tổng: \(\boxed{O(n+m)}\).
- Bộ nhớ pi: **O(m)**.
- Lưu k vị trí: thêm **O(k)**.
- Chỉ đếm: **O(m)** tổng bộ nhớ phụ.

Cả hai chế độ có cùng cận xấu nhất. Việc reset j sau lần khớp không thể làm thuật toán cần duyệt lại đoạn văn bản; i luôn tăng.

## 12. Unicode: chỉ số của Java là UTF-16

Java `String` biểu diễn dữ liệu bằng **UTF-16 code units**, nên:

- `String.length()` đếm số **đơn vị UTF-16**.
- `String.charAt(i)` trả một đơn vị UTF-16.
- `String.indexOf` trả offset UTF-16.
- Mã KMP trong bài cũng trả offset UTF-16.

Ví dụ emoji `😀` dùng **hai code units**, do đó với T=`"a😀😀"`, P=`"😀"`:

~~~text
Code points:       a   😀   😀
Code-point index:  0    1    2
UTF-16 offset:     0    1    3
~~~

Danh sách vị trí KMP là **[1,3]**, không phải [1,2].

Với T=`"😀😀😀"` và P=`"😀😀"`:

~~~text
UTF-16 length of T = 6
UTF-16 length of P = 4
overlap starts = [0,2]
nonOverlap starts = [0]
~~~

Nếu bài yêu cầu vị trí theo **Unicode code point**, cần chạy KMP trên các giá trị `int` lấy từ `String.codePoints()`, hoặc tạo ánh xạ offset trước khi xuất. Nếu cần “ký tự nhìn thấy” theo **grapheme cluster**, lại phải phân đoạn Unicode riêng; ngay cả code point cũng chưa chắc tương ứng một ký tự hiển thị.

### Hoa/thường và chuẩn hóa

KMP ở đây so sánh chính xác. `"A"` và `"a"` khác nhau; ký tự `é` được mã hóa thành một code point và chuỗi `e` cộng dấu kết hợp có thể hiển thị giống nhau nhưng khác ở cấp mã.

Nếu yêu cầu không phân biệt chữ hoa/thường hoặc chuẩn hóa Unicode, phải **biến đổi đồng nhất cả T và P**. Quá trình này có thể làm thay đổi chiều dài và offset; nếu cần trả chỉ số trên T gốc, phải lưu ánh xạ giữa văn bản biến đổi và văn bản ban đầu.

Không nên âm thầm lower-case rồi dùng các chỉ số cũ để cắt chuỗi gốc khi phép biến đổi làm độ dài thay đổi.

## 13. Trường hợp biên và quy ước

| Dữ liệu / tình huống | Kết quả đúng theo bài |
|---|---|
| T rỗng, P không rỗng | 0 lần ở cả hai chế độ |
| P dài hơn T | 0 lần |
| Không có lần khớp | 0 lần |
| T bằng P, P không rỗng | 1 lần |
| P dài một ký tự | Overlap = non-overlap |
| T toàn ký tự giống nhau, P lặp ký tự đó | Có thể có chênh lệch lớn |
| Hai khớp sát nhau, đầu sau bằng cuối trước | Không chồng lấn |
| P rỗng | Mã **từ chối** bằng `IllegalArgumentException` |
| T hoặc P null | `NullPointerException` do `Objects.requireNonNull` |
| T/P chứa emoji | Vị trí là offset UTF-16 |
| Streaming chia cắt giữa một lần khớp | KMP phải giữ `matched` qua chunk |
| Chỉ cần count, số khớp rất lớn | Nên dùng biến long và không lưu vị trí |
| So khớp không phân biệt hoa thường | Cần chính sách chuẩn hóa riêng |
| Nhiều mẫu có chiều dài khác nhau | Cần xác định quy tắc cấm chồng lấn giữa các mẫu |

### Mẫu rỗng không có một cách đếm mặc định cho mọi đề

Một số định nghĩa coi mẫu rỗng xuất hiện tại **n+1 ranh giới** của T. Nhưng khoảng dài 0 không dùng ký tự nào, và việc “cấm chồng lấn” trên các khoảng rỗng không nhất thiết có ý nghĩa như mẫu có m>0. Một số hệ thống chọn 0 hoặc 1 lần; một số từ chối.

Trong bài và Java demo, **m=0 là lỗi đầu vào**, giúp thuật toán tiến đều và cách giải thích các khoảng thống nhất. Nếu một đề khác chấp nhận mẫu rỗng, phải viết đặc tả và test riêng, không tùy tiện lấy nhánh xử lý m>0 để áp dụng.

## 14. Phân biệt ba câu hỏi đếm khác nhau

Với T=`"aaaa"`, P=`"aa"`:

~~~text
T positions: 0 1 2 3
All matches: 0,1,2

overlap count = 3
maximum non-overlap count = 2, choose {0,2}
~~~

Nhưng nếu hỏi “có bao nhiêu cách chọn một **tập con** các vị trí khớp không giao nhau?”, tính cả tập rỗng thì có:

~~~text
{}
{0}
{1}
{2}
{0,2}
~~~

Tổng cộng **5 cách**. Đây không phải kết quả 2 và cũng không phải 3.

Nếu các lần khớp đều dài m, một DP đếm số cách chọn có thể xét tại mỗi vị trí “bỏ qua khớp này” hoặc “nhận khớp này và bỏ mọi khớp giao nó”. Tuy nhiên nếu có nhiều vị trí dẫn tới cùng lựa chọn, cần định nghĩa cách nhận diện **mỗi phương án** chính xác để tránh đếm trùng.

Tương tự, với **regex**, một mẫu có thể khớp nhiều độ dài, có lookahead hoặc khớp chuỗi rỗng; semantics của `Matcher.find()` là một hợp đồng riêng. Không dùng trực tiếp công thức `i+m` với **m không cố định**.

Nếu có **nhiều literal patterns**, có thể dùng Aho–Corasick để tìm nhiều lần khớp, nhưng cách tối đa hóa số lần **không chồng lấn giữa các mẫu** cần mô hình khoảng (và quy tắc chọn theo kết thúc sớm nhất nếu tối đa số lượng). Đây là bài khác với một P cố định trong bài này.

## 15. Lỗi thường gặp

1. **Không hỏi rõ có cho phép chồng lấn** trước khi đếm.
2. **Dùng `from=i+m` khi cần đếm tất cả khớp**, bỏ các vị trí giao nhau.
3. **Dùng `from=i+1` khi cần cấm chồng lấn**, đếm các đoạn bị trùng ký tự.
4. **Dựa trên `from` cũ thay vì vị trí i vừa tìm được** để tính lần tìm tiếp.
5. **Dùng `j=0` sau khớp KMP overlap**, bỏ khả năng hậu tố nối tiếp tiền tố.
6. **Dùng `j=pi[m-1]` khi cấm chồng lấn**, nhận các khớp bắt đầu trong đoạn đã dùng.
7. **Tăng i thêm m bên trong vòng KMP vốn đã tăng i**, gây bỏ sót ký tự.
8. **Nhầm khoảng [start,end) với [start,end]**, coi hai khớp sát nhau là chồng lấn.
9. **Không kiểm P rỗng**, có thể gây vòng lặp vô hạn hoặc nhầm số ranh giới.
10. **Đánh đồng `String.length` với số Unicode code points**, khiến chỉ số emoji bị lệch.
11. **Chuẩn hóa T mà không chuẩn hóa P** trong bài không phân biệt biểu diễn Unicode.
12. **Làm mất offset gốc** khi chuẩn hóa, rồi dùng offset biến đổi để trích T gốc.
13. **Xử lý mỗi chunk độc lập**, bỏ sót khớp ở ranh giới chunk.
14. **Giữ một đoạn đuôi chunk và đếm lại** khớp đã được báo ở chunk trước.
15. **Chỉ cần count nhưng lưu toàn bộ các vị trí**, lãng phí bộ nhớ.
16. **Lấy `String.indexOf` và tự tuyên bố O(n+m)** mà không có phân tích thuật toán thực tế.
17. **Áp greedy earliest-start cho nhiều mẫu chiều dài biến đổi**, không còn chứng minh tối ưu.
18. **Nhầm “số lần không chồng lấn lớn nhất” với “số cách chọn”**, cho kết quả sai đề.
19. **Bỏ qua T rỗng hoặc m>n** trong test.
20. **Không thử các mẫu có tiền tố/hậu tố trùng mạnh** như `"aaa"`, `"aba"`, `"abab"`.
21. **Đếm thành công KMP rồi không cập nhật j**, khiến lần quét tiếp theo truy cập `pattern.charAt(m)` ngoài phạm vi.
22. **Không dùng cùng đơn vị chỉ số giữa KMP và chương trình xử lý đầu ra** (0-based/1-based, UTF-16/code point).
23. **Không kiểm số khớp non-overlap ≤ overlap** khi debug.
24. **Không phân biệt đếm số bước của vòng lặp với đếm số khớp**, nhất là khi không có khớp.
25. **Không kiểm mẫu chỉ có một ký tự**, nơi hai chế độ bắt buộc bằng nhau.

## 16. Kiểm chứng với oracle độc lập

Với P không rỗng và T nhỏ, một oracle độc lập với KMP là **quét mọi vị trí bắt đầu**:

~~~text
all = []
for i from 0 to n-m:
    if T[i,i+m) equals P:
        all.add(i)
~~~

Kết quả `all` chính là danh sách overlap. Với non-overlap, từ `all` sắp tăng chọn tham lam:

~~~text
chosen = []
nextAllowed = 0
for i in all:
    if i >= nextAllowed:
        chosen.add(i)
        nextAllowed = i + m
~~~

Cần đối chiếu **toàn bộ danh sách vị trí**, không chỉ count, vì hai chương trình có thể cùng count nhưng sai một vài offset.

### Oracle DP kiểm số lần tối đa

Với dữ liệu nhỏ, đặt `dp[i]` là số lần khớp không chồng lấn tối đa tính từ vị trí i. Có hai lựa chọn:

- Bỏ qua i: `dp[i+1]`.
- Nếu có khớp bắt đầu tại i: nhận nó và dùng `1+dp[i+m]`.

Do đó:

\[
\boxed{
dp[i]=\max\left(dp[i+1],
\ 1+dp[i+m]\ \text{nếu khớp tại i}\right).
}
\]

Với i lớn hơn n−m, `dp[i]=0`. So sánh count non-overlap của KMP với `dp[0]` để kiểm chứng quy tắc tham lam bằng một cơ chế **khác**.

### Bộ test nên có

| T | P | Các vị trí overlap | Các vị trí non-overlap |
|---|---|---|---|
| `aaaaa` | `aaa` | 0,1,2 | 0 |
| `banana` | `ana` | 1,3 | 1 |
| `abababa` | `aba` | 0,2,4 | 0,4 |
| `aaaaaa` | `aa` | 0,1,2,3,4 | 0,2,4 |
| `abc` | `d` | không có | không có |
| `a` | `aa` | không có | không có |
| `aaaa` | `a` | 0,1,2,3 | 0,1,2,3 |
| `😀😀😀` | `😀😀` | UTF-16: 0,2 | UTF-16: 0 |

Nên sinh ngẫu nhiên T,P từ một bảng chữ cái nhỏ, so sánh **KMP**, **duyệt brute-force**, **String.indexOf** và **DP tối ưu non-overlap**. Với streaming, chia cùng một T ở các ranh giới chunk khác nhau và đối chiếu kết quả với xử lý toàn chuỗi.

## 17. Bài tập tự luyện

**Bài 1.** Với T=`"aaaaa"`, P=`"aaa"`, có bao nhiêu lần xuất hiện nếu cho chồng lấn?

*Đáp án:* **3**, tại các vị trí 0,1,2.

**Bài 2.** Cùng dữ liệu, nếu không cho chồng lấn, số lần lớn nhất là bao nhiêu?

*Đáp án:* **1**.

**Bài 3.** T=`"abababa"`, P=`"aba"`: danh sách non-overlap là gì?

*Đáp án:* **[0,4]**; lần khớp tại 2 giao với lần tại 0.

**Bài 4.** T=`"banana"`, P=`"ana"`: vì sao hai lần khớp không thể chọn cùng lúc?

*Đáp án:* Các đoạn [1,4) và [3,6) giao tại chỉ số 3.

**Bài 5.** T=`"aaaaaa"`, P=`"aa"`: số lần hai chế độ?

*Đáp án:* **5** overlapping, **3** non-overlapping.

**Bài 6.** Một khớp `indexOf` bắt đầu tại 7, m=4. Tìm lần tiếp theo từ đâu?

*Đáp án:* **8** nếu cho chồng lấn; **11** nếu không.

**Bài 7.** Nếu P=`"aaa"`, prefix function là gì?

*Đáp án:* **[0,1,2]**.

**Bài 8.** KMP cho chồng lấn cập nhật j sau full match như thế nào?

*Đáp án:* **`j=pi[m-1]`**.

**Bài 9.** KMP không chồng lấn cập nhật j sau full match thế nào?

*Đáp án:* **`j=0`**.

**Bài 10.** Nếu m=1, hai cách đếm có thể khác không?

*Đáp án:* **Không**, vì các khớp ở vị trí khác nhau không thể dùng chung một đơn vị ký tự.

**Bài 11.** Với n=10,m=3, overlap count tối đa bao nhiêu?

*Đáp án:* **n−m+1=8**.

**Bài 12.** Với n=10,m=3, non-overlap count không thể vượt bao nhiêu?

*Đáp án:* **floor(10/3)=3**.

**Bài 13.** Nếu pi[m−1]=0, P có thể xuất hiện chồng lấn với chính nó không?

*Đáp án:* **Không**; chồng lấn sẽ tạo một biên toàn mẫu dương, trái giả thiết.

**Bài 14.** Mẫu rỗng trong chương trình được xử lý thế nào?

*Đáp án:* Bị từ chối bằng `IllegalArgumentException`; muốn đếm các ranh giới phải đổi đặc tả.

**Bài 15.** T=`"a😀😀"`, P=`"😀"`: vị trí Java trả là gì?

*Đáp án:* Offset UTF-16 **[1,3]**.

**Bài 16.** Nếu T được gửi thành ba chunk `"ab"`, `"aba"`, `"ba"`, có thể đếm riêng từng chunk rồi cộng được không?

*Đáp án:* **Không**; khớp có thể vượt biên chunk, cần giữ trạng thái KMP.

**Bài 17.** Độ phức tạp KMP trên T dài n, P dài m là gì?

*Đáp án:* **O(n+m)** thời gian, O(m) bộ nhớ cho pi nếu chỉ đếm.

**Bài 18.** Đếm **số cách chọn** các khớp không giao nhau có đồng nghĩa count non-overlap không?

*Đáp án:* **Không**. Count non-overlap là số khớp chọn tối đa; số cách chọn là một bài đếm tổ hợp/DP.

**Bài 19.** Nhiều mẫu độ dài khác nhau, muốn chọn nhiều đoạn không giao nhau, có luôn ưu tiên vị trí bắt đầu sớm nhất?

*Đáp án:* **Không**. Với interval scheduling độ dài thay đổi, thường chọn đoạn **kết thúc sớm nhất**, không phải bắt đầu sớm nhất.

**Bài 20.** Cách nào kiểm tra kết quả KMP non-overlap độc lập?

*Đáp án:* Quét mọi vị trí khớp bằng brute-force, chọn greedy trên danh sách ấy, và có thể đối chiếu count với DP `dp[i]`.

**Tổng kết:** Một lần xuất hiện của mẫu P không rỗng tại i chiếm khoảng **[i,i+m)**. Với **cho phép chồng lấn**, đếm mọi vị trí khớp; với **cấm chồng lấn**, chọn các khoảng rời nhau, và với **một mẫu cố định**, tham lam lấy lần sớm nhất đạt số lượng tối đa. Khi dùng `String.indexOf`, sau khớp tại i hãy tìm tiếp từ **i+1** hoặc **i+m**. Khi dùng KMP, sau khi `j==m`, hãy đặt **`j=pi[m-1]` cho overlapping** hoặc **`j=0` cho non-overlapping**. Cả hai chế độ KMP có cận **O(n+m)**. Hãy xác định rõ chính sách mẫu rỗng, đơn vị chỉ số UTF-16, điều kiện ghép chunk và phân biệt **đếm số lần** với **đếm số cách chọn**.
