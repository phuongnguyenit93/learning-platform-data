# Quy tắc cân bằng dấu ngoặc nhọn trong nội dung inline snippet

## 1. Mục tiêu và phạm vi

**JEP 413 – Code Snippets in Java API Documentation** bổ sung thẻ `{@snippet ...}` cho Javadoc từ **JDK 18**. Tính năng này tiếp tục được hỗ trợ trên các JDK hiện đại và giúp trình bày ví dụ mã trong tài liệu API. Khi dùng dạng inline, nội dung snippet nằm ngay trong chú thích `/** ... */` của mã nguồn. Vì vậy, Javadoc phải xác định được đâu là dấu ngoặc của đoạn mã và đâu là dấu ngoặc kết thúc thẻ inline.

Bài học tập trung vào quy tắc **các dấu ngoặc nhọn `{` và `}` phải cân bằng và lồng đúng thứ tự** trong nội dung inline snippet. Sau bài học, bạn có thể:

- Giải thích cách Javadoc xác định dấu `}` đóng thẻ `{@snippet ...}`.
- Nhận diện dấu ngoặc trong block Java, chuỗi, ký tự, comment và text block.
- Hiểu vì sao dấu ngoặc trong string literal vẫn được tính, dù Java coi chúng là ký tự dữ liệu.
- Sửa ví dụ có ngoặc mất cân bằng hoặc chuyển sang external snippet khi cần giữ nguyên nội dung.
- Kiểm tra cú pháp tài liệu và kiểm chứng riêng hành vi của mã ví dụ.

Đây là quy tắc phân tích **inline tag trong chú thích tài liệu**, không phải quy tắc biên dịch Java. Javadoc không phân tích ngữ nghĩa Java để nhận biết một dấu ngoặc nằm trong chuỗi hay comment; nó cần đếm các dấu ngoặc theo cú pháp inline tag.

## 2. Cách Javadoc tìm dấu đóng của inline snippet

Một inline snippet có cấu trúc:

~~~java
/**
 * Ví dụ:
 *
 * {@snippet :
 * if (ready) {
 *     System.out.println("Ready");
 * }
 * }
 */
~~~

Có hai lớp cú pháp cùng xuất hiện:

1. **Inline tag Javadoc** mở bằng `{@snippet` và đóng bằng dấu `}` tương ứng.
2. **Mã Java bên trong** có thể có các block riêng, mỗi block mở bằng `{` và đóng bằng `}`.

Dấu `}` đầu tiên mà Javadoc xác định là khớp với dấu `{` mở inline tag sẽ kết thúc snippet. Các dấu ngoặc của block Java nằm bên trong phải được cân bằng trước khi đến dấu đóng thẻ.

Quy tắc tổng quát của inline tag yêu cầu các dấu ngoặc nhọn xuất hiện trong nội dung tự do phải có **số lượng bằng nhau và được lồng đúng thứ tự**. Javadoc không thực hiện phân tích từ vựng như trình biên dịch Java để bỏ qua dấu ngoặc trong dấu nháy đơn, dấu nháy kép hoặc sau dấu gạch chéo ngược. Vì vậy, parser vẫn nhìn thấy dấu ngoặc trong string literal, character literal, comment và text block.

Có thể mô phỏng cách đếm để hiểu:

- Bắt đầu ở dấu `{` mở thẻ `{@snippet`.
- Gặp một dấu `{` trong phần thân thì có thêm một mức lồng.
- Gặp dấu `}` thì đóng mức lồng gần nhất.
- Khi dấu `}` khớp với dấu mở thẻ ngoài cùng, inline snippet kết thúc.

Đây là mô hình giải thích cú pháp, không phải đoạn mã Java mà người học cần chạy. Điều quan trọng là **parser chỉ quan tâm ký tự ngoặc và thứ tự lồng nhau**, không quan tâm ý nghĩa Java của chúng.

## 3. Các block Java thông thường: trường hợp dễ nhất

Các cấu trúc Java có block thường đã tự tạo ra cặp ngoặc cân bằng. Ví dụ:

~~~java
/**
 * {@snippet :
 * if (quantity > 0) {
 *     System.out.println(quantity);
 * }
 * }
 */
~~~

Trong ví dụ:

- `if (...) {` mở block điều kiện.
- Dấu `}` ngay sau lệnh in đóng block `if`.
- Dấu `}` cuối cùng đóng thẻ snippet.

Với nhiều block lồng nhau, mỗi block cần được đóng theo thứ tự ngược lại với lúc mở:

~~~java
/**
 * {@snippet :
 * if (order != null) {
 *     for (Item item : order.items()) {
 *         if (item.isAvailable()) {
 *             process(item);
 *         }
 *     }
 * }
 * }
 */
~~~

Hãy đọc các dấu ngoặc từ trong ra ngoài:

1. Block `if (item.isAvailable())` được đóng trước.
2. Tiếp theo là block `for`.
3. Sau đó là block `if (order != null)`.
4. Cuối cùng mới là dấu `}` đóng snippet.

Cách viết này có thể kiểm tra bằng cách ghép từng dấu mở với dấu đóng tương ứng. Nếu bỏ một dấu đóng ở bên trong, dấu `}` cuối cùng có thể bị dùng để đóng block Java thay vì đóng inline tag, khiến Javadoc báo lỗi hoặc phân tích sai phần còn lại của chú thích.

## 4. Dấu ngoặc trong string literal và character literal vẫn được tính

Đây là điểm dễ gây nhầm lẫn nhất. Trình biên dịch Java hiểu nội dung nằm trong dấu nháy là dữ liệu. Parser inline tag của Javadoc **không có quy tắc đặc biệt cho dấu nháy**. Nó không biết `}` là ký tự của chuỗi và không bỏ qua nó.

### 4.1. Một dấu ngoặc đóng trong chuỗi

Ví dụ sau không an toàn:

~~~java
/**
 * {@snippet :
 * String closingBrace = "}";
 * System.out.println(closingBrace);
 * }
 */
~~~

Trong Java, `"}"` là một string literal hợp lệ. Nhưng khi phân tích inline tag, dấu `}` bên trong chuỗi vẫn là một dấu ngoặc đóng. Nó có thể được xem là dấu kết thúc snippet trước khi Javadoc đọc đến dòng cuối. Kết quả là thẻ bị đóng sớm và phần còn lại không còn thuộc snippet như tác giả dự định.

### 4.2. Một dấu ngoặc mở trong chuỗi

Trường hợp ngược lại cũng có vấn đề:

~~~java
/**
 * {@snippet :
 * String openingBrace = "{";
 * System.out.println(openingBrace);
 * }
 */
~~~

Dấu `{` trong chuỗi tạo thêm một mức lồng theo cách đếm của inline tag. Dấu `}` cuối cùng mà tác giả định dùng để đóng snippet có thể chỉ đóng dấu `{` trong chuỗi; dấu mở thẻ ngoài cùng vẫn chưa được đóng. Javadoc vì vậy không xác định được điểm kết thúc như mong muốn.

### 4.3. Hai dấu ngoặc cân bằng trong cùng một chuỗi

Ví dụ:

~~~java
/**
 * {@snippet :
 * String braces = "{}";
 * System.out.println(braces);
 * }
 */
~~~

Hai ký tự ngoặc trong chuỗi tạo thành một cặp cân bằng khi xét theo ký tự. Parser vẫn tính chúng, dù Java coi cả hai là nội dung chuỗi. Trường hợp này có thể thỏa điều kiện cân bằng về mặt ký tự, nhưng làm người đọc khó phân biệt ngoặc của mã với ngoặc dữ liệu. Với ví dụ cần minh họa dữ liệu có ngoặc, **external snippet thường rõ ràng và dễ bảo trì hơn**.

### 4.4. Character literal cũng có cùng quy tắc

Không có ngoại lệ cho dấu nháy đơn:

~~~java
/**
 * {@snippet :
 * char closing = '}';
 * }
 */
~~~

Dấu `}` trong character literal vẫn tham gia vào việc xác định dấu kết thúc inline tag. Tương tự, `'{'` tạo thêm dấu mở. Đừng dựa vào quy tắc escape của Java để nghĩ rằng parser Javadoc sẽ bỏ qua những ký tự này.

## 5. Dấu ngoặc trong comment, text block và markup comment

Parser inline tag không phân tích cú pháp Java. Do đó, dấu ngoặc nhọn xuất hiện ở bất cứ vị trí nào trong nội dung đều cần được tính.

### 5.1. Comment một dòng

~~~java
/**
 * {@snippet :
 * // Giá trị ví dụ: }
 * System.out.println("done");
 * }
 */
~~~

Dù dấu `}` đầu tiên chỉ nằm trong comment Java, parser inline tag vẫn nhìn thấy nó. Comment một dòng không làm dấu ngoặc trở nên vô hình.

### 5.2. Comment nhiều dòng

~~~java
/**
 * {@snippet :
 * /*
 *  * Mẫu dữ liệu có dấu {
 *  */
 * System.out.println("done");
 * }
 */
~~~

Dấu `{` trong comment vẫn được tính. Ngoài ra, nội dung inline snippet có giới hạn riêng: **không được chứa chuỗi ký tự `*/`** vì chuỗi này kết thúc chú thích tài liệu Java bên ngoài. Vì vậy, block comment như ví dụ trên không thể được nhúng nguyên vẹn trong inline snippet.

### 5.3. Text block

~~~java
/**
 * {@snippet :
 * String json = """
 *     {
 *       "status": "ready"
 *     }
 *     """;
 * System.out.println(json);
 * }
 */
~~~

Text block là một dạng string literal trong Java, nhưng các dấu `{` và `}` bên trong vẫn là ký tự thô đối với parser inline tag. Ở ví dụ JSON, hai dấu ngoặc tạo thành cặp cân bằng; tuy nhiên, cấu trúc dữ liệu phức tạp có thể chứa ngoặc mất cân bằng theo từng mảnh, làm việc nhúng inline trở nên khó kiểm soát.

### 5.4. Markup comment của snippet

Các chỉ thị như `// @highlight`, `// @start region=...` và `// @end region=...` cũng nằm trong nội dung snippet. Nếu comment chứa dấu ngoặc nhọn thì các ký tự đó vẫn được tính khi Javadoc phân tích inline tag. Đừng cho rằng vì đó là markup comment nên dấu ngoặc sẽ bị bỏ qua trước khi tìm dấu đóng thẻ.

## 6. Dấu gạch chéo ngược không escape được ngoặc nhọn

Trong Java string literal, dấu gạch chéo ngược có thể tạo escape sequence. Ví dụ `"\\}"` có thể được dùng để biểu diễn dấu `}` trong dữ liệu chuỗi. Tuy nhiên, **parser inline tag không phân tích escape sequence Java**. Nó không coi `\\}` là một dấu ngoặc đóng đã được escape.

Ví dụ không nên dựa vào:

~~~java
/**
 * {@snippet :
 * String closingBrace = "\\}";
 * }
 */
~~~

Khi đọc nội dung inline tag, Javadoc vẫn thấy ký tự `}` sau dấu gạch chéo ngược. Dấu gạch chéo ngược không làm thay đổi quy tắc ghép ngoặc của inline tag.

Unicode escape cũng cần cẩn trọng. Unicode escape trong mã nguồn được xử lý trong quá trình phân tích source trước khi Javadoc xử lý comment. Vì vậy, viết dạng `\u007d` để mong dấu đóng không được nhận diện không phải là cách escape an toàn; sau bước xử lý Unicode, nó có thể trở thành chính ký tự `}`.

**Không có escape sequence riêng để cho phép đặt tùy ý một dấu ngoặc nhọn không cân bằng trong nội dung inline snippet.** Khi cần thể hiện đúng một đoạn mã như vậy, hãy chuyển sang external snippet.

## 7. Cách xử lý khi ví dụ không thể cân bằng

Nếu nội dung minh họa có dấu ngoặc nhọn không cân bằng theo cách đếm ký tự, có hai lựa chọn thực tế:

1. **Chỉnh ví dụ nếu nội dung cho phép:** viết lại ví dụ để không còn ký tự gây nhầm lẫn, nhưng chỉ khi cách viết mới vẫn trung thực với điều cần giải thích.
2. **Dùng external snippet:** đặt mã vào một tệp riêng rồi tham chiếu bằng thuộc tính `file` hoặc `class`. Đây là cách phù hợp khi cần giữ nguyên string literal, character literal, regex, JSON, comment hoặc text block có ký tự đặc biệt.

Không nên tự thêm một dấu ngoặc vào ví dụ chỉ để thỏa parser nếu điều đó làm thay đổi dữ liệu hoặc ý nghĩa của mã. Tài liệu API phải thể hiện đúng hành vi mà người dùng cần học.

### Ví dụ external snippet có thể giữ nguyên dấu ngoặc

Cấu trúc thư mục:

~~~text
src/main/java/
└── example/
    ├── BraceExamples.java
    └── snippet-files/
        └── BraceDataExamples.java
~~~

Tệp `src/main/java/example/snippet-files/BraceDataExamples.java`:

~~~java
package example;

public final class BraceDataExamples {
    private BraceDataExamples() {
    }

    public static void main(String[] args) {
        // @start region=brace-data
        String closingBrace = "}";
        String openingBrace = "{";
        String json = """
                {
                  "status": "ready"
                }
                """;
        System.out.println(closingBrace);
        System.out.println(openingBrace);
        System.out.println(json);
        // @end region=brace-data
    }
}
~~~

Trong Javadoc của lớp `BraceExamples`, tham chiếu vùng cần trình bày:

~~~java
/**
 * Ví dụ dữ liệu chứa dấu ngoặc nhọn:
 *
 * {@snippet file="BraceDataExamples.java" region=brace-data}
 */
public class BraceExamples {
}
~~~

External snippet lấy nội dung từ tệp riêng nên không bị giới hạn cân bằng ngoặc của inline tag. Tệp ngoài cũng có thể chứa block comment `/* ... */` mà không kết thúc chú thích Javadoc đang chứa thẻ tham chiếu.

Tệp ví dụ vẫn là mã nguồn Java thông thường: có thể biên dịch và chạy bằng công cụ JDK. Tuy nhiên, **Javadoc chỉ trích và trình bày nội dung**; cần thực hiện bước biên dịch/chạy hoặc kiểm thử riêng nếu muốn xác nhận ví dụ đúng.

## 8. Cách tự kiểm tra cặp ngoặc trước khi tạo tài liệu

Với một inline snippet, có thể rà soát theo trình tự:

1. Tìm dấu `{@snippet` mở thẻ và xác định dòng có dấu `:`.
2. Bắt đầu đọc từ dòng mới đầu tiên sau dấu `:`.
3. Duyệt từng ký tự `{` và `}` trong toàn bộ nội dung. **Không bỏ qua** dấu ngoặc chỉ vì nó nằm trong chuỗi, comment, text block hoặc sau dấu gạch chéo ngược.
4. Mỗi dấu `{` phải được ghép với một dấu `}` phía sau theo đúng thứ tự lồng nhau.
5. Đảm bảo không có dấu `}` nào đóng thẻ ngoài cùng trước khi hết nội dung dự định hiển thị.
6. Đảm bảo dấu `}` cuối cùng là dấu đóng thẻ inline snippet.
7. Kiểm tra thêm rằng nội dung không có chuỗi `*/`; đây là giới hạn của chú thích tài liệu truyền thống, độc lập với quy tắc ngoặc.
8. Sinh Javadoc để xác nhận parser chấp nhận thẻ và xem HTML kết quả có chứa đúng phần mã hay không.

Một mẹo hữu ích là ghi chú cặp mở/đóng tạm thời bên cạnh ví dụ trong lúc rà soát. Không giữ các ghi chú đó trong mã nguồn nếu chúng làm ví dụ khó đọc.

### Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Snippet kết thúc ngay giữa string literal. | Dấu `}` trong chuỗi bị tính như dấu đóng thẻ. | Dùng external snippet hoặc viết lại dữ liệu minh họa khi không đổi ý nghĩa. |
| Javadoc báo thiếu dấu đóng inline tag. | Dấu `{` trong string/comment tạo thêm mức lồng, nhưng không có dấu `}` ghép tương ứng. | Kiểm tra toàn bộ nội dung, kể cả chuỗi và comment; chuyển sang external nếu cần. |
| Đoạn có block Java lồng nhau bị lỗi. | Thiếu dấu `}` đóng một block hoặc sai thứ tự đóng. | Ghép từng cặp từ block trong cùng ra block ngoài. |
| Thêm `\\` trước `}` nhưng vẫn lỗi. | Backslash không phải escape cho parser inline tag. | Không dùng escape Java để điều khiển cú pháp Javadoc. |
| Mã có `*/` làm chú thích kết thúc bất ngờ. | Ký tự này kết thúc comment Java bên ngoài. | Đưa ví dụ vào tệp external. |
| Tài liệu sinh được nhưng ví dụ sai kết quả. | Javadoc trình bày snippet, không tự chạy logic Java. | Biên dịch và chạy ví dụ hoặc thêm unit test. |

## 9. Bài tập thực hành

### Bài tập 1: Đếm dấu ngoặc trong block lồng nhau

Xét nội dung:

~~~java
{@snippet :
    if (account != null) {
        for (Order order : account.orders()) {
            if (order.isValid()) {
                submit(order);
            }
        }
    }
}
~~~

Hãy xác định dấu `}` nào đóng từng block và dấu `}` nào đóng snippet. Sau đó thử xóa dấu đóng của `for`, dự đoán parser sẽ ghép các dấu còn lại như thế nào.

### Bài tập 2: String literal có ngoặc

Xét ba dòng riêng:

~~~java
String a = "}";
String b = "{";
String c = "{}";
~~~

- Dòng nào tạo một dấu ngoặc đóng không có dấu mở tương ứng?
- Dòng nào tạo dấu mở không có dấu đóng tương ứng?
- Dòng nào có cặp ngoặc cân bằng theo ký tự?
- Vì sao parser vẫn đếm dấu ngoặc dù chúng nằm trong string literal?

Đáp án: dòng `a` có dấu đóng lẻ; dòng `b` có dấu mở lẻ; dòng `c` có cặp cân bằng. Parser không phân tích ngữ nghĩa string literal và không loại bỏ ký tự nằm trong dấu nháy.

### Bài tập 3: Chuyển ví dụ sang external snippet

Tạo một tệp `BraceDataExamples.java` có các dữ liệu:

- Chuỗi chứa ký tự `}`.
- Character literal chứa ký tự `{`.
- Một text block chứa object JSON với các cặp ngoặc.
- Một comment giải thích định dạng dữ liệu.

Đánh dấu vùng `region=brace-data`, sau đó tham chiếu từ Javadoc bằng `{@snippet file="BraceDataExamples.java" region=brace-data}`. Biên dịch tệp ví dụ bằng `javac` và tạo tài liệu bằng `javadoc` để kiểm tra đường dẫn và vùng được trích.

**Tự kiểm:** không có nội dung inline mất cân bằng; hiểu rõ dấu ngoặc trong chuỗi/comment vẫn được tính; ví dụ external giữ nguyên dữ liệu; mô tả API không bị thay đổi để chiều theo parser.

## 10. Ghi nhớ

- **Inline snippet yêu cầu ngoặc nhọn cân bằng và lồng đúng thứ tự.** Dấu đóng đầu tiên khớp với dấu mở của thẻ sẽ kết thúc inline snippet.
- **Javadoc không bỏ qua ngoặc trong string, character literal, comment hoặc text block.** Parser không thực hiện phân tích từ vựng Java cho nội dung tự do của inline tag.
- **Backslash không escape ngoặc nhọn** trong inline tag; Unicode escape cũng có thể được xử lý trước khi Javadoc đọc comment.
- **Chuỗi `*/` không thể xuất hiện trong nội dung inline** vì nó kết thúc chú thích tài liệu bên ngoài.
- **External snippet là lựa chọn phù hợp khi cần giữ nguyên dữ liệu hoặc cú pháp không thể biểu diễn an toàn inline.** Mã external có thể được biên dịch/chạy riêng để kiểm chứng.

## Tài liệu chính thống

- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [Oracle – JDK 26 Javadoc Snippets Guide](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification, mục Inline Tags và snippet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).

