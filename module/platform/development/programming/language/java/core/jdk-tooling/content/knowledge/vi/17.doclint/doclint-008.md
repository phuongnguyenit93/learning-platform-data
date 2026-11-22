# Sửa cảnh báo DocLint trong Javadoc

**DocLint** là bộ kiểm tra các vấn đề thường gặp trong documentation comment của Java. Nó giúp phát hiện comment thiếu, thẻ Javadoc sai, tham chiếu không tồn tại, HTML không hợp lệ ở mức phổ biến và vấn đề accessibility trước khi tài liệu API được phát hành.

DocLint không tự sửa comment. Nó đọc mã nguồn và báo vị trí có vấn đề; lập trình viên phải sửa nội dung hoặc cấu trúc comment rồi chạy lại công cụ. Một tài liệu không còn cảnh báo cú pháp vẫn cần được đọc lại để bảo đảm mô tả đúng hành vi API.

DocLint được tích hợp trong cả công cụ `javadoc` và `javac`, nhưng cách bật mặc định khác nhau: `javadoc` bật các kiểm tra DocLint theo mặc định cho những comment được đưa vào tài liệu sinh ra; `javac` chỉ chạy DocLint khi được yêu cầu bằng tùy chọn `-Xdoclint`. Vì vậy, nếu mục tiêu là kiểm tra tài liệu được phát hành, hãy chạy `javadoc`; nếu muốn phát hiện vấn đề ngay trong bước biên dịch, có thể bật DocLint cho `javac`.

## 1. Chạy DocLint và đọc kết quả

Với cấu trúc dự án:

```text
project/
├── src/
│   └── com/
│       └── example/
│           └── Calculator.java
└── docs/
```

Chạy Javadoc trên một tệp:

```sh
javadoc -d docs -Xdoclint:all src/com/example/Calculator.java
```

Hoặc quét các package bên dưới source root:

```sh
javadoc -d docs -sourcepath src -subpackages com.example -Xdoclint:all
```

Ý nghĩa:

- `-d docs` chọn thư mục chứa HTML được tạo.
- `-sourcepath src` chỉ định gốc mã nguồn.
- `-subpackages com.example` yêu cầu xử lý package và các package con.
- `-Xdoclint:all` bật tất cả nhóm kiểm tra DocLint.

Với JDK 17 trở lên, cũng có thể bật kiểm tra khi biên dịch:

```sh
javac -Xdoclint:all -d out src/com/example/Calculator.java
```

`javac` không bật DocLint mặc định. Nếu chỉ chạy `javac` mà không có `-Xdoclint`, việc biên dịch thành công không chứng minh Javadoc đã được kiểm tra.

Một chẩn đoán thường có dạng:

```text
Calculator.java:12: warning: no @return
    public static int add(int left, int right) {
                      ^
```

Đọc thông báo theo thứ tự:

1. Tên tệp và số dòng chỉ vị trí cần xem.
2. Loại cảnh báo hoặc lỗi cho biết nhóm vấn đề.
3. Dòng mã được in lại giúp xác định declaration hoặc comment liên quan.
4. Dấu mũ `^` chỉ vị trí mà công cụ phát hiện vấn đề.

Bắt đầu bằng lỗi cú pháp và tham chiếu sai vì chúng có thể làm tài liệu sinh ra không đúng. Sau đó xử lý comment hoặc tag còn thiếu và cuối cùng kiểm tra khả năng truy cập của HTML.

## 2. Năm nhóm kiểm tra của DocLint

DocLint tổ chức chẩn đoán thành năm nhóm:

| Nhóm | Nội dung | Ví dụ |
|---|---|---|
| `missing` | Comment hoặc tag tài liệu bị thiếu | Thiếu comment cho API, thiếu `@param` hoặc `@return` |
| `reference` | Tham chiếu đến phần tử Java không hợp lệ | `{@link}` sai tên lớp/method, `@param` sai tên tham số |
| `syntax` | Cú pháp Javadoc sai hoặc ký tự cần escape | Dùng `<`, `>`, `&` trực tiếp; tag không hợp lệ |
| `html` | Cấu trúc HTML có vấn đề | Thiếu thẻ đóng, lồng block element sai |
| `accessibility` | Vấn đề khả năng truy cập trong HTML | Ảnh thiếu `alt`, bảng thiếu caption hoặc cấu trúc tiêu đề phù hợp |

DocLint có thể báo warning hoặc error tùy mức độ nghiêm trọng. Ví dụ, thiếu mô tả thường là warning; tham chiếu sai, cú pháp sai hoặc HTML có khả năng tạo đầu ra không hợp lệ có thể là error.

DocLint không phải bộ xác thực HTML đầy đủ. Nó tập trung vào các lỗi phổ biến trong documentation comment; tài liệu được tạo vẫn nên được xem lại và kiểm tra trong trình duyệt hoặc bằng công cụ phù hợp.

## 3. Sửa cảnh báo missing: bổ sung comment và tag cần thiết

Nhóm `missing` thường phát hiện:

- Lớp hoặc thành viên cần tài liệu nhưng chưa có Javadoc comment.
- Method có tham số nhưng comment thiếu `@param`.
- Method có giá trị trả về nhưng comment thiếu `@return`.
- Tag mô tả generic type parameter chưa được ghi khi cần.

Một Javadoc comment bắt đầu bằng `/**` và kết thúc bằng `*/`. Comment bắt đầu bằng `/*` không phải documentation comment.

Ví dụ chưa đầy đủ:

```java
package com.example;

public class Calculator {
    public static int add(int left, int right) {
        return left + right;
    }
}
```

Phiên bản có tài liệu:

```java
package com.example;

/**
 * Provides basic integer calculations.
 */
public class Calculator {

    /**
     * Adds two integer values.
     *
     * @param left the first value
     * @param right the second value
     * @return the sum of the two values
     */
    public static int add(int left, int right) {
        return left + right;
    }
}
```

Mỗi tag cần mô tả đúng ý nghĩa:

- `@param left` phải trùng tên tham số trong khai báo.
- `@param right` phải trùng tên tham số còn lại.
- `@return` mô tả giá trị method thực sự trả về.
- Method `void` không cần `@return`.
- Constructor dùng `@param` nếu nhận tham số; constructor không có kiểu trả về.
- Với generic type parameter, dùng cú pháp `@param <T>`.

Ví dụ generic method:

```java
/**
 * Returns the supplied value without changing it.
 *
 * @param <T> the value type
 * @param value the value to return
 * @return the same value
 */
public static <T> T identity(T value) {
    return value;
}
```

Không thêm tag chỉ để làm biến mất warning. Phần mô tả cần giúp người dùng hiểu vai trò tham số, kết quả, giới hạn hoặc điều kiện của API.

## 4. Viết @return và @throws đúng hợp đồng

`@return` nên mô tả giá trị thực tế, gồm đơn vị, trạng thái hoặc trường hợp đặc biệt nếu cần.

Ví dụ:

```java
/**
 * Divides the dividend by the divisor using integer division.
 *
 * @param dividend the value to divide
 * @param divisor the value by which to divide; must not be zero
 * @return the integer quotient
 * @throws ArithmeticException if the divisor is zero
 */
public static int divide(int dividend, int divisor) {
    return dividend / divisor;
}
```

Với phép chia số nguyên, divisor bằng 0 gây `ArithmeticException`. Comment nêu đúng điều kiện phát sinh ngoại lệ, không chỉ ghi một câu chung chung như “throws an exception”.

`@throws` hoặc `@exception` dùng để mô tả exception mà người gọi cần biết. Tên exception phải tham chiếu được đến một kiểu hợp lệ. Ví dụ `@throws IOException` cần có kiểu `IOException` mà Javadoc phân giải được qua import hoặc tên đầy đủ.

Không ghi `@return` cho method `void`. Nếu method trả về boolean, mô tả rõ ý nghĩa của `true` và `false` thay vì chỉ viết “returns a boolean”.

Với method có nhiều trường hợp trả về, mô tả các nhánh quan trọng. Ví dụ, nếu trả về `null` khi không tìm thấy dữ liệu, hãy ghi rõ điều đó hoặc cân nhắc dùng `Optional<T>` nếu phù hợp với thiết kế API.

## 5. Sửa cảnh báo reference: kiểm tra link và tên tag

Nhóm `reference` phát hiện tham chiếu Javadoc không khớp với declaration Java. Các lỗi thường gặp:

- Tên lớp hoặc package bị viết sai.
- `{@link}` trỏ tới method không tồn tại.
- Chữ ký method trong link thiếu hoặc sai kiểu tham số.
- `@param` dùng tên không trùng tham số thật.
- `@throws` tham chiếu sai tên exception.
- `@see` chứa tên kiểu hoặc thành viên không thể phân giải.

Ví dụ sai:

```java
/**
 * Adds two values. See {@link #sum(int, int)}.
 *
 * @param first the first value
 * @param second the second value
 * @return the sum
 */
public static int add(int left, int right) {
    return left + right;
}
```

Ở đây declaration tên method là `add`, không phải `sum`; tên tham số là `left` và `right`, không phải `first` và `second`.

Sửa lại:

```java
/**
 * Adds two values. See {@link #add(int, int)}.
 *
 * @param left the first value
 * @param right the second value
 * @return the sum
 */
public static int add(int left, int right) {
    return left + right;
}
```

Một số cách viết link:

| Cú pháp | Công dụng |
|---|---|
| `{@link String}` | Liên kết đến kiểu `String` |
| `{@link java.util.List}` | Liên kết bằng tên kiểu đầy đủ |
| `{@link #add(int, int)}` | Liên kết đến method trong cùng lớp |
| `{@link #add(int, int) add values}` | Hiển thị nhãn tùy chỉnh |
| `{@linkplain #add(int, int)}` | Link hiển thị văn bản thường thay vì font code |
| `@see java.util.List` | Thêm tham chiếu trong phần See Also |

Khi link đến overload, ghi rõ danh sách tham số để Javadoc chọn đúng method. Với kiểu mảng, generic hoặc nested type, dùng cú pháp tham chiếu theo quy tắc Javadoc và kiểm tra bằng cách chạy lại công cụ thay vì đoán.

## 6. Sửa lỗi syntax: escape ký tự đặc biệt

Javadoc dùng HTML trong documentation comment. Các ký tự `<`, `>` và `&` có ý nghĩa đặc biệt trong HTML, vì vậy không nên viết chúng trực tiếp khi muốn hiển thị như văn bản.

Ví dụ sai:

```java
/**
 * Checks whether size < limit and value > 0.
 */
public boolean isValid(int size, int limit, int value) {
    return size < limit && value > 0;
}
```

Dùng inline tag `{@code}` để hiển thị biểu thức code:

```java
/**
 * Checks whether {@code size < limit} and {@code value > 0}.
 */
public boolean isValid(int size, int limit, int value) {
    return size < limit && value > 0;
}
```

Hoặc dùng HTML entity khi cần văn bản HTML:

| Ký tự muốn hiển thị | Entity |
|---|---|
| `<` | `&lt;` |
| `>` | `&gt;` |
| `&` | `&amp;` |
| Dấu nháy kép | `&quot;` |

Các inline tag hữu ích:

- `{@code ...}` hiển thị nội dung theo kiểu code.
- `{@literal ...}` hiển thị văn bản nguyên dạng mà không xử lý như HTML.
- `{@link ...}` tạo liên kết đến API.
- `{@linkplain ...}` tạo liên kết với nhãn văn bản thường.
- `{@value ...}` hiển thị giá trị constant field khi áp dụng.

Ví dụ:

```java
/**
 * Pass a value such as {@code List<String>}.
 * The literal text {@literal <T>} represents a type parameter.
 */
```

Không đặt một dấu ngoặc nhọn hoặc thẻ HTML chưa đóng trong comment rồi kỳ vọng DocLint tự sửa. Hãy dùng inline tag hoặc entity đúng mục đích.

## 7. Sửa lỗi HTML: đóng thẻ và lồng đúng cấu trúc

DocLint nhóm `html` kiểm tra các lỗi HTML phổ biến trong comment, ví dụ thẻ yêu cầu đóng nhưng bị bỏ quên hoặc block element được đặt bên trong inline element.

Ví dụ có cấu trúc sai:

```java
/**
 * Returns a value.
 * <b>
 *   <p>The result is positive.</p>
 * </b>
 */
```

`<p>` là block element; không nên đặt block element bên trong inline element như `<b>`.

Có thể viết:

```java
/**
 * Returns a value.
 *
 * <p><strong>The result is positive.</strong></p>
 */
```

Hoặc dùng inline tag khi chỉ cần nhấn mạnh một cụm ngắn:

```java
/**
 * Returns the {@code positive} result when the input is valid.
 */
```

Danh sách HTML cần đóng thẻ rõ ràng:

```java
/**
 * Supported modes:
 * <ul>
 *   <li>Fast mode</li>
 *   <li>Safe mode</li>
 * </ul>
 */
```

Với bảng, bảo đảm cấu trúc nhất quán:

```java
/**
 * <table>
 *   <caption>Supported status codes</caption>
 *   <thead>
 *     <tr><th scope="col">Code</th><th scope="col">Meaning</th></tr>
 *   </thead>
 *   <tbody>
 *     <tr><td>200</td><td>Success</td></tr>
 *     <tr><td>404</td><td>Not found</td></tr>
 *   </tbody>
 * </table>
 */
```

Không nên lồng các thẻ tùy ý. Hãy dùng HTML đơn giản, có cấu trúc rõ ràng và kiểm tra đầu ra bằng Javadoc sau mỗi lần sửa.

## 8. Sửa cảnh báo accessibility

Nhóm `accessibility` giúp phát hiện một số vấn đề làm tài liệu khó sử dụng với công nghệ hỗ trợ. Ví dụ:

- Ảnh thiếu thuộc tính `alt` mô tả nội dung.
- Bảng thiếu caption hoặc cấu trúc tiêu đề cột phù hợp.
- Nội dung chỉ phân biệt bằng hình ảnh nhưng không có mô tả văn bản.

Ví dụ ảnh chưa tốt:

```java
/**
 * <img src="architecture.png">
 */
```

Bổ sung mô tả:

```java
/**
 * <img src="architecture.png" alt="Diagram showing the service and repository layers">
 */
```

Thuộc tính `alt` nên mô tả thông tin mà ảnh truyền tải trong ngữ cảnh tài liệu. Nếu ảnh chỉ mang tính trang trí và không bổ sung nội dung, xử lý theo hướng dẫn accessibility phù hợp của HTML/doclet thay vì viết alt gây nhiễu.

Với bảng, dùng `<caption>` để mô tả mục đích và `<th>` cho tiêu đề cột. Thuộc tính `scope="col"` giúp xác định tiêu đề cột trong bảng dữ liệu đơn giản.

DocLint chỉ kiểm tra một số vấn đề phổ biến; nó không thay thế đánh giá accessibility đầy đủ. Hãy kiểm tra tài liệu được sinh bằng trình đọc màn hình hoặc công cụ kiểm tra phù hợp nếu accessibility là yêu cầu sản phẩm.

## 9. Ví dụ hoàn chỉnh: sửa một lớp có nhiều loại cảnh báo

Tạo tệp `src/com/example/Calculator.java`:

```java
package com.example;

/**
 * Provides basic integer calculations.
 *
 * <p>All operations return their results directly.</p>
 *
 * @since 1.0
 */
public final class Calculator {

    /** Prevents instantiation of this utility class. */
    private Calculator() {
    }

    /**
     * Adds two integer values.
     *
     * @param left the first value
     * @param right the second value
     * @return the sum of the two values
     * @see #divide(int, int)
     */
    public static int add(int left, int right) {
        return left + right;
    }

    /**
     * Divides two integer values using integer division.
     *
     * @param dividend the value to divide
     * @param divisor the value by which to divide
     * @return the integer quotient
     * @throws ArithmeticException if {@code divisor} is zero
     * @see #add(int, int)
     */
    public static int divide(int dividend, int divisor) {
        return dividend / divisor;
    }
}
```

Chạy Javadoc:

```sh
javadoc -d docs -Xdoclint:all src/com/example/Calculator.java
```

Nếu chạy thành công, thư mục `docs` chứa trang HTML cho lớp. Mở `docs/com/example/Calculator.html` để kiểm tra nội dung hiển thị, liên kết và định dạng.

Có thể biên dịch riêng mã nguồn:

```sh
javac -Xdoclint:all -d out src/com/example/Calculator.java
```

Hai lệnh có mục đích khác nhau: `javadoc` sinh tài liệu HTML; `javac` biên dịch Java thành class file. Cả hai có thể chạy DocLint khi được cấu hình phù hợp.

## 10. Kiểm tra package-info.java và module-info.java

Tài liệu không chỉ gắn với class và method. Có thể viết tài liệu cho package trong `package-info.java`:

```java
/**
 * Provides calculation utilities.
 *
 * <p>Types in this package operate on numeric values.</p>
 */
package com.example;
```

Với ứng dụng modular, có thể ghi tài liệu cho module trong `module-info.java`:

```java
/**
 * Provides the example calculation application.
 */
module com.example.app {
    exports com.example;
}
```

Khi chạy Javadoc, bảo đảm package/module nằm trong phạm vi nguồn được chọn. Nếu chỉ truyền một tệp nguồn, công cụ sẽ không tự quét mọi package khác trong dự án.

Để quét package và package con:

```sh
javadoc -d docs -sourcepath src -subpackages com.example -Xdoclint:all
```

## 11. Kiểm soát phạm vi DocLint

Các nhóm có thể được bật/tắt bằng tùy chọn:

| Lệnh | Ý nghĩa |
|---|---|
| `-Xdoclint` | Bật các kiểm tra được khuyến nghị |
| `-Xdoclint:all` | Bật tất cả nhóm |
| `-Xdoclint:none` | Tắt toàn bộ DocLint |
| `-Xdoclint:html` | Chỉ bật nhóm HTML |
| `-Xdoclint:reference,syntax` | Bật nhóm reference và syntax |
| `-Xdoclint:all,-missing` | Bật tất cả trừ nhóm missing |

Ví dụ chỉ kiểm tra HTML, syntax và accessibility:

```sh
javadoc -d docs -Xdoclint:html,syntax,accessibility src/com/example/Calculator.java
```

Có thể điều chỉnh mức visibility trong `javac`, ví dụ:

```sh
javac -Xdoclint:all/protected -d out src/com/example/Calculator.java
```

Tùy chọn này kiểm tra các declaration có visibility protected trở lên. Trong `javadoc`, phạm vi declaration được kiểm tra còn phụ thuộc các tùy chọn chọn nội dung tài liệu như `-public`, `-protected`, `-package` hoặc `-private`.

`-Xdoclint:none` chỉ tắt kiểm tra. Nó không sửa comment, không xác nhận HTML hợp lệ và không làm tham chiếu sai trở thành đúng. Không nên dùng tùy chọn này để che warning trong pipeline phát hành.

## 12. SuppressWarnings: chỉ dùng khi có lý do rõ ràng

DocLint nhận biết annotation `@SuppressWarnings` với giá trị `"doclint"` hoặc `"doclint:<group>"`.

Ví dụ chỉ suppress nhóm missing trên một declaration:

```java
@SuppressWarnings("doclint:missing")
public void legacyOperation() {
}
```

Có thể chỉ định nhiều nhóm:

```java
@SuppressWarnings({"doclint:missing", "doclint:html"})
public void legacyOperation() {
}
```

`@SuppressWarnings("doclint")` suppress mọi nhóm DocLint trong phạm vi declaration được áp dụng. Annotation ở declaration bao ngoài cũng có thể ảnh hưởng các declaration lồng bên trong theo quy tắc DocLint.

Chỉ suppress khi có lý do kỹ thuật cụ thể, chẳng hạn API tương thích cũ không thể bổ sung tài liệu mà không gây thay đổi ngoài phạm vi. Với API mới hoặc comment có thể sửa, hãy viết tài liệu chính xác thay vì suppress.

Annotation chỉ ẩn chẩn đoán. Nó không cải thiện nội dung, không sửa HTML và không bảo đảm tham chiếu hoạt động. Việc suppress cả error cũng có thể che lỗi làm tài liệu đầu ra sai.

## 13. Tích hợp kiểm tra vào build

Để tránh lỗi chỉ xuất hiện trước khi phát hành, hãy đưa việc sinh Javadoc vào quy trình build.

Với Maven, chạy goal Javadoc của project:

```sh
mvn javadoc:javadoc
```

Với Gradle:

```sh
./gradlew javadoc
```

Trên Windows, dùng:

```powershell
gradlew.bat javadoc
```

Các lệnh này phụ thuộc plugin và cấu hình build của dự án. Hãy kiểm tra log để xác nhận task thực sự chạy Javadoc và không bị bỏ qua do cấu hình profile hoặc module.

Trong CI, nên:

1. Chạy build/compile.
2. Chạy Javadoc với DocLint được bật.
3. Lưu log và artifact HTML để xem lại khi thất bại.
4. Đặt quy tắc xử lý warning phù hợp với chất lượng tài liệu của dự án.
5. Chạy lại sau khi sửa và xác nhận không còn lỗi mới.

Có thể dùng `-Werror` của Javadoc để biến warning thành lỗi trong pipeline khi muốn yêu cầu không còn warning. Trước khi bật, cần xử lý warning hiện có và xác nhận phiên bản JDK/Javadoc đang dùng hỗ trợ tùy chọn này.

## 14. Cách xử lý chẩn đoán hiệu quả

Khi có nhiều warning, hãy phân loại:

| Thông báo/vấn đề | Hướng xử lý |
|---|---|
| No comment | Thêm Javadoc comment có ý nghĩa cho declaration được phát hành |
| No @param | Bổ sung tag cho từng tham số, đúng tên và mô tả |
| No @return | Bổ sung mô tả giá trị trả về cho method non-void |
| Reference not found | Kiểm tra tên lớp, package, method và chữ ký trong link |
| Parameter name not found | So sánh tên sau `@param` với declaration |
| Invalid input for tag | Kiểm tra cú pháp tag, loại tag và nội dung |
| Unescaped angle bracket | Dùng `{@code}`, `{@literal}` hoặc HTML entity |
| Unclosed HTML element | Đóng thẻ và kiểm tra cấu trúc lồng |
| Block element inside inline element | Chuyển block ra ngoài hoặc dùng inline tag |
| Missing alt/caption | Bổ sung mô tả ảnh và caption/heading bảng phù hợp |

Sau mỗi nhóm sửa:

1. Chạy lại đúng lệnh Javadoc.
2. Xác nhận warning cũ đã biến mất.
3. Kiểm tra không phát sinh warning/error mới.
4. Mở HTML được tạo để xem nội dung hiển thị.
5. Đọc lại mô tả để bảo đảm không sai hợp đồng API.

## 15. Lỗi thường gặp khi sửa DocLint

| Lỗi xử lý | Vì sao chưa đúng | Cách làm tốt hơn |
|---|---|---|
| Thêm tag nhưng để mô tả rỗng | Warning có thể biến mất nhưng tài liệu không giúp người dùng | Mô tả ý nghĩa thực tế của tham số/kết quả |
| Copy tên tham số từ method khác | `@param` không khớp declaration hiện tại | Đối chiếu từng tên trong chữ ký |
| Đổi `{@link}` thành văn bản thường | Mất liên kết API và không sửa được nguyên nhân reference | Sửa đúng tên hoặc chữ ký tham chiếu |
| Escape toàn bộ HTML | Có thể làm mất định dạng mong muốn | Chỉ escape ký tự cần hiển thị; dùng tag HTML hợp lệ |
| Xóa tag HTML để hết lỗi | Nội dung hoặc cấu trúc tài liệu có thể mất | Sửa cặp thẻ và thứ tự lồng |
| Dùng `-Xdoclint:none` trong CI | Tắt toàn bộ kiểm tra, che lỗi mới | Giữ kiểm tra và sửa comment |
| Suppress trên cả lớp | Có thể ẩn lỗi ở nhiều method không liên quan | Sửa nội dung hoặc suppress hẹp khi có lý do |
| Chỉ xem log, không mở HTML | DocLint không kiểm tra mọi vấn đề trình bày | Mở trang HTML và đọc lại như người dùng API |
| Giả định DocLint là HTML validator đầy đủ | Một số lỗi hoặc vấn đề accessibility có thể nằm ngoài phạm vi | Dùng thêm công cụ kiểm tra HTML/accessibility khi cần |

## 16. Checklist trước khi hoàn tất

- [ ] Đã chạy `javadoc` với DocLint bật.
- [ ] Đã xử lý nhóm `missing` cho API thuộc phạm vi tài liệu.
- [ ] Các `@param` khớp tên tham số và mô tả đúng.
- [ ] Method non-void có `@return` phù hợp.
- [ ] `@throws` và `@see` tham chiếu đúng kiểu/API.
- [ ] Mọi `{@link}` trỏ đến declaration tồn tại.
- [ ] Ký tự `<`, `>` và `&` được escape hoặc đặt trong inline tag thích hợp.
- [ ] HTML có cấu trúc hợp lệ và thẻ cần thiết được đóng.
- [ ] Ảnh có alt phù hợp; bảng có caption và header rõ ràng.
- [ ] Không dùng suppress để che lỗi có thể sửa.
- [ ] Đã chạy lại Javadoc sau lần sửa cuối.
- [ ] Đã mở và đọc HTML được tạo.
- [ ] Build/CI kiểm tra tài liệu theo chính sách của dự án.

## 17. Tài liệu tham khảo

- Oracle JDK 21 — The `javadoc` Command và phần DocLint: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javadoc.html
- Oracle JDK — The `javac` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- JavaDoc Guide: https://docs.oracle.com/en/java/javase/21/javadoc/javadoc-guide.pdf

Sửa cảnh báo DocLint tốt nhất là sửa nguyên nhân trong documentation comment: bổ sung mô tả còn thiếu, sửa tham chiếu, viết HTML đúng và cải thiện accessibility. Khi chạy DocLint trong build và kiểm tra HTML thực tế, tài liệu API sẽ chính xác, dễ đọc và đáng tin cậy hơn.