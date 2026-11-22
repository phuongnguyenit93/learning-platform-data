# Độ rộng, độ chính xác và căn lề

## 1. Ba yêu cầu khác nhau khi trình bày dữ liệu

Khi in một báo cáo dạng cột, ta thường cần:

- Các cột có khoảng dành sẵn để dễ đọc.
- Chuỗi hoặc số được biểu diễn với mức chi tiết phù hợp.
- Nội dung nằm sát trái hoặc sát phải trong phần dành sẵn.

Trong chuỗi định dạng của `Formatter` và `printf`, ba việc đó tương ứng với:

| Thành phần | Câu hỏi nó giải quyết |
| --- | --- |
| Độ rộng (width) | Kết quả được dành tối thiểu bao nhiêu ký tự? |
| Độ chính xác (precision) | Với conversion này, mức chi tiết hoặc giới hạn nội dung là gì? |
| Căn lề | Nếu còn chỗ trống, thêm khoảng đệm ở bên nào? |

Chúng không phải ba cách nói của cùng một giới hạn. Đặc biệt, **độ rộng không cắt dữ liệu dài**, và **độ chính xác không có cùng ý nghĩa cho mọi loại dữ liệu**.

Các quy tắc dưới đây thuộc API định dạng vẫn được hỗ trợ trên JDK hiện đại; xem [Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html).

## 2. Đọc đúng vị trí các thành phần

Với một chỉ thị định dạng thông thường:

```text
%[argument_index$][flags][width][.precision]conversion
```

Ví dụ:

```text
%-10.5s
 │ │ │└─ s: biểu diễn chuỗi
 │ │ └── .5: giới hạn nội dung chuỗi
 │ └──── 10: độ rộng tối thiểu
 └────── -: căn trái
```

Với `"JavaLearning"`, phần chuỗi được lấy là `"JavaL"`, sau đó thêm năm khoảng trắng bên phải để đủ độ rộng 10.

Còn `%10.2f` có nghĩa:

- Biểu diễn số theo dạng thập phân cố định `f`.
- Hai chữ số sau dấu thập phân.
- Dành ít nhất mười ký tự cho toàn bộ biểu diễn.
- Căn phải theo mặc định.

Dấu chấm trong **chuỗi mẫu** luôn viết là `.` để giới thiệu precision. Ký tự phân cách thập phân xuất hiện trong **kết quả** lại phụ thuộc locale.

## 3. Độ rộng là tối thiểu, không phải tối đa

```java
String text = String.format(Locale.ROOT, "%8s", "Java");
```

Kết quả nằm giữa dấu ngoặc để nhìn rõ khoảng trắng:

```text
[    Java]
```

Chuỗi `Java` dài 4, nên cần thêm 4 khoảng trắng để đủ 8. Theo mặc định, phần đệm ở bên trái.

Nhưng với chuỗi dài hơn độ rộng:

```java
String text = String.format(Locale.ROOT, "%4s", "JavaLearning");
```

Kết quả:

```text
[JavaLearning]
```

Không có việc cắt còn `"Java"`. Giá trị dài 12 nên toàn bộ biểu diễn vẫn dài 12.

Số nguyên cũng vậy:

```java
String text = String.format(Locale.ROOT, "%3d", 12345);
```

Kết quả là `12345`, dài 5. Độ rộng 3 không làm mất các chữ số đầu hoặc cuối.

Điều này rất quan trọng khi xuất bảng: một giá trị bất ngờ dài hơn sẽ mở rộng cột và có thể làm lệch bố cục. Nếu sản phẩm cần giới hạn tối đa, phải chọn chính sách riêng cho dữ liệu dài; không dựa vào width.

## 4. Căn phải, căn trái và số 0 đệm

### Căn phải mặc định

```java
String text = String.format(Locale.ROOT, "%8s", "Java");
```

Biểu diễn:

```text
[    Java]
```

### Căn trái bằng cờ -

```java
String text = String.format(Locale.ROOT, "%-8s", "Java");
```

Biểu diễn:

```text
[Java    ]
```

Ký tự `-` là cờ căn trái, không phải một số width âm. Khi cần căn trái, vẫn viết độ rộng dương sau cờ.

Nếu không có độ rộng thì không có một phần dành sẵn để căn trái; mẫu như `%-s` báo lỗi thiếu width.

### Đệm số 0 cho định dạng số phù hợp

```java
String text = String.format(Locale.ROOT, "%08.2f", -12.3);
```

Kết quả:

```text
[-0012.30]
```

Toàn bộ biểu diễn dài 8: dấu trừ, bốn chữ số phần nguyên, dấu thập phân và hai chữ số phần lẻ.

Số 0 được đặt sau dấu, không phải tạo thành `000-12.30`. Cờ `0` là quy tắc định dạng số ở conversion hỗ trợ nó, không phải cách đệm tùy ý cho mọi chuỗi.

Không kết hợp `-` và `0` để yêu cầu vừa căn trái vừa đệm 0. `%-08d` là tổ hợp cờ không hợp lệ và ném `IllegalFormatFlagsException`; xem [ngoại lệ tổ hợp cờ](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/IllegalFormatFlagsException.html).

## 5. Precision của chuỗi: giới hạn nội dung trước khi đệm

Với chuỗi thông thường được định dạng bằng `%s`, precision giới hạn số ký tự được đưa vào kết quả.

```java
String text = String.format(Locale.ROOT, "%.3s", "JavaLearning");
```

Kết quả là `Jav`.

Kết hợp width và precision:

```java
String text = String.format(Locale.ROOT, "%8.3s", "JavaLearning");
```

Kết quả:

```text
[     Jav]
```

Có thể suy luận theo hai bước:

1. Precision 3 giới hạn phần nội dung còn `Jav`.
2. Width 8 thêm 5 khoảng trắng, vì phần nội dung hiện dài 3.

Đổi thành `%-8.3s` thì năm khoảng trắng nằm bên phải.

Precision của chuỗi không tự thêm dấu `...` hoặc ký tự biểu thị nội dung bị cắt. Nếu cần dấu lược bỏ, phải thiết kế bước xử lý đó riêng, tính cả phần dành cho dấu lược bỏ vào giới hạn mong muốn.

Width và precision cũng không phải đơn vị pixel hay một bảo đảm về số ô hiển thị của terminal. Emoji, dấu kết hợp và kiểu chữ có độ rộng khác nhau có thể làm bố cục nhìn lệch dù số ký tự Java trông phù hợp. Với văn bản Unicode cần cắt theo ký tự người dùng nhìn thấy, phải có chính sách xử lý cụm ký tự phù hợp; đừng xem `%.Ns` là bộ dàn trang văn bản hoàn chỉnh.

## 6. Precision của số: phụ thuộc conversion

### f: số chữ số sau dấu thập phân

```java
String text = String.format(Locale.ROOT, "%.2f", 123.456);
```

Kết quả là `123.46`. Đây là làm tròn để hiển thị, không phải cắt đơn thuần phần dư thành `123.45`.

Với `%8.2f`, biểu diễn `123.46` dài 6 nên thêm hai khoảng trắng bên trái:

```text
[  123.46]
```

Nếu số có phần nguyên lớn hơn, width không cắt nó. Precision 2 chỉ giới hạn phần lẻ theo quy tắc của conversion `f`, không giới hạn tổng chiều dài số.

### e: số chữ số sau dấu thập phân của phần trị

```java
String text = String.format(Locale.ROOT, "%.2e", 12345.0);
```

Kết quả:

```text
1.23e+04
```

Precision 2 điều khiển hai chữ số sau dấu thập phân của phần `1.23`. Nó không có nghĩa toàn bộ chuỗi chỉ có hai chữ số.

### g: tổng số chữ số có nghĩa

```java
String text = String.format(Locale.ROOT, "%.4g", 12.3);
```

Kết quả là `12.30`: bốn chữ số có nghĩa theo quy tắc định dạng của Java.

Với `g`, precision không mang nghĩa “bốn chữ số sau dấu thập phân”. Conversion này chọn dạng thập phân hoặc dạng khoa học theo giá trị và precision. Không thay `f` bằng `g` nếu yêu cầu nghiệp vụ là luôn có đúng N chữ số sau dấu thập phân.

### Không phải conversion nào cũng nhận precision

`%.2d` không phải cách in số nguyên với ít nhất hai chữ số. Precision không áp dụng cho conversion số nguyên `d`.

Muốn số nguyên 7 thành `07`, dùng width và cờ đệm số 0:

```java
String text = String.format(Locale.ROOT, "%02d", 7);
```

Conversion ký tự, ngày/giờ, phần trăm và xuống dòng cũng không nhận precision theo cùng cách của chuỗi hoặc số thực. Khi conversion không hỗ trợ, việc truyền precision có thể ném `IllegalFormatPrecisionException`; xem [hợp đồng ngoại lệ precision](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/IllegalFormatPrecisionException.html).

## 7. Độ rộng tính cho cả biểu diễn, không riêng chữ số

Với số, phần được tính vào độ rộng có thể bao gồm:

- Dấu cộng hoặc trừ.
- Chữ số phần nguyên và phần lẻ.
- Dấu phân cách thập phân.
- Dấu phân nhóm nếu có.
- Phần số mũ với dạng khoa học.
- Dấu ngoặc hoặc tiền tố tương ứng với cách định dạng được chọn.

Vì vậy không thể dự đoán độ rộng chỉ bằng cách đếm số chữ số của giá trị gốc.

Một cách suy luận thuận tiện:

```text
Giá trị + conversion + precision + locale + các cờ số
    ↓
Biểu diễn nội dung
    ↓
Nếu còn ngắn hơn width, thêm phần đệm theo quy tắc căn lề
```

Đây là mô hình để hiểu kết quả, không phải yêu cầu mọi implementation phải thực hiện đúng từng bước nội bộ như vậy.

Ví dụ `%8.2f` với `123.456`:

```text
Biểu diễn nội dung: 123.46  → 6 ký tự
Width: 8
Phần đệm: 2 khoảng trắng ở trái
```

Đừng lấy “width trừ số chữ số gốc” làm công thức, vì làm tròn có thể làm thay đổi cả số chữ số phần nguyên.

## 8. Ví dụ đầy đủ: nhìn thấy cả khoảng trắng và lỗi cấu hình

Tệp `FormatLayoutDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.math.BigDecimal;
import java.util.Locale;

public class FormatLayoutDemo {
    private static void show(String label, String pattern, Object value) {
        String text = String.format(Locale.ROOT, pattern, value);
        System.out.println(label + "=[" + text + "], length=" + text.length());
    }

    private static void showError(String pattern, Object value) {
        try {
            String.format(Locale.ROOT, pattern, value);
        } catch (IllegalArgumentException expected) {
            System.out.println(pattern + " -> "
                    + expected.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        show("right", "%8s", "Java");
        show("left", "%-8s", "Java");
        show("stringLimit", "%8.3s", "JavaLearning");
        show("stringLong", "%4s", "JavaLearning");
        show("integerLong", "%3d", 12345);
        show("fixed", "%8.2f", 123.456);
        show("negativeZeroPad", "%08.2f", -12.3);
        show("scientific", "%.2e", 12345.0);
        show("significant", "%.4g", 12.3);
        show("decimalRounding", "%.2f", new BigDecimal("12.345"));

        System.out.printf(Locale.ROOT, "|%-8s|%4s|%8s|%n",
                "Item", "Qty", "Price");
        System.out.printf(Locale.ROOT, "|%-8s|%4d|%8.2f|%n",
                "Tea", 3, 12.5);

        showError("%.2d", 12);
        showError("%-s", "Java");
        showError("%-08d", 12);
    }
}
```

Biên dịch và chạy:

```shell
javac FormatLayoutDemo.java
java FormatLayoutDemo
```

Kết quả:

```text
right=[    Java], length=8
left=[Java    ], length=8
stringLimit=[     Jav], length=8
stringLong=[JavaLearning], length=12
integerLong=[12345], length=5
fixed=[  123.46], length=8
negativeZeroPad=[-0012.30], length=8
scientific=[1.23e+04], length=8
significant=[12.30], length=5
decimalRounding=[12.35], length=5
|Item    | Qty|   Price|
|Tea     |   3|   12.50|
%.2d -> IllegalFormatPrecisionException
%-s -> MissingFormatWidthException
%-08d -> IllegalFormatFlagsException
```

Dấu `[` và `]` không phải formatter tự thêm vào các giá trị; phương thức `show` thêm chúng để phần đệm dễ quan sát.

Phần `length=` đếm chiều dài chuỗi đã tạo bằng `String.length()`. Với các ký tự ASCII trong ví dụ, việc đếm không gặp vấn đề emoji hoặc dấu kết hợp.

Ba lỗi cuối được bắt có chủ ý để chương trình tiếp tục minh họa. Trong mã ứng dụng, các mẫu cố định sai như vậy nên được sửa và kiểm tra trước khi dùng, không bắt ngoại lệ rồi bỏ nội dung báo cáo.

## 9. Dựng bảng bằng cách chọn kiểu căn phù hợp

Ví dụ báo cáo thường dùng:

- Tên mặt hàng căn trái.
- Số lượng căn phải.
- Giá căn phải và có hai chữ số phần lẻ.

```java
// Mã minh họa hai dòng của một bảng.
System.out.printf(Locale.ROOT, "|%-8s|%4s|%8s|%n",
        "Item", "Qty", "Price");
System.out.printf(Locale.ROOT, "|%-8s|%4d|%8.2f|%n",
        "Tea", 3, 12.5);
```

Tiêu đề `Qty` dùng `%s`, còn dữ liệu số lượng dùng `%d`. Cùng width không có nghĩa phải dùng cùng conversion.

Nếu tên dài hơn 8 ký tự, `%-8s` sẽ mở rộng cột. Nếu yêu cầu chỉ cho tối đa 8 ký tự, có thể cân nhắc `%-8.8s` với dữ liệu chuỗi phù hợp, nhưng phải chấp nhận việc cắt nội dung. Đối với thông tin định danh hoặc dữ liệu không được mất, nên mở rộng cột hoặc chuyển sang cấu trúc xuất khác.

Không dùng precision của số để “ép vừa cột” bằng cách bỏ các chữ số quan trọng của phần nguyên. Khi số vượt chiều rộng dự kiến, cần xác định chính sách hiển thị thay vì âm thầm làm sai dữ liệu.

## 10. Precision hiển thị không thay đổi giá trị nguồn

```java
double value = 123.456;
String shown = String.format(Locale.ROOT, "%.2f", value);
```

`shown` là `"123.46"`, nhưng `value` không được gán lại. Các phép tính sau vẫn dùng giá trị `double` đang lưu.

Với số thập phân cần cách biểu diễn chính xác ngay từ dữ liệu đầu vào, có thể dùng `BigDecimal` từ chuỗi:

```java
BigDecimal amount = new BigDecimal("12.345");
String shown = String.format(Locale.ROOT, "%.2f", amount);
```

Kết quả hiển thị trong ví dụ là `12.35`. `amount` vẫn biểu diễn `12.345`.

Nếu nghiệp vụ yêu cầu một quy tắc làm tròn cụ thể cho **giá trị tính toán**, phải áp dụng quy tắc đó ở tầng tính toán, ví dụ bằng API của `BigDecimal` với chế độ làm tròn đã chọn. Không để một mẫu `printf` trở thành nơi duy nhất xác định quy tắc tiền tệ.

Cũng cần nhớ số thực nhị phân không biểu diễn chính xác mọi phân số thập phân. Việc chọn precision là định dạng kết quả của giá trị đang có, không tự sửa sai số đã phát sinh từ cách lưu hoặc tính dữ liệu trước đó.

## 11. Các lỗi tư duy thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| `%5s` luôn tạo đúng 5 ký tự | Tạo ít nhất 5, có thể dài hơn |
| `%5d` giới hạn số nguyên còn 5 chữ số | Không cắt số nguyên dài |
| `%.2f` chỉ lấy hai chữ số rồi bỏ phần dư | Có làm tròn theo quy tắc conversion |
| `%.2d` tương đương `%02d` | Precision không áp dụng cho `d` |
| Precision luôn là số chữ số phần lẻ | Với `g` là chữ số có nghĩa; với `s` là giới hạn nội dung |
| `-` là width âm | Đây là cờ căn trái |
| Đệm 0 chỉ là thêm ký tự 0 ở đầu chuỗi | Quy tắc số đặt đệm đúng vị trí so với dấu |
| Width tạo cột có độ rộng pixel cố định | Đây không phải bộ dàn trang hay phép đo font |

Khi kết quả lệch, nên xem chuỗi giữa dấu phân cách và kiểm tra độ dài trước khi sửa thử các con số trong mẫu.

## 12. Bài tập tự kiểm tra

1. `%6s` với `"AB"` cho bốn khoảng trắng bên trái rồi AB.
2. `%-6s` với `"AB"` cho AB rồi bốn khoảng trắng bên phải.
3. `%6.2s` với `"ABCDEFG"` cho bốn khoảng trắng rồi AB: precision giới hạn nội dung trước khi áp dụng phần đệm.
4. `%2d` với `1234` vẫn in `1234`.
5. Vì sao `%.4g` với `12.3` khác `%.4f`? Mẫu đầu yêu cầu bốn chữ số có nghĩa, mẫu sau yêu cầu bốn chữ số sau dấu thập phân.
6. Nếu một cột tên dùng `%-8s` nhưng tên dài 20 ký tự, hãy chọn rõ: mở rộng, xuống dòng hay cắt có thông báo; width không tự quyết định thay ứng dụng.

Khi soạn mẫu, hãy quyết định lần lượt **cách biểu diễn → mức chi tiết → khoảng dành sẵn → phía đặt phần đệm**. Cách tách bốn quyết định này giúp tránh việc sửa width để giải một vấn đề thực ra thuộc precision hoặc chính sách dữ liệu dài.
