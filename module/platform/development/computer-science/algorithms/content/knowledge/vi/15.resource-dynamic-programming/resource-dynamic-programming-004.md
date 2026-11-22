# Đổi tiền với mục tiêu ít đồng nhất

## Mục tiêu học tập

Bài toán **đổi tiền với mục tiêu ít đồng nhất** được hiểu là: tạo đúng một số tiền mục tiêu bằng **số đồng tiền ít nhất**, chứ không phải tìm cách có ít loại mệnh giá nhất hay dùng các đồng có mệnh giá đồng nhất. Đây là một bài toán điển hình của **quy hoạch động tài nguyên**: mỗi đồng được chọn tiêu thụ một phần số tiền còn lại và có “chi phí” là một lần sử dụng đồng.

Sau bài này, bạn có thể:

1. Đặc tả bài toán **minimum coin change** chính xác: số tiền mục tiêu, danh sách mệnh giá, số lượng đồng không giới hạn hay có giới hạn, quy ước không thể đổi.
2. Nhận diện vì sao thuật toán **tham lam lấy đồng lớn nhất trước** không luôn tối ưu; tự xây phản ví dụ và hiểu khi nào một hệ mệnh giá đặc biệt cho phép tham lam.
3. Lập công thức quy hoạch động `dp[s]` cho **số đồng ít nhất để tạo đúng s**, chứng minh bằng **cấu trúc con tối ưu** và quy nạp theo số tiền.
4. Cài đặt **bottom-up DP `O(mA)`** với `m` loại mệnh giá và số tiền mục tiêu `A`, kể cả **khôi phục một phương án đổi tiền**.
5. Phân biệt đổi tiền **không giới hạn số đồng mỗi loại** và **giới hạn số lượng**; hiểu khi nào duyệt số tiền tăng hoặc giảm.
6. Xử lý biên: `A=0`, không có đồng, mệnh giá trùng, mệnh giá không dương, không đạt đúng mục tiêu, tràn số và số tiền rất lớn.
7. Phân biệt bài toán **ít đồng nhất** với **đếm số cách đổi tiền**, **chọn ít loại mệnh giá**, và các biến thể có phí/tài nguyên khác.
8. Viết và kiểm thử chương trình **Java 17+** chạy được, có đầu ra minh bạch và trường hợp phản ví dụ của tham lam.

## 1. Mô hình bài toán: “ít đồng nhất” nghĩa là gì?

Cho danh sách các mệnh giá nguyên dương:

\[
D=[d_1,d_2,\ldots,d_m],\qquad d_i>0,
\]

và một số tiền mục tiêu nguyên không âm `A`.

Trong phiên bản cơ bản, ta có **không giới hạn số đồng** của từng mệnh giá. Đặt `x_i` là số lần dùng đồng mệnh giá `d_i`. Ta cần:

\[
\sum_{i=1}^{m}x_i d_i=A,\qquad x_i\in\mathbb{Z}_{\ge0},
\]

và muốn **tối thiểu hóa**:

\[
\boxed{\sum_{i=1}^{m}x_i}.
\]

Mỗi đồng được sử dụng đóng góp **1** vào hàm mục tiêu, không phụ thuộc mệnh giá lớn hay nhỏ.

**Ví dụ:** với `D=[1,3,4]`, `A=6`:

- `4+1+1=6`, dùng **3 đồng**.
- `3+3=6`, dùng **2 đồng**.
- `1+1+1+1+1+1=6`, dùng **6 đồng**.

Đáp án tối ưu là **2 đồng**, phương án `[3,3]`.

### 1.1. Các điều kiện cần ghi rõ

| Thành phần | Hợp đồng ở phiên bản cơ bản |
| --- | --- |
| Mục tiêu | Đổi **đúng** số tiền `A` |
| Mệnh giá | Các số nguyên **dương**; không dùng 0 hoặc âm |
| Nguồn đồng | **Không giới hạn** số đồng mỗi loại, trừ khi đề nói khác |
| Hàm mục tiêu | Tổng **số đồng** được dùng là nhỏ nhất |
| Đáp án nếu không thể đổi đúng | Trả `-1` hoặc một trạng thái “không có nghiệm” được công bố |
| Số tiền bằng 0 | Dùng **0 đồng**, nghiệm rỗng |
| Mệnh giá bằng nhau | Trong bản không giới hạn, không làm thay đổi số đồng tối ưu |
| Thứ tự chọn đồng | Không ảnh hưởng số đồng tối ưu; nếu cần thứ tự đầu ra cụ thể phải định nghĩa riêng |

**Không nên nhầm “ít đồng nhất” với “ít mệnh giá khác nhau nhất”.** Với `D=[1,3,4]` và `A=6`, một phương án dùng một loại mệnh giá duy nhất là `1+1+1+1+1+1`; nó dùng **một loại mệnh giá** nhưng tới **sáu đồng**. Bài toán đang học quan tâm **số đồng**, nên chọn `3+3`.

### 1.2. Các cách đặt vấn đề gần giống nhưng khác

- **Min coins, unlimited:** ít đồng nhất, dùng mỗi mệnh giá tùy ý nhiều lần.
- **Min coins, bounded:** mỗi mệnh giá chỉ có một số lượng đồng nhất định.
- **Count combinations:** đếm số bộ số lượng `(x_1,\ldots,x_m)` tạo ra `A`, không tối thiểu số đồng.
- **Count ordered sequences:** đếm chuỗi chọn đồng, có thể coi `[1,3]` và `[3,1]` là hai cách khác nhau.
- **Minimum distinct denominations:** giảm số **loại mệnh giá** xuất hiện, không phải giảm tổng số đồng.
- **Minimum fee:** mỗi đồng hoặc giao dịch có một chi phí riêng; tối thiểu tổng phí có thể khác tối thiểu số đồng.

Muốn thiết kế DP đúng, trước tiên cần viết rõ **biến quyết định** và **hàm mục tiêu**.

## 2. Vì sao tham lam lấy đồng lớn nhất trước có thể sai?

Một ý tưởng quen thuộc là:

> Luôn chọn đồng có mệnh giá lớn nhất nhưng không vượt quá số tiền còn lại, rồi lặp đến khi đủ tiền.

Cách này dễ hiểu và có thể đúng trong **một số hệ mệnh giá đặc biệt**. Nhưng nó **không đúng với mọi danh sách mệnh giá**.

### 2.1. Phản ví dụ quan trọng

```text
Mệnh giá: [1, 3, 4]
Số tiền:  6
```

Tham lam:

```text
Ban đầu còn 6
Chọn 4 -> còn 2
Chọn 1 -> còn 1
Chọn 1 -> còn 0

Phương án tham lam: [4, 1, 1]
Tổng: 3 đồng
```

Nhưng:

```text
3 + 3 = 6
Phương án tối ưu: [3, 3]
Tổng: 2 đồng
```

Một quyết định có vẻ tốt **tại thời điểm hiện tại** (lấy đồng 4 lớn nhất) lại làm phần dư 2 khó đổi ngắn gọn. Hai đồng 3 cho kết quả tốt hơn.

### 2.2. Tham lam còn có thể báo “không đổi được” dù có nghiệm

Xét:

```text
Mệnh giá: [3, 4]
Số tiền:  6
```

Tham lam chọn 4 trước, còn 2; không có đồng 1 hoặc 2 nên **bị kẹt**. Nhưng vẫn tồn tại cách đổi `3+3=6` bằng 2 đồng.

Vì vậy với hệ mệnh giá bất kỳ, tham lam không chỉ có thể **tốn nhiều đồng hơn** mà còn có thể **bỏ lỡ nghiệm hợp lệ**.

### 2.3. Khi nào tham lam có thể đúng?

Có những **hệ mệnh giá chuẩn tắc** (*canonical coin systems*) mà quy tắc tham lam luôn tối ưu cho mọi số tiền có thể đổi. Ví dụ hệ các lũy thừa của 2:

```text
[1, 2, 4, 8, 16, ...]
```

Với các đồng lũy thừa 2, nếu một nghiệm có **hai đồng cùng mệnh giá `2^j`** trong khi đồng `2^{j+1}` tồn tại, thay hai đồng đó bằng một đồng lớn hơn vẫn giữ tổng tiền nhưng **giảm số đồng**. Lập luận đổi chỗ này giúp giải thích quy tắc tham lam cho hệ đặc biệt ấy.

Tuy nhiên:

- Có đồng mệnh giá 1 **không có nghĩa** tham lam luôn tối ưu: `[1,3,4]` là phản ví dụ.
- Mệnh giá “trông giống tiền thật” **không đủ** để chứng minh tham lam đúng.
- Nếu đề bài **không bảo đảm** một cấu trúc đặc biệt, nên dùng DP hoặc một thuật toán có chứng minh phù hợp.

**Bài học về tư duy:** lựa chọn tham lam cần **greedy-choice property** được chứng minh riêng cho hệ mệnh giá, còn DP xây nghiệm tối ưu từ mọi lựa chọn hợp lệ.

## 3. Trạng thái quy hoạch động cho số đồng ít nhất

Đặt:

\[
dp[s]=\text{số đồng ít nhất để tạo đúng số tiền }s.
\]

Nếu số tiền `s` không thể tạo, quy ước:

\[
dp[s]=+\infty.
\]

Với không giới hạn số đồng:

\[
dp[0]=0.
\]

Với `s>0`:

\[
\boxed{
dp[s]=1+\min_{\substack{d\in D\\d\le s\\dp[s-d]<+\infty}}dp[s-d]
}
\]

Nếu không có mệnh giá nào tạo được trạng thái trước đó, `dp[s]=+\infty`.

Có thể viết dưới dạng lựa chọn **đồng cuối cùng**: giả sử một cách đổi tối ưu cho s sử dụng đồng cuối cùng mệnh giá d. Bỏ đồng đó, phần còn lại tạo đúng `s-d` và phải tối ưu; nếu không, thay phần còn lại bằng một phương án tốt hơn sẽ giảm tổng số đồng, mâu thuẫn với tính tối ưu.

Vì thế, ta chỉ cần thử **tất cả mệnh giá d có thể làm đồng cuối**.

### 3.1. Cơ sở và kết quả

- `dp[0]=0` vì đổi số tiền 0 không cần đồng nào.
- Với `s>0` và không tìm được cách tạo, giữ `dp[s]=INF`.
- Kết quả cho `A` là `dp[A]` nếu hữu hạn; nếu vẫn `INF`, trả `-1`.

Đặc biệt, nếu `D=[]`:

- Với `A=0`: kết quả 0.
- Với `A>0`: không có nghiệm, trả -1.

Không tự cho rằng `dp[s]` luôn hữu hạn nếu không có mệnh giá 1.

### 3.2. Tại sao cần mệnh giá dương?

Điều kiện `d>0` bảo đảm `s-d<s`. Khi tính `dp[s]`, mọi trạng thái phụ thuộc đã được tính ở các số tiền **nhỏ hơn**.

Nếu cho phép đồng mệnh giá 0, việc chọn đồng đó không giúp tiến tới mục tiêu nhưng vẫn tăng số đồng; nếu cho phép mệnh giá âm, phụ thuộc có thể đi tới số tiền lớn hơn và không còn khớp thứ tự xử lý `0..A`.

Vì vậy bản DP này **yêu cầu mọi mệnh giá là số nguyên dương**. Nếu nghiệp vụ có khoản hoàn tiền hoặc giao dịch âm, đó là mô hình khác và cần thuật toán/giới hạn riêng.

## 4. Quy hoạch động bottom-up

Ta tính `dp[0],dp[1],\ldots,dp[A]` theo thứ tự số tiền tăng dần.

```text
MIN_COINS_UNLIMITED(denominations, A):
    yêu cầu: A >= 0; mọi d thuộc denominations đều > 0

    tạo dp[0..A], ban đầu toàn INF
    dp[0] = 0

    for sum từ 1 đến A:
        for mỗi coin trong denominations:
            if coin <= sum và dp[sum-coin] != INF:
                dp[sum] = min(
                    dp[sum],
                    dp[sum-coin] + 1
                )

    if dp[A] == INF:
        return -1

    return dp[A]
```

**Tư duy:** tại số tiền `sum`, thử đặt mỗi đồng `coin` ở cuối nghiệm. Vì `coin>0`, bài toán nhỏ hơn là `sum-coin` đã được giải. Chọn số đồng ít nhất trong các ứng viên.

### 4.1. Ví dụ từng trạng thái cho [1,3,4], A=6

| Số tiền s | Các cách tạo tốt nhất đã xét | `dp[s]` |
| ---: | --- | ---: |
| 0 | Không chọn đồng | 0 |
| 1 | `1` | 1 |
| 2 | `1+1` | 2 |
| 3 | `3` | 1 |
| 4 | `4` | 1 |
| 5 | `4+1` | 2 |
| 6 | `3+3` | **2** |

Mảng kết quả:

```text
s:     0  1  2  3  4  5  6
dp[s]: 0  1  2  1  1  2  2
```

Ở `s=6`:

- Nếu đồng cuối là 1: `dp[5]+1=2+1=3`.
- Nếu đồng cuối là 3: `dp[3]+1=1+1=2`.
- Nếu đồng cuối là 4: `dp[2]+1=2+1=3`.

Do đó `dp[6]=2`. Phản ví dụ tham lam được giải đúng bởi DP vì thuật toán **so sánh các lựa chọn đồng cuối**, thay vì cố định đồng lớn nhất trước.

### 4.2. Trạng thái không thể đạt

Với mệnh giá `[4,6]` và mục tiêu `A=8`:

```text
dp[0] = 0
dp[1],dp[2],dp[3] = INF
dp[4] = 1    (4)
dp[5] = INF
dp[6] = 1    (6)
dp[7] = INF
dp[8] = 2    (4+4)
```

Nếu mục tiêu là `2` hoặc `7`, không có nghiệm. Không được suy rằng số đồng bằng 0 hay 1 chỉ vì vòng lặp không tìm được cách cập nhật; **0 chỉ là đáp án cho số tiền 0**.

## 5. Chứng minh DP tính số đồng tối ưu

### 5.1. Bất biến khi tính theo số tiền

Trước khi bắt đầu tính `dp[s]`, mọi `dp[t]` với `0≤t<s` đã bằng số đồng ít nhất để tạo đúng t, hoặc bằng `INF` nếu t không đạt được.

**Khởi tạo:** `dp[0]=0` đúng vì không chọn đồng là cách duy nhất cần xét để tạo số tiền 0 với số đồng ít nhất.

**Duy trì:** xét số tiền `s>0`.

- Mọi nghiệm hợp lệ cho s phải có ít nhất một đồng cuối cùng d trong D.
- Bỏ đồng cuối đó sẽ còn một nghiệm hợp lệ cho `s-d`, với `s-d<s` vì d dương.
- Theo giả thiết quy nạp, số đồng ít nhất cho phần dư là `dp[s-d]`.
- Vậy một nghiệm dùng đồng cuối d cần ít nhất `dp[s-d]+1` đồng; nếu trạng thái phần dư đạt được, ta xây được chính một nghiệm với số đồng ấy.
- Lấy min trên mọi d là đủ để xét tất cả dạng đồng cuối có thể có.

Nếu không có trạng thái `dp[s-d]` hữu hạn, sẽ không thể tạo s; giữ `INF` là đúng.

Do đó sau bước s, `dp[s]` chính xác. Quy nạp đến `s=A` cho đáp án tối ưu.

### 5.2. Tính dừng

Có đúng `A` vòng lặp số tiền dương và mỗi vòng xét hữu hạn `m` loại đồng. Chỉ số `s` tăng tới `A` rồi dừng; điều kiện `d>0` khiến công thức không tham chiếu ngược vào cùng trạng thái hay trạng thái tương lai.

### 5.3. Vì sao không cần duyệt thứ tự các đồng?

Bài toán yêu cầu **tổng số đồng nhỏ nhất**, không quan tâm thứ tự lấy đồng. Một nghiệm `[3,1,3]` và `[1,3,3]` có cùng số tiền, cùng số đồng và tương đương về mục tiêu. Công thức xét đồng cuối không có nghĩa mọi hoán vị phải được liệt kê; nó chỉ cần lấy giá trị tối ưu của phần dư.

Nếu bài toán đếm **chuỗi có thứ tự**, việc đếm hoán vị sẽ quan trọng. Nhưng đó là một mục tiêu khác, không phải công thức min ở đây.

## 6. Khôi phục một cách đổi tối ưu

Nếu đề chỉ hỏi **số đồng**, mảng `dp` là đủ. Nhưng nếu cần biết **các đồng thực sự dùng**, ta lưu thêm:

```text
lastCoin[s] = một mệnh giá c được chọn làm đồng cuối
              khi dp[s] đạt giá trị tốt nhất
```

Khi tìm thấy ứng viên làm giảm `dp[s]`:

```text
dp[s] = dp[s-c] + 1
lastCoin[s] = c
```

Sau khi tính xong:

```text
if dp[A] == INF:
    không có nghiệm
else:
    remaining = A
    chosen = []

    while remaining > 0:
        c = lastCoin[remaining]
        append c to chosen
        remaining -= c

    return chosen
```

### 6.1. Bất biến truy vết

Nếu `lastCoin[s]=c`, ta có:

\[
dp[s]=dp[s-c]+1,
\]

với `c>0`. Từ `s=A`, mỗi bước trừ một mệnh giá dương nên `remaining` giảm nghiêm ngặt và không thể lặp vô hạn.

Độ dài của mảng kết quả đúng bằng `dp[A]`, và tổng giá trị các đồng bằng A, vì bước truy vết cuối cùng kết thúc tại `remaining=0`.

### 6.2. Ví dụ

Với `D=[1,3,4]`, `A=6`:

```text
dp[6] = 2
lastCoin[6] = 3

remaining 6 -> chọn 3 -> còn 3
remaining 3 -> chọn 3 -> còn 0

chosen = [3, 3]
```

Nếu có **nhiều phương án tối ưu**, cách cập nhật mảng `lastCoin` khi bằng nhau sẽ quyết định phương án được khôi phục. Ví dụ nếu vòng lặp mệnh giá có thứ tự cố định và chỉ cập nhật khi số đồng **nhỏ hơn nghiêm ngặt** (`candidate < dp[s]`), phương án thắng đầu tiên được giữ.

**Không tự suy rằng đó là phương án từ điển nhỏ nhất, nhiều đồng lớn nhất, hoặc ổn định theo thứ tự input.** Những yêu cầu phụ ấy cần một quy tắc so sánh và chứng minh riêng.

## 7. Phân tích độ phức tạp

Gọi:

- `A` là số tiền mục tiêu.
- `m` là số loại mệnh giá trong input.
- Mọi mệnh giá đều là số nguyên dương.

Mỗi số tiền từ 1 đến A xét m đồng:

\[
T(A,m)=O(A\cdot m).
\]

Mảng `dp` có `A+1` ô, nên chi phí bộ nhớ:

\[
S(A)=O(A).
\]

Nếu lưu thêm `lastCoin` để khôi phục, bộ nhớ vẫn `O(A)`. Truy vết chọn ra k đồng mất `O(k)` thời gian và `O(k)` không gian kết quả; do mỗi đồng có mệnh giá ít nhất 1, với A>0 ta có `k≤A`.

### 7.1. Tại sao gọi là giả đa thức (pseudo-polynomial)?

Giả sử `A=1,000,000,000`. Số này chỉ cần khoảng 30 bit để biểu diễn dưới dạng nhị phân, nhưng DP trực tiếp cần tới **một tỷ trạng thái**. Thời gian `O(mA)` là đa thức theo **giá trị số A**, không phải đa thức theo **số bit biểu diễn A**.

Vì vậy thuật toán được gọi là **giả đa thức**, không phải một thuật toán đa thức mạnh theo kích thước đầu vào ở dạng nhị phân.

Hậu quả thực tế:

- Dễ áp dụng khi A tương đối nhỏ và m vừa phải.
- Rất tốn RAM/thời gian nếu A cực lớn, dù danh sách mệnh giá có ít phần tử.
- Khi A lớn và có cấu trúc mệnh giá đặc biệt, nên khảo sát các thuật toán/biến đổi khác thay vì cấp phát mảng A+1 phần tử.

### 7.2. Nếu số lượng mệnh giá rất lớn

Trong bản không giới hạn, có thể **loại mệnh giá trùng** vì việc lặp cùng một loại không thay đổi tập nghiệm hoặc số đồng tối ưu. Có thể bỏ các mệnh giá `d>A` với bài toán mục tiêu cố định A vì chúng không thể xuất hiện trong nghiệm có tổng đúng A.

Sắp xếp mệnh giá không phải điều kiện để DP đúng; nó chủ yếu phục vụ loại trùng, tối ưu nhỏ hoặc cố định chính sách hòa.

### 7.3. Giảm bài toán bằng ước chung lớn nhất

Gọi `g=gcd(d_1,\ldots,d_m)`. Mọi tổng tạo được từ các mệnh giá đều chia hết cho g. Vậy nếu `A` không chia hết cho g, chắc chắn **không có nghiệm**.

Ví dụ `D=[4,6]` có `g=2`. Mục tiêu 7 lẻ nên không thể đổi.

Nếu `g` chia hết A, ta có thể chia **tất cả mệnh giá và A** cho g mà không thay đổi số đồng tối ưu. Ví dụ:

```text
D = [4,6], A = 8
g = 2
Bài toán rút gọn: D' = [2,3], A' = 4
Nghiệm: [2,2] trong đơn vị rút gọn
Tương ứng: [4,4] trong đơn vị ban đầu
```

**Nhưng điều kiện `g|A` chỉ là điều kiện cần, không đủ**. Với `D=[4,6]`, `A=2` cũng chia hết cho g=2 nhưng không tạo được 2. Không được trả “có nghiệm” chỉ dựa trên phép kiểm tra gcd.

Khi không có mệnh giá nào, không định nghĩa phép chia toàn bộ mệnh giá theo cách này; xử lý `A=0` hoặc không có nghiệm trực tiếp.

## 8. Phân biệt “không giới hạn” với “có giới hạn số đồng”

Đây là một khác biệt rất quan trọng trong các bài DP tài nguyên.

### 8.1. Không giới hạn (*unbounded coin change*)

Mỗi mệnh giá có thể dùng tùy ý nhiều lần. Công thức:

\[
dp[s]=\min_{d\le s}(dp[s-d]+1).
\]

Khi duyệt số tiền `s` tăng dần, một trạng thái `dp[s-d]` có thể **đã dùng mệnh giá d trước đó**, nên việc tiếp tục thêm d là hợp lệ.

Với `D=[1,3,4]`, `A=6`, chọn `3+3` là hợp lệ vì có thể dùng hai đồng mệnh giá 3.

### 8.2. Có giới hạn (*bounded coin change*)

Giả sử mỗi loại đồng `d_i` chỉ có `count_i` đồng. Khi đó phải thêm điều kiện:

\[
0\le x_i\le count_i.
\]

Ví dụ:

```text
Mệnh giá: [1, 3, 4]
Số lượng: [2, 1, 1]
Số tiền:  6
```

Ở bản không giới hạn, `3+3` dùng 2 đồng là tối ưu. Nhưng nếu chỉ có **một đồng 3**, phương án đó **không hợp lệ**. Với nguồn đồng đã cho, nghiệm tốt nhất là:

```text
4 + 1 + 1 = 6
3 đồng
```

Bài toán **giới hạn số đồng** có cùng mục tiêu “ít đồng nhất” nhưng **miền lựa chọn khác nhau**. Không thể chạy bản unbounded rồi kiểm tra số lượng đồng ở cuối mà mong vẫn tìm được nghiệm tối ưu trong mọi trường hợp.

### 8.3. DP có giới hạn bằng các đồng vật lý riêng biệt

Một cách đơn giản là xem **mỗi đồng thực có** là một phần tử kiểu 0/1: mỗi đồng chỉ được chọn **một lần**.

Với mỗi đồng trị giá c, cập nhật số tiền **giảm dần**:

```text
for mỗi đồng thực c:
    for sum từ A giảm đến c:
        if dp[sum-c] có thể đạt:
            dp[sum] = min(dp[sum], dp[sum-c]+1)
```

**Vì sao phải giảm dần?** Nếu cập nhật `sum` tăng dần trong cùng lần xử lý một đồng, trạng thái mới từ chính đồng ấy có thể được dùng lại ngay cho `sum+c`, khiến một đồng vật lý được tính **nhiều lần**. Duyệt giảm dần buộc mỗi đồng chỉ tham gia **tối đa một lần** trong một lượt.

Với `N=\sum_i count_i` đồng vật lý, cách này tốn `O(AN)` thời gian và `O(A)` bộ nhớ nếu chỉ cần số đồng ít nhất.

### 8.4. Công thức theo từng loại mệnh giá

Một cách biểu diễn khác giúp thấy rõ giới hạn là:

\[
dp[i][s]
=\text{số đồng ít nhất tạo s khi chỉ dùng các loại }1..i.
\]

Với loại thứ i có mệnh giá `d_i` và số lượng `count_i`:

\[
dp[i][s]
=\min_{\substack{0\le t\le count_i\\td_i\le s}}
\left(dp[i-1][s-td_i]+t\right).
\]

Công thức này xét tất cả số lượng t hợp lệ của loại i. Nó dễ khôi phục nghiệm khi lưu quyết định t tại mỗi trạng thái, nhưng có thể tốn nhiều thời gian/bộ nhớ hơn 1D DP.

**Cảnh báo truy vết 1D cho bounded DP:** nếu lưu một mảng `lastCoin[s]` đơn giản trong lúc cập nhật 0/1 theo số tiền giảm dần, những trạng thái cha có thể bị thay ở các lượt sau. Truy ngược các cha mà không giữ thông tin **giai đoạn** có thể tạo nghiệm không hợp lệ (ví dụ dùng lại một đồng). Muốn khôi phục bounded nghiệm an toàn, dùng bảng trạng thái theo giai đoạn, snapshot/con trỏ bất biến, hoặc thiết kế truy vết có chứng minh riêng.

### 8.5. Tối ưu cho số lượng đồng lớn: binary splitting

Nếu một loại mệnh giá có rất nhiều đồng, lặp từng đồng vật lý có thể quá chậm. Có thể chia `count_i` thành các bó số lượng `1,2,4,\ldots` và một bó dư, mỗi bó đại diện cho một **lựa chọn 0/1**:

- Bó có q đồng mệnh giá d có **giá trị q·d**.
- Nếu chọn bó ấy, **chi phí số đồng là q**, không phải 1.
- Duyệt số tiền giảm dần theo mỗi bó, như 0/1 knapsack.

Số bó mỗi loại là `O(log(count_i+1))`, giảm thời gian từ `O(A\sum_i count_i)` xuống khoảng `O(A\sum_i\log(count_i+1))` nếu cài đúng, chưa kể chi phí tạo bó. Phải dùng kiểu số đủ rộng cho tích `q·d` và kiểm soát bó vượt mục tiêu A.

**Không nhầm:** gộp q đồng thành một bó không có nghĩa chỉ tính bó đó là **1 đồng**. Trong hàm mục tiêu, bó phải đóng góp **q đồng**.

## 9. Java 17+: chương trình hoàn chỉnh

Chương trình sau lưu vào tệp **`MinCoinsDemo.java`**. Nó minh họa:

- Tham lam để thấy phản ví dụ, **không tuyên bố tham lam luôn tối ưu**.
- DP không giới hạn với mảng `dp` và khôi phục danh sách đồng tối ưu.
- DP có giới hạn số lượng bằng cách xử lý từng đồng vật lý 0/1.
- Trường hợp không đổi được, số tiền 0 và danh sách mệnh giá rỗng.
- Kiểm tra đầu vào để tránh mệnh giá 0/âm và số tiền không hợp lệ.

```java
import java.util.Arrays;
import java.util.Objects;

public class MinCoinsDemo {

    record Change(int minCoins, int[] chosen, int[] table) {
    }

    private static void validate(int[] denoms, int amount) {
        Objects.requireNonNull(denoms, "denoms");

        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }

        // The array needs amount + 1 cells, and INF=amount+1.
        if (amount == Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "amount too large for array DP");
        }

        for (int coin : denoms) {
            if (coin <= 0) {
                throw new IllegalArgumentException(
                        "coin values must be positive");
            }
        }
    }

    // Greedy is NOT always optimal. For illustration only.
    static int greedyCount(int[] denoms, int amount) {
        validate(denoms, amount);

        int[] sorted = denoms.clone();
        Arrays.sort(sorted);

        int remaining = amount;
        int used = 0;

        for (int i = sorted.length - 1; i >= 0; i--) {
            int take = remaining / sorted[i];
            used += take;
            remaining -= take * sorted[i];
        }

        return remaining == 0 ? used : -1;
    }

    // Unlimited quantity of each denomination.
    static Change minUnlimited(int[] denoms, int amount) {
        validate(denoms, amount);

        int INF = amount + 1;
        int[] dp = new int[amount + 1];
        int[] lastCoin = new int[amount + 1];

        Arrays.fill(dp, INF);
        dp[0] = 0;

        for (int sum = 1; sum <= amount; sum++) {
            for (int coin : denoms) {
                if (coin <= sum && dp[sum - coin] != INF) {
                    int candidate = dp[sum - coin] + 1;

                    if (candidate < dp[sum]) {
                        dp[sum] = candidate;
                        lastCoin[sum] = coin;
                    }
                }
            }
        }

        if (dp[amount] == INF) {
            return new Change(-1, new int[0], dp);
        }

        int[] chosen = new int[dp[amount]];
        int remaining = amount;

        for (int i = 0; i < chosen.length; i++) {
            int coin = lastCoin[remaining];
            chosen[i] = coin;
            remaining -= coin;
        }

        return new Change(dp[amount], chosen, dp);
    }

    // Bounded quantities. Each physical coin may be used once.
    // Returns the minimum count, or -1 if exact change is impossible.
    static int minBounded(
            int[] denoms, int[] counts, int amount) {

        validate(denoms, amount);
        Objects.requireNonNull(counts, "counts");

        if (denoms.length != counts.length) {
            throw new IllegalArgumentException(
                    "denominations/counts length mismatch");
        }

        int INF = amount + 1;
        int[] dp = new int[amount + 1];
        Arrays.fill(dp, INF);
        dp[0] = 0;

        for (int type = 0; type < denoms.length; type++) {
            if (counts[type] < 0) {
                throw new IllegalArgumentException(
                        "negative coin count");
            }

            int coin = denoms[type];

            // No exact solution needs more than amount/coin
            // physical coins of this denomination.
            int usable = Math.min(
                    counts[type], amount / coin);

            for (int copy = 0; copy < usable; copy++) {
                // Descending to avoid reusing this same coin.
                for (int sum = amount; sum >= coin; sum--) {
                    if (dp[sum - coin] != INF) {
                        dp[sum] = Math.min(
                                dp[sum],
                                dp[sum - coin] + 1);
                    }
                }
            }
        }

        return dp[amount] == INF ? -1 : dp[amount];
    }

    public static void main(String[] args) {
        int[] denoms = {1, 3, 4};
        int amount = 6;

        Change optimal = minUnlimited(denoms, amount);

        System.out.println("Denominations: "
                + Arrays.toString(denoms));
        System.out.println("Target: " + amount);
        System.out.println("Greedy count: "
                + greedyCount(denoms, amount));
        System.out.println("DP minimum: "
                + optimal.minCoins());
        System.out.println("DP coins: "
                + Arrays.toString(optimal.chosen()));
        System.out.println("DP table 0..6: "
                + Arrays.toString(optimal.table()));

        System.out.println("Unlimited [4, 6], amount 2: "
                + minUnlimited(new int[]{4, 6}, 2).minCoins());
        System.out.println("Unlimited [4, 6], amount 8: "
                + minUnlimited(new int[]{4, 6}, 8).minCoins());

        int[] counts = {2, 1, 1};
        System.out.println("Bounded counts [2, 1, 1], amount 6: "
                + minBounded(denoms, counts, 6));
        System.out.println("Bounded counts [2, 1, 1], amount 7: "
                + minBounded(denoms, counts, 7));

        System.out.println("Zero target: "
                + minUnlimited(denoms, 0).minCoins());
        System.out.println("Empty denominations, target 5: "
                + minUnlimited(new int[0], 5).minCoins());
    }
}
```

Chạy với JDK 17 hoặc mới hơn:

```bash
javac MinCoinsDemo.java
java MinCoinsDemo
```

**Đầu ra chuẩn chính xác:**

```text
Denominations: [1, 3, 4]
Target: 6
Greedy count: 3
DP minimum: 2
DP coins: [3, 3]
DP table 0..6: [0, 1, 2, 1, 1, 2, 2]
Unlimited [4, 6], amount 2: -1
Unlimited [4, 6], amount 8: 2
Bounded counts [2, 1, 1], amount 6: 3
Bounded counts [2, 1, 1], amount 7: 2
Zero target: 0
Empty denominations, target 5: -1
```

### 9.1. Giải thích những lựa chọn quan trọng

- `Change` là `record` Java, gom số đồng tối thiểu, một danh sách đồng được chọn và bảng DP minh họa. Record là tính năng chuẩn dùng được trên Java 17.
- `validate` từ chối số tiền âm, mệnh giá không dương và mảng `null`. Mảng mệnh giá rỗng **được phép** để biểu diễn trường hợp không có đồng.
- `amount == Integer.MAX_VALUE` bị từ chối vì không thể biểu diễn an toàn kích thước mảng `amount+1` bằng `int` hoặc sentinel `INF=amount+1`. **Dù A nhỏ hơn giá trị này**, mảng vẫn có thể không cấp phát được do giới hạn RAM; đây là giới hạn tài nguyên của DP theo số tiền.
- `INF=amount+1` lớn hơn mọi số đồng của một nghiệm hợp lệ, vì mỗi đồng có mệnh giá ít nhất 1 nên với mục tiêu A không thể dùng quá A đồng trong một nghiệm có tổng đúng A.
- `dp[0]=0`, còn các số tiền chưa biết cách tạo giữ giá trị `INF`.
- Nếu `dp[sum-coin]==INF`, không cộng 1 vào trạng thái đó; đây là bước chặn cần thiết để không dùng một trạng thái **không thể đạt** như nghiệm hợp lệ.
- Khi tìm được `candidate<dp[sum]`, ta cập nhật cả `dp` lẫn `lastCoin`. Nếu bằng nhau, mã giữ lựa chọn cũ; thứ tự liệt kê mệnh giá có thể ảnh hưởng **phương án xuất ra**, nhưng không làm sai **số đồng tối ưu**.
- Sau khi tính, mảng `chosen` được xây bằng cách lần ngược `lastCoin`. Các phần tử có thể không được sắp tăng/giảm vì thứ tự chọn đồng không phải yêu cầu.
- `greedyCount` sắp **bản sao** danh sách mệnh giá theo thứ tự tăng, sau đó duyệt giảm. Nó không thay đổi mảng đầu vào nhưng **không có bảo đảm tối ưu** cho mọi hệ mệnh giá.
- `minBounded` nhận số lượng đồng của từng loại, chỉ xử lý tối đa `min(count, amount/coin)` đồng vì nhiều hơn không thể được dùng trong nghiệm không âm có tổng A.
- Với mỗi **đồng vật lý**, vòng số tiền đi **giảm dần** để một đồng không thể bị sử dụng hai lần trong cùng lượt. Ở bản `minUnlimited`, vòng số tiền đi tăng vì được phép dùng lại mệnh giá.
- Số đồng được đếm theo từng **lần xuất hiện**, không phải số loại mệnh giá.

### 9.2. Những đảm bảo và giới hạn của ví dụ

Chương trình minh họa làm việc với số tiền và mệnh giá `int`. Không có việc dùng số thực để biểu diễn tiền. Trong hệ thống tài chính, nên biểu diễn tiền dưới dạng số nguyên ở **đơn vị nhỏ nhất** (ví dụ đồng, xu) hoặc dùng kiểu chính xác phù hợp khi có phần thập phân, tránh làm tròn bất ngờ của `double`.

Khi số tiền A quá lớn, việc tạo mảng `A+1` phần tử có thể không khả thi. Việc từ chối giá trị `Integer.MAX_VALUE` chỉ phòng một kiểu lỗi **tràn chỉ số**; không thay thế kiểm tra giới hạn RAM của hệ thống thực tế.

Các phương thức trả `-1` khi không có nghiệm, và trả `0` khi `A=0`. Đó là hợp đồng có chủ đích, không phải kết luận rằng một số tiền dương không đổi được thì dùng 0 đồng.

## 10. Kiểm thử bằng các nhóm đầu vào

Các trường hợp sau cần được xử lý rõ:

| Mệnh giá | Mục tiêu | Kết quả tối ưu (unlimited) | Giải thích |
| --- | ---: | ---: | --- |
| `[1,3,4]` | 6 | 2 | `3+3`; tham lam dùng 3 đồng |
| `[1]` | 7 | 7 | Bảy đồng 1 |
| `[2,5]` | 3 | -1 | Không tạo đúng 3 |
| `[4,6]` | 8 | 2 | `4+4` |
| `[4,6]` | 2 | -1 | gcd chia hết nhưng vẫn không có nghiệm |
| `[5,10]` | 0 | 0 | Nghiệm rỗng |
| `[]` | 0 | 0 | Không cần đồng |
| `[]` | 5 | -1 | Không có đồng nào |
| `[7,7,1]` | 14 | 2 | Hai đồng 7; loại trùng không đổi tối ưu |
| `[9,6,5,1]` | 11 | 2 | `6+5` |
| `[1,4,6]` | 8 | 2 | `4+4` |
| `[1,3,4]` | 2 | 2 | `1+1` |
| `[2]` | 7 | -1 | Không thể tạo số lẻ |
| `[2,3]` | 7 | 3 | `2+2+3` |

### 10.1. Kiểm tra một phương án khôi phục

Nếu hàm trả `minCoins=k` và danh sách `chosen`:

1. Nếu `k=-1`, phải tuyên bố **không có nghiệm**, không đưa một phương án giả.
2. Nếu `k≥0`, phải có `chosen.length==k`.
3. Mọi giá trị trong `chosen` phải thuộc danh sách mệnh giá hợp lệ.
4. Tổng các giá trị trong `chosen` phải bằng A; nên tính tổng bằng kiểu rộng để tránh tràn `int` trong kiểm thử.
5. Với bản bounded, số lần xuất hiện của từng mệnh giá trong phương án không được vượt quá số lượng có sẵn.
6. Giá trị k phải nhỏ nhất trong các cách đổi hợp lệ, không chỉ là một cách đổi đúng.

### 10.2. Oracle brute-force cho bài nhỏ

Với A và m nhỏ, có thể thử mọi lựa chọn số đồng hợp lệ hoặc dùng BFS trên các số tiền để kiểm chứng kết quả DP:

- Đồ thị có đỉnh `0,1,\ldots,A`.
- Với mỗi mệnh giá d và số tiền s, có cạnh `s→s+d` nếu `s+d≤A`.
- Mỗi cạnh có **chi phí bằng 1 đồng**.
- Đường đi ngắn nhất từ 0 đến A có số cạnh đúng bằng số đồng ít nhất.

BFS trên đồ thị này trả cùng số đồng tối ưu vì mọi cạnh có trọng số 1. Đây là cách kiểm thử độc lập và cũng là một cách nhìn hữu ích về DP.

Nếu đề có giới hạn số lượng đồng, chỉ có trạng thái `s` là chưa đủ để biểu diễn số đồng **còn lại của từng loại**; phải mở rộng trạng thái hoặc dùng cách giải bounded, không áp dụng BFS unlimited rồi gọi đó là bounded.

## 11. Nhìn bài toán như đường đi ngắn nhất

Ở phiên bản unlimited:

- Mỗi đỉnh biểu diễn số tiền đã tạo `s`.
- Mỗi cạnh ứng với việc thêm một đồng d, đi từ `s` đến `s+d`.
- Mỗi cạnh có **độ dài/chi phí 1**.
- Mục tiêu là đường đi ngắn nhất từ 0 tới A.

Vì `d>0`, mọi cạnh đều đi từ số tiền nhỏ hơn sang lớn hơn. Đồ thị có thứ tự tự nhiên `0,1,\ldots,A` và **không có chu trình có hướng**. Bottom-up DP thực chất là một phép tìm đường đi ngắn nhất trên đồ thị có thứ tự topo đó.

Có hai cách diễn giải tương đương:

\[
dp[s]=\min_{d\le s}(dp[s-d]+1)
\]

và:

\[
dp[s+d]=\min(dp[s+d],dp[s]+1).
\]

Cách thứ nhất “nhìn đồng cuối” và duyệt đích `s`. Cách thứ hai “thử thêm một đồng” từ một trạng thái đã đạt được. Vì mọi mệnh giá dương, thứ tự xử lý `s` tăng bảo đảm các cạnh tiến về phía trước.

**Liên hệ quan trọng:** một bài toán quy hoạch động đôi khi có thể được nhìn như bài toán đồ thị. Nhưng điều này **không có nghĩa** mọi biến thể đổi tiền đều giải bằng BFS trên chỉ một biến `s`. Giới hạn số lượng, phí biến đổi theo từng loại hoặc điều kiện thứ tự có thể đòi hỏi trạng thái rộng hơn.

### 11.1. BFS thay vì DP có tốt hơn không?

Khi tất cả cạnh có chi phí 1, BFS tìm số bước ít nhất trên đồ thị trạng thái. Với `A+1` trạng thái và tối đa `m` cạnh đi ra từ mỗi trạng thái, chặn tổng quát là `O(mA)` thời gian và `O(A)` bộ nhớ.

BFS có thể kết thúc sớm nếu gặp A ở một mức nhỏ, và dễ truy vết bằng parent của đỉnh số tiền. Bottom-up DP có ưu điểm thứ tự đơn giản, không cần hàng đợi, phù hợp khi cần tính nhiều số tiền từ 0 tới A.

Không nên kết luận BFS luôn nhanh hơn hoặc chậm hơn: hai cách giải cùng mô hình có thể khác nhau về số trạng thái thực tế phải duyệt và chi phí triển khai.

## 12. Phân biệt bài toán ít đồng với bài toán đếm số cách

Một nhầm lẫn rất phổ biến trong quy hoạch động đổi tiền là thay phép **min** bằng phép **cộng số cách** mà không thay đổi ý nghĩa trạng thái.

### 12.1. Ít đồng nhất

Hàm mục tiêu:

\[
\min\sum_i x_i.
\]

DP:

\[
dp[s]=\min_{d\le s}(dp[s-d]+1).
\]

Đáp án là **một số nguyên biểu thị số đồng tối thiểu**.

### 12.2. Đếm số tổ hợp (không phân biệt thứ tự)

Nếu hỏi có bao nhiêu cách dùng các mệnh giá không giới hạn sao cho tổng bằng A, và `[1,3]` tương đương `[3,1]`, có thể dùng:

```text
ways[0] = 1

for mỗi mệnh giá coin:
    for sum từ coin đến A:
        ways[sum] += ways[sum-coin]
```

Ở đây:

- `ways[s]` là **số cách**, không phải số đồng.
- Dùng phép **cộng**, không phải min.
- Vòng ngoài là **mệnh giá**, vòng trong số tiền **tăng**, để mỗi tổ hợp được đếm theo một thứ tự quy ước và cho phép dùng nhiều đồng cùng loại.
- Nếu mệnh giá trùng nhưng được xem là cùng một loại, phải loại trùng trước khi đếm; không được để lặp hai lần một mệnh giá và vô tình đếm lặp các tổ hợp.

Với `[1,3,4]`, `A=6`, bài “ít đồng nhất” trả `2`; bài “đếm số cách” trả một số cách tổ hợp khác. Hai bài có trạng thái và phép toán khác nhau dù cùng tổng mục tiêu A.

### 12.3. Đếm dãy có thứ tự

Nếu `[1,3]` và `[3,1]` được coi là hai chuỗi khác nhau, một công thức khác có thể là:

```text
ways[0] = 1

for sum từ 1 đến A:
    for mỗi coin có coin <= sum:
        ways[sum] += ways[sum-coin]
```

Thứ tự các vòng lặp quyết định **ý nghĩa đếm**. Không sao chép mã đếm số cách vào bài min coins mà bỏ qua khác biệt này.

### 12.4. Vấn đề tràn khi đếm

Số cách đổi tiền có thể tăng rất nhanh, vượt `int` hoặc `long`, trong khi số đồng tối thiểu cho A với mệnh giá dương luôn không lớn hơn A nếu có nghiệm. Các bài đếm thường cần modulo hoặc `BigInteger` theo đề bài; không tự áp dụng kiểu số và sentinel của bản min coins cho bài đếm.

## 13. Thay đổi mục tiêu: phí giao dịch, ít loại, trọng số

Giả sử một đồng mệnh giá d có **phí** `cost(d)` khác 1. Nếu mục tiêu là **tối thiểu tổng phí**, công thức đổi thành:

\[
dp[s]=\min_{d\le s}
\left(dp[s-d]+cost(d)\right),
\]

với điều kiện và mô hình phí rõ ràng (ví dụ phí không âm và lựa chọn đồng không phụ thuộc lịch sử).

Đó là một biến thể **minimum cost**, không nhất thiết trùng số đồng ít nhất. Nếu phí thay đổi theo số lần chọn, theo loại đồng đã sử dụng hoặc theo thứ tự giao dịch, phải bổ sung trạng thái tương ứng.

Nếu mục tiêu là **ít loại mệnh giá khác nhau**, không thể đơn giản thay `+1` bằng một biến khác trong `dp[s]` vì việc cộng thêm một đồng loại d có thể có phí **0 hoặc 1** tùy loại d đã xuất hiện trước đó. Khi ấy cần mô hình hóa tập loại mệnh giá đã sử dụng, hoặc phát triển thuật toán khác theo cấu trúc ràng buộc.

Nếu đồng có thể sử dụng **tối đa một lần**, đó là bài 0/1; nếu mỗi loại có giới hạn, là bounded; nếu dùng lại tùy ý, là unbounded. Ba phiên bản này khác **miền nghiệm**, dù có thể cùng viết mục tiêu `min \sum_i x_i`.

## 14. Các cách tối ưu thêm khi A lớn

Thuật toán `O(mA)` là điểm khởi đầu tin cậy nhưng không luôn phù hợp khi `A` rất lớn.

### 14.1. Loại mệnh giá không cần thiết

Với mục tiêu cố định A và chỉ có mệnh giá dương, đồng `d>A` không thể dùng. Có thể loại các mệnh giá ấy trước khi chạy DP. Loại trùng trong bản không giới hạn cũng không làm đổi nghiệm tối ưu.

Nếu cần in một cách đổi mang danh tính từng loại dù giá trị giống nhau, việc loại trùng có thể làm mất lựa chọn loại cụ thể; phải xét hợp đồng đầu ra trước khi loại.

### 14.2. GCD và chia tỷ lệ

Nếu `g=gcd(D)` và `g|A`, thay bài toán bằng các mệnh giá `d/g` và mục tiêu `A/g`, làm số trạng thái giảm g lần. Nếu `g` không chia A, kết luận không có nghiệm ngay.

Đây là tối ưu an toàn vì phép chia cùng một số dương g giữ nguyên các phương trình số đồng nguyên và số lượng đồng sử dụng.

### 14.3. Chọn thuật toán theo cấu trúc hệ mệnh giá

Với hệ mệnh giá được chứng minh **canonical**, tham lam có thể nhanh và dùng rất ít bộ nhớ. Với một tập mệnh giá tổng quát, không có chứng minh thì vẫn phải chọn thuật toán xử lý đầy đủ các khả năng phù hợp.

Với ràng buộc đặc biệt (số loại đồng nhỏ, số tiền rất lớn, giới hạn số lượng, nhiều truy vấn, một loại đồng lớn so với A), có thể xem xét tối ưu bằng lý thuyết số, trạng thái theo phần dư, min-plus hoặc cấu trúc dữ liệu riêng. Những phương pháp ấy cần chứng minh tùy bài; không có một mẹo chuyển mọi đầu vào thành `O(log A)`.

### 14.4. Đổi tiền nhiều lần cho cùng D

Nếu có nhiều truy vấn số tiền `A_1,A_2,\ldots,A_q` với **cùng danh sách mệnh giá**, ta có thể tính DP một lần tới:

\[
A_{\max}=\max_i A_i,
\]

rồi trả từng truy vấn bằng `dp[A_i]` trong `O(1)` sau tiền xử lý. Tổng chi phí là `O(mA_{\max}+q)` thời gian và `O(A_{\max})` bộ nhớ.

Đây là trường hợp tiền xử lý có thể được phân bổ cho nhiều truy vấn. Nếu mệnh giá hoặc giới hạn số lượng thay đổi giữa các truy vấn, bảng DP cũ không tự động còn đúng.

## 15. Những lỗi thường gặp

1. **Áp dụng tham lam cho mọi hệ mệnh giá**; `[1,3,4]` với `A=6` là phản ví dụ.
2. **Nhầm số đồng với số loại đồng**; một nghiệm dùng một loại chưa chắc dùng ít đồng.
3. **Khởi tạo `dp[s]=0` cho mọi s**; như vậy không phân biệt trạng thái chưa đạt được với số tiền 0.
4. **Quên `dp[0]=0`**, khiến tất cả trạng thái phụ không có cơ sở.
5. **Cộng 1 vào INF** mà không kiểm tra; với sentinel lớn có thể tràn số và tạo ra nghiệm giả.
6. **Cho phép mệnh giá 0 hoặc âm** nhưng vẫn dùng DP một chiều theo số tiền dương, làm sai phụ thuộc.
7. **Quên mệnh giá có thể dùng lặp** trong bản unlimited; không được xem mỗi loại là một đồng duy nhất.
8. **Với bounded, duyệt số tiền tăng cho từng đồng vật lý**, khiến cùng một đồng bị dùng nhiều lần.
9. **Với unlimited, dùng vòng cập nhật 0/1 giảm dần theo từng loại** rồi tưởng cho phép dùng vô hạn.
10. **Không giữ `lastCoin` nhưng vẫn cố gắng khôi phục phương án** từ chỉ mỗi `dp[A]`.
11. **Truy vết bounded chỉ từ parent 1D có thể bị ghi đè**, dẫn tới phương án dùng đồng vượt số lượng có sẵn.
12. **Giả định mọi số tiền có thể tạo** khi không có đồng mệnh giá 1.
13. **Cho rằng `gcd(D)|A` là đủ**; `D=[4,6],A=2` chứng minh sai.
14. **Không phân biệt A=0 và A>0 không đạt được**; đáp án là 0 ở trường hợp đầu, -1 ở trường hợp sau.
15. **Đếm số tổ hợp thay vì tìm min** chỉ vì cả hai đều có từ “đổi tiền” trong tên bài.
16. **Nhầm thứ tự vòng lặp trong bài đếm cách**, thay đổi việc đếm tổ hợp hay hoán vị.
17. **Không cân nhắc A rất lớn**, khiến mảng DP tiêu tốn tài nguyên vượt RAM.
18. **Sắp đầu vào mệnh giá mà quên giữ liên kết với số lượng** trong bản bounded.
19. **Dùng số thực để tính chính xác giá trị tiền nhỏ nhất**, dễ gặp sai số làm tròn khi so bằng.
20. **Công bố một phương án duy nhất là “phương án tối ưu duy nhất”** trong khi có thể có nhiều cách dùng cùng số đồng.

## 16. Checklist thiết kế bài đổi tiền

Trước khi viết code, hãy trả lời:

1. Mục tiêu là **ít số đồng nhất**, tổng phí thấp nhất, ít loại mệnh giá nhất hay đếm số cách?
2. Phải tạo **đúng** A hay được phép trả phần dư?
3. Mỗi mệnh giá dùng **vô hạn** hay có giới hạn số đồng cụ thể?
4. Mệnh giá có nguyên dương và mục tiêu có không âm không?
5. Có thể có mệnh giá trùng? Nếu có, các loại trùng được coi là tương đương hay có danh tính riêng?
6. Đầu ra cần **số đồng**, **một phương án**, hay **tất cả phương án tối ưu**?
7. Khi có nhiều đáp án cùng số đồng, có cần thứ tự ưu tiên nào không?
8. Khi không thể tạo A, API trả `-1`, `Optional`, ngoại lệ hay một đối tượng báo trạng thái?
9. A và số lượng truy vấn lớn cỡ nào? Có đủ RAM cho `O(A)`?
10. Có cấu trúc mệnh giá nào đã được chứng minh cho phép dùng greedy không?
11. Bộ kiểm thử có ca 0, mảng rỗng, không có nghiệm, trùng, mệnh giá lớn hơn A, nguồn đồng có giới hạn không?
12. Nếu dùng cấu trúc 1D bounded DP, đã chứng minh hướng duyệt và cơ chế truy vết đúng chưa?

## 17. Bài tập tự kiểm tra

**Bài 1 — Phản ví dụ tham lam.** Cho mệnh giá `[1,3,4]`, mục tiêu 6. Hãy chạy tham lam và DP; ghi số đồng, các đồng được chọn và giải thích vì sao tham lam sai.

**Bài 2 — Bảng DP.** Với `D=[1,3,4]`, hãy tính `dp[0],dp[1],\ldots,dp[7]`. Với `s=6`, nêu tất cả ứng viên từ các đồng 1, 3, 4.

**Bài 3 — Không có nghiệm.** Với `D=[4,6]`, xác định kết quả cho `A=2`, `A=7`, `A=8`. Điều kiện gcd giúp loại trường hợp nào, và vì sao không phải điều kiện đủ?

**Bài 4 — Khôi phục.** Nếu `dp[6]=2` và `lastCoin[6]=3`, `lastCoin[3]=3`, hãy truy ngược một phương án. Vì sao vòng truy vết dừng?

**Bài 5 — Bounded vs unlimited.** Với mệnh giá `[1,3,4]` và số lượng `[2,1,1]`, hãy tìm số đồng ít nhất cho A=6 và A=7. So sánh A=6 với bản unlimited.

**Bài 6 — Hướng duyệt.** Vì sao trong DP 0/1 phải duyệt số tiền giảm dần khi xử lý một đồng vật lý? Nếu duyệt tăng, chuyện gì có thể xảy ra?

**Bài 7 — Độ phức tạp.** Với `m=20` loại mệnh giá và `A=100000`, số lần xét cặp `(sum,coin)` ở bản DP cơ bản là bao nhiêu theo bậc? Bộ nhớ cần bao nhiêu ô? Vì sao `O(mA)` còn gọi là giả đa thức?

**Bài 8 — Khác mục tiêu.** Một bài hỏi số cách đổi A mà không phân biệt thứ tự. Vì sao không được dùng `dp[s]=min(dp[s-c]+1)` để đếm? Hướng các vòng lặp trong công thức đếm tổ hợp là gì?

**Bài 9 — Tối ưu GCD.** Cho `D=[6,10,14]` và `A=30`. Tính gcd, rút gọn mệnh giá/số tiền, và cho một cách đổi hợp lệ. Có thể chỉ dựa trên gcd để khẳng định số đồng tối ưu không?

**Bài 10 — Nhiều truy vấn.** Cho một hệ mệnh giá cố định và 10000 câu hỏi số tiền không lớn hơn 50000. Có cần tính lại `dp` từ đầu cho từng câu hỏi không? Nêu chiến lược tiền xử lý và độ phức tạp.

**Bài 11 — Kiểm thử.** Hãy thiết kế một kiểm thử ngẫu nhiên cho các mệnh giá dương nhỏ với A≤30 để so kết quả DP với BFS trên đồ thị các số tiền. Cần kiểm tra thêm điều gì nếu hàm trả danh sách đồng đã chọn?

**Bài 12 — Bó nhị phân.** Với 13 đồng cùng mệnh giá 5 trong bản bounded, có thể chia số lượng thành các bó 1, 2, 4, 6. Một bó chứa 4 đồng có giá trị số tiền và chi phí số đồng là bao nhiêu? Vì sao không được tính bó đó là một đồng?

### Đáp án gợi ý

1. Tham lam `4+1+1` cần 3 đồng; DP `3+3` cần 2 đồng. Lấy đồng lớn nhất trước gây phần dư 2 tốn hai đồng 1.
2. `dp[0..7]=[0,1,2,1,1,2,2,2]`; tại s=6, các ứng viên lần lượt là `dp[5]+1=3`, `dp[3]+1=2`, `dp[2]+1=3`.
3. A=2: -1; A=7: -1; A=8: 2 đồng `4+4`. Với gcd=2, A lẻ 7 bị loại ngay; A=2 chia hết gcd nhưng vẫn không có nghiệm.
4. Chọn 3 ở s=6 rồi 3 ở s=3, còn 0, nhận `[3,3]`. Mỗi bước trừ một đồng có mệnh giá dương, nên số tiền còn lại giảm.
5. Bounded A=6 cần 3 đồng `4+1+1`; A=7 cần 2 đồng `3+4`. Unlimited A=6 chỉ cần 2 đồng `3+3`, nhưng bản bounded chỉ có một đồng 3.
6. Duyệt giảm ngăn trạng thái vừa tạo ở số tiền thấp được dùng lại ngay khi xử lý **cùng một đồng**; duyệt tăng có thể dùng một đồng nhiều lần.
7. Có khoảng `mA=2,000,000` lượt xem ứng viên; bảng DP có `A+1=100001` ô (và thêm mảng truy vết nếu cần). A được biểu diễn bằng `O(log A)` bit, trong khi số trạng thái tăng theo **giá trị A**.
8. Công thức min cho một giá trị tối ưu, không đếm nghiệm. Đếm tổ hợp dùng `ways[0]=1`, vòng **mệnh giá ngoài**, vòng **số tiền tăng bên trong**, cộng số cách.
9. `gcd(6,10,14)=2`; rút gọn `D'=[3,5,7]`, `A'=15`. Một cách đổi `10+10+10=30` dùng 3 đồng (hoặc `6+10+14=30`). gcd cho điều kiện cần về khả năng đổi, không cho số đồng tối ưu.
10. Tính DP một lần đến `Amax=50000`, `O(mAmax)` tiền xử lý và `O(Amax)` bộ nhớ; sau đó trả mỗi câu hỏi `O(1)`, tổng thêm `O(q)`.
11. Tạo mảng mệnh giá dương ngắn và mục tiêu nhỏ, chạy DP và BFS cùng tập dữ liệu; kiểm tra cùng số đồng, cùng trạng thái không đạt được. Với phương án khôi phục, kiểm tra số đồng, tổng giá trị, mệnh giá hợp lệ, và số lượng đồng giới hạn nếu là bounded.
12. Bó bốn đồng mệnh giá 5 có **giá trị 20** và **chi phí 4 đồng**. Nếu tính chi phí bó là 1 sẽ thay đổi sai hàm mục tiêu.

## Ghi nhớ

Với các mệnh giá **nguyên dương** và **không giới hạn số đồng**, bài toán đổi tiền **ít đồng nhất** có trạng thái `dp[s]` là **số đồng ít nhất tạo đúng s**. Khởi tạo `dp[0]=0`, những số tiền không thể tạo là `INF`, rồi dùng:

\[
dp[s]=\min_{d\le s,\ dp[s-d]\ne INF}(dp[s-d]+1).
\]

Tính theo số tiền tăng dần cho thời gian `O(mA)` và bộ nhớ `O(A)`; lưu `lastCoin` nếu cần khôi phục một phương án. **Tham lam không đúng tổng quát**, như `[1,3,4]` với A=6. Nếu mỗi mệnh giá chỉ có số đồng giới hạn, phải dùng DP bounded/0-1 với hướng duyệt thích hợp. Luôn phân biệt **ít đồng** với **đếm số cách**, xử lý A=0 và không có nghiệm, kiểm soát mệnh giá dương, giới hạn RAM và hiểu rằng DP theo A là **giả đa thức**.
