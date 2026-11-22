# Băm cuộn và thuật toán Rabin–Karp

## Mục tiêu học tập

**Băm cuộn** (*rolling hash*) là cách cập nhật mã băm của một cửa sổ chuỗi khi cửa sổ dịch sang phải một vị trí mà không phải đọc lại toàn bộ cửa sổ. **Rabin–Karp** ứng dụng kỹ thuật này để tìm những vị trí xuất hiện của một **mẫu** (*pattern*) trong **văn bản** (*text*). Nội dung thuộc nhóm **Tìm kiếm chuỗi**.

Bài này tập trung vào: hash đa thức, công thức cuộn O(1), lựa chọn cơ số/môđun, **va chạm hash**, xác minh khớp chính xác, các trường hợp biên, chứng minh tính đúng, phân tích thời gian, mã **Java 17+** và bài tập. Điểm cần nhớ: **hai hash bằng nhau chưa bảo đảm hai đoạn văn bản bằng nhau**. Bước so sánh ký tự thật có thể loại khớp giả nhưng làm tăng cận thời gian xấu nhất.

Sau bài này, bạn có thể:

1. Mô tả bài tìm mọi vị trí khớp, kể cả khớp chồng lấn.
2. Tính hash đa thức bằng công thức lặp và lấy modulo đúng cách.
3. Suy ra công thức bỏ ký tự cũ, nhân cơ số và thêm ký tự mới.
4. Phân biệt thời gian **quét hash O(n+m)** với thời gian **xác minh ứng viên O(Cm)**.
5. Triển khai hai môđun và so sánh thật để đảm bảo kết quả chính xác.
6. Xử lý mẫu rỗng, mẫu dài hơn text, emoji UTF-16 và phân biệt hoa/thường.
7. Biết khi nào KMP, Z-function hoặc prefix hash phù hợp hơn.
8. Kiểm chứng mã bằng các bộ test độc lập.

---

## 1. Phát biểu bài toán

Cho `text` độ dài n và `pattern` độ dài m. Ta cần tìm tất cả chỉ số bắt đầu i mà:

\[
0\le i\le n-m,
\]

và:

\[
text[i+j]=pattern[j]\quad \text{với mọi }0\le j<m.
\]

Các chỉ số trong bài bắt đầu từ **0**. Đoạn `text[i..i+m)` chứa m ký tự ở vị trí i tới i+m−1.

Ví dụ:

```text
text = "abracadabra"
pattern = "abra"
Kết quả: [0, 7]
```

Vị trí 0 và 7 đều bắt đầu đoạn dài 4 đúng bằng `"abra"`.

### Khớp chồng lấn

```text
text = "aaaaa"
pattern = "aa"

Vị trí 0: aa
Vị trí 1: aa
Vị trí 2: aa
Vị trí 3: aa

Kết quả: [0, 1, 2, 3]
```

Một match ở i không làm ta bỏ vị trí i+1. Nếu nhảy thêm m sau khi thấy match, sẽ bỏ các lần xuất hiện **chồng lấn**. Trong bài này ta luôn tìm **tất cả** match.

### Mẫu rỗng và mẫu quá dài

Quy ước của chương trình:

- Nếu `m=0`, chuỗi rỗng khớp ở **mọi ranh giới giữa code unit**, tức các vị trí `0,1,...,n`. Với text="abc", kết quả `[0,1,2,3]`.
- Nếu text và pattern đều rỗng, kết quả `[0]`.
- Nếu `m>n`, không có cửa sổ đủ dài, nên trả `[]`.

Các nền tảng có thể quy ước khác với mẫu rỗng. Khi giải đề, phải ưu tiên đặc tả của đề; đây là quy ước được chọn cho ví dụ.

---

## 2. Cách ngây thơ và động cơ băm cuộn

Cách trực tiếp thử từng vị trí i và so tối đa m ký tự:

```text
for i = 0..n-m:
    match = true
    for j = 0..m-1:
        if text[i+j] != pattern[j]:
            match = false
            break
    if match:
        output i
```

Trong trường hợp xấu nhất, cách này thực hiện `(n-m+1)m` phép so sánh, là **O(nm)**.

Ví dụ text gồm rất nhiều ký tự 'a', còn pattern gồm m−1 ký tự 'a' rồi 'b': hầu hết các cửa sổ khớp dài ở đầu rồi mới sai ở ký tự cuối.

**Ý tưởng Rabin–Karp:** tính một dấu vân tay số nguyên ngắn của pattern và của mỗi cửa sổ độ dài m. Nếu hash khác nhau, hai chuỗi chắc chắn khác nhau và không phải kiểm tra ký tự nữa. Nếu hash trùng nhau, ta mới kiểm tra chi tiết để loại **collision**.

Trở ngại là tính hash từng cửa sổ từ đầu tốn O(m). **Rolling hash** giải quyết bằng cách tính hash mới từ hash cũ trong **O(1)**.

---

## 3. Hash đa thức

Chọn một cơ số B, một môđun M, và ánh xạ mỗi ký tự c thành giá trị nguyên `value(c)`.

Với chuỗi `s_0s_1...s_{m-1}`:

\[
H(s)=\left(\sum_{i=0}^{m-1}
value(s_i)B^{m-1-i}\right)\bmod M.
\]

Ta có thể tính bằng vòng lặp:

```text
h = 0
for mỗi ký tự c từ trái sang phải:
    h = (h * B + value(c)) % M
```

Với cách này, hash luôn thuộc miền `[0,M)` và không cần tính số nguyên `B^m` rất lớn.

### Ví dụ tính bằng tay

Chỉ để minh họa, đặt a=1, b=2, B=31, M=101.

```text
Chuỗi "aba"
H = (1*31^2 + 2*31 + 1) mod 101
  = 1024 mod 101
  = 14
```

Với `"bab"`:

```text
H = (2*31^2 + 1*31 + 2) mod 101
  = 1955 mod 101
  = 36
```

Nếu hash khác nhau, hai đoạn không thể bằng nhau. Nếu hash bằng nhau, chúng **có thể** khác nhau vì không gian hash hữu hạn.

### Hash không phải mã định danh duy nhất

Lấy B=2, M=5 và a=1,b=2,c=3:

\[
H("bc")=(2\cdot2+3)\bmod5=2,
\]

\[
H("ca")=(3\cdot2+1)\bmod5=2.
\]

Hai chuỗi `"bc"` và `"ca"` **khác nhau** nhưng hash bằng nhau. Đây là **hash collision**.

Theo nguyên lý Dirichlet, nếu chỉ có M giá trị hash mà xét hơn M chuỗi, phải tồn tại collision. Dùng hai môđun vẫn chỉ tạo số hữu hạn cặp hash; nó giảm rủi ro trong nhiều tình huống, nhưng không biến hash thành phép so sánh tuyệt đối.

---

## 4. Công thức băm cuộn trong O(1)

Giả sử cửa sổ hiện tại gồm m ký tự:

```text
old: [a0, a1, a2, ..., a(m-1)]
new: [a1, a2, ..., a(m-1), x]
```

Hash cũ:

\[
h=\left(value(a_0)B^{m-1}
+value(a_1)B^{m-2}
+\cdots+value(a_{m-1})\right)\bmod M.
\]

Đặt:

\[
P=B^{m-1}\bmod M.
\]

Loại đóng góp của ký tự đầu:

\[
removed=(h-value(a_0)\cdot P)\bmod M.
\]

Sau đó dịch các hệ số còn lại bằng cách nhân B rồi thêm ký tự mới x:

\[
\boxed{h_{\text{new}}=(removed\cdot B+value(x))\bmod M.}
\]

Đó là **rolling hash O(1)** khi biết h và P.

### Làm phép trừ modulo an toàn

Java dùng toán tử `%` nhưng số âm có thể cho kết quả âm. Nếu h và phần đóng góp cần trừ đều đã chuẩn hóa vào `[0,M)`, ta tính:

```java
long remove = value(outgoing) * highPower % mod;
long rest = (oldHash - remove + mod) % mod;
long next = (rest * BASE + value(incoming)) % mod;
```

Vì `oldHash-remove` lớn hơn −M và nhỏ hơn M, cộng M một lần trước `% mod` là đủ để có kết quả không âm.

### Vì sao là B^(m-1), không phải B^m?

Trong hash của cửa sổ dài m, ký tự đầu đứng trước m−1 ký tự và có hệ số `B^{m-1}`. Nếu trừ nhầm `B^m`, mọi hash sau cửa sổ đầu sẽ sai.

Đặc biệt khi m=1, `P=B^0=1`. Công thức cuộn bỏ ký tự duy nhất rồi thêm ký tự mới, đúng như mong đợi.

### Mô phỏng cửa sổ "ababa"

Vẫn dùng B=31, M=101, a=1,b=2, m=3.

\[
P=31^2\bmod101=52.
\]

Cửa sổ đầu `"aba"` có h=14.

Trượt sang `"bab"`: rời 'a'=1, vào 'b'=2.

\[
removed=(14-1\cdot52)\bmod101
=(-38)\bmod101=63.
\]

\[
h_{\text{new}}=(63\cdot31+2)\bmod101
=1955\bmod101=36.
\]

Trượt sang `"aba"` tiếp theo: rời 'b'=2, vào 'a'=1.

\[
removed=(36-2\cdot52)\bmod101
=(-68)\bmod101=33,
\]

\[
h_{\text{new}}=(33\cdot31+1)\bmod101
=1024\bmod101=14.
\]

| Bắt đầu | Cửa sổ | Hash |
| ---: | --- | ---: |
| 0 | aba | 14 |
| 1 | bab | 36 |
| 2 | aba | 14 |

Với pattern="aba", hai cửa sổ hash bằng pattern ở vị trí **0 và 2**; xác minh ký tự cho hai match thật.

---

## 5. Thuật toán Rabin–Karp chuẩn

Với m>0 và m≤n:

1. Tính hash pattern trong O(m).
2. Tính hash cửa sổ đầu dài m trong O(m).
3. Tính `P=B^{m-1}\bmod M`.
4. Với từng `start=0..n-m`, so hash cửa sổ với hash mẫu.
5. Hash khác → bỏ qua cửa sổ.
6. Hash bằng → **xác minh ký tự thật**; chỉ thêm start nếu thật sự khớp.
7. Nếu start chưa phải cửa sổ cuối, dùng công thức rolling để đến start+1.

Giả mã:

```text
RABIN_KARP(text, pattern):
    n = length(text)
    m = length(pattern)
    result = []

    if m == 0:
        return [0, 1, ..., n]

    if m > n:
        return []

    patternHash = HASH(pattern)
    windowHash = HASH(text[0..m))
    power = B^(m-1) mod M

    for start = 0..n-m:
        if windowHash == patternHash:
            if text[start..start+m) == pattern:
                result.add(start)

        if start < n-m:
            windowHash = ROLL(
                windowHash,
                text[start],
                text[start+m],
                power)

    return result
```

### Bất biến cửa sổ

Trước lần so sánh tại start=i:

\[
windowHash=H(text[i..i+m)).
\]

Cơ sở: giá trị tại i=0 được tính trực tiếp từ m ký tự đầu. Bước quy nạp: công thức rolling trừ đúng ký tự đầu, nhân B và thêm ký tự mới, nên tạo hash đúng cho cửa sổ i+1.

Nhờ vậy, nếu một đoạn **thật sự khớp**, nó luôn có hash bằng pattern và được đưa vào bước xác minh. Không có **false negative** do bộ lọc hash nếu công thức tính nhất quán.

### Vì sao cần xác minh ký tự thật?

Đảo chiều suy luận “hash bằng nhau ⇒ chuỗi bằng nhau” là sai vì collision. Do đó bản Java sử dụng `text.regionMatches(start, pattern, 0, m)` sau khi hash trùng. Hàm này so trực tiếp m code unit và không chấp nhận một đoạn khác ký tự.

Kết hợp bất biến hash và xác minh thật:

- **Không bỏ sót match thật:** mọi vị trí đều được duyệt, một match thật luôn có hash trùng.
- **Không nhận match giả:** thêm vị trí chỉ khi `regionMatches` xác nhận chính xác.

### Khớp chồng lấn

Vòng lặp tăng start từng đơn vị, kể cả sau một match. Đó là lý do `"aa"` trong `"aaaaa"` trả `[0,1,2,3]` thay vì chỉ `[0,2]`.

### Cửa sổ cuối

Cửa sổ cuối có `start=n-m`. Nếu tiếp tục cuộn, mã sẽ muốn đọc `text.charAt(n)` — chỉ số không hợp lệ. Vì vậy roll **chỉ khi `start<n-m`**.

---

## 6. Hash kép và lựa chọn số học trong Java

Một hash modulo M có thể va chạm. Ta có thể tính đồng thời hai hash dùng môđun nguyên tố khác nhau:

\[
M_1=1\,000\,000\,007,\quad
M_2=1\,000\,000\,009.
\]

Hash một chuỗi là cặp:

\[
(H_{M_1}(s),H_{M_2}(s)).
\]

Chỉ khi **cả hai thành phần** trùng mới xác minh ký tự. Việc dùng hai môđun giảm khả năng một collision đơn lẻ lọt qua bộ lọc trên nhiều dữ liệu thông thường.

**Cảnh báo:** hash kép **không loại bỏ collision về mặt toán học**. Nếu base/môđun cố định và đầu vào đối kháng, không được tự khẳng định xác suất collision bằng một con số nhỏ mà không có mô hình ngẫu nhiên hóa. Để đúng tuyệt đối, giữ bước `regionMatches`.

### Hằng số của ví dụ

```java
BASE = 911_382_323L;
MOD1 = 1_000_000_007L;
MOD2 = 1_000_000_009L;
```

Cơ số nhỏ hơn hai môđun. Chương trình tính giá trị ký tự bằng `(long)ch+1`, trong đó `ch` là một **UTF-16 code unit** kiểu Java `char` (0..65535).

Hash, môđun, lũy thừa và phép nhân đều dùng **long**. Với bộ hằng này, tích lớn nhất gần `9.11\cdot10^{17}`, vẫn thấp hơn `Long.MAX_VALUE≈9.22\cdot10^{18}`. Nếu đổi BASE/MOD thành số lớn hơn, phải **đánh giá lại nguy cơ overflow**; chỉ viết `%` sau khi nhân không cứu được phép nhân đã tràn.

---

## 7. Java 17+ chạy được — Rabin–Karp hai môđun

Tệp **`RabinKarpRollingHashDemo.java`** triển khai rolling hash với **O(1) trạng thái băm**, không tạo substring cho mỗi cửa sổ. Nó trả danh sách tất cả vị trí theo UTF-16, dùng hai môđun và xác minh thật.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class RabinKarpRollingHashDemo {

    private static final long BASE = 911_382_323L;
    private static final long MOD1 = 1_000_000_007L;
    private static final long MOD2 = 1_000_000_009L;

    // One Java char is one UTF-16 code unit.
    private static long value(char ch) {
        return (long) ch + 1L;
    }

    private static long appendHash(
            long current, char ch, long mod) {

        return (current * BASE + value(ch)) % mod;
    }

    private static long rollHash(
            long oldHash,
            char outgoing,
            char incoming,
            long highPower,
            long mod) {

        long removed =
                value(outgoing) * highPower % mod;

        long withoutFirst =
                (oldHash - removed + mod) % mod;

        return (withoutFirst * BASE + value(incoming)) % mod;
    }

    public static List<Integer> findAll(
            String text, String pattern) {

        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(pattern, "pattern");

        int n = text.length();
        int m = pattern.length();

        List<Integer> positions = new ArrayList<>();

        if (m == 0) {
            for (int i = 0; i <= n; i++) {
                positions.add(i);
            }
            return positions;
        }

        if (m > n) {
            return positions;
        }

        long power1 = 1;
        long power2 = 1;

        for (int i = 1; i < m; i++) {
            power1 = power1 * BASE % MOD1;
            power2 = power2 * BASE % MOD2;
        }

        long pattern1 = 0;
        long pattern2 = 0;
        long window1 = 0;
        long window2 = 0;

        for (int i = 0; i < m; i++) {
            pattern1 = appendHash(
                    pattern1, pattern.charAt(i), MOD1);
            pattern2 = appendHash(
                    pattern2, pattern.charAt(i), MOD2);

            window1 = appendHash(
                    window1, text.charAt(i), MOD1);
            window2 = appendHash(
                    window2, text.charAt(i), MOD2);
        }

        for (int start = 0; start <= n - m; start++) {
            if (window1 == pattern1
                    && window2 == pattern2
                    && text.regionMatches(
                            start, pattern, 0, m)) {

                positions.add(start);
            }

            if (start < n - m) {
                char outgoing = text.charAt(start);
                char incoming = text.charAt(start + m);

                window1 = rollHash(
                        window1, outgoing, incoming,
                        power1, MOD1);

                window2 = rollHash(
                        window2, outgoing, incoming,
                        power2, MOD2);
            }
        }

        return positions;
    }

    // Tiny hash to demonstrate an actual collision.
    private static int toyHash(String text) {
        int hash = 0;

        for (int i = 0; i < text.length(); i++) {
            int digit = text.charAt(i) - 'a' + 1;
            hash = (hash * 2 + digit) % 5;
        }

        return hash;
    }

    public static void main(String[] args) {
        System.out.println(
                "Abracadabra abra: "
                        + findAll("abracadabra", "abra"));

        System.out.println(
                "Overlapping aa: "
                        + findAll("aaaaa", "aa"));

        System.out.println(
                "Overlapping aaa: "
                        + findAll("aaaaa", "aaa"));

        System.out.println(
                "Mississippi issi: "
                        + findAll("mississippi", "issi"));

        System.out.println(
                "Case sensitive: "
                        + findAll("ABCabc", "abc"));

        System.out.println(
                "Empty pattern: "
                        + findAll("abc", ""));

        System.out.println(
                "Both empty: "
                        + findAll("", ""));

        System.out.println(
                "Longer pattern: "
                        + findAll("abc", "abcd"));

        System.out.println(
                "Unicode UTF-16 positions: "
                        + findAll("a😀a😀", "😀"));

        System.out.println(
                "Toy hash bc: " + toyHash("bc"));

        System.out.println(
                "Toy hash ca: " + toyHash("ca"));

        System.out.println(
                "Toy collision: "
                        + (toyHash("bc") == toyHash("ca")));

        boolean nullRejected = false;

        try {
            findAll(null, "a");
        } catch (NullPointerException ex) {
            nullRejected = true;
        }

        System.out.println(
                "Null rejected: " + nullRejected);
    }
}
```

Biên dịch và chạy trên **JDK 17 trở lên**:

```bash
javac RabinKarpRollingHashDemo.java
java RabinKarpRollingHashDemo
```

**Đầu ra chính xác:**

```text
Abracadabra abra: [0, 7]
Overlapping aa: [0, 1, 2, 3]
Overlapping aaa: [0, 1, 2]
Mississippi issi: [1, 4]
Case sensitive: [3]
Empty pattern: [0, 1, 2, 3]
Both empty: [0]
Longer pattern: []
Unicode UTF-16 positions: [1, 4]
Toy hash bc: 2
Toy hash ca: 2
Toy collision: true
Null rejected: true
```

### Diễn giải các hàm

**value(char):** chuyển UTF-16 code unit thành số từ 1 đến 65536. Băm cặp ký tự theo cùng quy tắc ở text và pattern.

**appendHash:** nhân hash trước với BASE rồi thêm ký tự mới và lấy modulo. Lặp m lần tính được hash ban đầu trong O(m).

**rollHash:** tính lại hash sau khi cửa sổ dịch một ký tự. Bước `removed` trừ đóng góp ký tự rời cửa sổ, `withoutFirst` chuẩn hóa phần dư, rồi nhân BASE và thêm ký tự vào.

**findAll:** xử lý các trường hợp m=0 và m>n trước; tính hai hash mẫu và cửa sổ, rồi duyệt các start hợp lệ. Chỉ khi hai hash bằng nhau mới gọi `regionMatches`; do đó kết quả là khớp chính xác, không bị collision đánh lừa.

**toyHash:** cố tình dùng hash nhỏ B=2,M=5; hash `"bc"` và `"ca"` đều bằng 2 dù hai chuỗi khác nhau. Đây là ví dụ làm rõ lý do cần xác minh.

### Vì sao không tạo substring ở mỗi vị trí?

Trong nhiều Java hiện đại, gọi `text.substring(start,start+m)` nhiều lần có thể cấp phát hoặc chép dữ liệu mới. `regionMatches` so trực tiếp đoạn văn bản với pattern mà không yêu cầu tạo String cửa sổ. Nó chỉ được gọi cho ứng viên có hai hash trùng.

### Đầu ra cho mẫu rỗng

Với text dài n, có n+1 ranh giới hợp lệ cho chuỗi rỗng. Điều kiện m=0 được xử lý **trước** khi tính `BASE^{m-1}` vì số mũ sẽ âm và công thức rolling không có ý nghĩa với cửa sổ dài 0.

### Chỉ số Java UTF-16

`String.length()` và `String.charAt(i)` dùng **UTF-16 code unit**, không phải số code point hoặc grapheme cluster.

Trong `"a😀a😀"`, mỗi emoji `😀` chiếm **hai** code unit. Hai lần xuất hiện bắt đầu ở code-unit index 1 và 4, nên trả `[1,4]`. Nếu đề đòi index theo code point, cần chuyển đổi biểu diễn và ánh xạ index, không thể coi kết quả của `charAt` là code-point index.

Bản mã phân biệt hoa/thường: `"abc"` chỉ khớp ở index 3 của `"ABCabc"`. Nếu cần so khớp theo chuẩn hóa Unicode hoặc không phân biệt chữ, phải áp dụng biến đổi nhất quán lên **cả text và pattern** rồi xác định rõ cách ánh xạ kết quả về chuỗi gốc.

---

## 8. Chứng minh tính đúng

### 8.1. Bất biến rolling hash

Trước mỗi lần so tại vị trí i, `window1` và `window2` lần lượt là hash chính xác của `text[i..i+m)` theo hai môđun.

- **Cơ sở:** cửa sổ đầu được tính trực tiếp từ m ký tự `text[0..m)`.
- **Quy nạp:** công thức cuộn trừ đúng ký tự đầu có hệ số `BASE^{m-1}`, nhân BASE và thêm ký tự mới, tạo hash cửa sổ kế tiếp.

Bất biến đúng với mọi i hợp lệ.

### 8.2. Không bỏ match thật

Nếu `text[i..i+m)` bằng pattern thì toàn bộ code unit tương ứng bằng nhau. Hash theo cùng công thức và môđun cũng bằng nhau. Vị trí i đi qua hai phép thử hash, sau đó `regionMatches` trả true, nên i được thêm vào kết quả. Do vòng lặp xét **mọi vị trí i từ 0 tới n-m**, không match thật nào bị bỏ.

### 8.3. Không nhận match giả

Mã chỉ thêm i nếu `regionMatches` xác nhận đoạn text đúng bằng pattern. Nếu hash trùng do collision nhưng ký tự khác, xác minh trả false, nên i không được thêm.

Vì vậy thuật toán trả **đúng tất cả vị trí match theo UTF-16**.

### 8.4. Tính dừng

Với m>0 và m≤n, có đúng n−m+1 lượt kiểm tra cửa sổ. Mỗi roll dùng hữu hạn phép toán; so ký tự tốn tối đa m bước. Với m>n hoặc m=0, mã xử lý sớm. Do vậy mọi chuỗi đầu vào hữu hạn đều kết thúc.

---

## 9. Độ phức tạp chính xác

Ký hiệu:

- n: độ dài text.
- m: độ dài pattern.
- C: số cửa sổ có **hai hash bằng hash mẫu**, gồm cả match thật và collision.
- k: số match thật được trả (k≤C).

**Tiền xử lý:** tính hash hai chuỗi độ dài m và hai lũy thừa `BASE^{m-1}`, tốn **O(m)**.

**Quét hash:** có n−m+1 cửa sổ, mỗi roll dùng O(1) thao tác; tốn **O(n)**.

**Xác minh:** tối đa C ứng viên, mỗi ứng viên so tối đa m code unit; tốn **O(Cm)**.

Tổng thời gian của bản **có xác minh để bảo đảm đúng**:

\[
\boxed{O(n+m+Cm)}.
\]

Vì C có thể bằng n−m+1, cận xấu nhất là:

\[
\boxed{O(nm)}.
\]

Ví dụ text và pattern đều gồm 'a' lặp lại: rất nhiều cửa sổ **khớp thật**, nên mỗi `regionMatches` có thể so đủ m ký tự, dù **không xảy ra collision**.

Nếu bỏ xác minh, thuật toán thực hiện O(n+m) phép hash nhưng có thể nhận khớp giả; không còn bảo đảm chính xác tuyệt đối.

### Không gian

Rolling hash của mã chỉ giữ một số biến hash, modulo, power và vị trí: **O(1) bộ nhớ phụ**, không kể input và kết quả.

Danh sách k vị trí chiếm **O(k)**. Với mẫu rỗng, k=n+1 theo quy ước nên output chiếm O(n).

Nếu phải băm nhiều đoạn bất kỳ, có thể dùng **prefix hash** cần O(n) mảng phụ để trả hash của mỗi đoạn trong O(1).

---

## 10. Prefix hash: mở rộng từ rolling

Thay vì chỉ giữ hash của một cửa sổ, với nhiều truy vấn `text[l..r)` có thể tiền xử lý:

\[
pref[0]=0,
\]

\[
pref[i+1]=(pref[i]\cdot B+value(text[i]))\bmod M.
\]

Đồng thời:

\[
pow[0]=1,\quad
pow[i+1]=(pow[i]\cdot B)\bmod M.
\]

Hash của đoạn [l,r):

\[
\boxed{
H(l,r)=
(pref[r]-pref[l]\cdot pow[r-l])\bmod M.
}
\]

Sau phép trừ, phải chuẩn hóa modulo về số không âm.

### Vì sao công thức đúng?

Hash của prefix dài r gồm phần prefix dài l, đã bị nhân thêm `B^{r-l}`, cộng phần đoạn từ l tới r−1. Lấy hiệu loại phần đầu, để lại hash của đúng đoạn [l,r).

### Khi nào dùng?

- **Rolling cửa sổ cố định:** một mẫu và nhiều cửa sổ liên tiếp; O(1) bộ nhớ phụ.
- **Prefix hash:** nhiều truy vấn đoạn bất kỳ; O(n) tiền xử lý và O(n) bộ nhớ, rồi O(1) mỗi hash đoạn.
- **So sánh hai đoạn:** nếu độ dài khác nhau, phải kiểm tra độ dài trước; hash bằng nhau vẫn có thể collision.

---

## 11. So sánh các thuật toán tìm chuỗi

| Thuật toán | Ý tưởng | Thời gian xấu nhất | Kết quả chính xác? |
| --- | --- | --- | --- |
| Naive | So ký tự ở từng cửa sổ | `O(nm)` | Có |
| Rabin–Karp chỉ hash | Dùng rolling hash làm kết luận | `O(n+m)` phép hash | Không bảo đảm do collision |
| **Rabin–Karp + xác minh** | Hash lọc ứng viên, rồi so thật | `O(nm)`; cụ thể `O(n+m+Cm)` | **Có** |
| KMP | Prefix function để tránh so lại | `O(n+m)` | Có |
| Z-function | Tính độ dài prefix khớp | `O(n+m)` | Có |

### Khi nên dùng Rabin–Karp

Rabin–Karp có công thức rolling rõ ràng, dễ áp dụng khi cần so nhiều cửa sổ hoặc mở rộng sang substring hashing. Trong dữ liệu thông thường có ít ứng viên, hiệu năng có thể tốt.

### Khi nên dùng KMP

Nếu đề yêu cầu **đúng tuyệt đối và thời gian O(n+m) trong trường hợp xấu nhất**, KMP hoặc Z-function là lựa chọn phù hợp hơn, vì không có collision và không cần so lại m ký tự ở mỗi match.

### Nhiều pattern

Nếu nhiều mẫu có **cùng độ dài**, có thể tính hash các mẫu, nhóm chúng theo hash rồi quét văn bản một lần cho độ dài ấy; khi hash trùng cần xác minh mọi ứng viên liên quan. Nếu mẫu **khác độ dài**, cần nhóm theo độ dài hoặc dùng cấu trúc khác như trie/Aho–Corasick.

### Hash không phải công cụ bảo mật

Hash đa thức không phải cryptographic hash; không dùng nó làm chữ ký hoặc chứng chỉ chống giả mạo. Dữ liệu đối kháng có thể chủ động tạo collision.

---

## 12. Lỗi thường gặp

1. **Quên xử lý m=0**, khiến số mũ m−1 âm hoặc truy cập sai.
2. **Không kiểm tra m>n** trước khi đọc m ký tự đầu của text.
3. **Dùng int nhân hai số gần 10^9**, bị overflow trước phép modulo.
4. **Sai `BASE^{m-1}` thành `BASE^m`** khi trừ ký tự đầu.
5. **Quên chuẩn hóa phép trừ âm** trong Java.
6. **Nhân BASE trước khi bỏ ký tự đầu** nhưng vẫn dùng công thức trừ của thứ tự cũ.
7. **Không lấy modulo khi cập nhật cả hai hash**.
8. **Dùng chỉ một hash hoặc hai hash để kết luận bằng nhau tuyệt đối**, quên collision.
9. **Không xác minh ký tự thật** khi bài yêu cầu exact.
10. **Không cập nhật hash thứ hai** khi cửa sổ trượt.
11. **Nhảy thêm m sau match**, làm mất khớp chồng lấn.
12. **Roll sau cửa sổ cuối**, truy cập `charAt(n)` và lỗi index.
13. **Trả chỉ số 1-based trong khi đề dùng 0-based**.
14. **Nhầm UTF-16 code unit và ký tự Unicode**, nhất là emoji.
15. **Chuẩn hóa text nhưng không chuẩn hóa pattern**, làm sai ngữ nghĩa.
16. **Không phân biệt vị trí đầu tiên với mọi vị trí khớp**, dừng sớm sai yêu cầu.
17. **Tuyên bố luôn O(n+m) dù có xác minh từng ứng viên**.
18. **Lưu substring mới cho mọi cửa sổ**, tăng cấp phát và chi phí.
19. **Tự thay đổi BASE hoặc MOD mà không tính nguy cơ long overflow**.
20. **Coi double hash là bằng chứng không collision**, không đúng về toán học.
21. **Không kiểm tra hiệu năng khi text/pattern lặp nhiều**, gây nhiều lần so ký tự.
22. **Bỏ test mẫu dài đúng bằng n**, nơi chỉ có một cửa sổ.
23. **Bỏ test đầu vào null**, nhận lỗi khó hiểu ở vị trí khác.
24. **Dùng rolling hash làm hash bảo mật**, không đáp ứng tính chống đối kháng.

---

## 13. Kiểm thử và oracle độc lập

### Oracle đơn giản

Viết một hàm tham chiếu quét tất cả vị trí và so từng ký tự, không dùng hash:

```text
NAIVE(text,pattern):
    n = length(text)
    m = length(pattern)

    if m==0:
        return [0..n]

    results = []
    for i=0..n-m:
        equal=true
        for j=0..m-1:
            if text[i+j] != pattern[j]:
                equal=false
                break
        if equal:
            results.add(i)
    return results
```

So danh sách kết quả của Rabin–Karp với oracle này trên những chuỗi ngẫu nhiên ngắn; nó giúp phát hiện lỗi rolling, sai vị trí, thiếu khớp chồng lấn và sai xử lý đầu vào.

### Các bộ test nên có

| Text | Pattern | Kết quả |
| --- | --- | --- |
| `abracadabra` | `abra` | `[0,7]` |
| `aaaaa` | `aa` | `[0,1,2,3]` |
| `aaaaa` | `aaa` | `[0,1,2]` |
| `ababa` | `aba` | `[0,2]` |
| `mississippi` | `issi` | `[1,4]` |
| `ABCabc` | `abc` | `[3]` |
| `abc` | `""` | `[0,1,2,3]` |
| `""` | `""` | `[0]` |
| `abc` | `abcd` | `[]` |
| `abc` | `c` | `[2]` |
| `a😀a😀` | `😀` | `[1,4]` (UTF-16) |
| `abcabcabc` | `abc` | `[0,3,6]` |

### Kiểm thử riêng công thức rolling

Với chuỗi ngẫu nhiên và mỗi độ dài m từ 1 tới n:

1. Tính hash cửa sổ đầu trực tiếp.
2. Trượt từng vị trí bằng công thức roll.
3. Tính lại hash trực tiếp từ m ký tự của cửa sổ mới.
4. So hai giá trị theo cùng B,M.

Nếu khác nhau, thường có lỗi lũy thừa, modulo âm hoặc index ký tự rời/vào.

### Đối kháng collision

Với hash đồ chơi B=2,M=5, `"bc"` và `"ca"` có hash bằng 2 nhưng khác nhau. Phép so sánh ký tự phải loại khớp giả. Đây là kiểm thử logic **collision**, không phải dự báo xác suất của hai môđun lớn trong chương trình.

### Thuộc tính cần đúng

- Mọi vị trí trả đều hợp lệ và tăng dần.
- Mỗi vị trí trả phải thật sự khớp pattern.
- Không có vị trí khớp thật bị bỏ.
- Với n ký tự giống nhau và m ký tự giống hệt (1≤m≤n), có đúng n−m+1 match.
- Với pattern rỗng, có n+1 vị trí theo quy ước.
- Hash trượt ở mọi cửa sổ phải bằng hash tính trực tiếp của cùng cửa sổ.

---

## 14. Bài tập tự kiểm tra

1. Bài Rabin–Karp tìm gì? Điều kiện chỉ số bắt đầu hợp lệ là gì?
2. Vì sao cách naive có thể mất O(nm)?
3. Viết công thức hash đa thức độ dài m.
4. Tính hash `"aba"` khi a=1,b=2,B=31,M=101.
5. Tại sao `"bc"` và `"ca"` có thể collision khi B=2,M=5?
6. Viết công thức băm cuộn khi cửa sổ dịch sang phải một vị trí.
7. Vì sao lũy thừa cần dùng là `B^{m-1}`?
8. Vì sao phải chuẩn hóa số âm trong Java trước khi lấy `% M`?
9. Với text `"aaaaa"` và pattern `"aa"`, liệt kê mọi vị trí khớp.
10. Với pattern rỗng và text `"abc"`, kết quả của chương trình là gì?
11. Nếu m>n, phải xử lý ở bước nào?
12. Hai hash bằng nhau có đủ để trả match không? Vì sao?
13. Tại sao dùng hai môđun có lợi nhưng vẫn cần xác minh?
14. Khi nào phải dừng cập nhật rolling để tránh đọc vượt text?
15. Nêu cận thời gian cho C ứng viên khớp hash và m ký tự mẫu.
16. Vì sao rất nhiều **match thật** có thể khiến bản xác minh mất O(nm)?
17. Bộ nhớ phụ cho rolling hash thuần trong mã là bao nhiêu?
18. Với `"a😀a😀"` và pattern `"😀"`, vị trí Java UTF-16 là gì?
19. Vì sao tìm kiếm không phân biệt hoa/thường có thể cần chuẩn hóa trước?
20. So sánh bảo đảm xấu nhất của KMP và Rabin–Karp xác minh.
21. Viết công thức hash đoạn `text[l..r)` bằng prefix hash.
22. Đề yêu cầu nhiều pattern cùng độ dài: có thể tận dụng rolling thế nào?
23. Nêu hai bất biến/điều kiện đủ để bảo đảm không có false negative và false positive.
24. Hãy thiết kế một oracle không dùng hash để kiểm thử mã.

### Đáp án gợi ý

1. Tìm mọi i sao cho `text[i..i+m)==pattern`; m>0 thì `0≤i≤n-m`.
2. Mỗi trong n−m+1 cửa sổ có thể phải so tới m ký tự.
3. `H(s)=sum(value(s_i)B^(m-1-i)) mod M`.
4. `1024 mod101=14`.
5. Hai chuỗi đều cho 7 mod5=2 dù ký tự khác.
6. Bỏ `value(outgoing)B^(m-1)`, chuẩn hóa modulo, nhân B, thêm value(incoming), lại lấy modulo.
7. Ký tự đầu trong đa thức độ dài m có hệ số `B^{m-1}`.
8. Java `%` có thể trả số âm; `(old-removed+M)%M` cho phần dư không âm khi hai thành phần trong [0,M).
9. `[0,1,2,3]`.
10. `[0,1,2,3]`.
11. Trước khi tính hash cửa sổ đầu, trả `[]`.
12. Không; có collision, cần xác minh ký tự thật để exact.
13. Hai môđun lọc bớt ứng viên sai nhưng không loại trừ collision về toán học.
14. Chỉ roll nếu `start<n-m`.
15. `O(n+m+Cm)`, xấu nhất `O(nm)`.
16. Mỗi match thật cũng cần so m ký tự trong `regionMatches`.
17. O(1), cộng O(k) để lưu danh sách kết quả.
18. `[1,4]`.
19. Case folding/Unicode normalization phải áp dụng nhất quán cho cả hai chuỗi; vị trí có thể cần ánh xạ.
20. KMP exact O(n+m) xấu nhất; Rabin–Karp xác minh có thể O(nm).
21. `(pref[r]-pref[l]*pow[r-l]) mod M`, lấy dư không âm.
22. Băm các mẫu theo nhóm, trượt một cửa sổ cùng độ dài, tra ứng viên theo hash và xác minh thật.
23. Hash cửa sổ tính đúng và mọi match thật có hash bằng pattern; chỉ thêm vị trí sau `regionMatches` true.
24. Quét từng i và so ký tự trực tiếp, bao gồm quy ước mẫu rỗng.

---

## Ghi nhớ

**Rabin–Karp = hash mẫu + rolling hash cửa sổ + kiểm tra ứng viên.** Với cửa sổ dài m, công thức:

\[
h_{\mathrm{next}}
=\left(
\bigl(h_{\mathrm{old}}-value(outgoing)B^{m-1}\bigr)B
+value(incoming)
\right)\bmod M
\]

cần **chuẩn hóa phép trừ modulo** trước phép nhân tiếp.

Hash mọi cửa sổ tốn **O(n+m)** thời gian và **O(1)** bộ nhớ phụ cho phần rolling. **Hash trùng chỉ tạo ứng viên, không chứng minh chuỗi bằng nhau.** Mã Java dùng hai môđun và `String.regionMatches` để bảo đảm chính xác tuyệt đối; vì xác minh tối đa m ký tự cho C ứng viên, cận tổng là `O(n+m+Cm)`, xấu nhất `O(nm)`. Nếu cần O(n+m) xấu nhất mà vẫn exact, dùng KMP hoặc Z-function. Luôn xác định rõ quy ước cho mẫu rỗng, khớp chồng lấn và chỉ số UTF-16 trong Java.
