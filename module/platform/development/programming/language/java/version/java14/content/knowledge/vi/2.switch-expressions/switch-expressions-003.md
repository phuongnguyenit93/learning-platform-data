# Các kiểu selector và hằng `case` thuộc phạm vi `switch` của Java 14

## 1. Mục tiêu và phạm vi phiên bản

Khi viết `switch (selector)`, **selector** là biểu thức được tính một lần để chọn nhánh xử lý; **nhãn `case`** là các giá trị có thể khớp với kết quả của biểu thức đó. Java 14 đã chuẩn hóa `switch` expression (biểu thức `switch` trả về giá trị), đồng thời vẫn hỗ trợ `switch` statement (câu lệnh `switch`). Cả hai dạng phải tuân thủ cùng những quy tắc về kiểu selector và hằng `case` của **Java 14**.

Bài học tập trung vào quy tắc **khi biên dịch theo Java 14**, chẳng hạn với `javac --release 14`. Đây vẫn là kiến thức cần thiết để hiểu và duy trì mã Java 14 cũng như các nhánh `switch` theo kiểu hằng truyền thống. Các bản Java mới đã mở rộng `switch` (đặc biệt từ Java 21); vì vậy không dùng danh sách giới hạn của Java 14 để khẳng định mọi cú pháp `switch` hiện đại cũng bị giới hạn như vậy.

## 2. Những kiểu selector được Java 14 chấp nhận

| Nhóm | Kiểu của biểu thức trong `switch (...)` | Dạng giá trị ở `case` | Ví dụ |
| --- | --- | --- | --- |
| Số nguyên nguyên thủy | `byte`, `short`, `char`, `int` | Hằng số nguyên/ký tự tương thích với kiểu selector | `case 1`, `case 'A'` |
| Kiểu bao (wrapper) tương ứng | `Byte`, `Short`, `Character`, `Integer` | Hằng số tương thích với kiểu nguyên thủy tương ứng; giá trị wrapper được mở hộp khi so khớp | `case 200` |
| Liệt kê | Một kiểu `enum` cụ thể | Hằng enum thuộc **chính** kiểu đó; trong Java 14 viết tên không kèm tên kiểu | `case RUNNING` |
| Chuỗi | `String` | Hằng chuỗi `String` xác định ở thời điểm biên dịch | `case "OK"` |

**Không hợp lệ làm selector của Java 14:** `long`, `Long`, `float`, `Float`, `double`, `Double`, `boolean`, `Boolean`, `Object` hay kiểu lớp tùy ý. Ví dụ `switch (someLong)` hoặc `switch (someBoolean)` không biên dịch được ở mức ngôn ngữ Java 14. Không suy ra quy tắc này cho mọi phiên bản Java mới: Java 21 đã cho phép nhiều kiểu tham chiếu hơn thông qua pattern matching for `switch`, còn một số mở rộng cho kiểu nguyên thủy ở các bản mới có trạng thái preview tùy phiên bản.

Điểm quan trọng về kết quả so khớp:

- Với số và ký tự, so khớp theo **giá trị** của hằng; `char` có thể so với hằng số nguyên biểu diễn cùng đơn vị mã UTF-16 nếu giá trị hợp lệ cho `char`.
- Với `enum`, so khớp một hằng enum cụ thể, không so sánh tên chuỗi của enum. Mã `case RUNNING` chỉ hợp lệ nếu selector có kiểu enum chứa hằng `RUNNING`.
- Với `String`, so khớp nội dung bằng cơ chế tương đương `String.equals`, **phân biệt chữ hoa/chữ thường**; không phải so sánh tham chiếu bằng `==`.
- Nếu selector là `Byte`, `Short`, `Character`, `Integer`, `String` hoặc `enum` và có giá trị `null`, `switch` của Java 14 ném `NullPointerException` trước khi chạy bất kỳ nhánh nào, kể cả `default`.

## 3. Điều kiện để một giá trị trở thành hằng `case`

### 3.1. Hằng được tính tại thời điểm biên dịch

Đối với selector không phải `enum`, mỗi `case` phải dùng **biểu thức hằng tại thời điểm biên dịch** (compile-time constant expression), đồng thời phải tương thích phép gán với kiểu selector. Những ví dụ điển hình:

- Literal: `case 0`, `case 'B'`, `case "START"`.
- Phép tính hoàn toàn từ hằng: `case 2 + 3` (giá trị 5), `case 'A' + 1` (giá trị 66), `case "JA" + "VA"` (chuỗi `"JAVA"`).
- **Biến hằng** (constant variable) kiểu nguyên thủy hoặc `String`: `final int LIMIT = 10;` hay `static final String READY = "READY";`, với giá trị khởi tạo bằng biểu thức hằng.

Từ khóa `final` **không tự động** biến mọi biến thành hằng biên dịch. `final int x = parseValue();` là giá trị chỉ biết lúc chạy; `static final Integer CODE = 200;` cũng không phải constant variable theo quy tắc của Java vì `Integer` là kiểu tham chiếu khác `String`. Do đó cả hai **không dùng trực tiếp làm `case`** trong Java 14, dù có `final`.

Giá trị đến từ biến thường, tham số phương thức, lời gọi hàm (kể cả lời gọi trả về giá trị cố định), hoặc phép tính cần dữ liệu lúc chạy cũng không đủ điều kiện làm `case`.

### 3.2. Hằng phải tương thích với kiểu selector

Một hằng số nguyên dạng `int` có thể dùng cho selector `byte`, `short` hoặc `char` **nếu giá trị nằm trong miền biểu diễn của kiểu đích** theo quy tắc tương thích phép gán hằng của Java. Ví dụ:

| Selector | Nhãn hợp lệ | Nhãn không hợp lệ và lý do |
| --- | --- | --- |
| `byte b` | `case 127` | `case 128`: vượt miền `byte` |
| `short s` | `case 30000` | `case 40000`: vượt miền `short` |
| `char c` | `case 65`, `case 'A'` (nếu ở hai switch khác nhau) | `case -1`: giá trị âm không biểu diễn bởi `char` |
| `int n` | `case 1 + 2` | `case 3L`: hằng `long` không tương thích với `int` |
| `String text` | `case "a" + "b"` | `case 123`: không phải `String` |
| `Status status` | `case RUNNING` | `case "RUNNING"`: chuỗi không phải hằng enum |

Không được có **hai giá trị case trùng nhau** trong cùng một khối `switch`, kể cả viết dưới biểu thức khác nhau: `case 3` và `case 1 + 2` gây lỗi biên dịch. Tương tự, `case 'A'` và `case 65` trong cùng một `switch (char)` là trùng giá trị.

### 3.3. Riêng đối với `enum`

Trong Java 14, với `enum Status { NEW, RUNNING, DONE }`, nhãn phải là tên hằng enum **không có tiền tố tên kiểu**: `case NEW` hoặc `case RUNNING`. Viết `case Status.RUNNING` không đúng cú pháp nhãn enum được Java 14 chấp nhận. Quy tắc về nhãn enum có thể khác trong các phiên bản Java mới, nên phải xét đúng `--release` khi biên dịch.

## 4. Một ví dụ Java 14 đầy đủ, chạy được

Lưu mã dưới tên `SwitchSelectorDemo.java`:

```java
public class SwitchSelectorDemo {
    enum Status { NEW, RUNNING, DONE }

    static final int SUCCESS_CODE = 200;
    static final String KEYWORD = "java" + "14";

    public static void main(String[] args) {
        byte priority = 2;
        String priorityName = switch (priority) {
            case 1, 2 -> "thấp";
            case 3 -> "cao";
            default -> "khác";
        };

        char letter = 'B';
        String letterGroup = switch (letter) {
            case 'A', 66 -> "A/B"; // 66 là mã của 'B'
            default -> "khác";
        };

        Status status = Status.RUNNING;
        String statusName = switch (status) {
            case NEW -> "mới";
            case RUNNING -> "đang xử lý";
            case DONE -> "xong";
        };

        Integer httpCode = 200;
        String httpMessage = switch (httpCode) {
            case SUCCESS_CODE -> "OK";
            default -> "không rõ";
        };

        String input = "java14";
        String tokenStatus = switch (input) {
            case KEYWORD -> "hợp lệ";
            default -> "khác";
        };

        System.out.println("Mức: " + priorityName);
        System.out.println("Ký tự: " + letterGroup);
        System.out.println("Trạng thái: " + statusName);
        System.out.println("Mã: " + httpMessage);
        System.out.println("Chuỗi: " + tokenStatus);
    }
}
```

Biên dịch bằng JDK hỗ trợ tùy chọn `--release 14` và chạy:

```bash
javac --release 14 SwitchSelectorDemo.java
java SwitchSelectorDemo
```

Kết quả chuẩn:

```text
Mức: thấp
Ký tự: A/B
Trạng thái: đang xử lý
Mã: OK
Chuỗi: hợp lệ
```

Cần quan sát năm điểm:

1. `priority` có kiểu `byte`; hằng `1`, `2`, `3` đều nằm trong miền `byte`. Nhãn `case 1, 2` gộp nhiều giá trị trong một nhánh.
2. `letter` có kiểu `char`; `'A'` và `66` đều là hằng hợp lệ, tương ứng hai ký tự khác nhau.
3. `status` là enum; các nhãn là `NEW`, `RUNNING`, `DONE`, không mang tiền tố `Status.`. Ba nhãn bao phủ toàn bộ enum, nên biểu thức này không cần `default`.
4. `httpCode` là `Integer`, được mở hộp để so với hằng nguyên thủy `SUCCESS_CODE`.
5. `KEYWORD` là hằng chuỗi ghép từ literal ngay lúc biên dịch, nên có thể dùng làm nhãn cho selector `String`.

## 5. Nhãn `case` trong `switch` statement và `switch` expression

Java 14 cho phép cả hai lối viết nhãn dưới đây:

```java
int score = 2;

// Biểu thức: trả về một giá trị
String group = switch (score) {
    case 1, 2 -> "cơ bản";
    case 3 -> "nâng cao";
    default -> "khác";
};

// Câu lệnh: thực hiện tác vụ
switch (score) {
    case 1, 2 -> System.out.println("cơ bản");
    case 3 -> System.out.println("nâng cao");
    default -> System.out.println("khác");
}
```

Cú pháp `case 1, 2 ->` và `case 1, 2:` cho phép nhiều hằng trong một nhãn. Với `->`, chương trình không tự chạy tiếp sang nhánh kế tiếp (không có fall-through ngầm). Cú pháp dùng dấu `:` cũng hợp lệ ở Java 14, nhưng các nhóm câu lệnh có thể chạy tiếp qua nhánh sau nếu không có lệnh chuyển điều khiển thích hợp như `break` ở dạng statement. Trong cùng **một** khối `switch`, không trộn quy tắc `->` và nhóm nhãn `:`.

Khi `switch` là **expression**, nó phải bao phủ mọi giá trị selector có thể xuất hiện. Với enum, liệt kê đủ mọi hằng enum có thể đạt yêu cầu này mà không cần `default`; với số nguyên hoặc `String`, thông thường cần `default`. Nếu nhánh `->` dùng khối lệnh và cần trả về giá trị từ khối, sử dụng `yield`:

```java
int n = -3;
String description = switch (n) {
    case 0 -> "không";
    default -> {
        String sign = n > 0 ? "dương" : "âm";
        yield sign;
    }
};
```

Lưu ý: quy tắc "expression phải bao phủ mọi trường hợp" độc lập với quy tắc "nhãn `case` phải là hằng hợp lệ". Một chương trình có các nhãn đúng kiểu vẫn lỗi biên dịch nếu `switch` expression không đầy đủ.

## 6. `null`, `default` và tính đúng đắn

Ví dụ sau **biên dịch được với Java 14 nhưng ném `NullPointerException` khi chạy**:

```java
String input = null;
String result = switch (input) {
    case "YES" -> "đồng ý";
    default -> "khác";
};
```

`default` chỉ xử lý giá trị selector không khớp các hằng, **không bắt `null`** trong Java 14. `case null` cũng không hợp lệ ở phiên bản này. Khi đầu vào có thể `null`, hãy kiểm tra trước lúc gọi `switch`, chẳng hạn `if (input == null) ...`, hoặc quy định rõ đầu vào không được `null`. Từ Java 21, `switch` với pattern matching được chuẩn hóa và có thể có nhãn `case null`; đó là tính năng của phiên bản mới hơn, không áp dụng khi biên dịch `--release 14`.

Với `switch` statement, `default` có thể vắng mặt; nếu không nhãn nào khớp thì không nhánh nào chạy. Với `switch` expression, phải đủ trường hợp như đã nêu. Trong mã dễ bảo trì, dùng enum khi miền trạng thái hữu hạn và ổn định; dùng `String` khi thật sự xử lý chuỗi đầu vào và lưu ý phân biệt hoa/thường. Không ép chuyển kiểu chỉ để dùng `switch` nếu có thể làm thay đổi giá trị hoặc ý nghĩa dữ liệu.

## 7. Những lỗi thường gặp và cách sửa

| Tình huống | Nguyên nhân | Cách xử lý đúng |
| --- | --- | --- |
| `switch (longValue)` với `long` | Selector không thuộc kiểu được hỗ trợ trong Java 14 | Chọn cách rẽ nhánh khác hoặc chuyển dữ liệu có kiểm tra miền giá trị khi phù hợp |
| `switch (byteValue) { case 128 -> ... }` | Hằng `128` vượt miền `byte` | Dùng hằng đúng miền hoặc điều chỉnh kiểu dữ liệu theo yêu cầu |
| `case getCode()` | Gọi phương thức không phải biểu thức hằng biên dịch | Dùng literal hoặc constant variable hợp lệ; với điều kiện động thì dùng cấu trúc khác |
| `case SOME_INTEGER` với `static final Integer SOME_INTEGER = 1` | Kiểu wrapper `Integer` không tạo constant variable | Dùng `static final int SOME_INTEGER = 1` |
| `case Status.RUNNING` khi selector là `Status` | Nhãn enum có tiền tố không hợp lệ trong Java 14 | Viết `case RUNNING` |
| `case 2` và `case 1 + 1` trong cùng switch | Hai hằng có cùng giá trị | Xóa nhãn trùng hoặc gộp logic cần thiết |
| `case null` trong Java 14 | Java 14 không hỗ trợ nhãn `null` | Kiểm tra `null` trước `switch` |
| `switch` expression thiếu `default` và chưa đủ trường hợp | Biểu thức không bao phủ mọi giá trị | Thêm `default` hoặc liệt kê đầy đủ hằng enum |
| `case "ok"` không bắt chuỗi `"OK"` | So sánh `String` phân biệt hoa/thường | Chuẩn hóa đầu vào có chủ đích hoặc khai báo các nhãn phù hợp |

## 8. Tự kiểm tra

1. `byte b = 127;` với `case 127` và `case 128`: chỉ `127` hợp lệ vì `128` không thể gán cho `byte`.
2. `String s = "Java";` với `case "Ja" + "va"`: hợp lệ vì phép nối literal là hằng biên dịch và cho ra `"Java"`.
3. `enum Level { LOW, HIGH }`; với `switch (level)`: dùng `case LOW`, `case HIGH` trong Java 14. Nếu biểu thức bao phủ cả hai nhãn thì không bắt buộc có `default`.
4. `final int x = getValue();` có dùng `case x` được không? **Không**: biến này có thể chỉ được gán một lần nhưng giá trị không biết khi biên dịch.
5. `switch (Boolean.TRUE)` biên dịch được với `--release 14` không? **Không**: `Boolean` không nằm trong tập selector được Java 14 hỗ trợ.

**Ghi nhớ:** Với Java 14, trước tiên kiểm tra **kiểu của selector**, sau đó kiểm tra từng **hằng `case` có xác định khi biên dịch, đúng kiểu và không trùng giá trị**; cuối cùng kiểm tra **`null` và tính đầy đủ** nếu viết `switch` expression.

### Tài liệu đặc tả

- [Java Language Specification, Java SE 14, §14.11 — Switch Statement](https://docs.oracle.com/javase/specs/jls/se14/html/jls-14.html#jls-14.11): kiểu selector, nhãn case, tính tương thích và so khớp.
- [Java Language Specification, Java SE 14, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se14/html/jls-15.html#jls-15.28): yêu cầu của biểu thức `switch`.
- [Oracle Java SE 21 Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): phân biệt những mở rộng được chuẩn hóa sau Java 14.