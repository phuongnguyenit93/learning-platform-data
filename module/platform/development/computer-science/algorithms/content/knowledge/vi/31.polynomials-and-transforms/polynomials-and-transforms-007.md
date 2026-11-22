# Chọn độ dài, đệm số không và tránh tích chập vòng ngoài ý muốn

Trong bài toán **nhân đa thức** hoặc **tích chập dãy số**, việc dùng FFT (Fast Fourier Transform) hay NTT (Number Theoretic Transform) không chỉ là viết đúng công thức biến đổi. Một chi tiết tưởng nhỏ — **chọn độ dài biến đổi N và đệm đủ số 0** — quyết định phép nhân theo miền tần số có khôi phục được **tích chập tuyến tính** mong muốn hay không.

**Quy tắc quan trọng nhất:** nếu hai dãy không rỗng có độ dài n và m, tích chập tuyến tính có **n+m−1 hệ số**. Muốn khôi phục toàn bộ tích chập này bằng một DFT/FFT/NTT độ dài N, phải bảo đảm:

**N ≥ n+m−1**.

Với triển khai **radix-2**, N phải là một **lũy thừa của 2** được biến đổi hỗ trợ. Chọn:

**N = 2^ceil(log₂(n+m−1))**,

và **đệm 0 bên phải** cả hai dãy đến đúng N phần tử. Sau biến đổi thuận, nhân điểm từng phần tử, biến đổi ngược, chỉ giữ **n+m−1 hệ số đầu**.

Nếu chọn N **quá ngắn**, phép nhân FFT/NTT không trả tích chập tuyến tính mà là **tích chập vòng (circular convolution)**: các hệ số bậc cao **cuộn lại (wrap around)** và cộng vào những hệ số bậc thấp. Đây là **lỗi đại số**, không phải lỗi làm tròn hay lỗi NTT.

Bài thuộc nhóm **Đa thức và biến đổi**, trình bày bản chất linear/circular convolution, ví dụ cuộn hệ số, cách chọn N, zero-padding, ràng buộc NTT, độ chính xác modulo, mã **Java 17+ chạy độc lập** và phương pháp kiểm thử.

## 1. Phân biệt ba đối tượng: đa thức, dãy và biến đổi

Một đa thức:

**A(x) = a₀ + a₁x + ... + aₙ₋₁x^(n−1)**

có thể được lưu bằng mảng hệ số:

**a = [a₀,a₁,...,aₙ₋₁]**.

Tương tự:

**B(x) = b₀ + b₁x + ... + bₘ₋₁x^(m−1)**.

Khi nhân hai đa thức, hệ số của C(x)=A(x)B(x) tại bậc k là:

**cₖ = Σ aᵢbⱼ, với i+j=k**.

Vì i nằm trong 0..n−1 và j trong 0..m−1, tổng i+j lớn nhất là **n+m−2**. Vậy C có tối đa **n+m−1 hệ số**, đánh số k=0..n+m−2.

Khi dùng NTT hoặc FFT, ta tạm biểu diễn A,B thành hai vector **độ dài N**. Điều quan trọng là phép biến đổi độ dài N mặc định tính các chỉ số **theo vòng modulo N**. Chỉ khi **N đủ lớn**, quy tắc theo vòng mới trùng với phép cộng chỉ số bình thường của tích chập tuyến tính.

### Độ dài mảng khác bậc thực của đa thức

Một dãy có thể có số 0 cuối, ví dụ a=[1,2,0,0] vẫn biểu diễn 1+2x. Nếu muốn tối ưu, có thể bỏ những số 0 cuối trước khi chọn độ dài, miễn là đề cho phép thay đổi quy ước độ dài. Nhưng **không được bỏ hệ số khác 0** hay thay đổi vị trí hệ số.

Hợp đồng thường dùng trong code: mọi phần tử đầu vào được coi là một vị trí hệ số; với n,m>0, kết quả trả **đúng n+m−1 phần tử**, kể cả những số 0 ở cuối.

## 2. Tích chập tuyến tính: công thức và ví dụ

Với a có n phần tử và b có m phần tử, **linear convolution** được định nghĩa:

**c[k] = Σ a[i]·b[k−i]**

với những chỉ số i và k−i đều hợp lệ.

Độ dài output:

**R = n+m−1** nếu n>0 và m>0.

Nếu một dãy rỗng, code bài này quy ước tích chập tuyến tính là **mảng rỗng**. Đây là định nghĩa tiện dụng cho API, khác với các tình huống đòi lưu rõ bậc của đa thức không.

### Ví dụ A(x) và B(x)

~~~text
a = [1, 2, 3]           A(x) = 1 + 2x + 3x^2
b = [4, 5, 6]           B(x) = 4 + 5x + 6x^2
~~~

Nhân theo từng bậc:

- c[0]=1·4=**4**.
- c[1]=1·5+2·4=**13**.
- c[2]=1·6+2·5+3·4=**28**.
- c[3]=2·6+3·5=**27**.
- c[4]=3·6=**18**.

Vậy:

**linear(a,b) = [4,13,28,27,18]**.

Ở đây n=3,m=3 nên **R=5**. Tích có bậc tối đa 4; chỉ cấp 4 ô là không đủ giữ toàn bộ kết quả.

### Sơ đồ theo hệ số

~~~text
C(x) = 4 + 13x + 28x^2 + 27x^3 + 18x^4

K=0:  4
K=1: 13
K=2: 28
K=3: 27
K=4: 18
~~~

Đây là đáp án tuyến tính phải khôi phục trước khi nghĩ đến làm tròn hoặc rút gọn modulo.

## 3. Tích chập vòng: chỉ số được cộng theo modulo N

Với hai dãy độ dài **N**, tích chập vòng định nghĩa:

**d[k] = Σ a[i]·b[j]**, trong đó **(i+j) mod N = k**.

Viết gọn:

**d[k] = Σ_{i=0}^{N−1} a[i]·b[(k−i) mod N]**.

Khác với tuyến tính, các cặp chỉ số có tổng lớn hơn hoặc bằng N **không bị bỏ** mà cộng vào vị trí tổng modulo N.

Nếu c là tích chập tuyến tính của hai dãy gốc (và mỗi dãy gốc đã được đưa vào vector N phần tử phù hợp), thì:

**d[k] = c[k] + c[k+N] + c[k+2N] + ...**

với những chỉ số c hợp lệ.

Công thức này gọi là **folding / aliasing / wrap-around**. Nó cho thấy chính xác hệ số nào bị cộng chồng.

### Vì sao FFT/NTT trả tích chập vòng?

DFT độ dài N sử dụng nghiệm bậc N của 1, nên **ω^N=1**. Trong miền tần số, mọi lũy thừa x^N được đồng nhất với 1 khi quay về miền hệ số.

Theo ngôn ngữ đa thức, nhân bằng DFT độ dài N và biến đổi ngược cho tích:

**A(x)·B(x) modulo (x^N−1)**.

Vì x^N≡1 theo môđun ấy, một hệ số của x^(N+t) sẽ góp vào hệ số x^t.

Nó **không phải** kết quả A(x)B(x) đầy đủ khi bậc tích ≥N.

## 4. Ví dụ cuộn hệ số: chọn N=4 là sai cho bài tuyến tính

Quay lại:

~~~text
a = [1, 2, 3]
b = [4, 5, 6]
linear = [4, 13, 28, 27, 18]
~~~

Nếu chọn biến đổi độ dài **N=4**, cả a và b đều có thể đệm thành 4 phần tử:

~~~text
a4 = [1, 2, 3, 0]
b4 = [4, 5, 6, 0]
~~~

Nhưng tích tuyến tính dài R=5 vẫn **lớn hơn N=4**.

Hệ số c[4]=18 cuộn về vị trí 4 mod4=0:

~~~text
Linear coefficients by degree:
k=0   4
k=1  13
k=2  28
k=3  27
k=4  18

Cyclic N=4:
d[0] = c[0] + c[4] = 4 + 18 = 22
d[1] = c[1]        = 13
d[2] = c[2]        = 28
d[3] = c[3]        = 27
~~~

Vậy **circular N=4 = [22,13,28,27]**.

Đây không phải sai số nhỏ gần 0, mà là **khác hẳn hệ số bậc 0**: 22 thay vì 4, đồng thời hệ số bậc 4 biến mất.

### Cách đúng: chọn N=8

Với R=5, lũy thừa hai nhỏ nhất không nhỏ hơn R là **N=8**.

~~~text
a8 = [1, 2, 3, 0, 0, 0, 0, 0]
b8 = [4, 5, 6, 0, 0, 0, 0, 0]

NTT(a8) * NTT(b8) pointwise
then inverse NTT

Full vector size 8:
[4, 13, 28, 27, 18, 0, 0, 0]

Return first R=5:
[4, 13, 28, 27, 18]
~~~

Không có chỉ số tích i+j nào đạt 8, nên không có hệ số nào cuộn từ bậc cao về bậc thấp.

**Ghi nhớ:** N phải đủ chứa **tích**, không chỉ đủ chứa **hai đầu vào**.

## 5. Chứng minh điều kiện N≥n+m−1

Giả sử a có các vị trí 0..n−1, b có 0..m−1 và n,m đều dương.

Trong tích, mọi cặp i,j thỏa:

**0 ≤ i+j ≤ (n−1)+(m−1) = n+m−2**.

Nếu:

**N≥n+m−1**,

thì **i+j<N** cho mọi cặp. Vì thế:

**(i+j) mod N = i+j**.

Do vậy điều kiện vòng không gây bất cứ sự trùng chỉ số nào, và tích chập vòng độ dài N chính xác là tích chập tuyến tính được **đệm thêm số 0 tới N phần tử**.

Ngược lại, nếu N<n+m−1, tồn tại một cặp chỉ số i,j với i+j≥N. Với những hệ số đầu vào khác 0 ở các vị trí ấy, phần đóng góp sẽ cuộn về vị trí thấp và có thể thay đổi output. Vì vậy **không có bảo đảm cho mọi dữ liệu** khi N quá ngắn.

### Có trường hợp N ngắn vẫn cho kết quả tình cờ đúng không?

Có, nếu các hệ số ở vị trí sẽ cuộn đều bằng 0 hoặc tổng cuộn vô tình triệt tiêu theo modulo, output có thể không lộ lỗi ở một test.

Nhưng đó không làm thay đổi quy tắc bảo đảm **R=n+m−1**. Một giải pháp đúng cho mọi đầu vào không được dựa vào việc dữ liệu tình cờ không gây wrap.

### Đề chỉ cần vài hệ số đầu?

Nếu đề hỏi **tích đa thức modulo x^K** (chỉ giữ hệ số bậc <K), đây là **phép cắt bỏ các hệ số cao**, không phải tích chập vòng modulo x^K−1. Muốn dùng FFT/NTT chuẩn một lần, vẫn phải tránh wrap làm nhiễm các hệ số thấp; hoặc dùng thuật toán truncated convolution chuyên dụng có chứng minh.

## 6. Vì sao radix-2 chọn lũy thừa của hai?

FFT/NTT có nhiều biến thể, nhưng chương trình thông dụng nhất dùng **Cooley–Tukey radix-2**, chia một DFT độ dài N thành hai DFT độ dài N/2. Cách này yêu cầu:

**N=2^k**, với k≥0.

Do đó lựa chọn thực tế:

**R=n+m−1**.

**N=smallestPowerOfTwoAtLeast(R)**.

Ví dụ:

| n | m | R=n+m−1 | N cho radix-2 |
| ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 1 |
| 3 | 2 | 4 | 4 |
| 3 | 3 | 5 | 8 |
| 4 | 4 | 7 | 8 |
| 5 | 4 | 8 | 8 |
| 5 | 5 | 9 | 16 |
| 9 | 8 | 16 | 16 |
| 9 | 9 | 17 | 32 |

Nếu R đã là một lũy thừa của hai, **N=R** là đúng, không cần luôn nhân đôi thêm.

### Cần cảnh giác khi tính nextPowerOfTwo

Một lỗi nguy hiểm trong Java:

~~~java
int needed = a.length + b.length - 1;
int n = 1;
while (n < needed) n <<= 1;
~~~

Nếu n,m rất lớn, phép cộng **int có thể overflow**, hoặc n<<=1 có thể tràn thành số âm rồi lặp sai.

Cách an toàn:

1. Chuyển sang **long trước khi cộng**.
2. Kiểm tra kích thước tối đa mà biến đổi thật sự hỗ trợ.
3. Chỉ sau đó mới tăng N bằng dịch trái khi biết không vượt giới hạn.

Trong chương trình NTT, N không được vượt **2^23** do lựa chọn môđun, nên kiểm tra cận trước khi cấp phát.

### FFT không luôn bắt buộc power-of-two

Một thư viện dùng mixed-radix, Bluestein hoặc DFT trực tiếp có thể hỗ trợ N không phải lũy thừa hai. Điều kiện quan trọng không đổi: **N phải đủ lớn để tránh wrap**, và **N phải thuộc tập độ dài được thuật toán biến đổi hỗ trợ**.

## 7. Zero padding chính xác là thao tác gì?

**Zero padding** nghĩa là mở rộng dãy bằng **các hệ số 0 ở phía cuối**, giữ nguyên tất cả hệ số gốc ở đúng chỉ số.

Ví dụ:

~~~text
a = [2, 5, 1]
N = 8

Pad correctly:
[2, 5, 1, 0, 0, 0, 0, 0]
~~~

Không được:

- Thêm 0 vào **đầu** nếu vẫn muốn hệ số bắt đầu ở bậc 0.
- Chèn 0 **giữa** các hệ số, làm thay đổi bậc.
- Ghi đè hệ số cuối bằng 0.
- Cắt input còn N phần tử nếu input dài hơn N.
- Đệm chỉ một phía đủ N, còn phía kia giữ vector thiếu định nghĩa trong API biến đổi.

### Thêm số 0 không làm đổi đa thức

Vì:

**A(x) = a₀+a₁x+...+aₙ₋₁x^(n−1)+0·x^n+...**,

nên phần padding không thay đổi giá trị đa thức, chỉ thay đổi vector mà thuật toán biến đổi nhận.

### Không đệm bằng chu kỳ hoặc lặp lại hệ số

Nếu a=[1,2,3] mà mở rộng thành [1,2,3,1,2,3,...], ta đã tạo một dãy mới, không còn là cùng đa thức. Đệm bằng **0** là điều kiện cần khi dùng một phép biến đổi để thu tích chập tuyến tính.

### Sau biến đổi ngược, bỏ những 0 nào?

Đầu ra kích thước N có R hệ số cần thiết, còn **N−R phần tử cuối** phải bằng 0 trong số học chính xác nếu N≥R.

Trả về **R hệ số đầu**, không nhất thiết trả cả N; tuy nhiên nếu hợp đồng bài yêu cầu vector padded thì phải nêu rõ việc giữ N phần tử.

## 8. Một trường hợp khác: N=4 vừa đủ

Cho:

~~~text
a = [1, 2, 3]  (n=3)
b = [4, 5]     (m=2)
~~~

Khi ấy:

**R=3+2−1=4**.

Tích tuyến tính:

~~~text
c0 = 1*4                  = 4
c1 = 1*5 + 2*4            = 13
c2 = 2*5 + 3*4            = 22
c3 = 3*5                  = 15

linear = [4, 13, 22, 15]
~~~

Chọn N=4 là **đúng**; không có hệ số bậc ≥4 nên không có wrap.

Điều này chỉ ra lỗi không nằm ở bản thân N=4, mà ở việc **N=4 có đủ cho R của đầu vào cụ thể hay không**.

## 9. Ví dụ nhiều hệ số cuộn về cùng vị trí

Cho:

~~~text
a = [1, 1, 1, 1]
b = [1, 1, 1, 1]
n = m = 4

Linear convolution:
[1, 2, 3, 4, 3, 2, 1]
R = 7
~~~

Nếu dùng N=4 (chỉ đủ chứa mỗi đầu vào), các hệ số cao cuộn lại:

~~~text
d[0] = c[0] + c[4] = 1+3 = 4
d[1] = c[1] + c[5] = 2+2 = 4
d[2] = c[2] + c[6] = 3+1 = 4
d[3] = c[3]        = 4

Cyclic N=4:
[4, 4, 4, 4]
~~~

Với N=8, biến đổi ngược trả:

~~~text
[1, 2, 3, 4, 3, 2, 1, 0]
~~~

và sau cắt R=7 được đúng kết quả tuyến tính.

Ví dụ này cho thấy wrap có thể xảy ra ở **nhiều hệ số**, không chỉ c[4] như bài đầu.

## 10. Tích chập vòng có thể là điều bài toán muốn

Không phải lúc nào circular convolution cũng sai. Nó đúng khi đề thực sự muốn các chỉ số quay vòng.

Ví dụ:

- Tương quan/tích chập của tín hiệu có chu kỳ N.
- Một bài đếm cặp theo tổng chỉ số **modulo N**.
- Phép nhân trong vành đa thức **F[x]/(x^N−1)**.
- Một số thuật toán xử lý tín hiệu tuần hoàn.

Nếu đề muốn circular convolution độ dài N, kết quả [22,13,28,27] trong ví dụ N=4 **là đúng cho phép toán đó**.

**Sai lầm chỉ xuất hiện khi bài muốn linear convolution nhưng triển khai trả circular convolution.**

### Hai môđun đa thức khác nhau

- **Modulo x^N:** loại bỏ các hệ số bậc ≥N, **không cộng chúng vào hệ số thấp**.
- **Modulo x^N−1:** thay x^N bằng 1, nên **cộng hệ số bậc cao vào các vị trí thấp**.

Tích chập vòng của DFT/NTT độ dài N tương ứng với **modulo x^N−1**, không phải chỉ cắt mảng output tại N.

Đây là khác biệt rất dễ nhầm khi đề yêu cầu "chỉ lấy K hệ số đầu".

## 11. DFT và định lý tích chập

Với một trường hoặc miền số có nghiệm đơn vị bậc N thích hợp, ký hiệu ω là một nghiệm bậc N nguyên thủy của 1.

DFT độ dài N của vector a:

**Â[k] = Σ_{j=0}^{N−1} a[j]·ω^(j·k)**.

Công thức biến đổi ngược:

**a[j] = N⁻¹·Σ_{k=0}^{N−1} Â[k]·ω^(−j·k)**,

nếu N có nghịch đảo trong miền tính.

Nếu Ĉ[k]=Â[k]·B̂[k], thì sau biến đổi ngược, ta nhận:

**d[r] = Σ_{i+j≡r (mod N)} a[i]·b[j]**.

Đó là **tích chập vòng**, không phải mặc định là tích chập tuyến tính.

### Vì sao pointwise multiplication đúng?

Mỗi hạng a[i]b[j] trong tích Â[k]B̂[k] mang thừa số ω^((i+j)k). Sau inverse transform, tính trực giao của nghiệm đơn vị loại các hạng có tổng chỉ số không đồng dư với r modulo N.

Đây là lý do có dấu **mod N** trong định lý: phép biến đổi độ dài N làm việc với các tần số/cấp số theo chu kỳ N.

### Điều kiện cần của inverse

Trong FFT phức, có thể chia kết quả biến đổi ngược cho N.

Trong NTT trên trường hữu hạn F_p, ta phải nhân với **nghịch đảo modular N⁻¹ mod p**. Với N là lũy thừa của hai và p nguyên tố lẻ phù hợp, N≠0 mod p nên nghịch đảo tồn tại.

Quên chia cho N (hoặc nhân N⁻¹) làm mọi hệ số bị nhân thêm N theo miền số.

## 12. NTT: lựa chọn môđun và giới hạn độ dài

**NTT** sử dụng cùng ý tưởng DFT nhưng thực hiện các phép toán trong một **trường hữu hạn modulo số nguyên tố p**. Ưu điểm: mọi phép cộng/nhân/biến đổi đều là số học môđun chính xác, không có sai số floating-point.

Một lựa chọn phổ biến:

**p = 998244353 = 119·2^23 + 1**, **primitive root g=3**.

Do đó p−1 chia hết cho **2^23**, và triển khai radix-2 với các root phù hợp hỗ trợ độ dài:

**N=1,2,4,...,2^23**.

Với mỗi độ dài N chia p−1, lấy:

**ω = g^((p−1)/N) mod p**.

Nếu ω có bậc đúng N, nó là nghiệm đơn vị cần thiết.

### Hạn chế quan trọng

Với p=998244353 và radix-2, **không được chọn N>2^23**, dù máy vẫn cấp phát mảng lớn được. Khi N không chia p−1, công thức root không tạo đúng nghiệm bậc N; NTT sẽ sai.

Vì vậy để nhân hai đa thức lớn mà:

**R=n+m−1>2^23**,

bài phải dùng một phương pháp khác: một NTT prime hỗ trợ độ dài lớn hơn, thuật toán phân khối, nhiều lần biến đổi với overlap phù hợp, hoặc nhân đa thức theo cấu trúc khác.

**Không được cố tăng N=2^24 với cùng root/mod này rồi hy vọng kết quả đúng.**

### Vì sao không tùy ý dùng 1_000_000_007?

Số 1_000_000_007 là một prime phổ biến, nhưng:

**1_000_000_007−1 = 1_000_000_006**,

chỉ chia hết cho 2 một lần. Nó **không hỗ trợ trực tiếp NTT radix-2 với N=4,8,16,...** bằng nghiệm đơn vị bậc tương ứng.

Nếu đề muốn output modulo 1_000_000_007, có thể cần dùng nhiều NTT prime rồi CRT, hoặc chọn phương pháp khác có chứng minh.

## 13. Kỹ thuật NTT radix-2 và bit reversal

Triển khai NTT lặp thường làm hai phần:

1. **Bit-reversal permutation**: đưa các vị trí về thứ tự chỉ số có bit bị đảo.
2. Các tầng **butterfly** với độ dài len=2,4,8,...,N.

Ở mỗi butterfly:

**u=a[left]**.

**v=ω^j·a[right] mod p**.

Cập nhật:

**a[left]=(u+v) mod p**.

**a[right]=(u−v) mod p**.

Với inverse NTT, dùng **ω⁻¹** ở mỗi tầng, sau đó nhân mọi phần tử với **N⁻¹ mod p**.

### Vì sao bit reversal?

Trong radix-2 iterative, các nhóm con được hợp nhất ở từng mức len. Hoán vị bit-reversal sắp input để mỗi butterfly xử lý đúng cặp phần tử cần thiết mà không cần đệ quy hay cấp phát mảng con cho mọi tầng.

### Không nhầm NTT với cộng trực tiếp

NTT không thay đổi định nghĩa tích chập. Nó chỉ là cách thực hiện nhanh phép biến đổi trong một miền số. **N vẫn quyết định linear hay circular**.

Một NTT hoàn hảo về số học, dùng đúng root và inverse, vẫn cho **đáp án tuyến tính sai** nếu chọn N<R.

## 14. Độ chính xác: tích chập modulo p không phải tích nguyên bất kỳ

Mã Java dùng NTT modulo p=998244353, nên hệ số output là:

**c[k] mod p**, chuẩn hóa vào **[0,p−1]**.

Nếu c[k] âm, giá trị trả về là phần dư không âm của hệ số âm đó. Ví dụ:

~~~text
a = [ 2, -1,  3]
b = [-4,  5]

Linear coefficients in integers:
[-8, 14, -17, 15]

Returned modulo 998244353:
[998244345, 14, 998244336, 15]
~~~

**998244345 đại diện cho -8 mod p**, không phải hệ số nguyên dương 998244345 trong bài muốn số học nguyên chính xác.

### Khi nào có thể khôi phục dấu?

Nếu đã chứng minh mọi hệ số nguyên thật c[k] nằm trong khoảng mở:

**−p/2 < c[k] < p/2**,

ta có thể chuyển phần dư r về:

- r nếu r≤(p−1)/2.
- r−p nếu r>(p−1)/2.

Khi không có cận này, chỉ một modulo không đủ phân biệt c và c+p.

### Cận hệ số đơn giản

Nếu mọi |a[i]|≤M_A và |b[j]|≤M_B, một hệ số c[k] có tối đa min(n,m) hạng:

**|c[k]| ≤ min(n,m)·M_A·M_B**.

Nếu cận này đủ nhỏ hơn p/2, có thể khôi phục signed coefficients từ NTT đơn prime. Nếu không, dùng **nhiều prime + CRT** với tích các môđun đủ lớn, hoặc BigInteger/thuật toán chính xác khác.

### Tránh overflow trước modulo

Mã đặt mỗi giá trị trong [0,p−1] và tính tích dưới dạng **long**.

Với p≈10^9:

**(p−1)² < 10^18 < Long.MAX_VALUE≈9.22×10^18**,

nên phép nhân hai phần dư trong long **an toàn**. Không được viết int*int rồi mới ép sang long: overflow xảy ra trước khi modulo.

## 15. Java 17+: NTT và phép nhân tuyến tính an toàn theo độ dài

Chương trình dưới đây triển khai:

- **MOD=998244353**, primitive root 3, radix-2 N≤2^23.
- **paddedSize(n,m)**: lấy R=n+m−1 bằng long, kiểm tra giới hạn, chọn N=power-of-two nhỏ nhất ≥R.
- **ntt(array,inverse)**: bit reversal + butterfly + nhân nghịch đảo N.
- **linear(a,b)**: zero-pad cả hai dãy tới N, NTT thuận, nhân từng phần tử, NTT ngược, **trả đúng R hệ số đầu**.
- **circular(a,b,N)**: chỉ để minh họa phép tích chập vòng thực sự, và yêu cầu độ dài input không vượt N.
- **naiveLinear(a,b)**: oracle O(nm) dùng số học modulo trực tiếp.
- Các ví dụ cố ý dùng N sai để thấy wrap, trường hợp N vừa đủ, số âm, dãy rỗng và một phần tử.

**Lưu tệp:** ConvolutionPaddingNttDemo.java

~~~java
import java.util.Arrays;
import java.util.Objects;

public class ConvolutionPaddingNttDemo {

    static final int MOD = 998_244_353;
    static final int ROOT = 3;
    static final int MAX_N = 1 << 23;

    static int powMod(long base, long exponent) {
        if (exponent < 0) {
            throw new IllegalArgumentException("Negative exponent");
        }

        long result = 1;
        long factor = Math.floorMod(base, (long) MOD);

        while (exponent > 0) {
            if ((exponent & 1L) != 0) {
                result = result * factor % MOD;
            }

            exponent >>>= 1;
            if (exponent > 0) {
                factor = factor * factor % MOD;
            }
        }
        return (int) result;
    }

    static int norm(int value) {
        return Math.floorMod(value, MOD);
    }

    static int paddedSize(int n, int m) {
        if (n < 0 || m < 0) {
            throw new IllegalArgumentException("Negative length");
        }
        if (n == 0 || m == 0) return 0;

        long needed = (long) n + (long) m - 1L;
        if (needed > MAX_N) {
            throw new IllegalArgumentException(
                    "Required length exceeds supported NTT size");
        }

        int size = 1;
        while (size < needed) {
            size <<= 1;
        }
        return size;
    }

    static void ntt(int[] a, boolean inverse) {
        int n = a.length;

        if (n < 1 || n > MAX_N
                || (n & (n - 1)) != 0) {
            throw new IllegalArgumentException(
                    "NTT length must be power of two <= 2^23");
        }

        // In-place bit-reversal permutation.
        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >>> 1;

            while ((j & bit) != 0) {
                j ^= bit;
                bit >>>= 1;
            }

            j ^= bit;

            if (i < j) {
                int temp = a[i];
                a[i] = a[j];
                a[j] = temp;
            }
        }

        for (int len = 2; len <= n; len <<= 1) {
            int wlen = powMod(ROOT, (MOD - 1L) / len);

            if (inverse) {
                wlen = powMod(wlen, MOD - 2L);
            }

            for (int begin = 0; begin < n; begin += len) {
                long w = 1L;

                for (int j = 0; j < len / 2; j++) {
                    int left = begin + j;
                    int right = left + len / 2;

                    long u = a[left];
                    long v = w * a[right] % MOD;

                    a[left] = (int) ((u + v) % MOD);
                    a[right] = (int) ((u - v + MOD) % MOD);

                    w = w * wlen % MOD;
                }
            }
        }

        if (inverse) {
            int invN = powMod(n, MOD - 2L);
            for (int i = 0; i < n; i++) {
                a[i] = (int) ((long) a[i] * invN % MOD);
            }
        }
    }

    static int[] normalizedPadded(int[] source, int n) {
        if (source.length > n) {
            throw new IllegalArgumentException(
                    "Input is longer than transform length");
        }

        int[] padded = new int[n];

        for (int i = 0; i < source.length; i++) {
            padded[i] = norm(source[i]);
        }

        return padded;
    }

    // Returns the full linear convolution modulo MOD.
    static int[] linear(int[] a, int[] b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");

        if (a.length == 0 || b.length == 0) {
            return new int[0];
        }

        int n = paddedSize(a.length, b.length);
        int required = a.length + b.length - 1;

        int[] x = normalizedPadded(a, n);
        int[] y = normalizedPadded(b, n);

        ntt(x, false);
        ntt(y, false);

        for (int i = 0; i < n; i++) {
            x[i] = (int) ((long) x[i] * y[i] % MOD);
        }

        ntt(x, true);

        // The remaining entries are padding, not output.
        return Arrays.copyOf(x, required);
    }

    // Explicit circular convolution of length N, for comparison.
    static int[] circular(int[] a, int[] b, int n) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");

        if (n < 1 || n > MAX_N
                || (n & (n - 1)) != 0) {
            throw new IllegalArgumentException(
                    "Invalid circular NTT length");
        }

        int[] x = normalizedPadded(a, n);
        int[] y = normalizedPadded(b, n);

        ntt(x, false);
        ntt(y, false);

        for (int i = 0; i < n; i++) {
            x[i] = (int) ((long) x[i] * y[i] % MOD);
        }

        ntt(x, true);
        return x;
    }

    // Independent O(n*m) reference computation.
    static int[] naiveLinear(int[] a, int[] b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");

        if (a.length == 0 || b.length == 0) {
            return new int[0];
        }

        int[] c = new int[a.length + b.length - 1];

        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < b.length; j++) {
                long term = (long) norm(a[i]) * norm(b[j]);
                long sum = c[i + j] + term % MOD;
                c[i + j] = (int) (sum % MOD);
            }
        }

        return c;
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        int[] b = {4, 5, 6};

        int[] correct = linear(a, b);

        System.out.println("A required=5, N="
                + paddedSize(a.length, b.length));
        System.out.println("A linear: "
                + Arrays.toString(correct));
        System.out.println("A circular N=4: "
                + Arrays.toString(circular(a, b, 4)));
        System.out.println("A matches naive: "
                + Arrays.equals(correct, naiveLinear(a, b)));

        int[] ones = {1, 1, 1, 1};

        System.out.println("B required=7, N="
                + paddedSize(ones.length, ones.length));
        System.out.println("B linear: "
                + Arrays.toString(linear(ones, ones)));
        System.out.println("B circular N=4: "
                + Arrays.toString(circular(ones, ones, 4)));

        System.out.println("Boundary N=4: "
                + Arrays.toString(
                        linear(new int[]{1, 2, 3},
                               new int[]{4, 5})));

        System.out.println("Negative linear mod: "
                + Arrays.toString(
                        linear(new int[]{2, -1, 3},
                               new int[]{-4, 5})));

        System.out.println("Empty linear: "
                + Arrays.toString(
                        linear(new int[0],
                               new int[]{1, 2})));

        System.out.println("Singleton N=1: "
                + Arrays.toString(
                        linear(new int[]{5}, new int[]{7})));

        System.out.println("Normalized input: "
                + Arrays.toString(
                        linear(new int[]{998_244_354},
                               new int[]{-1, 2})));

        System.out.println("NTT max supported N: " + MAX_N);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 ConvolutionPaddingNttDemo.java
java ConvolutionPaddingNttDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
A required=5, N=8
A linear: [4, 13, 28, 27, 18]
A circular N=4: [22, 13, 28, 27]
A matches naive: true
B required=7, N=8
B linear: [1, 2, 3, 4, 3, 2, 1]
B circular N=4: [4, 4, 4, 4]
Boundary N=4: [4, 13, 22, 15]
Negative linear mod: [998244345, 14, 998244336, 15]
Empty linear: []
Singleton N=1: [35]
Normalized input: [998244352, 2]
NTT max supported N: 8388608
~~~

### Vì sao demo có hàm circular?

Hàm circular cho thấy cùng phép biến đổi NTT có thể tính **đúng tích chập vòng** khi người gọi muốn điều đó. Lỗi không phải circular, mà là **lẫn yêu cầu tuyến tính và vòng**.

Hàm linear không nhận N từ người dùng; nó **tự tính đủ N** từ hai độ dài và bảo đảm cắt đúng R hệ số. Đây là cách thiết kế API giúp tránh lỗi.

### Vì sao normalizedPadded phải sao chép?

Chúng ta không muốn biến đổi trực tiếp mảng hệ số gốc: NTT in-place sẽ sửa các giá trị thành miền tần số. Tạo hai mảng mới độ dài N vừa đệm số 0 vừa **bảo toàn input**, giúp nhiều lần gọi cùng dữ liệu không tạo kết quả ngẫu nhiên.

### Vì sao kiểm tra N≤2^23?

Bởi đây là giới hạn nghiệm đơn vị của NTT prime đã chọn. Lỗi độ dài không được khắc phục bằng cấp phát thêm RAM; nó đòi một thuật toán biến đổi hoặc prime khác.

### Vì sao kết quả có hệ số lớn gần MOD?

Do code trả phần dư không âm. Chẳng hạn −8 mod998244353 là 998244345, **không phải lỗi wrap chỉ số**. Khi xử lý số âm, cần phân biệt **quy tắc modulo hệ số** với **modulo chỉ số**.

## 16. Trình tự triển khai không thể đảo lộn

Một pipeline tuyến tính nên làm theo thứ tự:

~~~text
Inputs a[0..n-1], b[0..m-1]
        |
        v
Check empty inputs
        |
        v
R = n + m - 1   (compute safely)
        |
        v
Choose supported N >= R
        |
        v
Normalize coefficients modulo p
        |
        v
Zero-pad BOTH arrays to N
        |
        v
Forward NTT/FFT on both padded arrays
        |
        v
Pointwise multiply frequency arrays
        |
        v
Inverse NTT/FFT, including 1/N scaling
        |
        v
Keep first R coefficients
        |
        v
Return linear convolution
~~~

### Những bước bắt buộc

1. **Tính R trước khi chọn N**, không chỉ lấy max(n,m).
2. **Đệm cả hai dãy tới cùng N**, không thể nhân điểm hai phổ khác độ dài.
3. **Không được đổi thứ tự coefficient index** khi đệm.
4. **Sau inverse** mới cắt output, không cắt phổ giữa chừng.
5. Với NTT, **N phải được hỗ trợ bởi p và primitive root**.
6. Với FFT phức, cẩn thận scale inverse và làm tròn khi phục hồi số nguyên.

### Kiểm tra ngay trong API

Các ràng buộc nên được kiểm tra sớm:

- Null input: báo lỗi rõ ràng.
- Mảng rỗng: theo hợp đồng, trả [].
- NTT N phải là lũy thừa hai hợp lệ và ≤max.
- Dãy đầu vào dài hơn N: không được tự truncate.
- Required length quá lớn: ném exception **trước khi cấp phát**.
- Các coefficient âm: chuẩn hóa modulo trước NTT.

Việc kiểm tra giúp biến lỗi trả đáp án sai âm thầm thành lỗi tham số dễ chẩn đoán.

## 17. FFT phức và sai số floating-point

Khi dùng FFT trên complex numbers dạng double, kết quả sau inverse có thể như:

~~~text
Expected integer: 28
Computed double: 27.9999999997

Expected integer: 0
Computed double: -0.0000000002
~~~

Trong tình huống kết quả thực là các số nguyên và sai số đủ nhỏ, ta thường **làm tròn về số nguyên gần nhất**.

Tuy nhiên:

- Không thể khẳng định mọi bài có hệ số lớn đều an toàn với double FFT.
- Phải xét cận sai số, quy mô hệ số, N và số phép toán.
- Không thể dùng làm tròn để sửa một hệ số đã bị **wrap** do N quá ngắn.
- Một coefficient thật sự quá lớn có thể không được biểu diễn chính xác trong double trước khi FFT chạy.

### Phân biệt ba kiểu sai

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Hệ số cao cộng vào thấp | N<R, circular aliasing | So với folding c[k+tN] |
| Sai vài đơn vị gần hệ số đúng | Floating-point roundoff | Kiểm tra cận error, tăng precision hoặc dùng NTT |
| Hệ số âm thành số gần MOD | Biểu diễn phần dư modulo p | Giải mã signed nếu có cận chắc chắn |

Một code chạy NTT vẫn có thể sai vì độ dài; một code chạy FFT vẫn có thể đúng độ dài nhưng sai vì rounding. **Hai vấn đề độc lập**.

## 18. Trường hợp input dài và cách chia khối

Với prime 998244353, NTT radix-2 hỗ trợ tối đa N=2^23. Nếu:

**n+m−1 > 2^23**,

không thể tăng N trực tiếp mà vẫn dùng cùng cấu hình.

Một hướng giải là **chia dãy thành các khối**, nhân các khối nhỏ sao cho mỗi tích khối có R_block không vượt độ dài NTT hỗ trợ, rồi **cộng các kết quả vào đúng offset** của tích chập cuối.

### Overlap-add

Nếu có tín hiệu dài a và kernel b ngắn, chọn block length K sao cho:

**N≥K+m−1**.

Với mỗi block a[t..t+K), ta tính tích chập của block và b, rồi cộng kết quả bắt đầu ở **vị trí t** trong output chung.

Các đoạn output của những block kề nhau có phần **chồng lấp**. Phải cộng đúng vùng overlap; không được lấy riêng từng block rồi nối thẳng.

### Overlap-save

Một lựa chọn khác là overlap-save: đưa các block có overlap vào circular convolution độ dài N, sau đó **loại bỏ những mẫu đầu bị nhiễm alias** theo đúng độ dài kernel. Cách này cần chỉ số và quy tắc giữ/bỏ được thiết kế cẩn thận.

**Không dùng một phép circular convolution N nhỏ rồi cắt R để thay cho tích chập lớn.** Phải xử lý rõ các phần đã cuộn và các offset của từng block.

### Đa thức nhiều chiều

Với tích chập 2D của hai ma trận kích thước (h₁,w₁) và (h₂,w₂), kích thước tuyến tính mong muốn là:

**H=h₁+h₂−1**, **W=w₁+w₂−1**.

Nếu dùng FFT/NTT 2D, phải chọn độ dài biến đổi đủ lớn **theo từng chiều**: N_H≥H và N_W≥W. Đệm thiếu ở một chiều sẽ gây wrap theo chiều ấy.

## 19. Vì sao kiểm thử chỉ bằng tổng hệ số là chưa đủ?

Một tính chất đúng của tích chập tuyến tính:

**Σ c[k] = (Σ a[i])·(Σ b[j])**.

Nhưng tích chập vòng cũng có **tổng hệ số bằng cùng tích**: các hệ số bị cuộn về vị trí khác chứ không mất đi.

Ví dụ:

~~~text
Linear A:
[4, 13, 28, 27, 18]
Sum = 90

Cyclic A with N=4:
[22, 13, 28, 27]
Sum = 90
~~~

Vậy test chỉ so tổng **không phát hiện lỗi wrap**.

Để kiểm tra pipeline tuyến tính, phải so **từng hệ số** với oracle hoặc dùng một tính chất đủ mạnh về độ dài và từng vị trí.

### Oracle tốt: nhân trực tiếp O(nm)

Với mảng nhỏ, tự tính:

~~~text
NAIVE_LINEAR(a, b):
    if a empty or b empty:
        return []

    result = [0] * (n+m-1)

    for i in 0..n-1:
        for j in 0..m-1:
            result[i+j] += a[i] * b[j]

    return result
~~~

Nếu đang làm modulo p, chuẩn hóa mỗi coefficient và mỗi phép cộng/nhân theo modulo.

Oracle này **không dùng FFT/NTT**, nên độc lập về cấu trúc thuật toán, rất phù hợp để phát hiện nhầm N, root, inverse, indices và normalization.

## 20. Kiểm thử property-based và tình huống biên

Tạo nhiều cặp mảng ngẫu nhiên có độ dài nhỏ, rồi:

1. Tính **naive linear** bằng hai vòng lặp.
2. Tính **NTT linear** với N tự chọn.
3. So **toàn bộ R phần tử**.
4. Kiểm tra R=n+m−1 khi n,m không rỗng.
5. Kiểm tra N là lũy thừa hai nhỏ nhất không nhỏ hơn R.
6. Kiểm tra input **không bị sửa**.
7. Với N≥max(n,m) nhưng N<R, tính circular NTT và so với **naive folding** theo modulo N.
8. Với N≥R, kiểm tra circular NTT N phần tử bắt đầu bằng R hệ số tuyến tính và kết thúc bằng N−R số 0.
9. Thử hệ số **âm**, 0, gần MOD, lớn hơn MOD và cả Integer.MIN_VALUE.
10. Kiểm tra N=1, N=2, các ranh giới R=power of two và R=power of two+1.

### Test phát hiện lỗi độ dài

| a | b | R | N đúng | Kết quả tuyến tính |
| --- | --- | ---: | ---: | --- |
| [1,2,3] | [4,5,6] | 5 | 8 | [4,13,28,27,18] |
| [1,2,3] | [4,5] | 4 | 4 | [4,13,22,15] |
| [1,1,1,1] | [1,1,1,1] | 7 | 8 | [1,2,3,4,3,2,1] |
| [5] | [7] | 1 | 1 | [35] |
| [] | [1,2] | 0 | 0 theo API | [] |
| [2,-1,3] | [-4,5] | 4 | 4 | [-8,14,-17,15] trong Z |
| [998244354] | [-1,2] | 2 | 2 | [-1,2] modulo p |

### Kiểm tra input không bị sửa

NTT thông thường là **in-place**. Nếu bạn đưa mảng a gốc trực tiếp vào ntt(a,false), sau phép biến đổi nó **không còn là mảng hệ số**.

Một API tích chập được thiết kế tốt nên sao chép dữ liệu vào mảng padding, hoặc ghi rõ hàm **mutates input**.

Trong code bài này, linear và circular đều tạo mảng sao chép; a,b đầu vào được giữ nguyên.

### Kiểm tra giới hạn kích thước

Không nên cố cấp phát mảng cực lớn chỉ để thử lỗi N>MAX. Có thể kiểm tra **paddedSize** bằng độ dài số nguyên, trước cấp phát:

- R=2^23 → N=2^23 được chấp nhận.
- R=2^23+1 → bị từ chối.
- n=0 hoặc m=0 → output rỗng, không cần NTT.

## 21. Những lỗi thường gặp

1. **Chọn N≥max(n,m)** thay vì **N≥n+m−1**.
2. **Chọn N=n+m−2**, thiếu đúng một hệ số cuối.
3. **Coi circular convolution là linear convolution**, không thấy wrap.
4. **Lấy n+m thay vì n+m−1 làm output length**; có thể thừa một hệ số 0.
5. **Luôn nhân đôi N ngay cả khi R đã là power-of-two**, tốn RAM/time không cần.
6. **Không kiểm tra N thuộc tập độ dài hỗ trợ của FFT/NTT**, root sai.
7. **Dùng mod998244353 với N>2^23**, không có radix-2 root cần thiết.
8. **Dùng mod1e9+7 cho radix-2 NTT dài mà không xét p−1**, không có root thích hợp.
9. **Đệm 0 chỉ một input** nhưng biến đổi hai vector không cùng N.
10. **Đệm 0 ở đầu** và quên bù chỉ số output bị dịch.
11. **Chèn 0 giữa các coefficient**, đổi bậc đa thức.
12. **Đệm bằng cách lặp dãy**, biến tích chập tuyến tính thành dữ liệu khác.
13. **Cắt input vì dài hơn N**, đánh mất hệ số.
14. **Cắt phổ trước inverse transform**, phá thông tin biến đổi.
15. **Quên scale 1/N trong inverse FFT hoặc nhân nghịch đảo N ở NTT**.
16. **Quên dùng root inverse khi inverse NTT**, không khôi phục input.
17. **Không chuẩn hóa hệ số âm modulo p**, đưa số âm trực tiếp vào butterfly.
18. **Nhân int*int rồi mới ép long**, overflow trước khi mod.
19. **Cho rằng modulo output luôn bằng hệ số nguyên thật**, dù hệ số có thể vượt p.
20. **Giải mã signed residue không có cận |c|<p/2**, diễn giải sai.
21. **Coi floating-point error có thể được sửa bằng zero padding**, không phân biệt nguồn lỗi.
22. **Coi aliasing là lỗi floating-point** và chỉ gọi round/Math.round.
23. **Dùng c[k] mod x^N như c[k] modulo x^N−1**, nhầm truncate với wrap.
24. **Chỉ kiểm tra tổng hệ số**, không phát hiện folding.
25. **Không thử a,b khác độ dài**, bỏ qua lỗi công thức R.
26. **Không thử N=1 và n=m=1**, tạo lỗi vòng radix-2.
27. **Không thử một mảng rỗng**, tính R=−1 hoặc cấp phát kích thước âm.
28. **Cộng n+m−1 trong int trước khi kiểm tra**, overflow độ dài.
29. **Không giữ nguyên input**, lần gọi NTT sau dùng dữ liệu đã biến đổi.
30. **Dùng circular convolution ở mỗi block rồi nối thẳng**, không overlap-add.
31. **Chỉ so 4 hệ số đầu khi đáp án cần 5**, bỏ sót chính hệ số đã gây wrap.
32. **Dùng một bộ test toàn số 0**, khiến mọi lỗi độ dài không lộ.
33. **Nhầm chỉ số i+j của tích chập với i−j của tương quan (correlation)**.
34. **Không xác định đề cần linear, circular hay truncated convolution**, chọn sai phép toán từ đầu.
35. **Quên rằng độ dài output tính theo số hệ số n,m không theo bậc viết trong ký hiệu**, dẫn tới off-by-one.
36. **Nhầm size được cấp phát với size N được phép bởi primitive root**, cấp phát thành công vẫn sai toán học.

## 22. Phân biệt convolution và correlation

**Convolution** trong bài này có:

**c[k] = Σ a[i]b[j]** với i+j=k.

**Cross-correlation** thường xét độ dịch với chỉ số dạng **i−j** hoặc tương đương bằng việc đảo một dãy, tùy quy ước. Không được tự dùng công thức convolution cho một bài correlation mà không đảo/chuyển chỉ số phù hợp.

Ví dụ, nếu phải đếm số cách ghép một phần tử ở vị trí i của a với một phần tử ở vị trí j của b sao cho **i−j=t**, có thể đảo b rồi tính convolution, sau đó ánh xạ vị trí output về t.

Dù đã biến đổi thành convolution đúng, **vẫn phải chọn độ dài N đủ cho toàn bộ tích chập tuyến tính**. Việc đảo mảng không loại bỏ điều kiện zero padding.

### Tính không giao hoán của bài tương quan

Convolution của dãy vô hướng có tính giao hoán **a*b=b*a** về các hệ số tuyến tính. Correlation theo độ dịch có thể đổi dấu độ dịch khi đổi thứ tự hai dãy; đừng trộn hai định nghĩa.

## 23. Khi nào chọn naive thay cho NTT?

Gọi R=n+m−1 và N là power-of-two nhỏ nhất ≥R.

- **Schoolbook:** O(nm) phép nhân/cộng, code ngắn, ít cấu trúc phụ.
- **NTT radix-2:** O(N log N), cần mảng N, root đúng, modulo prime và inverse transform.

Với những mảng rất ngắn, schoolbook thường đơn giản hơn và có thể nhanh hơn do NTT có chi phí khởi tạo, bit reversal, modular exponentiation và ba lần biến đổi.

NTT có lợi khi n,m tương đối lớn, phép nhân trực tiếp O(nm) trở nên đắt, và bài cần **convolution modulo một prime phù hợp**.

### Bộ nhớ NTT

Mã tạo hai mảng độ dài N để thực hiện hai biến đổi, rồi giữ mảng output độ dài R:

**O(N+R) = O(N)** bộ nhớ phụ và kết quả, vì R≤N.

Nếu làm convolution cho nhiều cặp khác nhau, có thể cân nhắc tái sử dụng buffer và tiền xử lý roots với đồng bộ truy cập thích hợp. Nhưng nếu chia sẻ buffer giữa nhiều lời gọi mà không quản lý tốt, có thể tạo lỗi ghi chồng.

### Phép nhân số nguyên cực lớn

Để nhân hai số nguyên rất dài, có thể biểu diễn theo các limb rồi dùng convolution để ghép tích các limb, sau đó truyền carry. Khi đó cần:

- Chọn base limb để kiểm soát cận hệ số.
- Chọn N đủ lớn cho linear convolution.
- Dùng đủ modulo/CRT hoặc FFT có bảo đảm precision.
- Truyền carry từ bậc thấp lên cao sau khi có hệ số.
- Xử lý dấu, số 0 và chuẩn hóa.

Chọn N sai sẽ phá tích số nguyên ngay cả khi bước carry đúng.

## 24. Bài tập tự kiểm tra

**Câu 1.** Hai dãy dài n=6,m=7 cần tối thiểu bao nhiêu hệ số output?  
**Đáp án:** R=6+7−1=12. Với radix-2, N=16.

**Câu 2.** n=m=4, chọn N=4 có đủ cho linear convolution không?  
**Đáp án:** Không, R=7, cần ít nhất N=8.

**Câu 3.** Vì sao a=[1,2,3],b=[4,5,6] dùng N=4 cho hệ số đầu bằng 22 thay vì 4?  
**Đáp án:** Hệ số c[4]=18 cuộn về chỉ số 0, nên 4+18=22.

**Câu 4.** Với n=3,m=2, N=4 đúng hay sai?  
**Đáp án:** Đúng, R=4.

**Câu 5.** Vì sao phải đệm 0 **ở cuối**?  
**Đáp án:** Giữ nguyên hệ số ứng với bậc x^i; chèn 0 vào đầu hay giữa làm thay đổi bậc.

**Câu 6.** Điều kiện để circular convolution độ dài N trùng linear convolution?  
**Đáp án:** N≥n+m−1 với hai vector gốc được zero-pad đúng.

**Câu 7.** Nếu R=9 thì N radix-2 nhỏ nhất là bao nhiêu?  
**Đáp án:** 16.

**Câu 8.** FFT/NTT độ dài N nhân đa thức theo môđun nào?  
**Đáp án:** Theo modulo x^N−1, dẫn tới wrap các bậc cao vào bậc thấp.

**Câu 9.** Muốn chỉ giữ K hệ số thấp, dùng circular convolution độ dài K có tự động đúng không?  
**Đáp án:** Không. Truncated convolution modulo x^K loại bỏ hệ số cao; circular convolution cộng chúng xuống hệ số thấp.

**Câu 10.** Tại sao p=998244353 thích hợp cho radix-2 NTT?  
**Đáp án:** p−1=119·2^23 và có primitive root 3, cho nghiệm đơn vị độ dài 2^k với k≤23.

**Câu 11.** Có thể dùng cùng NTT để xử lý R=2^23+1 không?  
**Đáp án:** Không với lựa chọn prime/root/radix-2 này; cần phương án khác hoặc phân khối.

**Câu 12.** Vì sao [-8,14,-17,15] có thể được in thành [998244345,14,998244336,15]?  
**Đáp án:** NTT trả hệ số modulo998244353 dạng phần dư không âm.

**Câu 13.** Vì sao làm tròn không sửa được aliasing do N ngắn?  
**Đáp án:** Đó là phép cộng hệ số sai chỉ số về mặt đại số, không phải sai số số thực.

**Câu 14.** Tổng hệ số có phát hiện mọi lỗi wrap không?  
**Đáp án:** Không; circular folding giữ nguyên tổng hệ số.

**Câu 15.** Kiểm thử độc lập tốt nhất cho mảng nhỏ?  
**Đáp án:** Nhân trực tiếp O(nm) rồi so từng hệ số.

**Câu 16.** NTT trả linear output có độ dài N hay R?  
**Đáp án:** Biến đổi ngược tạo vector N, nhưng hàm linear thường trả **R=n+m−1** phần tử có ý nghĩa.

**Câu 17.** Với input rỗng, API trong bài trả gì?  
**Đáp án:** [] và không chạy NTT.

**Câu 18.** Vì sao không dùng int để nhân hai phần dư gần 10^9?  
**Đáp án:** Tích có thể gần 10^18, vượt int; phải ép long trước khi nhân.

**Câu 19.** Với overlap-add, vì sao không nối thẳng các tích block?  
**Đáp án:** Các block sau nhân kernel có vùng output chồng lấp, phải cộng tại offset phù hợp.

**Câu 20.** Kết quả vòng có luôn sai không?  
**Đáp án:** Không; nó đúng nếu bài thật sự yêu cầu chỉ số modulo N.

## 25. Checklist thực hành và tổng kết

Trước khi nộp bài tích chập FFT/NTT, kiểm tra:

1. **Đề cần loại nào?** Linear, circular hay truncated convolution?
2. **Input n,m có thể rỗng không?** Định nghĩa rõ output.
3. **Cần bao nhiêu hệ số?** R=n+m−1 khi cả hai không rỗng.
4. **Chọn N hợp lệ:** với radix-2, chọn power-of-two nhỏ nhất ≥R.
5. **Kiểm tra giới hạn NTT root:** đặc biệt với 998244353 là N≤2^23.
6. **Tránh overflow length:** cộng độ dài bằng long trước khi chọn N.
7. **Đệm cả hai input bằng 0 tới N**, chỉ ở phía sau.
8. **Chuẩn hóa coefficient modulo p** nếu dùng NTT, kể cả số âm.
9. Biến đổi thuận, nhân điểm từng phần tử, inverse transform đúng **root inverse và 1/N**.
10. **Cắt output còn đúng R hệ số**, không chỉ giữ số phần tử trước khi biến đổi.
11. Phân biệt kết quả **modulo p** với kết quả nguyên chính xác.
12. Nếu cần số nguyên thực sự, kiểm tra **cận hệ số** hoặc dùng CRT/giải pháp khác.
13. Không sửa input nếu API hứa không mutate.
14. So với oracle nhân trực tiếp O(nm) trên test nhỏ và test aliasing có chủ đích.
15. Thử R là power-of-two và R=power-of-two+1 để bắt lỗi ranh giới.
16. Nếu R vượt max NTT, chọn thuật toán khác hoặc chia khối **có xử lý overlap**.

**Kết luận:** FFT/NTT độ dài N tự nhiên tạo **tích chập vòng modulo N**. Để thu **tích chập tuyến tính**, phải **đệm 0 tới N≥n+m−1**; với radix-2, chọn lũy thừa hai hợp lệ ngay phía trên. Một lỗi chọn N có thể làm hệ số cao cuộn xuống hệ số thấp mà mọi phép butterfly, modular multiplication và inverse transform đều vẫn chạy đúng — vì thế **kiểm tra độ dài trước khi biến đổi là điều kiện đầu tiên của tính đúng**.
