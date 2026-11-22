# Java 10 – Ảnh hưởng của collection rỗng đến kiểu suy luận của `var` và generics

> **Phạm vi:** Java 10 → `var và generics` → `Ảnh hưởng của collection rỗng đến kiểu suy luận`. Tập trung vào quy tắc generics, diamond (`<>`), generic factory và local-variable type inference vẫn dùng trong Java 17+ và JDK hiện đại. `var` được bổ sung từ Java 10; `List.of`/`Set.of`/`Map.of` đã xuất hiện từ Java 9, `List.copyOf` từ Java 10, còn `Stream.toList` từ Java 16. Những ví dụ có phiên bản cao hơn đều được ghi rõ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Dự đoán đúng kiểu của `var list = new ArrayList<>();`, `var list = List.of();`, `var list = Collections.emptyList();` và các factory rỗng tương tự.
2. Giải thích vì sao **collection rỗng** không cung cấp phần tử làm manh mối suy luận kiểu generic, và tại sao thiếu **target type** khi dùng `var` dễ dẫn đến `Object`.
3. Phân biệt `List<Object>` với `List<String>`, `List<?>` và raw `List`; tránh việc kiểu quá rộng làm suy yếu kiểm tra compile time.
4. Chỉ định kiểu mong muốn bằng khai báo tường minh, type argument ở constructor, **type witness** cho generic method, tham số đã có kiểu hoặc chữ ký phương thức.
5. Nhận ra tính **rỗng**, tính **unmodifiable** và kiểu generic là ba khía cạnh độc lập.
6. Áp dụng quy tắc cho `List`, `Set`, `Map`, `Optional`, `Stream`, mảng và một số collection đặc biệt.
7. Biên dịch và chạy ví dụ Java 17+ để tự kiểm chứng kiểu suy luận, giá trị đầu ra và giới hạn của các API.

## 2. Ý tưởng cốt lõi: không có phần tử thì lấy kiểu `T` từ đâu?

Xét hai khai báo:

~~~java
var first = new ArrayList<>(List.of("Java")); // suy luận ArrayList<String>
var second = new ArrayList<>();               // suy luận ArrayList<Object>
~~~

Ở khai báo thứ nhất, tham số constructor là một collection mang thông tin `String`. Trình biên dịch có đủ ràng buộc để suy luận kiểu phần tử.

Ở khai báo thứ hai, chỉ thấy `new ArrayList<>()`: diamond `<>` không chứa type argument và constructor không nhận phần tử/collection có kiểu để ràng buộc `T`. Bên trái `var` cũng không đưa ra một target type cụ thể như `List<String>`. Với `ArrayList`, giới hạn của tham số kiểu là `Object`, nên kết quả thường gặp là `ArrayList<Object>`.

~~~java
var elements = new ArrayList<>(); // ArrayList<Object>
elements.add("A");                // hợp lệ vì String là Object
elements.add(42);                 // cũng hợp lệ vì Integer là Object
System.out.println(elements);    // [A, 42]
~~~

**Sai lầm thường gặp:** Tin rằng lần gọi `elements.add("A")` đầu tiên sẽ khiến trình biên dịch suy ra `ArrayList<String>`. Suy luận đã hoàn thành **ở câu lệnh khai báo**; các lệnh sau không thay đổi kiểu của biến.

Một collection có kích thước 0 **không nhất thiết** mang kiểu phần tử `Object`. Nếu nơi tạo nó vẫn có thông tin kiểu (trong khai báo, type witness, constructor, phương thức hoặc đối số khác), kết quả vẫn có thể là `List<String>` hay `Set<Integer>`. Mấu chốt là **mất thông tin về `T` trong ngữ cảnh suy luận**, không phải bản thân việc collection rỗng.

## 3. `var` và target typing hoạt động thế nào?

### 3.1. Có target type: trình biên dịch suy luận từ vế trái

~~~java
List<String> names = new ArrayList<>();
List<String> labels = List.of();
List<String> cached = Collections.emptyList();
~~~

Các khai báo này hợp lệ: vế trái đã nói rõ kiểu mong đợi là `List<String>`, vì vậy diamond và generic factory có **ngữ cảnh đích** để xác định type argument là `String`, dù danh sách ban đầu rỗng.

Với diamond, có thể viết dài hơn `new ArrayList<String>()`, nhưng `new ArrayList<>()` rõ ràng và đủ khi vế trái đã cung cấp `List<String>`.

### 3.2. Không có target type cụ thể: `var` dựa vào biểu thức standalone

~~~java
var names = new ArrayList<>();      // ArrayList<Object>
var labels = List.of();             // List<Object>
var cached = Collections.emptyList(); // List<Object>
~~~

Với khai báo `var`, biểu thức khởi tạo được định kiểu như một biểu thức độc lập theo quy tắc local-variable type inference. Không có vế trái dạng `List<String>` làm target type. Khi generic method/constructor không nhận được đủ ràng buộc từ đối số, compiler thường dùng giới hạn rộng nhất thích hợp, ví dụ `Object`.

Đối chiếu:

| Khai báo | Kiểu suy luận/kết quả | Điểm quyết định |
| --- | --- | --- |
| `List<String> a = new ArrayList<>();` | `List<String>`; instance `ArrayList<String>` | Target type ở vế trái |
| `var a = new ArrayList<>();` | `ArrayList<Object>` | Không có target type hay đối số cung cấp `T` |
| `var a = new ArrayList<String>();` | `ArrayList<String>` | Type argument được viết tường minh |
| `List<String> a = List.of();` | `List<String>` | Generic factory nhận target type |
| `var a = List.of();` | `List<Object>` | Factory không có phần tử và thiếu target type |
| `var a = List.<String>of();` | `List<String>` | Type witness chỉ định `T` |
| `var a = List.of("A");` | `List<String>` | Phần tử `"A"` cung cấp kiểu |
| `var a = new ArrayList<>(List.of("A"));` | `ArrayList<String>` | Constructor nhận collection có phần tử `String` |

Lưu ý: Kiểu của biến khai báo bằng `var` có thể là implementation cụ thể, như `ArrayList<String>`, thay vì interface `List<String>`. Khi yêu cầu thiết kế là **phụ thuộc vào interface**, khai báo `List<String> a = ...` vẫn có giá trị.

### 3.3. Diamond không giống raw type

So sánh:

~~~java
var typedBroad = new ArrayList<>(); // ArrayList<Object>, kiểu generic hợp lệ
var raw = new ArrayList();          // raw ArrayList, bỏ type argument
~~~

`ArrayList<Object>` là parameterized type và vẫn được Java kiểm tra generic khi dùng trong API; raw `ArrayList` đánh mất nhiều kiểm tra kiểu và có thể gây cảnh báo `unchecked`. Việc suy luận `Object` đôi khi không đúng mục đích, nhưng **không đồng nghĩa** với sử dụng raw type. Tránh tạo raw collection mới trong code Java hiện đại.

## 4. Tại sao `List<Object>` không thể dùng thay `List<String>`?

Java generics **invariant**: dù `String` là subtype của `Object`, `List<String>` không phải subtype của `List<Object>`, và `List<Object>` cũng không phải `List<String>`.

~~~java
var items = new ArrayList<>();  // ArrayList<Object>

// List<String> strings = items; // LỖI biên dịch
// consumeStrings(items);        // LỖI nếu consumeStrings(List<String>)

List<Object> objects = items;   // HỢP LỆ
objects.add("hello");
objects.add(10);
~~~

Vì `items` là `ArrayList<Object>`, không thể truyền vào API yêu cầu `List<String>`, **dù hiện tại nó đang rỗng** hoặc bạn chỉ định thêm chuỗi. Kiểu static, không phải dữ liệu tại runtime, quyết định tính tương thích của lời gọi.

Vì sao Java không tự coi `List<String>` là `List<Object>`? Nếu cho phép, code nhận `List<Object>` có thể thêm một `Integer` vào danh sách được caller tin là chỉ chứa `String`, gây mất an toàn kiểu.

Nếu API chỉ cần **đọc** phần tử dưới dạng `Object`, có thể nhận tham số `List<?>` hoặc `List<? extends SomeBase>` phù hợp. Đây là lựa chọn thiết kế API, không phải lý do để biến mọi collection của dự án thành `List<Object>`. Với `List<?>`, không thể thêm phần tử không-null tùy ý vì kiểu phần tử thực tế chưa biết.

## 5. Cách giữ đúng kiểu cho collection rỗng

### 5.1. Cách 1 — Khai báo vế trái rõ kiểu

~~~java
List<String> names = new ArrayList<>();
Set<Integer> ids = new HashSet<>();
Map<String, Integer> counters = new HashMap<>();
~~~

Đây thường là lựa chọn đơn giản nhất cho một collection rỗng được tạo để thêm phần tử ở các câu lệnh sau. Vế trái vừa thể hiện **hợp đồng kiểu**, vừa cung cấp ngữ cảnh suy luận cho diamond.

### 5.2. Cách 2 — Dùng `var` nhưng viết type argument ở constructor

~~~java
var names = new ArrayList<String>();       // ArrayList<String>
var ids = new HashSet<Integer>();          // HashSet<Integer>
var counters = new HashMap<String, Integer>(); // HashMap<String,Integer>
~~~

Không có “mất type” ở đây: `var` suy luận từ biểu thức `new ArrayList<String>()` đã có type argument cụ thể. Chọn cách này khi kiểu implementation là điều bạn thực sự muốn dùng trong phạm vi cục bộ.

**Cẩn thận:** `var names = new ArrayList<String>();` có kiểu tĩnh `ArrayList<String>`, còn `List<String> names = new ArrayList<>();` có kiểu khai báo `List<String>`. Hai cách có thể dùng cùng một object và đều kiểm tra phần tử String, nhưng phạm vi phương thức mà biến nhìn thấy khác nhau.

### 5.3. Cách 3 — Type witness cho generic factory

Dấu `<T>` đặt **trước tên phương thức** sau dấu chấm là cách viết rõ type argument cho phương thức generic:

~~~java
var names = List.<String>of();                   // List<String>
var cached = Collections.<String>emptyList();    // List<String>
var ids = Set.<Integer>of();                     // Set<Integer>
var mapping = Map.<String, Integer>of();         // Map<String,Integer>
var stream = Stream.<String>empty();             // Stream<String>
var optional = Optional.<String>empty();         // Optional<String>
~~~

Dùng khi muốn `var` và factory rỗng nhưng vẫn giữ kiểu cụ thể. Dấu `<>` của diamond trong `new ArrayList<>()` và type witness `<String>` trong `List.<String>of()` có vai trò khác nhau: diamond **yêu cầu compiler suy luận type argument**, còn type witness **cung cấp type argument trực tiếp**.

Không nhầm `List.<String>of()` với `List<String>.of()`: cách thứ hai không phải cú pháp gọi static generic method hợp lệ.

### 5.4. Cách 4 — Truyền collection hoặc đối số đã có kiểu

~~~java
var names = new ArrayList<>(List.of("An", "Binh")); // ArrayList<String>
var emptyNames = new ArrayList<>(List.<String>of()); // ArrayList<String>
~~~

Ở trường hợp thứ nhất, phần tử `String` ràng buộc kiểu. Ở trường hợp thứ hai, danh sách **vẫn rỗng** nhưng generic type của đối số đã được định rõ bằng type witness; vì vậy compiler có thể suy luận `ArrayList<String>`.

Có thể dùng biến trung gian:

~~~java
List<String> seed = List.of();
var names = new ArrayList<>(seed); // ArrayList<String>
~~~

Số lượng phần tử của `seed` không quan trọng đối với suy luận ở đây; `Collection<? extends String>` là thông tin kiểu có sẵn từ biến `seed`.

### 5.5. Cách 5 — Lấy kết quả từ phương thức có kiểu trả về tường minh

~~~java
static List<String> loadNames() {
    return List.of();
}

// Trong phương thức khác:
var names = loadNames(); // List<String>, dù loadNames() trả danh sách rỗng
~~~

`loadNames()` được khai báo trả `List<String>`; compiler biết kiểu trả về từ **chữ ký phương thức**, không cần xem lúc chạy có bao nhiêu phần tử. Đây là cách quan trọng khi lấy dữ liệu qua repository/service/API.

### 5.6. Capacity, độ dài và tên biến không quyết định `T`

~~~java
var a = new ArrayList<>(0);        // ArrayList<Object>
var b = new ArrayList<String>(0);  // ArrayList<String>
var c = new String[0];             // String[]
~~~

Đối số `0` trong `new ArrayList<>(0)` chỉ chỉ định **dung lượng khởi tạo** cho ArrayList, không phải kiểu phần tử; vì vậy nó không cung cấp `T`. Với mảng `new String[0]`, component type `String` được ghi trực tiếp trong biểu thức tạo mảng nên `var` suy luận `String[]` dù độ dài bằng 0. Tên biến như `stringList` cũng không thể buộc compiler chọn `String`.

## 6. Các generic factory rỗng thường gặp

### 6.1. `List.of()` và `Collections.emptyList()`

~~~java
var a = List.of();                  // List<Object>
var b = Collections.emptyList();    // List<Object>
var c = List.<String>of();          // List<String>
var d = Collections.<String>emptyList(); // List<String>
~~~

Cả `List.of()` và `Collections.emptyList()` đều trả danh sách không thể sửa cấu trúc qua API danh sách. Mục đích của bài là **suy luận generic type**: `a` và `b` thiếu type argument, còn `c`/`d` có kiểu `String` nhờ type witness. Dùng `List<String> a = List.of();` cũng đủ để compiler suy luận `String` mà không cần type witness.

### 6.2. `Set.of()`

~~~java
var empty = Set.of();               // Set<Object>
var names = Set.<String>of();       // Set<String>
Set<String> target = Set.of();      // Set<String>
~~~

`Set.of` không nhận phần tử null và không cam kết thứ tự duyệt. Với tập rỗng, những điều này không làm thay đổi vấn đề generic: thiếu target type thì tham số `E` thường suy luận `Object`.

### 6.3. `Map.of()` và `new HashMap<>()`

~~~java
var emptyMap = Map.of();                    // Map<Object,Object>
var typedMap = Map.<String, Integer>of();   // Map<String,Integer>
Map<String, Integer> target = Map.of();     // Map<String,Integer>

var mutableMap = new HashMap<>();              // HashMap<Object,Object>
var mutableTyped = new HashMap<String,Integer>(); // HashMap<String,Integer>
~~~

`Map` cần **hai** type argument: `K` cho key và `V` cho value. Cần giữ cả hai loại đúng theo hợp đồng, nhất là khi truyền sang method yêu cầu `Map<String,Integer>`. Với `var mutableMap = new HashMap<>()`, thêm một cặp `("A", 1)` sau đó **không đổi** generic type `Object,Object`.

### 6.4. `Optional.empty()`

~~~java
var unknown = Optional.empty();           // Optional<Object>
var known = Optional.<String>empty();     // Optional<String>
Optional<String> expected = Optional.empty(); // Optional<String>
~~~

`Optional` không phải collection, nhưng là ví dụ generic factory rỗng rất gần với vấn đề này. Không có giá trị bên trong để ràng buộc `T`, nên target type/type witness đặc biệt hữu ích. Trong API, nên công bố chữ ký trả `Optional<User>` thay vì để caller suy đoán từ dữ liệu lúc chạy.

### 6.5. `Stream.empty()` và pipeline rỗng

~~~java
var stream = Stream.empty();                    // Stream<Object>
var typedStream = Stream.<String>empty();       // Stream<String>
var values = Stream.<String>empty().toList();   // List<String>
~~~

`Stream.toList()` xuất hiện từ Java 16 nên dùng được trong ví dụ Java 17+. Một stream rỗng tự nó không mang phần tử để ràng buộc `T`; việc chỉ định kiểu ở `Stream.<String>empty()` sẽ cho phép các thao tác sau nhận `String`. Kết quả `toList()` là danh sách không cho chỉnh sửa cấu trúc theo hợp đồng Java hiện đại.

### 6.6. Empty collection không có nghĩa luôn rơi về `Object`

~~~java
enum Level { LOW, HIGH }
var levels = EnumSet.noneOf(Level.class); // EnumSet<Level>
var names = new String[0];                // String[]
~~~

`EnumSet.noneOf(Level.class)` nhận một class token có đủ thông tin về kiểu enum, nên trả `EnumSet<Level>` mặc dù tập rỗng. `new String[0]` có component type tường minh. Với một generic method có giới hạn tham số kiểu khác `Object`, compiler cũng có thể suy luận giới hạn ấy thay vì `Object` khi thiếu ràng buộc khác. Do đó, không nên phát biểu máy móc rằng “mọi collection rỗng dưới `var` đều có kiểu `Object`”.

## 7. Suy luận kiểu không phụ thuộc vào thao tác `add` trong tương lai

Ví dụ:

~~~java
var users = new ArrayList<>(); // ArrayList<Object>
users.add("An");               // OK
users.add("Binh");             // OK
// users bây giờ vẫn là ArrayList<Object>
~~~

Dù có hai phần tử đều là String, generic type đã chốt ở thời điểm **khai báo**. Nếu sau đó có:

~~~java
void sendNames(List<String> names) {
    // xử lý tên
}
~~~

thì `sendNames(users)` **không biên dịch**, vì `ArrayList<Object>` không chuyển được thành `List<String>`. Nói “danh sách hiện chỉ chứa String” không thay thế được hợp đồng kiểu. Để sửa, hãy thay câu lệnh khai báo ngay từ đầu bằng `List<String> users = new ArrayList<>();` hoặc `var users = new ArrayList<String>();`.

Cũng không nên sử dụng unchecked cast `(List<String>) (List<?>) users` chỉ để qua compiler. Cast kiểu này có thể che giấu dữ liệu không tương thích và dẫn đến lỗi khi phần tử được đọc như String. Chọn lại thiết kế kiểu đúng hoặc chuyển đổi từng phần tử với kiểm tra thực tế nếu đang xử lý nguồn dữ liệu không tin cậy.

## 8. Rỗng, không cho sửa và generic type là ba khái niệm khác nhau

| Ví dụ | Kiểu tham chiếu theo khai báo | Có thể thêm phần tử qua list? | Ban đầu rỗng? |
| --- | --- | --- | --- |
| `var a = new ArrayList<>();` | `ArrayList<Object>` | Có | Có |
| `var a = new ArrayList<String>();` | `ArrayList<String>` | Có | Có |
| `var a = List.of();` | `List<Object>` | Không | Có |
| `var a = List.<String>of();` | `List<String>` | Không | Có |
| `List<String> a = new ArrayList<>();` | `List<String>` | Có, nếu instance còn mutable | Có |
| `List<String> a = Collections.emptyList();` | `List<String>` | Không | Có |

`var a = List.of();` có kiểu `List<Object>` nhưng **không** có nghĩa `a.add("x")` hoạt động: lệnh `add` có thể vượt kiểm tra kiểu ở compile time (`String` là `Object`) nhưng sẽ ném `UnsupportedOperationException` ở runtime vì danh sách không cho sửa.

Ngược lại, `var a = new ArrayList<String>();` có kiểu generic đúng `String` và cho phép thêm/bớt phần tử vì ArrayList mutable. **Generic type** kiểm soát kiểu phần tử, còn **mutability** do hợp đồng implementation/API quyết định.

Một collection có generic type đúng cũng không nhất thiết immutable sâu: `List<MutableUser>` có thể là unmodifiable list nhưng vẫn chứa đối tượng `MutableUser` có state sửa được. Không nhầm vấn đề này với type inference.

## 9. Ví dụ hoàn chỉnh, biên dịch/chạy được với Java 17+

Lưu mã sau vào tệp **`EmptyCollectionsInference.java`**. Chương trình dùng các phép gán kiểm tra kiểu (`List<Object>`, `List<String>`, `Map<String,Integer>`) để trình biên dịch xác nhận suy luận; lời gọi `acceptStrings` chỉ chấp nhận danh sách phần tử String.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Stream;

public class EmptyCollectionsInference {
    enum Level { LOW, HIGH }

    static List<String> readNothing() {
        return List.of();
    }

    static void acceptStrings(List<String> words) {
        System.out.println("acceptedStrings=" + words.size());
    }

    public static void main(String[] args) {
        var mixed = new ArrayList<>();
        List<Object> checkedMixed = mixed;
        mixed.add("Java");
        mixed.add(10);
        System.out.println("mixed=" + checkedMixed);

        var emptyFactory = List.of();
        List<Object> checkedFactory = emptyFactory;
        System.out.println("emptyFactory=" + checkedFactory.size());

        var typed = new ArrayList<String>();
        typed.add("typed");
        acceptStrings(typed);

        List<String> target = new ArrayList<>();
        target.add("target");
        System.out.println("target=" + target);

        var typedEmpty = List.<String>of();
        acceptStrings(typedEmpty);
        var typedFromCollections = Collections.<String>emptyList();
        acceptStrings(typedFromCollections);

        var seeded = new ArrayList<>(List.of("alpha", "beta"));
        acceptStrings(seeded);
        System.out.println("seeded=" + seeded);

        var blankSeed = new ArrayList<>(List.<String>of());
        blankSeed.add("later");
        acceptStrings(blankSeed);
        System.out.println("blankSeed=" + blankSeed);

        var fromMethod = readNothing();
        acceptStrings(fromMethod);

        var capacityZero = new ArrayList<Integer>(0);
        capacityZero.add(42);
        System.out.println("capacityZero=" + capacityZero);

        var mixedMap = new HashMap<>();
        Map<Object, Object> checkedMap = mixedMap;
        checkedMap.put("one", 1);
        checkedMap.put(2, "two");
        System.out.println("mixedMapSize=" + mixedMap.size());

        var typedMap = Map.<String, Integer>of();
        Map<String, Integer> checkedTypedMap = typedMap;
        System.out.println("typedMapSize=" + checkedTypedMap.size());

        var emptySet = Set.of();
        Set<Object> checkedEmptySet = emptySet;
        System.out.println("emptySetSize=" + checkedEmptySet.size());

        var none = Optional.<String>empty();
        var unknown = Optional.empty();
        Optional<String> checkedNone = none;
        Optional<Object> checkedUnknown = unknown;
        System.out.println("optionalsEmpty=" +
                (checkedNone.isEmpty() && checkedUnknown.isEmpty()));

        var streamResult = Stream.<String>empty().toList();
        acceptStrings(streamResult);

        var array = new String[0];
        String[] typedArray = array;
        System.out.println("arrayLength=" + typedArray.length);

        var enumSet = EnumSet.noneOf(Level.class);
        EnumSet<Level> checkedEnumSet = enumSet;
        System.out.println("enumSetSize=" + checkedEnumSet.size());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac --release 17 EmptyCollectionsInference.java
java EmptyCollectionsInference
~~~

**Stdout chính xác** khi chạy chương trình:

~~~text
mixed=[Java, 10]
emptyFactory=0
acceptedStrings=1
target=[target]
acceptedStrings=0
acceptedStrings=0
acceptedStrings=2
seeded=[alpha, beta]
acceptedStrings=1
blankSeed=[later]
acceptedStrings=0
capacityZero=[42]
mixedMapSize=2
typedMapSize=0
emptySetSize=0
optionalsEmpty=true
acceptedStrings=0
arrayLength=0
enumSetSize=0
~~~

Các điểm cần quan sát:

- `mixed` đã được suy luận `ArrayList<Object>`, nên phần tử String và Integer cùng được thêm; phép gán `List<Object> checkedMixed = mixed` biên dịch.
- `emptyFactory` được kiểm chứng là `List<Object>` qua phép gán có kiểu tường minh, dù không có phần tử.
- `typed`, `typedEmpty`, `typedFromCollections`, `seeded`, `blankSeed` và `fromMethod` đều đi qua `acceptStrings(List<String>)` mà không lỗi biên dịch. Các trường hợp này có nguồn thông tin kiểu rõ ràng.
- `blankSeed` minh họa collection nguồn **rỗng** nhưng đã được chỉ định `String` bằng type witness, cho phép constructor suy luận `ArrayList<String>`.
- `capacityZero` có kiểu `ArrayList<Integer>` vì constructor viết tường minh `Integer`, không phải vì dung lượng bằng 0.
- `mixedMap` là `HashMap<Object,Object>`; `Map.<String,Integer>of()` trả Map có cặp kiểu xác định ngay cả khi rỗng.
- `Optional.<String>empty()` và `Optional.empty()` khác nhau ở type argument mặc dù cả hai đều không chứa giá trị.
- `Stream.<String>empty().toList()` tạo `List<String>` không cho sửa; `EnumSet.noneOf(Level.class)` và `new String[0]` cũng giữ kiểu cụ thể dù không có phần tử.

Các biến tên `checked...` và phương thức `acceptStrings` là **kiểm chứng compile-time**, không dùng reflection để khẳng định type parameter khi chạy vì Java generics có type erasure.

## 10. Ví dụ lỗi biên dịch: ghi nhận rõ để tránh áp dụng sai

Các đoạn sau là **minh họa có dòng lỗi**, không phải chương trình chạy độc lập. Dòng lỗi được comment và phần giải thích mô tả điều gì xảy ra nếu bỏ comment.

### 10.1. Tưởng `List<Object>` được coi như `List<String>`

~~~java
var names = new ArrayList<>();         // ArrayList<Object>
// List<String> typedNames = names;    // LỖI: incompatible types
List<Object> typedObjects = names;     // OK
~~~

Không có sự chuyển ngầm từ `List<Object>` sang `List<String>` vì generic invariant.

### 10.2. Tưởng phần tử được thêm sẽ đổi generic type

~~~java
var names = new ArrayList<>(); // ArrayList<Object>
names.add("An");
// acceptStrings(names);       // LỖI nếu acceptStrings yêu cầu List<String>
~~~

Dù `names` hiện chỉ có phần tử String, kiểu vẫn là `ArrayList<Object>`.

### 10.3. Tưởng factory unmodifiable có thể thêm phần tử

~~~java
var names = List.<String>of(); // List<String>
// names.add("An");            // BIÊN DỊCH ĐƯỢC, nhưng runtime ném UnsupportedOperationException
~~~

Kiểu generic đúng không làm danh sách trở thành mutable.

### 10.4. Tưởng diamond và raw type tương đương

~~~java
var safe = new ArrayList<>(); // ArrayList<Object>, vẫn có generic checking
var raw = new ArrayList();    // raw ArrayList, không ghi type argument
~~~

Raw type có thể tạo lời gọi unchecked trong các trường hợp chuyển sang parameterized type. Trong code mới, chỉ dùng kiểu có type argument cụ thể và tránh raw collection.

### 10.5. Tưởng `var` đoán kiểu từ tên biến hoặc phương thức sử dụng sau

~~~java
var stringList = new ArrayList<>(); // vẫn là ArrayList<Object>
// saveStrings(stringList);          // lỗi nếu saveStrings nhận List<String>
~~~

Tên `stringList` không được Java dùng làm đầu vào suy luận kiểu. Cần viết `List<String> stringList = new ArrayList<>();`, hoặc `var stringList = new ArrayList<String>();`.

## 11. Áp dụng trong thiết kế API và công việc hằng ngày

### 11.1. Tạo danh sách để thu thập kết quả

Khi biết rõ kiểu phần tử sẽ lưu, ưu tiên:

~~~java
List<String> errors = new ArrayList<>();
for (var errorCode : List.of("E01", "E02")) {
    errors.add(errorCode);
}
~~~

Hoặc nếu phạm vi cục bộ thật sự cần kiểu implementation:

~~~java
var errors = new ArrayList<String>();
~~~

Tránh `var errors = new ArrayList<>();` nếu muốn chắc chắn không thể thêm nhầm `Integer` hay truyền sai kiểu vào API yêu cầu `List<String>`.

### 11.2. Trả kết quả rỗng từ service/repository

API nên khai báo hợp đồng:

~~~java
public List<String> findNames() {
    return List.of(); // target type của return là List<String>
}
~~~

Caller:

~~~java
var names = findNames(); // List<String>, kể cả khi kết quả hiện đang rỗng
~~~

Đây là tình huống `var` rất hợp lý: chữ ký phương thức thể hiện kiểu cụ thể, caller không cần lặp `List<String>`. Nên giữ generic type chính xác ở ranh giới module, tránh trả raw `List` hoặc `List<Object>` khi domain thực sự là `String`.

### 11.3. Khởi tạo empty constant hoặc giá trị mặc định

~~~java
private static final List<String> EMPTY_TAGS = List.of();
private static final Map<String, Integer> EMPTY_COUNTS = Map.of();
~~~

Với field, dùng kiểu khai báo tường minh vì Java **không hỗ trợ** `var` làm kiểu field. Dùng các immutable factory để cung cấp giá trị mặc định; khi cần collection mutable, hãy tạo `new ArrayList<>()` với kiểu mục tiêu rõ ràng.

### 11.4. Chọn kiểu để nhận dữ liệu không đồng nhất

`List<Object>` có chỗ dùng hợp lệ, ví dụ bộ dữ liệu thật sự chứa các loại phần tử khác nhau và API có xử lý phân biệt kiểu. Nhưng không nên vô tình nhận `Object` chỉ vì khai báo rỗng thiếu thông tin:

~~~java
List<Object> mixedValues = new ArrayList<>(); // chủ động khai báo hỗn hợp
List<String> userNames = new ArrayList<>();   // chủ động khai báo tên người
~~~

Việc dùng `var` với factory rỗng mà không kiểm tra type thường làm lộ vấn đề khi tích hợp API ở bước sau, khó phát hiện hơn so với viết rõ hợp đồng ngay tại điểm khai báo.

### 11.5. Kiểm soát mutability độc lập với type inference

Chọn cấu trúc phù hợp mục đích:

- `List<String> collected = new ArrayList<>();`: danh sách có thể bổ sung.
- `List<String> empty = List.of();`: danh sách rỗng không cho sửa.
- `List<String> snapshot = List.copyOf(collected);`: tạo danh sách không cho sửa, giữ cấu trúc tại thời điểm sao chép từ nguồn có thể sửa.
- `var snapshot = List.copyOf(collected);`: cũng có kiểu `List<String>` vì `collected` đã mang type parameter `String`.

Lưu ý `List.copyOf` không tạo deep copy của phần tử mutable; đây là vấn đề thiết kế tính bất biến, không làm thay đổi suy luận `String` của ví dụ trên.

### 11.6. Chỉ định kiểu cho stream/Optional ngay từ đầu nếu rỗng

~~~java
var noUsers = Optional.<String>empty();
var noEvents = Stream.<String>empty().toList();
~~~

Khi cần truyền kết quả vào API nhận `Optional<String>`/`List<String>`, type witness sẽ bảo đảm đúng generic type. Nếu đã có chữ ký phương thức trả các kiểu đó, target typing trong `return Optional.empty();` hay `return List.of();` cũng hoạt động.

## 12. Bảng nhanh trước khi review pull request

| Tình huống | Nên chọn | Lý do |
| --- | --- | --- |
| Local collection rỗng để thêm String | `List<String> xs = new ArrayList<>();` | Có target type rõ, không cho thêm sai loại |
| Muốn `var` và mutable ArrayList<String> | `var xs = new ArrayList<String>();` | Constructor cung cấp `T` |
| Muốn `var` và empty List<String> unmodifiable | `var xs = List.<String>of();` | Factory có type witness |
| Có nguồn `Collection<String>`, tạo bản copy mutable | `var xs = new ArrayList<>(source);` | Constructor nhận đủ kiểu từ nguồn |
| Lấy List<String> từ method | `var xs = loadNames();` | Kiểu trả về method quyết định |
| Empty Map key String/value Integer | `Map<String,Integer> map = new HashMap<>();` | Khóa và giá trị đều được ràng buộc |
| Empty Set<String> | `Set<String> tags = Set.of();` | Target type và tính unmodifiable rõ |
| Empty Optional<String> | `Optional<String> value = Optional.empty();` | Target type định rõ tham số generic |
| Array dài 0 của String | `var xs = new String[0];` | Component type đã viết rõ |
| Rỗng vì capacity = 0 | `var xs = new ArrayList<String>(0);` | Capacity không giúp suy luận generic |
| Cần thật sự chứa nhiều loại object | `List<Object> xs = new ArrayList<>();` | Thể hiện chủ ý, không vô tình suy luận rộng |

## 13. Bài tập tự kiểm tra và đáp án

**Bài 1.** `var numbers = new ArrayList<>();` có kiểu gì? Thêm `numbers.add(10)` có biến nó thành `ArrayList<Integer>` không?

**Đáp án:** `ArrayList<Object>`. `add` không thay đổi type parameter; đây là thao tác trên object sau khi compiler đã chốt kiểu biến.

**Bài 2.** Vì sao `List<String> labels = List.of();` hợp lệ nhưng `var labels = List.of();` không suy luận `String`?

**Đáp án:** Khai báo đầu có target type `List<String>`; khai báo `var` không đưa ra target type, factory rỗng thiếu phần tử để ràng buộc `T` và thường chọn `Object`.

**Bài 3.** `var labels = List.<String>of();` có kiểu gì? Có gọi `labels.add("A")` thành công không?

**Đáp án:** `List<String>`. Lời gọi `add` có thể vượt kiểm tra kiểu nhưng runtime ném `UnsupportedOperationException` vì danh sách không cho sửa cấu trúc.

**Bài 4.** `var labels = new ArrayList<>(List.of("A", "B"));` có kiểu gì?

**Đáp án:** `ArrayList<String>`. Phần tử chuỗi trong constructor argument cung cấp thông tin cho suy luận `T`.

**Bài 5.** `var labels = new ArrayList<>(List.<String>of());` có thể thêm String không?

**Đáp án:** Có. Đối số List rỗng đã được gắn `String`, nên constructor suy luận `ArrayList<String>`, là một mutable ArrayList.

**Bài 6.** `var ids = new ArrayList<>(0);` có kiểu gì? Số 0 có nói rằng kiểu phần tử là `Integer` không?

**Đáp án:** `ArrayList<Object>`. `0` là tham số initial capacity, không phải phần tử hay tham số kiểu.

**Bài 7.** `var flags = Set.of();` và `var flags2 = Set.<String>of();` khác nhau ra sao?

**Đáp án:** `flags: Set<Object>`; `flags2: Set<String>`. Cả hai đều rỗng và unmodifiable.

**Bài 8.** `var counters = new HashMap<>();` có kiểu gì và khắc phục thế nào nếu API cần `Map<String,Integer>`?

**Đáp án:** `HashMap<Object,Object>`. Khai báo `Map<String,Integer> counters = new HashMap<>();` hoặc `var counters = new HashMap<String,Integer>();`.

**Bài 9.** `var names = readNothing();` có kiểu gì nếu method `readNothing()` khai báo trả `List<String>` nhưng trả `List.of()`?

**Đáp án:** `List<String>`. Caller sử dụng kiểu trả về trong method signature; trong thân method, `return List.of();` có target type `List<String>`.

**Bài 10.** `var names = new String[0];` có kiểu `Object[]` hay `String[]`?

**Đáp án:** `String[]` vì biểu thức tạo mảng chỉ rõ component type String. Độ dài rỗng không làm mất thông tin đó.

**Bài 11.** `var none = Optional.empty();` và `var noneString = Optional.<String>empty();` có khác nhau về giá trị không?

**Đáp án:** Cả hai đều là Optional rỗng, nhưng kiểu suy luận lần lượt là `Optional<Object>` và `Optional<String>`. Khác biệt thể hiện khi giao tiếp với API đòi type parameter cụ thể.

**Bài 12.** Tại sao `var mixed = new ArrayList<>(); mixed.add("A");` không thể truyền an toàn cho `method(List<String>)`?

**Đáp án:** Vì `mixed` vẫn là `ArrayList<Object>`. Java không cho chuyển ngầm sang `List<String>`, dù dữ liệu thực tế hiện tại chỉ có String; generic type được kiểm tra tại compile time.

**Bài 13.** `EnumSet.noneOf(Level.class)` trả danh sách/tập rỗng, vậy `var levels = ...` có suy luận `EnumSet<Object>` không?

**Đáp án:** Không. Phương thức nhận `Level.class` làm thông tin kiểu, nên kết quả là `EnumSet<Level>`. Đây là phản ví dụ quan trọng đối với việc khái quát “collection rỗng luôn suy ra Object”.

**Bài 14.** Hai dòng nào diễn đạt rõ mong muốn tạo List<String> mutable rỗng?

~~~java
var a = new ArrayList<>();
List<String> b = new ArrayList<>();
var c = new ArrayList<String>();
~~~

**Đáp án:** `b` và `c`. `a` là ArrayList<Object> do không có target type hoặc đối số ràng buộc `String`.

## 14. Tài liệu chính thức để tra cứu

1. [JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286): giải thích `var` và nguyên tắc initializer được định kiểu như biểu thức standalone.
2. [OpenJDK – Style Guidelines for Local Variable Type Inference](https://openjdk.org/projects/amber/guides/lvti-style-guide): khuyến nghị tránh kết hợp `var` với diamond/generic factory khi thiếu thông tin kiểu, ví dụ `new ArrayList<>()` và `List.of()`.
3. [Dev.java – Type Inference](https://dev.java/learn/generics/type-inference/): target type, diamond, generic method và type witness.
4. [Java Language Specification – Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): quy tắc khai báo và suy luận kiểu cho local variable.
5. [Java Language Specification – Type Inference](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html): quy tắc inference, type constraints và các ngữ cảnh của generic method/constructor.
6. [Java SE API – List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): `List.of`, `List.copyOf` và quy tắc unmodifiable.
7. [Java SE API – Collections](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html): `Collections.emptyList` và các utility collection.
8. [Java SE API – Optional](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): `Optional.empty` và thao tác với Optional.

**Ghi nhớ:** Một collection rỗng không làm mất generic type một cách tự động. Điều gây ra kiểu quá rộng thường là **không đủ thông tin trong biểu thức khởi tạo và không có target type khi dùng `var`**. Hãy viết rõ `T` ở nơi có thể (khai báo, constructor, type witness, method signature hoặc đối số đã có kiểu) để API và compiler tiếp tục bảo vệ kiểu dữ liệu chính xác.
