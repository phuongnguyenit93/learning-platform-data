# Dãy con đối xứng dài nhất (Longest Palindromic Subsequence)

> **Chủ đề:** Computer Science Algorithms → Quy hoạch động dãy.  
> **Mục tiêu:** Phân biệt *dãy con* với *đoạn con* đối xứng; thiết kế DP trên đoạn `dp[i][j]`, chứng minh quan hệ chuyển, tính độ dài và dựng lại một đáp án, tối ưu bộ nhớ khi chỉ cần độ dài, xử lý đầu vào rỗng/Unicode, và nhận biết các bài toán liên quan. Ví dụ sử dụng Java 17+.

## 1. Định nghĩa chính xác của bài toán

Cho dãy ký hiệu `s` dài `n`, tìm một **dãy con đối xứng dài nhất** (*longest palindromic subsequence*, viết tắt **LPS**).

- **Dãy con (*subsequence*)** được hình thành bằng cách chọn một số vị trí trong dãy gốc, **giữ nguyên thứ tự tương đối**. Các vị trí được chọn **không cần liên tiếp**.
- **Đối xứng (*palindromic*)** nghĩa là đọc từ trái sang phải và từ phải sang trái nhận cùng dãy ký hiệu. Ví dụ `"abba"`, `"aba"`, `"x"`, và dãy rỗng đều đối xứng.
- **Dài nhất** nghĩa là cực đại số ký hiệu được chọn. Nếu có nhiều dãy con cùng độ dài tối ưu, đề bài thường cho phép trả **một đáp án bất kỳ**; muốn kết quả từ điển nhỏ nhất hoặc liệt kê tất cả đáp án phải bổ sung yêu cầu riêng.

Bài có hai dạng output thường gặp:

1. Chỉ trả **độ dài** LPS.
2. Trả **một dãy con đối xứng** đạt độ dài đó, đôi khi cần cả danh sách vị trí gốc.

Ví dụ:

```text
s = "bbbab"
Vị trí 0-based: 0 1 2 3 4
Ký tự:          b b b a b

Chọn các vị trí: 0, 1, 2, 4
Dãy con:         b  b  b  b  → "bbbb"
Độ dài LPS:      4
```

Không thể có dãy con dài 5, bởi toàn chuỗi `"bbbab"` không đối xứng. Vì đã tìm được dãy đối xứng dài 4, độ dài tối ưu là 4.

### 1.1. Phân biệt với đoạn con đối xứng dài nhất

**Đoạn con (*substring*)** phải gồm **các ký hiệu liên tiếp**. Với `"bbbab"`:

- LPS là `"bbbb"` (vị trí `0,1,2,4`), dài **4**.
- Đoạn con đối xứng liên tiếp dài nhất là `"bbb"` (vị trí `0..2`), dài **3**.

Vì vậy không thể dùng nguyên thuật toán **mở rộng từ tâm** hay Manacher dành cho *substring* rồi khẳng định đã giải LPS. LPS thuộc dạng **DP trên đoạn với quyền bỏ ký hiệu**, không phải bài tìm chuỗi liên tiếp.

| Input | Một LPS | Độ dài LPS | Một đoạn con đối xứng dài nhất |
|---|---|---:|---|
| `"bbbab"` | `"bbbb"` | 4 | `"bbb"` (3) |
| `"cbbd"` | `"bb"` | 2 | `"bb"` (2) |
| `"character"` | `"carac"` | 5 | `"ara"` (3) |
| `"agbdba"` | `"abdba"` | 5 | `"bdb"` (3) |
| `"racecar"` | `"racecar"` | 7 | `"racecar"` (7) |
| `"abc"` | Một ký hiệu như `"a"` | 1 | Một ký hiệu dài 1 |
| `""` | `""` | 0 | `""` |

Một dãy đơn lẻ như `"a"` luôn đối xứng, nên với input **không rỗng**, LPS có độ dài **ít nhất 1**. Với input rỗng, độ dài LPS bằng **0**.

### 1.2. Thứ gì đang được tính là một “ký hiệu”?

Trong các công thức, `n` là số **phần tử của dãy được tối ưu**. Nếu dãy là số nguyên, phần tử là số nguyên; nếu dãy là chuỗi, cần xác định “ký tự” nghĩa là gì.

Trong Java:

- `String.length()` đếm **đơn vị mã UTF-16**.
- `charAt(i)` lấy một **đơn vị UTF-16**; một ký tự ngoài Basic Multilingual Plane như `"😀"` được lưu bằng **cặp surrogate**, tức hai `char`.
- `String.codePoints().toArray()` cung cấp mảng **Unicode code point**. Các ví dụ Java chính dùng mảng này, nên độ dài LPS được tính theo **code point**, không cắt đôi surrogate pair.
- Một **cụm ký tự người dùng nhìn thấy** (*grapheme cluster*) vẫn có thể gồm nhiều code point, ví dụ chữ cái đi kèm dấu kết hợp. Nếu bài yêu cầu đối xứng theo *grapheme* hay theo ngữ nghĩa ngôn ngữ, phải tách cụm và chuẩn hóa phù hợp trước khi chạy DP.

Dữ liệu ASCII đơn giản thì các cách đếm trên trùng nhau. Khi so sánh Unicode, cần nêu rõ có phân biệt chữ hoa/chữ thường và có chuẩn hóa `NFC`/`NFD` hay không. Thuật toán so sánh **giá trị phần tử đúng như đầu vào đã biểu diễn**, không tự thực hiện collation theo ngôn ngữ.

## 2. Thiết kế trạng thái: quy hoạch động trên đoạn

Ta định nghĩa trên mảng ký hiệu `a[0..n-1]`:

> `dp[i][j]` là **độ dài dãy con đối xứng dài nhất nằm hoàn toàn trong đoạn bao gồm hai đầu mút** `a[i..j]`.

Đây là bài toán tối ưu **trong một khoảng chỉ số**, nên gọi là **interval DP**.

Phần còn lại là suy ra `dp[i][j]` từ các đoạn **ngắn hơn**. Xét hai ký hiệu ở hai đầu:

- `a[i]` ở đầu trái.
- `a[j]` ở đầu phải.

Ta sẽ dùng ba loại trạng thái:

1. **Đoạn rỗng** `i>j`: giá trị **0**.
2. **Đoạn một phần tử** `i==j`: giá trị **1**.
3. **Đoạn có ít nhất hai phần tử** `i<j`: xét bằng nhau/khác nhau ở hai đầu.

Không phải lúc nào cũng tạo bảng chứa một ô cho đoạn rỗng; công thức có thể xử lý riêng trường hợp đó bằng giá trị 0.

### 2.1. Quan hệ chuyển khi hai đầu bằng nhau

Nếu `a[i] == a[j]` và `i<j`, ta có thể đặt hai ký hiệu bằng nhau ở **hai đầu của một palindrome**, rồi chọn một LPS của đoạn ở giữa.

Công thức:

`dp[i][j] = 2 + dp[i+1][j-1]`.

Nếu `j=i+1`, đoạn trong rỗng nên `dp[i+1][j-1]=0`; kết quả là **2**. Đây là trường hợp hai ký hiệu kề nhau bằng nhau như `"bb"`.

**Ví dụ:**

```text
a[i..j] = "abca"
Hai đầu: a ... a (bằng nhau)
Đoạn giữa: "bc" → LPS dài 1
Ghép hai đầu: "aba" hoặc "aca" → LPS dài 3.
```

Điểm tinh tế: tại sao khi hai đầu bằng nhau ta được **luôn** ghép cả hai, thay vì còn phải lấy `max` với trường hợp bỏ một đầu? Phần 4 sẽ chứng minh. Quy tắc trên không chỉ là một heuristic.

### 2.2. Quan hệ chuyển khi hai đầu khác nhau

Nếu `a[i] != a[j]`, không có palindrome subsequence nào vừa **chọn `a[i]` làm đầu trái** vừa **chọn `a[j]` làm đầu phải**: hai ký hiệu ấy không bằng nhau.

Vì vậy mọi palindrome subsequence hợp lệ phải **bỏ ít nhất một trong hai đầu**:

- Bỏ `a[i]` ⇒ nằm trong đoạn `a[i+1..j]`.
- Bỏ `a[j]` ⇒ nằm trong đoạn `a[i..j-1]`.

Ta chọn độ dài lớn hơn:

`dp[i][j] = max(dp[i+1][j], dp[i][j-1])`.

Như vậy công thức đầy đủ là:

```text
LPS(i, j) =
    0                              nếu i > j
    1                              nếu i == j
    2 + LPS(i+1, j-1)              nếu i < j và a[i] == a[j]
    max(LPS(i+1,j), LPS(i,j-1))    nếu i < j và a[i] != a[j]
```

### 2.3. Câu trả lời cuối nằm ở đâu?

Nếu `n=0`, đáp án là **0** và không được truy cập `dp[0][-1]`.

Nếu `n>0`, toàn dãy là đoạn `a[0..n-1]`, nên:

`LPS length = dp[0][n-1]`.

Đối với yêu cầu trả dãy con thực tế, cần dùng bảng này để **truy vết** từ `(0,n-1)` hoặc lưu thêm quyết định.

## 3. Thứ tự tính: đoạn nhỏ trước, đoạn lớn sau

Cả ba trạng thái trong chuyển đều nhỏ hơn đoạn hiện tại:

- `(i+1, j-1)`: ngắn hơn 2.
- `(i+1, j)`: ngắn hơn 1.
- `(i, j-1)`: ngắn hơn 1.

Vì vậy có thể tính theo **độ dài đoạn tăng dần**.

### 3.1. Cách A: duyệt độ dài

```text
for i = 0..n-1:
    dp[i][i] = 1

for len = 2..n:
    for i = 0..n-len:
        j = i + len - 1
        if a[i] == a[j]:
            inside = (len == 2) ? 0 : dp[i+1][j-1]
            dp[i][j] = inside + 2
        else:
            dp[i][j] = max(dp[i+1][j], dp[i][j-1])
```

Cách này trực tiếp thể hiện “đoạn ngắn hơn được giải trước”.

### 3.2. Cách B: duyệt `i` giảm, `j` tăng

```text
for i = n-1 downto 0:
    dp[i][i] = 1
    for j = i+1..n-1:
        if a[i] == a[j]:
            dp[i][j] = 2 + (i+1 <= j-1 ? dp[i+1][j-1] : 0)
        else:
            dp[i][j] = max(dp[i+1][j], dp[i][j-1])
```

Khi xét `(i,j)`:

- Hàng `i+1` đã được tính vì `i` giảm.
- Ô `(i,j-1)` đã được tính vì `j` tăng trên hàng `i`.
- Đường chéo `(i+1,j-1)` cũng đã có, nếu đoạn giữa không rỗng.

Đây là cách dùng trong ví dụ Java 2D của bài.

**Lỗi phổ biến:** duyệt `i` từ 0 lên n-1 và `j` từ i+1 lên n-1 thì `dp[i+1][j]` **chưa** được tính, nhưng mặc định mảng Java `int` chứa 0; code có thể chạy và cho kết quả sai âm thầm.

## 4. Chứng minh quan hệ chuyển tối ưu

Không đủ để thấy công thức “có vẻ hợp lý”. Ta cần chứng minh với **mọi** đoạn, công thức trả độ dài tối ưu.

### 4.1. Trường hợp cơ sở

Đoạn rỗng không chứa ký hiệu nào, nên LPS có độ dài 0.

Đoạn một ký hiệu luôn có palindrome chính là ký hiệu ấy, nên LPS có độ dài 1.

### 4.2. Hai đầu khác nhau: loại trừ đầy đủ

Nếu `a[i] != a[j]`, một palindrome subsequence chọn **cả hai đầu làm đầu/cuối** sẽ có ký hiệu đầu và cuối không bằng nhau, mâu thuẫn định nghĩa palindrome.

Vì vậy mỗi palindrome subsequence của đoạn phải nằm **ít nhất trong một** trong hai đoạn `(i+1,j)` hoặc `(i,j-1)`. Lấy `max` giữa hai tối ưu con không bỏ sót ứng viên, và mỗi ứng viên con đều là một dãy con hợp lệ của đoạn lớn.

Do đó:

`LPS(i,j)=max(LPS(i+1,j),LPS(i,j-1))`.

### 4.3. Hai đầu bằng nhau: chứng minh ghép cả hai là tối ưu

Giả sử `a[i] == a[j]`, `i<j`, và gọi `M=LPS(i+1,j-1)`.

**Chặn dưới:** lấy một palindrome tối ưu của đoạn trong dài M, ghép `a[i]` bên trái và `a[j]` bên phải. Vì hai ký hiệu bằng nhau, kết quả vẫn đối xứng và là dãy con của đoạn lớn, dài `M+2`. Vậy `LPS(i,j) >= M+2`.

**Chặn trên:** lấy một palindrome subsequence bất kỳ của đoạn lớn, dài `L`.

- Nếu `L<=1`, hiển nhiên `L<=M+2`.
- Nếu `L>=2`, bỏ **ký hiệu đầu và ký hiệu cuối được chọn** trong dãy palindrome ấy; phần còn lại vẫn là một palindrome dài `L-2`.
- Hai ký hiệu đã bỏ là **hai vị trí cực biên được chọn**, nên tất cả vị trí còn lại nằm **bên trong đoạn `(i+1..j-1)`**, bất kể dãy ban đầu có thật sự dùng `i` hay `j` hay không.
- Theo định nghĩa M là tối ưu của đoạn trong, `L-2<=M`, suy ra `L<=M+2`.

Vậy mọi ứng viên đều có độ dài tối đa M+2, và ta đã xây được một ứng viên độ dài M+2. Kết luận:

`LPS(i,j)=M+2`.

Lập luận này giải thích **vì sao công thức với hai đầu bằng nhau không cần thử bỏ một đầu**.

### 4.4. Quy nạp theo độ dài đoạn

Giả sử mọi đoạn ngắn hơn `len` đã có giá trị đúng. Với một đoạn dài `len`:

- Nếu hai đầu bằng nhau, công thức ở phần 4.3 là đúng nhờ tối ưu đoạn trong đã biết.
- Nếu hai đầu khác nhau, công thức ở phần 4.2 là đúng nhờ tối ưu hai đoạn bớt một đầu đã biết.

Do đó đoạn hiện tại được tính đúng. Bắt đầu từ đoạn rỗng và một phần tử, quy nạp cho mọi đoạn tới độ dài n chứng minh `dp[0][n-1]` là độ dài tối ưu.

Thuật toán dừng vì có hữu hạn `O(n²)` ô, mỗi ô thực hiện `O(1)` thao tác cơ bản trên ký hiệu đã biểu diễn thành số nguyên.

## 5. Truy vết một dãy con đối xứng dài nhất

Nếu bài yêu cầu **chuỗi thực tế**, không chỉ độ dài, ta bắt đầu từ toàn đoạn `(i=0,j=n-1)` và đi ngược theo các quyết định đã xác định `dp[i][j]`.

Đặt:

- `length = dp[0][n-1]`.
- Một mảng kết quả có đúng `length` phần tử.
- Hai vị trí ghi `left=0` và `right=length-1`.

Xử lý:

1. Nếu `i==j`, ghi ký hiệu giữa vào `result[left]` rồi dừng.
2. Nếu `a[i]==a[j]` và `i<j`, ghi `a[i]` vào **đầu trái** và `a[j]` vào **đầu phải** của kết quả; tăng `i`, giảm `j`.
3. Nếu `a[i]!=a[j]`, so sánh `dp[i+1][j]` với `dp[i][j-1]`. Bỏ phía có giá trị tối ưu nhỏ hơn; khi bằng nhau có thể chọn một bên nhất quán.
4. Lặp cho đến khi khoảng rỗng hoặc chỉ còn một ký hiệu.

Vì các cặp bằng nhau luôn được viết vào **hai đầu đối xứng**, kết quả cuối đọc hai chiều giống nhau. Mỗi ký hiệu được lấy từ một vị trí có thứ tự tăng dần của input, nên là **dãy con hợp lệ**.

### 5.1. Không nhầm vị trí chỉ số và số ký hiệu kết quả

Biến `i,j` là chỉ số **trên input**; `left,right` là chỉ số **trên output**. Hai cặp này thay đổi với tốc độ khác nhau khi bỏ ký hiệu.

Nếu dùng mảng `result` cố định:

```text
input:          b b b a b
output ban đầu: _ _ _ _
ghép b đầu/cuối:
                b _ _ b
xét phần giữa:
                b b b b
```

Với LPS có độ dài lẻ, bước cuối cùng ghi **một ký hiệu ở giữa**, không ghi cặp hai lần.

### 5.2. Hòa giữa hai cách bỏ đầu

Khi `a[i]!=a[j]` và `dp[i+1][j]==dp[i][j-1]`, cả hai nhánh đều có thể dẫn tới LPS tối ưu. Nếu chỉ cần **một nghiệm**, có thể đặt quy tắc cố định:

- Hòa thì **bỏ ký hiệu bên trái** (`i++`).

Quy tắc này giúp code chạy xác định, nhưng **không bảo đảm LPS nhỏ nhất theo thứ tự từ điển**. Muốn nghiệm từ điển nhỏ nhất, phải định nghĩa thứ tự ký hiệu và thiết kế thêm cách chọn/truy vết phù hợp; không thể chỉ đổi `>=` thành `>` mà mặc nhiên đúng.

## 6. Java 17: DP 2D và dựng lại một LPS

Lưu thành **LongestPalindromicSubsequenceDemo.java**:

```java
import java.util.Objects;

public class LongestPalindromicSubsequenceDemo {
    record Result(int length, String subsequence) {}

    static Result solve(String text) {
        Objects.requireNonNull(text, "text");

        // Mỗi phần tử là một Unicode code point.
        int[] a = text.codePoints().toArray();
        int n = a.length;
        if (n == 0) {
            return new Result(0, "");
        }

        int[][] dp = new int[n][n];

        // i giảm, j tăng: các đoạn con đã được tính trước.
        for (int i = n - 1; i >= 0; i--) {
            dp[i][i] = 1;
            for (int j = i + 1; j < n; j++) {
                if (a[i] == a[j]) {
                    int inside = (i + 1 < j) ? dp[i + 1][j - 1] : 0;
                    dp[i][j] = inside + 2;
                } else {
                    dp[i][j] = Math.max(dp[i + 1][j], dp[i][j - 1]);
                }
            }
        }

        int length = dp[0][n - 1];
        int[] result = new int[length];
        int left = 0, right = length - 1;
        int i = 0, j = n - 1;

        while (i <= j) {
            if (i == j) {
                result[left] = a[i];
                break;
            }

            if (a[i] == a[j]) {
                result[left++] = a[i];
                result[right--] = a[j];
                i++;
                j--;
            } else if (dp[i + 1][j] >= dp[i][j - 1]) {
                i++;   // Quy tắc hòa: bỏ trái.
            } else {
                j--;
            }
        }

        return new Result(length, new String(result, 0, length));
    }

    public static void main(String[] args) {
        Result x = solve("bbbab");
        System.out.println("bbbab: " + x.subsequence()
                + " (length " + x.length() + ")");

        Result y = solve("character");
        System.out.println("character: " + y.subsequence()
                + " (length " + y.length() + ")");

        Result z = solve("cbbd");
        System.out.println("cbbd: " + z.subsequence()
                + " (length " + z.length() + ")");

        Result empty = solve("");
        System.out.println("empty: [" + empty.subsequence()
                + "] (length " + empty.length() + ")");

        // Kiểm tra có một code point ngoài BMP.
        System.out.println("emoji code-point length: "
                + solve("\uD83D\uDE00a\uD83D\uDE00").length());
    }
}
```

Biên dịch và chạy (Java 17 trở lên):

```bash
javac -encoding UTF-8 LongestPalindromicSubsequenceDemo.java
java LongestPalindromicSubsequenceDemo
```

Stdout chính xác:

```text
bbbab: bbbb (length 4)
character: carac (length 5)
cbbd: bb (length 2)
empty: [] (length 0)
emoji code-point length: 3
```

**Giải thích:**

- `"bbbab"` chọn bốn ký hiệu `b`, bỏ `a`.
- `"character"` tạo `"carac"`, có hai phía đối xứng qua `r`.
- `"cbbd"` chọn `"bb"`.
- Chuỗi rỗng trả `Result(0,"")`, không truy cập mảng DP âm.
- Đoạn ký tự Unicode được ghi dưới dạng escape `\uD83D\uDE00` cho một emoji trong **mã nguồn Java**; Java hiểu đây là cặp surrogate hợp lệ, còn `codePoints()` gom thành **một** phần tử để xử lý.

`new String(int[] codePoints, int offset, int count)` tạo chuỗi từ các **code point** đã chọn, không giả định mỗi ký hiệu chiếm một `char`. Vì vậy kết quả không bị cắt giữa hai đơn vị UTF-16 của một code point ngoài BMP.

**Độ phức tạp:** có `n(n+1)/2` đoạn không rỗng, mỗi ô được tính trong `O(1)`. Thời gian **`O(n²)`**, bộ nhớ DP **`O(n²)`**, cộng `O(n)` cho mảng code point và output dài không quá n. Phần truy vết tối đa `O(n)` bước. `n` trong phân tích là **số code point** của chuỗi, không phải nhất thiết là `text.length()`.

**Đầu vào và lỗi:** `text == null` bị từ chối bằng `Objects.requireNonNull`. Nếu n rất lớn, tạo `int[n][n]` có thể hết bộ nhớ; giải pháp nén ở phần 8 chỉ trả **độ dài**, còn nếu cần dãy con có thể phải dùng chiến lược lưu/truy vết khác.

## 7. Truy vết cụ thể trên `bbbab`

Gán chỉ số `0..4`:

```text
         j=0 j=1 j=2 j=3 j=4
          b   b   b   a   b
i=0 b     1   2   3   3   4
i=1 b         1   2   2   3
i=2 b             1   1   3
i=3 a                 1   1
i=4 b                     1
```

Các ô bên dưới đường chéo không dùng, có thể hiểu là đoạn rỗng khi `i>j`. Cách tính một số ô:

- `dp[2][4]` ứng với `"bab"`: hai đầu đều `b`, nên `2+dp[3][3]=3`.
- `dp[1][3]` ứng với `"bba"`: hai đầu `b` và `a` khác nhau, lấy `max(dp[2][3]=1, dp[1][2]=2)=2`.
- `dp[0][4]` ứng với `"bbbab"`: hai đầu `b`, nên `2+dp[1][3]=4`.

Đi từ `(0,4)`:

1. `b == b`: ghi cặp `b...b`, chuyển đến `(1,3)`.
2. `b != a`: so `dp[2][3]=1` với `dp[1][2]=2`; bỏ `a` ở vị trí 3, còn `(1,2)`.
3. `b == b`: ghi cặp `bb` vào giữa, kết thúc.

Kết quả là `"bbbb"`, độ dài 4.

**Lưu ý:** cùng một độ dài tối ưu có thể có nhiều **bộ chỉ số được chọn** hoặc nhiều **chuỗi ký hiệu tối ưu**. Bảng chỉ lưu độ dài, không đếm số cách và không đảm bảo liệt kê toàn bộ LPS.

## 8. Tối ưu bộ nhớ xuống `O(n)` khi chỉ cần độ dài

Bảng 2D `dp[i][j]` rất rõ nghĩa nhưng tốn `O(n²)` bộ nhớ. Nếu bài chỉ hỏi **độ dài** LPS, có thể dùng một mảng `dp[j]` và một biến lưu đường chéo.

Duyệt `i` **giảm** từ `n-1` về 0. Trước khi bắt đầu cập nhật hàng `i`:

- Với `j>i`, `dp[j]` còn lưu giá trị **hàng trước** `LPS(i+1,j)`.
- Sau khi đã cập nhật `dp[j-1]` trong vòng j tăng, `dp[j-1]` lưu giá trị **hàng hiện tại** `LPS(i,j-1)`.
- Biến `previousDiagonal` giữ giá trị **hàng trước, cột trước** `LPS(i+1,j-1)` trước khi nó bị ghi đè.

### 8.1. Công thức 1D và bất biến

```text
for i = n-1 downto 0:
    dp[i] = 1
    previousDiagonal = 0  // Đoạn giữa rỗng khi j=i+1.
    for j = i+1..n-1:
        old = dp[j]        // Giá trị LPS(i+1,j).
        if a[i] == a[j]:
            dp[j] = previousDiagonal + 2
        else:
            dp[j] = max(dp[j], dp[j-1])
        previousDiagonal = old

answer = (n == 0) ? 0 : dp[n-1]
```

Tại vòng `j`:

| Biến | Nghĩa ngay trước khi cập nhật |
|---|---|
| `dp[j]` | `LPS(i+1,j)` của hàng trước |
| `dp[j-1]` | `LPS(i,j-1)` của hàng hiện tại |
| `previousDiagonal` | `LPS(i+1,j-1)` của hàng trước |
| `old` | Bản sao của `dp[j]` trước khi ghi để dùng làm đường chéo ở lượt j+1 |

Nếu viết `previousDiagonal = dp[j]` **sau khi đã cập nhật** mà không lưu `old`, ta lấy nhầm **hàng hiện tại** thay vì đường chéo hàng trước, làm công thức sai. Đây là lỗi rất phổ biến khi nén interval DP.

### 8.2. Java 17: tính độ dài bằng một mảng

Lưu thành **LpsLengthOptimizedDemo.java**:

```java
import java.util.Objects;

public class LpsLengthOptimizedDemo {
    static int length(String text) {
        Objects.requireNonNull(text, "text");
        int[] a = text.codePoints().toArray();
        int n = a.length;
        if (n == 0) {
            return 0;
        }

        int[] dp = new int[n];

        for (int i = n - 1; i >= 0; i--) {
            dp[i] = 1;
            int previousDiagonal = 0;

            for (int j = i + 1; j < n; j++) {
                int old = dp[j];

                if (a[i] == a[j]) {
                    dp[j] = previousDiagonal + 2;
                } else {
                    dp[j] = Math.max(dp[j], dp[j - 1]);
                }

                previousDiagonal = old;
            }
        }
        return dp[n - 1];
    }

    public static void main(String[] args) {
        System.out.println("agbdba: " + length("agbdba"));
        System.out.println("abc: " + length("abc"));
        System.out.println("banana: " + length("banana"));
        System.out.println("empty: " + length(""));
        System.out.println("emoji code points: "
                + length("\uD83D\uDE00a\uD83D\uDE00"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LpsLengthOptimizedDemo.java
java LpsLengthOptimizedDemo
```

Stdout:

```text
agbdba: 5
abc: 1
banana: 5
empty: 0
emoji code points: 3
```

Số ô trạng thái còn là `n`; tổng lượt cập nhật vẫn là `n(n-1)/2`, nên **`O(n²)` thời gian**, **`O(n)` bộ nhớ phụ** cho `dp` và mảng code point.

**Giới hạn chức năng:** bản 1D chỉ trả **độ dài**. Nó đã ghi đè phần lớn các giá trị `dp[i][j]` cần cho cách truy vết trực tiếp ở phần 5. Nếu đề yêu cầu xuất dãy con, không thể dùng nguyên `dp[j]` cuối cùng rồi đi ngược bằng cùng thuật toán truy vết; cần giữ đủ quyết định hoặc dùng kỹ thuật khôi phục khác.

## 9. Quan hệ giữa LPS và LCS của chuỗi đảo ngược

Có một đẳng thức nổi tiếng:

`LPS(s) = LCS(s, reverse(s))` **về độ dài**,

khi `reverse(s)` đảo **cùng đơn vị ký hiệu** mà bài đang tối ưu. `LCS` là *longest common subsequence* (dãy con chung dài nhất).

### 9.1. Trực giác

Một palindrome subsequence của `s` đọc ngược vẫn là chính nó. Vì vậy nó cũng là một subsequence của `reverse(s)`. Điều này chứng minh:

`LPS(s) <= LCS(s, reverse(s))`.

Theo quan hệ DP của LPS và LCS khi đặt một chuỗi cạnh bản đảo của nó, hai độ dài tối ưu bằng nhau. Cách nhìn LCS là một lựa chọn khác để tính **độ dài**, nhưng thường lưu bảng hai chiều trên hai bản chuỗi, vẫn tốn `O(n²)` thời gian trong cách cài chuẩn.

### 9.2. Khi nào dùng công thức này?

- Khi đã có hàm LCS đúng và chỉ cần **độ dài LPS**.
- Khi muốn liên hệ hai mẫu bài DP: **DP theo đoạn** và **DP theo hai tiền tố**.
- Khi muốn kiểm thử chéo **độ dài** hai thuật toán độc lập trên những chuỗi nhỏ.

Nếu cần **truy vết một palindrome subsequence**, DP đoạn giúp thao tác trực tiếp với hai đầu bằng nhau và dựng **hai nửa đối xứng**. Truy vết LCS trên `s` và `reverse(s)` có hệ tọa độ khác; đừng tự đồng nhất các chỉ số trong chuỗi đảo với chỉ số cùng chiều của chuỗi gốc khi tái dựng.

**Unicode:** `new StringBuilder(s).reverse()` có cách xử lý cặp surrogate, nhưng không tự xử lý đảo **grapheme cluster** theo ngôn ngữ. Nếu cần định nghĩa chính xác theo code point, hãy đảo mảng `s.codePoints().toArray()` rồi dựng chuỗi từ mảng đảo; phải dùng cùng đơn vị trong cả hai thuật toán.

## 10. Từ LPS đến số ký hiệu phải xóa ít nhất

Bài toán liên quan: **xóa ít ký hiệu nhất để dãy còn lại đối xứng**. Mỗi phép xóa bỏ một vị trí, không đổi thứ tự các ký hiệu giữ lại.

Một dãy còn lại sau khi xóa là một **subsequence** của input. Để số lần xóa nhỏ nhất, ta phải giữ lại **subsequence đối xứng dài nhất**.

Vì vậy:

`minimumDeletionsToPalindrome(s) = n - LPS(s)`.

**Chứng minh:**

- Giữ một LPS dài L rồi xóa n−L vị trí khác tạo palindrome, nên có lời giải dùng n−L lần xóa.
- Mọi cách xóa k vị trí để tạo palindrome giữ một palindrome subsequence dài n−k. Vì L là độ dài lớn nhất, `n−k<=L`, suy ra `k>=n−L`.
- Hai chặn bằng nhau, nên tối ưu đúng là n−L.

Ví dụ:

```text
"bbbab": n=5, LPS=4 → xóa tối thiểu 1 ký hiệu (xóa a).
"character": n=9, LPS=5 → xóa tối thiểu 4 ký hiệu.
"racecar": n=7, LPS=7 → không cần xóa.
```

Bài toán **thêm ít ký hiệu nhất để tạo palindrome** có kết quả tối ưu bằng `n-LPS(s)` dưới mô hình cho phép chèn ký hiệu tùy ý ở bất kỳ vị trí và chi phí chèn bằng 1. Tuy vậy **cách tái dựng những phép chèn** khác cách chỉ giữ lại LPS; nếu đề cần chuỗi sau khi chèn hoặc vị trí thao tác, phải thiết kế khôi phục riêng.

### 10.1. Truy hồi trực tiếp cho số xóa ít nhất

Đặt `del[i][j]` là số lần xóa tối thiểu để `a[i..j]` trở thành palindrome.

```text
del[i][j] =
    0                                         nếu i >= j
    del[i+1][j-1]                             nếu a[i] == a[j]
    1 + min(del[i+1][j], del[i][j-1])          nếu a[i] != a[j]
```

Kết quả `del[0][n-1]` bằng `n - dp[0][n-1]`. Công thức này cũng là một dạng interval DP, nhưng **ngữ nghĩa trạng thái khác**: nó đếm số ký hiệu bị xóa, không đếm số ký hiệu giữ lại.

**Không dùng công thức `n-LPS` cho các biến thể khác hợp đồng:** nếu chi phí xóa theo ký hiệu không bằng nhau, chỉ được xóa trong một số vị trí, hoặc phải giữ độ dài tối thiểu khác, cần DP khác.

## 11. So với bài đoạn con đối xứng dài nhất: mở rộng từ tâm

Nhằm tránh nhầm tên bài, dưới đây là một cài đặt **đúng cho substring**. Nó không giải LPS, nhưng tạo ví dụ đối chiếu hữu ích.

Với một chuỗi:

- Mỗi palindrome liên tiếp có **tâm** là một ký hiệu (độ dài lẻ) hoặc khoảng giữa hai ký hiệu (độ dài chẵn).
- Từ mỗi tâm, mở rộng hai đầu khi hai ký hiệu bằng nhau.
- Giữ đoạn liên tiếp dài nhất đã gặp.

### 11.1. Java 17: longest palindromic substring để đối chiếu

Lưu thành **PalindromicSubstringContrast.java**:

```java
import java.util.Objects;

public class PalindromicSubstringContrast {
    static String longestSubstring(String text) {
        Objects.requireNonNull(text, "text");
        int[] a = text.codePoints().toArray();

        int bestStart = 0;
        int bestLength = 0;

        for (int center = 0; center < a.length; center++) {
            // kind=0: tâm lẻ; kind=1: tâm chẵn.
            for (int kind = 0; kind <= 1; kind++) {
                int left = center;
                int right = center + kind;

                while (left >= 0 && right < a.length
                        && a[left] == a[right]) {
                    int length = right - left + 1;
                    if (length > bestLength) {
                        bestLength = length;
                        bestStart = left;
                    }
                    left--;
                    right++;
                }
            }
        }

        return new String(a, bestStart, bestLength);
    }

    public static void main(String[] args) {
        System.out.println("bbbab substring: "
                + longestSubstring("bbbab"));
        System.out.println("character substring: "
                + longestSubstring("character"));
        System.out.println("cbbd substring: "
                + longestSubstring("cbbd"));
        System.out.println("empty substring: ["
                + longestSubstring("") + "]");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PalindromicSubstringContrast.java
java PalindromicSubstringContrast
```

Stdout:

```text
bbbab substring: bbb
character substring: ara
cbbd substring: bb
empty substring: []
```

Độ phức tạp của cách mở rộng tâm là **`O(n²)` thời gian, `O(n)` bộ nhớ** do mảng code point được tạo từ chuỗi Java (ngoài mảng này, số biến làm việc là `O(1)`). Đây là bài toán khác: muốn tìm LPS của `"bbbab"`, không thể trả `"bbb"` vì bỏ ký hiệu `a` cho phép được `"bbbb"` dài hơn.

## 12. LPS không giống đếm số LPS

Bảng `dp[i][j]` ở trên chỉ lưu **độ dài tối ưu**. Nó không trả lời:

- Có bao nhiêu **bộ chỉ số** chọn ra một palindrome subsequence tối ưu?
- Có bao nhiêu **chuỗi ký hiệu phân biệt** là LPS?
- Những LPS ấy là gì theo thứ tự từ điển?

Ba yêu cầu này có thể có đáp án khác nhau. Ví dụ `"aaaa"`:

- LPS theo chuỗi ký hiệu là `"aaaa"`, duy nhất ở độ dài 4.
- Trong một chuỗi dài hơn có nhiều ký hiệu trùng, các **bộ chỉ số khác nhau** có thể cho cùng một chuỗi LPS.
- Đếm trực tiếp bằng cách cộng số phương án từ hai nhánh `dp[i+1][j]` và `dp[i][j-1]` dễ **đếm trùng** các nghiệm nằm trong phần giao `dp[i+1][j-1]`.

Bài đếm **số LPS phân biệt** cần một quan hệ chuyển khác, thường phải xử lý các ký hiệu trùng và các biên xuất hiện. Không được dùng nguyên công thức độ dài rồi đổi `max` thành dấu `+` mà mong ra số nghiệm.

Tương tự, bài “**dãy con đối xứng dài nhất có thứ tự từ điển nhỏ nhất**” đòi hỏi chính sách chọn/khôi phục đáp án có chứng minh; quy tắc hòa tùy ý ở phần 5 chỉ bảo đảm **độ dài tối ưu**.

## 13. Kiểm thử bằng vét cạn cho chuỗi ngắn

Với chuỗi dài `n` nhỏ, có thể liệt kê **toàn bộ `2^n` subsequence** theo tập chỉ số:

1. Mỗi mặt nạ bit từ `0` đến `2^n−1` biểu diễn một lựa chọn vị trí.
2. Đọc các ký hiệu đã chọn theo thứ tự tăng chỉ số.
3. Kiểm tra dãy đó có đối xứng không.
4. Giữ độ dài lớn nhất, so sánh với DP.

Oracle này tốn **`O(n·2^n)` thời gian** trong cách kiểm tra trực tiếp, nên chỉ dùng trên test rất nhỏ. Bù lại, nó gần như độc lập với công thức DP, dễ phát hiện lỗi base, lỗi chỉ số hoặc vòng lặp.

### 13.1. Java 17: kiểm thử vét cạn mọi chuỗi A/B/C dài tối đa 6

Lưu thành **LpsExhaustiveCheck.java**:

```java
public class LpsExhaustiveCheck {
    static int fastLength(String text) {
        char[] a = text.toCharArray(); // Test chỉ dùng ASCII A,B,C.
        int n = a.length;
        if (n == 0) {
            return 0;
        }

        int[][] dp = new int[n][n];
        for (int i = n - 1; i >= 0; i--) {
            dp[i][i] = 1;
            for (int j = i + 1; j < n; j++) {
                if (a[i] == a[j]) {
                    dp[i][j] = 2
                            + (i + 1 < j ? dp[i + 1][j - 1] : 0);
                } else {
                    dp[i][j] = Math.max(dp[i + 1][j], dp[i][j - 1]);
                }
            }
        }
        return dp[0][n - 1];
    }

    static int bruteForce(String text) {
        char[] a = text.toCharArray();
        int n = a.length;
        int best = 0;

        for (int mask = 0; mask < (1 << n); mask++) {
            char[] picked = new char[n];
            int size = 0;
            for (int i = 0; i < n; i++) {
                if ((mask & (1 << i)) != 0) {
                    picked[size++] = a[i];
                }
            }

            boolean palindrome = true;
            for (int l = 0, r = size - 1; l < r; l++, r--) {
                if (picked[l] != picked[r]) {
                    palindrome = false;
                    break;
                }
            }
            if (palindrome) {
                best = Math.max(best, size);
            }
        }
        return best;
    }

    public static void main(String[] args) {
        int checked = 0;

        // Có 3^n chuỗi độ dài n trên bảng {A,B,C}.
        for (int n = 0; n <= 6; n++) {
            int combinations = 1;
            for (int i = 0; i < n; i++) {
                combinations *= 3;
            }

            for (int code = 0; code < combinations; code++) {
                int x = code;
                char[] letters = new char[n];
                for (int i = 0; i < n; i++) {
                    letters[i] = (char) ('A' + x % 3);
                    x /= 3;
                }

                String s = new String(letters);
                if (fastLength(s) != bruteForce(s)) {
                    throw new AssertionError("Mismatch for: " + s);
                }
                checked++;
            }
        }

        System.out.println("Checked cases: " + checked);
        System.out.println("All matched: true");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LpsExhaustiveCheck.java
java LpsExhaustiveCheck
```

Stdout:

```text
Checked cases: 1093
All matched: true
```

Tổng số test là `3^0+3^1+...+3^6 = 1+3+9+27+81+243+729 = 1093`. Việc duyệt mọi chuỗi rất ngắn không thay thế chứng minh toán học ở phần 4, nhưng cho một **kiểm chứng độc lập có thể chạy được**.

**Giới hạn của oracle:** phương pháp dùng `(1 << n)` với `int` nên chỉ phù hợp n nhỏ, ở đây tối đa 6. Mã test dùng ASCII `char`; nó không nhằm kiểm thử toàn bộ Unicode, trong khi mã LPS chính dùng code point.

## 14. Tối ưu hóa và lựa chọn thuật toán theo yêu cầu

### 14.1. Nếu n nhỏ hoặc trung bình và cần một LPS thực tế

Ưu tiên **DP 2D**:

- Dễ chứng minh và cài đặt.
- Dễ in bảng để gỡ lỗi.
- Truy vết một kết quả chỉ `O(n)` sau khi tính bảng.
- Bộ nhớ `O(n²)` có thể là giới hạn lớn nhất.

### 14.2. Nếu chỉ cần độ dài và RAM hạn chế

Dùng **DP 1D**:

- `O(n²)` lượt chuyển như 2D.
- Chỉ `O(n)` vùng DP, tính cả mảng code point là `O(n)`.
- Không thể truy vết bằng bảng 2D vì phần lớn dữ liệu đã bị ghi đè.

### 14.3. Nếu đã có thư viện LCS

Lấy độ dài LCS của `s` và `reverse(s)` theo cùng cách biểu diễn ký hiệu. Đây là một cách kiểm tra/triển khai khác, nhưng không tự làm độ phức tạp tiệm cận thấp hơn `O(n²)` của DP chuẩn.

### 14.4. Nếu bài thực ra hỏi đoạn liên tiếp

Chuyển sang **longest palindromic substring**:

- Mở rộng quanh tâm: `O(n²)` thời gian.
- Manacher: có thể đạt `O(n)` trên dãy ký hiệu, nếu triển khai và xử lý đúng các biên.
- Hai thuật toán này không trả lời bài subsequence khi cho phép bỏ ký hiệu tùy ý.

### 14.5. Khi n rất lớn

Bảng `int[n][n]` có số ô `n²`, chưa tính overhead của từng hàng trong Java. Ví dụ `n=10_000` cần khoảng **100 triệu ô**, tức **400 MB dữ liệu `int` thô** trước cả overhead mảng, JVM và các cấu trúc khác. Không thể giả định cứ `O(n²)` là cấp phát được.

DP 1D giải được vấn đề **bộ nhớ**, nhưng **thời gian vẫn bậc hai**; với n rất lớn, các phương pháp cần xem thêm cấu trúc chuỗi, bộ ký hiệu, giới hạn đầu vào hoặc kỹ thuật tăng tốc chuyên biệt. Không hứa có giải pháp tổng quát tuyến tính cho LPS chỉ bằng nén bộ nhớ.

### 14.6. Nếu muốn trả vị trí gốc

Có thể lưu các chỉ số mỗi lần chọn hai đầu ở bước truy vết, điền vào hai phía mảng vị trí giống mảng ký hiệu. Khi kết quả có độ dài lẻ, lưu chỉ số giữa một lần. Cần khẳng định các chỉ số tăng dần khi đọc kết quả; nếu đầu vào là Unicode code point, chỉ số đó là **chỉ số code point**, không phải offset UTF-16 trong `String`.

## 15. Các lỗi thường gặp

### Lỗi 1 — Nhầm subsequence với substring

Dùng mở rộng tâm cho `"bbbab"` cho ra `"bbb"` dài 3, trong khi LPS đúng dài 4. **Sửa:** nếu đề nói *dãy con*, được bỏ vị trí và phải dùng trạng thái subsequence phù hợp.

### Lỗi 2 — Đặt điều kiện cơ sở `dp[i][i]=0`

Một ký hiệu đơn lẻ là palindrome dài 1. **Sửa:** `dp[i][i]=1`, đoạn rỗng bằng 0.

### Lỗi 3 — Với hai đầu bằng nhau mà dùng `2+dp[i+1][j]`

Đoạn `i+1..j` còn chứa ký hiệu `j`, nên việc cộng cả hai đầu có thể **dùng lặp** vị trí `j`. **Sửa:** lấy đoạn trong `i+1..j-1`.

### Lỗi 4 — Truy cập ô trong rỗng với hai ký hiệu kề nhau

Khi `j=i+1`, `dp[i+1][j-1]` có chỉ số đầu lớn hơn chỉ số cuối; mảng Java không lưu ô tam giác rỗng. **Sửa:** coi đoạn trong rỗng có giá trị 0 và xử lý bằng điều kiện.

### Lỗi 5 — Duyệt bảng sai hướng

Nếu `i` tăng, `dp[i+1][j]` chưa chắc đã có; mảng `int[][]` mặc định bằng 0 nên lỗi có thể khó thấy. **Sửa:** dùng độ dài đoạn tăng hoặc `i` giảm, `j` tăng.

### Lỗi 6 — Quên trường hợp chuỗi rỗng

Với `n=0`, truy cập `dp[0][n-1]` dẫn tới chỉ số âm. **Sửa:** trả độ dài 0 và chuỗi rỗng trước khi tạo/truy cập bảng.

### Lỗi 7 — Nghĩ hai đầu khác nhau thì phải bỏ cả hai

Nếu `a[i]!=a[j]`, chỉ cần **bỏ một** trong hai đầu, chọn phía có LPS dài hơn. Bỏ cả hai có thể mất nghiệm tối ưu.

### Lỗi 8 — Dùng greedy thay DP

Ví dụ chỉ giữ những cặp trùng đầu/cuối tìm thấy đầu tiên mà không xét **hai phương án bỏ đầu** có thể mất dãy tối ưu. Khi hai đầu khác nhau, phải so sánh độ dài các bài con.

### Lỗi 9 — Truy vết mà không giữ bảng hoặc quyết định

Mảng `dp[j]` của phiên bản 1D chỉ chứa những giá trị đã được ghi đè theo quá trình tính. Nó không đủ để đi ngược theo phương pháp truy vết 2D. **Sửa:** dùng bảng đầy đủ hoặc một thuật toán khôi phục đã chứng minh.

### Lỗi 10 — Truy vết độ dài lẻ thành hai ký hiệu giữa

Khi `i==j`, chỉ có **một** ký hiệu ở tâm. Ghi cả hai phía sẽ nhân đôi tâm và làm đáp án dài hơn độ dài LPS thực.

### Lỗi 11 — Giả định dãy tối ưu là duy nhất

Trong `"abca"`, `"aba"` và `"aca"` đều là LPS dài 3. Test không nên bắt buộc một chuỗi duy nhất nếu đề chỉ cần một LPS bất kỳ; hãy kiểm tra palindrome, subsequence và độ dài tối ưu.

### Lỗi 12 — Nhầm chỉ số code point và UTF-16

`charAt()` trên emoji có thể tách một ký hiệu thành hai surrogate. Nếu muốn đếm code point, dùng `codePoints()` nhất quán trong tính DP và dựng lại output.

### Lỗi 13 — Đếm số cách bằng cùng bảng độ dài

`max` chọn giá trị tối ưu, không lưu số nghiệm. Nếu đếm số LPS, các nhánh có thể trùng nghiệm; không thể chỉ cộng mà không xét trùng.

### Lỗi 14 — Đánh giá sai chi phí bộ nhớ

Độ phức tạp `O(n²)` không có nghĩa lúc nào cũng vừa RAM. Trong Java, `int[][]` còn có overhead mảng từng hàng; n lớn có thể gây `OutOfMemoryError`.

### Lỗi 15 — Ghi `dp[i][j]` theo điều kiện hai đầu nhưng quên hai đoạn con

Khi hai đầu khác nhau, kết quả là `max(dp[i+1][j],dp[i][j-1])`. Không được dùng `dp[i+1][j-1]` cho cả hai trường hợp, vì có thể mất một ký hiệu cần giữ ở một đầu.

### Lỗi 16 — Nhầm độ dài LPS với số lần xóa

Độ dài LPS là **số ký hiệu giữ lại**; số xóa ít nhất để thành palindrome là **`n-LPS`**, không phải LPS.

## 16. Bộ test phải có để kiểm tra lời giải

| Input | Độ dài LPS | Một kết quả hợp lệ | Điểm kiểm tra |
|---|---:|---|---|
| `""` | 0 | `""` | Chuỗi rỗng |
| `"a"` | 1 | `"a"` | Đường chéo cơ sở |
| `"aa"` | 2 | `"aa"` | Hai đầu bằng nhau, đoạn trong rỗng |
| `"ab"` | 1 | `"a"` hoặc `"b"` | Hai đầu khác nhau |
| `"bbbab"` | 4 | `"bbbb"` | Được bỏ ký hiệu không liên tiếp |
| `"cbbd"` | 2 | `"bb"` | Không phải cả hai đầu đều phù hợp |
| `"character"` | 5 | `"carac"` | Hai đầu được ghép sau các lần bỏ |
| `"agbdba"` | 5 | `"abdba"` | Một palindrome độ dài lẻ |
| `"banana"` | 5 | `"anana"` | Palindrome trong dãy |
| `"racecar"` | 7 | `"racecar"` | Cả chuỗi đã đối xứng |
| `"aaaa"` | 4 | `"aaaa"` | Ký hiệu trùng |
| `"abc"` | 1 | Một ký hiệu bất kỳ | Nhiều nghiệm tối ưu |
| `"abca"` | 3 | `"aba"` hoặc `"aca"` | Hòa giữa hai nghiệm |
| `"😀a😀"` | 3 code point | Toàn chuỗi | Cặp surrogate khi dùng Java |

Một **oracle tự động** nên kiểm:

1. `result.length()` theo đúng đơn vị ký hiệu bằng độ dài DP.
2. Kết quả đọc xuôi và ngược bằng nhau.
3. Kết quả là một **subsequence** của input theo chỉ số tăng.
4. Độ dài trùng với brute force trên chuỗi ngắn.
5. Bản 2D và bản 1D cho **cùng độ dài**.
6. Nếu so với longest palindromic substring, luôn có `LPS_length >= substring_length`, không nhất thiết bằng nhau.

Khi kiểm tra string Java có Unicode, nên so sánh theo **code point**, không đơn giản dùng `String.length()` hoặc đảo từng `char` mà chưa xác định ý nghĩa.

## 17. Bài tập tự luyện và hướng dẫn giải

### Bài 1 — Viết công thức

Cho dãy ký hiệu `a[0..n-1]`, đặt `dp[i][j]` là độ dài LPS trong đoạn `i..j`. Hãy nêu đủ ba điều kiện cơ sở/chuyển.

**Đáp án:** rỗng (`i>j`) cho 0; một phần tử (`i==j`) cho 1; hai đầu bằng nhau cho `2+dp[i+1][j-1]`; khác nhau cho `max(dp[i+1][j],dp[i][j-1])`, với trường hợp đoạn trong rỗng bằng 0.

### Bài 2 — Tính bằng tay

Tính độ dài LPS của `"cbbd"`.

**Đáp án:** `dp[0][3] = max(dp[1][3],dp[0][2])`; một đoạn chứa cặp `"bb"` dài 2, không có palindrome dài 3. Kết quả **2**.

### Bài 3 — Dãy con không liên tiếp

Với `"bbbab"`, giải thích vì sao LPS là 4 nhưng longest palindromic substring là 3.

**Đáp án:** chọn các vị trí `0,1,2,4` thành `"bbbb"` dài 4; những vị trí không liên tiếp do bỏ `a` tại vị trí 3. Substring phải liên tiếp, `"bbb"` chỉ dài 3.

### Bài 4 — Giải thích hai đầu bằng nhau

Nếu `a[i]==a[j]`, vì sao có thể dùng `2+dp[i+1][j-1]` mà không cần lấy `max` với các nhánh bỏ một đầu?

**Đáp án:** ghép hai đầu vào một palindrome tối ưu của đoạn trong cho chặn dưới. Bất kỳ palindrome có độ dài L của đoạn lớn, bỏ hai ký hiệu đầu/cuối được chọn còn palindrome dài L−2 nằm trong đoạn trong; do đó L không thể vượt `2+dp[i+1][j-1]`.

### Bài 5 — Trạng thái và vòng lặp

Một bạn tính `i=0,1,...,n-1` rồi `j=i+1,...,n-1`, với `dp[i][j]` phụ thuộc `dp[i+1][j]`. Tại sao thứ tự sai?

**Đáp án:** khi tính hàng i, hàng i+1 chưa được tính. Cần `i` giảm hoặc duyệt **độ dài đoạn tăng**.

### Bài 6 — Tối ưu bộ nhớ

Trong DP 1D, `previousDiagonal` lưu giá trị gì và tại sao phải lưu `old=dp[j]` trước khi cập nhật?

**Đáp án:** `previousDiagonal` phải là `LPS(i+1,j-1)` của hàng trước; sau khi cập nhật `dp[j]`, giá trị cũ `LPS(i+1,j)` sẽ cần làm đường chéo ở lượt j+1. Nếu không lưu `old`, dữ liệu hàng trước bị ghi đè.

### Bài 7 — Độ dài hay kết quả cụ thể

Nếu đề chỉ yêu cầu độ dài LPS và RAM hạn chế, chọn 2D hay 1D? Nếu yêu cầu xuất một LPS, chọn thế nào?

**Đáp án:** chỉ độ dài: DP 1D `O(n)` bộ nhớ, `O(n²)` thời gian. Xuất một LPS: DP 2D dễ truy vết bằng hai con trỏ; nếu hạn RAM cần kỹ thuật khôi phục khác, không thể dùng ngay cách đi ngược trên mảng 1D cuối.

### Bài 8 — Xóa để thành palindrome

Với `"character"`, cần xóa ít nhất bao nhiêu ký hiệu để còn palindrome?

**Đáp án:** n=9, LPS dài 5 (`"carac"`), nên cần xóa **4** ký hiệu; giữ lại một LPS dài 5 là cách đạt đúng số xóa.

### Bài 9 — Không đếm trùng

Cho `"abca"`, có ít nhất hai chuỗi LPS khác nhau là `"aba"` và `"aca"` đều dài 3. Vì sao bảng chỉ lưu `dp[i][j]` không tự cho số LPS phân biệt?

**Đáp án:** bảng lưu **độ dài lớn nhất**, phép `max` không lưu số cách; các nhánh bỏ đầu/trái có thể cùng độ dài và các nghiệm có thể trùng ký hiệu, cần công thức đếm riêng.

### Bài 10 — Unicode

Nếu chuỗi đầu vào gồm ba **code point** `"😀a😀"`, vì sao `String.length()` trong Java không phải 3 nhưng DP theo `codePoints()` trả độ dài LPS 3?

**Đáp án:** emoji ngoài BMP dùng hai đơn vị UTF-16, nên `String.length()` lớn hơn số code point. `codePoints()` gom mỗi cặp surrogate thành một ký hiệu; dãy code point `[😀,a,😀]` đã đối xứng.

### Bài 11 — Khi yêu cầu đổi thành palindrome liên tiếp

Nếu đề thực sự hỏi substring palindrome dài nhất, có thể giữ nguyên `dp[i][j] = max(dp[i+1][j],dp[i][j-1])` không?

**Đáp án:** không. Công thức này cho phép **bỏ vị trí** và thu một subsequence không liên tiếp. Bài substring có thể dùng mở rộng tâm, Manacher, hoặc DP kiểu boolean `isPal[i][j]` để kiểm tra **cả đoạn liên tiếp** có palindrome không.

### Bài 12 — Ước lượng bộ nhớ

Với n=10.000, bảng `int[n][n]` có bao nhiêu phần tử và phần dữ liệu `int` thô tốn khoảng bao nhiêu bộ nhớ?

**Đáp án:** `100.000.000` ô, mỗi `int` 4 byte ⇒ khoảng **400 triệu byte** (xấp xỉ 381 MiB), chưa tính overhead của các mảng, đầu vào, output và JVM. Nếu chỉ cần độ dài, hãy cân nhắc 1D.

## 18. Checklist khi gặp đề “dãy con đối xứng”

1. **Subsequence hay substring?** Có được bỏ ký hiệu ở giữa không? Nếu được, đây là LPS.
2. **Cần độ dài, một nghiệm hay tất cả nghiệm?** Các yêu cầu này khác về lưu trữ/truy vết.
3. **Đơn vị ký hiệu là gì?** `char`, Unicode code point, grapheme, hay phần tử số?
4. **`dp[i][j]` có nghĩa gì?** Độ dài tối ưu trong đoạn **bao gồm cả i và j**.
5. **Cơ sở đúng chưa?** Đoạn rỗng 0, đoạn một phần tử 1.
6. **Hai đầu bằng nhau?** Ghép cả hai với tối ưu đoạn trong.
7. **Hai đầu khác nhau?** Bỏ một trong hai đầu, lấy `max`.
8. **Thứ tự phụ thuộc đúng chưa?** Duyệt độ dài tăng hoặc `i` giảm, `j` tăng.
9. **N=0 được xử lý chưa?** Tránh truy cập `dp[0][-1]`.
10. **Khi tái dựng, có viết hai đầu đối xứng không?** Trường hợp tâm lẻ chỉ viết một ký hiệu.
11. **Có quy tắc hòa rõ ràng không?** Một kết quả tối ưu bất kỳ khác từ điển nhỏ nhất.
12. **Có đủ bộ nhớ `O(n²)` không?** Nếu chỉ cần độ dài, dùng `O(n)` bộ nhớ.
13. **Nén bộ nhớ có lưu đường chéo cũ không?** Không đọc trạng thái đã bị ghi đè.
14. **Có phân biệt độ dài và số nghiệm không?** Muốn đếm cách phải có DP riêng.
15. **Đã kiểm tra bằng ví dụ nhỏ/brute force chưa?** Rỗng, một ký hiệu, toàn trùng, không trùng, hai đầu bằng, hai đầu khác, Unicode.
16. **Độ phức tạp có gắn với đúng n không?** `n` là số ký hiệu sau khi chọn biểu diễn, không luôn bằng số đơn vị UTF-16.

**Ghi nhớ:** LPS là bài **quy hoạch động trên đoạn** với trạng thái `dp[i][j]`. Nếu hai đầu bằng nhau, ghép chúng vào LPS của đoạn giữa; nếu khác nhau, bỏ trái hoặc bỏ phải rồi lấy nhánh tốt hơn. Công thức đúng nhờ phân trường hợp đầy đủ và lập luận ghép hai đầu. Tính toàn bảng tốn **`O(n²)` thời gian và `O(n²)` bộ nhớ**, có thể giảm bộ nhớ xuống **`O(n)`** khi chỉ cần độ dài. Đừng nhầm *dãy con* với *đoạn con* đối xứng liên tiếp.
