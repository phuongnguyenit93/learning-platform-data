# `var` kết hợp diamond `<>` trong lời gọi hàm tạo (Java 10+)

## 1. Mục tiêu bài học

Trong Java, `var` và toán tử diamond `<>` đều hỗ trợ suy luận kiểu để giảm lặp khi khai báo biến generic. Tuy nhiên, chúng hoạt động ở **hai vị trí khác nhau**:

- **`var` ở vế trái**: trình biên dịch suy ra **kiểu tĩnh của biến cục bộ** từ biểu thức khởi tạo.
- **`<>` ở lời gọi hàm tạo**: trình biên dịch suy ra **đối số kiểu generic** của lớp được tạo, dựa trên ngữ cảnh và các đối số truyền vào constructor.

Hai cơ chế đều được kiểm tra ở **thời điểm biên dịch**. Chúng không làm Java thành ngôn ngữ kiểu động và không tự tìm cách hiểu ý định lập trình viên từ những lệnh viết phía sau.

Bài tập trung vào trường hợp kết hợp `var` với diamond, cách giữ thông tin kiểu generic khi tạo `List`, `ArrayList`, `Map`, `HashMap`, và cách tránh vô tình suy ra `Object`. Tất cả ví dụ dùng cú pháp còn phù hợp ở JDK 17+.

## 2. Diamond suy luận đối số kiểu từ đâu?

Giả sử muốn tạo danh sách chuỗi. Cách viết tường minh:

~~~java
ArrayList<String> names = new ArrayList<String>();
~~~

Với diamond:

~~~java
ArrayList<String> names = new ArrayList<>();
~~~

Trình biên dịch thấy vế trái có kiểu **`ArrayList<String>`**, nên lời gọi `new ArrayList<>()` được suy ra đối số kiểu `String`. Khi khai báo theo interface, quy tắc tương tự:

~~~java
List<String> names = new ArrayList<>();
Map<String, Integer> counts = new HashMap<>();
~~~

Các ví dụ trong phần này là đoạn mã đặt bên trong phương thức, giả sử đã import các lớp `java.util`.

- `List<String>` cung cấp **target type** (kiểu đích) cho biểu thức tạo `ArrayList`.
- `Map<String, Integer>` giúp diamond suy ra cả kiểu khóa `String` và kiểu giá trị `Integer`.
- `names.add("An")` được phép; `names.add(100)` bị từ chối ở compile time.
- `counts.put("Java", 10)` hợp lệ; `counts.put(10, "Java")` bị từ chối bởi kiểu khóa/giá trị.

Diamond **không phải raw type**: cú pháp `new ArrayList<>()` vẫn yêu cầu trình biên dịch xác định các đối số kiểu generic.

## 3. Điều gì xảy ra khi dùng `var` và diamond cùng lúc?

Hãy xét riêng ba khai báo:

~~~java
List<String> first = new ArrayList<>();
var second = new ArrayList<String>();
var third = new ArrayList<>();
~~~

| Khai báo | Kiểu tĩnh được suy ra/khai báo | Nguồn thông tin generic |
| --- | --- | --- |
| `first` | `List<String>` | `String` xuất hiện ở kiểu đích bên trái |
| `second` | `ArrayList<String>` | `String` xuất hiện trực tiếp trong lời gọi constructor |
| `third` | `ArrayList<Object>` | Không có kiểu đích hay đối số constructor cung cấp kiểu phần tử cụ thể |

Trong câu `var third = new ArrayList<>();`, chính `var` cần suy luận kiểu từ biểu thức bên phải, nên **không có khai báo `List<String>` làm kiểu đích cho diamond**. Constructor rỗng cũng không chứa dữ liệu phần tử. Khi không có ràng buộc cụ thể hơn, đối số generic được suy ra là `Object`, và kiểu biến là **`ArrayList<Object>`**.

Điều này tạo ra hành vi có thể gây hiểu nhầm:

~~~java
var items = new ArrayList<>(); // ArrayList<Object>
items.add("Java");
items.add(10);                  // int được boxing thành Integer

Object a = items.get(0);
// items.get(0).toUpperCase(); // Lỗi: kiểu trả về là Object
~~~

Cả `String` lẫn `Integer` đều là kiểu con của `Object`, nên có thể được đưa vào `ArrayList<Object>`. Đây là **kiểm tra kiểu tĩnh với kiểu rộng**, không phải thay đổi kiểu của `items` theo từng phần tử.

**Đặc biệt:** trình biên dịch không nhìn những lệnh `add` sau đó để suy ra lại `String` hoặc `Integer`. Kiểu của biến đã được xác định khi khai báo.

## 4. Ba cách giữ đúng thông tin generic

### Cách 1: Kiểu tường minh ở vế trái, diamond ở vế phải

~~~java
List<String> names = new ArrayList<>();
Map<String, Integer> ages = new HashMap<>();
~~~

Ưu điểm: thông tin kiểu xuất hiện ngay nơi khai báo; biến phụ thuộc interface `List` hoặc `Map` thay vì lớp triển khai. Cách này rất phù hợp khi tạo collection rỗng.

### Cách 2: `var` ở vế trái, generic rõ ràng trong constructor

~~~java
var names = new ArrayList<String>();
var ages = new HashMap<String, Integer>();
~~~

Kiểu được suy ra lần lượt là `ArrayList<String>` và `HashMap<String,Integer>`. Mặc dù dùng `var`, đối số kiểu `String` và `Integer` không hề bị mất.

Đánh đổi: `var names` có kiểu tĩnh là **`ArrayList<String>`**, không phải interface `List<String>`. Nếu phần còn lại của phương thức nên làm việc với interface, cân nhắc cách 1.

### Cách 3: Dùng diamond nhưng đưa thông tin generic qua đối số constructor

~~~java
List<String> original = List.of("An", "Binh");
var copied = new ArrayList<>(original);
copied.add("Chi");
~~~

Constructor của `ArrayList` nhận collection nguồn với kiểu phần tử đã biết. Từ `List<String>`, trình biên dịch suy ra `E = String`; sau đó `var` suy ra **`ArrayList<String>`**.

Ví dụ ngắn hơn:

~~~java
var names = new ArrayList<>(List.of("An", "Binh"));
// names có kiểu ArrayList<String>
names.add("Chi");
// names.add(42); // Lỗi biên dịch: Integer không phải String
~~~

Ở đây thông tin kiểu `String` đến từ biểu thức `List.of("An", "Binh")` được truyền cho constructor. Vì vậy **`var` kết hợp diamond không tự động là cách viết sai**: quan trọng là constructor có đủ dữ liệu kiểu hay không.

## 5. Khi nguồn là collection rỗng

Đây là trường hợp rất dễ suy luận ra kiểu rộng hơn mong muốn:

~~~java
var a = new ArrayList<>();                    // ArrayList<Object>
var b = new ArrayList<>(List.of());           // ArrayList<Object>
var c = new ArrayList<String>();              // ArrayList<String>
var d = new ArrayList<>(List.<String>of());   // ArrayList<String>
List<String> e = new ArrayList<>();            // List<String>
~~~

Giải thích:
1. `a`: constructor rỗng và không có kiểu đích để suy ra `String`.
2. `b`: `List.of()` không nhận phần tử, nên cũng không cung cấp kiểu phần tử cụ thể; trong ngữ cảnh này suy ra `Object`.
3. `c`: `String` được viết trực tiếp ở constructor.
4. `d`: `List.<String>of()` dùng **type witness** để nói rõ danh sách nguồn là `List<String>`; diamond của `ArrayList` suy ra `String`.
5. `e`: `List<String>` ở vế trái cung cấp kiểu đích.

`List.of(...)` tạo danh sách không thể thêm/xóa phần tử, nhưng `new ArrayList<>(List.of(...))` tạo **bản sao `ArrayList` có thể sửa đổi**. Việc sao chép không biến `ArrayList` thành immutable collection.

Khi cần danh sách rỗng có kiểu phần tử rõ ràng, hãy ưu tiên cách giản dị:

~~~java
List<String> names = new ArrayList<>();
// hoặc
var names2 = new ArrayList<String>();
~~~

Hai lệnh trên dùng hai tên biến khác nhau để có thể đứng cùng khối. Không phải vì `var` luôn buộc phải chỉ rõ generic ở constructor; đây là lựa chọn để tránh suy luận thiếu thông tin.

## 6. Ví dụ hoàn chỉnh, biên dịch và chạy được trên Java 17+

Tạo tệp **VarDiamondDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class VarDiamondDemo {
    public static void main(String[] args) {
        // Không có thông tin phần tử: ArrayList<Object>.
        var mixed = new ArrayList<>();
        mixed.add("Java");
        mixed.add(10);
        System.out.println("mixed size = " + mixed.size());
        System.out.println("mixed types = "
                + mixed.get(0).getClass().getSimpleName() + ", "
                + mixed.get(1).getClass().getSimpleName());

        // Dùng var nhưng ghi rõ generic ở constructor.
        var names = new ArrayList<String>();
        names.add("An");
        names.add("Binh");
        System.out.println("names first = "
                + names.get(0).toUpperCase());

        // Kiểu đích ở vế trái giúp diamond suy ra String.
        List<String> typed = new ArrayList<>();
        typed.add("Chi");
        System.out.println("typed first = "
                + typed.get(0).toUpperCase());

        // Constructor suy luận từ đối số List<String>.
        var copied = new ArrayList<>(List.of("Mai", "Lan"));
        copied.add("Hoa");
        System.out.println("copied = "
                + String.join(", ", copied));

        // Ghi rõ hai đối số generic cho Map.
        var ages = new HashMap<String, Integer>();
        ages.put("An", 20);
        System.out.println("age of An = " + ages.get("An"));

        // Kiểu đích theo interface Map.
        Map<String, Integer> scores = new HashMap<>();
        scores.put("Java", 100);
        System.out.println("score Java = " + scores.get("Java"));

        // Bản sao từ danh sách rỗng có type witness Long.
        var ids = new ArrayList<>(List.<Long>of());
        ids.add(5L);
        System.out.println("first id = " + ids.get(0));
    }
}
~~~

Chạy trong thư mục chứa tệp, dùng JDK 17 trở lên:

~~~bash
javac VarDiamondDemo.java
java VarDiamondDemo
~~~

**Kết quả chính xác:**

~~~text
mixed size = 2
mixed types = String, Integer
names first = AN
typed first = CHI
copied = Mai, Lan, Hoa
age of An = 20
score Java = 100
first id = 5
~~~

**Những điều cần quan sát:**
- `mixed` có kiểu `ArrayList<Object>`, nên nhận cả chuỗi lẫn số được boxing. `getClass()` chỉ phản ánh lớp của đối tượng lúc chạy, không thay đổi kiểu tĩnh của các phần tử được đọc qua `mixed.get(...)`.
- `names` có kiểu `ArrayList<String>`; vì vậy `get(0).toUpperCase()` được kiểm tra hợp lệ ở compile time.
- `typed` có kiểu tĩnh `List<String>`, nhưng đối tượng là `ArrayList<String>`. Sự khác nhau giữa interface và lớp triển khai là chủ ý thiết kế.
- `copied` suy ra `ArrayList<String>` nhờ kiểu phần tử của danh sách được truyền vào constructor.
- `ages` giữ chính xác cả kiểu khóa và giá trị; `scores` làm điều tương tự nhưng khai báo qua interface `Map`.
- `ids` có kiểu `ArrayList<Long>` vì `List.<Long>of()` cung cấp thông tin generic cụ thể.

Chương trình không phụ thuộc thứ tự duyệt `HashMap`: nó chỉ lấy giá trị theo khóa đã biết, nên kết quả trên ổn định.

## 7. Các trường hợp không biên dịch và cách sửa

Những ví dụ dưới đây **cố ý không hợp lệ**; chúng không thuộc chương trình hoàn chỉnh ở mục 6.

### 7.1. Tưởng lệnh `add` giúp suy luận `String`

~~~java
var words = new ArrayList<>(); // ArrayList<Object>
words.add("one");
words.add("two");
// String first = words.get(0); // Lỗi: Object không gán trực tiếp cho String
~~~

Sửa bằng cách chỉ rõ kiểu ngay ở initializer hoặc kiểu đích:

~~~java
var words = new ArrayList<String>();
words.add("one");
String first = words.get(0);
~~~

Hai ví dụ là hai đoạn độc lập, không đặt trong cùng một scope vì tên `words` trùng nhau.

### 7.2. Nhầm `ArrayList<Object>` với `List<String>`

~~~java
var data = new ArrayList<>();
// List<String> names = data; // Lỗi biên dịch
~~~

`data` có kiểu `ArrayList<Object>`. Generic Java có **tính bất biến** (*invariance*): `List<Object>` không phải `List<String>`, dù mọi đối tượng `String` đều là `Object`. Không thể tự động “thu hẹp” kiểu phần tử khi gán.

Sửa đúng: chọn `List<String> data = new ArrayList<>();` hoặc `var data = new ArrayList<String>();` ngay từ đầu, khi mục đích thực sự là danh sách chuỗi.

### 7.3. Dùng `var new ArrayList<>()` nhưng mong compiler suy ra khóa/giá trị của Map từ lệnh `put`

~~~java
var map = new HashMap<>(); // HashMap<Object, Object>
map.put("Java", 10);
map.put(7, "seven");       // Vẫn hợp lệ về mặt generic Object/Object
~~~

Sửa để trình biên dịch kiểm tra dữ liệu:

~~~java
var map = new HashMap<String, Integer>();
map.put("Java", 10);
// map.put(7, "seven"); // Lỗi: sai cả kiểu khóa và kiểu giá trị
~~~

### 7.4. Nhầm diamond với raw type

~~~java
var typed = new ArrayList<>(); // ArrayList<Object>, có generic
~~~

Dấu `<>` kích hoạt suy luận kiểu generic; nó không tắt generic. Dạng raw như `new ArrayList()` không cung cấp đối số kiểu và có thể làm mất kiểm tra kiểu hữu ích. Trong code Java hiện đại, ưu tiên kiểu có tham số generic và không dùng raw type để “né” lỗi suy luận.

### 7.5. Nhầm suy luận kiểu generic với suy luận kiểu biến

~~~java
var list = new ArrayList<>(List.of(1, 2, 3));
list.add(4);
System.out.println(list.get(0).intValue()); // 1
~~~

Dòng đầu gồm **hai bước logic**: diamond suy ra `Integer` từ constructor argument, rồi `var` suy ra kiểu `ArrayList<Integer>` của biểu thức hoàn chỉnh. Từ đó, các phép gọi trên phần tử được kiểm tra như `Integer`, không phải `Object`.

## 8. `var` có thể làm lộ kiểu triển khai thay vì interface

So sánh hai khai báo:

~~~java
List<String> names = new ArrayList<>();
var otherNames = new ArrayList<String>();
~~~

Cả hai quản lý phần tử `String`, nhưng khác **kiểu tĩnh của biến**:
- `names`: `List<String>`, biểu diễn hợp đồng thao tác với danh sách.
- `otherNames`: `ArrayList<String>`, cho phép gọi cả những phương thức cụ thể của `ArrayList`.

Ví dụ, `otherNames.ensureCapacity(100)` hợp lệ vì kiểu tĩnh là `ArrayList<String>`, còn `names.ensureCapacity(100)` không hợp lệ khi biến chỉ có kiểu tĩnh `List<String>`. Đó là khác biệt trong API khả dụng, không phải về dữ liệu phần tử.

Vì vậy không nên mặc định chuyển **mọi** khai báo kiểu interface sang `var`. Khi cần giảm phụ thuộc vào lớp triển khai, khai báo `List<T>` hoặc `Map<K,V>` tường minh vẫn là lựa chọn rõ ràng.

## 9. Type erasure và cách hiểu đúng kết quả runtime

Với:

~~~java
var strings = new ArrayList<String>();
var objects = new ArrayList<>();
// strings.add(42); // Lỗi biên dịch: Integer không hợp lệ cho ArrayList<String>
objects.add(42);    // Hợp lệ cho ArrayList<Object>
~~~

Java kiểm tra đối số kiểu generic trong quá trình biên dịch. Do **type erasure**, phần lớn thông tin tham số generic không còn được phản ánh như một lớp riêng ở runtime: `strings.getClass()` và `objects.getClass()` cùng chỉ đến lớp `ArrayList`.

Không thể dùng một lệnh `getClass()` để suy ra rằng một instance là `ArrayList<String>` hay `ArrayList<Object>`. Chính **kiểu khai báo lúc biên dịch** mới điều khiển những thao tác như `add` và kiểu trả về của `get`.

Khi đọc một `Object` và thực sự cần dùng API của `String`, hãy thu hẹp kiểu an toàn:

~~~java
var mixed = new ArrayList<>();
mixed.add("Java");
Object value = mixed.get(0);
if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

`instanceof` pattern matching ở đây hợp lệ với JDK 17+. Nó không biến `mixed` thành `ArrayList<String>`; `text` chỉ là biến đã được kiểm tra kiểu trong phạm vi nhánh điều kiện.

## 10. Chọn cách viết phù hợp

| Nhu cầu | Cách khai báo khuyến nghị | Lý do |
| --- | --- | --- |
| Danh sách rỗng có kiểu phần tử cụ thể, ưu tiên interface | `List<String> list = new ArrayList<>();` | Có target type, tránh suy luận `Object` |
| Danh sách rỗng nhưng muốn dùng `var` | `var list = new ArrayList<String>();` | Generic đủ rõ ở constructor |
| Bản sao từ một `List<String>` có sẵn | `var copy = new ArrayList<>(source);` | Kiểu của `source` giúp suy luận `String` |
| Map rỗng với khóa/giá trị đã xác định | `Map<String,Integer> map = new HashMap<>();` | Khóa và giá trị được kiểm tra chặt từ đầu |
| Collection thật sự cần giữ nhiều loại đối tượng | Chỉ định `List<Object>` có chủ ý | Thể hiện quyết định chọn kiểu phần tử rộng, giúp người đọc không đoán nhầm |
| Không cần thao tác sửa danh sách | `var names = List.of("A", "B");` | Suy ra `List<String>`; không cần tạo thêm `ArrayList` |

Nguyên tắc thực tế: hãy kiểm tra **kiểu được suy ra có đúng hợp đồng dữ liệu hay không** trước khi chọn cách viết ngắn nhất. Nếu biểu thức bên phải đã bộc lộ kiểu rõ ràng, `var` có thể rất hữu ích. Nếu hai phía đều yêu cầu suy luận mà không có đối số đủ thông tin, nên viết rõ generic ở một phía.

## 11. Câu hỏi tự kiểm tra

**1. `var list = new ArrayList<>();` thường có kiểu gì?**  
`ArrayList<Object>`, vì thiếu target type và constructor rỗng không cho biết kiểu phần tử cụ thể.

**2. `List<String> list = new ArrayList<>();` vì sao có thể nhận `String`?**  
Kiểu đích `List<String>` giúp diamond suy ra tham số generic `String`.

**3. `var list = new ArrayList<>(List.of("A", "B"));` có kiểu gì?**  
`ArrayList<String>` do kiểu `String` được suy ra từ các phần tử nguồn đưa vào constructor.

**4. Hai lệnh dưới đây có cùng kiểu tĩnh không?**

~~~java
List<String> a = new ArrayList<>();
var b = new ArrayList<String>();
~~~

Không. Biến `a` có kiểu tĩnh `List<String>`, biến `b` có kiểu tĩnh `ArrayList<String>`; cả hai giữ đúng kiểu phần tử `String`.

**5. `var list = new ArrayList<>(); list.add("A");` có khiến `list` trở thành `ArrayList<String>` không?**  
Không. Kiểu tĩnh đã được quyết định ở dòng khai báo; các lệnh `add` phía sau không tham gia suy luận lại.

**6. `new ArrayList<>()` có tương đương `new ArrayList()` không?**  
Không. Dấu diamond yêu cầu suy luận generic; dạng không có đối số kiểu ở lời gọi `new ArrayList()` là raw type và nên tránh trong code Java hiện đại.

## 12. Ghi nhớ cuối bài

- **`var`** suy ra kiểu **biến**, còn **`<>`** suy ra **đối số generic của constructor**.
- Với `var list = new ArrayList<>();`, thiếu thông tin kiểu dẫn đến `ArrayList<Object>`; điều này vẫn hoàn toàn là **kiểu tĩnh**.
- Có thể kết hợp `var` và diamond một cách an toàn nếu **đối số constructor** mang đủ thông tin kiểu, như `new ArrayList<>(List.of("A"))`.
- Muốn đảm bảo `List<String>`, `Map<String,Integer>` hoặc generic khác, hãy đưa thông tin đó vào **kiểu đích** hoặc **constructor**, tránh chỉ dựa vào những câu lệnh sử dụng về sau.
- Trong mã cần hợp đồng interface rõ ràng, `List<T>` và `Map<K,V>` tường minh thường dễ bảo trì hơn.

**Đọc thêm:** [Oracle — Local Variable Type Inference (JDK 17)](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html), [Dev.java — Type Inference](https://dev.java/learn/generics/type-inference/) và [OpenJDK — Local Variable Type Inference Style Guidelines](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-style-guide.md).
