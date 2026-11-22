# Math, StrictMath và nhu cầu kết quả tái lập

## 1. Cùng công thức chưa đủ để có cùng kết quả

Một chương trình mô phỏng có thể cần chạy lại để tìm lỗi. Một bộ kiểm thử có thể cần so sánh kết quả giữa máy phát triển và máy CI. Trong những trường hợp đó, “hai số rất gần nhau” và “hai kết quả có cùng biểu diễn” là hai yêu cầu khác nhau.

Với số thực dấu phẩy động, cần tách ba câu hỏi:

| Mục tiêu | Câu hỏi cần trả lời |
|---|---|
| Độ chính xác | Kết quả gần giá trị toán học đúng đến mức nào? |
| Tính ổn định của thuật toán | Sai số đầu vào và sai số làm tròn có bị khuếch đại mạnh không? |
| Khả năng tái lập | Với dữ liệu và quy trình đã xác định, lần chạy khác có cho cùng kết quả theo tiêu chí đã chọn không? |

Một thuật toán có thể lặp lại chính xác cùng một kết quả sai. Một thuật toán khác có thể cho các kết quả lệch vài bit cuối nhưng đều đạt sai số nghiệp vụ. Vì vậy, hãy xác định yêu cầu trước khi chọn `Math`, `StrictMath` và cách kiểm thử.

Bài này dùng Java 17 trở lên. Tên nhóm kiến thức “Java 6” không có nghĩa là phải cài JDK 6 hay học lại cách xử lý dấu phẩy động của JVM cũ.

## 2. Hai lớp có vai trò gì?

`java.lang.Math` và `java.lang.StrictMath` cung cấp các phương thức tĩnh như `sqrt`, `sin`, `cos`, `log`, `exp`. Chúng được dùng trực tiếp, không cần tạo đối tượng hoặc thêm thư viện.

Điểm phân biệt chính nằm ở **hợp đồng kết quả của từng phương thức**, không nằm ở việc một lớp dùng `double` “tốt hơn” lớp kia.

### Math: tuân thủ hợp đồng, có dư địa tối ưu

Một số hàm của `Math` cho phép các triển khai hợp lệ trả về kết quả khác nhau ở bit cuối. Triển khai có thể tận dụng lệnh phần cứng hoặc thư viện của nền tảng, nhưng vẫn phải đáp ứng giới hạn sai số và các điều kiện trong đặc tả phương thức. Vì thế, `Math` phù hợp khi ứng dụng chấp nhận sai số đã quy định và cần đánh giá hiệu năng trên tải thực tế. [Hợp đồng lớp Math](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html).

Điều này không có nghĩa mỗi lần gọi `Math.sin(x)` sẽ cho một số ngẫu nhiên, hoặc hai máy chắc chắn cho hai kết quả khác nhau. Một ví dụ chạy trên một máy thường không bộc lộ khác biệt; việc không quan sát thấy khác biệt không tạo thêm bảo đảm ngoài hợp đồng API.

### StrictMath: cố định ngữ nghĩa thuật toán cho các hàm được chỉ định

`StrictMath` ràng buộc một nhóm hàm phải cho kết quả theo các thuật toán được công bố của fdlibm 5.3, nhằm hỗ trợ tính khả chuyển và tái lập. Nhóm này gồm `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `exp`, `log`, `log10`, `cbrt`, `pow`, `sinh`, `cosh`, `tanh`, `hypot`, `expm1` và `log1p`. [Hợp đồng lớp StrictMath](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StrictMath.html).

Với đầu vào hữu hạn xác định và cùng chuỗi phép tính, đây là lựa chọn thích hợp khi quy trình cần kết quả của các hàm đó theo cùng một ngữ nghĩa đã quy định. Tuy nhiên, đổi tên lớp không tự cố định đầu vào, thứ tự cộng, lịch thực thi đồng thời hoặc cách lưu kết quả.

Không nên suy ra rằng mọi phương thức trong `StrictMath` đều là một thuật toán fdlibm, hay mọi phương thức trong `Math` đều được phép khác nhau. Ví dụ, `sqrt` của cả hai lớp yêu cầu căn bậc hai được làm tròn đúng; với `2.0`, chúng phải trả về cùng giá trị `double`. [Math.sqrt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#sqrt(double)), [StrictMath.sqrt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StrictMath.html#sqrt(double)).

### Chọn theo yêu cầu

| Tình huống | Hướng lựa chọn |
|---|---|
| Tính toán thông thường, kiểm thử bằng sai số được chấp nhận | Bắt đầu với Math và hợp đồng của phương thức cụ thể |
| Mô phỏng hoặc quy trình cần đối chiếu kết quả các hàm siêu việt giữa các nền tảng Java | Dùng StrictMath cho phần cần tái lập, đồng thời cố định toàn bộ quy trình |
| Cần số thập phân chính xác theo quy tắc nghiệp vụ | Đánh giá mô hình số khác, chẳng hạn BigDecimal với quy tắc làm tròn rõ ràng |
| Thuật toán bị mất chữ số có nghĩa hoặc tràn số | Sửa thuật toán và miền dữ liệu; đổi Math thành StrictMath chưa giải quyết nguyên nhân |

Không mặc định `StrictMath` luôn chính xác hơn hoặc luôn chậm hơn. Tái lập và sai số là hai tiêu chí khác nhau; hiệu năng phải được đo với phương thức, JVM và tải sử dụng thực tế.

## 3. Java 17+ đã luôn đánh giá biểu thức dấu phẩy động theo chế độ strict

Từ Java 17, mọi biểu thức dấu phẩy động Java đều được đánh giá theo ngữ nghĩa strict. Thêm `strictfp` không làm thay đổi cách đánh giá biểu thức trên các phiên bản này. Vì vậy, mã mới không cần thêm từ khóa đó để “bật tính tái lập”. [JLS §15.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.4).

Hai tầng cần phân biệt:

- `a + b`, `a * b`: phép toán của ngôn ngữ, chịu quy tắc đánh giá và làm tròn của Java.
- `Math.sin(a)`, `StrictMath.sin(a)`: lời gọi thư viện, chịu thêm hợp đồng của phương thức được gọi.

Always-strict không làm `Math.sin` tự trở thành `StrictMath.sin`. Nó cũng không làm số thực dấu phẩy động có tính kết hợp. Java bảo toàn cách đánh giá mà chương trình đã chỉ định; nếu lập trình viên đổi cấu trúc phép tính, kết quả có thể đổi. [JLS §15.7.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.7.3).

## 4. Những yếu tố StrictMath không tự giải quyết

### 4.1. Thứ tự cộng vẫn quan trọng

Xét hai dãy:

```text
A: 10^16, 1, -10^16
B: 10^16, -10^16, 1
```

Khi cộng tuần tự bằng `double` từ tổng ban đầu `0.0`:

- A cho `0.0`: ở độ lớn `10^16`, bước cộng `1.0` bị làm tròn mất.
- B cho `1.0`: hai số lớn triệt tiêu trước, sau đó mới cộng `1.0`.

Đây là hệ quả của các bước làm tròn, không phải dấu hiệu JVM chạy sai. Dùng `StrictMath` ở một hàm khác trong chương trình không sửa được thứ tự cộng này.

Với tính toán song song, nếu yêu cầu tái lập chặt, cần xác định cách chia nhóm và cây gộp kết quả. Việc nguồn dữ liệu có thứ tự không tự chứng minh rằng mọi cách rút gọn song song đều có cùng cấu trúc phép cộng. Khi chưa có hợp đồng đó, một vòng lặp tuần tự với dữ liệu cố định dễ kiểm soát hơn.

### 4.2. Nhân rồi cộng khác phép FMA

`Math.fma(a, b, c)` và `StrictMath.fma(a, b, c)` biểu diễn phép nhân cộng hợp nhất (fused multiply-add): tính tích và tổng chính xác về mặt toán học rồi làm tròn một lần sang kiểu kết quả. Biểu thức thông thường `a * b + c` có bước làm tròn ở phép nhân và ở phép cộng. [Math.fma](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#fma(double,double,double)).

Chọn:

```text
d = 2^-27
a = 1 + d
b = 1 - d
c = -1
```

Theo đại số, `a*b+c = -2^-54`. Trong biểu thức rời, tích `a*b` được làm tròn thành `1.0`, rồi trừ `1.0` cho `+0.0`. FMA giữ thông tin của tích đến bước cộng và trả về `-2^-54`.

Do đó, thay biểu thức rời bằng FMA là một thay đổi thuật toán có thể đổi kết quả. Dùng FMA khi nó phù hợp với mục tiêu sai số; nếu đã có kết quả chuẩn dùng để đối chiếu từng bit, cần đánh giá lại kết quả chuẩn khi thay đổi này được thực hiện.

### 4.3. Dữ liệu và cấu hình cũng thuộc quy trình

Để một phép tính hữu hạn có thể đối chiếu giữa các lần chạy, cần xác định ít nhất:

1. Dữ liệu đầu vào và biểu diễn của chúng, bao gồm cách chuyển đổi từ tệp hoặc chuỗi.
2. Thuật toán, thứ tự phép tính, kiểu `float`/`double` và các vị trí ép kiểu.
3. Những phương thức thư viện được chọn, kể cả có dùng FMA hay không.
4. Cách chia nhóm, gộp tổng và quản lý dữ liệu dùng chung nếu có chạy đồng thời.
5. Tiêu chí so sánh, cách lưu kết quả và phiên bản của thuật toán.

Nếu có số giả ngẫu nhiên, cần quy định bộ sinh, hạt giống và thứ tự lấy mẫu. Chỉ cố định hạt giống nhưng đổi số lần gọi hoặc thứ tự gọi vẫn có thể thay đổi toàn bộ dữ liệu tiếp theo. Tên `StrictMath` cũng không khiến `StrictMath.random()` trở thành nguồn đầu vào cố định.

## 5. Chương trình chạy đầy đủ

Lưu thành `ReproducibleMathLab.java`. Chương trình dùng Java 17+, không có thư viện ngoài.

```java
public final class ReproducibleMathLab {
    private ReproducibleMathLab() {
    }

    private static double sum(double[] values) {
        double total = 0.0;
        for (double value : values) {
            total += value;
        }
        return total;
    }

    private static double score(double[] input) {
        double total = 0.0;
        for (double x : input) {
            if (!Double.isFinite(x)) {
                throw new IllegalArgumentException("finite input required");
            }
            total += StrictMath.sin(x);
        }
        return total;
    }

    private static boolean sameRepresentation(double a, double b) {
        return Double.doubleToLongBits(a) == Double.doubleToLongBits(b);
    }

    public static void main(String[] args) {
        System.out.println("sin(1)=" + Double.toHexString(StrictMath.sin(1.0)));
        System.out.println("sqrtBits="
                + sameRepresentation(Math.sqrt(2.0), StrictMath.sqrt(2.0)));
        System.out.println("sumA=" + sum(new double[] {1e16, 1.0, -1e16}));
        System.out.println("sumB=" + sum(new double[] {1e16, -1e16, 1.0}));

        double delta = Math.scalb(1.0, -27);
        double a = 1.0 + delta;
        double b = 1.0 - delta;
        System.out.println("plain=" + Double.toHexString(a * b - 1.0));
        System.out.println("fma=" + Double.toHexString(StrictMath.fma(a, b, -1.0)));

        System.out.println("zeroNumeric=" + (+0.0 == -0.0));
        System.out.println("zeroBits=" + sameRepresentation(+0.0, -0.0));

        double[] input = {0.0, 0.5, 1.0};
        double first = score(input);
        double second = score(input);
        System.out.println("score=" + Double.toHexString(first));
        System.out.println("repeatBits=" + sameRepresentation(first, second));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac -Xlint:all -Werror ReproducibleMathLab.java
java ReproducibleMathLab
```

Stdout:

```text
sin(1)=0x1.aed548f090ceep-1
sqrtBits=true
sumA=0.0
sumB=1.0
plain=0x0.0p0
fma=-0x1.0p-54
zeroNumeric=true
zeroBits=false
score=0x1.52264649747f3p0
repeatBits=true
```

Cách đọc kết quả:

- `Double.toHexString` hiển thị giá trị nhị phân dưới dạng hệ mười sáu: `p-54` nghĩa là nhân với `2^-54`. Cách hiển thị này giúp nhìn rõ giá trị `double` thực tế.
- `sqrtBits=true` minh họa rằng hai lớp có thể có cùng hợp đồng xác định kết quả cho một phương thức.
- `sumA`/`sumB` chứng minh thay đổi thứ tự cộng có thể thay đổi kết quả ngay trong cùng một lần chạy.
- `plain`/`fma` thể hiện hai mô hình làm tròn khác nhau.
- `score` dùng `StrictMath.sin`, cộng theo thứ tự cố định, với một mảng đầu vào không bị thay đổi trong lúc tính.
- `repeatBits=true` xác nhận hai lần chạy hàm trong chương trình này cho cùng biểu diễn. Riêng phép thử cục bộ đó không phải là bằng chứng cho mọi JVM; bảo đảm khả chuyển phải dựa vào đặc tả của các phép toán đã dùng.

`score` chủ động từ chối đầu vào NaN/vô cực để ví dụ có miền dữ liệu rõ ràng. Đây là chính sách của hàm ví dụ, không phải quy tắc bắt buộc cho mọi ứng dụng.

## 6. So sánh kết quả theo tiêu chí nào?

### So sánh giá trị bằng ==

`+0.0 == -0.0` là `true`, nhưng `NaN == NaN` là `false`. Vì vậy, `==` không phải phép kiểm tra “mọi bit đều giống nhau”. Dấu của zero còn có thể ảnh hưởng phép tính tiếp theo, chẳng hạn `1.0 / -0.0` cho âm vô cực. [Hợp đồng so sánh Double](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html).

### So sánh biểu diễn đã quy chuẩn NaN

Hàm `sameRepresentation` trong chương trình dùng `Double.doubleToLongBits`: phân biệt hai dấu zero và quy các NaN về một biểu diễn chuẩn. Nó phù hợp khi tiêu chí coi mọi NaN là một nhóm nhưng vẫn quan tâm dấu zero.

Nếu cần phân biệt các mẫu bit NaN, `Double.doubleToRawLongBits` giữ khác biệt mà phép chuyển đổi có thể quan sát được. Tuy nhiên, không được suy ra rằng phép tính với NaN sẽ bảo toàn mọi thông tin payload trên mọi nền tảng. Bài toán cần tái lập chính xác các mẫu bit đặc biệt phải có chính sách riêng. [Double.doubleToLongBits](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html#doubleToLongBits(double)), [Double.doubleToRawLongBits](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html#doubleToRawLongBits(double)).

### So sánh gần đúng theo yêu cầu của miền bài toán

Nếu mục tiêu là sai số nghiệp vụ hoặc sai số số học, có thể dùng sai số tuyệt đối, sai số tương đối hoặc khoảng cách theo ulp, tùy miền dữ liệu. ULP là đơn vị liên quan khoảng cách giữa các giá trị dấu phẩy động lân cận ở độ lớn đang xét. Đừng dùng một ngưỡng tùy ý cho mọi đại lượng.

Ví dụ về **ý tưởng** kiểm tra kết quả hữu hạn:

```text
|actual - expected| <= absoluteTolerance
hoặc
|actual - expected| <= relativeTolerance * max(|actual|, |expected|)
```

Đây là công thức định hướng, chưa phải mã kiểm thử tổng quát. Khi hiện thực, phải kiểm soát tràn ở phép trừ/nhân, xử lý NaN/vô cực, quy định đơn vị và chọn ngưỡng dựa trên yêu cầu. Gần zero, sai số tuyệt đối thường có vai trò rõ hơn; với đại lượng lớn, sai số tương đối có thể phù hợp hơn.

Hai kết quả đều nằm trong dung sai không có nghĩa chúng giống từng bit. Ngược lại, hai kết quả giống từng bit không chứng minh chúng gần đáp án toán học đúng. Cũng không nên mặc định dùng `StrictMath` làm “đáp án chính xác tuyệt đối” để chấm mọi thuật toán khác.

## 7. Áp dụng vào một quy trình cần tái lập

Giả sử một mô phỏng cần đối chiếu kết quả giữa máy phát triển và CI:

1. Chốt dữ liệu kiểm thử bằng tệp có phiên bản; không lấy dữ liệu thay đổi theo thời điểm chạy.
2. Chốt miền hợp lệ và chính sách với NaN, vô cực, dấu zero.
3. Dùng `StrictMath` cho các hàm có hợp đồng thuật toán tái lập cần thiết.
4. Chốt thứ tự tính; nếu chạy song song, chốt cấu trúc gộp thay vì chỉ chốt số luồng.
5. Lưu cả thông tin thuật toán, đầu vào và môi trường để có thể điều tra sai khác.
6. Chạy cùng bộ dữ liệu trên các môi trường đích; kiểm tra kết quả theo tiêu chí đã công bố.

Nếu đổi thuật toán tổng, chuyển sang FMA hoặc đổi cách chia nhóm, hãy coi đó là thay đổi có thể ảnh hưởng kết quả. Có thể cần cập nhật kết quả chuẩn sau khi đánh giá chất lượng số học; đừng sửa giá trị kỳ vọng chỉ để kiểm thử chuyển xanh.

## 8. Lỗi thường gặp và bài tập tự kiểm chứng

| Nhận định dễ nhầm | Cách kiểm tra lại |
|---|---|
| Thêm strictfp sẽ làm Math.sin tái lập trên Java 17+ | Tách quy tắc biểu thức khỏi hợp đồng hàm thư viện; strictfp không còn đổi cách đánh giá |
| StrictMath loại bỏ mọi sai số | double vẫn hữu hạn; xem ví dụ thứ tự cộng |
| Math luôn khác StrictMath | Không có bảo đảm khác nhau; sqrt có hợp đồng làm tròn đúng |
| StrictMath luôn chậm hơn | Đo đúng hàm, JVM và tải trước khi kết luận |
| Cùng tập số thì cộng thế nào cũng ra cùng tổng | Kiểm tra thứ tự và cây gộp kết quả |
| Hai chuỗi số thập phân in ra giống nhau là đủ | Xác định độ chính xác hiển thị và tiêu chí so sánh giá trị |
| strict trong tên lớp nghĩa là toàn bộ chương trình xác định | Kiểm tra cả đầu vào, số ngẫu nhiên, thứ tự xử lý và dữ liệu dùng chung |

Thực hành:

1. Đổi thứ tự phần tử của `input` trong ví dụ và so sánh `score` bằng dạng hex. Không yêu cầu mọi phép hoán vị đều phải tạo khác biệt; điều cần kiểm tra là chương trình có còn cam kết cùng thứ tự tính hay không.
2. Thay `StrictMath.sin` bằng `Math.sin` và chạy trên các môi trường đang dùng. Ghi lại kết quả quan sát được, rồi đối chiếu với hợp đồng API; phân biệt quan sát thực nghiệm với bảo đảm của đặc tả.
3. Thêm `Double.NaN` vào đầu vào và giải thích vì sao hàm `score` từ chối dữ liệu đó.
4. Trước khi lưu kết quả cho một ứng dụng cụ thể, viết một câu rõ ràng: “chấp nhận sai số bao nhiêu” hoặc “so sánh biểu diễn theo quy tắc nào”, kèm miền dữ liệu. Câu này quyết định cách kiểm thử và mức tái lập thực sự cần thiết.
