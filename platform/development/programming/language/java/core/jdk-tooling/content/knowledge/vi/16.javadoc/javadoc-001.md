# Lệnh javadoc trong Java

**`javadoc`** là công cụ dòng lệnh đi kèm JDK, dùng để đọc tài liệu trong mã nguồn Java và tạo tài liệu API dưới dạng HTML. Công cụ phân tích các *documentation comment* (doc comment), tên kiểu, method, field, package và module, sau đó tạo các trang có liên kết để lập trình viên tra cứu.

Javadoc giúp người viết thư viện mô tả cách dùng API, tham số, giá trị trả về, ngoại lệ, phiên bản và các lưu ý tương thích. Người sử dụng thư viện có thể đọc tài liệu mà không cần mở mã nguồn triển khai.

## 1. Javadoc dùng để làm gì?

Khi xây dựng một thư viện hoặc ứng dụng có API dùng chung, chỉ có tên class và method thường chưa đủ để người khác hiểu cách sử dụng. Javadoc giúp trả lời các câu hỏi:

- Class hoặc interface này giải quyết vấn đề gì?
- Method nhận tham số nào và mỗi tham số có ý nghĩa gì?
- Method trả về giá trị gì?
- Trường hợp nào có thể phát sinh exception?
- API xuất hiện từ phiên bản nào?
- API có bị deprecated hoặc có lựa chọn thay thế không?
- Có quy tắc, giới hạn hoặc lưu ý về thread safety, hiệu năng hay quyền sở hữu dữ liệu không?

Ví dụ một khai báo method:

```java
public int divide(int dividend, int divisor)
        throws ArithmeticException
```

Javadoc có thể giải thích ý nghĩa của `dividend`, `divisor`, kết quả trả về và điều kiện phát sinh `ArithmeticException`.

Javadoc thường được dùng để:

- Tạo tài liệu cho thư viện và SDK.
- Công bố API nội bộ hoặc API cho khách hàng.
- Tạo tài liệu tham khảo cho dự án Java.
- Kiểm tra chất lượng comment và liên kết tới các kiểu/method.
- Duy trì tài liệu nhất quán với mã nguồn khi API thay đổi.

## 2. Kiểm tra và gọi lệnh javadoc

`javadoc` là một công cụ của JDK. Mở terminal và kiểm tra:

```bash
java -version
javac -version
javadoc --version
```

Nếu hệ thống không nhận diện `javadoc`:

- Kiểm tra máy đã cài JDK đầy đủ.
- Kiểm tra thư mục `bin` của JDK có trong `PATH`.
- Kiểm tra `JAVA_HOME` trỏ đến thư mục gốc của JDK.
- Mở terminal mới sau khi thay đổi biến môi trường.

Xem hướng dẫn tùy chọn:

```bash
javadoc --help
```

Javadoc không thay thế `javac`. Công cụ này tạo tài liệu từ mã nguồn và metadata có thể phân giải; nó không tạo các tệp bytecode `.class` như trình biên dịch.

## 3. Documentation comment là gì?

Javadoc nhận diện comment tài liệu bằng cú pháp bắt đầu với ba dấu sao:

```java
/**
 * Nội dung mô tả class, method hoặc field.
 */
```

Doc comment thường được đặt ngay trước khai báo mà nó mô tả.

Ví dụ:

```java
/**
 * Tính tổng hai số nguyên.
 *
 * @param left số nguyên thứ nhất
 * @param right số nguyên thứ hai
 * @return tổng của hai số
 */
public static int add(int left, int right) {
    return left + right;
}
```

Cần phân biệt:

| Loại comment | Cú pháp | Javadoc xử lý |
| --- | --- | --- |
| Documentation comment | `/** ... */` | Được dùng để tạo tài liệu |
| Block comment thông thường | `/* ... */` | Không được dùng làm doc comment |
| Line comment | `// ...` | Không được dùng làm doc comment |

Javadoc gắn doc comment với khai báo kế tiếp, ví dụ class, interface, constructor, method, field, package hoặc module. Đặt comment đúng vị trí giúp tài liệu được gắn với đúng thành phần API.

## 4. Cấu trúc một documentation comment

Một doc comment thường gồm ba phần:

1. **Mô tả chính:** giải thích ngắn gọn mục đích của thành phần.
2. **Phần mô tả chi tiết:** giải thích cách hoạt động, giới hạn, ví dụ hoặc lưu ý.
3. **Block tags:** thông tin có cấu trúc như tham số, giá trị trả về, exception và phiên bản.

Ví dụ:

```java
/**
 * Chia số nguyên bị chia cho số chia.
 *
 * <p>Phép chia sử dụng quy tắc chia số nguyên của Java,
 * vì vậy phần thập phân bị loại bỏ.</p>
 *
 * @param dividend số nguyên bị chia
 * @param divisor số nguyên chia
 * @return thương sau phép chia số nguyên
 * @throws ArithmeticException nếu divisor bằng 0
 * @since 1.0
 */
public static int divide(int dividend, int divisor) {
    return dividend / divisor;
}
```

Javadoc hỗ trợ nội dung HTML trong doc comment. Dùng các thẻ phù hợp như `<p>`, `<ul>`, `<li>`, `<pre>` và `<code>`; cần bảo đảm HTML hợp lệ và các thẻ được đóng đúng cách.

Với ký tự có ý nghĩa trong HTML, dùng entity hoặc inline tag. Ví dụ, viết `{@code List<String>}` để hiển thị mã generic mà không bị hiểu nhầm là thẻ HTML.

## 5. Các block tag thường dùng

Block tag bắt đầu bằng ký tự `@` và thường đặt ở cuối doc comment.

| Tag | Ý nghĩa | Áp dụng |
| --- | --- | --- |
| `@param` | Mô tả tham số | Method, constructor, type parameter |
| `@return` | Mô tả giá trị trả về | Method có giá trị trả về |
| `@throws` | Mô tả exception có thể phát sinh | Method, constructor |
| `@exception` | Tương đương `@throws` | Method, constructor |
| `@see` | Tham chiếu đến tài liệu hoặc thành phần liên quan | Nhiều loại khai báo |
| `@since` | Phiên bản API xuất hiện | Class, method, field, package |
| `@deprecated` | Đánh dấu API không còn được khuyến nghị | Class, method, field, constructor |
| `@author` | Tác giả | Class, interface, package |
| `@version` | Thông tin phiên bản | Class, interface |
| `@serial` | Tài liệu hóa field phục vụ serialization | Serializable class/field |
| `@serialField` | Tài liệu hóa field trong serializable class | Field |
| `@serialData` | Mô tả dữ liệu được ghi bởi phương thức serialization | Method liên quan |
| `@implSpec` | Mô tả yêu cầu về cách triển khai | API có hợp đồng triển khai |
| `@implNote` | Ghi chú về chi tiết triển khai | API có ghi chú triển khai |
| `@apiNote` | Ghi chú bổ sung dành cho người dùng API | API |

Ví dụ dùng `@param`, `@return` và `@throws`:

```java
/**
 * Tìm vị trí của một ký tự trong chuỗi.
 *
 * @param text chuỗi cần tìm
 * @param target ký tự cần tìm
 * @return vị trí đầu tiên, hoặc -1 nếu không tìm thấy
 * @throws NullPointerException nếu text là null
 */
public static int find(String text, char target) {
    return text.indexOf(target);
}
```

Với method generic, có thể mô tả type parameter bằng cú pháp `@param <T>`:

```java
/**
 * Trả về phần tử đầu tiên trong danh sách.
 *
 * @param <T> kiểu phần tử
 * @param values danh sách đầu vào
 * @return phần tử đầu tiên
 */
public static <T> T first(java.util.List<T> values) {
    return values.get(0);
}
```

Tên type parameter phải đặt trong dấu ngoặc nhọn trong tag, ví dụ `@param <T>`. Với method có nhiều tham số, mỗi tham số cần một mô tả tương ứng.

## 6. Các inline tag thường dùng

Inline tag nằm ngay trong câu mô tả và có dạng `{@tag ...}`.

| Inline tag | Công dụng |
| --- | --- |
| `{@code ...}` | Hiển thị nội dung như mã nguồn |
| `{@literal ...}` | Hiển thị nguyên văn mà không xử lý nội dung như HTML |
| `{@link ...}` | Tạo liên kết đến class, method hoặc thành phần API |
| `{@linkplain ...}` | Tạo liên kết với nhãn hiển thị dạng văn bản thường |
| `{@value ...}` | Hiển thị giá trị hằng số phù hợp |
| `{@inheritDoc}` | Kế thừa nội dung tài liệu từ khai báo cha |
| `{@docRoot}` | Đường dẫn tương đối đến thư mục gốc tài liệu |
| `{@index ...}` | Thêm thuật ngữ vào chỉ mục tìm kiếm |

Ví dụ:

```java
/**
 * Trả về số phần tử tối đa được xử lý.
 *
 * <p>Dùng {@code MAX_SIZE} để giới hạn dữ liệu đầu vào.
 * Xem thêm {@link #validate(int)} trước khi xử lý.</p>
 *
 * @return giới hạn phần tử
 */
public static int maxSize() {
    return MAX_SIZE;
}
```

`{@link #validate(int)}` tạo liên kết đến method trong cùng class. Có thể liên kết đến thành phần ở class khác bằng tên đầy đủ hoặc tên tương đối trong phạm vi phân giải của Javadoc.

Ví dụ dùng `{@literal}`:

```java
/**
 * Biểu thức có dạng {@literal x < y}.
 */
```

Nếu viết trực tiếp `<` trong HTML mà không escape, trình tạo tài liệu có thể hiểu nhầm đó là phần mở đầu của một thẻ HTML.

## 7. Viết tài liệu cho class, method và constructor

### Tài liệu cho class

Doc comment của class nên mô tả mục đích, vai trò, cách tạo và cách sử dụng class. Nếu có giới hạn về thread safety, mutable state hoặc tài nguyên, hãy nêu rõ.

```java
/**
 * Cung cấp các phép toán số nguyên cơ bản.
 *
 * <p>Lớp này chỉ chứa các phương thức tiện ích static.</p>
 *
 * @since 1.0
 */
public final class Calculator {
    // ...
}
```

### Tài liệu cho method

Method nên có mô tả hành vi, tham số, giá trị trả về và exception quan trọng.

```java
/**
 * Cộng hai số nguyên.
 *
 * @param left toán hạng thứ nhất
 * @param right toán hạng thứ hai
 * @return tổng của hai toán hạng
 */
public static int add(int left, int right) {
    return left + right;
}
```

Không thêm `@return` cho method `void`. Không thêm `@param` nếu method không có tham số. Mô tả exception cần phản ánh điều kiện thực tế mà API có thể phát sinh.

### Tài liệu cho constructor

Constructor nên mô tả trạng thái ban đầu của object và ý nghĩa tham số.

```java
/**
 * Tạo một bộ đếm bắt đầu từ giá trị chỉ định.
 *
 * @param initialValue giá trị ban đầu
 */
public Counter(int initialValue) {
    this.value = initialValue;
}
```

### Tài liệu cho field

Field public hoặc protected nên được mô tả nếu người dùng API cần hiểu ý nghĩa, đơn vị hoặc giới hạn của giá trị.

```java
/**
 * Số lần thử tối đa.
 */
public static final int MAX_RETRIES = 3;
```

## 8. Tài liệu cho package và module

Có thể đặt tài liệu ở cấp package bằng tệp **`package-info.java`**.

Ví dụ:

```java
/**
 * Cung cấp các tiện ích số học cho ứng dụng.
 *
 * <p>Các class trong package này hỗ trợ những phép toán
 * số nguyên cơ bản.</p>
 */
package com.example.math;
```

Javadoc dùng comment này để tạo trang mô tả package, thường là `package-summary.html`.

Với ứng dụng modular, có thể viết doc comment trước khai báo module trong `module-info.java`:

```java
/**
 * Cung cấp API tính toán cho các module khác.
 */
module com.example.math {
    exports com.example.math;
}
```

Tài liệu module mô tả mục đích module và quan hệ phụ thuộc. Khi tạo Javadoc cho module, cần dùng các tùy chọn module path hoặc module source path phù hợp.

## 9. Ví dụ hoàn chỉnh: tạo tài liệu cho một API

Ví dụ sau tạo package `com.example.math` với class `Calculator`, đồng thời có class `Main` để kiểm tra chương trình.

Cấu trúc thư mục:

```text
project/
  src/
    com/
      example/
        math/
          package-info.java
          Calculator.java
        app/
          package-info.java
          Main.java
  docs/
  out/
```

Tạo tệp **`src/com/example/math/package-info.java`**:

```java
/**
 * Cung cấp các tiện ích số học cho ứng dụng.
 *
 * <p>Package này minh họa cách viết tài liệu API bằng Javadoc.</p>
 */
package com.example.math;
```

Tạo tệp **`src/com/example/math/Calculator.java`**:

```java
package com.example.math;

/**
 * Cung cấp các phép toán số nguyên cơ bản.
 *
 * <p>Các phép toán sử dụng quy tắc số nguyên của Java.</p>
 *
 * @since 1.0
 */
public final class Calculator {

    private Calculator() {
    }

    /**
     * Cộng hai số nguyên.
     *
     * @param left toán hạng thứ nhất
     * @param right toán hạng thứ hai
     * @return tổng của hai số nguyên
     * @see #divide(int, int)
     * @since 1.0
     */
    public static int add(int left, int right) {
        return left + right;
    }

    /**
     * Chia số nguyên bị chia cho số chia.
     *
     * <p>Kết quả tuân theo phép chia số nguyên của Java,
     * phần thập phân bị loại bỏ về phía 0.</p>
     *
     * @param dividend số nguyên bị chia
     * @param divisor số nguyên chia
     * @return thương sau phép chia số nguyên
     * @throws ArithmeticException nếu divisor bằng 0
     * @since 1.0
     */
    public static int divide(int dividend, int divisor) {
        return dividend / divisor;
    }
}
```

Tạo tệp **`src/com/example/app/package-info.java`**:

```java
/**
 * Chứa chương trình minh họa cách sử dụng API số học.
 */
package com.example.app;
```

Tạo tệp **`src/com/example/app/Main.java`**:

```java
package com.example.app;

import com.example.math.Calculator;

/**
 * Chạy ví dụ sử dụng {@link Calculator}.
 */
public final class Main {

    private Main() {
    }

    /**
     * Điểm bắt đầu của chương trình.
     *
     * @param args đối số dòng lệnh
     */
    public static void main(String[] args) {
        System.out.println("sum=" + Calculator.add(7, 5));
        System.out.println("quotient=" + Calculator.divide(17, 5));
    }
}
```

### Bước 1: Tạo thư mục đầu ra

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force docs, out | Out-Null
```

**macOS/Linux:**

```bash
mkdir -p docs out
```

### Bước 2: Tạo tài liệu HTML bằng javadoc

Chạy tại thư mục gốc `project`:

```bash
javadoc -d docs -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -sourcepath src -subpackages com.example
```

Giải thích:

- `-d docs`: ghi tài liệu HTML vào thư mục `docs`.
- `-encoding UTF-8`: đọc mã nguồn và doc comment bằng UTF-8.
- `-docencoding UTF-8`: dùng UTF-8 cho tệp HTML được tạo.
- `-charset UTF-8`: khai báo charset trong tài liệu HTML.
- `-sourcepath src`: chỉ định thư mục gốc của mã nguồn.
- `-subpackages com.example`: tạo tài liệu cho package `com.example` và các package con.

Javadoc sẽ phân tích các package tìm được dưới `com.example`, gồm `com.example.math` và `com.example.app`.

### Bước 3: Kiểm tra tài liệu được tạo

Cấu trúc đầu ra có dạng:

```text
docs/
  index.html
  allclasses-index.html
  allpackages-index.html
  com/
    example/
      math/
        package-summary.html
        Calculator.html
      app/
        package-summary.html
        Main.html
```

Tên và một số tệp chỉ mục có thể thay đổi theo phiên bản JDK và standard doclet. Các trang quan trọng cần kiểm tra là trang class, package và trang chỉ mục.

Mở `docs/index.html` trong trình duyệt. Chọn package `com.example.math`, mở class `Calculator`, rồi kiểm tra mô tả class, method, tham số, giá trị trả về và exception.

### Bước 4: Biên dịch và chạy chương trình

Javadoc chỉ tạo tài liệu. Nếu muốn kiểm tra chương trình, biên dịch riêng bằng `javac`:

```bash
javac -d out -sourcepath src src/com/example/app/Main.java
```

Chạy:

```bash
java -cp out com.example.app.Main
```

Kết quả chính xác:

```text
sum=12
quotient=3
```

Ví dụ dùng phép chia số nguyên: `17 / 5` cho kết quả `3` vì phần thập phân bị loại bỏ về phía 0.

## 10. Các tùy chọn javadoc quan trọng

| Tùy chọn | Công dụng |
| --- | --- |
| `-d <directory>` | Thư mục lưu tài liệu được tạo |
| `-sourcepath <path>` | Nơi tìm mã nguồn Java |
| `-subpackages <packages>` | Tạo tài liệu cho package và package con |
| `-classpath` / `--class-path` | Nơi tìm class hoặc thư viện cần phân giải |
| `-private` | Bao gồm cả thành viên private |
| `-package` | Bao gồm thành viên package-private và các mức truy cập rộng hơn |
| `-protected` | Chỉ public và protected; đây là mức mặc định |
| `-public` | Chỉ public |
| `-author` | Đưa nội dung `@author` vào tài liệu |
| `-version` | Đưa nội dung `@version` vào tài liệu |
| `-encoding` | Encoding của mã nguồn đầu vào |
| `-docencoding` | Encoding của tệp HTML đầu ra |
| `-charset` | Charset được khai báo trong HTML |
| `-overview <file>` | Tệp HTML mô tả tổng quan tài liệu |
| `-link <url>` | Liên kết đến tài liệu API bên ngoài |
| `-tag` | Khai báo block tag tùy chỉnh |
| `-Xdoclint` | Kiểm tra cú pháp doc comment, HTML và tham chiếu |
| `-Werror` | Kết thúc với trạng thái lỗi nếu có warning |
| `-quiet` | Giảm thông báo trong quá trình tạo tài liệu |
| `-notimestamp` | Không ghi timestamp vào phần đầu trang được tạo |

Mức hiển thị mặc định là public và protected. Dùng `-private` khi cần tạo tài liệu nội bộ có cả thành viên private; không nên dùng mức này cho tài liệu API công khai nếu không muốn tiết lộ chi tiết triển khai.

Ví dụ tạo tài liệu bao gồm private member và thông tin author/version:

```bash
javadoc -d docs-internal -private -author -version -sourcepath src -subpackages com.example
```

## 11. Kiểm tra chất lượng tài liệu bằng doclint

Javadoc có thể kiểm tra doc comment để phát hiện một số vấn đề như:

- HTML sai cấu trúc hoặc thiếu thẻ đóng.
- Tham chiếu đến class, method hoặc field không tồn tại.
- Tag không hợp lệ hoặc dùng sai vị trí.
- Thiếu hoặc sai mô tả tham số và giá trị trả về trong các trường hợp được kiểm tra.
- Cú pháp doc comment không đúng.

Dùng:

```bash
javadoc -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example
```

Ý nghĩa:

- `-Xdoclint:all` yêu cầu kiểm tra tất cả nhóm doclint được hỗ trợ.
- `-Werror` yêu cầu quá trình tạo tài liệu thất bại nếu có warning.
- `-d docs` xác định thư mục đầu ra.

Có thể chỉ định nhóm kiểm tra cụ thể bằng `-Xdoclint:<group>`. Các nhóm thường gặp gồm:

| Nhóm | Kiểm tra |
| --- | --- |
| `accessibility` | Một số yêu cầu về khả năng truy cập trong nội dung HTML |
| `html` | Cú pháp và cấu trúc HTML |
| `reference` | Tham chiếu đến thành viên và kiểu |
| `syntax` | Cú pháp Javadoc và các tag |
| `missing` | Tài liệu còn thiếu theo phạm vi kiểm tra |

Ví dụ bỏ kiểm tra nhóm missing trong khi vẫn kiểm tra các nhóm còn lại:

```bash
javadoc -Xdoclint:all,-missing -d docs -sourcepath src -subpackages com.example
```

Không nên tắt toàn bộ doclint chỉ để làm biến mất warning. Hãy đọc chẩn đoán, sửa doc comment hoặc chọn ngoại lệ có chủ đích khi dự án có lý do rõ ràng.

## 12. Liên kết đến tài liệu API bên ngoài

Khi tài liệu của dự án tham chiếu đến API Java chuẩn, có thể dùng tùy chọn `-link` để tạo liên kết đến tài liệu JDK đã xuất bản.

Ví dụ với Java SE 17:

```bash
javadoc -d docs -sourcepath src -subpackages com.example -link https://docs.oracle.com/en/java/javase/17/docs/api/
```

Sau đó, các tham chiếu như `{@link java.util.List}` hoặc `{@link java.time.LocalDate}` có thể liên kết đến trang API tương ứng khi Javadoc phân giải được kiểu và tài liệu đích truy cập được.

Để liên kết tài liệu của thư viện bên thứ ba, dùng URL gốc tài liệu API của thư viện đó. Phiên bản tài liệu đích phải tương ứng với phiên bản dependency mà dự án hỗ trợ.

Nếu môi trường build không có mạng, có thể dùng cơ chế offline link với `-linkoffline` và bản tài liệu API đã tải về. Xem `javadoc --help` để biết cú pháp và cấu trúc package list/element list mà phiên bản JDK đang dùng yêu cầu.

## 13. Tạo tài liệu cho ứng dụng modular

Với module Java, Javadoc có thể đọc module source path và tạo tài liệu cho module được chỉ định.

Ví dụ cấu trúc:

```text
src/
  com.example.math/
    module-info.java
    com/example/math/
      package-info.java
      Calculator.java
```

Tệp `module-info.java`:

```java
/**
 * Cung cấp API số học.
 */
module com.example.math {
    exports com.example.math;
}
```

Tạo tài liệu:

```bash
javadoc --module-source-path src -d docs --module com.example.math
```

Trong đó:

- `--module-source-path src`: nơi chứa cây thư mục mã nguồn module.
- `--module com.example.math`: module cần tạo tài liệu.
- `-d docs`: thư mục đầu ra.

Với nhiều module, có thể chỉ định danh sách module theo cú pháp được JDK hỗ trợ. Module descriptor, package export và dependency cần hợp lệ để Javadoc phân giải được các tham chiếu.

Đối với tài liệu module công khai, hãy kiểm tra các package được export và API mà người dùng module có thể truy cập. Tài liệu nội bộ có thể cần mức hiển thị khác và cấu hình phù hợp.

## 14. Viết tài liệu cho API deprecated

Khi một API không còn được khuyến nghị, hãy đánh dấu bằng annotation `@Deprecated` và mô tả bằng tag `@deprecated`.

Ví dụ:

```java
/**
 * Trả về tên ở định dạng cũ.
 *
 * @deprecated Dùng {@link #displayName()} thay thế.
 */
@Deprecated(since = "2.0", forRemoval = false)
public String oldName() {
    return displayName();
}
```

Hai phần có vai trò khác nhau:

- `@Deprecated` là annotation trong mã nguồn để compiler và công cụ nhận biết API đã deprecated.
- `@deprecated` là block tag cung cấp lời giải thích trong tài liệu Javadoc.

Khi deprecated API, nên nêu lý do, phiên bản bắt đầu deprecated và phương án thay thế. Không nên xóa API ngay nếu thư viện cần duy trì tương thích ngược.

## 15. Tùy chỉnh tiêu đề và nội dung tài liệu

Có thể thêm trang tổng quan bằng `-overview`:

```bash
javadoc -d docs -overview overview.html -sourcepath src -subpackages com.example
```

Tệp overview thường chứa HTML giới thiệu thư viện, mục tiêu, hướng dẫn cài đặt hoặc ví dụ tổng quát.

Một số tùy chọn trình bày khác:

- `-doctitle`: tiêu đề chính của tài liệu.
- `-windowtitle`: tiêu đề cửa sổ hoặc tab trình duyệt.
- `-header`: nội dung header.
- `-footer`: nội dung footer.
- `-bottom`: nội dung ở phần cuối trang.
- `-use`: tạo trang mô tả nơi các kiểu được sử dụng.
- `-splitindex`: chia chỉ mục thành nhiều trang khi cần.

Ví dụ:

```bash
javadoc -d docs -doctitle "Calculator API" -windowtitle "Calculator API Reference" -sourcepath src -subpackages com.example
```

Các tùy chọn này tác động đến tài liệu HTML được tạo. Với dự án lớn, nên giữ cấu hình tiêu đề và nội dung tổng quan trong build script để mọi lần tạo tài liệu có cùng định dạng.

## 16. Tạo tài liệu trong Maven và Gradle

Trong dự án thực tế, không nên phải nhớ và chạy một lệnh Javadoc dài bằng tay mỗi lần phát hành. Build tool có thể tích hợp việc tạo tài liệu vào quy trình build.

### Maven

Dự án Maven có thể dùng Maven Javadoc Plugin. Ví dụ cấu hình plugin trong `pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.11.2</version>
        </plugin>
    </plugins>
</build>
```

Tạo tài liệu:

```bash
mvn javadoc:javadoc
```

Tạo Javadoc dạng JAR để phân phối cùng thư viện:

```bash
mvn javadoc:jar
```

Plugin có thể được cấu hình thêm encoding, doclint, source level, links và các tùy chọn Javadoc khác. Phiên bản plugin trong ví dụ là phiên bản cụ thể; dự án nên chọn phiên bản được kiểm thử và quản lý tập trung.

### Gradle

Với Gradle dùng Groovy DSL, Java plugin cung cấp tác vụ `javadoc`. Có thể cấu hình:

```groovy
tasks.named('javadoc', Javadoc) {
    options.encoding = 'UTF-8'
    options.docEncoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.addStringOption('Xdoclint:all', '-quiet')
}
```

Chạy:

```bash
./gradlew javadoc
```

Trên Windows:

```powershell
.\gradlew.bat javadoc
```

Tài liệu thường được tạo trong thư mục build của module, ví dụ `build/docs/javadoc`. Đường dẫn thực tế phụ thuộc cấu hình dự án.

Với build đa module, kiểm tra từng module có task Javadoc và dependency source tương ứng. Nếu muốn build thất bại khi có warning, cấu hình thêm tùy chọn `-Werror` theo API của phiên bản Gradle đang dùng.

## 17. Lỗi thường gặp khi chạy javadoc

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `javadoc` không được nhận diện | Chưa cài JDK hoặc `PATH` chưa có thư mục `bin` | Kiểm tra `JAVA_HOME` và `PATH` |
| Không tìm thấy package hoặc class | Sai source path, classpath hoặc tên package | Kiểm tra cấu trúc thư mục và các tùy chọn `-sourcepath`, `-classpath` |
| Trang package không có mô tả | Thiếu hoặc đặt sai `package-info.java` | Thêm doc comment trước khai báo package |
| Liên kết `{@link}` không được phân giải | Sai tên class/member hoặc thiếu dependency | Kiểm tra tên đầy đủ, chữ ký method và classpath/module path |
| Doclint báo HTML lỗi | Thẻ HTML sai cú pháp hoặc chưa đóng | Sửa HTML trong doc comment |
| Javadoc báo thiếu mô tả param | Tag `@param` thiếu hoặc tên tham số không khớp | Đối chiếu từng tag với khai báo method |
| Không thấy private member | Mức hiển thị mặc định là public/protected | Dùng `-private` cho tài liệu nội bộ |
| Không thấy author/version | Chưa bật tùy chọn tương ứng | Dùng `-author` hoặc `-version` |
| Tài liệu tiếng Việt bị lỗi dấu | Encoding đầu vào hoặc đầu ra không thống nhất | Dùng `-encoding UTF-8`, `-docencoding UTF-8`, `-charset UTF-8` |
| Build Javadoc thất bại do warning | Có warning và đang bật `-Werror` | Sửa warning hoặc điều chỉnh chính sách có chủ đích |

## 18. Thực hành tốt khi viết Javadoc

- Viết mô tả mục đích API trước khi liệt kê chi tiết triển khai.
- Mô tả hành vi quan sát được, không hứa hẹn những điều implementation không bảo đảm.
- Dùng `@param`, `@return` và `@throws` đúng với chữ ký và hành vi method.
- Dùng `{@link}` để kết nối các API liên quan.
- Ghi rõ đơn vị, miền giá trị, điều kiện biên và tác dụng phụ nếu chúng quan trọng.
- Nêu rõ thread safety, mutability và quyền sở hữu tài nguyên khi API có liên quan.
- Dùng `package-info.java` để mô tả mục đích package.
- Dùng `module-info.java` để mô tả module khi dự án dùng JPMS.
- Dùng UTF-8 thống nhất cho mã nguồn và tài liệu đầu ra.
- Chạy doclint trong CI để phát hiện comment lỗi trước khi phát hành.
- Tạo tài liệu từ đúng phiên bản mã nguồn chuẩn bị phát hành.
- Không đưa thông tin bí mật, thông tin cá nhân hoặc chi tiết nội bộ không nên công khai vào Javadoc được phân phối.

Javadoc công khai là một phần của hợp đồng sử dụng API. Khi hành vi method thay đổi, hãy cập nhật comment và ví dụ cùng lúc với mã nguồn.

## 19. Quy trình tạo tài liệu đề xuất

Một quy trình có thể lặp lại:

1. Viết doc comment cho public/protected API.
2. Bổ sung mô tả package trong `package-info.java` và module trong `module-info.java` nếu cần.
3. Kiểm tra block tag và inline tag có khớp khai báo.
4. Chạy Javadoc với `-sourcepath`, `-subpackages` hoặc tùy chọn module phù hợp.
5. Bật `-Xdoclint:all` để kiểm tra comment và HTML.
6. Dùng `-Werror` trong CI nếu chính sách yêu cầu không có warning.
7. Kiểm tra các trang class, method, package và liên kết ngoài.
8. Chạy `javac` và test riêng để xác nhận mã nguồn vẫn biên dịch và hoạt động.
9. Lưu hoặc đóng gói tài liệu cùng phiên bản artifact được phát hành.

## 20. Ghi nhớ

- `javadoc` là công cụ JDK tạo tài liệu API HTML từ doc comment trong mã nguồn Java.
- Documentation comment dùng cú pháp `/** ... */`.
- Block tag thường dùng gồm `@param`, `@return`, `@throws`, `@see`, `@since` và `@deprecated`.
- Inline tag thường dùng gồm `{@code}`, `{@literal}`, `{@link}`, `{@linkplain}` và `{@inheritDoc}`.
- Dùng `package-info.java` và `module-info.java` để mô tả package và module.
- Dùng `-d`, `-sourcepath`, `-subpackages` để xác định đầu ra và nguồn cần tạo tài liệu.
- Dùng `-private` khi cần tài liệu cả thành viên private.
- Dùng `-Xdoclint:all` và `-Werror` để kiểm soát chất lượng comment.
- Javadoc tạo tài liệu; `javac` biên dịch mã nguồn thành bytecode.

Khi sử dụng thành thạo `javadoc`, bạn có thể tạo tài liệu API nhất quán từ mã nguồn, giúp người dùng hiểu cách gọi class và method, đồng thời phát hiện sớm những comment hoặc tham chiếu chưa chính xác.
