# Giữ nguyên hợp đồng String, char và code point trong Java

## 1. Vì sao hợp đồng String quan trọng khi tối ưu JVM?

Java định nghĩa một hợp đồng rõ ràng cho String và CharSequence: chuỗi được nhìn như một dãy các giá trị char 16 bit theo UTF-16. Các API công khai phải giữ nguyên ý nghĩa đó, dù JVM thay đổi cách lưu trữ, tối ưu phép nối chuỗi hoặc biên dịch mã.

Khi xử lý Unicode, cần phân biệt ba đơn vị:

- **UTF-16 code unit**: một giá trị char 16 bit. Đây là đơn vị đánh chỉ số của String.
- **Unicode code point**: một giá trị số xác định một vị trí trong không gian mã Unicode. Java biểu diễn code point bằng int.
- **UTF-8 byte**: đơn vị dữ liệu khi mã hóa chuỗi để truyền hoặc lưu trữ.

Một ký tự nằm trong Basic Multilingual Plane (BMP), ngoài vùng surrogate, thường chiếm một UTF-16 code unit. Một code point bổ sung (supplementary), chẳng hạn nhiều emoji hoặc ký hiệu âm nhạc, được biểu diễn bằng một cặp surrogate và chiếm hai code unit.

Vì vậy, không được đồng nhất String.length(), số code point, số glyph người dùng nhìn thấy và số byte khi mã hóa. Mỗi con số trả lời một câu hỏi khác nhau.

## 2. String và char theo hợp đồng Java

String là immutable: sau khi được tạo, chuỗi không thể bị thay đổi. Các thao tác như replace, concat, substring hoặc strip trả về giá trị String mới hoặc một giá trị đã có; chúng không sửa nội dung của object ban đầu.

char là kiểu nguyên thủy 16 bit dùng để biểu diễn một UTF-16 code unit. Một char có thể là:

- Một code unit biểu diễn một BMP code point.
- Một high surrogate.
- Một low surrogate.

Một char đơn lẻ không thể biểu diễn mọi Unicode code point. Khi cần giữ một code point bất kỳ, dùng int.

Ví dụ tạo String có emoji bằng API code point:

~~~java
int codePoint = 0x1F600;
String emoji = new String(Character.toChars(codePoint));
~~~

Character.toChars chuyển code point thành một hoặc hai char UTF-16. Với code point bổ sung, kết quả là một cặp high-surrogate/low-surrogate.

Không ép code point về char bằng cast:

~~~java
int codePoint = 0x1F600;
char truncated = (char) codePoint;
~~~

Phép cast trên chỉ giữ 16 bit thấp và làm mất dữ liệu. Nếu mục tiêu là tạo String, dùng Character.toChars hoặc StringBuilder.appendCodePoint.

## 3. length và charAt đếm code unit

String.length() trả về số UTF-16 code unit, không phải số Unicode code point.

String.charAt(index) trả về một char tại vị trí index. Nếu vị trí đó là một nửa của surrogate pair, phương thức trả về đúng surrogate đó; nó không tự ghép cặp.

Ví dụ với chuỗi A + U+1F600 + B:

~~~java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";

System.out.println(text.length());
System.out.println(text.charAt(1));
System.out.println(Character.isHighSurrogate(text.charAt(1)));
System.out.println(Character.isLowSurrogate(text.charAt(2)));
~~~

Kết quả:

~~~text
4
?
true
true
~~~

Dòng thứ hai có thể hiển thị ký tự thay thế hoặc một glyph không nhìn thấy được tùy console, font và encoding. Hai kết quả boolean cho thấy chỉ số 1 và 2 là hai nửa của cùng một code point.

Các API dùng chỉ số String như charAt, substring, subSequence, indexOf, lastIndexOf và getChars đều làm việc theo UTF-16 code unit. Đây là một phần của hợp đồng và không thay đổi khi JVM tối ưu bộ nhớ.

## 4. codePointAt, codePointBefore và codePointCount

Khi cần thao tác theo Unicode code point, dùng các API chuyên biệt:

~~~java
int cp = text.codePointAt(index);
int previous = text.codePointBefore(index);
int count = text.codePointCount(beginIndex, endIndex);
~~~

- codePointAt(index) đọc code point bắt đầu tại UTF-16 index.
- codePointBefore(index) đọc code point ngay trước UTF-16 index.
- codePointCount(beginIndex, endIndex) đếm code point trong vùng UTF-16 từ beginIndex đến endIndex, không bao gồm endIndex.

Điểm cần chú ý: tham số index của codePointAt và codePointBefore vẫn là UTF-16 index. codePointCount cũng nhận hai biên theo UTF-16 index. API trả về số code point hoặc giá trị code point, nhưng không thay đổi quy ước chỉ số của String.

Nếu codePointAt gặp high surrogate ngay trước low surrogate hợp lệ, nó kết hợp cặp thành một int. Nếu gặp surrogate không ghép cặp, nó trả về giá trị surrogate đó. codePointCount tính mỗi surrogate không ghép cặp là một code point trong vùng đếm.

## 5. chars và codePoints khác nhau

String cung cấp hai stream API thường dễ bị nhầm:

| API | Phần tử của stream | Supplementary code point |
|---|---|---|
| chars() | Các UTF-16 code unit được mở rộng thành int | Hai phần tử surrogate |
| codePoints() | Các Unicode code point | Một phần tử int |

Ví dụ:

~~~java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";

int[] units = text.chars().toArray();
int[] points = text.codePoints().toArray();
~~~

Với A😀B:

- chars() có bốn phần tử: U+0041, U+D83D, U+DE00, U+0042.
- codePoints() có ba phần tử: U+0041, U+1F600, U+0042.

Dùng chars() khi thuật toán thật sự cần từng code unit UTF-16, chẳng hạn xử lý định dạng dựa trên chỉ số char hoặc một giao thức xác định theo UTF-16. Dùng codePoints() khi thuật toán cần xử lý từng code point Unicode.

Không thay chars() bằng codePoints() một cách máy móc nếu thuật toán đang xử lý UTF-16 offsets. Cũng không dùng chars() khi mục tiêu là phân loại, đếm hoặc chuyển đổi code point.

## 6. Duyệt code point đúng cách

Cách đơn giản và dễ đọc là dùng IntStream:

~~~java
text.codePoints().forEach(codePoint -> {
    processCodePoint(codePoint);
});
~~~

Nếu cần vòng lặp thông thường, tăng index theo số UTF-16 code unit của code point vừa đọc:

~~~java
for (int index = 0; index < text.length();) {
    int codePoint = text.codePointAt(index);
    processCodePoint(codePoint);
    index += Character.charCount(codePoint);
}
~~~

Character.charCount trả về 1 cho code point nằm trong BMP và 2 cho supplementary code point. Với surrogate không ghép cặp, codePointAt trả về giá trị surrogate trong vùng BMP nên charCount vẫn là 1.

Không tăng index thêm 1 sau mỗi codePointAt nếu muốn bỏ qua toàn bộ supplementary code point. Làm vậy sẽ đọc lại low surrogate ở vòng kế tiếp như một giá trị riêng.

Nếu dùng codePoints() hoặc vòng lặp trên, vẫn phải xác định rõ thuật toán có chấp nhận surrogate không ghép cặp hay không. String có thể chứa chuỗi UTF-16 không well-formed; code point traversal không tự xác thực toàn bộ dữ liệu.

## 7. Chuyển đổi giữa code point và UTF-16 index

Một code point bổ sung chiếm hai code unit, do đó code point offset và String index không thể thay thế cho nhau.

String.offsetByCodePoints(index, offset) nhận:

- index: vị trí bắt đầu theo UTF-16 code unit.
- offset: số code point cần di chuyển.

Kết quả là một UTF-16 index:

~~~java
int end = text.offsetByCodePoints(0, 2);
String prefix = text.substring(0, end);
~~~

Với A😀B, di chuyển qua hai code point đầu tiên sẽ cho UTF-16 index 3. substring vẫn nhận chỉ số UTF-16, vì vậy prefix chứa A và emoji.

Nếu API bên ngoài trả về vị trí theo code point, cần chuyển vị trí đó sang UTF-16 index trước khi gọi substring hoặc charAt. Nếu API trả về UTF-16 index, không chuyển đổi lần nữa.

Các phép chuyển đổi như codePointCount và offsetByCodePoints có thể phải quét các code unit trong vùng cần đi qua. Không giả định chúng là phép tra cứu O(1). Trong vòng lặp hiệu năng nhạy cảm, giữ một UTF-16 cursor và tiến dần theo Character.charCount để tránh đếm lại từ đầu.

## 8. Code point không đồng nghĩa với ký tự người dùng nhìn thấy

Unicode code point là một đơn vị mã hóa logic, không phải lúc nào cũng là một ký tự hiển thị hoàn chỉnh.

Một glyph hoặc grapheme cluster có thể gồm nhiều code point:

- Chữ cái kết hợp với combining mark.
- Emoji cùng skin-tone modifier.
- Emoji gia đình hoặc nghề nghiệp nối bằng ZERO WIDTH JOINER.
- Cờ được tạo từ hai regional indicator.

Do đó, codePointCount không phải số ký tự người dùng nhìn thấy trên màn hình.

Nếu cần di chuyển con trỏ trong văn bản, cắt chuỗi theo ký tự hiển thị hoặc giới hạn số ký tự giao diện, cần xử lý grapheme boundary. BreakIterator.getCharacterInstance(Locale) là API trong JDK có thể dùng làm điểm bắt đầu cho việc tìm ranh giới ký tự; hãy kiểm thử các chuỗi combining mark, emoji modifier, ZWJ và regional indicator theo phiên bản Unicode mà ứng dụng cần hỗ trợ. Với yêu cầu phân đoạn grapheme đầy đủ theo Unicode hiện đại, chọn một implementation có cam kết phù hợp với phiên bản Unicode/UAX #29 của sản phẩm.

Không dùng length() hoặc codePointCount để áp đặt giới hạn số glyph trên giao diện.

## 9. So sánh String không tự chuẩn hóa Unicode

String.equals so sánh nội dung chuỗi theo các code unit. Nó không tự chuẩn hóa Unicode và không thực hiện so sánh theo locale.

Ví dụ, chữ é có thể được biểu diễn bằng:

- Một code point U+00E9.
- Hai code point U+0065 và U+0301.

Hai chuỗi này có thể hiển thị giống nhau nhưng có dãy code unit khác nhau, do đó equals trả về false trước khi chuẩn hóa.

Nếu nghiệp vụ cần so sánh theo canonical equivalence, dùng java.text.Normalizer với một normalization form đã chọn:

~~~java
String nfc = Normalizer.normalize(value, Normalizer.Form.NFC);
~~~

Chỉ chuẩn hóa khi hợp đồng dữ liệu yêu cầu. Normalization thay đổi chuỗi code unit, có thể ảnh hưởng đến hash, chữ ký số, offset, lưu trữ, khóa định danh hoặc dữ liệu gốc cần giữ nguyên. Không tự chuẩn hóa mọi chuỗi chỉ vì muốn tối ưu hoặc so sánh dễ hơn.

String.compareTo cũng không phải phép so sánh từ điển theo ngôn ngữ. Khi cần thứ tự hiển thị theo locale, dùng Collator và cấu hình locale phù hợp.

## 10. UTF-16 trong String và UTF-8 khi trao đổi dữ liệu

String biểu diễn nội dung theo UTF-16 code unit. Khi ghi ra file, gửi qua mạng hoặc lưu trong giao thức, dữ liệu phải được mã hóa thành byte theo một charset cụ thể.

Dùng charset tường minh:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

Không dựa vào charset mặc định của môi trường khi dữ liệu cần tương thích giữa máy, container, JVM hoặc hệ điều hành. Dùng StandardCharsets.UTF_8 cho giao thức yêu cầu UTF-8.

Ba đại lượng không giống nhau:

| Đại lượng của A😀B | Giá trị |
|---|---:|
| UTF-16 code unit (String.length) | 4 |
| Unicode code point | 3 |
| UTF-8 byte | 6 |

Nếu dữ liệu có thể chứa surrogate không ghép cặp và ứng dụng cần từ chối dữ liệu không hợp lệ, dùng CharsetEncoder với CodingErrorAction.REPORT. Các convenience method như String.getBytes(Charset) có thể thay thế chuỗi đầu vào không hợp lệ bằng replacement bytes của charset. Việc chọn REPLACE, IGNORE hay REPORT là quyết định của hợp đồng giao thức.

Ví dụ strict UTF-8 encoder:

~~~java
CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

ByteBuffer encoded = encoder.encode(CharBuffer.wrap(text));
~~~

Với REPORT, dữ liệu UTF-16 không well-formed sẽ gây CharacterCodingException thay vì bị âm thầm thay thế.

## 11. Compact Strings từ Java 9 và hợp đồng API

Java 9 giới thiệu Compact Strings trong HotSpot. Cách triển khai lưu trữ String dùng byte array cùng một coder để chọn cách biểu diễn phù hợp:

- Chuỗi có thể biểu diễn hoàn toàn bằng Latin-1 có thể lưu bằng một byte cho mỗi ký tự.
- Chuỗi cần phạm vi UTF-16 dùng biểu diễn UTF-16.

Mục tiêu là giảm footprint bộ nhớ của nhiều chuỗi phổ biến và cải thiện hiệu quả sử dụng cache. Đây là chi tiết triển khai của JVM, không phải một API để ứng dụng thao tác trực tiếp.

Compact Strings không thay đổi hợp đồng công khai:

- String.length vẫn đếm UTF-16 code unit.
- charAt vẫn trả về char theo UTF-16 index.
- substring vẫn nhận UTF-16 index.
- codePointAt và codePoints vẫn xử lý surrogate pair theo Unicode.
- equals và hashCode vẫn dựa trên nội dung String theo hợp đồng Java.

Không truy cập nội bộ String bằng reflection, Unsafe hoặc giả định rằng trường lưu trữ là char[]. Không suy ra số byte nội bộ từ length(), không giữ tham chiếu đến backing array và không phụ thuộc vào coder nội bộ. JVM có thể thay đổi cách lưu trữ mà không thay đổi hành vi API.

## 12. Giữ nguyên ngữ nghĩa khi tối ưu hiệu năng

Khi tối ưu xử lý chuỗi, trước tiên xác định đơn vị mà thuật toán phải giữ nguyên:

| Yêu cầu | Đơn vị/API phù hợp |
|---|---|
| Đọc hoặc cắt theo UTF-16 offset | charAt, substring, getChars |
| Xử lý từng code point | codePointAt, codePointBefore, codePoints |
| Đếm code point trong vùng | codePointCount |
| Di chuyển theo code point | offsetByCodePoints |
| Xây dựng code point supplementary | Character.toChars, StringBuilder.appendCodePoint |
| Xử lý UTF-8 bytes | StandardCharsets.UTF_8 |
| Kiểm tra dữ liệu UTF-16 không hợp lệ khi encode | CharsetEncoder với REPORT |
| So sánh canonical equivalent | Normalizer theo chính sách nghiệp vụ |
| Tìm ranh giới ký tự hiển thị | Grapheme segmentation phù hợp |

Các quy tắc thực tế:

1. Giữ nguyên đơn vị index ở API boundary. Nếu API nhận UTF-16 index, không âm thầm chuyển sang code point index.
2. Không cắt giữa high surrogate và low surrogate khi muốn giữ một code point nguyên vẹn.
3. Dùng int cho code point và char cho một UTF-16 code unit.
4. Dùng appendCodePoint khi thêm một code point vào StringBuilder.
5. Chỉ normalize khi hợp đồng dữ liệu yêu cầu.
6. Chọn charset tường minh khi chuyển String thành byte.
7. Kiểm tra surrogate không ghép cặp khi giao thức không chấp nhận dữ liệu đó.
8. Benchmark trên workload thực tế thay vì dựa vào suy đoán về backing array hoặc JIT.

Nếu mục tiêu là tăng tốc, hãy so sánh các implementation có cùng đầu vào, đầu ra và semantics. Một vòng lặp char có thể nhanh hơn nhưng sai nếu yêu cầu là xử lý từng code point. Tối ưu không được thay đổi đơn vị đếm, ranh giới, encoding hoặc dữ liệu quan sát được.

## 13. Ví dụ hoàn chỉnh: kiểm tra String, char và code point

**Tệp StringCodePointContractDemo.java:**

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.stream.Collectors;

public class StringCodePointContractDemo {
    private static String formatCodePoints(int[] values) {
        return Arrays.stream(values)
                .mapToObj(value -> String.format("U+%04X", value))
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        String text = "A" + new String(Character.toChars(0x1F600)) + "B";
        int[] units = text.chars().toArray();
        int[] codePoints = text.codePoints().toArray();
        int prefixEnd = text.offsetByCodePoints(0, 2);

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("code point count: "
                + text.codePointCount(0, text.length()));
        System.out.println("charAt(1) is high surrogate: "
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("charAt(2) is low surrogate: "
                + Character.isLowSurrogate(text.charAt(2)));
        System.out.println("codePointAt(1): U+"
                + Integer.toHexString(text.codePointAt(1)).toUpperCase());
        System.out.println("chars(): " + formatCodePoints(units));
        System.out.println("codePoints(): " + formatCodePoints(codePoints));
        System.out.println("UTF-16 index after 2 code points: " + prefixEnd);
        System.out.println("UTF-8 byte length: "
                + text.getBytes(StandardCharsets.UTF_8).length);

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("canonically equivalent before NFC: "
                + composed.equals(decomposed));
        System.out.println("canonically equivalent after NFC: "
                + Normalizer.normalize(composed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFC)));

        String unpaired = String.valueOf('\uD83D');
        System.out.println("unpaired surrogate code point count: "
                + unpaired.codePointCount(0, unpaired.length()));
        System.out.println("unpaired value is surrogate: "
                + Character.isSurrogate(unpaired.charAt(0)));
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all StringCodePointContractDemo.java
java StringCodePointContractDemo
~~~

Output:

~~~text
UTF-16 length: 4
code point count: 3
charAt(1) is high surrogate: true
charAt(2) is low surrogate: true
codePointAt(1): U+1F600
chars(): U+0041, U+D83D, U+DE00, U+0042
codePoints(): U+0041, U+1F600, U+0042
UTF-16 index after 2 code points: 3
UTF-8 byte length: 6
canonically equivalent before NFC: false
canonically equivalent after NFC: true
unpaired surrogate code point count: 1
unpaired value is surrogate: true
~~~

Ví dụ chứng minh String API giữ UTF-16 index ngay cả khi dùng code point API. chars() đưa ra hai surrogate riêng, còn codePoints() ghép chúng thành U+1F600. Chuỗi có surrogate không ghép cặp vẫn có thể tồn tại trong String và được codePointCount tính là một code point; nếu giao thức yêu cầu Unicode scalar values hợp lệ, ứng dụng phải xác thực riêng.

## 14. Lỗi thường gặp

- **Coi length() là số ký tự nhìn thấy:** length() đếm UTF-16 code unit.
- **Coi char là mọi Unicode character:** char chỉ chứa một code unit 16 bit.
- **Dùng char để giữ code point bổ sung:** dùng int hoặc cặp surrogate theo API.
- **Duyệt charAt và tăng 1 khi cần code point:** có thể xử lý hai nửa surrogate như hai phần tử riêng.
- **Cho rằng codePointAt nhận code point index:** tham số của nó vẫn là UTF-16 index.
- **Cho rằng codePointCount đếm glyph:** nó đếm code point, không đếm grapheme cluster.
- **Cho rằng codePoints() tự xác thực Unicode:** surrogate không ghép cặp vẫn được tính và trả về như một giá trị riêng.
- **Dùng substring với code point offset:** chuyển bằng offsetByCodePoints trước khi cắt.
- **Cắt chuỗi giữa surrogate pair:** có thể tạo chuỗi UTF-16 không well-formed.
- **Cho rằng equals tự chuẩn hóa Unicode:** equals so sánh nội dung chính xác; dùng Normalizer khi nghiệp vụ yêu cầu.
- **Dùng getBytes() không chỉ định charset:** kết quả có thể phụ thuộc cấu hình môi trường; chỉ định StandardCharsets.UTF_8 khi giao thức yêu cầu.
- **Âm thầm thay thế dữ liệu malformed:** dùng CharsetEncoder với REPORT khi cần từ chối dữ liệu không hợp lệ.
- **Dựa vào byte[] hoặc coder nội bộ của String:** đó là chi tiết triển khai, không phải hợp đồng ứng dụng.
- **Tối ưu char loop mà không đo và không kiểm tra semantics:** benchmark cùng kết quả và đơn vị xử lý trước khi thay implementation.

## 15. Ghi nhớ

String là chuỗi UTF-16 code unit immutable. length(), charAt(), substring() và các chỉ số String dùng UTF-16 index. char là một code unit; code point cần int và supplementary code point dùng hai surrogate. chars() trả từng code unit, còn codePoints() trả từng code point. Code point vẫn chưa phải grapheme cluster mà người dùng nhìn thấy. UTF-8 byte length là một đại lượng khác. Compact Strings của Java 9 tối ưu cách lưu trữ nhưng không thay đổi các hợp đồng API này. Khi tối ưu JVM, hãy giữ nguyên đơn vị đếm, index, encoding, normalization và cách xử lý surrogate mà ứng dụng cam kết.

## 16. Tài liệu tham khảo

- [String – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)
- [CharSequence – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/CharSequence.html)
- [Character – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html)
- [Normalizer – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html)
- [BreakIterator – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/BreakIterator.html)
- [CharsetEncoder – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html)
- [CodingErrorAction – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [JEP 254: Compact Strings](https://openjdk.org/jeps/254)
