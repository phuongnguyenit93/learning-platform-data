# Giới hạn của char và String.length()

## 1. Hai công cụ hữu ích, nhưng không phải mô hình đầy đủ của “một ký tự”

`char` và `String.length()` xuất hiện rất sớm khi học Java. Với các chuỗi như `"Java"` hoặc `"123"`, ta dễ hình thành hai giả định:

- Một `char` luôn chứa trọn một ký tự người dùng nhìn thấy.
- `length()` luôn trả số ký tự người dùng nhìn thấy.

Hai giả định này chỉ tình cờ đúng với một số dữ liệu đơn giản. Khi xử lý tên có dấu tổ hợp, chữ ngoài vùng BMP hoặc emoji, cần hiểu đúng đơn vị của API.

Quy tắc nền tảng:

> `char` chứa một đơn vị mã UTF-16; `String.length()` đếm số đơn vị mã UTF-16 trong chuỗi.

Chúng không bị “lỗi Unicode”. Chúng hoạt động theo hợp đồng của mình; lỗi xảy ra khi chương trình dùng hợp đồng ấy cho một yêu cầu có đơn vị khác.

Bài dùng Java 17 trở lên. Các quy tắc về kiểu `char`, chỉ số chuỗi và API theo mã Unicode dưới đây vẫn được sử dụng trong Java hiện nay.

## 2. Giới hạn biểu diễn của char

### 2.1. char là một giá trị 16 bit không dấu

Miền giá trị của `char` là từ 0 đến 65.535, tương ứng `0x0000` đến `0xFFFF`. Đây là định nghĩa kiểu dữ liệu trong [JLS: Integral Types and Values](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.1).

Miền đó đủ chứa một đơn vị UTF-16. Nó không đủ chứa mọi mã Unicode, vì không gian mã Unicode mở rộng đến U+10FFFF.

Trong văn bản UTF-16 hợp lệ:

- Một giá trị vô hướng Unicode trong vùng BMP, ngoài dải surrogate, được biểu diễn bằng một `char`.
- Một giá trị ngoài BMP cần hai `char` tạo thành cặp surrogate.

Ví dụ, chữ `A` có mã U+0041 nên vừa một `char`. Emoji U+1F600 cần cặp `D83D DE00`.

Đừng nhầm hai giá trị surrogate thành hai ký tự độc lập của emoji. Chúng là hai phần của một cách biểu diễn.

### 2.2. Đổi sang Character hoặc char[] không tự đổi đơn vị

`Character` là lớp bọc của một `char`; nó không mở rộng phạm vi để chứa một mã ngoài BMP.

`toCharArray()` tạo mảng các đơn vị UTF-16. Với một emoji ngoài BMP, mảng có hai phần tử. Duyệt từng phần tử của mảng vẫn là duyệt từng đơn vị, không phải duyệt từng mã Unicode hoàn chỉnh.

Nếu cần giữ một mã Unicode, dùng `int`. Nếu cần giữ một đoạn văn bản bất kỳ, dùng `String` hoặc kiểu chuỗi phù hợp, thay vì cố nhét toàn bộ đoạn vào một `char`.

### 2.3. Ép kiểu không phải là mã hóa UTF-16

Đây là điểm rất dễ sai:

```java
int point = 0x1F600;
char wrong = (char) point;
```

Đoạn minh họa trên biên dịch được, nhưng `wrong` nhận `0xF600`: phần giá trị còn lại sau phép thu hẹp xuống 16 bit. Nó không nhận cặp surrogate và không đại diện U+1F600.

Muốn tạo văn bản từ một mã Unicode hợp lệ, có thể dùng:

```java
int point = 0x1F600;
String text = new String(Character.toChars(point));
```

Hoặc khi đang ghép văn bản:

```java
StringBuilder builder = new StringBuilder();
builder.appendCodePoint(0x1F600);
String text = builder.toString();
```

Các đoạn này minh họa bên trong một phương thức. Ép kiểu số và chuyển một mã Unicode thành các đơn vị UTF-16 là hai thao tác khác nhau.

## 3. charAt có thể chỉ trả một nửa, và overload nhận char có giới hạn tương ứng

Một số mã Unicode ngoài BMP là chữ cái, không chỉ là emoji. Ví dụ U+10400 là một chữ thuộc hệ chữ Deseret.

Nếu gọi `Character.isLetter(text.charAt(0))`, giá trị được kiểm tra có thể chỉ là phần cao của cặp surrogate. Bộ phân loại không thể suy ra toàn bộ chữ chỉ từ nửa đó.

Lưu chương trình sau thành `CharBoundaryDemo.java`:

```java
public class CharBoundaryDemo {
    public static void main(String[] args) {
        int point = 0x1F600;
        char narrowed = (char) point;
        String smile = new String(Character.toChars(point));

        System.out.println("charMax=" + (int) Character.MAX_VALUE);
        System.out.printf("original=U+%X%n", point);
        System.out.printf("narrowed=%04X%n", (int) narrowed);
        System.out.println("smileUnits=" + smile.length());
        System.out.println("firstIsHigh="
                + Character.isHighSurrogate(smile.charAt(0)));
        System.out.println("secondIsLow="
                + Character.isLowSurrogate(smile.charAt(1)));

        String letter = new String(Character.toChars(0x10400));
        System.out.println("letterUnits=" + letter.length());
        System.out.println("letterByChar="
                + Character.isLetter(letter.charAt(0)));
        System.out.println("letterByCodePoint="
                + Character.isLetter(letter.codePointAt(0)));
        System.out.println("lettersFromChars="
                + letter.chars().filter(Character::isLetter).count());
        System.out.println("lettersFromCodePoints="
                + letter.codePoints().filter(Character::isLetter).count());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 CharBoundaryDemo.java
java CharBoundaryDemo
```

Stdout:

```text
charMax=65535
original=U+1F600
narrowed=F600
smileUnits=2
firstIsHigh=true
secondIsLow=true
letterUnits=2
letterByChar=false
letterByCodePoint=true
lettersFromChars=0
lettersFromCodePoints=1
```

Hai dòng cuối cho thấy một giới hạn ít rõ ràng hơn: `chars()` trả một luồng `int`, nhưng các giá trị trong luồng vẫn là từng đơn vị UTF-16 được mở rộng thành số nguyên. Kiểu phần tử là `int` không làm luồng đó trở thành luồng mã Unicode. Dùng `codePoints()` khi cần ghép cặp surrogate để xử lý mã ngoài BMP.

Hành vi của các overload nhận `char` và `int` được giải thích trong [Character: Unicode Character Representations](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html).

## 4. String.length() đo gì?

`String.length()` trả về một `int` là số đơn vị UTF-16 trong chuỗi. Chỉ số dùng với `charAt` và `substring` cũng tính theo các đơn vị đó. Đây là hợp đồng tại [Java API: String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#length()).

Ví dụ:

| Nội dung | length() | Số mã Unicode | Nhận xét |
| --- | ---: | ---: | --- |
| Chuỗi rỗng | 0 | 0 | Không có đơn vị nào |
| `ABC` | 3 | 3 | Các mã ASCII đều vừa một đơn vị |
| `é` dạng U+00E9 | 1 | 1 | Một mã trong BMP |
| `e` + dấu sắc U+0301 | 2 | 2 | Thường được nhìn như một chữ có dấu |
| U+1F600 | 2 | 1 | Một mã ngoài BMP |
| Hai emoji U+1F600 liên tiếp | 4 | 2 | Mỗi mã cần hai đơn vị |

Ngay cả khi `length()` trùng số mã Unicode, nó vẫn chưa chắc trùng số cụm ký tự người dùng cảm nhận. Chữ cơ sở kèm dấu tổ hợp là ví dụ cụ thể.

### 4.1. Không phải số byte hoặc độ rộng hiển thị

`length()` không biết ứng dụng sẽ mã hóa chuỗi sang UTF-8, UTF-16 hay bộ mã khác khi xuất ra tệp hoặc mạng. Muốn kiểm tra số byte UTF-8, phải xét kết quả mã hóa UTF-8.

Nó cũng không biết phông chữ, kích thước chữ hoặc quy tắc dựng emoji. Vì vậy, không thể dùng `length()` như một phép đo số pixel hay số cột terminal.

Lưu chương trình sau thành `LengthContractDemo.java`:

```java
import java.nio.charset.StandardCharsets;

public class LengthContractDemo {
    private static void show(String name, String text) {
        System.out.println(name
                + ": units=" + text.length()
                + ", codePoints="
                + text.codePointCount(0, text.length())
                + ", utf8Bytes="
                + text.getBytes(StandardCharsets.UTF_8).length);
    }

    public static void main(String[] args) {
        show("empty", "");
        show("ASCII", "ABC");
        show("precomposed", "\u00E9");
        show("decomposed", "e\u0301");
        show("smile", "\uD83D\uDE00");
        show("two-smiles", "\uD83D\uDE00\uD83D\uDE00");
        show("mixed", "A\uD83D\uDE00B");
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 LengthContractDemo.java
java LengthContractDemo
```

Stdout:

```text
empty: units=0, codePoints=0, utf8Bytes=0
ASCII: units=3, codePoints=3, utf8Bytes=3
precomposed: units=1, codePoints=1, utf8Bytes=2
decomposed: units=2, codePoints=2, utf8Bytes=3
smile: units=2, codePoints=1, utf8Bytes=4
two-smiles: units=4, codePoints=2, utf8Bytes=8
mixed: units=4, codePoints=3, utf8Bytes=6
```

Với `"A" + U+1F600 + "B"`, ba mã Unicode trở thành bốn đơn vị UTF-16 và sáu byte UTF-8. Cả ba con số đều đúng, nhưng trả lời ba câu hỏi khác nhau.

### 4.2. Không phải công thức đo bộ nhớ heap

Một `char` có 16 bit không có nghĩa mọi đối tượng `String` luôn chiếm đúng `length() * 2` byte heap. Cách lưu bên trong JDK, phần thông tin của đối tượng và căn chỉnh bộ nhớ là các yếu tố khác.

Dùng `length()` để nói về độ dài theo API. Nếu cần phân tích bộ nhớ thực tế, dùng công cụ đo thích hợp với JVM đang chạy.

Việc kết quả có kiểu `int` cũng không bảo đảm có thể cấp phát một chuỗi lớn tùy ý đến giới hạn `int`. Giới hạn triển khai và bộ nhớ khả dụng có thể khiến cấp phát thất bại sớm hơn.

## 5. Lỗi cắt chuỗi: chỉ số hợp lệ nhưng nội dung bị tách

Giả sử yêu cầu là giữ hai mã Unicode đầu của `A + U+1F600 + B`.

Cách viết `substring(0, 2)` giữ hai đơn vị UTF-16: chữ `A` và phần cao của emoji. Đây không phải hai mã Unicode nguyên vẹn.

Một giải pháp theo mã Unicode là đổi số lượng mã cần giữ thành ranh giới UTF-16 trước khi lấy đoạn.

Lưu chương trình sau thành `CodePointPrefixDemo.java`:

```java
import java.util.Objects;

public class CodePointPrefixDemo {
    private static String prefixByCodePoints(String text, int limit) {
        Objects.requireNonNull(text, "text");
        if (limit < 0) {
            throw new IllegalArgumentException("limit must be non-negative");
        }

        int total = text.codePointCount(0, text.length());
        int keep = Math.min(limit, total);
        int end = text.offsetByCodePoints(0, keep);
        return text.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        String broken = text.substring(0, 2);
        String whole = prefixByCodePoints(text, 2);

        System.out.println("brokenUnits=" + broken.length());
        System.out.println("brokenEndsWithHigh="
                + Character.isHighSurrogate(
                        broken.charAt(broken.length() - 1)));
        System.out.println("wholeUnits=" + whole.length());
        System.out.println("wholeCodePoints="
                + whole.codePointCount(0, whole.length()));
        System.out.println("wholeEndsWithLow="
                + Character.isLowSurrogate(
                        whole.charAt(whole.length() - 1)));
        System.out.println("zero=[" + prefixByCodePoints(text, 0) + "]");
        System.out.println("oversizeEqual="
                + text.equals(prefixByCodePoints(text, 99)));

        String combining = "e\u0301";
        String firstPoint = prefixByCodePoints(combining, 1);
        System.out.println("firstPoint=[" + firstPoint + "]");
        System.out.println("combiningUnits=" + combining.length());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 CodePointPrefixDemo.java
java CodePointPrefixDemo
```

Stdout:

```text
brokenUnits=2
brokenEndsWithHigh=true
wholeUnits=3
wholeCodePoints=2
wholeEndsWithLow=true
zero=[]
oversizeEqual=true
firstPoint=[e]
combiningUnits=2
```

`whole` kết thúc bằng phần thấp vì cặp surrogate được giữ nguyên sau chữ `A`. Một phần thấp đứng cuối tự nó không chứng minh dữ liệu sai; điều cần xét là nó có phần cao tương ứng đứng trước hay không.

Hàm đã đáp ứng hợp đồng “giữ tối đa một số mã Unicode”. Nó không đáp ứng hợp đồng “giữ tối đa một số ký tự người dùng cảm nhận”: với `e + dấu sắc`, giữ một mã chỉ còn `e` và làm mất dấu.

Nếu yêu cầu là giới hạn theo cụm ký tự, cần phân đoạn cụm, chẳng hạn dùng hỗ trợ `\X` trong [Pattern](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Pattern.html) trên JDK phù hợp. Đừng đổi tên hàm thành “safe substring” rồi ngầm cho rằng một cách cắt đã đúng cho mọi yêu cầu.

## 6. Cách duyệt đúng phụ thuộc đơn vị cần xử lý

### 6.1. Khi cần duyệt đơn vị UTF-16

Vòng lặp theo `char` vẫn phù hợp khi đang kiểm tra cấu tạo UTF-16 hoặc xử lý một giao thức chỉ cho phép ASCII:

```java
for (int i = 0; i < text.length(); i++) {
    char unit = text.charAt(i);
    // Xử lý một đơn vị UTF-16.
}
```

Đây là đoạn minh họa với biến `text` đã được khai báo. Không cần thay mọi vòng lặp `char` nếu hợp đồng đầu vào và mục tiêu thực sự dùng đơn vị này.

### 6.2. Khi cần duyệt mã Unicode

Có thể dùng:

```java
for (int offset = 0; offset < text.length();) {
    int point = text.codePointAt(offset);
    // Xử lý mã point.
    offset += Character.charCount(point);
}
```

Hoặc dùng `text.codePoints()` khi cách xử lý phù hợp với luồng số nguyên. Chỉ số `offset` vẫn là chỉ số UTF-16; bước tăng được điều chỉnh theo số đơn vị của mã vừa đọc.

### 6.3. Khi cần thao tác như trình biên tập văn bản

Việc di chuyển con trỏ, xóa một ký tự người dùng cảm nhận hoặc rút gọn nhãn thường cần ranh giới cụm ký tự. Một cụm có thể gồm nhiều mã Unicode, đặc biệt với dấu tổ hợp và chuỗi emoji.

Quy tắc phân đoạn có thể thay đổi theo phiên bản Unicode mà thư viện hỗ trợ. Chọn rõ đơn vị ở mức yêu cầu sản phẩm trước khi quyết định API.

## 7. Dữ liệu không hợp lệ vẫn có thể đi qua các phép đếm

Java cho phép tạo một `String` chứa surrogate không ghép cặp. `length()` vẫn đếm các đơn vị đó. `codePointCount` cũng không phải một hàm xác minh toàn bộ tính hợp lệ của UTF-16; surrogate không ghép cặp được tính như một phần tử trong phép đếm.

Vì vậy:

- Không coi `length() > 0` là bằng chứng chuỗi có ít nhất một ký tự hiển thị hợp lệ.
- Không coi `codePointCount` là bước làm sạch dữ liệu.
- Nếu giao tiếp với hệ thống yêu cầu Unicode hợp lệ, cần kiểm tra hoặc chính sách xử lý lỗi rõ ràng tại ranh giới nhận/xuất dữ liệu.

Trong các ví dụ thông thường, dùng chuỗi đầu vào hợp lệ giúp tập trung vào cách chọn đơn vị. Khi xây dựng hàm dùng chung, hãy ghi rõ giả định đó thay vì để tên hàm hứa quá nhiều.

## 8. Chọn cách đo theo hợp đồng

| Câu hỏi thực tế | Cách đo phù hợp |
| --- | --- |
| Chuỗi có bao nhiêu đơn vị mà charAt đánh chỉ số? | `length()` |
| Chuỗi có bao nhiêu mã Unicode? | `codePointCount(0, length())` |
| Có bao nhiêu chữ cái ngoài BMP? | Duyệt mã Unicode rồi dùng overload `Character` nhận `int` |
| Người dùng cảm nhận bao nhiêu ký tự? | Phân đoạn cụm ký tự theo quy tắc đã chọn |
| Văn bản chiếm bao nhiêu byte UTF-8? | Đếm byte sau mã hóa UTF-8 |
| Nhãn có vừa chiều rộng giao diện không? | Đo theo môi trường dựng và phông chữ |

Nếu tài liệu yêu cầu chỉ ghi “tối đa 20 ký tự”, hãy xác định thêm 20 đơn vị UTF-16, 20 mã Unicode hay 20 cụm ký tự. Giới hạn theo byte lại cần ghi rõ bộ mã. Sự rõ ràng này giúp phía giao diện và phía máy chủ kiểm tra cùng một điều.

## 9. Tự kiểm tra

1. `char` có thể chứa số 0x1F600 mà không mất thông tin không?
2. Vì sao `(char) 0x1F600` không tạo ra một emoji?
3. Với `A + U+1F600 + B`, `length()` và số mã Unicode bằng bao nhiêu?
4. `chars()` trả `int`; vậy có tự khắc phục vấn đề surrogate không?
5. Vì sao kiểm tra chữ cái bằng `Character.isLetter(charAt(i))` có thể bỏ sót chữ ngoài BMP?
6. Giữ một mã đầu của `e + U+0301` có giữ được chữ có dấu không?
7. Có thể dùng `length()` thay số byte UTF-8 không?
8. Một hàm đếm mã Unicode có đồng thời xác nhận UTF-16 hợp lệ không?

Đáp án:

1. Không; giá trị đó vượt miền 16 bit của `char`.
2. Phép thu hẹp chỉ giữ phần giá trị 16 bit, không tạo cặp surrogate.
3. Bốn đơn vị UTF-16 và ba mã Unicode.
4. Không; `chars()` vẫn phát từng đơn vị. Dùng `codePoints()` cho mã Unicode.
5. Giá trị `char` có thể chỉ là một nửa của chữ.
6. Không; chỉ giữ `e`, mất dấu sắc.
7. Không; phải xét kết quả mã hóa bằng đúng bộ mã.
8. Không; đó là hai trách nhiệm khác nhau.

Hãy dùng `char` và `length()` khi bài toán thực sự cần đơn vị UTF-16. Khi yêu cầu nói về mã Unicode, cụm ký tự hoặc byte, chuyển sang công cụ tương ứng và đặt tên đơn vị rõ ràng.
