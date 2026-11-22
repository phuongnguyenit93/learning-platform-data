# Phân biệt khai báo theo giao diện với kiểu cụ thể do `var` suy luận

## 1. Mục tiêu

Trong Java, cùng một đối tượng `ArrayList<String>` có thể được giữ trong biến khai báo theo giao diện `List<String>` hoặc trong biến có kiểu cụ thể `ArrayList<String>`. Java 10 bổ sung `var` để **suy luận kiểu biến cục bộ từ biểu thức khởi tạo**, nhưng `var` không tự chọn giao diện mà người lập trình muốn lập trình hướng đến.

Hai khai báo sau đều hợp lệ trên Java 17 trở lên, và đều tạo đối tượng `ArrayList`:

~~~java
// Hai dòng minh họa độc lập bên trong một phương thức:
List<String> byInterface = new ArrayList<>();
var byConcrete = new ArrayList<String>();
~~~

Tuy nhiên, **kiểu tĩnh của biến khác nhau**:

- `byInterface` có kiểu biên dịch `List<String>`. Nó có thể tham chiếu một đối tượng triển khai `List<String>` khác khi cần.
- `byConcrete` được trình biên dịch suy luận là `ArrayList<String>` từ `new ArrayList<String>()`; những thành viên public dành riêng cho `ArrayList` cũng có thể được gọi từ biến này.
- Kiểu thực tế ở thời điểm khởi tạo của cả hai đối tượng đều là `ArrayList`. `var` không thay đổi kiểu runtime của object, không làm Java trở thành ngôn ngữ kiểu động và không phát sinh cơ chế đặc biệt khi chạy.

Điểm quan trọng hơn khi dùng **generics** là phần suy luận của biểu thức `new ...<>` (*diamond*). Với kiểu khai báo tường minh, compiler có thông tin từ vế trái để suy luận tham số kiểu; nếu cả hai bên cùng yêu cầu suy luận, kết quả có thể rộng hơn dự kiến, ví dụ `ArrayList<Object>`.

Bài này giải thích cách lựa chọn khai báo trong code hiện đại. Các ví dụ áp dụng trên JDK 17+ và dựa vào những quy tắc Java vẫn đang được hỗ trợ.

## 2. Kiểu tĩnh, kiểu đối tượng và ý nghĩa “lập trình theo giao diện”

Xét hai cách khởi tạo:

~~~java
// Đoạn minh họa trong phương thức; cần import java.util.List và ArrayList.
List<String> a = new ArrayList<>();
var b = new ArrayList<String>();
~~~

| Câu hỏi | `List<String> a = new ArrayList<>();` | `var b = new ArrayList<String>();` |
| --- | --- | --- |
| Kiểu **tĩnh** của biến | `List<String>` | `ArrayList<String>` |
| Kiểu **runtime** của đối tượng vừa tạo | `ArrayList` | `ArrayList` |
| Có các thao tác `List` như `add`, `get`, `size`? | Có | Có |
| Có thể gọi `ArrayList.ensureCapacity(int)` trực tiếp? | Không; kiểu `List` không công bố phương thức đó | Có |
| Có thể gán tiếp một đối tượng `LinkedList<String>` cho cùng biến? | Có | Không, do `LinkedList` không phải subtype của `ArrayList` |
| Kiểu generic của phần tử | `String` | `String` |
| `var` có đổi kiểu biến ở lần gán sau? | Không áp dụng | Không: suy luận một lần tại chỗ khai báo |

**Kiểu tĩnh** quyết định những phương thức trình biên dịch cho phép gọi và những phép gán hợp lệ. **Kiểu runtime** quyết định implementation nào thực sự thực thi khi gọi phương thức đa hình. Sự khác biệt giữa hai khái niệm này tồn tại từ lâu trong Java, không phải do `var` tạo ra.

Ví dụ:

~~~java
// HỢP LỆ, minh họa trong thân phương thức.
List<String> names = new ArrayList<>();
names.add("Java");
names = new LinkedList<>();
names.add("Kotlin");
System.out.println(names); // [Kotlin]
~~~

Biến `names` có kiểu tĩnh `List<String>`, nên cả `ArrayList<String>` và `LinkedList<String>` đều có thể được gán cho nó. Đối tượng `ArrayList` ban đầu không tự biến thành `LinkedList`: câu gán chỉ làm biến tham chiếu sang một đối tượng khác.

~~~java
// HỢP LỆ lúc khai báo và gọi phương thức riêng.
var names = new ArrayList<String>();
names.ensureCapacity(10);

// KHÔNG HỢP LỆ nếu bỏ comment: LinkedList không phải ArrayList.
// names = new LinkedList<String>();
~~~

Ở đây `names` có kiểu tĩnh `ArrayList<String>`, nên Java sẽ từ chối phép gán đối tượng `LinkedList<String>` cho biến đó. `ensureCapacity` là một thao tác công khai của `ArrayList` và **không** thuộc hợp đồng `List`.

**Đừng kết luận rằng khai báo theo giao diện luôn tốt hơn hoặc `var` luôn tốt hơn.** Kiểu tĩnh phù hợp là kiểu giúp đoạn code vừa rõ ý định, vừa dùng đúng thao tác cần thiết. Khai báo theo giao diện có lợi khi muốn thao tác với hợp đồng `List`; kiểu cụ thể có thể hợp lý khi một đoạn code thực sự cần chức năng đặc thù của `ArrayList`.

## 3. Vì sao `var` không tự suy luận về `List`?

`var` không phải một toán tử tạo giao diện trừu tượng. Trình biên dịch suy ra kiểu từ **biểu thức khởi tạo ở vế phải** theo quy tắc ngôn ngữ.

~~~java
// Trong thân phương thức:
var first = new ArrayList<String>();  // ArrayList<String>
var second = new LinkedList<String>(); // LinkedList<String>
var third = List.of("Java");          // List<String>
~~~

Kiểu của `third` là `List<String>` bởi chữ ký của phương thức tĩnh `List.of(...)` **trả về `List<E>`**. Nó không trở thành lớp implementation nội bộ mà `List.of` có thể tạo ra trong runtime. Không nên phụ thuộc vào tên của các lớp implementation nội bộ này; chúng không phải hợp đồng sử dụng API.

Quy tắc tương tự áp dụng cho phương thức do bạn tự viết:

~~~java
// Đây là một phương thức minh họa thuộc một class.
static List<String> loadNames() {
    return new ArrayList<>(List.of("Java"));
}

// Trong phương thức gọi:
var names = loadNames(); // Kiểu tĩnh của names là List<String>.
~~~

Mặc dù `loadNames()` hiện trả về đối tượng `ArrayList` trong runtime, **kiểu khai báo trả về của phương thức là `List<String>`**. Biến `names` nhận kiểu tĩnh `List<String>`. Thay phần cài đặt `loadNames()` để trả về `LinkedList` không đổi kiểu tĩnh ở nơi gọi.

Vì vậy muốn giữ kiểu tĩnh `List<String>` trong biến cục bộ, hai cách rõ ràng là:

~~~java
// Hai khai báo riêng biệt, mỗi cách một biến.
List<String> namesA = new ArrayList<>();
var namesB = loadNames(); // loadNames() khai báo trả List<String>.
~~~

Có thể ép kiểu biểu thức sang `List<String>` rồi dùng `var`, nhưng việc ép kiểu không cần thiết chỉ để giấu tên giao diện thường khiến mã khó đọc hơn. Nếu **chủ đích thiết kế** là kiểu `List<String>`, khai báo tường minh theo giao diện thường diễn đạt điều đó tốt nhất.

## 4. `var` và generic diamond `<>`: điểm dễ gây lỗi nhất

Diamond `<>` cho phép suy luận tham số generic khi khởi tạo một lớp generic. Nhưng thông tin compiler có được sẽ khác nhau tùy ngữ cảnh.

### 4.1. Có kiểu đích ở vế trái

~~~java
// HỢP LỆ trong phương thức:
List<String> words = new ArrayList<>();
Map<String, Integer> scores = new HashMap<>();
~~~

Trình biên dịch dùng kiểu đích `List<String>` để suy luận diamond của `new ArrayList<>()` thành `ArrayList<String>`; và dùng kiểu đích `Map<String, Integer>` để suy luận `HashMap<String, Integer>`.

Biến `words` có kiểu tĩnh `List<String>`; biến `scores` có kiểu tĩnh `Map<String, Integer>`. Trường hợp này **không phải raw type**: generic vẫn được kiểm tra và các tham số kiểu đã được suy luận.

### 4.2. Cùng lúc bỏ kiểu vế trái và tham số kiểu của constructor

~~~java
// HỢP LỆ nhưng dễ ngoài dự tính:
var words = new ArrayList<>();
var scores = new HashMap<>();
~~~

Với hai biểu thức không có thêm thông tin kiểu trong ví dụ này, kết quả là:

- `words`: `ArrayList<Object>`;
- `scores`: `HashMap<Object, Object>`.

Ví dụ:

~~~java
// Đoạn này hợp lệ vì phần tử có kiểu Object.
var mixed = new ArrayList<>();
mixed.add("Java");
mixed.add(10);
System.out.println(mixed); // [Java, 10]
~~~

Nếu mong muốn danh sách chỉ nhận chuỗi, đoạn trên **không** thể tự hiểu mục đích đó. `var` suy luận kiểu dựa vào biểu thức khởi tạo, không phân tích các lần `add` xuất hiện về sau để “nâng cấp” kiểu biến.

### 4.3. Cách giữ thông tin generic khi vẫn dùng `var`

**Cách A — Ghi rõ tham số kiểu tại constructor:**

~~~java
var words = new ArrayList<String>();               // ArrayList<String>
var scores = new HashMap<String, Integer>();       // HashMap<String,Integer>
~~~

**Cách B — Khởi tạo bằng biểu thức đã đủ thông tin generic:**

~~~java
var words = new ArrayList<>(List.of("Java", "Kotlin"));
// Có đủ thông tin từ List.of(...): ArrayList<String>.

var scores = Map.of("Java", 10, "Kotlin", 20);
// Map<String,Integer> theo chữ ký phương thức và kiểu đối số.
~~~

**Cách C — Dùng kiểu giao diện rõ ràng:**

~~~java
List<String> words = new ArrayList<>();
Map<String, Integer> scores = new HashMap<>();
~~~

Cách B không có nghĩa mọi `new GenericClass<>(...)` đều suy luận như mong muốn. Kiểu của đối số, overload constructor và ngữ cảnh cụ thể vẫn quyết định kết quả; khi cần chắc chắn, cung cấp tham số generic ở chỗ khai báo.

### 4.4. Phân biệt `Object` với raw type

`ArrayList<Object>` là một **kiểu generic có tham số `Object`**, còn `ArrayList` đứng trần không có đối số kiểu là **raw type**. Raw type làm mất phần kiểm tra generic và có thể phát sinh cảnh báo unchecked. `var words = new ArrayList<>();` suy luận `ArrayList<Object>` trong ví dụ trên, **không** làm biến thành raw type.

~~~java
// Minh họa: cả hai được khai báo đúng generic.
var objects = new ArrayList<>();           // ArrayList<Object>
var strings = new ArrayList<String>();     // ArrayList<String>

// HỢP LỆ:
objects.add("Java");
objects.add(10);
strings.add("Java");

// KHÔNG HỢP LỆ nếu bỏ comment: phần tử không có kiểu String.
// strings.add(10);
~~~

Java generics còn **bất biến (invariant)**: `List<String>` không phải subtype của `List<Object>` dù `String` là subtype của `Object`. `var` không thay đổi quy tắc generic này.

## 5. Tác động tới cách viết API và khả năng thay implementation

Khi một tham số hoặc kiểu trả về không phụ thuộc vào tính năng riêng của `ArrayList`, sử dụng interface thường diễn đạt ý định tốt hơn:

~~~java
// Các phương thức minh họa nằm bên trong class.
public static void printNames(List<String> names) {
    names.forEach(System.out::println);
}

public static List<String> createNames() {
    return new ArrayList<>(List.of("Java", "Kotlin"));
}
~~~

Vì chữ ký `printNames(List<String>)` nhận interface, caller có thể truyền nhiều implementation `List<String>` phù hợp. Vì `createNames()` công bố kiểu `List<String>`, có thể đổi phần thân để tạo `LinkedList` mà vẫn giữ hợp đồng nguồn ở những nơi gọi không dựa vào chi tiết triển khai.

**`var` không được phép làm kiểu của field, tham số phương thức hoặc kiểu trả về phương thức.** Những nơi công bố API vẫn phải khai báo kiểu cụ thể, interface hoặc generic rõ ràng.

Đối với biến cục bộ bên trong phương thức, chọn cách diễn đạt ý định:

~~~java
// Khi chỉ cần thao tác chung của List và muốn biến thay được implementation:
List<String> items = new ArrayList<>();

// Khi thực sự dùng một chức năng công khai riêng của ArrayList:
var buffer = new ArrayList<String>();
buffer.ensureCapacity(100);

// Khi phương thức đã trả về kiểu interface đủ rõ:
var result = createNames(); // List<String>, theo chữ ký createNames().
~~~

Không nhất thiết đổi mọi biến cục bộ `var` thành `List`: ví dụ một đối tượng `ArrayList` được tạo, dùng vài lần rồi kết thúc trong một đoạn nhỏ thường không gây phụ thuộc kiến trúc đáng kể. Tuy nhiên, nếu phần code sau đó gọi `ensureCapacity` chỉ vì kiểu cụ thể được suy luận, hãy cân nhắc đó có phải hành vi thật sự cần thiết hay không.

### Phụ thuộc có thể hình thành ngoài ý định

~~~java
// Lúc đầu:
var names = new ArrayList<String>();
names.ensureCapacity(50);

// Sau khi refactor initializer:
var names = new LinkedList<String>();
// names.ensureCapacity(50); // Không biên dịch: LinkedList không có method này.
~~~

Nếu mã chỉ cần hành vi của `List`, khai báo `List<String> names` từ đầu sẽ làm ranh giới abstraction hiển thị rõ hơn với người đọc và giúp compiler ngăn gọi những API riêng của implementation.

Mặt khác, nếu yêu cầu hiệu năng thực sự cần `ArrayList.ensureCapacity`, dùng kiểu `ArrayList<String>` là chính đáng. Quyết định nên dựa trên hành vi cần sử dụng, không dựa đơn thuần vào độ ngắn của cú pháp.

## 6. `var` không làm thay đổi đối tượng runtime, tính bất biến hay hiệu năng tự thân

Đây là ba khái niệm khác nhau:

1. **Kiểu tĩnh của biến** (`List<String>`, `ArrayList<String>`) được xác định khi biên dịch.
2. **Lớp thực tế của đối tượng** vẫn là lớp mà biểu thức tạo ra hoặc phương thức trả về cung cấp.
3. **Khả năng sửa đổi dữ liệu** là hợp đồng/hành vi của đối tượng, không được suy ra chỉ từ `var` hay từ interface `List`.

Ví dụ `List.of(...)` và `List.copyOf(...)` tạo các danh sách **unmodifiable** theo hợp đồng API. Điều này độc lập với khai báo biến:

~~~java
// Các đoạn minh họa trong phương thức:
List<String> direct = List.of("Java");
var inferred = List.of("Java"); // Kiểu tĩnh cũng là List<String>.
~~~

Cả hai có thể gọi `get(0)` và đều có phương thức `add` trong interface `List` ở mức compile time, nhưng gọi `add` sẽ ném `UnsupportedOperationException` trong runtime vì danh sách không cho phép sửa.

~~~java
// Java 17+, đoạn minh họa:
var source = new ArrayList<>(List.of("Java"));
var copy = List.copyOf(source); // List<String> được suy luận.
source.add("Kotlin");
System.out.println(copy);      // [Java]
~~~

`copy` không thay đổi theo việc bổ sung phần tử vào `source`, đúng hợp đồng `List.copyOf`. Đây là API có từ Java 10 và vẫn được hỗ trợ.

**`final var`** chỉ ngăn gán lại biến; không làm collection trở nên unmodifiable:

~~~java
final var data = new ArrayList<String>();
data.add("Java"); // HỢP LỆ: thay đổi nội dung object.
 // data = new ArrayList<String>(); // KHÔNG HỢP LỆ nếu bỏ comment: gán lại final.
~~~

Tương tự, `List<String> data = new ArrayList<>();` và `var data = new ArrayList<String>();` không tự thêm chi phí runtime chỉ vì khác cách khai báo kiểu cục bộ. Thay đổi implementation, cấu trúc dữ liệu và thuật toán mới là nơi có thể ảnh hưởng hành vi/hiệu năng; tránh khẳng định hiệu năng tốt hơn chỉ vì sử dụng `var`.

## 7. Ví dụ Java 17+ đầy đủ: giao diện, kiểu cụ thể, factory và generics

Lưu tệp **`InterfaceVsVarDemo.java`**. Mã dùng các API công khai vẫn được hỗ trợ trên JDK hiện đại.

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class InterfaceVsVarDemo {

    static List<String> createNames() {
        return new ArrayList<>(List.of("Java", "Kotlin"));
    }

    public static void main(String[] args) {
        List<String> byInterface = new ArrayList<>(List.of("A"));
        var byConcrete = new ArrayList<String>(List.of("B"));

        System.out.println(byInterface.getClass().getSimpleName());
        System.out.println(byConcrete.getClass().getSimpleName());

        byInterface = new LinkedList<>(List.of("C"));
        System.out.println(byInterface);

        byConcrete.ensureCapacity(8);
        byConcrete.add("D");
        System.out.println(byConcrete);

        var byFactory = createNames();
        byFactory = new LinkedList<>(List.of("E"));
        System.out.println(byFactory);

        var inferredStrings = new ArrayList<>(List.of("F", "G"));
        inferredStrings.add("H");
        System.out.println(inferredStrings);

        var broad = new ArrayList<>();
        broad.add("I");
        broad.add(10);
        System.out.println(broad);

        var snapshot = List.copyOf(byConcrete);
        System.out.println(snapshot);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 InterfaceVsVarDemo.java
java InterfaceVsVarDemo
~~~

**Stdout chính xác:**

~~~text
ArrayList
ArrayList
[C]
[B, D]
[E]
[F, G, H]
[I, 10]
[B, D]
~~~

### Đọc kết quả theo thứ tự

1. Hai dòng `ArrayList` đầu tiên chứng minh cả hai biến ban đầu cùng trỏ tới đối tượng `ArrayList`. Tuy nhiên kiểu tĩnh của `byInterface` là `List<String>`, còn `byConcrete` là `ArrayList<String>`.
2. `byInterface = new LinkedList<>(...)` biên dịch vì `LinkedList<String>` triển khai `List<String>`. `println` in `[C]`.
3. `byConcrete.ensureCapacity(8)` biên dịch vì `ArrayList` công bố phương thức này; sau đó thêm `"D"` nên in `[B, D]`. `ensureCapacity` chỉ điều chỉnh khả năng chứa bên trong khi cần, **không** thêm phần tử.
4. `byFactory` nhận kiểu tĩnh `List<String>` từ chữ ký `createNames()`, dù trong phương thức factory đối tượng được tạo bằng `ArrayList`. Vì thế gán lại `LinkedList<>` hợp lệ và in `[E]`.
5. `new ArrayList<>(List.of("F", "G"))` có thông tin generic đủ để suy luận `ArrayList<String>`; thêm `"H"` hợp lệ, in `[F, G, H]`.
6. `new ArrayList<>()` không có thông tin phần tử, nên `broad` suy luận thành `ArrayList<Object>`; nó nhận cả chuỗi `"I"` và số `10`, in `[I, 10]`.
7. `List.copyOf(byConcrete)` trả về danh sách không thể sửa có các phần tử hiện tại của `byConcrete`; tại thời điểm sao chép là `[B, D]`.

Các đoạn lỗi được comment trong những mục trước **không** nằm trong chương trình hoàn chỉnh; file này có thể biên dịch bằng JDK 17+ hỗ trợ `--release 17`, không cần thư viện bên ngoài.

## 8. Cùng một biểu thức, khác điều người gọi được phép làm

Xét các câu lệnh sau, giả sử chúng được đặt trong một phương thức và có import tương ứng:

~~~java
List<String> interfaceList = new ArrayList<>();
var concreteList = new ArrayList<String>();

interfaceList.add("A"); // HỢP LỆ
concreteList.add("B");  // HỢP LỆ

// interfaceList.ensureCapacity(20); // Không biên dịch: List không khai báo.
// concreteList.ensureCapacity(20);  // HỢP LỆ: ArrayList khai báo.
~~~

Compiler kiểm tra lời gọi `ensureCapacity` dựa vào **kiểu tĩnh của biến nhận** chứ không “nhìn thấy” object runtime là `ArrayList` rồi cho gọi mọi phương thức của object.

Ngược lại:

~~~java
// Minh họa các phép gán:
List<String> interfaceList = new ArrayList<>();
interfaceList = new LinkedList<>(); // HỢP LỆ

var concreteList = new ArrayList<String>();
// concreteList = new LinkedList<String>(); // Không biên dịch.
~~~

Sau khi khai báo, `var` không liên tục suy luận lại kiểu theo phép gán. Từ đó compiler thực hiện những kiểm tra giống hệt như khi bạn ghi tường minh `ArrayList<String> concreteList`.

**Chọn kiểu trừu tượng là một chủ đích về thiết kế.** Java không thể suy ra chỉ từ `new ArrayList<String>()` rằng người viết thật sự chỉ muốn giao diện `List<String>`, bởi một số chương trình cần dùng chính những thành viên riêng của `ArrayList`.

## 9. Những tình huống hay nhầm trong mã generic

| Tình huống | Kết quả/thực chất | Cách làm phù hợp |
| --- | --- | --- |
| `List<String> x = new ArrayList<>();` | `x` là `List<String>`, diamond suy luận `String` từ kiểu đích. | Phù hợp khi muốn làm việc qua giao diện. |
| `var x = new ArrayList<String>();` | `x` là `ArrayList<String>`. | Dùng khi kiểu cụ thể rõ ràng/cần thiết. |
| `var x = new ArrayList<>();` | Trong trường hợp này `x` là `ArrayList<Object>`. | Thêm `String` ở constructor hoặc dùng `List<String>` bên trái. |
| `var x = new ArrayList<>(List.of("A"));` | `x` là `ArrayList<String>`. | Hợp lệ vì đối số cung cấp thông tin suy luận. |
| `var x = List.of("A");` | Kiểu tĩnh `List<String>`, runtime là một implementation của API `List.of`. | Không phụ thuộc tên implementation nội bộ. |
| `var x = createNames();` với `createNames()` trả `List<String>` | Kiểu tĩnh `List<String>`. | Kiểm tra chữ ký của factory khi đọc code. |
| `var x = new HashMap<>();` | Kiểu `HashMap<Object,Object>` trong trường hợp này. | Dùng `new HashMap<String,Integer>()` hoặc `Map<String,Integer>` ở vế trái. |
| `List<Object> x = new ArrayList<String>();` | Không biên dịch: generic bất biến. | Thiết kế tham số generic/wildcard theo nhu cầu, không cố ép kiểu. |
| `var x = null;` | Không biên dịch: thiếu kiểu để suy luận. | Khai báo tường minh kiểu phù hợp nếu giá trị ban đầu là `null`. |
| `var x = new ArrayList<String>(); x = new LinkedList<String>();` | Không biên dịch vì `x` đã là `ArrayList<String>`. | Khai báo `List<String> x` từ đầu nếu cần thay implementation. |

### Phân biệt generics với kiểu phần tử thực tế khi chạy

Do type erasure, ở runtime Java không lưu `ArrayList<String>` như một class riêng khác `ArrayList<Integer>`. `getClass()` của cả hai đối tượng đều cho class `ArrayList`. Khả năng chặn `strings.add(10)` đến từ **generic type checking tại thời điểm biên dịch**, không phải từ phép kiểm tra một class `ArrayList<String>` riêng ở runtime.

Vì vậy `getClass().getSimpleName()` chỉ dùng để minh họa class hiện thực, **không chứng minh** kiểu generic `String` hay `Object`. Hãy quan sát khai báo và kết quả kiểm tra biên dịch để xác định generic type.

## 10. Nguyên tắc chọn `List<T>`, `ArrayList<T>` hoặc `var`

### Khi nên ưu tiên khai báo theo giao diện

- Mã chỉ cần các thao tác được `List`, `Map`, `Set` hoặc interface thích hợp công bố.
- Bạn muốn thể hiện rõ khả năng chuyển giữa những implementation tương thích ở đoạn mã đó.
- Biến sống đủ lâu hoặc trải qua nhiều bước xử lý, nên kiểu trừu tượng rõ ràng giúp người đọc hiểu ranh giới phụ thuộc.
- Bạn đang khai báo tham số, kiểu trả về hoặc field; những vị trí này không dùng được `var`. Tùy hợp đồng, khai báo theo interface thường giảm việc lộ chi tiết implementation.

### Khi `var` giúp code rõ hơn

- Biểu thức khởi tạo đã cho thấy kiểu mà người đọc cần biết; ví dụ `var names = List.of("Java");` hoặc `var index = 0;`.
- Kiểu cụ thể là chủ đích và có thể xác định trực tiếp, chẳng hạn `var buffer = new ArrayList<String>();` kèm thao tác `buffer.ensureCapacity(...)`.
- Bạn đang dùng kết quả của một factory/method có kiểu trả về được công bố rõ, và không cần lặp lại một kiểu generic dài ở biến cục bộ.
- Vòng đời của biến ngắn và việc suy luận không làm mờ ý nghĩa dữ liệu; tên biến mô tả vai trò tốt.

### Khi nên tránh `var` hoặc bổ sung thông tin

- `var items = new ArrayList<>();` khi thực sự muốn phần tử `String`. Đây là trường hợp dễ suy luận thành `Object`.
- Initializer là một method call với kiểu trả về khó nhìn thấy, trong khi việc biết generic type quan trọng để hiểu code.
- Biểu thức tạo đối tượng concrete nhưng phần tiếp theo chỉ nên dựa vào interface; khai báo interface giúp nhắc người đọc và compiler rằng không cần các phương thức riêng của implementation.
- Việc refactor có khả năng đổi class được khởi tạo và các dòng dùng biến phụ thuộc vào phương thức concrete; cân nhắc kiểu interface để tránh sự phụ thuộc tình cờ.

Một quy tắc thực hành hữu ích là **không viết `var` chỉ vì có thể**. Hãy quyết định kiểu trừu tượng nào cần thể hiện và độ rõ ràng của initializer trước; sau đó chọn cách viết dễ đọc hơn.

## 11. Tự kiểm tra với năm bài tập ngắn

**Câu 1.** Với `var values = new ArrayList<String>();`, kiểu tĩnh của `values` là gì? Có thể gán `new LinkedList<String>()` sau đó không?

**Đáp án:** `ArrayList<String>`; không thể gán `LinkedList<String>` vì nó không kế thừa `ArrayList<String>`.

**Câu 2.** Với `List<String> values = new ArrayList<>();`, `values.ensureCapacity(5)` có biên dịch không?

**Đáp án:** Không; interface `List` không khai báo `ensureCapacity`. Dù object hiện tại là `ArrayList`, lời gọi được kiểm tra theo kiểu tĩnh `List<String>`.

**Câu 3.** Với `var values = List.of("A", "B");`, biến có kiểu tĩnh `ArrayList<String>` hay `List<String>`?

**Đáp án:** `List<String>`; chữ ký `List.of` trả về `List<E>`. Kiểu implementation runtime không phải loại cần xác định để sử dụng API này.

**Câu 4.** Với `var values = new ArrayList<>();`, vì sao `values.add(5)` và `values.add("A")` cùng biên dịch?

**Đáp án:** Vì không có thông tin generic khác, compiler suy luận `ArrayList<Object>`; số `5` được boxing thành `Integer`, và cả `Integer` lẫn `String` là subtype của `Object`. Muốn `String`, cung cấp tham số generic hoặc kiểu đích rõ ràng.

**Câu 5.** Nếu `static List<String> fetch() { return new ArrayList<>(); }`, biến trong `var result = fetch();` có kiểu tĩnh nào?

**Đáp án:** `List<String>`. Biến nhận kiểu trả về được công bố của `fetch()`. Nó không suy luận ngược vào phần cài đặt để chọn `ArrayList<String>`.

## 12. Tài liệu chính thức còn áp dụng

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): định nghĩa `var` với biến cục bộ, suy luận từ initializer và phạm vi áp dụng từ Java 10.
- [OpenJDK — Local Variable Type Inference Style Guidelines](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-style-guide.md): đặc biệt hướng dẫn G5 về “programming to the interface” cho biến cục bộ; cân nhắc tính dễ đọc và phụ thuộc vào implementation.
- [OpenJDK — Local Variable Type Inference FAQ](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md): giải thích `var` là suy luận kiểu tĩnh, không phải kiểu động; cảnh báo về diamond khi cả hai bên đều thiếu thông tin generic.
- [Oracle Java 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): cú pháp và ví dụ Java 10+ còn áp dụng.
- [Oracle Java SE 17 API — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html): đối chiếu phương thức được công bố trên interface và implementation.
- [Oracle Java SE 17 API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): phương thức từ Java 10 trả danh sách không thể sửa; không phụ thuộc cách khai báo `var` hay `List`.

**Điều cần nhớ:** `List<String> x = new ArrayList<>()` có kiểu tĩnh do **người viết lựa chọn ở vế trái**; `var x = new ArrayList<String>()` có kiểu tĩnh **suy luận từ biểu thức vế phải** là `ArrayList<String>`. Suy luận tự động không thay cho quyết định thiết kế API hoặc chọn abstraction. Khi dùng generic diamond, hãy kiểm tra thông tin kiểu đã đủ để compiler không suy luận thành `Object` ngoài ý định.