# indexOf với ký tự hoặc Unicode code point trong Java String

Trong Java, **String.indexOf(int ch)** tìm lần xuất hiện đầu tiên của một ký tự hoặc một Unicode code point trong chuỗi; **String.indexOf(int ch, int fromIndex)** tìm từ một vị trí UTF-16 được chỉ định. Cả hai phương thức trả về **vị trí bắt đầu trong dãy đơn vị mã UTF-16** hoặc **-1 nếu không tìm thấy**.

Điểm dễ nhầm là đối số có kiểu **int**, không chỉ là char. Vì vậy, chúng có thể tìm những code point Unicode nằm ngoài BMP (Basic Multilingual Plane) và chiếm **hai đơn vị mã UTF-16**, chẳng hạn emoji 😀 (U+1F600). Tuy nhiên, vị trí trả về vẫn là **chỉ số UTF-16**, không phải số thứ tự code point hoặc số ký tự người dùng nhìn thấy.

## 1. Cú pháp và ý nghĩa

Java cung cấp hai overload liên quan trực tiếp:

~~~java
int indexOf(int ch)
int indexOf(int ch, int fromIndex)
~~~

Đây là **chữ ký API để học**, không phải phương thức cần tự định nghĩa. Hai overload đều trả về int:

- **indexOf(ch)**: tìm giá trị ch từ đầu chuỗi; nếu xuất hiện nhiều lần, trả vị trí bắt đầu của lần đầu tiên.
- **indexOf(ch, fromIndex)**: chỉ xem xét các lần xuất hiện có vị trí bắt đầu từ **fromIndex trở đi**.
- **Tìm thấy**: trả về chỉ số UTF-16 của lần khớp.
- **Không tìm thấy**: trả về **-1**; đây là giá trị báo không có kết quả, không phải một chỉ số hợp lệ.
- **Không sửa chuỗi**: String bất biến, indexOf() chỉ đọc nội dung.

Với ch nằm trong BMP, hành vi về cơ bản là tìm đơn vị mã char có giá trị bằng ch. Với ch là code point bổ sung từ **U+10000 đến U+10FFFF**, phương thức tìm **cặp high surrogate + low surrogate** tương ứng và trả chỉ số của high surrogate. Với giá trị ch âm hoặc lớn hơn **U+10FFFF**, không có code point hợp lệ để tìm nên kết quả là -1.

## 2. Tìm một ký tự BMP bằng char

Trong Java, literal như **'a'**, **'J'**, **'?'**, **'7'** có kiểu char. Khi truyền cho indexOf(int), Java tự nâng giá trị char sang int. Bạn không cần ép kiểu.

~~~java
String text = "Java Java";

System.out.println(text.indexOf('J'));     // 0
System.out.println(text.indexOf('a'));     // 1
System.out.println(text.indexOf('v'));     // 2
System.out.println(text.indexOf('z'));     // -1
System.out.println(text.indexOf('J', 1));  // 5
~~~

Giải thích: chữ 'J' xuất hiện tại vị trí 0 và 5; indexOf('J') lấy vị trí 0, còn indexOf('J', 1) bỏ qua vị trí 0 và tìm vị trí 5. Nếu không có giá trị cần tìm, trả về -1.

**Không có sự khác biệt về kết quả giữa giá trị char 'J' và int 74** khi tìm trong chuỗi này:

~~~java
String text = "Java";
System.out.println(text.indexOf('J')); // 0
System.out.println(text.indexOf(74));  // 0
~~~

74 chính là code point U+004A của chữ J. Tuy nhiên, nên dùng literal char khi muốn thể hiện một ký tự BMP dễ nhận biết và dùng mã code point dạng int khi xử lý Unicode tổng quát.

### Phân biệt chữ hoa và chữ thường

indexOf() tìm **đúng giá trị ký tự/code point**; nó không tự bỏ qua hoa/thường:

~~~java
String text = "Java";
System.out.println(text.indexOf('J')); // 0
System.out.println(text.indexOf('j')); // -1
~~~

Nếu nghiệp vụ cần tìm không phân biệt hoa/thường, phải xác định một quy tắc xử lý thích hợp. Việc tự chuyển toàn bộ chuỗi sang lowercase/uppercase có thể chịu ảnh hưởng của locale hoặc biến đổi số lượng ký tự; không nên mặc định phép chuyển đổi đó bảo toàn chỉ số UTF-16 trong mọi trường hợp.

## 3. Vì sao kết quả là UTF-16 index, không phải thứ tự code point?

Java String sử dụng các **đơn vị mã UTF-16**. Một code point trong BMP thường chiếm một đơn vị mã; code point bổ sung ngoài BMP chiếm **hai** đơn vị mã: high surrogate rồi low surrogate.

Xét chuỗi:

~~~java
String text = "A😀B😀";
~~~

Nội dung gồm bốn Unicode code point theo thứ tự: A, 😀, B, 😀.

| UTF-16 index | Đơn vị mã | Ý nghĩa |
|---:|---|---|
| 0 | U+0041 | A |
| 1 | U+D83D | High surrogate của 😀 thứ nhất |
| 2 | U+DE00 | Low surrogate của 😀 thứ nhất |
| 3 | U+0042 | B |
| 4 | U+D83D | High surrogate của 😀 thứ hai |
| 5 | U+DE00 | Low surrogate của 😀 thứ hai |

Vì vậy:

- **text.length() = 6**: sáu đơn vị mã UTF-16.
- **text.codePointCount(0, text.length()) = 4**: bốn Unicode code point.
- **text.indexOf('B') = 3**: B là code point thứ ba nếu đếm từ 1, nhưng bắt đầu tại UTF-16 index 3.
- **text.indexOf(0x1F600) = 1**: emoji đầu tiên bắt đầu ở high surrogate index 1.
- **text.indexOf(0x1F600, 2) = 4**: vị trí bắt đầu 1 nhỏ hơn fromIndex 2, nên bỏ qua emoji đầu và tìm emoji thứ hai tại index 4.

Số thứ tự code point, vị trí UTF-16 và cụm ký tự hiển thị (grapheme cluster) là các khái niệm khác nhau. indexOf() trả về **UTF-16 offset**.

## 4. Tìm code point ngoài BMP bằng int

Một emoji như 😀 tương ứng **U+1F600** và có giá trị thập phân 128512. Giá trị đó lớn hơn giới hạn của char, nên cần biểu diễn bằng **int**.

~~~java
String text = "A😀B😀";
int smile = 0x1F600;

System.out.println(text.indexOf(smile));      // 1
System.out.println(text.indexOf(smile, 2));   // 4
System.out.println(text.indexOf(smile, 4));   // 4
System.out.println(text.indexOf(smile, 5));   // -1
~~~

Ở lần tìm cuối, fromIndex=5 trỏ vào low surrogate của emoji thứ hai. **Vị trí bắt đầu** của cả hai cặp emoji là 1 và 4, đều nhỏ hơn 5; do đó không tìm được cặp bắt đầu tại hoặc sau index 5.

Một literal char chỉ lưu một đơn vị mã 16 bit, nên **không thể viết** một emoji bổ sung trực tiếp như char '😀'. Hãy dùng int 0x1F600, Character.toCodePoint(high, low) khi đã có cặp surrogate, hoặc một API trả về code point dạng int.

Ví dụ tạo giá trị tìm kiếm từ chính chuỗi:

~~~java
String text = "A😀B";
int emojiCodePoint = text.codePointAt(1);
System.out.printf("U+%X%n", emojiCodePoint); // U+1F600
System.out.println(text.indexOf(emojiCodePoint)); // 1
~~~

**Điểm quan trọng:** codePointAt(1) trả về U+1F600 nhờ ghép cặp surrogate đúng; indexOf(emojiCodePoint) tìm cả cặp này. Cần phân biệt với text.charAt(1), vốn chỉ trả về high surrogate.

## 5. Chỉ số fromIndex: bao gồm vị trí bắt đầu

Với **indexOf(ch, fromIndex)**, Java tìm lần xuất hiện đầu tiên có chỉ số bắt đầu **lớn hơn hoặc bằng fromIndex**. Chính vị trí fromIndex vẫn nằm trong phạm vi tìm kiếm.

~~~java
String text = "ABABA";

System.out.println(text.indexOf('A'));      // 0
System.out.println(text.indexOf('A', 0));   // 0
System.out.println(text.indexOf('A', 1));   // 2
System.out.println(text.indexOf('A', 2));   // 2
System.out.println(text.indexOf('A', 3));   // 4
System.out.println(text.indexOf('A', 5));   // -1
~~~

Những lưu ý về ranh giới:

- **fromIndex âm**: việc tìm kiếm bắt đầu tương đương vị trí 0.
- **fromIndex bằng 0**: tương đương tìm từ đầu chuỗi.
- **fromIndex >= length()**: với overload tìm ch, không còn vị trí bắt đầu hợp lệ, nên trả về -1.
- **Chuỗi rỗng**: không có code unit để khớp, nên indexOf(int ch) luôn trả về -1.
- **fromIndex là UTF-16 offset**, không phải số thứ tự Unicode code point.

Tìm code point bổ sung đòi hỏi hai đơn vị mã liền nhau. Nếu fromIndex rơi vào giữa một cặp (tại low surrogate), cặp có high surrogate phía trước fromIndex sẽ **không** được coi là một lần khớp mới bắt đầu từ fromIndex.

## 6. Một code point hợp lệ khác với một surrogate code unit

Đối số int của indexOf() có hai cách được xử lý tùy miền giá trị:

| Đối số ch | Cách Java tìm |
|---|---|
| 0 đến U+FFFF | So khớp một đơn vị mã UTF-16 có giá trị bằng ch |
| U+10000 đến U+10FFFF | So khớp cặp surrogate UTF-16 hợp lệ biểu diễn ch |
| ch âm hoặc ch > U+10FFFF | Không có kết quả: -1 |

Trong dải **U+D800 đến U+DFFF**, các giá trị là surrogate code unit, **không phải Unicode scalar value độc lập**. Tuy nhiên, vì nằm trong miền 0 đến U+FFFF, indexOf(int) vẫn có thể tìm được riêng high/low surrogate trong chuỗi.

~~~java
String text = "A😀B";

System.out.println(text.indexOf(0xD83D));   // 1: high surrogate
System.out.println(text.indexOf(0xDE00));   // 2: low surrogate
System.out.println(text.indexOf(0x1F600));  // 1: cặp đầy đủ
System.out.println(text.indexOf(0x110000)); // -1: ngoài miền Unicode
~~~

Đây là khác biệt hữu ích khi gỡ lỗi UTF-16:

- Tìm **0xD83D** chỉ xác định đơn vị mã high surrogate, chưa chứng minh đó là emoji 😀 hoàn chỉnh.
- Tìm **0x1F600** yêu cầu **cả cặp** high surrogate U+D83D và low surrogate U+DE00 liền nhau.
- Với String có surrogate đơn lẻ hoặc cặp không hợp lệ, việc tìm một đơn vị mã surrogate vẫn có thể có kết quả; tìm code point bổ sung tương ứng sẽ không khớp cặp không hợp lệ.

Để kiểm tra giá trị bổ sung là code point hợp lệ, có thể dùng Character.isValidCodePoint(int); nếu nghiệp vụ yêu cầu **Unicode scalar value**, còn phải loại trừ dải surrogate U+D800–U+DFFF.

## 7. Chương trình đầy đủ Java 17+

Lưu tệp **StringIndexOfCodePointDemo.java** bằng UTF-8:

~~~java
public class StringIndexOfCodePointDemo {
    public static void main(String[] args) {
        String text = "A😀B😀";
        int emoji = 0x1F600;

        System.out.println("length=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));

        System.out.println("A=" + text.indexOf('A'));
        System.out.println("B=" + text.indexOf('B'));
        System.out.println("missing=" + text.indexOf('X'));

        System.out.println("emoji-first=" + text.indexOf(emoji));
        System.out.println("emoji-from-2=" + text.indexOf(emoji, 2));
        System.out.println("emoji-from-4=" + text.indexOf(emoji, 4));
        System.out.println("emoji-from-5=" + text.indexOf(emoji, 5));

        System.out.println("high=" + text.indexOf(0xD83D));
        System.out.println("low=" + text.indexOf(0xDE00));
        System.out.println("invalid=" + text.indexOf(0x110000));

        int found = text.indexOf(emoji);
        if (found >= 0) {
            System.out.printf("found=U+%X%n", text.codePointAt(found));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StringIndexOfCodePointDemo.java
java StringIndexOfCodePointDemo
~~~

Đầu ra chính xác:

~~~text
length=6
codePoints=4
A=0
B=3
missing=-1
emoji-first=1
emoji-from-2=4
emoji-from-4=4
emoji-from-5=-1
high=1
low=2
invalid=-1
found=U+1F600
~~~

**Giải thích kết quả:**

1. length=6 vì có hai emoji, mỗi emoji chiếm hai đơn vị mã UTF-16.
2. codePoints=4 vì nội dung gồm A, emoji, B, emoji.
3. 'B' nằm tại UTF-16 index 3, dù là code point thứ ba tính từ đầu.
4. Chỉ số của hai emoji là 1 và 4, tức vị trí **đầu cặp surrogate**.
5. fromIndex=2 bỏ qua cặp bắt đầu ở 1; fromIndex=5 bỏ qua cả cặp bắt đầu ở 4.
6. 0xD83D và 0xDE00 được xử lý như giá trị đơn vị mã riêng; 0x110000 nằm ngoài miền Unicode.
7. Chỉ sau khi bảo đảm found >= 0, chương trình mới gọi codePointAt(found) để đọc code point khớp, tránh sử dụng -1 làm chỉ số.

Chương trình không dựa vào cách console vẽ emoji để xác minh kết quả: code point được in dưới dạng U+1F600.

## 8. Tìm tất cả lần xuất hiện của một code point

Khi cần mọi vị trí, có thể gọi indexOf(ch, fromIndex) trong vòng lặp và cập nhật **fromIndex** sau mỗi lần tìm thấy. Với code point bổ sung, nên nhảy qua toàn bộ cặp UTF-16 vừa khớp để tránh lặp lại và để thể hiện rõ điểm bắt đầu tìm tiếp.

Ví dụ độc lập, lưu **AllCodePointMatches.java**:

~~~java
public class AllCodePointMatches {
    public static void main(String[] args) {
        String text = "😀x😀y😀";
        int target = 0x1F600;
        int fromIndex = 0;

        while (true) {
            int found = text.indexOf(target, fromIndex);
            if (found == -1) {
                break;
            }
            System.out.println("match at UTF-16 index " + found);
            fromIndex = found + Character.charCount(target);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AllCodePointMatches.java
java AllCodePointMatches
~~~

Kết quả:

~~~text
match at UTF-16 index 0
match at UTF-16 index 3
match at UTF-16 index 6
~~~

Vì mỗi emoji chiếm hai đơn vị mã, chuỗi "😀x😀y😀" có các vị trí bắt đầu là 0, 3, 6. Hàm Character.charCount(0x1F600) trả 2; sau mỗi lần tìm, fromIndex được chuyển qua emoji đã khớp.

Nếu mục tiêu là **mọi lần xuất hiện có thể chồng lấn** của một mẫu chuỗi, chính sách di chuyển con trỏ có thể khác. Ví dụ trên chỉ xử lý từng code point đơn lẻ và lấy những lần xuất hiện tiếp theo.

### Khi chỉ cần duyệt từng code point, không phải tìm một giá trị

String.codePoints() cung cấp IntStream các code point; thích hợp để xử lý **toàn bộ** code point mà không cần xác định vị trí UTF-16. Nếu cần biết chính xác vị trí bắt đầu khớp trong String, indexOf(int) hoặc vòng lặp duyệt chỉ số UTF-16 sẽ phù hợp hơn.

## 9. Phân biệt indexOf(int) với indexOf(String)

String còn có overload **indexOf(String str)** và **indexOf(String str, int fromIndex)** để tìm **cả một chuỗi con**, khác với tìm một code point bằng int.

Ví dụ:

~~~java
String text = "abcabc";

System.out.println(text.indexOf('a'));     // 0: một ký tự
System.out.println(text.indexOf("ab"));    // 0: chuỗi con
System.out.println(text.indexOf("bc", 3)); // 4: chuỗi con từ index 3
~~~

Với emoji ngoài BMP, có thể tạo String biểu diễn code point bằng:

~~~java
int cp = 0x1F600;
String emoji = new String(Character.toChars(cp));
String text = "A😀B";

System.out.println(text.indexOf(cp));    // 1
System.out.println(text.indexOf(emoji)); // 1
~~~

Kết quả giống nhau ở ví dụ, nhưng **kiểu tham số quyết định overload**: int tìm một code point (hoặc một đơn vị mã BMP), String tìm một dãy đơn vị mã. Đừng vô tình tìm chuỗi ký tự chữ số "128512" khi mục tiêu là emoji có code point 128512.

**Lưu ý sự khác nhau về chuỗi rỗng:** tìm "" bằng overload indexOf(String) có quy tắc khớp chuỗi rỗng tại một vị trí hợp lệ; tìm int không có khái niệm “code point rỗng”. Các quy tắc trên về fromIndex >= length() áp dụng cho **indexOf(int ch, int fromIndex)**; không tự áp dụng nguyên xi sang overload indexOf(String, int).

## 10. Sai lầm thường gặp và cách tránh

1. **Dùng '😀' làm char literal:** một char chỉ chứa một đơn vị mã UTF-16; emoji U+1F600 cần hai đơn vị mã. Dùng int 0x1F600.
2. **Hiểu kết quả là số thứ tự code point:** giá trị trả về của indexOf() là UTF-16 index. Với "A😀B", 'B' ở vị trí 3.
3. **Nhầm fromIndex với thứ tự code point:** fromIndex=2 bắt đầu tìm từ UTF-16 index 2, không có nghĩa bỏ qua hai Unicode code point.
4. **Xem -1 là vị trí bình thường:** trước khi dùng kết quả với charAt(), codePointAt(), substring(), cần kiểm tra result >= 0.
5. **Cho rằng indexOf(0xD83D) có nghĩa tìm trọn emoji 😀:** đó chỉ là tìm high surrogate; muốn trọn code point dùng 0x1F600.
6. **Mong indexOf() không phân biệt hoa/thường, tự bỏ dấu hoặc chuẩn hóa Unicode:** nó tìm giá trị theo dãy đơn vị mã; các quy tắc so khớp mở rộng phải được thiết kế riêng.
7. **Thấy String.indexOf('x') và String.indexOf("x") mà nghĩ mọi quy tắc đều giống nhau:** tham số char được nâng thành int, còn "x" là String; các overload khác nhau, đặc biệt ở quy tắc tìm chuỗi rỗng.
8. **Tính index theo số ký tự hiển thị:** emoji có thể ghép nhiều code point và dấu kết hợp; UTF-16 index không trực tiếp tương ứng vị trí hiển thị.
9. **Cắt chuỗi tại chỉ số tưởng là biên code point:** nếu nhận kết quả indexOf(int) là đầu cặp surrogate, muốn lấy trọn code point bổ sung cần kết thúc tại start + Character.charCount(ch), không mặc định start + 1.
10. **Dùng kết quả tìm chuỗi Unicode làm chỉ số cho hệ khác:** các thư viện hoặc giao thức có thể đo offset theo UTF-8 bytes, code points hoặc grapheme clusters; cần quy đổi minh bạch trước khi trao đổi chỉ số.

## 11. Bài tập tự kiểm tra

Với:

~~~java
String s = "x😀y😀";
~~~

Hãy tự dự đoán:

1. s.length() và s.codePointCount(0, s.length()) bằng bao nhiêu?
2. s.indexOf('y') bằng bao nhiêu?
3. s.indexOf(0x1F600) bằng bao nhiêu?
4. s.indexOf(0x1F600, 2) bằng bao nhiêu?
5. s.indexOf(0x1F600, 5) bằng bao nhiêu?
6. s.indexOf(0xD83D) có nhất thiết là kiểm tra trọn một emoji 😀 hay không?

**Đáp án và lý do:**

1. **6 và 4**: x, emoji, y, emoji có 4 code point nhưng 6 đơn vị mã UTF-16.
2. **3**: x ở 0; emoji đầu chiếm 1–2; y bắt đầu ở 3.
3. **1**: emoji đầu có high surrogate tại 1.
4. **4**: bỏ qua cặp bắt đầu ở 1, tìm cặp thứ hai tại 4.
5. **-1**: fromIndex 5 nằm sau điểm bắt đầu cuối cùng 4.
6. **Không**: 0xD83D chỉ yêu cầu khớp một đơn vị mã high surrogate, không xác nhận cả cặp U+D83D U+DE00.

**Kết luận:** dùng **indexOf(int ch)** để tìm ký tự BMP hoặc Unicode code point; dùng **indexOf(int ch, int fromIndex)** khi cần tìm tiếp từ một offset. Khi tìm code point bổ sung, Java so khớp **cặp surrogate**, nhưng **mọi chỉ số trả về và fromIndex vẫn đo bằng đơn vị mã UTF-16**. Luôn kiểm tra **-1** và cẩn thận với ranh giới cặp surrogate.
