# Chuẩn hóa Unicode và lựa chọn so khớp theo ký tự hay đơn vị mã

**Tìm kiếm chuỗi** không chỉ là tìm một dãy ký tự giống nhau. Với dữ liệu Unicode, trước khi so khớp ta phải quyết định: **đơn vị nào được xem là một phần tử**, hai chuỗi “giống nhau” theo **cách hiểu nào**, và **chỉ số kết quả** được đo trên chuỗi nào. Cùng một văn bản có thể dài 6 đơn vị mã UTF-16, 4 Unicode code point và 4 grapheme cluster; hai chuỗi nhìn giống hệt nhau có thể khác các byte hoặc mã Unicode; một phép chuẩn hóa có thể rút ngắn hoặc làm dài chuỗi, khiến offset sau chuẩn hóa **không còn là offset trên chuỗi gốc**.

Bài học này thuộc nhóm **Tìm kiếm chuỗi** của Computer Science Algorithms. Nội dung tập trung vào **chuẩn hóa Unicode và lựa chọn so khớp theo ký tự hay đơn vị mã**: UTF-8 byte, UTF-16 code unit, Unicode code point, extended grapheme cluster, so khớp chính xác và tương đương chuẩn hóa, NFC/NFD/NFKC/NFKD, vị trí/biên giới chồng lấn, xử lý emoji/chữ có dấu, mã Java 17+ chạy độc lập, kiểm thử và lưu ý về bảo toàn offset.

## 1. Vấn đề: “một ký tự” có thể có bốn cách đếm khác nhau

Lấy văn bản `"A🙂B🙂"`. Người đọc thường thấy bốn hình/ký tự: A, 🙂, B, 🙂. Nhưng trong Java:

- `text.length() = 6`: Java `String` đếm **đơn vị mã UTF-16**.
- `text.codePointCount(0, text.length()) = 4`: đếm **code point** của chuỗi Unicode hợp lệ.
- Nếu phân đoạn theo extended grapheme cluster, ta nhận **4 cụm**.
- Nếu mã hóa thành UTF-8, số byte là **10**: A một byte, hai emoji mỗi emoji bốn byte, B một byte. Số byte tùy encoding.

Mặc dù 4 code point và 4 grapheme tình cờ bằng nhau trong ví dụ này, **chúng không phải cùng một đơn vị**. Ví dụ `"e\u0301"` (chữ e và dấu sắc kết hợp) chứa **2 code point** nhưng thường là **1 grapheme cluster**; `"👩‍💻"` có nhiều code point nối với zero-width joiner (ZWJ) và thường hiển thị thành **một emoji/cụm**.

| Khái niệm | Đơn vị | Trong Java 17 | Khi phù hợp |
| --- | --- | --- | --- |
| **Byte** | Một byte của bản mã UTF-8, UTF-16LE, v.v. | `getBytes(charset)` | Giao thức, tệp, byte offset, tìm kiếm trực tiếp trong dữ liệu đã mã hóa |
| **UTF-16 code unit** | 16 bit của `char` | `length()`, `charAt()`, `indexOf()` | API `String`, chỉ số substring Java, dữ liệu đã quy ước offset UTF-16 |
| **Unicode code point** | Một giá trị Unicode vô hướng hợp lệ | `codePoints()`, `codePointAt()`, `offsetByCodePoints()` | Xử lý mã chữ, thuật toán cần phần tử là code point |
| **Extended grapheme cluster** | Một chuỗi code point thường được cảm nhận như một ký tự hiển thị | `Pattern.compile("\\X")` | Tránh cắt vỡ dấu ghép, skin tone, emoji ZWJ, ký tự hiển thị |

**Ghi nhớ:** “Ký tự” trong tài liệu nghiệp vụ thường hàm ý *ký tự người dùng nhìn thấy*, nhưng `char` của Java **không** có nghĩa đó. Đừng dùng `String.length()` để kết luận số ký tự hiển thị, và đừng dùng code point để bảo đảm không cắt rời emoji ghép nhiều code point.

### Tại sao byte offset khác String offset?

Chuỗi Java thường được truy cập qua API UTF-16. Nếu truyền văn bản UTF-8 từ tệp/network, một emoji có thể chiếm **4 byte** nhưng **2 UTF-16 code unit** và **1 code point**. Nếu kết quả tìm kiếm phải trả offset byte trong tệp, phải có cơ chế ánh xạ sau khi giải mã hoặc tìm kiếm trực tiếp trong chuỗi byte với quy tắc mã hóa hợp lệ. Không được đem chỉ số `charAt` rồi gắn nhãn “byte offset”.

## 2. UTF-16: đơn vị mã và cặp surrogate

UTF-16 biểu diễn nhiều code point thuộc Basic Multilingual Plane (BMP) bằng một code unit 16 bit, nhưng các code point ngoài BMP cần **cặp surrogate**: một `high surrogate` và một `low surrogate`.

Với `"A🙂B🙂"` (chỉ số UTF-16, đánh từ 0):

~~~text
UTF-16 index:    0     1       2       3     4       5
                 A    high    low       B   high    low
Code point:      A       🙂            B       🙂
~~~

- `text.charAt(1)` trả **nửa đầu** surrogate của emoji đầu tiên; nó không phải toàn bộ emoji.
- `text.codePointAt(1)` trả code point của emoji khi bắt đầu tại high surrogate hợp lệ.
- `text.indexOf("🙂")` trả **1**. Để tìm tiếp, vị trí thứ hai của emoji là **4**.
- Code point index của hai emoji tương ứng là **1** và **3**.
- Grapheme index của chúng trong ví dụ này cũng là **1** và **3**.

**Lỗi điển hình:** cắt chuỗi bằng `substring(0,2)` có thể để lại high surrogate mà không có low surrogate, tạo chuỗi UTF-16 **không hợp lệ** đối với nhiều yêu cầu Unicode. Với dữ liệu đến từ nguồn không đáng tin, nên xác định chính sách xử lý surrogate cô lập: **từ chối**, thay bằng replacement character, hoặc giữ như đơn vị mã thô. Bài và chương trình demo chọn **từ chối surrogate cô lập**.

### Biên giới của mẫu rỗng theo UTF-16

Trong bài, mẫu rỗng khớp tại **mọi ranh giới giữa các đơn vị của hệ đang chọn**, kể cả ranh giới nằm giữa high/low surrogate trong cách đếm UTF-16. Ví dụ `"A🙂"` có length 3, nên kết quả UTF-16 của mẫu rỗng là `[0,1,2,3]`; vị trí **2** là giữa hai code unit của emoji. Đây là quy ước toán học cho phép tìm kiếm **zero-length pattern**, **không** phải lời khuyên đặt con trỏ văn bản ở giữa một emoji.

Với code point/grapheme, mẫu rỗng chỉ khớp ở biên giới code point/grapheme tương ứng; nó **không** tạo offset ở giữa surrogate pair. Nếu nghiệp vụ không cho phép mẫu rỗng, hãy báo lỗi ngay thay vì dùng quy ước này.

## 3. Code point: đúng mã Unicode nhưng chưa phải ký tự hiển thị

**Unicode code point** là đơn vị nhận dạng của Unicode, ví dụ chữ `é` (U+00E9), dấu sắc kết hợp (U+0301), emoji 🙂 (U+1F642). Code point có thể được biểu diễn bằng **một hoặc hai UTF-16 code unit**.

Trong Java:

~~~java
String s = "A🙂B🙂";
int units = s.length();                       // 6
int points = s.codePointCount(0, s.length()); // 4
int[] cp = s.codePoints().toArray();          // 4 phần tử
int secondEmojiUtf16 = s.offsetByCodePoints(0, 3); // 4
~~~

Ví dụ trên là **mẩu mã minh họa**, còn chương trình Java chạy độc lập ở mục 11 triển khai đầy đủ và kiểm tra kết quả.

So khớp theo code point có nghĩa biến hai chuỗi hợp lệ thành hai dãy số nguyên Unicode, rồi tìm dãy mẫu trong dãy văn bản. **Thứ tự và số lượng code point** phải bằng nhau ở chỗ tìm thấy.

Một điểm quan trọng: trong `"e\u0301"`, mẫu `"e"` sẽ **khớp theo code point** ngay tại phần tử đầu, dù nó mới là một phần của grapheme `é`. Nếu bài toán yêu cầu không tìm/cắt **bên trong một ký tự hiển thị**, so khớp code point đơn thuần chưa đủ.

### Bảo toàn offset UTF-16 khi dùng code point

Nếu kết quả là code point index i nhưng API tiếp theo cần Java `substring`, hãy tính biên giới UTF-16 bằng:

`s.offsetByCodePoints(0, i)`.

Với việc tìm nhiều vị trí, tính một lần mảng **offset của mọi biên giới code point** để tránh quét lại từ đầu cho mỗi kết quả. Mã demo trả mỗi vị trí theo dạng `i@u`, trong đó i là **ordinal code point**, u là **UTF-16 offset trên chuỗi gốc**.

Khi chọn so khớp code point, nhớ kiểm tra surrogate cô lập trước. `String.codePoints()` có hành vi cung cấp giá trị cho surrogate không ghép, nhưng những giá trị đó **không phải Unicode scalar value hợp lệ**. Chương trình demo áp dụng chính sách strict để mô hình có ý nghĩa rõ.

## 4. Grapheme cluster: ký tự hiển thị có thể gồm nhiều code point

Unicode định nghĩa **extended grapheme cluster** gần với đơn vị mà người dùng muốn chọn/xóa/di chuyển con trỏ theo “ký tự”. Ví dụ:

- `"e\u0301"`: chữ e + dấu sắc kết hợp → thường **một grapheme**.
- `"👍🏽"`: emoji ngón tay cái + modifier màu da → thường **một grapheme**.
- `"👩‍💻"`: người phụ nữ + zero-width joiner + laptop → thường **một grapheme**.
- `"🇻🇳"`: hai regional indicator → thường **một grapheme cờ**.

Một đoạn mã nhỏ có thể có một code point nhưng chưa phải grapheme hoàn chỉnh. Ví dụ, trong `"👩‍💻!"`:

- Mẫu `"👩"` **khớp** ở UTF-16 offset 0 nếu chỉ xét dãy code unit.
- Mẫu cũng **khớp** ở code point index 0 nếu chỉ xét dãy code point.
- Mẫu **không khớp như một grapheme cluster nguyên vẹn**, vì grapheme đầu tiên của văn bản là toàn bộ `"👩‍💻"`.

Đó là sự khác nhau về **ngữ nghĩa** của “tìm kiếm”: tìm chuỗi con theo mã có thể hợp lệ cho xử lý dữ liệu, nhưng gây hành vi khó hiểu khi người dùng muốn tìm **emoji độc lập**.

### Phân đoạn grapheme trong Java 17

Java Regex hỗ trợ `\\X` để khớp một **extended grapheme cluster**:

~~~java
Pattern p = Pattern.compile("\\X");
Matcher m = p.matcher(text);
while (m.find()) {
    String cluster = m.group();
    int startUtf16 = m.start();
    int endUtf16 = m.end();
}
~~~

Đây là **đoạn minh họa**, cần `import java.util.regex.Pattern` và `Matcher` hoặc dùng toàn văn ở mục 11. `Matcher.start()` và `end()` vẫn là **offset UTF-16**, dù thứ đang được phân đoạn là grapheme.

**Lưu ý:** grapheme theo quy tắc Unicode là gần với ký tự người dùng cảm nhận nhưng không bảo đảm phản ánh mọi quy ước chữ viết/hiển thị/font/locale. Quy tắc phân đoạn và bảng Unicode có thể được cập nhật giữa các phiên bản JDK. Nếu kết quả phải đồng nhất giữa hệ thống khác nhau, cần kiểm thử phiên bản Unicode và giao thức dữ liệu, không chỉ tên hàm.

## 5. Tương đương nhìn thấy và tương đương mã Unicode

Hai chuỗi có thể hiển thị gần như nhau nhưng có dãy code point khác:

~~~text
Chuỗi A:  "é"        U+00E9
Chuỗi B:  "e\u0301"  U+0065 U+0301
~~~

Trong Java, so sánh `"é".equals("e\u0301")` là **false**, vì `String.equals` so sánh dãy code unit, không tự chuẩn hóa Unicode. Nhưng hai chuỗi này **tương đương chuẩn tắc (canonical equivalent)** theo Unicode; sau chuẩn hóa NFC chúng trở thành cùng một dãy chuẩn.

Đây là lý do một hệ thống tìm kiếm tiếng Việt/châu Âu có dấu có thể báo **“không tìm thấy”** dù người dùng nhìn hai từ giống nhau: một chuỗi được lưu ở dạng ký tự dựng sẵn, chuỗi còn lại ở dạng chữ cái cơ sở và dấu kết hợp.

### Chuẩn hóa không phải xóa dấu

Chuẩn hóa Unicode như NFC/NFD **không xóa dấu** khỏi chữ. Ví dụ `"é"` sau NFD thành `"e\u0301"`, vẫn **có dấu** dưới dạng combining mark. Tìm kiếm “bỏ qua dấu” (accent-insensitive) là một yêu cầu khác và thường cần chính sách xử lý nhiều trường hợp, ví dụ lựa chọn có xóa combining mark hay không. Làm mất dấu không phải một phép biến đổi luôn an toàn cho tên người, định danh hay ngữ nghĩa ngôn ngữ.

### Chuẩn hóa không phải tự động không phân biệt hoa/thường

NFC/NFD/NFKC/NFKD **không phải** thuật toán Unicode full case folding. `"A"` và `"a"` vẫn khác dưới NFC. Nếu muốn tìm kiếm không phân biệt hoa/thường, cần đặc tả thêm xử lý case folding, locale, biến đổi có thể tăng/giảm số ký tự và ánh xạ offset. Không nên chỉ gọi `toLowerCase()` rồi cho rằng đã giải xong mọi trường hợp Unicode.

## 6. Bốn dạng chuẩn hóa Unicode

Java cung cấp `java.text.Normalizer` với các dạng `Normalizer.Form`:

| Dạng | Tên | Ý nghĩa | Ví dụ khái niệm |
| --- | --- | --- | --- |
| **NFD** | Canonical Decomposition | Phân rã theo tương đương chuẩn tắc | `é → e + dấu sắc` |
| **NFC** | Canonical Decomposition + Composition | Phân rã rồi tổng hợp chuẩn tắc khi hợp lệ | `e + dấu sắc → é` |
| **NFKD** | Compatibility Decomposition | Phân rã cả các dạng tương thích | `① → 1`, nhiều chữ kiểu trình bày biến đổi |
| **NFKC** | Compatibility Decomposition + Composition | Phân rã tương thích rồi tổng hợp | `① → 1`, có thể làm mất phân biệt hình thức |

**NFC/NFD** cố gắng đưa các chuỗi **tương đương chuẩn tắc** về dạng nhất quán. **NFKC/NFKD** thực hiện thêm các **biến đổi tương thích** rộng hơn, có thể gộp các ký hiệu vốn người dùng hoặc hệ thống muốn phân biệt. Ví dụ:

- `Normalizer.normalize("①", NFKC)` tạo `"1"`.
- `Normalizer.normalize("ﬃ", NFKC)` tạo `"ffi"`.
- `"①"` và `"1"` **không** bằng nhau dưới NFC, nhưng **có thể** bằng nhau dưới NFKC.

**Không tự dùng NFKC** cho định danh pháp lý, chuỗi mật khẩu, mã sản phẩm, trường chứa ký hiệu đặc thù hoặc văn bản mà phân biệt ký hiệu tương thích là quan trọng. Nếu xác thực/security liên quan, phải theo tiêu chuẩn/cấu hình xác thực cụ thể, không phát minh quy tắc chuẩn hóa.

### Java 17

~~~java
import java.text.Normalizer;

String input = "e\u0301";
String nfc = Normalizer.normalize(input, Normalizer.Form.NFC);
String nfd = Normalizer.normalize("é", Normalizer.Form.NFD);
boolean normalized = Normalizer.isNormalized(
        nfc, Normalizer.Form.NFC);
~~~

Chuẩn hóa là phép **biến đổi chuỗi**. Nó có thể thay đổi cách biểu diễn Unicode và độ dài theo code unit/code point, thậm chí thay đổi ranh giới so khớp khi dùng compatibility form. Phải **chuẩn hóa cả văn bản và mẫu theo cùng chính sách** nếu muốn so tương đương sau chuẩn hóa; chỉ chuẩn hóa một phía là không đủ.

## 7. Bẫy chỉ số: vị trí trên chuỗi đã chuẩn hóa không phải vị trí gốc

Một ví dụ ngắn:

~~~text
original   = "e\u0301X"
NFC        = "éX"

original.indexOf("X") = 2 (UTF-16 offset gốc)
NFC.indexOf("X")      = 1 (UTF-16 offset đã chuẩn hóa)
~~~

Chuỗi ban đầu chứa e, dấu sắc kết hợp, X = **3 code unit**. Chuỗi sau NFC chứa é, X = **2 code unit**.

Nếu tìm kiếm trên bản sao đã chuẩn hóa rồi trả `1` như chỉ số trên văn bản **gốc**, người dùng sẽ đặt con trỏ vào **dấu sắc** thay vì chữ X. Đây là lỗi data alignment, không phải lỗi thuật toán tìm mẫu.

Nguyên tắc:

1. **Biết rõ hệ chỉ số yêu cầu:** byte, UTF-16 code unit, code point hay grapheme.
2. **Biết rõ hệ văn bản:** bản gốc hay bản đã biến đổi.
3. Nếu chỉ trả kết quả trên **bản đã chuẩn hóa**, phải gắn nhãn offset normalized.
4. Nếu API cần offset **trên bản gốc**, phải lưu **ánh xạ vị trí có thể chứng minh được** qua biến đổi hoặc chọn một phép so khớp giữ nguyên ranh giới gốc.
5. Khi biến đổi có thể **gộp, tách, sắp xếp lại** phần tử, không tồn tại phép chuyển đổi offset đơn giản bằng cộng một hằng số cho mọi vị trí.

### Cách bảo toàn offset gốc trong demo

Chương trình Java ở mục 11 cung cấp một chế độ rất cụ thể:

- Phân đoạn **văn bản gốc** và **mẫu gốc** thành các grapheme cluster.
- Chuẩn hóa **từng cluster riêng** bằng NFC hoặc NFKC (nếu yêu cầu).
- So khớp **danh sách cluster sau biến đổi** theo từng cluster.
- Khi gặp match, trả về **UTF-16 offset bắt đầu của cluster trên văn bản gốc**, đã ghi nhận khi phân đoạn.

Cách này hữu ích khi **định nghĩa match là dãy grapheme cluster trọn vẹn** và mỗi cluster được so sánh theo NFC. Nhưng phải nói rõ giới hạn:

> **So khớp chuỗi token grapheme đã chuẩn hóa từng token không đồng nghĩa với tìm substring tùy ý sau khi chuẩn hóa toàn bộ chuỗi.**

Ví dụ `"ﬃ"` là **1 grapheme**; dưới NFKC nó thành chuỗi `"ffi"` nhưng nếu giữ mỗi grapheme là **một token**, nó vẫn là một token có giá trị chuỗi `"ffi"`. Mẫu `"ffi"` là **3 grapheme token**, nên phép tìm kiếm **theo chuỗi token** không báo match dù **NFKC toàn chuỗi** của hai bên bằng nhau. Đây là lựa chọn ngữ nghĩa minh bạch, không phải lỗi của bộ chuẩn hóa.

Nếu muốn **full-string NFKC substring matching** và vẫn giữ offset gốc một cách tổng quát, cần hệ thống **position/span mapping** phù hợp với phép biến đổi, kể cả tình huống một cluster biến thành nhiều ký tự. Không thể chỉ áp `String.indexOf` trên bản chuẩn hóa rồi trả chỉ số như thể đó là offset gốc.

## 8. So khớp theo code unit, code point, hay grapheme?

Chọn dựa trên **đề bài và cách người dùng hiểu kết quả**, không dựa trên việc cách nào có tên nghe hiện đại nhất.

| Nhu cầu | Đơn vị nên xét | Vì sao |
| --- | --- | --- |
| Tìm substring theo hợp đồng Java `String`, trả index cho `substring` | **UTF-16 code unit** | Khớp trực tiếp hệ tọa độ `charAt/indexOf` |
| So sánh dãy mã Unicode bất kể mỗi mã chiếm 1 hay 2 UTF-16 unit | **Code point** | Tránh tách một supplementary code point thành hai đơn vị |
| Tìm “ký tự người dùng nhìn thấy” hoàn chỉnh | **Grapheme cluster** | Tránh match chỉ một phần dấu ghép, skin tone, emoji ZWJ |
| Tìm không phân biệt dạng tổ hợp dấu chuẩn tắc | **Chọn đơn vị + NFC/NFD** | Định nghĩa thêm tương đương chuẩn tắc |
| Tìm không phân biệt ký hiệu tương thích | **NFKC/NFKD theo chính sách** | Có thể gộp các ký hiệu phân biệt về mặt ngữ nghĩa |
| Xử lý offset bên trong file UTF-8 | **Byte sau xác định encoding** | UTF-16 offset không phải byte offset |
| Chuỗi chứa thứ tự hiển thị phức tạp và ký tự nhiều script | **Unicode segmentation/locale-aware processing** | Vị trí hiển thị không chỉ phụ thuộc độ dài code unit |

**Không có một chế độ đúng cho mọi yêu cầu.** Trong trình soạn thảo văn bản, người dùng thường muốn tìm nguyên grapheme. Trong một parser xử lý mẫu gồm ký tự cú pháp, tìm code point có thể đủ. Trong một API Java yêu cầu offset `String`, trả UTF-16 là tự nhiên. Trong công cụ kiểm tra byte-stream, phải giữ đúng encoding và byte offsets.

### Case folding, locale và collation không phải cùng khái niệm

- **Normalization:** xác định dạng Unicode nhất quán.
- **Case-insensitive matching:** cho phép các chữ thuộc quan hệ chữ hoa/thường tương ứng, có thể cần Unicode case folding.
- **Collation:** so sánh/sắp xếp theo quy tắc ngôn ngữ, có thể coi một số chuỗi khác nhau là tương đương ở một mức độ nào đó.
- **Accent-insensitive matching:** chính sách bỏ qua khác biệt dấu; không đơn thuần là NFC.

Một hệ thống có thể cần kết hợp chúng nhưng phải **quy định thứ tự biến đổi** và test offset. Đừng giả định `String.equalsIgnoreCase`, `toLowerCase(Locale.ROOT)`, `Normalizer` và `Collator` luôn tạo cùng tập match.

## 9. Đường biên, vị trí chồng lấn và mẫu rỗng

Với **so khớp theo một đơn vị đã chọn** (UTF-16 unit, code point hoặc grapheme token), hãy định nghĩa:

- Văn bản gồm n phần tử theo đơn vị đó.
- Mẫu gồm m phần tử theo cùng đơn vị.
- Với m>0, các vị trí bắt đầu hợp lệ là `0..n−m`.
- Nếu m>n, không có match.
- Nếu m=0, quy ước của bài trả mọi biên giới `0..n`.
- Nếu tìm **tất cả** lần xuất hiện, dịch vị trí bắt đầu **1 phần tử** sau mỗi lần, kể cả khi vừa có match, để cho phép chồng lấn.

Ví dụ với `"aaaa"` và mẫu `"aa"`, kết quả trong cả ba hệ đơn vị thường là `[0,1,2]`, không phải chỉ `[0,2]`. Với emoji ghép nhiều code point, dịch **một grapheme token** chứ không dịch một code point nếu mục tiêu là tìm nguyên grapheme.

Với một kết quả dạng `i@u` trong demo:
- `i`: chỉ số bắt đầu tính theo code point hoặc grapheme token của **văn bản gốc**.
- `u`: UTF-16 offset ở đầu phần tử thứ i trong **văn bản gốc**.

Ví dụ `[1@1,3@4]` nghĩa là hai match ở vị trí code point/grapheme 1 và 3, tương ứng Java `String` offset 1 và 4. Không lẫn hai hệ chỉ số trong API.

## 10. Chi phí và tính đúng của phép so khớp đã chọn

Sau khi chuyển văn bản/mẫu thành hai dãy phần tử theo đơn vị đã chọn, thuật toán so khớp trực tiếp kiểm tra từng vị trí và so lần lượt các phần tử.

Với n phần tử văn bản và m phần tử mẫu, `1≤m≤n`, số vị trí thử là `n−m+1`. Nếu mỗi phép so phần tử có chi phí O(1), cận trên của so khớp trực tiếp là:

`O(m(n−m+1))`, thường được chặn thô bởi `O(nm)`.

Nhưng **giá thành của phần tử khác nhau**:

- So hai UTF-16 `char` là phép so đơn giản.
- So hai số nguyên code point cũng là phép so đơn giản, sau khi đã giải mã.
- So hai **grapheme token là hai chuỗi** có thể tốn O(độ dài token), chưa kể chi phí phân đoạn và chuẩn hóa. Không được ghi chương trình token-grapheme là O(nm) theo code unit rồi bỏ qua chi phí so chuỗi/normalize.

Chương trình demo dùng **list và mảng để giữ các biên giới**, vì cần trả mọi match. Với n phần tử và k kết quả, bộ nhớ ít nhất gồm O(n) phần tử đã token hóa (nếu dùng chiến lược tiền xử lý) cộng O(k) đầu ra. Trình tự `String.codePoints().toArray()` cũng dùng bộ nhớ O(n) số nguyên code point.

### Chứng minh tính đúng của tìm kiếm theo token

Tại mỗi vị trí `s`, vòng so khớp kiểm tra các phần tử `textToken[s+j]` và `patternToken[j]` theo j tăng từ 0. Nếu có sai khác, s không thể là nơi xuất hiện đúng dãy token mẫu. Nếu tất cả m phần tử trùng, s là một match. Vì vòng ngoài xét **đầy đủ mọi s từ 0 tới n−m**, không match nào bị bỏ sót; vì chỉ báo match sau khi đủ m phần tử khớp, không có match giả.

Định lý này đúng cho **bất kỳ dãy token đã được xác định rõ**. Khi có chuẩn hóa từng token, phép bằng nhau trong chứng minh là bằng nhau **sau phép biến đổi token**. Đó là định nghĩa bài toán được giải, không phải cam kết rằng mọi khái niệm “nhìn giống nhau” của con người đều được tìm thấy.

### So khớp grapheme có phải lúc nào cũng cần?

Không nhất thiết. Nếu chỉ cần tìm một chuỗi con theo quy ước Java và sử dụng kết quả để gọi `substring`, so khớp UTF-16 chính xác có thể là đủ. Nếu đầu ra được dùng để bôi đen **ký tự người dùng nhìn thấy**, bạn cần biên giới grapheme và mapping; code point cũng có thể cắt một cluster. Nếu không rõ yêu cầu, phải chọn và ghi rõ hợp đồng API thay vì lặng lẽ chuyển đổi đơn vị.

## 11. Java 17+ chạy độc lập: ba cách so khớp và chuẩn hóa từng grapheme

Chương trình sau thực hiện **chính xác ba kiểu tìm tất cả vị trí**:

1. **UTF-16 code-unit exact:** so từng `charAt`, trả danh sách UTF-16 offset.
2. **Code point exact:** chuyển thành mảng `int`, so từng code point, đồng thời giữ ánh xạ sang UTF-16 offset gốc.
3. **Extended grapheme cluster:** phân đoạn bằng `Pattern.compile("\\X")`, có thể so **nguyên token** hoặc **token sau NFC/NFKC**, trả cả ordinal grapheme và offset UTF-16 gốc.

Chương trình cố ý **không** gộp normalization, case folding và accent stripping thành một phép “tìm gần giống” mơ hồ. Mỗi biến thể có hợp đồng riêng.

Có kiểm tra surrogate cô lập, ví dụ tự sinh bằng `String.valueOf((char) 0xD800)`; chuỗi đó bị từ chối trước khi phân đoạn. Đầu vào hợp lệ có thể chứa emoji BMP và supplementary theo đúng cặp surrogate.

Tạo tệp **`UnicodeMatchingDemo.java`** bằng UTF-8.

~~~java
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class UnicodeMatchingDemo {
    private static final Pattern GRAPHEME =
            Pattern.compile("\\X");

    // index: ordinal of code point/grapheme in ORIGINAL text.
    // utf16: original Java String offset at that boundary.
    record Hit(int index, int utf16) {
        @Override
        public String toString() {
            return index + "@" + utf16;
        }
    }

    record Segments(List<String> tokens, int[] starts) {}

    private static void validate(String text) {
        Objects.requireNonNull(text, "text");
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (Character.isHighSurrogate(c)) {
                if (i + 1 >= text.length()
                        || !Character.isLowSurrogate(
                                text.charAt(i + 1))) {
                    throw new IllegalArgumentException(
                            "Unpaired high surrogate");
                }
                i++; // Skip the matching low surrogate.
            } else if (Character.isLowSurrogate(c)) {
                throw new IllegalArgumentException(
                        "Unpaired low surrogate");
            }
        }
    }

    static List<Integer> utf16Matches(
            String text, String pattern) {
        validate(text);
        validate(pattern);

        List<Integer> hits = new ArrayList<>();
        int n = text.length(), m = pattern.length();
        for (int start = 0; start <= n - m; start++) {
            int j = 0;
            while (j < m
                    && text.charAt(start + j) == pattern.charAt(j)) {
                j++;
            }
            if (j == m) {
                hits.add(start);
            }
        }
        return List.copyOf(hits);
    }

    private static int[] boundariesOfCodePoints(int[] cps) {
        int[] boundary = new int[cps.length + 1];
        int offset = 0;
        for (int i = 0; i < cps.length; i++) {
            boundary[i] = offset;
            offset += Character.charCount(cps[i]);
        }
        boundary[cps.length] = offset;
        return boundary;
    }

    static List<Hit> codePointMatches(
            String text, String pattern) {
        validate(text);
        validate(pattern);
        int[] a = text.codePoints().toArray();
        int[] b = pattern.codePoints().toArray();
        int[] boundary = boundariesOfCodePoints(a);

        List<Hit> hits = new ArrayList<>();
        for (int start = 0; start <= a.length - b.length; start++) {
            int j = 0;
            while (j < b.length && a[start + j] == b[j]) {
                j++;
            }
            if (j == b.length) {
                hits.add(new Hit(start, boundary[start]));
            }
        }
        return List.copyOf(hits);
    }

    static Segments splitGraphemes(String text) {
        validate(text);
        Matcher matcher = GRAPHEME.matcher(text);
        List<String> tokens = new ArrayList<>();
        List<Integer> offsets = new ArrayList<>();

        while (matcher.find()) {
            tokens.add(matcher.group());
            offsets.add(matcher.start());
        }
        offsets.add(text.length()); // End boundary, incl. empty.
        int[] starts = offsets.stream()
                .mapToInt(Integer::intValue).toArray();
        return new Segments(List.copyOf(tokens), starts);
    }

    private static String transform(
            String token, Normalizer.Form form) {
        return form == null ? token :
                Normalizer.normalize(token, form);
    }

    static List<Hit> graphemeMatches(
            String text, String pattern, Normalizer.Form form) {
        Segments a = splitGraphemes(text);
        Segments b = splitGraphemes(pattern);

        List<String> ta = new ArrayList<>();
        List<String> tb = new ArrayList<>();
        for (String token : a.tokens()) {
            ta.add(transform(token, form));
        }
        for (String token : b.tokens()) {
            tb.add(transform(token, form));
        }

        List<Hit> hits = new ArrayList<>();
        for (int start = 0;
                start <= ta.size() - tb.size(); start++) {
            int j = 0;
            while (j < tb.size()
                    && ta.get(start + j).equals(tb.get(j))) {
                j++;
            }
            if (j == tb.size()) {
                hits.add(new Hit(start, a.starts()[start]));
            }
        }
        return List.copyOf(hits);
    }

    // Independent reference: Java indexOf, advance by ONE UTF-16
    // code unit to preserve overlapping substring matches.
    private static List<Integer> referenceUtf16(
            String text, String pattern) {
        List<Integer> hits = new ArrayList<>();
        if (pattern.isEmpty()) {
            for (int i = 0; i <= text.length(); i++) {
                hits.add(i);
            }
            return hits;
        }
        int searchFrom = 0;
        while (searchFrom <= text.length() - pattern.length()) {
            int found = text.indexOf(pattern, searchFrom);
            if (found < 0) break;
            hits.add(found);
            searchFrom = found + 1;
        }
        return hits;
    }

    // Separate reference for code-point positions:
    // UTF-16 spans by offsetByCodePoints, String.equals.
    private static List<Hit> referenceCodePoints(
            String text, String pattern) {
        int n = text.codePointCount(0, text.length());
        int m = pattern.codePointCount(0, pattern.length());
        List<Hit> hits = new ArrayList<>();

        for (int start = 0; start <= n - m; start++) {
            int from = text.offsetByCodePoints(0, start);
            int to = text.offsetByCodePoints(from, m);
            if (text.substring(from, to).equals(pattern)) {
                hits.add(new Hit(start, from));
            }
        }
        return hits;
    }

    // Independent matching mechanism using List.subList.equals.
    private static List<Hit> referenceGraphemes(
            String text, String pattern, Normalizer.Form form) {
        Segments a = splitGraphemes(text);
        Segments b = splitGraphemes(pattern);
        List<String> ta = new ArrayList<>();
        List<String> tb = new ArrayList<>();
        for (String token : a.tokens())
            ta.add(transform(token, form));
        for (String token : b.tokens())
            tb.add(transform(token, form));

        List<Hit> hits = new ArrayList<>();
        for (int start = 0;
                start <= ta.size() - tb.size(); start++) {
            if (ta.subList(start, start + tb.size()).equals(tb)) {
                hits.add(new Hit(start, a.starts()[start]));
            }
        }
        return hits;
    }

    static void check(String text, String pattern) {
        if (!utf16Matches(text, pattern).equals(
                referenceUtf16(text, pattern))) {
            throw new AssertionError("UTF-16 mismatch");
        }
        if (!codePointMatches(text, pattern).equals(
                referenceCodePoints(text, pattern))) {
            throw new AssertionError("Code-point mismatch");
        }
        for (Normalizer.Form form : new Normalizer.Form[]{
                null, Normalizer.Form.NFC,
                Normalizer.Form.NFD, Normalizer.Form.NFKC}) {
            if (!graphemeMatches(text, pattern, form).equals(
                    referenceGraphemes(text, pattern, form))) {
                throw new AssertionError("Grapheme mismatch");
            }
        }
    }

    private static String randomText(Random random, int count) {
        String[] atoms = {
            "a", "b", "é", "e\u0301",
            "🙂", "👩‍💻", "👍🏽", "①", " "
        };
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < count; i++) {
            result.append(atoms[random.nextInt(atoms.length)]);
        }
        return result.toString();
    }

    static void randomCheck() {
        Random random = new Random(2026L);
        for (int test = 0; test < 300; test++) {
            String text = randomText(random, random.nextInt(9));
            String pattern = randomText(random, random.nextInt(5));
            check(text, pattern);
        }
        System.out.println("randomCheck=PASS (300 pairs)");
    }

    public static void main(String[] args) {
        String emoji = "A🙂B🙂";
        System.out.println("emoji utf16="
                + utf16Matches(emoji, "🙂")
                + " cp=" + codePointMatches(emoji, "🙂")
                + " grapheme=" + graphemeMatches(
                        emoji, "🙂", null));

        String canonical = "cafe\u0301 café";
        System.out.println("canonical utf16="
                + utf16Matches(canonical, "café")
                + " cp=" + codePointMatches(canonical, "café")
                + " graphemeExact=" + graphemeMatches(
                        canonical, "café", null)
                + " graphemeNFC=" + graphemeMatches(
                        canonical, "café", Normalizer.Form.NFC));

        System.out.println("combining utf16="
                + utf16Matches("e\u0301", "e")
                + " cp=" + codePointMatches("e\u0301", "e")
                + " grapheme=" + graphemeMatches(
                        "e\u0301", "e", null));

        System.out.println("zwj utf16="
                + utf16Matches("👩‍💻!", "👩")
                + " cp=" + codePointMatches("👩‍💻!", "👩")
                + " grapheme=" + graphemeMatches(
                        "👩‍💻!", "👩", null));

        System.out.println("skinTone grapheme="
                + graphemeMatches("👍🏽", "👍", null));
        System.out.println("flag grapheme="
                + graphemeMatches("🇻🇳", "🇻", null));

        System.out.println("compatibility circledNFC="
                + graphemeMatches(
                        "①", "1", Normalizer.Form.NFC)
                + " circledNFKC=" + graphemeMatches(
                        "①", "1", Normalizer.Form.NFKC));

        boolean wholeNfkcEqual = Normalizer.normalize(
                "ﬃ", Normalizer.Form.NFKC).equals(
                Normalizer.normalize("ffi", Normalizer.Form.NFKC));
        System.out.println("ligature globalNFKCEqual="
                + wholeNfkcEqual + " tokenNFKC="
                + graphemeMatches(
                        "ﬃ", "ffi", Normalizer.Form.NFKC));

        System.out.println("empty utf16="
                + utf16Matches("A🙂", "")
                + " cp=" + codePointMatches("A🙂", "")
                + " grapheme=" + graphemeMatches(
                        "A🙂", "", null));

        System.out.println("lengths utf16=" + emoji.length()
                + " codePoints=" + emoji.codePointCount(
                        0, emoji.length())
                + " graphemes="
                + splitGraphemes(emoji).tokens().size());

        String original = "e\u0301X";
        String normalized = Normalizer.normalize(
                original, Normalizer.Form.NFC);
        System.out.println("offsetShift original="
                + original.indexOf("X") + " normalized="
                + normalized.indexOf("X"));

        String a = "e\u0301", b = "é";
        System.out.println("canonicalRawEqual=" + a.equals(b)
                + " canonicalNFCEqual=" + Normalizer.normalize(
                        a, Normalizer.Form.NFC).equals(
                        Normalizer.normalize(
                                b, Normalizer.Form.NFC)));

        boolean rejected = false;
        try {
            codePointMatches(
                    "abc", String.valueOf((char) 0xD800));
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        if (!rejected) {
            throw new AssertionError(
                    "Expected orphan surrogate rejection");
        }
        System.out.println("orphanSurrogate=rejected");

        check("A🙂B🙂", "🙂");
        check("cafe\u0301 café", "café");
        check("e\u0301", "e");
        check("👩‍💻!", "👩");
        check("👍🏽", "👍");
        check("🇻🇳", "🇻");
        check("①", "1");
        check("ﬃ", "ffi");
        check("A🙂", "");
        randomCheck();
    }
}
~~~

### Biên dịch và chạy

Dùng **JDK 17 trở lên**, lưu mã nguồn theo UTF-8:

~~~bash
javac -encoding UTF-8 UnicodeMatchingDemo.java
java UnicodeMatchingDemo
~~~

**Đầu ra kỳ vọng** (dạng `i@u` nghĩa là index theo code point/grapheme và offset UTF-16 gốc):

~~~text
emoji utf16=[1, 4] cp=[1@1, 3@4] grapheme=[1@1, 3@4]
canonical utf16=[6] cp=[6@6] graphemeExact=[5@6] graphemeNFC=[0@0, 5@6]
combining utf16=[0] cp=[0@0] grapheme=[]
zwj utf16=[0] cp=[0@0] grapheme=[]
skinTone grapheme=[]
flag grapheme=[]
compatibility circledNFC=[] circledNFKC=[0@0]
ligature globalNFKCEqual=true tokenNFKC=[]
empty utf16=[0, 1, 2, 3] cp=[0@0, 1@1, 2@3] grapheme=[0@0, 1@1, 2@3]
lengths utf16=6 codePoints=4 graphemes=4
offsetShift original=2 normalized=1
canonicalRawEqual=false canonicalNFCEqual=true
orphanSurrogate=rejected
randomCheck=PASS (300 pairs)
~~~

### Đọc từng ví dụ

**emoji:** hai emoji 🙂 nằm ở UTF-16 offset 1 và 4. Chỉ số code point/grapheme là 1 và 3; dạng `1@1,3@4` giữ đồng thời cả hai hệ tọa độ.

**canonical:** văn bản chứa `"cafe\u0301"`, dấu cách, `"café"`. So khớp exact theo UTF-16 và code point chỉ tìm được phần dựng sẵn ở offset 6. Theo grapheme exact, nó bắt đầu ở grapheme thứ 5 (`5@6`). Sau NFC **từng grapheme**, dạng decomposed ở đầu văn bản trở thành tương đương với mẫu, nên có thêm match `0@0`; offset gốc vẫn được giữ đúng.

**combining:** chuỗi `e + dấu sắc kết hợp` chứa code point e, nên tìm mẫu e cho phép match theo UTF-16 và code point. Nhưng e chỉ là một phần grapheme `é`, nên tìm grapheme nguyên vẹn không báo match.

**zwj:** tìm emoji phụ nữ `"👩"` trong `"👩‍💻!"` thấy dãy mã ở đầu nhưng không phải toàn bộ grapheme emoji lập trình viên; kết quả grapheme là rỗng.

**skinTone/flag:** tìm một phần của chuỗi emoji modifier hoặc cờ không phải tìm nguyên grapheme. Cần đối chiếu với mục tiêu giao diện trước khi chọn chính sách.

**compatibility:** vòng tròn số 1 `"①"` và số `"1"` khác nhau dưới NFC nhưng được gộp qua NFKC. Nếu đây là mã ký hiệu quan trọng, hành vi gộp có thể không mong muốn.

**ligature:** cả hai chuỗi có cùng NFKC toàn chuỗi, nhưng một bên là một cluster, bên kia là ba cluster; do demo dùng so khớp **theo token**, nó cố ý trả rỗng. Đây là một khác biệt phải nêu rõ khi lựa chọn giải pháp.

**empty:** mẫu rỗng theo UTF-16 có cả biên giới bên trong surrogate pair; theo code point/grapheme thì không. Đừng lẫn số biên giới với số ký tự hiển thị.

**offsetShift:** ký tự X dịch từ offset 2 ở bản gốc thành offset 1 ở bản NFC. Nếu API tiêu thụ offset trên bản gốc, trả 1 là sai.

**orphanSurrogate:** chương trình từ chối một high surrogate đơn lẻ, thay vì lặng lẽ coi nó như một code point bình thường.

**randomCheck:** 300 cặp chuỗi ngẫu nhiên được sinh từ chữ ASCII, chữ có dấu dựng sẵn/ghép, emoji, emoji ZWJ, emoji kèm modifier, ký hiệu tương thích và dấu cách. Mỗi trường hợp so thuật toán chính với ba nhóm oracle: `String.indexOf` cho UTF-16, `substring/offsetByCodePoints` cho code point, và `List.subList.equals` cho danh sách grapheme token (exact, NFC, NFD, NFKC). Nếu sai, chương trình ném `AssertionError` trước khi in PASS.

**Giới hạn xác minh:** Các oracle chia sẻ chính sách chuẩn hóa và bộ phân đoạn grapheme của Java; chúng xác minh **phép tìm kiếm và offset** độc lập với vòng so khớp chính, không phải bộ chứng nhận rằng mọi cài đặt Unicode trên mọi JDK sẽ phân đoạn mọi chuỗi hiếm theo cùng phiên bản Unicode. Với hệ thống yêu cầu tương thích giao diện chặt chẽ, cần bổ sung bộ dữ liệu chuẩn phân đoạn của phiên bản Unicode đang triển khai.

## 12. So khớp sau chuẩn hóa và ánh xạ span cần thận trọng

### Phương án A: chỉ cần kết quả trên bản chuẩn hóa

Nếu toàn hệ thống **lưu và xử lý** cùng một dạng (chẳng hạn NFC), có thể chuẩn hóa cả đầu vào và mẫu ngay khi nhận dữ liệu rồi tìm trong chuỗi chuẩn hóa. Khi ấy index được định nghĩa trên **dữ liệu đã chuẩn hóa**; không tuyên bố đó là offset của một bản gốc khác.

Ví dụ:

~~~java
String normalizedText = Normalizer.normalize(
        sourceText, Normalizer.Form.NFC);
String normalizedPattern = Normalizer.normalize(
        pattern, Normalizer.Form.NFC);
int offsetInNormalizedText =
        normalizedText.indexOf(normalizedPattern);
~~~

Mã là **mảnh minh họa** có biến `sourceText` và `pattern` do người gọi cung cấp, không phải chương trình chạy riêng. Khi trả kết quả, đặt tên rõ `offsetInNormalizedText`.

### Phương án B: cần offset của bản gốc và match nguyên grapheme

Phân đoạn chuỗi gốc, giữ biên giới UTF-16 của mỗi grapheme, biến đổi/so sánh từng token và trả offset gốc. Chương trình `graphemeMatches` làm đúng điều này.

Đổi lại, **ngữ nghĩa** là so khớp các grapheme đã chuẩn hóa **từng token**, không phải tìm đoạn ký tự tùy ý trong chuỗi được NFKC toàn bộ. Ví dụ `"ﬃ"` và `"ffi"` cho thấy ranh giới token có thể khác.

### Phương án C: yêu cầu global normalization và span chính xác trên bản gốc

Nếu ứng dụng thật sự cần kết quả của **global normalized substring matching** cùng span nguồn chính xác, phải thiết kế **mapping provenance** qua các phép chuẩn hóa, có thể lưu các đoạn nguồn tương ứng với những đơn vị đích, và giải quyết khi gộp/tách/reorder code point.

Nhiều dạng tương đương còn đòi xác định chính sách highlight của phần mở rộng: nếu một ký tự nguồn biến thành nhiều ký tự đích, match một phần của đoạn mở rộng sẽ highlight **toàn bộ** nguồn hay bị từ chối? Cần một quy tắc cụ thể, test bằng dữ liệu thực tế và lưu rõ index space. Không có phép toán `offsetOriginal = offsetNormalized + constant` dùng chung cho mọi văn bản.

## 13. Trường hợp thực tế và quy tắc lựa chọn

### Tìm trong mã nguồn, giao thức hoặc dữ liệu máy

Nếu chuỗi có cú pháp rõ và offset phải tương thích `String`, so khớp **code unit UTF-16** có thể là đúng theo hợp đồng. Khi thao tác byte-level, dùng encoding/byte offsets. Đừng tự động áp NFC cho các dấu hiệu cú pháp hoặc khóa bảo mật nếu quy ước coi **dãy byte/mã** là quan trọng.

### Tìm trong tên hiển thị và văn bản đa ngôn ngữ

Có thể cần **NFC canonical equivalence** để chữ dựng sẵn và dấu ghép đối xử nhất quán, cùng phân đoạn **grapheme** nếu highlight phải giữ nguyên ký tự hiển thị. Nhưng đừng tự xem mọi dấu hoặc khác biệt hoa/thường là không quan trọng; cần yêu cầu nghiệp vụ và test theo ngôn ngữ cụ thể.

### Tìm trong emoji/chat

Một emoji gia đình hay nghề nghiệp có thể gồm ZWJ và nhiều code point; một ký tự cờ có thể gồm hai regional indicators. Nếu UX yêu cầu match **một emoji hoàn chỉnh**, chọn grapheme cluster và kiểm tra các tổ hợp phổ biến; nếu cần tìm **các thành phần mã** của emoji, code point lại là lựa chọn hợp lý.

### Định danh và kiểm tra an toàn

Normalization có thể làm trùng các chuỗi vốn khác nhau về byte hoặc hình thức. Nhưng **confusable characters/homoglyphs** không được giải quyết toàn bộ bằng NFC/NFKC; việc hai ký hiệu nhìn giống nhau nhưng khác script có thể cần kiểm tra riêng. Khi dữ liệu được dùng cho xác thực, URL, tên tài khoản, khóa, đường dẫn, hãy theo chuẩn đã quy định cho loại định danh đó thay vì tự áp “chuẩn hóa mạnh” hay xóa dấu tùy tiện.

### So khớp nhiều lần và hiệu năng

Nếu phải tìm nhiều mẫu trên cùng văn bản, chi phí phân đoạn và chuẩn hóa có thể được **tái sử dụng**. Có thể cache bản token và biên giới, nhưng cần đảm bảo cache luôn đi kèm **đúng bản văn bản và đúng dạng normalization**; không dùng offset cũ sau khi nội dung được sửa.

KMP/Z-algorithm có thể tìm subsequence trên **dãy code point** hoặc **dãy grapheme token** nếu định nghĩa phép bằng nhau phù hợp. Tuy nhiên, tiền xử lý không làm mất chi phí tokenization/normalization, và KMP trên token chuỗi có chi phí so sánh token cần tính riêng.

## 14. Những lỗi dễ mắc

1. Dùng `String.length()` như số ký tự người dùng nhìn thấy.
2. Dùng `charAt(i)` như toàn bộ code point khi ký tự ngoài BMP có surrogate pair.
3. Dùng `substring` với offset code point mà không chuyển về UTF-16.
4. Trả UTF-16 offset rồi ghi nhãn “số code point”.
5. Trả offset trên chuỗi NFC như thể đó là offset trên bản gốc.
6. Chỉ chuẩn hóa mẫu mà không chuẩn hóa văn bản (hoặc ngược lại).
7. Cho rằng NFC/NFD tự động xóa dấu tiếng Việt.
8. Cho rằng NFKC an toàn với mọi mã sản phẩm/định danh và biểu tượng.
9. Cho rằng chuẩn hóa và case folding là cùng một phép.
10. Xem tìm theo code point là bảo đảm không cắt rời grapheme.
11. Cho rằng `"👩"` là một grapheme xuất hiện trong `"👩‍💻"` chỉ vì dãy code point có tiền tố ấy.
12. Quên emoji skin tone hay cờ có nhiều code point trong một cluster.
13. Không quy định mẫu rỗng và dẫn tới kết quả không nhất quán giữa hệ đơn vị.
14. Bỏ qua khớp chồng lấn do tăng vị trí bắt đầu bằng độ dài mẫu.
15. Đếm biên giới trên UTF-16 rồi dùng cho API grapheme.
16. Sử dụng byte offset trên UTF-8 như UTF-16 offset Java.
17. Cắt giữa high surrogate và low surrogate tạo chuỗi ill-formed.
18. Cho phép surrogate cô lập mà vẫn gọi mọi phần tử của `codePoints()` là scalar value.
19. Dùng `BreakIterator` hay một thư viện segmenter bất kỳ mà chưa kiểm tra quy tắc cho ZWJ/emoji trên phiên bản triển khai.
20. Cho rằng Java `String.indexOf` tự áp normalization.
21. Cho rằng grapheme cluster tương ứng chính xác mọi đơn vị chữ viết của tất cả ngôn ngữ.
22. Dùng normalization theo từng grapheme và tuyên bố tương đương tìm substring trên global NFKC.
23. Không làm rõ một ký tự nguồn biến thành nhiều ký tự đích thì highlight span thế nào.
24. Không tính chi phí so chuỗi token grapheme/chuẩn hóa khi phân tích độ phức tạp.
25. Không test dạng dựng sẵn và phân rã của cùng chữ có dấu.
26. Chỉ test emoji một code point, bỏ qua ZWJ/modifier/regional indicator.
27. Mặc định tất cả JDK áp cùng phiên bản quy tắc phân đoạn Unicode.
28. Coi \`==\` là phép so giá trị nội dung chuỗi Java; với `String` cần `equals` hoặc so nội dung đã chuẩn hóa.
29. Không kiểm tra null/surrogate malformed trong API nhận dữ liệu ngoài.
30. Áp dụng accent stripping, lowercase hoặc compatibility folding mà không xem tác động đến ngữ nghĩa và bảo mật.
31. Tối ưu đường tìm kiếm trước khi thống nhất **đơn vị so khớp** và **chính sách tương đương**.
32. Không phân biệt một match trong bản chuẩn hóa với một vị trí bôi đen **trên chuỗi gốc**.

## 15. Bài tập có lời giải

**Bài 1.** `"A🙂B🙂"` có length bao nhiêu theo Java String? **Đáp án:** 6 UTF-16 code units.

**Bài 2.** Cùng chuỗi, có bao nhiêu code point và grapheme cluster theo quy tắc ví dụ? **Đáp án:** 4 code point và 4 grapheme cluster.

**Bài 3.** Mẫu `"🙂"` có các vị trí UTF-16 nào trong `"A🙂B🙂"`? **Đáp án:** 1 và 4.

**Bài 4.** Cùng ví dụ, chỉ số code point của hai match? **Đáp án:** 1 và 3; offset UTF-16 tương ứng 1 và 4.

**Bài 5.** `"e\u0301"` có bao nhiêu code point và grapheme? **Đáp án:** 2 code point nhưng thường 1 grapheme.

**Bài 6.** Mẫu `"e"` có khớp code point trong `"e\u0301"` không? **Đáp án:** có tại index0; nhưng không khớp nguyên grapheme.

**Bài 7.** Vì sao mẫu `"👩"` không khớp nguyên grapheme trong `"👩‍💻!"`? **Đáp án:** grapheme đầu là toàn bộ emoji ZWJ `"👩‍💻"`.

**Bài 8.** `"👍🏽"` chứa một hay hai grapheme? **Đáp án:** một grapheme, dù gồm emoji và modifier riêng code point.

**Bài 9.** `"🇻🇳"` gồm mấy regional indicator? **Đáp án:** hai; theo phân đoạn phổ biến chúng tạo một grapheme cờ.

**Bài 10.** `"é"` và `"e\u0301"` có bằng nhau dưới `String.equals` trước chuẩn hóa không? **Đáp án:** không.

**Bài 11.** Dạng chuẩn hóa nào có thể đưa hai chuỗi bài 10 về cùng dạng composed? **Đáp án:** NFC.

**Bài 12.** Dạng nào thường phân rã `é` thành e và combining acute? **Đáp án:** NFD.

**Bài 13.** `"①"` có thể trở thành `"1"` dưới NFKC không? **Đáp án:** có, đó là biến đổi compatibility.

**Bài 14.** NFKC có phù hợp mặc định với mọi identifier không? **Đáp án:** không; có thể gộp ký hiệu có ý nghĩa khác nhau.

**Bài 15.** Nếu bản gốc `"e\u0301X"` thì offset UTF-16 của X là gì? **Đáp án:** 2.

**Bài 16.** Nếu chuẩn hóa NFC toàn chuỗi bài 15 thì offset của X thành gì? **Đáp án:** 1 trên **bản chuẩn hóa**, không phải trên bản gốc.

**Bài 17.** Vì sao không thể dùng một hằng số chung để đổi offset normalized thành offset gốc? **Đáp án:** normalization có thể gộp/tách/reorder ở những vị trí khác nhau.

**Bài 18.** Trong Java 17, API nào cho dãy Unicode code point? **Đáp án:** `String.codePoints()`; trước đó cần chính sách xử lý surrogate cô lập.

**Bài 19.** API nào chuyển code point index về UTF-16 offset? **Đáp án:** `offsetByCodePoints` hoặc mảng biên giới code point tự xây.

**Bài 20.** Regex `\\X` dùng để làm gì? **Đáp án:** phân đoạn extended grapheme cluster trong Java Pattern.

**Bài 21.** `Matcher.start()` của một match `\\X` trả offset code point hay UTF-16? **Đáp án:** UTF-16 offset của Java String.

**Bài 22.** Theo quy ước mẫu rỗng, `"A🙂"` trả những biên giới UTF-16 nào? **Đáp án:** `[0,1,2,3]`.

**Bài 23.** Theo code point/grapheme, mẫu rỗng của `"A🙂"` trả những offset UTF-16 nào? **Đáp án:** 0, 1, 3; không có biên giới giữa cặp surrogate.

**Bài 24.** NFKC toàn chuỗi `"ﬃ"` có bằng NFKC toàn chuỗi `"ffi"` không? **Đáp án:** có.

**Bài 25.** So khớp `"ﬃ"` với `"ffi"` dưới *token-grapheme NFKC* của code có trả match không? **Đáp án:** không; một bên 1 token, bên kia 3 token.

**Bài 26.** Muốn tìm theo code point nhưng bôi đen văn bản gốc, cần trả thêm thông tin gì? **Đáp án:** UTF-16 offset/span gốc của match.

**Bài 27.** Khi chỉ tìm theo byte UTF-8, có thể cộng offset UTF-16 để ra offset byte không? **Đáp án:** không; độ dài mã hóa mỗi code point khác nhau.

**Bài 28.** Chuẩn hóa NFC có làm tìm kiếm không phân biệt hoa thường không? **Đáp án:** không; hai yêu cầu riêng.

**Bài 29.** Chuẩn hóa Unicode có đồng nghĩa với xóa dấu không? **Đáp án:** không; dấu có thể chuyển từ dạng dựng sẵn sang combining mark.

**Bài 30.** Muốn tìm mọi match chồng lấn, sau match cần tăng vị trí thử như thế nào? **Đáp án:** tăng **một phần tử của đơn vị đã chọn**, không nhảy qua toàn bộ mẫu.

**Bài 31.** Nếu đoạn đã chuẩn hóa làm một cluster thành nhiều ký tự, hệ thống highlight cần làm gì? **Đáp án:** định nghĩa rõ mapping span nguồn–đích hoặc giới hạn chỉ tìm nguyên token; không đoán offset.

**Bài 32.** Khi nào nên dùng grapheme thay vì code point? **Đáp án:** khi chính sách là tìm/hiển thị một đơn vị ký tự người dùng nhận thấy mà không cắt rời dấu ghép hoặc emoji ZWJ.

## 16. Checklist thiết kế tìm kiếm Unicode

1. Đầu vào là **byte đã mã hóa**, Java String, hay chuỗi chuẩn hóa sẵn?
2. **Đơn vị so khớp** đã ghi rõ: UTF-16 unit, code point hay grapheme?
3. **Đơn vị trả index** đã ghi rõ và khớp API cần tiêu thụ?
4. Cần **tất cả match**, match đầu tiên, và match **chồng lấn**?
5. **Mẫu rỗng** có hợp lệ và được trả như thế nào?
6. Có kiểm tra **surrogate cô lập** hoặc xác định quy tắc thay thế malformed Unicode?
7. Với emoji ngoài BMP, đã test **high/low surrogate** và index chuyển đổi?
8. Với dấu ghép, đã test `é` so với `e + combining acute`?
9. Với emoji ZWJ, modifier, cờ, đã test **grapheme trọn vẹn**?
10. Có yêu cầu **canonical equivalence** NFC/NFD không?
11. Có thực sự được phép áp **compatibility** NFKC/NFKD không?
12. Có cần case-insensitive, accent-insensitive hay collation không, và đã tách khỏi normalization?
13. Cả văn bản và mẫu có áp **cùng chính sách** không?
14. Nếu trả offset normalized, đã **gắn nhãn chính xác** chưa?
15. Nếu trả offset gốc, đã **bảo toàn/mapping** qua mọi phép biến đổi chưa?
16. So khớp grapheme từng token có được phân biệt với substring trên **global normalized text** chưa?
17. Có kiểm tra input rỗng, dài hơn văn bản, nhiều match và match chồng lấn?
18. Khi dữ liệu lớn, đã tính chi phí **token hóa, normalization, so sánh token và lưu kết quả** chưa?
19. Có lưu/khóa phiên bản Unicode/JDK nếu cần tái lập ranh giới grapheme giữa môi trường?
20. Có kiểm tra kết quả bằng một oracle độc lập trên dữ liệu mẫu, và không nhầm số match với số ký tự người dùng nhìn thấy?

**Ghi nhớ:** Trước khi chọn KMP, Z hay một thuật toán tìm chuỗi khác, phải chọn **đơn vị phần tử** và **quan hệ bằng nhau**. **UTF-16** phù hợp offset của Java String; **code point** phù hợp thao tác theo mã Unicode; **grapheme cluster** phù hợp tìm nguyên ký tự hiển thị. **NFC/NFD** xử lý tương đương chuẩn tắc, **NFKC/NFKD** còn gộp cả những khác biệt tương thích. Đặc biệt, **chuẩn hóa có thể đổi chiều dài và offset**: kết quả trên chuỗi chuẩn hóa không tự động là vị trí của văn bản gốc.