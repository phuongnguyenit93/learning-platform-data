# Character.isEmoji và các thuộc tính emoji liên quan

Java 21 bổ sung các phương thức `Character.isEmoji()` và các phương thức kiểm tra thuộc tính emoji của Unicode. Chúng cho phép xác định một **Unicode code point** có thuộc tính emoji nào, chẳng hạn có phải emoji nói chung, có kiểu hiển thị emoji mặc định, là ký tự chỉ màu da hay có thể tham gia một thành phần của chuỗi emoji.

Các phương thức này kiểm tra thuộc tính của từng code point. Chúng không render emoji, không xác định font hoặc nền tảng có hình vẽ tương ứng hay không, và cũng không xác thực toàn bộ một emoji sequence như cờ quốc gia, keycap hoặc chuỗi nối bằng Zero Width Joiner (ZWJ). Khi xử lý `String`, cần duyệt theo code point thay vì giả định mỗi `char` là một ký tự Unicode hoàn chỉnh.

## 1. Các phương thức emoji trong `Character` của Java 21

Java 21 cung cấp năm phương thức static nhận tham số `int codePoint`:

| Phương thức | Ý nghĩa |
| --- | --- |
| `Character.isEmoji(int codePoint)` | Trả về `true` nếu code point có thuộc tính Unicode `Emoji`. |
| `Character.isEmojiPresentation(int codePoint)` | Trả về `true` nếu code point có thuộc tính `Emoji_Presentation`, tức mặc định được trình bày theo kiểu emoji. |
| `Character.isEmojiModifier(int codePoint)` | Trả về `true` nếu code point là emoji modifier, thường dùng cho các tông màu da. |
| `Character.isEmojiModifierBase(int codePoint)` | Trả về `true` nếu code point là một emoji base có thể kết hợp với emoji modifier. |
| `Character.isEmojiComponent(int codePoint)` | Trả về `true` nếu code point có thuộc tính `Emoji_Component`, tức là một thành phần được dùng trong một số emoji sequence. |

Các phương thức này được thêm từ Java 21 và dựa trên dữ liệu Unicode mà phiên bản Java đó hỗ trợ. API nhận `int` vì một Unicode code point có thể nằm ngoài vùng BMP và cần nhiều hơn một đơn vị `char` UTF-16 để biểu diễn.

Ví dụ kiểm tra một số code point:

```java
int grinningFace = 0x1F600;
int digitOne = 0x0031;
int thumbsUp = 0x1F44D;
int mediumSkinTone = 0x1F3FD;

System.out.println(Character.isEmoji(grinningFace));             // true
System.out.println(Character.isEmojiPresentation(grinningFace)); // true

System.out.println(Character.isEmoji(digitOne));                 // true
System.out.println(Character.isEmojiPresentation(digitOne));     // false

System.out.println(Character.isEmojiModifierBase(thumbsUp));     // true
System.out.println(Character.isEmojiModifier(mediumSkinTone));    // true
System.out.println(Character.isEmojiComponent(mediumSkinTone));   // true
```

Ví dụ chữ số `1` cho thấy `Emoji` và `Emoji_Presentation` là hai thuộc tính khác nhau. Chữ số có thể làm thành phần mở đầu của keycap emoji nên có thuộc tính `Emoji`, nhưng bản thân nó mặc định được hiển thị như văn bản, không phải emoji presentation.

## 2. Phân biệt Emoji và Emoji Presentation

`Emoji` cho biết code point được Unicode xem là một emoji hoặc có thể được dùng trong emoji sequence. Thuộc tính này không khẳng định ký tự sẽ luôn hiển thị bằng hình emoji.

`Emoji_Presentation` cho biết code point mặc định có kiểu hiển thị emoji. Một số ký tự có thuộc tính `Emoji` nhưng mặc định hiển thị dạng văn bản. Trong nội dung văn bản, ký tự Variation Selector-16 (`U+FE0F`) thường được dùng để yêu cầu kiểu hiển thị emoji; Variation Selector-15 (`U+FE0E`) yêu cầu kiểu hiển thị văn bản khi có hỗ trợ.

Ví dụ với ký tự bản quyền:

```java
int copyright = 0x00A9;

System.out.println(Character.isEmoji(copyright));             // true
System.out.println(Character.isEmojiPresentation(copyright)); // false

String textStyle = "\u00A9\uFE0E";
String emojiStyle = "\u00A9\uFE0F";

System.out.println(textStyle);
System.out.println(emojiStyle);
```

`Character.isEmojiPresentation(0x00A9)` chỉ kiểm tra thuộc tính mặc định của code point `©`. Phương thức này không nhận cả chuỗi nên không đánh giá tác động của `U+FE0E` hoặc `U+FE0F` trong chuỗi. Hình thức thực tế còn phụ thuộc font, hệ điều hành, trình duyệt và môi trường hiển thị.

Không nên dùng `isEmoji()` như điều kiện duy nhất để quyết định rằng một ký tự phải được render bằng font màu. Nếu cần biết mặc định Unicode, hãy xem thêm `isEmojiPresentation()`. Nếu cần xử lý nội dung chuỗi có variation selector, phải đọc và xử lý cả chuỗi code point theo quy tắc Unicode.

## 3. Emoji modifier và modifier base

Emoji modifier là các code point dùng để biểu diễn tông màu da. Unicode định nghĩa các modifier trong dải `U+1F3FB` đến `U+1F3FF`. Chúng thường không đứng độc lập như một emoji hoàn chỉnh mà được kết hợp với một emoji modifier base phù hợp.

```java
int wavingHand = 0x1F44B;
int mediumSkinTone = 0x1F3FD;

System.out.println(Character.isEmojiModifierBase(wavingHand)); // true
System.out.println(Character.isEmojiModifier(mediumSkinTone)); // true
```

Ví dụ chuỗi vẫy tay với tông màu da trung bình:

```java
String handWithSkinTone = "\uD83D\uDC4B\uD83C\uDFFD";
System.out.println(handWithSkinTone);
```

Chuỗi này gồm hai code point: emoji base `U+1F44B` và modifier `U+1F3FD`. Trong Java, `String.length()` trả về số đơn vị UTF-16, không phải số code point hay số ký tự emoji mà người dùng nhìn thấy.

`isEmojiModifierBase()` chỉ cho biết code point có thuộc tính modifier base. Nó không xác nhận một chuỗi bất kỳ gồm base và modifier là một sequence hợp lệ trong mọi ngữ cảnh. Muốn xác thực sequence phải áp dụng quy tắc emoji sequence của Unicode.

## 4. Emoji Component và vai trò trong sequence

`Emoji_Component` là thuộc tính dành cho code point được dùng làm thành phần của một số emoji sequence. Ví dụ thường gặp gồm emoji modifier, regional indicator, keycap combining mark, variation selector và ZWJ. Một component có thể không tạo thành hình emoji độc lập khi đứng riêng.

```java
int skinTone = 0x1F3FD;
int zeroWidthJoiner = 0x200D;
int variationSelector16 = 0xFE0F;
int keycapMark = 0x20E3;

System.out.println(Character.isEmojiComponent(skinTone));             // true
System.out.println(Character.isEmojiComponent(zeroWidthJoiner));      // true
System.out.println(Character.isEmojiComponent(variationSelector16));  // true
System.out.println(Character.isEmojiComponent(keycapMark));          // true
```

Không đồng nhất `Emoji_Component` với `Emoji`. Một số code point là thành phần kỹ thuật của sequence nhưng không phải emoji độc lập. Vì vậy, khi xây dựng bộ lọc, bộ đếm hoặc quy tắc nhập liệu, cần xác định rõ mục tiêu là tìm code point có thuộc tính `Emoji`, tìm thành phần sequence hay nhận diện một emoji sequence hoàn chỉnh.

## 5. Duyệt chuỗi theo Unicode code point

Java biểu diễn `String` bằng UTF-16. Một code point trong vùng BMP thường chiếm một `char`; code point ngoài BMP được mã hóa bằng một cặp surrogate gồm hai `char`. Emoji phổ biến nằm ngoài BMP nên nhiều emoji có `String.length() == 2` dù chỉ là một code point.

Không nên duyệt emoji bằng `charAt()` hoặc `chars()` rồi truyền từng `char` vào `Character.isEmoji()`. Cách đó sẽ tách một cặp surrogate thành hai giá trị riêng và không còn code point gốc.

Dùng `String.codePoints()` để duyệt đúng code point:

```java
String face = "\uD83D\uDE00"; // U+1F600

System.out.println(face.length());                  // 2 đơn vị UTF-16
System.out.println(face.codePointCount(0, face.length())); // 1 code point

face.codePoints().forEach(codePoint -> {
    System.out.printf(
            "U+%04X: emoji=%s, presentation=%s%n",
            codePoint,
            Character.isEmoji(codePoint),
            Character.isEmojiPresentation(codePoint)
    );
});
```

Nếu cần xử lý bằng vòng lặp chỉ số, dùng `codePointAt()` và tăng chỉ số theo `Character.charCount(codePoint)`:

```java
String value = "A\uD83D\uDE00B";

for (int index = 0; index < value.length();) {
    int codePoint = value.codePointAt(index);
    System.out.printf("U+%04X%n", codePoint);
    index += Character.charCount(codePoint);
}
```

`codePoints()` và `codePointAt()` xử lý surrogate pair đúng cách. Chúng không gộp nhiều code point thành một grapheme cluster hoặc emoji sequence. Đây là hai cấp độ khác nhau: code point là đơn vị mã Unicode, còn grapheme cluster gần với một ký tự mà người dùng cảm nhận khi đọc.

## 6. Một emoji hiển thị có thể gồm nhiều code point

Một emoji sequence có thể chứa nhiều code point nhưng được font và nền tảng hiển thị như một biểu tượng. Một số dạng thường gặp:

| Dạng sequence | Thành phần thường dùng | Ví dụ |
| --- | --- | --- |
| Emoji có variation selector | Emoji base + `U+FE0F` | `©️` |
| Emoji có tông màu da | Modifier base + emoji modifier | `👍🏽` |
| ZWJ sequence | Emoji + `U+200D` + emoji khác | `👩🏽‍💻` |
| Cờ quốc gia | Hai regional indicator | `🇻🇳` |
| Keycap | Chữ số hoặc `#`/`*`, variation selector tùy dạng, `U+20E3` | `1️⃣` |

Có thể duyệt các code point của một chuỗi ZWJ để quan sát từng thành phần:

```java
String technologist = "\uD83D\uDC69\uD83C\uDFFD\u200D\uD83D\uDCBB";

technologist.codePoints().forEach(codePoint -> {
    System.out.printf(
            "U+%04X emoji=%s component=%s modifierBase=%s modifier=%s%n",
            codePoint,
            Character.isEmoji(codePoint),
            Character.isEmojiComponent(codePoint),
            Character.isEmojiModifierBase(codePoint),
            Character.isEmojiModifier(codePoint)
    );
});
```

Đây là chuỗi gồm người phụ nữ, modifier tông màu da, ZWJ và máy tính. Các phương thức `Character` đánh giá từng code point riêng lẻ. Chúng không xác nhận rằng toàn bộ chuỗi tuân theo quy tắc RGI emoji sequence, cũng không đảm bảo font hiện tại có glyph ghép đúng thành một biểu tượng.

Ví dụ cờ Việt Nam gồm hai regional indicator:

```java
String vietnamFlag = "\uD83C\uDDFB\uD83C\uDDF3";

vietnamFlag.codePoints().forEach(codePoint ->
        System.out.println(Character.isEmoji(codePoint))
);
```

Mỗi regional indicator có thể mang thuộc tính emoji, nhưng một cờ quốc gia cần một cặp indicator hợp lệ. Một regional indicator riêng lẻ không tự đại diện cho một cờ quốc gia. Tương tự, chữ số `1` có thuộc tính `Emoji`, nhưng chỉ chuỗi keycap đầy đủ mới tạo dạng keycap.

## 7. Đếm code point có thuộc tính emoji không đồng nghĩa đếm emoji hiển thị

Có thể dùng stream để đếm số code point có thuộc tính `Emoji`:

```java
String text = "A😀B👍🏽C";

long emojiCodePointCount = text.codePoints()
        .filter(Character::isEmoji)
        .count();

System.out.println(emojiCodePointCount);
```

Kết quả là số code point có thuộc tính `Emoji`, không phải số biểu tượng emoji mà người dùng nhìn thấy. Với `👍🏽`, base và modifier là hai code point nhưng thường hiển thị như một grapheme cluster. Với cờ, keycap hoặc ZWJ sequence, một biểu tượng cũng có thể gồm nhiều code point.

Tương tự, lọc bỏ mọi code point có `isEmoji()` trả về `true` có thể phá vỡ chuỗi. Ví dụ, xóa riêng modifier hoặc regional indicator có thể để lại phần văn bản không còn là sequence hợp lệ. Nếu yêu cầu sản phẩm là giới hạn số ký tự hiển thị, cắt chuỗi, hoặc kiểm duyệt emoji sequence, hãy xử lý theo grapheme cluster và quy tắc Unicode Emoji, không chỉ đếm code point.

## 8. Dữ liệu Unicode của Java 21 và giới hạn phiên bản

Các thuộc tính ký tự mà `Character` sử dụng gắn với phiên bản Unicode được triển khai trong JDK. Java 21 dựa trên Unicode 15.0.0. Do đó, một code point được bổ sung trong phiên bản Unicode mới hơn có thể chưa được nhận diện bằng các thuộc tính emoji của `Character` trong Java 21, ngay cả khi font hoặc nền tảng khác đã hiển thị được ký tự đó.

Khi nâng cấp JDK, dữ liệu Unicode và kết quả kiểm tra thuộc tính có thể thay đổi theo phiên bản Java mới. Nếu ứng dụng cần hành vi nhất quán giữa các máy chạy nhiều JDK, hãy xác định phiên bản Unicode mục tiêu và kiểm thử tập code point/sequence theo yêu cầu sản phẩm. Không suy luận rằng API `Character` của Java 21 luôn nhận diện mọi emoji được Unicode công bố sau Unicode 15.0.

## 9. Lỗi thường gặp

| Cách làm hoặc giả định | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Truyền từng `char` vào `Character.isEmoji(int)` cho mọi ký tự | Code point ngoài BMP bị tách thành hai surrogate, không còn giá trị code point gốc. | Duyệt bằng `String.codePoints()` hoặc `codePointAt()`. |
| Nghĩ `isEmoji()` đồng nghĩa mặc định hiển thị emoji | Một số ký tự như chữ số có thuộc tính `Emoji` nhưng không có `Emoji_Presentation`. | Kiểm tra thêm `isEmojiPresentation()` và variation selector trong chuỗi khi cần. |
| Nghĩ `isEmojiComponent()` xác nhận một emoji hoàn chỉnh | Component có thể chỉ là ZWJ, variation selector hoặc modifier. | Phân tích sequence theo quy tắc Unicode Emoji. |
| Đếm `isEmoji()` rồi gọi đó là số emoji nhìn thấy | Một emoji hiển thị có thể gồm nhiều code point. | Phân biệt code point, grapheme cluster và emoji sequence. |
| Xóa từng code point có thuộc tính emoji | Có thể để lại ZWJ, modifier hoặc regional indicator rời rạc. | Xử lý toàn bộ grapheme cluster/emoji sequence theo yêu cầu. |
| Cho rằng JDK 21 nhận mọi emoji mới nhất | Dữ liệu Unicode của Java 21 gắn với Unicode 15.0.0. | Kiểm tra phiên bản Unicode của JDK và chọn phiên bản Java phù hợp. |
| Cho rằng `Character` quyết định hình emoji trên màn hình | API chỉ cung cấp thuộc tính Unicode, không điều khiển font hay renderer. | Kiểm thử trên môi trường hiển thị thực tế. |

## 10. Tài liệu tham khảo chính thức

- [Java SE 21 API — `Character`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html): các phương thức `isEmoji`, `isEmojiPresentation`, `isEmojiModifier`, `isEmojiModifierBase`, `isEmojiComponent` và thông tin Unicode của JDK.
- [Java SE 21 API — `String.codePoints()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#codePoints()): duyệt chuỗi theo Unicode code point.
- [Unicode Technical Standard #51 — Unicode Emoji](https://www.unicode.org/reports/tr51/): emoji properties, modifier, variation selector, ZWJ và emoji sequence.
- [Unicode 15.0.0 — Emoji Data](https://www.unicode.org/Public/15.0.0/ucd/emoji/emoji-data.txt): dữ liệu thuộc tính emoji được dùng làm cơ sở cho Unicode 15.0.
