# `@link`: nối phần mã minh họa đến lớp, field, constructor hoặc method đích

## Mục tiêu bài học

Java 18 giới thiệu `{@snippet}` qua JEP 413. Ngoài việc tô nổi bật hoặc thay đổi phần chữ hiển thị, snippet còn có thể tạo **liên kết ngay trên tên trong đoạn mã**. Markup tag `@link` biến một phần văn bản trong snippet thành hyperlink đến trang tài liệu của một phần tử API.

Khả năng này tiếp tục được hỗ trợ trong JDK hiện đại. Nó hữu ích khi người đọc đang xem một ví dụ mã và muốn mở ngay tài liệu của lớp, field, constructor hoặc method được sử dụng.

Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`. Sau khi học, bạn có thể:

- Dùng `@link` để liên kết văn bản trong snippet đến một phần tử API.
- Viết đúng thuộc tính `target` theo cú pháp reference của `{@link}`.
- Liên kết đến class, field, constructor và method.
- Chỉ định danh sách tham số để phân biệt các overload.
- Chọn `type=link` hoặc `type=linkplain` cho kiểu hiển thị của liên kết.
- Mở rộng phạm vi liên kết qua nhiều dòng bằng `region`.
- Tránh liên kết chồng lấn và cấu hình liên kết đến API bên ngoài.

## 1. `@link` trong snippet giải quyết vấn đề gì?

Một ví dụ mã thường nhắc đến nhiều API:

~~~java
String normalized = input.strip();
System.out.println(normalized);
~~~

Người đọc có thể nhận ra tên method nhưng vẫn phải rời khỏi đoạn ví dụ để tìm tài liệu tương ứng. `@link` cho phép gắn liên kết vào chính chữ `strip()` hoặc `println` trong khối mã.

Ví dụ:

~~~java
/**
 * Chuẩn hóa chuỗi đầu vào:
 * {@snippet :
 *     String normalized = input.strip(); // @link substring="strip()" target="java.lang.String#strip()"
 * }
 */
public class StringSnippetDoc {
}
~~~

Khi `javadoc` tạo HTML:

- Dòng mã vẫn được hiển thị.
- Comment điều khiển `// @link ...` bị lược khỏi khối mã.
- Văn bản `strip()` trở thành một liên kết đến tài liệu method `String.strip()` nếu target được phân giải thành công.

`@link` là **markup comment nằm trong snippet**. Nó khác với `{@link ...}` ở phần văn xuôi của Javadoc:

| Cú pháp | Vị trí | Tác dụng |
| --- | --- | --- |
| `{@link String#strip()}` | Phần mô tả bằng văn bản của Javadoc. | Tạo liên kết inline trong câu văn. |
| `// @link substring="strip()" target="java.lang.String#strip()"` | Comment bên trong nội dung snippet. | Tạo liên kết ngay trên phần mã được chọn. |

Cả hai dùng chung quy tắc tham chiếu đến phần tử API, nhưng phục vụ hai vị trí hiển thị khác nhau.

## 2. Cú pháp của markup tag `@link`

Cú pháp tổng quát:

~~~text
// @link [substring="văn bản" | regex="biểu_thức"] [region="tên_vùng"] target="API_REFERENCE" [type=link|linkplain]
~~~

Các thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `substring` | Chọn mỗi lần xuất hiện của chuỗi ký tự nguyên văn trong phạm vi. |
| `regex` | Chọn mỗi đoạn văn bản khớp biểu thức chính quy trong phạm vi. |
| `region` | Mở rộng phạm vi liên kết từ dòng hiện tại sang một region kết thúc bằng `@end` tương ứng. |
| `target` | Đích liên kết, viết theo cú pháp reference dùng bởi `{@link}`. |
| `type` | Kiểu liên kết: `link` (mặc định) hoặc `linkplain`. |

**Hai quyết định độc lập:**

1. `substring`, `regex` và `region` xác định **đoạn mã nào được gắn liên kết**.
2. `target` xác định **liên kết dẫn tới đâu**; `type` xác định cách hiển thị liên kết.

Nếu không có `substring` hoặc `regex`, toàn bộ phạm vi được liên kết. Phạm vi mặc định là dòng chứa markup comment; nếu có `region`, phạm vi là các dòng trong region đó. Vì vậy, hãy chỉ định selector khi không muốn biến cả dòng mã thành một liên kết.

Ví dụ liên kết đúng một tên method:

~~~java
item.strip(); // @link substring="strip()" target="java.lang.String#strip()"
~~~

Ví dụ liên kết tất cả lần xuất hiện của một chuỗi trong một dòng:

~~~java
System.out.println("done"); // @link substring="println" target="java.io.PrintStream#println(java.lang.String)"
~~~

Ví dụ trên chỉ phù hợp nếu `println` được dùng với đối số `String`. Nếu dòng có overload khác, cần chọn đúng target tương ứng.

## 3. Hiểu cú pháp `target`: class và member reference

`target` sử dụng cùng dạng tham chiếu phần tử chương trình như `{@link ...}`. Dạng tổng quát:

~~~text
module/package.Class#member
~~~

Các phần đầu có thể lược bỏ nếu `javadoc` suy ra được từ ngữ cảnh, nhưng khi viết bài học hoặc ví dụ có thể tái sử dụng, nên ghi rõ tên class và member để dễ đọc.

| Loại đích | Ví dụ target | Ý nghĩa |
| --- | --- | --- |
| Class hoặc interface | `java.lang.String` | Trang tài liệu của kiểu `String`. |
| Field | `java.lang.System#out` | Field `out` của `System`. |
| Enum constant | `java.time.DayOfWeek#MONDAY` | Hằng enum `MONDAY`. |
| Constructor | `java.lang.String#String()` | Constructor không tham số của `String`. |
| Method | `java.lang.String#strip()` | Method `strip()` của `String`. |
| Overloaded method | `java.io.PrintStream#println(java.lang.String)` | Overload nhận một tham số kiểu `String`. |

Một reference có thể trỏ đến constructor, method, field, enum member hoặc class/interface. Đối với constructor, tên member dùng chính tên class. Dấu `#` ngăn cách class với member.

### 3.1. Liên kết đến class

~~~java
LinkTargets item; // @link substring="LinkTargets" target="LinkTargets"
~~~

Ở đây, chữ `LinkTargets` được nối đến tài liệu của class `LinkTargets` trong cùng package hoặc trong bộ tài liệu được tạo.

Có thể dùng tên đầy đủ:

~~~java
String value; // @link substring="String" target="java.lang.String"
~~~

Dùng tên đầy đủ giúp tránh nhầm khi có nhiều class cùng tên trong các package khác nhau.

### 3.2. Liên kết đến field

~~~java
int limit = LinkTargets.DEFAULT_LIMIT; // @link substring="DEFAULT_LIMIT" target="LinkTargets#DEFAULT_LIMIT"
~~~

`target` có dạng `Class#fieldName`. Chỉ phần `DEFAULT_LIMIT` được chọn, còn các phần khác của dòng không trở thành liên kết.

Field đích phải là một phần tử mà `javadoc` có thể phân giải và có tài liệu đích tương ứng. Nếu field không được đưa vào tập tài liệu được sinh, hoặc không có thông tin liên kết đến tài liệu ngoài, liên kết có thể không được tạo như mong muốn.

### 3.3. Liên kết đến constructor

Constructor được tham chiếu bằng tên class sau dấu `#`:

~~~java
item = new LinkTargets("A"); // @link substring="new LinkTargets" target="LinkTargets#LinkTargets(java.lang.String)"
~~~

Ở đây:

- `LinkTargets#LinkTargets(...)` chỉ constructor của class `LinkTargets`.
- `java.lang.String` là kiểu tham số constructor.
- Selector `new LinkTargets` khiến cả cụm được liên kết đến constructor, trong khi các phần khác của dòng vẫn là mã thông thường.

Nếu class có nhiều constructor, hãy ghi danh sách tham số để phân biệt chính xác. Không dựa vào tên constructor một mình khi có nhiều overload.

### 3.4. Liên kết đến method

~~~java
String value = item.value(); // @link substring="value()" target="LinkTargets#value()"
~~~

Reference `LinkTargets#value()` trỏ đến method `value()`. Dấu ngoặc đơn thể hiện danh sách tham số rỗng.

Với method nhận tham số:

~~~java
LinkTargets result = LinkTargets.of("A"); // @link substring="of" target="LinkTargets#of(java.lang.String)"
~~~

Method `of` được chọn và nối đến overload có một tham số kiểu `String`.

## 4. Overload: vì sao nên ghi kiểu tham số trong target?

Một class có thể khai báo nhiều method cùng tên nhưng khác danh sách tham số:

~~~java
public static LinkTargets of(String value) { ... }

public static LinkTargets of(String value, int version) { ... }
~~~

Nếu chỉ ghi `LinkTargets#of`, `javadoc` có thể suy ra method khi tên đó là duy nhất. Nhưng khi có overload, reference nên ghi rõ tham số để đích không mơ hồ.

~~~java
LinkTargets first = LinkTargets.of("A"); // @link substring="of" target="LinkTargets#of(java.lang.String)"
LinkTargets second = LinkTargets.of("B", 2); // @link substring="of" target="LinkTargets#of(java.lang.String, int)"
~~~

Hai dòng đều chọn chữ `of`, nhưng target khác nhau:

- `LinkTargets#of(java.lang.String)` là overload nhận một tham số `String`.
- `LinkTargets#of(java.lang.String, int)` là overload nhận `String` và `int`.

Một số quy tắc khi viết parameter list:

- Tham số được ghi theo thứ tự khai báo của method hoặc constructor.
- Dùng tên kiểu đầy đủ nếu muốn reference dễ phân giải trong mọi ngữ cảnh.
- Có thể có khoảng trắng giữa các token trong parameter list, ví dụ `(java.lang.String, int)`.
- Nếu method hoặc constructor không overload và tên không trùng field/enum member trong cùng class, parameter list có thể được bỏ; tuy nhiên, ghi rõ chữ ký vẫn giúp ví dụ dễ kiểm tra hơn.

**Đừng nhầm selector với target:** `substring="of"` chọn văn bản `of` trong snippet; `target="LinkTargets#of(java.lang.String, int)"` chọn overload nhận hai tham số. Hai thuộc tính giải quyết hai vấn đề khác nhau.

## 5. Ví dụ hoàn chỉnh: liên kết class, field, constructor và method

Ta tạo một class API nhỏ để các đích liên kết đều nằm trong cùng bộ tài liệu. Cách này giúp kiểm tra từng loại reference mà không phụ thuộc vào tài liệu API bên ngoài.

File `LinkTargets.java`:

~~~java
/**
 * Một kiểu đơn giản dùng làm đích liên kết cho snippet.
 */
public final class LinkTargets {
    /** Giới hạn mặc định của ví dụ. */
    public static final int DEFAULT_LIMIT = 10;

    private final String value;

    /** Tạo một đối tượng từ chuỗi đầu vào. */
    public LinkTargets(String value) {
        this.value = value;
    }

    /** Trả về giá trị đã lưu. */
    public String value() {
        return value;
    }

    /** Tạo đối tượng với chuỗi đầu vào. */
    public static LinkTargets of(String value) {
        return new LinkTargets(value);
    }

    /** Tạo đối tượng với chuỗi và phiên bản. */
    public static LinkTargets of(String value, int version) {
        return new LinkTargets(value + "-" + version);
    }
}
~~~

File `SnippetLinkDoc.java`:

~~~java
/**
 * Ví dụ cho thấy cách gắn liên kết đến các loại API khác nhau.
 *
 * {@snippet :
 *     LinkTargets item; // @link substring="LinkTargets" target="LinkTargets"
 *     item = new LinkTargets("A"); // @link substring="new LinkTargets" target="LinkTargets#LinkTargets(java.lang.String)"
 *     int limit = LinkTargets.DEFAULT_LIMIT; // @link substring="DEFAULT_LIMIT" target="LinkTargets#DEFAULT_LIMIT"
 *     LinkTargets first = LinkTargets.of("A"); // @link substring="of" target="LinkTargets#of(java.lang.String)"
 *     LinkTargets second = LinkTargets.of("B", 2); // @link substring="of" target="LinkTargets#of(java.lang.String, int)"
 *     String text = item.value(); // @link substring="value()" target="LinkTargets#value()"
 * }
 */
public class SnippetLinkDoc {
}
~~~

Các liên kết được tạo:

| Văn bản trong snippet | Target | Phần tử đích |
| --- | --- | --- |
| `LinkTargets` | `LinkTargets` | Class. |
| `new LinkTargets` | `LinkTargets#LinkTargets(java.lang.String)` | Constructor. |
| `DEFAULT_LIMIT` | `LinkTargets#DEFAULT_LIMIT` | Field. |
| `of` ở dòng đầu | `LinkTargets#of(java.lang.String)` | Overload một tham số. |
| `of` ở dòng thứ hai | `LinkTargets#of(java.lang.String, int)` | Overload hai tham số. |
| `value()` | `LinkTargets#value()` | Method. |

Ở đây, mỗi markup comment chọn một đoạn riêng, nên các liên kết không chồng lên nhau. Comment điều khiển bị bỏ khỏi mã hiển thị; phần văn bản được chọn trở thành anchor link trong HTML.

## 6. `type=link` và `type=linkplain`

Markup `@link` hỗ trợ hai giá trị cho thuộc tính `type`:

| Giá trị | Ý nghĩa |
| --- | --- |
| `link` | Kiểu mặc định. Liên kết thường hiển thị theo font monospace, phù hợp với tên phần tử API trong đoạn mã. |
| `linkplain` | Liên kết được hiển thị theo kiểu chữ thông thường, không dùng kiểu monospace của code link. |

Ví dụ:

~~~java
int limit = LinkTargets.DEFAULT_LIMIT; // @link substring="DEFAULT_LIMIT" target="LinkTargets#DEFAULT_LIMIT" type=link
String name = item.value(); // @link substring="value()" target="LinkTargets#value()" type=linkplain
~~~

Cả hai đều tạo liên kết đến cùng loại đích API như trước. Thuộc tính `type` chỉ thay đổi cách trình bày chữ liên kết.

Thông thường:

- Dùng `link` cho tên class, method, field hoặc constructor trong mã.
- Dùng `linkplain` khi nhãn hiển thị là một cụm từ tự nhiên, hoặc khi muốn kiểu chữ của liên kết hòa vào văn bản.
- Nếu không ghi `type`, mặc định là `link`.

Đừng nhầm `type` của `@link` với `type` của `@highlight`. `@highlight` dùng `bold`, `italic` hoặc `highlighted`; `@link` dùng `link` hoặc `linkplain`.

## 7. Liên kết nhiều lần trong một region

Nếu một method xuất hiện nhiều lần trong nhiều dòng và tất cả cần trỏ đến cùng một tài liệu, có thể dùng `region`:

~~~java
/**
 * Các lời gọi value() đều dẫn đến cùng method:
 * {@snippet :
 *     // @link region="valueCalls" substring="value()" target="LinkTargets#value()" :
 *     String first = item.value();
 *     String second = another.value();
 *     String third = fallback.value();
 *     // @end region="valueCalls"
 * }
 */
public class RegionLinkDoc {
}
~~~

`@link region="valueCalls"` mở phạm vi liên kết. Selector `substring="value()"` được áp dụng trên các dòng trong region; mỗi lần xuất hiện của `value()` đều được nối đến `LinkTargets#value()`. Dòng marker `@end` kết thúc phạm vi.

Nếu bỏ `region`, selector chỉ được áp dụng trên dòng chứa markup comment. Nếu bỏ cả `substring` lẫn `regex`, toàn bộ region sẽ trở thành liên kết. Cần cân nhắc điều này trước khi dùng vì một vùng lớn có thể biến cả đoạn mã thành một anchor duy nhất.

Region cũng có thể được mở bằng `@start region=...` rồi kết thúc bằng `@end region=...`. Riêng `@link region=...` có thể vừa mở region, vừa xác định hành vi liên kết trong vùng đó.

## 8. Không để các liên kết chồng lấn

`javadoc` báo lỗi nếu nhiều markup `@link` cùng áp dụng lên một phần văn bản. Các liên kết chồng lấn có thể xuất phát từ hai selector `substring` hoặc `regex` khác nhau.

Ví dụ không nên tạo:

~~~java
item.value(); // @link substring="value" target="LinkTargets#value()" @link substring="value()" target="LinkTargets#value()"
~~~

Hai selector cùng chọn phần `value` trong `value()`. Vì vậy, một vùng văn bản nhận nhiều target là trường hợp không hợp lệ.

Cách sửa là chọn một selector duy nhất cho mỗi đoạn, hoặc chia ví dụ thành những dòng khác nhau nếu cần các đích khác nhau:

~~~java
String value = item.value(); // @link substring="value()" target="LinkTargets#value()"
LinkTargets copy = LinkTargets.of("A"); // @link substring="of" target="LinkTargets#of(java.lang.String)"
~~~

Khi dùng regex, hãy kiểm tra các lần khớp thực tế. Một mẫu rộng như `.*` có thể làm toàn bộ dòng trở thành một liên kết, gây chồng lấn với một markup link khác trên cùng vùng.

## 9. Liên kết đến API bên ngoài

Khi target nằm trong một class được tạo tài liệu ở cùng lần chạy `javadoc`, standard doclet có thể tạo liên kết trực tiếp. Khi target nằm trong một bộ tài liệu API bên ngoài, cần cung cấp thông tin liên kết ngoài phù hợp.

Ví dụ snippet tham chiếu đến `java.lang.String#strip()` hoặc `java.io.PrintStream#println(java.lang.String)`. Khi cần nối tới tài liệu Java SE được phát hành độc lập với source của dự án, có thể cấu hình tùy chọn `-link` hoặc `-linkoffline` của `javadoc`.

Ví dụ với bộ tài liệu Java SE 26:

~~~bash
javadoc -d docs -link https://docs.oracle.com/en/java/javase/26/docs/api/ LinkExternalDoc.java
~~~

URL phải tương ứng với bộ tài liệu API mà bạn muốn tham chiếu. Nếu xây dựng tài liệu với JDK khác, hãy chọn URL version phù hợp và kiểm tra liên kết đầu ra. `-linkoffline` phù hợp khi muốn dùng package-list hoặc element-list đã tải sẵn, không cần tải tài liệu API trực tiếp trong lần chạy.

Nếu thiếu thông tin liên kết ngoài, target có thể không tạo được hyperlink đúng dù cú pháp `@link` đã viết đúng. Khi debug, hãy tách hai việc: **reference có hợp lệ không** và **Javadoc có biết URL của bộ tài liệu đích không**.

## 10. Cách kiểm chứng bằng `javadoc`

Đặt hai file `LinkTargets.java` và `SnippetLinkDoc.java` trong cùng thư mục. Chạy:

~~~bash
javadoc -d docs LinkTargets.java SnippetLinkDoc.java
~~~

Mở `docs/SnippetLinkDoc.html` và kiểm tra:

1. `LinkTargets` dẫn đến trang tài liệu class.
2. `new LinkTargets` dẫn đến constructor có tham số `String`.
3. `DEFAULT_LIMIT` dẫn đến field tương ứng.
4. Hai chữ `of` dẫn đến hai overload khác nhau.
5. `value()` dẫn đến method `value()`.
6. Các markup comment `// @link ...` không xuất hiện trong khối mã.
7. Nếu có dùng `type=linkplain`, kiểu chữ của liên kết khác với `type=link` theo stylesheet.

Trong HTML, các phần được liên kết sẽ được bao bởi phần tử anchor với thuộc tính `href` trỏ đến tài liệu đích. Có thể dùng Inspect của trình duyệt để xem URL thực tế; không nên tự đoán tên file HTML hoặc fragment khi class, package hay overload thay đổi.

Nếu target là API bên ngoài, thử thêm `-link` với URL tài liệu tương ứng. Nếu target là overload, kiểm tra lại đầy đủ kiểu tham số và thứ tự tham số. Khi `javadoc` báo lỗi, đọc thông báo về reference trước khi thay selector.

## 11. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `target="String#strip()"` nhưng reference không được phân giải. | Tên class không được suy ra từ ngữ cảnh hoặc import. | Dùng tên đầy đủ `java.lang.String#strip()`. |
| Link method overload chỉ bằng tên `#of`. | Có nhiều method cùng tên nên target mơ hồ. | Ghi rõ parameter list, ví dụ `#of(java.lang.String, int)`. |
| Dùng `target="LinkTargets.of"`. | Target dùng cú pháp reference của Javadoc, không phải cú pháp gọi method Java bằng dấu chấm. | Dùng `LinkTargets#of(java.lang.String)`. |
| Muốn link constructor nhưng dùng target là tên method khác. | Constructor được tham chiếu bằng tên class sau dấu `#`. | Dùng `LinkTargets#LinkTargets(java.lang.String)`. |
| Bỏ selector và vô tình link cả dòng. | Khi không có `substring`/`regex`, toàn bộ phạm vi được liên kết. | Thêm `substring` hoặc `regex`. |
| Hai markup link cùng chọn một đoạn chữ. | Overlapping links không được phép; Javadoc báo lỗi. | Tách selector hoặc tách dòng để các phần được chọn không giao nhau. |
| Target ở thư viện bên ngoài nhưng không có liên kết tài liệu ngoài. | Javadoc không có thông tin vị trí tài liệu đích. | Cấu hình `-link` hoặc `-linkoffline`. |
| Dùng `type=bold` trong `@link`. | Đây là kiểu của `@highlight`, không phải kiểu link. | Dùng `type=link` hoặc `type=linkplain`. |
| Nghĩ link markup sẽ đổi cách chạy chương trình. | `@link` chỉ tạo anchor trong HTML Javadoc. | Xem liên kết như trợ giúp điều hướng tài liệu, không phải thay đổi mã Java. |

## 12. Bài tập tự đánh giá

### Bài 1 — Liên kết đến field

Cho dòng:

~~~java
int limit = LinkTargets.DEFAULT_LIMIT;
~~~

Muốn chỉ chữ `DEFAULT_LIMIT` dẫn đến field tương ứng, viết markup nào?

**Đáp án:**

~~~java
int limit = LinkTargets.DEFAULT_LIMIT; // @link substring="DEFAULT_LIMIT" target="LinkTargets#DEFAULT_LIMIT"
~~~

### Bài 2 — Liên kết đúng constructor

Cho câu lệnh:

~~~java
LinkTargets item = new LinkTargets("A");
~~~

**Đáp án:**

~~~java
LinkTargets item = new LinkTargets("A"); // @link substring="new LinkTargets" target="LinkTargets#LinkTargets(java.lang.String)"
~~~

Target dùng tên class lặp lại sau `#` và kiểu tham số constructor.

### Bài 3 — Phân biệt overload

Class có hai method `of(String)` và `of(String, int)`. Hãy viết target cho từng lời gọi.

**Đáp án:**

~~~java
LinkTargets first = LinkTargets.of("A"); // @link substring="of" target="LinkTargets#of(java.lang.String)"
LinkTargets second = LinkTargets.of("B", 2); // @link substring="of" target="LinkTargets#of(java.lang.String, int)"
~~~

### Bài 4 — Chọn kiểu hiển thị

Khi muốn link tên method trong code theo font monospace mặc định, dùng `type` nào?

**Đáp án:** `type=link`, cũng là giá trị mặc định. `type=linkplain` tạo liên kết với kiểu chữ thông thường.

### Bài 5 — Vì sao Javadoc báo lỗi overlapping links?

Một dòng có hai markup link, một selector `substring="value"` và một selector `substring="value()"`, cùng áp dụng trên `item.value()`.

**Đáp án:** Hai selector cùng chọn phần văn bản chồng lấn. Javadoc không cho phép nhiều markup link áp dụng lên cùng đoạn. Hãy giữ một selector phù hợp hoặc chia các mục tiêu thành các dòng riêng.

## Tổng kết

- `@link` là markup comment trong `{@snippet}` để gắn hyperlink lên văn bản mã.
- `substring`, `regex` và `region` chọn **đoạn mã được liên kết**; `target` chọn phần tử API đích.
- `target` dùng cú pháp reference như `{@link}`: class, field, enum member, constructor hoặc method.
- Với overload, ghi rõ danh sách kiểu tham số; constructor dùng tên class sau dấu `#`.
- `type=link` là mặc định, `type=linkplain` dùng kiểu chữ thông thường.
- Nếu không có selector, toàn bộ dòng hoặc region được liên kết. Các link chồng lấn gây lỗi.
- Với API ngoài, cấu hình `-link` hoặc `-linkoffline` để cung cấp URL tài liệu.
- `@link` được giới thiệu trong Java 18 và vẫn có trong đặc tả Javadoc JDK 27.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Documentation Comment Specification, JDK 27, mục Linking text](https://download.java.net/java/early_access/jdk27/docs/specs/javadoc/doc-comment-spec.html#snippet): thuộc tính `substring`, `regex`, `region`, `target`, `type` và quy tắc overlapping links.
2. [Oracle — JavaDoc Documentation Comment Specification, JDK 27, mục References](https://download.java.net/java/early_access/jdk27/docs/specs/javadoc/doc-comment-spec.html#references): cú pháp tham chiếu class, field, constructor, method và overload.
3. [Oracle — JavaDoc Guide, JDK 26, chương Markup Comments](https://docs.oracle.com/en/java/javase/26/javadoc/javadoc-guide.pdf): ví dụ thực tế về liên kết văn bản trong snippet.
4. [Oracle — The javadoc Command, JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html): tùy chọn `-link` và `-linkoffline` cho tài liệu API bên ngoài.
5. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): nguồn gốc tính năng `{@snippet}` và markup comment trong Java 18.
