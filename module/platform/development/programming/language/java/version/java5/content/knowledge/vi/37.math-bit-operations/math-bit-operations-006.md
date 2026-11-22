# Lựa chọn Math hoặc StrictMath theo yêu cầu tái lập kết quả

## 1. Xác định “giống nhau” nghĩa là gì trước khi chọn API

Hai hệ thống có thể cùng tính một công thức và in ra cùng vài chữ số, nhưng các bit cuối của giá trị `double` vẫn khác nhau. Khi chọn `Math` hoặc `StrictMath`, cần phân biệt:

- **Đủ chính xác cho bài toán:** sai số nằm trong giới hạn chấp nhận được.
- **Tái lập kết quả số:** cùng đầu vào và cùng quy trình phải tạo lại kết quả đã thống nhất.
- **Tái lập theo bit:** biểu diễn dấu phẩy động phải khớp theo chính sách so sánh bit đã định nghĩa.

`Math` cho phép một số hàm có triển khai được tối ưu theo nền tảng, miễn tuân theo hợp đồng độ chính xác và hành vi của hàm. Vì vậy, không phải mọi hàm `Math` đều cam kết cùng kết quả từng bit trên tất cả triển khai.

`StrictMath` quy định chặt hơn ngữ nghĩa của một nhóm hàm số học, giúp tái lập kết quả giữa các nền tảng. Trong Java SE 21, những hàm như `sin`, `cos`, `exp`, `log`, `log10`, `cbrt`, `pow`, `hypot`, `expm1`, `log1p` thuộc nhóm có ngữ nghĩa được gắn với các thuật toán fdlibm quy định trong tài liệu lớp.

Điều cần chọn là **hợp đồng phù hợp**, không phải giả định một lớp luôn “chính xác hơn” lớp còn lại.

## 2. Những điểm giống và khác cần biết

| Tiêu chí | Math | StrictMath |
| --- | --- | --- |
| Kiểu dữ liệu thường gặp | `double`/`float` và các kiểu nguyên theo từng phương thức | Tương tự |
| Phải tuân theo hành vi API | Có | Có |
| Một số hàm được phép dùng tối ưu theo nền tảng với kết quả bit thấp khác nhau | Có, trong giới hạn hợp đồng | Nhóm hàm có ngữ nghĩa thuật toán quy định chặt phải giữ ngữ nghĩa đó |
| Phù hợp khi cần kết quả hàm ổn định theo hợp đồng giữa nền tảng | Cần xem từng hàm | Thường là lựa chọn cho nhóm hàm được quy định |
| Luôn nhanh hơn hoặc luôn chậm hơn | Không thể kết luận chung | Không thể kết luận chung |
| Tự bảo đảm toàn bộ chương trình có tính xác định | Không | Không |

Một triển khai `Math` có thể gọi hàm tương ứng của `StrictMath`; ở nhiều đầu vào, kết quả của hai lớp có thể giống từng bit. Việc quan sát thấy khác nhau không phải điều kiện cần để hiểu sự khác nhau về hợp đồng.

Ngược lại, một mẫu chạy mà `Math.sin(x)` và `StrictMath.sin(x)` khớp bit không chứng minh chúng sẽ khớp ở mọi đầu vào và mọi nền tảng.

Không phải mọi phương thức của hai lớp đều có sự khác biệt thực tế này. Ví dụ `sqrt` có yêu cầu trả căn bậc hai được làm tròn đúng theo hợp đồng của từng lớp; nhiều phép toán nguyên hoặc phép chọn giá trị cũng có kết quả được xác định rõ. Hãy đọc phương thức cụ thể thay vì suy từ tên lớp cho toàn bộ API.

## 3. Khi nào chọn Math?

`Math` phù hợp khi bài toán chấp nhận kết quả trong giới hạn sai số đã xác định và không yêu cầu mọi bit cuối của một số hàm phải giống giữa các nền tảng.

Ví dụ: tính vị trí đồ họa, xử lý tín hiệu có ngưỡng sai số được kiểm chứng, hoặc tính toán số thông thường mà hợp đồng chỉ xét độ chính xác đầu ra. Điều đó không có nghĩa là bỏ qua sai số; vẫn phải chọn công thức ổn định và xác nhận ngưỡng phù hợp.

Các tối ưu của `Math` có thể có lợi cho hiệu năng, nhưng mức chênh phụ thuộc hàm, JDK, phần cứng, dữ liệu và cách gọi. Nếu hiệu năng là điều kiện quyết định, đo đúng luồng tính toán cần dùng. Không chọn theo một con số tốc độ được suy đoán từ tên lớp.

Khi kiểm chứng theo sai số, cần xác định giới hạn tuyệt đối/tương đối hoặc theo ulp phù hợp với bài toán, đồng thời xử lý `NaN`, vô cực và số 0 có dấu riêng nếu chúng thuộc miền dữ liệu. Không chọn một epsilon tùy ý rồi coi nó đúng cho mọi giá trị.

## 4. Khi nào chọn StrictMath?

`StrictMath` hữu ích khi yêu cầu tái lập kết quả của các hàm được quy định là một phần của hợp đồng, chẳng hạn:

- Chạy lại một mô phỏng số để đối chiếu với kết quả đã lưu.
- So sánh các bước tính trên nhiều máy bằng biểu diễn dấu phẩy động đã chuẩn hóa.
- Tạo bộ dữ liệu tham chiếu cần ổn định theo quy trình đã chốt.
- Thuật toán mà một khác biệt rất nhỏ có thể đổi nhánh quyết định ở bước tiếp theo.

Cần dùng nhất quán ở những lời gọi có ảnh hưởng đến hợp đồng đó. Nếu phần quan trọng của chuỗi vẫn gọi một hàm `Math` có quyền thay đổi bit thấp theo nền tảng, thay riêng lời gọi cuối sang `StrictMath` chưa giải quyết được cả chuỗi.

`StrictMath` vẫn tính bằng dấu phẩy động hữu hạn. Nó không trả số thực chính xác tùy ý, không thay thế chính sách thập phân của `BigDecimal`, và không sửa một công thức bị triệt tiêu hoặc tràn số.

Ví dụ `StrictMath.exp(x) - 1` vẫn là hai bước; nếu x rất nhỏ, nên chọn công thức chuyên biệt `StrictMath.expm1(x)`. Tính tái lập và tính ổn định số là hai yêu cầu cần được giải quyết đồng thời.

## 5. Java hiện đại: strictfp không chọn StrictMath thay bạn

Trong Java 17 trở lên, các biểu thức dấu phẩy động luôn được đánh giá theo ngữ nghĩa nghiêm ngặt của ngôn ngữ. Không cần thêm `strictfp` để bật chế độ đó trong mã hiện đại.

Điều này áp dụng cho các phép toán và biểu thức do ngôn ngữ quy định; nó không đổi hợp đồng một hàm thư viện `Math.sin` thành hợp đồng của `StrictMath.sin`.

Vì vậy, cách làm hiện hành là:

- Giữ công thức và thứ tự phép toán rõ ràng.
- Chọn `Math` hoặc `StrictMath` tại các lời gọi dựa trên yêu cầu.
- Đọc tài liệu đúng phiên bản Java đang dùng và kiểm chứng khi nâng cấp môi trường.

Không lấy một hướng dẫn cũ yêu cầu thêm `strictfp` làm giải pháp cho sự khác biệt giữa hai lớp.

## 6. Chương trình minh họa đầy đủ

Lưu thành `MathChoiceDemo.java`. Chương trình dùng cú pháp và API có trên Java 17 trở lên.

```java
public class MathChoiceDemo {
    private static double kernel(double x, boolean reproducible) {
        if (reproducible) {
            return StrictMath.sin(x) + StrictMath.log1p(x);
        }
        return Math.sin(x) + Math.log1p(x);
    }

    public static void main(String[] args) {
        double x = 0x1.0p-3;
        double mathResult = kernel(x, false);
        double strictResult = kernel(x, true);

        System.out.println("input = " + Double.toHexString(x));
        System.out.println("Math result = " + Double.toHexString(mathResult));
        System.out.println("StrictMath result = " + Double.toHexString(strictResult));
        System.out.println("same bits here = "
                + (Double.doubleToLongBits(mathResult)
                == Double.doubleToLongBits(strictResult)));

        double positiveZero = 0.0;
        double negativeZero = -0.0;
        System.out.println("zeros numerically equal = "
                + (positiveZero == negativeZero));
        System.out.println("zero bits equal = "
                + (Double.doubleToLongBits(positiveZero)
                == Double.doubleToLongBits(negativeZero)));

        double a = 1e16;
        double b = -1e16;
        double c = 1.0;
        System.out.println("left sum = " + ((a + b) + c));
        System.out.println("right sum = " + (a + (b + c)));

        double invalid = StrictMath.log(-1.0);
        System.out.println("invalid is NaN = " + Double.isNaN(invalid));
    }
}
```

Lệnh:

```shell
javac --release 17 -encoding UTF-8 MathChoiceDemo.java
java MathChoiceDemo
```

Một kết quả đã kiểm chứng trên môi trường chạy ví dụ:

```text
input = 0x1.0p-3
Math result = 0x1.f08db2e58f08ep-3
StrictMath result = 0x1.f08db2e58f08ep-3
same bits here = true
zeros numerically equal = true
zero bits equal = false
left sum = 1.0
right sum = 0.0
invalid is NaN = true
```

`0x1.0p-3` là literal dấu phẩy động hệ 16, biểu diễn chính xác `1 × 2^-3 = 0.125`. `Double.toHexString` giúp quan sát giá trị ở dạng tương ứng với biểu diễn nhị phân mà không chỉ nhìn vài chữ số thập phân.

Hai dòng kết quả của `Math`/`StrictMath` giống nhau trong lần chạy này. Không cần cố tìm một đầu vào gây khác biệt để dùng `StrictMath`; nhu cầu bắt nguồn từ hợp đồng tái lập. Giá trị phía `Math` có thể khác ở môi trường khác trong phạm vi hợp đồng của các hàm được gọi.

### Vì sao kiểm tra bit khác kiểm tra ==?

`+0.0 == -0.0` là `true`, nhưng hai giá trị có bit dấu khác nhau. `Double.doubleToLongBits` cho phép kiểm tra biểu diễn có phân biệt dấu của số 0.

Phương thức này chuẩn hóa các giá trị `NaN` về một dạng bit chuẩn. Nếu giao thức cần quy tắc riêng cho payload của `NaN`, phải định nghĩa riêng; không mặc định `StrictMath` bảo toàn cùng payload. `Double.isNaN` là phép kiểm tra giá trị đặc biệt rõ ràng.

Không dùng `==` để kiểm tra hai kết quả `NaN` bằng nhau, vì `NaN == NaN` là `false`.

## 7. StrictMath không giải quyết toàn bộ tính tái lập

Hai dòng `left sum`/`right sum` cho thấy:

```text
(1e16 + (-1e16)) + 1 = 1
1e16 + ((-1e16) + 1) = 0
```

Ở biểu thức thứ hai, số 1 quá nhỏ để được giữ lại khi cộng vào `-1e16` bằng `double`. Không có lời gọi `sin` hoặc `log` nào trong hai biểu thức, nên đổi lớp thư viện không làm chúng bằng nhau.

Một quy trình cần tái lập còn phải kiểm soát:

| Thành phần | Vì sao quan trọng |
| --- | --- |
| Đầu vào | Cùng chuỗi hiển thị ngắn chưa chắc cùng giá trị nhị phân ban đầu |
| Thứ tự cộng/tổng hợp | Dấu phẩy động không có tính kết hợp như số thực |
| Chạy song song | Cách gom các phần tổng có thể thay đổi thứ tự tính |
| Nguồn ngẫu nhiên | Chọn `StrictMath` không cố định hạt giống hoặc thứ tự lấy mẫu |
| Dữ liệu thời gian/trạng thái ngoài | Hàm toán học không loại bỏ sự thay đổi của đầu vào |
| Chính sách giá trị đặc biệt | Cần thống nhất xử lý `NaN`, vô cực và số 0 có dấu |
| Phiên bản và cấu hình môi trường | Cần lưu đủ thông tin để kiểm tra lại hợp đồng và phát hiện thay đổi khi nâng cấp |

Đặc biệt, `StrictMath.random()` không phải lời hứa “mỗi lần chạy tạo cùng chuỗi”. Nếu cần nguồn ngẫu nhiên tái lập, phải chọn và cấu hình nguồn sinh cùng với cách tiêu thụ mẫu như một phần riêng của thuật toán.

## 8. Quy trình lựa chọn ngắn gọn

1. Ghi rõ yêu cầu đầu ra: sai số cho phép hay khớp biểu diễn theo bit.
2. Xác định các hàm thực sự ảnh hưởng kết quả; đọc hợp đồng từng hàm.
3. Với nhu cầu tái lập chặt cho nhóm hàm được quy định, dùng `StrictMath` và giữ công thức, đầu vào, thứ tự tổng hợp ổn định.
4. Kiểm chứng trên các môi trường hỗ trợ bằng đầu vào và kết quả tham chiếu phù hợp. Chỉ một lần chạy trên một máy chưa chứng minh tính tái lập liên nền tảng.
5. Nếu có yêu cầu hiệu năng, đo sau khi đã thống nhất hợp đồng đúng/sai; không đổi API làm mất hợp đồng chỉ vì giả định nhanh hơn.

Bộ dữ liệu kiểm chứng nên có đầu vào bình thường, gần ranh giới quyết định của thuật toán, số rất nhỏ/lớn và các giá trị đặc biệt được phép. Nếu cần so bit, lưu dạng không làm mất thông tin thay vì một chuỗi đã làm tròn để hiển thị.

## 9. Tự kiểm tra

- Nếu `Math` và `StrictMath` khớp bit cho 100 mẫu trên một máy, có thể suy rằng hai lớp luôn tương đương không?
- Dùng `StrictMath.sin` có khiến phép cộng song song luôn ra cùng tổng không?
- `strictfp` có đổi `Math.log` thành `StrictMath.log` không?
- `StrictMath` có đồng nghĩa với độ chính xác tùy ý không?

Cả bốn câu trả lời đều là không. Phải phân biệt bằng chứng trên mẫu, hợp đồng hàm, thứ tự thuật toán và độ chính xác của kiểu dữ liệu.

Tham khảo: [Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html), [StrictMath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StrictMath.html) và [JLS 21, biểu thức dấu phẩy động](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.4).
