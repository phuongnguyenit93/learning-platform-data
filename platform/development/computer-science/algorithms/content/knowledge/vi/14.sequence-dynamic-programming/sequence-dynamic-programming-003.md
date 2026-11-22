# Dãy con chung dài nhất và cách truy vết

## 1. Phát biểu bài toán

**Dãy con chung dài nhất (Longest Common Subsequence, LCS)** của hai dãy A và B là một dãy xuất hiện trong cả A lẫn B theo **cùng thứ tự tương đối**, nhưng các phần tử được chọn **không cần liên tiếp**. Mục tiêu cơ bản là tìm **độ dài lớn nhất** của một dãy con chung; một biến thể quan trọng yêu cầu **truy vết** để in ra dãy con cụ thể và những vị trí phần tử đã được chọn.

Với một chuỗi A, C là **subsequence** nếu có các chỉ số tăng nghiêm ngặt \(0\le i_0<i_1<\cdots<i_{L-1}<|A|\) sao cho C[t]=A[i_t] với mọi t. Để là dãy con chung, C cũng phải có một dãy chỉ số tăng phù hợp trong B. Chỉ số tương ứng ở hai chuỗi **không nhất thiết bằng nhau**.

Ví dụ:

~~~text
A = ABCBDAB
B = BDCABA

LCS thứ nhất: BCBA
  Vị trí trong A: [1, 2, 3, 5]
  Vị trí trong B: [0, 2, 4, 5]

LCS thứ hai: BDAB
  Vị trí trong A: [3, 4, 5, 6]
  Vị trí trong B: [0, 1, 3, 4]

Độ dài tối ưu: 4.
~~~

Hai dãy con BCBA và BDAB đều dài 4, cùng hợp lệ. Do đó **độ dài tối ưu xác định**, nhưng **nội dung LCS có thể không duy nhất**. Bài toán chỉ yêu cầu một LCS bất kỳ khác với bài toán yêu cầu mọi LCS hoặc LCS nhỏ nhất theo thứ tự từ điển.

### Phân biệt subsequence với substring

**Substring (chuỗi con liên tiếp)** yêu cầu các phần tử đứng cạnh nhau; subsequence cho phép bỏ các phần tử ở giữa. Với A="ABCDE", B="ACE":
- LCS là "ACE" dài 3, vì chọn A[0], A[2], A[4].
- "ACE" không phải substring của A do A còn B và D nằm xen giữa.
- Longest common substring là **bài toán khác** với một truy hồi khác (khi ký tự khác nhau, độ dài kết thúc tại vị trí đang xét thường được đặt 0).

Quy hoạch động của LCS có thể xử lý **chuỗi, mảng số, dãy từ hoặc token**, miễn là phép xác định hai phần tử bằng nhau được định nghĩa nhất quán.

## 2. Tại sao dùng quy hoạch động?

Thử tất cả subsequence của A có thể phải xét tới \(2^{|A|}\) tập vị trí, rồi kiểm tra xem có tồn tại trong B không. Với đầu vào dài, brute force không phù hợp.

LCS có hai đặc điểm mà **quy hoạch động (dynamic programming, DP)** khai thác:
- **Cấu trúc con tối ưu:** độ dài LCS của hai tiền tố có thể tính từ độ dài LCS tối ưu của những tiền tố ngắn hơn. Ta chứng minh công thức bao quát các lựa chọn của lời giải tối ưu.
- **Các bài toán con chồng lặp:** nếu hai ký tự cuối khác nhau, một lời giải đệ quy thử bỏ ký tự cuối của A hoặc B. Những nhánh này có thể tiếp tục chạm đến cùng một cặp tiền tố. Lưu kết quả theo cặp chỉ số tránh giải lại.

Kết quả DP không chỉ là cách tính nhanh hơn: **bảng độ dài cũng chứa thông tin cần thiết để lần ngược và tái tạo một LCS**.

Giả sử A có m phần tử và B có n phần tử. Có \((m+1)(n+1)\) trạng thái tiền tố. Với mỗi trạng thái, công thức chỉ cần O(1) phép so sánh/tra cứu giá trị đã biết, nên ta có thể tính bảng trong O(mn) thời gian.

## 3. Định nghĩa trạng thái: hai tiền tố

Đặt:

\[
dp[i][j]=\text{độ dài LCS của }A[0..i)\text{ và }B[0..j).
\]

Ký hiệu [0..i) là khoảng nửa mở chứa các phần tử chỉ số 0 đến i−1. Điều đó nghĩa là:
- i là **độ dài tiền tố A**, không phải chỉ số phần tử cuối.
- j là **độ dài tiền tố B**.
- Nếu i,j>0, hai phần tử cuối đang xét là A[i−1] và B[j−1].
- Các chỉ số hợp lệ của bảng: \(0\le i\le m\), \(0\le j\le n\).

### Trạng thái cơ sở

Nếu một tiền tố rỗng, không thể có subsequence chung khác rỗng:

\[
dp[0][j]=0,\qquad dp[i][0]=0.
\]

Vì vậy cần bảng có kích thước **(m+1)×(n+1)**, không phải chỉ m×n.

### Khi hai phần tử cuối bằng nhau

Nếu \(A[i-1]=B[j-1]\):

\[
\boxed{dp[i][j]=dp[i-1][j-1]+1.}
\]

Có thể lấy một LCS của hai tiền tố ngắn hơn rồi **nối phần tử chung cuối**. Để thấy công thức tối ưu, cần biết luôn tồn tại một LCS tối ưu có thể dùng hai phần tử cuối bằng nhau làm cặp khớp cuối; phần trước của cặp đó không thể dài hơn dp[i−1][j−1].

**Cẩn thận:** không nói rằng **mọi** LCS của hai tiền tố đều bắt buộc dùng cặp ký tự cuối. Khi có nhiều nghiệm, một LCS tối ưu có thể dùng những vị trí khác; công thức chỉ cần sự tồn tại của **một** nghiệm tối ưu có cặp khớp này.

### Khi hai phần tử cuối khác nhau

Nếu \(A[i-1]\ne B[j-1]\), một subsequence chung không thể dùng **cả hai** ký tự cuối như cùng một phần tử khớp. Một nghiệm tối ưu phải bỏ ký tự cuối của ít nhất một phía:

\[
\boxed{dp[i][j]=\max(dp[i-1][j],dp[i][j-1]).}
\]

Một nhánh tương ứng bỏ A[i−1], nhánh còn lại bỏ B[j−1]. Lấy max bởi ta chưa biết lựa chọn nào giữ được subsequence dài hơn.

**Công thức tổng quát:**

\[
dp[i][j]=
\begin{cases}
0,&i=0\text{ hoặc }j=0,\\
dp[i-1][j-1]+1,&A[i-1]=B[j-1],\\
\max(dp[i-1][j],dp[i][j-1]),&A[i-1]\ne B[j-1].
\end{cases}
\]

### Chứng minh bằng quy nạp

Quy nạp theo tổng độ dài tiền tố i+j. Khi i=0 hoặc j=0, đáp án cơ sở 0 là đúng.

Giả sử các trạng thái có tổng độ dài nhỏ hơn i+j đã đúng:
- Nếu phần tử cuối bằng nhau, một nghiệm tối ưu có thể chọn cặp khớp cuối; phần trước là một subsequence chung của hai tiền tố đã bỏ cặp ấy. Nhờ giả thuyết quy nạp, giá trị tốt nhất của phần trước là dp[i−1][j−1]. Nối ký tự chung tạo giá trị dp[i−1][j−1]+1.
- Nếu chúng khác nhau, ít nhất một ký tự cuối phải bị loại. Tất cả nghiệm hợp lệ nằm trong **một trong hai** lớp xét ở dp[i−1][j] hoặc dp[i][j−1]. Dùng tối ưu của hai trạng thái con và lấy max là đủ.

Do đó công thức trả đúng độ dài LCS cho mọi i,j.

## 4. Điền bảng từ trên xuống dưới, trái sang phải

Một cách tính **bottom-up tabulation**:
1. Tạo bảng dp có m+1 hàng, n+1 cột, ban đầu toàn 0.
2. Với i=1..m, duyệt j=1..n.
3. Tính dp[i][j] từ dp[i−1][j−1], dp[i−1][j] hoặc dp[i][j−1].
4. Sau khi điền hết, **dp[m][n]** là độ dài LCS của toàn bộ A và B.

Bất biến vòng lặp: trước khi tính dp[i][j], các ô **phía trên, phía trái và chéo trên trái** đã có giá trị chính xác. Với cách duyệt này, mọi tham chiếu trong công thức đều sẵn sàng.

Ví dụ A="ABCBDAB", B="BDCABA" có bảng sau:

| A \\ B | ∅ | B | D | C | A | B | A |
|---|---:|---:|---:|---:|---:|---:|---:|
| ∅ | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| A | 0 | 0 | 0 | 0 | 1 | 1 | 1 |
| B | 0 | 1 | 1 | 1 | 1 | 2 | 2 |
| C | 0 | 1 | 1 | 2 | 2 | 2 | 2 |
| B | 0 | 1 | 1 | 2 | 2 | 3 | 3 |
| D | 0 | 1 | 2 | 2 | 2 | 3 | 3 |
| A | 0 | 1 | 2 | 2 | 3 | 3 | 4 |
| B | 0 | 1 | 2 | 2 | 3 | 4 | 4 |

Cách đọc một số ô:
- dp[1][4]=1 vì hai phần tử cuối tương ứng A và A giống nhau, nên bằng dp[0][3]+1.
- dp[3][3]=2 do C=C, lấy dp[2][2]+1=2.
- dp[6][6]=4 vì A=A, lấy dp[5][5]+1=4.
- dp[7][6]=4 vì B khác A, lấy max(dp[6][6],dp[7][5])=max(4,4).

**Không nhầm bảng với dữ liệu gốc:** hàng/cột có nhãn A, B, C,... tương ứng phần tử ở **vị trí i−1, j−1**, còn số trong ô là độ dài LCS của **toàn bộ hai tiền tố** tới vị trí ấy.

## 5. Truy vết: từ độ dài về chính dãy LCS

Nếu chỉ cần độ dài, dp[m][n] là đủ. Nếu yêu cầu **nội dung** của LCS, phải đi ngược qua bảng:

**Bắt đầu tại (i,j)=(m,n).** Khi i>0 và j>0:
1. **A[i−1] == B[j−1]:** nhận phần tử chung A[i−1] vào danh sách tạm; ghi cặp vị trí (i−1,j−1); đi **chéo lên trái** tới (i−1,j−1).
2. **Phần tử khác nhau và dp[i−1][j] > dp[i][j−1]:** đi **UP** (lên trên), giảm i.
3. **Phần tử khác nhau và dp[i−1][j] < dp[i][j−1]:** đi **LEFT** (sang trái), giảm j.
4. **Phần tử khác và hai ô bằng nhau:** cả UP và LEFT đều có thể dẫn đến một LCS tối ưu. Cần chọn một quy tắc tie-break xác định, ví dụ **ưu tiên UP**.

Kết thúc khi i=0 hoặc j=0. Các phần tử được lấy trong chiều từ cuối về đầu, nên **đảo ngược** danh sách đã ghi nhận để thành LCS theo thứ tự đọc.

Giả mã:

~~~text
i = m
j = n
reverseChars = []
reversePairs = []

while i > 0 and j > 0:
    if A[i - 1] == B[j - 1]:
        reverseChars.add(A[i - 1])
        reversePairs.add((i - 1, j - 1))
        i--
        j--
    else if dp[i - 1][j] >= dp[i][j - 1]:
        i--              // UP nếu hòa
    else:
        j--              // LEFT nếu phía trái lớn hơn

reverse(reverseChars)
reverse(reversePairs)
return reverseChars, reversePairs
~~~

**Đây không phải một thuật toán tham lam độc lập:** các quyết định UP/LEFT dựa vào **bảng giá trị tối ưu đã tính**. Nếu thiếu bảng hoặc thông tin tương đương, chọn bỏ phần tử nào bằng trực giác có thể làm mất LCS dài nhất.

### Truy vết cụ thể với A="ABCBDAB" và B="BDCABA"

Áp dụng ưu tiên UP khi hai giá trị bằng nhau:

| Ô bắt đầu (i,j) | Hai phần tử cuối | Hành động |
|---|---|---|
| (7,6) | B và A khác | dp[6][6]=4, dp[7][5]=4 → hòa, đi UP tới (6,6) |
| (6,6) | A và A giống | Nhận A tại (5,5), đi chéo tới (5,5) |
| (5,5) | D và B khác | dp[4][5]=3 > dp[5][4]=2, đi UP |
| (4,5) | B và B giống | Nhận B tại (3,4), đi chéo |
| (3,4) | C và A khác | dp[3][3]=2 > dp[2][4]=1, đi LEFT |
| (3,3) | C và C giống | Nhận C tại (2,2), đi chéo |
| (2,2) | B và D khác | dp[2][1]=1 > dp[1][2]=0, đi LEFT |
| (2,1) | B và B giống | Nhận B tại (1,0), đi chéo tới cột 0 |

Đường đi ghi ký tự theo thứ tự ngược: **A, B, C, B**. Đảo lại thành **BCBA**; các vị trí tương ứng:

~~~text
LCS: BCBA
Vị trí trong A: [1, 2, 3, 5]
Vị trí trong B: [0, 2, 4, 5]
Cặp chỉ số: [(1,0), (2,2), (3,4), (5,5)]
~~~

Nếu dùng quy tắc **ưu tiên LEFT khi hòa**, một đường đi khác trả **BDAB**, với các vị trí (3,0), (4,1), (5,3), (6,4). Cả hai có độ dài tối ưu 4.

### Bất biến truy vết

Khi ở trạng thái (i,j), phần kết quả đã ghi ở chiều ngược thuộc **hậu tố của một LCS tối ưu** cho hai chuỗi ban đầu; phần còn phải tìm có độ dài dp[i][j] và nằm trong hai tiền tố A[0..i), B[0..j).

- Nếu hai phần tử cuối bằng nhau, truy hồi cho phép nhận cặp khớp cuối và chuyển sang dp[i−1][j−1], giảm độ dài còn phải tìm đúng một.
- Nếu khác nhau, đi về ô **có cùng độ dài tối ưu** nên không làm mất độ dài có thể đạt.
- Nếu hòa, cả hai ô con đều có giá trị tối ưu, nên chọn một trong hai vẫn đúng.

Mỗi bước làm i+j giảm ít nhất một, vì thế vòng lặp kết thúc. Khi tới hàng/cột 0, dp=0 nên không còn gì phải chọn. Số lần nhận cặp khớp chính xác là dp[m][n]; các chỉ số giảm nghiêm ngặt trong chiều truy vết, nên sau khi đảo chúng **tăng nghiêm ngặt** trong cả hai dãy. Kết quả là một subsequence chung có độ dài tối ưu.

## 6. Nhiều LCS: tie-break không phải sắp thứ tự từ điển

Bảng dp chỉ lưu **độ dài tối ưu**, không quyết định duy nhất chuỗi khôi phục. Khi hai phần tử cuối khác nhau và dp[i−1][j]==dp[i][j−1], cả hai hướng đều bảo toàn độ dài tối ưu.

- **Ưu tiên UP** trên mọi tie cho một kết quả xác định trên cùng dữ liệu, thường khác kết quả của LEFT.
- **Ưu tiên LEFT** cũng tạo một LCS hợp lệ.
- **LCS nhỏ nhất theo thứ tự từ điển** là yêu cầu bổ sung; quy tắc chọn UP/LEFT tùy ý **không bảo đảm** cho chuỗi nhỏ nhất. Cần thuật toán lựa chọn giữa các nghiệm tối ưu theo tiêu chí từ điển.
- **Liệt kê mọi LCS:** nhiều đường đi DP có thể tạo cùng một chuỗi khi dữ liệu có ký tự trùng. Cần khử trùng; số chuỗi LCS khác nhau có thể rất lớn, nên không thể khẳng định sẽ liệt kê hết trong O(mn).

Khi đề bài chỉ yêu cầu **một** dãy con chung dài nhất, việc chương trình A in BCBA và chương trình B in BDAB không phải là lỗi. Đúng đắn phải đánh giá qua **độ dài tối ưu, tính subsequence và tính hợp lệ của các vị trí**.

**Lưu mảng hướng hay không?** Có thể ghi hướng DIAG/UP/LEFT tại mỗi ô khi điền dp, rồi truy vết theo mảng hướng; cách này trực quan nhưng thêm O(mn) bộ nhớ nếu lưu một hướng cho tất cả ô. Nếu đã lưu bảng độ dài và còn hai dãy nguồn, có thể suy ra hướng trực tiếp như giả mã, không cần mảng hướng riêng.

## 7. Java 17+ hoàn chỉnh: trả dãy và vị trí khớp

Chương trình dưới đây:
1. Chuyển String thành **mảng Unicode code point** để một emoji ngoài BMP là một phần tử thay vì hai UTF-16 char.
2. Tính bảng dp theo truy hồi LCS.
3. Truy vết với **hai quy tắc tie** để thấy nhiều nghiệm tối ưu.
4. Trả về **độ dài, dãy con và cặp chỉ số code point 0-based**.
5. Kiểm thử trường hợp không có phần tử chung, chuỗi rỗng, chuỗi giống hệt và Unicode.

Lưu thành **LcsTracebackDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class LcsTracebackDemo {
    private LcsTracebackDemo() {
    }

    enum TieChoice {
        UP, LEFT
    }

    record Position(int aIndex, int bIndex) {
        @Override
        public String toString() {
            return "(" + aIndex + "," + bIndex + ")";
        }
    }

    record Result(int length, String subsequence,
                  List<Position> positions) {
    }

    public static Result lcs(String first, String second,
                             TieChoice tieChoice) {
        if (first == null || second == null || tieChoice == null) {
            throw new IllegalArgumentException("Null input");
        }

        int[] a = first.codePoints().toArray();
        int[] b = second.codePoints().toArray();
        int m = a.length;
        int n = b.length;

        // dp[i][j] là LCS length của a[0..i) và b[0..j).
        int[][] dp = new int[m + 1][n + 1];
        for (int i = 1; i <= m; i++) {
            for (int j = 1; j <= n; j++) {
                if (a[i - 1] == b[j - 1]) {
                    dp[i][j] = dp[i - 1][j - 1] + 1;
                } else {
                    dp[i][j] = Math.max(dp[i - 1][j],
                                        dp[i][j - 1]);
                }
            }
        }

        List<Integer> reversedCodePoints = new ArrayList<>();
        List<Position> reversedPositions = new ArrayList<>();
        int i = m;
        int j = n;

        while (i > 0 && j > 0) {
            if (a[i - 1] == b[j - 1]) {
                reversedCodePoints.add(a[i - 1]);
                reversedPositions.add(new Position(i - 1, j - 1));
                i--;
                j--;
            } else if (dp[i - 1][j] > dp[i][j - 1]
                    || (dp[i - 1][j] == dp[i][j - 1]
                        && tieChoice == TieChoice.UP)) {
                i--;
            } else {
                j--;
            }
        }

        // Đường truy vết đi từ cuối về đầu nên cần đảo thứ tự.
        Collections.reverse(reversedCodePoints);
        Collections.reverse(reversedPositions);

        StringBuilder sequence = new StringBuilder();
        for (int codePoint : reversedCodePoints) {
            sequence.appendCodePoint(codePoint);
        }

        return new Result(
                dp[m][n],
                sequence.toString(),
                List.copyOf(reversedPositions)
        );
    }

    public static void main(String[] args) {
        String a = "ABCBDAB";
        String b = "BDCABA";

        Result up = lcs(a, b, TieChoice.UP);
        Result left = lcs(a, b, TieChoice.LEFT);
        System.out.println("Length: " + up.length());
        System.out.println("Tie UP: " + up.subsequence()
                + " " + up.positions());
        System.out.println("Tie LEFT: " + left.subsequence()
                + " " + left.positions());

        Result unicode = lcs("A😀B", "😀XB", TieChoice.UP);
        System.out.println("Unicode: " + unicode.subsequence()
                + " (code points=" + unicode.length() + ")");

        Result disjoint = lcs("ABC", "XYZ", TieChoice.UP);
        System.out.println("Disjoint length: " + disjoint.length());
        System.out.println("Empty length: "
                + lcs("", "ABC", TieChoice.UP).length());
        System.out.println("Identical: "
                + lcs("ABC", "ABC", TieChoice.UP).subsequence());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên trong môi trường nguồn/terminal UTF-8:

~~~bash
javac -encoding UTF-8 LcsTracebackDemo.java
java LcsTracebackDemo
~~~

Stdout (khi terminal hỗ trợ Unicode):

~~~text
Length: 4
Tie UP: BCBA [(1,0), (2,2), (3,4), (5,5)]
Tie LEFT: BDAB [(3,0), (4,1), (5,3), (6,4)]
Unicode: 😀B (code points=2)
Disjoint length: 0
Empty length: 0
Identical: ABC
~~~

**Giải thích chi tiết:**
- **dp** là mảng (m+1)×(n+1) có giá trị 0 mặc định. Hai vòng lặp khởi đầu ở i=j=1, nên không truy cập chỉ số âm.
- Khi phần tử khớp, ta ghi code point và cặp Position rồi đi chéo. Các cặp đang được ghi từ cuối về đầu, do đó cần Collections.reverse trước khi in.
- Hàm Position.toString() tạo dạng "(i,j)" để Java in danh sách đúng định dạng kiểm chứng.
- Khi hai ô hướng UP và LEFT hòa nhau, tham số TieChoice quyết định hướng; nó **không thay đổi** độ dài dp[m][n].
- String.codePoints() cho phép một emoji 😀 được xem như một phần tử dãy. StringBuilder.appendCodePoint() ghép lại Unicode đúng theo các code point đã truy vết.
- Chỉ số trong Position là **chỉ số code point**, không phải offset UTF-16 của Java String. Có thể dùng String.offsetByCodePoints(0,index) để đổi sang offset UTF-16 khi cần thao tác substring.
- Java String là immutable nên hàm không sửa đầu vào. Hàm kiểm tra null và cho phép chuỗi rỗng hợp lệ.
- Ví dụ giả định mỗi code point là một phần tử, **không** tự gom các ký tự kết hợp thành grapheme. Quy tắc so Unicode cần được xác định theo mục tiêu ứng dụng.

## 8. Độ phức tạp

Gọi m và n là số phần tử của hai dãy (trong chương trình Java là số Unicode code point), L là độ dài LCS.

| Bước | Thời gian | Bộ nhớ phụ trợ |
|---|---|---|
| Chuyển chuỗi sang mảng code point | O(m+n) | O(m+n) |
| Tạo và tính bảng dp | **O(mn)** | **O(mn)** |
| Truy vết từ (m,n) tới hàng/cột 0 | O(m+n) | O(L) cho cặp chỉ số và phần tử nhận |
| Đảo danh sách, dựng chuỗi kết quả | O(L) | O(L) |
| Tổng chương trình minh họa | **O(mn+m+n)** | **O(mn+m+n)** |

Với m,n≥1, người ta thường nói gọn thời gian **O(mn)** và bộ nhớ **O(mn)** cho bảng đầy đủ. L luôn không quá min(m,n). Khi một chuỗi rỗng, chi phí vẫn có thể gồm việc đọc/chuyển đổi chuỗi còn lại, vì vậy biểu thức cộng m+n diễn đạt chính xác hơn ở các trường hợp biên.

### Chỉ tính độ dài với hai hàng

Nếu chỉ cần LCS **length**, hàng dp[i] chỉ phụ thuộc hàng dp[i−1] và ô bên trái trong hàng hiện tại. Có thể lưu **hai hàng** thay vì cả bảng và đặt chuỗi ngắn hơn ở chiều cột để giảm bộ nhớ còn O(min(m,n)). Một hàng cũng có thể đủ nếu lưu riêng giá trị chéo cũ.

**Không được giả định rằng hai hàng vẫn cho phép dùng nguyên vòng truy vết của bản đầy đủ:** các hàng cũ đã bị ghi đè, nên các giá trị cần cho đường đi từ dp[m][n] về dp[0][0] không còn sẵn.

### Khi cần truy vết nhưng bộ nhớ hạn chế: Hirschberg

Thuật toán **Hirschberg** dùng tính LCS theo hai hàng kết hợp chia để trị: chia một chuỗi thành hai phần, tính các giá trị độ dài xuôi/ngược để chọn điểm tách thích hợp trên chuỗi kia, rồi truy vết đệ quy ở hai phía. Với cách triển khai cẩn thận, có thể khôi phục **một** LCS trong thời gian O(mn) nhưng chỉ dùng **O(min(m,n)) bộ nhớ làm việc** cho DP, chưa tính lưu đầu vào và đầu ra.

Đây là thuật toán nâng cao, không phải chỉ thay int[][] bằng hai mảng rồi giữ nguyên vòng while. Với dữ liệu vừa bộ nhớ, bảng đầy đủ rõ ràng và ít lỗi hơn.

### Chi phí thực tế

Bảng của hai chuỗi độ dài 10.000 × 10.000 có hơn 100 triệu ô int, riêng dữ liệu số nguyên đã chiếm khoảng **400 MB** (chưa tính overhead các mảng và các vùng nhớ khác). Nếu m×n lớn hơn bộ nhớ có sẵn, cân nhắc Hirschberg hoặc thuật toán khác phù hợp với cấu trúc dữ liệu.

Nếu đề yêu cầu tìm **tất cả** LCS, việc xuất kết quả có thể rất lớn dù bảng độ dài tính xong trong O(mn). Không gán độ phức tạp O(mn) cho tác vụ liệt kê tất cả nghiệm.

## 9. Các trường hợp cần chú ý

### 9.1. Nhiều ký tự trùng và nhiều nghiệm

Với A="ABCBDAB", B="BDCABA", đã thấy hai LCS khác nhau đều dài 4. Khi kiểm thử, phải chấp nhận nhiều nghiệm nếu đề không bắt buộc thứ tự từ điển hoặc một quy tắc tie cụ thể.

Khi một ký tự xuất hiện nhiều lần, các **đường đi truy vết khác nhau** đôi khi lại tạo cùng một chuỗi LCS. Nếu nhiệm vụ là liệt kê mọi LCS phân biệt, cần khử trùng kết quả; chỉ duyệt toàn bộ nhánh DP không bảo đảm mỗi chuỗi xuất hiện đúng một lần.

### 9.2. Chỉ số Java và Unicode

Trong Java, String.charAt(index) trả một đơn vị **UTF-16 char**, không nhất thiết một ký tự Unicode hoàn chỉnh. 😀 thường chiếm hai char. Đo LCS theo char hoặc theo code point có thể cho hai bài toán với **định nghĩa độ dài khác nhau**.

Thậm chí code point không hoàn toàn tương đương **grapheme cluster** (ký tự người đọc nhìn thấy): các dấu kết hợp hoặc emoji ghép có thể gồm nhiều code point. Nếu sản phẩm yêu cầu LCS theo grapheme, phải tách chuỗi thành dãy grapheme trước và định nghĩa phép bằng nhau tương ứng.

Unicode normalization cũng có thể cần thiết khi hai chuỗi nhìn giống nhau nhưng một bên dùng ký tự dựng sẵn, bên kia dùng ký tự cơ sở và dấu kết hợp. Cách chuẩn hóa là một phần **hợp đồng dữ liệu**, không phải một chi tiết tự động của truy hồi DP.

### 9.3. LCS cho dãy đối tượng

Nếu A và B là List<Event> hoặc List<Token>, thay so code point bằng phép so phần tử phù hợp (ví dụ so ID, loại token hoặc Objects.equals). **Phép bằng nhau dùng khi tính bảng phải đúng là phép bằng nhau dùng khi truy vết**, nếu không đường đi khôi phục có thể không còn là subsequence chung theo cùng định nghĩa.

Khi cặp phần tử được coi bằng nhau theo khóa nhưng có thông tin payload khác, cần quyết định kết quả LCS giữ phần tử của nguồn nào hoặc chỉ giữ khóa; chương trình mẫu in ký tự đã khớp, không có payload bổ sung.

### 9.4. Bài toán diff và so sánh phiên bản

Các cặp chỉ số từ LCS có thể dùng làm một **xương sống các phần tử được giữ chung** giữa hai phiên bản tài liệu hoặc chuỗi token. Các đoạn không thuộc subsequence chung gợi ý phần tử bị thêm/bỏ.

Tuy nhiên, sản phẩm diff có thể tối ưu riêng cho ít chỉnh sửa, cách nhóm thay đổi, bố cục hiển thị và dữ liệu rất lớn. Một LCS bất kỳ không nhất thiết tạo diff dễ đọc nhất; tie-breaking có thể ảnh hưởng nhiều tới cách hiển thị kết quả.

## 10. Lỗi triển khai phổ biến

1. **Nhầm LCS với longest common substring:** một bài yêu cầu giữ thứ tự, bài kia yêu cầu liên tiếp.
2. **Dùng dp[i][j] cho phần tử A[i],B[j]:** i,j là **độ dài tiền tố**, nên phần tử cuối là A[i−1],B[j−1].
3. **Thiếu hàng/cột 0:** dẫn đến lỗi truy cập chỉ số âm hoặc sai cơ sở.
4. **Ký tự khác mà đặt dp[i][j]=0:** đó không phải truy hồi LCS; phải lấy max của UP/LEFT.
5. **Ký tự giống mà lấy max(UP,LEFT) rồi bỏ qua chéo:** có thể vẫn đúng một số ca nhưng công thức/truy vết không còn được chứng minh theo cách chuẩn; dùng công thức chéo +1 đã nêu.
6. **Truy vết không kiểm tra ký tự bằng nhau:** có thể ghi nhận các phần tử không khớp và tạo chuỗi sai.
7. **Đi chéo khi ký tự khác vì ô chéo lớn:** không bảo đảm phần tử tương ứng tồn tại trong cả hai dãy.
8. **Quên đảo kết quả:** nhận ký tự theo chiều từ cuối về đầu, dễ in chuỗi đảo.
9. **Không giữ cặp chỉ số hoặc tính sai chỉ số:** kết quả chuỗi có thể đúng nhưng vị trí báo cáo không tăng và không khớp.
10. **Coi tie là lỗi hoặc khẳng định kết quả duy nhất:** nhiều LCS khác nhau đều hợp lệ nếu cùng độ dài tối ưu.
11. **Nhầm quy tắc UP/LEFT với lexicographic minimum:** không có bảo đảm chung.
12. **Nén bảng còn hai hàng rồi vẫn truy vết như trước:** dữ liệu của các hàng cũ đã bị ghi đè.
13. **Quên trường hợp rỗng:** dp[0][n] và dp[m][0] luôn bằng 0, truy vết phải dừng ngay.
14. **So sánh char mà đề yêu cầu ký tự Unicode hoàn chỉnh:** có thể chia tách một emoji thành hai surrogate.
15. **Tính cả chương trình O(m+n):** đó chỉ là thời gian của đường truy vết, còn điền bảng cần O(mn).
16. **Cho rằng liệt kê tất cả LCS có cùng chi phí với tìm một LCS:** số lượng nghiệm có thể rất lớn.
17. **Không đảm bảo phép so bằng nhau nhất quán:** nếu tính DP bằng so không phân biệt hoa/thường nhưng truy vết lại phân biệt, nghiệm có thể sai.
18. **Không định nghĩa đầu ra khi có nhiều nghiệm:** cần biết đề cho phép một LCS bất kỳ hay yêu cầu tie-break cụ thể.

## 11. Kiểm thử và xác minh đường truy vết

| Trường hợp | A | B | Kỳ vọng |
|---|---|---|---|
| Một chuỗi rỗng | "" | "ABC" | L=0, dãy rỗng |
| Cả hai rỗng | "" | "" | L=0 |
| Hai chuỗi giống nhau | "ABC" | "ABC" | L=3, "ABC" |
| Không có phần tử chung | "ABC" | "XYZ" | L=0 |
| Subsequence không liên tiếp | "ABCDE" | "ACE" | L=3, "ACE" |
| Có nhiều LCS | "ABCBDAB" | "BDCABA" | L=4, "BCBA"/"BDAB" hợp lệ |
| Nhiều ký tự trùng | "AAAA" | "AA" | L=2, "AA" |
| Code point ngoài BMP | "A😀B" | "😀XB" | L=2 theo code point, "😀B" |
| Thứ tự đảo | "ABC" | "CBA" | L=1, có nhiều lựa chọn |
| Tie khác nhau | "ABA" | "BAA" | L=2, có thể là "AA" hoặc "BA" |

Không nên chỉ so kết quả với một chuỗi chuẩn khi đề không yêu cầu tie-break: một cách truy vết khác có thể trả LCS hợp lệ nhưng khác nội dung.

**Các điều kiện kiểm chứng một Result của chương trình:**
1. Số phần tử của subsequence bằng L, với đơn vị đếm đã chọn (code point hoặc token).
2. Số cặp vị trí bằng L.
3. Mỗi cặp (i,j) nằm trong biên hai dãy nguồn; các i tăng nghiêm ngặt và các j tăng nghiêm ngặt.
4. Phần tử tại A[i] bằng phần tử tại B[j] và bằng phần tử của subsequence ở vị trí tương ứng.
5. L bằng dp[m][n] đã tính hoặc bằng kết quả của một thuật toán tính độ dài độc lập.

Với dãy rất nhỏ, có thể **đối chiếu brute force**: duyệt mọi subsequence của một dãy, kiểm tra nó có là subsequence của dãy kia và lấy độ dài lớn nhất; so với DP. Brute force này chỉ dùng kiểm thử vì có thể tốn thời gian hàm mũ.

Nếu kiểm thử các nhánh tie, chạy cả UP và LEFT, kiểm tra cả hai đều có cùng độ dài tối ưu và cặp chỉ số hợp lệ; việc hai chuỗi khôi phục khác nhau **không tự nó là lỗi**.

## 12. Bài tập tự kiểm tra

**Câu 1.** A="ABCDE", B="ACE". Vì sao "ACE" là LCS nhưng không phải substring của A?

**Đáp án:** Các vị trí A[0], A[2], A[4] tăng theo thứ tự nhưng không liền kề. Subsequence không cần liên tiếp, substring thì cần.

**Câu 2.** Trạng thái dp[i][j] có ý nghĩa gì?

**Đáp án:** Độ dài LCS giữa hai tiền tố **A[0..i)** và **B[0..j)**. Hai phần tử cuối đang so là A[i−1], B[j−1].

**Câu 3.** Nếu A[i−1] khác B[j−1], công thức đúng là gì?

**Đáp án:** dp[i][j]=max(dp[i−1][j],dp[i][j−1]). Ta phải bỏ ít nhất một trong hai phần tử cuối và xét cả hai khả năng tối ưu.

**Câu 4.** Tại sao truy vết phải đảo danh sách ký tự đã chọn?

**Đáp án:** Vòng while đi từ (m,n) về (0,0) nên ghi các phần tử khớp từ **cuối LCS về đầu LCS**. Đảo lại mới có thứ tự đọc ban đầu.

**Câu 5.** Với A="ABCBDAB" và B="BDCABA", nếu ưu tiên UP khi hòa, chương trình in gì?

**Đáp án:** BCBA, độ dài 4; các cặp chỉ số [(1,0),(2,2),(3,4),(5,5)]. Ưu tiên LEFT có thể in BDAB, cũng dài 4.

**Câu 6.** Có thể vừa lưu hai hàng dp vừa dùng nguyên truy vết kiểu bảng đầy đủ không?

**Đáp án:** Không. Các hàng cũ không còn lưu lại. Muốn dựng một LCS trong bộ nhớ thấp cần chiến lược như Hirschberg hoặc thông tin truy vết bổ sung.

**Câu 7.** Tại sao việc in một chuỗi có độ dài bằng dp[m][n] chưa đủ để xác minh truy vết?

**Đáp án:** Chuỗi ấy còn phải là **subsequence của cả A và B**, với những cặp chỉ số tăng nghiêm ngặt. Chỉ dài đúng nhưng có phần tử sai vẫn không phải LCS.

**Câu 8.** String.codePoints() có hoàn toàn tương đương ký tự người dùng nhìn thấy không?

**Đáp án:** Không. Một grapheme cluster có thể chứa nhiều code point như ký tự cơ sở và dấu kết hợp. Cần xác định đơn vị phần tử và quy tắc chuẩn hóa theo yêu cầu.

**Câu 9.** Nếu đề yêu cầu LCS nhỏ nhất theo từ điển, đổi quy tắc hòa từ UP thành LEFT có đủ không?

**Đáp án:** Không có bảo đảm. Phải thiết kế phép lựa chọn theo thứ tự từ điển giữa các nghiệm tối ưu, không chỉ chọn một hướng cố định khi bảng DP hòa.

**Ghi nhớ:** LCS là bài toán **dãy con giữ thứ tự nhưng không yêu cầu liên tiếp**. Bảng DP lưu **độ dài tối ưu của hai tiền tố**; khi ký tự cuối bằng nhau dùng **chéo +1**, khi khác dùng **max(trên, trái)**. Muốn truy vết một LCS, đi ngược từ dp[m][n], nhận cặp khớp khi bằng nhau, đi về ô giữ tối ưu khi khác, rồi **đảo thứ tự các cặp đã nhận**. Nhiều chuỗi LCS khác nhau có thể cùng tối ưu.
