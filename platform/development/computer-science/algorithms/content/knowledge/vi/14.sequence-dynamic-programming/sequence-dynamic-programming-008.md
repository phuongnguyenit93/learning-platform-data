# Tách chuỗi theo từ điển (Word Break) — Quy hoạch động dãy

**Tách chuỗi theo từ điển (word break / dictionary segmentation)** là bài toán xác định một chuỗi ký tự có thể được chia thành các **đoạn liên tiếp, không chồng lấn, không bỏ sót ký tự**, sao cho mỗi đoạn là một từ hợp lệ trong từ điển hay không. Nhiều phiên bản còn yêu cầu **đếm số cách tách**, **tìm cách dùng ít từ nhất**, **phục hồi một phương án** hoặc **liệt kê mọi phương án**.

Bài toán thuộc **quy hoạch động dãy** vì quyết định một điểm cắt ở vị trí i liên hệ với lời giải cho **tiền tố** hoặc **hậu tố** trước/sau điểm ấy. Cốt lõi không nằm ở việc thử thật nhiều dấu cách, mà ở việc **ghi nhớ kết quả của những đoạn đã giải**, tránh giải đi giải lại cùng một tiền tố.

Ví dụ:

~~~text
s = "catsanddog"
D = {"cat", "cats", "and", "sand", "dog"}

Hai cách hợp lệ:
  cat | sand | dog
  cats | and | dog

Tồn tại?                 Có
Số cách tách khác nhau?   2
Ít từ nhất?              3
~~~

**Một từ có thể được dùng lặp lại** trong các ví dụ chuẩn của bài học. Mỗi từ trong từ điển phải **không rỗng**. Chuỗi rỗng được quy ước có **một cách tách rỗng**, dùng 0 từ; nếu một đề cụ thể cấm cách tách rỗng, phải đổi điều kiện cơ sở và đặc tả theo đề ấy.

## 1. Phát biểu chính xác bài toán

Cho một chuỗi **S** có độ dài n theo đơn vị chỉ số đã chọn, và tập từ điển **D** gồm những chuỗi **không rỗng**. Cần tìm dãy các ranh giới:

**0 = p₀ < p₁ < ... < pₖ = n**

sao cho với mọi j từ 1 đến k, đoạn **S[pⱼ₋₁:pⱼ]** thuộc D.

Khi đó chuỗi gốc được tách thành:

**S[p₀:p₁] | S[p₁:p₂] | ... | S[pₖ₋₁:pₖ]**.

Điều kiện quan trọng:

- Các từ phải phủ **toàn bộ S**, không được bỏ một ký tự ở đầu, giữa hay cuối.
- Thứ tự các từ **giữ nguyên thứ tự ký tự của chuỗi gốc**; đây không phải bài tìm một tập từ có thể sắp lại.
- Mỗi từ được so khớp **chính xác** theo quy tắc so sánh chuỗi đã quy định; không mặc định tự bỏ dấu, tự sửa lỗi chính tả hay bỏ khoảng trắng.
- Nếu D là một **tập**, việc viết cùng một từ hai lần không tạo ra hai cách tách mới.
- Hai cách tách được coi là khác nhau nếu **dãy vị trí cắt** khác nhau. Ví dụ "aaaa" có thể tách "a|aaa" hoặc "aa|aa", là hai cách khác nhau.
- Phiên bản cơ bản **không giới hạn số lần sử dụng mỗi từ**. Nếu mỗi từ chỉ được dùng tối đa một lần, trạng thái chỉ số chuỗi đơn thuần có thể không đủ; phải theo dõi tài nguyên từ điển đã tiêu thụ.

Những loại đầu ra phổ biến:

| Biến thể | Câu hỏi | Giá trị ví dụ với "catsanddog" |
| --- | --- | --- |
| **Tồn tại** | Có cách tách phủ hết S? | true |
| **Đếm** | Có bao nhiêu dãy vị trí cắt hợp lệ? | 2 |
| **Cực tiểu** | Cách tách dùng ít từ nhất gồm mấy từ? | 3 |
| **Phục hồi** | Một cách tách tối ưu cụ thể là gì? | [cat, sand, dog] |
| **Liệt kê** | Những cách tách nào hợp lệ? | Cả hai cách ở trên |

Các câu hỏi trên có thể dùng cùng một đồ thị điểm cắt, nhưng **phép tổng hợp kết quả** khác nhau: OR, cộng số cách hoặc min.

## 2. Chọn trạng thái DP theo tiền tố

Đánh số các ranh giới từ **0 đến n**. Vị trí i đại diện cho tiền tố **S[0:i)** gồm i ký tự theo quy ước chỉ số của thuật toán.

Định nghĩa:

- **possible[i]**: có ít nhất một cách tách hợp lệ tiền tố S[0:i) không?
- **ways[i]**: số cách tách hợp lệ của tiền tố S[0:i).
- **minWords[i]**: số từ ít nhất để tách tiền tố S[0:i); giá trị **∞** nếu chưa thể đạt.
- **parent[i]**: vị trí cắt ngay trước từ cuối trong một phương án đạt minWords[i], dùng để phục hồi.

**Điều kiện cơ sở:**

~~~text
possible[0] = true
ways[0]     = 1
minWords[0] = 0
parent[0]   = không dùng

Với i = 1..n:
    possible[i] = false
    ways[i]     = 0
    minWords[i] = vô cực
    parent[i]   = chưa xác định
~~~

Lý do **ways[0]=1**: chỉ có đúng **một** dãy từ rỗng tạo ra chuỗi rỗng. Đây không có nghĩa đã chọn một từ; đó là **đơn vị** dùng để cộng số cách khi bắt đầu ghép từ.

### Công thức truy hồi theo từ cuối

Xét một điểm cắt j với **0 ≤ j < i**. Nếu **S[j:i) ∈ D**, ta có thể tách tiền tố S[0:j) trước, sau đó nối thêm từ cuối S[j:i).

Công thức:

**possible[i] = OR của possible[j] trên mọi j mà S[j:i) ∈ D.**

**ways[i] = tổng ways[j] trên mọi j mà S[j:i) ∈ D.**

**minWords[i] = min(minWords[j] + 1)** trên mọi j có **possible[j] = true** và **S[j:i) ∈ D**.

Nếu không có ứng viên, possible[i] vẫn false, ways[i]=0, minWords[i] vẫn ∞.

Có hai điều kiện riêng cần đúng khi chuyển từ j đến i: **từ cuối phải có trong từ điển** và **tiền tố phía trước phải tách được**. Chỉ tìm thấy một từ khớp với hậu tố chưa đủ kết luận cả chuỗi tách được.

### Vì sao các trường hợp không bị đếm trùng?

Mỗi cách tách hợp lệ của S[0:i) có **một điểm cắt cuối cùng duy nhất j**. Nếu j khác nhau, dãy ranh giới khác nhau nên hai nhóm lời giải không trùng. Xóa từ cuối S[j:i) của một cách tách thu được đúng một cách tách tiền tố S[0:j). Ngược lại, nối từ cuối vào một cách tách tiền tố tạo đúng một cách tách S[0:i).

Vì vậy phép cộng **ways[j]** trên các điểm cắt cuối hợp lệ đếm **mỗi cách đúng một lần**. Đây là lý do quan trọng để phân biệt DP đếm với việc chỉ duyệt từ trong từ điển mà vô tình tính trùng bản sao của cùng một từ.

## 3. Truy vết bảng DP với "catsanddog"

Giả sử:

~~~text
S = c a t s a n d d o g
i = 0 1 2 3 4 5 6 7 8 9 10  (ranh giới)

D = {cat, cats, and, sand, dog}
~~~

Các chuyển thành công:

- Từ **0 → 3** bằng "cat".
- Từ **0 → 4** bằng "cats".
- Từ **3 → 7** bằng "sand".
- Từ **4 → 7** bằng "and".
- Từ **7 → 10** bằng "dog".

Sơ đồ:

~~~text
           "cat"       "sand"       "dog"
      0 ----------> 3 ----------> 7 ----------> 10
       \                         ^
        \ "cats"        "and"   /
         ----------> 4 ---------
~~~

Bảng trạng thái tại các ranh giới quan trọng:

| Ranh giới i | Tiền tố | possible[i] | ways[i] | minWords[i] |
| ---: | --- | --- | ---: | ---: |
| 0 | "" | true | 1 | 0 |
| 3 | "cat" | true | 1 | 1 |
| 4 | "cats" | true | 1 | 1 |
| 7 | "catsand" | true | 2 | 2 |
| 10 | "catsanddog" | true | 2 | 3 |

Các ranh giới 1, 2, 5, 6, 8, 9 không đạt được theo D và có ways=0. Đến ranh giới 7, cả "cat|sand" và "cats|and" cùng kết thúc, nên ways[7]=1+1=2. Từ "dog" nối hai cách ấy tạo ways[10]=2.

Nếu chỉ yêu cầu tồn tại, có thể trả **true** ngay khi biết possible[10]. Nếu cần đếm, không được dừng sau khi tìm ra cách đầu tiên: phải tổng hợp **tất cả** đường cắt hợp lệ dẫn đến n.

Nếu muốn một cách dùng **ít từ nhất**, lưu parent cho những chuyển cải thiện minWords. Nếu hai ứng viên cùng số từ, cách xử lý hòa phải được định nghĩa: giữ phương án gặp trước, chọn thứ tự từ điển hoặc một tiêu chí khác.

## 4. Hai hướng triển khai DP tương đương

### Top-down: đệ quy có ghi nhớ (memoization)

Định nghĩa **can(i)** là “hậu tố bắt đầu tại i có thể tách hết không?”. Khi đó:

~~~text
can(n) = true

can(i):
    nếu memo[i] đã có kết quả: trả memo[i]
    thử mọi từ w khớp đúng từ vị trí i
    nếu can(i + độ_dài(w)) == true:
        memo[i] = true
        return true
    memo[i] = false
    return false
~~~

Vì mỗi từ không rỗng, vị trí i luôn **tăng** trong các lời gọi đệ quy. Do đó không có vòng lặp phụ thuộc. Không có memo, các hậu tố giống nhau có thể bị giải lại rất nhiều lần, dẫn đến cây thử nghiệm có kích thước **hàm mũ**.

Top-down thường tiện khi chỉ một phần nhỏ trạng thái cần xét, hoặc khi dễ suy nghĩ theo lựa chọn **từ đầu của hậu tố**. Nhược điểm: có thể sâu tới O(n) lời gọi, dễ tràn ngăn xếp với chuỗi rất dài trên một số môi trường.

### Bottom-up: điền bảng từ trái sang phải

Cách trực tiếp theo công thức từ cuối:

~~~text
dp[0] = true

for i = 1..n:
    for j = 0..i-1:
        if dp[j] và S[j:i) thuộc D:
            dp[i] = true
            break
~~~

Với **đếm**, thay OR bằng cộng; với **min**, thay bằng min và lưu parent. Phải tiếp tục xét các điểm cắt thích hợp khi cần đếm tất cả cách, không dừng sớm chỉ vì đã tìm được một cách.

Một cách bottom-up khác là **đẩy từ tiền tố đã đạt được sang vị trí tiếp theo**:

~~~text
dp[0] = true

for start = 0..n-1:
    if dp[start] == false: continue

    for mỗi từ w khớp tại vị trí start:
        end = start + length(w)
        dp[end] = true
~~~

Hướng này đặc biệt tự nhiên với **Trie**: từ mỗi ranh giới có thể đạt, duyệt các ký tự tiếp theo và phát hiện tất cả từ bắt đầu tại đó.

**Quan trọng:** bottom-up theo đầu ra i và bottom-up đẩy từ start chỉ là **hai thứ tự thực thi** của cùng những cạnh chuyển. Cả hai đúng nếu các cạnh luôn đi từ vị trí nhỏ sang vị trí lớn (từ không rỗng).

## 5. Đếm cách tách và vấn đề số rất lớn

Với từ điển **D={"a","aa","aaa"}** và chuỗi **S="aaaa"**, các cách tách là:

~~~text
a | a | a | a
a | a | aa
a | aa | a
aa | a | a
aa | aa
a | aaa
aaa | a
~~~

**Tổng cộng 7 cách.** Ít từ nhất là 2, ví dụ "a|aaa", "aa|aa" hoặc "aaa|a".

Nếu chuỗi gồm rất nhiều ký tự "a" và từ điển chứa nhiều độ dài từ khác nhau, số cách có thể tăng rất nhanh. Chẳng hạn nếu D={"a","aa"}, số cách tách chuỗi gồm n ký tự "a" thỏa truy hồi kiểu Fibonacci. Với n lớn, số cách có thể vượt **int** hoặc **long**.

Khi đề hỏi **số cách chính xác**, Java nên dùng **BigInteger** nếu kích thước cho phép. Nếu đề yêu cầu **modulo M**, cập nhật:

**ways[end] = (ways[end] + ways[start]) mod M**.

Nhưng phải nhớ: **ways[end] mod M = 0 không chứng minh end không thể đạt**. Số cách thật có thể là bội số của M. Khi còn cần biến thể **tồn tại** hoặc **min**, nên lưu cờ possible riêng hoặc một trạng thái đạt được độc lập với số cách modulo.

### Hai từ điển có “bản sao” của cùng một từ

Nếu người dùng cung cấp D=["cat","cat","sand","dog"], hai lần ghi "cat" không có nghĩa "cat|sand|dog" có hai cách tách khác nhau. Nếu đề xem từ điển là **tập chuỗi hợp lệ**, phải **khử trùng** hoặc đánh dấu từ kết thúc ở Trie bằng boolean, thay vì đếm số bản sao đầu vào.

Chỉ khi bài toán thật sự coi từng mục từ là **một lựa chọn phân biệt có danh tính riêng**, cách đếm mới cần đổi. Bản chuẩn Word Break đếm theo **ranh giới tách chuỗi**.

## 6. Tìm số từ ít nhất và phục hồi lời giải

Với S[0:i), định nghĩa minWords[i] là số từ ít nhất; ban đầu minWords[0]=0, còn các vị trí khác là **INF**.

Khi tìm thấy một từ S[j:i) thuộc D và j đã đạt được:

~~~text
candidate = minWords[j] + 1

nếu candidate < minWords[i]:
    minWords[i] = candidate
    parent[i] = j
~~~

Sau khi tính xong, nếu minWords[n] là INF thì **không có cách tách**. Nếu có lời giải, bắt đầu tại i=n và lặp:

1. Đọc **j=parent[i]**.
2. Đưa từ **S[j:i)** vào danh sách kết quả.
3. Đặt **i=j**.
4. Khi i=0, đảo danh sách vì ta vừa đi ngược từ từ cuối về từ đầu.

Ví dụ **"abcdef"** với D={"abcd","abc","def","e","f"}:

- Cách **abcd|e|f** hợp lệ, nhưng dùng **3 từ**.
- Cách **abc|def** hợp lệ và dùng **2 từ**.
- Vì mục tiêu min, DP trả **2**, dù từ đầu "abcd" dài hơn "abc".

Một cờ possible không đủ để phục hồi phương án; cần parent hoặc phải tính lại/lần theo bảng DP để xác định lựa chọn. Nếu đề muốn **tất cả phương án đạt min**, phải lưu nhiều tiền nhiệm hoặc có thuật toán truy vết riêng.

### Quy tắc hòa

Nếu nhiều cách có cùng minWords, bài học dùng quy tắc đơn giản: **chỉ cập nhật parent khi tìm được số từ nhỏ hơn thực sự**. Khi bằng nhau, giữ đường đã được duyệt thấy trước. Kết quả này **xác định đối với một thứ tự duyệt cố định**, nhưng **không nhất thiết nhỏ nhất theo thứ tự từ điển**.

Nếu đề yêu cầu “cách tách ít từ nhất và nhỏ nhất theo từ điển”, không thể chỉ dùng quy tắc hòa tùy ý; cần đưa thứ tự từ điển vào trạng thái/so sánh đường đi hoặc thiết kế truy vết ưu tiên có chứng minh.

## 7. Tối ưu kiểm tra từ bằng Trie

Công thức cơ bản thử mọi cặp (j,i) với 0≤j<i. Có **O(n²)** cặp. Tuy nhiên, chi phí kiểm tra “S[j:i) có trong từ điển hay không” không phải lúc nào O(1).

Trong Java hiện đại, **String.substring** tạo chuỗi mới và sao chép dữ liệu liên quan đến độ dài đoạn. Tra HashSet<String> thường còn tính hash của chuỗi con. Do đó một triển khai thử mọi substring có thể tốn tới **O(n³)** tổng thời gian trong trường hợp xấu nhất nếu tính chi phí tạo và tra substring, dù số cặp chỉ là O(n²).

**Trie (cây tiền tố)** khắc phục việc tạo quá nhiều substring:

- Mỗi nút ứng với một tiền tố của một hoặc nhiều từ.
- Một cạnh là một ký tự/mã điểm Unicode.
- Nút đánh dấu **terminal** nếu đường từ gốc đến nó tạo thành một từ đầy đủ.
- Từ ranh giới start đã đạt được, đi qua các mã điểm của S[start:], theo các cạnh Trie.
- Mỗi lần chạm nút terminal tại end, có một từ hợp lệ S[start:end) và có thể cập nhật DP[end].
- Nếu không còn cạnh phù hợp, **dừng ngay** tại start vì không còn từ nào bắt đầu bằng tiền tố đang duyệt.

Ví dụ Trie chứa "cat" và "cats": khi đọc c→a→t, nút "cat" đã terminal; nếu tiếp tục đọc s, nút "cats" cũng terminal. Ta thu được cả hai điểm cắt mà không tạo hai chuỗi con đầy đủ.

### Chi phí theo độ dài từ lớn nhất

Gọi:

- **n**: số mã điểm của chuỗi đầu vào;
- **L**: độ dài mã điểm lớn nhất của một từ trong D;
- **S**: tổng độ dài mã điểm của các từ đầu vào để xây Trie.

Xây Trie tốn **O(S)** thao tác cạnh theo mô hình tra Map có chi phí kỳ vọng O(1). Với mỗi start, ta duyệt tối đa L ký tự hoặc dừng khi không có cạnh, do đó có nhiều nhất **O(nL)** lần bước qua cạnh. Thêm O(n) trạng thái DP.

Vì vậy thời gian trong mô hình thao tác Map và số học đơn vị là **O(S+nL)**, thay vì kiểm tra mọi substring dài đến n. Bộ nhớ là **O(S+n)** cho Trie, mã điểm đầu vào và bảng DP, **chưa tính độ lớn BigInteger** và kết quả xuất ra.

Nếu L rất lớn và các từ có chung tiền tố dài, O(nL) vẫn có thể tiến gần O(n²). Nếu D lớn nhưng không có nhiều từ khớp, Trie dừng sớm rất hữu ích.

**Lưu ý:** phép cộng BigInteger có chi phí phụ thuộc số bit, nên thời gian bit thực tế của biến thể đếm chính xác có thể lớn hơn mô hình O(nL).

## 8. Java 17+: chương trình đầy đủ dùng Trie và DP

Chương trình bên dưới thực hiện **đồng thời** các yêu cầu:

- **possible**: tách hết chuỗi được không?
- **ways**: số cách tách **chính xác**, bằng BigInteger.
- **minWords**: số từ ít nhất nếu tách được, hoặc −1 nếu không có nghiệm.
- **oneMin**: phục hồi một cách tách dùng ít từ nhất.

Để hỗ trợ cả ký tự ngoài Basic Multilingual Plane (chẳng hạn emoji), mã làm việc với mảng **Unicode code point** từ String.codePoints(), không dùng chỉ số char để tách giữa hai nửa của một surrogate pair. Từ điển vẫn được so khớp **đúng nguyên dạng**: chương trình không tự chuẩn hóa Unicode hay phân biệt ngôn ngữ.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class DictionaryWordBreakDemo {

    record Answer(boolean possible, BigInteger ways,
                  int minWords, List<String> oneMin) {}

    static final class TrieNode {
        final Map<Integer, TrieNode> next = new HashMap<>();
        boolean terminal = false;
    }

    static Answer analyze(String text, Collection<String> dictionary) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(dictionary, "dictionary");

        // Build a trie. Repeated dictionary words do not create
        // extra segmentations: terminal is a boolean.
        TrieNode root = new TrieNode();
        for (String word : dictionary) {
            Objects.requireNonNull(word, "dictionary word");
            if (word.isEmpty()) {
                throw new IllegalArgumentException(
                        "Dictionary words must be nonempty");
            }

            TrieNode node = root;
            for (int cp : word.codePoints().toArray()) {
                node = node.next.computeIfAbsent(
                        cp, ignored -> new TrieNode());
            }
            node.terminal = true;
        }

        // Indices refer to Unicode code points, not UTF-16 char units.
        int[] codePoints = text.codePoints().toArray();
        int n = codePoints.length;

        boolean[] reachable = new boolean[n + 1];
        BigInteger[] ways = new BigInteger[n + 1];
        int[] minWords = new int[n + 1];
        int[] parent = new int[n + 1];

        Arrays.fill(ways, BigInteger.ZERO);
        Arrays.fill(minWords, Integer.MAX_VALUE);
        Arrays.fill(parent, -1);

        reachable[0] = true;
        ways[0] = BigInteger.ONE;
        minWords[0] = 0;

        // Forward DP: only traverse trie from reachable boundaries.
        for (int start = 0; start < n; start++) {
            if (!reachable[start]) {
                continue;
            }

            TrieNode node = root;
            for (int pos = start; pos < n; pos++) {
                node = node.next.get(codePoints[pos]);
                if (node == null) {
                    break;
                }
                if (!node.terminal) {
                    continue;
                }

                // A whole dictionary word spans [start, end).
                int end = pos + 1;
                reachable[end] = true;
                ways[end] = ways[end].add(ways[start]);

                int candidate = minWords[start] + 1;
                if (candidate < minWords[end]) {
                    minWords[end] = candidate;
                    parent[end] = start;
                }
            }
        }

        if (!reachable[n]) {
            return new Answer(false, BigInteger.ZERO, -1, List.of());
        }

        // Reconstruct the minimum-word segmentation backwards.
        List<String> pieces = new ArrayList<>();
        for (int end = n; end > 0; ) {
            int start = parent[end];
            if (start < 0) {
                throw new IllegalStateException("Broken parent chain");
            }
            pieces.add(new String(codePoints, start, end - start));
            end = start;
        }
        Collections.reverse(pieces);

        return new Answer(
                true, ways[n], minWords[n], List.copyOf(pieces));
    }

    public static void main(String[] args) {
        List<String> animals = List.of(
                "cat", "cats", "and", "sand", "dog");

        System.out.println("catsanddog: "
                + analyze("catsanddog", animals));
        System.out.println("catsandog: "
                + analyze("catsandog", animals));

        List<String> pineapple = List.of(
                "apple", "pen", "applepen", "pine", "pineapple");
        System.out.println("pineapplepenapple: "
                + analyze("pineapplepenapple", pineapple));

        System.out.println("aaaa: "
                + analyze("aaaa", List.of("a", "aa", "aaa")));
        System.out.println("cars: "
                + analyze("cars", List.of("car", "ca", "rs")));
        System.out.println("abcdef: "
                + analyze("abcdef", List.of("abcd", "abc", "def", "e", "f")));

        System.out.println("empty: "
                + analyze("", List.of("cat")));
        System.out.println("unicode: "
                + analyze("café🥭sữa", List.of("café", "🥭", "sữa")));
    }
}
~~~

Lưu thành tệp **DictionaryWordBreakDemo.java** mã hóa **UTF-8**, biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 DictionaryWordBreakDemo.java
java DictionaryWordBreakDemo
~~~

Đầu ra theo định dạng toString() tự sinh của Java record:

~~~text
catsanddog: Answer[possible=true, ways=2, minWords=3, oneMin=[cat, sand, dog]]
catsandog: Answer[possible=false, ways=0, minWords=-1, oneMin=[]]
pineapplepenapple: Answer[possible=true, ways=3, minWords=3, oneMin=[pine, applepen, apple]]
aaaa: Answer[possible=true, ways=7, minWords=2, oneMin=[a, aaa]]
cars: Answer[possible=true, ways=1, minWords=2, oneMin=[ca, rs]]
abcdef: Answer[possible=true, ways=2, minWords=2, oneMin=[abc, def]]
empty: Answer[possible=true, ways=1, minWords=0, oneMin=[]]
unicode: Answer[possible=true, ways=1, minWords=3, oneMin=[café, 🥭, sữa]]
~~~

**Giải thích từng phần:**

1. **TrieNode** dùng Map<Integer,TrieNode> để nối theo **mã điểm Unicode**. Một nút terminal có nghĩa toàn bộ đường từ gốc tạo ra một từ. Vì terminal chỉ là boolean, từ trùng trong dữ liệu từ điển không nhân số cách.
2. **reachable[start]** kiểm tra tiền tố trước vị trí start có thể tách được. Nếu false, không có cách nào hợp lệ đi từ start tới end mà tạo một cách tách hoàn chỉnh của tiền tố end.
3. Mỗi khi gặp **terminal tại pos**, từ hợp lệ kết thúc ở **end=pos+1**. Chuyển này đi từ start nhỏ đến end lớn nên DP được xử lý đúng thứ tự.
4. **ways[end] += ways[start]** cộng các cách đã tách tiền tố trước từ vừa đọc. Có thể có nhiều start dẫn đến cùng end, nên phải cộng chứ không ghi đè.
5. **minWords[end]** chỉ thay khi tìm được số từ *nhỏ hơn thật sự*. Tại trường hợp hòa, phương án phát hiện trước được giữ lại; vì start tăng theo thứ tự, kết quả ví dụ được xác định.
6. **parent[end]** lưu start của từ cuối thuộc phương án min. Sau khi kết thúc, đi ngược parent và gọi **new String(codePoints,start,len)** để phục hồi từ đúng ranh giới mã điểm.
7. Nếu **n=0**, không có chuyển nào; reachable[0]=true, ways[0]=1, minWords[0]=0 và danh sách từ rỗng. Nếu n>0 nhưng không thể tách, Answer trả **false/0/−1/[]**.
8. Chương trình **không thay đổi chuỗi** hoặc từ điển đầu vào. Chi phí cấp phát chủ yếu là Trie, bảng DP, mảng codePoints và các chuỗi được phục hồi.

**Kết quả "pineapplepenapple"** có ba cách tách: "pine|apple|pen|apple", "pine|applepen|apple" và "pineapple|pen|apple". Hai cách cuối dùng ba từ; với thứ tự cập nhật của mã, một kết quả min là **[pine, applepen, apple]**.

## 9. Chứng minh tính đúng của DP

Xem các ranh giới **0,1,...,n** là đỉnh của một **đồ thị có hướng không chu trình (DAG)**. Vẽ cạnh **i→j** khi **i<j** và **S[i:j) ∈ D**. Cạnh biểu diễn chọn một từ kéo dài từ vị trí i đến j.

Bây giờ:

- Một **cách tách hợp lệ** tương ứng đúng một đường đi từ đỉnh 0 đến đỉnh n.
- Một đường đi từ 0 đến n tương ứng đúng một dãy điểm cắt và do đó đúng một cách tách.
- Mỗi cạnh làm tăng vị trí, vì từ không rỗng, nên **không có chu trình**.
- Duyệt i tăng dần là một **thứ tự tô-pô** của đồ thị.

### Chứng minh cho tồn tại

Bất biến: trước khi xử lý start, reachable[start] đúng nếu và chỉ nếu tồn tại đường đi từ 0 đến start. Cơ sở reachable[0]=true ứng với đường đi rỗng. Mọi cạnh từ start đến end được áp dụng khi reachable[start]=true, nên end được đánh dấu là đạt được từ một đường đi hợp lệ. Ngược lại, đường đi bất kỳ đến end có một cạnh cuối start→end; vì start<end, tiền tố đến start đã được xử lý, và cạnh tương ứng sẽ đánh dấu end.

### Chứng minh cho số cách

Bất biến: ways[i] là số đường đi khác nhau từ 0 đến i sau khi các tiền nhiệm nhỏ hơn i đã được xử lý. Các đường đi đến end được phân hoạch theo **cạnh cuối cùng start→end**. Số đường đi kết thúc qua cạnh đó là ways[start]; cộng qua các start hợp lệ thu đủ và không trùng mọi đường đi. Cơ sở ways[0]=1 ứng với đúng một đường rỗng.

### Chứng minh cho minWords

Mỗi cạnh tương ứng với **thêm một từ**, nên số từ là số cạnh trên đường đi. Đường đi ngắn nhất về số cạnh đến end bắt buộc có cạnh cuối start→end. Trước cạnh cuối, tiền tố đường đi đến start phải tối ưu; nếu không có đường ngắn hơn đến start, thay vào sẽ cải thiện toàn đường. Vì thế:

**minWords[end] = min(minWords[start]+1)** trên mọi cạnh hợp lệ.

Duyệt theo thứ tự tăng làm các tiền nhiệm được giải xong trước khi dùng. Chuỗi parent ghi lại các cạnh thuộc một đường ngắn nhất. Quy nạp theo chỉ số cho thấy toàn bộ ba đại lượng đúng khi kết thúc ở n.

**Lưu ý:** nếu thay mỗi từ bằng chi phí tùy ý không âm, cùng đồ thị DAG có thể dùng min-cost DP với **minCost[start]+cost(word)**. Nếu xuất hiện ràng buộc không thể biểu diễn chỉ bằng vị trí hiện tại (như giới hạn số lần sử dụng một từ), chứng minh này không còn đầy đủ nếu không bổ sung trạng thái.

## 10. Độ phức tạp và lựa chọn cách cài đặt

| Phương pháp | Công việc chính | Thời gian thường phân tích | Bộ nhớ phụ |
| --- | --- | --- | --- |
| Thử mọi cách đặt dấu cắt không memo | Cây lựa chọn có/không tại các ranh giới | Có thể **hàm mũ** | Phụ thuộc đệ quy/kết quả |
| DP theo mọi j<i, giả định kiểm tra từ O(1) | O(n²) cặp ranh giới | **O(n²)** theo mô hình kiểm tra từ O(1) | O(n)+từ điển |
| DP Java 17 tạo substring cho mọi cặp | O(n²) substring, hash và tra | Có thể đến **O(n³)** khi tính giá tạo/tra chuỗi | O(n) DP, chuỗi tạm |
| Trie + DP forward | Xây Trie rồi duyệt từ điểm cắt đạt | **O(S+nL)** thao tác Map kỳ vọng | **O(S+n)**, chưa tính độ dài BigInteger |
| DP với tập các từ và thử từng từ | Thử từng từ tại mỗi vị trí đạt | Phụ thuộc số từ và tổng độ dài so khớp | O(n)+từ điển |

Trong bảng, **S** là tổng độ dài các từ điển tính theo mã điểm, **L** là độ dài từ lớn nhất và **n** là số mã điểm của đầu vào.

**Chi phí đếm chính xác:** tổng số cách có thể tăng rất lớn. BigInteger thực hiện cộng theo số bit, không luôn là phép cộng hằng số. Vì vậy O(S+nL) là cận theo thao tác truy cập cạnh và cập nhật trạng thái trong mô hình số học đơn vị; thời gian bit thực tế và bộ nhớ BigInteger có thể lớn hơn.

**Chi phí liệt kê mọi cách:** ngay cả khi đã biết số cách bằng DP, việc in toàn bộ câu tách có chi phí ít nhất tỉ lệ với **kích thước đầu ra**. Nếu số cách tăng hàm mũ, không thể kỳ vọng một thuật toán liệt kê tất cả chạy O(n²) với n lớn.

**Chi phí phục hồi một cách min:** đi ngược parent theo số từ được chọn, rồi tạo chuỗi từ các lát codePoints. Tổng số mã điểm được phục hồi là n nên việc dựng các từ để xuất tốn **O(n)** cho toàn bộ kết quả.

## 11. Vì sao tham lam chọn từ dài nhất thường sai?

Một cách làm có vẻ nhanh là từ vị trí hiện tại, luôn chọn **từ dài nhất** khớp với chuỗi còn lại, rồi đi tiếp. Quy tắc này không đảm bảo có lời giải, càng không đảm bảo số từ ít nhất.

### Phản ví dụ cho bài tồn tại

~~~text
S = "cars"
D = {"car", "ca", "rs"}

Greedy longest-first:
  "car" | "s"    -> "s" không thuộc D -> thất bại

Một cách hợp lệ:
  "ca" | "rs"    -> thành công
~~~

Quyết định "car" dài hơn "ca" làm mất khả năng tách phần còn lại. Một điểm cắt hợp lệ phải được đánh giá dựa trên **khả năng tách toàn bộ hậu tố**, không chỉ độ dài của từ vừa chọn.

### Phản ví dụ cho bài ít từ nhất

~~~text
S = "abcdef"
D = {"abcd", "abc", "def", "e", "f"}

Greedy longest-first:
  "abcd" | "e" | "f" -> 3 từ

Tối ưu:
  "abc" | "def"     -> 2 từ
~~~

Greedy tạo được một cách hợp lệ nhưng **không tối ưu**. Đây là lý do cần DP minWords thay vì giữ duy nhất lựa chọn cục bộ.

**Kết luận:** không có một chiến lược “chọn từ dài nhất trước” đúng cho mọi từ điển. Một bài toán tham lam muốn đúng cần chứng minh điều kiện lựa chọn phù hợp (ví dụ cấu trúc tiền tố đặc biệt), không thể suy ra từ trực giác độ dài.

## 12. Unicode, chữ hoa/thường, dấu và khoảng trắng

### UTF-16 char khác Unicode code point

Java String lưu dữ liệu theo đơn vị UTF-16. Một ký tự ngoài BMP, ví dụ **🥭**, dùng **hai char** nhưng chỉ là **một code point**. Nếu dùng String.length() và charAt() như chỉ số “ký tự người dùng”, có thể tách nhầm giữa hai nửa surrogate.

Chương trình ở mục 8 dùng **text.codePoints().toArray()** và Trie theo int code point, nên các vị trí cắt được tính theo mã điểm; **new String(int[] codePoints, offset, count)** phục hồi chuỗi hợp lệ ở các ranh giới mã điểm.

Tuy nhiên, **code point vẫn khác grapheme cluster**: một ký tự nhìn thấy có thể gồm nhiều code point, chẳng hạn chữ cái và dấu kết hợp. Nếu ứng dụng muốn tách theo đơn vị hiển thị của người dùng, cần quy tắc phân đoạn grapheme thích hợp, không chỉ codePoints.

### Chuẩn hóa Unicode

Hai chuỗi hiển thị giống nhau có thể có biểu diễn Unicode khác nhau:

- "é" dưới dạng một code point.
- "e" + ký tự dấu sắc kết hợp dưới dạng hai code point.

Thuật toán so khớp **chính xác** có thể xem chúng là khác nhau. Nếu nghiệp vụ yêu cầu coi là tương đương, có thể chuẩn hóa **cả chuỗi đầu vào lẫn từ điển** theo cùng chuẩn, ví dụ **Normalizer.Form.NFC**, **trước khi** chạy DP. Khi chuẩn hóa thay đổi độ dài/ranh giới, vị trí trả về cần được hiểu theo chuỗi đã chuẩn hóa hoặc phải lưu ánh xạ về chuỗi gốc.

### Hoa/thường và dấu tiếng Việt

Đừng mặc định "Cat" và "cat" giống nhau hay "sua" và "sữa" giống nhau. Chuyển chữ hoa/thường cần xác định **Locale** và quy tắc nghiệp vụ. Tự bỏ dấu có thể làm các từ khác nhau nhập vào cùng một từ điển đã chuẩn hóa, ảnh hưởng đến kết quả đếm.

### Khoảng trắng và dấu câu

Bản word break lý thuyết thường nhận một chuỗi không có khoảng trắng sẵn. Nếu S chứa khoảng trắng, thuật toán vẫn xem đó là một code point cần được phủ: phải có từ trong từ điển chứa khoảng trắng ở vị trí phù hợp, hoặc phải có một bước tiền xử lý bỏ/chuẩn hóa khoảng trắng theo **đặc tả**. Không được âm thầm bỏ dấu câu/khoảng trắng rồi khẳng định đã tách đúng chuỗi gốc.

## 13. Các biến thể thường gặp

### Chỉ cần tồn tại

Dùng boolean possible[] và có thể dừng khi possible[n] đã được chứng minh, hoặc dùng memoization từ đầu. Không cần BigInteger, parent hay số từ tối thiểu. Trong nhiều trường hợp, biến thể này nhẹ hơn đáng kể.

### Đếm số cách modulo M

Dùng int/long và lấy modulo trong từng phép cộng. Nếu M có thể lớn, phải tránh tràn trong phép cộng trước modulo. Không suy ra tính tồn tại từ waysModulo==0.

### Đếm số cách dùng đúng k từ

Một chiều vị trí không đủ; dùng trạng thái **ways[i][k]**. Khi có từ từ start đến end, chuyển:

**ways[end][k+1] += ways[start][k]**.

Tổng hợp các k phù hợp theo yêu cầu. Nếu có giới hạn k, phải kiểm tra độ phức tạp **O(nK)** trạng thái, và chi phí xét các cạnh/từ còn nằm ngoài số trạng thái.

### Đếm số cách đạt ít từ nhất

Lưu đồng thời **minWords[i]** và **countMin[i]**:

- Nếu ứng viên candidate nhỏ hơn minWords[end]: thay minWords[end] và đặt countMin[end]=countMin[start].
- Nếu candidate bằng minWords[end]: cộng countMin[start].
- Nếu candidate lớn hơn: không thêm vào số cách tối ưu.

Cần cơ sở minWords[0]=0, countMin[0]=1. Với "catsanddog", cả hai cách đều dùng 3 từ nên **countMin[n]=2**. Với "aaaa" và D={"a","aa","aaa"}, minWords=2 nhưng **countMin[n]=3** (a|aaa, aa|aa, aaa|a), khác **ways[n]=7**.

### Từ có trọng số hoặc chi phí

Nếu mỗi từ w có chi phí cost(w), thay minWords bằng **minCost** và cập nhật:

**minCost[end] = min(minCost[end], minCost[start] + cost(w))**.

Vì các cạnh đều tăng vị trí, đồ thị chuyển là DAG; DP theo thứ tự ranh giới vẫn dùng được ngay cả khi có chi phí âm, miễn là bài toán vẫn chỉ xét những đường đi hữu hạn từ 0 đến n và không thêm cạnh rỗng. Nếu muốn tối thiểu số từ rồi tối thiểu chi phí, state/so sánh tối ưu phải xét **cặp tiêu chí** theo thứ tự ưu tiên.

### Xuất toàn bộ câu tách

Có thể tính trước **possibleSuffix[i]** để bỏ các nhánh dẫn tới hậu tố vô nghiệm, sau đó DFS thử mọi từ khớp và ghi lại dãy từ. Tuy nhiên, số kết quả có thể hàm mũ; cần cân nhắc **giới hạn số lời giải**, phân trang hoặc chỉ đếm nếu đề không yêu cầu liệt kê.

### Mỗi từ chỉ được dùng một lần

Bài tiêu chuẩn cho phép lặp lại từ. Nếu mỗi mục từ có lượng sử dụng hạn chế, trạng thái phải ghi nhớ số lượng còn lại hoặc tập từ đã dùng; khi từ điển nhỏ có thể dùng bitmask. Một chiều vị trí i thường **không đủ** vì hai cách đạt cùng i nhưng đã dùng những tập từ khác nhau có các lựa chọn tương lai khác nhau.

### Một từ điển, nhiều chuỗi truy vấn

Có thể **xây Trie một lần** rồi dùng nó cho nhiều chuỗi đầu vào khác nhau. Mỗi chuỗi vẫn cần DP riêng, nhưng không cần dựng lại Trie. Nếu từ điển thường xuyên cập nhật, phải bảo đảm dữ liệu Trie phản ánh phiên bản mới trước khi trả truy vấn.

## 14. Trường hợp biên và bộ kiểm thử

| Chuỗi S | Từ điển D | Tồn tại | Số cách | Ít từ nhất | Một cách |
| --- | --- | --- | ---: | ---: | --- |
| "" | {"cat"} | true | 1 | 0 | [] |
| "a" | {} | false | 0 | — | [] |
| "abc" | {"abc"} | true | 1 | 1 | [abc] |
| "catsanddog" | {"cat","cats","and","sand","dog"} | true | 2 | 3 | [cat,sand,dog] |
| "catsandog" | {"cat","cats","and","sand","dog"} | false | 0 | — | [] |
| "aaaa" | {"a","aa","aaa"} | true | 7 | 2 | [a,aaa] |
| "cars" | {"car","ca","rs"} | true | 1 | 2 | [ca,rs] |
| "abcdef" | {"abcd","abc","def","e","f"} | true | 2 | 2 | [abc,def] |
| "café🥭sữa" | {"café","🥭","sữa"} | true | 1 | 3 | [café,🥭,sữa] |

Dấu “—” ở cột ít từ nhất nghĩa là **không có lời giải**, chứ không phải 0 từ. Trong API minh họa, trường minWords nhận **−1** cho trường hợp ấy.

### Bài kiểm thử ngẫu nhiên bằng chuẩn tham chiếu

Với chuỗi ngắn n≤10 và từ điển nhỏ, có thể thử **mọi vị trí cắt** bằng quay lui và thu được danh sách đầy đủ các phương án. Sau đó đối chiếu:

1. possible[n] có bằng “số phương án >0” hay không?
2. ways[n] có bằng số phương án không?
3. minWords[n] có bằng số phần tử nhỏ nhất trong một phương án không?
4. Ghép chuỗi từ **oneMin** có đúng bằng S không?
5. Mỗi từ trong oneMin có thuộc D không?
6. Với các từ bị lặp trong đầu vào từ điển, kết quả đếm có giữ nguyên khi coi D là tập không?
7. Với từ có emoji hoặc dấu tiếng Việt, có điểm cắt nào chia đôi surrogate pair không?

Kiểm thử với chuỗi **không thể tách ở gần cuối**, chứ không chỉ chuỗi vô nghiệm ngay từ ký tự đầu. Ví dụ "catsandog" có nhiều tiền tố hợp lệ, nhưng không có từ cuối phù hợp để phủ hết chuỗi.

## 15. Lỗi phổ biến khi giải bài

1. **Quên ways[0]=1.** Khi đó DP đếm có thể không tạo được một cách nào từ chuỗi rỗng.
2. **Nhầm ranh giới [start,end).** end là chỉ số ngay sau từ, không phải chỉ số ký tự cuối.
3. **Chỉ thấy một từ khớp đã trả true.** Phải bảo đảm phần trước/sau từ cũng tách được.
4. **Dùng greedy longest-first mà không chứng minh.** "cars" và "abcdef" là hai phản ví dụ.
5. **Không memoize các hậu tố đã xét.** Thử vét cạn có thể lặp lại cùng bài toán con rất nhiều lần.
6. **Đếm một cách nhiều lần vì từ điển lặp mục từ.** Bản chuẩn dùng tập từ, không dùng số bản sao của mục từ làm số cách.
7. **Dừng sau cách đầu tiên khi đang đếm.** Điều này chỉ hợp lý cho biến thể tồn tại, không phải biến thể đếm.
8. **Dùng int hoặc long cho số cách không có giới hạn.** Có thể tràn; chọn BigInteger hoặc modulo theo đề.
9. **Dùng ways modulo bằng 0 để kết luận không tồn tại.** Trạng thái đạt và giá trị modulo phải tách biệt.
10. **Cho phép từ rỗng trong mô hình dùng lại vô hạn.** Sẽ có cạnh i→i, phá thứ tự DP và có nguy cơ vô số chuỗi từ.
11. **Quên xử lý S rỗng.** Theo quy ước bài học, có một cách rỗng và min=0.
12. **Cho rằng mọi từ phân biệt có thể dùng một lần.** Bản chuẩn cho phép tái sử dụng từ nhiều lần, cần sửa state nếu bài cấm.
13. **Tính độ phức tạp substring như O(1) trong Java.** Việc tạo/cấp phát/tính hash chuỗi con phụ thuộc độ dài.
14. **Nhầm Unicode code point với char hoặc ký tự hiển thị.** Có thể tách sai vị trí đối với emoji, dấu tổ hợp.
15. **Chuẩn hóa chỉ từ điển mà không chuẩn hóa đầu vào.** Hai phía phải dùng cùng quy tắc so khớp.
16. **Chỉ lưu minWords nhưng cần in phương án.** Phải có parent hoặc cách phục hồi dựa trên các bảng DP.
17. **Khi hòa min, tự tuyên bố phương án từ điển nhỏ nhất.** Phải đặt và cài quy tắc tie-breaker thực sự.
18. **Liệt kê mọi cách mà không xét kích thước đầu ra.** Có thể vượt thời gian/bộ nhớ vì số cách hàm mũ.
19. **Thiếu điều kiện kiểm tra phần tử từ điển null.** Với Java API, null cần có hợp đồng xử lý rõ ràng.
20. **Áp dụng DP chỉ có vị trí khi còn ràng buộc số lần dùng hoặc tập từ đã dùng.** Trạng thái chưa đủ thông tin cho tương lai.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Với S="leetcode", D={"leet","code"}, kết quả tồn tại và ít từ nhất là gì?  
**Đáp án:** Tồn tại=true, minWords=2, cách tách [leet,code].

**Câu 2.** Tại sao ways[0]=1 chứ không phải 0?  
**Đáp án:** Có đúng một cách tách chuỗi rỗng thành dãy từ rỗng; nhờ vậy việc nối từ đầu tiên tạo được số cách dương.

**Câu 3.** Trong công thức ways[i], vì sao cộng ways[j] qua mọi j mà S[j:i) thuộc D không đếm trùng?  
**Đáp án:** Mỗi cách tách có điểm cắt cuối cùng j duy nhất; các nhóm lời giải theo j rời nhau.

**Câu 4.** Cho S="aaaa", D={"a","aa","aaa"}. Có bao nhiêu cách tách và ít nhất mấy từ?  
**Đáp án:** 7 cách, ít nhất 2 từ. Có 3 cách tối ưu dùng hai từ: a|aaa, aa|aa, aaa|a.

**Câu 5.** Vì sao phép cập nhật minWords[end] phải kiểm tra minWords[start] đạt được?  
**Đáp án:** Nếu start không thể tách, ta không thể lấy một đường đến start rồi nối thêm từ, và cộng 1 vào sentinel vô cực có thể gây tràn hoặc tạo đáp án giả.

**Câu 6.** Từ điển chứa hai lần "cat" có làm tăng số cách tách trong bản Word Break chuẩn không?  
**Đáp án:** Không. Từ điển được xem là tập từ hợp lệ, các cách tách phân biệt bằng vị trí cắt, không bằng số bản sao từ.

**Câu 7.** Vì sao Trie giúp so khớp nhiều từ có chung tiền tố?  
**Đáp án:** Trie dùng chung các cạnh tiền tố; từ start đi theo chuỗi một lần qua các cạnh và ghi nhận các nút terminal, không cần tạo substring mới cho từng điểm kết thúc.

**Câu 8.** Nếu phải liệt kê mọi cách tách của chuỗi rất dài có nhiều cách, liệu DP O(nL) có đảm bảo việc xuất tất cả vẫn O(nL)?  
**Đáp án:** Không. Liệt kê có chi phí theo tổng kích thước đầu ra, có thể hàm mũ, nên không thể chỉ nhìn chi phí tính trạng thái.

**Câu 9.** Với "cars" và D={"car","ca","rs"}, greedy chọn từ dài nhất có đúng không?  
**Đáp án:** Không. Greedy chọn "car", còn "s" không tách được; DP tìm "ca|rs".

**Câu 10.** Với một từ điển sử dụng cho nhiều đầu vào, tối ưu tái sử dụng nào hợp lý?  
**Đáp án:** Xây Trie một lần theo phiên bản từ điển cố định, rồi tính bảng DP mới cho từng chuỗi đầu vào.

## 17. Tóm tắt

**Word Break = quy hoạch động trên các ranh giới điểm cắt của chuỗi.** Một trạng thái i mô tả việc xử lý tiền tố S[0:i). Một cạnh từ i đến j hợp lệ khi đoạn S[i:j) là từ có trong từ điển.

- **Tồn tại:** dùng **OR** các tiền nhiệm hợp lệ.
- **Đếm:** cộng **ways** của mọi tiền nhiệm; cơ sở **ways[0]=1**.
- **Ít từ nhất:** lấy **min(minWords[prev]+1)** và lưu **parent** để phục hồi.
- **Trie:** từ mỗi ranh giới đã đạt, đi qua những tiền tố khớp để giảm kiểm tra chuỗi con; thời gian theo thao tác thường là **O(S+nL)**.
- **Chuỗi rỗng:** theo quy ước có một cách tách rỗng; **từ điển không được chứa từ rỗng** trong mô hình dùng không giới hạn.
- **Unicode:** định nghĩa rõ đơn vị chỉ số và quy tắc chuẩn hóa; với Java, code point giúp tránh cắt giữa surrogate pair.
- **Điều kiện đổi bài:** khi mỗi từ chỉ được dùng một lần, có trọng số, yêu cầu thứ tự từ điển hay phải liệt kê tất cả, cần thay trạng thái/truy vết/đánh giá độ phức tạp tương ứng.

Điều quan trọng nhất là **mỗi kết quả tiền tố được tính một lần rồi tái sử dụng**. Cách này loại bỏ phép thử lặp lại vô ích, đồng thời cho phép chuyển từ câu hỏi “có tách được không?” sang “có bao nhiêu cách?” và “cách nào tốt nhất?” chỉ bằng việc xác định đúng phép tổng hợp, cơ sở và dữ liệu truy vết.
