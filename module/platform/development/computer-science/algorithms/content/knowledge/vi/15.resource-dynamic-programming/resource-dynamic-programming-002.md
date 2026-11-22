# Ba lô không giới hạn và thứ tự cập nhật

**Ba lô không giới hạn** (*unbounded knapsack* hay *complete knapsack*) là một bài toán **quy hoạch động tài nguyên**: có nhiều **loại vật**, mỗi loại có một **trọng lượng/chi phí** và một **giá trị/lợi ích**, được phép lấy **bao nhiêu bản sao cũng được**, miễn tổng trọng lượng không vượt sức chứa. So với ba lô 0/1, nơi mỗi vật chỉ được chọn tối đa một lần, điểm thay đổi tưởng nhỏ này làm thay đổi **phép chuyển và hướng duyệt mảng DP**.

Trong triển khai một chiều kiểu “xét từng loại vật”, quy tắc cốt lõi là:

- **Ba lô không giới hạn:** Với mỗi loại vật, duyệt sức chứa **tăng từ weight đến C**, cho phép kết quả hiện tại dùng lại **chính loại vật ấy**.
- **Ba lô 0/1:** Với mỗi vật, duyệt sức chứa **giảm từ C đến weight**, để mỗi vật không được sử dụng nhiều lần trong cùng lượt.
- Nếu đổi thứ tự vòng lặp thành **sức chứa ngoài, loại vật trong**, bài toán **tối đa giá trị** vẫn có thể giải đúng vì mọi phép chuyển dùng sức chứa nhỏ hơn; nhưng trong **bài đếm cách đổi tiền**, thứ tự vòng lặp quyết định đang **đếm tổ hợp hay hoán vị**.

Bài học sẽ phân tích chính xác ba mô hình thường dễ nhầm: **không vượt sức chứa**, **phải dùng đúng sức chứa** và **đếm số cách ghép tài nguyên**. Mỗi công thức có **ý nghĩa trạng thái, bất biến và trường hợp cơ sở khác nhau**. Cuối bài có chương trình Java 17+ chạy được, tái dựng số lượng từng loại vật và kiểm tra các trường hợp trùng lặp, chi phí 0, lợi ích âm, mục tiêu không thể đạt và tràn số.

## 1. Phát biểu bài toán chuẩn

Cho m loại vật (đánh số 0..m−1). Loại i có:

- `weight[i] > 0`: trọng lượng/chi phí **nguyên dương**.
- `value[i]`: lợi ích, có thể nguyên âm, 0 hoặc dương.
- Có **vô hạn số bản sao** của loại này.

Sức chứa `C >= 0` là một số nguyên. Cần tìm số lượng `count[i] >= 0` là số nguyên sao cho:

```text
Tối đa:       sum(count[i] * value[i])
Ràng buộc:    sum(count[i] * weight[i]) <= C
              count[i] là số nguyên không âm
              mỗi loại có thể lấy nhiều lần
```

Trong biến thể **không vượt sức chứa**, được phép **không lấy vật nào**, nên giá trị tối ưu luôn **≥ 0** dù một số vật có lợi ích âm. Những vật lợi ích âm có thể bị bỏ qua; chúng không cần thiết để tối đa giá trị khi không bắt buộc dùng hết sức chứa.

**Giả thiết weight > 0 rất quan trọng:** Nếu một loại vật có `weight=0` và `value>0`, ta lấy vô hạn bản sao mà không mất tài nguyên: bài toán tối đa giá trị **không có nghiệm hữu hạn**, không thể chỉ dùng mảng DP hữu hạn để trả một con số đúng. Nếu weight=0, value≤0 thì loại đó không giúp tối ưu biến thể không vượt sức chứa, nhưng có thể gây **vòng truy vết vô hạn** nếu triển khai theo cách lấy vật rồi giữ nguyên sức chứa. Vì vậy mã minh họa **từ chối mọi weight≤0** thay vì âm thầm bỏ qua.

### Ví dụ cơ bản

Có hai loại vật:

| Loại | Trọng lượng | Lợi ích | Số bản sao tối đa |
| --- | ---: | ---: | --- |
| A | 2 | 3 | Không giới hạn |
| B | 3 | 4 | Không giới hạn |

Sức chứa `C=7`.

Một phương án tối ưu là lấy **2 bản sao A + 1 bản sao B**:

```text
Tổng trọng lượng = 2 + 2 + 3 = 7
Tổng lợi ích      = 3 + 3 + 4 = 10
```

Trong ba lô **0/1** cũng với hai vật A/B, ta chỉ lấy mỗi loại tối đa một bản sao, nên tốt nhất là **A+B** có giá trị **7**, dù sức chứa 7 vẫn còn chỗ. Đây là khác biệt về **ràng buộc số bản sao**, không phải khác biệt về cách in kết quả.

## 2. Phân biệt ba lô 0/1, ba lô không giới hạn, ba lô hữu hạn

| Bài toán | Số lần chọn một loại vật | Hướng cập nhật thường dùng khi vòng ngoài theo vật |
| --- | --- | --- |
| **0/1 knapsack** | 0 hoặc 1 lần | **Sức chứa giảm** |
| **Unbounded/complete knapsack** | Bất kỳ số lần không âm | **Sức chứa tăng** |
| **Bounded knapsack** | Tối đa `limit[i]` bản sao | Cần xử lý số lượng riêng, ví dụ phân rã nhị phân hoặc monotone queue phù hợp |

Ví dụ với vật A trọng lượng 2, lợi ích 3, sức chứa 6:

- Nếu **không giới hạn**: lấy A ba lần, giá trị 9.
- Nếu **0/1**: chỉ lấy A một lần, giá trị 3.
- Nếu **bounded với limit[A]=2**: chỉ lấy A nhiều nhất hai lần, giá trị 6.

Từ “**loại vật**” không có nghĩa chỉ được lấy một cái. Đề bài phải nói rõ số lượng bản sao. Đặc biệt, khi có nhiều phần tử trùng trọng lượng và giá trị trong danh sách đầu vào, cần xác định đó là **hai loại độc lập được lấy vô hạn** hay **hai món đơn lẻ 0/1**; không nên suy diễn từ dữ liệu.

### Một phép chuyển có “lấy lại chính nó” hay không?

Khác biệt sâu hơn hướng vòng lặp:

- **0/1:** Khi xử lý vật i, trạng thái mới sau lấy i phải dựa vào **trạng thái của giai đoạn chưa xét i**, nếu không có thể lấy i nhiều lần.
- **Không giới hạn:** Khi xử lý vật i, trạng thái sau lấy i có thể dựa vào **trạng thái đã được cập nhật trong cùng giai đoạn i**, bởi lấy thêm một bản sao của i là hợp lệ.

Điểm này sẽ xuất hiện rõ trong mảng `dp[capacity]`.

## 3. Trạng thái một chiều: lợi ích tối đa khi **không vượt** sức chứa

Định nghĩa:

```text
A[c] = tổng lợi ích lớn nhất có thể đạt
       khi chọn tùy ý số bản sao các loại vật
       với tổng trọng lượng <= c.

Công việc còn lại là tìm A[C].
```

Vì được chọn **rỗng**, `A[0]=0` và `A[c]>=0` cho mọi c.

Một công thức đúng với trọng lượng nguyên dương:

```text
A[0] = 0

A[c] = max(
    A[c-1],                                 // không dùng hết đơn vị c
    value[i] + A[c-weight[i]]               // chọn thêm một bản sao i
       với mọi i có weight[i] <= c
)
cho c=1,2,...,C
```

Ở đây `A[c-1]` mang ý nghĩa **cho phép bỏ trống phần sức chứa**, không phải “thêm một vật trọng lượng 1”. Với vật trọng lượng nguyên, một lời giải có tổng trọng lượng không vượt c hoặc đã nằm trong mức c−1, hoặc (nếu dùng đúng c) có thể bỏ bớt một bản sao của một loại i để được một lời giải trong mức c−weight[i]. Ngược lại, mọi nhánh chuyển đều tạo lời giải hợp lệ trong c.

**Hướng tính:** `weight[i]>0` nên `c-weight[i]<c`. Nếu duyệt `c=1..C`, mọi `A[c-weight[i]]` cần dùng đã được tính trước. Do đó công thức này không phụ thuộc dữ liệu tương lai và có thể dùng một mảng `long[C+1]`.

### Tính dần cho ví dụ A=(2,3), B=(3,4)

| Sức chứa c | A[c] | Một lựa chọn đạt A[c] |
| ---: | ---: | --- |
| 0 | 0 | Không lấy gì |
| 1 | 0 | Chưa có vật nào vừa |
| 2 | 3 | 1 A |
| 3 | 4 | 1 B |
| 4 | 6 | 2 A |
| 5 | 7 | 1 A + 1 B |
| 6 | 9 | 3 A |
| 7 | 10 | 2 A + 1 B |

Ví dụ `A[7]`:

```text
carry = A[6]           = 9
take A = 3 + A[7-2]    = 3 + 7 = 10
take B = 4 + A[7-3]    = 4 + 6 = 10

A[7] = max(9,10,10) = 10
```

Hai nhánh lấy A hoặc lấy B có thể dẫn tới **hai cách tái dựng thứ tự** nhưng cùng đa tập chọn 2 A và 1 B. Khi bài yêu cầu chỉ **giá trị lớn nhất**, cách chọn khi hòa không ảnh hưởng tính đúng.

### Tại sao không cần trạng thái “đã dùng vật i bao nhiêu lần”?

Vì được dùng **không giới hạn**, số lần dùng một loại trong quá khứ không ảnh hưởng khả năng dùng nó ở tương lai. Toàn bộ phần ràng buộc liên quan tới lựa chọn tiếp theo được tóm tắt bằng **sức chứa còn/đang xét**. Đối với ba lô 0/1, phải biết đã xử lý vật nào, nên giai đoạn i hoặc cách duyệt đảo chiều rất quan trọng để không lấy lại vật đó.

## 4. Triển khai theo từng loại vật: lý do phải duyệt sức chứa **tăng**

Cách thường gặp nhất để giải complete knapsack:

```java
long[] dp = new long[capacity + 1];

for (Item item : items) {
    for (int c = item.weight(); c <= capacity; c++) {
        dp[c] = Math.max(
                dp[c],
                dp[c - item.weight()] + item.value());
    }
}
```

Đoạn trên giả định đã kiểm tra `capacity>=0`, `item.weight()>0`, mảng và dữ liệu hợp lệ; cần cân nhắc tràn số khi cộng. Chương trình Java hoàn chỉnh ở phần 11 sẽ xử lý đầu vào và dùng `Math.addExact`.

### Bất biến theo loại vật

Sau khi xử lý xong các loại `0..i`, `dp[c]` là giá trị tốt nhất với sức chứa không vượt c, khi **chỉ được dùng các loại 0..i** nhưng mỗi loại có thể được lấy nhiều bản sao.

Khi xử lý loại i với trọng lượng w>0:

- Các loại trước i đã có mặt trong `dp`.
- Ta duyệt c **tăng** từ w đến C.
- Khi đến c, `dp[c-w]` có thể **đã được cải thiện bởi chính loại i** trong lượt này, bởi c−w<c.
- Vì vậy `dp[c-w]+value[i]` có thể có 2, 3, ... bản sao của i.
- Phép `max` giữ lại phương án tốt nhất giữa không thêm i và thêm một bản sao i.

Bằng quy nạp theo loại i và sức chứa c, mọi số bản sao không âm của loại i đều được xét gián tiếp, không cần vòng thứ ba đếm số bản sao. Sau lượt cuối, `dp[C]` chính là đáp án.

### Mô phỏng một loại vật

Chỉ có A trọng lượng 2, giá trị 3, sức chứa C=6:

```text
Ban đầu:
c:     0  1  2  3  4  5  6
dp:    0  0  0  0  0  0  0

Cập nhật theo c TĂNG:
c=2 -> dp[2] = max(0, dp[0]+3) = 3
c=3 -> dp[3] = max(0, dp[1]+3) = 3
c=4 -> dp[4] = max(0, dp[2]+3) = 6
                  ^ dp[2] đã dùng 1 A
c=6 -> dp[6] = max(0, dp[4]+3) = 9
                  ^ dp[4] đã dùng 2 A

Kết quả dp[6]=9, tương ứng 3 bản sao A.
```

**Nếu duyệt c giảm** với chỉ một loại A:

```text
c=6 -> đọc dp[4] cũ = 0, được 3
c=4 -> đọc dp[2] cũ = 0, được 3
c=2 -> đọc dp[0] cũ = 0, được 3

Kết quả dp[6]=3: chỉ lấy được 1 bản sao A.
```

Đây là kết quả của **0/1 knapsack**, không phải unbounded knapsack. Vì thế hướng quét không phải chi tiết tối ưu vi mô; nó quyết định **mô hình có được phép tái sử dụng vật đang xét hay không**.

## 5. Vì sao ba lô 0/1 phải duyệt sức chứa giảm?

Ở bài 0/1, mỗi vật có thể chọn 0 hoặc 1 lần. Nếu dùng 1D DP và vòng ngoài theo vật:

```java
for (Item item : items) {
    for (int c = capacity; c >= item.weight(); c--) {
        dp[c] = Math.max(
                dp[c],
                dp[c - item.weight()] + item.value());
    }
}
```

Khi c giảm, ô `dp[c-weight]` có chỉ số **nhỏ hơn c**, nên ô ấy **chưa được cập nhật bởi vật đang xét trong cùng lượt**. Nhánh lấy vật chỉ thêm nó vào một phương án **không chứa vật ấy**, bảo đảm số bản sao không vượt một.

**Phản ví dụ ngắn:** Vật A=(weight 2, value 3), C=6.

- Duyệt **tăng**: `dp[6]=9`, tức 3 bản sao A → **sai** cho bài 0/1.
- Duyệt **giảm**: `dp[6]=3`, tức 1 bản sao A → đúng.

**Giả định và ngoại lệ:** Cách giải thích này áp dụng khi cập nhật *một mảng dp tại chỗ*, vòng ngoài theo vật và item.weight()>0. Nếu dùng **hai mảng riêng cho giai đoạn i−1 và i**, ta có thể truy cập giai đoạn trước trực tiếp mà không cần dựa vào chiều duyệt; nhưng chi phí bộ nhớ khác. Không nên học thuộc “mọi bài DP đều duyệt tăng/giảm” mà không hiểu **ô nguồn thuộc giai đoạn nào**.

## 6. Đổi thứ tự vòng lặp: sức chứa ngoài, vật trong

Với bài **tối đa giá trị** không giới hạn và trọng lượng nguyên dương, công thức `A[c]` ở phần 3 có thể triển khai:

```java
for (int c = 1; c <= capacity; c++) {
    dp[c] = dp[c - 1];     // Không bắt buộc dùng hết c
    for (Item item : items) {
        if (item.weight() <= c) {
            dp[c] = Math.max(
                    dp[c],
                    dp[c - item.weight()] + item.value());
        }
    }
}
```

Lúc này **sức chứa c** là vòng ngoài; mọi ô `dp[c-w]` đã được tính từ **sức chứa nhỏ hơn c**, nên công thức tối ưu cho `A[c]` được áp dụng trực tiếp.

**Kết quả tối ưu giống cách vòng ngoài theo vật:** Vì việc chọn các loại vật không giới hạn và mục tiêu là **tổng lợi ích tối đa**, mọi đa tập vật hợp lệ có thể được xét ở một trong những thứ tự thêm vật, và tối ưu chỉ phụ thuộc đa tập chứ không phụ thuộc **trình tự lấy vật**.

Tuy nhiên, **không được suy rộng** kết luận này cho mọi loại DP:

- Khi **đếm số cách ghép tiền**, thứ tự vòng lặp làm thay đổi “một cách” có xét thứ tự chọn hay không.
- Khi có ràng buộc **trình tự** (ví dụ không được chọn cùng loại hai lần liên tiếp), thứ tự chọn có ý nghĩa, nên trạng thái phải bổ sung thông tin quá khứ phù hợp.
- Khi vật được lấy **tối đa một lần**, dùng sức chứa ngoài và vật trong với cùng một mảng có thể vô tình dùng lại một vật.
- Khi trọng lượng bằng 0, phụ thuộc `dp[c]` về chính `dp[c]` phá tính tiến triển theo c; phải xử lý ngoài công thức này.

Trong chương trình phần 11, cách **sức chứa ngoài, vật trong** được dùng để vừa tính tối ưu vừa **truy vết ổn định** số bản sao từng loại.

## 7. Hai khái niệm dễ lẫn: “không vượt” và “đúng bằng”

### Không vượt sức chứa (at most)

Ràng buộc là `totalWeight <= C`. Luôn có lời giải rỗng đạt 0. Ta có thể **để dư sức chứa** nếu không còn vật phù hợp hoặc nếu lấy thêm làm giảm lợi ích.

Ví dụ vật `(4,8)` và `(6,11)`, C=7:

```text
Chọn một vật nặng 6, lợi ích 11; dư 1 đơn vị.
Không có cách ghép đúng 7 với các trọng lượng 4 và 6.

Giá trị tối ưu at most 7 = 11.
```

### Bắt buộc dùng đúng sức chứa (exact fill)

Ràng buộc là `totalWeight == C`. Không thể mặc định mọi c đều có lời giải. Cần biểu diễn **trạng thái không thể đạt**, không được coi là giá trị 0 bình thường.

Một công thức:

```text
E[0] = 0
E[c] = không thể đạt, với mọi c > 0 lúc khởi tạo

Cho c = 1..C:
  Với mọi loại i có weight[i] <= c và E[c-weight[i]] đạt được:
     E[c] = max(E[c], E[c-weight[i]] + value[i])
```

Vì mỗi trọng lượng >0, chỉ dùng ô có chỉ số nhỏ hơn. Trạng thái đạt được có thể có lợi ích **âm**, nếu mọi cách lấp đúng c đều buộc lấy vật có lợi ích âm.

**Ví dụ:**

```text
Vật A=(4,8), B=(6,11)

Exact fill C=7: không có cách ghép 4*x+6*y=7 (x,y>=0).
Exact fill C=8: lấy 2 A, lợi ích 16.
At most  C=7: lấy 1 B, lợi ích 11, còn dư 1.
```

Dùng mảng `boolean reachable[c]` tách biệt với `long best[c]` là cách rõ ràng để phân biệt **không đạt được** và **đạt được với lợi ích 0 hoặc âm**. Nếu dùng giá trị sentinel như `Long.MIN_VALUE`, phải tránh cộng với sentinel để không tràn số.

### “Không vượt” và “đúng bằng” không thể dùng chung base case mù quáng

- `A[c]` at most: mặc định 0 vì được bỏ mọi vật.
- `E[c]` exact fill: chỉ `E[0]=0`; các c>0 mặc định **không thể đạt**.

Việc khởi tạo `E[c]=0` cho mọi c khiến chương trình có thể trả 0 ở sức chứa không thể lấp, hoặc trả giá trị của cách lấp một phần cho câu hỏi đòi lấp hết.

## 8. Đếm cách đổi tiền: thứ tự vòng lặp đổi **ý nghĩa đáp án**

Giả sử có các **mệnh giá phân biệt, nguyên dương** `coins=[1,2,3]` và số tiền `S=4`, dùng không giới hạn mỗi mệnh giá.

Đây là **bài đếm**, không phải bài tối đa giá trị. Cùng một số tiền được ghép nhiều cách, phải định nghĩa rõ **thứ tự chọn đồng xu có được phân biệt không**.

### 8.1. Đếm tổ hợp – không phân biệt thứ tự

Với các mệnh giá 1,2,3, những tổ hợp tạo 4 là:

```text
1 + 1 + 1 + 1
1 + 1 + 2
2 + 2
1 + 3

Tổng cộng 4 tổ hợp.
```

Các chuỗi `1+3` và `3+1` được coi là **cùng một tổ hợp** vì dùng cùng đa tập mệnh giá.

Công thức cập nhật một chiều:

```java
long[] ways = new long[target + 1];
ways[0] = 1;           // Một cách tạo tổng 0: chọn rỗng

for (int coin : coins) {
    for (int sum = coin; sum <= target; sum++) {
        ways[sum] += ways[sum - coin];
    }
}
```

**Vật/coin ngoài, tổng tiền tăng trong**. Bất biến sau khi xử lý mệnh giá thứ i: `ways[s]` là số tổ hợp tạo s **chỉ sử dụng các mệnh giá 0..i**, mỗi loại có thể lấy nhiều lần. Mỗi tổ hợp được đếm **đúng một lần** theo cấu trúc số lượng của từng mệnh giá, không tùy thứ tự liệt kê chúng.

Chỉ cần đổi vòng trong thành **giảm** sẽ ngầm giới hạn mỗi mệnh giá ở **một lần**, khiến bài toán thành **đếm tổ hợp kiểu 0/1**.

### 8.2. Đếm dãy có thứ tự – phân biệt trình tự chọn

Khi hai trình tự `1+3` và `3+1` được tính là **hai cách**, ta đếm các **dãy** (*ordered sequences*) ghép thành S.

Công thức:

```text
P[0] = 1
P[s] = sum(P[s-coin]) trên mọi coin <= s
       (s = 1..S)
```

Lựa chọn **đồng cuối cùng** trong dãy là một loại coin. Đặt nó ở cuối một dãy có tổng s−coin; mỗi dãy khác nhau được xét theo đúng đồng cuối nên không trùng.

Mã tương ứng:

```java
long[] ways = new long[target + 1];
ways[0] = 1;

for (int sum = 1; sum <= target; sum++) {
    for (int coin : coins) {
        if (coin <= sum) {
            ways[sum] += ways[sum - coin];
        }
    }
}
```

**Tổng tiền ngoài, coin trong**. Với coins [1,2,3], S=4:

```text
P[0] = 1
P[1] = P[0] = 1
P[2] = P[1] + P[0] = 2
P[3] = P[2] + P[1] + P[0] = 4
P[4] = P[3] + P[2] + P[1] = 7

Kết quả: 7 dãy có thứ tự, khác với 4 tổ hợp.
```

**Đặc biệt về đầu vào:** Các mệnh giá phải **phân biệt** nếu mỗi mệnh giá là một loại lựa chọn được nhận dạng bằng giá trị. Nếu truyền `[1,1,2]` mà không xử lý trùng, thuật toán có thể đếm hai đồng 1 “khác loại” dù đề coi chúng là cùng mệnh giá, làm phóng đại số cách. Mã minh họa từ chối trùng để đảm bảo ý nghĩa rõ ràng.

**Trường hợp sum=0:** Có đúng **1** cách là **không chọn đồng nào**, bất kể đó là tổ hợp hay dãy. Nếu đề yêu cầu phải chọn ít nhất một đồng, quy ước sẽ khác và cần sửa cách định nghĩa.

### 8.3. Bảng ghi nhớ về thứ tự

| Cấu trúc hai vòng | Ý nghĩa thường gặp nếu DP và base khớp |
| --- | --- |
| Vật ngoài, c **tăng** | Unbounded knapsack; cho phép dùng nhiều bản sao của vật hiện tại |
| Vật ngoài, c **giảm** | 0/1 knapsack; dùng tối đa một bản sao của vật hiện tại |
| Coin ngoài, sum **tăng**, cộng số cách | Đếm **tổ hợp** theo mệnh giá |
| Sum ngoài, coin trong, cộng số cách | Đếm **dãy có thứ tự/hoán vị** theo mệnh giá |
| c ngoài, vật trong, lấy max | Unbounded max-value với trọng lượng dương, có thể truy vết bằng quyết định theo c |

Đây là **các mẫu cho những công thức cụ thể**, không phải một bảng quy tắc áp dụng cho mọi bài DP. Phải kiểm tra **state nghĩa là gì**, `dp[c]` đang thuộc giai đoạn nào và `+` hay `max` đang kết hợp những gì.

## 9. Chứng minh đúng cho ba lô không giới hạn

### 9.1. Lựa chọn đủ và hợp lệ

Mọi nghiệm khả thi của bài không vượt sức chứa hoặc **rỗng**, hoặc chứa một loại vật i. Bỏ đi một bản sao của i sẽ tạo nghiệm có trọng lượng không vượt `c-weight[i]`. Do đó tổng lợi ích của nghiệm ban đầu không vượt `value[i]+A[c-weight[i]]`. Nếu nghiệm không dùng hết c và trọng lượng nguyên, nó cũng được bao phủ bởi `A[c-1]`.

Ngược lại, mỗi nhánh của công thức:

- `A[c-1]` là một tập vật có trọng lượng ≤c−1≤c.
- `value[i]+A[c-weight[i]]` là một tập vật dùng c−w đơn vị hoặc ít hơn, thêm một vật i nặng w, tổng ≤c.

Mọi nhánh tạo nghiệm hợp lệ, và mọi nghiệm tối ưu đều được một nhánh bao phủ. Lấy `max` là đúng.

### 9.2. Quy nạp theo sức chứa

**Cơ sở c=0:** Vì trọng lượng mọi vật dương, không vật nào vừa sức chứa 0; lấy rỗng cho giá trị 0, nên A[0]=0.

**Bước quy nạp:** Giả sử `A[t]` đúng cho mọi t<c. Mỗi nhánh ở sức chứa c chỉ dùng `A[c-1]` hoặc `A[c-weight[i]]`, đều có chỉ số nhỏ hơn c. Theo giả thiết, chúng cho phần tiếp diễn tối ưu. Như lập luận ở 9.1, công thức xét đủ mọi hình thức của một nghiệm tối ưu và không tạo nghiệm vô hiệu. Vì vậy A[c] đúng.

Tính đúng với **số lượng không giới hạn** xuất phát từ việc `A[c-weight[i]]` đã có thể chứa bao nhiêu bản sao của i cũng được; việc cộng thêm một i không vi phạm giới hạn số lượng nào.

### 9.3. Vì sao vòng lặp kết thúc?

Với trọng lượng w>0, mỗi lần lấy một vật ở giai đoạn truy vết làm sức chứa còn lại từ c xuống c−w<c. Khi không có vật mới được chọn, ta giảm c đi 1. Đó là đại lượng nguyên không âm **giảm nghiêm ngặt** cho tới 0.

Nếu cho phép vật trọng lượng 0 mà vẫn lưu quyết định “chọn vật ấy”, sau chọn c không giảm, việc truy vết có thể lặp vô hạn. Đây là lý do ràng buộc weight>0 vừa có ý nghĩa toán học vừa là điều kiện tiến triển của thuật toán.

### 9.4. Bất biến cập nhật tại chỗ theo từng vật

Giả sử trước khi xét loại i, `dp[c]` tối ưu với các loại đã xử lý trước đó. Khi c tăng:

- Các ô có chỉ số thấp hơn c đã được cập nhật trong cùng lượt i.
- `dp[c-w_i]` bao gồm các phương án dùng bất kỳ số bản sao i.
- Từ đó cộng một i tạo thêm mọi phương án có ít nhất một bản sao i.
- Giá trị cũ `dp[c]` giữ các phương án không dùng thêm i.

Do đó sau lượt i, mọi `dp[c]` tối ưu với các loại đã xử lý, và công thức sau cùng cho kết quả đúng. Thứ tự **tăng** tạo ra việc “dùng lại chính vật i” một cách hợp lệ, không phải lỗi do mảng bị ghi đè.

## 10. Phân tích độ phức tạp và phạm vi áp dụng

Gọi m là số loại vật và C là sức chứa nguyên không âm.

| Kỹ thuật | Thời gian | Bộ nhớ chính |
| --- | --- | --- |
| Unbounded max-value, 1D item-first | **O(mC)** | **O(C)** |
| Unbounded max-value, capacity-first + truy vết | **O(mC)** | O(C+m) gồm DP, choice và mảng số lượng |
| 0/1 max-value, 1D item-first giảm | **O(mC)** | **O(C)** |
| Exact fill dùng reachable[] và best[] | **O(mC)** | **O(C)** |
| Đếm tổ hợp tiền, coin-first | **O(mS)** | **O(S)** |
| Đếm dãy có thứ tự, amount-first | **O(mS)** | **O(S)** |

Các cận trên giả định truy cập mảng, cộng và so sánh số nguyên có chi phí O(1). Tổng thời gian cũng bao gồm kiểm tra input O(m) và khởi tạo mảng O(C/S).

### Đây là thuật toán giả đa thức

Độ phức tạp O(mC) phụ thuộc vào **giá trị số** C, không phải chỉ độ dài mã hóa nhị phân của C. Ví dụ C=10⁹ đòi hỏi một tỷ ô dù biểu diễn C chỉ cần khoảng 30 bit. Vì vậy đây là **pseudo-polynomial time**, không phải đa thức theo kích thước đầu vào tính bằng số bit trong mọi trường hợp.

Nếu C rất lớn, cần cân nhắc giảm đơn vị, dùng cấu trúc trạng thái thưa khi số trạng thái đạt được ít, đổi mô hình ràng buộc hoặc dùng kỹ thuật tối ưu khác phù hợp. Không cấp phát mảng `C+1` chỉ vì n nhỏ.

### Không gian O(C) không đồng nghĩa tổng không gian O(1)

Mảng `dp` và `choice` có độ dài C+1, nên là O(C). Mảng số lượng từng vật dài m, nên O(m). Nếu cần trả **danh sách từng bản sao** thay vì mảng đếm, kích thước đầu ra có thể là O(C/minWeight). Mã ví dụ trả số lượng từng loại để gọn và tránh lặp một vật hàng triệu lần trong output.

### Tràn số và miền giá trị

- Số bản sao tối đa của một vật weight≥1 không vượt C, nhưng tổng giá trị có thể vượt `int`; dùng `long` cho lợi ích.
- Số **cách** đổi tiền có thể rất lớn, thậm chí vượt `long`; có thể dùng `BigInteger` hoặc modulo theo yêu cầu.
- Ví dụ Java dùng `Math.addExact(long,long)` để **báo lỗi khi tràn long** thay vì âm thầm tạo kết quả sai. Nó không tự biến một kết quả quá lớn thành số đúng; phải chọn cách biểu diễn đáp án khác nếu cần.
- `Integer.MAX_VALUE` không phải kích thước mảng an toàn; biểu thức `capacity+1` có thể tràn int ngay tại cận. Mã từ chối trường hợp đó, nhưng ngân sách nhỏ hơn cận vẫn có thể gây `OutOfMemoryError` trên JVM.

## 11. Chương trình Java 17+ hoàn chỉnh

Chương trình minh họa năm phép tính riêng:

1. `bestAtMost`: tối đa lợi ích ba lô không giới hạn, **sức chứa ngoài**, lưu quyết định để **truy vết số lượng từng loại**.
2. `bestUnboundedItemFirst`: cùng mục tiêu, **loại vật ngoài, sức chứa tăng**; dùng để đối chiếu giá trị tối ưu.
3. `bestZeroOne`: ba lô 0/1, **loại vật ngoài, sức chứa giảm**.
4. `bestExactFill`: tối đa lợi ích nhưng **trọng lượng phải đúng C**, trả `OptionalLong.empty()` nếu không thể đạt.
5. `countCombinations` và `countOrderedSequences`: phân biệt **tổ hợp** với **trình tự chọn đồng**.

Tất cả vật có weight nguyên dương. Mã không sửa mảng đầu vào. Khi tái dựng ở `bestAtMost`, nếu ở sức chứa c không có lựa chọn nào làm tăng giá trị so với c−1, mảng `choice[c]` để −1 và giảm c đi một đơn vị. Nếu có một lựa chọn vật i thực sự cải thiện giá trị, giảm c đi weight[i], tăng số lượng i; vì các ô trước c đã tính xong và không thay đổi về sau trong thứ tự capacity-first, truy vết khôi phục đúng giá trị DP. Trường hợp hòa ưu tiên phương án hiện tại (không ghi đè decision), giúp stdout tái lập được.

Lưu thành **`UnboundedKnapsackUpdateOrder.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.OptionalLong;
import java.util.Set;

public class UnboundedKnapsackUpdateOrder {
    record Item(int weight, long value) {
        Item {
            if (weight <= 0) {
                throw new IllegalArgumentException(
                        "weight must be positive");
            }
        }
    }

    record Solution(long maximumValue,
                    int usedWeight,
                    int[] quantities) {}

    private static void checkItems(Item[] items, int capacity) {
        Objects.requireNonNull(items, "items must not be null");
        if (capacity < 0) {
            throw new IllegalArgumentException(
                    "capacity must be nonnegative");
        }
        if (capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "capacity too large for dense DP");
        }
        for (Item item : items) {
            Objects.requireNonNull(item, "item must not be null");
        }
    }

    // Khong gioi han, tong weight <= capacity.
    // Capacity ngoai: truy vet an toan bang choice[c].
    static Solution bestAtMost(Item[] items, int capacity) {
        checkItems(items, capacity);
        long[] dp = new long[capacity + 1];
        int[] choice = new int[capacity + 1];
        Arrays.fill(choice, -1);

        for (int c = 1; c <= capacity; c++) {
            dp[c] = dp[c - 1]; // Cho phep de du suc chua
            for (int i = 0; i < items.length; i++) {
                Item item = items[i];
                if (item.weight() <= c) {
                    long candidate = Math.addExact(
                            dp[c - item.weight()], item.value());
                    if (candidate > dp[c]) {
                        dp[c] = candidate;
                        choice[c] = i;
                    }
                }
            }
        }

        int[] quantities = new int[items.length];
        int usedWeight = 0;
        int c = capacity;

        while (c > 0) {
            int i = choice[c];
            if (i < 0) {
                c--; // Doan nay khong can dung het c
            } else {
                quantities[i]++;
                usedWeight += items[i].weight();
                c -= items[i].weight();
            }
        }
        return new Solution(dp[capacity], usedWeight, quantities);
    }

    // Khong gioi han: vat ngoai, capacity TANG.
    static long bestUnboundedItemFirst(Item[] items, int capacity) {
        checkItems(items, capacity);
        long[] dp = new long[capacity + 1];
        for (Item item : items) {
            for (int c = item.weight(); c <= capacity; c++) {
                long candidate = Math.addExact(
                        dp[c - item.weight()], item.value());
                if (candidate > dp[c]) {
                    dp[c] = candidate;
                }
            }
        }
        return dp[capacity];
    }

    // 0/1: vat ngoai, capacity GIAM.
    static long bestZeroOne(Item[] items, int capacity) {
        checkItems(items, capacity);
        long[] dp = new long[capacity + 1];
        for (Item item : items) {
            for (int c = capacity; c >= item.weight(); c--) {
                long candidate = Math.addExact(
                        dp[c - item.weight()], item.value());
                if (candidate > dp[c]) {
                    dp[c] = candidate;
                }
            }
        }
        return dp[capacity];
    }

    // Khong gioi han: tong weight PHAI bang capacity.
    static OptionalLong bestExactFill(Item[] items, int capacity) {
        checkItems(items, capacity);
        long[] best = new long[capacity + 1];
        boolean[] reachable = new boolean[capacity + 1];
        reachable[0] = true;

        for (int c = 1; c <= capacity; c++) {
            for (Item item : items) {
                int w = item.weight();
                if (w <= c && reachable[c - w]) {
                    long candidate = Math.addExact(
                            best[c - w], item.value());
                    if (!reachable[c] || candidate > best[c]) {
                        reachable[c] = true;
                        best[c] = candidate;
                    }
                }
            }
        }
        return reachable[capacity]
                ? OptionalLong.of(best[capacity])
                : OptionalLong.empty();
    }

    private static void checkCoins(int[] coins, int target) {
        Objects.requireNonNull(coins, "coins must not be null");
        if (target < 0) {
            throw new IllegalArgumentException(
                    "target must be nonnegative");
        }
        if (target == Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "target too large for dense DP");
        }

        Set<Integer> seen = new HashSet<>();
        for (int coin : coins) {
            if (coin <= 0) {
                throw new IllegalArgumentException(
                        "coin must be positive");
            }
            if (!seen.add(coin)) {
                throw new IllegalArgumentException(
                        "duplicate denomination: " + coin);
            }
        }
    }

    // Dem TO HOP: khong phan biet thu tu cac dong.
    static long countCombinations(int[] coins, int target) {
        checkCoins(coins, target);
        long[] ways = new long[target + 1];
        ways[0] = 1;

        for (int coin : coins) {
            for (int sum = coin; sum <= target; sum++) {
                ways[sum] = Math.addExact(
                        ways[sum], ways[sum - coin]);
            }
        }
        return ways[target];
    }

    // Dem DAY CO THU TU: 1+3 khac 3+1.
    static long countOrderedSequences(int[] coins, int target) {
        checkCoins(coins, target);
        long[] ways = new long[target + 1];
        ways[0] = 1;

        for (int sum = 1; sum <= target; sum++) {
            for (int coin : coins) {
                if (coin <= sum) {
                    ways[sum] = Math.addExact(
                            ways[sum], ways[sum - coin]);
                }
            }
        }
        return ways[target];
    }

    private static String exactString(OptionalLong result) {
        return result.isPresent()
                ? Long.toString(result.getAsLong())
                : "impossible";
    }

    private static void show(
            String label, Item[] items, int capacity) {
        Solution answer = bestAtMost(items, capacity);
        System.out.println(label
                + ": value=" + answer.maximumValue()
                + ", used=" + answer.usedWeight()
                + ", counts=" + Arrays.toString(answer.quantities()));
    }

    public static void main(String[] args) {
        Item[] main = {new Item(2, 3), new Item(3, 4)};
        Item[] alternate = {new Item(4, 8), new Item(6, 11)};
        Item[] negative = {new Item(2, -2), new Item(3, -1)};

        show("Main C7", main, 7);
        show("Main C6", main, 6);
        show("Small C1", main, 1);
        System.out.println("Item-first C7: "
                + bestUnboundedItemFirst(main, 7));
        System.out.println("Zero-one C7: "
                + bestZeroOne(main, 7));

        show("At-most C7", alternate, 7);
        System.out.println("Exact C7: "
                + exactString(bestExactFill(alternate, 7)));
        System.out.println("Exact C8: "
                + exactString(bestExactFill(alternate, 8)));

        show("Negative at-most C5", negative, 5);
        System.out.println("Negative exact C5: "
                + exactString(bestExactFill(negative, 5)));

        int[] coins = {1, 2, 3};
        System.out.println("Combinations sum4: "
                + countCombinations(coins, 4));
        System.out.println("Ordered sum4: "
                + countOrderedSequences(coins, 4));
        System.out.println("Combinations sum0: "
                + countCombinations(coins, 0));
        System.out.println("Impossible sum5: "
                + countCombinations(new int[]{2, 4}, 5));

        show("No items C0", new Item[0], 0);

        try {
            new Item(0, 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid item: " + ex.getMessage());
        }

        try {
            countCombinations(new int[]{1, 1, 2}, 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid coins: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac UnboundedKnapsackUpdateOrder.java
java UnboundedKnapsackUpdateOrder
```

**Stdout chính xác:**

```text
Main C7: value=10, used=7, counts=[2, 1]
Main C6: value=9, used=6, counts=[3, 0]
Small C1: value=0, used=0, counts=[0, 0]
Item-first C7: 10
Zero-one C7: 7
At-most C7: value=11, used=6, counts=[0, 1]
Exact C7: impossible
Exact C8: 16
Negative at-most C5: value=0, used=0, counts=[0, 0]
Negative exact C5: -3
Combinations sum4: 4
Ordered sum4: 7
Combinations sum0: 1
Impossible sum5: 0
No items C0: value=0, used=0, counts=[]
Invalid item: weight must be positive
Invalid coins: duplicate denomination: 1
```

### Giải thích các test

- **Main C7:** Hai A và một B tốn đúng 7, lợi ích 10. Cả capacity-first và item-first tăng đều cho 10.
- **Main C6:** Ba A có trọng lượng 6, lợi ích 9; hai B chỉ được 8, nên chọn ba A.
- **Small C1:** Không vật nào nặng ≤1; bài at-most được phép chọn rỗng.
- **Zero-one C7:** Chỉ có đúng một A và một B, tổng giá trị 7, minh họa khác biệt với unbounded.
- **At-most C7:** Lấy vật nặng 6 lợi ích 11, còn dư 1; không có nghiệm lấp đúng 7 trong các loại nặng 4/6.
- **Exact C8:** Hai vật trọng lượng 4, giá trị 8 mỗi vật tạo đúng 8 và lợi ích 16.
- **Negative at-most:** Vật có lợi ích âm làm giảm tổng lợi ích, nên chọn rỗng đạt 0. **Negative exact:** Muốn đúng trọng lượng 5 phải lấy một vật nặng 2 và một vật nặng 3, tổng lợi ích **−3**; không được dùng 0 làm sentinel của trường hợp không thể đạt.
- **Combinations/Ordered:** Cùng mệnh giá [1,2,3] và tổng 4 nhưng đếm 4 tổ hợp so với 7 trình tự; đó là **hai bài toán đếm khác nhau**, không phải hai thuật toán cho cùng một đáp án.
- **Combinations sum0:** Một lựa chọn rỗng có tổng 0; **Impossible sum5:** Các mệnh giá 2 và 4 không thể ghép thành số lẻ 5.
- **No items C0:** Chọn rỗng hợp lệ cho mục tiêu at-most với capacity 0.
- **Invalid item/coins:** Mã chủ động từ chối trọng lượng 0 và mệnh giá trùng, tránh nghiệm vô hạn hoặc ý nghĩa đếm mơ hồ.

### Vì sao truy vết ở capacity-first không bị sai do cập nhật sau?

Trong mã `bestAtMost`, ta tính `dp[c]` theo thứ tự `c=1..C`. Một khi đã rời khỏi sức chứa c, **không còn phép cập nhật nào thay đổi dp[c] hoặc choice[c]**, vì các lượt sau chỉ viết ô có chỉ số lớn hơn. Nếu quyết định tại c là lấy vật i, `dp[c]` đã được tạo từ `dp[c-weight[i]]+value[i]`, trong đó `c-weight[i]<c` đã được tính cố định. Bởi vậy chuỗi quyết định `choice[c] -> choice[c-weight[i]]` thực sự tương ứng với một nghiệm đạt giá trị DP. Nếu chọn “carry” từ `dp[c-1]`, giảm c đi 1 và tiếp tục. Cả hai chuyển đều đi tới sức chứa nhỏ hơn, bảo đảm kết thúc.

Trong dạng **item-first**, lời giải tối ưu về giá trị vẫn đúng; nhưng một mảng `choice[c]` đơn giản không phải lúc nào cũng đủ để truy vết nếu các ô tiền nhiệm có thể bị cập nhật trong **những giai đoạn loại vật khác nhau**. Khi cần tái dựng với item-first, phải thiết kế thêm thông tin giai đoạn hoặc parent nhất quán, hoặc dùng cách capacity-first như mã mẫu. Không nên cố gắn việc truy vết naïve vào một mảng DP dùng nhiều giai đoạn mà chưa chứng minh được nguồn của mỗi quyết định.

## 12. Các trường hợp biên cần kiểm tra

| Trường hợp | Điều cần bảo đảm |
| --- | --- |
| `C=0` | At-most và exact fill đều có nghiệm rỗng giá trị 0 (khi weight>0) |
| Danh sách vật rỗng, C>0 | At-most đạt 0; exact fill không thể đạt |
| Có vật nặng hơn C | Không được truy cập ô c−w âm; bỏ vật ấy trong các trạng thái không đủ sức chứa |
| Mọi lợi ích âm | At-most chọn rỗng (0); exact fill vẫn có thể phải chọn và cho kết quả âm |
| Vật weight=0, value>0 | Nếu không giới hạn số bản sao, tối đa **không bị chặn trên** |
| Vật weight=0, value≤0 | Có thể bỏ qua trong bài at-most; mã mẫu chọn **từ chối** để đảm bảo tiến triển |
| Vật weight<0 | Không hợp lệ trong mô hình tài nguyên tiêu hao không âm |
| Vật weight=1 | Có thể lặp đến C bản sao; xác thực chi phí/bộ nhớ |
| Hai loại có cùng weight/value | Vẫn là hai loại độc lập nếu input định nghĩa như vậy; không ảnh hưởng giá trị tối đa |
| Mệnh giá trùng trong bài **đếm cách** | Phải phân biệt loại bằng ID hoặc loại trùng; mã mẫu từ chối để không đếm sai |
| Tổng số cách quá lớn | Dùng BigInteger hoặc modulo; long có giới hạn |
| Không thể đạt exact fill | Trả trạng thái không đạt (ví dụ OptionalLong.empty), **không trả 0 tùy tiện** |
| C cực lớn | DP O(mC), bộ nhớ O(C); có thể không khả thi |
| Tổng value quá lớn | Math.addExact phát hiện tràn long |
| Muốn lấy ít vật nhất khi có nhiều nghiệm tối ưu | Cần thêm tiêu chí hòa/DP phụ, không suy ra từ `max(value)` |

### Số lượng và thứ tự không tương đương

Kết quả mảng `quantities=[2,1]` nói rằng lấy hai A và một B. Nó **không lưu** thứ tự vật được đưa vào ba lô, bởi mục tiêu tổng giá trị chỉ phụ thuộc **đa tập**. Nếu bài toán nói rằng “vật A chỉ được lấy trước B” hoặc “không được lấy hai bản sao A liên tiếp”, phải thêm trạng thái mô tả những ràng buộc trình tự. Đây không còn là unbounded knapsack chuẩn.

## 13. Biến thể tài nguyên và cách chọn trạng thái

### 13.1. Sức chứa nhiều chiều

Nếu mỗi vật vừa tốn trọng lượng vừa tốn thời gian, trạng thái có thể là `dp[weight][time]`, hoặc hơn nữa. Cần đảm bảo mỗi chuyển giảm ít nhất một tài nguyên để tránh vòng phụ thuộc, và đếm số trạng thái bằng **tích các giới hạn**. Dùng kỹ thuật 1D của bài này cho ràng buộc hai tài nguyên có thể làm mất thông tin về khả năng tiếp diễn.

### 13.2. Vật hữu hạn số lượng

Nếu mỗi loại được lấy nhiều nhất k_i lần, kỹ thuật cập nhật tăng của unbounded cho phép lấy **quá k_i lần**, sai. Các chiến lược phù hợp gồm DP có chiều/biến biểu diễn số lượng đã dùng, phân rã số lượng thành nhóm 1,2,4,... để dùng 0/1 knapsack, hoặc tối ưu deque theo lớp đồng dư nếu phù hợp.

**Lưu ý phân rã nhị phân:** Tạo các nhóm giả với tổng trọng lượng/giá trị nhân theo số bản sao, rồi xử lý mỗi nhóm **0/1, duyệt sức chứa giảm**. Không xử lý các nhóm giả theo hướng tăng vì sẽ phá ràng buộc số lượng.

### 13.3. Tối thiểu số vật để ghép đúng tổng

Trong bài đổi tiền ít đồng nhất, trạng thái thường là `minCoins[s]`:

```text
minCoins[0] = 0
minCoins[s] = min(1 + minCoins[s-coin])
              trên các coin<=s có trạng thái trước đạt được
```

Những số tiền không ghép được phải giữ trạng thái **không thể đạt**. Đây là bài **min**, khác với `max(value)` hoặc **cộng số cách**. Thứ tự cập nhật có thể dùng sum tăng với coin trong, miễn là mỗi mệnh giá có thể dùng không giới hạn và công thức phụ thuộc tổng nhỏ hơn.

### 13.4. Đổi tiền có thứ tự nhưng coi các đồng trùng loại khác nhau?

Nếu cùng mệnh giá có các **nhãn/loại riêng** và đề phân biệt các nhãn, `[1a,1b]` có thể được xem là hai lựa chọn khác nhau ngay cả khi cả hai đều có giá trị tiền 1. Khi đó phải định nghĩa rõ “một cách” là chuỗi nhãn, tổ hợp nhãn, hay chỉ đa tập mệnh giá. Bộ đếm đúng phụ thuộc **định nghĩa đối tượng được đếm**, không chỉ do mã hai vòng.

### 13.5. Lợi ích không cộng tính

Nếu lấy hai bản sao cùng loại làm giảm lợi ích của bản sao thứ hai (*diminishing returns*), công thức `value[i] + dp[c-weight[i]]` không còn mô tả đúng. Có thể cần thêm số lượng từng loại hoặc hàm lợi ích phụ thuộc lựa chọn trước. Unbounded knapsack chuẩn giả định **mỗi bản sao đóng góp cùng một value[i]** và tổng lợi ích là tổng tuyến tính.

## 14. Những sai lầm thường gặp

1. **Duyệt sức chứa giảm khi cần không giới hạn.** Như vậy thường giải bài 0/1 vì một vật không được dùng lại trong cùng lượt.
2. **Duyệt tăng khi cần 0/1.** Có thể lấy một món nhiều lần trong cùng lượt; ví dụ A=(2,3), C=6 cho 9 thay vì 3.
3. **Không nói rõ `dp[c]` là at-most hay exact fill.** Khởi tạo khác nhau và mục tiêu có thể khác.
4. **Khởi tạo exact fill bằng 0 cho mọi c.** Biến những sức chứa không đạt được thành nghiệm giả.
5. **Cho phép weight=0 với value dương.** Nghiệm tối đa không hữu hạn, truy vết có thể không giảm sức chứa.
6. **Truy cập `dp[c-weight]` khi c<weight.** Chỉ cập nhật khi vật vừa với sức chứa.
7. **Dùng cùng một thứ tự vòng lặp cho mọi bài đếm.** Coin ngoài đếm tổ hợp; sum ngoài đếm trình tự, với các giả định đúng.
8. **Quên `ways[0]=1`.** Nếu bằng 0 thì mọi công thức đếm cách cộng từ trạng thái gốc đều ra 0.
9. **Đếm đồng xu 1 bị lặp trong input thành hai mệnh giá khác nhau vô tình.** Cần loại trùng hoặc định nghĩa có nhãn riêng.
10. **Cho rằng nhiều chuỗi khác nhau luôn là nhiều cách nếu đề hỏi tổ hợp.** `1+3` và `3+1` cùng một tổ hợp.
11. **Dùng `int` cho số cách lớn.** Có thể tràn rất sớm; thậm chí `long` cũng không đủ cho n/target lớn.
12. **Không xử lý lợi ích âm.** Với at-most, luôn có thể bỏ; với exact fill, nghiệm tối ưu có thể âm nên không dùng 0 làm giá trị mặc định đạt được.
13. **Trộn trạng thái tiền tố loại vật và trạng thái sức chứa.** Dùng quyết định của item-first để truy vết theo capacity mà không lưu đúng giai đoạn có thể tạo lịch sử không nhất quán.
14. **Quên trạng thái không thể đạt khi truy vết exact fill.** Mã minh họa chỉ trả giá trị tùy chọn, không tạo chuỗi lựa chọn cho trường hợp không thể đạt.
15. **Dùng 0/1 cập nhật giảm nhưng thêm đồ thị/counting khác mà không chứng minh.** Phải biết mỗi ô nguồn dp thuộc giai đoạn nào.
16. **Suy luận “max và sum đều như nhau về loop order”.** Mục tiêu tối đa đa tập không phân biệt thứ tự, còn đếm cách có thể phân biệt thứ tự rất rõ.
17. **Không xác thực sức chứa âm.** C không âm là một phần định nghĩa, truy cập mảng C+1 với C âm không có nghĩa.
18. **Bỏ qua giả đa thức.** O(mC) có thể quá lớn khi C được mã hóa ngắn nhưng giá trị rất lớn.
19. **Bỏ qua yêu cầu phải chọn ít nhất một vật.** Nếu bài yêu cầu không rỗng, base case at-most=0 và “lấy rỗng” có thể không hợp lệ; cần sửa DP.
20. **Quên rằng nhiều bản sao là cùng một loại.** Không được hiểu m món trong input là giới hạn m bản sao cho cả bài unbounded.
21. **Ghi đè vùng nhớ/trạng thái trước khi hiểu phụ thuộc.** Hướng duyệt là cách bảo vệ điều kiện giai đoạn, không phải thói quen thuần cú pháp.
22. **Sai kiểu số khi cộng lợi ích.** Tổng giá trị có thể vượt int; dùng long và cân nhắc overflow.
23. **Đánh đồng kết quả tối ưu với một phương án tối ưu duy nhất.** Có thể có nhiều cách chọn lượng vật cho cùng giá trị; chính sách hòa quyết định phương án được trả.
24. **Nhầm tiền “không đổi được” với “0 cách tạo 0”.** Với tổng 0 có một cách chọn rỗng, còn tổng không thể đạt có 0 cách.
25. **Cố tăng tốc bằng greedy mà chưa có chứng minh.** Chọn vật có tỷ lệ giá trị/trọng lượng cao nhất không luôn tối ưu cho ba lô nguyên không giới hạn do phần sức chứa thừa và tính rời rạc; DP giải bài chuẩn theo C.

## 15. Bài tập có đáp án

**Bài 1.** Chỉ có vật A=(w=2,v=3), sức chứa 6. Tối ưu ba lô không giới hạn và ba lô 0/1 khác nhau ra sao?

**Đáp án:** Không giới hạn: lấy 3 A, tổng trọng lượng 6, giá trị 9. 0/1: lấy tối đa 1 A, giá trị 3. Trong 1D item-first, duyệt c tăng cho unbounded và c giảm cho 0/1.

**Bài 2.** Vật A=(2,3), B=(3,4), C=7. Hãy tính A[0..7] cho bài at-most.

**Đáp án:** `[0,0,3,4,6,7,9,10]`. Sức chứa 7 đạt 10 bằng hai A và một B.

**Bài 3.** Vì sao item-first unbounded duyệt c tăng có thể lấy nhiều A trong một lượt?

**Đáp án:** Ở c=4, `dp[2]` đã chứa một A từ bước c=2 trong lượt xử lý A; cộng thêm A tạo hai bản sao. Ở c=6, lại dùng `dp[4]` để tạo ba A.

**Bài 4.** Với vật (4,8), (6,11), sức chứa 7, kết quả at-most và exact fill là gì?

**Đáp án:** At-most có giá trị 11, lấy vật nặng 6 và dư 1. Exact fill **không thể đạt** vì mọi tổng của 4 và 6 đều chẵn, không bằng 7.

**Bài 5.** Nếu bắt buộc ghép đúng 5 bằng vật (2,−2) và (3,−1), giá trị tối ưu là bao nhiêu? Nếu chỉ cần không vượt 5?

**Đáp án:** Exact fill phải lấy một mỗi loại, tổng lợi ích −3. At-most có thể chọn rỗng và đạt 0, lớn hơn mọi tổ hợp có lợi ích âm.

**Bài 6.** Với mệnh giá [1,2,3] và tổng 4, có bao nhiêu **tổ hợp** và bao nhiêu **trình tự có thứ tự**?

**Đáp án:** Tổ hợp **4**: 1+1+1+1, 1+1+2, 2+2, 1+3. Trình tự có thứ tự **7**, vì các thứ tự như 1+3 và 3+1 được tính riêng.

**Bài 7.** Tại sao `ways[0]` phải bằng 1 trong bài đếm cách?

**Đáp án:** Vì có một cách duy nhất tạo tổng 0: **không chọn đồng nào**. Đây là trạng thái xuất phát để sinh những cách tạo tổng dương; nếu để 0, sẽ không có cách nào được cộng lên.

**Bài 8.** Thay vòng sum tăng bằng sum giảm trong `for coin : coins` của đếm tổ hợp có tác động gì?

**Đáp án:** Nguồn `ways[sum-coin]` chưa được cập nhật bởi coin đang xét, nên mỗi coin chỉ có thể dùng một lần trong cùng lượt. Điều này đếm tổ hợp **0/1**, không phải tổ hợp tiền không giới hạn.

**Bài 9.** Có loại vật weight=0, value=5 và được chọn không giới hạn. Giá trị tối ưu at-most có hữu hạn không?

**Đáp án:** Không. Có thể chọn k bản sao mà không tốn sức chứa, nhận 5k, tăng không giới hạn khi k tăng. Một số trả về hữu hạn bất kỳ đều sai nếu không thay đổi điều kiện bài toán.

**Bài 10.** Bảng DP cần bao nhiêu ô nếu C=1000 trong dạng 1D? Độ phức tạp theo m loại?

**Đáp án:** Mảng chứa C+1=1001 ô (cộng mảng choice nếu truy vết); thời gian O(mC), bộ nhớ O(C) cho giá trị hoặc O(C+m) khi trả số lượng từng loại. Với C lớn, đây là giả đa thức.

**Bài 11.** Vì sao `Math.addExact` hợp lý trong ví dụ Java, và nó có bảo đảm kết quả đúng nếu giá trị vượt long không?

**Đáp án:** Math.addExact phát hiện tràn số và ném ArithmeticException thay vì âm thầm cho số sai. Nó **không** biểu diễn được kết quả vượt long; muốn tính chính xác trong trường hợp đó cần BigInteger hoặc kiểu số phù hợp.

**Bài 12.** Khi chỉ cần giá trị tối ưu unbounded at-most, có nên bắt buộc dùng mảng choice để truy vết không?

**Đáp án:** Không. Dùng một mảng dp O(C) là đủ. Chỉ giữ choice/parent khi đề yêu cầu phương án cụ thể, và phải bảo đảm lưu được quyết định tương ứng đúng với dữ liệu dp theo giai đoạn.

**Bài 13.** Nếu đề đếm số cách dùng đúng tổng với `coins=[1,1,2]` và coi hai mệnh giá 1 là **cùng một loại**, có thể đưa nguyên mảng vào vòng coin-first không?

**Đáp án:** Không. Hai lần xuất hiện của mệnh giá 1 làm thuật toán đếm như có hai loại 1 khác nhau, gây đếm trùng tổ hợp. Cần loại trùng mệnh giá hoặc thiết kế cách xử lý theo danh tính nếu đề phân biệt các đồng.

**Bài 14.** Một đề yêu cầu lấy **đúng một bản sao của từng vật**, không ít hơn và không nhiều hơn. Dùng unbounded knapsack được không?

**Đáp án:** Không. Số lượng đã bị cố định (mỗi loại đúng một) nên không còn quyền chọn số bản sao vô hạn; phải kiểm tra ràng buộc/tổng trực tiếp hoặc xây mô hình khác theo chính yêu cầu. Hướng duyệt tăng sẽ cho những phương án lặp vật vi phạm.

## Ghi nhớ

**Ba lô không giới hạn** cho phép lặp một loại vật bao nhiêu lần cũng được, với trọng lượng **nguyên dương** và tổng trọng lượng không vượt C (hoặc đúng C nếu đề yêu cầu). Trong 1D DP theo từng vật, **duyệt sức chứa tăng** cho phép tái sử dụng vật hiện tại; **duyệt giảm** thuộc bài **0/1**. Nếu duyệt sức chứa ngoài, các trạng thái `dp[c-w]` của sức chứa nhỏ hơn đã sẵn sàng và có thể dùng để truy vết ổn định. Phải phân biệt **at-most** (có thể chọn rỗng, giá trị ban đầu 0) với **exact fill** (sức chứa dương có thể không đạt). Trong bài **đếm tiền**, coin ngoài/sum tăng đếm **tổ hợp**, còn sum ngoài/coin trong đếm **trình tự có thứ tự**; cả hai dùng `ways[0]=1`. Hiểu **ý nghĩa trạng thái, phụ thuộc và hướng cập nhật** luôn quan trọng hơn việc học thuộc cú pháp vòng lặp.
