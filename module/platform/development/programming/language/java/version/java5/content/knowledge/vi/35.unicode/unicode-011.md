# Kiểm tra phân loại chữ cái, chữ số theo code point

## 1. Phân loại ký tự cần bắt đầu từ đúng đơn vị

Một chương trình có thể cần biết mã vừa đọc là chữ cái, chữ số hay dấu phân cách. Với dữ liệu Unicode, không nên chỉ kiểm tra các khoảng ASCII như `A-Z` nếu yêu cầu chấp nhận chữ của nhiều ngôn ngữ.

Java cung cấp các phương thức trong `Character`:

```java
Character.isLetter(int codePoint)
Character.isDigit(int codePoint)
Character.isLetterOrDigit(int codePoint)
```

Các phương thức trả về `boolean` và kiểm tra một mã Unicode, không kiểm tra cả một chuỗi. Chúng dựa vào thuộc tính Unicode mà JDK hỗ trợ, không đoán theo hình dáng ký tự trên màn hình.

Quy trình thường dùng:

```text
Đọc mã Unicode từ String
          ↓
Giữ kết quả ở kiểu int
          ↓
Gọi phương thức phân loại phù hợp
          ↓
Áp dụng quy tắc của ứng dụng
```

Bước cuối cần được xác định riêng. Một mã được Unicode xếp là chữ cái không có nghĩa nó được phép xuất hiện ở mọi vị trí của mọi loại mã định danh.

Bài dùng Java 17 trở lên và tập trung vào các API hiện hành.

## 2. Ý nghĩa chính xác của ba phép kiểm tra

### 2.1. isLetter: chữ cái theo nhóm Unicode

`Character.isLetter(point)` trả `true` cho các nhóm Unicode:

| Nhóm | Tên hằng trong Character |
| --- | --- |
| Chữ hoa | `UPPERCASE_LETTER` |
| Chữ thường | `LOWERCASE_LETTER` |
| Chữ dạng titlecase | `TITLECASE_LETTER` |
| Chữ bổ trợ | `MODIFIER_LETTER` |
| Chữ thuộc nhóm khác | `OTHER_LETTER` |

Một chữ không nhất thiết có cặp hoa/thường. Chẳng hạn nhiều chữ Hán vẫn là chữ cái theo phép kiểm tra này.

Dấu tổ hợp đứng riêng, dấu cách, gạch dưới và emoji không tự trở thành chữ cái chỉ vì chúng có thể xuất hiện cạnh chữ. Các nhóm của `isLetter` được quy định tại [Character.isLetter(int)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#isLetter(int)).

`isAlphabetic` là một phép kiểm tra có định nghĩa rộng hơn; không thay hai phương thức cho nhau chỉ vì cùng có thể dịch là “thuộc chữ”. Hãy chọn theo hợp đồng cần kiểm tra.

### 2.2. isDigit: chữ số thập phân, không phải mọi ký hiệu số

`Character.isDigit(point)` kiểm tra nhóm `DECIMAL_DIGIT_NUMBER`, thường viết tắt là `Nd`.

Nó chấp nhận nhiều bộ chữ số ngoài ASCII, chẳng hạn:

- `0` đến `9`.
- Chữ số Arabic-Indic như U+0663.
- Chữ số dạng fullwidth như U+FF13.
- Một số bộ chữ số ngoài BMP, chẳng hạn U+1D7D1.

Nhưng ký hiệu số mũ hai U+00B2, phân số một phần hai U+00BD hoặc số La Mã U+216B không thuộc nhóm chữ số thập phân này.

Quy tắc phân loại được mô tả tại [Character.isDigit(int)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#isDigit(int)).

### 2.3. isLetterOrDigit: phép hoặc của hai điều kiện

`Character.isLetterOrDigit(point)` tương đương với:

```java
Character.isLetter(point) || Character.isDigit(point)
```

Nó không tự cho phép dấu cách, gạch dưới, dấu gạch nối hoặc dấu tổ hợp. Nếu ứng dụng cần những thành phần đó, phải bổ sung quy tắc rõ ràng thay vì mặc định “letter or digit” đã bao phủ chúng.

## 3. Đừng dùng giá trị số để thay cho phân loại chữ số

`Character.getNumericValue(point)` trả giá trị số theo một hợp đồng khác. Một ký hiệu có giá trị số có thể vẫn không phải chữ số thập phân.

Ví dụ:

| Mã | Ký hiệu hoặc ý nghĩa | isDigit | getNumericValue |
| --- | --- | --- | ---: |
| U+0033 | `3` | true | 3 |
| U+0663 | Chữ số Arabic-Indic ba | true | 3 |
| U+FF13 | Chữ số fullwidth ba | true | 3 |
| U+1D7D1 | Chữ số ba dạng toán học ngoài BMP | true | 3 |
| U+00B2 | `²` | false | 2 |
| U+00BD | `½` | false | -2 |
| U+216B | `Ⅻ` | false | 12 |
| U+0041 | `A` | false | 10 |

Giá trị `-1` nghĩa là không có giá trị số theo phương thức. Giá trị `-2` nghĩa là có giá trị số nhưng không biểu diễn được bằng một số nguyên không âm phù hợp với hợp đồng trả về, ví dụ phân số.

Java còn gán giá trị 10 đến 35 cho các chữ Latin A-Z, a-z và dạng fullwidth của chúng trong phương thức này. Vì vậy, điều kiện `getNumericValue(point) >= 0` chắc chắn không đồng nghĩa với `isDigit(point)`. Xem [Character.getNumericValue(int)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#getNumericValue(int)).

Nếu đã xác nhận một mã là chữ số thập phân và cần giá trị 0 đến 9, có thể dùng `Character.digit(point, 10)`. Phương thức này có xét cơ số; đừng nhầm nó với việc phân loại hoặc phân tích nguyên một chuỗi số.

## 4. Ví dụ phân loại nhiều loại mã Unicode

Lưu thành `UnicodeClassifyDemo.java`:

```java
public class UnicodeClassifyDemo {
    private static void show(int point) {
        System.out.printf(
                "U+%04X letter=%s digit=%s either=%s numeric=%d%n",
                point,
                Character.isLetter(point),
                Character.isDigit(point),
                Character.isLetterOrDigit(point),
                Character.getNumericValue(point));
    }

    public static void main(String[] args) {
        int[] points = {
                0x0041, 0x1EBF, 0x4E2D, 0x10400,
                0x0033, 0x0663, 0xFF13, 0x1D7D1,
                0x00B2, 0x00BD, 0x216B, 0x0301
        };
        for (int point : points) {
            show(point);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 UnicodeClassifyDemo.java
java UnicodeClassifyDemo
```

Stdout:

```text
U+0041 letter=true digit=false either=true numeric=10
U+1EBF letter=true digit=false either=true numeric=-1
U+4E2D letter=true digit=false either=true numeric=-1
U+10400 letter=true digit=false either=true numeric=-1
U+0033 letter=false digit=true either=true numeric=3
U+0663 letter=false digit=true either=true numeric=3
U+FF13 letter=false digit=true either=true numeric=3
U+1D7D1 letter=false digit=true either=true numeric=3
U+00B2 letter=false digit=false either=false numeric=2
U+00BD letter=false digit=false either=false numeric=-2
U+216B letter=false digit=false either=false numeric=12
U+0301 letter=false digit=false either=false numeric=-1
```

U+1EBF là chữ `ế` dựng sẵn. U+4E2D là chữ Hán, còn U+10400 là chữ Deseret ngoài BMP. Chúng đều được nhận diện là chữ, dù cách hiển thị và quan hệ hoa/thường không giống nhau.

Dòng U+216B cũng đáng chú ý: số La Mã này thuộc nhóm `LETTER_NUMBER`, không thuộc năm nhóm chữ của `isLetter`, và cũng không thuộc `Nd`. Tên nhóm chứa chữ “LETTER” không làm nó tự động thỏa `isLetter`.

## 5. Vì sao phải dùng overload nhận int?

Một mã ngoài BMP nằm trong chuỗi dưới dạng hai đơn vị UTF-16. `charAt` trả từng đơn vị; nếu đưa một nửa surrogate vào overload nhận `char`, bộ phân loại không thể suy ra mã đầy đủ.

Đoạn sau minh họa bên trong một phương thức:

```java
String text = new String(Character.toChars(0x10400));

boolean wrongUnit = Character.isLetter(text.charAt(0));
boolean wholePoint = Character.isLetter(text.codePointAt(0));
```

Kết quả lần lượt là `false` và `true`. Giá trị đầu tiên không phản ánh chữ Deseret; nó chỉ phản ánh đơn vị surrogate mà `charAt(0)` trả về.

Cũng không sửa được vấn đề bằng cách ép `char` sang `int`:

```java
int stillOnlyOneUnit = text.charAt(0);
boolean result = Character.isLetter(stillOnlyOneUnit);
```

Biến có kiểu `int`, nhưng dữ liệu bên trong vẫn chỉ là một đơn vị đã đọc trước đó. Cần đọc đúng mã từ đầu, không chỉ đổi kiểu của biến.

Để duyệt một chuỗi theo mã Unicode:

```java
for (int offset = 0; offset < text.length();) {
    int point = text.codePointAt(offset);
    boolean letter = Character.isLetter(point);
    boolean digit = Character.isDigit(point);
    // Dùng kết quả letter và digit theo yêu cầu.
    offset += Character.charCount(point);
}
```

Đây là đoạn minh họa với `text` đã có giá trị khác `null`. Bước tăng là một hoặc hai đơn vị tùy mã. Có thể dùng `text.codePoints()` nếu cách viết bằng luồng phù hợp; `chars()` vẫn phát từng đơn vị UTF-16 nên không thay thế tương đương.

## 6. Kiểm tra cả chuỗi: phải quy định rỗng, null và tập ký tự cho phép

Một yêu cầu cụ thể có thể là:

> Chuỗi khác null, không rỗng, và mọi mã Unicode đều là chữ hoặc chữ số thập phân.

Đây là một chính sách đơn giản, không phải bộ xác thực tên người hoặc tên tài khoản phổ quát. Ta có thể viết bằng `codePoints().allMatch(...)`.

Chương trình dưới còn so sánh với một chính sách ASCII: chỉ cho phép `A-Z`, `a-z` và `0-9`. Lưu thành `AlphanumericPolicyDemo.java`:

```java
public class AlphanumericPolicyDemo {
    private static boolean unicodeAlphanumeric(String text) {
        return text != null
                && !text.isEmpty()
                && text.codePoints().allMatch(Character::isLetterOrDigit);
    }

    private static boolean asciiAlphanumeric(String text) {
        return text != null
                && !text.isEmpty()
                && text.codePoints().allMatch(point ->
                        (point >= 'A' && point <= 'Z')
                        || (point >= 'a' && point <= 'z')
                        || (point >= '0' && point <= '9'));
    }

    private static void show(String label, String text) {
        System.out.println(label
                + ": unicode=" + unicodeAlphanumeric(text)
                + ", ascii=" + asciiAlphanumeric(text));
    }

    public static void main(String[] args) {
        String letter = new String(Character.toChars(0x10400));
        String digit = new String(Character.toChars(0x1D7D1));

        System.out.println("supplementaryLetterByChar="
                + Character.isLetter(letter.charAt(0)));
        System.out.println("supplementaryLetterByPoint="
                + Character.isLetter(letter.codePointAt(0)));
        System.out.println("supplementaryDigitByChar="
                + Character.isDigit(digit.charAt(0)));
        System.out.println("supplementaryDigitByPoint="
                + Character.isDigit(digit.codePointAt(0)));

        show("plain", "Java21");
        show("Vietnamese", "\u1EBF2");
        show("Arabic-digit", "A\u0663");
        show("supplementary", letter + digit);
        show("combining", "e\u0301");
        show("underscore", "java_21");
        show("space", "java 21");
        show("emoji", "java\uD83D\uDE00");
        show("empty", "");
        show("null", null);
        show("unpaired-surrogate", "\uD800");
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 AlphanumericPolicyDemo.java
java AlphanumericPolicyDemo
```

Stdout:

```text
supplementaryLetterByChar=false
supplementaryLetterByPoint=true
supplementaryDigitByChar=false
supplementaryDigitByPoint=true
plain: unicode=true, ascii=true
Vietnamese: unicode=true, ascii=false
Arabic-digit: unicode=true, ascii=false
supplementary: unicode=true, ascii=false
combining: unicode=false, ascii=false
underscore: unicode=false, ascii=false
space: unicode=false, ascii=false
emoji: unicode=false, ascii=false
empty: unicode=false, ascii=false
null: unicode=false, ascii=false
unpaired-surrogate: unicode=false, ascii=false
```

`allMatch` trên luồng rỗng trả `true`, vì không có phần tử vi phạm. Do yêu cầu ở đây không chấp nhận chuỗi rỗng, hàm kiểm tra `!text.isEmpty()` riêng.

Các phép `&&` đánh giá ngắn mạch. Khi `text` là `null`, các lời gọi `isEmpty()` và `codePoints()` không được thực hiện.

Hai chính sách đều đúng với định nghĩa của chúng. Không dùng phép kiểm tra Unicode rộng để thay cho quy tắc ASCII của một giao thức, cũng không dùng khoảng ASCII để đại diện mọi chữ và chữ số của người dùng toàn cầu.

## 7. Dấu tổ hợp là trường hợp cần quyết định chính sách

Trong ví dụ, `"e\u0301"` là chữ `e` và dấu sắc tổ hợp. Hai mã thường được hiển thị thành một chữ có dấu, nhưng dấu U+0301 không phải chữ cái hoặc chữ số.

Vì thế, chính sách “mọi mã đều là letter hoặc digit” từ chối chuỗi này. Đó là kết quả đúng của điều kiện đã viết, nhưng có thể không đúng với ý định sản phẩm “cho nhập tên có dấu”.

Nếu xử lý tên hoặc văn bản tự nhiên:

- Quy định có chấp nhận các nhóm dấu tổ hợp hay không và chúng được phép ở vị trí nào.
- Xác định chính sách chuẩn hóa Unicode nếu cần so sánh các biểu diễn tương đương.
- Quy định riêng dấu cách, dấu nối và dấu nháy nếu miền dữ liệu cần chúng.
- Kiểm tra theo mẫu dữ liệu thật của ngôn ngữ cần hỗ trợ.

Không tự xóa mọi dấu để làm chuỗi vượt qua kiểm tra. Chuẩn hóa NFC có thể ghép một số tổ hợp thành chữ dựng sẵn nhưng không bảo đảm mọi cụm hợp lệ sẽ trở thành đúng một mã thuộc `isLetter`.

Các phép phân loại là công cụ xây dựng chính sách; chúng không tự xác định chính sách phù hợp cho mọi ngôn ngữ.

## 8. Phân loại chữ số khác với phân tích một giá trị số

Chuỗi `"-12"` chứa dấu âm nên không thỏa “mọi mã là chữ số”. Chuỗi `"12.5"` có dấu chấm nên cũng không thỏa. Điều đó không quyết định chúng có phải biểu diễn số hợp lệ theo một định dạng cụ thể hay không.

Nếu mục tiêu là đọc số nguyên, số thập phân hoặc số có quy tắc vùng miền, hãy dùng bộ phân tích và hợp đồng tương ứng. Không tự cộng giá trị từng mã mà bỏ qua dấu, dấu phân cách, tràn số hoặc quy tắc cú pháp.

Tương tự, nếu giao thức chỉ cho phép chữ số ASCII, điều kiện phù hợp là `point >= '0' && point <= '9'`. Việc một chữ số ngoài ASCII được `isDigit` chấp nhận không buộc giao thức phải chấp nhận nó.

## 9. Những giới hạn cần ghi nhớ

- Dữ liệu phân loại Unicode phụ thuộc phiên bản JDK. Khi nâng JDK, các mã được bổ sung vào Unicode có thể được nhận diện khác trước; các ví dụ trong bài dùng mã đã được hỗ trợ trên những JDK nêu trên.
- Phân loại không thay thế kiểm tra tính hợp lệ đầu vào. Java có thể chứa surrogate không ghép cặp trong `String`; ví dụ chính sách ở trên từ chối chúng vì không phải letter/digit, nhưng không vì thế trở thành bộ chẩn đoán UTF-16 tổng quát.
- `isLetterOrDigit` không tương đương kiểm tra định danh Java. Định danh có quy tắc riêng cho vị trí đầu và các vị trí tiếp theo.
- Hai chuỗi đều chỉ gồm chữ và số vẫn có thể trông giống nhau dù dùng mã hoặc hệ chữ khác. Phân loại không phải phép phát hiện ký tự giả dạng hay bảo đảm tính duy nhất của tên.
- Một phép kiểm tra code point không đếm cụm ký tự hiển thị. Cần chọn đơn vị riêng khi có giới hạn độ dài.

## 10. Tự kiểm tra

1. Tại sao nên dùng `isLetter(int)` khi phân loại nội dung một `String` Unicode?
2. Đổi kết quả `charAt` sang `int` có khôi phục cả mã ngoài BMP không?
3. U+0663 có thể thỏa `isDigit` dù không nằm giữa `'0'` và `'9'` không?
4. U+00B2 có giá trị số 2. Vì sao không suy ra nó thỏa `isDigit`?
5. `getNumericValue('A')` bằng 10 có nghĩa `A` là chữ số thập phân không?
6. Vì sao cần kiểm tra rỗng riêng trước `allMatch`?
7. Chính sách letter-or-digit có tự chấp nhận `e + dấu sắc tổ hợp` không?
8. Kiểm tra từng mã là chữ số có thay thế bộ phân tích số âm hoặc số thập phân không?

Đáp án:

1. Overload nhận `int` phân loại được mã ngoài BMP nếu bên gọi đã đọc đúng cả mã.
2. Không; dữ liệu đã đọc vẫn chỉ là một đơn vị UTF-16.
3. Có; đây là chữ số thập phân Unicode.
4. Nó thuộc một nhóm số khác, không phải `Nd`.
5. Không; giá trị số và phân loại chữ số là hai hợp đồng khác nhau.
6. `allMatch` trên luồng rỗng trả `true`, trong khi chính sách có thể yêu cầu có nội dung.
7. Không; dấu tổ hợp cần chính sách riêng.
8. Không; cú pháp và chuyển đổi giá trị số là trách nhiệm khác.

Khi phân loại Unicode, hãy đọc đúng mã, chọn đúng thuộc tính và áp dụng đúng chính sách. Ba bước này giúp mã vừa xử lý được chữ ngoài BMP, vừa tránh chấp nhận hoặc từ chối dữ liệu ngoài ý định.
