# Nhân cộng hợp nhất bằng Math.fma trong Java

## 1. Math.fma là gì?

Math.fma thực hiện phép nhân cộng hợp nhất (fused multiply-add): tính tích của hai số rồi cộng với số thứ ba, sau đó chỉ làm tròn một lần cho kết quả cuối cùng.

Cú pháp:

~~~java
double result = Math.fma(a, b, c);
float resultFloat = Math.fma(x, y, z);
~~~

Về mặt toán học, phép tính là:

\[
\operatorname{fma}(a,b,c)=a\times b+c
\]

Điểm khác biệt nằm ở cách tính số dấu phẩy động:

- Biểu thức a * b + c thông thường thực hiện phép nhân, làm tròn tích về kiểu kết quả, sau đó cộng c và làm tròn lần nữa.
- Math.fma tính tích và tổng với độ chính xác trung gian đủ để chỉ làm tròn một lần ở kết quả cuối.

Vì vậy, Math.fma có thể cho kết quả khác biểu thức a * b + c. Khác biệt này có ý nghĩa khi tích và số hạng cộng gần triệt tiêu nhau, hoặc khi tích trung gian vượt phạm vi biểu diễn nhưng tổng cuối vẫn biểu diễn được.

Math.fma thuộc lớp java.lang.Math nên không cần import. Các overload float và double có từ Java 9.

## 2. Vì sao một lần làm tròn lại quan trọng?

Kiểu float và double lưu số theo dạng nhị phân với số bit hữu hạn. Nhiều giá trị thập phân không thể biểu diễn chính xác. Mỗi phép toán có thể phải làm tròn về giá trị gần nhất có thể biểu diễn.

Với biểu thức a * b + c, tích a * b có thể bị làm tròn trước khi cộng c. Nếu c gần bằng số đối của tích chính xác, sai lệch nhỏ do lần làm tròn đầu tiên có thể trở thành phần lớn của kết quả cuối.

Math.fma tránh lần làm tròn trung gian đó. Phương thức tính giá trị chính xác của tích và tổng theo ngữ nghĩa fused multiply-add rồi làm tròn một lần về kiểu float hoặc double.

Điều này không có nghĩa Math.fma tạo ra độ chính xác vô hạn. Các toán hạng đầu vào vẫn là giá trị float hoặc double đã được biểu diễn hữu hạn; kết quả cuối cũng phải làm tròn về kiểu tương ứng. FMA chỉ loại bỏ lần làm tròn trung gian giữa phép nhân và phép cộng.

## 3. Ví dụ sai khác do triệt tiêu số

Ví dụ sau chọn hai số rất gần 1. Tích chính xác của chúng hơi nhỏ hơn 1, nhưng khi chỉ lưu kết quả phép nhân dưới dạng double, giá trị này được làm tròn thành 1.0. Khi trừ 1.0, biểu thức thông thường cho kết quả 0.0.

Math.fma giữ được phần sai khác nhỏ đó cho đến lần làm tròn cuối:

~~~java
double epsilon = Math.scalb(1.0, -27);
double a = 1.0 + epsilon;
double b = 1.0 - epsilon;

double separate = a * b - 1.0;
double fused = Math.fma(a, b, -1.0);

System.out.println("separate: " + separate);
System.out.println("fused: " + fused);
~~~

Kết quả:

~~~text
separate: 0.0
fused: -5.551115123125783E-17
~~~

Giá trị fused tương ứng với -2^-54. Phép nhân thông thường đã làm tròn tích trước khi trừ 1.0 nên thông tin nhỏ bị mất. Math.fma thực hiện phép nhân cộng như một phép toán hợp nhất và giữ lại phần dư chính xác hơn.

Đây là ví dụ điển hình cho thấy hai biểu thức có cùng công thức đại số vẫn có thể cho kết quả khác nhau khi tính bằng số dấu phẩy động.

## 4. FMA có thể tránh tràn ở kết quả trung gian

Một lợi ích khác là FMA không làm tròn tích trung gian thành infinity trước khi cộng số hạng thứ ba. Nếu tích chính xác vượt phạm vi double nhưng tổng chính xác cuối cùng vẫn nằm trong phạm vi biểu diễn, Math.fma có thể trả về kết quả hữu hạn.

~~~java
double separate = 1.0e308 * 2.0 - 1.0e308;
double fused = Math.fma(1.0e308, 2.0, -1.0e308);

System.out.println("overflow separate: " + separate);
System.out.println("overflow fused: " + fused);
~~~

Kết quả:

~~~text
overflow separate: Infinity
overflow fused: 1.0E308
~~~

Ở biểu thức thông thường, phép nhân 1.0e308 * 2.0 vượt phạm vi double và trở thành Infinity. Sau đó trừ 1.0e308 vẫn là Infinity. Math.fma tính tích và tổng hợp nhất nên kết quả cuối cùng là 1.0e308.

FMA không thể ngăn mọi trường hợp tràn. Nếu chính kết quả chính xác cuối cùng vượt phạm vi kiểu dữ liệu, kết quả vẫn có thể là Infinity.

## 5. Các overload float và double

Math.fma có hai overload chính:

~~~java
public static double fma(double a, double b, double c)

public static float fma(float a, float b, float c)
~~~

Chọn overload dựa trên kiểu toán hạng:

~~~java
double doubleResult = Math.fma(1.5, 2.0, 4.0);
float floatResult = Math.fma(1.5f, 2.0f, 0.25f);

System.out.println(doubleResult);
System.out.println(floatResult);
~~~

Kết quả:

~~~text
7.0
3.25
~~~

Khi dùng hậu tố f, các literal như 1.5f và 2.0f có kiểu float nên overload float được chọn. Nếu truyền literal double hoặc biến double, overload double được chọn.

Không nên chuyển tất cả toán hạng sang double một cách tùy tiện nếu thuật toán yêu cầu kết quả float. Việc đổi kiểu sẽ thay đổi độ chính xác và phạm vi của kết quả.

## 6. Ứng dụng trong công thức và thuật toán số

### Tính biểu thức tuyến tính

Với biểu thức a*x + b, có thể dùng:

~~~java
double y = Math.fma(a, x, b);
~~~

Phép nhân và phép cộng được hợp nhất. Cách này phù hợp với các phép tính lặp lại trong mô hình số, mô phỏng, đồ họa và xử lý tín hiệu khi cần kiểm soát sai số làm tròn.

### Tính đa thức bằng phương pháp Horner

Đa thức:

\[
p(x)=a_0x^2+a_1x+a_2
\]

có thể viết lại theo dạng Horner:

\[
p(x)=(a_0x+a_1)x+a_2
\]

Dùng Math.fma để hợp nhất từng bước:

~~~java
double x = 5.0;
double a0 = 2.0;
double a1 = 3.0;
double a2 = 4.0;

double result = Math.fma(Math.fma(a0, x, a1), x, a2);
System.out.println(result);
~~~

Kết quả:

~~~text
69.0
~~~

Horner giảm số phép nhân cần thực hiện so với cách khai triển trực tiếp. Dùng FMA cho từng bước còn giảm số lần làm tròn trung gian trong các cặp nhân cộng.

### Tích vô hướng và phép cộng dồn

Trong một vòng lặp tính tổng tích của hai mảng, có thể viết:

~~~java
double sum = 0.0;

for (int i = 0; i < left.length; i++) {
    sum = Math.fma(left[i], right[i], sum);
}
~~~

Mỗi vòng lặp hợp nhất phép nhân hai phần tử với phép cộng vào tổng hiện tại. Điều này có thể giảm sai số so với việc tính tích riêng rồi cộng vào sum.

Tuy nhiên, tổng vẫn được làm tròn sau mỗi vòng lặp. Kết quả còn phụ thuộc thứ tự cộng, dữ liệu đầu vào và độ lớn tương đối của các số. Với yêu cầu độ chính xác cao, cần xem xét cả thuật toán cộng bù, thứ tự cộng hoặc thư viện số học phù hợp; chỉ dùng FMA không bảo đảm mọi sai số đều biến mất.

## 7. Giá trị đặc biệt: NaN và vô cực

Math.fma tuân theo quy tắc số dấu phẩy động IEEE 754 đối với các giá trị đặc biệt. Một số trường hợp cần lưu ý:

- Nếu một trong ba đối số là NaN, kết quả là NaN.
- Nếu một toán hạng của phép nhân là vô cực và toán hạng còn lại là số 0, phép nhân không xác định và kết quả là NaN.
- Nếu tích có dấu vô cực và số hạng cộng là vô cực trái dấu, kết quả là NaN.
- Nếu kết quả chính xác cuối cùng vượt phạm vi kiểu float hoặc double, kết quả có thể là vô cực.

Không nên dùng phép so sánh == để kiểm tra NaN vì NaN không bằng chính nó. Dùng Double.isNaN hoặc Float.isNaN:

~~~java
double value = Math.fma(Double.POSITIVE_INFINITY, 0.0, 1.0);

System.out.println(Double.isNaN(value));
~~~

Kết quả:

~~~text
true
~~~

Nếu miền dữ liệu cho phép NaN hoặc vô cực, hãy quyết định rõ cách xử lý chúng trong nghiệp vụ và kiểm thử các trường hợp biên tương ứng.

## 8. Math.fma và strict floating-point trong Java hiện đại

Math.fma có từ Java 9. Java 17 chuẩn hóa việc thực thi phép toán dấu phẩy động theo ngữ nghĩa strict trên mọi nền tảng thông qua JEP 306. Vì vậy, với Java 17 trở lên, từ khóa strictfp không còn cần thiết để yêu cầu các phép toán float và double tuân theo ngữ nghĩa nghiêm ngặt.

Điều này không làm cho phép nhân cộng thông thường trở thành phép FMA. Nếu cần ngữ nghĩa nhân cộng hợp nhất với một lần làm tròn, hãy gọi Math.fma một cách tường minh.

Math.fma là lựa chọn về ngữ nghĩa và độ chính xác của phép toán. Không nên giả định rằng trình biên dịch sẽ tự thay mọi biểu thức a * b + c bằng lời gọi này, vì hai cách có thể tạo ra kết quả khác nhau.

## 9. Khi nào nên và không nên dùng Math.fma?

Nên cân nhắc Math.fma khi:

- Công thức có dạng a*b+c và sai số làm tròn ảnh hưởng đáng kể đến kết quả.
- Hai thành phần gần triệt tiêu nhau.
- Muốn tránh tràn hoặc mất thông tin ở tích trung gian khi tổng cuối vẫn hữu hạn.
- Thuật toán số như Horner, tích vô hướng hoặc mô phỏng có lợi từ phép nhân cộng hợp nhất.
- Cần kết quả theo đúng ngữ nghĩa IEEE 754 fused multiply-add.

Không nên coi FMA là giải pháp thay thế cho mọi phép nhân cộng:

- Nếu kết quả không nhạy với sai số làm tròn, lời gọi FMA có thể không mang lại lợi ích thực tế.
- FMA có thể cho kết quả khác kết quả cũ của chương trình; khi thay thế biểu thức, cần kiểm thử lại các trường hợp biên.
- FMA không biến double thành số thập phân chính xác và không thay thế BigDecimal cho các phép tính tài chính cần quy tắc thập phân.
- Không mặc định FMA luôn nhanh hơn. Hiệu năng phụ thuộc JVM, CPU và workload; hãy đo trên dữ liệu thực tế nếu tốc độ là mục tiêu.
- FMA không khắc phục sai thứ tự thuật toán, dữ liệu đầu vào sai hoặc lỗi tích lũy từ các phép tính khác.

## 10. Ví dụ hoàn chỉnh có thể biên dịch

**Tệp MathFmaDemo.java:**

~~~java
public class MathFmaDemo {
    public static void main(String[] args) {
        double epsilon = Math.scalb(1.0, -27);
        double a = 1.0 + epsilon;
        double b = 1.0 - epsilon;

        double separate = a * b - 1.0;
        double fused = Math.fma(a, b, -1.0);
        System.out.println("separate: " + separate);
        System.out.println("fused: " + fused);

        double separateOverflow = 1.0e308 * 2.0 - 1.0e308;
        double fusedOverflow = Math.fma(1.0e308, 2.0, -1.0e308);
        System.out.println("overflow separate: " + separateOverflow);
        System.out.println("overflow fused: " + fusedOverflow);

        float floatResult = Math.fma(1.5f, 2.0f, 0.25f);
        System.out.println("float result: " + floatResult);

        double x = 5.0;
        double polynomial = Math.fma(Math.fma(2.0, x, 3.0), x, 4.0);
        System.out.println("polynomial: " + polynomial);
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all MathFmaDemo.java
java MathFmaDemo
~~~

Kết quả chuẩn:

~~~text
separate: 0.0
fused: -5.551115123125783E-17
overflow separate: Infinity
overflow fused: 1.0E308
float result: 3.25
polynomial: 69.0
~~~

Chương trình minh họa sự khác biệt về kết quả, không chỉ cách gọi API. Hai dòng đầu cho thấy FMA giữ được phần dư bị mất khi làm tròn tích riêng. Hai dòng tiếp theo cho thấy FMA có thể tránh tràn ở kết quả trung gian. Hai dòng cuối xác nhận overload float và cách áp dụng FMA cho đa thức.

## 11. Lỗi thường gặp

- **Cho rằng Math.fma luôn giống a*b+c:** hai cách có thể khác do số lần làm tròn.
- **Nghĩ FMA làm tăng độ chính xác vô hạn:** toán hạng và kết quả vẫn bị giới hạn bởi float hoặc double.
- **Chỉ kiểm tra trường hợp số thông thường:** nên kiểm tra cả triệt tiêu, giá trị lớn, NaN, vô cực và số 0 nếu các trường hợp đó có thể xuất hiện.
- **Đổi kiểu không chủ ý:** literal có hậu tố f chọn overload float; literal không có hậu tố thường là double.
- **Dùng FMA cho tiền tệ:** FMA vẫn là số học nhị phân dấu phẩy động. Với tiền tệ cần quy tắc thập phân, hãy dùng BigDecimal cùng chính sách làm tròn phù hợp.
- **Giả định FMA luôn nhanh hơn:** hiệu năng tùy môi trường thực thi. Đo benchmark khi cần tối ưu.
- **Cho rằng Java tự hợp nhất mọi phép nhân cộng:** gọi Math.fma tường minh khi cần ngữ nghĩa một lần làm tròn.

## 12. Ghi nhớ

Math.fma(a, b, c) tính a*b+c với một lần làm tròn ở kết quả cuối. API này có từ Java 9 và có overload cho float, double. FMA hữu ích khi phép nhân cộng nhạy với sai số, khi các số gần triệt tiêu hoặc khi tích trung gian có thể tràn dù kết quả cuối còn hữu hạn. Dùng nó trong công thức tuyến tính, Horner và phép cộng dồn khi phù hợp; đồng thời kiểm thử lại kết quả vì FMA có thể khác phép nhân rồi cộng thông thường. FMA giảm một nguồn sai số làm tròn, nhưng không thay thế việc thiết kế thuật toán số đúng.
