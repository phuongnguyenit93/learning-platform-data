# Chuỗi biểu diễn có giá trị thay thế khi null với `Objects.toString`

## 1. Mục tiêu của bài

Khi hiển thị một thuộc tính hoặc đối tượng có thể vắng mặt, ứng dụng thường muốn một chuỗi dễ hiểu như `"(chưa có)"`, `"N/A"` hoặc `"-"` thay vì chữ `"null"` mặc định. Từ **Java 7**, class tiện ích `java.util.Objects` cung cấp phương thức:

~~~java
public static String toString(Object o, String nullDefault)
~~~

Phương thức này biến một **tham chiếu đối tượng** thành chuỗi bằng cách gọi `o.toString()` nếu đối tượng không `null`; **chỉ khi chính `o` bằng `null`**, nó trả lại tham số thứ hai `nullDefault`. Đây là API vẫn có trong các phiên bản Java hiện hành, phù hợp để tạo văn bản hiển thị, thông báo hoặc nhãn đơn giản với chính sách thay thế rõ ràng.

Sau khi học, bạn cần:

1. Hiểu đúng hai nhánh xử lý của `Objects.toString(o, nullDefault)`.
2. Phân biệt nó với `Objects.toString(o)`, `String.valueOf(Object)` và gọi `o.toString()` trực tiếp.
3. Biết rằng **`null` khác chuỗi rỗng `""`**, và fallback **không được dùng** chỉ vì chuỗi kết quả rỗng.
4. Hiểu rằng `nullDefault` có thể là `null`; phương thức **không cam kết luôn trả về chuỗi khác `null`**.
5. Phân biệt **tham chiếu đối tượng là `null`** với **một đối tượng không `null` nhưng implementation `toString()` bị lỗi hoặc trả về `null`**.
6. Hiểu thời điểm đánh giá biểu thức fallback, lựa chọn tạo fallback đắt tiền, và giới hạn khi dùng ở log, API, báo cáo.
7. Viết chương trình Java 17+ có thể biên dịch, đọc đúng stdout và tránh các hiểu nhầm từ Java cũ không còn cần thiết.

**Bối cảnh phiên bản:** `java.util.Objects` và hai overload `toString` có từ **Java 7**; bài dùng cú pháp Java 17+ cho ví dụ thực thi nhưng chỉ tập trung kiến thức vẫn áp dụng hiện nay. Nguồn xác nhận: [Java SE 7 API — `Objects`](https://docs.oracle.com/javase/7/docs/api/java/util/Objects.html) và [Java SE 26 API — `Objects`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html).

## 2. Hợp đồng của `Objects.toString(Object, String)`

Đọc lời gọi:

~~~java
String label = Objects.toString(value, "(chưa có)");
~~~

Đây là **một dòng minh họa** trong phương thức có `value` đã khai báo và `import java.util.Objects;`. Nó có hai tham số:

- `value`: **tham chiếu đối tượng** cần lấy biểu diễn chuỗi; có thể mang kiểu `String`, `Integer`, class miền nghiệp vụ hoặc bất kỳ subtype nào của `Object`.
- `"(chưa có)"`: giá trị **dự phòng khi tham chiếu `value` bằng `null`**. Đây là một `String` và có thể là biến, kết quả của một biểu thức, hoặc chính `null`.

Ngữ nghĩa quan sát được tương đương với biểu thức:

~~~java
String label = (value != null) ? value.toString() : "(chưa có)";
~~~

Đây là **minh họa trong một phương thức**, không phải file Java hoàn chỉnh. Hãy đọc đúng điều kiện: Java kiểm tra `value != null`, **không kiểm tra** `value.toString() != null`.

| Đầu vào `o` | `nullDefault` | Kết quả của `Objects.toString(o, nullDefault)` |
| --- | --- | --- |
| `null` | `"(chưa có)"` | `"(chưa có)"` |
| `null` | `""` | Chuỗi rỗng `""` |
| `null` | `null` | Tham chiếu `null` |
| `"Java"` | `"(chưa có)"` | `"Java"` |
| `""` | `"(chưa có)"` | Chuỗi rỗng `""` |
| `Integer.valueOf(0)` | `"-"` | `"0"` |
| Đối tượng `Product` có `toString()` trả `"Product(A7)"` | `"-"` | `"Product(A7)"` |

**Ghi nhớ:** fallback chỉ phụ thuộc việc **tham chiếu ở tham số đầu tiên là `null`**. Phương thức không tự hiểu nghiệp vụ “thiếu”, không bỏ khoảng trắng, không coi `0`, `false` hay `""` là dữ liệu vắng mặt.

### 2.1. Phương thức thuộc `Objects`, không thuộc `Object`

Lời gọi chuẩn là:

~~~java
java.util.Objects.toString(value, "(chưa có)");
~~~

Hoặc có import:

~~~java
import java.util.Objects;

// Trong phương thức:
String label = Objects.toString(value, "(chưa có)");
~~~

Đây là **đoạn minh họa** chứ không phải class độc lập. Không có overload `value.toString("(chưa có)")` trên `Object`: method instance `Object.toString()` **không có tham số fallback**. Và không được gọi `value.toString()` trước khi kiểm tra `value` nếu có khả năng `null`.

### 2.2. Kết quả là chuỗi biểu diễn, không phải đối tượng mới

`Objects.toString(o, fallback)` trả `String`, **không** thay đổi `o` và **không** biến một biến `null` thành đối tượng khác. Nếu `o` không `null`, việc định dạng phụ thuộc vào `o.toString()`. Nếu `o` là `Integer`, bạn nhận chữ số; nếu `o` là một class tự viết, bạn nhận biểu diễn do class ấy quyết định.

Không dùng kết quả này để thay cho bước **kiểm tra dữ liệu đầu vào**, **giải mã JSON**, **escape HTML**, hoặc **chuyển đổi sang đối tượng nghiệp vụ**. Đây chỉ là một tiện ích biểu diễn chuỗi.

## 3. Ví dụ Java 17+: đối tượng thật, đối tượng null, chuỗi rỗng và số 0

Tạo file `ObjectsToStringDemo.java`:

~~~java
import java.util.Objects;

public class ObjectsToStringDemo {
    static final class Product {
        private final String code;

        Product(String code) {
            this.code = code;
        }

        @Override
        public String toString() {
            return "Product(" + code + ")";
        }
    }

    public static void main(String[] args) {
        Product current = new Product("A7");
        Product missing = null;
        String empty = "";

        System.out.println("current=" +
                Objects.toString(current, "(missing)"));
        System.out.println("missing=" +
                Objects.toString(missing, "(missing)"));
        System.out.println("empty=" +
                Objects.toString(empty, "(missing)"));
        System.out.println("zero=" +
                Objects.toString(0, "(missing)"));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac --release 17 ObjectsToStringDemo.java
java ObjectsToStringDemo
~~~

Stdout **chính xác**:

~~~text
current=Product(A7)
missing=(missing)
empty=
zero=0
~~~

Giải thích theo từng dòng:

1. `current` khác `null` nên Java gọi `current.toString()`; class `Product` chủ động trả biểu diễn `Product(A7)`. Fallback bị bỏ qua về **giá trị kết quả**.
2. `missing` là tham chiếu `null`; Java trả `"(missing)"` và **không gọi method trên `null`**.
3. `empty` khác `null` mặc dù nội dung có độ dài 0. Kết quả vẫn là `""`, nên sau dấu `=` không có chữ nào.
4. Literal số `0` được boxing thành giá trị kiểu `Integer` để truyền vào tham số `Object`; `Integer.toString()` trả `"0"`. Không thay bằng fallback vì số 0 là một giá trị hợp lệ.
5. Không có annotation, ép kiểu, dependency hoặc thư viện bên ngoài. Chỉ cần JDK phù hợp và file đúng tên.

**Sai lầm thường gặp:** thấy dòng `empty=` rồi kết luận fallback “không hoạt động”. Thực ra fallback chỉ hoạt động **khi tham chiếu null**, không phải khi `String.isEmpty()` trả `true`.

## 4. So sánh ba cách chuyển đối tượng thành chuỗi

Có ba biểu thức rất giống nhau nhưng chính sách `null` khác nhau:

~~~java
Objects.toString(value)
Objects.toString(value, "(missing)")
String.valueOf(value)
~~~

Đây là ba **biểu thức minh họa**, không phải câu lệnh Java độc lập. Với biến `value` được khai báo có kiểu `Object`:

| Biểu thức | Khi `value == null` | Khi `value != null` |
| --- | --- | --- |
| `Objects.toString(value)` | Trả **chuỗi ký tự** `"null"` | Gọi `value.toString()` |
| `Objects.toString(value, "(missing)")` | Trả chuỗi do bạn chỉ định `"(missing)"` | Gọi `value.toString()` |
| `String.valueOf(value)` | Trả **chuỗi ký tự** `"null"` | Gọi `value.toString()` |
| `value.toString()` | **Ném `NullPointerException`** | Gọi `value.toString()` |

Nếu cần hiển thị chữ `"null"` đúng nghĩa, các phiên bản một tham số vẫn có thể hợp lý. Nếu muốn biểu diễn mang ý nghĩa người dùng như `"(missing)"`, hãy chỉ định rõ `nullDefault`.

### 4.1. Chương trình so sánh kết quả

Tạo file `NullComparisonDemo.java`:

~~~java
import java.util.Objects;

public class NullComparisonDemo {
    public static void main(String[] args) {
        Object value = null;

        System.out.println("one=" + Objects.toString(value));
        System.out.println("two=" +
                Objects.toString(value, "(missing)"));
        System.out.println("valueOf=" + String.valueOf(value));
        System.out.println("actualNull=" +
                (Objects.toString(value, null) == null));
        System.out.println("emptyFallback=" +
                Objects.toString(value, "").isEmpty());
        System.out.println("nonnull=" +
                Objects.toString(7, "(missing)"));
    }
}
~~~

~~~bash
javac --release 17 NullComparisonDemo.java
java NullComparisonDemo
~~~

Stdout:

~~~text
one=null
two=(missing)
valueOf=null
actualNull=true
emptyFallback=true
nonnull=7
~~~

Điểm đáng chú ý: `one=null` và `valueOf=null` đều in bốn ký tự `n-u-l-l`; chúng **không** chứng minh các method trả một tham chiếu `null`. Trái lại, dòng `actualNull=true` là phép kiểm tra trực tiếp cho thấy `Objects.toString(value, null)` thực sự trả **tham chiếu `null`**.

Muốn phân biệt chắc chắn hai trường hợp, hãy kiểm tra `result == null` hoặc áp dụng test cụ thể, đừng chỉ `println(result)` vì `println(String)` cũng có thể hiển thị `"null"` cho tham chiếu null.

### 4.2. Cẩn thận với overload của `String.valueOf`

`String.valueOf` có nhiều overload, bao gồm `String.valueOf(Object)` và `String.valueOf(char[])`. Khi so sánh hai API, tốt nhất dùng **biến kiểu `Object`** như ví dụ trên để bảo đảm gọi đúng overload dành cho Object. Một literal `null` không có kiểu tường minh có thể tham gia **overload resolution** theo quy tắc khác; không nên lấy `String.valueOf(null)` làm mẫu kiểm tra tương đương với `String.valueOf((Object) null)`.

Với `Objects.toString`, cũng nên viết code rõ kiểu giá trị thực tế thay vì chỉ dựa vào ví dụ thiếu ngữ cảnh.

## 5. `nullDefault` có thể là null — và điều này có ý nghĩa

Tên tham số **`nullDefault`** mô tả *trường hợp sử dụng*, không phải một bảo đảm rằng nó phải khác `null`. API `Objects.toString(Object, String)` không tự ép fallback thành chuỗi non-null. Câu lệnh:

~~~java
String result = Objects.toString(null, null);
~~~

hợp lệ; biến `result` nhận **`null`**. Điều đó khác `Objects.toString(null)`, là overload một tham số và trả chuỗi ký tự `"null"`.

**Khuyến nghị khi hiển thị:** Nếu yêu cầu chức năng là “luôn có nhãn người dùng đọc được khi thiếu đối tượng”, hãy truyền một chuỗi fallback **khác `null`**:

~~~java
String displayName = Objects.toString(name, "(chưa có tên)");
~~~

Đây là đoạn minh họa có `name` đã khai báo. Việc truyền `null` làm fallback chỉ nên diễn ra khi caller **cố ý cho phép kết quả nullable** và đã xử lý nhánh đó.

### 5.1. Fallback không tự chuẩn hóa dữ liệu

Các giá trị sau đều **không** kích hoạt fallback vì bản thân chúng không null:

- `""`: chuỗi có độ dài 0.
- `"   "`: chuỗi gồm toàn khoảng trắng.
- `0` hoặc `0.0`: số bằng 0.
- `false`: giá trị boolean hợp lệ.
- `"null"`: chuỗi chứa chữ `null`, khác tham chiếu null.
- Một object có `toString()` trả `""`: đây vẫn là kết quả của `toString()`.

Nếu nghiệp vụ định nghĩa “vắng mặt” bao gồm **rỗng**, **chỉ toàn khoảng trắng** hoặc một giá trị sentinel, cần viết chính sách riêng để kiểm tra các trường hợp đó, không kỳ vọng `Objects.toString` xử lý thay.

Ví dụ **đoạn trong phương thức** có `String input`:

~~~java
String display = (input == null || input.isBlank())
        ? "(chưa có)"
        : input;
~~~

`String.isBlank()` được bổ sung từ **Java 11**, nên dùng được trên Java 17+; đây **không** phải một tính năng Java 7. Nó kiểm tra chính sách “null hoặc blank”, hoàn toàn khác hợp đồng cơ bản của `Objects.toString`. Nếu cần giữ nguyên khoảng trắng hợp lệ, đừng dùng `isBlank()` một cách cơ học.

## 6. Một trường hợp tinh tế: object không null nhưng `toString()` trả null hoặc ném lỗi

Javadoc `Object.toString()` của Java hiện hành quy định rằng tuân thủ hợp đồng method này nghĩa là **trả một kết quả không null**. Tuy nhiên, một class tự viết **vẫn có thể vi phạm hợp đồng** bằng cách override `toString()` rồi trả `null`, hoặc ném exception.

Với `Objects.toString(o, fallback)`:

- Nếu `o != null`, phương thức **gọi `o.toString()`**.
- Nếu override bị lỗi và trả `null`, kết quả có thể là **null thật**, dù `fallback` không null.
- Nếu override ném `RuntimeException`, exception vẫn được **lan truyền**; `Objects.toString` không phải khối `try/catch`.
- Fallback **không được thử lại** chỉ vì `toString()` trả null hoặc ném lỗi.

### 6.1. Chương trình kiểm chứng điều kiện biên

Tạo file `FallbackEdgeDemo.java`:

~~~java
import java.util.Objects;

public class FallbackEdgeDemo {
    static final class BadText {
        @Override
        public String toString() {
            return null;
        }
    }

    static final class BrokenText {
        @Override
        public String toString() {
            throw new IllegalStateException("broken");
        }
    }

    public static void main(String[] args) {
        System.out.println("objectNull=" +
                Objects.toString(null, "fallback").equals("fallback"));

        System.out.println("badResultNull=" +
                (Objects.toString(new BadText(), "fallback") == null));

        try {
            Objects.toString(new BrokenText(), "fallback");
        } catch (IllegalStateException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 FallbackEdgeDemo.java
java FallbackEdgeDemo
~~~

Stdout:

~~~text
objectNull=true
badResultNull=true
error=broken
~~~

Đây là chương trình **cố ý mô tả implementation sai hợp đồng** để thấy giới hạn của tiện ích. Không nên viết `toString()` trả null trong code sản phẩm. Khi custom class cần chuỗi biểu diễn, hãy trả một `String` hợp lệ ngay cả khi một thuộc tính bên trong là null.

Ví dụ cách override tốt hơn khi thuộc tính `code` có thể null:

~~~java
@Override
public String toString() {
    return "Product(" + Objects.toString(code, "(unknown)") + ")";
}
~~~

Đây là **phương thức đặt bên trong class** có field `code` và import `java.util.Objects`. Nó tạo biểu diễn không null trong trường hợp field `code` null, nếu các đoạn còn lại là chuỗi hằng. Dùng `Objects.toString` để xử lý **field nullable** bên trong một `toString()` có thể giúp class tuân thủ hợp đồng.

Nguồn: [Object.toString(), Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#toString()).

### 6.2. Không biến lỗi bất thường thành dữ liệu hợp lệ một cách thiếu kiểm soát

Nếu code bên thứ ba có `toString()` ném exception, tốt hơn là sửa implementation hoặc bao lỗi ở ranh giới đúng thiết kế thay vì dùng fallback như một cơ chế nuốt lỗi. Fallback của `Objects.toString` chỉ dành cho **tham chiếu null**, không phải **ngoại lệ**. Một biểu diễn lỗi được âm thầm thay bằng `"(missing)"` có thể che giấu sự cố sản phẩm.

## 7. Biểu thức fallback được đánh giá trước khi gọi method

Một điểm dễ ảnh hưởng hiệu năng: Java **đánh giá các đối số của lời gọi phương thức trước khi gọi phương thức**. `Objects.toString(value, createDefault())` không phải API lazy. Dù `value` khác null, biểu thức `createDefault()` **vẫn được thực hiện** để tạo tham số thứ hai.

Tạo file `DefaultEvaluationDemo.java`:

~~~java
import java.util.Objects;

public class DefaultEvaluationDemo {
    static String computeDefault() {
        System.out.println("prepare-default");
        return "(missing)";
    }

    public static void main(String[] args) {
        Object known = "ready";

        System.out.println("eager=" +
                Objects.toString(known, computeDefault()));

        Object absent = null;

        System.out.println("lazy=" +
                (absent != null ? absent.toString() : computeDefault()));

        System.out.println("lazyKnown=" +
                (known != null ? known.toString() : computeDefault()));
    }
}
~~~

~~~bash
javac --release 17 DefaultEvaluationDemo.java
java DefaultEvaluationDemo
~~~

Stdout chính xác:

~~~text
prepare-default
eager=ready
prepare-default
lazy=(missing)
lazyKnown=ready
~~~

Phân tích:

1. Dòng đầu tiên gọi `computeDefault()`, in `prepare-default`, **dù `known` khác null**; kết quả cuối của `Objects.toString` vẫn là `ready`.
2. Ở biểu thức ba ngôi với `absent == null`, Java chỉ đánh giá nhánh fallback, nên in `prepare-default` rồi `lazy=(missing)`.
3. Với `known != null`, biểu thức ba ngôi chỉ đánh giá nhánh `known.toString()`; **không** có dòng `prepare-default` thứ ba.
4. Sự khác biệt có thể quan trọng nếu fallback phải tra cứu dữ liệu, định dạng phức tạp hoặc có tác dụng phụ.

**Cách chọn:**

- Fallback là chuỗi hằng đơn giản như `"(missing)"`: dùng `Objects.toString(value, "(missing)")` cho ngắn gọn và dễ đọc.
- Fallback là biểu thức tốn chi phí hoặc cần thực hiện **chỉ khi null**: dùng điều kiện có kiểm tra null, hoặc tổ chức helper riêng với ngữ nghĩa lazy rõ ràng.
- Không giả định Java tự bỏ qua phép tính ở tham số `nullDefault` vì method có logic chọn nhánh bên trong. Thứ tự đánh giá đối số là quy tắc ngôn ngữ, khác với logic bên trong method.

**Khác biệt với `Objects.requireNonNullElseGet`:** API Java 9+ đó nhận `Supplier` để lấy **đối tượng** không null khi tham số gốc null. Nó không phải overload lazy của `Objects.toString` và không có cùng chính sách chuyển đổi chuỗi. Chỉ chọn khi hợp đồng đúng là trả một đối tượng non-null; đừng lạm dụng để thay một dòng hiển thị.

## 8. Ứng dụng: tạo nhãn hiển thị nhất quán

Ví dụ có nhiều trường dữ liệu có thể bị thiếu. Thay vì viết cùng một điều kiện null cho mọi chỗ hiển thị, bạn có thể định nghĩa helper trả nhãn có fallback rõ ràng:

~~~java
static String display(Object value) {
    return Objects.toString(value, "(not provided)");
}
~~~

Đây là **phương thức đặt trong class** đã import `Objects`; nó không phải chương trình độc lập. Lợi ích là thống nhất ngôn ngữ hiển thị và giảm lỗi gọi `toString()` trên tham chiếu null.

### 8.1. Chương trình đầy đủ

Tạo file `DisplayLabelDemo.java`:

~~~java
import java.util.Objects;

public class DisplayLabelDemo {
    static String display(Object value) {
        return Objects.toString(value, "(not provided)");
    }

    public static void main(String[] args) {
        String name = "Mai";
        String nickname = null;
        String optionalNote = "";

        System.out.println("name=" + display(name));
        System.out.println("nickname=" + display(nickname));
        System.out.println("noteEmpty=" +
                display(optionalNote).isEmpty());
        System.out.println("number=" + display(42));
    }
}
~~~

~~~bash
javac --release 17 DisplayLabelDemo.java
java DisplayLabelDemo
~~~

Stdout:

~~~text
name=Mai
nickname=(not provided)
noteEmpty=true
number=42
~~~

**Giới hạn cần biết:** Phương thức nhận `Object` rất tiện cho hiển thị đơn giản nhưng có thể khiến API lỏng về kiểu. Nếu một lĩnh vực nghiệp vụ yêu cầu nhãn `String`, có thể khai báo `static String displayName(String name)` để chữ ký rõ hơn. Và đừng dùng một nhãn chung cho mọi trường nếu yêu cầu giao diện cần phân biệt “chưa nhập”, “không áp dụng”, “đã bị xóa” hoặc “ẩn vì không có quyền”.

### 8.2. Dùng với collection trên Java 17+

Khi tạo danh sách nhãn từ các giá trị có thể null:

~~~java
List<Object> values = Arrays.asList("Java", null, 7, "");
List<String> labels = values.stream()
        .map(value -> Objects.toString(value, "(missing)"))
        .toList();
~~~

Đây là **đoạn trong phương thức** với import `java.util.List`, `java.util.Arrays`, `java.util.Objects`. `Stream.toList()` có từ **Java 16**, nên mẫu này dùng với Java 17+ chứ không phải Java 7. Kết quả về mặt nội dung là danh sách `["Java", "(missing)", "7", ""]`. Thứ tự được giữ vì đây là stream tuần tự từ list có thứ tự.

**Cần phân biệt:** `List.of("Java", null)` không cho phép phần tử null và sẽ ném `NullPointerException` khi tạo list; vì vậy ở ví dụ có dữ liệu null, dùng `Arrays.asList(...)` hoặc nguồn nullable hợp lệ. Chính sách null của collection **độc lập** với `Objects.toString`.

## 9. So với `Objects.requireNonNullElse` (Java 9+)

Một phương thức khác của `Objects`, `Objects.requireNonNullElse(obj, defaultObj)`, có vẻ giống vì cùng dùng giá trị dự phòng. Nhưng nó giải quyết **bài toán khác**:

- `Objects.toString(o, nullDefault)` luôn có kiểu trả về khai báo là **`String`**, không yêu cầu fallback non-null và gọi `o.toString()` nếu object có mặt.
- `Objects.requireNonNullElse(obj, defaultObj)` (Java 9+) trả về **một object kiểu generic T**, chọn object đầu nếu khác null và object dự phòng nếu null; nó **yêu cầu kết quả không null** và từ chối fallback null bằng `NullPointerException` khi cần dùng fallback.
- Một bên phục vụ **biểu diễn chuỗi**; một bên phục vụ **thay thế đối tượng**. Không tự đổi API chỉ vì cùng có chữ “null”.

File `RequireNonNullComparisonDemo.java`:

~~~java
import java.util.Objects;

public class RequireNonNullComparisonDemo {
    public static void main(String[] args) {
        String missing = null;
        String replacement = "(missing)";

        System.out.println("text=" +
                Objects.toString(missing, replacement));

        System.out.println("object=" +
                Objects.requireNonNullElse(missing, replacement));

        try {
            Objects.requireNonNullElse(missing, null);
        } catch (NullPointerException ex) {
            System.out.println("nullDefaultRejected=true");
        }

        System.out.println("nullAllowed=" +
                (Objects.toString(missing, null) == null));
    }
}
~~~

~~~bash
javac --release 17 RequireNonNullComparisonDemo.java
java RequireNonNullComparisonDemo
~~~

Stdout:

~~~text
text=(missing)
object=(missing)
nullDefaultRejected=true
nullAllowed=true
~~~

Hai dòng đầu **hiển thị giống nhau trong trường hợp hai biến đều là String**. Tuy nhiên, chúng không chứng minh hai method tương đương với đối tượng khác: `requireNonNullElse` trả lại một đối tượng, còn `toString` tạo biểu diễn chuỗi. Dòng cuối cho thấy chính sách fallback null khác nhau.

**Khi nào dùng gì?**

| Mục tiêu | Phương thức phù hợp |
| --- | --- |
| Muốn nhãn chuỗi thay thế khi object null | `Objects.toString(o, "(missing)")` |
| Muốn giữ object gốc hoặc thay bằng object khác nếu null | `Objects.requireNonNullElse(o, fallbackObject)` (Java 9+) |
| Muốn fallback object tạo chậm khi cần | `Objects.requireNonNullElseGet(o, supplier)` (Java 9+), với hợp đồng non-null |
| Muốn chuỗi thay thế khi string null hoặc blank | Kiểm tra `null` và `isBlank()` theo yêu cầu nghiệp vụ, không chỉ `Objects.toString` |
| Muốn ném lỗi khi object null vì null là vi phạm hợp đồng | `Objects.requireNonNull(o)` và xử lý đúng tầng |

## 10. Dùng trong `toString()` của class miền nghiệp vụ

Một class miền nghiệp vụ thường muốn tạo chuỗi dễ đọc khi một vài **field bên trong** có thể null. Bạn có thể đưa logic fallback vào chính method `toString()`:

~~~java
import java.util.Objects;

final class CustomerSummary {
    private final String name;
    private final Integer level;

    CustomerSummary(String name, Integer level) {
        this.name = name;
        this.level = level;
    }

    @Override
    public String toString() {
        return "CustomerSummary{name=" +
                Objects.toString(name, "(missing)") +
                ", level=" +
                Objects.toString(level, "(missing)") +
                "}";
    }
}
~~~

Đây là **đoạn khai báo class bổ trợ**, không có `main`; muốn chạy phải tạo đối tượng và in kết quả trong một class chạy riêng. Ví dụ:

~~~java
CustomerSummary customer = new CustomerSummary(null, 3);
System.out.println(customer);
~~~

Đoạn sử dụng trên nằm trong phương thức chạy. Chuỗi biểu diễn sẽ là:

~~~text
CustomerSummary{name=(missing), level=3}
~~~

Điểm hay ở đây là `toString()` của **đối tượng `CustomerSummary`** trả một chuỗi có cấu trúc nhất quán, và các field nullable được xử lý rõ ràng. Tuy nhiên:

- Không đưa mật khẩu, token, số định danh hay dữ liệu nhạy cảm vào `toString()` của domain object, vì logger/debugger có thể gọi nó.
- Đừng coi `toString()` là hợp đồng serialize dữ liệu bền vững. Cấu trúc này dành cho **con người đọc**, không nhất thiết ổn định giữa các phiên bản.
- Nếu cần JSON/CSV/XML hoặc chuẩn hóa đầu ra API, sử dụng serializer/encoder thích hợp với schema, không nối chuỗi tùy ý.
- Nếu chuỗi fallback là thông điệp giao diện, có thể cần quốc tế hóa theo locale. `Objects.toString` chỉ chọn chuỗi, **không thực hiện i18n**.

## 11. Những rủi ro khi dùng cho log, báo cáo và bảo mật

`Objects.toString` rất tiện để log thông tin nullable:

~~~java
logger.info("Account label: " +
        Objects.toString(accountLabel, "(unavailable)"));
~~~

Đây là **đoạn minh họa** với `logger` và `accountLabel` đã khai báo. Nó chỉ giải quyết trường hợp tham chiếu null. Các nguyên tắc thực tế vẫn cần:

1. **Tránh dữ liệu nhạy cảm:** Một object có `toString()` chứa thông tin nhạy cảm sẽ vẫn được in nguyên văn nếu object không null.
2. **Không được coi fallback là masking:** `"(unavailable)"` chỉ xuất hiện khi tham chiếu null, không ẩn dữ liệu đã có.
3. **Phân biệt lỗi và thiếu dữ liệu:** Nếu việc lấy thông tin gặp exception, cần xử lý lỗi đúng hợp đồng; không âm thầm coi exception là một object null rồi ghi nhãn thiếu dữ liệu.
4. **Chọn fallback có ý nghĩa:** Tại trang giao diện nên ưu tiên văn bản phù hợp người dùng; trong log kỹ thuật có thể dùng `"<missing>"` hoặc key có cấu trúc.
5. **Không tạo cấu trúc máy đọc bằng `toString()`:** Khi dữ liệu cần parse lại, dùng định dạng có escape đúng; dấu phẩy, xuống dòng, dấu ngoặc trong giá trị có thể phá định dạng nối chuỗi.
6. **Không dùng kết quả làm ID ổn định:** `Object.toString()` mặc định có thể chứa tên class và hash ở dạng hex, không phải khóa nghiệp vụ bền vững.
7. **Đánh giá chi phí `toString()`:** Với đối tượng lớn hoặc method override nặng, gọi `toString()` chỉ để log có thể tạo công việc không cần thiết. Hãy dùng khả năng ghi log có điều kiện/tham số hóa theo framework đang dùng.
8. **Không nhầm an toàn null với an toàn luồng:** `Objects.toString` không bảo đảm thread safety của `o.toString()`; các field bên trong object có thể bị sửa đồng thời tùy implementation.

### 11.1. “Chỉ khi null” có phù hợp với nghiệp vụ không?

Nếu field `nickname` là `""` và UI muốn hiển thị `"(không có biệt danh)"`, `Objects.toString(nickname, "(không có biệt danh)")` **không đủ**. Cần quyết định nghiệp vụ: chuỗi trống có đồng nghĩa “chưa cung cấp” hay không? Nếu có, kiểm tra thêm empty/blank.

Ngược lại, với chuỗi trống là dữ liệu hợp lệ, một helper tự thay rỗng thành fallback sẽ **làm sai dữ liệu**. Không trộn hai chính sách trong cùng một method nếu không có hợp đồng rõ ràng.

## 12. Kiểm thử hành vi mà không lẫn chuỗi chữ `"null"` với null thật

Vì `System.out.println((String) null)` thường in `null` giống chuỗi `"null"`, khi test nên dùng assertion/biểu thức boolean để phân biệt.

Ví dụ **đoạn trong phương thức**:

~~~java
Object absent = null;

String generated = Objects.toString(absent, "(missing)");
if (!"(missing)".equals(generated)) {
    throw new AssertionError("Wrong fallback");
}

String nullable = Objects.toString(absent, null);
if (nullable != null) {
    throw new AssertionError("Expected real null");
}

String blank = Objects.toString("", "(missing)");
if (!blank.isEmpty()) {
    throw new AssertionError("Empty String must remain empty");
}
~~~

Đây là **đoạn kiểm tra** được đặt trong class/method có import `Objects`; nếu không ném `AssertionError` thì ba điều kiện đều được thỏa. Không dùng kết quả `println` làm bằng chứng duy nhất cho tình trạng null.

Một bộ test hợp lý cho một wrapper hiển thị phải bao phủ:

- Object null, fallback khác null.
- Object null, fallback chuỗi rỗng.
- Object null, fallback null (nếu API cho phép kết quả nullable).
- Object khác null có `toString()` bình thường.
- Object là `String` rỗng hoặc toàn khoảng trắng.
- Object khác null có `toString()` gây lỗi hoặc vi phạm hợp đồng (khi dữ liệu nằm trong phạm vi không đáng tin).
- Fallback đắt tiền được đánh giá sớm nếu truyền trực tiếp vào lời gọi.
- Các giá trị hợp lệ như `0`, `false` và `""` không bị tự thay thế.

**Nếu mục tiêu của một hệ thống yêu cầu kết quả luôn non-null:** Chọn fallback non-null **và** xác định rằng đối tượng đầu vào có implementation `toString()` tuân thủ hợp đồng. Không suy ra một lời gọi `Objects.toString` tự nó loại bỏ mọi khả năng kết quả null bất kể implementation.

## 13. Những lỗi và ngộ nhận phổ biến

| Ngộ nhận | Kết luận đúng |
| --- | --- |
| “`Objects.toString(o, fallback)` thay mọi giá trị trống bằng fallback” | Chỉ thay khi **tham chiếu `o` null** |
| “`Objects.toString(o)` và overload hai tham số giống nhau” | Với `o=null`, overload một tham số trả chữ `"null"`, overload hai tham số trả `nullDefault` |
| “Fallback luôn non-null” | Tham số `nullDefault` có thể là null |
| “Object khác null thì kết quả chắc chắn non-null vì có fallback” | Với override `toString()` không tuân thủ hợp đồng và trả null, fallback **không** được dùng |
| “Nếu `o.toString()` ném lỗi, fallback sẽ được trả” | Exception vẫn lan truyền |
| “`String.valueOf(o)` nhận tham số fallback” | Không có overload `String.valueOf(Object, String fallback)` |
| “`String.valueOf((Object) null)` trả null thật” | Trả chuỗi ký tự `"null"` |
| “`Objects.toString` kiểm tra mọi field trong object” | Chỉ kiểm tra **tham chiếu truyền vào**; nếu khác null thì gọi `o.toString()` |
| “`Objects.toString` gọi `trim()` hoặc `isBlank()`” | Không. Không tự chuẩn hóa nội dung |
| “`Objects.toString` biến object thành JSON” | Không phải serializer, không escape theo schema |
| “`Objects.toString(o, expensive())` chỉ gọi expensive khi o null” | Đối số được đánh giá **trước lời gọi** |
| “Dùng fallback là đủ để che dữ liệu nhạy cảm” | Không. Object khác null vẫn có thể tiết lộ dữ liệu từ `toString()` |
| “`Objects.requireNonNullElse` là alias của `Objects.toString`” | Không. Nó chọn object generic non-null và có từ Java 9 |
| “`Object.toString()` mặc định là một định danh ổn định” | Không. Biểu diễn mặc định/override phục vụ mô tả, không phải khóa bền vững |

## 14. Quy trình lựa chọn giải pháp trong code hiện hành

Khi cần hiển thị một giá trị có thể null:

1. **Xác định kiểu nguồn.** Là `String` nullable, số/enum, hay đối tượng có `toString()` tùy chỉnh?
2. **Định nghĩa rõ “thiếu”.** Chỉ `null`, hay còn rỗng/blank/sentinel? Nếu chỉ null, `Objects.toString` rất thích hợp.
3. **Chọn fallback có ý nghĩa.** Ví dụ `"(chưa nhập)"` cho giao diện hoặc `"<missing>"` cho log; tránh nhầm hai trạng thái nghiệp vụ khác nhau.
4. **Kiểm tra fallback non-null nếu yêu cầu.** `Objects.toString(null, null)` vẫn trả null.
5. **Xác nhận `toString()` của nguồn có giá trị.** Nếu đó là object miền nghiệp vụ, override trả chuỗi đọc được, không tiết lộ dữ liệu không nên hiển thị.
6. **Xem chi phí tính fallback.** Chuỗi hằng thì truyền trực tiếp; fallback cần truy vấn hoặc tính toán lớn thì dùng điều kiện lazy.
7. **Phân biệt biểu diễn với validation.** Không dùng nhãn hiển thị thay cho việc bắt lỗi dữ liệu bắt buộc; nếu thiếu thông tin là lỗi, ưu tiên kiểm tra và báo lỗi.
8. **Phân biệt Java version.** Overload hai tham số có từ Java 7; một số helper tương tự như `requireNonNullElse` (Java 9) và `String.isBlank` (Java 11) chỉ dùng khi release phù hợp.
9. **Test các giá trị biên.** Null thật, chuỗi rỗng, fallback null, override `toString()` bất thường, và biểu thức fallback có tác dụng phụ.
10. **Không mở rộng phạm vi của method.** `Objects.toString` chỉ chọn chuỗi biểu diễn, không tự quản lý format, locale, escaping, quyền truy cập hay logging semantics.

### 14.1. Mẫu ngắn gọn nên dùng

~~~java
String title = Objects.toString(possiblyNullTitle, "(chưa có tiêu đề)");
~~~

Phù hợp khi chỉ `null` mới là thiếu và fallback là chuỗi hằng.

### 14.2. Mẫu khi null hoặc blank đều thiếu

~~~java
String title = (possiblyNullTitle == null
        || possiblyNullTitle.isBlank())
        ? "(chưa có tiêu đề)"
        : possiblyNullTitle;
~~~

Đoạn Java 11+ này **không phải** chức năng có sẵn của `Objects.toString`; hãy dùng khi nghiệp vụ thực sự yêu cầu.

### 14.3. Mẫu khi fallback đắt tiền

~~~java
String title = (possibleTitle != null)
        ? possibleTitle.toString()
        : computeDisplayFallback();
~~~

Đoạn minh họa yêu cầu `possibleTitle` và helper `computeDisplayFallback()` đã khai báo. Khác với việc truyền `computeDisplayFallback()` làm tham số thứ hai của `Objects.toString`, biểu thức điều kiện chỉ gọi helper **khi null**.

### 14.4. Mẫu khi null là lỗi đầu vào

~~~java
String title = Objects.requireNonNull(possiblyNullTitle,
        "Title is required");
~~~

Nếu null là vi phạm hợp đồng, dùng API báo lỗi phù hợp. Đây không phải bài toán “biểu diễn có giá trị thay thế”.

## 15. Câu hỏi tự kiểm tra

**1.** `Objects.toString(null, "N/A")` trả gì?  
**Đáp án:** Chuỗi `"N/A"`, không ném `NullPointerException`.

**2.** `Objects.toString(null)` trả gì?  
**Đáp án:** Chuỗi ký tự `"null"` theo overload một tham số.

**3.** `Objects.toString("", "N/A")` có trả `"N/A"` không?  
**Đáp án:** Không. `""` là một String khác null, nên trả `""`.

**4.** `Objects.toString(0, "N/A")` có dùng fallback?  
**Đáp án:** Không. `0` được boxing thành một object `Integer` không null; kết quả là `"0"`.

**5.** `Objects.toString(null, null) == null` có đúng không?  
**Đáp án:** Đúng. Overload hai tham số chấp nhận null fallback và có thể trả null.

**6.** Một object không null có `toString()` trả null thì fallback có tự xuất hiện?  
**Đáp án:** Không. Java gọi `toString()` trên object đó; kết quả có thể là null. Implementation như vậy không tuân thủ hợp đồng `Object.toString()` hiện hành.

**7.** Một object không null có `toString()` ném exception, `Objects.toString` có xử lý bằng fallback không?  
**Đáp án:** Không. Exception tiếp tục lan truyền.

**8.** Vì sao `Objects.toString(value, expensiveDefault())` có thể vẫn chậm khi `value != null`?  
**Đáp án:** `expensiveDefault()` được đánh giá để tạo tham số thứ hai trước lời gọi method.

**9.** `String.valueOf((Object) null)` khác `Objects.toString(null, "missing")` thế nào?  
**Đáp án:** `String.valueOf((Object) null)` trả chữ `"null"`; overload hai tham số trả `"missing"`.

**10.** Muốn `""` và chuỗi toàn khoảng trắng đều thành nhãn thiếu, dùng `Objects.toString` riêng có đủ không?  
**Đáp án:** Không. Cần kiểm tra `String.isBlank()` hoặc chính sách tương đương phù hợp yêu cầu.

**11.** Muốn thay một đối tượng null bằng đối tượng khác mà không cần chuyển thành String, API nào thích hợp hơn?  
**Đáp án:** `Objects.requireNonNullElse` (Java 9+) nếu cả object dự phòng phải khác null; nó không phải overload của `toString`.

**12.** Có nên dùng `Objects.toString(user, "(hidden)")` để che dữ liệu nhạy cảm của user không?  
**Đáp án:** Không. Khi `user` khác null, `user.toString()` vẫn có thể hiển thị dữ liệu nhạy cảm. Cần policy redaction/masking riêng.

**13.** Một số nguyên `Integer age = null` có thể dùng `Objects.toString(age, "unknown")` không?  
**Đáp án:** Có. Nó trả `"unknown"` khi tham chiếu Integer null, hoặc biểu diễn số khi có giá trị.

**14.** In `Objects.toString(null, null)` bằng `println` thấy chữ `null` thì có nghĩa method trả chuỗi `"null"`?  
**Đáp án:** Không. `println` cũng có thể biểu diễn tham chiếu String null thành chữ `null`. Hãy kiểm tra `result == null`.

## 16. Tài liệu chính thức

- [Java SE 26 — `java.util.Objects`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html): hợp đồng hiện hành của hai overload `toString` và các phương thức null-safety liên quan.
- [Java SE 26 — `Objects.toString(Object, String)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html#toString(java.lang.Object,java.lang.String)): trả `o.toString()` nếu `o` khác null; ngược lại trả `nullDefault`.
- [Java SE 7 — `java.util.Objects`](https://docs.oracle.com/javase/7/docs/api/java/util/Objects.html): nguồn gốc API từ Java 7, xác nhận overload hai tham số đã tồn tại khi tính năng được giới thiệu.
- [Java SE 26 — `Object.toString()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#toString()): hợp đồng trả biểu diễn chuỗi không null và lưu ý không dùng biểu diễn đó làm định danh ổn định.
- [Java SE 26 — `String.valueOf(Object)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#valueOf(java.lang.Object)): chuyển đối tượng thành String, với chính sách null cho overload Object.
- [Java SE 26 — `Objects.requireNonNullElse`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html#requireNonNullElse(T,T)): API chọn giá trị đối tượng khác null, khác mục tiêu biểu diễn chuỗi.
- [Java SE 26 — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): kiểm tra null là vi phạm hợp đồng, không phải gán nhãn hiển thị.

**Ghi nhớ:** `Objects.toString(o, nullDefault)` là lựa chọn ngắn gọn khi cần **chuỗi thay thế cho một tham chiếu null**. Nó **không** thay chuỗi rỗng, **không** tự bắt lỗi từ `toString()`, **không** bảo đảm kết quả non-null nếu fallback null hoặc implementation `toString()` sai hợp đồng, và **không** tạo fallback theo kiểu lazy. Dùng đúng ngữ nghĩa này giúp code hiển thị rõ ràng, dễ kiểm thử và an toàn hơn trước lỗi gọi method trên tham chiếu null.