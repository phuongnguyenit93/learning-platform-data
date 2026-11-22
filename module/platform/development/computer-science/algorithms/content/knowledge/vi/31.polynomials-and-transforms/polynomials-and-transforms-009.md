# Sai số làm tròn và khôi phục hệ số nguyên

**Sai số làm tròn và khôi phục hệ số nguyên** là một vấn đề quan trọng khi dùng **FFT** (*Fast Fourier Transform*) để nhân đa thức có hệ số nguyên. Biến đổi Fourier rời rạc giúp tính tích chập trong `O(N log N)` thay vì phép nhân trực tiếp `O(nm)`, nhưng phép triển khai bằng số thực `double` chỉ cho kết quả **xấp xỉ**. Việc gọi `Math.round` trên các hệ số sau FFT nghịch đảo không tự biến phép tính thành một thuật toán số nguyên chính xác.

Bài thuộc nhóm **Đa thức và biến đổi** trong Computer Science Algorithms. Ta sẽ giải thích vì sao sai số xuất hiện; chứng minh **điều kiện đủ để làm tròn đúng**; phân biệt độ lớn hệ số với độ lớn số trung gian; kiểm soát zero-padding, dấu âm và trường hợp cận số; và học cách dùng **NTT + định lý số dư Trung Hoa (CRT)** để **khôi phục chính xác có chứng nhận trong một miền được giới hạn**. Có chương trình **Java 17 độc lập**, ví dụ phản chứng `2^53+1`, và kiểm thử đối chiếu với nhân BigInteger trực tiếp.

Mục tiêu không phải là “luôn chọn FFT” hoặc “luôn chọn NTT”, mà là **chọn phương án phù hợp với ràng buộc độ chính xác, độ lớn hệ số, kích thước đầu vào và bộ nhớ**.

## 1. Định nghĩa tích chập của hai đa thức

Cho:

\[
A(x)=a_0+a_1x+\cdots+a_{n-1}x^{n-1},
\quad
B(x)=b_0+b_1x+\cdots+b_{m-1}x^{m-1}.
\]

Nếu A và B biểu diễn bằng hai mảng không rỗng độ dài n,m, tích `C=A·B` có `n+m-1` hệ số:

\[
\boxed{c_k=\sum_{\substack{i+j=k\\0\le i<n,\,0\le j<m}}a_i b_j.}
\]

Đây là **tích chập tuyến tính**. Mỗi c_k là tổng của tất cả tích a_i b_j có tổng chỉ số i+j=k; không phải phép nhân phần tử cùng vị trí.

Ví dụ:

~~~text
A = [1, 2, 3]       = 1+2x+3x^2
B = [4, 5]          = 4+5x

c0=1*4             = 4
c1=1*5+2*4         = 13
c2=2*5+3*4         = 22
c3=3*5             = 15

C = [4, 13, 22, 15]
~~~

Phương pháp hai vòng lặp:

~~~text
for i = 0 .. n-1:
    for j = 0 .. m-1:
        c[i+j] += a[i]*b[j]
~~~

Tốn **O(nm)** phép toán và O(n+m) bộ nhớ kết quả. Cần thận trọng vì `long` không an toàn với mọi `long×long` và tổng nhiều tích; oracle trong chương trình dùng **BigInteger** để tính kết quả thật.

**Quy ước API:** một mảng rỗng `[]` biểu diễn đa thức không và tích với mảng rỗng trả `[]`. Khi cả hai mảng không rỗng, kết quả dài đúng `n+m−1`, kể cả khi hệ số cuối bằng 0. Mảng `[0]` vẫn chứa một phần tử khác với biểu diễn mảng rỗng.

## 2. FFT và yêu cầu zero-padding

Một DFT độ dài N cho **tích chập vòng modulo N**. Muốn dùng nó cho tích chập tuyến tính, phải đệm số 0 để không có chỉ số bậc cao quấn về đầu dãy.

Với bản FFT radix-2, chọn lũy thừa hai nhỏ nhất:

\[
\boxed{N=2^{\lceil\log_2(n+m-1)\rceil},\qquad N\ge n+m-1.}
\]

Quy trình:
1. Tạo hai dãy số phức độ dài N; phần thực là hệ số nguyên chuyển sang double, phần ảo bằng 0.
2. Tính FFT thuận của cả hai dãy.
3. Nhân **theo từng tần số**.
4. FFT nghịch đảo và **chia từng giá trị cho N**.
5. Lấy `n+m−1` hệ số đầu, không lấy tất cả N phần tử nếu N lớn hơn chiều dài tích.
6. Nếu hệ số toán học là số nguyên, có thể **thử làm tròn**; nhưng phải xét điều kiện sai số ở phần sau.

Ví dụ A=[1,1], B=[1,1] có tích tuyến tính [1,2,1] (3 hệ số). Nếu chỉ dùng DFT độ dài N=2, tích chập vòng là [2,2]: hệ số c₂ đã quấn về c₀. Với N=4, kết quả đầu ba hệ số đúng về mặt toán học.

**Sai lầm thường gặp:** lấy N=max(n,m), quên chia N sau IFFT, nhầm dấu góc FFT thuận/nghịch, sai bit reversal, và in cả các hệ số padding. Đây là lỗi cài thuật toán, không phải sai số làm tròn nhỏ.

## 3. Những nguồn sai số trong FFT double

### Sai số khi biểu diễn đầu vào

Java `double` là binary64, có 53 bit độ chính xác hữu hiệu của phần trị. Mọi số nguyên từ −2^53 tới +2^53 biểu diễn chính xác, nhưng không phải mọi số lớn hơn đều có thể lưu nguyên vẹn.

\[
2^{53}=9007199254740992.
\]

Số nguyên kế tiếp `9007199254740993` không có biểu diễn double chính xác; chuyển thành double sẽ ra `9007199254740992`. Do đó:

~~~text
A=[9007199254740993], B=[1]
Tích nguyên chính xác:      [9007199254740993]
FFT(double) + Math.round:  [9007199254740992]  <-- SAI
~~~

Đây là **phản ví dụ độ dài một**, không có butterfly hay sin/cos. Sai số có từ **ép kiểu hệ số đầu vào**. Điều quan trọng: kết quả xấp xỉ sau phép tính lại là **một số nguyên chính xác trong double**; nó không thể bị phát hiện chỉ bằng câu hỏi “giá trị sau FFT có sát một số nguyên không?”.

### Sai số ở các butterfly

FFT radix-2 dùng căn bậc đơn vị phức:

\[
\omega=e^{\pm 2\pi i/N},\qquad
u=X[j],\quad v=\omega X[j+N/2],
\]

sau đó gán các phần tử butterfly bằng `u+v` và `u−v`. Các góc `sin`, `cos` và các phép nhân cộng số thực gần như luôn phải làm tròn. Sai số nhỏ của mỗi phép có thể tích lũy qua O(log N) tầng, và độ lớn sai số phụ thuộc biên độ trung gian.

Chẳng hạn, một giá trị toán học đúng bằng 22 có thể thành `21.999999999999996` sau IFFT; lần này làm tròn ra 22 **đúng**. Nhưng điều tương tự không được bảo đảm cho mọi kích thước và mọi dữ liệu.

### Sai số do triệt tiêu

Nếu hệ số âm được cho phép, một hệ số c_k có thể là tổng nhiều tích dương và âm rất lớn, rồi gần triệt tiêu nhau. Tổng toán học `10^{16}+1−10^{16}=1`, nhưng double không thể bảo toàn đồng thời mọi bit thấp quanh 10^16 trong mọi thứ tự cộng.

**Hệ số cuối nhỏ không có nghĩa các tích trung gian nhỏ.** Khi xét nguy cơ sai số, cần đánh giá độ lớn hệ số **đầu vào** và độ lớn tổng tích, không chỉ xem độ lớn của kết quả.

### Phần ảo dư không chứng nhận phần thực đúng

Với hệ số thực, phần ảo sau IFFT lý tưởng là 0, nhưng tính toán có thể tạo phần dư gần 0. Một phần ảo nhỏ là **tín hiệu chẩn đoán** tốt khi debug, không phải bằng chứng rằng phần thực đã đúng tới 0,5 đơn vị.

Trong phản ví dụ 2^53+1, phần ảo bằng 0 nhưng phần thực vẫn sai một đơn vị so với kết quả nguyên thật.

## 4. Điều kiện đủ để làm tròn đúng

Gọi `c_k` là hệ số nguyên toán học đúng, `y_k` là giá trị xấp xỉ thực do thuật toán tính.

Nếu đã có **bảo đảm**:

\[
\boxed{|y_k-c_k|<\frac12}
\]

thì **số nguyên gần y_k nhất duy nhất là c_k**. Do đó làm tròn y_k về số nguyên gần nhất sẽ cho đúng hệ số c_k. Muốn khôi phục cả đa thức, điều kiện này phải đúng **với mọi k** và hệ số phải nằm trong miền có thể biểu diễn bởi kiểu đầu ra.

Phân biệt ba điều:
- **Có chứng minh sai số tuyệt đối dưới 0,5:** làm tròn đúng.
- **Chỉ nhìn thấy y_k cách một số nguyên nào đó dưới 0,5:** chưa biết số nguyên ấy có là c_k hay không.
- **Chỉ thấy phần ảo gần 0:** không bảo đảm giá trị thực là hệ số đúng.

Trong Java, `Math.round(double)` trả `long`. Nếu đầu vào NaN, vô cực hoặc nằm ngoài miền `long`, Java có quy tắc chuyển đổi/bão hòa riêng; không thể xem nó là bộ chuyển đổi số nguyên lớn chính xác. Với các đầu vào gần nửa nguyên, cách làm tròn tại trường hợp hòa cũng cần được xác định; điều kiện **bất đẳng thức nghiêm `<0.5`** tránh sự mơ hồ đó.

### Độ lớn dưới 2^53 chưa đủ tự chứng minh FFT exact

Ngay khi **mọi hệ số đầu vào** biểu diễn chính xác dưới double, kết quả các phép nhân phức, cos/sin, cộng và trừ vẫn bị làm tròn. Vì thế “hệ số nhỏ hơn 2^53” không phải một **định lý tổng quát** bảo đảm FFT khôi phục đúng. Cần cận sai số cho **toàn bộ phép biến đổi** hoặc một phương án kiểm tra nguyên chính xác.

Tương tự, chia hệ số thành phần cao/thấp giúp giảm nguy cơ nhưng từng phép tích chập số thực vẫn cần ràng buộc sai số, và việc tổ hợp các phần phải dùng phép cộng/nhân nguyên đủ rộng.

## 5. Cận độ lớn hệ số tích chập

Đặt:

\[
A_{\max}=\max_i|a_i|,\qquad B_{\max}=\max_j|b_j|.
\]

Mỗi hệ số c_k là tổng nhiều nhất `min(n,m)` tích, nên:

\[
\boxed{|c_k|\le H=\min(n,m)\,A_{\max}B_{\max}.}
\]

Đây là **cận đủ và bảo thủ**, áp dụng cả khi hệ số âm. Nếu các số dương/âm triệt tiêu, hệ số thực tế có thể nhỏ hơn H, nhưng không được tự lấy hiệu ứng triệt tiêu làm bảo đảm khi chưa biết kết quả thật.

Ví dụ A dài 4, `A_max=100`; B dài 7, `B_max=50` thì `H=4×100×50=20000`. Nếu nhân theo cơ số rất lớn, H có thể vượt 64-bit dù từng hệ số nằm trong long.

**Tính H bằng BigInteger** để tránh tràn ở biểu thức `min(n,m)×A_max×B_max`. Đặc biệt `Math.abs(Long.MIN_VALUE)` trả về giá trị âm vì `2^63` không nằm trong signed long dương. Trong Java, `BigInteger.valueOf(value).abs()` xử lý an toàn.

H giúp ta:
1. Nhận diện trường hợp hệ số có thể quá lớn để làm tròn double đáng tin.
2. Chứng minh **sự duy nhất của hệ số nguyên** từ các phần dư modulo của NTT, nếu tích các mô-đun đủ lớn.
3. Chọn số prime hoặc số chữ số cần tách khi muốn exact integer multiplication.

## 6. NTT thay FFT thực bằng số học nguyên modulo

**NTT (Number Theoretic Transform)** có cấu trúc butterfly tương tự FFT nhưng dùng số nguyên modulo số nguyên tố p. Thay vì cos/sin gần đúng, ta dùng phần tử căn bậc đơn vị `\omega` có **bậc đúng N** modulo p.

Điều kiện cần cho NTT radix-2 độ dài N là `N | (p−1)` với p nguyên tố; chọn primitive root g của p và `\omega=g^{(p-1)/N} mod p`. Phép biến đổi nghịch dùng `\omega^{-1}` và nhân với `N^{-1} mod p`.

Nếu phép toán modulo được triển khai **không tràn**, NTT thuận → nhân từng phần tử → NTT nghịch cho **đúng hệ số tích chập modulo p**:

\[
\boxed{\mathrm{NTTConv}_p(A,B)[k]\equiv c_k\pmod p.}
\]

Không có số thực nên **không có sai số làm tròn**. Tuy nhiên, một residue modulo p **không phải tự động là hệ số nguyên thật**. Ví dụ với p=7, ba số `1,8,−6` đều cho residue 1.

Nếu đề chỉ yêu cầu tích chập **modulo 998244353**, một NTT với prime này là đủ. Nếu đề muốn hệ số **nguyên có dấu** của tích đa thức, phải có **cận độ lớn** và khôi phục từ đủ mô-đun.

## 7. Hai mô-đun NTT và định lý số dư Trung Hoa

Chương trình Java dùng:

\[
p_1=998244353,\quad p_2=1004535809.
\]

Cả hai có **primitive root 3**. Đối với radix-2:
- p1 hỗ trợ N tối đa `2^{23}`;
- p2 hỗ trợ N tối đa `2^{21}`.

Vì dùng cả hai cùng độ dài, chương trình đặt **MAX_SIZE = 2^21**. Dùng N lớn hơn giới hạn này với cùng hai prime sẽ vi phạm điều kiện NTT.

Tích mô-đun:

\[
\boxed{M=p_1p_2=1002772198720536577.}
\]

Hai prime khác nhau nên nguyên tố cùng nhau. Sau NTT, với mỗi hệ số c, ta biết chính xác:

\[
r_1=c\bmod p_1,\quad r_2=c\bmod p_2.
\]

CRT cho giá trị duy nhất `x∈[0,M)` khớp cả hai residue:

\[
t=((r_2-r_1)p_1^{-1})\bmod p_2,
\quad
\boxed{x=r_1+p_1 t}.
\]

Với bộ prime này:

~~~text
M = 1002772198720536577
p1^(-1) mod p2 = 669690699
~~~

Nếu muốn số nguyên có dấu, chuyển về đại diện đối xứng:

\[
\boxed{c=
\begin{cases}
x-M & x>M/2,\\
x & x\le M/2.
\end{cases}}
\]

### Bảo đảm khôi phục: 2H < M

Nếu cận toàn đa thức thỏa:

\[
\boxed{2H<M},
\]

thì mọi hệ số thật nằm trong khoảng `[-H,H]` hẹp hơn một chu kỳ M. Hai số nguyên khác nhau trong khoảng này không thể đồng dư modulo M (hiệu khác 0 có trị tuyệt đối nhỏ hơn M). Do đó hai residue xác định **duy nhất hệ số nguyên thật**.

**Đây là lý do bản exactCRT có tên “exact” trong miền đã kiểm tra**, không phải vì nó làm tròn gần một số nguyên.

Với M khoảng 1.00277×10^18, miền có dấu an toàn do cận đủ là khoảng `±5.01386×10^{17}`. Số `2^53+1≈9×10^{15}` **nằm trong miền** này nên NTT+CRT khôi phục chính xác, dù double đã mất một bit.

### Bộ kiểm tra cận cố ý từ chối một số bài toán có thể giải được

Chương trình kiểm tra `2×min(n,m)×max|a|×max|b|<M`. Nếu điều kiện thất bại, hàm ném `CRT_BOUND_EXCEEDED` và **không trả một hệ số có nguy cơ bị quấn**.

Cận H bảo thủ: có trường hợp các hệ số thật vẫn nhỏ nhờ triệt tiêu nhưng H quá lớn. Bản bài học vẫn **từ chối** do chưa có chứng minh an toàn; có thể dùng nhiều prime, thuật toán BigInteger trực tiếp cho đa thức nhỏ, hoặc tách hệ số nếu cần hỗ trợ.

### Vì sao phép nhân long trong bản NTT cụ thể này an toàn?

Mỗi residue trong `[0,p−1]`. Với p lớn nhất khoảng 1.005×10^9, tích hai residue dưới khoảng **1.01×10^18**, nhỏ hơn Long.MAX_VALUE≈9.22×10^18. Vì vậy phép nhân `long×long` trước mod không tràn đối với **đúng hai prime trên**.

Tương tự, phép nhân `(r2−r1)×inv` trong CRT và `p1×t+r1` đều dưới khoảng 1.01×10^18. Nếu thay prime, không được giữ nguyên kết luận an toàn; cần chứng minh lại cận hoặc dùng mulMod/BigInteger.

### Nếu muốn hệ số vượt M/2

Các lựa chọn:
- Dùng **thêm một hoặc nhiều prime NTT** và CRT với BigInteger, đồng thời kiểm tra **tất cả prime cùng hỗ trợ N**.
- **Coefficient splitting:** biểu diễn hệ số bằng các chữ số nhỏ, thực hiện nhiều tích chập rồi tổ hợp bằng số nguyên rộng.
- Dùng **naive BigInteger** nếu đa thức ngắn.
- Nếu yêu cầu chỉ modulo một prime, không cần CRT khôi phục số có dấu.

Không được lấy kết quả CRT đã quấn rồi gọi là “hệ số đúng” khi không có bound.

## 8. Ví dụ hệ số âm và lỗi bỏ bước đổi dấu

Với:

~~~text
A = [-2, 3, -1]
B = [4, -5, 2]
~~~

Ta tính:

~~~text
c0 = (-2)*4                    = -8
c1 = (-2)*(-5) + 3*4           = 22
c2 = (-2)*2 + 3*(-5) + (-1)*4  = -23
c3 = 3*2 + (-1)*(-5)           = 11
c4 = (-1)*2                   = -2

C = [-8, 22, -23, 11, -2]
~~~

Trong NTT, một hệ số âm như `−8` được biểu diễn bởi phần dư `p−8`. CRT tìm đại diện `x=M−8` trong `[0,M)`. Sau khi so với M/2, phải trừ M để khôi phục `−8`. Nếu bỏ bước này, sẽ nhận một số dương gần 10^18 **sai hoàn toàn** dù cả hai biến đổi NTT đều đúng modulo prime.

## 9. Chương trình Java 17 độc lập

Chương trình sau minh họa **đồng thời**:
- `naiveBig`: tích chập chính xác bằng BigInteger, dùng làm oracle.
- `fftRounded`: FFT số phức double rồi `Math.round`, **không có bảo đảm exact**.
- `ntt`: biến đổi nguyên modulo p với bit-reversal và butterfly.
- `exactCRT`: hai NTT, CRT, kiểm tra `2H<M` bằng BigInteger, khôi phục hệ số âm.
- `verify`: 14.641 cặp đa thức nhỏ vét cạn và 3.000 cặp xác định có hệ số lớn, đối chiếu **từng hệ số** với BigInteger.

Định nghĩa output rõ ràng: mảng rỗng nhân với mọi mảng → `[]`; hai mảng không rỗng → mảng độ dài n+m−1. Hàm exactCRT chỉ chấp nhận NTT size không vượt `2^21` và bound đủ nhỏ.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class PolynomialRoundingRecoveryDemo {
    static final long P1 = 998244353L;
    static final long P2 = 1004535809L;
    static final long ROOT = 3L;
    static final long M = P1 * P2;
    static final int MAX_SIZE = 1 << 21;
    static final long INV_P1_MOD_P2 = modPow(P1, P2 - 2, P2);

    // Oracle exact: moi phep nhan va cong dung BigInteger.
    static BigInteger[] naiveBig(long[] a, long[] b) {
        if (a.length == 0 || b.length == 0)
            return new BigInteger[0];

        BigInteger[] c =
                new BigInteger[a.length + b.length - 1];
        Arrays.fill(c, BigInteger.ZERO);
        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < b.length; j++) {
                c[i + j] = c[i + j].add(
                        BigInteger.valueOf(a[i])
                                .multiply(BigInteger.valueOf(b[j])));
            }
        }
        return c;
    }

    // FFT radix-2 voi real/imag; KHONG bao dam exact.
    static void fft(double[] re, double[] im, boolean inv) {
        int n = re.length;
        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >> 1;
            while ((j & bit) != 0) {
                j ^= bit;
                bit >>= 1;
            }
            j ^= bit;
            if (i < j) {
                double t = re[i];
                re[i] = re[j];
                re[j] = t;
                t = im[i];
                im[i] = im[j];
                im[j] = t;
            }
        }

        for (int len = 2; len <= n; len <<= 1) {
            double angle = (inv ? 2.0 : -2.0)
                    * Math.PI / len;
            double stepRe = Math.cos(angle);
            double stepIm = Math.sin(angle);

            for (int start = 0; start < n; start += len) {
                double wr = 1.0, wi = 0.0;
                for (int j = 0; j < len / 2; j++) {
                    int u = start + j, v = u + len / 2;
                    double vr = re[v] * wr - im[v] * wi;
                    double vi = re[v] * wi + im[v] * wr;
                    double ur = re[u], ui = im[u];

                    re[u] = ur + vr;
                    im[u] = ui + vi;
                    re[v] = ur - vr;
                    im[v] = ui - vi;

                    double nextWr = wr * stepRe - wi * stepIm;
                    wi = wr * stepIm + wi * stepRe;
                    wr = nextWr;
                }
            }
        }
        if (inv) {
            for (int i = 0; i < n; i++) {
                re[i] /= n;
                im[i] /= n;
            }
        }
    }

    static long[] fftRounded(long[] a, long[] b) {
        if (a.length == 0 || b.length == 0)
            return new long[0];

        long needLong = (long) a.length + b.length - 1L;
        if (needLong > Integer.MAX_VALUE)
            throw new IllegalArgumentException("Too many terms");
        int needed = (int) needLong;
        int n = 1;
        while (n < needed) {
            if (n > (1 << 29))
                throw new IllegalArgumentException("FFT too large");
            n <<= 1;
        }

        double[] ar = new double[n], ai = new double[n];
        double[] br = new double[n], bi = new double[n];
        for (int i = 0; i < a.length; i++)
            ar[i] = (double) a[i];
        for (int i = 0; i < b.length; i++)
            br[i] = (double) b[i];

        fft(ar, ai, false);
        fft(br, bi, false);
        for (int i = 0; i < n; i++) {
            double r = ar[i] * br[i] - ai[i] * bi[i];
            double imag = ar[i] * bi[i] + ai[i] * br[i];
            ar[i] = r;
            ai[i] = imag;
        }
        fft(ar, ai, true);

        long[] result = new long[needed];
        for (int i = 0; i < needed; i++)
            result[i] = Math.round(ar[i]);
        return result;
    }

    // NTT modular, cac mod <1.01e9 nen long*long an toan.
    static long modPow(long a, long e, long mod) {
        long result = 1L;
        long x = a % mod;
        while (e > 0L) {
            if ((e & 1L) != 0L)
                result = result * x % mod;
            x = x * x % mod;
            e >>>= 1;
        }
        return result;
    }

    static long normalize(long value, long mod) {
        long r = value % mod;
        return r < 0L ? r + mod : r;
    }

    static void ntt(long[] a, boolean inverse, long mod) {
        int n = a.length;
        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >> 1;
            while ((j & bit) != 0) {
                j ^= bit;
                bit >>= 1;
            }
            j ^= bit;
            if (i < j) {
                long temp = a[i];
                a[i] = a[j];
                a[j] = temp;
            }
        }

        for (int len = 2; len <= n; len <<= 1) {
            long root = modPow(
                    ROOT, (mod - 1L) / len, mod);
            if (inverse)
                root = modPow(root, mod - 2L, mod);

            for (int start = 0; start < n; start += len) {
                long w = 1L;
                for (int j = 0; j < len / 2; j++) {
                    long u = a[start + j];
                    long v = a[start + j + len / 2]
                            * w % mod;
                    a[start + j] = (u + v) % mod;
                    a[start + j + len / 2] =
                            (u - v + mod) % mod;
                    w = w * root % mod;
                }
            }
        }

        if (inverse) {
            long inverseN = modPow(n, mod - 2L, mod);
            for (int i = 0; i < n; i++)
                a[i] = a[i] * inverseN % mod;
        }
    }

    static long[] convolutionMod(
            long[] a, long[] b, int n,
            int needed, long mod) {
        long[] x = new long[n], y = new long[n];
        for (int i = 0; i < a.length; i++)
            x[i] = normalize(a[i], mod);
        for (int i = 0; i < b.length; i++)
            y[i] = normalize(b[i], mod);

        ntt(x, false, mod);
        ntt(y, false, mod);
        for (int i = 0; i < n; i++)
            x[i] = x[i] * y[i] % mod;
        ntt(x, true, mod);
        return Arrays.copyOf(x, needed);
    }

    static BigInteger maxAbs(long[] a) {
        BigInteger best = BigInteger.ZERO;
        for (long x : a) {
            BigInteger candidate =
                    BigInteger.valueOf(x).abs();
            if (candidate.compareTo(best) > 0)
                best = candidate;
        }
        return best;
    }

    // Exact trong mien duoc chung nhan boi 2H<M.
    static long[] exactCRT(long[] a, long[] b) {
        if (a.length == 0 || b.length == 0)
            return new long[0];

        long requested = (long) a.length + b.length - 1L;
        if (requested > MAX_SIZE)
            throw new IllegalArgumentException(
                    "NTT_SIZE_EXCEEDED");

        BigInteger bound = BigInteger.valueOf(
                Math.min(a.length, b.length))
                .multiply(maxAbs(a))
                .multiply(maxAbs(b));
        if (bound.shiftLeft(1).compareTo(
                BigInteger.valueOf(M)) >= 0)
            throw new IllegalArgumentException(
                    "CRT_BOUND_EXCEEDED");

        int needed = (int) requested;
        int n = 1;
        while (n < needed) n <<= 1;

        long[] r1 = convolutionMod(a, b, n, needed, P1);
        long[] r2 = convolutionMod(a, b, n, needed, P2);
        long[] out = new long[needed];

        for (int i = 0; i < needed; i++) {
            long diff = (r2[i] - r1[i]) % P2;
            if (diff < 0L) diff += P2;
            long t = diff * INV_P1_MOD_P2 % P2;
            long x = r1[i] + P1 * t; // 0<=x<M
            out[i] = x > M / 2L ? x - M : x;
        }
        return out;
    }

    // So tung he so voi BigInteger, KHONG dung epsilon.
    static void checkPair(long[] a, long[] b,
                          boolean checkSmallFFT) {
        BigInteger[] expected = naiveBig(a, b);
        long[] actual = exactCRT(a, b);
        if (expected.length != actual.length)
            throw new AssertionError("Wrong output length");

        for (int i = 0; i < actual.length; i++) {
            if (!expected[i].equals(
                    BigInteger.valueOf(actual[i])))
                throw new AssertionError(
                        "Mismatch at coefficient " + i);
        }
        if (checkSmallFFT && !Arrays.equals(
                fftRounded(a, b), actual))
            throw new AssertionError("Small FFT mismatch");
    }

    // Tat ca day do dai 0..4 tren {-1,0,1}: 121 day.
    static List<long[]> smallPolynomials() {
        List<long[]> all = new ArrayList<>();
        List<long[]> layer = new ArrayList<>();
        all.add(new long[0]);
        layer.add(new long[0]);

        for (int length = 1; length <= 4; length++) {
            List<long[]> next = new ArrayList<>();
            for (long[] prefix : layer) {
                for (long x : new long[]{-1, 0, 1}) {
                    long[] cur = Arrays.copyOf(
                            prefix, prefix.length + 1);
                    cur[cur.length - 1] = x;
                    next.add(cur);
                }
            }
            all.addAll(next);
            layer = next;
        }
        return all;
    }

    static int seed = 4152026;
    static int randomInt(int bound) {
        seed = seed * 1664525 + 1013904223;
        return (int) (
                Integer.toUnsignedLong(seed) % bound);
    }

    record Stats(int exhaustive, int random, int total) {}

    static Stats verify() {
        List<long[]> list = smallPolynomials();
        if (list.size() != 121)
            throw new AssertionError("Wrong enumeration");

        int exhaustive = 0;
        for (long[] a : list) {
            for (long[] b : list) {
                checkPair(a, b, true);
                exhaustive++;
            }
        }

        int random = 0;
        for (int test = 0; test < 3000; test++) {
            int na = randomInt(11), nb = randomInt(11);
            long[] a = new long[na], b = new long[nb];
            boolean high = test % 3 == 0;
            int range = high ? 100_000_000 : 20_001;
            long shift = high ? 50_000_000L : 10_000L;

            for (int i = 0; i < na; i++)
                a[i] = randomInt(range) - shift;
            for (int i = 0; i < nb; i++)
                b[i] = randomInt(range) - shift;

            checkPair(a, b, false);
            random++;
        }

        if (exhaustive != 14641 || random != 3000)
            throw new AssertionError("Wrong test count");
        return new Stats(exhaustive, random,
                         exhaustive + random);
    }

    public static void main(String[] args) {
        long[] a = {1, 2, 3};
        long[] b = {4, 5};

        System.out.println("simple.naive="
                + Arrays.toString(naiveBig(a, b)));
        System.out.println("simple.fftRounded="
                + Arrays.toString(fftRounded(a, b)));
        System.out.println("simple.exactCRT="
                + Arrays.toString(exactCRT(a, b)));

        long[] signedA = {-2, 3, -1};
        long[] signedB = {4, -5, 2};
        System.out.println("signed.fftRounded="
                + Arrays.toString(
                    fftRounded(signedA, signedB)));
        System.out.println("signed.exactCRT="
                + Arrays.toString(
                    exactCRT(signedA, signedB)));
        System.out.println("empty.exactCRT="
                + Arrays.toString(
                    exactCRT(new long[0], b)));

        long[] precision = {9_007_199_254_740_993L};
        long[] one = {1};
        System.out.println("precision.fftRounded="
                + Arrays.toString(
                    fftRounded(precision, one)));
        System.out.println("precision.exactCRT="
                + Arrays.toString(
                    exactCRT(precision, one)));

        try {
            exactCRT(new long[]{1_000_000_000L},
                     new long[]{1_000_000_000L});
            throw new AssertionError(
                    "Expected bound rejection");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "boundGuard=" + ex.getMessage());
        }

        System.out.println("moduli=[" + P1 + ", " + P2 + "]");
        System.out.println("modulusProduct=" + M);

        Stats stats = verify();
        System.out.println(
                "testedSmall=" + stats.exhaustive());
        System.out.println(
                "testedRandom=" + stats.random());
        System.out.println(
                "testedTotal=" + stats.total());
    }
}
~~~

Lưu mã thành **PolynomialRoundingRecoveryDemo.java**, chạy bằng **JDK 17 trở lên**:

~~~bash
javac PolynomialRoundingRecoveryDemo.java
java PolynomialRoundingRecoveryDemo
~~~

**Đầu ra dự kiến:**

~~~text
simple.naive=[4, 13, 22, 15]
simple.fftRounded=[4, 13, 22, 15]
simple.exactCRT=[4, 13, 22, 15]
signed.fftRounded=[-8, 22, -23, 11, -2]
signed.exactCRT=[-8, 22, -23, 11, -2]
empty.exactCRT=[]
precision.fftRounded=[9007199254740992]
precision.exactCRT=[9007199254740993]
boundGuard=CRT_BOUND_EXCEEDED
moduli=[998244353, 1004535809]
modulusProduct=1002772198720536577
testedSmall=14641
testedRandom=3000
testedTotal=17641
~~~

**Cách hiểu các dòng quan trọng:**
- Các mẫu hệ số nhỏ có kết quả FFT làm tròn trùng với exactCRT, **không** suy ra FFT luôn đúng.
- `precision.fftRounded` sai một đơn vị vì **double không biểu diễn được 2^53+1**. Ở N=1, sai số không thể quy cho butterfly.
- `precision.exactCRT` đúng vì hệ số thật nằm trong miền CRT cho phép.
- `boundGuard` biểu thị chương trình chủ động **từ chối một phép khôi phục chưa được chứng minh**, không trả hệ số đã quấn modulo.
- `modulusProduct` là M đã được chứng minh nằm trong signed long; bản code không hỗ trợ tự động hệ số lớn hơn khoảng khôi phục hai prime.
- Dòng thống kê là số ca kiểm thử, **không phải benchmark tốc độ**.

### Một số lưu ý về code

**1. Không bỏ qua điều kiện 2H<M.** Nếu một hệ số thật là M+5, hai phần dư giống hệt hệ số 5. CRT không thể biết hệ số thật là 5 hay M+5 chỉ từ hai residue. Cận là điều kiện giải quyết chính sự nhập nhằng này.

**2. Long.MIN_VALUE.** Cận BigInteger dùng `BigInteger.valueOf(x).abs()`, tránh sai số âm do `Math.abs(Long.MIN_VALUE)`.

**3. Input rỗng.** Nếu một mảng rỗng, hàm trả `[]` và không cố chạy NTT độ dài 0. Nếu hai mảng có mỗi bên một phần tử, N=1 và các vòng butterfly không chạy, phép nhân và CRT vẫn đúng.

**4. Giới hạn NTT.** Code kiểm tra số hệ số cần không vượt 2^21; N được chọn là lũy thừa 2 nhỏ nhất, nên N cũng không vượt 2^21. Nếu cần N lớn hơn, phải thay prime hoặc cấu trúc biến đổi; không vượt giới hạn một cách tùy tiện.

**5. Chi phí phép nhân.** Với hai prime đã chọn, tích các residue `<1.01×10^{18}` nên phép nhân long trong NTT an toàn. Nếu thay prime gần giới hạn int, cần kiểm tra lại cận trước khi dùng mã nguyên xi.

## 10. Kiểm thử có oracle độc lập

Bộ kiểm thử tạo **mọi đa thức độ dài 0..4** có hệ số thuộc `{-1,0,1}`:

\[
1+3+9+27+81=121\text{ mảng}.
\]

Mọi cặp mảng theo thứ tự (A,B) là:

\[
\boxed{121^2=14641\text{ cặp}.}
\]

Từng cặp được tính bằng **naiveBig**, bằng **exactCRT** và, đối với nhóm nhỏ, bằng **fftRounded**. `checkPair` so **toàn bộ số hệ số** và **từng giá trị đúng tuyệt đối**, không dùng một epsilon để ngầm chấp nhận sai số.

Thêm **3.000 cặp được tạo xác định** bằng PRNG 32-bit với seed cố định, gồm:
- Mảng độ dài từ 0 đến 10.
- Hệ số âm/dương trong khoảng xấp xỉ ±10.000.
- Một phần hệ số lớn hơn, trong khoảng xấp xỉ ±50.000.000; tích chập vẫn trong bound hai prime khi độ dài nhỏ.

Nhóm ngẫu nhiên **không** bắt buộc fftRounded trùng với exactCRT, vì chính mục tiêu bài là chứng minh có những vùng double không đáng tin cậy. Nhóm này xác minh **NTT+CRT với cận** bằng BigInteger.

| Nhóm | Số cặp | Phép đối chiếu |
| --- | ---: | --- |
| Vét cạn 121×121 mảng | 14.641 | BigInteger, exactCRT, FFT nhỏ |
| Sinh xác định gồm hệ số âm và lớn | 3.000 | BigInteger với exactCRT |
| **Tổng** | **17.641** | Từng hệ số đúng nguyên |

Mô hình thuật toán NTT/CRT đã được đối chiếu độc lập trên toàn bộ **17.641 cặp** và không phát hiện sai khác. Ví dụ `2^53+1` chủ động chứng minh FFT double làm tròn **không có bảo đảm tuyệt đối**.

**Đừng tự xem kiểm thử hữu hạn là chứng minh cho mọi input.** Độ đúng trong miền hỗ trợ còn phải dựa vào:
- NTT có root phù hợp với N trên cả hai prime.
- Phép cộng/nhân modulo không bị tràn long.
- CRT tái dựng chính xác hai residue.
- `2H<M` bảo đảm hệ số nguyên có dấu được xác định duy nhất.

## 11. Chứng minh tính đúng của khôi phục NTT+CRT

### Mệnh đề A — Không mất bậc do quấn chỉ số

Vì N≥n+m−1, mọi cặp i,j của hệ số gốc thỏa `i+j≤n+m−2<N`. Do đó phép tích chập vòng modulo N **không quấn** một hệ số bậc cao vào bậc thấp. Các hệ số đầu của kết quả NTT chính là kết quả tích chập tuyến tính **modulo p**.

### Mệnh đề B — NTT tạo đúng residue

Với N là lũy thừa của 2 chia hết `p−1` theo điều kiện `N|(p−1)`, chọn root bậc N. Phép biến đổi thuận và nghịch là ánh xạ tuyến tính khả nghịch modulo p. Nhân từng giá trị biến đổi tương ứng với tích chập vòng. Vì mã dùng số học nguyên modular exact, NTT trả `r_i=c_k mod p_i`.

### Mệnh đề C — CRT tạo đại diện duy nhất modulo M

Vì p1,p2 nguyên tố khác nhau, chúng nguyên tố cùng nhau. Với mọi cặp residue, CRT cung cấp duy nhất x trong [0,M) thỏa cả hai. Công thức `x=r1+p1×(((r2−r1)×p1^{-1}) mod p2)` xây đúng đại diện đó.

### Mệnh đề D — Khoảng [-H,H] xác định duy nhất c

Mỗi c_k có độ lớn ≤H do bất đẳng thức tam giác. Nếu 2H<M, hai số nguyên khác nhau trong [-H,H] có hiệu khác 0 và trị tuyệt đối <M, không thể đồng dư modulo M. Vậy đại diện đối xứng duy nhất trong miền đó chính là c_k thật.

Ghép bốn mệnh đề: **exactCRT trả hệ số nguyên đúng**, với điều kiện kích thước, modulo, bound và số học đã nêu.

## 12. Độ phức tạp và chọn thuật toán

Đặt L=n+m−1 và N là lũy thừa 2 nhỏ nhất ≥L.

| Cách nhân | Thời gian | Bộ nhớ | Tính đúng |
| --- | --- | --- | --- |
| Naive BigInteger | O(nm) phép nhân/cộng BigInteger | O(L) BigInteger | Chính xác; bit-complexity tùy độ lớn hệ số |
| FFT double + round | O(N log N) thao tác số thực | O(N) double | **Xấp xỉ**, cần bound sai số để khôi phục |
| Một NTT modulo p | O(N log N) phép toán modular | O(N) | Chính xác **mod p** |
| Hai NTT + CRT | O(N log N) + O(L) CRT | O(N) long | Chính xác hệ số có dấu nếu `2H<M` |
| NTT nhiều prime + BigInteger CRT | Phụ thuộc số prime | O(N) cho mỗi biến đổi, thêm CRT | Chính xác khi tổng modulus và điều kiện N phù hợp |

Với n,m nhỏ, naïve có thể nhanh hơn do tránh overhead FFT/NTT. Với n,m lớn và hệ số vừa phải, FFT hoặc NTT mang lợi ích lớn. Với hệ số rất lớn cần chính xác, cân nhắc **nhiều NTT + CRT** hoặc **tách hệ số**; bản hai prime không thể tự hỗ trợ mọi `long[]`.

Đừng tự nhận một phép nhân BigInteger có giá O(1) khi phân tích ở mức bit; độ phức tạp O(nm) ở bảng là số phép toán hệ số, chưa bao gồm chi phí tính với số nguyên nhiều bit.

## 13. Những sai lầm điển hình

| Sai lầm | Hậu quả | Khắc phục |
| --- | --- | --- |
| FFT không padding đến n+m−1 | Tích chập vòng bị aliasing | Dùng next power of two ≥n+m−1 |
| Quên chia N trong IFFT | Hệ số sai tỉ lệ | Chuẩn hóa nghịch đảo |
| Lấy cả N kết quả thay vì n+m−1 | In thêm padding | Cắt theo độ dài tích thật |
| Dùng double cho mọi long không cần kiểm tra | Mất bit ngay từ đầu | Thử 2^53+1, xét exact NTT |
| “Gần số nguyên” ⇒ “đúng” | Có thể gần **số nguyên sai** | Cần cận `|y−c|<0.5` |
| Chỉ xem phần ảo sau IFFT | Không bắt lỗi phần thực | Không dùng làm chứng nhận |
| Phép nhân hệ số long trực tiếp | Có thể tràn trước cộng | BigInteger hoặc modular safe |
| `Math.abs(Long.MIN_VALUE)` khi tính bound | Bound có thể sai dấu | BigInteger.abs |
| NTT với N ngoài giới hạn prime | Không tồn tại root N-th phù hợp | Kiểm tra N≤2^21 |
| Bỏ mod sau butterfly | Giá trị vượt miền | Mọi phép biến đổi modulo p |
| Ghép CRT nhưng quên số âm | Trả M−8 thay vì −8 | Chuyển đại diện đối xứng |
| Bỏ kiểm tra 2H<M | Khôi phục mơ hồ modulo M | Thêm prime, splitting, hoặc từ chối |
| Đổi prime nhưng không kiểm tra long multiply | Overflow modular | Chứng minh cận mới |
| Tin một bài test nhỏ chứng minh mọi FFT | Bỏ lỗi cỡ lớn/triệt tiêu | Chứng minh + oracle độc lập |
| Dùng FFT float làm oracle cho FFT float | Hai cách có thể sai giống nhau | So BigInteger hoặc exact CRT |

## 14. Bài tập tự luyện có đáp án

**Bài 1.** A=[2,1], B=[3,4]. Tích chập?

*Đáp án:* [6,11,4].

**Bài 2.** A dài 5, B dài 4. Radix-2 N tối thiểu?

*Đáp án:* 5+4−1=8, nên N=8.

**Bài 3.** A dài 5, B dài 5. N tối thiểu?

*Đáp án:* Cần 9 hệ số; N=16.

**Bài 4.** Vì sao DFT N=2 cho [1,1]×[1,1] ra [2,2] thay vì [1,2,1]?

*Đáp án:* Hệ số bậc 2 quấn về bậc 0 trong tích chập vòng.

**Bài 5.** Hệ số long nào tạo phản ví dụ đơn giản cho double?

*Đáp án:* 9007199254740993=2^53+1, bị double làm tròn còn 9007199254740992.

**Bài 6.** Biết chắc `|y−c|<0.5` và c nguyên, y=7.49. c?

*Đáp án:* 7; nhờ **cận sai số** đã được chứng minh, không chỉ vì y sát số 7.

**Bài 7.** Giá trị FFT y chính xác bằng 100 có chứng minh c=100 không?

*Đáp án:* Không nếu chưa có bảo đảm sai số/độ chính xác phép tính.

**Bài 8.** A dài 4, max|a|=100; B dài 7, max|b|=50. H?

*Đáp án:* 4×100×50=20.000.

**Bài 9.** CRT trả x=M−8, biết hệ số thật trong khoảng có dấu. c?

*Đáp án:* c=x−M=−8.

**Bài 10.** Vì sao dùng hai mô-đun chưa đủ để phục hồi mọi hệ số nguyên vô hạn?

*Đáp án:* Cặp residue chỉ xác định một lớp đồng dư modulo M; cần bound hoặc thêm modulus.

**Bài 11.** Điều kiện `2H<M` nói gì?

*Đáp án:* Các hệ số trong [-H,H] được xác định duy nhất bởi phần dư modulo M.

**Bài 12.** Vì sao prime NTT phải hỗ trợ N?

*Đáp án:* Cần phần tử có bậc N; với prime p phải có N chia p−1.

**Bài 13.** Hai prime bài hỗ trợ N tối đa chung bao nhiêu?

*Đáp án:* 2^21, do p2 hỗ trợ không quá 2^21.

**Bài 14.** Nếu đổi p2 thành prime rất lớn, long modular multiplication có mặc nhiên an toàn?

*Đáp án:* Không; cần xét tích tối đa hai residue trước phép mod.

**Bài 15.** Nếu 2H≥M nhưng hệ số thực có thể nhỏ vì triệt tiêu, exactCRT làm gì?

*Đáp án:* Từ chối vì không có chứng minh miền phục hồi đủ chặt; cần phương án khác.

**Bài 16.** Vì sao oracle dùng BigInteger?

*Đáp án:* Tránh tràn tích/cộng hệ số và có kết quả toán học chính xác.

**Bài 17.** Sau NTT, residue của hệ số −2 là gì?

*Đáp án:* p−2 theo modulo p; sau CRT và đổi đại diện có dấu về −2.

**Bài 18.** Độ phức tạp FFT/NTT theo N?

*Đáp án:* O(N log N) cho một biến đổi radix-2.

**Bài 19.** Hệ số c nhỏ có chứng tỏ các phép trung gian double chính xác?

*Đáp án:* Không; các tích lớn có thể triệt tiêu và làm mất các bit thấp.

**Bài 20.** Nếu cần hệ số cỡ 10^30, bản exactCRT trả long có đủ?

*Đáp án:* Không; cần nhiều prime và CRT BigInteger hoặc phép nhân BigInteger phù hợp.

**Bài 21.** Vì sao so hai kết quả FFT double với nhau chưa đủ chứng minh exact?

*Đáp án:* Hai chương trình có thể mắc cùng kiểu sai số hoặc cùng mất bit đầu vào.

**Bài 22.** Hai mảng có nhiều phần tử nhưng tất cả đều bằng 0; kết quả dài bao nhiêu?

*Đáp án:* n+m−1 phần tử 0, với H=0 nên CRT đủ bound.

## 15. Checklist trước khi nộp bài

1. Xác định phép toán là **tích chập tuyến tính**, không nhầm với convolution vòng.
2. Chọn N là lũy thừa 2 ít nhất bằng n+m−1, kiểm tra giới hạn phép biến đổi.
3. Xác nhận FFT nghịch đảo có nhân `1/N` và lấy đúng số phần tử cần.
4. **Không kết luận exact** chỉ nhờ `Math.round` hoặc phần ảo rất nhỏ.
5. Với FFT double, xác định điều kiện/cận sai số tuyệt đối `<1/2` nếu cần hệ số nguyên đúng.
6. Đánh giá mất precision quanh `2^53` và các case âm/triệt tiêu.
7. Với NTT, kiểm tra prime, primitive root và độ dài N hợp lệ.
8. Tính bound H bằng BigInteger, bao gồm Long.MIN_VALUE.
9. Nếu dùng hai residue để phục hồi số có dấu, chỉ cam kết khi `2H<M`.
10. CRT phải dùng đúng nghịch đảo modulo và đổi đại diện x>M/2 thành x−M.
11. Chứng minh các phép nhân modular dùng long **không tràn với các prime cụ thể**.
12. Khi vượt bound/size, báo lỗi và chọn thuật toán khác; không trả hệ số có thể sai.
13. So với phép nhân BigInteger trực tiếp trên bộ nhỏ/vét cạn và các ca cực trị.
14. Benchmark theo n,m, độ lớn hệ số và giới hạn bộ nhớ; không mặc định FFT luôn nhanh hơn naïve trên đa thức nhỏ.

## Tổng kết

FFT giúp nhân đa thức nhanh, nhưng trong `double` các hệ số nguyên được **khôi phục bằng làm tròn** chỉ đúng khi đã **chứng minh sai số tuyệt đối dưới 1/2** và kết quả nằm trong kiểu đích. Sai số có thể xuất hiện ngay khi ép `2^53+1` sang double, trước bất kỳ butterfly nào; “kết quả rất gần một số nguyên” **không phải chứng chỉ**.

NTT loại bỏ sai số số thực bằng phép toán nguyên modular. Ghép hai prime `998244353` và `1004535809` qua CRT cho `M=1002772198720536577`. Với cận `H=min(n,m)max|a|max|b|` và **2H<M**, công thức CRT khôi phục được **đúng mọi hệ số nguyên có dấu** trong miền cho phép. Bản Java 17 kiểm tra điều kiện trước khi trả kết quả và đã được đối chiếu bằng mô hình độc lập trên **17.641 cặp đa thức**, gồm hệ số âm và dữ liệu cỡ lớn.
