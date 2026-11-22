# Java 10 – Thực hành tổng hợp: Đối chiếu suy luận var với các kiểu khai báo tường minh

> **Ngữ cảnh:** Java 10 → **Thực hành tổng hợp** → **Đối chiếu suy luận `var` với các kiểu khai báo tường minh**. Tính năng *local variable type inference* có từ **Java 10 (JEP 286)** và vẫn hữu ích trên JDK hiện đại. Bài thực hành này đặt hai cách viết cạnh nhau, phân tích **static type, generic inference, overload resolution, null/lambda, tính dễ đọc và ranh giới API**. Code đã thử với **`javac --release 10` và `javac --release 17`** trên Zulu OpenJDK 24.0.2. Java 10 ở đây là mốc ngôn ngữ, **không phải khuyến nghị triển khai JDK 10 không còn được hỗ trợ bảo mật**.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Hiểu `var` là **suy luận kiểu cục bộ tại compile time**, không phải dynamic typing.
2. So static type của biến `var` với biến khai báo tường minh có cùng initializer.
3. Nhận diện việc kiểu tường minh `List<String>`/`Map<String,Integer>` giữ **interface contract**, còn `var` có thể suy concrete class.
4. Phân tích vì sao `var xs = new ArrayList<>()` suy `ArrayList<Object>` nếu không có target typing phù hợp.
5. Hiểu generic factory methods và type witness cho `Collections.emptyList()`, `List.of()`, `Optional.empty()`.
6. Chứng minh overload resolution có thể đổi dù runtime object giữ nguyên.
7. Xác định type của literal số, conditional expression, array, null-cast, anonymous class.
8. Dùng `var` hợp lệ trong block, classic/enhanced `for` và try-with-resources.
9. Hiểu `final var` không làm object immutable.
10. Phân biệt local variable inference Java 10 với cú pháp `(var x) -> ...` trong lambda parameters xuất hiện **Java 11**.
11. Nhận diện khai báo `var` không hợp lệ và sửa bằng kiểu tường minh/initializer.
12. Biên dịch chương trình hoàn chỉnh, đọc stdout đã kiểm chứng và làm bài tập refactor.

**Nguyên tắc:** `var` **chỉ bỏ phần type viết bên trái**, còn compiler vẫn gán cho biến một **kiểu tĩnh xác định từ initializer**. Thay `Object value = "a"` bằng `var value = "a"` có thể đổi static type từ Object sang String; do đó **không phải mọi phép thay type bằng var đều type-neutral**.

## 2. `var` có phải là một kiểu dữ liệu?

Không. Java 10 có một **restricted type name** `var` được compiler hiểu ở những vị trí khai báo biến cục bộ được phép. Nó không phải class `java.lang.Var` và không chuyển Java thành ngôn ngữ kiểu động.

~~~java
String message = "hello";
var sameMessage = "hello"; // compiler suy String
~~~

Hai biến có cùng static type `String`. Một phép gán không tương thích:

~~~java
var number = 42;   // int
// number = "42";  // KHÔNG BIÊN DỊCH: int không nhận String
~~~

Sau khai báo, compiler kiểm từng assignment/lời gọi method theo static type đã biết. Các lần gán về sau **không được dùng để suy lại type**.

### 2.1. Ví dụ type-neutral và không type-neutral

| Bản tường minh | Bản dùng var | Kiểu giống nhau? |
| --- | --- | --- |
| `String x = "A";` | `var x = "A";` | Có, String |
| `int x = 1;` | `var x = 1;` | Có, int |
| `double x = 1.0;` | `var x = 1.0;` | Có, double |
| `long x = 1L;` | `var x = 1L;` | Có, long |
| `int[] x = new int[]{1,2};` | `var x = new int[]{1,2};` | Có, int[] |
| `Object x = "A";` | `var x = "A";` | Không, Object vs String |
| `List<String> x = new ArrayList<String>();` | `var x = new ArrayList<String>();` | Không, List vs ArrayList |
| `List<String> x = new ArrayList<>();` | `var x = new ArrayList<>();` | Không, List<String> vs ArrayList<Object> |
| `List<String> x = Collections.emptyList();` | `var x = Collections.emptyList();` | Không, List<String> vs List<Object> |

Để refactor, so sánh **static type thực**, không chỉ xem dữ liệu in ra giống nhau.

## 3. Trường hợp 1 – Literal và primitive types

~~~java
int explicitInt = 10;
var inferredInt = 10; // int

long explicitLong = 10;
var inferredLong = 10L; // long

double explicitDouble = 1.0;
var inferredDouble = 1.0; // double

float explicitFloat = 1.0f;
var inferredFloat = 1.0f; // float
~~~

`long explicitLong = 10;` gán một int literal sang long bằng **widening conversion** dựa trên type đích; `var inferredInt = 10;` không có target long, nên giữ static type int.

| Initializer | Type của `var` |
| --- | --- |
| `10` | int |
| `10L` | long |
| `2.5` | double |
| `2.5f` | float |
| `true` | boolean |
| `'a'` | char |
| `"a"` | String |
| `new int[]{3, 5}` | int[] |

### 3.1. Ảnh hưởng đến method overload

~~~java
static String overload(int value) { return "int"; }
static String overload(long value) { return "long"; }
~~~

Nếu khai báo `long value = 10;`, compiler chọn overload(long); nếu đổi thành `var value = 10;`, compiler chọn overload(int). Muốn giữ kiểu long với var, dùng `var value = 10L;`.

Do đó hai biến cùng hiển thị `10` **chưa đủ** chứng minh chúng có cùng type.

### 3.2. Conditional expression

~~~java
var choice = true ? 1 : 2L; // long
~~~

Type của toàn bộ biểu thức điều kiện được xác định tại compile time theo numeric promotion; **không** chọn type phụ thuộc nhánh nào chạy ở runtime. Với hai overload bên trên, `overload(choice)` trả `long`.

## 4. Trường hợp 2 – Interface type so với concrete class

~~~java
List<String> names = new ArrayList<String>();
var names2 = new ArrayList<String>();
~~~

Đoạn đầu có static type `List<String>`, đoạn sau là `ArrayList<String>`. Dù runtime object đều là ArrayList, biến thứ nhất giữ **abstraction interface**, còn biến thứ hai phụ thuộc concrete class.

~~~java
List<String> names = new ArrayList<String>();
names = new LinkedList<String>(); // Hợp lệ
~~~

Trong khi:

~~~java
var names2 = new ArrayList<String>();
// names2 = new LinkedList<String>(); // KHÔNG BIÊN DỊCH
~~~

Compiler không tự suy interface `List` “vì về mặt thiết kế đó là interface đẹp nhất”. Nó suy kiểu initializer, ở đây là ArrayList<String>.

**Khi nào dùng khai báo tường minh?** Khi muốn thay đổi implementation, giảm coupling hoặc biểu đạt một contract như `List`/`Map`/`Set`.

**Khi nào var phù hợp?** Khi constructor đã cho đủ thông tin, concrete type là đúng chủ đích, và loại bỏ phần type lặp lại giúp code dễ đọc.

## 5. Trường hợp 3 – Diamond `<>` dễ mất generic type

Đây là bẫy quan trọng của bài.

### 5.1. Có target type

~~~java
List<String> names = new ArrayList<>();
names.add("Lan");
// names.add(10); // KHÔNG BIÊN DỊCH
~~~

Compiler nhận target type `List<String>` ở bên trái, suy constructor generic parameter là `String`.

### 5.2. Dùng `var` không có type arguments

~~~java
var names = new ArrayList<>();
names.add("Lan");
names.add(10); // HỢP LỆ: static type ArrayList<Object>
~~~

Ở trường hợp này `var` không cung cấp target `String` như khai báo tường minh. Type được suy thành **`ArrayList<Object>`**. Compiler **không nhìn các lệnh add ở dòng sau** để tự giới hạn lại `String`.

Bản dùng var giữ type String:

~~~java
var names = new ArrayList<String>();
~~~

Bản giữ abstraction:

~~~java
List<String> names = new ArrayList<>();
~~~

### 5.3. Cùng vấn đề với Map

~~~java
Map<String, Integer> explicit = new HashMap<>();
explicit.put("one", 1);
~~~

nhưng:

~~~java
var inferred = new HashMap<>();
inferred.put("one", 1);
inferred.put(2, "two"); // HỢP LỆ: HashMap<Object,Object>
~~~

Nếu bạn muốn type arguments chính xác:

~~~java
var inferred = new HashMap<String, Integer>();
~~~

**Đừng** dùng type suy Object chỉ vì tiện mà business contract yêu cầu String/Integer.

### 5.4. Generic invariance

~~~java
var values = new ArrayList<>();
List<String> strings = values; // KHÔNG BIÊN DỊCH
~~~

`values` có kiểu ArrayList<Object>. Java không coi `List<Object>` là subtype của `List<String>`; nếu cho phép điều này, type safety sẽ mất. Chọn type tường minh/constructor type arguments phù hợp tại khai báo thay vì dùng unchecked cast để che sai sót.

## 6. Trường hợp 4 – Generic factory và target typing

~~~java
List<String> explicit = Collections.emptyList();
var inferred = Collections.emptyList();
~~~

Với khai báo tường minh, `Collections.emptyList()` nhận type target `List<String>` và suy generic argument String. Khi dùng var, expression không có target như vậy, thông thường suy `List<Object>` trong trường hợp này.

Một cách kiểm:

~~~java
static int countStrings(List<String> values) {
    return values.size();
}
static int countObjects(List<Object> values) {
    return values.size();
}
~~~

~~~java
List<String> first = Collections.emptyList();
var second = Collections.emptyList();

countStrings(first); // Hợp lệ
countObjects(second); // Hợp lệ
// countStrings(second); // Không biên dịch
~~~

Cách dùng var có type witness:

~~~java
var empty = Collections.<String>emptyList();
~~~

hoặc giữ bản tường minh vì rõ ý hơn:

~~~java
List<String> empty = Collections.emptyList();
~~~

### 6.1. Các factory khác

~~~java
var list = List.of();              // thường List<Object> ở ngữ cảnh này
var absent = Optional.empty();     // thường Optional<Object>
~~~

Trong khi:

~~~java
List<String> list = List.of();
Optional<String> absent = Optional.empty();
~~~

hoặc:

~~~java
var list = List.<String>of();
var absent = Optional.<String>empty();
~~~

đều cung cấp type argument String.

`var list = List.of("A", "B");` có thông tin type từ arguments nên suy `List<String>`. Collection unmodifiable do contract `List.of`/`List.copyOf`, **không phải do var**.

## 7. Trường hợp 5 – Overload resolution có thể đổi behavior

Hai overload:

~~~java
static String pick(Object value) { return "Object"; }
static String pick(String value) { return "String"; }
~~~

Hai biến:

~~~java
Object explicit = "java";
var inferred = "java";
~~~

Giá trị runtime của cả hai đều là String, nhưng static types là Object và String. Vì vậy `pick(explicit)` chọn `pick(Object)`, còn `pick(inferred)` chọn `pick(String)`.

### 7.1. Ví dụ runnable độc lập đã kiểm

Lưu `OverloadStaticTypes.java`:

~~~java
public class OverloadStaticTypes {
    static String pick(Object value) { return "Object"; }
    static String pick(String value) { return "String"; }

    public static void main(String[] args) {
        Object explicitGeneral = "java";
        var inferredSpecific = "java";
        System.out.println("explicit-overload=" + pick(explicitGeneral));
        System.out.println("var-overload=" + pick(inferredSpecific));
        System.out.println("same-runtime-class=" +
                (explicitGeneral.getClass() == inferredSpecific.getClass()));
    }
}
~~~

~~~bash
javac --release 10 -encoding UTF-8 OverloadStaticTypes.java
java OverloadStaticTypes
~~~

Stdout đã kiểm:

~~~text
explicit-overload=Object
var-overload=String
same-runtime-class=true
~~~

Đây là **overloading chọn chữ ký khi compile**, không phải overriding/dynamic dispatch. Khi review thay `Object x` bằng `var x`, phải kiểm các overload phía sau ngay cả khi code vẫn compile.

## 8. Trường hợp 6 – `null` literal và cast

~~~java
String name = null; // Hợp lệ
// var name = null; // Không biên dịch
~~~

Initializer `null` literal đơn thuần không cung cấp static type hợp lệ cho local-variable inference.

Có thể cung cấp type bằng cast:

~~~java
var name = (String) null; // Hợp lệ, suy String
~~~

Nhưng khai báo `String name = null;` thường dễ đọc hơn. Sau khi đã có reference type, biến var vẫn có thể nhận null nếu không final:

~~~java
var name = "A"; // String
name = null;    // Hợp lệ
~~~

`var` không áp đặt non-null contract.

## 9. Trường hợp 7 – Array literal

~~~java
int[] values = {1, 2};         // Hợp lệ
// var values = {1, 2};        // Không biên dịch
var values = new int[]{1, 2};  // Hợp lệ, type int[]
~~~

Dạng `{1, 2}` cần target array type; expression `new int[]{1, 2}` đã có type. Nếu muốn giữ cách viết ngắn dạng `{...}` thì sử dụng khai báo `int[]` tường minh.

## 10. Trường hợp 8 – Lambda expressions và method references

Lambda expression cần **target functional interface**.

~~~java
Predicate<String> isShort = s -> s.length() < 4;
~~~

Nhưng:

~~~java
// var isShort = s -> s.length() < 4; // Không biên dịch
~~~

Bản có cast hợp lệ:

~~~java
var isShort =
        (Predicate<String>) s -> s.length() < 4;
~~~

Song bản `Predicate<String> isShort = ...` thường rõ contract hơn.

Method reference cũng vậy:

~~~java
ToIntFunction<String> length = String::length;
// var length = String::length; // Không biên dịch, thiếu target
~~~

### 10.1. Var lambda parameters từ Java 11, không phải Java 10

~~~java
Predicate<String> nonempty = (var s) -> !s.isEmpty();
~~~

Đây là cú pháp **Java 11/JEP 323**, không phải tính năng Java 10 nguyên gốc. Thí nghiệm: `javac --release 10` từ chối lambda parameter var này, trong khi `javac --release 17` cho biên dịch thành công.

Không trộn cách khai báo lambda parameters, ví dụ `(var x, y)` hoặc `(var x, String y)` là không hợp lệ. Và có var bên trong lambda parameters cũng **không** cho phép bare `var f = x -> ...;`.

## 11. Trường hợp 9 – `final var` và mutability

~~~java
final List<String> explicit = new ArrayList<>();
final var inferred = new ArrayList<String>();

explicit.add("a"); // Hợp lệ
inferred.add("b"); // Hợp lệ

// inferred = new ArrayList<>(); // Không biên dịch, final reference
~~~

`final` cấm **gán lại local variable**, không cấm thay đổi object được trỏ tới. `var` không biến ArrayList thành immutable collection. Muốn unmodifiable list, dùng API như `List.copyOf`/`List.of` với các điều kiện phù hợp; đó là **API contract** khác biệt.

## 12. Trường hợp 10 – Vòng lặp và try-with-resources

`var` trong Java 10 được phép ở các local declaration forms phù hợp.

Classic for:

~~~java
int sum = 0;
for (var i = 0; i < 3; i++) {
    sum += i;
}
System.out.println(sum); // 3
~~~

Enhanced for:

~~~java
Map<String, Integer> data = Map.of("only", 7);
for (var entry : data.entrySet()) {
    System.out.println(entry.getKey() + ":" + entry.getValue());
}
~~~

Trong ví dụ trên `entry` suy `Map.Entry<String,Integer>`; output `only:7`.

Try-with-resources:

~~~java
try (var reader = new StringReader("ok")) {
    System.out.println((char) reader.read()); // o
}
~~~

`reader` suy `StringReader` và vẫn được đóng khi thoát try block. Cơ chế resource closing/checked exceptions không đổi do dùng var.

## 13. Trường hợp 11 – Anonymous class giữ type cụ thể

~~~java
var anonymous = new Object() {
    String label() { return "anonymous-member"; }
};
System.out.println(anonymous.label());
~~~

Compiler có thể suy type anonymous class, cho phép gọi method mới `label()` qua biến local.

Nếu viết:

~~~java
Object anonymous = new Object() {
    String label() { return "anonymous-member"; }
};
// anonymous.label(); // Không biên dịch: Object không có label()
~~~

thì static type tường minh `Object` che thành viên ấy. Đây là **thay đổi static API có thể truy cập**, không phải `var` tạo động lực gọi method ở runtime. Đừng thiết kế public API dựa vào anonymous class methods chỉ để tận dụng var.

## 14. Các hạn chế cần biết ở declaration site

| Code | Hợp lệ? | Vì sao |
| --- | --- | --- |
| `var x = 1;` | Có | Initializer int |
| `var x = null;` | Không | Null literal không suy type |
| `var x;` | Không | Thiếu initializer |
| `var a = 1, b = 2;` | Không | Compound var declaration |
| `var x = {1, 2};` | Không | Array shorthand không có target type |
| `var x = new int[]{1,2};` | Có | Có expression type int[] |
| `var x = x;` | Không | Self-reference trong initializer |
| `var a[] = new int[2];` | Không | Bracket pairs sau tên không được phép |
| `class C { var x = 1; }` | Không | Field type không dùng var |
| `void f(var x){}` | Không | Method parameter type không dùng var |
| `var f(){return 1;}` | Không | Return type không dùng var |
| `var p = s -> true;` | Không | Bare lambda thiếu target |
| `var p = String::length;` | Không | Bare method reference thiếu target |
| `final var x = new ArrayList<String>();` | Có | Final local var |
| `for(var e : list)` | Có | Enhanced for suy element type |
| `try(var r = new StringReader("x"))` | Có | Resource AutoCloseable có type rõ |

**Lưu ý:** Những dòng lỗi là ví dụ để nghiên cứu compiler, **không copy vào file runnable** bên dưới.

### 14.1. Không suy ngược từ các lệnh sau

~~~java
var items = new ArrayList<>();
items.add("A");
items.add("B");
~~~

Type vẫn là `ArrayList<Object>`, không trở thành `ArrayList<String>`.

### 14.2. Public API boundaries cần type rõ

Field, method parameter và return type phải có type tường minh:

~~~java
private List<String> names;

public List<String> findNames() {
    return List.copyOf(names);
}

public void replaceNames(List<String> next) {
    names = List.copyOf(next);
}
~~~

Đoạn trên là **các thành viên minh họa của một class**, không phải standalone file. Sự rõ ràng của API contract không nên bị thay bởi suy luận local var.

## 15. Chương trình thực hành đầy đủ: `VarVsExplicitDemo.java`

Lưu đúng file `VarVsExplicitDemo.java`. Chương trình đã biên dịch thành công bằng `--release 10` và `--release 17`, cho kết quả ổn định dưới đây.

~~~java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;

public final class VarVsExplicitDemo {
    static String overload(int value) { return "int"; }
    static String overload(long value) { return "long"; }
    static int countStringList(List<String> values) { return values.size(); }
    static int countObjectList(List<Object> values) { return values.size(); }

    public static void main(String[] args) throws Exception {
        int explicitInt = 10;
        var inferredInt = 10;
        long explicitLong = 10;
        var inferredLong = 10L;
        System.out.println("explicit-int-overload=" + overload(explicitInt));
        System.out.println("var-int-overload=" + overload(inferredInt));
        System.out.println("explicit-long-overload=" + overload(explicitLong));
        System.out.println("var-long-overload=" + overload(inferredLong));

        List<String> explicitStrings = new ArrayList<>();
        var concreteStrings = new ArrayList<String>();
        explicitStrings.add("a");
        concreteStrings.add("b");
        System.out.println("explicit-list-type-size=" + countStringList(explicitStrings));
        System.out.println("var-typed-list-size=" + countStringList(concreteStrings));

        var broadList = new ArrayList<>();
        broadList.add("text");
        broadList.add(42);
        System.out.println("var-diamond-object-list=" + countObjectList(broadList));
        List<String> contextualList = new ArrayList<>();
        contextualList.add("typed");
        System.out.println("explicit-diamond-string-list=" +
                countStringList(contextualList));

        Map<String, Integer> explicitMap = new HashMap<>();
        var specificMap = new HashMap<String, Integer>();
        var broadMap = new HashMap<>();
        explicitMap.put("one", 1);
        specificMap.put("two", 2);
        broadMap.put("three", 3);
        broadMap.put(4, "four");
        System.out.println("explicit-map-size=" + explicitMap.size());
        System.out.println("var-specific-map-size=" + specificMap.size());
        System.out.println("var-diamond-map-size=" + broadMap.size());

        List<String> targetedEmpty = Collections.emptyList();
        var inferredEmpty = Collections.emptyList();
        System.out.println("explicit-generic-empty=" + countStringList(targetedEmpty));
        System.out.println("var-generic-empty=" + countObjectList(inferredEmpty));

        final var finalReference = new ArrayList<String>();
        finalReference.add("mutable");
        System.out.println("final-var-mutable-object=" + finalReference.size());

        var anonymous = new Object() {
            String label() { return "anonymous-member"; }
        };
        System.out.println("anonymous-access=" + anonymous.label());

        var choice = true ? 1 : 2L;
        System.out.println("conditional-overload=" + overload(choice));
        var nullableString = (String) null;
        System.out.println("cast-null-accepted=" + (nullableString == null));

        int sum = 0;
        for (var i = 0; i < 3; i++) { sum += i; }
        System.out.println("for-index-sum=" + sum);
        for (var entry : Map.of("only", 7).entrySet()) {
            System.out.println("foreach-entry=" + entry.getKey() + ":" +
                    entry.getValue());
        }
        try (var reader = new StringReader("ok")) {
            System.out.println("resource-first-char=" + (char) reader.read());
        }

        Predicate<String> explicitlyTypedLambda = s -> s.startsWith("a");
        var inferredFromCast = (Predicate<String>) s -> s.startsWith("a");
        System.out.println("explicit-lambda=" +
                explicitlyTypedLambda.test("abc"));
        System.out.println("var-lambda-cast=" + inferredFromCast.test("abc"));

        var ints = new int[] {3, 5};
        System.out.println("array-element-sum=" + (ints[0] + ints[1]));
        var immutable = List.copyOf(explicitStrings);
        System.out.println("copyof-size=" + immutable.size());
    }
}
~~~

### 15.1. Build target Java 10

~~~bash
mkdir -p out10
javac --release 10 -encoding UTF-8 -d out10 VarVsExplicitDemo.java
javap -verbose -classpath out10 VarVsExplicitDemo
java -cp out10 VarVsExplicitDemo
~~~

Trên JDK24 thử nghiệm, `javap` xác nhận:

~~~text
minor version: 0
major version: 54
~~~

Class-file major 54 là target **Java 10**. `--release 10` không khiến compiler thực đổi version và không chứng minh code đã được thử trên một runtime Java 10 thật.

### 15.2. Build target Java 17

~~~bash
mkdir -p out17
javac --release 17 -encoding UTF-8 -d out17 VarVsExplicitDemo.java
javap -verbose -classpath out17 VarVsExplicitDemo
java -cp out17 VarVsExplicitDemo
~~~

Header đã xác minh:

~~~text
minor version: 0
major version: 61
~~~

Để tuyên bố compatibility với runtime Java17, chạy tests trên runtime17 thật. Kết quả class major61 là xác minh **bytecode target**, không thay thế integration tests.

### 15.3. Stdout chính xác đã kiểm

~~~text
explicit-int-overload=int
var-int-overload=int
explicit-long-overload=long
var-long-overload=long
explicit-list-type-size=1
var-typed-list-size=1
var-diamond-object-list=2
explicit-diamond-string-list=1
explicit-map-size=1
var-specific-map-size=1
var-diamond-map-size=2
explicit-generic-empty=0
var-generic-empty=0
final-var-mutable-object=1
anonymous-access=anonymous-member
conditional-overload=long
cast-null-accepted=true
for-index-sum=3
foreach-entry=only:7
resource-first-char=o
explicit-lambda=true
var-lambda-cast=true
array-element-sum=8
copyof-size=1
~~~

### 15.4. Bằng chứng các phép so sánh

- ``explicit-int-overload` và `var-int-overload`: cùng int.
- `explicit-long-overload` và `var-long-overload`: cùng long.
- `explicit-list-type-size` và `var-typed-list-size`: hai cách vẫn tương thích method nhận List<String>, nhưng static types List/ArrayList khác nhau.
- `var-diamond-object-list=2`: chấp nhận String và Integer, type ArrayList<Object>.
- `explicit-diamond-string-list=1`: target type List<String> bảo vệ generic constraint.
- `var-diamond-map-size=2`: HashMap<Object,Object> chấp nhận key/value khác kiểu.
- `explicit-generic-empty` và `var-generic-empty`: cùng size 0 nhưng static generic types khác.
- `final-var-mutable-object=1`: final không làm object bất biến.
- `anonymous-access`: type anonymous class được giữ đủ để gọi method.
- `conditional-overload=long`: conditional expression type long.
- `cast-null-accepted=true`: cast cho type tường minh để infer.
- `for-index-sum`, `foreach-entry`, `resource-first-char`: ba vị trí hợp lệ của var.
- `explicit-lambda` và `var-lambda-cast`: lambda có functional-interface target.
- `array-element-sum`: initializer new int[] suy int[].
- `copyof-size`: List.copyOf giữ API unmodifiable, không liên quan biến có viết var.

Stdout không in HashMap iteration order, tránh phụ thuộc thứ tự không được bảo đảm.

## 16. Mười hai compile-negative tests đã xác minh

Mỗi đoạn sau **cố ý không biên dịch** và đã được kiểm riêng với `javac --release 10`; không dán chúng vào chương trình ở phần 15. Các trường hợp:

### 16.1. Null hoặc thiếu initializer

~~~java
class Null {
    void test() {
        var x = null; // COMPILE ERROR
    }
}
~~~

~~~java
class NoInitializer {
    void test() {
        var x; // COMPILE ERROR
    }
}
~~~

### 16.2. Compound, array shorthand, self-reference

~~~java
class Compound {
    void test() {
        var x = 1, y = 2; // COMPILE ERROR
    }
}
~~~

~~~java
class ArrayLiteral {
    void test() {
        var x = {1, 2}; // COMPILE ERROR
    }
}
~~~

~~~java
class SelfReference {
    void test() {
        var x = x; // COMPILE ERROR
    }
}
~~~

### 16.3. Thiếu target lambda hoặc method reference

~~~java
class LambdaWithoutTarget {
    void test() {
        var f = (String s) -> s.length(); // COMPILE ERROR
    }
}
~~~

~~~java
class MethodRefWithoutTarget {
    void test() {
        var f = String::length; // COMPILE ERROR
    }
}
~~~

### 16.4. Field, method parameter, return type

~~~java
class VarField {
    var value = 10; // COMPILE ERROR
}
~~~

~~~java
class VarParam {
    void test(var value) {} // COMPILE ERROR
}
~~~

~~~java
class VarReturn {
    var test() { return 10; } // COMPILE ERROR
}
~~~

### 16.5. Gán sai generic type sau var

~~~java
import java.util.*;
class DiamondMismatch {
    void test() {
        var xs = new ArrayList<>();
        List<String> text = xs; // COMPILE ERROR
    }
}
~~~

~~~java
import java.util.*;
class EmptyListMismatch {
    void test() {
        var xs = Collections.emptyList();
        List<String> text = xs; // COMPILE ERROR
    }
}
~~~

Cả 12 ca được compiler từ chối đúng mong đợi. Wording của diagnostics khác theo javac version/locale, nên kiểm **exit code không thành công**, không so error text nguyên văn.

### 16.6. Biên dịch var lambda parameters theo release

~~~java
import java.util.function.Predicate;
class LambdaVar11 {
    Predicate<String> predicate = (var s) -> s.length() > 1;
}
~~~

Đã kiểm: `javac --release 10` thất bại, `javac --release 17` thành công, phù hợp JEP323 (Java 11). Đây là khác biệt phiên bản cần nêu rõ, không phải một “cách dùng var không hợp lệ trên mọi JDK”.

## 17. Hướng dẫn code review: dùng var hay tường minh?

**Ưu tiên var khi:**

- Initializer cho type rõ: `var amount = 10L;`, `var file = Path.of("a.txt");`.
- Constructor đã viết đầy đủ generic arguments và concrete type thực sự được cần: `var map = new HashMap<String, Integer>();`.
- Loop/resource có type dài nhưng nguồn rõ: `for (var entry : map.entrySet())`, `try (var reader = ...)`.
- Tên biến diễn đạt ý nghĩa và type tĩnh không cần lặp.
- Không thay đổi static abstraction, generic constraints hay overload semantics một cách vô ý.

**Ưu tiên khai báo tường minh khi:**

- Muốn contract interface: `List<String> data = new ArrayList<>();`.
- Factory generic cần type target: `List<String> empty = Collections.emptyList();`.
- Initializer như `process()` không cho người đọc dễ suy type.
- Cần supertype để cho phép gán implementation khác hoặc chọn overload có chủ đích.
- Lambda/method reference cần functional-interface type.
- Type có ý nghĩa ở ranh giới API hoặc trong code review.

Không có quy tắc “càng ít ký tự càng sạch”; OpenJDK Amber style guide nhấn mạnh **type clues, readability và người đọc code**.

## 18. Quy trình refactor an toàn

1. Ghi static type cũ, ví dụ `List<String>`.
2. Tính type của initializer trong **standalone context** khi chuyển sang var.
3. Kiểm diamond `<>`/generic factory có dựa vào target cũ không.
4. Nếu type mới khác, quyết định thay đổi ấy có chủ đích hay không.
5. Kiểm các overload/assignments/method calls dùng biến phía sau.
6. Giữ kiểu tường minh nếu đang bảo vệ abstraction hoặc giao diện module.
7. Nếu var hữu ích, thêm type arguments phía constructor/method khi cần.
8. Biên dịch đúng target bằng `javac --release`.
9. Chạy tests, đặc biệt khi overload hoặc generic behavior có thể khác.
10. Review lại tên biến và độ dễ suy type của initializer.

### 18.1. Ví dụ refactor type-neutral

~~~java
String title = "Java";
~~~

thành:

~~~java
var title = "Java";
~~~

Cùng static type String, là một refactor local an toàn nếu code style chấp nhận.

### 18.2. Ví dụ refactor không type-neutral

~~~java
List<String> names = new ArrayList<>();
~~~

thành:

~~~java
var names = new ArrayList<>();
~~~

là thay đổi sang ArrayList<Object> trong ngữ cảnh này. Đây có thể là bug compiler chấp nhận code rộng hơn ý định, vì phần tử Integer được đưa vào mà không bị từ chối.

### 18.3. Trường hợp overload không bị compiler cảnh báo

~~~java
Object value = "java";
pick(value);
~~~

đổi thành:

~~~java
var value = "java";
pick(value);
~~~

có thể chọn overload khác nhưng **vẫn biên dịch thành công**. Đây là lý do unit tests có giá trị hơn việc chỉ check compile trong một số refactors.

## 19. Tình huống ứng dụng cần nghĩ kỹ

### 19.1. Repository/service method returns

~~~java
static List<String> loadNames() {
    return List.of("Lan", "Mai");
}
~~~

Bản:

~~~java
List<String> names = loadNames();
var names2 = loadNames();
~~~

có static type **List<String> cho cả hai**, vì method invocation có static return type tường minh. `var` không suy “runtime concrete type” từ implementation bên trong method. Khi method name và return semantics rõ, var thường hợp lý.

### 19.2. Abstraction và khả năng đổi implementation

Nếu code cần đổi `ArrayList` sang `LinkedList` mà không sửa các dòng khác, `List<String>` tường minh là lựa chọn đúng. Nếu var suy concrete ArrayList thì khả năng đổi implementation có thể bị thu hẹp.

### 19.3. Đặt tên biến khi dùng var

So sánh:

~~~java
var x = service.compute();
~~~

với:

~~~java
ResultSummary summary = service.compute();
~~~

Bản tường minh làm thông tin type rõ dù `compute()` mơ hồ. Nếu đổi tên method/biến cho giàu ngữ nghĩa, `var summary = service.createSummary();` có thể đủ rõ. **Cân nhắc ngữ cảnh thật**, không ép mọi chỗ dùng var.

### 19.4. Type declaration giúp type-checking tại chỗ

~~~java
List<String> names = repository.load();
~~~

Nếu method `load()` trả type không tương thích, compiler từ chối ngay khi khai báo. Bản `var names = repository.load();` có thể nhận một type “rộng hơn” hoặc khác ý định, rồi lỗi xuất hiện xa hơn hoặc không lộ nếu code chỉ gọi API chung. Type tường minh đôi khi là **documentation và một compile-time assertion** hữu ích.

## 20. Bài tập có lời giải

**Câu 1.** `var` có khiến Java chuyển sang dynamic typing? — **Không**, type được suy ở compile time.

**Câu 2.** `var n = 1` là int hay long? — **int**.

**Câu 3.** Dùng var mà muốn long literal? — `var n = 1L;`.

**Câu 4.** `long n = 1;` và `var n = 1;` có cùng type? — **Không**, lần lượt long và int.

**Câu 5.** `var xs = new ArrayList<>()` type gì? — `ArrayList<Object>` trong ngữ cảnh không target khác.

**Câu 6.** `List<String> xs = new ArrayList<>()` type gì? — `List<String>`, constructor suy generic String.

**Câu 7.** `var xs = new ArrayList<String>()` type gì? — `ArrayList<String>`.

**Câu 8.** Vì sao `List<String> xs = varListOfObject` không được? — Generic invariance: List<Object> không phải List<String>.

**Câu 9.** `var xs = Collections.emptyList()` type gì? — `List<Object>` trong ví dụ.

**Câu 10.** Muốn var với emptyList String? — `Collections.<String>emptyList()`.

**Câu 11.** `Object x = "A"` và `var x = "A"` cùng type? — **Không**, Object/String.

**Câu 12.** Vì sao hai biến đó có thể gọi overload khác? — Overload được chọn theo static type.

**Câu 13.** `var x = null` biên dịch? — **Không**.

**Câu 14.** `var x = (String)null` biên dịch? — **Có**, nhưng thường kém rõ hơn String x=null.

**Câu 15.** `var x = {1,2}` biên dịch? — **Không**; cần `new int[]{1,2}` hoặc int[] tường minh.

**Câu 16.** Bare lambda `var p = x -> ...` biên dịch? — **Không**, cần functional-interface target.

**Câu 17.** `(var x) -> ...` là Java 10 hay Java 11? — **Java 11**, JEP 323.

**Câu 18.** `final var list` làm object bất biến? — **Không**, chỉ ngăn gán lại biến.

**Câu 19.** `for (var i=0;...)` hợp lệ? — **Có**.

**Câu 20.** `for (var entry : map.entrySet())` hợp lệ? — **Có**.

**Câu 21.** `try (var r = new StringReader("x"))` hợp lệ? — **Có**, resource type rõ.

**Câu 22.** `var` có dùng cho method return type? — **Không**.

**Câu 23.** `var` có dùng cho class fields hoặc method parameters? — **Không**.

**Câu 24.** `var anonymous = new Object(){ String f(){return "a";}};` có thể gọi f? — **Có**, type anonymous được suy.

**Câu 25.** `var x = true ? 1 : 2L` type gì? — **long**.

**Câu 26.** `var` có suy lại type theo assignments sau khai báo? — **Không**.

**Câu 27.** Tại sao `List<String> xs = ...` có thể tốt hơn var? — Nó thể hiện abstraction/interface và type target rõ.

**Câu 28.** Chỉ compile thành công sau refactor thì đã giữ behavior? — **Chưa chắc**, overload có thể đổi.

## 21. Checklist thực hành trước khi chốt một refactor

- [ ] Kiểu suy luận từ initializer được xác định chính xác.
- [ ] So static type của khai báo cũ và mới.
- [ ] Đánh giá abstraction/interface còn đúng ý định.
- [ ] Kiểm diamond `<>` và factory generic cần type target.
- [ ] Kiểm overloads, assignments và generic method arguments.
- [ ] Kiểm suffix của primitive literals và conditional expression.
- [ ] Không dùng var ở field, method parameter/return.
- [ ] Không bare `null`, lambda, method reference, array shorthand.
- [ ] Không multiple variable declarators hoặc self-reference trong var.
- [ ] Hiểu `final var` không làm object immutable.
- [ ] Phân biệt Java10 var với Java11 lambda-parameter var.
- [ ] Kiểm type và tên biến rõ với người đọc.
- [ ] Biên dịch, chạy tests trên JDK/runtime phù hợp.
- [ ] Phân biệt các ví dụ cố ý lỗi với chương trình runnable.
- [ ] Không giới thiệu cú pháp/flags Java lỗi thời thay cho kiến thức hiện hành.

## 22. Tài liệu chính thức còn áp dụng

1. [OpenJDK JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286): mục tiêu, cơ chế, các vị trí và điều kiện áp dụng trong Java10.
2. [Oracle Java SE 17 – Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): syntax và style guidance còn áp dụng.
3. [Java SE 25 JLS `14.4 – Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): quy định initializer, array shorthand, multiple declarators và self-reference.
4. [OpenJDK Amber – Style Guidelines for Local Variable Type Inference](https://openjdk.org/projects/amber/guides/lvti-style-guide): readability/type clues và lựa chọn var hay type tường minh.
5. [OpenJDK JEP 323 – Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): cú pháp Java11 `(var x) -> ...`.
6. [Java SE 25 JLS `15 – Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html): overload resolution, poly expressions và conditional types.
7. [Java SE 25 JLS `5 – Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html): assignment/widening contexts và conversions.
8. [Oracle Java SE 17 – javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compile `--release` và diagnostics.
9. [Oracle Java SE 17 – javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): class-file inspection.
10. [Java SE 17 – Collections.emptyList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#emptyList()): generic factory.
11. [Java SE 17 – List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): List.of và List.copyOf.
12. [Java SE 17 – ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): concrete generic list implementation.
13. [Java SE 17 – HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): concrete generic map implementation.
14. [Java SE 17 – Predicate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Predicate.html): target của lambda.

**Tổng kết:** Dùng `var` để giảm thông tin lặp khi initializer đã rõ và static type suy ra là type mong muốn. Nếu khai báo tường minh đang giữ interface, tạo target cho generic factory/diamond, hoặc quyết định overload, thay bằng var có thể đổi compile-time behavior. Hãy chọn giữa **`var` và type tường minh theo type safety, tính rõ ràng, abstraction và tests**, không theo số ký tự ít nhất.
