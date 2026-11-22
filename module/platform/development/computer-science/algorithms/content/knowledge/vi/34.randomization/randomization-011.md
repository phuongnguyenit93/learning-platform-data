# Phân biệt đầu vào ngẫu nhiên với thuật toán dùng ngẫu nhiên

Hai cụm từ **“đầu vào ngẫu nhiên”** và **“thuật toán dùng ngẫu nhiên”** có thể xuất hiện cùng nhau khi phân tích độ phức tạp, nhưng chúng nói về **hai nguồn xác suất khác nhau**:

- **Đầu vào ngẫu nhiên:** Dữ liệu `X` được lấy từ một phân phối xác suất `D`. Thuật toán xử lý có thể **hoàn toàn tất định**: với cùng một đầu vào, nó thực hiện cùng những bước như nhau.
- **Thuật toán dùng ngẫu nhiên:** Đầu vào `x` được **giữ cố định**, còn thuật toán tự sử dụng những lựa chọn ngẫu nhiên `R`: chọn chốt (pivot), lấy mẫu, xáo trộn, chọn hàm hash, v.v. Với cùng một `x` nhưng những `R` khác nhau, thời gian hoặc kết quả có thể khác nhau.

Hai tình huống đôi khi cho **cùng kỳ vọng trong một mô hình đặc biệt**, nhưng đó là một định lý cần chứng minh, **không phải lý do để đánh đồng hai mô hình**. Bài thuộc nhóm **Ngẫu nhiên hóa** và dùng quicksort làm ví dụ chính: quicksort chọn chốt đầu tiên trên **hoán vị đầu vào ngẫu nhiên**, so với quicksort **chọn chốt ngẫu nhiên bên trong thuật toán** trên một đầu vào cố định. Toàn bộ ví dụ mã dùng **Java 17+**.

Sau bài, bạn sẽ biết đặt đúng biến ngẫu nhiên, viết đúng kỳ vọng và lượng từ, nhận diện giả thiết phân phối đầu vào, phân tích đầu vào đối kháng, phân biệt kiểm thử thực nghiệm với chứng minh, hiểu hạt giống (seed), và không nhầm “dữ liệu nhìn ngẫu nhiên” với bảo đảm ngẫu nhiên hóa của thuật toán.

## 1. Chốt mô hình: dữ liệu X và lựa chọn R

Gọi:

- `X`: **biến ngẫu nhiên đầu vào**, nhận giá trị là một bộ dữ liệu cụ thể `x`.
- `D`: **phân phối của X**, ví dụ phân phối đều trên mọi hoán vị của n khóa phân biệt.
- `R`: **random coins** hoặc chuỗi lựa chọn ngẫu nhiên bên trong thuật toán, ví dụ những chỉ số pivot.
- `A(x,r)`: phép chạy của thuật toán trên đầu vào `x` với lựa chọn `r`.
- `T_A(x,r)`: chi phí của lần chạy, chẳng hạn số phép so sánh.
- `f(x)`: đáp án toán học đúng.

Một thuật toán tất định `A_det` không sử dụng R. Một thuật toán ngẫu nhiên `A_rand` có thể cho các quá trình chạy khác nhau trên cùng `x` khi R thay đổi.

### 1.1. Kỳ vọng theo đầu vào

Với thuật toán tất định và dữ liệu lấy theo phân phối D:

```text
E_{X~D}[ T_det(X) ].
```

Đây là **average-case complexity** tương ứng với **phân phối D đã cho**. Ví dụ:

```text
X = một hoán vị đều ngẫu nhiên của 40 khóa phân biệt
A_det = quicksort luôn chọn phần tử đầu làm pivot.
```

Một số input khiến `A_det` chậm, nhưng có thể **hiếm** dưới D. Thay D bằng phân phối khác có thể làm kỳ vọng đổi rất nhiều. **Không có một “average input” duy nhất** nếu chưa định nghĩa D.

### 1.2. Kỳ vọng theo đồng xu của thuật toán

Với một đầu vào `x` đã cho và thuật toán tự chọn pivot ngẫu nhiên:

```text
E_R[ T_rand(x,R) ].
```

Đây là **expected runtime of a randomized algorithm on a fixed input**. Nếu ta chứng minh:

```text
For EVERY valid fixed x with n distinct keys:
    E_R[T_rand(x,R)] <= c*n*log(n)
```

thì bảo đảm áp dụng cả khi `x` là dãy tăng, dãy giảm hoặc một hoán vị xấu mà đối thủ cố ý đưa vào, với điều kiện **lựa chọn R vẫn theo mô hình đã chứng minh**.

### 1.3. Nếu cả X và R đều ngẫu nhiên?

Khi hệ thống thực sự nhận dữ liệu `X~D` và thuật toán cũng dùng R độc lập với X, ta có:

```text
E_X E_R[T_rand(X,R)].
```

Theo luật kỳ vọng lặp, đây là kỳ vọng tổng quát của chi phí trên cả hai nguồn ngẫu nhiên. Nhưng:

```text
E_X E_R[T_rand(X,R)] = O(n log n)
```

**không tự suy ra** một bảo đảm cho **mọi x cụ thể**. Nó có thể chỉ trung bình tốt vì D ít sinh những input khó. Muốn bảo đảm từng input, phải chứng minh riêng `E_R[T_rand(x,R)]` cho **mọi x**.

### 1.4. Bảng ba phát biểu dễ nhầm

| Câu nói | Viết đúng | Điều được bảo đảm |
| --- | --- | --- |
| Thuật toán tất định nhanh trên dữ liệu ngẫu nhiên | `E_{X~D}[T_det(X)]` | Trung bình dưới **phân phối D** |
| Thuật toán dùng random nhanh trên input bất kỳ | `forall x: E_R[T_rand(x,R)] <= g(n)` | Trung bình theo **R cho từng x** |
| Hệ thống vừa nhận input random vừa dùng thuật toán random | `E_X E_R[T_rand(X,R)]` | Trung bình qua **cả X và R** |

Đổi thứ tự `E_X E_R` thường được phép khi các biến và chi phí thỏa điều kiện tích phân/kỳ vọng, nhưng dù tính được tổng kỳ vọng, **lượng từ “với mọi x” không tự xuất hiện**.

## 2. Thuật toán tất định trên đầu vào ngẫu nhiên

Một thuật toán **tất định** luôn xử lý cùng một input theo cùng một quy trình. Nếu nó chạy nhiều lần trên dữ liệu **khác nhau** do bộ sinh dữ liệu tạo ra, thời gian quan sát vẫn có thể thay đổi.

Ví dụ dùng **quicksort chọn chốt đầu tiên**:

```text
partition(A[l..r]):
    pivot = A[l]
    phân hoạch phần tử nhỏ/lớn hơn pivot
    quicksort trên hai phía
```

Không có `Random`, `nextInt`, seed, bốc thăm hoặc chọn mẫu nào trong thuật toán này. Tuy vậy, nếu input là hoán vị ngẫu nhiên, **vị trí/rank của phần tử đầu tiên có thể ngẫu nhiên** dưới mô hình D.

### 2.1. Input tăng dần là tình huống xấu

Với `n` khóa phân biệt:

```text
A = [0,1,2,...,n-1]
```

Chọn chốt đầu tiên khiến pivot luôn là phần tử nhỏ nhất của phần chưa xử lý; phân hoạch tạo một phần rỗng và phần còn lại có `n−1` phần tử.

Số so sánh với pivot:

```text
C(n) = (n-1) + C(n-1)
C(1) = 0

C(n) = n(n-1)/2 = Theta(n^2).
```

Với `n=40`:

```text
C(40) = 40*39/2 = 780.
```

**Không có xác suất nào trong tính toán này**: đầu vào cố định, thuật toán tất định, chi phí chắc chắn 780 theo đúng triển khai và bộ đếm minh họa.

### 2.2. Đầu vào là hoán vị đều ngẫu nhiên

Bây giờ **đổi mô hình đầu vào**, không đổi mã quicksort:

```text
X ~ Uniform(all n! permutations of n distinct keys)
A_det uses first pivot, without any internal random draws.
```

Ở mỗi bước, pivot có thể mang các thứ hạng khác nhau do phân phối thứ tự input. Quicksort chọn chốt đầu tiên trong mô hình này có số so sánh kỳ vọng:

```text
E_X[C_det(X)] = 2(n+1)H_n - 4n
```

với:

```text
H_n = 1 + 1/2 + 1/3 + ... + 1/n.
```

Vì `H_n=Theta(log n)`, kỳ vọng là **Theta(n log n)**.

Nhưng điều đó **chỉ đúng với phân phối D đã nói**: hoán vị đều ngẫu nhiên của các khóa phân biệt. Nếu D luôn trả mảng đã tăng dần, kỳ vọng trở lại `n(n−1)/2`.

### 2.3. “Dữ liệu nhìn lộn xộn” không phải chứng minh uniform

Một bộ dữ liệu sinh từ nguồn bên ngoài có thể trông không sắp xếp, nhưng không có nghĩa nó là **hoán vị đều**. Dữ liệu có thể thiên lệch, lặp nhiều khóa, gần có thứ tự, hoặc có tương quan ẩn.

Một sample benchmark trên vài input “random-looking” không cho phép khẳng định `E_X[T(X)] = O(n log n)` cho mọi phân phối D. Cần biết D hoặc nêu rõ đó chỉ là một **kết quả thực nghiệm trên tập mẫu**.

## 3. Thuật toán tự dùng ngẫu nhiên trên đầu vào cố định

Giữ nguyên:

```text
x = [0,1,2,...,39].
```

Nhưng thay quy tắc pivot:

```text
partition(A[l..r]):
    i = uniformly random index in [l,r]
    swap(A[l],A[i])
    pivot = A[l]
    phân hoạch hai phía
    quicksort đệ quy
```

Thuật toán **rút một lựa chọn ngẫu nhiên bên trong chính nó** cho mỗi đoạn con. Người dùng có thể gửi input x cố định, nhưng pivot được rút lại theo R.

### 3.1. Kỳ vọng trên từng x

Với mọi x gồm **n khóa phân biệt**, mỗi pivot rank trong đoạn con xuất hiện với xác suất đều. Khi đó:

```text
For every fixed x with n distinct keys:
    E_R[C_rand(x,R)]
      = 2(n+1)H_n - 4n
      = Theta(n log n).
```

Đây là bảo đảm **mạnh hơn theo phạm vi input** so với average-case của quicksort chọn pivot đầu tiên trên một D cụ thể. Nó bao gồm cả input tăng dần và giảm dần đã cố định.

### 3.2. Worst-case vẫn có thể lớn

Chọn pivot ngẫu nhiên không xóa những chuỗi chọn kém: vẫn có thể liên tục rút phần tử nhỏ nhất hoặc lớn nhất trong đoạn hiện tại, khiến chi phí đạt `Theta(n^2)`.

```text
E_R[T(x,R)] = O(n log n)
```

**không** đồng nghĩa với:

```text
for every R, T(x,R) = O(n log n).
```

Điều kiện trước là **trung bình theo R**, điều kiện sau là **worst-case trên mọi chuỗi R**. Chúng là hai loại bảo đảm khác nhau.

### 3.3. Ngẫu nhiên hóa không đồng nghĩa xác suất trả sai

Quicksort ngẫu nhiên vẫn tuân theo bất biến phân hoạch: khi kết thúc bình thường, kết quả là mảng đã sắp xếp. Pivot xấu khiến chi phí tăng chứ không tạo đáp án sai. Theo mô hình thuật toán toán học và cài đặt không lỗi:

```text
Pr_R[output incorrect | fixed x] = 0.
```

Đây là ví dụ **Las Vegas** (kết quả đúng, chi phí thay đổi). Monte Carlo lại có thể có xác suất kết quả sai, ví dụ một phép kiểm tra bằng nhau dựa trên fingerprint ngẫu nhiên có nguy cơ va chạm. **Xác suất lỗi** là biến cố khác với **xác suất chạy chậm** và khác cả hai loại kỳ vọng thời gian của bài.

## 4. Khi nào hai mô hình có cùng kết quả?

Với quicksort **chọn pivot đầu tiên** trên **hoán vị đều ngẫu nhiên** của n khóa phân biệt, và quicksort **chọn pivot đều ngẫu nhiên** trên **bất kỳ thứ tự cố định nào** của chính các khóa đó, hai mô hình cho cùng **phân phối thứ hạng pivot ở mỗi bước**.

Đây là cơ chế đằng sau sự tương đồng:

- Ở mô hình **X ngẫu nhiên**, pivot đầu tiên của một đoạn con có thứ hạng đều vì thứ tự tương đối của khóa trong đoạn con là ngẫu nhiên dưới giả thiết hoán vị đều.
- Ở mô hình **R ngẫu nhiên**, pivot được chọn bằng một chỉ số đều trong đoạn con, nên rank của pivot cũng đều, dù thứ tự input ban đầu cố định.
- Hai cách tạo pivot rank dẫn đến cùng **phân phối số phép so sánh** trong phân tích quicksort chuẩn với khóa phân biệt.

Bởi vậy, cả hai đều thỏa:

```text
2(n+1)H_n - 4n.
```

**Nhưng không được đảo kết luận:** “trong ví dụ quicksort có cùng kỳ vọng” **không** có nghĩa **mọi thuật toán** trên input ngẫu nhiên tương đương một thuật toán random trên input tùy ý. Mô hình đầu vào D, cách thuật toán dùng R và thứ tự lượng từ vẫn khác nhau.

### 4.1. Chứng minh kỳ vọng bằng cặp khóa

Sắp n khóa phân biệt theo thứ hạng `1,...,n`. Gọi `I_ij` là biến chỉ báo hai khóa hạng i<j được so sánh với nhau trong quicksort chuẩn.

Chúng được so sánh khi pivot đầu tiên trong **nhóm hạng từ i đến j** là một trong hai đầu mút của nhóm. Trong hai mô hình ngẫu nhiên nêu trên, mỗi rank trong nhóm có cơ hội như nhau để được chọn đầu tiên, nên:

```text
Pr[I_ij = 1] = 2/(j-i+1).
```

Số so sánh:

```text
C = SUM_{1<=i<j<=n} I_ij.
```

Dùng **tuyến tính của kỳ vọng**, không cần các `I_ij` độc lập:

```text
E[C]
  = SUM_{1<=i<j<=n} E[I_ij]
  = SUM_{1<=i<j<=n} 2/(j-i+1)
  = 2(n+1)H_n - 4n.
```

Cận bậc `Theta(n log n)` theo `H_n=Theta(log n)`. Định lý trên giả định **khóa phân biệt** và số so sánh của sơ đồ quicksort với chốt được phân hoạch như trong chương trình. Với nhiều khóa bằng nhau, một phiên bản phân hoạch hai phía có thể kém; cần phân hoạch **ba phía `<,=,>`** hoặc phân tích lại.

## 5. Một ví dụ lập luận sai và cách sửa

**Lập luận sai:**

> “Quicksort chọn chốt đầu tiên chạy O(n log n) trên input ngẫu nhiên, nên nó sẽ chạy expected O(n log n) trên bất kỳ dữ liệu nào mà người dùng đưa vào.”

Thiếu giả thiết chính: **input người dùng có tuân theo phân phối hoán vị đều không?** Nếu người dùng đưa mảng tăng dần thì chi phí là `Theta(n²)`.

**Lập luận đúng 1:**

> “Nếu input X được lấy đều từ mọi hoán vị n khóa phân biệt, quicksort chọn chốt đầu tiên có `E_X[T_det(X)]=Theta(n log n)`.”

**Lập luận đúng 2:**

> “Với mỗi input x cố định gồm n khóa phân biệt, quicksort chọn pivot đều ngẫu nhiên trong từng đoạn con có `E_R[T_rand(x,R)]=Theta(n log n)`.”

Lập luận thứ hai vẫn phụ thuộc **R thực sự được rút theo phân phối giả định**, không bị đối thủ đoán/kiểm soát trước khi cố định input.

## 6. Ai kiểm soát ngẫu nhiên, và vào thời điểm nào?

Nguồn ngẫu nhiên có thể đến từ:

| Nguồn | Được chọn bởi | Ví dụ | Kỳ vọng nào? |
| --- | --- | --- | --- |
| Phân phối input X | Bài toán/môi trường dữ liệu | Dữ liệu thực sự được lấy đều trên n! hoán vị | `E_X[T_det(X)]` |
| Random coins R | Bản thân thuật toán | Pivot bằng `rng.nextInt(...)` | `E_R[T_rand(x,R)]` |
| Trình tạo test | Hệ kiểm thử bên ngoài hàm | Sinh array và gọi deterministic sort | Đo **thực nghiệm** trên sample X |
| Khâu tiền xử lý xáo trộn | Một thành phần pipeline | Shuffle trước khi gọi sort | Tính random của **toàn pipeline**, không phải của riêng hàm sort |
| Cả X và R | Hai nguồn trong cùng hệ thống | Input ngẫu nhiên và pivot ngẫu nhiên | `E_X E_R[T_rand(X,R)]` |

### 6.1. Shuffling trước khi gọi hàm: trường hợp dễ nhập nhằng

Nếu dữ liệu gốc x cố định, nhưng chương trình tự chạy **Fisher–Yates shuffle** rồi gọi quicksort chọn chốt đầu tiên, thì hàm quicksort sau shuffle vẫn là **tất định**. Tuy nhiên **pipeline gồm shuffle + sort** là **thuật toán ngẫu nhiên hóa trên x cố định**, vì shuffle dùng R.

Phân biệt cấp độ:

```text
pipeline(x):
    y = randomShuffle(x)  // dùng R
    deterministicSort(y)  // tự thân không dùng R
```

Khi phân tích pipeline, phải **tính cả chi phí O(n) của shuffle** và chứng minh Fisher–Yates tạo phân phối đều trên hoán vị dưới mô hình rút số đều. Đừng đẩy phần random vào “đầu vào ngẫu nhiên” rồi quên chi phí tiền xử lý hoặc quên xác định ai kiểm soát shuffle.

### 6.2. Bộ test ngẫu nhiên không biến code thành randomized algorithm

Ví dụ:

```java
int[] data = generateRandomPermutation();
deterministicSort(data);
```

Bộ sinh chỉ nằm trong **harness**. Nếu người dùng tự gọi `deterministicSort(sortedArray)`, hàm không thể tự lựa pivot ngẫu nhiên. **Random test input** mô tả cách thử nghiệm, không phải một bảo đảm của API.

### 6.3. Seed cố định và tính tái lập

Trong Java, một PRNG có thể được tạo bằng:

```java
new SplittableRandom(20261110L)
```

Với cùng seed và cùng chuỗi lời gọi, kết quả thực nghiệm có thể tái lập. Đây là **đặc tính giúp debug/QA**, không biến bằng chứng trung bình trên pseudo-random thành một chứng minh. Từ góc nhìn toán học, tính ngẫu nhiên nằm ở phân phối seed và các random coins dự kiến; sau khi seed bị cố định, **một lần chạy cụ thể** lại tất định.

**Lưu ý đối kháng:** Nếu đối thủ nhìn thấy seed hoặc tất cả random choices **trước khi chọn x**, họ có thể chọn input phụ thuộc R. Chứng minh `forall x fixed before R: E_R[T(x,R)]<=g(n)` không tự bảo đảm cùng kết luận cho `x=x(R)` do đối thủ xây sau khi thấy R. Cần định nghĩa mô hình đối thủ và thứ tự chọn input/random rõ ràng. `SplittableRandom` không được thiết kế để chống dự đoán mật mã.

## 7. Đổi phân phối đầu vào thì average-case đổi theo

Lấy thuật toán quicksort chọn chốt đầu tiên `A_det` và n=40:

**Phân phối D1:** Luôn chọn mảng `[0,1,...,39]`.

```text
Pr_D1[X=sorted] = 1.
E_{X~D1}[C_det(X)] = 780.
```

**Phân phối D2:** Chọn đều trên 40! hoán vị.

```text
E_{X~D2}[C_det(X)]
  = 2*41*H_40 - 160
  ≈ 190.841.
```

Hai kỳ vọng đều đúng vì **D1 và D2 khác nhau**. Không có mâu thuẫn. Đầu vào sorted là trường hợp rất hiếm dưới D2 (xác suất `1/40!`) nhưng là trường hợp chắc chắn dưới D1.

**Thuật toán pivot ngẫu nhiên**, khi giữ input sorted cố định, có:

```text
E_R[C_rand(sorted,R)] ≈ 190.841.
```

Đây là cốt lõi của ý tưởng **bảo vệ phân tích khỏi hình dạng input** bằng lựa chọn pivot nội bộ (trên khóa phân biệt). Tuy nhiên input có nhiều khóa bằng nhau vẫn có thể làm phiên bản phân hoạch **hai phía** gặp `Theta(n²)` bất kể pivot; random pivot không tự chữa mọi thiết kế phân hoạch.

## 8. Kiểm thử và chứng minh: không thay nhau được

Ta có thể chạy quicksort 5.000 lần trên các input được shuffle, đo trung bình, sau đó chạy 5.000 lần random pivot trên input sorted và đo trung bình. Hai số có thể gần kỳ vọng lý thuyết.

Nhưng cần tách:

1. **Chứng minh toán học:** Dùng sự phân bố đều của rank pivot và tuyến tính kỳ vọng cho công thức `2(n+1)H_n−4n`.
2. **Kiểm thử/benchmark:** Chạy nhiều seed để phát hiện lỗi lập trình, so stdout, theo dõi trung bình mẫu và kiểm tra các trường hợp biên.
3. **Tính tin cậy của nguồn random:** PRNG sinh các giá trị xác định theo seed, trong khi phân tích lý thuyết thường giả định lựa chọn đồng đều và độc lập theo mô hình lý tưởng.
4. **Chi phí được đo:** Đếm số so sánh khác với đo wall-clock; wall-clock còn phụ thuộc JVM, GC, bộ nhớ, hệ điều hành và máy chạy.

Không thể chứng minh `E[T]=190.841` từ một kết quả thực nghiệm `mean=190.864`. Ngược lại, công thức đúng về mặt toán học không có nghĩa cài đặt Java chắc chắn không có bug; vì vậy chương trình có cả kiểm thử.

## 9. Đầu vào đối kháng: chọn x trước hay sau R?

### 9.1. Đối thủ cố định input trước khi thuật toán rút R

Mô hình quen thuộc của một randomized algorithm:

```text
Adversary chooses fixed x.
Algorithm privately samples R.
Algorithm runs on (x,R).
```

Nếu chứng minh `forall x, E_R[T(x,R)]<=g(n)`, đối thủ có thể chọn input rất xấu cho thuật toán tất định, nhưng không làm hỏng bảo đảm kỳ vọng khi R được rút sau và độc lập với x.

### 9.2. Đối thủ thấy R trước khi chọn input

Nếu:

```text
Algorithm's random seed/pivot choices are revealed.
Adversary chooses x based on R.
```

thì R và x **không còn độc lập**. Phân tích theo một x cố định có thể không áp dụng. Chẳng hạn khi pivot order có thể dự đoán, đối thủ cố tạo thứ tự khóa khiến các pivot liên tục cực lệch.

Không được tuyên bố một thuật toán random là “bất khả đánh bại” mà không mô tả mô hình đối thủ, tính riêng tư của randomness và thời điểm chọn input.

### 9.3. Đầu vào có phân phối thật khác giả định

Ứng dụng thực tế có thể gặp dữ liệu có thời gian thay đổi, sinh bởi hành vi người dùng, chứa khóa trùng nhiều, hoặc được tạo có chủ đích để phá phân hoạch. Câu “trong dữ liệu bình thường quicksort nhanh” là nhận xét kinh nghiệm, **không phải cận kỳ vọng đã định nghĩa** nếu không có mô hình D.

Nếu không muốn giả định D, có thể thiết kế **randomized pivot** hoặc dùng thuật toán **worst-case O(n log n)** như heapsort; đối với dữ liệu có nhiều khóa trùng, ưu tiên phân hoạch ba phía khi thích hợp.

## 10. Java 17+ minh họa hai thí nghiệm khác nhau

Tệp: **RandomInputVsRandomAlgorithmDemo.java**.

Chương trình dùng **cùng một phép phân hoạch hai phía** để so sánh công bằng:

- `deterministicSort(a)`: luôn chọn **đầu đoạn** làm pivot; không nhận `Random`.
- `randomizedSort(a,rng)`: rút pivot index bên trong mỗi lần phân hoạch.
- `shuffle(a,rng)`: Fisher–Yates chỉ dùng **để sinh input cho thí nghiệm đầu tiên**, không nằm trong hàm deterministicSort.
- `ascending(n)`: sinh input **tăng dần, cố định**.
- `Stats`: ghi số so sánh trung bình, nhỏ nhất và lớn nhất qua các lần thử.
- `enumerate`: duyệt **tất cả 7! = 5040 hoán vị** đầu vào, mỗi hoán vị gọi **thuật toán tất định**, kiểm tra kết quả đúng và so kỳ vọng thực nghiệm chính xác với công thức.
- Một ca **toàn khóa bằng nhau** cho thấy phiên bản phân hoạch hai phía có nhược điểm không được khắc phục bởi pivot ngẫu nhiên.

**Ranh giới quan trọng:** Mã không dùng `Arrays.sort` bên trong thuật toán; nó chỉ dùng mảng mong đợi để kiểm tra correctness. So sánh được đếm **mỗi lần so một phần tử với pivot** trong vòng phân hoạch, không bao gồm các phép so phụ của framework.

```java
import java.util.*;

public class RandomInputVsRandomAlgorithmDemo {
    static void swap(int[] a, int i, int j) {
        int t = a[i]; a[i] = a[j]; a[j] = t;
    }

    static int[] ascending(int n) {
        int[] a = new int[n];
        for (int i = 0; i < n; i++) a[i] = i;
        return a;
    }

    // Same partition algorithm for both variants.
    // rng == null means deterministic first-pivot quicksort.
    // rng != null means a random pivot for every recursive subarray.
    static long quicksort(
            int[] a, int left, int right, SplittableRandom rng) {
        if (left >= right) return 0L;
        int pivotIndex = (rng == null) ? left
                : left + rng.nextInt(right - left + 1);
        swap(a, left, pivotIndex);
        int pivot = a[left];
        int split = left;

        long comparisons = 0;
        for (int j = left + 1; j <= right; j++) {
            comparisons++;
            if (a[j] < pivot) {
                split++;
                swap(a, split, j);
            }
        }
        swap(a, left, split);
        return comparisons
                + quicksort(a, left, split - 1, rng)
                + quicksort(a, split + 1, right, rng);
    }

    static long deterministicSort(int[] a) {
        Objects.requireNonNull(a);
        return quicksort(a, 0, a.length - 1, null);
    }

    static long randomizedSort(int[] a, SplittableRandom rng) {
        Objects.requireNonNull(a);
        Objects.requireNonNull(rng);
        return quicksort(a, 0, a.length - 1, rng);
    }

    // This is an INPUT GENERATOR, not part of deterministicSort.
    static void shuffle(int[] a, SplittableRandom rng) {
        for (int i = a.length - 1; i > 0; i--) {
            swap(a, i, rng.nextInt(i + 1));
        }
    }

    static double harmonic(int n) {
        double sum = 0;
        for (int i = 1; i <= n; i++) sum += 1.0 / i;
        return sum;
    }

    // Expected number of pivot comparisons for distinct keys
    // with a uniformly random rank pivot on every subproblem.
    static double theoreticalExpectedComparisons(int n) {
        if (n <= 1) return 0.0;
        return 2.0 * (n + 1) * harmonic(n) - 4.0 * n;
    }

    static class Stats {
        long total;
        long count;
        long min = Long.MAX_VALUE;
        long max;

        void add(long comparisons) {
            total += comparisons;
            count++;
            min = Math.min(min, comparisons);
            max = Math.max(max, comparisons);
        }
        double mean() {
            return (double) total / count;
        }
    }

    // Exhaustively enumerate ALL input permutations, with
    // the deterministic algorithm fixed and no internal RNG.
    static void enumerate(
            int[] a, int index, int[] expected, Stats out) {
        if (index == a.length) {
            int[] copy = a.clone();
            long comparisons = deterministicSort(copy);
            if (!Arrays.equals(copy, expected)) {
                throw new AssertionError(
                        "bad deterministic sort");
            }
            out.add(comparisons);
            return;
        }
        for (int i = index; i < a.length; i++) {
            swap(a, index, i);
            enumerate(a, index + 1, expected, out);
            swap(a, index, i);
        }
    }

    public static void main(String[] args) {
        final int n = 40;
        int[] adversarial = ascending(n);
        long worst = deterministicSort(adversarial);
        System.out.println(
                "Fixed sorted input, first pivot: comparisons="
                + worst + ", correct=" + Arrays.equals(
                        adversarial, ascending(n)));

        int[] example = {7, 1, 6, 2, 5, 3, 4};
        int[] detExample = example.clone();
        int[] rndExample = example.clone();
        long detExampleCost = deterministicSort(detExample);
        long rndExampleCost = randomizedSort(
                rndExample, new SplittableRandom(20261110L));
        System.out.println(
                "Same fixed input: deterministic comparisons="
                + detExampleCost
                + ", randomized comparisons=" + rndExampleCost);
        System.out.println(
                "Both outputs: " + Arrays.toString(detExample)
                + " / " + Arrays.toString(rndExample));

        SplittableRandom inputRandom = new SplittableRandom(987654321L);
        SplittableRandom internalRandom = new SplittableRandom(123456789L);
        Stats averageRandomInput = new Stats();
        Stats averageRandomPivot = new Stats();

        // Two DIFFERENT experiments:
        // A: random input X, deterministic algorithm.
        // B: fixed sorted input x, randomized algorithm coins R.
        for (int trial = 0; trial < 5000; trial++) {
            int[] randomInput = ascending(n);
            shuffle(randomInput, inputRandom);
            long costInput = deterministicSort(randomInput);
            if (!Arrays.equals(randomInput, ascending(n))) {
                throw new AssertionError(
                        "bad sort on random input");
            }
            averageRandomInput.add(costInput);

            int[] fixedInput = ascending(n);
            long costPivot = randomizedSort(fixedInput, internalRandom);
            if (!Arrays.equals(fixedInput, ascending(n))) {
                throw new AssertionError(
                        "bad sort on fixed input");
            }
            averageRandomPivot.add(costPivot);
        }

        System.out.printf(Locale.ROOT,
                "Random INPUT, deterministic algorithm: "
                + "mean=%.3f, min=%d, max=%d%n",
                averageRandomInput.mean(),
                averageRandomInput.min, averageRandomInput.max);
        System.out.printf(Locale.ROOT,
                "Fixed INPUT, randomized algorithm: "
                + "mean=%.3f, min=%d, max=%d%n",
                averageRandomPivot.mean(),
                averageRandomPivot.min, averageRandomPivot.max);
        System.out.printf(Locale.ROOT,
                "Distinct-key theoretical E[comparisons] "
                + "for n=40: %.3f%n",
                theoreticalExpectedComparisons(n));

        Stats exhaustive = new Stats();
        enumerate(ascending(7), 0, ascending(7), exhaustive);
        System.out.printf(Locale.ROOT,
                "All 7! input permutations: count=%d, "
                + "exact mean=%.6f, theory=%.6f%n",
                exhaustive.count, exhaustive.mean(),
                theoreticalExpectedComparisons(7));

        int[] repeated = {5, 5, 5, 5, 5};
        long repeatedCost = randomizedSort(
                repeated, new SplittableRandom(8888L));
        System.out.println(
                "All-equal keys, 2-way quicksort: comparisons="
                + repeatedCost + ", correct="
                + Arrays.equals(repeated,
                        new int[] {5, 5, 5, 5, 5}));

        if (worst != (long) n * (n - 1) / 2
                || exhaustive.count != 5040) {
            throw new AssertionError(
                    "expected complexity counters mismatch");
        }
        System.out.println(
                "QA: PASS (5000 trials each, all 5040 permutations)");
    }
}
```

### 10.1. Lệnh biên dịch và chạy

Dùng JDK 17 trở lên:

```bash
javac RandomInputVsRandomAlgorithmDemo.java
java RandomInputVsRandomAlgorithmDemo
```

**Stdout chính xác với các seed trong mã:**

```text
Fixed sorted input, first pivot: comparisons=780, correct=true
Same fixed input: deterministic comparisons=15, randomized comparisons=11
Both outputs: [1, 2, 3, 4, 5, 6, 7] / [1, 2, 3, 4, 5, 6, 7]
Random INPUT, deterministic algorithm: mean=190.864, min=151, max=299
Fixed INPUT, randomized algorithm: mean=190.837, min=150, max=304
Distinct-key theoretical E[comparisons] for n=40: 190.841
All 7! input permutations: count=5040, exact mean=13.485714, theory=13.485714
All-equal keys, 2-way quicksort: comparisons=10, correct=true
QA: PASS (5000 trials each, all 5040 permutations)
```

### 10.2. Đọc từng dòng theo đúng mô hình

**Fixed sorted input, first pivot:** Dãy tăng đã cố định và thuật toán tất định → đúng **780 so sánh**, không có lấy mẫu.

**Same fixed input:** Cùng một mảng 7 phần tử, hai kiểu chọn pivot có số so sánh khác nhau (15 và 11). Cả hai sắp xếp chính xác, nên **sự khác biệt chi phí không phải lỗi đáp án**.

**Random INPUT, deterministic algorithm:** Mỗi thử tạo một **hoán vị mới** bằng Fisher–Yates ở phía **harness**, rồi đưa vào **cùng hàm deterministicSort không có RNG**. Trung bình 5.000 thử là **190.864**.

**Fixed INPUT, randomized algorithm:** Mỗi thử bắt đầu từ cùng dãy tăng `[0..39]`, rồi thuật toán **tự rút pivot**. Trung bình 5.000 thử là **190.837**.

**Theoretical E[comparisons]:** Định lý cho giá trị khoảng **190.841**, nằm gần hai trung bình đo được. Các trung bình mẫu khác nhau nhẹ là điều bình thường; chúng **không phải hai giá trị kỳ vọng toán học khác nhau**.

**All 7! input permutations:** Với n=7, chương trình kiểm tra **đầy đủ 5040 hoán vị**, so chi phí trung bình đúng `13.485714` với công thức cũng cho `13.485714` sau khi in 6 chữ số sau dấu phẩy. Đây là một đối chiếu hữu ích để phát hiện sai công thức/triển khai, dù chứng minh với n tùy ý vẫn dựa trên lý luận cặp khóa.

**All-equal keys:** Mảng toàn 5 vẫn được sort đúng, nhưng phân hoạch hai phía của mã có số so sánh bằng `5*4/2=10`. Nếu tăng n, cấu hình toàn khóa bằng nhau tạo `Theta(n²)` ngay cả với pivot ngẫu nhiên; **bảo đảm n log n đã nói yêu cầu khóa phân biệt**. Muốn xử lý duplicate hiệu quả, nên xem xét 3-way partition.

**QA PASS:** 5.000 lượt test cho mỗi mô hình và toàn bộ 7! hoán vị được thực thi không phát hiện lỗi, mọi mảng sau sort đều đúng.

## 11. Chứng minh tính đúng của quicksort và công thức kỳ vọng

### 11.1. Correctness không phụ thuộc pivot chọn thế nào

Ở một lần partition, thuật toán lấy pivot và duyệt các phần tử còn lại; phần nhỏ hơn pivot được đưa về bên trái, phần không nhỏ hơn ở bên phải. Sau đó pivot được đặt đúng ở giữa hai nhóm.

Bất biến sau partition:

```text
a[left..split-1] < pivot
a[split] == pivot
a[split+1..right] >= pivot.
```

Hai nhánh có kích thước nhỏ hơn đoạn ban đầu, nên quy nạp theo độ dài đoạn: sau khi sort hai nhánh, toàn đoạn được sort. Lựa chọn pivot bằng đầu đoạn hay index ngẫu nhiên đều **không ảnh hưởng** kết luận về thứ tự cuối cùng.

### 11.2. Worst-case của first-pivot trên dãy tăng

Với n khóa phân biệt đã tăng dần, pivot đầu tiên luôn nhỏ nhất; mỗi lần phải so n−1 phần tử còn lại. Tổng:

```text
C(n) = SUM_{k=1..n} (k-1)
     = n(n-1)/2
     = Theta(n^2).
```

Trong mã n=40 nên `C=780`, một giá trị **tất định** của input sorted.

### 11.3. Kỳ vọng với pivot rank đồng đều

Đặt các khóa theo rank từ 1 đến n. Hai khóa rank i<j được so sánh trong quicksort tiêu chuẩn khi khóa đầu tiên được chọn làm pivot trong tập rank `[i..j]` là một trong hai đầu mút; xác suất:

```text
p_ij = 2/(j-i+1).
```

Gọi `I_ij` là 1 nếu hai khóa được so sánh, 0 nếu không. Tổng số so sánh là:

```text
C = SUM_{i<j} I_ij.
```

Tuyến tính kỳ vọng:

```text
E[C]
  = SUM_{i<j} E[I_ij]
  = SUM_{i<j} p_ij
  = 2(n+1)H_n - 4n.
```

**Không cần các biến chỉ báo độc lập** để dùng tuyến tính kỳ vọng. Sự đồng đều của pivot rank có thể đến từ **input hoán vị đều** khi thuật toán tất định lấy first pivot, hoặc đến từ **R** khi thuật toán lấy pivot đều trên đoạn con với input cố định. Đó là điểm hai mô hình gặp nhau **trong bài toán này**.

## 12. Bảo đảm phân tích: hãy viết lượng từ cho đúng

Xem ba phát biểu:

**A. Average-case phụ thuộc D:**

```text
Given D = uniform permutations:
    E_{X~D}[T_det(X)] = Theta(n log n).
```

**B. Randomized expected theo từng đầu vào:**

```text
For every fixed x with n distinct keys:
    E_R[T_rand(x,R)] = Theta(n log n).
```

**C. Worst-case trên mọi lựa chọn random:**

```text
For every fixed x and every random tape R:
    T_rand(x,R) <= O(n log n).
```

Trong quicksort chuẩn, A và B đúng dưới giả thiết đã cho; C sai vì tồn tại những chuỗi pivot cực lệch.

**A không kéo theo B:** Một thuật toán tất định có thể rất tốt dưới D nhưng cực chậm trên một x nằm ngoài vùng phổ biến của D.

**B không kéo theo C:** Kỳ vọng tốt vẫn cho phép một số lựa chọn R cực chậm.

**B là khẳng định trên từng x; C là worst-case mạnh hơn:** Chúng không chỉ khác ở chữ expected mà còn khác ở lượng từ `E_R` và `for every R`.

### 12.1. Cận đuôi thời gian là một câu hỏi thứ ba

Với biến chi phí không âm `T`, bất đẳng thức Markov cho:

```text
Pr[T >= a] <= E[T]/a, a>0.
```

Ví dụ nếu `E[T]=200`, thì:

```text
Pr[T >= 2000] <= 0.1.
```

Đây là **cận trên**, không phải xác suất trễ chính xác. Khi mục tiêu là deadline, phải nghiên cứu **tail probability** hoặc worst-case, chứ không lấy giá trị kỳ vọng làm giới hạn cứng. Xác suất vượt deadline vẫn **khác xác suất kết quả sai**.

## 13. Những lỗi thường gặp

1. Coi bộ sinh **input random** trong test là một phần của hàm **sort tất định**.
2. Chỉ vì dữ liệu “nhìn ngẫu nhiên” mà mặc định nó có phân phối đều trên hoán vị.
3. Quên nêu phân phối D khi nói average-case.
4. Lấy trung bình theo input X rồi tự đổi thành trung bình theo random coins R.
5. Viết `E_X[T_det(X)]` nhưng kết luận trên **mọi x**.
6. Đưa input sorted cho first-pivot quicksort và mong expected n log n chỉ vì thuật toán tên quicksort.
7. Coi random pivot làm mất hoàn toàn worst-case quadratic.
8. Coi một pivot xấu là một trường hợp **sai đáp án**.
9. Coi dữ liệu được shuffle sẵn nhưng thuật toán không có RNG là “hàm sort tự ngẫu nhiên”.
10. Coi pipeline có shuffle trước sort là hoàn toàn tất định; pipeline có randomness.
11. Quên tính chi phí `O(n)` của shuffle khi phân tích pipeline.
12. Lặp test với cùng seed, cùng chuỗi gọi mà gọi là phép thử độc lập.
13. Dùng seed cố định để chứng minh phân phối runtime thay vì tái lập testcase.
14. Cho rằng PRNG thông thường là nguồn ngẫu nhiên mật mã.
15. Không xác định đối thủ chọn x trước hay sau khi biết R.
16. Áp `forall fixed x` cho x phụ thuộc R mà không chứng minh lại.
17. Bỏ giả thiết n khóa phân biệt trong công thức quicksort chuẩn.
18. Coi pivot ngẫu nhiên tự khắc phục mọi input chứa nhiều khóa trùng.
19. Không phân biệt thuật toán hai phía với ba phía khi phân tích duplicate.
20. Nhầm độ phức tạp kỳ vọng O(n log n) với giới hạn thời gian mỗi lần chạy.
21. Dùng một lần chạy nhanh để khẳng định mean runtime của cả phân phối.
22. Dùng một lần chạy chậm để bác bỏ một cận kỳ vọng đúng.
23. So hai trung bình mẫu hơi khác nhau rồi tuyên bố hai kỳ vọng toán học khác nhau.
24. Coi `E_X E_R[T(X,R)]` luôn suy ra `forall x E_R[T(x,R)]`.
25. Quên phân biệt kỳ vọng về số so sánh với thời gian thực tế wall-clock.
26. Dùng `Math.random()` bên ngoài hàm để tạo testcase, rồi kết luận bản thân hàm có random.
27. Không kiểm chứng đầu ra vẫn đúng khi pivot thay đổi.
28. Bỏ ca input tăng/giảm, input rỗng/một phần tử và duplicate trong test.
29. Dùng phân phối giả định của môi trường nhưng không có dữ liệu xác minh.
30. Khẳng định xác suất lỗi của thuật toán chỉ từ phân phối thời gian.
31. Dùng một giá trị seed bị lộ cho đầu vào đối kháng rồi áp định lý với R bí mật.
32. Bỏ qua chi phí đệ quy sâu/stack overflow của một cài đặt quicksort trên dữ liệu rất lớn.
33. Giả sử tuyến tính kỳ vọng đòi các biến chỉ báo độc lập; thực tế không cần.
34. Tái sử dụng công thức expected comparisons của quicksort chuẩn cho mọi biến thể partition mà không kiểm tra.
35. Không ghi rõ lượng từ “for every fixed input” trong lời giải randomized algorithm.

## 14. Bài tập có đáp án

**Bài 1.** Đầu vào X lấy từ D, hàm xử lý không có random. Kỳ vọng theo biến nào?

**Đáp án:** `E_{X~D}[T_det(X)]`.

**Bài 2.** Input x cố định nhưng thuật toán chọn pivot ngẫu nhiên. Kỳ vọng theo biến nào?

**Đáp án:** `E_R[T_rand(x,R)]`.

**Bài 3.** X và R đều ngẫu nhiên, độc lập, muốn trung bình toàn hệ thống thì viết gì?

**Đáp án:** `E_X E_R[T_rand(X,R)]`.

**Bài 4.** “Chạy nhanh trên đầu vào ngẫu nhiên” có nói input nào cũng nhanh không?

**Đáp án:** Không; kết luận phụ thuộc phân phối đầu vào D.

**Bài 5.** Quicksort first-pivot trên n khóa phân biệt tăng dần cần bao nhiêu so sánh?

**Đáp án:** `n(n−1)/2` theo triển khai đếm mỗi lần so với pivot.

**Bài 6.** Khi n=40, số so sánh ở bài 5?

**Đáp án:** `40*39/2=780`.

**Bài 7.** Quicksort first-pivot trên hoán vị đều có expected comparisons bậc nào?

**Đáp án:** `Theta(n log n)` với khóa phân biệt.

**Bài 8.** Nêu công thức chính xác expected comparisons của quicksort chuẩn theo rank pivot đồng đều.

**Đáp án:** `2(n+1)H_n−4n`.

**Bài 9.** Quicksort random pivot trên input sorted cố định có expected comparisons bậc nào?

**Đáp án:** `Theta(n log n)` nếu n khóa phân biệt và pivot rank đều trên mỗi đoạn con.

**Bài 10.** Random pivot có loại được worst-case quadratic trên mọi random tape không?

**Đáp án:** Không; chuỗi pivot cực lệch vẫn có thể xảy ra.

**Bài 11.** Chọn pivot xấu có làm quicksort trả mảng sai không?

**Đáp án:** Không, nếu triển khai đúng và thuật toán kết thúc bình thường; chỉ làm tăng chi phí.

**Bài 12.** Bộ sinh random permutation nằm bên ngoài `deterministicSort`. Hàm sort có phải thuật toán random không?

**Đáp án:** Không; bản thân hàm vẫn tất định, dù harness cấp dữ liệu ngẫu nhiên.

**Bài 13.** Hệ thống tự shuffle input trước khi gọi deterministicSort. Toàn pipeline có random không?

**Đáp án:** Có, vì bước shuffle rút R; khi tính chi phí phải tính cả shuffle.

**Bài 14.** Nếu D luôn sinh mảng sorted n=40, expected first-pivot comparisons?

**Đáp án:** 780, vì phân phối tập trung trên một input.

**Bài 15.** Nếu D uniform over n! permutations, expected comparisons theo D là gì?

**Đáp án:** `2(n+1)H_n−4n`.

**Bài 16.** Vì sao hai mô hình quicksort có cùng kỳ vọng trong ví dụ?

**Đáp án:** Vì rank pivot ở mỗi đoạn con có phân phối đều trong cả hai mô hình dưới các giả thiết khác nhau.

**Bài 17.** Với hai khóa rank i<j, xác suất chúng được so sánh khi rank pivot đều?

**Đáp án:** `2/(j−i+1)`.

**Bài 18.** Có cần các biến chỉ báo cặp khóa độc lập mới cộng được kỳ vọng không?

**Đáp án:** Không, dùng tính tuyến tính kỳ vọng.

**Bài 19.** Mẫu 5.000 lần random INPUT được mean=190.864 chứng minh giá trị lý thuyết chính xác là 190.864 không?

**Đáp án:** Không; đó là trung bình mẫu, còn lý thuyết với n=40 là khoảng 190.841.

**Bài 20.** Mẫu 5.000 lần random PIVOT trên x fixed được mean=190.837 chứng minh mọi lần đều dưới 300 phép so sánh không?

**Đáp án:** Không; max=304 trong mẫu và vẫn có thể có lựa chọn R chậm hơn nữa.

**Bài 21.** Vì sao 7! = 5040 hoán vị giúp QA ví dụ n=7?

**Đáp án:** Có thể kiểm tra toàn bộ miền hoán vị và so mean thực nghiệm chính xác với công thức cho n=7.

**Bài 22.** Quicksort hai phía trên n khóa bằng nhau có thể đạt bậc chi phí nào?

**Đáp án:** `Theta(n²)`, ngay cả khi random pivot, vì không tạo được phân hoạch cân bằng nếu cùng khóa đi hết một phía.

**Bài 23.** Cải thiện partition khi có nhiều khóa trùng?

**Đáp án:** Dùng phân hoạch ba phía `<pivot`, `=pivot`, `>pivot` hoặc thuật toán khác có bảo đảm thích hợp.

**Bài 24.** Seed cố định có giúp tái lập bug không?

**Đáp án:** Có, với cùng seed và thứ tự gọi PRNG.

**Bài 25.** Seed cố định có chứng minh độc lập xác suất của các phép chọn không?

**Đáp án:** Không; nó tạo một chuỗi giả ngẫu nhiên xác định và chỉ giúp thử nghiệm tái lập.

**Bài 26.** Nếu đối thủ thấy R rồi chọn x phụ thuộc R, có thể áp trực tiếp định lý cho x fixed không?

**Đáp án:** Không; phải phân tích lại mô hình đối thủ/thứ tự lựa chọn.

**Bài 27.** Nếu `E[T]=200`, Markov cho `Pr[T>=2000]` cận trên bao nhiêu?

**Đáp án:** `<=0.1` vì T không âm.

**Bài 28.** Cận Markov trên là xác suất trễ chính xác hay cận?

**Đáp án:** Chỉ là cận trên, có thể lỏng.

**Bài 29.** Nếu kết quả sort chính xác nhưng đôi khi chậm, xác suất trả sai có phải xác suất chạy chậm không?

**Đáp án:** Không; đó là hai biến cố khác nhau. Với quicksort đúng, xác suất sai là 0.

**Bài 30.** Nêu cách trình bày ngắn gọn đúng hai mô hình trong báo cáo.

**Đáp án:** Với average-case ghi `X~D` và `E_X[T_det(X)]`; với randomized runtime ghi `for every fixed x` và `E_R[T_rand(x,R)]`, kèm giả thiết ngẫu nhiên của R.

## 15. Checklist trước khi sử dụng phân tích xác suất

- [ ] Đã xác định biến ngẫu nhiên là **X đầu vào**, **R của thuật toán** hay cả hai?
- [ ] Nếu X ngẫu nhiên, đã nêu phân phối D và tính hợp lý của nó?
- [ ] Nếu R ngẫu nhiên, đầu vào x có cố định trước khi rút R?
- [ ] Đã phân biệt `E_X` và `E_R` trong công thức?
- [ ] Khẳng định đúng lượng từ: **trung bình dưới D** hay **mọi x cố định**?
- [ ] Nếu có shuffle tiền xử lý, đã tính chi phí và phân phối hoán vị?
- [ ] Nếu dùng quicksort, khóa phân biệt hay có thể trùng?
- [ ] Đã kiểm tra worst-case trên x và trên R tách biệt khỏi expected?
- [ ] Có phân biệt xác suất chạy lâu với xác suất kết quả sai?
- [ ] Đã kiểm tra correctness độc lập với lựa chọn pivot?
- [ ] Seed cố định chỉ dùng cho tái lập thí nghiệm, không thay chứng minh?
- [ ] Benchmark có nêu số mẫu, kích thước n, nguồn sinh và đơn vị chi phí?
- [ ] Có ca sorted, reversed, all-equal, rỗng, và một phần tử?
- [ ] Nếu đối kháng, đã làm rõ đối thủ có nhìn thấy random coins không?
- [ ] Nếu viện dẫn cùng kỳ vọng giữa hai mô hình, đã nêu điều kiện làm chúng tương đương?

## Kết luận

**Đầu vào ngẫu nhiên** là xác suất nằm trong **dữ liệu X**:

```text
E_{X~D}[T_det(X)].
```

**Thuật toán dùng ngẫu nhiên** là xác suất nằm trong **lựa chọn R của chính thuật toán** khi **x đã cố định**:

```text
E_R[T_rand(x,R)].
```

Chúng có thể tạo cùng công thức `2(n+1)H_n−4n` ở hai biến thể quicksort với khóa phân biệt, nhưng **phạm vi bảo đảm khác nhau**: thuật toán tất định cần **giả thiết phân phối input**, trong khi pivot ngẫu nhiên cung cấp cận kỳ vọng trên **từng input cố định** dưới mô hình random coins phù hợp.

Hãy luôn chỉ rõ **ai sinh ngẫu nhiên**, **ngẫu nhiên xảy ra trước hay sau khi input được chọn**, và **kỳ vọng được lấy theo biến nào**. Ba câu hỏi đó giúp tránh nhầm average-case với randomized expected-case, tránh đánh đồng chạy chậm với trả sai, và viết phân tích thuật toán ngẫu nhiên hóa có thể kiểm chứng.
