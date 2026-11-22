# Doc comment và Javadoc trong Java

## Mục tiêu

Sau bài này, bạn có thể phân biệt comment thông thường với documentation comment; viết doc comment đúng vị trí cho class, field, constructor và method; dùng block tag và inline tag để mô tả API; tạo tài liệu HTML bằng công cụ javadoc; kiểm tra lỗi bằng DocLint; tổ chức tài liệu cho package/module; và sử dụng các tính năng Markdown comment, code snippet trong những phiên bản JDK phù hợp.

## 1. Doc comment là gì?

**Doc comment (documentation comment)** là comment có cấu trúc được đặt gần một khai báo Java để mô tả cách sử dụng, ý nghĩa, điều kiện và kết quả của API đó. Công cụ **javadoc** đọc các doc comment cùng khai báo trong source code rồi tạo tài liệu API, mặc định là các trang HTML.

Doc comment giúp người dùng thư viện hiểu:

- Class hoặc interface dùng để làm gì.
- Constructor tạo object trong điều kiện nào.
- Method nhận tham số gì và trả về giá trị nào.
- Method có thể ném exception nào và trong trường hợp nào.
- Field hoặc constant đại diện cho giá trị gì.
- API được giới thiệu từ phiên bản nào hoặc đã bị thay thế chưa.
- Các method có quan hệ với nhau như thế nào.

Doc comment là một phần của source documentation. Nội dung của nó không thay đổi logic chương trình, không tự kiểm tra hợp đồng ở runtime và không thay thế việc viết test. Một mô tả nói rằng method không nhận null cũng không khiến JVM tự động từ chối null; code phải thực thi điều kiện đó nếu API yêu cầu.

## 2. Phân biệt các loại comment

Java có comment thông thường và documentation comment:

| Cú pháp | Tên | Javadoc xử lý như tài liệu API? |
|---|---|---|
| // ... | Line comment | Không |
| /* ... */ | Traditional comment | Không |
| /** ... */ | Traditional documentation comment | Có |
| /// ... | Markdown documentation comment | Có từ JDK 23 |

Ví dụ comment thông thường:

~~~java
// Tính tổng hai số.
int total = 2 + 3;

/*
 * Phần này giải thích một đoạn code.
 */
~~~

Hai comment trên chỉ dành cho người đọc source. Công cụ javadoc không dùng chúng để tạo mô tả API.

Traditional doc comment bắt đầu bằng ba ký tự slash-star:

~~~java
/**
 * Adds two integers and returns their sum.
 *
 * @param left first addend
 * @param right second addend
 * @return the sum of the two values
 */
public static int add(int left, int right) {
    return left + right;
}
~~~

Javadoc nhận diện doc comment khi nó đứng ngay trước khai báo được mô tả. Comment nên nằm trước annotation, modifier, keyword hoặc tên khai báo. Nếu có nhiều doc comment trước cùng một khai báo, chỉ comment gần khai báo nhất được sử dụng. Comment đặt sau khi khai báo đã bắt đầu sẽ không được gắn vào khai báo đó.

Doc comment có thể áp dụng cho module, package, class, interface, constructor, method, annotation element, enum member và field. Không dùng doc comment để mô tả một local variable hoặc một câu lệnh bất kỳ bên trong method.

## 3. Viết traditional doc comment đúng cấu trúc

Một doc comment truyền thống thường có dạng:

~~~java
/**
 * Main description: giải thích ngắn gọn khai báo này làm gì.
 *
 * Có thể bổ sung cách sử dụng, điều kiện, ví dụ và lưu ý.
 *
 * @param name mô tả tham số
 * @return mô tả giá trị trả về
 * @throws IllegalArgumentException mô tả trường hợp ném exception
 * @since 1.0
 */
~~~

Phần nội dung trước block tag đầu tiên được gọi là **main description**. Nội dung này không tiếp tục sau khi block tag đã bắt đầu. Các thông tin bổ sung được viết bằng block tag ở những dòng riêng.

### Viết câu summary đầu tiên

Câu đầu tiên của main description nên là một câu ngắn, đầy đủ và mô tả chính xác khai báo. Javadoc thường dùng câu đầu này trong bảng summary, index và những vị trí cần mô tả ngắn.

Ví dụ tốt:

~~~java
/**
 * Converts a temperature from Celsius to Fahrenheit.
 */
~~~

Ví dụ chưa tốt:

~~~java
/**
 * This method. It does some conversion.
 */
~~~

Tránh mở đầu bằng những câu chung chung như “This method does something”. Hãy mô tả hành vi cụ thể, đầu vào hoặc kết quả quan trọng.

Nếu muốn chỉ rõ câu summary thay vì phụ thuộc cách Javadoc xác định câu đầu, có thể dùng inline tag {@summary ...} ở đầu main description:

~~~java
/**
 * {@summary Adds two integers and returns their sum.}
 *
 * The method uses normal Java integer arithmetic.
 */
~~~

### Viết đoạn văn và HTML

Traditional doc comment hỗ trợ văn bản, inline tag và HTML. Có thể dùng các phần tử HTML5 như:

- p để tách đoạn.
- ul và li để liệt kê.
- pre để giữ định dạng khối.
- a để tạo liên kết.
- code để hiển thị tên API hoặc đoạn code ngắn.

Ví dụ:

~~~java
/**
 * Reads a configuration value.
 *
 * <p>The method checks the supplied key before returning its value.
 *
 * <ul>
 *   <li>Keys are case-sensitive.</li>
 *   <li>A missing key returns the default value.</li>
 * </ul>
 */
~~~

Không dùng HTML sai cấu trúc. Khi viết ký tự đặc biệt như dấu nhỏ hơn, lớn hơn hoặc ampersand trong mô tả, dùng HTML entity hoặc inline tag phù hợp để tránh Javadoc hiểu nhầm chúng là markup.

Nếu viết heading HTML trong doc comment, hãy chọn cấp heading phù hợp với vị trí khai báo để cấu trúc trang HTML được tạo ra hợp lý. Với class/package/module, heading trong comment thường bắt đầu từ cấp 2; với method/field/member thường bắt đầu từ cấp 4. Markdown documentation comments có quy tắc heading riêng.

## 4. Các block tag quan trọng

Block tag bắt đầu bằng ký tự @ ở đầu một dòng, sau phần main description. Tên tag và đối tượng được mô tả phải đúng với khai báo.

### @param

Dùng để mô tả từng tham số của method hoặc constructor. Mỗi formal parameter nên có một tag tương ứng:

~~~java
/**
 * Returns the larger of two values.
 *
 * @param first first value to compare
 * @param second second value to compare
 * @return the larger value
 */
public static int max(int first, int second) {
    return Math.max(first, second);
}
~~~

Với generic method, type parameter cũng được mô tả bằng @param. Tên type parameter phải đặt trong dấu ngoặc nhọn:

~~~java
/**
 * Returns the supplied value.
 *
 * @param <T> type of the value
 * @param value value to return
 * @return the same value
 */
public static <T> T identity(T value) {
    return value;
}
~~~

Ở đây có hai loại tham số cần phân biệt: <T> là type parameter, còn value là formal parameter.

### @return

Dùng cho method có kiểu trả về khác void. Hãy mô tả ý nghĩa và điều kiện của giá trị trả về, không chỉ lặp lại tên kiểu.

~~~java
/**
 * Calculates the area of a rectangle.
 *
 * @param width rectangle width
 * @param height rectangle height
 * @return the rectangle area
 */
public static double area(double width, double height) {
    return width * height;
}
~~~

Method trả về void không dùng block tag @return. Nếu method trả về boolean, mô tả rõ điều kiện true và false có ý nghĩa gì.

### @throws và @exception

Dùng để mô tả exception có thể được method hoặc constructor ném ra:

~~~java
/**
 * Divides one integer by another.
 *
 * @param numerator number being divided
 * @param denominator divisor
 * @return integer quotient
 * @throws IllegalArgumentException if denominator is zero
 */
public static int divide(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException("denominator must not be zero");
    }
    return numerator / denominator;
}
~~~

@exception là tên tag cũ tương đương, nhưng nên ưu tiên @throws.

Mô tả exception phải nói rõ điều kiện phát sinh. Không cần liệt kê mọi lỗi có thể xảy ra trong JVM; hãy tập trung vào những trường hợp có ý nghĩa với hợp đồng API.

Checked exception xuất hiện trong throws clause nên được mô tả. Unchecked exception có thể không xuất hiện trong throws clause nhưng vẫn có thể được ghi bằng @throws nếu người dùng API cần biết.

### @see

Dùng để dẫn đến class, method, field, package hoặc tài liệu liên quan:

~~~java
/**
 * Returns the absolute value of a number.
 *
 * @param value input value
 * @return absolute value
 * @see Math#abs(int)
 */
public static int absolute(int value) {
    return Math.abs(value);
}
~~~

Nếu muốn chèn liên kết ngay trong câu mô tả, hãy dùng inline tag {@link ...} hoặc {@linkplain ...}.

### @since

Cho biết API được giới thiệu từ phiên bản nào:

~~~java
/**
 * Returns a normalized identifier.
 *
 * @param value identifier to normalize
 * @return normalized identifier
 * @since 2.1
 */
~~~

@since nên phản ánh phiên bản sản phẩm/thư viện thực tế. Không tự ghi phiên bản JDK nếu API thuộc phiên bản ứng dụng và không có quan hệ trực tiếp.

### @deprecated

Dùng để cảnh báo API không còn được khuyến nghị và chỉ ra API thay thế. Nên kết hợp tag này với annotation @Deprecated:

~~~java
/**
 * Adds two values using the legacy method name.
 *
 * @deprecated since 2.0; use {@link #add(int, int)} instead.
 */
@Deprecated(since = "2.0")
public static int sumLegacy(int left, int right) {
    return add(left, right);
}
~~~

Câu đầu của phần deprecated nên nêu phiên bản deprecate và API thay thế. Nếu có lý do tương thích hoặc bảo trì, bổ sung ở các câu sau.

### @author và @version

- @author ghi tác giả hoặc nhóm chịu trách nhiệm.
- @version ghi version của phần mềm hoặc thành phần được mô tả.

Hai tag này chỉ được hiển thị khi dùng tùy chọn tương ứng, chẳng hạn -author và -version. Không thêm tag chỉ để lấp chỗ trống; hãy tuân theo quy ước tài liệu của dự án.

### Tag dành cho serialization và module

Một số tag có phạm vi chuyên biệt:

| Tag | Mục đích |
|---|---|
| @serial | Mô tả serializable field hoặc trạng thái serialized |
| @serialField | Mô tả field trong serialPersistentFields |
| @serialData | Mô tả dữ liệu do serialization method ghi |
| @uses | Ghi nhận service mà module sử dụng |
| @provides | Ghi nhận service provider mà module cung cấp |

Các tag @uses và @provides chỉ dùng trong doc comment của module declaration. Chúng giúp tài liệu module thể hiện quan hệ service của JPMS.

## 5. Các inline tag thường dùng

Inline tag có dạng {@tag ...} và có thể xuất hiện bên trong câu mô tả.

| Inline tag | Công dụng |
|---|---|
| {@code text} | Hiển thị text bằng font code và không xử lý như HTML/tag lồng nhau |
| {@literal text} | Hiển thị nguyên văn mà không dùng font code |
| {@link reference} | Tạo liên kết đến API với kiểu chữ code |
| {@linkplain reference} | Tạo liên kết trong văn bản thông thường |
| {@value} | Hiển thị giá trị compile-time constant |
| {@inheritDoc} | Kế thừa phần tài liệu tương ứng từ method được override |
| {@summary text} | Chỉ định câu summary |
| {@docRoot} | Đường dẫn tương đối đến thư mục gốc của tài liệu được tạo |
| {@snippet ...} | Chèn code snippet có định dạng |

### @code và @literal

Dùng @code cho tên class, method, giá trị hoặc biểu thức:

~~~java
/**
 * Returns {@code true} when the collection is empty.
 */
~~~

Dùng @literal khi cần hiển thị nguyên văn nhưng không cần font code:

~~~java
/**
 * The text {@literal <unknown>} is used when no name is available.
 */
~~~

@code hữu ích khi văn bản có dấu < hoặc > vì nội dung được hiển thị như code, không bị diễn giải thành HTML tag.

### @link và @linkplain

Liên kết đến API ngay trong câu:

~~~java
/**
 * Use {@link String#isBlank()} to check whether a string contains
 * only whitespace characters.
 *
 * See also {@linkplain java.util.Objects Objects}.
 */
~~~

Một reference thường có dạng:

~~~text
package.Class#member(parameterTypes)
~~~

Nếu method bị overload, ghi danh sách kiểu tham số để Javadoc phân biệt đúng method. Có thể dùng label để thay đổi nội dung hiển thị của liên kết.

### @value

Dùng để chèn giá trị của static field có compile-time constant:

~~~java
/**
 * Default retry count: {@value}.
 */
public static final int DEFAULT_RETRIES = 3;
~~~

@value không tự gọi getter hoặc tính biểu thức runtime. Nó dành cho constant mà Javadoc có thể xác định giá trị tại thời điểm biên dịch.

### @inheritDoc

Khi override method, có thể kế thừa mô tả từ method ở superclass hoặc interface:

~~~java
/**
 * {@inheritDoc}
 */
@Override
public String toString() {
    return "Calculator";
}
~~~

Có thể bổ sung nội dung riêng nếu implementation có điều kiện hoặc hành vi đặc thù. Khi method override chỉ thay đổi một số tham số hoặc exception, cần kiểm tra phần nào có thể kế thừa và phần nào phải mô tả lại.

### @snippet

Tag @snippet được thêm trong JDK 18 để đưa code example vào tài liệu thuận tiện hơn so với chỉ dùng @code và pre:

~~~java
/**
 * Example:
 *
 * {@snippet :
 * int total = Calculator.add(7, 5);
 * System.out.println(total);
 * }
 */
~~~

Snippet có thể được viết trực tiếp trong comment, lấy từ file bên ngoài hoặc kết hợp cả hai. External snippet hữu ích khi ví dụ dài cần được biên dịch/test riêng trong source tree.

Một external snippet có thể đặt trong thư mục snippet-files theo package hoặc được tìm qua tùy chọn --snippet-path. Các markup comment trong snippet có thể đánh dấu vùng, highlight hoặc liên kết đoạn code.

Lưu ý: Javadoc đưa snippet vào tài liệu và hỗ trợ trình bày; đừng mặc định rằng mọi snippet đã được biên dịch và kiểm thử tự động. Hãy tổ chức test cho các ví dụ quan trọng trong build.

## 6. Markdown documentation comments từ JDK 23

Từ JDK 23, Javadoc hỗ trợ viết doc comment bằng Markdown theo JEP 467. Cú pháp dùng một chuỗi các dòng liên tiếp bắt đầu bằng ba dấu slash:

~~~java
/// # Calculator
///
/// Provides integer arithmetic operations.
///
/// Use the method [add(int, int)][#add(int, int)] to add two values.
///
/// @since 1.0
public final class Calculator {
    // declarations
}
~~~

Markdown comment hỗ trợ:

- Heading, paragraph, list và fenced code block.
- CommonMark links và simple GFM pipe tables.
- Inline tag và block tag của Javadoc.
- Liên kết thuận tiện đến program elements trong API.

Mọi dòng thuộc cùng một Markdown doc comment, kể cả dòng trống, phải bắt đầu bằng ///. Một dòng trống hoàn toàn sẽ kết thúc chuỗi comment. Nếu cần dòng trống, viết /// trên dòng đó.

Ví dụ:

~~~java
/// This comment contains two paragraphs.
///
/// The second paragraph is part of the same doc comment.
public void run() {
}
~~~

Không nên viết:

~~~java
/// This comment ends here.

/// This becomes a separate comment.
public void run() {
}
~~~

Trong ví dụ sai, dòng trống không có /// làm ngắt chuỗi Markdown doc comment.

Markdown doc comment có thể kết hợp JavaDoc tags và HTML khi cần. Không đặt JavaDoc tag bên trong literal code span hoặc fenced code block vì lúc đó tag được coi là nội dung code.

Nếu dự án cần hỗ trợ JDK 17 hoặc 21, hãy dùng traditional /** ... */ comments để tương thích. Markdown documentation comments yêu cầu JDK 23 trở lên.

## 7. Doc comment cho package và module

### package-info.java

Dùng file package-info.java để mô tả mục đích của package, các API chính, quy ước sử dụng và quan hệ với package khác.

~~~java
/**
 * Provides reusable arithmetic utilities.
 *
 * <p>Public classes in this package are intended for application code.
 */
package com.example.math;
~~~

File này có thể chứa package annotations và import statements. Đây là cách được khuyến nghị cho package documentation hiện đại; package.html chỉ còn được hỗ trợ vì lý do tương thích lịch sử.

### module-info.java

Module có thể có doc comment riêng:

~~~java
/**
 * Provides mathematical utilities for client applications.
 *
 * @uses java.util.spi.ToolProvider
 */
module com.example.math {
    exports com.example.math;
}
~~~

Khi module cung cấp hoặc sử dụng service, có thể mô tả bằng @provides và @uses trong doc comment module. Các tag này giải thích service contract và provider/service behavior cho người dùng module.

### doc-files

Có thể bổ sung tài liệu riêng cho package trong thư mục doc-files:

~~~text
src/
└── com/example/math/
    ├── package-info.java
    ├── Calculator.java
    └── doc-files/
        ├── usage.md
        └── architecture.html
~~~

Javadoc có thể xử lý file HTML hoặc Markdown trong doc-files. Dùng chúng cho hướng dẫn dài, sơ đồ, ví dụ nhiều bước hoặc tài liệu không phù hợp để đặt trực tiếp trong comment của một declaration.

## 8. Ví dụ hoàn chỉnh: viết doc comment và tạo Javadoc

Tạo file src/com/example/Calculator.java:

~~~java
package com.example;

/**
 * Provides small integer arithmetic utilities.
 *
 * <p>Use {@link #add(int, int)} to add values and
 * {@link #divide(int, int)} for integer division.
 *
 * @since 1.0
 * @see java.lang.Math
 */
public final class Calculator {

    /**
     * Default number of retry attempts used by examples.
     */
    public static final int DEFAULT_RETRIES = 3;

    private Calculator() {
    }

    /**
     * Adds two integers.
     *
     * @param left first addend
     * @param right second addend
     * @return sum of left and right
     * @since 1.0
     */
    public static int add(int left, int right) {
        return left + right;
    }

    /**
     * Divides one integer by another using integer division.
     *
     * @param numerator value being divided
     * @param denominator divisor
     * @return quotient rounded toward zero
     * @throws IllegalArgumentException if denominator is zero
     */
    public static int divide(int numerator, int denominator) {
        if (denominator == 0) {
            throw new IllegalArgumentException(
                    "denominator must not be zero");
        }
        return numerator / denominator;
    }

    /**
     * Returns the supplied value after checking that it is not null.
     *
     * @param <T> type of the supplied value
     * @param value value to validate
     * @param name parameter name used in the exception message
     * @return the same value
     * @throws IllegalArgumentException if value is null
     */
    public static <T> T requireValue(T value, String name) {
        if (value == null) {
            throw new IllegalArgumentException(
                    name + " must not be null");
        }
        return value;
    }

    /**
     * Adds two values using the legacy method name.
     *
     * @deprecated since 2.0; use {@link #add(int, int)} instead.
     */
    @Deprecated(since = "2.0")
    public static int sumLegacy(int left, int right) {
        return add(left, right);
    }

    /**
     * Runs a small demonstration of the arithmetic methods.
     *
     * @param args command-line arguments; not used by this example
     */
    public static void main(String[] args) {
        System.out.println("sum=" + add(7, 5));
        System.out.println("quotient=" + divide(9, 2));
        System.out.println("value=" + requireValue("Java", "language"));
    }
}
~~~

Biên dịch chương trình với JDK 17 trở lên:

~~~bash
javac --release 17 -d out src/com/example/Calculator.java
~~~

Chạy:

~~~bash
java -cp out com.example.Calculator
~~~

Output chính xác:

~~~text
sum=12
quotient=4
value=Java
~~~

Tạo tài liệu HTML bằng javadoc:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -d docs src/com/example/Calculator.java
~~~

Sau khi chạy thành công, thư mục docs chứa các trang HTML của API, trong đó có:

~~~text
docs/
├── index.html
├── allclasses-index.html
└── com/
    └── example/
        └── Calculator.html
~~~

Tùy phiên bản JDK và cấu hình standard doclet, thư mục có thể có thêm CSS, JavaScript, search index và các trang navigation.

Ví dụ này minh họa:

- Doc comment ở class và method.
- @param cho tham số thường và type parameter.
- @return và @throws.
- @since, @see và @deprecated.
- Inline link đến method khác.
- Constant field có thể mô tả bằng {@value}.
- Một chương trình có thể biên dịch và chạy độc lập với bước tạo tài liệu.

## 9. Các tùy chọn javadoc thường dùng

| Tùy chọn | Mục đích |
|---|---|
| -d docs | Chọn thư mục lưu tài liệu HTML |
| -sourcepath src | Chọn thư mục chứa source package |
| -subpackages com.example | Sinh docs cho package và subpackage |
| -public | Chỉ tạo tài liệu cho public API |
| -protected | Tạo tài liệu cho public và protected API; đây là mặc định |
| -package | Bao gồm cả package-private API |
| -private | Bao gồm cả private API |
| -author | Hiển thị @author |
| -version | Hiển thị @version |
| -link URL | Liên kết tới Javadoc của thư viện/API bên ngoài |
| -Xdoclint:all | Bật toàn bộ nhóm kiểm tra DocLint |
| -Werror | Chuyển warning thành lỗi |

Sinh tài liệu cho toàn bộ package và subpackage:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example
~~~

Nếu tài liệu tham chiếu API Java SE bên ngoài, có thể liên kết tới Javadoc của JDK:

~~~bash
javadoc --release 17 -d docs -link https://docs.oracle.com/en/java/javase/17/docs/api/ -sourcepath src -subpackages com.example
~~~

URL truyền cho -link phải trỏ đến thư mục gốc của tài liệu Javadoc bên ngoài có element-list hoặc package-list phù hợp, không phải URL của một trang class đơn lẻ.

### Tùy chọn DocLint

DocLint giúp phát hiện lỗi thường gặp trong doc comment. Các nhóm kiểm tra chính:

| Nhóm | Nội dung |
|---|---|
| accessibility | Lỗi ảnh hưởng khả năng truy cập, ví dụ thiếu alt hoặc caption |
| html | HTML sai cấu trúc hoặc thiếu thẻ đóng |
| missing | Thiếu doc comment hoặc tag cần thiết |
| reference | Link tới class, method, parameter hoặc exception không hợp lệ |
| syntax | Sai cú pháp tag hoặc ký tự HTML cần escape |

javadoc bật DocLint mặc định cho tài liệu được tạo. Trong CI, có thể ghi rõ:

~~~bash
javadoc -Xdoclint:all -Werror -d docs src/com/example/Calculator.java
~~~

- -Xdoclint:all bật mọi nhóm kiểm tra.
- -Werror làm build thất bại nếu có warning.

Không nên tắt DocLint chỉ để build thành công khi có lỗi reference hoặc HTML. Hãy sửa nội dung gốc. DocLint không phải bộ kiểm tra HTML hoàn chỉnh; sau khi sinh tài liệu, dự án vẫn có thể dùng validator HTML/accessibility để kiểm tra output cuối cùng.

## 10. Quy tắc viết doc comment chất lượng

Một doc comment tốt trả lời câu hỏi của người sử dụng API, không chỉ lặp lại tên method.

### Mô tả hành vi và hợp đồng

Hãy mô tả:

- Điều kiện đầu vào hợp lệ.
- Giá trị mặc định hoặc giới hạn.
- Giá trị trả về có ý nghĩa gì.
- Side effect nếu có.
- Exception có thể xảy ra và nguyên nhân.
- Thread-safety hoặc tính bất biến nếu có ý nghĩa.
- Resource lifecycle: ai mở, ai đóng, ai sở hữu.

Ví dụ, thay vì viết “Gets user”, hãy giải thích method tìm user theo ID, trả về Optional.empty khi không tồn tại, và ném exception khi ID không hợp lệ nếu đó là hợp đồng thực tế.

### Không viết sai hoặc mơ hồ

Tránh những mô tả như:

- “Returns the result” mà không nói result là gì.
- “Throws exception on error” mà không nêu điều kiện.
- “Fast method” mà không có ngữ cảnh đo lường.
- “Thread-safe” khi implementation chưa bảo đảm.
- “Never null” khi code vẫn có thể trả null.

Nếu API có hành vi khác nhau theo input hoặc trạng thái object, hãy mô tả rõ từng trường hợp.

### Giữ tài liệu đồng bộ với code

Khi đổi tên tham số, kiểu trả về, exception, default value hoặc behavior, cập nhật doc comment trong cùng thay đổi. Không để documentation mô tả API cũ.

Nếu method override kế thừa hợp đồng từ interface, dùng @inheritDoc khi phù hợp. Nếu implementation có điều kiện bổ sung, hãy ghi rõ phần khác biệt.

### Viết ví dụ có thể kiểm chứng

Ví dụ code nên:

- Dùng đúng package/import và API hiện hành.
- Có output đúng với code.
- Không phụ thuộc vào môi trường không được nêu.
- Được biên dịch hoặc chạy trong test khi có thể.
- Có ghi rõ phiên bản JDK tối thiểu nếu sử dụng tính năng mới.

Với ví dụ dài, ưu tiên @snippet và file nguồn riêng để code có thể được test như một phần của dự án.

## 11. Lỗi thường gặp và cách xử lý

### Dùng /* ... */ thay vì /** ... */

**Dấu hiệu:** comment xuất hiện trong source nhưng không hiện trong tài liệu API.

**Nguyên nhân:** comment thường không được standard doclet xem là documentation comment.

**Cách xử lý:** dùng /** ... */ hoặc Markdown /// phù hợp phiên bản JDK.

### Đặt doc comment sai vị trí

**Dấu hiệu:** Javadoc không gắn comment với method/class mong muốn.

**Nguyên nhân:** có annotation, modifier, khai báo hoặc một comment khác chen giữa vị trí comment và declaration.

**Cách xử lý:** đặt doc comment ngay trước annotation và declaration. Chỉ giữ một doc comment cho mỗi declaration.

### Thiếu @param hoặc @return

**Dấu hiệu:** DocLint cảnh báo method documentation thiếu thông tin.

**Nguyên nhân:** thiếu tag cho tham số hoặc kiểu trả về, hoặc tên tham số trong tag không trùng source.

**Cách xử lý:** đối chiếu từng formal parameter và type parameter; thêm @return cho method không void.

### Viết sai tên type parameter

**Dấu hiệu:** tag không liên kết với type parameter hoặc DocLint báo lỗi reference.

**Nguyên nhân:** dùng @param T thay vì @param <T>.

**Cách xử lý:** ghi type parameter trong dấu ngoặc nhọn, sau đó ghi các tham số thường theo đúng tên khai báo.

### Link tới method overload không rõ

**Dấu hiệu:** link không được phân giải hoặc trỏ nhầm method.

**Nguyên nhân:** bỏ danh sách tham số trong khi class có nhiều overload cùng tên.

**Cách xử lý:** ghi đầy đủ reference như #add(int, int) hoặc tên kiểu được import/fully qualified phù hợp.

### Ký tự < và > làm hỏng HTML

**Dấu hiệu:** Javadoc báo lỗi syntax hoặc HTML hiển thị sai.

**Nguyên nhân:** dùng ký tự đặc biệt như markup mà không escape.

**Cách xử lý:** dùng {@code ...}, {@literal ...} hoặc HTML entity phù hợp.

### @deprecated không có API thay thế

**Dấu hiệu:** người dùng biết API cũ không nên dùng nhưng không biết thay bằng gì.

**Nguyên nhân:** thiếu chỉ dẫn trong phần deprecated.

**Cách xử lý:** kết hợp @Deprecated với @deprecated, nêu phiên bản deprecate và liên kết đến API thay thế.

### Markdown comment bị ngắt

**Dấu hiệu:** chỉ một phần nội dung được nhận diện là doc comment.

**Nguyên nhân:** có dòng trống không bắt đầu bằng /// hoặc comment khác chen giữa các dòng.

**Cách xử lý:** bảo đảm mọi dòng trong chuỗi Markdown doc comment, kể cả dòng trống, đều bắt đầu bằng ///. Tính năng này yêu cầu JDK 23 trở lên.

### Javadoc tạo HTML nhưng vẫn có lỗi nội dung

**Dấu hiệu:** lệnh javadoc chạy xong nhưng trang docs có link sai hoặc mô tả thiếu.

**Nguyên nhân:** không phải mọi lỗi nội dung đều làm tool thất bại; DocLint cũng chỉ phát hiện một số nhóm vấn đề.

**Cách xử lý:** dùng -Xdoclint:all -Werror, kiểm tra HTML được tạo và review nội dung API như một phần của code review.

## 12. Checklist trước khi merge

- [ ] Doc comment đặt ngay trước declaration cần mô tả.
- [ ] Câu đầu tiên là summary ngắn gọn và chính xác.
- [ ] Mọi tham số có @param tương ứng.
- [ ] Generic type parameter dùng cú pháp @param <T>.
- [ ] Method không void có @return.
- [ ] Exception quan trọng có @throws và điều kiện phát sinh rõ ràng.
- [ ] Link dùng reference đúng, đặc biệt với method overload.
- [ ] API deprecated có @Deprecated và chỉ dẫn thay thế.
- [ ] @since phản ánh đúng phiên bản API.
- [ ] HTML và inline tag có cú pháp hợp lệ.
- [ ] Markdown /// chỉ dùng khi toolchain hỗ trợ JDK 23+.
- [ ] Snippet được kiểm thử riêng khi chứa ví dụ quan trọng.
- [ ] javadoc chạy thành công với DocLint.
- [ ] Tài liệu HTML được review cùng thay đổi source.

## 13. Tài liệu tham khảo chính thức

- [JavaDoc Guide, Java SE 26](https://docs.oracle.com/en/java/javase/26/javadoc/index.html) — hướng dẫn sử dụng Javadoc, snippets và Markdown documentation comments.
- [Documentation Comment Specification for the Standard Doclet, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html) — vị trí doc comment, main description, block tag, inline tag, reference và quy tắc method documentation.
- [The javadoc Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html) — cú pháp lệnh, standard doclet, options, DocLint và cách sinh HTML.
- [Programmer's Guide to Snippets](https://docs.oracle.com/en/java/javase/22/javadoc/programmers-guide-snippets.html) — inline, external và hybrid snippets, markup regions và cách quản lý ví dụ code.
- [JEP 467: Markdown Documentation Comments](https://openjdk.org/jeps/467) — giới thiệu Markdown documentation comments trong JDK 23.
- [How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html) — hướng dẫn phong cách viết API documentation.

Doc comment biến source code thành tài liệu API có thể tạo và kiểm tra tự động. Hãy mô tả đúng hợp đồng của từng khai báo, dùng tag theo đúng ngữ cảnh và chạy Javadoc với DocLint trong quy trình build để tài liệu luôn đi cùng code.
