# Tính xác định và ảnh hưởng của thứ tự phép toán số thực

## 1. Tại sao một thuật toán song song có thể ra hai kết quả khác nhau?

Trong toán học, tổng của một dãy số thực không đổi nếu ta hoán vị các phần tử hoặc đổi cách đặt dấu ngoặc. Trong máy tính, kiểu `double` chỉ lưu được tập hữu hạn các giá trị. Sau mỗi phép cộng, kết quả thường được **làm tròn**, và một phần chữ số thấp có thể bị mất. Do đó, **đổi thứ tự cộng có thể làm đổi kết quả**, ngay cả khi không có lỗi đồng thời.

Khi chạy song song, chương trình thường:

1. Chia dữ liệu thành các khối hoặc nhóm.
2. Giao khối cho các worker.
3. Tính một tổng cục bộ trên từng worker.
4. Ghép các tổng cục bộ thành kết quả cuối.

Nếu ranh giới khối hoặc thứ tự ghép đổi theo scheduler, số worker, backend hay chế độ tối ưu, kết quả `double` có thể khác vài bit hoặc khác nhiều hơn với dữ liệu triệt tiêu mạnh. Điều này có ý nghĩa với tính tổng thống kê, tích vô hướng, mô phỏng, machine learning, xử lý dữ liệu phân tán và các pipeline cần kiểm chứng kết quả.

Bài này tách ba yêu cầu:

- **Tính xác định / reproducibility:** cùng input, cùng hợp đồng tính toán có cho **cùng bit** giữa các lần chạy không?
- **Độ chính xác số học / numerical accuracy:** kết quả lệch giá trị tổng toán học đến mức nào?
- **Đúng đắn đồng thời / race freedom:** có đủ mọi đóng góp, không mất update, không data race?

Một chương trình hoàn toàn **race-free** vẫn có thể cho kết quả khác bit nếu thứ tự các phép cộng khác. Một chương trình **tái lập được** vẫn có thể lặp lại cùng một kết quả sai lệch đáng kể. Không thể dùng một trong ba tính chất để khẳng định hai tính chất còn lại.

## 2. IEEE 754 binary64 và làm tròn

Trong Java, `double` dùng biểu diễn IEEE 754 binary64: 1 bit dấu, 11 bit số mũ và 52 bit fraction, với 53 bit có nghĩa đối với số normal. Độ chính xác tương ứng khoảng 15–17 chữ số thập phân. Số đặc biệt bao gồm +0, -0, +Infinity, -Infinity, NaN và số subnormal gần 0.

Một phép cộng hai operand `double` được làm tròn về một giá trị binary64 biểu diễn được. Chế độ mặc định dùng **round-to-nearest, ties-to-even**. Có thể mô tả:

**fl(a+b) = làm tròn về binary64 của giá trị toán học a+b**,

với các quy tắc riêng cho các giá trị đặc biệt, overflow và underflow.

Đặt **u=2^(-53)≈1,11×10^(-16)** là unit roundoff trong phân tích sai số relative của binary64 dưới các giả thiết phù hợp. Không nhầm u với `Double.MIN_VALUE`: hằng này là số dương subnormal nhỏ nhất, không phải sai số tương đối máy.

### 2.1. Vì sao 0,1+0,2 khác 0,3?

Nhiều phân số thập phân có biểu diễn nhị phân vô hạn. Java làm tròn literal `0.1`, `0.2`, `0.3` thành các double khác nhau. Kết quả của phép cộng trên các giá trị ấy có thể không bằng bit với literal 0.3:

```java
System.out.println(0.1 + 0.2 == 0.3); // false
```

Không có thread nào ở đây; tính sai khác xảy ra ngay trong phép toán tuần tự.

### 2.2. Phép cộng máy không kết hợp

Theo số thực toán học:

**(a+b)+c = a+(b+c)**.

Nhưng phép cộng floating-point thực thi:

**fl(fl(a+b)+c)** và **fl(a+fl(b+c))**

có thể khác nhau.

Lấy **a=10¹⁶, b=−10¹⁶, c=1**. Các số ±10¹⁶ và 1 đều biểu diễn chính xác trong binary64, nhưng `−10¹⁶+1` bị làm tròn trở lại −10¹⁶. Do đó:

```text
(a+b)+c = (10^16−10^16)+1 = 1
a+(b+c) = 10^16 + (−10^16+1)
        = 10^16 + (−10^16) = 0
```

Hai kết quả đều tuân thủ ngữ nghĩa `double` nhưng **khác bit**. Đây là thuộc tính số học, không phải bug của trình biên dịch.

## 3. Một ví dụ có thể kiểm tra bằng tay

Xét dãy đầu vào cố định:

**[10¹⁶, 1, −10¹⁶, 1]**.

Tổng toán học chính xác là **2**. Kết quả bằng `double` tùy cách cộng:

| Quy tắc | Biểu diễn | Kết quả |
|---|---|---:|
| Forward | Cộng từ trái qua phải, accumulator khởi tạo 0 | 1 |
| Reverse | Cộng từ phải qua trái, accumulator khởi tạo 0 | 0 |
| Fixed pairwise | (x₀+x₁)+(x₂+x₃) | 0 |
| Kahan thông thường | Sequential compensated sum | 1 |
| Neumaier | Sequential compensated sum có xử lý triệt tiêu | 2 |
| Tham chiếu chính xác | Tổng đúng của các operand binary64 | 2 |

**Forward:** 10¹⁶+1 bị làm tròn thành 10¹⁶; cộng −10¹⁶ thành 0; cộng 1 thành **1**.

**Reverse:** 1+(−10¹⁶) bị làm tròn thành −10¹⁶; cộng 1 vẫn −10¹⁶; cộng 10¹⁶ thành **0**.

**Pairwise:** từng cặp (10¹⁶+1) và (−10¹⁶+1) làm tròn thành ±10¹⁶, cộng nhau thành **0**.

**Neumaier:** ghi lại những đóng góp nhỏ vào compensation, cho **2** trong ví dụ này. Không được suy rộng từ một ví dụ thành bảo đảm Neumaier luôn tính chính xác tuyệt đối.

### 3.1. Kết quả tái lập có thể sai lệch

Nếu luôn cố định cây pairwise trên dãy này, kết quả 0 là **tất định**; nhưng nó không bằng tổng lý tưởng 2. Nếu một thuật toán đưa ra 2 trên dãy này nhờ compensation, nó chính xác hơn cho **ví dụ này**, nhưng phải tiếp tục phân tích tính tái lập khi cấu trúc parallel reduction đổi.

Mọi đánh giá nên báo riêng: cấu trúc gộp, tổng đối chiếu, sai số tuyệt đối, sai số tương đối khi tổng thật khác 0, và tính giống nhau tới từng bit qua các lần chạy.

## 4. Vì sao thứ tự phép toán thay đổi khi chạy song song?

Một phép reduction chia input thành các phần, mỗi worker tính tổng cục bộ rồi reducer gộp:

```text
Input: x0 x1 x2 x3 x4 x5 x6 x7

Worker 0: (x0+x1) => s0
Worker 1: (x2+x3) => s1
Worker 2: (x4+x5) => s2
Worker 3: (x6+x7) => s3

Tree A: (s0+s1)+(s2+s3)
Tree B: ((s0+s2)+s1)+s3
Tree C: s0+(s1+(s2+s3))
```

Trên số thực, mọi cây cho cùng tổng. Trên binary64, từng cây có những điểm làm tròn khác nhau.

Nguyên nhân thực tế gồm:

- **Partition:** chia block theo số worker 2, 4 hay 8 dẫn tới các tổng cục bộ khác.
- **Work stealing:** task có thể bị gom hoặc hoàn tất theo trình tự khác.
- **Completion order:** reducer cộng partial ngay khi task hoàn thành thay vì theo index input.
- **Tree shape:** framework MapReduce/SQL/parallel stream hoặc GPU đổi cấu trúc cây reduction.
- **SIMD, fused operations:** tính tích vô hướng hoặc các biểu thức nhân-cộng với vectorization/FMA có thể thay đổi rounding.
- **Backend:** CPU/GPU/native BLAS và thư viện khác có chiến lược kernel khác.
- **Dữ liệu:** thứ tự input từ HashMap hoặc nguồn dữ liệu phân tán có thể không được bảo đảm ổn định nếu không có sort/key quy định.

Để kiểm lỗi, đừng giả định cứ kết quả khác bit là có data race; có thể tất cả operand đã được xử lý đúng nhưng thứ tự cộng khác.

### 4.1. Race freedom khác reproducibility

Dùng `synchronized` để bảo vệ một biến tổng tránh hai thread ghi đè nhau, nhưng **thứ tự vào critical section** vẫn có thể đổi. Kết quả không nhất thiết bitwise reproducible.

Dùng mỗi worker một subtotal và chờ mọi Future giúp tránh lost updates. Nhưng nếu nhận các Future theo **thứ tự hoàn thành** rồi cộng vào accumulator, thứ tự vẫn phụ thuộc scheduling.

Bảo đảm tốt hơn là **đặt kết quả của block j vào partials[j]** bất kể worker nào chạy, rồi gộp theo cấu trúc cố định.

## 5. Java Stream API và yêu cầu kết hợp

Một biểu thức hợp lệ với parallel stream:

```java
double sum = java.util.Arrays.stream(values)
    .parallel()
    .reduce(0.0, Double::sum);
```

Hợp đồng khái quát của `reduce` song song cần hàm kết hợp có tính **associative** và identity thích hợp. Cộng binary64 **không associative trên tất cả các đầu vào**. Vì vậy phép reduce số thực ở trên không được coi là lời hứa luôn có cùng bit như vòng cộng sequential hoặc mọi kế hoạch partition khác.

`DoubleStream.sum()` thường có kỹ thuật **compensated summation** nhằm cải thiện độ chính xác, nhưng điều đó **không** tự đặt ra một thứ tự reduction bitwise cố định giữa mọi chế độ chạy. Tính chất encounter order của stream không đồng nghĩa thứ tự thực thi các phép cộng giống nhau.

Nếu yêu cầu chỉ là sai số nhỏ, có thể sử dụng các API tính tổng phù hợp rồi kiểm tolerance; nếu yêu cầu cùng bit giữa số worker khác nhau, cần mô tả và điều khiển **thứ tự số học** cụ thể.

## 6. Thiết kế fixed-block reproducible reduction

Ý tưởng: **cố định cách chia khối theo index**, không theo số worker, và **cố định thứ tự ghép**:

1. Chọn block size b≥1 như một tham số của thuật toán.
2. Tạo các khối [0,b), [b,2b), …, đoạn cuối có thể ngắn hơn.
3. Mỗi task cộng tuần tự các phần tử của **chính khối đó theo thứ tự tăng chỉ số**.
4. Mỗi task không ghi vào accumulator global.
5. Lưu Future theo thứ tự submit, sau khi hoàn thành lấy subtotal của block j vào đúng `partials[j]`.
6. Gộp partials bằng cây nhị phân **chia đôi ở midpoint** đã quy định sẵn.

```text
block size = 2:
partials[0] = fl(x0+x1)
partials[1] = fl(x2+x3)
partials[2] = fl(x4+x5)
partials[3] = fl(x6+x7)

result = fl(fl(partials[0]+partials[1])
            +fl(partials[2]+partials[3]))

Các task có thể hoàn thành theo thứ tự 2,0,3,1.
Vị trí partials[] vẫn được ghép theo block index 0,1,2,3.
```

### 6.1. Chứng minh độc lập số worker

**Giả thiết:** cùng mảng input về giá trị bit, input không bị mutation trong lúc đọc, block size và phiên bản code cố định, các phép cộng `double` dùng cùng quy tắc rounding và xử lý giá trị đặc biệt.

- Ranh giới khối chỉ phụ thuộc n và b, không phụ thuộc worker.
- Phép cộng trong mỗi khối diễn ra theo đúng index tăng dần, nên subtotal từng khối là xác định.
- Future lưu trong danh sách theo thứ tự block index; kết quả đặt vào đúng vị trí, không phải completion order.
- Cây pairwise chia ở midpoint có cấu trúc xác định từ số block; nếu các lá trùng bit thì từng nút trong cũng trùng bit theo quy nạp.

Vậy thay số worker 1→2→4 mà không đổi b **không đổi cấu trúc số học**, và kết quả tái lập theo bit trong những giả thiết ấy.

**Giới hạn quan trọng:** nếu đổi b từ 2 sang 4 thì partial sums đổi. Với dãy [10¹⁶,1,−10¹⁶,1], block 2 tạo hai tổng ±10¹⁶ rồi gộp cho 0; block 4 cộng tuần tự cả bốn số cho 1. Dù chỉ một worker, thay b vẫn thay kết quả.

### 6.2. Đừng gộp theo thời điểm hoàn thành

Cho ba subtotal [10¹⁶, −10¹⁶, 1]. Gộp thứ tự 0→1→2 được 1. Gộp 0→2→1 được 0. Cả hai đều cộng đủ ba giá trị và có thể được synchronized đúng, nhưng kết quả khác. **Race-free không đảm bảo numerical deterministic**.

### 6.3. Độ phức tạp

Với n phần tử, b là block size và q=ceil(n/b):

- Tổng work các block: O(n).
- Gộp cây: O(q) work.
- Bộ nhớ partials: O(q), thêm overhead Future/task; stack pairwise O(log q).
- Với đủ worker và bỏ qua overhead, độ sâu lý tưởng khoảng O(b+log q). Trên p worker, thời gian còn chịu cận Ω(n/p).
- b quá nhỏ: overhead scheduling cao; b quá lớn: ít task, khó song song hóa.

Cài đặt Java trong bài dùng gộp cây **tuần tự** ở bước cuối để cấu trúc rõ ràng. Có thể song song hóa cây này, nhưng cần cố định quan hệ cha-con và thứ tự hai operand cho mỗi phép cộng nếu muốn hợp đồng reproducibility.

## 7. Pairwise summation và giới hạn sai số

Pairwise summation chia dãy làm hai nửa, tính tổng mỗi nửa, rồi cộng kết quả:

```text
pairwise(A,lo,hi):
    nếu hi == lo: return +0.0
    nếu hi == lo+1: return A[lo]
    mid = lo + (hi-lo)/2
    return pairwise(A,lo,mid) + pairwise(A,mid,hi)
```

Với cây cân bằng, chiều cao O(log n), work O(n), stack O(log n). Khi độ dài input không là lũy thừa 2, chia midpoint vẫn cố định.

Một cận sai số tuyệt đối quen thuộc cho cộng tuần tự trong mô hình làm tròn chuẩn (không overflow/underflow bất thường, \(ku<1\)) là:

**|computedSum−exactSum| ≤ γ_(n−1)·sum(|x_i|)**,

với **γ_k=ku/(1−ku)** và u là unit roundoff. Với cây pairwise, số mức làm tròn tác động lên một số hạng chỉ O(log n), nên có các cận dựa vào γ tại độ sâu cây trong điều kiện tương ứng.

**Không** suy ra pairwise tốt hơn trên từng input. Ở dãy bốn số mục 3, pairwise trả 0 trong khi forward trả 1 và Neumaier trả 2.

### 7.1. Sai số tương đối và condition number

Nếu S là tổng chính xác của các operand, error tuyệt đối là |computed−S|. Error tương đối là |computed−S|/|S| nếu S≠0. Khi S=0, tỷ lệ tương đối **không định nghĩa**.

Một thước đo độ nhạy của phép tổng là \(κ=\sum|x_i|/|\sum x_i|\) khi mẫu khác 0. Nếu nhiều số lớn trái dấu triệt tiêu, κ lớn và error tương đối có thể tăng rất mạnh. Các dãy [10¹⁶,1,−10¹⁶,1] là ví dụ có tính triệt tiêu đáng kể.

Không dùng kiểm epsilon tuyệt đối duy nhất cho mọi scale; cần kết hợp error tuyệt đối, tương đối, ULP hoặc chính sách ứng dụng. So sánh số học gần nhau không đồng nghĩa so **raw bits**.

## 8. Kahan compensated summation

Kahan giữ một biến bù c nhằm theo dõi một phần sai số làm tròn bị mất khi cộng:

```text
sum = 0
c = 0
for x theo thứ tự:
    y = x - c
    t = sum + y
    c = (t - sum) - y
    sum = t
return sum
```

Trực giác: khi một số rất nhỏ không thay đổi giá trị sum lớn, c giúp đưa phần bị mất vào phép cộng tiếp theo. Kahan thường cải thiện tính ổn định nhưng **không exact trong mọi trường hợp**.

Với [10¹⁶,1,−10¹⁶,1] ở thứ tự đã nêu, Kahan thông thường cho **1**, không phải tổng lý tưởng 2. Vì vậy không nên nói Kahan luôn giải quyết triệt tiêu. Bản thân trạng thái Kahan phải được cập nhật theo **thứ tự xác định**, và việc gộp các trạng thái Kahan riêng lẻ cần một quy tắc được chứng minh nếu chạy song song.

## 9. Neumaier compensated summation

Neumaier bổ sung một cách xử lý tốt hơn cho những số có độ lớn đảo chiều:

```text
sum = 0
correction = 0
for x:
    t = sum + x
    if abs(sum) >= abs(x):
        correction += (sum - t) + x
    else:
        correction += (x - t) + sum
    sum = t
return sum + correction
```

Trên cùng dãy bốn số, phần bù giữ được hai số 1 bị mất và cho **2**.

**Không mặc định Neumaier luôn đúng tuyệt đối:** correction vẫn là `double` và có thể làm tròn, overflow, underflow. Với dữ liệu khác, cần đánh giá bằng oracle chính xác. Neumaier cũng không tự làm kết quả độc lập thứ tự nếu ta xáo input hoặc thay cách merge giữa các worker.

Có thể tính compensated subtotal trong mỗi block cố định rồi gộp partial theo cây cố định; cách đó giúp tính tái lập của **thuật toán cụ thể**, nhưng muốn bảo toàn độ chính xác compensation xuyên các block cần nghiên cứu bộ kết hợp phù hợp, không chỉ cộng các giá trị sum thô.

## 10. BigDecimal để có oracle chính xác

Để đo sai số so với **tổng chính xác của các giá trị binary64 đã nhận**, có thể dùng:

```java
java.math.BigDecimal sum = java.math.BigDecimal.ZERO;
for (double x : values) {
    if (!Double.isFinite(x)) {
        throw new IllegalArgumentException("non-finite");
    }
    sum = sum.add(new java.math.BigDecimal(x));
}
```

`new BigDecimal(double)` biểu diễn đúng giá trị nhị phân hữu hạn của x dưới dạng decimal. `BigDecimal.add` **không truyền MathContext** là phép cộng decimal chính xác, do đó kết quả không phụ thuộc thứ tự cộng theo toán học (trong giới hạn tài nguyên).

**Ba thao tác chuyển đổi có ý nghĩa khác nhau:**

- `new BigDecimal(doubleValue)`: chuyển đúng giá trị binary64 đã được biểu diễn; có thể hiện thêm nhiều chữ số decimal không nhìn thấy trong literal.
- `BigDecimal.valueOf(doubleValue)`: dùng biểu diễn decimal canonical ngắn của double; giá trị decimal có thể không trùng với binary64 rational chính xác.
- `new BigDecimal("0.1")`: ghi chính xác số thập phân 0,1 theo chuỗi; nếu yêu cầu số tiền decimal exact, **đừng parse qua double trước**.

BigDecimal không nhận NaN hoặc Infinity. Nếu mỗi lần add lại có `MathContext` với precision hữu hạn, phép cộng sẽ làm tròn và có thể phụ thuộc thứ tự. Nếu cần tổng của những số thập phân từ dữ liệu nguồn, parse chính **chuỗi nguồn** thay vì đánh giá lại các double đã mất precision.

### 10.1. Exact/binned accumulator

Một **superaccumulator** hoặc các bin chứa tổng chính xác theo số mũ có thể cộng các operand binary64 vào một dạng nguyên chính xác, rồi chỉ làm tròn một lần ở cuối. Với cách merge bin đúng, thứ tự gộp có thể không còn ảnh hưởng kết quả toán học, kể cả khi chạy song song.

Đây là cách mạnh hơn về reproducibility/accuracy nhưng có chi phí bộ nhớ và thời gian riêng; chương trình Java mẫu dưới đây chỉ dùng BigDecimal cho oracle và fixed-block reduction cho reproducibility thực hành.

## 11. ±0, NaN, Infinity, subnormal và overflow

Các giá trị IEEE đặc biệt cần chính sách rõ ràng:

- `+0.0 == -0.0` là true, nhưng `Double.doubleToRawLongBits(+0.0)` khác `Double.doubleToRawLongBits(-0.0)`. Phép chia 1.0/+0.0 và 1.0/−0.0 cho +Infinity và −Infinity.
- `Double.NaN == Double.NaN` là false; dùng `Double.isNaN`. `Double.doubleToLongBits` chuẩn hóa nhiều NaN payload, còn `Double.doubleToRawLongBits` phản ánh raw bits.
- Cộng +Infinity và −Infinity sinh NaN. Với phép toán có NaN payload khác nhau, raw-bit reproducibility còn phụ thuộc chính sách NaN, không chỉ giá trị số học.
- Subnormal rất gần 0 và underflow cần phân tích riêng; cận lỗi tương đối đơn giản có thể không áp dụng nguyên vẹn ở vùng này.
- Một cách nhóm có thể tạo Infinity ở tổng trung gian dù tổng toán học sau triệt tiêu vẫn hữu hạn. Bởi vậy không thể chỉ nhìn tổng lý tưởng để kết luận mọi thứ tự double an toàn.
- `Double.isFinite(x)` giúp giới hạn input khi ứng dụng chỉ cho phép dữ liệu hữu hạn; kết quả intermediate cũng cần kiểm khi miền giá trị lớn.

Trong bài mẫu, input ngẫu nhiên được giới hạn hữu hạn và không gây overflow; phép kiểm bitwise dùng `Double.doubleToRawLongBits`. Nếu ứng dụng cần coi +0/-0 tương đương, phải **chuẩn hóa theo hợp đồng**, không thay đổi tùy ý sau khi đã tạo Golden tests.

## 12. FMA, strictfp và thay đổi backend

`Math.fma(a,b,c)` tính a·b+c và **làm tròn một lần**. Biểu thức `a*b+c` có thể làm tròn sau nhân rồi lại làm tròn sau cộng. Vì vậy hai cách tính có thể cho các bit khác nhau; FMA thường giảm sai số ở nhiều phép toán nhưng là một **thay đổi hợp đồng số học** nếu kết quả cũ phải tái lập.

Java 17 có **always-strict floating-point semantics** theo JEP 306; modifier `strictfp` trở nên không cần thiết để xử lý intermediate precision theo cơ chế Java cũ. Nhưng tính strict không khiến cộng trở thành associative, không buộc mọi parallel stream dùng cùng reduction tree, và không tự kiểm soát mã JNI/native/GPU bên ngoài.

Nếu triển khai GPU, BLAS hoặc một backend có chế độ fast-math, phải chốt phiên bản kernel, chính sách FMA/reassociation, rounding, xử lý subnormal và ý nghĩa kết quả. Không suy từ “cùng thuật toán ở mức source” thành “cùng bit trên mọi phần cứng”.

## 13. Quy trình thiết kế phép tính tái lập

1. **Chốt loại bảo đảm:** bitwise trong một môi trường, cùng kết quả giữa số thread, cùng sai số tolerance, hay exact arithmetic.
2. **Cố định input:** thứ tự, binary representation, data version, parsing/locale, duplicate và đơn vị.
3. **Cố định partition:** block size và ranh giới theo index **độc lập** số worker.
4. **Không ghi shared accumulator:** mỗi task tính subtotal của riêng mình và đọc một snapshot input.
5. **Gắn subtotal với block index:** completion order không được quyết định thứ tự cộng.
6. **Cố định reduction tree:** midpoint, hướng operand, identity cho dãy rỗng.
7. **Chọn thuật toán số học:** forward, pairwise, Kahan, Neumaier, BigDecimal/exact tùy accuracy.
8. **Không trộn số học tùy ý:** FMA và MathContext có thể đổi kết quả.
9. **Tách special cases:** NaN, ±Infinity, ±0 và nguy cơ overflow.
10. **Đối chiếu oracle độc lập:** BigDecimal exact cho binary64 finite hoặc arithmetic exact trên dữ liệu nhỏ.
11. **Kiểm nhiều số worker:** 1,2,4,8 với **cùng block size** và compare raw bits.
12. **Thử dữ liệu đối kháng:** cancellation, số lớn/số nhỏ, n=0, n=1, block không đều.
13. **Đo cả throughput và overhead:** n, block, q=ceil(n/b), số futures, GC, bộ nhớ, span.
14. **Version hóa numerical policy:** đổi b, cây gộp hoặc backend cần cập nhật Golden tests.
15. **Nếu yêu cầu exact hơn nữa:** cân nhắc decimal/fixed-point hoặc superaccumulator.

## 14. Chương trình Java 17 độc lập

Bản Java sau thực hiện tổng theo chiều xuôi/ngược, fixed pairwise, Kahan, Neumaier và exact BigDecimal sum. Điểm chính là hàm `fixedParallel`:

- Chia các khối theo **b cố định**, không theo worker count.
- Submit mỗi khối vào ExecutorService, subtotal cục bộ không ghi shared accumulator.
- Lưu danh sách Future theo thứ tự **block index**.
- Dùng `get()` tuần tự để lắp lại mảng partials đúng index, rồi gộp theo cây pairwise cố định.
- Dùng cùng ba thread pool qua nhiều phép thử, tránh tạo hàng nghìn pool trong vòng lặp.

Bộ kiểm thử ngẫu nhiên sẽ gọi cùng một hàm với pool 1, 2 và 4 worker, so raw bit; ngoài ra kiểm oracle BigDecimal exact trên dãy và đảo dãy để xác nhận tổng tham chiếu **không** phụ thuộc thứ tự.



## 15. Biên dịch, chạy và đọc stdout

Lưu toàn bộ lớp dưới tên `FloatingPointOrderDemo.java`:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class FloatingPointOrderDemo {
    private FloatingPointOrderDemo() {}

    static double forward(double[] a) {
        double sum = 0.0;
        for (double x : a) sum += x;
        return sum;
    }

    static double reverse(double[] a) {
        double sum = 0.0;
        for (int i = a.length - 1; i >= 0; i--) sum += a[i];
        return sum;
    }

    static double kahan(double[] a) {
        double sum = 0.0, c = 0.0;
        for (double x : a) {
            double y = x - c;
            double t = sum + y;
            c = (t - sum) - y;
            sum = t;
        }
        return sum;
    }

    static double neumaier(double[] a) {
        double sum = 0.0, correction = 0.0;
        for (double x : a) {
            double t = sum + x;
            if (Math.abs(sum) >= Math.abs(x)) {
                correction += (sum - t) + x;
            } else {
                correction += (x - t) + sum;
            }
            sum = t;
        }
        return sum + correction;
    }

    static double fixedPairwise(double[] a) {
        if (a.length == 0) return 0.0;
        return pairwise(a, 0, a.length);
    }

    private static double pairwise(double[] a, int left, int right) {
        if (right - left == 1) return a[left];
        int mid = left + (right - left) / 2;
        return pairwise(a, left, mid) + pairwise(a, mid, right);
    }

    // Exact decimal representation of finite binary64 operands,
    // not necessarily the original decimal values before parsing.
    static BigDecimal exactBinarySum(double[] a) {
        BigDecimal total = BigDecimal.ZERO;
        for (double x : a) {
            if (!Double.isFinite(x)) {
                throw new IllegalArgumentException("non-finite input");
            }
            total = total.add(new BigDecimal(x));
        }
        return total;
    }

    static boolean sameRawBits(double a, double b) {
        return Double.doubleToRawLongBits(a)
            == Double.doubleToRawLongBits(b);
    }

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    // Block indices depend only on array length and blockSize.
    static double fixedParallel(
            double[] a, int blockSize, ExecutorService pool)
            throws InterruptedException, ExecutionException {
        if (a == null || blockSize < 1 || pool == null) {
            throw new IllegalArgumentException("invalid arguments");
        }
        List<Future<Double>> tasks = new ArrayList<>();
        for (int start = 0; start < a.length;) {
            final int lo = start;
            final int hi = lo + Math.min(blockSize, a.length - lo);
            tasks.add(pool.submit(() -> {
                double subtotal = 0.0;
                for (int i = lo; i < hi; i++) subtotal += a[i];
                return subtotal;
            }));
            start = hi;
        }

        // Completion order is irrelevant: get in submission order.
        double[] partials = new double[tasks.size()];
        for (int i = 0; i < tasks.size(); i++) {
            partials[i] = tasks.get(i).get();
        }
        return fixedPairwise(partials);
    }

    static void reverseArray(double[] a) {
        for (int i = 0, j = a.length - 1; i < j; i++, j--) {
            double temp = a[i];
            a[i] = a[j];
            a[j] = temp;
        }
    }

    public static void main(String[] args) throws Exception {
        double a = 1e16, b = -1e16, c = 1.0;
        System.out.println("(a+b)+c: " + ((a + b) + c));
        System.out.println("a+(b+c): " + (a + (b + c)));

        double[] xs = {1e16, 1.0, -1e16, 1.0};
        System.out.println("Input: " + Arrays.toString(xs));
        System.out.println("Forward: " + forward(xs));
        System.out.println("Reverse: " + reverse(xs));
        System.out.println("Fixed pairwise: " + fixedPairwise(xs));
        System.out.println("Kahan: " + kahan(xs));
        System.out.println("Neumaier: " + neumaier(xs));
        System.out.println(
            "Exact binary64 sum: " +
            exactBinarySum(xs).toPlainString());

        ExecutorService pool1 = Executors.newFixedThreadPool(1);
        ExecutorService pool2 = Executors.newFixedThreadPool(2);
        ExecutorService pool4 = Executors.newFixedThreadPool(4);
        try {
            double w1 = fixedParallel(xs, 2, pool1);
            double w4 = fixedParallel(xs, 2, pool4);
            double changedBlock = fixedParallel(xs, 4, pool1);
            System.out.println("Fixed block 2 (1 worker): " + w1);
            System.out.println("Fixed block 2 (4 workers): " + w4);
            System.out.println(
                "Same bits across workers: " + sameRawBits(w1, w4));
            System.out.println(
                "Changed block size 4: " + changedBlock);

            Random random = new Random(5312026L);
            for (int trial = 0; trial < 500; trial++) {
                int n = random.nextInt(81);
                double[] data = new double[n];
                for (int i = 0; i < n; i++) {
                    switch (random.nextInt(6)) {
                        case 0 -> data[i] = 1e16;
                        case 1 -> data[i] = -1e16;
                        case 2 -> data[i] = 1.0;
                        case 3 -> data[i] = -1.0;
                        case 4 -> data[i] = random.nextInt(2001) - 1000;
                        default ->
                            data[i] =
                                (random.nextInt(2001) - 1000) / 8.0;
                    }
                }

                double base = fixedParallel(data, 8, pool1);
                double other2 = fixedParallel(data, 8, pool2);
                double other4 = fixedParallel(data, 8, pool4);
                check(sameRawBits(base, other2),
                    "two worker mismatch " + trial);
                check(sameRawBits(base, other4),
                    "four worker mismatch " + trial);
                check(Double.isFinite(base),
                    "unexpected overflow in bounded test");

                double[] reversed = data.clone();
                reverseArray(reversed);
                check(exactBinarySum(data).compareTo(
                    exactBinarySum(reversed)) == 0,
                    "exact sum depends on order");
            }
            System.out.println("Fixed partition random trials: 500 PASS");
        } finally {
            pool1.shutdown();
            pool2.shutdown();
            pool4.shutdown();
        }

        System.out.println(
            "0.1+0.2==0.3: " + (0.1 + 0.2 == 0.3));
        System.out.println(
            "Signed zero bits differ: " +
            !sameRawBits(+0.0, -0.0));
        System.out.println(
            "NaN equals itself: " + (Double.NaN == Double.NaN));
    }
}
```

Biên dịch với JDK 17 trở lên và chạy:

```bash
javac -encoding UTF-8 FloatingPointOrderDemo.java
java FloatingPointOrderDemo
```

**Đầu ra xác định:**

```text
(a+b)+c: 1.0
a+(b+c): 0.0
Input: [1.0E16, 1.0, -1.0E16, 1.0]
Forward: 1.0
Reverse: 0.0
Fixed pairwise: 0.0
Kahan: 1.0
Neumaier: 2.0
Exact binary64 sum: 2
Fixed block 2 (1 worker): 0.0
Fixed block 2 (4 workers): 0.0
Same bits across workers: true
Changed block size 4: 1.0
Fixed partition random trials: 500 PASS
0.1+0.2==0.3: false
Signed zero bits differ: true
NaN equals itself: false
```

### 15.1. Diễn giải kết quả

- `(a+b)+c` là 1 còn `a+(b+c)` là 0: phép cộng binary64 không kết hợp.
- Dãy bốn phần tử có tổng toán học 2, forward ra 1, reverse/pairwise ra 0; kết quả phụ thuộc thứ tự.
- Neumaier và BigDecimal cho 2 ở ví dụ này. **BigDecimal là oracle** cho tổng chính xác các double đã được biểu diễn, không phải bằng chứng mọi số decimal gốc đã được bảo tồn.
- Khi b=2, chương trình chia dãy thành hai block: [10¹⁶,1] và [−10¹⁶,1], mỗi subtotal là ±10¹⁶ rồi cộng thành 0. Dù dùng pool một worker hay bốn worker, output raw bits bằng nhau vì **partition và merge tree giống nhau**.
- Khi đổi b=4, toàn bộ dãy vào một block nên tính forward ra 1. Đổi b tức đổi thuật toán số học, không còn phải giữ nguyên bit.
- Bộ kiểm 500 ca sinh mảng có số lượng 0..80, giá trị lớn/trái dấu, các số nguyên nhỏ và m/8 biểu diễn chính xác. Mỗi ca chạy đúng block size 8 dưới pool 1,2,4 worker và kiểm raw-bit equality. Sau đó đảo dãy, so kết quả BigDecimal exact để kiểm oracle độc lập thứ tự.
- Ba dòng cuối nhắc ta cách so kết quả phụ thuộc mục tiêu: số học bằng nhau, raw-bit equality hay phát hiện NaN.

### 15.2. Giới hạn và cách mở rộng

Bộ test random **không tự chứng minh** mọi hệ thống song song trên mọi máy cho bit giống nhau; chính cấu trúc fixed-block và cách gộp có chứng minh ở mục 6. Đồng thời, kiểm oracle BigDecimal không chứng minh fixed-block sum có error nhỏ hơn mọi phương pháp khác. Với dữ liệu cực lớn, cần quản lý số Future đang chờ, kích thước block, tiêu thụ bộ nhớ, và có thể dùng cây merge song song **với cấu trúc cố định**.

Mỗi task chỉ đọc input, nhưng chương trình **không sao chép mảng input** trước khi submit; caller phải bảo đảm không thread khác sửa dãy trong quá trình tính. Thư viện production cần version/snapshot dữ liệu, kiểm lỗi từ `Future.get()`, đóng pool, và có giới hạn bộ nhớ theo số block.

## 16. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Coi phép cộng double associative | Mỗi bước làm tròn | Cố định thứ tự hoặc dùng exact arithmetic |
| Kết quả khác bit là có data race | Race-free vẫn có thể khác merge order | Phân biệt hai lớp vấn đề |
| Dùng synchronized rồi coi kết quả reproducible | Thứ tự vào khóa thay đổi | Subtotals theo block index |
| Gộp theo completion order | Đổi thứ tự phép cộng | Gộp theo index và tree cố định |
| Partition theo số worker | Thay worker sẽ thay cách nhóm | Cố định b theo data indices |
| Cố định tree rồi gọi kết quả exact | Kết quả fixed tree vẫn làm tròn | So với oracle |
| Coi Kahan/Neumaier luôn exact | Compensation vẫn dùng double | Báo giới hạn và kiểm case xấu |
| Nghĩ pairwise luôn tốt hơn | Error bound không xếp hạng mọi instance | Đo data thực |
| Dùng reduce song song mà quên associativity | Framework có thể regroup | Cố định reduction policy |
| Nhầm unit roundoff với Double.MIN_VALUE | MIN_VALUE là subnormal | u=2^-53 |
| Parse decimal qua double trước BigDecimal | Precision input có thể mất | BigDecimal(String) |
| Dùng BigDecimal.valueOf làm oracle exact binary64 | Chuyển qua shortest decimal text | Dùng new BigDecimal(double) cho finite |
| Dùng MathContext rounding rồi coi BigDecimal exact | Rounding phụ thuộc thứ tự | Add không MathContext cho oracle |
| So raw bits bằng == | +0 == -0 nhưng bits khác | Double.doubleToRawLongBits |
| So NaN==NaN | NaN không bằng chính nó | Double.isNaN |
| Thay a*b+c thành Math.fma mà không ghi đổi numeric policy | FMA làm tròn một lần | Pin công thức và test |
| Coi Java strictfp giúp associative | Strict semantics không đổi đại số rounding | Không reassociate tùy ý |
| Không xử lý Infinity/overflow/underflow | Sai số vượt mô hình thông thường | Ràng buộc miền, báo ngoại lệ |
| Không kiểm mutation input khi chạy task | Mỗi worker có thể nhìn snapshot khác | Bảo đảm immutable input |
| Đánh giá một lần rồi tuyên bố reproducible | Scheduling có thể khác | Chứng minh cấu trúc, chạy nhiều cấu hình |

## 17. Bài tập có đáp án

**Bài 1.** Vì sao cộng double không kết hợp? *Đáp án:* mỗi phép cộng làm tròn và có thể mất chữ số thấp trước phép cộng tiếp.

**Bài 2.** Với a=10¹⁶,b=−10¹⁶,c=1, (a+b)+c bằng bao nhiêu? *Đáp án:* 1.

**Bài 3.** Cũng ba số ấy, a+(b+c) bằng bao nhiêu? *Đáp án:* 0.

**Bài 4.** Dãy [10¹⁶,1,−10¹⁶,1] có tổng chính xác? *Đáp án:* 2.

**Bài 5.** Forward trên dãy ấy? *Đáp án:* 1.

**Bài 6.** Reverse trên dãy ấy? *Đáp án:* 0.

**Bài 7.** Pairwise trên dãy ấy? *Đáp án:* 0.

**Bài 8.** Kahan thông thường trong ví dụ? *Đáp án:* 1.

**Bài 9.** Neumaier trong ví dụ? *Đáp án:* 2.

**Bài 10.** Deterministic có đồng nghĩa exact? *Đáp án:* không, fixed tree có thể lặp lại cùng một sai số.

**Bài 11.** Không có data race thì có chắc kết quả reduction cùng bit? *Đáp án:* không nếu thứ tự combine thay đổi.

**Bài 12.** Điều quan trọng nhất để tái lập giữa worker count? *Đáp án:* cùng partition, phép cộng trong block và merge tree cố định.

**Bài 13.** Thay block size có thể thay bit không? *Đáp án:* có.

**Bài 14.** Vì sao Future được lưu theo thứ tự submit? *Đáp án:* để kết quả block j được gộp theo chỉ số chứ không theo thời gian hoàn thành.

**Bài 15.** Với n phần tử, block b, số partial? *Đáp án:* ceil(n/b).

**Bài 16.** Work fixed-block sum? *Đáp án:* O(n+ceil(n/b)).

**Bài 17.** Độ cao pairwise tree trên q partial? *Đáp án:* O(log q).

**Bài 18.** Ý nghĩa u=2^-53? *Đáp án:* unit roundoff của binary64 trong mô hình phù hợp.

**Bài 19.** Condition number của tổng lớn khi nào? *Đáp án:* nhiều số lớn triệt tiêu làm tổng cuối rất nhỏ so với sum absolute.

**Bài 20.** Khi tổng tham chiếu S=0 có relative error thông thường không? *Đáp án:* không định nghĩa, nên dùng absolute error.

**Bài 21.** new BigDecimal(double) có tác dụng gì? *Đáp án:* biểu diễn chính xác giá trị binary64 hữu hạn đã có.

**Bài 22.** Muốn lưu decimal 0,1 chính xác? *Đáp án:* new BigDecimal("0.1") từ String.

**Bài 23.** MathContext có thể khiến BigDecimal sum phụ thuộc thứ tự không? *Đáp án:* có, nếu mỗi add bị làm tròn.

**Bài 24.** FMA khác a*b+c? *Đáp án:* FMA làm tròn một lần cho toàn phép nhân-cộng.

**Bài 25.** Strictfp trong Java 17 có biến cộng thành associative? *Đáp án:* không.

**Bài 26.** Trong Java, 0.1+0.2==0.3? *Đáp án:* false.

**Bài 27.** +0.0 == -0.0? *Đáp án:* true nhưng raw bits khác.

**Bài 28.** Double.NaN == Double.NaN? *Đáp án:* false.

**Bài 29.** Dùng kiểm raw bit khi nào? *Đáp án:* khi contract yêu cầu bitwise reproducibility, có chính sách NaN/zero rõ.

**Bài 30.** Với dữ liệu tài chính cần decimal exact, nên cân nhắc gì? *Đáp án:* BigDecimal từ String hoặc số nguyên theo đơn vị tiền nhỏ nhất.

**Bài 31.** Một phép tính song song nhận đủ partial nhưng gộp theo completion order có lỗi đồng thời không? *Đáp án:* có thể hoàn toàn race-free, song không tái lập bit.

**Bài 32.** Nếu task đọc input bị thread khác sửa, fixed tree có đủ bảo đảm không? *Đáp án:* không; cần snapshot nhất quán/immutable input.

**Bài 33.** Exact accumulator có thể giúp kết quả độc lập thứ tự bằng cách nào? *Đáp án:* cộng các giá trị chính xác rồi làm tròn một lần ở cuối, nếu merge exact.

**Bài 34.** Khi đổi backend CPU→GPU cần làm gì? *Đáp án:* cố định numeric policy, kiểm reassociation/FMA, version và golden-bit tests.

## 18. Kết luận và checklist

- Phân biệt kết quả tái lập, chính xác và race-free.
- Kiểm dữ liệu cancellation như [10¹⁶,1,−10¹⁶,1].
- Ghi rõ kiểu số, rounding, special value và cách parse.
- Cố định block index, block size và reduction tree khi cần bitwise.
- Không để completion order quyết định phép cộng.
- Đo sai số bằng oracle độc lập với giới hạn phù hợp.
- Không nhận Kahan/Neumaier là exact vô điều kiện.
- Dùng BigDecimal từ String cho decimal exact và từ double cho exact binary operand.
- Kiểm +0/−0, NaN, Infinity, subnormal/overflow.
- Kiểm nhiều worker count nhưng giữ cùng numeric algorithm.
- Version hóa b, backend, compiler/JDK và FMA policy khi so golden outputs.
- Nếu cần reproducibility bất chấp thứ tự, xem exact/binned accumulator.

**Kết luận:** phép cộng floating-point không kết hợp chính xác, nên thuật toán song song có thể đổi kết quả khi thay cách chia/ghép. Cố định **partition và cây reduction** giúp giữ tính tái lập theo bit trong hợp đồng xác định, nhưng không bảo đảm kết quả gần tổng lý tưởng nhất. **Kahan, Neumaier, pairwise, BigDecimal** giải các khía cạnh độ chính xác khác nhau; chọn thuật toán theo yêu cầu cùng bit, sai số chấp nhận được hay số học exact.
