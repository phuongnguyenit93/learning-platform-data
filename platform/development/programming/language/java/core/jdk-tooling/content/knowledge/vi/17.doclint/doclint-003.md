# Xử lý lỗi tag Javadoc bằng DocLint

Javadoc comments mô tả API Java và được công cụ **javadoc** chuyển thành tài liệu HTML. Một tag sai tên, đặt sai vị trí, tham chiếu không tồn tại hoặc HTML không hợp lệ có thể tạo warning hoặc error khi sinh tài liệu. **DocLint** là bộ kiểm tra tích hợp của Javadoc giúp phát hiện phần lớn lỗi phổ biến trước khi tài liệu được phát hành.

Bài này sử dụng JDK 17 trở lên. Nội dung tập trung vào cách nhận diện lỗi block tag và inline tag, sửa tên tham số hoặc tham chiếu sai, xử lý ký tự HTML, hiểu các nhóm kiểm tra của DocLint và đưa kiểm tra Javadoc vào quy trình build.

## 1. Javadoc comment và tag là gì?

Javadoc comment là comment bắt đầu bằng **/**\*** và được đặt ngay trước khai báo mà nó mô tả, chẳng hạn module, package, class, interface, constructor, method hoặc field.

Ví dụ:

~~~java
/**
 * Converts a message to uppercase.
 */
public String upper(String message) {
    return message.toUpperCase();
}
~~~

Comment thông thường bắt đầu bằng **/* ** hoặc **//** không được xem là Javadoc comment cho khai báo.

Một Javadoc comment thường có hai phần:

1. Main description: phần mô tả chính nằm trước block tag đầu tiên.
2. Tag section: các block tag cung cấp thông tin có cấu trúc như tham số, giá trị trả về, exception, phiên bản hoặc liên kết.

Câu đầu tiên của main description nên là câu tóm tắt ngắn gọn, mô tả đầy đủ mục đích của API. Khi block tag đầu tiên xuất hiện, main description kết thúc; không tiếp tục viết phần mô tả chính sau đó.

## 2. Phân biệt block tag và inline tag

### 2.1. Block tag

Block tag bắt đầu bằng ký tự **@** ở đầu một dòng, sau phần dấu sao và khoảng trắng của comment. Nội dung của tag kéo dài tới block tag kế tiếp hoặc hết comment.

Ví dụ:

~~~java
/**
 * Calculates the total price.
 *
 * @param unitPrice price of one item
 * @param quantity number of items
 * @return the total price
 */
public long total(long unitPrice, int quantity) {
    return unitPrice * quantity;
}
~~~

Các lỗi thường gặp:

- Viết **@param** ở giữa dòng và mong nó được nhận diện như block tag.
- Viết sai tên tag, ví dụ **@returns** thay vì **@return**.
- Đặt tag ở phần mô tả chính nhưng quên xuống dòng.
- Gõ tên tham số khác với tên trong khai báo method.
- Dùng tag ở loại khai báo không hỗ trợ tag đó.

Nếu muốn bắt đầu một dòng mô tả bằng ký tự **@** mà không tạo tag, dùng entity HTML **&#064;** hoặc đặt ký tự đó trong inline tag phù hợp.

### 2.2. Inline tag

Inline tag nằm trong nội dung mô tả và được bao bởi cặp dấu ngoặc nhọn.

Ví dụ:

~~~java
/**
 * Returns the {@code String} representation of this value.
 * See {@link #toString()} for the textual form.
 */
~~~

Một số inline tag thường dùng:

| Inline tag | Mục đích |
|---|---|
| **{@code ...}** | Hiển thị văn bản dạng code, không phân tích nội dung như HTML hoặc tag lồng |
| **{@literal ...}** | Hiển thị nguyên văn nhưng không dùng font code |
| **{@link ...}** | Tạo liên kết inline tới class, method, field hoặc API |
| **{@linkplain ...}** | Tạo liên kết với nhãn hiển thị dạng văn bản thường |
| **{@inheritDoc}** | Chèn nội dung Javadoc được kế thừa từ method cha hoặc interface |
| **{@value}** | Chèn giá trị của hằng số phù hợp |
| **{@docRoot}** | Đường dẫn tương đối tới gốc tài liệu được sinh |

Lỗi phổ biến là bỏ ngoặc nhọn, ví dụ viết **@code String** thay vì **{@code String}**, hoặc đóng inline tag không đúng vị trí. Kiểm tra đủ cả dấu ngoặc, tên tag và nội dung của tag.

## 3. Đặt tag đúng khai báo

Không phải tag nào cũng dùng được cho mọi loại khai báo.

| Tag | Nơi dùng chính | Dữ liệu cần cung cấp |
|---|---|---|
| **@param** | Class/type parameter, method, constructor | Tên tham số hoặc **&lt;T&gt;** cho type parameter |
| **@return** | Method có giá trị trả về | Mô tả giá trị được trả về |
| **@throws** | Method, constructor | Kiểu exception và điều kiện phát sinh |
| **@see** | Nhiều loại khai báo | Tên API, URL hoặc văn bản tham chiếu |
| **@since** | Module, package, type, member | Phiên bản API được giới thiệu |
| **@deprecated** | Type hoặc member được đánh dấu deprecated | Lý do và API thay thế |
| **@author** | Overview, module, package, type | Tên tác giả; hiển thị khi dùng **-author** |
| **@version** | Overview, module, package, type | Thông tin phiên bản; hiển thị khi dùng **-version** |
| **@serial** | Class, package hoặc field serializable theo quy tắc tương ứng | Hướng dẫn serialized form |
| **@provides**, **@uses** | Module declaration | Service được cung cấp hoặc sử dụng |

Một số quy tắc quan trọng:

- **@param** không dùng cho field.
- **@return** chỉ dùng cho method; không dùng cho constructor hoặc method **void**.
- **@throws** dùng cho method và constructor, không dùng làm mô tả exception chung ở class.
- **@param &lt;T&gt;** dùng cho type parameter generic; phải có dấu ngoặc nhọn.
- **@deprecated** nên đi cùng annotation **@Deprecated** trên chính khai báo.
- **@exception** là dạng tương đương cũ của **@throws**; nên ưu tiên **@throws**.

Nếu một method override hoặc implement method khác, standard doclet có thể kế thừa main description và các tag **@param**, **@return**, **@throws** còn thiếu từ method cha/interface khi source tương ứng có sẵn. Có thể dùng **{@inheritDoc}** để chèn nội dung kế thừa rõ ràng. Tag này chỉ hợp lệ trong các vị trí hỗ trợ trên method có quan hệ kế thừa; không dùng cho constructor hoặc field.

## 4. Sửa các lỗi block tag thường gặp

### 4.1. Sai tên trong @param

Khai báo:

~~~java
public String greet(String recipient) {
    return "Hello, " + recipient;
}
~~~

Sai:

~~~java
/**
 * Greets a recipient.
 *
 * @param name person to greet
 * @return greeting text
 */
~~~

Đúng:

~~~java
/**
 * Greets a recipient.
 *
 * @param recipient person to greet
 * @return greeting text
 */
~~~

Tên sau **@param** phải khớp với tham số thực tế. Với generic type parameter:

~~~java
/**
 * Wraps a value.
 *
 * @param <T> type of the wrapped value
 * @param value value to wrap
 */
public <T> T identity(T value) {
    return value;
}
~~~

**@param T** và **@param &lt;T&gt;** không tương đương; generic type parameter cần đặt trong dấu ngoặc nhọn.

### 4.2. Thiếu hoặc đặt sai @return

Method trả về dữ liệu nên mô tả kết quả:

~~~java
/**
 * Returns the number of characters in a message.
 *
 * @param message message to measure
 * @return number of UTF-16 code units in the message
 */
public int length(String message) {
    return message.length();
}
~~~

Không thêm **@return** cho constructor hoặc method **void**. Với method trả về **boolean**, mô tả điều kiện true và false thay vì chỉ viết “the result”.

### 4.3. Sai kiểu trong @throws

Dùng tên kiểu exception hợp lệ và mô tả điều kiện phát sinh:

~~~java
/**
 * Parses a positive integer.
 *
 * @param text text to parse
 * @return parsed integer
 * @throws NumberFormatException if text is not a valid integer
 * @throws IllegalArgumentException if the parsed value is not positive
 */
public int parsePositive(String text) {
    int value = Integer.parseInt(text);
    if (value <= 0) {
        throw new IllegalArgumentException("value must be positive");
    }
    return value;
}
~~~

Tên sau **@throws** phải được Javadoc phân giải thành kiểu exception. Có thể ghi exception unchecked dù nó không xuất hiện trong **throws** clause của chữ ký method. Đừng ghi một class thông thường không kế thừa **Throwable**.

### 4.4. Tag lặp hoặc tag thừa

Kiểm tra từng tag có tương ứng với khai báo không:

- Không ghi hai **@return** cho cùng một method.
- Không lặp **@param** cho cùng một tham số.
- Không thêm **@param** cho tên tham số không tồn tại.
- Không thêm **@throws** cho một tên type bị gõ sai.
- Không đưa **@return** vào constructor hay method **void**.

Tag lặp hoặc thông tin thừa có thể tạo warning; tag sai cấu trúc hoặc sai tham chiếu có thể tạo error. Cách xử lý tốt nhất là sửa comment theo chữ ký thật của API.

## 5. Sửa lỗi inline tag và tham chiếu API

### 5.1. Cú pháp liên kết với {@link}

Một member reference thường có dạng:

~~~text
{@link package.Class#method(Type) label}
~~~

Có thể bỏ package hoặc class khi tham chiếu trong cùng class:

~~~java
/**
 * Formats a message. Use {@link #normalize(String) normalize}
 * before storing user input.
 */
public String format(String text) {
    return normalize(text);
}

/**
 * Normalizes whitespace.
 *
 * @param text input text
 * @return normalized text
 */
private String normalize(String text) {
    return text.trim();
}
~~~

Nếu có overload, ghi rõ kiểu tham số để Javadoc chọn đúng method. Nếu tên class hoặc member không được phân giải, kiểm tra:

1. Tên package và class có chính xác không.
2. Tên member có đúng chữ hoa/chữ thường không.
3. Danh sách kiểu tham số có khớp chữ ký không.
4. Tham chiếu có thiếu dấu **#**, dấu ngoặc hoặc dấu phẩy không.
5. Kiểu được tham chiếu có nằm trong source/API mà Javadoc có thể tìm thấy không.

Nếu class thuộc API bên ngoài, dùng **-link** hoặc **-linkoffline** để tạo hyperlink tới bộ Javadoc bên ngoài. **-link** cần URL tới thư mục tài liệu có **element-list** hoặc **package-list**; **-linkoffline** hữu ích khi file danh sách có sẵn cục bộ nhưng tài liệu đích không truy cập được trong lúc build.

### 5.2. {@link} và {@linkplain}

Cả hai đều tạo liên kết tới API. **{@link}** hiển thị nhãn theo kiểu code; **{@linkplain}** hiển thị nhãn dạng văn bản thông thường.

Ví dụ:

~~~java
/**
 * Converts the input using {@link String#strip()}.
 * See {@linkplain String#trim() the trim method} for related behavior.
 */
~~~

Nếu link không hoạt động, kiểm tra cú pháp member reference và khả năng truy cập tài liệu ngoài. Không thay link bằng văn bản thường chỉ để che một tham chiếu sai.

### 5.3. {@inheritDoc} đặt sai vị trí

**{@inheritDoc}** chèn phần mô tả từ method được override hoặc implement. Dùng trong main description hoặc nội dung của **@param**, **@return**, **@throws** trên method phù hợp.

Ví dụ:

~~~java
interface MessageSource {
    /**
     * Loads a message for a key.
     *
     * @param key message key
     * @return resolved message
     */
    String load(String key);
}

final class DefaultMessageSource implements MessageSource {
    /**
     * {@inheritDoc}
     */
    @Override
    public String load(String key) {
        return key;
    }
}
~~~

Nếu method không override hoặc implement một method có documentation để kế thừa, Javadoc không thể tìm nội dung phù hợp. Khi đó hãy viết mô tả trực tiếp hoặc đặt **{@inheritDoc}** ở method đúng quan hệ kế thừa.

## 6. Xử lý ký tự HTML và nội dung code

Javadoc comment có thể chứa HTML. Các ký tự **&lt;**, **&gt;** và **&amp;** có ý nghĩa đặc biệt trong markup; nếu dùng như văn bản thông thường, cần escape hoặc đặt trong inline tag thích hợp.

Sai:

~~~java
/**
 * Returns true if size < limit and size > 0.
 */
~~~

Đúng bằng **{@code}**:

~~~java
/**
 * Returns true if {@code size < limit && size > 0}.
 */
~~~

Hoặc dùng HTML entities:

~~~java
/**
 * Returns true if size &lt; limit and size &gt; 0.
 */
~~~

Các lưu ý:

- Dùng **{@code ...}** cho tên class, biểu thức, lệnh và đoạn code ngắn.
- Dùng **{@literal ...}** khi cần giữ nguyên ký tự mà không dùng font code.
- Escape ampersand thành **&amp;** khi nó là văn bản.
- Đóng các HTML element yêu cầu thẻ kết thúc.
- Không lồng block element bên trong inline element.
- Dùng HTML hợp lệ theo chuẩn HTML5.
- Với **&lt;img&gt;**, cung cấp nội dung **alt** có ý nghĩa.
- Với bảng, bổ sung caption hoặc thông tin phù hợp để hỗ trợ accessibility.

Block tag cũng có thể bị nhận diện nhầm nếu một dòng mô tả bắt đầu bằng **@**. Khi đó dùng entity **&#064;** hoặc đặt nội dung trong **{@code}**.

## 7. DocLint kiểm tra những gì?

Trong JDK 17, DocLint được bật mặc định khi chạy công cụ **javadoc**. Nó kiểm tra các nhóm vấn đề phổ biến trong documentation comments.

| Nhóm | Kiểm tra | Ví dụ lỗi |
|---|---|---|
| **accessibility** | Vấn đề hỗ trợ truy cập trong HTML | Bảng thiếu caption hoặc hình thiếu mô tả phù hợp |
| **html** | Cấu trúc HTML và cách lồng element | Thiếu thẻ đóng hoặc đặt block element bên trong inline element |
| **missing** | Thiếu Javadoc comment hoặc tag cần thiết | Thiếu mô tả class, **@param** hoặc **@return** |
| **reference** | Tham chiếu tới phần tử Java | **@see** hoặc **{@link}** trỏ tới member không tồn tại; tên **@param** sai |
| **syntax** | Cú pháp Javadoc và ký tự đặc biệt | Tag không hợp lệ, **&lt;** hoặc **&amp;** chưa escape |

DocLint không phải bộ kiểm tra HTML toàn diện và không tự sửa comment. Nó giúp tìm phần lớn lỗi thường gặp; tài liệu được sinh vẫn nên được kiểm tra thêm nếu có yêu cầu HTML/accessibility nghiêm ngặt.

### 7.1. Bật tất cả nhóm kiểm tra

~~~powershell
javadoc -Xdoclint:all -d docs -sourcepath src com.example
~~~

JDK 17 bật DocLint mặc định, nhưng ghi rõ **-Xdoclint:all** trong build làm cho ý định kiểm tra rõ ràng hơn.

### 7.2. Chọn nhóm kiểm tra

Chỉ kiểm tra HTML, syntax và accessibility:

~~~powershell
javadoc -Xdoclint:html,syntax,accessibility -d docs -sourcepath src com.example
~~~

Tắt nhóm **missing** nhưng giữ các nhóm còn lại:

~~~powershell
javadoc -Xdoclint:all,-missing -d docs -sourcepath src com.example
~~~

Tắt toàn bộ DocLint:

~~~powershell
javadoc -Xdoclint:none -d docs -sourcepath src com.example
~~~

Chỉ nên tắt một nhóm khi đã hiểu warning nào được bỏ qua và có quy trình kiểm tra thay thế. **-Xdoclint:none** không sửa comment; nó chỉ ngừng báo các vấn đề DocLint.

### 7.3. Chuyển warning thành lỗi trong CI

Dùng **-Werror** để build thất bại nếu Javadoc phát ra warning:

~~~powershell
javadoc -Xdoclint:all -Werror -d docs -sourcepath src com.example
~~~

Cách này hữu ích trong CI vì warning về tài liệu không bị bỏ qua âm thầm. Nếu dự án đang có nhiều warning cũ, hãy sửa theo từng nhóm trước khi bật **-Werror** cho toàn bộ build.

### 7.4. Chọn phạm vi khai báo được kiểm tra

Javadoc mặc định tạo tài liệu cho public và protected API. Các tùy chọn visibility ảnh hưởng những khai báo được đưa vào output và được kiểm tra:

| Tùy chọn | Phạm vi |
|---|---|
| **-public** | Chỉ public |
| **-protected** | Public và protected; đây là mặc định |
| **-package** | Public, protected và package-private |
| **-private** | Tất cả, gồm private |

Nếu lỗi chỉ xuất hiện khi kiểm tra tài liệu nội bộ, chạy thêm **-private** để mở rộng phạm vi.

**javac** cũng hỗ trợ **-Xdoclint** để kiểm tra comment trong lúc biên dịch, nhưng tùy chọn này không bật mặc định trong **javac**. Việc sinh tài liệu bằng **javadoc** vẫn là bước cần thiết để kiểm tra kết quả HTML.

## 8. Ví dụ hoàn chỉnh: Javadoc hợp lệ và chạy được

Tạo cấu trúc:

~~~text
project/
└── src/
    └── com/
        └── example/
            ├── package-info.java
            └── TextFormatter.java
~~~

Nội dung **src/com/example/package-info.java**:

~~~java
/**
 * Public API for formatting short messages.
 */
package com.example;
~~~

Nội dung **src/com/example/TextFormatter.java**:

~~~java
package com.example;

import java.util.Objects;

/**
 * Combines a prefix and a value into a message.
 *
 * <p>Use {@link #format(String,String) format} to create a message.
 */
public final class TextFormatter {

    /**
     * Creates a formatter.
     */
    public TextFormatter() {
    }

    /**
     * Joins a prefix and a value.
     *
     * @param prefix text placed before the value
     * @param value text placed after the prefix
     * @return the combined message
     * @throws java.lang.NullPointerException if prefix or value is null
     * @since 1.0
     */
    public String format(String prefix, String value) {
        return Objects.requireNonNull(prefix)
                .concat(Objects.requireNonNull(value));
    }

    /**
     * Prints a sample formatted message.
     *
     * @param args command-line arguments; not used
     */
    public static void main(String[] args) {
        System.out.println(new TextFormatter().format("Hello, ", "Java!"));
    }
}
~~~

Từ thư mục **project**, tạo tài liệu với tất cả nhóm DocLint và biến warning thành error:

~~~powershell
javadoc -Xdoclint:all -Werror -d docs -sourcepath src com.example
~~~

Biên dịch và chạy ví dụ:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac -d out src/com/example/TextFormatter.java
java -cp out com.example.TextFormatter
~~~

Stdout chính xác:

~~~text
Hello, Java!
~~~

Ví dụ có package comment, class comment, constructor comment, **@param**, **@return**, **@throws**, **@since** và **{@link}**. Các tên tham số và tham chiếu đều khớp khai báo nên phù hợp để làm mẫu cho build có DocLint.

## 9. Đọc diagnostic và tìm vị trí lỗi

Khi phát hiện vấn đề, Javadoc thường in thông báo, dòng source liên quan và dấu **^** chỉ vị trí lỗi. Nội dung chính xác của thông báo có thể thay đổi theo phiên bản JDK.

Quy trình đọc lỗi:

1. Đọc tên file và số dòng trước.
2. Xem nhóm DocLint nếu được nêu trong diagnostic.
3. Kiểm tra tag hoặc HTML ngay tại vị trí được chỉ ra.
4. So sánh tag với chữ ký method/type.
5. Sửa nguyên nhân gốc rồi chạy lại cùng lệnh.

Một số dạng thông báo có thể gặp:

| Dạng lỗi | Cần kiểm tra |
|---|---|
| Invalid tag hoặc unknown tag | Chính tả, block/inline syntax và tag custom đã đăng ký hay chưa |
| **@param** không hợp lệ | Tên tham số hoặc cú pháp **&lt;T&gt;** |
| Missing **@return** | Method có giá trị trả về nhưng thiếu mô tả |
| Reference not found | Tên class/member, chữ ký overload, import và external link |
| End tag missing | HTML element chưa đóng |
| Unescaped **&lt;** hoặc **&amp;** | Dùng **{@code}**, **{@literal}** hoặc HTML entity |
| Missing comment | Khai báo nằm trong phạm vi được sinh nhưng chưa có Javadoc |
| Invalid use of **{@inheritDoc}** | Method không có comment cha/interface phù hợp hoặc tag đặt sai vị trí |

Không chỉ sửa để thông báo biến mất. Hãy đảm bảo phần mô tả sau khi sửa vẫn đúng với hành vi API.

## 10. Phân biệt warning và error

DocLint có thể báo warning hoặc error tùy mức độ ảnh hưởng tới tài liệu sinh ra.

- Warning thường liên quan đến nội dung còn thiếu, thông tin trùng lặp hoặc comment không cần thiết nhưng chưa làm HTML trở nên không hợp lệ.
- Error thường liên quan đến cú pháp Javadoc sai, tham chiếu sai hoặc HTML có thể tạo output không hợp lệ.

Nếu build thành công nhưng có warning, tài liệu vẫn có thể được sinh. Tuy nhiên, warning về API public thường là dấu hiệu tài liệu chưa đủ hoặc sai lệch so với code. Với thư viện được phát hành, nên xử lý warning thay vì bỏ qua.

**-Werror** giúp biến warning thành lỗi build. Dùng tùy chọn này sau khi đã làm sạch warning hiện có để ngăn lỗi tài liệu mới lọt vào release.

## 11. Custom tag và taglet

Dự án có thể dùng tag riêng cho quy trình nội bộ. Nếu Javadoc gặp một tag không thuộc standard doclet, cần đăng ký tag đó bằng tùy chọn **-tag** hoặc triển khai taglet bằng **-taglet**.

Cú pháp tổng quát:

~~~text
-tag name:locations:header
~~~

Các trường được phân tách bằng dấu **:**. **name** là tên tag, **locations** xác định nơi tag được phép dùng, và **header** là nhãn hiển thị trong tài liệu.

Nếu dự án có tag tùy chỉnh, hãy thống nhất định nghĩa tag trong build để Javadoc nhận diện nó. Khi cần logic render phức tạp hoặc inline tag có nhiều đối số, dùng Taglet phù hợp.

Không đổi một tag chuẩn như **@param** thành custom tag. Với tag chuẩn, hãy sửa cú pháp và cách dùng theo specification.

## 12. Quy trình sửa lỗi tag Javadoc

Khi build Javadoc thất bại:

1. Chạy lại đúng lệnh **javadoc** và giữ nguyên diagnostic đầy đủ.
2. Phân loại lỗi vào **syntax**, **html**, **reference**, **missing** hoặc **accessibility**.
3. Xác nhận Javadoc comment bắt đầu bằng **/**\*** và nằm ngay trước khai báo.
4. Đối chiếu **@param**, **@return** và **@throws** với chữ ký method.
5. Sửa tên tag, dấu ngoặc của inline tag và tham chiếu **{@link}**/**@see**.
6. Escape ký tự HTML và sửa cấu trúc element.
7. Nếu dùng custom tag, đăng ký bằng **-tag** hoặc taglet.
8. Chạy **javadoc -Xdoclint:all** lại.
9. Khi không còn warning cần xử lý, bật **-Werror** trong CI.
10. Mở một số trang HTML được sinh để kiểm tra nội dung, liên kết và khả năng đọc.

Nếu chỉ muốn tìm lỗi trong một nhóm, dùng tùy chọn DocLint có chọn lọc. Sau khi sửa xong, chạy lại toàn bộ nhóm để bảo đảm không còn lỗi ở nhóm khác.

## 13. Checklist trước khi phát hành Javadoc

- [ ] Javadoc comment dùng **/**\* ... */** và đặt ngay trước khai báo.
- [ ] Main description có câu tóm tắt rõ ràng.
- [ ] Block tag bắt đầu ở đầu dòng và không bị lẫn với văn bản thường.
- [ ] Mỗi **@param** khớp đúng tên tham số; generic parameter dùng **&lt;T&gt;**.
- [ ] **@return** chỉ dùng cho method có giá trị trả về.
- [ ] **@throws** trỏ tới exception type hợp lệ và mô tả điều kiện phát sinh.
- [ ] **{@link}** và **@see** trỏ tới class/member tồn tại.
- [ ] **{@inheritDoc}** chỉ dùng trong method có quan hệ kế thừa phù hợp.
- [ ] Inline tag có đủ dấu ngoặc nhọn.
- [ ] Ký tự **&lt;**, **&gt;** và **&amp;** được escape hoặc đặt trong **{@code}**/**{@literal}**.
- [ ] HTML element được đóng và lồng đúng; bảng/hình có thông tin accessibility phù hợp.
- [ ] Custom tag được đăng ký trong build.
- [ ] **javadoc -Xdoclint:all** chạy thành công.
- [ ] Warning quan trọng đã được xử lý; CI dùng **-Werror** khi phù hợp.
- [ ] HTML được sinh đã được kiểm tra trên trình duyệt hoặc validator cần thiết.

Lỗi tag Javadoc thường xuất phát từ tag sai loại, sai vị trí, tên tham số không khớp, tham chiếu API không tồn tại hoặc HTML chưa hợp lệ. Hãy đọc diagnostic của DocLint, sửa comment theo đúng khai báo Java và chạy lại **javadoc -Xdoclint:all**. Dùng **-Werror** trong CI để bảo đảm warning về tài liệu cũng được xử lý trước khi phát hành.

## Tài liệu tham khảo

- Oracle, The javadoc Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html
- Oracle, Documentation Comment Specification for the Standard Doclet, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html
- Oracle, The javac Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
