# NTT và điều kiện của môđun, căn đơn vị

**NTT (Number Theoretic Transform)** là một phép biến đổi kiểu Fourier được tính hoàn toàn trong **số học modulo**. Thay vì dùng số phức và chấp nhận sai số làm tròn như FFT số thực, NTT dùng các **căn đơn vị** có đúng bậc trong một trường hữu hạn để biến phép **nhân đa thức** từ tích chập bậc hai thành các phép biến đổi có độ phức tạp gần tuyến tính.

Vấn đề quan trọng nhất trong bài **“NTT và điều kiện của môđun, căn đơn vị”** thuộc nhóm **Đa thức và biến đổi** của Computer Science Algorithms không phải là học thuộc một đoạn mã butterfly. Mấu chốt là hiểu **vì sao không thể chọn tùy ý môđun**: phải có căn đơn vị bậc bằng độ dài biến đổi, và phép chia cho độ dài biến đổi trong phép nghịch đảo phải hợp lệ. Chỉ khi các điều kiện đại số này được thỏa mãn, công thức NTT thuận, nghịch và định lý tích chập mới đúng.

Bài trình bày từ định nghĩa đa thức, tích chập, trường hữu hạn, căn nguyên thủy bậc n, cách kiểm tra phần tử sinh, môđun nổi tiếng **998244353 = 119·2^23+1**, tính NTT theo radix-2 với đảo bit, công thức nghịch đảo, giới hạn độ dài, chứng minh tính đúng, xử lý hệ số âm/long, cho đến **CRT để khôi phục tích chập số nguyên chính xác**. Phần Java 17+ cuối bài đã được chạy với 14.641 cặp đa thức vét cạn, 1.500 cặp có seed và 500 phép đối chiếu DFT trực tiếp.

## 1. Bài toán nhân đa thức

Cho hai đa thức:

~~~text
A(x) = a[0] + a[1]x + ... + a[n-1]x^(n-1).
B(x) = b[0] + b[1]x + ... + b[m-1]x^(m-1).
~~~

Tích C(x)=A(x)B(x) có hệ số:

~~~text
c[k] = tổng a[i]*b[j] trên mọi i+j=k.

Nếu cả hai mảng hệ số khác rỗng:
số hệ số kết quả = n+m-1.
~~~

Đây là **tích chập tuyến tính** (linear convolution). Cài đặt ngây thơ dùng hai vòng lặp qua i và j, cập nhật c[i+j], tốn **O(nm)** phép nhân/cộng modulo.

Nếu n và m đều xấp xỉ một triệu, phép nhân trực tiếp có số cặp hệ số rất lớn. NTT giúp đưa đa thức về **các giá trị tại những điểm đặc biệt**, nhân từng giá trị tương ứng, rồi biến đổi ngược để thu hệ số.

## 2. Ví dụ tích chập nhỏ

Với:

~~~text
A(x)=1+2x+3x².
B(x)=4+5x.

c[0]=1*4=4.
c[1]=1*5+2*4=13.
c[2]=2*5+3*4=22.
c[3]=3*5=15.

C=[4,13,22,15].
~~~

Với môđun 998244353, mọi hệ số trên đều nhỏ hơn môđun nên biểu diễn theo modulo không thay đổi. NTT và phép nhân schoolbook phải cho **cùng mảng [4,13,22,15]**.

Nhưng nếu hệ số có số âm, ví dụ A=[1,−2,3], B=[−4,5], kết quả nguyên là [−4,13,−22,15]. Theo modulo 998244353, kết quả chuẩn không âm là:

~~~text
[998244349, 13, 998244331, 15].
~~~

**NTT modulo không trả lại số âm nguyên gốc**; nó trả đại diện [0,p−1] của từng hệ số. Khi cần kết quả nguyên chính xác, phải biết cách khôi phục hoặc dùng nhiều môđun, được trình bày ở phần CRT.

## 3. Trường hữu hạn là điều kiện cơ sở

Nếu p là **số nguyên tố**, tập các phần dư:

~~~text
F_p = {0,1,2,...,p-1}
~~~

tạo thành **trường hữu hạn**: cộng, trừ, nhân theo p và mọi phần tử khác 0 đều có nghịch đảo nhân.

Nhóm các phần tử khác 0, viết F_p^×, có **p−1 phần tử** và là một nhóm nhân **cyclic**. Do đó tồn tại **phần tử sinh (primitive root modulo p)** g với mọi phần tử khác 0 là một lũy thừa của g.

Nhờ cấu trúc này, ta có thể xây những căn đơn vị có đúng bậc n, sử dụng phép chia cho n qua nghịch đảo modulo p, và chứng minh tính trực giao cần thiết của NTT.

Cần phân biệt **môđun bất kỳ** với **môđun nguyên tố**. Với số hợp m, phần dư modulo m thường **không tạo trường**; một phần tử khác 0 có thể không có nghịch đảo, và chỉ kiểm tra rằng một số có bậc nhân n chưa đủ để dùng công thức nghịch đảo DFT thông thường.

## 4. Căn đơn vị bậc n là gì?

Trong trường F_p, một số ω là **căn đơn vị bậc n** nếu:

~~~text
ω^n ≡ 1 (mod p).
~~~

Nhưng điều kiện ấy **chưa đủ**. Chẳng hạn ω=1 thỏa ω^n=1 với mọi n, nhưng không mang đủ thông tin để phân biệt n vị trí của biến đổi.

Cần ω là **căn nguyên thủy bậc n**: bậc nhân của ω **chính xác bằng n**. Tức:

~~~text
ω^n = 1 (mod p),
và ω^k != 1 (mod p) với mọi 1 <= k < n.
~~~

Khi n là lũy thừa của 2 và n>1, từ ω^n=1 chỉ cần kiểm tra thêm ω^(n/2) != 1 để kết luận bậc đúng n. Với n tổng quát, có thể kiểm tra ω^(n/q) != 1 cho mọi ước nguyên tố phân biệt q của n.

**Căn đơn vị nguyên thủy khác với phần tử sinh g**: g có bậc p−1, còn ω thường có bậc n nhỏ hơn, được tạo từ g. Chúng không phải hai tên gọi có thể thay thế tùy ý.

## 5. Điều kiện để tồn tại căn nguyên thủy bậc n

Vì nhóm F_p^× có bậc p−1 và cyclic, một phần tử có bậc n tồn tại **khi và chỉ khi**:

~~~text
n chia hết p−1? KHÔNG.
Điều kiện đúng: (p−1) % n == 0.
Tức: n | (p−1).
~~~

Nói cách khác, **n phải là một ước của p−1**, không phải p−1 là ước của n.

Nếu n | (p−1) và g là phần tử sinh modulo p, ta đặt:

~~~text
ω_n = g^((p−1)/n) mod p.
~~~

Khi đó ω_n có bậc đúng n. Chứng minh: g có bậc p−1, nên bậc của g^d bằng (p−1)/gcd(p−1,d). Với d=(p−1)/n, kết quả là n.

Vì n≤p−1<p, nên n không đồng dư 0 modulo p, và **n có nghịch đảo modulo p**. Điều kiện này quan trọng đối với NTT nghịch đảo: cần nhân kết quả với n^(−1).

## 6. Vì sao môđun 998244353 thích hợp cho NTT?

Môđun thường dùng:

~~~text
p = 998244353 (số nguyên tố).

p−1 = 998244352
    = 119 * 2^23
    = 7 * 17 * 2^23.
~~~

Vì vậy các kích thước n=1,2,4,8,...,2^23 đều là ước của p−1. NTT radix-2 có thể dùng **độ dài tối đa 2^23 = 8.388.608** với môđun này.

Một phần tử sinh của F_p^× là:

~~~text
g = 3.
~~~

Muốn NTT độ dài n=2^k, đặt ω_n=3^((p−1)/n) modulo p. Chỉ dùng n≤2^23. Không thể dùng cùng môđun này cho NTT radix-2 độ dài 2^24 theo công thức chuẩn, vì 2^24 không chia p−1.

Lưu ý đây là **giới hạn đại số**, chưa phải giới hạn bộ nhớ. Trên máy có RAM ít, cấp phát hai mảng cỡ 2^23 cùng các mảng tạm có thể khó; dự án thực tế cần kiểm tra thêm bộ nhớ và giới hạn độ dài input.

## 7. Chứng minh g=3 là phần tử sinh

Trong nhóm cyclic bậc p−1, một phần tử g có bậc p−1 khi:

~~~text
g^(p−1) = 1 (mod p)

và với mọi ước nguyên tố q của p−1:
g^((p−1)/q) != 1 (mod p).
~~~

Ở đây:

~~~text
p−1=2^23*7*17.
Các ước nguyên tố phân biệt: {2,7,17}.
~~~

Vì vậy chỉ cần kiểm tra:

~~~text
3^((p−1)/2)  != 1 (mod p).
3^((p−1)/7)  != 1 (mod p).
3^((p−1)/17) != 1 (mod p).
3^(p−1)       = 1 (mod p).
~~~

Chương trình Java thực hiện đúng các phép thử này bằng **modPow**. Khi xác định bậc của một ứng viên g với một môđun nguyên tố khác, phải phân tích **đầy đủ p−1** và kiểm tra mọi ước nguyên tố phân biệt. Không được chỉ thấy g^n=1 với một n nào đó rồi kết luận g là phần tử sinh.

## 8. Môđun 1.000.000.007 có dùng NTT radix-2 dài được không?

Số 1.000.000.007 cũng là số nguyên tố phổ biến trong bài lập trình, nhưng:

~~~text
1.000.000.007 − 1 = 1.000.000.006
                    = 2 * 500.000.003.
~~~

Phần lũy thừa 2 lớn nhất chia được p−1 chỉ là **2^1**. Do đó với p=1.000.000.007, ta có thể có căn nguyên thủy bậc 1 hoặc 2, nhưng **không có căn nguyên thủy bậc 4,8,16,...**.

Nếu hai đa thức cần NTT độ dài 8, không thể giữ nguyên môđun này và chỉ thay g một cách tùy ý; bất đẳng thức n | (p−1) **không đạt**.

Các lựa chọn:

- Dùng một hoặc nhiều **môđun thân thiện với NTT**, rồi nếu bài cần môđun khác, tái tạo kết quả bằng CRT hoặc một phương pháp được chứng minh đúng.
- Dùng phép nhân đa thức ngây thơ nếu kích thước nhỏ.
- Dùng thuật toán tích chập khác phù hợp yêu cầu chính xác và miền dữ liệu.

Đừng nhầm việc một số nguyên tố “đẹp, hay dùng” với việc nó tự hỗ trợ mọi kích thước NTT radix-2.

## 9. Ví dụ căn nguyên thủy dễ tính tay: modulo 17

Để hiểu cơ chế trước khi dùng môđun lớn, xét:

~~~text
p=17 là số nguyên tố.
p−1=16.
g=3 là phần tử sinh modulo 17.

Chọn n=8.
ω = 3^((17−1)/8) = 3² = 9 (mod 17).
~~~

Ta kiểm tra:

~~~text
9^2 = 81 ≡ 13 (mod17).
9^4 ≡ 13² = 169 ≡ 16 (mod17).
9^8 ≡ 16² = 256 ≡ 1 (mod17).
~~~

Vì ω^8=1 nhưng ω^4=16≠1, số 9 có đúng bậc 8. Khi n=4, ω_4=3^4=13; với dãy [1,2,3,4], DFT modulo 17 theo ω_4 cho:

~~~text
A[0]=10.
A[1]=6.
A[2]=15.
A[3]=7.
~~~

Những phép tính chỉ dùng cộng/nhân modulo 17, không có số phức. Dùng p=17 để học thì dễ, nhưng p−1 chỉ có 2^4 nên NTT radix-2 hỗ trợ tối đa n=16; không đủ cho nhân đa thức lớn.

## 10. Công thức NTT thuận

Giả sử có một mảng a dài n và ω là căn nguyên thủy bậc n modulo p. NTT thuận định nghĩa:

~~~text
A[k] = Σ a[j] * ω^(j*k) (mod p)
       với j=0..n−1, k=0..n−1.
~~~

Đây là DFT trên trường F_p. Điểm đánh giá tương ứng là các lũy thừa của ω:

~~~text
A[k] = a(ω^k),
nếu a(x)=Σ a[j] x^j.
~~~

Dãy [1,ω,ω²,...,ω^(n−1)] gồm **n phần tử khác nhau** vì ω có bậc đúng n. Nếu chọn ω=1, tất cả điểm đánh giá trùng nhau, nên không thể khôi phục toàn bộ hệ số từ các giá trị ấy.

Bản NTT tính trực tiếp công thức trên cần O(n²) phép nhân/cộng. Thuật toán butterfly radix-2 tận dụng sự lặp lại của các lũy thừa ω để giảm xuống **O(n log n)**.

## 11. NTT nghịch đảo và hệ số n^(−1)

NTT nghịch đảo đưa dãy giá trị A[k] về hệ số a[j]:

~~~text
a[j] = n^(-1) *
       Σ A[k] * ω^(-j*k) (mod p),
       với k=0..n−1.
~~~

Trong trường F_p, vì n không chia hết p nên n có nghịch đảo nhân modulo p. Với p nguyên tố, công thức Fermat cho:

~~~text
n^(-1) ≡ n^(p−2) (mod p).
ω^(-1) ≡ ω^(p−2) (mod p).
~~~

Đó là lý do chương trình dùng **modPow(n, MOD−2)** và khi inverse dùng **modPow(omega, MOD−2)**.

Nếu quên nhân **n^(-1)** ở cuối NTT nghịch, kết quả bị nhân thêm n, không phải mảng hệ số ban đầu. Nếu dùng ω cùng chiều ở cả NTT thuận và nghịch mà không đảo căn, cũng không thu lại dãy ban đầu.

## 12. Chứng minh phép nghịch đảo bằng tính trực giao

Thay công thức NTT thuận vào NTT nghịch:

~~~text
reconstructed[j]
 = n^(-1) * Σ_k A[k] * ω^(-j*k)
 = n^(-1) * Σ_t a[t] * Σ_k ω^((t−j)*k).
~~~

Nếu t=j, tổng trong là n vì mọi số hạng bằng 1.

Nếu t≠j, đặt z=ω^(t−j). Vì ω có **đúng bậc n**, z≠1 nhưng z^n=1. Trong **trường** F_p, 1−z≠0 nên có nghịch đảo. Tổng cấp số nhân:

~~~text
1+z+z²+...+z^(n−1)
 = (1−z^n)/(1−z)
 = 0.
~~~

Vậy mọi hệ số a[t] với t≠j bị triệt tiêu, còn a[j] được nhân n rồi nhân n^(-1), trả đúng a[j].

Chứng minh này lý giải **cả hai điều kiện**: cần ω có đúng bậc n để không lẫn các hệ số, và cần n khả nghịch để chia n. Với môđun nguyên tố và n | (p−1), cả hai đều thỏa.

## 13. Môđun hợp số cần thận trọng hơn

Với môđun hợp số, các phần dư không tạo trường và một phần tử khác 0 có thể là **ước của 0**. Vì vậy lập luận chia cho 1−z ở tổng cấp số nhân không còn tự động hợp lệ.

Một ví dụ:

~~~text
m=15.
z=4 có bậc nhân đúng 2 modulo 15:
4² ≡ 1 (mod15), 4 != 1.

Nhưng 1+4=5 != 0 (mod15).
~~~

Dù độ dài 2 có nghịch đảo modulo 15 (vì gcd(2,15)=1), tính trực giao cần thiết vẫn không tự xảy ra nếu chỉ chọn một phần tử có bậc 2. Với vành hợp số phải dùng định nghĩa **principal root of unity** và các điều kiện bổ sung để bảo đảm tổng trực giao.

Bài và mã Java cố ý dùng trường **F_p với p nguyên tố**, nơi điều kiện n | (p−1) cùng ω nguyên thủy giải quyết vấn đề rõ ràng.

## 14. Định lý tích chập: nhân điểm rồi biến đổi ngược

Nếu A(x), B(x) là hai đa thức, C(x)=A(x)B(x), thì với mọi điểm t:

~~~text
C(t) = A(t) * B(t).
~~~

Vì NTT là phép **đánh giá đa thức** tại các ω^k, ta có:

~~~text
NTT(C)[k] = NTT(A)[k] * NTT(B)[k] (mod p).
~~~

Nhân hai đa thức bằng:

~~~text
1. Đệm a,b lên cùng độ dài N hợp lệ.
2. Fa = NTT(a).
3. Fb = NTT(b).
4. Fc[k] = Fa[k]*Fb[k] mod p.
5. c = INTT(Fc).
6. Trả L hệ số đầu của c.
~~~

Nếu N đủ lớn để chứa tất cả hệ số của tích, không xảy ra hiện tượng quấn vòng của tích chập tuần hoàn. Kết quả chính là **tích chập tuyến tính modulo p**.

## 15. Vì sao phải zero-padding tới N ≥ n+m−1?

NTT độ dài N trên vector độ dài N thực chất mô tả tích trong vành đa thức modulo **x^N−1**. Nếu tích có bậc ít nhất N, các hệ số bậc cao **quấn về** chỉ số thấp:

~~~text
x^N ≡ 1 (mod x^N−1).
~~~

Vì vậy phải chọn N≥L, với L=n+m−1 cho hai đa thức khác rỗng, để đa thức tích có bậc nhỏ hơn N.

Cách chọn đơn giản:

~~~text
L = length(a)+length(b)-1.
N = lũy thừa 2 nhỏ nhất sao cho N >= L.
~~~

Nếu L=4, N=4; nếu L=5, N=8. Không phải cứ dùng N=max(length(a),length(b)) là đúng.

Mã kiểm tra L bằng phép cộng kiểu **long** trước khi ép về int, và từ chối nếu L>2^23. Nếu một trong hai mảng rỗng, quy ước của API là đa thức zero và trả mảng rỗng; không cố NTT kích thước 0.

## 16. Butterfly của NTT radix-2

Giả sử ta chia tổng DFT thành hai phần ứng với chỉ số chẵn và lẻ:

~~~text
E[k] = NTT của a[0],a[2],a[4],...
O[k] = NTT của a[1],a[3],a[5],...
~~~

Với một căn ω của bậc N:

~~~text
A[k]       = E[k] + ω^k * O[k].
A[k+N/2]   = E[k] − ω^k * O[k].
~~~

Một **butterfly** nhận u và v đã nhân twiddle factor w, rồi tạo:

~~~text
newLeft  = (u+v) mod p.
newRight = (u−v) mod p.
~~~

Hai kết quả chia sẻ phần tính w*v. Nhờ phép biến đổi ở mỗi tầng chỉ tốn O(N) và có log2 N tầng, toàn bộ NTT chạy trong **O(N log N)**.

Với NTT nghịch, dùng ω^(−1) và cuối cùng nhân N^(−1). Công thức butterfly tương tự, chỉ thay chiều căn. Không thay dấu bằng cách tùy tiện mà phải dựa vào hướng biến đổi đã định nghĩa.

## 17. Đảo bit trước khi chạy các tầng butterfly

Bản radix-2 **decimation-in-time** lặp sử dụng thứ tự chỉ số **bit-reversal permutation** để các nhóm butterfly ở mỗi tầng có thể cập nhật ngay tại chỗ.

Với N=8, chỉ số có 3 bit:

~~~text
i    nhị phân    đảo 3 bit    vị trí mới
0    000         000          0
1    001         100          4
2    010         010          2
3    011         110          6
4    100         001          1
5    101         101          5
6    110         011          3
7    111         111          7
~~~

Mã Java hoán đổi a[i] và a[j] chỉ khi i<j, tránh đổi một cặp hai lần. Sau đó xử lý các nhóm độ dài len=2,4,8,...,N.

Nếu bỏ bước đảo bit nhưng giữ nguyên vòng butterfly DIT này, kết quả thường không còn khớp định nghĩa NTT của mảng input theo thứ tự gốc. Một triển khai DIF có thể có thứ tự khác, nhưng phải thiết kế đồng bộ cả biến đổi thuận, nghịch và vị trí hoán đổi.

## 18. Chọn ω cho từng tầng

Trong mỗi tầng xử lý block độ dài len là lũy thừa 2, cần căn nguyên thủy **bậc len**:

~~~text
omegaLen = g^((p−1)/len) mod p.
~~~

Tại nhóm block:

~~~text
w = 1.
for j=0..len/2−1:
    u = a[start+j].
    v = w*a[start+j+len/2] mod p.

    a[start+j]       = (u+v) mod p.
    a[start+j+len/2] = (u−v) mod p.

    w = w*omegaLen mod p.
~~~

Với NTT nghịch, thay omegaLen bằng **nghịch đảo modulo p của omegaLen**. Mã triển khai bằng modPow(omegaLen, p−2). Có thể tối ưu bằng tiền tính bảng căn/twiddle nếu gọi nhiều lần cùng N, nhưng bản học thuật chọn cách rõ ràng và bảo đảm đúng.

Trong phép biến đổi, mỗi tầng có N/len block, mỗi block có len/2 butterfly, tổng số butterfly mỗi tầng bằng N/2. Số tầng log2 N, nên đúng là O(N log N).

## 19. An toàn số học Java với môđun 998244353

Môđun được chọn nhỏ hơn 2^31. Với u,v∈[0,p), tổng tối đa 2(p−1):

~~~text
2*(998244353−1)
 = 1996488704
 < Integer.MAX_VALUE = 2147483647.
~~~

Vì vậy **int sum=u+v** trong code không tràn, rồi nếu sum≥p thì trừ p. Hiệu u−v thuộc [−(p−1),p−1], cũng vừa int; nếu âm thì cộng p.

Riêng phép nhân **w * a[right]** có thể gần 10^18, vượt int nhưng **vẫn nhỏ hơn Long.MAX_VALUE ≈9.22·10^18**. Do đó mã ép toán hạng sang long trước khi nhân, rồi `% MOD`, sau đó mới ép về int:

~~~java
int v = (int) (w * a[right] % MOD);
int sum = u + v;
if (sum >= MOD) sum -= MOD;
int diff = u - v;
if (diff < 0) diff += MOD;
~~~

Không được viết nhân giữa hai int rồi `% MOD` vì phép nhân int tràn từ rất sớm. Khi thay MOD bằng một số nguyên tố khác, phải **tính lại cận an toàn** cho cả phép cộng int lẫn phép nhân long, không sao chép khẳng định trên.

## 20. Hệ số âm, hệ số long và nghĩa của kết quả

API nhận **long[]** cho hai đa thức, kể cả các giá trị Long.MIN_VALUE và Long.MAX_VALUE. Trước khi NTT, mỗi hệ số được chuẩn hóa:

~~~java
(int) Math.floorMod(coefficient, (long) MOD)
~~~

Điều này không tràn khi coefficient âm, khác với việc dùng Math.abs(Long.MIN_VALUE). Mảng làm việc nội bộ là **int[]** vì mỗi giá trị đã nằm trong [0,MOD).

Kết quả luôn là **hệ số modulo 998244353** dưới dạng int chuẩn, không phải tích các hệ số long trong số nguyên chính xác.

Ví dụ:

~~~text
A=[1,-2,3], B=[-4,5].
Tích nguyên chính xác=[-4,13,-22,15].
NTT theo MOD trả:
[998244349,13,998244331,15].
~~~

Nếu đầu bài muốn c[k] nguyên có dấu, không được chỉ coi mọi số dư lớn hơn MOD/2 là số âm **mà không có một cận độ lớn bảo đảm**. Việc khôi phục cần đủ thông tin, đặc biệt khi c[k] có thể vượt MOD nhiều lần.

## 21. Mã Java 17+ hoàn chỉnh

Chương trình **NttRootsLesson.java** cài toàn bộ quy trình:

- **modPow:** lũy thừa modulo dùng nhân long, an toàn ở môđun cố định 998244353.
- **requireNttLength:** kiểm tra N là lũy thừa 2, 1≤N≤2^23 và N chia p−1.
- **transform:** NTT thuận/nghịch tại chỗ, bit reversal, butterfly các tầng len=2..N; inverse dùng omega nghịch đảo và chia N bằng N^(p−2).
- **convolution:** nhận hai mảng long, chuẩn hóa hệ số, zero-pad, hai NTT thuận, nhân từng điểm, một NTT nghịch, cắt đúng n+m−1 hệ số.
- **schoolbookOracle:** nhân đa thức O(nm) độc lập để kiểm chứng kết quả.
- **directDft:** tính trực tiếp DFT định nghĩa O(N²), không dùng butterfly, để đối chiếu cả NTT thuận/nghịch.
- **checkPrimitiveRoots:** xác nhận 998244353−1=119·2^23, g=3 là phần tử sinh theo các ước nguyên tố {2,7,17}, và ω có đúng bậc 2^k với k=0..23.
- **verify:** kiểm thử cặp đa thức vét cạn, dữ liệu long có seed, DFT trực tiếp, hệ số cực trị và input lỗi.

Mã giả định đúng sự thật toán học rằng **998244353 là số nguyên tố**; kiểm tra generator được thực hiện với phân tích p−1 của chính môđun này. Không coi hàm requireNttLength là một chứng minh tính nguyên tố cho mọi modulus do người dùng nhập.

~~~java
import java.util.*;

public final class NttRootsLesson {
    public static final int MOD = 998244353;
    public static final int GENERATOR = 3;
    public static final int MAX_LOG = 23;
    public static final int MAX_SIZE = 1 << MAX_LOG;

    private NttRootsLesson() { }

    private static long modPow(long base, long exponent) {
        long x = Math.floorMod(base, (long) MOD);
        long answer = 1;
        while (exponent > 0) {
            if ((exponent & 1L) != 0) {
                answer = answer * x % MOD;
            }
            exponent >>>= 1;
            if (exponent > 0) {
                x = x * x % MOD;
            }
        }
        return answer;
    }

    private static void requireNttLength(int n) {
        if (n < 1 || n > MAX_SIZE || (n & (n - 1)) != 0
                || (MOD - 1) % n != 0) {
            throw new IllegalArgumentException(
                    "NTT length must be power of two <= 2^23");
        }
    }

    private static void transform(int[] a, boolean inverse) {
        int n = a.length;
        requireNttLength(n);

        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >>> 1;
            while ((j & bit) != 0) {
                j ^= bit;
                bit >>>= 1;
            }
            j ^= bit;
            if (i < j) {
                int t = a[i];
                a[i] = a[j];
                a[j] = t;
            }
        }

        for (int len = 2; len <= n; len <<= 1) {
            int half = len >>> 1;
            long omega = modPow(GENERATOR, (MOD - 1L) / len);
            if (inverse) {
                omega = modPow(omega, MOD - 2L);
            }
            for (int start = 0; start < n; start += len) {
                long w = 1;
                for (int j = 0; j < half; j++) {
                    int left = start + j;
                    int right = left + half;
                    int u = a[left];
                    int v = (int) (w * a[right] % MOD);

                    int sum = u + v;
                    if (sum >= MOD) sum -= MOD;
                    int difference = u - v;
                    if (difference < 0) difference += MOD;

                    a[left] = sum;
                    a[right] = difference;
                    w = w * omega % MOD;
                }
            }
        }

        if (inverse) {
            long invN = modPow(n, MOD - 2L);
            for (int i = 0; i < n; i++) {
                a[i] = (int) (a[i] * invN % MOD);
            }
        }
    }

    public static int[] convolution(long[] a, long[] b) {
        if (a == null || b == null) {
            throw new IllegalArgumentException("null coefficient array");
        }
        if (a.length == 0 || b.length == 0) {
            return new int[0];
        }

        long required = (long) a.length + b.length - 1;
        if (required > MAX_SIZE) {
            throw new IllegalArgumentException(
                    "convolution needs NTT length beyond 2^23");
        }
        int n = 1;
        while (n < required) n <<= 1;

        int[] fa = new int[n];
        int[] fb = new int[n];
        for (int i = 0; i < a.length; i++) {
            fa[i] = (int) Math.floorMod(a[i], (long) MOD);
        }
        for (int i = 0; i < b.length; i++) {
            fb[i] = (int) Math.floorMod(b[i], (long) MOD);
        }

        transform(fa, false);
        transform(fb, false);
        for (int i = 0; i < n; i++) {
            fa[i] = (int) ((long) fa[i] * fb[i] % MOD);
        }
        transform(fa, true);
        return Arrays.copyOf(fa, (int) required);
    }

    private static int[] schoolbookOracle(long[] a, long[] b) {
        if (a.length == 0 || b.length == 0) return new int[0];
        int[] result = new int[a.length + b.length - 1];
        for (int i = 0; i < a.length; i++) {
            long x = Math.floorMod(a[i], (long) MOD);
            for (int j = 0; j < b.length; j++) {
                long y = Math.floorMod(b[j], (long) MOD);
                long exactWithinLong = result[i + j] + x * y;
                result[i + j] = (int) (exactWithinLong % MOD);
            }
        }
        return result;
    }

    private static void checkConvolution(long[] a, long[] b) {
        int[] actual = convolution(a, b);
        int[] expected = schoolbookOracle(a, b);
        if (!Arrays.equals(actual, expected)) {
            throw new AssertionError("convolution mismatch: a="
                    + Arrays.toString(a) + " b=" + Arrays.toString(b)
                    + " actual=" + Arrays.toString(actual)
                    + " expected=" + Arrays.toString(expected));
        }
        for (int value : actual) {
            if (value < 0 || value >= MOD) {
                throw new AssertionError("coefficient not normalized");
            }
        }
    }

    private static long[] ternaryArray(int code, int length) {
        long[] values = {-1, 0, 2};
        long[] result = new long[length];
        for (int i = 0; i < length; i++) {
            result[i] = values[code % 3];
            code /= 3;
        }
        return result;
    }

    private static int[] directDft(int[] input, boolean inverse) {
        int n = input.length;
        long omega = modPow(GENERATOR, (MOD - 1L) / n);
        if (inverse) omega = modPow(omega, MOD - 2L);
        long invN = inverse ? modPow(n, MOD - 2L) : 1;
        int[] output = new int[n];
        for (int k = 0; k < n; k++) {
            long total = 0;
            for (int j = 0; j < n; j++) {
                long exponent = ((long) j * k) % n;
                long term = input[j] * modPow(omega, exponent) % MOD;
                total = (total + term) % MOD;
            }
            output[k] = (int) (total * invN % MOD);
        }
        return output;
    }

    private static void checkPrimitiveRoots() {
        if (MOD - 1L != 119L * (1L << MAX_LOG)) {
            throw new AssertionError("wrong modulus factorization");
        }
        if (modPow(GENERATOR, MOD - 1L) != 1) {
            throw new AssertionError("generator not in group");
        }
        for (int primeDivisor : new int[] {2, 7, 17}) {
            if (modPow(GENERATOR, (MOD - 1L) / primeDivisor) == 1) {
                throw new AssertionError("generator not primitive");
            }
        }
        for (int log = 0; log <= MAX_LOG; log++) {
            int n = 1 << log;
            long omega = modPow(GENERATOR, (MOD - 1L) / n);
            if (modPow(omega, n) != 1
                    || (n > 1 && modPow(omega, n / 2) == 1)) {
                throw new AssertionError("root has wrong order: n=" + n);
            }
        }
        if ((1_000_000_007 - 1) % 8 == 0) {
            throw new AssertionError("unexpected 8th root over 1e9+7");
        }
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    private static void verify() {
        checkPrimitiveRoots();

        List<long[]> vectors = new ArrayList<>();
        for (int length = 0; length <= 4; length++) {
            int cases = 1;
            for (int i = 0; i < length; i++) cases *= 3;
            for (int code = 0; code < cases; code++) {
                vectors.add(ternaryArray(code, length));
            }
        }
        int exhaustive = 0;
        for (long[] a : vectors) {
            for (long[] b : vectors) {
                checkConvolution(a, b);
                exhaustive++;
            }
        }

        Random random = new Random(4142026L);
        int seeded = 0;
        for (int trial = 0; trial < 1500; trial++) {
            long[] a = new long[random.nextInt(61)];
            long[] b = new long[random.nextInt(61)];
            for (int i = 0; i < a.length; i++) a[i] = random.nextLong();
            for (int j = 0; j < b.length; j++) b[j] = random.nextLong();
            checkConvolution(a, b);
            seeded++;
        }

        int directChecks = 0;
        for (int n = 1; n <= 16; n <<= 1) {
            for (int trial = 0; trial < 100; trial++) {
                int[] array = new int[n];
                for (int i = 0; i < n; i++) {
                    array[i] = random.nextInt(MOD);
                }
                int[] transformed = array.clone();
                transform(transformed, false);
                if (!Arrays.equals(transformed, directDft(array, false))) {
                    throw new AssertionError("forward NTT disagrees with DFT");
                }
                int[] restored = transformed.clone();
                transform(restored, true);
                if (!Arrays.equals(restored, array)
                        || !Arrays.equals(restored,
                                          directDft(transformed, true))) {
                    throw new AssertionError("inverse NTT disagrees with DFT");
                }
                directChecks++;
            }
        }

        checkConvolution(new long[] {Long.MIN_VALUE, Long.MAX_VALUE},
                         new long[] {Long.MAX_VALUE, Long.MIN_VALUE});
        checkConvolution(new long[] {MOD - 1L, MOD - 1L},
                         new long[] {MOD - 1L, MOD - 1L});
        checkConvolution(new long[] {1, 2, 3}, new long[] {4, 5});
        checkConvolution(new long[0], new long[] {1});
        expectInvalid(() -> convolution(null, new long[] {1}));
        expectInvalid(() -> convolution(new long[] {1}, null));
        expectInvalid(() -> transform(new int[0], false));
        expectInvalid(() -> transform(new int[3], false));

        System.out.println("Primitive root and 2^0..2^23 orders: PASS");
        System.out.println("Exhaustive polynomial pairs: "
                           + exhaustive + " PASS");
        System.out.println("Seeded polynomial pairs: "
                           + seeded + " PASS");
        System.out.println("Direct DFT and inverse checks: "
                           + directChecks + " PASS");
        System.out.println("Long extremes and invalid inputs: PASS");
    }

    public static void main(String[] args) {
        System.out.println("Modulus: " + MOD);
        System.out.println("MOD-1 = 119 * 2^23: "
                           + (MOD - 1L == 119L * (1L << MAX_LOG)));
        System.out.println("Convolution [1,2,3] x [4,5]: "
                + Arrays.toString(convolution(
                        new long[] {1, 2, 3}, new long[] {4, 5})));
        System.out.println("Negative convolution: "
                + Arrays.toString(convolution(
                        new long[] {1, -2, 3}, new long[] {-4, 5})));
        int[] example = {1, 2, 3, 4};
        transform(example, false);
        System.out.println("NTT of [1,2,3,4]: "
                           + Arrays.toString(example));
        transform(example, true);
        System.out.println("Inverse restores: "
                           + Arrays.toString(example));
        System.out.println("Max supported transform length: " + MAX_SIZE);
        verify();
    }
~~~

Lưu mã vào **NttRootsLesson.java**, rồi chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac NttRootsLesson.java
java NttRootsLesson
~~~

**Stdout chính xác từ lần chạy kiểm thử:**

~~~text
Modulus: 998244353
MOD-1 = 119 * 2^23: true
Convolution [1,2,3] x [4,5]: [4, 13, 22, 15]
Negative convolution: [998244349, 13, 998244331, 15]
NTT of [1,2,3,4]: [10, 173167434, 998244351, 825076915]
Inverse restores: [1, 2, 3, 4]
Max supported transform length: 8388608
Primitive root and 2^0..2^23 orders: PASS
Exhaustive polynomial pairs: 14641 PASS
Seeded polynomial pairs: 1500 PASS
Direct DFT and inverse checks: 500 PASS
Long extremes and invalid inputs: PASS
~~~

Hai dòng NTT thuận [1,2,3,4] và NTT nghịch khôi phục là minh chứng trực tiếp cho phép biến đổi khả nghịch. Các dòng PASS được in sau khi những phép kiểm tra tương ứng đã chạy; nếu sai, chương trình ném AssertionError.

## 22. Kiểm thử vét cạn 14.641 cặp đa thức

Mã sinh tất cả mảng hệ số theo bảng giá trị:

~~~text
alphabet = {-1,0,2}.
độ dài = 0..4.
~~~

Số mảng khác nhau:

~~~text
3^0 + 3^1 + 3^2 + 3^3 + 3^4
 = 1+3+9+27+81
 = 121.
~~~

Chọn mọi cặp có thứ tự giữa hai tập mảng, tổng:

~~~text
121*121 = 14641 cặp đa thức.
~~~

Mỗi cặp được nhân theo hai cách: NTT và schoolbook O(nm) độc lập. Danh sách hệ số phải bằng nhau **đúng từng ô**, không chỉ có cùng tổng, cùng checksum hay có số phần tử tương đương.

Tập vét cạn chứa đa thức rỗng, một hệ số, toàn 0, nhiều hệ số âm, tích có nhiều lần cộng vào cùng c[k] và các độ dài NTT nhỏ 1,2,4,8. Đây là cách phát hiện sai padding, butterfly, căn nghịch đảo hoặc cắt length.

## 23. Kiểm thử 1.500 cặp có seed và giá trị 64-bit

Chương trình dùng Random(4142026L) để tạo **1.500** cặp mảng:

~~~text
length(a), length(b) được chọn từ 0..60.
a[i], b[j] = random.nextLong().
~~~

Nội dung có thể chứa cả số âm/dương rất lớn; các hệ số được chuẩn hóa modulo trước khi NTT. Oracle schoolbook cũng chuẩn hóa độc lập và cộng/tích với miền số được chứng minh an toàn cho môđun cố định.

Ngoài các cặp random, mã thử riêng:

~~~text
[Long.MIN_VALUE,Long.MAX_VALUE]
  nhân
[Long.MAX_VALUE,Long.MIN_VALUE];

[MOD−1,MOD−1] nhân [MOD−1,MOD−1];

[1,2,3] nhân [4,5].
~~~

Bộ kiểm thử đảm bảo không âm thầm dùng trực tiếp phép nhân hai hệ số long rất lớn ở lõi tính tích chập. Các kết quả NTT phải nằm trong [0,MOD).

## 24. Kiểm tra NTT với DFT định nghĩa độc lập

So NTT với schoolbook chỉ kiểm chứng **tích chập**, nhưng chưa trực tiếp xác nhận NTT thuận/nghịch đã khớp công thức DFT. Do đó mã bổ sung phép thử **directDft**:

~~~text
Dãy đầu vào ngẫu nhiên đã chuẩn hóa.
Tính transform(...,false).
Tính DFT trực tiếp bằng tổng Σ a[j]*ω^(j*k).
So từng phần tử.

Tính transform(...,true) trên ảnh NTT.
So với dãy ban đầu.
So tiếp với công thức inverse DFT trực tiếp.
~~~

Độ dài N=1,2,4,8,16. Với **100 dãy cho mỗi N**, có 5·100=**500 lượt đối chiếu**; mỗi lượt kiểm tra cả chiều thuận lẫn nghịch.

Nhờ có hai oracle khác kiểu (schoolbook tích chập và direct DFT O(N²)), những lỗi đảo bit, thiếu n^(-1), dùng sai ω ở tầng hoặc sai quy ước dấu có nhiều cơ hội bị phát hiện.

## 25. Điều kiện để nhân đa thức chính xác trên số nguyên

NTT với một môđun p chỉ biết từng hệ số c[k] **modulo p**. Nếu c[k] nguyên có thể lớn hơn p, thông tin một modulo **không đủ** để phân biệt c[k], c[k]+p, c[k]−p,...

Muốn khôi phục hệ số nguyên chính xác, có thể dùng **nhiều môđun nguyên tố thân thiện NTT** p1,p2,...,pr sao cho đôi một nguyên tố cùng nhau, rồi kết hợp phần dư bằng **Chinese Remainder Theorem (CRT)**. Đặt:

~~~text
M = p1*p2*...*pr.
~~~

CRT khôi phục duy nhất một lớp đồng dư modulo M. Nếu hệ số thật **không âm** và có cận 0≤c[k]<M, ta xác định được đúng c[k]. Nếu hệ số có dấu và biết |c[k]|≤B, cần **M>2B** để chọn đại diện có dấu duy nhất trong khoảng [−B,B].

Một cận đủ cho |c[k]| là:

~~~text
B <= min(length(a),length(b))
     * maxAbs(a)
     * maxAbs(b).
~~~

Đây là cận trên thô, có thể tính bằng BigInteger nếu hệ số gần Long.MIN_VALUE/Long.MAX_VALUE để tránh tràn khi ước lượng B. Mọi môđun trong CRT phải **tự hỗ trợ độ dài biến đổi N đã chọn**, chứ không thể lấy bất kỳ vài số nguyên tố rồi mặc định NTT cùng N đều hợp lệ.

Bài hiện tại **không cài CRT**: kết quả API được nêu rõ là tích chập **modulo 998244353**. Khi yêu cầu xuất hệ số nguyên chính xác, cần bổ sung CRT hoặc dùng một thuật toán số nguyên lớn tương ứng.

## 26. So sánh NTT với FFT

| Tiêu chí | FFT số phức | NTT trên F_p |
| --- | --- | --- |
| Giá trị tính toán | Số thực/số phức | Phần dư trong trường hữu hạn |
| Vấn đề sai số | Sai số làm tròn khi dùng floating point | Chính xác modulo p khi thao tác nguyên không tràn |
| Điểm biến đổi | Căn đơn vị phức | Căn đơn vị có bậc đúng N modulo p |
| Điều kiện N radix-2 | Dùng căn phức cho 2^k | Phải có 2^k | (p−1) |
| Kết quả tích chập | Thường cần làm tròn/kiểm soát lỗi | Kết quả modulo p chính xác |
| Khôi phục số nguyên lớn | Cần kiểm soát độ chính xác | CRT với nhiều modulus và cận hệ số |
| Cài đặt radix-2 | Butterfly cộng/trừ/nhân phức | Butterfly cộng/trừ/nhân modulo |

Không nên kết luận NTT luôn nhanh hơn FFT: tốc độ thực tế phụ thuộc cài đặt, phần cứng, kiểu dữ liệu, phương pháp nhân modulo và kích thước. Lợi thế quan trọng của NTT trong bài lập trình là **không có sai số floating point của phép biến đổi**, nhưng có ràng buộc đại số về môđun và độ dài.

## 27. Các lỗi triển khai phổ biến

1. **Dùng môđun nguyên tố bất kỳ**, không kiểm tra N | (p−1).
2. **Chọn ω=1** vì thấy ω^N=1, bỏ qua điều kiện **bậc đúng N**.
3. **Nhầm phần tử sinh g với căn ω_N**: g thường có bậc p−1, không phải N.
4. **Không phân tích p−1** khi chứng minh g là phần tử sinh.
5. **Dùng p=1.000.000.007 cho radix-2 N=8**, dù p−1 chỉ chia hết cho 2.
6. **Coi một số có bậc N trong môđun hợp số là đủ**, không kiểm tra tính trực giao/principal root.
7. **Không nhân N^(-1) khi inverse NTT**, kết quả bị nhân N.
8. **Dùng ω cùng chiều ở forward và inverse**, không đổi sang ω^(-1).
9. **Không đệm tới N≥lenA+lenB−1**, nhận tích chập quấn vòng.
10. **Dùng N không là lũy thừa của 2** trong mã radix-2 đang học.
11. **Vượt 2^23 với môđun 998244353**, thiếu căn bậc N cần thiết.
12. **Bỏ bit-reversal** khi dùng vòng butterfly DIT in-place như trong mã.
13. **Sai twiddle factor ở từng tầng len**, dùng căn bậc N thay vì căn bậc len mà không điều chỉnh số mũ.
14. **Nhân hai int rồi lấy %MOD**, tích int đã tràn.
15. **Thay MOD bằng số lớn hơn mà không tính lại an toàn int sum**, gây tràn cộng.
16. **Không chuẩn hóa hệ số âm** trước khi dùng butterfly.
17. **Cho rằng NTT trả hệ số nguyên âm/gốc**, dù kết quả đang ở [0,p).
18. **Không kiểm tra độ dài trước khi cấp phát**, gây lỗi kích thước hoặc độ dài không hợp lệ.
19. **Đổi dấu trực tiếp của Long.MIN_VALUE**, làm tràn trước khi mod.
20. **Chỉ so tổng hệ số** khi test convolution, bỏ qua lỗi vị trí c[k].
21. **Chỉ test tích chập mà không test DFT thuận/nghịch**, thiếu một lớp oracle độc lập.
22. **Lấy một modulo làm đủ cho tích chập nguyên không giới hạn**, không có cận CRT.
23. **Suy diễn phép chia modulo luôn hợp lệ**, dù n hoặc mẫu số có thể không khả nghịch.
24. **Nhầm convolution tuyến tính và tuần hoàn**; hai bài có yêu cầu padding khác nhau.
25. **Khẳng định bộ nhớ luôn nhỏ**, quên rằng n=2^23 cần nhiều mảng dài hàng triệu phần tử.
26. **Không nêu quy ước đa thức rỗng**, dẫn đến công thức n+m−1 âm hoặc khó hiểu.

## 28. Bài tập và hướng nghiên cứu

**Bài 1 — Chọn môđun:** tính v2(p−1) của p=17, p=998244353 và p=1.000.000.007; kết luận NTT radix-2 tối đa của mỗi môđun.

**Bài 2 — Bậc căn:** với p=17,g=3,n=8, tính ω=9, kiểm tra ω^8=1 và ω^4≠1; vì sao ω=1 không thể dùng?

**Bài 3 — Sinh ω từ g:** chứng minh nếu g có bậc p−1 và n chia p−1 thì g^((p−1)/n) có bậc n.

**Bài 4 — Test phần tử sinh:** phân tích 998244352 thành thừa số nguyên tố, giải thích vì sao chỉ kiểm tra các số mũ (p−1)/2, (p−1)/7 và (p−1)/17.

**Bài 5 — DFT tay:** với modulo 17, n=4, căn ω=13, tính DFT của [1,2,3,4] và kiểm tra [10,6,15,7].

**Bài 6 — Inverse:** chứng minh tổng Σω^(k·d) bằng N khi d≡0(mod N) và bằng 0 ở trường hợp khác, rồi suy ra công thức NTT nghịch.

**Bài 7 — Butterfly:** viết các cặp chỉ số được ghép khi N=8 và len=2,4,8; tính số butterfly mỗi tầng.

**Bài 8 — Bit reversal:** liệt kê hoán vị đảo 3 bit cho các chỉ số 0..7; so với bảng ở mục 17.

**Bài 9 — Padding:** nhân [1,2,3] với [4,5]. Vì sao N=4 đủ còn N=2 không đủ? Nêu hệ quả của modulo x^N−1.

**Bài 10 — Hệ số âm:** nhân [1,−2,3] và [−4,5], kiểm tra kết quả integer [−4,13,−22,15] và phần dư NTT [998244349,13,998244331,15].

**Bài 11 — Vét cạn:** sinh mọi mảng dài 0..4 với hệ số −1,0,2 rồi so NTT với schoolbook; tự suy ra 14.641 cặp.

**Bài 12 — DFT độc lập:** viết công thức O(N²) để so biến đổi thuận/nghịch với butterfly trên N=1,2,4,8,16. Vì sao test cả hai chiều cần thiết?

**Bài 13 — CRT:** giả sử c[k] có dấu và |c[k]|≤B. Chứng minh M>2B đủ để khôi phục duy nhất từ CRT; giải thích vì sao phải biết các modulus đều hỗ trợ độ dài N.

**Bài 14 — Môđun hợp số:** với m=15, z=4, chứng minh z có bậc 2 nhưng 1+z≠0 modulo 15. Bài học này phá giả định nào của inverse NTT?

**Bài 15 — Hiệu năng:** đo thời gian schoolbook và NTT trên nhiều kích thước, gồm input rất nhỏ. Giải thích vì sao overhead tiền xử lý/biến đổi có thể khiến NTT chậm hơn ở n nhỏ.

**Kết luận:** **NTT không chỉ là FFT thay số phức bằng phép %**. Nền tảng của NTT là trường hữu hạn, căn đơn vị có **đúng bậc N**, và nghịch đảo của N. Với p=998244353, g=3 và N=2^k≤2^23, các điều kiện này được đáp ứng; ta có thể dùng butterfly radix-2, đảo bit và biến đổi ngược để nhân đa thức **O(N log N)** chính xác modulo p. Khi chọn môđun khác phải kiểm tra lại n | (p−1), căn và phép nghịch đảo; khi cần hệ số nguyên chính xác ngoài phạm vi một modulo cần CRT với cận hệ số rõ ràng.
