# Xây dựng cận bằng nới lỏng ràng buộc

**Nhánh và cận (branch and bound, B&B)** là phương pháp tìm lời giải tối ưu bằng cách chia không gian nghiệm thành các bài toán con (**branch**) và loại bỏ những bài toán con chắc chắn không thể cải thiện lời giải tốt nhất đã biết (**bound**). Bước then chốt là xây dựng một **cận hợp lệ**: một con số có chứng minh rằng mọi nghiệm khả thi trong nhánh đều không thể vượt qua (với bài toán **tối đa hóa**), hoặc không thể thấp hơn (với bài toán **tối thiểu hóa**).

**Nới lỏng ràng buộc (constraint relaxation)** là cách tạo cận phổ biến: thay bài toán con khó bằng một bài toán **dễ hơn**, cho phép thêm những nghiệm mà bài gốc không chấp nhận. Không gian nghiệm mở rộng giúp cực trị của bài nới lỏng nằm về phía **lạc quan** so với cực trị của bài gốc. Chẳng hạn với ba lô 0/1, cho phép lấy **một phần của món hàng** biến bài toán khó thành **fractional knapsack**, giải được bằng tham lam theo tỷ lệ giá trị/trọng lượng và cung cấp **cận trên** cho giá trị tối ưu của mọi lựa chọn nguyên.

Bài thuộc chủ đề **Nhánh và cận**. Nội dung bao gồm định nghĩa cận trên/cận dưới, điều kiện an toàn khi cắt nhánh, cách suy ra cận từ nới lỏng, công thức phân số của 0/1 knapsack, ưu nhược điểm của cận mạnh/yếu, cách xử lý làm tròn chính xác, chiến lược nhánh, biến thể cho bài toán cực tiểu và những ràng buộc cần giữ lại. Bài có chương trình **Java 17+ chạy độc lập**, kết quả chuẩn và gợi ý kiểm thử đối chiếu bằng vét cạn.

**Mục tiêu học tập:** phát biểu được vì sao nới lỏng cho cận hợp lệ; phân biệt **incumbent** (nghiệm thực sự khả thi) với **relaxation bound** (giá trị có thể không đạt được); xây dựng cận theo từng nút, không chỉ cho gốc; dùng điều kiện cắt nhánh đúng chiều; chứng minh tính đúng và hiểu vì sao thời gian xấu nhất vẫn có thể là hàm mũ.

## 1. Bài toán gốc, bài toán con và nghiệm tốt nhất đã biết

Giả sử bài toán tối đa hóa có tập nghiệm khả thi F và hàm mục tiêu `v(s)`. Giá trị tối ưu là:

**`OPT = max_{s∈F} v(s)`.**

Trong nhánh và cận, một nút N đại diện cho tập nghiệm con `F(N) ⊆ F` sau khi đã cố định một số quyết định. Ví dụ, trong 0/1 knapsack ta có thể cố định vài món đã chọn hoặc đã bỏ; những món còn lại chưa quyết định.

Ta thường duy trì:

- **Nghiệm đang tốt nhất (incumbent):** một nghiệm **thực sự khả thi** với giá trị B. Vì đang tối đa hóa, **`B≤OPT`**.
- **Cận trên của nút `U(N)`:** số thỏa **`OPT(N)≤U(N)`**, trong đó `OPT(N)` là giá trị tối ưu của các nghiệm trong nhánh N.
- **Quy tắc cắt nhánh:** nếu **`U(N)≤B`** thì không nghiệm nào trong N có thể **cải thiện** giá trị tốt nhất B. Có thể bỏ toàn bộ N nếu mục tiêu chỉ là **giá trị tối ưu** hoặc **một nghiệm tối ưu**.

Ở bài toán **tối thiểu hóa**, các dấu đổi chiều: incumbent B là một nghiệm khả thi nên `B≥OPT`; một **cận dưới `L(N)≤OPT(N)`** cho phép cắt khi **`L(N)≥B`**.

| Loại mục tiêu | Incumbent khả thi B | Cận do nới lỏng | Điều kiện cắt khi chỉ cần một nghiệm tối ưu |
|---|---|---|---|
| **Tối đa hóa** | B là **cận dưới** của OPT | **Cận trên** U(N) | `U(N)≤B` |
| **Tối thiểu hóa** | B là **cận trên** của OPT | **Cận dưới** L(N) | `L(N)≥B` |

Không được nhầm một **giá trị tham lam nhưng khả thi** với cận trên của bài tối đa hóa: nghiệm tham lam có thể thấp hơn tối ưu nên chỉ cung cấp **cận dưới**. Ngược lại, giá trị tối ưu của bài nới lỏng có thể cao hơn bất kỳ nghiệm nguyên nào và không nhất thiết là một phương án hợp lệ để xuất ra.

### Một nhánh được hiểu như thế nào?

Với n món trong ba lô, tại nút đang xét k món đầu theo một thứ tự đã chọn:

- Những món “lấy” góp một trọng lượng và giá trị đã biết.
- Những món “bỏ” không thể xuất hiện trở lại trong nhánh.
- Các món từ k trở đi là quyết định còn mở.
- Một nhánh vi phạm sức chứa lập tức vô nghiệm và không cần mở rộng.
- Một cận phải được tính **trên đúng tập món còn lại**, không được vô tình cho phép lấy lại món đã bỏ hoặc dùng lại món đã lấy.

Điều cuối rất quan trọng: cận phải là cận của **bài toán con đang xét**, không phải một công thức lạc quan không liên quan tới các quyết định đã cố định. Một cận “quá cao” vẫn có thể an toàn nhưng cắt yếu; một cận “quá thấp” có thể **cắt mất nghiệm tối ưu**.

## 2. Nguyên lý nới lỏng ràng buộc

Với nút N của bài tối đa hóa, giả sử bài gốc có tập nghiệm khả thi `F(N)`. Ta xây một bài nới lỏng có tập khả thi `R(N)` sao cho:

**`F(N) ⊆ R(N)`.**

Khi dùng **cùng hàm mục tiêu** trên hai tập:

**`max_{s∈F(N)} v(s) ≤ max_{s∈R(N)} v(s) = U_relax(N)`.**

Vậy `U_relax(N)` là một **cận trên hợp lệ** cho bài tối đa hóa. Chúng ta được phép giải bài **dễ hơn** vì cực trị của nó không thể thấp hơn cực trị của bài gốc.

Với bài **tối thiểu hóa**, quan hệ đảo chiều:

**`min_{s∈R(N)} v(s) ≤ min_{s∈F(N)} v(s)`.**

Lúc này giá trị nới lỏng là **cận dưới**, không phải cận trên.

### “Nới lỏng” nghĩa là mở rộng tập nghiệm

Các ví dụ phổ biến:

- Thay điều kiện biến quyết định `x_i∈{0,1}` bằng `0≤x_i≤1` (nới lỏng **tính nguyên**).
- Bỏ một số ràng buộc xung đột, liên thông hoặc thứ tự, khiến nhiều cấu hình trước đó bị cấm trở nên được phép.
- Thay bài toán tổ hợp bằng một **quy hoạch tuyến tính (LP relaxation)** chứa tất cả nghiệm nguyên hợp lệ như những điểm đặc biệt.
- Nới lỏng một ràng buộc khó bằng **phạt Lagrange**, từ đó suy ra cận với dấu phù hợp.

Bài nới lỏng không nhất thiết có một nghiệm tương ứng với một lời giải hợp lệ của bài gốc. Nó chỉ cần dễ giải và thỏa quan hệ bao hàm/cận được chứng minh.

**Lưu ý:** tự ý **thêm ràng buộc mới** làm tập khả thi nhỏ lại thì không còn là nới lỏng kiểu trên; với bài tối đa hóa, cực trị mới có thể **thấp hơn** tối ưu của nút, khiến cận trên sai. Một số phương pháp cận khác không dựa trực tiếp vào bao hàm tập khả thi nhưng cũng phải có chứng minh riêng.

## 3. Độ mạnh và chi phí tính cận

Một cận tốt có hai đặc điểm:

1. **Hợp lệ (admissible):** không cắt bỏ bất kỳ nhánh nào có thể cải thiện incumbent.
2. **Đủ chặt:** gần tối ưu của bài toán con, giúp `U(N)≤B` hoặc `L(N)≥B` xuất hiện sớm.

Ví dụ bài tối đa hóa có `OPT(N)=11` và incumbent `B=11`:

- Cận trên 50 hợp lệ nhưng **không cắt được** nhánh.
- Cận trên 12 hợp lệ nhưng vẫn **không cắt được**.
- Cận trên 11 hợp lệ và **cắt được**.
- Cận trên 10 là **không hợp lệ** nếu đúng là `OPT(N)=11`; cắt bằng nó có thể mất nghiệm tối ưu.

Một cận chặt hơn có thể tốn thời gian hoặc RAM hơn để tính. Tổng thời gian B&B phụ thuộc **số nút mở rộng × chi phí tính cận**, chứ không chỉ số nút bị cắt. Không phải lúc nào giải một LP rất lớn tại mỗi nút cũng nhanh hơn dùng cận đơn giản.

Nếu có hai **cận trên hợp lệ** U₁ và U₂ cho cùng một nút của bài tối đa hóa, thì:

**`min(U₁,U₂)` vẫn là cận trên hợp lệ**, đồng thời không yếu hơn từng cận. Tương tự với tối thiểu hóa, **`max(L₁,L₂)`** của các cận dưới hợp lệ vẫn là cận dưới hợp lệ. Tuy nhiên phải tính thêm chi phí để lấy những cận ấy.

## 4. Ví dụ chính: bài toán ba lô 0/1

Cho n món. Món i có:

- Trọng lượng nguyên **dương** `w_i>0`.
- Giá trị nguyên **không âm** `v_i≥0`.

Ba lô có sức chứa nguyên `W≥0`. Mỗi món được chọn **tối đa một lần**, biến quyết định `x_i∈{0,1}`.

Bài toán là:

**Tối đa hóa `Σ v_i x_i`**, với:

- `Σ w_i x_i ≤ W`;
- `x_i∈{0,1}`.

Nếu số món vừa phải, có thể thử mọi tập con trong O(2ⁿ) nhánh. Nhánh và cận vẫn có thể phải xét số mũ trong trường hợp xấu, nhưng cố gắng **cắt sớm** nhờ cận trên của các nút.

### Nới lỏng thành fractional knapsack

Giữ ràng buộc sức chứa nhưng thay:

**`x_i∈{0,1}` thành `0≤x_i≤1`.**

Nói cách khác, bài nới lỏng cho phép **lấy một phần của một món**. Mọi cách chọn 0/1 vẫn hợp lệ khi cho phép lấy phân số, nên:

**`OPT_0/1 ≤ OPT_fractional`**.

Bài fractional knapsack có giá trị/trọng lượng không âm, trọng lượng dương, và nghiệm tối ưu đạt được khi **ưu tiên tỷ lệ `ρ_i=v_i/w_i` lớn hơn trước**, lấy trọn từng món khi còn sức chứa, cuối cùng có thể lấy **một phần của món kế tiếp**. Các món có v=0 không làm tăng cận và không gây khó khăn cho tính đúng.

Đây là bước nới lỏng quan trọng: bài 0/1 khó hơn vì không được lấy một phần món, còn bài fractional có quy tắc tham lam tối ưu nhờ lý lẽ **hoán đổi** (nếu một nghiệm fractional còn dùng phần của món tỷ lệ thấp trong khi món tỷ lệ cao chưa lấy hết, chuyển một lượng trọng lượng nhỏ sang món tỷ lệ cao sẽ không làm giảm giá trị).

## 5. Xây cận fractional tại một nút

Giả sử đã sắp các món theo **tỷ lệ giá trị/trọng lượng giảm dần**. Ở một nút:

- `pos` là vị trí món tiếp theo **chưa quyết định**.
- `usedWeight` là tổng trọng lượng của các món đã chọn trong nhánh.
- `currentValue` là tổng giá trị đã chọn.
- `remaining = W−usedWeight≥0` là sức chứa còn lại.

Ta **giữ nguyên những quyết định đã cố định**, chỉ cho phép lấy phân số đối với các món trong đoạn `pos..n−1`.

Để tính cận trên:

1. Bắt đầu `U=currentValue`, `space=remaining`.
2. Duyệt các món chưa quyết định theo tỷ lệ `v_i/w_i` giảm dần.
3. Nếu `w_i≤space`, cho phép lấy trọn món, cộng `v_i` vào U và trừ `w_i` khỏi space.
4. Nếu `w_i>space>0`, cho phép lấy phần `space/w_i` của món, cộng **`space·v_i/w_i`** vào U rồi dừng.
5. Nếu đã hết sức chứa hoặc hết món, dừng.

Giá trị thu được là **tối ưu của bài fractional suffix** cộng với giá trị prefix đã chọn. Vì mọi nghiệm 0/1 của nhánh là nghiệm của bài fractional này, U là cận trên của nhánh.

### Truy vết một phép tính cận

Ba món theo tỷ lệ giảm:

| Chỉ số | Trọng lượng | Giá trị | Tỷ lệ `v/w` |
|---:|---:|---:|---:|
| 0 | 2 | 5 | 2,5 |
| 1 | 3 | 6 | 2,0 |
| 2 | 4 | 7 | 1,75 |

Sức chứa **W=5**.

Tại **gốc**, chưa chọn/bỏ gì: lấy trọn món 0 (w=2,v=5), rồi món 1 (w=3,v=6); tổng giá trị fractional **11**. Vì đây cũng là nghiệm 0/1 hợp lệ, tối ưu nguyên thật sự là **11**.

Giả sử đã chọn món 0 nhưng **bỏ món 1**. Còn room=3 và chỉ còn món 2 (w=4,v=7). Bài nới lỏng cho lấy `3/4` món 2, cộng `7·3/4=5,25`. Tổng cận thực là **`5+5,25=10,25`**, thấp hơn incumbent 11, nên nhánh này chắc chắn không cải thiện.

Nếu **bỏ món 0**, những món còn lại là 1 và 2: lấy trọn món 1 được 6, còn room=2, lấy một nửa món 2 được 3,5; cận là **`9,5`**. Nhánh này cũng không thể đạt giá trị 11.

Nhờ cận của **từng nút**, sau khi tìm nghiệm giá trị 11, ta có thể loại những nhánh còn lại mà không cần liệt kê mọi tập con.

## 6. Làm tròn cận: đúng chiều mới an toàn

Giá trị fractional có thể không nguyên, còn mục tiêu 0/1 knapsack ở bài này là **tổng các giá trị nguyên**. Nếu cận fractional thực là F, ta biết:

`OPT_integer ≤ F`.

Vì `OPT_integer` là số nguyên, suy ra cận nguyên **chặt hơn nhưng vẫn an toàn**:

**`OPT_integer ≤ floor(F)`**.

Ví dụ `F=10,25` ⇒ nghiệm nguyên không thể có giá trị lớn hơn **10**. Do đó có thể dùng **floor(F)** làm cận trên nguyên. Nếu dùng ceil(F)=11 thì vẫn là cận trên hợp lệ nhưng **yếu hơn**, có thể bỏ lỡ cơ hội cắt nhánh.

**Điều kiện then chốt:** F phải được tính **chính xác** hoặc bảo đảm **không bị đánh giá thấp**. Lấy `floor` của một kết quả `double` đã sai số âm có thể biến cận hợp lệ thành cận **quá thấp**, đặc biệt gần số nguyên hoặc khi giá trị rất lớn.

### Tính cận nguyên chính xác trong Java

Với `currentValue` nguyên, các món lấy trọn có tổng nguyên, chỉ có tối đa một món fractional. Nếu còn `space` và món tiếp theo có giá trị v, trọng lượng w, ta cộng:

**`floor(space·v/w)`**.

Dùng `BigInteger` để nhân và chia nguyên chính xác:

~~~java
// Đoạn mã minh họa, đặt trong một phương thức Java phù hợp.
BigInteger part = BigInteger.valueOf(space)
        .multiply(BigInteger.valueOf(value))
        .divide(BigInteger.valueOf(weight));
upper = upper.add(part);
~~~

Vì space,v≥0 và weight>0, phép chia nguyên của BigInteger đúng bằng floor của phân số. Không có làm tròn xuống do sai số số thực. Tổng các phần nguyên và phần fractional **được lấy floor đúng** vì tất cả món trọn vẹn đóng góp số nguyên.

Với giá trị hoặc mục tiêu **không nguyên**, không được tùy tiện áp dụng phép floor này. Cần dùng cận trong kiểu số/độ chính xác phù hợp và làm tròn ra **phía an toàn**.

### Sắp thứ tự tỷ lệ cũng cần chính xác

So sánh hai món a và b bằng:

`v_a/w_a > v_b/w_b`

khi `w_a,w_b>0`, tương đương:

**`v_a·w_b > v_b·w_a`**.

Nhưng tích có thể tràn long nếu số lớn, nên mã Java dùng BigInteger để **nhân chéo chính xác** trong comparator. Không nên sắp bằng `double(v)/w` khi độ chính xác là một phần của chứng minh cận; thứ tự sai có thể làm greedy fractional **không đạt optimum của bài nới lỏng**, khiến giá trị tính được không còn là cận trên an toàn.

## 7. Duy trì incumbent và điều kiện cắt nhánh

Giả sử đã có một tập món khả thi với giá trị B. Ban đầu tập rỗng là nghiệm hợp lệ vì `w_i>0`, `v_i≥0` và W≥0, nên có thể đặt **`B=0`**. Mỗi khi tìm được nghiệm tốt hơn, cập nhật B và lưu tập món tương ứng.

Tại nút N:

- Nếu `usedWeight>W`, nhánh **vô nghiệm**; không mở rộng.
- Tính `U(N)` từ fractional relaxation của các món còn lại.
- Nếu **`U(N)≤B`**, bỏ N vì không thể cải thiện best.
- Nếu không, chọn một món còn lại và tạo hai nhánh: **lấy** (nếu vừa sức) hoặc **bỏ**.
- Khi tất cả món đã được quyết định, nếu giá trị hơn B thì cập nhật incumbent.

Một cấu trúc DFS:

~~~text
search(pos, usedWeight, currentValue):
    if pos == n:
        if currentValue > best:
            best = currentValue
            save chosen set
        return

    upper = fractionalUpperBound(pos, usedWeight, currentValue)
    if upper <= best:
        return  // Không thể cải thiện incumbent hiện tại.

    item = sortedItems[pos]

    if usedWeight + item.weight <= capacity:
        mark item as taken
        search(pos+1, usedWeight+item.weight,
               currentValue+item.value)
        unmark item

    search(pos+1, usedWeight, currentValue) // Bỏ món.
~~~

**Vì sao xét nhánh lấy trước?** Sau khi sắp các món theo mật độ giá trị, thử lấy trước thường tìm được nghiệm tốt sớm, làm incumbent B tăng và giúp cắt mạnh hơn. Đây chỉ là **heuristic thứ tự duyệt**, không cần thiết cho tính đúng; đôi khi thứ tự khác hiệu quả hơn.

### Cắt khi bằng nhau có an toàn không?

Nếu chỉ cần **giá trị tối ưu** hoặc **một nghiệm tối ưu**, cắt khi `U≤B` là đúng: một nhánh chỉ có thể đạt **bằng B** thì không cải thiện. Nhưng nếu đề yêu cầu **liệt kê mọi nghiệm tối ưu** hoặc đếm số nghiệm tối ưu, cắt bằng nhau có thể bỏ mất những nghiệm bằng B. Khi ấy cần thay đổi quy tắc và dữ liệu theo đúng mục tiêu đầu ra.

**Không bao giờ dùng cận trên làm incumbent.** Incumbent phải có tập lựa chọn khả thi tương ứng. Một nghiệm fractional lấy `0,75` món không được dùng để khẳng định đã có nghiệm 0/1 giá trị fractional ấy.

## 8. Phản ví dụ: tham lam nguyên không phải cận trên

Xét hai món và sức chứa W=3:

| Món | Trọng lượng | Giá trị | Tỷ lệ |
|---|---:|---:|---:|
| 0 | 2 | 4 | 2 |
| 1 | 3 | 5 | 5/3 |

Tham lam **nguyên** theo tỷ lệ lấy món 0 trước, còn sức chứa 1 không đủ cho món 1, thu giá trị **4**. Đây là **nghiệm khả thi**, nhưng không tối ưu: bỏ món 0 và lấy món 1 được **5**.

Vì thế:

- **Greedy nguyên = 4** là **cận dưới** cho bài tối đa hóa.
- **Fractional relaxation** lấy trọn món 0 (giá trị 4), rồi lấy `1/3` món 1 (giá trị `5/3`), đạt **`F=17/3≈5,666…`**.
- Cận nguyên an toàn là **`floor(F)=5`**.
- Tối ưu 0/1 thật bằng **5**.

Nếu dùng “giá trị greedy 4” làm **cận trên** và incumbent đã bằng 4, thuật toán có thể cắt cả nút gốc, **bỏ qua nghiệm 5**. Đây là lỗi sai tư duy giữa “một lời giải đang có” và “một giới hạn không thể vượt qua”.

## 9. Chứng minh cắt nhánh bằng nới lỏng không mất tối ưu

Giả sử ở mỗi nút N, hàm bound trả cận trên hợp lệ:

**`OPT(N)≤U(N)`**.

Và incumbent B luôn là giá trị của một nghiệm **thực sự khả thi** đã tìm được. Nếu `U(N)≤B` thì:

**`OPT(N)≤U(N)≤B`**.

Do vậy không có nghiệm nào trong N có giá trị **lớn hơn** B. Bỏ N không thể làm mất một giá trị tối ưu tốt hơn B.

Nếu không cắt, chia nhánh lấy/bỏ món tiếp theo tạo hai tập nghiệm **không giao nhau** và bao phủ tất cả nghiệm của nút. Nhánh lấy được kiểm tra ràng buộc trọng lượng, nhánh bỏ không làm tăng trọng lượng. Cuối cùng mọi nghiệm khả thi hoặc được xét ở một lá, hoặc nằm trong nhánh đã chứng minh không thể cải thiện incumbent.

Khi duyệt xong, B bằng giá trị tối ưu. Cùng với việc lưu tập món khả thi ở thời điểm cập nhật B, ta nhận **một nghiệm tối ưu**.

### Chứng minh bound fractional hợp lệ

Tại một nút, các món đã chọn trong prefix đóng góp currentValue và dùng usedWeight. Mọi nghiệm còn lại của nhánh có một vector 0/1 cho các món suffix, với tổng trọng lượng không vượt `W−usedWeight`. Vector ấy cũng thỏa bài fractional suffix với `0≤x_i≤1`. Vì fractional tối ưu tối đa trên một tập lớn hơn, nó không nhỏ hơn giá trị của mọi nghiệm 0/1 trong suffix. Cộng currentValue rồi lấy floor chính xác vì mục tiêu nguyên giữ được quan hệ:

**`OPT_integer(N)≤floor(OPT_fractional(N))=U(N)`**.

Điều này vẫn đúng với những món có giá trị 0, với sức chứa còn lại 0, và khi không còn món nào. Nếu còn capacity nhưng không có món vừa, fractional có thể lấy một phần món nặng; cận vẫn hợp lệ, dù không thể chuyển phần đó thành nghiệm 0/1.

## 10. Cách làm cận mạnh hơn hoặc rẻ hơn

### 10.1. Bỏ toàn bộ ràng buộc sức chứa còn lại

Một cận rất đơn giản cho bài max với giá trị không âm:

**`U_simple=currentValue+Σ_{i≥pos}v_i`**.

Nó cho phép “lấy hết các món còn lại” dù vượt sức chứa. Đây là một nới lỏng hợp lệ, luôn ≥ giá trị của mọi lựa chọn 0/1 khả thi, nhưng thường quá lạc quan nên cắt rất yếu. Chi phí tính có thể O(1) mỗi nút nếu tiền tính mảng tổng suffix.

### 10.2. Fractional knapsack

Giữ giới hạn sức chứa nhưng nới lỏng tính nguyên nên chặt hơn `U_simple` hoặc ít nhất không yếu hơn nó. Sau khi sắp theo tỷ lệ, tính cận bằng quét suffix có thể mất **O(n)** cho mỗi nút. Với nhiều nút, chi phí tính bound có thể đáng kể; có thể tiền tính tổng trọng lượng/giá trị và dùng tìm kiếm để tính nhanh hơn trong một số cấu trúc, nhưng phải giữ đúng điều kiện các quyết định đã cố định.

### 10.3. Cận từ một bài toán con dễ hơn nhưng gần bài gốc

Tùy bài toán, có thể nới lỏng chỉ một số ràng buộc xung đột để giữ lại các hạn chế quan trọng khác. Nếu tập khả thi của relaxation càng gần bài gốc, cận thường càng chặt; đổi lại bài relaxation có thể khó giải hơn.

Không có quy tắc “nới lỏng nhiều nhất là tốt nhất”. Bỏ càng nhiều hạn chế thì tập khả thi thường càng lớn và **cận trên của bài max càng cao, tức càng yếu**. Lựa chọn tốt phụ thuộc thời gian giải relaxation so với số nhánh nó cắt được.

### 10.4. Cận Lagrange (ý tưởng)

Với bài max knapsack và số nhân `λ≥0`, từ ràng buộc `Σw_i x_i≤C` có thể suy ra:

`Σv_i x_i ≤ λC + Σ(v_i−λw_i)x_i`.

Nếu tạm bỏ ràng buộc sức chứa và chỉ giữ `0≤x_i≤1`, ta có cận:

**`U(λ)=λC+Σ max(0,v_i−λw_i)`**.

Khi các món prefix đã cố định, phải cộng **giá trị prefix** và dùng **sức chứa còn lại**/món suffix trong biểu thức. Chọn λ hợp lý có thể tạo cận hữu ích; tối ưu λ có thể cho cận chặt hơn một giá trị λ tùy tiện. Đây là một ví dụ *nới lỏng/đưa ràng buộc vào mục tiêu bằng hệ số phạt*, không phải công thức cho phép cập nhật incumbent.

Nếu λ được lưu ở kiểu số thực, phải quản lý sai số theo hướng an toàn. Mã Java ở phần dưới **không dùng λ** mà dùng fractional bound chính xác để rõ ràng hơn.

## 11. Quy trình thiết kế cận cho những bài toán khác

Có thể áp dụng khung sau:

1. **Định nghĩa bài toán con:** quyết định nào đã cố định? Những biến nào chưa? Ràng buộc nào đã được tiêu thụ?
2. **Chọn hướng tối ưu:** max cần upper bound để loại nhánh; min cần lower bound.
3. **Chọn một relaxation có tập nghiệm bao bài toán con:** nới lỏng một ràng buộc khó nhưng **giữ được toàn bộ nghiệm hợp lệ của nhánh**.
4. **Giải relaxation hoặc tìm một cận được chứng minh trên giá trị relaxation:** giải đúng tối ưu relaxation là cách rõ ràng nhất. Nếu dùng ước lượng thay vì giải đúng, phải chứng minh ước lượng nằm **đúng phía lạc quan**.
5. **Thử trên bài nhỏ:** so bound của từng nút với tối ưu thật bằng vét cạn; mọi cận bị vi phạm là lỗi nghiêm trọng.
6. **Đánh giá chi phí:** số node, số lần gọi bound, chi phí mỗi bound và lượng RAM.
7. **Kết hợp incumbent khả thi:** dùng heuristic để tìm nghiệm tốt sớm, giúp cắt nhiều hơn.
8. **Chứng minh đầy đủ:** ràng buộc nới lỏng không làm rớt nghiệm gốc, và các nhánh lấy/bỏ bao phủ toàn bộ không gian.

### Ví dụ với bài toán tối thiểu hóa

Trong **Traveling Salesperson Problem (TSP)** tối thiểu hóa, có thể nới lỏng điều kiện “mọi đỉnh thuộc đúng một chu trình Hamilton” thành một **bài gán/assignment** cho phép nhiều chu trình con tách rời (kèm điều kiện vào/ra thích hợp). Tập tour hợp lệ là một phần của tập nghiệm assignment nên:

**`OPT_assignment ≤ OPT_TSP`**.

Giá trị bài gán là **cận dưới** cho TSP, không phải cận trên. Nếu đã có một tour hợp lệ chi phí B, nhánh có **lower bound ≥ B** có thể cắt khi chỉ cần một tour tối ưu. Ở đây “nới lỏng ràng buộc loại trừ subtour” làm bài toán dễ hơn và cực tiểu **thấp hơn hoặc bằng** chi phí tour thật.

Trong các bài khác, một **minimum spanning tree**, bài toán luồng, bài toán matching hoặc một LP có thể cung cấp cận, nhưng phải kiểm tra chi tiết quan hệ tập nghiệm và mô hình chi phí: tên thuật toán quen thuộc **không tự động chứng minh** cận hợp lệ cho mọi biến thể.

## 12. Java 17+ hoàn chỉnh: nhánh và cận 0/1 knapsack

Chương trình dưới đây dùng:

- `int[] weights`: trọng lượng **dương**.
- `long[] values`: giá trị **không âm**.
- `capacity` không âm.
- Sắp item theo mật độ giá trị/trọng lượng **giảm dần**, so sánh bằng BigInteger nhân chéo để không sai thứ tự do làm tròn/tràn.
- `fractionalUpperBound` tính cận nguyên **floor của cực trị fractional** hoàn toàn bằng BigInteger, không dùng double.
- `search` thử nhánh **lấy** trước (nếu vừa sức), sau đó nhánh **bỏ**, và cắt khi cận không hơn incumbent.
- `chosen` và `bestChosen` được đánh chỉ số theo **chỉ số gốc của món**, dù khi tìm kiếm danh sách đã được sắp theo tỷ lệ.
- `Result` trả giá trị, tổng trọng lượng và **một** tập chỉ số món tăng dần.

Để giữ tổng giá trị không tràn long trong mọi nghiệm, chương trình kiểm tra **tổng giá trị của tất cả món** bằng `Math.addExact` ngay đầu vào; nếu quá long, từ chối. Vì mọi v≥0, mọi giá trị tổng của một tập con nằm trong long khi tổng tất cả món vừa long. Các phép so sánh phân số và nhân chéo vẫn dùng BigInteger vì một tích trung gian có thể vượt long.

**Hợp đồng:** chương trình giải đúng khi dữ liệu hợp lệ và hoàn tất việc duyệt; **không có bảo đảm thời gian đa thức**. Với n lớn, số nhánh có thể quá nhiều và đệ quy có thể gây áp lực stack. Đây là mã học thuật minh họa bound an toàn, không phải solver công nghiệp cho mọi quy mô.

Lưu tệp **`RelaxationBoundDemo.java`**:

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class RelaxationBoundDemo {
    private record Item(int originalIndex, int weight, long value) {}

    public record Result(
            long bestValue, int totalWeight, List<Integer> items) {}

    private final int capacity;
    private final Item[] sortedItems;
    private final boolean[] chosen;
    private final boolean[] bestChosen;
    private long bestValue;

    private RelaxationBoundDemo(
            int[] weights, long[] values, int capacity) {
        if (weights == null || values == null
                || weights.length != values.length
                || capacity < 0) {
            throw new IllegalArgumentException("Invalid knapsack input");
        }

        this.capacity = capacity;
        this.sortedItems = new Item[weights.length];
        this.chosen = new boolean[weights.length];
        this.bestChosen = new boolean[weights.length];
        this.bestValue = 0L; // Tập rỗng luôn là nghiệm khả thi.

        long totalValue = 0L;
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                        "Weights positive, values nonnegative");
            }
            try {
                totalValue = Math.addExact(totalValue, values[i]);
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException(
                        "Total item value overflows long", ex);
            }
            sortedItems[i] = new Item(i, weights[i], values[i]);
        }

        // So sánh v_a/w_a và v_b/w_b bằng nhân chéo chính xác.
        Arrays.sort(sortedItems, (a, b) -> {
            BigInteger avBw = BigInteger.valueOf(a.value())
                    .multiply(BigInteger.valueOf(b.weight()));
            BigInteger bvAw = BigInteger.valueOf(b.value())
                    .multiply(BigInteger.valueOf(a.weight()));
            int cmp = bvAw.compareTo(avBw); // Tỷ lệ giảm dần.
            return cmp != 0
                    ? cmp
                    : Integer.compare(a.originalIndex(), b.originalIndex());
        });
    }

    // Cận trên NGUYÊN: floor(tối ưu fractional suffix).
    private BigInteger fractionalUpperBound(
            int pos, int usedWeight, long currentValue) {
        long space = (long) capacity - usedWeight;
        BigInteger bound = BigInteger.valueOf(currentValue);

        for (int i = pos; i < sortedItems.length && space > 0; i++) {
            Item item = sortedItems[i];
            if (item.weight() <= space) {
                space -= item.weight();
                bound = bound.add(BigInteger.valueOf(item.value()));
            } else {
                // Chỉ lấy một phần của món đầu tiên không vừa.
                BigInteger part = BigInteger.valueOf(space)
                        .multiply(BigInteger.valueOf(item.value()))
                        .divide(BigInteger.valueOf(item.weight()));
                bound = bound.add(part);
                break;
            }
        }
        return bound;
    }

    private void search(int pos, int usedWeight, long currentValue) {
        if (pos == sortedItems.length) {
            if (currentValue > bestValue) {
                bestValue = currentValue;
                System.arraycopy(
                        chosen, 0, bestChosen, 0, chosen.length);
            }
            return;
        }

        if (fractionalUpperBound(pos, usedWeight, currentValue)
                .compareTo(BigInteger.valueOf(bestValue)) <= 0) {
            return; // Không thể cải thiện nghiệm đang tốt nhất.
        }

        Item item = sortedItems[pos];

        // Nhánh lấy món, chỉ xét nếu còn đủ sức chứa.
        if (item.weight() <= capacity - usedWeight) {
            chosen[item.originalIndex()] = true;
            search(
                    pos + 1,
                    usedWeight + item.weight(),
                    currentValue + item.value());
            chosen[item.originalIndex()] = false;
        }

        // Nhánh không lấy món.
        search(pos + 1, usedWeight, currentValue);
    }

    public static Result solve(
            int[] weights, long[] values, int capacity) {
        RelaxationBoundDemo solver =
                new RelaxationBoundDemo(weights, values, capacity);
        solver.search(0, 0, 0L);

        List<Integer> indices = new ArrayList<>();
        int weight = 0;
        for (int i = 0; i < solver.bestChosen.length; i++) {
            if (solver.bestChosen[i]) {
                indices.add(i);
                weight += weights[i];
            }
        }
        return new Result(
                solver.bestValue, weight, List.copyOf(indices));
    }

    private static void show(
            String name, int[] weights, long[] values, int capacity) {
        Result result = solve(weights, values, capacity);
        System.out.printf(
                "%s: best=%d, weight=%d, items=%s%n",
                name, result.bestValue(),
                result.totalWeight(), result.items());
    }

    public static void main(String[] args) {
        show("Small optimum",
                new int[] {2, 3, 4},
                new long[] {5, 6, 7}, 5);

        show("Four items",
                new int[] {2, 3, 4, 5},
                new long[] {3, 4, 5, 8}, 8);

        show("Greedy trap",
                new int[] {2, 3},
                new long[] {4, 5}, 3);

        show("Tie",
                new int[] {1, 1},
                new long[] {5, 5}, 1);

        show("No items",
                new int[0], new long[0], 10);

        show("Zero capacity",
                new int[] {1, 2},
                new long[] {6, 7}, 0);

        show("Too heavy",
                new int[] {6, 7},
                new long[] {10, 11}, 5);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac RelaxationBoundDemo.java
java RelaxationBoundDemo
~~~

**Kết quả đầu ra chuẩn:**

~~~text
Small optimum: best=11, weight=5, items=[0, 1]
Four items: best=12, weight=8, items=[1, 3]
Greedy trap: best=5, weight=3, items=[1]
Tie: best=5, weight=1, items=[0]
No items: best=0, weight=0, items=[]
Zero capacity: best=0, weight=0, items=[]
Too heavy: best=0, weight=0, items=[]
~~~

### Giải thích từng trường hợp

**Small optimum:** với ba món (2,5),(3,6),(4,7), W=5, chọn món 0 và 1 đạt giá trị 11; những nhánh còn lại có upper bound nhỏ hơn hoặc bằng 11 nên bị cắt.

**Four items:** các món có trọng lượng [2,3,4,5], giá trị [3,4,5,8], W=8. Chọn món 1 và 3 có trọng lượng 3+5=8, giá trị 4+8=12. Một số tập khác như món 0 và 3 chỉ đạt 11.

**Greedy trap:** tham lam nguyên theo mật độ có thể chỉ chọn món 0 (giá trị 4), nhưng optimum là món 1 (giá trị 5). Fractional bound cho phép giữ nhánh còn cơ hội cải thiện.

**Tie:** hai món cùng trọng lượng và giá trị, W=1. Comparator phá hòa theo chỉ số gốc tăng, DFS thử lấy trước, cập nhật incumbent chỉ khi `currentValue>bestValue`. Nghiệm đầu tiên giá trị 5 chọn món 0, các nhánh chỉ hòa bị cắt, nên kết quả là [0].

**No items:** tập rỗng là nghiệm duy nhất, giá trị 0, danh sách rỗng.

**Zero capacity:** mọi món có trọng lượng dương, không món nào chọn được, giá trị 0.

**Too heavy:** mỗi món nặng hơn sức chứa, dù bài fractional có thể lấy một phần để tạo cận dương, không có nghiệm nguyên lấy món, nên kết quả 0. Đây là ví dụ rõ ràng rằng **cận fractional không phải nghiệm khả thi**.

## 13. Tại sao mã không dùng double cho cận?

Trong một lời giải B&B, sai số nhỏ ở cận có thể gây hậu quả lớn hơn sai số một kết quả trung gian: nó có thể khiến một nhánh chứa nghiệm tối ưu bị **cắt vĩnh viễn**.

Mã dùng BigInteger ở hai nơi:

1. **Sắp tỷ lệ:** phép nhân chéo `v_a·w_b` và `v_b·w_a` được tính chính xác, tránh sai thứ tự fractional greedy.
2. **Giá trị phần món:** phép tính `space·value/weight` dùng BigInteger nên phép nhân không tràn; phép chia lấy floor của phân số không âm **chính xác**.

Còn `currentValue` và `bestValue` dùng long do tổng mọi giá trị đầu vào đã được xác nhận vừa long. Mọi tập con có tổng giá trị không lớn hơn tổng toàn bộ các món (vì giá trị không âm), nên các phép cộng của những món đã chọn an toàn.

**Đánh đổi:** BigInteger làm comparator và bound đắt hơn phép toán primitive. Với bộ dữ liệu có giới hạn rõ, có thể dùng long và chứng minh các tích không tràn để nhanh hơn; không nên bỏ kiểm tra chỉ vì bộ thử nhỏ đang chạy đúng.

## 14. Thứ tự xét nhánh và cải thiện incumbent

Cận dù tốt vẫn không thể cắt khi incumbent quá yếu. Trong bài tối đa hóa, muốn cắt sớm cần tìm được **một nghiệm khả thi tốt** càng sớm càng tốt.

Các lựa chọn phổ biến:

- **Thử nhánh có vẻ tốt trước:** với knapsack, sau khi sắp theo tỷ lệ giá trị/trọng lượng, thử lấy món nếu vừa sức trước khi thử bỏ.
- **Khởi tạo incumbent bằng heuristic khả thi:** ví dụ một tập món greedy nguyên; dù có thể không tối ưu, nó vẫn là cận dưới hợp lệ. Nếu heuristic được thêm vào mã, phải lưu cả danh sách món tạo ra giá trị ấy.
- **Ưu tiên nút có cận lạc quan cao nhất:** với bài max, có thể dùng priority queue theo upper bound (*best-bound search*) thay vì DFS; thường hy vọng tìm nghiệm tốt sớm, nhưng hàng đợi có thể tiêu tốn nhiều RAM.
- **Thử nghiệm thứ tự biến:** chọn món quyết định nào trước có thể thay đổi số nút tìm kiếm rất nhiều, dù không đổi tập nghiệm. Nếu thay thứ tự sau khi đã xây bound theo suffix đã sắp, phải tái định nghĩa dữ liệu suffix phù hợp.

**Không nhầm “đi nhánh tốt trước” với chứng minh đúng.** Tính đúng đến từ việc mọi nhánh chưa cắt đều được phân chia đầy đủ và mọi nhánh bị cắt có cận hợp lệ. Heuristic chỉ thay đổi hiệu năng.

### DFS, BFS và best-bound

| Chiến lược | Cách chọn nút tiếp | Đặc điểm |
|---|---|---|
| DFS | Đi sâu theo nhánh trước, quay lui | Stack O(n), thường dễ có một nghiệm nhanh |
| BFS | Xử lý theo số quyết định đã cố định | Có thể giữ số lượng nút lớn trong hàng đợi |
| Best-bound | Chọn nút có U lớn nhất với bài max | Có thể tìm nghiệm tốt sớm, nhưng cần heap/priority queue |
| Hybrid | Heuristic/DFS trước rồi best-bound | Cân bằng mục tiêu tìm nghiệm và kiểm soát bộ nhớ |

Bản Java dùng DFS để minh họa bất biến rõ ràng và giữ bộ nhớ phụ tương đối nhỏ.

## 15. Độ phức tạp và giới hạn thực tế

Với n món:

- Sắp theo tỷ lệ dùng **O(n log n)** phép so sánh, mỗi so sánh gồm phép nhân BigInteger (chi phí bit phụ thuộc độ lớn các hệ số).
- Ở mỗi nút, tính fractional bound bằng cách quét tối đa số món chưa quyết định, **O(n)** phép xử lý trong trường hợp xấu.
- Mỗi biến có nhánh lấy/bỏ, nên số nút của cây tìm kiếm có thể tới **`2^(n+1)−1`** (trước các cắt nhánh).
- Vì vậy thời gian xấu nhất vẫn có thể là **`O(n·2^n)`** thao tác số học, chưa tính chi phí bit BigInteger và overhead đệ quy.
- Bộ nhớ lưu danh sách món, mảng chosen/bestChosen, kết quả và stack DFS là **O(n)**, ngoài đối tượng BigInteger tạm và bộ nhớ nội bộ của thao tác sắp xếp.

**Nới lỏng không biến bài NP-hard thành đa thức.** Nó giúp **cắt nhánh trên nhiều đầu vào cụ thể**. Với dữ liệu đối kháng hoặc cận yếu, số nút vẫn tăng theo hàm mũ.

Với n lớn, đệ quy có thể dẫn tới `StackOverflowError`, và ngay cả n vừa phải cũng có thể cần quá nhiều thời gian. Mã này không có timeout hay cơ chế dừng sớm trả cận, nên chỉ báo hoàn thành tối ưu khi thuật toán thật sự duyệt xong. Nếu cần giới hạn thời gian, solver thực tế có thể trả **incumbent khả thi** kèm **global bound còn mở**, từ đó biết mức chênh tối ưu (*optimality gap*) thay vì tuyên bố đã tối ưu.

### Bound toàn cục khi chưa duyệt xong

Trong best-bound search, nếu còn các nút chưa xử lý với các upper bound U₁,U₂,... và incumbent B, một cận trên toàn cục có thể lấy từ:

**`U_global=max(B,U₁,U₂,...)`**.

Giá trị B vẫn là cận dưới của optimum. Khi `U_global≤B`, đã chứng minh tối ưu (theo độ chính xác cận). Nếu dừng sớm với `B<U_global`, chỉ có thể khẳng định nghiệm đang có giá trị B và tối ưu nằm trong **[B,U_global]** đối với bài max.

Không được dùng bound của **một nút** để thay cho bound toàn cục nếu còn những nút khác chưa giải.

## 16. Kiểm thử: kiểm tra cả cận và nghiệm

Để kiểm thử B&B, không đủ so đầu ra giá trị trên một vài ví dụ. Cần kiểm tra rằng **mọi cận dùng để cắt đều an toàn** và **danh sách lựa chọn là nghiệm khả thi**.

### Oracle vét cạn

Với n≤18 hoặc n≤20 trong thử nghiệm nhỏ, liệt kê `2^n` tập con:

- Tính tổng trọng lượng, tổng giá trị.
- Bỏ tập vượt sức chứa.
- Giữ max giá trị trong các tập hợp lệ.

So `bestValue` của B&B với giá trị vét cạn. Đồng thời kiểm tra những chỉ số trả về không trùng, thuộc khoảng 0..n−1, có tổng trọng lượng ≤W và tổng giá trị đúng bằng bestValue.

### Kiểm chứng cận của từng nút

Sinh một prefix quyết định lấy/bỏ món theo thứ tự đã sắp; từ prefix ấy xác định currentWeight/currentValue và tập các món suffix. Với n nhỏ, liệt kê mọi tập con suffix còn hợp lệ để tính **OPT(node)**. Sau đó so:

**`OPT(node) ≤ fractionalUpperBound(node)`**.

Đây là kiểm thử đặc biệt quan trọng. Một giá trị bị sai do nhân tràn, làm tròn sai hoặc sắp tỷ lệ sai có thể làm thuật toán cho output đúng trong nhiều ví dụ đơn giản nhưng vẫn **cắt sai** ở trường hợp hiếm.

### Bộ ca biên

| Dữ liệu | Điều cần xác nhận |
|---|---|
| n=0 | best=0, items=[] |
| W=0, mọi w>0 | best=0, items=[] |
| Mọi món nặng hơn W | best=0, không lấy phần fractional làm nghiệm |
| Một món vừa sức | Lấy món nếu v>0 |
| Hai món tỷ lệ bằng nhau | So tỷ lệ chính xác, tie cho một nghiệm hợp lệ |
| Nhiều món v=0 | Tập rỗng có thể là nghiệm tối ưu |
| Greedy nguyên không tối ưu | B&B vẫn tìm đúng giá trị tối ưu |
| Tất cả món vừa sức | Chọn mọi món có v>0, tổng giá trị tối ưu |
| Slope/tỷ lệ là phân số sát nhau | Comparator không làm tròn sai |
| Giá trị và trọng lượng lớn hợp lệ | Nhân chéo/frac dùng BigInteger |
| Tổng giá trị vượt long | Từ chối theo hợp đồng của mã |
| Trọng lượng 0/âm, giá trị âm | Từ chối theo hợp đồng của mã |
| Danh sách weights/values khác độ dài hoặc null | Từ chối |
| Nhiều nghiệm tối ưu | Trả một nghiệm; không tuyên bố liệt kê mọi nghiệm |

### Kiểm thử ngẫu nhiên

Sinh n từ 0..12, trọng lượng dương 1..10, giá trị không âm 0..30, W từ 0..30. Với mỗi bộ dữ liệu, kiểm tra:

1. Giá trị B&B trùng với vét cạn.
2. Danh sách món có chỉ số tăng, không lặp.
3. Trọng lượng và giá trị được tính lại đúng bằng kết quả.
4. Không vượt W.
5. Có cả trường hợp tie và giá trị 0.
6. Cận fractional ở những nút được chọn ngẫu nhiên **không thấp hơn tối ưu của suffix 0/1**.
7. Thứ tự món trong đầu vào có thể bị hoán vị: giá trị tối ưu không thay đổi, dù danh sách chỉ số theo input mới khác.

**Không dùng chính hàm fractionalUpperBound làm oracle cho nó.** Phải so với tối ưu nguyên được xác nhận bằng một phương pháp độc lập như liệt kê tập con.

## 17. Những lỗi phổ biến

1. **Sai hướng của cận:** tối đa hóa cần **cận trên để cắt**, tối thiểu hóa cần **cận dưới để cắt**.
2. **Dùng nghiệm tham lam nguyên làm upper bound:** nghiệm khả thi chỉ chứng minh đã đạt **ít nhất** giá trị ấy trong bài max.
3. **Nới lỏng làm mất nghiệm gốc:** nếu bài mới loại một nghiệm hợp lệ thì giá trị có thể không còn là cận an toàn.
4. **Không tính lại cận theo nhánh:** dùng sai tập món sau khi đã cố định lấy/bỏ.
5. **Cho phép lấy lại món đã bỏ trong bound như thể là suffix:** có thể cận quá lạc quan (an toàn nhưng yếu); nếu trừ giá trị prefix sai thì có thể nguy hiểm.
6. **Lấy greedy nguyên thay cho fractional optimum:** một nghiệm greedy nguyên có thể thấp hơn tối ưu suffix.
7. **Lấy floor của double bị làm tròn xuống:** có thể tạo cận thấp hơn tối ưu nguyên và cắt sai.
8. **Sắp ratio bằng phép chia nguyên `v/w`:** làm mất phần thập phân, thứ tự dễ sai.
9. **Nhân chéo bằng kiểu không đủ rộng:** tràn làm comparator sai.
10. **Nhầm cộng phần món với lấy trọn món:** fractional upper là giá trị toán học, không được dùng để cập nhật incumbent hoặc danh sách món.
11. **Không kiểm tra sức chứa trước nhánh lấy:** tạo nút vô nghiệm hoặc tổng trọng lượng tràn.
12. **Đánh giá cận bằng currentValue nhưng quên các món còn lại:** cận thấp giả và có thể cắt mất optimum.
13. **Dùng cận quá yếu nhưng cho rằng bài sẽ chạy nhanh:** cận hợp lệ không tự bảo đảm hiệu năng tốt.
14. **Cắt tại `U=B` rồi tuyên bố đếm được mọi nghiệm tối ưu:** chỉ an toàn nếu không cần liệt kê/đếm các nghiệm hòa.
15. **Không lưu nghiệm khi cập nhật best:** có thể trả giá trị đúng nhưng tập món sai hoặc rỗng.
16. **Thứ tự sorted bị nhầm với chỉ số gốc:** phải lưu originalIndex để xuất đúng món.
17. **Không hoàn tác chosen sau nhánh lấy:** trạng thái lựa chọn “rò rỉ” sang nhánh bỏ.
18. **Mặc định B&B là đa thức:** trường hợp xấu vẫn có thể cần số mũ nút.
19. **Tự động dừng theo thời gian rồi nói “đã tối ưu”:** phải phân biệt incumbent với cận toàn cục còn mở.
20. **Tối ưu cực tiểu mà dùng cận upper như max:** có thể cắt sai chiều.

## 18. Checklist khi thiết kế cận bằng nới lỏng

- Bài toán cần **min hay max**? Incumbent là nghiệm khả thi và cận một phía nào?
- Một nút đang cố định những quyết định gì, miền nghiệm con gồm những gì?
- Bài nới lỏng có **chứa mọi nghiệm của bài toán con** không?
- Giá trị tối ưu của bài nới lỏng có được tính **đúng** hoặc được chặn thêm theo **phía an toàn** không?
- Cận được tính theo đúng các biến/chỉ số còn chưa quyết định không?
- Với fractional knapsack, các món còn lại có được sắp theo **tỷ lệ chính xác** không?
- Trọng lượng, giá trị và phép nhân/chia có giới hạn đủ để không tràn không?
- Nếu mục tiêu nguyên, có dùng floor của **giá trị fractional chính xác** để làm cận trên chặt hơn không?
- Ngưỡng cắt là `U≤B` cho bài max hoặc `L≥B` cho bài min khi chỉ cần một nghiệm không?
- Khi cần **tất cả nghiệm tối ưu**, đã sửa điều kiện cắt nhánh hòa cho phù hợp chưa?
- Có nghiệm khả thi tốt sớm để làm incumbent chưa? Có bao giờ dùng bound làm incumbent sai không?
- Nhánh lấy/bỏ có bao phủ hết nghiệm và kiểm tra tính khả thi không?
- Đã đếm cả chi phí **tính bound** khi phân tích hiệu năng chưa?
- Đã thử những ca tham lam sai, tie, W=0, n=0, giá trị 0 và input lớn chưa?
- Đã kiểm chứng **tối ưu ở từng nhánh** bằng vét cạn nhỏ để kiểm tra tính admissible của bound chưa?

**Kết luận:** nới lỏng ràng buộc là phương pháp có cơ sở toán học để xây **cận lạc quan**, giúp thuật toán nhánh và cận bỏ qua an toàn các nhánh không thể cải thiện lời giải đang tốt nhất. Với 0/1 knapsack, cho phép lấy một phần món tạo fractional optimum là **cận trên**; phép `floor` của cận fractional **tính chính xác** vẫn là cận trên vì tổng giá trị nguyên. Điều kiện cắt `upper≤incumbent` được chứng minh bằng bất đẳng thức, không phải kinh nghiệm. Hiệu quả thực tế phụ thuộc độ chặt của cận, chất lượng incumbent và chi phí tính cận; tính đúng phụ thuộc việc **không bao giờ đánh giá thấp một upper bound** hoặc đánh giá cao một lower bound.