# Biến đổi Fourier rời rạc và cách nhìn theo giá trị đa thức

**Biến đổi Fourier rời rạc** (*Discrete Fourier Transform, DFT*) có một diễn giải rất quan trọng trong thuật toán: nó chuyển **dãy hệ số** của đa thức thành **dãy giá trị của đa thức tại các căn bậc N của đơn vị**. Phép biến đổi ngược (*Inverse DFT, IDFT*) khôi phục hệ số từ những giá trị đó. **FFT** (*Fast Fourier Transform*) là thuật toán tính DFT/IDFT nhanh, chứ không phải một phép toán khác với DFT.

Động cơ chính trong thuật toán số và đa thức là **phép nhân đa thức**: nhân hệ số trực tiếp cần O(nm) phép toán, trong khi ở **dạng giá trị** tích đa thức được tính bằng cách nhân các giá trị tương ứng. Nhờ FFT, có thể chuyển hệ số sang giá trị, nhân theo từng điểm rồi chuyển ngược về hệ số trong **O(N log N)**, với N là độ dài biến đổi sau khi thêm các hệ số 0.

Bài này đi từ khái niệm đa thức, căn bậc N của đơn vị, DFT/IDFT và chứng minh khả nghịch, tới FFT radix-2, biến đổi chẵn–lẻ, **tích chập tuyến tính so với tích chập vòng**, điều kiện **zero-padding N≥n+m−1**, tính toán số phức và sai số dấu phẩy động. Kèm chương trình **Java 17+ chạy độc lập**, đầu ra cụ thể, oracle đối chiếu DFT trực tiếp và phép nhân O(nm), cùng các bài tập thực hành.

## 1. Đa thức có hai cách biểu diễn

Cho:

\[
A(x)=a_0+a_1x+a_2x^2+\cdots+a_{n-1}x^{n-1}.
\]

Trong **dạng hệ số**, ta lưu:

~~~text
A(x) = 1 + 2x + 3x^2
coefficients = [1,2,3]

index:        0 1 2
coefficient:  1 2 3
~~~

Dãy được sắp từ **bậc thấp tới bậc cao**: chỉ số i tương ứng hệ số của \(x^i\). Đây là thứ tự mà mã Java của bài nhận. Nếu một đề lưu hệ số theo bậc cao trước, phải đổi thứ tự trước khi nhân.

Trong **dạng giá trị**, ta chọn các điểm khác nhau \(x_0,x_1,\ldots,x_{N-1}\) rồi lưu:

\[
(x_0,A(x_0)),\ (x_1,A(x_1)),\ldots,\ (x_{N-1},A(x_{N-1})).
\]

Ví dụ với \(A(x)=1+2x+3x^2\):

~~~text
x       A(x)
0       1
1       6
2       17
~~~

Ba giá trị tại ba điểm phân biệt đủ để xác định duy nhất một đa thức bậc **nhỏ hơn 3**, vì hiệu của hai đa thức bậc dưới 3 không thể có ba nghiệm phân biệt trừ khi nó là đa thức 0.

### Đánh giá đa thức bằng Horner

Nếu chỉ muốn tính A tại một điểm x, **Horner** dùng:

\[
A(x)=(\cdots((a_{n-1}x+a_{n-2})x+a_{n-3})\cdots)x+a_0.
\]

Chi phí O(n), rất tốt cho **một lần đánh giá**. Nhưng nếu cần đánh giá tại N điểm khác nhau, dùng Horner cho từng điểm sẽ là O(nN). DFT chọn hệ điểm đặc biệt để tính đồng thời trong O(N log N) với FFT.

## 2. Tại sao dạng giá trị làm phép nhân đơn giản?

Cho:

\[
A(x)=1+2x+3x^2,\qquad B(x)=4+5x.
\]

Tích:

\[
C(x)=A(x)B(x)=4+13x+22x^2+15x^3.
\]

Trong dạng hệ số, để tính \(c_k\) phải xét các cặp chỉ số i,j có i+j=k:

\[
\boxed{c_k=\sum_{i+j=k}a_i b_j.}
\]

Đây là phép **tích chập tuyến tính** (*linear convolution*). Nhân trực tiếp hai đa thức dài n và m hệ số tốn O(nm) phép nhân.

Ở **bất kỳ một điểm x nào**, phép nhân dễ hơn:

\[
\boxed{C(x)=A(x)B(x).}
\]

Nếu đã biết A(x_k) và B(x_k) tại **cùng N điểm x_k**, ta nhận được N giá trị của C bằng đúng **N phép nhân số**, thay vì chập từng hệ số:

~~~text
A values: A(x0), A(x1), ..., A(xN-1)
B values: B(x0), B(x1), ..., B(xN-1)

C values: A(x0)*B(x0), ..., A(xN-1)*B(xN-1)
~~~

Sau đó cần **nội suy** để chuyển từ những giá trị C(x_k) về hệ số \(c_0,c_1,\ldots\). DFT/IDFT giải quyết hiệu quả cả **đánh giá** và **khôi phục** trên hệ điểm đặc biệt.

**Điều kiện rất quan trọng:** hai đa thức phải được đánh giá tại **cùng các điểm**. Nhân A(x_k) với B(y_k) khi x_k≠y_k nói chung không tạo giá trị C(x_k).

## 3. Các căn bậc N của đơn vị

Đặt:

\[
\boxed{\omega_N=e^{-2\pi i/N}
=\cos(2\pi/N)-i\sin(2\pi/N)}.
\]

Đây là một **căn bậc N nguyên thủy của đơn vị** trong số phức:

\[
\omega_N^N=1
\]

và \(1,\omega_N,\omega_N^2,\ldots,\omega_N^{N-1}\) là N điểm khác nhau, nằm đều trên đường tròn đơn vị.

Đó chính là hệ điểm đánh giá DFT:

\[
\boxed{x_k=\omega_N^k,\quad k=0,\ldots,N-1.}
\]

Với N=4:

~~~text
                 +i  = omega^3
                  |
                  |
 -1 = omega^2 ----+---- +1 = omega^0
                  |
                  |
                 -i  = omega^1

omega_4 = -i
~~~

Thứ tự lũy thừa dùng **góc âm**, nên các điểm đi theo chiều kim đồng hồ từ 1.

### Hai đẳng thức làm nên FFT

Khi N chẵn:

\[
\omega_N^{N/2}=-1.
\]

Và:

\[
(\omega_N^k)^2=\omega_{N/2}^k.
\]

Đẳng thức thứ nhất giúp hai nửa kết quả khác nhau đúng một dấu cộng/trừ. Đẳng thức thứ hai cho phép tái sử dụng các giá trị của DFT có độ dài **N/2**.

## 4. Định nghĩa DFT là đánh giá đa thức

Với dãy có N hệ số \(a_0,\ldots,a_{N-1}\):

\[
A(x)=\sum_{j=0}^{N-1}a_jx^j.
\]

**DFT thuận**, theo quy ước của bài, là:

\[
\boxed{
X_k=\sum_{j=0}^{N-1}a_j\omega_N^{kj}
=A(\omega_N^k),\quad k=0,\ldots,N-1.
}
\]

Như vậy, DFT đơn giản là một vector gồm N giá trị của cùng một đa thức tại N điểm được lựa chọn đặc biệt.

### Ví dụ N=4

Lấy \(a=[1,2,3,0]\), tức:

\[
A(x)=1+2x+3x^2.
\]

Các giá trị:

| k | Điểm \(\omega_4^k\) | A tại điểm đó |
|---|---|---|
| 0 | \(1\) | \(6\) |
| 1 | \(-i\) | \(-2-2i\) |
| 2 | \(-1\) | \(2\) |
| 3 | \(i\) | \(-2+2i\) |

Chẳng hạn:

\[
A(-i)=1-2i+3(-1)=-2-2i.
\]

Vì vậy:

\[
\boxed{DFT([1,2,3,0])=[6,-2-2i,2,-2+2i].}
\]

Nếu tính trực tiếp theo định nghĩa, có N tổng, mỗi tổng N số hạng, nên thời gian **O(N²)**. **FFT** tính đúng các giá trị ấy nhưng khai thác tính chất căn đơn vị để chỉ cần **O(N log N)**.

### DFT và FFT có giống nhau không?

- **DFT** là **định nghĩa phép biến đổi** từ hệ số sang giá trị.
- **FFT** là **họ thuật toán nhanh** thực hiện DFT/IDFT.
- Kết quả toán học của FFT thuận **chính là DFT**, không phải một đối tượng khác.
- Có DFT với N=3,5,6,...; mã **FFT radix-2** trong bài chỉ nhận N là lũy thừa 2.

Không nên nói “DFT là O(N²) còn FFT là O(N log N)” như thể DFT có một độ phức tạp cố định. Chính xác hơn, **tính DFT trực tiếp** là O(N²), còn **thuật toán FFT phù hợp** có thể tính DFT nhanh hơn.

## 5. Phép biến đổi ngược IDFT

Các căn bậc N của đơn vị có tính trực giao tổng hữu hạn:

\[
\boxed{
\sum_{k=0}^{N-1}\omega_N^{k(j-\ell)}
=
\begin{cases}
N,&j\equiv\ell\pmod N,\\
0,&j\not\equiv\ell\pmod N.
\end{cases}
}
\]

Nếu j=ℓ theo modulo N, mọi số hạng bằng 1, nên tổng bằng N. Nếu j≠ℓ, đặt \(q=\omega_N^{j-\ell}\). Ta có q≠1 nhưng q^N=1, nên:

\[
1+q+\cdots+q^{N-1}
=\frac{1-q^N}{1-q}=0.
\]

Từ đó suy ra **IDFT**:

\[
\boxed{
a_j=\frac1N\sum_{k=0}^{N-1}
X_k\omega_N^{-kj}.
}
\]

Thế \(X_k=\sum_t a_t\omega_N^{kt}\) vào:

\[
\begin{aligned}
\frac1N\sum_kX_k\omega_N^{-kj}
&=\frac1N\sum_t a_t\sum_k\omega_N^{k(t-j)}\\
&=a_j.
\end{aligned}
\]

Các số hạng t≠j triệt tiêu, chỉ còn số hạng t=j.

### Quy ước dấu và chuẩn hóa

Trong bài:

- **FFT/DFT thuận:** số mũ \(-2\pi ikj/N\); không chia N.
- **FFT/IDFT ngược:** số mũ \(+2\pi ikj/N\); chia **1/N** đúng một lần.

Một số tài liệu đổi dấu hoặc phân bố hệ số chuẩn hóa khác. Điều đó không sai nếu được dùng **nhất quán**. Nhưng lấy dấu của một tài liệu và hệ số chia của tài liệu khác có thể làm khôi phục hệ số sai.

Với [1,2,3,0], áp dụng IDFT lên \([6,-2-2i,2,-2+2i]\) phải lấy lại đúng **[1,2,3,0]** trong số học chính xác.

## 6. Cách nhìn “giá trị đa thức” và cách nhìn “tần số”

Trong xử lý tín hiệu, dãy \(a_j\) thường là các mẫu theo thời gian, còn \(X_k\) có thể được hiểu là thành phần **tần số**. Trong thuật toán đa thức, ta có thể không cần diễn giải vật lý: \(X_k\) chỉ là giá trị \(A(\omega_N^k)\).

Hai cách nhìn dùng **cùng công thức**:

\[
X_k=\sum_j a_j e^{-2\pi ikj/N}.
\]

Điểm then chốt của nhân đa thức là tính chất:

\[
(A\cdot B)(x_k)=A(x_k)B(x_k).
\]

Sơ đồ:

~~~text
Hệ số A --FFT--> Giá trị A tại các căn đơn vị
                                  |
                                  | nhân theo từng điểm
                                  |
Hệ số B --FFT--> Giá trị B tại cùng các căn đơn vị
                                  |
                           Giá trị đa thức C
                                  |
                                 IDFT
                                  |
                            Hệ số của C
~~~

Vì vậy FFT thường xuất hiện trong thuật toán **nhân đa thức**, **chập dãy**, **đếm cặp theo tổng chỉ số**, **nhân số lớn** và một số bài toán tổ hợp.

## 7. Phân rã chẵn–lẻ tạo thuật toán FFT radix-2

Giả sử N là lũy thừa của 2. Tách đa thức:

\[
A(x)=a_0+a_1x+a_2x^2+a_3x^3+\cdots.
\]

Đặt:

\[
E(y)=a_0+a_2y+a_4y^2+\cdots,
\]

\[
O(y)=a_1+a_3y+a_5y^2+\cdots.
\]

Ta có:

\[
\boxed{A(x)=E(x^2)+xO(x^2).}
\]

Đánh giá tại \(\omega_N^k\):

\[
A(\omega_N^k)
=E(\omega_{N/2}^k)
+\omega_N^k O(\omega_{N/2}^k).
\]

Đánh giá tại \(\omega_N^{k+N/2}\) và dùng \(\omega_N^{N/2}=-1\):

\[
A(\omega_N^{k+N/2})
=E(\omega_{N/2}^k)
-\omega_N^k O(\omega_{N/2}^k).
\]

Với \(k=0,\ldots,N/2-1\), đặt:

\[
u=E(\omega_{N/2}^k),\quad
v=\omega_N^kO(\omega_{N/2}^k).
\]

Ta nhận hai giá trị:

\[
\boxed{X_k=u+v,\qquad X_{k+N/2}=u-v.}
\]

Phép kết hợp một cặp \(u,v\) thành \(u+v,u-v\) được gọi là **butterfly**.

### Tại sao nhanh?

Mỗi bài toán kích thước N được chuyển thành **hai bài toán kích thước N/2** cộng O(N) phép toán butterfly:

\[
T(N)=2T(N/2)+O(N).
\]

Khi N=2^r, cây phân rã có r tầng, mỗi tầng tổng O(N) công việc:

\[
\boxed{T(N)=O(N\log_2N).}
\]

FFT không làm thiếu các giá trị DFT. Nó khai thác tính đối xứng của căn đơn vị để **tính cùng kết quả bằng ít phép tính hơn**.

## 8. FFT lặp tại chỗ, bit-reversal và hệ số xoay

Mã Java dùng **FFT radix-2 lặp tại chỗ**, vì nó tránh phải tạo hàng loạt mảng con khi đệ quy.

Các bước:

1. Đưa các chỉ số vào thứ tự **bit-reversal**.
2. Chạy các tầng butterfly `len=2,4,8,...,N`.
3. Với mỗi khối dài len, tính các cặp `u,v` cách nhau `len/2`.
4. Nhân nửa v với hệ số xoay (*twiddle*) \(e^{\pm2\pi ij/len}\).
5. Ghi hai kết quả `u+v`, `u-v` tại vị trí tương ứng.
6. Khi inverse, đảo dấu góc và cuối cùng chia mọi phần tử cho N.

### Ví dụ bit-reversal với N=8

Ba bit chỉ số được đảo thứ tự:

~~~text
0 = 000 -> 000 = 0
1 = 001 -> 100 = 4
2 = 010 -> 010 = 2
3 = 011 -> 110 = 6
4 = 100 -> 001 = 1
5 = 101 -> 101 = 5
6 = 110 -> 011 = 3
7 = 111 -> 111 = 7

Thứ tự sau bit-reversal:
[0,4,2,6,1,5,3,7]
~~~

Sau hoán vị, tầng len=2 kết hợp các cặp liền nhau; tầng len=4 kết hợp các nửa dài 2; tầng len=8 kết hợp hai nửa dài 4.

### Số phức không thể nhân như hai số thực độc lập

Cho \(z_1=a+bi\), \(z_2=c+di\):

\[
\boxed{z_1z_2=(ac-bd)+(ad+bc)i.}
\]

Khi nhân phổ của hai đa thức, phải dùng **cả phần thực và phần ảo**. Không được chỉ nhân hai phần thực rồi cho phần ảo bằng 0; một kết quả DFT của đa thức hệ số thực vẫn thường có phần ảo khác 0.

### Hệ số xoay từng tầng

Với mỗi độ dài len:

\[
w_{step}=\cos(2\pi/len)\mp i\sin(2\pi/len)
\]

cho FFT thuận/ngược theo dấu đã chọn. Trong từng nhóm butterfly, bắt đầu w=1 và nhân w với w_step sau mỗi bước. Như vậy không phải gọi `Math.cos` và `Math.sin` ở từng butterfly.

## 9. Nhân đa thức bằng FFT: sáu bước chính

Giả sử đa thức A có **n hệ số** và B có **m hệ số**, n,m>0:

**Bước 1.** Độ dài hệ số của tích:

\[
\boxed{needed=n+m-1}.
\]

Vì bậc A không vượt n−1 và bậc B không vượt m−1, bậc tích không vượt n+m−2, nên cần tối đa n+m−1 hệ số.

**Bước 2.** Chọn N là lũy thừa 2 nhỏ nhất thỏa:

\[
\boxed{N\ge needed}.
\]

**Bước 3.** Thêm hệ số 0 vào cuối hai dãy để có cùng độ dài N:

~~~text
A=[1,2,3] -> [1,2,3,0]
B=[4,5]   -> [4,5,0,0]
N=4
~~~

**Bước 4.** Tính FFT thuận của hai dãy tại cùng hệ căn bậc N của đơn vị.

**Bước 5.** Nhân các giá trị tương ứng:

\[
Z_k=X_kY_k.
\]

**Bước 6.** Tính IDFT để nhận hệ số tích và lấy đúng **needed phần tử đầu**.

Với ví dụ:

\[
(1+2x+3x^2)(4+5x)
=4+13x+22x^2+15x^3.
\]

Kết quả hệ số:

~~~text
[4,13,22,15]
~~~

### Kiểm bằng thay x=2

A(2)=17 và B(2)=14. Tích hai giá trị là 238.

C(2) với dãy [4,13,22,15]:

\[
4+13(2)+22(4)+15(8)=238.
\]

Kiểm một giá trị là kiểm tra hữu ích, nhưng **chưa đủ** để bảo đảm tất cả hệ số đúng: hai đa thức khác nhau có thể bằng nhau ở một điểm. Cần oracle nhân trực tiếp để so từng hệ số trong test.

## 10. Vì sao không được quên padding: tích chập vòng

DFT_N làm **phép nhân theo điểm** tương ứng với **tích chập vòng** (*circular convolution*) độ dài N:

\[
\boxed{
c^{circle}_k=\sum_{i=0}^{N-1}
a_i b_{(k-i)\bmod N}.
}
\]

Nếu tích đa thức thật có hệ số tại \(x^N,x^{N+1},...\), chúng sẽ **bị cuộn** vào hệ số bậc nhỏ hơn theo quan hệ:

\[
x^N\equiv1\pmod{x^N-1}.
\]

Đây là **aliasing** trong phép chập.

### Phản ví dụ chọn N quá ngắn

A=[1,2,3], B=[4,5]. Tích tuyến tính dài 4:

~~~text
linear convolution:
[4,13,22,15]
~~~

Nếu làm chập vòng độ dài 3, hệ số ở bậc 3 là 15 bị cộng vòng về bậc 0:

~~~text
circular convolution length 3:
[4+15,13,22] = [19,13,22]
~~~

Đây **không phải** hệ số tích đa thức thông thường.

### Hai lý do khác nhau để thêm số 0

- **Đúng toán học:** cần N≥n+m−1 để kết quả tuyến tính không bị cuộn vòng.
- **Đúng với FFT radix-2:** N nên là một lũy thừa 2.

Một DFT trực tiếp độ dài N=5 vẫn tồn tại, và nếu needed≤5 thì không aliasing. Nhưng mã FFT radix-2 minh họa yêu cầu N=1,2,4,8,16,... Đừng nhầm hai điều kiện.

### Chứng minh kết quả tích đúng khi đủ N

Đặt C=A·B, bậc C≤n+m−2<N. Ta biết N giá trị:

\[
Z_k=A(\omega_N^k)B(\omega_N^k)=C(\omega_N^k).
\]

N giá trị của một đa thức bậc <N tại N điểm phân biệt xác định duy nhất C. IDFT là phép khôi phục hệ số của đa thức ấy, nên thu được đúng **chập tuyến tính**. Khi N quá nhỏ, dữ liệu giá trị không phân biệt được C với phần dư của C theo \(x^N-1\), gây aliasing.

## 11. Java 17+: FFT lặp tại chỗ và nhân đa thức

Chương trình **DiscreteFourierPolynomialDemo.java**:

- Dùng hai mảng `double[] real` và `double[] imag` để biểu diễn vector số phức.
- Cài FFT radix-2 **tại chỗ** với bit-reversal, butterfly và inverse chia N.
- Nhân hai mảng hệ số `long[]` theo thứ tự **bậc tăng dần**. Vì chuyển sang `double` và `Math.round`, chức năng nhân này dành cho **ví dụ số nguyên nhỏ**, không được coi là bảo đảm chính xác tuyệt đối cho mọi input long.
- Chọn N nhỏ nhất là lũy thừa 2 không dưới n+m−1.
- Hỗ trợ N=1, mảng hệ số rỗng, hệ số âm, đa thức 0 và điều kiện từ chối kích thước FFT không đúng.
- Giới hạn `MAX_FFT_SIZE` là chính sách tài nguyên của demo, không phải giới hạn toán học của DFT.
- Tự kiểm tra 100 vector bằng **DFT trực tiếp**, **IDFT khôi phục** và 200 bộ nhân đa thức nguyên nhỏ bằng **O(nm)**.

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.Random;
import java.util.StringJoiner;

public class DiscreteFourierPolynomialDemo {
    static final int MAX_FFT_SIZE = 1 << 20;

    static void fft(double[] real, double[] imag, boolean inverse) {
        Objects.requireNonNull(real, "real");
        Objects.requireNonNull(imag, "imag");
        int n = real.length;

        if (n == 0 || n != imag.length || (n & (n - 1)) != 0
                || n > MAX_FFT_SIZE) {
            throw new IllegalArgumentException(
                "FFT size must be a supported positive power of two"
            );
        }

        // Bit-reversal permutation.
        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >> 1;
            while ((j & bit) != 0) {
                j ^= bit;
                bit >>= 1;
            }
            j ^= bit;

            if (i < j) {
                double t = real[i];
                real[i] = real[j];
                real[j] = t;
                t = imag[i];
                imag[i] = imag[j];
                imag[j] = t;
            }
        }

        // Butterfly stages of lengths 2, 4, 8, ..., n.
        for (int len = 2; len <= n;) {
            double angle = 2.0 * Math.PI / len
                * (inverse ? 1.0 : -1.0);
            double stepReal = Math.cos(angle);
            double stepImag = Math.sin(angle);

            for (int start = 0; start < n; start += len) {
                double wr = 1.0;
                double wi = 0.0;

                for (int j = 0; j < len / 2; j++) {
                    int u = start + j;
                    int v = u + len / 2;

                    double vr = real[v] * wr - imag[v] * wi;
                    double vi = real[v] * wi + imag[v] * wr;
                    double ur = real[u];
                    double ui = imag[u];

                    real[u] = ur + vr;
                    imag[u] = ui + vi;
                    real[v] = ur - vr;
                    imag[v] = ui - vi;

                    double newWr = wr * stepReal - wi * stepImag;
                    wi = wr * stepImag + wi * stepReal;
                    wr = newWr;
                }
            }

            if (len == n) {
                break;
            }
            len <<= 1;
        }

        if (inverse) {
            for (int i = 0; i < n; i++) {
                real[i] /= n;
                imag[i] /= n;
            }
        }
    }

    private static int chooseSize(long needed) {
        if (needed < 1 || needed > MAX_FFT_SIZE) {
            throw new IllegalArgumentException(
                "product length exceeds FFT demo budget"
            );
        }
        int size = 1;
        while (size < needed) {
            size <<= 1;
        }
        return size;
    }

    // Floating-point FFT convolution, rounded to long.
    // Demonstration only: use small integer coefficients.
    static long[] multiply(long[] a, long[] b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        if (a.length == 0 || b.length == 0) {
            return new long[0];
        }

        long needed = (long) a.length + b.length - 1L;
        int n = chooseSize(needed);
        double[] ar = new double[n];
        double[] ai = new double[n];
        double[] br = new double[n];
        double[] bi = new double[n];

        for (int i = 0; i < a.length; i++) {
            ar[i] = a[i];
        }
        for (int i = 0; i < b.length; i++) {
            br[i] = b[i];
        }

        fft(ar, ai, false);
        fft(br, bi, false);

        for (int i = 0; i < n; i++) {
            double cr = ar[i] * br[i] - ai[i] * bi[i];
            double ci = ar[i] * bi[i] + ai[i] * br[i];
            ar[i] = cr;
            ai[i] = ci;
        }
        fft(ar, ai, true);

        long[] result = new long[(int) needed];
        for (int i = 0; i < result.length; i++) {
            result[i] = Math.round(ar[i]);
        }
        return result;
    }

    // Independent O(n*m) reference for small integers.
    static long[] naiveMultiply(long[] a, long[] b) {
        if (a.length == 0 || b.length == 0) {
            return new long[0];
        }
        long[] out = new long[a.length + b.length - 1];
        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < b.length; j++) {
                out[i + j] += a[i] * b[j];
            }
        }
        return out;
    }

    static long evaluateSmall(long[] coefficients, long x) {
        long value = 0L;
        for (int i = coefficients.length - 1; i >= 0; i--) {
            value = value * x + coefficients[i];
        }
        return value;
    }

    static String formatSpectrum(double[] real, double[] imag) {
        StringJoiner result = new StringJoiner(", ", "[", "]");
        for (int i = 0; i < real.length; i++) {
            double r = Math.abs(real[i]) < 1e-9 ? 0.0 : real[i];
            double im = Math.abs(imag[i]) < 1e-9 ? 0.0 : imag[i];
            result.add(String.format(
                Locale.US, "(%.3f%+.3fi)", r, im
            ));
        }
        return result.toString();
    }

    static String formatReal(double[] real) {
        StringJoiner result = new StringJoiner(", ", "[", "]");
        for (double x : real) {
            double v = Math.abs(x) < 1e-9 ? 0.0 : x;
            result.add(String.format(Locale.US, "%.3f", v));
        }
        return result.toString();
    }

    // Independent direct O(n^2) DFT oracle on small complex vectors.
    static void checkDirectDftAndInverse() {
        int checks = 0;

        for (int n : new int[] {1, 2, 4, 8, 16}) {
            for (int test = 0; test < 20; test++) {
                double[] re = new double[n];
                double[] im = new double[n];

                for (int j = 0; j < n; j++) {
                    re[j] = (test * 7 + j * 3) % 11 - 5;
                    im[j] = (test + j * 2) % 7 - 3;
                }

                double[] originalReal = re.clone();
                double[] originalImag = im.clone();
                double[] directReal = new double[n];
                double[] directImag = new double[n];

                for (int k = 0; k < n; k++) {
                    for (int j = 0; j < n; j++) {
                        double theta = -2.0 * Math.PI * k * j / n;
                        double c = Math.cos(theta);
                        double s = Math.sin(theta);
                        directReal[k] += originalReal[j] * c
                            - originalImag[j] * s;
                        directImag[k] += originalReal[j] * s
                            + originalImag[j] * c;
                    }
                }

                fft(re, im, false);
                for (int k = 0; k < n; k++) {
                    if (Math.abs(re[k] - directReal[k]) > 1e-8
                            || Math.abs(im[k] - directImag[k]) > 1e-8) {
                        throw new AssertionError(
                            "FFT/direct DFT mismatch at n=" + n
                        );
                    }
                }

                fft(re, im, true);
                for (int k = 0; k < n; k++) {
                    if (Math.abs(re[k] - originalReal[k]) > 1e-8
                            || Math.abs(im[k] - originalImag[k]) > 1e-8) {
                        throw new AssertionError(
                            "IDFT round-trip mismatch at n=" + n
                        );
                    }
                }
                checks++;
            }
        }
        System.out.println(
            "Direct DFT and inverse checks: PASS (" + checks + " cases)"
        );
    }

    static void checkNaiveConvolution() {
        Random random = new Random(2026L);
        int checks = 200;

        for (int test = 0; test < checks; test++) {
            long[] a = new long[1 + random.nextInt(8)];
            long[] b = new long[1 + random.nextInt(8)];
            for (int i = 0; i < a.length; i++) {
                a[i] = random.nextInt(11) - 5;
            }
            for (int i = 0; i < b.length; i++) {
                b[i] = random.nextInt(11) - 5;
            }

            if (!Arrays.equals(multiply(a, b), naiveMultiply(a, b))) {
                throw new AssertionError(
                    "FFT/naive convolution mismatch at test=" + test
                );
            }
        }
        System.out.println(
            "Naive convolution checks: PASS (" + checks + " cases)"
        );
    }

    public static void main(String[] args) {
        double[] real = {1, 2, 3, 0};
        double[] imag = {0, 0, 0, 0};

        fft(real, imag, false);
        System.out.println("DFT [1,2,3,0]: "
            + formatSpectrum(real, imag));

        fft(real, imag, true);
        System.out.println("IDFT: " + formatReal(real));

        long[] a = {1, 2, 3};
        long[] b = {4, 5};
        long[] c = multiply(a, b);
        System.out.println("A=" + Arrays.toString(a));
        System.out.println("B=" + Arrays.toString(b));
        System.out.println("C=A*B=" + Arrays.toString(c));
        System.out.println(
            "C(2)=" + evaluateSmall(c, 2)
            + "; A(2)*B(2)="
            + (evaluateSmall(a, 2) * evaluateSmall(b, 2))
        );

        System.out.println("(1+x)^2="
            + Arrays.toString(
                multiply(new long[] {1, 1}, new long[] {1, 1})
            ));
        System.out.println("Signed product="
            + Arrays.toString(
                multiply(new long[] {2, -1, 3}, new long[] {1, 4})
            ));
        System.out.println("Zero polynomial product="
            + Arrays.toString(
                multiply(new long[] {0, 0}, new long[] {7, 0})
            ));
        System.out.println("Empty coefficient array product="
            + Arrays.toString(
                multiply(new long[] {}, new long[] {5})
            ));

        checkDirectDftAndInverse();
        checkNaiveConvolution();

        try {
            fft(new double[3], new double[3], false);
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid FFT size rejected: "
                + e.getMessage());
        }
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 DiscreteFourierPolynomialDemo.java
java DiscreteFourierPolynomialDemo
~~~

**Stdout với dữ liệu và quy ước trên:**

~~~text
DFT [1,2,3,0]: [(6.000+0.000i), (-2.000-2.000i), (2.000+0.000i), (-2.000+2.000i)]
IDFT: [1.000, 2.000, 3.000, 0.000]
A=[1, 2, 3]
B=[4, 5]
C=A*B=[4, 13, 22, 15]
C(2)=238; A(2)*B(2)=238
(1+x)^2=[1, 2, 1]
Signed product=[2, 7, -1, 12]
Zero polynomial product=[0, 0, 0]
Empty coefficient array product=[]
Direct DFT and inverse checks: PASS (100 cases)
Naive convolution checks: PASS (200 cases)
Invalid FFT size rejected: FFT size must be a supported positive power of two
~~~

### Cách đọc mã Java

**FFT tại chỗ:** hàm `fft` biến đổi trực tiếp hai mảng real và imag. Nếu inverse=true, đổi dấu góc và cuối cùng chia cả phần thực và ảo cho N. Giá trị N=1 hợp lệ: không có butterfly nào cần chạy, phần tử được giữ nguyên.

**Bit-reversal:** vòng hoán vị dùng các bit của chỉ số để đưa dữ liệu về đúng trật tự tính butterfly lặp. Sau đó mỗi tầng chỉ cần xét những nhóm liên tiếp.

**Butterfly:** phần `vr,vi` nhân số phức ở nhánh v với twiddle factor. Cần lưu `ur,ui` **trước khi ghi đè** để tạo đồng thời hai đầu ra `u+v,u-v`.

**Nhân phổ:** không được nhân chỉ phần thực; tích số phức dùng `cr=ar*br-ai*bi`, `ci=ar*bi+ai*br` theo giá trị cũ trước khi cập nhật.

**Chọn N:** `chooseSize` lấy lũy thừa 2 không nhỏ hơn `needed`, bảo đảm không xảy ra cuộn hệ số khi nhân đa thức. Nếu một đầu vào rỗng, chương trình trả mảng rỗng theo hợp đồng API.

**Làm tròn:** `Math.round` giúp biểu diễn kết quả cho **hệ số nguyên nhỏ**. Nếu đầu vào có hệ số lớn, độ dài N lớn hoặc cần độ chính xác tuyệt đối, mã này **không đưa ra bảo đảm số học**; cần NTT/CRT hoặc thuật toán exact.

**Đầu ra:** `formatSpectrum` đặt các phần rất nhỏ gần 0 thành 0 để tránh in `-0.000`; hiển thị ba chữ số thập phân theo `Locale.US`. Đây chỉ là **định dạng khi in**, không thay đổi dữ liệu tính toán.

**Oracle:** `checkDirectDftAndInverse` dùng chính định nghĩa O(N²) để so FFT trên 100 vector phức và kiểm khôi phục, còn `checkNaiveConvolution` đối chiếu 200 cặp đa thức hệ số nhỏ với hai vòng lặp. Đây là hai cơ chế độc lập với butterfly.

## 12. Phân tích độ phức tạp

Với hai đa thức có n và m hệ số, đặt N là lũy thừa 2 nhỏ nhất ≥n+m−1.

- Sao chép/padding: O(N).
- FFT thuận của A: O(N log N).
- FFT thuận của B: O(N log N).
- Nhân N cặp giá trị: O(N).
- IDFT: O(N log N).
- Thu needed hệ số: O(n+m).

Tổng:

\[
\boxed{\text{Thời gian }O(N\log N).}
\]

Bản Java dùng bốn mảng double độ dài N cho hai vector phức, cùng mảng kết quả dài needed:

\[
\boxed{\text{Bộ nhớ phụ }O(N).}
\]

Trong trường hợp n,m cùng cỡ, FFT cải thiện độ phức tạp từ **O(nm)** của nhân trực tiếp xuống khoảng **O((n+m)\log(n+m))**.

**Không nên dùng FFT cho mọi đa thức nhỏ.** Với đa thức chỉ vài hệ số, hai vòng lặp nhân trực tiếp ngắn, dễ kiểm tra và tránh sai số dấu phẩy động. FFT có overhead lượng giác, cấp phát bộ nhớ và sắp xếp bit-reversal.

## 13. Sai số của FFT double

Trong toán học chính xác, IDFT(DFT(a)) bằng đúng a. Nhưng trong máy tính, FFT dùng `Math.cos`, `Math.sin` và các phép toán `double`, nên có sai số làm tròn.

Một hệ số toán học là 13 có thể được khôi phục gần:

~~~text
12.999999999999996
~~~

Một hệ số toán học bằng 0 có thể thành:

~~~text
-0.000000000000002
~~~

Khi **biết chắc hệ số thật là số nguyên nhỏ** và sai số đủ nhỏ, làm tròn về số nguyên gần nhất thường cho kết quả đúng. Nhưng không có bảo đảm chung cho mọi dữ liệu:

- `double` chỉ có khoảng **53 bit precision** ở phần trị.
- Hệ số có độ lớn quá cao có thể không biểu diễn chính xác.
- Sai số từ nhiều butterfly có thể cộng dồn.
- Sự triệt tiêu giữa những giá trị lớn gần nhau có thể giảm độ chính xác.
- `Math.round` không phải chứng minh rằng hệ số nguyên đã được khôi phục đúng.

Nếu bài cần **tích đa thức nguyên chính xác tuyệt đối**, đặc biệt trên hệ số lớn, nên cân nhắc **NTT** với số nguyên mô-đun phù hợp, có thể kết hợp **CRT** để tái dựng.

### NTT là gì?

**Number Theoretic Transform** là một phép biến đổi tương tự DFT nhưng làm việc trong **trường hữu hạn modulo p**, với căn bậc N nguyên thủy của 1 theo modulo p.

Nếu N chia p−1 và chọn đúng căn cùng phần tử nghịch đảo của N, có thể triển khai butterfly và phép biến đổi ngược **không sai số số thực**. Kết quả đầu tiên là các hệ số **modulo p**, không tự trở thành hệ số nguyên có thể lớn hơn p. Nếu muốn hệ số chính xác không modulo, cần phân tích cận và đôi khi dùng nhiều modulo + CRT.

Ngay cả trong NTT, phải tránh tràn ở phép nhân modulo khi cài trên kiểu dữ liệu có giới hạn.

## 14. Các tính chất DFT hữu ích

### Tuyến tính

Với vector a,b cùng N và hằng \(\alpha,\beta\):

\[
DFT(\alpha a+\beta b)
=\alpha DFT(a)+\beta DFT(b).
\]

Tính chất này suy ra trực tiếp từ định nghĩa tổng.

### Tích chập vòng

\[
\boxed{DFT(a\circledast b)=DFT(a)\odot DFT(b)}
\]

với \(\circledast\) là tích chập vòng độ dài N và \(\odot\) là nhân từng phần tử. Nếu muốn chập tuyến tính, phải padding tới N đủ lớn.

### Đối xứng liên hợp khi đầu vào thực

Nếu mọi a_j là số thực, thì:

\[
\boxed{X_{N-k}=\overline{X_k}}
\]

với chỉ số tính modulo N. Ví dụ DFT([1,2,3,0]) có X_1=−2−2i và X_3=−2+2i là hai số liên hợp. X_0 thực; nếu N chẵn, X_{N/2} cũng thực.

### Parseval theo chuẩn hóa đã chọn

\[
\boxed{
\sum_{j=0}^{N-1}|a_j|^2
=\frac1N\sum_{k=0}^{N-1}|X_k|^2.
}
\]

Hệ số 1/N là đúng với **DFT thuận không chuẩn hóa** của bài. Nếu đổi quy ước, hệ số bên phải cũng thay đổi.

## 15. Các tình huống biên và cách xử lý

| Trường hợp | Xử lý/giải thích |
|---|---|
| FFT độ dài N=1 | Hợp lệ, phần tử giữ nguyên |
| FFT độ dài N=0 | API demo từ chối |
| FFT độ dài N=3 | DFT tồn tại, nhưng mã radix-2 từ chối |
| Hai mảng real/imag không cùng độ dài | Báo lỗi |
| Hai đa thức có đúng một hệ số | Kết quả có đúng một hệ số |
| Một mảng hệ số rỗng | Demo trả `[]` |
| Đa thức 0 có mảng `[0]` | Nhân giữ một hệ số bằng 0 |
| Đa thức có hệ số 0 ở cuối | Kết quả giữ đúng n+m−1 vị trí hệ số, kể cả số 0 cuối |
| Hệ số âm | Mã minh họa xử lý trên dữ liệu nguyên nhỏ |
| Cần nhân modulo p chính xác | Cân nhắc NTT nếu có căn phù hợp |
| Cần kết quả nguyên rất lớn | Không tin vào Math.round(double) không có chứng minh sai số |
| N chưa đủ n+m−1 | Có aliasing do chập vòng |
| Quên chia N khi inverse | Hệ số bị nhân N lần |
| Truy vấn chỉ A(x) tại một điểm | Horner O(n) đơn giản hơn |
| Nhiều lần nhân với cùng đa thức | Có thể tái sử dụng phổ của đa thức cố định nếu N và điểm lấy mẫu giống nhau |
| Đa thức rất thưa | Phương pháp khai thác hệ số khác 0 có thể tốt hơn FFT |

**Điểm khác biệt trong biểu diễn đa thức 0:** một mảng `[]` là mảng không có hệ số, được xem là 0 theo hợp đồng API; mảng `[0]` là biểu diễn có một hệ số 0. Nếu hàm nhân muốn trả biểu diễn chuẩn hóa, có thể bỏ các số 0 ở cuối, nhưng phải thống nhất quy ước. Mã demo không bỏ để dễ so với phép chập O(nm).

## 16. Những lỗi thường gặp

1. **Nhầm DFT là một thuật toán bắt buộc O(N²)** thay vì phép biến đổi có thể tính bằng FFT.
2. **Không hiểu DFT là đánh giá đa thức tại N điểm**, chỉ ghi nhớ công thức không có ý nghĩa.
3. **Dùng dấu số mũ ngược** và cho ra phần ảo trái với quy ước.
4. **Quên chia N khi làm IDFT**, nhân kết quả lên N lần.
5. **Nhân hai vector ở những điểm x khác nhau**, không tạo C(x) mong muốn.
6. **Chọn N chỉ bằng max(n,m)**, gây aliasing khi tích cần n+m−1 hệ số.
7. **Cho rằng chập vòng luôn là chập tuyến tính**, không xét hệ số bị cuộn.
8. **Nhân phần thực với phần thực và ảo với ảo**, sai quy tắc nhân số phức.
9. **Lấy sai thứ tự hệ số**, trong khi `a[i]` phải là hệ số của x^i.
10. **Bit-reversal sai**, butterfly đọc các phần tử sai thứ tự.
11. **Sai dấu trong twiddle factor**, khiến DFT thuận không đúng.
12. **Đọc lại phần tử butterfly đã ghi đè** trước khi tính đủ cả u+v và u−v.
13. **Dùng N=3 với mã FFT radix-2** mà không kiểm.
14. **Không xét N=1**, một trường hợp hoàn toàn hợp lệ.
15. **Không cắt output về n+m−1 hệ số**, trả cả phần padding nhiễu.
16. **Cho rằng `Math.round` luôn đúng với mọi đầu vào long**, bỏ qua precision của double.
17. **Đem hệ số thực không nguyên đi làm tròn**, làm mất kết quả số học mong muốn.
18. **Đếm số lượng test thành công mà không kiểm từng hệ số**, khó phát hiện lỗi biên.
19. **Chỉ kiểm C(2)=A(2)B(2)** mà không so cả vector kết quả với oracle.
20. **Nhầm NTT là exact trên số nguyên không modulo**, trong khi kết quả là modulo p.
21. **Không kiểm tràn trong nhân modulo của NTT**, gây sai dù lý thuyết chính xác.
22. **Thử FFT trên số lớn nhưng so bằng == với double**, nhận sai về độ chính xác.
23. **Cho rằng FFT luôn nhanh hơn O(nm)** trên mọi kích thước, bỏ qua overhead.
24. **Không thử hệ số âm**, dễ che lỗi dấu.
25. **Không thử zero-padding ở ranh giới n+m−1 vừa vượt lũy thừa 2**, nơi chọn N dễ sai.

## 17. Kiểm chứng bằng oracle độc lập

Một bài FFT nên được kiểm bằng **cơ chế không dùng FFT** trên đầu vào nhỏ.

**Oracle DFT trực tiếp.** Với N=1,2,4,8,16, tính đúng công thức tổng \(X_k=\sum_j a_j e^{-2\pi ikj/N}\) bằng hai vòng lặp, rồi so phần thực và phần ảo với FFT. Mã Java kiểm **20 vector phức** cho mỗi N, tổng 100 trường hợp.

**Oracle IDFT.** Với cùng 100 vector, chạy FFT thuận rồi ngược, kiểm mỗi phần tử gần giá trị ban đầu. Từ đó phát hiện lỗi dấu, chuẩn hóa, hoán vị và butterfly.

**Oracle nhân đa thức.** Trên dữ liệu nguyên nhỏ, tính:

~~~text
C = zeros[n+m-1]

for i in 0..n-1:
    for j in 0..m-1:
        C[i+j] += A[i]*B[j]
~~~

So tất cả hệ số của FFT sau làm tròn với C. Đây là phép so độc lập vì không sử dụng căn đơn vị, sin/cos hoặc DFT. Mã Java dùng Random seed cố định để thử 200 bộ.

### Bộ test đặc trưng

| A | B | Hệ số tích |
|---|---|---|
| [1,2,3] | [4,5] | [4,13,22,15] |
| [1,1] | [1,1] | [1,2,1] |
| [2,−1,3] | [1,4] | [2,7,−1,12] |
| [5] | [7] | [35] |
| [0] | [7] | [0] |
| [0,0] | [7,0] | [0,0,0] |
| [] | [5] | [] |

Nên thử thêm `needed` đúng bằng một lũy thừa 2 và lớn hơn một lũy thừa 2 đúng một đơn vị. Hai trường hợp khiến kích thước FFT thay đổi đột ngột và thường phát hiện lỗi padding.

## 18. Câu hỏi tự luyện

**Bài 1.** DFT chuyển dãy hệ số thành dạng gì?

*Đáp án:* Các **giá trị của đa thức tại N căn bậc N của đơn vị**.

**Bài 2.** DFT của [1,2,3,0] dùng N=4 là gì?

*Đáp án:* \([6,-2-2i,2,-2+2i]\).

**Bài 3.** Trong quy ước bài, DFT thuận dùng góc dấu gì?

*Đáp án:* Dấu **âm**; IDFT dùng dấu dương và chia N.

**Bài 4.** Vì sao có IDFT?

*Đáp án:* Vì các căn bậc N của đơn vị tạo ma trận đánh giá khả nghịch; tổng trực giao triệt tiêu các hệ số khác vị trí cần lấy.

**Bài 5.** Khi nhân hai đa thức tại dạng giá trị, hai vector phải cùng điều kiện nào?

*Đáp án:* Các giá trị phải được đánh giá tại **cùng hệ điểm x_k**.

**Bài 6.** Viết cách tách chẵn–lẻ của A(x).

*Đáp án:* \(A(x)=E(x^2)+xO(x^2)\), E gom hệ số chỉ số chẵn, O gom hệ số chỉ số lẻ.

**Bài 7.** Butterfly tạo hai đầu ra từ u,v như thế nào?

*Đáp án:* **u+v** và **u−v**.

**Bài 8.** Tính DFT trực tiếp và dùng FFT radix-2 có thời gian bao nhiêu?

*Đáp án:* Lần lượt **O(N²)** và **O(N log N)**.

**Bài 9.** A có 5 hệ số, B có 3 hệ số. Tích cần tối đa bao nhiêu hệ số?

*Đáp án:* **7**, vì 5+3−1=7.

**Bài 10.** Với hai đa thức trên, chọn N radix-2 nhỏ nhất là bao nhiêu?

*Đáp án:* **8**.

**Bài 11.** Với A=[1,2,3], B=[4,5], chọn N=3 có gì xảy ra?

*Đáp án:* Kết quả chập vòng là **[19,13,22]**, sai so với chập tuyến tính **[4,13,22,15]**.

**Bài 12.** Vì sao N≥n+m−1 ngăn aliasing?

*Đáp án:* Bậc tích nhỏ hơn N, không có hệ số bậc ≥N bị cuộn vào bậc thấp.

**Bài 13.** Nếu quên chia N trong IDFT, kết quả thay đổi thế nào?

*Đáp án:* Trong số học chính xác, hệ số khôi phục bị nhân **N lần**.

**Bài 14.** DFT có tồn tại với N=3 không?

*Đáp án:* Có. Chỉ mã FFT radix-2 minh họa yêu cầu N là lũy thừa 2.

**Bài 15.** Nếu một bên đa thức chỉ có một hệ số, có cần FFT không?

*Đáp án:* Không cần; nhân từng hệ số với hằng số là O(n).

**Bài 16.** Làm tròn double sau IDFT có luôn cho đúng tích số nguyên long?

*Đáp án:* **Không**. Sai số dấu phẩy động và giới hạn độ chính xác có thể làm hỏng hệ số.

**Bài 17.** Khi cần nhân đa thức nguyên chính xác theo modulo phù hợp, cân nhắc gì?

*Đáp án:* **NTT**. Nếu phải tái dựng hệ số lớn không modulo, có thể cần nhiều modulo kết hợp **CRT**.

**Bài 18.** Vì sao một giá trị C(2)=A(2)B(2) chưa chứng minh toàn bộ hệ số đúng?

*Đáp án:* Hai đa thức khác nhau có thể có cùng giá trị tại một điểm; phải so từng hệ số hoặc dùng đủ các điểm.

**Bài 19.** Với đầu vào thực, hai giá trị DFT X_k và X_{N-k} có quan hệ gì?

*Đáp án:* Chúng là **liên hợp phức** của nhau.

**Bài 20.** Để kiểm FFT độc lập, có thể dùng oracle nào?

*Đáp án:* **DFT trực tiếp O(N²)**, **IDFT round-trip** và **nhân đa thức O(nm)** trên dữ liệu nhỏ.

**Tổng kết:** DFT là phép đánh giá đa thức có N hệ số tại **N căn bậc N của đơn vị**; IDFT nội suy ngược về hệ số dựa trên tính trực giao của các căn ấy. FFT radix-2 tách **hệ số chẵn và lẻ**, kết hợp bằng butterfly để tính DFT trong **O(N log N)**. Để nhân hai đa thức dài n,m, phải chọn **N≥n+m−1**, padding, FFT hai dãy, nhân giá trị từng điểm và IDFT. Nếu N quá nhỏ, kết quả là **chập vòng** bị aliasing chứ không phải tích tuyến tính. Mã Java 17 minh họa cách cài và oracle kiểm chứng; khi cần hệ số nguyên **chính xác tuyệt đối** ở quy mô lớn, phải phân tích sai số `double` hoặc chuyển sang NTT/CRT.
