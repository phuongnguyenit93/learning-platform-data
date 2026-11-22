# Doclint và sửa lỗi liên kết, mô tả tham số trong Java 17

## 1. DocLint giúp kiểm tra tài liệu API như thế nào?

Javadoc không chỉ chuyển comment thành trang HTML. Khi tạo tài liệu, công cụ còn phân tích cấu trúc comment, tag, tham chiếu tới class/method và một phần cú pháp HTML để phát hiện lỗi có thể làm tài liệu khó đọc hoặc liên kết không hoạt động.

Trong JDK 17, cơ chế kiểm tra này được gọi là **DocLint**. Nó có thể phát hiện các vấn đề như:

- Tham chiếu trong `{@link ...}` không trỏ tới một phần tử có thể phân giải.
- `@param` dùng tên tham số không tồn tại trong khai báo.
- Thiếu mô tả hoặc tag tài liệu theo nhóm kiểm tra được bật.
- Tag Javadoc đặt sai vị trí hoặc có cú pháp không hợp lệ.
- HTML trong comment không hợp lệ hoặc có vấn đề về khả năng truy cập.
- Thẻ và nội dung tài liệu không khớp với khai báo method/class.

DocLint giúp phát hiện lỗi cấu trúc trong tài liệu API ngay trong quy trình build. Nó không đánh giá liệu lời giải thích có đúng về nghiệp vụ, có đủ dễ hiểu hay có phản ánh đúng hành vi runtime hay không. Người viết vẫn phải bảo đảm nội dung mô tả chính xác.

Trong Java 17, hãy dùng `javadoc` đi kèm JDK và cấu hình DocLint phù hợp với mức nghiêm ngặt của dự án. Không cần plugin ngoài để bật các kiểm tra cơ bản.

Sau bài học, người học cần:

1. Hiểu DocLint kiểm tra những nhóm lỗi nào.
2. Chạy Javadoc với `-Xdoclint` và xử lý warning/error.
3. Viết `{@link}` và `@see` trỏ đúng tới class, method, constructor hoặc field.
4. Sửa liên kết tới method overload bằng chữ ký chính xác.
5. Viết `@param`, `@return`, `@throws` đầy đủ và khớp với khai báo.
6. Thiết lập liên kết tới Javadoc bên ngoài bằng `-link` hoặc `-linkoffline`.
7. Đưa kiểm tra tài liệu vào quy trình build/CI mà không che giấu warning.

## 2. DocLint trong JDK 17

### 2.1. DocLint được chạy khi tạo Javadoc

Ví dụ đơn giản:

~~~bash
javadoc -d build/docs -Xdoclint:all -sourcepath src/main/java -subpackages com.example
~~~

Lệnh trên yêu cầu Javadoc tạo tài liệu cho các package bên dưới `com.example` và bật tất cả nhóm kiểm tra DocLint. Nếu source tree có comment lỗi, Javadoc sẽ báo warning hoặc error kèm vị trí để người viết sửa.

DocLint là một phần của công cụ Javadoc. Nó không phải một thư viện runtime mà ứng dụng cần import vào source code.

### 2.2. Các nhóm kiểm tra

JDK 17 hỗ trợ các nhóm DocLint sau:

| Nhóm | Phạm vi |
|---|---|
| `accessibility` | Một số vấn đề về khả năng truy cập trong nội dung HTML/Javadoc |
| `html` | Cú pháp và cấu trúc HTML trong comment |
| `reference` | Tham chiếu tới symbol, class, member và tag liên quan |
| `syntax` | Cú pháp của Javadoc tag và inline tag |
| `missing` | Comment hoặc tag tài liệu bị thiếu |

Mặc định, Javadoc chạy các nhóm kiểm tra trừ nhóm `missing`. Muốn yêu cầu đầy đủ hơn, dùng:

~~~bash
javadoc -Xdoclint:all ...
~~~

Muốn tạm bỏ nhóm `missing` nhưng vẫn kiểm tra các nhóm còn lại:

~~~bash
javadoc -Xdoclint:all,-missing ...
~~~

Trong một số dự án có nhiều mã legacy, nhóm `missing` có thể tạo ra lượng warning lớn. Có thể bật từng bước để xử lý nợ tài liệu, nhưng không nên tắt toàn bộ DocLint chỉ để build im lặng.

### 2.3. Tắt DocLint

Tùy chọn:

~~~bash
javadoc -Xdoclint:none ...
~~~

tắt các kiểm tra DocLint. Đây không phải cách sửa lỗi. Chỉ dùng khi có lý do vận hành cụ thể và có phương án kiểm tra thay thế; với dự án mới hoặc API công khai, nên giữ kiểm tra bật.

### 2.4. Kiểm tra theo package

Javadoc có tùy chọn `-Xdoclint/package:` để giới hạn các kiểm tra DocLint theo package. Cú pháp nhóm và package cần theo đúng JDK 17:

~~~bash
javadoc -Xdoclint:all -Xdoclint/package:com.example.api ...
~~~

Khi áp dụng trên codebase lớn, có thể bắt đầu với package API công khai rồi mở rộng. Hãy giữ cấu hình nhất quán trong CI để kết quả không phụ thuộc vào máy lập trình viên.

## 3. Tạo Javadoc với cấu hình nghiêm ngặt

### 3.1. Ví dụ lệnh cơ bản

Với source tree:

~~~text
src/main/java/
  com/example/api/
    Calculator.java
    UserService.java
~~~

Chạy:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -sourcepath src/main/java \
  -Xdoclint:all \
  -subpackages com.example.api
~~~

Giải thích:

- `--release 17`: tạo tài liệu theo API/phiên bản Java mục tiêu 17.
- `-d build/docs`: thư mục chứa HTML được tạo.
- `-sourcepath`: nơi tìm source package.
- `-Xdoclint:all`: bật tất cả nhóm DocLint, bao gồm kiểm tra thiếu comment/tag.
- `-subpackages`: chọn package gốc và các package con cần tạo tài liệu.

Thư mục đích phải có quyền ghi. Nếu tài liệu được tạo trong build pipeline, nên xóa output cũ theo cơ chế build trước khi tạo lại để tránh giữ HTML cũ của class đã bị xóa.

### 3.2. Biến warning thành lỗi build

Javadoc hỗ trợ `-Werror` để build thất bại khi có warning:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -sourcepath src/main/java \
  -Xdoclint:all \
  -Werror \
  -subpackages com.example.api
~~~

Đây là cấu hình hữu ích cho CI khi dự án đã xử lý các warning hiện có. Nếu bật `-Werror` ngay trên một codebase có nhiều warning cũ, build có thể thất bại hàng loạt; hãy xử lý nợ tài liệu theo phạm vi rõ ràng rồi mới áp dụng chính sách nghiêm ngặt.

### 3.3. Dependency trên classpath hoặc module path

Nếu Javadoc cần phân giải kiểu từ dependency:

- Với dependency dạng classpath, cung cấp `-classpath`.
- Với dependency dạng module, cung cấp `--module-path` và các tùy chọn module tương ứng.

Ví dụ:

~~~bash
javadoc --release 17 \
  -classpath "lib/dependency.jar" \
  -d build/docs \
  -Xdoclint:all \
  -sourcepath src/main/java \
  -subpackages com.example
~~~

Nếu thiếu dependency, tham chiếu trong comment có thể không được phân giải dù tên class nhìn có vẻ đúng. Hãy xác nhận Javadoc đang chạy với đúng dependency graph của project.

## 4. Viết mô tả tham số bằng @param

### 4.1. Tên trong @param phải khớp khai báo

Ví dụ method:

~~~java
/**
 * Tìm hồ sơ theo mã định danh.
 *
 * @param userId mã định danh duy nhất của người dùng
 * @return hồ sơ nếu tìm thấy, hoặc {@code null} nếu không có
 */
public UserProfile findUser(String userId) {
    // ...
}
~~~

Tên `userId` trong `@param` phải khớp với tên tham số trong khai báo. Nếu đổi tên tham số thành `id` nhưng quên sửa Javadoc, DocLint có thể báo `@param` không tồn tại.

Sai:

~~~java
/**
 * Tìm hồ sơ.
 * @param userID mã người dùng
 */
public UserProfile findUser(String userId) {
    // ...
}
~~~

`userID` và `userId` là hai tên khác nhau. Java phân biệt chữ hoa/chữ thường; Javadoc cũng cần tên chính xác.

### 4.2. Mỗi tham số nên có mô tả có ý nghĩa

Tránh mô tả lặp lại tên tham số:

~~~java
/**
 * @param timeout timeout
 */
~~~

Mô tả tốt hơn cần nêu ý nghĩa, đơn vị, miền giá trị hoặc điều kiện:

~~~java
/**
 * @param timeout thời gian chờ tối đa, tính bằng milliseconds; giá trị
 *                {@code 0} có nghĩa là không giới hạn
 */
~~~

Không tự ghi một quy tắc như `0` có nghĩa vô hạn nếu API thực tế không quy định như vậy. Mô tả phải phản ánh đúng hợp đồng của method.

### 4.3. Generic type parameter dùng cú pháp có dấu ngoặc nhọn

Với class generic:

~~~java
/**
 * Bộ lưu trữ một giá trị có kiểu xác định.
 *
 * @param <T> kiểu của giá trị được lưu
 */
public final class Box<T> {
    // ...
}
~~~

Với generic method:

~~~java
/**
 * Trả về phần tử đầu tiên của danh sách.
 *
 * @param <T> kiểu phần tử trong danh sách
 * @param values danh sách cần đọc
 * @return phần tử đầu tiên
 * @throws IllegalArgumentException nếu danh sách rỗng
 */
public static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values is empty");
    }
    return values.get(0);
}
~~~

`@param <T>` mô tả type parameter; `@param values` mô tả tham số method. Không bỏ dấu `<` và `>` trong tag dành cho generic type parameter.

### 4.4. Constructor cũng dùng @param

~~~java
/**
 * Tạo một client có giới hạn thời gian chờ.
 *
 * @param endpoint địa chỉ dịch vụ cần kết nối
 * @param timeout thời gian chờ tối đa cho mỗi request
 * @throws NullPointerException nếu {@code endpoint} hoặc {@code timeout} là null
 * @throws IllegalArgumentException nếu timeout không dương
 */
public ApiClient(URI endpoint, Duration timeout) {
    // ...
}
~~~

Constructor không có `@return`, vì nó không trả về một giá trị theo cú pháp method.

## 5. Viết @return và @throws đúng hợp đồng

### 5.1. @return cho method có kết quả

~~~java
/**
 * Tính tổng hai số nguyên.
 *
 * @param left toán hạng thứ nhất
 * @param right toán hạng thứ hai
 * @return tổng của hai toán hạng
 */
public int add(int left, int right) {
    return left + right;
}
~~~

Mô tả `@return` nên nói rõ kết quả có ý nghĩa gì, không chỉ viết “giá trị trả về”. Với method trả collection hoặc Optional, nêu rõ trường hợp rỗng/null và liệu collection có thể sửa đổi được hay không nếu đó là một phần của hợp đồng.

### 5.2. Không thêm @return cho method void

Sai:

~~~java
/**
 * Ghi thông báo.
 *
 * @return không có gì
 */
public void log(String message) {
    // ...
}
~~~

Method `void` không có giá trị trả về; hãy bỏ `@return`. Nếu method có side effect quan trọng, mô tả nó trong phần nội dung comment.

### 5.3. @throws mô tả điều kiện phát sinh

~~~java
/**
 * Chia hai số nguyên.
 *
 * @param dividend số bị chia
 * @param divisor số chia
 * @return thương nguyên của phép chia
 * @throws ArithmeticException nếu {@code divisor} bằng zero
 */
public int divide(int dividend, int divisor) {
    return dividend / divisor;
}
~~~

`@throws` nên nêu điều kiện thực tế dẫn tới exception. Có thể tài liệu hóa cả unchecked exception dù nó không nằm trong `throws` clause, nếu đó là một phần quan trọng của hợp đồng API.

Không ghi một exception chỉ vì nó có thể xảy ra ở một implementation cụ thể nhưng không thuộc hợp đồng công khai, trừ khi người dùng API cần biết và hành vi đó được bảo đảm.

### 5.4. @throws và throws clause không phải một

- `throws IOException` trong khai báo là thành phần của chữ ký method và ảnh hưởng việc gọi/biên dịch.
- `@throws IOException` trong Javadoc giải thích trường hợp API phát sinh exception.

Hai phần nên nhất quán nhưng không thay thế nhau.

## 6. Sửa lỗi liên kết nội bộ bằng @link

### 6.1. Liên kết tới class hoặc interface

~~~java
/**
 * Bộ xử lý request dùng {@link java.net.http.HttpClient}.
 */
public final class RequestProcessor {
}
~~~

Nếu kiểu đã được import, có thể dùng tên đơn giản trong reference khi Javadoc phân giải được:

~~~java
import java.net.http.HttpClient;

/**
 * Bộ xử lý request dùng {@link HttpClient}.
 */
~~~

Với tài liệu API công khai, tên đầy đủ có thể làm rõ nguồn của kiểu và tránh nhầm với class cùng tên trong package khác.

### 6.2. Liên kết tới method của class hiện tại

~~~java
/**
 * Gọi {@link #connect()} trước khi gửi request.
 *
 * @see #close()
 */
public void send() {
    // ...
}
~~~

`#connect()` trỏ tới member của class hiện tại. Dùng `#` để chỉ member thay vì viết tên như một URL tự do.

### 6.3. Liên kết tới method của class khác

~~~java
/**
 * Dùng {@link java.time.Duration#ofSeconds(long)} để tạo timeout.
 */
public Duration timeout() {
    return Duration.ofSeconds(5);
}
~~~

Reference gồm kiểu sở hữu member, tên method và chữ ký tham số nếu cần phân biệt overload.

### 6.4. Liên kết tới overload cụ thể

Nếu một class có nhiều method cùng tên, hãy chỉ rõ kiểu tham số:

~~~java
/**
 * Xem thêm {@link String#substring(int, int)} để lấy một đoạn chuỗi.
 */
~~~

Nếu chỉ viết `{@link String#substring}`, Javadoc có thể không phân biệt được overload hoặc tạo liên kết không như ý. Với API có nhiều overload, dùng chữ ký đầy đủ để reference rõ ràng.

Các kiểu tham số trong reference cần được viết theo cú pháp Javadoc, dùng tên kiểu và package có thể phân giải được. Khi có ambiguity, dùng tên fully qualified.

### 6.5. Thêm nhãn hiển thị

~~~java
/**
 * Xem {@link java.util.Optional#orElse(Object) cách lấy giá trị mặc định}.
 */
~~~

Phần sau reference là nhãn hiển thị cho người đọc. Có thể dùng `{@linkplain ...}` nếu muốn nhãn hiển thị theo kiểu văn bản thông thường thay vì kiểu liên kết mặc định.

### 6.6. Liên kết tới field hoặc constructor

Ví dụ:

~~~java
/**
 * Giá trị mặc định được lưu trong {@link #DEFAULT_TIMEOUT}.
 *
 * @see #ApiClient(URI, Duration)
 */
~~~

Với constructor, dùng tên class và danh sách tham số. Với field, dùng tên field; nếu class có field trùng tên ở nhiều context, ghi rõ class sở hữu.

## 7. Sử dụng @see và các inline tag liên quan

### 7.1. @see

`@see` tạo mục tham khảo ở phần cuối trang Javadoc:

~~~java
/**
 * Đọc cấu hình từ tệp UTF-8.
 *
 * @see java.nio.file.Files#readString(java.nio.file.Path, java.nio.charset.Charset)
 */
~~~

Dùng `@see` khi muốn người đọc tìm API hoặc tài liệu liên quan nhưng không cần chèn liên kết ngay trong đoạn văn.

### 7.2. {@link} và {@linkplain}

- `{@link ...}` chèn liên kết ngay trong câu và hiển thị theo kiểu code.
- `{@linkplain ...}` chèn liên kết với nhãn văn bản thông thường.

Ví dụ:

~~~java
/**
 * Dùng {@link List#size()} để lấy kích thước và
 * {@linkplain java.util.Collections tiện ích Collections} cho thao tác trên collection.
 */
~~~

### 7.3. {@code} và {@literal}

Dùng `{@code ...}` cho tên biến, biểu thức hoặc đoạn code ngắn:

~~~java
/**
 * Giá trị mặc định là {@code Duration.ofSeconds(5)}.
 */
~~~

Dùng `{@literal ...}` khi muốn hiển thị văn bản nguyên dạng mà không xử lý như HTML/Javadoc markup. Ví dụ:

~~~java
/**
 * Biểu thức phải có dạng {@literal x < y}.
 */
~~~

Không dùng `<` hoặc `>` thô trong HTML nếu chúng có thể bị hiểu là tag. Với code dài nhiều dòng, có thể dùng:

~~~java
/**
 * <pre>{@code
 * var client = HttpClient.newHttpClient();
 * var response = client.send(request, BodyHandlers.ofString());
 * }</pre>
 */
~~~

### 7.4. {@inheritDoc}

Với override, có thể kế thừa phần mô tả từ method cha/interface:

~~~java
/**
 * {@inheritDoc}
 */
@Override
public void close() {
    // ...
}
~~~

`{@inheritDoc}` hữu ích khi hợp đồng đã được mô tả đầy đủ ở API cha. Nếu implementation có điều kiện hoặc hành vi bổ sung, hãy viết thêm phần riêng thay vì chỉ kế thừa một cách máy móc.

## 8. Sửa lỗi HTML trong Javadoc

DocLint có nhóm kiểm tra HTML. Comment Javadoc được chuyển thành HTML, vì vậy cần viết markup đúng và có cấu trúc rõ ràng.

### 8.1. Đóng tag và lồng tag hợp lệ

Sai:

~~~java
/**
 * Các bước:
 * <ul>
 *   <li>Khởi tạo
 *   <li>Thực thi
 * </ul>
 */
~~~

Đúng:

~~~java
/**
 * Các bước:
 * <ul>
 *   <li>Khởi tạo</li>
 *   <li>Thực thi</li>
 * </ul>
 */
~~~

HTML hiện đại cho phép một số tag bỏ thẻ đóng theo ngữ pháp HTML, nhưng viết cấu trúc đầy đủ giúp comment dễ đọc và tránh các lỗi markup không cần thiết. Với tag void như `<br>` hoặc `<img>`, tuân theo cú pháp HTML được Javadoc hỗ trợ.

### 8.2. Không dùng tag HTML chỉ để định dạng tùy tiện

Ưu tiên Markdown-like Javadoc tag/HTML đơn giản được Javadoc hỗ trợ:

- `<p>` cho đoạn văn.
- `<ul>` và `<ol>` cho danh sách.
- `<code>` hoặc `{@code ...}` cho code.
- `<pre>{@code ...}</pre>` cho code block.
- `<table>`, `<tr>`, `<th>`, `<td>` cho bảng khi thực sự cần.

Tránh tag không chuẩn, thuộc tính lỗi thời hoặc markup phụ thuộc trình duyệt cụ thể. DocLint có thể phát hiện nhiều vấn đề nhưng không bảo đảm mọi HTML tùy chỉnh đều hiển thị giống nhau trên mọi công cụ.

### 8.3. Alt text cho hình ảnh

Nếu Javadoc có hình ảnh, cung cấp văn bản thay thế có ý nghĩa:

~~~java
/**
 * <img src="diagram.png" alt="Sơ đồ luồng xử lý request">
 */
~~~

Alt text giúp người dùng trình đọc màn hình hiểu nội dung hình và hỗ trợ nhóm kiểm tra accessibility.

### 8.4. Tránh HTML escape sai

Nếu cần hiển thị ký tự đặc biệt, dùng inline tag phù hợp:

~~~java
/**
 * Dùng {@code a < b} để so sánh hai giá trị.
 */
~~~

Hoặc `{@literal ...}` khi muốn giữ nguyên ký tự. Không đặt một đoạn HTML chưa đóng trong comment rồi kỳ vọng Javadoc tự sửa.

## 9. Liên kết tới Javadoc bên ngoài

### 9.1. Tùy chọn -link

Nếu tài liệu tham chiếu tới thư viện bên ngoài, Javadoc có thể tạo hyperlink tới site tài liệu của thư viện bằng `-link`:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -Xdoclint:all \
  -link https://docs.oracle.com/en/java/javase/17/docs/api/ \
  -sourcepath src/main/java \
  -subpackages com.example
~~~

URL phải là gốc của bộ Javadoc bên ngoài có metadata package/module list phù hợp. Javadoc dùng metadata đó để tạo đường dẫn tới type và member tương ứng.

### 9.2. Tùy chọn -linkoffline

Khi môi trường build không truy cập mạng, có thể dùng `-linkoffline`:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -Xdoclint:all \
  -linkoffline https://library.example/docs/api/ /opt/javadoc/library-api \
  -sourcepath src/main/java \
  -subpackages com.example
~~~

Tham số thứ nhất là URL sẽ được dùng trong hyperlink được tạo. Tham số thứ hai là vị trí local chứa metadata `element-list` hoặc `package-list` của bộ Javadoc bên ngoài. Đường dẫn local cần tồn tại và đúng cấu trúc mà Javadoc mong đợi.

### 9.3. Kiểm tra link ngoài

`-link` giúp Javadoc biết cách tạo hyperlink tới API bên ngoài. Nó không thay thế việc xác nhận website đích còn hoạt động, nội dung đúng phiên bản hoặc anchor member vẫn tồn tại sau khi thư viện nâng cấp.

Khi cập nhật dependency:

1. Cập nhật phiên bản URL tài liệu tương ứng.
2. Kiểm tra package/module metadata.
3. Tạo Javadoc lại.
4. Mở một số liên kết được sinh để xác nhận target.
5. Kiểm tra riêng các URL tự viết trong comment.

Không trỏ tài liệu Java 17 sang một phiên bản JDK khác chỉ vì URL ngắn hơn. Dùng phiên bản tài liệu khớp với API mà dự án biên dịch.

## 10. Các lỗi DocLint thường gặp và cách sửa

### 10.1. `reference not found`

Ví dụ:

~~~java
/**
 * Xem {@link #connectNow()}.
 */
public void connect() {
}
~~~

Không có member `connectNow()` trong class hiện tại nên reference không phân giải được.

**Cách sửa:** kiểm tra tên member, class sở hữu, chữ ký overload và dependency path. Nếu muốn dẫn tới một URL bên ngoài, dùng cú pháp HTML link hoặc Javadoc reference đúng thay vì giả lập tên member không tồn tại.

### 10.2. `@param name not found`

Ví dụ:

~~~java
/**
 * @param userID mã người dùng
 */
public void load(String userId) {
}
~~~

**Cách sửa:** đổi `userID` thành `userId`, hoặc đổi tên tag theo đúng khai báo nếu chữ ký method đã thay đổi.

### 10.3. Thiếu mô tả tham số

Tag có tên nhưng phần mô tả rỗng hoặc không đủ ý nghĩa làm tài liệu kém chất lượng và có thể bị nhóm missing phát hiện tùy dạng lỗi:

~~~java
/**
 * @param limit
 */
~~~

Sửa thành:

~~~java
/**
 * @param limit số phần tử tối đa cần trả về; phải lớn hơn zero
 */
~~~

Nếu `limit` cho phép zero hoặc số âm với ý nghĩa riêng, hãy mô tả đúng quy tắc thực tế.

### 10.4. Dùng @param cho type parameter sai cú pháp

Sai:

~~~java
/**
 * @param T kiểu phần tử
 */
class Store<T> {
}
~~~

Đúng:

~~~java
/**
 * @param <T> kiểu phần tử được lưu
 */
class Store<T> {
}
~~~

### 10.5. @return trên method void

Xóa `@return` khỏi method `void`. Mô tả side effect trong phần văn bản đầu comment.

### 10.6. Link tới overload không rõ

Nếu method có nhiều overload, hãy nêu chữ ký:

~~~java
/**
 * Xem {@link String#substring(int, int)}.
 */
~~~

Không dựa vào một reference ngắn có thể khớp nhiều method.

### 10.7. HTML tag không đóng hoặc lồng sai

Kiểm tra tag mở/đóng, thứ tự lồng và ký tự đặc biệt. Dùng code inline tag khi muốn hiển thị code thay vì chèn HTML thô.

### 10.8. External link không có metadata

Nếu Javadoc không tìm được package list/element list, kiểm tra URL gốc, phiên bản tài liệu và tham số `-link`/`-linkoffline`. Với build offline, cung cấp metadata local hợp lệ.

### 10.9. Warning missing xuất hiện quá nhiều

Nếu bật `-Xdoclint:all` trên codebase cũ, nhiều public member có thể chưa có comment hoặc tag. Hãy lập kế hoạch bổ sung tài liệu theo package/API công khai; không nên xóa tag hoặc tắt toàn bộ DocLint để che vấn đề.

## 11. Ví dụ hoàn chỉnh: sửa Javadoc cho một API

### 11.1. Phiên bản có lỗi

~~~java
package com.example.api;

import java.time.Duration;
import java.net.URI;

/**
 * Client cho dịch vụ.
 * <p>
 * Xem {@link #sendRequest()} để gửi.
 */
public final class ApiClient {
    /**
     * Tạo client.
     * @param url địa chỉ
     * @param timeout
     * @return client
     */
    public ApiClient(URI endpoint, Duration timeout) {
    }

    /**
     * Gửi request.
     * @param body nội dung
     * @return
     */
    public String send(String body) {
        return body;
    }
}
~~~

Các vấn đề:

- Link `#sendRequest()` không tồn tại.
- `@param url` không khớp tham số `endpoint`.
- `@param timeout` thiếu mô tả.
- Constructor không có giá trị trả về nên không dùng `@return`.
- `@return` của `send` chưa mô tả nội dung.
- Mô tả method còn quá chung chung.

### 11.2. Phiên bản đã sửa

~~~java
package com.example.api;

import java.net.URI;
import java.time.Duration;

/**
 * Client gửi request văn bản tới một dịch vụ HTTP.
 *
 * <p>Client sử dụng endpoint được cung cấp khi khởi tạo và giới hạn
 * thời gian chờ theo cấu hình. Xem thêm {@link java.net.http.HttpClient}
 * để biết API HTTP cấp thấp của Java.
 */
public final class ApiClient {

    /**
     * Tạo client cho endpoint đã chỉ định.
     *
     * @param endpoint URI gốc của dịch vụ; không được là {@code null}
     * @param timeout thời gian chờ tối đa cho một request; phải dương
     * @throws NullPointerException nếu endpoint hoặc timeout là {@code null}
     * @throws IllegalArgumentException nếu timeout không dương
     */
    public ApiClient(URI endpoint, Duration timeout) {
    }

    /**
     * Gửi nội dung văn bản tới dịch vụ.
     *
     * @param body nội dung request được gửi; không được là {@code null}
     * @return nội dung response dưới dạng chuỗi
     * @throws NullPointerException nếu body là {@code null}
     * @throws java.io.IOException nếu xảy ra lỗi I/O khi gửi hoặc đọc response
     * @throws InterruptedException nếu thread đang chờ bị interrupt
     * @see #ApiClient(URI, Duration)
     */
    public String send(String body)
            throws java.io.IOException, InterruptedException {
        return body;
    }
}
~~~

Ví dụ này minh họa cách viết comment khớp với chữ ký và tham chiếu thật. Trong một implementation thực tế, exception và quy tắc null phải phản ánh đúng code; không sao chép mô tả mẫu nếu hành vi của method khác.

### 11.3. Chạy DocLint

Với source tree đặt tại `src/main/java/com/example/api/ApiClient.java`:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -sourcepath src/main/java \
  -Xdoclint:all \
  -Werror \
  com.example.api
~~~

Nếu dùng `-subpackages`, có thể tạo tài liệu cho toàn bộ package con. Khi Javadoc báo lỗi, đọc file và số dòng, sửa comment gốc rồi chạy lại lệnh. Không sửa HTML sinh ra trong `build/docs`; lần tạo tiếp theo sẽ ghi đè output từ source.

## 12. Tổ chức Javadoc trong dự án module

### 12.1. Tài liệu package

Có thể dùng `package-info.java` để mô tả package:

~~~java
/**
 * API công khai cho việc gửi và nhận request.
 *
 * <p>Các kiểu trong package này được thiết kế để ứng dụng gọi từ module khác.
 */
package com.example.api;
~~~

### 12.2. Tài liệu module

Với dự án module hóa, có thể đặt mô tả module trong `module-info.java`:

~~~java
/**
 * Module cung cấp API gửi request tới dịch vụ.
 */
module com.example.client {
    requires java.net.http;
    exports com.example.api;
}
~~~

Javadoc của module giúp người dùng hiểu module export package nào và cần dependency module nào. Mô tả tài liệu nên khớp với `requires`, `exports` và API thật.

### 12.3. Không nhầm tài liệu package với tài liệu member

`package-info.java` mô tả phạm vi package; nó không thay thế comment của public class, constructor và method. API công khai vẫn cần mô tả tham số, kết quả và exception tại member tương ứng.

## 13. Tích hợp DocLint vào build và CI

### 13.1. Nguyên tắc

Một pipeline tài liệu tốt nên:

1. Dùng cùng JDK 17 với môi trường mục tiêu.
2. Tạo Javadoc từ source của phiên bản đang build.
3. Bật các nhóm DocLint đã thống nhất.
4. Thất bại khi có warning nếu dự án đã đạt ngưỡng chất lượng.
5. Giữ output trong thư mục build, không commit HTML sinh ra trừ khi dự án có chủ đích xuất bản tài liệu tĩnh.
6. Lưu log Javadoc để developer tìm đúng dòng cần sửa.

### 13.2. Chạy từ terminal

Lệnh ví dụ:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -sourcepath src/main/java \
  -Xdoclint:all \
  -Werror \
  -subpackages com.example
~~~

Trong PowerShell, có thể dùng dấu backtick để xuống dòng hoặc đặt toàn bộ lệnh trên một dòng. Hãy bảo đảm đường dẫn source và package gốc đúng với cấu trúc dự án.

### 13.3. Maven hoặc Gradle

Với Maven/Gradle, cấu hình Javadoc task/plugin để truyền cùng các tùy chọn `-Xdoclint:all` và `-Werror` thay vì để mỗi developer chạy một lệnh khác nhau. Cú pháp cấu hình phụ thuộc phiên bản plugin/build tool; kiểm tra tài liệu plugin đang được dự án khóa phiên bản.

Không thêm một plugin hoặc task tùy tiện chỉ để che warning. Mục tiêu là có một lệnh build tái lập, cùng JDK và cùng cấu hình cho local lẫn CI.

### 13.4. Xử lý nợ tài liệu theo giai đoạn

Nếu codebase có nhiều public API chưa có Javadoc:

- Bắt đầu với package mới hoặc API thường xuyên thay đổi.
- Sửa link và tag sai trước vì chúng có thể làm người đọc hiểu nhầm.
- Bổ sung mô tả tham số, return và throws.
- Mở rộng phạm vi `missing` theo từng package.
- Khi warning đã được xử lý, bật `-Werror` để ngăn lỗi quay lại.

Không nên đặt `-Xdoclint:none` lâu dài chỉ vì lượng warning ban đầu lớn.

## 14. Những điều DocLint không kiểm tra thay bạn

DocLint là kiểm tra cấu trúc tài liệu, không phải kiểm chứng nội dung. Nó không thể bảo đảm:

- Mô tả thuật toán đúng với implementation.
- Mô tả timeout hoặc đơn vị đo không sai.
- Điều kiện `@throws` phản ánh mọi đường đi runtime.
- Ví dụ code có kết quả đúng hoặc compile được trong mọi ngữ cảnh.
- Liên kết tới website bên ngoài sẽ luôn còn hoạt động.
- Nội dung tài liệu không mâu thuẫn với tài liệu khác.
- Mô tả API đáp ứng nhu cầu của người dùng.

Vì vậy, hãy review nội dung cùng source code, chạy ví dụ quan trọng và kiểm tra HTML sinh ra. DocLint phát hiện lỗi có thể máy kiểm tra được; chất lượng giải thích vẫn cần người viết và reviewer.

## 15. Bài tập thực hành

### Bài 1 — Bật DocLint

Tạo Javadoc cho một package Java 17 bằng:

~~~bash
javadoc --release 17 -Xdoclint:all -d build/docs -sourcepath src/main/java -subpackages com.example
~~~

Ghi lại warning/error và phân loại chúng theo nhóm `html`, `reference`, `syntax`, `accessibility` hoặc `missing`.

### Bài 2 — Sửa @param

Tạo method có hai tham số `userId` và `timeout`. Viết một tag `@param` sai chữ hoa/thường, chạy DocLint, sau đó sửa đúng tên và thêm mô tả có ý nghĩa cho từng tham số.

### Bài 3 — Generic type parameter

Viết class `Repository<T>` và method `<R> R map(...)`. Bổ sung `@param <T>`, `@param <R>` và tag cho các tham số thường. Giải thích khác biệt giữa hai loại tag.

### Bài 4 — Link tới overload

Tạo hai overload `find(String)` và `find(String, boolean)`. Viết hai `{@link}` trỏ đúng từng overload. Thử bỏ chữ ký tham số và quan sát kết quả Javadoc.

### Bài 5 — Link external

Tạo tài liệu có tham chiếu tới một API thư viện bên ngoài. Cấu hình `-link` tới Javadoc của dependency; sau đó thử `-linkoffline` với metadata local trong môi trường không có mạng.

### Bài 6 — @return và @throws

Viết một method có giá trị trả về và một method `void`. Thêm tag hợp lệ cho từng method; thử thêm `@return` vào method `void` rồi sửa theo cảnh báo.

### Bài 7 — CI nghiêm ngặt

Chạy Javadoc với `-Xdoclint:all -Werror`. Sửa warning trong package mẫu cho đến khi build thành công. Ghi lại vì sao chỉ tắt DocLint không được xem là hoàn thành bài.

## 16. Tiêu chí hoàn thành

Người học nắm vững bài khi có thể:

1. Giải thích vai trò và giới hạn của DocLint trong JDK 17.
2. Kể tên các nhóm `accessibility`, `html`, `reference`, `syntax`, `missing`.
3. Chạy Javadoc với `-Xdoclint:all` và hiểu tác dụng của `-Werror`.
4. Sửa `reference not found` bằng cách kiểm tra class, member và chữ ký overload.
5. Viết `@param` đúng tên và mô tả cả tham số thông thường lẫn generic type parameter.
6. Viết `@return` và `@throws` khớp hợp đồng method.
7. Dùng `{@link}`, `{@linkplain}`, `{@code}`, `{@literal}`, `{@inheritDoc}` và `@see` đúng mục đích.
8. Sửa HTML/Javadoc markup và thêm alt text khi có hình.
9. Cấu hình `-link` hoặc `-linkoffline` cho tài liệu API bên ngoài.
10. Tích hợp DocLint vào build/CI và không coi việc tắt kiểm tra là sửa lỗi.

## 17. Tài liệu chính thức

- [Java SE 17 Javadoc Tool Guide](https://docs.oracle.com/en/java/javase/17/javadoc/): hướng dẫn tạo tài liệu và các tùy chọn Javadoc.
- [Java SE 17 Javadoc Tool — DocLint](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): cú pháp `-Xdoclint`, nhóm kiểm tra và các tùy chọn liên quan.
- [Java SE 17 Javadoc Tags](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html): cú pháp comment, block tags, inline tags và reference.
- [Java SE 17 Javadoc Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html#references): quy tắc tham chiếu tới program elements.
- [Java SE 17 man page — javadoc](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): `-link`, `-linkoffline`, `-Werror` và các tùy chọn command line.

**Ghi nhớ:** DocLint phát hiện lỗi cú pháp, HTML, tham chiếu và tag trong tài liệu Javadoc. Muốn sửa lỗi link, hãy xác định đúng class/member và chữ ký overload; muốn sửa mô tả tham số, hãy khớp chính xác tên khai báo và giải thích ý nghĩa thực tế. Bật `-Xdoclint:all` trong build, dùng `-Werror` khi dự án đã sẵn sàng, và vẫn review nội dung vì DocLint không xác nhận tính đúng đắn của lời giải thích.
