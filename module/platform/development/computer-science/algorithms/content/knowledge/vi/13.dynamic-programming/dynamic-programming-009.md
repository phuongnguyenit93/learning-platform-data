# Truy vết để khôi phục một lời giải trong quy hoạch động

## 1. Tính giá trị tối ưu khác với khôi phục lời giải

**Quy hoạch động (dynamic programming – DP)** thường được giới thiệu bằng một bảng ghi giá trị tốt nhất, chẳng hạn tổng giá trị ba lô lớn nhất, độ dài dãy con chung dài nhất hoặc số bước chỉnh sửa nhỏ nhất. Nhưng đề bài thực tế có thể yêu cầu nhiều hơn một con số:

- Với ba lô 0/1: **những vật phẩm nào** được lấy?
- Với LCS (longest common subsequence): **dãy con chung cụ thể** là gì, thay vì chỉ độ dài?
- Với đường đi chi phí nhỏ nhất: **tọa độ hoặc đỉnh nào** được đi qua?
- Với xâu và phép chỉnh sửa: **chuỗi thao tác insert/delete/replace** nào biến chuỗi A thành B?
- Với lập lịch: **những công việc nào** tạo nên lợi nhuận tối đa?

Ví dụ, biết ba lô có giá trị tối ưu bằng 12 chưa đủ để nói đã lấy vật phẩm nào. Để trả lại **một nhân chứng (witness)** chứng minh giá trị ấy có thể đạt được, ta phải **truy vết (traceback/backtracking of DP choices)** từ một trạng thái mục tiêu, lần theo các quyết định đã tạo ra giá trị tối ưu và đi về trạng thái cơ sở.

Ở đây **truy vết DP** khác với thuật toán quay lui (backtracking) tìm kiếm toàn bộ nhánh: sau khi DP đã tính xong, truy vết thường chỉ **đi theo một đường đi tối ưu đã được xác định**, không duyệt mọi tổ hợp một lần nữa.

### Ba phần của một lời giải DP đầy đủ

1. **Định nghĩa trạng thái:** dp[state] đại diện cho gì và trên dữ liệu nào?
2. **Chuyển trạng thái:** từ những trạng thái nhỏ hơn và lựa chọn nào ta đạt được dp[state]?
3. **Khôi phục:** từ trạng thái đích, chọn một chuyển trạng thái đạt đúng giá trị dp[state], ghi nhận quyết định, rồi chuyển về trạng thái tiền nhiệm; lặp đến base case.

Muốn truy vết đúng, phải giữ nhất quán cả **giá trị**, **chuyển trạng thái**, **hướng dựng bảng** và **quy ước phá hòa**. Nhiều chương trình tính dp đúng nhưng truy vết sai vì không lưu đủ thông tin hoặc vì dùng lại bảng đã được tối ưu bộ nhớ.

## 2. Hai chiến lược lưu dấu quyết định

Có hai cách chính để khôi phục một lời giải sau khi tính bảng DP.

### Cách A – Lưu con trỏ/trạng thái cha hoặc quyết định

Mỗi khi chọn một nhánh tốt nhất cho dp[s], lưu thông tin để đi ngược:

- prev[s]: trạng thái trước khi đến s.
- choice[s]: hành động được chọn (lấy/không lấy vật phẩm, đi lên/đi trái/đi chéo).
- Một số bài chỉ cần lưu hướng 1–2 bit trên mỗi ô thay vì nguyên chỉ số cha, nếu hình dạng chuyển trạng thái cố định.

Sau khi bảng hoàn tất, bắt đầu từ s_target; đọc choice/prev, ghi hành động, cập nhật s ← prev[s] cho đến khi đạt trạng thái cơ sở.

**Ưu điểm:** truy vết đơn giản, thường O(số quyết định trong một lời giải), không cần suy luận lại nhánh. **Nhược điểm:** thêm bộ nhớ cho parent/choice, và phải chắc rằng thông tin này mô tả đúng **phiên bản DP** đã dùng để tính trạng thái.

### Cách B – Suy ngược từ các giá trị DP đã lưu

Nếu còn giữ **đầy đủ các giá trị DP ở những trạng thái cần thiết**, có thể so sánh dp[s] với các giá trị ứng viên. Ví dụ, trong ba lô 0/1, tại hàng i và sức chứa c:

- Nếu dp[i][c] == dp[i-1][c], có một lời giải tối ưu **không lấy** vật phẩm i-1, nên ta có thể về (i-1,c).
- Nếu nhánh không lấy không đạt dp[i][c], ta phải lấy vật phẩm i-1 (với trọng lượng hợp lệ), rồi về (i-1,c-w[i-1]).

Với nhiều nhánh cùng cho giá trị bằng nhau, cần chọn một chính sách nhất quán. So sánh các giá trị có thể **đủ để dựng một nghiệm tối ưu** nhưng thường **không xác định duy nhất nghiệm**.

**Ưu điểm:** không cần lưu riêng mảng parent nếu bảng DP đã có. **Nhược điểm:** phụ thuộc việc các hàng/cột DP cũ còn tồn tại, phải đối chiếu đúng công thức và không được dùng các giá trị đã bị ghi đè. Với số thực có làm tròn, so sánh bằng tuyệt đối để truy vết còn có thể thiếu an toàn; lưu quyết định khi tính thường rõ ràng hơn.

## 3. Mẫu quy trình truy vết chuẩn

Trước khi viết code, hãy trả lời các câu hỏi:

- Trạng thái đích là trạng thái nào? dp[n][W], dp[0][0], một trạng thái có giá trị tốt nhất trong cả hàng, hay min trên nhiều trạng thái cuối?
- Có một hay nhiều trạng thái cơ sở hợp lệ? Khi nào dừng?
- Mỗi chuyển trạng thái làm thay đổi chỉ số/trạng thái ra sao?
- Một lựa chọn ứng với **vật phẩm nào, ký tự nào, cạnh nào**?
- Cần xuất kết quả theo thứ tự thuận hay ngược?
- Khi nhiều nhánh cùng tối ưu, chọn nhánh nào để tái lập kết quả nhất quán?

Khung giả mã:

~~~text
reconstruct(target):
    current = target
    reversedActions = []

    while not isBaseCase(current):
        action, previous = chooseOptimalTransition(current, dp, choice)
        if action contributesToAnswer:
            reversedActions.append(action)
        current = previous

    reverse(reversedActions) if transitions were followed backwards
    return reversedActions
~~~

Đây là **giả mã**, không phải chương trình Java tự chạy. Trong bài thực tế, một số chuyển trạng thái như “không lấy vật phẩm” không đóng góp phần tử vào kết quả; một số khác như “lấy vật phẩm” thêm một chỉ số. Với LCS, các bước bỏ qua ký tự chỉ di chuyển chỉ số mà không thêm vào chuỗi.

### Ba bất biến khi truy vết

1. **Giá trị còn lại có thể đạt được:** trạng thái hiện tại và quyết định đang xét vẫn nằm trên một đường chuyển trạng thái tối ưu.
2. **Mỗi bước đều tiến về cơ sở:** chỉ số i giảm, hoặc i/j tăng theo một bảng suffix, hoặc một đại lượng thứ tự tốt giảm nghiêm ngặt để không lặp vô hạn.
3. **Đầu ra là các quyết định thật của chuyển trạng thái:** không thêm vật phẩm/ký tự nằm ngoài miền đã giải; không sử dụng một lựa chọn hai lần nếu mô hình chỉ cho phép dùng một lần.

Nếu một trong ba bất biến không còn đúng, kết quả truy vết có thể không khả thi dù giá trị dp cuối cùng vẫn chính xác.

## 4. Ví dụ 1 – Ba lô 0/1: trạng thái, chuyển và truy vết

Bài toán: có n vật phẩm, mỗi vật phẩm i có trọng lượng w[i] > 0 và giá trị v[i] ≥ 0, sức chứa nguyên W ≥ 0. Mỗi vật phẩm được lấy **tối đa một lần** và không thể lấy phân số. Ta muốn tối đa hóa tổng giá trị, không vượt W.

Định nghĩa trạng thái:

~~~text
dp[i][c] = gia tri lon nhat khi chi xet i vat pham dau tien
           va suc chua khong vuot c

0 <= i <= n
0 <= c <= W
~~~

Base case: dp[0][c]=0 với mọi c (không có vật phẩm nào thì giá trị tối đa bằng 0).

Đối với vật phẩm thứ i (đánh số từ 1 trong công thức, chỉ số mảng là i-1):

~~~text
notTake = dp[i-1][c]

if w[i-1] <= c:
    take = dp[i-1][c-w[i-1]] + v[i-1]
    dp[i][c] = max(notTake, take)
else:
    dp[i][c] = notTake
~~~

Chú ý rằng nhánh take đọc từ **hàng i-1**, không phải hàng i, để vật phẩm hiện tại không bị dùng nhiều lần.

### Bảng ví dụ cụ thể

Chọn bốn vật phẩm theo thứ tự ban đầu:

| Chỉ số 0-based | Trọng lượng | Giá trị |
| --- | ---: | ---: |
| 0 | 2 | 3 |
| 1 | 3 | 4 |
| 2 | 4 | 5 |
| 3 | 5 | 8 |

Với W=8, bảng giá trị dp theo c=0..8 là:

~~~text
suc chua c:    0  1  2  3  4  5  6  7  8
i = 0:         0  0  0  0  0  0  0  0  0
i = 1 (w2):    0  0  3  3  3  3  3  3  3
i = 2 (w3):    0  0  3  4  4  7  7  7  7
i = 3 (w4):    0  0  3  4  5  7  8  9  9
i = 4 (w5):    0  0  3  4  5  8  8 11 12
~~~

Giá trị mục tiêu là dp[4][8]=12. Để tìm vật phẩm:

1. Bắt đầu (i=4,c=8). Nhánh **lấy vật phẩm 3** đạt dp[3][3]+8=4+8=12, lớn hơn nhánh bỏ dp[3][8]=9. Chọn chỉ số 3, chuyển sang (3,3).
2. Ở (3,3), vật phẩm 2 nặng 4 > 3, không thể lấy. Chuyển sang (2,3).
3. Ở (2,3), lấy vật phẩm 1: dp[1][0]+4=4 > dp[1][3]=3. Chọn chỉ số 1, chuyển sang (1,0).
4. Ở (1,0), vật phẩm 0 nặng 2 > 0, bỏ và về (0,0).
5. Dừng ở i=0. Vì truy vết từ cuối về đầu, danh sách chỉ số thu được là [3,1]. Đảo lại thành **[1,3]**.

Kiểm chứng: trọng lượng 3+5=8 ≤ W và giá trị 4+8=**12**, đúng với dp[4][8]. Chú ý **không dùng** đáp án dp[4][8] như thể nó đã chứa sẵn danh sách lựa chọn; chính chuỗi chuyển trạng thái mới cho biết hai vật phẩm được lấy.

## 5. Lưu quyết định take[i][c] và xử lý hòa

Một cách triển khai dễ kiểm tra là dùng hai bảng:

- dp[i][c]: giá trị tốt nhất.
- take[i][c]: true nếu tại trạng thái (i,c), thuật toán chọn lấy **vật phẩm i-1** để đạt giá trị tốt nhất.

Khi xét một trạng thái:

~~~text
best = dp[i-1][c]
take[i][c] = false

if w[i-1] <= c:
    candidate = dp[i-1][c-w[i-1]] + v[i-1]
    if candidate > best:
        best = candidate
        take[i][c] = true

dp[i][c] = best
~~~

Dùng dấu **>** thay vì **≥** nghĩa là nếu hai lựa chọn có cùng giá trị, ta **ưu tiên bỏ vật phẩm đang xét**. Quy tắc phá hòa này:

- Không làm giảm giá trị tối ưu, vì hai nhánh có cùng giá trị.
- Làm đầu ra ổn định/tái lập với cùng dữ liệu và cùng thứ tự vật phẩm.
- **Không bảo đảm** ít vật phẩm nhất, tổng trọng lượng nhỏ nhất hoặc danh sách chỉ số theo thứ tự từ điển nhỏ nhất. Nếu muốn tiêu chí phụ đó, phải đưa nó vào mô hình so sánh kết quả và chứng minh đúng.

Khi truy vết theo take:

~~~text
i = n
c = W
chosen = []

while i > 0:
    if take[i][c]:
        chosen.append(i-1)
        c -= w[i-1]
    i -= 1

reverse(chosen)
~~~

Điểm dễ sai là thay đổi **c ngay khi take=true** nhưng không thay đổi c nếu take=false. Bước i-- luôn diễn ra vì mỗi hàng DP biểu diễn việc đã xem xét thêm đúng một vật phẩm. Nếu lấy vật phẩm i-1 mà vẫn giữ c cũ, các lựa chọn được khôi phục có thể vượt sức chứa.

### Có cần lưu cả dp và take?

Không bắt buộc. Nếu còn dp đầy đủ, có thể truy vết bằng cách so sánh dp[i][c] với dp[i-1][c]. Nếu bằng nhau thì bỏ vật phẩm i-1; nếu không bằng và vật phẩm vừa khả thi vừa làm đạt dp[i][c], lấy nó. Tuy nhiên, bảng take rõ ràng, giảm khả năng nhầm quy tắc hòa khi viết phần khôi phục.

**Bộ nhớ:** dp là O(nW), take cũng O(nW) trạng thái. Java boolean[][] thường không phải cấu trúc bit nén lý tưởng; nếu bộ nhớ quan trọng, có thể lưu quyết định vào bitset hoặc tìm cách tái tính, nhưng cần phân tích độ phức tạp và khả năng truy vết.

## 6. Vì sao nén DP còn một chiều có thể làm mất khả năng truy vết?

Bài ba lô 0/1 chỉ hỏi **giá trị tối ưu** có thể dùng mảng dp[c] duy nhất:

~~~text
dp[0..W] = 0

for each item i:
    for c from W down to w[i]:
        dp[c] = max(dp[c], dp[c-w[i]] + v[i])
~~~

Chiều **giảm dần** của c là bắt buộc cho 0/1: khi đang xử lý vật phẩm i, dp[c-w[i]] phải thuộc kết quả của các vật phẩm **trước i**. Nếu duyệt tăng dần, có nguy cơ dùng giá trị vừa cập nhật trong cùng lượt và lấy một vật phẩm nhiều lần.

Sau khi nén, dp[c] ở cuối không còn chứa **toàn bộ các hàng lịch sử dp[i][c]**. Bởi vậy, không thể đơn giản áp dụng phép so dp[i][c] với dp[i-1][c] để truy vết: các hàng i-1 đã bị ghi đè.

**Lỗi thường gặp:** khi cập nhật dp[c], chỉ lưu parent[c] = i rồi về c-w[i] trong một lần truy vết cuối cùng. Thông tin parent[c-w[i]] sau đó có thể bị **ghi đè bởi một vật phẩm ở lượt sau**, không phản ánh cùng chuỗi quyết định đã tạo dp[c]. Kết quả thậm chí có thể dùng một vật phẩm quá một lần hoặc dựng ra giá trị không khớp dp[W].

Một số giải pháp hợp lệ:

1. **Giữ bảng dp 2D** và truy vết từ (n,W). Đây là cách dễ kiểm chứng nhất.
2. **Giữ bảng quyết định take 2D** khi tính DP 1D, nhưng phải bảo đảm take[i][c] ghi nhận chính chuyển trạng thái ở **lượt i**. Khi truy vết giảm i, các quyết định theo từng lớp vẫn hợp lệ.
3. **Checkpoint hoặc tính lại một số hàng** khi cần truy vết, đánh đổi thêm thời gian để dùng ít bộ nhớ.
4. **Giữ cấu trúc cha bất biến theo phiên bản** cho mỗi cập nhật được chọn; tránh để các con trỏ trỏ tới trạng thái đã bị thay đổi. Cần kiểm soát số node được tạo và độ phức tạp.
5. Nếu bài toán có thuật toán truy vết tiết kiệm bộ nhớ đặc thù, dùng thuật toán đó thay vì tự suy đoán parent từ mảng dp cuối.

Kết luận về nén bộ nhớ: **O(W) bộ nhớ để tính giá trị không tự động đồng nghĩa với O(W) bộ nhớ để lấy danh sách vật phẩm**. Yêu cầu đầu ra có thể làm thay đổi phương án DP tốt nhất.

## 7. Ví dụ 2 – LCS: khôi phục dãy con chung, không chỉ độ dài

Cho hai chuỗi A và B. **Dãy con (subsequence)** giữ nguyên thứ tự tương đối các ký tự nhưng không bắt buộc nằm liền nhau. LCS là một dãy con chung có độ dài lớn nhất.

Ví dụ:

~~~text
A = "ABCDE"
B = "ACE"

LCS length = 3
One LCS    = "ACE"
~~~

Định nghĩa dp[i][j] là **độ dài LCS của hai hậu tố** A[i..) và B[j..), với 0≤i≤|A|, 0≤j≤|B|.

~~~text
if i == len(A) or j == len(B):
    dp[i][j] = 0
else if A[i] == B[j]:
    dp[i][j] = 1 + dp[i+1][j+1]
else:
    dp[i][j] = max(dp[i+1][j], dp[i][j+1])
~~~

Tính bảng từ **cuối chuỗi về đầu** để các trạng thái bên phải và bên dưới đã có kết quả. Độ dài tối ưu nằm ở dp[0][0].

### Truy vết LCS từ trạng thái đích

Bắt đầu i=0,j=0; trong khi i<|A| và j<|B|:

- Nếu A[i]==B[j], thêm ký tự đó vào kết quả rồi tăng **cả i và j**.
- Nếu khác nhau, so dp[i+1][j] với dp[i][j+1]:
  - Nếu dp[i+1][j] ≥ dp[i][j+1], bỏ qua A[i], tăng i.
  - Ngược lại, bỏ qua B[j], tăng j.
- Dừng khi hết một chuỗi.

Đối với DP hậu tố này, khi hai ký tự hiện tại bằng nhau, luôn tồn tại một LCS tối ưu bắt đầu bằng ký tự ấy; việc chọn đường chéo là hợp lệ. Với ký tự khác nhau, ít nhất một nhánh bỏ qua ký tự đầu của một chuỗi đạt đúng giá trị tối ưu. Trong trường hợp hai nhánh bằng nhau, có thể chọn một nhánh tùy quy tắc phá hòa.

Kết quả LCS không nhất thiết duy nhất. Với A="ab", B="ba", các LCS có độ dài 1 là "a" và "b". Quy tắc **ưu tiên tăng i khi hòa** trong ví dụ Java bên dưới cho ra **"b"**. Cùng độ dài tối ưu không có nghĩa mọi chiến lược truy vết trả cùng một chuỗi.

### Hướng dựng bảng quyết định hướng truy vết

Một cài đặt khác định nghĩa dp[i][j] cho **hai tiền tố** A[0..i) và B[0..j). Khi đó dựng bảng từ đầu về cuối và truy vết từ (len(A),len(B)) đi **lùi chỉ số**. Hai kiểu định nghĩa đều đúng, nhưng không thể lấy công thức của bảng tiền tố rồi truy vết theo bảng hậu tố, hoặc ngược lại.

**Độ phức tạp:** bảng LCS kích thước (n+1)×(m+1) được dựng O(nm) thời gian và O(nm) bộ nhớ; truy vết một nghiệm O(n+m) thời gian và O(L) bộ nhớ đầu ra với L là độ dài LCS. Nếu chỉ cần **độ dài**, có thể nén còn O(min(n,m)) bộ nhớ; nhưng để khôi phục chuỗi bằng cách truy vết trực tiếp, cần giữ thông tin hoặc dùng kỹ thuật chuyên biệt như Hirschberg.

### Về Unicode và Java

Trong mã Java minh họa, String.length() và charAt() làm việc theo **đơn vị mã UTF-16**, không hẳn theo Unicode code point hay cụm chữ người dùng nhìn thấy. Bài kiểm thử dùng ASCII để hợp đồng rõ ràng. Nếu bài toán LCS trên code point thực, hãy chuyển đầu vào sang dãy code point và chạy DP trên dãy đó; nếu yêu cầu tương đương theo ngôn ngữ, còn cần đặc tả chuẩn hóa Unicode và cách so sánh.

## 8. Java 17 – Chương trình hoàn chỉnh khôi phục hai lời giải

Ví dụ gồm hai hàm độc lập: ba lô 0/1 trả **giá trị, trọng lượng và chỉ số vật phẩm được chọn**; LCS trả **một chuỗi chung dài nhất**. Cả hai không sửa dữ liệu đầu vào. Dữ liệu minh họa đủ nhỏ để lưu bảng 2D.

Lưu toàn bộ mã sau vào tệp **DpTracebackDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class DpTracebackDemo {

    record Item(int weight, int value) {
        Item {
            if (weight <= 0 || value < 0) {
                throw new IllegalArgumentException(
                        "weight must be positive and value nonnegative");
            }
        }
    }

    record KnapsackAnswer(long value, int usedWeight,
                          List<Integer> indices) {}

    // Tra ve gia tri toi uu VA chi so 0-based cac vat pham da chon.
    static KnapsackAnswer knapsack(Item[] items, int capacity) {
        Objects.requireNonNull(items, "items");
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity must be >= 0");
        }
        for (Item item : items) {
            Objects.requireNonNull(item, "item");
        }

        int n = items.length;
        long[][] dp = new long[n + 1][capacity + 1];
        boolean[][] take = new boolean[n + 1][capacity + 1];

        for (int i = 1; i <= n; i++) {
            Item item = items[i - 1];
            for (int c = 0; c <= capacity; c++) {
                long best = dp[i - 1][c];
                if (item.weight() <= c) {
                    long candidate = dp[i - 1][c - item.weight()]
                            + item.value();

                    // Neu bang nhau thi uu tien KHONG lay vat pham.
                    if (candidate > best) {
                        best = candidate;
                        take[i][c] = true;
                    }
                }
                dp[i][c] = best;
            }
        }

        List<Integer> chosenReversed = new ArrayList<>();
        int remaining = capacity;

        for (int i = n; i >= 1; i--) {
            if (take[i][remaining]) {
                chosenReversed.add(i - 1);
                remaining -= items[i - 1].weight();
            }
        }
        Collections.reverse(chosenReversed);

        return new KnapsackAnswer(
                dp[n][capacity],
                capacity - remaining,
                List.copyOf(chosenReversed));
    }

    // LCS cho chuoi so sanh theo don vi ma UTF-16 (char).
    static String lcs(String a, String b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");

        int n = a.length(), m = b.length();
        int[][] dp = new int[n + 1][m + 1];

        // dp[i][j] la LCS length cua hai hau to a[i..], b[j..].
        for (int i = n - 1; i >= 0; i--) {
            for (int j = m - 1; j >= 0; j--) {
                if (a.charAt(i) == b.charAt(j)) {
                    dp[i][j] = dp[i + 1][j + 1] + 1;
                } else {
                    dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
                }
            }
        }

        StringBuilder answer = new StringBuilder();
        int i = 0, j = 0;

        while (i < n && j < m) {
            if (a.charAt(i) == b.charAt(j)) {
                answer.append(a.charAt(i));
                i++;
                j++;
            } else if (dp[i + 1][j] >= dp[i][j + 1]) {
                i++; // Pha hoa: uu tien bo qua ky tu cua a.
            } else {
                j++;
            }
        }
        return answer.toString();
    }

    public static void main(String[] args) {
        Item[] items = {
                new Item(2, 3),
                new Item(3, 4),
                new Item(4, 5),
                new Item(5, 8)
        };
        KnapsackAnswer ans = knapsack(items, 8);

        System.out.println("knapsack value = " + ans.value());
        System.out.println("knapsack weight = " + ans.usedWeight());
        System.out.println("knapsack indices = " + ans.indices());
        System.out.println("empty capacity = " +
                knapsack(items, 0).indices());

        System.out.println("LCS(ABCDE,ACE) = " + lcs("ABCDE", "ACE"));
        System.out.println("LCS(ab,ba) = " + lcs("ab", "ba"));
        System.out.println("empty LCS = '" + lcs("", "ABC") + "'");

        try {
            knapsack(items, -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid capacity: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên trong thư mục chứa tệp:

~~~bash
javac DpTracebackDemo.java
java DpTracebackDemo
~~~

**Stdout chính xác:**

~~~text
knapsack value = 12
knapsack weight = 8
knapsack indices = [1, 3]
empty capacity = []
LCS(ABCDE,ACE) = ACE
LCS(ab,ba) = b
empty LCS = ''
invalid capacity: capacity must be >= 0
~~~

### Kiểm chứng đầu ra từng bước

- knapsack dùng bốn vật phẩm (w,v)=(2,3),(3,4),(4,5),(5,8) và W=8. Chọn chỉ số 1 và 3 có tổng trọng lượng 3+5=8, tổng giá trị 4+8=12. Bảng dp[4][8] cũng bằng 12, nên nghiệm khôi phục vừa khả thi vừa đạt giá trị tối ưu.
- Với W=0 và mọi trọng lượng đều dương, không thể lấy vật phẩm nào, nên danh sách được chọn rỗng.
- LCS("ABCDE","ACE") là "ACE". Khi A="ab", B="ba" và hai nhánh cùng độ dài, quy tắc tăng i trả "b"; kết quả "a" cũng dài nhất nhưng không được chọn theo quy tắc này.
- LCS với chuỗi rỗng trả chuỗi rỗng. Sức chứa âm bị từ chối trước khi cấp phát bảng.

### Vì sao mã này dễ truy vết đúng?

- Hàm knapsack dùng bảng theo cả **hàng i và cột sức chứa c**, nên take[i][c] được gắn với trạng thái chính xác khi vừa tính. Trong vòng truy vết, i luôn giảm; remaining chỉ giảm khi take=true.
- Giá trị dùng long để giảm nguy cơ tràn khi cộng nhiều item.value int; với mảng Item[] hợp lệ, tổng các giá trị int không âm vẫn nằm trong miền long do kích thước mảng Java hữu hạn.
- Chỉ số trả về là **0-based**, đúng với thứ tự items đầu vào; Collections.reverse đưa các chỉ số về thứ tự tăng dần.
- Hàm lcs dựng bảng **hậu tố** từ n-1,m-1 về 0; sau đó đi **xuôi** i,j. Vì mỗi vòng tăng i hoặc j, nó kết thúc sau nhiều nhất n+m bước.
- Mã không khẳng định tạo LCS **nhỏ nhất theo từ điển**, và cũng không xử lý định nghĩa Unicode grapheme phức tạp: hai yêu cầu ấy cần một hợp đồng và thuật toán bổ sung.

### Chi phí

| Hàm | Dựng DP | Truy vết | Bộ nhớ phụ |
| --- | --- | --- | --- |
| knapsack với n vật phẩm, W nguyên | O(nW) | O(n) | O(nW) cho dp và take, cộng O(số vật phẩm đã chọn) |
| lcs với hai chuỗi dài n,m | O(nm) | O(n+m) | O(nm) cho bảng, cộng O(L) đầu ra |

Bộ nhớ của mảng nhiều chiều Java còn có overhead đối tượng từng hàng. Nếu n hoặc W đủ lớn để bảng O(nW) không thể cấp phát, chương trình có thể báo lỗi thiếu bộ nhớ; phải chọn phương án thuật toán khác thay vì cố tăng W vô hạn. Độ phức tạp O(nW) cho ba lô theo sức chứa nguyên là **giả đa thức**, không phải đa thức theo số bit biểu diễn W.

## 9. Truy vết ở các dạng DP khác

### Đường đi tối ưu trong bảng lưới

Giả sử được đi chỉ sang phải hoặc xuống dưới trên một ma trận, và muốn chi phí đường đi nhỏ nhất từ (0,0) đến (R-1,C-1). Với chi phí cell[r][c]:

~~~text
dp[r][c] = cell[r][c] +
    min(dp[r-1][c], dp[r][c-1])    (cac hang/cot bien xu ly rieng)
~~~

Mỗi ô có thể lưu parent = UP hoặc LEFT, tương ứng ô tiền nhiệm đã tạo min. Khi truy vết từ (R-1,C-1), lặp theo parent về (0,0), ghi từng tọa độ, sau đó đảo danh sách. Mỗi bước làm r hoặc c giảm nên tối đa O(R+C) bước. Nếu chỉ cần một con đường và giữ đủ dp, cũng có thể so hai ô tiền nhiệm để tìm nhánh đạt min.

**Điều kiện đúng:** đây là mô hình chỉ có chuyển phải/xuống, không có cạnh chu kỳ. Nếu cho phép di chuyển bốn hướng tùy ý với trọng số, cấu trúc trạng thái và thuật toán có thể phải đổi (ví dụ tìm đường đi trên đồ thị), không thể lấy nguyên công thức bảng lưới.

### Edit distance và chuỗi thao tác

Với khoảng cách chỉnh sửa Levenshtein, mỗi trạng thái thường có các lựa chọn:

- Giữ ký tự bằng nhau hoặc thay thế từ ô chéo.
- Xóa một ký tự từ ô phía trên/bên cạnh tùy định nghĩa chỉ số.
- Chèn một ký tự từ ô còn lại.

Bảng dp lưu **chi phí tối ưu**, còn bảng parent hoặc việc so sánh với các ô tiền nhiệm giúp khôi phục **một chuỗi thao tác**. Nếu có nhiều đường cùng chi phí, ưu tiên thao tác nào sẽ quyết định danh sách thao tác. Muốn bảo đảm danh sách có ý nghĩa, mỗi bước phải cập nhật đúng cả **chỉ số của hai chuỗi** và phân biệt trường hợp ký tự khớp (chi phí 0) với thay thế (chi phí 1).

### LIS – Dãy con tăng dài nhất

Với LIS, một thiết kế O(n²) dùng len[i] = độ dài LIS kết thúc tại chỉ số i, và parent[i] = chỉ số phần tử đứng ngay trước i trong lời giải đã chọn. Khi tìm được vị trí kết thúc có len lớn nhất, lần theo parent[i] tới -1 rồi đảo danh sách để được các phần tử theo thứ tự.

Với giải pháp LIS O(n log n) dùng mảng tail, mảng **giá trị tail đơn thuần không phải là LIS thực tế**. Muốn truy vết, cần lưu chỉ số phần tử cuối tương ứng cho từng độ dài và predecessor cho từng vị trí khi cập nhật. Vì thế, một cấu trúc đủ để tính độ dài chưa chắc đủ để xuất nghiệm.

### Đếm số cách so với tìm một cách

Bài toán **đếm số cách** và bài toán **tối ưu + truy vết một cách** có mục tiêu khác nhau. Nếu dp[s] chỉ chứa **số cách**, số đó không chỉ ra trực tiếp một đường đi. Muốn dựng một cách hợp lệ, cần biết nhánh nào có số cách >0 và đi theo điều kiện tương ứng; muốn liệt kê **mọi cách**, có thể phải duyệt nhánh và chi phí xuất kết quả tăng theo số nghiệm, có thể là hàm mũ.

Tương tự, muốn xuất **tất cả** LCS tối ưu thì việc đi một nhánh khi hòa là chưa đủ; phải xét nhiều nhánh, loại bỏ kết quả trùng nếu yêu cầu và chấp nhận chi phí có thể rất lớn.

## 10. Chứng minh tính đúng của truy vết

Chứng minh một chương trình DP có truy vết thường tách làm hai mệnh đề.

**Mệnh đề 1 – Giá trị DP đúng.** Dùng quy nạp theo thứ tự tính trạng thái: base case đúng, mỗi chuyển trạng thái xét hết các lựa chọn hợp lệ, và giá trị tốt nhất được lấy theo min/max. Với ba lô 0/1, mỗi lời giải tối ưu trên i vật phẩm hoặc không lấy vật phẩm cuối hoặc có lấy nó, không có trường hợp thứ ba; vì vậy công thức chuyển trạng thái là đầy đủ.

**Mệnh đề 2 – Truy vết tạo nghiệm hợp lệ có đúng giá trị.** Với trạng thái hiện tại s, cho mỗi bước đã chọn phải chứng minh:

1. Chuyển trạng thái đã chọn thật sự là một nhánh hợp lệ từ trạng thái nhỏ hơn.
2. Tổng chi phí/giá trị của lựa chọn hiện tại cộng với giá trị của trạng thái tiền nhiệm bằng dp[s] (hoặc tương ứng đúng công thức min/max).
3. Có đại lượng tiến triển đơn điệu về cơ sở (ví dụ i giảm từ n về 0).
4. Các quyết định đã ghi không vi phạm ràng buộc; với ba lô 0/1 mỗi bước giảm i nên không thể lấy cùng một item hai lần.
5. Khi đến cơ sở, các lựa chọn ghép lại tạo nghiệm ban đầu và đạt đúng dp[target].

**Bất biến của truy vết ba lô:** tại trạng thái (i,c), danh sách đã chọn từ các vật phẩm chỉ số ≥i có tổng trọng lượng đúng bằng W-c, và giá trị chúng cộng dp[i][c] đúng bằng dp[n][W]. Khi take=true, cập nhật c←c-w[i-1], thêm giá trị v[i-1]; theo công thức DP, bất biến vẫn giữ. Khi take=false, dp[i][c]=dp[i-1][c] và bất biến cũng giữ. Đến i=0, dp[0][c]=0, nên giá trị của các vật phẩm đã chọn bằng dp[n][W].

**Bất biến của truy vết LCS:** tại (i,j), chuỗi kết quả đã viết là một tiền tố của **một** LCS tối ưu của hai chuỗi gốc theo các lựa chọn đã đi, và phần độ dài còn phải dựng bằng dp[i][j]. Khi ký tự khớp, thêm một ký tự rồi đi chéo; khi khác, chọn nhánh vẫn có độ dài dp[i][j]. Khi đạt biên, dp=0 và kết quả thu được có độ dài dp[0][0].

Không thể kết luận truy vết đúng chỉ vì “tổng trọng lượng không vượt W”. Một nghiệm hợp lệ chưa chắc tối ưu; phải đối chiếu cả giá trị nghiệm với dp[target].

## 11. Đánh đổi thời gian–bộ nhớ khi cần cả lời giải

| Cách làm | Dữ liệu lưu | Lợi thế | Đánh đổi |
| --- | --- | --- | --- |
| Lưu đầy đủ dp 2D | Giá trị từng trạng thái | Có thể truy vết qua so sánh ô; dễ chứng minh | O(số trạng thái) bộ nhớ |
| DP đầy đủ + bảng choice | Giá trị và nhánh đã chọn | Truy vết rõ ràng; tie-breaking được chốt | Thêm bộ nhớ choice |
| DP nén một chiều | Chỉ giá trị của một/lát cắt trạng thái | Tiết kiệm bộ nhớ khi chỉ cần đáp số | Không có lịch sử để truy vết trực tiếp |
| DP nén + choice theo lớp | Giá trị hiện tại và quyết định của từng trạng thái/lượt | Có thể dựng nghiệm mà không giữ toàn bộ giá trị | Choice vẫn có thể O(số trạng thái) |
| Tính lại/checkpoint | Một phần trạng thái và tái tính đoạn cần thiết | Giảm bộ nhớ đỉnh | Tăng thời gian tính/độ phức tạp mã |
| Thuật toán truy vết chuyên biệt | Cấu trúc phụ tối ưu hóa cho bài | Có thể giảm bộ nhớ đáng kể | Cần chứng minh riêng, không áp dụng mọi DP |

Ví dụ **Hirschberg** cho LCS dùng các lần tính chiều dài LCS bằng DP một chiều ở hai phía điểm chia để tìm chỗ tách của một LCS tối ưu, sau đó đệ quy khôi phục. Nó có thể dùng O(nm) thời gian và O(min(n,m)) bộ nhớ làm việc (ngoài đầu ra) với thiết kế phù hợp. Đây là ví dụ rằng không phải lúc nào muốn truy vết cũng cần giữ toàn bộ bảng 2D, nhưng đổi lại thuật toán phức tạp hơn.

**Khả năng truy vết có thể ảnh hưởng ngay từ đầu đến thiết kế trạng thái.** Nếu đề bài yêu cầu không chỉ một nghiệm mà nghiệm có ít phần tử nhất trong số các nghiệm tối ưu, ta cần lưu hoặc so sánh thêm số phần tử; nếu muốn nghiệm có thứ tự từ điển nhỏ nhất, quy tắc phá hòa phải xét cấu trúc đáp án chứ không chỉ xét giá trị DP.

## 12. Ràng buộc dữ liệu, lỗi phổ biến và cách khắc phục

| Sai sót | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chỉ lưu dp cuối mà không giữ lịch sử | Không thể áp dụng traceback theo hàng/cột cũ | Chọn chiến lược khôi phục trước khi nén |
| Truy vết từ sai trạng thái đích | Chọn nghiệm của một bài toán khác | Xác định rõ dp[target] hoặc argmax cuối |
| Đọc sai hàng i trong ba lô 0/1 | Có thể dùng lại một vật phẩm | Nhánh take bắt buộc về hàng i-1 |
| Quên giảm c khi lấy món | Nghiệm có thể vượt sức chứa | Cập nhật remaining theo trọng lượng đã lấy |
| Trộn bảng LCS tiền tố/hậu tố | Đi sai hướng và ra chuỗi sai | Đồng bộ định nghĩa, hướng fill và traceback |
| Truy vết khi hòa không nhất quán | Kết quả không tái lập, dễ kiểm thử sai | Đặt tie policy rõ ràng và dùng ở mọi trạng thái |
| Lấy giá trị DP làm danh sách lựa chọn | Đáp án chỉ là con số | Lưu parent/choice hoặc suy ngược chuyển trạng thái |
| Con trỏ cha bị ghi đè khi nén | Sinh nghiệm không hợp lệ hoặc dùng món nhiều lần | Giữ parent theo phiên bản/lớp hoặc bảng 2D |
| Không đảo kết quả từ cuối về đầu | Thứ tự vật phẩm/ký tự/đỉnh bị ngược | Reverse khi truy vết đi từ đích về nguồn |
| Không xử lý trường hợp rỗng | Ngoài mảng hoặc truy vết vô hạn | Base case và điều kiện dừng rõ ràng |
| Dùng số thực rồi so bằng tuyệt đối | Bị tác động bởi sai số dấu phẩy động | Lưu quyết định hoặc định nghĩa sai số phù hợp |
| Không kiểm tra nghiệm sau truy vết | DP đúng nhưng danh sách sai vẫn bị bỏ qua | Tính lại tổng trọng lượng/giá trị/độ dài |
| Quên chi phí bộ nhớ | Vượt RAM với O(nW), O(nm) | Ước lượng số trạng thái và lựa chọn lưu trữ |
| Nhầm char với code point | Kết quả LCS Unicode ngoài BMP sai ngữ nghĩa | Chuyển sang code point nếu đặc tả yêu cầu |

**Chú ý tính xác định:** nếu có nhiều nghiệm cùng tối ưu, việc bộ kiểm thử đòi đúng một danh sách cụ thể có thể là yêu cầu quá mạnh, trừ khi đề bài quy định quy tắc phá hòa. Bộ kiểm thử thường nên xác minh **tính khả thi** và **đạt đúng giá trị tối ưu**; khi đã công bố tie policy mới kiểm thêm đầu ra chính xác.

## 13. Kiểm thử dựa trên thuộc tính và ví dụ biên

### Kiểm thử ba lô 0/1 có truy vết

- Không chọn chỉ số ngoài [0,n), không chọn trùng chỉ số.
- Tổng trọng lượng được khôi phục bằng usedWeight và ≤W.
- Tổng giá trị của các vật phẩm theo indices bằng dp[n][W].
- Với n nhỏ, đối chiếu tối ưu bằng duyệt tất cả 2^n tập con; danh sách có thể khác nếu tồn tại nhiều nghiệm đồng tối ưu.
- Với W=0 và mọi trọng lượng dương, indices rỗng, giá trị 0.
- Với n=0, kết quả 0, không có chỉ số.
- Trường hợp nhiều vật phẩm bằng giá trị hoặc cùng phương án tối ưu: chính sách “hòa thì bỏ món hiện tại” tạo một kết quả xác định.
- Mảng đầu vào không bị thay đổi; lỗi sức chứa âm bị từ chối.

### Kiểm thử LCS

- Chuỗi kết quả phải là một **subsequence của cả A và B**.
- Độ dài chuỗi kết quả phải bằng dp[0][0].
- Nếu một chuỗi rỗng, kết quả rỗng.
- Nếu hai chuỗi bằng nhau, chính chuỗi ấy là LCS.
- Với A="ab", B="ba", kết quả "a" hoặc "b" đều tối ưu; bản ví dụ chọn "b" theo quy tắc hòa.
- Với một bộ chữ cái nhỏ, có thể kiểm chứng ngẫu nhiên bằng brute force trên hai chuỗi ngắn.
- Với Unicode, phải định nghĩa “ký tự” là UTF-16 char, code point hay grapheme trước khi công bố kỳ vọng.

### Các ca mẫu

| Ca | Kết quả mong đợi |
| --- | --- |
| Ba lô w=[2,3,4,5], v=[3,4,5,8], W=8 | Giá trị 12; chỉ số [1,3]; trọng lượng 8 |
| Ba lô cùng dữ liệu, W=0 | Giá trị 0; chỉ số [] |
| Ba lô chỉ một vật phẩm nặng 5, W=3 | Không lấy món; giá trị 0 |
| Ba lô một vật phẩm nặng 5, W=5 | Lấy chỉ số 0 |
| Ba lô hai vật phẩm đồng giá trị tối ưu | Nghiệm hợp lệ và giá trị dp đúng; tie policy quyết định chỉ số |
| LCS("ABCDE","ACE") | "ACE" |
| LCS("ab","ba") | "b" theo chính sách hòa của ví dụ |
| LCS("","ABC") | "" |
| LCS("HELLO","HELLO") | "HELLO" |
| Sức chứa âm | IllegalArgumentException |
| Chuỗi null hoặc Item[] null | NullPointerException từ Objects.requireNonNull |

### Bài tập tự luyện

1. Với ba lô n=4 và W=8 trong bảng, hãy tự tính các hàng dp. Truy vết từ (4,8), viết rõ từng trạng thái, quyết định take/skip và kiểm tra nghiệm cuối.
2. Thay chính sách hòa ở knapsack thành “ưu tiên lấy khi candidate==best”. So sánh kết quả chỉ số trên ví dụ có nhiều nghiệm tối ưu; chứng minh giá trị vẫn tối ưu.
3. Viết lại knapsack **không có take[][]**, chỉ dùng dp[][] và suy ngược bằng so sánh dp[i][c] với dp[i-1][c]. Kiểm tra đặc biệt khi giá trị bằng 0 và khi có nhiều nghiệm.
4. Chuyển knapsack sang DP 1D. Giải thích vì sao parent[c] theo trạng thái cuối cùng có thể không còn đại diện cho cùng chuỗi quyết định; đề xuất phương án checkpoint hoặc bảng choice theo lớp.
5. Cho A="ABCBDAB", B="BDCABA". Tính độ dài LCS rồi khôi phục **một** LCS, cho biết khi hòa đã bỏ ký tự phía nào và kết quả có nhất thiết là duy nhất không.
6. Với lưới 3×3 có chi phí, xây bảng đường đi nhỏ nhất khi chỉ được đi xuống/phải; lưu hướng UP/LEFT rồi khôi phục tọa độ theo thứ tự nguồn đến đích.
7. Với bài toán LIS, sửa lời giải chỉ tính len[i] thành lời giải trả danh sách chỉ số bằng parent[i]. Tại sao mảng tail giá trị trong phương pháp O(n log n) chưa phải là đáp án LIS?
8. Thiết kế kiểm thử tự động: từ đầu ra khôi phục, tính lại giá trị/trọng lượng/độ dài và đối chiếu với dp[target]. Hãy thử cố tình sửa sai một chỉ số để thấy bài kiểm thử phát hiện.
9. Nghiên cứu phương án tiết kiệm bộ nhớ khi vẫn cần LCS, chẳng hạn Hirschberg. Trình bày đánh đổi thời gian, bộ nhớ và mức độ phức tạp khi cài đặt.

**Kết luận:** bảng DP cho biết **giá trị** nhưng không tự động cho biết **lời giải cụ thể**. Muốn truy vết, cần biết trạng thái đích, các chuyển trạng thái tối ưu, quy tắc phá hòa và điều kiện dừng; có thể lưu parent/choice hoặc suy ngược từ bảng đầy đủ. Việc nén bộ nhớ phải được thiết kế cùng lúc với yêu cầu khôi phục, vì xóa lịch sử DP có thể xóa luôn thông tin cần để dựng nghiệm.
