# Placeholder, dấu ba chấm và ranh giới giữa mã chạy thật với mã được hiển thị

## Mục tiêu bài học

Một ví dụ trong tài liệu API cần đủ ngắn để người đọc hiểu ý chính. Vì vậy, tài liệu thường bỏ qua phần cài đặt, dữ liệu cụ thể hoặc những dòng không liên quan. Người viết có thể muốn hiển thị dấu ba chấm `...` để báo rằng một phần mã đã được lược bỏ, trong khi file nguồn vẫn phải chứa một câu lệnh Java hợp lệ để compiler kiểm tra.

Với `{@snippet}` và markup tag `@replace`, ta có thể giữ một **placeholder hợp lệ trong source** rồi thay nó thành dấu ba chấm hoặc văn bản giải thích khi Javadoc tạo HTML. Cách làm này giúp phân biệt rõ:

- **Mã nguồn:** nội dung thật trong file Java, có thể được compiler kiểm tra nếu file hoàn chỉnh.
- **Markup comment:** chỉ dẫn cho Javadoc, được lược khỏi khối mã hiển thị.
- **Snippet hiển thị:** văn bản sau khi Javadoc áp dụng các phép thay thế và định dạng.
- **Chương trình chạy:** hành vi của file source khi được biên dịch và thực thi; nó không được thay đổi bởi `@replace`.

Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`. Sau khi học, bạn có thể:

- Phân biệt dấu ba chấm là placeholder trình bày với toán tử varargs hợp lệ trong Java.
- Chọn placeholder hợp lệ cho source trước khi thay bằng `...`.
- Dùng `@replace` để thay một literal, một dòng hoặc cả region.
- Biết khi nào nên dùng comment giải thích, inline snippet và external snippet.
- Hiểu vì sao HTML sau khi thay có thể là mã giả, không biên dịch được.
- Kiểm tra source bằng `javac` và kiểm tra phần hiển thị bằng `javadoc`.

## 1. Ba lớp nội dung cần phân biệt

Khi viết ví dụ cho Javadoc, không nên coi source và nội dung được trình bày là một. Một snippet có thể trải qua ba lớp:

| Lớp | Nội dung | Ai xử lý? |
| --- | --- | --- |
| File source | Câu lệnh Java, literal, comment và placeholder ban đầu. | Java compiler khi ta chạy `javac`. |
| Markup của snippet | Các comment như `// @replace ...`, `// @highlight ...`. | Standard doclet của `javadoc`. |
| Nội dung hiển thị | Mã sau khi marker được lược bỏ và replacement được áp dụng. | HTML được `javadoc` sinh ra và trình duyệt hiển thị. |

Ví dụ source:

~~~java
int retryLimit = 3; // @replace substring="3" replacement="MAX_RETRIES"
~~~

Nội dung snippet hiển thị:

~~~java
int retryLimit = MAX_RETRIES;
~~~

Ở đây, compiler nhìn thấy câu lệnh gốc với literal số nguyên `3`. Javadoc nhìn thấy cùng source nhưng xử lý markup để tạo HTML có chữ `MAX_RETRIES`. Biến `MAX_RETRIES` trong bản hiển thị có thể không được khai báo trong snippet; mục đích là trình bày ý tưởng, không phải tạo một bản sao có thể chạy.

**`@replace` không sửa file source, không thay đổi bytecode và không đổi giá trị khi chương trình chạy.** Nó chỉ biến đổi văn bản trong quá trình sinh tài liệu.

## 2. Dấu ba chấm trong Java có nhiều ý nghĩa

Dấu `...` thường được dùng trong tài liệu để biểu thị phần nội dung đã lược bỏ. Nhưng trong Java, ba dấu chấm liên tiếp cũng có một ý nghĩa cú pháp thật: **variable arity parameter** (varargs).

### 2.1. Varargs là cú pháp Java hợp lệ

~~~java
public static void main(String... args) {
    System.out.println(args.length);
}
~~~

`String... args` là khai báo tham số varargs hợp lệ. Compiler cho phép phương thức nhận không hoặc nhiều đối số kiểu `String`. Trong ngữ cảnh này, `...` là thành phần cú pháp của declaration.

Dạng varargs tương đương về kiểu tham số với mảng ở nhiều khía cạnh của lời gọi:

~~~java
public static void log(String... messages) {
    for (String message : messages) {
        System.out.println(message);
    }
}
~~~

Đây là mã Java thực sự. Không được thay `String... messages` bằng cách hiểu “đã lược bỏ một phần code”.

### 2.2. Dấu ba chấm làm placeholder thường không phải cú pháp Java

Ví dụ:

~~~java
public void process() {
    ...
}
~~~

Đoạn trên **không phải** một method body Java hợp lệ. Dấu `...` ở vị trí này không đại diện cho một câu lệnh Java. Nó là quy ước trình bày thường thấy trong tài liệu và mã giả.

Một số dạng hiển thị khác cũng có thể không biên dịch:

~~~java
return ...;
~~~

~~~java
String value = ...;
~~~

Các dấu ba chấm này hữu ích khi giải thích API hoặc lược bỏ giá trị cụ thể, nhưng compiler không thể xem chúng như literal hay biểu thức hợp lệ.

### 2.3. Comment có dấu ba chấm vẫn là comment

~~~java
public void process() {
    // ...
}
~~~

Đoạn này biên dịch được vì `...` nằm trong comment. Tuy nhiên, comment không thay thế phần cài đặt và cũng không làm cho chương trình tự động thực hiện công việc đã lược bỏ. Nếu muốn hiển thị `...` như một dòng mã giả không có comment, có thể dùng `@replace` để thay một placeholder hợp lệ trong source.

### Bảng phân biệt

| Cách viết | Có hợp lệ trong Java? | Ý nghĩa |
| --- | --- | --- |
| `String... args` trong parameter declaration | Có | Tham số varargs. |
| `...` đứng riêng trong method body | Không | Placeholder trình bày, không phải statement. |
| `return ...;` | Không | Placeholder thay cho biểu thức trả về. |
| `// ...` | Có | Comment thông thường. |
| `; // @replace substring=";" replacement="..."` | Có ở source | Empty statement được thay bằng dấu ba chấm trong Javadoc. |

## 3. Giữ source hợp lệ, hiển thị dấu ba chấm bằng `@replace`

`@replace` thay một phần văn bản trong snippet khi tạo HTML. Để thay một biểu thức bằng dấu ba chấm, hãy viết biểu thức placeholder hợp lệ trong source.

Ví dụ:

~~~java
String name = "placeholder"; // @replace substring='"placeholder"' replacement="..."
~~~

Source có string literal `"placeholder"` nên câu lệnh hợp lệ. Sau khi Javadoc xử lý, người đọc thấy:

~~~java
String name = ...;
~~~

Đây là một ví dụ trình bày rút gọn. Dòng trong HTML không còn là câu lệnh Java hoàn chỉnh vì `...` không phải biểu thức hợp lệ ở vị trí đó. Đó không phải lỗi nếu mục tiêu của snippet là giải thích rằng giá trị cụ thể đã được lược bỏ.

### 3.1. Thay một giá trị mặc định

Source:

~~~java
int timeoutSeconds = 30; // @replace substring="30" replacement="..."
~~~

Hiển thị:

~~~java
int timeoutSeconds = ...;
~~~

Người đọc tập trung vào tên biến và ý nghĩa của cấu hình. File source vẫn chứa giá trị số `30` để biên dịch.

### 3.2. Thay một biểu thức dài

Source:

~~~java
return calculateChecksum(data, algorithm); // @replace substring="calculateChecksum(data, algorithm)" replacement="..."
~~~

Hiển thị:

~~~java
return ...;
~~~

Cách này hữu ích khi phần tính toán không phải trọng tâm của ví dụ. Nên chọn đúng biểu thức cần thay, để giữ lại phần cấu trúc câu lệnh giúp người đọc hiểu ngữ cảnh.

### 3.3. Thay toàn bộ dòng

Nếu muốn lược bỏ cả một câu lệnh, không cần selector:

~~~java
// @replace replacement="..." :
return calculateDetailedResult(input);
~~~

Hiển thị:

~~~java
...
~~~

Dấu `:` khiến markup comment đứng riêng áp dụng lên dòng tiếp theo. Vì không có `substring` hoặc `regex`, toàn bộ dòng thuộc phạm vi mặc định được thay.

## 4. Placeholder cần được chọn theo vị trí cú pháp

Không phải placeholder nào cũng dùng được ở mọi vị trí. Câu lệnh nguồn phải hợp lệ trong ngữ cảnh Java mà nó xuất hiện.

| Vị trí muốn lược bỏ | Placeholder hợp lệ trong source | Nội dung có thể hiển thị |
| --- | --- | --- |
| Giá trị gán cho biến | Literal hợp lệ như `0`, `false`, `null` hoặc `"placeholder"` tùy kiểu. | `...` hoặc tên hằng tượng trưng. |
| Biểu thức trả về | Biểu thức hợp lệ có kiểu phù hợp, như `0` hoặc `"placeholder"`. | `return ...;`. |
| Một statement trong method body | Empty statement `;` hoặc lời gọi placeholder hợp lệ. | Dòng `...` hoặc câu lệnh minh họa. |
| Phần thân method | Một hoặc nhiều statement hợp lệ. | Một region rút gọn bằng `...`. |
| Argument trong lời gọi | Biểu thức hợp lệ có kiểu tương thích. | `...` hoặc tên tham số tượng trưng. |
| Giá trị trong annotation | Hằng compile-time phù hợp với kiểu annotation element. | Dạng rút gọn chỉ trong HTML; source giữ giá trị thật. |

Ví dụ với giá trị boolean:

~~~java
boolean enabled = false; // @replace substring="false" replacement="..."
~~~

Source hợp lệ; HTML hiển thị `boolean enabled = ...;`.

Ví dụ với return value kiểu số:

~~~java
int calculate() {
    return 0; // @replace substring="0" replacement="..."
}
~~~

Source biên dịch nếu method còn lại hợp lệ; HTML có `return ...;`.

Lưu ý: placeholder phải có kiểu phù hợp với vị trí. Không thể thay mọi biểu thức bằng một literal tùy ý rồi kỳ vọng compiler vẫn chấp nhận. Chọn giá trị mặc định đúng kiểu, hoặc dùng một biến/hằng có kiểu phù hợp.

## 5. Lược bỏ phần thân method bằng region

Khi ví dụ cần giữ chữ ký method nhưng không cần giải thích cài đặt, hãy dùng region:

~~~java
/**
 * Ví dụ minh họa một method có phần triển khai được lược bỏ:
 * {@snippet :
 *     public int calculate(int input) {
 *         // @replace region="implementation" replacement="..." :
 *         int normalized = Math.max(0, input);
 *         int result = normalized * 2;
 *         return result;
 *         // @end region="implementation"
 *     }
 * }
 */
public class RegionPlaceholderDoc {
}
~~~

Nội dung hiển thị:

~~~java
public int calculate(int input) {
    ...
}
~~~

Source ban đầu có ba statement Java hợp lệ. Javadoc thay toàn bộ region `implementation` bằng `...`. Kết quả HTML là một bản trình bày rút gọn, không phải một method body có thể biên dịch.

Điều này hữu ích khi người đọc chỉ cần biết:

- Tên method.
- Kiểu trả về.
- Tham số đầu vào.
- Vị trí method được sử dụng trong API.

Nếu cần giữ một statement quan trọng và chỉ lược bỏ phần còn lại, hãy chia ví dụ thành các region riêng hoặc chọn selector cụ thể hơn. Đừng thay toàn bộ region khi một vài dòng trong đó là nội dung người học cần hiểu.

## 6. Phân biệt inline snippet và external snippet

Javadoc hỗ trợ hai cách cung cấp nội dung snippet. Mỗi cách có mục đích và giới hạn riêng.

### 6.1. Inline snippet

~~~java
/**
 * Ví dụ về giới hạn số lần thử:
 * {@snippet :
 *     int maxAttempts = 3; // @highlight substring="maxAttempts"
 *     if (maxAttempts > 0) {
 *         System.out.println(maxAttempts);
 *     }
 * }
 */
public class InlineSnippetDoc {
}
~~~

Nội dung snippet nằm ngay trong documentation comment. Compiler xử lý file Java chứa class và comment; nội dung bên trong `{@snippet}` không phải một compilation unit riêng được `javac` biên dịch như mã chương trình độc lập.

Vì vậy, inline snippet có thể chứa đoạn mã ngắn, mã giả hoặc ví dụ không hoàn chỉnh tùy mục tiêu tài liệu. Tuy nhiên, cú pháp Javadoc và markup vẫn cần hợp lệ để `javadoc` tạo tài liệu thành công.

### 6.2. External snippet

External snippet lấy mã từ một file riêng:

~~~java
/**
 * Ví dụ đầy đủ về cách gọi service:
 * {@snippet file="ServiceExample.java" region="usage"}
 */
public class ExternalSnippetDoc {
}
~~~

File external có thể được tổ chức như source Java bình thường, có package, class và method. Nếu nó là một file Java hoàn chỉnh, có thể chạy `javac` để kiểm tra riêng.

Một ví dụ external đặc biệt hữu ích khi muốn giữ source biên dịch được nhưng HTML trình bày bản rút gọn bằng `@replace`. File nguồn chứa placeholder hợp lệ; Javadoc lấy nội dung và biến đổi nó khi tạo snippet hiển thị.

### So sánh

| Đặc điểm | Inline snippet | External snippet |
| --- | --- | --- |
| Nơi lưu mã | Bên trong comment `{@snippet : ...}`. | File riêng, tham chiếu bằng thuộc tính `file`. |
| Compiler kiểm tra | Không biên dịch phần snippet như file Java độc lập. | Có thể biên dịch file ngoài nếu nó là compilation unit hợp lệ. |
| Phù hợp với | Ví dụ ngắn, mã giả, đoạn minh họa tại chỗ. | Ví dụ dài, có thể tái sử dụng hoặc cần biên dịch độc lập. |
| Markup comment | Được xử lý khi sinh Javadoc. | Được xử lý khi Javadoc trích nội dung file. |
| Khả năng source và HTML khác nhau | Có, thông qua markup. | Có, thông qua markup; source gốc vẫn là file riêng. |

## 7. Ví dụ hoàn chỉnh: external source biên dịch được, HTML là mã rút gọn

Giả sử cấu trúc thư mục:

~~~text
src/
└── demo/
    ├── ServiceDoc.java
    └── snippet-files/
        └── ServiceExample.java
~~~

### 7.1. File external `ServiceExample.java`

~~~java
package demo;

public final class ServiceExample {
    private ServiceExample() {
    }

    public static int calculate(int input) {
        // @start region="implementation"
        int normalized = Math.max(0, input);
        int doubled = normalized * 2;
        return doubled; // @replace substring="doubled" replacement="..."
        // @end region="implementation"
    }

    public static void main(String[] args) {
        // @start region="usage"
        int result = calculate(10); // @replace substring="calculate(10)" replacement="..."
        System.out.println(result);
        // @end region="usage"
    }
}
~~~

File này là Java source hợp lệ:

- Constructor private có body hợp lệ.
- Method `calculate` có các statement đầy đủ.
- Method `main` có lời gọi method và câu lệnh in hợp lệ.
- Marker region và markup replace là comment nên compiler bỏ qua chúng.

### 7.2. File Javadoc `ServiceDoc.java`

~~~java
package demo;

/**
 * Ví dụ sử dụng service:
 * {@snippet file="ServiceExample.java" region="usage"}
 *
 * Phần cài đặt chi tiết:
 * {@snippet file="ServiceExample.java" region="implementation"}
 */
public final class ServiceDoc {
}
~~~

Snippet `usage` hiển thị:

~~~java
int result = ...;
System.out.println(result);
~~~

Snippet `implementation` hiển thị:

~~~java
int normalized = Math.max(0, input);
int doubled = normalized * 2;
return ...;
~~~

File source vẫn giữ lời gọi `calculate(10)` và phần triển khai method. Trong snippet `implementation`, Javadoc trích region được mở bằng `@start`; markup `@replace` chỉ thay chữ `doubled` trên dòng return. HTML vì thế trình bày `return ...;` trong khi source vẫn trả về biến `doubled`.

Lưu ý: markup `@replace` được đặt trong file external và Javadoc áp dụng khi đọc file đó. Không cần chỉnh sửa source sau khi sinh tài liệu.

## 8. Kiểm tra source và bản trình bày bằng hai công cụ

Không có một lệnh duy nhất thay thế cả hai loại kiểm tra. Dùng `javac` để kiểm tra source và `javadoc` để kiểm tra markup cùng HTML.

### 8.1. Biên dịch file external bằng `javac`

Từ thư mục gốc của ví dụ, chạy:

~~~bash
javac -d out src/demo/snippet-files/ServiceExample.java
~~~

Nếu lệnh thành công, file external là Java compilation unit hợp lệ. Markup comment không làm thay đổi cú pháp chương trình.

### 8.2. Sinh tài liệu bằng `javadoc`

Chạy:

~~~bash
javadoc -d docs -sourcepath src demo
~~~

Mở `docs/demo/ServiceDoc.html`. Kiểm tra:

1. Region `usage` được trích đúng.
2. Lời gọi `calculate(10)` được thay bằng `...`.
3. Region `implementation` được thay bằng một dấu ba chấm.
4. Các marker `@start`, `@end` và `@replace` không xuất hiện như comment trong khối mã.
5. File `ServiceExample.java` trên đĩa vẫn còn các statement gốc.

Compiler và Javadoc trả lời hai câu hỏi khác nhau:

| Lệnh | Câu hỏi được trả lời |
| --- | --- |
| `javac` | File source có hợp lệ và biên dịch được không? |
| `javadoc` | Snippet có được trích và biến đổi đúng để trình bày không? |

Đầu ra Javadoc có thể không biên dịch được vì `@replace` đã thay literal, statement hoặc region bằng `...`. Điều này không chứng minh source gốc sai.

## 9. Khi nào nên dùng placeholder, comment hoặc `@replace`?

Không phải ví dụ nào cũng cần replacement. Chọn kỹ thuật theo điều muốn truyền đạt:

| Mục tiêu | Cách nên dùng | Lý do |
| --- | --- | --- |
| Lược bỏ phần triển khai dài, chỉ cần nói rằng còn code khác | Comment `// ...` nếu muốn giữ chú thích trong snippet. | Đơn giản, không cần markup. |
| Muốn dấu ba chấm xuất hiện như một dòng mã giả | Placeholder hợp lệ + `@replace`. | Source có thể biên dịch; HTML có thể rút gọn. |
| Muốn thay một giá trị cụ thể bằng tên tượng trưng | `@replace substring`. | Giữ lại cấu trúc câu lệnh và thay đúng literal. |
| Muốn thay nhiều dạng có chung mẫu | `@replace regex`. | Chọn theo mẫu và có thể dùng capture group. |
| Muốn lược bỏ nhiều dòng triển khai | `@replace region`. | Thay cả phần đã đánh dấu bằng một placeholder. |
| Muốn ví dụ là mã giả ngay từ đầu | Inline snippet có thể dùng mã minh họa không hoàn chỉnh. | Không cần duy trì file source biên dịch riêng. |
| Muốn ví dụ được compiler kiểm tra độc lập | External snippet là compilation unit hoàn chỉnh. | Có thể chạy `javac` riêng trước khi sinh Javadoc. |

Một nguyên tắc hữu ích: nếu đoạn mã là ví dụ hướng dẫn một cú pháp hoặc API, hãy giữ phần quan trọng nhất nguyên vẹn. Chỉ lược bỏ phần không liên quan. Một snippet chỉ có dấu ba chấm thường không đủ để người học hiểu API đang được sử dụng như thế nào.

## 10. Những giới hạn và lỗi thường gặp

| Nhầm lẫn | Thực tế | Cách xử lý |
| --- | --- | --- |
| Nghĩ `...` là statement Java. | Dấu ba chấm đứng riêng trong method body không phải statement hợp lệ. | Dùng placeholder hợp lệ trong source rồi thay bằng `@replace`, hoặc ghi rõ đó là mã giả. |
| Nghĩ varargs `String... args` cũng chỉ là placeholder. | `...` trong formal parameter declaration là cú pháp Java thật. | Phân biệt ngữ cảnh khai báo varargs với dấu ba chấm lược bỏ. |
| Biên dịch HTML sau khi replacement. | HTML có thể cố ý chứa `return ...;` hoặc dòng `...` không hợp lệ với compiler. | Biên dịch source gốc, kiểm tra HTML riêng. |
| Nghĩ `javadoc` tự chạy `javac` cho external snippet. | Javadoc trích và xử lý văn bản; nó không thay thế bước compile riêng. | Chạy `javac` rõ ràng khi cần bảo đảm source biên dịch được. |
| Dùng placeholder sai kiểu. | Literal thay thế ban đầu có thể không phù hợp với kiểu biến hoặc giá trị trả về. | Chọn placeholder hợp lệ theo ngữ cảnh source. |
| Dùng `@replace` mà quên selector. | Toàn bộ dòng hoặc region sẽ bị thay. | Thêm `substring`/`regex` nếu chỉ muốn thay một phần. |
| Quên kết thúc region. | Marker vùng không đầy đủ có thể khiến Javadoc báo lỗi. | Đóng bằng `@end` tương ứng. |
| Nghĩ replacement xóa source gốc. | Source không bị chỉnh sửa bởi Javadoc. | Mở lại file external để kiểm tra; replacement chỉ áp dụng cho đầu ra. |
| Dùng `@replace` để ẩn credential. | Giá trị gốc vẫn tồn tại trong file và có thể bị đọc hoặc phân phối. | Không đưa secret vào source hoặc snippet. |

## 11. Bài tập tự đánh giá

### Bài 1 — Dấu ba chấm nào là Java syntax?

Trong hai dòng:

~~~java
public void log(String... messages) { }
public void process() { ... }
~~~

Dòng nào là cú pháp Java hợp lệ?

**Đáp án:** Dòng khai báo `String... messages` hợp lệ vì đây là varargs. Dòng thứ hai không hợp lệ vì `...` đứng riêng không phải statement.

### Bài 2 — Giữ source hợp lệ, thay literal bằng dấu ba chấm

Source:

~~~java
int limit = 100;
~~~

Muốn hiển thị `int limit = ...;`, viết:

~~~java
int limit = 100; // @replace substring="100" replacement="..."
~~~

Source vẫn có literal số nguyên hợp lệ; HTML có dấu ba chấm thay cho literal.

### Bài 3 — Lược bỏ cả phần triển khai

Source có ba statement trong một region. Muốn hiển thị một dòng `...` thay cho cả vùng, dùng:

~~~java
// @replace region="body" replacement="..." :
int first = calculateFirst();
int second = calculateSecond();
return first + second;
// @end region="body"
~~~

Dấu `:` làm region bắt đầu ở dòng tiếp theo; marker `@end` kết thúc vùng.

### Bài 4 — Compiler và Javadoc có thể cho kết quả khác nhau không?

Source external chứa:

~~~java
return 0; // @replace substring="0" replacement="..."
~~~

Compiler có thể biên dịch source nhưng HTML hiển thị `return ...;` không?

**Đáp án:** Có. Compiler đọc source gốc có biểu thức `0` hợp lệ. Javadoc thay literal bằng `...` khi tạo HTML; kết quả hiển thị không nhất thiết là Java code có thể biên dịch.

### Bài 5 — Nên dùng inline hay external snippet?

Một ví dụ dài có nhiều method, cần compiler kiểm tra và đồng thời muốn lược bỏ implementation trong HTML. Nên chọn loại nào?

**Đáp án:** External snippet. Lưu ví dụ thành file Java hoàn chỉnh, dùng `javac` kiểm tra source và dùng `{@snippet file=...}` để Javadoc trích region. `@replace` biến đổi bản hiển thị mà không sửa file gốc.

## Tổng kết

- Dấu ba chấm `...` thường biểu thị nội dung bị lược bỏ trong tài liệu, nhưng `String... args` là cú pháp varargs hợp lệ của Java.
- Source, markup comment và snippet HTML là ba lớp nội dung khác nhau.
- `@replace` thay văn bản trong đầu ra Javadoc; file source và hành vi runtime vẫn nguyên vẹn.
- Hãy chọn placeholder hợp lệ theo vị trí cú pháp, rồi thay bằng `...` hoặc nội dung giải thích.
- Inline snippet phù hợp với ví dụ tại chỗ; external snippet phù hợp với source dài hoặc cần biên dịch độc lập.
- `javac` kiểm tra source; `javadoc` kiểm tra markup và nội dung hiển thị. Đầu ra sau replacement có thể là mã giả và không cần biên dịch được.
- Không dùng replacement để che secret: source gốc vẫn chứa giá trị ban đầu.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Documentation Comment Specification, JDK 27, mục Modifying the displayed text](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html#snippet): quy tắc `@replace`, selector, replacement và region.
2. [Oracle — JavaDoc Guide: Snippets, JDK 26](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): inline/external snippet và ví dụ thay văn bản hiển thị.
3. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): thiết kế `{@snippet}` được đưa vào Java 18.
4. [Oracle — Java Language Specification, Java SE 27, `8.4.1 Formal Parameters`](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.1): quy tắc formal parameter và variable arity parameter.
5. [Oracle — The javac Command, JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): biên dịch source Java bằng compiler.
6. [Oracle — The javadoc Command, JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html): sinh tài liệu API và xử lý documentation comments.
