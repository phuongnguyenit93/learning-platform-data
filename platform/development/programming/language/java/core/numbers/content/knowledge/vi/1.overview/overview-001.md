# Số trong Java là gì và những bài toán cần biểu diễn?

## 1. Số trong chương trình là gì?

Trong toán học, số nguyên và số thực là những khái niệm có miền giá trị rất rộng. Trong Java, một **giá trị số** được biểu diễn bằng một kiểu dữ liệu có giới hạn xác định: số bit, miền giá trị, độ chính xác và phép toán được hỗ trợ. Vì bộ nhớ hữu hạn, không một kiểu nguyên thủy nào biểu diễn chính xác mọi số toán học.

Hãy nhìn vào những giá trị đều gồm chữ số nhưng khác ý nghĩa:

- `27` học viên: một **số lượng nguyên**, cần đếm, cộng và so sánh.
- `36.5` °C: một **đại lượng đo**, thường có phần thập phân và sai số.
- `19.90` USD: một **giá tiền**, cần chính sách chính xác thập phân và làm tròn.
- `00123`: có thể là **mã khách hàng**, phải giữ nguyên số 0 đầu, không cần phép cộng.
- `20261027`: có thể là cách viết ngày, không thích hợp cho phép toán số học tùy tiện.

Vì vậy, trước khi chọn `int` hay `double`, hãy xác định **ý nghĩa dữ liệu**, miền hợp lệ, độ chính xác cần thiết, phép toán, đơn vị và định dạng. Một chuỗi ký tự toàn chữ số chưa chắc nên lưu bằng kiểu số.

## 2. Những kiểu số chủ yếu của Java

Sáu kiểu nguyên thủy thường dùng để tính số học là `byte`, `short`, `int`, `long`, `float` và `double`. Java còn có `char` (một kiểu *integral* theo đặc tả, nhưng ý nghĩa chính là đơn vị mã UTF-16) và `boolean` (không phải kiểu số).

| Kiểu | Kích thước | Miền hoặc đặc điểm | Mục đích |
|---|---:|---|---|
| `byte` | 8 bit | −128 đến 127 | Byte/giao thức, dữ liệu nhị phân |
| `short` | 16 bit | −32.768 đến 32.767 | Tương thích giao thức, định dạng 16 bit |
| `int` | 32 bit | −2.147.483.648 đến 2.147.483.647 | Số lượng, chỉ số, phép toán nguyên thông thường |
| `long` | 64 bit | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | Bộ đếm, số nguyên lớn |
| `float` | 32 bit | Dấu phẩy động nhị phân IEEE 754, khoảng 6–9 chữ số thập phân có nghĩa | Dữ liệu 32 bit có thể chấp nhận sai số |
| `double` | 64 bit | Dấu phẩy động nhị phân IEEE 754, khoảng 15–17 chữ số thập phân có nghĩa | Đo lường và tính toán khoa học thông thường |

Độ chính xác của `float`/`double` là **số chữ số có nghĩa**, không phải luôn chính xác đến một số cố định chữ số sau dấu phẩy. Đây là kiểu **xấp xỉ nhị phân**: các giá trị như `0.1` thập phân thường không được lưu chính xác tuyệt đối. `float` và `double` còn có `NaN`, vô cực và số 0 có dấu.

Hai lớp `java.math` đặc biệt quan trọng:

- **`BigInteger`**: số nguyên chính xác có độ lớn tùy ý trong giới hạn tài nguyên máy; dùng khi `long` cũng không đủ.
- **`BigDecimal`**: số thập phân chính xác theo phần trị nguyên và *scale* (số chữ số theo thang thập phân). Phù hợp cho giá, thuế, phép tính có yêu cầu thập phân và quy tắc làm tròn rõ ràng.

`BigInteger` và `BigDecimal` là **đối tượng**, không phải primitive; dùng các phương thức như `add`, `multiply`, `divide` thay vì toán tử số học thông thường. Các lớp bao `Integer`, `Long`, `Double`... dành cho các tình huống cần đối tượng/generic/collection; cần nhớ có boxing/unboxing và giá trị `null` có thể gây lỗi khi unboxing.

## 3. Ba chiều quan trọng của biểu diễn số

### 3.1. Miền giá trị: số lớn đến đâu?

`int` chứa số nguyên có dấu 32 bit. `long` chứa số nguyên có dấu 64 bit. Một phép cộng, trừ hoặc nhân số nguyên primitive có thể **tràn miền (overflow)**: ví dụ `Integer.MAX_VALUE + 1` thành `Integer.MIN_VALUE`. Java không tự mở rộng kết quả thành `long` và phép cộng nguyên bình thường không tự ném lỗi.

Khi cần phát hiện tràn số, sử dụng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`; chúng ném `ArithmeticException` khi vượt miền. Khi cần miền rộng hơn, chuyển toán hạng sang `long` **trước phép tính**, ví dụ `(long) a * b`; viết `(long) (a * b)` có thể đã quá muộn nếu `a * b` là phép nhân `int` bị tràn. Nếu `long` không đủ, cân nhắc `BigInteger` và đánh giá chi phí bộ nhớ/hiệu năng.

### 3.2. Độ chính xác: số có đúng bằng giá trị mong muốn?

`double` dùng biểu diễn nhị phân có độ chính xác hữu hạn. Giá trị thập phân `0.1` thường chỉ được lưu xấp xỉ, nên `0.1 + 0.2 == 0.3` là `false`. Điều này không làm `double` vô dụng: nó rất phù hợp cho nhiều phép đo và thuật toán số có mô hình sai số được kiểm soát.

Nếu bài toán đòi **đúng theo thập phân**, như cộng tiền `0.10 + 0.20 = 0.30`, hãy dùng `BigDecimal` được tạo từ chuỗi, ví dụ `new BigDecimal("0.10")`. Tránh `new BigDecimal(0.1)`: constructor nhận giá trị nhị phân xấp xỉ sẵn có của literal `double`. `BigDecimal.valueOf(0.1)` thường mang ý nghĩa thập phân mong muốn khi bắt đầu từ literal `double`, nhưng tốt nhất dữ liệu tiền nên đi từ chuỗi hoặc đơn vị nhỏ nhất rõ ràng.

### 3.3. Ngữ nghĩa và đơn vị: đó có thật là đại lượng số học?

Một mã bưu chính `"00123"`, mã nhân viên `"000045"` hay số điện thoại nên dùng `String` để bảo toàn ký tự, số 0 đầu, dấu `+` và định dạng. Ngày tháng dùng `LocalDate`, thời điểm dùng `Instant` và khoảng thời gian dùng `Duration` trong `java.time` khi phù hợp; tránh số nguyên “trần” không rõ là giây, mili giây hay ngày lịch.

Số `5` mét khác `5` giây. Nếu phải nhận số nguyên thủy qua API, đặt tên kèm đơn vị (ví dụ `timeoutMillis`), kiểm tra miền dữ liệu và chuyển đổi ở biên hệ thống.

## 4. Literal và phép toán cơ bản

Các dạng literal thường gặp:

~~~java
int learners = 27;                // hệ thập phân
int oneMillion = 1_000_000;       // _ để dễ đọc
int bits = 0b1010;                // nhị phân: 10
int hex = 0xFF;                   // thập lục phân: 255
long views = 3_000_000_000L;      // hậu tố L cho long
double ratio = 0.125;             // literal thập phân mặc định double
float sample = 0.125f;            // f hoặc F cho float
double distance = 6.02e3;         // 6020.0
~~~

Literal nguyên thập phân không có `L` thường có kiểu `int`, trong khi literal có dấu chấm thập phân thường có kiểu `double` (trừ khi có hậu tố `f`/`F`). Dấu `_` chỉ được đặt giữa các chữ số ở vị trí hợp lệ; `1_.0` là cú pháp sai. Java cũng có literal bát phân với tiền tố `0`: `010` mang giá trị thập phân `8`, dễ gây bất ngờ nếu người đọc tưởng số thập phân.

Một số quy tắc ảnh hưởng trực tiếp đến kết quả:

- `5 / 2` bằng `2` vì hai toán hạng là số nguyên; `5.0 / 2` và `(double) 5 / 2` bằng `2.5`.
- `byte`, `short` và `char` thường được nâng lên `int` trong biểu thức số học (*numeric promotion*).
- `int` có thể mở rộng sang `long` và `double`, nhưng **chuyển sang dấu phẩy động vẫn có thể mất độ chính xác**, nhất là số nguyên lớn.
- Ép kiểu từ `double` sang `int` bỏ phần thập phân đối với giá trị hữu hạn trong miền; ngoài miền hữu hạn kết quả bão hòa ở biên, còn `NaN` thành 0. Không coi cast là bảo đảm không mất thông tin.
- Literal `byte b = 100;` được chấp nhận vì hằng số `int` nằm trong miền `byte`, nhưng không thể tự động chuyển mọi **biến** `int` sang `byte`.

Khi nhập số từ văn bản, có thể dùng `Integer.parseInt("42")`, `Long.parseLong("3000000000")`, `new BigInteger("12345678901234567890")` hoặc `new BigDecimal("19.90")`. Đầu vào không hợp lệ hoặc vượt miền sẽ tạo lỗi như `NumberFormatException`; cần kiểm tra và xử lý ở biên ứng dụng. Với số hiển thị theo khu vực (dấu phẩy/dấu chấm phân cách), định nghĩa `Locale` và công cụ parse/format tương ứng; không tự thay ký tự một cách mơ hồ.

## 5. Bài toán nào chọn kiểu nào?

| Dữ liệu cần biểu diễn | Ví dụ | Lựa chọn khởi đầu | Điều cần xác định |
|---|---|---|---|
| Số lượng thông thường | 27 học viên; chỉ số mảng | `int` | Có âm không, giới hạn lớn nhất? |
| Bộ đếm lớn | 3 tỷ lượt truy cập | `long` | Có cộng dồn gây tràn không? |
| Dữ liệu nhị phân/giao thức | Byte, số nguyên 16 bit | `byte`, `short` | Signedness, cách giải mã, thứ tự byte |
| Giá/tiền/thuế | 19.90 × 3 | `BigDecimal` hoặc `long` lưu đơn vị nhỏ nhất theo hợp đồng | Tiền tệ, scale, làm tròn |
| Phép đo vật lý | 36.5 °C; 2.75 m | `double` | Sai số thiết bị, đơn vị và cách so sánh |
| Số nguyên cực lớn | Số nguyên 100 chữ số | `BigInteger` | Thời gian và bộ nhớ |
| Tỉ lệ, xác suất | 17/23; 12.5% | `double` nếu cho phép xấp xỉ; `BigDecimal` khi thập phân phải chính xác | Miền 0..1, cách làm tròn/hiển thị |
| Định danh | `"00123"`; số điện thoại | `String` | Bảo toàn số 0 đầu và ký tự |
| Thời gian | 90 phút; thời điểm UTC | `Duration`; `Instant` | Đơn vị, lịch, múi giờ |

Bảng là **gợi ý bắt đầu**, chưa thay thế quy tắc nghiệp vụ. Chẳng hạn, hóa đơn không chỉ cần `BigDecimal`: còn phải quy định tiền tệ, thời điểm làm tròn, số chữ số sau dấu phẩy và cách phân bổ phần lẻ. Tỉ lệ trong thống kê có thể cần `double`, trong hệ thống tài chính có thể cần phương pháp chính xác thập phân.

### Một kịch bản bán vé

- `seatCount = 120` là số lượng ghế, `int` thường phù hợp.
- `ticketPrice = 149.90` là giá tiền, biểu diễn bằng `BigDecimal("149.90")`.
- `bookingCode = "000120"` là mã đặt chỗ; dùng `String`, không làm mất `00`.
- `elapsed = 90 phút` là khoảng thời gian; dùng `Duration.ofMinutes(90)`.
- `successRate = 0.973` là tỷ lệ đo thống kê; `double` có thể phù hợp nếu sai số được chấp nhận.

Cùng là chữ số, năm trường hợp đòi năm cách hiểu dữ liệu khác nhau.

## 6. Ví dụ Java 17+ độc lập: biểu diễn đúng từng đại lượng

Tạo tệp `NumberRepresentationDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumberRepresentationDemo {
    public static void main(String[] args) {
        int students = 27;
        long views = 3_000_000_000L;
        double temperature = 36.5;

        BigDecimal ticketPrice = new BigDecimal("19.90");
        BigDecimal ticketCount = new BigDecimal("3");
        BigDecimal total = ticketPrice.multiply(ticketCount);

        BigInteger hugeNumber =
                new BigInteger("123456789012345678901234567890");
        String customerCode = "00123";

        System.out.println("students=" + students);
        System.out.println("views=" + views);
        System.out.println("temperature=" + temperature);
        System.out.println("total=" + total.toPlainString());
        System.out.println("huge+1=" + hugeNumber.add(BigInteger.ONE));
        System.out.println("customerCode=" + customerCode);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac NumberRepresentationDemo.java
java NumberRepresentationDemo
~~~

Đầu ra chính xác:

~~~text
students=27
views=3000000000
temperature=36.5
total=59.70
huge+1=123456789012345678901234567891
customerCode=00123
~~~

`views` vượt miền `int` nên dùng `long`; `temperature` là phép đo cho phép biểu diễn floating-point. `BigDecimal` giữ hai chữ số thập phân trong phép nhân `19.90 × 3 = 59.70`. `BigInteger` cho phép cộng số nguyên lớn hơn miền `long`. `customerCode` bảo toàn số 0 đầu vì nó là mã định danh.

## 7. Ví dụ Java 17+ độc lập: lỗi phổ biến

Tạo tệp `NumberPitfalls.java`:

~~~java
public class NumberPitfalls {
    public static void main(String[] args) {
        int a = 5;
        int b = 2;

        System.out.println("5 / 2 (int) = " + (a / b));
        System.out.println("5 / 2 (double) = " + ((double) a / b));
        System.out.println("int overflow = " + (Integer.MAX_VALUE + 1));
        System.out.println("0.1 + 0.2 == 0.3 = " + ((0.1 + 0.2) == 0.3));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("overflow detected");
        }
    }
}
~~~

~~~bash
javac NumberPitfalls.java
java NumberPitfalls
~~~

Đầu ra:

~~~text
5 / 2 (int) = 2
5 / 2 (double) = 2.5
int overflow = -2147483648
0.1 + 0.2 == 0.3 = false
overflow detected
~~~

Ba hiện tượng **khác nhau**: chia nguyên bỏ phần lẻ, phép cộng nguyên tràn miền, và floating-point chỉ lưu xấp xỉ. Cách xử lý phụ thuộc bài toán: dùng toán hạng floating-point khi muốn thương xấp xỉ, `Math.addExact` hoặc kiểu rộng hơn để xử lý số nguyên, `BigDecimal` khi cần chính xác thập phân. So sánh `double` gần đúng bằng dung sai chỉ phù hợp khi dung sai được xác định theo đơn vị, độ lớn và sai số của bài toán; không chọn một `epsilon` cố định cho mọi trường hợp.

## 8. BigDecimal, phép chia và làm tròn

`BigDecimal` không hỗ trợ toán tử `+`/`*`/`/` như primitive; nó có `add`, `subtract`, `multiply`, `divide`. Phép chia `10 / 3` là thập phân vô hạn: gọi `new BigDecimal("10").divide(new BigDecimal("3"))` sẽ ném `ArithmeticException` vì không thể biểu diễn chính xác bằng số chữ số hữu hạn. Hãy xác định scale và quy tắc làm tròn theo nghiệp vụ.

Ví dụ tạo tệp `DecimalRoundingDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalRoundingDemo {
    public static void main(String[] args) {
        BigDecimal result = new BigDecimal("10")
                .divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        System.out.println(result.toPlainString());
    }
}
~~~

~~~bash
javac DecimalRoundingDemo.java
java DecimalRoundingDemo
~~~

Kết quả:

~~~text
3.33
~~~

Thêm một chi tiết: `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` là `false` vì `equals` xem xét cả *scale*. `compareTo` giữa hai giá trị đó trả 0 vì bằng nhau về mặt số học. Cần chọn cách so sánh phù hợp, đặc biệt khi dùng làm khóa bản đồ hoặc kiểm tra điều kiện nghiệp vụ.

Một hệ thống cũng có thể lưu giá bằng số **đơn vị tiền nhỏ nhất** với `long`, ví dụ giá quy ra xu. Cách này phù hợp nếu đơn vị, khoảng giá trị và quy tắc chuyển đổi được quy định rõ; nó không tự giải quyết các phép chia, tỷ giá hoặc làm tròn tùy ý.

## 9. Checklist chọn cách biểu diễn

1. **Bản chất dữ liệu:** đó là số lượng để tính toán, phép đo, tỷ lệ, số tiền, mã định danh hay ngày/giờ?
2. **Miền giá trị:** nhỏ nhất/lớn nhất, có âm không, có thể tăng không giới hạn không, giá trị trung gian có vượt miền không?
3. **Độ chính xác:** cần số nguyên chính xác, thập phân chính xác hay xấp xỉ floating-point? Có dung sai được đo/thiết kế không?
4. **Phép toán:** có chia, cộng dồn, tính thuế, nhân nhiều lần hoặc so sánh bằng không? Quy tắc overflow/làm tròn là gì?
5. **Đơn vị và định dạng:** mét hay km, giây hay mili giây, VND hay USD, ký tự mã cần bảo toàn, locale nhập/xuất?
6. **Giá trị biên:** thử với 0, số âm, cực đại, số rất lớn, mẫu số bằng 0, dữ liệu sai, sai số tích lũy và các phép toán trung gian.

### Những hiểu lầm thường gặp

- “`double` có 64 bit nên tiền luôn chính xác”: sai, vì đó là dấu phẩy động **nhị phân**.
- “`int` tràn thì Java tự đổi sang `long`”: sai, cần nâng kiểu trước phép tính hoặc kiểm tra overflow.
- “Toàn chữ số thì phải lưu bằng số”: sai, mã định danh và số điện thoại thường là văn bản.
- “`BigDecimal` tự chọn cách làm tròn như kế toán”: sai, phải đặt scale và `RoundingMode` theo hợp đồng.
- “`float` có bảy chữ số **sau dấu phẩy**”: sai, cần hiểu số chữ số **có nghĩa**.
- “Cast là chuyển đổi không mất dữ liệu”: sai, thu hẹp kiểu và chuyển sang floating-point có thể mất thông tin.
- “`BigInteger` vô hạn hoàn toàn”: sai, nó bị giới hạn bởi bộ nhớ và chi phí tính toán của môi trường chạy.

## 10. Câu hỏi tự kiểm tra

1. Bộ đếm có thể tăng đến 4 tỷ: `int` hay `long` phù hợp hơn? Vì sao?
2. Vì sao `"000045"` là mã nhân viên nên giữ dưới dạng `String`?
3. Khi cộng tiền `0.10` và `0.20`, vì sao không mặc nhiên dùng `double`?
4. `5 / 2` và `5.0 / 2` khác nhau thế nào?
5. Một cảm biến có sai số ±0,1 °C: cần làm rõ gì trước khi so sánh hai số đo?
6. Với `int a, b`, tại sao `(long) (a * b)` có thể đã mất thông tin, còn `(long) a * b` có thể tránh được?

**Gợi ý đáp án:** (1) `long` vì 4 tỷ vượt `int`; (2) phải giữ số 0 đầu và mã không dùng phép toán số học; (3) `double` biểu diễn xấp xỉ nhị phân còn `BigDecimal` phù hợp yêu cầu thập phân chính xác; (4) một biểu thức chia nguyên nhận `2`, biểu thức kia nhận `2.5`; (5) đơn vị, độ chính xác cảm biến và dung sai so sánh; (6) phép nhân `int` có thể tràn **trước khi** ép kiểu, nên cần nâng toán hạng trước.

**Ghi nhớ:** Chọn kiểu số trong Java là chọn **mô hình biểu diễn** của đại lượng: ý nghĩa, miền giá trị, độ chính xác, đơn vị, phép toán và quy tắc làm tròn đều ảnh hưởng đến tính đúng đắn của chương trình.