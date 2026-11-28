# Kiểm chứng regex khi tên biến là một phần của định danh khác

## Mục tiêu bài học

Khi dùng `@highlight` trong `{@snippet}`, ta thường muốn làm nổi bật một tên biến cụ thể. Tuy nhiên, nếu tên đó cũng xuất hiện bên trong một định danh dài hơn, việc tìm chuỗi đơn giản có thể tô nhầm nhiều vị trí.

Ví dụ, mục tiêu là làm nổi bật biến `id` trong dòng:

~~~java
int id = 1, userId = 2, idValue = 3, id2 = 4;
~~~

Nếu dùng `substring="id"`, công cụ còn tìm thấy `id` bên trong `userId`, `idValue` và `id2`. Để giới hạn kết quả, có thể dùng regex với ranh giới từ hoặc lookaround. Khi cần chính xác theo quy tắc ký tự của Java identifier, ta có thể dùng character property `\p{javaJavaIdentifierPart}`.

Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`. Sau khi học, bạn có thể:

- Nhận diện false positive khi tên biến nằm trong một định danh khác.
- Dùng `\b` để phân biệt chuỗi nằm giữa các ký tự word và non-word trong trường hợp thông thường.
- Hiểu vì sao `\b` không phải lúc nào cũng trùng với ranh giới của Java identifier.
- Viết regex dựa trên `Character.isJavaIdentifierPart` để kiểm tra ký tự ngay trước và sau tên cần chọn.
- Xây dựng bảng test gồm trường hợp phải khớp và không được khớp.
- Biết giới hạn của regex: nó chọn văn bản trong snippet, không phân tích cú pháp để nhận diện token Java.

## 1. Vấn đề: một tên ngắn có thể nằm trong tên dài hơn

Giả sử đoạn mã có các biến sau:

~~~java
int id = 1;
int userId = 2;
int idValue = 3;
int id2 = 4;
~~~

Tên mục tiêu là `id`. Nếu viết:

~~~java
int id = 1; // @highlight substring="id"
~~~

thì chỉ dòng này được xử lý, nhưng khi áp dụng trên một dòng có nhiều tên, `substring` sẽ tìm mọi lần xuất hiện của chuỗi `id` trong phạm vi được chọn. Nó không biết đâu là tên biến độc lập, đâu là phần của tên dài hơn.

Ví dụ:

~~~java
int id = 1, userId = 2, idValue = 3, id2 = 4; // @highlight substring="id"
~~~

Các vị trí chứa chữ `id` đều được tìm thấy:

- `id` là tên biến mục tiêu.
- `userId` chứa `id` ở cuối.
- `idValue` chứa `id` ở đầu.
- `id2` chứa `id` ở đầu.

Đây không phải lỗi của `substring`. Nó làm đúng việc tìm **chuỗi ký tự nguyên văn**. Khi yêu cầu có thêm điều kiện “không được nằm trong một định danh dài hơn”, ta cần một mẫu regex có kiểm tra phần ký tự xung quanh.

## 2. Bước đầu: dùng ranh giới từ `\b`

Trong regex Java, `\b` là *word boundary*: vị trí nằm giữa ký tự thuộc nhóm word (`\w`) và ký tự không thuộc nhóm word (`\W`), hoặc tại đầu/cuối input khi có word character ở phía bên kia.

Với tên ASCII thông thường, có thể viết:

~~~java
int id = 1, userId = 2, idValue = 3, id2 = 4; // @highlight regex='\bid\b'
~~~

Mẫu `\bid\b` có ba phần:

- `\b` đầu tiên yêu cầu ranh giới word ngay trước `id`.
- `id` khớp hai ký tự nguyên văn.
- `\b` cuối yêu cầu ranh giới word ngay sau `id`.

Trong dòng ví dụ, `id` độc lập được chọn. Các trường hợp `userId`, `idValue` và `id2` không khớp vì ít nhất một phía của chuỗi `id` vẫn tiếp giáp với ký tự word.

Đây là cách ngắn gọn và hữu ích khi ví dụ chỉ dùng tên ASCII thông thường. Tuy nhiên, **word boundary của regex không đồng nghĩa với ranh giới identifier của ngôn ngữ Java**.

### 2.1. `\b` dựa trên `\w`, không dựa trên bộ phân tích cú pháp Java

Theo API `java.util.regex.Pattern`:

- `\w` là word character.
- `\W` là ký tự không thuộc `\w`.
- `\b` xác định vị trí chuyển tiếp giữa hai nhóm này.

Với cấu hình mặc định, `\w` được định nghĩa là `[a-zA-Z_0-9]`; khi bật `UNICODE_CHARACTER_CLASS`, tập ký tự word được mở rộng theo quy tắc Unicode. `@highlight regex` sử dụng cú pháp regex của Java, nên cần hiểu đúng các lớp ký tự mà mẫu đang dùng.

Trong khi đó, Java identifier có quy tắc riêng. Ký tự `$` có thể xuất hiện trong identifier theo đặc tả ngôn ngữ, dù không được khuyến khích cho tên viết thủ công thông thường. Nhưng `$` không thuộc lớp `\w` mặc định.

Vì vậy, regex:

~~~java
int $id = 1, id$ = 2; // @highlight regex='\bid\b'
~~~

có thể tô nhầm `id` bên trong `$id` và `id$`: ký tự `$` được xem là non-word, tạo ra ranh giới `\b` ở cạnh nó. Hai tên này vẫn có hình dạng identifier hợp lệ theo quy tắc ký tự Java, dù việc dùng `$` thường dành cho mã được sinh tự động hoặc trường hợp đặc biệt.

### 2.2. `\b` cũng có thể khác với identifier Unicode

Java cho phép chữ cái và chữ số trong identifier lấy từ tập Unicode rộng. Trong khi đó, tập `\w` phụ thuộc vào quy tắc regex và cờ Unicode được bật hay không.

Ví dụ, nếu ký tự Unicode đứng cạnh `id` được regex xem là non-word, `\bid\b` có thể nhận diện một ranh giới ở đó dù trong Java ký tự ấy vẫn được phép thuộc cùng identifier. Vì vậy, đừng dùng `\b` như một lời khẳng định rằng chuỗi đã được tách đúng theo lexical grammar của Java trong mọi trường hợp Unicode.

Một điểm quan trọng khác: `\b` chỉ kiểm tra ranh giới văn bản. Nó không biết đoạn `id` đang nằm trong tên biến, string literal hay comment. Ví dụ `"id"` có ranh giới word ở hai dấu nháy; regex vẫn có thể chọn chữ `id` bên trong chuỗi.

## 3. Ranh giới identifier thông thường với tên ASCII

Nếu ví dụ chỉ sử dụng chữ cái Latin, chữ số, dấu gạch dưới và ký tự dollar, có thể mô tả tập ký tự liền kề bằng một character class rõ ràng:

~~~java
int id = 1, userId = 2, idValue = 3, id2 = 4, _id = 5, id_ = 6, $id = 7, id$ = 8; // @highlight regex='(?<![A-Za-z0-9_$])id(?![A-Za-z0-9_$])'
~~~

Mẫu:

~~~regex
(?<![A-Za-z0-9_$])id(?![A-Za-z0-9_$])
~~~

được đọc như sau:

- `(?<![A-Za-z0-9_$])`: negative lookbehind, yêu cầu ký tự ngay trước `id` **không thuộc** nhóm chữ cái ASCII, chữ số, `_` hoặc `$`.
- `id`: phần văn bản cần chọn.
- `(?![A-Za-z0-9_$])`: negative lookahead, yêu cầu ký tự ngay sau `id` **không thuộc** nhóm đó.

Kết quả:

- `id` độc lập được chọn.
- `userId` không được chọn vì trước `id` là chữ `r`.
- `idValue` không được chọn vì sau `id` là chữ `V`.
- `id2` không được chọn vì sau `id` là chữ số.
- `_id` không được chọn vì trước `id` là `_`.
- `id_` không được chọn vì sau `id` là `_`.
- `$id` và `id$` không được chọn vì `$` được đưa vào character class.

Cách này làm rõ chính xác tập ký tự được xem là một phần của tên trong ví dụ ASCII. Nhưng nó **không mô tả đầy đủ mọi Java identifier Unicode**. Nếu tài liệu có tên chứa chữ cái ngoài ASCII, dấu kết hợp hoặc ký tự hợp lệ khác, nên dùng property của Java thay vì tự liệt kê một nhóm hẹp.

## 4. Cách sát với Java identifier: `\p{javaJavaIdentifierPart}`

API `Character` cung cấp `isJavaIdentifierStart` và `isJavaIdentifierPart` để xác định ký tự có thể bắt đầu hoặc tiếp tục một Java identifier. `java.util.regex.Pattern` cũng hỗ trợ các character property tương ứng, bao gồm `\p{javaJavaIdentifierPart}`.

Để kiểm tra một chuỗi mục tiêu không bị dính vào identifier ở hai phía, có thể dùng:

~~~java
int id = 1, userId = 2, idValue = 3, id2 = 4, _id = 5, id_ = 6, $id = 7, id$ = 8; // @highlight regex='(?<!\p{javaJavaIdentifierPart})id(?!\p{javaJavaIdentifierPart})'
~~~

Mẫu tổng quát:

~~~regex
(?<!\p{javaJavaIdentifierPart})TARGET(?!\p{javaJavaIdentifierPart})
~~~

Trong đó `TARGET` là tên cần tìm. Hai điều kiện kiểm tra lân cận có nghĩa:

1. Ngay trước mục tiêu không có ký tự được phép làm thành phần của Java identifier.
2. Ngay sau mục tiêu không có ký tự được phép làm thành phần của Java identifier.

Với `id`, mẫu sẽ loại các trường hợp nằm trong `userId`, `idValue`, `id2`, `_id`, `id_`, `$id` và `id$`. Nó còn áp dụng cho các ký tự identifier Unicode được `Character.isJavaIdentifierPart` nhận diện, bao gồm chữ cái, chữ số, ký tự tiền tệ, dấu kết nối, dấu kết hợp và ký tự được phép bỏ qua theo quy tắc Java.

### 4.1. Phân biệt ký tự bắt đầu và ký tự tiếp tục

Java định nghĩa hai phép kiểm tra khác nhau:

| API | Ý nghĩa |
| --- | --- |
| `Character.isJavaIdentifierStart(int)` | Ký tự có thể đứng ở đầu một Java identifier. |
| `Character.isJavaIdentifierPart(int)` | Ký tự có thể đứng ở vị trí tiếp theo trong Java identifier. |

Khi kiểm tra ranh giới quanh một tên mục tiêu đã biết, điều cần xác định là ký tự kề bên có thể **tiếp tục** identifier hiện tại hay không. Vì vậy, `javaJavaIdentifierPart` phù hợp cho cả lookbehind lẫn lookahead.

Nếu cần xác thực toàn bộ chuỗi có hình dạng identifier, quy tắc phải khác: ký tự đầu dùng `javaJavaIdentifierStart`, các ký tự còn lại dùng `javaJavaIdentifierPart`. Mẫu hình dạng identifier cơ bản là:

~~~regex
\p{javaJavaIdentifierStart}\p{javaJavaIdentifierPart}*
~~~

Mẫu này chỉ mô tả hình dạng ký tự; nó chưa loại bỏ keyword, boolean literal hoặc `null`. Việc xác thực một identifier hợp lệ đầy đủ còn phụ thuộc quy tắc lexical của Java.

### 4.2. Chọn giữa ba mẫu

| Mẫu | Phù hợp khi | Giới hạn |
| --- | --- | --- |
| `substring="id"` | Cần tìm đúng chuỗi `id` bất kể vị trí. | Khớp cả trong identifier dài hơn. |
| `regex='\bid\b'` | Tên ASCII thông thường, không có ký tự đặc biệt làm thay đổi ranh giới. | `\b` dựa trên `\w`, không phải quy tắc Java identifier đầy đủ. |
| `regex='(?<!\p{javaJavaIdentifierPart})id(?!\p{javaJavaIdentifierPart})'` | Cần ranh giới theo ký tự được Java cho phép trong identifier. | Vẫn là tìm kiếm văn bản, không phân biệt token với string literal/comment. |

## 5. Kiểm chứng bằng bảng test

Đừng chỉ nhìn một ví dụ có kết quả mong muốn. Hãy lập danh sách cả trường hợp cần chọn lẫn trường hợp không được chọn. Với mục tiêu `id`, bảng sau có thể dùng để kiểm tra:

| Văn bản xuất hiện trong mã | `substring="id"` | `\bid\b` | Java identifier boundary |
| --- | --- | --- | --- |
| `id` | Có | Có | Có |
| `userId` | Có | Không | Không |
| `idValue` | Có | Không | Không |
| `id2` | Có | Không | Không |
| `_id` | Có | Không | Không |
| `id_` | Có | Không | Không |
| `$id` | Có | **Có thể khớp nhầm** | Không |
| `id$` | Có | **Có thể khớp nhầm** | Không |
| `αid` | Có | Tùy tập `\w`/cờ Unicode | Không |
| `idβ` | Có | Tùy tập `\w`/cờ Unicode | Không |

Trong bảng, “Java identifier boundary” là mẫu dùng `\p{javaJavaIdentifierPart}` ở cả hai phía. “Có” nghĩa là phần `id` được chọn; “Không” nghĩa là bị loại vì nó nằm liền trong một identifier dài hơn.

### 5.1. Ví dụ kiểm chứng trên một dòng

Tạo một snippet gồm đủ trường hợp:

~~~java
/**
 * Chỉ nhấn tên biến id độc lập:
 * {@snippet :
 *     int id = 1, userId = 2, idValue = 3, id2 = 4, _id = 5, id_ = 6, $id = 7, id$ = 8; // @highlight regex='(?<!\p{javaJavaIdentifierPart})id(?!\p{javaJavaIdentifierPart})'
 * }
 */
public class IdentifierBoundaryDoc {
}
~~~

Trong khối mã HTML, chỉ `id` độc lập cần được đánh dấu. Những lần xuất hiện khác của chuỗi `id` bên trong tên dài hơn không được chọn.

Để đối chiếu với cách dùng `\b`, thay markup comment bằng:

~~~java
int id = 1, userId = 2, idValue = 3, id2 = 4, $id = 5, id$ = 6; // @highlight regex='\bid\b'
~~~

Kiểm tra xem `id` trong `$id` và `id$` có bị tô nhầm không. Ví dụ này cho thấy tại sao một mẫu ngắn có thể đúng trong tập tên thông thường nhưng chưa đủ chặt với mọi ký tự Java cho phép.

### 5.2. Ví dụ với identifier Unicode

Java cho phép identifier sử dụng chữ cái từ nhiều hệ chữ Unicode. Có thể minh họa tên `αid` và `idβ`, trong đó `α` và `β` là chữ cái Hy Lạp:

~~~java
int id = 1, αid = 2, idβ = 3; // @highlight regex='(?<!\p{javaJavaIdentifierPart})id(?!\p{javaJavaIdentifierPart})'
~~~

Mẫu dựa trên `javaJavaIdentifierPart` kiểm tra đúng loại ký tự kề bên theo API Java. Điều này hữu ích nếu tài liệu mô tả mã có identifier Unicode, dù tên biến ASCII vẫn thường dễ đọc và dễ bảo trì hơn trong ví dụ hướng dẫn.

## 6. Giới hạn quan trọng: regex không phải Java lexer

Ngay cả mẫu ranh giới dựa trên `javaJavaIdentifierPart` cũng chỉ chọn văn bản. Nó không xác định đoạn được chọn có phải **identifier token** trong cú pháp Java hay không.

Ví dụ:

~~~java
String message = "id"; // @highlight regex='(?<!\p{javaJavaIdentifierPart})id(?!\p{javaJavaIdentifierPart})'
~~~

Hai dấu nháy kép không phải Java identifier part, nên chuỗi `id` bên trong literal vẫn có ranh giới phù hợp và có thể được đánh dấu. Tương tự, một đoạn văn bản trong comment cũng có thể khớp nếu hai phía thỏa mãn regex.

Do đó, hãy phân biệt:

- **Ranh giới ký tự identifier:** kiểm tra ký tự ngay trước và sau một chuỗi có thể thuộc cùng identifier hay không.
- **Nhận diện token Java:** xác định đoạn đó là identifier token sau khi áp dụng lexical rules, đồng thời phân biệt nó với string literal, comment, keyword và các token khác.

`@highlight regex` làm việc ở tầng văn bản của snippet. Nếu mục tiêu là chọn một identifier token nhưng tuyệt đối không chạm vào string literal hay comment, regex đơn giản không đủ để đảm bảo trong mọi đoạn mã. Hãy cấu trúc ví dụ sao cho tên cần nhấn xuất hiện ở vị trí rõ ràng, hoặc dùng công cụ phân tích cú pháp Java khi cần xử lý mã nguồn theo token.

## 7. Quy trình kiểm chứng regex có hệ thống

Khi viết một markup regex cho tên biến, thực hiện lần lượt:

1. **Xác định chuỗi mục tiêu.** Ví dụ cần chọn `id`, không phải mọi chuỗi có hai ký tự đó.
2. **Liệt kê false positive.** Thêm tên bắt đầu bằng mục tiêu, kết thúc bằng mục tiêu, có chữ số, dấu gạch dưới, dấu dollar và ký tự Unicode.
3. **Chọn quy tắc ranh giới.** Dùng `\b` cho trường hợp từ thông thường; dùng `javaJavaIdentifierPart` khi muốn bám sát tập ký tự identifier của Java.
4. **Kiểm tra hai phía.** Negative lookbehind ngăn ký tự identifier ở bên trái; negative lookahead ngăn ký tự identifier ở bên phải.
5. **Kiểm tra ngữ cảnh phi identifier.** Thử cả string literal và comment để nhận ra regex vẫn có thể chọn văn bản ở đó.
6. **Sinh Javadoc.** Mở HTML vừa sinh và kiểm tra chính xác các đoạn được đánh dấu.
7. **Điều chỉnh ví dụ nếu cần.** Nếu phải phân biệt token về mặt cú pháp, chuyển sang ví dụ gọn hoặc công cụ hiểu cú pháp thay vì mở rộng regex đến mức khó bảo trì.

Ví dụ, với mục tiêu `id`:

~~~text
Mục tiêu: id

Phải chọn:
  id

Không được chọn:
  userId
  idValue
  id2
  _id
  id_
  $id
  id$
  αid
  idβ
~~~

Bảng test này giúp xác nhận mẫu không chỉ hoạt động với ví dụ thuận lợi mà còn xử lý được các tên dễ gây nhầm.

## 8. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng `substring="id"` để tìm riêng biến `id`. | Chuỗi `id` có thể nằm trong `userId`, `idValue` hoặc `id2`. | Chuyển sang `regex` với điều kiện ranh giới hai phía. |
| Dùng `id\b` mà không có ranh giới trái. | Có thể khớp phần cuối của `userId`. | Thêm ranh giới bên trái, ví dụ `\bid\b` trong trường hợp ASCII thông thường. |
| Nghĩ `\b` chính là ranh giới Java identifier. | `\b` dựa trên `\w`; tập đó không đồng nhất với `Character.isJavaIdentifierPart`. | Dùng `\p{javaJavaIdentifierPart}` ở lookbehind và lookahead khi cần bám sát Java. |
| Quên ký tự `$` trong mẫu ASCII. | `$` có thể xuất hiện trong Java identifier nhưng không thuộc `\w` mặc định. | Thêm `$` vào character class ASCII hoặc dùng Java identifier property. |
| Chỉ kiểm tra một phía. | Tên mục tiêu có thể bị dính ở bên trái hoặc bên phải. | Dùng cả negative lookbehind và negative lookahead. |
| Nghĩ regex sẽ bỏ qua string literal và comment. | `@highlight regex` tìm văn bản, không phân tích token. | Kiểm tra ngữ cảnh hoặc dùng parser nếu cần nhận diện token thật. |
| Dùng character class ASCII cho identifier Unicode. | Các chữ cái, dấu kết hợp và ký tự hợp lệ ngoài ASCII không nằm trong danh sách tự viết. | Dùng `\p{javaJavaIdentifierPart}` cho ranh giới ký tự Java. |
| Thấy regex khớp một ví dụ nên kết luận đã đúng. | Chưa kiểm tra các tên dài, hậu tố số và ký tự đặc biệt. | Xây dựng bảng test cả positive lẫn negative cases. |

## 9. Bài tập tự đánh giá

### Bài 1 — Tại sao `substring` tô nhầm?

~~~java
int key = 1, cacheKey = 2, keyName = 3; // @highlight substring="key"
~~~

**Đáp án:** Chuỗi `key` xuất hiện trong cả ba tên. `substring` không nhận biết ranh giới identifier, nên nó tìm cả `cacheKey` và `keyName`.

### Bài 2 — Ranh giới từ có đủ không?

~~~java
int key = 1, $key = 2, key$ = 3; // @highlight regex='\bkey\b'
~~~

**Đáp án:** `\b` dựa trên `\w` và `\W`. Vì `$` không thuộc `\w` mặc định, nó có thể tạo ranh giới ở hai cạnh `key` trong `$key` và `key$`. Dùng `\p{javaJavaIdentifierPart}` để kiểm tra theo tập ký tự Java identifier.

### Bài 3 — Viết regex bám sát Java identifier

Hãy chọn riêng `key` trong các tên `key`, `cacheKey`, `keyValue`, `key2`, `$key`.

**Đáp án:**

~~~java
int key = 1, cacheKey = 2, keyValue = 3, key2 = 4, $key = 5; // @highlight regex='(?<!\p{javaJavaIdentifierPart})key(?!\p{javaJavaIdentifierPart})'
~~~

Mẫu kiểm tra ký tự Java identifier part ngay trước và sau `key`. Chỉ tên độc lập được chọn.

### Bài 4 — Vì sao string literal vẫn có thể khớp?

~~~java
String value = "key"; // @highlight regex='(?<!\p{javaJavaIdentifierPart})key(?!\p{javaJavaIdentifierPart})'
~~~

**Đáp án:** Hai dấu nháy không phải Java identifier part, vì vậy văn bản `key` trong literal có ranh giới phù hợp. Regex không phân tích xem nó nằm trong literal hay token identifier.

## Tổng kết

- `substring` tìm chuỗi nguyên văn nên có thể tô nhầm khi tên mục tiêu nằm trong định danh dài hơn.
- `\b` là ranh giới word của regex dựa trên `\w`/`\W`, hữu ích cho tên ASCII thông thường nhưng không phải ranh giới Java identifier trong mọi trường hợp.
- Với identifier ASCII, có thể tự liệt kê `[A-Za-z0-9_$]` ở hai phía; với tập ký tự Java, dùng `\p{javaJavaIdentifierPart}` trong negative lookbehind và negative lookahead.
- Java identifier có thể chứa ký tự Unicode, dấu kết hợp, dấu kết nối và ký tự tiền tệ; đừng mặc định chỉ chữ cái Latin và chữ số.
- Regex trong `@highlight` chỉ chọn văn bản. Nó không phân biệt identifier với string literal hoặc comment.
- Hãy kiểm tra cả trường hợp phải khớp và không được khớp bằng HTML do `javadoc` sinh ra.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Guide, JDK 26, mục Markup Comments / Highlighting / Using Regular Expressions](https://docs.oracle.com/en/java/javase/26/javadoc/javadoc-guide.pdf): cách dùng `@highlight` với `substring`, `regex`, word boundary và lookaround; khuyến nghị kiểm tra tài liệu sinh ra.
2. [Oracle — Class Pattern, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html): định nghĩa `\w`, `\b`, lookbehind, lookahead và các character property của regex Java.
3. [Oracle — Java Language Specification, Java SE 27, `3.8 Identifiers](https://docs.oracle.com/javase/specs/jls/se27/html/jls-3.html#jls-3.8): quy tắc ký tự bắt đầu và tiếp tục Java identifier, bao gồm Unicode, `$` và `_`.
4. [Oracle — Class Character, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html): `isJavaIdentifierStart` và `isJavaIdentifierPart`.
5. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): giới thiệu `{@snippet}` trong Java 18.
