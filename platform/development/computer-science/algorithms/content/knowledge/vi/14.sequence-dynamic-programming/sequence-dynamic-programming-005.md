# Đoạn con chung dài nhất và phân biệt với dãy con

## 1. Hai bài toán có tên gần giống nhưng yêu cầu rất khác nhau

Cho hai chuỗi (hoặc hai dãy) `A` và `B`. Có hai khái niệm cần phân biệt rõ:

- **Đoạn con chung dài nhất** (*Longest Common Substring*, thường viết **LCSubstring**): tìm một đoạn các phần tử **liên tiếp** xuất hiện nguyên vẹn, đúng thứ tự, ở cả hai dãy.
- **Dãy con chung dài nhất** (*Longest Common Subsequence*, viết **LCS**): tìm một dãy giữ nguyên **thứ tự tương đối**, nhưng **được phép bỏ qua** một số phần tử ở giữa mỗi dãy.

Chữ **“liên tiếp”** là điểm quyết định. Mọi đoạn con chung đều là một dãy con chung, nhưng không phải dãy con chung nào cũng là đoạn con.

Ví dụ:

```text
A = "abcde"
B = "ace"

Đoạn con chung:
  "a", "c", "e" (đều dài 1)
  "ac" KHÔNG phải đoạn con của A hoặc B theo nghĩa liên tiếp.

Dãy con chung:
  "ace" dài 3
  vì trong A ta có thể lấy a, bỏ b, lấy c, bỏ d, lấy e.

Đáp án LCSubstring: độ dài 1, ví dụ "a".
Đáp án LCS:       độ dài 3, "ace".
```

Hai bài toán có thể có kết quả giống nhau trên một số đầu vào, nhưng **công thức quy hoạch động và cách lấy đáp án khác nhau**. Nếu nhầm công thức, chương trình có thể chạy đúng trên các ví dụ đơn giản mà trả sai trên dữ liệu có ký tự bị chen giữa.

Trong tiếng Việt, **“đoạn con”** thường nhấn mạnh tính liên tiếp, còn **“dãy con”** (*subsequence*) cho phép bỏ phần tử. Trong tiếng Anh, *substring* áp dụng cho chuỗi ký tự; với mảng, khái niệm tương ứng thường gọi là *subarray* hoặc *contiguous segment*. Khi đọc đề, hãy ưu tiên **định nghĩa cụ thể** hơn là chỉ tên tiếng Anh/tiếng Việt.

## 2. Định nghĩa và điều kiện chính xác

Xét hai dãy `A` và `B` dài lần lượt `m` và `n`.

### 2.1. Đoạn con liên tiếp

Một đoạn con của `A` là các phần tử `A[l], A[l+1], \ldots, A[r-1]` với `0 \le l \le r \le m`, thường viết là khoảng chỉ số nửa mở `[l,r)`. Độ dài là `r-l`.

Một dãy `X` là **đoạn con chung** nếu tồn tại các vị trí bắt đầu `p` trong `A` và `q` trong `B` sao cho:

\[
A[p+t]=B[q+t]\quad\text{với mọi }0\le t<|X|.
\]

Tức là khi đã bắt đầu so khớp, **không được bỏ ký tự ở giữa**. LCSubstring tìm `X` có `|X|` lớn nhất.

Ví dụ:

```text
A = "ababc"
B = "babca"

A[1..5) = "babc"
B[0..4) = "babc"

Đoạn con chung dài nhất = "babc", độ dài 4.
```

Đáp án có thể không duy nhất. Nếu đề chỉ hỏi **độ dài**, trả một số nguyên. Nếu hỏi **một đoạn cụ thể**, cần quyết định cách xử lý trường hợp có nhiều đoạn dài nhất (ví dụ chọn đoạn xuất hiện sớm nhất trong `A`, rồi sớm nhất trong `B`).

### 2.2. Dãy con không nhất thiết liên tiếp

Một dãy con của `A` được tạo bằng cách chọn một số chỉ số **tăng nghiêm ngặt**:

\[
0\le i_1<i_2<\cdots<i_k<m,
\]

rồi lấy `A[i_1], A[i_2],\ldots,A[i_k]`. Các chỉ số được chọn không cần liền nhau.

Ví dụ:

```text
A = "abcde"
Chọn các chỉ số 0, 2, 4 -> "ace" (dãy con).
Nhưng "ace" không là đoạn con liên tiếp của A.
```

**LCS** tìm dãy con chung có độ dài lớn nhất. Kết quả không nhất thiết là một đoạn liên tiếp trong bất kỳ dãy đầu vào nào.

### 2.3. Bảng phân biệt nhanh

| Tiêu chí | Đoạn con chung dài nhất (LCSubstring) | Dãy con chung dài nhất (LCS) |
|---|---|---|
| Có bắt buộc liên tiếp? | **Có**, ở cả hai dãy | **Không** |
| Có phải giữ thứ tự? | Có | Có |
| Được bỏ ký tự ở giữa? | **Không** | **Có** |
| Ví dụ `A="abcde", B="ace"` | `"a"`, `"c"` hoặc `"e"`, dài `1` | `"ace"`, dài `3` |
| Trạng thái DP tiêu biểu | Độ dài **hậu tố chung** của hai tiền tố | Độ dài **dãy con chung tốt nhất** của hai tiền tố |
| Khi ký tự cuối khác nhau | **Đặt về `0`** | **Lấy max từ trên hoặc trái** |
| Đáp án độ dài | **Max trên mọi ô DP** | **`dp[m][n]`** |
| Có thể truy vết một đáp án? | Có, từ ô đạt max và vị trí kết thúc | Có, từ bảng DP và các quyết định đi chéo/lên/trái |

Hai bài đều thường được dạy bằng DP `O(mn)` nhưng **không thể hoán đổi công thức chuyển trạng thái**.

## 3. Vì sao “liên tiếp” thay đổi công thức DP?

Để hiểu sự khác biệt, xét **hai tiền tố**:

- `A[0..i)`: `i` phần tử đầu của `A`.
- `B[0..j)`: `j` phần tử đầu của `B`.

Các chỉ số `i,j` trong bảng DP là **độ dài tiền tố**, nên chạy từ `0` tới `m`/`n`. Ký tự cuối của hai tiền tố không rỗng là `A[i-1]` và `B[j-1]`.

Trong LCSubstring, ta chỉ có thể kéo dài một đoạn đang khớp khi **hai ký tự cuối bằng nhau**. Nếu khác, một đoạn chung kết thúc **đúng tại hai vị trí ấy** không thể có độ dài dương; phải đặt về `0`.

Trong LCS, hai ký tự cuối khác nhau không buộc ta xóa toàn bộ kết quả trước đó. Ta có quyền **bỏ ký tự cuối của một trong hai dãy** và giữ lại một dãy con chung đã tìm được. Vì vậy, trạng thái có thể kế thừa từ ô **phía trên hoặc phía trái**.

Đó là lý do bản chất của hai phép chuyển khác nhau dù cùng dùng hai vòng lặp.

## 4. Quy hoạch động cho đoạn con chung dài nhất (LCSubstring)

### 4.1. Định nghĩa trạng thái

Đặt `suffix[i][j]` là:

> **Độ dài của đoạn con chung dài nhất kết thúc đúng tại** `A[i-1]` và `B[j-1]`, tức độ dài **hậu tố chung dài nhất** của hai tiền tố `A[0..i)` và `B[0..j)`.

Đây là **hậu tố chung**, không phải “độ dài đoạn con chung dài nhất trong toàn bộ hai tiền tố”.

**Trạng thái cơ sở:** nếu ít nhất một tiền tố rỗng, không có hậu tố chung khác rỗng:

\[
suffix[0][j]=0,\quad suffix[i][0]=0.
\]

**Công thức chuyển:**

\[
suffix[i][j]=
\begin{cases}
suffix[i-1][j-1]+1,& A[i-1]=B[j-1],\\
0,& A[i-1]\ne B[j-1].
\end{cases}
\]

Và đáp án là:

\[
L_{\text{substring}}=\max_{\substack{0\le i\le m\\0\le j\le n}}suffix[i][j].
\]

**Nhớ:** không được chỉ trả `suffix[m][n]`, vì đoạn chung tốt nhất có thể kết thúc **ở giữa** hai chuỗi, không nhất thiết ở hai ký tự cuối.

### 4.2. Tại sao lệch ký tự phải đặt về 0?

Giả sử `A[i-1] != B[j-1]`. Không thể có đoạn chung độ dài ít nhất `1` mà đồng thời kết thúc ở hai ký tự khác nhau này. Dù trước đó có một đoạn chung dài, nó **không còn là hậu tố chung của hai tiền tố hiện tại**, vì ký tự cuối đã khác. Do đó trạng thái **bắt buộc bằng `0`**.

Nếu hai ký tự cuối bằng nhau, ta có thể nối đúng một ký tự vào hậu tố chung dài nhất của hai tiền tố trước đó: `suffix[i-1][j-1]+1`. Chỉ cần ô **chéo trên-trái** vì cả hai chuỗi đều tiến thêm một ký tự.

### 4.3. Ví dụ bảng DP nhỏ

Với `A="abc"` và `B="ac"`:

| `suffix[i][j]` | rỗng | a | c |
|---|---:|---:|---:|
| rỗng | 0 | 0 | 0 |
| a | 0 | 1 | 0 |
| b | 0 | 0 | 0 |
| c | 0 | 0 | 1 |

Độ dài đoạn con chung dài nhất bằng **max tất cả ô = 1**. Có hai đáp án tối ưu `"a"` và `"c"`.

Quan sát `suffix[3][2]=1` chỉ là độ dài của **hậu tố chung kết thúc tại hai ký tự cuối**. Trong ví dụ này nó trùng với max, nhưng không phải lúc nào cũng vậy. Với `A="abcX"` và `B="abcY"`, max bằng `3` (đoạn `"abc"`) trong khi `suffix[4][4]=0` vì `X!=Y`.

### 4.4. Truy vết một đoạn con chung

Mỗi khi tính được `suffix[i][j]` lớn hơn độ dài tốt nhất hiện tại `bestLen`, ghi lại:

- `bestLen=suffix[i][j]`.
- `endA=i`: vị trí **kết thúc không lấy** của đoạn trong `A`.
- `endB=j`: vị trí **kết thúc không lấy** của đoạn trong `B`.

Khi kết thúc:

```text
startA = endA - bestLen
startB = endB - bestLen
Đoạn con của A = A[startA .. endA)
Đoạn con của B = B[startB .. endB)
```

Nếu `bestLen=0`, hai chuỗi **không có phần tử chung nào**; trả chuỗi rỗng `""` và có thể quy ước vị trí bắt đầu là `-1` để biểu thị **không có lần xuất hiện không rỗng**.

Nếu nhiều đoạn cùng độ dài lớn nhất, một cách quyết định là **chỉ cập nhật khi `currentLen > bestLen`**, quét `i` rồi `j` tăng dần. Trong cách quét này, đoạn được giữ là đoạn có **vị trí bắt đầu sớm nhất trong `A`**; nếu cùng vị trí đó, chọn vị trí sớm nhất trong `B`. Đây là **quy tắc hòa do triển khai lựa chọn**, không phải định nghĩa bắt buộc của LCSubstring.

### 4.5. Tối ưu bộ nhớ còn hai hàng

Mỗi ô `suffix[i][j]` chỉ dùng `suffix[i-1][j-1]` của **hàng trước**. Vì vậy không cần lưu toàn bộ ma trận để lấy một đoạn chung:

```text
prev[j] = giá trị ở hàng i-1
curr[j] = giá trị ở hàng i

for i = 1..m:
    curr[0] = 0
    for j = 1..n:
        if A[i-1] == B[j-1]:
            curr[j] = prev[j-1] + 1
            cập nhật bestLen/endA/endB nếu lớn hơn
        else:
            curr[j] = 0
    hoán đổi prev và curr
```

Có `m×n` phép so sánh, nên thời gian `O(mn)`; phần bảng DP chỉ cần `O(n)` bộ nhớ. Nếu muốn dùng `O(min(m,n))` cho bảng, có thể đổi vai trò hai chuỗi sao cho chiều `j` là chuỗi ngắn hơn; khi trả **vị trí trong hai chuỗi gốc**, nhớ ánh xạ lại chiều sau khi đổi.

**Bẫy một hàng:** nếu cập nhật `dp[j]` từ trái sang phải rồi dùng ngay `dp[j-1]`, bạn có thể đã đọc giá trị của **hàng hiện tại**, không phải ô chéo của **hàng trước**. Ví dụ `A="a", B="aa"` có LCSubstring độ dài `1`; cách làm sai có thể cộng liên tiếp thành `2` trong một hàng. Với một hàng cần giữ **giá trị đường chéo cũ** một cách có chủ đích hoặc duyệt theo hướng phù hợp. Hai hàng thường dễ giải thích và kiểm thử hơn.

## 5. Quy hoạch động cho dãy con chung dài nhất (LCS)

### 5.1. Định nghĩa trạng thái

Đặt `dp[i][j]` là:

> **Độ dài dãy con chung dài nhất** của hai tiền tố `A[0..i)` và `B[0..j)`.

Khác LCSubstring, trạng thái này xét **mọi dãy con** trong hai tiền tố, chứ không bắt buộc kết thúc đúng tại `A[i-1]` và `B[j-1]`.

**Cơ sở:**

\[
dp[0][j]=0,\qquad dp[i][0]=0.
\]

**Công thức chuyển:**

\[
dp[i][j]=
\begin{cases}
dp[i-1][j-1]+1,& A[i-1]=B[j-1],\\
\max(dp[i-1][j],dp[i][j-1]),& A[i-1]\ne B[j-1].
\end{cases}
\]

**Đáp án độ dài** là:

\[
L_{\text{subsequence}}=dp[m][n].
\]

Không cần lấy max trên toàn bộ bảng: `dp[m][n]` đã đại diện cho **hai chuỗi đầy đủ**, và việc cho phép bỏ ký tự đảm bảo nó không nhỏ hơn các trạng thái tiền tố.

### 5.2. Vì sao khác nhau thì lấy max?

Khi `A[i-1] != B[j-1]`, một dãy con chung **không thể** dùng **cả hai ký tự cuối khác nhau** như cùng một ký tự cuối của dãy con. Có ít nhất một ký tự cuối phải bị bỏ:

- Bỏ `A[i-1]` → lời giải nằm trong `dp[i-1][j]`.
- Bỏ `B[j-1]` → lời giải nằm trong `dp[i][j-1]`.

Chọn phương án dài hơn. Không phải đặt `0` vì ta vẫn có thể giữ một dãy con chung ở **các vị trí trước đó**.

Khi hai ký tự cuối bằng nhau, tồn tại một lời giải tối ưu dùng ký tự cuối đó của cả hai chuỗi: ghép chúng sau một LCS của hai tiền tố trước, cho độ dài `dp[i-1][j-1]+1`.

### 5.3. So sánh ngay trên bảng nhỏ

Vẫn với `A="abc"` và `B="ac"`:

| `dp[i][j]` | rỗng | a | c |
|---|---:|---:|---:|
| rỗng | 0 | 0 | 0 |
| a | 0 | 1 | 1 |
| b | 0 | 1 | 1 |
| c | 0 | 1 | 2 |

Đáp án LCS là `dp[3][2]=2`, dãy `"ac"`. Hai chữ `a` và `c` **không liền nhau** trong `A` vì có `b` ở giữa, nên `"ac"` không phải đoạn con chung.

Cùng dữ liệu cho hai kết quả khác nhau:

```text
A = "abc"
B = "ac"

LCSubstring = 1, ví dụ "a".
LCS       = 2, "ac".
```

### 5.4. Truy vết một dãy con chung

Để **dựng lại** LCS chứ không chỉ tính độ dài, một cách đơn giản là lưu bảng `dp` đầy đủ. Bắt đầu ở `(i,j)=(m,n)`:

1. Nếu `A[i-1]==B[j-1]`, ký tự đó có thể thuộc một LCS. Ghi nó vào **phía trước** kết quả, rồi giảm cả `i,j`.
2. Nếu khác nhau và `dp[i-1][j] >= dp[i][j-1]`, giảm `i` (bỏ ký tự cuối của `A`).
3. Nếu khác nhau và `dp[i-1][j] < dp[i][j-1]`, giảm `j` (bỏ ký tự cuối của `B`).
4. Dừng khi `i==0` hoặc `j==0`.

Bởi truy vết đi **từ cuối về đầu**, có thể thu ký tự vào một mảng kết quả từ **phải sang trái** để không phải đảo cả chuỗi.

Khi hai hướng có cùng độ dài tối ưu, lựa chọn đi lên hay sang trái đều có thể đúng, nhưng có thể cho **hai LCS khác nhau**. Quy tắc hòa trong ví dụ Java là **ưu tiên đi lên** nếu bằng nhau; **không có lời hứa** trả dãy con chung nhỏ nhất theo từ điển.

### 5.5. Chỉ cần độ dài thì có thể giảm bộ nhớ

Nếu chỉ cần `dp[m][n]`, hàng hiện tại chỉ phụ thuộc hàng trước và ô bên trái trên hàng hiện tại. Có thể lưu `prev` và `curr` dài `n+1`:

```text
for i = 1..m:
    curr[0] = 0
    for j = 1..n:
        if A[i-1] == B[j-1]:
            curr[j] = prev[j-1] + 1
        else:
            curr[j] = max(prev[j], curr[j-1])
    swap(prev, curr)

return prev[n]
```

Nếu đổi vai trò để chiều trong là chuỗi ngắn hơn, phần DP chỉ tốn `O(min(m,n))` bộ nhớ. Tuy nhiên, **không còn toàn bộ bảng để truy vết trực tiếp**. Muốn dựng một LCS với bộ nhớ tuyến tính có thể dùng kỹ thuật như **Hirschberg**, dựa trên chia để trị và các hàng DP; đây là phần mở rộng, không phải điều mà phiên bản truy vết đầy đủ dưới đây đang làm.

## 6. Java 17+ hoàn chỉnh: tính và truy vết cả hai khái niệm

Chương trình dưới đây cố ý dùng tên hàm **khác nhau hoàn toàn**:

- `longestCommonSubstring`: trả **một đoạn con chung liên tiếp**, độ dài và vị trí bắt đầu của nó trong hai chuỗi.
- `longestCommonSubsequence`: trả **một dãy con chung** có độ dài tối đa, cho phép bỏ ký tự.
- `longestCommonSubsequenceLength`: chỉ trả **độ dài LCS** bằng bộ nhớ hai hàng.

**Đơn vị so khớp:** mã dùng `String.codePoints().toArray()`, tức so khớp theo **Unicode code point**, không phải đơn vị `char` UTF-16. Ví dụ emoji `😀` là **một code point** nhưng chiếm **hai `char`** trong Java. Các vị trí `startInFirst`/`startInSecond` trong kết quả là **chỉ số code point 0-based**; nếu cần chỉ số UTF-16 cho `String.substring`, phải chuyển đổi bằng `offsetByCodePoints`. Các ký tự kết hợp thành grapheme (ví dụ chữ cái cộng dấu tổ hợp) vẫn có thể gồm **nhiều code point**; chương trình **không** tự chuẩn hóa Unicode hay gộp grapheme.

Lưu đúng tên tệp **`CommonSequenceDemo.java`**, biên dịch với UTF-8:

```java
import java.util.Arrays;
import java.util.Objects;

public final class CommonSequenceDemo {
    private CommonSequenceDemo() {
    }

    public record CommonSubstring(
            String text,
            int length,
            int startInFirst,
            int startInSecond) {
        public CommonSubstring {
            Objects.requireNonNull(text, "text");
        }
    }

    // LONGEST COMMON SUBSTRING: các ký tự phải liên tiếp.
    // Vị trí trả về là chỉ số CODE POINT, không phải UTF-16 char.
    public static CommonSubstring longestCommonSubstring(
            String first, String second) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");

        int[] a = first.codePoints().toArray();
        int[] b = second.codePoints().toArray();

        int[] prev = new int[b.length + 1];
        int[] curr = new int[b.length + 1];

        int bestLen = 0;
        int bestEndA = -1;
        int bestEndB = -1;

        for (int i = 1; i <= a.length; i++) {
            Arrays.fill(curr, 0);
            for (int j = 1; j <= b.length; j++) {
                if (a[i - 1] == b[j - 1]) {
                    curr[j] = prev[j - 1] + 1;

                    if (curr[j] > bestLen) {
                        bestLen = curr[j];
                        bestEndA = i;
                        bestEndB = j;
                    }
                }
                // Nếu khác nhau: curr[j] đã là 0.
            }
            int[] temp = prev;
            prev = curr;
            curr = temp;
        }

        if (bestLen == 0) {
            return new CommonSubstring("", 0, -1, -1);
        }

        int startA = bestEndA - bestLen;
        int startB = bestEndB - bestLen;

        // Dựng theo code point, tránh cắt đôi surrogate pair.
        String text = new String(a, startA, bestLen);
        return new CommonSubstring(text, bestLen, startA, startB);
    }

    // LONGEST COMMON SUBSEQUENCE: được bỏ ký tự ở giữa.
    // Lưu bảng đầy đủ để có thể truy vết một LCS.
    public static String longestCommonSubsequence(
            String first, String second) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");

        int[] a = first.codePoints().toArray();
        int[] b = second.codePoints().toArray();
        int[][] dp = new int[a.length + 1][b.length + 1];

        for (int i = 1; i <= a.length; i++) {
            for (int j = 1; j <= b.length; j++) {
                if (a[i - 1] == b[j - 1]) {
                    dp[i][j] = dp[i - 1][j - 1] + 1;
                } else {
                    dp[i][j] = Math.max(
                        dp[i - 1][j], dp[i][j - 1]
                    );
                }
            }
        }

        int i = a.length;
        int j = b.length;
        int pos = dp[i][j];
        int[] answer = new int[pos];

        while (i > 0 && j > 0) {
            if (a[i - 1] == b[j - 1]) {
                answer[--pos] = a[i - 1];
                i--;
                j--;
            } else if (dp[i - 1][j] >= dp[i][j - 1]) {
                i--; // Khi hòa, ưu tiên đi lên.
            } else {
                j--;
            }
        }

        return new String(answer, 0, answer.length);
    }

    // Chỉ tính độ dài LCS, không dựng chuỗi.
    // Tối ưu chiều trong theo chuỗi ngắn hơn.
    public static int longestCommonSubsequenceLength(
            String first, String second) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");

        int[] a = first.codePoints().toArray();
        int[] b = second.codePoints().toArray();

        if (b.length > a.length) {
            int[] temp = a;
            a = b;
            b = temp;
        }

        int[] prev = new int[b.length + 1];
        int[] curr = new int[b.length + 1];

        for (int i = 1; i <= a.length; i++) {
            curr[0] = 0;
            for (int j = 1; j <= b.length; j++) {
                if (a[i - 1] == b[j - 1]) {
                    curr[j] = prev[j - 1] + 1;
                } else {
                    curr[j] = Math.max(prev[j], curr[j - 1]);
                }
            }
            int[] temp = prev;
            prev = curr;
            curr = temp;
        }

        return prev[b.length];
    }

    private static void showSubstring(
            String label, CommonSubstring match) {
        System.out.println(label + ": \"" + match.text()
            + "\" length=" + match.length()
            + " startA=" + match.startInFirst()
            + " startB=" + match.startInSecond());
    }

    public static void main(String[] args) {
        String a = "abcde";
        String b = "ace";

        showSubstring(
            "Contrast substring",
            longestCommonSubstring(a, b)
        );
        System.out.println("Contrast subsequence: \""
            + longestCommonSubsequence(a, b)
            + "\" length="
            + longestCommonSubsequenceLength(a, b));

        String x = "ababc";
        String y = "babca";
        showSubstring(
            "Overlap substring",
            longestCommonSubstring(x, y)
        );
        System.out.println("Overlap subsequence: \""
            + longestCommonSubsequence(x, y)
            + "\" length="
            + longestCommonSubsequenceLength(x, y));

        showSubstring(
            "Tie substring",
            longestCommonSubstring("abcXYZ", "XYZabc")
        );
        showSubstring(
            "No match",
            longestCommonSubstring("xyz", "abc")
        );
        System.out.println("No match subsequence: \""
            + longestCommonSubsequence("xyz", "abc")
            + "\"");

        showSubstring(
            "Repeated substring",
            longestCommonSubstring("aaaa", "aa")
        );

        showSubstring(
            "Unicode substring",
            longestCommonSubstring("a😀b", "😀b")
        );
        System.out.println("Unicode subsequence length: "
            + longestCommonSubsequenceLength("a😀b", "😀b"));

        System.out.println("Empty substring length: "
            + longestCommonSubstring("", "hello").length());
        System.out.println("Empty subsequence length: "
            + longestCommonSubsequenceLength("", "hello"));
    }
}
```

Dùng **JDK 17 trở lên**, lưu tệp nguồn ở mã hóa UTF-8 rồi biên dịch/chạy:

```bash
javac -encoding UTF-8 CommonSequenceDemo.java
java CommonSequenceDemo
```

**Đầu ra chuẩn:**

```text
Contrast substring: "a" length=1 startA=0 startB=0
Contrast subsequence: "ace" length=3
Overlap substring: "babc" length=4 startA=1 startB=0
Overlap subsequence: "babc" length=4
Tie substring: "abc" length=3 startA=0 startB=3
No match: "" length=0 startA=-1 startB=-1
No match subsequence: ""
Repeated substring: "aa" length=2 startA=0 startB=0
Unicode substring: "😀b" length=2 startA=1 startB=0
Unicode subsequence length: 2
Empty substring length: 0
Empty subsequence length: 0
```

### Đọc kết quả theo hợp đồng

- Với `"abcde"` và `"ace"`, đoạn con chung dài nhất chỉ có **1 code point**, còn LCS dùng được cả `a,c,e` nên dài **3**.
- Với `"ababc"` và `"babca"`, đoạn `"babc"` xuất hiện liên tiếp trong cả hai dãy, nên nó đồng thời cũng là một LCS độ dài **4**.
- `"abcXYZ"` và `"XYZabc"` có cả `"abc"` lẫn `"XYZ"` là những đoạn chung độ dài `3`. Với quy tắc cập nhật **chỉ khi lớn hơn**, chương trình giữ `"abc"` vì xuất hiện sớm hơn trong chuỗi thứ nhất.
- Không có ký tự chung thì cả LCSubstring và LCS đều có độ dài `0`. Đối với LCSubstring, vị trí `-1` là quy ước báo **không có một lần xuất hiện không rỗng**, không phải chỉ số hợp lệ.
- `"aaaa"` và `"aa"` chứa nhiều cặp vị trí trùng; một lời giải LCSubstring dài nhất là `"aa"`, kết thúc ngay ở hai ký tự đầu theo quy tắc hòa.
- `"a😀b"` có **3 code point** nhưng `String.length()` trong Java trả **4 đơn vị UTF-16**. Đoạn `"😀b"` dài **2 code point**, bắt đầu tại code point số `1` trong chuỗi đầu.
- Các đầu vào rỗng là cơ sở hợp lệ: không có đoạn/dãy con chung không rỗng nào.

## 7. Vì sao hai công thức đúng? Chứng minh bằng quy nạp

### 7.1. Chứng minh DP đoạn con chung

Ta chứng minh `suffix[i][j]` đúng bằng độ dài hậu tố chung dài nhất của `A[0..i)` và `B[0..j)`.

**Cơ sở:** nếu `i=0` hoặc `j=0`, ít nhất một tiền tố rỗng, không thể có hậu tố chung không rỗng. Giá trị `0` đúng.

**Bước quy nạp:**

- Nếu `A[i-1] != B[j-1]`, không thể có một hậu tố chung không rỗng kết thúc ở cả hai vị trí đó, nên kết quả buộc bằng `0`.
- Nếu `A[i-1] == B[j-1]`, bỏ ký tự cuối chung khỏi bất kỳ hậu tố chung không rỗng nào còn lại một hậu tố chung của hai tiền tố ngắn hơn. Ngược lại, mọi hậu tố chung của hai tiền tố ngắn hơn đều có thể được nối thêm ký tự cuối chung. Vì vậy độ dài lớn nhất bằng `suffix[i-1][j-1]+1`.

Mọi đoạn con chung `X` đều là một hậu tố chung của **cặp tiền tố kết thúc tại hai lần xuất hiện của `X`**. Do đó lấy **max trên toàn bộ bảng** tìm được độ dài đoạn chung lớn nhất, và vị trí kết thúc ghi nhận từ ô đạt max xác định một lời giải cụ thể.

### 7.2. Chứng minh DP dãy con chung

Ta chứng minh `dp[i][j]` đúng bằng độ dài LCS của hai tiền tố.

**Cơ sở:** một tiền tố rỗng chỉ có dãy con rỗng chung, nên độ dài lớn nhất bằng `0`.

**Bước quy nạp:**

- Nếu hai ký tự cuối bằng nhau, có thể chọn chúng làm phần tử cuối của một dãy con chung và nối vào LCS của hai tiền tố trước; đạt `dp[i-1][j-1]+1`. Không cần một lựa chọn tốt hơn bỏ cả hai ký tự cuối, vì khi hai ký tự bằng nhau, có thể biến một lựa chọn tối ưu thành lựa chọn dùng ký tự cuối bằng nhau mà không giảm số lượng.
- Nếu hai ký tự cuối khác nhau, một dãy con chung không thể kết thúc bằng **cả hai** ký tự cuối đang khác; vì vậy ít nhất một trong hai ký tự cuối không được chọn. Mọi lời giải tối ưu thuộc một trong hai bài toán con `dp[i-1][j]` hoặc `dp[i][j-1]`. Lấy `max` cho kết quả đúng.

Theo quy nạp, `dp[m][n]` chính là độ dài LCS của hai dãy hoàn chỉnh.

**Hệ quả:** mọi đoạn con chung đều là dãy con chung, nên luôn có:

\[
0\le L_{\text{substring}}\le L_{\text{subsequence}}\le \min(m,n).
\]

Khi dữ liệu có nhiều ký tự chung **không liên tiếp**, bất đẳng thức thứ hai có thể chênh lệch lớn.

## 8. Độ phức tạp và sử dụng bộ nhớ

Gọi `m`, `n` là **số phần tử** trong hai dãy; với chương trình trên, đó là **số Unicode code point**, không nhất thiết bằng `String.length()`.

| Nhiệm vụ | Thời gian | Bộ nhớ bảng DP | Ghi chú |
|---|---|---|---|
| LCSubstring với hai hàng như mã | `O(mn)` | `O(n)` | Theo chiều trong là `B`; giữ độ dài max và vị trí kết thúc |
| LCSubstring tối ưu hai chiều | `O(mn)` | `O(min(m,n))` | Đổi vai trò chuỗi và ánh xạ lại vị trí |
| LCS chỉ độ dài, hai hàng như mã | `O(mn)` | `O(min(m,n))` | Không trực tiếp khôi phục LCS từ hai hàng cuối |
| LCS dựng một dãy bằng bảng đầy đủ | `O(mn)` | `O(mn)` | Truy vết thêm tối đa `O(m+n)` bước |
| Vét cạn mọi đoạn con của một chuỗi | Tối đa `O(m²n)` hoặc hơn tùy cách kiểm tra | Phụ thuộc cách làm | Dễ hiểu cho đầu vào rất nhỏ, khó mở rộng |
| Liệt kê mọi dãy con | Tăng theo hàm mũ | Phụ thuộc số dãy con | Không phù hợp với đầu vào lớn |

Khi dùng `String.codePoints().toArray()`, chương trình còn cấp **hai mảng code point `O(m+n)`**, và việc tạo chuỗi kết quả dùng thêm bộ nhớ tương ứng độ dài kết quả. Vì vậy:

- Hàm `longestCommonSubstring` cần khoảng **`O(m+n)` bộ nhớ phụ** tổng cộng trong cài đặt này (hai mảng code point và hai hàng DP chiều `n`).
- Hàm `longestCommonSubsequenceLength` cũng dùng **`O(m+n)`** tổng cộng do hai mảng code point, dù **riêng bảng DP** đã tối ưu còn `O(min(m,n))`.
- Hàm `longestCommonSubsequence` dùng **`O(mn+m+n)`**, bị chi phối bởi ma trận DP khi cả hai dãy dài.

Về thời gian, chuyển chuỗi thành mảng code point mất `O(m+n)`; điền bảng mất `O(mn)`. Tổng là `O(m+n+mn)`, thường viết gọn **`O(mn)` với `m,n\ge 1`**. Không có thuật toán nào trong ba hàm trên tự chạy được cho hai chuỗi dài hàng triệu code point bằng bảng `m×n` mà vẫn tiết kiệm thời gian/bộ nhớ.

### Khi đầu vào rất lớn

Nếu cần **LCSubstring** cho dữ liệu lớn, các cấu trúc chuyên sâu như **suffix automaton**, **suffix array**, **suffix tree** hoặc tìm kiếm bằng **rolling hash** có thể hữu ích, nhưng có các đánh đổi khác nhau. Chẳng hạn suffix automaton có thể hỗ trợ tìm LCSubstring trong thời gian tuyến tính theo tổng độ dài dưới các giả định triển khai và thao tác tra cứu phù hợp; rolling hash cần xử lý rủi ro va chạm nếu muốn kết quả chắc chắn chính xác.

Với **LCS**, ngay cả khi chỉ cần độ dài, DP cơ bản vẫn tốn `O(mn)` thời gian; tối ưu hai hàng chỉ giảm **bộ nhớ**, không giảm số cặp trạng thái phải xét. Các thuật toán phụ thuộc đặc tính dữ liệu hoặc chỉ số lượng phép sửa khác nhau có thể tốt hơn ở một số ứng dụng, nhưng không phải chỉ đổi một dòng trong công thức.

## 9. Phân biệt tính liên tiếp, số lần xuất hiện và cách phá hòa

### 9.1. “Dài nhất” là độ dài, không phải số lần xuất hiện

Hai chuỗi `"aaaa"` và `"aa"` có một **nội dung** đoạn chung dài nhất là `"aa"` nhưng có nhiều **cặp vị trí xuất hiện** của nội dung này. Nếu đề yêu cầu **đếm số cặp vị trí** hay **liệt kê mọi đoạn chung dài nhất**, đó là phần việc bổ sung. Hàm `longestCommonSubstring` chỉ trả **một** nội dung đoạn và một cặp vị trí theo quy tắc hòa.

Tương tự, LCS có thể có nhiều **dãy con khác nhau** cùng độ dài tối ưu; hàm truy vết trả **một** dãy, không tự liệt kê hoặc đếm tất cả LCS.

### 9.2. Giải mã vị trí và độ dài

Trong hàm LCSubstring, `startInFirst` và `startInSecond` là **chỉ số code point** từ `0`. Hai vị trí bắt đầu cộng với `length` xác định đúng một đoạn chung. Với chuỗi Java chứa ký tự ngoài BMP, **không** đưa thẳng các chỉ số code point này vào `String.substring(int,int)` vì `substring` dùng chỉ số **UTF-16 char**.

Nếu muốn lấy đoạn bằng `substring`, hãy đổi như sau:

```java
// Mã sử dụng minh họa; giả định match.length() > 0.
int fromUtf16 = first.offsetByCodePoints(
    0, match.startInFirst()
);
int toUtf16 = first.offsetByCodePoints(
    fromUtf16, match.length()
);
String segment = first.substring(fromUtf16, toUtf16);
```

Đoạn này **không phải chương trình Java độc lập**: `first` và `match` là các biến cần được tạo từ chương trình hoàn chỉnh ở trên. Phương pháp này tránh cắt đôi hai `char` tạo nên một ký tự ngoài BMP.

### 9.3. Unicode, chuẩn hóa và đại diện ký tự

Java `String` lưu các **đơn vị mã UTF-16**. Dùng `codePoints()` giúp so khớp chính xác theo Unicode code point, không tự biến các chuỗi có hình thức hiển thị giống nhau thành cùng một chuỗi.

Ví dụ một ký tự có dấu có thể được biểu diễn bằng:

- Một code point đã được tổ hợp sẵn (precomposed).
- Một chữ cái cơ sở đi kèm **dấu kết hợp** (combining mark), gồm nhiều code point.

Hai chuỗi trông giống nhau có thể khác dãy code point, nên kết quả thuật toán vẫn phản ánh **biểu diễn thực tế**. Nếu bài toán coi hai cách biểu diễn là tương đương, nên **chuẩn hóa Unicode** (ví dụ NFC) theo hợp đồng trước khi áp dụng DP. Nếu cần so khớp theo **grapheme cluster** (đơn vị người dùng nhìn thấy), phải tách chuỗi theo grapheme thay vì chỉ code point.

### 9.4. Ký tự hoa/thường và dấu cách

Thuật toán ở đây **phân biệt chữ hoa/chữ thường**, dấu cách, dấu tiếng Việt và mọi code point khác. `"A"` và `"a"` không bằng nhau. Nếu yêu cầu không phân biệt hoa/thường hoặc bỏ khoảng trắng, phải chuẩn hóa theo quy tắc nghiệp vụ **trước khi so khớp**, đồng thời lưu ý vị trí trả về có thể không còn ánh xạ trực tiếp tới chuỗi gốc sau biến đổi độ dài.

## 10. Ứng dụng: chọn đúng khái niệm theo yêu cầu

**LCSubstring (liên tiếp)** phù hợp khi cần:

- Tìm một **đoạn văn bản nguyên vẹn** xuất hiện trong cả hai tài liệu.
- Phát hiện các vùng dữ liệu **trùng liên tiếp** trong hai luồng hoặc chuỗi.
- Tìm một **chuỗi con DNA/RNA liên tiếp** chung trong mô hình ký hiệu đơn giản.
- So khớp một phần của chuỗi mã hoặc mẫu ký tự mà **không được phép chèn/bỏ phần tử ở giữa đoạn**.

**LCS (không cần liên tiếp)** phù hợp khi cần:

- So sánh hai phiên bản tài liệu hoặc mã nguồn và giữ **trật tự** những thành phần chung dù có dòng được thêm/xóa xen giữa.
- Hình dung các đoạn chung trong một hệ thống **diff** đơn giản; nhiều công cụ thực tế còn có các tối ưu/ràng buộc khác.
- So sánh hai chuỗi hoạt động, lộ trình hay dãy sự kiện có **phần tử bỏ qua** nhưng vẫn phải giữ thứ tự.
- Đo mức tương đồng theo số phần tử có thể bảo toàn khi thực hiện các phép chèn/xóa theo một mô hình thích hợp.

Không suy diễn từ chữ “chung” rằng luôn cần LCS. Câu “hai đoạn xuất hiện **liền nhau**” gợi ý LCSubstring; câu “được phép **xóa/bỏ một số ký tự** nhưng giữ thứ tự” gợi ý LCS.

### Liên hệ với số phép chèn/xóa

Nếu chỉ cho phép **xóa** ký tự từ `A` và **chèn** ký tự để biến thành `B`, với chi phí `1` cho mỗi thao tác, số thao tác tối thiểu là:

\[
m+n-2\cdot L_{\text{subsequence}}.
\]

Giải thích: giữ lại một LCS dài `L`, xóa `m-L` ký tự không nằm trong nó từ `A` và chèn `n-L` ký tự để thu được `B`. Công thức dùng **LCS subsequence**, **không phải LCSubstring**. Nếu cho phép **thay thế** ký tự với chi phí riêng hoặc thêm các phép biến đổi khác, cần mô hình khoảng cách chỉnh sửa tương ứng; không tự dùng công thức trên.

## 11. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách khắc phục |
|---|---|---|
| Nhầm tên `substring` với `subsequence` | Dùng sai mô hình “liên tiếp” | Chốt rõ có được bỏ phần tử ở giữa không |
| LCSubstring: khi khác ký tự lại dùng `max(top,left)` | Đang thực hiện công thức LCS, cho phép nhảy qua ký tự | Đặt **`0`** khi ký tự cuối khác nhau |
| LCS: khi khác ký tự lại đặt `0` | Phá mất dãy con chung đã có trong tiền tố | Lấy **`max(dp[i-1][j],dp[i][j-1])`** |
| LCSubstring: trả `suffix[m][n]` | Bỏ đoạn chung tốt nhất kết thúc ở giữa | Theo dõi **max mọi ô** và vị trí kết thúc |
| LCS: lấy max mà không hiểu trạng thái tiền tố | Khó truy vết và dễ cài đặt sai | LCS độ dài trả **`dp[m][n]`** |
| Quên hàng/cột cơ sở `0` | Truy cập ngoài mảng, lệch ký tự đầu | Dùng bảng kích thước `(m+1)×(n+1)` |
| Nhầm `i` với `i-1` khi đọc ký tự | So sánh sai hoặc `IndexOutOfBoundsException` | `i` là độ dài tiền tố; ký tự cuối là `A[i-1]` |
| LCSubstring dùng một hàng nhưng lấy giá trị trái **đã cập nhật** | Tạo độ dài giả lớn hơn độ dài chuỗi | Dùng hai hàng hoặc bảo toàn giá trị chéo cũ |
| Quên reset ô LCSubstring khi khác ký tự | Mang độ dài của đoạn khớp cũ sang đoạn mới không liên tiếp | Gán `0` ở mỗi mismatch |
| Chỉ lưu độ dài nhưng đề yêu cầu một đoạn cụ thể | Không đủ dữ liệu dựng chuỗi | Lưu vị trí kết thúc khi cập nhật max |
| Truy vết LCS chỉ bằng hai hàng cuối như bảng đầy đủ | Thiếu lịch sử quyết định | Lưu ma trận hoặc dùng thuật toán truy vết tiết kiệm bộ nhớ |
| Tin rằng LCS luôn duy nhất | Có thể có nhiều kết quả cùng độ dài | Định nghĩa tie-break hoặc chấp nhận bất kỳ LCS hợp lệ |
| Dùng `String.length()` làm số code point | Sai độ dài/vị trí đối với emoji và ký tự ngoài BMP | Phân biệt UTF-16 với code point; dùng `codePoints()` khi cần |
| Dùng chỉ số code point trực tiếp trong `substring` | Có thể cắt sai hoặc vào giữa surrogate pair | Dùng `offsetByCodePoints` |
| Chưa thống nhất chuẩn hóa/chữ hoa-dấu | Chuỗi hiển thị giống nhau vẫn có thể so sánh khác | Chuẩn hóa theo hợp đồng |
| Cấp bảng `O(mn)` cho đầu vào rất lớn mà không dự trù RAM | Hết bộ nhớ trước khi tính xong | Cân nhắc hai hàng, thuật toán khác hoặc giới hạn bài toán |

## 12. Kiểm thử đúng tính liên tiếp và thứ tự

Một bộ kiểm thử nên bao gồm những tình huống **phân biệt được hai thuật toán**, không chỉ các chuỗi giống nhau:

1. **Một chuỗi rỗng:** cả LCSubstring và LCS đều có độ dài `0`.
2. **Không có ký tự chung:** trả độ dài `0` và chuỗi rỗng.
3. **Hai chuỗi bằng nhau:** cả hai độ dài bằng độ dài dãy; riêng LCSubstring phải trả toàn bộ chuỗi.
4. **Các ký tự chung bị ngắt quãng:** `A="abcde",B="ace"` → LCSubstring `1`, LCS `3`.
5. **Đoạn chung ở giữa:** `A="xxabcY",B="zzabcZ"` → LCSubstring `"abc"` dài `3`, không được chỉ đọc ô cuối cùng.
6. **Nhiều nghiệm tối ưu:** `A="abcXYZ",B="XYZabc"` → có hai đoạn chung dài `3`; kiểm tra quy tắc hòa nếu yêu cầu đầu ra xác định.
7. **Nhiều bản sao:** `"aaaa"` và `"aa"` → LCSubstring `2`; không nhầm số lần xuất hiện thành độ dài.
8. **Đảo trật tự:** `"ab"` và `"ba"` → không có dãy chung độ dài `2`, vì không thể đảo thứ tự; LCSubstring và LCS đều chỉ dài `1`.
9. **Unicode ngoài BMP:** `"a😀b"` và `"😀b"` → đoạn chung dài `2` **code point**, không phải `3` đơn vị UTF-16.
10. **Chữ hoa, dấu kết hợp và chuẩn hóa:** xác định chính xác đơn vị so sánh và hợp đồng tương đương.

### Kiểm thử đối chứng bằng vét cạn cho chuỗi ngắn

Để kiểm tra độc lập một cài đặt DP, với chuỗi ngắn có thể làm cách chậm:

- **LCSubstring:** liệt kê mọi đoạn con liên tiếp của `A` và kiểm tra đoạn đó có xuất hiện liên tiếp trong `B` không; lấy độ dài lớn nhất.
- **LCS:** liệt kê mọi dãy con của `A`, kiểm tra có xuất hiện theo thứ tự (được bỏ ký tự) trong `B` không; lấy độ dài lớn nhất. Cách này có thể cần tới `2^m` dãy con.

So sánh độ dài của hai cách chậm với DP trên các cặp chuỗi được sinh ngẫu nhiên từ một bảng chữ cái nhỏ (ví dụ `a,b,c`) để thường xuyên tạo trùng, hòa và đoạn bị gián đoạn. Với phiên bản dựng chuỗi, còn phải kiểm tra:

- Độ dài chuỗi trả về bằng độ dài DP.
- LCSubstring thực sự **liên tiếp** trong cả hai chuỗi.
- LCS thực sự là **dãy con** theo thứ tự trong cả hai chuỗi.
- Các vị trí bắt đầu do LCSubstring trả về trỏ đúng tới nội dung kết quả.

Kiểm thử có thể bắt lỗi triển khai, nhưng **định nghĩa trạng thái và chứng minh quy nạp** mới lý giải tại sao thuật toán đúng cho mọi đầu vào hợp lệ.

## 13. Bài tập tự luyện

**Bài 1 — Định nghĩa.** Cho `A="abcde"` và `B="ace"`. Tìm độ dài LCSubstring và LCS. Vì sao `"ace"` không phải LCSubstring?

*Đáp án:* LCSubstring bằng **`1`**, LCS bằng **`3`**. Trong `A`, `a`, `c`, `e` không nằm liền nhau.

**Bài 2 — Công thức.** Với `A[i-1]!=B[j-1]`, hãy viết công thức `suffix[i][j]` cho đoạn con chung và `dp[i][j]` cho dãy con chung.

*Đáp án:* `suffix[i][j]=0`; còn `dp[i][j]=max(dp[i-1][j],dp[i][j-1])`.

**Bài 3 — Max ở đâu?** Cho `A="abcX"` và `B="abcY"`. LCSubstring có độ dài bao nhiêu? Giá trị hậu tố chung `suffix[4][4]` bằng bao nhiêu?

*Đáp án:* LCSubstring dài **`3`** (`"abc"`), trong khi `suffix[4][4]=0` vì `X!=Y`. Vì vậy phải lấy max toàn bộ bảng LCSubstring.

**Bài 4 — Truy vết.** Nếu `suffix[7][9]=4` và đó là giá trị tốt nhất, đoạn con chung nằm ở khoảng chỉ số nửa mở nào của hai dãy?

*Đáp án:* trong `A` là `[7-4,7)=[3,7)`; trong `B` là `[9-4,9)=[5,9)`.

**Bài 5 — Nhiều đáp án.** Cho `A="abcXYZ"`, `B="XYZabc"`. Kể tên hai đoạn con chung cùng dài `3`. Nếu quét `i` rồi `j` tăng dần và chỉ cập nhật khi lớn hơn, đoạn nào được giữ?

*Đáp án:* `"abc"` và `"XYZ"`. Quy tắc trên giữ `"abc"` vì nó kết thúc sớm hơn trong `A`.

**Bài 6 — LCS và phép chèn/xóa.** Nếu `A="abcde"`, `B="ace"`, chỉ được chèn hoặc xóa ký tự với chi phí `1`, cần tối thiểu bao nhiêu thao tác để đổi `A` thành `B`?

*Đáp án:* LCS dài `3`, nên `5+3-2×3=2` thao tác; xóa `b` và `d`. Không dùng độ dài LCSubstring bằng `1` trong công thức.

**Bài 7 — Một hàng DP.** Vì sao cập nhật `curr[j]` cho LCSubstring từ `curr[j-1]` là sai? Cho một phản ví dụ ngắn.

*Đáp án gợi ý:* ô cần dùng phải là `prev[j-1]`. Với `A="a",B="aa"`, nếu cập nhật từ trái sang phải theo giá trị của hàng hiện tại, có thể tính sai độ dài `2` dù `A` chỉ dài `1`.

**Bài 8 — Unicode.** `String.length()` của `"a😀b"` là bao nhiêu? Có bao nhiêu Unicode code point? Nếu LCSubstring trả `startInFirst=1` theo code point thì có thể dùng trực tiếp `substring(1,3)` để lấy `"😀b"` không?

*Đáp án:* `String.length()=4` đơn vị UTF-16, có **`3` code point**. Không nên dùng trực tiếp chỉ số code point như chỉ số UTF-16; dùng `offsetByCodePoints` hoặc dựng lại từ mảng code point.

**Bài 9 — Tự mở rộng.** Viết hàm chỉ trả độ dài LCSubstring với bộ nhớ `O(min(m,n))`, rồi viết thêm phiên bản LCS chỉ trả độ dài với hai hàng. Kiểm tra hai kết quả trên chuỗi rỗng, chuỗi lặp và nhiều cặp ngẫu nhiên. Với LCS cần dựng lại chuỗi, hãy giải thích vì sao phiên bản hai hàng đơn giản không đủ thông tin truy vết trực tiếp.

## Ghi nhớ

**Đoạn con chung dài nhất (LCSubstring) đòi hỏi liên tiếp; dãy con chung dài nhất (LCS) chỉ đòi hỏi giữ thứ tự.** Đây là hai bài toán khác nhau:

- LCSubstring: `suffix[i][j]=suffix[i-1][j-1]+1` khi hai ký tự cuối bằng nhau, **nếu khác thì bằng `0`**; lấy **max toàn bộ bảng** và ghi vị trí kết thúc.
- LCS: `dp[i][j]=dp[i-1][j-1]+1` khi bằng nhau, **nếu khác thì lấy `max` của hai tiền tố bỏ một ký tự cuối**; đáp án độ dài ở **`dp[m][n]`**.

Cả hai công thức cơ bản dùng `O(mn)` thời gian. LCSubstring dựng một đoạn cụ thể bằng **hai hàng DP** và vị trí kết thúc; LCS dựng một dãy con cụ thể dễ nhất với **toàn bảng DP**, còn chỉ tính độ dài có thể tối ưu bằng hai hàng. Khi cài đặt Java, hãy làm rõ **ký tự UTF-16, code point, quy tắc hòa và yêu cầu giữ liên tiếp** trước khi chọn công thức.
