# Tham chiếu hàm tạo mảng bằng `Type[]::new` trong Java

**`Type[]::new`** là cú pháp *array constructor reference* (tham chiếu hàm tạo mảng). Nó cho phép truyền “cách tạo một mảng có độ dài được cung cấp sau” như một hàm, thay vì tự viết lambda `size -> new Type[size]` ở mỗi chỗ sử dụng.

Ví dụ điển hình:

~~~java
String[] names = java.util.stream.Stream.of("An", "Bình", "Chi")
        .toArray(String[]::new);
~~~

Ở đây, `String[]::new` chỉ định **kiểu mảng cần tạo**; API `Stream.toArray` sẽ cấp kích thước cần thiết và đưa các phần tử của stream vào mảng kết quả. Kiểu trả về là `String[]`, không phải `Object[]`.

## 1. Cú pháp và kiểu hàm đích

Một tham chiếu hàm tạo mảng phải được sử dụng ở nơi Java biết *target type* là một functional interface có chữ ký phù hợp. Kiểu đích thường dùng nhất là `IntFunction<T[]>` trong gói `java.util.function`.

~~~java
import java.util.function.IntFunction;

IntFunction<String[]> newStrings = String[]::new;
// Tương đương về tác dụng với:
IntFunction<String[]> same = length -> new String[length];
~~~

**Hai đoạn trên là đoạn minh họa nằm trong một phương thức; không phải tệp Java độc lập.**

Chữ ký trừu tượng của `IntFunction<R>` là `R apply(int value)`. Đối với `IntFunction<String[]>`, chữ ký sau khi thay tham số kiểu là:

~~~java
String[] apply(int length);
~~~

Vì vậy:

- `Type` là kiểu phần tử được dùng để khai báo mảng (ví dụ `String`, `Integer`, `Order`, `int`).
- `[]::new` là một **tham chiếu tới thao tác tạo mảng**, chưa tạo mảng tại lúc khai báo.
- Khi gọi `factory.apply(n)`, thao tác tương ứng tạo một mảng `new Type[n]`.
- Giá trị `n` là **độ dài**, không phải phần tử. Tham chiếu này không tự sao chép dữ liệu vào mảng.
- Mảng mới chứa các giá trị mặc định: `null` với phần tử tham chiếu, `0` với `int`, `false` với `boolean`, v.v.

Cú pháp này áp dụng cả cho mảng phần tử là primitive, ví dụ `int[]::new`, khi kiểu đích là `IntFunction<int[]>`. Tuy nhiên một số API tổng quát, như `Stream<T>.toArray(IntFunction<A[]>)`, yêu cầu kiểu phần tử mảng là kiểu tham chiếu `A`; việc tự tạo `int[]` bằng `IntFunction<int[]>` không biến `Stream<Integer>` thành `IntStream`.

## 2. Ví dụ chạy độc lập: tạo mảng đúng độ dài

Tạo file `ArrayConstructorReferenceDemo.java`:

~~~java
import java.util.Arrays;
import java.util.function.IntFunction;

public class ArrayConstructorReferenceDemo {
    public static void main(String[] args) {
        IntFunction<String[]> strings = String[]::new;
        String[] slots = strings.apply(3);
        slots[1] = "Bình";

        IntFunction<int[]> integers = int[]::new;
        int[] scores = integers.apply(2);

        String[] empty = strings.apply(0);

        System.out.println("slots=" + Arrays.toString(slots));
        System.out.println("scores=" + Arrays.toString(scores));
        System.out.println("empty length=" + empty.length);
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 ArrayConstructorReferenceDemo.java
java ArrayConstructorReferenceDemo
~~~

Kết quả:

~~~text
slots=[null, Bình, null]
scores=[0, 0]
empty length=0
~~~

Điểm quan trọng: `String[]::new` không phải hàm tạo một chuỗi `String`. Nếu muốn tạo đối tượng `String`, đó là cú pháp khác, ví dụ `String::new` với functional interface tương thích. `String[]::new` luôn tạo **mảng các String**.

## 3. Ứng dụng chính: `Stream.toArray(Type[]::new)`

API `Stream<T>` có hai overload đáng phân biệt:

| Cách gọi | Kết quả | Khi nào dùng |
| --- | --- | --- |
| `stream.toArray()` | `Object[]` | Khi thực sự muốn mảng `Object[]`. |
| `stream.toArray(String[]::new)` | `String[]` | Khi muốn mảng được định kiểu và các phần tử phù hợp với `String`. |
| `stream.toArray(Integer[]::new)` | `Integer[]` | Khi dữ liệu phù hợp với phần tử `Integer`. |

Ví dụ đầy đủ, file `StreamArrayDemo.java`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

public class StreamArrayDemo {
    public static void main(String[] args) {
        String[] result = Stream.of("An", "Bình", "Chi")
                .filter(s -> s.length() >= 2)
                .map(s -> s + "!")
                .toArray(String[]::new);

        Object[] generic = Stream.of("A", "B").toArray();
        String[] fromList = List.of("Đà Nẵng", "Hà Nội")
                .toArray(String[]::new);

        System.out.println(Arrays.toString(result));
        System.out.println(generic.getClass().getTypeName());
        System.out.println(Arrays.toString(fromList));
    }
}
~~~

~~~bash
javac --release 17 StreamArrayDemo.java
java StreamArrayDemo
~~~

Kết quả:

~~~text
[An!, Bình!, Chi!]
java.lang.Object[]
[Đà Nẵng, Hà Nội]
~~~

`Stream.toArray(IntFunction<A[]>)` cung cấp cho hàm tạo mảng một số nguyên biểu thị kích thước mảng cần thiết. Điều này cho phép thư viện tự quản lý việc phân bổ mảng. Với stream có thứ tự gặp (*encounter order*), kết quả `toArray` giữ thứ tự các phần tử. Đừng giả định generator luôn được gọi đúng một lần hoặc rằng mọi cách triển khai stream sẽ gọi hàm ở cùng thời điểm; chỉ dựa vào hợp đồng của API.

Trong Java, nếu chỉ gọi `Stream<String>.toArray()`, việc biết phần tử là `String` **không** đổi kiểu runtime của mảng trả về: đó vẫn là `Object[]`. Không ép kiểu `(String[]) stream.toArray()`; ép kiểu đó có thể gây `ClassCastException` do kiểu mảng thực tế không phải `String[]`.

## 4. Dùng với `Collection.toArray(IntFunction<T[]>)`

Từ Java 11, giao diện `Collection` có overload `<T> T[] toArray(IntFunction<T[]> generator)`. Vì `List` là một `Collection`, có thể viết:

~~~java
List<String> labels = List.of("đỏ", "xanh");
String[] colors = labels.toArray(String[]::new);
~~~

Đây là **đoạn minh họa** đặt trong phương thức đã import `java.util.List`. Những cách làm cùng mục đích khác là `labels.toArray(new String[0])` hoặc `labels.toArray(new String[labels.size()])`.

Có một khác biệt tinh tế so với `Stream.toArray`: triển khai mặc định của `Collection.toArray(IntFunction)` gọi generator với **0** rồi đưa mảng nhận được vào overload `toArray(T[])` để thu thập phần tử. Vì vậy, **không được dựa vào việc generator nhận đúng `collection.size()`**. Implementation có thể override; hợp đồng cần quan tâm là mảng kết quả đúng nội dung và kiểu. Điều này giải thích tại sao `String[]::new` phù hợp: nó tạo được mảng bất kỳ độ dài không âm.

Đừng nhầm hai overload này:

- `Stream.toArray(String[]::new)`: tích lũy phần tử từ **một pipeline stream**.
- `Collection.toArray(String[]::new)`: lấy phần tử từ **một collection** đã có.

Cả hai đều cung cấp mảng được định kiểu và không thay đổi các đối tượng phần tử. Đây là thao tác tạo mảng mới; nếu phần tử là đối tượng mutable, mảng và collection/stream vẫn có thể trỏ tới **cùng những đối tượng phần tử** (không phải deep copy).

## 5. Tái sử dụng với phương thức generic

Một lợi ích lớn là không phải viết `new T[size]` bên trong phương thức generic. Java không cho tạo mảng mới trực tiếp với tham số kiểu chưa được reify:

~~~java
// Đoạn minh họa KHÔNG biên dịch:
static <T> T[] broken(int size) {
    return new T[size]; // generic array creation
}
~~~

Thay vào đó, **người gọi cung cấp factory của kiểu mảng cụ thể**. File `GenericArrayFactoryDemo.java`:

~~~java
import java.util.Arrays;
import java.util.function.IntFunction;
import java.util.stream.Stream;

public class GenericArrayFactoryDemo {
    static <T> T[] collectToArray(
            Stream<T> source, IntFunction<T[]> arrayFactory) {
        return source.toArray(arrayFactory);
    }

    public static void main(String[] args) {
        String[] words = collectToArray(
                Stream.of("Java", "Lambda"), String[]::new);

        Integer[] numbers = collectToArray(
                Stream.of(1, 2, 3), Integer[]::new);

        System.out.println(Arrays.toString(words));
        System.out.println(Arrays.toString(numbers));
    }
}
~~~

~~~bash
javac --release 17 GenericArrayFactoryDemo.java
java GenericArrayFactoryDemo
~~~

Kết quả:

~~~text
[Java, Lambda]
[1, 2, 3]
~~~

Người gọi chỉ định `String[]::new` hoặc `Integer[]::new`, giúp thư viện biết rõ kiểu mảng runtime. Kiểu phần tử `T` trong chữ ký generic vẫn chịu cơ chế *type erasure*; chính factory cụ thể mới tạo được đối tượng mảng có component type thật.

Đây cũng là lý do không thể viết `T[]::new` trong một phương thức generic tùy ý; thay vào đó hãy truyền `IntFunction<T[]>` từ nơi còn biết kiểu cụ thể. Tránh dùng `(T[]) new Object[size]` để “lách” lỗi: ép kiểu này không biến `Object[]` thành `String[]` ở runtime và dễ gây `ClassCastException` tại chỗ sử dụng.

## 6. Mảng nhiều chiều: `Type[][]::new`

Tham chiếu `String[][]::new` có thể thích nghi với `IntFunction<String[][]>`, tạo mảng ngoài (mảng chứa các tham chiếu tới mảng `String[]`). Nó tương đương về ý nghĩa với `length -> new String[length][]`, **không tự tạo tất cả các hàng bên trong**.

File `MatrixFactoryDemo.java`:

~~~java
import java.util.Arrays;
import java.util.function.IntFunction;

public class MatrixFactoryDemo {
    public static void main(String[] args) {
        IntFunction<String[][]> outerFactory = String[][]::new;
        String[][] rows = outerFactory.apply(2);

        System.out.println("rows=" + rows.length);
        System.out.println("first row null=" + (rows[0] == null));

        rows[0] = new String[] {"A", "B"};
        rows[1] = new String[] {"C"};

        System.out.println(Arrays.deepToString(rows));
    }
}
~~~

~~~bash
javac --release 17 MatrixFactoryDemo.java
java MatrixFactoryDemo
~~~

Kết quả:

~~~text
rows=2
first row null=true
[[A, B], [C]]
~~~

Nếu cần mảng chữ nhật thực sự, có thể tự tạo bằng `new String[rows][columns]` trong một lambda hoặc method factory thích hợp. Cú pháp `String[][]::new` chỉ nhận **một độ dài** từ interface kiểu `IntFunction`; nó không biểu diễn hàm tạo cần cả hai kích thước.

Một số ví dụ kiểu đích hợp lệ:

| Tham chiếu | Functional interface phù hợp | Kết quả khi `apply(4)` |
| --- | --- | --- |
| `String[]::new` | `IntFunction<String[]>` | `new String[4]` |
| `int[]::new` | `IntFunction<int[]>` | `new int[4]` |
| `Person[]::new` | `IntFunction<Person[]>` | `new Person[4]`, cần có kiểu `Person`. |
| `String[][]::new` | `IntFunction<String[][]>` | `new String[4][]`; bốn hàng ban đầu `null`. |

## 7. Kiểu đích và những lỗi biên dịch phổ biến

### Thiếu target type

Tham chiếu phương thức/hàm tạo là *poly expression*. Những biểu thức sau **không hợp lệ** vì thiếu functional interface làm kiểu đích:

~~~java
// Không biên dịch:
var factory = String[]::new;
Object factory2 = String[]::new;
~~~

Phải viết rõ:

~~~java
java.util.function.IntFunction<String[]> factory = String[]::new;
~~~

Hoặc dùng ngữ cảnh đã có kiểu tham số mong đợi, như `stream.toArray(String[]::new)`.

### Chọn sai functional interface

`Supplier<String[]>` có chữ ký `() -> String[]` (không nhận độ dài), nên không phù hợp với `String[]::new`, vốn cần một `int`. Nếu muốn một mảng luôn dài 10, dùng một lambda cấp kích thước rõ ràng:

~~~java
java.util.function.Supplier<String[]> fixed = () -> new String[10];
~~~

Trong khi đó, `IntFunction<String[]>` biểu diễn kích thước do caller quyết định, thích hợp cho nhiều API tạo mảng động.

### Nhầm mảng primitive với mảng wrapper

`int[]` khác `Integer[]`:

- `int[]::new` tạo mảng các `int` primitive.
- `Integer[]::new` tạo mảng các `Integer` object-reference.
- `IntStream.range(1, 4).toArray()` trả về `int[]`; đây là API chuyên cho primitive stream.
- `Stream<Integer>.toArray(Integer[]::new)` trả về `Integer[]`; không thể dùng `int[]::new` để đáp ứng tham số `IntFunction<A[]>` của overload đó.

Với luồng dữ liệu số primitive, ưu tiên `IntStream`, `LongStream`, `DoubleStream` cùng API `toArray()` chuyên biệt khi phù hợp, tránh boxing không cần thiết.

### Sai kiểu phần tử khi chạy

Java kiểm tra kiểu phần tử khi ghi vào mảng runtime. Ví dụ sau **cố ý gây lỗi**:

~~~java
// Đoạn minh họa nằm trong phương thức, sau khi import Stream.
java.util.stream.Stream<Object> mixed =
        java.util.stream.Stream.of("hợp lệ", 42);

// Có thể biên dịch, nhưng 42 không thể lưu vào String[]:
// String[] wrong = mixed.toArray(String[]::new);
// Khi chạy dòng trên sẽ ném ArrayStoreException.
~~~

Generic type `A` của overload `Stream.toArray(IntFunction<A[]>)` được suy ra từ generator, không nhất thiết được compiler ràng buộc để mọi giá trị thật trong stream gán được vào `A`. Không dùng generator của kiểu hẹp hơn dữ liệu có thể đi qua pipeline.

### Kích thước không hợp lệ

Bản thân biểu thức `String[]::new` hợp lệ; khi thực thi `factory.apply(-1)`, lệnh tạo mảng tương ứng ném `NegativeArraySizeException`. Kích thước quá lớn có thể ném `OutOfMemoryError` hoặc lỗi giới hạn độ dài mảng tùy JVM. Không tạo array từ kích thước không đáng tin cậy mà không kiểm soát giới hạn nghiệp vụ và bộ nhớ.

## 8. Khi nào nên dùng, và điều gì cần nhớ

**Nên dùng `Type[]::new`** khi API cần callback nhận kích thước để tạo đúng kiểu mảng, đặc biệt `Stream.toArray`, `Collection.toArray`, hoặc helper generic có tham số `IntFunction<T[]>`. Cách viết gọn, có kiểu rõ ràng và chuyển trách nhiệm xác định kích thước cho API gọi.

**Nên dùng `size -> new Type[size]`** khi cần logic bổ sung trước/sau khi tạo mảng, ví dụ xác thực kích thước hoặc tạo mảng với điều kiện đặc biệt. Trong các pipeline, ưu tiên generator không có side effect; không phụ thuộc số lần hoặc thứ tự nó được gọi.

**Không nên tạo mảng chỉ vì cú pháp thuận tiện.** Nếu vẫn cần thêm/xóa phần tử thường xuyên, `List` có thể phù hợp hơn; chuyển thành array chỉ tại ranh giới API cần mảng. Mảng có độ dài cố định; việc tạo mới tốn bộ nhớ theo số phần tử, và sao chép tham chiếu vào mảng không đồng nghĩa deep copy.

Checklist khi đọc hoặc viết `Type[]::new`:

1. Functional interface đích có **đúng một tham số kích thước `int`** và trả về kiểu mảng phù hợp chưa?
2. Kiểu runtime cần là `String[]`, `Integer[]`, `int[]`, hay mảng nhiều chiều?
3. API gọi generator khi nào, và có đảm bảo gì về kích thước hoặc số lần gọi?
4. Mọi phần tử thực sự có thể lưu vào component type của mảng không?
5. Với phương thức generic, đã để caller truyền factory kiểu cụ thể thay vì cố `new T[n]` chưa?
6. Nếu dùng mảng nhiều chiều, đã cấp phát các mảng con cần thiết chưa?

**Kết luận kỹ thuật:** `Type[]::new` là phiên bản tham chiếu hàm tạo của `size -> new Type[size]` trong ngữ cảnh functional interface thích hợp. Nó đặc biệt hữu ích để chuyển `Stream<T>` hoặc `Collection<T>` sang một mảng **đúng kiểu runtime**, đồng thời tránh cách tạo mảng generic không hợp lệ và những ép kiểu `Object[]` thiếu an toàn.
