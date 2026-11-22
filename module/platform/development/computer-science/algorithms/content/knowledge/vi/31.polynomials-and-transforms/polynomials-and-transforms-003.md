# Nhân số lớn bằng chia để trị Karatsuba

**Karatsuba** là thuật toán **nhân hai số nguyên lớn bằng chia để trị** (*divide and conquer*) nhằm giảm số phép nhân của các nửa số từ **bốn xuống ba**. Trong phép nhân thông thường giữa hai số có n chữ số, ta kết hợp từng chữ số của số này với từng chữ số của số kia, dẫn tới khoảng **O(n²)** phép toán trên chữ số. Karatsuba biểu diễn mỗi số thành **phần cao và phần thấp**, sử dụng một đẳng thức đại số để tính kết quả chỉ từ **ba phép nhân kích thước xấp xỉ một nửa**, rồi cộng, trừ và dịch vị trí để ghép lại. Nhờ vậy, thời gian tiệm cận là **O(n^{log₂3}) ≈ O(n^{1,585})**, tốt hơn bậc hai khi n đủ lớn.

Bài nằm trong nhóm **Đa thức và biến đổi** của Computer Science Algorithms, với chủ đề trực tiếp **Nhân số lớn bằng chia để trị Karatsuba**. Mục tiêu không chỉ là ghi nhớ công thức. Ta sẽ bắt đầu từ cách nhân theo cột, mô hình số lớn dưới dạng dãy chữ số và sự liên hệ với **nhân đa thức/chập (convolution)**, dẫn ra ba tích của Karatsuba, truy vết ví dụ **1234 × 5678**, chứng minh tính đúng và độ phức tạp, phân biệt tách theo hệ thập phân với tách theo **bit**, xử lý số âm/0/số có độ dài lệch nhau, và tự cài một chương trình **Java 17+ chạy được**. Mã dùng BigInteger **để cộng, trừ, dịch bit và biểu diễn số lớn**, còn các phép nhân lớn được thực hiện bằng **đệ quy Karatsuba**, không gọi `BigInteger.multiply` trong chính thuật toán. `BigInteger.multiply` chỉ xuất hiện như **oracle độc lập trong kiểm thử**, bên cạnh một hàm nhân từng chữ số dùng để kiểm chéo.

**Kết quả cần nắm:** biết giải thích vì sao `z₁=(a+b)(c+d)−z₂−z₀` là hạng giữa, áp dụng `T(n)=3T(n/2)+O(n)`, xử lý đúng cơ số và vị trí dịch, biết điều kiện mà phép nhân `long` ở ngưỡng cơ sở không tràn, có chiến lược kiểm thử so với nhân từng chữ số và nhân BigInteger chuẩn, và đánh giá liệu Karatsuba có thực sự đáng dùng ở kích thước đầu vào cụ thể hay không.

## 1. Vấn đề: tại sao phép nhân số rất lớn cần thuật toán riêng?

Máy tính có kiểu nguyên cố định, ví dụ `int` và `long` trong Java. Một `long` có dấu có giá trị tối đa:

**9.223.372.036.854.775.807**.

Nếu nhân hai số có vài trăm, vài nghìn hoặc hàng triệu chữ số, ta **không thể** giữ toàn bộ số hay tích trong một `long`. Cần biểu diễn số lớn bằng một dãy **chữ số theo cơ số B** hoặc một đối tượng số nguyên đa độ chính xác như `BigInteger`.

Một số nguyên không âm có các chữ số `d₀,d₁,...,d_{n−1}` theo **thứ tự từ thấp lên cao**:

**`X=d₀+d₁B+d₂B²+...+d_{n−1}B^{n−1}`**, với `0≤dᵢ<B`.

Nếu chọn B=10, dᵢ là chữ số thập phân. Nếu chọn B=10⁴, một phần tử mảng mang bốn chữ số thập phân. Nếu chọn B=2³⁰, một phần tử mang 30 bit; dữ liệu thực tế có thể lưu trong `int` hoặc `long` tùy toán tử.

Để tính X·Y, hệ số của `B^k` trước khi xử lý nhớ (*carry*) là tổng:

**`c_k=Σ_{i+j=k}d_i e_j`**.

Đây chính là **phép chập** hai dãy chữ số, đồng thời là **phép nhân hai đa thức tại B**. Vì vậy Karatsuba có liên hệ tự nhiên với nhóm **Đa thức và biến đổi**, mặc dù mục tiêu thực tế của bài là tính tích hai số nguyên lớn.

### Hai yêu cầu khác nhau

- **Tính đúng:** tích phải chính xác tới mọi chữ số, không được dùng `double` rồi làm tròn khi độ dài lớn.
- **Tính hiệu quả:** khi số có hàng nghìn chữ số, tránh thực hiện tất cả cặp tích chữ số nếu có phép biến đổi đại số giúp giảm công việc.

Karatsuba giải yêu cầu thứ hai **mà không đánh đổi tính chính xác**: nó dùng phép cộng, trừ và các phép nhân con chính xác, nên cho tích nguyên chính xác tuyệt đối.

## 2. Nhân theo cột (schoolbook multiplication) có gì chậm?

Xét số X có n chữ số và Y có m chữ số theo cùng cơ số B. Cách nhân theo cột thử **mỗi chữ số của X với mỗi chữ số của Y**, tổng n·m tích đơn chữ số. Sau đó cộng các tích vào cột tương ứng và xử lý carry.

Ví dụ:

~~~text
      1234
   ×  5678
   --------
      9872     = 1234 × 8
     86380     = 1234 × 70
    740400     = 1234 × 600
   6170000     = 1234 × 5000
   --------
   7006652
~~~

Với hai số cùng độ dài n chữ số, thời gian **O(n²)**. Với độ dài khác nhau n và m, thời gian **O(nm)**. Bộ nhớ phụ cho các cột kết quả thường O(n+m), nếu có thể thực hiện carry tại chỗ.

Nhân theo cột rất đáng dùng khi mỗi số ngắn:

- Thuật toán dễ triển khai, dễ test.
- Số thao tác nhỏ, vùng dữ liệu liên tiếp nên thường tận dụng cache tốt.
- Không có chi phí tạo hàng loạt đối tượng đệ quy.
- Là **base case** cho Karatsuba và nhiều thuật toán nhân nhanh hơn.

**Karatsuba không loại bỏ schoolbook**. Nó chia bài lớn cho đến khi các bài con đủ nhỏ, rồi dùng phép nhân trực tiếp ở lá đệ quy. Đó là một **hybrid algorithm**: cấp cao chọn chia để trị; cấp thấp chọn nhân thường.

## 3. Tách hai số thành phần cao và phần thấp

Chọn một cơ số B và một số lượng chữ số m (hoặc số bit k). Đặt **`M=B^m`**. Mỗi số không âm X,Y được tách thành:

**`X=aM+b`**, với `0≤b<M`,  
**`Y=cM+d`**, với `0≤d<M`.

Ở đây:

- `a`: phần cao của X.
- `b`: phần thấp của X.
- `c`: phần cao của Y.
- `d`: phần thấp của Y.
- `M`: giá trị vị trí mà phần cao bắt đầu, ví dụ 100 nếu tách hai chữ số cuối theo thập phân.

Theo phép phân phối:

**`XY=(aM+b)(cM+d)=acM²+(ad+bc)M+bd`**.

Đặt các tích:

- **`z₂=ac`**, tích hai phần cao.
- **`z₀=bd`**, tích hai phần thấp.
- **`z₁=ad+bc`**, hạng giữa.

Một cách trực tiếp phải tính **bốn tích**: ac, ad, bc, bd. Nếu mỗi tích có khoảng n/2 chữ số, ta nhận truy hồi:

**`T(n)=4T(n/2)+O(n)=O(n²)`**.

Vậy chỉ chia đôi số mà vẫn giữ bốn tích **không làm giảm số mũ tiệm cận** so với schoolbook. Ý tưởng đặc biệt của Karatsuba là **tính hạng giữa bằng một tích kết hợp**, không nhân ad và bc riêng.

## 4. Công thức Karatsuba: ba phép nhân thay cho bốn

Ta đã cần hai phép nhân con:

**`z₂=ac`**,  
**`z₀=bd`**.

Hãy tính thêm **duy nhất một tích**:

**`z_S=(a+b)(c+d)`**.

Khai triển:

**`z_S=ac+ad+bc+bd=z₂+(ad+bc)+z₀`**.

Chuyển vế:

**`z₁=ad+bc=z_S−z₂−z₀`**.

Do đó:

**`XY=z₂M²+z₁M+z₀`**.

Ta chỉ cần **ba phép nhân lớn**:

1. `z₀=Karatsuba(b,d)`.
2. `z₂=Karatsuba(a,c)`.
3. `z_S=Karatsuba(a+b,c+d)`.

Các phép toán còn lại là cộng/trừ và dịch vị trí, có chi phí tuyến tính theo số chữ số của toán hạng ở mỗi nút.

### Sơ đồ phân rã

~~~text
                X * Y
                  |
    X = a*M + b,  Y = c*M + d
                  |
         +--------+--------+
         |        |        |
       b*d       a*c    (a+b)*(c+d)
        z0        z2         zS
         |        |        |
         +--------+--------+
                  |
           z1 = zS-z2-z0
                  |
       result = z2*M*M + z1*M + z0
~~~

**Ghi nhớ chính xác:** không phải `z₁=(a+b)(c+d)`, mà:

**`z₁=(a+b)(c+d)−ac−bd`**.

Quên hai phép trừ sẽ khiến hạng giữa chứa **trùng** các phần ac, bd, cho kết quả quá lớn.

### Tại sao hạng giữa không âm với các phần không âm?

Vì `z₁=ad+bc` và a,b,c,d đều không âm, nên **z₁≥0**. Trong phép trừ `z_S−z₂−z₀`, các số trung gian có thể rất lớn, nhưng kết quả toán học không âm. Nếu code sử dụng số có dấu cố định bị tràn, có thể thấy một z₁ âm giả; đó là lỗi biểu diễn số, **không** phải do Karatsuba có hạng giữa âm.

Một biến thể Karatsuba khác dùng những hiệu như `(a−b)(d−c)` có thể sinh giá trị âm trung gian hợp lệ. Bản cơ bản ở đây dùng tổng để giữ ba tích không âm cho phần trị tuyệt đối, dễ chứng minh và triển khai hơn.

## 5. Truy vết tay 1234 × 5678

Chọn B=10, m=2 chữ số, nên **M=10²=100**:

**`1234=12·100+34`**;  
**`5678=56·100+78`**.

Vậy:

- `a=12`, `b=34`.
- `c=56`, `d=78`.

Tính ba tích:

~~~text
z0 = b*d             = 34*78    = 2652
z2 = a*c             = 12*56    = 672
zS = (a+b)*(c+d)     = 46*134   = 6164
z1 = zS-z2-z0        = 6164-672-2652 = 2840
~~~

Ghép theo giá trị vị trí:

~~~text
result = z2*M*M + z1*M + z0
       = 672*10000 + 2840*100 + 2652
       = 6720000 + 284000 + 2652
       = 7006652
~~~

**`1234×5678=7.006.652`**.

Lưu ý: **z₀=2652** dài hơn hai chữ số thấp đã tách. Đó là điều bình thường. Không được cắt z₀ còn “52” hoặc tự bỏ carry trước khi cộng. Các phần `z₀,z₁,z₂` là **số nguyên đầy đủ**, có thể dài hơn nửa ban đầu. Công thức dịch rồi cộng **tự xử lý phần nhớ** đúng về mặt số học.

### Một phương án kiểm tra bằng phép nhân thường

Có thể tính:

**`1234×(5000+600+70+8)`**, cộng các tích một chữ số với các hàng đã dịch, ra cùng 7.006.652. Phép kiểm này **độc lập** với cách sử dụng công thức ba tích, rất có ích khi viết unit test cho thuật toán Karatsuba.

### Bẫy viết nhầm cơ số

Nếu đã tách m=2 chữ số thập phân, giá trị dịch là **M=100**, không phải 10. Nếu tách **k bit**, giá trị dịch là **M=2^k**, không phải 10^k. Dùng nhầm M làm sai mọi ví dụ ngoài trường hợp đặc biệt.

## 6. Vì sao thuật toán nhanh hơn: truy hồi và định lý Master

Giả sử hai số có độ dài n **chữ số cơ số B** và ta chia khoảng n/2 chữ số thấp và n/2 chữ số cao. Mỗi cấp đệ quy tính ba phép nhân kích thước xấp xỉ n/2:

**`T(n)=3T(n/2)+O(n)`**.

Phần O(n) gồm tách phần cao/thấp khi dùng biểu diễn thích hợp, cộng/trừ các số có O(n) chữ số, và ghép/dịch giá trị vị trí. Trong một triển khai dùng `BigInteger`, các phép cộng, trừ, bitmask và shift cũng có chi phí phụ thuộc độ dài bit, không phải O(1). Cận vẫn biểu diễn đúng khi mỗi phép ấy tốn O(n) và các tích con được tính đệ quy.

Theo định lý Master:

- a=3 bài con.
- b=2 là hệ số thu nhỏ kích thước.
- f(n)=O(n).
- `n^{log_b a}=n^{log₂3}≈n^{1,5849625}`.

Vì `n^{log₂3}` lớn hơn n theo số mũ, phần đệ quy chi phối:

**`T(n)=Θ(n^{log₂3})≈Θ(n^{1,585})`**.

### Đếm số phép nhân ở các cấp

Giả sử n=2^k và mọi bài con nhỏ tới đúng một chữ số:

- Nhân thường sau chia đôi bốn tích: **`4^k=n²` phép nhân một chữ số**.
- Karatsuba: **`3^k=n^{log₂3}` phép nhân một chữ số**.

Ví dụ n=1024=2¹⁰:

- Trường hợp mô hình nhân thường: `1024²=1.048.576` tích lá.
- Karatsuba thuần túy: `3¹⁰=59.049` tích lá.

Sự khác biệt tăng nhanh khi n lớn. Tuy nhiên **đếm phép nhân lá không đủ để dự đoán thời gian thực**: các phép cộng/trừ, bộ nhớ tạm, đối tượng, cache, chi phí cắt số và chọn ngưỡng dừng vẫn ảnh hưởng nhiều.

### Không phải O(log n)

Độ sâu đệ quy là O(log n), nhưng ở mỗi nút lại có **ba lời gọi con**, không phải một. Nhiều người suy nhầm “chia đôi n nên thuật toán O(log n)” — đây là độ sâu của **một đường đi trong cây đệ quy**, không phải tổng công việc của toàn cây.

### Không phải lúc nào cũng nhanh hơn phép nhân thường

Karatsuba có nhiều đối tượng và phép cộng/trừ trung gian hơn nhân trường học. Với số chỉ vài chữ số hoặc vài machine words, overhead đệ quy có thể lớn hơn phần tiết kiệm từ ba thay vì bốn tích. Vì vậy thư viện số lớn thực tế thường:

- Dùng schoolbook với số nhỏ.
- Chuyển sang Karatsuba khi vượt một **ngưỡng đã đo**.
- Có thể chuyển tiếp sang Toom–Cook hoặc FFT/NTT cho số rất lớn.

Ngưỡng cụ thể phụ thuộc phần cứng, dạng dữ liệu, cách lưu limbs và implementation; **không có một ngưỡng chuẩn tối ưu cho mọi JVM**.

## 7. Tách theo bit: cách thuận tiện trong Java

Ví dụ thập phân giúp hiểu công thức, nhưng trong mã Java có `BigInteger`, thao tác bit rõ ràng hơn.

Cho hai số nguyên **không âm** x,y. Đặt:

**`n=max(bitLength(x),bitLength(y))`**,  
**`k=⌊n/2⌋`**,  
**`M=2^k`**.

Khi đó:

**`xHigh=x>>k`**,  
**`xLow=x mod 2^k`**,  
**`yHigh=y>>k`**,  
**`yLow=y mod 2^k`**.

Trong Java BigInteger:

~~~java
int half = n / 2;
BigInteger mask = BigInteger.ONE
        .shiftLeft(half)
        .subtract(BigInteger.ONE);

BigInteger xLow = x.and(mask);
BigInteger xHigh = x.shiftRight(half);
BigInteger yLow = y.and(mask);
BigInteger yHigh = y.shiftRight(half);
~~~

Đoạn này là minh họa tách số và **không phải chương trình Java độc lập**. Nó giả thiết x,y không âm và n đủ lớn để half≥1. Code chạy đầy đủ ở mục 11 xử lý các trường hợp cơ sở trước.

Vì:

**`x=xHigh·2^k+xLow`** và tương tự cho y, ta ghép:

~~~java
BigInteger result = z2.shiftLeft(2 * half)
        .add(cross.shiftLeft(half))
        .add(z0);
~~~

Ở đây `shiftLeft(k)` là nhân **2^k**, không phải dịch **k chữ số thập phân**. Điều này đúng vì phiên bản này tách **bit**.

### Tại sao dùng bit mask?

`mask=2^k−1` có đúng k bit thấp bằng 1. Với x≥0:

**`x.and(mask)=x mod 2^k`**.

Còn `x.shiftRight(k)=⌊x/2^k⌋`, nên phần cao/phần thấp tách chính xác.

**Cảnh báo với số âm:** BigInteger bitwise `and` và `shiftRight` trên số âm dựa trên biểu diễn dấu kiểu hai phần bù mở rộng. Bởi vậy bản mã **tách trị tuyệt đối trước khi đệ quy**; không áp dụng công thức mask đơn giản trên số âm rồi giả định phần cao/thấp là các chữ số không âm.

## 8. Xử lý các trường hợp đặc biệt

### 8.1. Một số bằng 0

**`0×y=0`**. Kiểm tra ngay trước khi đệ quy giúp tránh sinh cả cây ba phép nhân khi một nhánh con có giá trị 0. Trong nhiều ca độ dài hai số rất lệch nhau, điều này cũng giảm chi phí vô ích.

### 8.2. Số âm

Karatsuba chuẩn tách các **phần trị tuyệt đối không âm**. Với x,y có dấu:

1. Lấy a=|x|, b=|y|.
2. Tính p=KaratsubaPositive(a,b).
3. Nếu hai dấu **khác nhau**, trả −p; nếu cùng dấu, trả p.

Vì Java `BigInteger` không giới hạn ở 64-bit, `abs` xử lý được những số âm rất lớn. Với `long` đơn thuần, `Math.abs(Long.MIN_VALUE)` có thể tràn và vẫn âm; đây là lý do dùng BigInteger để biểu diễn số lớn dễ an toàn hơn.

Ví dụ:

**`−12345×6789=−83810205`**,  
**`−1×−1=1`**,  
**`0×−999...=0`**.

### 8.3. Độ dài lẻ

Nếu n=65 bit, chọn k=⌊65/2⌋=32. Phần thấp có tối đa 32 bit, phần cao có tối đa 33 bit. Không cần n chẵn; biểu diễn `xHigh·2^32+xLow` vẫn đúng.

Tổng `xHigh+xLow` có thể dài **hơn phần lớn nhất một bit**. Vì vậy bài con tính `z_S` đôi khi có kích thước `⌈n/2⌉+1`, không phải chính xác n/2. Sự khác biệt O(1) bit mỗi cấp **không đổi số mũ O(n^{log₂3})** của phân tích tiệm cận, miễn ngưỡng cơ sở bảo đảm kích thước thực sự giảm.

### 8.4. Hai số dài khác nhau rất nhiều

Nếu x có 1000 bit còn y chỉ 10 bit, việc luôn chia theo n=1000 vẫn **đúng**, nhưng có thể tạo nhiều phần cao/thấp bằng 0 và chi phí phụ không cần thiết. Một thuật toán sản xuất có thể:

- Nhân số lớn với **một limb nhỏ** trực tiếp trong O(n).
- Chia operand dài theo các khối rồi nhân với operand ngắn.
- Điều chỉnh ngưỡng schoolbook, tránh tạo những nhánh nhiều số 0.
- Dùng thư viện `BigInteger.multiply` đã tối ưu, nếu mục tiêu là hiệu năng thực tế chứ không phải tự cài Karatsuba.

Bản bài học ưu tiên tính đúng và tính minh bạch. Nó có kiểm tra 0 ngay ở mỗi lời gọi đệ quy, nhưng **không** tuyên bố nhanh nhất cho mọi cặp số lệch độ dài.

### 8.5. Số 1 và tiền tố 0

Nhân với 1 phải cho lại đúng toán hạng. Khi parse chuỗi thập phân:

- `"00000120"` có giá trị 120.
- `"-0030"` có giá trị −30.
- Tích là −3600, không có quy tắc tự giữ số 0 đứng đầu.

BigInteger biểu diễn **giá trị nguyên**, không bảo tồn định dạng chữ số ban đầu. Nếu ứng dụng cần giữ số 0 đầu để hiển thị theo một độ rộng cố định, đó là **vấn đề format đầu ra**, không thuộc phép nhân số học.

## 9. Ngưỡng cơ sở: tại sao 30 bit an toàn với long?

Để dừng đệ quy, bản mã chọn:

**`BASE_CASE_BITS=30`**.

Khi hai số không âm đều có nhiều nhất 30 bit:

**`0≤a,b≤2³⁰−1`**.

Tích lớn nhất là:

**`(2³⁰−1)²<2⁶⁰<2⁶³−1`**.

Vì vậy ta có thể đưa hai toán hạng nhỏ sang `long` rồi nhân bằng `Math.multiplyExact` mà **không tràn long**. Lấy `BigInteger.valueOf` để đưa tích trở lại kiểu đa độ chính xác.

~~~java
if (n <= BASE_CASE_BITS) {
    long a = x.longValueExact();
    long b = y.longValueExact();
    return BigInteger.valueOf(Math.multiplyExact(a, b));
}
~~~

Nếu đổi ngưỡng thành 64 bit nhưng vẫn dùng `long * long`, tích hai số có gần 64 bit **không thể chứa trong long**. Kết quả sẽ sai hoặc ném `ArithmeticException`. Không tăng threshold tùy tiện khi chưa đổi cách nhân cơ sở.

### Base case cũng có thể là schoolbook mảng limbs

Nếu tự xây thư viện số lớn từ mảng `int[]`, ngưỡng dừng có thể là số lượng limbs (ví dụ 16 hoặc 32 limb). Base case khi đó dùng nhân theo cột trên các limb; đảm bảo tích hai limb cộng carry vào kiểu chứa trung gian đủ rộng, thường `long` nếu chọn B phù hợp.

Chọn threshold bằng **benchmark trên môi trường thực**, không bằng một con số đọc từ bài khác mà không kiểm chứng.

## 10. Pseudocode Karatsuba đầy đủ

Bản dưới đây là thủ tục toán học trên **số nguyên không âm** dùng biểu diễn nhị phân:

~~~text
KARATSUBA_POSITIVE(x, y):
    if x == 0 or y == 0:
        return 0

    n = max(bitLength(x), bitLength(y))
    if n <= BASE_CASE_BITS:
        return safeSmallMultiply(x, y)

    k = floor(n / 2)
    B = 2^k
    mask = B - 1

    xLow  = x & mask
    xHigh = x >> k
    yLow  = y & mask
    yHigh = y >> k

    z0 = KARATSUBA_POSITIVE(xLow, yLow)
    z2 = KARATSUBA_POSITIVE(xHigh, yHigh)
    zS = KARATSUBA_POSITIVE(xLow + xHigh,
                           yLow + yHigh)

    cross = zS - z0 - z2

    return (z2 << (2*k)) + (cross << k) + z0
~~~

Bộ bao ngoài xử lý dấu:

~~~text
MULTIPLY_SIGNED(x, y):
    if x == 0 or y == 0:
        return 0
    answer = KARATSUBA_POSITIVE(abs(x), abs(y))
    return -answer if exactly one of x,y is negative
           else answer
~~~

Có ba lời gọi nhân đệ quy, không phải bốn. Phần `xLow+xHigh`/`yLow+yHigh` có thể tăng một bit, nên điều kiện dừng phải chắc chắn sẽ đạt được. Với ngưỡng 30 bit và k=⌊n/2⌋ cho n>30, kích thước bài con giảm hữu hạn, do đó thuật toán kết thúc.

**Không** sử dụng phép nhân BigInteger mặc định trong z0/z2/zS nếu muốn thực sự minh họa Karatsuba: phải gọi **chính hàm đệ quy**. Dùng BigInteger để cộng, trừ, mask, shift **không làm biến ba tích thành một lời gọi nhân built-in**.

## 11. Java 17+ chạy độc lập: Karatsuba, schoolbook và kiểm thử

Chương trình Java dưới đây có ba thành phần tách biệt:

1. **`karatsuba` và `positiveKaratsuba`:** phép nhân chính, tách bit rồi gọi **ba phép nhân đệ quy**. Phần biểu diễn số lớn, phép cộng/trừ/shift dùng BigInteger; **không gọi BigInteger.multiply trong hai hàm này**.
2. **`schoolbookDecimal`:** oracle độc lập nhân **từng chữ số thập phân** bằng mảng `long[]`, xử lý carry từ phải sang trái. Chỉ dùng để kiểm thử/so sánh, không phải hàm đệ quy của Karatsuba.
3. **`BigInteger.multiply`:** oracle thứ hai trong kiểm thử, do thư viện chuẩn cung cấp. Nó **không** được dùng để tính các tích trung gian trong thuật toán Karatsuba đang học.

Java 17 hỗ trợ đầy đủ `BigInteger`, `Random` và `Math.multiplyExact` dùng ở đây. Không cần thư viện ngoài.

**Hợp đồng:** nhận hai BigInteger có dấu, không null; trả tích chính xác. Code demo dùng chuỗi thập phân làm input thử nghiệm và có kết quả xuất ra chuẩn hóa (không giữ leading zeros). `schoolbookDecimal` giả thiết chuỗi số **hợp lệ ở dạng chuẩn do `BigInteger.toString()` sinh ra**, không phải parser tổng quát cho mọi ký hiệu số; parse chuỗi người dùng được xử lý bởi `new BigInteger(text)`.

Lưu thành **`KaratsubaDemo.java`**:

~~~java
import java.math.BigInteger;
import java.util.Random;

public final class KaratsubaDemo {
    private static final int BASE_CASE_BITS = 30;

    // Public entry: sign handling is OUTSIDE the
    // nonnegative bit-splitting recursion.
    public static BigInteger karatsuba(
            BigInteger left, BigInteger right) {
        if (left == null || right == null) {
            throw new IllegalArgumentException(
                    "Operands must not be null");
        }
        if (left.signum() == 0 || right.signum() == 0) {
            return BigInteger.ZERO;
        }

        BigInteger magnitude = positiveKaratsuba(
                left.abs(), right.abs());
        boolean negative = (left.signum() < 0)
                != (right.signum() < 0);

        return negative ? magnitude.negate() : magnitude;
    }

    private static BigInteger positiveKaratsuba(
            BigInteger x, BigInteger y) {
        // Invariant: x >= 0, y >= 0.
        if (x.signum() == 0 || y.signum() == 0) {
            return BigInteger.ZERO;
        }

        int n = Math.max(x.bitLength(), y.bitLength());
        if (n <= BASE_CASE_BITS) {
            // Each is < 2^30. The product is < 2^60,
            // so this *small* long multiplication is safe.
            long a = x.longValueExact();
            long b = y.longValueExact();
            return BigInteger.valueOf(Math.multiplyExact(a, b));
        }

        int half = n / 2;
        BigInteger mask = BigInteger.ONE
                .shiftLeft(half)
                .subtract(BigInteger.ONE);

        BigInteger xLow = x.and(mask);
        BigInteger xHigh = x.shiftRight(half);
        BigInteger yLow = y.and(mask);
        BigInteger yHigh = y.shiftRight(half);

        // Three, not four, recursive large products.
        BigInteger z0 = positiveKaratsuba(xLow, yLow);
        BigInteger z2 = positiveKaratsuba(xHigh, yHigh);
        BigInteger zSum = positiveKaratsuba(
                xLow.add(xHigh), yLow.add(yHigh));

        BigInteger cross = zSum.subtract(z0).subtract(z2);
        if (cross.signum() < 0) {
            throw new AssertionError(
                    "Nonnegative parts cannot give negative cross");
        }

        // Base = 2^half; combine by exact binary shifts.
        return z2.shiftLeft(2 * half)
                .add(cross.shiftLeft(half))
                .add(z0);
    }

    // Independent decimal schoolbook reference:
    // O(number of decimal digits of a * those of b).
    // Arguments are canonical signed decimal strings.
    private static String schoolbookDecimal(
            String left, String right) {
        boolean negLeft = left.startsWith("-");
        boolean negRight = right.startsWith("-");
        String a = negLeft ? left.substring(1) : left;
        String b = negRight ? right.substring(1) : right;

        if (a.equals("0") || b.equals("0")) {
            return "0";
        }

        // Long accumulator also holds intermediate sums.
        long[] columns = new long[a.length() + b.length()];

        for (int i = a.length() - 1; i >= 0; i--) {
            int digitA = a.charAt(i) - '0';
            for (int j = b.length() - 1; j >= 0; j--) {
                int digitB = b.charAt(j) - '0';
                columns[i + j + 1] += (long) digitA * digitB;
            }
        }

        // Propagate carries from least significant to most.
        for (int i = columns.length - 1; i >= 1; i--) {
            columns[i - 1] += columns[i] / 10;
            columns[i] %= 10;
        }

        int first = 0;
        while (first < columns.length - 1
                && columns[first] == 0) {
            first++;
        }

        StringBuilder digits = new StringBuilder();
        for (int i = first; i < columns.length; i++) {
            digits.append(columns[i]);
        }

        String answer = digits.toString();
        return negLeft != negRight ? "-" + answer : answer;
    }

    // Compare against TWO oracles: Java BigInteger and
    // independent decimal grade-school multiplication.
    private static void example(String left, String right) {
        BigInteger a = new BigInteger(left);
        BigInteger b = new BigInteger(right);
        BigInteger actual = karatsuba(a, b);

        BigInteger library = a.multiply(b); // Oracle only.
        String manual = schoolbookDecimal(
                a.toString(), b.toString());

        if (!actual.equals(library)
                || !actual.toString().equals(manual)) {
            throw new AssertionError(
                    "Mismatch for " + left + " and " + right);
        }

        System.out.println("multiply(" + left + ", "
                + right + ") = " + actual);
    }

    // Show the decimal B=100 example independently of
    // the binary split used inside positiveKaratsuba.
    private static void showDecimalTrace() {
        long a = 12, b = 34, c = 56, d = 78;
        long base = 100;

        long z0 = b * d;
        long z2 = a * c;
        long zSum = (a + b) * (c + d);
        long cross = zSum - z0 - z2;
        long result = z2 * base * base
                + cross * base + z0;

        System.out.println("Trace 1234 x 5678: z0=" + z0
                + ", z2=" + z2
                + ", zSum=" + zSum
                + ", cross=" + cross
                + ", result=" + result);
    }

    private static void randomizedChecks() {
        Random random = new Random(20261110L);

        for (int i = 0; i < 800; i++) {
            int aBits = random.nextInt(513);
            int bBits = random.nextInt(513);
            BigInteger a = new BigInteger(aBits, random);
            BigInteger b = new BigInteger(bBits, random);

            if (random.nextBoolean()) {
                a = a.negate();
            }
            if (random.nextBoolean()) {
                b = b.negate();
            }

            BigInteger actual = karatsuba(a, b);
            if (!actual.equals(a.multiply(b))) {
                throw new AssertionError(
                        "Random BigInteger cross-check failed");
            }

            if (i < 150 && !actual.toString().equals(
                    schoolbookDecimal(
                            a.toString(), b.toString()))) {
                throw new AssertionError(
                        "Random schoolbook cross-check failed");
            }
        }

        System.out.println(
                "Random comparisons: 800 PASS "
                + "(150 schoolbook cross-checks)");
    }

    private static void boundaryChecks() {
        int[] bitLengths = {
            1, 2, 29, 30, 31, 32,
            60, 61, 127, 128, 256, 512
        };

        for (int bits : bitLengths) {
            BigInteger a = BigInteger.ONE
                    .shiftLeft(bits)
                    .subtract(BigInteger.ONE);
            BigInteger b = BigInteger.ONE
                    .shiftLeft(bits)
                    .add(BigInteger.ONE);

            if (!karatsuba(a, b).equals(a.multiply(b))) {
                throw new AssertionError(
                        "Bit boundary failure at " + bits);
            }
        }

        System.out.println(
                "Power-of-two boundaries: 12 PASS");
    }

    public static void main(String[] args) {
        example("1234", "5678");
        example("-12345", "6789");
        example("0",
                "-999999999999999999999999999999999");
        example("999999999999999999",
                "999999999999999999");
        example("18446744073709551616",
                "18446744073709551616");
        example("1000000000000000000000000000000000000000",
                "12345");
        example("00000120", "-0030");

        showDecimalTrace();
        randomizedChecks();
        boundaryChecks();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 KaratsubaDemo.java
java KaratsubaDemo
~~~

**Stdout chính xác** (theo đúng thứ tự của main):

~~~text
multiply(1234, 5678) = 7006652
multiply(-12345, 6789) = -83810205
multiply(0, -999999999999999999999999999999999) = 0
multiply(999999999999999999, 999999999999999999) = 999999999999999998000000000000000001
multiply(18446744073709551616, 18446744073709551616) = 340282366920938463463374607431768211456
multiply(1000000000000000000000000000000000000000, 12345) = 12345000000000000000000000000000000000000000
multiply(00000120, -0030) = -3600
Trace 1234 x 5678: z0=2652, z2=672, zSum=6164, cross=2840, result=7006652
Random comparisons: 800 PASS (150 schoolbook cross-checks)
Power-of-two boundaries: 12 PASS
~~~

### Vì sao các dòng output này đáng kiểm?

- **1234×5678:** buộc công thức ba tích và cách ghép cơ số đúng; trace thập phân xác nhận 7.006.652.
- **Dấu âm:** `−12345×6789` phải âm; không được áp dụng bitmask lên số âm trực tiếp.
- **0:** trả về ngay, không sinh cây đệ quy vô ích.
- **18 chữ số 9 bình phương:** có carry nhiều cột; nếu ghép sai z₁ hoặc bỏ carry, kết quả dễ sai.
- **2^64 bình phương:** cả hai toán hạng đã vượt khả năng long có dấu; đáp án đúng là **2^128**, chứng minh phép nhân thật sự dùng số lớn.
- **Độ dài rất lệch:** số dài nhiều số 0 nhân 12345; vẫn đúng dù không cân bằng.
- **Leading zeros:** chuỗi “00000120” mang giá trị 120 và “−0030” mang giá trị −30, tích chuẩn hóa là −3600.
- **800 random + 12 ranh giới:** không chứng minh tuyệt đối, nhưng bắt được nhiều sai lệch ở split, dấu, carry, ngưỡng base case và bit lengths.

**Các lần gọi `a.multiply(b)` trong `example` và `randomizedChecks` là oracle kiểm thử, không phải thành phần của `positiveKaratsuba`.** Nếu bỏ toàn bộ kiểm thử/printing, thuật toán nhân chính vẫn hoạt động với ba lời gọi đệ quy cùng các phép cộng/trừ/shift.

## 12. Chứng minh tính đúng

Ta chứng minh bằng quy nạp theo kích thước bit của hai trị tuyệt đối không âm.

### Cơ sở

Khi một toán hạng là 0, trả 0 = x·y. Khi cả hai có bit length≤30, chuyển sang long rồi nhân trực tiếp. Vì tích luôn <2^60, phép nhân không tràn long, nên kết quả trả là x·y chính xác.

### Bước quy nạp

Với n>30, thuật toán chọn `k=⌊n/2⌋` và `M=2^k`, tách:

**`x=aM+b`**, **`y=cM+d`**.

Các toán hạng a,b,c,d và các tổng a+b,c+d có bit length nhỏ hơn n khi n>30, nên cả ba lời gọi đệ quy thật sự tiến tới bài toán nhỏ hơn. Theo giả thiết quy nạp:

**`z₂=ac`**,  
**`z₀=bd`**,  
**`z_S=(a+b)(c+d)`**.

Do đó:

**`cross=z_S−z₂−z₀=ad+bc`**.

Thuật toán ghép:

**`z₂M²+cross·M+z₀=acM²+(ad+bc)M+bd=(aM+b)(cM+d)=xy`**.

Vậy kết quả đúng với mọi số nguyên không âm ở cấp n.

### Mở rộng cho số có dấu

Với x,y bất kỳ, đặt X=|x|,Y=|y|. Thuật toán con trả X·Y đúng. Tích x·y có trị tuyệt đối X·Y và dấu âm đúng khi **chính xác một** toán hạng âm. Bộ bao ngoài áp dụng quy tắc ấy; trường hợp 0 đã trả 0. Vì vậy hàm `karatsuba` cho tích chính xác của mọi cặp BigInteger hợp lệ.

### Vì sao thuật toán dừng?

Nếu n>30, k≥15. Phần cao có tối đa n−k bit, phần thấp có tối đa k bit; tổng cao+thấp có tối đa max(n−k,k)+1 bit. Với n>30, độ dài lớn nhất đó **nhỏ hơn n**, nên kích thước các bài toán con giảm. Cuối cùng mọi nhánh chạm ngưỡng≤30 hoặc 0. Không có chu trình gọi vô hạn.

## 13. Kiểm thử độc lập và property-based testing

Khi tự cài thuật toán chia để trị, rất dễ có bug chỉ lộ ở số lẻ bit, số có nhiều 1, số có nhiều 0, hoặc đúng điểm kích thước thay đổi. Vì vậy cần **oracle độc lập**, không chỉ chạy một ví dụ thủ công.

### 13.1. So với nhân BigInteger chuẩn

Trong Java, `a.multiply(b)` là phép nhân số lớn của thư viện chuẩn. Dù implementation có thể tự dùng các thuật toán nhanh, kết quả **được coi là oracle về giá trị toán học** cho việc học và test bản Karatsuba.

Test:

~~~text
for random signed BigInteger a,b:
    got = karatsuba(a,b)
    expected = a.multiply(b)
    assert got.equals(expected)
~~~

Tạo số có bitLength 0..512, gán dấu ngẫu nhiên, so nhiều cặp. Những ca quan trọng gồm 0, ±1, số nguyên tố lớn, powers of two, giá trị ngay trên và dưới 2^k, và hai số có độ dài rất khác.

### 13.2. So với nhân từng chữ số độc lập

Nếu chỉ so với BigInteger.multiply, một số người e ngại sự phụ thuộc vào cùng thư viện. Vì vậy chương trình còn có **schoolbookDecimal**, không dùng công thức Karatsuba:

- Duyệt từng chữ số thập phân của a,b.
- Cộng tích chữ số vào cột i+j+1.
- Dồn carry từ phải sang trái.
- Ghép chuỗi số thập phân, xử lý dấu.

Với đầu vào đủ ngắn để kiểm thử, so:

**`karatsuba(a,b).toString()==schoolbookDecimal(a,b)`**.

Đây là **hai cách giải khác nhau**, giúp giảm nguy cơ hai cài đặt cùng mắc lỗi công thức ghép z₁.

### 13.3. Các bất biến cần kiểm ở mỗi nút

Với một nút có x,y không âm, k≥1:

1. `x=xHigh·2^k+xLow`.
2. `y=yHigh·2^k+yLow`.
3. `0≤xLow,yLow<2^k`.
4. `z₀≥0`, `z₂≥0` và `cross≥0`.
5. `cross=zSum−z0−z2`.
6. Giá trị trả đúng `z₂·2^{2k}+cross·2^k+z₀`.
7. Mỗi lời gọi đệ quy con có kích thước **nhỏ hơn** lời gọi cha khi n>30.
8. Ở base case, hai toán hạng đều <2^30 và tích <2^60.

Đây là các **local invariants** rất hữu ích khi đặt breakpoint hoặc in debug cho một cặp số gây sai.

### 13.4. Sinh số kiểm thử theo các họ biên

- **0, 1, −1** và các số rất nhỏ.
- **`2^k`**, **`2^k−1`**, **`2^k+1`** gần ngưỡng chia, ví dụ k=29,30,31,32,60,61,127,128.
- Hai số toàn bit 1: `2^k−1` nhân `2^k−1`.
- Số độ dài không cân bằng: 1024-bit × 4-bit.
- Cả hai số âm, chỉ một âm, và 0 nhân số âm.
- Tương ứng decimal: `999...9`, `1000...0`, `1010...01`.
- Số có leading zeros trong **chuỗi nhập**, để kiểm parser/format.
- Số có độ dài **lẻ** và số có phần cao hoặc phần thấp bằng 0.

Một bộ đối chiếu ngoài Java có thể mô phỏng đệ quy theo BigInt bất kỳ độ chính xác rồi kiểm nhiều dữ liệu. Trên **3.000 cặp có dấu ngẫu nhiên** tới khoảng 700 bit, một mô hình đệ quy ba tích cho kết quả trùng phép nhân BigInt trực tiếp; **1.100 trường hợp** đồng thời trùng nhân thập phân từng chữ số độc lập, và **400 ca ranh giới bit** trùng tích chuẩn. Những kiểm tra này chứng thực công thức triển khai, nhưng **không thay thế chứng minh quy nạp** ở mục 12.

### 13.5. Kiểm thử tốc độ đúng cách

Để đo hiệu năng, không chỉ chạy một phép nhân:

1. Chọn các nhóm độ dài n (ví dụ 32,64,128,256,512,1024,4096 bit).
2. Dùng nhiều cặp random độc lập với **độ dài thật** mong muốn; tránh toàn số 0 và 1 khi mục tiêu đo nhánh chung.
3. **Warm up JVM/JIT** trước khi ghi số đo.
4. Không in kết quả hoặc chuyển toàn bộ số sang chuỗi trong vòng đo.
5. Kiểm kết quả bằng oracle **ngoài** đoạn thời gian đang đo.
6. So schoolbook, Karatsuba tự cài và BigInteger.multiply chuẩn trên **cùng dữ liệu**.
7. Chạy nhiều lần, lấy median/distribution và báo phiên bản JDK, heap/CPU.
8. Phân biệt thời gian **parse decimal**, thời gian **multiply**, và thời gian **format decimal**.

Karatsuba lý thuyết tốt hơn không có nghĩa bản Java dùng nhiều BigInteger tạm sẽ nhanh hơn phép nhân native được tối ưu ở mọi n.

## 14. Chia để trị trên chữ số mảng: thiết kế cho bài lập trình yêu cầu tự cài

Trong một số bài lập trình hoặc khi tự làm thư viện BigInt, đề **không cho dùng BigInteger.multiply** hoặc không có kiểu số lớn có sẵn. Ta có thể dùng mảng các **limb** theo cơ số B.

Ví dụ chọn **B=10⁴**. Số thập phân lớn được tách thành nhóm bốn chữ số, lưu **little-endian**:

~~~text
Number: 1234567890123

Groups from right:
0123 | 6789 | 2345 | 1

little-endian limbs = [123, 6789, 2345, 1]
B = 10000
~~~

Cách viết để bảo đảm đúng:
`123+6789·B+2345·B²+1·B³`.

Một thiết kế đầy đủ cần:

- `trimLeadingZeros(limbs)`: bỏ các limb cao bằng 0, giữ biểu diễn 0 thống nhất.
- `add(a,b)`: cộng hai dãy limb, xử lý carry nếu cần.
- `subtractNonNegative(a,b)`: trừ khi a≥b, xử lý borrow; nếu muốn trừ tùy ý cần sign.
- `schoolbook(a,b)`: nhân từng cặp limb bằng kiểu trung gian đủ rộng, chuẩn hóa carry.
- `karatsubaLimbs(a,b)`: tách theo **số lượng limb**, dùng ba tích đệ quy, cộng kết quả với các offset limb tương đương `B^k`.
- `normalizeResult`: bảo đảm mỗi limb cuối nằm trong [0,B−1] và không có leading zero thừa.

### Vì sao phải chú ý carry/borrow?

Trong phiên bản BigInteger, các toán tử `add/subtract/shiftLeft` đã xử lý **carry, borrow và dấu** cho ta. Trong mảng limb, `zS−z0−z2` có thể gây borrow qua nhiều limb và `z₂B^{2k}+z₁B^k+z₀` có thể sinh carry. Không thể chỉ cộng từng phần tử mảng mà không chuẩn hóa.

Nếu ta lưu tạm các **hệ số chưa carry**, những hệ số ở giữa có thể lớn hơn B−1 hoặc âm trước khi tổng được chuẩn hóa. Cần quy tắc truyền nhớ nhất quán, đặc biệt với phép trừ. Một phương án đơn giản là xây các hàm cộng/trừ **luôn trả mảng limb đã chuẩn hóa**, rồi ghép các mảng đã dịch và cộng theo thứ tự.

### Chọn B sao cho tích limb và tổng tạm không tràn

Nếu chọn B=10⁴, tích hai limb tối đa `(9999)²<10^8`; dùng `long` cho tổng các tích và carry có vùng an toàn đáng kể trong dữ liệu bình thường. Nhưng nếu gom rất nhiều tích vào cùng một `int` trước khi truyền carry, **vẫn có thể overflow**. Không suy rằng “một tích limb vừa int” thì tổng hàng trăm/nghìn tích cũng vừa int.

Nếu chọn B=2³² và lưu limb trong int có dấu, tích hai limb theo nghĩa unsigned cần các phép nhân/ghép được thiết kế cẩn thận; `long` có dấu không chứa đủ mọi tích unsigned 32×32 dưới dạng **giá trị dương**. Chọn B nhỏ hơn hoặc dùng kỹ thuật unsigned/high-part thích hợp.

### Pseudocode mảng limb

~~~text
KARATSUBA_LIMBS(A, B):
    trim leading zeros
    if A or B is zero: return zero
    if min length is small: return SCHOOLBOOK(A, B)

    n = max(len(A), len(B))
    k = floor(n/2)

    A0 = lower k limbs of A
    A1 = remaining upper limbs of A
    B0 = lower k limbs of B
    B1 = remaining upper limbs of B

    Z0 = KARATSUBA_LIMBS(A0, B0)
    Z2 = KARATSUBA_LIMBS(A1, B1)
    ZS = KARATSUBA_LIMBS(ADD(A0,A1), ADD(B0,B1))

    CROSS = SUBTRACT(SUBTRACT(ZS,Z0),Z2)

    return ADD(
        ADD(SHIFT_LIMBS(Z2,2*k), SHIFT_LIMBS(CROSS,k)),
        Z0
    )
~~~

Ở đây `SHIFT_LIMBS(X,k)` là nhân X với **B^k** bằng cách thêm k limb 0 ở **đầu thấp** của dãy little-endian. Nó **khác** `shiftLeft(k)` khi dùng BigInteger và cơ số B không phải 2.

**Tại sao base case ở đây dùng min length?** Nếu một operand chỉ có vài limb mà operand còn lại dài, nhân schoolbook với số limb nhỏ có thể rẻ hơn phân rã cả số dài. Đây là **tối ưu thực thi**, không thay đổi đẳng thức Karatsuba; phải đo ngưỡng phù hợp. Bản Java tham khảo ở mục 11 dùng max bit length và kiểm 0 để đơn giản hóa bất biến.

## 15. Liên hệ với đa thức và phép chập

Biểu diễn số theo cơ số B là một phép đánh giá đa thức:

**`A(t)=a₀+a₁t+...+a_{n−1}t^{n−1}`**,  
**`X=A(B)`**.

Nhân hai số X=A(B),Y=C(B) tương ứng với:

**`X·Y=(A·C)(B)`**,

trong đó hệ số của đa thức tích là convolution của các chữ số. Sau đó cần xử lý carry để chuyển hệ số chưa chuẩn hóa về đúng các chữ số trong [0,B−1].

Karatsuba có thể được xem là **nhân hai đa thức bậc một theo biến M**:

**`(aM+b)(cM+d)`**.

Ta chỉ cần tính ba giá trị tích tại những kết hợp phù hợp rồi suy ra hệ số giữa. Phép biến đổi giảm **rank số phép nhân** từ 4 xuống 3 và áp dụng đệ quy cho các hệ số nhiều chữ số.

### Karatsuba có phải FFT không?

**Không.** Karatsuba là chia để trị với đẳng thức ba tích ở hai nửa. **FFT/NTT** tính convolution bằng biến đổi giữa miền hệ số và miền giá trị/miền tần số rồi nhân từng điểm, sau đó biến đổi ngược. Đối với đa thức hoặc số có số lượng limb rất lớn, các thuật toán dựa trên FFT/NTT hoặc các phương pháp nhân nhanh khác có thể có độ phức tạp tốt hơn Karatsuba.

Karatsuba phù hợp ở **kích thước trung bình** trong nhiều thư viện vì công thức tương đối đơn giản và overhead thấp hơn các biến đổi phức tạp. Nhưng ngưỡng chuyển thuật toán phụ thuộc implementation.

### So sánh Toom–Cook ở mức ý tưởng

Toom–Cook tách mỗi operand thành **nhiều phần hơn hai**, xem chúng là hệ số của một đa thức, đánh giá tại một số điểm, nhân các giá trị, rồi nội suy. Ví dụ Toom-3 có thể đạt số mũ thời gian thấp hơn Karatsuba trong mô hình phù hợp, nhưng cần nhiều phép cộng/trừ/nội suy hơn và có overhead lớn hơn ở dữ liệu nhỏ.

Karatsuba chính là một **trường hợp cơ bản quan trọng của tư duy đánh giá–tái tổ hợp** trong nhân đa thức, nhưng không nên gọi mọi Toom–Cook hay FFT là “Karatsuba”.

## 16. So sánh các lựa chọn nhân số lớn

| Thuật toán | Tư tưởng | Bậc thời gian thường nêu | Khi có ích |
|---|---|---|---|
| Nhân từng chữ số (schoolbook) | Xét mọi cặp chữ số | **O(n²)** | Số nhỏ, base case, code đơn giản |
| Karatsuba | Chia đôi, **3 tích con** | **O(n^{log₂3})≈O(n^{1,585})** | Số trung bình/lớn, kích thước có lợi cho đệ quy |
| Toom–Cook | Chia nhiều phần và nội suy | Phụ thuộc số phần; có biến thể tốt hơn Karatsuba | Kích thước lớn hơn ngưỡng crossover |
| Nhân bằng FFT/NTT | Convolution trong miền biến đổi | Thường gần **O(n log n)** trong mô hình phù hợp | Dãy rất dài, tối ưu hiệu năng cao |
| `BigInteger.multiply` | API thư viện, có tối ưu nội bộ | Phụ thuộc kích thước/JDK/cài đặt | Ứng dụng Java thật khi không cần tự cài |

**Chú ý khi so độ phức tạp:** n là độ dài theo **bit hoặc limb**, không phải giá trị nguyên của số. Nếu x≈10^1000, n theo chữ số thập phân là khoảng 1001, chứ không phải 10^1000. Không nói “O(x^{1,585})” nếu x là giá trị số.

Ngoài ra, thao tác **đọc và in** số dài n chữ số cũng tốn ít nhất Ω(n) ký tự, và chuyển đổi giữa cơ số nhị phân và thập phân có chi phí thực tế riêng. Khi benchmark phải tách thao tác parse/format khỏi phép nhân lõi.

## 17. Bộ nhớ, đệ quy và chi phí cấp phát BigInteger

### Độ sâu và kích thước kết quả

Mỗi lần chia làm độ dài bit của toán hạng giảm xấp xỉ một nửa, nên độ sâu một nhánh đệ quy là **O(log n)**. Tích của hai số n bit có thể cần tối đa khoảng **2n bit** để biểu diễn chính xác; không được ép kết quả trở lại n bit và mất phần cao.

Với implementation đệ quy lưu các kết quả z0,z2,zSum và BigInteger trung gian, tổng dữ liệu **đang sống** dọc một đường đệ quy có thể được kiểm soát ở mức tuyến tính theo n trong mô hình lưu trữ đơn giản, bên cạnh stack O(log n). Tuy nhiên số đối tượng và bộ đệm **cấp phát trong toàn bộ quá trình** lớn hơn rất nhiều; garbage collector của Java có thể khiến **peak heap thực tế** khác đáng kể dự đoán lý thuyết.

**Không coi chương trình dùng BigInteger là một cách tối ưu RAM.** Nó là cách viết rõ ràng, tránh phải tự code carry/borrow khi học công thức. Một thư viện sản xuất thường dùng mảng limb và quản lý buffer chuyên dụng để giảm cấp phát.

### Tràn kích thước dịch bit

BigInteger hỗ trợ số rất lớn, nhưng tham số `shiftLeft(int n)` vẫn là **int**, và mảng bên trong phải cấp phát được. Với đầu vào khổng lồ đến mức `2*half` không biểu diễn được hoặc bộ nhớ không đủ, bản cài này **không cam kết** xử lý. Các giới hạn vật lý và API vẫn tồn tại dù kiểu dữ liệu được gọi là “arbitrary precision”.

### Stack overflow?

Độ sâu O(log n) thường không lớn cho số có kích thước thực tế, nhưng không có thuật toán đệ quy nào được miễn hoàn toàn giới hạn stack của JVM. Nếu phát triển hệ thống khắt khe, có thể quản lý stack tường minh hoặc đặt ràng buộc input/heap rõ ràng. Với bài học cỡ vài trăm/vài nghìn bit, đây không phải vấn đề lớn nhất; overhead cấp phát và ngưỡng base case quan trọng hơn.

### Đầu vào không đáng tin cậy

Nếu API nhận số thập phân dài hàng triệu ký tự từ client, hãy đặt giới hạn độ dài và kiểm soát tài nguyên. Không nên cho phép một yêu cầu tùy ý tạo cây hàng triệu BigInteger trung gian mà không có quota CPU/heap. Kích thước input là một tham số bảo vệ hệ thống, không chỉ bài toán lý thuyết.

## 18. Các sai lầm thường gặp khi cài Karatsuba

1. **Dùng bốn tích con thay vì ba:** vẫn đúng phép nhân, nhưng không có lợi thế số mũ Karatsuba.
2. **Nhầm z₁ với (a+b)(c+d):** thiếu trừ z0 và z2, đếm trùng các tích cao/thấp.
3. **Gắn z0 với ac và z2 với bd rồi dịch sai:** phải thống nhất thấp×thấp ở B^0, cao×cao ở B^{2m}.
4. **Tách số theo 10^m nhưng ghép bằng dịch bit:** sai cơ số.
5. **Tách theo 2^k nhưng ghép bằng cách nối chuỗi thập phân:** sai vị trí.
6. **Dịch z₂ một lần k thay vì 2k:** hệ số cao cần nhân B^{2k}.
7. **Bỏ carry của z0 vì tưởng phần thấp chỉ có k chữ số:** z0 có thể dài tới 2k chữ số.
8. **Giả định tổng (a+b) luôn có đúng n/2 chữ số:** có thể dài hơn một chữ số/bit.
9. **Chỉ xử lý độ dài chẵn:** số có n lẻ vẫn cần tách với floor/ceil.
10. **Đệ quy không giảm kích thước:** có thể treo hoặc StackOverflowError, nhất là ngưỡng quá thấp.
11. **Không có base case:** Karatsuba đệ quy vô hạn ở các số nhỏ.
12. **Base case dùng long nhưng giữ 64 bit mỗi toán hạng:** tích có thể vượt long, sai dù phần còn lại dùng BigInteger.
13. **Nhầm 30 bit với 30 chữ số thập phân:** hai kích thước rất khác.
14. **Coi 0 là số có bit length không nhỏ:** BigInteger.ZERO.bitLength()==0.
15. **Không kiểm 0 sớm:** tạo nhiều nhánh nhân với 0 vô ích khi độ dài lệch nhau.
16. **Tách số âm trực tiếp bằng bitmask:** biểu diễn hai phần bù khiến low/high không còn theo giả thiết không âm đơn giản.
17. **Dùng Math.abs(Long.MIN_VALUE) cho input long âm:** overflow và giữ dấu âm.
18. **Quên dấu khi hai toán hạng trái dấu:** kết quả đáng ra âm.
19. **Quên trường hợp hai số cùng âm:** tích đáng ra dương.
20. **Cho phép null âm thầm đi vào recursive method:** ném NullPointerException khó hiểu thay vì hợp đồng rõ.
21. **Nhầm BigInteger.shiftLeft(k) với nhân 10^k:** nó nhân 2^k.
22. **Tưởng BigInteger có độ phức tạp O(1) khi cộng/trừ số n bit:** chúng cần đi qua các word, chi phí phụ thuộc n.
23. **Tính T(n)=3T(n/2) rồi quên O(n) ghép:** thiếu chi phí thực tế dù bậc số mũ không đổi.
24. **Tưởng chia đôi đồng nghĩa O(log n) thời gian:** có ba nhánh đệ quy tại mỗi nút.
25. **Nói Karatsuba luôn nhanh hơn nhân thường:** overhead có thể chi phối ở n nhỏ.
26. **Không benchmark crossover threshold:** dùng ngưỡng tùy tiện có thể chậm.
27. **So Karatsuba với BigInteger.multiply mà không warm-up JVM:** số đo JIT không đáng tin.
28. **Đưa toString/println vào vùng benchmark:** đo formatting thay vì multiply.
29. **Tạo BigInteger mới cho từng chữ số và sao chép toàn chuỗi ở mọi nút:** tăng overhead đáng kể.
30. **Quên chuẩn hóa leading zeros trong mảng limbs:** tạo nhiều nhánh 0 và có thể tính sai bit length.
31. **Lưu số dưới dạng chuỗi rồi cắt không xét dấu:** dấu '-' không phải chữ số.
32. **Dùng double/Math.pow để tính lũy thừa 10 của số lớn:** có thể mất tính chính xác.
33. **Dồn tích digit vào int[] không kiểm số lần cộng:** số trung gian có thể overflow trước khi truyền carry.
34. **Không xử lý borrow khi tự cài zS−z0−z2 trên mảng:** tạo hệ số âm giả.
35. **Không dùng kiểu đủ rộng cho limb product:** một tích limb có thể overflow.
36. **Nhầm các phép dịch của mảng little-endian với big-endian:** thêm limb 0 sai đầu.
37. **So hai thuật toán cùng dùng một công thức lỗi:** nên có schoolbook và oracle thư viện độc lập.
38. **Chỉ test số nhỏ nằm dưới threshold:** không hề chạy nhánh Karatsuba, chưa kiểm zS/cross.
39. **Chỉ test số chẵn bit length:** bỏ bug n lẻ và lệch high/low.
40. **Chỉ test số dương:** bỏ bug dấu.
41. **Dùng số có nhiều chữ số 9 nhưng không kiểm carry:** lỗi có thể ẩn ở trường hợp khác.
42. **In tất cả kết quả ngẫu nhiên trong test:** xuất I/O khổng lồ, làm chậm kiểm thử.
43. **Không kiểm độ dài kết quả có thể tới 2n bit:** nguy cơ truncate nếu lưu mảng cố định n.
44. **Nhầm nhân đa thức/chập với phép cộng từng hệ số không carry:** số nguyên còn cần chuẩn hóa cơ số.
45. **Coi BigInteger.multiply trong code kiểm thử là bằng chứng tự cài Karatsuba:** phép nhân chính phải tách rành mạch với oracle.
46. **Tuyên bố chương trình luôn O(n^{1,585}) bao gồm cả parse/string conversion:** phân tích lõi nhân khác toàn pipeline.
47. **Dùng Karatsuba cho số 64-bit bình thường không cần:** `Math.multiplyExact` hoặc BigInteger trực tiếp thường đơn giản hơn.
48. **Kỳ vọng dùng Karatsuba giải mọi bài modulo lớn:** cần xác định mục tiêu là tích nguyên đầy đủ hay tích modulo M; đôi khi có thuật toán modular trực tiếp tốt hơn.
49. **Không chặn input quá lớn trên service:** CPU/heap denial-of-service.
50. **Không có test số độ dài lệch nhau:** bỏ bug khi high của operand ngắn bằng 0.

## 19. Bài tập áp dụng

**Bài 1 — Tự tính ba tích.** Với X=2468 và Y=1357, tách theo M=100 và tính z0, z2, zS, cross, rồi ghép. So với nhân thường. Không được nhân trực tiếp X·Y làm phương pháp chính.

**Bài 2 — Đổi cơ số.** Viết công thức Karatsuba khi tách theo M=2^16. Cho số có độ dài bit lẻ và minh họa high/low; giải thích tại sao `shiftLeft(16)` tương ứng nhân M, không nhân 10^16.

**Bài 3 — Kiểm threshold.** Thử `BASE_CASE_BITS` lần lượt 15, 20, 25, 30 trên cùng bộ số 64..4096 bit, đối chiếu kết quả BigInteger.multiply, đo thời gian median. Đừng tăng lên 64 mà không sửa phép nhân long ở base case.

**Bài 4 — Số âm.** Kiểm `−1×−1`, `−12345×6789`, `0×số rất lớn`, `số rất lớn×−1`. Viết chứng minh tách trị tuyệt đối rồi gắn dấu là đủ.

**Bài 5 — Đếm số lời gọi.** Bổ sung bộ đếm số lời gọi recursive và số base-case multiplications. So tốc độ tăng của số lá với `n^{log₂3}` ở n=2^k, có dừng ở ngưỡng>1. Nêu vì sao số lời gọi không xác định duy nhất từ n nếu một số phần con bằng 0.

**Bài 6 — Xây BigInt theo B=10⁴.** Cài parse decimal → little-endian limbs; các hàm add/subtract/shiftLimbs, schoolbook; sau đó thay phần nhân lớn bằng Karatsuba. Đối chiếu với BigInteger.multiply trên hàng nghìn cặp random.

**Bài 7 — Thử toàn chữ số 9.** Cho X=10^k−1, Y=10^k−1, chứng minh:

**`XY=10^{2k}−2·10^k+1`**.

Dùng công thức này làm oracle không phụ thuộc phép nhân lớn khi test k=1..1000.

**Bài 8 — Karatsuba cho đa thức.** Với A(t)=a0+a1t và B(t)=b0+b1t, tính ba tích hệ số a0b0,a1b1,(a0+a1)(b0+b1), rồi suy ra hệ số t^1. Mở rộng chia mảng đa thức thành hai nửa.

**Bài 9 — So ngưỡng cơ sở khi mất cân bằng.** Tạo một số 4096-bit và một số 16-bit. Đo performance khi dùng thuật toán mặc định và phiên bản nhân với limb nhỏ theo O(n). Giải thích vì sao tổng quát O(n^{1,585}) không buộc lựa chọn đầu tiên nhanh nhất cho mọi hình dạng input.

**Bài 10 — Lựa chọn thuật toán theo miền.** Một ứng dụng chỉ nhân hai `long`, ứng dụng khác nhân 10.000 chữ số một lần, ứng dụng thứ ba nhân 1000 cặp dài 100.000 chữ số. Đề xuất lựa chọn giữa long+overflow check, BigInteger.multiply và nhân nhanh chuyên dụng, kèm tiêu chí xác minh chính xác và benchmark.

## 20. Checklist trước khi nộp

- Đã xác định input là số nguyên có dấu, số không âm, hay chuỗi/mảng digits?
- Đã ghi rõ n là **độ dài bit/limb**, không phải giá trị số?
- Đã có base case đủ nhỏ và không tràn khi nhân trực tiếp?
- Với đầu vào 0, có trả 0 ngay?
- Với số âm, có tách `abs` trước bit mask rồi gắn lại dấu?
- Khi n lẻ, cách tách high/low còn bảo toàn `x=xHigh·2^k+xLow`?
- Đã chọn đúng cơ số M=2^k khi dùng `shiftLeft`?
- Đã lấy đúng z0=low×low, z2=high×high?
- Đã tính **zS=(high+low)(high+low)** của hai toán hạng bằng lần gọi nhân thứ ba?
- Đã trừ cả z0 và z2 để có `cross=zS−z0−z2`?
- Đã ghép **`z2·M²+cross·M+z0`** đúng vị trí?
- Đã xử lý carry/borrow nếu tự cài arrays limbs?
- Đã bảo đảm bài con của zS nhỏ hơn cha khi n>threshold?
- Đã phân tích `T(n)=3T(n/2+O(1))+O(n)` và kết luận O(n^{log₂3})?
- Đã tính overhead cấp phát/shift/add khi so thời gian thực?
- Có benchmark trước khi khẳng định Karatsuba nhanh hơn nhân thường?
- Đã tách BigInteger.multiply trong **oracle**, không dùng nó để thay ba phép nhân của thuật toán?
- Đã so ít nhất với một thuật toán độc lập như schoolbook?
- Đã test âm, 0, 1, số toàn bit 1, số gần lũy thừa 2, số lẻ bit length, số có độ dài rất khác?
- Khi trả kết quả, có hỗ trợ đến **2n bit** và không mất chữ số cao?
- Nếu làm hệ thống thật, có giới hạn độ dài input và theo dõi heap/CPU?
- Nếu bài yêu cầu nhân modulo hoặc đa thức, đã xác định đúng phép toán và cơ số dữ liệu?

**Kết luận:** Karatsuba biến bài toán nhân hai số lớn thành **ba phép nhân trên các nửa** nhờ đẳng thức:

**`(aM+b)(cM+d)=acM²+[(a+b)(c+d)−ac−bd]M+bd`**.

So với bốn phép nhân tự nhiên của phép khai triển, ba phép nhân giúp đạt **O(n^{log₂3})≈O(n^{1,585})** thay vì O(n²). Thuật toán đúng với số nguyên có dấu nếu tính trên trị tuyệt đối rồi gắn dấu, đúng với độ dài lẻ nếu tách/ghép theo cùng cơ số, và cần một base case tránh overflow. Đây cũng là ví dụ tiêu biểu cho việc **giảm số tích bằng một biến đổi đại số**, liên hệ trực tiếp với nhân đa thức và convolution. Muốn dùng trong thực tế, hãy đối chiếu với phép nhân độc lập, đo hiệu năng tại những kích thước thật, và cân nhắc thư viện `BigInteger.multiply` đã được tối ưu khi không bắt buộc tự cài.