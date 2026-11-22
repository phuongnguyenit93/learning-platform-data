# instanceof với List<?> và các trường hợp kiểu tham số hóa hợp lệ trong Java Generics

## 1. Vấn đề: tại sao instanceof List<?> hợp lệ nhưng instanceof List<String> thường bị từ chối?

`instanceof` là toán tử Java dùng để hỏi liệu một tham chiếu **không null** có thể được nhìn như một kiểu được chỉ định tại runtime hay không:

~~~java
Object value = List.of("Java", "Kotlin");

System.out.println(value instanceof List);     // true
System.out.println(value instanceof List<?>);  // true

// System.out.println(value instanceof List<String>); // Không biên dịch.
~~~

Khi một đối tượng được tạo từ `ArrayList<String>` hay `List.of("Java")`, JVM vẫn không duy trì toàn bộ type arguments của một đối tượng collection để kiểm tra mọi phần tử. Theo cách Java generics được triển khai bằng **type erasure**, runtime có thể kiểm tra được đối tượng có triển khai `List` hay không, nhưng không thể phân biệt đáng tin cậy `List<String>` với `List<Integer>` chỉ bằng một phép kiểm tra runtime trên đối tượng đó.

`List<?>` là trường hợp đặc biệt hữu ích: đây là **parameterized type với unbounded wildcard**. Nó được coi là **reifiable type** theo quy tắc ngôn ngữ, tức có thể dùng ở vế phải `instanceof` từ một biểu thức kiểu `Object`. Tuy nhiên dấu `?` nghĩa là “kiểu phần tử chưa biết”, **không** có nghĩa “mọi phần tử đã được kiểm tra và hợp lệ với String”.

Bài này giải thích:
- Kiểu nào có thể dùng trong `instanceof`.
- Vì sao `List<?>`, `Map<?, ?>`, `Class<?>` và `List<?>[]` có thể hợp lệ.
- Vì sao `Object instanceof List<String>` không hợp lệ.
- Ngoại lệ quan trọng từ Java 16 trở đi: **một số kiểu tham số hóa cụ thể cũng được phép** khi kiểu tĩnh của biểu thức bên trái bảo đảm có casting conversion phù hợp.
- Pattern matching cho `instanceof` trong Java 17.
- Cách **kiểm tra từng phần tử** nếu nghiệp vụ thực sự cần `List<String>`, kể cả cấu trúc lồng nhau.

## 2. Type erasure và giới hạn kiểm tra runtime

Giả sử hai biến:

~~~java
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
~~~

Ở compile time, `List<String>` và `List<Integer>` là hai kiểu tham số hóa khác nhau. Compiler ngăn những lời gọi như `words.add(123)`; nhờ thế code thông thường dùng đúng generic không cần tự cast khi đọc.

Nhưng các đối tượng `ArrayList` của hai biến không phải các lớp runtime chuyên biệt hoàn toàn khác nhau theo T. Với những khai báo trên:

~~~java
System.out.println(words.getClass() == numbers.getClass()); // true
~~~

Cùng lớp runtime không đồng nghĩa cùng kiểu phần tử ở compile time. JVM không có cơ chế `instanceof List<String>` tổng quát để duyệt toàn bộ phần tử và chứng minh chúng là String.

**Hai câu hỏi rất khác nhau:**

1. “Đối tượng có phải một `List` không?” — `instanceof List<?>` kiểm tra được.
2. “Mỗi phần tử trong List có đúng là String không?” — cần kiểm tra phần tử hoặc dựa vào một API có bất biến kiểu đáng tin.

Ví dụ:

~~~java
Object mixed = List.of("Java", 7);
boolean isList = mixed instanceof List<?>; // true.
~~~

`mixed` chứa cả String và Integer nhưng vẫn là một List, vì vậy kết quả `true` là chính xác. Nếu code chỉ nhìn vào `isList` mà ép toàn bộ dữ liệu thành `List<String>`, nó đã đưa ra một kết luận không được phép kiểm tra hỗ trợ.

## 3. Reifiable type nghĩa là gì trong ngữ cảnh này?

Trong Java Language Specification, một kiểu **reifiable** là kiểu có đủ biểu diễn cần thiết ở runtime theo các quy tắc của ngôn ngữ. Những nhóm quan trọng khi học `instanceof`:

- Kiểu nguyên thủy (không phải kiểu tham chiếu ở RHS `instanceof` trong Java 17; không viết `value instanceof int`).
- Class/interface không generic như `String`, `Number` hoặc `Runnable`.
- Raw type của một generic class/interface như `List`, `Map` hoặc `ArrayList`.
- Parameterized type mà **tất cả các type arguments đều là unbounded wildcard**, như `List<?>` và `Map<?, ?>`.
- Array có element type reifiable, như `String[]` hoặc `List<?>[]`.

Đối với toán tử `instanceof` trên một tham chiếu `Object`, các kiểu thực dụng ở RHS thường gặp là:

~~~java
Object input = List.of("A");

boolean a = input instanceof List;             // Hợp lệ: raw List.
boolean b = input instanceof List<?>;          // Hợp lệ: wildcard không giới hạn.
boolean c = input instanceof ArrayList<?>;     // Hợp lệ về cú pháp; kết quả tùy runtime class.
boolean d = input instanceof Map<?, ?>;        // Hợp lệ: cả hai đối số wildcard.
boolean e = input instanceof Class<?>;         // Hợp lệ: Class<T> với wildcard.
boolean f = input instanceof List<?>[];        // Hợp lệ: array của reifiable component type.
~~~

Đây là các **phép kiểm tra hợp lệ về mặt biên dịch**, không có nghĩa tất cả trả `true`. Với `input` là List.of("A"), kết quả `input instanceof ArrayList<?>` thường là false, vì API List.of không hứa trả ArrayList cụ thể. `input instanceof Map<?, ?>` và `input instanceof List<?>[]` cũng false.

`List<?>` là parameterized type, **không phải raw type**. Nếu chỉ cần biết đối tượng là List rồi đọc phần tử dưới dạng Object, `List<?>` thường truyền đạt ý định tốt hơn `List` raw.

### Những kiểu tham số hóa không reifiable theo nghĩa thông thường

Ví dụ:

~~~java
List<String>
List<Integer>
Map<String, Integer>
List<? extends Number>
Map<String, List<Integer>>
~~~

Các kiểu này chứa một hoặc nhiều type arguments cụ thể hoặc wildcard có cận khác unbounded wildcard. Chúng không cung cấp một bài kiểm tra runtime tổng quát qua `Object`. Bởi vậy các đoạn dưới là **cố ý không biên dịch trên Java 17**:

~~~java
Object value = List.of("Java");

// boolean a = value instanceof List<String>;
// boolean b = value instanceof Map<String, Integer>;
// boolean c = value instanceof List<? extends Number>;
~~~

Không được sửa bằng cách ép `(List<String>) value` trước khi kiểm tra, vì unchecked cast không xác nhận toàn bộ phần tử; nó chỉ chuyển rủi ro thành ngoại lệ ở nơi dùng phần tử.

## 4. Bảng phân biệt các RHS của instanceof

| Kiểm tra (giả sử `Object value`) | Hợp lệ Java 17? | Thực tế kiểm tra |
| --- | --- | --- |
| `value instanceof String` | Có | Object là String hoặc subtype của String (thực tế String là final). |
| `value instanceof List` | Có | Object triển khai List; raw type làm mất biểu đạt generic. |
| `value instanceof List<?>` | Có | Object triển khai List, không biết kiểu phần tử. |
| `value instanceof ArrayList<?>` | Có | Runtime class phù hợp ArrayList, không biết kiểu phần tử. |
| `value instanceof Map<?, ?>` | Có | Object triển khai Map, chưa biết kiểu khóa/giá trị. |
| `value instanceof Class<?>` | Có | Object là đối tượng Class, không biết T. |
| `value instanceof List<?>[]` | Có | Object là array có thành phần runtime phù hợp kiểu List; không kiểm tra phần tử từng List. |
| `value instanceof List<String>` | Không | Không thể xác minh tham số String qua một Object. |
| `value instanceof Map<String, Integer>` | Không | Không thể xác minh key/value generic qua Object. |
| `value instanceof List<? extends Number>` | Không | Không có kiểm tra runtime trực tiếp cho cận generic đó qua Object. |

Bảng trên cố ý giữ **kiểu tĩnh vế trái là Object**. Nếu vế trái đã có kiểu tham số hóa cụ thể, kết quả hợp lệ về cú pháp có thể khác theo các quy tắc `casting conversion`; xem phần tiếp theo.

## 5. Ngoại lệ quan trọng: kiểu tham số hóa cụ thể đôi khi hợp lệ với instanceof

Không nên học một quy tắc tuyệt đối rằng **“`instanceof List<String>` lúc nào cũng bất hợp lệ”**.

Từ **Java 16**, hạn chế cũ buộc kiểu RHS của toán tử `instanceof` luôn phải reifiable đã được nới lỏng khi kiểu nguồn có thể được chuyển sang kiểu đích bằng một **casting conversion** hợp lệ. Điều này đáng chú ý khi vế trái đã có generic type đủ cụ thể.

Ví dụ **biên dịch được bằng Java 17**:

~~~java
List<String> known = new ArrayList<>(List.of("Java"));

boolean sameType = known instanceof List<String>;
boolean concrete = known instanceof ArrayList<String>;
~~~

Trong tình huống này, compiler **đã biết** biến `known` là `List<String>`. Kiểm tra `ArrayList<String>` xem đối tượng runtime có thuộc class ArrayList phù hợp hay không; type argument String đã được bảo đảm ở mức compile-time của tham chiếu nguồn theo hệ thống kiểu thông thường.

Mẫu pattern matching cũng hợp lệ vì nguồn `List<String>` chưa nhất thiết là `ArrayList<String>`:

~~~java
if (known instanceof ArrayList<String> actual) {
    System.out.println(actual.get(0)); // Java.
}
~~~

Điểm cốt lõi:

- Compiler dùng **kiểu tĩnh vế trái** để quyết định có casting conversion thích hợp với kiểu RHS hay không.
- Runtime vẫn chủ yếu kiểm tra raw class/interface của đối tượng.
- Phép kiểm tra **không chứng minh lại type arguments** từ nội dung object. Nếu collection bị nhiễm dữ liệu vì raw/unchecked operation, `instanceof ArrayList<String>` vẫn có thể true trong khi đọc phần tử String gây `ClassCastException`.

### Vì sao Object instanceof List<String> vẫn sai?

~~~java
Object unknown = new ArrayList<String>();

// boolean bad = unknown instanceof List<String>; // Không biên dịch.
boolean good = unknown instanceof List<?>;        // Hợp lệ.
~~~

Dù người viết nhìn thấy initializer chứa String, **kiểu tĩnh của biến unknown là Object**. Compiler không dùng một ký ức về initializer để chứng minh an toàn của phép kiểm tra `List<String>` tại lần dùng biến sau. Nó chỉ có thông tin Object và không thể cho phép kiểm tra tham số String như một test runtime tổng quát.

Tương tự:

~~~java
List<?> unknownElement = new ArrayList<String>();

// boolean bad = unknownElement instanceof ArrayList<String>; // Không biên dịch.
boolean good = unknownElement instanceof ArrayList<?>;        // Hợp lệ.
~~~

Wildcard cho biết phần tử chưa xác định; compiler không thể kết luận type parameter là String chỉ từ kiểu `List<?>`.

**Quy trình nhận diện:** trước khi hỏi “kiểu RHS có hợp lệ với `instanceof` không?”, phải xem **cả kiểu RHS lẫn kiểu tĩnh biểu thức LHS**. Nếu LHS là Object, hãy ưu tiên RHS reifiable; nếu LHS đã có tham số generic cụ thể, Java 16+ có thể chấp nhận RHS tham số hóa tương thích.

## 6. Pattern matching for instanceof trong Java 17

Java 17 hỗ trợ viết:

~~~java
Object input = List.of("A", "B");

if (input instanceof List<?> list) {
    System.out.println(list.size());
    Object first = list.get(0);
}
~~~

Ở đây compiler đồng thời:
1. Kiểm tra input có phải List không.
2. Ràng buộc biến mới `list` trong nhánh mà pattern đúng.
3. Gán kiểu tĩnh `List<?>` cho `list`.

Không cần viết dạng cũ:

~~~java
if (input instanceof List<?>) {
    List<?> list = (List<?>) input;
    System.out.println(list.size());
}
~~~

Cả hai đều hợp lệ, nhưng pattern matching gọn hơn và giới hạn phạm vi biến hợp lý hơn.

### Phạm vi của pattern variable và short-circuit

~~~java
Object input = List.of("A", "B");

if (input instanceof List<?> list && !list.isEmpty()) {
    System.out.println(list.get(0));
}
~~~

`list` chỉ có thể dùng trong nhánh mà pattern match đã thành công, và biểu thức `&&` dùng short-circuit nên đoạn sau được đánh giá khi `list` đã có giá trị hợp lệ.

Không được dùng biến pattern ở nơi compiler không chứng minh được nó đã được khởi tạo:

~~~java
// if (input instanceof List<?> list || list.isEmpty()) { }
// Không biên dịch: ở vế phải của ||, list chưa chắc đã được gán.
~~~

### Pattern đã luôn đúng có thể bị từ chối

Trong Java 17:

~~~java
List<String> already = List.of("Java");

// if (already instanceof List<String> same) { }
// Lỗi Java 17: pattern này là unconditional pattern.
~~~

Lỗi trên có tính chất **khác** với `Object instanceof List<String>`. Kiểu nguồn `List<String>` đã là subtype của kiểu pattern `List<String>`, khiến pattern trở thành dạng không được phép trong `instanceof` của source level 17. Ngược lại, phép kiểm tra biểu thức truyền thống `already instanceof List<String>` có thể hợp lệ khi quy tắc casting conversion thỏa mãn.

Một cách pattern hữu ích là kiểm tra **kiểu con chưa chắc đúng**:

~~~java
List<String> already = new ArrayList<>();

if (already instanceof ArrayList<String> array) {
    System.out.println(array.size());
}
~~~

Tình huống này hợp lệ vì không phải mọi List<String> đều là ArrayList<String>. Lưu ý Java ở các phiên bản sau có thể phát triển quy tắc pattern; bài nhắm tới chương trình Java 17+ và trình bày riêng ràng buộc source level 17.

## 7. List<?> cho phép đọc gì và chặn thao tác ghi nào?

Sau khi thành công với:

~~~java
Object candidate = List.of("Java", 5);

if (candidate instanceof List<?> list) {
    Object first = list.get(0); // Hợp lệ.
    int count = list.size();     // Hợp lệ.

    // list.add("Kotlin");       // Không biên dịch.
}
~~~

Với `List<?>`, compiler biết danh sách có **một kiểu phần tử nào đó**, nhưng không biết kiểu chính xác là gì. Vì thế phần tử đọc được an toàn dưới dạng Object; ngược lại, thêm một String tùy ý có thể phá kiểu phần tử vốn là Integer ở một đối tượng khác.

Đừng nhầm với:

~~~java
List<Object> objects = new ArrayList<>();
objects.add("Java");
objects.add(5);
~~~

`List<Object>` là một parameterized type có E đúng bằng Object, còn `List<?>` chứa một type argument chưa xác định. Do generics có tính invariant, một `List<String>` không thể gán trực tiếp cho `List<Object>` nhưng có thể gán cho `List<?>`:

~~~java
List<String> words = List.of("A");

// List<Object> wrong = words; // Không biên dịch.
List<?> safeView = words;       // Hợp lệ.
~~~

`list.add(null)` có thể hợp lệ về **kiểu tĩnh** đối với wildcard nhưng không đảm bảo thành công: `List.of` không cho sửa đổi, và nhiều collection có chính sách null riêng. Bài này tránh thao tác ghi vào cấu trúc chưa biết type arguments.

## 8. Sau `instanceof List<?>`, cách tạo `List<T>` đã xác minh

Một pattern `candidate instanceof List<?> input` chỉ kiểm tra **container**. Nếu API cần thực sự có `List<String>`, nó phải kiểm tra các phần tử rồi xây kết quả typed mới, không cast unchecked toàn bộ danh sách.

Với class token `Class<T>`: (1) xác nhận đối tượng là `List<?>`; (2) duyệt từng `Object` và yêu cầu `elementType.isInstance(item)`; (3) dùng `elementType.cast(item)` để đưa giá trị hợp lệ vào `ArrayList<T>` mới; (4) nếu dùng `List.copyOf`, công bố rõ chính sách **không nhận null** và không sửa đổi danh sách kết quả.

Ví dụ `checkedList(List.of("A","B"), String.class)` tạo một kết quả String typed, còn danh sách `List.of("A", 1)` phải bị từ chối dù vẫn khớp `instanceof List<?>`. Phương thức `checkedList` được triển khai đầy đủ, chạy độc lập ở chương trình ngay bên dưới. Bài chuyên về xác minh **mọi phần tử** trình bày thêm chân lý rỗng, null, nghiệp vụ và concurrent mutation.

## 9. Generic lồng nhau phải kiểm tra từng tầng

Để nhận `Map<String, List<Integer>>` từ `Object`, `candidate instanceof Map<?, ?>` chỉ là kiểm tra đầu tiên. Cần kiểm tra **mỗi key** là `String`, **mỗi value** là `List<?>`, rồi **mỗi phần tử** của list con là `Integer`. Kết quả typed mới được tạo sau khi các tầng dữ liệu phù hợp; không thể dùng `(Map<String,List<Integer>>) candidate` như một validator.

Chương trình hoàn chỉnh dưới đây cài đặt `checkedScores` và đối chiếu `nestedOdd=[1, 3]`. Việc tạo bản sao tránh chia sẻ cấu trúc collection có thể sửa với nguồn nhưng không tự tạo deep copy phần tử, cũng không thay thế yêu cầu nhất quán khi nguồn đang bị sửa đồng thời.


## 10. Chương trình Java 17+ hoàn chỉnh, có thể biên dịch và chạy

Lưu tệp **InstanceofGenericsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class InstanceofGenericsDemo {
    static <T> List<T> checkedList(
            Object candidate, Class<T> elementType) {

        if (!(candidate instanceof List<?> input)) {
            throw new IllegalArgumentException("List required");
        }

        List<T> result = new ArrayList<>();

        for (Object item : input) {
            if (!elementType.isInstance(item)) {
                throw new IllegalArgumentException("Unexpected element");
            }
            result.add(elementType.cast(item));
        }

        return List.copyOf(result);
    }

    static Map<String, List<Integer>> checkedScores(Object candidate) {
        if (!(candidate instanceof Map<?, ?> input)) {
            throw new IllegalArgumentException("Map required");
        }

        Map<String, List<Integer>> result = new HashMap<>();

        for (Map.Entry<?, ?> entry : input.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalArgumentException("String key required");
            }

            result.put(
                    key,
                    checkedList(entry.getValue(), Integer.class)
            );
        }

        return Map.copyOf(result);
    }

    public static void main(String[] args) {
        Object unknown = List.of("Java", 7);

        System.out.println(
                "listWildcard=" + (unknown instanceof List<?>)
        );
        System.out.println(
                "mapWildcard=" + (unknown instanceof Map<?, ?>)
        );
        System.out.println(
                "nullMatch=" + (((Object) null) instanceof List<?>)
        );

        if (unknown instanceof List<?> list) {
            System.out.println("size=" + list.size());
            System.out.println("first=" + list.get(0));
        }

        List<String> known =
                new ArrayList<>(List.of("Java"));

        // Java 16+: hợp lệ vì LHS đã có generic type String.
        System.out.println(
                "knownSubtype=" +
                (known instanceof ArrayList<String>)
        );

        if (known instanceof ArrayList<String> array) {
            System.out.println("patternFirst=" + array.get(0));
        }

        Object arrayCandidate = new List<?>[] {
                List.of("x"), List.of(4)
        };
        System.out.println(
                "wildcardArray=" +
                (arrayCandidate instanceof List<?>[])
        );

        System.out.println(
                "classWildcard=" +
                (String.class instanceof Class<?>)
        );

        System.out.println(
                "validated=" +
                checkedList(List.of("A", "B"), String.class)
        );

        try {
            checkedList(unknown, String.class);
        } catch (IllegalArgumentException error) {
            System.out.println("invalid=IllegalArgumentException");
        }

        Map<String, List<Integer>> scores =
                checkedScores(
                        Map.of(
                                "odd", List.of(1, 3),
                                "even", List.of(2, 4)
                        )
                );
        System.out.println("nestedOdd=" + scores.get("odd"));

        // Thao tác raw sau đây cố ý làm nhiễm dữ liệu của List<String>.
        List raw = known;
        raw.add(42);

        // instanceof không xác minh type argument String ở runtime.
        System.out.println(
                "stillArrayList=" +
                (known instanceof ArrayList<String>)
        );

        try {
            String bad = known.get(1);
            System.out.println(bad);
        } catch (ClassCastException error) {
            System.out.println("polluted=ClassCastException");
        }
    }
}
~~~

Biên dịch ở mức ngôn ngữ Java 17 bằng JDK có hỗ trợ `--release 17`:

~~~bash
javac --release 17 -Xlint:unchecked InstanceofGenericsDemo.java
java InstanceofGenericsDemo
~~~

Compiler phát **unchecked warning** ở `raw.add(42)` vì lời gọi trên raw List. Đây là cảnh báo của quá trình biên dịch, không phải stdout chương trình.

Stdout chính xác:

~~~text
listWildcard=true
mapWildcard=false
nullMatch=false
size=2
first=Java
knownSubtype=true
patternFirst=Java
wildcardArray=true
classWildcard=true
validated=[A, B]
invalid=IllegalArgumentException
nestedOdd=[1, 3]
stillArrayList=true
polluted=ClassCastException
~~~

### Phân tích những dòng quan trọng

**`listWildcard=true`:** đầu vào là một List, bất kể nó chứa String và Integer. Kiểu `List<?>` chấp nhận mọi loại phần tử nhưng không xác thực loại cụ thể.

**`mapWildcard=false`:** đối tượng này là List, không phải Map. Việc `Map<?, ?>` có cú pháp hợp lệ không quyết định kết quả `true`.

**`nullMatch=false`:** `instanceof` trên null luôn trả false trong các ví dụ này; kiểm tra không ném NullPointerException chỉ vì tham chiếu null.

**`knownSubtype=true` và `patternFirst=Java`:** biến có kiểu `List<String>`, nhưng runtime object là ArrayList. Java 17 cho phép kiểm tra `ArrayList<String>` theo quy tắc casting conversion.

**`wildcardArray=true`:** JVM kiểm tra cấu trúc array với component type tương thích List; nó không xác thực generic element type trong từng List của array.

**`validated=[A, B]`:** hàm kiểm tra dữ liệu thực tế chỉ chấp nhận các phần tử String và tạo danh sách mới.

**`invalid=IllegalArgumentException`:** `unknown` chứa Integer nên validator từ chối; `instanceof List<?>` vẫn đã thành công ở bước trước.

**`nestedOdd=[1, 3]`:** validator lồng nhau kiểm tra Map, key String, List và từng Integer trước khi tạo giá trị có kiểu.

**`stillArrayList=true` nhưng `polluted=ClassCastException`:** alias raw đưa một Integer vào ArrayList vốn được giữ qua `List<String>`. `instanceof ArrayList<String>` không phát hiện sai phần tử; lỗi xuất hiện khi đọc như String và kiểm tra kiểu runtime thất bại. Đây là minh chứng rằng kiểm tra lớp runtime không bằng xác thực generic arguments.

## 11. Array của wildcard-parameterized types

Một trường hợp thường bị bỏ sót:

~~~java
List<?>[] lists = new List<?>[2];
lists[0] = List.of("A");
lists[1] = List.of(123);

Object value = lists;
boolean isListArray = value instanceof List<?>[]; // true.
~~~

`List<?>` là reifiable theo ngôn ngữ, do đó array `List<?>[]` hợp lệ. Runtime kiểm tra array có component type phù hợp `List`; **không** chứng minh phần tử của từng danh sách có một type argument cụ thể.

Ngược lại, không được tạo array generic cụ thể trực tiếp:

~~~java
// List<String>[] illegal = new List<String>[2];
// Lỗi: generic array creation.
~~~

Và khi vế trái có kiểu Object, phép kiểm tra `value instanceof List<String>[]` không được dùng như một cách xác minh mảng danh sách chuỗi.

Mảng trong Java mang thông tin kiểu thành phần runtime và có thể có kiểm tra `ArrayStoreException`, trong khi generics dùng erasure. `List<?>[]` phối hợp hai cơ chế nhưng không vượt qua giới hạn kiểm tra sâu của generic arguments.

Nếu không cần mảng, nhiều API hiện đại thuận tiện và nhất quán hơn khi dùng `List<List<?>>` hoặc một cấu trúc generic phù hợp thay vì generic array.

## 12. Raw List và List<?> trong instanceof khác nhau thế nào?

Hai kiểm tra sau đều có thể nhận ra một đối tượng triển khai List:

~~~java
Object input = List.of("Java");

boolean rawCheck = input instanceof List;
boolean wildcardCheck = input instanceof List<?>;
~~~

Khác biệt đáng chú ý nằm ở **cách biểu đạt kiểu** và hành vi khi ta tiếp tục sử dụng kết quả:

~~~java
if (input instanceof List<?> list) {
    Object element = list.get(0);
    // list.add("new"); // Compiler chặn.
}
~~~

`List<?>` giữ lại thông tin rằng danh sách có một kiểu phần tử chưa biết. Nếu cast sang raw `List` rồi gọi add, code có thể mất kiểm tra generic và phát cảnh báo unchecked.

~~~java
if (input instanceof List) {
    List raw = (List) input;
    // raw.add(42); // Có thể sinh unchecked warning và gây nhiễm dữ liệu.
}
~~~

Bản thân `instanceof List` không phải luôn có lỗi hoặc bắt buộc sinh warning. Vấn đề là sử dụng **raw type** trong code mới không cung cấp sự an toàn generic như wildcard.

Với Java 17, khuyến nghị thường là dùng `instanceof List<?> list` cho mục đích nhận biết một collection chưa biết kiểu phần tử, rồi xác minh từng phần tử nếu miền nghiệp vụ yêu cầu một loại cụ thể.

## 13. Các trường hợp hợp lệ và không hợp lệ khác

### 13.1. Multiple unbounded wildcards

~~~java
Object value = Map.of("one", 1);

if (value instanceof Map<?, ?> map) {
    System.out.println(map.size());
}
~~~

`Map<?, ?>` hợp lệ vì cả key type và value type đều không xác định. Nhưng `Map<String, ?>` từ một biến Object không được tự động chấp nhận như một phép xác nhận String cho key.

### 13.2. Kiểm tra Optional<?> và Class<?>

~~~java
Object maybe = java.util.Optional.of("Java");
boolean optional = maybe instanceof java.util.Optional<?>;

Object classObject = String.class;
boolean classToken = classObject instanceof Class<?>;
~~~

Các phép kiểm tra trên hợp lệ; với Optional<?> không thể kết luận giá trị bên trong là String, cũng như với Class<?> chưa có type parameter T cụ thể.

### 13.3. instanceof không chấp nhận primitive ở RHS trong Java 17

~~~java
Object value = Integer.valueOf(3);

boolean boxed = value instanceof Integer; // Hợp lệ.
// boolean primitive = value instanceof int; // Không biên dịch ở Java 17.
~~~

Generic type arguments cũng không được thay thế bằng primitive:

~~~java
// List<int> invalid; // Không hợp lệ: type argument cần reference type.
List<Integer> valid = List.of(1, 2, 3);
~~~

### 13.4. Kiểu đã biết vẫn không có quyền kiểm tra mọi tham số tùy ý

~~~java
List<String> known = List.of("Java");

// boolean wrong = known instanceof ArrayList<Integer>;
// Không có casting conversion phù hợp giữa tham số String và Integer.
boolean possible = known instanceof ArrayList<String>;
~~~

Sự nới lỏng Java 16+ **không có nghĩa** mọi parameterized RHS đều hợp lệ. Hệ thống kiểu vẫn xét quan hệ có thể cast được giữa vế trái và RHS.

## 14. Những lỗi compiler cần phân biệt

**Lỗi 1 — không thể kiểm tra type argument từ Object**

~~~java
Object object = List.of("Java");
// boolean invalid = object instanceof List<String>;
~~~

Trình biên dịch Java 17 có thể báo:

~~~text
Object cannot be safely cast to List<String>
~~~

Nguyên nhân: không có casting conversion phù hợp để làm phép kiểm tra tham số String an toàn từ Object.

**Lỗi 2 — nguồn List<?> nhưng đích muốn String**

~~~java
List<?> unknown = List.of("Java");
// boolean invalid = unknown instanceof ArrayList<String>;
~~~

Compiler không biết wildcard thật sự là String; từ `List<?>` không có bằng chứng an toàn cho kiểu tham số hóa cụ thể `ArrayList<String>`.

**Lỗi 3 — pattern không thêm bất kỳ kiểm tra kiểu có ý nghĩa nào trong Java 17**

~~~java
List<String> known = List.of("Java");
// if (known instanceof List<String> same) { }
// Java 17 báo lỗi pattern đã luôn đúng theo kiểu tĩnh.
~~~

Đừng nhầm với dạng toán tử boolean truyền thống vốn có thể được phép. Ví dụ `known instanceof ArrayList<String> array` là pattern có ý nghĩa vì chỉ một số List mới là ArrayList.

**Lỗi 4 — tin rằng instanceof List<?> chứng minh phần tử là String**

~~~java
Object input = List.of("Java", 7);

if (input instanceof List<?> list) {
    // String first = (String) list.get(1); // Runtime ClassCastException.
}
~~~

Cần validator khi muốn bảo đảm loại phần tử, không chỉ cast.

**Lỗi 5 — dùng instanceof Map<?,?> rồi ép thẳng thành Map<String,List<Integer>>**

~~~java
Object input = Map.of("scores", List.of("wrong"));

if (input instanceof Map<?, ?> map) {
    // Unchecked cast bên dưới không kiểm tra sâu:
//  Map<String, List<Integer>> invalid =
//          (Map<String, List<Integer>>) map;
}
~~~

Bản thân Map tồn tại, nhưng key/value generic chưa được kiểm tra. Hãy kiểm tra key và list con rồi xây cấu trúc có kiểu.

## 15. Quy trình ra quyết định khi viết instanceof với generics

1. **Ghi kiểu tĩnh của vế trái.** Nếu là Object, không suy luận type arguments từ runtime object.
2. **Xác định mục tiêu kiểm tra.** Chỉ hỏi “đây có phải List không?” hay phải xác nhận từng phần tử là String?
3. **Với Object và collection không biết type arguments**, dùng `List<?>` hoặc `Map<?, ?>`.
4. **Nếu vế trái đã có parameterized type**, xem kiểu RHS có casting conversion hợp lệ hay không; Java 16+ có thể cho phép kiểm tra tham số cụ thể trong bối cảnh này.
5. **Nếu muốn binding pattern**, kiểm tra thêm quy tắc flow scoping và unconditional pattern của source version. Trên Java 17, một pattern mà kiểu nguồn đã là subtype của kiểu pattern có thể bị từ chối.
6. **Không xem instanceof là validator tổng quát cho nested generics.** Muốn `List<String>` hoặc `Map<String,List<Integer>>` thật sự sạch, phải xác nhận từng tầng/phần tử.
7. **Dùng API an toàn và tạo bản sao** khi nhận dữ liệu từ vùng không tin cậy. Hạn chế raw types, unchecked casts và mutable aliases.
8. **Kiểm chứng bằng compiler mục tiêu**, ví dụ `javac --release 17`, thay vì suy luận từ mã chạy ở JDK phiên bản khác.

Một chú ý về bảo trì: cú pháp pattern matching và quy tắc đối với unconditional patterns có thay đổi theo phiên bản Java. Bài dùng Java 17 làm chuẩn cho ví dụ chạy; khi áp dụng trên JDK mới hơn, nên kiểm tra chẩn đoán theo `--release` hoặc `--source` tương ứng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `Object value` chứa một `List<String>`. Có thể viết `value instanceof List<String>` không?

**Đáp án:** Không trong Java 17. Kiểu tĩnh Object không cung cấp thông tin để kiểm tra tham số String bằng phép test runtime. Dùng `value instanceof List<?>` rồi xác thực từng phần tử nếu cần.

**Câu 2.** `value instanceof List<?>` trả true có chứng minh tất cả phần tử là String không?

**Đáp án:** Không. Nó chỉ kiểm tra runtime object triển khai List; List có thể chứa String, Integer hoặc dữ liệu khác.

**Câu 3.** Vì sao `List<String> known` lại có thể dùng `known instanceof ArrayList<String>`?

**Đáp án:** Từ Java 16, `instanceof` có thể dùng một non-reifiable parameterized type khi kiểu tĩnh LHS cho phép casting conversion phù hợp tới RHS. Kiểu String đã được mô tả bởi tham chiếu List<String>, còn runtime kiểm tra đối tượng có phải ArrayList.

**Câu 4.** Nếu `known instanceof ArrayList<String>` true, nó có phát hiện được Integer được đưa vào qua raw alias không?

**Đáp án:** Không. Runtime test không xác thực kiểu từng phần tử. Đọc phần tử bị nhiễm như String có thể ném ClassCastException.

**Câu 5.** `Map<?, ?>` có tự chứng minh map chứa `String` key và `List<Integer>` value không?

**Đáp án:** Không. Cần kiểm tra các entry, key, List và các Integer bên trong.

**Câu 6.** Có thể dùng `value instanceof List<?>[]` từ Object không?

**Đáp án:** Có. Array với component type List<?> là reifiable, nhưng runtime không kiểm tra kiểu phần tử nằm trong từng List của array.

**Câu 7.** Tại sao `if (known instanceof List<String> same)` bị từ chối ở Java 17 khi known đã là List<String>?

**Đáp án:** Đây là unconditional type pattern theo kiểu tĩnh; quy tắc pattern matching của Java 17 từ chối nó. Lỗi khác với việc không thể cast an toàn từ Object sang List<String>.

**Câu 8.** `List<?>` và raw `List` khác nhau ra sao sau kiểm tra instanceof?

**Đáp án:** Chúng có thể kiểm tra cùng runtime List, nhưng `List<?>` giữ thông tin một kiểu phần tử chưa biết và chặn thêm tùy ý; raw List bỏ type argument và dễ tạo thao tác unchecked.

**Câu 9.** Cách đáng tin để nhận dữ liệu `Object` và tạo `List<String>` không có phần tử sai kiểu?

**Đáp án:** Dùng `instanceof List<?>`, duyệt từng phần tử kiểm tra `String.class.isInstance`, sao chép các phần tử đã hợp lệ vào `List<String>`, và quy định rõ chính sách null/mutation.

## 17. Ghi nhớ

**`instanceof List<?>` là hợp lệ và hữu ích** vì kiểm tra được runtime List mà không hứa hẹn điều gì về kiểu phần tử. `List<String>` không phải một bài kiểm tra runtime tổng quát từ `Object`.

Tuy nhiên, **Java 16+ không cấm mọi parameterized RHS**: khi vế trái đã có generic type phù hợp, phép kiểm tra như `List<String> x; x instanceof ArrayList<String>` có thể biên dịch. Compiler dùng kiểu tĩnh của biểu thức để xét casting conversion, nhưng runtime vẫn không xác thực nội dung generic arguments.

Muốn chứng minh dữ liệu nhiều tầng thật sự phù hợp `List<String>` hoặc `Map<String,List<Integer>>`, phải **kiểm tra từng phần tử và xây kết quả có kiểu rõ ràng**. Phân biệt được ba tầng — **kiểu tĩnh**, **điều kiện instanceof tại runtime**, và **xác thực nội dung** — là chìa khóa để sử dụng generics an toàn.
