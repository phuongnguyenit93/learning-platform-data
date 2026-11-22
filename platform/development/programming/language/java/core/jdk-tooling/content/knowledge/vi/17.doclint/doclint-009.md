# Tài liệu Javadoc không hợp lệ và cách sửa

## 1. Tài liệu Javadoc không hợp lệ là gì?

Javadoc tạo tài liệu HTML từ documentation comment trong mã nguồn Java. Một comment có thể trông đúng như văn bản nhưng vẫn không hợp lệ vì sai cấu trúc HTML, dùng sai block tag, tham chiếu đến kiểu hoặc member không tồn tại, hoặc thiếu thông tin theo quy tắc kiểm tra tài liệu.

Các vấn đề thường gặp gồm:

- Thẻ HTML mở nhưng không đóng, dùng sai cấu trúc hoặc thuộc tính không hợp lệ.
- Dùng @param, @return, @throws ở sai loại khai báo.
- Ghi tên tham số không tồn tại hoặc thiếu mô tả tham số.
- {@link ...} hoặc @see trỏ đến class, method hay package không phân giải được.
- Inline tag thiếu dấu ngoặc hoặc sai cú pháp.
- Hình ảnh thiếu văn bản thay thế, bảng HTML thiếu caption.
- API công khai thiếu documentation comment hoặc thiếu tag cần thiết.
- Dùng custom tag nhưng chưa đăng ký với công cụ Javadoc.

Một số lỗi khiến Javadoc dừng với error; một số khác là warning. Khi dự án yêu cầu tài liệu sạch, cả warning cũng nên được xử lý trước khi phát hành.

## 2. Phân biệt lỗi Java và lỗi Javadoc

javac kiểm tra mã nguồn Java để tạo bytecode. Javadoc đọc declaration và documentation comment để tạo tài liệu HTML. Hai công việc có liên quan nhưng kiểm tra các vấn đề khác nhau.

| Loại lỗi | Ví dụ | Công cụ phát hiện |
|---|---|---|
| Lỗi cú pháp Java | Thiếu dấu ;, sai kiểu dữ liệu | javac và compiler được Javadoc sử dụng |
| Lỗi cấu trúc comment | Dùng sai cú pháp inline link | Javadoc / DocLint |
| Lỗi HTML | Thẻ b chưa đóng | Javadoc / DocLint |
| Lỗi tham chiếu | @see MissingType không tồn tại | Javadoc / DocLint |
| Thiếu tài liệu | Public method không có comment | Nhóm missing của DocLint |
| Lỗi accessibility | img thiếu alt, table thiếu caption | Nhóm accessibility của DocLint |

Một dự án có thể biên dịch thành công bằng javac nhưng vẫn tạo tài liệu Javadoc có lỗi. Ngược lại, comment đúng không thể bù cho mã nguồn Java không biên dịch được.

Javadoc đôi khi vẫn tạo một phần HTML khi gặp lỗi, nhưng có thể chèn dấu đánh dấu chẩn đoán và trả mã thoát khác 0. Không phát hành tài liệu được tạo từ lần chạy thất bại.

## 3. DocLint kiểm tra những gì?

**DocLint** là bộ kiểm tra documentation comment được tích hợp trong công cụ Javadoc. Nó phát hiện các lỗi phổ biến trước khi tài liệu được giao cho người đọc.

Các nhóm kiểm tra:

| Nhóm | Nội dung kiểm tra | Ví dụ |
|---|---|---|
| html | Cấu trúc và cách dùng HTML trong comment | Thẻ không đóng, cấu trúc HTML sai |
| accessibility | Khả năng truy cập của HTML | Hình thiếu alt, bảng thiếu caption |
| missing | Tài liệu hoặc tag cần thiết bị thiếu | Public class hoặc method không có comment |
| reference | Tham chiếu đến phần tử Java | @see hoặc {@link} không tìm thấy |
| syntax | Cú pháp và cách dùng documentation tag | Tag sai vị trí, inline tag sai cú pháp |

Các nhóm này có thể được bật hoặc tắt riêng. -Xdoclint bật các kiểm tra được khuyến nghị; -Xdoclint:all bật tất cả nhóm, bao gồm cả missing.

Trong nhiều cấu hình JDK hiện đại, các kiểm tra DocLint được bật mặc định nhưng nhóm missing không được bật. Nếu muốn buộc API công khai phải có comment và tag đầy đủ, hãy bật rõ -Xdoclint:all.

-Xdoclint là tùy chọn mở rộng của Javadoc. Cú pháp và chi tiết có thể thay đổi giữa các bản JDK, vì vậy hãy xem javadoc --help-extra trên đúng phiên bản build.

## 4. Lỗi HTML trong documentation comment

Javadoc xử lý phần mô tả như nội dung HTML. Thẻ mở và đóng không khớp có thể làm DocLint báo lỗi.

Ví dụ không hợp lệ:

~~~java
/**
 * Returns a value <b>without closing the element.
 */
public int value() {
    return 10;
}
~~~

DocLint có thể báo:

~~~text
error: element not closed: b
~~~

Sửa bằng cách đóng thẻ:

~~~java
/**
 * Returns a <b>valid</b> value.
 */
public int value() {
    return 10;
}
~~~

Hoặc dùng inline tag {@code ...} khi chỉ muốn hiển thị tên biến, kiểu, biểu thức hoặc lệnh Java:

~~~java
/**
 * Pass a positive value to {@code calculate(int)}.
 */
~~~

Một số lỗi HTML khác:

- Lồng các thẻ theo thứ tự không hợp lệ.
- Đặt block tag vào giữa một phần tử HTML đang mở.
- Dùng thuộc tính không phù hợp với HTML được Javadoc hỗ trợ.
- Dùng dấu < hoặc > trong văn bản mà không escape.
- Viết HTML table hoặc list thiếu cấu trúc.

Nếu muốn hiển thị ký tự HTML như văn bản, dùng {@literal ...}, {@code ...} hoặc entity HTML phù hợp. Ví dụ:

~~~java
/**
 * The expression {@code a < b} is true when a is smaller than b.
 * The literal text {@literal <T>} represents a type parameter.
 */
~~~

Không dùng HTML thô khi một inline tag có thể diễn đạt rõ hơn.

## 5. Lỗi accessibility trong HTML

Tài liệu API cũng cần dễ đọc với trình đọc màn hình và công nghệ hỗ trợ. Nhóm accessibility của DocLint phát hiện một số vấn đề HTML thường gặp.

### Hình ảnh thiếu alt

Không hợp lệ:

~~~html
<img src="architecture.png">
~~~

DocLint có thể báo:

~~~text
error: no "alt" attribute for image
~~~

Sửa bằng văn bản thay thế mô tả nội dung:

~~~html
<img src="architecture.png" alt="Sơ đồ các module của ứng dụng">
~~~

Nếu hình chỉ mang tính trang trí và không truyền tải thông tin, dùng giá trị alt rỗng khi phù hợp với mục đích truy cập:

~~~html
<img src="separator.png" alt="">
~~~

### Bảng thiếu caption

Một bảng có thể đọc được về mặt hiển thị nhưng thiếu mô tả ngữ cảnh:

~~~html
<table>
  <tr><th>Key</th><th>Value</th></tr>
  <tr><td>A</td><td>B</td></tr>
</table>
~~~

DocLint có thể báo:

~~~text
error: no caption for table
~~~

Sửa bằng caption:

~~~html
<table>
  <caption>Giá trị cấu hình mẫu</caption>
  <tr><th scope="col">Key</th><th scope="col">Value</th></tr>
  <tr><td>A</td><td>B</td></tr>
</table>
~~~

Dùng heading, danh sách và bảng khi chúng giúp người đọc hiểu cấu trúc. Không chèn HTML chỉ để trang trí.

## 6. Dùng sai block tag

Block tag phải phù hợp với loại declaration đang được mô tả.

| Tag | Nơi sử dụng phù hợp |
|---|---|
| @param | Tham số của method/constructor hoặc type parameter |
| @return | Method trả về giá trị |
| @throws / @exception | Ngoại lệ mà method hoặc constructor có thể ném |
| @see | Tham chiếu đến phần tử hoặc tài liệu liên quan |
| @since | Phiên bản API được giới thiệu |
| @deprecated | API đã bị deprecated và hướng thay thế |

Ví dụ sai: đặt @return trong comment của class:

~~~java
/**
 * Represents a calculator.
 * @return the result
 */
public class Calculator {
}
~~~

DocLint báo lỗi tương tự:

~~~text
error: invalid use of @return
~~~

@return chỉ dành cho method có giá trị trả về. Class không có giá trị trả về, nên tag này không có ý nghĩa ở vị trí đó.

Ví dụ đúng:

~~~java
/**
 * Multiplies a value by two.
 *
 * @param value the value to multiply
 * @return the doubled value
 */
public int twice(int value) {
    return value * 2;
}
~~~

### @param phải khớp tên tham số

Không hợp lệ:

~~~java
/**
 * Adds two values.
 * @param first first value
 * @param second second value
 */
public int add(int left, int right) {
    return left + right;
}
~~~

Tên trong @param phải trùng với tên khai báo left và right. Sửa:

~~~java
/**
 * Adds two values.
 *
 * @param left the first value
 * @param right the second value
 * @return the sum
 */
public int add(int left, int right) {
    return left + right;
}
~~~

Với generic type, tên type parameter phải đặt trong dấu ngoặc nhọn:

~~~java
/**
 * Holds a value.
 *
 * @param <T> the value type
 */
public class Box<T> {
}
~~~

### Không đặt @return cho void method hoặc constructor

Method void và constructor không trả về giá trị cho người gọi. Hãy mô tả hành vi trong phần mô tả chính, dùng @param cho tham số và @throws khi cần.

## 7. Lỗi tham chiếu trong @see và {@link}

Javadoc có thể tạo liên kết đến class, package, method, constructor hoặc field. Nếu tên tham chiếu không tồn tại, viết sai overload hoặc không thể phân giải trong ngữ cảnh hiện tại, DocLint có thể báo reference not found.

Ví dụ sai:

~~~java
/**
 * Uses a helper.
 * @see MissingType
 */
public class Client {
}
~~~

Sửa bằng một kiểu có thật:

~~~java
/**
 * Uses a calculator.
 * @see Calculator
 */
public class Client {
}
~~~

Có thể liên kết đến method trong cùng class:

~~~java
/**
 * Returns twice the input.
 *
 * @see #add(int, int)
 */
public int twice(int value) {
    return value * 2;
}
~~~

Inline link:

~~~java
/**
 * Use {@link #twice(int)} to double a value.
 */
~~~

Một số nguyên tắc:

- Dùng đúng tên class và package.
- Với method overload, ghi đầy đủ danh sách kiểu tham số nếu cần phân biệt.
- Dùng #member cho member trong cùng class.
- Dùng tên đầy đủ như java.util.List khi tên ngắn bị mơ hồ.
- Đảm bảo dependency hoặc module chứa phần tử được tham chiếu nằm trong môi trường phân giải của Javadoc.
- Kiểm tra @see và {@link} sau khi đổi tên API.

Không viết link đến một tên gần giống rồi hy vọng trình duyệt tự tìm được. Liên kết Javadoc phải trỏ đến phần tử mà công cụ có thể phân giải.

## 8. Lỗi cú pháp inline tag và custom tag

Inline tag nằm trong phần mô tả và có dạng {@tag ...}. Phải có cặp ngoặc nhọn và nội dung đúng cú pháp.

Ví dụ:

~~~java
/**
 * Returns the value of {@code count}.
 * See {@link #size()} for the current size.
 * The literal token is {@literal <END>}.
 */
~~~

Các lỗi thường gặp:

- Thiếu dấu } kết thúc inline tag.
- Viết sai tên tag.
- Đưa tag chỉ hợp lệ ở block section vào giữa câu.
- Dùng {@link} nhưng bỏ phần tham chiếu.
- Nhầm @code với {@code ...}.

Ví dụ sai:

~~~java
/**
 * Calls {@link #size().
 */
~~~

Sửa:

~~~java
/**
 * Calls {@link #size()}.
 */
~~~

### Custom tag

Nếu dự án có tag riêng như @implNote hoặc tag nội bộ, Javadoc phải biết cách xử lý tag đó. Có thể đăng ký tag dạng đơn giản bằng -tag hoặc cung cấp Taglet bằng -taglet và -tagletpath.

Ví dụ một tag tùy chỉnh không có nội dung phức tạp:

~~~bash
javadoc -tag note:a:Note -d docs src/demo/*.java
~~~

Cú pháp -tag gồm tên tag, vị trí hợp lệ và tiêu đề hiển thị. Hãy kiểm tra javadoc --help và tài liệu Taglet cho đúng phiên bản trước khi thêm tag vào build.

## 9. Thiếu documentation comment và tag bắt buộc

Nhóm missing kiểm tra các phần tử cần tài liệu nhưng chưa có comment, cũng như một số tag cần thiết bị thiếu.

Ví dụ:

~~~java
package demo;

public class MissingDocs {
    public void run(String input) {
    }
}
~~~

Khi bật kiểm tra missing, Javadoc có thể cảnh báo:

~~~text
warning: no comment
warning: use of default constructor, which does not provide a comment
warning: no comment
~~~

Cách sửa là viết comment cho API được công bố, thêm constructor có comment nếu constructor được tạo mặc định nhưng cần xuất hiện trong tài liệu, và bổ sung tag theo hợp đồng method.

Ví dụ:

~~~java
package demo;

/**
 * Runs a named operation.
 */
public class Operation {
    /** Creates an operation. */
    public Operation() {}

    /**
     * Runs the operation for the given input.
     *
     * @param input the input name
     */
    public void run(String input) {
    }
}
~~~

Không nhất thiết phải mô tả mọi private implementation detail trong Javadoc API. Hãy chọn mức hiển thị phù hợp: mặc định Javadoc thường tập trung public/protected; -private mở rộng tài liệu đến cả thành viên private.

## 10. Bật và cấu hình DocLint

### Bật tất cả nhóm kiểm tra

~~~bash
javadoc -Xdoclint:all -d docs src/demo/*.java
~~~

all bao gồm accessibility, html, missing, reference và syntax.

### Bỏ riêng kiểm tra missing

~~~bash
javadoc -Xdoclint:all,-missing -d docs src/demo/*.java
~~~

Cách này vẫn kiểm tra HTML, accessibility, reference và syntax nhưng không yêu cầu mọi API phải có comment.

### Tắt DocLint

~~~bash
javadoc -Xdoclint:none -d docs src/demo/*.java
~~~

Đây là cách tắt các kiểm tra DocLint. Nó không đảm bảo mọi warning của standard doclet biến mất; một số kiểm tra hoặc cảnh báo khác vẫn có thể xuất hiện. Chỉ dùng khi có lý do cụ thể và đã hiểu phần kiểm tra bị bỏ qua.

### Chỉ kiểm tra một nhóm

~~~bash
javadoc -Xdoclint:reference -d docs src/demo/*.java
javadoc -Xdoclint:accessibility -d docs src/demo/*.java
~~~

### Giới hạn kiểm tra theo package

~~~bash
javadoc -Xdoclint/package:demo.* -d docs src/demo/*.java
~~~

Cú pháp package filter cho phép chỉ định package hoặc prefix package; thêm dấu - trước package để loại khỏi nhóm kiểm tra được chỉ định.

### Chuyển warning thành lỗi build

~~~bash
javadoc -Xdoclint:all -Werror -d docs src/demo/*.java
~~~

-Werror yêu cầu Javadoc thất bại nếu còn warning. Đây là cách hữu ích trong CI để tránh tài liệu lỗi hoặc thiếu được đưa vào bản phát hành.

Có thể tăng số lượng chẩn đoán được in bằng -Xmaxerrs và -Xmaxwarns khi dự án có nhiều lỗi.

## 11. Ví dụ Java 17 hoàn chỉnh: từ comment đúng đến HTML

Cấu trúc:

~~~text
project/
  src/
    demo/
      Calculator.java
      Main.java
  classes/
  docs/
~~~

Tệp src/demo/Calculator.java:

~~~java
package demo;

/**
 * Provides small integer calculations.
 * <p>The examples use ordinary signed {@code int} values.</p>
 */
public final class Calculator {
    /** Creates a calculator. */
    public Calculator() {}

    /**
     * Returns twice the supplied value.
     *
     * @param value the value to double
     * @return the value multiplied by two
     */
    public int twice(int value) {
        return value * 2;
    }

    /**
     * Adds two values.
     *
     * @param left the first value
     * @param right the second value
     * @return the sum of the values
     * @see #twice(int)
     */
    public int add(int left, int right) {
        return left + right;
    }
}
~~~

Tệp src/demo/Main.java:

~~~java
package demo;

/** Runs a small calculation example. */
public final class Main {
    /** Creates the entry point. */
    public Main() {}

    /**
     * Starts the example.
     *
     * @param args command-line arguments (not used)
     */
    public static void main(String[] args) {
        Calculator calculator = new Calculator();
        System.out.println("twice=" + calculator.twice(6));
        System.out.println("sum=" + calculator.add(4, 5));
    }
}
~~~

Biên dịch mã nguồn:

~~~bash
javac --release 17 -encoding UTF-8 -d classes \
    src/demo/Calculator.java src/demo/Main.java
~~~

Chạy chương trình:

~~~bash
java -cp classes demo.Main
~~~

Stdout chính xác:

~~~text
twice=12
sum=9
~~~

Tạo Javadoc với tất cả kiểm tra và warnings-as-errors:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror \
    -encoding UTF-8 -d docs \
    src/demo/Calculator.java src/demo/Main.java
~~~

Nếu lệnh thành công, thư mục docs/demo/ có các trang Calculator.html và Main.html, cùng các trang package và index.

Ví dụ này kiểm tra cả source Java lẫn tài liệu. Nếu xóa comment constructor, đổi @param value thành @param input, hoặc đổi @see #twice(int) thành một member không tồn tại, bước Javadoc có thể báo warning hoặc error tùy nhóm kiểm tra được bật.

## 12. Quy trình sửa tài liệu không hợp lệ

Khi Javadoc báo lỗi, hãy làm theo thứ tự:

1. Đọc đầy đủ thông báo, file, số dòng và vị trí dấu ^.
2. Xác định nhóm lỗi: HTML, accessibility, missing, reference hay syntax.
3. Mở đúng documentation comment được chỉ ra.
4. Kiểm tra declaration mà comment đang mô tả: class, constructor, method hay field.
5. Đối chiếu @param, @return, @throws với chữ ký Java thực tế.
6. Kiểm tra từng @see, {@link} và overload.
7. Sửa HTML, inline tag và accessibility.
8. Chạy lại Javadoc với đúng nhóm kiểm tra.
9. Dùng -Werror trước khi phát hành để không bỏ sót warning.

Ví dụ chẩn đoán:

~~~text
Calculator.java:12: error: reference not found
 * @see MissingType
        ^
~~~

Hãy tìm xem MissingType có thực sự tồn tại, có được import hoặc nằm trong module/package mà Javadoc phân giải được không. Nếu ý định là liên kết đến Calculator, sửa tham chiếu thành @see Calculator.

Không chỉ xóa tag để làm build xanh. Hãy sửa comment để mô tả đúng hợp đồng API.

## 13. Tích hợp kiểm tra Javadoc vào CI

Một pipeline cơ bản có thể chạy biên dịch trước, sau đó tạo tài liệu với DocLint:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes \
    src/demo/Calculator.java src/demo/Main.java

javadoc --release 17 -Xdoclint:all -Werror \
    -encoding UTF-8 -d build/docs \
    src/demo/Calculator.java src/demo/Main.java
~~~

Nếu dự án có nhiều package, dùng source path hoặc package list theo cấu trúc source thực tế. Đảm bảo Javadoc nhìn thấy các dependency, module và source cần thiết để giải quyết link.

Một số nguyên tắc:

- Dùng cùng phiên bản JDK trong máy local và CI.
- Giữ -encoding UTF-8 khi source có tiếng Việt hoặc ký tự Unicode.
- Bật -Xdoclint:all khi muốn kiểm tra cả missing documentation.
- Bật -Werror khi muốn mọi warning chặn phát hành.
- Chỉ tắt một nhóm khi đã ghi rõ lý do và có kiểm tra thay thế.
- Kiểm tra cả link nội bộ lẫn link ngoài nếu build có dùng -link hoặc -linkoffline.
- Lưu lại HTML sinh ra như artifact để reviewer kiểm tra.

## 14. Lỗi thường gặp và cách xử lý

### Javadoc vẫn sinh HTML dù có error

Javadoc có thể tiếp tục tạo một số file để báo cáo nhiều lỗi trong một lần chạy. HTML sinh ra có thể chứa diagnostic marker và không phải kết quả hợp lệ để phát hành. Hãy căn cứ vào error và exit code, không chỉ nhìn thấy file HTML là kết luận thành công.

### -Xdoclint:none vẫn có warning

Tùy chọn này tắt DocLint, nhưng standard doclet hoặc các bước kiểm tra khác vẫn có thể phát ra warning. Hãy đọc nội dung cảnh báo để xác định nguồn; không coi none là chế độ bảo đảm không có cảnh báo.

### -Xdoclint:all làm build thất bại vì thiếu comment

Nhóm missing kiểm tra những phần tử chưa được mô tả. Nếu dự án chưa có chính sách tài liệu đầy đủ, có thể dùng -Xdoclint:all,-missing trong giai đoạn chuyển đổi, sau đó bổ sung comment và bật lại all.

### Tham chiếu đúng trong IDE nhưng Javadoc không tìm thấy

IDE có thể dùng classpath hoặc module path khác với lệnh build. Đảm bảo lệnh Javadoc nhận đúng --class-path, --module-path, --source-path và dependency tương ứng.

### HTML hợp lệ về hình thức nhưng DocLint vẫn báo lỗi

HTML có thể hiển thị trong trình duyệt nhưng vẫn thiếu yêu cầu accessibility. Kiểm tra alt cho ảnh, caption cho bảng và cấu trúc heading/table.

### Tag tùy chỉnh không được nhận diện

Đăng ký custom tag bằng -tag, hoặc triển khai Taglet và truyền -tagletpath/-taglet. Kiểm tra vị trí tag được phép và cách xử lý nội dung của tag.

## 15. Checklist trước khi phát hành Javadoc

- [ ] Mỗi class, constructor và API cần công bố có documentation comment phù hợp.
- [ ] HTML mở/đóng đúng và dùng cấu trúc hợp lệ.
- [ ] Hình ảnh có alt mô tả phù hợp.
- [ ] Bảng có caption và heading rõ ràng.
- [ ] @param khớp tên tham số hoặc type parameter.
- [ ] @return chỉ dùng cho method có giá trị trả về.
- [ ] @throws mô tả ngoại lệ phù hợp.
- [ ] @see và {@link} phân giải được.
- [ ] Inline tag có đủ dấu ngoặc và cú pháp đúng.
- [ ] Custom tag đã được đăng ký.
- [ ] DocLint đã chạy với các nhóm cần thiết.
- [ ] CI dùng -Werror nếu warning phải chặn phát hành.
- [ ] HTML output được kiểm tra trước khi phân phối.
