# Biến đổi ngược và khôi phục hệ số tích

**Biến đổi ngược (inverse transform)** là bước đưa dữ liệu từ **miền tần số/giá trị tại các điểm đánh giá** trở lại **các hệ số của đa thức**. Trong phép nhân đa thức bằng FFT hoặc NTT, sau khi biến đổi thuận hai dãy hệ số và nhân các giá trị tương ứng, ta **chưa có các hệ số tích**. Phải thực hiện **biến đổi ngược**, dùng đúng dấu/căn nguyên thủy nghịch đảo và **chuẩn hóa theo độ dài biến đổi**. Nếu thiếu bước cuối này, kết quả thường bị nhân lên N lần, đảo sai thứ tự hoặc trở thành **tích chập vòng** thay vì **tích chập tuyến tính** mong muốn.

Bài học thuộc nhóm **Đa thức và biến đổi** của Computer Science Algorithms, tập trung vào **biến đổi ngược và khôi phục hệ số tích**. Nội dung giải thích công thức DFT/IDFT và NTT/INTT, phép nhân trong miền biến đổi, đệm số 0 để tránh aliasing, điều kiện tồn tại căn nguyên thủy và nghịch đảo modulo, bảo đảm số học chính xác, chứng minh bằng tính trực giao của căn đơn vị, Java 17+ cài đặt NTT thuận/ngược, ước lượng độ phức tạp, các lỗi thường gặp và bộ kiểm thử đối chiếu độc lập.

## 1. Bài toán gốc: cần khôi phục hệ số nào?

Cho hai đa thức:

`A(x)=a₀+a₁x+…+a_(m−1)x^(m−1)`,

`B(x)=b₀+b₁x+…+b_(k−1)x^(k−1)`.

Tích của chúng:

`C(x)=A(x)B(x)=c₀+c₁x+…+c_(m+k−2)x^(m+k−2)`,

với hệ số:

`c_t=Σ_(i+j=t) aᵢbⱼ`.

Tổng chỉ chạy qua các cặp chỉ số hợp lệ `0≤i<m`, `0≤j<k`. Đây là **tích chập tuyến tính (linear convolution)** của hai dãy hệ số.

Ví dụ:

~~~text
A(x) = 1 + 2x + 3x²          a = [1, 2, 3]
B(x) = 4 + 5x               b = [4, 5]

C(x) = 4 + 13x + 22x² + 15x³
c = [4, 13, 22, 15]
~~~

Tính trực tiếp:

- `c₀=1·4=4`.
- `c₁=1·5+2·4=13`.
- `c₂=2·5+3·4=22`.
- `c₃=3·5=15`.

Nếu cả hai dãy **không rỗng**, độ dài dãy hệ số tích theo quy ước trả về đầy đủ là:

`L=m+k−1`.

Chương trình vẫn trả đúng L phần tử **kể cả khi một số hệ số đầu/cuối bằng 0**. Với dãy rỗng, demo định nghĩa kết quả là dãy rỗng `[]`; đây là quy ước API cho biểu diễn đa thức không có hệ số.

### So sánh cách nhân trực tiếp và cách biến đổi

| Phương án | Cách thực hiện | Độ phức tạp chính |
| --- | --- | --- |
| Nhân từng cặp hệ số | Với mọi i,j cộng `aᵢbⱼ` vào `c_(i+j)` | `O(mk)` |
| DFT/FFT | Biến đổi A, B; nhân từng giá trị; IDFT | `O(N log N)` |
| NTT | NTT thuận A, B; nhân theo điểm; INTT | `O(N log N)` |

Ở hai phương án biến đổi, `N` là độ dài biến đổi được chọn **ít nhất bằng L**. Khi dùng FFT/NTT radix-2, thường chọn **lũy thừa của 2 nhỏ nhất không nhỏ hơn L**.

**Trọng tâm của bài:** vì sao nhân các phần tử trong miền biến đổi cho hệ số tích sau phép **biến đổi ngược**, và phải làm gì để nhận đúng dãy `c₀,c₁,…`.

## 2. Từ hệ số đến các giá trị: trực giác đánh giá đa thức

Một đa thức bậc không vượt N−1 được xác định bởi N giá trị tại **N điểm phân biệt** trên trường thích hợp. Biến đổi Fourier rời rạc là cách đánh giá đa thức tại các lũy thừa của một **căn nguyên thủy bậc N**.

Gọi `ω` là căn nguyên thủy bậc N, nghĩa là:

`ω^N=1`,

và `ω^t≠1` với mọi `1≤t<N`.

Ta đệm các hệ số về đúng N phần tử:

`a=(a₀,…,a_(N−1))`,

trong đó các hệ số không tồn tại ban đầu được xem bằng 0. Biến đổi thuận là:

`Â_k=Σ_(j=0)^(N−1) aⱼ ω^(jk)`,  với `k=0,…,N−1`.

Đây chính là giá trị của đa thức tại `x=ω^k`:

`Â_k=A(ω^k)`.

Với B cũng tương tự:

`B̂_k=B(ω^k)`.

Khi đã có hai dãy biến đổi, nhân **từng chỉ số**:

`Ĉ_k=Â_k·B̂_k`.

Do phép đánh giá đa thức bảo toàn phép nhân:

`Ĉ_k=A(ω^k)B(ω^k)=C(ω^k)`.

Như vậy, `Ĉ` là các **giá trị của tích C tại N điểm**, chưa phải các hệ số. Bước khôi phục phải **nội suy** dãy hệ số từ N giá trị đó. DFT/NTT ngược là phép nội suy này trong điều kiện phù hợp.

### Ví dụ nhỏ bằng giá trị tại hai điểm

Lấy hai hệ số `a=[2,3]` và N=2. Trong trường các số nguyên modulo 17, căn nguyên thủy bậc 2 là `ω=−1≡16 (mod 17)`.

- `Â₀=2+3=5 (mod 17)`.
- `Â₁=2+3·16=50≡16 (mod 17)`.

Vì vậy `NTT₂([2,3])=[5,16]`.

Phép biến đổi ngược dùng `ω^(−1)=16` và `2^(−1)≡9 (mod17)`:

- `a₀=9·(5+16)≡9·4≡2 (mod17)`.
- `a₁=9·(5+16·16)≡9·(5+1)≡3 (mod17)`.

Ta **khôi phục đúng [2,3]**. Nếu quên nhân nghịch đảo của 2, ta sẽ thu được `[4,6]` thay vì `[2,3]`.

## 3. DFT và phép biến đổi ngược trong số phức

Với DFT thông thường trên số phức, một quy ước phổ biến là:

`ω_N=exp(−2πi/N)`.

**DFT thuận:**

`X_k=Σ_(j=0)^(N−1) x_j exp(−2πijk/N)`.

**DFT ngược (IDFT):**

`x_j=(1/N) Σ_(k=0)^(N−1) X_k exp(+2πijk/N)`.

Hai khác biệt quan trọng so với công thức thuận:

1. **Đảo dấu góc:** hàm mũ âm trong thuận trở thành hàm mũ dương trong ngược.
2. **Chia cho N:** mỗi hệ số kết quả được nhân `1/N`.

Chỉ thực hiện một trong hai bước **chưa đủ** để được nghịch đảo đúng.

### Ví dụ DFT/IDFT với N=4

Cho `x=[1,2,0,0]`, dùng quy ước DFT có dấu âm:

~~~text
DFT(x) = [3, 1-2i, -1, 1+2i]
IDFT(DFT(x)) = [1, 2, 0, 0]
~~~

Nếu bỏ phần `1/4` của IDFT, ta nhận `[4,8,0,0]`. Nếu thay đổi dấu của DFT ngược nhưng không thay đổi chuẩn hóa, kết quả cũng không đúng nguyên dãy x theo tổng quát.

### Công thức dùng liên hợp

Với dãy phức và cách định nghĩa dấu ở trên:

`IDFT(X)=conj(DFT(conj(X)))/N`.

Công thức giúp tái sử dụng hàm FFT thuận để tính FFT ngược nếu các phép liên hợp và chia N được thực hiện đúng. Tuy nhiên ở chương trình Java dưới đây, ta dùng **NTT trên trường hữu hạn**, nơi phép “liên hợp phức” không áp dụng; thay vào đó dùng **căn nguyên thủy nghịch đảo modulo**.

### Vấn đề sai số số thực

FFT số phức thường sử dụng `double`, vì vậy kết quả nghịch đảo có thể gần một số nguyên, chẳng hạn `21.9999999997` thay vì đúng 22. Với hệ số tích nguyên và giới hạn độ lớn phù hợp, người ta thường:

- Lấy phần thực khi hệ số lý thuyết là thực.
- Kiểm tra phần ảo gần 0.
- Làm tròn về số nguyên gần nhất.
- Đảm bảo chặn sai số đủ nhỏ trong miền dữ liệu đang xử lý.

**Không thể mặc nhiên làm tròn là luôn chính xác** nếu hệ số lớn, N lớn hoặc sai số tích lũy không được kiểm soát. Đó là lý do nhiều bài toán số học dùng **NTT** để nhận kết quả **chính xác modulo một số nguyên tố**.

## 4. NTT: biến đổi Fourier trên trường hữu hạn

**Number Theoretic Transform (NTT)** thay số phức bằng số nguyên modulo một số nguyên tố `p`.

Với NTT trên `𝔽_p`:

- Chọn p nguyên tố.
- Chọn N sao cho `N | (p−1)`, đảm bảo tồn tại căn nguyên thủy bậc N trong `𝔽_p`.
- Chọn `ω` có bậc đúng bằng N.
- Dùng cộng, trừ, nhân, lũy thừa **modulo p**.
- N phải **khác 0 modulo p**, để tồn tại `N^(−1)`.

NTT thuận:

`X_k=Σ_(j=0)^(N−1) x_j ω^(jk) (mod p)`.

NTT ngược:

`x_j=N^(−1) Σ_(k=0)^(N−1) X_k ω^(−jk) (mod p)`.

Nghịch đảo nhân `N^(−1)` **không phải phép chia nguyên thông thường**. Theo định lý Fermat nhỏ (vì p nguyên tố và N không chia hết cho p):

`N^(−1) ≡ N^(p−2) (mod p)`.

Tương tự:

`ω^(−1)≡ω^(p−2) (mod p)`.

Vì vậy cùng một hàm lũy thừa nhanh `modPow` có thể tìm các nghịch đảo.

### Mô-đun NTT phổ biến

Chương trình Java dùng:

`p=998244353=119·2²³+1`.

Giá trị `g=3` là căn nguyên thủy (primitive root) modulo p. Với độ dài biến đổi `N=2^t` và `0≤t≤23`:

`ω_N=3^((p−1)/N) mod p`.

Đây là căn nguyên thủy bậc N. Vì vậy độ dài lũy thừa của 2 tối đa trong cài đặt là:

`N_max=2²³=8 388 608`.

**Không được tự tăng N lên 2²⁴** với mô-đun này, dù bộ nhớ còn đủ: vì 2²⁴ **không chia hết p−1**, công thức không tạo được căn nguyên thủy bậc 2²⁴.

Trong Java, mọi giá trị dư nằm trong `[0,p−1]`. Tích của hai giá trị dư nhỏ hơn `(p−1)²≈9.96·10¹⁷`, vẫn nằm trong giới hạn `long` có dấu (~9.22·10¹⁸). Vì vậy **nhân modulo bằng long là an toàn với chính p này**; điều đó không đúng với mọi mô-đun 64 bit khác.

### Hệ số âm khi chuyển vào trường

`−3 mod p = p−3 = 998244350`.

Hàm chuẩn hóa đúng phải xử lý dấu âm của phép `%` trong Java:

~~~java
static long normalize(long value) {
    long residue = value % 998244353L;
    return residue < 0 ? residue + 998244353L : residue;
}
~~~

Đây là **mảnh mã minh họa**. Đầu ra NTT luôn biểu diễn mỗi hệ số bằng **phần dư chuẩn** trong `0..p−1`, chứ không bắt buộc hiển thị hệ số có dấu âm ban đầu.

## 5. Vì sao biến đổi ngược khôi phục đúng?

Xét dãy x có N phần tử trên trường 𝔽_p, với ω là căn nguyên thủy bậc N và N có nghịch đảo modulo p.

Áp dụng thuận rồi ngược:

`x'_j = N^(−1) Σ_k [Σ_t x_t ω^(tk)] ω^(−jk)`.

Đổi thứ tự tổng:

`x'_j=N^(−1) Σ_t x_t [Σ_(k=0)^(N−1) ω^((t−j)k)]`.

Đặt `r=ω^(t−j)`. Ta có tổng cấp số nhân:

`1+r+…+r^(N−1)`.

- Khi `t=j`, `r=1`, tổng bằng N.
- Khi `t≠j` và `0≤t,j<N`, vì ω có bậc **đúng N**, `r≠1` nhưng `r^N=1`. Do đó tổng bằng `(r^N−1)/(r−1)=0` trong trường.

Vậy mọi số hạng t≠j bị triệt tiêu; còn lại:

`x'_j=N^(−1)·N·x_j=x_j`.

Đây là **tính trực giao của các lũy thừa của căn đơn vị**. Nó giải thích đồng thời:

- Tại sao cần ω có **bậc chính xác N**.
- Tại sao biến đổi ngược phải dùng **ω^(−1)**.
- Tại sao cần nhân **N^(−1)** sau khi tổng hợp.

Nếu chọn ω sai bậc hoặc quên N^(−1), lập luận triệt tiêu ở trên không còn cho kết quả cần thiết.

## 6. Từ tích theo điểm về tích chập: định lý tích chập

Sau khi đệm hai dãy hệ số a,b lên độ dài N, gọi:

`A_k=NTT_N(a)_k`,

`B_k=NTT_N(b)_k`,

`D_k=A_k B_k mod p`.

Biến đổi ngược:

`c=INTT_N(D)`.

Kết quả này về bản chất là **tích chập vòng dài N**:

`c_t = Σ_(i+j≡t mod N) a_i b_j (mod p)`.

Điều kiện `i+j≡t mod N` cho phép các chỉ số **quấn vòng**: hệ số ở bậc N, N+1, ... của tích thực có thể cộng ngược về các vị trí thấp hơn.

### Tích chập vòng khác tích chập tuyến tính

Cho:

~~~text
a = [1, 2, 3]
b = [4, 5, 6]

Tích chập tuyến tính:
[4, 13, 28, 27, 18]   (độ dài 5)
~~~

Nếu ép biến đổi độ dài `N=4`, hệ số bậc 4 bằng 18 bị quấn về bậc 0:

~~~text
Tích chập vòng N=4:
[4+18, 13, 28, 27] = [22, 13, 28, 27]
~~~

Điều này **không phải lỗi NTT ngược**: NTT dài 4 đang trả đúng **tích chập vòng modulo x⁴−1**. Lỗi nằm ở chỗ người lập trình muốn tích chập tuyến tính nhưng chọn N quá nhỏ.

### Điều kiện zero padding để khôi phục hệ số tích tuyến tính

Nếu a có m phần tử và b có k phần tử, hệ số tích có các chỉ số từ 0 tới m+k−2. Chọn:

`N≥m+k−1`.

Khi đó không có cặp `i+j` nào đạt N hoặc lớn hơn, nên không thể quấn vào chỉ số thấp; **tích chập vòng trùng với tích chập tuyến tính** trên L phần tử đầu.

Với NTT radix-2 ở bài này, chọn:

`N=2^ceil(log₂(m+k−1))`,

tức lũy thừa của 2 nhỏ nhất không nhỏ hơn L. Không đệm để hai dãy có độ dài bằng **max(m,k)** rồi mặc nhiên nghĩ đã đủ; cần N cho **tích**, không chỉ cho từng toán hạng.

Ví dụ đầu bài:

~~~text
a = [1, 2, 3], b = [4, 5]
L = 3 + 2 - 1 = 4
N = 4

a_padded = [1, 2, 3, 0]
b_padded = [4, 5, 0, 0]

c = INTT(NTT(a_padded) * NTT(b_padded))
  = [4, 13, 22, 15]
~~~

Nếu L=5, cần N=8 chứ không thể chọn N=4.

## 7. Đi từng bước biến đổi ngược trên butterfly

NTT dùng **phân rã Cooley–Tukey radix-2**. Dữ liệu có độ dài N là lũy thừa của 2 và được đưa về thứ tự **bit reversal** trước khi chạy các tầng butterfly.

Mỗi tầng xử lý các khối độ dài:

`len=2,4,8,…,N`.

Trong một khối, đặt:

- `ω_len = g^((p−1)/len) mod p` cho biến đổi thuận.
- `ω_len^(−1)` cho biến đổi ngược.
- `w=1,ω_len,ω_len²,…` cho các cặp butterfly.

Mỗi butterfly nhận hai giá trị u,v đã nhân hệ số xoay w:

`u=a[i+j]`,

`v=a[i+j+len/2]·w mod p`.

Ghi:

`a[i+j]=(u+v) mod p`,

`a[i+j+len/2]=(u−v) mod p`.

Ở biến đổi **ngược**, cấu trúc butterfly và thứ tự bit reversal **giống cách thực hiện thuận**, nhưng căn xoay được thay bằng **nghịch đảo của nó**. Sau tầng cuối, **mỗi phần tử phải nhân thêm `N^(−1) mod p`**.

Cách diễn đạt “đổi dấu góc” của FFT phức trở thành “đổi căn nguyên thủy sang nghịch đảo” của NTT. Với gốc g cố định, có thể tính `ω_len^(−1)=modPow(ω_len,p−2)`.

### Các nguồn sai ở butterfly

1. Dùng **ω thuận** trong cả hai chiều rồi chỉ chia N ở cuối.
2. Đổi ω nhưng **quên nhân invN**.
3. Dùng số nguyên âm sau phép trừ mà không cộng p trước khi lấy modulo.
4. Nhân trên `int`, tràn trước khi `%p`.
5. Bit reversal sai hoặc đảo đầu vào **hai lần không đúng vị trí**.
6. Tính căn cho toàn N rồi dùng sai bước mũ cho từng tầng len.
7. Cho phép độ dài không phải lũy thừa của 2 vào thuật toán radix-2.

Code dùng điều kiện n>0, n là lũy thừa của 2 và `n≤2²³` để chặn các trường hợp không có nghĩa trong cài đặt này.

## 8. Khôi phục hệ số có dấu: “modulo p” không có nghĩa “nguyên gốc”

Nếu tính NTT modulo p, hệ số được khôi phục là:

`c_t mod p`,

không phải tự động chính số nguyên `c_t` khi c_t lớn hoặc âm.

Ví dụ:

~~~text
a = [-1, 2]
b = [3, -4]

Tích hệ số nguyên:
[-3, 10, -8]

Hệ số modulo 998244353:
[998244350, 10, 998244345]
~~~

Hai dãy là **tương ứng modulo p**, nhưng không có cùng biểu diễn số nguyên có dấu. Khi biết mọi hệ số thật nằm trong khoảng:

`−p/2 < c_t < p/2`,

có thể khôi phục đại diện có dấu duy nhất bằng quy tắc:

- Nếu phần dư `r≤floor(p/2)`: lấy r.
- Nếu `r>floor(p/2)`: lấy `r−p`.

Trong ví dụ, ta nhận lại `[-3,10,-8]`. Tuy nhiên, nếu hệ số thực có thể là `p−3`, cùng phần dư ấy cũng có thể bị hiểu thành −3 khi chuyển sang đại diện cân bằng. **Không được suy diễn dấu nếu không có chặn biên độ**.

### Khi hệ số vượt mô-đun

Ví dụ một tích có hệ số đúng bằng `p+2`. NTT modulo p trả `2`; thông tin về số lần cộng p đã mất. Không có phép biến đổi ngược đơn mô-đun nào tự lấy lại `p+2` từ phần dư 2.

Để tính **tích hệ số nguyên chính xác vượt giới hạn một mô-đun**, thường cần:

- Dùng nhiều mô-đun NTT độc lập hỗ trợ cùng N.
- Ghép kết quả bằng **Chinese Remainder Theorem (CRT)**.
- Có **chặn độ lớn hệ số** để bảo đảm nghiệm nguyên được xác định duy nhất từ các phần dư; với hệ số có dấu, một chặn đủ thường là tích các mô-đun `P>2B` khi `|c_t|≤B`.
- Hoặc chọn thuật toán số nguyên chính xác khác phù hợp.

Bài Java minh họa **một mô-đun**, vì mục tiêu là học phép biến đổi ngược và khôi phục **hệ số tích modulo p**. Nó không giả vờ tính được mọi hệ số nguyên lớn tùy ý.

## 9. Kiểm chứng toán học bằng các trường hợp nhỏ

### 9.1. Nhân đa thức cơ bản

`(1+2x+3x²)(4+5x)=4+13x+22x²+15x³`.

Kết quả NTT ngược:

`[4,13,22,15]`.

### 9.2. Lỗ hệ số bằng 0

~~~text
a = [2, 0, 1]     A(x)=2+x²
b = [1, 0, 3]     B(x)=1+3x²

C(x) = 2 + 7x² + 3x⁴
c = [2, 0, 7, 0, 3]
~~~

Độ dài tích vẫn là 5, gồm cả các hệ số 0 giữa dãy. N phải ≥5; radix-2 chọn N=8.

### 9.3. Lũy thừa của phần dư âm một

Nếu `a=b=[p−1,p−1]`, mỗi hệ số đầu vào tương đương −1 modulo p. Ta có:

`(−1−x)²=1+2x+x²`.

Do đó kết quả chuẩn modulo p là:

`[1,2,1]`.

### 9.4. Phép biến đổi thuận–ngược phải là hàm đồng nhất

Với mọi dãy `a` có độ dài N hợp lệ:

`INTT(NTT(a))=normalize(a)`,

trong đó mỗi phần tử được giảm về `[0,p−1]`. Đây là phép kiểm thử cực kỳ quan trọng và tách biệt khỏi phép thử nhân đa thức: một cài đặt có thể trả đúng vài tích ngẫu nhiên nhưng vẫn sai về thứ tự hoặc chuẩn hóa trong một nhánh biến đổi.

### 9.5. Độ dài N=1

Với dãy chỉ có một phần tử, NTT thuận/ngược là phép đồng nhất; nghịch đảo của 1 bằng 1. Nhân hai đa thức hằng:

`[5]×[2]=[10]`.

Không được yêu cầu N tối thiểu bằng 2; N=1 là trường hợp hợp lệ của thuật toán.

### 9.6. Hai dãy rỗng hoặc một dãy rỗng

Theo API demo, nếu ít nhất một dãy không có hệ số, kết quả là `[]`. Không truyền dãy độ dài 0 vào `ntt` vì NTT tại N=0 không có căn nguyên thủy hay nghịch đảo độ dài.

Một dãy **có hệ số nhưng tất cả bằng 0**, chẳng hạn `[0,0]`, khác với dãy rỗng. Nhân `[0,0]` với `[5]` cho `[0,0]` vì L=2.

## 10. Phân tích độ phức tạp và giới hạn dữ liệu

Gọi m,k là độ dài hai dãy không rỗng. Chọn N là lũy thừa của 2 nhỏ nhất sao cho `N≥m+k−1`.

- **Đệm số 0 và chuẩn hóa hệ số:** O(N).
- **Hai NTT thuận:** mỗi phép O(N log N).
- **Nhân theo điểm:** O(N).
- **Một NTT ngược và nhân invN:** O(N log N).
- **Cắt kết quả còn L hệ số:** O(L).

Tổng thời gian:

`O(N log N)`

và bộ nhớ phụ:

`O(N)`

cho các mảng độ dài N; bên cạnh đó có O(L) cho kết quả và O(1) biến trong các vòng butterfly. Vì N là lũy thừa 2 tiếp theo sau L, `N<2L` khi L≥2, do đó ta cũng có thể nói thời gian O(L log L) trong giới hạn độ dài được mô-đun hỗ trợ.

**Nhân trực tiếp:** O(mk) thời gian, O(L) bộ nhớ đầu ra. Với m,k rất nhỏ, nhân trực tiếp thường nhanh và đơn giản hơn dù có cận tiệm cận kém hơn.

### Chi phí hàm lũy thừa modulo

Mỗi tầng tính căn nguyên thủy bằng `modPow`, có O(log p) bước. Có O(log N) tầng, thêm O(log N·log p) phép toán. Với p cố định là 998244353 và N đủ lớn, thành phần chính vẫn O(N log N); trong mô hình tổng quát có thể ghi rõ phần chi phí tìm căn và nghịch đảo.

### Giới hạn N và giới hạn bộ nhớ

Với p=998244353, **NTT radix-2 chỉ hỗ trợ N≤2²³**. Ngoài việc kiểm tra N, cần cân nhắc:

- Hai mảng `long[N]` đã chiếm khoảng 16N byte (chưa tính overhead), chưa kể kết quả.
- N=2²³ có thể yêu cầu **hàng trăm MB**, tùy môi trường Java và cách cấp phát.
- Dữ liệu vượt giới hạn hỗ trợ phải dùng mô-đun/thuật toán khác hoặc phân khối, **không** được im lặng tạo NTT sai.

Trong chương trình, phép cộng m+k−1 dùng `long` trước khi đổi thành `int`, tránh tràn phép cộng kích thước mảng kiểu int.

## 11. Java 17+: NTT thuận, NTT ngược và khôi phục hệ số tích

Mã nguồn triển khai một phương án **NTT iterative radix-2**, đầy đủ:

1. Chuẩn hóa hệ số về `[0,p−1]`.
2. Bit-reversal permutation.
3. Các tầng butterfly len=2,4,…,N.
4. Với inverse, dùng căn nguyên thủy nghịch đảo ở từng tầng.
5. **Nhân `N^(−1) mod p` sau tầng cuối**.
6. Nhân đa thức: chọn N từ m+k−1, đệm 0, biến đổi thuận hai mảng, nhân theo điểm, gọi inverse, cắt đúng L hệ số.
7. Hàm `naiveConvolution` độc lập đối chiếu O(mk).
8. Bộ kiểm thử 500 cặp đa thức ngẫu nhiên và 160 mảng thuận–ngược, kể cả N=1.
9. Dùng `long` cho nhân modulo; kiểm soát đầu vào N và phần dư âm.
10. Không sửa trực tiếp hai mảng hệ số đầu vào của người gọi khi nhân đa thức; hàm `ntt` tự thay đổi **mảng được truyền vào**, nhưng `convolution` làm việc trên mảng đệm mới.

**Lưu tệp `InverseTransformProductDemo.java` bằng UTF-8:**

~~~java
import java.util.Arrays;
import java.util.Random;

public class InverseTransformProductDemo {
    static final long MOD = 998_244_353L;
    static final long ROOT = 3L;
    static final int MAX_N = 1 << 23;

    static long normalize(long value) {
        long r = value % MOD;
        return r < 0L ? r + MOD : r;
    }

    static long modPow(long base, long exponent) {
        if (exponent < 0L)
            throw new IllegalArgumentException(
                    "Negative modular exponent");
        long value = normalize(base);
        long answer = 1L;
        while (exponent > 0L) {
            if ((exponent & 1L) != 0L)
                answer = answer * value % MOD;
            value = value * value % MOD;
            exponent >>= 1;
        }
        return answer;
    }

    // In-place iterative radix-2 NTT over F_998244353.
    // inverse=false: transform coefficients to point values.
    // inverse=true:  restore coefficients AND multiply by inv(n).
    static void ntt(long[] a, boolean inverse) {
        int n = a.length;
        if (n == 0 || (n & (n - 1)) != 0 || n > MAX_N) {
            throw new IllegalArgumentException(
                    "NTT size must be a power of 2 in [1, 2^23]");
        }

        // Canonical modular residues also support negative input.
        for (int i = 0; i < n; i++)
            a[i] = normalize(a[i]);

        // Bit-reversal permutation.
        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >> 1;
            while ((j & bit) != 0) {
                j ^= bit;
                bit >>= 1;
            }
            j ^= bit;
            if (i < j) {
                long tmp = a[i];
                a[i] = a[j];
                a[j] = tmp;
            }
        }

        for (int len = 2; len <= n; len <<= 1) {
            // ROOT^((MOD-1)/len) is a primitive len-th root.
            long step = modPow(ROOT, (MOD - 1L) / len);
            if (inverse) step = modPow(step, MOD - 2L);

            for (int start = 0; start < n; start += len) {
                long w = 1L;
                int half = len >> 1;
                for (int j = 0; j < half; j++) {
                    long u = a[start + j];
                    long v = a[start + j + half] * w % MOD;

                    a[start + j] = (u + v) % MOD;
                    a[start + j + half] =
                            (u - v + MOD) % MOD;

                    w = w * step % MOD;
                }
            }
        }

        if (inverse) {
            long invN = modPow(n, MOD - 2L);
            for (int i = 0; i < n; i++)
                a[i] = a[i] * invN % MOD;
        }
    }

    // Return the complete LINEAR convolution modulo MOD.
    // Empty coefficient sequence -> empty result by API convention.
    static long[] convolution(long[] a, long[] b) {
        if (a == null || b == null)
            throw new IllegalArgumentException(
                    "Coefficient arrays cannot be null");
        if (a.length == 0 || b.length == 0)
            return new long[0];

        long needed = (long) a.length + b.length - 1L;
        if (needed > MAX_N)
            throw new IllegalArgumentException(
                    "Convolution length exceeds NTT modulus limit");

        int n = 1;
        while (n < needed) n <<= 1;

        long[] fa = new long[n];
        long[] fb = new long[n];
        for (int i = 0; i < a.length; i++)
            fa[i] = normalize(a[i]);
        for (int i = 0; i < b.length; i++)
            fb[i] = normalize(b[i]);

        ntt(fa, false);
        ntt(fb, false);
        for (int i = 0; i < n; i++)
            fa[i] = fa[i] * fb[i] % MOD;
        ntt(fa, true);

        return Arrays.copyOf(fa, (int) needed);
    }

    // Independent O(m*k) reference, used only on small inputs.
    static long[] naiveConvolution(long[] a, long[] b) {
        if (a.length == 0 || b.length == 0)
            return new long[0];
        long[] result = new long[a.length + b.length - 1];
        for (int i = 0; i < a.length; i++) {
            long x = normalize(a[i]);
            for (int j = 0; j < b.length; j++) {
                long y = normalize(b[j]);
                long term = x * y % MOD;
                result[i + j] = (result[i + j] + term) % MOD;
            }
        }
        return result;
    }

    // Interpretation only when actual signed coefficients
    // are known to lie in (-MOD/2, MOD/2).
    static long[] balancedRepresentatives(long[] residues) {
        long[] answer = new long[residues.length];
        for (int i = 0; i < residues.length; i++) {
            long r = normalize(residues[i]);
            answer[i] = r > MOD / 2L ? r - MOD : r;
        }
        return answer;
    }

    static void show(String name, long[] a, long[] b) {
        long[] result = convolution(a, b);
        long[] oracle = naiveConvolution(a, b);
        if (!Arrays.equals(result, oracle))
            throw new AssertionError("Wrong convolution: " + name);
        System.out.println(name + "=" + Arrays.toString(result));
    }

    static void randomCheck() {
        Random random = new Random(2026L);

        // Verify products with an independent quadratic oracle.
        for (int test = 0; test < 500; test++) {
            int m = random.nextInt(14);
            int k = random.nextInt(14);
            long[] a = new long[m];
            long[] b = new long[k];

            for (int i = 0; i < m; i++)
                a[i] = random.nextInt(20_001) - 10_000L;
            for (int i = 0; i < k; i++)
                b[i] = random.nextInt(20_001) - 10_000L;

            long[] fast = convolution(a, b);
            long[] slow = naiveConvolution(a, b);
            if (!Arrays.equals(fast, slow))
                throw new AssertionError(
                        "Random product mismatch at " + test);
        }
        System.out.println(
                "randomConvolution=PASS (500 pairs)");

        // Verify inverse(forward(x)) = normalize(x).
        for (int test = 0; test < 160; test++) {
            int n = 1 << random.nextInt(6); // 1,2,4,8,16,32
            long[] a = new long[n];
            long[] expected = new long[n];
            for (int i = 0; i < n; i++) {
                a[i] = random.nextInt(20_001) - 10_000L;
                expected[i] = normalize(a[i]);
            }

            ntt(a, false);
            ntt(a, true);
            if (!Arrays.equals(a, expected))
                throw new AssertionError(
                        "Random inverse mismatch at " + test);
        }
        System.out.println(
                "randomRoundTrip=PASS (160 arrays)");
    }

    public static void main(String[] args) {
        show("basic",
                new long[]{1, 2, 3},
                new long[]{4, 5});
        show("signed",
                new long[]{-1, 2},
                new long[]{3, -4});
        show("gaps",
                new long[]{2, 0, 1},
                new long[]{1, 0, 3});
        show("maxResidue",
                new long[]{MOD - 1, MOD - 1},
                new long[]{MOD - 1, MOD - 1});
        show("zeroPolynomial",
                new long[]{0, 0},
                new long[]{5});
        show("constant",
                new long[]{5},
                new long[]{2});
        show("empty",
                new long[0],
                new long[]{2, 3});
        show("bothEmpty",
                new long[0],
                new long[0]);
        show("largeInputs",
                new long[]{
                    1_000_000_000_000L,
                    -1_000_000_000_000L
                }, new long[]{2, -3});

        long[] signedProduct = convolution(
                new long[]{-1, 2},
                new long[]{3, -4});
        System.out.println("signedView="
                + Arrays.toString(
                        balancedRepresentatives(signedProduct)));

        long[] roundTrip = {1, 2, 3, 0};
        ntt(roundTrip, false);
        ntt(roundTrip, true);
        System.out.println("roundTrip="
                + Arrays.toString(roundTrip));

        // Deliberately use N=4 for a product needing L=5.
        // This is CORRECT circular convolution, not linear!
        long[] circularA = {1, 2, 3, 0};
        long[] circularB = {4, 5, 6, 0};
        ntt(circularA, false);
        ntt(circularB, false);
        for (int i = 0; i < 4; i++)
            circularA[i] =
                    circularA[i] * circularB[i] % MOD;
        ntt(circularA, true);
        System.out.println("circular4="
                + Arrays.toString(circularA));

        long root4 = modPow(ROOT, (MOD - 1L) / 4L);
        if (modPow(root4, 4) != 1L ||
                modPow(root4, 2) != MOD - 1L)
            throw new AssertionError("Invalid root order");
        System.out.println("root4Order=4");

        try {
            ntt(new long[]{1, 2, 3}, false);
            throw new AssertionError(
                    "Expected non-power-of-two rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidLength=rejected");
        }

        try {
            ntt(new long[0], true);
            throw new AssertionError(
                    "Expected empty NTT rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("zeroTransform=rejected");
        }

        randomCheck();
    }
}
~~~

### Biên dịch và chạy

Dùng JDK **17 trở lên**, mã UTF-8:

~~~bash
javac -encoding UTF-8 InverseTransformProductDemo.java
java InverseTransformProductDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
basic=[4, 13, 22, 15]
signed=[998244350, 10, 998244345]
gaps=[2, 0, 7, 0, 3]
maxResidue=[1, 2, 1]
zeroPolynomial=[0, 0]
constant=[10]
empty=[]
bothEmpty=[]
largeInputs=[516560941, 205964177, 275719235]
signedView=[-3, 10, -8]
roundTrip=[1, 2, 3, 0]
circular4=[22, 13, 28, 27]
root4Order=4
invalidLength=rejected
zeroTransform=rejected
randomConvolution=PASS (500 pairs)
randomRoundTrip=PASS (160 arrays)
~~~

### Giải thích các dòng quan trọng

**basic:** khôi phục chính xác bốn hệ số `[4,13,22,15]` của tích hai đa thức cơ bản.

**signed:** hệ số nguyên có dấu ban đầu là `[-3,10,-8]`; NTT trả các phần dư chuẩn `[p−3,10,p−8]`. `signedView` chỉ chuyển sang đại diện cân bằng, hợp lý khi đã biết chặn độ lớn.

**gaps:** những hệ số bằng 0 giữa đa thức được bảo toàn, kết quả `[2,0,7,0,3]`.

**maxResidue:** hai dãy chứa p−1, tương đương −1 trong trường. Kết quả `[1,2,1]` chứng minh chương trình không bị tràn `int` trong phép nhân modulo.

**zeroPolynomial:** dãy `[0,0]` vẫn là một dãy hệ số có độ dài 2; tích với `[5]` có độ dài 2, khác quy ước kết quả của dãy rỗng.

**largeInputs:** hệ số đầu vào cỡ 10¹² được chuẩn hóa modulo p trước NTT. Kết quả là hệ số **mod p**, không phải kết quả nguyên lớn ban đầu.

**roundTrip:** biến đổi thuận rồi ngược cùng độ dài 4 khôi phục nguyên dãy; nhánh inverse có nhân `invN` đúng.

**circular4:** minh họa thiếu zero padding. Hai dãy dài 3 nhân nhau cần L=5; N=4 cho `[22,13,28,27]` do hệ số bậc 4 quấn về bậc 0. Đây là dữ liệu mẫu cố ý, **không** phải kết quả tuyến tính đúng.

**root4Order:** kiểm tra căn được dùng cho N=4 có bậc đúng 4: lũy thừa bậc 4 bằng 1, bậc 2 bằng p−1 (khác 1).

**invalidLength/zeroTransform:** NTT radix-2 từ chối độ dài không phải lũy thừa 2 và từ chối N=0; hàm nhân đa thức xử lý đầu vào rỗng **trước khi gọi NTT**.

**randomConvolution:** 500 cặp đa thức ngẫu nhiên gồm cả dãy rỗng và hệ số âm, so toàn bộ dãy tích với thuật toán `O(mk)` độc lập.

**randomRoundTrip:** 160 dãy độ dài `1,2,4,8,16,32`, hệ số âm/dương, được kiểm tra tính chất `INTT(NTT(x))=normalize(x)`. Dòng PASS chỉ xuất hiện khi các phép kiểm đều thành công.

### Giới hạn của bản demo

Chương trình giải **nhân hai dãy hệ số modulo 998244353**. Nó không tự cho kết quả số nguyên chính xác ngoài mô-đun, không triển khai FFT double/CRT, không hỗ trợ N là số không phải lũy thừa của 2 và không hỗ trợ N>2²³. Với mô-đun này, nhân dư bằng `long` là an toàn, nhưng không được sao chép cách nhân ấy sang một mô-đun 64 bit rất lớn mà không xem tràn.

**Sự độc lập của phép kiểm:** `naiveConvolution` không gọi NTT; nó tính từng `aᵢbⱼ` và cộng vào vị trí i+j, nên có thể phát hiện lỗi của bước inverse, zero padding hoặc nhân theo điểm. Kiểm tra thuận–ngược xác minh một bất biến khác. Những bộ test nhỏ không loại trừ mọi lỗi ở N cực lớn, vì vậy chứng minh dựa trên căn nguyên thủy và trường số vẫn là thành phần không thể thiếu.

## 12. Các tình huống dễ nhầm khi áp dụng

### 12.1. Thuận đúng nhưng ngược sai

Nếu NTT thuận hoàn toàn đúng nhưng inverse dùng cùng căn ω thuận, dữ liệu có thể bị biến đổi hoán vị thay vì khôi phục. Trong DFT trên số phức, dùng sai dấu sẽ làm xuất hiện hiệu ứng đảo chỉ số theo modulo N; không thể chỉ “đổi một hệ số” để sửa dữ liệu trong mọi cấu hình. Cách kiểm định cơ bản là **round-trip trên nhiều dãy không đối xứng**.

### 12.2. Quên chia N

Ở NTT, “chia cho N” nghĩa là **nhân nghịch đảo modulo p**, không phải viết `a[i]/=N` bằng chia nguyên Java. Nếu N=4, invN=`748683265` modulo 998244353; việc làm tròn phép chia nguyên thông thường sẽ phá hủy kết quả.

### 12.3. Khôi phục hệ số trước khi nhân

Phép nhân nhanh là:

`INTT(NTT(a) ⊙ NTT(b))`,

với ⊙ là **nhân theo từng phần tử**. Nếu biến đổi ngược hai dãy riêng biệt rồi nhân theo điểm ở miền hệ số, sẽ chỉ nhận `aᵢbᵢ`, **không phải tích chập** `Σ aᵢb_(t−i)`.

### 12.4. Nhầm trật tự và số chiều

NTT là phép biến đổi trên dãy đúng N phần tử. Dữ liệu sau bit reversal cần được xử lý bằng các tầng tương ứng; nếu tự thay đổi thứ tự rồi lấy đầu ra mà không khôi phục đúng thứ tự mong đợi, phần tử ở vị trí k có thể không còn là giá trị tại `ω^k`. Với code iterative DIT chuẩn, bit reversal ở đầu và butterfly theo độ dài tăng dần đưa kết quả về thứ tự chỉ số thông thường.

### 12.5. Trộn hai mô-đun hoặc hai cách biểu diễn

Phải dùng **cùng MOD, cùng N, cùng quy ước căn** cho hai đa thức và phép inverse. Nếu một dãy biến đổi dưới MOD1, dãy còn lại dưới MOD2 rồi nhân trực tiếp từng giá trị, kết quả không còn thuộc một phép toán xác định. Khi dùng nhiều mô-đun CRT, phải tính **từng phép nhân độc lập trong cùng một trường**, sau đó mới ghép kết quả.

### 12.6. Nhân các dãy có độ dài đã là lũy thừa 2

Ngay cả khi a,b cùng dài N=8, tích tuyến tính có độ dài tới **15**. Không thể cứ giữ N=8 vì input đã đủ “đẹp”. Cần đệm lên ít nhất N'=16 để không chồng vòng, trừ khi bài yêu cầu tích chập vòng modulo x⁸−1.

### 12.7. Làm tròn FFT số phức một cách thiếu kiểm soát

IDFT bằng double có thể trả `-0.0000000003` thay vì đúng 0, hoặc `12.999999999` thay vì đúng 13. Nếu hệ số thật là số thực, **không được ép về int**. Nếu hệ số là số nguyên lớn, sai số có thể vượt 1/2; cần bound/kiểm chứng/NTT nhiều mô-đun thay vì tin mọi phép `Math.round`.

## 13. Chọn FFT, NTT hay nhân trực tiếp?

| Nhu cầu | Phương án thường phù hợp | Lý do |
| --- | --- | --- |
| Đa thức rất ngắn | Nhân trực tiếp O(mk) | Đơn giản, ít overhead, dễ chính xác |
| Hệ số nguyên, chỉ cần kết quả mod 998244353, L≤2²³ | NTT + INTT | Không sai số làm tròn |
| Hệ số thực/phức | FFT + IFFT | Tính trên số thực/phức, chấp nhận sai số số học |
| Hệ số nguyên lớn cần kết quả nguyên tuyệt đối | NTT nhiều MOD + CRT hoặc thuật toán nguyên chính xác | Tránh mất thông tin do modulo |
| Phép nhân vòng độ dài N | NTT/FFT dài N | Cần hiểu phép nhân modulo x^N−1 |
| N không phải lũy thừa của 2 | Chọn padding hoặc cấu trúc biến đổi phù hợp | Bản radix-2 cần N=2^t |
| Dữ liệu đầu vào nhiều truy vấn lặp lại | Tiền biến đổi một toán hạng khi phù hợp | Có thể tái sử dụng giá trị trong miền biến đổi cùng N/MOD |

**Với phép nhân đa thức modulo p, NTT ngược là thao tác bắt buộc để lấy hệ số**, không phải phần tối ưu tùy chọn. Độ đúng của NTT phải được xét cùng **quy tắc chọn N**, **root** và **normalization**.

## 14. Những lỗi thường gặp

1. Nhận giá trị tại N điểm sau phép nhân theo điểm rồi in chúng như hệ số tích.
2. Quên chạy biến đổi ngược sau khi nhân hai phổ.
3. Trong DFT phức, dùng cùng dấu góc cho thuận và ngược.
4. Trong NTT, dùng cùng căn ω cho thuận và ngược mà không lấy nghịch đảo.
5. Quên chia N trong IDFT.
6. Dùng chia nguyên `/N` thay vì nhân `N^(−1) mod p` trong INTT.
7. Lấy nghịch đảo modulo bằng cách chia số thực `1.0/N`.
8. Dùng N không chia p−1 nên không có căn nguyên thủy bậc N.
9. Dùng ω có bậc nhỏ hơn N, khiến các điểm đánh giá trùng nhau.
10. Dùng ROOT=3 nhưng tự thay MOD mà không kiểm tra primitive root mới.
11. Chọn N chỉ ≥max(m,k) thay vì ≥m+k−1 cho tích chập tuyến tính.
12. Không đệm hai dãy lên cùng N.
13. Không cắt mảng kết quả về đúng L=m+k−1.
14. Ngầm bỏ các hệ số 0 cuối dù API cần bảo toàn độ dài.
15. Không phân biệt tích chập vòng với tích chập tuyến tính.
16. Nhầm x^N−1 với đa thức tích thông thường khi giải thích wrap-around.
17. Nhân từng phần tử trong miền hệ số thay cho tích chập.
18. Nhân hai phổ được tạo bởi hai mô-đun hoặc hai N khác nhau.
19. Lấy `a[i] * b[i]` bằng int trước `%MOD`, gây tràn.
20. Dùng long nhưng chọn MOD lớn tới mức tích các phần dư vượt Long.MAX_VALUE.
21. Không chuẩn hóa hệ số âm trước NTT.
22. Dùng `(u−v)%MOD` trực tiếp trong Java và để kết quả âm.
23. Bit reversal sai, khiến các tầng butterfly đọc nhầm vị trí.
24. Đảo bit dữ liệu không đúng một lần trong kiểu iterative đang dùng.
25. Cài vòng tầng len tăng không đúng hoặc kết thúc ở N/2 thay vì N.
26. Quên khôi phục hệ số invN **cho mọi phần tử** sau tầng cuối.
27. Cho N=0 vào NTT; không có ý nghĩa root/inverse length.
28. Cho N=3 vào thuật toán radix-2 nhưng vẫn kỳ vọng chạy.
29. Cho N>2²³ với MOD 998244353.
30. Tràn int khi tính độ dài m+k−1 cho mảng cực lớn.
31. Nhầm hệ số sau INTT modulo p với hệ số nguyên âm ban đầu.
32. Dùng đại diện cân bằng r−p mà không bảo đảm chặn biên độ.
33. Nghĩ một mô-đun đủ khôi phục mọi tích nguyên lớn.
34. Dùng CRT nhưng không bảo đảm tích các mô-đun đủ lớn so với hệ số thật.
35. Quên hệ số do zero-padding tạo nên; coi các số 0 mới như kết quả cần in.
36. Tin rằng FFT double luôn khôi phục chính xác bằng làm tròn.
37. Không thử phép biến đổi thuận rồi ngược trên một dãy tùy ý.
38. Chỉ test hệ số dương, bỏ qua số âm và phần dư gần MOD.
39. Chỉ test dãy dài bằng 2 hoặc 4 mà không test độ dài 1.
40. Không test một dãy rỗng, dãy không rỗng toàn 0 và các hệ số trống giữa dãy.
41. Không thử sản phẩm cần N lớn hơn từng input dù input đã là lũy thừa của 2.
42. Không test bằng phép nhân trực tiếp độc lập O(mk).
43. Coi 500 test ngẫu nhiên là bằng chứng đúng với mọi N≤2²³, bỏ qua chứng minh toán học.
44. Quên rằng chuẩn hóa modulo làm mất thông tin nguyên lớn, dù INTT tính chính xác trong trường.
45. Không ghi rõ bài đang giải trên 𝔽_p, trên số phức hay trên số nguyên tùy ý.

## 15. Bài tập có lời giải

**Bài 1.** Hai đa thức có m=3 và k=2 hệ số, tích dài bao nhiêu? **Đáp án:** L=3+2−1=4.

**Bài 2.** Với m=3 và k=3, NTT radix-2 cần N tối thiểu bao nhiêu? **Đáp án:** L=5, chọn N=8.

**Bài 3.** Tích `[1,2,3]×[4,5]` có hệ số nào? **Đáp án:** `[4,13,22,15]`.

**Bài 4.** Tại sao nhân trong miền biến đổi là nhân theo từng k? **Đáp án:** mỗi phần tử thuận là giá trị đa thức tại cùng điểm `ω^k` và `C(ω^k)=A(ω^k)B(ω^k)`.

**Bài 5.** Vì sao phải thực hiện biến đổi ngược sau nhân theo điểm? **Đáp án:** nhân theo điểm cho các **giá trị của tích**, còn biến đổi ngược khôi phục **hệ số**.

**Bài 6.** Công thức IDFT theo quy ước dấu âm của DFT thuận? **Đáp án:** `x_j=(1/N)Σ_k X_k exp(+2πijk/N)`.

**Bài 7.** Trong phép nghịch đảo, dấu góc Fourier thay đổi ra sao? **Đáp án:** từ âm sang dương.

**Bài 8.** Nếu quên chia N sau IDFT, kết quả ra sao? **Đáp án:** thường bằng N lần hệ số đúng.

**Bài 9.** Công thức NTT ngược trên trường 𝔽_p? **Đáp án:** `x_j=N^(−1)Σ_k X_k ω^(−jk) mod p`.

**Bài 10.** Nghịch đảo của N modulo p tính thế nào với p nguyên tố, N không chia p? **Đáp án:** `N^(p−2) mod p`.

**Bài 11.** Vì sao cần căn nguyên thủy ω có bậc chính xác N? **Đáp án:** để bảo đảm các tổng hình học triệt tiêu ở các chỉ số khác nhau, phục vụ công thức nghịch đảo.

**Bài 12.** Với p=998244353, độ dài lũy thừa 2 lớn nhất của NTT demo? **Đáp án:** 2²³.

**Bài 13.** Cơ số g của NTT demo là bao nhiêu? **Đáp án:** g=3.

**Bài 14.** Độ dài N=1 có hợp lệ không? **Đáp án:** có; NTT/INTT là phép đồng nhất và inv1=1.

**Bài 15.** Vì sao phải pad lên ít nhất m+k−1? **Đáp án:** để tích chập vòng không quấn các hệ số bậc ≥N về chỉ số thấp.

**Bài 16.** `[1,2,3]×[4,5,6]` tuyến tính cho kết quả nào? **Đáp án:** `[4,13,28,27,18]`.

**Bài 17.** Nếu cùng bài 16 nhưng dùng tích chập vòng N=4, kết quả nào? **Đáp án:** `[22,13,28,27]`.

**Bài 18.** Tại sao hệ số đầu vòng N=4 là 22? **Đáp án:** c₀=4 và hệ số c₄=18 quấn về vị trí 0, thành 4+18=22.

**Bài 19.** `[2,0,1]×[1,0,3]` có hệ số nào? **Đáp án:** `[2,0,7,0,3]`.

**Bài 20.** Trên trường 𝔽_p, −3 được biểu diễn dưới dạng phần dư chuẩn nào? **Đáp án:** `p−3`.

**Bài 21.** Với p=998244353, giá trị dư chuẩn của −8? **Đáp án:** 998244345.

**Bài 22.** Tích nguyên `[-1,2]×[3,-4]` là gì? **Đáp án:** `[-3,10,-8]`.

**Bài 23.** Tích modulo p của bài 22 là gì? **Đáp án:** `[998244350,10,998244345]`.

**Bài 24.** Khi nào có thể đổi phần dư về đại diện có dấu cân bằng? **Đáp án:** khi biết hệ số nguyên thật nằm trong một khoảng đại diện duy nhất, điển hình `|c_t|<p/2`.

**Bài 25.** NTT một mô-đun có khôi phục được hệ số thật p+2 không? **Đáp án:** không; phần dư chỉ là 2.

**Bài 26.** Muốn số nguyên chính xác vượt p, có thể dùng gì? **Đáp án:** nhiều mô-đun NTT và CRT với chặn biên độ phù hợp hoặc thuật toán chính xác khác.

**Bài 27.** Tại sao phép `(u−v)%p` trên Java có thể cần sửa? **Đáp án:** Java trả phần dư âm nếu u−v âm; cần cộng p trước modulo.

**Bài 28.** Dùng `int` để nhân hai số gần p rồi mới mod có đúng không? **Đáp án:** không; tích có thể tràn int trước khi chia dư.

**Bài 29.** Với MOD≈10^9 và phép nhân hai phần dư, dùng long trong demo có an toàn không? **Đáp án:** có với p=998244353 vì tích <10¹⁸<Long.MAX_VALUE.

**Bài 30.** Độ phức tạp NTT nhân hai dãy sau padding N? **Đáp án:** O(N log N) thời gian, O(N) bộ nhớ phụ.

**Bài 31.** Nhân trực tiếp hai dãy m,k có độ phức tạp gì? **Đáp án:** O(mk), tiện làm oracle trên input nhỏ.

**Bài 32.** Nếu một input rỗng theo API demo, convolution trả gì? **Đáp án:** `[]`; không gọi NTT N=0.

**Bài 33.** `[0,0]×[5]` trả gì? **Đáp án:** `[0,0]` theo quy ước giữ L hệ số.

**Bài 34.** NTT thuận rồi NTT ngược trên cùng dãy phải thỏa tính chất nào? **Đáp án:** khôi phục đúng từng phần dư chuẩn modulo p.

**Bài 35.** Vì sao N=2²⁴ không dùng được ở MOD 998244353? **Đáp án:** 2²⁴ không chia MOD−1, nên thiếu căn nguyên thủy bậc đó trong trường.

**Bài 36.** Nếu a,b có độ dài 8 mỗi bên, N=8 có đủ cho nhân tuyến tính không? **Đáp án:** không; L=15, nên chọn N=16.

**Bài 37.** Tại sao NTT ngược không thể thay bằng việc chia từng hệ số phổ cho N? **Đáp án:** phải **tổng hợp các giá trị theo căn nghịch đảo** rồi mới nhân invN; chỉ chia phổ không thực hiện nội suy.

**Bài 38.** Kiểm thử nào phát hiện lỗi bỏ invN trực tiếp nhất? **Đáp án:** so `INTT(NTT(x))` với x trên các dãy không rỗng, đặc biệt N>1.

**Bài 39.** Nếu tính FFT double cho hệ số nguyên lớn, vì sao làm tròn có thể sai? **Đáp án:** sai số số thực tích lũy có thể vượt 0,5, làm kết quả tròn thành số nguyên không đúng.

**Bài 40.** Khi nào nên dùng phép nhân trực tiếp thay NTT? **Đáp án:** khi đa thức ngắn, ít truy vấn hoặc chi phí tiền xử lý NTT vượt lợi ích.

## 16. Checklist giải bài biến đổi ngược

1. **Mô hình:** Đầu vào là hệ số đa thức hay giá trị tại các điểm đánh giá?
2. **Mục tiêu:** Cần hệ số tích nguyên, hệ số modulo p, hay hệ số thực/phức?
3. **Đơn vị modulo:** Nếu dùng NTT, đã chọn p nguyên tố và cùng một p cho mọi dãy?
4. **Độ dài tích:** Đã tính `L=m+k−1`, kiểm tra overflow và xử lý input rỗng?
5. **Zero padding:** Đã chọn N≥L và đúng dạng lũy thừa 2 cho radix-2?
6. **Giới hạn root:** N có chia p−1 và nhỏ hơn mức mà mô-đun hỗ trợ?
7. **Root thuận:** Đã dùng căn nguyên thủy bậc len ở từng tầng?
8. **Root ngược:** Đã dùng căn nghịch đảo ở các tầng inverse?
9. **Chuẩn hóa nghịch đảo:** Đã nhân **invN=N^(p−2) mod p** đúng một lần sau tầng cuối?
10. **Biểu diễn âm:** Mọi hệ số đầu vào đã được chuẩn hóa modulo trước phép nhân?
11. **Nhân an toàn:** Kiểu dữ liệu có đủ chỗ cho tích của hai phần dư trước khi modulo?
12. **Butterfly:** Có cập nhật đúng `u+v` và `u−v` với chuẩn hóa không âm?
13. **Bit reversal:** Đã xử lý chính xác thứ tự chỉ số cho cài đặt iterative?
14. **Nhân miền biến đổi:** Có nhân `A_k·B_k` cùng chỉ số, cùng N/MOD?
15. **Biến đổi ngược:** Có chạy inverse **sau nhân phổ**, không in phổ như hệ số?
16. **Cắt đầu ra:** Đã lấy đúng L hệ số đầu sau INTT, không lấy tất cả N hệ số đệm?
17. **Cyclic vs linear:** Đã xác minh không wrap-around nếu muốn tích tuyến tính?
18. **Signed/large coefficients:** Có phân biệt phần dư mod p với số nguyên gốc?
19. **CRT/FFT:** Nếu cần số nguyên lớn tuyệt đối, đã có phương án đủ bound và kiểm soát sai số?
20. **Round-trip:** Đã thử `INTT(NTT(x))=normalize(x)` trên N=1,2,4,8,…?
21. **Oracle:** Đã đối chiếu hệ số tích với `O(mk)` trên các test nhỏ?
22. **Input biên:** Đã thử hệ số âm, 0, đa thức rỗng, đa thức hằng, khoảng trống hệ số?
23. **Giới hạn tài nguyên:** Đã tính bộ nhớ của hai mảng dài N và thời gian O(N log N)?
24. **Không sửa input:** Nếu API không muốn mutate, đã copy đầu vào trước khi gọi NTT in-place?
25. **Tính đúng:** Đã giải thích vì sao căn nguyên thủy có tính trực giao và vì sao inverse khôi phục đúng?

**Ghi nhớ:** phép nhân đa thức nhanh dựa trên chuỗi bước:

`hệ số A,B → biến đổi thuận → nhân từng giá trị → biến đổi ngược → hệ số tích C`.

Phép **ngược** phải dùng **căn nghịch đảo** và **chuẩn hóa bằng N^(−1)**. Muốn khôi phục **tích tuyến tính**, phải chọn độ dài **N≥m+k−1** để tránh quấn vòng. Với NTT, kết quả được khôi phục **chính xác modulo p**, không tự động là hệ số nguyên gốc nếu vượt phạm vi biểu diễn một mô-đun.
