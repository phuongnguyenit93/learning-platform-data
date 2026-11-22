# Suy luận kiểu từ phương thức trả về giao diện hoặc lớp cụ thể với `var`

Khi viết `var result = someMethod();`, Java suy luận **kiểu tĩnh của biến từ kiểu của biểu thức gọi phương thức tại thời điểm biên dịch**. Trường hợp phương thức thông thường không có tham số kiểu cần suy luận, đó là **kiểu trả về được khai báo trong chữ ký phương thức được chọn**, chứ không phải lớp thực tế của đối tượng mà phương thức tạo ra khi chạy.

Đây là một điểm quan trọng của `var`, có từ Java 10 và **vẫn áp dụng trong Java hiện đại**: `var` rút ngắn cách viết biến cục bộ, nhưng không tạo ra kiểu động và không tự “nhìn xuyên” giao diện để lộ mọi phương thức riêng của lớp triển khai.

## 1. Kiểu khai báo và lớp thực tế là hai điều khác nhau

Xem phương thức sau:

~~~java
import java.util.ArrayList;
import java.util.List;

static List<String> loadNames() {
    return new ArrayList<>(List.of("An", "Bình"));
}
~~~

*Đây là đoạn minh họa phương thức, cần đặt trong một lớp; chưa phải chương trình độc lập.*

Trong `static List<String> loadNames()`, **`List<String>` là kiểu trả về công khai theo chữ ký**, còn `new ArrayList<>(...)` tạo ra một đối tượng thực tế thuộc lớp `ArrayList`. Bên gọi nhìn thấy hợp đồng `List<String>`:

~~~java
var names = loadNames();       // Suy luận: List<String>
String first = names.get(0);   // Hợp lệ: get là phương thức của List
names.add("Mai");              // Có thể gọi theo kiểu List; khả năng sửa được phụ thuộc đối tượng

// names.ensureCapacity(20);  // Lỗi biên dịch: List không khai báo ensureCapacity
~~~

`ArrayList` có `ensureCapacity`, nhưng `names` đã được suy luận là `List<String>`. Việc phương thức hiện trả về một `ArrayList` **không làm kiểu tĩnh của `names` đổi thành `ArrayList<String>`**.

Có thể quan sát lớp thực tế lúc chạy bằng `names.getClass()`, song kết quả đó không sửa các quy tắc kiểm tra kiểu khi biên dịch. Một phương thức được phép trả về một lớp triển khai khác ở lần gọi sau, miễn là nó đáp ứng kiểu trả về đã khai báo.

**Ba lớp thông tin cần phân biệt:**

1. **Chữ ký tại điểm gọi:** phương thức khai báo trả về kiểu nào (ví dụ `List<String>`).
2. **Kiểu suy luận của `var`:** kiểu của biểu thức gọi phương thức theo trình biên dịch (thường là `List<String>` như chữ ký trên).
3. **Lớp đối tượng lúc chạy:** đối tượng thực tế (ví dụ `ArrayList`, `LinkedList` hoặc một lớp phù hợp khác).

## 2. Khi phương thức khai báo trả về giao diện

Nếu chữ ký là `List<String>`, `Collection<String>`, `Map<String, Integer>` hoặc một giao diện khác, biến khai báo bằng `var` nhận **kiểu giao diện đó cùng các đối số kiểu generic phù hợp**.

~~~java
static java.util.Collection<String> loadCollection() {
    return new java.util.ArrayList<>(java.util.List.of("A", "B"));
}

// Đặt trong phương thức:
var items = loadCollection(); // Collection<String>
System.out.println(items.size());
~~~

Người đọc có thể dùng các phương thức được khai báo trên `Collection` (`size`, `iterator`, `contains`, v.v.). Không thể gọi `items.get(0)` vì `Collection` không có `get(int)`, kể cả khi đối tượng thực tế là `ArrayList`.

Điều này thể hiện nguyên tắc *lập trình theo giao diện*: bên gọi dựa trên hợp đồng công khai. Thay đổi triển khai bên trong `loadCollection()` thường không bắt buộc sửa mã bên gọi nếu chữ ký và hành vi cam kết vẫn giữ nguyên.

| Chữ ký hoặc biểu thức tại điểm gọi | Kiểu `var` suy luận | Điểm cần nhớ |
| --- | --- | --- |
| `List<String> fetch()` | `List<String>` | Chỉ gọi được API của `List` và các kiểu cha |
| `Collection<String> fetch()` | `Collection<String>` | Không có `get(int)` của `List` |
| `Map<String, Integer> fetch()` | `Map<String, Integer>` | Giữ nguyên tham số generic |
| `Object fetch()` | `Object` | Không tự suy luận thành lớp của đối tượng được trả về |
| `ArrayList<String> fetch()` | `ArrayList<String>` | Dùng được cả API riêng của `ArrayList` |

Các dòng trong bảng là các **chữ ký ví dụ độc lập**; không thể đặt nhiều phương thức `fetch()` trùng tên, trùng tham số chỉ khác kiểu trả về vào cùng một lớp Java.

## 3. Khi phương thức khai báo trả về lớp cụ thể

Nếu phương thức **khai báo** trả về `ArrayList<String>`, kiểu suy luận của `var` là `ArrayList<String>`:

~~~java
static java.util.ArrayList<String> loadArrayList() {
    return new java.util.ArrayList<>(java.util.List.of("An", "Bình"));
}

// Đặt trong phương thức:
var names = loadArrayList();  // ArrayList<String>
names.ensureCapacity(20);    // Hợp lệ: phương thức của ArrayList
~~~

Lưu ý: `ensureCapacity(20)` chỉ điều chỉnh khả năng chứa nội bộ, không thêm 20 phần tử vào danh sách.

So sánh hai tình huống:

~~~java
var a = loadNames();      // List<String>, do chữ ký loadNames()
var b = loadArrayList();  // ArrayList<String>, do chữ ký loadArrayList()

// a.ensureCapacity(20);  // Lỗi biên dịch
b.ensureCapacity(20);     // Hợp lệ
~~~

Cả `a` và `b` có thể đang trỏ tới đối tượng `ArrayList`, nhưng kiểu tĩnh của chúng khác nhau. Không có bước suy luận lại kiểu trong lúc chạy.

Đôi khi nên chủ động khai báo kiểu giao diện ngay cả khi phương thức trả về lớp cụ thể:

~~~java
java.util.List<String> names = loadArrayList();
~~~

Cách này làm rõ rằng phần mã phía sau chỉ cần hợp đồng `List`. Ngược lại, `var names = loadArrayList();` chọn đúng kiểu `ArrayList<String>`; đó là lựa chọn hợp lệ khi kiểu cụ thể hữu ích và rõ ràng.

## 4. Chương trình chạy được: cùng lớp đối tượng, hai kiểu tĩnh

Lưu thành tệp **`VarFromMethodReturnDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class VarFromMethodReturnDemo {
    static List<String> asInterface() {
        return new ArrayList<>(List.of("An", "Bình"));
    }

    static ArrayList<String> asConcrete() {
        return new ArrayList<>(List.of("An", "Bình"));
    }

    public static void main(String[] args) {
        var byInterface = asInterface();  // Kiểu tĩnh: List<String>
        var byConcrete = asConcrete();    // Kiểu tĩnh: ArrayList<String>

        System.out.println("interface first=" + byInterface.get(0));
        System.out.println("interface runtime="
                + byInterface.getClass().getSimpleName());
        System.out.println("concrete runtime="
                + byConcrete.getClass().getSimpleName());

        // Hợp lệ: LinkedList<String> cũng triển khai List<String>.
        byInterface = new LinkedList<>(List.of("Mai"));

        // Hợp lệ: byConcrete có kiểu tĩnh ArrayList<String>.
        byConcrete.ensureCapacity(20);

        System.out.println("reassigned first=" + byInterface.get(0));

        // Không hợp lệ (nếu bỏ chú thích):
        // byInterface.ensureCapacity(20);  // List không có phương thức này
        // byConcrete = new LinkedList<String>(); // Không phải ArrayList<String>
    }
}
~~~

Chạy bằng **JDK 17 trở lên** (cú pháp được dùng trong ví dụ tương thích Java 10):

~~~bash
javac VarFromMethodReturnDemo.java
java VarFromMethodReturnDemo
~~~

Kết quả `stdout`:

~~~text
interface first=An
interface runtime=ArrayList
concrete runtime=ArrayList
reassigned first=Mai
~~~

Cách đọc kết quả:

- `byInterface` có kiểu **`List<String>`** vì `asInterface()` khai báo như vậy; lúc đầu đối tượng thực tế là `ArrayList`.
- `byConcrete` có kiểu **`ArrayList<String>`** vì `asConcrete()` khai báo như vậy. Do đó gọi được `ensureCapacity`.
- Biến `byInterface` được phép nhận một `LinkedList<String>` mới sau đó vì cả hai triển khai `List<String>`. Phép gán không làm kiểu tĩnh `byInterface` thay đổi.
- `byConcrete` không thể nhận `LinkedList<String>` bởi đó không phải `ArrayList<String>`.

Đừng dùng `getClass()` làm căn cứ chọn phương thức được phép gọi trong mã nguồn. Nó mô tả lớp đối tượng ở **thời điểm chạy**, còn kiểm tra lời gọi phương thức dựa trên kiểu tĩnh.

## 5. Kiểu của biến còn phụ thuộc vào kiểu của đối tượng gọi phương thức

Java chọn chữ ký phương thức bằng thông tin kiểu ở **điểm gọi**. Đây là trường hợp đáng chú ý khi lớp triển khai override phương thức và khai báo kiểu trả về cụ thể hơn (*covariant return type*).

~~~java
import java.util.ArrayList;
import java.util.List;

interface NameSource {
    List<String> load();
}

class LocalNameSource implements NameSource {
    @Override
    public ArrayList<String> load() {
        return new ArrayList<>(List.of("An"));
    }
}

// Các dòng sau đặt trong một phương thức:
NameSource source = new LocalNameSource();
var fromInterface = source.load();            // List<String>

LocalNameSource concreteSource = new LocalNameSource();
var fromConcrete = concreteSource.load();     // ArrayList<String>
~~~

Cùng một đối tượng triển khai `LocalNameSource`, nhưng biểu thức `source.load()` được phân tích theo kiểu tĩnh `NameSource` nên có kiểu `List<String>`. Biểu thức `concreteSource.load()` dùng chữ ký override trên `LocalNameSource`, trả về `ArrayList<String>`.

Java vẫn dùng cơ chế dispatch động để chạy phần triển khai phù hợp; **dispatch động không biến `var` thành kiểu động**. Nếu thấy kết quả suy luận khác mong đợi, kiểm tra cả **kiểu của biến/biểu thức đứng trước dấu chấm** lẫn chữ ký phương thức được chọn.

## 6. Trường hợp generic: vì sao không phải lúc nào cũng đọc mỗi chữ ký là đủ?

Với phương thức generic, kiểu trả về có thể chứa tham số kiểu như `T`. Trình biên dịch suy luận `T` từ đối số và ngữ cảnh hợp lệ **trước khi** có kiểu cuối cùng của biểu thức gọi phương thức. `var` lấy kiểu của biểu thức đó.

Ví dụ trong thư viện chuẩn:

~~~java
import java.util.Collections;
import java.util.List;

// Các khai báo sau đặt trong một phương thức:
var unknown = Collections.emptyList();          // List<Object>
List<String> expected = Collections.emptyList(); // List<String>
var explicit = Collections.<String>emptyList();  // List<String>
var byArgument = Collections.singletonList("An");// List<String>
~~~

`Collections.emptyList()` có chữ ký generic dạng `<T> List<T> emptyList()`. Khi gán vào `List<String> expected`, kiểu đích từ bên trái giúp suy luận `T = String`. Với `var unknown`, **không có kiểu đích `List<String>` từ biến bên trái**, và lời gọi không có đối số để chỉ ra `T`, nên kiểu được suy luận trong trường hợp này là `List<Object>`.

Hai cách cho ý định `List<String>` rõ ràng là:

~~~java
List<String> names = Collections.emptyList();
var names2 = Collections.<String>emptyList();
~~~

Trong khi đó, `Collections.singletonList("An")` có đối số kiểu `String`, cung cấp dữ kiện để suy luận kết quả `List<String>` ngay cả khi bên trái dùng `var`.

**Cẩn thận:** `Collections.emptyList()` và `List.of(...)` trả về các danh sách không hỗ trợ thêm/xóa phần tử theo API; tính chất này đến từ phương thức tạo danh sách, **không phải từ `var`**. `List<String>` mô tả kiểu phần tử và API, không hứa rằng danh sách có thể sửa được.

### Phương thức khai báo trả về `Object`

~~~java
static Object loadText() {
    return "Java";
}

// Trong phương thức:
var value = loadText();        // Object, dù đối tượng thực tế là String
// value.length();             // Lỗi biên dịch: Object không có length()
String text = (String) value;  // Ép kiểu tường minh; chỉ an toàn khi đúng lớp thực tế
~~~

Nếu API luôn trả về `String`, việc sửa chữ ký thành `String loadText()` khi phù hợp hợp đồng sẽ tạo mã gọi dễ hiểu hơn. Tránh ép kiểu chỉ để bù cho một hợp đồng kiểu trả về quá rộng, trừ khi API buộc phải có kiểu rộng và bạn đã xử lý tính an toàn của phép ép kiểu.

## 7. `var` không thay đổi quy tắc generic hoặc tính bất biến

Với `var names = asInterface();`, tham số kiểu `String` được giữ lại. Vì thế:

~~~java
var names = asInterface(); // List<String>
names.add("Mai");         // Hợp lệ với danh sách ArrayList được trả về trong ví dụ
// names.add(123);        // Lỗi biên dịch: Integer không tương thích String
~~~

`var` không bỏ kiểm tra generic và không thay thế `List<String>` bằng một “danh sách bất kỳ”.

Tương tự, `final var names = asInterface();` có kiểu tĩnh `List<String>`, đồng thời cấm **gán lại biến `names`**. Nó không tự ngăn `names.add("Mai")` nếu đối tượng thực tế cho phép sửa. `final` và `var` giải quyết hai vấn đề khác nhau: khóa phép gán và suy luận kiểu tĩnh.

Với phương thức trả về giao diện `List<String>`, bản thân interface không quyết định liệu danh sách có sửa được hay không. Ví dụ một phương thức có thể trả về `ArrayList` có thể sửa; phương thức khác có thể trả về `List.of(...)` không sửa được. Không dùng tên biến `var` để suy đoán khả năng thay đổi.

## 8. Chọn kiểu tường minh hay `var` trong mã thực tế

| Tình huống | Viết gì? | Lý do |
| --- | --- | --- |
| `loadNames()` trả về `List<String>` và ngữ cảnh đã rõ | `var names = loadNames();` | Gọn, vẫn giữ hợp đồng `List<String>` |
| Người đọc không thể đoán kiểu trả về từ tên phương thức | `List<String> names = loadNames();` | Giúp thấy API ngay tại vị trí khai báo |
| Muốn cố ý chỉ sử dụng giao diện dù factory trả về `ArrayList` | `List<String> names = asConcrete();` | Nêu rõ phụ thuộc vào giao diện |
| Thực sự cần phương thức riêng của `ArrayList` và API trả về `ArrayList` | `var buffer = asConcrete();` | Suy luận đúng kiểu cụ thể |
| Gọi generic factory mà không đủ dữ kiện về `T` | `List<String> names = Collections.emptyList();` | Giữ rõ kiểu phần tử mong muốn |
| Muốn biến tham chiếu chỉ được gán một lần | `final var names = loadNames();` | Không thay đổi kiểu suy luận, nhưng chặn gán lại |

**Quy tắc thực hành:** Khi gặp `var x = service.method();`, hãy xem **chữ ký trả về của `method()` trên kiểu tĩnh của `service`**. Nếu đó là phương thức generic, kiểm tra cả quy tắc suy luận tham số kiểu ở lời gọi. Nếu kiểu không dễ đoán và ảnh hưởng cách dùng biến, viết kiểu tường minh là lựa chọn tốt.

Chữ ký phương thức luôn phải khai báo kiểu trả về hợp lệ; `var` không được dùng làm kiểu trả về cho phương thức. Nó là cơ chế suy luận kiểu cho các vị trí khai báo biến mà Java hỗ trợ, đặc biệt biến cục bộ có biểu thức khởi tạo.

## 9. Bài tập tự kiểm tra

Giả sử các phương thức được khai báo như sau (mỗi chữ ký nằm trong một lớp thích hợp):

~~~java
static java.util.List<String> api() {
    return new java.util.ArrayList<>();
}

static java.util.ArrayList<String> concreteApi() {
    return new java.util.ArrayList<>();
}

static Object genericApi() {
    return "Hello";
}
~~~

Trong một phương thức khác, xét:

~~~java
var a = api();
var b = concreteApi();
var c = genericApi();

// a.ensureCapacity(10);
// b.ensureCapacity(10);
// c.length();
~~~

**Câu hỏi:** Kiểu tĩnh của `a`, `b`, `c` lần lượt là gì? Dòng gọi phương thức nào trong ba dòng cuối biên dịch được nếu bỏ chú thích? Kiểu thực tế có thể khác kiểu tĩnh ở điểm nào?

**Đáp án:**

1. `a` là `List<String>`, dù `api()` trả về đối tượng `ArrayList`. Không thể gọi `a.ensureCapacity(10)` vì `List` không khai báo phương thức đó.
2. `b` là `ArrayList<String>`, nên `b.ensureCapacity(10)` hợp lệ.
3. `c` là `Object`, dù thực tế chứa `String`. Không thể gọi `c.length()` vì `Object` không có phương thức `length()`.
4. Cả ba đối tượng đều có thể có lớp runtime cụ thể khác với kiểu tĩnh: `a` và `b` thực tế là `ArrayList`; `c` là `String`. Kiểu tĩnh mới là căn cứ Java dùng để kiểm tra các lời gọi trong ví dụ.

## 10. Điều cần nhớ

- **`var` lấy kiểu của biểu thức ở thời điểm biên dịch.** Với lời gọi phương thức thông thường, kiểu đó gắn với chữ ký trả về được chọn tại điểm gọi.
- **Phương thức khai báo giao diện** → biến `var` thường có kiểu giao diện, dù đối tượng thực tế thuộc lớp cụ thể.
- **Phương thức khai báo lớp cụ thể** → biến `var` có kiểu lớp cụ thể, nếu không có quy tắc generic đặc biệt làm thay đổi kết quả.
- **Với generic**, kiểu của biểu thức còn phụ thuộc vào suy luận tham số kiểu và ngữ cảnh lời gọi; `var` không cung cấp kiểu đích giống `List<String> names = ...`.
- **Kiểu tĩnh khác lớp runtime**; `getClass()` không làm xuất hiện thêm phương thức trên kiểu tĩnh của biến.

Tham khảo: [Java Language Specification — Local Variable Declarations (`14.4)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.4) và [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286).
