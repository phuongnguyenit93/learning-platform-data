# Nhánh và cận cho bài toán ba lô 0/1 (Branch and Bound for 0/1 Knapsack)

> **Chủ đề:** Computer Science Algorithms → Nhánh và cận (*Branch and Bound, B&B*).  
> **Mục tiêu:** Hiểu cây lựa chọn **lấy/bỏ** của ba lô 0/1, xây cận trên hợp lệ từ **ba lô phân số**, duy trì nghiệm tốt nhất đã biết (*incumbent*), cắt nhánh an toàn, cài **DFS Branch and Bound** và **Best-First Branch and Bound**, truy vết tập vật được chọn, kiểm tra với quy hoạch động và vét cạn, phân tích độ phức tạp và nhận diện lỗi do số thực/sắp xếp/cận sai. Ví dụ dùng **Java 17+**.

## 1. Bài toán ba lô 0/1 và mô hình tối ưu

Cho `n` vật. Vật `i` có:

- Trọng lượng nguyên dương `w_i`.
- Giá trị nguyên không âm `v_i`.
- Một bản duy nhất có thể lấy hoặc bỏ.

Ba lô có sức chứa `W >= 0`. Chọn `x_i ∈ {0,1}` để:

`maximize Σ_(i=1..n) v_i·x_i`

với điều kiện:

`Σ_(i=1..n) w_i·x_i <= W`.

Điều kiện **0/1** nghĩa là một vật chỉ được chọn **tối đa một lần**. Không được lấy một phần vật và không được dùng nhiều bản sao của cùng vật.

### 1.1. Ví dụ xuyên suốt

Xét bốn vật:

| Vật | Trọng lượng | Giá trị | Giá trị / trọng lượng |
|---|---:|---:|---:|
| A | 2 | 40 | 20 |
| B | 3 | 50 | 16,666... |
| C | 4 | 65 | 16,25 |
| D | 5 | 70 | 14 |

Sức chứa `W=7`.

Một nghiệm là chọn B và C: trọng lượng `3+4=7`, giá trị `50+65=115`. Không có tập vật hợp lệ nào có giá trị lớn hơn, nên **đáp án tối ưu là 115**.

Một chiến lược tham lam lấy vật theo mật độ giá trị (`v/w`) từ cao xuống thấp sẽ lấy A rồi B, được trọng lượng 5, giá trị 90; không còn đủ chỗ lấy C hoặc D. Kết quả tham lam **90**, thấp hơn tối ưu 115.

**Bài học quan trọng:** sắp xếp theo `v/w` rất hữu ích để tính một **cận trên**, nhưng lựa chọn tham lam theo mật độ **không** giải chính xác ba lô 0/1 nói chung.

### 1.2. Những dạng bài gần giống nhưng không phải cùng bài

- **Ba lô phân số (*fractional knapsack*):** được lấy một phần vật; tham lam theo mật độ giải tối ưu khi trọng lượng dương và giá trị không âm.
- **Ba lô không giới hạn (*unbounded knapsack*):** lấy nhiều bản sao một loại; chuyển và cây quyết định khác.
- **Ba lô giới hạn số lượng (*bounded knapsack*):** mỗi loại có `k_i` bản sao; cần biểu diễn/giới hạn số lượng riêng.
- **Ba lô yêu cầu đúng W:** trạng thái không khả thi và điều kiện cơ sở khác. Bài này dùng **không vượt W**, có thể chọn tập rỗng với giá trị 0.
- **Ba lô nhiều tài nguyên:** mỗi vật có nhiều loại chi phí; một cận theo trọng lượng đơn lẻ có thể còn hợp lệ nhưng thường kém chặt.

## 2. Ý tưởng nhánh và cận: tìm có chứng minh, không chỉ đoán

**Nhánh (*branch*)** nghĩa là tách một trạng thái thành các trường hợp con. Trong ba lô 0/1, với vật tiếp theo chỉ có hai trường hợp:

1. **Lấy vật** nếu vẫn đủ sức chứa.
2. **Bỏ vật**.

**Cận (*bound*)** là một giới hạn đã được chứng minh về giá trị tốt nhất **có thể** đạt ở các nhánh con.

Với bài **cực đại**, dùng **cận trên** `UB(node)`: mọi lời giải hoàn chỉnh từ nút đó có giá trị không vượt `UB(node)`.

Ta duy trì **incumbent**: giá trị tốt nhất trong các **nghiệm khả thi đã biết**, gọi là `best`.

Khi:

`UB(node) <= best`

ta có thể **cắt toàn bộ nhánh**, vì ngay cả kết quả lý tưởng của nhánh cũng **không thể cải thiện** giá trị đang có.

Ba điều kiện quyết định tính đúng:

- `best` thực sự là giá trị của một nghiệm **khả thi**. Đây là **cận dưới** của optimum cực đại.
- `UB` thực sự là **cận trên** của mọi nghiệm mở rộng từ nút. Một ước lượng “có vẻ cao” nhưng đôi lúc thấp hơn giá trị khả thi là **không an toàn**.
- Các nhánh lấy/bỏ **bao phủ mọi tập vật**. Chỉ cắt do quá sức chứa hoặc do một cận trên hợp lệ.

### 2.1. Vì sao cắt không làm mất optimum?

Gọi `OPT(node)` là giá trị tối đa của mọi nghiệm hoàn chỉnh từ nút đó. Theo tính hợp lệ của bound:

`OPT(node) <= UB(node)`.

Nếu `UB(node) <= best`, suy ra:

`OPT(node) <= best`.

Vì `best` đã là giá trị của **một nghiệm hợp lệ**, không có nghiệm nào trong nhánh cắt tốt hơn incumbent. Cắt nhánh không thay đổi giá trị tối ưu được trả về.

Nếu nhiệm vụ là **liệt kê tất cả nghiệm tối ưu** hoặc mọi tập vật đạt cùng giá trị tốt nhất, cắt với `<=` có thể bỏ những nghiệm **bằng** incumbent; khi ấy phải thay chính sách duyệt/cắt phù hợp. Bài này chỉ cần **một nghiệm tối ưu và giá trị của nó**.

## 3. Cây trạng thái 0/1

Ta sắp một thứ tự các vật để xét, rồi đánh số theo thứ tự đó. Một trạng thái của cây tìm kiếm chứa:

- `index`: vị trí vật kế tiếp cần quyết định.
- `usedWeight`: tổng trọng lượng đã chọn.
- `currentValue`: tổng giá trị đã chọn.
- `selected`: những vật đã lấy ở các vị trí trước `index`.
- `best`: incumbent, thường được chia sẻ cho toàn bộ quá trình tìm kiếm.

Bất biến:

`0 <= index <= n`,  
`0 <= usedWeight <= W`,

và `currentValue` đúng bằng tổng giá trị những vật đã chọn từ **tiền tố `0..index-1`**.

Ở nút `(index,usedWeight,currentValue)`, gọi vật kế tiếp là i:

```text
                         (i, used, value)
                         /                \
          LẤY vật i nếu đủ chỗ           BỎ vật i
             /                              \
 (i+1, used+w_i, value+v_i)      (i+1, used, value)
```

Nếu `usedWeight + w_i > W` thì nhánh **lấy** không hợp lệ; chỉ còn nhánh **bỏ**. Trong code, tránh tính `usedWeight+w_i` trước khi kiểm tra tràn: với hai số không âm và `usedWeight<=W`, kiểm tra `w_i <= W-usedWeight` trước.

Khi `index==n`, mọi vật đã được quyết định: đây là một **lá** và `currentValue` là giá trị của một nghiệm khả thi.

### 3.1. Tập nghiệm được bảo toàn qua thứ tự sắp xếp

Đổi thứ tự các vật không làm thay đổi tập con của các **vật gốc** có thể chọn. Mỗi vật vẫn xuất hiện chính xác một lần trong cây và có hai quyết định lấy/bỏ.

Vì vậy ta có thể sắp vật theo mật độ `v/w` trước khi tìm kiếm để bound mạnh hơn, sau đó lưu **chỉ số gốc** để khôi phục danh sách vật đúng theo input.

### 3.2. DFS, BFS và Best-First

- **DFS B&B:** đi sâu vào một nhánh trước, thường lấy trước rồi bỏ. Dùng stack đệ quy, bộ nhớ nhỏ `O(n)` cho đường tìm kiếm.
- **BFS B&B:** khám phá theo độ sâu, có thể giữ rất nhiều nút trong queue.
- **Best-First B&B:** ưu tiên mở rộng nút có cận trên cao nhất, thường dùng **priority queue**. Có thể tìm nghiệm tốt sớm, nhưng frontier có thể rất lớn.

Cả ba đều chỉ đúng tối ưu nếu **bound hợp lệ** và không bỏ nhánh có thể cải thiện incumbent.

## 4. Vì sao ba lô phân số tạo được cận trên hợp lệ?

Ở một nút, các vật trước `index` đã được lấy hoặc bỏ, không được xét lại. Những vật từ `index` đến `n−1` còn chưa quyết định. Sức chứa còn lại:

`R = W - usedWeight`.

Bài toán con 0/1 cần chọn các vật còn lại, mỗi vật hoặc lấy hết hoặc bỏ. Ta **nới lỏng ràng buộc**:

`x_j ∈ {0,1}` trở thành `0 <= x_j <= 1`.

Nghĩa là cho phép lấy **một phần** của vật cuối. Tập phương án của bài nới lỏng **chứa tất cả** phương án 0/1 khả thi. Do đó:

`optimum_0/1_remainder <= optimum_fractional_remainder`.

Khi các vật còn lại có trọng lượng dương, giá trị không âm, bài phân số có thể tối ưu bằng cách lấy từ vật có **mật độ `v/w` cao nhất** trước.

Vì vậy một cận trên tại nút là:

`UB = currentValue + fractionalOptimum(remaining items, R)`.

**Lưu ý cực kỳ quan trọng:** cận trên là **giá trị bài phân số tối ưu**, không phải giá trị nghiệm tham lam **0/1** bỏ vật không vừa. Nếu ta chỉ nhặt các vật vừa nguyên vẹn, phần còn lại có thể cho một nghiệm tốt hơn, nên giá trị tham lam nguyên vẹn là **cận dưới** khả thi, không phải cận trên.

### 4.1. Công thức tính bound sau khi sắp theo mật độ

Sắp các vật còn lại theo `v_j/w_j` giảm dần. Đặt `remaining=R`, `bound=currentValue`.

Duyệt từng vật còn chưa quyết định:

1. Nếu vật j **vừa hoàn toàn**, cộng `v_j`, giảm `remaining` đi `w_j`.
2. Nếu vật j **không vừa** nhưng còn một ít sức chứa, cộng phần giá trị:

   `v_j · remaining / w_j`,

   sau đó dừng. Không được cộng tiếp giá trị của những vật khác khi dung lượng còn lại đã được dùng hết.
3. Nếu đã hết sức chứa, không còn phần thưởng bổ sung từ những vật còn lại.

Vì vật được sắp theo mật độ giảm, đây là **giá trị tối ưu của thư giãn phân số một chiều**.

### 4.2. Chứng minh tham lam tối ưu cho phiên bản phân số

Giả sử trong một lời giải phân số, ta lấy một phần vật có mật độ thấp B trong khi vật mật độ cao A vẫn còn chưa được lấy hết. Có thể chuyển một lượng trọng lượng rất nhỏ từ B sang A:

- Tổng trọng lượng không đổi.
- Giá trị tăng hoặc giữ nguyên vì mật độ A không thấp hơn B.

Lặp phép hoán đổi tới khi mọi vật mật độ cao được lấy hết trước vật thấp hơn. Kết quả có cấu trúc “một tiền tố vật lấy toàn bộ, tối đa một vật cuối lấy một phần”. Đây chính là cách tính greedy ở trên.

Lập luận phụ thuộc **trọng lượng dương, giá trị không âm và chỉ một giới hạn sức chứa**. Không được tự dùng cùng greedy nếu có hai giới hạn độc lập mà chưa chứng minh nới lỏng/cận tương ứng.

### 4.3. Sắp xếp theo tỉ lệ mà không dùng số thực

Để so sánh hai vật `a` và `b` có trọng lượng dương:

`v_a / w_a > v_b / w_b` tương đương `v_a·w_b > v_b·w_a`.

Nếu dùng `int` hoặc `long` nhân trực tiếp, tích có thể tràn. Các ví dụ Java sử dụng **`BigInteger`** để nhân chéo, sắp giảm theo mật độ và phá hòa theo **chỉ số input gốc**.

**Vì sao quan trọng?** Nếu sắp vật sai tỉ lệ, cách lấp đầy “vật tốt trước” có thể không còn là optimum của bài phân số. Khi dùng giá trị đó làm **cận trên**, ta có nguy cơ cắt mất nghiệm tối ưu. Sắp sai không chỉ làm chương trình chậm; nó có thể **làm mất tính đúng**.

## 5. Cận trên với số nguyên: dùng làm tròn lên an toàn

Giá trị vật trong bài học là **số nguyên không âm**. Khi lấy một phần vật, bound phân số có thể là số không nguyên.

Trong ví dụ W=7:

- Lấy nguyên A: trọng lượng 2, giá trị 40.
- Lấy nguyên B: thêm trọng lượng 3, giá trị 50.
- Còn chỗ 2, lấy một nửa vật C nặng 4, giá trị `65×2/4=32,5`.

Tổng bound phân số:

`UB_fractional = 40+50+32,5 = 122,5`.

Tối ưu 0/1 là số nguyên nên chắc chắn:

`OPT_0/1 <= 122,5` và do đó `OPT_0/1 <= floor(122,5) = 122`.

Ta có thể giữ cận trên **nguyên an toàn hơi lỏng** bằng cách lấy **ceiling**:

`UB_integer = ceil(UB_fractional) = 123`.

Ceiling lớn hơn hoặc bằng giá trị phân số thực, nên **không bao giờ thấp hơn optimum 0/1**. Có thể bớt cắt nhánh hơn dùng `floor` chính xác, nhưng an toàn và thuận tiện khi so với incumbent nguyên.

### 5.1. Vì sao không nên chuyển bound sang `double` rồi so sánh bừa?

`double` không biểu diễn chính xác mọi số nguyên lớn và phép chia phân số có thể làm tròn. Nếu quá trình tính cận bị **làm tròn xuống thấp hơn cận toán học**, điều kiện cắt `bound<=best` có nguy cơ **cắt sai**.

Để tránh phụ thuộc sai số làm tròn, các ví dụ thực hành dùng:

- `BigInteger` cho tổng giá trị và tích `v×remaining`.
- Phép chia nguyên `divideAndRemainder` để tính `ceil(v×remaining / w)` **chính xác**.
- So sánh `BigInteger.compareTo`, không dùng epsilon tùy ý.

Với kết quả cần là số nguyên, bound dạng ceiling vẫn hợp lệ. Dùng **ceiling**, không phải rounding-to-nearest, vì rounding-to-nearest có thể làm giảm cận.

### 5.2. Công thức ceiling chính xác

Với `numerator >= 0` và `denominator > 0`, viết:

```text
(q, r) = divideAndRemainder(numerator, denominator)
ceil(numerator / denominator) = q + (r == 0 ? 0 : 1)
```

Ta tránh cả sai số số thực lẫn tràn khi cộng kiểu số máy. Cần phân biệt trường hợp `remaining=0`: phần phân số bằng 0, không cần chia hay cộng.

### 5.3. Bound lỏng vẫn đúng

Nếu ta dùng `ceil(122,5)=123` dù cận chính xác có thể hạ về 122 vì optimum nguyên, thuật toán vẫn trả lời đúng; chỉ có thể duyệt **nhiều nút hơn**. Một cận **thấp hơn optimum thật** là lỗi nghiêm trọng; một cận **cao hơn cần thiết** chỉ ảnh hưởng hiệu năng.

## 6. Minh họa cây nhánh và cận với bốn vật

Vẫn xét A(2,40), B(3,50), C(4,65), D(5,70), W=7. Các vật đã ở thứ tự mật độ giảm.

### 6.1. Nút gốc

```text
index = 0
usedWeight = 0
currentValue = 0
remaining = 7

Fractional fill: A + B + 1/2 C
Fractional UB = 122,5
Integer ceiling bound = 123
```

Chúng ta mới biết `OPT<=123`, chưa biết optimum cụ thể.

### 6.2. Chọn nhánh lấy A trước

Lấy A:

```text
index = 1
usedWeight = 2
currentValue = 40
remaining = 5
```

Các vật chưa xét là B,C,D. Cận trên phần còn lại là B nguyên `50` cộng nửa C `32,5`, nên bound toàn nút vẫn bằng `122,5` (ceiling 123).

Đi tiếp lấy B:

```text
Đã lấy: A, B
usedWeight = 5
currentValue = 90
remaining = 2
```

Không thể lấy C nguyên vì `4>2`, cũng không thể lấy D nguyên vì `5>2`. Một lá khả thi có giá trị 90; `best=90`.

Các nhánh khác sau đó có thể tìm A+C (trọng lượng 6, giá trị 105) hoặc A+D (trọng lượng 7, giá trị 110), nâng incumbent.

### 6.3. Bỏ A: không mất lời giải tối ưu

Ở nhánh **bỏ A**, các vật còn B,C,D, sức chứa vẫn 7.

Lấy nguyên B và C:

`usedWeight=3+4=7`, `currentValue=50+65=115`.

Incumbent được cập nhật thành **115**, tốt hơn mọi nghiệm đi qua A đã tìm thấy.

Đây là lý do không được ép thuật toán luôn chọn vật mật độ cao nhất: nhánh **bỏ A** mới chứa optimum.

### 6.4. Tại sao cận cắt được nhánh?

Nếu một nhánh có `UB=110` trong khi `best=115`, thì mọi nghiệm từ nhánh có giá trị không quá 110, nên không thể thắng 115. Không cần đi sâu để xét từng tập vật trong nhánh đó.

**Không được cắt chỉ vì `currentValue<best`:** giá trị hiện tại còn có thể được cộng thêm từ các vật chưa xét. Phải so **upper bound của giá trị tối đa có thể đạt sau khi hoàn thiện**, không phải so giá trị hiện tại.

## 7. Pseudocode DFS Branch and Bound

Bản DFS đi theo đường sâu trước, ưu tiên thử **lấy vật** rồi mới **bỏ vật**:

```text
sort items by descending value/weight
best = 0
bestSelection = empty

dfs(index, usedWeight, currentValue, selected):
    if index == n:
        if currentValue > best:
            best = currentValue
            bestSelection = copy(selected)
        return

    ub = fractionalUpperBound(items[index..n-1],
                              W - usedWeight,
                              currentValue)
    if ub <= best:
        return  // Cắt an toàn

    item = items[index]

    // Nhánh lấy vật (nếu khả thi).
    if item.weight <= W - usedWeight:
        selected[index] = true
        dfs(index+1,
            usedWeight + item.weight,
            currentValue + item.value,
            selected)
        selected[index] = false

    // Nhánh bỏ vật.
    dfs(index+1, usedWeight, currentValue, selected)
```

Đây là **pseudocode** để thấy cấu trúc cây; Java 17 độc lập nằm ở phần 8.

Có thể đặt cập nhật `best` ngay tại nút **chưa hoàn chỉnh**: tập vật đã chọn tại nút đó đã là một tập **khả thi**; ta có thể hoàn tất bằng cách **bỏ tất cả vật còn lại**. Tuy nhiên, khi muốn minh họa cây và đếm số lá, bản DFS dưới đây chỉ cập nhật incumbent ở **lá**, giúp hành vi thống kê rõ ràng.

### 7.1. Bất biến trước và sau mỗi nhánh

- Trước khi gọi nhánh lấy, `selected[index]` có thể chưa được gán.
- Khi đi nhánh lấy, đánh dấu true và cộng trọng lượng/giá trị đúng một lần.
- Sau khi nhánh lấy trả về, đặt lại false để nhánh bỏ nhìn thấy **cùng trạng thái tiền tố** như trước khi thử lấy.
- Nhánh bỏ không thay đổi trọng lượng và giá trị.
- Sau khi cả hai nhánh xong, mọi tổ hợp từ tiền tố đã được xét hoặc đã bị loại vì một lý do an toàn.

Nếu quên hoàn tác `selected[index]`, danh sách truy vết có thể chứa vật **không thực sự được lấy**; nếu cộng trọng lượng hai lần, có thể làm sai tính khả thi.

## 8. Java 17 — DFS Branch and Bound chính xác, có truy vết

Đây là chương trình độc lập dùng `BigInteger` cho giá trị và cận. Trọng lượng và sức chứa dùng `long` **không âm**, nhưng phép cộng trọng lượng chỉ được thực hiện khi đã kiểm tra đủ chỗ bằng phép trừ `capacity-usedWeight`.

Lưu thành **KnapsackBranchAndBoundDfsDemo.java**:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class KnapsackBranchAndBoundDfsDemo {
    record Type(String id, long weight, long value) {}
    record Item(int originalIndex, String id, long weight, long value) {}
    record Result(
            BigInteger optimum,
            List<String> chosenIds,
            long chosenWeight,
            BigInteger rootUpperBound,
            long visited,
            long pruned,
            long leaves,
            long overweightSkips) {}

    static Item[] prepare(Type[] input) {
        Objects.requireNonNull(input, "input");
        Item[] items = new Item[input.length];

        for (int i = 0; i < input.length; i++) {
            Type t = Objects.requireNonNull(input[i], "item");
            Objects.requireNonNull(t.id(), "item ID");

            if (t.weight() <= 0 || t.value() < 0) {
                throw new IllegalArgumentException(
                        "Weights must be positive; values nonnegative");
            }
            items[i] = new Item(i, t.id(), t.weight(), t.value());
        }

        Arrays.sort(items, (a, b) -> {
            BigInteger left = BigInteger.valueOf(a.value())
                    .multiply(BigInteger.valueOf(b.weight()));
            BigInteger right = BigInteger.valueOf(b.value())
                    .multiply(BigInteger.valueOf(a.weight()));

            int byDensity = right.compareTo(left); // Giảm dần.
            return byDensity != 0 ? byDensity
                    : Integer.compare(a.originalIndex(), b.originalIndex());
        });
        return items;
    }

    static final class Solver {
        final long capacity;
        final Item[] items;
        final boolean[] selected;

        boolean[] bestSelected;
        BigInteger best = BigInteger.ZERO;

        long visited;
        long pruned;
        long leaves;
        long overweightSkips;

        Solver(Type[] input, long capacity) {
            if (capacity < 0) {
                throw new IllegalArgumentException("Negative capacity");
            }

            this.capacity = capacity;
            this.items = prepare(input);
            this.selected = new boolean[items.length];
            this.bestSelected = new boolean[items.length];
        }

        // Cận trên nguyên an toàn bằng ceiling của tối ưu phân số.
        BigInteger upperBound(int from, long usedWeight,
                              BigInteger currentValue) {
            long remaining = capacity - usedWeight;
            BigInteger upper = currentValue;

            for (int j = from; j < items.length; j++) {
                Item item = items[j];

                if (item.weight() <= remaining) {
                    upper = upper.add(BigInteger.valueOf(item.value()));
                    remaining -= item.weight();
                } else {
                    if (remaining > 0) {
                        BigInteger numerator = BigInteger.valueOf(
                                item.value()).multiply(
                                BigInteger.valueOf(remaining));

                        BigInteger[] div = numerator.divideAndRemainder(
                                BigInteger.valueOf(item.weight()));

                        upper = upper.add(div[0]);
                        if (div[1].signum() != 0) {
                            upper = upper.add(BigInteger.ONE);
                        }
                    }
                    break;
                }
            }
            return upper;
        }

        void dfs(int index, long usedWeight, BigInteger currentValue) {
            visited++;

            if (index == items.length) {
                leaves++;

                if (currentValue.compareTo(best) > 0) {
                    best = currentValue;
                    bestSelected = selected.clone();
                }
                return;
            }

            if (upperBound(index, usedWeight, currentValue)
                    .compareTo(best) <= 0) {
                pruned++;
                return;
            }

            Item item = items[index];

            // Thử LẤY trước; chỉ lấy khi không vượt capacity.
            if (item.weight() <= capacity - usedWeight) {
                selected[index] = true;
                dfs(index + 1,
                        usedWeight + item.weight(),
                        currentValue.add(
                                BigInteger.valueOf(item.value())));
                selected[index] = false;
            } else {
                overweightSkips++;
            }

            // Sau rollback, thử BỎ vật.
            dfs(index + 1, usedWeight, currentValue);
        }

        Result solve() {
            BigInteger initialBound =
                    upperBound(0, 0L, BigInteger.ZERO);

            dfs(0, 0L, BigInteger.ZERO);

            // Khôi phục theo thứ tự vật gốc, không theo tỉ lệ đã sort.
            List<Item> chosen = new ArrayList<>();
            long totalWeight = 0L;

            for (int i = 0; i < items.length; i++) {
                if (bestSelected[i]) {
                    chosen.add(items[i]);
                    totalWeight += items[i].weight();
                }
            }

            chosen.sort(Comparator.comparingInt(Item::originalIndex));
            List<String> ids = new ArrayList<>();
            for (Item item : chosen) {
                ids.add(item.id());
            }

            return new Result(best, List.copyOf(ids), totalWeight,
                    initialBound, visited, pruned, leaves,
                    overweightSkips);
        }
    }

    static Result solve(Type[] input, long capacity) {
        return new Solver(input, capacity).solve();
    }

    public static void main(String[] args) {
        Type[] items = {
            new Type("A", 2, 40),
            new Type("B", 3, 50),
            new Type("C", 4, 65),
            new Type("D", 5, 70)
        };

        Result answer = solve(items, 7);
        System.out.println("Root upper bound (ceil): "
                + answer.rootUpperBound());
        System.out.println("Optimum: " + answer.optimum());
        System.out.println("Chosen IDs: " + answer.chosenIds());
        System.out.println("Chosen weight: " + answer.chosenWeight());
        System.out.println("Visited: " + answer.visited()
                + ", pruned: " + answer.pruned()
                + ", leaves: " + answer.leaves());

        Type[] greedyTrap = {
            new Type("A", 6, 12),
            new Type("B", 5, 9),
            new Type("C", 5, 9)
        };

        System.out.println("Greedy trap optimum: "
                + solve(greedyTrap, 10).optimum());
        System.out.println("Zero capacity: "
                + solve(items, 0).optimum());
        System.out.println("No items: "
                + solve(new Type[0], 7).optimum());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 KnapsackBranchAndBoundDfsDemo.java
java KnapsackBranchAndBoundDfsDemo
```

Stdout:

```text
Root upper bound (ceil): 123
Optimum: 115
Chosen IDs: [B, C]
Chosen weight: 7
Visited: 17, pruned: 2, leaves: 5
Greedy trap optimum: 18
Zero capacity: 0
No items: 0
```

### 8.1. Những phần quan trọng trong mã

**Sắp xếp an toàn:** so sánh chéo tỉ lệ bằng `BigInteger`, không dùng `(double)value/weight` để quyết định thứ tự khi cần chứng minh bound chặt.

**Hai quyết định tại một nút:** nếu vật vừa thì đi nhánh lấy, sau đó nhánh bỏ; mỗi vật xuất hiện đúng một lần. `selected[index]=false` là bước hoàn tác.

**Cắt bound:** khi `upperBound<=best`, không cần mở rộng. `best=0` ban đầu tương ứng **tập rỗng khả thi**, kể cả khi không có vật hoặc sức chứa bằng 0.

**Truy vết:** `bestSelected` là snapshot khi thấy một lá tốt hơn. Sau khi tìm xong, sắp các vật đã chọn theo `originalIndex` để in danh sách theo input gốc.

**Cận nguyên an toàn:** đoạn `divideAndRemainder` tính chính xác phần trần khi có vật chỉ còn chỗ lấy phân số. Không dùng `double`, không tràn khi nhân chéo và nhân giá trị với dung lượng còn lại.

**Trọng lượng:** `weight<=capacity-usedWeight` được kiểm tra trước khi cộng. Do `usedWeight<=capacity` và `capacity` thuộc `long` không âm, phép cộng nếu được phép luôn không vượt `capacity` và không tràn dương.

### 8.2. Ý nghĩa các bộ đếm

- `visited`: số lần hàm `dfs` được gọi, tính cả lá hoặc nút bị cắt.
- `pruned`: số nút bị loại vì **cận trên không thể cải thiện incumbent**.
- `leaves`: số nút đã quyết định đủ `n` vật và được thăm.
- `overweightSkips`: số lần **nhánh lấy** không hợp lệ vì thiếu sức chứa; các lần này không tạo lời gọi `dfs`.

Trên ví dụ, bản include-first thăm 17 nút, cắt 2 nút bằng bound và đến 5 lá. Bộ đếm là **kết quả theo thứ tự duyệt và chính sách cắt cụ thể**, không phải hằng số cho mọi cài đặt B&B.

### 8.3. Các trường hợp đặc biệt đã được xử lý

- Không có vật: có một lời giải rỗng giá trị 0.
- `capacity=0`: với tất cả trọng lượng dương, nghiệm rỗng tối ưu.
- `value=0`: vật giá trị 0 không giúp cải thiện optimum trong bài có quyền bỏ; không ảnh hưởng tính đúng của bound.
- Hai vật cùng mật độ: phá hòa bằng vị trí gốc, kết quả tìm kiếm xác định.
- `BigInteger`: giá trị có thể vượt `long` khi cộng nhiều vật, nhưng **trọng lượng và số lượng nút** vẫn có giới hạn kiểu `long`/tài nguyên thực tế.

Nếu input chứa trọng lượng 0, mã sẽ **từ chối** thay vì chia cho 0 trong tính mật độ. Có thể thiết kế tiền xử lý vật zero-weight, nhưng phải làm nhất quán với ràng buộc và truy vết.

## 9. Chứng minh DFS Branch and Bound trả giá trị tối ưu

Ta chứng minh theo cây các quyết định.

### 9.1. Mỗi lá đại diện một tập vật 0/1

Mỗi tầng quyết định một vật khác nhau. Nhánh lấy đưa vật vào tập đúng một lần; nhánh bỏ không đưa vào. Vì vậy mọi đường đi từ gốc đến lá ứng với một vector chọn `x_i∈{0,1}`.

Với các nhánh lấy chỉ được đi khi đủ chỗ, mọi lá được thăm đều là **nghiệm khả thi**.

### 9.2. Mỗi tập vật khả thi có một đường đi tương ứng

Xét một tập vật S bất kỳ có tổng trọng lượng không quá W. Duyệt các vật theo thứ tự đã sắp:

- Nếu vật thuộc S, đi nhánh lấy.
- Nếu không thuộc S, đi nhánh bỏ.

Các tổng trọng lượng tiền tố của S không vượt W vì trọng lượng dương, nên mọi nhánh lấy theo S đều hợp lệ. Do đó nếu **không cắt**, thuật toán có thể đến lá của S.

### 9.3. Cắt không bỏ một nghiệm tốt hơn incumbent

Theo chứng minh ở phần 4, upper bound từ fractional relaxation không nhỏ hơn tối ưu 0/1 của mọi phần còn lại. Việc dùng `ceil` ở phần 5 chỉ làm bound **cao hơn hoặc bằng** giá trị thư giãn, nên vẫn an toàn.

Nếu cắt vì `upperBound<=best`, thì mọi lá thuộc nhánh này có giá trị không vượt `best`. Cắt như vậy không bỏ nghiệm cải thiện incumbent.

### 9.4. Kết luận

Mỗi lá được thăm cập nhật incumbent khi tốt hơn. Mỗi nhánh không thăm phải bị loại vì **quá sức chứa** hoặc vì **không thể thắng incumbent**. Nếu tồn tại nghiệm có giá trị lớn hơn giá trị cuối cùng `best`, đường đi tới nghiệm đó không thể bị cắt an toàn, mâu thuẫn với việc thuật toán đã duyệt hết các nhánh còn mở.

Vậy `best` là giá trị tối ưu và `bestSelected` ghi lại một tập vật khả thi đạt đúng `best`.

**Điểm cần phân biệt:** không có định lý nào nói “sort tỉ lệ rồi lấy nhánh cao trước sẽ luôn tìm optimum trước”. Tính đúng đến từ **cây xét đủ hai lựa chọn** và **cận hợp lệ**, không đến từ tham lam.

## 10. Best-First Branch and Bound: ưu tiên cận trên cao nhất

Bản DFS dùng stack và đi theo một nhánh sâu trước. Một cách khác là giữ tập nút chờ trong **priority queue**, luôn lấy nút có `upperBound` cao nhất để mở rộng.

Một nút best-first cần lưu:

- `level`: vị trí vật kế tiếp.
- `weight`: trọng lượng các vật đã chọn.
- `profit`: giá trị đã chọn.
- `upper`: cận trên của toàn bộ các cách hoàn thiện từ nút.
- `selected`: tập vật đã chọn tới thời điểm hiện tại (chẳng hạn `BitSet`).
- `sequence`: số thứ tự tạo nút để phá hòa ổn định.

**Quy tắc hàng đợi:** cận lớn hơn được ưu tiên; nếu bằng nhau có thể ưu tiên nút sâu hơn; nếu vẫn bằng nhau, ưu tiên nút được sinh sớm hơn.

### 10.1. Cập nhật incumbent ngay ở trạng thái chưa hoàn chỉnh

Một điểm quan trọng: trong bài ba lô **không vượt W**, mọi tập vật đã lấy tại một nút khả thi có thể trở thành **nghiệm hoàn chỉnh** bằng cách **bỏ tất cả vật chưa quyết định**. Vì vậy `profit` của một nút khả thi là một **cận dưới hợp lệ**, có thể cập nhật incumbent ngay tại lúc sinh nút.

Điều này không giống bài bắt buộc dùng **đúng W**, nơi một tiền tố có thể chưa phải nghiệm hoàn chỉnh được.

Cách cập nhật sớm thường giúp cắt thêm nút. Nhưng lúc đó bộ đếm “số lá được mở rộng” không còn phản ánh số nghiệm đã biết, vì một incumbent có thể được chốt từ **nút chưa đủ độ sâu n**.

### 10.2. Cắt cả khi đưa vào queue và khi lấy ra

Khi sinh nút:

1. Cập nhật incumbent nếu `profit` của nút tốt hơn.
2. Tính `upper`.
3. Chỉ đưa nút vào queue nếu `upper>incumbent`.

Khi lấy nút khỏi queue, incumbent có thể đã tăng nhờ nhánh khác sau lúc nút được đưa vào. Vì vậy **kiểm lại** `node.upper>incumbent` trước khi mở rộng.

Cận không cần thay đổi chỉ vì incumbent thay đổi; nhưng **quyết định có nên mở rộng nút** phải dựa trên incumbent mới nhất.

## 11. Java 17 — Best-First với PriorityQueue và BitSet

Lưu thành **KnapsackBestFirstBnBDemo.java**:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.BitSet;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class KnapsackBestFirstBnBDemo {
    record Type(String id, long weight, long value) {}
    record Item(int sourceIndex, String id, long weight, long value) {}

    record Node(
            int level,
            long weight,
            BigInteger profit,
            BigInteger upper,
            BitSet picked,
            long sequence) {}

    record Result(BigInteger optimum, List<String> ids,
                  long expanded, long generated, long pruned) {}

    static final class Solver {
        final long capacity;
        final Item[] items;
        final PriorityQueue<Node> queue;

        BigInteger best = BigInteger.ZERO;
        BitSet bestPicked = new BitSet();
        long generated;
        long expanded;
        long pruned;
        long sequence;

        Solver(Type[] input, long capacity) {
            Objects.requireNonNull(input, "input");
            if (capacity < 0) {
                throw new IllegalArgumentException("Negative capacity");
            }
            this.capacity = capacity;
            items = new Item[input.length];

            for (int i = 0; i < input.length; i++) {
                Type t = Objects.requireNonNull(input[i], "item");
                Objects.requireNonNull(t.id(), "item ID");
                if (t.weight() <= 0 || t.value() < 0) {
                    throw new IllegalArgumentException("Invalid item");
                }
                items[i] = new Item(i, t.id(), t.weight(), t.value());
            }

            Arrays.sort(items, (a, b) -> {
                BigInteger left = BigInteger.valueOf(a.value())
                        .multiply(BigInteger.valueOf(b.weight()));
                BigInteger right = BigInteger.valueOf(b.value())
                        .multiply(BigInteger.valueOf(a.weight()));

                int ratio = right.compareTo(left);
                return ratio != 0 ? ratio
                        : Integer.compare(a.sourceIndex(), b.sourceIndex());
            });

            Comparator<Node> priority = (a, b) -> {
                int byUpper = b.upper().compareTo(a.upper());
                if (byUpper != 0) {
                    return byUpper;
                }

                int byDepth = Integer.compare(b.level(), a.level());
                return byDepth != 0 ? byDepth
                        : Long.compare(a.sequence(), b.sequence());
            };
            queue = new PriorityQueue<>(priority);
        }

        BigInteger upperBound(int from, long usedWeight,
                              BigInteger current) {
            long remaining = capacity - usedWeight;
            BigInteger bound = current;

            for (int j = from; j < items.length; j++) {
                Item item = items[j];

                if (item.weight() <= remaining) {
                    bound = bound.add(BigInteger.valueOf(item.value()));
                    remaining -= item.weight();
                } else {
                    if (remaining > 0) {
                        BigInteger numerator = BigInteger.valueOf(
                                item.value()).multiply(
                                BigInteger.valueOf(remaining));
                        BigInteger[] parts = numerator.divideAndRemainder(
                                BigInteger.valueOf(item.weight()));

                        bound = bound.add(parts[0]);
                        if (parts[1].signum() != 0) {
                            bound = bound.add(BigInteger.ONE);
                        }
                    }
                    break;
                }
            }
            return bound;
        }

        void offer(int level, long weight, BigInteger profit,
                   BitSet picked) {
            generated++;

            // Tập vật đã lấy là nghiệm khả thi: bỏ hết vật còn lại.
            if (profit.compareTo(best) > 0) {
                best = profit;
                bestPicked = (BitSet) picked.clone();
            }

            BigInteger upper = upperBound(level, weight, profit);
            if (upper.compareTo(best) <= 0) {
                pruned++;
                return;
            }

            queue.add(new Node(level, weight, profit, upper,
                    (BitSet) picked.clone(), sequence++));
        }

        Result solve() {
            offer(0, 0L, BigInteger.ZERO, new BitSet());

            while (!queue.isEmpty()) {
                Node node = queue.poll();

                // Một incumbent tốt hơn có thể đã tìm thấy sau enqueue.
                if (node.upper().compareTo(best) <= 0) {
                    pruned++;
                    continue;
                }
                expanded++;

                if (node.level() == items.length) {
                    continue;
                }

                Item item = items[node.level()];

                if (item.weight() <= capacity - node.weight()) {
                    BitSet take = (BitSet) node.picked().clone();
                    take.set(node.level());
                    offer(node.level() + 1,
                            node.weight() + item.weight(),
                            node.profit().add(
                                    BigInteger.valueOf(item.value())),
                            take);
                }

                // Không chọn vật hiện tại.
                offer(node.level() + 1, node.weight(),
                        node.profit(), node.picked());
            }

            // Trả vật theo input gốc, không theo thứ tự density.
            List<Item> chosen = new ArrayList<>();
            for (int i = 0; i < items.length; i++) {
                if (bestPicked.get(i)) {
                    chosen.add(items[i]);
                }
            }
            chosen.sort(Comparator.comparingInt(Item::sourceIndex));

            List<String> ids = new ArrayList<>();
            for (Item item : chosen) {
                ids.add(item.id());
            }

            return new Result(best, List.copyOf(ids),
                    expanded, generated, pruned);
        }
    }

    static Result solve(Type[] items, long capacity) {
        return new Solver(items, capacity).solve();
    }

    public static void main(String[] args) {
        Type[] standard = {
            new Type("A", 2, 40),
            new Type("B", 3, 50),
            new Type("C", 4, 65),
            new Type("D", 5, 70)
        };

        Result r = solve(standard, 7);
        System.out.println("Best-first optimum: " + r.optimum());
        System.out.println("Chosen: " + r.ids());
        System.out.println("Expanded: " + r.expanded()
                + ", generated: " + r.generated()
                + ", pruned: " + r.pruned());

        Type[] greedyTrap = {
            new Type("A", 6, 12),
            new Type("B", 5, 9),
            new Type("C", 5, 9)
        };

        System.out.println("Greedy trap optimum: "
                + solve(greedyTrap, 10).optimum());
        System.out.println("Zero capacity: "
                + solve(standard, 0).optimum());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 KnapsackBestFirstBnBDemo.java
java KnapsackBestFirstBnBDemo
```

Stdout:

```text
Best-first optimum: 115
Chosen: [B, C]
Expanded: 8, generated: 14, pruned: 6
Greedy trap optimum: 18
Zero capacity: 0
```

### 11.1. Diễn giải số đo

- `generated`: số trạng thái được **đề xuất** qua `offer`, kể cả trạng thái bị cắt trước khi vào queue.
- `expanded`: số trạng thái thực sự được lấy ra và **mở rộng**.
- `pruned`: số trạng thái bị loại do `upper<=best`, tại lúc sinh hoặc lúc lấy ra khỏi queue.

Trong bài mẫu, best-first sinh 14 trạng thái, mở rộng 8 và cắt 6 theo chính sách cận. Chỉ số này không so trực tiếp với `visited` của DFS mà không xét cách mỗi bản định nghĩa bộ đếm và thời điểm cập nhật incumbent.

### 11.2. Vì sao phải clone BitSet?

Mỗi nút trong priority queue có thể tồn tại lâu hơn nhánh cha đã sinh nó. Nếu các nút cùng tham chiếu một `BitSet` rồi một nhánh sửa nó, những nút khác bị **thay đổi lịch sử lựa chọn**, làm truy vết sai.

Mỗi lần sinh node, code clone `picked`. Bản lấy vật clone và set vị trí tương ứng; bản bỏ dùng snapshot không có bit đó. `bestPicked` cũng được clone khi cập nhật incumbent.

### 11.3. Khi nào Best-First bất lợi?

Priority queue có thể giữ rất nhiều nút đang mở. Trong trường hợp xấu, số phần tử có thể tăng **theo hàm mũ**, đồng thời mỗi nút còn lưu `BitSet` và `BigInteger`.

DFS dùng **ít RAM hơn** vì có thể giữ một đường tìm kiếm và một số thông tin rollback. Best-first đổi bộ nhớ lấy khả năng ưu tiên những nút có bound tốt; không có bảo đảm luôn ít thời gian hơn DFS trên mọi input.

## 12. Phản ví dụ: tham lam theo tỉ lệ không phải thuật toán chính xác

Xét ba vật, sức chứa `W=10`:

| Vật | w | v | v/w |
|---|---:|---:|---:|
| A | 6 | 12 | 2 |
| B | 5 | 9 | 1,8 |
| C | 5 | 9 | 1,8 |

Tham lam theo mật độ:

- Lấy A nặng 6, giá trị 12.
- Còn chỗ 4, B và C đều nặng 5, không lấy được.
- Kết quả tham lam: **12**.

Nhưng chọn B+C:

- Tổng trọng lượng `5+5=10`.
- Tổng giá trị `9+9=18`.

Vậy tối ưu 0/1 là **18**. B&B phải có nhánh **bỏ A** để tìm B+C.

### 12.1. Bound gốc của ví dụ này

Bài phân số làm:

- Lấy A nguyên: 6 kg, lợi nhuận 12.
- Còn 4 kg, lấy `4/5` của B: giá trị `9×4/5=7,2`.

Cận trên phân số là:

`12+7,2 = 19,2`,

và cận nguyên an toàn bằng ceiling là **20**.

Do đó ở nút gốc:

`greedy feasible = 12 <= optimum_0/1 = 18 <= UB_integer = 20`.

**Phân biệt ba số:** 12 là giá trị của **một nghiệm khả thi**, 18 là **optimum thật**, 20 là **cận trên nới lỏng** dùng để cắt nhánh. Không được lấy 20 làm đáp án, vì nó có thể đòi lấy một phần vật.

## 13. Java 17 — đối chiếu greedy, DP và vét cạn

Chương trình này triển khai **ba cách độc lập** trên dữ liệu nhỏ:

- Greedy density để tạo một nghiệm khả thi, **không đảm bảo tối ưu**.
- DP 0/1 theo sức chứa để lấy optimum khi W vừa phải.
- Vét cạn lựa chọn lấy/bỏ để kiểm tra optimum với n nhỏ.

Nó không thực hiện nhánh và cận; mục đích là một **oracle đối chứng** cho kết quả của hai chương trình B&B.

Lưu thành **KnapsackGreedyDpBruteCompareDemo.java**:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;

public class KnapsackGreedyDpBruteCompareDemo {
    record Item(String id, int weight, long value) {}

    static void validate(Item[] items, int capacity) {
        Objects.requireNonNull(items, "items");
        if (capacity < 0 || capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid capacity");
        }
        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (item.weight() <= 0 || item.value() < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }
    }

    static Item[] densitySorted(Item[] input) {
        Item[] sorted = input.clone();
        Arrays.sort(sorted, (a, b) -> {
            BigInteger left = BigInteger.valueOf(a.value())
                    .multiply(BigInteger.valueOf(b.weight()));
            BigInteger right = BigInteger.valueOf(b.value())
                    .multiply(BigInteger.valueOf(a.weight()));
            return right.compareTo(left);
        });
        return sorted;
    }

    static long greedyFeasible(Item[] items, int capacity) {
        validate(items, capacity);
        long result = 0L;
        int remaining = capacity;

        for (Item item : densitySorted(items)) {
            if (item.weight() <= remaining) {
                result = Math.addExact(result, item.value());
                remaining -= item.weight();
            }
        }
        return result;
    }

    static long dpOptimum(Item[] items, int capacity) {
        validate(items, capacity);
        long[] dp = new long[capacity + 1];

        for (Item item : items) {
            // Duyệt GIẢM: mỗi vật chỉ chọn tối đa một lần.
            for (int c = capacity; c >= item.weight(); c--) {
                long take = Math.addExact(
                        dp[c - item.weight()], item.value());
                dp[c] = Math.max(dp[c], take);
            }
        }
        return dp[capacity];
    }

    static long bruteRecursive(Item[] items, int index,
                               int remaining) {
        if (index == items.length) {
            return 0L;
        }

        long skip = bruteRecursive(items, index + 1, remaining);
        long take = Long.MIN_VALUE;

        if (items[index].weight() <= remaining) {
            take = Math.addExact(items[index].value(),
                    bruteRecursive(items, index + 1,
                            remaining - items[index].weight()));
        }
        return Math.max(skip, take);
    }

    static long bruteOptimum(Item[] items, int capacity) {
        validate(items, capacity);
        return bruteRecursive(items, 0, capacity);
    }

    public static void main(String[] args) {
        Item[] items = {
            new Item("A", 6, 12),
            new Item("B", 5, 9),
            new Item("C", 5, 9)
        };
        System.out.println("Ratio greedy: "
                + greedyFeasible(items, 10));
        System.out.println("0/1 DP optimum: "
                + dpOptimum(items, 10));
        System.out.println("Brute-force optimum: "
                + bruteOptimum(items, 10));

        Item[] classic = {
            new Item("A", 2, 40),
            new Item("B", 3, 50),
            new Item("C", 4, 65),
            new Item("D", 5, 70)
        };
        System.out.println("Classic DP optimum: "
                + dpOptimum(classic, 7));
        System.out.println("Empty items: "
                + dpOptimum(new Item[0], 7));
        System.out.println("Zero capacity: "
                + dpOptimum(classic, 0));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 KnapsackGreedyDpBruteCompareDemo.java
java KnapsackGreedyDpBruteCompareDemo
```

Stdout:

```text
Ratio greedy: 12
0/1 DP optimum: 18
Brute-force optimum: 18
Classic DP optimum: 115
Empty items: 0
Zero capacity: 0
```

**Vì sao so sánh này có giá trị?** Trên input nhỏ, quy hoạch động và vét cạn dùng cách triển khai **khác** với fractional bound. Nếu hai B&B đều trả 18 và 115 như DP/vét cạn, đó là kiểm tra chéo tốt hơn chỉ so B&B với chính một công thức của nó. Không có bộ test hữu hạn nào thay thế được chứng minh cận hợp lệ ở phần 9.

### 13.1. Độ phức tạp các cách đối chứng

- **Greedy:** sắp xếp `O(n log n)` phép so sánh và duyệt O(n); cho nghiệm khả thi nhưng không đảm bảo tối ưu 0/1.
- **DP 0/1:** `O(n(W+1))` phép chuyển, `O(W+1)` bộ nhớ số `long`; **giả đa thức** theo W.
- **Vét cạn:** nhiều nhất `2^n` tập con, thời gian `O(2^n)` lần nhánh theo cách đệ quy, bộ nhớ stack `O(n)` khi chỉ lấy giá trị; với n lớn không khả thi.
- **B&B:** worst-case vẫn tăng theo `2^n`, nhưng có thể cắt rất nhiều nhánh khi bound chặt và incumbent tốt.

DP phù hợp khi W nhỏ/vừa. B&B có thể đáng cân nhắc khi W lớn khiến bảng `dp[W+1]` không khả thi nhưng n không quá lớn và bài có cấu trúc để cắt nhánh hiệu quả. Không có lựa chọn nào thắng trong mọi trường hợp.

## 14. DFS và Best-First: so sánh thực chất

| Tiêu chí | DFS Branch and Bound | Best-First Branch and Bound |
|---|---|---|
| Cấu trúc quản lý nút | Đệ quy / stack | Priority queue theo upper bound |
| Thứ tự mở rộng | Thường lấy trước rồi bỏ | Nút có bound cao hơn trước |
| Lưu những gì | Một đường lựa chọn + incumbent | Frontier nhiều nút, mỗi nút có selection |
| Bộ nhớ trong worst-case | `O(n)` cho path/stack, chưa tính input | Có thể `O(2^n)` nút |
| Cận trên cần đúng? | Có | Có |
| Có thể tìm nghiệm tốt sớm? | Có, tùy thứ tự nhánh | Có, tùy độ chặt của bound |
| Có thể dừng với optimum khi queue/cây đã cắt hết? | Có | Có |
| Hiệu năng thực tế | Phụ thuộc thứ tự và pruning | Phụ thuộc ưu tiên cận, chi phí queue và bộ nhớ |

Hai phiên bản Java cố ý có **thời điểm cập nhật incumbent khác nhau**: DFS cập nhật ở lá, best-first cập nhật ngay ở tiền tố khả thi. Do đó không nên kết luận best-first “nhanh hơn đúng bằng 17/8 lần” từ bộ đếm. Đó là hai phép đo **khác định nghĩa**, lại chưa tính overhead priority queue và BigInteger.

### 14.1. Kỹ thuật lai

Một hệ thống có thể:

1. Dùng một greedy feasible để tìm **incumbent ban đầu**.
2. Chạy DFS B&B để tiết kiệm RAM.
3. Sắp xếp vật theo mật độ để tính cận phân số.
4. Với mỗi nút, thử nhánh có triển vọng cao hơn trước (ví dụ tính bound hai con rồi chọn thứ tự).
5. Nếu không đủ thời gian, trả nghiệm tốt nhất đang có **kèm chứng chỉ khoảng cách** dựa trên bound của các nhánh chưa xử lý, thay vì khẳng định đã tối ưu.

Nếu thời gian kết thúc trước khi cây được chứng minh hết nhánh có thể cải thiện, phải nói **chưa chứng minh optimum**, dù đã có một nghiệm tốt.

## 15. Cận dưới, cận trên và khoảng cách tối ưu

Trong bài cực đại:

- **Lower bound của optimum:** giá trị `L` của một nghiệm khả thi (incumbent). Ta biết `L<=OPT`.
- **Upper bound của optimum:** một số `U` sao cho `OPT<=U`, có thể lấy max bound của những nút chưa xử lý và best hiện tại.

Khi đã có:

`L <= OPT <= U`,

ta biết khoảng chưa chắc chắn của nghiệm tối ưu.

Nếu `L=U` theo thang giá trị nguyên, nghiệm hiện có đã được chứng minh tối ưu.

### 15.1. Chứng chỉ dừng sớm

Giả sử `best=115`, nhưng queue còn một nút có bound 123. Ta **chưa** chứng minh optimum là 115 chỉ từ các số đó, dù dữ liệu mẫu có optimum thật là 115. Nút chưa xét **có thể** chứa nghiệm từ 116 đến 123 theo thông tin hiện tại.

Nếu tất cả nút chưa xử lý đều có `UB<=115`, thì không nút nào có thể cải thiện incumbent: **115 đã được chứng minh tối ưu**.

**Không được lẫn `UB(root)` với optimum trả về.** Cận root chỉ chứng minh khoảng có thể, không là một nghiệm 0/1.

### 15.2. Cận nhỏ hơn nghiệm hiện tại là dấu hiệu gì?

Nếu tính được `UB(node)<currentValue` với giá trị không âm và nghiệm tiền tố khả thi, rất có thể bound đã tính sai, vì ta luôn có thể hoàn tất bằng cách bỏ những vật chưa xét, đạt ít nhất `currentValue`.

Các code mẫu có bound bắt đầu bằng `currentValue` rồi chỉ cộng các giá trị không âm, nên không gặp bất thường này.

## 16. Có thể dùng những cận trên nào khác?

### 16.1. Cận tổng giá trị còn lại

Một bound rất đơn giản:

`UB_simple = currentValue + Σ_(j>=index) v_j`.

Vì bỏ hết ràng buộc sức chứa, đây chắc chắn là cận trên (với giá trị không âm). Nhưng thường **rất lỏng** vì cộng cả những vật chắc chắn không vừa.

Ưu điểm: có thể tính suffix-sum một lần, lấy bound trong `O(1)` cho mỗi nút. Nhược điểm: ít cắt nhánh.

### 16.2. Cận phân số (fractional relaxation)

Bound đã dùng:

`UB_fractional = currentValue + optimum_fractional(suffix, remainingCapacity)`.

Chặt hơn hoặc bằng bound tổng giá trị, vì vẫn tôn trọng sức chứa sau khi cho phép lấy phân số. Khi đã sort mật độ, có thể tính bằng quét từ `index`; ví dụ Java dùng `O(n-index)` cho mỗi lần tính cận.

Có thể tiền xử lý prefix-sum trọng lượng/giá trị và tìm điểm gãy bằng binary search trong vài tình huống, nhưng phải chứng minh đúng khi các vật trước đó đã bị quyết định và suffix có sự thay đổi theo node.

### 16.3. Cận bằng bài thư giãn mạnh hơn

Có thể giải một bài toán thư giãn khác, hoặc một DP nhỏ trên phần vật còn lại để lấy cận chặt hơn. Nhưng tính một bound quá đắt ở **mỗi nút** có thể làm B&B chậm hơn dù ít nút hơn.

Cần cân bằng:

`chi phí tính bound × số nút` so với `lượng nhánh bị cắt`.

### 16.4. Lower bound từ nghiệm tham lam

Lấy nguyên các vật vừa sức chứa theo thứ tự density cho một **nghiệm khả thi**, nên có thể cập nhật incumbent. Nhưng **không dùng** giá trị greedy làm `UB`.

Một heuristic tạo nghiệm tốt là công cụ **cận dưới**, còn một relaxation cho phép nhiều lựa chọn hơn bài gốc là công cụ **cận trên**.

## 17. Những lỗi khó khi sắp tỉ lệ và cận phân số

### 17.1. Dùng phép chia nguyên

Nếu sắp theo `value/weight` mà cả hai là `int`, Java làm phép chia nguyên, ví dụ `50/3=16` và `65/4=16`. Những vật có mật độ khác nhau có thể bị coi như bằng nhau và sắp sai; bound phân số greedy có nguy cơ không tối ưu.

**Sửa:** dùng phép nhân chéo với kiểu không tràn (như `BigInteger`) hoặc một so sánh số thực đã được phân tích chặt về an toàn.

### 17.2. Sắp theo giá trị tuyệt đối, không theo mật độ

Vật giá trị cao nhưng rất nặng không phải lúc nào tốt hơn vật giá trị thấp hơn nhưng nhẹ hơn khi chỉ còn một phần sức chứa. Fractional greedy **phải** xét `v/w`, không chỉ `v`.

### 17.3. Dùng greedy nguyên vật làm bound

Với ví dụ A(6,12), B(5,9), C(5,9), W=10, greedy nguyên vật cho 12 nhưng optimum 18. Nếu dùng `UB=12` rồi incumbent đạt 12, nhánh chứa B+C có thể bị cắt sai. **Sửa:** bound phải cho phép phần phân số hoặc một relaxation hợp lệ khác.

### 17.4. Nhân tỉ lệ bằng long bị tràn

Với giá trị/trọng lượng lớn, `v_a*w_b` có thể vượt `Long.MAX_VALUE` dù bản thân từng trường vẫn hợp lệ. Comparator có thể trả ngược kết quả, làm thứ tự mật độ sai. **Sửa:** `BigInteger` hoặc phép so sánh phân số chính xác không tràn.

### 17.5. Làm tròn cận xuống do `double`

Một bound dùng `double` rồi ép sang `long` có thể thấp hơn cận thật nếu có sai số. **Sửa:** tính cận bằng số nguyên chính xác (`BigInteger`) hoặc dùng quy trình làm tròn bảo thủ được chứng minh. Không dựa vào một epsilon tự chọn.

### 17.6. Cộng toàn bộ vật còn lại, sau đó cộng phân số thêm lần nữa

Cận phần phân số phải là **lấy các vật vừa**, rồi **tối đa một phần của vật đầu tiên không vừa**. Khi dung lượng hết, dừng. Nếu tiếp tục cộng lợi nhuận, bound chỉ lỏng hơn, nhưng không còn là optimum thư giãn; dễ gây hiểu nhầm trong phân tích.

### 17.7. Tính bound từ toàn bộ input ở mọi nút

Những vật **đã bị bỏ** không còn quyền xuất hiện trong nghiệm con. Nếu cứ cộng lại chúng khi tính bound, cận thường **quá lỏng** (dù có thể vẫn an toàn). Nếu lỡ trừ sai các vật đã lấy hoặc nhầm trọng lượng đã dùng, cận có thể **thấp hơn thực tế** và gây lỗi cắt.

**Sửa:** định nghĩa rõ `index`, suffix chưa quyết định, `currentWeight` và `currentValue`; chỉ thư giãn phần **còn được chọn**.

## 18. Các lỗi về state, incumbent và khôi phục

### 18.1. Cắt khi currentValue thấp

So `currentValue <= best` rồi cắt là sai: phần còn lại có thể thêm nhiều giá trị. Phải dùng **upper bound sau khi hoàn thiện**.

### 18.2. Cập nhật best từ phương án quá sức chứa

`best` chỉ được cập nhật từ **nghiệm khả thi**. Một phương án có giá trị rất cao nhưng tổng trọng lượng vượt W không phải cận dưới hợp lệ; nó có thể khiến thuật toán cắt hết nghiệm thật.

### 18.3. Cắt với `upper==best` khi cần tất cả nghiệm tối ưu

Nếu đề chỉ cần một nghiệm tối ưu, dấu `<=` đúng. Nếu muốn **mọi tập tối ưu**, có thể tồn tại nghiệm khác trong nhánh với `UB==best`; phải tránh cắt những nhánh này trước khi kiểm tra.

### 18.4. Quên hoàn tác picked

DFS dùng một mảng Boolean chia sẻ giữa các nhánh; nếu quên `picked[index]=false`, kết quả truy vết có thể chứa vật từ nhánh cũ.

### 18.5. Chia sẻ BitSet của nhiều nút queue

Best-first lưu nhiều trạng thái đồng thời; mỗi nút cần **snapshot độc lập**. Gán `picked` tham chiếu chung rồi sửa nó sẽ làm nhiễm trạng thái giữa các nhánh.

### 18.6. Gộp hai vật “bị áp đảo” một cách thiếu điều kiện

Trong ba lô 0/1, **không thể luôn xóa vật B chỉ vì tồn tại vật A nhẹ hơn và giá trị cao hơn**. Lý do: A cũng có thể đã được lấy, và lời giải tối ưu có thể cần **cả A lẫn B**.

Ví dụ:

```text
Capacity = 3
A: weight 1, value 5
B: weight 2, value 4

A nhẹ hơn và giá trị cao hơn B.
Nhưng nghiệm tối ưu lấy CẢ A+B → weight 3, value 9.
Nếu xóa B sẽ chỉ còn value 5.
```

Trong bài 0/1, luận điểm dominance phải xét đúng số bản sao và những vật đã chọn; quy tắc loại vật một-một như trên **không an toàn nói chung**.

### 18.7. Làm mất vị trí input khi sort

Nếu đề yêu cầu in tên/ID hoặc chỉ số vật gốc, phải giữ `originalIndex` trước khi sắp mật độ. Một vật đứng đầu sau sort không có nghĩa là vật số 0 trong input.

### 18.8. Quên kiểm tra miền kiểu số

`usedWeight+w_i` có thể tràn nếu thực hiện trước khi kiểm tra. `value` tích với `remaining` khi tính bound có thể tràn. Dùng `capacity-usedWeight` để kiểm tra vừa chỗ, và `BigInteger` cho các tích/tổng giá trị lớn.

### 18.9. Cho phép trọng lượng bằng 0 mà vẫn chia tỉ lệ

`v/0` không xác định. Nếu một vật 0/1 có trọng lượng 0, giá trị dương, ta có thể **chọn nó miễn phí** một lần (và cộng vào kết quả), nhưng ví dụ Java này **không hỗ trợ** trường hợp ấy; nó báo lỗi đầu vào để giữ điều kiện bound rõ ràng.

### 18.10. Nhầm thứ tự duyệt với tính đúng

Thử **lấy trước** hoặc **bỏ trước** đều có thể trả optimum nếu duyệt đủ nhánh và cắt an toàn. Thứ tự ảnh hưởng **số nút** và **thời điểm tìm nghiệm tốt**, không thay đổi bài toán toán học.

## 19. Độ phức tạp lý thuyết và bộ nhớ

### 19.1. Worst-case vẫn có thể hàm mũ

Với n vật, không có pruning thì cây nhị phân có tối đa:

`1 + 2 + 4 + ... + 2^n = 2^(n+1)-1` nút.

Ở mỗi nút, việc tính fractional bound bằng cách quét suffix dài tối đa n tốn `O(n)` phép toán cơ bản, nên thời gian chặn trên của bản minh họa:

`O(n·2^n + n log n)`

trong mô hình phép toán số học cố định, chưa tính chi phí bit của `BigInteger` và copy trạng thái khi cập nhật nghiệm.

Một số input cho pruning rất mạnh; một số khác hầu như không có cận loại được nút nào. B&B **không** biến ba lô 0/1 tổng quát thành thuật toán đa thức trong worst-case.

### 19.2. Bộ nhớ DFS

- Mảng vật, thứ tự sắp xếp và selected: `O(n)`.
- Stack đệ quy: tối đa `O(n)` mức.
- Snapshot nghiệm tốt: `O(n)`.
- Một số đối tượng `BigInteger` tạm cho tính bound: phụ thuộc độ dài bit giá trị và hoạt động GC.

Vì vậy bộ nhớ cấu trúc tìm kiếm **`O(n)`** nếu không giữ tất cả nút. Thực tế n rất lớn vẫn có thể gây `StackOverflowError` trên JVM do độ sâu đệ quy n.

### 19.3. Bộ nhớ Best-First

Priority queue có thể chứa số nút tăng **theo hàm mũ**, mỗi nút lưu `BitSet`, `BigInteger` và metadata. Tổng bộ nhớ có thể tới `O(n·2^n)` bit hoặc hơn theo cách biểu diễn đường chọn và cấu trúc hàng đợi; không thể hứa bộ nhớ tuyến tính như DFS.

Chi phí push/pop priority queue là `O(log Q)` với Q số nút trong queue, cộng chi phí bound và clone `BitSet`.

### 19.4. Khi nào DP thắng B&B?

Quy hoạch động 0/1:

`dp[c] = max(dp[c],dp[c-w_i]+v_i)` với c giảm,

có `O(nW)` thời gian và `O(W)` bộ nhớ cho trọng lượng/sức chứa nguyên và W đủ nhỏ.

Nếu n lớn nhưng W nhỏ, DP thường đáng tin cậy và có chi phí dễ dự đoán hơn B&B. Nếu W khổng lồ so với tài nguyên RAM, một bảng DP theo W có thể bất khả thi trong khi B&B vẫn thực hiện được trên n vừa phải — **nếu** cận cắt đủ mạnh.

Nên nhìn đồng thời **n, W, phân bố mật độ và giá trị, sức chứa tương quan với tổng trọng lượng, yêu cầu thời gian/RAM**, không chỉ tên thuật toán.

## 20. Các trường hợp biên và hợp đồng đầu vào

| Tình huống | Kết quả/cách xử lý phù hợp bài học |
|---|---|
| `n=0` | Tập rỗng, optimum `0` |
| `W=0`, mọi `w_i>0` | Không lấy gì, optimum `0` |
| Một vật có `w_i>W` | Không thể lấy; nhánh lấy bị loại |
| Một vật có `w_i==W` | Có thể lấy trọn vật |
| Tất cả `v_i=0` | Tập rỗng optimum `0`; bound 0 có thể cắt ngay |
| Hai vật có cùng mật độ | Sort phá hòa ổn định theo chỉ số gốc |
| Nhiều tập vật đồng tối ưu | Trả một tập; tie-break/cắt ảnh hưởng tập được chọn |
| `w_i=0, v_i>0` | Cần xử lý riêng; mã minh họa từ chối |
| `v_i<0` | Mã minh họa từ chối để bound giả định không âm; với quyền bỏ, vật âm thường không giúp cực đại |
| `W` rất lớn | DFS không tạo mảng `W+1`, nhưng vẫn có thể tốn thời gian hàm mũ |
| Giá trị vượt `long` khi cộng các vật | Code B&B dùng `BigInteger` cho tổng/bound |
| Trọng lượng hoặc capacity âm | Không phù hợp hợp đồng; từ chối |
| Yêu cầu dùng chính xác W | Không dùng nguyên chương trình; phải đổi định nghĩa khả thi và chiến lược incumbent |
| Muốn liệt kê tất cả tập tối ưu | Cần đổi điều kiện cắt/thu thập lời giải |

### 20.1. Các vật giá trị bằng 0 có làm sai bound không?

Không. Khi `v=0`, mật độ bằng 0 và được xếp ở cuối nếu các vật khác có giá trị dương. Fractional optimum có thể bỏ chúng; bound không cộng gì khi xét chúng. Trong bài không bắt buộc lấy vật, tập rỗng là nghiệm tối ưu khi mọi giá trị bằng 0.

### 20.2. Nếu tồn tại vật trọng lượng âm?

Trọng lượng âm không có nghĩa trong mô hình knapsack chuẩn, và phá lập luận giới hạn dung lượng cũng như greedy theo mật độ. Không cố “sửa” bằng cách lấy trị tuyệt đối; cần mô hình bài toán khác.

### 20.3. Với giá trị âm nhưng trọng lượng dương?

Trong bài cực đại với quyền không chọn, chọn một vật giá trị âm không có lợi nếu nó còn chiếm sức chứa. Có thể bỏ các vật đó trước khi giải trong biến thể chuẩn. Tuy nhiên, các phiên bản có yêu cầu **chọn đúng số vật**, **đúng trọng lượng** hoặc phụ thuộc giữa vật có thể cần xử lý khác; code chỉ nhận giá trị không âm.

## 21. Kiểm thử độc lập, không chỉ xem kết quả mẫu

### 21.1. Oracle vét cạn cho n nhỏ

Với n nhỏ (ví dụ `n<=20` để kiểm thử trên máy thông thường), liệt kê mọi mask từ 0 đến `2^n-1`:

```text
bestBrute = 0

for each mask:
    sumWeight = 0
    sumValue = 0

    for each item i:
        if bit i of mask is 1:
            sumWeight += w[i]
            sumValue += v[i]

    if sumWeight <= W:
        bestBrute = max(bestBrute, sumValue)
```

Đây là **pseudocode oracle**, không phải thuật toán B&B. Nó không dùng fractional bound, nên có thể phát hiện sai sót trong phần cận nếu B&B trả giá trị khác.

### 21.2. So sánh với DP 0/1

Với W vừa phải, dùng DP như chương trình ở phần 13 để đối chiếu optimum. DP theo dung lượng kiểm soát việc dùng mỗi vật một lần bằng **vòng c giảm**. Nó độc lập với việc sort tỉ lệ và tính fractional bound.

Khi cả B&B, DP và brute force cho cùng optimum trên nhiều test ngắn/ngẫu nhiên, đó là tín hiệu triển khai tốt, nhưng **không thay chứng minh bound hợp lệ**.

### 21.3. Kiểm tra tập vật truy vết

Ngoài giá trị optimum, phải xác minh:

1. Mỗi vật gốc xuất hiện **không quá một lần**.
2. Mọi chỉ số/tên vật trỏ tới đúng item đầu vào.
3. Tổng trọng lượng các vật đã chọn `<= W`.
4. Tổng giá trị các vật đã chọn bằng optimum trả về.
5. Với nhiều optimum, kết quả có thể khác nhau nhưng vẫn hợp lệ.

Đặc biệt với best-first, `BitSet` phải được clone để mỗi node lưu đúng lựa chọn riêng.

### 21.4. Bộ test trọng điểm

| Input | Optimum | Điều kiểm tra |
|---|---:|---|
| A `(2,40)`, B `(3,50)`, C `(4,65)`, D `(5,70)`, W=7 | **115** | B+C tối ưu, greedy ratio có thể sai |
| A `(6,12)`, B `(5,9)`, C `(5,9)`, W=10 | **18** | Bỏ vật mật độ cao đầu tiên có lợi |
| Một vật `(w=2,v=5)`, W=1 | **0** | Không thể lấy vật nặng hơn W |
| Một vật `(w=2,v=5)`, W=2 | **5** | Vừa đúng sức chứa |
| Hai vật `(w=1,v=5)`, `(w=2,v=4)`, W=3 | **9** | Không được xóa vật bị “áp đảo” vô điều kiện |
| Hai vật cùng mật độ `(1,2)` và `(2,4)`, W=3 | **6** | Tie-break vẫn cho đúng optimum |
| Ba vật giá trị 0, W dương | **0** | Tập rỗng đạt optimum |
| Không vật | **0** | Base case |
| W=0, mọi trọng lượng dương | **0** | Không truy cập chỉ số/mảng sai |
| W nhỏ, n nhiều | Đối chiếu DP | B&B có thể nhiều nhánh |
| Giá trị rất lớn | Đối chiếu BigInteger | Không tràn phép nhân/cộng bound |

### 21.5. Một kiểm tra bound mạnh hơn

Với một nút bất kỳ và n nhỏ, có thể vét cạn **chỉ các vật chưa quyết định** để tìm `trueBestCompletion`. Tính `UB(node)` rồi kiểm:

`UB(node) >= trueBestCompletion`.

Đây là kiểm thử trực tiếp tính **admissible** của bound, không chỉ là kiểm tra optimum cuối. Nên tạo trạng thái bao gồm cả những vật đã lấy và đã bỏ để tránh vô tình so bound với tập nghiệm sai.

Nếu tìm được một nút có `UB<trueBestCompletion`, cận **không an toàn** và có nguy cơ làm thuật toán trả giá trị sai — bất kể bộ test optimum trước đó đã PASS.

## 22. Bài tập tự luyện có đáp án

### Bài 1 — Nhận diện nhánh

Trong bài ba lô 0/1, tại nút sắp xét vật i có thể có mấy nhánh?

**Đáp án:** tối đa hai, **lấy** hoặc **bỏ**. Nhánh lấy chỉ tồn tại nếu thêm vật không vượt sức chứa.

### Bài 2 — Phân biệt bound và nghiệm

Ba vật có W=10, tham lam nguyên vật trả 12, fractional relaxation trả 19,2. Hai số nào có thể là cận dưới và cận trên của optimum?

**Đáp án:** 12 là một **cận dưới** vì đến từ nghiệm khả thi; 19,2 là **cận trên** vì bài phân số chứa mọi nghiệm 0/1. Nếu biểu diễn cận trên nguyên bằng ceiling, dùng 20.

### Bài 3 — Kiểm tra an toàn khi cắt

Một nhánh có UB=95, incumbent=100. Có được cắt?

**Đáp án:** có, miễn UB đã được chứng minh hợp lệ và incumbent là nghiệm khả thi, vì nhánh không thể thắng 100.

### Bài 4 — Không cắt theo giá trị hiện tại

Một nút mới đạt `currentValue=20`, incumbent=100 nhưng còn ba vật giá trị lớn. Có thể cắt chỉ vì 20 nhỏ hơn 100 không?

**Đáp án:** không. Phải tính bound của **giá trị có thể đạt sau khi hoàn thành**; nhánh có thể bổ sung hơn 80 giá trị.

### Bài 5 — Tính fractional bound

Với A(2,40), B(3,50), C(4,65), D(5,70), W=7 đã sort mật độ, hãy tính UB phân số nút gốc.

**Đáp án:** lấy A+B giá trị 90, còn 2/4 trọng lượng C cho giá trị 32,5. UB phân số `122,5`, ceiling nguyên an toàn `123`.

### Bài 6 — Nhánh chứa optimum

Vì sao B+C giá trị 115 không thể được tìm bằng một thuật toán luôn bắt buộc lấy A trước khi xét B,C?

**Đáp án:** B+C **không chứa A**, nên phải giữ nhánh bỏ A. Greedy theo mật độ không phải chứng minh optimum 0/1.

### Bài 7 — Tràn khi sort tỉ lệ

Hai vật có giá trị/trọng lượng lớn; `long` có thể tràn ở tích `v_a*w_b`. Có cách so sánh chính xác nào?

**Đáp án:** nhân chéo bằng `BigInteger` rồi so kết quả: `v_a*w_b` với `v_b*w_a`; khi trọng lượng dương, thứ tự tương đương mật độ.

### Bài 8 — Dùng ceiling thay floor

UB phân số là 122,5. Nếu dùng 123 làm cận thì có làm sai nghiệm không?

**Đáp án:** không. 123 **cao hơn** bound thật nên vẫn là cận trên hợp lệ, nhưng có thể làm thuật toán cắt ít hơn. Lấy floor 122 cũng là chặn nguyên hợp lệ khi lợi nhuận nghiệm 0/1 là số nguyên **và tính chính xác 122,5**, song code số thực làm tròn xuống thiếu kiểm soát có thể khiến bound hỏng.

### Bài 9 — Khôi phục vật gốc

Sau sort theo density, vật C chuyển sang vị trí thứ hai trong mảng. Nếu in chỉ số mảng đã sort, có thể sai gì?

**Đáp án:** vị trí đã sort không còn khớp chỉ số input. Phải lưu `originalIndex` hoặc ID và phục hồi theo nó.

### Bài 10 — Trường hợp capacity=0

Với tất cả `w_i>0`, W=0, optimum bằng bao nhiêu?

**Đáp án:** 0, tập rỗng. Root upper bound cũng bằng 0; B&B có thể cắt ngay mà vẫn trả nghiệm hợp lệ.

### Bài 11 — So DFS và Best-First

Hai phiên bản đều dùng fractional UB hợp lệ; bản nào luôn nhanh hơn?

**Đáp án:** không có bản nào luôn nhanh hơn. DFS thường tiết kiệm bộ nhớ, best-first có thể ưu tiên nút hứa hẹn nhưng giữ frontier lớn và tốn chi phí heap/clone.

### Bài 12 — B&B có đa thức không?

Vì nhiều nhánh bị cắt trên bài mẫu, có thể khẳng định B&B giải mọi ba lô 0/1 trong `O(n²)`?

**Đáp án:** không. Worst-case số nút vẫn có thể tăng gần `2^n`; với bound tính bằng quét suffix, thời gian chặn trên của code mẫu `O(n·2^n)` trong mô hình phép toán hằng số.

### Bài 13 — Vật bị áp đảo

A `(w=1,v=5)`, B `(w=2,v=4)`, W=3. Có thể xóa B vì A nhẹ hơn và lời nhiều hơn không?

**Đáp án:** không. Có thể lấy cả A+B, đạt 9; xóa B làm mất optimum. Đây là lỗi thường gặp khi áp dominance không đúng cho 0/1.

### Bài 14 — Tất cả nghiệm tối ưu

Đề yêu cầu liệt kê **mọi tập vật tối ưu**. Có thể cắt nhánh với `UB<=best` không?

**Đáp án:** không phải luôn. Khi `UB==best`, nhánh vẫn có thể chứa một tập khác cùng giá trị tối ưu. Cần cách cắt và thu thập nghiệm phù hợp mục tiêu liệt kê.

### Bài 15 — Bound của nút đã bỏ một vật

Ở một nhánh đã quyết định **bỏ A**, phép fractional fill có được lấy lại A không?

**Đáp án:** không. Bound của nhánh phải chỉ xét **những vật chưa quyết định**, vì quyết định bỏ A đã cố định. Cộng A vào chỉ làm cận lỏng, nhưng nếu nhầm cả các giá trị/trọng lượng đã cố định có thể gây lỗi.

### Bài 16 — Khi nào kết luận optimum?

Một cây B&B đã có incumbent=115. Cần điều kiện gì trên tất cả nhánh chưa xử lý để kết luận chắc chắn 115 tối ưu?

**Đáp án:** mọi nhánh chưa xử lý đều có bound `<=115`, hoặc đã được chứng minh vô nghiệm/không khả thi. Khi không còn nhánh có thể cải thiện, 115 đã được chứng minh tối ưu.

## 23. Checklist trước khi nộp lời giải B&B cho ba lô 0/1

1. **Bài đúng là 0/1 hay unbounded/bounded?** Mỗi vật xuất hiện đúng một lần trong cây?
2. **Mục tiêu là cực đại tổng giá trị với trọng lượng không vượt W?** Nếu exact-fill hoặc nhiều tài nguyên, cần đổi điều kiện.
3. **Đã viết rõ trạng thái?** `index`, `usedWeight`, `currentValue`, `selected`, incumbent.
4. **Nhánh lấy và bỏ đã bao phủ mọi khả năng?** Chỉ cắt nhánh lấy khi không đủ sức chứa.
5. **Bound có phải cận trên được chứng minh không?** Thư giãn sang fractional knapsack là hợp lệ trong điều kiện đề?
6. **Sắp mật độ có chính xác không?** Tránh integer division và tràn tích khi comparator.
7. **Nếu bound có phân số, phép làm tròn có an toàn không?** Ceiling chính xác bằng số nguyên lớn nếu cần.
8. **Bound xét đúng suffix chưa quyết định chưa?** Không vô tình chọn lại vật đã bị bỏ.
9. **Incumbent có đến từ nghiệm khả thi không?** Không dùng nghiệm quá W làm `best`.
10. **Điều kiện cắt có hợp mục tiêu không?** `UB<=best` cho một nghiệm tối ưu; cân nhắc khác nếu liệt kê mọi optimum.
11. **Khi làm DFS đã hoàn tác chính xác chưa?** Đặc biệt mảng `selected`.
12. **Khi làm best-first đã clone state của từng node chưa?** Không dùng chung `BitSet` có thể sửa.
13. **Khôi phục tập vật theo chỉ số input gốc chưa?** Sort chỉ là kỹ thuật duyệt.
14. **Đã tính worst-case hàm mũ chưa?** Đừng chỉ nhìn tốc độ trên một ví dụ.
15. **RAM có đủ cho frontier Best-First không?** Priority queue có thể rất lớn.
16. **Đã kiểm tra đầu vào rỗng, W=0, vật quá nặng, giá trị 0, nhiều nghiệm hòa chưa?**
17. **Đã kiểm tra tràn trọng lượng và giá trị chưa?** Dùng `capacity-usedWeight` và kiểu số đủ lớn.
18. **Đã so với DP và brute force trên test nhỏ chưa?** Kiểm cả tính khả thi của vật truy vết.
19. **Đã thử phản ví dụ tham lam chưa?** Chọn vật mật độ cao đầu tiên không luôn tối ưu.
20. **Nếu cần dừng sớm do thời gian, có báo nghiệm hiện tại và bound còn lại thay vì khẳng định tối ưu không?**

**Ghi nhớ:** Nhánh và cận cho ba lô 0/1 **không** đồng nghĩa “lấy vật có `v/w` cao nhất”. Tại mỗi nút, thuật toán xét **lấy/bỏ**, duy trì một nghiệm khả thi tốt nhất `best`, và tính **cận trên** bằng cách thư giãn phần vật chưa quyết định thành **ba lô phân số**. Nếu `UB<=best`, nhánh không thể cải thiện và được cắt an toàn. DFS thường tiết kiệm bộ nhớ; Best-First ưu tiên cận lớn nhưng có thể tốn frontier. **Tính đúng nằm ở chứng minh cận trên và việc xét đủ những nhánh chưa được cắt**, còn hiệu năng phụ thuộc độ chặt của bound, thứ tự thử nhánh và cấu trúc dữ liệu.
