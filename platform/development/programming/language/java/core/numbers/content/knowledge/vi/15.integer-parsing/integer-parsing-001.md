# parseInt, parseLong và các phương thức parse số nguyên tương ứng trong Java

Khi dữ liệu từ form, tệp cấu hình hoặc CSV chứa `"125"`, giá trị đang là `String`. Muốn cộng, so sánh hay lưu thành số, chương trình cần **parse** chuỗi thành primitive phù hợp, đồng thời kiểm tra cú pháp và phạm vi giá trị. Bài nhập môn này tập trung vào các parser **có dấu** của `Byte`, `Short`, `Integer` và `Long`; những biến thể về wrapper, unsigned, prefix và `BigInteger` được triển khai sâu ở các bài kế tiếp.

## 1. Bốn parser signed chính và kiểu trả về

| API | Kiểu primitive | Phạm vi |
| --- | --- | --- |
| `Byte.parseByte("127")` | `byte` | -128 đến 127 |
| `Short.parseShort("32767")` | `short` | -32768 đến 32767 |
| `Integer.parseInt("42")` | `int` | -2147483648 đến 2147483647 |
| `Long.parseLong("3000000000")` | `long` | -9223372036854775808 đến 9223372036854775807 |

Ví dụ trong một phương thức Java:

```java
byte flag = Byte.parseByte("100");
short temperature = Short.parseShort("-120");
int count = Integer.parseInt("125");
long total = Long.parseLong("3000000000");
```

Bốn lời gọi trên trả về **primitive**. Phương thức `Integer.valueOf("42")` trả về wrapper `Integer`, không phải `int`; bài kế tiếp giải thích boxing/unboxing. Đừng chọn parser nhỏ chỉ vì biến nhận rộng hơn:

```java
long valid = Long.parseLong("3000000000");
// long invalid = Integer.parseInt("3000000000");
// Integer.parseInt vẫn ném NumberFormatException trước khi gán cho long.
```

**Chọn kiểu từ miền nghiệp vụ trước khi parse.** Nếu trường có thể lớn hơn `int` nhưng vừa `long`, dùng `Long.parseLong`. Nếu vượt `long`, chọn `BigInteger` khi cần giá trị số học chính xác. Nếu là mã định danh cần giữ số 0 đầu, hãy giữ `String`.

## 2. Cú pháp chuỗi và ký tự không hợp lệ

Các overload chỉ nhận một `String` mặc định parse **decimal**, có thể có một dấu cộng/trừ ASCII ở đầu rồi đến ít nhất một chữ số hợp lệ. Ví dụ:

```java
int a = Integer.parseInt("+42"); // 42
int b = Integer.parseInt("-42"); // -42
int c = Integer.parseInt("-0");  // 0
int d = Integer.parseInt("077"); // 77, không tự chuyển sang hệ 8
```

Parser kiểm tra toàn bộ chuỗi và miền giá trị. Bảng sau cho các input không hợp lệ với `Integer.parseInt(String)`:

| Input | Lý do từ chối |
| --- | --- |
| `""`, `"+"`, `"-"` | Không có chữ số |
| `"12x"`, `"4 2"` | Ký tự không hợp lệ giữa chuỗi |
| `"1.5"`, `"1e3"` | Không phải chuỗi số nguyên decimal |
| `" 42 "` | Không tự bỏ khoảng trắng |
| `"1_000"`, `"42L"` | Ký hiệu literal thuộc mã Java, không thuộc parser chuỗi |
| `"0x2A"` | Không tự nhận prefix hex |
| `"2147483648"` | Vượt `Integer.MAX_VALUE` |

Java có thể chấp nhận một số chữ số Unicode qua `Character.digit`. Nếu giao thức yêu cầu ASCII `0..9`, kiểm tra ASCII riêng. Việc gọi `strip()` trước parser chỉ phù hợp khi chính sách dữ liệu cho phép bỏ khoảng trắng ngoài. Các bài sau phân tích đầy đủ Unicode, `trim`/`strip`, lỗi `NumberFormatException` và literal so với String.

## 3. Cơ số là tham số, không phải prefix

Các parser có overload `parse...(String, int radix)` hỗ trợ radix từ 2 đến 36:

```java
int binary = Integer.parseInt("101101", 2); // 45
int octal = Integer.parseInt("77", 8);      // 63
int hex = Integer.parseInt("FF", 16);      // 255
long limit = Long.parseLong("7FFFFFFFFFFFFFFF",16); // Long.MAX_VALUE
```

`Integer.parseInt("0xFF", 16)` ném `NumberFormatException`: `x` không phải chữ số hex hợp lệ trong API này. Nếu định dạng input quy định prefix hex hoặc số 0 đầu mang nghĩa octal, hãy đọc bài `decode` để chọn parser thích hợp. Radix không tăng kích thước số nguyên mà kiểu đích có thể chứa.

## 4. Lỗi parse khác tràn phép toán

`NumberFormatException` phát sinh với chuỗi sai, radix sai hoặc số vượt miền. Parser từ chối thay vì âm thầm tràn vòng như một phép cộng kiểu `int`:

```java
int max = Integer.parseInt("2147483647");  // Thành công.
// Integer.parseInt("2147483648");         // NumberFormatException.
int wrapped = Integer.MAX_VALUE + 1;       // Integer.MIN_VALUE.
```

Khi nhận dữ liệu từ người dùng, không nên bắt mọi exception rồi trả 0, vì `"0"` là giá trị hợp lệ. Có thể bắt riêng `NumberFormatException` và trả trạng thái lỗi hoặc thông báo validation. Một số nghiệp vụ như số lượng dương còn cần kiểm tra `n > 0` sau khi parse thành công.

## 5. Chương trình Java 17 chạy độc lập

Lưu thành `SignedParsingBasics.java`:

```java
public class SignedParsingBasics {
    static void invalid(String text) {
        try {
            Integer.parseInt(text);
            System.out.println(text + "=UNEXPECTED");
        } catch (NumberFormatException ex) {
            System.out.println(text + "=INVALID");
        }
    }

    public static void main(String[] args) {
        System.out.println("byte=" + Byte.parseByte("127"));
        System.out.println("short=" + Short.parseShort("-32768"));
        System.out.println("int=" + Integer.parseInt("+42"));
        System.out.println("long=" + Long.parseLong("3000000000"));
        System.out.println("binary=" + Integer.parseInt("101101", 2));
        System.out.println("hex=" + Integer.parseInt("FF", 16));
        System.out.println("decimalZero=" + Integer.parseInt("077"));
        invalid("2147483648");
        invalid("1_000");
        invalid(" 42 ");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SignedParsingBasics.java
java SignedParsingBasics
```

Kết quả:

```text
byte=127
short=-32768
int=42
long=3000000000
binary=45
hex=255
decimalZero=77
2147483648=INVALID
1_000=INVALID
 42 =INVALID
```

Ba dòng `INVALID` do chương trình tự bắt đúng loại exception; chúng không phụ thuộc thông điệp ngoại lệ của JDK.

## 6. Tự kiểm tra

1. Vì sao `Integer.parseInt("3000000000")` lỗi, còn `Long.parseLong("3000000000")` chạy được?
2. `Byte.parseByte("128")` có tự tràn vòng thành -128 không?
3. `Integer.parseInt("077")` cho 77 hay 63? Vì sao?
4. Phân biệt `Integer.parseInt("FF",16)` và `Integer.parseInt("0xFF",16)`.
5. Có nên chuyển mã định danh `"00042"` thành số nguyên để lưu không?

**Ghi nhớ:** chọn primitive theo miền cần hỗ trợ; xác định radix, dấu, chữ số, giới hạn và cách báo lỗi. Các bài kế tiếp đào sâu từng khía cạnh thay vì coi một phương thức parse là đủ cho mọi định dạng.

**Tài liệu chuẩn:** [Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html), [Long](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html), [Byte](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html), [Short](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Short.html).
