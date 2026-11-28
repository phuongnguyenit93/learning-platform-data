# `@replace`: thay đổi văn bản trình bày mà vẫn giữ mã nguồn có thể biên dịch

## Mục tiêu bài học

Từ Java 18, `{@snippet}` cho phép đưa ví dụ mã vào tài liệu API do `javadoc` tạo ra. Đôi khi source cần giữ một giá trị placeholder hợp lệ để công cụ bên ngoài có thể đọc hoặc biên dịch; trong tài liệu, ta lại muốn hiển thị dấu ba chấm, một thông báo rút gọn hoặc cách viết dễ hiểu hơn.

Markup tag **`@replace`** thay một phần văn bản trong snippet bằng nội dung khác **chỉ ở đầu ra Javadoc**. File nguồn vẫn giữ nguyên placeholder ban đầu.

Tính năng này được giới thiệu cùng `{@snippet}` trong Java 18 và tiếp tục được hỗ trợ trong các JDK hiện đại. Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`.

Sau bài học, bạn có thể:

- Dùng `@replace` với `substring` để thay chuỗi nguyên văn.
- Dùng `regex` để thay đoạn khớp mẫu và tái sử dụng capture group.
- Dùng `region` để thay nội dung trên nhiều dòng.
- Thay toàn bộ dòng/vùng khi không chỉ định `substring` hoặc `regex`.
- Xóa nội dung bằng replacement rỗng và chèn nội dung bằng no-op placeholder.
- Phân biệt source được biên dịch với nội dung đã biến đổi để trình bày trong Javadoc.
- Kiểm chứng file external snippet bằng `javac` và đầu ra hiển thị bằng `javadoc`.

## 1. Vì sao cần `@replace`?

Một ví dụ có thể cần lược bỏ chi tiết để người đọc tập trung vào ý chính. Chẳng hạn, mã nguồn dùng chuỗi rỗng làm giá trị placeholder:

~~~java
var text = "";
~~~

Nếu hiển thị nguyên văn, người đọc có thể hiểu nhầm chuỗi rỗng là dữ liệu quan trọng. Ta muốn trình bày:

~~~java
var text = ...;
~~~

Dấu `...` giúp thể hiện rằng giá trị cụ thể được lược bỏ. Tuy nhiên, viết trực tiếp `...` trong mã Java không phải biểu thức hợp lệ ở vị trí gán cho biến.

`@replace` cho phép giữ placeholder hợp lệ trong source và thay nó khi Javadoc sinh HTML:

~~~java
var text = ""; // @replace substring='""' replacement="..."
~~~

Kết quả hiển thị trong Javadoc:

~~~java
var text = ...;
~~~

| Nơi xem | Nội dung |
| --- | --- |
| File nguồn Java | `var text = "";` cùng markup comment `@replace`. |
| Snippet trong HTML Javadoc | `var text = ...;`. |

File nguồn không bị sửa. Bộ xử lý snippet chỉ thay phần hiển thị khi tạo tài liệu.

**Điểm cốt lõi:** `@replace` là phép biến đổi trình bày. Nó không thực thi phép gán, không thay giá trị runtime và không ghi đè file source.

## 2. Cú pháp và phạm vi thay thế

Cú pháp tổng quát:

~~~text
// @replace [substring="văn bản" | regex="biểu_thức"] [region="tên_vùng"] replacement="văn_bản_mới"
~~~

| Thuộc tính | Vai trò |
| --- | --- |
| `substring` | Chọn chuỗi nguyên văn cần thay. Mọi lần xuất hiện trong phạm vi đều được thay. |
| `regex` | Chọn các đoạn khớp biểu thức chính quy. Mọi kết quả khớp trong phạm vi đều được thay. |
| `region` | Xác định phạm vi nhiều dòng; kết thúc bằng `@end` tương ứng. |
| `replacement` | Văn bản mới được đưa vào đầu ra hiển thị. |

**Phạm vi mặc định là dòng hiện tại.** Nếu có `region`, phạm vi là toàn bộ region cho đến marker `@end` tương ứng.

Nếu không có `substring` và cũng không có `regex`, `@replace` thay **toàn bộ phạm vi** bằng giá trị `replacement`. Vì vậy, một chỉ dẫn ở cuối dòng có thể thay cả dòng; một chỉ dẫn mở region có thể thay toàn bộ vùng.

Ví dụ thay một chuỗi cụ thể:

~~~java
int limit = 100; // @replace substring="100" replacement="MAX_LIMIT"
~~~

Kết quả:

~~~java
int limit = MAX_LIMIT;
~~~

Ví dụ thay toàn bộ dòng:

~~~java
// @replace replacement="..." :
long result = calculateDetailedResult(input);
~~~

Kết quả hiển thị:

~~~java
...
~~~

Trong ví dụ thứ hai, markup comment đứng riêng và kết thúc bằng dấu `:`, nên chỉ dẫn áp dụng lên dòng ngay sau nó. Không có selector nên toàn bộ dòng mã được thay bằng `...`.

## 3. Thay chuỗi nguyên văn bằng `substring`

`substring` phù hợp khi biết chính xác phần văn bản cần thay. Ví dụ phổ biến là thay chuỗi placeholder bằng dấu ba chấm:

~~~java
/**
 * {@snippet :
 *     public static void main(String... args) {
 *         var text = ""; // @replace substring='""' replacement="..."
 *         System.out.println(text);
 *     }
 * }
 */
public class ReplaceSubstringDoc {
}
~~~

Nội dung mã được hiển thị:

~~~java
public static void main(String... args) {
    var text = ...;
    System.out.println(text);
}
~~~

Trong source, `""` là string literal hợp lệ. Sau khi thay thế, `...` không còn là biểu thức Java hợp lệ ở vị trí này, nhưng đó là chủ ý của tài liệu: cho người đọc thấy giá trị cụ thể đã được lược bỏ.

### 3.1. Mọi lần xuất hiện trong phạm vi đều được thay

~~~java
String message = "item-item"; // @replace substring="item" replacement="value"
~~~

Kết quả:

~~~java
String message = "value-value";
~~~

`substring` thay **mỗi lần xuất hiện** của chuỗi được chọn trong phạm vi, không chỉ lần đầu tiên. Vì vậy, trước khi dùng selector ngắn như `id` hoặc `x`, hãy kiểm tra xem nó có xuất hiện trong tên dài hơn hay string literal khác hay không.

### 3.2. Dấu nháy trong giá trị selector

Nếu chuỗi cần thay chứa dấu nháy kép, hãy bao giá trị `substring` bằng dấu nháy đơn:

~~~java
String value = "placeholder"; // @replace substring='"placeholder"' replacement="..."
~~~

Giá trị selector là `"placeholder"`, gồm cả hai dấu nháy kép. Dấu nháy đơn bên ngoài giúp parser phân biệt ranh giới thuộc tính.

Quy tắc thuộc tính của snippet không hỗ trợ escape sequence tổng quát. Không tự thêm backslash theo thói quen viết Java string literal. Hãy chọn loại dấu nháy bao ngoài phù hợp với ký tự bên trong giá trị.

## 4. Thay theo mẫu bằng `regex`

Khi phần cần thay thay đổi theo mẫu, `regex` mô tả các chuỗi cần nhận diện.

~~~java
String version = "v1.2"; // @replace regex='v([0-9]+)\.([0-9]+)' replacement="$1.$2"
~~~

Kết quả hiển thị:

~~~java
String version = "1.2";
~~~

Phân tích regex:

- `v` khớp chữ `v` ở đầu chuỗi phiên bản.
- `([0-9]+)` là capture group thứ nhất, nhận một hoặc nhiều chữ số.
- `\.` khớp dấu chấm theo nghĩa literal.
- `([0-9]+)` tiếp theo là capture group thứ hai.

Replacement `$1.$2` lấy nội dung group 1, thêm dấu chấm, rồi lấy nội dung group 2. Đây là quy tắc replacement của `String.replaceAll` trong Java.

### 4.1. Capture group trong replacement

Khi dùng `regex`, có thể dùng `$number` để chèn nội dung của nhóm bắt được:

| Replacement | Ý nghĩa |
| --- | --- |
| `$1` | Nội dung capture group thứ nhất. |
| `$2` | Nội dung capture group thứ hai. |
| `$1-$2` | Ghép nội dung hai group với dấu gạch nối. |
| `$0` | Toàn bộ đoạn khớp, theo quy tắc replacement của Java regex. |

Ví dụ chuẩn hóa mã sản phẩm:

~~~java
String productCode = "SKU-042"; // @replace regex='SKU-([0-9]+)' replacement="Product-$1"
~~~

Kết quả:

~~~java
String productCode = "Product-042";
~~~

Đoạn `042` được capture bởi group 1 và đưa vào replacement. Phần `SKU-` được thay bằng `Product-`.

Tên và số lượng group phải khớp với regex. Nếu replacement tham chiếu group không tồn tại, Javadoc có thể báo lỗi khi xử lý markup. Hãy bắt đầu bằng regex nhỏ, kiểm tra các group, rồi mới dùng replacement phức tạp.

### 4.2. Ký tự đặc biệt trong replacement

Replacement của regex tuân theo quy tắc `Matcher.replaceAll` / `String.replaceAll`:

- Dấu `$` được dùng để tham chiếu capture group.
- Dấu `\` có thể dùng để escape ký tự tiếp theo trong replacement.
- Nếu muốn in một dấu dollar theo nghĩa literal, cần escape nó theo quy tắc replacement của Java regex.

Điều này khác với giá trị selector `regex`: regex mô tả phần cần khớp, còn `replacement` có quy tắc diễn giải riêng. Đừng giả định replacement luôn là văn bản literal không có ký tự đặc biệt.

Ví dụ, replacement `"$1"` không có nghĩa là chuỗi gồm hai ký tự `$1`; nó chèn nội dung group 1. Khi cần hiển thị chính xác ký tự dollar hoặc backslash, hãy kiểm tra quy tắc replacement trong API `Matcher` và xác nhận kết quả bằng HTML do Javadoc sinh ra.

## 5. Thay toàn bộ dòng hoặc vùng

Không phải lúc nào cũng cần selector. Nếu mục tiêu là lược bỏ một dòng chi tiết hoặc thay toàn bộ phần triển khai bằng dấu ba chấm, có thể bỏ `substring` và `regex`.

### 5.1. Thay toàn bộ dòng

~~~java
int calculated = expensiveCalculation(input); // @replace replacement="..."
~~~

Kết quả:

~~~java
...
~~~

Dòng mã nguồn ban đầu vẫn giữ nguyên trong file. Trong Javadoc, cả phạm vi dòng được thay bằng `...`.

### 5.2. Thay toàn bộ region

Có thể dùng `region` để áp dụng replacement trên nhiều dòng:

~~~java
/**
 * {@snippet :
 *     // @replace region="implementation" replacement="..." :
 *     int first = calculateFirst(input);
 *     int second = calculateSecond(first);
 *     return combine(first, second);
 *     // @end region="implementation"
 * }
 */
public class ReplaceRegionDoc {
}
~~~

Vùng `implementation` được thay bằng một dấu ba chấm trong đầu ra. Các dòng trong file nguồn vẫn là các câu lệnh Java ban đầu.

Khi cần giữ một số dòng và chỉ thay phần còn lại, thêm `substring` hoặc `regex` cùng `region`:

~~~java
/**
 * {@snippet :
 *     // @replace region="details" substring="calculateDetailed" replacement="calculate" :
 *     int first = calculateDetailedFirst(input);
 *     int second = calculateDetailedSecond(input);
 *     return combine(first, second);
 *     // @end region="details"
 * }
 */
public class ReplaceRegionSubstringDoc {
}
~~~

Ở ví dụ này, mọi lần xuất hiện của `calculateDetailed` trong region được thay bằng `calculate`. Các phần còn lại của từng dòng được giữ nguyên.

Dấu `:` ở cuối markup comment khiến vùng bắt đầu từ dòng tiếp theo. Marker `@end region="details"` đóng vùng tương ứng.

## 6. Xóa văn bản bằng replacement rỗng

Muốn xóa một đoạn khỏi bản hiển thị, đặt `replacement=""`:

~~~java
System.out.println("debug"); // @replace replacement=""
System.out.println("result");
~~~

Dòng đầu biến mất khỏi snippet được sinh ra; dòng thứ hai vẫn xuất hiện. Trong source, câu lệnh debug vẫn còn nguyên.

Có thể chỉ xóa một phần của dòng:

~~~java
System.out.println("DEBUG: " + message); // @replace substring='"DEBUG: "' replacement=""
~~~

Kết quả:

~~~java
System.out.println( + message);
~~~

Ví dụ trên minh họa phép thay văn bản đúng theo selector; tuy nhiên kết quả có thể không phải mã Java đẹp hoặc hợp lệ. Nếu muốn đầu ra dễ đọc hơn, hãy chọn placeholder hoặc selector phù hợp để thay cả phần biểu thức, thay vì chỉ xóa một mảnh làm hỏng cú pháp.

**Xóa khỏi tài liệu không đồng nghĩa xóa khỏi source.** Nếu một dòng chứa dữ liệu nhạy cảm, replacement rỗng không phải biện pháp bảo vệ dữ liệu: file nguồn vẫn chứa giá trị đó và có thể được lưu trữ, phân phối hoặc đọc bởi công cụ khác.

## 7. Chèn văn bản bằng cách thay một no-op placeholder

`@replace` không chỉ xóa hoặc thay văn bản đã có. Có thể **chèn nội dung mới** bằng cách đặt một placeholder không làm thay đổi hành vi chương trình, rồi thay placeholder đó trong tài liệu.

Ví dụ, một empty statement `;` là Java hợp lệ:

~~~java
public static void main(String[] args) {
    String status = "ready";
    ; // @replace substring=";" replacement='System.out.println("ready");'
}
~~~

File nguồn có empty statement, nên vẫn biên dịch. Trong Javadoc, dấu `;` được thay bằng câu lệnh:

~~~java
public static void main(String[] args) {
    String status = "ready";
    System.out.println("ready");
}
~~~

Đây là cách chèn một dòng ví dụ mà không đưa câu lệnh hiển thị vào source đang được biên dịch. Cần đảm bảo câu lệnh thay thế phù hợp với ngữ cảnh của snippet.

Một no-op khác có thể dùng là marker comment `//`. Empty statement thường dễ nhận biết và ít phụ thuộc vào cách xử lý comment của ngôn ngữ hơn.

## 8. Ví dụ thực tế: external snippet vẫn biên dịch

Đây là trường hợp thể hiện rõ nhất mục tiêu “giữ source hợp lệ nhưng trình bày rút gọn”.

Tạo cấu trúc:

~~~text
src/
└── demo/
    ├── ReplaceDoc.java
    └── snippet-files/
        └── CompileReadyExample.java
~~~

### 8.1. File nguồn external snippet

File `src/demo/snippet-files/CompileReadyExample.java`:

~~~java
package demo;

public final class CompileReadyExample {
    public static void main(String[] args) {
        // @start region="main"
        String endpoint = "https://api.example.test";
        String token = "placeholder"; // @replace substring='"placeholder"' replacement="..."
        System.out.println(endpoint);
        System.out.println(token); // @replace replacement=""
        ; // @replace substring=";" replacement='System.out.println("done");'
        // @end region="main"
    }
}
~~~

Đây là một file Java hoàn chỉnh:

- `"placeholder"` là string literal hợp lệ.
- `System.out.println(token);` là câu lệnh Java hợp lệ.
- `;` là empty statement hợp lệ.
- Các dòng `@start`, `@end` và `@replace` là comment nên không ảnh hưởng đến cú pháp Java.

### 8.2. File Javadoc tham chiếu snippet

File `src/demo/ReplaceDoc.java`:

~~~java
package demo;

/**
 * Ví dụ về cách trình bày rút gọn mà vẫn giữ source kiểm tra được:
 *
 * {@snippet file="CompileReadyExample.java" region="main"}
 */
public final class ReplaceDoc {
}
~~~

Javadoc lấy region `main` trong file external, rồi áp dụng các markup comment `@replace` bên trong vùng.

Đầu ra hiển thị dự kiến:

~~~java
String endpoint = "https://api.example.test";
String token = ...;
System.out.println(endpoint);
System.out.println("done");
~~~

| File nguồn external | Snippet HTML |
| --- | --- |
| `String token = "placeholder";` | `String token = ...;` |
| `System.out.println(token);` | Dòng bị xóa. |
| `;` | `System.out.println("done");` |

File external vẫn là mã Java hợp lệ. Đầu ra HTML là ví dụ rút gọn, có thể không còn biên dịch được do dấu ba chấm thay cho literal. Đó là hành vi mong muốn khi người viết muốn kiểm tra source thật nhưng trình bày hình thức đơn giản hơn cho người đọc.

## 9. Kiểm chứng bằng `javac` và `javadoc`

Hai công cụ kiểm tra hai kết quả khác nhau:

- `javac` kiểm tra **file nguồn external** còn biên dịch được không.
- `javadoc` kiểm tra **markup và bản hiển thị** có được tạo đúng không.

Từ thư mục gốc có `src`, chạy lệnh biên dịch file external:

~~~bash
javac -d out src/demo/snippet-files/CompileReadyExample.java
~~~

Nếu lệnh thành công, source external được chấp nhận bởi compiler. Sau đó sinh tài liệu:

~~~bash
javadoc -d docs -sourcepath src demo
~~~

Mở `docs/demo/ReplaceDoc.html` và kiểm tra:

1. `"placeholder"` đã được thay bằng `...`.
2. Dòng `System.out.println(token);` không còn trong snippet.
3. Empty statement `;` được thay bằng `System.out.println("done");`.
4. Các marker `@start`, `@end` và `@replace` không xuất hiện trong mã hiển thị.
5. File external trong `src/demo/snippet-files` vẫn giữ nội dung gốc.

Nếu dùng inline snippet, phần mã nằm bên trong documentation comment nên `javac` không biên dịch phần nội dung đó như một compilation unit riêng. Khi cần xác nhận mã ví dụ có thể biên dịch, hãy lưu nó thành external source file hoặc tạo fixture riêng để compiler kiểm tra.

## 10. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Viết `@replace substring="..."` nhưng quên `replacement`. | Không có văn bản thay thế để áp dụng. | Thêm `replacement="..."` hoặc replacement rỗng nếu muốn xóa. |
| Dùng `substring` khi muốn chọn nhiều dạng văn bản khác nhau. | Selector chỉ tìm chuỗi nguyên văn. | Dùng `regex` nếu các giá trị có chung mẫu. |
| Dùng `regex` nhưng tham chiếu capture group không tồn tại. | `$2` yêu cầu regex có group thứ hai. | Kiểm tra ngoặc capture và chỉ số group. |
| Nghĩ `replacement="$1"` là ký tự literal `$1`. | `$1` được hiểu là nội dung capture group thứ nhất. | Dùng quy tắc escape replacement của Java regex khi cần in dấu dollar theo nghĩa literal. |
| Nghĩ `@replace` chỉ thay lần xuất hiện đầu tiên. | `substring` và `regex` áp dụng cho từng lần khớp trong scope. | Kiểm tra tất cả lần xuất hiện trong dòng/region. |
| Không chỉ định selector và vô tình thay cả dòng. | Không có `substring`/`regex` thì toàn bộ scope bị thay. | Thêm selector nếu chỉ muốn thay một phần. |
| Region thiếu marker kết thúc. | Phạm vi không được đóng theo tên hoặc thứ tự tương ứng. | Bổ sung `@end` hoặc `@end region="..."`. |
| Dùng dấu ba chấm trực tiếp trong source Java. | `...` không phải placeholder Java hợp lệ trong mọi vị trí. | Giữ literal hoặc no-op hợp lệ trong source rồi thay bằng `@replace`. |
| Nghĩ output sau replace phải biên dịch. | Javadoc có thể cố ý trình bày dạng mã không hoàn chỉnh. | Biên dịch file source gốc và kiểm tra riêng HTML. |
| Dùng `@replace` để che mật khẩu hoặc token. | File nguồn không bị thay đổi; giá trị gốc vẫn tồn tại. | Không đưa bí mật vào source hoặc snippet ngay từ đầu. |
| Nhầm `@replace` với `String.replaceAll` trong chương trình. | Một cái là markup xử lý lúc sinh tài liệu, một cái là API runtime. | Dùng `@replace` cho presentation; dùng API String/Matcher cho xử lý dữ liệu thực thi. |

## 11. Bài tập tự đánh giá

### Bài 1 — Thay placeholder

Cho dòng:

~~~java
String name = "placeholder";
~~~

Muốn hiển thị `String name = ...;` nhưng giữ source hợp lệ, viết markup thế nào?

**Đáp án:**

~~~java
String name = "placeholder"; // @replace substring='"placeholder"' replacement="..."
~~~

### Bài 2 — Dùng capture group

Cho:

~~~java
String version = "release-18";
~~~

Muốn bỏ tiền tố `release-` và giữ số phiên bản, dùng:

~~~java
String version = "release-18"; // @replace regex='release-([0-9]+)' replacement="$1"
~~~

Kết quả hiển thị là `String version = "18";`.

### Bài 3 — Xóa một dòng khỏi bản hiển thị

~~~java
System.out.println("trace");
~~~

**Đáp án:**

~~~java
System.out.println("trace"); // @replace replacement=""
~~~

Không có selector nên toàn bộ dòng được thay bằng chuỗi rỗng. Dòng lệnh vẫn tồn tại trong source.

### Bài 4 — Chèn câu lệnh bằng no-op

Muốn source có empty statement nhưng tài liệu hiển thị câu lệnh in:

~~~java
; // @replace substring=";" replacement='System.out.println("ready");'
~~~

Source biên dịch vì `;` là empty statement; Javadoc hiển thị câu lệnh thay thế.

### Bài 5 — Phân biệt hai lần kiểm chứng

Một external snippet có source hợp lệ nhưng Javadoc thay literal bằng `...`. Compiler có thể thành công trong khi HTML không còn biên dịch được không?

**Đáp án:** Có. `javac` kiểm tra file nguồn gốc. `javadoc` tạo một bản trình bày đã được thay thế. Hai kết quả phục vụ hai mục tiêu khác nhau.

## Tổng kết

- `@replace` thay đổi **văn bản hiển thị** trong snippet, không sửa file nguồn và không thay đổi hành vi runtime.
- `substring` chọn chuỗi nguyên văn; `regex` chọn đoạn khớp mẫu; `region` mở rộng phạm vi qua nhiều dòng.
- Không có `substring`/`regex` thì toàn bộ dòng hoặc region được thay.
- Replacement rỗng dùng để xóa; no-op placeholder như `;` hoặc `//` có thể dùng để chèn văn bản vào đầu ra.
- Regex replacement hỗ trợ capture group như `$1`, theo quy tắc `String.replaceAll`.
- External snippet có thể được lưu như source file để `javac` kiểm tra, trong khi Javadoc trình bày phiên bản rút gọn không nhất thiết biên dịch được.
- Không dùng `@replace` để che dữ liệu bí mật: source gốc vẫn được giữ nguyên.
- Luôn kiểm tra cả source bằng compiler và HTML bằng Javadoc khi hai mục tiêu đều quan trọng.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Documentation Comment Specification, JDK 27, mục Modifying the displayed text](https://download.java.net/java/early_access/jdk27/docs/specs/javadoc/doc-comment-spec.html#snippet): thuộc tính `@replace`, phạm vi dòng/region, selector và replacement.
2. [Oracle — JavaDoc Guide: Snippets, JDK 26, mục Modifying Text](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): ví dụ placeholder hợp lệ được thay bằng dấu ba chấm trong đầu ra.
3. [Oracle — Class String, Java SE 26 API, `replaceAll`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#replaceAll(java.lang.String,java.lang.String)): quy tắc thay chuỗi theo regex và replacement group.
4. [Oracle — Class Matcher, Java SE 26 API, `replaceAll`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Matcher.html#replaceAll(java.lang.String)): quy tắc tham chiếu capture group, dấu dollar và backslash trong replacement.
5. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): tính năng `{@snippet}` được đưa vào Java 18.
