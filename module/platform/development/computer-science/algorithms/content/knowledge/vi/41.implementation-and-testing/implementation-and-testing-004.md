# Sai số số thực và phép so sánh theo yêu cầu bài toán

Số thực trong toán học là một miền vô hạn, nhưng `double` của Java chỉ biểu diễn được **một tập hữu hạn các giá trị nhị phân**. Vì thế tính toán trên `double` có thể khác kết quả đại số chính xác: `0.1 + 0.2 == 0.3` trả `false`, nhiều số nguyên lớn khác nhau cùng được làm tròn thành một `double`, việc trừ hai số gần nhau gây mất chữ số có nghĩa, và quan hệ “gần bằng với sai số ε” **không** nhất thiết bắc cầu. Chọn sai phép so sánh có thể làm hỏng binary search, sort, hình học tính toán, mô phỏng và kiểm thử thuật toán.

Bài **“Sai số số thực và phép so sánh theo yêu cầu bài toán”**, thuộc nhóm **Cài đặt và kiểm thử** của Computer Science Algorithms, hướng dẫn phân loại yêu cầu so sánh trước khi viết code: **chính xác theo giá trị rời rạc**, **chính xác theo dữ liệu decimal**, **gần đúng theo một sai số có đơn vị**, **thứ tự toàn phần để sort**, hoặc **dấu của một biểu thức đại số**. Bài giải thích mô hình IEEE 754 binary64, ULP, sai số làm tròn, hủy chữ số, absolute/relative tolerance, NaN/Infinity/negative zero, so sánh phân số chính xác bằng `BigInteger`, định hướng hình học chính xác trên tọa độ `long`, và phép cộng bù Neumaier.

Cuối bài có **chương trình Java 17+ chạy độc lập** và stdout đã kiểm chứng. Bộ test so sánh dấu của 15.625 bộ ba điểm lưới và 4.000 bộ điểm cực trị với oracle `BigDecimal`; so 5.184 cặp phân số nhỏ và 3.202 cặp phân số cực trị với oracle khác; kiểm tra 20.000 cặp `double` về tính đối xứng của phép gần bằng, cùng NaN, Infinity, `-0.0`, ULP, comparator, sai số khi cộng và các input không hợp lệ.

## 1. Bài toán cần “đúng” theo nghĩa nào?

Trước khi chọn `==`, `Double.compare`, phép so dung sai ε hay số học chính xác, phải trả lời **đề bài yêu cầu tính đúng kiểu gì**:

| Tình huống | Đối tượng | Tiêu chuẩn thường phù hợp |
| --- | --- | --- |
| So sánh hai ID nguyên `long` | Rời rạc, chính xác | `==` hoặc `Long.compare` |
| So thứ tự hai phân số a/b, c/d với a,b,c,d nguyên | Hữu tỉ chính xác | `BigInteger` nhân chéo có xử lý dấu mẫu |
| Tính hướng quay của ba điểm có tọa độ nguyên | Dấu định thức chính xác | Tích có hướng dùng số nguyên đủ lớn |
| So hai kết quả mô phỏng gần đúng | Số đo/tính toán gần đúng | Sai số tuyệt đối, tương đối hoặc cận phân tích phù hợp |
| Sắp xếp `double` để binary search hoặc TreeMap | Thứ tự nhất quán, bắc cầu | `Double.compare`, có chính sách NaN/-0.0 |
| Tiền tệ với giá trị nhập từ chữ số thập phân | Decimal với quy tắc làm tròn | `BigDecimal(String)` hoặc đơn vị nhỏ nhất |
| Kiểm thử nghiệm số | Xấp xỉ kết quả tham chiếu | Chọn sai số theo đơn vị, điều kiện bài và tính ổn định |

“Dùng EPS cho tất cả phép so” là sai lầm phổ biến. Trong nhiều bài, kết quả phải exact; trong nhiều bài khác, `==` lại quá chặt vì lỗi làm tròn.

## 2. IEEE 754 binary64 của Java lưu được gì?

Kiểu `double` thường theo định dạng **IEEE 754 binary64**: 1 bit dấu, 11 bit số mũ và 52 bit phần fraction được lưu; với số chuẩn hóa, có thêm bit 1 đầu ẩn nên **độ chính xác significand là 53 bit nhị phân**.

~~~text
double finite normal:
  (-1)^sign × (1.fraction_52_bits) × 2^exponent

Số chữ số thập phân có nghĩa thường khoảng 15–17.
~~~

Không phải mọi số thập phân hữu hạn đều có biểu diễn nhị phân hữu hạn. Ví dụ `0.5` chính xác vì bằng 1/2, còn `0.1` có khai triển nhị phân vô hạn nên phải làm tròn.

`float` dùng binary32, ít bit chính xác hơn; `double` có phạm vi/độ chính xác lớn hơn nhưng **không là số thực toán học có vô hạn chữ số**. Chuyển từ `float` sang `double` không phục hồi thông tin đã mất ở bước nhập hoặc tính bằng `float`.

## 3. Ví dụ 0.1 + 0.2 và chuyện “in trông đúng”

Chạy Java:

~~~java
System.out.println(0.1 + 0.2 == 0.3);
System.out.println(0.1 + 0.2);
~~~

Cho:

~~~text
false
0.30000000000000004
~~~

Biểu diễn gần đúng của các toán hạng 0.1, 0.2 và 0.3 được làm tròn độc lập; sau phép cộng và làm tròn, bit kết quả không trùng bit của literal 0.3.

Có trường hợp Java in gọn một số khiến ta **không nhìn thấy hết sai số**: `Double.toString` thường chọn biểu diễn decimal ngắn đủ để khi parse lại có cùng giá trị double. Do đó không dùng chữ số hiển thị làm bằng chứng hai số có cùng giá trị thực toán học.

Điều cần sửa không phải Java mà là **mô hình dữ liệu và tiêu chuẩn so sánh**. Nếu đại lượng vốn là giá trị decimal exact, dùng `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất; nếu là kết quả đo/tính gần đúng, chọn dung sai có cơ sở.

## 4. Đơn vị sai số và giới hạn nguyên chính xác

Với binary64, **mọi số nguyên có độ lớn không quá 2^53 đều biểu diễn chính xác**. Từ ngoài vùng này, không phải mọi số nguyên liên tiếp đều còn là các giá trị `double` phân biệt.

~~~text
2^53 = 9007199254740992

long a = 9007199254740993
long b = 9007199254740992

Long.compare(a,b)    = 1
Double.compare((double)a,(double)b) = 0
~~~

Tại vùng đó, bước cách giữa các số `double` lân cận có thể đã bằng 2 thay vì 1. Đừng ép timestamp nanosecond, ID nguyên, số tiền đơn vị nhỏ, số lượng bản ghi hoặc chỉ số chính xác sang double chỉ để so.

Một số nguyên vượt 2^53 vẫn có thể biểu diễn chính xác nếu nó phù hợp bước nhảy binary64; điểm quan trọng là **không phải tất cả số nguyên liên tiếp** đều được biểu diễn. Không kết luận mọi số lớn hơn 2^53 đều sai.

## 5. Mô hình làm tròn và machine epsilon

Với phép toán cơ bản trên các số chuẩn hóa, không overflow hoặc underflow đáng kể, thường phân tích:

~~~text
fl(a op b) = (a op b) × (1 + delta),
|delta| <= u.

Với round-to-nearest binary64:
  u khoảng 2^-53.
~~~

Ở đây `fl` là kết quả được làm tròn, `u` là unit roundoff. Đây là mô hình sai số cục bộ **dưới giả thiết phù hợp**, không phải một định lý áp cho mọi giá trị bao gồm NaN, Infinity, phép chia zero hay mất chính xác tuyệt đối ở vùng rất gần 0.

Java `Math.ulp(1.0)` trả **2^-52**, là khoảng cách tới số double lớn hơn kế tiếp ở quanh 1.0. Cần phân biệt `ulp(1.0)` với **unit roundoff u=2^-53**; chúng không phải cùng khái niệm.

## 6. ULP và khoảng cách giữa số double thay đổi theo độ lớn

**ULP (unit in the last place)** thể hiện bước cách biểu diễn quanh một giá trị. Java cung cấp:

~~~java
Math.ulp(1.0);
Math.nextUp(1.0);
Math.nextDown(1.0);
~~~

Ở gần 1, bước cách lớn hơn thường xấp xỉ 2^-52. Ở các số lớn, ULP cũng lớn; gần zero là các **subnormal** với bước nhảy rất nhỏ (số dương nhỏ nhất là 2^-1074).

Vì ULP biến thiên, một ngưỡng tuyệt đối 1e-9 có thể **quá rộng** với kết quả nhỏ và **quá chặt** với kết quả rất lớn. Ngược lại, nếu chỉ cho phép vài ULP thì kết quả có sai số thuật toán tích lũy qua nhiều phép tính có thể vẫn không đạt dù ứng dụng chấp nhận được.

ULP là công cụ phân tích, không phải đáp án chung cho mọi câu hỏi về tính gần đúng. Phải xuất phát từ mức sai số của **đề bài**, không chọn “4 ULP” hoặc “EPS 1e-9” vì thấy thường gặp.

## 7. Sai số tuyệt đối và tương đối

Hai cách đo phổ biến:

~~~text
Absolute error:
    |computed - reference|.

Relative error:
    |computed - reference| / |reference|,
    khi reference khác 0.
~~~

Ví dụ phép đo tọa độ theo mét có sai số thực tế 0.001 m, ta có thể chọn ngưỡng tuyệt đối theo đơn vị mét. Nếu kết quả có giá trị khoảng 10^12, sai số tuyệt đối 1 có thể nhỏ về tương đối nhưng lớn nếu bài toán đo tiền chính xác từng đơn vị.

**Relative error không ổn định gần 0** vì mẫu số nhỏ hoặc bằng 0. Vì thế nhiều bài sử dụng kết hợp sai số tuyệt đối và tương đối.

Không nên tính một tỷ lệ rồi mặc nhiên xem nó vô hại với zero, NaN hoặc Infinity. Mỗi đại lượng cần chính sách về miền giá trị.

## 8. Một hợp đồng gần bằng rõ ràng

Chương trình Java dùng:

~~~text
close(a,b; absTol,relTol) đúng nếu:

a == b
hoặc
|a-b| <= max(
    absTol,
    relTol * max(|a|, |b|)
).

Các trường hợp NaN hoặc vô cực khác nhau
được xử lý riêng trước khi tính.
~~~

`absTol` có cùng **đơn vị vật lý** với a,b. `relTol` không có đơn vị và điều chỉnh theo độ lớn hai số. Dạng `max(...)` làm việc tốt cho nhiều bài so xấp xỉ; một số API khác dùng `absTol + relTol*scale`, nhưng đó là **hợp đồng khác**, phải thống nhất với bài và test.

Ví dụ gần zero: `a=0`, `b=0.75e-9`, `absTol=1e-9`, `relTol=0` thì close=true. Với số cỡ 10^12, chọn `relTol=1e-12` cho dung sai cỡ 1 đơn vị; dùng chỉ `absTol=1e-9` sẽ quá chặt.

Ngưỡng ε phải **được chọn theo ý nghĩa đại lượng**, số phép toán, và mức sai lệch có thể chấp nhận. Không có EPS vạn năng phù hợp mọi chương trình.

## 9. Vì sao close xử lý NaN/Infinity trước?

Trong IEEE 754:

- `Double.NaN == Double.NaN` là `false`.
- `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` là `true`.
- Vô cực và số hữu hạn không có chênh lệch hữu hạn.
- `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` là NaN, không thể đưa thẳng vào một phép kiểm khoảng cách.
- `+0.0 == -0.0` là `true` trong phép so primitive `==`.

Bản hàm `close` **trả false nếu một vế là NaN**, **trả true nếu hai vế `==`** (bao gồm cùng dấu Infinity), và chỉ tính dung sai khi cả hai vế khác nhau nhưng hữu hạn. Đây là một **quy ước API cụ thể**; bài toán không muốn chấp nhận Infinity có thể từ chối dữ liệu không hữu hạn ngay từ đầu.

Từ chối `absTol` âm/NaN/Infinity và `relTol` ngoài [0,1) giúp tránh những tham số khiến câu so sánh vô nghĩa. Không được kiểm `a==b` trước khi kiểm tính hợp lệ của tolerance rồi vô tình chấp nhận tolerance sai.

## 10. Overflow khi tính hiệu hai double

Khi `a=-Double.MAX_VALUE`, `b=Double.MAX_VALUE`, hiệu thực toán học có độ lớn vượt phạm vi double hữu hạn, nên trong Java:

~~~text
Math.abs(a-b) = Infinity.
~~~

Điều đó không tự động là bug trong `close`: với `relTol<1`, hai giá trị khác dấu và có độ lớn cực lớn phải được coi là cách xa nhau. Trong code, ngưỡng `max(absTol,relTol*scale)` hữu hạn nên so Infinity ≤ bound là false, đúng với hợp đồng đã chọn.

Tuy nhiên, nếu một ứng dụng cần **giá trị khoảng cách số học chính xác** chứ không chỉ predicate gần bằng, phải dùng số học biểu diễn rộng hơn hoặc thiết kế tránh overflow. Không nên áp công thức tính hiệu một cách máy móc khi đầu vào có thể cực trị.

## 11. Gần bằng không bắc cầu

Với EPS tuyệt đối 1e-9:

~~~text
a = 0.
b = 0.75e-9.
c = 1.50e-9.

close(a,b)=true.
close(b,c)=true.
close(a,c)=false.
~~~

Vì vậy quan hệ “hai số cách nhau ≤EPS” **không phải một quan hệ tương đương**: thiếu tính bắc cầu. Nó có thể phù hợp để đánh giá độ lệch một kết quả số, nhưng **không dùng làm quy tắc bằng nhau trong Set/Map hay so sánh sắp xếp**.

Không thể tự khắc phục bằng cách đặt EPS nhỏ hơn: miễn EPS>0, ta có thể xây ba số cách nhau vừa đủ để tái tạo phản ví dụ.

Nếu đề yêu cầu phân nhóm theo độ gần nhau, phải **định nghĩa thuật toán phân cụm hoặc bucket** với ngữ nghĩa cụ thể, không mặc nhiên coi close là equality bắc cầu.

## 12. Vì sao comparator kiểu EPS có thể làm sort sai?

Một comparator thường gặp nhưng lỗi:

~~~java
// Chỉ là ví dụ SAI cho việc sort.
int compare(double a,double b) {
    if (Math.abs(a-b) <= EPS) return 0;
    return a < b ? -1 : 1;
}
~~~

Nó xem a và b “bằng nhau” nhưng không nhất thiết xem a và c cùng quan hệ phù hợp với b và c. Comparator của Java phải có **hợp đồng thứ tự**, gồm tính phản đối xứng của dấu, tính bắc cầu và nhất quán của lớp tương đương comparator.

Nếu không, `Arrays.sort`/`Collections.sort` có thể trả kết quả không mong muốn hoặc trong một số dữ liệu phát hiện comparator vi phạm hợp đồng. `TreeMap`/`TreeSet` dùng comparator để xác định các key có bị xem là trùng, có thể làm mất key hợp lệ.

**Giải pháp:** để sort các `double`, dùng `Double.compare(a,b)` hoặc `Comparator.comparingDouble(...)` với chính sách NaN/Infinity đã được chấp nhận. Sau khi sort, áp predicate gần bằng **ở tầng đánh giá**, không dùng nó để thay thế thứ tự toàn phần.

## 13. Double.compare và sự khác nhau với toán tử ==

`Double.compare` xác định một thứ tự tổng cho các giá trị `double` theo quy tắc của Java, trong đó **-0.0 nhỏ hơn +0.0** và **NaN được sắp sau cả +Infinity**. Các giá trị NaN được xem bằng nhau trong phép compare.

~~~text
-0.0 == +0.0                  -> true.
Double.compare(-0.0,+0.0)    -> -1.

Double.NaN == Double.NaN     -> false.
Double.compare(NaN,NaN)      -> 0.
~~~

Điều này có chủ ý: thứ tự phục vụ sort và cấu trúc key có thể khác quan hệ `==` primitive. Nếu ứng dụng muốn **coi hai zero là cùng một key**, cần chuẩn hóa `-0.0` về `+0.0` trước khi lập khóa hoặc thiết kế comparator nhất quán.

`Double.doubleToLongBits` chuyển NaN về dạng bit canonical, còn `Double.doubleToRawLongBits` bảo toàn payload NaN. Dùng bit-level equality chỉ khi bài thực sự hỏi **bit pattern**, không phải giá trị thực xấp xỉ.

## 14. So sánh chính xác với các giá trị decimal

Nếu bài toán là tiền tệ hay số thập phân được nhập từ văn bản, dùng:

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal sum = a.add(b);
System.out.println(sum.toPlainString());
~~~

Stdout:

~~~text
0.3
~~~

**Tránh `new BigDecimal(0.1)`** nếu muốn giá trị decimal 0.1 do người dùng gõ: constructor từ double chuyển đúng **giá trị nhị phân đã xấp xỉ**, có thể có đuôi decimal dài. `BigDecimal.valueOf(0.1)` dùng biểu diễn decimal chuẩn của số double hiện có; tiện khi nguồn bắt buộc là double nhưng **không thể khôi phục dữ liệu chính xác đã mất trước đó**.

`BigDecimal.equals` phân biệt scale (ví dụ `1.0` và `1.00` có thể không equals), còn `compareTo` so theo giá trị số. Khi bài hỏi bằng nhau về số lượng, cân nhắc `compareTo()==0` với quy tắc scale do nghiệp vụ quy định.

## 15. Phép chia BigDecimal và quy tắc làm tròn

Dùng decimal không có nghĩa phép chia luôn kết thúc hữu hạn: 1/3 có vô hạn chữ số decimal. Do đó:

~~~java
BigDecimal one = new BigDecimal("1");
BigDecimal three = new BigDecimal("3");

BigDecimal q = one.divide(
    three, 10, RoundingMode.HALF_EVEN);
~~~

Bước này **cố ý làm tròn tới 10 chữ số sau dấu phẩy**. Trong các bài tính toán tài chính, quy tắc làm tròn (`HALF_EVEN`, `HALF_UP`, xuống, lên...) và thời điểm làm tròn phải đến từ đề/chuẩn nghiệp vụ.

Nếu gọi `one.divide(three)` không cho độ chính xác hoặc rounding phù hợp, Java có thể ném `ArithmeticException` do khai triển thập phân không kết thúc. Không nên bắt ngoại lệ rồi lặng lẽ trả 0 hoặc cắt ngẫu nhiên.

## 16. So sánh phân số hữu tỉ chính xác

Bài cho hai phân số a/b và c/d, với b,d khác 0, muốn so lớn/nhỏ chính xác. Nếu dùng double:

~~~text
(double)a/b so với (double)c/d
~~~

có thể không phân biệt các phân số rất gần nhau, làm mất thứ tự toán học. Đặc biệt, `a` và `c` có thể là `long` lớn không còn biểu diễn chính xác khi cast.

Giải pháp nguyên học là **nhân chéo**:

~~~text
Sau khi chuẩn hóa mẫu số dương:
a/b < c/d  khi và chỉ khi  a*d < c*b.
~~~

Không nhân trực tiếp bằng `long` nếu |a|,|b|,|c|,|d| lớn vì `a*d` có thể overflow. Bản code chuyển sang `BigInteger` **trước khi nhân**, chuẩn hóa mẫu âm bằng `negate` trên BigInteger, rồi so `a*d` với `c*b`.

Phương pháp này exact với mọi `long` hợp lệ kể cả `Long.MIN_VALUE`, không có tolerance. Mẫu số 0 bị từ chối, không gán ý nghĩa vô cực tùy tiện cho một phân số không hợp lệ.

## 17. Chứng minh phép nhân chéo và xử lý mẫu âm

Nếu b>0 và d>0, nhân cả hai vế của bất đẳng thức `a/b < c/d` với tích dương b*d **không đổi chiều dấu**, được a*d<c*b.

Nếu một mẫu âm, thay `a/b` thành `(-a)/(-b)` trước. Nhưng `-Long.MIN_VALUE` overflow trong `long`; do đó code tạo `BigInteger.valueOf` rồi mới negate, bảo toàn dấu đúng.

Ví dụ:

~~~text
1/3 và 2/6:
1*6 = 6.
2*3 = 6.
Kết quả compare = 0, exact.

-1/-3 và 1/3:
cả hai cùng 1/3, compare = 0.
~~~

Không cần rút gọn phân số bằng gcd trước khi so, dù rút gọn có thể giảm kích thước của BigInteger trong một số workload. Tính đúng phụ thuộc chuẩn hóa dấu và phép nhân không overflow.

## 18. Hình học: orientation của ba điểm nguyên

Với A(ax,ay), B(bx,by), C(cx,cy), dấu của tích có hướng:

~~~text
cross = (bx-ax)*(cy-ay)
      - (by-ay)*(cx-ax).

cross > 0: A->B->C ngược chiều kim đồng hồ.
cross < 0: thuận chiều kim đồng hồ.
cross = 0: thẳng hàng.
~~~

Đây là predicate nền tảng của convex hull, giao đoạn, phân loại điểm trên đường thẳng và nhiều bài hình học. Nếu tọa độ nguyên long, phép trừ bx-ax **có thể overflow ngay trước khi nhân**, và tích của hai hiệu có thể cần hơn 64 bit.

**Không đủ** chỉ cast tích thành double sau khi đã tính hiệu bằng long; overflow đã xảy ra. Bản Java chuyển từng tọa độ sang BigInteger **trước khi trừ**, tạo các vector bằng subtract, tính cross bằng multiply/subtract rồi lấy signum exact.

Vì bài hỏi **dấu của định thức**, ta không cần biết giá trị decimal xấp xỉ; tính exact tránh việc một số rất nhỏ về tương đối bị làm tròn thành 0.

## 19. Ví dụ hình học ở giới hạn long

Chọn:

~~~text
A = (Long.MIN_VALUE, Long.MIN_VALUE).
B = (Long.MAX_VALUE, Long.MIN_VALUE).
C = (Long.MIN_VALUE, Long.MAX_VALUE).
~~~

Vector AB nằm ngang theo chiều x dương rất lớn; AC thẳng đứng theo chiều y dương rất lớn. Tích có hướng thực phải dương:

~~~text
orientation(A,B,C)=+1.
~~~

Hiệu Long.MAX_VALUE - Long.MIN_VALUE **không vừa long**. Tích độ lớn còn vượt xa giới hạn long. Dùng `BigInteger` giữ chính xác và trả +1 như stdout.

Nếu tọa độ đầu vào vốn là `double` do đo đạc hoặc phép tính trước đó, không thể tùy ý cast sang long rồi tuyên bố đã khôi phục tính đúng hình học. Khi dữ liệu đã xấp xỉ, cần **robust geometric predicates** thích hợp với mô hình input đó, ví dụ adaptive precision hoặc exact arithmetic trên biểu diễn nhị phân đầu vào.

## 20. Sai số khi cộng dồn và tính không kết hợp

Phép cộng thực có tính kết hợp, nhưng phép cộng `double` sau làm tròn **không bảo đảm tính kết hợp**:

~~~text
(1e16 + 1) - 1e16
  trong double có thể thành 0.

1e16 + (1 - 1e16)
  cũng có thể mất chữ số nhỏ tùy thứ tự.
~~~

Ví dụ kinh điển:

~~~text
terms = [1e16, 1, -1e16].

Tổng toán học = 1.
Cộng tuần tự double = 0.
~~~

Khi cộng `1e16 + 1`, số 1 quá nhỏ so với khoảng cách ULP tại 1e16 nên bị **hấp thụ**. Khi trừ `1e16`, sai số làm tròn đã có không được hồi phục.

Vì thế kết quả một tổng double có thể phụ thuộc **thứ tự dữ liệu**. Điều này ảnh hưởng song song hóa, reduce trong streams, kiểm thử snapshot và thuật toán tích lũy hàng triệu số có nhiều độ lớn khác nhau.

## 21. Hủy chữ số có nghĩa (catastrophic cancellation)

Nếu trừ hai giá trị rất gần nhau, kết quả thực là hiệu nhỏ. Sai số tuyệt đối nhỏ có sẵn trong mỗi toán hạng có thể trở thành **sai số tương đối lớn** trong hiệu.

~~~text
a ≈ b,
a-b là một số rất nhỏ.

Sai số trước phép trừ:
 a = a_true + err_a.
 b = b_true + err_b.

Hiệu tính được chứa:
 (a_true-b_true)+(err_a-err_b).
~~~

Khi a_true≈b_true, phần `err_a-err_b` có thể cùng cỡ hoặc lớn hơn hiệu thực. Không thể chữa hoàn toàn bằng EPS ở bước so sánh cuối: cần **thiết kế công thức số ổn định** ngay từ đầu.

Các kỹ thuật gồm biến đổi biểu thức tránh trừ hai số gần nhau, dùng log1p/expm1 cho một số công thức đặc biệt, compensated summation, nâng độ chính xác, hoặc dùng số học exact khi đầu vào rời rạc.

## 22. Cộng bù Neumaier để giảm mất thông tin

Bản Java triển khai một dạng **Neumaier compensated summation**: giữ `sum` và một `correction` bổ sung phần sai số có thể khôi phục khi cộng.

~~~text
sum=0, correction=0.
for each x:
    t=sum+x.
    if abs(sum)>=abs(x):
        correction += (sum-t)+x.
    else:
        correction += (x-t)+sum.
    sum=t.
answer=sum+correction.
~~~

Với `[1e16,1,-1e16]`, phép cộng thường cho 0 còn Neumaier cho **1**. Trên 10.000 lần lặp bộ ba (30.000 số), test xác nhận cộng thường cho 0, phép cộng bù cho **10.000**.

Neumaier là kỹ thuật **giảm sai số**, không biến double thành exact arithmetic trong mọi điều kiện. Code từ chối NaN/Infinity ở đầu vào, và ném ArithmeticException khi tổng trung gian hoặc correction vượt phạm vi hữu hạn. Một bài toán có tổng toán học hữu hạn nhưng trung gian double overflow có thể vẫn cần **thiết kế cách cộng khác**.

## 23. Khi nào dùng phép so số thực trực tiếp?

Không phải lúc nào `==` cũng sai. Nếu bài toán hỏi hai biến có cùng **giá trị double đang lưu** hay không, `a==b` là phép so có ngữ nghĩa xác định (trừ NaN theo chuẩn). Nếu dữ liệu là kết quả từ cùng một nhánh phép tính và hai bên cùng biểu diễn, việc exact equality có thể là hợp đồng phù hợp.

Ví dụ nhị phân tìm một sentinel `Double.POSITIVE_INFINITY` có thể kiểm bằng `==`, hoặc cần phân biệt NaN thì dùng `Double.isNaN`. Nếu bài hỏi **bit pattern**, dùng API bit-level thích hợp.

Nhưng với hai **đường tính khác nhau** ra cùng một đại lượng thực về mặt toán học, `==` có thể không phù hợp do các bước làm tròn khác nhau. Khi ấy dùng định lượng sai số, phân tích số hoặc exact arithmetic theo miền bài toán.

## 24. Chọn tolerance từ yêu cầu cụ thể

Một số nguyên tắc:

1. **Đơn vị:** nếu tọa độ tính bằng mét và yêu cầu lệch dưới 1 mm, absolute tolerance có thể xoay quanh 0.001 m, nếu error budget cho phép.
2. **Quy mô:** nếu so kết quả tích lũy cỡ 10^12, relative tolerance có thể phù hợp hơn absolute tolerance rất nhỏ.
3. **Gần zero:** cần absolute floor để tránh tỷ lệ vô nghĩa khi reference≈0.
4. **Thuật toán:** số bước, tình trạng hủy chữ số và điều kiện bài toán có thể khuếch đại lỗi; EPS phải đủ bao phủ lỗi dự kiến, không tùy tiện.
5. **An toàn:** trong hình học exact, phân số nguyên, so thứ tự sort, dùng tolerance có thể phá bất biến cần exact; khi đó chọn representation/algorithm khác.
6. **Miền hợp lệ:** quy định trước NaN/Infinity/-0.0, input overflow, underflow.

Nếu đề bài nêu chấp nhận sai số tuyệt đối ≤10^-6 **hoặc** tương đối ≤10^-6, cần xem “hoặc” áp thế nào: quy tắc max trong demo là một diễn giải phù hợp, còn tổng abs+rel có thể cho tiêu chuẩn khác. **Sao chép đúng hợp đồng của đề**, không tự suy diễn.

## 25. Rounding, scaling và công thức số ổn định

Đôi khi hai thuật toán đều đúng về toán nhưng một công thức ổn định hơn. Ví dụ giải phương trình bậc hai với b lớn có thể gây cancellation ở `-b ± sqrt(discriminant)`. Công thức chọn dấu rồi lấy nghiệm còn lại qua tích hai nghiệm có thể giảm sai số, khi điều kiện cho phép.

Khi lấy trung bình hai số rất lớn, `(a+b)/2` có thể overflow dù trung bình hữu hạn; một số dạng `a/2+b/2` tránh overflow nhưng có kiểu sai số khác, còn `a+(b-a)/2` lại có thể overflow ở hiệu khi a,b trái dấu. Không có phép biến đổi duy nhất tối ưu mọi miền.

Với các phép cộng nhiều phần tử, có thể dùng pairwise summation hoặc compensated summation; với các phép tính cần exact decimal, dùng BigDecimal theo rounding policy; với bài integer, giữ dữ liệu nguyên và sử dụng BigInteger khi bậc phép toán lớn.

**Mục tiêu là giảm sai số trong quá trình tính**, chứ không chỉ thêm EPS ở dòng `if` sau cùng.

## 26. Bài toán binary search và điều kiện đơn điệu

Binary search cần một **predicate đơn điệu** theo tham số. Nếu so bằng EPS theo một cách làm biến dạng bất đẳng thức, miền true/false có thể không còn tương ứng với lời giải mong muốn.

Ví dụ tìm số nguyên nhỏ nhất thỏa `f(x) >= T` thì phải so đúng theo yêu cầu: nếu f(x) là số nguyên exact, tránh chuyển sang double. Nếu f(x) là nghiệm số gần đúng, cần biết error bound để không quyết định sai ngay gần ranh giới.

Khi binary search trên double để tìm nghiệm thực, thường dừng theo số lần lặp cố định hoặc tiêu chí về **độ rộng khoảng và sai số giá trị**, và đảm bảo cập nhật hai đầu không bị kẹt do mid làm tròn trùng một đầu. `Math.nextUp/nextDown` giúp nhận diện khi không còn giá trị double nằm giữa.

Không dùng `while (left != right)` cho mọi bài binary search số thực vì rounding có thể làm vòng lặp không tiến.

## 27. Vì sao bài toán hình học hay lỗi nhất?

Trong convex hull, ba điểm gần thẳng hàng có cross thật rất nhỏ so với độ lớn tọa độ. Nếu dùng cross kiểu double và so với EPS cố định, một phép làm tròn có thể đổi dấu của cross, dẫn tới:

- Loại nhầm một đỉnh trên hull.
- Đảo chiều đoạn, tạo đa giác sai.
- Giao đoạn bị xem là không giao hoặc ngược lại.
- Comparator góc trong phép sort không nhất quán.

Nếu tọa độ là **số nguyên** và miền cho phép, `BigInteger` orientation là phép so chính xác đáng tin; nếu tọa độ là **floating-point** từ dữ liệu đo, có thể cần predicate adaptive precision, khoảng sai số được kiểm chứng hoặc quy tắc hình học với tolerance xuất phát từ đơn vị.

Không được thay mọi `cross==0` bằng `abs(cross)<EPS` mà không đánh giá quy mô và tính nhất quán toàn cục của thuật toán.

## 28. Cách thiết kế oracle kiểm thử số học

Bài toán so sánh số thực cần test không chỉ ví dụ “đẹp” mà cả trường hợp cực biên và **oracle độc lập**.

Chương trình Java dùng hai cách tính khác nhau:

- `orientation` dùng `BigInteger` và trả dấu của hiệu hai tích.
- `independentOrientation` dùng `BigDecimal` với tọa độ long được chuyển **chính xác**, tạo hai vector rồi so tích bằng `compareTo`.
- `compareFractions` dùng BigInteger nhân chéo.
- `independentFraction` dùng BigDecimal nhân chéo với mẫu đã chuẩn hóa, không chia ra double.
- `close` được kiểm về tính đối xứng và hợp đồng edge cases, **không** thử ép tính bắc cầu vì tính chất ấy là sai.

Mục đích của oracle là **độc lập đường biểu diễn số học** để tăng khả năng phát hiện lỗi. Hai oracle BigDecimal và BigInteger đều thực hiện số học exact trên dữ liệu nguyên long, nhưng dùng lớp/cách cài khác nhau.

## 29. Kiểm thử 15.625 bộ ba điểm lưới

Tọa độ mỗi điểm chọn trong `{-2,-1,0,1,2}` ở cả x và y. Có **25 điểm lưới** có thể chọn; một bộ ba A,B,C có:

~~~text
25 × 25 × 25 = 15625 bộ.
~~~

Cho phép trùng điểm và thẳng hàng. Mỗi bộ được tính orientation bằng BigInteger, rồi đối chiếu dấu với oracle BigDecimal. Điều này bắt các lỗi:

- Sai dấu của cross product.
- Nhầm thứ tự A,B,C.
- Quên trừ tọa độ gốc.
- Xử lý thẳng hàng/cùng điểm sai.
- Kiểu so sánh khác -1/0/+1 khi cross thật có dấu.

Ngoài lưới nhỏ, bộ test có **4.000 bộ tọa độ cực trị** lấy xen kẽ từ Long.MIN/MAX, ±(2^53+1), 0, ±1 và long ngẫu nhiên toàn miền, đối chiếu cùng oracle. Kết quả cả hai nhóm **PASS**.

## 30. Kiểm thử 5.184 phân số nhỏ và 3.202 bộ cực trị

Bộ test exhaustive chọn a và c trong [-4,4], b và d trong `[-4,4]` nhưng khác 0. Số phân số ứng viên:

~~~text
9 lựa chọn tử số × 8 lựa chọn mẫu số = 72.
72 × 72 = 5184 cặp so.
~~~

Mọi cặp được tính bằng BigInteger rồi so với BigDecimal nhân chéo. Test chứa mẫu âm, phân số âm, các phân số bằng nhau có biểu diễn khác và nhiều trường hợp tử bằng 0.

Thêm 4.000 lượt sinh từ danh sách long cực trị, loại những cặp có mẫu số 0; có **3.202** trường hợp hợp lệ được chạy. Đây là con số **đã quan sát theo seed 5382026**, không phải dự đoán xác suất.

Kết quả chính xác của `1/3` so với `2/6` bằng **0**. Không chuyển phân số sang double để quyết định khi yêu cầu chính xác theo toán học.

## 31. Kiểm thử tolerance và comparator

Phép `close` của bài được thiết kế **đối xứng**: dùng `max(|a|,|b|)` làm scale thay vì chỉ scale theo b. Test sinh **20.000 cặp bit pattern double** ngẫu nhiên, bao gồm khả năng xuất hiện NaN/Infinity/subnormal, rồi kiểm:

~~~text
close(a,b,absTol,relTol)
  == close(b,a,absTol,relTol).
~~~

Có test riêng khẳng định `close` **không bắc cầu**, `-0.0` và `+0.0` được coi gần bằng, cùng Infinity được chấp nhận theo hợp đồng nhưng NaN không gần bất cứ gì.

Đối với comparator sort, test một tập gồm NaN, ±Infinity, ±0, số âm/dương và giá trị hữu hạn lớn; kiểm tra tính bắc cầu của `Double.compare` trên các bộ ba rồi sort và xác nhận không giảm. Đây là cách kiểm đặc tính **thứ tự**, khác hẳn việc kiểm sai số số thực.

Test cũng xác nhận `Math.ulp(1.0)==2^-52` và `Math.nextUp(1.0)>1.0`.

## 32. Kiểm thử mất mát khi cộng và input lỗi

Chương trình tạo 30.000 số bằng cách lặp 10.000 lần bộ ba:

~~~text
[1e16, 1, -1e16].
~~~

Tổng exact phải là 10.000. Cộng tuần tự bằng double thu **0**, Neumaier thu **10.000** trong lần chạy. Đây là ví dụ có chủ đích để lộ absorption/cancellation, không phải khẳng định mọi dãy sẽ được Neumaier tính exact.

Bộ test còn bắt buộc các input sau bị từ chối:

- Absolute tolerance âm hoặc NaN.
- Relative tolerance bằng 1 hoặc Infinity.
- Mẫu số phân số bằng 0.
- Mảng cộng null hoặc chứa NaN.
- Tổng hai Double.MAX_VALUE làm overflow.

Những trường hợp này là một phần của **hợp đồng API** chứ không phải góc phụ có thể bỏ qua. Nếu đổi chính sách chấp nhận Infinity/NaN phải sửa test tương ứng.

## 33. Java 17+ hoàn chỉnh

Lưu toàn bộ mã thành **FloatingComparisonLesson.java**. Mã chỉ dùng thư viện chuẩn Java, không đọc file bên ngoài hay yêu cầu dependency. Các thành phần:

1. `close(a,b,absTol,relTol)`: phép gần bằng đối xứng có kiểm tham số, NaN/Infinity và signed zero.
2. `compareFractions(a,b,c,d)`: chính xác với phân số có số nguyên long, nhân chéo BigInteger và chuẩn hóa mẫu.
3. `orientation(A,B,C)`: định thức BigInteger cho tọa độ nguyên long, trả dấu -1/0/+1.
4. `neumaierSum(values)`: phép cộng bù trên các double hữu hạn, có báo lỗi khi overflow.
5. Hai oracle dùng BigDecimal, cùng bộ test exhaustive/random và input lỗi.
6. `main`: các phản ví dụ trực quan, chạy `verify`, in stdout đã quan sát.

~~~java
import java.math.*;
import java.util.*;

public final class FloatingComparisonLesson {
    private FloatingComparisonLesson() {}

    public static boolean close(double a, double b,
                                double absTol, double relTol) {
        if (!Double.isFinite(absTol) || absTol < 0
                || !Double.isFinite(relTol)
                || relTol < 0 || relTol >= 1) {
            throw new IllegalArgumentException("invalid tolerance");
        }
        if (Double.isNaN(a) || Double.isNaN(b)) return false;
        if (a == b) return true;
        if (!Double.isFinite(a) || !Double.isFinite(b)) return false;
        double scale = Math.max(Math.abs(a), Math.abs(b));
        double limit = Math.max(absTol, relTol * scale);
        return Math.abs(a - b) <= limit;
    }

    public static int compareFractions(long a, long b,
                                       long c, long d) {
        if (b == 0 || d == 0) {
            throw new IllegalArgumentException("zero denominator");
        }
        BigInteger an = BigInteger.valueOf(a);
        BigInteger bn = BigInteger.valueOf(b);
        BigInteger cn = BigInteger.valueOf(c);
        BigInteger dn = BigInteger.valueOf(d);
        if (bn.signum() < 0) {
            an = an.negate();
            bn = bn.negate();
        }
        if (dn.signum() < 0) {
            cn = cn.negate();
            dn = dn.negate();
        }
        return an.multiply(dn).compareTo(cn.multiply(bn));
    }

    public static int orientation(long ax, long ay,
                                  long bx, long by,
                                  long cx, long cy) {
        BigInteger abx = BigInteger.valueOf(bx)
                .subtract(BigInteger.valueOf(ax));
        BigInteger aby = BigInteger.valueOf(by)
                .subtract(BigInteger.valueOf(ay));
        BigInteger acx = BigInteger.valueOf(cx)
                .subtract(BigInteger.valueOf(ax));
        BigInteger acy = BigInteger.valueOf(cy)
                .subtract(BigInteger.valueOf(ay));
        BigInteger cross = abx.multiply(acy)
                .subtract(aby.multiply(acx));
        return cross.signum();
    }

    public static double neumaierSum(double[] values) {
        if (values == null) {
            throw new IllegalArgumentException("null terms");
        }
        double sum = 0.0;
        double correction = 0.0;
        for (double x : values) {
            if (!Double.isFinite(x)) {
                throw new IllegalArgumentException("non-finite term");
            }
            double t = sum + x;
            if (!Double.isFinite(t)) {
                throw new ArithmeticException("non-finite partial sum");
            }
            if (Math.abs(sum) >= Math.abs(x)) {
                correction += (sum - t) + x;
            } else {
                correction += (x - t) + sum;
            }
            if (!Double.isFinite(correction)) {
                throw new ArithmeticException("correction overflow");
            }
            sum = t;
        }
        double total = sum + correction;
        if (!Double.isFinite(total)) {
            throw new ArithmeticException("final overflow");
        }
        return total;
    }

    private static int independentOrientation(
            long ax, long ay, long bx, long by, long cx, long cy) {
        BigDecimal x1 = BigDecimal.valueOf(bx)
                .subtract(BigDecimal.valueOf(ax));
        BigDecimal y1 = BigDecimal.valueOf(by)
                .subtract(BigDecimal.valueOf(ay));
        BigDecimal x2 = BigDecimal.valueOf(cx)
                .subtract(BigDecimal.valueOf(ax));
        BigDecimal y2 = BigDecimal.valueOf(cy)
                .subtract(BigDecimal.valueOf(ay));
        return x1.multiply(y2).compareTo(y1.multiply(x2));
    }

    private static int independentFraction(
            long a, long b, long c, long d) {
        if (b == 0 || d == 0) {
            throw new IllegalArgumentException("zero denominator");
        }
        BigDecimal an = BigDecimal.valueOf(a);
        BigDecimal bn = BigDecimal.valueOf(b);
        BigDecimal cn = BigDecimal.valueOf(c);
        BigDecimal dn = BigDecimal.valueOf(d);
        if (bn.signum() < 0) {
            an = an.negate();
            bn = bn.negate();
        }
        if (dn.signum() < 0) {
            cn = cn.negate();
            dn = dn.negate();
        }
        return an.multiply(dn).compareTo(cn.multiply(bn));
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static void invalid(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    private static void arithmeticError(Runnable operation) {
        try {
            operation.run();
        } catch (ArithmeticException expected) {
            return;
        }
        throw new AssertionError("overflow accepted");
    }

    public static void verify() {
        int geometric = 0;
        for (long ax = -2; ax <= 2; ax++)
            for (long ay = -2; ay <= 2; ay++)
                for (long bx = -2; bx <= 2; bx++)
                    for (long by = -2; by <= 2; by++)
                        for (long cx = -2; cx <= 2; cx++)
                            for (long cy = -2; cy <= 2; cy++) {
                                int actual = orientation(
                                        ax, ay, bx, by, cx, cy);
                                int expected = Integer.signum(
                                        independentOrientation(
                                                ax, ay, bx, by, cx, cy));
                                require(actual == expected,
                                        "geometric exhaustive mismatch");
                                geometric++;
                            }

        long[] edges = {
            Long.MIN_VALUE, Long.MIN_VALUE + 1, -9007199254740993L,
            -1, 0, 1, 9007199254740993L,
            Long.MAX_VALUE - 1, Long.MAX_VALUE
        };
        Random rng = new Random(5382026L);
        int largeGeometry = 0;
        for (int i = 0; i < 4000; i++) {
            long[] c = new long[6];
            for (int j = 0; j < c.length; j++) {
                c[j] = (i % 2 == 0)
                        ? edges[rng.nextInt(edges.length)]
                        : rng.nextLong();
            }
            require(orientation(c[0], c[1], c[2], c[3], c[4], c[5])
                    == Integer.signum(independentOrientation(
                            c[0], c[1], c[2], c[3], c[4], c[5])),
                    "geometric extreme mismatch");
            largeGeometry++;
        }

        int rational = 0;
        for (long a = -4; a <= 4; a++)
            for (long b = -4; b <= 4; b++) {
                if (b == 0) continue;
                for (long c = -4; c <= 4; c++)
                    for (long d = -4; d <= 4; d++) {
                        if (d == 0) continue;
                        require(Integer.signum(compareFractions(a,b,c,d))
                                == Integer.signum(
                                        independentFraction(a,b,c,d)),
                                "rational exhaustive mismatch");
                        rational++;
                    }
            }
        int largeRational = 0;
        for (int i = 0; i < 4000; i++) {
            long a = edges[rng.nextInt(edges.length)];
            long b = edges[rng.nextInt(edges.length)];
            long c = edges[rng.nextInt(edges.length)];
            long d = edges[rng.nextInt(edges.length)];
            if (b == 0 || d == 0) continue;
            require(Integer.signum(compareFractions(a,b,c,d))
                    == Integer.signum(independentFraction(a,b,c,d)),
                    "rational extreme mismatch");
            largeRational++;
        }

        double epsilon = 1e-9;
        double a = 0;
        double b = 0.75e-9;
        double c = 1.5e-9;
        require(close(a,b,epsilon,0)
                && close(b,c,epsilon,0)
                && !close(a,c,epsilon,0),
                "close should not be transitive");
        require(close(-0.0,+0.0,0,0)
                && Double.compare(-0.0,+0.0) < 0,
                "signed zero contract");
        require(!close(Double.NaN,Double.NaN,1,0)
                && close(Double.POSITIVE_INFINITY,
                         Double.POSITIVE_INFINITY,0,0)
                && !close(Double.POSITIVE_INFINITY,
                          Double.NEGATIVE_INFINITY,1,0),
                "NaN/infinity contract");
        require(close(1e12,1e12+1,1e-8,1e-12)
                && !close(1e12,1e12+1,1e-8,1e-13),
                "relative tolerance contract");
        require(!close(-Double.MAX_VALUE,
                       Double.MAX_VALUE,1,0.5),
                "overflowing difference must be far");
        require(Math.ulp(1.0)==Math.scalb(1.0,-52)
                && Math.nextUp(1.0)>1.0,
                "ULP contract");

        double[] totalOrder = {
            Double.NaN, Double.POSITIVE_INFINITY, 1.0,
            +0.0, -0.0, -1.0, -Double.MAX_VALUE,
            Double.NEGATIVE_INFINITY, Double.NaN
        };
        for (double x : totalOrder)
            for (double y : totalOrder)
                for (double z : totalOrder)
                    if (Double.compare(x,y)<=0
                            && Double.compare(y,z)<=0)
                        require(Double.compare(x,z)<=0,
                                "total-order transitivity");
        Arrays.sort(totalOrder);
        for (int i=1; i<totalOrder.length; i++)
            require(Double.compare(totalOrder[i-1],
                                   totalOrder[i])<=0,
                    "Double.compare sorting");

        int symmetric = 0;
        for (int i=0; i<20000; i++) {
            double x = Double.longBitsToDouble(rng.nextLong());
            double y = Double.longBitsToDouble(rng.nextLong());
            double absTol = (i % 2 == 0) ? 0 : 1e-6;
            double relTol = (i % 3 == 0) ? 0 : 1e-8;
            require(close(x,y,absTol,relTol)
                    == close(y,x,absTol,relTol),
                    "approximate equality must be symmetric");
            symmetric++;
        }

        double[] values = new double[30000];
        for (int i=0; i<10000; i++) {
            values[i*3] = 1e16;
            values[i*3+1] = 1;
            values[i*3+2] = -1e16;
        }
        double naive = 0;
        for (double v : values) naive += v;
        require(naive == 0.0 && neumaierSum(values) == 10000.0,
                "compensated summation regression");

        invalid(() -> close(1,1,-1,0));
        invalid(() -> close(1,1,0,1));
        invalid(() -> close(1,1,Double.NaN,0));
        invalid(() -> close(1,1,0,Double.POSITIVE_INFINITY));
        invalid(() -> compareFractions(1,0,2,3));
        invalid(() -> compareFractions(1,2,3,0));
        invalid(() -> neumaierSum(null));
        invalid(() -> neumaierSum(new double[]{Double.NaN}));
        arithmeticError(() -> neumaierSum(
                new double[]{Double.MAX_VALUE,Double.MAX_VALUE}));

        System.out.println("Grid orientations: "+geometric+" PASS");
        System.out.println("Extreme orientations: "+largeGeometry+" PASS");
        System.out.println("Small rational comparisons: "+rational+" PASS");
        System.out.println("Extreme rational comparisons: "
                +largeRational+" PASS");
        System.out.println("Tolerance symmetry: "+symmetric+" PASS");
        System.out.println("NaN, infinity, zero, ULP, sorting: PASS");
        System.out.println("Compensated sum and bad inputs: PASS");
    }

    public static void main(String[] args) {
        System.out.println("0.1+0.2 == 0.3: "+(0.1+0.2==0.3));
        System.out.println("0.1+0.2 close to 0.3: "
                +close(0.1+0.2,0.3,1e-12,1e-12));
        BigDecimal exact = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("Exact decimal sum: "
                +exact.toPlainString());
        long a = 9007199254740993L, b = 9007199254740992L;
        System.out.println("Long compare past 2^53: "
                +Long.compare(a,b));
        System.out.println("Double compare past 2^53: "
                +Double.compare((double)a,(double)b));
        System.out.println("Exact fraction compare 1/3 vs 2/6: "
                +compareFractions(1,3,2,6));
        System.out.println("Extreme orientation sign: "
                +orientation(Long.MIN_VALUE,Long.MIN_VALUE,
                             Long.MAX_VALUE,Long.MIN_VALUE,
                             Long.MIN_VALUE,Long.MAX_VALUE));
        System.out.println("Double.compare(-0.0,+0.0): "
                +Double.compare(-0.0,+0.0));
        System.out.println("close is transitive: "
                +(close(0,0.75e-9,1e-9,0)
                  && close(0.75e-9,1.5e-9,1e-9,0)
                  && close(0,1.5e-9,1e-9,0)));
        double[] cancellation = {1e16,1,-1e16};
        double naive = 0;
        for (double v : cancellation) naive += v;
        System.out.println("Cancellation naive: "+naive);
        System.out.println("Cancellation Neumaier: "
                +neumaierSum(cancellation));
        verify();
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac FloatingComparisonLesson.java
java FloatingComparisonLesson
~~~

**Stdout thực tế từ lần chạy Java:**

~~~text
0.1+0.2 == 0.3: false
0.1+0.2 close to 0.3: true
Exact decimal sum: 0.3
Long compare past 2^53: 1
Double compare past 2^53: 0
Exact fraction compare 1/3 vs 2/6: 0
Extreme orientation sign: 1
Double.compare(-0.0,+0.0): -1
close is transitive: false
Cancellation naive: 0.0
Cancellation Neumaier: 1.0
Grid orientations: 15625 PASS
Extreme orientations: 4000 PASS
Small rational comparisons: 5184 PASS
Extreme rational comparisons: 3202 PASS
Tolerance symmetry: 20000 PASS
NaN, infinity, zero, ULP, sorting: PASS
Compensated sum and bad inputs: PASS
~~~

Khi thực hiện qua JShell để kiểm thử, môi trường shell có thể in một diagnostic BOM ở đầu hoặc dòng stderr lúc thoát; các dòng trên là **stdout do chương trình in** và tất cả phép kiểm bên trong đã hoàn thành trước các dòng PASS. Nếu dùng lệnh `javac`/`java` trên một file UTF-8 Java như hướng dẫn, không cần chèn BOM vào đầu file.

## 34. Checklist lỗi phổ biến khi cài đặt

1. **Dùng `==` để so hai đường tính floating khác nhau** dù đề chỉ yêu cầu gần đúng.
2. **Dùng EPS cho hai số nguyên exact**, khiến các giá trị khác nhau thành bằng nhau.
3. **Chọn EPS tuyệt đối cố định** mà không quan tâm đơn vị/độ lớn dữ liệu.
4. **Dùng sai số tương đối gần zero** mà không có absolute floor.
5. **Không xét NaN**, để phép so khác nhau trả false theo cách khó đoán.
6. **Không xét ±Infinity**, làm phép trừ ra NaN/Infinity rồi so sai.
7. **Nhầm -0.0 và +0.0 trong Double.compare và `==`**.
8. **Xem close như quan hệ tương đương**, dù nó không bắc cầu.
9. **Dùng epsilon comparator cho Array.sort hoặc TreeMap**, vi phạm contract.
10. **Dùng comparator bằng `a-b` rồi ép int**, sai với số lớn và overflow.
11. **Chuyển long ID hoặc tọa độ nguyên sang double trước khi so**, mất phân biệt sau 2^53.
12. **Dùng `long` nhân chéo hai phân số cực lớn**, overflow.
13. **Đổi dấu Long.MIN_VALUE trong long**, overflow ở giá trị cực tiểu.
14. **Tính hiệu vector bằng long rồi mới đổi sang BigInteger**, overflow đã xảy ra.
15. **Dùng EPS mặc định cho orientation nguyên exact**, biến cross khác 0 thành 0.
16. **Giữ BigDecimal(double) khi muốn decimal từ chuỗi**, nhận giá trị nhị phân đã làm tròn.
17. **Không chỉ định RoundingMode cho phép chia decimal vô hạn**, gặp ArithmeticException.
18. **Dùng BigDecimal.equals cho equality số học mà bỏ qua scale**, gây kết quả không mong muốn.
19. **Dùng ULP như sai số tuyệt đối cố định toàn miền**, không xét biến thiên theo độ lớn.
20. **Nhầm machine epsilon 2^-52 và unit roundoff 2^-53**.
21. **Cho rằng mọi số nguyên >2^53 đều không biểu diễn được**, phát biểu sai.
22. **Không kiểm tra overflow/underflow**, giả định mọi kết quả đều hữu hạn và normal.
23. **Cộng số nhỏ vào số rất lớn rồi trừ số lớn**, mất contribution do absorption.
24. **Cho rằng đổi thứ tự cộng không đổi kết quả double**, quên non-associativity.
25. **Dùng sai số ở dòng if để che một thuật toán số không ổn định**, thay vì sửa công thức.
26. **Kiểm thử chỉ trên số nhỏ dương và phân số dễ chia**, bỏ extreme.
27. **Không có oracle độc lập**, để hai bản code cùng mắc một lỗi.
28. **Sử dụng test gần bằng để kiểm hợp đồng thứ tự của comparator**, sai mục tiêu test.
29. **Cho rằng compensated summation luôn exact**, trong khi nó chỉ giảm sai số với giả thiết phù hợp.
30. **Áp cùng epsilon cho tọa độ mét, tiền và góc đo bằng radian**, không thống nhất đơn vị.
31. **Không tính tới sai số sinh ra trước bước hiện tại**, ví dụ dữ liệu đã được cast float.
32. **Không phân biệt roundoff, truncation, modeling error và measurement error**.
33. **Dùng so close để quyết định một ranh giới luật/đếm rời rạc**, thay vì so exact theo hợp đồng.
34. **Coi toàn bộ NaN payload có cùng bit pattern**, trong khi `Double.compare` chỉ là thứ tự theo quy tắc Java.
35. **Không kiểm tra tính đơn điệu khi binary search số thực**, có thể kẹt ở mid không đổi.

## 35. Bài tập tự luyện

**Bài 1 — Biểu diễn:** tại sao 0.5 exact trong binary còn 0.1 không? In `0.1+0.2` và giải thích `==0.3` trả false.

**Bài 2 — Mốc 2^53:** tính `Long.compare(9007199254740993L,9007199254740992L)` và so sau khi cast cả hai sang double.

**Bài 3 — Abs/rel:** với a=0,b=1e-10 và a=1e12,b=1e12+1, chọn absolute/relative tolerance có ý nghĩa rồi giải thích hai kết quả.

**Bài 4 — Không bắc cầu:** dựng ba số a,b,c với close(a,b), close(b,c) true nhưng close(a,c) false; giải thích vì sao không dùng nó làm comparator.

**Bài 5 — Comparator:** sắp mảng có -0.0,+0.0,NaN,±Infinity bằng Double.compare, so với `==` của các cặp đặc biệt.

**Bài 6 — Fraction:** so exact hai phân số `1/3` và `2/6`, rồi thử mẫu âm và Long.MIN_VALUE. Tại sao phép nhân long trực tiếp nguy hiểm?

**Bài 7 — Orientation:** tính dấu cross cho ba điểm nguyên và chứng minh vì sao chuyển sang BigInteger phải xảy ra **trước phép trừ**.

**Bài 8 — Geometry oracle:** xây mọi bộ ba điểm từ 5×5 vị trí, dùng hai cách số học chính xác khác nhau để kiểm dấu orientation.

**Bài 9 — Signed zero:** mô tả `-0.0 == +0.0`, `Double.compare(-0.0,+0.0)` và khi nào cần chuẩn hóa zero trong Map.

**Bài 10 — Decimal:** tạo BigDecimal từ "0.1"+"0.2" và so kết quả với `new BigDecimal(0.1)`, `BigDecimal.valueOf(0.1)`.

**Bài 11 — Rounding:** tính 1/3 bằng BigDecimal với 10 chữ số thập phân và RoundingMode.HALF_EVEN; thử phép chia không kèm rounding.

**Bài 12 — Summation:** trên `[1e16,1,-1e16]`, so naive/Kahan/Neumaier. Thử hoán vị và giải thích Kahan không nhất thiết sửa mọi trường hợp.

**Bài 13 — ULP:** in `Math.ulp(1.0)`, `Math.ulp(1e16)`, `Math.nextUp(1.0)` và so độ lớn bước nhảy.

**Bài 14 — Infinity:** thiết kế bảng quyết định cho `close` với hai Infinity cùng dấu, khác dấu, Infinity và finite, và NaN.

**Bài 15 — Binary search:** xác định điều kiện dừng của phép tìm nghiệm số thực khi midpoint làm tròn bằng một đầu khoảng.

**Bài 16 — Predicate theo đề:** cho yêu cầu “tính tổng tiền chính xác từng cent”, “đo nhiệt độ chấp nhận ±0.1°C” và “sort 1 triệu double chứa NaN”; chọn kiểu số và phép so phù hợp.

**Bài 17 — Differential test:** tạo 4.000 bộ tọa độ long cực trị ngẫu nhiên, so dấu cross từ BigInteger với oracle BigDecimal exact.

**Bài 18 — Phân tích rủi ro:** trong một dự án tính toán, liệt kê dữ liệu nào **exact** và dữ liệu nào **approximate**, ngưỡng chấp nhận lỗi ở mỗi bước và các edge case phải test.

## 36. Tóm tắt và quy trình quyết định

Trước khi viết một phép so số thực, hãy hỏi theo đúng thứ tự:

1. **Giá trị là nguyên/rời rạc hay đại lượng đo gần đúng?** Nếu chính xác, giữ kiểu nguyên và dùng BigInteger/BigDecimal khi cần.
2. **Đề bài đòi equality hay error budget?** Nếu gần đúng, ghi cụ thể sai số theo đơn vị và mức độ lớn.
3. **Cần sort/heap/tree/binary search không?** Nếu cần thứ tự, dùng comparator bắc cầu nhất quán; tránh epsilon-equality làm comparator.
4. **Có NaN, Infinity, -0.0 và giá trị cực trị không?** Chính sách xử lý phải được kiểm thử.
5. **Có nguy cơ overflow ở phép trung gian trước so sánh không?** Chuyển sang biểu diễn rộng hơn **trước khi trừ/nhân**, không chỉ ở kết quả cuối.
6. **Sai số tích lũy có thể khuếch đại qua phép trừ gần nhau hoặc tổng lớn không?** Dùng công thức ổn định, pairwise/compensated sum hoặc exact arithmetic khi phù hợp.
7. **Có oracle độc lập kiểm thử không?** So exact bằng kiểu số khác, test boundary/tie/NaN/extreme và đánh giá đúng hợp đồng.

**Kết luận:** So sánh số thực không phải chọn một `EPS` rồi dùng mọi nơi. Độ đúng xuất phát từ **ngữ nghĩa đề bài**: khi dữ liệu là exact, giữ exact; khi kết quả là approximate, xác định sai số có đơn vị và quy tắc NaN/Infinity; khi cấu trúc dữ liệu cần thứ tự, bảo đảm comparator bắc cầu; khi biểu thức có nguy cơ overflow/cancellation, chọn biểu diễn và công thức số ổn định. Một phép so chỉ đáng tin khi cả **mô hình số, thuật toán và bộ kiểm thử** cùng tuân theo hợp đồng ấy.
