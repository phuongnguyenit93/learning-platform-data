# Biểu diễn chi phí bằng quan hệ truy hồi

> **Chủ đề:** Computer Science Algorithms → Chia để trị.  
> **Mục tiêu:** Biết chuyển cấu trúc một thuật toán đệ quy thành **quan hệ truy hồi chi phí**, giải thích các thành phần của truy hồi, tính tiệm cận bằng cây đệ quy/phép thế/định lý Master trong điều kiện áp dụng, xử lý kích thước lẻ và chia không đều, và phân biệt thời gian với bộ nhớ đỉnh. Bài có ví dụ Java 17 chạy độc lập, kiểm đếm thao tác và bài tập tự luyện.

## 1. Quan hệ truy hồi đo cái gì?

Trong thiết kế **chia để trị** (*divide and conquer*), thuật toán thường:

1. **Chia** một đầu vào kích thước `n` thành các bài toán con.
2. **Trị** mỗi bài toán con, có thể bằng lời gọi đệ quy.
3. **Kết hợp** kết quả các bài toán con.
4. **Dừng** khi gặp bài toán đủ nhỏ để giải trực tiếp.

Một **quan hệ truy hồi** (*recurrence relation*) mô tả chi phí của bài toán kích thước `n` thông qua chi phí của các bài toán nhỏ hơn.

Ví dụ điển hình:

`T(n) = 2T(n/2) + c·n`, với `T(1)=d`, khi `n` là lũy thừa của 2.

Ý nghĩa:

- `T(n)`: chi phí **toàn bộ** một lần giải đầu vào kích thước `n`.
- `2T(n/2)`: thuật toán giải **hai** bài toán con, mỗi bài có kích thước `n/2`.
- `c·n`: chi phí **ngoài** các lời gọi con, như phân chia, duyệt, ghép hay sao chép.
- `T(1)=d`: chi phí trực tiếp của **trường hợp cơ sở**; không thể chỉ viết phần đệ quy mà bỏ trường hợp dừng.

Đại lượng `T` thường biểu diễn **thời gian**, nhưng có thể thay bằng số phép so sánh, phép cộng, lần truy cập phần tử, số nút đệ quy hoặc lượng công việc khác. Cần nêu rõ **đơn vị đếm** trước khi lập công thức; “chi phí” không tự đồng nghĩa với “số phép so sánh”.

Quan hệ truy hồi là **mô hình cần suy ra từ thuật toán**; còn `O(n log n)`, `Θ(n)` hay `O(n²)` là **kết quả phân tích** sau khi giải hoặc chặn truy hồi. Không nên viết một công thức đã biết theo trí nhớ rồi áp vào mã có số lời gọi, kích thước con hoặc bước ghép khác.

## 2. Bộ công thức chung và cách đọc

Nếu một lời gọi kích thước `n` tạo `r(n)` bài toán con có kích thước `n_1,...,n_r`, và các lời gọi được thực hiện tuần tự, ta thường mô tả tổng công việc:

`T(n) = T(n_1) + T(n_2) + ... + T(n_r) + f(n)`.

Ở đây `f(n)` là chi phí **không nằm trong các lời gọi đệ quy đã tính**. Nếu ta đã cộng `T(n_i)` rồi lại cộng lần nữa chi phí xử lý bên trong con, sẽ **đếm trùng**.

Một số mẫu phổ biến:

| Cấu trúc | Truy hồi thời gian | Kết quả thường gặp |
|---|---|---|
| Một lời gọi cỡ `n-1`, xử lý hằng số | `T(n)=T(n-1)+Θ(1)` | `Θ(n)` |
| Một lời gọi cỡ `n/2`, xử lý hằng số | `T(n)=T(floor(n/2))+Θ(1)` | `Θ(log n)` |
| Một lời gọi cỡ `n/2`, quét `n` phần tử | `T(n)=T(floor(n/2))+Θ(n)` | `Θ(n)` |
| Hai lời gọi cỡ `n/2`, ghép tuyến tính | `T(n)=2T(n/2)+Θ(n)` | `Θ(n log n)` |
| Hai lời gọi cỡ `n/2`, ghép hằng số | `T(n)=2T(n/2)+Θ(1)` | `Θ(n)` |
| Ba lời gọi cỡ `n/2`, xử lý tuyến tính | `T(n)=3T(n/2)+Θ(n)` | `Θ(n^(log₂3))` |
| Hai lời gọi cỡ `n/2`, xử lý `n²` | `T(n)=2T(n/2)+Θ(n²)` | `Θ(n²)` |

Các công thức trong bảng hiểu với trường hợp cơ sở hằng số và kích thước nguyên hợp lệ; khi cần chứng minh chính xác, viết `floor`, `ceil` hoặc giới hạn `n` là lũy thừa thích hợp. Dấu `Θ` trong thành phần ngoài đệ quy nói **cả chặn trên và chặn dưới** của chi phí đó; nếu chỉ có chặn trên `O(f(n))`, ta không tự động được kết luận chặn chặt `Θ` cho toàn bộ truy hồi.

### 2.1. Bốn câu phải hỏi khi nhìn mã

1. **Tham số nào đại diện kích thước đầu vào?** Có thể là `hi-lo`, số nút cây, số mức cần xử lý, không nhất thiết là biến tên `n`.
2. **Trường hợp cơ sở nào kết thúc?** `n<=1`, đoạn rỗng, cây rỗng, hay độ sâu bằng 0? Một lời gọi không giảm kích thước có thể khiến chương trình không dừng.
3. **Có bao nhiêu lời gọi con và kích thước chính xác của chúng?** Hai lời gọi tuần tự **đều tính**, ngay cả khi chúng có cùng kích thước. Chỉ đếm một lần nếu mã **thực sự** chỉ thực hiện một lời gọi.
4. **Ngoài đệ quy có thao tác gì?** Tạo mảng, sao chép phần tử, phân hoạch, tìm điểm giữa, trộn, xử lý mỗi cạnh… Mỗi thao tác cần được cộng vào `f(n)` đúng số lần.

**Quan trọng:** `T(n)` là chi phí của **thuật toán triển khai**, không phải chỉ của một công thức toán trừu tượng. Hai cài đặt cùng giải một bài toán nhưng một bản sao chép dữ liệu trong mỗi lần gọi còn bản kia chỉ truyền chỉ số có thể có `f(n)` rất khác.

## 3. Từng bước lập truy hồi từ một đoạn mã

Xét các hàm đệ quy sau trên dữ liệu kích thước nguyên `n`. Chúng minh họa *công việc tổng hợp*, không trực tiếp sắp một mảng.

### 3.1. Chia đôi, chỉ đi xuống một nhánh

```text
solve(n):
    if n <= 1: return
    làm O(1) công việc
    solve(floor(n/2))
```

Với trường hợp cơ sở `T(0)=T(1)=Θ(1)`:

`T(n)=T(floor(n/2))+Θ(1)` với `n>1`.

Có khoảng `log₂ n` lần giảm một nửa trước khi đến `1`, nên `T(n)=Θ(log n)`. **Không** được viết `2T(n/2)` chỉ vì “đang chia đầu vào làm hai phần”; mã **chỉ gọi đệ quy một phần**. Tìm kiếm nhị phân là ví dụ điển hình: xét giữa rồi chọn duy nhất nửa còn khả năng chứa đáp án.

### 3.2. Chia đôi, mỗi tầng vẫn quét toàn bộ đoạn

```text
solve(n):
    if n <= 1: return
    quét n phần tử
    solve(floor(n/2))
```

`T(n)=T(floor(n/2))+Θ(n)`.

Các mức tốn khoảng `n, n/2, n/4, ...`; tổng chuỗi hình học nhỏ hơn `2n`, nên `T(n)=Θ(n)`. **Có ít mức không có nghĩa tổng thời gian là logarit**: phải cộng chi phí ở từng mức.

### 3.3. Hai nhánh con và bước ghép tuyến tính

```text
solve(lo, hi):
    if hi - lo <= 1: return
    mid = lo + (hi - lo)/2
    solve(lo, mid)
    solve(mid, hi)
    ghép hai đoạn trong Θ(hi - lo)
```

Nếu `n=hi-lo`:

`T(n)=T(floor(n/2))+T(ceil(n/2))+Θ(n)` khi `n>1`.

Nếu chỉ xét `n=2^h` cho dễ tính, hai nhánh bằng nhau:

`T(n)=2T(n/2)+Θ(n)`.

Vì mỗi tầng đệ quy có **tổng kích thước các đoạn là n** và số tầng là `Θ(log n)`, tổng chi phí là `Θ(n log n)` khi bước ghép thật sự làm `Θ(n)` công việc trên mỗi nút nội. Merge sort với bộ đệm và hai con trỏ là ví dụ chuẩn.

### 3.4. Hai nhánh nhưng xử lý ngoài đệ quy không hằng số

Nếu mỗi lời gọi cấp/sao chép `n` phần tử, phần ngoài đệ quy có thể là `Θ(n)` dù phần “chọn mid” chỉ `O(1)`. Truy hồi phải tính **cả bước chuẩn bị đầu vào con**, **kết hợp kết quả**, sao chép hoặc quét, không chỉ câu lệnh ngay trước `return`.

Ngược lại, khi chỉ truyền cặp chỉ số `[lo,hi)` và không sao chép, việc “tạo hai khoảng” tốn `O(1)`; không tự phát sinh `Θ(n)` nếu mã không quét/chép.

## 4. Ví dụ Java 17: đo một truy hồi theo đơn vị công việc định nghĩa sẵn

Một truy hồi không nhất thiết phải đo bằng mili-giây. Ta có thể **gán một đơn vị công việc** cho một lời gọi cơ sở, và `n` đơn vị cho một thao tác xử lý tuyến tính ở mỗi nút nội. Khi đó kết quả số chính xác, dễ đối chiếu với cây đệ quy.

Lưu tệp **RecurrenceWorkDemo.java**:

```java
public class RecurrenceWorkDemo {
    // Một lời gọi cỡ n/2, mỗi nút đóng góp 1 đơn vị.
    static long oneBranchCalls(int n) {
        if (n <= 1) {
            return 1L;
        }
        return 1L + oneBranchCalls(n / 2);
    }

    // Một lời gọi cỡ n/2, mỗi nút nội đóng góp n đơn vị.
    static long oneBranchWithScan(int n) {
        if (n <= 1) {
            return 1L;
        }
        return n + oneBranchWithScan(n / 2);
    }

    // Hai lời gọi cỡ floor/ceil(n/2), mỗi nút nội đóng góp n.
    static long balancedMergeWork(int n) {
        if (n <= 1) {
            return 1L;
        }
        int left = n / 2;
        int right = n - left;
        return n + balancedMergeWork(left) + balancedMergeWork(right);
    }

    public static void main(String[] args) {
        int n = 8;
        System.out.println("One branch calls: " + oneBranchCalls(n));
        System.out.println("Half plus scan: " + oneBranchWithScan(n));
        System.out.println("Two branches plus merge: " + balancedMergeWork(n));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 RecurrenceWorkDemo.java
java RecurrenceWorkDemo
```

Kết quả:

```text
One branch calls: 4
Half plus scan: 15
Two branches plus merge: 32
```

Giải thích:

- `oneBranchCalls(8)` có các cỡ `8→4→2→1`: bốn lời gọi, mỗi lời gọi góp 1 → `4`.
- `oneBranchWithScan(8)` có tổng `8+4+2+1=15`.
- `balancedMergeWork(8)` có ba tầng nút nội, mỗi tầng tổng `8`: `8+8+8`, cộng `8` lá cơ sở mỗi lá `1` → `32`.

**Đừng suy ra số micro/mili-giây thực tế từ những con số này.** Chúng là số **đơn vị công việc theo mô hình do ta chọn**, không phải đo wall-clock. Phần Java vẫn thực hiện thật các lời gọi đệ quy để tính tổng, nhưng toán học chỉ là một cách đếm công việc và không dùng phép đo runtime của JVM.

`long` cũng có giới hạn. Với kích thước quá lớn, công thức đếm có thể tràn `long`, và hàm đệ quy có thể hết ngăn xếp trước khi phép đếm hoàn thành. Ví dụ chỉ dùng `n=8`.

## 5. Giải truy hồi bằng cây đệ quy (*recursion tree*)

Cây đệ quy giúp nhìn **số bài toán ở từng tầng** và **tổng chi phí riêng tầng**.

Xét:

`T(n)=2T(n/2)+c n`, `T(1)=d`, với `n=2^h`.

Ở tầng `i`:

- Có `2^i` lời gọi.
- Mỗi lời gọi xử lý bài toán kích thước `n/2^i`.
- Chi phí ngoài đệ quy trên mỗi lời gọi nội là `c·n/2^i`.
- Tổng chi phí tầng `i` là `2^i·c·n/2^i = c n`.

Các tầng nội là `i=0,...,h-1`: có `h=log₂n` tầng. Có `n` lá kích thước `1`, tổng chi phí cơ sở `d n`.

Vậy với mô hình chính xác đã nêu:

`T(n)=c n log₂ n + d n = Θ(n log n)`.

Sơ đồ cho `n=8`:

```text
T(8)             chi phí ghép: 8c
├── T(4)         chi phí ghép: 4c
│   ├── T(2)     chi phí ghép: 2c
│   │   ├── T(1): d
│   │   └── T(1): d
│   └── T(2)     chi phí ghép: 2c
│       ├── T(1): d
│       └── T(1): d
└── T(4)         chi phí ghép: 4c
    ├── T(2)     chi phí ghép: 2c
    │   ├── T(1): d
    │   └── T(1): d
    └── T(2)     chi phí ghép: 2c
        ├── T(1): d
        └── T(1): d
```

Lưu ý **đếm tổng chi phí theo tầng** chứ không chỉ đếm độ sâu. Một cây có độ sâu `log n` vẫn có thể có `n` lá hoặc nhiều hơn.

### 5.1. Ví dụ chỉ một nhánh nhưng quét n

`T(n)=T(n/2)+c n`, `T(1)=d`.

Cây chỉ có **một nút mỗi tầng**:

`T(n)=c n + c n/2 + c n/4 + ... + d`.

Tổng phần quét là chuỗi hình học: `cn (1+1/2+1/4+...) < 2cn`, đồng thời cấp gốc tốn `cn`, nên `T(n)=Θ(n)`. Không phải `Θ(n log n)` vì **chi phí mỗi tầng giảm**.

### 5.2. Khi chi phí tập trung ở lá

`T(n)=2T(n/2)+c`, với `T(1)=d`.

Tầng `i` có `2^i` nút, mỗi nút nội tốn `c`; chi phí tăng theo tầng. Tổng số nút của cây nhị phân hoàn chỉnh là `2n-1`, có `n` lá và `n-1` nút nội, nên:

`T(n)=c(n-1)+dn=Θ(n)`.

Độ sâu vẫn `Θ(log n)` nhưng công việc tổng là `Θ(n)` vì có `Θ(n)` nút.

### 5.3. Khi chi phí gốc chiếm ưu thế

`T(n)=2T(n/2)+c n²`.

Tổng chi phí ở tầng `i` là:

`2^i · c(n/2^i)² = c n² / 2^i`.

Tổng theo tầng là một chuỗi hình học giảm và bị chặn bởi `2c n²`; riêng gốc đã tốn `c n²`. Do đó `T(n)=Θ(n²)`.

**Mẹo nhận diện:** so sánh chi phí tổng theo tầng: tăng dần xuống lá, gần như không đổi giữa các tầng, hay giảm dần từ gốc. Đó cũng là trực giác của ba trường hợp trong định lý Master.

## 6. Giải truy hồi bằng thế/lặp và chứng minh quy nạp

Với truy hồi không cần Master, **khai triển** nhiều lần thường là cách trực tiếp.

### 6.1. Một nhánh giảm một phần tử

`T(n)=T(n-1)+c`, `T(1)=d`.

Khai triển:

`T(n)=T(n-2)+2c = ... = T(1)+(n-1)c = d+(n-1)c`.

Vậy `T(n)=Θ(n)` nếu `c,d` là hằng số dương.

### 6.2. Một nhánh giảm một nửa

`T(n)=T(n/2)+c`, `T(1)=d`, `n=2^h`.

Khai triển sau `h` bước:

`T(n)=T(1)+h c=d+c log₂n=Θ(log n)`.

Nếu có `floor(n/2)`, số bước vẫn là `Θ(log n)` với `n>=2`; phải xét cơ sở `T(0)` nếu code có khả năng đi tới 0.

### 6.3. Phương pháp đoán rồi chứng minh (*substitution method*)

Với `T(n)=2T(n/2)+c n`, muốn chứng minh `T(n)=O(n log n)`, không được chỉ viết “giả sử `T(n)=O(n log n)` nên đúng”. Hãy đặt **bất đẳng thức cụ thể** và chứng minh bằng quy nạp.

Với `n` là lũy thừa 2 và `n>=2`, giả sử tồn tại hằng số `A` sao cho:

`T(n/2) <= A (n/2) log₂(n/2) + B (n/2)`.

Suy ra:

`T(n) <= 2[A (n/2)(log₂n-1) + B n/2] + c n`  
`= A n log₂n + B n + (c-A)n`.

Chọn `A>=c` làm hạng cuối không dương. Kết hợp cơ sở phù hợp cho một chặn trên dạng `A n log₂ n + B n`.

Để có `Θ(n log n)`, còn cần chặn dưới. Nếu bước ghép thực hiện **ít nhất** `c' n` công việc trên mỗi nút nội với `c'>0`, cây đệ quy có `log₂ n` tầng nội, mỗi tầng tốn ít nhất `c'n`, do đó `T(n)=Ω(n log n)`.

**Điểm cần tránh:** chỉ chứng minh `T(n)=O(n log n)` không tự suy ra `Θ(n log n)`. Phải có chặn dưới tương ứng hoặc phương trình chi phí chính xác.

### 6.4. Kiểm soát tham số chặn

Nếu giả sử `T(n)<=A n log₂ n` ngay tại `n=1`, vế phải bằng 0, không thể chặn một cơ sở có `T(1)>0`. Có thể:

- Bắt đầu từ `n>=2` và xử lý cơ sở riêng.
- Dùng `A n log₂n+B n`.
- Hoặc viết `A n log₂(n+1)` nếu thuận tiện và chứng minh hệ số phù hợp.

Một chứng minh quy nạp cần khớp cả **cơ sở** lẫn **bước**, không chỉ đúng trực giác tiệm cận.

## 7. Định lý Master: lúc nào áp dụng được?

Dạng thường gặp:

`T(n)=aT(n/b)+f(n)`,

trong đó:

- `a>=1` là **số lời gọi con** (hằng số),
- `b>1` là **hệ số giảm kích thước** (hằng số),
- `f(n)` là chi phí ngoài các lời gọi, không âm và có quy luật đủ tốt,
- trường hợp cơ sở tốn `Θ(1)`.

Đặt `p=log_b a`. Đại lượng `n^p` phản ánh quy mô **số lá** và công việc đệ quy thuần. So sánh `f(n)` với `n^p`.

### Trường hợp 1: công việc ở các lá chi phối

Nếu có `ε>0` sao cho:

`f(n)=O(n^(p-ε))`,

thì theo các điều kiện chuẩn của Master:

`T(n)=Θ(n^p)`.

Ví dụ: `T(n)=4T(n/2)+Θ(n)` ⇒ `a=4`, `b=2`, `p=log₂4=2`; `n=O(n^(2-1))` ⇒ `T(n)=Θ(n²)`.

### Trường hợp 2: các tầng có chi phí ngang bậc

Nếu:

`f(n)=Θ(n^p (log n)^q)` với `q>=0` hằng số,

thì dạng mở rộng thường dùng của trường hợp 2 cho:

`T(n)=Θ(n^p (log n)^(q+1))`.

Đặc biệt, khi `q=0`:

`f(n)=Θ(n^p)` ⇒ `T(n)=Θ(n^p log n)`.

Ví dụ: `T(n)=2T(n/2)+Θ(n)` ⇒ `p=1`, `f(n)=Θ(n)`, nên `Θ(n log n)`.

### Trường hợp 3: công việc ở gần gốc chi phối

Nếu có `ε>0` sao cho:

`f(n)=Ω(n^(p+ε))`,

**và** điều kiện đều đặn (*regularity*):

`a f(n/b) <= c f(n)` với một hằng số `c<1` cho đủ lớn `n`,

thì:

`T(n)=Θ(f(n))`.

Ví dụ: `T(n)=2T(n/2)+Θ(n²)` với phần ngoài đệ quy có dạng bậc hai đều đặn. Khi `f(n)=n²`, ta có `2f(n/2)=n²/2`, nên chọn `c=1/2` và kết luận `T(n)=Θ(n²)`.

**Không được bỏ điều kiện regularity ở trường hợp 3** khi `f(n)` có dạng dao động hoặc khác thường. Nếu chỉ biết `f(n)=Ω(n^(p+ε))`, chưa đủ để áp định lý theo dạng này.

### 7.1. Bảng đối chiếu nhanh

| Truy hồi | `a` | `b` | `p=log_b a` | `f(n)` | Kết quả |
|---|---:|---:|---:|---|---|
| `2T(n/2)+n` | 2 | 2 | 1 | `n` | `Θ(n log n)` |
| `2T(n/2)+1` | 2 | 2 | 1 | `1` | `Θ(n)` |
| `T(n/2)+n` | 1 | 2 | 0 | `n` | `Θ(n)` |
| `4T(n/2)+n` | 4 | 2 | 2 | `n` | `Θ(n²)` |
| `2T(n/2)+n²` | 2 | 2 | 1 | `n²` | `Θ(n²)` |
| `3T(n/2)+n` | 3 | 2 | `log₂3` | `n` | `Θ(n^(log₂3))` |
| `T(n/2)+1` | 1 | 2 | 0 | `1` | `Θ(log n)` |
| `2T(n/2)+n log n` | 2 | 2 | 1 | `n log n` | `Θ(n log²n)` |

Bảng trình bày theo lũy thừa/chia đều phù hợp hoặc các quy ước làm tròn thông thường có thể chứng minh không đổi bậc; dấu cộng với `n` hoặc `1` tượng trưng cho chi phí dương có bậc như ghi.

**Điểm cần nhớ:** định lý Master **không** cho phép mặc định áp với mọi quan hệ truy hồi chứa đệ quy. Trước khi điền `a,b`, hãy xác nhận số lời gọi, kích thước mỗi nhánh và hình thức `f(n)` khớp dạng của định lý.

### 7.2. Những truy hồi không khớp ba trường hợp đơn giản

Ví dụ `T(n)=2T(n/2)+n/log n` (với `n` đủ lớn) có `f(n)` **chậm hơn n** nhưng không chậm hơn một lũy thừa `n^(1-ε)` cố định, cũng không phải dạng trường hợp 2 với `q>=0` đã nêu. Không được ép vào trường hợp 1 rồi kết luận `Θ(n)`.

Dùng cây đệ quy, phân tích tổng theo tầng hoặc dạng định lý mở rộng phù hợp. Với trường hợp ví dụ này, tổng tầng có dạng `n Σ_{j=1}^{log₂n} (1/j)` trong mô hình n là lũy thừa 2, nên đạt bậc `Θ(n log log n)`, chứ không phải chỉ `Θ(n)`.

Những biến thể với `f(n)` có log mũ âm, dao động mạnh, nhiều tỷ lệ chia khác nhau hoặc kích thước không đều có thể đòi hỏi công cụ khác, không thể suy bằng một bảng Master duy nhất.

## 8. Kích thước lẻ, floor/ceil và hai nhánh không bằng nhau

Trong Java, `n/2` với `n` nguyên không âm là **chia lấy phần nguyên**. Nếu `n=7`, hai đoạn `[lo,mid)` và `[mid,hi)` có kích thước `3` và `4`, không có đoạn dài `3.5`.

Truy hồi chính xác của một phép tách đôi và ghép tuyến tính thường là:

`T(n)=T(floor(n/2))+T(ceil(n/2))+Θ(n)`.

Ta thường rút gọn thành `2T(n/2)+Θ(n)` khi chỉ cần bậc tiệm cận và đã giải thích vì sao làm tròn không ảnh hưởng kết quả. Trong merge sort, cả hai nhánh luôn có kích thước tối đa `ceil(n/2)`, nên độ sâu là `Θ(log n)`; mỗi tầng có tổng độ dài các đoạn con không vượt `n`, đồng thời việc ghép ở phần lớn các tầng tạo tổng công việc tuyến tính. Vì vậy tổng vẫn `Θ(n log n)` khi bước ghép xử lý đủ các phần tử.

**Không làm tròn tùy tiện** nếu ranh giới làm thay đổi số lời gọi dừng, nếu có một nhánh kích thước 0 và lại được gọi vô hạn, hoặc thuật toán có hành vi đặc biệt với các kích thước không phải lũy thừa 2.

### 8.1. Tách tỷ lệ không đều nhưng có định hướng

Ví dụ:

`T(n)=T(n/3)+T(2n/3)+Θ(n)`.

Đây là hai bài toán con có kích thước **khác nhau**, không khớp `aT(n/b)` với **một** cỡ con giống nhau.

Một lập luận cây đệ quy:

- Ở một tầng, tổng kích thước các đoạn con không vượt kích thước gốc `n` vì `n/3+2n/3=n`.
- Nhánh dài nhất giảm mỗi lần xuống tối đa khoảng `2n/3`, nên chiều cao lớn nhất là `O(log n)`.
- Khi các nhánh nội còn nhiều phần tử, chi phí quét/ghép tổng cộng trên các tầng tạo chặn dưới tương ứng để suy `Θ(n log n)` dưới giả thiết chia và ghép chuẩn cùng trường hợp cơ sở hằng.

Không được thay thành `2T(n/2)` như **phương trình chính xác**. Có thể trùng bậc kết quả, nhưng đó là điều **phải chứng minh**, không phải đồng nhất hai thuật toán.

### 8.2. Quicksort: độ lệch phụ thuộc dữ liệu

Quicksort phân hoạch một đoạn dài `n` quanh pivot, trả một vị trí chia:

`T(n)=T(q)+T(n-q-1)+Θ(n)`,

trong đó `q` là số phần tử ở bên trái pivot sau phân hoạch. Cần phân biệt:

- **Pivot cân bằng:** `q≈(n-1)/2` ⇒ hai nhánh gần bằng nhau ⇒ `Θ(n log n)`.
- **Pivot cực lệch:** `q=0` hoặc `q=n-1` ⇒ `T(n)=T(n-1)+Θ(n)` ⇒ `Θ(n²)`.
- **Pivot ngẫu nhiên:** `q` là biến ngẫu nhiên, thường cần một truy hồi **kỳ vọng**, không thể đưa một giá trị q cố định vào công thức rồi tuyên bố thời gian kỳ vọng.

Với thứ tự pivot được chọn ngẫu nhiên đều trong các vị trí của đoạn gồm **các khóa phân biệt** (theo mô hình quicksort chuẩn), một dạng truy hồi kỳ vọng về số phép so sánh là:

`E[C(n)] = (n-1) + (1/n) Σ_{q=0}^{n-1} (E[C(q)] + E[C(n-1-q)])`.

Dưới các giả định nêu trên, giải truy hồi cho kết quả `E[C(n)]=Θ(n log n)`. **Kỳ vọng không phải chặn cho mọi đầu vào và mọi lần chạy**; mỗi lần chạy vẫn có thể gặp phân hoạch xấu.

### 8.3. Nếu phân hoạch có chi phí dữ liệu phụ thuộc

Nếu `partition` đi qua `n` phần tử, đó là `Θ(n)`. Nhưng nếu dùng cấu trúc đặc biệt và phân hoạch tốn thêm một thao tác như sắp lại cả đoạn bằng thuật toán khác, phải đưa đúng chi phí ấy vào `f(n)`.

Khi các khóa trùng nhiều, cách phân hoạch **hai chiều** có thể tạo nhánh rất lệch. Một quicksort ba chiều (tách nhỏ hơn / bằng / lớn hơn) có cấu trúc truy hồi khác trên các đầu vào có nhiều khóa bằng nhau. Không dùng kết quả của một phiên bản để cam kết cho phiên bản khác khi chưa phân tích.

## 9. Java 17: đo số so sánh của quicksort lệch

Để nhìn rõ trường hợp xấu, ví dụ này cố ý chọn **phần tử cuối làm pivot** và dùng phân hoạch Lomuto hai chiều. Với mảng đã tăng sẵn, pivot cuối luôn là giá trị lớn nhất trong đoạn; mỗi lần chỉ giảm kích thước một phần tử.

Lưu thành **QuickSortCostDemo.java**:

```java
import java.util.Arrays;

public class QuickSortCostDemo {
    private static long comparisons;

    static void sort(int[] a, int lo, int hi) {
        // Xử lý đoạn nửa mở [lo, hi).
        if (hi - lo <= 1) {
            return;
        }

        int pivot = a[hi - 1];
        int store = lo;

        for (int j = lo; j < hi - 1; j++) {
            comparisons++;
            if (a[j] <= pivot) {
                swap(a, store, j);
                store++;
            }
        }
        swap(a, store, hi - 1);

        sort(a, lo, store);
        sort(a, store + 1, hi);
    }

    static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3, 4, 5};
        comparisons = 0L;
        sort(a, 0, a.length);
        System.out.println("Sorted: " + Arrays.toString(a));
        System.out.println("Comparisons: " + comparisons);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 QuickSortCostDemo.java
java QuickSortCostDemo
```

Stdout:

```text
Sorted: [1, 2, 3, 4, 5]
Comparisons: 10
```

**Vì sao là 10?** Các lượt phân hoạch lần lượt so sánh `4,3,2,1` phần tử với pivot. Tổng `4+3+2+1=10`, bằng `n(n-1)/2` khi `n=5`.

Truy hồi so sánh trên đầu vào này:

`C(n)=C(n-1)+(n-1)`, với `C(0)=C(1)=0`.

Do đó:

`C(n)=(n-1)+(n-2)+...+1=n(n-1)/2=Θ(n²)`.

Ví dụ **cố ý** chọn một chính sách pivot xấu đối với mảng đã sắp. Không suy ra “quicksort luôn `Θ(n²)`”; kết luận trên đúng cho dữ liệu, cách chọn pivot và cách phân hoạch đã mô tả. Những cài đặt có pivot ngẫu nhiên, pivot trung vị hoặc chia ba nhánh có hành vi khác.

## 10. Chi phí thực trong merge sort: đếm thao tác, không chỉ nhớ công thức

Merge sort là ví dụ điển hình có **hai lời gọi đệ quy** và bước ghép tuyến tính. Nhưng số **phép so sánh giá trị** trong một lần merge có thể phụ thuộc các giá trị; để chứng minh thời gian `Θ(n log n)`, thường dễ đếm **số phần tử được ghi ra buffer** hơn.

Trong một lần merge hai nửa tổng độ dài `n`:

- Mỗi phần tử được ghi vào buffer **đúng một lần** ⇒ số lần ghi buffer là `n`.
- Nếu hai nửa đều không rỗng, số phép so sánh **không vượt** `n-1`; có thể ít hơn tùy dữ liệu.
- Sau đó có thể sao chép buffer về mảng bằng `System.arraycopy` hoặc thao tác tương đương, cũng tốn `O(n)` công việc.

Đặt `W(n)` là **số lần ghi phần tử vào buffer** qua toàn bộ lời gọi merge sort trên đoạn dài `n`. Với trường hợp cơ sở `W(0)=W(1)=0`:

`W(n)=W(floor(n/2))+W(ceil(n/2))+n`, với `n>=2`.

Với `n=2^h`: `W(n)=n log₂ n`. Đây là phương trình **chính xác** cho số lần ghi buffer nếu mỗi lần merge ghi đúng n phần tử.

### 10.1. Java 17: kiểm đếm trong merge sort

Lưu thành **MergeSortCostDemo.java**:

```java
import java.util.Arrays;

public class MergeSortCostDemo {
    private static long comparisons = 0L;
    private static long bufferWrites = 0L;

    static void mergeSort(int[] a) {
        int[] buffer = new int[a.length];
        sort(a, buffer, 0, a.length);
    }

    static void sort(int[] a, int[] buffer, int lo, int hi) {
        if (hi - lo <= 1) {
            return;
        }

        int mid = lo + (hi - lo) / 2;
        sort(a, buffer, lo, mid);
        sort(a, buffer, mid, hi);

        int i = lo;
        int j = mid;
        int k = lo;

        while (i < mid && j < hi) {
            comparisons++;
            if (a[i] <= a[j]) {
                buffer[k++] = a[i++];
            } else {
                buffer[k++] = a[j++];
            }
            bufferWrites++;
        }

        while (i < mid) {
            buffer[k++] = a[i++];
            bufferWrites++;
        }

        while (j < hi) {
            buffer[k++] = a[j++];
            bufferWrites++;
        }

        System.arraycopy(buffer, lo, a, lo, hi - lo);
    }

    public static void main(String[] args) {
        int[] a = {8, 7, 6, 5, 4, 3, 2, 1};
        mergeSort(a);

        System.out.println("Sorted: " + Arrays.toString(a));
        System.out.println("Comparisons: " + comparisons);
        System.out.println("Buffer writes: " + bufferWrites);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MergeSortCostDemo.java
java MergeSortCostDemo
```

Stdout:

```text
Sorted: [1, 2, 3, 4, 5, 6, 7, 8]
Comparisons: 12
Buffer writes: 24
```

**Giải thích số liệu:** Với tám phần tử, cây chia có ba tầng ghép; mỗi tầng ghi tổng tám phần tử vào buffer nên `8×3=24` lần. Trên mảng giảm nghiêm ngặt này, mỗi lần merge các giá trị của nửa phải đều nhỏ hơn giá trị nửa trái; số so sánh theo ba tầng là `4+4+4=12`. Số so sánh **không nhất thiết bằng số lần ghi**.

**Không nhầm số lần ghi buffer với toàn bộ thời gian:** ví dụ còn có các thao tác so sánh, cập nhật con trỏ, gọi hàm và sao chép buffer về mảng; những thao tác ấy vẫn có tổng chi phí cùng bậc `Θ(n log n)`. Bộ đếm chỉ minh họa một **thước đo có thể xác định chính xác** để liên hệ truy hồi với công việc thực.

**Tính đúng:** công thức thời gian chỉ hữu ích khi thuật toán **thật sự sắp được**. Merge sort còn cần chứng minh hai nửa sắp đúng và thao tác merge tạo đoạn đã có thứ tự, bảo toàn đa tập phần tử. Phân tích chi phí không thay thế chứng minh tính đúng.

## 11. Đếm thời gian khác với đếm bộ nhớ đỉnh

Đây là một trong những nhầm lẫn quan trọng nhất khi nhìn cây đệ quy.

### 11.1. Thời gian: cộng công việc của tất cả nhánh

Nếu hai lời gọi con thực hiện **tuần tự**, tổng thời gian bao gồm cả hai:

`T(n)=T(left)+T(right)+f(n)`.

Ngay cả khi `left` và `right` có cùng kích thước, hai lời gọi thường đều cần chạy. Cộng `T` theo **cả cây** là đúng khi mô hình một luồng và mỗi thao tác tốn chi phí phù hợp.

### 11.2. Ngăn xếp đệ quy: xét đường gọi đang hoạt động

Nếu hàm gọi **nhánh trái, chờ hoàn thành, rồi mới gọi nhánh phải**, các frame con **không tồn tại đồng thời**. Độ sâu stack là chiều dài đường gọi dài nhất:

`D(n)=1+max(D(left),D(right))`, với `D(1)=1`.

Với hai nửa cân bằng, `D(n)=Θ(log n)`. Không cộng `D(left)+D(right)` để suy stack nếu các nhánh được thực thi tuần tự.

Nếu mỗi frame chỉ có một lượng biến cục bộ `O(1)`, **bộ nhớ call stack** là `O(D(n))`. Với quicksort pivot rất lệch và gọi đệ quy hai nhánh một cách ngây thơ, `D(n)` có thể `Θ(n)`; với merge sort cân bằng, `D(n)=Θ(log n)`.

### 11.3. Bộ nhớ phụ thuộc cấp phát và vòng đời đối tượng

Đặt `S(n)` là **bộ nhớ đỉnh bổ sung** tại thời điểm một lời gọi đang chạy. Nếu một frame giữ một buffer kích thước `g(n)` **trong suốt lúc gọi con**, có thể có dạng:

`S(n)=g(n)+max(S(left),S(right))`.

Nếu `g(n)=Θ(n)` và các nhánh cân bằng, tổng buffer trên một đường gọi có dạng:

`n+n/2+n/4+...=Θ(n)`,

không phải `Θ(n log n)` chỉ vì cây có `log n` tầng. Ngược lại, nếu mỗi frame giữ `Θ(n)` buffer **cùng kích thước n gốc** ở mọi độ sâu, tổng có thể thành `Θ(n log n)`.

Nếu buffer được cấp **một lần tại đầu thuật toán** như `mergeSort` ở ví dụ trên, bộ nhớ phụ có buffer `Θ(n)` cộng stack `Θ(log n)`, tổng vẫn `Θ(n)`.

**Điều cần phân biệt:**

- **Tổng số byte cấp phát trong cả lần chạy:** có thể cộng trên toàn bộ cây.
- **Bộ nhớ sống đồng thời/đỉnh (*peak live memory*):** phụ thuộc vòng đời buffer và nhánh hoạt động.
- **Bộ nhớ lưu đầu vào/đầu ra:** có tính vào “auxiliary space” hay không phải được nêu rõ.
- **Đệ quy song song:** nếu thực sự chạy hai nhánh **đồng thời**, các bộ nhớ con có thể cùng sống; không thể áp dụng ngay công thức `max` của nhánh tuần tự.

### 11.4. Ví dụ: Fibonacci đệ quy ngây thơ

Với hàm:

```text
fib(n):
    if n <= 1: return n
    return fib(n-1) + fib(n-2)
```

Thời gian có truy hồi `T(n)=T(n-1)+T(n-2)+Θ(1)`, dẫn đến tăng theo hàm mũ, `Θ(φ^n)` dưới mô hình chi phí hằng số cho mỗi phép cộng/định nghĩa trên `int` với n trong miền hợp lệ.

Nhưng độ sâu stack tối đa chỉ `Θ(n)` vì mỗi đường gọi giảm ít nhất một đơn vị. Nếu dùng **memoization** để tránh tính lại cùng trạng thái, số trạng thái chỉ `n+1`, nên thời gian có thể `Θ(n)` và bộ nhớ `Θ(n)` cho bảng nhớ (cùng stack đệ quy). Đây là ví dụ cho thấy **cây công việc** và **đường ngăn xếp đang chạy** là hai đối tượng khác nhau.

## 12. Công việc, độ sâu và thuật toán song song

Với chia để trị chạy song song, còn hai đại lượng thường dùng:

- **Work `W(n)`:** tổng số thao tác nếu cộng tất cả các nút/lời gọi con.
- **Span `S(n)` hoặc critical-path length:** số thao tác trên đường phụ thuộc dài nhất, khi các nhánh con độc lập có thể chạy đồng thời và bỏ qua overhead.

Với hai lời gọi con có thể thực thi **song song lý tưởng**:

`W(n)=W(left)+W(right)+f_work(n)`.

Nhưng span có thể là:

`S(n)=max(S(left),S(right))+f_span(n)`,

không phải tổng hai nhánh, **nếu** các nhánh thực sự độc lập và các bước sau khi nối có thứ tự phụ thuộc được mô hình đúng.

Ví dụ, merge sort song song với hai lời gọi sort độc lập nhưng **bước merge vẫn tuần tự Θ(n)**:

`S(n)=S(n/2)+Θ(n)=Θ(n)`,

dù work tổng vẫn `Θ(n log n)`. Không thể kết luận span `Θ(log n)` chỉ vì có hai nhánh song song; bước ghép tuần tự lớn tạo đường găng dài.

Nếu bước ghép cũng được song song hóa bằng thuật toán khác, cần lập lại `f_span(n)`. Hơn nữa, chương trình thực tế có chi phí tạo tác vụ, đồng bộ, contention và giới hạn số lõi; mô hình “vô hạn bộ xử lý” chỉ là chặn lý thuyết, không phải bảo đảm tốc độ trên máy tính thật.

## 13. Những truy hồi không nên ép vào Master

Không phải bài nào cũng có mẫu `aT(n/b)+f(n)`.

### 13.1. Hai kích thước con khác nhau

`T(n)=T(n/3)+T(2n/3)+Θ(n)` phải phân tích qua cây đệ quy, phép thế hoặc định lý phù hợp cho các tỉ lệ con khác nhau. Không tự chọn `a=2,b=2` vì “có hai nhánh”.

### 13.2. Giảm bằng phép trừ

`T(n)=T(n-1)+Θ(n)` có độ sâu `n` và tổng `1+2+...+n=Θ(n²)`; không phải truy hồi chia theo tỉ lệ hằng `n/b`.

### 13.3. Nhánh phụ thuộc dữ liệu

`T(n)=T(q)+T(n-q-1)+Θ(n)` của quicksort cần mô hình q (xấu nhất, tốt nhất, kỳ vọng). Nếu chỉ biết một nhánh “thường nhỏ”, chưa đủ để kết luận Big-O chặt.

### 13.4. Nhiều tham số

Một thuật toán có thể phụ thuộc độ dài `n` và số nhóm `k`, hoặc số đỉnh `V` và số cạnh `E`. Khi đó có thể cần:

`T(n,k)=T(n/2,k)+T(n/2,k)+Θ(nk)`,

hoặc một công thức đa tham số khác. **Không giấu một tham số có thể lớn vào hằng số** nếu nó thay đổi theo input.

### 13.5. Không bảo đảm giảm kích thước

Ví dụ:

```text
bad(n):
    if n == 1: return
    bad(n)
```

Không thể lập `T(n)=T(n)+Θ(1)` rồi “giải” ra hữu hạn: chương trình **không dừng**. Để truy hồi chi phí có ý nghĩa, phải xác nhận mọi nhánh tiến về một trường hợp cơ sở.

### 13.6. Số lời gọi khủng và trùng lặp bài toán con

Naive Fibonacci có `T(n)=T(n-1)+T(n-2)+Θ(1)`, nhưng hai lời gọi tiếp tục tính lại nhiều trạng thái giống nhau. Khi thêm memoization, công việc thay đổi thành “mỗi trạng thái tính một lần”, nên **truy hồi thời gian không còn là cây gọi ngây thơ**. Không giữ nguyên truy hồi của phiên bản cũ sau khi tối ưu bằng cache.

### 13.7. Hệ số chi phí không hằng số

Nếu các phép thao tác trên số nguyên lớn có độ dài bit `L`, chi phí phép cộng/nhân có thể phụ thuộc `L`; nếu đọc tệp, chi phí I/O phụ thuộc kích thước khối. Hãy nêu **mô hình tính toán**: phép toán từ máy hằng số, bit complexity, hay số lần I/O. Một kết luận `Θ(n)` trong một mô hình không tự suy sang mọi mô hình khác.

## 14. Công thức thường gặp trong những thuật toán chia để trị

| Thuật toán/cách triển khai | Truy hồi thời gian thường dùng | Kết quả | Cần kiểm tra |
|---|---|---|---|
| Binary search đệ quy | `T(n)=T(n/2)+Θ(1)` | `Θ(log n)` | Chỉ theo một nửa |
| Merge sort trên mảng | `T(n)=2T(n/2)+Θ(n)` | `Θ(n log n)` | Merge đọc/ghi đủ phần tử |
| Quicksort cân bằng | `T(n)=2T(n/2)+Θ(n)` | `Θ(n log n)` | Điều kiện pivot cân bằng |
| Quicksort lệch nhất | `T(n)=T(n-1)+Θ(n)` | `Θ(n²)` | Pivot tạo một nhánh rỗng |
| Karatsuba (nhân số lớn theo phép đếm thao tác phù hợp) | `T(n)=3T(n/2)+Θ(n)` | `Θ(n^(log₂3))` | 3 phép nhân con, cộng/trừ tuyến tính theo số chữ số |
| Strassen (nhân ma trận) | `T(n)=7T(n/2)+Θ(n²)` | `Θ(n^(log₂7))` | 7 phép nhân ma trận con, cộng/trừ ma trận bậc hai |
| Quét tuyến tính rồi gọi một nửa | `T(n)=T(n/2)+Θ(n)` | `Θ(n)` | Đừng bỏ qua chi phí quét |
| Duyệt tất cả nút cây nhị phân | `T(n)=T(n_left)+T(n_right)+Θ(1)` | `Θ(n)` | `n_left+n_right=n-1`, không cần cây cân bằng |

Ở Karatsuba, Strassen hay các thuật toán xử lý nhiều chữ số, `n` là **kích thước dữ liệu số/chữ số hoặc chiều ma trận**, không phải giá trị số học của dữ liệu. Nếu mỗi phép toán trên số lớn có chi phí khác với giả định từ máy, phân tích phải ghi thêm điều đó.

### 14.1. Vì sao duyệt cây không cần cân bằng để có Θ(n)?

Một hàm như:

```text
visit(node):
    if node is null: return
    do O(1) work on node
    visit(node.left)
    visit(node.right)
```

thăm mỗi nút đúng một lần. Nếu có `n` nút thật và thời gian xử lý mỗi nút là `Θ(1)`, tổng là `Θ(n)` **dù cây lệch**. Truy hồi đúng là `T(n)=T(n_left)+T(n_right)+Θ(1)` với `n_left+n_right=n-1`, không cần giả định cả hai con có kích thước `n/2`. Tuy nhiên, **độ sâu stack** vẫn có thể `Θ(n)` với cây lệch.

**Thông điệp:** đôi khi đếm tổng số phần tử/nút trực tiếp **đơn giản và chính xác hơn** cố ép một truy hồi vào trường hợp chia đều.

## 15. Kiểm tra đúng bằng ví dụ nhỏ trước khi tổng quát hóa

Một truy hồi tốt có thể đối chiếu với việc đếm thủ công trên đầu vào nhỏ.

### 15.1. Tính bằng bảng

Với `T(1)=1`, `T(n)=2T(n/2)+n`, `n=2^h`:

| n | T(n) | Cách tính |
|---:|---:|---|
| 1 | 1 | Cơ sở |
| 2 | 4 | `2×1+2` |
| 4 | 12 | `2×4+4` |
| 8 | 32 | `2×12+8` |
| 16 | 80 | `2×32+16` |

Công thức chính xác là `T(n)=n(log₂n+1)` cho các lũy thừa hai có `n>=1`. Bảng xác nhận số học của những trường hợp nhỏ; **chứng minh tổng quát** dựa vào cây đệ quy hoặc quy nạp, không chỉ dựa bảng.

Với `T(1)=1`, `T(n)=T(n/2)+n`, `n=2^h`:

| n | T(n) |
|---:|---:|
| 1 | 1 |
| 2 | 3 |
| 4 | 7 |
| 8 | 15 |
| 16 | 31 |

Công thức là `T(n)=2n-1` trên các lũy thừa hai, tức `Θ(n)`, dù độ sâu có `Θ(log n)`.

### 15.2. Nêu rõ số phép toán cần đếm

Trong Java, một vòng lặp `for(int i=0; i<n; i++)` quét `n` phần tử, nhưng nếu thân vòng thực hiện một phép toán trên **chuỗi dài L**, thời gian một lượt không nhất thiết là `O(1)` theo chi phí bit/ký tự. Nêu mô hình trước khi viết `f(n)=Θ(n)`.

Tương tự, một lời gọi thư viện như `Arrays.copyOfRange` có thể **sao chép số phần tử tỉ lệ độ dài đoạn**, dù code chỉ có một dòng. Số dòng không phản ánh số thao tác.

### 15.3. Đếm nhánh rẽ có thực sự xảy ra?

Khi code có:

```text
if condition:
    solve(left)
else:
    solve(right)
```

chỉ **một** trong hai nhánh chạy trong một lần gọi, không phải cả hai. Truy hồi thời gian xấu nhất có thể là `max(T(left), T(right))+f(n)` chứ không phải tổng. Nhưng nếu code là:

```text
solve(left)
solve(right)
```

hai lời gọi **đều** được thực hiện, nên phải cộng cả hai. Phân biệt `if/else` với hai lời gọi liên tiếp là thao tác kiểm tra quan trọng.

## 16. Các lỗi phổ biến khi viết và giải truy hồi

### Lỗi 1. Thiếu chi phí chia/ghép

Viết `T(n)=2T(n/2)+O(1)` cho merge sort trong khi code trộn/sao chép `n` phần tử. **Sửa:** tính cả bước ghép `Θ(n)`.

### Lỗi 2. Đếm số nhánh sai

Viết `2T(n/2)` cho binary search, mặc dù mỗi lần chỉ chọn một nửa. **Sửa:** dùng `T(n/2)+Θ(1)`.

### Lỗi 3. Thay `floor/ceil` mà không xét biên

Với `n=3`, hai nhánh có thể dài `1` và `2`, không phải hai nhánh `1.5`. **Sửa:** lập truy hồi chính xác với `floor/ceil`; chỉ rút gọn khi đã giải thích ảnh hưởng tiệm cận.

### Lỗi 4. Nhầm độ sâu với tổng thời gian

Cây merge sort sâu `Θ(log n)` nhưng mỗi tầng xử lý tổng `Θ(n)`, nên thời gian `Θ(n log n)`, không phải `Θ(log n)`.

### Lỗi 5. Nhầm thời gian với bộ nhớ stack

Đối với hai nhánh **tuần tự**, thời gian cộng cả hai; stack chỉ giữ các frame trên **một đường gọi đang hoạt động**. Tính stack bằng cộng mọi nút thường phóng đại đáng kể.

### Lỗi 6. Dùng Master khi không đúng dạng

`T(n)=T(n/3)+T(2n/3)+Θ(n)` không có cùng kích thước `n/b` cho mọi nhánh. `T(n)=T(n-1)+Θ(n)` cũng không phải chia theo tỉ lệ cố định. **Sửa:** dùng cây, phép thế hoặc định lý mở rộng phù hợp.

### Lỗi 7. Bỏ điều kiện regularity

Ở trường hợp 3 của Master, chỉ biết `f(n)` lớn hơn `n^p` theo một lũy thừa dương chưa đủ khi `f(n)` không đều đặn. Kiểm tra `a f(n/b) <= c f(n)` cho một `c<1`.

### Lỗi 8. Lẫn lộn chặn trên với chặn chặt

Nếu chỉ biết `f(n)=O(n)`, không được mặc nhiên đặt `f(n)=Θ(n)` rồi kết luận mọi trường hợp. **Sửa:** tìm chặn dưới hoặc một đơn vị công việc luôn được thực hiện.

### Lỗi 9. Bỏ trường hợp cơ sở và tính dừng

Không có `T(1)`/`T(0)` hợp lệ, một số truy hồi không xác định được. Đệ quy không giảm kích thước có thể không kết thúc, nên mọi Big-O hữu hạn đều không có ý nghĩa cho lần chạy đó.

### Lỗi 10. Đặt cùng ký hiệu cho đơn vị đo khác nhau

`T(n)` là tổng phép so sánh, còn `S(n)` là bộ nhớ đỉnh; không thể cộng trực tiếp các đại lượng này. Một truy hồi cho số lời gọi không tự bằng truy hồi cho mili-giây.

### Lỗi 11. Tính sai khi có memoization

Đệ quy Fibonacci ngây thơ lặp lại trạng thái; khi dùng cache, mỗi trạng thái được giải một lần. Cần phân tích đồ thị trạng thái hoặc DP, không lấy nguyên cây gọi của phiên bản ngây thơ.

### Lỗi 12. Cho rằng thuật toán chia đôi luôn nhanh

Nếu mỗi nút nội làm `Θ(n²)` công việc hoặc có quá nhiều nhánh, tổng có thể `Θ(n²)` hoặc lớn hơn. Lợi ích của chia để trị phụ thuộc **cả số nhánh, cỡ nhánh và bước ngoài đệ quy**.

## 17. Bài tập tự luyện và đáp án

### Bài A: Hai nhánh, ghép hằng số

Một hàm chia mảng thành hai nửa, gọi cả hai nhánh và làm `Θ(1)` ngoài đệ quy ở mỗi nút. Giả sử cơ sở hằng số. Lập truy hồi và suy bậc thời gian.

**Đáp án:** `T(n)=2T(n/2)+Θ(1)`, `T(1)=Θ(1)`, khi n là lũy thừa hai. Cây có `Θ(n)` nút, nên `T(n)=Θ(n)`.

### Bài B: Chia một nửa nhưng quét toàn bộ

Mỗi lời gọi quét `n` phần tử, sau đó chỉ gọi đệ quy trên nửa đầu. Kết quả?

**Đáp án:** `T(n)=T(floor(n/2))+Θ(n)` ⇒ `Θ(n)` vì chi phí theo tầng là `n+n/2+n/4+...`.

### Bài C: Ba nhánh kích thước một nửa

Một hàm tạo **ba** lời gọi trên các đầu vào dài `n/2` và làm `Θ(n)` thao tác ngoài đệ quy.

**Đáp án:** `T(n)=3T(n/2)+Θ(n)`; với `p=log₂3≈1.585`, `f(n)=O(n^(p-ε))` cho một `ε>0`, nên trường hợp 1 của Master cho `Θ(n^(log₂3))`.

### Bài D: Hai nhánh và phép ghép bình phương

Một hàm gọi hai nửa rồi dùng hai vòng lặp lồng nhau trên n phần tử, mỗi vòng làm công việc hằng số.

**Đáp án:** `T(n)=2T(n/2)+Θ(n²)`. Trường hợp 3 của Master áp dụng với `f(n)=n²` (regularity: `2f(n/2)=f(n)/2`), nên `Θ(n²)`.

### Bài E: Quicksort pivot cuối trên dãy tăng

Với `n=6` khóa phân biệt tăng dần, Lomuto pivot cuối thực hiện bao nhiêu phép so sánh với pivot? Truy hồi?

**Đáp án:** `5+4+3+2+1=15` phép so sánh; `C(n)=C(n-1)+(n-1)`, `C(0)=C(1)=0`, nên `Θ(n²)`.

### Bài F: So sánh hai cách dùng Master

Cho `T(n)=2T(n/2)+n log n`. `p` là gì và kết quả theo dạng trường hợp 2 mở rộng?

**Đáp án:** `a=2,b=2,p=1`, `f(n)=Θ(n^p log n)` với `q=1`, nên `T(n)=Θ(n log² n)`.

### Bài G: Không chia đều

`T(n)=T(n/3)+T(2n/3)+Θ(n)`. Vì sao không dùng trực tiếp `a=2,b=2` của Master?

**Đáp án:** hai nhánh có kích thước **khác nhau**; không thể viết chính xác hai lời gọi cùng kích thước `n/2`. Có thể phân tích cây và chứng minh `Θ(n log n)` dưới điều kiện chia đều theo tỉ lệ đã nêu và chi phí ghép tuyến tính, nhưng đó là **chứng minh riêng**.

### Bài H: Thời gian và stack của hai nhánh

Cho `T(n)=2T(n/2)+Θ(n)` với hai lời gọi **tuần tự**, mỗi frame có `O(1)` biến cục bộ; buffer được cấp một lần bên ngoài và dùng lại.

**Đáp án:** thời gian `Θ(n log n)`; stack `Θ(log n)` frame; buffer dùng chung `Θ(n)` nếu cấp theo kích thước đầu vào; tổng bộ nhớ phụ `Θ(n)`. Không cộng stack của hai nhánh như thể chúng đồng thời.

### Bài I: Truy hồi số phép ghi của merge sort

Cho `n=16=2⁴`, mỗi lần merge ghi đúng độ dài đoạn vào buffer. Không tính số ghi ở lá. Có bao nhiêu lần ghi buffer?

**Đáp án:** `W(n)=2W(n/2)+n`, `W(1)=0`; `W(16)=16 log₂16=16×4=64`.

### Bài J: Phân biệt sort và select

Một thuật toán sắp xếp toàn bộ mảng dùng merge sort `Θ(n log n)`; một thuật toán khác chỉ cần giá trị lớn thứ k, dùng min-heap kích thước k `O(n log(k+1))`. Nếu `k=1`, hai chi phí khác nhau ra sao?

**Đáp án:** chọn phần tử lớn nhất chỉ cần quét một lần, `Θ(n)` thời gian và `O(1)` bộ nhớ; không cần sort toàn bộ. Đây là bài toán khác nên không mâu thuẫn với cận dưới `Ω(n log n)` của **sắp xếp so sánh toàn bộ**.

## 18. Checklist trước khi kết luận độ phức tạp

1. **Xác định n:** độ dài đoạn, số nút, số chữ số hay kích thước khác; có thêm tham số cần theo dõi không?
2. **Xác định đại lượng:** thời gian, số phép so sánh, số lần ghi, số lời gọi, bộ nhớ sống, hay span song song?
3. **Ghi cơ sở:** `T(0)`/`T(1)` và điều kiện dừng; kiểm tra mọi lời gọi con thực sự giảm kích thước.
4. **Đếm nhánh thật:** có bao nhiêu lời gọi con chạy trong một lượt? Điều kiện `if/else` chỉ chọn một nhánh hay hai lời gọi tuần tự?
5. **Viết kích thước chính xác:** `floor`, `ceil`, nhánh lệch, `q` phụ thuộc pivot, xử lý riêng n lẻ.
6. **Đếm f(n):** mọi thao tác không đệ quy, gồm chia, phân hoạch, merge, sao chép, cấp phát, xử lý trên cấu trúc con.
7. **Lựa chọn cách giải:** khai triển cho một nhánh; cây đệ quy để thấy chi phí theo tầng; substitution để chứng minh; Master **chỉ khi đúng dạng và điều kiện**.
8. **Ghi đủ giả thiết:** giới hạn n, kích thước bằng nhau, mô hình từ máy, thời gian kỳ vọng với ngẫu nhiên, đặc tính dữ liệu.
9. **Tách thời gian và không gian:** cộng công việc các nhánh cho thời gian; xem đường gọi đang hoạt động và tuổi thọ buffer cho bộ nhớ.
10. **Chứng minh đúng bậc:** nếu tuyên bố `Θ`, cần chặn trên và chặn dưới. Nếu chỉ có chặn trên, trình bày `O` một cách trung thực.
11. **Đối chiếu ví dụ nhỏ:** `n=1,2,4,8` hoặc dữ liệu lệch để phát hiện số nhánh/chi phí cơ sở sai.
12. **Không nhầm mô hình với code thực:** thay đổi cách chia, tạo buffer, memoization, thứ tự gọi hay song song hóa có thể làm truy hồi thay đổi.

**Ghi nhớ:** biểu diễn chi phí bằng quan hệ truy hồi là quá trình **đọc đúng cấu trúc công việc thực sự của thuật toán**: số lời gọi, kích thước từng lời gọi và chi phí ngoài đệ quy. Cây đệ quy và định lý Master là công cụ **giải**, không thay việc **lập** truy hồi. Với chia để trị, hãy luôn hỏi **đang đếm tổng công việc, độ sâu ngăn xếp hay bộ nhớ đỉnh** trước khi đưa ra kết luận.
