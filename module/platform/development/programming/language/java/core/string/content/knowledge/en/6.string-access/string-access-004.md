# codePointCount trên một khoảng UTF-16 trong Java

## 1. Mục tiêu và ý nghĩa

Phương thức **String.codePointCount(int beginIndex, int endIndex)** đếm số **Unicode code point** được biểu diễn trong **một khoảng của chuỗi Java**. Điểm dễ nhầm nhất: hai tham số **beginIndex** và **endIndex** đều là **chỉ số đơn vị mã UTF-16 (UTF-16 code unit)**, không phải chỉ số code point hay chỉ số ký tự người dùng nhìn thấy.

Cú pháp:

~~~java
int count = text.codePointCount(beginIndex, endIndex);
~~~

Các câu lệnh minh họa trong bài có thể đặt trong một phương thức Java. Quy ước của API:

- **beginIndex**: vị trí bắt đầu trong String, **bao gồm** vị trí này.
- **endIndex**: vị trí kết thúc, **không bao gồm** vị trí này; khoảng được viết **[beginIndex, endIndex)**.
- Chỉ số hợp lệ thỏa **0 <= beginIndex <= endIndex <= text.length()**.
- Nếu **beginIndex == endIndex**, kết quả là **0**.
- Nếu bắt đầu nhỏ hơn 0, kết thúc lớn hơn **length()**, hoặc bắt đầu lớn hơn kết thúc, phương thức ném **IndexOutOfBoundsException**.
- Mỗi **surrogate pair hợp lệ nằm trọn trong khoảng** được đếm là **1 code point**.
- Mỗi **surrogate đơn lẻ** trong khoảng, kể cả một nửa của cặp bị cắt bởi ranh giới, được đếm là **1**.

**Điều quan trọng:** phương thức đếm theo đoạn UTF-16 **đúng như được truyền vào**. Nó không tự kéo giãn khoảng để giữ nguyên các cặp surrogate, không chuẩn hóa Unicode, không đếm grapheme cluster và không tự biến tham số thành vị trí code point.

## 2. Ba khái niệm cần phân biệt

| Khái niệm | Trong Java | Cách hiểu |
| --- | --- | --- |
| **UTF-16 code unit** | **char**, **String.length()**, chỉ số của **charAt()**/**substring()** | Một đơn vị 16 bit; code point ngoài vùng BMP cần hai đơn vị |
| **Unicode code point** | **codePointAt()**, **codePoints()**, **codePointCount()** | Giá trị Unicode; một cặp high surrogate + low surrogate biểu diễn một code point bổ sung |
| **Extended grapheme cluster** | Có thể phân đoạn bằng regex **\\X** | Một cụm thường được người dùng cảm nhận như một ký tự, có thể chứa nhiều code point |

**Basic Multilingual Plane (BMP)** là các code point từ U+0000 đến U+FFFF, trừ dải surrogate vốn không phải Unicode scalar value độc lập. Những code point bổ sung từ U+10000 đến U+10FFFF được mã hóa bằng **hai UTF-16 code unit**: **high surrogate** theo sau bởi **low surrogate**.

Do đó:

- Chữ Latin thông thường **A**: thường 1 code unit và 1 code point.
- Emoji **😊** (U+1F60A): 2 code unit, 1 code point.
- Chữ **a** cộng dấu sắc kết hợp **a\u0301**: 2 code unit, 2 code point, nhưng thường 1 grapheme cluster.
- Emoji **👩‍💻**: 5 code unit, 3 code point, thường 1 grapheme cluster.

**codePointCount()** trả lời câu hỏi về **code point trong khoảng UTF-16**; nó không nhất thiết trả lời câu hỏi “có bao nhiêu chữ, bao nhiêu emoji hay bao nhiêu ký tự hiển thị?”.

## 3. Minh họa chính: "A😊B"

Xét chuỗi:

~~~java
String text = "A😊B";
~~~

Bố cục của chuỗi theo chỉ số **UTF-16**:

| Vị trí code unit | Nội dung | Vai trò |
| ---: | --- | --- |
| 0 | **A** | Chữ BMP, 1 code unit |
| 1 | **U+D83D** | High surrogate của **😊** |
| 2 | **U+DE0A** | Low surrogate của **😊** |
| 3 | **B** | Chữ BMP, 1 code unit |
| 4 | Ranh giới cuối chuỗi | Vị trí **endIndex** hợp lệ, không phải ký tự |

Vậy **text.length() == 4**, nhưng toàn chuỗi chỉ có **3 code point**: **A**, **😊**, **B**.

Các khoảng tiêu biểu:

| Khoảng UTF-16 | Phần được lấy | **codePointCount** | Giải thích |
| --- | --- | ---: | --- |
| **[0, 4)** | **A😊B** | 3 | A (1) + cặp surrogate của 😊 (1) + B (1) |
| **[1, 3)** | **😊** | 1 | Hai code unit kết hợp thành một code point |
| **[0, 1)** | **A** | 1 | Một chữ BMP |
| **[3, 4)** | **B** | 1 | Một chữ BMP |
| **[1, 1)** | Rỗng | 0 | Không có code unit nào |
| **[0, 2)** | A + high surrogate riêng | 2 | Ranh giới 2 cắt đôi surrogate pair |
| **[2, 4)** | Low surrogate riêng + B | 2 | Ranh giới 2 cắt đôi surrogate pair |

Điều này dẫn đến một tính chất cần thận trọng:

~~~java
int whole = text.codePointCount(0, 4);   // 3
int left = text.codePointCount(0, 2);    // 2
int right = text.codePointCount(2, 4);   // 2
~~~

**left + right == 4**, khác với **whole == 3**, vì điểm chia **2** nằm **giữa hai nửa surrogate pair**. Việc cộng số code point của các khoảng chỉ tương thích với số đếm toàn đoạn nếu mọi ranh giới chia **không tách** một surrogate pair hợp lệ.

Nếu đổi điểm chia thành **3**, tức ngay sau emoji, kết quả:

~~~java
int left = text.codePointCount(0, 3);    // 2 (A, 😊)
int right = text.codePointCount(3, 4);   // 1 (B)
~~~

Khi đó **left + right == 3**, đúng bằng số code point toàn chuỗi.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu thành tệp **CodePointCountRangeDemo.java** (mã hóa UTF-8):

~~~java
public class CodePointCountRangeDemo {
    public static void main(String[] args) {
        String text = "A😊B";

        System.out.println("UTF16 units: " + text.length());
        System.out.println("All: " +
                text.codePointCount(0, text.length()));
        System.out.println("Emoji: " +
                text.codePointCount(1, 3));
        System.out.println("Left split: " +
                text.codePointCount(0, 2));
        System.out.println("Right split: " +
                text.codePointCount(2, 4));
        System.out.println("Empty: " +
                text.codePointCount(1, 1));

        System.out.println("High surrogate: " +
                Character.isHighSurrogate(text.charAt(1)));
        System.out.println("Low surrogate: " +
                Character.isLowSurrogate(text.charAt(2)));

        int endAfterTwoPoints = text.offsetByCodePoints(0, 2);
        System.out.println("Index after 2 points: " +
                endAfterTwoPoints);
        System.out.println("Prefix: " +
                text.substring(0, endAfterTwoPoints));
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 CodePointCountRangeDemo.java
java CodePointCountRangeDemo
~~~

Stdout:

~~~text
UTF16 units: 4
All: 3
Emoji: 1
Left split: 2
Right split: 2
Empty: 0
High surrogate: true
Low surrogate: true
Index after 2 points: 3
Prefix: A😊
~~~

Các con số được tính dựa trên cặp surrogate của emoji **😊**: high surrogate U+D83D và low surrogate U+DE0A.

Điểm cần ghi nhớ từ chương trình:

1. **length()** đo số code unit; **codePointCount(0, length())** đo số code point trong cả String.
2. **[1, 3)** chứa trọn surrogate pair nên kết quả bằng 1.
3. **[0, 2)** và **[2, 4)** tạo ra các khoảng có một surrogate lẻ; mỗi surrogate lẻ được tính là 1.
4. **offsetByCodePoints(0, 2)** trả về **chỉ số UTF-16 bằng 3** sau hai code point đầu, thích hợp để truyền vào **substring()**.

**Quan trọng:** **charAt(1)** cho ra high surrogate, không phải ký tự emoji hoàn chỉnh. Muốn đọc code point bắt đầu ở vị trí đó, dùng **text.codePointAt(1)**; kết quả là U+1F60A.

## 5. Giới hạn beginIndex/endIndex và khoảng rỗng

Khoảng trong Java là **nửa mở**:

\[
[beginIndex,endIndex)
\]

Ví dụ với **"Java"** (mỗi ký tự trong ví dụ này là một code unit):

| Lệnh | Kết quả | Vì sao |
| --- | ---: | --- |
| **"Java".codePointCount(0, 4)** | 4 | Đếm cả chuỗi |
| **"Java".codePointCount(1, 3)** | 2 | Chứa ký tự ở vị trí 1 và 2 |
| **"Java".codePointCount(0, 0)** | 0 | Khoảng rỗng đầu chuỗi |
| **"Java".codePointCount(4, 4)** | 0 | Khoảng rỗng cuối chuỗi |

Các lệnh sau không hợp lệ:

~~~java
String text = "Java";
text.codePointCount(-1, 2); // beginIndex âm
text.codePointCount(1, 5);  // endIndex vượt length()
text.codePointCount(3, 2);  // beginIndex > endIndex
~~~

Đây là đoạn **minh họa lỗi**, không nên chạy ba lệnh liên tiếp nếu muốn quan sát từng lỗi, vì lệnh đầu tiên đã ném **IndexOutOfBoundsException** và có thể làm dừng chương trình. Các ranh giới đúng cần thoả đồng thời **0 <= beginIndex <= endIndex <= text.length()**.

Đừng nhầm các trường hợp **endIndex == length()** (hợp lệ) với truy cập **charAt(length())** (không hợp lệ, vì đây là vị trí ngay sau phần tử cuối).

Nếu phương thức chỉ nhận khoảng code point từ người dùng hoặc từ một API khác, **không được** đưa trực tiếp chúng vào **codePointCount(beginIndex, endIndex)**. Trước tiên phải chuyển các offset theo code point thành offset UTF-16.

## 6. Chuyển giữa vị trí UTF-16 và vị trí code point

**codePointCount(begin, end)** trả lại **số code point**, không trả lại chỉ số. Khi cần một offset UTF-16 tương ứng với một số code point, Java cung cấp:

~~~java
int endUtf16 = text.offsetByCodePoints(startUtf16, numberOfCodePoints);
~~~

Ví dụ:

~~~java
String text = "A😊B";
int endUtf16 = text.offsetByCodePoints(0, 2); // 3
String firstTwo = text.substring(0, endUtf16); // "A😊"
~~~

Vì ký tự bổ sung **😊** chiếm hai code unit nên offset sau hai code point đầu là **3**, không phải **2**.

Một phép đếm prefix cũng hữu ích khi chuyển **offset UTF-16** thành thứ tự code point:

~~~java
String text = "A😊B";
int utf16Index = 3; // bắt đầu chữ B
int codePointsBeforeB = text.codePointCount(0, utf16Index); // 2
~~~

Điều kiện cần chú ý là **utf16Index** phải nằm ở ranh giới code point khi bạn định diễn giải kết quả như số code point **trước một ký tự nguyên vẹn**. Nếu dùng **utf16Index == 2** (giữa emoji), **codePointCount(0, 2)** vẫn trả về **2**, nhưng đó không phải vị trí hợp lệ để đặt con trỏ “sau hai code point” trong chuỗi gốc.

**offsetByCodePoints()** cũng cần điểm khởi đầu và số code point hợp lệ. Nó có thể di chuyển từ một vị trí UTF-16 tùy ý, kể cả vị trí ở giữa surrogate pair; nếu muốn đảm bảo không chia đôi code point, **đầu vào phải là ranh giới hợp lệ**.

### Hàm hỗ trợ kiểm tra ranh giới surrogate

Một **ranh giới code point hợp lệ** không được nằm giữa high surrogate và low surrogate kề nhau. Phương thức sau kiểm tra điều kiện đó:

~~~java
static boolean isCodePointBoundary(String text, int index) {
    if (index < 0 || index > text.length()) {
        return false;
    }
    if (index == 0 || index == text.length()) {
        return true;
    }
    return !(Character.isHighSurrogate(text.charAt(index - 1))
            && Character.isLowSurrogate(text.charAt(index)));
}
~~~

Đây là **đoạn mã phương thức**; cần đặt trong một lớp Java. Ví dụ với **"A😊B"**: chỉ số **1** và **3** là ranh giới, **2** không phải. Hai đầu **0** và **4** cũng là ranh giới.

Phương thức này chỉ đảm bảo **không cắt giữa một surrogate pair**, chứ **không xác nhận toàn bộ String là UTF-16 hợp lệ**. Java String có thể chứa các surrogate lẻ vốn đã có sẵn trong dữ liệu.

## 7. Ví dụ Java 17+: kiểm tra ranh giới trước khi đếm

Ví dụ sau thích hợp khi API của bạn muốn đếm **các code point hoàn chỉnh** và cần từ chối khoảng cắt đôi surrogate pair. Lưu thành **SafeCodePointRangeDemo.java**:

~~~java
public class SafeCodePointRangeDemo {
    static boolean isBoundary(String text, int index) {
        if (index < 0 || index > text.length()) {
            return false;
        }
        if (index == 0 || index == text.length()) {
            return true;
        }
        return !(Character.isHighSurrogate(text.charAt(index - 1))
                && Character.isLowSurrogate(text.charAt(index)));
    }

    static int countOnBoundaries(String text, int begin, int end) {
        if (text == null) {
            throw new IllegalArgumentException("text is null");
        }
        if (begin > end ||
                !isBoundary(text, begin) ||
                !isBoundary(text, end)) {
            throw new IllegalArgumentException(
                    "range splits a surrogate pair or is invalid");
        }
        return text.codePointCount(begin, end);
    }

    public static void main(String[] args) {
        String text = "A😊B";

        System.out.println(isBoundary(text, 1));
        System.out.println(isBoundary(text, 2));
        System.out.println(isBoundary(text, 3));
        System.out.println(countOnBoundaries(text, 0, 3));

        try {
            System.out.println(countOnBoundaries(text, 0, 2));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected a split surrogate pair");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SafeCodePointRangeDemo.java
java SafeCodePointRangeDemo
~~~

Stdout:

~~~text
true
false
true
2
Rejected a split surrogate pair
~~~

Phương thức **countOnBoundaries** chọn chính sách **từ chối khoảng nằm giữa một surrogate pair**. Đây là ràng buộc **tự viết thêm**, không phải hành vi mặc định của **String.codePointCount()**. API chuẩn cho phép đếm cả các khoảng như **[0, 2)** và sẽ tính surrogate lẻ là một code point.

Các ứng dụng cần bảo đảm dữ liệu Unicode chặt chẽ còn phải có bước xác thực **không có surrogate lẻ trong toàn bộ vùng dữ liệu**. Kiểm tra ranh giới không thay thế cho xác thực đó.

## 8. Dấu tiếng Việt và emoji phức hợp: đếm code point khác đếm grapheme

Một dấu tiếng Việt có thể được mã hóa bằng **combining mark**; ví dụ:

~~~java
String composed = "\u00E1";     // á, một code point dựng sẵn
String decomposed = "a\u0301"; // a + dấu sắc kết hợp

System.out.println(composed.codePointCount(0, composed.length()));     // 1
System.out.println(decomposed.codePointCount(0, decomposed.length())); // 2
~~~

Hai giá trị thường **hiển thị** giống nhau, nhưng **codePointCount()** có kết quả khác nhau. Nguyên nhân là phương thức này **không tự chuẩn hóa** NFC/NFD. Nếu nghiệp vụ cần so sánh hai dạng canonical tương đương, có thể áp dụng **java.text.Normalizer** nhất quán:

~~~java
import java.text.Normalizer;

// Các lệnh sau đặt bên trong một phương thức:
String a = Normalizer.normalize("\u00E1", Normalizer.Form.NFC);
String b = Normalizer.normalize("a\u0301", Normalizer.Form.NFC);
System.out.println(a.equals(b)); // true
~~~

Phần code phía trên là **đoạn minh họa có import**, không phải chương trình độc lập. Chuẩn hóa không làm mất dấu tiếng Việt, còn phép bỏ dấu là một yêu cầu nghiệp vụ khác.

Tương tự:

- Emoji **😊**: 2 UTF-16 code unit nhưng 1 code point.
- Emoji **👍🏽**: 4 UTF-16 code unit, 2 code point, thường hiển thị thành một biểu tượng.
- Emoji **👩‍💻**: 5 UTF-16 code unit, 3 code point, thường hiển thị thành một biểu tượng nhờ ZERO WIDTH JOINER.
- Emoji quốc kỳ **🇻🇳**: 4 UTF-16 code unit, 2 code point, thường hiển thị thành một lá cờ.

Vì vậy, ngay cả khi đưa toàn bộ chuỗi vào **codePointCount(0, length())**, con số nhận được có thể **khác số ký tự người dùng nhìn thấy**. Nếu yêu cầu là cắt hoặc giới hạn ký tự hiển thị, cần phân đoạn **extended grapheme cluster**, có thể dùng regex Java **Pattern.compile("\\X")** trong JDK hỗ trợ hoặc thư viện Unicode chuyên dụng khi cần kiểm soát phiên bản Unicode.

## 9. So sánh codePointCount với các API liên quan

| API | Trả về | Chỉ số/đầu vào | Lưu ý |
| --- | --- | --- | --- |
| **length()** | Số UTF-16 code unit trong toàn String | Không tham số | Không phải số code point với emoji ngoài BMP |
| **charAt(i)** | Một **char** (một code unit) | **i** là UTF-16 index | Có thể trả về một nửa surrogate pair |
| **codePointAt(i)** | Code point bắt đầu ở **i**, nếu có cặp hợp lệ | **i** là UTF-16 index | Nếu bắt đầu tại low surrogate lẻ, trả về giá trị code unit đó |
| **codePointBefore(i)** | Code point ngay trước **i** | **i** là UTF-16 index, bắt đầu từ 1 | Xét cặp surrogate theo hướng lùi |
| **codePointCount(begin, end)** | Số code point trong đoạn UTF-16 nửa mở | Hai offset UTF-16 | Surrogate lẻ trong đoạn đếm là 1 |
| **offsetByCodePoints(i, delta)** | Offset UTF-16 sau khi di chuyển theo code point | **i** là UTF-16 index; delta là số code point có dấu | Có thể dùng để tìm điểm cuối phù hợp cho substring |
| **codePoints().count()** | Số code point trong cả String dưới dạng **long** | Không có chỉ số đoạn trực tiếp | Nếu chỉ cần tổng số toàn chuỗi, có thể dùng **codePointCount(0, length())** |
| **substring(begin, end)** | String con trên khoảng UTF-16 | Hai offset UTF-16 | Có thể cắt đôi surrogate pair nếu dùng sai offset |

**codePoints()** trả về **IntStream** các giá trị code point. Số lượng điểm mã của **toàn chuỗi** thu được bằng **text.codePoints().count()** và **text.codePointCount(0, text.length())** sẽ bằng nhau khi cùng xét một String; **codePoints().count()** trả về **long**, còn **codePointCount()** trả về **int**.

Về chi phí, việc đếm số code point trong khoảng cần duyệt các code unit liên quan để nhận diện surrogate pair; nó không được hiểu là thao tác lấy độ dài **O(1)** giống như đọc thuộc tính **length()** của String. Với dữ liệu lớn và nhiều phép truy vấn, cân nhắc lưu sẵn thông tin chỉ mục ở các **ranh giới hợp lệ** hoặc thay đổi cấu trúc dữ liệu phù hợp, thay vì liên tục quét lại các khoảng.

## 10. Mẫu áp dụng vào bài toán thực tế

### Tình huống 1: Đếm nội dung giữa hai vị trí Java đã biết

Nếu **begin** và **end** đến từ **Matcher.start()/end()**, **String.indexOf()**, hoặc một API Java trả về offset UTF-16, có thể gọi:

~~~java
int codePoints = text.codePointCount(begin, end);
~~~

Trước khi diễn giải kết quả như số ký tự đầy đủ, kiểm tra ranh giới có tách surrogate pair hay không. Không phải mọi đoạn con hoặc vị trí do ứng dụng tự tính đều được bảo đảm nằm tại ranh giới code point.

### Tình huống 2: Lấy 10 code point đầu

Không dùng **substring(0, 10)** nếu có thể xuất hiện emoji, vì 10 code point có thể cần nhiều hơn 10 code unit UTF-16.

~~~java
int amount = Math.min(10, text.codePointCount(0, text.length()));
int endIndex = text.offsetByCodePoints(0, amount);
String prefix = text.substring(0, endIndex);
~~~

Đoạn này giữ tối đa 10 code point tính từ đầu String, không tự bảo đảm giữ trọn một grapheme gồm nhiều code point. Với yêu cầu “10 ký tự nhìn thấy”, thay bằng phân đoạn grapheme.

### Tình huống 3: Đếm phần đã nhập từ đầu tới vị trí caret

Nếu caret tính bằng offset UTF-16 **và** trỏ vào ranh giới code point hợp lệ:

~~~java
int pointsBeforeCaret = text.codePointCount(0, caretUtf16Index);
~~~

Nếu con trỏ có thể nằm giữa surrogate pair, cần điều chỉnh về một ranh giới hợp lệ trước khi diễn giải kết quả. Nếu giao diện đếm theo grapheme thay vì code point, sử dụng chỉ số grapheme độc lập.

### Tình huống 4: Chia đoạn để xử lý song song hoặc phân trang

Khi chia tại các offset UTF-16, một điểm chia không được đi qua surrogate pair nếu các phần sẽ được xử lý như văn bản Unicode hoàn chỉnh. Nếu cắt tại vị trí giữa cặp, tổng **codePointCount** của các phần có thể lớn hơn tổng thực sự của đoạn ban đầu. Nên xác định ranh giới chia dựa trên **offsetByCodePoints()** hoặc kiểm tra ranh giới trước khi cắt; nếu cần bảo toàn ký tự hiển thị, dùng grapheme boundary.

## 11. Những lỗi phổ biến và cách tránh

1. **Tưởng beginIndex/endIndex là chỉ số code point.** Đây là offset UTF-16. Chuyển chỉ số bằng **offsetByCodePoints()** trước khi gọi phương thức cần offset.
2. **Tưởng đếm từng đoạn rồi cộng luôn bằng tổng.** Điều này sai nếu điểm chia cắt một surrogate pair; hãy chia tại ranh giới code point hợp lệ.
3. **Lấy beginIndex == endIndex làm lỗi.** Khoảng rỗng hợp lệ và trả về 0.
4. **Dùng endIndex = length() - 1 để đếm toàn chuỗi.** Vì khoảng nửa mở, muốn đếm toàn bộ phải truyền **endIndex = length()**.
5. **Coi surrogate lẻ là lỗi tự động ném exception.** API **codePointCount()** đếm chúng là 1; xác thực UTF-16 hợp lệ là trách nhiệm riêng.
6. **Coi số code point là số chữ nhìn thấy.** Combining mark và emoji ghép có thể là nhiều code point trong một grapheme.
7. **Tự cắt bằng substring ở offset tùy ý.** Có thể sinh surrogate lẻ, gây kết quả khó đoán khi hiển thị hoặc mã hóa sang UTF-8.
8. **Nghĩ codePointCount tự chuẩn hóa chữ tiếng Việt.** NFC và NFD có thể khác số code point; chuẩn hóa phải là một bước tường minh theo nghiệp vụ.
9. **Dùng codePointCount để suy ra số byte lưu trữ.** Độ dài byte phụ thuộc charset; để biết byte UTF-8, dùng **text.getBytes(StandardCharsets.UTF_8).length**.

## 12. Tự kiểm tra

**Câu 1.** Với **String s = "A😊B"**, kết quả **s.length()** và **s.codePointCount(0, s.length())** là gì?

**Đáp án:** 4 code unit và 3 code point.

**Câu 2.** Vì sao **s.codePointCount(0, 2) + s.codePointCount(2, 4)** bằng 4 thay vì 3?

**Đáp án:** Ranh giới UTF-16 tại vị trí 2 nằm giữa high và low surrogate của emoji; mỗi nửa khi đứng riêng trong một khoảng được đếm là 1.

**Câu 3.** Khoảng **[1, 1)** trả về gì?

**Đáp án:** 0 vì đây là khoảng rỗng, hợp lệ.

**Câu 4.** Muốn lấy hai code point đầu của **"A😊B"** thì dùng điểm cuối UTF-16 nào?

**Đáp án:** **s.offsetByCodePoints(0, 2)** trả về 3; dùng **s.substring(0, 3)** để lấy **"A😊"**.

**Câu 5.** **codePointCount** có tự từ chối surrogate lẻ hoặc tự đếm emoji **👩‍💻** là một ký tự không?

**Đáp án:** Không. Surrogate lẻ tính một đơn vị trong phép đếm; emoji ZWJ này gồm 3 code point và thường là 1 grapheme cluster.

**Câu 6.** Với chữ **"á"** ở NFC và chữ **"a\u0301"** ở NFD, vì sao kết quả có thể khác?

**Đáp án:** NFC có một code point dựng sẵn, còn dạng kết hợp gồm hai code point. Phương thức không tự normalize.

## 13. Ghi nhớ

- **String.codePointCount(beginIndex, endIndex)** đếm **Unicode code point** trên khoảng **UTF-16 nửa mở [beginIndex, endIndex)**.
- **Hai chỉ số đều là offset UTF-16**; giá trị trả về là **số code point**, không phải vị trí hay số grapheme.
- **Một surrogate pair đầy đủ được đếm một lần; surrogate lẻ trong khoảng được đếm một lần mỗi phần**.
- **Không cắt surrogate pair** khi muốn tách chuỗi thành những vùng văn bản Unicode nguyên vẹn; khi cần tính tổng giữa nhiều đoạn, mọi ranh giới chia phải được kiểm tra.
- **offsetByCodePoints()** giúp di chuyển theo code point và trả lại offset UTF-16 đúng loại để dùng với **substring()**.
- Tiếng Việt có dấu kết hợp và emoji nhiều thành phần cho thấy rõ **code point không tương đương ký tự hiển thị**.

Tham khảo API: **Java SE 17, java.lang.String#codePointCount(int,int)**, **String#offsetByCodePoints(int,int)**, **Character#isHighSurrogate(char)**, **Character#isLowSurrogate(char)** và quy tắc Unicode về UTF-16.