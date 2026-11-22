# Giải hệ đồng dư bằng định lý phần dư Trung Hoa

**Định lý phần dư Trung Hoa** (*Chinese Remainder Theorem*, viết tắt **CRT**) là công cụ số học để giải đồng thời nhiều điều kiện về số dư của **cùng một số nguyên x**. Thay vì thử từng x, ta dùng quan hệ giữa các môđun, **ước chung lớn nhất (gcd)**, **nghịch đảo môđun** và **thuật toán Euclid mở rộng** để xác định hệ có nghiệm hay không, rồi tính một nghiệm chuẩn và **chu kỳ của toàn bộ nghiệm**.

Bài này thuộc nhóm **Thuật toán số học**. Trọng tâm không chỉ là công thức CRT cho các môđun **đôi một nguyên tố cùng nhau** (*pairwise coprime*), mà còn là **CRT tổng quát**: các môđun có thể chia sẻ ước chung, khi đó một số hệ **vô nghiệm**, còn hệ có nghiệm thì mọi nghiệm tạo thành **một lớp đồng dư duy nhất modulo bội chung nhỏ nhất (lcm)**.

Sau bài học, bạn cần làm được bốn việc:

1. Chuyển bài toán chia có dư thành hệ đồng dư, chuẩn hóa số dư âm đúng cách.
2. Phân biệt CRT cổ điển cho môđun đôi một nguyên tố cùng nhau và **gộp từng cặp** để giải hệ tổng quát.
3. Chứng minh chính xác điều kiện có nghiệm: `gcd(m,n)` phải chia hết `b−a` khi gộp hai phương trình.
4. Cài đặt Java 17+ bằng **BigInteger** để tránh tràn số, dùng Euclid mở rộng tìm nghịch đảo, trả **vô nghiệm** hoặc `x ≡ r (mod M)`, và kiểm thử bằng vét cạn trên các môđun nhỏ.

**Giả thiết và quy ước của bài:** Các môđun `m_i` là **số nguyên dương**; số dư `a_i` có thể âm hoặc vượt môđun và luôn được chuẩn hóa về `[0,m_i)`. Môđun 1 hợp lệ, môđun 0 hoặc âm bị **từ chối ở API Java mẫu**. Chuỗi kết quả `x ≡ r (mod M)` nghĩa là **toàn bộ nghiệm nguyên** là `x=r+kM` với `k∈ℤ`, trong đó `0≤r<M` và `M>0`. Không bao giờ mặc định kết quả chỉ có một số nguyên duy nhất.

## 1. Đồng dư và phép chia có dư

Với môđun dương m, ta định nghĩa:

```text
a ≡ b (mod m)
khi và chỉ khi m chia hết (a - b).

Ký hiệu tương đương:
m | (a - b)
```

Ví dụ:

```text
17 ≡ 2  (mod 5)     vì 17-2=15 chia hết cho 5
-1 ≡ 4  (mod 5)     vì -1-4=-5 chia hết cho 5
23 ≡ 2  (mod 7)     vì 23-2=21 chia hết cho 7
```

Mỗi điều kiện `x ≡ a (mod m)` tương đương với:

```text
x = a + k*m
với k là một số nguyên tùy ý.
```

Nghĩa là một phương trình đồng dư riêng lẻ có **vô hạn nghiệm nguyên**, nhưng các nghiệm cùng thuộc một lớp theo modulo m.

### 1.1. Hệ đồng dư

Một hệ k phương trình có dạng:

```text
x ≡ a1 (mod m1)
x ≡ a2 (mod m2)
...
x ≡ ak (mod mk)

với m1, m2, ..., mk > 0.
```

Ta cần tìm **một số nguyên x thỏa mãn tất cả**, hoặc kết luận **không có x nào**; nếu có nghiệm thì mô tả **toàn bộ nghiệm** bằng một lớp đồng dư chuẩn.

Ví dụ kinh điển:

```text
x ≡ 2 (mod 3)
x ≡ 3 (mod 5)
x ≡ 2 (mod 7)
```

Nghiệm không âm nhỏ nhất là **23**:

```text
23 mod 3 = 2
23 mod 5 = 3
23 mod 7 = 2
```

Các nghiệm khác là 23+105k với k∈ℤ. Số **105** không phải ngẫu nhiên: đó là `lcm(3,5,7)=3×5×7`.

### 1.2. Vì sao phải chuẩn hóa số dư?

Một số dư được ghi `-1 (mod 5)` và số dư `4 (mod 5)` là **cùng một điều kiện**. Để tính toán và so sánh dễ hơn, dùng đại diện chuẩn:

```text
aNormalized = a mod m
0 <= aNormalized < m
```

Trong Java:

```java
BigInteger normalized = a.mod(m); // yêu cầu m > 0
```

**Phân biệt `mod` với `remainder`:** Với số âm, toán tử `%` trên int/long và `BigInteger.remainder` có thể cho số dư âm. Ví dụ `-1 % 5 = -1` trong Java, trong khi `BigInteger.valueOf(-1).mod(BigInteger.valueOf(5)) = 4`.

Không được chỉ viết `a % m` rồi mặc định kết quả luôn ở khoảng [0,m).

## 2. CRT cổ điển: các môđun đôi một nguyên tố cùng nhau

Hai số nguyên dương m,n **nguyên tố cùng nhau** khi:

```text
gcd(m,n) = 1
```

Một danh sách môđun **đôi một nguyên tố cùng nhau** khi **mọi cặp chỉ số khác nhau** có gcd bằng 1:

```text
gcd(mi,mj) = 1 cho mọi i != j.
```

Đây là giả thiết **mạnh hơn** điều kiện gcd của cả danh sách bằng 1. Ví dụ `gcd(6,10,15)=1` nhưng `gcd(6,10)=2`, nên 6,10,15 **không đôi một nguyên tố cùng nhau**.

**Định lý CRT cổ điển:** Nếu các môđun `m1,...,mk` đôi một nguyên tố cùng nhau, hệ đồng dư **luôn có nghiệm với mọi bộ số dư**, và có **đúng một lớp nghiệm modulo**

```text
M = m1 * m2 * ... * mk.
```

Từ “duy nhất” ở đây nghĩa là một **đại diện chuẩn r trong [0,M)**, không phải một số nguyên x duy nhất trên ℤ.

### 2.1. Công thức dựng nghiệm trực tiếp

Đặt:

```text
M  = product(mi)
Mi = M / mi
yi = inverse(Mi modulo mi)

x = (sum ai*Mi*yi) modulo M
```

Vì các môđun đôi một nguyên tố cùng nhau:

```text
gcd(Mi, mi) = 1
```

nên tồn tại nghịch đảo `yi` sao cho:

```text
Mi * yi ≡ 1 (mod mi).
```

Khi xét một môđun `mj` cố định:

- Hạng j đóng góp `aj*Mj*yj ≡ aj (mod mj)`.
- Với mọi i≠j, `Mi` chứa thừa số `mj`, nên `ai*Mi*yi ≡ 0 (mod mj)`.

Vì vậy tổng thỏa mãn chính xác mọi phương trình.

**Chú ý môđun bằng 1:** Hệ `x≡a (mod 1)` không ràng buộc x. Trong hiện thực công thức tích, bỏ qua phương trình mod1 hoặc coi đóng góp bằng 0; không yêu cầu tìm nghịch đảo trong modulo1 vì “nghịch đảo môđun 1” không phải thao tác chuẩn cần dùng. Thuật toán gộp cặp phần sau xử lý mod1 tự nhiên hơn.

### 2.2. Ví dụ đầy đủ cho 3,5,7

Hệ:

```text
x ≡ 2 (mod 3)
x ≡ 3 (mod 5)
x ≡ 2 (mod 7)
```

Ta có:

```text
M = 3*5*7 = 105

i=1:
    M1 = 105/3 = 35
    35 mod 3 = 2
    inverse(2 modulo 3) = 2
    term1 = 2*35*2 = 140

i=2:
    M2 = 105/5 = 21
    21 mod 5 = 1
    inverse(1 modulo 5) = 1
    term2 = 3*21*1 = 63

i=3:
    M3 = 105/7 = 15
    15 mod 7 = 1
    inverse(1 modulo 7) = 1
    term3 = 2*15*1 = 30

sum = 140 + 63 + 30 = 233

233 mod 105 = 23
```

Kết luận:

```text
x ≡ 23 (mod 105)

Tập nghiệm:
x = 23 + 105*k, k thuộc Z.
```

Phép kiểm tra độc lập là thay 23 vào cả ba phương trình. Với nghiệm chuẩn 23, mỗi phương trình đều đúng.

### 2.3. Vì sao chu kỳ là tích các môđun?

Nếu x và y cùng thỏa hệ, thì:

```text
mi | (x - y) cho mọi i.
```

Khi các mi **đôi một nguyên tố cùng nhau**, tích M cũng chia `x−y`. Vì vậy x≡y (mod M): tất cả nghiệm có cùng số dư modulo M.

Ngược lại, nếu x là một nghiệm, thì x+kM cũng là nghiệm vì M chia hết từng mi. Do đó tất cả nghiệm là một lớp modulo M.

## 3. CRT tổng quát: các môđun có thể chung ước

Khi hai môđun không nguyên tố cùng nhau, **không phải mọi cặp số dư đều tương thích**.

Xét hai phương trình:

```text
x ≡ a (mod m)
x ≡ b (mod n)

m > 0, n > 0.
```

**Định lý gộp cặp tổng quát:**

Đặt `g=gcd(m,n)`. Hệ có nghiệm **khi và chỉ khi**

```text
g | (b - a)
```

hay tương đương:

```text
a ≡ b (mod g).
```

Nếu có nghiệm, tập nghiệm là **một lớp đồng dư duy nhất modulo**

```text
L = lcm(m,n) = m*(n/g).
```

Nếu không thỏa điều kiện chia hết, hệ **vô nghiệm**.

### 3.1. Ví dụ tương thích dù hai môđun chung ước

```text
x ≡ 2 (mod 6)
x ≡ 8 (mod 14)
```

Ta có `gcd(6,14)=2` và `8−2=6` chia hết cho 2, nên tồn tại nghiệm.

Nghiệm chuẩn:

```text
x ≡ 8 (mod 42)
```

Kiểm tra:

```text
8 mod 6  = 2
8 mod 14 = 8

lcm(6,14)=42.
```

Các nghiệm: 8,50,92,134,... và 8−42=−34,... Đây là **một lớp modulo42**, không phải modulo84=6×14.

### 3.2. Ví dụ vô nghiệm

```text
x ≡ 1 (mod 6)
x ≡ 2 (mod 14)
```

Vì `g=2` nhưng `b−a=1` không chia hết 2, không thể có x nào thỏa đồng thời.

Có thể nhìn bằng tính chẵn lẻ:

- x≡1(mod6) buộc x **lẻ**.
- x≡2(mod14) buộc x **chẵn**.

Mâu thuẫn, nên hệ vô nghiệm.

**Không được dùng công thức CRT tích các môđun và cố tính nghịch đảo trong trường hợp này.** Nghịch đảo không tồn tại sẽ là dấu hiệu giả thiết sai; vấn đề quan trọng là **kiểm tra tính tương thích trước**.

## 4. Suy ra công thức gộp cặp từng bước

Đây là thuật toán quan trọng nhất của bài, xử lý cả trường hợp đôi một nguyên tố cùng nhau lẫn trường hợp có chung ước.

Giả sử đang có:

```text
x ≡ a (mod m)
x ≡ b (mod n)
```

Bước 1. Từ phương trình đầu:

```text
x = a + m*t, với t thuộc Z.
```

Bước 2. Thay vào phương trình thứ hai:

```text
a + m*t ≡ b (mod n)

m*t ≡ b-a (mod n).
```

Đặt:

```text
delta = b-a
g = gcd(m,n).
```

Bước 3. Điều kiện tồn tại t là `g|delta`. Nếu `delta mod g != 0`, kết luận **INCONSISTENT**.

Bước 4. Nếu chia hết, đặt:

```text
m' = m/g
n' = n/g
d' = delta/g
```

Ta thu được:

```text
m' * t ≡ d' (mod n').
```

Vì `gcd(m',n')=1`, số `m'` có nghịch đảo theo modulo n' khi n'>1.

Bước 5. Tìm nghịch đảo `inv` của m' theo modulo n':

```text
m' * inv ≡ 1 (mod n').

t ≡ d' * inv (mod n').
```

Chọn đại diện `t0` trong [0,n').

Bước 6. Tính:

```text
L = lcm(m,n) = m*n'

r = (a + m*t0) mod L
```

Kết quả:

```text
x ≡ r (mod L), 0 <= r < L.
```

**Trường hợp đặc biệt `n'=1`:** Phương trình rút gọn theo modulo1 luôn đúng, không cần tìm nghịch đảo. Chọn t0=0, rồi chuẩn hóa r=a mod L. Đây là cách xử lý tự nhiên khi môđun mới n đã là một ước của m và điều kiện tương thích.

### 4.1. Tính tay ví dụ môđun 6 và 14

```text
a=2, m=6
b=8, n=14

g=gcd(6,14)=2
delta=8-2=6
6 chia hết cho 2 => tương thích.

m'=6/2=3
n'=14/2=7
d'=6/2=3

3*t ≡ 3 (mod 7)

inverse(3 modulo 7)=5, vì 3*5=15≡1 mod7.

t ≡ 3*5 ≡ 15 ≡ 1 (mod 7)

L = 6*7=42

r = 2 + 6*1 = 8

Kết quả:
x ≡ 8 (mod 42).
```

### 4.2. Tính tay ví dụ số dư âm

```text
x ≡ -1 (mod 5)
x ≡  2 (mod 3)
```

Chuẩn hóa:

```text
-1 (mod 5) = 4 (mod 5)

a=4, m=5
b=2, n=3

g=1
delta=2-4=-2
m'=5, n'=3
inverse(5 modulo 3)
 = inverse(2 modulo 3)
 = 2

t ≡ (-2)*2 = -4 ≡ 2 (mod 3)

L = 5*3 = 15
r = 4+5*2 = 14

x ≡ 14 (mod 15).
```

Trong Java, phải dùng phép `mod` của BigInteger để đưa kết quả âm như −4 về số dư không âm 2.

### 4.3. Tại sao cần chia môđun trước khi lấy nghịch đảo?

Phương trình `m*t≡delta (mod n)` chỉ có thể giải bằng nghịch đảo của m modulo n khi `gcd(m,n)=1`. Khi g>1, nghịch đảo đó **không tồn tại**.

Vì vậy ta kiểm tra `g|delta`, rồi chia cả m,n,delta cho g. Khi ấy m' và n' nguyên tố cùng nhau và có nghịch đảo hợp lệ. Không thể bỏ bước chia g và gọi modInverse trên m,n ban đầu.

## 5. Euclid mở rộng và nghịch đảo môđun

### 5.1. Nghịch đảo môđun là gì?

Cho số nguyên a và môđun dương m>1. Một số nguyên inv là **nghịch đảo của a modulo m** nếu:

```text
a*inv ≡ 1 (mod m).
```

Nghịch đảo tồn tại **khi và chỉ khi**:

```text
gcd(a,m)=1.
```

Ví dụ:

```text
inverse(3 modulo 7)=5
3*5=15≡1(mod7).

inverse(2 modulo 4) KHÔNG TỒN TẠI
vì gcd(2,4)=2.
```

### 5.2. Đồng nhất thức Bézout

**Thuật toán Euclid mở rộng** trả một bộ:

```text
g = gcd(a,b)
x, y thuộc Z
a*x + b*y = g.
```

Nếu g=1:

```text
a*x + b*y = 1
=> a*x ≡ 1 (mod b)
=> x là một nghịch đảo của a modulo b.
```

Lấy `x mod b` để được nghịch đảo chuẩn trong [0,b).

Ví dụ:

```text
30*(-1)+18*(2)=6
gcd(30,18)=6.
```

Đối với hai môđun đã rút gọn m',n', ta biết gcd=1; nếu Euclid mở rộng trả hệ số x của m' thì `x mod n'` là nghịch đảo cần dùng.

### 5.3. Vì sao mã dùng BigInteger thay vì long?

CRT có thể tạo chu kỳ:

```text
M = lcm(m1,...,mk)
```

lớn hơn nhiều mọi môđun riêng lẻ. Với môđun đôi một nguyên tố cùng nhau, chu kỳ là tích của chúng. Ngay cả khi từng môđun vừa kiểu long, tích nhiều môđun có thể tràn long.

BigInteger cho phép cộng/nhân/chia/gcd/mod chính xác trên số nguyên lớn, giới hạn thực tế bởi bộ nhớ và thời gian. Mã tránh dùng một sentinel số như −1 hoặc Long.MAX_VALUE để đánh dấu vô nghiệm: dùng **Optional.empty()** để biểu diễn không có lớp nghiệm.

**Nhớ rằng BigInteger bất biến.** Các hàm `add`, `multiply`, `divide`, `mod` trả về giá trị mới; chúng không sửa đối tượng cũ. BigInteger.mod yêu cầu môđun **dương**.

## 6. Giải hệ nhiều phương trình bằng cách gộp liên tiếp

Với hệ nhiều điều kiện, thuật toán đơn giản và thống nhất nhất là **merge** từng phương trình vào một kết quả đang có.

Khởi đầu bằng hệ rỗng:

```text
current: x ≡ 0 (mod 1)
```

Vì mọi số nguyên đều đồng dư 0 modulo1, trạng thái này biểu diễn tập nghiệm của **không có ràng buộc nào**.

Với từng phương trình `x≡ai (mod mi)`:

1. Chuẩn hóa `ai=ai mod mi`, xác nhận mi>0.
2. Gộp `current` với phương trình mới bằng công thức ở phần 4.
3. Nếu `gcd(current.modulus,mi)` không chia hiệu hai số dư, dừng: **INCONSISTENT**.
4. Nếu tương thích, thay `current` bằng lớp nghiệm chuẩn modulo lcm hai môđun.

Sau khi hết phương trình, current biểu diễn **chính xác toàn bộ nghiệm hệ**.

### 6.1. Giả mã đầy đủ

```text
CRT_GENERAL(equations):
    current = (residue=0, modulus=1)

    for each (b,n) in equations:
        require n > 0
        b = b mod n

        (a,m) = current

        g = gcd(m,n)
        delta = b-a

        if delta is not divisible by g:
            return NO_SOLUTION

        mr = m/g
        nr = n/g

        if nr == 1:
            t = 0
        else:
            inv = inverse(mr modulo nr)
            t = ((delta/g)*inv) mod nr

        L = m*nr
        r = (a+m*t) mod L
        current = (r,L)

    return current
```

**Không cần kiểm tra tính nguyên tố của các môđun.** Điều kiện của CRT là gcd và tính tương thích, không phải tất cả môđun đều là số nguyên tố.

### 6.2. Ví dụ gộp ba phương trình không đôi một coprime

Hệ:

```text
x ≡ 2 (mod 6)
x ≡ 8 (mod 14)
x ≡ 2 (mod 15)
```

Sau hai phương trình đầu:

```text
current: x ≡ 8 (mod 42)
```

Gộp với x≡2(mod15):

```text
a=8,m=42
b=2,n=15

g=gcd(42,15)=3
delta=2-8=-6
-6 chia hết cho 3 => tương thích

mr=42/3=14
nr=15/3=5
d'=-6/3=-2

14*t ≡ -2 (mod5)
4*t ≡ 3 (mod5)
inverse(4 modulo5)=4

t ≡ (-2)*4 = -8 ≡ 2 (mod5)

L=42*5=210
r=8+42*2=92
```

Kết quả:

```text
x ≡ 92 (mod 210)

92 mod 6  = 2
92 mod 14 = 8
92 mod 15 = 2
```

Ở bước cuối, môđun kết quả là **210=lcm(6,14,15)**, không phải `6×14×15=1260`.

### 6.3. Tại sao gộp dần không làm mất nghiệm?

Giả sử current là **toàn bộ nghiệm** của các phương trình đã xử lý:

```text
x ≡ a (mod m)
```

Một số x thỏa toàn bộ hệ cũ **khi và chỉ khi** x thuộc lớp a mod m. Thêm một điều kiện `x≡b(mod n)` tương đương lấy **giao của hai lớp đồng dư**. Thuật toán merge tính chính xác giao ấy (rỗng nếu bất tương thích, hoặc một lớp modulo lcm nếu tương thích). Vì vậy current mới vẫn tương đương toàn bộ hệ đã xử lý.

Dùng quy nạp theo số phương trình, sau vòng cuối, kết quả là đúng cho cả hệ. **Đây là lý do có thể gộp bằng một vòng lặp mà không cần giải toàn hệ từ đầu mỗi lần.**

## 7. Chứng minh điều kiện g|b−a là cần và đủ

Xét:

```text
x ≡ a (mod m)
x ≡ b (mod n).
```

### 7.1. Tính cần thiết

Nếu x là nghiệm thì tồn tại s,t∈ℤ:

```text
x=a+m*s=b+n*t

b-a=m*s-n*t.
```

Số g=gcd(m,n) chia m và n, nên chia cả vế phải `m*s−n*t`. Vậy:

```text
g | (b-a).
```

Nếu điều này sai, hệ chắc chắn **không thể có nghiệm**.

### 7.2. Tính đủ

Giả sử g chia b−a. Đặt m'=m/g, n'=n/g, d'=(b−a)/g. Ta có gcd(m',n')=1.

Theo Bézout, tồn tại u,v∈ℤ:

```text
m'*u + n'*v = 1.
```

Nhân hai vế với d':

```text
m'*(d'*u) + n'*(d'*v) = d'.
```

Lấy modulo n':

```text
m'*(d'*u) ≡ d' (mod n').
```

Vì vậy t=d'*u là một nghiệm cho phương trình rút gọn. Thay x=a+m*t sẽ thỏa đồng thời x≡a(mod m) và x≡b(mod n). Hệ **có nghiệm**.

### 7.3. Tính duy nhất modulo lcm

Nếu x,y đều là nghiệm, m và n đều chia x−y. Do đó:

```text
lcm(m,n) | (x-y).
```

Ngược lại, nếu x là nghiệm, mọi số x+k*lcm(m,n) cũng thỏa hai phương trình. Bởi vậy tất cả nghiệm là **một lớp modulo lcm**, và có đúng một đại diện chuẩn trong `[0,lcm)`.

### 7.4. Mở rộng cho toàn hệ

Một hệ nhiều phương trình có nghiệm **khi và chỉ khi** từng cặp số dư phù hợp modulo gcd của hai môđun:

```text
ai ≡ aj (mod gcd(mi,mj))
cho mọi cặp i,j.
```

Thuật toán gộp dần tránh phải kiểm tra tất cả O(k²) cặp riêng rẽ: ở mỗi bước, nó kiểm tra tương thích giữa **lớp nghiệm đã gộp** và điều kiện mới, rồi cập nhật. Nếu hoàn tất, kết quả là một lớp modulo `lcm(m1,...,mk)`.

**Điều dễ nhầm:** `gcd(m1,...,mk)=1` **không đủ** để áp dụng công thức tích hay kết luận mọi bộ số dư đều có nghiệm. Phải là **đôi một nguyên tố cùng nhau** đối với CRT cổ điển, hoặc dùng điều kiện tương thích của CRT tổng quát.

## 8. Các trường hợp biên quan trọng

### 8.1. Môđun bằng 1

```text
x ≡ 123 (mod 1)
x ≡ -999 (mod 1)
```

Mọi số nguyên đều thỏa vì mọi số dư đều chuẩn hóa thành 0 modulo1. Gộp hai điều kiện cho:

```text
x ≡ 0 (mod 1).
```

Trong thuật toán merge, nếu n'=1, chọn t=0 vì phương trình rút gọn modulo1 luôn đúng.

### 8.2. Hệ rỗng

Không có phương trình nào thì **mọi số nguyên** đều hợp lệ. Để giữ cùng kiểu biểu diễn, ta trả:

```text
x ≡ 0 (mod 1).
```

Đây là một quy ước thuận tiện cho API. Nó không có nghĩa là hệ rỗng chỉ có nghiệm x=0.

### 8.3. Hai môđun bằng nhau

```text
x ≡ 17 (mod 12)
x ≡ -7 (mod 12)
```

Hai số dư chuẩn đều bằng 5:

```text
17 mod 12 = 5
-7 mod 12 = 5
```

Nên hệ tương thích và kết quả:

```text
x ≡ 5 (mod 12).
```

Ngược lại:

```text
x ≡ 1 (mod 4)
x ≡ 2 (mod 4)
```

không thể đồng thời đúng, nên vô nghiệm.

### 8.4. Môđun này chia hết môđun kia

Ví dụ:

```text
x ≡ 5 (mod 12)
x ≡ 1 (mod 4)
```

Vì 12 chia hết 4 và 5 mod4=1, điều kiện mod4 **không bổ sung ràng buộc mới**. Kết quả vẫn là x≡5(mod12).

Nếu điều kiện thứ hai là x≡2(mod4), chúng mâu thuẫn: không tồn tại nghiệm.

### 8.5. Số dư âm hoặc lớn hơn môđun

```text
x ≡ -1 (mod 5)  tương đương x ≡ 4 (mod 5)
x ≡ 17 (mod 12) tương đương x ≡ 5 (mod 12)
```

Việc chuẩn hóa không thay đổi tập nghiệm. **Không phải** phải thêm một phương trình x≥0 để số dư không âm; chuẩn hóa số dư chỉ là chọn đại diện thuận tiện cho cùng lớp đồng dư.

### 8.6. Môđun 0 hoặc âm

Trong toán học, có thể dùng cách nói khác cho “chia hết bởi 0” hoặc đưa môđun âm về trị tuyệt đối, nhưng trong **định nghĩa thuật toán và API này**, ta **chỉ nhận môđun dương**.

- m=0: từ chối, không tính BigInteger.mod(0).
- m<0: từ chối ở đầu vào, không âm thầm đổi thành |m|.

Quy ước nhất quán giúp tránh các lỗi khó theo dõi trong modulo và nghịch đảo.

### 8.7. Nhiều nghiệm trong một đoạn [L,R]

Sau khi tính được lớp `x≡r(mod M)`, toàn bộ nghiệm có dạng `r+kM`. Nếu cần chỉ những nghiệm nằm trong [L,R], tìm các số nguyên k sao cho:

```text
L <= r+k*M <= R.
```

Vì M>0:

```text
ceil((L-r)/M) <= k <= floor((R-r)/M).
```

Đếm số nguyên k trong đoạn trên; nếu cận dưới lớn hơn cận trên, không có nghiệm trong khoảng dù hệ tổng quát có nghiệm.

**Khi lập trình:** Chú ý phép chia nguyên của Java đối với số âm là làm tròn **về 0**, không tự động là floor/ceil toán học. Với BigInteger, có thể viết floorDiv/ceilDiv đúng theo dấu và dùng chúng để tính cận; không lấy đơn giản `(L-r)/M` cho mọi số âm nếu cần kết quả chính xác.

### 8.8. Tìm nghiệm dương nhỏ nhất

Nếu kết quả chuẩn `r∈[0,M)`:

- Nếu r>0, nghiệm nguyên dương nhỏ nhất là **r**.
- Nếu r=0, nghiệm nguyên dương nhỏ nhất là **M**, vì 0 không phải số dương.

Nếu đề yêu cầu **không âm**, nghiệm nhỏ nhất luôn là r. Phải đọc rõ định nghĩa “dương” hay “không âm” trước khi in.

## 9. Chương trình Java 17+ hoàn chỉnh

Tên tệp: **`ChineseRemainderTheoremDemo.java`**.

Bản cài đặt dùng:

- `record Congruence(BigInteger residue, BigInteger modulus)`: validate môđun dương, chuẩn hóa residue về [0,m).
- `extendedGcd(a,b)`: Euclid mở rộng trả gcd không âm và các hệ số Bézout.
- `merge(first,second)`: CRT tổng quát cho hai lớp; trả Optional.empty nếu điều kiện gcd không thỏa.
- `solve(List<Congruence>)`: bắt đầu từ x≡0(mod1), gộp mọi phương trình; trả một lớp nghiệm chuẩn hoặc không có nghiệm.
- `verify(solution,equations)`: tự kiểm tra rằng nghiệm chuẩn đúng với mọi phương trình.
- `bruteSmall(equations)`: **oracle độc lập** cho hệ nhỏ, liệt kê mọi x trong [0,lcm) bằng toán tử trên long; chỉ dùng với môđun nhỏ bảo đảm không tràn.
- `randomizedCrossCheck()`: sinh 800 hệ ngẫu nhiên, trong đó một phần **chắc chắn tương thích** từ một nghiệm ẩn, phần còn lại ngẫu nhiên không có bảo đảm; đối chiếu kết quả CRT với oracle vét cạn, gồm hệ rỗng, môđun1, môđun trùng, môđun chung ước, số dư âm.
- Một ca BigInteger có **môđun kết quả 81 chữ số**, chứng minh tránh tràn long.

Mã không dùng `BigInteger.modInverse` trực tiếp: nó tự xây nghịch đảo từ kết quả Euclid mở rộng để giải thích rõ cơ chế lý thuyết.

### 9.1. Mã Java 17 độc lập

```java
import java.math.BigInteger;
import java.util.*;

public class ChineseRemainderTheoremDemo {
    static final BigInteger ZERO = BigInteger.ZERO;
    static final BigInteger ONE = BigInteger.ONE;

    record Congruence(BigInteger residue, BigInteger modulus) {
        Congruence {
            Objects.requireNonNull(residue, "residue");
            Objects.requireNonNull(modulus, "modulus");
            if (modulus.signum() <= 0) {
                throw new IllegalArgumentException(
                        "modulus must be positive");
            }
            residue = residue.mod(modulus);
        }
    }

    record Bezout(BigInteger gcd, BigInteger x, BigInteger y) {}

    // Euclidean algorithm with Bezout coefficients:
    // a*x + b*y = gcd(a,b), gcd >= 0.
    static Bezout extendedGcd(BigInteger a, BigInteger b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        BigInteger oldR = a, r = b;
        BigInteger oldS = ONE, s = ZERO;
        BigInteger oldT = ZERO, t = ONE;

        while (!r.equals(ZERO)) {
            BigInteger quotient = oldR.divide(r);

            BigInteger nr = oldR.subtract(quotient.multiply(r));
            oldR = r;
            r = nr;

            BigInteger ns = oldS.subtract(
                    quotient.multiply(s));
            oldS = s;
            s = ns;

            BigInteger nt = oldT.subtract(
                    quotient.multiply(t));
            oldT = t;
            t = nt;
        }

        if (oldR.signum() < 0) {
            oldR = oldR.negate();
            oldS = oldS.negate();
            oldT = oldT.negate();
        }
        return new Bezout(oldR, oldS, oldT);
    }

    static Optional<Congruence> merge(
            Congruence first, Congruence second) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");

        BigInteger a = first.residue();
        BigInteger m = first.modulus();
        BigInteger b = second.residue();
        BigInteger n = second.modulus();

        BigInteger g = m.gcd(n);
        BigInteger difference = b.subtract(a);
        if (!difference.mod(g).equals(ZERO)) {
            return Optional.empty();
        }

        BigInteger mReduced = m.divide(g);
        BigInteger nReduced = n.divide(g);
        BigInteger k;

        if (nReduced.equals(ONE)) {
            // No restriction on k modulo 1.
            k = ZERO;
        } else {
            Bezout bezout =
                    extendedGcd(mReduced, nReduced);
            if (!bezout.gcd().equals(ONE)) {
                throw new AssertionError(
                        "reduced moduli must be coprime");
            }
            BigInteger inverse =
                    bezout.x().mod(nReduced);
            k = difference.divide(g)
                    .multiply(inverse)
                    .mod(nReduced);
        }

        BigInteger lcm = m.multiply(nReduced);
        BigInteger answer = a.add(m.multiply(k)).mod(lcm);
        return Optional.of(new Congruence(answer, lcm));
    }

    static Optional<Congruence> solve(
            List<Congruence> equations) {
        Objects.requireNonNull(equations, "equations");

        // Empty system: every integer is valid, i.e. x=0 mod 1.
        Congruence current = new Congruence(ZERO, ONE);

        for (Congruence eq : equations) {
            Objects.requireNonNull(eq, "equation");
            Optional<Congruence> merged = merge(current, eq);
            if (merged.isEmpty()) {
                return Optional.empty();
            }
            current = merged.get();
        }
        return Optional.of(current);
    }

    static Congruence c(long residue, long modulus) {
        return new Congruence(
                BigInteger.valueOf(residue),
                BigInteger.valueOf(modulus));
    }

    static String display(Optional<Congruence> value) {
        return value.map(eq -> "x = " + eq.residue()
                        + " (mod " + eq.modulus() + ")")
                .orElse("INCONSISTENT");
    }

    static boolean verify(
            Congruence solution,
            List<Congruence> equations) {
        if (solution.residue().signum() < 0
                || solution.residue()
                        .compareTo(solution.modulus()) >= 0) {
            return false;
        }
        for (Congruence eq : equations) {
            if (!solution.residue().mod(eq.modulus())
                    .equals(eq.residue())) {
                return false;
            }
        }
        return true;
    }

    static long gcdSmall(long a, long b) {
        while (b != 0) {
            long remainder = a % b;
            a = b;
            b = remainder;
        }
        return Math.abs(a);
    }

    // Independent oracle: enumerate every x modulo the lcm.
    // Only use on small moduli, so long arithmetic is exact.
    static Optional<Congruence> bruteSmall(
            List<Congruence> equations) {
        long period = 1;
        for (Congruence eq : equations) {
            long mod = eq.modulus().longValueExact();
            period = Math.multiplyExact(
                    period / gcdSmall(period, mod), mod);
        }

        long answer = -1;
        for (long x = 0; x < period; x++) {
            boolean ok = true;
            for (Congruence eq : equations) {
                long mod = eq.modulus().longValueExact();
                long residue = eq.residue().longValueExact();
                if (x % mod != residue) {
                    ok = false;
                    break;
                }
            }
            if (ok) {
                if (answer != -1) {
                    throw new AssertionError(
                            "more than one answer modulo lcm");
                }
                answer = x;
            }
        }

        if (answer == -1) {
            return Optional.empty();
        }
        return Optional.of(c(answer, period));
    }

    static void randomizedCrossCheck() {
        Random rng = new Random(20261110L);
        for (int trial = 0; trial < 800; trial++) {
            int size = rng.nextInt(6);
            long witness = rng.nextInt(101) - 50;
            boolean guaranteedCompatible = rng.nextBoolean();
            List<Congruence> equations = new ArrayList<>();

            for (int i = 0; i < size; i++) {
                long mod = 1 + rng.nextInt(9);
                long raw = guaranteedCompatible
                        ? witness + mod * (rng.nextInt(9) - 4)
                        : rng.nextInt(101) - 50;
                equations.add(c(raw, mod));
            }

            Optional<Congruence> fast = solve(equations);
            Optional<Congruence> oracle = bruteSmall(equations);

            if (!fast.equals(oracle)) {
                throw new AssertionError(
                        "trial " + trial
                        + ", equations=" + equations
                        + ", fast=" + fast
                        + ", oracle=" + oracle);
            }
            if (fast.isPresent()
                    && !verify(fast.get(), equations)) {
                throw new AssertionError(
                        "verification failed trial " + trial);
            }
        }
        System.out.println(
                "Random brute-force cross-check: PASS (800 systems)");
    }

    public static void main(String[] args) {
        System.out.println(
                "Coprime: " + display(solve(List.of(
                        c(2, 3), c(3, 5), c(2, 7)))));

        System.out.println(
                "Noncoprime compatible: "
                        + display(solve(List.of(
                                c(2, 6), c(8, 14)))));

        System.out.println(
                "Noncoprime incompatible: "
                        + display(solve(List.of(
                                c(1, 6), c(2, 14)))));

        System.out.println(
                "Chained compatible: " + display(solve(List.of(
                        c(2, 6), c(8, 14), c(2, 15)))));

        System.out.println(
                "Negative residue: " + display(solve(List.of(
                        c(-1, 5), c(2, 3)))));

        System.out.println(
                "Normalized residue -1 mod 5: "
                        + c(-1, 5).residue());

        System.out.println(
                "Duplicate compatible: "
                        + display(solve(List.of(
                                c(17, 12), c(-7, 12)))));

        System.out.println(
                "Duplicate incompatible: "
                        + display(solve(List.of(
                                c(1, 4), c(2, 4)))));

        System.out.println(
                "Only modulus 1: "
                        + display(solve(List.of(
                                c(123, 1), c(-999, 1)))));

        System.out.println(
                "No equations: "
                        + display(solve(List.of())));

        Bezout bezout = extendedGcd(
                BigInteger.valueOf(30), BigInteger.valueOf(18));
        System.out.println(
                "Extended GCD: gcd=" + bezout.gcd()
                + ", 30*x+18*y="
                + BigInteger.valueOf(30).multiply(bezout.x())
                        .add(BigInteger.valueOf(18)
                                .multiply(bezout.y())));

        BigInteger pow = BigInteger.TEN.pow(40);
        BigInteger m = pow.add(BigInteger.valueOf(7));
        BigInteger n = pow.add(BigInteger.valueOf(19));
        BigInteger hidden = BigInteger.TEN.pow(75)
                .add(new BigInteger("12345678901234567890"));
        List<Congruence> big = List.of(
                new Congruence(hidden, m),
                new Congruence(hidden, n));
        Congruence solution = solve(big).orElseThrow();
        System.out.println(
                "BigInteger: coprime=" + m.gcd(n).equals(ONE)
                + ", verified=" + verify(solution, big)
                + ", modulusDigits="
                + solution.modulus().toString().length());

        try {
            c(1, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Zero modulus rejected: " + ex.getMessage());
        }

        try {
            c(1, -5);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Negative modulus rejected: "
                            + ex.getMessage());
        }

        randomizedCrossCheck();
    }
}
```

### 9.2. Biên dịch và chạy

Lưu toàn bộ code vào **ChineseRemainderTheoremDemo.java**, dùng JDK 17 trở lên:

```bash
javac ChineseRemainderTheoremDemo.java
java ChineseRemainderTheoremDemo
```

**Stdout chính xác:**

```text
Coprime: x = 23 (mod 105)
Noncoprime compatible: x = 8 (mod 42)
Noncoprime incompatible: INCONSISTENT
Chained compatible: x = 92 (mod 210)
Negative residue: x = 14 (mod 15)
Normalized residue -1 mod 5: 4
Duplicate compatible: x = 5 (mod 12)
Duplicate incompatible: INCONSISTENT
Only modulus 1: x = 0 (mod 1)
No equations: x = 0 (mod 1)
Extended GCD: gcd=6, 30*x+18*y=6
BigInteger: coprime=true, verified=true, modulusDigits=81
Zero modulus rejected: modulus must be positive
Negative modulus rejected: modulus must be positive
Random brute-force cross-check: PASS (800 systems)
```

### 9.3. Giải thích output và các kiểm thử

**Coprime:** Với các môđun 3,5,7 đôi một nguyên tố cùng nhau, kết quả 23 modulo105. Có thể kiểm tra bằng công thức tích ở phần 2 hoặc gộp liên tiếp ở phần 6.

**Noncoprime compatible:** Môđun 6 và14 có gcd2; hiệu số dư 8−2=6 chia hết2 nên có nghiệm; chuẩn là 8 modulo42.

**Noncoprime incompatible:** Môđun 6 và14 cũng có gcd2 nhưng hiệu 2−1=1 không chia hết2; chính xác trả INCONSISTENT.

**Chained compatible:** Sau gộp hai phương trình đầu, thêm điều kiện modulo15 và nhận 92 modulo210; chứng minh rằng kết quả không chỉ đúng cho hai phương trình.

**Negative residue / Normalized:** Số dư −1 modulo5 được đưa về4. Hệ với x≡2(mod3) cho x≡14(mod15).

**Duplicate compatible:** Điều kiện 17 mod12 và −7 mod12 là cùng một lớp5 modulo12; kết quả không nhân đôi chu kỳ.

**Duplicate incompatible:** Hai số dư khác nhau modulo4 không thể cùng đúng; báo vô nghiệm.

**Only modulus1 / No equations:** Hai trường hợp đều biểu diễn **toàn bộ số nguyên** bằng x≡0(mod1); trong API, đó là nghiệm hợp lệ chứ không phải INCONSISTENT.

**Extended GCD:** Chương trình xác nhận tồn tại hệ số x,y cho `30x+18y=6`, phù hợp `gcd(30,18)=6`.

**BigInteger:** Dùng hai môđun khoảng 10⁴⁰ nguyên tố cùng nhau; lcm có **81 chữ số**, lớn hơn rất nhiều long. Kiểm tra nghiệm bằng cách thế lại vào hai phương trình, cho verified=true.

**Zero/Negative modulus rejected:** Chính sách input không nhận môđun không dương; lỗi thông báo rõ ràng.

**Random brute-force cross-check:** Bộ sinh với seed cố định tạo **800 hệ nhỏ**, mỗi hệ có 0–5 phương trình, môđun từ1 đến9, số dư có thể âm. Một nửa trường hợp được tạo dựa trên một nghiệm ẩn để chắc chắn tương thích; phần còn lại là ngẫu nhiên. Oracle tự tính lcm của các môđun nhỏ rồi **duyệt mọi x từ 0 đến lcm−1**, kiểm tra trực tiếp toàn hệ. Nó còn xác nhận nghiệm chuẩn là **duy nhất modulo lcm**. Sau đó so Optional<Congruence> từ CRT với đáp án brute force, và xác minh nghiệm bằng phép mod đối với từng phương trình. Chỉ in PASS nếu mọi hệ đều khớp.

### 9.4. Tại sao kết quả dùng Optional?

Hệ có nghiệm nhưng r=0 là **khác** với hệ vô nghiệm. Nếu dùng một số như 0 để báo lỗi, kết quả có thể bị nhầm với nghiệm hợp lệ x≡0(mod M). Trong Java:

```java
Optional<Congruence> result = solve(equations);
```

- `Optional.empty()`: hệ không có nghiệm.
- `Optional.of(Congruence(r,M))`: mọi x=r+kM, k∈ℤ đều là nghiệm.

Nếu trả cấu trúc tự định nghĩa có cờ `hasSolution` thì cũng hợp lệ. Quan trọng là **không trộn trạng thái vô nghiệm với một số dư hợp lệ**.

## 10. Phân tích độ phức tạp

Gọi k là số phương trình, và B là **số bit tối đa của các số nguyên trung gian**, đặc biệt có thể đạt khoảng số bit của `lcm(m1,...,mk)`.

### 10.1. Không phải tìm nghiệm bằng thử từng số

Brute force tìm một đại diện bằng cách thử x từ 0 đến L−1, L=lcm mọi môđun; thời gian ít nhất O(kL) phép so sánh môđun nếu kiểm tra tất cả phương trình cho từng x. L có thể cực lớn (ví dụ 81 chữ số), nên vét cạn **không phù hợp làm thuật toán chính**.

CRT gộp cặp dùng **k vòng**, mỗi vòng gồm:

- Một phép gcd.
- Một phép chia hết để kiểm tra tương thích.
- Một phép Euclid mở rộng trên môđun đã rút gọn (trừ khi n'=1).
- Một số phép cộng, trừ, nhân, chia, modulo BigInteger.

Số vòng Euclid là O(log max(m,n)) theo số bước chia của thuật toán số học thông thường. Nhưng **không được** khẳng định mọi phép BigInteger tốn O(1): cộng, nhân, chia và gcd trên các số B bit có độ phức tạp bit phụ thuộc B, cũng như thuật toán nhân/chia lớn được sử dụng trong JDK.

Nếu tạm dùng **mô hình số học đơn vị** coi phép toán trên số nguyên có chi phí O(1), có thể mô tả gộp k phương trình là khoảng:

```text
O(k * log M)
```

với M là cận lớn cho môđun trung gian. Đây là cách mô tả định tính số bước Euclid, **không phải cận thời gian bit chặt cho BigInteger**.

Trong thực tế, chương trình hoạt động đa thức theo số bit đầu vào và tăng theo kích thước của lcm; không tăng tuyến tính theo **giá trị số** của lcm như brute force.

### 10.2. Kích thước kết quả

Nếu đôi một nguyên tố cùng nhau:

```text
M = product(mi)
log2(M) = sum log2(mi).
```

Vậy số chữ số/bits của môđun kết quả có thể xấp xỉ **tổng** kích thước các môđun ban đầu. Không thể giả định kết quả luôn vừa int/long.

Nếu không đôi một nguyên tố cùng nhau:

```text
M = lcm(mi)
```

thường **nhỏ hơn tích**, đôi khi nhỏ hơn rất nhiều khi các môđun trùng hoặc chia hết nhau.

### 10.3. Bộ nhớ

Thuật toán gộp có thể chỉ giữ current, một phương trình mới và các biến trung gian nên ngoài danh sách đầu vào cần O(B) bit cho một số lượng hằng định các BigInteger lớn ở mỗi bước (tùy các giá trị trung gian). Nếu nạp sẵn toàn bộ k phương trình, bộ nhớ còn gồm tổng các BigInteger của input.

Mã kiểm thử bruteSmall không phải một phần cần thiết của solver sản xuất; nó chỉ phục vụ xác minh, và có thể tốn thời gian theo giá trị lcm.

## 11. Hai cách tiếp cận và khi nào dùng

| Trường hợp | Cách phù hợp |
| --- | --- |
| Mọi môđun đôi một nguyên tố cùng nhau | CRT cổ điển bằng tích M và nghịch đảo `Mi⁻¹` hoặc gộp cặp |
| Môđun có thể trùng/chung ước | **Gộp cặp tổng quát** với gcd và điều kiện tương thích |
| Chỉ có hai phương trình | Công thức merge trực tiếp |
| Hệ dài và không biết trước tất cả phương trình | Giữ current rồi merge thêm từng phương trình |
| Có khả năng kết quả vượt long | BigInteger; không tự ép về long |
| Chỉ cần kiểm tra hệ có nghiệm | Merge rồi dừng sớm ở bất tương thích |
| Cần nghiệm trong đoạn [L,R] | Sau CRT, giải bất đẳng thức cho k trong `r+kM` |
| Chỉ cần số lượng nghiệm trong đoạn | Đếm k nguyên thỏa cận ceil/floor |
| Môđun rất nhỏ và muốn kiểm tra code | Brute force trong một chu kỳ làm oracle |
| Nhiều hệ trên cùng bộ môđun | Có thể tiền xử lý một phần tùy ràng buộc; cần giữ tương thích ở trường hợp không coprime |

### 11.1. Có nhất thiết sử dụng công thức tích M không?

Không. Công thức tích của CRT cổ điển rất đẹp và thuận tiện khi môđun đôi một coprime. Nhưng nếu bài có môđun chung ước, **gộp cặp tổng quát** là một lựa chọn an toàn hơn vì:

- Tự kiểm tra hệ có nghiệm hay không.
- Không đòi có nghịch đảo giữa các môđun chưa rút gọn.
- Tự tính lcm thay vì nhân môđun vô điều kiện.
- Áp dụng được cho cả các môđun đôi một coprime (khi g=1 ở mỗi bước).

Một hệ có các môđun đôi một coprime thì cả hai phương pháp cho **cùng một lớp nghiệm**, có thể khác cách biểu diễn trung gian trước khi chuẩn hóa.

### 11.2. Garner's algorithm có thay thế CRT tổng quát không?

**Garner** là biến thể giải CRT bằng biểu diễn mixed-radix, thường được sử dụng khi các môđun đôi một nguyên tố cùng nhau và muốn tránh tính một tích khổng lồ trong một số bước hoặc xử lý nghiệm dưới một môđun đích khác. Nhưng phiên bản Garner cơ bản vẫn cần các nghịch đảo giữa các môđun, nên **không tự xử lý hệ bất tương thích với môđun chung ước**.

Trong bài tổng quát này, **gcd-aware merge** là phương pháp nền tảng; Garner là một hướng mở rộng khi giả thiết thích hợp đã được xác minh.

## 12. Những lỗi thường gặp

1. **Tưởng rằng mọi hệ đồng dư đều có nghiệm.** Khi môđun chung ước, số dư có thể bất tương thích.
2. **Chỉ kiểm tra gcd của toàn bộ danh sách bằng1 rồi áp CRT cổ điển.** Cần **đôi một** coprime, không chỉ gcd tổng bằng1.
3. **Không kiểm tra `gcd(m,n)|(b−a)` khi gộp.** Có thể tự dựng nghiệm cho hệ vô nghiệm.
4. **Dùng môđun kết quả là m*n trong trường hợp chung ước.** Chu kỳ đúng là lcm=m*(n/g).
5. **Lấy nghịch đảo m mod n khi gcd(m,n)>1.** Nghịch đảo không tồn tại.
6. **Quên chia m,n và b−a cho gcd trước khi lấy inverse.** Phương trình rút gọn bị sai.
7. **Đặt `m'=m/g` nhưng vẫn dùng modulo n thay vì `n'=n/g`.** Công thức t sai.
8. **Lấy nghịch đảo với n'=1.** Điều kiện modulo1 không cần nghịch đảo; chọn t0=0.
9. **Không chuẩn hóa số dư âm.** Giá trị `-1%5` trong Java bằng−1, không phải4.
10. **Dùng `BigInteger.remainder` nhưng mong kết quả luôn không âm.** Với đầu vào âm, cần `mod` của BigInteger với môđun dương.
11. **Dùng BigInteger.mod với môđun≤0.** API yêu cầu số chia dương; phải validate đầu vào.
12. **Ghi `x=23` như nghiệm duy nhất trên ℤ.** Toàn bộ nghiệm của hệ mod 105 là 23+105k.
13. **Không phân biệt nghiệm dương nhỏ nhất và nghiệm không âm nhỏ nhất.** Nếu r=0, nghiệm dương nhỏ nhất là M.
14. **Dùng 0 làm dấu vô nghiệm.** r=0 là kết quả CRT hợp lệ.
15. **Dùng −1 làm dấu vô nghiệm nhưng không có lớp kết quả.** Có nghiệm nguyên âm; nên dùng Optional/cờ rõ.
16. **Tự đổi môđun âm thành dương khi API quy định từ chối.** Phải tuân thủ hợp đồng đầu vào.
17. **Quên trường hợp môđun1.** Điều kiện modulo1 là vô điều kiện, không tạo mâu thuẫn.
18. **Quên trường hợp hệ rỗng.** Về mặt logic, không có ràng buộc nên mọi số nguyên hợp lệ.
19. **Giả định hai môđun bằng nhau luôn mâu thuẫn.** Nếu số dư chuẩn giống nhau, chúng là cùng điều kiện.
20. **Giả định hai môđun bằng nhau luôn tương thích.** Nếu số dư chuẩn khác, hệ vô nghiệm.
21. **Quên modulo chuẩn hóa r cuối cùng.** Nên đưa r vào [0,L), không giữ giá trị trung gian âm/lớn tùy ý.
22. **Dùng int hoặc long cho tích môđun lớn.** Có thể tràn dù từng mi vừa long.
23. **Tính `m*n/g` bằng long và tràn trước khi chia g.** Nếu dùng long, nên giảm trước khi nhân và kiểm tra overflow; BigInteger an toàn hơn.
24. **Bắt lỗi arithmetic rồi in INCONSISTENT.** Overflow là lỗi số học của cài đặt, không chứng minh hệ vô nghiệm.
25. **Nghĩ rằng nghịch đảo modulo luôn tồn tại.** Điều kiện là gcd=1 (với môđun>1).
26. **Nhầm hệ số Bézout x với nghiệm CRT cuối.** Hệ số inverse chỉ hỗ trợ giải biến t trong x=a+m*t.
27. **Không kiểm tra nghiệm bằng thế lại từng phương trình.** Có thể bỏ qua lỗi dấu/gcd/chuẩn hóa.
28. **Dùng vòng for x từ0 đến tích môđun để làm solver chính.** Không khả thi khi chu kỳ rất lớn.
29. **Tin brute force với vài test nhỏ là chứng minh lý thuyết.** Nó là kiểm thử; tính đúng phải dựa trên điều kiện gcd và Bézout.
30. **Không phân biệt `lcm` với `gcd`.** gcd kiểm tra tương thích; lcm là chu kỳ nghiệm.
31. **Trừ hai số dư không đúng thứ tự rồi áp công thức t không tương ứng.** Nếu chọn x=a+m*t thì delta=b−a; dùng chiều ngược phải điều chỉnh toàn công thức.
32. **Cho rằng CRT chỉ áp dụng khi các môđun là số nguyên tố.** Chỉ cần đôi một coprime cho cổ điển, tổng quát còn cho phép chung ước.
33. **Dùng phép chia nguyên mặc định của Java để tính ceil/floor cho k âm.** Phải xử lý làm tròn đúng theo toán học.
34. **Đếm số nghiệm trên ℤ là một số hữu hạn.** Nếu hệ có nghiệm và mọi môđun dương, có vô hạn nghiệm nguyên; trong một chu kỳ có đúng một đại diện chuẩn.
35. **Kết luận lcm kết quả bằng tích của môđun dù có trùng môđun.** Với m=n, lcm=m, không phải m².
36. **Quên điều kiện tương thích sau khi gộp hai phương trình khi thêm phương trình thứ ba.** Phải kiểm tra với current (modulus lcm cũ).
37. **Giữ số dư raw không chuẩn hóa rồi so trực tiếp bằng `==`.** Hai đại diện khác nhau có thể cùng lớp mod m.
38. **Không kiểm tra BigInteger bất biến.** `a.add(b)` không sửa a; cần lấy giá trị trả về.
39. **Nhầm mọi phương trình modulo1 thành x=0.** Chúng không ràng buộc giá trị x; x≡0(mod1) biểu diễn mọi số nguyên.
40. **Chỉ chạy kiểm thử hệ coprime.** Lỗi chính của generalized CRT thường nằm ở gcd>1, môđun trùng, dư âm và vô nghiệm.

## 13. Bài tập tự luyện có đáp án

**Bài 1.** `x≡a(mod m)` nghĩa là gì?

**Đáp án:** m chia hết x−a, hay tồn tại k∈ℤ sao cho x=a+k*m.

**Bài 2.** Chuẩn hóa số dư −1 modulo5 được bao nhiêu?

**Đáp án:** 4, vì −1≡4(mod5).

**Bài 3.** Điều kiện nào để CRT cổ điển bảo đảm luôn có nghiệm với mọi bộ số dư?

**Đáp án:** Các môđun **đôi một nguyên tố cùng nhau**.

**Bài 4.** gcd(6,10,15)=1 có đủ để khẳng định môđun đôi một coprime không?

**Đáp án:** Không; gcd(6,10)=2, nên tập không đôi một coprime.

**Bài 5.** Giải x≡2(mod3), x≡3(mod5), x≡2(mod7).

**Đáp án:** x≡23(mod105).

**Bài 6.** Với hệ bài 5, liệt kê ba nghiệm không âm nhỏ nhất.

**Đáp án:** 23,128,233.

**Bài 7.** Điều kiện có nghiệm cho hai đồng dư x≡a(modm), x≡b(modn) là gì?

**Đáp án:** `gcd(m,n)|(b−a)`.

**Bài 8.** Chu kỳ nghiệm hai đồng dư tương thích là gì?

**Đáp án:** `lcm(m,n) = m*(n/gcd(m,n))`.

**Bài 9.** Giải x≡2(mod6), x≡8(mod14).

**Đáp án:** x≡8(mod42).

**Bài 10.** Vì sao x≡1(mod6), x≡2(mod14) vô nghiệm?

**Đáp án:** gcd(6,14)=2 không chia 2−1=1.

**Bài 11.** Với m=6,n=14, g=2, phương trình rút gọn cho biến t có môđun bao nhiêu?

**Đáp án:** n'=14/2=7; từ x=a+6t, ta giải (6/2)t≡(b−a)/2(mod7).

**Bài 12.** Nghịch đảo của 3 modulo7 bằng bao nhiêu?

**Đáp án:** 5 vì 3×5=15≡1(mod7).

**Bài 13.** Nghịch đảo của 2 modulo4 có tồn tại không?

**Đáp án:** Không, vì gcd(2,4)=2.

**Bài 14.** Giải hệ x≡−1(mod5), x≡2(mod3).

**Đáp án:** x≡14(mod15).

**Bài 15.** Giải hệ ba phương trình x≡2(mod6), x≡8(mod14), x≡2(mod15).

**Đáp án:** x≡92(mod210).

**Bài 16.** Với hai điều kiện x≡17(mod12) và x≡−7(mod12), hệ có nghiệm không?

**Đáp án:** Có, cả hai là x≡5(mod12).

**Bài 17.** Với x≡1(mod4) và x≡2(mod4), hệ có nghiệm không?

**Đáp án:** Không.

**Bài 18.** Tập nghiệm của x≡123(mod1) là gì?

**Đáp án:** Mọi số nguyên, có thể biểu diễn x≡0(mod1).

**Bài 19.** Hệ không có phương trình được solver biểu diễn thế nào?

**Đáp án:** x≡0(mod1), nghĩa là mọi số nguyên được chấp nhận.

**Bài 20.** Nếu hệ cho x≡0(mod18), nghiệm **nguyên dương nhỏ nhất** là gì?

**Đáp án:** 18; nghiệm không âm nhỏ nhất là0.

**Bài 21.** Nếu x≡5(mod12) và x≡1(mod4), kết quả?

**Đáp án:** x≡5(mod12), vì điều kiện modulo4 là hệ quả của điều kiện modulo12.

**Bài 22.** Nếu x≡5(mod12) và x≡2(mod4), kết quả?

**Đáp án:** Vô nghiệm vì 5 mod4=1 khác2.

**Bài 23.** Vì sao trong công thức tích CRT, Mi=M/mi có nghịch đảo theo modulo mi?

**Đáp án:** Vì các môđun đôi một coprime nên gcd(Mi,mi)=1.

**Bài 24.** Viết công thức nghiệm CRT cổ điển.

**Đáp án:** `x≡Σ ai*Mi*inv(Mi mod mi) (mod M)`, M=∏mi, Mi=M/mi; với mi=1 có thể bỏ điều kiện ấy.

**Bài 25.** Euclid mở rộng trả gì ngoài gcd?

**Đáp án:** Hai hệ số nguyên x,y thỏa ax+by=gcd(a,b).

**Bài 26.** Vì sao hệ số Bézout của a khi gcd(a,m)=1 dùng làm inverse modulo m?

**Đáp án:** Từ ax+my=1 suy ra ax≡1(mod m).

**Bài 27.** Môđun 6 và 14 có tích84 nhưng lcm42; tại sao CRT trả modulo42?

**Đáp án:** Hiệu của hai nghiệm phải chia hết cả 6 và14, tức chia hết lcm42; đây là chu kỳ nhỏ nhất, không phải tích84.

**Bài 28.** Tại sao không dùng Long.MAX_VALUE làm sentinel “vô nghiệm”?

**Đáp án:** Số dư/kết quả có thể nhận giá trị rất lớn; trạng thái vô nghiệm nên biểu diễn bằng Optional.empty hoặc cờ riêng.

**Bài 29.** Vì sao Java BigInteger có lợi trong CRT?

**Đáp án:** Lcm/tích môđun có thể vượt 64 bit, BigInteger giữ phép toán nguyên chính xác.

**Bài 30.** Nếu hệ trả x≡7(mod20), có bao nhiêu nghiệm trong [0,100]?

**Đáp án:** 5 nghiệm: 7,27,47,67,87.

**Bài 31.** Nếu hệ trả x≡0(mod10), có bao nhiêu nghiệm nguyên dương không vượt50?

**Đáp án:** 5 nghiệm: 10,20,30,40,50.

**Bài 32.** Công thức chọn k cho nghiệm r+kM trong [L,R]?

**Đáp án:** `ceil((L−r)/M)≤k≤floor((R−r)/M)` với M>0; phải xử lý làm tròn số âm chính xác.

**Bài 33.** Muốn kiểm thử solver trên môđun nhỏ mà không dùng lại công thức CRT, làm gì?

**Đáp án:** Tính lcm nhỏ rồi duyệt từng x trong [0,lcm), kiểm tra phép chia lấy dư của từng phương trình; so với kết quả solver.

**Bài 34.** Có thể kết luận hệ vô nghiệm khi `gcd(m1,...,mk)=1` không?

**Đáp án:** Không. gcd tổng bằng1 không bảo đảm mọi cặp môđun tương thích; phải kiểm tra ràng buộc số dư.

**Bài 35.** Khi gộp hai phương trình đã tương thích, vì sao không cần lưu cả hai phương trình ban đầu?

**Đáp án:** Vì kết quả x≡r(mod lcm) mô tả **chính xác giao tập nghiệm** của cả hai; có thể dùng làm ràng buộc duy nhất cho bước tiếp theo.

## 14. Checklist trước khi nộp lời giải

| Hạng mục | Câu hỏi tự kiểm |
| --- | --- |
| Miền đầu vào | Mọi môđun đã được xác thực dương chưa? |
| Chuẩn hóa | Số dư âm đã được đưa về [0,m) chưa? |
| Trường hợp cổ điển | Có thực sự **đôi một** coprime hay không? |
| Gộp tổng quát | Đã tính g=gcd(m,n) đúng chưa? |
| Tương thích | Đã kiểm tra g chia hết b−a chưa? |
| Rút gọn | Đã dùng m'=m/g, n'=n/g, d'=(b−a)/g chưa? |
| Nghịch đảo | Chỉ lấy inverse sau khi gcd(m',n')=1 và n'>1? |
| Môđun1 | Có xử lý n'=1 mà không tính inverse? |
| Chu kỳ | Đã dùng lcm=m*(n/g), không dùng m*n khi g>1? |
| Nghiệm chuẩn | Đã đưa r về [0,lcm) chưa? |
| Tràn số | Dùng BigInteger hoặc có chứng minh cận và kiểm tra overflow? |
| Vô nghiệm | Kết quả lỗi tách biệt hẳn số dư0 hợp lệ? |
| Hệ rỗng | Quy ước x≡0(mod1) đã được hiểu rõ? |
| Kết luận | Đã mô tả mọi nghiệm x=r+kM, k∈ℤ? |
| Kiểm tra | Đã thay r vào **tất cả** phương trình? |
| Kiểm thử | Có test coprime, noncoprime, vô nghiệm, dư âm, mod1, mod trùng? |
| Đoạn giá trị | Nếu cần [L,R], đã tính ceil/floor đúng cả với số âm? |

## Kết luận

**Định lý phần dư Trung Hoa** biến một hệ nhiều phương trình đồng dư thành **một lớp đồng dư duy nhất**, nếu các ràng buộc tương thích.

- Với **môđun đôi một nguyên tố cùng nhau**, hệ luôn có nghiệm với mọi số dư; chu kỳ kết quả là **tích các môđun**, và có công thức trực tiếp bằng nghịch đảo modulo.
- Với **môđun có thể chung ước**, hai phương trình `x≡a(modm)` và `x≡b(modn)` gộp được **khi và chỉ khi `gcd(m,n) | (b−a)`**; nếu gộp được, chu kỳ là **lcm(m,n)**.
- Giải hệ dài bằng cách **bắt đầu ở x≡0(mod1), rồi gộp từng phương trình**. Mỗi bước giữ chính xác giao tập nghiệm đã xử lý; nếu gặp một mâu thuẫn thì toàn hệ vô nghiệm.
- Dùng **Euclid mở rộng** để tính nghịch đảo sau khi đã rút gọn theo gcd; dùng **BigInteger** để không làm sai kết quả vì tràn số.

Hãy luôn trình bày kết quả theo **`x≡r(modM)`, 0≤r<M**, hoặc **INCONSISTENT**, và nhớ rằng x=r+kM cho mọi k∈ℤ mới là **toàn bộ tập nghiệm**. Nắm vững điều kiện gcd và việc gộp hai lớp đồng dư là đủ để giải phần lớn bài CRT trong lập trình thuật toán, kể cả khi môđun trùng nhau, có chung ước hoặc rất lớn.
