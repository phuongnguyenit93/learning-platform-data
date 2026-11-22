# Tạo Period và đọc chuỗi ISO-8601

## 1. Khoảng theo lịch được biểu diễn như thế nào?

Khi yêu cầu là “gia hạn 3 tháng” hoặc “thêm 1 năm và 10 ngày”, các đơn vị cần giữ lại là **năm, tháng, ngày trên lịch**. `java.time.Period` biểu diễn một lượng thời gian theo lịch ISO bằng ba thành phần đó. Đối tượng không chứa ngày bắt đầu, ngày kết thúc, giờ hay múi giờ.

Ví dụ, `Period.of(1, 2, 3)` có nghĩa là một lượng gồm 1 năm, 2 tháng và 3 ngày. Nó chưa trả lời được “kéo dài chính xác bao nhiêu giây”, vì cần biết lượng này được áp dụng vào ngày nào. Trong ứng dụng, có thể dùng nó để mang cấu hình gia hạn hoặc một khoảng ngày tháng qua nhiều lớp mà vẫn giữ rõ đơn vị.

`Period` là bất biến: sau khi tạo, giá trị của đối tượng không đổi. Các phương thức tạo mới trả về một giá trị có thể lưu và truyền đi an toàn. Những phép cộng vào ngày cụ thể là bước sử dụng tiếp theo; bài này tập trung vào **tạo giá trị, đọc các thành phần và chuyển đổi với chuỗi**.

## 2. Chọn phương thức tạo theo dữ liệu đầu vào

Không dùng `new Period(...)`; lớp cung cấp các phương thức tĩnh để tạo đối tượng.

| Dữ liệu đang có | Cách tạo | Giá trị chuỗi khi in |
|---|---|---|
| Chưa có khoảng nào | `Period.ZERO` | `P0D` |
| 2 năm | `Period.ofYears(2)` | `P2Y` |
| 15 tháng | `Period.ofMonths(15)` | `P15M` |
| 10 ngày | `Period.ofDays(10)` | `P10D` |
| 2 tuần | `Period.ofWeeks(2)` | `P14D` |
| 1 năm, 2 tháng, 3 ngày | `Period.of(1, 2, 3)` | `P1Y2M3D` |
| Chuỗi có đơn vị | `Period.parse("P1Y2M3D")` | `P1Y2M3D` |

`ofWeeks` chuyển ngay số tuần thành số ngày bằng phép nhân 7. `Period` không lưu một trường tuần riêng, vì vậy tạo từ 2 tuần rồi đọc lại chỉ thấy 14 ngày. Tương tự, đọc `P2W` cũng cho ra giá trị có 14 ngày. Khi số tuần quá lớn khiến phép nhân vượt phạm vi số nguyên `int`, `ofWeeks` ném `ArithmeticException`.

Các phương thức `of`, `ofYears`, `ofMonths`, `ofDays` nhận các thành phần kiểu `int`, có thể bằng 0 hoặc âm. Đầu vào như 15 tháng hoặc 40 ngày là hợp lệ: đây là **số lượng**, không phải trường tháng/ngày của một ngày cụ thể.

Ví dụ minh họa trong một phương thức Java:

```java
Period grace = Period.ofDays(10);
Period renewal = Period.ofMonths(15);
Period mixed = Period.of(1, 2, 3);
```

Cần `import java.time.Period;` khi dùng tên ngắn. Đoạn trên chỉ là các câu lệnh minh họa, chương trình chạy đầy đủ nằm ở phần 5.

### Đọc thành phần, không tự đổi đơn vị

Dùng `getYears()`, `getMonths()` và `getDays()` để lấy đúng thành phần đã lưu. Với `Period.of(1, 15, 40)`, ba giá trị lần lượt là `1`, `15`, `40`.

`getMonths()` không trả về tổng tháng, còn `getDays()` không trả về tổng số ngày của toàn bộ khoảng. Nếu cần tổng tháng từ phần năm/tháng, có thể dùng `toTotalMonths()`; phần ngày không được cộng vào kết quả đó. Không có quy tắc chung đổi tháng thành 30 ngày hoặc năm thành 365 ngày.

Việc tạo giá trị và `parse` không tự chuẩn hóa tháng thành năm. Vì thế `Period.ofMonths(15)` có chuỗi `P15M`, không tự thành `P1Y3M`. Nếu chủ động gọi `normalized()`, phần năm/tháng mới được chuẩn hóa; ngày vẫn giữ riêng. Hai đối tượng `Period.ofMonths(15)` và `Period.of(1, 3, 0)` có cấu trúc thành phần khác nhau nên `equals` trả về `false`. Điều này cần lưu ý khi kiểm tra giá trị nhận từ cấu hình.

## 3. Đọc cấu trúc chuỗi PnYnMnD

Chuỗi `P1Y2M3D` có thể đọc từ trái sang phải:

| Phần | Ý nghĩa |
|---|---|
| `P` | Bắt đầu một biểu diễn khoảng |
| `1Y` | 1 năm |
| `2M` | 2 tháng |
| `3D` | 3 ngày |

Thứ tự là năm (`Y`), tháng (`M`), tuần (`W`) rồi ngày (`D`). Có thể bỏ các thành phần không cần dùng, nhưng phải có ít nhất một thành phần. Muốn biểu diễn khoảng bằng 0, viết `P0D` hoặc một thành phần 0 hợp lệ khác; riêng `P` là thiếu dữ liệu.

Các trường hợp thường gặp:

| Chuỗi đầu vào | Kết quả của `Period.parse(...)` khi in | Giải thích |
|---|---|---|
| `P2Y` | `P2Y` | 2 năm |
| `P6M` | `P6M` | 6 tháng |
| `P3W` | `P21D` | Tuần được chuyển thành ngày |
| `P10D` | `P10D` | 10 ngày |
| `P1Y0M3D` | `P1Y3D` | Khi in, thành phần 0 bị lược bỏ |
| `P0M` | `P0D` | Giá trị bằng 0 có biểu diễn chuỗi thống nhất |
| `P15M` | `P15M` | Không tự chuẩn hóa thành năm/tháng |

Đây là cú pháp khoảng, không phải ngày tháng. Chuỗi ngày `2026-10-25` cần kiểu như `LocalDate`, còn `P3M` là một lượng 3 tháng. `Period.parse` không đọc ngôn ngữ tự nhiên như `3 tháng` và không phụ thuộc thiết lập vùng để suy ra đơn vị.

### Chữ M ở phần ngày và chữ M ở phần giờ

Trong chuỗi của `Period`, `M` là **tháng**. Chuỗi có phần giờ như `PT15M` biểu diễn 15 phút và thuộc phạm vi `Duration`, không được `Period.parse` chấp nhận. Không thêm `T`, `H`, `S` hay phần giây vào giá trị dành cho `Period`.

Tương tự, `P1D` và `PT24H` cần được giữ đúng ý nghĩa theo lịch và theo thời lượng. Chúng không phải hai cách viết có thể thay thế tùy ý trong mọi phép tính có múi giờ.

### Những dạng Java chấp nhận rộng hơn cú pháp cơ bản

`Period.parse` chấp nhận chữ hoa hoặc chữ thường, dấu ở đầu và dấu của từng thành phần. Số lượng phải dùng chữ số ASCII và nằm trong giới hạn mà phương thức có thể biểu diễn bằng `int`.

Ví dụ:

```java
Period a = Period.parse("p2m");      // P2M
Period b = Period.parse("-P1Y2M");   // P-1Y-2M
Period c = Period.parse("P-1Y2M");   // P-1Y2M
Period d = Period.parse("P1W2D");    // P9D
```

Ở `-P1Y2M`, dấu âm đầu chuỗi đảo dấu cả phần năm lẫn tháng. Ở `P-1Y2M`, chỉ phần năm âm; phần tháng vẫn dương. Không được diễn giải hai chuỗi này là cùng một giá trị.

Những dạng có dấu riêng từng thành phần hoặc trộn tuần với các đơn vị khác được Java hỗ trợ, nhưng không nên mặc định rằng mọi hệ thống tuyên bố hỗ trợ ISO-8601 đều nhận chúng. Khi trao đổi dữ liệu, hãy thống nhất tập cú pháp mà hai phía chấp nhận. Trong cấu hình thông thường, nên dùng chữ hoa và biểu diễn đơn giản như `P3M`, `P1Y2M`, `P10D` để người đọc dễ nhận ra ý nghĩa.

## 4. Chuyển đối tượng về chuỗi và kiểm tra dữ liệu sai

`toString()` trả về biểu diễn có thể đọc lại bằng `Period.parse`. Ví dụ:

```java
Period original = Period.of(1, 2, 3);
String encoded = original.toString();
Period decoded = Period.parse(encoded);
boolean sameValue = original.equals(decoded); // true
```

Giá trị được bảo toàn trong vòng chuyển đổi đối tượng → chuỗi → đối tượng. **Cách viết ban đầu của chuỗi không nhất thiết được giữ lại**: `P2W` thành `P14D`, chữ thường thành chữ hoa, thành phần 0 có thể biến mất. Nếu cần giữ nguyên văn dữ liệu người dùng đã nhập, phải lưu chuỗi gốc riêng; đừng dùng `toString()` như một cách phục hồi cách viết gốc.

`Period.parse` ném `DateTimeParseException` khi chuỗi không đúng cú pháp hoặc không biểu diễn được giá trị yêu cầu. Một số đầu vào sai điển hình:

| Đầu vào | Vì sao không dùng được với Period |
|---|---|
| `P` | Không có thành phần nào |
| `3M` | Thiếu tiền tố `P` |
| `P1D2M` | Sai thứ tự đơn vị |
| `P1.5M` | Thành phần không phải số nguyên |
| `PT15M` | Có phần giờ, không thuộc `Period` |
| `2026-10-25` | Là chuỗi ngày, không phải lượng theo lịch |
| ` P3M ` | Có khoảng trắng ngoài chuỗi; bộ phân tích không tự cắt bỏ |

`null` là trường hợp riêng và gây `NullPointerException`. Với dữ liệu bên ngoài, kiểm tra giá trị có mặt trước, rồi xử lý lỗi cú pháp bằng ngoại lệ phù hợp. Nếu giao diện cho phép bỏ qua khoảng trắng đầu/cuối, việc gọi `strip()` phải là lựa chọn được nêu rõ ở lớp tiếp nhận dữ liệu, không phải hành vi được mặc định gán cho `Period.parse`.

**Phân tích cú pháp thành công chưa đủ để đáp ứng quy tắc nghiệp vụ.** Ví dụ `P-3M`, `P0D` và `P1Y-2M` có thể là giá trị `Period` hợp lệ nhưng không phù hợp với quy định “thời hạn gia hạn phải dương và không có thành phần âm”. Khi quy định đúng như vậy, có thể kiểm tra `isZero()` và `isNegative()` sau khi đọc chuỗi. `isNegative()` trả về `true` khi có ít nhất một thành phần âm; nó không tính một tổng ngày giả định để quyết định dấu.

## 5. Chương trình chạy đầy đủ

Lưu đoạn sau vào `PeriodCreationDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài.

```java
import java.time.Period;
import java.time.format.DateTimeParseException;

public class PeriodCreationDemo {
    public static void main(String[] args) {
        Period plan = Period.of(1, 2, 3);
        System.out.println("created=" + plan);
        System.out.printf("parts=%d,%d,%d%n",
                plan.getYears(), plan.getMonths(), plan.getDays());

        Period weeks = Period.ofWeeks(2);
        System.out.println("weeks=" + weeks);
        System.out.println("parsedWeeks=" + Period.parse("P2W"));
        System.out.println("months=" + Period.ofMonths(15));
        System.out.println("parsed=" + Period.parse("P1Y2M3D"));
        System.out.println("zero=" + Period.ZERO);

        String encoded = plan.toString();
        System.out.println("roundTrip=" + plan.equals(Period.parse(encoded)));
        System.out.println("leadingSign=" + Period.parse("-P1Y2M"));
        System.out.println("componentSign=" + Period.parse("P-1Y2M"));

        try {
            Period.parse("PT15M");
        } catch (DateTimeParseException e) {
            System.out.println("invalid=DateTimeParseException");
        }

        System.out.println("renewal=" + parseRenewal("P3M"));
        try {
            parseRenewal("P1Y-2M");
        } catch (IllegalArgumentException e) {
            System.out.println("rejected=" + e.getMessage());
        }
    }

    static Period parseRenewal(String text) {
        if (text == null) {
            throw new IllegalArgumentException("missing period");
        }
        Period value = Period.parse(text);
        if (value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException("period must be positive");
        }
        return value;
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac PeriodCreationDemo.java
java PeriodCreationDemo
```

Kết quả chuẩn:

```text
created=P1Y2M3D
parts=1,2,3
weeks=P14D
parsedWeeks=P14D
months=P15M
parsed=P1Y2M3D
zero=P0D
roundTrip=true
leadingSign=P-1Y-2M
componentSign=P-1Y2M
invalid=DateTimeParseException
renewal=P3M
rejected=period must be positive
```

`parseRenewal` thể hiện hai bước độc lập: đọc được cấu trúc chuỗi, sau đó áp dụng điều kiện của một chức năng cụ thể. Chính sách “không có thành phần âm và không bằng 0” là lựa chọn của ví dụ này; bản thân `Period` vẫn cho phép các thành phần âm. Với chuỗi sai cú pháp, `DateTimeParseException` vẫn được truyền ra để lớp tiếp nhận có thể báo lỗi nhập liệu.

## 6. Tự thực hành

Trước khi chạy, dự đoán kết quả của các biểu thức sau rồi đối chiếu:

```java
System.out.println(Period.of(0, 15, 0));
System.out.println(Period.parse("P3W2D"));
System.out.println(Period.parse("P0Y0M0D"));
System.out.println(Period.parse("-P2M5D"));
System.out.println(Period.parse("P15M").getMonths());
```

Đáp án:

```text
P15M
P23D
P0D
P-2M-5D
15
```

Hãy giải thích bằng lời vì sao kết quả thứ hai không còn đơn vị tuần và vì sao kết quả cuối là `15`, thay vì `3`. Sau đó thử `P1D2M` và xác định đây là lỗi cú pháp, khác với giá trị hợp lệ nhưng bị `parseRenewal` từ chối.

## 7. Các điểm cần nhớ khi áp dụng

- Chọn phương thức tạo theo đơn vị đang có; giữ rõ ý nghĩa năm/tháng/ngày từ lúc nhận dữ liệu.
- `Period` có đúng ba thành phần năm, tháng, ngày; tuần được quy về ngày ngay khi tạo hoặc đọc chuỗi.
- `P3M` là 3 tháng; `PT3M` không thuộc cú pháp mà `Period` đọc.
- `parse` không tự chuẩn hóa tháng, không tự cắt khoảng trắng và không quyết định điều kiện nghiệp vụ.
- `toString()` giữ giá trị để đọc lại, có thể thay đổi cách viết so với chuỗi đầu vào.
- Đọc thành phần không đồng nghĩa với đổi toàn bộ khoảng sang một đơn vị duy nhất.

Tham khảo hợp đồng phương thức và cú pháp được hỗ trợ tại [Java SE 21 — Period](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html).
