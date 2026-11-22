# Tiền xử lý ước nguyên tố nhỏ nhất

**Tiền xử lý ước nguyên tố nhỏ nhất** (*smallest prime factor precomputation*, viết tắt **SPF**) là kỹ thuật dùng một lần sàng số nguyên để xây mảng `spf[x]` cho mọi số nguyên x trong miền cố định `1..N`. Với `x≥2`, `spf[x]` là **số nguyên tố nhỏ nhất chia hết x**. Sau khi có bảng, ta phân tích một số x≤N thành thừa số nguyên tố bằng cách **liên tiếp chia x cho `spf[x]`**, không phải thử lần lượt các số từ 2 tới √x. Từ cùng phân tích thừa số, ta có thể nhanh chóng đếm ước, liệt kê ước, tính hàm Euler φ, hàm Möbius μ, tổng ước σ, và số lượng thừa số nguyên tố khác nhau.

Đây là một kỹ thuật nền tảng trong nhóm **Thuật toán số học** của **Computer Science Algorithms**, đặc biệt hữu ích khi có **rất nhiều truy vấn** trên cùng miền số nguyên bị chặn. Ví dụ, đề yêu cầu xử lý 100.000 câu hỏi “phân tích n thành thừa số nguyên tố” hoặc “n có bao nhiêu ước?” với mọi n≤1.000.000. Thay vì thực hiện trial division gần như từ đầu cho mỗi truy vấn, ta bỏ chi phí để **xây chỉ mục SPF một lần** rồi tái sử dụng.

Bài trình bày hai cách xây bảng: **sàng kiểu Eratosthenes** trong `O(N log log N)` và **sàng tuyến tính (linear/Euler sieve)** trong `O(N)`, cùng chứng minh vì sao mỗi composite được gán đúng ước nguyên tố nhỏ nhất. Phần thực hành có **Java 17+ chạy độc lập**, kết hợp phân tích thừa số, kiểm tra nguyên tố, tính các hàm số học, sinh danh sách ước, và tính trước những hàm ấy cho mọi n≤N bằng công thức truy hồi. Bài cũng chỉ ra giới hạn về bộ nhớ, tràn số, miền truy vấn, các ca 0/1/âm và kiểm thử độc lập bằng phép chia thử.

**Mục tiêu học tập:** tự cài SPF theo hai cách; hiểu bất biến `spf[n]`; phân tích một x thành tích các lũy thừa nguyên tố và chứng minh độ phức tạp; suy ra φ, τ, σ, μ, ω và Ω; dùng bảng để tính hàng loạt truy vấn; biết khi nào việc cấp phát `O(N)` không còn phù hợp và phải đổi mô hình.

## 1. Định nghĩa SPF và những quy ước không được nhầm

Với số nguyên `n≥2`, định nghĩa:

**`spf(n)=min{p | p là số nguyên tố và p chia hết n}`.**

Một số ví dụ:

| n | Phân tích thành thừa số nguyên tố | spf[n] |
|---:|---|---:|
| 2 | 2 | 2 |
| 3 | 3 | 3 |
| 4 | 2² | 2 |
| 6 | 2·3 | 2 |
| 9 | 3² | 3 |
| 15 | 3·5 | 3 |
| 25 | 5² | 5 |
| 49 | 7² | 7 |
| 60 | 2²·3·5 | 2 |
| 84 | 2²·3·7 | 2 |
| 97 | 97 | 97 |

Điểm quan trọng: **SPF là số nguyên tố**, không phải “ước dương nhỏ nhất” nói chung. Nếu tính cả 1 thì 1 là ước nhỏ nhất của mọi số dương và bài toán trở nên vô nghĩa. SPF bắt buộc chọn từ **các số nguyên tố**.

Nếu n là **nguyên tố**, ước nguyên tố duy nhất của nó là **chính n**, do đó:

**`n≥2 là số nguyên tố ⇔ spf[n]=n`.**

Nếu n là hợp số, `spf[n]<n` và đương nhiên `spf[n]` chia hết n.

### Trường hợp 0 và 1

- **n=1:** không có ước nguyên tố; `spf(1)` **không được định nghĩa theo toán học**. Trong mảng lập trình, ta có thể đặt `spf[1]=1` làm **sentinel/convention** để thuận tiện, nhưng **không** vì thế mà coi 1 là nguyên tố.
- **n=0:** mọi số nguyên tố đều chia 0, nên khái niệm “thừa số nguyên tố của 0” theo phân tích duy nhất thông thường **không áp dụng**. Bài này để `spf[0]=0` như giá trị chưa dùng, và **từ chối factorize(0)**. Không được đưa 0 vào vòng `x=x/spf[x]` vì dễ chia cho 0 hoặc lặp vô hạn.
- **n âm:** có thể phân tích dấu −1 và phần trị tuyệt đối nếu thiết kế API hỗ trợ, nhưng mã ở bài **chỉ chấp nhận x≥1**. Đặc biệt `Math.abs(Integer.MIN_VALUE)` vẫn âm do tràn số, nên không thể sửa API âm bằng cách gọi Math.abs một cách ngây thơ.

Mảng trong Java là **0-based**; ta dành các chỉ số 0..N, trong đó chỉ số 0 không phải đầu vào factorization. Mọi API truy vấn của bài đều yêu cầu **`1≤x≤N`**, trừ khi nói rõ khác.

## 2. Tại sao cần tiền xử lý?

Giả sử cần phân tích một số x thành thừa số nguyên tố. Cách dễ nhất là **trial division**:

1. Với d từ 2 tới khi `d·d>x`, thử chia x cho d.
2. Nếu chia hết, chia lặp để thu số mũ của d.
3. Phần x còn lại >1 là một số nguyên tố.

Để **một** số x, cách này phù hợp và có cận O(√x) số phép thử chia trong trường hợp x là số nguyên tố gần giới hạn. Với nhiều truy vấn, công việc lặp lại rất nhiều.

Nếu có Q truy vấn x≤N:

- Trial division cơ bản: có thể cần tới **O(Q√N)** phép thử trong cận xấu.
- Xây một bảng SPF theo sàng tuyến tính: **O(N)** thời gian tiền xử lý và O(N) bộ nhớ theo mô hình chuẩn.
- Mỗi lần phân tích x bằng bảng SPF: **O(log x)** bước chia trong trường hợp x≥2.

Tổng có thể được chặn bởi:

**`O(N + Σ_i log x_i)`**,

chưa tính số ký tự in ra hoặc phép toán phụ của các truy vấn. Tất nhiên, nếu Q=1 và N rất lớn, cấp phát cả bảng có thể **chậm và tốn RAM hơn trial division**.

Đây là một dạng đánh đổi:

**Xây chỉ mục một lần → nhiều truy vấn nhanh; đổi lại cần biết giới hạn N và giữ bảng O(N) trong bộ nhớ.**

## 3. Mảng SPF minh họa trên 1..20

Quy ước `spf[1]=1`. Với 2..20:

~~~text
n:       1  2  3  4  5  6  7  8  9 10
spf[n]:  1  2  3  2  5  2  7  2  3  2

n:      11 12 13 14 15 16 17 18 19 20
spf[n]: 11  2 13  2  3  2 17  2 19  2
~~~

Với n=18, `spf[18]=2`. Chia:

~~~text
18 / 2 = 9
spf[9] = 3
 9 / 3 = 3
spf[3] = 3
 3 / 3 = 1
~~~

Thu được `18=2·3·3=2·3²`. Không phải tìm mọi ước của 18 từ đầu. Mỗi lần lấy ra `p=spf[x]`, p luôn là **một số nguyên tố thực sự** và phần còn lại x/p vẫn nằm trong 1..N.

### Hai dạng đầu ra thừa số

- **Danh sách có lặp (prime factors with multiplicity):** `[2,3,3]` cho 18.
- **Danh sách các cặp nguyên tố–số mũ:** `[(2,1),(3,2)]`, thường viết `2·3²`.

Dạng thứ hai tiết kiệm hơn khi cần tính hàm số học: chỉ cần duyệt từng **nguyên tố phân biệt** một lần. Dữ liệu `[(p,e)]` cũng là biểu diễn chuẩn của định lý phân tích duy nhất:

**`n=∏_{i=1}^k p_i^{e_i}`**, với p_i khác nhau và e_i≥1.

## 4. Cách 1: sàng kiểu Eratosthenes ghi SPF lần đầu

Ta có thể biến tấu sàng nguyên tố để ghi **ước nguyên tố nhỏ nhất**:

- Khởi tạo `spf[0..N]=0`, đặt `spf[1]=1`.
- Duyệt p tăng từ 2 tới N.
- Nếu `spf[p]≠0`, p đã biết là hợp số, bỏ qua như một số nguyên tố dùng để đánh dấu.
- Nếu `spf[p]==0`, p là nguyên tố chưa đánh dấu:
  - Gán `spf[p]=p`.
  - Với các bội `j=p²,p²+p,p²+2p,...≤N`, nếu `spf[j]==0` thì gán `spf[j]=p`.
- Khi kết thúc, mỗi số x≥2 đều có SPF đúng.

Pseudocode:

~~~text
classicSPF(N):
    spf[0..N] = 0
    spf[1] = 1

    for p = 2 .. N:
        if spf[p] != 0:
            continue       // already marked composite

        spf[p] = p         // p is prime

        if p * p > N:
            continue

        for j = p*p; j <= N; j += p:
            if spf[j] == 0:
                spf[j] = p

    return spf
~~~

### Vì sao chỉ đánh dấu từ p²?

Nếu j là bội của p và `j<p²`, thì `j=p·k` với `2≤k<p`. Bản thân k có một ước nguyên tố `q≤k<p`, suy ra j đã có ước nguyên tố nhỏ hơn p. Trong lượt duyệt các số nhỏ hơn p, j đã được đánh dấu hoặc sẽ được xét trước khi tới p.

Vậy bắt đầu ở **p²** không bỏ sót composite cần gán SPF=p.

### Vì sao “chỉ gán nếu bằng 0” là bắt buộc?

Nếu số j có nhiều ước nguyên tố, ví dụ 30 chia hết cho 2,3,5, ta cần **giữ lần gán đầu tiên theo thứ tự nguyên tố tăng dần**:

- Lượt p=2: spf[30]=2.
- Lượt p=3 hoặc p=5: **không được ghi đè**.

Nếu cứ gán `spf[j]=p` ở mọi lần đi qua bội, giá trị cuối có thể là 5, **không còn là ước nguyên tố nhỏ nhất**.

### Chứng minh tính đúng

Với mỗi hợp số x, đặt p là ước nguyên tố nhỏ nhất của x. Vì x hợp số, x≥p² (nếu x=p·q thì q≥p). Do vậy x xuất hiện trong lượt đánh dấu các bội của p từ p². Không có nguyên tố nào <p chia x, nên trước lượt p, spf[x] chưa được gán bởi một nguyên tố nhỏ hơn p. Tại p, spf[x] nhận p. Các lượt nguyên tố lớn hơn không ghi đè. Nếu x nguyên tố, nó không thể bị đánh dấu như bội của một nguyên tố nhỏ hơn, nên spf[x]=x.

### Độ phức tạp

Tổng số lần xét bội của các nguyên tố p≤√N tỷ lệ `Σ_{p prime≤√N} N/p`, có cận chuẩn **O(N log log N)**; có thêm O(N) cho vòng lặp qua các chỉ số. Mảng spf tốn **O(N)** bộ nhớ.

Nếu muốn code đơn giản, đây là lựa chọn dễ đọc. Nhưng chú ý phép `p*p` có thể **tràn int** trước khi đem so với N. Để an toàn, dùng điều kiện `p≤N/p` hoặc phép nhân `(long)p*p`, như mã Java ở mục 11.

## 5. Cách 2: sàng tuyến tính (Euler/linear sieve)

Sàng tuyến tính xây bảng SPF trong **O(N)** thời gian theo mô hình mỗi phép tra cứu/cập nhật phần tử là O(1). Nó dùng thêm một danh sách `primes` các nguyên tố đã gặp.

Duyệt x tăng dần từ 2 tới N:

1. Nếu `spf[x]==0`, x chưa bị đánh dấu ⇒ x nguyên tố. Gán `spf[x]=x` và thêm x vào primes.
2. Với các nguyên tố p trong primes theo thứ tự tăng:
   - Nếu **`p>spf[x]`**, dừng vòng.
   - Nếu **`x·p>N`**, dừng vòng.
   - Gán **`spf[x·p]=p`**.
3. Tiếp tục x+1.

Pseudocode:

~~~text
linearSPF(N):
    spf[0..N] = 0
    spf[1] = 1
    primes = []

    for x = 2 .. N:
        if spf[x] == 0:
            spf[x] = x
            primes.add(x)

        for p in primes increasing:
            if p > spf[x]:
                break
            if x > N / p:
                break

            spf[x * p] = p

    return spf, primes
~~~

### Điều kiện p≤spf[x] có ý nghĩa gì?

Xét composite `v=x·p` với p là số nguyên tố. Nếu p≤spf[x], **x không có ước nguyên tố nào nhỏ hơn p**, nên p là ước nguyên tố nhỏ nhất của v:

**`spf[x·p]=p`.**

Nếu p>spf[x], v vẫn có một ước nguyên tố nhỏ hơn p là spf[x]; gán SPF(v)=p sẽ sai. Đồng thời để đảm bảo mỗi composite được tạo **đúng một lần**, ta không sinh các cặp x,p không cần thiết.

### Vì sao mỗi hợp số được đánh dấu đúng một lần?

Cho hợp số v, gọi p=spf[v] và x=v/p. Vì p là ước nguyên tố nhỏ nhất của v, x không có ước nguyên tố <p; do đó **`p≤spf[x]`**. Khi xử lý x, vòng primes có p, điều kiện cho phép gán `spf[x·p]=p`, tức gán đúng v.

Giả sử cũng có một cặp khác `v=y·q` được tạo, với q nguyên tố và q≤spf[y]. Khi đó q phải là **ước nguyên tố nhỏ nhất** của v (không có ước nguyên tố nào nhỏ hơn q từ y), nên q=p, dẫn tới y=v/q=x. Vậy **không thể** có hai cặp khác nhau sinh cùng một v.

Điều này giải thích tính **tuyến tính**, vì mỗi composite được gán SPF đúng một lần, mỗi prime được phát hiện một lần, và các vòng có điểm dừng sớm. Cách đếm đúng là dựa trên **số phép tạo composite hữu ích**, không phải “vòng for lồng nhau luôn O(N²)”.

### So sánh hai sàng

| Tiêu chí | Sàng Eratosthenes ghi SPF | Sàng tuyến tính |
|---|---|---|
| Ý tưởng | Gán bội của từng nguyên tố, chỉ giữ lần đầu | Tạo mỗi composite theo cặp x,p duy nhất |
| Bất biến then chốt | Nguyên tố nhỏ hơn gán trước | Chỉ ghép p≤spf[x] |
| Thời gian | **O(N log log N)** | **O(N)** |
| Bộ nhớ SPF | O(N) | O(N) |
| Danh sách primes | Không bắt buộc, có thể bổ sung | Cần cho vòng lặp |
| Số lần xem composite | Có thể nhiều lần qua các bội | Một lần gán hữu ích cho mỗi composite |
| Mức dễ kiểm chứng | Dễ | Trung bình; cần hiểu giới hạn p |
| Thực tế | Có thể rất cạnh tranh vì cache và vòng gọn | Tốt cho tiền xử lý lớn và hàm số học tuyến tính |

**O(N) không có nghĩa linear sieve luôn nhanh hơn trong mọi môi trường.** Chi phí HashMap/ArrayList không liên quan trong bản mảng nguyên thủy, nhưng danh sách primes dạng `ArrayList<Integer>` có overhead boxing trong Java. Bản mẫu ưu tiên dễ học; tối ưu hiệu năng có thể dùng mảng `int[] primes` và chỉ số độ dài.

## 6. Phân tích thừa số nhanh bằng SPF

Sau khi đã xây bảng `spf` cho 1..N, để phân tích x (1≤x≤N):

~~~text
factorize(x):
    if x == 1: return empty list

    factors = []
    while x > 1:
        p = spf[x]
        exponent = 0
        do:
            x = x / p
            exponent++
        while x > 1 and x % p == 0

        factors.add((p, exponent))

    return factors
~~~

**Không** gọi lại sieve sau mỗi lần truy vấn. Ta chỉ lấy `spf[x]` của các giá trị x giảm dần.

Ví dụ x=84:

~~~text
x=84, spf=2 -> x=42, exponent(2)=1
x=42 chia tiếp 2 -> x=21, exponent(2)=2
x=21, spf=3 -> x=7, exponent(3)=1
x=7,  spf=7 -> x=1, exponent(7)=1

Kết quả: 84 = 2^2 * 3 * 7
~~~

### Vì sao số bước O(log x)?

Mỗi lần chia x cho một số nguyên tố p≥2, x giảm **ít nhất một nửa**. Do đó số phép chia liên tiếp không vượt `⌊log₂x⌋` (đối với x≥2, tính hằng số hợp lý). Kiểm tra nhóm cùng nguyên tố và tạo danh sách cặp cũng chỉ tương ứng với số lần chia hoặc số lượng nguyên tố phân biệt.

Vì vậy:

- **Thời gian factorize(x): O(log x)** trong cận xấu nhất.
- **Bộ nhớ output:** O(k) cặp (p,e), với k là số nguyên tố phân biệt, `k≤log₂x`.
- Không cần lưu lại tất cả các factorization cho 1..N dưới dạng hàng triệu List riêng; mảng spf đã mã hóa đủ thông tin để tái tạo chúng khi có truy vấn.

### Vì sao các p được xuất theo thứ tự tăng?

spf[x] luôn là ước nguyên tố nhỏ nhất của phần x còn lại. Sau khi loại hết p, phần x mới không còn chia hết p và không có ước nguyên tố <p trong x trước đó. Vì vậy các p xuất ra theo **thứ tự tăng**, thuận tiện để hiển thị `2^a·3^b·...` và sinh các ước.

### Đừng nhầm “số lần chia” với số lần thử chia

Trial division có thể **thử nhiều d không chia hết**; SPF chỉ truy xuất trực tiếp nguyên tố tiếp theo. Cận O(log x) là cho **chia và lấy mảng sau tiền xử lý**, không phải cho toàn bộ quá trình **xây SPF từ đầu**.

## 7. Các hàm số học được suy từ phân tích thừa số

Viết:

**`n=p₁^{a₁}·p₂^{a₂}·...·p_k^{a_k}`**, với p_i phân biệt và a_i≥1.

Từ đúng k cặp (p,a), ta suy ra nhiều đại lượng mà không phải liệt kê toàn bộ ước.

### 7.1. Số ước dương τ(n)

Mỗi ước dương của n có dạng `p₁^{b₁}...p_k^{b_k}`, với `0≤b_i≤a_i`. Mỗi b_i có a_i+1 lựa chọn độc lập, nên:

**`τ(n)=∏_{i=1}^k(a_i+1)`.**

Ví dụ `84=2²·3·7` ⇒ `τ(84)=3·2·2=12`.

Với n=1 là tích rỗng, `τ(1)=1`: 1 chỉ có một ước dương là 1.

### 7.2. Tổng ước dương σ(n)

Với mỗi prime power p^a, ta được đóng góp hình học:

**`1+p+p²+...+p^a`**.

Khi kết hợp các nguyên tố độc lập:

**`σ(n)=∏_{i=1}^k(1+p_i+...+p_i^{a_i})`.**

Ví dụ 84:

**`σ(84)=(1+2+4)(1+3)(1+7)=7·4·8=224`.**

Nếu dùng công thức `(p^{a+1}−1)/(p−1)`, cần cẩn thận tràn số khi tính lũy thừa. Mã Java cộng từng power bằng **long + Math.addExact/Math.multiplyExact**.

### 7.3. Hàm Euler φ(n)

**`φ(n)`** là số nguyên k trong 1..n có `gcd(k,n)=1`. Với n≥1:

**`φ(n)=n∏_{p|n}(1−1/p)`**,

sản phẩm chạy qua các **nguyên tố phân biệt** p chia n.

Cách tính chính xác bằng số nguyên:

~~~text
phi = n
for each DISTINCT prime factor p:
    phi = (phi / p) * (p - 1)
~~~

Không dùng phép nhân số thực `phi *= (1.0−1.0/p)` rồi ép kiểu vì có thể có sai số. Ví dụ 84 có các p=2,3,7:

**`φ(84)=84·(1−1/2)(1−1/3)(1−1/7)=24`.**

Với n=1, `φ(1)=1`, vì chỉ có k=1 và gcd(1,1)=1.

### 7.4. Hàm Möbius μ(n)

Định nghĩa cho n≥1:

- **`μ(1)=1`**.
- Nếu n chia hết cho bình phương của một số nguyên tố, **`μ(n)=0`**.
- Nếu n là tích của k nguyên tố **khác nhau**, **`μ(n)=(-1)^k`**.

Ví dụ:

- `30=2·3·5` có 3 nguyên tố phân biệt, không có bình phương ⇒ **μ(30)=−1**.
- `84=2²·3·7` có thừa số 2² ⇒ **μ(84)=0**.
- `97` nguyên tố ⇒ **μ(97)=−1**.
- `μ(1)=1`.

Möbius dùng trong **Möbius inversion**, một số bài đếm cặp nguyên tố cùng nhau, cộng trừ theo ước, nhưng không nên áp dụng công thức đảo Möbius khi chưa hiểu quan hệ hàm mục tiêu.

### 7.5. ω(n) và Ω(n) — hai kiểu “số thừa số nguyên tố”

Đây là một cặp ký hiệu dễ nhầm:

- **`ω(n)` (omega thường):** số **nguyên tố phân biệt** chia n.
- **`Ω(n)` (Omega hoa):** số thừa số nguyên tố **tính cả số lần lặp**, tức tổng các số mũ.

Với `84=2²·3·7`:

**`ω(84)=3`**, **`Ω(84)=2+1+1=4`**.

Với số nguyên tố 97, cả hai đều 1. Với 1, cả hai bằng 0.

Đối với n>1, nếu `ω(n)=Ω(n)` thì n **square-free** (không có thừa số nguyên tố xuất hiện với số mũ≥2); cùng điều kiện ấy thì `μ(n)` bằng ±1.

### 7.6. Tất cả các hàm trên dùng SPF ra sao?

Chạy `factorize(n)` để lấy mỗi cặp (p,e) đúng một lần. Trong cùng vòng:

- Nhân `τ` với (e+1).
- Nhân `σ` với tổng hình học của p tới e.
- Sửa `φ` bằng `φ/p·(p−1)`.
- Nếu e≥2, đặt `μ=0`; nếu không, đổi dấu μ.
- Tăng `ω` một lần mỗi cặp.
- Tăng `Ω` thêm e.

Nếu chỉ có một vài truy vấn, việc **tính các hàm trên khi cần** sẽ tiết kiệm RAM hơn cấp phát thêm nhiều bảng dài N+1.

## 8. Liệt kê tất cả các ước từ prime powers

Khi cần **danh sách các ước dương** của n, từ danh sách cặp `(p,e)`, khởi tạo:

**`divisors=[1]`.**

Với mỗi prime p có số mũ e:

1. Ghi lại `oldSize=divisors.size()` trước khi thêm các ước mới.
2. Với a từ 1..e:
   - Tính `power=p^a`.
   - Với mỗi phần tử ở **oldSize vị trí cũ**, thêm `divisors[j]·power`.
3. Tiếp tục prime tiếp theo.

**Chỉ nhân các ước có từ trước khi xử lý p**, không lấy cả những ước vừa sinh ra trong cùng lượt p để nhân tiếp, nếu không một prime power có thể bị dùng quá số mũ cho phép và tạo trùng.

Với 84=2²·3·7:

~~~text
Start:           [1]
After p=2,e=2:   [1, 2, 4]
After p=3,e=1:   [1, 2, 4, 3, 6, 12]
After p=7,e=1:   [1, 2, 4, 3, 6, 12,
                    7, 14, 28, 21, 42, 84]

Sort ascending:
[1, 2, 3, 4, 6, 7, 12, 14, 21, 28, 42, 84]
~~~

Danh sách có đúng **τ(n)** phần tử, và mỗi ước xuất hiện đúng một lần do tính duy nhất của phân tích nguyên tố. Trước sắp xếp, công việc sinh tương ứng số ước. Nếu yêu cầu **thứ tự tăng**, cần sắp xếp thêm, chi phí **O(τ(n) log τ(n))**.

**Không gọi việc liệt kê ước là O(log n)**: kết quả có thể chứa nhiều số. SPF chỉ cho phép lấy thừa số nguyên tố nhanh, còn xuất đủ tất cả ước phải tốn **Ω(τ(n))** thời gian và bộ nhớ output.

### Các câu hỏi về ước không cần enumerate

Nếu chỉ hỏi “n có bao nhiêu ước?”, dùng τ(n) từ số mũ, không cần list. Nếu hỏi “tổng các ước?”, dùng σ(n), không cần list. Khi tính tổng ước nguyên tố hoặc tổng ước thực sự, cần xác định hàm mục tiêu; **σ(n)−n** là tổng **ước dương thực sự** (loại chính n), nhưng không áp dụng tùy tiện cho n=0.

## 9. Tính trước φ, τ, μ, ω, Ω cho mọi n bằng SPF

Khi Q truy vấn có thể hỏi nhiều hàm số học tại mọi x≤N, ta có thể dùng `spf` để xây thêm các bảng giá trị trong **O(N)** thời gian. Đây là một **mức tiền xử lý bổ sung**, tăng bộ nhớ nhưng mỗi truy vấn trở thành O(1).

Đặt **`p=spf[n]`** và **`m=n/p`** với n≥2. Ta đã tính xong các bảng tại m<n khi duyệt n tăng.

### Trường hợp p còn chia m: m%p==0

Khi `m%p==0`, n có một lần p nhiều hơn m và p **đã có** trong m.

- **`φ[n]=φ[m]·p`**.
- **`μ[n]=0`** (n chứa p²).
- **`ω[n]=ω[m]`** (số prime phân biệt không tăng).
- **`Ω[n]=Ω[m]+1`**.

Nếu `exp[n]` là **số mũ của spf[n] trong n**, thì:

**`exp[n]=exp[m]+1`.**

Số ước:

**`τ[n]=τ[m]/(exp[m]+1)·(exp[m]+2)`.**

Lý do: m có đóng góp (exp[m]+1) lựa chọn số mũ của p, còn n tăng số lựa chọn thành (exp[m]+2). Trừ nhân tử cũ rồi nhân nhân tử mới; phép chia cho (exp[m]+1) **chia hết chính xác** trước khi nhân.

### Trường hợp p không chia m: m%p!=0

Khi `m%p!=0`, p là một nguyên tố **mới** so với m:

- **`φ[n]=φ[m]·(p−1)`**.
- **`μ[n]=−μ[m]`**.
- **`ω[n]=ω[m]+1`**.
- **`Ω[n]=Ω[m]+1`**.
- **`exp[n]=1`**.
- **`τ[n]=2·τ[m]`**.

Cơ sở:

~~~text
phi[1] = 1
tau[1] = 1
mu[1] = 1
omega[1] = 0
Omega[1] = 0
exp[1] = 0
~~~

### Pseudocode

~~~text
for n = 2 .. N:
    p = spf[n]
    m = n / p

    if m % p == 0:
        phi[n] = phi[m] * p
        mu[n] = 0
        omega[n] = omega[m]
        Omega[n] = Omega[m] + 1
        exp[n] = exp[m] + 1
        tau[n] = (tau[m] / (exp[m] + 1)) * (exp[m] + 2)
    else:
        phi[n] = phi[m] * (p - 1)
        mu[n] = -mu[m]
        omega[n] = omega[m] + 1
        Omega[n] = Omega[m] + 1
        exp[n] = 1
        tau[n] = 2 * tau[m]
~~~

Do mỗi n chỉ xem một p=spf[n] và số hằng phép tính trên các giá trị m<n đã có, toàn bộ bước dựng các bảng là **O(N)**.

**Cảnh báo:** nếu chỉ cần truy vấn ít lần, không phải lúc nào cũng đáng lưu thêm 5–6 mảng kích thước N+1. Có thể tính φ/τ/μ/ω/Ω từ factorize(n) trong O(log n) mà ít RAM hơn.

## 10. Cách chọn giới hạn N và dự trù bộ nhớ

Cần chọn **N là giới hạn lớn nhất của truy vấn sẽ dùng SPF**. Không dùng N nhỏ hơn rồi truy cập `spf[x]` với x>N; Java có thể ném lỗi ngoài mảng, hoặc code tự viết có thể trả kết quả vô nghĩa.

### Ví dụ bộ nhớ

Một mảng Java `int[N+1]` cần khoảng:

**`4·(N+1) byte`** cho dữ liệu nguyên thủy, chưa tính header/object alignment.

- N=1.000.000: khoảng **4 MB** dữ liệu.
- N=10.000.000: khoảng **40 MB** dữ liệu.
- N=100.000.000: khoảng **400 MB** dữ liệu.

Thêm các bảng `phi,tau,mu,exp,omega,Omega`, danh sách primes, overhead đối tượng Java và heap reserve có thể khiến bộ nhớ tăng nhiều lần. Đối với N=10 triệu, **nhiều mảng int** có thể vượt giới hạn bộ nhớ của đề dù riêng một mảng spf còn vừa.

### Dự trù thời gian

- Build SPF một lần.
- Q truy vấn factorization: thời gian tổng `O(Σ log x_i)`.
- Q truy vấn isPrime có SPF: **O(Q)**.
- Nếu dựng thêm phi/tau/μ tables: O(N) lần nữa, mỗi truy vấn những hàm này O(1).
- Nếu liệt kê ước cho từng truy vấn: tổng còn phụ thuộc **số phần tử output**.

Không thể nói “chạy O(log n) cho cả bài” nếu vẫn phải đọc N dữ liệu đầu vào hoặc xây bảng độ dài N.

### Khi N quá lớn hoặc không biết trước

- Nếu chỉ có **ít truy vấn**, trial division hoặc sàng các nguyên tố nhỏ tới √maxQuery có thể thực dụng hơn.
- Nếu maxQuery lớn nhưng chỉ cần **primes trong một đoạn [L,R]**, hãy xét **segmented sieve**, tránh mảng SPF đến tận R.
- Nếu cần **phân tích những số 64-bit rất lớn**, SPF toàn miền 2^63 không thể cấp phát; có thể dùng trial division bằng primes nhỏ, kiểm tra nguyên tố và các thuật toán phân tích như **Pollard–Rho** với những điều kiện triển khai phù hợp.
- Nếu các truy vấn trộn cả số trong và ngoài miền tiền xử lý, API phải có **một chiến lược rõ**: hoặc từ chối x>N, hoặc gọi một thuật toán khác được thiết kế riêng. Không truy cập mảng vượt miền.

SPF là công cụ đúng với **miền hữu hạn có thể cấp phát**, không phải một oracle phân tích số nguyên bất kỳ.

## 11. Java 17+ hoàn chỉnh: hai sàng và các truy vấn số học

Chương trình sau có thể lưu và chạy độc lập. Nó cung cấp:

1. `SpfIndex` xây bảng bằng **linear sieve O(N)** và lưu primes.
2. `classicSpf` xây bảng bằng biến thể **Eratosthenes O(N log log N)** để đối chiếu.
3. `factorize(x)` trả List các cặp (prime, exponent).
4. `isPrime(x)`, `smallestPrimeFactor(x)`.
5. `totient(x)`, `divisorCount(x)`, `divisorSum(x)`, `mobius(x)`, `distinctPrimeCount(x)`, `totalPrimeFactors(x)`.
6. `divisors(x)` trả các ước dương **đã sắp tăng**.
7. `ArithmeticTables` tính trước φ, τ, μ, ω, Ω bằng truy hồi tại mục 9.

**Hợp đồng:**

- `limit≥1` và không bằng `Integer.MAX_VALUE`, để `limit+1` không tràn int. Dù vậy giới hạn RAM thực tế nhỏ hơn rất nhiều.
- Các phương thức truy vấn chỉ nhận `x∈[1,limit]`; số khác ném `IllegalArgumentException`.
- Đặt `spf[1]=1` như một **sentinel**, không coi 1 là nguyên tố.
- `factorize(1)` trả danh sách rỗng, nhưng khi in biểu diễn số 1 ta viết `"1"`.
- `divisors(1)=[1]`, φ(1)=1, τ(1)=1, σ(1)=1, μ(1)=1, ω(1)=Ω(1)=0.
- Mã dùng `Math.addExact/Math.multiplyExact` cho tổng ước và các phép nhân tổng quát cần bảo vệ; nếu vượt long, ném `ArithmeticException` thay vì wrap âm thầm.
- Cấu trúc dữ liệu `record PrimePower` thuộc Java 17. Cần dùng JDK 17 trở lên.

Lưu thành **`SmallestPrimeFactorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class SmallestPrimeFactorDemo {
    private record PrimePower(int prime, int exponent) {}

    private static final class SpfIndex {
        final int limit;
        final int[] spf;
        final List<Integer> primes = new ArrayList<>();

        SpfIndex(int limit) {
            if (limit < 1 || limit == Integer.MAX_VALUE) {
                throw new IllegalArgumentException(
                        "SPF limit must be in [1, Integer.MAX_VALUE)");
            }
            this.limit = limit;
            this.spf = new int[limit + 1];
            spf[1] = 1; // 1 is NOT prime.

            for (int x = 2; x <= limit; x++) {
                if (spf[x] == 0) {
                    spf[x] = x; // x is a new prime.
                    primes.add(x);
                }

                for (int p : primes) {
                    // Each composite x*p is marked exactly once.
                    // Check division BEFORE multiplication.
                    if (p > spf[x] || x > limit / p) {
                        break;
                    }
                    spf[x * p] = p;
                }
            }
        }

        private void requireNumber(int x) {
            if (x < 1 || x > limit) {
                throw new IllegalArgumentException(
                        "Number outside SPF domain [1, limit]");
            }
        }

        int smallestPrimeFactor(int x) {
            requireNumber(x);
            return spf[x];
        }

        boolean isPrime(int x) {
            requireNumber(x);
            return x >= 2 && spf[x] == x;
        }

        List<Integer> primesUpTo(int boundary) {
            requireNumber(boundary);
            List<Integer> result = new ArrayList<>();
            for (int p : primes) {
                if (p > boundary) {
                    break;
                }
                result.add(p);
            }
            return List.copyOf(result);
        }

        List<PrimePower> factorize(int x) {
            requireNumber(x);
            List<PrimePower> factors = new ArrayList<>();

            while (x > 1) {
                int p = spf[x];
                int exponent = 0;
                do {
                    x /= p;
                    exponent++;
                } while (x > 1 && x % p == 0);

                factors.add(new PrimePower(p, exponent));
            }
            return List.copyOf(factors);
        }

        int totient(int x) {
            requireNumber(x);
            int result = x;

            for (PrimePower f : factorize(x)) {
                int p = f.prime();
                result = (result / p) * (p - 1);
            }
            return result;
        }

        int divisorCount(int x) {
            int result = 1;
            for (PrimePower f : factorize(x)) {
                result = Math.multiplyExact(
                        result, f.exponent() + 1);
            }
            return result;
        }

        int distinctPrimeCount(int x) {
            return factorize(x).size();
        }

        int totalPrimeFactors(int x) {
            int result = 0;
            for (PrimePower f : factorize(x)) {
                result += f.exponent();
            }
            return result;
        }

        int mobius(int x) {
            int result = 1;
            for (PrimePower f : factorize(x)) {
                if (f.exponent() >= 2) {
                    return 0;
                }
                result = -result;
            }
            return result;
        }

        long divisorSum(int x) {
            long result = 1L;

            for (PrimePower f : factorize(x)) {
                long term = 1L;
                long power = 1L;
                for (int e = 0; e < f.exponent(); e++) {
                    power = Math.multiplyExact(
                            power, (long) f.prime());
                    term = Math.addExact(term, power);
                }
                result = Math.multiplyExact(result, term);
            }
            return result;
        }

        List<Integer> divisors(int x) {
            List<Integer> result = new ArrayList<>();
            result.add(1);

            for (PrimePower f : factorize(x)) {
                int oldSize = result.size();
                long power = 1L;

                for (int e = 1; e <= f.exponent(); e++) {
                    power = Math.multiplyExact(
                            power, (long) f.prime());
                    for (int i = 0; i < oldSize; i++) {
                        long value = Math.multiplyExact(
                                (long) result.get(i), power);
                        result.add(Math.toIntExact(value));
                    }
                }
            }
            Collections.sort(result);
            return List.copyOf(result);
        }
    }

    // Independent alternative: mark prime multiples from p*p.
    static int[] classicSpf(int limit) {
        if (limit < 1 || limit == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid limit");
        }

        int[] spf = new int[limit + 1];
        spf[1] = 1;

        for (int p = 2; p <= limit; p++) {
            if (spf[p] != 0) {
                continue;
            }

            spf[p] = p;
            if (p > limit / p) {
                continue; // Avoid p*p overflow.
            }

            for (long j = (long) p * p;
                    j <= limit; j += p) {
                int at = (int) j;
                if (spf[at] == 0) {
                    spf[at] = p;
                }
            }
        }
        return spf;
    }

    // Optional O(N) arithmetic-function tables after SPF.
    private static final class ArithmeticTables {
        final int[] phi;
        final int[] tau;
        final int[] mu;
        final int[] exponent;
        final int[] omega;
        final int[] bigOmega;

        ArithmeticTables(SpfIndex index) {
            int n = index.limit;
            phi = new int[n + 1];
            tau = new int[n + 1];
            mu = new int[n + 1];
            exponent = new int[n + 1];
            omega = new int[n + 1];
            bigOmega = new int[n + 1];

            phi[1] = 1;
            tau[1] = 1;
            mu[1] = 1;

            for (int x = 2; x <= n; x++) {
                int p = index.spf[x];
                int m = x / p;

                if (m % p == 0) {
                    // The same prime p already occurs in m.
                    phi[x] = Math.multiplyExact(phi[m], p);
                    exponent[x] = exponent[m] + 1;
                    tau[x] = Math.multiplyExact(
                            tau[m] / (exponent[m] + 1),
                            exponent[m] + 2);
                    mu[x] = 0;
                    omega[x] = omega[m];
                    bigOmega[x] = bigOmega[m] + 1;
                } else {
                    // p is a newly introduced distinct prime.
                    phi[x] = Math.multiplyExact(
                            phi[m], p - 1);
                    exponent[x] = 1;
                    tau[x] = Math.multiplyExact(tau[m], 2);
                    mu[x] = -mu[m];
                    omega[x] = omega[m] + 1;
                    bigOmega[x] = bigOmega[m] + 1;
                }
            }
        }
    }

    private static String formatFactors(
            List<PrimePower> factors) {
        if (factors.isEmpty()) {
            return "1";
        }

        StringBuilder result = new StringBuilder();
        for (PrimePower f : factors) {
            if (result.length() > 0) {
                result.append(" * ");
            }
            result.append(f.prime());
            if (f.exponent() > 1) {
                result.append("^").append(f.exponent());
            }
        }
        return result.toString();
    }

    private static void show(SpfIndex index, int n) {
        System.out.println(
                "n=" + n
                + ": factors=" + formatFactors(index.factorize(n))
                + ", phi=" + index.totient(n)
                + ", tau=" + index.divisorCount(n)
                + ", mu=" + index.mobius(n)
                + ", omega=" + index.distinctPrimeCount(n)
                + ", Omega=" + index.totalPrimeFactors(n)
                + ", sigma=" + index.divisorSum(n));
    }

    public static void main(String[] args) {
        SpfIndex index = new SpfIndex(100);
        int[] classic = classicSpf(100);

        System.out.println(
                "Linear sieve matches classic sieve: "
                + Arrays.equals(index.spf, classic));
        System.out.println(
                "Primes <= 30: " + index.primesUpTo(30));
        System.out.println(
                "SPF[1]=" + index.smallestPrimeFactor(1)
                + ", SPF[49]=" + index.smallestPrimeFactor(49)
                + ", SPF[84]=" + index.smallestPrimeFactor(84)
                + ", SPF[97]=" + index.smallestPrimeFactor(97));

        for (int n : new int[] {1, 30, 49, 60, 84, 97}) {
            show(index, n);
        }

        System.out.println(
                "Divisors(84): " + index.divisors(84));

        ArithmeticTables tables = new ArithmeticTables(index);
        System.out.println(
                "Tables n=84: phi=" + tables.phi[84]
                + ", tau=" + tables.tau[84]
                + ", mu=" + tables.mu[84]
                + ", omega=" + tables.omega[84]
                + ", Omega=" + tables.bigOmega[84]);

        System.out.println(
                "isPrime(1)=" + index.isPrime(1)
                + ", isPrime(97)=" + index.isPrime(97)
                + ", isPrime(100)=" + index.isPrime(100));
    }
}
~~~

Biên dịch và chạy trên **Java 17+**:

~~~bash
javac -encoding UTF-8 SmallestPrimeFactorDemo.java
java SmallestPrimeFactorDemo
~~~

**Stdout chính xác** của chương trình:

~~~text
Linear sieve matches classic sieve: true
Primes <= 30: [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
SPF[1]=1, SPF[49]=7, SPF[84]=2, SPF[97]=97
n=1: factors=1, phi=1, tau=1, mu=1, omega=0, Omega=0, sigma=1
n=30: factors=2 * 3 * 5, phi=8, tau=8, mu=-1, omega=3, Omega=3, sigma=72
n=49: factors=7^2, phi=42, tau=3, mu=0, omega=1, Omega=2, sigma=57
n=60: factors=2^2 * 3 * 5, phi=16, tau=12, mu=0, omega=3, Omega=4, sigma=168
n=84: factors=2^2 * 3 * 7, phi=24, tau=12, mu=0, omega=3, Omega=4, sigma=224
n=97: factors=97, phi=96, tau=2, mu=-1, omega=1, Omega=1, sigma=98
Divisors(84): [1, 2, 3, 4, 6, 7, 12, 14, 21, 28, 42, 84]
Tables n=84: phi=24, tau=12, mu=0, omega=3, Omega=4
isPrime(1)=false, isPrime(97)=true, isPrime(100)=false
~~~

### Cách đọc các kết quả

**Dòng 1:** hai thuật toán sàng được cài **độc lập** trả ra cùng mảng SPF trên miền 1..100. Đây là một kiểm thử chéo hữu ích, nhưng một ví dụ N=100 không đủ thay thế kiểm thử ngẫu nhiên và chứng minh toán học.

**Primes ≤30:** được lấy trực tiếp từ danh sách primes của linear sieve. Không có 1, vì 1 không nguyên tố.

**SPF[49]=7:** 49=7², nên ước nguyên tố nhỏ nhất là 7. **SPF[97]=97:** nguyên tố có SPF bằng chính nó. **SPF[84]=2:** mọi số chẵn ≥2 có ước nguyên tố nhỏ nhất bằng 2.

**n=1:** biểu diễn phân tích là "1" theo quy ước hiển thị, dù danh sách các cặp PrimePower **rỗng**. Điều này làm các phép tính tích rỗng cho τ, σ, μ vẫn đúng bằng 1.

**n=30:** là số square-free gồm ba nguyên tố khác nhau, nên μ=−1, ω=Ω=3, φ=8, τ=8 và tổng ước σ=72.

**n=49:** có bình phương nguyên tố 7² nên μ=0; ba ước [1,7,49] cho τ=3 và σ=57.

**n=60:** 60=2²·3·5, có 12 ước, φ=16 và σ=168. Ký hiệu omega thường là 3, Omega hoa là 4.

**n=84:** 84=2²·3·7; φ=24, τ=12, σ=224, μ=0, ω=3, Ω=4. Danh sách ước in chính xác 12 số đã sắp.

**n=97:** là nguyên tố, có đúng hai ước [1,97], φ(97)=96, μ(97)=−1, σ(97)=98.

**Tables n=84:** kết quả tiền xử lý toàn miền bằng truy hồi khớp với cách tính từ factorize(84). Nếu nhiều truy vấn φ/τ/μ, bảng có thể trả ngay O(1).

**isPrime:** hàm kiểm tra có điều kiện `n≥2` nên trả false với n=1, true với 97 và false với 100.

## 12. Những chỗ Java dễ tràn số hoặc hết bộ nhớ

### Vòng sàng và phép nhân p·x

Trong linear sieve, viết:

~~~java
if (p > spf[x] || x > limit / p) {
    break;
}
spf[x * p] = p;
~~~

Điều kiện `x>limit/p` được tính **trước** `x*p`, nên tránh overflow khi tích vượt limit. Không viết:

~~~java
if (x * p > limit) {
    break;
}
~~~

khi x và p là int, vì phép nhân đã có thể overflow **trước khi so sánh**. Một tích tràn âm không thể dùng làm chỉ số mảng.

### Vòng từ p²

Trong classic sieve, dùng:

~~~java
if (p > limit / p) {
    continue;
}
for (long j = (long) p * p; j <= limit; j += p) {
    // ...
}
~~~

Như vậy phép nhân p² được nâng sang long và chỉ thực hiện khi p²≤limit. Tương tự, điều kiện vòng `i*i<=N` với i int phải được thay bằng `i<=N/i` để tránh nhân tràn.

### Kích thước mảng N+1

Khi limit=Integer.MAX_VALUE, biểu thức `limit+1` trên int tràn âm. Bản mã từ chối trường hợp này, nhưng đó **không phải** điều kiện đủ để bộ nhớ luôn an toàn: ví dụ một mảng int[1.000.000.001] vẫn có thể vượt RAM/heap. Phải dự trù số bytes và headroom; `OutOfMemoryError` cần được giải bằng **chọn thuật toán, phân vùng, cấu hình RAM hoặc giảm miền**, không phải chỉ bằng try/catch rồi tiếp tục thiếu dữ liệu.

### Cộng và nhân trên các hàm số học

- φ(n)≤n và τ(n)≤n cho n≥1, nên với n≤Integer.MAX_VALUE−1, kết quả cuối của các hàm này nằm trong int. Trong code, `Math.multiplyExact` giúp bảo vệ phép nhân nếu sửa công thức.
- σ(n) có thể **lớn hơn n**, dùng **long**; với các miền số lớn hơn int, bản thân σ có thể vượt long.
- Nếu thay `sum=(p^{a+1}−1)/(p−1)`, phép tính lũy thừa trung gian có thể tràn dù thương thật còn nhỏ.
- Không dùng `Math.pow(double,double)` rồi ép về long cho phân tích số nguyên chính xác ở miền lớn vì floating point có thể mất độ chính xác.
- Không dùng `Math.abs(Integer.MIN_VALUE)` khi muốn hỗ trợ số âm; phải đổi qua long hoặc xử lý trường hợp đặc biệt.

### Số âm và 0

Nếu cần phân tích số âm, định nghĩa `n=(-1)·|n|`; phân tích thừa số nguyên tố dương của |n| và quyết định dấu output riêng. Đối với 0, không có phân tích nguyên tố hữu hạn duy nhất. API code cố tình từ chối cả hai để không mơ hồ.

## 13. Các bất biến và chứng minh nhanh

### Bất biến linear sieve

Sau khi xử lý x theo thứ tự tăng, mọi số đã gán SPF có giá trị là một **nguyên tố chia hết số ấy**, và mỗi composite trong miền đã tạo được sẽ được gán qua **đúng một cặp (i,p)** hợp lệ với p≤spf[i].

Với composite v có p=spf[v], i=v/p, ta biết spf[i]≥p. Khi tới i, vòng primes có p, nên v được sinh. Điều kiện p≤spf[i] bảo đảm p không lớn hơn ước nguyên tố nhỏ nhất của i, nên p=spf[i·p]. Tính duy nhất đã được chứng minh ở mục 5. Do đó sau khi x chạy tới N, mọi composite đã có SPF chính xác; những số chưa đánh dấu khi được xét chính là primes.

### Bất biến factorization

Ở đầu mỗi lượt, tích các prime powers đã ghi **nhân với x còn lại** bằng số đầu vào ban đầu n. Khi lấy p=spf[x] và chia p đúng e lần:

**`x_old = p^e·x_new`**.

Do p là prime và x_new không còn chia hết p, cặp (p,e) là thành phần phân tích đúng. X giảm nghiêm ngặt khi x>1, nên vòng lặp kết thúc. Tới x=1, các cặp đã ghi cho tích đúng n; định lý phân tích nguyên tố duy nhất cho biết không thiếu hoặc thừa thừa số.

### Bất biến sinh ước

Sau khi xử lý những prime powers đầu tiên, danh sách chứa **tất cả** tích các lũy thừa `p_i^{b_i}` trong miền số mũ đã xử lý, mỗi tổ hợp một lần. Khi thêm một prime mới, giữ nguyên danh sách cũ cho b=0, rồi tạo mỗi tích cũ nhân `p^1,...,p^e` cho các b>0. Các tổ hợp số mũ khác nhau cho các số khác nhau nhờ phân tích nguyên tố duy nhất; do vậy không có ước trùng.

### Bất biến bảng φ,τ,μ

Khi tính n tăng, m=n/spf[n] luôn nhỏ hơn n nên các giá trị tại m đã tồn tại. Phân biệt m chia được p hay không là phân biệt **thêm một lần p cũ** và **thêm một prime mới**. Mỗi công thức ở mục 9 là hệ quả trực tiếp của tích các prime powers, nên quy nạp theo n cho thấy các bảng đúng trên toàn miền.

## 14. Kiểm thử độc lập thay vì chỉ tin một bản sàng

Hai cách sàng có thể cùng bị sai vì một giả định chung (ví dụ coi 1 là prime). Vì vậy bộ kiểm thử tốt nên có thêm **oracle trial division** và các bất biến số học khác bản chất.

### 14.1. So linear sieve với classic sieve

Với một N thử nghiệm vừa phải, so **toàn bộ** phần tử:

**`spfLinear[n]==spfClassic[n]`** cho mọi n∈[1,N].

Kiểm riêng:

- `spf[1]==1` theo convention.
- `spf[2]==2`.
- `spf[n]≤n`, chia hết n và là prime với mọi n≥2.
- Nếu `spf[n]==n` thì n là nguyên tố theo oracle khác.
- Với mọi composite, SPF phải nhỏ hơn n.

### 14.2. Oracle trial division

Với mỗi n≥2, thử các d từ 2 tới √n, tìm **ước dương đầu tiên**:

~~~text
trialSPF(n):
    for d = 2 .. floor(sqrt(n)):
        if n % d == 0:
            return d
    return n
~~~

Đây là một oracle độc lập với sàng cho dữ liệu nhỏ. Nếu d đầu tiên chia n, d bắt buộc là nguyên tố: nếu d hợp số thì nó có ước nhỏ hơn d, mâu thuẫn d là ước nhỏ nhất từ 2.

So `spf[n]` với oracle này trên các giá trị ngẫu nhiên, các bình phương nguyên tố, các hợp số có prime factor lớn, và số nguyên tố gần N.

### 14.3. Kiểm factorization

Với n nhỏ:

1. Chạy factorize(n) từ SPF.
2. Chạy trial division độc lập để tạo cặp (p,e).
3. So các cặp theo đúng thứ tự.
4. Nhân lại p^e bằng **long** và kiểm bằng n.
5. Kiểm mọi p là prime và các p tăng nghiêm ngặt.

Các trường hợp n=1, n=2, n=p^a, n=p·q và n chứa nhiều nguyên tố phân biệt là bắt buộc.

### 14.4. Kiểm φ và các hàm đếm

Với n≤một ngưỡng nhỏ, không cần dùng công thức prime powers để làm oracle:

- **φ(n)**: đếm trực tiếp những i∈[1,n] có `gcd(i,n)==1`.
- **τ(n)**: đếm trực tiếp những i∈[1,n] thỏa `n%i==0`.
- **σ(n)**: cộng trực tiếp những i ấy.
- **μ(n)**: kiểm phân tích bằng phép chia thử độc lập rồi áp dụng định nghĩa square-free.
- **ω(n),Ω(n)**: đếm theo danh sách prime factors của oracle trial division.

Với N thử nghiệm lớn hơn, có thể kiểm toàn bộ các bảng phi/tau/mu tính từ SPF **khớp** với cách factorize từng n; sau đó đối chiếu với oracle brute-force ở một số n nhỏ. Cách kiểm ba tầng này bắt lỗi công thức truy hồi lẫn bug sàng.

### 14.5. Các kiểm thử đã có trong mô hình bài

Một bộ kiểm thử tham chiếu độc lập có thể đặt N=120.000 và:

- So **từng phần tử** của linear SPF với classic SPF trên 1..120.000.
- So **15.000** số chọn ngẫu nhiên với phân tích thừa số trial division.
- So **2.200** số nhỏ với φ tính bằng GCD và τ/σ bằng duyệt trực tiếp mọi ước.
- So toàn bộ **120.000** giá trị φ, τ, μ, ω, Ω từ công thức bảng với kết quả suy từ prime powers.
- Kiểm kết quả cố định: 30,49,60,84,97 và n=1.

**Không chỉ chạy vài ví dụ số chẵn:** nhiều lỗi sẽ chỉ xuất hiện ở bình phương của một nguyên tố lớn, số n có nhiều thừa số, hoặc giới hạn N sát biên.

## 15. Các bài toán vận dụng

### 15.1. Đếm bao nhiêu số trong [1,N] có đúng k ước

Nếu đã có bảng τ[n], có thể duyệt 1..N một lần và tạo bảng tần suất:

~~~text
frequency[k] = count of n in [1,N] with tau[n] == k
~~~

Mỗi truy vấn theo k trả O(1) sau tiền xử lý O(N). Nếu chỉ có một k, có thể đếm trực tiếp từ bảng τ, không bắt buộc giữ frequency.

### 15.2. Số square-free trong đoạn

Một số n≥1 là square-free nếu không chia hết cho p² của bất kỳ nguyên tố nào. Với n>1:

**`μ(n)≠0 ⇔ n square-free`.**

Xây prefix count:

**`prefixSquareFree[i]=prefixSquareFree[i−1]+[μ(i)≠0]`**.

Truy vấn số lượng square-free trong [L,R] bằng:

**`prefixSquareFree[R]−prefixSquareFree[L−1]`**,

với 1≤L≤R≤N. Cần nhớ `μ(1)=1`, nên 1 được tính là square-free.

### 15.3. Số nguyên tố trong đoạn

Từ `isPrime[n]=(n≥2 && spf[n]==n)`, xây:

**`primePrefix[i]=primePrefix[i−1]+[isPrime(i)]`**.

Truy vấn số nguyên tố trong [L,R] là hiệu hai prefix sums. Đừng cộng 1 vào số nguyên tố.

### 15.4. Đếm số thừa số nguyên tố có lặp

Với `Ω(n)`, một bài yêu cầu “số lượng prime factors tính cả bội số” có thể trả ngay `Ω[n]`. Nếu đề chỉ hỏi “bao nhiêu prime khác nhau” thì phải dùng `ω[n]`. Ví dụ 84 là phép thử quan trọng: Ω=4, ω=3.

### 15.5. Phân tích nhiều số rồi ghép thành LCM/GCD

Nếu có nhiều số ≤N, phân tích từng số thành cặp (p,e). Với GCD, số mũ mỗi nguyên tố là **min** qua các số (thiếu nguyên tố nghĩa là mũ 0); với LCM là **max**. Với nhiều số và dữ liệu lớn, có thể dùng Euclid GCD trực tiếp nhanh hơn việc factorize, nên không ép sử dụng SPF cho mọi bài. Khi tính LCM bằng `a/gcd(a,b)*b`, vẫn phải kiểm tra overflow phần nhân.

### 15.6. Truy vấn nhiều lần trên cùng giới hạn

Nếu đề có nhiều test cases dùng cùng N, tạo bảng SPF **một lần bên ngoài vòng test**. Nếu các test có các giới hạn N khác nhau nhưng tất cả đã biết trước, có thể dùng `maxN` trong tất cả test; không nên liên tục cấp phát và xây lại sàng nếu tổng miền cho phép tiền xử lý chung.

## 16. Khi nào SPF là công cụ phù hợp?

| Tình huống | Lựa chọn gợi ý |
|---|---|
| Rất nhiều truy vấn factorization, mọi x≤N và N vừa RAM | Tiền xử lý SPF |
| N vừa RAM, cần φ/τ/μ/ω/Ω cho mọi n | SPF + bảng số học O(N) |
| Chỉ cần liệt kê primes ≤N | Sàng Eratosthenes với boolean/bitset có thể gọn hơn SPF |
| Q rất nhỏ, một x rất lớn | Trial division hoặc factorization chuyên biệt |
| Truy vấn nguyên tố của các số 64-bit lớn | Primality test thích hợp, không cấp SPF tới 2^63 |
| Tìm các prime trong đoạn [L,R] rất xa 0 | Segmented sieve |
| N lên hàng trăm triệu, heap hẹp | Đo RAM thực tế; cân nhắc cấu trúc lưu compact hoặc đổi bài toán |
| Chỉ cần các ước của vài số | Trial division và sinh ước từ prime factors |
| N≤1 | SPF[1] convention; không có prime; factorize(1) rỗng |
| Truy vấn có x>N | Từ chối rõ ràng hoặc dùng giải pháp khác |

**Lời nhắc:** SPF không phải một cấu trúc dữ liệu cho “mọi số tự nhiên” theo nghĩa vô hạn. Nó được xây trên **một miền đóng** và giá trị ngoài miền không có entry hợp lệ.

## 17. Những lỗi thường gặp

1. **Coi 1 là số nguyên tố:** sai dù `spf[1]=1` theo convention.
2. **Phân tích n=0 bằng vòng while n>1 hoặc chia spf[0]:** 0 không có prime factorization hữu hạn như n>0.
3. **Quên mảng cần N+1 phần tử:** chỉ số N là hợp lệ, mảng int[N] không chứa ô N.
4. **Dùng `p*p` bằng int khi N lớn:** có thể overflow trước khi so giới hạn.
5. **Dùng `x*p` bằng int trước kiểm biên trong linear sieve:** có thể âm và gây index sai.
6. **Bỏ điều kiện p≤spf[x] trong linear sieve:** composite có thể bị gán nhiều lần hoặc gán ước prime không nhỏ nhất.
7. **Ghi đè spf[j] ở classic sieve sau khi đã có giá trị:** mất thuộc tính nhỏ nhất.
8. **Đánh dấu classic sieve từ 2p thay vì p² mà không tính chi phí:** có thể vẫn đúng nếu giữ first-set, nhưng lặp bội thừa nhiều hơn và không dùng tối ưu chuẩn.
9. **Không ghi spf[p]=p cho prime p:** prime có thể vẫn bằng 0 sau sàng.
10. **Kết luận spf[x]==x với x=1 là prime:** phải thêm điều kiện x≥2.
11. **Cho rằng x là prime chỉ vì spf[x]==0 sau build:** bảng hoàn chỉnh phải có spf[x]≠0 với mọi x≥2.
12. **Dùng factorize(x) ngoài giới hạn N:** có thể truy cập ngoài mảng hoặc đọc 0.
13. **Không chia x sau khi lấy p:** while loop không tiến tới 1.
14. **Không nhóm các lần chia cùng p thành số mũ:** vẫn có prime factors nhưng khó tính τ, μ và σ.
15. **Chia một lần rồi chuyển prime ngay:** bỏ mất số mũ của p khi n có p².
16. **Coi thừa số 1 là một prime factor:** làm sai ω, Ω, μ và φ.
17. **Tính số ước là tổng (a_i+1):** phải nhân `∏(a_i+1)`.
18. **Tính σ chỉ bằng tổng các prime factors:** sigma là tổng **mọi ước dương**, có công thức tích cấp số nhân.
19. **Tính φ bằng phép nhân floating point rồi ép int:** có thể sai do làm tròn.
20. **Tính μ bằng số prime factors tính cả lặp rồi đổi dấu:** có p² phải trả 0.
21. **Nhầm ω với Ω:** với 84 là 3 và 4, không cùng giá trị.
22. **Quên n=1 trong φ,τ,σ,μ:** cả bốn là 1, còn ω=Ω=0.
23. **Khi sinh ước, dùng cả phần tử vừa thêm trong cùng lượt prime:** tạo lũy thừa lớn quá số mũ và trùng.
24. **Tưởng liệt kê τ(n) ước tốn O(log n):** output đã có τ(n) phần tử.
25. **Không sort khi đề cần ước tăng dần:** cách sinh từ powers không tự đảm bảo thứ tự.
26. **Dùng int cho sigma hoặc lũy thừa trung gian không kiểm tràn:** tổng ước có thể vượt n.
27. **Nhầm Big-O của linear sieve là O(N²) vì có hai vòng:** không tính điều kiện dừng và tính duy nhất mỗi composite.
28. **Gọi classic sieve O(N) mà không chứng minh:** biến thể sàng bội có cận O(N log log N).
29. **Suy thời gian xây tuyến tính từ O(N) bộ nhớ:** hai đại lượng khác nhau.
30. **Tiền xử lý N quá lớn chỉ cho một truy vấn:** có thể tốn thời gian/RAM không đáng.
31. **Giữ quá nhiều bảng O(N) không cần thiết:** phi/tau/mu/omega arrays đều chiếm RAM.
32. **Xây lại sieve cho từng test case:** lặp công việc tiền xử lý.
33. **Bỏ qua overflow của `N+1` khi N=Integer.MAX_VALUE:** tạo kích thước âm.
34. **Dùng Math.abs(Integer.MIN_VALUE) để hỗ trợ n âm:** vẫn âm vì overflow.
35. **Cho rằng segmented sieve trả sẵn SPF mọi số tới R:** nó giải bài prime range theo mô hình khác.
36. **Không kiểm số nguyên tố bình phương:** 49,121,169 thường bắt lỗi đánh dấu từ p².
37. **Chỉ test số chẵn:** dễ bỏ bug với ước nguyên tố nhỏ nhất là 3,5,7...
38. **Không test số nguyên tố gần N:** dễ quên gán spf[p]=p.
39. **So hai sàng nhưng không có oracle độc lập:** hai bản có thể cùng sai convention hoặc điều kiện biên.
40. **Coi mọi bài toán số học là bài SPF:** GCD, modular exponentiation, primality cho số lớn có lựa chọn tốt hơn.

## 18. Bài tập vận dụng

**Bài 1 — Viết classic sieve.** Xây bảng spf[1..100] bằng sàng bội bắt đầu tại p². In spf của 1,2,49,60,97,100 và so với sàng tuyến tính.

**Bài 2 — Chứng minh tuyến tính.** Với composite n, đặt p=spf[n], x=n/p. Chứng minh p≤spf[x], rồi giải thích vì sao cặp (x,p) là cặp duy nhất tạo n trong linear sieve.

**Bài 3 — Đếm ước nhiều truy vấn.** Cho N≤10⁶ và Q≤10⁵. Xây SPF một lần; với mỗi query n, factorize rồi trả τ(n). So với cách thử hết d≤√n.

**Bài 4 — Square-free prefix.** Dùng μ[n] để tạo prefix count và trả số lượng square-free trong [L,R]. Chú ý 1 được tính là square-free, 0 không nằm trong miền.

**Bài 5 — Tổng ước thực sự.** Viết hàm `properDivisorSum(n)=σ(n)−n` cho n≥1. Thử n=6 (1+2+3=6) và n=28 (1+2+4+7+14=28), rồi giải thích perfect numbers.

**Bài 6 — Phân tích 360.** Kiểm `360=2³·3²·5`, suy `τ(360)=4·3·2=24`, φ(360)=96, μ(360)=0, ω(360)=3, Ω(360)=6. Dùng hai sàng độc lập để kiểm spf(360)=2.

**Bài 7 — Lưu primes tối ưu.** Thay `List<Integer> primes` dạng boxed bằng `int[]` với biến `primeCount`. Đo build time và peak memory trên N=10⁶ và 10⁷; nêu lý do các số đo thực nghiệm không luôn giống tỷ lệ Big-O.

**Bài 8 — Tần suất số lượng ước.** Dùng bảng τ để đếm có bao nhiêu n≤N có đúng k ước, và tính prefix counts theo k nếu có nhiều truy vấn.

**Bài 9 — Tìm tập các prime divisors.** Với một số n, trả các ước nguyên tố **không lặp** tăng dần. So kết quả với factorize(n) và mô tả khác biệt với danh sách có multiplicity.

**Bài 10 — Phạm vi lớn.** Bài yêu cầu phân tích vài số 64-bit tới 10¹⁸. Giải thích tại sao cấp spf đến 10¹⁸ không khả thi và đề xuất một quy trình có kiểm tra nguyên tố và factorization phù hợp hơn, không tự khẳng định trial division đến √n luôn đủ nhanh.

## 19. Checklist trước khi nộp

- Đã chọn N từ **giới hạn truy vấn thật** và dự trù RAM cho mảng `N+1`?
- Với `n≥2`, spf[n] có đúng là **nguyên tố nhỏ nhất chia n**?
- Đã quy ước rõ `spf[1]=1` nhưng **isPrime(1)=false**?
- Đã từ chối factorize(0), số âm hoặc x>N nếu API không hỗ trợ?
- Classic sieve có duyệt primes theo thứ tự tăng, đánh dấu từ p² và chỉ gán spf[j] nếu còn 0?
- Linear sieve có điều kiện **`p≤spf[x]`** và **`x≤N/p`** trước phép nhân?
- Đã kiểm với các bình phương nguyên tố như 4,9,25,49,121?
- Đã thử số nguyên tố lớn gần N để đảm bảo spf[p]=p?
- factorize có chia hết tất cả số mũ p rồi mới chuyển sang prime kế?
- Với n=1, factor list rỗng nhưng φ,τ,σ,μ=1 và ω,Ω=0?
- Đã phân biệt số nguyên tố **khác nhau** ω và số prime factors **có lặp** Ω?
- τ có dùng tích (e+1), σ có dùng tích các tổng hình học?
- φ có tính bằng số nguyên và mỗi prime phân biệt chỉ xử lý một lần?
- μ có trả 0 nếu có prime factor có exponent≥2?
- Khi sinh ước, có cố định oldSize trước khi nhân các lũy thừa prime mới?
- Nếu đề cần ước tăng dần, đã sort và tính chi phí output?
- Khi tiền xử lý φ/τ/μ, có dùng m=n/spf[n] và hai nhánh m%p đúng?
- Đã kiểm soát `p*p`, `x*p`, `N+1` và tổng ước có thể overflow?
- Đã đánh giá liệu Q có đủ lớn để trả giá xây SPF O(N) không?
- Nếu N quá lớn, đã cân nhắc trial division, segmented sieve hay factorization khác?
- Đã so bảng với **một oracle trial division độc lập** và kiểm φ bằng GCD khi n nhỏ?
- Đã kiểm các ca 1,2, số prime, số square-free, prime powers và composite có nhiều prime khác nhau?

**Kết luận:** tiền xử lý **ước nguyên tố nhỏ nhất SPF** biến việc phân tích nhiều số trong một miền hữu hạn thành những phép **truy xuất mảng và chia liên tiếp**, thay cho lặp trial division ở từng query. Sàng kiểu Eratosthenes xây SPF trong O(N log log N); sàng tuyến tính dùng quy tắc p≤spf[x] để tạo mỗi composite đúng một lần và đạt O(N) thời gian. Từ phân tích `n=∏p_i^{a_i}` có thể suy nhanh τ, σ, φ, μ, ω, Ω và sinh mọi ước; nếu cần nhiều truy vấn, các hàm ấy cũng có thể được tiền xử lý O(N) bằng truy hồi. Điều quan trọng khi áp dụng là giữ đúng các bất biến nguyên tố, xử lý 0/1 và miền truy vấn, tránh tràn khi nhân/chỉ số, tính cả chi phí kết quả đầu ra và lựa chọn N đủ nhỏ để lưu trữ hiệu quả.