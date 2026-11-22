# Doclint, DocTree và chất lượng Javadoc trong Java

Javadoc không chỉ là phần mô tả để người đọc mở trên website API. Khi được viết và kiểm tra đúng cách, nó trở thành **hợp đồng dễ đọc của thư viện**: người dùng hiểu một method làm gì, nhận đầu vào nào, trả về điều gì, có thể ném ngoại lệ nào và những điều kiện nào phải được giữ. Trong JDK hiện đại, hai công cụ quan trọng cho công việc này là **DocLint** và **DocTree**:

- **DocLint** kiểm tra các lỗi phổ biến trong documentation comments: cú pháp Javadoc, tham chiếu đến API, thẻ bị thiếu, cấu trúc HTML và một số vấn đề accessibility.
- **DocTree API** biểu diễn nội dung comment thành **cây cú pháp (AST)** để công cụ phân tích thẻ, liên kết, HTML và ví dụ mã theo cấu trúc thay vì tự tách chuỗi bằng regex.
- **Javadoc tool** dùng doclet để đọc source và tạo tài liệu. **StandardDoclet** là doclet mặc định, tạo HTML; custom Doclet/Taglet cho phép xây dựng quy trình xuất hoặc mở rộng nội dung riêng.

Đây là các công cụ tiếp tục được duy trì. API DocTree có từ Java 8; Doclet API hiện đại có từ Java 9; `{@snippet}` có từ JDK 18; Markdown documentation comments với `///` được bổ sung ở JDK 23. Bài này tập trung vào khả năng còn áp dụng trong JDK hiện đại, đồng thời phân biệt phần nào có thể chạy trên Java 8 và phần nào cần JDK mới hơn.

## 1. Javadoc nằm ở đâu trong quy trình phát triển?

Javadoc là **công cụ của JDK**, không phải cơ chế chạy trong JVM mỗi khi ứng dụng gọi method. Nó đọc source code và documentation comments, phân tích cấu trúc chương trình, rồi tạo HTML hoặc đầu ra khác thông qua doclet.

~~~text
Java source
  |
  +-- declarations: class, method, field, package, module
  |
  +-- documentation comments: /** ... */ hoặc /// ...
             |
             v
       Javadoc tool
             |
             +--> DocLint: kiểm tra lỗi phổ biến
             |
             +--> DocTree / language model: cấu trúc để phân tích
             |
             v
       Doclet (mặc định: StandardDoclet)
             |
             v
       HTML API documentation
~~~

Điều này tạo ra ba loại kiểm tra khác nhau:

1. **Biên dịch Java:** cú pháp và kiểu của chương trình có hợp lệ không?
2. **Kiểm tra documentation:** comment có đúng cú pháp, thẻ và tham chiếu có hợp lệ không?
3. **Đánh giá chất lượng nội dung:** người dùng có hiểu hợp đồng API và dùng đúng được không?

DocLint hỗ trợ mạnh bước 2. Nó không chứng minh bước 3 và cũng không thay thế compiler cho mã nguồn.

### 1.1. Javadoc comment khác comment thông thường

~~~java
// Comment dành cho người đọc source; Javadoc không xem đây là tài liệu API.

/* Comment nhiều dòng thông thường; không phải Javadoc comment. */

/**
 * Documentation comment gắn với declaration ngay bên dưới.
 */
public final class AccountService {
}
~~~

Traditional Javadoc comment bắt đầu bằng `/**` và phải đặt ngay trước declaration mà nó mô tả. Nếu comment bị ngăn cách bởi một declaration khác hoặc đặt sai vị trí, tool có thể không gắn nó vào API mong muốn.

Javadoc nhận diện comment cho module, package, class, interface, constructor, method, annotation element, enum member và field. Một declaration chỉ có một documentation comment được nhận diện; nếu có nhiều comment liên tiếp, comment gần declaration nhất được dùng.

### 1.2. Tài liệu cấp package và module

Với package, cách hiện hành là dùng `package-info.java`:

~~~java
/**
 * Provides services for account operations.
 *
 * <p>The package exposes the public service contract.
 */
package com.example.account;
~~~

`package.html` chỉ còn được hỗ trợ vì tương thích lịch sử; với dự án mới nên dùng `package-info.java`.

Với module, có thể đặt documentation comment trong `module-info.java`:

~~~java
/**
 * Provides the public account API.
 */
module com.example.account {
    exports com.example.account;
}
~~~

Tài liệu bổ sung cũng có thể đặt trong thư mục `doc-files` của package hoặc module. JDK hiện đại hỗ trợ tài liệu HTML và Markdown trong cấu trúc này.

## 2. DocLint kiểm tra điều gì?

DocLint là bộ kiểm tra tích hợp với Javadoc và javac. Nó báo lỗi hoặc cảnh báo trong documentation comments, đặc biệt những vấn đề có thể làm liên kết sai, tạo HTML không hợp lệ hoặc khiến tài liệu thiếu thông tin quan trọng.

Trong JDK hiện đại, các nhóm kiểm tra chính gồm:

| Nhóm | Kiểm tra | Ví dụ lỗi |
| --- | --- | --- |
| `accessibility` | Vấn đề accessibility phổ biến trong HTML | Ảnh thiếu `alt`, bảng thiếu caption phù hợp |
| `html` | Cấu trúc HTML sai hoặc thiếu thẻ đóng | Đặt block element trong inline element, quên `</p>` |
| `missing` | Thiếu documentation comments hoặc thẻ cần thiết | Method thiếu `@param`, `@return` hoặc mô tả |
| `reference` | Tham chiếu API trong Javadoc không hợp lệ | `{@link}` không tìm thấy method, `@param` sai tên |
| `syntax` | Cú pháp Javadoc sai | Tag không hợp lệ, dấu `<`, `>` hoặc `&` không được escape đúng |

### 2.1. DocLint được bật mặc định ở đâu?

Cần phân biệt hai lệnh:

- **`javadoc`:** DocLint được bật mặc định trong Javadoc tool hiện đại. Có thể chỉ định rõ nhóm bằng `-Xdoclint:...` hoặc tắt bằng `-Xdoclint:none`.
- **`javac`:** DocLint không được bật mặc định. Muốn kiểm tra documentation comments trong bước compile, phải thêm `-Xdoclint` hoặc `-Xdoclint:all`.

Vì vậy, việc build source bằng `javac` thành công **không chứng minh** Javadoc hợp lệ. Ngược lại, Javadoc chạy thành công cũng không chứng minh code example trong comment đã được compile và test.

### 2.2. Chạy các nhóm kiểm tra tường minh

~~~bash
javadoc -Xdoclint:all -d build/docs src/main/java/com/example/ExampleApi.java
~~~

`-Xdoclint:all` yêu cầu tất cả nhóm kiểm tra. Có thể chọn một số nhóm:

~~~bash
javadoc -Xdoclint:html,syntax,reference -d build/docs src/main/java/com/example/ExampleApi.java
~~~

Hoặc chạy kiểm tra khi compile:

~~~bash
javac -Xdoclint:all -d build/classes src/main/java/com/example/ExampleApi.java
~~~

Với dự án public API, nên giữ kiểm tra documentation trong CI thay vì chỉ chạy thủ công trước khi release.

### 2.3. Biến warning thành lỗi trong CI

Javadoc có tùy chọn `-Werror` để build thất bại khi có warning:

~~~bash
javadoc -Xdoclint:all -Werror -d build/docs src/main/java/com/example/ExampleApi.java
~~~

Trong dự án nhiều package:

~~~bash
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src/main/java -subpackages com.example
~~~

**Không bật `-Werror` một cách mù quáng trên codebase cũ** nếu chưa xem warning hiện có. Hãy sửa warning thật, xác định package nào có legacy docs cần xử lý theo lộ trình, rồi đặt ngưỡng CI rõ. Đừng tắt toàn bộ DocLint chỉ để build xanh.

### 2.4. Phạm vi declaration được kiểm tra

Javadoc chỉ xử lý các module/package/type/member nằm trong tập đầu vào và phạm vi visibility được chọn. Các tùy chọn `-public`, `-protected`, `-package`, `-private` ảnh hưởng nội dung được đưa vào tài liệu. Khi kiểm tra API công khai, cần bảo đảm đúng package và visibility được đưa vào lệnh build.

Trong javac, `-Xdoclint:all/private` có thể mở rộng kiểm tra đến private declarations; mức truy cập mặc định của javac DocLint là private. Vì vậy một constructor private không có comment cũng có thể tạo warning khi bật đầy đủ.

### 2.5. Giới hạn của DocLint

DocLint không cố sửa comment và không phải một HTML validator đầy đủ. Nó phát hiện một tập lỗi phổ biến trong ngữ cảnh Javadoc; nó không bảo đảm mọi HTML, CSS, accessibility, link ngoài hoặc bản dịch đều hoàn hảo.

Một quy trình tài liệu chất lượng có thể cần thêm:
- Kiểm tra link ngoài và link tới tài liệu dependency.
- HTML validator hoặc accessibility checker phù hợp.
- Review nội dung API bởi người hiểu domain.
- Kiểm tra code snippet bằng compiler/test.
- Review generated HTML sau khi nâng JDK.

## 3. Ví dụ lỗi DocLint thường gặp

### 3.1. Thiếu @param hoặc @return

~~~java
/**
 * Calculates the total amount.
 *
 * @param quantity number of items
 */
public static long total(long quantity) {
    return quantity * 100L;
}
~~~

Method trả về `long` nhưng thiếu `@return`. Nhóm `missing` có thể cảnh báo.

Cách viết đầy đủ:

~~~java
/**
 * Calculates the total amount for the requested quantity.
 *
 * @param quantity number of items; must not be negative
 * @return the total amount in minor currency units
 * @throws IllegalArgumentException if quantity is negative
 */
public static long total(long quantity) {
    if (quantity < 0) {
        throw new IllegalArgumentException("quantity must be non-negative");
    }
    return quantity * 100L;
}
~~~

Mô tả `@param` nên nói ý nghĩa, đơn vị và điều kiện hợp lệ. `@return` nên nói giá trị trả về có nghĩa gì. `@throws` nên nói điều kiện thực tế khiến exception xuất hiện.

### 3.2. Tham chiếu sai tên method hoặc parameter

~~~java
/**
 * Returns a display name.
 *
 * @param userName input name
 * @return the display name
 * @see #normalize(String)
 */
public static String displayName(String name) {
    return name.trim();
}
~~~

Ở đây `@param userName` không khớp parameter `name`; `#normalize(String)` có thể không tồn tại. Nhóm `reference` giúp phát hiện những lỗi này.

### 3.3. HTML thiếu cấu trúc hoặc không hợp lệ

~~~java
/**
 * <p>Returns the result.
 * <b>Important</p>
 */
public String result() {
    return "ok";
}
~~~

Đoạn trên mở `<b>` nhưng đóng bằng `</p>`; cấu trúc HTML không cân bằng. Cần dùng HTML5 hợp lệ và đóng đúng các element yêu cầu end tag.

### 3.4. Dấu ngoặc nhọn trong generic type

~~~java
/**
 * Returns a List<String> of names.
 */
public List<String> names() {
    return List.of();
}
~~~

Trong traditional Javadoc, `<String>` có thể bị hiểu là HTML tag. Dùng `{@code}` hoặc escape HTML:

~~~java
/**
 * Returns a {@code List<String>} of names.
 */
public List<String> names() {
    return List.of();
}
~~~

`{@code}` phù hợp với tên kiểu, biểu thức và code ngắn. Không nên biến toàn bộ đoạn giải thích thành HTML entity nếu inline tag đã diễn đạt đúng ý.

### 3.5. Không dùng suppression để che lỗi thiết kế

Có thể dùng `@SuppressWarnings("doclint:missing")` hoặc nhóm cụ thể khi một trường hợp thực sự không thể tài liệu hóa theo quy tắc chung. Nhưng suppression phải có lý do rõ và phạm vi nhỏ.

Không đặt `@SuppressWarnings("doclint")` trên class lớn chỉ để bỏ mọi warning. Cách đó làm mất tín hiệu về link hỏng, parameter sai và HTML lỗi trong các member bên trong.

## 4. Viết Javadoc có chất lượng: nội dung quan trọng hơn số lượng tag

Một comment tốt trả lời các câu hỏi mà người dùng API cần biết: API giải quyết vấn đề gì, input có ý nghĩa gì, đơn vị nào, có thể null không, method trả về gì, điều kiện nào làm method ném exception, có side effect/I/O/blocking hay thay đổi trạng thái không, và có ví dụ sử dụng an toàn không.

### 4.1. Câu đầu là summary sentence

StandardDoclet thường dùng câu đầu tiên của phần mô tả làm summary trong trang API và bảng tổng hợp. Câu đầu nên ngắn gọn nhưng đủ ý, nói rõ declaration làm gì.

~~~java
/**
 * Returns the account balance in minor currency units.
 *
 * <p>The value is read from the current transaction snapshot.
 */
public long balance() {
    return 0L;
}
~~~

Tránh mở đầu bằng câu chung chung như “This method is used to...” nếu có thể nói thẳng hành vi. Từ JDK 10, `{@summary ...}` cho phép chỉ rõ đoạn summary thay cho quy tắc lấy câu đầu.

### 4.2. Viết @param theo domain

Không chỉ lặp lại tên biến:

~~~java
@param timeout timeout
~~~

Hãy nêu đơn vị và giới hạn:

~~~java
@param timeout maximum wait time in milliseconds; must be non-negative
~~~

Nếu giá trị là phần trăm, bytes, epoch milliseconds, số tiền theo minor units hoặc một ID có namespace, cần nói rõ.

### 4.3. Viết @return theo ngữ nghĩa

Không chỉ viết “the result”. Nên nêu giá trị có thể null hay không, đơn vị đo, thứ tự phần tử trong collection, collection mutable hay immutable nếu đó là hợp đồng, sentinel value có nghĩa gì và kết quả có phải snapshot hay live view.

~~~java
/**
 * Returns the users matching the query.
 *
 * @return an immutable list ordered by creation time ascending;
 *         the list is empty when no user matches
 */
public List<User> search(String query) {
    return List.of();
}
~~~

### 4.4. Viết @throws theo điều kiện

`@throws IllegalArgumentException` không nên chỉ ghi “if invalid”. Nêu input hoặc trạng thái nào bị xem là invalid.

~~~java
/**
 * Parses an account identifier.
 *
 * @param value textual identifier
 * @return parsed identifier
 * @throws IllegalArgumentException if value is blank or has an invalid format
 */
public AccountId parse(String value) {
    return AccountId.of(value);
}
~~~

Tài liệu phải khớp implementation và contract thực tế. Không liệt kê exception chỉ vì một method gọi bên trong có thể ném; hãy mô tả exception mà caller có thể quan sát và cần xử lý.

### 4.5. Dùng @deprecated cùng annotation

Với API không còn được khuyến nghị, dùng annotation `@Deprecated` và tag `@deprecated` để giải thích lý do và hướng thay thế:

~~~java
/**
 * Reads the legacy account code.
 *
 * @deprecated Use {@link #accountId()} instead.
 */
@Deprecated(since = "2.4", forRemoval = false)
public String legacyCode() {
    return accountId().toString();
}
~~~

Tag nên nói API bị deprecated vì sao và chuyển sang API nào. Nếu có thời điểm dự kiến removal hoặc thay đổi tương thích, hãy ghi rõ theo chính sách versioning của dự án.

### 4.6. @inheritDoc cho method override

Khi override một method đã có contract tốt, `{@inheritDoc}` có thể kế thừa mô tả từ supertype:

~~~java
/**
 * {@inheritDoc}
 *
 * <p>This implementation uses the local cache before querying storage.
 */
@Override
public User find(UserId id) {
    return cache.find(id);
}
~~~

Không dùng `{@inheritDoc}` để che việc method con có thêm parameter, exception hoặc behavior khác mà contract cha không mô tả.

### 4.7. Liên kết API đúng cách

- `{@link Type#method(Type)}`: link inline, thường hiển thị kiểu code.
- `{@linkplain Type#method(Type) readable label}`: link với nhãn văn bản thông thường.
- `@see`: tạo mục tham khảo.
- `{@code ...}`: hiển thị code literal.
- `{@literal ...}`: hiển thị text literal, không diễn giải HTML/Javadoc tag.

Nên dùng reference có kiểu và chữ ký rõ ràng để tránh link trỏ nhầm overload. Khi tạo tài liệu cho nhiều module hoặc dependency ngoài, cấu hình external Javadoc links tương ứng version để link được resolve.

## 5. HTML, accessibility và cấu trúc trang

Javadoc hiện đại sinh HTML5. HTML trong documentation comments cần hợp lệ và phù hợp vị trí được render.

Không đặt block elements như `<p>`, `<div>`, `<ul>` bên trong inline elements như `<code>`, `<span>`, `<b>` theo cách làm hỏng cấu trúc. Dùng `<code>` cho đoạn ngắn hoặc `{@code}` để an toàn hơn.

~~~java
/**
 * Supported account states:
 * <ul>
 *   <li>ACTIVE — account can be used.</li>
 *   <li>LOCKED — authentication is blocked.</li>
 *   <li>CLOSED — account is no longer available.</li>
 * </ul>
 */
public enum AccountState {
    ACTIVE, LOCKED, CLOSED
}
~~~

Nếu thêm hình ảnh trong Javadoc, cung cấp `alt` text có ý nghĩa. Tài nguyên có thể được đặt trong `doc-files` theo package/module. Với bảng, cung cấp caption hoặc cấu trúc tiêu đề rõ ràng để người dùng công nghệ hỗ trợ có thể hiểu nội dung.

## 6. Markdown documentation comments từ JDK 23

JDK 23 bổ sung khả năng viết Javadoc comment bằng Markdown thông qua các dòng liên tiếp bắt đầu bằng `///`:

~~~java
/// Returns the total amount.
///
/// The method uses integer arithmetic and returns minor units.
///
/// @param quantity number of items
/// @return the total in minor currency units
public long total(long quantity) {
    return quantity * 100L;
}
~~~

StandardDoclet hỗ trợ CommonMark cùng Javadoc tags và links. Có thể dùng Markdown headings, lists, tables, fenced code blocks và inline formatting.

**Giới hạn tương thích:** `///` documentation comments là tính năng JDK 23+. Nếu thư viện vẫn build bằng JDK 8, 11, 17 hoặc 21, hãy tiếp tục dùng `/** ... */` cho source compatibility hoặc nâng JDK toolchain trước khi chuyển cú pháp. Đừng nhầm việc code target một Java release với phiên bản Javadoc tool dùng để xử lý source.

Để tạo dòng trống trong Markdown Javadoc comment, dòng đó cũng phải bắt đầu bằng `///`:

~~~java
/// First paragraph.
///
/// Second paragraph.
public void execute() {
}
~~~

Một dòng trắng hoàn toàn không có `///` có thể kết thúc documentation comment. Markdown comments vẫn có thể dùng HTML khi cần và các inline/block tags của Javadoc.

## 7. Code snippets với {@snippet}

`{@snippet}` được bổ sung từ JDK 18 để đưa code example vào tài liệu theo cách có cấu trúc. Nó hỗ trợ snippet inline, file bên ngoài hoặc dạng hybrid.

~~~java
/**
 * Creates a greeting.
 *
 * {@snippet :
 * String name = "Lan";
 * String message = "Hello, " + name;
 * System.out.println(message);
 * }
 *
 * @return a greeting for the supplied user
 */
public String greeting() {
    return "Hello";
}
~~~

Với ví dụ dài, có thể đặt file trong `snippet-files` cạnh source package hoặc cấu hình `--snippet-path`. Khi dùng external snippet, có thể chỉ định `file` hoặc `class` và chọn region cần hiển thị.

~~~java
/**
 * Example:
 *
 * {@snippet file="examples/AccountExample.java" region="create"}
 */
public final class AccountService {
}
~~~

Snippet hỗ trợ markup comments như `@highlight`, `@replace`, `@link`, `@start` và `@end` để đánh dấu vùng, nhấn mạnh dòng hoặc liên kết tới API.

**Javadoc không thay thế test code snippet.** Đừng mặc định mọi đoạn trong `{@snippet}` đã được compile hoặc chạy. Một số snippet cố ý có dấu `...`, import rút gọn hoặc phụ thuộc ngữ cảnh. Đối với ví dụ phải chạy được, đặt source trong thư mục có thể compile/test, dùng snippet external hoặc hybrid, chạy compiler/test trong CI và chạy Javadoc để kiểm tra syntax, links và generated HTML.

## 8. DocTree: biểu diễn Javadoc thành AST

Nếu công cụ chỉ cần tìm từ khóa đơn giản, đọc text có thể đủ. Nhưng khi cần biết một đoạn là `@param`, `{@link}`, HTML element, `@snippet` hay plain text, dùng **DocTree AST** đáng tin cậy hơn regex.

| API | Vai trò |
| --- | --- |
| `DocCommentTree` | Root node của documentation comment, chứa main description, first sentence và block tags |
| `DocTree` | Interface chung của node trong cây comment |
| `DocTree.Kind` | Loại node như `TEXT`, `LINK`, `PARAM`, `RETURN`, `THROWS`, `START_ELEMENT`, `SNIPPET` |
| `DocTrees` | Cầu nối tới comment tree của declaration và language model |
| `DocTreeScanner` | Visitor đi qua các node con của DocTree |
| `DocTreePathScanner` | Visitor có giữ path từ root đến node hiện tại |
| `DocTreePath` | Đường dẫn trong cây tài liệu, hữu ích khi cần phân giải reference |
| `DocTreeFactory` | Tạo các node DocTree |
| `DocSourcePositions` | Lấy vị trí source của node trong documentation comment |

`DocTree`, `DocTrees` và các API liên quan có từ Java 8. Trong JDK module system hiện đại, các package compiler tree nằm trong module `jdk.compiler`. Công cụ dùng API này cần chạy bằng JDK có compiler module; runtime image tối giản không nhất thiết có module đó.

Một comment như:

~~~java
/**
 * Returns {@link String#trim()} output.
 *
 * @param value input text
 * @return normalized text
 */
~~~

có thể được biểu diễn thành cây chứa text node, link node, param node và return node. Công cụ kiểm tra API có thể tìm tất cả `@param` nodes, đối chiếu tên parameter với declaration, kiểm tra link nodes hoặc thống kê `@throws` mà không phải tự parse dấu ngoặc nhọn và dấu HTML.

### 8.1. Lấy DocCommentTree bằng DocTrees

~~~java
JavacTask task = (JavacTask) compiler.getTask(...);
Iterable<? extends CompilationUnitTree> units = task.parse();

DocTrees docTrees = DocTrees.instance(task);

DocCommentTree comment =
        docTrees.getDocCommentTree(treePath);
~~~

`treePath` xác định declaration trong compilation unit. `DocTrees` cũng có overload nhận `Element` hoặc `FileObject`. Cách chọn phụ thuộc công cụ đang làm việc với syntax tree, language model hay file tài liệu độc lập.

### 8.2. Dùng visitor thay vì tự duyệt danh sách node

`DocTreeScanner` tự gọi visitor cho các node con theo cấu trúc. Nếu cần ngữ cảnh cha/con hoặc phân giải reference, `DocTreePathScanner` duy trì path tới node hiện tại. Đây là cách thích hợp để viết công cụ kiểm tra Javadoc coverage, báo cáo liên kết API hỏng, kiểm tra tag bắt buộc theo annotation, tạo chỉ mục API hoặc xuất metadata.

## 9. Chương trình Java hoàn chỉnh: DocTreeAudit

Chương trình `DocTreeAudit.java` dưới đây dùng compiler API để đọc source file, lấy documentation comments và duyệt cây DocTree. Nó:
1. Dùng `ToolProvider` lấy system Java compiler.
2. Tạo `JavacTask` và parse compilation unit.
3. Lấy `DocTrees` từ task.
4. Duyệt class và method bằng `TreePathScanner`.
5. Lấy `DocCommentTree` của từng declaration.
6. In loại block tags, tên parameter và reference trong `{@link}`.

Chương trình dùng API có từ Java 8 và đã được compile/run trên OpenJDK 24.

### 9.1. File ExampleApi.java

~~~java
/**
 * Small example API for demonstrating Javadoc analysis.
 *
 * <p>The method uses {@link String#trim()} before returning its result.
 *
 * @since 1.0
 */
public final class ExampleApi {
    private ExampleApi() {
    }

    /**
     * Returns the input without leading or trailing whitespace.
     *
     * @param value the non-null input text
     * @return the normalized text
     * @throws IllegalArgumentException if {@code value} is null
     * @see String#trim()
     */
    public static String normalize(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }
        return value.trim();
    }
}
~~~

### 9.2. File DocTreeAudit.java

~~~java
import com.sun.source.doctree.DocCommentTree;
import com.sun.source.doctree.DocTree;
import com.sun.source.doctree.LinkTree;
import com.sun.source.doctree.ParamTree;
import com.sun.source.util.DocTrees;
import com.sun.source.util.DocTreeScanner;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodTree;

import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class DocTreeAudit {
    private DocTreeAudit() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: DocTreeAudit <Java-source-file>");
        }

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A full JDK with the system compiler is required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager fileManager =
                     compiler.getStandardFileManager(
                             diagnostics, null, StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> files =
                    fileManager.getJavaFileObjects(new File(args[0]));

            JavacTask task = (JavacTask) compiler.getTask(
                    null,
                    fileManager,
                    diagnostics,
                    Arrays.asList("-proc:none"),
                    null,
                    files);

            Iterable<? extends CompilationUnitTree> units = task.parse();
            DocTrees docTrees = DocTrees.instance(task);

            for (CompilationUnitTree unit : units) {
                new TreePathScanner<Void, Void>() {
                    @Override
                    public Void visitClass(ClassTree node, Void unused) {
                        inspect(getCurrentPath(),
                                "type " + node.getSimpleName(), docTrees);
                        return super.visitClass(node, unused);
                    }

                    @Override
                    public Void visitMethod(MethodTree node, Void unused) {
                        if (node.getReturnType() != null) {
                            inspect(getCurrentPath(),
                                    "method " + node.getName(), docTrees);
                        }
                        return super.visitMethod(node, unused);
                    }
                }.scan(unit, null);
            }
        }
    }

    private static void inspect(
            TreePath path,
            String label,
            DocTrees docTrees) {

        DocCommentTree comment = docTrees.getDocCommentTree(path);
        if (comment == null) {
            System.out.println(label + ": missing");
            return;
        }

        System.out.println(label + ": present");
        for (DocTree tag : comment.getBlockTags()) {
            System.out.println("  blockTag=" + tag.getKind());
            if (tag instanceof ParamTree) {
                ParamTree param = (ParamTree) tag;
                System.out.println("  param=" + param.getName());
            }
        }

        new DocTreeScanner<Void, Void>() {
            @Override
            public Void visitLink(LinkTree link, Void unused) {
                System.out.println("  link=" + link.getReference());
                return super.visitLink(link, unused);
            }
        }.scan(comment, null);
    }
}
~~~

### 9.3. Biên dịch và chạy

Đặt hai file trong cùng thư mục:

~~~bash
javac -encoding UTF-8 DocTreeAudit.java ExampleApi.java
java DocTreeAudit ExampleApi.java
~~~

### 9.4. Đầu ra đã kiểm tra

~~~text
type ExampleApi: present
  blockTag=SINCE
  link=String#trim()
method normalize: present
  blockTag=PARAM
  param=value
  blockTag=RETURN
  blockTag=THROWS
  blockTag=SEE
~~~

Kết quả cho thấy công cụ đã đọc được comment cấp type và method, nhận diện đúng `@param`, `@return`, `@throws`, `@see` và `{@link}`. Nó in reference dạng cấu trúc; đoạn demo này **chưa resolve link tới Element** và chưa kiểm tra type compatibility. Muốn xác minh target, cần phân tích semantic context và dùng `DocTreePath` cùng `DocTrees.getElement(...)`.

### 9.5. Giới hạn của ví dụ

- Đây là tool phân tích comment, không phải custom Doclet.
- Nó chỉ parse source và duyệt declaration trong file đầu vào.
- Nó không compile business logic, chạy test hoặc bảo đảm mọi link ngoài đều hợp lệ.
- Nó không kiểm tra snippet có chạy hay không.
- Nếu cần kiểm tra toàn bộ module/project, phải mở rộng input, source path, module path và error reporting theo build system.

## 10. DocTree, Doclet và Taglet khác nhau thế nào?

| Thành phần | Vai trò | Dùng khi |
| --- | --- | --- |
| DocTree API | Cấu trúc AST của comment để đọc/phân tích | Viết linter, analyzer, coverage checker |
| Doclet API | Backend nhận chương trình và quyết định cách sinh tài liệu | Muốn xuất HTML tùy chỉnh, JSON, báo cáo hoặc format riêng |
| Taglet API | Xử lý một loại tag tùy chỉnh trong doclet | Muốn thêm tag như `@permission` hoặc `{@badge}` |

### 10.1. StandardDoclet

Nếu không chỉ định doclet, Javadoc dùng `StandardDoclet` để tạo HTML API docs. Nó hỗ trợ các Javadoc tags tiêu chuẩn và user-defined Taglets.

### 10.2. Custom Doclet API

Doclet API hiện đại nằm trong module `jdk.javadoc` và có từ JDK 9. Một implementation cần:
- Public no-argument constructor.
- `init(Locale, Reporter)`.
- `getSupportedOptions()`.
- `getSupportedSourceVersion()`.
- `run(DocletEnvironment)`.

Doclet nhận `DocletEnvironment` để truy cập các element được chọn cho tài liệu. Khi cần đọc comments theo cấu trúc, nó có thể dùng `DocTrees`; khi cần type/package/module information, dùng Language Model API.

Custom Doclet phù hợp khi StandardDoclet không đáp ứng format đầu ra. Nếu chỉ cần kiểm tra comment, viết DocTree-based analyzer hoặc chạy DocLint thường đơn giản hơn.

### 10.3. Taglet

Taglet mở rộng cách StandardDoclet render tag tùy chỉnh. Taglet inline phải trả flow content hợp lệ; block taglet thường tạo nội dung phù hợp với definition list. Taglet không thay thế toàn bộ quá trình sinh tài liệu.

Không nên tự xây một doclet mới chỉ để thêm một tag đơn giản. Chọn đúng mức mở rộng giúp công cụ ít phụ thuộc và dễ nâng JDK hơn.

## 11. Chất lượng Javadoc trong API thực tế

DocLint chỉ phát hiện một phần lỗi. Để tài liệu thực sự hữu ích, cần review các khía cạnh sau.

### 11.1. Contract và behavior

Mô tả input hợp lệ, output, nullability, đơn vị, side effects, exception conditions, thread safety, blocking, consistency và các giới hạn mà caller cần biết.

### 11.2. Compatibility và versioning

Dùng `@since` để ghi phiên bản API xuất hiện. Khi thay đổi contract, cập nhật docs cùng source. Khi deprecated, ghi rõ replacement và migration path.

Đừng ghi `@since Java 8` chỉ vì module được viết bằng Java 8 nếu method thực tế được bổ sung ở phiên bản thư viện khác. `@since` nói về lịch sử API của sản phẩm/thư viện.

### 11.3. Ví dụ code

Một ví dụ nên có imports và context đủ để hiểu, dùng API hiện hành, compile/test được nếu được quảng bá là runnable, không bỏ qua resource cleanup hoặc error handling quan trọng, không hard-code secret/path và có output đúng nếu đưa output.

### 11.4. Links và external references

Link tới method/class cụ thể khi nó giúp caller hiểu hợp đồng. Với tài liệu dependency, cấu hình external Javadoc links tương ứng version. Kiểm tra cả link nội bộ và link ngoài trong CI; DocLint không thể bảo đảm website bên ngoài luôn tồn tại.

### 11.5. Tính nhất quán giữa source và generated docs

Một số nội dung đến từ inherited docs, package docs, module docs, external snippet hoặc Taglet. Chỉ đọc source comment của một method chưa chắc thấy toàn bộ nội dung người dùng cuối nhìn thấy. Review generated HTML trong release.

## 12. Tích hợp DocLint vào CI

Một quy trình phù hợp cho thư viện Java có thể gồm:

1. Compile source với compiler warnings và DocLint theo policy.
2. Chạy Javadoc cho toàn bộ public API.
3. Dùng `-Xdoclint:all -Werror` để build fail khi có warning.
4. Compile/test snippet độc lập nếu chúng được cam kết chạy được.
5. Kiểm tra link ngoài, HTML và accessibility bằng công cụ phù hợp.
6. Lưu generated docs như build artifact hoặc publish cùng release.
7. Khi nâng JDK, xem thay đổi DocLint, HTML output và Markdown/snippet parsing.

### 12.1. Ví dụ lệnh cho project package

~~~bash
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src/main/java -subpackages com.example
~~~

Nếu source dùng module path hoặc nhiều dependency, thêm cấu hình `--module-path`, `--module` hoặc các option phù hợp theo cấu trúc project. Không dùng một lệnh rút gọn rồi cho rằng nó tự tìm mọi source/module trong repository.

### 12.2. javac và javadoc có vai trò bổ sung

~~~bash
javac -Xdoclint:all -Xlint:all -d build/classes @sources.txt
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src/main/java -subpackages com.example
~~~

`javac` DocLint disabled by default, vì vậy cần bật nếu muốn kiểm tra ở compile stage. Javadoc có DocLint enabled by default, nhưng nên dựa vào lệnh CI được ghi rõ và version JDK đã pin.

### 12.3. Maven và Gradle

Với Maven/Gradle, đặt Javadoc generation trong lifecycle task tương ứng và truyền options của StandardDoclet/DocLint qua cấu hình plugin. Không chỉ dựa vào IDE hiển thị warning vì CI và local IDE có thể dùng JDK khác nhau.

Build cần ghi nhận JDK dùng để chạy Javadoc, release/source level đang document, packages/module được đưa vào, DocLint flags và `-Werror`, external links và snippet paths, vị trí output và chính sách publish.

## 13. Phân biệt phiên bản công cụ

| Tính năng | Mốc phiên bản | Ghi chú |
| --- | --- | --- |
| Traditional `/** ... */` Javadoc comments | Từ các phiên bản Java đầu tiên | Vẫn hỗ trợ rộng rãi |
| DocTree/DocTrees compiler APIs | Java 8 | AST và utilities để đọc comment |
| Doclet API `jdk.javadoc.doclet` | JDK 9 | API hiện đại cho custom doclet |
| `@summary` | JDK 10 | Chỉ định summary rõ ràng |
| `{@snippet}` | JDK 18 | Inline/external/hybrid code snippets |
| Markdown documentation comments `///` | JDK 23 | Dùng với Javadoc tool tương ứng trở lên |

Nếu dự án cần source compatibility với Java 8, dùng traditional comments và toolchain tương thích. Nếu dùng `///` hoặc `{@snippet}`, hãy ghi rõ minimum JDK của **documentation build**, vì toolchain xử lý docs có thể cần mới hơn runtime target của thư viện.

## 14. Lỗi thường gặp khi làm Javadoc tooling

1. **Nhầm comment `//` với Javadoc.** Chỉ `/** ... */` hoặc Markdown documentation comments `///` được StandardDoclet nhận diện theo quy tắc tương ứng.
2. **Đặt comment sai vị trí.** Documentation comment phải gắn ngay trước declaration.
3. **Nghĩ compile thành công nghĩa là docs hợp lệ.** `javac` không bật DocLint mặc định.
4. **Tắt DocLint để bỏ warning.** Điều này có thể che link hỏng, tag thiếu và HTML sai.
5. **Nghĩ DocLint là HTML validator đầy đủ.** Nó chỉ kiểm tra một tập lỗi phổ biến.
6. **Dùng regex để parse Javadoc.** Nested inline tags, HTML, braces và block tags khiến regex dễ sai; dùng DocTree AST.
7. **Import nhầm `DocTreeScanner`.** Class này nằm trong `com.sun.source.util`, không phải `com.sun.source.doctree`.
8. **Nhầm DocTree với Doclet.** DocTree là AST của comment; Doclet là backend sinh tài liệu.
9. **Nhầm Taglet với Doclet.** Taglet xử lý một tag, Doclet kiểm soát output toàn bộ.
10. **Cho rằng `{@snippet}` tự compile code.** Snippet cần test bằng compiler/build task riêng khi yêu cầu runnable.
11. **Dùng Markdown `///` với toolchain Java cũ.** Tính năng này cần JDK 23+.
12. **Dùng `{@link}` sai overload.** Ghi đúng tên type và signature, sau đó chạy reference DocLint.
13. **Thiếu `@param <T>` cho generic type parameter.** Tài liệu type parameter khác parameter value.
14. **Ghi `@return` cho method void.** Dùng tag đúng declaration.
15. **Bỏ qua nullability và unit.** Người dùng không biết có thể truyền null hay số đo theo milliseconds/seconds.
16. **Ghi `@throws` không khớp implementation.** Tài liệu và behavior phải nhất quán.
17. **Dùng `{@inheritDoc}` cho API khác contract.** Phải bổ sung phần behavior mới hoặc khác.
18. **Không document deprecation migration.** Caller biết API deprecated nhưng không biết chuyển sang đâu.
19. **Dùng HTML heading sai cấp.** Generated page có thể bị rối cấu trúc/accessibility.
20. **Dùng Taglet trả block HTML trong vị trí inline.** Output có thể làm hỏng HTML.
21. **Không đóng gói `doc-files`/`snippet-files`.** Generated docs thiếu hình, ví dụ hoặc tài nguyên.
22. **Không kiểm tra generated HTML.** Source comment đúng chưa chắc output cuối dễ đọc hoặc link ngoài hoạt động.
23. **Dùng JDK khác nhau giữa local và CI.** DocLint, Markdown comment và snippet support có thể khác.
24. **Dùng API compiler trong runtime image thiếu `jdk.compiler`.** DocTree analyzer cần module compiler ở môi trường chạy tool.
25. **Gộp tất cả docs vào một comment quá dài.** Tách phần contract, examples và guide theo đúng phạm vi.
26. **Document implementation detail như contract.** Caller bị phụ thuộc vào behavior không được cam kết.
27. **Không review API khi behavior đổi.** Docs cũ trở thành thông tin sai dù DocLint vẫn pass.

## 15. Checklist chất lượng Javadoc

- [ ] Comment gắn đúng declaration và đúng loại comment?
- [ ] Summary sentence nói rõ API làm gì?
- [ ] Input, output, nullability, đơn vị và giới hạn đã rõ?
- [ ] `@param` khớp từng parameter và generic type parameter?
- [ ] `@return` phù hợp với kiểu trả về và nêu ngữ nghĩa?
- [ ] `@throws` khớp điều kiện lỗi có thể xảy ra?
- [ ] Side effects, thread safety, blocking và consistency được mô tả khi caller cần?
- [ ] `{@link}` trỏ đúng type/method/overload?
- [ ] Generic types và dấu `<`, `>` được bọc `{@code}` hoặc escape?
- [ ] HTML5 hợp lệ và element có cấu trúc đúng?
- [ ] Accessibility của ảnh/bảng/heading được xem xét?
- [ ] `@deprecated` đi cùng annotation và replacement rõ ràng?
- [ ] `@since` phản ánh version API thật?
- [ ] Override dùng `{@inheritDoc}` đúng ngữ cảnh?
- [ ] Snippet có đủ context và đã được test nếu được mô tả là runnable?
- [ ] Javadoc/DocLint chạy trong CI?
- [ ] Build dùng `-Xdoclint:all` và policy warning rõ?
- [ ] Có `-Werror` khi codebase đã sẵn sàng?
- [ ] Generated HTML và external links được kiểm tra?
- [ ] DocTree analyzer dùng AST thay vì regex?
- [ ] Tooling chỉ phụ thuộc API JDK được tài liệu hóa, không dùng internal `com.sun.tools.*`?
- [ ] JDK version hỗ trợ cú pháp Markdown/snippet được ghi rõ?
- [ ] Tài liệu được review lại mỗi khi API contract thay đổi?

**Ghi nhớ:** DocLint giúp phát hiện các lỗi phổ biến trong documentation comments; DocTree cho phép công cụ đọc comment như AST; Javadoc/StandardDoclet biến tài liệu thành HTML; Doclet và Taglet là các điểm mở rộng khi cần output hoặc tag riêng. Một build tốt nên chạy DocLint nghiêm ngặt trong CI, kiểm thử snippet bằng compiler/test riêng và review generated HTML. Javadoc có chất lượng khi mô tả đúng contract mà caller cần — không phải chỉ khi đủ số tag hoặc không còn warning.

## Tài liệu chính thức

- [Oracle JDK 26 — The javadoc Command: DocLint options, groups, -Werror](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html)
- [Oracle JDK 26 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html)
- [Oracle Java SE 26 — DocTree: common interface for documentation syntax tree nodes](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/doctree/DocTree.html)
- [Oracle Java SE 26 — DocCommentTree](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/doctree/DocCommentTree.html)
- [Oracle Java SE 26 — DocTrees: access to documentation comment syntax trees](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/util/DocTrees.html)
- [Oracle Java SE 26 — DocTreeScanner](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/util/DocTreeScanner.html)
- [Oracle Java SE 26 — DocTreePathScanner](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/util/DocTreePathScanner.html)
- [Oracle Java SE 26 — Doclet API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/Doclet.html)
- [Oracle Java SE 26 — StandardDoclet and user-defined Taglets](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/StandardDoclet.html)
- [Oracle JDK 26 — The javac Command: -Xdoclint and access scopes](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [JEP 467 — Markdown Documentation Comments, delivered in JDK 23](https://openjdk.org/jeps/467)
