# Trường hợp diamond thiếu thông tin để suy luận kiểu phần tử mong muốn

**Chủ đề:** `var` và generics trong Java 10 trở lên. Bài học giải thích vì sao `var list = new ArrayList<>();` có thể cho kết quả khác với `List<String> list = new ArrayList<>();`, cách phát hiện kiểu đã suy luận và cách cung cấp đủ thông tin khi cần một kiểu phần tử cụ thể. Các quy tắc này vẫn áp dụng trong Java hiện đại; chương trình hoàn chỉnh được viết với cú pháp chạy được từ Java 10 và kiểm tra trên JDK hiện đại bằng `--release 10`.

## 1. Diamond (`<>`) và `var` giải quyết hai phần khác nhau

**Diamond operator** là cặp dấu `<>` ở phía tạo đối tượng generic, chẳng hạn `new ArrayList<>()`. Java hỗ trợ diamond từ Java 7; trình biên dịch cố gắng suy luận các đối số kiểu nằm bên trong `<>` từ ngữ cảnh biểu thức và các ràng buộc sẵn có.

**`var`** (suy luận kiểu biến cục bộ, Java 10+) nằm ở **bên trái** khai báo. Nó cho phép trình biên dịch lấy kiểu của biến từ biểu thức khởi tạo thay vì yêu cầu người viết lặp lại kiểu tường minh.

Hai tính năng có thể kết hợp:

~~~java
var items = new ArrayList<>();
~~~

Nhưng ở dòng này, **`var` không cho trình biên dịch biết rằng phần tử mong muốn là `String`, `Integer` hay một kiểu khác**. Đồng thời `new ArrayList<>()` không có đối số constructor nào mang thông tin về kiểu phần tử. Với `ArrayList<E>` có giới hạn kiểu mặc định là `Object`, kiểu được suy luận là **`ArrayList<Object>`**.

So sánh ba khai báo sau:

~~~java
List<String> first = new ArrayList<>();    // kiểu biến: List<String>
var second = new ArrayList<String>();      // kiểu biến: ArrayList<String>
var third = new ArrayList<>();             // kiểu biến: ArrayList<Object>
~~~

*Các dòng trên là đoạn minh họa; giả sử đã import `java.util.List` và `java.util.ArrayList`.*

Ở `first`, **kiểu đích** `List<String>` ở bên trái truyền ràng buộc `String` tới biểu thức khởi tạo; diamond có thể suy luận `E = String`. Ở `second`, đối số kiểu `String` được cung cấp trực tiếp cho constructor, nên `var` suy luận `ArrayList<String>`. Ở `third`, không có thông tin kiểu phần tử cần thiết, nên `E` trở thành `Object`.

Điểm mấu chốt: **trình biên dịch suy luận kiểu ở lúc xử lý khai báo**, không chờ những lệnh `add(...)` xuất hiện sau đó để đoán ý định.

## 2. Vì sao `var list = new ArrayList<>()` thường không phải `List<String>`?

Giả sử muốn tạo danh sách chỉ chứa tên người dùng:

~~~java
var names = new ArrayList<>();
names.add("An");
names.add("Binh");
names.add(42); // VẪN biên dịch: names là ArrayList<Object>
~~~

Những lời gọi `add` sau khai báo không khiến kiểu `ArrayList<Object>` thay đổi. Vì `String` và `Integer` đều là `Object`, cả ba lời gọi trên đều hợp lệ. Nếu đây là dữ liệu tên người dùng, trình biên dịch đã không còn giúp ngăn thêm sai loại dữ liệu như mong đợi.

Khi lấy phần tử:

~~~java
var names = new ArrayList<>();
names.add("An");
// String name = names.get(0); // LỖI: get(0) có kiểu Object
Object value = names.get(0);  // hợp lệ
~~~

`names.get(0)` có **kiểu tĩnh** là `Object`. Dù giá trị thực tế ở vị trí 0 là một chuỗi, điều đó không biến toàn bộ danh sách thành `List<String>`.

Một hàm nhận `List<String>` cũng không nhận được `ArrayList<Object>`:

~~~java
static void requireStrings(List<String> strings) {
    System.out.println(strings.size());
}

// ...
var names = new ArrayList<>();
names.add("An");
// requireStrings(names); // LỖI: ArrayList<Object> không phải List<String>
~~~

Đây là các **đoạn minh họa**, không phải chương trình hoàn chỉnh. Java generics là **bất biến** (*invariant*) theo đối số kiểu: `List<Object>` không tự động là `List<String>`, cũng như `List<String>` không tự động là `List<Object>`.

Vì thế, khi thực sự cần `String`, sửa ở **nguồn ràng buộc kiểu**, thay vì ép kiểu sau khi danh sách đã được tạo.

## 3. Những cách cung cấp đủ thông tin cho diamond

### Cách 1 — Khai báo kiểu đích tường minh

~~~java
List<String> names = new ArrayList<>();
names.add("An");
// names.add(42); // LỖI: chỉ chấp nhận String
~~~

Vế trái `List<String>` cho biết rõ kiểu phần tử mong muốn, đồng thời khuyến khích lập trình theo giao diện `List`. Diamond suy luận `String` từ kiểu đích này. Chọn cách này khi API hoặc cấu trúc dữ liệu cần thể hiện kiểu tường minh.

### Cách 2 — Giữ `var` nhưng ghi đối số kiểu ở constructor

~~~java
var names = new ArrayList<String>();
names.add("An");
// names.add(42); // LỖI: chỉ chấp nhận String
~~~

Kiểu suy luận của biến `names` là **`ArrayList<String>`**, vì constructor đã cung cấp `String`. Đây thường là cách trực tiếp nhất để tạo một collection rỗng, có thể thay đổi, trong khi vẫn giữ `var`.

Tương tự với map:

~~~java
var scores = new HashMap<String, Integer>();
scores.put("Java", 10);
// scores.put("Java", "ten"); // LỖI: value phải là Integer
~~~

Ngược lại, `var scores = new HashMap<>();` khi không có ràng buộc khác sẽ suy luận **`HashMap<Object, Object>`**.

### Cách 3 — Đưa dữ liệu có kiểu vào constructor

~~~java
var names = new ArrayList<>(List.of("An", "Binh"));
names.add("Chi");
// names.add(42); // LỖI: phần tử phải là String
~~~

Ở đây `List.of("An", "Binh")` có kiểu `List<String>`. Constructor của `ArrayList` nhận `Collection<? extends E>`, nên trình biên dịch nhận được thông tin để suy luận `E = String`. Kiểu biến là **`ArrayList<String>`**.

Chú ý: `List.of(...)` tạo danh sách **không cho phép thêm/xóa phần tử**. Trong ví dụ, `new ArrayList<>(...)` tạo một bản sao có thể thay đổi; do đó `names.add("Chi")` hợp lệ. Nếu chỉ cần danh sách không thay đổi, có thể viết `var names = List.of("An", "Binh");` để nhận `List<String>` mà không cần `ArrayList` hay diamond.

### Cách 4 — Dùng type witness khi nguồn dữ liệu trống

Không có phần tử ban đầu để suy ra `String`? Có thể cung cấp đối số kiểu cho phương thức factory:

~~~java
var names = new ArrayList<>(List.<String>of());
names.add("An"); // hợp lệ: ArrayList<String>
~~~

`List.<String>of()` tạo một `List<String>` rỗng. Constructor nhận được collection có kiểu rõ ràng và suy luận `ArrayList<String>`. Với collection rỗng thông thường, `var names = new ArrayList<String>();` thường ngắn và dễ đọc hơn; *type witness* hữu ích khi cần giữ cách xây dựng từ một nguồn generic rỗng.

## 4. Bảng đối chiếu ngữ cảnh suy luận

| Mã khai báo | Kiểu tĩnh của biến | Nguồn thông tin kiểu |
| --- | --- | --- |
| `var a = new ArrayList<>();` | `ArrayList<Object>` | Không có ràng buộc phần tử; dùng giới hạn mặc định |
| `List<String> a = new ArrayList<>();` | `List<String>` | Kiểu đích từ vế trái |
| `var a = new ArrayList<String>();` | `ArrayList<String>` | Đối số kiểu tường minh của constructor |
| `var a = new ArrayList<>(List.of("a", "b"));` | `ArrayList<String>` | Kiểu dữ liệu đầu vào của constructor |
| `var a = new ArrayList<>(List.<String>of());` | `ArrayList<String>` | Type witness của factory rỗng |
| `var a = List.of("a", "b");` | `List<String>` | Kiểu suy luận từ các đối số của factory; không có diamond |
| `var m = new HashMap<>();` | `HashMap<Object, Object>` | Không có ràng buộc cho khóa/giá trị |
| `var m = new HashMap<String, Integer>();` | `HashMap<String, Integer>` | Hai đối số kiểu tường minh |

*Các biểu thức ở bảng giả định đã import `java.util.*` hoặc các lớp được nêu; mỗi hàng là một khai báo độc lập.*

Quy tắc `Object` ở đây áp dụng cho các tham số kiểu **không bị ràng buộc thêm** như `E` của `ArrayList<E>`. Không nên khái quát thành “mọi diamond không có dữ liệu đều suy luận `Object`”: với một lớp generic có giới hạn kiểu khác, kết quả có thể là giới hạn đó. Mục 7 đưa ví dụ.

## 5. Chương trình thực hành hoàn chỉnh, biên dịch được từ Java 10

Lưu mã vào tệp **`DiamondInferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;

public class DiamondInferenceDemo {
    static void requireStrings(List<String> strings) {
        System.out.println("first-upper=" +
                strings.get(0).toUpperCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        // Không có thông tin E: suy luận ArrayList<Object>.
        var loose = new ArrayList<>();
        loose.add("Java");
        loose.add(10);
        System.out.println("loose=" + loose);

        // Có target type List<String> cho diamond.
        List<String> fromTarget = new ArrayList<>();
        fromTarget.add("java");
        requireStrings(fromTarget);

        // Có type argument ngay trong constructor.
        var explicit = new ArrayList<String>();
        explicit.add("Generics");
        requireStrings(explicit);

        // Constructor nhận Collection có kiểu String.
        var fromArgument = new ArrayList<>(List.of("An", "Binh"));
        fromArgument.add("Chi");
        requireStrings(fromArgument);
        System.out.println("fromArgument=" + fromArgument);

        // Nguồn trống nhưng type witness vẫn cung cấp String.
        var emptyTyped = new ArrayList<>(List.<String>of());
        emptyTyped.add("Typed");
        requireStrings(emptyTyped);

        // Với map, cung cấp cả hai đối số kiểu nếu tạo rỗng.
        var scores = new HashMap<String, Integer>();
        scores.put("Java", 10);
        System.out.println("score=" + scores.get("Java"));
    }
}
~~~

Biên dịch và chạy bằng JDK có hỗ trợ chế độ nguồn Java 10:

~~~bash
javac --release 10 DiamondInferenceDemo.java
java DiamondInferenceDemo
~~~

Kết quả chuẩn:

~~~text
loose=[Java, 10]
first-upper=JAVA
first-upper=GENERICS
first-upper=AN
fromArgument=[An, Binh, Chi]
first-upper=TYPED
score=10
~~~

Lệnh `javac --release 10` yêu cầu JDK đủ mới và còn hỗ trợ mục tiêu biên dịch này; nếu dự án biên dịch trực tiếp bằng Java 17+, chỉ cần `javac DiamondInferenceDemo.java`. Mã nguồn không sử dụng tính năng Java mới hơn Java 10.

Quan sát hai khía cạnh:

1. `loose` chấp nhận hai kiểu phần tử khác nhau, vì `E` đã được suy ra là `Object` ở dòng khai báo.
2. Cả `fromTarget`, `explicit`, `fromArgument` và `emptyTyped` đều có phần tử `String`; vì vậy chúng đều truyền được vào `requireStrings(List<String>)` mà không cần cast.

Chương trình dùng `Locale.ROOT` để làm rõ việc chuyển chữ hoa trong ví dụ, tránh phụ thuộc locale mặc định của máy chạy.

## 6. Ví dụ cố ý lỗi để nhận diện kiểu suy luận

Đoạn dưới đây **không biên dịch**; không ghép vào chương trình đang chạy. Giả sử đã import `ArrayList` và `List`:

~~~java
static void requireStrings(List<String> values) {}

static void demonstrate() {
    var values = new ArrayList<>();  // ArrayList<Object>
    values.add("a");

    requireStrings(values);          // LỖI: không phải List<String>
    String item = values.get(0);     // LỖI: get(0) trả về Object
}
~~~

Hai lỗi minh họa độc lập:

- `requireStrings(values)` cần `List<String>`, nhưng biến `values` có kiểu `ArrayList<Object>`. Việc danh sách thực tế mới được thêm một chuỗi không làm thay đổi chữ ký generic.
- `String item = values.get(0)` cần một `String`, nhưng `get` có kiểu trả về `Object` theo khai báo `ArrayList<Object>`.

**Sửa đúng nguyên nhân:** thay dòng khai báo thành `var values = new ArrayList<String>();` hoặc `List<String> values = new ArrayList<>();`. Khi đó cả hai câu lệnh trở nên hợp lệ. Không dùng cast thô, kiểu raw `ArrayList` hoặc `@SuppressWarnings` để che lỗi: chúng làm giảm kiểm tra kiểu và có thể khiến lỗi chuyển sang lúc chạy.

### Cách đọc chẩn đoán từ trình biên dịch

Khi thấy lỗi dạng:

~~~text
incompatible types: ArrayList<Object> cannot be converted to List<String>
~~~

hãy quay lại **dòng khởi tạo** tìm kiểu phần tử mà trình biên dịch đã suy luận. Không nên chỉ kiểm tra phần tử đã `add` hoặc cho rằng dấu `<>` đồng nghĩa với kiểu mà người viết mong muốn.

## 7. Diamond còn phụ thuộc các giới hạn kiểu khác

Những ví dụ trước chủ yếu xét `ArrayList<E>` hoặc `HashMap<K,V>`, nơi tham số kiểu không có ràng buộc riêng ngoài `Object`. Một lớp có giới hạn `T extends Number` tạo tình huống khác.

Lưu thành **`BoundedInferenceDemo.java`**:

~~~java
public class BoundedInferenceDemo {
    static class NumberBox<T extends Number> {
        private T value;

        void put(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        var box = new NumberBox<>();
        NumberBox<Number> verified = box;
        verified.put(2.5);
        System.out.println("bound=" + box.get());
    }
}
~~~

Chạy:

~~~bash
javac --release 10 BoundedInferenceDemo.java
java BoundedInferenceDemo
~~~

Stdout:

~~~text
bound=2.5
~~~

`NumberBox<T>` yêu cầu `T extends Number`. Khi không có thông tin khác, diamond ở `new NumberBox<>()` có thể suy luận **`NumberBox<Number>`**, không phải `NumberBox<Object>`; phép gán `NumberBox<Number> verified = box;` trong chương trình xác nhận kiểu đó. Ví dụ nhấn mạnh rằng kết quả suy luận phụ thuộc **tập ràng buộc kiểu**, không chỉ phụ thuộc sự có mặt hay vắng mặt của `var`.

## 8. Quy trình xử lý trong mã thực tế

Khi gặp một dòng `var x = new SomeGenericClass<>();`, kiểm tra theo thứ tự:

1. **Kiểu phần tử/khóa/giá trị dự kiến là gì?** Chẳng hạn `String`, `Integer`, `Map<String, List<Integer>>`.
2. **Constructor có đối số mang thông tin generic không?** Nếu chỉ `<>` và constructor không đối số, thường thiếu căn cứ xác định kiểu mong muốn.
3. **Có kiểu đích tường minh không?** `var` không mang `List<String>` hay `Map<String, Integer>` vào vế phải; một khai báo kiểu tường minh thì có thể.
4. **Kiểu static thực tế có phù hợp với API sau đó không?** Nếu cần truyền vào `List<String>` hoặc lấy phần tử dưới dạng `String`, bảo đảm kiểu generic là `String` ngay ở dòng khai báo.
5. **Giải pháp có giữ đúng ngữ nghĩa collection không?** `List.of(...)` tạo danh sách không thể thay đổi; `new ArrayList<>(...)` tạo bản sao có thể thay đổi. Chọn theo mục đích, không chỉ để trình biên dịch suy luận được kiểu.

Trong phần lớn trường hợp, chọn một trong hai mẫu rõ nghĩa:

~~~java
List<String> names = new ArrayList<>();
// Hoặc:
var names = new ArrayList<String>();
~~~

Nếu dữ liệu đầu vào đã có kiểu rõ ràng thì `var names = new ArrayList<>(existingNames);` cũng hợp lý, miễn `existingNames` có kiểu phần tử mong muốn.

**Không dùng `getClass()` để kiểm tra đối số kiểu generic:** do *type erasure*, đối số như `String` hay `Object` thông thường không được giữ dưới dạng tham số hóa ở `Class` runtime. Muốn xác nhận suy luận kiểu, dùng kiểm tra biên dịch, chữ ký phương thức, khai báo nguồn và khả năng gán kiểu; không dựa vào lớp runtime của `ArrayList`.

## 9. Lỗi phổ biến và tự kiểm tra

| Tình huống | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `var names = new ArrayList<>();` rồi kỳ vọng `names` là `List<String>` | Thực tế suy luận `ArrayList<Object>` | Ghi `new ArrayList<String>()` hoặc khai báo `List<String>` ở vế trái |
| Thêm `names.add("An")` rồi nghĩ trình biên dịch sẽ đổi kiểu | Suy luận không diễn ra lại sau khai báo | Cung cấp kiểu đúng ngay từ initializer |
| `var map = new HashMap<>();` rồi kỳ vọng khóa `String`, giá trị `Integer` | Suy luận `HashMap<Object,Object>` | Ghi `new HashMap<String,Integer>()` hoặc `Map<String,Integer> map = new HashMap<>()` |
| Ép kiểu `(List<String>)` từ một danh sách sai generic | Nguy cơ lỗi lúc chạy và mất bảo đảm an toàn kiểu | Sửa khai báo gốc, kiểm tra kiểu dữ liệu thật |
| Dùng `List.of(...)` rồi gọi `add(...)` | `UnsupportedOperationException` vì danh sách không hỗ trợ thêm/xóa | Sao chép vào `new ArrayList<>(List.of(...))` nếu cần chỉnh sửa |
| Tin rằng mọi `new Type<>()` không có đối số luôn cho `Object` | Bỏ qua bound như `T extends Number` và ngữ cảnh kiểu đích | Xét đầy đủ bound, constructor arguments và target typing |

**Câu hỏi tự kiểm tra:**

1. Với `var result = new ArrayList<>();`, kiểu của `result` là gì, và vì sao thêm `result.add("Java")` không làm kiểu đó trở thành `ArrayList<String>`?
2. Vì sao `List<String> result = new ArrayList<>();` cho phép `result.get(0)` có kiểu `String`?
3. Nêu hai cách tạo một `ArrayList<String>` rỗng, có thể thêm phần tử, trong đó một cách vẫn dùng `var`.
4. Với `var result = new ArrayList<>(List.of(1, 2, 3));`, kiểu phần tử được suy luận từ đâu?
5. Vì sao `var box = new NumberBox<>();` trong ví dụ `T extends Number` không suy luận thành `NumberBox<Object>`?

**Đáp án:** (1) `ArrayList<Object>`, vì suy luận diễn ra tại khai báo và không dựa vào `add` sau đó; (2) kiểu đích truyền ràng buộc `String` cho diamond; (3) `List<String> result = new ArrayList<>();` và `var result = new ArrayList<String>();`; (4) từ `List<Integer>` mà `List.of(1, 2, 3)` cung cấp cho constructor; (5) `Object` không thỏa ràng buộc `T extends Number`, nên giới hạn `Number` quyết định trường hợp thiếu thông tin này.