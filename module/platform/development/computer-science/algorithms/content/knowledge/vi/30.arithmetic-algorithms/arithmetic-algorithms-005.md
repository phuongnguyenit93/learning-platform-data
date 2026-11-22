# Nghịch đảo modulo và điều kiện tồn tại

## Mục tiêu học tập

Trong nhóm **Thuật toán số học**, **nghịch đảo modulo** (*modular multiplicative inverse*) là công cụ giúp giải phương trình đồng dư, thực hiện “phép chia” hợp lệ trong số học modulo, xây dựng các công thức tổ hợp theo môđun và kết hợp nghiệm bằng định lý phần dư Trung Hoa.

Nhưng **không phải số nào cũng có nghịch đảo modulo**. Với môđun nguyên dương `m≥2`, một số nguyên a có nghịch đảo modulo m **khi và chỉ khi**:

\[
\boxed{\gcd(a,m)=1}.
\]

Đây là trọng tâm của bài: không được “chia hai vế cho a” trong đồng dư nếu chưa kiểm tra điều kiện trên.

Sau bài học, bạn có thể:

1. Định nghĩa và kiểm tra nghịch đảo modulo, phân biệt nghịch đảo với phần dư thông thường.
2. Chứng minh điều kiện cần và đủ `gcd(a,m)=1` bằng **định lý Bézout**.
3. Dùng **thuật toán Euclid mở rộng** để tìm nghịch đảo cho môđun bất kỳ `m≥2` khi nó tồn tại.
4. Dùng **định lý Fermat nhỏ** để tính nghịch đảo bằng lũy thừa nhanh khi môđun là **số nguyên tố** và `a\not\equiv0\pmod p`.
5. Hiểu vai trò của định lý Euler, sự khác biệt giữa môđun nguyên tố và hợp số, và nguy cơ của cách “chia modulo” sai.
6. Giải phương trình tuyến tính `ax\equiv b\pmod m`: kiểm tra `gcd(a,m)\mid b` và mô tả **tất cả nghiệm**.
7. Xử lý a âm, a lớn hơn môđun, a=0, m=1, m=0 và tràn số.
8. Viết chương trình **Java 17+** với `BigInteger`, xác minh công thức và in kết quả chính xác.
9. Áp dụng trong tổ hợp modulo, xử lý nhiều truy vấn và định lý phần dư Trung Hoa.
10. Thiết kế kiểm thử độc lập bằng vét cạn trên môđun nhỏ.

---

## 1. Số học modulo: những định nghĩa cần phân biệt

Với môđun nguyên dương m, hai số nguyên a và b **đồng dư modulo m** nếu hiệu của chúng chia hết cho m:

\[
a\equiv b\pmod m
\quad\Longleftrightarrow\quad
m\mid(a-b).
\]

Ví dụ:

\[
17\equiv5\pmod{12}
\]

vì `17-5=12` chia hết cho 12.

Lớp đồng dư của a là tập tất cả số dạng `a+km` với k nguyên. Khi làm bài thuật toán, ta thường dùng **đại diện chuẩn** trong khoảng:

\[
0,1,\ldots,m-1.
\]

### 1.1. Phép cộng và nhân modulo

Nếu:

\[
a\equiv a'\pmod m,\quad b\equiv b'\pmod m,
\]

thì:

\[
a+b\equiv a'+b'\pmod m,
\]

\[
ab\equiv a'b'\pmod m.
\]

Vì vậy, việc cộng, trừ và nhân hai lớp đồng dư có thể tính bằng các đại diện của chúng rồi lấy dư.

**Không có quy tắc tương tự cho phép chia tùy ý.** Muốn chia cho a, trước hết phải chứng minh a có **nghịch đảo nhân** trong modulo m.

### 1.2. Định nghĩa nghịch đảo modulo

Số x là một **nghịch đảo modulo m** của a nếu:

\[
\boxed{ax\equiv1\pmod m.}
\]

Ký hiệu:

\[
x\equiv a^{-1}\pmod m.
\]

Ví dụ:

\[
3\cdot4=12\equiv1\pmod{11},
\]

nên:

\[
\boxed{3^{-1}\equiv4\pmod{11}}.
\]

Một số cụ thể có thể viết dưới nhiều dạng đồng dư:

```text
4, 15, -7, 26, ...
```

đều là các nghịch đảo của 3 modulo 11, vì chúng cùng thuộc lớp đồng dư 4. Khi yêu cầu “tìm nghịch đảo”, chương trình thường trả **một đại diện chuẩn duy nhất** trong khoảng `0..m-1`.

### 1.3. Nghịch đảo không phải số đối

**Số đối cộng** của a là −a, thỏa:

\[
a+(-a)\equiv0\pmod m.
\]

**Nghịch đảo nhân** của a là x, thỏa:

\[
ax\equiv1\pmod m.
\]

Hai khái niệm khác nhau. Ví dụ modulo 11, số đối của 3 là 8, nhưng nghịch đảo nhân của 3 là 4.

### 1.4. Nghịch đảo cũng không phải phép chia nguyên

Trong số nguyên thông thường, 1/3 không phải số nguyên. Nhưng trong modulo 11, `3^{-1}` tồn tại và bằng 4. Vì vậy:

\[
\frac{5}{3}\pmod{11}
\]

nếu được định nghĩa bằng **nhân với nghịch đảo**, sẽ là:

\[
5\cdot3^{-1}\equiv5\cdot4\equiv9\pmod{11}.
\]

Ở đây ký hiệu phân số chỉ là cách viết tắt của phép nhân với nghịch đảo modulo, **không phải** phép chia số thực hay phép chia nguyên trước khi lấy dư.

### 1.5. Quy ước môđun

Bài này làm việc với `m≥2`.

- **m=0:** phép đồng dư modulo 0 không được dùng theo định nghĩa chuẩn của bài, và phép `a.mod(0)` trong Java không hợp lệ.
- **m âm:** có thể quy đổi về `|m|` trong lý thuyết số, nhưng API mẫu **yêu cầu m≥2** để không nhập nhằng.
- **m=1:** tất cả số nguyên cùng một lớp đồng dư duy nhất. Cấu trúc này được xem là vành không (zero ring), có những quy ước suy biến khác biệt về đơn vị và nghịch đảo. Để phù hợp bài toán nghịch đảo modulo thông dụng và các API lập trình, chương trình **từ chối m=1** và dùng định lý cần-đủ cho `m≥2`.

Không đưa m=1 vào công thức lũy thừa Fermat hay công thức đếm nghiệm thông thường mà không quy định riêng.

---

## 2. Điều kiện tồn tại: gcd(a,m)=1

### 2.1. Định lý

Với m nguyên và `m≥2`, một số nguyên a có nghịch đảo modulo m **khi và chỉ khi**:

\[
\boxed{\gcd(a,m)=1}.
\]

Gọi a và m là **nguyên tố cùng nhau** (*coprime* hoặc *relatively prime*) khi ước chung lớn nhất bằng 1. Bản thân a **không cần là số nguyên tố**; nó chỉ cần không có thừa số nguyên tố chung với m.

### 2.2. Chứng minh chiều cần

Giả sử tồn tại x sao cho:

\[
ax\equiv1\pmod m.
\]

Theo định nghĩa đồng dư, tồn tại số nguyên k để:

\[
ax-1=km.
\]

Suy ra:

\[
ax-km=1.
\]

Mọi ước chung của a và m đều chia vế trái, nên phải chia 1. Do đó:

\[
\gcd(a,m)=1.
\]

Vậy **nếu có nghịch đảo, gcd bắt buộc bằng 1**.

### 2.3. Chứng minh chiều đủ bằng Bézout

**Định lý Bézout:** với hai số nguyên a,m không đồng thời bằng 0, tồn tại hai số nguyên x,y sao cho:

\[
ax+my=\gcd(a,m).
\]

Nếu `gcd(a,m)=1`, ta có:

\[
ax+my=1.
\]

Lấy modulo m:

\[
ax\equiv1\pmod m,
\]

nên x chính là một nghịch đảo của a modulo m.

Vậy **nếu gcd bằng 1, nghịch đảo chắc chắn tồn tại**.

### 2.4. Tính duy nhất theo lớp đồng dư

Giả sử x và y đều là nghịch đảo của a:

\[
ax\equiv1\pmod m,\quad ay\equiv1\pmod m.
\]

Lấy hiệu:

\[
a(x-y)\equiv0\pmod m.
\]

Vì `gcd(a,m)=1`, a có thể được khử hợp lệ khỏi đồng dư, dẫn đến:

\[
x-y\equiv0\pmod m.
\]

Do đó:

\[
\boxed{x\equiv y\pmod m}.
\]

Nghịch đảo **duy nhất theo lớp đồng dư**, mặc dù có vô hạn số nguyên đại diện. Khi chuẩn hóa về `[0,m)`, ta thu được đúng một số.

### 2.5. Ví dụ tồn tại

| a | m | gcd(a,m) | Có nghịch đảo? | Đại diện chuẩn |
| ---: | ---: | ---: | --- | ---: |
| 3 | 11 | 1 | Có | 4 |
| 7 | 26 | 1 | Có | 15 |
| 10 | 17 | 1 | Có | 12 |
| 14 | 33 | 1 | Có | 26 |
| −3 | 11 | 1 | Có | 7 |
| 6 | 9 | 3 | Không | — |
| 0 | 7 | 7 | Không | — |
| 1 | 2 | 1 | Có | 1 |

Kiểm tra:

\[
7\cdot15=105\equiv1\pmod{26},
\]

\[
10\cdot12=120\equiv1\pmod{17},
\]

\[
14\cdot26=364\equiv1\pmod{33}.
\]

Với a=−3 và m=11:

\[
-3\equiv8\pmod{11},
\]

\[
8\cdot7=56\equiv1\pmod{11}.
\]

Với a=6,m=9:

\[
\gcd(6,9)=3\ne1.
\]

Không có x nào làm `6x≡1(mod 9)`, vì mọi `6x` chia hết cho 3, trong khi 1 thì không.

### 2.6. Đơn vị modulo

Những lớp đồng dư có nghịch đảo tạo thành **nhóm nhân các đơn vị modulo m**, ký hiệu thường gặp là:

\[
(\mathbb Z/m\mathbb Z)^\times.
\]

Với `m=10`, các đại diện có nghịch đảo là:

```text
1, 3, 7, 9
```

vì chúng nguyên tố cùng nhau với 10.

Các giá trị:

```text
0, 2, 4, 5, 6, 8
```

không có nghịch đảo modulo 10.

Số lớp đồng dư có nghịch đảo bằng **hàm phi Euler** `φ(m)`. Khi m là số nguyên tố p, mọi lớp khác 0 đều khả nghịch và `φ(p)=p-1`.

---

## 3. Tại sao không được tùy tiện chia hoặc khử nhân tử?

Trong số học thông thường:

\[
ax=ay\quad (a\ne0)
\]

suy ra x=y.

Nhưng với đồng dư:

\[
ax\equiv ay\pmod m,
\]

muốn suy ra `x≡y(mod m)`, ta phải có:

\[
\gcd(a,m)=1.
\]

### 3.1. Phản ví dụ modulo 8

Xét:

\[
2x\equiv2\pmod8.
\]

Cả x=1 và x=5 đều thỏa:

\[
2\cdot1=2\equiv2\pmod8,
\]

\[
2\cdot5=10\equiv2\pmod8.
\]

Nếu “chia hai vế cho 2” để được `x≡1(mod 8)`, ta bỏ nghiệm x=5. Thực tế:

\[
\gcd(2,8)=2.
\]

Có thể chia đồng dư và **giảm môđun** một cách đúng đắn:

\[
2x\equiv2\pmod8
\iff
x\equiv1\pmod4.
\]

Những nghiệm modulo 8 là 1 và 5.

### 3.2. Quy tắc khử đúng

Nếu:

\[
ac\equiv bc\pmod m,
\]

đặt `d=\gcd(c,m)` thì:

\[
\boxed{a\equiv b\pmod{m/d}.}
\]

Muốn giữ nguyên môđun m sau khi khử c, phải có d=1. Đây là quy tắc giải thích tại sao “chia đồng dư” cần kiểm tra ước chung lớn nhất.

### 3.3. Khi bài toán cho một phép chia

Một biểu thức kiểu:

\[
a/b\pmod m
\]

có thể được hiểu là:

\[
a\cdot b^{-1}\pmod m
\]

**chỉ nếu** `gcd(b,m)=1`. Nếu gcd không bằng 1, không thể gán một kết quả duy nhất bằng “nghịch đảo của b” vì nghịch đảo không tồn tại.

Trong trường hợp không khả nghịch, ta có thể giải riêng phương trình tuyến tính:

\[
bx\equiv a\pmod m,
\]

và có thể gặp **không nghiệm** hoặc **nhiều nghiệm**, chứ không phải một kết quả chia modulo duy nhất.

---

## 4. Thuật toán Euclid và Euclid mở rộng

### 4.1. Euclid tìm gcd

Thuật toán Euclid dựa vào:

\[
\gcd(a,b)=\gcd(b,a\bmod b).
\]

Lặp cho đến khi số chia trở thành 0; số khác 0 còn lại là gcd.

Ví dụ:

```text
gcd(26, 7)

26 = 3*7 + 5
 7 = 1*5 + 2
 5 = 2*2 + 1
 2 = 2*1 + 0

gcd(26,7) = 1
```

Chỉ tính gcd đủ để biết **nghịch đảo có tồn tại**, nhưng chưa cho giá trị nghịch đảo.

### 4.2. Euclid mở rộng tìm hệ số Bézout

Thuật toán Euclid **mở rộng** (*extended Euclidean algorithm*, EEA) tìm thêm x,y sao cho:

\[
ax+by=\gcd(a,b).
\]

Khi b là môđun m và gcd bằng 1, x chính là một nghịch đảo modulo m.

### 4.3. Truy ngược ví dụ 7 modulo 26

Từ Euclid:

```text
26 = 3*7 + 5
 7 = 1*5 + 2
 5 = 2*2 + 1
```

Truy ngược:

\[
1=5-2\cdot2,
\]

\[
=5-2(7-5)=3\cdot5-2\cdot7,
\]

\[
=3(26-3\cdot7)-2\cdot7,
\]

\[
=\boxed{3\cdot26-11\cdot7}.
\]

Do đó:

\[
7(-11)+26(3)=1.
\]

Hệ số của 7 là `-11`, nên:

\[
7^{-1}\equiv-11\equiv15\pmod{26}.
\]

Kiểm tra:

\[
7\cdot15=105=4\cdot26+1.
\]

### 4.4. Công thức đệ quy của EEA

Với a,b không âm và b>0, viết:

\[
a=qb+r,\quad q=\lfloor a/b\rfloor,\quad r=a\bmod b.
\]

Giả sử lời gọi đệ quy cho:

\[
bx_1+ry_1=g.
\]

Thay `r=a-qb`:

\[
bx_1+(a-qb)y_1=g,
\]

\[
ay_1+b(x_1-qy_1)=g.
\]

Vậy:

\[
\boxed{x=y_1,\qquad y=x_1-qy_1.}
\]

Trường hợp cơ sở:

\[
\operatorname{egcd}(a,0)=(a,1,0)
\]

với a≥0.

### 4.5. Giả mã

```text
EXTENDED_GCD(a,b):
    // tiền điều kiện a>=0, b>=0

    if b==0:
        return (g=a, x=1, y=0)

    q = a div b
    r = a mod b

    (g,x1,y1) = EXTENDED_GCD(b,r)

    x = y1
    y = x1 - q*y1

    return (g,x,y)
```

Để lấy nghịch đảo:

```text
INVERSE(a,m):
    require m>=2
    a = normalize(a,m)  // 0..m-1

    (g,x,y) = EXTENDED_GCD(a,m)

    if g!=1:
        return NO_INVERSE

    return normalize(x,m)
```

### 4.6. Chuẩn hóa hệ số âm

Kết quả x của Bézout có thể âm, ví dụ x=−11. Công thức chuẩn hóa toán học:

\[
norm(x,m)=((x\bmod m)+m)\bmod m.
\]

Trong Java `long`, phép `%` với số âm có thể trả số âm. Trong Java `BigInteger`, `x.mod(m)` với m dương luôn trả **đại diện không âm**, nên code có thể dùng:

```java
x.mod(modulus)
```

miễn modulus đã được xác nhận dương.

### 4.7. Độ phức tạp

Số bước chia dư của Euclid là **O(log m)** khi đầu vào a đã chuẩn hóa vào `0..m−1`. EEA cũng dùng cùng số bước và thêm một ít số học mỗi bước.

Nếu dùng kiểu số cố định và mọi phép số học có chi phí O(1), ta thường nói EEA chạy **O(log m)** thời gian và O(log m) stack nếu đệ quy, hoặc O(1) biến phụ nếu lặp.

Với `BigInteger`, phép chia/nhân/trừ trên số nhiều bit **không có chi phí hằng số**; `O(log m)` khi ấy là **số vòng lặp Euclid**, không phải số phép bit chính xác. Đây là phân biệt quan trọng nếu phân tích thuật toán trên số cực lớn.

### 4.8. Vì sao thích dùng BigInteger để giảng?

Bản `long` của EEA có nguy cơ tràn khi tính các hệ số Bézout trung gian với các số lớn. Java `BigInteger` cho phép giữ số nguyên chính xác, không tràn số học theo kiểu long, và có sẵn `gcd`, `mod`, `modPow`, `modInverse`.

Tất nhiên BigInteger vẫn dùng RAM và CPU tỷ lệ với số bit; nó không biến việc tính toán số cực lớn thành miễn phí.

---

## 5. Tính nghịch đảo bằng Fermat nhỏ

Khi môđun là **số nguyên tố** p và `p\nmid a`, định lý Fermat nhỏ nói:

\[
a^{p-1}\equiv1\pmod p.
\]

Nhân hai vế với nghịch đảo của a, hoặc biến đổi trong nhóm nhân:

\[
a^{p-2}\equiv a^{-1}\pmod p.
\]

Do đó:

\[
\boxed{a^{-1}\equiv a^{p-2}\pmod p}
\]

**chỉ áp dụng khi p nguyên tố và `a\not\equiv0\pmod p`.**

### 5.1. Ví dụ modulo 11

Cho a=3,p=11:

\[
3^{-1}\equiv3^{9}\pmod{11}.
\]

Lũy thừa nhanh cho kết quả 4:

\[
3\cdot4=12\equiv1\pmod{11}.
\]

### 5.2. Lũy thừa nhị phân

Để tính `a^e mod m`, không nên nhân a với chính nó e lần. **Binary exponentiation** dùng bình phương và xét từng bit của e:

```text
MOD_POW(a,e,m):
    result=1
    base=a mod m

    while e>0:
        if e odd:
            result=result*base mod m

        base=base*base mod m
        e=floor(e/2)

    return result
```

Số vòng lặp là O(log e). Với `e=p−2`, số vòng O(log p), giả sử phép nhân modulo có chi phí hằng số.

Trong Java, `BigInteger.modPow(exponent,modulus)` cung cấp phép lũy thừa modulo hiệu quả.

### 5.3. Môđun hợp số: Fermat không áp dụng

Ví dụ m=8, a=3. Ta có:

\[
\gcd(3,8)=1,
\]

nên nghịch đảo tồn tại và bằng 3 vì:

\[
3\cdot3=9\equiv1\pmod8.
\]

Nếu **sai lầm** lấy `a^{m-2}=3^6` modulo 8:

\[
3^6\equiv1\pmod8,
\]

nhận kết quả 1, nhưng:

\[
3\cdot1\not\equiv1\pmod8.
\]

Vậy không được áp công thức `a^{m-2}` cho môđun hợp số chỉ vì a và m nguyên tố cùng nhau.

### 5.4. Điều kiện a không chia hết cho p

Ngay cả khi p là số nguyên tố:

\[
a\equiv0\pmod p
\]

thì `gcd(a,p)=p\ne1`, nghịch đảo **không tồn tại**.

Ví dụ:

```text
0 mod 11   -> không có nghịch đảo
11 mod 11  -> không có nghịch đảo
22 mod 11  -> không có nghịch đảo
```

Không nên tính `0^{p-2}` rồi coi kết quả là nghịch đảo.

### 5.5. Trường hợp p=2

Với p=2, số khác 0 duy nhất là lớp 1. Fermat dùng số mũ `p−2=0`:

\[
1^0\equiv1\pmod2.
\]

Nên `1^{-1}\equiv1(mod 2)`. Code phải cho phép số mũ 0 trong modPow.

### 5.6. Kiểm tra p có nguyên tố?

Nếu p được chứng minh là nguyên tố từ đề, có thể dùng ngay. Nếu p là dữ liệu bất kỳ, cần kiểm tra số nguyên tố trước khi áp Fermat.

Java `BigInteger.isProbablePrime(certainty)` là **phép kiểm tra xác suất cao**, không phải một chứng minh nguyên tố tuyệt đối. Bài mẫu sử dụng nó như **hàng rào đầu vào thực dụng**, đồng thời nhấn mạnh: điều kiện toán học của Fermat vẫn là “p nguyên tố thật”.

Nếu cần chứng minh nguyên tố trong môi trường đối kháng, hãy dùng công cụ kiểm tra nguyên tố có bảo đảm phù hợp với miền đầu vào.

---

## 6. Định lý Euler: mở rộng cho môđun hợp số

Định lý Euler phát biểu: nếu `gcd(a,m)=1` thì:

\[
\boxed{a^{\varphi(m)}\equiv1\pmod m},
\]

trong đó `\varphi(m)` là số lớp dư từ 1 tới m−1 nguyên tố cùng nhau với m.

Suy ra:

\[
\boxed{a^{-1}\equiv a^{\varphi(m)-1}\pmod m}.
\]

### 6.1. Ví dụ modulo 8

`m=8`, các phần tử khả nghịch là 1,3,5,7 nên `\varphi(8)=4`.

Với a=3:

\[
3^{-1}\equiv3^{3}\equiv27\equiv3\pmod8.
\]

Kiểm tra `3·3≡1(mod 8)`.

### 6.2. Tại sao không luôn dùng Euler thay Euclid?

Với môđun nguyên tố p, biết ngay `\varphi(p)=p-1` nên Fermat rất tiện. Với môđun hợp số tổng quát, để biết `\varphi(m)` thường cần **phân tích thừa số nguyên tố của m**, có thể khó hơn tìm nghịch đảo bằng Euclid.

Vì vậy nếu chỉ cần **một nghịch đảo bất kỳ**, EEA là cách tổng quát, không cần biết m là nguyên tố và không cần phân tích m.

### 6.3. Không bỏ qua gcd

Euler cũng yêu cầu `gcd(a,m)=1`. Với a=6,m=9, `\varphi(9)=6` nhưng:

\[
6^6\not\equiv1\pmod9.
\]

Không thể dùng Euler để tìm nghịch đảo vốn không tồn tại.

### 6.4. So sánh ba cách

| Phương pháp | Điều kiện | Cần thông tin đặc biệt? | Số bước cơ bản |
| --- | --- | --- | --- |
| Euclid mở rộng | `m≥2` và `gcd(a,m)=1` | Không cần m nguyên tố | O(log m) phép chia dư |
| Fermat nhỏ | p nguyên tố, `a\bmod p\ne0` | Biết/chứng minh p nguyên tố | O(log p) bước lũy thừa |
| Euler | `gcd(a,m)=1` | Biết `\varphi(m)` | O(log \varphi(m)) bước lũy thừa, chưa tính phi |

Nếu kết quả yêu cầu đúng tuyệt đối mà chưa biết m có phải nguyên tố, **Euclid mở rộng** là lựa chọn mặc định đáng tin.

---

## 7. Phương trình tuyến tính ax ≡ b (mod m)

Đây là ứng dụng quan trọng thể hiện vì sao **không có nghịch đảo** không đồng nghĩa với **mọi phương trình có a làm hệ số đều vô nghiệm**.

Bài toán:

\[
ax\equiv b\pmod m,\quad m\ge2.
\]

Đặt:

\[
d=\gcd(a,m).
\]

### 7.1. Điều kiện có nghiệm

Phương trình có nghiệm **khi và chỉ khi**:

\[
\boxed{d\mid b}.
\]

**Chiều cần:** nếu `ax≡b(mod m)`, tồn tại k sao cho `ax-b=km`, tức:

\[
ax-km=b.
\]

Vì d chia cả a và m, d phải chia b.

**Chiều đủ:** nếu d chia b, ta chia cả a,b,m cho d:

\[
a'=a/d,\quad b'=b/d,\quad m'=m/d.
\]

Do:

\[
\gcd(a',m')=1,
\]

nghịch đảo của a' modulo m' tồn tại (khi m'≥2). Phương trình giảm thành:

\[
a'x\equiv b'\pmod{m'},
\]

nên:

\[
\boxed{x\equiv b'(a')^{-1}\pmod{m'}}.
\]

Vì vậy luôn xây được nghiệm.

### 7.2. Số nghiệm modulo m

Nếu d chia b và `m'=m/d\ge2`, có đúng **d nghiệm phân biệt modulo m**:

\[
\boxed{x=x_0+k\,m',\quad k=0,1,\ldots,d-1},
\]

trong đó:

\[
x_0=(b'\cdot(a')^{-1})\bmod m'.
\]

Vì `0≤x_0<m'` nên các số `x_0+k m'` đã nằm trong khoảng `0..m-1` và không lặp nhau.

Nếu d=1, có **đúng một nghiệm modulo m**. Khi đó bài toán trở về phép nhân với nghịch đảo a.

### 7.3. Trường hợp đặc biệt d=m

Nếu `a≡0(mod m)` thì:

\[
ax\equiv0\pmod m
\]

với **mọi x**. Do đó:

- Nếu `b≡0(mod m)`, **mọi m lớp dư** đều là nghiệm.
- Nếu `b\not\equiv0(mod m)`, **không có nghiệm**.

Khi d=m, môđun rút gọn m'=1, nên ta **không gọi hàm inverse với modulus 1**. Chương trình Java xử lý nhánh này riêng để trả đủ các nghiệm.

### 7.4. Ví dụ có hai nghiệm

Giải:

\[
6x\equiv8\pmod{14}.
\]

`d=gcd(6,14)=2`, và 2 chia 8 nên có nghiệm.

Chia cho 2:

\[
3x\equiv4\pmod7.
\]

Vì `3^{-1}\equiv5(mod 7)`:

\[
x\equiv4\cdot5=20\equiv6\pmod7.
\]

Có d=2 nghiệm modulo 14:

\[
x_0=6,\quad x_1=6+7=13.
\]

Kiểm tra:

\[
6\cdot6=36\equiv8\pmod{14},
\]

\[
6\cdot13=78\equiv8\pmod{14}.
\]

Kết quả:

\[
\boxed{x\in\{6,13\}\pmod{14}}.
\]

### 7.5. Ví dụ vô nghiệm

Giải:

\[
6x\equiv5\pmod{14}.
\]

`gcd(6,14)=2` nhưng 2 không chia 5, nên:

\[
\boxed{\text{Không có nghiệm}}.
\]

Không nên cố tìm `6^{-1} mod 14` vì nghịch đảo ấy không tồn tại.

### 7.6. Ví dụ có ba nghiệm

Giải:

\[
12x\equiv9\pmod{21}.
\]

`d=gcd(12,21)=3` và `3|9`. Chia cho 3:

\[
4x\equiv3\pmod7.
\]

`4^{-1}\equiv2(mod 7)`, nên:

\[
x\equiv6\pmod7.
\]

Có ba nghiệm modulo 21:

\[
\boxed{x=6,13,20}.
\]

### 7.7. Ví dụ hệ số bằng 0

`0x≡0(mod 7)` có tất cả bảy nghiệm `0,1,2,3,4,5,6`.

`0x≡1(mod 7)` vô nghiệm.

Điều kiện gcd vẫn đúng:

\[
\gcd(0,7)=7.
\]

- `7|0` → có 7 nghiệm.
- `7\nmid1` → không có nghiệm.

---

## 8. Nhiều nghiệm không phải nghịch đảo đa trị

Một số người suy luận:

> Vì `6x≡8(mod 14)` có hai nghiệm nên 6 có “hai nghịch đảo modulo 14”.

Điều đó **sai**. Nghịch đảo của 6 cần thỏa:

\[
6x\equiv1\pmod{14},
\]

nhưng:

\[
\gcd(6,14)=2\nmid1,
\]

nên **không có nghịch đảo nào**.

Phương trình `6x≡8(mod 14)` có hai nghiệm vì vế phải 8 **chia hết cho gcd**, không phải vì 6 khả nghịch. Sự phân biệt này quan trọng khi viết API: nên có **hàm inverse** trả một Optional và **hàm solveLinearCongruence** trả một họ nghiệm.

### 8.1. Quan hệ với “chia hai vế”

Với `ax≡b(mod m)`, chỉ khi gcd(a,m)=1 ta mới viết:

\[
x\equiv b a^{-1}\pmod m
\]

mà giữ nguyên môđun m.

Khi gcd=d>1 và d chia b, phép “chia” đúng là chuyển sang:

\[
(a/d)x\equiv(b/d)\pmod{m/d}.
\]

Sau đó cần **nâng lại** nghiệm từ modulo m/d thành d lớp dư modulo m.

### 8.2. Một bất biến kiểm thử

Với nghiệm x hợp lệ:

\[
(ax-b)\bmod m=0.
\]

Khi xây một họ nghiệm `x_0+k(m/d)` với `k=0..d-1`, tất cả nghiệm phải:

- Nằm trong `0..m-1`.
- Phân biệt.
- Thỏa phương trình.
- Có đúng d phần tử.

Các thuộc tính này kiểm tra dễ dàng bằng vét cạn cho môđun nhỏ.

---

## 9. Java 17+: triển khai tổng quát bằng BigInteger

Chương trình dưới đây:

- Dùng `BigInteger` để tránh tràn số khi tính hệ số Bézout.
- Dùng EEA để tìm nghịch đảo cho **mọi modulus m≥2**, không đòi m nguyên tố.
- Chuẩn hóa a âm hoặc a lớn hơn m bằng `a.mod(m)`.
- Trả `Optional.empty()` khi gcd khác 1.
- Có ví dụ Fermat cho môđun đã biết là nguyên tố, kèm kiểm tra probable-prime như lớp bảo vệ thực dụng.
- Giải `ax≡b(mod m)` và biểu diễn **họ nghiệm** bằng nghiệm đầu, bước nhảy và số nghiệm, không tự cấp phát một danh sách khổng lồ.
- Chỉ liệt kê nghiệm khi số lượng không vượt giới hạn do người gọi cung cấp.
- Dùng `m≥2` như hợp đồng API rõ ràng.
- In đủ các ví dụ đã tính tay.

Tệp: **`ModularInverseDemo.java`**.

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class ModularInverseDemo {

    private static final BigInteger ZERO =
            BigInteger.ZERO;
    private static final BigInteger ONE =
            BigInteger.ONE;
    private static final BigInteger TWO =
            BigInteger.TWO;

    public record Bezout(
            BigInteger gcd,
            BigInteger x,
            BigInteger y) {
    }

    public record SolutionFamily(
            BigInteger first,
            BigInteger step,
            BigInteger count,
            BigInteger modulus) {

        // All canonical residues, but only for small count.
        public List<BigInteger> listAtMost(int maximum) {
            if (maximum < 0
                    || count.compareTo(
                            BigInteger.valueOf(maximum)) > 0) {
                throw new IllegalArgumentException(
                        "Too many solutions to list");
            }

            List<BigInteger> answer = new ArrayList<>();

            for (BigInteger k = ZERO;
                    k.compareTo(count) < 0;
                    k = k.add(ONE)) {
                answer.add(first.add(k.multiply(step)));
            }

            return answer;
        }
    }

    private static void requireModulus(BigInteger modulus) {
        Objects.requireNonNull(modulus, "modulus");

        if (modulus.compareTo(TWO) < 0) {
            throw new IllegalArgumentException(
                    "modulus must be >= 2");
        }
    }

    // Preconditions: a >= 0 and b >= 0.
    // Returns a*x + b*y == gcd(a,b).
    private static Bezout extendedGcd(
            BigInteger a, BigInteger b) {

        if (b.equals(ZERO)) {
            return new Bezout(a, ONE, ZERO);
        }

        BigInteger[] divRem = a.divideAndRemainder(b);
        BigInteger quotient = divRem[0];
        BigInteger remainder = divRem[1];

        Bezout sub = extendedGcd(b, remainder);

        return new Bezout(
                sub.gcd(),
                sub.y(),
                sub.x().subtract(
                        quotient.multiply(sub.y())));
    }

    public static Optional<BigInteger> inverse(
            BigInteger a, BigInteger modulus) {

        Objects.requireNonNull(a, "a");
        requireModulus(modulus);

        BigInteger normalized = a.mod(modulus);
        Bezout result = extendedGcd(
                normalized, modulus);

        if (!result.gcd().equals(ONE)) {
            return Optional.empty();
        }

        return Optional.of(
                result.x().mod(modulus));
    }

    // Use this only if the modulus is genuinely prime.
    // isProbablePrime(100) screens composites with
    // high confidence, but is not a primality proof.
    public static Optional<BigInteger> inverseFermat(
            BigInteger a, BigInteger prime) {

        Objects.requireNonNull(a, "a");
        requireModulus(prime);

        if (!prime.isProbablePrime(100)) {
            throw new IllegalArgumentException(
                    "modulus is not probably prime");
        }

        BigInteger normalized = a.mod(prime);

        if (normalized.equals(ZERO)) {
            return Optional.empty();
        }

        return Optional.of(
                normalized.modPow(
                        prime.subtract(TWO), prime));
    }

    // Solve a*x == b (mod m), with m >= 2.
    // A family has x = first + k*step,
    // for k = 0 .. count-1, all modulo m.
    public static Optional<SolutionFamily> solveLinear(
            BigInteger a,
            BigInteger b,
            BigInteger modulus) {

        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        requireModulus(modulus);

        BigInteger d = a.gcd(modulus);

        if (!b.mod(d).equals(ZERO)) {
            return Optional.empty();
        }

        // a is divisible by m, so ax == 0 (mod m).
        // If d | b, then b is also 0 modulo m:
        // every residue is a solution.
        if (d.equals(modulus)) {
            return Optional.of(
                    new SolutionFamily(
                            ZERO, ONE, modulus, modulus));
        }

        BigInteger reducedModulus =
                modulus.divide(d);
        BigInteger reducedA = a.divide(d);
        BigInteger reducedB = b.divide(d);

        BigInteger reducedInverse = inverse(
                reducedA, reducedModulus).orElseThrow();

        BigInteger first = reducedInverse
                .multiply(reducedB)
                .mod(reducedModulus);

        return Optional.of(
                new SolutionFamily(
                        first,
                        reducedModulus,
                        d,
                        modulus));
    }

    private static BigInteger bi(long value) {
        return BigInteger.valueOf(value);
    }

    private static String showInverse(
            Optional<BigInteger> result) {
        return result.map(BigInteger::toString)
                .orElse("none");
    }

    private static String showSolutions(
            Optional<SolutionFamily> result) {
        return result.map(
                family -> family.listAtMost(100).toString())
                .orElse("none");
    }

    public static void main(String[] args) {
        System.out.println(
                "inverse(3 mod 11): "
                + showInverse(inverse(bi(3), bi(11))));

        System.out.println(
                "inverse(7 mod 26): "
                + showInverse(inverse(bi(7), bi(26))));

        System.out.println(
                "inverse(10 mod 17): "
                + showInverse(inverse(bi(10), bi(17))));

        System.out.println(
                "inverse(6 mod 9): "
                + showInverse(inverse(bi(6), bi(9))));

        System.out.println(
                "inverse(-3 mod 11): "
                + showInverse(inverse(bi(-3), bi(11))));

        System.out.println(
                "inverse(0 mod 7): "
                + showInverse(inverse(bi(0), bi(7))));

        System.out.println(
                "verify 7*15 mod 26: "
                + bi(7).multiply(bi(15)).mod(bi(26)));

        Bezout bz = extendedGcd(bi(7), bi(26));
        System.out.println(
                "Bezout(7,26): gcd=" + bz.gcd()
                + ", x=" + bz.x()
                + ", y=" + bz.y());

        System.out.println(
                "Fermat inverse(3 mod 11): "
                + showInverse(inverseFermat(
                        bi(3), bi(11))));

        System.out.println(
                "Fermat inverse(0 mod 11): "
                + showInverse(inverseFermat(
                        bi(0), bi(11))));

        System.out.println(
                "6x = 8 (mod 14): "
                + showSolutions(solveLinear(
                        bi(6), bi(8), bi(14))));

        System.out.println(
                "6x = 5 (mod 14): "
                + showSolutions(solveLinear(
                        bi(6), bi(5), bi(14))));

        System.out.println(
                "0x = 0 (mod 7): "
                + showSolutions(solveLinear(
                        bi(0), bi(0), bi(7))));

        System.out.println(
                "12x = 9 (mod 21): "
                + showSolutions(solveLinear(
                        bi(12), bi(9), bi(21))));

        System.out.println(
                "inverse(42 mod 2017): "
                + showInverse(inverse(bi(42), bi(2017))));

        boolean invalidModulusRejected = false;

        try {
            inverse(bi(3), bi(1));
        } catch (IllegalArgumentException ex) {
            invalidModulusRejected = true;
        }

        System.out.println(
                "m<=1 rejected: "
                + invalidModulusRejected);
    }
}
```

### 9.1. Lệnh biên dịch và chạy

Dùng JDK 17 trở lên:

```bash
javac ModularInverseDemo.java
java ModularInverseDemo
```

**Stdout kỳ vọng chính xác:**

```text
inverse(3 mod 11): 4
inverse(7 mod 26): 15
inverse(10 mod 17): 12
inverse(6 mod 9): none
inverse(-3 mod 11): 7
inverse(0 mod 7): none
verify 7*15 mod 26: 1
Bezout(7,26): gcd=1, x=-11, y=3
Fermat inverse(3 mod 11): 4
Fermat inverse(0 mod 11): none
6x = 8 (mod 14): [6, 13]
6x = 5 (mod 14): none
0x = 0 (mod 7): [0, 1, 2, 3, 4, 5, 6]
12x = 9 (mod 21): [6, 13, 20]
inverse(42 mod 2017): 1969
m<=1 rejected: true
```

### 9.2. Ý nghĩa hàm extendedGcd

Hàm riêng `extendedGcd(a,b)` nhận **hai số không âm**. Ở nhánh cơ sở b=0, nó trả:

```text
gcd=a, x=1, y=0
```

vì `a*1+0*0=a`.

Ở mỗi nhánh đệ quy, nó nhận hệ số Bézout của cặp `(b,a mod b)` rồi biến đổi theo thương `a/b`. Trả về:

\[
a\cdot x+b\cdot y=\gcd(a,b).
\]

Hàm `inverse` đã chuẩn hóa a sang khoảng `0..m-1`, còn m≥2, nên tiền điều kiện không âm được bảo đảm.

### 9.3. Ý nghĩa Optional

Nghịch đảo **có thể không tồn tại**. Dùng:

```java
Optional<BigInteger>
```

giúp người gọi phân biệt kết quả hợp lệ với trường hợp không có nghịch đảo. Không nên trả 0 để biểu thị thất bại, vì 0 có thể bị hiểu sai trong một API khác; riêng với m≥2, 0 không phải nghịch đảo, nhưng dùng Optional vẫn rõ ý hơn.

`inverse(6,9)` trả `Optional.empty()` thay vì phép tính sai.

### 9.4. Vì sao BigInteger.mod thay vì %

`BigInteger.mod(modulus)` trả số trong `[0,m)` khi m>0. Đây là cách trực tiếp để xử lý a âm và hệ số Bézout âm.

Ví dụ:

```text
a = -3
m = 11

normalize(-3,11) = 8
inverse(8,11)    = 7
```

Vì `8*7=56≡1(mod 11)`, kết quả là 7.

### 9.5. Hàm inverseFermat không thay thế kiểm tra điều kiện

Hàm `inverseFermat` kiểm tra p lớn hơn 1, chạy `isProbablePrime(100)` để **lọc hợp số với độ tin cậy cao**, sau đó chuẩn hóa a và trả rỗng nếu a≡0(mod p).

Hãy nhớ: `isProbablePrime` là kiểm tra **xác suất**; lập luận Fermat trong toán học cần p thật sự nguyên tố. Trong chương trình mẫu, p=11 là số nguyên tố nhỏ dễ xác minh độc lập.

### 9.6. SolutionFamily là gì?

Với phương trình có nghiệm, `SolutionFamily` lưu:

- `first`: nghiệm nhỏ nhất theo lớp modulo `m/d`, nằm trong `0..m/d-1`.
- `step`: `m/d`, khoảng cách giữa các nghiệm chuẩn.
- `count`: `d=gcd(a,m)`, số nghiệm modulo m.
- `modulus`: môđun gốc m.

Các nghiệm:

\[
first+k\cdot step,\quad k=0,\ldots,count-1.
\]

Thay vì luôn tạo danh sách dài count, object giữ biểu diễn **nén**. Hàm `listAtMost(maximum)` chỉ tạo danh sách nếu count≤maximum. Nếu count quá lớn, nó báo lỗi có chủ đích thay vì cố cấp phát RAM vô hạn.

### 9.7. Vì sao không tính inverse trong nhánh a≡0?

Nếu a chia hết cho m thì d=m. Sau khi chia cả a,b,m cho d sẽ có môđun mới `m/d=1`, nằm ngoài hợp đồng của `inverse`.

Vì vậy `solveLinear` xử lý thẳng:

- Nếu b chia hết cho m: tất cả m nghiệm.
- Nếu không: vô nghiệm.

Điều kiện kiểm tra `b.mod(d)==0` đã loại trường hợp vô nghiệm trước khi đi vào nhánh này.

### 9.8. An toàn số học

Các phép tính:

```text
a*x + m*y
inverse * reducedB
first + k*step
```

có thể vượt phạm vi long với đầu vào lớn. `BigInteger` tránh tràn số nguyên, nhưng bộ nhớ và thời gian vẫn phụ thuộc kích thước số.

Với số lượng nghiệm d quá lớn, không nên xuất tất cả d phần tử. Bản mẫu dùng tham số `maximum` làm chốt kiểm soát tài nguyên khi in danh sách.

---

## 10. Độ phức tạp và lựa chọn kiểu dữ liệu

### 10.1. Một truy vấn nghịch đảo bằng EEA

Với a đã chuẩn hóa trong `0..m−1`:

- Euclid/EEA có O(log m) bước chia dư.
- Bộ nhớ đệ quy O(log m) stack frame; bản lặp có thể dùng O(1) biến số học nếu giả định số cố định.

Nếu m vừa trong long và hệ số trung gian được tính an toàn, bản số nguyên cố định thường rất nhanh.

Nếu dùng BigInteger, phép chia các số có nhiều bit không O(1). Vì vậy cận **O(log m)** chỉ mô tả **số vòng Euclid**, không phải chi phí bit đầy đủ.

### 10.2. Fermat bằng modPow

Với p nguyên tố:

\[
a^{-1}\equiv a^{p-2}\pmod p.
\]

Lũy thừa nhị phân dùng O(log p) lần nhân modulo ở mức trừu tượng. Với BigInteger, chi phí mỗi phép nhân modulo phụ thuộc số bit của p.

### 10.3. Giải phương trình tuyến tính

Tính gcd và inverse trên môđun rút gọn mất O(log m) bước Euclid, chưa kể chi phí BigInteger. Sau đó biểu diễn nghiệm bằng `SolutionFamily` là O(1) đối tượng ở mức cấu trúc.

Nếu **liệt kê** d nghiệm, cần O(d) phần tử đầu ra và ít nhất O(d) thời gian phát sinh nghiệm. Đừng nói toàn bộ hàm giải và in d nghiệm vẫn O(log m).

### 10.4. Khi nào dùng int, long, BigInteger?

- `int` thích hợp cho môđun nhỏ nhưng phép nhân `a*b` dễ tràn.
- `long` mở rộng phạm vi, nhưng `a*b` vẫn có thể tràn nếu a,b gần `10^{18}`.
- `BigInteger` tránh tràn chính xác nhưng tốn CPU/RAM hơn; hợp khi muốn code tổng quát và dễ chứng minh.
- Nếu bài có giới hạn m≤`10^9+7`, có thể dùng `long` cho tích hai phần dư cỡ `10^9` vì tích dưới `10^{18}`, nhưng phải kiểm tra đúng cận.
- Nếu m và thừa số có thể gần `Long.MAX_VALUE`, cần thuật toán nhân modulo tránh overflow hoặc dùng BigInteger.

### 10.5. Số âm trong Java

Đối với kiểu nguyên thủy:

```java
-3 % 11
```

cho **−3**, không phải 8.

Cách chuẩn hóa toán học:

```java
long r = ((a % m) + m) % m;
```

có thể cần cẩn trọng với tổng `(a % m)+m` nếu m rất lớn gần giới hạn long. Với `m≥2` và BigInteger, dùng thẳng:

```java
a.mod(m)
```

để nhận đại diện không âm mà không tràn.

---

## 11. Tính nhiều nghịch đảo modulo một số nguyên tố

Giả sử p nguyên tố đã biết, cần tính `inv[1],inv[2],...,inv[N]` với:

\[
1\le N<p.
\]

Có một công thức tiền xử lý rất hữu ích:

\[
inv[1]=1.
\]

Với `2≤i≤N`:

\[
\boxed{
inv[i]\equiv
-\left\lfloor\frac p i\right\rfloor
\cdot inv[p\bmod i]
\pmod p.
}
\]

Chọn đại diện chuẩn:

\[
inv[i]=
\left(p-\left(\left\lfloor p/i\right\rfloor
\cdot inv[p\bmod i]\right)\bmod p\right)\bmod p.
\]

### 11.1. Chứng minh công thức

Viết:

\[
p=q i+r,\quad 0\le r<i.
\]

Lấy modulo p:

\[
r\equiv-qi\pmod p.
\]

Với p nguyên tố và `1≤i<p`, cả i và r (khi r>0) đều khác 0 modulo p và khả nghịch. Nhân với nghịch đảo của r và i suy ra:

\[
i^{-1}\equiv-q\,r^{-1}\pmod p.
\]

Đó là công thức ở trên với `r=p\bmod i`.

Khi p nguyên tố và i<p, `r=0` chỉ xảy ra nếu i chia hết cho p, tức i=p; trường hợp này đã bị loại bởi điều kiện N<p.

### 11.2. Ví dụ p=11

`inv[1]=1`.

Với i=2:

\[
q=11/2=5,\quad r=1,
\]

\[
inv[2]\equiv-5\,inv[1]\equiv6\pmod{11}.
\]

Với i=3:

\[
q=3,\quad r=2,
\]

\[
inv[3]\equiv-3\cdot6=-18\equiv4\pmod{11}.
\]

Kiểm tra:

\[
2\cdot6=12\equiv1\pmod{11},
\]

\[
3\cdot4=12\equiv1\pmod{11}.
\]

### 11.3. Chi phí

Với modulo p nguyên tố và N<p, bảng cần **O(N)** thời gian và O(N) bộ nhớ nếu mỗi phép nhân modulo được coi là O(1).

Đối với `p≈10^9+7` và tính trên kiểu Java `long`, tích `(p/i)\cdot inv[p\bmod i]` thường nằm dưới khoảng `p^2≈10^{18}`, nhưng phải kiểm tra cận nếu p hoặc N lớn hơn.

### 11.4. Không áp công thức bảng bừa bãi cho hợp số

Với môđun hợp số, các giá trị `r=p\bmod i` có thể **không khả nghịch**, ngay cả khi i khả nghịch; lập luận trên không thể dùng như ở modulo nguyên tố.

Nếu cần nhiều nghịch đảo modulo hợp số, nên kiểm tra gcd cho từng giá trị hoặc khai thác cấu trúc số học phù hợp; đừng dùng công thức prime-table mà không xét điều kiện.

---

## 12. Nghịch đảo modulo trong công thức tổ hợp

Một ứng dụng nổi tiếng là tính:

\[
\binom nk \bmod p
\]

với p nguyên tố.

Nếu `0≤k≤n<p`, các giai thừa `n!,k!,(n-k)!` đều **khác 0 modulo p**, nên đều có nghịch đảo.

Khi đó:

\[
\boxed{
\binom nk\equiv
fact[n]\cdot
invFact[k]\cdot
invFact[n-k]\pmod p.
}
\]

Có thể tiền xử lý:

```text
fact[0]=1
fact[i]=fact[i-1]*i mod p

invFact[n]=fact[n]^(p-2) mod p

for i from n down to 1:
    invFact[i-1]=invFact[i]*i mod p
```

### 12.1. Tại sao phải yêu cầu n<p trong cách cơ bản này?

Nếu `n≥p`, số `n!` chứa thừa số p, nên:

\[
n!\equiv0\pmod p.
\]

Số 0 **không có nghịch đảo modulo p**. Vì vậy không thể dùng trực tiếp công thức với `invFact[n]` trong trường hợp ấy.

Khi n có thể vượt p, cần cách khác như **định lý Lucas**, đếm số mũ p trong giai thừa hoặc phương pháp tổ hợp modulo nguyên tố chuyên biệt.

### 12.2. Môđun hợp số thì sao?

Nếu m hợp số, kể cả khi n<m, một số thừa số trong factorial có thể không nguyên tố cùng nhau với m. Khi đó factorial có thể **không khả nghịch**.

Ví dụ modulo 8, `2!=2` và:

\[
\gcd(2,8)=2.
\]

Không tồn tại `(2!)^{-1} mod 8`. Việc “chia factorial modulo 8” bằng nghịch đảo thông thường là sai.

Muốn tính tổ hợp modulo hợp số, phải dùng kỹ thuật phù hợp với cấu trúc thừa số của m, không tự áp công thức prime.

### 12.3. Tránh chia trước khi lấy dư

Biểu thức:

\[
\frac{n!}{k!(n-k)!}
\]

là một số nguyên thông thường, nhưng nếu tính factorial modulo m **trước khi chia**, thì phần mẫu số có thể không khả nghịch. Hai thao tác này **không tự hoán đổi**.

Đặc biệt:

```text
integer division, then mod
```

không thể được thay bằng:

```text
mod both sides, then integer division
```

nếu không có lập luận số học cụ thể.

---

## 13. Định lý phần dư Trung Hoa và vai trò của nghịch đảo

Xét hệ:

\[
x\equiv a\pmod{m_1},
\]

\[
x\equiv b\pmod{m_2}.
\]

Khi `gcd(m_1,m_2)=1`, định lý phần dư Trung Hoa (**CRT**) bảo đảm có đúng một lớp nghiệm modulo `m_1m_2`.

Một cách xây nghiệm:

\[
x=a+m_1t.
\]

Thay vào đồng dư thứ hai:

\[
m_1t\equiv b-a\pmod{m_2}.
\]

Vì `gcd(m_1,m_2)=1`, nghịch đảo `m_1^{-1} mod m_2` tồn tại, nên:

\[
t\equiv(b-a)\,m_1^{-1}\pmod{m_2}.
\]

### 13.1. Ví dụ

```text
x ≡ 2 (mod 3)
x ≡ 3 (mod 5)
```

Đặt `x=2+3t`. Khi đó:

\[
3t\equiv1\pmod5.
\]

Nghịch đảo của 3 modulo 5 là 2, nên:

\[
t\equiv2\pmod5.
\]

Suy ra:

\[
x\equiv2+3\cdot2=8\pmod{15}.
\]

Kiểm tra:

\[
8\bmod3=2,\quad8\bmod5=3.
\]

### 13.2. Khi hai môđun không nguyên tố cùng nhau

Nếu `gcd(m_1,m_2)>1`, nghịch đảo `m_1^{-1} mod m_2` không tồn tại. Nhưng hệ CRT tổng quát **vẫn có thể có nghiệm** nếu hai phần dư tương thích theo ước chung.

Do đó không được kết luận “không có nghịch đảo ⇒ mọi hệ CRT đều vô nghiệm”. Phải giải hệ đồng dư với điều kiện tương thích riêng.

---

## 14. Một số nhận xét toán học mở rộng

### 14.1. Nghịch đảo của tích

Nếu gcd(a,m)=gcd(b,m)=1, cả a và b đều khả nghịch, và:

\[
(ab)^{-1}\equiv a^{-1}b^{-1}\pmod m.
\]

Chứng minh:

\[
(ab)(a^{-1}b^{-1})
=(aa^{-1})(bb^{-1})\equiv1\pmod m.
\]

Nếu một thừa số không khả nghịch, tích cũng không khả nghịch trong vành `\mathbb Z/m\mathbb Z`.

### 14.2. Nghịch đảo của nghịch đảo

Nếu `x=a^{-1} mod m` thì:

\[
x^{-1}\equiv a\pmod m.
\]

Vì `ax≡1` có tính giao hoán. Đây là một phép kiểm thử hữu ích:

```text
inverse(inverse(a,m),m) == normalize(a,m)
```

khi gcd(a,m)=1.

### 14.3. Nghịch đảo của số đối

Nếu a khả nghịch:

\[
(-a)^{-1}\equiv-a^{-1}\pmod m.
\]

Ví dụ a=3,m=11, nghịch đảo a là 4; nghịch đảo của −3 bằng −4≡7 modulo 11.

### 14.4. Nghịch đảo của lũy thừa

Nếu a khả nghịch thì:

\[
(a^k)^{-1}\equiv(a^{-1})^k\pmod m
\]

với k nguyên không âm. Không cần tính a^k thành số nguyên khổng lồ; có thể dùng lũy thừa modulo.

### 14.5. Lũy thừa số mũ âm

Trong nhóm các đơn vị modulo m, ta có thể định nghĩa:

\[
a^{-k}\equiv(a^{-1})^k\pmod m,\quad k>0.
\]

Nhưng nếu gcd(a,m)>1, `a^{-1}` không tồn tại nên ký hiệu số mũ âm không hợp lệ theo phép nhân modulo ấy.

### 14.6. Đếm những số có nghịch đảo

Từ 0 tới m−1 có đúng `φ(m)` giá trị nguyên tố cùng nhau với m và có nghịch đảo. Với m nguyên tố p, có p−1 phần tử khả nghịch; với m=12, chỉ 1,5,7,11 khả nghịch nên `φ(12)=4`.

### 14.7. Không được chọn nghịch đảo bằng phép chia thực

Lấy `1.0/a` trên số thực rồi làm tròn không có ý nghĩa để giải `ax≡1(mod m)`. Nghịch đảo modulo thuộc **lớp đồng dư số nguyên**, cần kiểm tra và tính bằng số học nguyên chính xác.

---

## 15. Các lỗi triển khai phổ biến

1. **Không kiểm tra gcd(a,m)=1**, trả một “nghịch đảo” cho a không khả nghịch.
2. **Dùng `a^{m-2}` cho môđun hợp số**, áp Fermat sai điều kiện.
3. **Dùng Fermat với a chia hết cho p**, mặc dù nghịch đảo của 0 không tồn tại.
4. **Chỉ kiểm tra a≠0**, quên rằng a khác 0 vẫn có thể không khả nghịch modulo hợp số.
5. **Coi mọi phương trình `ax≡b` có nghiệm duy nhất**, bỏ điều kiện `gcd(a,m)\mid b`.
6. **Thấy gcd>1 rồi kết luận mọi `ax≡b` vô nghiệm**, bỏ trường hợp nhiều nghiệm.
7. **Chia a,b cho d nhưng quên chia m cho d**, khiến tập nghiệm sai.
8. **Trả duy nhất nghiệm modulo m/d**, bỏ d nghiệm khi nâng về modulo m.
9. **Không xử lý d=m**, cố gọi inverse với môđun rút gọn 1.
10. **Không chuẩn hóa a âm**, lấy số âm làm kết quả cuối hoặc lỗi mod.
11. **Không chuẩn hóa hệ số Bézout âm**, ví dụ −11 thay vì 15 khi cần đại diện chuẩn.
12. **Nhầm hệ số Bézout của m với hệ số của a**, trả sai nghịch đảo.
13. **Đổi thứ tự a,m khi gọi EEA mà không đổi hệ số**, làm nhầm x,y.
14. **Dùng int nhân hai phần dư lớn**, tràn trước `%`.
15. **Dùng long cho bài có môđun gần 2^63**, nhân/trừ hệ số có thể tràn.
16. **Tưởng BigInteger khiến phép số học O(1)**, quên chi phí bit.
17. **Không từ chối m≤1 theo hợp đồng chương trình**, tạo trường hợp không nhất quán.
18. **Gọi BigInteger.mod với môđun không dương**, ném ArithmeticException.
19. **Dùng `a % m` của Java primitive rồi giả định không âm**, sai với a âm.
20. **Coi kết quả của BigInteger.isProbablePrime là chứng minh chắc chắn**, đánh giá sai mức tin cậy.
21. **Làm n! modulo p rồi nghịch đảo khi n≥p**, thực tế n!≡0.
22. **Áp công thức inv[i] của môđun nguyên tố cho môđun hợp số**, thiếu điều kiện cần.
23. **Liệt kê mọi nghiệm khi d rất lớn**, có thể hết RAM.
24. **Không kiểm tra kết quả bằng `a*x mod m==1`**, bỏ lỗi logic dễ phát hiện.
25. **Không kiểm tra các nghiệm của `ax≡b` bằng vét cạn trên m nhỏ**, bỏ lỗi nâng nghiệm.
26. **Đánh đồng số đại diện nguyên vô hạn với số nghiệm modulo m**, không xác định phạm vi chuẩn.
27. **Nhầm “nghịch đảo không tồn tại” với “phương trình tuyến tính luôn vô nghiệm”**.
28. **Dùng phép chia nguyên để mô phỏng phân số modulo**, sai nếu mẫu số khả nghịch nhưng phép chia nguyên cắt phần thập phân.
29. **Quên số mũ 0 trong Fermat với p=2**, bỏ trường hợp hợp lệ.
30. **Quên rằng kết quả inverse duy nhất theo lớp**, có thể nhận Bézout x khác giữa những triển khai nhưng sau chuẩn hóa phải bằng nhau.

---

## 16. Kiểm thử độc lập và các bất biến

### 16.1. Oracle nghịch đảo bằng vét cạn

Với môđun m nhỏ, kiểm tra mọi x trong `0..m-1`:

```text
BRUTE_INVERSE(a,m):
    require m>=2
    answers = []

    for x = 0..m-1:
        if normalize(a*x,m) == 1:
            answers.add(x)

    return answers
```

Nếu gcd(a,m)=1, danh sách phải có **đúng một phần tử** và bằng kết quả EEA đã chuẩn hóa.

Nếu gcd(a,m)>1, danh sách phải **rỗng**.

### 16.2. Oracle phương trình tuyến tính

Với a,b,m nhỏ:

```text
BRUTE_SOLVE(a,b,m):
    answers = []

    for x = 0..m-1:
        if normalize(a*x-b,m) == 0:
            answers.add(x)

    return answers
```

So danh sách này với:

\[
\{x_0+k(m/d)\mid k=0,\ldots,d-1\}
\]

khi d chia b, hoặc danh sách rỗng khi d không chia b.

### 16.3. Các ca bắt buộc

| a | m | Inverse |
| ---: | ---: | --- |
| 3 | 11 | 4 |
| 7 | 26 | 15 |
| 10 | 17 | 12 |
| 6 | 9 | Không có |
| −3 | 11 | 7 |
| 0 | 7 | Không có |
| 1 | 2 | 1 |
| 14 | 33 | 26 |
| 42 | 2017 | 1969 |

Các bài `ax≡b`:

| Phương trình | Nghiệm chuẩn |
| --- | --- |
| `6x≡8(mod 14)` | `[6,13]` |
| `6x≡5(mod 14)` | `[]` |
| `0x≡0(mod 7)` | `[0,1,2,3,4,5,6]` |
| `0x≡1(mod 7)` | `[]` |
| `9x≡0(mod 12)` | `[0,4,8]` |
| `12x≡9(mod 21)` | `[6,13,20]` |

### 16.4. Kiểm thử ngẫu nhiên có giới hạn nhỏ

Sinh nhiều bộ:

```text
m từ 2 tới 50
a từ -60 tới 60
b từ -6 tới 6
```

Đối với từng bộ:

1. Tính nghịch đảo bằng EEA.
2. Tính gcd bằng Euclid độc lập.
3. Vét cạn x trong `0..m-1` để kiểm tra `ax≡1`.
4. Kiểm tra tồn tại nghịch đảo **iff gcd=1**.
5. Giải `ax≡b` bằng công thức rút gọn.
6. Vét cạn mọi x để so tập nghiệm.
7. Kiểm tra trường hợp d=m, a=0 và b âm.
8. Kiểm tra các nghiệm đều nằm trong `0..m-1` và không trùng nhau.

Cách kiểm chứng này bắt được lỗi dấu âm, off-by-one, sai bước nhảy nghiệm và lỗi EEA.

### 16.5. Những bất biến nên assert

Nếu trả nghịch đảo x:

\[
0\le x<m,
\]

\[
(a\cdot x)\bmod m=1,
\]

\[
\gcd(a,m)=1.
\]

Nếu trả họ nghiệm của `ax≡b`:

\[
solutionCount=\gcd(a,m),
\]

\[
stride=m/\gcd(a,m),
\]

và mọi nghiệm chuẩn phải thỏa:

\[
(a\cdot x-b)\bmod m=0.
\]

Nếu kết quả báo “không có nghiệm”, cần kiểm tra:

\[
\gcd(a,m)\nmid b.
\]

### 16.6. Kiểm thử Fermat so với EEA

Với một số nguyên tố p đã biết, thử mọi a trong `1..p-1`:

```text
inverseEEA(a,p)
==
powMod(a,p-2,p)
```

Sau đó thử `a=0,p,2p` và xác minh cả hai hàm đều không trả nghịch đảo.

Đừng dùng kết quả Fermat với môđun hợp số để làm oracle đối chiếu EEA: Fermat không có bảo đảm ở đó.

---

## 17. Bài tập tự kiểm tra

### Bài 1 — Định nghĩa

Nghịch đảo modulo m của a phải thỏa phương trình gì? Nó có duy nhất dưới dạng số nguyên tuyệt đối hay duy nhất theo lớp đồng dư?

### Bài 2 — Điều kiện tồn tại

Nêu điều kiện cần và đủ để a có nghịch đảo modulo `m≥2`.

### Bài 3 — Ví dụ nhỏ

Tìm `3^{-1} mod 11` và xác minh bằng phép nhân.

### Bài 4 — Không tồn tại

Vì sao `6^{-1} mod 9` không tồn tại?

### Bài 5 — Số âm

Tìm nghịch đảo của −3 modulo 11.

### Bài 6 — Bézout

Từ `7(-11)+26(3)=1`, tìm nghịch đảo của 7 modulo 26.

### Bài 7 — Euclid mở rộng

Nếu lời gọi đệ quy cho `bx_1+(a mod b)y_1=g`, hãy biểu diễn hệ số x,y của `ax+by=g`.

### Bài 8 — Tính duy nhất

Chứng minh nếu x,y đều là nghịch đảo modulo m của a thì `x≡y(mod m)`.

### Bài 9 — Khử nhân tử

`2x≡2(mod 8)` có những nghiệm nào? Vì sao `x≡1(mod 8)` không diễn tả đủ?

### Bài 10 — Hợp số

Nghịch đảo của 3 modulo 8 có tồn tại không? Nếu có, bằng bao nhiêu?

### Bài 11 — Fermat sai điều kiện

Vì sao không dùng `3^{8-2} mod 8` để tìm nghịch đảo của 3 modulo 8?

### Bài 12 — Fermat đúng điều kiện

Tìm nghịch đảo của 3 modulo 11 bằng Fermat nhỏ.

### Bài 13 — Prime zero

Với p=11, vì sao 11 không có nghịch đảo modulo 11 dù p nguyên tố?

### Bài 14 — Euler

Với m=8, tính `φ(8)` và dùng Euler để tìm nghịch đảo của 3.

### Bài 15 — Phương trình đồng dư

Nêu điều kiện để `ax≡b(mod m)` có nghiệm theo `d=gcd(a,m)`.

### Bài 16 — Hai nghiệm

Giải `6x≡8(mod 14)` và liệt kê nghiệm chuẩn.

### Bài 17 — Vô nghiệm

Giải `6x≡5(mod 14)`.

### Bài 18 — Ba nghiệm

Giải `12x≡9(mod 21)`.

### Bài 19 — Hệ số 0

Giải `0x≡0(mod 7)` và `0x≡1(mod 7)`.

### Bài 20 — Tổng số nghiệm

Nếu d chia b và `d=gcd(a,m)`, có bao nhiêu nghiệm phân biệt modulo m?

### Bài 21 — Nâng nghiệm

Sau khi giảm `ax≡b(mod m)` thành `a'x≡b'(mod m/d)`, làm sao lấy đủ nghiệm modulo m?

### Bài 22 — Java BigInteger

Vì sao `BigInteger.mod(m)` với m>0 thuận tiện hơn toán tử `%` của long đối với a âm?

### Bài 23 — Tràn số

Nếu môđun gần giới hạn long, vì sao `(a*b)%m` có thể sai dù a,b đều trong khoảng 0..m-1?

### Bài 24 — Many inverses

Nêu công thức tiền xử lý `inv[i]` modulo một số nguyên tố p và điều kiện cho i.

### Bài 25 — Tổ hợp

Vì sao công thức factorial-inverse đơn giản cho `C(n,k) mod p` yêu cầu n<p nếu dùng `invFact[n]`?

### Bài 26 — CRT

Giải hệ `x≡2(mod 3)` và `x≡3(mod 5)` bằng nghịch đảo modulo.

### Bài 27 — Double inverse

Nếu a khả nghịch, kết quả `inverse(inverse(a,m),m)` bằng gì modulo m?

### Bài 28 — Test oracle

Mô tả cách kiểm chứng thuật toán inverse bằng vét cạn khi m≤50.

### Bài 29 — Phân biệt bài toán

Vì sao “a không có nghịch đảo” không đồng nghĩa `ax≡b(mod m)` chắc chắn vô nghiệm?

### Bài 30 — Môđun 1

Tại sao mã mẫu chủ động từ chối m=1, và điều đó ảnh hưởng thế nào đến nhánh a≡0(mod m) trong hàm giải phương trình?

### Đáp án gợi ý

1. `ax≡1(mod m)`; nghịch đảo duy nhất theo **lớp đồng dư modulo m**, không duy nhất như số nguyên.
2. `gcd(a,m)=1`.
3. `4`; vì `3*4=12≡1(mod 11)`.
4. `gcd(6,9)=3`, mọi `6x` chia hết cho 3 nên không thể đồng dư 1 modulo 9.
5. `7` vì `(-3)*7=-21≡1(mod 11)`.
6. Hệ số của 7 là −11, chuẩn hóa `−11 mod26=15`.
7. `x=y_1` và `y=x_1-(a div b)y_1`.
8. Từ `a(x-y)≡0` và gcd(a,m)=1, khử a hợp lệ để có `x-y≡0`.
9. `x=1,5(mod 8)`; vì gcd(2,8)=2, chỉ suy ra `x≡1(mod 4)`.
10. Có; `3^{-1}≡3(mod 8)` vì `3*3=9≡1`.
11. Môđun 8 hợp số, không thỏa điều kiện Fermat; `3^6 mod8=1` không phải nghịch đảo.
12. `3^9 mod11=4`.
13. `11≡0(mod 11)`, gcd(11,11)=11 nên không có nghịch đảo.
14. `φ(8)=4`; `3^{φ(8)-1}=3^3=27≡3(mod 8)`.
15. Có nghiệm **iff d chia b**.
16. d=2, giảm thành `3x≡4(mod 7)`, nghiệm `[6,13]` modulo 14.
17. Vô nghiệm vì 2 không chia 5.
18. d=3, nghiệm `[6,13,20]` modulo 21.
19. Phương trình thứ nhất có cả bảy lớp `0..6`; phương trình thứ hai vô nghiệm.
20. Đúng d nghiệm modulo m.
21. Nếu x0 là nghiệm chuẩn modulo m'=m/d, lấy `x0+k*m'` với k=0..d−1.
22. `BigInteger.mod` trả đại diện không âm khi m dương, không tràn và không cần sửa dấu như long `%`.
23. Phép nhân a*b có thể vượt giới hạn long **trước khi** lấy dư.
24. `inv[1]=1`, `inv[i]=-(p div i)*inv[p mod i] mod p`, với p nguyên tố và `1≤i<p`.
25. Khi n≥p, `n!≡0(mod p)` nên không khả nghịch; không thể lấy `invFact[n]` thông thường.
26. `x≡8(mod 15)`.
27. `a mod m`.
28. Duyệt x từ 0 tới m−1, kiểm tra `ax≡1`, đối chiếu với gcd và kết quả EEA.
29. `ax≡b` có thể có d>1 nghiệm nếu gcd(a,m)=d chia b, dù `ax≡1` không có nghiệm.
30. Vì m=1 là vành suy biến với quy ước đặc biệt; hàm giải khi d=m phải trả “mọi lớp dư” mà **không gọi inverse trên m/d=1**.

---

## Ghi nhớ

**Nghịch đảo modulo m của a tồn tại khi và chỉ khi `gcd(a,m)=1`, với `m≥2`**. Nếu tồn tại, nghịch đảo là duy nhất **theo lớp đồng dư**, và có thể tính tổng quát bằng **Euclid mở rộng** nhờ hệ số Bézout:

\[
ax+my=1\implies x\equiv a^{-1}\pmod m.
\]

Nếu môđun p là số nguyên tố và `a\not\equiv0(mod p)`, **Fermat nhỏ** cho:

\[
a^{-1}\equiv a^{p-2}\pmod p.
\]

Không dùng công thức Fermat cho môđun hợp số; không “chia đồng dư” khi hệ số không khả nghịch.

Với phương trình `ax≡b(mod m)`, đặt `d=gcd(a,m)`:

- Nếu `d\nmid b`: **không có nghiệm**.
- Nếu `d\mid b`: có **đúng d nghiệm phân biệt modulo m**. Khi `m/d≥2`, giải bằng nghịch đảo của `a/d` theo môđun `m/d` rồi nâng nghiệm `x=x0+k(m/d)`; nếu `d=m` và `b≡0(mod m)`, mọi lớp dư đều là nghiệm.

Khi lập trình Java, **chuẩn hóa số âm**, dùng **BigInteger** nếu cần tránh overflow, luôn xác minh nghịch đảo bằng `a*x≡1(mod m)` và nghiệm đồng dư bằng `a*x≡b(mod m)`.
