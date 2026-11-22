# Locale và hệ cơ số khi phân tích số bằng Scanner

## 1. Một chuỗi số cần được hiểu theo quy tắc nào?

Chuỗi `1,234` không tự nói rõ dấu phẩy dùng để phân nhóm hàng nghìn hay ngăn phần thập phân. Chuỗi `10` cũng có thể biểu diễn giá trị mười trong hệ thập phân hoặc giá trị mười sáu trong hệ thập lục phân.

Khi dùng Scanner, hai cấu hình giúp làm rõ cách hiểu:

- **Locale:** quy ước vùng dùng khi nhận diện dạng biểu diễn số, đặc biệt dấu phân nhóm và dấu thập phân.
- **Hệ cơ số (radix):** số lượng chữ số của hệ đếm dùng khi đọc số nguyên, chẳng hạn 2, 8, 10 hoặc 16.

Đây là quy tắc của **dữ liệu đầu vào**. Hãy lấy chúng từ đặc tả tệp, giao thức hoặc yêu cầu nhập liệu. Không thử đổi qua nhiều Locale cho đến khi một chuỗi được chấp nhận: cùng chuỗi có thể hợp lệ nhưng cho hai giá trị khác nhau.

Luồng xử lý có thể hình dung như sau:

```text
Ký tự đầu vào
    → phân tách token bằng delimiter
    → nhận diện số theo Locale và radix phù hợp
    → kiểm tra phạm vi của kiểu dữ liệu
    → giá trị Java
```

Nếu nguồn ban đầu chứa byte, việc giải mã byte thành ký tự xảy ra trước chuỗi bước trên. `useLocale()` không thay charset và không sửa được chữ đã giải mã sai.

## 2. Các phương thức cần phân biệt

| Phương thức | Vai trò |
| --- | --- |
| `useLocale(locale)` | Cấu hình quy ước vùng cho Scanner |
| `locale()` | Xem Locale đang sử dụng |
| `useRadix(radix)` | Đặt hệ cơ số mặc định cho các lần đọc số nguyên |
| `radix()` | Xem hệ cơ số mặc định |
| `nextInt()` | Đọc int theo hệ cơ số mặc định |
| `nextInt(radix)` | Đọc int với hệ cơ số của riêng lần gọi này |
| `hasNextInt(radix)` | Kiểm tra token tiếp theo có đọc được thành int theo hệ đó không |
| `nextBigInteger(radix)` | Đọc số nguyên lớn theo hệ cơ số chỉ định |
| `nextDouble()`, `nextBigDecimal()` | Đọc số có phần thập phân theo cú pháp tương ứng và Locale |

Scanner mới có radix mặc định là 10. Locale ban đầu lấy từ `Locale.getDefault(Locale.Category.FORMAT)`. Có thể thiết lập riêng trên từng Scanner; không cần đổi Locale mặc định của toàn bộ ứng dụng chỉ để đọc một tệp. Xem [Scanner API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Scanner.html).

Dùng các hằng như `Locale.US`, `Locale.GERMANY`, hoặc tạo Locale theo thẻ ngôn ngữ khi đặc tả yêu cầu, chẳng hạn `Locale.forLanguageTag("vi-VN")`. [Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html) biểu diễn lựa chọn ngôn ngữ/vùng; bản thân nó không phải bộ chuyển đổi số.

## 3. Locale thay đổi ý nghĩa của dấu phân cách

Với các Locale thông dụng trong ví dụ:

| Locale | Dấu phân nhóm | Dấu thập phân | Ví dụ biểu diễn 1234,50 theo giá trị toán học |
| --- | --- | --- | --- |
| `Locale.US` | `,` | `.` | `1,234.50` |
| `Locale.GERMANY` | `.` | `,` | `1.234,50` |

Đừng xem Locale là phép “đổi mọi dấu phẩy thành dấu chấm”. Cấu trúc phân nhóm cũng phải hợp lệ. Chẳng hạn `12,34.50` không phải cách nhóm hàng nghìn thông thường của Locale.US.

### Ví dụ hoàn chỉnh: đọc cùng giá trị và phát hiện sự mơ hồ

Lưu thành `ScannerLocaleDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Scanner;

public class ScannerLocaleDemo {
    private static BigDecimal parseOne(String input, Locale locale) {
        try (Scanner scanner = new Scanner(input).useLocale(locale)) {
            BigDecimal value = scanner.nextBigDecimal();
            if (scanner.hasNext()) {
                throw new IllegalArgumentException("Extra token");
            }
            return value;
        }
    }

    public static void main(String[] args) {
        System.out.println("US grouped = "
                + parseOne("1,234.50", Locale.US).toPlainString());
        System.out.println("DE grouped = "
                + parseOne("1.234,50", Locale.GERMANY).toPlainString());

        System.out.println("US ambiguous = "
                + parseOne("1,234", Locale.US).toPlainString());
        System.out.println("DE ambiguous = "
                + parseOne("1,234", Locale.GERMANY).toPlainString());

        try (Scanner scanner = new Scanner("12,5;13,5")
                .useLocale(Locale.GERMANY)
                .useDelimiter(";")) {
            while (scanner.hasNextBigDecimal()) {
                System.out.println("field = "
                        + scanner.nextBigDecimal().toPlainString());
            }
            if (scanner.hasNext()) {
                throw new IllegalArgumentException("Invalid field");
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 ScannerLocaleDemo.java
java ScannerLocaleDemo
```

Stdout chính xác:

```text
US grouped = 1234.50
DE grouped = 1234.50
US ambiguous = 1234
DE ambiguous = 1.234
field = 12.5
field = 13.5
```

Hai dòng đầu là hai cách viết của cùng giá trị. Hai dòng `ambiguous` cho thấy nguy cơ khó nhận ra hơn: cả hai lần đều đọc thành công nhưng giá trị khác nhau một nghìn lần.

`BigDecimal` được dùng để quan sát số thập phân chính xác trong ví dụ. `toPlainString()` xuất biểu diễn thập phân không dùng dạng số mũ và không tự chuyển sang dấu thập phân theo Locale của Scanner. Các quy tắc giá trị và scale được mô tả trong [BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).

### Delimiter phải để nguyên cấu trúc của số

Đầu vào cuối dùng dấu chấm phẩy giữa hai số có dấu phẩy thập phân:

```text
12,5;13,5
```

Nếu cấu hình delimiter là dấu phẩy, `12,5` đã bị tách thành `12` và `5` trước khi phân tích số. Lúc đó chọn Locale.GERMANY cũng không ghép hai token lại thành một số.

Delimiter và Locale giải quyết hai tầng khác nhau. Với định dạng bảng có dấu nháy, trường được trích dẫn hoặc dấu phân cách xuất hiện trong nội dung, cần bộ đọc đúng định dạng; không xem việc thay delimiter đơn giản là bộ đọc CSV đầy đủ.

## 4. Hệ cơ số của số nguyên

Một số nguyên biểu diễn theo radix r dùng các vị trí có trọng số là lũy thừa của r. Với `FF` trong hệ 16:

```text
F = 15
FF(base 16) = 15 × 16 + 15 = 255(base 10)
```

Radix hợp lệ từ `Character.MIN_RADIX` đến `Character.MAX_RADIX`, tương ứng 2 đến 36. Các chữ cái được dùng cho các giá trị từ 10 trở lên; `FF` và `ff` đều dùng được trong hệ 16.

Với radix thấp hơn, một chữ số có thể trở thành không hợp lệ: `9` không hợp lệ trong hệ 8, còn `G` không hợp lệ trong hệ 16. Radix nằm ngoài 2..36 gây `IllegalArgumentException`; đó là lỗi cấu hình, khác với dữ liệu không khớp kiểu số.

### Cấu hình mặc định và chỉ định cho một lần đọc

Lưu thành `ScannerRadixDemo.java`:

```java
import java.util.Locale;
import java.util.Scanner;

public class ScannerRadixDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("FF 10 10")
                .useLocale(Locale.ROOT)) {
            System.out.println("initial radix = " + scanner.radix());
            System.out.println("explicit hex = " + scanner.nextInt(16));
            System.out.println("radix after explicit = " + scanner.radix());
            System.out.println("default decimal = " + scanner.nextInt());

            scanner.useRadix(16);
            System.out.println("configured hex = " + scanner.nextInt());
            System.out.println("configured radix = " + scanner.radix());
        }

        try (Scanner scanner = new Scanner("1010 077 -FF")
                .useLocale(Locale.ROOT)) {
            System.out.println("binary = " + scanner.nextInt(2));
            System.out.println("octal = " + scanner.nextInt(8));
            System.out.println("negative hex = " + scanner.nextInt(16));
        }

        try (Scanner scanner = new Scanner("077")) {
            System.out.println("leading zero, radix 10 = "
                    + scanner.nextInt());
        }
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 ScannerRadixDemo.java
java ScannerRadixDemo
```

Stdout chính xác:

```text
initial radix = 10
explicit hex = 255
radix after explicit = 10
default decimal = 10
configured hex = 16
configured radix = 16
binary = 10
octal = 63
negative hex = -255
leading zero, radix 10 = 77
```

`nextInt(16)` không đổi giá trị mà `radix()` trả về. Ngược lại, `useRadix(16)` có hiệu lực cho các lần gọi đọc số nguyên dùng radix mặc định sau đó, cho đến khi đổi lại cấu hình.

Chuỗi `077` không tự chuyển thành số bát phân chỉ vì có số 0 ở đầu. Muốn giá trị 63, phải chỉ định hệ 8. Cú pháp dữ liệu của Scanner không phải toàn bộ cú pháp literal trong mã nguồn Java.

## 5. Tiền tố và phạm vi kiểu dữ liệu

Ba vấn đề cần kiểm tra độc lập:

1. Các ký tự có tạo thành số hợp lệ trong radix đã chọn không?
2. Token có dùng cú pháp được Scanner hỗ trợ không?
3. Giá trị có nằm trong phạm vi kiểu đích không?

Ví dụ, khi dùng `nextInt(16)`:

- `FF` đọc thành 255.
- `0xFF` không được tự bỏ tiền tố `0x`.
- `G1` có chữ số không hợp lệ cho hệ 16.
- `80000000` là số dương 2147483648, vượt giá trị lớn nhất của int. Nó không tự được hiểu thành int âm theo mẫu bit.
- Dấu gạch dưới như `1_000` trong Java literal không được tự xử lý như khi compiler đọc mã nguồn.

Nếu đặc tả đầu vào cho phép tiền tố `0x`, cần xác thực và xử lý tiền tố theo quy tắc rõ ràng trước khi chuyển đổi; không xóa tùy tiện mọi ký tự không phải chữ số.

### Ví dụ hoàn chỉnh: kiểm tra và tiêu thụ token không hợp lệ

Lưu thành `ScannerNumberBoundaryDemo.java`:

```java
import java.math.BigInteger;
import java.util.Locale;
import java.util.Scanner;

public class ScannerNumberBoundaryDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("0xFF FF 80000000 G1 7")
                .useLocale(Locale.ROOT)
                .useRadix(16)) {
            while (scanner.hasNext()) {
                if (scanner.hasNextInt()) {
                    System.out.println("int = " + scanner.nextInt());
                } else {
                    System.out.println("rejected = " + scanner.next());
                }
            }
        }

        try (Scanner scanner = new Scanner("80000000")
                .useLocale(Locale.ROOT)) {
            BigInteger large = scanner.nextBigInteger(16);
            System.out.println("BigInteger = " + large);
        }
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 ScannerNumberBoundaryDemo.java
java ScannerNumberBoundaryDemo
```

Stdout chính xác:

```text
rejected = 0xFF
int = 255
rejected = 80000000
rejected = G1
int = 7
BigInteger = 2147483648
```

Vòng lặp không bị kẹt vì nhánh từ chối gọi `next()` để tiêu thụ token. Chỉ gọi lại `hasNextInt()` trên cùng token sai thì không tiến vị trí đọc.

`hasNextInt()` kiểm tra cả khả năng biểu diễn bằng int. Giá trị trả về `false` không đủ để phân biệt sai cú pháp với vượt phạm vi. Nếu cần thông báo cụ thể, hãy đọc token và tổ chức các bước xác thực theo yêu cầu. `BigInteger` biểu diễn số nguyên vượt phạm vi các kiểu nguyên thủy, nhưng ứng dụng vẫn cần giới hạn độ dài và miền giá trị phù hợp.

## 6. Locale và radix không thay thế lẫn nhau

`useRadix(16)` không biến dấu phẩy thập phân thành dấu chấm. `useLocale(Locale.GERMANY)` không làm `FF` trở thành số thập lục phân nếu vẫn đọc bằng `nextInt()` với radix 10.

Radix ở đây dùng cho việc đọc **số nguyên**. Không dùng `useRadix(2)` rồi kỳ vọng `nextDouble()` tự phân tích `10.1` như một phân số nhị phân. Các phương thức đọc số thực có cú pháp riêng; dấu thập phân và định dạng số theo Locale vẫn là vấn đề riêng.

Tương tự, Locale của Scanner không tự quyết định Locale của `printf`, giao diện hoặc tệp đầu ra. Nếu muốn in số theo quy tắc vùng, phải chọn Locale cho thao tác định dạng đầu ra riêng.

Đọc số với đúng Locale cũng chưa bảo đảm mọi quy tắc nghiệp vụ. Scanner có thể hỗ trợ nhiều dạng chữ số hoặc dạng biểu diễn mà giao thức của ứng dụng không cho phép. Nếu hợp đồng yêu cầu chính xác dạng ASCII `1234.50`, không có phân nhóm và đúng hai chữ số thập phân, cần xác thực cú pháp đó riêng thay vì chỉ dựa vào việc `hasNextBigDecimal()` trả `true`.

## 7. Xử lý lỗi và quản lý cấu hình

| Tình huống | Cách hiểu |
| --- | --- |
| `nextInt()` hoặc `nextBigDecimal()` gặp token không hợp lệ | Có thể ném InputMismatchException; token gây lỗi chưa bị tiêu thụ |
| Không còn token mà vẫn gọi phương thức đọc | NoSuchElementException |
| Radix ngoài 2..36 | IllegalArgumentException |
| Scanner đã đóng | IllegalStateException |
| Chỉ kiểm tra bằng `hasNextInt(radix)` | Không tiêu thụ token và không đổi radix mặc định |

Khi kiểm tra bằng `hasNextInt(16)`, hãy đọc bằng `nextInt(16)` tương ứng. Nếu kiểm tra hệ 16 rồi gọi `nextInt()` trong khi mặc định vẫn là 10, hai thao tác đang áp dụng hai quy tắc khác nhau.

`reset()` xóa các cấu hình tùy chỉnh về delimiter, Locale và radix; radix trở lại 10. Nó không tua lại nguồn và không làm những token đã đọc xuất hiện trở lại. Không dùng reset như một “dấu trang” để đọc thử rồi quay lại.

Với tệp do hệ thống khác tạo, nên thiết lập Locale và radix rõ ràng ở nơi tạo Scanner rồi truyền nó vào hàm đọc. Tránh việc một hàm phụ âm thầm đổi cấu hình của Scanner dùng chung mà nơi gọi không biết. Với dữ liệu chứa các trường có hệ cơ số khác nhau, các phương thức như `nextInt(16)` thường biểu đạt ý định tại từng trường rõ hơn.

## 8. Thực hành

1. Đổi `"FF 10 10"` thành `"ff 10 10"`: kết quả số không thay đổi.
2. Đọc `"100"` bằng `nextInt(2)`, `nextInt(8)`, `nextInt(10)`, `nextInt(16)` trên bốn Scanner độc lập. Kết quả lần lượt là 4, 64, 100 và 256.
3. Đọc `"1,234"` bằng hai Locale trong ví dụ đầu. Giải thích vì sao kiểm tra “không có ngoại lệ” không chứng minh giá trị đúng.
4. Thay delimiter `;` bằng `,` trong ví dụ hai số thập phân. Quan sát rằng ranh giới token đã thay đổi trước bước nhận diện số.
5. Thử `"80000000"` với `hasNextInt(16)` và `hasNextBigInteger(16)`: một phép kiểm tra thất bại do phạm vi int, phép còn lại chấp nhận số nguyên lớn.

Trước mỗi lần nhập số, hãy xác định rõ: token được tách như thế nào, dấu phân nhóm/thập phân tuân theo Locale nào, số nguyên thuộc hệ cơ số nào và kiểu đích có chứa được giá trị hay không.
