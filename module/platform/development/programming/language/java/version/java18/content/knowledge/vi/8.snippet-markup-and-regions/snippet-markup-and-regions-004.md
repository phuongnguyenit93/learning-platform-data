# Chọn văn bản bằng `substring` và phân biệt với chọn bằng `regex`

## Mục tiêu bài học

Từ Java 18, `{@snippet}` cho phép đưa ví dụ mã trực tiếp vào tài liệu API do `javadoc` tạo ra. Một markup tag có thể làm nổi bật một phần văn bản trong ví dụ. Với `@highlight`, hai cách chọn nội dung quan trọng là:

- `substring`: chọn một **chuỗi ký tự nguyên văn**.
- `regex`: chọn văn bản **khớp với biểu thức chính quy**.

Cả hai đều điều khiển cách trình bày snippet; chúng không thay đổi mã nguồn Java hoặc hành vi khi chạy chương trình. Cú pháp này vẫn được hỗ trợ trong các JDK hiện đại.

Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`. Sau khi học, bạn có thể:

- Chọn chính xác một đoạn văn bản bằng `substring`.
- Dùng `regex` khi cần chọn theo mẫu, ranh giới từ hoặc vị trí tương đối.
- Giải thích vì sao một `substring` có thể khớp cả bên trong tên dài hơn.
- Đọc các ký tự đặc biệt của regex như `\b`, `+`, `.`, `*` và lookahead.
- Chọn phạm vi tìm kiếm theo dòng hiện tại hoặc nhiều dòng trong `region`.
- Kiểm tra kết quả thực tế bằng HTML do `javadoc` sinh ra.

## 1. Hai cách chọn văn bản giải quyết hai nhu cầu khác nhau

Cú pháp của `@highlight` cho phép dùng `substring` hoặc `regex` để xác định phần cần nhấn mạnh:

~~~java
int x2 = x; // @highlight substring="x"
~~~

Hoặc:

~~~java
int x2 = x; // @highlight regex='x\b'
~~~

Trong cả hai trường hợp, `@highlight` tác động lên dòng chứa markup comment. Điểm khác biệt nằm ở **quy tắc tìm văn bản**:

- `substring="x"` tìm từng lần xuất hiện của chuỗi `x` theo đúng nghĩa ký tự.
- `regex='x\b'` tìm từng đoạn phù hợp với mẫu regex. Ở đây `\b` yêu cầu ranh giới từ ngay sau `x`.

Với dòng `int x2 = x;`:

- `substring="x"` khớp chữ `x` ở `x2` và chữ `x` đứng riêng ở cuối dòng.
- `regex='x\b'` chỉ khớp chữ `x` đứng riêng ở cuối dòng. Chữ `x` trong `x2` không khớp vì ngay sau nó là `2`, một ký tự thuộc nhóm word character.

| Tiêu chí | `substring` | `regex` |
| --- | --- | --- |
| Cách mô tả | Chuỗi ký tự nguyên văn. | Mẫu biểu thức chính quy. |
| Độ phức tạp | Thấp, dễ đọc. | Linh hoạt, cần hiểu cú pháp regex. |
| Chọn một tên cố định | Rất phù hợp. | Thường không cần thiết. |
| Chọn nhiều dạng có chung mẫu | Khó nếu mỗi dạng khác nhau. | Phù hợp. |
| Giới hạn ranh giới từ | Không có cú pháp ranh giới. | Có thể dùng `\b` hoặc lookaround. |
| Chọn theo vị trí xung quanh | Không diễn đạt được điều kiện vị trí. | Có thể dùng lookahead/lookbehind. |
| Rủi ro thường gặp | Khớp cả trong tên dài hơn. | Mẫu quá rộng, greedy hoặc escape sai. |

**Quy tắc thực hành:** Nếu biết chính xác đoạn chữ cần nhấn, bắt đầu với `substring`. Chỉ dùng `regex` khi cần mô tả một nhóm chuỗi hoặc một điều kiện khớp mà chuỗi nguyên văn không diễn đạt được.

## 2. Chọn chuỗi nguyên văn bằng `substring`

`substring` nhận một chuỗi ký tự theo đúng nội dung muốn tìm. Có thể viết giá trị như một identifier không có dấu nháy hoặc đặt trong dấu nháy đơn/kép khi cần chứa khoảng trắng hay ký tự đặc biệt.

~~~java
/**
 * Chỉ ra biến chứa số lần thử:
 * {@snippet :
 *     int attempts = 3; // @highlight substring="attempts"
 *     if (attempts > 0) {
 *         System.out.println(attempts);
 *     }
 * }
 */
public class SubstringExample {
}
~~~

Trong HTML được tạo ra, các lần xuất hiện của `attempts` trong dòng đầu được làm nổi bật. Các dòng khác không bị tác động vì markup comment chỉ nằm trên dòng khai báo.

### 2.1. `substring` tìm mọi lần xuất hiện trong phạm vi

Xét ví dụ:

~~~java
String statusText = "status=" + status; // @highlight substring="status"
~~~

Trong dòng này, chuỗi `status` xuất hiện ba lần:

1. Bên trong tên biến `statusText`.
2. Bên trong chuỗi ký tự `"status="`.
3. Ở tên biến `status` phía sau dấu `+`.

Cả ba lần đều là văn bản nguyên văn `status` nên đều được chọn. Bộ xử lý snippet không phân tích cú pháp Java để phân biệt identifier với string literal.

Nếu chỉ muốn nhấn đúng tên biến `status` đứng riêng, `substring` không đủ để mô tả ranh giới đó. Khi ấy, hãy dùng `regex` hoặc điều chỉnh ví dụ để mục tiêu được thể hiện rõ hơn.

### 2.2. Chuỗi có dấu cách và dấu nháy

Có thể đặt giá trị `substring` trong dấu nháy để tìm một cụm từ:

~~~java
String message = "request accepted"; // @highlight substring="request accepted"
~~~

Nếu cần tìm cả dấu nháy kép bao quanh nội dung, chọn loại dấu nháy bao thuộc tính khác với dấu nháy nằm trong giá trị:

~~~java
System.out.println("ready"); // @highlight substring='"ready"'
~~~

Ở ví dụ trên, thuộc tính được bao bởi dấu nháy đơn; chuỗi cần tìm chứa dấu nháy kép. Cách này giúp tránh xung đột giữa cú pháp thuộc tính và nội dung muốn tìm.

`substring` phù hợp khi bạn cần nhấn một tên API, một literal, một cụm từ hoặc một đoạn văn bản cụ thể mà không cần điều kiện khớp phức tạp.

### 2.3. Chú ý chữ hoa và chữ thường

So khớp chuỗi nguyên văn phân biệt nội dung ký tự. Ví dụ `substring="userId"` nhắm đến đúng cách viết `userId`; không nên kỳ vọng nó tự khớp `userid` hoặc `USERID`.

~~~java
String userId = "A-17"; // @highlight substring="userId"
String userid = "B-29";
~~~

Chỉ `userId` trong dòng đầu được chọn bởi chỉ dẫn đó. Dòng thứ hai không nhận chỉ dẫn riêng, và cách viết khác chữ hoa/thường không được xem là cùng một chuỗi.

## 3. Chọn theo mẫu bằng `regex`

`regex` nhận một biểu thức chính quy theo cú pháp của Java regular expression (`java.util.regex.Pattern`). Thay vì nêu toàn bộ chuỗi cần tìm, ta mô tả **hình dạng** của đoạn văn bản.

Ví dụ chọn các tên biến có tiền tố `item` và theo sau bởi một hay nhiều chữ số:

~~~java
int item1 = 10, item2 = 20; // @highlight regex='item[0-9]+'
~~~

Mẫu `item[0-9]+` được phân tích như sau:

- `item`: chuỗi ký tự cố định.
- `[0-9]`: một chữ số từ 0 đến 9.
- `+`: lặp lại thành phần ngay trước nó ít nhất một lần.

Vì vậy `item1` và `item2` đều được chọn. Nếu dòng có `itemA`, phần đó không khớp vì ký tự sau `item` không phải chữ số.

### 3.1. Một số thành phần regex thường dùng

| Cú pháp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `.` | Một ký tự bất kỳ (theo quy tắc regex). | `a.c` khớp `abc`, `a-c`. |
| `*` | Thành phần trước đó lặp 0 hoặc nhiều lần. | `ab*` khớp `a`, `ab`, `abbb`. |
| `+` | Thành phần trước đó lặp 1 hoặc nhiều lần. | `ab+` khớp `ab`, `abbb`. |
| `?` | Thành phần trước đó xuất hiện 0 hoặc 1 lần. | `errors?` khớp `error` và `errors`. |
| `[0-9]` | Một ký tự thuộc tập chữ số. | `item[0-9]` khớp `item7`. |
| `[A-Z]` | Một chữ cái ASCII viết hoa. | `[A-Z][a-z]+` khớp một tên bắt đầu bằng chữ hoa. |
| `\d` | Một chữ số theo định nghĩa của regex Java. | `\d+` khớp một dãy chữ số. |
| `\b` | Ranh giới từ. | `x\b` khớp `x` đứng riêng ở cuối từ, không khớp phần đầu của `x2`. |
| `^` | Đầu chuỗi đầu vào của bộ máy regex. | Dùng khi cần ràng buộc vị trí bắt đầu. |
| `$` | Cuối chuỗi đầu vào của bộ máy regex. | Dùng khi cần ràng buộc vị trí kết thúc. |
| `A\|B` | Một trong hai nhánh. | `error\|warning` khớp `error` hoặc `warning`. |

Đây là cú pháp regex, không phải cú pháp riêng của JavaDoc. Nếu cần tra cứu đầy đủ, xem tài liệu `java.util.regex.Pattern` của JDK.

### 3.2. Dùng ranh giới từ để tránh khớp bên trong tên dài

Giả sử dòng mã:

~~~java
int x2 = x; // @highlight regex='x\b'
~~~

`x\b` chọn chữ `x` đứng riêng. Ở `x2`, sau `x` là chữ số `2`; chữ số này thuộc nhóm ký tự từ, vì thế không có ranh giới từ sau `x`. Ở cuối dòng, `x` được theo sau bởi dấu `;` nên có ranh giới từ.

Kết quả: chữ `x` cuối dòng được nhấn; phần `x` trong `x2` không được nhấn.

Đây là tình huống regex thể hiện lợi thế rõ ràng so với `substring="x"`.

### 3.3. Dùng lookahead để chọn theo phần đứng phía sau

Regex có thể kiểm tra ký tự phía sau mà không đưa ký tự kiểm tra vào phần được chọn. Cơ chế này gọi là *positive lookahead*.

~~~java
x = x + 1; // @highlight regex='x(?= \+)'
~~~

`x(?= \+)` chọn chữ `x` mà ngay sau nó là một dấu cách và dấu cộng. Dấu cộng trong regex phải được escape thành `\+` để mang nghĩa **ký tự cộng theo nghĩa đen**, thay vì toán tử lặp một hoặc nhiều lần.

Trong dòng `x = x + 1;`:

- Chữ `x` đầu tiên theo sau bởi ` =` nên không khớp.
- Chữ `x` thứ hai theo sau bởi ` +` nên khớp.

Lookahead chỉ kiểm tra điều kiện phía sau; phần được đánh dấu chỉ là chữ `x`, không bao gồm dấu cách hay dấu cộng.

Có thể dùng lookbehind để kiểm tra phần đứng trước khi chọn một đoạn. Các cơ chế này hữu ích khi cùng một ký tự xuất hiện nhiều lần và cần chọn đúng vị trí.

### 3.4. Chọn literal nằm trong dấu nháy

Muốn chọn một chuỗi literal trong mã:

~~~java
System.out.println("Hello, Java!"); // @highlight regex='"[^"]*"'
~~~

Mẫu `"[^"]*"` có nghĩa:

- Dấu `"` đầu tiên yêu cầu bắt đầu tại dấu nháy kép.
- `[^"]*` khớp 0 hoặc nhiều ký tự không phải dấu nháy kép.
- Dấu `"` cuối yêu cầu kết thúc ở dấu nháy kép tiếp theo.

Cách viết này phù hợp với một literal không chứa dấu nháy kép được escape. Nếu ví dụ có nhiều string literal trên cùng dòng hoặc literal có nội dung phức tạp, cần điều chỉnh regex cho đúng dữ liệu thực tế và kiểm tra đầu ra.

## 4. So sánh trực tiếp `substring` và `regex` trên cùng mã nguồn

Giả sử có dòng:

~~~java
int x2 = x + x3; 
~~~

Ta muốn chọn các trường hợp khác nhau:

| Mục tiêu | Markup comment | Kết quả được chọn |
| --- | --- | --- |
| Mọi chữ `x` xuất hiện | `// @highlight substring="x"` | `x` trong `x2`, `x` độc lập và `x` trong `x3`. |
| Chỉ chữ `x` đứng riêng ở cuối một từ | `// @highlight regex='x\b'` | `x` độc lập; không chọn phần đầu của `x2` và `x3`. |
| Các tên có dạng `x` theo sau bởi chữ số | `// @highlight regex='x[0-9]+'` | `x2` và `x3`. |
| Chỉ chọn `x` đứng trước dấu cộng | `// @highlight regex='x(?= \+)'` | `x` độc lập ngay trước dấu cộng. |

Các ví dụ trong bảng là những cách thay thế nhau cho comment cuối dòng. Không đặt tất cả các comment này vào cùng một dòng để mong chúng tạo ra các vùng nhấn mạnh độc lập; hãy chọn đúng chỉ dẫn cho mục tiêu đang giải thích.

Một cách dễ nhớ:

- **Chuỗi đã biết** → `substring`.
- **Mẫu biến đổi** → `regex`.
- **Ranh giới hoặc vị trí tương đối** → `regex` với boundary/lookaround.
- **Cần nhấn trên nhiều dòng** → thêm `region` để mở rộng phạm vi, rồi chọn `substring` hoặc `regex` trong vùng đó.

## 5. Kết hợp với `region` để tìm trên nhiều dòng

Theo mặc định, `@highlight` chỉ tìm trong dòng chứa markup comment. Muốn áp dụng cùng một bộ chọn trên nhiều dòng, mở một region bằng thuộc tính `region` và kết thúc bằng `@end`.

~~~java
/**
 * Tô đậm các tên item có hậu tố số trong vùng ví dụ:
 * {@snippet :
 *     // @highlight region="items" regex='item[0-9]+' type=bold :
 *     int item1 = 10;
 *     int item2 = 20;
 *     int total = item1 + item2;
 *     // @end region="items"
 *     System.out.println(total);
 * }
 */
public class RegionRegexExample {
}
~~~

Trong khối mã được sinh:

- `item1` và `item2` được chọn vì khớp `item[0-9]+`.
- `item` trong biểu thức `item1 + item2` cũng được chọn, nhưng nếu biểu thức có tên khác không khớp mẫu thì không được nhấn.
- Dòng `System.out.println(total);` nằm ngoài region nên không chịu tác động.
- Các markup comment bị lược khỏi đầu ra.

Nếu thay `regex='item[0-9]+'` bằng `substring="item"`, mọi lần xuất hiện của chữ `item` trong vùng được chọn, kể cả phần đầu của các tên dài hơn. Việc thay bộ chọn không làm thay đổi phạm vi region.

Dấu `:` ở cuối markup comment cho biết chỉ dẫn bắt đầu tác động từ dòng kế tiếp. `@end region="items"` đóng region đã mở bằng tên tương ứng.

## 6. Giá trị thuộc tính và cách đặt dấu nháy

Giá trị của thuộc tính markup dùng quy tắc tên-giá trị tương tự thuộc tính của `{@snippet}`. Có thể dùng identifier hoặc đặt nội dung trong dấu nháy đơn/kép. Một vài ví dụ:

~~~java
// Chuỗi đơn giản, không có khoảng trắng:
value = input; // @highlight substring=value

// Chuỗi có khoảng trắng:
value = input; // @highlight substring="input value"

// Muốn tìm cả dấu nháy kép:
System.out.println("ready"); // @highlight substring='"ready"'

// Regex chứa dấu nháy kép:
System.out.println("ready"); // @highlight regex='"[^"]*"'
~~~

Các giá trị có chứa dấu nháy nên dùng loại dấu nháy bao thuộc tính khác với dấu nháy bên trong giá trị. Đặc tả thuộc tính snippet không định nghĩa cơ chế escape tổng quát cho giá trị; vì vậy, không tự thêm backslash theo thói quen của chuỗi literal Java để “escape” dấu nháy thuộc tính. Hãy chọn delimiter phù hợp hoặc viết lại mẫu.

**Phân biệt hai ngữ cảnh dấu gạch chéo ngược:**

- Trong `regex='x\b'`, `\b` được chuyển tới bộ máy regex như cú pháp ranh giới từ.
- Trong chuỗi Java `"x\\b"`, backslash phải được escape theo cú pháp string literal của Java. Nhưng markup comment `@highlight regex=...` không phải string literal Java, nên không nhân đôi backslash theo quy tắc đó.

Đây là nguồn nhầm lẫn thường gặp khi viết regex trong comment của snippet.

## 7. Lỗi thường gặp khi chọn bằng regex

| Lỗi | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| Dùng `substring="id"` để chỉ chọn identifier `id` đứng riêng. | `substring` cũng khớp phần `id` trong `userId` hoặc `idValue`. | Dùng `regex='\bid\b'` nếu muốn ranh giới từ. |
| Dùng `regex='item+'` để khớp `item1`, `item2`. | Dấu `+` chỉ lặp ký tự `m` trước nó; chữ số không nằm trong mẫu. | Dùng `regex='item[0-9]+'`. |
| Dùng `regex='x+'` để tìm dấu cộng sau `x`. | `+` là toán tử regex, không phải ký tự cộng theo nghĩa đen. | Dùng `regex='x \+'` nếu cần khớp cả khoảng trắng và dấu cộng, hoặc lookahead nếu chỉ muốn chọn `x`. |
| Dùng `regex='.*'` mà không xem xét độ rộng mẫu. | `.*` có thể khớp gần như toàn bộ dòng do tính tham lam. | Giới hạn mẫu, ví dụ `"[^"]*"` cho string literal đơn giản. |
| Viết `regex="..."` nhưng trong mẫu cũng có dấu nháy kép. | Dấu nháy có thể kết thúc giá trị thuộc tính sớm. | Dùng dấu nháy đơn bao ngoài, ví dụ `regex='"[^"]*"'`. |
| Viết regex quá phức tạp chỉ để tìm một tên cố định. | Khó bảo trì và dễ sai hơn chuỗi nguyên văn. | Ưu tiên `substring` khi đã biết chính xác văn bản. |
| Quên kiểm tra regex có khớp không. | Mẫu sai hoặc quá hẹp có thể không chọn được phần mong muốn. | Sinh Javadoc và xem HTML thực tế. |
| Dùng regex mà không hiểu quy tắc Java Pattern. | Ký tự đặc biệt có thể mang ý nghĩa khác với văn bản thường. | Thử mẫu nhỏ với cả ví dụ khớp và không khớp; tham khảo `Pattern`. |

### Greedy và non-greedy

Một số mẫu có thể khớp rộng hơn mong muốn do tính *greedy* (tham lam). Ví dụ `".*"` bắt đầu ở dấu nháy kép đầu tiên và có thể kéo dài đến dấu nháy kép cuối cùng trên dòng. Nếu muốn giới hạn trong một literal đơn giản, `"[^"]*"` thường rõ ràng hơn.

Regex hỗ trợ lượng từ non-greedy như `*?` và `+?`. Tuy nhiên, không nên thêm độ phức tạp này nếu mẫu giới hạn bằng lớp ký tự đã giải quyết được yêu cầu.

## 8. Cách kiểm chứng kết quả trên JDK đang dùng

Tạo file `SubstringRegexDoc.java`:

~~~java
/**
 * So sánh chọn chuỗi nguyên văn và chọn theo regex:
 *
 * {@snippet :
 *     int x2 = x; // @highlight substring="x"
 *     int x2 = x; // @highlight regex='x\b'
 *     int item1 = 10, item2 = 20; // @highlight regex='item[0-9]+'
 *     System.out.println("Hello, Java!"); // @highlight regex='"[^"]*"'
 * }
 */
public class SubstringRegexDoc {
}
~~~

Chạy lệnh sau từ thư mục chứa file:

~~~bash
javadoc -d docs SubstringRegexDoc.java
~~~

Mở `docs/SubstringRegexDoc.html` và kiểm tra:

1. Ở dòng đầu, cả hai chữ `x` được đánh dấu vì dùng `substring="x"`.
2. Ở dòng thứ hai, chỉ chữ `x` đứng riêng được đánh dấu do regex `x\b`.
3. Ở dòng thứ ba, `item1` và `item2` được đánh dấu.
4. Ở dòng thứ tư, chuỗi `"Hello, Java!"` được chọn theo mẫu dấu nháy kép và nội dung bên trong.
5. Các markup comment không xuất hiện trong mã hiển thị.

Mỗi dòng trong ví dụ có một markup comment riêng để quan sát kết quả độc lập. Nếu dự án sử dụng stylesheet tùy chỉnh, phần được chọn có thể có hình thức khác, nhưng phạm vi văn bản cần được chọn vẫn phải đúng.

### Khi kết quả khác mong đợi

- Kiểm tra lại dấu nháy bao giá trị thuộc tính.
- Đọc regex theo cú pháp `java.util.regex.Pattern`.
- Kiểm tra có cần ranh giới từ hoặc lookaround không.
- Kiểm tra phạm vi: chỉ một dòng hay cả region.
- Sinh lại Javadoc và xem HTML mới nhất; không dựa vào ảnh chụp hoặc file HTML cũ.

`javadoc` là công cụ cần dùng để xác nhận markup. `javac` chỉ biên dịch mã Java và không thay thế bước sinh tài liệu khi kiểm tra cách đánh dấu snippet.

## 9. Bài tập tự đánh giá

### Bài 1 — Chọn tên chính xác hay mọi vị trí?

Dòng sau có nội dung gì được chọn?

~~~java
int id = userId + idValue; // @highlight substring="id"
~~~

**Đáp án:** Chuỗi `id` ở cả ba vị trí: identifier `id`, phần cuối của `userId` và phần đầu của `idValue`. `substring` tìm văn bản nguyên văn, không phân biệt token.

### Bài 2 — Dùng regex để chỉ chọn identifier độc lập

Với dòng mã ở bài 1, viết regex để chỉ chọn `id` đứng độc lập.

**Đáp án tham khảo:**

~~~java
int id = userId + idValue; // @highlight regex='\bid\b'
~~~

Hai ranh giới từ bảo đảm mẫu không khớp phần `id` nằm trong tên dài hơn. Trong trường hợp quy tắc tên phức tạp hơn, cần xác định rõ định nghĩa identifier mong muốn rồi thiết kế regex phù hợp.

### Bài 3 — Chọn biến có hậu tố số

Dòng sau cần nhấn tất cả tên biến bắt đầu bằng `cache` và kết thúc bằng một hay nhiều chữ số:

~~~java
int cache1 = 1, cache22 = 2, cacheX = 3;
~~~

**Đáp án:**

~~~java
int cache1 = 1, cache22 = 2, cacheX = 3; // @highlight regex='cache[0-9]+'
~~~

Mẫu chọn `cache1` và `cache22`, không chọn `cacheX`.

### Bài 4 — Chỉ chọn chữ đứng trước phép cộng

Trong dòng `x = x + 1;`, muốn chọn lần xuất hiện thứ hai của `x` mà không chọn dấu cộng, dùng:

~~~java
x = x + 1; // @highlight regex='x(?= \+)'
~~~

**Đáp án:** Lookahead kiểm tra sau chữ `x` có dấu cách và dấu cộng; dấu cộng được escape để mang nghĩa ký tự literal. Chỉ chữ `x` thứ hai được chọn.

### Bài 5 — Chọn literal chuỗi

Muốn nhấn chuỗi literal được đặt trong dấu nháy kép trên dòng:

~~~java
System.out.println("ready");
~~~

**Đáp án tham khảo:**

~~~java
System.out.println("ready"); // @highlight regex='"[^"]*"'
~~~

Mẫu bắt đầu và kết thúc ở dấu nháy kép, chọn các ký tự không phải dấu nháy kép ở giữa.

## Tổng kết

- `substring` chọn từng lần xuất hiện của **chuỗi ký tự nguyên văn** trong phạm vi; cách viết ngắn, dễ hiểu và phù hợp với tên hoặc cụm từ đã biết.
- `regex` chọn từng đoạn **khớp biểu thức chính quy**; phù hợp với nhóm tên theo mẫu, ranh giới từ và điều kiện theo vị trí.
- `substring` không phân tích cú pháp Java, vì vậy có thể khớp bên trong identifier dài hơn hoặc string literal.
- Regex dùng cú pháp `java.util.regex.Pattern`; các ký tự như `+`, `.`, `*`, `\b` và lookaround có ý nghĩa riêng.
- Mặc định `@highlight` chỉ xét dòng chứa comment; dùng `region` và `@end` nếu cần mở rộng phạm vi nhiều dòng.
- Chọn bộ lọc đơn giản nhất đáp ứng mục tiêu, rồi xác minh kết quả bằng HTML do `javadoc` sinh ra.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Documentation Comment Specification, JDK 27, mục Snippet/Highlighting](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html#snippet): mô tả `substring`, `regex`, phạm vi dòng/region và cú pháp markup comment.
2. [Oracle — JavaDoc Guide, JDK 27, mục Snippets](https://docs.oracle.com/en/java/javase/27/javadoc/index.html): hướng dẫn sử dụng snippet và markup comment trong công cụ Javadoc hiện hành.
3. [Oracle — JavaDoc Guide, JDK 26, mục Using Regular Expressions](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): ví dụ về ranh giới từ, lookahead, lookbehind và khuyến nghị kiểm tra đầu ra.
4. [Oracle — Class Pattern, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/Pattern.html): cú pháp biểu thức chính quy được dùng trong `regex`.
5. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): giới thiệu tính năng snippet trong Java 18.
