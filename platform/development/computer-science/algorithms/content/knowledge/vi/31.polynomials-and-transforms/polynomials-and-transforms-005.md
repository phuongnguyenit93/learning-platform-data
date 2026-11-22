# FFT bằng chia để trị chẵn–lẻ

**Chủ đề:** Computer Science Algorithms · Đa thức và biến đổi

## 1. Vì sao FFT xuất hiện trong bài toán đa thức?

Một đa thức có thể được biểu diễn bằng **mảng hệ số**:

\[
A(x)=a_0+a_1x+a_2x^2+\cdots+a_{n-1}x^{n-1}.
\]

Mảng A=[1,2,3] nghĩa là A(x)=1+2x+3x². Với B=[4,5], ta có B(x)=4+5x.

Nhân trực tiếp:

\[
A(x)B(x)=4+13x+22x^2+15x^3.
\]

Vì vậy mảng hệ số tích là:

~~~text
A = [1, 2, 3]
B = [4, 5]
A * B = [4, 13, 22, 15]
~~~

**Nhân đa thức thông thường** duyệt mọi cặp hệ số a_i,b_j rồi cộng a_i×b_j vào hệ số ở bậc i+j, mất O(nm) cho hai mảng dài n,m.

**FFT (Fast Fourier Transform, biến đổi Fourier nhanh)** cho phép tính **biến đổi Fourier rời rạc (DFT)** trên N giá trị với O(N log N) phép toán, thay vì O(N²) của công thức DFT trực tiếp. Kết hợp FFT với định lý tích chập, ta có thể nhân hai đa thức trong khoảng **O(N log N)** khi N được chọn ít nhất bằng n+m−1 và thường làm tròn lên lũy thừa của 2.

Bài này tập trung vào **Cooley–Tukey radix-2 FFT bằng chia để trị chẵn–lẻ**: phân dãy theo vị trí chẵn/lẻ, tính hai DFT nhỏ rồi ghép qua **butterfly** và **căn bậc N của đơn vị (roots of unity)**. Sau đó triển khai Java 17 có FFT thuận/nghịch, nhân đa thức, kiểm thử với DFT chậm và phép nhân trực tiếp. Phần sai số số thực và giới hạn không thể bỏ qua.

## 2. DFT: từ dãy hệ số sang các giá trị ở căn đơn vị

Cho dãy phức a[0..N−1]. Đặt:

\[
\omega_N=e^{-2\pi i/N},
\]

với \(i^2=-1\). Đây là căn đơn vị nguyên thủy bậc N:

\[
\omega_N^N=1,\qquad
\omega_N^{N/2}=-1
\]

(khi N chẵn), và các giá trị \(\omega_N^0,\omega_N^1,\ldots,\omega_N^{N-1}\) khác nhau.

**DFT thuận** (quy ước dấu âm trong số mũ):

\[
\boxed{
X[k]=\sum_{j=0}^{N-1}a[j]\omega_N^{jk},
\qquad 0\le k<N.
}
\]

Nếu xem A(x)=∑ a[j]x^j, thì X[k] chính là A được **đánh giá tại x=ω_N^k**. FFT không thay đổi ý nghĩa toán học của DFT; nó chỉ tính cùng các giá trị này **nhanh hơn**.

### 2.1. Ví dụ dãy bốn điểm

Lấy:

~~~text
a = [1, 2, 3, 0]
N = 4
omega_4 = -i
~~~

Tính theo định nghĩa:

\[
X[0]=1+2+3+0=6.
\]

\[
X[1]=1+2(-i)+3(-1)+0(i)=-2-2i.
\]

\[
X[2]=1+2(-1)+3(1)+0(-1)=2.
\]

\[
X[3]=1+2(i)+3(-1)+0(-i)=-2+2i.
\]

Vậy:

~~~text
DFT([1,2,3,0]) = [6, -2-2i, 2, -2+2i]
~~~

Các số phức không phải lỗi: dù hệ số đầu vào là số thực, giá trị tại các điểm phức thường có phần ảo.

### 2.2. Độ phức tạp DFT theo định nghĩa

Có N giá trị X[k]. Mỗi giá trị là tổng N số hạng; tính trực tiếp cần **O(N²)** phép toán phức. FFT radix-2 sẽ khai thác cấu trúc của các lũy thừa ω_N để tránh tính lại phần chung.

## 3. Chia để trị chẵn–lẻ

Giả sử **N là lũy thừa của 2**, N≥2. Tách các hệ số theo **chỉ số chẵn và lẻ**:

\[
A(x)=A_{\mathrm{even}}(x^2)+xA_{\mathrm{odd}}(x^2),
\]

trong đó:

\[
A_{\mathrm{even}}(y)=a_0+a_2y+a_4y^2+\cdots,
\]

\[
A_{\mathrm{odd}}(y)=a_1+a_3y+a_5y^2+\cdots.
\]

Tức với a=[a0,a1,a2,a3,a4,a5,a6,a7]:

~~~text
even = [a0, a2, a4, a6]
odd  = [a1, a3, a5, a7]
~~~

Ta có \(\omega_N^{2k}=\omega_{N/2}^k\). Do đó, đặt:
- E[k] là DFT kích thước N/2 của dãy hệ số chẵn.
- O[k] là DFT kích thước N/2 của dãy hệ số lẻ.

Khi đánh giá đa thức ban đầu tại \(\omega_N^k\):

\[
X[k]=E[k]+\omega_N^kO[k].
\]

Vì \(\omega_N^{k+N/2}=-\omega_N^k\), cùng E[k],O[k] còn cho điểm đối xứng:

\[
X[k+N/2]=E[k]-\omega_N^kO[k].
\]

Hai phương trình tạo thành **butterfly**:

\[
\boxed{
\begin{aligned}
t&=\omega_N^kO[k],\\
X[k]&=E[k]+t,\\
X[k+N/2]&=E[k]-t,
\end{aligned}
\qquad 0\le k<N/2.
}
\]

Thay vì tính hai tổng N phần tử độc lập, mỗi butterfly chỉ dùng **một phép nhân phức và hai phép cộng/trừ phức** sau khi đã có hai nửa.

### 3.1. Vì sao không phải chỉ tách đôi liên tiếp?

Chia ở đây là **theo tính chẵn/lẻ của chỉ số**, không phải lấy nửa đầu a[0..N/2) và nửa cuối a[N/2..N). Đẳng thức A(x)=A_even(x²)+xA_odd(x²) là chìa khóa của radix-2 FFT.

Nếu tách hai nửa liên tiếp mà vẫn áp dụng công thức butterfly chẵn/lẻ, thuật toán không còn tương ứng với phân rã đại số trên và có thể cho DFT sai.

### 3.2. Base case

Khi N=1, dãy chỉ có một giá trị a0 và DFT bằng chính a0:

\[
DFT_1([a_0])=[a_0].
\]

Đây là điểm dừng đệ quy. Một FFT radix-2 thông thường yêu cầu N≥1 và là lũy thừa của 2; dãy rỗng không phải biến đổi kích thước hợp lệ của phiên bản này.

## 4. Truy vết butterfly với [1,2,3,0]

Tách:

~~~text
a = [1, 2, 3, 0]
even = [1, 3]
odd  = [2, 0]
~~~

Hai DFT kích thước 2:
- DFT2([1,3]) = [1+3,1−3] = **[4,−2]**.
- DFT2([2,0]) = [2+0,2−0] = **[2,2]**.

Gọi E=[4,−2], O=[2,2].

### Butterfly k=0

\[
\omega_4^0=1,\quad t=1\times O[0]=2.
\]

Vậy:

\[
X[0]=4+2=6,\qquad X[2]=4-2=2.
\]

### Butterfly k=1

\[
\omega_4^1=-i,\quad t=(-i)\times O[1]=-2i.
\]

Vậy:

\[
X[1]=-2-2i,\qquad X[3]=-2+2i.
\]

Ghép đúng thứ tự k=0,1,2,3:

~~~text
E = [ 4, -2 ]
O = [ 2,  2 ]
X = [ 6, -2-2i, 2, -2+2i ]
~~~

Kết quả trùng hoàn toàn với phép tính DFT trực tiếp ở phần 2. Đây là kiểm tra cụ thể cho cả **dấu mũ**, **thứ tự chỉ số** và **công thức butterfly**.

## 5. Độ phức tạp của FFT chẵn–lẻ

Với N≥2 và N là lũy thừa của 2, mỗi lời gọi:
1. Tách thành hai dãy độ dài N/2: O(N).
2. Gọi đệ quy hai FFT kích thước N/2.
3. Ghép N/2 butterfly: O(N).

Do đó:

\[
T(N)=2T(N/2)+O(N),\qquad T(1)=O(1).
\]

Theo định lý Master, hoặc theo cây đệ quy có log₂N mức và mỗi mức O(N):

\[
\boxed{T(N)=O(N\log N)}.
\]

So với DFT trực tiếp O(N²), số phép toán giảm đáng kể khi N lớn. Ví dụ N=2²⁰, số cặp tính toán theo FFT có bậc N log₂N thay vì N².

**Bộ nhớ:** bản đệ quy minh họa tạo các mảng even, odd và kết quả ở mỗi lời gọi, dùng **O(N)** bộ nhớ sống bổ sung ở đỉnh trong quá trình duyệt đệ quy sâu và O(log N) mức stack; **tổng lượng phần tử mảng đã cấp phát qua cả quá trình** có thể đạt O(N log N). Cách FFT iterative in-place với **bit-reversal permutation** có thể giảm số đối tượng/mảng cấp phát, nhưng bài này cố ý chọn bản đệ quy chẵn–lẻ vì thể hiện trực tiếp chứng minh toán học.

## 6. FFT nghịch (IFFT) và quy tắc chuẩn hóa

DFT có phép biến đổi ngược. Với quy ước DFT thuận dùng dấu âm:

\[
X[k]=\sum_{j=0}^{N-1}a[j]e^{-2\pi ijk/N},
\]

**DFT nghịch (IDFT)** dùng dấu dương và chia N:

\[
\boxed{
a[j]=\frac1N\sum_{k=0}^{N-1}X[k]e^{+2\pi ijk/N}.
}
\]

Vì vậy để biến FFT thuận thành FFT nghịch:
- Đổi dấu của góc quay: dùng **+2π/N** thay cho **−2π/N**.
- **Chia mọi hệ số đầu ra cho N đúng một lần.**

Một lựa chọn khác là chia 2 ở mỗi tầng butterfly của FFT nghịch; do có log₂N tầng, tổng hệ số chia là N. Hai cách tương đương nếu cài nhất quán. Chương trình trong bài **chỉ chuẩn hóa ở lời gọi ngoài cùng**, không chia tại mỗi bước đệ quy.

### 6.1. Vì sao phải chia N?

Tính chất trực giao của các căn đơn vị cho:

\[
\sum_{k=0}^{N-1}\omega_N^{k(j-\ell)}
=\begin{cases}
N & j=\ell,\\
0 & j\ne\ell.
\end{cases}
\]

Khi thay công thức DFT vào IDFT, mọi thành phần không trùng chỉ số bị triệt tiêu; thành phần trùng xuất hiện N lần, nên cần hệ số 1/N để phục hồi a[j].

**Nếu quên chia N**, FFT nghịch trả N×a[j], không phải a[j].

## 7. Nhân đa thức qua tích chập

Với A=[a0,...,a_{n−1}] và B=[b0,...,b_{m−1}], hệ số thứ t của tích là:

\[
\boxed{c_t=\sum_{i+j=t}a_ib_j}.
\]

Đó là **tích chập tuyến tính (linear convolution)**. Số hệ số theo biểu diễn mảng thông thường là **n+m−1**, nếu cả hai mảng không rỗng.

Định lý tích chập cho DFT cùng độ dài N:

\[
DFT_N(c)=DFT_N(a)\odot DFT_N(b),
\]

trong đó \(\odot\) là **nhân từng thành phần**. Tuy nhiên DFT độ dài N tự nhiên mô tả **tích chập vòng (circular convolution)**. Để kết quả vòng bằng tích chập tuyến tính, cần thêm đủ số 0 để **không bị quấn chỉ số (wrap-around)**.

### 7.1. Chọn độ dài đệm zero-padding

Nếu A dài n và B dài m, cần:

\[
\boxed{N\ge n+m-1}.
\]

Với FFT radix-2, chọn:

\[
N=2^{\lceil \log_2(n+m-1)\rceil}
\]

cho n,m>0, tức **lũy thừa 2 nhỏ nhất không nhỏ hơn n+m−1**.

Sau đó:
1. Tạo hai dãy độ dài N, sao chép hệ số rồi điền 0 vào phần dư.
2. Tính FA=FFT(A), FB=FFT(B).
3. Nhân từng vị trí FC[k]=FA[k]×FB[k].
4. Tính C=IFFT(FC).
5. Chỉ lấy **n+m−1 hệ số đầu** làm kết quả tuyến tính.

Nếu một mảng đầu vào rỗng, bài này quy định kết quả là mảng rỗng, không gọi FFT với độ dài 0.

### 7.2. Ví dụ kiểm tra ở cả miền hệ số và miền tần số

A=[1,2,3] và B=[4,5]. Chiều dài tích tuyến tính là 3+2−1=4, vậy N=4 (đã là lũy thừa của 2).

Các hệ số sau padding:

~~~text
A4 = [1, 2, 3, 0]
B4 = [4, 5, 0, 0]
~~~

FFT thuận:

~~~text
FA = [6, -2-2i, 2, -2+2i]
FB = [9, 4-5i, -1, 4+5i]
~~~

Nhân điểm:

~~~text
FC = [54, -18+2i, -2, -18-2i]
~~~

IFFT của FC (chia 4) cho:

~~~text
[4, 13, 22, 15]
~~~

Đối chiếu nhân trực tiếp:
- c0=1×4=4.
- c1=1×5+2×4=5+8=13.
- c2=2×5+3×4=10+12=22.
- c3=3×5=15.

**Kết quả khớp chính xác trên toán học**; khi tính bằng double, có thể gặp các sai số nhỏ gần 0 hoặc gần số nguyên.

### 7.3. Nếu đệm thiếu sẽ xảy ra gì?

Tích tuyến tính có bốn hệ số [4,13,22,15]. Nếu cố biểu diễn tích chập vòng trên độ dài N=3 (về mặt toán học), hệ số ở chỉ số 3 bị **gập** về chỉ số 0:

~~~text
Linear:   [ 4, 13, 22, 15 ]
Cyclic N=3:
  index0 = 4 + 15 = 19
  index1 = 13
  index2 = 22
Result:   [19, 13, 22]
~~~

Đây là **aliasing/wrap-around**, không phải tích đa thức tuyến tính mong muốn. Bản radix-2 trong bài không chấp nhận N=3; ví dụ chỉ minh họa sự khác nhau của phép tích chập vòng so với tuyến tính.

### 7.4. Đa thức hệ số âm, số thực và trailing zeros

FFT phức làm việc với các hệ số double âm và thập phân:
- A=[−1,2], B=[3,−1] → [−3,7,−2].
- A=[0.5,−1], B=[2,0.25] → [1,−1.875,−0.25].
- A=[0,0], B=[3,4] → mảng [0,0,0] theo **độ dài biểu diễn 2+2−1**, dù đa thức toán học bằng 0.
- A=[] hoặc B=[] → [] theo quy ước của API này.
- Hai đa thức chỉ có một hệ số dùng N=1; FFT trả phần tử đó, nhân hai hệ số trực tiếp.

Không nên tự cắt bỏ các số 0 cuối mảng nếu hợp đồng cần bảo toàn chiều dài n+m−1.

## 8. Sai số số thực: FFT không phải phép nhân số nguyên chính xác

FFT phức được tính qua **Math.cos, Math.sin và phép toán double**. Các căn đơn vị và giá trị trung gian thường không thể biểu diễn chính xác theo nhị phân.

Vì thế sau IFFT một hệ số toán học bằng 13 có thể thu được 12.999999999999998 hoặc 13.000000000000002. Phần ảo đáng ra bằng 0 có thể chỉ nhỏ gần 0, chứ không đúng 0 tuyệt đối.

Các nguyên tắc:
- Nếu đầu ra là **hệ số thực**, lấy phần thực sau IFFT và kiểm soát độ lớn phần ảo (nếu cần đảm bảo dữ liệu thực).
- Khi hệ số toán học là **số nguyên đủ nhỏ** và đã chứng minh sai số thấp hơn 0.5, có thể dùng Math.round để làm tròn về số nguyên gần nhất.
- **Không được khẳng định Math.round luôn khôi phục chính xác mọi tích đa thức số nguyên.** Với hệ số lớn, chiều dài lớn hoặc sai số tích lũy, kết quả làm tròn có thể sai hẳn số nguyên.
- double chỉ biểu diễn nguyên chính xác tới một số giới hạn về độ lớn (mọi số nguyên tới 2^53 về trị tuyệt đối); nhiều số nguyên lớn hơn không có biểu diễn chính xác.
- Nếu cần kết quả **chính xác theo modulo**, xem xét **NTT (Number Theoretic Transform)** với môđun nguyên tố thích hợp có căn đơn vị nguyên thủy độ dài N. Một NTT độ dài 2^t thường đòi N chia hết p−1; có thể dùng nhiều môđun NTT và CRT nếu cần miền giá trị lớn hơn.
- Với dữ liệu rất nhỏ, nhân đa thức O(nm) bằng long/BigInteger có thể đơn giản và đáng tin cậy hơn.

Chương trình sau chỉ dùng phép làm tròn **để trình bày các ví dụ nhỏ với hệ số nguyên đã kiểm soát**. Hàm convolve trả **double[] không làm tròn**, để caller quyết định chính sách sai số.

## 9. Chương trình Java 17: đệ quy chẵn–lẻ và convolution

Lưu file **FftEvenOddDemo.java**. Phiên bản này có:
- Kiểu Complex bất biến bằng Java record.
- FFT đệ quy chia theo chỉ số chẵn/lẻ.
- DFT nghịch dùng dấu góc dương và **chia N ở ngoài**.
- Kiểm tra N là lũy thừa 2, đầu vào không null và số thực hữu hạn.
- Nhân đa thức bằng zero-padding đủ độ dài tuyến tính.
- DFT chậm O(N²) làm oracle cho ví dụ bốn điểm.
- Nhân đa thức O(nm) dùng đối chiếu kết quả.
- Hàm trình bày làm tròn **chỉ cho demo**, tách khỏi thuật toán FFT thật.

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class FftEvenOddDemo {
    private FftEvenOddDemo() {
    }

    public record Complex(double re, double im) {
        Complex add(Complex other) {
            return new Complex(
                    re + other.re, im + other.im);
        }

        Complex subtract(Complex other) {
            return new Complex(
                    re - other.re, im - other.im);
        }

        Complex multiply(Complex other) {
            return new Complex(
                    re * other.re - im * other.im,
                    re * other.im + im * other.re);
        }

        Complex dividedBy(double scalar) {
            return new Complex(re / scalar, im / scalar);
        }
    }

    private static final Complex ZERO = new Complex(0.0, 0.0);
    private static final Complex ONE = new Complex(1.0, 0.0);

    private static void checkTransformInput(Complex[] data) {
        Objects.requireNonNull(data, "data");

        if (data.length == 0
                || Integer.bitCount(data.length) != 1) {
            throw new IllegalArgumentException(
                    "FFT length must be a positive power of two");
        }

        for (Complex value : data) {
            if (value == null
                    || !Double.isFinite(value.re())
                    || !Double.isFinite(value.im())) {
                throw new IllegalArgumentException(
                        "FFT values must be finite");
            }
        }
    }

    // Cooley-Tukey radix-2: chia theo chỉ số chẵn/lẻ.
    private static Complex[] recursiveFft(
            Complex[] data, boolean inverse) {
        int n = data.length;
        if (n == 1) {
            return new Complex[]{data[0]};
        }

        Complex[] even = new Complex[n / 2];
        Complex[] odd = new Complex[n / 2];

        for (int i = 0; i < n / 2; i++) {
            even[i] = data[2 * i];
            odd[i] = data[2 * i + 1];
        }

        Complex[] e = recursiveFft(even, inverse);
        Complex[] o = recursiveFft(odd, inverse);
        Complex[] answer = new Complex[n];

        double angle = (inverse ? 2.0 : -2.0)
                * Math.PI / n;
        Complex root = new Complex(
                Math.cos(angle), Math.sin(angle));
        Complex w = ONE;

        for (int k = 0; k < n / 2; k++) {
            Complex t = w.multiply(o[k]);

            answer[k] = e[k].add(t);
            answer[k + n / 2] = e[k].subtract(t);

            w = w.multiply(root);
        }
        return answer;
    }

    // Chỉ hàm ngoài cùng chuẩn hóa IDFT bằng 1/n.
    public static Complex[] transform(
            Complex[] input, boolean inverse) {
        checkTransformInput(input);
        Complex[] result = recursiveFft(input, inverse);

        if (inverse) {
            for (int i = 0; i < result.length; i++) {
                result[i] = result[i].dividedBy(input.length);
            }
        }
        return result;
    }

    private static Complex[] asComplex(
            double[] values, int n) {
        Complex[] result = new Complex[n];
        Arrays.fill(result, ZERO);

        for (int i = 0; i < values.length; i++) {
            if (!Double.isFinite(values[i])) {
                throw new IllegalArgumentException(
                        "Non-finite polynomial coefficient");
            }
            result[i] = new Complex(values[i], 0.0);
        }
        return result;
    }

    // Lũy thừa hai nhỏ nhất >= required.
    private static int nextPowerOfTwo(long required) {
        if (required <= 0) {
            throw new IllegalArgumentException(
                    "Required length must be positive");
        }
        int n = 1;

        while ((long) n < required) {
            if (n > Integer.MAX_VALUE / 2) {
                throw new IllegalArgumentException(
                        "Transform is too large");
            }
            n *= 2;
        }
        return n;
    }

    // Tích chập TUYẾN TÍNH, không phải circular convolution.
    public static double[] convolve(double[] a, double[] b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");

        if (a.length == 0 || b.length == 0) {
            return new double[0];
        }

        long neededLong = (long) a.length + b.length - 1;
        if (neededLong > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "Result array too large");
        }

        int needed = (int) neededLong;
        int n = nextPowerOfTwo(needed);
        Complex[] fa = transform(asComplex(a, n), false);
        Complex[] fb = transform(asComplex(b, n), false);

        for (int k = 0; k < n; k++) {
            fa[k] = fa[k].multiply(fb[k]);
        }

        Complex[] time = transform(fa, true);
        double[] result = new double[needed];

        for (int i = 0; i < needed; i++) {
            result[i] = time[i].re();
        }
        return result;
    }

    // Oracle O(n*m), dùng cho kiểm tra dữ liệu nhỏ.
    public static double[] naiveConvolve(
            double[] a, double[] b) {
        if (a.length == 0 || b.length == 0) {
            return new double[0];
        }

        double[] result =
                new double[a.length + b.length - 1];
        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < b.length; j++) {
                result[i + j] += a[i] * b[j];
            }
        }
        return result;
    }

    // DFT theo định nghĩa: O(n^2), oracle độc lập.
    public static Complex[] slowDft(Complex[] data) {
        Objects.requireNonNull(data, "data");
        int n = data.length;
        Complex[] result = new Complex[n];

        for (int k = 0; k < n; k++) {
            Complex sum = ZERO;

            for (int t = 0; t < n; t++) {
                double angle = -2.0 * Math.PI
                        * k * t / n;
                Complex phase = new Complex(
                        Math.cos(angle), Math.sin(angle));
                sum = sum.add(data[t].multiply(phase));
            }
            result[k] = sum;
        }
        return result;
    }

    private static boolean close(
            Complex[] a, Complex[] b, double eps) {
        if (a.length != b.length) {
            return false;
        }
        for (int i = 0; i < a.length; i++) {
            double dr = a[i].re() - b[i].re();
            double di = a[i].im() - b[i].im();

            if (Math.hypot(dr, di) > eps) {
                return false;
            }
        }
        return true;
    }

    private static boolean close(
            double[] a, double[] b, double eps) {
        if (a.length != b.length) {
            return false;
        }
        for (int i = 0; i < a.length; i++) {
            if (Math.abs(a[i] - b[i]) > eps) {
                return false;
            }
        }
        return true;
    }

    // Chỉ dùng để HIỂN THỊ các ví dụ có hệ số nguyên nhỏ.
    private static long[] roundSmallExample(double[] a) {
        long[] result = new long[a.length];

        for (int i = 0; i < a.length; i++) {
            double nearest = Math.rint(a[i]);

            if (!Double.isFinite(a[i])
                    || Math.abs(a[i] - nearest) > 1e-6
                    || Math.abs(nearest) > 1_000_000.0) {
                throw new IllegalArgumentException(
                        "Not a small near-integer example");
            }
            result[i] = Math.round(a[i]);
        }
        return result;
    }

    private static long[] roundSmallReal(Complex[] a) {
        double[] real = new double[a.length];

        for (int i = 0; i < a.length; i++) {
            if (Math.abs(a[i].im()) > 1e-6) {
                throw new IllegalArgumentException(
                        "Non-negligible imaginary component");
            }
            real[i] = a[i].re();
        }
        return roundSmallExample(real);
    }

    private static String displaySpectrum(Complex[] a) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < a.length; i++) {
            if (i > 0) {
                sb.append(", ");
            }
            sb.append("(")
                    .append(Math.round(a[i].re()))
                    .append(",")
                    .append(Math.round(a[i].im()))
                    .append("i)");
        }
        return sb.append("]").toString();
    }

    public static void main(String[] args) {
        Complex[] input = asComplex(
                new double[]{1, 2, 3, 0}, 4);
        Complex[] frequency = transform(input, false);

        System.out.println("DFT4: "
                + displaySpectrum(frequency));
        System.out.println("IDFT4: "
                + Arrays.toString(
                        roundSmallReal(transform(
                                frequency, true))));
        System.out.println("FFT matches direct DFT: "
                + close(frequency, slowDft(input), 1e-9));

        double[] a = {1, 2, 3};
        double[] b = {4, 5};
        double[] product = convolve(a, b);

        System.out.println("Polynomial product: "
                + Arrays.toString(roundSmallExample(product)));
        System.out.println("Matches naive convolution: "
                + close(product, naiveConvolve(a, b), 1e-9));
        System.out.println("Chosen FFT length: "
                + nextPowerOfTwo(a.length + b.length - 1));

        System.out.println("Negative coefficients: "
                + Arrays.toString(
                        roundSmallExample(convolve(
                                new double[]{-1, 2},
                                new double[]{3, -1}))));
        System.out.println("Single coefficients: "
                + Arrays.toString(
                        roundSmallExample(convolve(
                                new double[]{5},
                                new double[]{7}))));
        System.out.println("Empty polynomial: "
                + Arrays.toString(convolve(
                        new double[0], new double[]{4, 5})));
        System.out.println("Zero polynomial: "
                + Arrays.toString(
                        roundSmallExample(convolve(
                                new double[]{0, 0},
                                new double[]{3, 4}))));
        System.out.println("Fractional coefficients correct: "
                + close(
                        convolve(
                                new double[]{0.5, -1},
                                new double[]{2, 0.25}),
                        new double[]{1, -1.875, -0.25},
                        1e-9));

        // Chỉ minh họa phép gập của linear convolution:
        long[] circular = new long[3];
        long[] integerProduct = roundSmallExample(product);
        for (int i = 0; i < integerProduct.length; i++) {
            circular[i % 3] += integerProduct[i];
        }
        System.out.println("Cyclic fold N=3: "
                + Arrays.toString(circular));

        try {
            transform(asComplex(
                    new double[]{1, 2, 3}, 3), false);
            System.out.println("Reject non-power-of-two: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject non-power-of-two: true");
        }
    }
}
~~~

### 9.1. Biên dịch và chạy

Với **JDK 17 trở lên**, lưu đúng tên public class và chạy:

~~~bash
javac -encoding UTF-8 FftEvenOddDemo.java
java FftEvenOddDemo
~~~

**Stdout dự kiến:**

~~~text
DFT4: [(6,0i), (-2,-2i), (2,0i), (-2,2i)]
IDFT4: [1, 2, 3, 0]
FFT matches direct DFT: true
Polynomial product: [4, 13, 22, 15]
Matches naive convolution: true
Chosen FFT length: 4
Negative coefficients: [-3, 7, -2]
Single coefficients: [35]
Empty polynomial: []
Zero polynomial: [0, 0, 0]
Fractional coefficients correct: true
Cyclic fold N=3: [19, 13, 22]
Reject non-power-of-two: true
~~~

### 9.2. Những điều quan trọng khi đọc code

**Complex record:** biểu diễn số z=re+i×im. Phép nhân (a+bi)(c+di)=(ac−bd)+(ad+bc)i. Kiểu bất biến giúp các nhánh đệ quy không vô tình sửa số phức dùng chung.

**recursiveFft:** tách data[2i] và data[2i+1] vào even/odd, gọi lại cùng thuật toán với N/2, rồi dùng root=e^{±2πi/N} và biến w cập nhật lũy thừa root ở mỗi butterfly.

**transform:** kiểm tra chiều dài lũy thừa 2 và giá trị hữu hạn trước khi chạy. Với inverse=true, nó chia N đúng một lần sau khi recursiveFft hoàn tất.

**asComplex:** zero-padding các hệ số số thực bằng số phức có phần ảo 0. ZERO là record bất biến nên dùng chung được trong các phần tử chưa có hệ số.

**nextPowerOfTwo:** chọn N đủ lớn để tích chập vòng không quấn vào hệ số tuyến tính. Dùng long cho chiều dài cần thiết; kiểm tra trước khi nhân đôi int để không overflow. Khi N rất lớn, dù chỉ số vẫn hợp lệ, ứng dụng vẫn có thể thiếu bộ nhớ; code không hứa hỗ trợ mọi kích thước lý thuyết.

**convolve:** thực hiện FFT(A), FFT(B), nhân từng tần số, IFFT; trả n+m−1 phần thực, không tự làm tròn kết quả. Phần ảo đáng ra nhỏ với dữ liệu thực, nhưng nếu cần chế độ kiểm chứng nghiêm ngặt nên kiểm tra sai số phần ảo và một ngưỡng lỗi tương ứng miền dữ liệu.

**slowDft:** O(N²), cài đúng định nghĩa DFT với dấu âm, độc lập về cơ chế chẵn/lẻ. Nó được dùng làm oracle so sánh ở ví dụ nhỏ, không phải lựa chọn cho dữ liệu lớn.

**naiveConvolve:** duyệt mọi cặp hệ số, dùng oracle cho tích chập. Phương pháp này có cùng định nghĩa đầu ra nhưng khác cơ chế với FFT nên tốt cho regression tests.

**displaySpectrum, roundSmallExample:** hai hàm **chỉ làm tròn số để in ví dụ nhỏ**. Dùng chúng để tính sản phẩm đa thức tổng quát hoặc để bảo đảm đúng tuyệt đối cho hệ số rất lớn là sai. Ngưỡng 1e−6 chỉ là kiểm tra minh họa, không phải chứng minh sai số toàn cục.

**Cyclic fold N=3:** mảng [19,13,22] được tính bằng cách gập hệ số thứ 3 vào thứ 0, nhằm minh họa aliasing. Nó không gọi FFT kích thước 3 vì bản radix-2 này chỉ chấp nhận N là lũy thừa 2.

## 10. Độ phức tạp toàn pipeline và trường hợp biên

Cho hai đa thức có n,m hệ số, không rỗng. Đặt L=n+m−1 và N là lũy thừa 2 nhỏ nhất thỏa N≥L.

Vì N<2L với L>1, ta có N=Θ(L). Pipeline:
- Sao chép và zero-padding: O(N).
- Hai FFT thuận: mỗi cái O(N log N).
- N phép nhân phức điểm: O(N).
- Một FFT nghịch: O(N log N).
- Cắt kết quả về L hệ số: O(L).

Tổng:

\[
\boxed{O((n+m)\log(n+m))}
\]

với n,m≥1 và n+m≥3; khi rất nhỏ thì xử lý O(1). Có O(N) bộ nhớ phụ sống cho các dãy phức/tầng đệ quy, cộng nhiều đối tượng và lượng cấp phát tổng cộng có thể đạt O(N log N) trong bản đệ quy minh họa.

### 10.1. Bảng test biên

| Trường hợp | Kết quả / điều kiện |
|---|---|
| FFT N=1 | Trả chính phần tử đầu vào |
| FFT N=0 | Từ chối |
| FFT N=3 | Từ chối vì không là lũy thừa 2 |
| FFT N=4 của [1,2,3,0] | [6,−2−2i,2,−2+2i] |
| IFFT của phổ trên | [1,2,3,0], sau chuẩn hóa 1/4 |
| [1,2,3] × [4,5] | [4,13,22,15] |
| [−1,2] × [3,−1] | [−3,7,−2] |
| [5] × [7] | [35] |
| Một đa thức rỗng | [] theo hợp đồng |
| [0,0] × [3,4] | [0,0,0] giữ chiều dài |
| [0.5,−1] × [2,0.25] | [1,−1.875,−0.25] gần đúng |
| Không đủ padding | Xuất hiện circular aliasing |
| Hệ số rất lớn | Có nguy cơ sai số/rounding |
| NaN/Infinity | Từ chối ở API FFT/convolve có dữ liệu cần biến đổi |

## 11. Kiểm thử độc lập và bất biến

### 11.1. So FFT với DFT trực tiếp

Với N=1,2,4,8,16,... nhỏ:
1. Sinh mảng các số phức có phần thực/ảo ngẫu nhiên vừa phải.
2. Tính FFT bằng chia chẵn/lẻ.
3. Tính DFT trực tiếp bằng hai vòng lặp theo công thức tổng.
4. So từng phần tử bằng một sai số có giới hạn, ví dụ \( |x-y|\le\epsilon \) cho dữ liệu và N nhỏ.
5. Chạy IFFT(FFT(a)), so với a.

Vì double không tính chính xác tuyệt đối, không nên kiểm thử bằng toán tử == trên các giá trị thực có qua sin/cos.

### 11.2. So convolution với nhân trực tiếp

Với các đa thức ngắn được sinh ngẫu nhiên:
1. Nhân trực tiếp c[k]+=a[i]×b[j].
2. Nhân qua FFT, chọn N≥n+m−1.
3. So các hệ số bằng sai số phù hợp độ lớn hệ số và chiều dài.
4. Thử cả âm, 0, số thập phân và những mảng có trailing zeros.

Cách kiểm thử này không dùng chính hàm FFT làm oracle và dễ phát hiện lỗi padding hoặc thứ tự butterfly.

### 11.3. Bất biến toán học

- FFT thuận dùng \(e^{-2\pi ijk/N}\); FFT nghịch dùng dấu ngược và chia N.
- FFT của dãy chỉ có a[0] khác 0 phải cho mọi X[k]=a[0].
- FFT của mảng toàn 0 phải có mọi thành phần bằng 0 (trong giới hạn sai số).
- Với dãy thực, phổ có **đối xứng liên hợp** X[N−k]=conjugate(X[k]) cho k=1..N−1; riêng X[0] và X[N/2] (N chẵn) có phần ảo gần 0.
- IFFT(FFT(a)) gần a.
- Độ dài tích chập tuyến tính của hai mảng không rỗng là n+m−1.
- Tích chập đơn vị [1] với B trả B (gần đúng trong float).
- Đổi thứ tự hai đa thức không đổi tích: A×B=B×A.
- Tính phân phối A×(B+C)=A×B+A×C khi các mảng được diễn giải cùng kích thước, trong phạm vi sai số.

## 12. So sánh với NTT và phương pháp khác

**FFT số phức:** làm việc trên double/Complex, linh hoạt với hệ số thực; nhanh nhưng có sai số làm tròn.

**NTT (Number Theoretic Transform):** làm việc trong một trường hữu hạn với môđun nguyên tố thích hợp, căn đơn vị nguyên thủy và phép nghịch đảo modulo đúng điều kiện. Tính toán được thực hiện **chính xác theo modulo** nếu mọi phép nhân/modulo không overflow và lựa chọn N hợp lệ.

Không phải cứ thay i bằng một số nguyên hay đổi phép cộng phức thành cộng modulo là NTT sẽ đúng. Cần kiểm tra các giả thiết:
- p là số nguyên tố.
- N có căn đơn vị nguyên thủy modulo p, thường N chia hết p−1.
- N khả nghịch modulo p để chuẩn hóa biến đổi nghịch.
- Mọi phép toán modulo p được thực hiện an toàn trên kiểu số.

Với đầu ra cần số nguyên chính xác không modulo, có thể dùng nhiều môđun NTT rồi CRT, nếu tích các môđun đủ bao phủ miền giá trị và xử lý đúng hệ số âm.

**Nhân trực tiếp O(nm):** vẫn hữu ích khi đa thức ngắn, khi cần oracle kiểm thử, hoặc khi phải dùng BigInteger và không muốn đối mặt với sai số FFT.

**FFT iterative in-place:** thường giảm cấp phát và cache miss nhưng cần xử lý hoán vị **bit reversal** hoặc biến thể decimation-in-frequency cẩn thận. Bản đệ quy chẵn–lẻ phù hợp để hiểu công thức trước khi tối ưu.

## 13. Những lỗi phổ biến

1. **Tách nửa đầu/nửa sau thay vì chỉ số chẵn/lẻ** nhưng vẫn áp dụng butterfly Cooley–Tukey radix-2.
2. **Dùng N không phải lũy thừa 2** với cài đặt chỉ hỗ trợ radix-2.
3. **Không có base case N=1**, đệ quy không kết thúc.
4. **Gán nhầm thứ tự X[k] và X[k+N/2]** khi ghép hai nửa.
5. **Quên dấu trừ ở nhánh thứ hai** của butterfly.
6. **Dùng \(\omega_N^{k+N/2}\) như \(\omega_N^k\)**, quên tính chất dấu âm.
7. **Dùng dấu góc nghịch cho FFT thuận** hoặc dấu góc thuận cho IFFT.
8. **Không chia N trong IFFT**, nhận N lần hệ số thật.
9. **Chia N ở nhiều chỗ không nhất quán**, gây co hệ số quá mức.
10. **Nhân phổ bằng phép cộng hoặc nhân chéo chỉ số**, thay vì nhân điểm cùng k.
11. **Đệm N<n+m−1**, biến tích chập tuyến tính thành tích chập vòng bị aliasing.
12. **Quên cắt kết quả IFFT về n+m−1**, trả nhiều hệ số 0 đệm dư.
13. **Cắt luôn những trailing zeros quan trọng theo hợp đồng mảng đầu vào**.
14. **Dùng vòng nhân trực tiếp nhưng khẳng định O(N log N)**; thuật toán phải thật sự dùng butterfly và đệ quy nửa kích thước.
15. **Đặt root góc −2π/N nhưng tăng w sai**, làm các twiddle factors lệch.
16. **Dùng Math.round cho mọi đầu ra FFT và tuyên bố chính xác tuyệt đối**, sai khi hệ số lớn.
17. **So double bằng == khi kiểm thử**, tạo false failure vì sai số dấu phẩy động.
18. **Không kiểm tra phần ảo nhỏ sau IFFT của đầu vào thực**, có thể che dữ liệu/hành vi bất thường.
19. **Không xử lý mảng rỗng**, vô tình gọi FFT N=0.
20. **Không xử lý N=1**, bỏ trường hợp nhân hai đa thức hằng.
21. **Không tính overflow khi chọn N tiếp theo**, khiến chiều dài âm hoặc cấp phát sai.
22. **Dùng số lớn trong long rồi ép double** mà không nhận ra mất độ chính xác.
23. **Nhầm DFT là cùng một biểu thức với FFT nhưng có tính chất exact khác**, dù FFT chỉ là thuật toán tính DFT.
24. **Đánh đồng FFT phức với NTT**, không kiểm tra điều kiện trường hữu hạn/căn nguyên thủy.
25. **Bỏ chi phí cấp phát và cache** của recursive FFT khi đánh giá ứng dụng thực tế.
26. **Chỉ kiểm thử một đa thức đối xứng**, bỏ sót lỗi dấu pha, thứ tự hoặc butterfly khi input bất đối xứng.
27. **Gọi kết quả vòng của N=3 là FFT radix-2 N=3**, trong khi mã không hỗ trợ độ dài này.
28. **Dùng stdout làm tròn để chứng minh độ chính xác nguyên lớn**, dù đó chỉ là minh họa đẹp cho dữ liệu nhỏ.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** DFT thuận của dãy N phần tử là gì?

**Đáp án:** X[k]=∑a[j]e^(−2πijk/N), với j=0..N−1.

**Câu 2.** FFT có tính một phép biến đổi khác DFT không?

**Đáp án:** Không. FFT là cách tính chính DFT nhanh hơn, dựa trên cấu trúc căn đơn vị.

**Câu 3.** Vì sao chia chẵn–lẻ đúng?

**Đáp án:** A(x)=A_even(x²)+xA_odd(x²); ω_N^(2k)=ω_(N/2)^k.

**Câu 4.** Hai công thức butterfly là gì?

**Đáp án:** t=ω_N^kO[k], X[k]=E[k]+t và X[k+N/2]=E[k]−t.

**Câu 5.** FFT bốn điểm của [1,2,3,0] là gì?

**Đáp án:** [6,−2−2i,2,−2+2i] với dấu âm ở DFT thuận.

**Câu 6.** Base case của radix-2 FFT là gì?

**Đáp án:** N=1, trả đúng phần tử đó.

**Câu 7.** Recurrence và độ phức tạp FFT?

**Đáp án:** T(N)=2T(N/2)+O(N), suy ra O(N log N).

**Câu 8.** IFFT khác FFT thuận thế nào?

**Đáp án:** Đổi dấu góc sang dương và chia mọi đầu ra cho N đúng một lần.

**Câu 9.** Vì sao cần zero-padding khi nhân đa thức?

**Đáp án:** DFT nhân điểm tạo tích chập vòng; cần N≥n+m−1 để không quấn các hệ số tuyến tính.

**Câu 10.** Hệ số tích của [1,2,3] và [4,5]?

**Đáp án:** [4,13,22,15].

**Câu 11.** Nếu fold kết quả trên vào chu kỳ N=3?

**Đáp án:** [19,13,22] vì hệ số 15 ở bậc 3 gập về bậc 0.

**Câu 12.** Có thể dùng FFT N=3 với code đệ quy radix-2 này không?

**Đáp án:** Không. Cần một FFT thuật toán khác cho N=3 hoặc zero-pad lên N=4 khi xử lý convolution tuyến tính.

**Câu 13.** Có thể làm tròn mọi tích FFT để nhận đáp án số nguyên chính xác không?

**Đáp án:** Không. Chỉ an toàn khi có kiểm soát sai số và miền giá trị; dữ liệu lớn có thể làm tròn sai.

**Câu 14.** NTT khác FFT phức ở điểm nào?

**Đáp án:** NTT tính toán trong modulo nguyên tố phù hợp, có căn đơn vị và nghịch đảo hợp lệ, cho kết quả chính xác theo modulo thay vì sai số double.

**Câu 15.** Khi nào nhân trực tiếp O(nm) vẫn nên dùng?

**Đáp án:** Khi đa thức rất ngắn, cần tính nguyên chính xác, hoặc cần oracle độc lập để kiểm thử FFT.

**Câu 16.** Vì sao trong FFT phức cần đối chiếu cả DFT trực tiếp và IFFT(FFT(a))?

**Đáp án:** DFT trực tiếp kiểm tra quy ước dấu/chỉ số/butterfly; biến đổi vòng về kiểm tra chuẩn hóa và tính nghịch đảo, hai hướng phát hiện những loại lỗi khác nhau.

**Ghi nhớ:** FFT chẵn–lẻ dựa trên \(A(x)=A_\mathrm{even}(x^2)+xA_\mathrm{odd}(x^2)\), ghép kết quả bằng hai nhánh butterfly với căn đơn vị ω_N. FFT thuận dùng dấu âm; IFFT dùng dấu dương và chia N. Khi nhân đa thức, **padding ít nhất n+m−1** để nhận tích chập tuyến tính, đồng thời nhớ **double chỉ cho kết quả gần đúng**, không phải số nguyên chính xác vô điều kiện.
