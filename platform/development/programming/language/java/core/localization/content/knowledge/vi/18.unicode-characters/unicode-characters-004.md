# length, codePointCount, codePoints và chỉ số UTF-16 trong Java

## 1. Ba cách “đếm ký tự” không phải lúc nào cũng giống nhau

Trong Java, một `String` biểu diễn một chuỗi các **đơn vị mã UTF-16 (code units)** ở cấp API. Khi xử lý localization, emoji, chữ viết ngoài Basic Multilingual Plane (BMP), dấu tổ hợp và nhiều ký tự Unicode, cần tách biệt:

1. **Đơn vị mã UTF-16:** mỗi `char` của Java là một code unit 16 bit. `String.length()` đếm các đơn vị này.
2. **Unicode code point:** giá trị số chỉ định một vị trí trong không gian mã Unicode, ví dụ `U+0041` (A), `U+1F600` (emoji khuôn mặt cười). `String.codePointCount(begin, end)` đếm các code point được biểu diễn trong đoạn UTF-16; `String.codePoints()` cho một luồng `int` tương ứng.
3. **Grapheme cluster / ký tự người dùng cảm nhận:** một cụm có thể gồm nhiều code point nhưng được nhìn và thao tác như một ký tự, ví dụ `e` + dấu sắc tổ hợp hoặc một emoji lá cờ được tạo từ hai regional indicator. Không có phương thức `String.length()` hay `codePointCount()` nào mặc định đếm số grapheme cluster theo đầy đủ quy tắc Unicode.

**Ví dụ:** chuỗi chứa chữ `A`, emoji `U+1F600`, chữ `e` theo sau bởi dấu kết hợp `U+0301`, rồi hai regional indicator `U+1F1FB` và `U+1F1F3` tạo thành cờ Việt Nam:

~~~text
Các code point:
U+0041 | U+1F600 | U+0065 | U+0301 | U+1F1FB | U+1F1F3

Số code point: 6
Số UTF-16 code units: 9
Số grapheme cluster thường được hiển thị: 4
~~~

Bốn grapheme cluster trong ví dụ tương ứng với **A**, **emoji cười**, **e với dấu sắc**, **emoji cờ**. Con số grapheme phụ thuộc quy tắc phân đoạn và rendering Unicode; không dựa vào nó để suy ra một giới hạn lưu trữ tính bằng UTF-16 code units.

Trong học tập về Java core, phải nhớ: **chỉ số truyền vào nhiều API của `String` là chỉ số UTF-16**, kể cả những API có chữ *codePoint* trong tên.

## 2. Vì sao một code point có thể chiếm hai char?

Unicode có các mã trong mặt phẳng cơ sở BMP (từ `U+0000` đến `U+FFFF`) và các mã bổ sung (supplementary code points, lớn hơn `U+FFFF`). Trong UTF-16:

- Code point ở BMP (không thuộc vùng surrogate khi là Unicode scalar value hợp lệ) có thể được biểu diễn bằng **một** `char`.
- Một supplementary code point cần **hai** `char`: **high surrogate** rồi **low surrogate**.
- High surrogate nằm trong vùng `U+D800`–`U+DBFF`; low surrogate nằm trong `U+DC00`–`U+DFFF`.
- `char` riêng lẻ **không đủ** để biểu diễn mọi code point Unicode. `int` là kiểu thích hợp khi đọc một code point.

Ví dụ emoji `U+1F600` có cặp UTF-16:

~~~text
Code point          : U+1F600
High surrogate      : U+D83D
Low surrogate       : U+DE00
Số UTF-16 code units: 2
Số Unicode code point: 1
~~~

Một chuỗi có thể chứa **surrogate đơn lẻ** (unpaired surrogate) do cắt sai, đọc dữ liệu không hợp lệ hoặc tạo trực tiếp `char`. Lưu ý: các phương thức `String.codePointCount` và `String.codePoints()` của Java **vẫn đếm/trả surrogate lẻ như một mục**. Vì vậy *đếm code point không đồng nghĩa với xác minh văn bản chứa toàn Unicode scalar values hợp lệ*.

### 2.1. Chỉ số UTF-16 của ví dụ

Các đơn vị mã trong chuỗi sáu code point được sắp như sau:

| Chỉ số UTF-16 | Code unit (hex) | Thuộc code point nào? |
| ---: | --- | --- |
| 0 | `U+0041` | A |
| 1 | `U+D83D` | High surrogate của `U+1F600` |
| 2 | `U+DE00` | Low surrogate của `U+1F600` |
| 3 | `U+0065` | e |
| 4 | `U+0301` | Dấu sắc tổ hợp |
| 5 | High surrogate của `U+1F1FB` | Regional indicator thứ nhất |
| 6 | Low surrogate của `U+1F1FB` | Regional indicator thứ nhất |
| 7 | High surrogate của `U+1F1F3` | Regional indicator thứ hai |
| 8 | Low surrogate của `U+1F1F3` | Regional indicator thứ hai |

Vị trí bắt đầu code point (tính theo `char`) là **0, 1, 3, 4, 5, 7**; vị trí ngay sau code point cuối là **9**. Vì có code point chiếm hai `char`, index theo code point và index theo UTF-16 **không thể hoán đổi**.

Trong nội bộ JVM, biểu diễn vật lý của một số `String` có thể được tối ưu hóa (ví dụ Compact Strings). Điều đó **không đổi hợp đồng API**: `length()`, `charAt`, `substring` và các chỉ số được mô tả ở đây vẫn theo đơn vị mã UTF-16.

## 3. String.length(): đếm đơn vị mã, không phải số code point

Phương thức:

~~~java
int count = text.length();
~~~

Đây là **đoạn minh họa**; `text` là `String` đã khai báo.

Với chuỗi ASCII `"Java"`, `length() == 4`, `codePointCount(0, 4) == 4`. Nhưng với một supplementary character, kết quả khác:

~~~java
String emoji = new String(Character.toChars(0x1F600));
System.out.println(emoji.length()); // 2
~~~

Ví dụ trên chạy khi nằm trong một phương thức Java. `Character.toChars(0x1F600)` trả hai `char`, nên độ dài của `String` là 2 dù người dùng nhìn thấy một emoji.

Hệ quả thực tế:

- `String.length()` phù hợp để tính **số UTF-16 code units** khi API hoặc dung lượng ô dữ liệu yêu cầu loại kích thước đó.
- `length()` **không** đếm code point, grapheme cluster, số chữ cái, số từ hay byte UTF-8.
- Không dùng `length() <= max` rồi tuyên bố “người dùng chỉ nhập tối đa max ký tự nhìn thấy” nếu giới hạn cần dựa trên grapheme.
- Nếu quy tắc là số byte khi gửi qua API hay database, phải đo theo **charset thực tế** như UTF-8, không suy từ `length()`.

### 3.1. charAt cũng đọc một code unit

~~~java
char firstPart = text.charAt(1);
~~~

`charAt(1)` chỉ trả về **high surrogate** `U+D83D` trong ví dụ, không trả nguyên `U+1F600`. Nếu in riêng nó ra giao diện hoặc chuyển qua encoding, ký tự có thể trở thành ký hiệu thay thế do cặp surrogate bị tách.

Dùng `Character.isHighSurrogate` và `Character.isLowSurrogate` để nhận diện các phần của cặp khi cần thao tác ở mức UTF-16; còn khi xử lý một code point, nên dùng các API code point phù hợp.

## 4. codePointCount(beginIndex, endIndex): đếm code point trong khoảng UTF-16

Cú pháp:

~~~java
int n = text.codePointCount(0, text.length());
~~~

**Cả hai tham số đều là chỉ số UTF-16**, không phải chỉ số code point:

- `beginIndex`: vị trí bắt đầu, bao gồm.
- `endIndex`: vị trí kết thúc, không bao gồm.
- Phần văn bản được xét là `[beginIndex, endIndex)`.
- Nếu gặp cặp surrogate đầy đủ trong khoảng, nó được tính là **một code point**.
- Surrogate lẻ trong khoảng được tính là **một mục**.
- Tham số vượt biên hoặc `beginIndex > endIndex` gây `IndexOutOfBoundsException`.

Với chuỗi ở mục 1:

~~~java
System.out.println(text.length());                        // 9
System.out.println(text.codePointCount(0, text.length())); // 6
~~~

Đây là minh họa trong một phương thức; chương trình đầy đủ ở mục 8.

**Trường hợp cắt đúng giữa surrogate pair:** đoạn `[1, 2)` chỉ chứa high surrogate của emoji nên `codePointCount(1, 2)` trả **1**, nhưng phần đó không phải code point scalar hợp lệ độc lập. Không dùng kết quả đếm để chứng minh đoạn Unicode còn nguyên vẹn.

### 4.1. codePointCount không xác định vị trí code point thứ n

Đếm code point của `text` chỉ cho biết **bao nhiêu**, không cho biết vị trí UTF-16 của code point thứ 3. Nếu bạn dùng:

~~~java
text.charAt(2)
~~~

thì index 2 vẫn là **low surrogate** của emoji, không phải code point thứ hai/từ thứ hai theo Unicode. Muốn di chuyển n code point, dùng `offsetByCodePoints` (mục 6).

Đừng tự viết `for (int i = 0; i < text.codePointCount(0, text.length()); i++) text.charAt(i)` vì vòng lặp này trộn hai hệ đơn vị chỉ số.

## 5. codePoints(): luồng int theo code point

`String.codePoints()` trả `IntStream`. Khi gặp cặp surrogate hợp lệ, stream kết hợp cả hai code unit thành **một** `int` có giá trị supplementary code point.

~~~java
int[] points = text.codePoints().toArray();
~~~

Trong ví dụ có `A`, emoji, `e`, dấu sắc tổ hợp và hai regional indicator, mảng này gồm:

~~~text
U+0041, U+1F600, U+0065, U+0301, U+1F1FB, U+1F1F3
~~~

**So với `chars()`:**

- `text.chars()` trả `IntStream` của **từng UTF-16 code unit** (mỗi `char` được mở rộng lên `int`). Nó cho **9 phần tử** trong chuỗi mẫu.
- `text.codePoints()` ghép surrogate pair và cho **6 phần tử** trong chuỗi mẫu.
- Cả hai không tự xử lý grapheme cluster; dấu tổ hợp `U+0301` vẫn là mục riêng trong code point stream.

Nếu đầu vào có surrogate lẻ, `codePoints()` đưa giá trị surrogate đó lên stream dưới dạng `int`. Nó **không tự xác thực**, cũng không tự sửa Unicode sai.

### 5.1. Vì sao nên dùng IntStream thay vì char loop?

Khi viết một bộ kiểm tra phạm vi code point hoặc thống kê Unicode, luồng code point tránh việc vô tình xử lý mỗi nửa emoji như một ký tự độc lập:

~~~java
long supplementaryCount = text.codePoints()
        .filter(Character::isSupplementaryCodePoint)
        .count();
~~~

Đây là đoạn minh họa trong phương thức có biến `text`. Nó đếm số **supplementary code points**, không đếm số emoji hay grapheme clusters. Các ký tự không phải emoji cũng có thể nằm ngoài BMP; một emoji phức hợp cũng có thể chứa nhiều code point, nên không thể suy ra số emoji từ con số này.

### 5.2. Đừng ép code point về char

~~~java
int cp = 0x1F600;
char broken = (char) cp; // Mất thông tin code point supplementary.
~~~

Đây là đoạn minh họa, không nên áp dụng. Ép `int` sang `char` chỉ giữ 16 bit thấp, không còn biểu diễn đúng `U+1F600`.

Nếu muốn dựng một chuỗi từ code point:

~~~java
String emoji = new String(Character.toChars(0x1F600));
String reconstructed = new String(
        new int[]{0x0041, 0x1F600, 0x0065}, 0, 3);
~~~

`Character.toChars` và constructor `String(int[], offset, count)` cho phép tạo UTF-16 tương ứng với các code point hợp lệ; tham số `count` trong constructor trên là **số phần tử mảng code point**, không phải số code unit của chuỗi kết quả.

## 6. offsetByCodePoints: chuyển vị trí code point sang index UTF-16

API thiết yếu để di chuyển trong `String` theo code point:

~~~java
int utf16Index = text.offsetByCodePoints(0, 2);
~~~

Trong chuỗi ví dụ, kết quả là **3**:

- Code point thứ nhất `A` chiếm chỉ số UTF-16 0.
- Code point thứ hai `U+1F600` chiếm chỉ số UTF-16 1 và 2.
- Vị trí **sau hai code point đầu tiên** là chỉ số UTF-16 **3**.

`offsetByCodePoints(index, codePointOffset)` nhận:

- `index`: vị trí bắt đầu **theo UTF-16**.
- `codePointOffset`: dịch tiến/lùi bao nhiêu **code point**; có thể âm.
- Giá trị trả về: vị trí mới **theo UTF-16**, không phải ordinal của code point.

Nếu vượt biên, phương thức ném `IndexOutOfBoundsException`. Tại vùng có surrogate lẻ, chúng vẫn được tính là một code point trong phép dịch.

### 6.1. Lấy code point thứ n (đếm từ 0)

~~~java
int n = 2;
int utf16Index = text.offsetByCodePoints(0, n);
int point = text.codePointAt(utf16Index);
~~~

Đây là snippet minh họa: n = 2 nghĩa là code point thứ ba, trong ví dụ là `U+0065` (`e`); chỉ số UTF-16 ở đó là 3. Điều kiện: `0 <= n < text.codePointCount(0, text.length())`, nếu không phải xử lý index ngoài phạm vi.

### 6.2. Cắt đoạn theo số code point, không làm vỡ surrogate pair

~~~java
static String sliceByCodePoints(String s, int startCp, int endCp) {
    int start = s.offsetByCodePoints(0, startCp);
    int end = s.offsetByCodePoints(0, endCp);
    return s.substring(start, end);
}
~~~

Đây là **phương thức minh họa**, cần dùng trong một class. `startCp` và `endCp` là các chỉ số **theo code point**, với end exclusive và miền `0 <= startCp <= endCp <= totalCodePoints`. Cần validate miền tham số nếu nhận input không tin cậy.

Hàm này không cắt giữa **một cặp surrogate hợp lệ** khi bắt đầu từ 0 và đi theo ranh giới code point. Tuy nhiên nó **vẫn có thể cắt giữa grapheme cluster** như chữ `e` và dấu sắc tổ hợp, hay hai regional indicator tạo thành một emoji cờ.

**Không** gọi `text.substring(0, 2)` để lấy “hai ký tự Unicode đầu tiên” trong chuỗi mẫu. Nó sẽ lấy `A` và **chỉ nửa đầu emoji**, tạo chuỗi có surrogate lẻ.

### 6.3. Chỉ số truyền vào vẫn phải nằm ở ranh giới thích hợp

`offsetByCodePoints` nhận index UTF-16 bất kỳ hợp lệ, không hứa tự đưa một vị trí **đang ở giữa surrogate pair** về đầu cặp. Nếu start index đã trỏ vào low surrogate (như index 2), việc dịch chuyển có thể coi low surrogate đó là một đơn vị độc lập theo đoạn đang xét.

Khi nhận index từ editor/UI, cần biết nó là UTF-16 index, code point index hay grapheme index. Không kết hợp trực tiếp các loại index mà không chuyển đổi/căn chỉnh ranh giới.

## 7. codePointAt, codePointBefore, indexOf và substring: giới hạn chỉ số

### 7.1. Đọc một code point tại chỉ số UTF-16

~~~java
int at = text.codePointAt(1);
int before = text.codePointBefore(3);
~~~

Cả hai trả về `U+1F600` trong ví dụ:

- `codePointAt(1)` bắt đầu ở **high surrogate** và nhìn thấy low surrogate theo sau, nên ghép thành code point đầy đủ.
- `codePointBefore(3)` nhìn từ vị trí 3 trở về, thấy low surrogate ở 2 và high ở 1, nên ghép thành code point đầy đủ.
- **Không** gọi `codePointAt(2)` rồi chờ giá trị `U+1F600`: vị trí 2 là low surrogate, nên nó được trả như một giá trị surrogate đơn lẻ.

Chỉ số của hai phương thức đều là **UTF-16**, và chúng có quy tắc biên khác nhau: `codePointAt(i)` yêu cầu `0 <= i < length()`, trong khi `codePointBefore(i)` yêu cầu `1 <= i <= length()`.

### 7.2. indexOf trả chỉ số UTF-16

~~~java
String emoji = new String(Character.toChars(0x1F600));
int position = text.indexOf(emoji); // 1
~~~

Kết quả **1** là vị trí UTF-16 nơi emoji bắt đầu, không phải “code point số 1” theo hợp đồng API dù tình cờ bằng 1 trong chuỗi này.

Khi tìm một ký tự nằm **sau** emoji, hai hệ tọa độ tách ra: `text.indexOf("e")` trả index UTF-16 **3**, trong khi `e` là code point thứ **3** nếu đếm từ 1 (code point index 2 nếu đếm từ 0).

`String.indexOf(int ch)` cũng nhận được **một Unicode code point** (nếu giá trị lớn hơn BMP) nhưng **kết quả trả về vẫn là chỉ số UTF-16**.

### 7.3. substring luôn nhận chỉ số UTF-16

`substring(beginIndex, endIndex)` cũng dùng khoảng `[beginIndex, endIndex)` theo UTF-16:

~~~java
String fullEmoji = text.substring(1, 3);   // Hai char, một code point.
String brokenHalf = text.substring(1, 2);  // Chỉ high surrogate.
~~~

`fullEmoji.length() == 2`, nhưng `fullEmoji.codePointCount(0, 2) == 1`. Còn `brokenHalf.length() == 1`; `Character.isHighSurrogate(brokenHalf.charAt(0))` trả `true`.

**Dữ liệu bị cắt không hợp lệ có thể đi qua nhiều API** mà không ném exception ngay. Lỗi thường chỉ xuất hiện khi chuyển sang UTF-8, render UI, kiểm tra chữ ký hoặc lưu một hệ thống đòi hỏi Unicode scalar values hợp lệ. Hãy cắt tại ranh giới code point và kiểm soát encoding đầu/cuối pipeline.

## 8. Chương trình Java 17 hoàn chỉnh: quan sát 9 code units và 6 code points

Đặt đoạn sau trong file **`Utf16IndexDemo.java`**. Chương trình tạo chuỗi từ **mảng code point**, tránh phụ thuộc khả năng nhập emoji của terminal/source editor. Toàn bộ stdout dùng mã `U+...` để so sánh ổn định.

~~~java
import java.util.Locale;
import java.util.stream.Collectors;

public class Utf16IndexDemo {
    static String hex(int codePoint) {
        return String.format(Locale.ROOT, "U+%04X", codePoint);
    }

    public static void main(String[] args) {
        int[] values = {
                0x0041, 0x1F600, 0x0065,
                0x0301, 0x1F1FB, 0x1F1F3
        };
        String text = new String(values, 0, values.length);
        String emoji = new String(Character.toChars(0x1F600));

        System.out.println("length=" + text.length());
        System.out.println("codePointCount=" +
                text.codePointCount(0, text.length()));
        System.out.println("codePoints=" + text.codePoints()
                .mapToObj(Utf16IndexDemo::hex)
                .collect(Collectors.joining(", ")));

        System.out.println("charAt(1)=" + hex(text.charAt(1)));
        System.out.println("charAt(2)=" + hex(text.charAt(2)));
        System.out.println("codePointAt(1)=" +
                hex(text.codePointAt(1)));
        System.out.println("codePointBefore(3)=" +
                hex(text.codePointBefore(3)));

        System.out.println("offsetByCodePoints(0,2)=" +
                text.offsetByCodePoints(0, 2));
        System.out.println("indexOf(emoji)=" + text.indexOf(emoji));

        String correct = text.substring(1, 3);
        String broken = text.substring(1, 2);
        System.out.println("valid substring length=" + correct.length()
                + ", codePoints=" +
                correct.codePointCount(0, correct.length()));
        System.out.println("broken substring length=" + broken.length()
                + ", highSurrogate=" +
                Character.isHighSurrogate(broken.charAt(0)));
        System.out.println("index at code point #4=" +
                text.offsetByCodePoints(0, 4));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 Utf16IndexDemo.java
java Utf16IndexDemo
~~~

**Stdout đã kiểm tra trên Java:**

~~~text
length=9
codePointCount=6
codePoints=U+0041, U+1F600, U+0065, U+0301, U+1F1FB, U+1F1F3
charAt(1)=U+D83D
charAt(2)=U+DE00
codePointAt(1)=U+1F600
codePointBefore(3)=U+1F600
offsetByCodePoints(0,2)=3
indexOf(emoji)=1
valid substring length=2, codePoints=1
broken substring length=1, highSurrogate=true
index at code point #4=5
~~~

**Vì sao kết quả như vậy?**

1. `length=9`: ba code point trong BMP chiếm mỗi điểm một code unit (`A`, `e`, `U+0301`), cộng ba supplementary code points chiếm hai code unit mỗi điểm (emoji cười và hai regional indicator): `3 × 1 + 3 × 2 = 9`.
2. `codePointCount=6`: stream code point gồm đúng sáu giá trị trong mảng.
3. `charAt(1)` và `charAt(2)` là hai surrogate `D83D` và `DE00`; `codePointAt(1)` ghép thành `U+1F600`.
4. `codePointBefore(3)` đọc nguyên emoji phía trước vị trí UTF-16 3.
5. Dịch hai code point từ UTF-16 index 0 đến index 3 vì emoji chiếm hai `char`.
6. `substring(1, 3)` giữ nguyên emoji; `substring(1, 2)` làm vỡ cặp surrogate.
7. Vị trí bắt đầu **code point index 4** (đếm từ 0) là **UTF-16 index 5**.

Không nên nhìn vào glyph hiển thị để đo số code point. Emoji lá cờ trong ví dụ được tạo từ **hai regional indicator**, mỗi cái là một supplementary code point. Một terminal có thể render thành lá cờ, hai biểu tượng riêng hoặc ký tự thay thế; nội dung Unicode của mảng code point không thay đổi.

## 9. Unicode code point vẫn khác grapheme cluster

Một “chữ” mà người dùng cảm nhận có thể gồm **nhiều code point**:

- `e` cộng `U+0301` biểu diễn chữ e có dấu sắc bằng hai code point; có thể trông tương đương ký tự dựng sẵn `é` (`U+00E9`), nhưng độ dài và code point count khác.
- Lá cờ Việt Nam trong ví dụ là cặp regional indicator `U+1F1FB` và `U+1F1F3`, không phải một code point duy nhất.
- Một số emoji người dùng nhìn là một biểu tượng nhưng được kết hợp từ nhiều code point bằng **zero-width joiner (ZWJ)**, biến thể `VS16`, dấu chỉ màu da hoặc các quy tắc Unicode khác.

Do đó, ba phép đếm có thể hoàn toàn khác:

| Quy tắc cần đo | API/cách tiếp cận | Lưu ý |
| --- | --- | --- |
| Số đơn vị UTF-16 | `String.length()` | Phù hợp giới hạn tính theo UTF-16 |
| Số code point được duyệt | `codePointCount(0, length())`, `codePoints()` | Có thể tính cả surrogate lẻ như một mục |
| Số ký tự người dùng cảm nhận | Bộ phân đoạn grapheme theo Unicode UAX #29 | Phải xác định phiên bản/implementation hỗ trợ |
| Số byte UTF-8 | `getBytes(StandardCharsets.UTF_8).length` | Chỉ đúng nếu văn bản được mã hóa theo chính sách xử lý ký tự không hợp lệ đã xác định |
| Số “chữ cái” | Tiêu chí ngôn ngữ/Unicode property cụ thể | Khác cả code point lẫn grapheme |

Java có `java.text.BreakIterator` cho các loại ranh giới văn bản, nhưng đừng mặc định bộ phân đoạn trong **mọi** JDK/locale đều bao phủ chính xác mọi quy tắc *extended grapheme cluster*, nhất là emoji hiện đại. Nếu sản phẩm cần cursor/delete/đếm “ký tự hiển thị” theo UAX #29, hãy chọn thư viện hoặc môi trường được kiểm chứng trên phiên bản Unicode sản phẩm yêu cầu.

### 9.1. Chuẩn hóa Unicode không giải quyết mọi vấn đề

`java.text.Normalizer` có thể chuyển một số biểu diễn tương đương về NFC/NFD. Ví dụ `e + U+0301` có thể được chuẩn hóa về `é` (`U+00E9`) theo NFC, làm thay đổi `length()` và `codePointCount()` mà người dùng vẫn thấy chữ giống nhau.

Tuy nhiên, chuẩn hóa **không phải** là cách biến mọi emoji sequence hoặc grapheme cluster thành một code point. Cũng không nên tự normalize mọi ID, secret, chữ ký, path hay trường dữ liệu nhạy cảm nếu contract chưa quy định: thay đổi dạng Unicode có thể ảnh hưởng tính bằng nhau và giá trị lưu trữ.

## 10. Giới hạn dữ liệu và thao tác an toàn

### 10.1. Khi một hệ thống giới hạn số ký tự

Trước khi kiểm tra `length()`, hãy làm rõ yêu cầu:

- **Giới hạn UTF-16 code units:** dùng `length()`, ví dụ các API trả độ dài Java `String`.
- **Giới hạn Unicode code points:** dùng `codePointCount(0, length())`, đồng thời validate surrogate nếu nguồn cần Unicode scalar values hợp lệ.
- **Giới hạn grapheme clusters:** dùng thuật toán phân đoạn grapheme thích hợp.
- **Giới hạn byte khi gửi/lưu:** mã hóa theo charset và đo byte; với UTF-8, non-BMP thường chiếm bốn byte, nhưng quan hệ byte/char/code point không cố định.

Không dùng một giới hạn có tên “100 characters” rồi ngầm đồng nhất với tất cả phương pháp. Khi ứng dụng hỗ trợ tiếng Việt, emoji, Indic scripts và người dùng quốc tế, sự nhầm lẫn có thể dẫn đến cắt sai văn bản hoặc báo lỗi độ dài không công bằng.

### 10.2. Lấy một đoạn ký tự mà không phá surrogate pair

Khi giới hạn theo code point, quy tắc cơ bản là tính ranh giới bằng `offsetByCodePoints` trước khi gọi `substring`. Ví dụ lấy tối đa `n` code point từ đầu:

~~~java
static String firstCodePoints(String s, int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be >= 0");
    }
    int total = s.codePointCount(0, s.length());
    int end = s.offsetByCodePoints(0, Math.min(n, total));
    return s.substring(0, end);
}
~~~

Đây là **một phương thức minh họa**, cần đặt trong class. Nó tránh cắt đôi cặp surrogate hợp lệ khi xuất phát từ index 0; **không** bảo đảm không cắt đôi grapheme cluster. Nếu input có surrogate lẻ sẵn thì phương thức cũng không tự loại bỏ phần sai.

### 10.3. Vòng lặp duyệt code point không cần tạo mảng

~~~java
for (int i = 0; i < s.length(); ) {
    int cp = s.codePointAt(i);
    // Xử lý cp.
    i += Character.charCount(cp);
}
~~~

Đây là **đoạn minh họa**, với `s` là `String`. `Character.charCount(cp)` trả 2 cho supplementary code point, 1 cho BMP/surrogate lẻ. Vòng lặp tiến theo ranh giới code point; với dữ liệu hợp lệ, nó không tách surrogate pair.

Nếu chỉ cần xử lý giá trị code point và không cần UTF-16 index, `s.codePoints().forEach(cp -> ...)` có thể dễ đọc hơn. Nếu cần index, sử dụng vòng lặp hoặc kết hợp `offsetByCodePoints` có chủ đích.

### 10.4. Tìm vị trí trong UI và dữ liệu

Khi một thư viện/editor gửi về caret position hoặc selection, phải xác nhận đơn vị chỉ số:

- Một số API trả **UTF-16 offset**, phù hợp trực tiếp với `String.substring`.
- Một số API trả **code point ordinal** hoặc **grapheme offset**.
- Một số hệ thống lưu **byte offset** theo UTF-8.

Không quy đổi “code point index 4” thành `substring(4)` nếu đoạn trước chứa supplementary code point. Trong ví dụ, code point index 4 tương ứng UTF-16 index 5. Cũng không suy từ byte offset thành `char` offset.

Các lỗi hay xảy ra ở vùng bôi đen văn bản, highlight kết quả tìm kiếm, vị trí lỗi validation, độ dài mật khẩu/username và phân trang nội dung Unicode.

## 11. Những nhầm lẫn và lỗi thường gặp

| Nhầm lẫn/lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `length()` đếm emoji là 1 | Supplementary emoji chiếm hai `char` | Dùng `codePointCount` khi cần code point |
| `charAt(i)` luôn trả một ký tự Unicode hoàn chỉnh | Có thể trả high/low surrogate | Dùng `codePointAt` ở ranh giới phù hợp |
| Dùng `codePointCount` rồi truyền kết quả vào `substring` như UTF-16 index | Cắt sai vị trí hoặc làm vỡ surrogate | Dùng `offsetByCodePoints` để chuyển index |
| `codePoints()` đếm grapheme | Dấu tổ hợp và flag emoji vẫn có nhiều code point | Dùng grapheme segmentation nếu UI cần |
| Surrogate lẻ được `codePoints()` tự sửa | Dữ liệu Unicode không hợp lệ vẫn đi qua stream | Validate và áp dụng chính sách reject/replace |
| `indexOf` trả chỉ số code point | `indexOf` trả **UTF-16 offset** | Chuyển rõ đơn vị trước khi dùng |
| `codePointAt(i)` nhận ordinal code point | Tham số i là UTF-16 index | Dùng `offsetByCodePoints` trước |
| Ép supplementary `int` xuống `char` | Mất dữ liệu | Dùng `Character.toChars` hoặc String constructor từ code points |
| Đếm byte bằng `length()` | Sai với UTF-8 và nhiều encoding | Mã hóa rồi đếm byte |
| Cắt chuỗi theo code point và nghĩ bảo toàn emoji ZWJ | Có thể làm vỡ grapheme cluster | Dùng thuật toán grapheme cho caret/UI |
| Tin mọi `BreakIterator` đều chính xác với emoji mới | Phân đoạn có thể lệch Unicode version | Kiểm thử bộ phân đoạn được chọn |
| Lấy UTF-16 index bắt đầu trong low surrogate rồi tự tăng/giảm code point | Ranh giới ban đầu đã không hợp lệ về cặp surrogate | Chuẩn hóa/vận hành theo ranh giới chính xác |

### 11.1. Trường hợp surrogate lẻ

`String` Java có thể chứa `char` thuộc surrogate range mà không có bạn ghép hợp lệ. Trong trường hợp đó:

- `length()` vẫn đếm đơn vị mã.
- `codePointCount()` coi surrogate lẻ là một phần tử.
- `codePoints()` phát ra giá trị surrogate như một `int`, chứ **không** biến nó thành Unicode scalar value hợp lệ.
- Khi mã hóa sang UTF-8 bằng encoder, kết quả của surrogate lẻ phụ thuộc **chính sách xử lý malformed input** (report, replace hoặc khác); cần kiểm soát rõ nếu dữ liệu phải được bảo toàn/làm sạch.

Với input có yêu cầu Unicode hợp lệ, hãy validate các cặp surrogate hoặc dùng decoder/encoder cấu hình báo lỗi. `codePointCount` không thực hiện nhiệm vụ đó.

### 11.2. Các phép đo có thể đổi khi normalization

Chuỗi `e + U+0301` có `length() == 2`, `codePointCount(...) == 2`, dù trên giao diện thường nhìn thành một chữ có dấu. Nếu normalize NFC thành `U+00E9`, `length() == 1`, `codePointCount(...) == 1`. Vì vậy phải xác định có chuẩn hóa Unicode hay không **trước khi** áp dụng quy tắc giới hạn được cam kết.

## 12. Bài tập thực hành

1. Tạo `String smile = new String(Character.toChars(0x1F600));`; so `smile.length()`, `smile.codePointCount(0, smile.length())`, `smile.chars().count()` và `smile.codePoints().count()`.
2. Từ chương trình ở mục 8, thử `text.codePointAt(2)`. Giải thích vì sao kết quả là **low surrogate** chứ không phải emoji đầy đủ.
3. Tính `text.offsetByCodePoints(0, 5)`. Tìm index UTF-16 tương ứng và xác nhận bằng bảng chỉ số ở mục 2.
4. Cắt `text.substring(3, 5)`: nó gồm những code point nào? Đó là một hay nhiều grapheme cluster?
5. Viết `sliceByCodePoints` với `startCp`, `endCp` và kiểm tra các trường hợp `0`, tổng số điểm, chỉ số âm và `startCp > endCp`.
6. Dùng `Character.isSurrogatePair(high, low)` để phát hiện surrogate pair của `U+1F600`; thử tách nửa cặp xem output encoding phản ứng thế nào.
7. Dùng `java.text.Normalizer` chuyển `"e\u0301"` sang NFC; so `length()`, `codePointCount` trước và sau.
8. Tạo một emoji ZWJ sequence rồi so `codePoints().count()` với số biểu tượng nhìn thấy trên UI. Không suy ra kết luận từ hình dạng trong console duy nhất.
9. Đo `text.getBytes(StandardCharsets.UTF_8).length` cho chuỗi mẫu (đã hợp lệ), đối chiếu với `length()` và `codePointCount()`.
10. Viết kiểm thử cho một quy tắc giới hạn “10 ký tự”: diễn đạt riêng ba phiên bản kiểm tra UTF-16 units, code points và grapheme clusters.
11. Chứng minh `text.indexOf("e") == 3` dù `e` là code point có ordinal 2 trong chuỗi mẫu.
12. Nhận một caret offset từ một UI: xác định nó thuộc hệ tọa độ nào trước khi cắt hoặc highlight văn bản.

## 13. Tổng kết

**`String.length()` đếm UTF-16 code units; `codePointCount(begin, end)` đếm các code point trong khoảng được chỉ định bằng UTF-16 indices; `codePoints()` phát luồng `int` theo code point; và nhiều phương thức như `charAt`, `codePointAt`, `substring`, `indexOf` vẫn dùng/trả UTF-16 offsets.**

Để chuyển từ ordinal code point sang chỉ số `String`, dùng `offsetByCodePoints`; để lặp qua code points mà không chia surrogate pair, dùng `codePoints()` hoặc vòng lặp với `codePointAt` và `Character.charCount`. Nếu yêu cầu “ký tự người dùng cảm nhận”, phải xét **grapheme clusters** và quy tắc phân đoạn Unicode, vì nhiều emoji và dấu tổ hợp gồm nhiều code point.

Tách rõ **code units, code points, grapheme clusters và bytes** giúp ứng dụng đa ngôn ngữ không cắt hỏng văn bản, không trộn chỉ số và không áp dụng sai giới hạn nhập liệu.

**Tài liệu tham khảo:**

- Java SE 17, `String`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java SE 17, `Character`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html
- Java SE 17, `BreakIterator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html
- Java SE 17, `Normalizer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html
- Unicode Standard Annex #29 (Text Segmentation): https://unicode.org/reports/tr29/
