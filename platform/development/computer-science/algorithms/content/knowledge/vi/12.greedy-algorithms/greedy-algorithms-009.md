# Đổi tiền tham lam và phản ví dụ trên hệ mệnh giá

**Đổi tiền tối thiểu (minimum coin change)** là bài toán tìm **ít đồng tiền nhất** để tạo đúng số tiền mục tiêu từ một hệ mệnh giá. Một cách giải dễ nghĩ đến là **tham lam (greedy)**: lấy đồng tiền có giá trị lớn nhất còn vừa với phần tiền chưa đổi, rồi lặp lại. Nhưng đồng có giá trị lớn nhất **không phải lúc nào cũng là lựa chọn xuất hiện trong một phương án tối ưu**.

Ví dụ then chốt: với hệ mệnh giá **{1, 3, 4}**, số tiền **6**, tham lam lấy `4+1+1` (3 đồng), còn phương án `3+3` chỉ dùng **2 đồng**. Đây là phản ví dụ chứng minh tham lam **không luôn đúng** đối với các hệ mệnh giá tùy ý.

Bài học này phân tích đặc tả, cách hoạt động của tham lam, chứng minh khi nào nó đúng, cách tìm phản ví dụ và phương pháp **quy hoạch động** để đối chiếu nghiệm tối ưu. Ví dụ Java 17+ có thể biên dịch và chạy với đầu ra xác định.

## 1. Đặc tả bài toán

Cho hệ mệnh giá nguyên dương phân biệt `D={d1,d2,...,dm}` và số tiền nguyên không âm `A`. Trong biến thể cơ bản:

- Mỗi mệnh giá được sử dụng **không giới hạn số đồng (unbounded)**.
- Cần tạo **đúng tổng A**, không trả thiếu hoặc vượt.
- Mục tiêu là **tối thiểu tổng số đồng**; thứ tự lấy đồng không ảnh hưởng giá trị phương án.
- Nếu không có cách tạo tổng A, kết quả là **không có nghiệm**.
- Với `A=0`, phương án rỗng (0 đồng) là một nghiệm tối ưu.

Viết dưới dạng tối ưu nguyên: tìm `x1,...,xm` nguyên không âm để tối thiểu `x1+...+xm`, với ràng buộc `d1*x1+...+dm*xm=A`.

**Phân biệt:** yêu cầu “ít đồng nhất” khác “ít loại mệnh giá nhất”, “ít phí giao dịch nhất” hay “có bao nhiêu cách đổi”. Nếu số lượng từng mệnh giá bị giới hạn, bài toán trở thành **bounded coin change** và cần xét thêm ràng buộc về số đồng tồn kho.

Nếu có đồng mệnh giá **1**, mọi số tiền nguyên không âm đều đổi được. Nhưng điều này chỉ bảo đảm **tồn tại nghiệm**, chưa bảo đảm tham lam tìm nghiệm **ít đồng nhất**.

## 2. Thuật toán đổi tiền tham lam

Sắp mệnh giá từ lớn xuống nhỏ. Với mỗi mệnh giá `d`, lấy nhiều đồng `d` nhất mà phần tiền còn lại cho phép. Gọi `remaining` là tiền chưa đổi:

```text
take = floor(remaining / d)
remaining = remaining - take * d
```

Khi kết thúc, nếu `remaining=0` thì danh sách đã chọn là một **cách đổi hợp lệ**. Nếu `remaining>0`, **riêng cách chọn tham lam đã thất bại**; bài toán gốc vẫn có thể có nghiệm.

```text
ALGORITHM GREEDY_CHANGE(D, A)
    REQUIRE every denomination is a positive distinct integer
    REQUIRE A >= 0
    SORT D BY descending denomination

    remaining <- A
    chosen <- empty list

    FOR EACH denomination d IN D DO
        take <- FLOOR(remaining / d)
        APPEND d TO chosen EXACTLY take TIMES
        remaining <- remaining - take * d
    END FOR

    IF remaining = 0 THEN RETURN chosen
    ELSE RETURN NONE
END ALGORITHM
```

**Bất biến:** `sum(chosen)+remaining=A` và `remaining>=0`. Vì `take*d<=remaining`, mỗi lần cập nhật giữ đúng bất biến. Khi `remaining=0`, tổng các đồng được chọn bằng A.

Bất biến này **chỉ chứng minh tính hợp lệ**, không chứng minh **tối ưu số đồng**. Đây là chỗ cần thêm lập luận lựa chọn tham lam.

### Ví dụ đổi 63 với {1, 5, 10, 25}

| Mệnh giá | Tiền trước bước | Số đồng lấy | Còn lại |
| ---: | ---: | ---: | ---: |
| 25 | 63 | 2 | 13 |
| 10 | 13 | 1 | 3 |
| 5 | 3 | 0 | 3 |
| 1 | 3 | 3 | 0 |

Kết quả `[25,25,10,1,1,1]`: tổng tiền 63, dùng **6 đồng**. Với số tiền này, kết quả cũng tối ưu. Tuy nhiên, **một ví dụ thành công không chứng minh mọi số tiền trên hệ đó đều thành công**, càng không phải chứng minh cho mọi hệ mệnh giá.

## 3. Phản ví dụ thứ nhất: {1, 3, 4} và số tiền 6

```text
D = {1, 3, 4}, A = 6

Tham lam:
6 -> lấy 4, còn 2
2 -> lấy 1, còn 1
1 -> lấy 1, còn 0
Kết quả: 4 + 1 + 1 = 6, dùng 3 đồng.

Tối ưu:
6 = 3 + 3, dùng 2 đồng.
```

Phương án hai đồng thực sự **tối ưu** vì không có mệnh giá 6 để dùng chỉ một đồng. Chọn 4 ngay từ đầu buộc phải trả phần dư 2 bằng hai đồng 1, trong khi chọn 3 cho phép hoàn tất bằng một đồng 3.

**Ý nghĩa thuật toán:** tham lam đã thực hiện lựa chọn **cục bộ hợp lệ**, nhưng lựa chọn đó loại bỏ phương án tốt nhất của bài toán toàn cục.

Với cùng hệ mệnh giá nhưng `A=8`, tham lam lại chọn `4+4` (2 đồng) và **tối ưu**. Điều này cho thấy một hệ **không chuẩn tắc** vẫn có những số tiền mà greedy trả đúng. Để bác bỏ khẳng định “luôn tối ưu”, chỉ cần **một phản ví dụ**; để chứng minh “luôn tối ưu”, cần lập luận đúng cho **mọi số tiền thuộc phạm vi bài toán**.

## 4. Phản ví dụ thứ hai: có nghiệm nhưng tham lam báo thất bại

Xét `D={4,6}`, `A=8`:

```text
Greedy:
    Lấy 6, còn 2.
    Không còn mệnh giá nào <= 2.
    Trả NONE.

Cách đổi đúng:
    4 + 4 = 8, dùng 2 đồng.
```

Vì không có đồng 1, tham lam có thể **kẹt phần dư**. Nhưng bài toán vẫn có nghiệm. Trả `NONE` từ tham lam **không đủ** để kết luận toàn hệ mệnh giá không đổi được số tiền đã cho.

Với cùng hệ và `A=5`, thực sự **không có nghiệm**: mọi đồng đều chẵn, không thể tạo tổng lẻ 5. Điều kiện `gcd(D)` phải chia hết A là điều kiện **cần**. Nhưng nó **không phải điều kiện đủ** cho các tổng không âm: `gcd(4,6)=2` chia hết 2, song không thể đổi số tiền 2 bằng các đồng 4 và 6.

**Ba trường hợp phải tách biệt:** greedy tìm đúng tối ưu; greedy cho nghiệm kém tối ưu hoặc mắc kẹt dù có nghiệm; và bài toán thực sự vô nghiệm.

## 5. Khi nào hệ mệnh giá được gọi là chuẩn tắc?

Một hệ mệnh giá **chuẩn tắc (canonical coin system)** đối với bài toán đổi tiền tối thiểu khi lựa chọn đồng lớn nhất vừa với phần dư **luôn** dẫn đến số đồng tối thiểu trên mọi số tiền trong phạm vi mà hệ được định nghĩa.

- `{1,3,4}` không chuẩn tắc vì số tiền 6.
- `{1,2,4,8}` thuộc lớp hệ chuẩn tắc có chứng minh rõ ràng.
- Việc các mệnh giá đã sắp tăng hoặc có mệnh giá 1 **không đủ** để kết luận hệ chuẩn tắc.

### Chứng minh cho hệ lũy thừa

Cho `b` là số nguyên từ 2 trở lên và hệ `D={1,b,b²,...,b^k}`. Mỗi mệnh giá có số lượng vô hạn.

**Lập luận trao đổi (exchange argument):** nếu một lời giải chứa ít nhất `b` đồng mệnh giá `b^i` với `i<k`, có thể thay `b` đồng ấy bằng **một đồng `b^(i+1)`** mà không đổi tổng tiền:

```text
b copies of b^i = 1 copy of b^(i+1)
Number of coins decreases by b - 1 > 0.
```

Do đó trong một lời giải tối ưu, với mỗi mệnh giá **thấp hơn mệnh giá lớn nhất**, số đồng phải nằm trong `0..b-1`; nếu nhiều hơn, có thể trao đổi để dùng ít đồng hơn.

Những số lượng ấy chính là **các chữ số trong biểu diễn cơ số b** của số tiền, nên được xác định duy nhất bởi phần dư sau khi trừ các đồng lớn nhất. Thuật toán greedy cũng lấy nhiều đồng `b^k` nhất, rồi lần lượt lấy các chữ số của phần dư ở các lũy thừa thấp hơn. Nó trùng với dạng chuẩn của mọi lời giải tối ưu, nên **greedy tối ưu cho mọi A≥0** trên hệ này.

Ví dụ `b=2`, `D={1,2,4,8}`, `A=14`: biểu diễn nhị phân `1110` cho `14=8+4+2`, tức **3 đồng**.

**Không suy rộng tùy tiện.** Chứng minh này phụ thuộc chặt vào việc mỗi mệnh giá liên tiếp **gấp b lần** mệnh giá trước. Nó không tự động chứng minh tính chuẩn tắc của `{1,5,10,25}` hoặc hệ mệnh giá tùy ý.

## 6. Greedy-choice property khác optimal substructure

Hai thuộc tính thường được sử dụng khi chứng minh thuật toán tối ưu:

1. **Cấu trúc con tối ưu (optimal substructure):** nếu một phương án tối ưu cho số tiền A có chọn đồng d, thì những đồng còn lại phải tạo cách đổi tối ưu cho A-d. Nếu phần còn lại chưa tối ưu, thay nó bằng phương án tốt hơn sẽ giảm tổng số đồng.
2. **Tính chất lựa chọn tham lam (greedy-choice property):** tồn tại một phương án tối ưu mà **lựa chọn đầu tiên** chính là đồng **lớn nhất hiện có không vượt phần tiền còn lại**.

Thuộc tính thứ nhất đúng với bài đổi tiền không giới hạn nói chung; nhưng thuộc tính thứ hai **không đúng** cho mọi hệ.

Với `D={1,3,4},A=6`, phần dư sau khi lấy 4 là 2. Cách đổi tối ưu cho phần dư 2 là `1+1`, nhưng tổng số đồng của lựa chọn `4+(1+1)` vẫn là **3**, nhiều hơn `3+3` (2 đồng). Như vậy, dù phần dư được giải tối ưu, **lựa chọn đồng đầu tiên đã sai**.

Khi xây dựng một thuật toán greedy, cần chứng minh có thể **trao đổi** một lời giải tối ưu bất kỳ thành lời giải dùng lựa chọn greedy mà **không làm tăng chi phí**. Với hệ lũy thừa, phép đổi `b` đồng nhỏ thành một đồng lớn làm được điều này. Với hệ tùy ý, phép trao đổi tương tự có thể không tồn tại.

## 7. Quy hoạch động: giải đúng cho hệ mệnh giá tùy ý

Đặt `dp[s]` là **số đồng ít nhất** để tạo đúng tổng s hoặc `UNREACHABLE` nếu không có cách đổi.

`dp[0]=0`. Với `s≥1`, một cách đổi không rỗng phải dùng một đồng cuối d. Phần còn lại là `s-d`. Vì vậy:

```text
dp[s] = 1 + MIN(dp[s-d])
        over all denominations d <= s
        where dp[s-d] is reachable

If none is reachable:
    dp[s] = UNREACHABLE
```

Giả mã:

```text
ALGORITHM OPTIMAL_CHANGE_DP(D, A)
    REQUIRE A >= 0 and every denomination > 0
    dp[0] <- 0
    dp[1..A] <- UNREACHABLE

    FOR s FROM 1 TO A DO
        FOR EACH coin d IN D DO
            IF d <= s AND dp[s-d] is reachable THEN
                candidate <- dp[s-d] + 1
                IF dp[s] is unreachable OR candidate < dp[s] THEN
                    dp[s] <- candidate
                    pick[s] <- d
                END IF
            END IF
        END FOR
    END FOR

    IF dp[A] is unreachable THEN
        RETURN NONE
    END IF

    Reconstruct a solution using pick from A down to 0.
    RETURN (dp[A], chosen denominations)
END ALGORITHM
```

### Vì sao DP tối ưu?

Chứng minh bằng quy nạp theo s. Với s=0, dùng 0 đồng là đúng. Giả sử mọi trạng thái nhỏ hơn s đã tối ưu hoặc được ghi nhận vô nghiệm chính xác. Mọi phương án đổi s khác rỗng có một đồng cuối d; phần còn lại đổi s-d. Theo giả thuyết, cần ít nhất `dp[s-d]` đồng cho phần còn lại. Duyệt **tất cả** mệnh giá d hợp lệ và lấy giá trị nhỏ nhất chính là xét đủ mọi khả năng của đồng cuối. Vì vậy dp[s] tối ưu; nếu không có trạng thái trước nào đạt được thì s vô nghiệm.

Với m mệnh giá và mục tiêu A, DP một chiều có **O(A·m) thời gian**, **O(A) bộ nhớ** cho trạng thái và phục dựng, ngoài danh sách đồng được xuất ra. Đây là thời gian **giả đa thức (pseudo-polynomial)**: phụ thuộc vào **giá trị số A**, không chỉ số chữ số biểu diễn A. Nếu A rất lớn, mảng dp có thể không khả thi về RAM dù thuật toán đúng.

## 8. So sánh trên các trường hợp quan trọng

| Mệnh giá | Mục tiêu | Tham lam | Tối ưu thật |
| --- | ---: | --- | --- |
| `{1,2,4,8}` | 14 | `8+4+2` = 3 đồng | 3 đồng; có chứng minh hệ lũy thừa. |
| `{1,3,4}` | 6 | `4+1+1` = 3 đồng | `3+3` = 2 đồng. |
| `{1,3,4}` | 8 | `4+4` = 2 đồng | 2 đồng. |
| `{4,6}` | 8 | Kẹt ở phần dư 2, trả NONE | `4+4` = 2 đồng. |
| `{4,6}` | 5 | Trả NONE | Vô nghiệm thật. |
| `{1,5,10,25}` | 63 | `25+25+10+1+1+1` = 6 đồng | 6 đồng đối với mục tiêu này. |
| Hệ mệnh giá hợp lệ bất kỳ | 0 | Danh sách rỗng | 0 đồng. |

Trong các bài mà chỉ cần **số lượng đồng**, greedy có thể tính số đồng mỗi loại bằng phép chia nguyên, không cần xuất từng đồng. Khi mệnh giá đã sắp, phần tính toán cần **O(m)** thời gian và **O(1)** bộ nhớ phụ. Nếu phải sắp mệnh giá trước, thêm O(m log m) thời gian; nếu xuất K đồng trong một danh sách, phải tính thêm **O(K)** thời gian và bộ nhớ đầu ra. Đừng đánh đồng chi phí tính số lượng mỗi loại với chi phí **in hoặc lưu toàn bộ lời giải**.

## 9. Java 17+: chạy và so sánh hai thuật toán

Chương trình cài đặt riêng:

- `greedy`: sắp các mệnh giá tăng trên một bản sao, duyệt ngược từ lớn tới nhỏ, chọn tối đa số đồng hiện tại; không quay lui.
- `optimalDP`: xét mọi mệnh giá làm đồng cuối cho từng tổng s và phục dựng một nghiệm tối ưu bằng mảng `pick`.
- `Optional<Change>`: phân biệt có nghiệm và không tìm được nghiệm. `Change` chứa số đồng và danh sách từng đồng.

Mã từ chối mệnh giá 0, âm, trùng lặp, mảng mệnh giá rỗng, số tiền âm. DP còn từ chối `amount=Integer.MAX_VALUE` vì `amount+1` sẽ tràn `int`. Với các số tiền rất lớn khác, cần bảo đảm có đủ RAM trước khi cấp mảng DP.

Tạo tệp **`GreedyCoinChangeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class GreedyCoinChangeDemo {
    record Change(int count, List<Integer> coins) {}

    private static int[] normalized(int[] denominations) {
        Objects.requireNonNull(denominations, "denominations");
        if (denominations.length == 0) {
            throw new IllegalArgumentException("No denominations");
        }

        int[] sorted = denominations.clone();
        Arrays.sort(sorted);

        for (int i = 0; i < sorted.length; i++) {
            if (sorted[i] <= 0 ||
                    (i > 0 && sorted[i] == sorted[i - 1])) {
                throw new IllegalArgumentException(
                        "Denominations must be positive and distinct");
            }
        }
        return sorted;
    }

    public static Optional<Change> greedy(int[] denominations,
                                          int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        int[] sorted = normalized(denominations);
        int remaining = amount;
        List<Integer> used = new ArrayList<>();

        for (int i = sorted.length - 1; i >= 0; i--) {
            int coin = sorted[i];
            int take = remaining / coin;
            for (int j = 0; j < take; j++) {
                used.add(coin);
            }
            remaining -= take * coin;
        }

        if (remaining != 0) {
            return Optional.empty();
        }
        return Optional.of(new Change(used.size(), List.copyOf(used)));
    }

    public static Optional<Change> optimalDP(int[] denominations,
                                             int amount) {
        if (amount < 0 || amount == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid amount for DP");
        }
        int[] sorted = normalized(denominations);
        int[] dp = new int[amount + 1];
        int[] pick = new int[amount + 1];
        Arrays.fill(dp, -1);
        dp[0] = 0;

        for (int sum = 1; sum <= amount; sum++) {
            for (int i = sorted.length - 1; i >= 0; i--) {
                int coin = sorted[i];
                if (coin > sum || dp[sum - coin] == -1) {
                    continue;
                }
                int candidate = dp[sum - coin] + 1;
                if (dp[sum] == -1 || candidate < dp[sum]) {
                    dp[sum] = candidate;
                    pick[sum] = coin;
                }
            }
        }

        if (dp[amount] == -1) {
            return Optional.empty();
        }

        List<Integer> used = new ArrayList<>();
        for (int remaining = amount; remaining > 0;
                remaining -= pick[remaining]) {
            used.add(pick[remaining]);
        }
        return Optional.of(new Change(dp[amount], List.copyOf(used)));
    }

    private static String show(Optional<Change> result) {
        if (result.isEmpty()) {
            return "none";
        }
        Change change = result.get();
        return change.count() + " " + change.coins();
    }

    public static void main(String[] args) {
        int[] powers = {1, 2, 4, 8};
        System.out.println("powersGreedy=" + show(greedy(powers, 14)));
        System.out.println("powersOptimal=" + show(optimalDP(powers, 14)));

        int[] noncanonical = {1, 3, 4};
        System.out.println("counterGreedy=" +
                show(greedy(noncanonical, 6)));
        System.out.println("counterOptimal=" +
                show(optimalDP(noncanonical, 6)));
        System.out.println("eightGreedy=" +
                show(greedy(noncanonical, 8)));
        System.out.println("eightOptimal=" +
                show(optimalDP(noncanonical, 8)));

        int[] withoutOne = {4, 6};
        System.out.println("gapGreedy=" +
                show(greedy(withoutOne, 8)));
        System.out.println("gapOptimal=" +
                show(optimalDP(withoutOne, 8)));
        System.out.println("impossibleGreedy=" +
                show(greedy(withoutOne, 5)));
        System.out.println("impossibleOptimal=" +
                show(optimalDP(withoutOne, 5)));

        int[] common = {1, 5, 10, 25};
        System.out.println("commonGreedy=" +
                show(greedy(common, 63)));
        System.out.println("commonOptimal=" +
                show(optimalDP(common, 63)));
        System.out.println("zeroGreedy=" +
                show(greedy(noncanonical, 0)));
        System.out.println("zeroOptimal=" +
                show(optimalDP(noncanonical, 0)));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac GreedyCoinChangeDemo.java
java GreedyCoinChangeDemo
```

**Đầu ra chính xác:**

```text
powersGreedy=3 [8, 4, 2]
powersOptimal=3 [8, 4, 2]
counterGreedy=3 [4, 1, 1]
counterOptimal=2 [3, 3]
eightGreedy=2 [4, 4]
eightOptimal=2 [4, 4]
gapGreedy=none
gapOptimal=2 [4, 4]
impossibleGreedy=none
impossibleOptimal=none
commonGreedy=6 [25, 25, 10, 1, 1, 1]
commonOptimal=6 [25, 25, 10, 1, 1, 1]
zeroGreedy=0 []
zeroOptimal=0 []
```

**Giải thích các ca chạy:**

- `powers`: hai thuật toán cùng trả 3 đồng; hệ lũy thừa có chứng minh tính đúng tổng quát.
- `counter`: greedy sai tối ưu với `{1,3,4}` và 6; DP trả `3+3`.
- `eight`: cùng hệ không chuẩn tắc nhưng ở mục tiêu 8 greedy vẫn tối ưu.
- `gap`: greedy không tìm được vì đã lấy 6; DP vẫn tìm `4+4`.
- `impossible`: hai thuật toán đều trả `none`; chỉ kết quả DP có cơ sở kết luận vô nghiệm cho bài toán không giới hạn.
- `common`: cả hai trả 6 đồng ở số tiền 63; kết quả này không thay thế chứng minh cho mọi số tiền.
- `zero`: kết quả 0 đồng, danh sách rỗng là đúng.

**Chi phí thật của mã:** `normalized` sao chép và sort m mệnh giá nên dùng O(m) bộ nhớ và O(m log m) thời gian. `greedy` còn cần O(K) để chứa K đồng đầu ra. `optimalDP` dùng hai mảng dài A+1 và danh sách nghiệm, nên cần O(A+K) bộ nhớ; phần chuyển trạng thái mất O(A·m) thời gian. Danh sách đồng trong `main` chỉ dành cho minh họa, không nên tạo nếu ứng dụng chỉ cần số lượng.

Mảng `denominations` ban đầu **không bị sắp lại** vì hàm làm việc trên `clone()`. Với `amount=0`, DP chỉ có trạng thái gốc, việc phục dựng không chạy và trả 0 đồng. Giá trị `-1` chỉ là trạng thái **không thể đổi** của bảng dp, không phải số lượng đồng hợp lệ.

## 10. Cách kiểm thử một hệ mệnh giá có chuẩn tắc không

Để **tìm phản ví dụ**, dùng DP làm phép đối chiếu cho nhiều số tiền trong một miền hữu hạn:

```text
ALGORITHM FIND_COUNTEREXAMPLE(D, LIMIT)
    FOR A FROM 0 TO LIMIT DO
        greedyResult <- GREEDY_CHANGE(D, A)
        optimalResult <- OPTIMAL_CHANGE_DP(D, A)

        IF optimalResult exists AND (
            greedyResult does not exist OR
            LENGTH(greedyResult) > LENGTH(optimalResult)
        ) THEN
            RETURN A
        END IF
    END FOR

    RETURN "No counterexample found up to LIMIT"
END ALGORITHM
```

**Kết luận phải đúng phạm vi:** nếu tìm được một số tiền mà greedy dùng nhiều đồng hơn DP (hoặc greedy không đổi được nhưng DP có nghiệm), hệ đó **không chuẩn tắc**. Nếu **không** tìm được phản ví dụ trong một miền hữu hạn, ta chỉ biết greedy đúng trong miền đã thử; muốn chứng minh đúng với **mọi A** cần một định lý hoặc tiêu chuẩn kiểm định đủ mạnh.

Một bài kiểm thử tốt cần cả các số tiền ngay trước/sau mệnh giá lớn, những trường hợp cần nhiều đồng nhỏ, hệ không có đồng 1, số tiền 0 và đầu vào sai mệnh giá.

## 11. Các biến thể và lựa chọn giải pháp

| Bài toán | Đặc điểm | Hướng giải |
| --- | --- | --- |
| Đổi tiền tối thiểu với số lượng đồng không hạn chế | Có thể dùng một mệnh giá nhiều lần | Greedy **nếu đã chứng minh đúng với hệ**, hoặc DP O(A·m). |
| Số lượng từng đồng có giới hạn | Không được lấy quá số đồng tồn kho | DP/truy tìm có trạng thái giới hạn, không áp dụng nguyên xi unbounded DP. |
| Mỗi đồng dùng tối đa một lần (0/1) | Mỗi đồng là một đối tượng riêng | Quy hoạch động 0/1, cần chiều cập nhật phù hợp. |
| Đếm số cách đổi | Tối đa hóa/đếm số tổ hợp thay vì tối thiểu đồng | Công thức DP cộng cách, không lấy min. |
| Đổi tiền với phí hoặc trọng số | Chi phí mỗi đồng có thể khác 1 | Tối ưu **tổng chi phí**; chọn mệnh giá lớn không còn cùng mục tiêu. |
| Số tiền có phần thập phân | Sai số floating-point có thể gây lệch phép so sánh | Quy về đơn vị tiền nhỏ nhất nguyên hoặc dùng số học thập phân chính xác. |

Với mục tiêu rất lớn, DP dạng mảng O(A) có thể hết bộ nhớ, dù đáp án nhỏ. Khi đó cần tìm cấu trúc đặc biệt của mệnh giá, dùng một thuật toán khác phù hợp hoặc điều chỉnh giới hạn bài toán. **Tính đúng của DP không đồng nghĩa nó luôn đủ hiệu quả về tài nguyên.**

## 12. Các lỗi thường gặp

1. **“Lấy đồng lớn nhất chắc chắn ít đồng nhất.”** Sai với `{1,3,4}`, A=6.
2. **“Có đồng 1 nên greedy luôn đúng.”** Đồng 1 chỉ bảo đảm luôn đổi được A.
3. **“Greedy trả NONE nghĩa là không có cách đổi.”** Sai với `{4,6}`, A=8.
4. **“Tổng đúng thì nghiệm tối ưu.”** Tổng đúng chứng minh hợp lệ, chưa chứng minh số đồng ít nhất.
5. **“Cấu trúc con tối ưu là đủ để greedy đúng.”** Còn cần chứng minh lựa chọn greedy an toàn.
6. **Quên ràng buộc số đồng.** Nếu mỗi mệnh giá có giới hạn tồn kho, có thể không dùng lại đồng tùy ý.
7. **Không xử lý A=0.** Nghiệm tối ưu là danh sách rỗng và 0 đồng, không phải NONE.
8. **Chấp nhận mệnh giá 0 hoặc âm.** Phép chia cho 0 sai; giá trị âm có thể phá điều kiện giảm phần dư.
9. **Dùng `double` để đổi số tiền có phần thập phân chính xác.** Sai số có thể làm lệch phép so sánh; quy đổi sang đơn vị nguyên nếu phù hợp.
10. **Dùng `dp[s]=0` để đánh dấu vô nghiệm.** Số 0 là số đồng hợp lệ duy nhất cho tổng 0; dùng sentinel riêng.
11. **Quên `pick` khi muốn phục dựng lời giải.** Bảng số đồng tối thiểu không tự mang thông tin đồng nào được chọn nếu không lưu/truy lại.
12. **Báo O(m) cho chương trình còn sắp mệnh giá và in K đồng.** Phải tính thêm O(m log m) và O(K).
13. **Nói “đã kiểm thử đến 100 nên hệ chuẩn tắc”.** Kiểm thử hữu hạn không mặc nhiên chứng minh mọi số tiền.
14. **Không phân biệt vô nghiệm với không tối ưu.** Greedy có thể tìm được một nghiệm nhưng sai số đồng, hoặc mắc kẹt dù có nghiệm khác.

## 13. Bài tập có lời giải

**Bài 1.** Với `D={1,3,4}`, A=6, vì sao greedy sai? **Đáp án:** greedy chọn `4+1+1` (3 đồng), còn `3+3` chỉ 2 đồng, và không có đồng 6 nên 2 đồng là tối ưu.

**Bài 2.** Với cùng D nhưng A=8, greedy có sai không? **Đáp án:** không; `4+4` dùng 2 đồng, không có đồng 8 nên là tối ưu.

**Bài 3.** Với `D={4,6}`, A=8, greedy báo NONE. Kết luận bài toán vô nghiệm có đúng không? **Đáp án:** không; dùng `4+4`.

**Bài 4.** Với `D={1,7,10}`, A=14, so sánh greedy với tối ưu. **Đáp án:** greedy lấy `10+1+1+1+1` (5 đồng), tối ưu là `7+7` (2 đồng).

**Bài 5.** Vì sao hệ `D={1,2,4,8}` dùng greedy luôn đúng? **Đáp án:** các mệnh giá là lũy thừa của 2; mọi cặp đồng cùng mệnh giá nhỏ có thể đổi thành một đồng lớn để giảm số đồng. Biểu diễn nhị phân của số tiền cho số đồng greedy tối ưu.

**Bài 6.** Với A=0, kết quả tối ưu là gì? **Đáp án:** dùng 0 đồng; danh sách rỗng là **một nghiệm**, không phải vô nghiệm.

**Bài 7.** Nếu gcd của các mệnh giá chia hết A, có chắc tồn tại cách đổi A không? **Đáp án:** không. `D={4,6}`, A=2 có gcd bằng 2 nhưng không thể đổi 2.

**Bài 8.** Tại sao DP có công thức `dp[s]=1+min dp[s-d]`? **Đáp án:** một phương án không rỗng cho s dùng một đồng d; phần còn lại phải đổi s-d. Xét toàn bộ d hợp lệ và lấy số đồng ít nhất không bỏ sót nghiệm tối ưu.

**Bài 9.** Nếu chỉ có **một đồng 3** trong hệ `{1,3,4}`, còn lại tùy ý, có thể coi phương án `3+3` hợp lệ không? **Đáp án:** không; đó là biến thể giới hạn số lượng, không phải unbounded coin change.

**Bài 10.** Chạy thử greedy và DP bằng nhau cho mọi A từ 0 đến 100 có chứng minh hệ chuẩn tắc không? **Đáp án:** chưa; chỉ xác nhận miền đã thử. Cần một chứng minh hoặc tiêu chuẩn đủ cho mọi A.

## 14. Checklist trước khi dùng greedy đổi tiền

1. Mục tiêu là **ít đồng nhất** hay một hàm chi phí khác?
2. Mỗi mệnh giá có **vô hạn đồng** hay có giới hạn?
3. Tổng phải **đúng A** hay được phép trả thiếu/thừa?
4. Có mệnh giá 1 không? Nếu không có, làm sao phân biệt **vô nghiệm thật** với greedy mắc kẹt?
5. Có chứng minh **greedy-choice property** cho hệ đang xét chưa?
6. Đã thử phản ví dụ `{1,3,4}` với A=6 và `{4,6}` với A=8 chưa?
7. Có thể dùng **DP** làm chuẩn đối chiếu trong miền A phù hợp không?
8. Có tính đủ O(m log m) khi sort mệnh giá, O(K) khi xuất đồng và O(A·m) với DP không?
9. Đã kiểm tra A=0, mệnh giá sai, số tiền lớn, độ chính xác số học và lỗi tràn số chưa?
10. Nếu tuyên bố “luôn tối ưu”, **đâu là chứng minh cho mọi đầu vào**, không chỉ một vài ví dụ?

**Ghi nhớ:** tham lam đổi tiền là một chiến lược **cục bộ**; nó tạo được tổng đúng nếu phần dư cuối là 0, nhưng chỉ tối ưu trên hệ mệnh giá có cấu trúc phù hợp. Phản ví dụ `{1,3,4}` đổi 6 cho thấy việc chọn đồng lớn nhất không luôn an toàn. Hãy chứng minh tính chuẩn tắc khi có thể, hoặc dùng quy hoạch động để tìm và xác minh lời giải tối ưu.
