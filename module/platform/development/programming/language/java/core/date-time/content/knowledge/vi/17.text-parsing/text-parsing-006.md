# Phân biệt phân tích không phân biệt hoa thường với xử lý ngày nghiêm ngặt

## 1. Dễ nhập tên tháng không có nghĩa là được nhập ngày không tồn tại

Giả sử một biểu mẫu nhận ngày theo mẫu `dd-MMM-uuuu`, trong đó `MMM` là tên tháng viết tắt bằng tiếng Anh. Người dùng có thể nhập `28-Feb-2023`, `28-FEB-2023` hoặc `28-feb-2023`. Bạn muốn chấp nhận cả ba cách viết nhưng vẫn phải từ chối `29-FEB-2023`, vì năm 2023 không có ngày 29 tháng 2.

Đây là **hai điều kiện độc lập**:

- Khi nhận diện tên tháng, có cần phân biệt chữ hoa và chữ thường không?
- Sau khi đã đọc được năm, tháng và ngày, chúng có tạo thành ngày hợp lệ không?

Trong Java, có thể nới điều kiện thứ nhất đồng thời giữ nghiêm điều kiện thứ hai. Cấu hình phù hợp là `DateTimeFormatterBuilder.parseCaseInsensitive()` kết hợp với `DateTimeFormatter.withResolverStyle(ResolverStyle.STRICT)`.

Đừng hạ mức kiểm tra ngày chỉ để chấp nhận tên tháng viết hoa. Cũng đừng nghĩ rằng chọn `STRICT` sẽ bắt buộc mọi chữ trong văn bản phải đúng hoa/thường.

## 2. Hai bước phân tích và ba nhóm điều khiển

Bộ định dạng đọc chuỗi qua hai bước chính:

```text
"28-fEb-2023"
       |
       v
Bước 1: Khớp văn bản với mẫu
        đọc ngày 28, tên tháng fEb, năm 2023
        nhận diện fEb là tháng 2 nhờ Locale và chính sách hoa/thường
       |
       v
Bước 2: Giải quyết các trường
        năm 2023 + tháng 2 + ngày 28 có hợp lệ không?
       |
       v
LocalDate: 2023-02-28
```

Trong bước đầu, có hai nhóm lựa chọn riêng: chính sách hoa/thường và mức linh hoạt khi đọc hình thức văn bản. Chúng cũng khác với chính sách giải quyết ngày ở bước sau.

| Cấu hình | Điều khiển việc gì? | Không thay thế việc gì? |
|---|---|---|
| `parseCaseInsensitive()` / `parseCaseSensitive()` | So khớp chữ hoa/thường trong các phần tiếp theo của bộ phân tích | Không kiểm tra năm nhuận hay số ngày của tháng |
| `parseStrict()` / `parseLenient()` trên builder | Mức linh hoạt khi đọc số, dấu và độ rộng theo thành phần của bộ phân tích | Không thay thế `ResolverStyle` |
| `withResolverStyle(STRICT/SMART/LENIENT)` | Kết hợp và kiểm tra các trường đã đọc thành ngày/giờ | Không chọn ngôn ngữ hay chính sách hoa/thường |

Các API có chữ `Strict` hoặc `Lenient` trong tên dễ gây nhầm, nhưng tác động ở vị trí khác nhau. Mục tiêu “nhận tên tháng không phân biệt hoa/thường và kiểm tra ngày hợp lệ” không đòi hỏi `parseLenient()` hoặc `ResolverStyle.LENIENT`.

## 3. Tạo bộ định dạng phù hợp

Khai báo sau có thể đặt trong một phương thức Java:

```java
DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .parseCaseInsensitive()
        .appendPattern("dd-MMM-uuuu")
        .toFormatter(Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);
```

Đọc từng bước:

1. `parseCaseInsensitive()` chuyển chính sách cho các thành phần được thêm phía sau sang không phân biệt hoa/thường.
2. `appendPattern` thêm cấu trúc ngày, tên tháng viết tắt và năm.
3. `toFormatter(Locale.ENGLISH)` chỉ rõ bộ tên tháng tiếng Anh cần nhận.
4. `withResolverStyle(STRICT)` yêu cầu các trường kết hợp thành ngày thực sự tồn tại.

`Locale.ENGLISH` là phần quan trọng: không phân biệt hoa/thường không đồng nghĩa với nhận mọi ngôn ngữ. `FEB` có thể khớp tên tháng tiếng Anh; một tên tháng tiếng Pháp không tự được dịch sang tiếng Anh chỉ vì đã bật lựa chọn này.

Với ngày lịch ISO, dùng `uuuu` trong ví dụ. `yyyy` là năm trong kỷ nguyên (`YEAR_OF_ERA`); nếu thiếu dữ liệu kỷ nguyên, phân tích nghiêm ngặt có thể chưa đủ trường để tạo `LocalDate`. Dùng đúng trường năm giúp tránh nhầm lỗi mô hình ngày với lỗi hoa/thường.

Bộ định dạng tạo ra là bất biến và có thể dùng chung. `withResolverStyle` trả về một bộ định dạng mới, vì vậy phải dùng giá trị trả về. Builder là đối tượng có thể thay đổi, nên dùng để dựng cấu hình rồi giữ `DateTimeFormatter` hoàn chỉnh để tái sử dụng.

## 4. So sánh bằng hai trục thay vì một mức “nghiêm” duy nhất

Với mẫu tiếng Anh `dd-MMM-uuuu`, xét ba cấu hình:

| Đầu vào | Phân biệt hoa/thường + STRICT | Không phân biệt hoa/thường + STRICT | Không phân biệt hoa/thường + SMART |
|---|---|---|---|
| `28-Feb-2023` | `2023-02-28` | `2023-02-28` | `2023-02-28` |
| `28-FEB-2023` | Lỗi khớp tên tháng | `2023-02-28` | `2023-02-28` |
| `29-FEB-2023` | Lỗi khớp tên tháng | Lỗi ngày không tồn tại | `2023-02-28` |
| `29-feb-2024` | Lỗi khớp tên tháng | `2024-02-29` | `2024-02-29` |

Ở hàng `29-FEB-2023`, cấu hình không phân biệt hoa/thường đã nhận diện đúng tháng 2. Nhưng khi dùng `STRICT`, nó vẫn từ chối tổ hợp ngày của năm không nhuận. Khi đổi riêng chính sách giải quyết trường sang `SMART`, giá trị ngày 29 trong tháng 2 năm đó được điều chỉnh về ngày cuối tháng.

Sự điều chỉnh này không liên quan đến việc viết `FEB`, `Feb` hay `feb`: đó là quyết định ở bước giải quyết trường. Nếu yêu cầu của biểu mẫu là người dùng phải nhập một ngày tồn tại, chọn `SMART` để “dễ nhập hơn” có thể làm ngày bị thay đổi ngoài ý muốn.

### parseStrict() không tự làm ngày trở nên nghiêm ngặt

Builder mặc định đọc văn bản theo chế độ nghiêm ngặt và phân biệt hoa/thường. Bộ định dạng trả về bởi `toFormatter(...)` mặc định lại giải quyết trường theo `SMART`.

Vì vậy đoạn sau vẫn có thể điều chỉnh `29-Feb-2023` về `2023-02-28`:

```java
DateTimeFormatter textStrictOnly = new DateTimeFormatterBuilder()
        .parseStrict()
        .appendPattern("dd-MMM-uuuu")
        .toFormatter(Locale.ENGLISH);
```

`parseStrict()` trong đoạn này áp dụng vào cách đọc văn bản; nó không tự gọi `withResolverStyle(STRICT)`. Hai mặc định có vẻ trái ngược nhưng thuộc hai bước khác nhau.

## 5. Vị trí gọi và phạm vi của chính sách hoa/thường

Các lời gọi `parseCaseInsensitive()` và `parseCaseSensitive()` ảnh hưởng những thành phần thêm vào **sau** lời gọi đó. Chúng có thể được đổi giữa chừng trong builder.

Ví dụ, muốn tên tháng linh hoạt nhưng hậu tố bắt buộc đúng ` END`:

```java
DateTimeFormatter mixed = new DateTimeFormatterBuilder()
        .parseCaseInsensitive()
        .appendPattern("dd-MMM-uuuu")
        .parseCaseSensitive()
        .appendLiteral(" END")
        .toFormatter(Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);
```

`28-feb-2023 END` được nhận, còn `28-feb-2023 end` bị từ chối. Khoảng trắng trước `END` là một phần của chuỗi nguyên văn và vẫn phải có. Chuyển chế độ không biến khoảng trắng hoặc dấu phân cách thành tùy chọn.

Nếu chỉ gọi `parseCaseInsensitive()` sau khi đã thêm toàn bộ mẫu ngày, nó không quay lại sửa chính sách cho các phần đã thêm. Hãy đặt cấu hình trước phần văn bản cần chịu tác động; với mẫu đơn giản, đặt ngay trước `appendPattern` giúp người đọc dễ kiểm tra phạm vi.

Lựa chọn này chỉ ảnh hưởng việc **đọc chuỗi**. Nó không yêu cầu `format()` in tên tháng thành chữ thường hay chữ hoa. Muốn thay cách hiển thị cần thiết kế đầu ra riêng, không suy ra từ chính sách nhận diện chữ đầu vào.

## 6. Chương trình chạy đầy đủ

Lưu tệp `CaseAndDateStrictnessDemo.java` dưới đây. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class CaseAndDateStrictnessDemo {
    public static void main(String[] args) {
        DateTimeFormatter sensitiveStrict = new DateTimeFormatterBuilder()
                .appendPattern("dd-MMM-uuuu")
                .toFormatter(Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter insensitiveStrict = new DateTimeFormatterBuilder()
                .parseCaseInsensitive()
                .appendPattern("dd-MMM-uuuu")
                .toFormatter(Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter insensitiveSmart =
                insensitiveStrict.withResolverStyle(ResolverStyle.SMART);

        show("sensitive-strict", "28-Feb-2023", sensitiveStrict);
        show("sensitive-strict", "28-FEB-2023", sensitiveStrict);
        show("insensitive-strict", "28-FEB-2023", insensitiveStrict);
        show("insensitive-strict", "28-fEb-2023", insensitiveStrict);
        show("insensitive-strict", "29-FEB-2023", insensitiveStrict);
        show("insensitive-smart", "29-FEB-2023", insensitiveSmart);
        show("insensitive-strict", "29-feb-2024", insensitiveStrict);
        show("insensitive-strict", "28/Feb/2023", insensitiveStrict);
        show("insensitive-strict", "28-Feb-2023x", insensitiveStrict);

        DateTimeFormatter textStrictOnly = new DateTimeFormatterBuilder()
                .parseStrict()
                .appendPattern("dd-MMM-uuuu")
                .toFormatter(Locale.ENGLISH);
        System.out.println("builder-default="
                + textStrictOnly.getResolverStyle());
        show("parseStrict-only", "29-Feb-2023", textStrictOnly);

        DateTimeFormatter mixed = new DateTimeFormatterBuilder()
                .parseCaseInsensitive()
                .appendPattern("dd-MMM-uuuu")
                .parseCaseSensitive()
                .appendLiteral(" END")
                .toFormatter(Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);
        show("mixed", "28-feb-2023 END", mixed);
        show("mixed", "28-feb-2023 end", mixed);
    }

    static void show(String label, String text, DateTimeFormatter formatter) {
        try {
            LocalDate date = LocalDate.parse(text, formatter);
            System.out.println(label + " | " + text + " -> " + date);
        } catch (DateTimeParseException e) {
            System.out.println(label + " | " + text + " -> ERROR");
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac CaseAndDateStrictnessDemo.java
java CaseAndDateStrictnessDemo
```

Kết quả chuẩn:

```text
sensitive-strict | 28-Feb-2023 -> 2023-02-28
sensitive-strict | 28-FEB-2023 -> ERROR
insensitive-strict | 28-FEB-2023 -> 2023-02-28
insensitive-strict | 28-fEb-2023 -> 2023-02-28
insensitive-strict | 29-FEB-2023 -> ERROR
insensitive-smart | 29-FEB-2023 -> 2023-02-28
insensitive-strict | 29-feb-2024 -> 2024-02-29
insensitive-strict | 28/Feb/2023 -> ERROR
insensitive-strict | 28-Feb-2023x -> ERROR
builder-default=SMART
parseStrict-only | 29-Feb-2023 -> 2023-02-28
mixed | 28-feb-2023 END -> 2023-02-28
mixed | 28-feb-2023 end -> ERROR
```

`ERROR` là nhãn do chương trình in khi bắt `DateTimeParseException`, không phải nguyên văn thông báo của Java. Chương trình kiểm tra cả lỗi nhận diện văn bản lẫn lỗi ngày không tồn tại; không nên phân loại hai lỗi này chỉ bằng việc thấy cùng một nhãn.

Dòng `28/Feb/2023` vẫn lỗi vì dấu phân cách không khớp mẫu. Dòng có ký tự `x` cuối chuỗi lỗi vì `LocalDate.parse(text, formatter)` yêu cầu đọc hết chuỗi; không tự bỏ phần dư chỉ vì bộ phân tích không phân biệt hoa/thường.

## 7. Những điều không được suy ra từ parseCaseInsensitive

- **Không tự bỏ dấu tiếng Việt.** Không phân biệt hoa/thường không phải chế độ loại bỏ dấu hoặc so khớp gần đúng.
- **Không tự sửa từ gõ sai.** Tên tháng viết sai không trở thành tên tháng hợp lệ.
- **Không tự dịch ngôn ngữ.** Bộ tên được nhận vẫn phụ thuộc `Locale` và mẫu đã chọn.
- **Không tự bỏ khoảng trắng hoặc đổi dấu phân cách.** Chuỗi vẫn phải đáp ứng cấu trúc của bộ định dạng.
- **Không tự chọn chính sách năm nhuận.** Việc chấp nhận hay điều chỉnh ngày phụ thuộc giải quyết trường.
- **Không thay thế kiểm tra nghiệp vụ.** Một ngày có thật vẫn có thể không đáp ứng quy định như “ngày cấp không được nằm trong tương lai”.

Không cần biến cả chuỗi thành chữ hoa hoặc chữ thường để đạt mục tiêu của bài. Cách biến đổi thủ công có thể ảnh hưởng những phần cần giữ nguyên, phụ thuộc ngôn ngữ khi dùng quy tắc mặc định, và làm thay đổi chuỗi nguồn cần báo lỗi. Cấu hình bộ phân tích giúp diễn tả đúng phần được phép linh hoạt mà vẫn giữ nguyên dữ liệu người dùng đã nhập.

Nếu cần chuẩn hóa khoảng trắng, đó là một quyết định riêng ở lớp tiếp nhận. Hãy xác định rõ có cho phép hay không thay vì coi đó là tác dụng của `parseCaseInsensitive`.

## 8. Tự kiểm tra và áp dụng

Khi xây dựng một bộ phân tích ngày có tên tháng, hãy xác định ba câu trả lời riêng:

1. Tên tháng thuộc ngôn ngữ nào và dùng dạng đầy đủ hay viết tắt?
2. Chữ hoa/thường có mang ý nghĩa bắt buộc trong từng phần không?
3. Ngày không tồn tại phải bị từ chối hay có chính sách điều chỉnh đã thống nhất?

Để thực hành, thêm các đầu vào sau vào chương trình trước khi xem dự đoán:

| Đầu vào | Với insensitiveStrict | Lý do |
|---|---|---|
| `31-APR-2023` | Lỗi | Tháng 4 không có ngày 31 |
| `30-aPr-2023` | `2023-04-30` | Tên tháng nhận diện được và ngày có thật |
| `29-FEB-2024` | `2024-02-29` | Năm nhuận |

Sau đó thử bỏ riêng `.withResolverStyle(ResolverStyle.STRICT)` khi tạo bộ định dạng không phân biệt hoa/thường. Hãy kiểm tra `getResolverStyle()` và quan sát điều gì xảy ra với `31-APR-2023`: tên tháng vẫn được đọc linh hoạt, nhưng chính sách ngày đã đổi sang mặc định `SMART`.

Tài liệu tham khảo: [DateTimeFormatterBuilder — parseCaseInsensitive, parseCaseSensitive và parseStrict](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html), [ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html) và [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) trong Java SE 21.
