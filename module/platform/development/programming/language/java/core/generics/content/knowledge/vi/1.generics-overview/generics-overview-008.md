# Kiến thức nền và trình tự học Generics trong Java Core

Bài này là **bản đồ học tập và tự đánh giá** cho người bắt đầu Java Generics. Thay vì học thuộc từng cú pháp `<T>`, `? extends T` và `? super T`, bạn sẽ đi từ những kiến thức cần có, qua các bài học theo đúng quan hệ phụ thuộc, rồi thực hiện một chương trình tổng hợp và tự kiểm tra mức độ thành thạo.

Generics giúp compiler kiểm tra **quan hệ giữa các kiểu** trong cấu trúc dữ liệu và API. Đích học tập không phải viết nhiều dấu ngoặc nhọn góc, mà là **đọc được chữ ký**, **dự đoán được câu lệnh có biên dịch không** và **biết giới hạn của bảo đảm kiểu khi chạy**.

Bài học dùng **Java 17+**; có thể thực hành với JDK và trình soạn thảo thông thường, không cần Spring, Hibernate, Maven, JUnit hay thư viện ngoài JDK. Nếu đã quen Java cơ bản, dùng phần kiểm tra đầu vào để rút ngắn những chặng bạn đã thành thạo.

## 1. Kết quả cần đạt và cách dùng lộ trình

Hoàn thành lộ trình nghĩa là bạn tự làm được những việc sau:

1. Nêu sự khác nhau giữa **kiểu tĩnh của biến**, **class thực tế của object** và **type arguments** do compiler biết.
2. Đọc/viết một class `Box<T>`, interface `Store<K,V>` và method `static <T> T first(List<T>)`.
3. Phân biệt **type parameter**, **type variable**, **type argument**, **parameterized type**, **raw type** và **wildcard** bằng ví dụ riêng.
4. Dự đoán lời gọi `add`, `get`, `set` hợp lệ theo `List<T>` và hiểu vì sao `List<Integer>` không tự là `List<Number>`.
5. Chọn `? extends T` cho một nguồn đọc và `? super T` cho một đích ghi khi **dòng dữ liệu đúng là một chiều**.
6. Giữ một `T` có tên khi API cần liên kết kiểu ở **nhiều vị trí** (đầu vào, kết quả hoặc thao tác đọc–ghi hai chiều).
7. Giải thích type erasure, raw/unchecked warnings, và vì sao một `ClassCastException` có thể chỉ xuất hiện lúc dùng giá trị.
8. Đọc được một số generic signatures của thư viện chuẩn và thiết kế một phương thức đủ an toàn để caller không phải cast.
9. Biết lúc nào cần **kiểu cụ thể, interface hoặc một phép kiểm tra runtime**, thay vì tạo generic abstraction không cần thiết.

Một bài không được xem là “đã học” chỉ vì bạn xem xong ví dụ. Hãy **đoán kết quả trước khi chạy**, giải thích đúng lý do compiler chấp nhận/từ chối, rồi tự sửa một biến thể để chứng minh hiểu quy tắc.

## 2. Kiểm tra kiến thức nền trước khi học

| Kiến thức cần có | Phép tự kiểm tra | Tối thiểu cần hiểu |
| --- | --- | --- |
| Kiểu tham chiếu và object | `Number n = Integer.valueOf(5);` | Biến có kiểu tĩnh Number, object có runtime class Integer. |
| Primitive và wrapper | `int` khác `Integer` thế nào? | Generics dùng reference type arguments; boxing/unboxing có thể xảy ra. |
| `Object` và cast | `Object x = 42; String s = (String) x;` | Cast có thể biên dịch nhưng fail với ClassCastException khi chạy. |
| Class và interface | `Dog extends Animal`, `implements Runnable` | Phân biệt subtype, inheritance và interface contract. |
| Override và overload | `Animal a = new Dog(); a.sound();` | Runtime dispatch dùng bản override; overload chọn chủ yếu ở compile time. |
| Collection căn bản | `List`, `Set`, `Map`, `add`, `get` | Biết List lưu theo vị trí, Map theo khóa; hiểu khả năng sửa phụ thuộc implementation. |
| Compile vs runtime | Lỗi `incompatible types` khác `ClassCastException` thế nào? | Lỗi compile time ngăn tạo code; exception xuất hiện khi một operation chạy. |
| Method signatures | Kiểu trả về và kiểu tham số nằm đâu? | Có thể đọc chữ ký generic dựa trên cấu trúc method thông thường. |

Nếu chưa chắc cột thứ ba, ưu tiên ôn Java Core trước. Riêng khi chưa biết `List.of` và `ArrayList`, cần nhớ: `List.of(...)` trả list không cho sửa; `new ArrayList<>(...)` thường tạo list có thể thêm/thay phần tử. Đây là khác biệt runtime về mutability, **không phải** khác biệt về generic type arguments.

### Những thứ chưa bắt buộc

Bạn không cần học sâu lambda, Stream, reflection, class loaders, AspectJ hay framework trước khi học generic class và method. `Function<T,R>` hoặc reflection sẽ xuất hiện ở giai đoạn đọc API nâng cao; chỉ bổ sung những phần cần thiết khi đi tới chặng đó.

## 3. Sơ đồ phụ thuộc của các chặng

~~~text
NỀN TẢNG JAVA
Kiểu tĩnh/runtime ── Object/cast ── class/interface
           │                │
           └──── Collection/Method ─────┐
                                        ▼
CHẶNG 1: Vì sao generics?  List<String> vs List<Object>
                                        ▼
CHẶNG 2: Type parameter, type argument, generic class/interface
                                        ▼
CHẶNG 3: Generic method, inference, bounded type variable
                                        ▼
CHẶNG 4: Invariance, wildcard, PECS, read/write relationship
                                        ▼
CHẶNG 5: Type erasure, raw type, warnings, runtime boundaries
                                        ▼
CHẶNG 6: Đọc chữ ký JDK và quyết định thiết kế API
                                        ▼
CHẶNG 7: Mini-project, regression tests, tự đánh giá
~~~

Một **chặng** không tương ứng với một ngày học cố định. Chuyển chặng khi làm được đầu ra và bài kiểm tra của chặng trước; nếu vướng wildcard, quay lại **subtyping và invariant generic collection**, không cố học thuộc câu PECS.

## 4. Chặng 1 — Tại sao cần một hợp đồng kiểu?

**Mục tiêu:** nhận ra vấn đề khi một API chỉ trả Object hoặc một collection thiếu ràng buộc kiểu.

Bài thực hành:
- Tạo `List<Object>` chứa `"Java"` và `17`. Đọc phần tử đầu bằng cast String; xác định vì sao cast có thể thành công.
- Đọc phần tử thứ hai dưới kiểu String; dự đoán exception. Sau đó sửa bằng danh sách `List<String>` để compiler từ chối `add(17)` ngay lúc biên dịch.
- Phân biệt **một collection dùng generic với type argument Object** và **một raw collection `List`**: cả hai không mang hợp đồng “chỉ String”, nhưng raw List còn bỏ qua kiểm tra generic tại một số thao tác.

Cần trả lời: “Chương trình sai kiểu từ lúc đưa dữ liệu vào, hay chỉ sai ở phép cast lúc dùng? Cách khai báo nào cho compiler biết quy tắc phải giữ?”

**Tiêu chí qua chặng:** tự viết được hai phép thử (một compile error, một runtime exception) và chỉ rõ operation gây ra mỗi loại.

Với người mới, đây là bài quan trọng về **động cơ dùng Generics**. Không cần đi sâu bytecode ở chặng này; chỉ cần thấy rằng kiểu được mô tả chính xác trong API giúp chuyển nhiều lỗi sang thời điểm sớm hơn.

## 5. Chặng 2 — Ngôn ngữ của generic types

**Mục tiêu:** hiểu chữ ký trước khi kết hợp nhiều cơ chế. Hãy phân loại các thành phần sau:

~~~java
final class Box<T> {
    private final T value;

    Box(T value) { this.value = value; }

    T get() { return value; }
}

// Từ một method sử dụng:
// Box<String> box = new Box<>("Java");
~~~

- `T` trong `class Box<T>`: **type parameter** được khai báo.
- Các vị trí `T` trong field, constructor, return type: **type variable** được tham chiếu.
- `String` trong `Box<String>`: **type argument** cụ thể.
- `Box<String>`: một **parameterized type**.
- `new Box<>()`: **diamond**, compiler suy luận type argument từ ngữ cảnh; không phải raw instantiation.
- `Box` không có đối số kiểu ở vị trí sử dụng: có thể là **raw type** trong bối cảnh tương ứng, làm suy yếu type checking.
- `Box<?>`: parameterized type có **wildcard** chưa biết type argument cụ thể, khác raw Box.

Bài thực hành:
1. Viết `Pair<K,V>`, thử `Pair<String,Integer>` và `Pair<Integer,String>`.
2. Viết interface `Formatter<T>` có `String format(T value)` và một implementation nhận Integer.
3. Đánh dấu đâu là tên type parameter, đâu là đối số trong `Map<String,List<Integer>>`.
4. Giải thích vì sao `List<int>` không hợp lệ nhưng `List<Integer>` hợp lệ.

**Tiêu chí qua chặng:** đọc đúng hai type arguments trong một nested parameterized type và không nhầm phạm vi T của class với kiểu thực tế của object.

## 6. Chặng 3 — Method generic, type inference và giới hạn

**Mục tiêu:** hiểu khi nào một method cần **một type parameter của riêng nó**.

~~~java
static <T> T last(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("empty");
    }
    return values.get(values.size() - 1);
}
~~~

`<T>` đứng **trước kiểu trả về** và mô tả rằng kết quả có cùng kiểu phần tử với list đầu vào. Compiler có thể suy luận T từ đối số và ngữ cảnh lời gọi. Nếu method static nằm trong generic class, nó vẫn phải tự khai báo những type variables mà method static cần sử dụng, chứ không lấy T instance của class một cách tự động.

Bài thực hành:
- Gọi `last(List.of("A","B"))` và `last(List.of(10,20))`. Dự đoán kiểu tĩnh và giá trị trả về.
- Thử `String invalid = last(List.of(1,2));` rồi quan sát lỗi compiler.
- Thử method `static <T extends Number> double twice(T x)` sử dụng `doubleValue()`.
- So sánh generic method với một method nhận Object và trả Object: method nào **bảo toàn quan hệ kiểu** cho caller?

**Tiêu chí qua chặng:** giải thích được tại sao cú pháp `<T>` cần có ở declaration và vì sao `T extends Number` cho phép gọi các phương thức Number. Không đánh đồng **generic bounds** với khai báo một class kế thừa.

## 7. Chặng 4 — Invariance, wildcard và luồng dữ liệu

Đây thường là chặng phải luyện nhiều phép gọi nhất. Việc `Integer extends Number` **không** khiến `List<Integer> extends List<Number>`. Nếu có thể gán trực tiếp, một API nhận List<Number> sẽ có thể thêm Double vào List<Integer>, phá cam kết dữ liệu của caller.

Chọn chữ ký dựa trên **vai trò** của collection:

| Mục đích | Chữ ký gợi ý | Thao tác an toàn |
| --- | --- | --- |
| Không quan tâm element type | `List<?>` | Xem kích thước, đọc ra Object; không thêm giá trị non-null tùy ý. |
| Nguồn chỉ được đọc như Number | `List<? extends Number>` | Đọc được Number từ List<Integer>/List<Double>. |
| Đích nhận Integer | `List<? super Integer>` | Thêm Integer vào List<Integer>/List<Number>/List<Object>. |
| Vừa đọc vừa ghi cùng loại | `List<T>` | Lấy T và ghi lại T vào chính list khi implementation cho phép. |
| Nguồn/đích truyền một chiều | `List<? extends T>` và `List<? super T>` | Copy các giá trị T theo hướng producer → consumer. |

Quy tắc gợi nhớ **PECS (Producer Extends, Consumer Super)** chỉ là cách chọn đúng vị trí khi dữ liệu đi một chiều; nó **không** khuyên dùng wildcard ở mọi collection.

Bài thực hành:
- Viết hàm tính tổng nhận được cả `List<Integer>` và `List<Double>`, chỉ đọc phần tử.
- Viết hàm thêm Integer vào đích `List<Number>` và `List<Object>`.
- Viết phương thức `copyInto` có một T dùng chung cho nguồn và đích, với wildcards đúng chiều.
- So sánh với một phép **hoán đổi giá trị hai chiều** giữa hai `List<T>`; giải thích vì sao hai `List<?>` độc lập không tự cho phép hoán đổi chéo các phần tử.

**Tiêu chí qua chặng:** với mỗi lỗi compiler ở `add/get`, bạn chỉ rõ “kiểu đích có thể thực sự là gì?” thay vì trả lời máy móc “extends chỉ đọc, super chỉ ghi”.

### Chú ý thao tác trên collection vẫn phải được phép ở runtime

`List<? super Integer>` cho phép gọi `add(1)` theo **hệ kiểu**, nhưng nếu object là list không sửa được, thao tác vẫn có thể ném UnsupportedOperationException. Generics không mô tả mutability của mọi implementation.

## 8. Chặng 5 — Erasure và biên giới an toàn runtime

**Mục tiêu:** hiểu phần nào được compiler bảo vệ, phần nào JVM có thể kiểm tra, và khi nào cần validation riêng.

~~~text
List<String> (compile-time contract)
       │ kiểm tra add/get theo String
       ▼
Class runtime thường chỉ là ArrayList
       │ raw/unchecked aliases có thể phá invariant
       ▼
Typed read / inserted checkcast
       └── có thể phát ClassCastException
~~~

Các quy tắc cần tự chứng minh:
- `T` unbounded thường bị xóa thành Object; `T extends Number` bị xóa theo Number.
- Hai ArrayList instances được tạo bằng `new ArrayList<String>()` và `new ArrayList<Integer>()` thường có cùng runtime class.
- `instanceof List<?>` kiểm tra runtime List; `instanceof List<String>` không dùng được để xác minh type arguments cụ thể từ một biến Object.
- Không trực tiếp tạo `new T()`, `new T[10]` hoặc `new List<String>[10]` theo cách thông thường.
- Raw List/unchecked cast có thể làm dữ liệu sai kiểu tồn tại **trước** khi typed read gây ClassCastException.
- Kiểu generic không tự bảo đảm null policy, nội dung đúng schema hoặc phân quyền truy cập.

Bài thực hành:
1. Dùng `-Xlint:rawtypes,unchecked` để quan sát warnings của một raw alias được tạo cố ý trong file thử nghiệm.
2. Tách rõ **lúc ghi sai** và **lúc đọc thành String** trong test; dự đoán vì sao cảnh báo compile time không tự chặn write.
3. Nếu nhận `List<?>` từ nguồn không tin cậy, kiểm tra từng phần tử `instanceof String` rồi tạo bản sao typed. Đừng biến `(List<String>) unknown` thành “validator”.
4. Đối chiếu array covariance: Object[] alias tới String[] từ chối Integer bằng ArrayStoreException ngay tại write, khác nhiều generic collection cases.

**Tiêu chí qua chặng:** diễn giải được một lỗi ClassCastException theo **dataflow** và biết phòng ngừa ở boundary thay vì chỉ thêm một catch cuối pipeline.

## 9. Chặng 6 — Đọc JDK API và lựa chọn thiết kế

Hãy đọc chữ ký của API chuẩn **từng tham số một**, không chỉ copy ví dụ:

| API cần đọc | Hãy xác định |
| --- | --- |
| `List<E>.add(E)`, `List<E>.get(int)` | E được dùng để nhận và trả gì? |
| `Map<K,V>.put(K,V)`, `entrySet()` | K/V mô tả quan hệ khóa–giá trị ra sao? |
| `Optional<T>.map(Function<? super T,? extends U>)` | T biến thành U qua function ở chặng nào? |
| `Collections.copy(List<? super T>,List<? extends T>)` | Đích nhận, nguồn cấp T; tại sao đích phải có sẵn đủ phần tử? |
| `Comparator<? super T>`, `Comparable<? super T>` | Tại sao có thể dùng comparator của supertype? |
| `Stream.map` và `Stream.flatMap` | Khác nhau ở một R với một Stream<R> như thế nào? |

Một lưu ý về API thực tế: `Collections.copy` **thay thế theo chỉ số**, không tự `addAll` vào cuối; destination phải đủ kích thước. Đọc đúng generic signature **chưa đủ** nếu bỏ qua hợp đồng về mutability và dữ liệu.

Bài thực hành:
- Lấy chữ ký thật của hai API JDK rồi **đánh dấu nơi tiêu thụ T, nơi sản xuất R**.
- Đọc một pipeline `Stream<String> → map(String::length) → Stream<Integer> → toList()` và đoán kiểu ở từng bước.
- So sánh API `print(Object)` với `<T> void print(T)`: nếu chỉ chuyển mọi giá trị thành String và không có liên hệ kiểu khác, vì sao T có thể không cần thiết?

**Tiêu chí qua chặng:** giải thích được **chữ ký trước khi chạy thử**, đồng thời ghi rõ các giả định về null, empty collection, mutability và exception behavior.

## 10. Chặng 7 — Bài tổng hợp kết nối kiến thức

Mục tiêu bài tổng hợp **không phải lặp lại một loạt Box/PECS demos**, mà kết nối một cách có chủ đích: record generic, method generic có input→output linkage, một phép chuyển dữ liệu một chiều, một phép biến đổi đầu ra và quan sát class runtime.

Lưu thành **GenericsRoadmapDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.function.Function;

public class GenericsRoadmapDemo {
    record Attempt<T>(String topic, T value) {}

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }
        return values.get(0);
    }

    static <T> void copyInto(
            List<? extends T> source,
            List<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    static <T, R> List<R> transform(
            Collection<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> output = new ArrayList<>();
        for (T item : source) {
            output.add(mapper.apply(item));
        }
        return output;
    }

    public static void main(String[] args) {
        Attempt<List<String>> lesson = new Attempt<>(
                "syntax", List.of("Type", "Bound")
        );

        System.out.println("first=" + first(lesson.value()));

        List<CharSequence> copied = new ArrayList<>();
        copyInto(lesson.value(), copied);
        System.out.println("copied=" + copied);

        List<Integer> sizes = transform(
                copied, CharSequence::length
        );
        System.out.println("lengths=" + sizes);

        System.out.println(
                "sameClass=" +
                (new ArrayList<String>().getClass()
                        == new ArrayList<Integer>().getClass())
        );
    }
}
~~~

Biên dịch và chạy với Java 17:

~~~bash
javac --release 17 -Xlint:all GenericsRoadmapDemo.java
java GenericsRoadmapDemo
~~~

Stdout:

~~~text
first=Type
copied=[Type, Bound]
lengths=[4, 5]
sameClass=true
~~~

### Giải thích luồng kiểu

1. `Attempt<T>` nhận T là `List<String>`, vì vậy `lesson.value()` có kiểu `List<String>`, không phải Object.
2. `first` nhận `List<String>` nên T được suy luận là String và trả String.
3. `copyInto` nhận nguồn List<String> và đích List<CharSequence> theo PECS, sao chép hai phần tử mà không đòi biến List<String> thành List<CharSequence>.
4. `transform` nhận các phần tử CharSequence, áp dụng `CharSequence::length` cho mỗi phần tử và xây `List<Integer>` mới; không sửa nguồn.
5. So sánh `getClass` chỉ cho thấy hai đối tượng ArrayList dùng chung runtime class, **không** chứng minh hai type arguments của các biến là như nhau.

### Bài biến thể để xác minh năng lực

- Thay `List<CharSequence> copied` bằng `List<Object>` và giải thích tại sao `copyInto` vẫn có thể thêm String; thay bằng `List<Integer>` và giải thích tại sao không còn một T phù hợp cho phép copy đó.
- Thay `CharSequence::length` bằng function trả Boolean, dự đoán `List<R>` trở thành kiểu gì.
- Thay list đích bằng `List.of(...)` rồi giải thích sự khác nhau giữa *compile được* và *thất bại khi gọi add*.
- Truyền một danh sách rỗng vào `first` và xác định exception, không gọi đó là “lỗi của Generics”.
- Tạo raw alias trong một file **test riêng** để thấy typed read có thể fail muộn; không thêm raw alias vào ví dụ production.

## 11. Bảng kiểm tra năng lực theo từng giai đoạn

| Chặng | Năng lực cần thể hiện không xem lời giải | Bằng chứng hoàn thành |
| --- | --- | --- |
| Nền | Giải thích type của biến vs runtime class và Object/cast | Phân biệt một compile error với runtime exception |
| 1 | Chỉ ra nhu cầu hợp đồng typed collection | Chuyển một List<Object> đang bị cast sang List<String> hợp lý |
| 2 | Đọc T/K/V và parameterized types | Box/Pair/interface generic được khai báo đúng |
| 3 | Viết generic method có kết quả phụ thuộc input | Không cần cast tại caller; có empty-input policy |
| 4 | Chọn wildcard dựa trên producer/consumer | Copy List<Integer> sang List<Number> không unchecked cast |
| 5 | Giải thích erasure và điều kiện heap pollution | Dự đoán chính xác operation gây CCE |
| 6 | Đọc chữ ký JDK có wildcard và mapper | Chỉ rõ T, R, chiều đọc/ghi, output type |
| 7 | Thiết kế và kiểm chứng một API nhỏ | Có ví dụ chạy được, output/edge cases được dự đoán trước |

Nếu còn sai ở chặng 4, quay về **invariance và quan hệ subtype**. Nếu sai ở chặng 5, tách **generic metadata tại compile time** với **object class tại runtime**. Nếu bạn hiểu lý thuyết nhưng không biên dịch được chặng 7, thử viết từng method với kiểu tường minh trước khi ghép toàn chương trình.

## 12. Bộ câu hỏi tổng hợp và đáp án ngắn

**Câu 1.** `Box<T>` và `Box<String>` khác nhau ở đâu?

**Đáp án:** `<T>` trong class declaration khai báo type parameter; String là type argument ở cách sử dụng, tạo parameterized type `Box<String>`.

**Câu 2.** `List<Integer>` có phải subtype của `List<Number>` không?

**Đáp án:** Không. Generic parameterization này invariant; dùng `? extends Number` khi cần đọc từ các list số khác nhau.

**Câu 3.** Tại sao `static <T> T identity(T value)` giữ được thông tin kiểu tốt hơn `Object identity(Object value)`?

**Đáp án:** Cùng T nối kiểu đầu vào và kiểu kết quả của lời gọi; caller có thể nhận type đã được compiler suy luận, thường không cần cast.

**Câu 4.** Với `List<? super Integer>`, vì sao `add(1)` hợp lệ nhưng `Integer x = get(0)` không được bảo đảm?

**Đáp án:** Actual type argument có thể là Integer, Number hoặc Object. Có thể ghi Integer; đọc ra chỉ chắc Object.

**Câu 5.** `List<?>` có giống raw `List` không?

**Đáp án:** Không. List<?> giữ một unknown captured element type, compiler không cho ghi phần tử non-null tùy ý. Raw List mất nhiều generic checks và có thể sinh unchecked warnings.

**Câu 6.** `String[]` và `List<String>` có giống nhau về kiểm tra runtime element type không?

**Đáp án:** Không. String[] có reified runtime component String và array-store check. Một ArrayList<String> thông thường không có String runtime token riêng để kiểm tra mỗi lần add.

**Câu 7.** Khi nào nên dùng generic method, khi nào kiểu cụ thể?

**Đáp án:** Dùng named type parameter khi có quan hệ kiểu cần giữ giữa các input/output; dùng kiểu cụ thể khi logic chỉ liên quan một entity hoặc một contract cố định. Không đặt `<T>` chỉ để gây ấn tượng “tổng quát”.

**Câu 8.** Khi một List<String> bị raw code thêm Integer, ClassCastException xuất hiện lúc nào?

**Đáp án:** Không bắt buộc ở raw add. Nó có thể xuất hiện khi typed read/usage khiến JVM cast Integer thành String; đọc như Object có thể vẫn thành công.

**Câu 9.** Type erasure có nghĩa Reflection không đọc được bất kỳ generic declaration nào không?

**Đáp án:** Không. Metadata của field/method/supertype có thể giữ Signature để Reflection phân tích declaration. Nhưng generic type argument của một đối tượng ArrayList thông thường không tự được reified.

**Câu 10.** Đích của `Collections.copy(dest,src)` có được tự tăng kích thước khi source dài hơn không?

**Đáp án:** Không. API này ghi đè theo index và đòi destination đủ kích thước; khác `addAll`.

## 13. Tự tổ chức buổi thực hành

Một quy trình học có thể lặp cho mỗi chặng:

1. **Dự đoán:** ghi kiểu của biểu thức và trạng thái compile/run trước khi dùng IDE.
2. **Chạy:** dùng `javac --release 17` để xác nhận; bật `-Xlint:rawtypes,unchecked` trong thử nghiệm legacy.
3. **Giải thích:** viết 2–3 câu về cơ chế kiểu và thời điểm kiểm tra.
4. **Biến thể:** thay type argument, wildcard hoặc method return type để xem điều gì đổi.
5. **So sánh:** kiểm tra cùng khái niệm ở một chữ ký JDK hoặc một test dữ liệu sai.
6. **Tự đánh giá:** chỉ qua chặng khi giải thích được cả case chạy đúng, case compiler từ chối và một edge case có ý nghĩa.

Không cần một lịch cố định hay số giờ tiêu chuẩn. Nếu đã giỏi collection và OOP, có thể chuyển nhanh qua chặng đầu; còn wildcard và erasure đáng dành thời gian để tự tạo test.

### Một số lỗi cần tự tìm ra mà không xem gợi ý

- Viết `List<int>` thay vì `List<Integer>`.
- Dùng `List<Object>` ở chỗ thực sự muốn nhận List<String> và List<Integer> nhưng chỉ đọc.
- Viết `static T method(T x)` trong generic class dù T chưa được khai báo tại static method.
- Lấy value từ `List<? super T>` rồi coi trực tiếp là T.
- Thêm T tùy ý vào `List<? extends T>`.
- Dùng raw `List` rồi suppress warning thay vì sửa invariant.
- Nghĩ `new T()` hợp lệ vì method có `<T>`.
- Nhầm `List.of` với một ArrayList sửa được.
- Dùng unchecked cast làm xác thực dữ liệu bên ngoài.

## 14. Tra cứu cú pháp ở đúng thời điểm

| Cú pháp | Khi nào ôn lại |
| --- | --- |
| `class Box<T>`, `interface Store<K,V>` | Chặng 2: declaration của generic type |
| `Box<String>`, `Map<String,Integer>` | Chặng 2: actual type arguments |
| `static <T> T first(List<T>)` | Chặng 3: generic method và quan hệ input/output |
| `<T extends Number>` | Chặng 3: upper bound để gọi members của Number |
| `List<?>` | Chặng 4: chỉ cần xem một danh sách có type chưa biết |
| `List<? extends Number>` | Chặng 4: producer và invariance |
| `List<? super Integer>` | Chặng 4: consumer và invariance |
| `Function<? super T,? extends R>` | Chặng 6–7: callback biến đổi kiểu |
| `Class<T>` và `Supplier<T>` | Sau chặng 5: cần class token hoặc factory runtime |
| `@SafeVarargs` / generic array constraints | Nâng cao sau khi hiểu erasure và heap pollution |

## 15. Định hướng học tiếp sau chương

Khi đã làm được mini-project và giải thích mọi câu hỏi tự kiểm tra, hãy đào sâu lần lượt theo vấn đề thực tế đang gặp:

- Generic inheritance, F-bounded types và bridge methods nếu bạn thiết kế hierarchy.
- Wildcard capture và bounded wildcards nâng cao nếu API cần nhiều nguồn/đích hoặc thao tác đọc–ghi nội bộ.
- Generic varargs, heap pollution và `@SafeVarargs` nếu đang xây tiện ích nhận varargs.
- `Type`, `ParameterizedType` và generic Reflection nếu cần đọc declaration metadata.
- `Function`, `Predicate`, `Stream.map` và `flatMap` nếu đang xây pipeline biến đổi dữ liệu.
- Tương thích nhị phân của public generic APIs nếu bạn phát hành library và tiến hóa bounds.

Với mỗi chủ đề, tiếp tục đặt ba câu hỏi: **Compiler biết quan hệ kiểu nào? JVM còn kiểm tra điều gì? Người gọi API được bảo đảm điều gì mà không cần cast?**

Đó là nền tảng để đi từ *sử dụng generics* tới *thiết kế generic APIs có chủ đích, an toàn và dễ bảo trì*.
