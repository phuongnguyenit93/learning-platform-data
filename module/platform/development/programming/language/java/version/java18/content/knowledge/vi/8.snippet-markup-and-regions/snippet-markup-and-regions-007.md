# Tham chiếu method overload trong `target` của `@link` và kiểm tra liên kết được phân giải

## Mục tiêu bài học

Trong một snippet Javadoc, markup comment `@link` có thể biến tên method trong mã ví dụ thành liên kết tới tài liệu API. Khi một class có nhiều method cùng tên, chỉ ghi tên method thường không đủ để xác định chính xác đích. Cần thêm **danh sách kiểu tham số** vào thuộc tính `target`.

Cú pháp này được giới thiệu cùng `{@snippet}` trong Java 18 và vẫn được hỗ trợ trong các JDK hiện đại. Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`.

Sau khi học, bạn có thể:

- Phân biệt các overload có cùng tên bằng parameter list trong `target`.
- Viết reference đến method có tham số primitive, reference type, array và generic type.
- Hiểu vì sao tên tham số và kiểu trả về không được đặt trong reference.
- Phân biệt việc Javadoc tham chiếu một declaration với việc trình biên dịch chọn overload cho một lời gọi.
- Xác định nguyên nhân một target không được phân giải.
- Dùng `javadoc` và DocLint để kiểm tra reference, sau đó xem anchor trong HTML được sinh ra.

## 1. Vì sao method overload cần parameter list?

Java cho phép một class khai báo nhiều method cùng tên nếu signature của chúng khác nhau. Ví dụ:

~~~java
public String format(String text) { ... }

public String format(String text, int width) { ... }

public String format(int value) { ... }
~~~

Cả ba method đều có tên `format`, nhưng chúng là ba declaration riêng. Trong snippet, nếu chỉ viết:

~~~java
api.format("hello"); // @link substring="format" target="demo.FormatterApi#format"
~~~

thì target chưa mô tả rõ overload cần liên kết. Theo đặc tả reference của Javadoc, tên method hoặc constructor **thông thường phải đi kèm danh sách kiểu tham số**; có thể bỏ danh sách này khi method không overloaded và tên không trùng field hoặc enum member trong cùng class.

Hãy viết rõ signature:

~~~java
api.format("hello"); // @link substring="format" target="demo.FormatterApi#format(java.lang.String)"
~~~

Kết quả là chữ `format` trong snippet trỏ đến overload `format(String)`.

Một target khác:

~~~java
api.format("hello", 20); // @link substring="format" target="demo.FormatterApi#format(java.lang.String, int)"
~~~

trỏ đến overload nhận hai tham số `String` và `int`.

**Nguyên tắc:** selector `substring` hoặc `regex` chọn chữ được gắn liên kết trong snippet; parameter list của `target` chọn declaration API đích. Hai phần này giải quyết hai câu hỏi khác nhau.

## 2. Cấu trúc reference dùng trong `target`

`target` dùng cùng cú pháp reference như inline tag `{@link ...}` trong Javadoc. Dạng tổng quát:

~~~text
module/package.Class#member(parameterType1, parameterType2)
~~~

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `module/` | Tên module, có thể bỏ nếu không cần phân biệt. |
| `package.Class` | Class hoặc interface chứa member. Có thể dùng tên đầy đủ hoặc tên được suy ra từ ngữ cảnh/import. |
| `#` | Phân cách class với member. |
| `member` | Tên method, constructor, field hoặc enum member. |
| `(parameter types)` | Danh sách kiểu tham số, theo đúng thứ tự khai báo. Cần ghi khi method overloaded. |

Ví dụ:

~~~java
// Method không tham số:
api.reset(); // @link substring="reset" target="demo.FormatterApi#reset()"

// Method có một tham số:
api.format("hello"); // @link substring="format" target="demo.FormatterApi#format(java.lang.String)"

// Method có hai tham số:
api.format("hello", 20); // @link substring="format" target="demo.FormatterApi#format(java.lang.String, int)"
~~~

### 2.1. Tên kiểu tham số phải đúng

Danh sách tham số mô tả **kiểu của các tham số trong declaration**, không phải tên tham số và cũng không phải giá trị truyền vào lời gọi.

Giả sử method được khai báo:

~~~java
public String format(String text, int width)
~~~

Reference đúng:

~~~text
demo.FormatterApi#format(java.lang.String, int)
~~~

Reference sai:

~~~text
demo.FormatterApi#format(text, width)
demo.FormatterApi#format(String text, int width)
demo.FormatterApi#format(String, int)
~~~

Hai dòng đầu dùng tên tham số hoặc cú pháp khai báo tham số. Dòng cuối chỉ có thể đúng nếu `String` được phân giải trong ngữ cảnh; để reference ổn định và dễ đọc, ví dụ trong bài dùng tên kiểu đầy đủ `java.lang.String`.

### 2.2. Có thể dùng tên ngắn nếu ngữ cảnh phân giải được

Javadoc đánh giá reference trong scope của documentation comment. Import của compilation unit được tính đến khi phân giải tên class và interface.

Ví dụ, nếu file có:

~~~java
import java.util.List;
import java.lang.String;
~~~

thì reference có thể dùng `List<String>` hoặc `String`. Tuy nhiên, tên đầy đủ thường rõ ràng hơn trong tài liệu dùng để minh họa overload:

~~~text
demo.FormatterApi#format(java.util.List<java.lang.String>)
~~~

Tên đầy đủ giúp tránh nhầm lẫn khi có các class cùng tên ở nhiều package hoặc khi source được chuyển sang package khác.

Các thành phần đầu của reference có thể bỏ nếu Javadoc suy ra được từ ngữ cảnh. Nếu method nằm trong chính class đang được ghi tài liệu, có thể dùng dạng `#format(java.lang.String)`.

### 2.3. Khoảng trắng trong reference

Đặc tả cho phép khoảng trắng giữa các token trong parameter list. Không đặt khoảng trắng tùy ý ở những phần khác của reference.

Nên giữ một phong cách nhất quán, ví dụ:

~~~text
demo.FormatterApi#format(java.lang.String, int)
~~~

Dấu phẩy phân cách các kiểu tham số. Không đưa dấu phẩy sau tham số cuối cùng.

## 3. Xác định đúng overload bằng kiểu tham số

### 3.1. Primitive type và wrapper type là hai kiểu khác nhau

Class có hai overload:

~~~java
public String format(int value) { ... }

public String format(Integer value) { ... }
~~~

Hai target khác nhau:

~~~java
// primitive int
api.format(42); // @link substring="format" target="demo.FormatterApi#format(int)"

// reference type Integer
api.format(Integer.valueOf(42)); // @link substring="format" target="demo.FormatterApi#format(java.lang.Integer)"
~~~

Không được dùng `int` để tham chiếu overload nhận `Integer` hoặc ngược lại. Java có boxing và unboxing khi phân giải lời gọi method, nhưng reference trong Javadoc chỉ đến declaration được chỉ rõ bằng kiểu tham số.

### 3.2. Thứ tự tham số có ý nghĩa

Giả sử có:

~~~java
public String combine(String prefix, int count) { ... }

public String combine(int count, String prefix) { ... }
~~~

Hai method có cùng tập kiểu nhưng khác thứ tự. Reference phải phản ánh đúng thứ tự trong declaration:

~~~java
api.combine("item", 3); // @link substring="combine" target="demo.FormatterApi#combine(java.lang.String, int)"
api.combine(3, "item"); // @link substring="combine" target="demo.FormatterApi#combine(int, java.lang.String)"
~~~

Nếu đảo thứ tự kiểu trong `target`, Javadoc không trỏ đến overload mong muốn.

### 3.3. Array type là một phần của parameter type

Một class có thể có:

~~~java
public String format(String text) { ... }

public String format(String[] parts) { ... }
~~~

Hai target:

~~~java
api.format("hello"); // @link substring="format" target="demo.FormatterApi#format(java.lang.String)"
api.format(new String[] {"a", "b"}); // @link substring="format" target="demo.FormatterApi#format(java.lang.String[])"
~~~

Dấu `[]` thuộc kiểu tham số. Không bỏ dấu ngoặc vuông khi muốn tham chiếu overload nhận mảng.

### 3.4. Parameterized type trong target

Đặc tả reference cho phép dùng parameterized type trong class và member reference. Ví dụ, nếu API có method:

~~~java
public String format(List<String> parts) { ... }
~~~

có thể tham chiếu bằng:

~~~java
api.format(List.of("a", "b")); // @link substring="format" target="demo.FormatterApi#format(java.util.List<java.lang.String>)"
~~~

Không thể tạo hai overload chỉ khác type argument như `format(List<String>)` và `format(List<Integer>)`, bởi type erasure khiến chúng có signature tương đương ở cấp khai báo. Hãy dùng các kiểu tham số thực sự khác nhau để tạo overload hợp lệ.

## 4. Parameter list không chứa kiểu trả về

Reference đến method chỉ cần tên method và danh sách kiểu tham số:

~~~text
demo.FormatterApi#format(java.lang.String)
~~~

Không ghi kiểu trả về trước tên method:

~~~text
java.lang.String demo.FormatterApi#format(java.lang.String)
~~~

Java không cho phép tạo overload chỉ bằng cách thay đổi kiểu trả về. Theo quy tắc method signature của Java Language Specification, signature được xác định bởi tên method, type parameters và formal parameter types; return type không phải yếu tố phân biệt overload.

Vì vậy:

- `format(String)` và `format(int)` là hai overload khác nhau.
- Hai method cùng tên và cùng kiểu tham số nhưng khác kiểu trả về không tạo thành hai overload hợp lệ.
- `target` không cần và không nhận kiểu trả về như một phần của reference.

Đây cũng là lý do không nên cố phân biệt overload bằng kiểu kết quả của biểu thức ở phía gọi.

## 5. Reference đến method không phải là overload resolution của lời gọi

Có hai hoạt động cần phân biệt:

1. **Java compiler chọn method cho lời gọi:** xem số lượng đối số, compile-time type của từng đối số, boxing, widening, varargs và các quy tắc overload resolution.
2. **Javadoc phân giải target:** tìm declaration được nêu trong reference, sử dụng tên class/member và danh sách kiểu tham số.

Ví dụ:

~~~java
Object input = "hello";
String result = api.format((String) input);
~~~

Lời gọi Java được compiler phân giải theo kiểu đối số tại vị trí gọi. Trong markup comment, target vẫn chỉ rõ declaration:

~~~java
api.format((String) input); // @link substring="format" target="demo.FormatterApi#format(java.lang.String)"
~~~

Không nên suy ra target chỉ từ cách viết lời gọi hoặc giá trị truyền vào. Hãy xem declaration của class API và ghi đúng kiểu tham số.

### Bảng phân biệt nhanh

| Nội dung | Java compiler | Javadoc `target` |
| --- | --- | --- |
| Mục đích | Chọn method được gọi trong chương trình. | Chọn declaration mà hyperlink trỏ đến. |
| Đầu vào chính | Compile-time type của đối số, số lượng đối số và ngữ cảnh lời gọi. | Tên class/member và parameter type list trong reference. |
| Boxing/widening | Có thể tham gia overload resolution. | Không dùng để tự suy ra một overload khác. |
| Tên tham số | Không dùng để chọn overload. | Không viết trong parameter list của reference. |
| Kiểu trả về | Không dùng để phân biệt overload. | Không nằm trong reference. |

## 6. Ví dụ hoàn chỉnh với nhiều overload

Ta tạo hai file trong package `demo` để kiểm tra các trường hợp phổ biến.

### 6.1. File `FormatterApi.java`

~~~java
package demo;

import java.util.List;

/**
 * API minh họa nhiều overload của cùng một method.
 */
public final class FormatterApi {

    /**
     * Định dạng chuỗi.
     * @param text chuỗi cần định dạng
     * @return chuỗi sau khi định dạng
     */
    public String format(String text) {
        return text;
    }

    /**
     * Định dạng chuỗi với độ rộng.
     * @param text chuỗi cần định dạng
     * @param width số lần lặp tối thiểu
     * @return chuỗi sau khi định dạng
     */
    public String format(String text, int width) {
        return text.repeat(Math.max(1, width));
    }

    /**
     * Định dạng giá trị nguyên thủy.
     * @param value giá trị số nguyên
     * @return biểu diễn dạng chuỗi
     */
    public String format(int value) {
        return Integer.toString(value);
    }

    /**
     * Định dạng giá trị nguyên dạng wrapper.
     * @param value giá trị số nguyên dạng wrapper
     * @return biểu diễn dạng chuỗi
     */
    public String format(Integer value) {
        return String.valueOf(value);
    }

    /**
     * Ghép các phần tử trong mảng chuỗi.
     * @param parts các phần tử chuỗi
     * @return chuỗi đã ghép
     */
    public String format(String[] parts) {
        return String.join(", ", parts);
    }

    /**
     * Ghép các phần tử trong danh sách chuỗi.
     * @param parts danh sách phần tử chuỗi
     * @return chuỗi đã ghép
     */
    public String format(List<String> parts) {
        return String.join(", ", parts);
    }

    /**
     * Kết hợp chuỗi với số lần lặp.
     * @param prefix tiền tố cần lặp
     * @param count số lần lặp tối thiểu
     * @return chuỗi sau khi kết hợp
     */
    public String combine(String prefix, int count) {
        return prefix.repeat(Math.max(1, count));
    }

    /**
     * Kết hợp số lần lặp với chuỗi.
     * @param count số lần lặp tối thiểu
     * @param prefix tiền tố cần lặp
     * @return chuỗi sau khi kết hợp
     */
    public String combine(int count, String prefix) {
        return prefix.repeat(Math.max(1, count));
    }
}
~~~

### 6.2. File `FormatterDoc.java`

~~~java
package demo;

import java.util.List;

/**
 * Minh họa cách tham chiếu từng overload trong snippet:
 *
 * {@snippet :
 *     FormatterApi api = new FormatterApi();
 *     String a = api.format("hello"); // @link substring="format" target="demo.FormatterApi#format(java.lang.String)"
 *     String b = api.format("hello", 2); // @link substring="format" target="demo.FormatterApi#format(java.lang.String, int)"
 *     String c = api.format(42); // @link substring="format" target="demo.FormatterApi#format(int)"
 *     String d = api.format(Integer.valueOf(42)); // @link substring="format" target="demo.FormatterApi#format(java.lang.Integer)"
 *     String e = api.format(new String[] {"a", "b"}); // @link substring="format" target="demo.FormatterApi#format(java.lang.String[])"
 *     String f = api.format(List.of("a", "b")); // @link substring="format" target="demo.FormatterApi#format(java.util.List<java.lang.String>)"
 *     String g = api.combine("item", 3); // @link substring="combine" target="demo.FormatterApi#combine(java.lang.String, int)"
 *     String h = api.combine(3, "item"); // @link substring="combine" target="demo.FormatterApi#combine(int, java.lang.String)"
 * }
 */
public final class FormatterDoc {
}
~~~

Mỗi dòng có một markup comment `@link` riêng. Selector `substring="format"` chọn tên trong snippet; target chỉ ra overload cụ thể. Các chữ `format` giống nhau nhưng liên kết đến những declaration khác nhau.

## 7. Kiểm tra target đã được phân giải

Đừng chỉ kiểm tra rằng tên method trong snippet có màu liên kết. Một anchor có thể trông giống hyperlink nhưng dẫn đến sai overload hoặc không có đích mong muốn. Cần kiểm tra cả quá trình sinh tài liệu và URL trong HTML.

### 7.1. Sinh tài liệu với DocLint

Từ thư mục gốc của ví dụ, nơi có thư mục `src/demo` chứa hai file trên, chạy:

~~~bash
javadoc -d docs -sourcepath src -Xdoclint:reference -Werror demo
~~~

Ý nghĩa các tùy chọn:

- `-d docs`: ghi tài liệu HTML vào thư mục `docs`.
- `-sourcepath src`: chỉ định nơi tìm source của package `demo`.
- `-Xdoclint:reference`: bật nhóm kiểm tra reference trong documentation comment.
- `-Werror`: biến warning thành lỗi để build tài liệu thất bại nếu còn warning.

`-Xdoclint` được bật mặc định trong `javadoc` hiện đại. Khi muốn kiểm tra riêng reference, chỉ định nhóm `reference` giúp tập trung vào tên class, method và các phần tử API được tham chiếu.

Nếu một target không tìm thấy method hoặc tên kiểu không phân giải được, DocLint có thể báo lỗi hoặc warning tương ứng. Đọc thông báo và vị trí dòng được chỉ ra để xác định reference cần sửa.

### 7.2. Mở HTML và kiểm tra hyperlink

Sau khi sinh thành công, mở:

~~~text
docs/demo/FormatterDoc.html
~~~

Tìm snippet và kiểm tra:

1. Tên `format` ở dòng đầu dẫn đến declaration `format(String)`.
2. Tên `format` ở dòng thứ hai dẫn đến `format(String, int)`.
3. Hai lời gọi với `int` và `Integer` dẫn đến hai overload tương ứng.
4. Dòng dùng `String[]` dẫn đến overload nhận mảng.
5. Dòng dùng `List<String>` dẫn đến overload nhận parameterized type.
6. Hai lời gọi `combine` dẫn đến hai overload có thứ tự tham số khác nhau.

Dùng Inspect của trình duyệt hoặc mở HTML dưới dạng văn bản để xem thuộc tính `href` của anchor. Với standard doclet, phần detail của method có `id` được tạo từ tên method và danh sách kiểu tham số đầy đủ, phân cách bằng dấu phẩy. Ví dụ dạng anchor là:

~~~text
format(java.lang.String)
format(java.lang.String,int)
format(int)
format(java.lang.Integer)
format(java.lang.String[])
~~~

Đối chiếu fragment trong `href` với `id` của phần method detail trong trang `FormatterApi.html`. Đây là cách xác nhận hyperlink đang trỏ đến đúng overload, không chỉ đúng trang class.

### 7.3. Phân biệt lỗi reference và lỗi external link

Có hai nhóm lỗi khác nhau:

- **Reference không phân giải:** tên class, member hoặc parameter type không khớp declaration. Hãy kiểm tra spelling, package, import, số lượng và thứ tự kiểu tham số.
- **Reference đến API bên ngoài nhưng thiếu vị trí tài liệu:** declaration có thể tồn tại nhưng bộ tài liệu hiện tại không biết URL đích. Với API bên ngoài, cấu hình `-link` hoặc `-linkoffline` cho bộ tài liệu đó.

Ví dụ khi cần link đến Java SE API bên ngoài:

~~~bash
javadoc -d docs -link https://docs.oracle.com/en/java/javase/27/docs/api/ -sourcepath src demo
~~~

Với tài liệu API bên ngoài, hãy dùng URL đúng phiên bản được phát hành và kiểm tra link trong HTML sau khi sinh. Đối với các API platform của JDK, standard doclet hiện đại tạo platform links theo cấu hình mặc định; tùy chọn `--no-platform-links` có thể tắt chúng.

## 8. Các lỗi thường gặp khi tham chiếu overload

| Lỗi | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| Chỉ ghi `target="demo.FormatterApi#format"` trong khi có nhiều overload. | Reference không xác định rõ parameter list. | Ghi đầy đủ kiểu tham số, ví dụ `#format(java.lang.String)`. |
| Đưa tên tham số vào target. | Reference cần kiểu tham số, không cần tên biến. | Dùng `#format(java.lang.String, int)`. |
| Ghi cả kiểu trả về trong target. | Return type không thuộc reference member syntax và không phân biệt overload. | Bỏ kiểu trả về, chỉ giữ class/member và parameter list. |
| Đảo thứ tự kiểu tham số. | `format(String, int)` khác `format(int, String)`. | So sánh với thứ tự trong declaration. |
| Nhầm `int` với `Integer`. | Primitive và wrapper là hai kiểu khác nhau. | Dùng đúng `int` hoặc `java.lang.Integer`. |
| Bỏ `[]` khỏi array parameter. | `String` khác `String[]`. | Ghi `java.lang.String[]`. |
| Dùng tên class ngắn không có import hoặc không suy ra được. | Reference được phân giải theo scope của comment. | Dùng fully qualified class name hoặc thêm import phù hợp. |
| Ghi kiểu tham số bằng tên của đối số ở call site. | Target tham chiếu declaration, không dùng kiểu biểu thức để tự chọn overload. | Đọc chữ ký method trong source và ghi đúng parameter types. |
| Dùng hai overload chỉ khác generic type argument. | Các kiểu generic có thể có cùng erasure, khiến khai báo không hợp lệ. | Thiết kế overload với parameter types hợp lệ và khác nhau theo quy tắc Java. |
| Method có ở thư viện ngoài nhưng link không mở được. | Thiếu cấu hình URL tài liệu ngoài. | Dùng `-link` hoặc `-linkoffline` và kiểm tra URL đích. |
| Chỉ kiểm tra tên được tô liên kết. | Có thể liên kết đến sai overload trong cùng class. | Kiểm tra `href` và `id` trong HTML. |

## 9. Quy trình xử lý một target không phân giải

Khi `javadoc` báo một reference không hợp lệ, làm theo trình tự:

1. **Xác định class đích.** Kiểm tra package, tên class và nested class nếu có.
2. **Xác định member.** Đúng tên method và đúng chữ hoa/thường.
3. **Đối chiếu parameter list.** Đếm tham số, kiểm tra kiểu và thứ tự.
4. **Kiểm tra tên kiểu.** Dùng primitive name hoặc tên class được import/phân giải; khi chưa chắc, viết fully qualified name.
5. **Kiểm tra kiểu mảng/generic.** Không bỏ dấu `[]`; parameterized type phải phản ánh đúng declaration.
6. **Kiểm tra scope.** Reference được đánh giá trong scope của documentation comment, với import của compilation unit.
7. **Kiểm tra external documentation.** Nếu target không thuộc bộ source đang sinh, cung cấp link đến tài liệu ngoài.
8. **Sinh lại Javadoc.** Dùng DocLint reference check, rồi kiểm tra `href` và fragment trong HTML.

Một target chỉ được xem là đã kiểm chứng khi cả hai điều kiện đều đạt: DocLint không báo reference sai và hyperlink trong HTML dẫn đến đúng phần method detail.

## 10. Bài tập tự đánh giá

### Bài 1 — Chọn overload theo primitive type

Class có:

~~~java
public String convert(int value) { ... }
public String convert(long value) { ... }
~~~

Viết hai target cho hai overload.

**Đáp án:**

~~~text
demo.Converter#convert(int)
demo.Converter#convert(long)
~~~

### Bài 2 — Phân biệt primitive và wrapper

Class có:

~~~java
public String find(int id) { ... }
public String find(Integer id) { ... }
~~~

**Đáp án:**

~~~text
demo.UserFinder#find(int)
demo.UserFinder#find(java.lang.Integer)
~~~

### Bài 3 — Phân biệt mảng và phần tử đơn

Class có:

~~~java
public String join(String value) { ... }
public String join(String[] values) { ... }
~~~

**Đáp án:**

~~~text
demo.Joiner#join(java.lang.String)
demo.Joiner#join(java.lang.String[])
~~~

### Bài 4 — Thứ tự tham số

Class có hai overload:

~~~java
public String pair(String name, int count) { ... }
public String pair(int count, String name) { ... }
~~~

**Đáp án:**

~~~text
demo.PairFormatter#pair(java.lang.String, int)
demo.PairFormatter#pair(int, java.lang.String)
~~~

### Bài 5 — Kiểu trả về có cần ghi không?

Method declaration:

~~~java
public String parse(String input) { ... }
~~~

Có cần viết `String` trước tên method trong target không?

**Đáp án:** Không. Target là `demo.Parser#parse(java.lang.String)`. Reference dùng class, member và parameter types; return type không phải thành phần của target.

### Bài 6 — Link nào đã thực sự đúng?

Một snippet có `api.format("hello", 10)`. Hai target được cân nhắc:

~~~text
demo.FormatterApi#format(java.lang.String, int)
demo.FormatterApi#format(java.lang.String)
~~~

**Đáp án:** Target đầu đúng vì method được gọi có hai tham số `String` và `int`. Target thứ hai trỏ đến overload một tham số và do đó là sai mục tiêu.

## Tổng kết

- `@link` trong snippet dùng reference syntax giống `{@link}`; `target` phải xác định đúng class, member và overload.
- Khi method overloaded, ghi parameter type list trong ngoặc, theo đúng số lượng, kiểu và thứ tự khai báo.
- Không ghi tên tham số hoặc kiểu trả về trong reference.
- Primitive, wrapper, array và parameterized type là các kiểu cần phân biệt khi chọn overload.
- Javadoc reference resolution dựa trên declaration và scope của documentation comment; nó không chạy overload resolution của lời gọi Java.
- Dùng `-Xdoclint:reference` để kiểm tra reference, `-Werror` nếu muốn warning làm build thất bại, rồi mở HTML kiểm tra `href` và `id` của method detail.
- Nếu target ở API ngoài, cung cấp cấu hình link tài liệu phù hợp.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Documentation Comment Specification, JDK 27, mục References](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html#references): cú pháp reference, parameter list, import scope, parameterized types và member references.
2. [Oracle — JavaDoc Documentation Comment Specification, JDK 27, mục Snippet / Linking text](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html#snippet): thuộc tính `@link`, `target`, selector, region và quy tắc liên kết.
3. [Oracle — JavaDoc Output Generated by the Standard Doclet, JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/std-doclet-output.html): cách standard doclet tạo method detail ID từ tên method và kiểu tham số đầy đủ.
4. [Oracle — The javadoc Command, JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html): DocLint, nhóm kiểm tra `reference`, `-Werror` và tùy chọn liên kết tài liệu ngoài.
5. [Oracle — Java Language Specification, Java SE 27, `8.4.2 Method Signature` và `8.4.9 Overloading`](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html): quy tắc signature và overload của method.
