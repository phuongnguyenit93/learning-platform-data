# Phân biệt sai số phương pháp với sai số dấu phẩy động

Trong **thuật toán số**, kết quả gần đúng có thể sai vì **bản thân phương pháp là xấp xỉ** hoặc vì **máy tính làm tròn khi biểu diễn, cộng, trừ, nhân, chia**. Hai nguyên nhân này khác nhau và cần được chẩn đoán riêng.

- **Sai số phương pháp** (method/truncation/discretization/iteration error): sai số vẫn tồn tại nếu mọi phép toán được thực hiện bằng số học thực chính xác, vì ta dùng công thức gần đúng, bước lưới hữu hạn hoặc chỉ chạy hữu hạn vòng.
- **Sai số dấu phẩy động** (representation/roundoff error): sai số do các số thực không luôn biểu diễn được bằng số bit hữu hạn, và các phép toán phải làm tròn về những giá trị máy có thể lưu.
- **Sai số dữ liệu và mô hình**: đầu vào đo đạc hoặc mô hình vật lý đã không chính xác, độc lập với hai loại sai số trên.
- **Độ điều kiện (conditioning)**: độ nhạy của kết quả toán học khi dữ liệu đầu vào thay đổi nhỏ; không đồng nhất với tính ổn định của code.

Điểm thực hành quan trọng nhất là **giảm bước h không phải lúc nào cũng làm đáp án tốt hơn**. Khi h giảm, sai số phương pháp có thể giảm trong khi sai số làm tròn **tăng** do phép trừ hai số gần nhau và phép chia cho h.

Bài học này thuộc **Thuật toán số**, giới thiệu mô hình sai số định lượng, đạo hàm bằng sai phân, tích phân hình thang, chia đôi tìm nghiệm, ULP, cancellation, cộng có bù, công thức bậc hai ổn định, BigDecimal/BigInteger, chương trình **Java 17+ chạy độc lập**, cách QA độc lập và giới hạn của các kết luận sai số.

## 1. Một kết quả sai có thể có nhiều nguyên nhân

Giả sử chương trình tính gần đúng giá trị đạo hàm tại một điểm. Có bốn câu hỏi khác nhau:

1. **Bài toán gốc có đúng mô tả thực tế không?** Ví dụ dữ liệu đo đã sai hoặc mô hình bỏ qua lực ma sát.
2. **Phương pháp có thay bài toán gốc bằng bài toán gần đúng không?** Ví dụ lấy đạo hàm bằng sai phân tiến với h>0.
3. **Phép toán máy có bảo toàn giá trị số học không?** Ví dụ 0.1 không có biểu diễn nhị phân hữu hạn trong double.
4. **Bài toán và phép tính có nhạy với perturbation không?** Ví dụ lấy hiệu hai số gần bằng nhau hoặc giải một hệ gần suy biến.

Không nên gọi tất cả những sai lệch này là “lỗi floating point”.

| Nguồn | Ví dụ | Có thể khắc phục bằng cách nào? |
| --- | --- | --- |
| Mô hình | Chọn phương trình vật lý không phù hợp | Xây mô hình đúng |
| Dữ liệu | Đo sai 1 mm | Đo/hiệu chuẩn tốt hơn |
| Phương pháp | Sai phân h=0.1 thay đạo hàm | Giảm h hợp lý, đổi phương pháp bậc cao |
| Roundoff | Trừ các giá trị double gần nhau | Công thức ổn định, precision phù hợp |
| Conditioning | Nghiệm thay đổi mạnh khi input đổi nhỏ | Phân tích độ nhạy, cải thiện dữ liệu/bài toán |

Một thuật toán ổn định không sửa được một mô hình sai. Tương tự, tính double với độ chính xác cao hơn không thể làm một phương pháp xấp xỉ hữu hạn tự nhiên trở thành phép tính toán học chính xác.

## 2. Định nghĩa chính xác ba đại lượng

Để tách hai loại sai số, đặt:

- **u**: nghiệm toán học chính xác.
- **u_h**: kết quả của phương pháp với bước h (hoặc số vòng k), giả sử các phép toán trong phương pháp được thực hiện bằng **số thực chính xác**.
- **û_h**: kết quả thực sự tính được bằng floating point khi triển khai phương pháp trên máy.

Khi cùng một dữ liệu và cùng một thuật toán được dùng để định nghĩa các đại lượng, ta có:

**û_h−u = (u_h−u) + (û_h−u_h)**.

Vì vậy:

**Sai số tổng = sai số phương pháp + sai số số học máy**.

Cụ thể:

**e_method=u_h−u**.

**e_float=û_h−u_h**.

Và:

**|û_h−u|≤|e_method|+|e_float|**.

Đây là phân rã **có dấu**: hai thành phần có thể triệt tiêu nhau tình cờ. Không nên cộng trực tiếp giá trị tuyệt đối rồi khẳng định đó là lỗi thực tế chính xác.

### Khi đầu vào cũng sai

Nếu giá trị đầu vào thực là d nhưng chương trình nhận d̃, cần thêm thành phần **F(d̃)−F(d)** hoặc một phân rã khác phù hợp. Không được giấu sai số đầu vào vào mục “roundoff” nếu dữ liệu đã sai trước khi tới máy tính.

### Khi không biết u chính xác

Nhiều bài toán thực tế không có nghiệm giải tích đơn giản. Ta cần:

- Một nghiệm tham chiếu nhiều precision hơn.
- Một cận sai số toán học.
- Một oracle độc lập.
- Hoặc các kiểm tra hội tụ và bất biến có cơ sở lý thuyết.

Không thể chỉ nhìn một kết quả double rồi đo chính xác được từng thành phần sai số mà không có thông tin tham chiếu.

## 3. Sai số tuyệt đối, tương đối và residual

Với giá trị đúng u và kết quả x:

**Sai số tuyệt đối:** E_abs=|x−u|.

**Sai số tương đối:** E_rel=|x−u|/|u|, khi u≠0.

Ví dụ:

- u=1000, x=999 ⇒ E_abs=1, E_rel=0.001.
- u=0.001, x=0.002 ⇒ E_abs=0.001, E_rel=1.

Khi u=0, E_rel theo công thức này **không xác định**. Nếu u rất nhỏ, E_rel cũng có thể rất lớn dù E_abs nhỏ.

### Tolerance kết hợp

Khi kiểm thử kết quả số thực, một tiêu chí thường hữu ích là:

**|actual−expected|≤atol+rtol·|expected|**.

Trong đó:

- **atol**: ngưỡng sai số tuyệt đối theo đơn vị bài toán.
- **rtol**: ngưỡng sai số tương đối.
- Cả hai phải xuất phát từ yêu cầu độ chính xác và thang đo dữ liệu, không lấy máy móc một hằng số EPS cho mọi bài.

### Residual khác sai số nghiệm

Trong bài tìm nghiệm f(x)=0, **residual=|f(x)|**. Residual nhỏ không tự bảo đảm x gần nghiệm nếu f rất phẳng hoặc bài toán kém điều kiện.

Ví dụ f(x)=10^−12(x−1) có nghiệm đúng x=1. Nhưng tại x=2, residual chỉ bằng 10^−12, còn sai số của x là **1**.

## 4. Sai số phương pháp tồn tại ngay cả với số học hoàn hảo

Các trường hợp điển hình:

1. **Sai phân đạo hàm:** dùng [f(x+h)−f(x)]/h thay f'(x).
2. **Tích phân số:** thay tích phân bằng tổng diện tích hình thang.
3. **Dừng lặp:** trả trung điểm sau 20 lần chia đôi thay nghiệm chính xác.
4. **Cắt chuỗi vô hạn:** dùng vài số hạng của khai triển Taylor.
5. **Rời rạc hóa phương trình vi phân:** dùng lưới hữu hạn thay miền liên tục.
6. **Nội suy/xấp xỉ đa thức:** thay một hàm khác bằng đa thức bậc giới hạn.

Trong các trường hợp ấy, bản thân công thức gần đúng là nguồn lỗi. Nó không cần CPU hoặc double để xuất hiện.

### Truncation error không đồng nghĩa ép kiểu

Trong numerical analysis, **truncation error** thường chỉ việc cắt chuỗi hoặc giới hạn bậc/phương pháp. Trong lập trình, “truncate” còn có thể chỉ **bỏ phần thập phân khi ép kiểu**, là hành vi biểu diễn số. Hai khái niệm có tên gần nhau nhưng vai trò khác nhau.

## 5. Sai phân tiến và bậc sai số O(h)

Với hàm đủ trơn, định nghĩa:

**D⁺_h f(x)=[f(x+h)−f(x)]/h**, h>0.

Khai triển Taylor:

**f(x+h)=f(x)+h f'(x)+(h²/2)f''(x)+O(h³)**.

Suy ra:

**D⁺_h f(x)=f'(x)+(h/2)f''(x)+O(h²)**.

Sai số phương pháp thường ở bậc:

**O(h)**.

### Ví dụ phân tích được hoàn toàn

Lấy **f(x)=x³** và **x=2**.

Đạo hàm thật:

**f'(2)=3·2²=12**.

Công thức sai phân tiến trong số học thực chính xác:

**[(2+h)³−8]/h = 12+6h+h²**.

Vậy:

**e_method=6h+h²**.

Với h=0.1:

**D⁺_0.1=12.61** và **e_method=0.61**.

Không cần thực hiện bất kỳ phép tính double nào để có sai số 0.61: nó là hậu quả của công thức sai phân tiến tại h hữu hạn.

### Vì sao tăng precision không giải quyết được?

Nếu dùng phép toán decimal chính xác với h=0.1, ta vẫn nhận **12.61**, vì đó là kết quả **chính xác của công thức xấp xỉ**, không phải đạo hàm thực 12.

## 6. Sai phân trung tâm và bậc O(h²)

Sai phân trung tâm:

**D⁰_h f(x)=[f(x+h)−f(x−h)]/(2h)**.

Nếu f đủ trơn gần x, khai triển Taylor cho:

**D⁰_h f(x)=f'(x)+(h²/6)f'''(x)+O(h⁴)**.

Sai số phương pháp thường ở bậc **O(h²)**.

Với cùng f(x)=x³ tại x=2:

**[(2+h)³−(2−h)³]/(2h) = 12+h²**.

Nên:

**e_method=h²**.

Với h=0.1:

- Sai phân tiến: **12.61**, sai số phương pháp 0.61.
- Sai phân trung tâm: **12.01**, sai số phương pháp 0.01.
- Đạo hàm đúng: **12**.

Đổi từ công thức O(h) sang O(h²) giúp giảm sai số phương pháp mà **không cần thay double bằng một kiểu số khác**.

### Cần giả thiết về tính trơn

Sai phân trung tâm không tự bảo đảm O(h²) với mọi hàm. Ví dụ |x| không có đạo hàm thông thường tại x=0. Nếu f không đủ khả vi hoặc các đạo hàm cao không bị chặn trong vùng xét, công thức xấp xỉ có thể không mang bậc sai số nêu trên.

## 7. Khi giảm h, method error giảm nhưng roundoff có thể tăng

Các công thức đạo hàm số thực hiện phép trừ **hai giá trị rất gần nhau**:

**f(x+h)−f(x)** hoặc **f(x+h)−f(x−h)**.

Khi h nhỏ, tử số cũng nhỏ nhưng các toán hạng có thể có độ lớn thông thường. Sai số rounding/representation trong chúng có thể bị **chia cho h** và khuếch đại.

Một mô hình định tính thường dùng là:

**E(h) ≲ C₁h^p + C₂u/h**.

Trong đó p=1 cho sai phân tiến thường gặp, p=2 cho trung tâm, u là unit roundoff, còn C₁,C₂ tùy hàm và cách đánh giá.

- Phần **C₁h^p** giảm khi h giảm.
- Phần **C₂u/h** có thể tăng khi h giảm.

Vì vậy lỗi tổng thường có vùng **h đủ nhỏ nhưng không quá nhỏ**.

### Quy tắc cân bằng sơ bộ

Sau khi chuẩn hóa thang đo, một cách cân bằng lý tưởng cho:

- Sai phân tiến: **h cỡ sqrt(u)**.
- Sai phân trung tâm: **h cỡ u^(1/3)**.

Đây không phải ngưỡng đúng cho mọi hàm. Nếu đạo hàm bậc cao nhỏ/lớn bất thường, input gần 0, độ lớn x thay đổi hoặc hàm f được tính không ổn định, h tối ưu khác.

### Trường hợp h quá nhỏ

Nếu x+h và x−h đều làm tròn bằng x, tử số trong cả hai công thức bằng 0. Kết quả máy có thể bằng **0** dù đạo hàm thật khác 0 rất xa.

Giảm h vô điều kiện là một lỗi thiết kế thuật toán số, không phải một bước “tăng precision”.

## 8. Thực nghiệm chính xác với f(x)=x³ tại x=2

Cột “lý tưởng” là **công thức đại số của phương pháp trong số thực chính xác**, được in qua double với 9 chữ số sau dấu thập phân. Cột “double” tính **các giá trị f(x±h) rồi lấy hiệu trực tiếp trên máy**.

| h | Tiến lý tưởng | Tiến double | Trung tâm lý tưởng | Trung tâm double |
| --- | ---: | ---: | ---: | ---: |
| 0.1 | 12.610000000 | 12.610000000 | 12.010000000 | 12.010000000 |
| 10^−8 | 12.000000060 | 11.999999927 | 12.000000000 | 11.999999927 |
| 10^−12 | 12.000000000 | 12.001066807 | 12.000000000 | 12.001066807 |
| 10^−16 | 12.000000000 | 0.000000000 | 12.000000000 | 0.000000000 |

### Cách hiểu

**h=0.1:** chênh lệch lớn chủ yếu đến từ phương pháp, nên thay formula mang lại lợi ích rõ.

**h=10^−8:** công thức lý tưởng đã rất gần 12, nhưng tính bằng double từ hai giá trị gần nhau có thể sai khoảng 7.3×10^−8.

**h=10^−12:** sai số double tăng đến khoảng 0.0010668, vượt xa sai số phương pháp lý tưởng.

**h=10^−16:** 2±h làm tròn về 2 trong double, nên cả hai phép sai phân trả **0**.

Số in 9 chữ số không có nghĩa method error thật sự bằng 0 ở h rất nhỏ: ví dụ trung tâm có e_method=h², nhưng 10^−24 nhỏ hơn độ phân giải hiển thị.

### Cẩn thận khi dùng “giá trị lý tưởng” trong code

Literal 1e-8 được biểu diễn thành một binary64 gần giá trị thập phân lý tưởng. Trong phần minh họa, các công thức **12+6h+h² và 12+h²** được dùng làm chuẩn giải thích, nhưng bản thân chúng khi tính bằng Java double cũng phải làm tròn. Một phép phân rã roundoff có chứng nhận cần tham chiếu nhiều precision và quy tắc định nghĩa đầu vào thật chính xác.

## 9. Sai số biểu diễn nhị phân: 0.1+0.2

IEEE-754 binary floating point biểu diễn chính xác các số dạng **m·2^k** trong miền mantissa/exponent được cấp. Phần lớn phân số thập phân như 0.1 không có chuỗi biểu diễn nhị phân hữu hạn.

Vì thế:

~~~java
System.out.println(0.1 + 0.2);
System.out.println((0.1 + 0.2) == 0.3);
~~~

cho:

~~~text
0.30000000000000004
false
~~~

Phép cộng số thực **0.1+0.2=0.3** không sai. Kết quả khác xuất hiện do **dữ liệu nhị phân xấp xỉ và làm tròn khi cộng**.

### BigDecimal không đồng nghĩa làm phép gần đúng thành chính xác

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
System.out.println(a.add(b));
~~~

cho **0.3** vì chuỗi thập phân được lưu chính xác ở phép cộng này. Nhưng nếu tính sai phân tiến h=0.1 bằng BigDecimal thì công thức vẫn cho 12.61; đó là **method error** không bị sửa.

Không nên khởi tạo BigDecimal từ **double đã làm tròn** nếu mục tiêu là bảo toàn chính xác chuỗi thập phân người dùng nhập. BigDecimal cũng cần rounding policy cho phép chia không có khai triển thập phân hữu hạn như 1/3.

## 10. ULP, machine epsilon và unit roundoff

Với Java double dạng IEEE-754 binary64:

- Precision của significand là **53 bit**.
- **Math.ulp(1.0)=2^−52≈2.220446049250313×10^−16**.
- **Unit roundoff u≈2^−53≈1.1102230246251565×10^−16** theo mô hình phép toán round-to-nearest thông thường trong miền số chuẩn.

**ULP** liên quan đến khoảng cách giữa các số biểu diễn được quanh một độ lớn nhất định. Khoảng cách thay đổi theo exponent.

Không được coi:

- ULP của mọi số đều giống Math.ulp(1.0).
- Machine epsilon và unit roundoff là cùng một số.
- Mọi phép toán đều có sai số tương đối ≤u trong trường hợp underflow, overflow, NaN hoặc chia cho 0.

### Thí nghiệm 2^53+1

**2^53=9007199254740992**.

**2^53+1=9007199254740993** không biểu diễn chính xác được bằng double. Vì thế trong double:

~~~java
double x = 9007199254740992.0;
System.out.println(x + 1.0 == x);
~~~

in **true**.

Cộng thêm 1 trong toán học nhưng giá trị máy không đổi. Đây là **roundoff/representation**, không phải sai số phương pháp.

Nếu yêu cầu giữ chính xác số nguyên lớn, dùng **BigInteger**, không dùng double chỉ vì nó có phạm vi exponent rất lớn.

## 11. Không kết hợp và triệt tiêu khi cộng số

Trong số thực, phép cộng có tính kết hợp. Trong floating point, mỗi phép cộng có thể làm tròn nên:

**fl(fl(a+b)+c)** có thể khác **fl(a+fl(b+c))**.

Ví dụ dãy:

**[10^16,1,−10^16]**.

Tổng toán học bằng **1**.

Nếu cộng tuần tự bằng double:

1. 10^16+1 làm tròn thành 10^16.
2. 10^16−10^16=0.

Kết quả naïve bằng **0**.

Nếu cộng 10^16−10^16 trước rồi mới +1, kết quả bằng **1**.

### Cancellation và lỗi đã có trước phép trừ

Không nên phát biểu “phép trừ hai số gần bằng nhau luôn tự sinh lỗi lớn”. Đôi khi phép trừ hai giá trị floating point đã được biểu diễn có thể chính xác (liên hệ **định lý Sterbenz**).

Vấn đề thường là hai giá trị **đã có sai số trước phép trừ**; lấy hiệu nhỏ làm những sai số ấy trở nên lớn so với kết quả cần tìm.

Ví dụ, (10^16+1)−10^16 phải bằng 1, nhưng toán hạng đầu đã bị làm tròn thành 10^16. Phép trừ cuối 10^16−10^16 có thể **chính xác** và vẫn trả kết quả sai so với bài toán gốc.

## 12. Độ điều kiện của phép trừ và tính ổn định

Đối với y=a−b, với y≠0, một condition number tương đối cho perturbation tương đối của hai đầu vào có dạng:

**κ≈(|a|+|b|)/|a−b|**.

Khi a≈b, mẫu rất nhỏ nên κ rất lớn. Một nhiễu tương đối nhỏ trong các toán hạng có thể gây sai lệch tương đối lớn ở hiệu.

### Conditioning và stability là hai thuộc tính khác nhau

**Conditioning:** bài toán toán học có nhạy với thay đổi input không?

**Numerical stability:** thuật toán có khuếch đại lỗi số học máy vô lý không?

Một thuật toán backward stable có thể cho kết quả chính xác của **một bộ dữ liệu nhiễu rất nhỏ**. Nhưng nếu bài toán kém điều kiện, output có thể vẫn khác nghiệm của dữ liệu gốc khá nhiều.

Ngược lại, một bài toán ổn định về mặt điều kiện vẫn có thể được giải bằng công thức máy kém ổn định.

### Forward error và backward error

- **Forward error**: khoảng cách giữa kết quả máy với đáp án thật.
- **Backward error**: mức thay đổi input nhỏ nhất (theo một chuẩn thích hợp) để coi kết quả máy là nghiệm chính xác của bài toán bị perturbation.

Đừng đánh giá stability chỉ bằng việc thấy một test ra nhiều chữ số có vẻ đúng. Các trường hợp gần suy biến mới thường bộc lộ lỗi.

## 13. Công thức nghiệm bậc hai: đại số tương đương, số học khác nhau

Với:

**a x²+b x+c=0**, a≠0,

công thức:

**x=(-b±sqrt(b²−4ac))/(2a)**

đúng trên số thực khi discriminant không âm. Nhưng khi -b gần sqrt(discriminant), nghiệm nhỏ được tính bằng **phép trừ hai số gần bằng nhau**, dễ bị mất nhiều bit có nghĩa.

### Ví dụ a=1, b=−10^16, c=1

Phương trình:

**x²−10^16x+1=0**.

Nghiệm lớn xấp xỉ 10^16; nghiệm nhỏ xấp xỉ **10^−16**.

Trong double, sqrt(b²−4) có thể làm tròn thành 10^16. Vì vậy:

**(-b−sqrt(...))/2**

bị làm tròn thành **0**.

### Công thức ổn định hơn

Tính:

**q=−0.5(b+sign(b)·sqrt(b²−4ac))**.

Sau đó dùng Viète:

**x_large=q/a**.

**x_small=c/q**.

Với bộ hệ số trên, phép chia c/q cho nghiệm nhỏ xấp xỉ **1.0E−16**, thay vì 0.

### Điều kiện giới hạn

Nếu q=0, discriminant âm, b²−4ac overflow, underflow hoặc hệ số bị scale quá chênh lệch, phải có xử lý bổ sung. Đây là ví dụ về **đổi cách tính để giảm roundoff**, không phải một solver hoàn chỉnh cho mọi trường hợp.

Một biểu thức **đúng trong đại số** chưa chắc là một biểu thức **ổn định trên double**.

## 14. Cộng bù sai số: Neumaier

Để tính tổng nhiều số chênh độ lớn, một cách cải thiện là **compensated summation**.

Thuật toán Neumaier giữ hai biến **sum** và **compensation**:

~~~text
sum = 0
compensation = 0

for x in values:
    next = sum + x

    if abs(sum) >= abs(x):
        compensation += (sum - next) + x
    else:
        compensation += (x - next) + sum

    sum = next

return sum + compensation
~~~

Trên dãy **[10^16,1,−10^16]**:

- Tổng bằng số thực chính xác: 1.
- Naive double sum: **0**.
- Neumaier sum: **1**.

### Không phải phép màu

Neumaier vẫn tính bằng double; compensation cũng có thể bị làm tròn. Nếu input gốc đã được chuyển sai thành double, không thể tự khôi phục một số nguyên hay một số thập phân bị mất chữ số từ thông tin không còn.

**Kahan summation** cũng là một kỹ thuật có bù, nhưng không phải một thuật toán giống hệt Neumaier. Kahan không bảo đảm lấy lại 1 cho mọi thứ tự triệt tiêu mạnh ở ví dụ trên. Không được đồng nhất hai biến thể hoặc hứa kết quả chính xác tuyệt đối.

### Pairwise summation

Một kỹ thuật khác là cộng theo cây cân đối thay vì cộng từ trái sang phải. Nó có thể giảm chiều sâu tích lũy roundoff với nhiều dãy dữ liệu, nhưng không có bảo đảm sẽ chính xác trong mọi tình huống.

## 15. Tích phân hình thang: method error không liên quan roundoff

Xét tích phân:

**I=∫₀¹ x² dx = 1/3**.

Quy tắc hình thang ghép với n đoạn đều, h=1/n:

**T_n=h[(f(0)+f(1))/2+Σ từ i=1 đến n−1 f(ih)]**.

Với f(x)=x², ta có công thức đại số chính xác:

**T_n=1/3+1/(6n²)**.

Vì vậy:

**e_method=T_n−I=1/(6n²)**.

### Ví dụ n=4

**T₄=0.34375**.

**I=1/3≈0.33333333**.

Sai số phương pháp:

**1/96≈0.01041667**.

Sai số vẫn tồn tại nếu tính tổng bằng hữu tỉ chính xác. Nó đến từ **thay đường cong bằng các đoạn thẳng** trong quy tắc hình thang.

### Bậc hội tụ

Khi tăng n, h=1/n giảm và method error trong ví dụ này giảm theo **O(h²)**.

Nhưng việc tăng n cũng làm tăng số phép cộng và số lần đánh giá hàm. Với n cực lớn, roundoff, thời gian và memory có thể trở thành giới hạn. Nếu cần accuracy cao, một quy tắc tích phân bậc cao hơn hoặc biến đổi giải tích có thể tốt hơn việc tăng n không giới hạn.

## 16. Chia đôi tìm nghiệm: sai số do dừng lặp

Giải:

**f(x)=x²−2=0** trên [1,2].

Nghiệm dương chính xác là **sqrt(2)**.

Bisection liên tiếp giữ nửa đoạn mà hai đầu có dấu f trái nhau.

Nếu việc xét dấu là chính xác, sau k lần thu hẹp:

**R_k−L_k=(R₀−L₀)/2^k**.

Nếu trả midpoint:

**|x_k−x*|≤(R_k−L_k)/2**.

### Sau 12 vòng

Với [1,2]:

**Width=1/4096=0.000244140625**.

**Midpoint=1.4141845703125**.

**Cận sai số nghiệm theo khoảng=0.0001220703125**.

Sai số do dừng tại 12 vòng là **method/iteration error**. Dù số học thật chính xác, không có lý do midpoint hữu hạn phải trùng sqrt(2).

### Sai số máy có thể phá cả invariant

- Midpoint có thể làm tròn bằng L hoặc R khi hai đầu quá gần.
- f(mid) có thể có dấu tính sai do đánh giá không ổn định.
- Phép (L+R)/2 có thể overflow nếu L,R rất lớn.
- Bisection cần **giữ nghiệm trong interval**; nếu phép đánh giá dấu sai, cận lỗi dựa trên width không còn được bảo đảm.

Đừng chỉ tăng số vòng để “chắc chắn hơn”; cần kiểm tra **stagnation** và điều kiện của phép tính f.

## 17. Residual nhỏ không bảo đảm sai số nghiệm nhỏ

Cho:

**f(x)=10^−12(x−1)**.

Nghiệm chính xác x*=1. Tại x=2:

**|f(2)|=10^−12**,

dù:

**|x−x*|=1**.

Nếu chỉ dùng tiêu chí “dừng khi residual<10^−9”, chương trình chấp nhận x=2 sai nhiều.

Để suy từ residual sang khoảng cách nghiệm thường cần:

- Một cận dưới của |f'| gần nghiệm.
- Một chứng minh về tính đơn điệu/đơn ánh.
- Một khoảng nghiệm có chứng nhận.
- Hoặc điều kiện số thích hợp.

### Vai trò của conditioning

Hàm có thể thay đổi rất ít khi x thay đổi nhiều, nên residual nhỏ chưa đủ thông tin về x. Đây là **vấn đề độ nhạy/quy mô**, không nhất thiết là roundoff.

## 18. Biểu diễn và phép tính trong Java 17+

**double** có 53 bit significand và exponent hữu hạn. Nó là lựa chọn nhanh, phù hợp nhiều phép tính số thực có tolerance hợp lý.

**BigInteger** lưu số nguyên chính xác vượt int/long, miễn đủ tài nguyên.

**BigDecimal** lưu số thập phân theo unscaled integer + scale; tiện khi input và output có ngữ nghĩa decimal như tiền hoặc số đo đã lượng tử hóa. Nhưng BigDecimal.divide có thể cần rounding mode và precision, vì các số như 1/3 không có khai triển thập phân hữu hạn.

### Khởi tạo BigDecimal đúng nguồn

Để giữ chính xác decimal mà người dùng nhập:

~~~java
BigDecimal exactDecimal = new BigDecimal("0.1");
~~~

Không nhầm với:

~~~java
BigDecimal exactBinaryValue = new BigDecimal(0.1);
~~~

Cách thứ hai chuyển **giá trị double đã xấp xỉ 0.1** thành decimal chính xác của chính giá trị nhị phân ấy. Nó không khôi phục 1/10 về mặt thập phân từ một thông tin đã bị làm tròn.

### BigDecimal không xóa method error

Dùng BigDecimal để tính công thức sai phân tiến tại h=0.1 vẫn cho kết quả gần đúng 12.61. Nó chỉ thay cách thực hiện phép tính, không thay phương pháp toán học.

### Math.fma

Trong một biểu thức dạng **a*b+c**, Math.fma có thể thực hiện phép nhân-cộng với **một lần làm tròn cuối**, hữu ích trong một số thuật toán ổn định. Nhưng nó không biến mọi chuỗi phép toán thành số thực chính xác, và không sửa được method error.

### Java 17 strict floating-point

Java 17 dùng ngữ nghĩa floating point strict cho biểu thức số thực; điều đó làm hành vi của ngôn ngữ được xác định rõ hơn, **không** có nghĩa phép toán double không làm tròn.

## 19. Java 17+ hoàn chỉnh: chương trình minh họa

Chương trình dưới đây **không đọc stdin** vì các bài tập có format khác nhau. Nó chạy các tình huống cố định và in stdout có thể đối chiếu:

- 0.1+0.2 và ULP.
- Mất một đơn vị tại 2^53.
- Sai phân với 4 mức h, bên cạnh công thức phương pháp lý tưởng.
- Chia đôi tìm sqrt(2) trong 12 vòng.
- Tích phân hình thang n=4.
- Naive sum và Neumaier.
- Nghiệm bậc hai nhỏ tính trực tiếp và tính ổn định.
- BigDecimal trừ hai số thập phân lớn.

**Tên tệp: NumericalErrorSourcesDemo.java**

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.Locale;

public class NumericalErrorSourcesDemo {

    static double cubic(double x) {
        return x * x * x;
    }

    static double forwardDifference(double x, double h) {
        return (cubic(x + h) - cubic(x)) / h;
    }

    static double centralDifference(double x, double h) {
        return (cubic(x + h) - cubic(x - h)) / (2.0 * h);
    }

    // Exact algebraic formulas at x=2 in real arithmetic,
    // evaluated as double only for comparison and display.
    static double idealForwardAtTwo(double h) {
        return 12.0 + 6.0 * h + h * h;
    }

    static double idealCentralAtTwo(double h) {
        return 12.0 + h * h;
    }

    record Bracket(double left, double right) {
        double middle() {
            return left + (right - left) / 2.0;
        }

        double halfWidth() {
            return (right - left) / 2.0;
        }
    }

    static Bracket bisectionSqrtTwo(int steps) {
        if (steps < 0) {
            throw new IllegalArgumentException(
                    "steps must be nonnegative");
        }

        double left = 1.0;
        double right = 2.0;

        for (int i = 0; i < steps; i++) {
            double mid = left + (right - left) / 2.0;

            // Stop if midpoint can no longer move.
            if (mid == left || mid == right) break;

            double value = mid * mid - 2.0;

            if (value == 0.0) {
                return new Bracket(mid, mid);
            } else if (value < 0.0) {
                left = mid;
            } else {
                right = mid;
            }
        }

        return new Bracket(left, right);
    }

    static double trapezoidSquare(int pieces) {
        if (pieces <= 0) {
            throw new IllegalArgumentException(
                    "pieces must be positive");
        }

        double h = 1.0 / pieces;
        double sum = 0.5; // (f(0)+f(1))/2 for f(x)=x^2.

        for (int i = 1; i < pieces; i++) {
            double x = i * h;
            sum += x * x;
        }

        return h * sum;
    }

    static double naiveSum(double[] values) {
        double sum = 0.0;
        for (double value : values) {
            sum += value;
        }
        return sum;
    }

    static double neumaierSum(double[] values) {
        double sum = 0.0;
        double compensation = 0.0;

        for (double value : values) {
            double next = sum + value;

            if (Math.abs(sum) >= Math.abs(value)) {
                compensation += (sum - next) + value;
            } else {
                compensation += (value - next) + sum;
            }

            sum = next;
        }

        return sum + compensation;
    }

    public static void main(String[] args) {

        System.out.println("Double 0.1+0.2: "
                + (0.1 + 0.2));

        System.out.println("Double sum equals 0.3: "
                + ((0.1 + 0.2) == 0.3));

        BigDecimal decimalSum =
                new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));

        System.out.println("Decimal 0.1+0.2: "
                + decimalSum);

        System.out.println("ULP(1.0): "
                + Math.ulp(1.0));

        double two53 = 9007199254740992.0;

        System.out.println("2^53+1 equals 2^53 in double: "
                + (two53 + 1.0 == two53));

        System.out.println("Exact integer 2^53+1: "
                + BigInteger.ONE.shiftLeft(53)
                        .add(BigInteger.ONE));

        String[] labels = {
                "0.1", "1e-8", "1e-12", "1e-16"
        };
        double[] steps = {
                0.1, 1e-8, 1e-12, 1e-16
        };

        for (int i = 0; i < steps.length; i++) {
            double h = steps[i];

            System.out.printf(Locale.ROOT,
                    "Derivative h=%s: forward=%.9f, "
                    + "central=%.9f, idealForward=%.9f, "
                    + "idealCentral=%.9f%n",
                    labels[i],
                    forwardDifference(2.0, h),
                    centralDifference(2.0, h),
                    idealForwardAtTwo(h),
                    idealCentralAtTwo(h));
        }

        Bracket bracket = bisectionSqrtTwo(12);

        System.out.printf(Locale.ROOT,
                "Bisection 12: x=%.8f, width=%.8f, "
                + "halfBound=%.8f%n",
                bracket.middle(),
                bracket.right() - bracket.left(),
                bracket.halfWidth());

        double integral = trapezoidSquare(4);

        System.out.printf(Locale.ROOT,
                "Trapezoid x^2 n=4: value=%.8f, "
                + "methodError=%.8f%n",
                integral, integral - 1.0 / 3.0);

        double[] values = { 1e16, 1.0, -1e16 };

        System.out.println("Sum [1e16,1,-1e16]: naive="
                + naiveSum(values)
                + ", neumaier=" + neumaierSum(values));

        double a = 1.0;
        double b = -1e16;
        double c = 1.0;

        double sqrtDiscriminant =
                Math.sqrt(b * b - 4 * a * c);

        double naiveSmall =
                (-b - sqrtDiscriminant) / (2.0 * a);

        double q = -0.5 * (
                b + Math.copySign(sqrtDiscriminant, b));
        double stableSmall = c / q;

        System.out.println("Quadratic small root: naive="
                + naiveSmall + ", stable=" + stableSmall);

        System.out.println("Exact decimal difference: "
                + new BigDecimal("10000000000000001")
                .subtract(new BigDecimal(
                        "10000000000000000")));
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 NumericalErrorSourcesDemo.java
java NumericalErrorSourcesDemo
~~~

**Đầu ra mẫu:**

~~~text
Double 0.1+0.2: 0.30000000000000004
Double sum equals 0.3: false
Decimal 0.1+0.2: 0.3
ULP(1.0): 2.220446049250313E-16
2^53+1 equals 2^53 in double: true
Exact integer 2^53+1: 9007199254740993
Derivative h=0.1: forward=12.610000000, central=12.010000000, idealForward=12.610000000, idealCentral=12.010000000
Derivative h=1e-8: forward=11.999999927, central=11.999999927, idealForward=12.000000060, idealCentral=12.000000000
Derivative h=1e-12: forward=12.001066807, central=12.001066807, idealForward=12.000000000, idealCentral=12.000000000
Derivative h=1e-16: forward=0.000000000, central=0.000000000, idealForward=12.000000000, idealCentral=12.000000000
Bisection 12: x=1.41418457, width=0.00024414, halfBound=0.00012207
Trapezoid x^2 n=4: value=0.34375000, methodError=0.01041667
Sum [1e16,1,-1e16]: naive=0.0, neumaier=1.0
Quadratic small root: naive=0.0, stable=1.0E-16
Exact decimal difference: 1
~~~

### Đọc kết quả theo từng nguồn sai số

- **Double 0.1+0.2:** representation/roundoff.
- **Decimal sum:** cùng phép cộng, nhưng kiểu dữ liệu phù hợp giữ chính xác chuỗi decimal.
- **Sai phân h=0.1:** method error còn lớn.
- **Sai phân h nhỏ:** roundoff và cancellation chi phối.
- **Bisection 12:** error do dừng sớm được đo qua interval width.
- **Trapezoid n=4:** error do phương pháp xấp xỉ tích phân.
- **Naive vs Neumaier:** hai cách triển khai tổng trên cùng input khác nhau vì roundoff.
- **Nghiệm bậc hai:** công thức đại số tương đương nhưng độ ổn định khác nhau.
- **BigDecimal difference:** giữ chính xác hiệu của hai số nguyên thập phân lớn.

### Giới hạn chương trình

Chương trình minh họa các trường hợp cố định, không phải bộ máy chứng nhận error bound cho mọi bài toán. Công thức “lý tưởng” được trình bày theo đại số nhưng hiển thị bằng double, nên bản thân bản in vẫn có làm tròn. Số vòng bisection và các giả thiết f trong ví dụ đã được chọn để minh họa rõ hai nguồn sai số; không có bảo đảm những thiết lập ấy tự thích hợp với một hàm black-box bất kỳ.

## 20. QA phân tách nguyên nhân bằng oracle độc lập

Nên QA trong ba tầng:

### Tầng 1 — Nghiệm hoặc cận toán học

Nếu có thể, viết nghiệm giải tích:

- f(x)=x³ ⇒ f'(2)=12.
- ∫₀¹x² dx=1/3.
- f(x)=x²−2 ⇒ nghiệm dương sqrt(2).
- Tổng [10^16,1,−10^16]=1.

Đây là mục tiêu đối chiếu cuối cùng.

### Tầng 2 — Phương pháp trong số học lý tưởng

Tính riêng:

- Sai phân tiến tại 2: **12+6h+h²**.
- Sai phân trung tâm tại 2: **12+h²**.
- Hình thang n đoạn cho x²: **1/3+1/(6n²)**.
- Bisection sau k vòng: **width≤(R₀−L₀)/2^k** nếu bảo toàn dấu.

Đây là cách phân biệt **method error** với **error do máy**.

### Tầng 3 — Kết quả triển khai floating point

So kết quả thực từ code với **kết quả phương pháp lý tưởng** ở cùng input, đồng thời thử h, n, precision và các trường hợp cancellation.

Nếu kết quả đúng toán học nhưng không đúng phương pháp, cần kiểm tra cách định nghĩa oracle. Nếu phương pháp đã có method error lớn, không được gọi phần chênh đó là roundoff.

## 21. Kiểm thử độ hội tụ của phương pháp

### Tỉ lệ lỗi của sai phân

Với sai phân tiến:

**E_method(h)=6h+h² ≈6h** khi h nhỏ.

Vì vậy:

**E_method(h)/E_method(h/2)≈2**.

Với sai phân trung tâm:

**E_method(h)=h²**,

nên:

**E_method(h)/E_method(h/2)=4** chính xác về mặt đại số.

Trong vùng h quá nhỏ, kết quả double có thể phá các tỉ lệ này do roundoff. Điều đó cho tín hiệu chẩn đoán rằng ta đã ra khỏi vùng method error chi phối.

### Tỉ lệ lỗi tích phân hình thang

Vì:

**E_method(n)=1/(6n²)**,

nên:

**E_method(n)/E_method(2n)=4**.

Đây là một oracle độc lập mà không phải so hai bản code hình thang giống nhau.

### Không chỉ dựa vào tỉ lệ

Một tỉ lệ quan sát đúng trong vài điểm không đủ chứng minh hội tụ với mọi dữ liệu. Chứng minh vẫn cần giả thiết toán học về tính trơn, miền xác định và phương pháp.

## 22. Kiểm thử chia đôi, residual và phạm vi bảo đảm

Với bisection, mỗi vòng nên kiểm tra:

1. L≤R.
2. Nghiệm tham chiếu vẫn nằm trong [L,R] trên bài thử có nghiệm biết trước.
3. Độ dài interval không tăng.
4. Nếu midpoint không trùng đầu đoạn, width giảm xấp xỉ một nửa.
5. Khi ngừng, sai số midpoint không vượt **width/2** trong bài có nghiệm đã được giữ.
6. Khi mid==L hoặc mid==R, chương trình dừng hoặc chọn chiến lược xử lý stagnation.

Đừng tự kiểm tra bisection bằng cách **chỉ so residual**. Nếu f phẳng hoặc tính không ổn định, residual không cho đủ thông tin về sai số nghiệm.

### Đánh giá dấu có thể sai

Nếu f(mid) được tính bằng công thức gây cancellation lớn, một phép so với 0 có thể nhận dấu không đúng. Lúc đó invariant giữ nghiệm trong interval đã bị phá; cận midpoint bằng width/2 không còn giá trị chứng minh.

Các bài toán đòi xác nhận nghiệm nghiêm ngặt có thể cần **interval arithmetic**, phân tích dấu bằng số học chính xác hoặc các tiêu chuẩn riêng.

## 23. Thí nghiệm tự động nên có

Một bộ test tốt bao gồm:

1. **Đạo hàm:** sinh nhiều h từ 0.001 đến 0.5, so hai công thức sai phân double với 12+6h+h² và 12+h² theo tolerance phù hợp.
2. **h quá nhỏ:** kiểm tra các mốc 10^−8, 10^−12, 10^−16 và lý giải vì sao lỗi thay đổi.
3. **Tích phân:** chọn nhiều n, so trapezoid với 1/3+1/(6n²).
4. **Bisection:** sinh nhiều phương trình x²−c trên đoạn chứa nghiệm sqrt(c), so interval và error bound.
5. **Triệt tiêu:** chọn nhiều bộ [10^16,a,−10^16], so naive và Neumaier với tổng nguyên chính xác a.
6. **Nghiệm bậc hai:** thử hệ số |b| lớn và c nhỏ, kiểm tra công thức ổn định có tránh nghiệm bằng 0 khi nghiệm thật nhỏ dương.
7. **Roundtrip số nguyên:** thử 2^53−1, 2^53, 2^53+1 trên double và BigInteger.
8. **Decimal:** so new BigDecimal("0.1") với new BigDecimal(0.1) về ngữ nghĩa.
9. **Scale:** nhân mọi dữ liệu với một hằng số, xem relative/absolute error biến đổi thế nào.
10. **Kết thúc lặp:** kiểm tra không có vòng vô hạn do midpoint không đổi.

Nếu chỉ thử 0.1+0.2 rồi suy ra mọi sai số đều do double thì chưa đủ. Cần một bộ test có **các đối chứng riêng của từng cơ chế**.

## 24. Khi nào đổi phương pháp, khi nào đổi precision?

| Quan sát | Hướng xử lý hợp lý |
| --- | --- |
| Sai số phù hợp bậc O(h) hoặc O(h²) | Cân nhắc cải tiến công thức hoặc giảm h trong vùng an toàn |
| Giảm h làm kết quả xấu đi | Nghi roundoff/cancellation; thay cách tính hoặc tăng precision |
| Công thức bậc hai mất nghiệm nhỏ | Biến đổi đại số ổn định hơn, dùng Viète |
| Tổng nhiều số chênh bậc | Thử Neumaier, pairwise, sắp thứ tự thích hợp |
| Input là decimal chính xác | BigDecimal(String) và chính sách làm tròn rõ |
| Input là số nguyên vượt double/long | BigInteger; không qua double |
| Residual nhỏ nhưng x sai | Kiểm tra condition number, scale và cận nghiệm |
| Tính không hội tụ khi tăng số vòng | Xem lại giả thiết phương pháp, overflow, stagnation và stability |

**Thứ tự khuyến nghị:** xác định bài toán và mô hình → chứng minh phương pháp → phân tích error/conditioning → triển khai ổn định → chọn kiểu số/tolerance → kiểm thử đối kháng.

Đừng bắt đầu bằng cách tăng precision vô hạn khi nguyên nhân thật là mô hình sai hoặc phương pháp không hội tụ.

## 25. Các lỗi phổ biến

1. **Đổ mọi sai số cho floating point** mà không tính sai số phương pháp.
2. **Tin BigDecimal sửa sai phân h=0.1 thành đúng 12**, trong khi công thức vẫn xấp xỉ.
3. **Giảm h vô hạn**, khiến cancellation làm lỗi lớn hơn.
4. **Cho rằng sai phân trung tâm luôn O(h²)** dù f không đủ trơn.
5. **Không phân biệt roundoff với sai số dữ liệu đo**, chẩn đoán sai nguồn.
6. **Không phân biệt absolute/relative error**, nhất là quanh nghiệm 0.
7. **Dùng relative error chia cho expected=0**, tạo NaN/Infinity.
8. **So hai double bằng == để kiểm tra nghiệm gần đúng**, không dùng tolerance.
9. **Đặt EPS cố định cho mọi đơn vị và thang đo**, kiểm thử sai.
10. **Coi residual nhỏ là x gần nghiệm**, bỏ conditioning.
11. **Nhầm ULP tại 1.0 với ULP mọi số**, đánh giá sai độ phân giải.
12. **Nhầm unit roundoff 2^−53 với Math.ulp(1.0)=2^−52**.
13. **Lưu 2^53+1 trong double và nghĩ giữ đúng từng đơn vị**, mất độ chính xác nguyên.
14. **Tin phép cộng double kết hợp**, đổi thứ tự làm output khác.
15. **Cho rằng compensated summation luôn chính xác**, bỏ roundoff còn lại.
16. **Không phân biệt Kahan và Neumaier**, trích sai tính chất.
17. **Quy mọi lỗi subtraction cho phép trừ cuối**, không xét toán hạng đã bị làm tròn trước đó.
18. **Giải quadratic bằng hiệu hai số rất gần nhau**, mất nghiệm nhỏ.
19. **Dùng công thức ổn định hơn mà không kiểm tra q=0/overflow**, vẫn có lỗi biên.
20. **Dùng BigDecimal(double) khi cần số thập phân gốc**, giữ sai số representation đã tồn tại.
21. **Cho rằng BigDecimal chia 1/3 luôn ra decimal chính xác hữu hạn**, thiếu rounding policy.
22. **Tăng số vòng bisection nhưng midpoint không còn thay đổi**, không phát hiện stagnation.
23. **Báo cận bisection dù đánh giá dấu f(mid) đã sai**, vi phạm invariant.
24. **Dùng (L+R)/2 trên hai số cực lớn mà không xét overflow**.
25. **Cho rằng O(h^p) cho biết sai số cụ thể**, bỏ hệ số phụ thuộc hàm.
26. **Nhầm chi phí tính toán với độ chính xác**, số vòng lớn chưa chắc tốt.
27. **Bỏ qua underflow, subnormal, overflow và NaN**, sai mô hình số học.
28. **Cho rằng Math.fma làm mọi phép toán chính xác**, nó chỉ giúp một mẫu nhân-cộng.
29. **Đổi kiểu số nhưng giữ thuật toán không ổn định**, lỗi vẫn có thể đáng kể.
30. **Dùng oracle cùng công thức double không ổn định**, không kiểm tra độc lập.
31. **Không kiểm tra tính trơn khi dùng Taylor**, phát biểu bậc sai số không có cơ sở.
32. **Không kiểm tra ngữ nghĩa decimal vs binary**, đòi equality sai.
33. **Nhầm kết quả phương pháp lý tưởng và kết quả máy**, phân rã sai số không còn đúng.
34. **Quên kiểm tra dấu khi dùng bisection**, sai interval.
35. **Cho rằng accuracy sẽ tăng đều khi nâng precision**, bỏ giới hạn mô hình và conditioning.
36. **Chỉ thử dữ liệu nhỏ, không thử cancellation**, bỏ lỗi lớn trong thực tế.

## 26. Bài tập và câu hỏi tự luyện

**Bài 1.** Với f(x)=x³ tại x=2, tìm sai số phương pháp của sai phân tiến.  
**Đáp án:** 6h+h².

**Bài 2.** Cùng hàm, sai số phương pháp của sai phân trung tâm?  
**Đáp án:** h².

**Bài 3.** Với h=0.1, tại sao BigDecimal không biến 12.61 thành 12?  
**Đáp án:** 12.61 là kết quả lý tưởng của công thức tiến với h hữu hạn.

**Bài 4.** Với h=10^−16 ở x=2, vì sao kết quả double có thể bằng 0?  
**Đáp án:** x±h làm tròn về x, tử số bằng 0.

**Bài 5.** 0.1+0.2 khác 0.3 trong double là lỗi loại nào?  
**Đáp án:** Biểu diễn/làm tròn binary floating point.

**Bài 6.** Math.ulp(1.0) bằng bao nhiêu?  
**Đáp án:** 2^−52≈2.220446049250313×10^−16.

**Bài 7.** Tại sao 2^53+1 làm tròn về 2^53 trong double?  
**Đáp án:** Binary64 không thể biểu diễn mọi số nguyên trên 2^53.

**Bài 8.** Tính tổng toán học của [10^16,1,−10^16] và kết quả naive double.  
**Đáp án:** Tổng thật 1, naive có thể cho 0.

**Bài 9.** Tích phân hình thang n=4 của x² trên [0,1] bằng bao nhiêu?  
**Đáp án:** 0.34375, error phương pháp 1/96.

**Bài 10.** Sau 12 lần bisection [1,2] tìm sqrt2, cận lỗi midpoint?  
**Đáp án:** 1/8192≈0.0001220703125.

**Bài 11.** Residual tại x=2 của f(x)=10^−12(x−1) là bao nhiêu?  
**Đáp án:** 10^−12, dù x cách nghiệm 1.

**Bài 12.** Condition và numerical stability khác nhau thế nào?  
**Đáp án:** Condition thuộc bài toán, stability thuộc thuật toán.

**Bài 13.** Cách tính nghiệm nhỏ bậc hai ổn định hơn ở ví dụ b lớn?  
**Đáp án:** Dùng q=−0.5(b+sign(b)sqrtΔ), rồi nghiệm nhỏ c/q.

**Bài 14.** Khi nào dùng BigInteger thay double?  
**Đáp án:** Khi cần số nguyên chính xác vượt miền biểu diễn nguyên liên tiếp của double, chẳng hạn 2^53+1.

**Bài 15.** Khi nào dùng BigDecimal(String)?  
**Đáp án:** Khi cần giữ chính xác giá trị decimal nhập dưới dạng chuỗi.

**Bài 16.** Phương pháp có bậc error O(h²) nhưng chạy double vẫn sai lớn, vì sao?  
**Đáp án:** Roundoff/cancellation có thể chi phối ở h quá nhỏ.

**Bài 17.** Nếu đổi h thành h/2, tỉ lệ lỗi phương pháp trung tâm với x³ tại x=2 thế nào?  
**Đáp án:** E(h)/E(h/2)=4.

**Bài 18.** Vì sao residual nhỏ không đồng nghĩa forward error nhỏ?  
**Đáp án:** Thiếu điều kiện về độ nhạy/đạo hàm hoặc khoảng nghiệm.

**Bài 19.** Vì sao không nên chỉ dùng một oracle double?  
**Đáp án:** Oracle có thể cùng loại roundoff và lỗi ổn định với chương trình được kiểm tra.

**Bài 20.** Hãy nêu phương pháp QA tách method error và floating error.  
**Gợi ý:** So nghiệm thật, công thức phương pháp lý tưởng và bản tính double trên cùng input.

## 27. Tổng kết và checklist áp dụng

Trước khi kết luận một kết quả gần đúng sai vì đâu:

1. **Viết nghiệm toán học mục tiêu**, hoặc chuẩn tham chiếu đáng tin.
2. **Xem mô hình và dữ liệu có sai lệch không** trước khi xét số học.
3. **Xác định phương pháp có xấp xỉ gì**: bước lưới h, số ô tích phân n, số vòng lặp k.
4. **Phân tích method error trong số học thực lý tưởng**, không gộp vào roundoff.
5. **Kiểm tra đầu vào có biểu diễn chính xác** trong kiểu số được dùng không.
6. **Kiểm tra ULP, roundoff, cancellation**, các phép toán dễ mất chữ số có nghĩa.
7. **Thử giảm h có kiểm soát**, xem lỗi giảm rồi có tăng trở lại không.
8. **Nếu số thực có nghiệm gần 0**, kết hợp absolute và relative tolerance.
9. **Kiểm tra conditioning**; dữ liệu nhỏ sai có thể gây output sai lớn.
10. **Xem công thức có ổn định số không**, thay cách đánh giá khi cần.
11. **Nếu precision thấp là nút thắt**, dùng phép tính bù, công thức ổn định, BigDecimal hoặc thư viện đa precision.
12. **Nếu method error là nút thắt**, tăng bậc công thức, giảm h/năng lưới hợp lý hoặc tăng số vòng theo cận toán học.
13. **Với bisection**, giữ interval invariant và kiểm tra stagnation.
14. **Với tổng lớn nhỏ lẫn lộn**, thử compensated/pairwise summation.
15. **Với hệ số chênh độ lớn**, tránh subtraction giữa hai giá trị gần bằng nhau khi có biểu thức khác ổn định hơn.
16. **Không coi thuật toán hội tụ trong số học thực là đủ** để bảo đảm code floating-point hội tụ.
17. **Dùng oracle độc lập và test đối kháng** trước khi kết luận QA PASS.
18. **Phân biệt số học máy, số học phương pháp và dữ liệu** trong phần giải thích.

**Kết luận:** sai số phương pháp trả lời câu hỏi **“Công thức xấp xỉ vốn chính xác đến đâu?”**, còn sai số dấu phẩy động trả lời **“Máy tính đã làm lệch việc thực hiện công thức ra sao?”**. Cần phân tích cả hai — cùng với độ điều kiện và sai số dữ liệu — để chọn đúng cải tiến: **đổi phương pháp/độ phân giải** hoặc **đổi cách tính/độ chính xác số học**.
