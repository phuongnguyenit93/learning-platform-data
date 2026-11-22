# Toán tử diamond `<>` và khác biệt với raw type trong Java

## 1. Vấn đề cần giải quyết

Generics giúp trình biên dịch kiểm tra kiểu phần tử trong collection hoặc lớp tổng quát. Khi khởi tạo đối tượng generic, Java có hai cách viết có vẻ giống nhau nhưng **khác nhau về độ an toàn kiểu**:

```java
List<String> names = new ArrayList<>(); // Diamond: trình biên dịch suy luận String.
List<String> old   = new ArrayList();   // Raw type: bỏ tham số kiểu, cảnh báo unchecked.
```

Ở dòng thứ nhất, `<>` là **toán tử diamond**: danh sách được khởi tạo với tham số kiểu suy luận từ ngữ cảnh (`String`). Ở dòng thứ hai, `new ArrayList()` là **raw type**: constructor được gọi thông qua kiểu `ArrayList` không tham số hóa. Dòng đó vẫn có thể biên dịch để hỗ trợ tương thích mã Java cũ, nhưng mất một phần kiểm tra kiểu và sinh cảnh báo về phép chuyển đổi không kiểm tra được.

Mục tiêu sau bài học:

- Nhận diện rõ `List<String>`, `new ArrayList<String>()`, `new ArrayList<>()`, `new ArrayList()` và `List<?>`.
- Hiểu `<>` suy luận kiểu **khi biên dịch** từ ngữ cảnh như khai báo biến, tham số phương thức hoặc kiểu trả về.
- Nhìn ra lý do raw type tạo cảnh báo `rawtypes`, `unchecked` và nguy cơ **heap pollution / ClassCastException**.
- Biết dùng diamond trong code Java 17+, phân biệt trường hợp có target type với khai báo bằng `var`, và chuyển dần mã legacy sang API an toàn kiểu.

`<>` được đưa vào Java 7 để giảm việc lặp lại tham số kiểu ở biểu thức `new`. Diamond vẫn tuân theo toàn bộ quy tắc của generics, không biến Java thành ngôn ngữ có kiểu động.

## 2. Năm cách viết dễ nhầm lẫn

| Cú pháp | Ý nghĩa | Có kiểm tra kiểu generic? |
| --- | --- | --- |
| `List<String> a` | Biến có kiểu phần tử `String` | Có |
| `new ArrayList<String>()` | Khởi tạo và chỉ định tường minh `String` | Có |
| `new ArrayList<>()` | Khởi tạo, để trình biên dịch **suy luận** tham số kiểu | Có |
| `new ArrayList()` | Sử dụng **raw type**, bỏ hẳn tham số kiểu | Không đầy đủ; có thể sinh cảnh báo |
| `List<?> any` | List của một kiểu chưa biết, nhưng vẫn là **parameterized type** | Có; giới hạn thao tác ghi để bảo vệ an toàn kiểu |

Hai dòng đầu dưới đây tương đương về hợp đồng generic mà biến `names` nhìn thấy:

```java
// Các câu lệnh này có thể đặt trong một phương thức Java.
List<String> names1 = new ArrayList<String>();
List<String> names2 = new ArrayList<>();
names1.add("Lan");
names2.add("Minh");
// names2.add(42); // Lỗi biên dịch vì List<String> không nhận Integer.
```

Diamond **không phải** chuỗi ký hiệu bỏ tham số kiểu như raw type. `new ArrayList<>()` yêu cầu trình biên dịch giải bài toán suy luận tham số kiểu cho lớp `ArrayList<E>`; kết quả vẫn được kiểm tra như một biểu thức generic. Trong khi đó `new ArrayList()` chọn cách dùng raw `ArrayList`, với các chữ ký generic được nhìn dưới dạng đã xóa tham số kiểu.

Một điểm đáng nhớ: type ở **vế trái** và type ở **vế phải** đều quan trọng.

```java
List<String> safe = new ArrayList<>(); // Hai phía giữ ràng buộc String.
List<String> weak = new ArrayList();   // Phép gán unchecked từ raw sang List<String>.
List raw = new ArrayList<>();          // Biến raw vẫn cho phép gọi add không kiểm tra.
```

Ở dòng cuối, diamond của biểu thức `new` **không thể làm biến `raw` trở nên an toàn**: nơi sử dụng biến vẫn chỉ biết nó là `List` raw. Đây là lý do phải kiểm tra chữ ký biến, tham số và giá trị trả về trong cả luồng dữ liệu.

## 3. Diamond hoạt động như thế nào?

Một kiểu tổng quát khai báo các **tham số kiểu**, ví dụ `ArrayList<E>` hay `Map<K,V>`. Với biểu thức tạo đối tượng `new ArrayList<>()`, dấu `<>` báo cho compiler suy luận `E` từ các ràng buộc có sẵn.

### 3.1. Suy luận từ kiểu đích của biến

```java
List<String> letters = new ArrayList<>();
Set<Long> ids = new HashSet<>();
Map<String, Integer> ages = new HashMap<>();
```

Compiler kiểm tra xem constructor có thể tạo biểu thức tương thích với `List<String>`, `Set<Long>` và `Map<String,Integer>` hay không. Các tham số kiểu ở phía phải thường không cần lặp lại vì phía trái đã cung cấp ràng buộc.

Lưu ý: diamond không có nghĩa compiler luôn lấy đúng ký tự ở vế trái rồi thay thế máy móc. Suy luận kiểu còn phụ thuộc constructor, kiểu tham số truyền vào, cách sử dụng và các ràng buộc tương thích của Java.

### 3.2. Suy luận từ tham số phương thức

```java
// Đoạn trong một lớp Java, giả sử đã import java.util.*.
static void acceptNames(List<String> names) {
    System.out.println(names.size());
}

// Trong một phương thức khác:
acceptNames(new ArrayList<>());
```

Lời gọi có ngữ cảnh đích `List<String>` từ chữ ký `acceptNames`, nên `new ArrayList<>()` có thể được suy luận phù hợp. Không nhất thiết phải gán vào biến trung gian.

### 3.3. Suy luận từ kiểu trả về

```java
static Map<String, List<Integer>> emptyGrades() {
    return new HashMap<>();
}
```

Ngữ cảnh `return` cung cấp kiểu đích `Map<String,List<Integer>>`; compiler kiểm tra được biểu thức trả về. Với phương thức generic, suy luận của lời gọi phương thức và của constructor có thể tương tác, nhưng đó là hai quy tắc cú pháp khác nhau.

### 3.4. Generic lồng nhau: viết gọn mà vẫn rõ kiểu

```java
Map<String, List<Integer>> grades = new LinkedHashMap<>();
grades.put("Lan", new ArrayList<>());
grades.get("Lan").add(8);
grades.get("Lan").add(9);
// grades có dữ liệu tương ứng "Lan" -> [8, 9].
```

Compiler suy luận `Map<String,List<Integer>>` cho `LinkedHashMap<>` và có thể suy luận `ArrayList<Integer>` cho lời gọi `put` vì tham số thứ hai được yêu cầu tương thích với `List<Integer>`. Hệ thống generics vẫn kiểm tra chiều sâu của collection lồng nhau.

### 3.5. Đưa dữ liệu constructor vào suy luận

```java
List<String> names = new ArrayList<>(List.of("Lan", "Mai"));
Map<String, Integer> ages =
        new HashMap<>(Map.of("Lan", 20, "Mai", 21));
```

Compiler kết hợp kiểu đích và đối số constructor. `List.of`/`Map.of` trong ví dụ là các **generic static factory method**; chúng tự suy luận tham số kiểu của phương thức. Chúng **không dùng diamond**; diamond là cú pháp liên quan đến khởi tạo đối tượng với `new`.

## 4. Diamond và `var`: khi không còn kiểu đích tường minh

Từ Java 10, `var` cho phép compiler suy luận kiểu **biến cục bộ** từ biểu thức khởi tạo. Điều này tạo tình huống khác với `List<String> names = ...`:

```java
var a = new ArrayList<>();         // a là ArrayList<Object>.
a.add("Java");                     // Hợp lệ.
a.add(2026);                       // Cũng hợp lệ vì kiểu phần tử là Object.

var b = new ArrayList<String>();   // b là ArrayList<String>.
b.add("Java");
// b.add(2026);                    // Lỗi biên dịch.
```

Khi viết `var a = new ArrayList<>()` và không có dữ liệu/kiểu đích hữu ích, compiler suy luận đối số kiểu không bị ràng buộc thành `Object`. Đây vẫn là một **parameterized type** (`ArrayList<Object>`), **không phải raw type** (`ArrayList`). Sự khác biệt nằm ở chỗ danh sách `Object` có thể chứa nhiều kiểu tham chiếu theo đúng hợp đồng, còn raw type bỏ qua thông tin tham số kiểu và có thể phá vỡ hợp đồng của một danh sách vốn được khai báo là `List<String>`.

Cách viết nên chọn nếu cần một list chuỗi với `var`:

```java
var names = new ArrayList<String>();
names.add("Lan");
```

Nếu muốn ẩn implementation bằng giao diện, dùng khai báo tường minh:

```java
List<String> names = new ArrayList<>();
```

Cách thứ hai thường giúp API dễ đổi từ `ArrayList` sang implementation khác và thể hiện yêu cầu chỉ lưu `String` ngay tại khai báo.

**Không suy đoán `var` tương đương `Object` ở mọi trường hợp.** Ví dụ `var names = List.of("Lan")` thường suy luận `List<String>` nhờ kiểu trả về và đối số của generic factory `List.of`. Vấn đề cụ thể là `new ArrayList<>()` không có ràng buộc đủ cụ thể khi đặt ngay sau `var`.

## 5. Raw type: di sản tương thích với Java trước generics

Trước Java 5, các collection như `List` và `ArrayList` chưa có tham số kiểu. Khi generics xuất hiện, Java vẫn cho phép dạng raw để mã cũ tiếp tục làm việc:

```java
List legacy = new ArrayList();
legacy.add("hello");
legacy.add(42);
Object item = legacy.get(0);
```

Raw type thường xóa kiểm tra compile-time rằng một phần tử phải là `String`, `Integer` hay một kiểu cụ thể. Sau đó người dùng có thể phải cast từ `Object`, với lỗi runtime nếu giá trị thực không tương thích.

Ngược lại, phiên bản generic sau cung cấp kiểm tra trước khi chạy:

```java
List<String> messages = new ArrayList<>();
messages.add("hello");
// messages.add(42);       // Lỗi ngay lúc biên dịch.
String item = messages.get(0); // Không cần cast thủ công.
```

### 5.1. Heap pollution: một biến nhìn thấy kiểu sai về nội dung

*Heap pollution* là tình huống một biến của kiểu có tham số hóa trỏ đến dữ liệu không phù hợp với tham số kiểu đó. Raw type là một con đường phổ biến gây ra vấn đề này:

```java
List<String> words = new ArrayList<>();
words.add("Java");

List raw = words;       // Truy cập cùng đối tượng qua biến raw.
raw.add(99);            // Cảnh báo unchecked, nhưng có thể chạy.

String second = words.get(1); // Ném ClassCastException lúc chạy.
```

Điểm nguy hiểm là `words` vẫn có kiểu khai báo `List<String>`, nhưng biến raw đã lén thêm `Integer` vào cùng một đối tượng danh sách. Biểu thức đọc phần tử thông qua `words.get(1)` khiến compiler chèn cast thích hợp; cast đó thất bại khi gặp `Integer`.

Khi chạy `javac -Xlint:rawtypes -Xlint:unchecked`, ta có thể thấy hai nhóm cảnh báo:

- `[rawtypes]`: khai báo hoặc sử dụng một kiểu generic ở dạng raw, chẳng hạn `List raw`.
- `[unchecked]`: thao tác mà compiler không thể xác minh tính đúng đắn của tham số kiểu, chẳng hạn `raw.add(99)` hoặc gán raw list cho `List<String>`.

Cảnh báo không phải sự bảo đảm rằng code sẽ tự động sửa dữ liệu. Nó đánh dấu một vị trí người phát triển phải kiểm tra.

### 5.2. Raw type trong vế phải cũng nguy hiểm

```java
List<String> names = new ArrayList();  // Unchecked conversion.
names.add("Lan");
```

Compiler có thể cho phép phép gán nhằm tương thích với mã cũ, nhưng constructor ở đây không truyền thông tin generic qua biểu thức. Việc loại bỏ cảnh báo đúng cách là dùng `new ArrayList<>()` hoặc `new ArrayList<String>()`. Không nên chỉ thêm `@SuppressWarnings("unchecked")` vì annotation đó không phục hồi kiểm tra kiểu.

### 5.3. Raw type không mang lại lợi ích tốc độ hay bộ nhớ

Generics Java chủ yếu được triển khai bằng **type erasure**: biểu diễn runtime thông thường dùng chung lớp `ArrayList` cho `ArrayList<String>` và `ArrayList<Integer>`. Do đó raw type không phải một lựa chọn tối ưu hiệu năng; chọn raw thường chỉ làm mất thông tin phục vụ kiểm tra lúc biên dịch.

```java
boolean sameClass =
    new ArrayList<String>().getClass() == new ArrayList<Integer>().getClass();
// sameClass là true.
```

Type erasure cũng giải thích vì sao không thể dùng `instanceof List<String>` để xác minh tham số `String` ở runtime. Khi cần kiểm tra có phải một loại list, `instanceof List<?>` là phép kiểm tra hợp lệ; việc kiểm tra các phần tử thực tế phải thực hiện riêng khi cần.

## 6. Đừng nhầm `<>`, `<?>` và kiểu raw

Ba cách viết có ngoặc nhọn góc nhưng ý nghĩa khác nhau:

```java
List<String> strings = new ArrayList<>(); // Diamond: suy luận kiểu khi new.
List<?> unknown = strings;               // Wildcard: có kiểu phần tử chưa biết.
List raw = strings;                      // Raw: loại bỏ thông tin tham số kiểu.
```

Với `List<?>`, compiler vẫn bảo vệ an toàn kiểu:

```java
Object value = unknown.get(0);  // Hợp lệ: đọc như Object.
// unknown.add("more");         // Lỗi biên dịch: không biết kiểu phần tử.
// unknown.add(42);             // Lỗi biên dịch.
unknown.add(null);              // Hợp lệ với chữ ký add, nếu implementation cho phép null.
```

Lưu ý: `List<?>` không đồng nghĩa `List<Object>`. Với `List<Object>`, bạn có thể thêm bất kỳ giá trị tham chiếu tương thích `Object`, nhưng không thể gán trực tiếp `List<String>` cho `List<Object>` vì generics Java là **invariant**:

```java
List<String> names = new ArrayList<>();
List<?> readable = names;       // Hợp lệ.
// List<Object> writable = names; // Lỗi biên dịch.
List<Object> objects = new ArrayList<>();
objects.add("Lan");
objects.add(42);
```

Khi API chỉ cần xem/đọc dữ liệu chưa biết kiểu, `List<?>` thường tốt hơn raw `List`. Khi API cần nhận đối tượng có kiểu cụ thể, hãy mô tả đúng kiểu hoặc dùng wildcard có bound (`? extends T`, `? super T`) tùy thao tác.

| Loại | Đọc phần tử ra | Thêm phần tử | Điều phải nhớ |
| --- | --- | --- | --- |
| `List<String>` | `String` | `String` | Kiểm tra kiểu đầy đủ. |
| `List<Object>` | `Object` | Mọi đối tượng tham chiếu | Vẫn là generic, không phải raw. |
| `List<?>` | `Object` | Không thêm đối tượng cụ thể; `null` được phép về mặt kiểu | An toàn cho truy cập kiểu chưa biết. |
| `List` raw | `Object` | Gọi `add` không kiểm tra generic, thường có unchecked warning | Có thể làm hỏng hợp đồng của biến generic khác. |

## 7. Diamond hợp lệ ở đâu và không hợp lệ ở đâu?

Diamond là **danh sách tham số kiểu rỗng tại biểu thức khởi tạo lớp generic**:

```java
List<String> a = new ArrayList<>(); // Hợp lệ.
Map<String, Integer> b = new HashMap<>(); // Hợp lệ.
// List<> c = new ArrayList<>();      // Sai: phía khai báo phải có kiểu.
// List<String> d = new List<>();     // Sai: List là interface, không thể new.
```

`<>` không viết ở mọi vị trí dùng generics. Khi khai báo lớp/phương thức, phải đặt **tên tham số kiểu**:

```java
class Holder<T> {
    private final T value;
    Holder(T value) { this.value = value; }
    T get() { return value; }
}

static <T> List<T> singleton(T item) {
    return new ArrayList<>(List.of(item));
}
```

Khi gọi phương thức generic, trình biên dịch thường suy luận kiểu từ đối số và ngữ cảnh, không dùng cú pháp `method<>()`:

```java
List<String> one = singleton("Java");  // Suy luận T = String.
// List<String> wrong = singleton<> ("Java"); // Không có diamond ở đây.
List<String> empty = Collections.<String>emptyList(); // Chỉ định type witness.
```

Điều kiện và giới hạn bổ sung:

1. Diamond dùng khi **constructor tạo lớp phù hợp**, không thể tạo trực tiếp interface hay abstract class.
2. Kiểu tham số generic chỉ nhận **reference type**: `new ArrayList<Integer>()` hợp lệ, `new ArrayList<int>()` không hợp lệ. Boxing và unboxing hỗ trợ khi đưa số nguyên vào `List<Integer>`.
3. Diamond không vượt qua giới hạn bound: ví dụ lớp `NumericBox<T extends Number>` không thể được tạo thành `NumericBox<String>` bằng cách dùng `<>`.
4. Java 7 cho phép diamond với constructor không tạo anonymous class; từ **Java 9** có thể dùng diamond cùng anonymous class với các ràng buộc về kiểu suy luận. Với code hiện đại, chỉ dùng biến thể anonymous class nếu thực sự cần và hiểu giới hạn; lambda hoặc implementation có tên thường dễ đọc hơn.
5. Đừng dựa vào diamond để che một kiểu khó hiểu: khi inference gây lỗi hoặc làm code mất rõ ràng, khai báo kiểu tường minh ở vế trái, thêm đối số kiểu rõ ràng ở `new`, hoặc đơn giản hóa các lớp generic lồng nhau.

## 8. Bài toán thực tế: cải thiện API legacy mà không mất an toàn

Giả sử một hàm cũ trả về `List` raw từ thư viện trước Java 5:

```java
// Chỉ minh họa API legacy.
static List loadLegacy() {
    List data = new ArrayList();
    data.add("Lan");
    data.add("Mai");
    return data;
}
```

Cách viết sau có thể biên dịch với cảnh báo, nhưng **không chứng minh** mọi phần tử đều là `String`:

```java
List<String> names = loadLegacy(); // Unchecked conversion.
```

Cách chuyển đổi được kiểm tra ở ranh giới an toàn hơn là nhận `Collection<?>`, duyệt từng phần tử, xác nhận kiểu, rồi đưa vào danh sách mới:

```java
// Đặt bên trong một lớp đã import java.util.*.
static List<String> copyStrings(Collection<?> input) {
    List<String> out = new ArrayList<>();
    for (Object value : input) {
        if (!(value instanceof String s)) {
            throw new IllegalArgumentException("Expected String element");
        }
        out.add(s);
    }
    return out;
}

// List<String> names = copyStrings(loadLegacy());
```

Đoạn này cố ý từ chối cả `null` vì `null instanceof String` là `false`. Nếu hợp đồng dữ liệu cho phép `null`, cần xử lý nó một cách tường minh thay vì vô tình chấp nhận hoặc bỏ qua. Tạo danh sách mới tránh để một alias raw tiếp tục chèn phần tử sai kiểu vào chính danh sách đã kiểm tra.

Khi kiểm soát được mã nguồn legacy, cách sửa tối ưu là cập nhật chữ ký ngay tại nơi khai báo:

```java
static List<String> loadNames() {
    List<String> names = new ArrayList<>();
    names.add("Lan");
    names.add("Mai");
    return names;
}
```

Không cần xóa sạch mọi lời gọi cũ trong một bước; có thể tạo adapter kiểm tra dữ liệu ở ranh giới, sau đó chuyển dần tham số, kiểu trả về và các biến nội bộ sang kiểu generic.

## 9. Chương trình chạy được: diamond, `var` và lỗi raw type

Tạo tệp **`DiamondVsRaw.java`** như sau. Phần raw type được giữ có chủ đích để minh họa rủi ro; các đoạn mới nên ưu tiên generic an toàn.

```java
import java.util.*;

public class DiamondVsRaw {
    static final class Box<T> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        names.add("Minh");
        System.out.println("typed: " + names);

        Box<Integer> score = new Box<>(9);
        System.out.println("box: " + score.get());

        Map<String, List<Integer>> grades = new LinkedHashMap<>();
        grades.put("Lan", new ArrayList<>());
        grades.get("Lan").add(9);
        System.out.println("map: " + grades);

        var noTarget = new ArrayList<>();
        noTarget.add("text");
        noTarget.add(42);
        System.out.println("inferred: " + noTarget);

        List<String> legacy = new ArrayList<>();
        legacy.add("OK");
        List raw = legacy;
        raw.add(123);
        try {
            String value = legacy.get(1);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("raw: ClassCastException");
        }
    }
}
```

Biên dịch trên **JDK 17+**; tùy chọn `-Xlint` yêu cầu compiler chỉ rõ vị trí cảnh báo:

```bash
javac -Xlint:rawtypes -Xlint:unchecked DiamondVsRaw.java
java DiamondVsRaw
```

Khi chạy `javac`, compiler sẽ báo `[rawtypes]` tại `List raw` và `[unchecked]` tại `raw.add(123)`. Diễn đạt đầy đủ/cách đánh số dòng trong cảnh báo phụ thuộc phiên bản compiler; đó là **diagnostics**, không phải stdout của chương trình.

Kết quả stdout của lệnh `java DiamondVsRaw` (đã biên dịch và chạy thử với JDK 21):

```text
typed: [Lan, Minh]
box: 9
map: {Lan=[9]}
inferred: [text, 42]
raw: ClassCastException
```

Diễn giải:

- `names` và `score` nhận ràng buộc generic chính xác. Diamond của `ArrayList<>` và `Box<>` giúp bỏ phần khai báo lặp lại.
- `grades` minh họa diamond cho `Map<String,List<Integer>>` và value là một `ArrayList<Integer>` suy luận từ tham số `put`.
- `var noTarget = new ArrayList<>()` tạo `ArrayList<Object>` vì không có ràng buộc cụ thể; cả chuỗi và số được boxing thành `Integer` đều thêm hợp lệ.
- `raw` trỏ tới **cùng đối tượng** với `legacy`, nên `raw.add(123)` đưa `Integer` vào `List<String>` và tạo vấn đề tại thời điểm đọc dữ liệu. `try/catch` làm ví dụ in ra tên loại lỗi để việc học không bị dừng ở stack trace thay đổi theo môi trường.

Trong code production, **loại bỏ alias raw**, đừng giữ cơ chế bắt `ClassCastException` như một giải pháp xử lý dữ liệu thường xuyên.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `List<String> a = new ArrayList();` xuất hiện `unchecked conversion` | Constructor dùng raw type | Đổi thành `new ArrayList<>()`. |
| `List raw = new ArrayList<>();` vẫn có `rawtypes` | Kiểu khai báo của biến vẫn raw | Viết `List<String>`, `List<?>` hoặc một kiểu thích hợp. |
| `var xs = new ArrayList<>();` nhận cả `String` và `Integer` | Compiler suy luận `ArrayList<Object>` khi không có target type cụ thể | Dùng `var xs = new ArrayList<String>()` hoặc `List<String> xs = new ArrayList<>()`. |
| `List<> xs` không biên dịch | Diamond không dùng thay cho danh sách tham số trong khai báo kiểu | Viết `List<String>`, `List<?>` hoặc `List<T>`. |
| `new List<>()` không biên dịch | `List` là interface | Tạo `new ArrayList<>()` hoặc một implementation phù hợp. |
| `List<Integer> x = new ArrayList<String>();` không biên dịch | Hai tham số kiểu không tương thích | Thống nhất kiểu cần lưu ở hai vế. |
| `List<Number> x = new ArrayList<Integer>();` không biên dịch | Generics bất biến | Chọn `List<Number>` ở hai phía hoặc wildcard phù hợp để chỉ đọc. |
| `List<?> xs` không `add("a")` được | Kiểu phần tử chưa biết | Dùng kiểu cụ thể nếu cần ghi, hoặc thiết kế tham số `? super T` thích hợp. |
| `@SuppressWarnings("unchecked")` làm hết cảnh báo | Chỉ ẩn diagnostic; không xác thực dữ liệu | Sửa khai báo generic hoặc kiểm tra/chuyển đổi ở boundary. |
| `ClassCastException` xuất hiện khi `get` dù list có kiểu generic | Raw alias hoặc unchecked cast đưa sai phần tử vào list | Truy ngược nguồn heap pollution; bỏ raw, thêm kiểm tra tại nơi nhận dữ liệu. |

### Quy tắc chọn nhanh khi viết code mới

- Đã có kiểu đích rõ như `List<User>`, `Map<String, Long>`: ưu tiên `new ArrayList<>()`, `new HashMap<>()` để tránh lặp lại.
- Dùng `var` với constructor generic rỗng: cân nhắc viết tường minh tham số kiểu ở biểu thức `new`; đừng mặc định `<>` suy luận đúng kiểu mong muốn.
- Đang xử lý dữ liệu chưa biết kiểu: dùng `List<?>`/`Collection<?>` để đọc an toàn; kiểm tra phần tử trước khi chuyển thành typed collection.
- Gặp raw type trong code legacy: bật `-Xlint:rawtypes -Xlint:unchecked`, lần theo cảnh báo và sửa từ chữ ký API nếu có thể.
- Không thêm raw type nhằm né các lỗi generic; lỗi compile-time thường đang giúp phát hiện mâu thuẫn hợp đồng dữ liệu.

## 11. Bài tập tự kiểm tra và lời giải định hướng

**Bài 1 — Hai constructor:** Tại sao `List<String> s = new ArrayList<>()` tốt hơn `List<String> s = new ArrayList()`? Hãy chỉ ra nơi compiler có đủ thông tin để kiểm tra `String` và nơi xuất hiện cảnh báo.

**Định hướng:** Diamond suy luận `String` qua kiểu đích; raw constructor bỏ tham số kiểu và phép gán sang `List<String>` không được kiểm tra đầy đủ.

**Bài 2 — Có hay không là raw?** Xem hai khai báo:

```java
var a = new ArrayList<>();
var b = new ArrayList();
```

**Định hướng:** `a` là `ArrayList<Object>` (parameterized type do inference); `b` là raw `ArrayList`. Khi gọi `add` với `b`, compiler có thể cảnh báo unchecked. Cả hai có thể nhận nhiều kiểu phần tử, nhưng cơ chế an toàn kiểu khác nhau.

**Bài 3 — Sửa API:** Cho đoạn legacy:

```java
Map cache = new HashMap();
cache.put("answer", 42);
Integer n = (Integer) cache.get("answer");
```

Hãy đổi sang `Map<String,Integer> cache = new HashMap<>()`, bỏ cast và thử gọi `cache.put(10, "wrong")`. **Định hướng:** dòng `put` sai kiểu mới bị từ chối ngay khi biên dịch.

**Bài 4 — Một alias raw:** Giải thích vì sao `List<String>` vẫn có thể ném `ClassCastException` khi đọc, mặc dù `add(123)` qua chính biến này là lỗi biên dịch. **Định hướng:** một tham chiếu khác ở dạng raw có thể chèn phần tử không đúng hợp đồng vào cùng đối tượng; chính xác hơn, generic chỉ bảo vệ được những lối truy cập mà compiler có đủ thông tin kiểu.

Khi tự kiểm tra, bạn cần phân biệt được ba ý cốt lõi: **diamond là suy luận tham số kiểu**, **raw type bỏ tham số kiểu để tương thích mã cũ**, và **wildcard vẫn là generic an toàn kiểu dành cho trường hợp chưa biết tham số cụ thể**. Hiểu ba điểm này giúp đọc cảnh báo compiler và chỉnh sửa collection API trong dự án Java mà không tạo lỗi runtime khó truy vết.
