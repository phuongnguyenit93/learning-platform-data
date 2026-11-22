# Phân biệt độ chính xác khi trình bày với giá trị số gốc trong Java

## Mục tiêu

Khi một ứng dụng Java hiển thị số tiền, tỷ lệ, điểm số hoặc kết quả đo, ta thường muốn **hiển thị ít chữ số hơn** để dễ đọc. Chẳng hạn, một phép tính có giá trị `12.3456` nhưng giao diện chỉ hiện `12.35`. Cần phân biệt rõ:

- **Giá trị số gốc**: dữ liệu được lưu trong biến `double`, `float`, `BigDecimal` hoặc kết quả của phép tính.
- **Độ chính xác khi trình bày**: số chữ số được chọn để tạo chuỗi hiển thị, thông qua `String.format`, `System.out.printf` hoặc formatter tương tự.
- **Làm tròn giá trị để sử dụng tiếp**: phép toán thật sự tạo ra một giá trị số mới theo quy tắc làm tròn, ví dụ `BigDecimal.setScale(..., RoundingMode.HALF_UP)`.

**Định dạng thành hai chữ số sau dấu thập phân không thay đổi biến số gốc.** Kết quả định dạng là một `String`; các phép toán làm tròn là chuyện khác và cần chọn quy tắc phù hợp với nghiệp vụ.

Bài này tập trung vào Java Core, chủ đề định dạng chuỗi, đặc biệt format specifier `%.2f` và ý nghĩa của nó so với giá trị đang được giữ trong bộ nhớ.

## 1. Ví dụ đầu tiên: số vẫn nguyên, chuỗi được rút gọn

```java
import java.util.Locale;

double original = 12.3456;

String displayed = String.format(Locale.US, "%.2f", original);

System.out.println("Original: " + original);
System.out.println("Displayed: " + displayed);
System.out.println("Still original: " + original);
```

Kết quả:

```text
Original: 12.3456
Displayed: 12.35
Still original: 12.3456
```

Phân tích:

1. `original` có kiểu `double`; lệnh `String.format` đọc giá trị này để tạo văn bản.
2. Chỉ thị `%.2f` yêu cầu biểu diễn số thực kiểu thập phân cố định với **hai chữ số sau dấu phân cách thập phân**.
3. `displayed` là chuỗi `"12.35"`, không phải một `double` mới.
4. Biến `original` chưa bị gán lại nên tiếp tục được dùng cho phép tính tiếp theo ở độ chính xác mà kiểu `double` đang lưu.

**Lưu ý về `double`:** số thập phân `12.3456` không nhất thiết được biểu diễn chính xác tuyệt đối bằng nhị phân IEEE 754. Việc `Double.toString` hiện `12.3456` có nghĩa nó xuất một dạng thập phân ngắn có thể chuyển trở lại cùng giá trị `double`, không phải bằng chứng rằng bit trong bộ nhớ mã hóa chính xác phân số thập phân đó. Tuy vậy, thao tác định dạng không sửa các bit của biến `original`.

## 2. Ý nghĩa của `%.2f`, `%8.2f` và `%.3g`

Các phương thức thuộc họ `java.util.Formatter` dùng cú pháp dấu `%` để mô tả cách biểu diễn một giá trị.

Ví dụ:

```java
String a = String.format(Locale.US, "%.2f", 12.3456);
String b = String.format(Locale.US, "%8.2f", 12.3456);
String c = String.format(Locale.US, "%.3g", 12345.678);
```

Bảng so sánh:

| Format | Ý nghĩa | Ví dụ kết quả |
| --- | --- | --- |
| `%.2f` | Số dạng thập phân cố định, hai chữ số sau dấu phân cách | `12.35` |
| `%.0f` | Số dạng thập phân cố định, không có chữ số sau dấu phân cách | `12` với `12.3456` |
| `%8.2f` | Như `%.2f` nhưng độ rộng tối thiểu của trường là tám ký tự | `"   12.35"` |
| `%.3e` | Dạng khoa học, ba chữ số sau dấu phân cách ở phần định trị | `1.235e+01` với `12.3456` |
| `%.3g` | Định dạng tổng quát với ba **chữ số có nghĩa** | `1.23e+04` với `12345.678` |

Đối với chuyển đổi `f`, *precision* là số chữ số sau dấu phân cách thập phân. Đối với `g`, *precision* biểu thị số chữ số có nghĩa. Đối với `e`, nó là số chữ số sau dấu phân cách trong phần định trị của dạng khoa học. Không thể hiểu mọi loại specifier theo cùng một quy tắc.

Ví dụ `%8.2f` có hai loại tham số định dạng khác nhau: `8` là **độ rộng hiển thị tối thiểu**, còn `2` mới là độ chính xác sau dấu thập phân. Độ rộng nhỏ hơn kết quả cần hiển thị sẽ không khiến Java âm thầm cắt bớt chữ số số học.

`%.2f` làm tròn để tạo chuỗi chứ không phải thao tác cắt chuỗi theo ký tự. Giá trị `12.3456` thành `12.35`, không phải `12.34`. Cách làm tròn ở tình huống đúng nửa đơn vị cần được xét cẩn thận khi dữ liệu đến từ số dấu phẩy động nhị phân.

### Chỉ thị `%d` không có precision kiểu `%.2f`

`%d` dùng cho số nguyên. Trong Java Formatter, không dùng `%.2d` để nói rằng muốn "số nguyên có hai chữ số"; precision không được hỗ trợ cho chuyển đổi số nguyên kiểu `d`. Nếu muốn thêm số không phía trước, một cách viết là `%02d`:

```java
String padded = String.format(Locale.US, "%02d", 7);
System.out.println(padded); // 07
```

Số `7` vẫn là số nguyên 7; `07` ở đây là **chuỗi được định dạng**, phù hợp hiển thị mã có độ rộng cố định theo yêu cầu.

## 3. Ba thao tác khác nhau cần phân biệt

| Thao tác | Kiểu dữ liệu đầu ra | Có sửa biến ban đầu? | Có tạo giá trị số đã làm tròn để tính tiếp? |
| --- | --- | --- | --- |
| `String.format(Locale.US, "%.2f", x)` | `String` | Không | Không |
| `System.out.printf("%.2f", x)` | Ghi chuỗi đã định dạng ra output | Không | Không |
| `BigDecimal.setScale(2, mode)` | `BigDecimal` mới | Không vì `BigDecimal` bất biến | Có |
| `Math.round(x)` với `x` kiểu `double` | `long` | Không | Có, nhưng làm tròn đến số nguyên |
| `new BigDecimal("12.3456")` | `BigDecimal` | Không | Biểu diễn giá trị thập phân được xây dựng từ chuỗi, chưa giảm scale |

Điểm quan trọng là phải xem **bạn cần làm gì với kết quả**. Nếu chỉ cần hiển thị báo cáo có hai chữ số thập phân, tạo `String` thường là đủ. Nếu nghiệp vụ yêu cầu chốt tiền đến cent, lưu số tiền đã quy đổi hoặc thực hiện các phép tính khác trên giá trị làm tròn, cần tạo giá trị số phù hợp và chọn `RoundingMode` có chủ đích.

Không nên chuyển một chuỗi đã định dạng sang số bằng `Double.parseDouble` chỉ để làm tròn: điều này trộn trách nhiệm hiển thị với tính toán và có thể thất bại theo locale (ví dụ chuỗi `12,35`).

## 4. `BigDecimal`: kiểm soát giá trị thập phân và quy tắc làm tròn

Các bài toán tài chính hoặc quy tắc thập phân chính xác thường cần `BigDecimal` thay vì dựa vào phép tính tiền tệ với `double`.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal original = new BigDecimal("12.3456");
BigDecimal rounded = original.setScale(2, RoundingMode.HALF_UP);

System.out.println(original); // 12.3456
System.out.println(rounded);  // 12.35
System.out.println(original); // 12.3456
```

Trong ví dụ, constructor từ **chuỗi thập phân** giữ đúng giá trị `12.3456`. Lệnh `setScale(2, RoundingMode.HALF_UP)` tạo **một đối tượng số mới** với hai chữ số sau dấu thập phân và làm tròn theo chế độ đã chọn. `BigDecimal` là bất biến: biến `original` không bị sửa.

### Phân biệt `HALF_UP` và `HALF_EVEN`

Các chế độ làm tròn là quy tắc nghiệp vụ, đặc biệt khi giá trị nằm **đúng giữa hai kết quả có thể**:

```java
BigDecimal sample = new BigDecimal("2.345");

System.out.println(sample.setScale(2, RoundingMode.HALF_UP));
System.out.println(sample.setScale(2, RoundingMode.HALF_EVEN));
```

Kết quả:

```text
2.35
2.34
```

Ở bước làm tròn đến hai chữ số, `2.345` nằm đúng giữa `2.34` và `2.35`. `HALF_UP` làm tròn phía xa số không khi đúng nửa; `HALF_EVEN` chọn kết quả có chữ số cuối được giữ là chẵn, trong trường hợp này là `2.34`.

Không suy luận chế độ làm tròn nghiệp vụ chỉ từ những gì hiển thị bằng `%.2f`. Nếu chính sách kế toán quy định `HALF_EVEN`, `HALF_UP` hoặc chế độ khác, hãy thực hiện chính sách trên giá trị số bằng `BigDecimal`.

### Vì sao nên tránh `new BigDecimal(double)` cho thập phân cố định

`double` lưu giá trị nhị phân gần với chữ số thập phân người dùng viết. Constructor `new BigDecimal(1.005)` chuyển **chính xác giá trị nhị phân của double** sang dạng thập phân, có thể tạo kết quả dài và khác mong đợi.

Nếu nguồn là chuỗi thập phân, dùng `new BigDecimal("1.005")`. Nếu nguồn đã là `double` và cần cách biểu diễn thập phân theo `Double.toString`, `BigDecimal.valueOf(double)` thường phù hợp hơn constructor nhận `double` trực tiếp. Dù vậy, `valueOf` không thể khôi phục thông tin chính xác đã mất từ các phép tính nhị phân trước đó.

Khi yêu cầu tính tiền, nên giữ dữ liệu dưới dạng `BigDecimal` phù hợp từ lúc nhập và xác định điểm làm tròn rõ ràng. Không tạo số đã làm tròn bằng cách biến đổi kết quả hiển thị nhiều lần.

## 5. `Locale` chỉ đổi quy ước trình bày

Một giá trị số có thể được viết khác nhau theo quốc gia:

```java
double amount = 12345.678;

String us = String.format(Locale.US, "%,.2f", amount);
String de = String.format(Locale.GERMANY, "%,.2f", amount);

System.out.println(us);
System.out.println(de);
```

Kết quả:

```text
12,345.68
12.345,68
```

Giải thích:

- Với `Locale.US`, dấu phẩy nhóm hàng nghìn và dấu chấm phân cách phần thập phân.
- Với `Locale.GERMANY`, dấu chấm nhóm hàng nghìn và dấu phẩy phân cách phần thập phân.
- `%,.2f` bật nhóm chữ số (`,`) và chọn hai chữ số thập phân (`.2`).

Cả hai định dạng đọc cùng một `double amount`. Sự thay đổi dấu phân cách không làm thay đổi giá trị lưu trong biến.

**Khuyến nghị về hợp đồng API:** Đầu ra dành cho con người nên dùng `Locale` thích hợp. Dữ liệu trao đổi giữa hệ thống nên dùng biểu diễn được định nghĩa bởi chuẩn truyền tin (ví dụ JSON number theo cú pháp JSON) hoặc một schema có quy định rõ kiểu, precision và locale. Không lưu thẳng `"12.345,68"` vào trường số của API rồi mong `Double.parseDouble` hiểu đúng.

`String.format("%.2f", value)` không truyền `Locale` sẽ sử dụng locale mặc định. Nếu kết quả dùng trong test, log có cấu trúc hoặc dữ liệu trao đổi cần tính ổn định, hãy chỉ định `Locale.US` hoặc locale phù hợp với chuẩn đầu ra thay vì phụ thuộc vào máy chạy.

## 6. Chọn lúc làm tròn: trước hay sau khi tính toán?

Giả sử bạn cần tính tổng ba giá trị `0.333`. Có hai chiến lược không tương đương:

1. **Giữ độ chính xác đầu vào**, cộng ba giá trị rồi làm tròn kết quả: `0.333 + 0.333 + 0.333 = 0.999`, làm tròn hai chữ số thành `1.00`.
2. **Làm tròn từng giá trị trước khi cộng**: mỗi `0.333` thành `0.33`, sau đó tổng thành `0.99`.

Ví dụ với `BigDecimal` để tránh độ lệch nhị phân:

```java
BigDecimal each = new BigDecimal("0.333");

BigDecimal roundAtEnd = each.add(each).add(each)
        .setScale(2, RoundingMode.HALF_UP);

BigDecimal roundBeforeSum = each.setScale(2, RoundingMode.HALF_UP)
        .multiply(new BigDecimal("3"));

System.out.println(roundAtEnd);       // 1.00
System.out.println(roundBeforeSum);   // 0.99
```

Không thể quyết định quy tắc nào đúng chỉ từ cách hiển thị. Đối với hóa đơn, thuế, thống kê hoặc phép đo, quy tắc làm tròn từng dòng hay trên tổng là **yêu cầu nghiệp vụ**. API cần nói rõ điểm làm tròn, số chữ số thập phân và `RoundingMode`, bởi chúng có thể thay đổi kết quả thực tế.

Nếu chỉ muốn hiển thị hai chữ số ở từng bước nhưng giữ số gốc để tính tiếp, có thể định dạng mỗi giá trị cho giao diện mà vẫn tính tổng bằng giá trị chưa được làm tròn. Phân biệt rõ "số đã hiển thị" với "số được dùng cho phép tính".

## 7. Ví dụ Java 17+ chạy hoàn chỉnh

Tạo tệp **`PrecisionPresentationDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public class PrecisionPresentationDemo {
    public static void main(String[] args) {
        double original = 12.3456;
        String displayed = String.format(Locale.US, "%.2f", original);

        System.out.println("Original: " + original);
        System.out.println("Displayed: " + displayed);
        System.out.println("Still original: " + original);
        System.out.println(
                "Width: [" + String.format(Locale.US, "%8.2f", original) + "]"
        );

        double quantity = 12345.678;
        System.out.println(
                "US: " + String.format(Locale.US, "%,.2f", quantity)
        );
        System.out.println(
                "Germany: " + String.format(Locale.GERMANY, "%,.2f", quantity)
        );

        BigDecimal amount = new BigDecimal("12.3456");
        BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);

        System.out.println("Decimal original: " + amount);
        System.out.println("Decimal rounded: " + rounded);
        System.out.println("Decimal original again: " + amount);

        BigDecimal halfway = new BigDecimal("2.345");
        System.out.println(
                "Half up: " + halfway.setScale(2, RoundingMode.HALF_UP)
        );
        System.out.println(
                "Half even: " + halfway.setScale(2, RoundingMode.HALF_EVEN)
        );
        System.out.println(
                "Significant: " + String.format(Locale.US, "%.3g", quantity)
        );
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 PrecisionPresentationDemo.java
java PrecisionPresentationDemo
```

Kết quả hiển thị:

```text
Original: 12.3456
Displayed: 12.35
Still original: 12.3456
Width: [   12.35]
US: 12,345.68
Germany: 12.345,68
Decimal original: 12.3456
Decimal rounded: 12.35
Decimal original again: 12.3456
Half up: 2.35
Half even: 2.34
Significant: 1.23e+04
```

Mỗi dòng chứng minh một điểm:

- `Original` và `Still original` trùng nhau; chỉ có `Displayed` dùng độ chính xác trình bày thấp hơn.
- `Width` thêm ba dấu cách phía trước để đạt chiều rộng tối thiểu tám ký tự; đây không phải thay đổi giá trị số.
- `US` và `Germany` dùng cùng số nhưng dấu phân cách theo locale.
- `BigDecimal.setScale` tạo giá trị thập phân làm tròn riêng, vẫn giữ đối tượng số gốc.
- `HALF_UP` và `HALF_EVEN` cho kết quả khác nhau ở điểm chính giữa.
- `%.3g` lấy ba chữ số có nghĩa, có thể dùng ký hiệu khoa học; khác với việc yêu cầu ba chữ số sau dấu thập phân.

## 8. Những tình huống thực tế và hướng xử lý

| Nhu cầu | Hướng xử lý | Lý do |
| --- | --- | --- |
| Hiển thị điểm trung bình thành hai chữ số | `String.format(locale, "%.2f", average)` | Chỉ thay đổi chuỗi đầu ra |
| In một bảng có cột số được căn đều | `%8.2f` hoặc `%-8.2f` | Width/alignment là yêu cầu trình bày |
| Lưu giá tiền đã chốt đến hai chữ số | `BigDecimal.setScale(2, roundingMode)` theo quy tắc nghiệp vụ | Giá trị số mới được chọn có chủ đích |
| Tính tỷ lệ rồi hiển thị phần trăm | Tính tỷ lệ, đổi sang đơn vị phần trăm nếu cần, sau đó format kết quả | `%.2f` tự nó không nhân với 100 |
| Hiển thị nhiều locale | Format trên cùng giá trị số với locale thích hợp | Dấu thập phân và dấu nhóm là quy ước ngôn ngữ |
| Viết số vào dữ liệu máy đọc | Dùng schema/serializer với biểu diễn số được quy định | Chuỗi format cho giao diện có thể không parse thống nhất |
| So sánh kết quả tính toán | Dùng giá trị số và định nghĩa epsilon/precision theo yêu cầu | Chuỗi cùng hiển thị không chứng minh giá trị số bằng nhau |

### Hai số khác nhau có thể hiển thị giống nhau

```java
double a = 1.231;
double b = 1.234;

System.out.println(String.format(Locale.US, "%.2f", a)); // 1.23
System.out.println(String.format(Locale.US, "%.2f", b)); // 1.23
System.out.println(a == b);                              // false
```

Hai chuỗi hiển thị đều là `"1.23"` nhưng giá trị số gốc không bằng nhau. Do đó không được suy luận `a == b` từ việc hai ô giao diện có cùng nội dung hai chữ số thập phân.

Ngược lại, việc hiển thị khác nhau do locale cũng không có nghĩa các số khác nhau. Khi thiết kế test, hãy phân biệt **kiểm thử định dạng** (so sánh chuỗi với locale cố định) và **kiểm thử tính toán** (so sánh giá trị, tolerance hoặc giá trị BigDecimal theo yêu cầu).

### Hai chuỗi có vẻ khác nhau nhưng biểu thị cùng giá trị

Ví dụ `"12.30"` và `"12.3"` là hai `String` khác nhau. Khi được diễn giải theo cùng quy ước thập phân, chúng đều biểu thị giá trị số 12.3. Đối với `BigDecimal`, phương thức `equals` còn xét cả scale; `new BigDecimal("12.30").equals(new BigDecimal("12.3"))` là `false`, trong khi `compareTo` trả về 0. Việc chọn so sánh "bằng nhau" theo giá trị hay theo cách biểu diễn cần khớp hợp đồng API.

## 9. Các lỗi thường gặp

1. **Cho rằng `String.format("%.2f", value)` làm tròn biến `value`.** Nó trả về chuỗi mới. Nếu tiếp tục tính toán, `value` vẫn như cũ.
2. **Gọi mọi specifier precision là "số chữ số thập phân".** Với `f` là chữ số sau dấu thập phân, với `g` là chữ số có nghĩa.
3. **Nhầm width với precision.** `%8.2f` có width 8 và precision 2; width không giới hạn số chữ số có nghĩa của giá trị.
4. **Dùng `%.2f` để làm tròn tiền tệ trong nghiệp vụ.** Nếu giá trị làm tròn phải được lưu hay tính tiếp, hãy định nghĩa kiểu số và chính sách làm tròn tường minh.
5. **Dùng `new BigDecimal(double)` khi nguồn là số thập phân người dùng nhập.** Nó giữ giá trị nhị phân của `double`, có thể khác kỳ vọng thập phân. Ưu tiên tạo từ chuỗi đã được parse hợp lệ hoặc từ nguồn `BigDecimal`.
6. **Dùng `Math.round` mà mong thu được hai chữ số thập phân.** Với `double`, `Math.round` trả về `long` nguyên; việc nhân chia với lũy thừa 10 dễ đưa sai số nhị phân vào phép tính.
7. **Bỏ qua `Locale`.** Các môi trường có thể hiển thị dấu phân cách khác nhau, khiến so sánh chuỗi hay parse ngược không ổn định.
8. **Làm tròn từng thành phần mà nghiệp vụ muốn làm tròn trên tổng.** Kết quả cuối có thể khác nhau, như ví dụ 0.333.
9. **So sánh số bằng chuỗi đã format.** Hai số khác nhau có thể cùng hiển thị thành `1.23`, và cùng một số có thể xuất hiện khác nhau ở hai locale.

## 10. Tự kiểm tra

**Câu 1.** Cho `double price = 19.999;`. Sau `String label = String.format(Locale.US, "%.2f", price);`, kiểu của `label` là gì? Biến `price` có thành 20.00 không?

**Đáp án:** `label` có kiểu `String`, mang nội dung `"20.00"`. `price` vẫn là cùng giá trị `double` trước lời gọi.

**Câu 2.** `%.3f` khác `%.3g` thế nào?

**Đáp án:** `%.3f` yêu cầu ba chữ số sau dấu phân cách thập phân trong biểu diễn cố định; `%.3g` yêu cầu ba chữ số có nghĩa trong biểu diễn tổng quát.

**Câu 3.** Vì sao `BigDecimal.setScale(2, RoundingMode.HALF_EVEN)` không giống chỉ in bằng `%.2f`?

**Đáp án:** `setScale` trả về đối tượng số `BigDecimal` mới đã được làm tròn bằng chế độ rõ ràng. `%.2f` chỉ tạo chuỗi trình bày theo quy tắc của formatter và không thay đổi giá trị số được truyền vào.

**Câu 4.** Vì sao không nên lấy chuỗi `"12.345,68"` (locale Đức) rồi đưa thẳng vào `Double.parseDouble`?

**Đáp án:** `Double.parseDouble` nhận cú pháp thập phân theo quy tắc không dùng dấu nhóm kiểu Đức; chuỗi này không phù hợp và sẽ gây `NumberFormatException`. Nếu phải đọc số định dạng theo locale, hãy dùng parser đúng locale và xác định rõ hợp đồng dữ liệu.

**Câu 5.** `0.333` được ghi ba lần. Làm tròn từng số thành `0.33` rồi cộng có giống cộng thành `0.999` rồi làm tròn không?

**Đáp án:** Không. Trường hợp đầu thành `0.99`, trường hợp sau thành `1.00` khi dùng làm tròn hai chữ số theo `HALF_UP`. Cần làm theo quy định của nghiệp vụ.

## Ghi nhớ

**Độ chính xác khi trình bày là quy tắc chuyển giá trị số sang `String`; nó không đồng nghĩa với độ chính xác của giá trị số gốc hay chính sách làm tròn dùng cho tính toán.** Dùng `String.format`/`printf` để hiển thị, dùng `BigDecimal` và `RoundingMode` khi thật sự cần giá trị thập phân đã làm tròn, và truyền `Locale` rõ ràng khi quy ước dấu phân cách có ý nghĩa.
