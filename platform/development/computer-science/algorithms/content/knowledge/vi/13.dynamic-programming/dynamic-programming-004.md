# Ghi nhớ kết quả theo hướng từ trên xuống

**Top-down dynamic programming với memoization (quy hoạch động từ trên xuống có ghi nhớ)** bắt đầu bằng một **hàm đệ quy mô tả trực tiếp bài toán**, sau đó lưu kết quả của mỗi **trạng thái bài toán con** để các lần gọi sau lấy lại ngay thay vì tính lại toàn bộ cây đệ quy. Đây là một cách chuyển **đệ quy có các bài toán con chồng lặp** thành lời giải hiệu quả mà vẫn giữ được cách suy luận “muốn giải bài toán lớn thì hỏi các bài toán nhỏ hơn”.

Điểm khó nhất không phải cú pháp tạo mảng `memo[]`, mà là xác định **trạng thái nào đủ để mô tả bài toán con**, **khi nào trạng thái thực sự đã được tính**, **những trường hợp cơ sở**, **thứ tự phụ thuộc** và **chi phí tổng**. Nếu lưu sai khóa hoặc nhầm giá trị hợp lệ `0` với ô “chưa tính”, đáp án có thể sai ngay cả khi chương trình chạy nhanh.

Bài này thuộc nhóm **Quy hoạch động**, trình bày từ mô hình đến chứng minh đúng, phân tích độ phức tạp, ví dụ Fibonacci, bài ít đồng xu nhất, ba lô 0/1 và chương trình Java 17+ tự kiểm tra đầu ra.

## 1. Khi nào đệ quy thuần lặp lại cùng một công việc?

Xét dãy Fibonacci:

```text
F(0) = 0
F(1) = 1
F(n) = F(n-1) + F(n-2) khi n >= 2
```

Một hàm đệ quy thuần:

```java
// Đoạn minh họa, không phải một chương trình độc lập.
static long fibSlow(int n) {
    if (n <= 1) return n;
    return fibSlow(n - 1) + fibSlow(n - 2);
}
```

Nếu gọi `F(5)`, cây lời gọi có các nhánh:

```text
F(5)
├── F(4)
│   ├── F(3)
│   │   ├── F(2)
│   │   │   ├── F(1)
│   │   │   └── F(0)
│   │   └── F(1)
│   └── F(2)
│       ├── F(1)
│       └── F(0)
└── F(3)
    ├── F(2)
    │   ├── F(1)
    │   └── F(0)
    └── F(1)
```

Trạng thái `F(3)` xuất hiện nhiều lần, `F(2)` cũng vậy. Mỗi lần đệ quy thuần gặp lại cùng `n`, nó vẫn mở cả cây tính toán con. Tổng số lời gọi tăng **theo hàm mũ**, thường biểu diễn là `Θ(φ^n)` với `φ=(1+√5)/2`, trong khi chỉ có `n+1` trạng thái `F(0),...,F(n)` khác nhau.

**Memoization** thay đổi cách thực thi:

- Lần đầu gặp `F(k)`: tính theo công thức đệ quy, **lưu** đáp án.
- Lần sau gặp `F(k)`: **trả giá trị đã lưu** với chi phí truy xuất mảng `O(1)`.
- Do mỗi `k` chỉ cần tính thực sự một lần và dùng tối đa hai trạng thái con, tổng thời gian trở thành **`Θ(n)`** với cách tính số học hằng thời gian và `n` trong miền kiểu số cho phép.

Với `F(5)`, chỉ sáu trạng thái `0..5` cần được giải thực sự. Đệ quy vẫn tồn tại, nhưng những nhánh trùng **không bị khai triển lần nữa**. Ghi nhớ không “làm đệ quy mất đi”; nó **cắt bớt việc trùng**.

## 2. Mẫu top-down memoization: STATE → BASE → CACHE → TRANSITION → STORE

Một hàm memoization có cấu trúc:

```text
solve(state):
    if state là trường hợp cơ sở:
        return baseAnswer

    if state đã có kết quả trong cache:
        return cache[state]

    answer = kết hợp(solve(childState1), solve(childState2), ...)
    cache[state] = answer
    đánh dấu state đã hoàn tất
    return answer
```

Các thành phần cần hiểu:

1. **`state`:** tập tham số tối thiểu xác định hoàn toàn đáp án của bài toán con. Với Fibonacci là `n`. Với bài có chọn đồ vật, thường cần cả **vị trí đồ vật** và **sức chứa còn lại**.
2. **`base case`:** trường hợp có đáp án trực tiếp mà không sinh bài toán con, như `F(0)=0`, `F(1)=1`.
3. **`cache`:** nơi ánh xạ từ trạng thái sang đáp án. Có thể là mảng một chiều, mảng hai chiều hoặc `HashMap` với khóa tổ hợp.
4. **`visited / computed / done`:** dấu hiệu trạng thái **đã được tính xong**, khác với giá trị đáp án.
5. **`transition`:** công thức dựa trên các bài toán con, ví dụ `F(n−1)+F(n−2)`.
6. **`return`:** mọi lần gọi trên cùng trạng thái phải trả cùng đáp án nếu dữ liệu đầu vào và quy tắc không đổi.

### Vì sao phải phân biệt “chưa tính” với đáp án hợp lệ?

Đoạn mã dưới đây **sai** nếu `0` có thể là kết quả:

```java
// SAI khi 0 là kết quả có nghĩa.
if (memo[state] != 0) {
    return memo[state];
}
```

Ví dụ Fibonacci có `F(0)=0`; bài đếm số đường có thể trả `0`; bài tối ưu hóa có thể trả `0` hoặc một số âm. Nếu coi `0` là chưa tính, chương trình tính lại các trạng thái đó, có thể mất lợi thế ghi nhớ. Trong bài khác, việc dùng `−1` để biểu thị “chưa tính” cũng sai nếu `−1` là **đáp án hợp lệ** hoặc là mã báo “không thể”.

Cách rõ ràng với Java mảng số:

```java
long[] memo = new long[n + 1];
boolean[] computed = new boolean[n + 1];

if (computed[state]) {
    return memo[state];
}
// ... tính answer ...
memo[state] = answer;
computed[state] = true;
return answer;
```

Đây là các dòng minh họa; `state` và `answer` được xác định bởi bài toán cụ thể. Có thể dùng `Long[]` với `null` biểu thị chưa tính, hoặc chọn sentinel đã chứng minh **nằm ngoài miền đáp án**, nhưng `boolean[]` thường rõ nhất khi dữ liệu hợp lệ có thể bằng `0`, `−1`, hoặc các giá trị khác.

**Chỉ đánh dấu `computed=true` sau khi có đáp án hoàn chỉnh.** Nếu có chu trình phụ thuộc giữa các trạng thái và ta đánh dấu là hoàn thành quá sớm, lần gọi quay trở lại có thể đọc kết quả chưa được tính. Với hệ trạng thái có chu trình cần phát hiện trạng thái “đang xử lý” hoặc chuyển sang thuật toán phù hợp cho đồ thị có chu trình; mẫu quy hoạch động đệ quy đơn giản giả định quan hệ phụ thuộc giảm dần và không tạo vòng.

## 3. Thiết kế trạng thái đúng: lưu đủ biến, không lưu dữ liệu thừa

Bước quyết định chất lượng một lời giải memoization là hỏi:

> “Sau khi giữ cố định những biến nào, kết quả bài toán con không còn phụ thuộc vào lịch sử đường đi trước đó?”

Một số ví dụ:

| Bài toán | Trạng thái đủ | Vì sao cần đúng những biến này? |
| --- | --- | --- |
| Fibonacci | `n` | `F(n)` chỉ phụ thuộc chỉ số `n` |
| Tổng số cách lên bậc thang, mỗi bước 1 hoặc 2 | `remainingSteps` | Số cách hoàn tất chỉ phụ thuộc số bậc còn lại (khi quy tắc cố định) |
| Ít đồng xu nhất để tạo tổng, mỗi đồng xu dùng không giới hạn | `remainingAmount` | Còn thiếu bao nhiêu quyết định đáp án; bộ mệnh giá cố định |
| Ba lô 0/1, duyệt từng đồ vật | `(index, capacityLeft)` | Cần biết **những đồ vật nào còn được chọn** và sức chứa còn lại |
| Đường đi lưới chỉ đi phải/xuống | `(row,column)` | Trạng thái tương lai phụ thuộc vị trí hiện tại nếu lưới cố định |
| So khớp hai chuỗi bằng LCS | `(i,j)` | Cần biết vị trí đang xét trong **cả hai chuỗi** |
| Quy hoạch động với điều kiện đã/chưa dùng ưu đãi một lần | `(position, usedCoupon)` | Hai đường đi tới cùng vị trí có thể còn quyền lựa chọn khác nhau |

Nếu bỏ bớt một biến thực sự ảnh hưởng đến lời giải, **hai trạng thái khác nhau bị gộp vào một ô cache**, tạo đáp án sai. Ví dụ trong ba lô 0/1, cùng sức chứa còn lại `5` nhưng đã xử lý đến đồ vật thứ nhất hoặc thứ ba là hai bài toán con **khác nhau**.

Ngược lại, nếu đưa vào khóa một biến không ảnh hưởng đến kết quả tương lai, như toàn bộ lịch sử chọn đồ khi chỉ cần `(i,capacityLeft)`, nhiều trạng thái về bản chất giống nhau không được tái sử dụng, dẫn đến cache phình to.

### Khóa cache và dữ liệu cố định

Trong lời giải “ít đồng xu nhất”, `solve(6)` với các mệnh giá `[1,3,4]` có thể bằng `2`, còn với mệnh giá `[4,5]` có thể **không giải được**. Vì vậy cache theo `remaining` là đủ **chỉ khi bộ mệnh giá cố định trong vòng đời cache đó**. Nếu đổi bộ mệnh giá hoặc quy tắc, phải tạo cache mới hoặc đưa thông tin cấu hình thích hợp vào khóa.

Tương tự, nếu bảng DP được xây từ mảng có thể sửa, cache có thể **stale** sau khi mảng thay đổi. Cách tránh đơn giản trong API là sao chép đầu vào cấu hình hoặc không tái sử dụng cache qua những phiên bản dữ liệu khác nhau.

## 4. Ví dụ một: Fibonacci với mảng đã tính

Công thức:

```text
F(n) = 0                  nếu n = 0
F(n) = 1                  nếu n = 1
F(n) = F(n-1) + F(n-2)    nếu n >= 2
```

Với `F(5)`, một lần tính theo hướng từ trên xuống:

```text
F(5) -> F(4) -> F(3) -> F(2) -> F(1) = 1
                               -> F(0) = 0
                         F(2) = 1, lưu lại
                 -> F(1) = 1
             F(3) = 2, lưu lại
       -> F(2) = 1, lấy từ memo
       F(4) = 3, lưu lại
-> F(3) = 2, lấy từ memo
F(5) = 5, lưu lại
```

**Bất biến cache:** Mỗi `computed[k]==true` nghĩa là `memo[k]` đã bằng giá trị toán học chính xác của `F(k)`. Bắt đầu không có trạng thái nào được đánh dấu; các giá trị cơ sở đúng trực tiếp; trạng thái khác chỉ đánh dấu sau khi đã tính đúng hai con. Quy nạp theo `k` cho thấy mọi giá trị lưu lại đều đúng.

**Độ phức tạp:**

- Có `n+1` trạng thái `0..n` và mỗi trạng thái có tối đa hai chuyển tiếp: **`O(n)` thời gian** nếu một phép cộng kiểu số cố định tốn `O(1)`.
- Hai mảng `memo` và `computed` chiếm **`O(n)` bộ nhớ**.
- Call stack sâu nhất có thể đạt **`O(n)`**, do một đường gọi `F(n),F(n−1),...,F(0)`.
- `long` của Java biểu diễn chính xác Fibonacci không âm đến **`F(92)=7540113804746346429`**; `F(93)` vượt `Long.MAX_VALUE`. Với `n>92` muốn kết quả chính xác phải dùng `BigInteger` và phân tích thêm chi phí số học nhiều bit, không tiếp tục cộng `long` rồi chấp nhận tràn.

Bản Java đầy đủ ở phần 9 giới hạn `0≤n≤92` và đếm số lần thực sự tính trạng thái. Nó **không** dùng giá trị `0` làm sentinel.

## 5. Ví dụ hai: ít đồng xu nhất — trạng thái không thể giải và số 0 hợp lệ

Cho các mệnh giá **nguyên dương** `coins=[c_1,...,c_m]`, mỗi mệnh giá được sử dụng **không giới hạn số lần**, cần số đồng xu ít nhất để đạt tổng `A≥0`. Định nghĩa `dp(t)` là số đồng xu nhỏ nhất cho tổng `t`, hoặc `INF` nếu không có cách.

Công thức:

```text
dp(0) = 0

dp(t) = min_{c in coins, c <= t} (1 + dp(t-c)),  t > 0

Nếu không có c hợp lệ hoặc mọi dp(t-c) là INF:
dp(t) = INF.
```

Mỗi trạng thái `t>0` chỉ gọi các trạng thái `t−c<t` vì `c>0`, nên quan hệ phụ thuộc là **không chu trình**. Một lựa chọn đồng xu đầu tiên `c` giảm tổng còn thiếu từ `t` thành `t−c`. Nếu tìm được phương án tối ưu có ít nhất một đồng xu, bỏ đồng xu đầu sẽ để lại lời giải tối ưu cho `t−c`; nếu không tối ưu, ta có thể thay bằng một lời giải tốt hơn và mâu thuẫn. Vì thế phép lấy `min` là đúng.

Ví dụ `coins=[1,3,4]`, `A=6`:

- Tham lam lấy đồng xu lớn nhất có thể có thể chọn `4+1+1`, tức **3** đồng xu.
- Quy hoạch động xét `3+3`, chỉ **2** đồng xu, là phương án tối ưu.
- `dp(0)=0` là **đáp án hợp lệ**, không phải “chưa tính”.
- Với `coins=[4,6]` và `A=7`, không có cách tạo tổng 7. API có thể trả **`−1`** để người gọi phân biệt với tổng 0 có đáp án 0; bên trong thuật toán có thể dùng một giá trị `INF` rồi chuyển khi trả kết quả.

### Vì sao phải cache cả trường hợp không thể?

Một trạng thái `t` không có lời giải có thể bị nhiều nhánh khác gọi tới. Nếu chỉ cache khi tìm được lời giải, các nhánh sẽ **thử lại toàn bộ các đường không thành công**. Memoization nên lưu cả kết quả **không thể giải** (sentinel `INF`), đồng thời dùng `computed[t]` để biết rằng trạng thái đã được kiểm tra xong.

Tránh tính `1 + INF` nếu `INF` là `Integer.MAX_VALUE`, vì số nguyên có thể tràn. Mã Java bên dưới dùng `long INF=Long.MAX_VALUE/4` và chỉ cộng 1 khi giá trị con thực sự hữu hạn.

**Độ phức tạp:** Với `A` là tổng đích và `m` loại đồng xu, có tối đa `A` trạng thái không-cơ-sở (`1..A`). Mỗi trạng thái thử tối đa `m` mệnh giá, nên **`O(A·m)` thời gian**, **`O(A+m)` bộ nhớ cho memo, đánh dấu và bản sao mệnh giá**, cộng call stack tối đa `O(A/c_min)`, chặn trên `O(A)`. Đây là chi phí theo **giá trị số `A`**, không phải độ dài biểu diễn nhị phân của `A`; vì thế với `A` rất lớn, DP này là thuật toán **giả đa thức (pseudo-polynomial)**.

Nếu `A=0`, trả `0` ngay. Nếu mệnh giá bằng 0 hoặc âm, phép gọi `dp(t−c)` có thể không giảm: code **phải từ chối** các mệnh giá không dương trước khi đệ quy.

## 6. Ví dụ ba: ba lô 0/1 — một trạng thái có hai chiều

Có `n` đồ vật, đồ vật `i` có trọng lượng `w[i]≥0`, giá trị `v[i]≥0`; mỗi đồ vật được chọn **tối đa một lần**. Sức chứa còn lại `c≥0`. Định nghĩa:

```text
K(i,c) = giá trị lớn nhất khi chỉ còn các đồ vật
         có chỉ số i..n-1 và sức chứa c.
```

Công thức:

```text
K(n,c) = 0, với mọi c >= 0

K(i,c) = max(
    K(i+1,c),                         // bỏ đồ vật i
    v[i] + K(i+1,c-w[i])              // lấy i, chỉ nếu w[i] <= c
)
```

**Vì sao không chỉ cache theo `c`?** Với sức chứa còn lại `c=5`, nếu `i=0` ta còn mọi đồ vật để chọn; nếu `i=n−1` chỉ còn một đồ vật. Hai trạng thái có cùng `c` nhưng giá trị tối ưu khác nhau. Khóa cache bắt buộc gồm **`(i,c)`** trong cách tổ chức này.

**Vì sao gọi `K(i+1,...)` ở cả hai nhánh?** Sau khi xét đồ vật `i`, nó **không còn được xét lại**; đây là ba lô 0/1. Nếu nhánh lấy đồ vật gọi lại `K(i,c−w[i])`, đồ vật có thể được sử dụng nhiều lần, chuyển thành bài toán ba lô không giới hạn hoặc gây vòng lặp với `w[i]=0`.

Ví dụ:

```text
weights = [2, 3, 4]
values  = [4, 5, 7]
capacity = 5
```

Chọn đồ vật trọng lượng `2` và `3`, tổng trọng lượng `5`, tổng giá trị `9`. Đó là lựa chọn tốt nhất; đồ vật trọng lượng `4` có giá trị `7`, kém hơn. Với `capacity=6`, có thể chọn `2+4`, được giá trị `11`.

### Trường hợp đặc biệt: đồ vật trọng lượng 0

Nếu cho phép `w[i]=0` và `v[i]>0`, **không được đặt base case `c==0` một cách máy móc**: vẫn có thể chọn đồ vật trọng lượng 0 dù không còn sức chứa.

Ví dụ đồ vật `(weight,value)=(0,3)` và `(2,4)`, `capacity=0`: lời giải đúng là `3` vì chọn đồ vật đầu tiên không dùng sức chứa. Mã mẫu chỉ dùng **`i==n`** làm trường hợp cơ sở; trong cả hai nhánh chỉ số `i` tăng, nên vẫn kết thúc ngay cả khi trọng lượng bằng 0.

**Độ phức tạp:** Có tối đa `n·(W+1)` trạng thái `(i,c)` không-cơ-sở với `0≤c≤W`; mỗi trạng thái thực hiện tối đa hai chuyển tiếp, nên **`O(nW)` thời gian**, **`O(nW)` bộ nhớ cho mảng memo/visited**, cộng **`O(n)` call stack** và bộ nhớ giữ dữ liệu. Dù dùng top-down và chỉ **tính** các trạng thái truy cập, mảng hai chiều dày đặc vẫn được **cấp phát cho toàn bộ không gian `n(W+1)`**. Nếu trạng thái rất thưa hoặc `W` cực lớn, nên xem xét `HashMap<State,Result>` hoặc một hướng khác thay vì mảng dày đặc.

## 7. Chứng minh nguyên tắc memoization đúng

Một thuật toán top-down có memoization thường được chứng minh dựa trên hai lớp:

**Lớp 1 — công thức trạng thái đúng.**

- **Base:** đáp án của trường hợp cơ sở được định nghĩa chính xác.
- **Transition:** nếu các đáp án bài toán con chính xác, công thức kết hợp trả đáp án chính xác của trạng thái cha.
- **Tiến triển:** mọi bài toán con nằm “nhỏ hơn” theo một thước đo giảm nghiêm ngặt, ví dụ `n` giảm ở Fibonacci, tổng còn thiếu `t` giảm ở coin change, `i` tăng đến `n` ở 0/1 knapsack.

**Lớp 2 — cache không thay đổi kết quả toán học.**

- Bất biến: nếu `computed[state]` đúng, `memo[state]` bằng đáp án đúng của trạng thái đó.
- Lần gọi khi đã tính: trả cache nên đáp án đúng được tái sử dụng.
- Lần gọi chưa tính: đệ quy tính các con; theo giả thiết quy nạp chúng đúng; transition cho đáp án đúng; sau đó mới lưu và đánh dấu.
- Vì có hữu hạn trạng thái và mỗi chuyển tiếp đi tới một trạng thái theo quan hệ phụ thuộc không chu trình, thuật toán dừng.

Ghi nhớ **không sửa công thức**, chỉ thay việc tính lại bằng việc đọc đáp án đã biết. Nếu chính công thức đệ quy sai, memoization chỉ giúp nhận một đáp án sai nhanh hơn.

### Lưu ý về trạng thái có chu trình

Không phải mọi hàm đệ quy đều là DP dạng DAG. Nếu `A` phụ thuộc `B` và `B` phụ thuộc ngược `A`, việc chỉ gắn `computed` sau khi giải xong vẫn có thể đệ quy vô hạn. Khi bài toán tạo đồ thị trạng thái có chu trình, có thể cần:

- Ba màu **UNVISITED / VISITING / DONE** để phát hiện chu trình;
- Thuật toán đường đi ngắn nhất, tìm thành phần liên thông mạnh, lặp tới điểm cố định hoặc một phương pháp thích hợp khác;
- Chứng minh rõ một hướng giảm (thứ tự tô pô, số bước còn lại, số vật còn lại...) trước khi dùng memo đệ quy đơn giản.

Không đánh dấu **VISITING** thành **DONE** rồi trả “đáp án tạm” nếu chưa có cơ sở toán học chứng minh đúng.

## 8. Khi top-down đáng dùng và khi bottom-up tốt hơn

**Top-down:** Bắt đầu từ trạng thái đích và chỉ mở những trạng thái con thực sự cần cho nó. Phù hợp khi công thức đệ quy dễ diễn đạt, trạng thái reachable thưa, hoặc nhiều nhánh có thể bỏ qua.

**Bottom-up (tabulation):** Xác định thứ tự các trạng thái sao cho trạng thái con đã được tính trước, thường dùng vòng lặp. Ưu điểm là tránh call stack và có thể tối ưu bộ nhớ theo hàng/cột hoặc trạng thái trước đó.

| Tiêu chí | Top-down + memo | Bottom-up |
| --- | --- | --- |
| Cách nghĩ | Đặt câu hỏi cần giải, chia nhỏ đệ quy | Xác định thứ tự điền bảng từ cơ sở lên |
| Trạng thái được **tính** | Chỉ trạng thái reachable từ câu hỏi gốc | Thường điền toàn bộ miền được lập lịch |
| Bộ nhớ cache | Mảng dày đặc hoặc `HashMap` thưa | Bảng hoặc vài hàng trạng thái |
| Stack lời gọi | Có, sâu theo quan hệ phụ thuộc | Thường không |
| Tránh tính lại | Cache kết quả đã tính | Mỗi ô bảng được điền theo lịch |
| Rủi ro | `StackOverflowError`, sai khóa cache, chu trình | Sai thứ tự duyệt, ghi đè kết quả cần dùng |
| Khi n, A hoặc W rất lớn | Cần cân nhắc độ sâu stack và RAM | Cần cân nhắc RAM và số ô phải điền |

**Không được nói “top-down chỉ dùng bộ nhớ cho reachable state” nếu cài đặt đã cấp phát `memo[n][W+1]`.** Cách cài bằng mảng dày đặc vẫn dùng `Θ(nW)` bộ nhớ, kể cả khi chỉ vài ô được đánh dấu. Một `HashMap` cho trạng thái thưa tránh nhiều ô không dùng, nhưng có chi phí hashing/boxing và object lớn hơn.

Ví dụ Fibonacci chỉ cần kết quả cuối: bottom-up với hai biến `prev` và `curr` đạt **`O(1)` bộ nhớ phụ**, còn top-down dùng memo và call stack `O(n)`. Nếu cần trả nhiều giá trị `F(k)` sau đó, bảng memo có giá trị tái sử dụng rõ ràng hơn.

### Khi memoization không đem lại lợi ích

Nếu cây đệ quy **không có hai lời gọi nào gặp cùng trạng thái**, cache chỉ tạo overhead. Trường hợp mỗi trạng thái được giải một lần, thời gian xử lý vốn đã tỉ lệ số trạng thái thực sự đi qua; memoization không cải thiện bậc thời gian. Dùng memo khi có **bài toán con chồng lặp**, khi cần nhiều truy vấn cùng bộ input, hoặc khi loại bỏ việc tính lại đem lại giá trị lớn hơn chi phí lưu/tra cứu.

## 9. Java 17+ — chương trình độc lập với ba bài toán memoization

Chương trình sau dùng:

- `FibMemo` với `long[] values` và `boolean[] done`; đếm số lần **vào hàm** và số trạng thái **thực sự được tính**.
- `CoinMemo` với trạng thái một chiều `remaining` và sentinel `INF` không xung đột với số đồng xu hợp lệ; trả `−1` nếu không thể.
- `KnapsackMemo` với trạng thái hai chiều `(i,capacityLeft)`; cho phép đồ vật trọng lượng 0 và dùng `long` cho tổng giá trị.
- `verifySmallCases()` đối chiếu với Fibonacci vòng lặp, coin change bottom-up và ba lô brute force trên các trường hợp nhỏ.
- Constructor tạo **bản sao dữ liệu cấu hình** để mệnh giá hoặc danh sách đồ vật bên ngoài thay đổi không làm cache của đối tượng đang dùng trở thành sai.

### Toàn bộ mã nguồn

Lưu thành tệp **TopDownMemoDemo.java**:

```java
import java.util.Arrays;
import java.util.Objects;

public class TopDownMemoDemo {
    static final class FibMemo {
        private final long[] value;
        private final boolean[] done;
        int calls;
        int states;

        FibMemo(int maxN) {
            if (maxN < 0 || maxN > 92) {
                throw new IllegalArgumentException("Fibonacci n must be 0..92");
            }
            value = new long[maxN + 1];
            done = new boolean[maxN + 1];
        }

        long get(int n) {
            if (n < 0 || n >= value.length) {
                throw new IllegalArgumentException("n outside memo domain");
            }
            calls++;
            if (done[n]) {
                return value[n];
            }

            long answer = (n <= 1) ? n : get(n - 1) + get(n - 2);
            value[n] = answer;
            done[n] = true;
            states++;
            return answer;
        }
    }

    static final class CoinMemo {
        // Không thể trùng số đồng xu tối thiểu cho amount kiểu int.
        private static final long INF = Long.MAX_VALUE / 4;
        private final int[] coins;
        private final long[] memo;
        private final boolean[] done;
        private final int amount;
        int states;

        CoinMemo(int[] denominations, int amount) {
            Objects.requireNonNull(denominations, "denominations");
            if (amount < 0 || amount == Integer.MAX_VALUE) {
                throw new IllegalArgumentException("invalid amount");
            }
            for (int c : denominations) {
                if (c <= 0) {
                    throw new IllegalArgumentException(
                        "coin must be positive");
                }
            }
            this.coins = denominations.clone();
            this.amount = amount;
            this.memo = new long[amount + 1];
            this.done = new boolean[amount + 1];
        }

        private long solve(int remaining) {
            if (remaining == 0) {
                return 0L;
            }
            if (done[remaining]) {
                return memo[remaining];
            }

            long best = INF;
            for (int coin : coins) {
                if (coin <= remaining) {
                    long sub = solve(remaining - coin);
                    if (sub != INF) {
                        best = Math.min(best, 1L + sub);
                    }
                }
            }

            memo[remaining] = best;  // Kể cả trạng thái không thể.
            done[remaining] = true;
            states++;
            return best;
        }

        int minCoins() {
            long answer = solve(amount);
            return answer == INF ? -1 : (int) answer;
        }
    }

    static final class KnapsackMemo {
        private final int[] weights;
        private final int[] values;
        private final long[][] memo;
        private final boolean[][] done;
        private final int capacity;
        int states;

        KnapsackMemo(int[] weights, int[] values, int capacity) {
            Objects.requireNonNull(weights, "weights");
            Objects.requireNonNull(values, "values");
            if (weights.length != values.length) {
                throw new IllegalArgumentException("lengths differ");
            }
            if (capacity < 0 || capacity == Integer.MAX_VALUE) {
                throw new IllegalArgumentException("invalid capacity");
            }
            for (int w : weights) {
                if (w < 0) {
                    throw new IllegalArgumentException("negative weight");
                }
            }
            for (int v : values) {
                if (v < 0) {
                    throw new IllegalArgumentException("negative value");
                }
            }

            this.weights = weights.clone();
            this.values = values.clone();
            this.capacity = capacity;
            this.memo = new long[weights.length][capacity + 1];
            this.done = new boolean[weights.length][capacity + 1];
        }

        private long solve(int i, int remain) {
            if (i == weights.length) {
                return 0L;
            }
            if (done[i][remain]) {
                return memo[i][remain];
            }

            long best = solve(i + 1, remain); // Bỏ đồ vật i.
            if (weights[i] <= remain) {
                long take = (long) values[i]
                        + solve(i + 1, remain - weights[i]);
                best = Math.max(best, take);
            }

            memo[i][remain] = best;
            done[i][remain] = true;
            states++;
            return best;
        }

        long maxValue() {
            return solve(0, capacity);
        }
    }

    record Verification(int fib, int coin, int knapsack) {}

    // Oracle Fibonacci bottom-up, độc lập với memo đệ quy.
    static long fibIterative(int n) {
        if (n <= 1) {
            return n;
        }
        long previous = 0, current = 1;
        for (int i = 2; i <= n; i++) {
            long next = previous + current;
            previous = current;
            current = next;
        }
        return current;
    }

    // Oracle coin change bottom-up; chỉ dùng với bộ coin dương.
    static int coinBottomUp(int[] coins, int amount) {
        final int INF = Integer.MAX_VALUE;
        int[] dp = new int[amount + 1];
        Arrays.fill(dp, INF);
        dp[0] = 0;

        for (int t = 1; t <= amount; t++) {
            for (int coin : coins) {
                if (coin <= t && dp[t - coin] != INF) {
                    dp[t] = Math.min(dp[t], dp[t - coin] + 1);
                }
            }
        }
        return dp[amount] == INF ? -1 : dp[amount];
    }

    // Oracle brute force liệt kê mọi tập con khi n nhỏ.
    static long knapsackBrute(int[] weights, int[] values, int cap) {
        long best = 0L;
        int n = weights.length;
        for (int mask = 0; mask < (1 << n); mask++) {
            long totalWeight = 0L;
            long totalValue = 0L;
            for (int i = 0; i < n; i++) {
                if ((mask & (1 << i)) != 0) {
                    totalWeight += weights[i];
                    totalValue += values[i];
                }
            }
            if (totalWeight <= cap) {
                best = Math.max(best, totalValue);
            }
        }
        return best;
    }

    static Verification verifySmallCases() {
        int fibCases = 0;
        for (int n = 0; n <= 35; n++) {
            if (new FibMemo(n).get(n) != fibIterative(n)) {
                throw new AssertionError("Fibonacci mismatch");
            }
            fibCases++;
        }

        int coinCases = 0;
        int[][] sets = {
            {1, 3, 4}, {2, 5}, {4, 6}, {1}, {3}
        };
        for (int[] coins : sets) {
            for (int target = 0; target <= 25; target++) {
                int actual = new CoinMemo(coins, target).minCoins();
                if (actual != coinBottomUp(coins, target)) {
                    throw new AssertionError("Coin mismatch");
                }
                coinCases++;
            }
        }

        int knapsackCases = 0;
        int variants = 1;
        for (int n = 0; n <= 4; n++) {
            for (int encoded = 0; encoded < variants; encoded++) {
                int[] weights = new int[n];
                int[] values = new int[n];
                int code = encoded;
                for (int i = 0; i < n; i++) {
                    weights[i] = code % 3 + 1;
                    code /= 3;
                    values[i] = i % 3 + 1;
                }

                for (int capacity = 0; capacity <= 10; capacity++) {
                    long actual =
                        new KnapsackMemo(weights, values, capacity)
                            .maxValue();
                    long expected =
                        knapsackBrute(weights, values, capacity);
                    if (actual != expected) {
                        throw new AssertionError("Knapsack mismatch");
                    }
                    knapsackCases++;
                }
            }
            variants *= 3;
        }
        return new Verification(fibCases, coinCases, knapsackCases);
    }

    public static void main(String[] args) {
        FibMemo f = new FibMemo(10);
        System.out.println(
            "Fib(10): " + f.get(10)
            + " | calls=" + f.calls
            + " | states=" + f.states);
        System.out.println("Fib(0): " + new FibMemo(0).get(0));
        System.out.println("Fib(92): " + new FibMemo(92).get(92));

        CoinMemo coins = new CoinMemo(new int[]{1, 3, 4}, 6);
        System.out.println(
            "Coins [1,3,4] -> 6: " + coins.minCoins()
            + " | computed=" + coins.states);
        System.out.println(
            "Coins [4,6] -> 7: "
            + new CoinMemo(new int[]{4, 6}, 7).minCoins());
        System.out.println(
            "Coins [4,6] -> 0: "
            + new CoinMemo(new int[]{4, 6}, 0).minCoins());

        KnapsackMemo bag =
            new KnapsackMemo(
                new int[]{2, 3, 4},
                new int[]{4, 5, 7}, 5);
        System.out.println("Knapsack cap=5: " + bag.maxValue());
        System.out.println(
            "Knapsack cap=0, zero-weight item: "
            + new KnapsackMemo(
                new int[]{0, 2}, new int[]{3, 4}, 0)
                .maxValue());

        int[] inputCoins = {1, 3, 4};
        int[] copy = inputCoins.clone();
        new CoinMemo(inputCoins, 6).minCoins();
        System.out.println(
            "Input unchanged: " + Arrays.equals(inputCoins, copy));

        Verification verified = verifySmallCases();
        System.out.println(
            "Verified: " + verified.fib() + " fib, "
            + verified.coin() + " coin, "
            + verified.knapsack() + " knapsack");
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 TopDownMemoDemo.java
java TopDownMemoDemo
```

Stdout dự kiến:

```text
Fib(10): 55 | calls=19 | states=11
Fib(0): 0
Fib(92): 7540113804746346429
Coins [1,3,4] -> 6: 2 | computed=6
Coins [4,6] -> 7: -1
Coins [4,6] -> 0: 0
Knapsack cap=5: 9
Knapsack cap=0, zero-weight item: 3
Input unchanged: true
Verified: 36 fib, 130 coin, 1331 knapsack
```

### Giải thích kết quả và xác thực

- `Fib(10)=55`. Trong cách gọi theo chiều sâu ở chương trình, có **11 trạng thái phân biệt** `0..10` và **19 lượt vào hàm**, gồm cả những lần gặp cache. Mỗi trạng thái tính thực sự đúng một lần.
- `CoinMemo([1,3,4],6)` tìm `3+3` với **2 đồng xu**. Các trạng thái `remaining=1..6` được tính thực sự một lần; tổng 0 là base case. Với `[4,6]` và tổng 7, cache lưu `INF` ở trạng thái không thể tạo rồi API trả `−1`. Tổng 0 luôn trả 0.
- Ba lô sức chứa 5 chọn hai đồ vật trọng lượng 2 và 3 để đạt giá trị **9**. Trường hợp sức chứa 0 nhưng có đồ vật không trọng lượng, kết quả **3**, chứng minh không thể mặc định “`capacity==0` thì trả 0”.
- Không có thao tác sort/swap trên bộ mệnh giá. Constructor sao chép input, nên caller không bị sửa dữ liệu khi tạo hoặc sử dụng cache.
- Bộ kiểm thử so Fibonacci với vòng lặp **36 giá trị `n=0..35`**, kiểm **5 bộ mệnh giá × 26 tổng `0..25` = 130** ca coin change; kiểm ba lô với `1+3+9+27+81=121` tổ hợp trọng lượng ở độ dài `0..4` và **11 sức chứa `0..10`**, tổng **1331 ca**. Oracle ba lô duyệt mọi tập con, nên độc lập với công thức quy hoạch động top-down.
- Các ca này **chưa bao phủ mọi input cực lớn** hoặc mọi tình huống bất hợp lệ. Bảo đảm tính đúng tổng quát dựa trên định nghĩa trạng thái, quan hệ chuyển tiếp, điều kiện dừng và bất biến memo ở các phần trước.

## 10. Chi phí thực sự: “số trạng thái × số chuyển tiếp”

Phát biểu thường dùng:

```text
Thời gian memoization ≈ số trạng thái thực sự tính
                         × công việc cho mỗi trạng thái

Bộ nhớ = dữ liệu cache + stack đệ quy + dữ liệu phụ
```

Đây là **khung phân tích**, không phải lúc nào cũng là phép nhân đúng một giá trị hằng: số nhánh của mỗi trạng thái có thể khác nhau và chi phí chuyển tiếp có thể phụ thuộc kích thước input. Cách tổng quát hơn là cộng **chi phí xử lý từng trạng thái reachable** và số lần xét các cạnh phụ thuộc.

| Bài toán | Trạng thái non-base | Số chuyển tiếp mỗi trạng thái | Thời gian top-down | Bộ nhớ điển hình |
| --- | --- | --- | --- | --- |
| Fibonacci `F(n)` | `O(n)` | Tối đa 2 | `O(n)` | `O(n)` memo + `O(n)` stack |
| Ít đồng xu nhất, tổng `A`, `m` mệnh giá | `O(A)` | Tối đa `m` | `O(A·m)` | `O(A+m)` memo/input + `O(A)` stack |
| Ba lô 0/1, `n` vật, sức chứa `W` | `O(nW)` | Tối đa 2 | `O(nW)` | `O(nW)` memo + `O(n)` stack |
| LCS hai chuỗi dài `m,n` | `O(mn)` | Tối đa 2 theo truy hồi phổ biến | `O(mn)` | `O(mn)` cache và `O(m+n)` stack |
| Đường đi trong lưới `R×C` chỉ phải/xuống | `O(RC)` | Tối đa 2 | `O(RC)` | `O(RC)` cache và `O(R+C)` stack |

**Phân biệt cache lookup và compute.** Mỗi trạng thái được **tính xong tối đa một lần**, nhưng có thể có nhiều lời gọi đi vào trạng thái đó rồi return từ cache. Tổng số lần tra cứu phụ thuộc số chuyển tiếp của các trạng thái đã giải. Với một DAG có `V` trạng thái reachable và `E` cạnh phụ thuộc được xét, thường phân tích `O(V+E)`, nếu tra cứu cache và từng phép kết hợp có chi phí hằng.

**Thời gian trước truy vấn đầu tiên:** Tạo mảng memo dày đặc `O(nW)` cũng có chi phí cấp phát/khởi tạo không nhỏ, dù chỉ vài trạng thái được mở. Đừng khẳng định “chỉ dùng `O(reachable)` RAM” trừ khi cấu trúc lưu trữ thực sự cấp phát theo nhu cầu.

**Độ sâu lời gọi:** Tránh lạm dụng top-down khi trạng thái tạo đường đệ quy cực dài, ví dụ coin `[1]` và tổng hàng triệu. Dù có memo, đường `A,A−1,...,0` vẫn sâu `Θ(A)` và có thể `StackOverflowError` trước khi dùng hết bộ nhớ cache. Một lời giải bottom-up có vòng lặp có thể phù hợp hơn.

**Tính toán nhiều giá trị lớn:** Với bài đếm cách, kết quả có thể vượt `long` ngay cả khi số trạng thái nhỏ. Có thể cần `BigInteger`, lấy modulo theo đề bài, hoặc một kiểu biểu diễn khác; không coi memoization là cách tránh tràn số.

## 11. Tránh những lỗi điển hình

**1. Cache theo thiếu tham số.** Ba lô 0/1 không thể chỉ dùng `capacity` khi đáp án còn phụ thuộc `index`. LCS cần cả `i` và `j`; bài có cờ “đã dùng quyền đặc biệt” cần thêm cờ đó.

**2. Nhầm `0`, `−1` hoặc `INF` với “chưa tính”.** Kết quả 0 có nghĩa, không thể tạo tổng được mã hóa bằng sentinel, giá trị âm có thể hợp lệ trong bài khác. Dùng `done[]` hoặc một sentinel chắc chắn không nằm trong miền kết quả.

**3. Không cache trường hợp thất bại.** Những trạng thái không thể giải cũng có thể xuất hiện lặp lại; bỏ qua chúng khiến chương trình liên tục làm lại công việc.

**4. Chỉ đánh dấu sau khi return.** Nếu không bao giờ ghi memo trước lúc `return`, mọi lần gọi sau vẫn coi trạng thái chưa giải. Luồng đúng: tính → lưu → đánh dấu → return.

**5. Đánh dấu DONE trước khi có kết quả.** Nếu phụ thuộc có vòng, lời gọi con có thể đọc giá trị mặc định của trạng thái cha đang chạy. Cần chứng minh DAG hoặc dùng cơ chế VISITING/DONE đúng.

**6. Base case không đầy đủ.** Fibonacci cần `F(0),F(1)`; coin cần tổng 0; ba lô cần khi đã xét hết đồ vật. Quên base gây recursion không dừng hoặc truy cập ngoài mảng.

**7. Viết chuyển tiếp không giảm kích thước.** Đồng xu mệnh giá 0 gọi lại chính tổng hiện tại. Ba lô lấy đồ vật rồi không tăng index có thể biến thành bài unbounded và không dừng với trọng lượng 0.

**8. Tối ưu sai do tham lam.** Với `coins=[1,3,4]`, tổng 6, chọn đồng xu lớn nhất đầu tiên tạo 3 đồng xu, không tối ưu. Memoization phải dùng công thức xét đủ lựa chọn hợp lệ.

**9. Sử dụng cache sau khi cấu hình thay đổi.** Cache theo `remaining` cho bộ coin cũ không còn đúng với bộ coin mới; cache theo `(i,c)` cho tập đồ vật cũ cũng thế. Clone input hoặc tạo cache mới khi thay đổi.

**10. Nghĩ memoization luôn nhanh hơn bottom-up.** Top-down có chi phí gọi đệ quy, lookup/HashMap và stack; nếu mọi trạng thái đều cần, bottom-up đơn giản có thể nhanh hơn và ít RAM hơn.

**11. Kết luận bộ nhớ `O(1)` vì mỗi lời gọi chỉ xử lý ít biến.** Các frame tồn tại đồng thời theo độ sâu đệ quy; memo và cấu trúc phụ cũng chiếm RAM. Tính tổng cả cache lẫn call stack.

**12. Dùng `int` cho giá trị dễ tràn.** Fibonacci `F(92)` cần `long`; Fibonacci vượt 92 cần kiểu lớn hơn. Tổng giá trị ba lô có thể vượt `int`, nên ví dụ tính bằng `long`.

**13. Nhầm trạng thái reachable với kích thước mảng được cấp phát.** Một bảng `boolean[n][W+1]` và `long[n][W+1]` luôn dành không gian cho toàn miền, dù nhiều ô chưa được tính.

**14. Tái sử dụng cache giữa các truy vấn khác điều kiện.** Nếu bài toán có thêm điều kiện lọc, ngân sách, chỉ số bắt đầu hoặc luật chuyển tiếp, những thứ đó phải nằm trong state hoặc cấu hình cache. Không được giả định hai câu hỏi “gần giống nhau” dùng chung memo là an toàn.

**15. Không kiểm tra mức độ lặp trạng thái.** Một cây đệ quy không có subproblem trùng không được cải thiện về bậc thời gian chỉ bằng caching; cần phân tích trạng thái và số cạnh phụ thuộc thật sự.

## 12. Bài tập luyện tập

**Bài 1 — Vẽ cây Fibonacci.** Vẽ đệ quy thuần của `F(6)` và đánh dấu mọi trạng thái lặp. So sánh số trạng thái phân biệt và tổng số lượt vào hàm với một triển khai memo có cache lưu cả `F(0)` và `F(1)`.

*Gợi ý:* Chỉ có 7 trạng thái `0..6`; số lượt vào hàm ở thứ tự xử lý sâu của mã mẫu là 11.

**Bài 2 — Sai sentinel.** Một lời giải `countWays(i)` có thể trả 0. Đoạn `if(memo[i]!=0)return memo[i]` có thể gây hệ quả gì? Viết lại bằng `boolean[] done` và một ví dụ trạng thái không có cách đi.

**Bài 3 — Ít đồng xu nhất.** Cho `coins=[1,3,4]` và `A=6`, viết các giá trị `dp(0)..dp(6)`, chỉ ra vì sao chọn đồng xu lớn nhất trước không đảm bảo tối ưu.

*Gợi ý:* `dp(0..6)=[0,1,2,1,1,2,2]`.

**Bài 4 — Trạng thái bất khả thi.** Với `coins=[4,6]`, xác định `dp(t)` cho `t=0..9`. Những trạng thái nào không thể giải? Vì sao vẫn cần cache `INF` cho chúng?

**Bài 5 — Ba lô 0/1 và khóa cache.** Cho hai đồ vật `(w,v)=(2,4),(3,5)`, sức chứa 5. Viết hai trạng thái `K(0,5)` và `K(1,5)`; vì sao lưu chung ở `memo[5]` là sai dù cùng sức chứa?

**Bài 6 — Trọng lượng 0.** Cho đồ vật `(0,3)` và `(2,4)`, sức chứa 0. Vì sao `if(capacity==0)return0` làm sai kết quả? Thiết kế base case đúng.

**Bài 7 — Top-down và bottom-up.** Với bài LCS hai chuỗi, đề xuất `state=(i,j)`, base case khi một chuỗi hết và transition khi ký tự bằng/khác. Nêu thời gian/bộ nhớ và trường hợp top-down có thể tính ít trạng thái hơn bảng đầy đủ.

**Bài 8 — Stack overflow.** Với coin `[1]`, `A=1.000.000`, phân tích vì sao memo 1D vẫn có thể tràn call stack. Đề xuất chuyển sang bottom-up hoặc cách xử lý khác mà không làm thay đổi định nghĩa bài toán.

**Bài 9 — Kiểm thử độc lập.** Viết các ca kiểm tra cho Fibonacci (`n=0,1,2,10,92`), coin (không thể tạo tổng, tổng 0, mệnh giá trùng, coin không dương), ba lô (mảng rỗng, sức chứa 0, vật trọng lượng 0, nhiều vật cùng trọng lượng). So sánh kết quả top-down với một oracle độc lập.

**Bài 10 — Cache phiên bản dữ liệu.** Một hàm `solve(remaining)` dùng mảng coin có thể sửa ở bên ngoài. Nêu hai thiết kế API để tránh cache cũ bị dùng khi coin thay đổi, và phân tích đánh đổi giữa sao chép cấu hình và quản lý phiên bản.

## 13. Checklist chọn và triển khai memoization

1. **Bài toán con có lặp?** Nếu không, memoization có thể chỉ tăng overhead.
2. **Trạng thái đầy đủ?** Mọi thông tin ảnh hưởng đến đáp án tương lai đều nằm trong khóa hoặc là cấu hình bất biến trong vòng đời cache.
3. **Base case đúng?** Các trạng thái tối thiểu cho đáp án trực tiếp, bao gồm đáp án 0 hoặc bất khả thi.
4. **Transition đúng và giảm dần?** Những lời gọi con tạo quan hệ phụ thuộc không chu trình; có thước đo tiến triển.
5. **Cache phân biệt chưa tính với đã tính?** Tránh dùng giá trị kết quả hợp lệ làm sentinel mà không chứng minh.
6. **Lưu cả kết quả thất bại?** Trạng thái bất khả thi cũng là thông tin tái sử dụng.
7. **Đúng kiểu dữ liệu và hợp đồng?** Có thể tràn số, có yêu cầu modulo/BigInteger, có sửa input hay cập nhật cấu hình không?
8. **Tài nguyên đủ?** Tính số trạng thái reachable, số chuyển tiếp, kích thước mảng/HashMap và độ sâu call stack.
9. **Top-down hay bottom-up?** Nếu sâu quá hoặc bảng dày đặc đã phải cấp phát, một giải pháp iterative có thể tốt hơn.
10. **Có kiểm chứng?** So với brute force/bottom-up trên input nhỏ, kiểm tra mảng rỗng, giá trị 0, trạng thái không thể giải, giá trị trùng và ngoại lệ.

**Tiêu chí hoàn thành:** Bạn có thể viết một hàm đệ quy mô tả đúng trạng thái và công thức quy hoạch động, thêm cache với dấu hiệu “đã tính” độc lập với đáp án, chứng minh mỗi trạng thái được xử lý thực sự tối đa một lần, phân tích số trạng thái/chuyển tiếp/độ sâu stack, và lựa chọn top-down hay bottom-up theo điều kiện thực tế.
