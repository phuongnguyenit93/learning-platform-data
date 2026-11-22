# Xóa kiểu (type erasure) là gì và vì sao Java chọn cách này?

**Type erasure (xóa kiểu)** là cơ chế Java dùng để biên dịch phần lớn thông tin kiểu generic thành các kiểu thông thường trong bytecode. Lập trình viên viết `List<String>`, `Box<T>` hoặc `<T extends Number>` để trình biên dịch kiểm tra an toàn kiểu; khi tạo bytecode, trình biên dịch thay tham số kiểu bằng **giới hạn trên** tương ứng, thêm phép ép kiểu nếu cần và đôi khi tạo **bridge method** để duy trì tính đa hình.

Mục tiêu quan trọng của thiết kế này là cho mã generic được đưa vào Java từ Java 5 có thể **tương tác với thư viện và bytecode được viết trước generics**, thay vì yêu cầu mọi thư viện cũ tạo các bản lớp riêng cho từng kiểu `T`.

> Nhớ trước: **generic chủ yếu được kiểm tra tại thời điểm biên dịch**; giá trị trong `List<String>` không tự mang một nhãn runtime “đây là danh sách String”. Tuy nhiên, không phải mọi dấu vết generic đều biến mất: chữ ký generic vẫn có thể được lưu trong metadata của class để phục vụ trình biên dịch và reflection.

## 1. Generic mang lại điều gì trước khi xóa kiểu?

Xét hai cách viết danh sách:

```java
// Minh họa, chưa phải chương trình hoàn chỉnh:
List raw = new ArrayList();                 // Raw type
raw.add("Java");
raw.add(123);                               // Vẫn biên dịch; bỏ kiểm tra phần tử

List<String> typed = new ArrayList<>();
typed.add("Java");
// typed.add(123);                          // Lỗi biên dịch: int/Integer không phải String
String text = typed.get(0);                 // Không cần tự viết cast
```

Ở mã nguồn, `List<String>` giúp trình biên dịch biết `add` cần `String` và `get` được xem là trả `String`. Với raw `List`, phần tử được nhìn qua `Object`, và lập trình viên phải tự bảo đảm hoặc tự ép kiểu.

Generic vì thế tạo **kiểm tra kiểu sớm** và làm API dễ đọc, dễ bảo trì hơn. Type erasure là cách Java hiện thực hóa những bảo đảm ở bước biên dịch; nó không có nghĩa generics “vô ích” hay “chỉ để viết đẹp”.

## 2. Trình biên dịch xóa kiểu theo những quy tắc nào?

Có ba nhóm biến đổi cần hiểu:

1. **Thay tham số kiểu** bằng giới hạn trên của nó; nếu không khai báo giới hạn thì dùng `Object`. Nếu có nhiều giới hạn, kiểu được dùng để xóa là giới hạn đầu tiên.
2. **Chèn cast** tại những chỗ mã nguồn đòi hỏi kiểu cụ thể hơn kiểu sau khi xóa. Cast vẫn có thể kiểm tra lúc chạy và ném `ClassCastException` khi dữ liệu bị làm bẩn qua raw type hoặc unchecked operation.
3. **Tạo bridge method khi cần** để phương thức ghi đè tiếp tục hoạt động đúng với quy tắc dispatch của JVM sau khi chữ ký tham số đã đổi do erasure.

Đối với một tham số kiểu:

| Khai báo nguồn | Kiểu sau khi xóa | Ý nghĩa |
| --- | --- | --- |
| `<T>` | `Object` | `T` không có giới hạn rõ ràng |
| `<T extends Number>` | `Number` | Biết chắc đối tượng thỏa giới hạn `Number` |
| `<T extends Number & Comparable<T>>` | `Number` | Giới hạn đầu tiên quyết định erasure của `T` |
| `List<String>` | `List` | Tham số kiểu `String` không tạo lớp runtime mới |
| `Map<String, Integer>` | `Map` | Hai tham số kiểu không nằm trong descriptor thông thường |

**Lưu ý:** dấu `extends` của type parameter có thể đi kèm lớp và interface. Ví dụ `T extends Number & Comparable<T>` hợp lệ vì `Number` là lớp đứng trước interface. Không thể dùng nhiều lớp cha.

### 2.1. Hình dung bản trước và sau erasure

Mã nguồn:

```java
// Mã nguồn minh họa:
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Có thể hình dung các chữ ký sau khi xóa tương đương với:

```java
// Pseudocode minh họa erasure, KHÔNG đặt chung với class Box<T> ở trên:
class Box {
    private Object value;

    Box(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
```

Đây là mô hình giảng giải, không phải tệp nguồn mà javac sinh ra. Javac tạo bytecode và có thể giữ thêm `Signature` metadata mô tả khai báo generic. Nếu gọi:

```java
// Snippet đặt trong chương trình có khai báo Box<T>:
Box<String> box = new Box<>("Java");
String value = box.get();
```

Lời gọi `get()` có kiểu nhìn từ nguồn là `String`; vì phương thức bị xóa có kết quả `Object`, compiler có thể chèn `checkcast String` trong bytecode của bên gọi.

Với `class NumericBox<N extends Number>`, trường kiểu `N`, tham số kiểu `N` và kiểu trả về `N` trong descriptor thông thường được xóa về `Number`, không phải `Object`.

## 3. Chương trình Java 17+ quan sát erasure và bridge method

Lưu nội dung sau thành tệp `TypeErasureDemo.java`:

```java
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class TypeErasureDemo {
    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static class NumericBox<N extends Number> {
        private final N value;

        NumericBox(N value) {
            this.value = value;
        }

        N get() {
            return value;
        }
    }

    static class Node<T> {
        private T value;

        void set(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static class TextNode extends Node<String> {
        @Override
        void set(String value) {
            super.set(value);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        List<String> words = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();
        words.add("Java");
        numbers.add(17);

        System.out.println("Same runtime class: "
                + (words.getClass() == numbers.getClass()));

        Box<String> box = new Box<>("Java");
        String text = box.get();
        System.out.println("Read through Box<String>: " + text);

        Method boxGet = Box.class.getDeclaredMethod("get");
        Method numericGet = NumericBox.class.getDeclaredMethod("get");

        System.out.println("Box.get erased return: "
                + boxGet.getReturnType().getSimpleName());
        System.out.println("Box.get generic return: "
                + boxGet.getGenericReturnType().getTypeName());
        System.out.println("NumericBox.get erased return: "
                + numericGet.getReturnType().getSimpleName());

        Node<String> node = new TextNode();
        node.set("hello");
        System.out.println("Stored value: " + node.get());

        Method bridge = Arrays.stream(TextNode.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .findFirst()
                .orElseThrow();

        System.out.println("Bridge method parameter: "
                + bridge.getParameterTypes()[0].getSimpleName());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 TypeErasureDemo.java
java TypeErasureDemo
```

Kết quả mong đợi:

```text
Same runtime class: true
Read through Box<String>: Java
Box.get erased return: Object
Box.get generic return: T
NumericBox.get erased return: Number
Stored value: hello
Bridge method parameter: Object
```

Diễn giải lần lượt:

- Hai đối tượng `ArrayList<String>` và `ArrayList<Integer>` có cùng **runtime class** là `ArrayList`. Chúng vẫn chứa các giá trị khác nhau, và các cách sử dụng kiểu ở nguồn vẫn được compiler kiểm tra.
- `Box.get()` được phản chiếu qua `Method.getReturnType()` với kiểu trả về **`Object`** sau erasure. Trong khi đó `Method.getGenericReturnType()` có thể đọc lại khai báo **`T`** từ metadata.
- `NumericBox.get()` trả về **`Number`** ở tầng bytecode vì giới hạn trên của `N` là `Number`.
- Biến `Node<String> node` tham chiếu một `TextNode`; gọi `set("hello")` vẫn đi qua phương thức ghi đè của `TextNode`. Compiler tạo bridge nhận `Object` để đường gọi theo descriptor đã xóa vẫn tới được phương thức nhận `String`.

Có thể dùng `javap -c -p TypeErasureDemo\$Box` hoặc, tùy shell, trích tên lớp lồng nhau bằng cú pháp quoting phù hợp để tự xem bytecode. `javap -v` cho thấy thêm các thuộc tính như `Signature` và các cờ của bridge method. Những lệnh quan sát bytecode mang tính bổ sung; chương trình Java ở trên đủ để thấy khác biệt bằng reflection.

## 4. Bridge method giải quyết vấn đề ghi đè nào?

Trong chương trình ở mục 3, ở mã nguồn:

```java
class Node<T> {
    void set(T value) { /* ... */ }
}

class TextNode extends Node<String> {
    @Override
    void set(String value) { /* ... */ }
}
```

Đây là snippet rút gọn để minh họa và không thay thế chương trình chạy độc lập bên trên. Sau erasure, phương thức của lớp cha có descriptor nhận `Object`, còn phương thức cụ thể của lớp con nhận `String`.

Nếu chỉ xét hai descriptor đó, JVM sẽ không tự hiểu `set(String)` là phương thức cần được gọi khi client đã biên dịch lời gọi tới `Node.set(Object)`. Compiler vì vậy có thể tạo thêm một phương thức **synthetic bridge** về bản chất tương đương:

```java
// Mã mô phỏng phương thức được compiler tạo bên trong TextNode:
void set(Object value) {
    set((String) value);
}
```

Bridge thật là bytecode do compiler tạo, **không** phải phương thức bạn phải tự viết trong lớp Java. Phương thức này bảo toàn dispatch động: `Node<String> n = new TextNode(); n.set("abc");` vẫn chạy logic ghi đè ở `TextNode`.

Vì bridge phải cast `Object` về `String`, mã sử dụng raw type sai cách có thể gặp `ClassCastException` ngay tại bridge. Đây là hành vi bảo vệ kiểu runtime, không phải dấu hiệu generics được chuyên biệt hóa.

## 5. Vì sao type erasure giúp tương thích với Java trước generics?

Java xuất hiện trước khi generics được đưa vào Java 5. Nhiều thư viện lâu đời dùng `Object`, raw `List`, `Collection` và API không khai báo type parameter. Chọn erasure giúp quá trình đưa generics vào thư viện cũ theo hướng **migration compatibility**.

### 5.1. Chữ ký JVM quen thuộc được giữ ở nhiều API

Xét cùng một ý định API ở hai thời kỳ:

```java
// Phiên bản trước generic (minh họa):
void consume(java.util.List items) { /* ... */ }

// Phiên bản khai báo generic (minh họa, thay thế bản trên):
void consume(java.util.List<String> items) { /* ... */ }
```

Hai phương thức trên đều có descriptor tham số JVM dùng `java/util/List`, thay vì tạo một descriptor riêng cho `List<String>`. Về mặt mô hình bytecode, đoạn tham số là:

```text
(Ljava/util/List;)V
```

Trong đó `L...;` biểu thị kiểu đối tượng `List`, còn `V` là `void`. Khi một thư viện được generic hóa nhưng **chữ ký đã xóa và các điều kiện tương thích khác được giữ nguyên**, bytecode client cũ vẫn có cơ hội liên kết đến các phương thức như trước.

Hai khai báo này **không thể cùng tồn tại dưới dạng overload trong một lớp**, vì sau erasure chúng trùng chữ ký.

### 5.2. Mã cũ và mã mới có thể gọi nhau

Ví dụ, một thư viện cũ cung cấp một `List` raw vẫn có thể được mã mới xử lý, dù compiler có thể báo **unchecked warning** khi gán hoặc ép về `List<String>`. Ngược lại, mã cũ nhận `List` vẫn có thể gọi API generic mà descriptor thông thường tương thích.

Nhờ đó, Java không phải tạo một lớp runtime mới `List<String>`, một lớp khác `List<Integer>`, rồi thay toàn bộ hạ tầng class loading và thư viện cũ. Các đối tượng `ArrayList` vẫn mang cùng tên lớp ở runtime; phần bổ sung của generics chủ yếu nằm ở hệ thống kiểu nguồn và metadata.

Điều này giúp **tương thích và triển khai dần**; không có nghĩa mọi thay đổi API đều tự động tương thích. Ví dụ, đổi giới hạn đầu tiên của `T` có thể đổi erasure của tham số hoặc kiểu trả về, làm đổi descriptor; đổi overload hoặc quy tắc kế thừa cũng có thể phá mã client. Phiên bản class file của bytecode mới và các API/JVM được sử dụng vẫn phải được môi trường chạy hỗ trợ. Type erasure không biến mọi class biên dịch bằng JDK mới thành class chạy được trên JVM rất cũ.

## 6. Vì sao `List<String>` và `List<Integer>` không có hai class runtime?

Đối số kiểu chỉ thay đổi **hợp đồng source-level**, không sinh một class `ArrayList` riêng cho `String` và `Integer`:

```java
List<String> words = new ArrayList<>();
List<Integer> ids = new ArrayList<>();
System.out.println(words.getClass() == ids.getClass()); // true
```

Phép so sánh dùng hai object khác nhau có **cùng class runtime**. Điều đó không biến `List<String>` thành `List<Integer>` hoặc `List<Object>`: compiler vẫn kiểm tra tính bất biến (*invariance*) và từ chối phép gán sai generic argument. Bài về hai cách dùng `Box<T>` cùng lớp runtime sẽ chứng minh riêng class identity, subtype metadata và type tokens.

## 7. Những điều không thể kiểm tra trực tiếp tại runtime

Type erasure dẫn tới một số giới hạn rõ ràng:

| Tình huống | Hợp lệ? | Vì sao |
| --- | --- | --- |
| `value instanceof List<?>` | Có | Kiểm tra raw runtime `List`; wildcard `?` không đòi biết kiểu phần tử |
| `value instanceof List<String>` | Không | Không thể kiểm tra tham số `String` của `List` ở runtime theo cách đó |
| `new T()` trong một lớp generic | Không | Không có thông tin class cụ thể và bảo đảm constructor cho `T` |
| `T.class` | Không | Type variable không có class literal tương ứng |
| `new List<String>[10]` | Không | Array kiểm tra kiểu phần tử lúc chạy trong khi `List<String>` không là kiểu reifiable |
| `List<int>` | Không | Type argument phải là kiểu tham chiếu; dùng `List<Integer>` và boxing/unboxing |

Với lớp generic, có thể lưu `Class<T>`, `Supplier<T>` hoặc factory được truyền từ ngoài nếu phải tạo đối tượng `T`. Chẳng hạn:

```java
// Snippet minh họa phương án dùng factory:
static <T> T create(java.util.function.Supplier<T> factory) {
    return factory.get();
}

// create(java.util.ArrayList::new) sẽ tạo một ArrayList.
```

Mặt khác, **array có kiểu thành phần reifiable** và kiểm tra kiểu này lúc chạy: cố ghi một `Integer` vào đối tượng runtime `String[]` có thể gây `ArrayStoreException`. Generic và array vì thế áp dụng hai cơ chế kiểm tra kiểu khác nhau.

## 8. Raw type và heap pollution: giới hạn thực tế của kiểm tra kiểu

Generic bảo vệ mã nguồn được biên dịch đúng kiểu, nhưng có các “lối thoát” như **raw type**, unchecked cast và một số thao tác phản xạ.

Xét snippet **cố ý không an toàn**:

```java
import java.util.ArrayList;
import java.util.List;

// Minh họa hành vi lỗi, không phải mẫu code nên dùng:
List<String> names = new ArrayList<>();
List raw = names;            // Raw type bỏ thông tin String khỏi lần thao tác này
raw.add(123);               // Có thể có unchecked warning
String first = names.get(0); // Có thể ném ClassCastException
```

Đối tượng danh sách thực chất chứa `Integer` ở chỉ số 0. Tuy nhiên, mã biên dịch với `names.get(0)` kỳ vọng `String` và sẽ có một cast thích hợp trên đường lấy dữ liệu; vì vậy lỗi thường lộ ra **khi đọc**, thay vì nhất thiết lúc raw `add`.

Tình trạng một biến có kiểu parameterized nhưng trỏ đến dữ liệu không bảo đảm theo kiểu khai báo gọi là **heap pollution**. Đây là lý do nên dùng `javac -Xlint:unchecked` để chú ý unchecked warning, hạn chế raw type, và không ép kiểu generic vô căn cứ. Một unchecked cast có thể không kiểm tra được tham số `String` ngay tại vị trí cast do erasure.

## 9. Nếu đã erasure, reflection còn thấy gì?

Cần tách **runtime class**, **kiểu đã xóa** và **generic declaration metadata**. Ví dụ, ở `class Box<T> { T get(); }` (đoạn ký hiệu chữ ký), JVM có thể sử dụng descriptor trả `Object`, trong khi `getGenericReturnType()` trả một `TypeVariable` tên `T` từ thuộc tính `Signature`.

Metadata ấy mô tả **cách lớp/field/method được khai báo**, không ghi lịch sử type inference của mọi lần tạo `new Box<String>()`. `obj.getClass()` không tự trả về `Box<String>` khi runtime class chung là `Box`. Thông tin về khai báo superclass cụ thể như `class StringBox extends Box<String>` có thể được reflection đọc riêng. Bài cuối chương đi sâu vào class-file `Signature` và các loại `Type` của reflection.

## 10. Type erasure khác reification và specialization thế nào?

Ba thuật ngữ không đồng nghĩa:

| Cơ chế | Câu hỏi chính | Với Java 17 |
| --- | --- | --- |
| **Erasure** | JVM descriptor dùng kiểu nào khi bỏ generic arguments? | Thường một class generic với `Object` hoặc first bound |
| **Reification** | Kiểu nào có đủ biểu diễn runtime để kiểm tra? | `String[]` có runtime component type; `List<String>` không reifiable theo cách đó |
| **Specialization** | Có sinh code/class riêng cho từng tổ hợp kiểu không? | `Box<String>` và `Box<Integer>` không tự sinh hai class generic riêng |

Không thể dùng cơ chế trên để suy ngay hiệu năng. Wrapper boxing, object layout, JIT và workload cần được đánh giá độc lập. Bài **erasure so với specialization** phân tích trade-offs và ví dụ class `IntBox` được lập trình thủ công.

## 11. Những nhầm lẫn thường gặp

**Nhầm 1 — “Generic mất hết tác dụng sau khi biên dịch.”** Sai. Rất nhiều lỗi kiểu bị chặn ngay khi javac biên dịch; các cast được chèn còn tiếp tục phát hiện sai kiểu trong một số đường chạy.

**Nhầm 2 — “`List<String>` là lớp khác `List<Integer>`.”** Sai đối với runtime class: hai cách dùng `ArrayList` vẫn là `ArrayList`; type arguments được compiler theo dõi.

**Nhầm 3 — “Vì bytecode giống nhau nên có thể overload `process(List<String>)` và `process(List<Integer>)`.”** Sai. Hai chữ ký xóa thành `process(List)` và gây **name clash** trong cùng lớp.

**Nhầm 4 — “`instanceof List<String>` hoạt động vì trong list đang toàn String.”** Sai. Một collection hiện đang chỉ chứa `String` không làm JVM có kiểu parameterized reifiable tương ứng để kiểm tra.

**Nhầm 5 — “Reflection không thể thấy bất kỳ generic nào.”** Sai. Metadata của khai báo generic có thể tồn tại dù không thể suy ra type argument từ bất kỳ instance nào.

**Nhầm 6 — “Type erasure bảo đảm mọi thay đổi từ API cũ sang API generic tương thích tuyệt đối.”** Sai. Tính tương thích phụ thuộc descriptor đã xóa, quan hệ kế thừa, overload, khả năng JVM đọc class file và hành vi API.

## 12. Cách tự kiểm chứng khi làm việc với API thực tế

Khi gặp một lỗi liên quan đến generics, hãy đi theo trình tự sau:

1. **Đọc type parameter và bounds** ở chữ ký nguồn, ví dụ `<T>`, `<T extends Number>`, `Comparable<? super T>`.
2. **Tìm kiểu sau erasure**: nếu `T` không bound thì `Object`; có bound thì lấy giới hạn đầu tiên; `List<String>` dùng raw `List` trong descriptor.
3. **Xác định chỗ cast có thể xuất hiện** khi gán kết quả generic cho kiểu cụ thể.
4. **Kiểm tra quan hệ override**: phương thức cụ thể trong subclass có cần bridge để phục vụ descriptor của superclass/interface hay không.
5. **Đọc unchecked warning** và kiểm tra raw/unchecked operations nếu lỗi chỉ xảy ra lúc chạy.
6. **Dùng `javap` hoặc reflection** để đối chiếu erasure, `Signature` và bridge khi cần xác minh sâu.

Ví dụ chạy chương trình ở mục 3 cùng với `javap -p -c TypeErasureDemo` và `javap -p -v TypeErasureDemo\$TextNode` (với quoting tên class lồng nhau theo shell) giúp quan sát lớp biên dịch; kết quả `Method.isBridge()` là cách đơn giản hơn để nhận biết bridge trong chương trình Java.

**Kết luận:** Java chọn type erasure để thêm khả năng kiểm tra kiểu generic vào một hệ sinh thái thư viện và bytecode đã tồn tại. Compiler thay type parameter bằng bound phù hợp, chèn cast và tạo bridge khi cần. Đổi lại, Java generic thông thường không cung cấp kiểm tra trực tiếp các type argument như `List<String>` tại runtime, nên hiểu rõ erasure, metadata và unchecked warning là kỹ năng thiết yếu khi đọc hoặc thiết kế API generic.