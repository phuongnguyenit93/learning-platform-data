# var với List, Set, Map và kiểu generic lồng nhau trong Java

*Chủ đề: Java 10 — var và generics. Các quy tắc trong bài vẫn áp dụng ở Java 17+ và các phiên bản Java hiện đại.*

## 1. `var` với generics thực sự có nghĩa gì?

Từ Java 10, `var` cho phép **suy luận kiểu tĩnh của biến cục bộ** từ biểu thức khởi tạo. Nếu biểu thức có kiểu generic như `List<String>`, `Set<Integer>` hay `Map<String,Integer>` thì biến khai báo bằng `var` vẫn giữ thông tin kiểu đó. `var` không tạo biến dynamic, không chuyển kiểu thành `Object` theo mặc định và không tắt kiểm tra generic của trình biên dịch.

~~~java
var names = List.of("Lan", "Mai");       // List<String>
var years = Set.of(2024, 2025);         // Set<Integer>
var scores = Map.of("Lan", 9, "Mai", 8); // Map<String, Integer>
~~~

Các chữ ký generic của `List.of`, `Set.of` và `Map.of` cho phép compiler xác định kiểu dựa trên các đối số. Vì thế:

~~~java
var names = List.of("Lan", "Mai");
String first = names.get(0);  // Hợp lệ
// names.add(123);           // Sai kiểu: List<String> không nhận Integer
~~~

Tuy nhiên, `names.add("An")` dù **đúng kiểu** vẫn ném `UnsupportedOperationException` khi chạy: danh sách tạo bằng `List.of` không thể sửa. Đây là hai khía cạnh khác nhau: **kiểu generic** được kiểm tra ở compile time, còn khả năng sửa tập hợp phụ thuộc hợp đồng của collection.

So sánh:

~~~java
List<String> a = List.of("Java", "SE");
var b = List.of("Java", "SE");
~~~

`a` và `b` đều có kiểu tĩnh `List<String>`. `var` chỉ lược bớt kiểu ở vị trí khai báo local variable.

## 2. `var` với `List<E>`

### 2.1. Suy luận kiểu từ phần tử

~~~java
var langs = List.of("Java", "Kotlin"); // List<String>
var primes = List.of(2, 3, 5);        // List<Integer>
var flags = List.of(true, false);    // List<Boolean>
~~~

Với ví dụ này, kiểu phần tử của danh sách rõ ràng từ các đối số. `List.of` trả về danh sách **không thể sửa**, cấm phần tử `null` và vẫn cho phép các phần tử bằng nhau. `var` không thay đổi các đặc điểm đó.

Danh sách mutable có thể được tạo bằng cách cung cấp tham số kiểu ở biểu thức khởi tạo:

~~~java
var editable = new ArrayList<String>(); // ArrayList<String>
editable.add("Java");

var copy = new ArrayList<>(List.of("Java", "SE")); // ArrayList<String>
copy.add("JDK"); // Hợp lệ, copy có thể sửa
~~~

Chú ý **kiểu khai báo** của `editable` là `ArrayList<String>`, không phải `List<String>`. Nếu muốn local variable mang kiểu interface, hãy viết `List<String> editable = new ArrayList<>();`. Lựa chọn này có thể giúp mã ít phụ thuộc lớp triển khai.

### 2.2. Danh sách rỗng và target type

~~~java
var empty = List.of();             // List<Object>
List<String> names = List.of();    // List<String>
var typed = List.<String>of();     // List<String>
~~~

Khi dùng `var`, không có kiểu đích ở vế trái để cho `List.of()` biết phần tử dự định là `String`. Với factory không có đối số, nó suy luận `Object`. Cách có kiểu bên trái hoặc **type witness** `<String>` sẽ nêu rõ ý định.

`List.copyOf(collection)` nhận collection có kiểu và tạo danh sách không thể sửa chứa các phần tử tại thời điểm gọi:

~~~java
var mutableNames = new ArrayList<>(List.of("Lan", "Mai")); // ArrayList<String>
var snapshot = List.copyOf(mutableNames);               // List<String>
mutableNames.add("An");
// snapshot vẫn chứa "Lan", "Mai"
~~~

Việc gọi `copyOf` không bảo đảm sao chép sâu các phần tử tham chiếu; nó chỉ cam kết cấu trúc tập hợp không thể sửa, với các lưu ý trong API.

## 3. `var` với `Set<E>`

~~~java
var ids = Set.of(1, 2, 3);                 // Set<Integer>
var roles = Set.of("dev", "reviewer");     // Set<String>
var sortedIds = new TreeSet<>(ids);        // TreeSet<Integer>
~~~

`Set.of` tạo một tập không thể sửa, không nhận `null`, không chấp nhận phần tử trùng nhau trong factory (sẽ ném `IllegalArgumentException`). **Thứ tự duyệt phần tử của `Set.of` không được cam kết**, vì vậy không nên viết bài kiểm thử phụ thuộc thứ tự chuỗi của `Set.toString()`.

Nếu cần đầu ra tăng dần có thể dự đoán với số nguyên:

~~~java
var ids = Set.of(20, 10, 30);
var sortedIds = new TreeSet<>(ids);
System.out.println(sortedIds); // [10, 20, 30]
~~~

`TreeSet` cung cấp hành vi sắp xếp, chứ không phải `var`. Với tập rỗng: `var emptySet = Set.of();` suy luận `Set<Object>`; có thể viết `Set<String> emptySet = Set.of();` hoặc `var emptySet = Set.<String>of();` nếu muốn `Set<String>`.

## 4. `var` với `Map<K, V>`

~~~java
var prices = Map.of("apple", 5, "pear", 7); // Map<String, Integer>
Integer applePrice = prices.get("apple");
~~~

`Map.of` trả về map không thể sửa, cấm khóa/giá trị `null` và cấm khóa trùng nhau khi tạo. `Map.of("a",1)` không tự trở thành `HashMap`; tên lớp nội bộ cụ thể của map không cần được ứng dụng dựa vào.

Nếu cần `Map` có thể sửa:

~~~java
var counts = new HashMap<String, Integer>(); // HashMap<String,Integer>
counts.put("a", 1);
counts.put("b", 2);

var seeded = new HashMap<>(Map.of("x", 10)); // HashMap<String,Integer>
seeded.put("y", 20);
~~~

Kiểu của biến dùng `var` ở hai trường hợp này vẫn chứa các type arguments. Một map rỗng không có thông tin khóa/giá trị sẽ suy luận rộng hơn:

~~~java
var emptyMap = Map.of();             // Map<Object, Object>
Map<String, Integer> typed = Map.of(); // Map<String, Integer>
var typed2 = Map.<String, Integer>of(); // Map<String, Integer>
~~~

Nếu biến phải có kiểu cụ thể, hãy đưa ra thông tin kiểu tại initializer hoặc khai báo kiểu bên trái.

## 5. Cạm bẫy phổ biến nhất: diamond `<>` không có kiểu đích

Đặt cạnh nhau:

~~~java
List<String> names = new ArrayList<>();          // List<String>
Map<String, Integer> counts = new HashMap<>();   // Map<String,Integer>
~~~

Vế trái có kiểu tường minh nên diamond `<>` có thể suy luận tham số generic từ **target type**. Nhưng:

~~~java
var names = new ArrayList<>(); // ArrayList<Object>
var counts = new HashMap<>();  // HashMap<Object, Object>
~~~

Vế trái `var` không cung cấp target type. Các constructor không có tham số làm ràng buộc generic nên suy luận ra `Object`. Đây là **parameterized type với `Object`**, khác với raw type.

~~~java
var mixed = new ArrayList<>(); // ArrayList<Object>
mixed.add("Java");
mixed.add(42);                 // Biên dịch vì String và Integer đều là Object
Object value = mixed.get(0);
~~~

Đoạn này có thể chạy, nhưng thường không phải kiểu `List<String>` mà lập trình viên muốn. Không thể gọi `mixed.get(0).toUpperCase()` trực tiếp vì kiểu tĩnh của phần tử là `Object`.

Các cách tránh:

~~~java
var names = new ArrayList<String>();                   // ArrayList<String>
var names2 = new ArrayList<>(List.of("Java", "SE"));     // ArrayList<String>
List<String> names3 = new ArrayList<>();                // List<String>

var counts = new HashMap<String, Integer>();           // HashMap<String,Integer>
Map<String, Integer> counts2 = new HashMap<>();         // Map<String,Integer>
var counts3 = new HashMap<>(Map.of("a", 1));            // HashMap<String,Integer>
~~~

**Quy tắc:** chỉ dùng `var` với diamond trống khi biểu thức bên phải có đủ ngữ cảnh xác định kiểu generic mong muốn. Nếu chưa có nguồn dữ liệu hay ràng buộc, viết rõ type arguments hoặc khai báo interface ở bên trái.

### Phân biệt với raw type

~~~java
var raw = new ArrayList();     // Raw ArrayList: bỏ type arguments
var objects = new ArrayList<>(); // ArrayList<Object>: vẫn là parameterized type
~~~

Raw type làm giảm bảo đảm kiểm tra kiểu và có thể dẫn đến cảnh báo unchecked. `ArrayList<Object>` vẫn có generic, nhưng `Object` là kiểu quá rộng nếu cần một danh sách thuần `String`. Tránh cả hai cách khi yêu cầu dữ liệu thực sự có kiểu cụ thể.

## 6. Kiểu generic lồng nhau vẫn được suy luận đầy đủ

### 6.1. Danh sách của các danh sách

~~~java
var lines = new ArrayList<List<String>>();
// Kiểu tĩnh: ArrayList<List<String>>

lines.add(List.of("Java", "SE"));
var firstLine = lines.get(0);  // List<String>
var firstWord = firstLine.get(0); // String
~~~

`var` ở từng dòng giữ thông tin generic từ biểu thức tương ứng: `lines.get(0)` có kiểu `List<String>` nên `firstWord` có kiểu `String`. Không có bước nào biến nó thành `Object`.

### 6.2. Map chứa List chứa Set

~~~java
var teams = new HashMap<String, List<Set<Integer>>>();
// Kiểu tĩnh: HashMap<String, List<Set<Integer>>>

teams.put("backend", List.of(Set.of(10, 20), Set.of(30)));

var groups = teams.get("backend"); // List<Set<Integer>>
var firstGroup = groups.get(0);   // Set<Integer>
var anyId = firstGroup.iterator().next(); // Integer; không dự đoán giá trị
~~~

Quan hệ kiểu:

| Biểu thức | Kiểu tĩnh |
| --- | --- |
| `teams` | `HashMap<String, List<Set<Integer>>>` |
| `teams.get("backend")` | `List<Set<Integer>>` |
| `groups.get(0)` | `Set<Integer>` |
| `firstGroup.iterator()` | `Iterator<Integer>` |
| `firstGroup.iterator().next()` | `Integer` |

Ở runtime, `teams.get("unknown")` có thể là `null`. `var` không tự kiểm tra null và không khiến kết quả `get` trở thành `Optional`. Nếu khóa có thể thiếu, kiểm tra bằng `containsKey`, `getOrDefault` hoặc xử lý `null` theo hợp đồng nghiệp vụ.

Mỗi collection giữ quy tắc riêng: `List` bảo toàn vị trí phần tử, nhưng `Set.of` không hứa về thứ tự duyệt. Nếu cần in tập có thứ tự, hãy tạo `new TreeSet<>(firstGroup)`.

### 6.3. Kiểu từ chữ ký generic của phương thức

~~~java
// Đoạn sau là hai thành viên trong cùng một lớp:
static Map<String, List<Set<Integer>>> loadTeams() {
    return Map.of("backend", List.of(Set.of(1, 2)));
}

void inspect() {
    var teams = loadTeams(); // Map<String, List<Set<Integer>>>
    var groups = teams.get("backend"); // List<Set<Integer>>
}
~~~

Chữ ký phương thức `loadTeams()` đã xác định kiểu trả về, nên local `var` sử dụng kiểu đó. **Đây là đoạn code minh họa cần đặt trong lớp**, không phải một tệp Java độc lập; chương trình chạy đầy đủ ở mục 7.

Kiểu trả về của phương thức và kiểu field phải khai báo tường minh. `var` được dùng cho local variable, không dùng để viết `var loadTeams()` hay một field `var teams`.

## 7. Chương trình Java 17+ hoàn chỉnh và đầu ra chính xác

Ví dụ sau bao gồm `List`, `Set`, `Map`, diamond, kiểu lồng nhau và việc kiểm tra lại kiểu suy luận qua các tham số phương thức generic tường minh.

~~~java
// File: VarGenericCollectionsDemo.java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class VarGenericCollectionsDemo {
    public static void main(String[] args) {
        var names = List.of("Lan", "Mai");           // List<String>
        var roles = Set.of("developer", "reviewer");   // Set<String>
        var scores = Map.of("Lan", 9, "Mai", 8);     // Map<String, Integer>

        var editableNames = new ArrayList<>(names);   // ArrayList<String>
        editableNames.add("An");

        var noHint = new ArrayList<>();                // ArrayList<Object>
        noHint.add("x");
        noHint.add(10);

        var teams = new HashMap<String, List<Set<Integer>>>();
        teams.put("team", List.of(Set.of(1, 2), Set.of(3)));

        var groups = teams.get("team");               // List<Set<Integer>>
        var firstGroupSorted = new TreeSet<>(groups.get(0));
        var memberCount = groups.stream().mapToInt(Set::size).sum();

        System.out.println("names = " + names);
        System.out.println("roles size = " + roles.size());
        System.out.println("score Lan = " + scores.get("Lan"));
        System.out.println("editable names = " + editableNames);
        System.out.println("diamond values = " + noHint);
        System.out.println("group count = " + groups.size());
        System.out.println("member count = " + memberCount);
        System.out.println("first group sorted = " + firstGroupSorted);

        verifyNames(names);
        verifyScores(scores);
        verifyTeams(teams);
    }

    static void verifyNames(List<String> names) { }
    static void verifyScores(Map<String, Integer> scores) { }
    static void verifyTeams(Map<String, List<Set<Integer>>> teams) { }
}
~~~

Lưu tệp đúng tên `VarGenericCollectionsDemo.java`. Có thể biên dịch đặt mức ngôn ngữ Java 17 trên JDK hiện đại rồi chạy:

~~~bash
javac --release 17 VarGenericCollectionsDemo.java
java VarGenericCollectionsDemo
~~~

Kết quả chuẩn:

~~~text
names = [Lan, Mai]
roles size = 2
score Lan = 9
editable names = [Lan, Mai, An]
diamond values = [x, 10]
group count = 2
member count = 3
first group sorted = [1, 2]
~~~

Diễn giải:

1. `names` có kiểu tĩnh `List<String>` nên truyền được vào `verifyNames(List<String>)`. `scores` có kiểu `Map<String,Integer>` nên truyền vào `verifyScores(Map<String,Integer>)`.
2. `roles` được kiểm tra qua `size()`, không thông qua thứ tự duyệt `Set.of` vốn không ổn định.
3. `editableNames` có kiểu `ArrayList<String>`, nên có thể thêm `"An"` và giữ danh sách `names` gốc không đổi.
4. `noHint` minh họa diamond suy luận ra `ArrayList<Object>` và chấp nhận cả chuỗi và số nguyên. Kiểu này hợp lệ nhưng kém chặt hơn khi ứng dụng chỉ định lưu chuỗi.
5. `teams` có kiểu `HashMap<String,List<Set<Integer>>>`, tương thích với tham số `Map<String,List<Set<Integer>>>` của `verifyTeams`.
6. `groups` là `List<Set<Integer>>`; số nhóm là 2, tổng số phần tử tập hợp là 2 + 1 = 3. `TreeSet` sắp xếp tập đầu thành `[1, 2]` để đầu ra không phụ thuộc thứ tự duyệt của `Set.of`.
7. Ba hàm `verify...` có thân rỗng và được gọi chỉ để minh họa **compiler kiểm tra generic ngay tại điểm gọi**. Nếu types bị mất, chương trình không thể biên dịch các lời gọi đó.

## 8. `var` không thay đổi luật generics

### 8.1. Generic invariance vẫn áp dụng

~~~java
var integers = List.of(1, 2, 3); // List<Integer>

// Sai: List<Integer> không phải subtype của List<Number>.
// List<Number> numbers = integers;

// Hợp lệ khi cần đọc giá trị dưới dạng Number:
List<? extends Number> numbers = integers;
Number first = numbers.get(0);
~~~

Dù `Integer` là subtype của `Number`, `List<Integer>` không phải subtype của `List<Number>`. `var` không biến generic Java thành covariant.

### 8.2. Danh sách lẫn nhiều kiểu có thể suy luận kiểu chung khó đọc

~~~java
var mixed = List.of(1, 2.5, "hello");
~~~

Compiler suy luận một kiểu chung phù hợp các đối số theo quy tắc least upper bound; **đừng mặc định kết quả là `List<Number>`**. Nếu muốn chứa nhiều số khác nhau:

~~~java
List<Number> numbers = List.of(1, 2.5);
~~~

Nếu nghiệp vụ thật sự cho phép số và chuỗi chung một collection:

~~~java
List<Object> items = List.of(1, 2.5, "hello");
~~~

Hãy chọn type arguments có chủ đích, tránh tạo collection quá rộng chỉ vì biểu thức initializer ngắn.

### 8.3. Type erasure không biến mất

Generic thường được kiểm tra khi biên dịch, và `var` không làm Java lưu một kiểu `List<String>` có thể kiểm tra trực tiếp bằng `instanceof` lúc chạy. Ví dụ, `instanceof List<String>` không phải phép kiểm tra runtime hợp lệ đối với một đối tượng danh sách tùy ý; có thể kiểm tra `instanceof List<?>` rồi kiểm tra phần tử theo nhu cầu.

Không dùng `var` để kỳ vọng JVM biết các tham số generic đã bị xóa ở runtime. Đây là cơ chế generics Java, độc lập với suy luận local variable.

### 8.4. Lambda cần kiểu đích rõ

~~~java
// Sai: biểu thức lambda không có target type từ var.
// var length = text -> text.length();

// Đúng: functional interface cung cấp target type.
java.util.function.Function<String, Integer> length =
        text -> text.length();
~~~

Vì `var` không cung cấp kiểu đích bên trái, lambda/method reference độc lập không đủ để suy luận kiểu local variable theo cách trên. Khi kiểu cần được đặt rõ ràng, hãy ghi functional interface hoặc một biểu thức có kiểu thích hợp.

## 9. Khi nào nên dùng `var` với collections?

| Tình huống | Cách viết gợi ý | Mục tiêu |
| --- | --- | --- |
| Factory có phần tử rõ kiểu | `var names = List.of("A", "B");` | Giữ `List<String>`, gọn và dễ đọc |
| Set có kiểu rõ | `var ids = Set.of(1, 2);` | Giữ `Set<Integer>` |
| Map có key/value rõ | `var scores = Map.of("a", 1);` | Giữ `Map<String,Integer>` |
| Collection rỗng với diamond | `List<String> names = new ArrayList<>();` | Tránh vô tình `ArrayList<Object>` |
| Collection rỗng nhưng muốn viết `var` | `var names = new ArrayList<String>();` | Type argument rõ ràng |
| Copy từ nguồn đã có kiểu | `var names = new ArrayList<>(source);` | Suy luận từ `source` |
| Generic lồng nhau từ constructor | `var teams = new HashMap<String,List<Set<Integer>>>();` | Không mất type arguments lồng nhau |
| Giá trị lồng nhau từ method | `var teams = loadTeams();` | Tránh lặp kiểu dài khi chữ ký method rõ |
| Field/return type/parameter | `Map<String,List<Set<Integer>>> ...` | Giữ hợp đồng API rõ ràng |
| Collection chứa kiểu hỗn hợp | Cân nhắc `List<Number>` hoặc `List<Object>` tường minh | Tuyên bố rõ ý định và giới hạn kiểu |

Thực hành tốt: đặt tên biến mô tả nội dung, ví dụ `scoresByName`, `groupsByTeam`; dùng `var` khi người đọc có thể biết kiểu bằng một cái nhìn ở initializer. Với type arguments sâu hoặc rỗng, việc khai báo kiểu tường minh đôi khi **dễ bảo trì hơn**.

## 10. Các lỗi thường gặp

- **“`var` làm mất generic nên bất kỳ đối tượng nào cũng cho vào `List<String>` được.”** Sai. Kiểu generic của biểu thức vẫn được kiểm tra tĩnh.
- **“`var list = new ArrayList<>()` là `ArrayList<String>` vì sau đó chỉ thêm chuỗi.”** Sai. Những lời gọi `add` ở các dòng sau không quay lại thay đổi kiểu suy luận ban đầu: ở đây là `ArrayList<Object>`.
- **“Diamond `<>` và raw constructor `new ArrayList()` hoàn toàn giống nhau.”** Sai. Một bên có type argument suy luận, một bên dùng raw type.
- **“`var` đảm bảo collection có thể thay đổi.”** Sai. `List.of`, `Set.of`, `Map.of` không thể sửa; `ArrayList` và `HashMap` có thể sửa.
- **“`Set.of` luôn in đúng thứ tự đối số.”** Sai. Phải dùng collection có thứ tự cam kết hoặc sắp xếp trước khi in.
- **“`HashMap<String,List<Set<Integer>>>` thành `Map<Object,Object>` khi khai báo bằng `var`.”** Sai. Nếu vế phải có đầy đủ type arguments, `var` giữ kiểu đó.
- **“`var` tự giải quyết `null` của `Map.get`.”** Sai. Mã vẫn phải xử lý khả năng không có khóa.
- **“`var` cho phép dùng `List<Integer>` như `List<Number>`.”** Sai. Generic invariance không đổi.
- **“`var` dùng cho field hoặc kiểu trả về method.”** Sai. Suy luận này dành cho các vị trí local variable được ngữ pháp cho phép.

## 11. Bài tập kèm đáp án

**Bài 1.** Xác định kiểu tĩnh:

~~~java
var a = List.of("A", "B");
var b = Set.of(1, 2);
var c = Map.of("x", true);
~~~

**Đáp án:** `a` là `List<String>`, `b` là `Set<Integer>`, `c` là `Map<String,Boolean>`.

**Bài 2.** Vì sao hai khai báo sau cho kiểu khác nhau?

~~~java
var first = new ArrayList<>();
List<String> second = new ArrayList<>();
~~~

**Đáp án:** `first` là `ArrayList<Object>` do không có thông tin kiểu đích; `second` có kiểu khai báo `List<String>` và diamond suy luận `String` từ kiểu đích.

**Bài 3.** Viết local variable `byTeam` với kiểu `HashMap<String,List<Integer>>` nhưng vẫn dùng `var`.

**Đáp án:**

~~~java
var byTeam = new HashMap<String, List<Integer>>();
~~~

**Bài 4.** Với `var teams = new HashMap<String,List<Set<Integer>>>();`, `teams.get("backend")` có kiểu gì?

**Đáp án:** `List<Set<Integer>>`; biểu thức có thể trả về `null` nếu chưa có khóa tương ứng.

**Bài 5.** `var empty = List.of();` và `List<String> typed = List.of();` có cùng kiểu tĩnh không?

**Đáp án:** Không. `empty` có kiểu `List<Object>`; `typed` có kiểu `List<String>`.

**Bài 6.** `var names = List.of("A"); names.add("B");` có đúng kiểu generic không, và chạy được không?

**Đáp án:** `add("B")` phù hợp kiểu `String` khi biên dịch, nhưng khi chạy sẽ ném `UnsupportedOperationException` vì `List.of` tạo danh sách không thể sửa.

**Bài 7.** `var integers = List.of(1,2); List<Number> n = integers;` có hợp lệ không?

**Đáp án:** Không. `List<Integer>` không gán trực tiếp cho `List<Number>`. Có thể dùng `List<? extends Number> n = integers;` để đọc như `Number`.

**Bài 8.** Vì sao không nên so sánh chuỗi `Set.of(2,1).toString()` với một thứ tự cố định?

**Đáp án:** `Set.of` không bảo đảm thứ tự duyệt. Khi cần đầu ra có thứ tự, dùng `new TreeSet<>(ids)` hoặc sắp xếp một danh sách từ các phần tử trước khi in.

## 12. Nguồn tham khảo chuẩn

- [JLS `14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4.1): quy tắc suy luận `var` từ kiểu của biểu thức initializer trong ngữ cảnh standalone.
- [JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): mục tiêu, phạm vi và giới hạn từ Java 10.
- [dev.java — Using the Var Type Identifier](https://dev.java/learn/language-basics/using-var/): hướng dẫn chính thức về `var` cho local variable.
- [Java SE API — List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html), [Set](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html), [Map](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): hợp đồng và kiểu generic của collection factory.
- [Java SE API — ArrayList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayList.html), [HashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashMap.html), [TreeSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html): constructor, kiểu dữ liệu và sắp xếp.
- [JLS `4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5): tính bất biến của các tham số kiểu và quy tắc generic Java.

**Kết luận ghi nhớ:** `var` có thể giữ chính xác kiểu `List<String>`, `Set<Integer>`, `Map<String,Integer>` hoặc các kiểu lồng nhau sâu. Hãy nhìn vào **biểu thức khởi tạo** để biết compiler có đủ dữ liệu suy luận type arguments chưa. Đặc biệt với `new ArrayList<>()`, `new HashMap<>()` và các factory rỗng, chọn kiểu cụ thể ngay từ đầu để tránh `Object` ngoài ý muốn.