# Quy tắc không trùng hằng `case` trong `switch` expression (Java 14+)

## 1. Mục tiêu và quy tắc cốt lõi

Trong `switch` expression, mỗi nhánh `case` xác định một hoặc nhiều giá trị có thể khớp với biểu thức đặt trong `switch (...)`. **Trong cùng một khối `switch`, không được có hai hằng `case` mang cùng giá trị**. Trình biên dịch kiểm tra điều này khi biên dịch mã nguồn và báo lỗi nếu phát hiện trùng, ngay cả khi hai nhánh viết khác nhau hoặc có phần thân khác nhau.

Quy tắc đã có khi `switch` expression trở thành tính năng chính thức ở Java 14 (JEP 361) và **vẫn áp dụng trong Java hiện đại**. Nó cũng áp dụng cho `switch` statement, cho cả cú pháp mũi tên `->` và cú pháp dấu hai chấm `:`.

Ví dụ sau **không biên dịch được** vì `1 + 1` và `2` đều có giá trị `2`:

```java
int code = 2;
String text = switch (code) {
    case 2 -> "Hai";
    case 1 + 1 -> "Cũng là hai"; // LỖI: trùng giá trị case 2
    default -> "Giá trị khác";
};
```

Đây là **lỗi biên dịch** (thường có thông báo `duplicate case label`), không phải tình huống JVM chọn nhánh đầu tiên rồi bỏ qua nhánh còn lại. Không thể dùng `default`, `break` hay `yield` để hợp thức hóa hai nhãn trùng nhau.

## 2. Thế nào được xem là trùng?

Đối với `case` hằng, Java xét **giá trị hằng sau khi tính ở thời điểm biên dịch**, không chỉ so sánh cách viết của nhãn.

| Dạng hằng | Ví dụ | Kết luận |
| --- | --- | --- |
| Số nguyên viết khác cách | `case 10` và `case 0xA` | Trùng: cùng là 10 |
| Biểu thức hằng số | `case 3` và `case 1 + 2` | Trùng: cùng là 3 |
| Hằng được khai báo | `case 7` và `case LIMIT` khi `LIMIT = 7` là constant variable | Trùng |
| Ký tự và mã số | `case 'A'` và `case 65` trong `switch` của `int` | Trùng: `'A'` có giá trị 65 |
| Chuỗi | `case "OK"` và `case "O" + "K"` | Trùng: cùng giá trị chuỗi `OK` |
| Enum | `case READY` lặp ở hai nhánh của cùng `switch` | Trùng: cùng một enum constant |

Với `String`, việc chọn nhánh dựa trên **nội dung chuỗi** (`equals`), không phải địa chỉ tham chiếu của đối tượng. Với hằng được nối chuỗi từ các literal, trình biên dịch biết giá trị trước khi chương trình chạy.

### 2.1. Trùng giữa hai nhánh khác nhau

```java
static final int CODE_OK = 200;
static final int ALSO_OK = 100 + 100;

// Trích đoạn trong một phương thức:
String message = switch (status) {
    case CODE_OK -> "OK";
    case ALSO_OK -> "Vẫn OK"; // LỖI: cả hai hằng đều là 200
    default -> "Khác";
};
```

Tên biến khác nhau không tạo ra hai giá trị `case` khác nhau. `static final` chỉ giúp nhãn là hằng hợp lệ khi kiểu và giá trị khởi tạo đáp ứng điều kiện của *constant variable*; không đảm bảo giá trị duy nhất.

### 2.2. Trùng ngay trong một nhãn gộp

```java
String group = switch (n) {
    case 1, 1 -> "Nhóm A"; // LỖI: lặp 1 ngay trong danh sách
    default -> "Khác";
};
```

Cú pháp gộp nhãn `case 1, 2 -> ...` là hợp lệ **khi từng hằng khác giá trị**. Dấu phẩy là cách đưa nhiều giá trị hợp lệ về cùng một nhánh; nó không miễn kiểm tra trùng lặp. Quy tắc áp dụng trên **toàn bộ khối**: nếu nhãn `case 1, 2` đã sử dụng `2` thì không thể thêm `case 2` ở phía dưới.

### 2.3. Trùng với enum hoặc String

```java
enum State { READY, RUNNING }

// Trích đoạn trong phương thức nhận tham số State state:
String result = switch (state) {
    case READY -> "Sẵn sàng";
    case RUNNING -> "Đang chạy";
    case READY -> "Lặp READY"; // LỖI: enum constant READY lặp lại
};
```

```java
// Trích đoạn trong phương thức nhận String command:
String action = switch (command) {
    case "START" -> "Bắt đầu";
    case "ST" + "ART" -> "Bắt đầu lần nữa"; // LỖI: hai chuỗi cùng giá trị
    default -> "Không rõ";
};
```

Hai nhánh `case "start"` và `case "START"` không bị coi là trùng vì Java phân biệt chữ hoa/chữ thường; chúng chỉ nên được dùng nếu ứng dụng thật sự muốn hai giá trị đầu vào khác nhau.

## 3. Ví dụ đúng, chạy được từ Java 14 trở lên

Lưu chương trình sau thành tệp **`UniqueCaseExample.java`**:

```java
public class UniqueCaseExample {
    private static final int NEW = 1;
    private static final int PROCESSING = 2;
    private static final int DONE = 3;

    public static void main(String[] args) {
        int status = PROCESSING;

        String description = switch (status) {
            case NEW -> "Mới";
            case PROCESSING -> "Đang xử lý";
            case DONE -> "Hoàn tất";
            default -> "Không xác định";
        };

        System.out.println(description);
        System.out.println(group(1));
        System.out.println(group(3));
    }

    static String group(int status) {
        return switch (status) {
            case 1, 2 -> "Chưa hoàn tất";
            case 3 -> "Đã hoàn tất";
            default -> "Khác";
        };
    }
}
```

Biên dịch và chạy với JDK 14+ (ví dụ JDK 17 hoặc 21):

```bash
javac UniqueCaseExample.java
java UniqueCaseExample
```

Kết quả:

```text
Đang xử lý
Chưa hoàn tất
Đã hoàn tất
```

Vì sao hợp lệ?

- Trong `switch (status)` thứ nhất, các hằng `NEW`, `PROCESSING` và `DONE` lần lượt là `1`, `2`, `3`: không trùng.
- Trong `switch` của phương thức `group`, nhánh `case 1, 2` gom **hai giá trị khác nhau**; nhánh `case 3` dùng giá trị còn lại.
- Số `1`, `2`, `3` được sử dụng lại trong **hai khối `switch` khác nhau** là hoàn toàn hợp lệ: phạm vi kiểm tra trùng là từng khối `switch`, không phải toàn phương thức hay toàn lớp.
- `default` xử lý các giá trị nguyên còn lại, khiến cả hai `switch` expression đều có nhánh trả về kết quả phù hợp. Nhánh `->` không rơi tiếp (*fall through*) sang nhánh sau.

Để xác nhận cú pháp còn tương thích chính xác với Java 14 khi đang dùng JDK mới hơn, có thể dùng `javac --release 14 UniqueCaseExample.java` rồi chạy bằng `java UniqueCaseExample`.

## 4. Kiểm chứng lỗi biên dịch và cách sửa

Đây là ví dụ độc lập **cố ý sai**, lưu thành `DuplicateCaseExample.java`:

```java
public class DuplicateCaseExample {
    public static void main(String[] args) {
        int code = 2;
        String label = switch (code) {
            case 2 -> "Hai";
            case 1 + 1 -> "Lặp hai"; // LỖI: trùng case 2
            default -> "Khác";
        };
        System.out.println(label);
    }
}
```

Chạy:

```bash
javac DuplicateCaseExample.java
```

Kết quả **biên dịch thất bại** với lỗi về nhãn `case` trùng (thường là `duplicate case label`; vị trí/dòng và định dạng thông báo tùy phiên bản `javac`). Vì không tạo được chương trình hợp lệ nên **không có stdout của chương trình**.

Cách sửa phụ thuộc mục đích:

**Hai cách viết của cùng một giá trị:** chỉ giữ **một** nhãn cho giá trị đó.

```java
String label = switch (code) {
    case 2 -> "Hai";
    default -> "Khác";
};
```

**Hai giá trị *khác nhau* cần chung kết quả:** gộp chúng trong cùng một nhãn, không gộp hai hằng trùng nhau.

```java
String label = switch (code) {
    case 1, 2 -> "Một hoặc hai";
    default -> "Khác";
};
```

**Hai điều kiện nghiệp vụ cần phân biệt nhưng có cùng mã số:** sửa thiết kế mã/trạng thái để có giá trị riêng, hoặc kiểm tra điều kiện khác bên trong **một** nhánh, thay vì lặp nhãn `case`.

## 5. Phân biệt với các quy tắc liên quan

### 5.1. `case` hằng phải có giá trị xác định tại lúc biên dịch

Một biểu thức `case` hằng phải là **constant expression** (hoặc tên enum constant). Ví dụ `static final int A = 2;`, `1 + 1` và `"O" + "K"` có thể được xác định khi biên dịch. Trái lại, có từ khóa `final` **chưa chắc** đủ:

```java
final int runtimeCode = Integer.parseInt("2");

// Trích đoạn trong một phương thức:
String text = switch (code) {
    case runtimeCode -> "Hai"; // LỖI: không phải constant expression
    default -> "Khác";
};
```

Ở đây lỗi là **`constant expression required`**, khác với lỗi **`duplicate case label`**. Nếu mã phụ thuộc dữ liệu tính lúc chạy, hãy dùng `if/else` hoặc thiết kế lại tập giá trị chuyển nhánh; không cố dùng biến runtime làm `case` hằng.

### 5.2. `default` và tính bao phủ không thay thế tính duy nhất

- Một khối `switch` có nhiều nhất **một** nhãn `default`. `default` không phải một giá trị hằng có thể dùng để che một nhãn bị lặp.
- `switch` expression phải bao phủ các giá trị có thể xảy ra (*exhaustive*). Với `int` hoặc `String` thường cần `default`; với `enum`, liệt kê đủ mọi enum constant có thể không cần `default`. **Đủ nhánh** và **không trùng nhãn** là hai yêu cầu riêng: đáp ứng yêu cầu này không tự động đáp ứng yêu cầu kia.
- Khác biệt `->`/`:` ảnh hưởng cách thực thi, nhưng **không ảnh hưởng** quy tắc hằng `case` duy nhất. Dạng `:` trong `switch` expression có thể dùng `yield` để trả kết quả; vẫn không thể lặp hằng.

```java
// Trích đoạn sai trong một phương thức:
String text = switch (code) {
    case 1:
        yield "Một";
    case 1 + 0: // LỖI: vẫn là 1 dù dùng cú pháp ':'
        yield "Lặp một";
    default:
        yield "Khác";
};
```

### 5.3. Phạm vi với các phiên bản Java mới hơn

Java 21 bổ sung `case` pattern và khả năng xử lý `case null` trong `switch` theo quy tắc tương ứng. **Quy tắc không có hai hằng `case` cùng giá trị vẫn giữ nguyên.** Nhãn `case null` và nhãn `default` còn có giới hạn riêng (mỗi loại tối đa một trong một khối). Lỗi một pattern che khuất nhánh phía sau (*dominated label*) là vấn đề khác với lỗi trùng **hằng** `case`; không nên đánh đồng hai loại kiểm tra.

Những ví dụ chương trình chạy được phía trên chỉ sử dụng cú pháp chính thức từ **Java 14**, nên vẫn phù hợp khi biên dịch bằng `--release 14`.

## 6. Quy trình rà soát khi gặp `duplicate case label`

1. Xác định chính xác **khối `switch`** chứa lỗi; không gom nhãn từ các khối `switch` khác.
2. Liệt kê mọi hằng trong tất cả nhãn `case`, kể cả các mục phân tách bằng dấu phẩy.
3. Tính giá trị các biểu thức hằng (`1 + 1`, `0xA`, chuỗi ghép, `static final` đủ điều kiện, enum constant) và tìm **giá trị lặp**, không chỉ tên lặp.
4. Giữ một nhánh cho mỗi giá trị. Gộp nhãn **chỉ khi các giá trị khác nhau** cùng xử lý một kết quả; nếu cần hành vi khác nhau thì cần mã đầu vào khác nhau hoặc phân nhánh điều kiện trong thân nhánh.
5. Biên dịch lại bằng `javac`. Khi dự án yêu cầu tương thích Java 14, ưu tiên kiểm tra thêm với `javac --release 14` trên một JDK hỗ trợ tùy chọn đó.

### Tự kiểm tra nhanh

Với `static final int LIMIT = 6;`, các cặp sau có trùng trong cùng một `switch (int)` không?

| Các nhãn | Đánh giá | Lý do |
| --- | --- | --- |
| `case 6` và `case LIMIT` | **Trùng** | `LIMIT` là hằng `6` |
| `case 2 + 4` và `case 0x6` | **Trùng** | Cả hai là `6` |
| `case 5, 6` và `case 7` | **Hợp lệ về tính duy nhất** | Ba giá trị `5`, `6`, `7` khác nhau |
| `case "a"` và `case "A"` trong `switch (String)` | **Không trùng** | Phân biệt hoa/thường |

Khi đánh giá một `switch` expression hoàn chỉnh, còn cần kiểm tra kiểu nhãn tương thích với kiểu selector và tính bao phủ tất cả trường hợp.

## Tài liệu chuẩn còn áp dụng

- [Java Language Specification, `14.11.1 — Switch Blocks (Java SE 21)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): quy định không hai `case` constant cùng giá trị trong một khối `switch`, và giới hạn `default`/`null`.
- [Java Language Specification, `15.29 — Constant Expressions (Java SE 21)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29): biểu thức hằng được phép dùng trong nhãn `case`.
- [Oracle Java 14 — Switch Expressions](https://docs.oracle.com/en/java/javase/14/language/switch-expressions.html): cú pháp `->`, `yield` và yêu cầu bao phủ của `switch` expression.
