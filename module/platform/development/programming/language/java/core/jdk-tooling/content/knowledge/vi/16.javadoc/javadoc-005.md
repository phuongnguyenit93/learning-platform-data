# Link trong Javadoc

Javadoc tạo tài liệu HTML từ documentation comment trong mã nguồn Java. **Link trong Javadoc** giúp người đọc chuyển từ một API sang class, method, field, package, module hoặc tài liệu tham khảo liên quan. Một liên kết tốt cho người đọc biết đích đến là gì, hoạt động khi tài liệu được tạo thành nhiều bộ riêng và không dẫn tới trang bị thiếu.

Có hai phạm vi chính:

- **Liên kết nội bộ**: trỏ tới declaration được tạo tài liệu trong cùng lần chạy Javadoc, chẳng hạn method khác trong class hoặc class khác trong project.
- **Liên kết bên ngoài**: trỏ tới API hoặc bộ tài liệu được tạo ở nơi khác, chẳng hạn Java SE API hoặc Javadoc của một thư viện dependency.

Javadoc cung cấp inline tags như **{@link}** và **{@linkplain}**, block tag **@see**, cùng tùy chọn dòng lệnh **-link** và **-linkoffline** để nối các bộ tài liệu độc lập.

## 1. Các loại link thường dùng

| Cú pháp | Vị trí | Mục đích |
|---|---|---|
| **{@link reference}** | Trong một câu hoặc đoạn mô tả | Tạo link tới module, package, class hoặc member |
| **{@linkplain reference label}** | Trong một câu hoặc đoạn mô tả | Tạo link với nhãn hiển thị dạng văn bản thông thường |
| **@see reference** | Block tag ở cuối documentation comment | Thêm mục liên kết trong phần See Also |
| **@see HTML anchor** | Block tag | Thêm link tới URL bên ngoài |
| **{@docRoot}** | Inline tag | Lấy đường dẫn tương đối từ trang hiện tại tới gốc bộ tài liệu |
| **-link URL** | Tùy chọn javadoc | Nối link tới bộ Javadoc bên ngoài có metadata danh sách package/module |
| **-linkoffline URL1 URL2** | Tùy chọn javadoc | Nối link tới bộ tài liệu bên ngoài khi metadata được lưu ở vị trí khác hoặc máy build không truy cập được URL |

Chọn cú pháp theo ngữ cảnh. Dùng {@link} khi nhắc tới API ngay trong câu; dùng @see khi muốn gom tài liệu liên quan thành một mục riêng; dùng -link hoặc -linkoffline khi tạo tài liệu cho nhiều thư viện hoặc module độc lập.

## 2. Cú pháp tham chiếu tới API

Tham chiếu trong Javadoc có thể trỏ tới module, package, class/interface, constructor, method, annotation member, field, enum constant hoặc record component.

Dạng tổng quát thường gặp:

~~~text
[module/][package.]Class#member(parameter-types)
~~~

Có thể rút gọn phần đầu khi Javadoc suy ra được từ vị trí của documentation comment.

Ví dụ:

| Tham chiếu | Đích đến |
|---|---|
| **{@link #normalize(String)}** | Method normalize trong class hiện tại |
| **{@link #DEFAULT_LOCALE}** | Field DEFAULT_LOCALE trong class hiện tại |
| **{@link NameFormatter}** | Class NameFormatter trong phạm vi hiện tại |
| **{@link NameFormatter#normalize(String)}** | Method normalize của NameFormatter |
| **{@link java.lang.String}** | Class String trong package java.lang |
| **{@link java.lang.String#trim()}** | Method trim của String |
| **{@link java.base/java.lang.String#trim()}** | Method trim của String, có chỉ rõ module java.base |
| **{@link #NameFormatter()}** | Constructor NameFormatter trong class hiện tại |

Với member, dấu **#** phân cách tên class và tên member. Với method hoặc constructor, có thể thêm danh sách kiểu tham số trong ngoặc để phân biệt các overload.

### Liên kết tới method overload

Giả sử class có hai method:

~~~java
public String format(String value) {
    return value.trim();
}

public String format(String value, int width) {
    return value.trim();
}
~~~

Tham chiếu rõ overload cần dùng:

~~~java
/**
 * Uses {@link #format(String)} for the default format.
 * For fixed-width output, use {@link #format(String, int)}.
 */
~~~

Nếu chỉ ghi {@link #format}, Javadoc có thể không xác định được member mong muốn hoặc đưa ra cảnh báo tùy trường hợp. Khi class có overload, nên ghi đủ danh sách tham số.

Có thể dùng tên kiểu đơn giản nếu kiểu nằm trong phạm vi import hoặc cùng package. Khi có tên trùng hoặc tham chiếu phức tạp, dùng tên đầy đủ như java.lang.String để giảm mơ hồ.

### Link tới field, constructor và nested type

Ví dụ:

~~~java
/**
 * Creates a formatter using {@link #NameFormatter()}.
 * The default width is {@link #DEFAULT_WIDTH}.
 * Builder options are available in {@link Builder}.
 */
~~~

#NameFormatter() trỏ tới constructor; #DEFAULT_WIDTH trỏ tới field; Builder trỏ tới nested type nếu Javadoc xác định được trong phạm vi hiện tại.

## 3. {@link} và {@linkplain}

Cả hai inline tag đều tạo link tới cùng loại API reference, nhưng khác cách hiển thị nhãn.

### {@link}

{@link} tạo link nội tuyến. Khi nhãn là tên declaration hoặc không cung cấp nhãn riêng, Javadoc thường hiển thị theo kiểu code, phù hợp với tên class, method và field.

Ví dụ:

~~~java
/**
 * Call {@link #normalize(String)} before comparing names.
 * The result is compatible with {@link java.lang.String#trim()}.
 */
~~~

Trong trang HTML, người đọc có thể nhấp vào tên method để mở phần tài liệu tương ứng.

Có thể cung cấp nhãn riêng sau reference:

~~~java
/**
 * See {@link #normalize(String) the normalization method}.
 */
~~~

### {@linkplain}

{@linkplain} hoạt động giống {@link}, nhưng nhãn được hiển thị bằng font văn bản thông thường thay vì kiểu code. Dùng khi nhãn là một cụm từ tự nhiên:

~~~java
/**
 * Read {@linkplain #normalize(String) the normalization rules}
 * before passing user input to this method.
 */
~~~

### So sánh nhanh

| Tag | Khi nên dùng | Cách hiển thị nhãn |
|---|---|---|
| **{@link #save()}** | Nhắc trực tiếp tên method | Kiểu code phù hợp với API identifier |
| **{@linkplain #save() save operation}** | Viết câu tự nhiên | Văn bản thông thường |
| **@see #save()** | Đưa method vào phần See Also | Một mục liên kết riêng |

Không cần dùng link cho mọi lần xuất hiện của một từ. Chỉ liên kết khi đích đến giúp người đọc hiểu hoặc sử dụng API tốt hơn.

## 4. @see: phần See Also

@see là block tag. Javadoc gom các tag này vào phần **See Also** của trang được tạo.

Có ba dạng chính.

### Tham chiếu tới program element

~~~java
/**
 * Normalizes the input before processing.
 *
 * @see #isEmpty(String)
 * @see java.lang.String#trim()
 * @see java.util.List
 */
~~~

Javadoc tạo link tới method, class hoặc type tương ứng nếu tham chiếu được phân giải.

### Link tới URL bằng HTML anchor

~~~java
/**
 * See the
 * @see <a href="https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html">String API documentation</a>
 */
~~~

Dạng này phù hợp khi muốn trỏ tới một trang web cụ thể, chẳng hạn hướng dẫn, tiêu chuẩn hoặc tài liệu không được tạo bởi Javadoc.

### Văn bản không tạo link

~~~java
/**
 * @see "Internal migration notes maintained by the platform team"
 */
~~~

Khi nội dung bắt đầu bằng dấu ngoặc kép, Javadoc hiển thị một mục văn bản mà không tạo hyperlink. Dùng dạng này khi muốn chỉ ra tài liệu hoặc đầu mối tham khảo không có URL.

Có thể khai báo nhiều @see trong cùng một documentation comment. Hãy giữ các mục ngắn, liên quan trực tiếp tới class hoặc member đang mô tả.

## 5. Link tới class và member trong cùng bộ tài liệu

Khi các class được đưa vào cùng một lần chạy Javadoc, Javadoc có thể tạo liên kết nội bộ mà không cần tùy chọn -link.

Ví dụ cấu trúc:

~~~text
src/
  com/example/api/
    NameFormatter.java
    NameValidator.java
~~~

Trong NameFormatter.java:

~~~java
package com.example.api;

/**
 * Formats user-facing names.
 * Use {@link NameValidator} to validate input and
 * {@link #normalize(String)} to normalize whitespace.
 *
 * @see NameValidator#isValid(String)
 */
public final class NameFormatter {

    private NameFormatter() {
    }

    /**
     * Removes leading and trailing whitespace.
     *
     * @param input text to normalize
     * @return normalized text, or an empty string when input is null
     * @see #isBlank(String)
     */
    public static String normalize(String input) {
        return input == null ? "" : input.trim();
    }

    /**
     * Checks whether the supplied text is blank.
     *
     * @param input text to inspect
     * @return true if input is null or blank
     */
    public static boolean isBlank(String input) {
        return input == null || input.isBlank();
    }
}
~~~

Trong NameValidator.java:

~~~java
package com.example.api;

/**
 * Validates user-facing names.
 */
public final class NameValidator {

    private NameValidator() {
    }

    /**
     * Checks whether a name contains non-whitespace text.
     *
     * @param value name to inspect
     * @return true when the name is valid
     */
    public static boolean isValid(String value) {
        return value != null && !value.isBlank();
    }
}
~~~

Tạo Javadoc cho cả package:

~~~bash
javadoc -d docs -sourcepath src -subpackages com.example.api
~~~

Khi cả hai class nằm trong cùng lần chạy, các tham chiếu NameValidator, NameValidator#isValid(String) và #normalize(String) được tạo thành link nội bộ trong HTML.

Các file HTML thường nằm dưới:

~~~text
docs/
  com/
    example/
      api/
        NameFormatter.html
        NameValidator.html
  index.html
  allclasses-index.html
~~~

Cấu trúc chi tiết phụ thuộc phiên bản Javadoc và cấu hình doclet. Hãy mở trang class được tạo để xác nhận link trỏ tới đúng member.

## 6. Link tới Java SE API bên ngoài

Khi source dùng class của JDK như String, List, Map hoặc Path, Javadoc có thể biết kiểu từ compiler nhưng muốn tạo hyperlink tới tài liệu Java SE được xuất bản ở một URL riêng thì cần cấu hình liên kết ngoài.

Tùy chọn **-link** nhận URL của thư mục gốc chứa tài liệu Javadoc bên ngoài:

~~~bash
javadoc -d docs -sourcepath src -subpackages com.example.api -link https://docs.oracle.com/en/java/javase/17/docs/api/
~~~

Trong ví dụ, URL là gốc của bộ Java SE 17 API docs. Javadoc sử dụng metadata tại thư mục đó để nhận diện module/package có thể liên kết, sau đó tạo link từ các reference như java.lang.String hoặc java.util.List.

Một số điểm quan trọng:

- Truyền URL tới thư mục gốc của bộ tài liệu, không phải URL của một trang class riêng lẻ.
- Thư mục tài liệu bên ngoài cần có file metadata do Javadoc tạo, thường là **element-list** đối với tài liệu modular hoặc **package-list** đối với tài liệu kiểu cũ.
- Có thể dùng nhiều tùy chọn -link trong cùng một lần chạy để liên kết nhiều bộ tài liệu.
- Chọn URL tương ứng với Java release mà dự án muốn tham chiếu.
- URL phải dẫn tới bộ tài liệu được xuất bản và có thể truy cập từ môi trường build.

Ví dụ source có thể viết:

~~~java
/**
 * Returns an immutable view.
 * See {@link java.util.List} and {@link java.lang.String#trim()}.
 */
~~~

Khi Javadoc được tạo với -link tới Java SE API, các reference bên ngoài có thể trỏ tới trang API chính thức tương ứng.

## 7. Link tới thư viện hoặc bộ tài liệu bên ngoài bằng -link

Giả sử thư viện Acme Model đã xuất bản Javadoc tại:

~~~text
https://docs.example.com/acme-model/api/
~~~

Trong source của ứng dụng, có reference:

~~~java
/**
 * Converts a model using {@link com.acme.model.Customer}.
 */
~~~

Nếu muốn link tới tài liệu Acme Model, thêm:

~~~bash
javadoc -d docs -sourcepath src -subpackages com.acme.app -link https://docs.example.com/acme-model/api/
~~~

Javadoc đọc file element-list hoặc package-list ở thư mục tài liệu đó để biết module và package có sẵn. Sau đó nó có thể tạo hyperlink tới class tương ứng.

Nếu bộ tài liệu bên ngoài được tạo theo module system, element-list mô tả các module/package. Với bộ tài liệu cũ không modular, có thể gặp package-list.

Không tự tạo hoặc sửa nội dung element-list/package-list để ép Javadoc nhận diện package. Đây là file metadata được Javadoc sinh ra trong quá trình tạo bộ tài liệu nguồn.

## 8. -linkoffline khi build không truy cập được tài liệu ngoài

Dùng **-linkoffline** khi URL tài liệu đã biết nhưng máy build không thể truy cập trực tiếp để lấy metadata, hoặc file metadata được lưu ở một vị trí khác.

Cú pháp:

~~~bash
javadoc -linkoffline URL1 URL2
~~~

Trong đó:

- **URL1** là URL sẽ được nhúng vào hyperlink trong HTML được tạo.
- **URL2** là đường dẫn hoặc URL tới thư mục chứa file element-list hoặc package-list mà Javadoc có thể đọc trong lúc build.

Ví dụ thư mục local có cấu trúc:

~~~text
project/
  src/
  docs-cache/
    element-list
~~~

Tạo tài liệu:

~~~bash
javadoc -d docs -sourcepath src -subpackages com.example.api -linkoffline https://docs.example.com/acme-model/api/ docs-cache
~~~

Javadoc dùng metadata trong docs-cache để phân giải package/class, nhưng hyperlink được tạo vẫn trỏ tới URL công bố của Acme Model.

Một số tình huống phù hợp:

- CI build chạy trong mạng nội bộ không có internet.
- Tài liệu dependency được tải hoặc cache sẵn.
- URL tài liệu công khai không cung cấp trực tiếp file metadata nhưng nhóm có bản metadata tương ứng.
- Muốn build tài liệu ổn định, không phụ thuộc kết nối mạng ở mỗi lần chạy.

URL1 phải trỏ tới đúng gốc của tài liệu đã xuất bản. URL2 phải chứa metadata tương ứng với chính bộ tài liệu đó; dùng nhầm element-list của một phiên bản khác có thể tạo link sai.

## 9. Link tới tài liệu tĩnh bằng {@docRoot}

Không phải mọi trang cần liên kết đều là class hoặc method. Một dự án có thể có hướng dẫn cài đặt, sơ đồ kiến trúc hoặc quy trình vận hành được xuất bản cùng Javadoc.

Inline tag **{@docRoot}** được thay bằng đường dẫn tương đối từ trang hiện tại tới gốc của bộ tài liệu được tạo.

Ví dụ:

~~~java
/**
 * Read the
 * <a href="{@docRoot}/guides/installation.html">installation guide</a>
 * before configuring the runtime.
 */
~~~

Nếu trang hiện tại nằm sâu trong package directory, Javadoc tạo đường dẫn tương đối phù hợp để quay về root.

Dùng {@docRoot} khi link tới một trang HTML hoặc resource nằm trong chính bộ tài liệu được tạo. Với API declaration, nên ưu tiên {@link} hoặc {@linkplain} vì Javadoc có thể tự tính đường dẫn tới class/member.

Đảm bảo file đích thực sự được copy vào thư mục output. {@docRoot} chỉ tạo đường dẫn tương đối; nó không tự tạo hoặc kiểm tra nội dung của trang HTML đích.

## 10. Phân giải reference và xử lý overload

Reference được đánh giá trong ngữ cảnh của documentation comment. Import của compilation unit được tính đến khi Javadoc phân giải tên class/interface.

Ví dụ:

~~~java
package com.example.api;

import java.util.List;

/**
 * Returns a {@link List} of results.
 */
public class SearchService {
}
~~~

Vì List đã được import, Javadoc có thể phân giải reference này thành java.util.List.

Khi tên bị trùng giữa các package, dùng tên đầy đủ:

~~~java
/**
 * Uses {@link java.util.Date} for legacy timestamps and
 * {@link java.time.LocalDate} for date-only values.
 */
~~~

Với method overload, ghi đầy đủ tham số:

~~~java
/**
 * @see #find(String)
 * @see #find(String, int)
 */
~~~

Nếu method nằm ở class khác:

~~~java
/**
 * Delegates to {@link SearchService#find(String)}.
 */
~~~

Khi reference không thể phân giải, kiểm tra:

1. Tên class, method hoặc field có đúng chữ hoa/chữ thường không.
2. Method có đúng số lượng và kiểu tham số không.
3. Kiểu tham số có cần tên đầy đủ để tránh mơ hồ không.
4. Class có nằm trong source set, classpath hoặc module path mà Javadoc đang dùng không.
5. Nếu target ở bộ tài liệu khác, đã cấu hình -link hoặc -linkoffline chưa.

## 11. HTML, ký tự đặc biệt và nhãn link

Documentation comment cho phép HTML markup, nhưng nội dung phải tuân theo cú pháp HTML phù hợp. Khi dùng link trực tiếp bằng HTML, hãy đặt nhãn mô tả đích đến.

Ví dụ:

~~~java
/**
 * See <a href="https://docs.example.com/security/">security guide</a>
 * for the deployment requirements.
 */
~~~

Các ký tự có ý nghĩa trong HTML cần được escape đúng cách:

| Ký tự | Cách viết khi cần hiển thị nguyên văn |
|---|---|
| < | &lt; hoặc {@literal <} |
| > | &gt; hoặc {@literal >} |
| & | &amp; |
| Dấu ngoặc nhọn trong inline tag | Dùng entity phù hợp nếu cần biểu diễn ký tự đóng tag |

Để hiển thị code hoặc kiểu generic, ưu tiên {@code}:

~~~java
/**
 * Accepts a {@code List<String>} as input.
 */
~~~

{@literal} hiển thị nội dung mà không diễn giải như HTML hoặc nested Javadoc tag. {@code} cũng hiển thị nội dung literal nhưng dùng kiểu chữ code.

Trong nhãn của inline tag, dấu ngoặc nhọn đóng } có ý nghĩa kết thúc tag. Nếu cần hiển thị ký tự này trong label, dùng entity &#125;.

Không đặt link lồng nhau hoặc tạo HTML anchor chồng lấn. Dùng một link rõ ràng cho một đích đến.

## 12. Kiểm tra link khi tạo Javadoc

Tùy chọn **-Xdoclint:all** bật các nhóm kiểm tra documentation comment, gồm cú pháp tag, HTML và reference. Có thể kết hợp **-Werror** để coi warning là lỗi trong pipeline.

Ví dụ:

~~~bash
javadoc -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example.api -link https://docs.oracle.com/en/java/javase/17/docs/api/
~~~

Nếu Javadoc báo lỗi reference:

- Đọc class/member được báo không tìm thấy.
- Kiểm tra package/import và signature.
- Xác nhận source hoặc dependency có mặt trong môi trường build.
- Xác nhận URL -link trỏ đúng gốc tài liệu và metadata file có mặt.
- Với build offline, kiểm tra URL1/URL2 của -linkoffline.

Doclint giúp phát hiện nhiều lỗi trong documentation comment và reference, nhưng không thay thế việc kiểm tra mọi URL trên internet. Một file metadata có thể cho Javadoc biết package tồn tại trong bộ tài liệu mà không bảo đảm máy chủ đang phục vụ mọi trang HTML đúng như dự kiến. Với link web quan trọng, nên có bước kiểm tra URL hoặc link checker trong CI.

### Xem kết quả HTML

Sau khi tạo tài liệu, mở trang class:

~~~text
docs/com/example/api/NameFormatter.html
~~~

Kiểm tra:

- Link nội bộ mở đúng class hoặc member.
- Link tới Java SE API mở đúng release.
- Link tới dependency mở đúng phiên bản thư viện.
- Nhãn link dễ hiểu khi đọc câu.
- Không có link trỏ tới file hoặc package đã bị đổi tên.
- Các trang tĩnh được tham chiếu qua {@docRoot} thực sự tồn tại.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Javadoc báo reference không tìm thấy | Sai tên class/member hoặc target không có trong source/classpath | Kiểm tra reference và môi trường phân giải |
| Link tới overload sai hoặc mơ hồ | Không chỉ rõ danh sách tham số | Ghi đầy đủ signature trong reference |
| Tên class hiển thị nhưng không có link ngoài | Chưa cấu hình -link/-linkoffline hoặc metadata không nhận diện package | Kiểm tra URL và element-list/package-list |
| -link báo không tìm thấy package-list/element-list | URL không trỏ tới thư mục gốc tài liệu hoặc metadata thiếu | Dùng đúng URL root hoặc -linkoffline với metadata local |
| Link external bị sai base path | Truyền URL tới trang class thay vì thư mục gốc | Truyền URL của directory chứa bộ Javadoc |
| Build CI không tạo được link ngoài | Môi trường build không truy cập internet | Cache metadata và dùng -linkoffline |
| Link tĩnh bị 404 | Trang HTML chưa được copy vào output hoặc relative path sai | Kiểm tra file đích và đường dẫn dùng {@docRoot} |
| HTML bị render sai | Ký tự đặc biệt chưa escape hoặc markup sai | Dùng HTML hợp lệ, {@code} hoặc {@literal} |
| Link text khó hiểu | Nhãn mặc định không mô tả đích đến | Thêm label có ý nghĩa hoặc dùng {@linkplain} |
| Javadoc phát warning dù source compile được | Documentation comment có lỗi độc lập với Java compiler | Chạy Javadoc với doclint và sửa warning |

## 14. Quy trình thiết lập link cho một dự án

1. Xác định class, method, field và package mà người đọc cần chuyển tới.
2. Dùng {@link} cho API identifier được nhắc trong câu.
3. Dùng {@linkplain} khi muốn nhãn là cụm từ tự nhiên.
4. Dùng @see cho tài liệu tham khảo liên quan ở cuối comment.
5. Đưa các package/class cùng project vào một lần chạy Javadoc để có link nội bộ.
6. Thêm -link cho bộ Javadoc ngoài có thể truy cập và có metadata.
7. Dùng -linkoffline nếu metadata được cache tại máy build hoặc mạng bị giới hạn.
8. Dùng {@docRoot} cho trang hướng dẫn tĩnh trong cùng output.
9. Chạy -Xdoclint:all và cân nhắc -Werror trong CI.
10. Mở HTML được tạo, kiểm tra link nội bộ và link ngoài quan trọng trước khi phát hành.

## 15. Ghi nhớ

- {@link} tạo hyperlink nội tuyến tới module, package, class hoặc member.
- {@linkplain} tạo link tương tự nhưng hiển thị nhãn bằng font văn bản thông thường.
- @see đưa reference vào phần See Also; có thể trỏ tới program element, URL hoặc văn bản không liên kết.
- Reference tới method overload nên ghi đầy đủ kiểu tham số; dùng tên đầy đủ khi có sự mơ hồ.
- Javadoc tự tạo link nội bộ khi target được đưa vào cùng bộ tài liệu.
- -link nối tới tài liệu ngoài có element-list hoặc package-list ở thư mục gốc.
- -linkoffline dùng URL đích và vị trí metadata riêng, phù hợp cho build offline.
- {@docRoot} giúp tạo đường dẫn tương đối tới trang tĩnh trong cùng bộ tài liệu.
- -Xdoclint:all giúp phát hiện lỗi tag, HTML và reference; -Werror có thể làm warning khiến build thất bại.
- Luôn kiểm tra HTML đầu ra và các URL quan trọng; link được tạo không bảo đảm trang bên ngoài luôn tồn tại.

## Tài liệu tham khảo chính thức

- [Documentation Comment Specification — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html)
- [The javadoc Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html)
- [How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html)
- [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/)