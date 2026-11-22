# Đếm tổ hợp và đếm thứ tự chọn tiền

Trong bài toán **đổi tiền (coin change)**, cùng một tập mệnh giá và cùng một tổng đích có thể dẫn tới **hai bài toán đếm hoàn toàn khác nhau**:

1. **Đếm tổ hợp (combinations):** Chỉ quan tâm **mỗi mệnh giá được lấy bao nhiêu đồng**, không quan tâm trình tự chọn. Hai cách `1+2` và `2+1` là **một** tổ hợp.
2. **Đếm cách chọn có thứ tự (ordered sequences):** Mỗi **chuỗi các lần chọn mệnh giá** là một cách. `1+2` và `2+1` là **hai** cách.

Cả hai thường dùng quy hoạch động (dynamic programming, DP), nhưng **trạng thái, cách tách trường hợp và thứ tự vòng lặp** phải phù hợp với ngữ nghĩa đếm. Việc đổi chỗ hai vòng `for` tưởng chừng nhỏ có thể làm đáp án thay đổi hoàn toàn mà chương trình vẫn biên dịch và chạy bình thường.

Bài học thuộc nhóm **Quy hoạch động tài nguyên**. Ta sẽ đi từ đặc tả chính xác đến công thức, bất biến, truy vết bảng, phiên bản **đồng xu không giới hạn** và **có giới hạn**, xử lý mệnh giá trùng, tràn số, kiểm thử độc lập và một chương trình Java 17+ có thể biên dịch/chạy trực tiếp.

## 1. Trước tiên phải chốt “một cách” nghĩa là gì

Giả sử có các mệnh giá **1, 2** và cần tạo tổng **3**. Mỗi mệnh giá được dùng số lần tùy ý.

**Nếu không quan tâm thứ tự:**

```text
1 + 1 + 1
1 + 2

=> 2 tổ hợp.
```

**Nếu quan tâm thứ tự:**

```text
1 + 1 + 1
1 + 2
2 + 1

=> 3 chuỗi lựa chọn.
```

Tập kết quả không khác ở **tổng giá trị**, nhưng khác ở **đối tượng được tính là riêng biệt**. Đừng tự chọn một trong hai cách hiểu chỉ vì đề dùng từ “số cách”; phải xem đề có nói “không phân biệt thứ tự”, “mọi thứ tự”, “cách xếp”, “chuỗi thao tác”, hay đưa ví dụ xác định rõ.

### Với mệnh giá [1, 2, 5] và tổng 5

Các **tổ hợp** gồm:

```text
1+1+1+1+1
1+1+1+2
1+2+2
5
```

Vậy có **4 tổ hợp**.

Đếm **chuỗi lựa chọn**:

- Năm đồng 1: **1** chuỗi.
- Ba đồng 1 và một đồng 2: vị trí đồng 2 có **4** lựa chọn.
- Một đồng 1 và hai đồng 2: vị trí đồng 1 có **3** lựa chọn.
- Một đồng 5: **1** chuỗi.

Tổng cộng **1+4+3+1=9** chuỗi có thứ tự.

Ví dụ này sẽ được chương trình Java ở mục 10 tính ra đúng **4** và **9**. Hai con số đều chính xác vì giải **hai đặc tả khác nhau**.

### Nên phân biệt thêm ba khía cạnh

| Câu hỏi | Ví dụ/ý nghĩa | Điều cần chốt |
| --- | --- | --- |
| Có phân biệt thứ tự chọn? | `1+2` với `2+1` | Combination hay ordered sequence |
| Đồng xu được dùng bao nhiêu lần? | Loại 2 chỉ còn hai đồng hay được dùng vô hạn? | Không giới hạn, có tồn kho, hay từng đồng dùng một lần |
| Có phân biệt hai đồng cùng mệnh giá? | Hai đồng vật lý 1 đồng có nhãn A, B | Theo **mệnh giá** hay theo **đồng xu/đối tượng** |

Ba trục này **độc lập**. Một bài “đếm tổ hợp” với số lượng mỗi mệnh giá bị giới hạn khác với bài dùng mệnh giá vô hạn. Một bài đếm tập con của các đồng xu vật lý khác với bài đếm số **vector số lượng** cho từng mệnh giá.

## 2. Đặc tả chuẩn: mệnh giá không giới hạn, mỗi mệnh giá là một loại

Trong các mục 3–6, ta dùng hợp đồng sau:

- Tập mệnh giá `coins=[c_1,c_2,...,c_k]`, với **`c_i>0`**.
- Các `c_i` được xem là **những loại mệnh giá phân biệt**; nếu input chứa `[1,2,2,5]`, chương trình chuẩn hóa thành `[1,2,5]` để tránh vô tình nhân đôi cách đếm.
- Mỗi loại mệnh giá được phép chọn **không giới hạn số lần**.
- Tổng đích `A≥0` là số nguyên.
- Trả **số cách chính xác**, nên chương trình Java dùng `BigInteger` thay vì `int`/`long` có thể tràn.
- Dữ liệu đầu vào không bị sửa; trong quá trình tính có thể sắp xếp **bản sao** của các mệnh giá.

Một **tổ hợp** là vector số nguyên không âm:

```text
(x_1, x_2, ..., x_k)

x_i >= 0
x_1*c_1 + x_2*c_2 + ... + x_k*c_k = A
```

Mỗi vector hợp lệ được tính **một lần**. Thứ tự liệt kê các loại mệnh giá trong vector chỉ là quy ước, không đại diện cho thứ tự chọn.

Một **chuỗi lựa chọn** là dãy hữu hạn `(d_1,d_2,...,d_r)`, trong đó mỗi `d_j` thuộc tập mệnh giá, và:

```text
d_1 + d_2 + ... + d_r = A
```

Hai dãy có cùng số phần tử của mỗi loại nhưng **khác thứ tự** là hai kết quả khác nhau.

**Với `A=0`, cả hai bài đều có đúng 1 cách:** **không chọn đồng nào**, gọi là *tổ hợp rỗng* hoặc *dãy rỗng*. Nếu không có mệnh giá (`coins=[]`), số cách tạo tổng dương là **0**, còn tổng 0 vẫn có **1** cách. Quy ước này là nền tảng của mọi công thức DP ở dưới.

## 3. Đếm tổ hợp bằng DP hai chiều: hiểu đúng công thức trước

Gọi `C(i,t)` là số tổ hợp tạo tổng `t` khi **chỉ dùng `i` mệnh giá đầu tiên** trong danh sách mệnh giá phân biệt `c_1..c_i`; mỗi loại được dùng vô hạn.

### Trường hợp cơ sở

```text
C(0, 0) = 1
C(0, t) = 0, với t > 0
C(i, 0) = 1, với mọi i >= 0
C(i, t) = 0, với t < 0
```

Không có loại mệnh giá nào thì tổng 0 có một tổ hợp rỗng, còn tổng dương không thể tạo. Khi có mệnh giá nhưng tổng 0, tổ hợp rỗng vẫn là cách duy nhất vì mọi `c_i` dương.

### Công thức chuyển trạng thái

Xét mệnh giá thứ `i` là `c=c_i`. Mọi tổ hợp tạo `t` thuộc **chính xác một** trong hai nhóm:

- **Không dùng đồng loại `c`:** có `C(i−1,t)` tổ hợp.
- **Dùng ít nhất một đồng loại `c`:** bỏ ra **một** đồng `c`, phần còn lại là một tổ hợp tạo `t−c` vẫn được dùng các loại `1..i`, có `C(i,t−c)` tổ hợp.

Hai nhóm không giao nhau và bao phủ mọi tổ hợp:

```text
C(i,t) = C(i-1,t) + C(i,t-c)    nếu t >= c
C(i,t) = C(i-1,t)               nếu t < c
```

**Vì sao vế thứ hai là `C(i,t−c)`, không phải `C(i−1,t−c)`?** Vì mệnh giá `c` còn được sử dụng **nhiều lần**. Sau khi bỏ ra một đồng `c`, phần còn lại vẫn có thể chứa thêm đồng `c`.

Nếu thay vế đó bằng `C(i−1,t−c)`, mỗi loại chỉ được dùng tối đa một lần; đó là bài toán **0/1**, không phải đổi tiền vô hạn.

### Rút xuống mảng một chiều

Ta có thể dùng `ways[t]` cho một hàng DP. Ban đầu:

```text
ways[0] = 1
ways[t] = 0, với t > 0
```

Sau đó xử lý **mỗi loại mệnh giá ở vòng ngoài**, và tổng `t` **tăng dần** ở vòng trong:

```java
// Lõi ý tưởng: coins là các mệnh giá dương, không trùng.
for (int coin : coins) {
    for (int t = coin; t <= amount; t++) {
        ways[t] = ways[t].add(ways[t - coin]);
    }
}
```

Đoạn này chưa phải chương trình độc lập: `ways` cần được khởi tạo bằng các đối tượng `BigInteger.ZERO` và `ways[0]=BigInteger.ONE`. Mã Java hoàn chỉnh ở mục 10.

**Giải thích chiều tăng dần:** Ở cùng một vòng xử lý mệnh giá `coin`, ô `ways[t−coin]` đã phản ánh cách dùng **bất kỳ số lượng đồng coin đó**. Vì vậy `ways[t]` nhận thêm đúng các tổ hợp có ít nhất một đồng đang xét, bao gồm trường hợp dùng nhiều lần.

Quan trọng hơn, vì vòng ngoài chỉ chuyển sang mệnh giá tiếp theo **sau khi xử lý xong một loại**, mỗi vector số lượng được xây theo **thứ tự chuẩn của các loại**. Nó không bị đếm lặp khi thứ tự chọn các đồng trong cùng một vector thay đổi.

## 4. Vết tính tổ hợp: mệnh giá [1,2,5], tổng 5

Khởi tạo `ways` có 6 ô, chỉ `ways[0]=1`:

```text
Chưa xét loại nào: [1, 0, 0, 0, 0, 0]

Sau mệnh giá 1:  [1, 1, 1, 1, 1, 1]

Sau mệnh giá 2:  [1, 1, 2, 2, 3, 3]

Sau mệnh giá 5:  [1, 1, 2, 2, 3, 4]
```

Diễn giải từng hàng:

- Với **chỉ đồng 1**, mỗi tổng `t` có đúng 1 tổ hợp: lấy `t` đồng mệnh giá 1.
- Khi thêm **loại 2**, tổng 4 có 3 tổ hợp: `1+1+1+1`, `1+1+2`, `2+2`.
- Khi thêm **loại 5**, tổng 5 có thêm một tổ hợp dùng đồng 5: `5`, nên tăng từ 3 lên **4**.

Tại mọi thời điểm sau khi xử lý loại thứ `i`:

> **Bất biến:** `ways[t]` bằng số tổ hợp tạo tổng `t` chỉ sử dụng các loại mệnh giá đã xử lý; mỗi vector số lượng được đếm đúng một lần.

Đây không chỉ là kinh nghiệm về thứ tự vòng lặp, mà là lý do thuật toán đúng.

## 5. Đếm thứ tự chọn tiền: thay cách chia trường hợp

Giờ ta muốn đếm số **chuỗi có thứ tự**. Đặt `P(t)` là số dãy mệnh giá có tổng bằng `t`, mỗi mệnh giá có thể xuất hiện vô hạn.

### Trường hợp cơ sở

```text
P(0) = 1       // Dãy rỗng
P(t) = 0       // Khi t < 0
```

Với `t>0`, phân loại **theo đồng xu cuối cùng** trong dãy. Nếu đồng cuối có mệnh giá `c`, phần phía trước là một dãy hợp lệ tạo tổng `t−c`. Các nhóm với đồng cuối khác nhau **không giao nhau**:

```text
P(t) = sum(P(t-c)) với mọi c thuộc coins và c <= t
```

Khác với công thức tổ hợp, ở đây trạng thái chỉ cần `t`, vì mỗi lần chọn **một đồng cuối** tạo ra một dãy mới có thứ tự. Tại mỗi tổng, ta phải xét **tất cả mệnh giá có thể đứng cuối**.

### Vòng lặp tương ứng

```java
// Lõi ý tưởng: coins là danh sách loại mệnh giá dương, không trùng.
ways[0] = BigInteger.ONE;

for (int t = 1; t <= amount; t++) {
    for (int coin : coins) {
        if (coin <= t) {
            ways[t] = ways[t].add(ways[t - coin]);
        }
    }
}
```

Đoạn này cũng là **lõi minh họa**; mảng `ways` cần khởi tạo đầy đủ. Thứ tự quyết định là:

- **Vòng ngoài: tổng `t` từ nhỏ lên lớn.**
- **Vòng trong: thử mọi loại mệnh giá làm bước cuối cùng.**

Khi tính `P(t)`, mọi `P(t−c)` đã được tính ở tổng nhỏ hơn vì `c>0`. Do vậy không có phụ thuộc vòng và không đếm trùng cùng một chuỗi: đồng cuối xác định đúng một nhóm, phần trước đó xác định một chuỗi ngắn hơn.

### Vết tính chuỗi có thứ tự cho [1,2,5]

```text
P(0) = 1
P(1) = P(0)                         = 1
P(2) = P(1) + P(0)                  = 2
P(3) = P(2) + P(1)                  = 3
P(4) = P(3) + P(2)                  = 5
P(5) = P(4) + P(3) + P(0)           = 9

Mảng P: [1, 1, 2, 3, 5, 9]
```

Với `t=3`, ba chuỗi là `[1,1,1]`, `[1,2]` và `[2,1]`. Hai chuỗi cuối có cùng tổ hợp nhưng được phân biệt bởi thứ tự.

**Lưu ý:** Nếu chỉ thay vòng lặp trong thuật toán tổ hợp thành tổng ngoài, đồng trong, thì đã **đổi bài toán**. Không thể gọi đó là “tối ưu” chỉ vì hai cách đều dùng một mảng `ways[]`.

## 6. So sánh trực diện hai mẫu DP một chiều

| Câu hỏi | Đếm tổ hợp không thứ tự | Đếm chuỗi chọn có thứ tự |
| --- | --- | --- |
| Đối tượng đếm | Vector số lượng theo mệnh giá | Dãy các lần chọn mệnh giá |
| Trạng thái tư duy | `C(i,t)`: xét `i` loại đầu | `P(t)`: tất cả dãy có tổng `t` |
| Vòng ngoài khi tối ưu 1D | **Mệnh giá** | **Tổng từ 1 lên A** |
| Vòng trong | **Tổng tăng từ coin lên A** | **Mọi mệnh giá hợp lệ** |
| Vì sao không đếm sai? | Xử lý loại theo thứ tự chuẩn, không đếm hoán vị | Chia dãy theo **đồng cuối cùng**, các nhóm rời nhau |
| `coins=[1,2]`, `A=3` | **2** | **3** |
| `coins=[1,2,5]`, `A=5` | **4** | **9** |
| Trường hợp `A=0` | **1** tổ hợp rỗng | **1** dãy rỗng |
| Thời gian số phép cộng | `O(kA)` | `O(kA)` |
| Bộ nhớ bảng số cách | `O(A)` | `O(A)` |

Hai cách có cùng **bậc độ phức tạp số phép chuyển tiếp** nhưng kết quả khác nhau vì **ngữ nghĩa và bất biến** khác nhau.

### Một ví dụ đối chiếu không có đồng 1

Với mệnh giá `[2,3]`, tổng `7`:

- Tổ hợp: chỉ `2+2+3`, nên **1**.
- Có thứ tự: `[2,2,3]`, `[2,3,2]`, `[3,2,2]`, nên **3**.

Với mệnh giá `[2,4]`, tổng `7`, cả hai đáp án là **0**, do mọi tổng tạo được đều chẵn. Không nên cho rằng kết quả 0 nghĩa là chưa tính xong trạng thái DP.

## 7. Vì sao thuật toán đúng? Chứng minh bằng bất biến

### 7.1. Tổ hợp: quy nạp theo mệnh giá

**Cơ sở:** Chưa có loại tiền nào, `ways[0]=1` và các tổng dương có `0` cách. Điều này khớp hoàn toàn với định nghĩa tổ hợp.

**Bước quy nạp:** Giả sử trước khi xử lý loại `c`, `ways[t]` là số tổ hợp chỉ dùng các loại trước đó. Với `t` tăng từ `c` đến `A`, thêm `ways[t−c]`:

- Các tổ hợp **không dùng** loại `c` đã nằm trong giá trị cũ `ways[t]`.
- Các tổ hợp **dùng ít nhất một** đồng `c` tương ứng duy nhất với các tổ hợp tạo `t−c` trong hệ đã gồm loại `c`.
- Do `t−c<t`, ô `ways[t−c]` đã cập nhật ở **chính vòng loại `c`**, nên chứa mọi khả năng dùng nhiều đồng `c`.
- Hai nhóm không giao nhau; không có tổ hợp nào bị bỏ sót hoặc đếm hai lần.

Vì vậy sau khi cập nhật `ways[t]`, giá trị đúng với các loại đã xử lý. Kết thúc tất cả loại, `ways[A]` là số tổ hợp cần tìm.

### 7.2. Có thứ tự: quy nạp theo tổng

**Cơ sở:** `ways[0]=1` ứng với dãy rỗng; với tổng âm có 0 dãy.

**Bước quy nạp:** Giả sử `ways[t']` đúng với mọi `t'<t`. Mọi dãy có tổng `t>0` đều có **một mệnh giá cuối cùng `c`**. Bỏ đồng cuối cho một dãy có tổng `t−c`, thuộc tập đã đếm bởi `ways[t−c]`. Ngược lại, nối đồng `c` vào cuối bất kỳ dãy tạo `t−c` sinh một dãy hợp lệ tổng `t`.

Nếu hai dãy có đồng cuối khác nhau, chúng là hai dãy khác nhau; nếu cùng đồng cuối, phần tiền tố phải khác thì chúng mới khác. Do đó tổng `Σ_c ways[t−c]` đếm mỗi dãy chính xác một lần.

### 7.3. Tại sao mọi phép chuyển tiếp kết thúc?

Các mệnh giá **dương** nên `t−c<t`. Với ordered DP, trạng thái phụ thuộc tổng nhỏ hơn. Với combinations 1D, tổng `t` tăng và giá trị cần đọc đã tồn tại. Cả hai đều dùng vòng lặp hữu hạn trên `k` và `A`.

Nếu cho phép mệnh giá **0** với số lần dùng vô hạn, có thể thêm bao nhiêu đồng 0 tùy thích vào một cách tạo tổng có sẵn, dẫn tới **vô hạn cách** (theo mô hình đếm số lần chọn). Nếu cho phép mệnh giá âm, đệ quy có thể tạo chu trình hoặc vô hạn cách. Vì vậy mã minh họa từ chối mọi `c≤0` thay vì âm thầm cho kết quả không có nghĩa theo đặc tả đã chọn.

## 8. Dữ liệu trùng, nhiều loại đồng xu và giới hạn tồn kho

### 8.1. Mệnh giá trùng có được xem là hai loại?

Giả sử input nhập `[1,2,2,5]`. Nếu hai số `2` là cùng **mệnh giá**, danh sách đó phải được chuẩn hóa thành `[1,2,5]` trước khi đếm. Nếu lặp qua hai mục `2` như hai **loại riêng** trong bài không giới hạn, cùng một cách lấy đồng 2 bị xem như có hai “màu” khác nhau, dẫn đến **đếm thừa** so với yêu cầu chỉ phân biệt mệnh giá.

Ví dụ `coins=[1,1]`, `A=1`:

- Nếu hai mục cùng biểu thị **mệnh giá 1**, cả tổ hợp lẫn chuỗi theo mệnh giá chỉ có **1** cách.
- Nếu chúng biểu thị **hai loại tiền có nhãn A và B khác nhau**, có thể có **2** cách chọn một đồng 1; đó là **một bài toán khác** vì danh tính loại tiền có nghĩa.

Chương trình Java trong bài nhận input là **danh sách mệnh giá**, tạo bản sao, sắp tăng rồi **loại mệnh giá trùng**; mọi phương pháp unbounded dùng danh sách đã chuẩn hóa.

### 8.2. Nếu mỗi loại có số lượng tồn kho hữu hạn

Giả sử mệnh giá `c_i` chỉ có tối đa `s_i` đồng. Với **tổ hợp không thứ tự**, trạng thái hai chiều có thể viết:

```text
B(i,t) = số tổ hợp tạo t chỉ dùng i loại đầu,
         mỗi loại j không quá s_j đồng.

B(0,0) = 1, B(0,t>0) = 0

B(i,t) = sum_{u=0..min(s_i, floor(t/c_i))}
           B(i-1, t-u*c_i)
```

Ta xét **tất cả số lượng `u` của loại hiện tại**, không đếm thứ tự. Có thể dùng hai hàng `previous` và `next`, vì mỗi loại chỉ đọc hàng loại trước. Cách cài đặt ba vòng trực tiếp có chi phí theo số lượng hợp lệ của `u`, về tổng quát:

```text
O(A * sum_i (min(s_i, floor(A/c_i)) + 1))
```

với `A` là tổng đích. Có các tối ưu bằng tổng trượt trên những lớp đồng dư để giảm chi phí, nhưng cần chứng minh riêng; không áp dụng máy móc vòng unbounded khi còn giới hạn tồn kho.

Ví dụ `coins=[1,2]`, `stock=[2,1]`, `A=4`:

```text
1+1+2 = 4

=> đúng 1 tổ hợp hợp lệ.
```

Không thể lấy `2+2` vì chỉ có **một** đồng 2; không thể lấy bốn đồng 1 vì chỉ có hai đồng 1.

### 8.3. Nếu mỗi **đồng vật lý** được dùng tối đa một lần (0/1)

Với các **đồng có danh tính riêng**, một cách chọn là một tập con các vật thể. Mảng `ways[t]` được cập nhật **giảm dần**:

```java
// Mỗi phần tử coins là một đồng vật lý dương, chỉ dùng 0 hoặc 1 lần.
for (int coin : coins) {
    for (int t = amount; t >= coin; t--) {
        ways[t] = ways[t].add(ways[t - coin]);
    }
}
```

Vì `t` giảm, `ways[t−coin]` **chưa được cập nhật bởi chính đồng đang xét**, nên một đồng không bị dùng lại hai lần trong cùng vòng. Đây là ý nghĩa **0/1**.

Nhưng nếu hai đồng vật lý có cùng giá trị, chúng vẫn là **hai đối tượng**. Ví dụ các đồng `[1_A,1_B,2_C]`, tổng `2`:

- Tập con `{2_C}`;
- Tập con `{1_A,1_B}`.

Có **2 tập con**, đúng với bản 0/1. Nếu lại có một đồng `2_D` riêng biệt, tập `{2_D}` là **một tập con khác**, mặc dù hai tập `{2_C}` và `{2_D}` có cùng vector số lượng theo mệnh giá. Vì thế kết quả “đếm tập con các đồng vật lý” không đồng nghĩa “đếm số tổ hợp mệnh giá” khi có các đồng trùng giá trị.

### 8.4. Nếu vừa giới hạn tồn kho vừa quan tâm thứ tự

Đây là bài **đếm chuỗi chọn tiền dưới ràng buộc số lượng**. Không thể dùng `P(t)=ΣP(t−c)` một chiều nếu còn phụ thuộc số đồng mỗi loại đã dùng. Một trạng thái tự nhiên là **vector tồn kho còn lại** hoặc số đồng đã dùng theo từng loại; thêm một đồng làm thay đổi vector đó. Số trạng thái có thể lớn cỡ tích `∏(s_i+1)` (trước khi loại các trạng thái không đạt được), nên cần đánh giá kỹ.

Một số bài toán có thể đếm bằng cách chọn vector số lượng trước rồi tính số thứ tự:

```text
Với vector (x_1,...,x_k) có tổng r = sum(x_i),
số chuỗi phân biệt theo mệnh giá =
r! / (x_1! * x_2! * ... * x_k!)
```

Đây là hệ số đa thức (*multinomial coefficient*). Tổng hệ số trên mọi vector thỏa điều kiện tổng `A` và giới hạn tồn kho sẽ cho số chuỗi chọn theo **mệnh giá**. Không nhân thêm hoán vị nếu bài chỉ hỏi **tổ hợp**.

## 9. Kết quả lớn, kiểm soát phạm vi và lựa chọn kiểu dữ liệu

Số cách có thể tăng rất nhanh. Kể cả khi tổng đích không lớn theo cảm nhận thông thường, số **chuỗi có thứ tự** có thể vượt `Integer.MAX_VALUE` hoặc `Long.MAX_VALUE`.

Các lựa chọn:

- **`BigInteger`:** Trả kết quả chính xác, nhưng phép cộng trên các số lớn không còn có chi phí hằng theo số bit; tốn thêm bộ nhớ và thời gian. Đây là lựa chọn của chương trình chính.
- **Modulo `M`:** Nếu đề yêu cầu “số cách modulo `1_000_000_007`”, có thể lưu số nguyên dư và cộng modulo ở từng bước. Kết quả **không phải số cách đầy đủ**, mà là số dư theo `M`. Không dùng modulo nếu người dùng cần giá trị chính xác.
- **`long`:** Chỉ dùng nếu có chứng minh hoặc ràng buộc đảm bảo đáp án không vượt phạm vi. Không được giả định mọi bài đếm tiền nhỏ đều an toàn.
- **Ngưỡng chặn/bão hòa:** Nếu bài chỉ cần biết “ít nhất `K` cách”, có thể dùng đếm bão hòa và cập nhật `min(K,ways)`, nhưng phải nêu rõ đáp án không chính xác khi vượt ngưỡng.

### Một số trường hợp biên

| Input | Số tổ hợp | Số chuỗi có thứ tự |
| --- | ---: | ---: |
| `coins=[]`, `A=0` | 1 | 1 |
| `coins=[]`, `A=5` | 0 | 0 |
| `coins=[1]`, `A=5` | 1 | 1 |
| `coins=[5]`, `A=3` | 0 | 0 |
| `coins=[2,4]`, `A=7` | 0 | 0 |
| `coins=[1,2]`, `A=3` | 2 | 3 |
| `coins=[1,2,5]`, `A=5` | 4 | 9 |
| `coins=[1,2,2,5]`, `A=5`, **chuẩn hóa trùng** | 4 | 9 |
| `coins=[1,2,5]`, `A=0` | 1 | 1 |

**Cận nhanh bằng ước chung lớn nhất:** Nếu tất cả mệnh giá dương có `g=gcd(c_1,...,c_k)`, mọi tổng tạo được đều là bội của `g`. Vì thế nếu `A%g!=0` thì số cách chắc chắn **0**. Điều ngược lại **không luôn đúng**: `A` chia hết cho `g` chưa đảm bảo có cách, ví dụ `coins=[4,6]` có `g=2` nhưng tổng `2` vẫn không tạo được. Có thể dùng điều kiện này để bỏ sớm bài toán bất khả thi khi các mệnh giá rất lớn, nhưng không nhất thiết cần trong mã minh họa.

**Mệnh giá lớn hơn tổng:** Một loại `c>A` không thể góp vào cách tạo tổng `A` nên có thể bỏ qua khi cập nhật DP; chương trình unbounded tự làm điều đó qua điều kiện vòng lặp/break. Việc có một đồng lớn không làm các cách đếm trước đó sai.

**Chọn số tiền âm:** Tổng đích `A<0` nằm ngoài mô hình mệnh giá dương này; chương trình báo lỗi rõ thay vì cấp phát mảng kích thước âm.

**Bài ít đồng xu nhất khác với bài đếm số cách.** Nếu cần **tối thiểu số đồng**, dùng `min` trên các phương án khả thi. Nếu cần **số cách**, dùng phép cộng `+` trên những lớp phương án rời nhau. Thay `+` bằng `min` hoặc ngược lại sẽ đổi bài toán, dù dạng bảng có vẻ tương tự.

## 10. Java 17+ — các công thức đếm và kiểm thử độc lập

Chương trình **CoinWaysDemo.java** có bốn cách đếm:

1. `countCombinations`: mệnh giá **không giới hạn**, **không phân biệt thứ tự**; vòng ngoài theo mệnh giá, vòng trong theo tổng tăng dần.
2. `countOrdered`: mệnh giá **không giới hạn**, **phân biệt thứ tự**; vòng ngoài theo tổng, vòng trong theo loại mệnh giá.
3. `countBoundedCombinations`: tồn kho `stock[i]` theo từng **mệnh giá phân biệt**, không phân biệt thứ tự; chuyển tiếp duyệt số lượng được chọn của mỗi loại.
4. `countPhysicalSubsetsOnce`: mỗi mục trong mảng là **một đồng vật lý riêng** được lấy 0 hoặc 1 lần; vòng tổng giảm dần.

Tất cả trả `BigInteger` để tránh tràn kiểu số trong kết quả. Hai phương pháp unbounded loại **mệnh giá trùng** vì đối tượng đếm là chuỗi/tổ hợp **theo mệnh giá**. Phương pháp theo đồng vật lý **không loại trùng**, vì các vật thể có cùng giá trị vẫn phân biệt.

Mã còn có hai phương pháp brute force độc lập dùng cho input nhỏ: **liệt kê vector số lượng** để đếm tổ hợp và **liệt kê từng chuỗi** để đếm thứ tự, sau đó đối chiếu mọi tập con của các mệnh giá `{1,2,3,4,5}` ở các tổng `0..12`.

### Toàn bộ mã nguồn

Lưu thành tệp **CoinWaysDemo.java**:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;

public class CoinWaysDemo {
    static void checkAmount(int amount) {
        if (amount < 0 || amount == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("invalid amount");
        }
    }

    // Mỗi giá trị dương chỉ đại diện cho một loại mệnh giá.
    // Không sửa mảng input; bản sao được sắp rồi khử trùng.
    static int[] distinctDenominations(int[] input) {
        Objects.requireNonNull(input, "input");
        int[] sorted = input.clone();
        Arrays.sort(sorted);
        int used = 0;

        for (int coin : sorted) {
            if (coin <= 0) {
                throw new IllegalArgumentException(
                    "denominations must be positive");
            }
            if (used == 0 || sorted[used - 1] != coin) {
                sorted[used++] = coin;
            }
        }
        return Arrays.copyOf(sorted, used);
    }

    static BigInteger[] initialWays(int amount) {
        BigInteger[] ways = new BigInteger[amount + 1];
        Arrays.fill(ways, BigInteger.ZERO);
        ways[0] = BigInteger.ONE;
        return ways;
    }

    // UNBOUNDED + không phân biệt thứ tự.
    static BigInteger countCombinations(int[] input, int amount) {
        checkAmount(amount);
        int[] coins = distinctDenominations(input);
        BigInteger[] ways = initialWays(amount);

        for (int coin : coins) {
            for (int t = coin; t <= amount; t++) {
                ways[t] = ways[t].add(ways[t - coin]);
            }
        }
        return ways[amount];
    }

    // UNBOUNDED + phân biệt thứ tự chọn các mệnh giá.
    static BigInteger countOrdered(int[] input, int amount) {
        checkAmount(amount);
        int[] coins = distinctDenominations(input);
        BigInteger[] ways = initialWays(amount);

        for (int t = 1; t <= amount; t++) {
            for (int coin : coins) {
                if (coin > t) {
                    break; // coins đã tăng dần.
                }
                ways[t] = ways[t].add(ways[t - coin]);
            }
        }
        return ways[amount];
    }

    // BOUNDED theo loại mệnh giá. coins phải dương, duy nhất,
    // tăng nghiêm ngặt; stock[i] >= 0 và là tồn kho của coins[i].
    static BigInteger countBoundedCombinations(
            int[] coins, int[] stock, int amount) {
        checkAmount(amount);
        Objects.requireNonNull(coins, "coins");
        Objects.requireNonNull(stock, "stock");
        if (coins.length != stock.length) {
            throw new IllegalArgumentException("lengths differ");
        }

        int previousCoin = 0;
        for (int i = 0; i < coins.length; i++) {
            if (coins[i] <= previousCoin || stock[i] < 0) {
                throw new IllegalArgumentException(
                    "coins must increase, stock must be nonnegative");
            }
            previousCoin = coins[i];
        }

        BigInteger[] ways = initialWays(amount);
        for (int i = 0; i < coins.length; i++) {
            BigInteger[] next = new BigInteger[amount + 1];
            Arrays.fill(next, BigInteger.ZERO);

            for (int t = 0; t <= amount; t++) {
                for (int taken = 0;
                        taken <= stock[i]
                        && (long) taken * coins[i] <= t;
                        taken++) {
                    int remainder = (int) (t - (long) taken * coins[i]);
                    next[t] = next[t].add(ways[remainder]);
                }
            }
            ways = next;
        }
        return ways[amount];
    }

    // Mỗi phần tử là một đồng vật lý riêng, dùng tối đa một lần.
    // Hai đồng cùng giá trị vẫn phân biệt bằng vị trí trong input.
    static BigInteger countPhysicalSubsetsOnce(
            int[] physicalCoins, int amount) {
        checkAmount(amount);
        Objects.requireNonNull(physicalCoins, "physicalCoins");
        BigInteger[] ways = initialWays(amount);

        for (int coin : physicalCoins) {
            if (coin <= 0) {
                throw new IllegalArgumentException(
                    "physical coin value must be positive");
            }
            for (int t = amount; t >= coin; t--) {
                ways[t] = ways[t].add(ways[t - coin]);
            }
        }
        return ways[amount];
    }

    // Oracle độc lập: liệt kê mọi vector số lượng (không có thứ tự).
    // Chỉ dùng với danh sách mệnh giá dương đã phân biệt và tổng nhỏ.
    static long bruteCombinations(int[] coins, int index, int amount) {
        if (index == coins.length) {
            return amount == 0 ? 1L : 0L;
        }
        long result = 0L;
        for (int count = 0; (long) count * coins[index] <= amount;
                count++) {
            result += bruteCombinations(
                coins, index + 1, amount - count * coins[index]);
        }
        return result;
    }

    // Oracle độc lập: liệt kê tất cả chuỗi mệnh giá.
    // Không có cache; chỉ dùng với tổng rất nhỏ.
    static long bruteOrdered(int[] coins, int amount) {
        if (amount == 0) {
            return 1L;
        }
        long result = 0L;
        for (int coin : coins) {
            if (coin <= amount) {
                result += bruteOrdered(coins, amount - coin);
            }
        }
        return result;
    }

    static int exhaustiveCheck() {
        int cases = 0;

        // 2^5 = 32 tập con mệnh giá của {1,2,3,4,5}.
        for (int mask = 0; mask < 32; mask++) {
            int[] coins = new int[Integer.bitCount(mask)];
            int index = 0;
            for (int c = 1; c <= 5; c++) {
                if ((mask & (1 << (c - 1))) != 0) {
                    coins[index++] = c;
                }
            }

            // 13 tổng: 0..12.
            for (int target = 0; target <= 12; target++) {
                BigInteger comb = countCombinations(coins, target);
                BigInteger ordered = countOrdered(coins, target);
                long expectedComb =
                    bruteCombinations(coins, 0, target);
                long expectedOrdered = bruteOrdered(coins, target);

                if (!comb.equals(BigInteger.valueOf(expectedComb))
                        || !ordered.equals(
                            BigInteger.valueOf(expectedOrdered))) {
                    throw new AssertionError(
                        "Mismatch coins=" + Arrays.toString(coins)
                        + " target=" + target);
                }
                cases++;
            }
        }
        return cases;
    }

    public static void main(String[] args) {
        int[] raw = {5, 1, 2, 2};
        int[] original = raw.clone();
        System.out.println("Raw coins: " + Arrays.toString(raw));
        System.out.println("Distinct types: "
                           + Arrays.toString(distinctDenominations(raw)));

        System.out.println("Target 5 combinations: "
                           + countCombinations(raw, 5));
        System.out.println("Target 5 ordered: "
                           + countOrdered(raw, 5));

        int[] coins = {1, 2, 5};
        for (int target = 0; target <= 5; target++) {
            System.out.println(
                "t=" + target
                + " comb=" + countCombinations(coins, target)
                + " ordered=" + countOrdered(coins, target));
        }

        int[] twoThree = {2, 3};
        System.out.println("Coins [2,3], target 7: "
                           + countCombinations(twoThree, 7)
                           + " combinations, "
                           + countOrdered(twoThree, 7)
                           + " ordered");
        System.out.println("Coins [2,4], target 7: "
                           + countCombinations(new int[]{2, 4}, 7)
                           + " combinations");

        System.out.println("Empty types, target 0: "
                           + countCombinations(new int[0], 0)
                           + " combinations, "
                           + countOrdered(new int[0], 0)
                           + " ordered");
        System.out.println("Empty types, target 3: "
                           + countCombinations(new int[0], 3)
                           + " combinations, "
                           + countOrdered(new int[0], 3)
                           + " ordered");

        System.out.println("Bounded [1x2,2x1], target 4: "
                           + countBoundedCombinations(
                               new int[]{1, 2}, new int[]{2, 1}, 4));
        System.out.println("Physical [1A,1B,2C], target 2: "
                           + countPhysicalSubsetsOnce(
                               new int[]{1, 1, 2}, 2));
        System.out.println("Input unchanged: "
                           + Arrays.equals(raw, original));
        System.out.println("Exhaustive: "
                           + exhaustiveCheck()
                           + " cases (32 sets x 13 targets) OK");
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac -encoding UTF-8 CoinWaysDemo.java
java CoinWaysDemo
```

Stdout dự kiến:

```text
Raw coins: [5, 1, 2, 2]
Distinct types: [1, 2, 5]
Target 5 combinations: 4
Target 5 ordered: 9
t=0 comb=1 ordered=1
t=1 comb=1 ordered=1
t=2 comb=2 ordered=2
t=3 comb=2 ordered=3
t=4 comb=3 ordered=5
t=5 comb=4 ordered=9
Coins [2,3], target 7: 1 combinations, 3 ordered
Coins [2,4], target 7: 0 combinations
Empty types, target 0: 1 combinations, 1 ordered
Empty types, target 3: 0 combinations, 0 ordered
Bounded [1x2,2x1], target 4: 1
Physical [1A,1B,2C], target 2: 2
Input unchanged: true
Exhaustive: 416 cases (32 sets x 13 targets) OK
```

### Phân tích chi tiết các hàm Java

**`distinctDenominations`:** Dùng `input.clone()` trước khi sort để không thay đổi dữ liệu của caller. Duyệt mảng đã tăng dần, giữ lại đúng một bản sao cho mỗi giá trị dương. Bài unbounded theo mệnh giá không được xem hai mục bằng nhau là hai loại độc lập.

**`initialWays`:** Khởi tạo `BigInteger.ZERO` cho toàn bộ tổng dương và `BigInteger.ONE` cho tổng 0. Không dùng `null` như số cách 0 và không dùng `0` làm chỉ dấu “chưa tính”: đây là tabulation, các giá trị được cập nhật theo đúng vòng lặp.

**`countCombinations`:** Mỗi loại chỉ có một vòng ngoài. Tổng chạy tăng từ `coin` lên `A`; bởi vậy có thể dùng thêm **nhiều đồng cùng loại** trong một tổ hợp, nhưng không tạo nhiều bản sao do các cách xếp lại thứ tự.

**`countOrdered`:** Tổng chạy từ `1` lên `A`. Với mỗi tổng, lần lượt thử các mệnh giá có thể đứng cuối; mọi `ways[t−coin]` đã hoàn tất vì `coin>0`. Danh sách được sort giúp dừng vòng thử khi `coin>t`.

**`countBoundedCombinations`:** Input mệnh giá phải tăng nghiêm ngặt và tồn kho không âm, để mỗi tọa độ là một loại riêng. Mỗi hàng mới thử số đồng `taken` từ `0` đến giới hạn và chỉ **đọc hàng trước**, nên không vượt tồn kho. Hai hàng dùng `O(A)` tham chiếu BigInteger ngoài mảng đầu vào.

**`countPhysicalSubsetsOnce`:** Ở mỗi đồng vật lý, vòng tổng giảm ngăn dùng lại đồng vừa xét. Hai đồng vật lý cùng mệnh giá được xem là hai đối tượng, phù hợp với bài đếm **tập con vật thể**.

**`bruteCombinations` và `bruteOrdered`:** Đây là oracle độc lập trên input nhỏ: hàm đầu thử trực tiếp số lượng của từng loại, hàm sau sinh mọi thứ tự chọn có thể. Chúng không lấy đáp án DP làm nguồn expected. Với mục đích kiểm thử, hàm brute không dùng memo và có thể tăng thời gian rất nhanh khi tổng lớn.

**`exhaustiveCheck`:** Duyệt tất cả **32 tập con** (bao gồm tập rỗng) của `{1,2,3,4,5}`, với **13 tổng từ 0 đến 12**, thành **416 ca**. Trên mỗi ca, đối chiếu hai phương pháp DP với hai bộ đếm brute độc lập. Kiểm thử này hữu ích để phát hiện sai chiều vòng lặp và lỗi base case; không thay thế chứng minh bất biến tổng quát.

### Bộ nhớ, số bit và độ phức tạp thật

Với `k` mệnh giá phân biệt và tổng `A`:

- Chuẩn hóa đầu vào gồm clone + sort + dedup: **`O(k log k)` thời gian**, **`O(k)` bộ nhớ phụ** cho bản sao, không tính chi phí runtime sort trên mảng nguyên thủy.
- Unbounded combinations và ordered: **`O(kA)` phép chuyển tiếp/cộng BigInteger**, **`O(A+k)` vị trí lưu tham chiếu** ngoài input. Với `BigInteger`, phép cộng có chi phí theo số bit của các số hạng và mỗi kết quả có thể cần cấp phát đối tượng mới.
- Bounded combinations theo stock: số phép cộng bị chặn bởi **`O(A·Σ_i(min(s_i,⌊A/c_i⌋)+1))`** và bộ nhớ bảng hai hàng **`O(A)`**; còn chi phí BigInteger phụ thuộc độ lớn đáp án.
- Physical subset 0/1: **`O(kA)` phép cộng**, **`O(A)` bộ nhớ bảng**; các đồng trùng mệnh giá vẫn tính riêng.
- Phương pháp brute chỉ thích hợp cho trường hợp nhỏ. Đếm toàn bộ mọi chuỗi có thể tốn thời gian theo số lượng chuỗi, vốn có thể tăng theo hàm mũ.

**Đừng nhầm “`O(kA)`” với chi phí đa thức theo độ dài input nhị phân:** Nếu `A` rất lớn được biểu diễn bằng vài chục bit, mảng dài `A+1` vẫn khổng lồ. Đây là thuật toán **giả đa thức (pseudo-polynomial)** theo giá trị tổng đích, không hẳn là đa thức theo số bit biểu diễn tổng.

Khi `A` quá lớn, cần xem lại bộ nhớ, có thể dùng toán tổ hợp, hàm sinh, ma trận chuyển tiếp hoặc thuật toán chuyên biệt phù hợp với giới hạn đề. Không cấp phát `BigInteger[A+1]` mù quáng khi không đủ RAM.

## 11. Liên hệ với các bài DP tài nguyên khác

**Khả năng tạo được tổng (subset/coin feasibility):** Chỉ cần một giá trị boolean cho mỗi tổng. Công thức dùng `OR` thay vì cộng số cách. Có thể lưu bằng bitset để tăng hiệu quả, nhưng đáp án chỉ là **có/không**, không nói có bao nhiêu cách.

**Số đồng xu ít nhất:** Dùng `min` trên số đồng; các trạng thái không thể cần sentinel `INF`. Kết quả không liên quan trực tiếp đến số tổ hợp/hoán vị. Một tổng có thể có nhiều cách nhưng chỉ một số ít cách đạt tối ưu.

**Ba lô 0/1:** Khi mỗi đồ vật được chọn tối đa một lần, dùng vòng tổng giảm trong nhiều bài DP một chiều. Khi mục tiêu là tối đa giá trị, cập nhật `max`; khi mục tiêu đếm tập con, cập nhật `+`. Chiều vòng lặp giữ đúng ràng buộc 0/1, còn toán tử kết hợp xác định bài tối ưu hay bài đếm.

**Bài phân phối tiền theo người/nhóm:** Nếu có nhiều người nhận và mỗi đồng có thể được phân cho người khác nhau, đối tượng đếm bao gồm **phân bổ** chứ không chỉ vector mệnh giá, nên phải bổ sung trạng thái và xác định có phân biệt người hay không. Không lấy công thức đổi tiền chuẩn rồi thay tên biến.

**Đếm đường đi:** Nếu bước có độ dài thuộc các tập `coins`, số cách đi **theo thứ tự các bước** đến vị trí `A` dùng truy hồi `P(A)=ΣP(A−c)`. Đây là cùng công thức với ordered coin sequences. Nếu chỉ đếm số lượng mỗi loại bước mà không quan tâm thứ tự, bài toán khác đi.

**Đếm cách phân hoạch số nguyên:** Nếu cho phép mọi mệnh giá từ `1` đến `A` và không phân biệt thứ tự, số cách biểu diễn `A` thành tổng các số nguyên dương chính là **số phân hoạch nguyên**. Nếu phân biệt thứ tự và cho mọi số nguyên dương làm bước, với `A≥1` sẽ có **`2^(A−1)` chuỗi**: mỗi một trong `A−1` khe giữa các đơn vị có thể chọn ngắt hay không ngắt. Hai bài tăng trưởng rất khác nhau dù đều dựa vào cộng các số dương.

**Truy vấn nhiều tổng trên cùng danh sách mệnh giá:** Có thể tính toàn bộ `ways[0..Amax]` một lần rồi trả nhiều truy vấn tổng trong miền đó, miễn là **tập mệnh giá và quy tắc đếm không đổi**. Nếu thêm, xóa hoặc đổi mệnh giá, bảng DP cũ không còn diễn giải đúng và phải được cập nhật hợp lệ hoặc xây lại. Một bảng combinations đã xây cho loại coin mới không thể tái sử dụng nguyên xi làm bảng ordered chỉ bằng cách đổi tên.

## 12. Các lỗi thường gặp và cách sửa

**1. Không hỏi rõ “có phân biệt thứ tự không”.** Hai bài cùng mệnh giá và tổng có thể cho kết quả 4 hoặc 9. Viết ví dụ rất nhỏ `[1,2], A=3` trước khi chọn công thức.

**2. Đổi vị trí vòng `for` mà không đổi diễn giải.** Coin ngoài, tổng tăng → **combinations**. Tổng ngoài, coin trong → **ordered**. Không chọn vòng theo sở thích.

**3. Dùng vòng tổng giảm cho coin unbounded.** Tổng giảm chỉ lấy mỗi loại tối đa một lần trong vòng cập nhật; nếu đề cho dùng vô hạn, kết quả bị thiếu. Với unbounded combinations, tổng phải **tăng**.

**4. Dùng vòng tổng tăng cho mỗi đồng vật lý 0/1.** Một đồng đang xét có thể bị dùng lại ngay trong vòng, khiến code đếm trường hợp vi phạm ràng buộc “mỗi đồng một lần”.

**5. Không khởi tạo `ways[0]=1`.** Không có tổ hợp/dãy rỗng làm cơ sở, mọi phép cộng thường sẽ cho 0, dù rõ ràng có phương án.

**6. Hiểu sai tổng bằng 0.** Với mệnh giá dương và có thể chọn 0 đồng, tổng 0 có **1 cách rỗng**, không phải 0 cách. Nếu đề có quy ước phải chọn ít nhất một đồng, phải viết lại hợp đồng, đặc biệt với coin 0 hoặc âm.

**7. Cho phép mệnh giá 0 hoặc âm trong bài unbounded.** Có thể tạo vô hạn cách hoặc phụ thuộc chu trình; mã ví dụ chủ động từ chối để bài toán hữu hạn và chuyển tiếp giảm tổng.

**8. Không khử mệnh giá trùng.** `[1,1]` không nên tạo hai loại 1 nếu chỉ đếm theo mệnh giá. Nếu chúng là hai vật thể khác nhau, phải dùng một mô hình **theo danh tính vật thể**, không tự xóa trùng.

**9. Dùng `int` mà quên overflow.** Số cách có thể rất lớn; chọn `BigInteger` hoặc modulo theo đặc tả. Một số âm do overflow không phải số cách hợp lệ.

**10. Đồng nhất tổ hợp với tập con đồng xu vật lý.** Hai đồng cùng mệnh giá có thể được xem là hai vật thể riêng trong bài tập con, nhưng không là hai mệnh giá riêng trong bài tổ hợp.

**11. Nhầm giới hạn tồn kho.** Với stock hữu hạn, không thể dùng thuật toán unbounded rồi hy vọng kết quả tự tuân theo `s_i`. Cần biến số lượng `taken` hoặc một chiến lược bounded tương đương.

**12. Cho rằng tất cả mệnh giá có `gcd=1` thì mọi tổng dương đều tạo được.** Với `[4,7]`, `gcd=1` nhưng tổng `1`, `2`, `3` đều bất khả thi; gcd chỉ là điều kiện cần cho các tổng đạt được.

**13. Dùng công thức đếm số cách để tìm ít đồng xu nhất.** Mục tiêu đếm dùng phép cộng số cách ở các trường hợp rời nhau; tối ưu số đồng dùng `min` và trạng thái không thể.

**14. Không kiểm tra bộ nhớ với tổng lớn.** Mảng dài `A+1` có thể không vừa heap, và các đối tượng BigInteger lớn tốn thêm dung lượng. `O(A)` vẫn rất lớn khi `A` lớn.

**15. Chỉ test các mảng có đồng 1.** Khi không có đồng 1, nhiều tổng không thể tạo; test `[2,4],A=7` hoặc mảng mệnh giá rỗng giúp phát hiện lỗi khởi tạo và unreachable states.

**16. Quên tính cả cấu hình vào khóa cache.** Nếu có memoization giữa nhiều lần gọi với các bộ mệnh giá khác nhau, chỉ cache theo tổng `t` là không đủ. Mã ví dụ tạo bảng mới trong mỗi lời gọi, tránh tái sử dụng dữ liệu cũ sai ngữ nghĩa.

## 13. Bài tập tự luyện

**Bài 1 — Tổ hợp và thứ tự:** Với `coins=[1,2,3]`, `A=4`, liệt kê đầy đủ các tổ hợp và các chuỗi có thứ tự. So sánh kết quả (**4 tổ hợp**, **7 chuỗi**) với hai công thức DP.

**Bài 2 — Bảng một chiều:** Dùng `coins=[1,2,5]`, `A=5`. Ghi toàn bộ `ways[0..5]` sau khi xử lý từng loại coin ở thuật toán combinations; rồi tính dãy `P(0..5)` cho ordered. Giải thích tại sao `ways[5]` lần lượt là 4 và 9.

**Bài 3 — Đảo thứ tự vòng lặp:** Chạy hai dạng vòng lặp trên `[1,2]`, `A=3` và viết hai bất biến khác nhau. Vì sao thuật toán ordered không bị đếm trùng khi xét các đồng cuối?

**Bài 4 — Loại mệnh giá trùng:** Với `input=[1,1,2]` và `A=3`, tính theo **mệnh giá phân biệt**. Sau đó giả sử hai đồng 1 có nhãn khác nhau và chỉ dùng mỗi vật thể một lần: có còn cùng một tập cách không?

**Bài 5 — Tồn kho hữu hạn:** Với `coins=[1,2]`, `stock=[2,1]`, `A=4`, lập bảng `B(i,t)`; liệt kê các vector số lượng hợp lệ và thử thay `stock` thành `[4,2]`. So sánh với unbounded.

**Bài 6 — Tổng bất khả thi:** Với `[2,4]` và `A=7`, giải thích vì sao cả hai đáp án bằng 0. Với `[4,6]`, `A=2`, phân tích tại sao `A%gcd==0` vẫn chưa đủ để bảo đảm có cách.

**Bài 7 — Bài 0/1 theo vật thể:** Với các đồng vật lý `[1_A,1_B,2_C]` và `A=2`, đếm các tập con. Vẽ mảng DP sau từng đồng khi tổng duyệt giảm; vì sao duyệt tăng là sai?

**Bài 8 — Chứng minh:** Viết chứng minh quy nạp của `C(i,t)=C(i−1,t)+C(i,t−c_i)`. Nêu hai tập trường hợp rời nhau và ánh xạ từ tổ hợp có ít nhất một đồng `c_i` về bài toán con.

**Bài 9 — Số cách lớn:** Với `coins=[1,2,3,4,5]` và `A` tăng dần, hãy so sánh khi dùng `int`, `long`, `BigInteger` và modulo `1_000_000_007`. Vì sao modulo không thích hợp nếu đề cần số cách đầy đủ?

**Bài 10 — Chọn thuật toán:** Đề A yêu cầu “số cách tạo 10 nghìn đồng bằng mệnh giá [1,2,5], thứ tự không tính”; đề B yêu cầu “số dãy thao tác cộng 1/2/5 tới tổng 10”; đề C có mỗi mệnh giá tồn kho hữu hạn; đề D là tập các đồng vật lý khác nhau. Hãy chỉ rõ trạng thái, vòng lặp và ý nghĩa một cách của từng đề.

**Bài 11 — Bổ sung trường hợp biên:** Kiểm thử mệnh giá rỗng, tổng 0, đồng lớn hơn tổng, không có cách tạo, input trùng, tổng âm, mệnh giá 0 hoặc âm. Phân biệt input bị từ chối với trường hợp hợp lệ nhưng có 0 cách.

**Bài 12 — Khôi phục một cách tạo tiền:** DP trong bài chỉ đếm số cách, không lưu cụ thể từng vector hay dãy. Hãy thiết kế backtracking có giới hạn số kết quả in ra và so sánh với cách chỉ tính số cách. Vì sao không nên cố liệt kê tất cả khi số cách cực lớn?

## 14. Checklist trước khi nộp lời giải

1. **Đếm đối tượng gì?** Vector số lượng mệnh giá, chuỗi lựa chọn, tập con vật thể hay một dạng phân bổ khác?
2. **Thứ tự có ý nghĩa?** Có phân biệt `1+2` và `2+1` không? Ví dụ nhỏ có đáp án kỳ vọng rõ không?
3. **Giới hạn dùng đồng:** Vô hạn, `s_i` đồng theo loại, hay mỗi vật thể tối đa một lần?
4. **Trùng mệnh giá:** Là input trùng vô ý cần khử hay các loại/vật thể có nhãn phân biệt?
5. **Trạng thái và cơ sở:** Tổng 0 có đúng một cách rỗng không? Tổng âm/không tạo được xử lý thế nào?
6. **Vòng lặp:** Combination unbounded → coin ngoài, tổng tăng. Ordered unbounded → tổng ngoài, coin trong. Physical 0/1 → mỗi vật thể ngoài, tổng giảm.
7. **Chứng minh không trùng/không thiếu:** Bài combination chia theo số loại đang xét; bài ordered chia theo đồng cuối; các nhóm có rời nhau và bao phủ không?
8. **Giá trị lớn:** Dùng `BigInteger` hay modulo? Đã tính cả số bit, RAM và nguy cơ cấp phát mảng quá lớn chưa?
9. **Dữ liệu hợp lệ:** Mọi coin dương? Tổng đích không âm? Có cần báo lỗi cho tồn kho âm hoặc mảng `null`?
10. **Tối ưu phù hợp:** Nếu có nhiều truy vấn tổng trên cùng mệnh giá, có thể tiền xử lý bảng; nếu mệnh giá đổi, phải tạo lại hoặc cập nhật đúng.
11. **Kiểm thử độc lập:** Dùng brute force đếm vector tổ hợp và liệt kê dãy thứ tự với tập mệnh giá/tổng nhỏ, không chỉ so hai bản DP với nhau.

**Tiêu chí hoàn thành:** Bạn có thể giải thích bằng ví dụ vì sao **tổ hợp** khác **chuỗi có thứ tự**, tự suy ra đúng hai công thức đếm, chọn chiều vòng lặp đúng cho unbounded/0-1, xử lý mệnh giá trùng và tổng 0, viết Java 17+ trả số cách chính xác bằng BigInteger, rồi chứng minh và kiểm thử độc lập rằng mọi cách hợp lệ được đếm đúng một lần.
