# Khác biệt làm tròn giữa fma và hai phép toán tách rời

## 1. Fused multiply-add là gì?

Một phép fused multiply-add (FMA) tính biểu thức:

```text
x * y + z
```

như một phép toán kết hợp duy nhất: tích chính xác của `x` và `y` được cộng với `z`, sau đó toàn bộ kết quả mới được làm tròn một lần về kiểu dấu phẩy động đích.

Từ Java 9, lớp `java.lang.Math` cung cấp `Math.fma`; `StrictMath` cũng cung cấp `StrictMath.fma`. Cả hai có overload cho `float` và `double`.

```java
double fused = Math.fma(x, y, z);
```

Với ba đối số `double`, kết quả tương đương việc tính chính xác toán học `x * y + z` trên các giá trị nhị phân mà ba biến đang biểu diễn, rồi làm tròn một lần về `double`. Với overload `float`, kết quả được làm tròn một lần về `float`.

FMA đặc biệt hữu ích trong tính toán số học vì phép nhân và phép cộng tách rời thường có hai lần làm tròn: một lần sau phép nhân và một lần sau phép cộng.

## 2. Hai phép toán tách rời làm tròn như thế nào?

Kiểu `double` trong Java biểu diễn số theo định dạng dấu phẩy động nhị phân 64 bit. Phần lớn số thực thập phân không thể biểu diễn chính xác bằng một số bit hữu hạn, vì vậy giá trị được làm tròn về số `double` gần nhất.

Khi tách phép nhân và phép cộng:

```java
double product = x * y;
double result = product + z;
```

quá trình gồm hai bước:

1. Tính tích `x * y`, sau đó làm tròn tích về `double` để lưu vào `product`.
2. Cộng giá trị đã làm tròn với `z`, rồi làm tròn kết quả phép cộng về `double`.

Thông tin bị mất ở lần làm tròn thứ nhất không thể được khôi phục ở phép cộng tiếp theo. Ngay cả khi kết quả cuối cùng của biểu thức chính xác có thể biểu diễn được, giá trị trung gian đã làm tròn vẫn có thể khiến kết quả tách rời khác đi.

Với FMA, tích trung gian không bị làm tròn riêng. Phép cộng được thực hiện trên tích chính xác và chỉ kết quả cuối cùng được làm tròn.

## 3. Ví dụ cho kết quả khác nhau rõ rệt

Ta chọn các giá trị:

```text
epsilon = 2^-27
x = 1 + epsilon
y = 1 - epsilon
z = -1
```

Các giá trị `x`, `y` và `z` đều biểu diễn chính xác dưới dạng `double`. Tích chính xác là:

```text
x * y = (1 + 2^-27)(1 - 2^-27)
      = 1 - 2^-54
```

Hai số `double` kề nhau bao quanh tích này là `1.0` và `1.0 - 2^-53`. Giá trị chính xác `1.0 - 2^-54` nằm đúng giữa hai số đó. Quy tắc làm tròn gần nhất, hòa thì chọn số có bit cuối của significand chẵn (round to nearest, ties to even) chọn `1.0`.

Do đó, phép tính tách rời thực hiện:

```text
rounded product = 1.0
separate result = 1.0 + (-1.0) = 0.0
```

FMA giữ tích chính xác cho đến khi cộng với `-1.0`:

```text
(1 - 2^-54) + (-1)
= -2^-54
```

Giá trị `-2^-54` biểu diễn chính xác dưới dạng `double`, nên FMA trả về giá trị khác 0.

## 4. Chương trình Java chạy được

Ví dụ dùng `Math.scalb(1.0d, -27)` để tạo chính xác lũy thừa của hai. Cách này tránh phụ thuộc vào việc viết một số thập phân gần đúng cho epsilon.

```java
public class FmaRoundingDemo {
    public static void main(String[] args) {
        double epsilon = Math.scalb(1.0d, -27);
        double x = 1.0d + epsilon;
        double y = 1.0d - epsilon;
        double z = -1.0d;

        double product = x * y;
        double separate = product + z;
        double fused = Math.fma(x, y, z);

        System.out.println("epsilon = " + epsilon);
        System.out.println("x = " + x);
        System.out.println("y = " + y);
        System.out.println("rounded product = " + product);
        System.out.println("separate result = " + separate);
        System.out.println("fma result = " + fused);
        System.out.println("separate hex = " + Double.toHexString(separate));
        System.out.println("fma hex = " + Double.toHexString(fused));
        System.out.println("fma exact expected = "
                + (-Math.scalb(1.0d, -54)));
    }
}
```

Lưu mã nguồn trong tệp `FmaRoundingDemo.java`, sau đó biên dịch và chạy với Java 17 trở lên:

```bash
javac --release 17 -Xlint:all FmaRoundingDemo.java
java FmaRoundingDemo
```

Kết quả:

```text
epsilon = 7.450580596923828E-9
x = 1.0000000074505806
y = 0.9999999925494194
rounded product = 1.0
separate result = 0.0
fma result = -5.551115123125783E-17
separate hex = 0x0.0p0
fma hex = -0x1.0p-54
fma exact expected = -5.551115123125783E-17
```

Biểu diễn hexadecimal giúp nhìn rõ kết quả: phép tính tách rời trả về số không, còn FMA trả về `-2^-54`. Ví dụ đã được biên dịch bằng `javac --release 17 -Xlint:all` và chạy với kết quả trên.

## 5. Math.fma và StrictMath.fma

Hai API có cùng mục đích và cùng quy tắc FMA:

```java
double a = Math.fma(x, y, z);
double b = StrictMath.fma(x, y, z);
```

- `Math.fma` thuộc lớp `Math` và là lựa chọn thông thường cho phép toán FMA.
- `StrictMath.fma` thuộc lớp `StrictMath` và cung cấp cùng phép toán theo hợp đồng của `StrictMath`.

Không nên thay FMA bằng biểu thức `x * y + z` nếu chương trình cần chính xác ngữ nghĩa một lần làm tròn. Ngược lại, nếu cần giữ kết quả của hai bước làm tròn riêng, hãy viết và lưu phép nhân trung gian rõ ràng.

## 6. FMA giúp giảm sai số ở đâu?

FMA thường hữu ích trong những thuật toán lặp lại phép nhân-cộng:

### Tính đa thức theo dạng Horner

Đa thức:

```text
a*x*x + b*x + c
```

có thể được sắp xếp theo dạng Horner:

```text
(a*x + b)*x + c
```

Dùng FMA cho từng bước:

```java
double value = Math.fma(Math.fma(a, x, b), x, c);
```

Mỗi lời gọi FMA thực hiện một phép nhân-cộng với một lần làm tròn. Cách này thường giảm số lần làm tròn trung gian so với các phép nhân và cộng tách rời.

### Tích vô hướng (dot product)

Khi cộng dồn tích của hai mảng số:

```java
double sum = 0.0d;
for (int i = 0; i < left.length; i++) {
    sum = Math.fma(left[i], right[i], sum);
}
```

Mỗi vòng lặp tính `left[i] * right[i] + sum` bằng một phép FMA. Điều này tránh làm tròn tích riêng trước khi cộng vào tổng. Phép cộng dồn vẫn làm tròn ở mỗi vòng lặp, nên FMA không loại bỏ toàn bộ sai số của thuật toán.

## 7. FMA không có nghĩa là mọi kết quả luôn “tốt hơn”

FMA tính kết quả chính xác của biểu thức nhân-cộng trên các giá trị đầu vào đã được biểu diễn, rồi làm tròn một lần. Đây là một bảo đảm toán học mạnh hơn hai bước làm tròn riêng, nhưng vẫn có những giới hạn:

- Các biến đầu vào có thể đã là giá trị xấp xỉ của dữ liệu thực ban đầu.
- Một lần làm tròn ở kết quả cuối vẫn có thể tạo sai số.
- Sai số do thuật toán, điều kiện bài toán hoặc phép triệt tiêu vẫn có thể tồn tại.
- Kết quả FMA có thể khác kết quả của chương trình cũ vốn dựa vào hai bước làm tròn.
- Không phải mọi biểu thức đều nên chuyển thành FMA; cần kiểm tra yêu cầu số học và ý nghĩa của kết quả.

Nếu chương trình cần tương thích chính xác với kết quả đã công bố hoặc một định dạng tính toán cũ, thay phép nhân-cộng tách rời bằng FMA có thể làm thay đổi đầu ra dù FMA chính xác hơn đối với biểu thức toán học tương ứng.

## 8. Lưu ý về hiệu năng và tính xác định

`Math.fma` thể hiện rõ ý định sử dụng một phép toán fused. JVM có thể tận dụng phần cứng hỗ trợ FMA, nhưng không nên giả định rằng mọi máy đều có cùng mức tăng tốc. Khi hiệu năng là tiêu chí, hãy benchmark trên JDK, CPU và dữ liệu thực tế.

Từ Java 17, các biểu thức dấu phẩy động của Java luôn dùng ngữ nghĩa strict. Ví dụ ở trên dùng `javac --release 17` để có hành vi trung gian rõ ràng và có thể tái lập. FMA vẫn là phép toán được yêu cầu tường minh qua `Math.fma` hoặc `StrictMath.fma`; không được coi một biểu thức nhân-cộng thông thường là hợp đồng thay thế cho API đó.

## 9. Khi nào nên dùng phép tính nào?

| Nhu cầu | Cách viết |
|---|---|
| Cần một phép nhân-cộng với một lần làm tròn | `Math.fma(x, y, z)` |
| Cần giữ hai bước làm tròn riêng biệt | `double p = x * y; double r = p + z;` |
| Tính Horner hoặc tích vô hướng cần giảm làm tròn trung gian | Dùng `Math.fma` trong từng bước |
| Cần duy trì kết quả tương thích với cách tính tách rời | Giữ phép nhân và phép cộng riêng, kiểm tra bằng test |
| Chưa rõ độ nhạy số học của thuật toán | So sánh sai số trên miền dữ liệu đại diện trước khi đổi |

## 10. Checklist khi review mã nguồn

1. Biểu thức có dạng `x * y + z` hoặc một phép nhân-cộng trong vòng lặp không?
2. Yêu cầu số học cần một lần làm tròn hay hai lần làm tròn?
3. Đầu vào có nằm gần điểm giữa giữa hai giá trị biểu diễn được, nơi làm tròn trung gian có thể thay đổi kết quả không?
4. Kết quả có được dùng trong thuật toán nhạy với sai số, như Horner hoặc tích vô hướng không?
5. Việc chuyển sang FMA có làm thay đổi kết quả mà API hoặc dữ liệu đầu ra đang cam kết không?
6. Ví dụ kiểm thử có xác nhận cả giá trị thập phân lẫn biểu diễn hexadecimal ở các trường hợp biên không?
7. Nếu quan tâm hiệu năng, đã benchmark trên môi trường chạy mục tiêu chưa?

`Math.fma` và `StrictMath.fma` là API Java 9 để thực hiện phép fused multiply-add với một lần làm tròn. Khác biệt cốt lõi là FMA cộng vào tích chính xác trước khi làm tròn; phép nhân và phép cộng tách rời làm tròn tích trước rồi mới cộng.