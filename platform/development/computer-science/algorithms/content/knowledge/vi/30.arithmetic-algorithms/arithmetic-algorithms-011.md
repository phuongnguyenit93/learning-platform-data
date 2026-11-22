# Kiểm tra nguyên tố Miller–Rabin và lựa chọn cơ sở

**Miller–Rabin** là thuật toán kiểm tra tính nguyên tố rất nhanh cho số nguyên lớn bằng **lũy thừa mô-đun và các phép bình phương liên tiếp**. Nó không thử chia cho tất cả ước đến căn bậc hai; thay vào đó, nó tìm **một cơ sở a chứng minh n là hợp số**. Một vòng kiểm tra với một cơ sở thường chưa đủ để kết luận n nguyên tố, vì một hợp số có thể **đánh lừa một số cơ sở nhất định**. Vì thế phần **lựa chọn cơ sở (bases)** quan trọng không kém chính vòng lặp Miller–Rabin.

Bài học thuộc nhóm **Thuật toán số học** trong Computer Science Algorithms. Ta sẽ làm rõ định nghĩa nguyên tố/hợp số, phân biệt phép thử Fermat với Miller–Rabin, phân tích phép tách `n−1=2^s·d`, hiểu *witness* và *strong pseudoprime*, cách chọn cơ sở **ngẫu nhiên** hoặc **tất định cho miền 64-bit**, ngăn tràn số trong Java 17, viết chương trình độc lập và kiểm chứng kết quả với phương pháp chia thử.

**Mục tiêu thực hành:** cho một giá trị `long n` bất kỳ trong Java, xác định chính xác nó có nguyên tố hay không **trong miền số nguyên dương có thể biểu diễn bằng signed long**; đồng thời hiểu khi nào phiên bản xác suất được phép nói *probably prime* thay vì kết luận chắc chắn.

## 1. Nguyên tố, hợp số và miền dữ liệu

Một số nguyên `n>1` là **số nguyên tố** nếu ước nguyên dương duy nhất của nó là 1 và n. Ví dụ `2,3,5,7,11,13,17,19`.

- `0`, `1` và mọi số âm **không phải số nguyên tố**.
- `2` là số nguyên tố **chẵn duy nhất**.
- Các số chẵn lớn hơn 2 đều là hợp số.
- Một `n>1` không nguyên tố được gọi là **hợp số**.

Ví dụ `21=3×7`, `561=3×11×17`, `2047=23×89` đều là hợp số.

### Tại sao chia thử có thể không đủ nhanh?

Kiểm tra bằng cách chia lần lượt các số từ 2 tới `⌊√n⌋` tốn `O(√n)` phép thử chia trong trường hợp xấu. Với n cỡ `10^{18}`, căn n cỡ `10^9`, không phù hợp nếu có nhiều truy vấn.

Ta có thể cải thiện chia thử bằng cách chỉ kiểm tra các số nguyên tố hoặc dùng sàng cho nhiều n nhỏ, nhưng đối với **một vài số rất lớn** Miller–Rabin thường nhanh hơn nhiều.

Chương trình ở cuối bài dùng **hai hướng khác nhau**:
- **Miller–Rabin với một bộ cơ sở đã biết đủ cho 64-bit**: kiểm tra số dương thuộc miền signed `long`.
- **Chia thử tới căn bậc hai**: chỉ làm **oracle đối chiếu** trên n nhỏ, không chạy chia thử cho n cỡ `10^{18}`.

## 2. Bắt đầu từ định lý Fermat nhỏ

Với n là **số nguyên tố** và a không chia hết cho n:

\[
a^{n-1}\equiv 1\pmod n.
\]

Nếu tìm thấy một cơ sở a sao cho `a^{n-1} mod n ≠ 1` thì n **chắc chắn là hợp số**. Tuy nhiên chiều ngược **không đúng**: có hợp số vẫn thỏa đồng dư đó đối với một hoặc nhiều cơ sở.

### Ví dụ hợp số Carmichael

`561=3×11×17` là số Carmichael: với mọi a nguyên tố cùng nhau với 561, `a^{560}≡1 (mod 561)`. Vì thế phép thử Fermat đơn thuần có thể bị đánh lừa dù n rõ ràng là hợp số.

Cụ thể:

~~~text
n = 561
a = 2
2^560 mod 561 = 1
~~~

Nếu chỉ kiểm tra bằng `a^{n-1} mod n == 1`, ta **không thể kết luận 561 nguyên tố**. Miller–Rabin đặt thêm điều kiện trên **chuỗi các phép bình phương**, mạnh hơn phép thử Fermat cơ bản.

## 3. Ý tưởng toán học của Miller–Rabin

Giả sử `n>2` là số lẻ. Phân tích:

\[
\boxed{n-1=2^s d,\qquad d\text{ lẻ},\quad s\ge1.}
\]

Ta lấy hết các thừa số 2 của `n−1`:
- `s` = số lần chia liên tiếp `n−1` cho 2;
- `d` = phần còn lại là số lẻ.

Với cơ sở a, xét:

\[
x_0=a^d\bmod n,
\quad x_1=x_0^2\bmod n,
\quad x_2=x_1^2\bmod n,\ldots,
\quad x_s=a^{n-1}\bmod n.
\]

Ta có chuỗi:

\[
a^d,\;a^{2d},\;a^{4d},\ldots,a^{2^s d}
\quad(\bmod n).
\]

### Vì sao có điều kiện `1` và `−1`?

Nếu n là số nguyên tố, trong trường hữu hạn modulo n, phương trình

\[
x^2\equiv1\pmod n
\]

chỉ có hai nghiệm `x≡1` và `x≡−1`. Thật vậy:

\[
(x-1)(x+1)\equiv0\pmod n.
\]

Với n nguyên tố, nếu tích chia hết cho n thì n chia hết một trong hai thừa số; vậy x phải tương đương 1 hoặc −1.

Mặt khác theo Fermat, cuối chuỗi `a^{n−1} mod n` phải bằng 1 đối với cơ sở a không chia hết cho n. Nếu `x_0≠1`, thì **trước lần đầu chuỗi bình phương đi tới 1**, phần tử ngay trước phải là `−1`; không thể là một căn bậc hai “lạ” của 1.

Do đó với **n nguyên tố** và cơ sở a không đồng dư 0 mod n, ít nhất một trong các điều kiện sau phải đúng:
1. `a^d mod n = 1`, hoặc
2. Có `r` với `0≤r<s` sao cho `a^{2^r d} mod n = n−1`.

Nếu **không** có hai kiểu kết quả này, n **không thể là nguyên tố**. Ta đã tìm được một **chứng cứ hợp số**, gọi là *Miller–Rabin witness*.

### Thuật ngữ quan trọng

- **Witness / cơ sở chứng minh hợp số:** cơ sở a khiến vòng Miller–Rabin bác bỏ n. Kết luận **composite** là chắc chắn.
- **Passing base / cơ sở không tìm được chứng cứ:** cơ sở a không bác bỏ n. Kết luận chỉ là **n chưa bị chứng minh hợp số ở cơ sở này**.
- **Strong probable prime (SPRP) to base a:** số lẻ n vượt qua phép thử mạnh với cơ sở a.
- **Strong pseudoprime to base a:** n thực chất **hợp số** nhưng vượt qua vòng Miller–Rabin ở cơ sở a.
- **Probably prime:** nhãn cho kết quả đã qua một số vòng chọn cơ sở khi **chưa** có bộ cơ sở đủ để chứng nhận tính đúng trên miền xét.
- **Deterministic primality for bounded domain:** đã có **định lý/định giới hạn đủ cơ sở** cho toàn miền n được phép. Khi đó vượt qua tất cả cơ sở trong bộ mới suy ra **nguyên tố chắc chắn trong miền**.

Không được biến “không tìm thấy witness ở cơ sở 2” thành “n là số nguyên tố”.

## 4. Một vòng kiểm tra Miller–Rabin

Với một `n≥3` lẻ và một giá trị cơ sở a:

1. Tách `n−1=2^s d` với d lẻ.
2. Chuẩn hóa cơ sở `a mod n`. Nếu kết quả 0, cơ sở đó **không cung cấp thông tin**, bỏ qua chứ không coi là chứng cứ nguyên tố.
3. Tính `x=a^d mod n` bằng **lũy thừa nhị phân mô-đun**.
4. Nếu `x=1` hoặc `x=n−1`, cơ sở này **không bác bỏ n**.
5. Nếu không, thực hiện tối đa `s−1` phép bình phương:
   - `x=(x×x) mod n`;
   - nếu `x=n−1`, cơ sở này **không bác bỏ n**;
   - nếu `x=1` trước khi từng gặp `n−1`, đã thấy một căn khác ±1 của 1, **n là hợp số**.
6. Nếu hết chuỗi mà chưa gặp 1 ngay từ đầu hoặc −1 ở điểm cho phép, cơ sở a **chứng minh n hợp số**.

Giả mã:

~~~text
isCompositeWitness(n, a):         // n le >= 3
    a = a mod n
    if a == 0: return false       // co so nay khong thong tin

    n-1 = 2^s * d  (d le)
    x = powMod(a, d, n)

    if x == 1 or x == n-1:
        return false               // khong phat hien hop so

    repeat s-1 lan:
        x = (x*x) mod n
        if x == n-1:
            return false           // khong phat hien hop so
        if x == 1:
            return true            // can bac hai phi tam thuong

    return true                    // co so chung minh hop so
~~~

**Quy ước tên hàm:** trong bài, `isCompositeWitness(n,a)=true` nghĩa là **đã phát hiện chứng cứ chắc chắn n hợp số**, không phải “n nguyên tố”. `false` nghĩa là **cơ sở không bác bỏ n**; một hợp số vẫn có thể cho false đối với một số cơ sở.

Phải xử lý riêng n âm, 0,1,2 và số chẵn **trước khi** gọi thuật toán dành cho n lẻ ≥3.

### Lũy thừa mô-đun nhanh

Không bao giờ tính nguyên số `a^d` rồi mới lấy mod nếu d lớn: số chữ số tăng cực nhanh. Dùng *binary exponentiation*:
- Giữ kết quả r ban đầu 1.
- Xét từng bit của d.
- Khi bit thấp bằng 1, nhân r với a theo mô-đun.
- Bình phương a theo mô-đun, dịch d.
- Chỉ lưu số dư dưới n sau mỗi bước.

Số phép nhân mô-đun là O(log d), thay vì O(d). Trong Java, `BigInteger.modPow` đã thực hiện lũy thừa mô-đun và tránh tràn kiểu `long`.

## 5. Tính tay với n=21 và a=2

Ta biết `21=3×7` là hợp số, nhưng dùng nó để kiểm tra cơ chế.

\[
21-1=20=2^2\cdot5.
\]

Vậy `s=2`, `d=5`. Tính:

\[
x_0=2^5\bmod21=32\bmod21=11.
\]

`11` không phải 1 và cũng không phải `n−1=20`. Bình phương một lượt vì `s−1=1`:

\[
x_1=11^2\bmod21=121\bmod21=16.
\]

`16` cũng không phải 20. **Cơ sở 2 là witness**, thuật toán trả “composite”.

~~~text
n=21, a=2
n-1=20=2^2*5
x0=2^5 mod 21 = 11
x1=11^2 mod 21 = 16
Khong xuat hien x0=1 hoac x0/x1=20
=> n la hop so
~~~

Đối với số nguyên tố, phép thử không thể bác bỏ nhầm một cơ sở hợp lệ, vì chuỗi phải đi qua 1 ngay từ đầu hoặc −1 trước khi bình phương về 1.

## 6. Một cơ sở có thể bị đánh lừa

### Hợp số 2047: cơ sở 2 không đủ

`2047=23×89` là hợp số nhưng vượt qua kiểm tra Miller–Rabin cơ sở 2: đây là một **strong pseudoprime base 2**.

~~~text
n=2047
isCompositeWitness(n, 2) = false
isCompositeWitness(n, 3) = true
~~~

Nếu chỉ thử cơ sở 2, ta chưa phát hiện được hợp số; thử thêm cơ sở 3 thì có chứng cứ.

### Hợp số 1.373.653: cơ sở 2 và 3 đều bị đánh lừa

`1.373.653=829×1657`. Kết quả:

~~~text
n=1373653
isCompositeWitness(n, 2) = false
isCompositeWitness(n, 3) = false
isCompositeWitness(n, 5) = true
~~~

Vì vậy kiểm tra **hai cơ sở nhỏ đầu tiên** chưa đảm bảo đúng cho mọi n lớn.

### Hợp số đánh lừa cả bảy cơ sở nguyên tố nhỏ

Xét:

\[
n=341550071728321=10670053\times32010157.
\]

Hợp số này vượt qua Miller–Rabin với các cơ sở nguyên tố đầu tiên `2,3,5,7,11,13,17`. Nó còn vượt qua nhiều cơ sở nguyên tố nhỏ khác. Nhưng một cơ sở trong **bộ bảy số đặc biệt 64-bit** ở phần sau sẽ tìm được chứng cứ hợp số.

**Bài học:** không được viết “thử các số nguyên tố 2,3,5,7,11,13,17 thì đúng cho mọi số 64-bit” nếu không có giới hạn số n đi kèm. **Số vòng lặp** không phải bằng chứng của một bộ cơ sở tùy tiện được chọn cố định.

## 7. Hai chiến lược chọn cơ sở: xác suất và tất định

### A. Chọn cơ sở ngẫu nhiên độc lập

Với n lẻ hợp số, một định lý của Miller–Rabin cho biết **không quá 1/4 số cơ sở** trong cách lấy ngẫu nhiên đều thích hợp có thể đánh lừa phép thử mạnh.

Nếu mỗi vòng chọn **độc lập và đều** một cơ sở trong vùng hợp lệ, xác suất hợp số qua hết k vòng bị chặn:

\[
\boxed{P(\text{hop so vuot k vong})\le(1/4)^k.}
\]

Ví dụ:

| Số vòng độc lập k | Cận xác suất mắc lỗi đối với hợp số |
| ---: | --- |
| 1 | ≤1/4 |
| 2 | ≤1/16 |
| 5 | ≤1/1.024 |
| 10 | ≤1/1.048.576 |
| 20 | ≤1/1.099.511.627.776 |
| 32 | ≤2^{-64} |

Điều này là **xác suất theo việc rút cơ sở**, không phải tuyên bố rằng sau 20 vòng số n có “xác suất 99.999…% là nguyên tố” theo nghĩa xác suất hậu nghiệm không có giả định về phân bố đầu vào.

**Điều kiện then chốt:**
- Các cơ sở phải được rút đều và độc lập theo giả thiết của định lý.
- Nếu lặp lại **cùng một cơ sở** k lần, không thể lấy cận `4^{-k}` như k phép thử độc lập.
- Nếu chỉ rút ngẫu nhiên trong một tập nhỏ, cố định, bị thiên lệch (ví dụ chỉ {2,3}), không có quyền viện dẫn cận tổng quát `4^{-k}`.
- Nếu input do đối thủ chủ động chọn, nguồn sinh ngẫu nhiên **phải khó đoán** nếu muốn ngăn họ tối ưu đầu vào để vượt qua lịch cơ sở. Java `SecureRandom` phù hợp hơn `Random`/`SplittableRandom` cho trường hợp đối kháng.

Với n đủ lớn sau khi xử lý số nhỏ, chương trình chọn ngẫu nhiên đều:

\[
2\le a\le n-2.
\]

Hàm `uniformBase` dùng `SecureRandom` và **rejection sampling** trên số nguyên BigInteger để tránh thiên lệch do lấy mod một số ngẫu nhiên có miền không chia hết kích thước khoảng.

**Kết quả đúng của phiên bản xác suất:** nếu tìm được witness → **hợp số chắc chắn**. Nếu không tìm được sau k vòng → **probably prime**, với giới hạn xác suất như trên cho mỗi n hợp số cố định khi giả thiết chọn cơ sở thỏa mãn.

### B. Chọn bộ cơ sở tất định cho số 64-bit

Khi n bị giới hạn trong **miền số nguyên 64-bit**, có thể dùng một **bộ cơ sở được biết là đủ cho toàn miền**, thay vì chọn ngẫu nhiên. Một bộ cơ sở 7 phần tử thường dùng là:

~~~text
2
325
9375
28178
450775
9780504
1795265022
~~~

Bộ 7 cơ sở này là bộ đã được xác lập đủ để phân biệt nguyên tố/hợp số đối với các số nguyên **0≤n<2^64** khi thực hiện Miller–Rabin đúng và xử lý các trường hợp nhỏ. Những phần tử như 325 và 9375 **không nhất thiết là số nguyên tố**; Miller–Rabin không yêu cầu cơ sở phải nguyên tố.

Trong Java:
- `long` là số nguyên có dấu 64-bit: từ `−2^63` đến `2^63−1`.
- Hàm `isPrimeDeterministic(long n)` dưới đây trả false cho n nhỏ hơn 2, và dùng bộ cơ sở đã đủ cho **toàn bộ n nguyên dương mà signed long biểu diễn được**.
- Miền `n≥2^63` nhưng `n<2^64` thuộc **unsigned 64-bit**; hàm nhận `long` dương **không** xử lý trực tiếp miền đó. Muốn bao phủ toàn unsigned 64-bit, cần cách biểu diễn/so sánh số không dấu hoặc BigInteger **đúng**.
- Với **n lớn hơn hoặc bằng 2^64**, không được áp dụng “bảy cơ sở này là đủ” như một định lý. Cần bộ cơ sở/giới hạn khác hoặc thuật toán kiểm chứng khác.

**Vì sao cơ sở lớn hơn n vẫn được phép?** Trong phép thử mô-đun, kiểm tra cơ sở `a mod n`. Nếu kết quả bằng 0, cơ sở đó không cung cấp witness, nên bỏ qua. Các cơ sở còn lại trong **bộ đã được bảo đảm cho miền n** vẫn có thể chứng minh đúng. Bài không kết luận tính đúng bằng một cơ sở tự chọn đơn lẻ.

**Tất định khác với xác suất:** đây không phải suy luận “7 vòng nên xác suất lỗi ≤4^{-7}”. Lý do không có false positive trong miền 64-bit là **tính bao phủ của bộ cơ sở đặc biệt**, không phải giả định chúng được chọn ngẫu nhiên độc lập.

### C. Số nguyên lớn hơn 64-bit

Khi n vượt signed long hoặc unsigned 64-bit:
- Dùng `BigInteger` cho toàn bộ n, d, a, phép nhân và lũy thừa mô-đun.
- Chọn các cơ sở ngẫu nhiên thật sự trên miền hợp lệ với số vòng phù hợp theo yêu cầu độ tin cậy, hoặc dùng thuật toán/cơ chế chứng minh nguyên tố nếu cần **chứng nhận**.
- Không mở rộng bộ 7 cơ sở trên bằng cách “giữ nguyên và hy vọng”.

Trong ứng dụng Java, `BigInteger.isProbablePrime(certainty)` cung cấp một API kiểm tra **nguyên tố xác suất**; tham số `certainty` không được hiểu đơn giản là **số cơ sở Miller–Rabin** do cài đặt có thể dùng các bước kiểm tra khác. Nếu yêu cầu đầu ra “nguyên tố chứng minh được”, API *probable prime* không tự biến thành chứng chỉ toán học.

## 8. Tràn số trong Java: lỗi nghiêm trọng nhất khi cài

Một lập trình viên có thể viết đúng thuật toán trên giấy nhưng cài sai vì:

~~~text
long x = (a * b) % n;      // co the tran long TRUOC khi modulo
long y = (x * x) % n;      // cung co the tran long
~~~

Ví dụ với n gần `9×10^{18}`, hai số dư mỗi số gần n, tích có thể tới `10^{37}`, vượt xa `Long.MAX_VALUE≈9,22×10^{18}`. Trong Java, phép nhân long tràn theo quy tắc số nguyên có dấu, không phát sinh ngoại lệ mặc định; kết quả mod sau đó **không còn là số dư đúng của tích toán học**.

**Ba hướng xử lý:**
1. **BigInteger** cho `modPow` và bình phương mô-đun: dễ đọc, chính xác, phù hợp cho bài dạy; chương trình dùng cách này.
2. **Nhân mô-đun bằng cộng/nhân đôi có kiểm soát** mà không vượt ngưỡng: tránh tràn nếu cài đúng, nhưng nhiều phép cộng/so sánh hơn, dễ sai dấu và chậm hơn.
3. **Kỹ thuật nhân rộng / Montgomery / Barrett / phép nhân 128-bit hoặc unsigned**: phù hợp khi tối ưu mạnh, nhưng cần chứng minh và kiểm thử riêng, không tự lấy `(a*b)%n` của signed long.

Mã Java 17 này dùng:
- `BigInteger.valueOf(n)` để giữ mô-đun chính xác;
- `BigInteger.modPow(BigInteger.valueOf(d), N)` để tính `a^d mod n`;
- `x.multiply(x).mod(N)` để bình phương an toàn.

Do đó không có phép nhân mô-đun nào **tràn long trước khi mod**. Chỉ sau khi có kết quả trong miền BigInteger mới so với 1 và n−1.

### Phân rã n−1 an toàn

Với `n>2` lẻ, `n−1` là số chẵn dương. Java có:

~~~text
int s = Long.numberOfTrailingZeros(n - 1);
long d = (n - 1) >>> s;
~~~

Đây là số mũ s của 2 trong n−1 và phần lẻ d. Vì n là **long dương**, `n−1` không âm và dịch phải không dấu `>>>` hoạt động đúng; n=1 phải được loại trước. Với n=2, n−1=1 có s=0, nhưng thuật toán dành cho n lẻ nên n=2 xử lý riêng.

## 9. Lọc số nhỏ trước khi chạy phép thử mạnh

Chương trình thử một danh sách số nguyên tố nhỏ:

~~~text
2,3,5,7,11,13,17,19,23,29,31,37
~~~

Với mỗi p:
- Nếu n bằng p, trả **true** ngay (nguyên tố).
- Nếu n chia hết cho p nhưng lớn hơn p, trả **false** ngay (hợp số).

Bước này giúp:
- Xử lý chính xác n=2 và các nguyên tố nhỏ.
- Loại nhanh số chẵn và nhiều hợp số nhỏ, tránh gọi `modPow`.
- Giảm việc rút cơ sở vô nghĩa trong phiên bản ngẫu nhiên.

**Chú ý:** kiểm tra hết các số nguyên tố nhỏ rồi không chia hết **chưa chứng minh n nguyên tố**. Nó chỉ là một bộ lọc nhanh; các số còn lại phải được kiểm tra bằng Miller–Rabin hoặc cách chắc chắn khác.

Không được thử phép chia cho n=0,1 rồi kết luận “nguyên tố” chỉ vì không tìm thấy ước. Quy ước nguyên tố luôn đòi `n>1`.

## 10. Chương trình Java 17 chạy độc lập

File **MillerRabinBasesDemo.java** dưới đây có:
- `isCompositeWitness(n,a)`: trả true **chỉ khi** cơ sở a chứng minh n hợp số; bỏ qua cơ sở có `a mod n=0`.
- `isPrimeDeterministic(n)`: kiểm tra **đúng cho signed long dương** bằng bộ 7 cơ sở đủ cho miền 64-bit.
- `isProbablePrimeRandom(n,rounds,SecureRandom)`: rút cơ sở **ngẫu nhiên đều bằng rejection sampling**, trả kết quả *probably prime* nếu chưa gặp witness.
- `trialPrime(n)`: oracle độc lập bằng chia thử, **chỉ dùng trên n nhỏ**.
- `verify()`: đối chiếu liên tục **20.001 số từ 0 đến 20.000** và kiểm tra **3.000 hợp số lẻ lớn** xây bằng tích hai số lớn hơn 1.
- Các ví dụ chứng minh **Fermat và một vài cơ sở nhỏ có thể bị đánh lừa**.

~~~java
import java.math.BigInteger;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Objects;

public class MillerRabinBasesDemo {
    private static final BigInteger ONE = BigInteger.ONE;

    private static final int[] SMALL_PRIMES = {
        2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37
    };

    // Bo 7 witness DU de kiem tra tat dinh n < 2^64.
    // Code nay chi nhan n DUONG trong signed long.
    private static final long[] BASES_64 = {
        2L, 325L, 9375L, 28178L,
        450775L, 9780504L, 1795265022L
    };

    // True = tim duoc chung cu n la HOP SO.
    // False = co so nay KHONG bac bo n (chua ket luan n prime).
    // Chi goi voi n le >= 3 va rawBase >= 2.
    static boolean isCompositeWitness(long n, long rawBase) {
        if (n < 3 || (n & 1L) == 0L) {
            throw new IllegalArgumentException(
                    "Odd n >= 3 required");
        }
        if (rawBase < 2) {
            throw new IllegalArgumentException(
                    "Base >= 2 required");
        }

        long a = rawBase % n;
        if (a == 0L) {
            // Co so la boi cua n: khong cung cap witness.
            return false;
        }

        long even = n - 1L;
        int s = Long.numberOfTrailingZeros(even);
        long d = even >>> s;     // n-1 = (2^s)*d, d le

        BigInteger N = BigInteger.valueOf(n);
        BigInteger minusOne = N.subtract(ONE);

        BigInteger x = BigInteger.valueOf(a).modPow(
                BigInteger.valueOf(d), N);

        if (x.equals(ONE) || x.equals(minusOne)) {
            return false;       // Khong phat hien hop so.
        }

        for (int r = 1; r < s; r++) {
            // Dung BigInteger, KHONG nhan long tran so.
            x = x.multiply(x).mod(N);

            if (x.equals(minusOne)) {
                return false;   // Co so chua bac bo n.
            }
            if (x.equals(ONE)) {
                return true;    // Can bac hai la cua 1.
            }
        }

        return true;            // Khong co -1 trong chuoi.
    }

    // Ket qua TAT DINH cho 0 <= n <= Long.MAX_VALUE.
    static boolean isPrimeDeterministic(long n) {
        if (n < 2L) return false;

        for (int p : SMALL_PRIMES) {
            if (n == p) return true;
            if (n % p == 0L) return false;
        }

        // Sau loc n le, n >= 41.
        for (long base : BASES_64) {
            if (isCompositeWitness(n, base)) {
                return false;
            }
        }
        return true;
    }

    // Lay deu a trong [2, n-2], n >= 5.
    // Rejection sampling tranh bias cua phep mod.
    static long uniformBase(long n, SecureRandom random) {
        if (n < 5L) {
            throw new IllegalArgumentException("n >= 5");
        }
        Objects.requireNonNull(random, "random");

        BigInteger choices = BigInteger.valueOf(n - 3L);
        BigInteger candidate;
        do {
            candidate = new BigInteger(
                    choices.bitLength(), random);
        } while (candidate.compareTo(choices) >= 0);

        // candidate: 0..n-4 => base: 2..n-2.
        return candidate.longValueExact() + 2L;
    }

    // Ket qua XAC SUAT (probable prime) voi co so
    // ngau nhien deu va doc lap qua SecureRandom.
    static boolean isProbablePrimeRandom(
            long n, int rounds, SecureRandom random) {
        if (rounds <= 0) {
            throw new IllegalArgumentException(
                    "rounds must be positive");
        }
        Objects.requireNonNull(random, "random");
        if (n < 2L) return false;

        for (int p : SMALL_PRIMES) {
            if (n == p) return true;
            if (n % p == 0L) return false;
        }

        for (int r = 0; r < rounds; r++) {
            long a = uniformBase(n, random);
            if (isCompositeWitness(n, a)) {
                return false;
            }
        }
        return true;
    }

    // Oracle: chia thu toi can bac hai, chi cho n NHO.
    static boolean trialPrime(long n) {
        if (n < 2L) return false;
        if (n % 2L == 0L) return n == 2L;

        for (long divisor = 3L;
                divisor <= n / divisor;
                divisor += 2L) {
            if (n % divisor == 0L) return false;
        }
        return true;
    }

    static void assertPrime(long n, boolean expected) {
        boolean actual = isPrimeDeterministic(n);
        if (actual != expected) {
            throw new AssertionError(
                    "Wrong primality: n=" + n);
        }
    }

    record Stats(long checkedRange,
                 int constructedComposites) {}

    static Stats verify() {
        long checked = 0L;
        for (long n = 0L; n <= 20_000L; n++) {
            if (isPrimeDeterministic(n) != trialPrime(n)) {
                throw new AssertionError(
                        "Mismatch with trial division: " + n);
            }
            checked++;
        }

        int constructed = 0;
        for (int i = 0; i < 3000; i++) {
            // Tich cua hai so lon hon 1 chac chan hop so.
            // Cac tich o day < Long.MAX_VALUE.
            long a = 1_500_000_001L + 2L * i;
            long b = 1_500_000_033L + 4L * i;
            long composite = Math.multiplyExact(a, b);
            if (isPrimeDeterministic(composite)) {
                throw new AssertionError(
                        "Odd product accepted: " + composite);
            }
            constructed++;
        }

        assertPrime(2L, true);
        assertPrime(97L, true);
        assertPrime(561L, false);            // Carmichael
        assertPrime(2047L, false);           // SPSP base 2
        assertPrime(1373653L, false);        // SPSP bases 2,3
        assertPrime(341550071728321L, false);
        assertPrime(3825123056546413051L, false);
        assertPrime(2305843009213693951L, true);
        assertPrime(Long.MAX_VALUE, false);

        return new Stats(checked, constructed);
    }

    public static void main(String[] args) {
        System.out.println("fixedBases="
                + Arrays.toString(BASES_64));

        long[] examples = {
            -17L, 0L, 1L, 2L, 3L, 4L, 17L,
            21L, 97L, 561L, 1105L, 1729L,
            2047L, 1373653L, 341550071728321L,
            3825123056546413051L,
            2305843009213693951L, Long.MAX_VALUE
        };
        for (long n : examples) {
            System.out.println("prime(" + n + ")="
                    + isPrimeDeterministic(n));
        }

        System.out.println("2047.base2.witness="
                + isCompositeWitness(2047L, 2L));
        System.out.println("2047.base3.witness="
                + isCompositeWitness(2047L, 3L));
        System.out.println("1373653.base2.witness="
                + isCompositeWitness(1373653L, 2L));
        System.out.println("1373653.base3.witness="
                + isCompositeWitness(1373653L, 3L));
        System.out.println("1373653.base5.witness="
                + isCompositeWitness(1373653L, 5L));

        long hardComposite = 341550071728321L;
        long[] firstSevenPrimes = {
            2L, 3L, 5L, 7L, 11L, 13L, 17L
        };
        boolean firstSevenMiss = true;
        for (long base : firstSevenPrimes) {
            if (isCompositeWitness(hardComposite, base)) {
                firstSevenMiss = false;
            }
        }
        boolean fixedSevenDetect = false;
        for (long base : BASES_64) {
            if (isCompositeWitness(hardComposite, base)) {
                fixedSevenDetect = true;
            }
        }
        System.out.println("firstSevenPrimesMiss="
                + firstSevenMiss);
        System.out.println("fixedSevenBasesDetect="
                + fixedSevenDetect);

        BigInteger fermat561 = BigInteger.valueOf(2L)
                .modPow(BigInteger.valueOf(560L),
                        BigInteger.valueOf(561L));
        System.out.println("fermat561base2=" + fermat561);
        System.out.println("MR561base2witness="
                + isCompositeWitness(561L, 2L));

        // Hai dong sau LUON on dinh: 1e9+7 la prime,
        // 561 chia het cho 3; random khong doi ket luan.
        SecureRandom random = new SecureRandom();
        System.out.println("probablePrime1000000007="
                + isProbablePrimeRandom(
                    1_000_000_007L, 12, random));
        System.out.println("probablePrime561="
                + isProbablePrimeRandom(
                    561L, 12, random));

        Stats stats = verify();
        System.out.println("checkedRange="
                + stats.checkedRange());
        System.out.println("constructedOddComposites="
                + stats.constructedComposites());
    }
}
~~~

Lưu mã vào **MillerRabinBasesDemo.java**. Với **JDK 17 trở lên**, chạy:

~~~bash
javac MillerRabinBasesDemo.java
java MillerRabinBasesDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
fixedBases=[2, 325, 9375, 28178, 450775, 9780504, 1795265022]
prime(-17)=false
prime(0)=false
prime(1)=false
prime(2)=true
prime(3)=true
prime(4)=false
prime(17)=true
prime(21)=false
prime(97)=true
prime(561)=false
prime(1105)=false
prime(1729)=false
prime(2047)=false
prime(1373653)=false
prime(341550071728321)=false
prime(3825123056546413051)=false
prime(2305843009213693951)=true
prime(9223372036854775807)=false
2047.base2.witness=false
2047.base3.witness=true
1373653.base2.witness=false
1373653.base3.witness=false
1373653.base5.witness=true
firstSevenPrimesMiss=true
fixedSevenBasesDetect=true
fermat561base2=1
MR561base2witness=true
probablePrime1000000007=true
probablePrime561=false
checkedRange=20001
constructedOddComposites=3000
~~~

### Giải thích những dòng quan trọng

- `prime(2)=true`, `prime(1)=false` và `prime(-17)=false` xác nhận hàm xử lý trường hợp biên.
- `prime(2047)=false` trong khi `2047.base2.witness=false` minh họa **không phải cơ sở nào cũng bắt được hợp số**.
- `1373653.base2.witness=false` và `1373653.base3.witness=false`, nhưng `base5.witness=true`. Nếu chọn các cơ sở cố định đầu tiên một cách tùy tiện, vẫn có thể bị đánh lừa.
- `firstSevenPrimesMiss=true` nghĩa là bảy **cơ sở nguyên tố nhỏ** 2,3,5,7,11,13,17 đều bỏ sót hợp số 341550071728321.
- `fixedSevenBasesDetect=true` nghĩa là ít nhất một cơ sở trong **bộ đặc biệt {2,325,9375,28178,450775,9780504,1795265022}** chứng minh số đó hợp số.
- `fermat561base2=1` nhưng `MR561base2witness=true` cho thấy Miller–Rabin phân biệt được trường hợp hợp số mà phép kiểm tra Fermat yếu hơn không phân biệt được.
- `probablePrime1000000007=true` có kết quả ổn định vì 1.000.000.007 thực sự là nguyên tố, nên mọi cơ sở hợp lệ đều không thể bác bỏ nó. `probablePrime561=false` ổn định vì 561 bị bộ lọc 3 loại ngay từ đầu. Các số hợp khác **có thể** có kết quả ngẫu nhiên thay đổi theo các cơ sở được rút, và đó là chủ ý của phương pháp xác suất.
- `checkedRange=20001` là số n trong đoạn [0,20.000] được đối chiếu với oracle chia thử.
- `constructedOddComposites=3000` là 3.000 tích số lẻ dương lớn; vì mỗi tích có hai thừa số lớn hơn 1, chúng chắc chắn là hợp số. Không dùng chia thử tới căn bậc hai trên các số này.

### Ghi chú về phương thức isCompositeWitness

Hàm nhận `rawBase≥2` nhưng **giảm modulo n** trước khi tính lũy thừa. Nếu `rawBase mod n=0`, hàm trả `false` với nghĩa **không có witness**, **không** có nghĩa “cơ sở này đã chứng minh nguyên tố”. Đây là cách dùng an toàn trong một bộ cơ sở tất định: những cơ sở vô ích được bỏ qua và những cơ sở khác vẫn phải được xét.

Hàm `isPrimeDeterministic` trả lời trong **signed long**; nó không thao tác với unsigned n≥2^63. Vì vậy tên phương thức không nên được hiểu là chứng nhận vô hạn mọi số BigInteger.

### Cách chọn cơ sở ngẫu nhiên trong code

`uniformBase` lấy một số ngẫu nhiên BigInteger trong `[0,n−4]` bằng rejection sampling rồi cộng 2. Do đó trả đúng miền `[2,n−2]`, không dùng `random.nextLong()%n` có thiên lệch/âm và không an toàn cho các giá trị n sát giới hạn long.

`SecureRandom` cho nguồn ngẫu nhiên phù hợp hơn trong tình huống an ninh so với PRNG có seed dễ dự đoán; nhưng **số vòng rounds phải dương** và cận xác suất vẫn dựa vào giả thiết phân phối/rút cơ sở. Với n đã bị small-prime filter phát hiện hợp số, mã không chạy các vòng tốn kém.

## 11. Kiểm thử độc lập và giới hạn của kiểm chứng

### Nhóm 1 — Đối chiếu từng số từ 0 đến 20.000

Bộ `verify` đối chiếu:

~~~text
for n = 0 .. 20000:
    actual = isPrimeDeterministic(n)
    expected = trialPrime(n)
    assert actual == expected
~~~

`trialPrime` **không gọi Miller–Rabin**, dùng kiểm tra ước số 2 rồi các ước lẻ tới `divisor ≤ n/divisor`. Điều kiện `divisor ≤ n/divisor` tránh việc `divisor×divisor` có thể tràn nếu ai đó mở rộng phạm vi oracle.

Có **20.001 số** được kiểm tra:
- **2.262 số nguyên tố** trong đoạn [0,20.000].
- **17.739 số không nguyên tố** (bao gồm 0 và 1).

Nếu MR trả false cho một số thật ra nguyên tố, hoặc trả true cho một số nhỏ có ước, chương trình phát sinh `AssertionError` ngay.

### Nhóm 2 — 3.000 hợp số lẻ lớn

Tạo:

\[
a_i=1\,500\,000\,001+2i,\qquad
b_i=1\,500\,000\,033+4i,\quad0\le i<3000.
\]

Mỗi a_i, b_i là số lẻ **lớn hơn 1**, vì vậy tích:

\[
n_i=a_ib_i
\]

chắc chắn là **hợp số lẻ**. Các tích trong bộ thử nằm khoảng `2,25×10^{18}`, vẫn nhỏ hơn `Long.MAX_VALUE`. Mã dùng `Math.multiplyExact` để **phát hiện tràn số** nếu thông số bộ thử bị sửa về sau.

Với 3.000 hợp số này, Miller–Rabin tất định **phải trả false**. Tập này giúp bắt lỗi số học khi n lớn; không cần biết a_i, b_i có phải nguyên tố hay không vì một tích của **hai số >1** luôn hợp số.

### Nhóm 3 — Các trường hợp đối kháng có chủ đích

- `561`: hợp số Carmichael qua phép thử Fermat base 2 nhưng Miller–Rabin base 2 phát hiện.
- `2047`: hợp số mạnh đánh lừa base 2.
- `1373653`: hợp số mạnh đánh lừa base 2 và 3.
- `341550071728321`: hợp số đánh lừa bảy **cơ sở nguyên tố nhỏ**, nhưng bị bộ bảy cơ sở đặc biệt phát hiện.
- `3825123056546413051`: một hợp số lớn, khó cho những bộ cơ sở nhỏ tùy tiện.
- `2305843009213693951 = 2^{61}−1`: một số nguyên tố Mersenne đã biết; hàm phải trả true.
- `Long.MAX_VALUE = 2^{63}−1`: hợp số; hàm phải trả false.

Những kiểm tra này khác về vai trò so với việc chọn ngẫu nhiên vài số. Chúng chủ động tìm **những vùng lỗi dễ mắc**: giả định một cơ sở đủ, nhầm strong pseudoprime, tràn phép nhân và xử lý n sát giới hạn long.

### Kết quả QA

Đã đối chiếu logic số học độc lập bằng mô hình lũy thừa mô-đun trên số nguyên chính xác với:
- Toàn bộ **20.001** số n nhỏ;
- **3.000** hợp số lẻ lớn có cấu trúc tích;
- Các số khó và các cơ sở nêu trên;
- Giá trị `2^{61}−1` và `Long.MAX_VALUE`.

Việc đối chiếu hữu hạn **không tự chứng minh bộ cơ sở đủ cho mọi n<2^64**. Tính tất định trên miền đó dựa vào **tính chất đã được xác lập của bộ bảy cơ sở chuyên biệt**, không phải chỉ dựa vào các bài test. Trong một triển khai thực tế cần chứng nhận, nên kiểm chứng thư viện/bộ cơ sở theo tài liệu chuẩn và chạy test/benchmark trong môi trường đích.

## 12. Độ phức tạp và hiệu năng

Xét n có b bit, tức `b≈log_2(n)`.

### Một vòng

- Tách `n−1=2^s d` cần đếm bit 0 cuối, chi phí thao tác nhỏ.
- `modPow(a,d,n)` cần O(b) phép nhân mô-đun theo thuật toán lũy thừa nhị phân.
- Vòng bình phương thêm nhiều nhất `s−1≤b−1` phép nhân mô-đun.

Vậy:

\[
\boxed{\text{Một cơ sở dùng }O(\log n)\text{ phép nhân mô-đun}.}
\]

Đối với k cơ sở, cần **O(k log n) phép nhân mô-đun**, không tính bộ lọc chia hết cho các số nguyên tố nhỏ.

**Đừng đồng nhất “phép nhân mô-đun” với một thao tác bit O(1)** khi n là BigInteger rất lớn. Bit-complexity còn phụ thuộc chi phí nhân/chia số có b bit. Nếu gọi `M(b)` là chi phí một phép nhân mô-đun b bit, có thể ước lượng tổng theo mô hình:

\[
O(k\,b\,M(b)).
\]

Với Java signed long, b≤63 và bộ tất định chỉ có **7 cơ sở**, nên số vòng bị giới hạn nhỏ; chi phí BigInteger có hằng số nhưng tránh lỗi tràn.

### Bộ nhớ

- `isCompositeWitness` giữ một vài BigInteger và biến long/int: O(b) bit cho các số có b bit theo mô hình thuật toán.
- Bản xác suất dùng thêm số ngẫu nhiên BigInteger có b bit trong lúc lấy cơ sở.
- Bản tất định không cần lưu một sàng tới căn n, không có bảng O(√n).

### So sánh trường hợp sử dụng

| Phương án | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Chia thử | Dễ hiểu; xác định chắc chắn; tốt với n nhỏ | O(√n), chậm với n lớn |
| Sàng Eratosthenes | Rất tốt khi cần kiểm tra nhiều n trong khoảng **nhỏ cố định** | Bộ nhớ O(N) để sàng tới N |
| Fermat | Lũy thừa mô-đun đơn giản | Hợp số Carmichael và pseudoprime đánh lừa |
| Miller–Rabin ngẫu nhiên | Nhanh với n lớn; giảm cận lỗi qua vòng độc lập | “Probably prime” nếu chưa có bảo đảm miền/bases |
| Miller–Rabin cơ sở tất định 64-bit | Nhanh và đúng trong miền được chứng nhận | Phải giữ đúng miền và bộ cơ sở; không mở rộng vô hạn |
| BigInteger.isProbablePrime | API thư viện Java cho số lớn | Kết quả là probabilistic theo hợp đồng API |
| Chứng chỉ nguyên tố (ví dụ hướng ECPP) | Có thể cung cấp chứng cứ cho số lớn | Triển khai, xác minh và hiệu năng phức tạp hơn |

Sàng và Miller–Rabin không thay thế nhau trong mọi bài: nếu yêu cầu đánh dấu hàng triệu số từ 1 đến N với N vừa phải, **sàng** có thể tốt hơn gọi Miller–Rabin cho từng số. Nếu chỉ có ít số ngẫu nhiên gần 10^18, một sàng tới N lại không thực tế.

## 13. Những sai lầm thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi 1 là nguyên tố | Kết quả sai ngay biên | Kiểm tra n<2 trước |
| Quên xử lý 2 và n chẵn | Chạy phép thử cho sai miền | 2 nguyên tố; số chẵn >2 hợp số |
| Dùng `n−1` trực tiếp mà không tách 2^s | Mất chuỗi bình phương cần kiểm tra | Tính d lẻ và s chính xác |
| Tính `a^d` trước khi lấy mod | Tràn số/hết bộ nhớ | Dùng modPow |
| Dùng `(x*x)%n` trên long | Tràn trước phép mod | BigInteger hoặc mulMod đã chứng minh |
| Dùng % trên số âm làm normalization tùy tiện | Có thể âm trong Java | Cơ sở raw dương; xử lý modulo đúng |
| Chọn `a=0 mod n` rồi coi là witness | Chứng cứ không có ý nghĩa | Bỏ qua cơ sở vô dụng |
| Nếu `x=1` thì báo hợp số | Bác bỏ sai nguyên tố | `x=1` ở vòng đầu là điều kiện **pass** |
| Nếu bình phương tới `n−1` thì báo hợp số | Đảo ý nghĩa phép thử | Gặp −1 đúng lúc là điều kiện **pass** |
| Hết vòng bình phương vẫn không thấy −1 nhưng trả prime | Bỏ witness | Trả composite |
| Một cơ sở vượt qua thì kết luận nguyên tố | Strong pseudoprime làm sai | Thử bộ đủ hoặc random nhiều vòng |
| Dùng 2,3,5,7,11,13,17 cho mọi long | Hợp số đối kháng đánh lừa | Dùng bộ cơ sở được chứng nhận cho miền |
| Nghĩ cơ sở phải là số nguyên tố | Giới hạn không cần thiết | Cơ sở đặc biệt có thể là hợp số |
| Lặp lại cơ sở 2 k lần rồi viện dẫn 4^-k | Không độc lập | Chọn ngẫu nhiên độc lập thật sự |
| Sinh random base bằng `rnd.nextLong()%n` | Âm/thiên lệch/chệch miền | Rejection sampling |
| Dùng Random seed đoán được cho bài đối kháng | Đối thủ có thể đoán lịch cơ sở | SecureRandom |
| Gọi kết quả probable prime là chứng minh toán học | Vượt hợp đồng xác suất | Phân biệt probable/deterministic/certificate |
| Áp dụng bộ 64-bit cho n>2^64 | Không có bảo đảm | Chọn thuật toán/bộ khác |
| Quên signed long không biểu diễn n≥2^63 dương | Xử lý sai miền | Dùng BigInteger/unsigned đúng cách |
| Sử dụng `Math.sqrt(n)` rồi so bằng số thực | Sai biên độ lớn do làm tròn | Dùng `d≤n/d` khi chia thử |
| Tin các bài test nhỏ chứng minh mọi input | Bỏ sót phản ví dụ lớn | Kiểm thử + chứng minh miền/bases |

## 14. Chọn cơ sở theo yêu cầu bài toán

### Tình huống A — n không vượt giới hạn nhỏ

Nếu `n≤10^6` và có rất nhiều truy vấn trong cùng miền, **sàng Eratosthenes** thường phù hợp. Xây một mảng `isPrime[x]` rồi trả lời O(1)/truy vấn. Nếu chỉ một vài n nhỏ, chia thử cũng đủ, dễ debug.

### Tình huống B — n là signed long dương

Dùng Miller–Rabin với bộ cơ sở đủ cho miền 64-bit và mulMod không tràn (hoặc BigInteger như bài). Lúc này kết luận có thể là **prime/composite tất định** trên miền hỗ trợ, không phải chỉ probable prime.

Nếu có hàng triệu truy vấn tốc độ cao, nên benchmark bản dùng BigInteger với bản mulMod/Montgomery tối ưu, nhưng **không đánh đổi tính đúng số học để lấy tốc độ**.

### Tình huống C — n là BigInteger hàng trăm/hàng nghìn bit

Dùng kiểm tra xác suất với số vòng thích hợp và nguồn random đủ chất lượng, hoặc thư viện đáng tin cậy. Nếu cần **chứng chỉ nguyên tố để người khác xác minh**, cần thuật toán/hệ thống có khả năng xuất và kiểm chứng chứng cứ, không chỉ gọi Miller–Rabin vài lần.

### Tình huống D — yêu cầu bảo mật hoặc đối thủ chọn đầu vào

Đặc biệt phân biệt:
- Một số **hợp số bị witness bác bỏ** là kết luận chắc chắn.
- Một số **vượt qua k cơ sở ngẫu nhiên** chỉ có đảm bảo xác suất dựa trên giả thiết cơ sở khó đoán/độc lập/đều.
- Một số **thuộc miền có bộ cơ sở tất định đã được chứng nhận** có thể được kết luận chính xác sau khi vượt bộ cơ sở.

Không dùng lịch cơ sở cố định kiểu “lấy k số nguyên tố đầu” mà chưa chứng minh đủ miền; không dùng RNG seed công khai rồi tự nhận cận lỗi như chọn ngẫu nhiên độc lập trong trường hợp đối kháng.

## 15. Bài tập tự luyện có đáp án

**Bài 1 — định nghĩa.** `n=1` có phải nguyên tố không?

*Đáp án:* Không. Số nguyên tố phải lớn hơn 1.

**Bài 2 — chẵn.** Tại sao 2 là trường hợp đặc biệt?

*Đáp án:* 2 là số nguyên tố chẵn duy nhất; mọi số chẵn lớn hơn 2 có ước 2.

**Bài 3 — phân rã.** Viết `n−1=2^s d` với n=41.

*Đáp án:* `40=2^3×5`, nên s=3, d=5.

**Bài 4 — phân rã.** Với n=97, s và d là gì?

*Đáp án:* `96=2^5×3`, nên s=5, d=3.

**Bài 5 — tính tay.** Với n=21,a=2, `x_0=2^5 mod21` bằng gì?

*Đáp án:* 11, sau đó bình phương `11² mod21=16`. Không xuất hiện 1 lúc đầu hoặc 20, nên a=2 là witness.

**Bài 6 — điều kiện pass.** Nếu `a^d mod n=1` ở ngay vòng đầu, đã kết luận n nguyên tố được chưa?

*Đáp án:* Chưa. Chỉ biết cơ sở này không bác bỏ n.

**Bài 7 — điều kiện −1.** Nếu một phép bình phương trong chuỗi đạt `n−1` trước khi đạt 1, cơ sở có chứng minh hợp số không?

*Đáp án:* Không; đây là kiểu hành vi mà số nguyên tố có thể có, nên cơ sở pass.

**Bài 8 — căn phi tầm thường.** Nếu `x^2≡1 mod n` mà `x≠±1 mod n`, suy ra gì?

*Đáp án:* n không thể nguyên tố, vì trong modulo nguyên tố chỉ có ±1 là căn của 1.

**Bài 9 — Carmichael.** Vì sao `2^560 mod561=1` không chứng minh 561 nguyên tố?

*Đáp án:* 561 là hợp số Carmichael, phép thử Fermat yếu hơn Miller–Rabin.

**Bài 10 — strong pseudoprime.** `2047` qua base 2, nhưng base 3 chứng minh hợp số. Có thể gọi 2047 là nguyên tố xác suất sau một vòng base 2 không?

*Đáp án:* Chỉ có thể gọi “không bị phát hiện bởi base 2”; không được kết luận nguyên tố chắc chắn.

**Bài 11 — nhiều cơ sở.** Vì sao cơ sở 2 và 3 không đủ cho mọi n?

*Đáp án:* Hợp số 1.373.653 vượt cả hai cơ sở nhưng bị cơ sở 5 bác bỏ.

**Bài 12 — cơ sở nguyên tố.** Cơ sở 325 có nhất thiết phải là số nguyên tố để dùng trong phép thử không?

*Đáp án:* Không. Điều quan trọng là tính chất bộ cơ sở đủ cho miền, không phải mỗi cơ sở đều nguyên tố.

**Bài 13 — miền.** Hàm nhận signed `long n` dương hỗ trợ n lớn nhất là bao nhiêu?

*Đáp án:* `Long.MAX_VALUE=2^63−1=9223372036854775807`. Muốn hỗ trợ unsigned n≥2^63 phải dùng biểu diễn/phép tính khác.

**Bài 14 — cận lỗi.** Nếu chọn độc lập đều 10 cơ sở hợp lệ cho n hợp số lẻ, cận xác suất qua tất cả là bao nhiêu?

*Đáp án:* Không quá `(1/4)^{10}=1/1.048.576` trong mô hình xác suất nêu ở bài.

**Bài 15 — lặp cơ sở.** Kiểm tra base 2 mười lần có được dùng cận `4^{-10}` không?

*Đáp án:* Không, mười vòng cùng base không độc lập.

**Bài 16 — base chia hết cho n.** Nếu `a mod n=0`, đó có phải witness không?

*Đáp án:* Không. Bỏ qua cơ sở này; đừng diễn giải pass thành chứng cứ nguyên tố.

**Bài 17 — overflow.** Vì sao `(a*b)%n` có thể sai trong Java long dù a,b<n?

*Đáp án:* Tích a*b có thể vượt Long.MAX_VALUE **trước** khi lấy modulo; BigInteger hoặc mulMod đúng mới an toàn.

**Bài 18 — API.** `BigInteger.isProbablePrime(certainty)` có tự cung cấp chứng chỉ toán học không?

*Đáp án:* Không. Tên API và hợp đồng là probable prime với mức tin cậy tương ứng.

**Bài 19 — 64-bit.** Vì sao thử bảy cơ sở `2,3,5,7,11,13,17` chưa đủ cho mọi số 64-bit?

*Đáp án:* Hợp số 341550071728321 vượt tất cả các cơ sở đó; cần bộ chứng nhận đủ miền.

**Bài 20 — oracle.** Vì sao kiểm tra 20.001 số nhỏ chưa đủ để khẳng định không có lỗi trên 10^18?

*Đáp án:* Những lỗi tràn số/chọn cơ sở chỉ xuất hiện ở giá trị lớn; cần kiểm tra đối kháng và dựa vào chứng minh/giới hạn bộ cơ sở.

**Bài 21 — sản phẩm.** Một ứng dụng sinh RSA prime hàng trăm bit có nên gọi thẳng `isPrimeDeterministic(long n)` không?

*Đáp án:* Không; signed long không chứa nổi n. Cần BigInteger, sinh số lớn, kiểm tra xác suất/kiểm chứng thích hợp và quy trình mật mã tin cậy. Bài này không phải một bộ sinh RSA key hoàn chỉnh.

**Bài 22 — lựa chọn thuật toán.** Cần đánh dấu tất cả nguyên tố từ 1 tới một triệu, có nên gọi Miller–Rabin một triệu lần không?

*Đáp án:* Sàng Eratosthenes thường phù hợp hơn cho cả miền liên tục, vì xây một lần rồi truy vấn nhanh.

## 16. Checklist trước khi nộp lời giải

1. **Xác định miền n:** số âm, 0,1,2, số chẵn, signed long hay BigInteger.
2. **Tách n−1 chính xác** thành 2^s·d với d lẻ; chú ý n>2 trước.
3. **Dùng modPow**, không tính lũy thừa nguyên đầy đủ.
4. **Không nhân long trực tiếp** khi bình phương mô-đun n lớn.
5. **Hiểu nghĩa witness:** true = đã chứng minh hợp số; false ở một cơ sở = chưa kết luận.
6. **Đừng thay “pass một cơ sở” bằng “nguyên tố”**.
7. **Chọn cơ sở đúng mục tiêu:** random độc lập cho probabilistic; bộ đã chứng nhận nếu muốn deterministic theo miền.
8. **Đừng lẫn bảy cơ sở đặc biệt** với bảy cơ sở nguyên tố đầu tiên.
9. **Cẩn thận a mod n=0**, đó là cơ sở không có thông tin.
10. **Không áp dụng bộ 64-bit cho BigInteger quá miền** mà không có bảo đảm.
11. **Lọc các số nguyên tố nhỏ** trước để giảm chi phí và xử lý biên.
12. **Chỉ gọi “probably prime”** với trường hợp xác suất; không quảng cáo là chứng chỉ.
13. **Test số nhỏ bằng chia thử**, rồi test hợp số lớn có cấu trúc và strong pseudoprimes.
14. **Nếu cần chắc chắn trong sản xuất**, dùng thư viện/thuật toán phù hợp, xác nhận miền và benchmark trước khi tối ưu.

## Ghi nhớ

- Miller–Rabin dựa vào `n−1=2^s d` và chuỗi `a^d,a^{2d},...,a^{2^s d} (mod n)`.
- Với n nguyên tố, `a^d≡1` hoặc một giá trị `a^{2^r d}≡−1` phải xuất hiện trước khi chuỗi đi tới 1. Cơ sở vi phạm là **witness chứng minh hợp số**.
- Một hợp số có thể **vượt qua một hay nhiều cơ sở**, nên lựa chọn cơ sở quyết định độ tin cậy.
- **k cơ sở ngẫu nhiên, đều, độc lập** cho cận lỗi không quá `4^{-k}` đối với một số lẻ hợp số; điều đó **không** áp dụng cho lịch cơ sở cố định tùy ý.
- Bộ đặc biệt `{2,325,9375,28178,450775,9780504,1795265022}` đủ để kiểm tra **tất định số nguyên dưới 2^64** khi số học mô-đun đúng; chương trình Java hỗ trợ **n dương thuộc signed long**.
- `BigInteger.modPow` và `BigInteger.multiply(...).mod(...)` tránh lỗi tràn long.
- Bộ kiểm chứng độc lập gồm **20.001 giá trị nhỏ và 3.000 hợp số lẻ lớn**, cùng các phản ví dụ strong pseudoprime. Nó xác nhận hành vi triển khai trên các ca đã thử, **không thay thế chứng nhận toán học của bộ cơ sở**.
