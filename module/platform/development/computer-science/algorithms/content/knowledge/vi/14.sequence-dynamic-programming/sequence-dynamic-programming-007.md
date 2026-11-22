# Đếm cách tạo một dãy con đích bằng quy hoạch động

## 1. Bài toán: một đích có thể được tạo theo bao nhiêu cách?

Cho hai dãy ký tự (hoặc hai dãy phần tử bất kỳ) **S** và **T**. Cần đếm số cách **chọn một số vị trí trong S theo thứ tự tăng nghiêm ngặt** để các phần tử được chọn ghép lại đúng bằng T. Không bắt buộc các vị trí trong S phải kề nhau.

Một **dãy con (subsequence)** được xác định bằng một dãy chỉ số tăng:

~~~text
0 <= i0 < i1 < ... < i(m-1) < n
S[i0] S[i1] ... S[i(m-1)] = T[0] T[1] ... T[m-1]
~~~

Ở đây n là độ dài S, m là độ dài T. Hai cách chọn được tính là **hai cách khác nhau nếu bộ chỉ số chọn khác nhau**, kể cả khi các ký tự được ghép đều giống hệt nhau. Đây là ngữ nghĩa của bài toán đếm số subsequence khớp một target (thường gọi là distinct subsequences theo cách chọn vị trí).

Ví dụ S="aaa", T="aa": có ba cách lấy chỉ số 0-based:

- (0,1): chọn hai ký tự a đầu tiên.
- (0,2): chọn ký tự a thứ nhất và thứ ba.
- (1,2): chọn hai ký tự a cuối cùng.

Kết quả là **3 cách**, mặc dù ba kết quả khi ghép đều là cùng chuỗi "aa". Nếu bài toán thực sự yêu cầu **đếm số chuỗi dãy con khác nhau về nội dung**, đó là một bài toán khác; không được lấy công thức trong bài này rồi hiểu kết quả thành số chuỗi phân biệt.

Ví dụ tiêu biểu:

| S | T | Số cách | Giải thích |
| --- | --- | ---: | --- |
| "rabbbit" | "rabbit" | 3 | Có ba chữ b trong S, chọn hai chữ b theo thứ tự |
| "babgbag" | "bag" | 5 | Năm bộ chỉ số b–a–g hợp lệ |
| "aaa" | "aa" | 3 | Chọn 2 trong 3 vị trí |
| "aaaaa" | "aaa" | 10 | Chọn 3 trong 5 vị trí |
| "abc" | "abc" | 1 | Chọn cả ba vị trí |
| "abc" | "ac" | 1 | Bỏ qua b |
| "abc" | "ca" | 0 | Không thể đảo thứ tự c trước a |
| "abc" | "" | 1 | Có đúng một cách chọn dãy vị trí rỗng |
| "" | "a" | 0 | Không thể tạo mục tiêu không rỗng từ nguồn rỗng |
| "" | "" | 1 | Chỉ có bộ vị trí rỗng |

Điểm mấu chốt là **thứ tự** và **số lần xuất hiện**. Dãy con khác với **đoạn con liên tiếp (substring/subarray)**: để tạo "ac" từ "abc", ta có thể bỏ b; nếu yêu cầu đoạn liên tiếp thì "ac" không xuất hiện.

## 2. Từ lựa chọn phần tử cuối đến công thức DP

Ta định nghĩa:

~~~text
dp[i][j] = so cach tao T[0..j) tu S[0..i)

0 <= i <= n
0 <= j <= m
~~~

Đoạn [0..j) là **tiền tố độ dài j** (cận phải không bao gồm); dp[i][j] chỉ xét **i phần tử đầu** của S và **j phần tử đầu** của T.

Để tính dp[i][j] khi i>0, j>0, hãy xét **ký tự cuối của tiền tố nguồn**, tức S[i-1]. Mỗi cách chọn chỉ thuộc một trong hai nhóm **rời nhau**:

1. **Không dùng S[i-1]:** mọi cách tạo T[0..j) từ S[0..i-1) đều hợp lệ. Có dp[i-1][j] cách.
2. **Có dùng S[i-1] làm ký tự cuối của dãy con đích:** điều này chỉ có thể khi S[i-1] == T[j-1]. Khi đó, các j-1 ký tự đầu của T phải được chọn từ i-1 ký tự trước của S. Có dp[i-1][j-1] cách.

Vì hai nhóm không trùng nhau và bao phủ toàn bộ lời giải, số cách là tổng của hai nhóm:

~~~text
if S[i-1] == T[j-1]:
    dp[i][j] = dp[i-1][j] + dp[i-1][j-1]
else:
    dp[i][j] = dp[i-1][j]
~~~

Nhánh **không lấy** S[i-1] luôn tồn tại; nhánh **lấy** chỉ tồn tại nếu hai ký tự cuối bằng nhau. Không cần tạo chuỗi con mới hay duyệt các tập vị trí; chỉ cần hai giá trị DP trước đó.

Đừng nhầm với LCS: bài LCS tìm **độ dài lớn nhất** nên thường dùng max, còn bài này đếm **tất cả cách hợp lệ** nên cộng các nhánh không giao nhau. Dùng max trong bài này sẽ làm mất các cách khác nhau.

### Vì sao dp[i-1][j-1] là đúng cho nhánh lấy?

Nếu ta buộc sử dụng vị trí i-1 làm phần tử thứ j của lời giải, j-1 vị trí trước phải nằm trong [0,i-1). Vì dãy chỉ số luôn tăng, mọi cách tạo T[0..j-1) từ tiền tố S[0..i-1) ghép thêm vị trí i-1 tạo **đúng một** cách của nhóm lấy. Ngược lại, bỏ vị trí i-1 khỏi bất kỳ cách thuộc nhóm lấy sẽ cho một cách của bài toán con ấy. Đây là một song ánh, nên số cách đúng bằng dp[i-1][j-1].

Nếu S[i-1] khác T[j-1], không thể dùng S[i-1] làm phần tử cuối; mọi cách đều nằm trong nhóm bỏ.

## 3. Trường hợp cơ sở và chiều tính bảng

Base cases phải được đặc tả theo **số cách chọn vị trí**, không theo số ký tự:

~~~text
dp[i][0] = 1       cho moi i tu 0 den n
dp[0][j] = 0       cho moi j > 0
dp[0][0] = 1
~~~

**Vì sao dp[i][0]=1, không phải 0?** Với mục tiêu rỗng, có đúng **một lựa chọn**: không lấy phần tử nào của S. Nếu ghi 0, các công thức đếm cách có thể bị sai dây chuyền ngay từ lần khớp ký tự đầu tiên.

**Vì sao dp[0][j>0]=0?** Không có vị trí nguồn để chọn, nên không thể tạo một đích khác rỗng.

Nếu m>n thì kết quả bằng 0: không thể chọn m chỉ số tăng nghiêm ngặt từ n vị trí khi m lớn hơn n. Đây là kiểm tra nhanh đúng, không cần dựng bảng.

### Thứ tự điền bảng hai chiều

Công thức dp[i][j] chỉ phụ thuộc **hàng i-1**, nên có thể duyệt i từ 1 đến n, và với mỗi i duyệt j từ 1 đến m. Mỗi ô chỉ cần một hoặc hai phép tra cứu và phép cộng.

~~~text
init dp[0..n][0..m] = 0
for i = 0..n:
    dp[i][0] = 1

for i = 1..n:
    for j = 1..min(i,m):
        dp[i][j] = dp[i-1][j]
        if S[i-1] == T[j-1]:
            dp[i][j] += dp[i-1][j-1]

answer = dp[n][m]
~~~

Duyệt j chỉ đến min(i,m) vì nếu j>i, số cách chắc chắn bằng 0. Đây là tối ưu nhỏ; không thay đổi công thức. Nếu dùng mảng được khởi tạo 0 thì có thể bỏ qua những ô không thể đạt.

**Độ phức tạp theo số phép cộng DP:** O(nm) trường hợp xấu nhất, bộ nhớ O(nm) ô giá trị. Khi số cách lớn đến mức cần BigInteger, chi phí mỗi phép cộng phụ thuộc vào số bit kết quả; phân tích “O(nm)” thường ngầm xem phép cộng số nguyên là O(1).

## 4. Mô phỏng bảng DP với ký tự trùng lặp

Xét S="aab", T="ab". Có đúng **hai** cách tạo "ab":

- Chọn chữ a ở vị trí 0 và b ở vị trí 2.
- Chọn chữ a ở vị trí 1 và b ở vị trí 2.

Bảng DP, với j là độ dài tiền tố T:

| Đã đọc tiền tố S | j=0, T="" | j=1, T="a" | j=2, T="ab" |
| --- | ---: | ---: | ---: |
| i=0, "" | 1 | 0 | 0 |
| i=1, "a" | 1 | 1 | 0 |
| i=2, "aa" | 1 | 2 | 0 |
| i=3, "aab" | 1 | 2 | 2 |

Giải thích bước cuối khi đọc b:

~~~text
dp[3][2] = dp[2][2] + dp[2][1]
         = 0 + 2
         = 2
~~~

S[i-1]='b' trùng ký tự cuối T[1]='b', nên hai cách tạo "a" từ "aa" đều có thể nối thêm b. Không phải chỉ kiểm tra rằng "a" có tồn tại; phải **đếm tất cả vị trí** của nó.

Với S="rabbbit", T="rabbit", phần chung trước và sau các chữ b chỉ có một cách; ba chữ b liên tiếp có ba lựa chọn lấy hai vị trí, nên kết quả bằng C(3,2)=3. Với S="babgbag", T="bag", số cách bằng 5, vì nhiều cặp b–a có thể nối với một vị trí g phía sau.

### Đếm cách theo chỉ số, không theo nội dung

Khi mọi phần tử của S đều bằng 'a' và mọi phần tử của T cũng là 'a', m≤n, mọi bộ m chỉ số tăng đều cho một dãy con hợp lệ:

~~~text
S = "a" lap n lan
T = "a" lap m lan

answer = C(n,m) = n! / (m! * (n-m)!)
~~~

Ví dụ C(5,3)=10. Đây là một thuộc tính mạnh để kiểm thử DP khi có nhiều ký tự trùng. Đồng thời, nó chứng minh số cách có thể **lớn theo cấp số mũ** của n, dù chương trình không bao giờ duyệt trực tiếp các cách ấy.

## 5. Nén bảng hai chiều thành DP một chiều

Ở bước i, dp[i][j] chỉ cần hai ô của hàng trước: dp[i-1][j] và dp[i-1][j-1]. Vì thế, ta có thể lưu **một hàng duy nhất**:

~~~text
ways[j] = so cach tao T[0..j) sau khi doc
          mot tien to cua S
~~~

Ban đầu chưa đọc ký tự nguồn nào:

~~~text
ways[0] = 1
ways[1..m] = 0
~~~

Khi gặp một ký tự s trong S, nếu s==T[j-1] thì phải thêm số cách tạo tiền tố đích dài j-1 **trước khi đọc s** vào số cách tạo tiền tố dài j:

~~~text
for each s in S, from left to right:
    for j from m down to 1:
        if s == T[j-1]:
            ways[j] = ways[j] + ways[j-1]

answer = ways[m]
~~~

**Điểm sống còn: j phải chạy từ phải sang trái (giảm dần).** Khi ta cập nhật ways[j], ways[j-1] vẫn còn là giá trị **trước khi xử lý ký tự nguồn hiện tại**. Như vậy mỗi vị trí của S được dùng nhiều nhất một lần trong cùng một cách chọn.

Nếu duyệt j từ 1 lên m, ways[j-1] có thể đã được tăng nhờ **chính ký tự s hiện tại**, rồi ways[j] lại nhận giá trị đó. Ta vô tình sử dụng **cùng một vị trí nguồn nhiều lần**.

### Phản ví dụ cho vòng lặp sai hướng

S="a", T="aa". Đáp án đúng bằng 0 vì nguồn chỉ có một vị trí.

Ban đầu ways=[1,0,0]. Nếu duyệt **tăng**:

1. j=1: s='a' khớp T[0], ways[1] += ways[0] => ways=[1,1,0].
2. j=2: s='a' cũng khớp T[1], ways[2] += ways[1] => ways=[1,1,1].
3. Thuật toán sai trả **1**, như thể có thể chọn cùng vị trí nguồn vừa làm ký tự thứ nhất vừa làm ký tự thứ hai.

Nếu duyệt **giảm**:

1. j=2: ways[2] += ways[1] (lúc này còn 0) => ways[2]=0.
2. j=1: ways[1] += ways[0] => ways[1]=1.
3. Trả ways[2]=**0**, đúng.

Đây là một mẫu quan trọng trong **quy hoạch động dãy**: khi cập nhật in-place, hướng vòng lặp phụ thuộc vào việc các chuyển trạng thái phải đọc **lớp cũ** hay được phép đọc **lớp vừa cập nhật**. Với đếm subsequence, bắt buộc dùng lớp cũ nên đi ngược chiều j.

### Bất biến của DP một chiều

Sau khi đã xử lý đúng i ký tự đầu của S, ways[j] bằng số cách chọn dãy con T[0..j) từ S[0..i), với mọi 0≤j≤m. Ban đầu i=0, ways[0]=1 và các j>0 bằng 0, nên đúng.

Khi xử lý S[i], duyệt j từ m về 1 giúp ways[j] và ways[j-1] lúc được dùng vẫn phản ánh các trạng thái từ lớp i. Nhánh bỏ ký tự giữ nguyên ways[j]; nhánh lấy (nếu trùng T[j-1]) thêm ways[j-1] của lớp cũ. Vì vậy bất biến đúng cho lớp i+1. Cuối cùng ways[m] đúng bằng câu trả lời.

**Chi phí:** O(nm) phép xét ký tự/chuyển trạng thái, bộ nhớ O(m) ô DP. Nếu m>n, có thể trả 0 sớm. Có thể giới hạn vòng j tới min(i+1,m) vì một tiền tố nguồn dài i+1 không thể tạo đích dài hơn nó.

## 6. Tràn số: int, long, BigInteger và phép lấy modulo

Số cách chọn vị trí có thể vượt cả miền của Java long. Với S gồm 70 chữ 'a' và T gồm 35 chữ 'a':

~~~text
answer = C(70,35) = 112186277816662845432
~~~

Giá trị này lớn hơn Long.MAX_VALUE = 9223372036854775807, nên không thể lưu chính xác bằng long; dùng int càng sai sớm hơn.

### Chọn kiểu số theo yêu cầu đề bài

| Yêu cầu | Cách lưu | Chú ý |
| --- | --- | --- |
| Bảo đảm số cách nhỏ | int hoặc long khi đã chứng minh cận trên | Không tự giả định nhỏ từ n,m |
| Cần **đếm chính xác** với dữ liệu lớn | java.math.BigInteger | Tốn bộ nhớ và thời gian cho số có nhiều bit |
| Chỉ cần kết quả **mod M** | Lưu các phần dư, cập nhật cộng modulo | M phải >0; dùng kiểu trung gian đủ rộng |
| Cần so sánh hoặc kiểm chứng với giá trị chính xác | BigInteger hoặc cấu trúc số lớn | Không thể suy ra giá trị nguyên từ một phần dư duy nhất |

Nếu đề yêu cầu trả kết quả mod 1_000_000_007, mỗi bước có thể tính:

~~~text
ways[j] = (ways[j] + ways[j-1]) mod 1000000007
~~~

Hai giá trị đều nhỏ hơn modulus, nhưng tổng của chúng có thể vượt Integer.MAX_VALUE khi lưu trong int. Dùng long cho phép cộng, sau đó lấy phần dư và chỉ ép về int nếu cần. Trong ví dụ Java bên dưới, modulus được đưa vào kiểu int dương và mảng lưu **long**, do đó cộng hai số nhỏ hơn int max là an toàn trong miền long.

Khi modulus=1, mọi phần dư, kể cả số 1 cách của target rỗng, đều bằng 0 theo toán học modulo. Nếu cần **số cách chính xác**, không được dùng kết quả modulo rồi coi như giá trị thật.

### Chi phí bit khi dùng BigInteger

Mệnh đề thời gian O(nm) nói về **số trạng thái và số phép cộng**. Với số cách cực lớn, mỗi lần BigInteger.add có thể phải xử lý nhiều từ máy. Nếu L là số bit lớn nhất của giá trị DP, chi phí số học có thể tăng theo L (xấp xỉ O(nmL) bit operations trong mô hình đơn giản), còn bộ nhớ của O(m) đối tượng BigInteger cũng phụ thuộc kích thước các số.

Đối với n nguồn, số cách chọn vị trí không vượt 2^n, nên số bit của kết quả là O(n) trong trường hợp tổng quát. Điều này giải thích tại sao **tối ưu bộ nhớ từ O(nm) về O(m) ô** không phải lúc nào cũng tương đương O(m) byte bộ nhớ khi ô chứa số lớn.

## 7. Java 17+: ba phiên bản đếm cách

Chương trình hoàn chỉnh dưới đây trình bày:

1. **count2D:** giữ toàn bộ bảng để dễ đối chiếu công thức và chứng minh.
2. **count1D:** nén bộ nhớ bằng cách duyệt j giảm dần; trả BigInteger chính xác.
3. **countModulo:** cũng nén bộ nhớ nhưng chỉ trả phần dư mod M, phù hợp với những bài ra giới hạn số cách.

Để có định nghĩa ký tự rõ hơn, mã chuyển String sang dãy **Unicode code point** bằng codePoints().toArray() trước khi chạy DP. Đây là lựa chọn khác với việc so sánh trực tiếp từng char UTF-16. Cách này hoạt động đúng cho ví dụ ASCII và ký tự ngoài BMP, nhưng **không tự chuẩn hóa Unicode**; xem phần lưu ý về ngữ nghĩa văn bản ở dưới.

Lưu toàn bộ mã trong **SubsequenceCountDemo.java**:

~~~java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;

public class SubsequenceCountDemo {

    private static int[] points(String text, String name) {
        return Objects.requireNonNull(text, name)
                .codePoints().toArray();
    }

    // Gia tri CHINH XAC, bang dp[i][j] cho cac tien to.
    static BigInteger count2D(String source, String target) {
        int[] s = points(source, "source");
        int[] t = points(target, "target");
        int n = s.length, m = t.length;

        if (m == 0) return BigInteger.ONE;
        if (m > n) return BigInteger.ZERO;

        BigInteger[][] dp = new BigInteger[n + 1][m + 1];
        for (int i = 0; i <= n; i++) {
            Arrays.fill(dp[i], BigInteger.ZERO);
            dp[i][0] = BigInteger.ONE;
        }

        for (int i = 1; i <= n; i++) {
            for (int j = 1; j <= Math.min(i, m); j++) {
                BigInteger answer = dp[i - 1][j];
                if (s[i - 1] == t[j - 1]) {
                    answer = answer.add(dp[i - 1][j - 1]);
                }
                dp[i][j] = answer;
            }
        }
        return dp[n][m];
    }

    // Gia tri CHINH XAC, chi giu mot hang dp dai m+1.
    static BigInteger count1D(String source, String target) {
        int[] s = points(source, "source");
        int[] t = points(target, "target");
        int n = s.length, m = t.length;

        if (m == 0) return BigInteger.ONE;
        if (m > n) return BigInteger.ZERO;

        BigInteger[] ways = new BigInteger[m + 1];
        Arrays.fill(ways, BigInteger.ZERO);
        ways[0] = BigInteger.ONE;

        for (int i = 0; i < n; i++) {
            for (int j = Math.min(i + 1, m); j >= 1; j--) {
                if (s[i] == t[j - 1]) {
                    ways[j] = ways[j].add(ways[j - 1]);
                }
            }
        }
        return ways[m];
    }

    // Chi tra so cach MOD modulus; modulus la so nguyen duong.
    static long countModulo(String source, String target, int modulus) {
        if (modulus <= 0) {
            throw new IllegalArgumentException("modulus must be positive");
        }
        int[] s = points(source, "source");
        int[] t = points(target, "target");
        int n = s.length, m = t.length;

        if (m > n) return 0L;
        if (m == 0) return 1L % modulus;

        long[] ways = new long[m + 1];
        ways[0] = 1L % modulus;

        for (int i = 0; i < n; i++) {
            for (int j = Math.min(i + 1, m); j >= 1; j--) {
                if (s[i] == t[j - 1]) {
                    // ways[j] va ways[j-1] deu < modulus <= int max.
                    ways[j] = (ways[j] + ways[j - 1]) % modulus;
                }
            }
        }
        return ways[m];
    }

    public static void main(String[] args) {
        System.out.println("rabbit 2D = " +
                count2D("rabbbit", "rabbit"));
        System.out.println("rabbit 1D = " +
                count1D("rabbbit", "rabbit"));
        System.out.println("babgbag -> bag = " +
                count1D("babgbag", "bag"));
        System.out.println("aaa -> aa = " +
                count1D("aaa", "aa"));
        System.out.println("aab -> ab = " +
                count2D("aab", "ab"));

        System.out.println("empty target = " +
                count1D("abc", ""));
        System.out.println("empty source = " +
                count1D("", "a"));
        System.out.println("both empty = " +
                count1D("", ""));
        System.out.println("cannot reuse index = " +
                count1D("a", "aa"));

        System.out.println("large count = " +
                count1D("a".repeat(70), "a".repeat(35)));
        System.out.println("10 mod 7 = " +
                countModulo("aaaaa", "aaa", 7));

        // U+1F600 duoc bieu dien bang hai char UTF-16.
        String emoji = new String(Character.toChars(0x1F600));
        System.out.println("Unicode code points = " +
                count1D(emoji.repeat(2), emoji));

        try {
            countModulo("abc", "a", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid modulo: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac SubsequenceCountDemo.java
java SubsequenceCountDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
rabbit 2D = 3
rabbit 1D = 3
babgbag -> bag = 5
aaa -> aa = 3
aab -> ab = 2
empty target = 1
empty source = 0
both empty = 1
cannot reuse index = 0
large count = 112186277816662845432
10 mod 7 = 3
Unicode code points = 2
invalid modulo: modulus must be positive
~~~

### Diễn giải cài đặt

- **points** dùng Objects.requireNonNull; đầu vào null bị từ chối ngay, không diễn giải null thành dãy rỗng.
- **count2D** dùng BigInteger.ZERO và BigInteger.ONE cho các cơ sở, do BigInteger là kiểu tham chiếu không phải giá trị số mặc định trong mảng. Arrays.fill tránh NullPointerException khi cộng với một ô chưa được khởi tạo. Các ô j>i vẫn là ZERO vì không thể tạo đích dài hơn số ký tự nguồn.
- **count1D** duyệt nguồn từ trái sang phải nhưng **duyệt đích từ phải sang trái**, tránh sử dụng lại một chỉ số nguồn ở cùng bước. Math.min(i+1,m) chỉ giới hạn các trạng thái có thể đạt.
- **countModulo** dùng long[] để tổng của hai phần dư nhỏ hơn modulus dương kiểu int không tràn. Trả kết quả trong [0,modulus) với modulus>0, kể cả modulus=1.
- **String.repeat** là API có trên Java 17. BigInteger cho ra kết quả C(70,35) chính xác, vượt giới hạn long. Ví dụ emoji được tạo bằng Character.toChars để không phụ thuộc việc trình biên dịch đọc trực tiếp ký tự ngoài BMP trong tệp nguồn.
- Các hàm **không sửa đầu vào**; chúng chỉ đọc chuỗi, xây dãy code point và bảng DP.
- Tất cả ví dụ dùng quan hệ **so sánh đúng bằng giữa code point**; không có so sánh gần đúng, bỏ dấu hoặc không phân biệt hoa thường.

### Độ phức tạp

| Hàm | Số lượt chuyển trạng thái | Bộ nhớ DP | Có cần số lớn? |
| --- | --- | --- | --- |
| count2D | O(nm) | O(nm) ô | BigInteger chính xác |
| count1D | O(nm) | O(m) ô | BigInteger chính xác |
| countModulo | O(nm) | O(m) ô | Không, chỉ tính phần dư |

Ba hàm còn tạo dãy code point kích thước O(n+m) để thể hiện Unicode rõ ràng. Vì thế, nếu tính **toàn bộ bộ nhớ phụ**, count1D và countModulo có O(n+m) ô phần tử nguyên cùng O(m) ô DP; count2D có O(nm) ô DP cộng O(n+m) cho chuỗi đã giải mã. Có thể tránh mảng code point của nguồn bằng cách duyệt IntStream/offset thích hợp nếu cần giảm bộ nhớ, nhưng phải giữ đúng chỉ số Unicode và thứ tự cập nhật.

BigInteger có chi phí theo độ dài bit, nên không nên hiểu O(nm) ô hoặc phép cộng là số byte/thời gian tuyệt đối độc lập với độ lớn đáp án.

## 8. Chứng minh tính đúng bằng quy nạp

Một bài toán đếm thường dễ sai khi các nhóm trường hợp **đếm trùng** hoặc **bỏ sót**. Với DP này, phân chia theo việc có sử dụng phần tử cuối của tiền tố nguồn là một phép chia rõ ràng và rời nhau.

**Mệnh đề:** dp[i][j] bằng số bộ j chỉ số tăng chọn từ i vị trí đầu S sao cho các ký tự được chọn tạo đúng j ký tự đầu T.

**Cơ sở:** với j=0, chỉ có bộ chỉ số rỗng, nên dp[i][0]=1. Với i=0,j>0, không có bộ j chỉ số nào, nên dp[0][j]=0. Ô dp[0][0]=1 phù hợp cả hai.

**Bước quy nạp:** giả sử toàn bộ trạng thái dùng i-1 vị trí nguồn đã đúng. Với một bộ chỉ số hợp lệ tạo T[0..j):

- Nếu bộ không chứa i-1, nó là một bộ được tính tại dp[i-1][j].
- Nếu bộ có chứa i-1, vì chỉ số tăng, i-1 buộc là chỉ số cuối. Chỉ có thể xảy ra khi S[i-1]=T[j-1]; bỏ i-1 cho một bộ được đếm tại dp[i-1][j-1].

Hai nhóm không giao nhau và mọi bộ hợp lệ thuộc đúng một nhóm. Do vậy cộng hai số cách (hoặc chỉ giữ nhánh bỏ nếu không khớp) cho dp[i][j] đúng. Theo quy nạp, dp[n][m] đúng.

**Đối với 1D:** sau i ký tự nguồn, ways[j] giữ dp[i][j]. Trước khi xử lý ký tự mới, cập nhật j giảm dần đảm bảo ways[j-1] chưa bị thay ở bước hiện tại; vì thế công thức một chiều thực hiện đúng chuyển trạng thái từ hàng i sang i+1. Trạng thái j=0 giữ 1 và không bị sửa. Bất biến duy trì đến khi xử lý hết n ký tự.

**Đối với modulo:** phép cộng và phép lấy phần dư tương thích: (a+b) mod M = ((a mod M)+(b mod M)) mod M. Do đó tính mod M ở từng bước cho cùng phần dư với việc tính kết quả nguyên chính xác rồi lấy mod một lần ở cuối. Lưu ý cách này **không phục hồi** được giá trị nguyên ban đầu từ phần dư.

## 9. Điều gì thay đổi khi đề bài yêu cầu khác?

Các từ “đếm dãy con” có thể chỉ những bài khác nhau. Hãy xác định kết quả cần đếm trước khi tái sử dụng DP.

| Biến thể câu hỏi | Bài này giải được trực tiếp? | Sự khác biệt |
| --- | --- | --- |
| Đếm số **bộ vị trí** tạo đúng T từ S | Có | Hai bộ vị trí khác nhau được tính riêng |
| Kiểm tra có tồn tại T như một subsequence của S | Không cần DP đếm | Hai con trỏ O(n+m) đủ cho một truy vấn |
| Đếm số lần T xuất hiện như **substring liên tiếp** | Không | Chỉ được chọn các vị trí kề nhau; có thể dùng thuật toán tìm mẫu |
| Đếm số **chuỗi subsequence khác nhau** của S | Không | Các bộ chỉ số tạo cùng nội dung thường phải gộp, cần DP khử trùng |
| Tìm **độ dài LCS** của S và T | Không | Bài tối ưu hóa, công thức max thay vì cộng |
| Đếm số **LCS tối ưu khác nhau** | Không trực tiếp | Phải kết hợp DP độ dài với đếm và kiểm soát trùng |
| Liệt kê **mọi bộ vị trí** tạo T | Không đủ chỉ trả số | Số đầu ra có thể là rất lớn; cần truy vết tất cả nhánh |
| Đếm subsequence khớp T theo modulo | Có, thay kiểu số | Mỗi phép cộng thực hiện modulo |
| Có ký tự đại diện, wildcard hoặc quy tắc so khớp tùy biến | Cần thiết kế lại điều kiện match | Phải xác định liệu các nhánh vẫn rời nhau và có bao nhiêu cách cho từng vị trí |

### Kiểm tra tồn tại khác đếm số cách

Nếu chỉ hỏi “T có là subsequence của S không?”, dùng hai con trỏ:

~~~text
j = 0
for each value x in S:
    if j < len(T) and x == T[j]:
        j += 1
return j == len(T)
~~~

Thuật toán tồn tại duyệt S một lần và không cần đếm mọi cách. Nó có thể trả true ngay cả khi có hàng triệu cách chọn chỉ số. Việc dùng DP O(nm) cho một câu hỏi chỉ cần Boolean thường không cần thiết.

### Liệt kê mọi cách có thể đắt hơn đếm

Với n ký tự 'a' và m≈n/2 ký tự 'a', số bộ vị trí tạo T xấp xỉ hệ số nhị thức trung tâm và tăng rất nhanh. DP có thể tính **số lượng** bằng số trạng thái đa thức (với BigInteger), nhưng để **liệt kê từng bộ vị trí** thì chương trình phải xuất số kết quả khổng lồ, nên không thể kỳ vọng tổng thời gian O(nm).

Nếu cần chỉ một cách chọn vị trí, cách đơn giản là đi theo hai con trỏ từ trái sang phải, lấy ký tự khớp sớm nhất; còn nếu cần một cách với tiêu chí phụ (nhỏ nhất theo từ điển, ít khoảng trống nhất), tiêu chí đó phải được định nghĩa và giải riêng.

## 10. Unicode, ký tự và ý nghĩa của “giống nhau”

Trong Java, String.length() và charAt() làm việc theo **đơn vị mã UTF-16**. Một ký tự Unicode ngoài BMP (như U+1F600) chiếm hai char. Nếu thuật toán tính chỉ số và ký tự bằng charAt thì “độ dài” đang là độ dài UTF-16, không nhất thiết là số Unicode code point hay số cụm chữ người dùng nhìn thấy.

Ví dụ Java dùng codePoints().toArray() nên chỉ số trong DP tương ứng với **Unicode code point**:

- Chuỗi gồm hai lần U+1F600 có hai code point nhưng bốn đơn vị mã UTF-16.
- Chọn một lần U+1F600 từ hai code point giống nhau có **hai** cách theo vị trí, nên kết quả ví dụ là 2.
- Không được tính hai nửa surrogate như hai vị trí độc lập nếu đặc tả là chọn các ký tự/code point.

Tuy nhiên, **code point không đồng nghĩa với grapheme cluster**. Một ký tự có dấu có thể được biểu diễn bằng một code point tiền tổ hợp hoặc một chuỗi chữ cơ sở cộng dấu tổ hợp. Hai chuỗi nhìn giống nhau có thể không bằng nhau khi so từng code point.

Nếu đề yêu cầu tương đương ký tự theo ngôn ngữ tự nhiên, có thể cần chuẩn hóa như Normalizer.Form.NFC trước, hoặc một chiến lược phân đoạn grapheme/so sánh tùy locale. **Thay đổi chuẩn hóa sẽ thay đổi bài toán đếm** và đôi khi thay cả số vị trí, nên phải công bố rõ trước khi áp dụng.

Với dữ liệu không phải chuỗi (ví dụ int[], token[], danh sách sự kiện), công thức DP không đổi; chỉ thay cách so S[i] và T[j]. Nếu đối tượng có phương thức equals, quan hệ so khớp cần nhất quán và không bị thay đổi trong lúc tính.

## 11. Tối ưu hóa và đánh đổi thực tế

### 11.1 Loại trường hợp không thể ngay từ đầu

- Nếu m=0, có chính xác một cách, kể cả khi n=0.
- Nếu m>n, không có cách nào.
- Nếu mục tiêu cần ký tự hoặc phần tử mà nguồn không có đủ số lần xuất hiện, kết quả bằng 0. Có thể tiền kiểm đếm tần suất, nhưng chi phí này không nhất thiết có lợi trên dữ liệu nhỏ.
- Nếu n và m lớn, 1D giảm từ O(nm) ô xuống O(m) ô DP; tuy nhiên vẫn cần O(nm) chuyển trạng thái trong cách làm tiêu chuẩn.

Nếu chỉ có một đích và một nguồn, O(nm) thường là lựa chọn vững chắc. Nếu **cùng một nguồn được hỏi với rất nhiều đích**, có thể cân nhắc bảng vị trí ký tự, automaton chỉ vị trí tiếp theo hoặc phương pháp nhiều mẫu, nhưng cần phân tích loại truy vấn và không được mặc định chúng tính **số cách** với cùng chi phí như kiểm tra tồn tại.

### 11.2 Dùng mảng hay Map?

Khi m là độ dài đích, một mảng ways[m+1] trực tiếp thường đơn giản và có locality tốt. Nếu trạng thái là cặp nhiều chiều thưa hoặc đồ thị trạng thái lớn, một Map để memoization có thể tránh cấp phát mọi trạng thái, nhưng đổi lại mất overhead hash, boxing và cấp phát đối tượng. Không nên chuyển DP dày sang HashMap chỉ vì nghĩ “cache luôn nhanh hơn”.

### 11.3 Khi nào giữ 2D dù tốn RAM?

Bảng 2D hữu ích để:

- Vẽ bảng, kiểm thử từng bước và chứng minh công thức.
- Truy vết số cách qua từng nhánh theo tiền tố.
- Phân tích các trạng thái trung gian sau một số ký tự nguồn.
- So sánh với kết quả một chiều để phát hiện lỗi hướng cập nhật.

Nếu chỉ cần một tổng cuối cùng, 1D thường phù hợp hơn. Nếu cần báo cáo cả một ma trận dp[i][j], không thể xóa toàn bộ các hàng mà vẫn đáp ứng đúng yêu cầu xuất dữ liệu trung gian.

### 11.4 Chi phí đầu ra và BigInteger

Với trường hợp nhiều cách, BigInteger chính xác có thể dài hàng nghìn chữ số. Không chỉ CPU cộng số, việc chuyển thành chuỗi để in cũng có chi phí theo số chữ số. Với các bài có yêu cầu modulo, dùng modulo xuyên suốt thường tiết kiệm tài nguyên rõ rệt.

Nếu người dùng không yêu cầu mod và số cách có thể vượt long, trả một long âm do tràn là **sai về mặt toán học**, không phải “xấp xỉ”. Cần chọn BigInteger, kiểm tra tràn hoặc yêu cầu giới hạn đầu vào chặt hơn.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nhầm subsequence với substring | Đếm thiếu vì bắt các ký tự liền nhau | Cho phép bỏ qua vị trí nguồn |
| Nhầm “số bộ vị trí” với “số chuỗi phân biệt” | Đếm trùng theo yêu cầu khác | Đặc tả rõ đối tượng được đếm |
| Đặt dp[i][0]=0 | Mất mọi cách bắt đầu khớp T | Đặt bằng 1 cho mục tiêu rỗng |
| Dùng max thay phép cộng | Chỉ giữ một nhánh thay vì đếm cả hai | Cộng skip + take khi ký tự khớp |
| Cộng nhánh take dù ký tự không khớp | Đếm các cách không tạo đúng T | Chỉ cộng khi S[i-1]==T[j-1] |
| Duyệt j tăng khi nén 1D | Một vị trí nguồn được dùng nhiều lần | Duyệt j từ m về 1 |
| Không khởi tạo BigInteger[] | NullPointerException khi add | Arrays.fill(..., BigInteger.ZERO) |
| Dùng int/long khi đáp án quá lớn | Tràn số, có thể thành số âm | BigInteger hoặc modulo theo yêu cầu |
| Lấy modulo sau khi đã tràn kiểu số | Phần dư sai | Lấy modulo từng bước bằng kiểu trung gian đủ rộng |
| Quên mục tiêu rỗng | Trả 0 thay vì 1 | Kiểm thử S="", T="" và T="" |
| Đếm theo char nhưng báo theo Unicode code point | Sai ý nghĩa chỉ số với surrogate pair | Dùng codePoints() nếu cần code point |
| So sánh chuỗi đã/không chuẩn hóa lẫn nhau | Kết quả khác kỳ vọng nghiệp vụ | Định nghĩa chuẩn hóa và equality |
| Duyệt không đúng thứ tự i,j trong 2D | Dùng ô chưa được tính | Duyệt hàng nguồn tăng dần |
| Liệt kê tất cả cách khi chỉ cần số lượng | Bùng nổ thời gian và đầu ra | DP đếm, không sinh từng cách |

**Mẫu tự kiểm tra tốt nhất:** hãy luôn thử S="a", T="aa". Thuật toán đúng phải trả **0**. Nếu thuật toán 1D trả 1, khả năng rất cao là bạn đã cập nhật chiều j sai và dùng lại cùng vị trí nguồn.

## 13. Kiểm thử theo thuộc tính và đối chứng brute force

Không chỉ kiểm thử một ví dụ có kết quả 3. Để chắc rằng công thức và quy ước đếm đúng, cần nhiều nhóm kiểm thử.

### Các tính chất bất biến

1. **Không âm:** số cách chính xác luôn ≥0.
2. **Target rỗng:** count(S,"")=1 với mọi S.
3. **Đích dài hơn nguồn:** nếu m>n thì count(S,T)=0.
4. **Giữ nguyên thứ tự:** S="ab", T="ba" phải trả 0.
5. **Tăng tiền tố nguồn:** khi thêm một ký tự vào cuối S, số cách tạo cùng T không thể giảm (chỉ có thêm lựa chọn); điều này đúng cho số đếm nguyên chính xác, **không** áp dụng đơn điệu cho phần dư modulo.
6. **Nếu S=T và độ dài bằng nhau:** có đúng một cách chọn tất cả các vị trí.
7. **Nếu toàn chữ giống nhau:** count("a"^n,"a"^m)=C(n,m) khi 0≤m≤n.
8. **2D và 1D phải bằng nhau:** nếu cùng một quy ước ký tự/so khớp.
9. **Modulo khớp phần dư:** countModulo(S,T,M) bằng count1D(S,T).mod(BigInteger.valueOf(M)) khi M>0.
10. **Không sửa dữ liệu nguồn:** các hàm đếm không có quyền thay đổi chuỗi đầu vào.

### Bộ kiểm thử điển hình

| Nguồn S | Đích T | Đáp án | Mục đích |
| --- | --- | ---: | --- |
| "" | "" | 1 | Hai dãy đều rỗng |
| "" | "a" | 0 | Không có vị trí nguồn |
| "abc" | "" | 1 | Dãy con rỗng duy nhất |
| "a" | "aa" | 0 | Không tái sử dụng một chỉ số |
| "aab" | "ab" | 2 | Hai vị trí a có thể thay thế nhau |
| "aaa" | "aa" | 3 | Đếm bộ chỉ số thay vì nội dung |
| "aaaaa" | "aaa" | 10 | Tính nhị thức |
| "rabbbit" | "rabbit" | 3 | Bộ dữ liệu điển hình |
| "babgbag" | "bag" | 5 | Nhiều lựa chọn xen kẽ |
| "abcdef" | "ace" | 1 | Bỏ qua vị trí nguồn |
| "abcdef" | "cae" | 0 | Không được đảo thứ tự |
| "😀😀" | "😀" | 2 | Hai Unicode code point giống nhau |
| "a" lặp 70 | "a" lặp 35 | 112186277816662845432 | Vượt long |

### Đối chứng brute force cho n nhỏ

Với nguồn có n≤20, có thể xét mọi bitmask từ 0 đến 2^n-1. Mỗi bitmask biểu diễn tập vị trí được chọn; khi duyệt chỉ số nguồn tăng dần, ghi các phần tử có bit 1. Nếu dãy thu được bằng T thì tăng bộ đếm.

~~~text
bruteForce(S,T):
    count = 0
    for mask = 0 .. (2^len(S))-1:
        subsequence = values at set bits, in increasing index order
        if subsequence == T:
            count += 1
    return count
~~~

Cách này tốn O(n×2^n) trong triển khai đơn giản, chỉ dùng làm **oracle cho dữ liệu nhỏ**, không phải giải pháp chính. Sinh ngẫu nhiên các cặp chuỗi trên alphabet nhỏ như {'a','b','c'} và đối chiếu 2D, 1D, brute force là cách tốt để phát hiện lỗi base case và lỗi duyệt j. Với modulo, so phần dư của kết quả BigInteger với hàm modulo.

## 14. Bài tập tự luyện

1. Dựng bảng dp[i][j] cho S="aaba", T="aa", ghi cả hàng i=0 và cột j=0. Từ các bộ chỉ số hợp lệ, tính số cách bằng tay rồi so với dp[n][m].
2. Với S="babgbag", T="bag", tự đánh số vị trí từ 0 và liệt kê năm bộ chỉ số b–a–g tăng dần; giải thích vì sao mọi bộ đều được đếm đúng một lần.
3. Viết phiên bản DP 2D dùng long với Math.addExact để **phát hiện tràn**. Khi thử S="a"^70, T="a"^35, so hành vi với BigInteger.
4. Xóa vòng j giảm của 1D và thay thành tăng để quan sát lỗi với S="a", T="aa"; trình bày vai trò của hàng DP cũ.
5. Viết hàm đếm cách tạo **dãy số nguyên target** từ dãy số nguyên source; chứng minh công thức không phụ thuộc kiểu ký tự.
6. Thêm tham số modulus dương vào lời giải 1D, kiểm thử modulus=1, modulus=7, modulus=1_000_000_007, và đối chiếu phần dư BigInteger.
7. Chứng minh công thức C(n,m) khi mọi ký tự giống nhau bằng cả lập luận chọn m vị trí và truy hồi của tam giác Pascal.
8. Giải bài toán **tồn tại** target là subsequence của source bằng hai con trỏ. So sánh O(n+m) với O(nm) của bài đếm, và cho ví dụ số cách rất lớn nhưng kiểm tra tồn tại vẫn đơn giản.
9. Với hai cách biểu diễn Unicode đã hợp thành và dấu tổ hợp, phân tích khi nào chuẩn hóa về NFC làm thay đổi số vị trí hoặc tính bằng nhau; tự viết các ca kiểm thử tương ứng.
10. Nếu cần trả **một bộ chỉ số** thay vì số cách, đề xuất greedy tìm vị trí khớp sớm nhất; nếu phải trả **tất cả bộ chỉ số**, giải thích vì sao thời gian xuất kết quả có thể tăng theo cấp số mũ.

**Ghi nhớ:** công thức đếm dãy con đích là **bỏ ký tự nguồn cuối** cộng **lấy ký tự ấy nếu khớp ký tự đích cuối**. Khởi tạo đích rỗng có đúng **một** cách; khi nén xuống 1D phải duyệt chỉ số đích **giảm dần** để không dùng lại cùng vị trí nguồn. Trước khi chọn int, long, BigInteger hay modulo, phải xác định giới hạn đáp án và yêu cầu chính xác của bài toán.
