# Giới hạn suy luận kiểu từ các phép gán xuất hiện về sau

## 1. Quy tắc cốt lõi

Trong Java 10 trở lên, `var` cho phép bỏ tên kiểu ở **khai báo biến cục bộ có biểu thức khởi tạo**. Compiler suy luận kiểu tại thời điểm phân tích khai báo, **chỉ dựa trên kiểu của biểu thức khởi tạo và ngữ cảnh hợp lệ của chính khai báo đó**. Những phép gán, lời gọi phương thức hoặc nhánh điều kiện viết **sau khai báo** không được dùng để suy luận lại kiểu của biến.

~~~java
// Đoạn minh họa bên trong phương thức.
var amount = 10;     // Kiểu tĩnh: int
amount = 20;         // Hợp lệ: vẫn là int.
// amount = "twenty"; // KHÔNG hợp lệ: String không chuyển thành int.
~~~

Với `var`, hai dòng đầu tương đương về kiểu tĩnh với:

~~~java
int amount = 10;
amount = 20;
~~~

Điều này có ba hệ quả thực tiễn:

1. **Suy luận diễn ra một lần:** thay đổi giá trị không làm thay đổi kiểu biến. Java vẫn là ngôn ngữ có kiểu tĩnh.
2. **Gán lại vẫn được phép:** nếu biến không `final`, phép gán mới hợp lệ khi biểu thức bên phải có thể chuyển đổi theo quy tắc gán của Java sang **kiểu đã được xác định**.
3. **Không có suy luận từ tương lai:** compiler không xem toàn bộ phần còn lại của phương thức để chọn một kiểu chung theo các phép gán sẽ xuất hiện.

Phân biệt rõ **kiểu biến** với **giá trị biến**: một biến `String` có thể lần lượt chứa `"Java"` rồi `"JDK"`; đó là hai giá trị khác nhau cùng kiểu, hoàn toàn không phải đổi kiểu.

Quy tắc này được nêu trực tiếp trong [OpenJDK JEP 286](https://openjdk.org/jeps/286) và [FAQ về suy luận kiểu biến cục bộ](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md). Nó vẫn áp dụng trong Java hiện đại; bài không dựa vào API đã bị loại bỏ hay cách dùng legacy.

## 2. Vì sao `var` bắt buộc phải có initializer?

Compiler không cho phép trì hoãn quyết định kiểu biến cho đến lần gán đầu tiên trong tương lai:

~~~java
// KHÔNG biên dịch: đoạn lỗi minh họa, không đặt vào ví dụ chạy.
var message;
message = "Hello";
~~~

Lý do: `var` chỉ có nghĩa khi compiler đã thấy biểu thức khởi tạo ngay trong khai báo. Không có initializer thì compiler không có nguồn thông tin hợp lệ để chọn kiểu cho biến.

Cách viết đúng, nếu giá trị đã có:

~~~java
var message = "Hello"; // Kiểu String.
message = "Java";       // Hợp lệ, vẫn là String.
~~~

Cách viết đúng, nếu giá trị chỉ được tính trong nhánh điều kiện sau đó:

~~~java
// Đoạn hợp lệ trong phương thức có sẵn biến boolean useShortName.
String message;
if (useShortName) {
    message = "JDK";
} else {
    message = "Java Development Kit";
}
System.out.println(message);
~~~

Ở đây `String message;` là **khai báo có kiểu tường minh**. Java vẫn kiểm tra *definite assignment*: trước khi đọc `message`, mọi đường đi đến lệnh đọc phải bảo đảm biến đã được gán một giá trị. Điều này khác hoàn toàn với việc compiler suy luận kiểu qua các nhánh.

Một biến `var` cũng không được khởi tạo bằng literal `null` không có kiểu:

~~~java
// KHÔNG hợp lệ: không thể suy luận kiểu từ null literal đứng riêng.
var result = null;

// HỢP LỆ: phải thể hiện kiểu ngay từ initializer.
String result2 = null;
var result3 = (String) null; // Kiểu String do cast cung cấp.
~~~

Trong code nghiệp vụ, `String result = null` thường dễ đọc hơn cast chỉ để dùng `var`; cần cân nhắc thiết kế trạng thái null rõ ràng.

## 3. Những phép gán sau khai báo được kiểm tra theo kiểu đã suy luận

### 3.1. Biến kiểu nguyên thủy

~~~java
// Minh họa hợp lệ và lỗi ở bên trong phương thức.
var count = 1;     // int
count = 2;         // Hợp lệ.
count = (int) 3L;  // Hợp lệ: cast chuyển long thành int.
// count = 3L;     // Không hợp lệ: long sang int là narrowing conversion.
// count = 3.5;    // Không hợp lệ: double sang int.
~~~

Phép cast có thể làm mất dữ liệu; ví dụ trên chỉ cho thấy quy tắc kiểu. Nó không làm `count` trở thành `long`. Nếu cần số thực, hãy chọn kiểu phù hợp **ngay ở initializer**:

~~~java
var rate = 1.0;  // double
rate = 2.5;      // Hợp lệ.
~~~

Đừng nhầm `+=` với phép gán `=`: phép toán gán kết hợp có quy tắc chuyển kiểu riêng, có thể bao gồm chuyển hẹp. Muốn đánh giá kiểu của biến, hãy xem kiểu được suy luận ở khai báo; đừng suy đoán kiểu từ việc một biểu thức `+=` biên dịch được.

### 3.2. Biến tham chiếu

~~~java
var title = "Java"; // String
title = "JDK";      // Hợp lệ.
// title = 17;      // Không hợp lệ: Integer/int không gán được cho String.
title = null;       // Hợp lệ với biến tham chiếu String.
~~~

`title = null` không làm mất thông tin kiểu. Sau phép gán, compiler vẫn coi `title` có kiểu tĩnh `String`; nếu gọi phương thức trên tham chiếu null khi chạy thì có thể ném `NullPointerException`.

Nếu chủ ý cho một biến nhận nhiều kiểu đối tượng, hãy công bố kiểu cha/giao diện thích hợp ngay từ đầu:

~~~java
Number value = Integer.valueOf(1);
value = Double.valueOf(2.5); // Hợp lệ: cả Integer và Double đều là Number.

var value2 = (Number) Integer.valueOf(1);
value2 = Double.valueOf(2.5); // Hợp lệ: initializer đã có kiểu Number.
~~~

Trái lại:

~~~java
var value = Integer.valueOf(1); // Integer
// value = Double.valueOf(2.5); // Không hợp lệ.
~~~

Compiler không nâng kiểu `Integer` thành `Number` chỉ vì một phép gán xuất hiện sau đó. Nếu cần khả năng gán nhiều subtype, chọn kiểu chung phù hợp từ lúc khai báo.

## 4. Polymorphism: cùng một interface, nhiều implementation

Tình huống thực tế rất thường gặp khi làm việc với collections:

~~~java
// Đoạn minh họa trong phương thức, với java.util.ArrayList và LinkedList.
var names = new ArrayList<String>();  // Kiểu tĩnh: ArrayList<String>.
names.add("Java");
// names = new LinkedList<String>(); // KHÔNG hợp lệ.
~~~

`LinkedList<String>` và `ArrayList<String>` đều triển khai `List<String>`, nhưng `LinkedList` không là subtype của `ArrayList`. Compiler không suy luận ngược rằng biến `names` nên có kiểu `List<String>` để dung hòa hai phép gán.

Nếu **chủ đích là thay implementation**, khai báo kiểu giao diện:

~~~java
// HỢP LỆ khi import List, ArrayList, LinkedList.
List<String> names = new ArrayList<>();
names = new LinkedList<>();
names.add("Java");
~~~

Hoặc dùng factory có **kiểu trả về đã được công bố là giao diện**:

~~~java
// Phương thức thuộc một class; đây là đoạn minh họa.
static List<String> createNames() {
    return new ArrayList<>(List.of("Java"));
}

// Bên trong phương thức gọi:
var names = createNames();            // Kiểu List<String>.
names = new LinkedList<String>();     // Hợp lệ.
~~~

Lý do cách thứ hai hợp lệ là `createNames()` có kiểu trả về `List<String>`. Kiểu của `names` suy luận **từ chữ ký phương thức tại initializer**, không phải từ phép gán `new LinkedList<>()` ở dòng sau.

Điều này giúp phân biệt:

| Khai báo ban đầu | Kiểu tĩnh của biến | Có thể gán `new LinkedList<String>()` sau đó? |
| --- | --- | --- |
| `var x = new ArrayList<String>();` | `ArrayList<String>` | Không |
| `ArrayList<String> x = new ArrayList<>();` | `ArrayList<String>` | Không |
| `List<String> x = new ArrayList<>();` | `List<String>` | Có |
| `var x = createNames();` với phương thức trả `List<String>` | `List<String>` | Có |
| `var x = List.of("Java");` | `List<String>` | Có, nếu biến không final |

**Lưu ý:** `List.of(...)` trả một danh sách *unmodifiable*; điều đó không làm biến tham chiếu trở thành `final`. Phép `x = new LinkedList<>()` có thể hợp lệ dù `x.add(...)` trên danh sách `List.of` ban đầu sẽ ném `UnsupportedOperationException`. Khả năng sửa đối tượng và khả năng gán lại biến là hai thuộc tính khác nhau.

## 5. Generics: lời gọi `add` sau đó không quyết định kiểu phần tử

Suy luận `var` không đọc những lệnh thêm phần tử bên dưới để đoán người viết muốn dùng `String`, `Integer` hay một kiểu chung.

~~~java
// HỢP LỆ; phần tử không bị ràng buộc là String.
var items = new ArrayList<>(); // Kiểu: ArrayList<Object>.
items.add("Java");
items.add(10);
~~~

Tại thời điểm khai báo, `new ArrayList<>()` không có kiểu đích tường minh cho tham số generic. Trong trường hợp này compiler suy luận `ArrayList<Object>`. Các lần gọi `items.add(...)` về sau **không chuyển** kiểu đó thành `ArrayList<String>` hay loại giao diện chung mới.

Vì vậy:

~~~java
var items = new ArrayList<>();
items.add("Java");
Object first = items.get(0);  // Hợp lệ, kiểu trả về là Object.
// String text = items.get(0); // Không biên dịch: Object không tự đổi thành String.
// items.get(0).length();      // Không biên dịch: Object không có length().
~~~

Một điểm dễ nhầm: `ArrayList<Object>` **không** phải raw type. Đây là kiểu generic với tham số kiểu cụ thể `Object`, vẫn được compiler kiểm tra. Nó khác với khai báo cũ `ArrayList items = new ArrayList();` không khai báo tham số generic.

### Muốn ràng buộc là `String` thì cung cấp thông tin từ initializer

~~~java
var items = new ArrayList<String>(); // ArrayList<String>
items.add("Java");
// items.add(10);                    // Không biên dịch.

List<String> names = new ArrayList<>(); // Kiểu biến List<String>.
names.add("Java");
// names.add(10);                      // Không biên dịch.
~~~

Hoặc sử dụng biểu thức khởi tạo đã có thông tin generic:

~~~java
var items = new ArrayList<>(List.of("Java", "Kotlin"));
// Kiểu của items: ArrayList<String>.
items.add("JDK"); // Hợp lệ.
~~~

Lưu ý `new ArrayList<>(List.of(...))` được suy luận nhờ kiểu của đối số **ngay trong biểu thức khởi tạo**. Đây là suy luận hợp lệ tại chỗ, không phải dựa vào các phép gán/add về sau.

### Hai ví dụ đặc biệt dễ lẫn

~~~java
var empty = List.of(); // List<Object> trong trường hợp này.
empty = List.of("A");  // Có thể biên dịch: vế phải được kiểm tra theo kiểu đích List<Object>.
Object value = empty.get(0);
// String s = empty.get(0); // Không biên dịch: kiểu phần tử của empty vẫn là Object.
~~~

Dòng gán `empty = List.of("A")` không chứng tỏ `empty` được đổi thành `List<String>`. Java có thể dùng **kiểu đích đã xác định** `List<Object>` để phân giải lời gọi generic `List.of(...)` ở vế phải, nhưng việc đó chỉ ảnh hưởng phép gán ấy, không thay đổi kiểu của `empty`.

Với lời gọi factory generic khác, loại diễn giải cụ thể có thể thay đổi theo chữ ký và ngữ cảnh; nguyên tắc vững chắc là: **kiểu biến đã suy luận không bị viết lại bởi các phép gán về sau**.

## 6. Điều kiện và nhánh code: xác định kiểu ngay ở điểm khai báo

Giả sử một chương trình chọn cấu trúc dữ liệu theo cấu hình:

~~~java
// KHÔNG hợp lệ: không được khai báo var rồi gán trong từng nhánh.
var cache;
if (useLinkedList) {
    cache = new LinkedList<String>();
} else {
    cache = new ArrayList<String>();
}
~~~

Cách sửa rõ ràng là:

~~~java
// HỢP LỆ trong một phương thức đã có boolean useLinkedList.
List<String> cache;
if (useLinkedList) {
    cache = new LinkedList<>();
} else {
    cache = new ArrayList<>();
}
cache.add("Java");
~~~

Hoặc chọn giá trị bằng biểu thức điều kiện, với **kiểu đích tường minh**:

~~~java
List<String> cache = useLinkedList
        ? new LinkedList<>()
        : new ArrayList<>();
cache.add("Java");
~~~

Trong trường hợp thứ hai, cả hai nhánh được kiểm tra trong ngữ cảnh `List<String>`. Nếu thay `List<String>` bằng `var`, compiler phải xác định kiểu cho cả biểu thức điều kiện; kết quả có thể là kiểu chung phức tạp do các quy tắc ngôn ngữ, không có cam kết rằng đó là đúng giao diện bạn dự định dùng.

Với `switch` expression hiện đại, bạn cũng có thể chọn kiểu đích rõ ràng:

~~~java
// Minh họa trong method với boolean preferLinkedList.
List<String> cache = switch (preferLinkedList ? "linked" : "array") {
    case "linked" -> new LinkedList<>();
    default -> new ArrayList<>();
};
~~~

Tất cả nhánh của biểu thức `switch` được kiểm tra theo quy tắc type compatibility/target typing thích hợp. Điều cần nhớ vẫn là: compiler suy luận **từ biểu thức khởi tạo và ngữ cảnh ngay tại đó**, không từ các câu lệnh sửa giá trị về sau.

## 7. Không nhầm suy luận từ initializer với suy luận trong lời gọi phương thức

Java có nhiều cơ chế suy luận kiểu. Suy luận tham số generic của một lời gọi phương thức có thể dựa vào kiểu của các đối số và, khi biểu thức là *poly expression*, cả **ngữ cảnh kiểu đích** ở nơi gọi. Nhưng đây không phải cơ chế quay lại cập nhật kiểu đã cố định của một biến `var`.

Ví dụ:

~~~java
// Khai báo phương thức bên trong class.
static <T> List<T> singleton(T value) {
    return List.of(value);
}

// Trong phương thức gọi:
var words = singleton("Java"); // List<String>.
words = List.of("JDK");         // Hợp lệ, vẫn là List<String>.
~~~

Kiểu `List<String>` được xác định từ **lời gọi `singleton("Java")` tại initializer**. `words = List.of("JDK")` sau đó chỉ được kiểm tra khả năng gán vào `List<String>`.

Nếu muốn sử dụng lại biến cho danh sách số nguyên:

~~~java
var words = singleton("Java"); // List<String>.
// words = singleton(42);      // Không hợp lệ: kết quả không là List<String>.
~~~

`var` không biến một danh sách `List<String>` thành một “biến danh sách tổng quát” mỗi lần gán.

### Lambda và method reference không tự cung cấp kiểu đích cho `var`

Một lambda hoặc tham chiếu phương thức đứng riêng cần một functional interface đích:

~~~java
// KHÔNG hợp lệ: lambda thiếu functional interface đích.
var predicate = text -> text.isBlank();

// HỢP LỆ: kiểu đích được khai báo tường minh.
java.util.function.Predicate<String> predicate =
        text -> text.isBlank();
~~~

Bạn không thể khắc phục khai báo `var predicate = ...` ở trên bằng cách dự định gán một `Predicate` khác vào `predicate` ở dòng sau. Kiểu đích cần có **ngay tại biểu thức khởi tạo**. Từ Java 11, `var` có thể xuất hiện trong tham số lambda dưới dạng `(var text) -> ...` nếu đã có functional interface đích; điều đó không thay đổi nguyên tắc này.

## 8. Chương trình Java 17+ hoàn chỉnh

Chương trình sau minh họa các phép gán hợp lệ, sự giới hạn kiểu cụ thể của `var`, generic diamond và cách chọn kiểu giao diện khi dự kiến thay implementation.

Lưu đúng tên file **`LaterAssignmentInferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class LaterAssignmentInferenceDemo {

    static List<String> initialNames() {
        return new ArrayList<>(List.of("Java", "Kotlin"));
    }

    public static void main(String[] args) {
        var number = 10;
        number = 20;
        System.out.println("number=" + number);

        var message = "A";
        message = "B";
        System.out.println("message=" + message);

        var concrete = new ArrayList<String>();
        concrete.add("Java");
        System.out.println("concrete=" + concrete);

        List<String> flexible = new ArrayList<>();
        flexible = new LinkedList<>(List.of("Kotlin"));
        System.out.println("flexible=" + flexible);

        var fromMethod = initialNames();
        fromMethod = new LinkedList<>(List.of("JDK"));
        System.out.println("fromMethod=" + fromMethod);

        var broad = new ArrayList<>();
        broad.add("A");
        broad.add(7);
        System.out.println("broad=" + broad);

        Object first = broad.get(0);
        System.out.println("first=" + first);

        var typed = new ArrayList<String>();
        typed.add("A");
        String typedFirst = typed.get(0);
        System.out.println("typedFirst=" + typedFirst);

        var chosen = true ? List.of("Java") : List.of("Kotlin");
        chosen = List.of("JDK");
        System.out.println("chosen=" + chosen);

        List<String> branchNames;
        boolean useLinkedList = true;
        if (useLinkedList) {
            branchNames = new LinkedList<>(List.of("L"));
        } else {
            branchNames = new ArrayList<>(List.of("A"));
        }
        System.out.println("branchNames=" + branchNames);
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn có hỗ trợ `--release 17`:

~~~bash
javac --release 17 LaterAssignmentInferenceDemo.java
java LaterAssignmentInferenceDemo
~~~

**Stdout chính xác:**

~~~text
number=20
message=B
concrete=[Java]
flexible=[Kotlin]
fromMethod=[JDK]
broad=[A, 7]
first=A
typedFirst=A
chosen=[JDK]
branchNames=[L]
~~~

### Vì sao chương trình cho kết quả đó?

- `number` được suy luận `int` từ `10`; gán `20` hợp lệ. `message` được suy luận `String` từ `"A"`; gán `"B"` hợp lệ.
- `concrete` được suy luận `ArrayList<String>` từ constructor. Chương trình chỉ thay đổi **nội dung** bằng `add("Java")`; không có gán sang implementation khác.
- `flexible` được khai báo `List<String>`; gán sang `LinkedList<>(List.of("Kotlin"))` hợp lệ, nên chỉ in danh sách mới `[Kotlin]`.
- `fromMethod` được suy luận `List<String>` từ **kiểu trả về đã công bố** của `initialNames()`. Vì vậy, một `LinkedList<String>` khác được gán vào biến này hợp lệ.
- `broad` được suy luận `ArrayList<Object>`, có thể thêm `"A"` và `Integer` được boxing từ `7`. `broad.get(0)` có kiểu **Object ở compile time**, dù giá trị runtime đầu tiên thực tế là một chuỗi; `println` hiển thị `A`.
- `typed` được suy luận `ArrayList<String>` do tham số generic tường minh; `typed.get(0)` có thể gán vào `String typedFirst` mà không cần cast.
- `chosen` có kiểu `List<String>` từ biểu thức điều kiện có hai nhánh trả `List<String>`. Gán tiếp `List.of("JDK")` hợp lệ vì cùng kiểu.
- `branchNames` được khai báo `List<String>`. Hai nhánh gán những implementation phù hợp và biến đã được gán trước khi gọi `println`. Vì `useLinkedList` là `true`, kết quả cuối là `[L]`.

### Thử lỗi biên dịch có chủ đích

Bốn đoạn tiếp theo **chỉ để đọc và thử riêng**, không chèn vào file đang chạy nếu muốn giữ output ở trên:

~~~java
// Lỗi 1: không thể khai báo var thiếu initializer.
var later;
later = 10;

// Lỗi 2: kiểu đã là int, phép gán String không hợp lệ.
var size = 1;
size = "large";

// Lỗi 3: kiểu đã là ArrayList<String>, không gán được LinkedList<String>.
var data = new ArrayList<String>();
data = new LinkedList<String>();

// Lỗi 4: get() trả Object khi var suy luận ArrayList<Object>.
var objects = new ArrayList<>();
objects.add("Java");
String text = objects.get(0);
~~~

Thông báo lỗi cụ thể có thể khác theo phiên bản compiler, nhưng bản chất là thiếu initializer hoặc vi phạm quy tắc gán đối với kiểu tĩnh đã xác định. Một phép gán xuất hiện về sau không khiến compiler chọn lại kiểu biến ban đầu.

## 9. Biến đổi trạng thái object không đồng nghĩa đổi kiểu biến

Đây là phân biệt quan trọng khi học các API collection và mutable object:

~~~java
// Đoạn hợp lệ trong phương thức.
var builder = new StringBuilder();
builder.append("Java");
builder.append(" 10");
String text = builder.toString(); // "Java 10"
~~~

`builder` luôn có kiểu tĩnh `StringBuilder`. `append(...)` thay đổi **trạng thái của object** mà biến đang tham chiếu; compiler không suy luận lại kiểu biến khi nội dung thay đổi.

Tương tự:

~~~java
var values = new ArrayList<String>();
values.add("A");
values.add("B");
values.remove("A");
System.out.println(values); // [B]
~~~

Mọi lệnh `add`, `remove` đều là thao tác trên đối tượng. Kiểu `ArrayList<String>` không đổi. Cả khi một phép gán hợp lệ thay thế object:

~~~java
var values = new ArrayList<String>();
values = new ArrayList<>(List.of("C"));
System.out.println(values); // [C]
~~~

Kiểu biến vẫn là `ArrayList<String>`; chỉ đối tượng tham chiếu thay đổi.

Với `final var`, Java cấm **gán lại biến**, nhưng vẫn cho thao tác thay đổi trạng thái nếu đối tượng hỗ trợ:

~~~java
final var values = new ArrayList<String>();
values.add("A"); // Hợp lệ.
// values = new ArrayList<String>(); // Không hợp lệ: biến final.
~~~

`final` và tính bất biến của collection là hai khái niệm khác nhau. Danh sách từ `List.of(...)` không thể sửa nội dung theo hợp đồng, dù biến nhận nó có thể được khai báo không `final`.

## 10. Một ngoại lệ dễ hiểu nhầm: kiểm tra kiểu theo luồng không đổi kiểu `var`

Java 17 hỗ trợ *pattern matching for instanceof* như sau:

~~~java
// Đoạn hợp lệ bên trong phương thức, Java 17+.
var item = (Object) "Java"; // Kiểu tĩnh của item: Object.
if (item instanceof String text) {
    System.out.println(text.length()); // 4
}
// item.length(); // Không hợp lệ: item vẫn là Object.
~~~

Bên trong nhánh `if`, compiler biết biến pattern `text` có kiểu `String` nên cho gọi `length()`. Điều đó **không thay đổi kiểu tĩnh của `item`**. Tương tự, compiler không dùng những phép gán ở các nhánh sau để biến `item` thành kiểu `String` mới.

Điểm này cũng giúp phân biệt `var` với việc phân tích luồng điều khiển: compiler có thể kiểm tra biến đã được gán, thu hẹp cách dùng theo một pattern ở phạm vi nhất định hoặc xác định branch reachability; nhưng suy luận kiểu biến cục bộ `var` đã kết thúc tại khai báo.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Vì sao xảy ra? | Cách khắc phục |
| --- | --- | --- |
| `var x; x = 1;` không biên dịch | Không có initializer ở khai báo `var`. | Viết `var x = 1;` hoặc `int x; x = 1;` nếu cần gán về sau. |
| `var x = 1; x = "one";` không biên dịch | Kiểu của `x` là `int`, không suy luận lại. | Chọn kiểu đúng với mục đích hoặc tách biến theo vai trò; không phụ thuộc vào đổi kiểu động. |
| `var names = new ArrayList<String>(); names = new LinkedList<String>();` không biên dịch | `names` đã có kiểu tĩnh `ArrayList<String>`. | Viết `List<String> names = new ArrayList<>();` từ đầu. |
| `var items = new ArrayList<>();` rồi `items.add("A")` vẫn cho `get(0)` kiểu `Object` | Diamond suy luận `Object` khi chưa có thông tin generic ở initializer; `add` không thay đổi kiểu phần tử. | Viết `var items = new ArrayList<String>();` hoặc `List<String> items = new ArrayList<>();`. |
| `var x = null;` không biên dịch | Null literal không cung cấp kiểu để suy luận. | Khai báo kiểu tường minh phù hợp hoặc dùng initializer có kiểu. |
| Tưởng `var result = factory();` có kiểu của implementation runtime | Compiler dựa vào kiểu trả về **công bố của `factory`**, không đi vào runtime. | Xem chữ ký `factory()`. |
| Thấy gán `List.of("A")` vào một biến `List<Object>` nên nghĩ biến biến thành `List<String>` | Ngữ cảnh phép gán có thể điều khiển generic inference của RHS; kiểu LHS vẫn là `List<Object>`. | Kiểm tra kiểu biến ban đầu và kiểu của `get(...)`. |
| Tưởng một lệnh `add`, `append` hoặc `remove` làm đổi kiểu biến | Đây là các lời gọi thay đổi trạng thái object. | Phân biệt thay object, sửa trạng thái object và đổi kiểu; Java không đổi kiểu biến. |
| Tưởng `instanceof String s` nâng kiểu của biến `Object` thành `String` | Pattern giới thiệu biến mới `s` có kiểu `String` trong phạm vi hợp lệ. | Dùng biến pattern `s`; biến gốc vẫn có kiểu đã khai báo. |

Những lỗi này đều được phát hiện hoặc lý giải bằng các quy tắc kiểu hiện hành. Không nên tìm các cờ compiler hay API nội bộ để “cho phép `var` tự đổi kiểu”: đó là hành vi không thuộc ngôn ngữ Java.

## 12. Checklist thiết kế code thực tế

1. **Xác định mục đích biến trước khai báo.** Biến sẽ chỉ giữ các giá trị cùng kiểu cụ thể hay cần nhiều implementation của một interface? Nếu cần nhiều subtype, công bố interface/kiểu cha phù hợp ngay từ đầu.
2. **Nhìn vào initializer.** Với `var`, kiểm tra kiểu của RHS, chữ ký phương thức trả về và tham số generic có đủ rõ hay không.
3. **Đặc biệt rà diamond.** `var list = new ArrayList<>()` dễ thành `ArrayList<Object>`. Dùng `new ArrayList<String>()`, cung cấp đối số có kiểu, hoặc ghi `List<String>` bên trái.
4. **Phân biệt gán với sửa nội dung.** `list = otherList` thay tham chiếu; `list.add(item)` sửa object; không thao tác nào tạo cơ chế suy luận lại kiểu của biến.
5. **Khi cần giá trị từ nhiều nhánh**, dùng một khai báo có kiểu tường minh và bảo đảm definite assignment, hoặc dùng biểu thức điều kiện/switch với kiểu đích phù hợp.
6. **Giữ API dễ hiểu.** `var` là cú pháp cho biến cục bộ có initializer, không được dùng làm kiểu field, tham số hay kiểu trả về phương thức. Đừng giấu abstraction chỉ để giảm số ký tự trong code.
7. **Biên dịch bằng target phù hợp**, ví dụ `javac --release 17` khi dự án phải chạy trên Java 17, và kiểm thử ứng dụng với runtime thực tế. Đừng dùng thông điệp gợi ý của IDE thay cho quy tắc ngôn ngữ.

### Tự kiểm tra

**Câu 1.** `var count = 0; count = 1L;` có hợp lệ không?

Không. `count` có kiểu `int` từ `0`; gán biến `long` vào `int` bằng phép gán thường là không hợp lệ nếu không có chuyển kiểu thích hợp. Compiler không suy luận lại thành `long`.

**Câu 2.** `var name = "Java"; name = "Kotlin";` có hợp lệ không?

Có. Hai giá trị cùng kiểu `String`; biến được phép gán lại vì không `final`.

**Câu 3.** `var names = new ArrayList<String>(); names = new LinkedList<String>();` có hợp lệ không?

Không. `names` là `ArrayList<String>`. Muốn dùng cả hai implementation, hãy khai báo `List<String> names` lúc đầu.

**Câu 4.** `var names = new ArrayList<>(); names.add("Java");` có khiến `names` trở thành `ArrayList<String>` không?

Không. Khi không có thông tin kiểu khác, `new ArrayList<>()` suy luận `ArrayList<Object>`. Phép `add` không định nghĩa lại generic parameter.

**Câu 5.** `var names = createNames();` với `createNames()` khai báo trả `List<String>` có kiểu nào?

`List<String>`, bất kể implementation runtime do `createNames()` trả về là `ArrayList` hay `LinkedList`.

**Câu 6.** `List<String> names; if (flag) names = new ArrayList<>(); else names = new LinkedList<>();` có được không?

Có, nếu mọi đường đi đều gán trước khi dùng. Đây là khai báo kiểu **tường minh**, kết hợp kiểm tra definite assignment; không phải `var` suy luận từ các phép gán sau.

**Câu 7.** `final var names = new ArrayList<String>(); names.add("Java");` có hợp lệ không?

Có. `final` cấm gán lại tham chiếu `names` nhưng không cấm gọi `add` trên đối tượng `ArrayList` có thể sửa.

## 13. Nguồn chuẩn còn áp dụng

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): định nghĩa suy luận kiểu biến cục bộ từ biểu thức khởi tạo và phạm vi `var` từ Java 10.
- [OpenJDK FAQ — Local Variable Type Inference, Q6](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md#q6-why-is-an-initializer-required-on-the-left-hand-side-of-a-var-declaration): giải thích vì sao `var` cần initializer và không sử dụng các phép gán ở những dòng sau.
- [OpenJDK FAQ bản JEP gốc — “How do we infer the type of a variable that has multiple assignments?”](https://cr.openjdk.org/~briangoetz/jep-286/lvti-faq.html): nêu trực tiếp rằng kiểu được suy luận *solely* từ initializer.
- [Oracle Java 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): cú pháp `var` và các giới hạn trên JDK 17.
- [OpenJDK — Local Variable Type Inference Style Guidelines](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-style-guide.md): cách cân nhắc độ rõ ràng, đặc biệt khi initializer bộc lộ kiểu cụ thể hoặc thông tin generic còn thiếu.
- [Java SE 17 — Java Language Specification, `14.4 Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4): quy tắc ngôn ngữ đối với khai báo biến cục bộ.
- [Java SE 17 — Java Language Specification, `5.2 Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.2): kiểm tra kiểu trong các phép gán sau khai báo.

**Ghi nhớ:** `var` chỉ điền kiểu cho biến **ngay lúc khai báo** bằng thông tin từ initializer. Compiler không quay lại thay đổi kiểu đó khi thấy `=`, `add(...)`, vòng lặp hay nhánh điều kiện ở phía sau. Muốn biến nhận nhiều implementation, hoặc muốn collection có generic type cụ thể, hãy cung cấp abstraction và thông tin kiểu thích hợp ngay khi khai báo.