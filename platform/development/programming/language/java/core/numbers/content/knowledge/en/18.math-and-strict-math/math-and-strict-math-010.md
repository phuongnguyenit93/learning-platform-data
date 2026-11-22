# Phân biệt yêu cầu tái lập của Math và StrictMath trong Java

Java có hai lớp tiện ích toán học trong `java.lang`: `Math` và `StrictMath`. Cả hai cung cấp nhiều hàm tương ứng như `sin`, `cos`, `log`, `exp`, `pow`, `sqrt` và `hypot`. Nhưng khi yêu cầu **tái lập kết quả giữa các nền tảng** (*reproducibility*), không thể kết luận rằng hai lớp có hợp đồng giống hệt nhau.

**Điểm khác biệt chính:** Với một số hàm số thực, `Math` cho phép những triển khai khác nhau cho ra các giá trị `double` *khác nhau ở bit thấp* dù vẫn đạt giới hạn sai số và tính chất được đặc tả. Đối với **nhóm hàm `StrictMath` được ràng buộc với thuật toán `fdlibm`**, Java quy định cách tính tham chiếu để giúp tạo **cùng kết quả bit-for-bit cho cùng đầu vào** trên các triển khai Java phù hợp.

Đây là chủ đề thuộc **Math và StrictMath** của Java Core. Bài học tách bạch “cùng công thức”, “đủ gần về số học”, “cùng bit”, “cùng kết quả toàn chương trình”, giải thích bối cảnh Java 17+ và hướng dẫn cách chọn API phù hợp.

## 1. Ba mức độ “tái lập” cần phân biệt

| Mức yêu cầu | Ý nghĩa | Cách đánh giá |
| --- | --- | --- |
| Tính đúng gần đúng (*numerical accuracy*) | Giá trị tính được ở trong giới hạn sai số cho phép của hàm | So sánh với chuẩn toán học và giới hạn `ulp`/dung sai |
| Tái lập bit một hàm (*bitwise function reproducibility*) | Cùng **đối số có cùng bit** thì kết quả trả về có cùng biểu diễn bit theo đặc tả | So sánh `Double.doubleToRawLongBits` hoặc `doubleToLongBits` theo mục tiêu |
| Tái lập toàn chương trình | Cùng dữ liệu và hợp đồng thực thi thì toàn bộ phép tính/chuỗi đầu ra nhất quán | Phải kiểm soát thuật toán, thứ tự phép toán, dữ liệu, luồng, định dạng và phiên bản/phụ thuộc |

Một phương thức **chính xác trong 1 ulp** vẫn có thể có **hai đáp án bit khác nhau** nếu đặc tả cho phép hai giá trị kề nhau quanh kết quả toán học. Vì vậy “chính xác cao” không tự suy ra “tái lập từng bit”.

Ngược lại, kết quả lặp lại giống hệt bit giữa các lần chạy không tự chứng minh nó đúng về mặt nghiệp vụ. Một thuật toán có thể nhất quán mà vẫn dùng công thức không ổn định, sai kiểu dữ liệu hoặc không phản ánh yêu cầu thực tế.

## 2. `Math`: ưu tiên tính đúng theo đặc tả, cho phép tối ưu triển khai

Theo tài liệu API, một số hàm tương ứng trong `Math` **không bắt buộc mọi triển khai cho kết quả bit-for-bit như nhau**. Điều này cho phép JVM tận dụng thư viện nền tảng hoặc lệnh CPU hiệu quả hơn, miễn kết quả vẫn tuân thủ hợp đồng của từng hàm.

Ví dụ `Math.sin(double)` yêu cầu kết quả có sai số trong **1 ulp** và thỏa tính *semi-monotonic*. Các hàm khác có thể có giới hạn 1 ulp, 2 ulp, hoặc đòi **làm tròn đúng** tùy phương thức; không được áp một con số cho mọi thành viên của `Math`.

Khái niệm `ulp` (*unit in the last place*) nói về khoảng cách giữa các giá trị dấu phẩy động có thể biểu diễn gần một giá trị được xét. Chẳng hạn:

~~~java
System.out.println(Math.ulp(1.0));
// 2.220446049250313E-16
~~~

Khoảng cách này phụ thuộc độ lớn của số; không tương đương một epsilon thập phân cố định cho toàn bộ miền `double`.

**Cần hiểu đúng “được phép khác”:**

- Không có nghĩa `Math` luôn khác `StrictMath`.
- Không có nghĩa một JVM luôn chọn hàm xấp xỉ “kém chính xác” hơn.
- Không có nghĩa `Math.sin(x)` được trả giá trị bất kỳ; vẫn có yêu cầu độ chính xác và tính chất của hàm.
- Không bảo đảm sử dụng `Math` luôn nhanh hơn `StrictMath`: hiệu năng thực phụ thuộc JDK/JIT/CPU, hàm được gọi và workload.

Nhiều triển khai thực tế có thể gọi trực tiếp `StrictMath` cho một số hàm hoặc tạo kết quả giống nhau tại bộ dữ liệu kiểm thử. **Một thử nghiệm cho ra kết quả bằng nhau trên máy hiện tại không nâng cấp hợp đồng API thành bảo đảm xuyên nền tảng.**

## 3. `StrictMath`: nhóm hàm được xác định bằng `fdlibm`

`StrictMath` được thiết kế để hỗ trợ khả năng di động/tái lập. Java quy định các hàm toán học nhất định sử dụng ngữ nghĩa tương ứng với **`fdlibm` (Freely Distributable Math Library) phiên bản 5.3**, hiểu như thuật toán được chuyển sang Java và thực thi theo quy tắc số học Java.

Theo API Java SE 21, nhóm hàm ràng buộc thuật toán `fdlibm` gồm:

- Lượng giác và nghịch đảo: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`.
- Mũ/logarit: `exp`, `log`, `log10`, `expm1`, `log1p`, `pow`.
- Hyperbolic: `sinh`, `cosh`, `tanh`.
- Các hàm khác trong nhóm: `cbrt`, `hypot`.

Với **cùng bit của đầu vào** và một triển khai tuân thủ đặc tả áp dụng, các hàm này có quy tắc tính toán tham chiếu, nhờ đó thích hợp hơn khi bạn cần kết quả **bit-for-bit ổn định giữa các nền tảng Java**.

**Không nên nói toàn bộ mọi phương thức của `StrictMath` đều sử dụng `fdlibm`**. Những thành viên như `abs`, `min`, `max`, `nextUp`, `copySign`, `sqrt` hoặc các phương thức số nguyên có hợp đồng riêng; một số có tính đúng chính xác/correctly rounded hoặc quy tắc bit rõ ràng mà không cần thuật toán `fdlibm`. Phải đọc tài liệu từng hàm khi yêu cầu tái lập chặt chẽ.

Cũng không nên nói `StrictMath` trả “giá trị toán học chính xác tuyệt đối” cho `sin` hay `log`. Kết quả vẫn là giá trị `double` xấp xỉ. Điều nó bổ sung là **một quy tắc tính toán được chỉ định**, không biến binary64 thành số thực có độ chính xác vô hạn.

## 4. So sánh trực tiếp hai lớp

| Câu hỏi | `Math` | `StrictMath` |
| --- | --- | --- |
| Có các hàm lượng giác/mũ/log tương ứng? | Có | Có |
| Hàm trả số thực được biểu diễn bằng `double`? | Có | Có |
| Phải tuân thủ quy tắc NaN, vô cực, zero có dấu theo từng hàm? | Có | Có |
| Mọi hàm tương ứng bắt buộc cùng bit trên mọi JVM? | **Không**; một số hàm cho phép tự do triển khai trong giới hạn đặc tả | **Nhóm hàm `fdlibm` có thuật toán tham chiếu** để tái lập |
| Có thể cho cùng kết quả bit ở JVM đang dùng? | Có thể | Có thể |
| Luôn chạy nhanh hơn lớp kia? | Không có bảo đảm | Không có bảo đảm |
| Chỉ cần chọn lớp là đủ bảo đảm tái lập *toàn bộ chương trình*? | Không | Không |

Ví dụ:

~~~java
double x = 0.7;
double a = Math.sin(x);
double b = StrictMath.sin(x);
~~~

Trên một số JVM, `a` và `b` có thể bằng nhau ở bit; trên triển khai khác, `Math.sin` có thể trả đáp án trong giới hạn `ulp` của nó nhưng khác bit thấp so với `StrictMath.sin`. **Không nên viết kiểm thử portable buộc `a == b` cho mọi x và mọi JVM** chỉ dựa trên tên hai hàm.

Nếu cần kiểm thử giao thức bitwise dựa trên `sin`, dùng `StrictMath.sin` và cố định các đầu vào (kể cả bit của `double`), không suy luận từ một tập benchmark có kết quả trùng hợp.

## 5. Java 17+ và JEP 306: `strictfp` không đồng nghĩa `StrictMath`

Từ **Java 17**, **JEP 306 — Restore Always-Strict Floating-Point Semantics** đưa ngôn ngữ và JVM về ngữ nghĩa dấu phẩy động luôn nghiêm ngặt (*always-strict*). Các phép toán primitive như cộng, trừ, nhân, chia trên `float`/`double` đều sử dụng ngữ nghĩa dấu phẩy động nghiêm ngặt; từ khóa `strictfp` không còn thay đổi cách đánh giá các biểu thức này trên Java 17+.

Điều này **không xóa khác biệt về hợp đồng thư viện**:

- `strictfp` (keyword) liên quan đến ngữ nghĩa thực thi biểu thức dấu phẩy động của mã Java; trên Java 17+ ngữ nghĩa ấy luôn strict.
- `StrictMath` là một **lớp API** với những hàm có yêu cầu thuật toán `fdlibm` đặc thù.
- `Math` vẫn có một số hàm được phép tối ưu theo nền tảng trong giới hạn sai số cho phép.

Nói cách khác, mã chạy trên Java 17+ **không tự biến lời gọi `Math.sin` thành lời gọi `StrictMath.sin`** chỉ vì phép toán dấu phẩy động đã always-strict. Đừng dùng từ khóa `strictfp` như giải pháp thay thế cho việc chọn đúng API hoặc thiết kế pipeline tái lập.

## 6. “Cùng đầu vào” là cùng *bit*, không chỉ chuỗi trông giống nhau

Kết quả phụ thuộc chính xác vào các bit của đối số. `0.7` trong source Java được làm tròn thành một giá trị binary64. Khi kiểm thử tái lập, nếu một hệ thống nhập chuỗi theo cách khác, ép từ `float` lên `double` hoặc làm tròn trước khi gọi hàm, **bit đầu vào** có thể khác nhau.

~~~java
double fromDouble = 0.7;
double fromFloat = (double) 0.7f;
boolean equalBits = Double.doubleToLongBits(fromDouble)
        == Double.doubleToLongBits(fromFloat); // false
~~~

Mặc dù khi hiển thị với `%.1f` cả hai có thể đều trông là `0.7`, hai giá trị biểu diễn bit khác nhau. `StrictMath.sin` không có trách nhiệm khiến **hai đối số khác bit** tạo cùng kết quả.

Khi cần lưu dữ liệu để tái lập một phép tính, hãy xác định:

1. Đầu vào được lưu như `double` binary64, `float` binary32 hay decimal.
2. Format trao đổi có đảm bảo round-trip hay không, ví dụ `Double.toString` + `Double.parseDouble`.
3. Có chuyển kiểu, thay đổi đơn vị, chuẩn hóa hay làm tròn trước phép tính không.
4. Có trạng thái NaN/vô cực/số 0 có dấu và chính sách xử lý bit đặc biệt không.

`Double.doubleToRawLongBits` giữ raw bit của giá trị để chẩn đoán. `Double.doubleToLongBits` chuẩn hóa các NaN thành một biểu diễn canonical khi cần so sánh số thực theo quy ước Java; lựa chọn API kiểm bit phụ thuộc mục tiêu. Với zero có dấu, cả hai có thể phân biệt `+0.0` và `-0.0`.

## 7. Ví dụ Java 17+ hoàn chỉnh: kết quả cố định và kiểm tra bit

Tạo tệp `ReproducibleMathDemo.java`:

~~~java
public class ReproducibleMathDemo {
    static String bits(double x) {
        return "0x" + Long.toHexString(Double.doubleToRawLongBits(x));
    }

    public static void main(String[] args) {
        double angle = 0.7;
        double a = StrictMath.sin(angle);
        double b = StrictMath.sin(angle);

        System.out.println("strict sin hex = "
                + Double.toHexString(a));
        System.out.println("strict sin bits = " + bits(a));
        System.out.println("repeat strict identical = "
                + (Double.doubleToLongBits(a)
                == Double.doubleToLongBits(b)));
        System.out.println("strict sin(-0) bits = "
                + bits(StrictMath.sin(-0.0)));
        System.out.println("strict log(1) = "
                + StrictMath.log(1.0));
        System.out.println("strict log(-1) is NaN = "
                + Double.isNaN(StrictMath.log(-1.0)));
        System.out.println("strict sqrt(4) = "
                + StrictMath.sqrt(4.0));
        System.out.println("math sqrt(4) = "
                + Math.sqrt(4.0));
        System.out.println("ulp(1) = " + Math.ulp(1.0));
        System.out.println("nextUp(1) = " + StrictMath.nextUp(1.0));

        double x = 1.0e16, y = -1.0e16, z = 1.0;
        System.out.println("left grouped = " + ((x + y) + z));
        System.out.println("right grouped = " + (x + (y + z)));

        System.out.println("strict abs(minInt) = "
                + StrictMath.abs(Integer.MIN_VALUE));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addExact overflow caught");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ReproducibleMathDemo.java
java ReproducibleMathDemo
~~~

Stdout đã xác minh với Java:

~~~text
strict sin hex = 0x1.49d6e694619b8p-1
strict sin bits = 0x3fe49d6e694619b8
repeat strict identical = true
strict sin(-0) bits = 0x8000000000000000
strict log(1) = 0.0
strict log(-1) is NaN = true
strict sqrt(4) = 2.0
math sqrt(4) = 2.0
ulp(1) = 2.220446049250313E-16
nextUp(1) = 1.0000000000000002
left grouped = 1.0
right grouped = 0.0
strict abs(minInt) = -2147483648
addExact overflow caught
~~~

Đọc kết quả theo đúng mục tiêu:

- Hai dòng `strict sin` cho phép quan sát cả biểu diễn hexadecimal của `double` và **bit thô** của kết quả `StrictMath.sin(0.7)` theo ngữ nghĩa `fdlibm`.
- `repeat strict identical = true` xác nhận hai lời gọi cùng đầu vào trong chương trình cho cùng bit; **chỉ test một máy không chứng minh mọi triển khai đều như vậy**, bảo đảm portable đến từ đặc tả `StrictMath`.
- `sin(-0.0)` giữ dấu âm của 0, thể hiện ở bit dấu của binary64.
- `log(-1.0)` trả NaN và `sqrt(4.0)` trả 2.0 theo hợp đồng hàm; hai kết quả dễ quan sát không có nghĩa mọi đầu vào `Math` và `StrictMath` sẽ cho cùng bit.
- Hai dòng `left grouped` và `right grouped` minh họa **thứ tự phép cộng khác nhau có thể cho kết quả khác nhau**, dù cùng dùng phép toán Java 17+ strict.
- `abs(Integer.MIN_VALUE)` vẫn ra `Integer.MIN_VALUE` vì miền `int` không chứa giá trị dương tương ứng. `addExact` ném khi cộng tràn miền, không liên quan “tái lập” của hàm lượng giác.

**Lưu ý:** các hàm được bảo đảm tái lập là những hàm mà hợp đồng API ràng buộc như `fdlibm`. Không lấy vài dòng output đơn giản của các hàm khác làm bằng chứng rằng toàn bộ API đều được quy định bằng cùng thuật toán.

## 8. Thứ tự phép tính vẫn có thể phá tái lập toàn chương trình

Ngay cả khi **từng lời gọi `StrictMath.sin`** cho cùng bit với cùng đầu vào, kết quả chương trình còn phụ thuộc cách các phép tính kết hợp.

Ví dụ:

~~~java
double x = 1.0e16;
double y = -1.0e16;
double z = 1.0;

double left = (x + y) + z;  // 1.0
double right = x + (y + z); // 0.0
~~~

Phép cộng dấu phẩy động **không có tính kết hợp** theo cách số thực toán học lý tưởng: thay ngoặc đã đổi chỗ làm tròn. Java 17 always-strict quy định cách tính biểu thức, nhưng **không khiến hai biểu thức có thứ tự khác nhau tương đương**.

Đối với pipeline song song, kết quả `reduce`/`sum` có thể chịu ảnh hưởng nếu thứ tự cộng thay đổi do chia partition hoặc thứ tự duyệt. Với thuật toán cần tái lập bitwise, cần kiểm soát thứ tự giảm, cách phân nhóm và chiến lược tích lũy, hoặc sử dụng một thuật toán tổng ổn định phù hợp.

Tương tự, thay `a * b + c` bằng `Math.fma(a,b,c)` thay đổi quy tắc làm tròn: `fma` thực hiện nhân rồi cộng với một lần làm tròn ở kết quả cuối theo đặc tả, có thể khác việc làm hai phép riêng. Đừng coi việc refactor sang một công thức “tương đương toán học” là bảo đảm **cùng bit**.

**Yêu cầu tái lập toàn bộ** còn bao gồm nguồn random, seed, dữ liệu sắp xếp, xử lý null/NaN, chuyển đổi kiểu, locale khi xuất chuỗi, phụ thuộc phiên bản và khả năng thay đổi thuật toán.

## 9. NaN, ±Infinity, ±0 và phép kiểm bit

Các giá trị dấu phẩy động đặc biệt làm nổi bật sự khác nhau giữa so sánh toán học và so sánh bit:

~~~java
double negativeZero = -0.0;

boolean numericallyEqual = (negativeZero == 0.0); // true
boolean sameBits = Double.doubleToRawLongBits(negativeZero)
        == Double.doubleToRawLongBits(+0.0);      // false

boolean nanEquality = (Double.NaN == Double.NaN); // false
boolean nanDetected = Double.isNaN(Double.NaN);  // true
~~~

Khi đối số âm 0, một số hàm giữ dấu theo hợp đồng, ví dụ `StrictMath.sin(-0.0)` trả âm 0. Với phép xử lý NaN, raw payload có thể khác, và `Double.doubleToLongBits` chuẩn hóa NaN; cần quyết định “bitwise identity” có bao gồm payload NaN hay không.

Kết quả `StrictMath` cũng có thể là NaN hoặc vô cực theo miền của hàm; strict reproducibility **không bảo đảm mọi phép tính cho số hữu hạn**. Dữ liệu không hữu hạn cần được validation theo ngữ nghĩa ứng dụng. Có thể dùng `Double.isFinite` khi ràng buộc cần số hữu hạn.

Nếu kết quả được serialize sang JSON hoặc hệ thống khác không hỗ trợ NaN/vô cực ở dạng số thông thường, phải chọn quy ước truyền tải riêng. Đây là vấn đề hợp đồng dữ liệu, không được `StrictMath` tự giải quyết.

## 10. Khi nào nên chọn `Math`, khi nào chọn `StrictMath`?

**Ưu tiên `Math`** khi cần hàm toán học đúng theo yêu cầu API, chú trọng hiệu năng/thông lượng nhưng **không đòi bit-for-bit reproducibility** với nhóm hàm lượng giác/mũ/log giữa các nền tảng. Tính toán UI, đồ họa, nhiều bài toán mô phỏng hay thống kê chấp nhận sai số được xác định thường phù hợp, sau khi đánh giá yêu cầu riêng.

**Cân nhắc `StrictMath`** khi bài toán cần so khớp bitwise đối với những hàm được ràng buộc theo `fdlibm`: tái lập kết quả trong kiểm thử liên nền tảng, trao đổi kết quả số học giữa các JVM tuân thủ cùng đặc tả, hoặc một thành phần thuật toán mà bit kết quả đóng vai trò dữ liệu đầu ra.

Tuy vậy, không tự đồng nhất `StrictMath` với:

- **“Luôn chậm hơn.”** Tốc độ phụ thuộc hàm và triển khai; hãy benchmark workload thực tế.
- **“Chính xác tuyệt đối hơn `Math`.”** Nó đảm bảo thuật toán tham chiếu cho một tập hàm, không biến `double` thành phép toán vô hạn precision.
- **“Tất cả method StrictMath đều fdlibm.”** Chỉ có tập hàm được liệt kê/định nghĩa trong tài liệu là ràng buộc tương ứng.
- **“Cùng source code ở hai máy chắc chắn cho toàn bộ ứng dụng cùng bit.”** Dữ liệu, thứ tự phép tính, thuật toán song song và các thành phần khác vẫn có thể khác.

Một lựa chọn hợp lý là dùng `Math` cho nhu cầu thông thường, xác định **điểm nào thực sự có yêu cầu tái lập chặt chẽ**, và chọn `StrictMath` cho các lời gọi phù hợp tại những điểm đó. Việc chọn phải dựa trên hợp đồng thực tế của hàm, không trên tên “Strict” một cách tuyệt đối.

## 11. Kiểm thử và chẩn đoán khi cần bit-for-bit

### Kiểm thử hai giá trị số thực

~~~java
static boolean sameCanonicalBits(double a, double b) {
    return Double.doubleToLongBits(a) == Double.doubleToLongBits(b);
}
~~~

Đây là **phương thức minh họa**, cần đặt trong class; nó dùng biểu diễn **canonical** với NaN. Nếu yêu cầu phân biệt payload, sử dụng `Double.doubleToRawLongBits`. Nếu chỉ kiểm tra giá trị **gần đúng** theo sai số, bitwise comparison là không phù hợp: hai số cách nhau 1 ulp sẽ bị coi là khác nhau.

### Kiểm thử “đúng gần đủ”

Nếu kết quả không đòi tái lập tuyệt đối mà chỉ cần sai số trong một mức cho phép, hãy xác định tolerance dựa trên miền giá trị, độ lớn và tính chất của hàm. Đối với những hàm `Math` có quy định sai số tính bằng `ulp`, thiết kế kiểm tra phù hợp với hợp đồng từng hàm, không áp một epsilon cố định cho mọi hàm và mọi giá trị.

### Lưu dấu vết kiểm thử tái lập

Nên lưu rõ phiên bản Java/API áp dụng, kiến trúc, bit hoặc hexadecimal của đầu vào/đầu ra, thuật toán và seed nếu có ngẫu nhiên. Nếu kiểm chứng xuyên các môi trường, chạy cùng bộ vector đầu vào và so sánh theo yêu cầu bài toán:

1. **Bitwise:** so sánh hex/bit, xử lý NaN và zero có dấu có chủ đích.
2. **Numerical tolerance:** so sánh theo sai số với NaN/vô cực được xử lý riêng.
3. **Nghiệp vụ:** kiểm tra kết quả được phép/không được phép (ví dụ ngưỡng, đơn vị, mô hình dữ liệu).

Đừng trộn ba kiểu assertion vào một bài test mà không ghi rõ tiêu chí thành công.

## 12. Các sai lầm hay gặp

1. **Nghĩ Java 17 always-strict khiến mọi `Math.sin`, `Math.log` bắt buộc cùng bit trên mọi nền tảng.** Sai: ngữ nghĩa biểu thức primitive và hợp đồng các hàm thư viện là hai tầng khác nhau.
2. **Nghĩ `strictfp` và `StrictMath` là cùng cơ chế.** Sai: một cái là modifier ngôn ngữ, một cái là class API.
3. **Nghĩ tất cả phương thức `StrictMath` được hiện thực trực tiếp bằng `fdlibm`.** Sai: tài liệu xác định danh sách cụ thể.
4. **Coi kết quả `Math.sin(x) == StrictMath.sin(x)` trên một JVM là bằng chứng portable.** Sai: kết quả thực tế trùng không thay thế bảo đảm trong tài liệu.
5. **Cho rằng `StrictMath` luôn chính xác hơn `Math`.** Mục tiêu quan trọng là tái lập thuật toán cho tập hàm tương ứng, không phải lời hứa “vô hạn độ chính xác”.
6. **Áp giới hạn 1 ulp cho mọi hàm của `Math`.** Mỗi method có yêu cầu riêng, có thể 0.5, 1, 2 ulp hoặc chính xác theo bit.
7. **Chỉ kiểm soát một hàm mà quên thứ tự cộng/reduction.** Nhóm phép tính khác nhau có thể dẫn tới kết quả bit khác nhau.
8. **Bỏ qua bit đầu vào, signed zero và NaN.** Hai chuỗi in giống nhau không nhất thiết tạo cùng binary64; hai zero bằng nhau theo `==` nhưng khác bit.
9. **Sửa biểu thức sang `Math.fma`, đổi cách tính hoặc thay cấu trúc pipeline mà không kiểm tra tính tái lập.** Số lần và vị trí làm tròn có thể đổi.
10. **Không đo hiệu năng trước khi khẳng định lớp nào nhanh.** JIT, CPU, thuật toán và phân bố đầu vào quyết định hiệu năng thực.
11. **Dùng `Double.toString`/format ít chữ số để chứng minh bitwise equality.** Một bản in có thể che sai lệch; dùng bit hoặc hex khi cần.
12. **Tái lập bitwise mà quên dữ liệu nghiệp vụ phải hợp lý.** Kết quả ổn định nhưng sai công thức/đơn vị vẫn là lỗi.

## 13. Câu hỏi tự kiểm tra

**1.** Vì sao `Math.sin(x)` có thể khác `StrictMath.sin(x)` ở bit thấp?

**Đáp án:** `Math.sin` có hợp đồng sai số/tính chất cho phép lựa chọn triển khai trong giới hạn; `StrictMath.sin` dùng ngữ nghĩa thuật toán `fdlibm` được chỉ định nhằm tái lập.

**2.** Java 17 always-strict có đồng nghĩa mọi method trong `Math` phải trả cùng bit trên mọi CPU?

**Đáp án:** Không. JEP 306 điều chỉnh ngữ nghĩa biểu thức dấu phẩy động của ngôn ngữ/JVM; không xóa các khoảng tự do triển khai được mô tả trong API `Math`.

**3.** `StrictMath.sin` có chính xác toán học tuyệt đối vì tên “Strict” không?

**Đáp án:** Không. Kết quả vẫn là `double` xấp xỉ; tính nổi bật là tuân theo thuật toán tham chiếu nhằm tái lập giữa nền tảng.

**4.** Vì sao `(1e16 + -1e16) + 1` khác `1e16 + (-1e16 + 1)`?

**Đáp án:** Phép cộng binary64 có thể làm tròn ở từng bước và không có tính kết hợp; hai cách nhóm phép toán cho `1.0` và `0.0`.

**5.** Khi nào dùng `Double.doubleToRawLongBits` thay cho so sánh `==`?

**Đáp án:** Khi tiêu chí là mẫu bit, kể cả phân biệt `-0.0` với `+0.0` và các NaN payload nếu còn được giữ. `==` thể hiện equality số học, không phải đồng nhất bit.

**6.** Một chương trình dùng `StrictMath.log` và `StrictMath.sin` đã đủ để có kết quả toàn bộ tái lập chưa?

**Đáp án:** Chưa. Vẫn cần kiểm soát bit đầu vào, thứ tự tính, các phép chuyển kiểu, dữ liệu đầu ra, ngẫu nhiên, song song và các bộ phận khác của pipeline.

## Tài liệu tham khảo

- [Java SE 21 — StrictMath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StrictMath.html): danh sách phương thức ràng buộc `fdlibm` và quy tắc đặc biệt từng phương thức.
- [Java SE 21 — Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html): độ chính xác tính theo `ulp`, semi-monotonic và quyền lựa chọn triển khai.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): thay đổi ngữ nghĩa strict của Java 17+.
- [Java SE 21 — Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html): `toHexString`, `doubleToRawLongBits`, `doubleToLongBits` và xử lý NaN/zero.
- [Java Language Specification `15.4 và `4.2.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.4): biểu thức dấu phẩy động và quy tắc đánh giá.
