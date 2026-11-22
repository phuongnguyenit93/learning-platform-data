# Các phương thức Character nhận đối số int

Khi phân loại hoặc chuyển đổi một ký tự Unicode trong Java, kiểu tham số ảnh hưởng đến dữ liệu bạn đang đưa vào. Phiên bản nhận `char` chỉ nhận được một đơn vị mã UTF-16; phiên bản nhận `int` có thể nhận trọn một điểm mã, kể cả ký tự bổ sung ngoài BMP.

Bài này giúp bạn chọn đúng phương thức, lấy đúng đầu vào từ chuỗi và hiểu giới hạn của việc xử lý từng điểm mã.

## 1. Vì sao int cần thiết?

Một điểm mã có thể lớn hơn `0xFFFF` nên không chứa trọn trong `char`. Ví dụ `U+10400` là một chữ hoa trong hệ chữ Deseret. Trong chuỗi Java, nó cần một cặp surrogate.

Nếu lấy hai phần bằng `charAt` rồi hỏi từng phần “có phải chữ cái không?”, bạn đang kiểm tra các đơn vị surrogate, không kiểm tra chữ Deseret ban đầu. Hãy lấy điểm mã bằng `codePointAt` hoặc `codePoints()` rồi gọi phiên bản nhận `int`. [Character: biểu diễn Unicode và hỗ trợ ký tự bổ sung](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html)

Có hai lỗi khác nhau cần tránh:

- **Ép điểm mã xuống char:** làm mất các bit cao.
- **Mở rộng một char lên int:** giữ được giá trị đơn vị mã đó, nhưng không tự ghép nó với đơn vị kế tiếp.

Ví dụ:

```java
int cp = text.codePointAt(index);
boolean letter = Character.isLetter(cp);
```

Đây là đoạn minh họa trong phương thức; `index` phải trỏ vào đầu điểm mã cần đọc trong biến `text` không rỗng.

Không thay dòng đầu bằng `int cp = text.charAt(index)` rồi cho rằng đầu vào đã trở thành một điểm mã đầy đủ. Kiểu `int` là khả năng chứa giá trị, không phải bằng chứng dữ liệu đã được giải mã đúng.

## 2. Các nhóm phương thức thường dùng

| Nhóm | Ví dụ nhận int | Mục đích |
| --- | --- | --- |
| Phân loại chữ và số | `isLetter`, `isDigit`, `isLetterOrDigit`, `isAlphabetic` | Kiểm tra thuộc tính Unicode của một điểm mã |
| Chữ hoa và chữ thường | `isUpperCase`, `isLowerCase`, `isTitleCase` | Kiểm tra dạng chữ |
| Chuyển dạng chữ | `toUpperCase`, `toLowerCase`, `toTitleCase` | Trả về một điểm mã |
| Khoảng trắng và điều khiển | `isWhitespace`, `isSpaceChar`, `isISOControl` | Kiểm tra theo định nghĩa tương ứng |
| Giá trị số | `digit(cp, radix)`, `getNumericValue(cp)` | Lấy giá trị số, với hai hợp đồng khác nhau |
| Thành phần định danh | `isJavaIdentifierStart`, `isJavaIdentifierPart` | Kiểm tra vị trí đầu hoặc phần sau của định danh Java |
| Thuộc tính khác | `getType`, `getDirectionality`, `isDefined`, `getName` | Tra cứu phân loại, hướng, trạng thái định nghĩa hoặc tên |
| Miền và biểu diễn | `isValidCodePoint`, `isSupplementaryCodePoint`, `charCount`, `toChars` | Kiểm tra phạm vi hoặc chuyển biểu diễn |

Đây là bảng định hướng, không phải danh sách mọi phương thức. Nên đọc hợp đồng của phương thức được chọn: một hàm trả `boolean`, một hàm trả điểm mã, hàm khác trả giá trị số hoặc tên.

Các phiên bản `char` vẫn có ích khi bài toán thật sự xử lý một đơn vị mã hoặc dữ liệu đã biết nằm trong BMP. Với văn bản Unicode tổng quát, hãy ưu tiên đường xử lý điểm mã.

## 3. Chọn thuộc tính theo ý nghĩa, không theo tên gần giống

### isLetter và isAlphabetic

`isLetter` nhận diện nhóm chữ cái theo phân loại của Unicode. `isAlphabetic` có phạm vi thuộc tính khác, có thể bao gồm thêm các trường hợp Unicode xem là alphabetic. Không mặc định hai hàm luôn cho cùng kết quả.

Một chữ cái không nhất thiết có dạng hoa và thường. Vì thế `isLetter(cp)` không thể thay bằng `isUpperCase(cp) || isLowerCase(cp)`.

### isDigit, digit và getNumericValue

Ba câu hỏi khác nhau:

- `isDigit(cp)`: đây có phải chữ số thập phân theo Unicode?
- `digit(cp, radix)`: giá trị chữ số trong cơ số yêu cầu là bao nhiêu? Trả -1 khi không phù hợp.
- `getNumericValue(cp)`: điểm mã mang giá trị số nào theo hợp đồng của hàm?

Chẳng hạn, ký hiệu số La Mã XII có thể mang giá trị 12 mà `isDigit` vẫn là `false`. Đừng dùng `getNumericValue` như một phép phân tích chuỗi số nguyên; nó xử lý từng điểm mã. Hàm trả -1 khi không có giá trị số, -2 khi giá trị số không biểu diễn được bằng một số nguyên không âm.

Nếu trường dữ liệu chỉ chấp nhận ASCII `0–9`, hãy kiểm tra đúng khoảng ấy. `isDigit` chấp nhận nhiều chữ số Unicode hơn.

### isWhitespace và isSpaceChar

Hai hàm có định nghĩa khác nhau. Khoảng trắng không ngắt `U+00A0` (NO-BREAK SPACE, NBSP) là ví dụ: `isWhitespace` trả `false` nhưng `isSpaceChar` trả `true`. Chọn theo quy tắc dữ liệu; không suy từ tên gọi rằng chúng tương đương.

## 4. Chương trình chạy đầy đủ

Ví dụ quan sát chữ bổ sung, chữ số bổ sung, số La Mã, NBSP và giới hạn khi đổi chữ hoa.

Lưu thành **CharacterIntDemo.java**:

```java
import java.util.Locale;

public class CharacterIntDemo {
    public static void main(String[] args) {
        int upper = 0x10400;
        String letter = new String(Character.toChars(upper));
        int lower = Character.toLowerCase(upper);

        System.out.println("point is letter=" + Character.isLetter(upper));
        System.out.println("first unit is letter="
                + Character.isLetter(letter.charAt(0)));
        System.out.println("second unit is letter="
                + Character.isLetter(letter.charAt(1)));
        System.out.printf("lowercase=U+%X%n", lower);
        System.out.println("lowercase check=" + Character.isLowerCase(lower));

        long unitLetters = letter.chars().filter(Character::isLetter).count();
        long pointLetters = letter.codePoints().filter(Character::isLetter).count();
        System.out.println("letters via chars=" + unitLetters);
        System.out.println("letters via codePoints=" + pointLetters);

        int zero = 0x1D7D8;
        System.out.println("supplementary zero is digit="
                + Character.isDigit(zero));
        System.out.println("digit value=" + Character.digit(zero, 10));

        int romanTwelve = 0x216B;
        System.out.println("Roman XII is digit=" + Character.isDigit(romanTwelve));
        System.out.println("Roman XII numeric value="
                + Character.getNumericValue(romanTwelve));

        int nbsp = 0x00A0;
        System.out.println("NBSP whitespace=" + Character.isWhitespace(nbsp));
        System.out.println("NBSP space char=" + Character.isSpaceChar(nbsp));

        int sharpS = 0x00DF;
        System.out.printf("sharp s point uppercase=U+%04X%n",
                Character.toUpperCase(sharpS));
        String sharpText = new String(Character.toChars(sharpS));
        System.out.println("sharp s string uppercase="
                + sharpText.toUpperCase(Locale.ROOT));

        StringBuilder result = new StringBuilder();
        result.appendCodePoint(lower);
        System.out.println("appended units=" + result.length());
        System.out.printf("appended point=U+%X%n", result.codePointAt(0));
    }
}
```

Chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 CharacterIntDemo.java
java CharacterIntDemo
```

Stdout:

```text
point is letter=true
first unit is letter=false
second unit is letter=false
lowercase=U+10428
lowercase check=true
letters via chars=0
letters via codePoints=1
supplementary zero is digit=true
digit value=0
Roman XII is digit=false
Roman XII numeric value=12
NBSP whitespace=false
NBSP space char=true
sharp s point uppercase=U+00DF
sharp s string uppercase=SS
appended units=2
appended point=U+10428
```

Các chữ và số trong ví dụ được tạo từ giá trị điểm mã, nên không cần phông chữ terminal hỗ trợ Deseret hoặc ký hiệu toán học.

Hai dòng về phần đầu/phần sau cho thấy việc kiểm tra riêng từng surrogate bỏ lỡ chữ thật. Dòng `lowercase=U+10428` cho thấy phiên bản nhận `int` giữ trọn kết quả bổ sung thay vì ép về một `char`.

## 5. chars() trả int nhưng vẫn có thể là sai đơn vị

Cả `chars()` và `codePoints()` đều trả luồng số nguyên. Điểm khác biệt là **giá trị mỗi phần tử**:

- `chars()` đưa ra từng đơn vị mã `char` dưới dạng `int`.
- `codePoints()` kết hợp cặp surrogate hợp lệ thành điểm mã.

[Tài liệu CharSequence: chars và codePoints](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/CharSequence.html)

Với một chữ Deseret duy nhất, chương trình nhận:

```text
letters via chars=0
letters via codePoints=1
```

Dù biểu thức `filter(Character::isLetter)` chọn phiên bản nhận `int`, dữ liệu từ `chars()` vẫn là hai surrogate. Chỉ đổi chữ ký hàm không thể sửa một nguồn đầu vào sai đơn vị.

Khi cần xử lý chuỗi theo điểm mã, đường đi điển hình là:

```java
long letters = text.codePoints()
        .filter(Character::isLetter)
        .count();
```

Đây là đoạn minh họa với biến `text` đã có. Nó đếm điểm mã được phân loại là chữ cái, không đếm cụm ký tự hiển thị và không xác thực toàn bộ chính sách đầu vào.

Nếu chuỗi chứa surrogate rời, `codePoints()` không tự sửa hoặc từ chối chúng. Cần kiểm tra riêng nếu hợp đồng yêu cầu dữ liệu UTF-16 hợp lệ.

## 6. Chuyển hoa/thường: một điểm mã khác với toàn chuỗi

`Character.toUpperCase(int)` và `toLowerCase(int)` trả một `int`, tức chỉ có chỗ cho một điểm mã. Chúng không thực hiện được phép chuyển cần nhiều điểm mã, phụ thuộc ngữ cảnh hoặc ngôn ngữ như API toàn chuỗi. [Tài liệu Character.toUpperCase](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#toUpperCase(int))

Ví dụ trong chương trình:

```text
Character.toUpperCase(U+00DF) → U+00DF
String.toUpperCase(Locale.ROOT) với ß → SS
```

`String.toUpperCase(Locale)` có thể làm chiều dài kết quả thay đổi và cho phép chọn locale. [Tài liệu String.toUpperCase](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#toUpperCase(java.util.Locale))

Chọn theo bài toán:

- Chuyển riêng một điểm mã theo ánh xạ đơn giản: dùng `Character`.
- Chuyển văn bản thành chữ hoa/thường theo quy tắc ngôn ngữ hoặc toàn chuỗi: dùng API `String` với locale phù hợp.
- Dùng `Locale.ROOT` khi chủ đích là xử lý văn bản trung lập về ngôn ngữ; không coi nó là lựa chọn mặc định cho mọi nội dung người dùng.

Không ánh xạ từng điểm mã bằng `Character::toUpperCase` rồi khẳng định kết quả tương đương mọi trường hợp của `String.toUpperCase(Locale)`.

## 7. Giữ kết quả int đúng cách

Các phương thức chuyển dạng chữ nhận `int` thường trả lại điểm mã `int`. Để đưa điểm mã ấy vào chuỗi:

```java
StringBuilder result = new StringBuilder();
result.appendCodePoint(cp);
```

Hoặc:

```java
String result = new String(Character.toChars(cp));
```

Các đoạn trên đặt trong phương thức, với `cp` đã được xác thực theo yêu cầu.

Đừng dùng `append(cp)` nếu mục tiêu là ký tự. Phiên bản `append(int)` ghép biểu diễn số thập phân, còn `appendCodePoint(int)` ghép biểu diễn của điểm mã. Cũng không ép `(char) cp` để “đưa về chữ”; cách đó mất dữ liệu với giá trị bổ sung.

## 8. Xác thực đầu vào và lưu ý phiên bản

**Tham số int không đồng nghĩa mọi int đều là điểm mã hợp lệ.** Khi số đến từ nguồn chưa biết, kiểm tra miền bằng `Character.isValidCodePoint`. Nếu yêu cầu là giá trị vô hướng Unicode, loại thêm vùng surrogate `0xD800–0xDFFF`.

**Đừng giả định mọi phương thức đều ném ngoại lệ với số sai.** Chính sách đầu vào/kết quả của từng phương thức khác nhau; đọc hợp đồng cụ thể.

**Các hàm định danh chỉ kiểm tra thành phần.** Việc một điểm mã được phép đứng đầu hoặc trong định danh chưa đủ để chứng minh một chuỗi là tên Java hợp lệ trong mọi ngữ cảnh; còn thứ tự, từ khóa và các quy tắc ngôn ngữ liên quan.

**Thuộc tính ký tự phụ thuộc dữ liệu Unicode của JDK.** Một điểm mã mới có thể được phân loại khác giữa các JDK dùng phiên bản dữ liệu khác. Khi khả năng nhận diện ký tự mới là yêu cầu, kiểm tra tài liệu `Character` của JDK đích và dùng bộ ví dụ đại diện.

**Không phải mọi API nhận int đều có cùng phiên bản tối thiểu.** Chẳng hạn các hàm `isEmoji(int)` và `isEmojiPresentation(int)` có từ Java 21. Ví dụ chạy đầy đủ trong bài chỉ dùng API có sẵn trên Java 17; nếu bổ sung phương thức mới hơn, hãy nâng yêu cầu biên dịch tương ứng. [Tài liệu Character.isEmoji](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#isEmoji(int))

## 9. Tự kiểm tra

1. Vì sao `Character.isLetter(text.charAt(0))` có thể bỏ lỡ một chữ bổ sung?
2. Vì sao truyền `(int) text.charAt(0)` vẫn chưa giải quyết được vấn đề?
3. Một ký hiệu có giá trị số 12 có bắt buộc làm `isDigit` trả `true` không?
4. Sau `int lower = Character.toLowerCase(cp)`, nên ghép bằng `append(lower)` hay `appendCodePoint(lower)`?

Đối chiếu:

1. Nó chỉ nhận một đơn vị mã của cặp surrogate.
2. Phép ép chỉ mở rộng giá trị một đơn vị mã, không ghép cả cặp.
3. Không; phân loại chữ số thập phân và thuộc tính giá trị số là hai việc khác nhau.
4. Dùng `appendCodePoint` để ghép biểu diễn ký tự của điểm mã.
