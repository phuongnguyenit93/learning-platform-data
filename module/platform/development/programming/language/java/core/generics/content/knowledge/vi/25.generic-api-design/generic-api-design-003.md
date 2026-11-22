# Dùng kiểu chính xác khi cần giữ quan hệ đọc–ghi trong Java Generics

## 1. Vấn đề thiết kế: một danh sách vừa cung cấp, vừa nhận lại cùng kiểu dữ liệu

Một lời khuyên quen thuộc khi viết generic APIs là **PECS — Producer Extends, Consumer Super**:

- Nếu collection chỉ **cung cấp** các giá trị kiểu T, chữ ký `? extends T` thường linh hoạt.
- Nếu collection chỉ **tiếp nhận** các giá trị kiểu T, chữ ký `? super T` thường linh hoạt.
- Nhưng khi **cùng một tham số vừa được đọc ra, vừa được ghi lại** và chương trình cần giữ **chính xác mối quan hệ kiểu ở hai hướng**, lựa chọn tốt có thể là **một type parameter T nhất quán**, chẳng hạn `List<T>`.

Ví dụ:

~~~java
static <T> T replaceFirst(List<T> values, T replacement) {
    return values.set(0, replacement);
}
~~~

Hàm này làm ba việc dưới **cùng một T**:

1. Nhận một `List<T>`.
2. Ghi giá trị `replacement` có kiểu T vào danh sách.
3. Trả về giá trị T cũ mà `List.set` cung cấp.

Caller dùng `List<String>` thì T là String; caller dùng `List<Integer>` thì T là Integer. Không cần ép kiểu, không cần wildcard capture ở bên ngoài, và compiler kiểm tra rằng giá trị thay thế tương thích với đúng danh sách được truyền vào.

~~~java
List<String> words = new ArrayList<>(List.of("old", "other"));

String previous = replaceFirst(words, "new"); // "old"
~~~

Nếu thử ghi số nguyên vào danh sách chuỗi:

~~~java
// replaceFirst(words, 99);
// Không biên dịch: không có T thống nhất giữa List<String> và Integer.
~~~

Đây là ví dụ cốt lõi của chủ đề **“dùng kiểu chính xác khi cần giữ quan hệ đọc–ghi”**. Không phải mọi wildcard đều xấu; nhưng wildcard là công cụ biểu diễn **một hướng linh hoạt** hoặc **một kiểu chưa xác định**, không thay thế được tất cả các ràng buộc giữa các lần đọc và ghi.

## 2. Định nghĩa “kiểu chính xác” trong generic API

Trong bài này, **kiểu chính xác** nghĩa là chữ ký giữ cùng một type argument có tên ở các vị trí cần liên hệ, ví dụ `List<T>`, `T`, `UnaryOperator<T>` hoặc `Map<K,V>`. Nó **không** có nghĩa runtime object chỉ được chứa chính xác một class không có subclass.

Ví dụ:

~~~java
List<Number> numbers = new ArrayList<>();
numbers.add(Integer.valueOf(1));
numbers.add(Double.valueOf(2.5));
~~~

Đây vẫn là `List<Number>` hợp lệ; Number là một kiểu tham chiếu mà Integer và Double đều có thể dùng tại vị trí nhận Number.

Cần phân biệt:

- `List<String>`: type argument đã cụ thể là String.
- `List<T>` trong generic method: type argument được caller và compiler xác định khi gọi; **các vị trí có cùng T phải nhất quán**.
- `List<?>`: danh sách có một type argument **chưa biết**, không được tự coi là String hay Number.
- `List<? extends Number>`: type argument là **một subtype chưa xác định** của Number.
- `List<? super Integer>`: type argument là **một supertype chưa xác định** của Integer.

**Tính invariant** của Java generics rất quan trọng:

~~~java
List<Integer> ints = new ArrayList<>();

// List<Number> invalid = ints; // Không biên dịch.
List<? extends Number> readable = ints; // Hợp lệ.
~~~

Dù Integer extends Number, `List<Integer>` không tự là subtype của `List<Number>`. Nếu điều đó được phép, code có thể ghi Double vào một danh sách vốn cam kết chứa Integer.

## 3. Ba kiểu chữ ký và khả năng đọc–ghi

| Loại tham số | Đọc ra an toàn | Ghi vào an toàn | Dùng khi |
| --- | --- | --- | --- |
| `List<T>` | T | Một giá trị tương thích T | Cần dùng cùng một T ở hai hướng. |
| `List<? extends T>` | T | Không thể thêm một T tùy ý | Chỉ cần lấy giá trị từ producer. |
| `List<? super T>` | Object (không bảo đảm đọc thành T) | T và các subtype phù hợp | Chỉ cần cung cấp các T cho consumer. |
| `List<?>` | Object | Không thể thêm giá trị non-null tùy ý | Chưa biết type argument, cần đọc/xử lý tổng quát. |
| `List<Object>` | Object | Bất kỳ Object | Danh sách thực sự được khai báo để chứa Object. |

Giải thích “không thể ghi” ở bảng: trình biên dịch không cho ghi **một giá trị T tùy ý** vào một collection có unknown captured type argument. Có những thao tác hợp lệ như `add(null)` về mặt kiểu tĩnh hoặc dùng **wildcard capture helper** để luân chuyển những giá trị đã được đọc từ chính collection đó. Vì vậy không nên hiểu câu này là “không một thao tác sửa đổi nào có thể tồn tại”.

Ngoài kiểu tĩnh, collection phải **có khả năng sửa đổi**: `List.of(...)`, `List.copyOf(...)` và danh sách từ `Stream.toList()` không cho các thao tác sửa đổi thông thường. Chữ ký `List<T>` không bảo đảm `set`, `add` hoặc `replaceAll` sẽ thành công ở runtime nếu list implementation không hỗ trợ.

## 4. Chỉ đọc: tại sao ? extends T là lựa chọn tốt

Ví dụ cần tính tổng một danh sách số:

~~~java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
~~~

Có thể gọi:

~~~java
double a = sum(List.of(1, 2, 3));       // Integer elements.
double b = sum(List.of(1.5, 2.5));      // Double elements.
~~~

`? extends Number` cho phép danh sách có type argument Number, Integer, Double hoặc subtype phù hợp. Khi đọc, mỗi phần tử **ít nhất có thể được xem như Number**.

Nhưng không được làm:

~~~java
static void invalid(List<? extends Number> values) {
    // values.add(Integer.valueOf(5)); // Không biên dịch.
    // values.add(Double.valueOf(5));  // Không biên dịch.
}
~~~

Bởi compiler không biết actual type argument của collection là Integer, Double hay một subtype khác. Việc “Integer là Number” chưa đủ chứng minh Integer có thể được thêm vào mọi danh sách `List<? extends Number>`.

**Nguyên tắc:** nếu thực sự chỉ đọc, hãy chấp nhận `List<? extends Number>` để caller không phải sao chép List<Integer> thành List<Number>. Nhưng nếu method định **thay đổi chính các số** và trả lại cùng type argument, cần thiết kế khác.

## 5. Chỉ ghi: tại sao ? super T là lựa chọn tốt

Ví dụ đưa những Integer mới vào một đích:

~~~java
static void appendIds(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
~~~

Có thể gọi với:

~~~java
List<Integer> integerTarget = new ArrayList<>();
List<Number> numberTarget = new ArrayList<>();
List<Object> objectTarget = new ArrayList<>();

appendIds(integerTarget);
appendIds(numberTarget);
appendIds(objectTarget);
~~~

Tất cả đích đều có thể tiếp nhận một Integer. Nhưng **đọc từ `List<? super Integer>` chỉ bảo đảm Object**:

~~~java
List<? super Integer> target = new ArrayList<Number>();
target.add(42);

Object value = target.get(0); // Hợp lệ.
// Integer invalid = target.get(0); // Không biên dịch.
~~~

Lý do: actual type argument có thể là Integer, Number hoặc Object. Compiler không thể hứa một giá trị đọc ra từ List<Object> luôn là Integer.

Đừng cast tùy tiện thành Integer nếu dữ liệu có thể được thêm từ những nguồn khác. Nếu cần đọc lại dưới dạng Integer hoặc giữ loại chính xác của phần tử, một chữ ký có type variable T hoặc một invariant được xác thực sẽ hợp lý hơn.

## 6. Khi cùng một List vừa nhận T vừa trả T: chọn List<T>

Một API cập nhật có thể trả **giá trị trước khi thay đổi**:

~~~java
static <T> T replaceFirst(List<T> values, T replacement) {
    return values.set(0, replacement);
}
~~~

Thử ba cách thiết kế:

~~~java
// Biến thể chỉ đọc:
static Number first(List<? extends Number> values) {
    return values.get(0);
}

// Biến thể chỉ ghi:
static void append(List<? super Integer> values, Integer x) {
    values.add(x);
}

// Biến thể cần đọc–ghi cùng kiểu:
static <T> T replaceFirst(List<T> values, T replacement) {
    return values.set(0, replacement);
}
~~~

`first` dùng một upper bounded wildcard vì lấy ra Number là đủ. `append` dùng lower bounded wildcard vì chỉ đẩy Integer vào. `replaceFirst` cần một T thống nhất cho danh sách, phần tử mới và giá trị trả về.

Trong generic code, một **named type parameter** không phải chỉ là cách viết dài hơn của wildcard. Nó cho phép mô hình hóa **quan hệ bằng nhau giữa các vị trí kiểu** của cùng một lời gọi.

### 6.1. Vì sao không dùng List<? extends T> cho cập nhật?

Giả sử:

~~~java
static <T> void invalid(
        List<? extends T> values, T replacement) {
    // values.set(0, replacement); // Không biên dịch.
}
~~~

Dù replacement có kiểu T, type argument bị bắt (*captured*) của `values` có thể là subtype T hẹp hơn. Vì vậy compiler không thể cho phép viết T tổng quát vào list đó.

### 6.2. Vì sao không dùng List<? super T> cho cả đầu ra?

~~~java
static <T> T invalidRead(List<? super T> values) {
    // return values.get(0); // Không biên dịch.
    throw new UnsupportedOperationException();
}
~~~

Mảnh code trên chỉ nhằm minh họa kiểu. `get` của list loại này chỉ có thể đọc như Object. Việc ném UnsupportedOperationException trong ví dụ là placeholder kiểm tra chữ ký và **không phải cách triển khai đề xuất** cho một API thực tế.

Sửa thiết kế bằng `List<T>` nếu cần đọc và ghi cùng T:

~~~java
static <T> T takeAndReplace(List<T> list, T replacement) {
    return list.set(0, replacement);
}
~~~

Một trường hợp khác là tách đường đọc và ghi ra **hai tham số** producer/consumer nếu bài toán thực chất chỉ truyền một chiều.

## 7. Một API sửa nhiều phần tử: UnaryOperator<T>

Giả sử muốn biến đổi từng phần tử của một danh sách **ngay tại chỗ**, bảo đảm mapper trả cùng T:

~~~java
static <T> void editAll(
        List<T> values, UnaryOperator<T> editor) {
    values.replaceAll(editor);
}
~~~

`UnaryOperator<T>` là specialization của `Function<T,T>`. Nó nhận T và trả T, rất phù hợp với thao tác **đọc → biến đổi → ghi cùng loại**.

Sử dụng:

~~~java
List<String> words = new ArrayList<>(List.of("hello", "world"));

editAll(words, String::toUpperCase);
System.out.println(words); // [HELLO, WORLD]
~~~

Chữ ký `List.replaceAll` của Java định nghĩa một `UnaryOperator<E>` phù hợp với kiểu phần tử E của danh sách. Compiler bảo đảm mapper không đột ngột biến một List<String> thành danh sách Integer.

### 7.1. Vì sao Function<T,R> không thay UnaryOperator<T> trong tình huống này?

Một `Function<String,Integer>` biến String thành Integer. Nếu muốn **thay thế phần tử trong chính List<String>**, kết quả Integer không thể lưu trở lại mà vẫn giữ `List<String>`.

~~~java
Function<String, Integer> length = String::length;

// List<String> words = ...
// words.replaceAll(length); // Không biên dịch.
~~~

Nếu nghiệp vụ muốn tạo loại danh sách mới, hãy tạo **List<R> mới** qua `Stream.map` hoặc một method biến đổi không sửa nguồn. Không nên ép unchecked để biến một List<String> thành List<Integer> trên cùng object.

## 8. Hoán đổi giữa hai danh sách: quan hệ T phải nhất quán

Khi cần trao đổi phần tử giữa **hai List**, cả hai đầu vào đều vừa cung cấp vừa nhận lại phần tử kiểu T:

~~~java
static <T> void swapFirst(List<T> left, List<T> right) {
    T oldLeft = left.get(0);
    left.set(0, right.get(0));
    right.set(0, oldLeft);
}
~~~

Gọi hợp lệ:

~~~java
List<String> left = new ArrayList<>(List.of("A"));
List<String> right = new ArrayList<>(List.of("B"));

swapFirst(left, right); // left chứa B, right chứa A.
~~~

Nhưng:

~~~java
List<String> words = new ArrayList<>(List.of("A"));
List<Integer> codes = new ArrayList<>(List.of(1));

// swapFirst(words, codes); // Không biên dịch.
~~~

Compiler không tìm được **một T đồng nhất** cho cả `List<String>` và `List<Integer>`. Nếu cho phép, phương thức có thể ghi Integer vào List<String> và String vào List<Integer>, phá cam kết kiểu.

Đây là ví dụ mà hai chữ ký kiểu `List<? extends Object>` sẽ **quá yếu**: cả hai list đều được chấp nhận để đọc Object, nhưng không có bảo đảm hai captured element types có thể ghi chéo cho nhau.

### 8.1. “Cùng T” chặt hơn “đều là subtype của Number”

~~~java
List<Integer> ints = new ArrayList<>(List.of(1));
List<Double> doubles = new ArrayList<>(List.of(2.5));

// swapFirst(ints, doubles); // Không biên dịch.
~~~

Dù Integer và Double đều extends Number, không có phép hoán đổi an toàn giữa hai list đó theo type arguments khai báo.

Nếu nghiệp vụ thật sự cần một danh sách hỗn hợp Number, caller có thể chủ động tạo hai `List<Number>` từ đầu. Nhưng không nên thay đổi kiểu nhìn của List<Integer> bằng unchecked cast để làm cho lời gọi được chấp nhận.

## 9. Copy một chiều khác hoàn toàn hoán đổi hai chiều

Đối với **truyền dữ liệu một chiều**, không nên bắt cả hai list có đúng cùng type argument nếu điều đó hạn chế caller vô ích.

Một chữ ký linh hoạt:

~~~java
static <T> void copyForward(
        List<? extends T> source,
        List<? super T> target) {

    for (T value : source) {
        target.add(value);
    }
}
~~~

Giải thích:
- Source **sinh** ra T → `? extends T`.
- Target **nhận** T → `? super T`.
- Method không đọc target như T để ghi ngược về source, nên không cần hai loại phần tử phải bằng nhau.

Ví dụ:

~~~java
List<Integer> source = List.of(7, 8);
List<Number> destination = new ArrayList<>();

copyForward(source, destination);

System.out.println(destination); // [7, 8]
~~~

`List<Integer>` có thể làm producer cho T là Number, và `List<Number>` nhận Number. Với một method chỉ truyền một chiều, chữ ký PECS thường đúng ngữ nghĩa và tái sử dụng tốt hơn `<T> void copy(List<T>,List<T>)`.

### 9.1. Đối chiếu với Collections.copy

Thư viện chuẩn cũng có chữ ký:

~~~java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src);
~~~

Trong `Collections.copy`, đích đứng **trước** nguồn; ý nghĩa type bounds vẫn như trên.

**Lưu ý hành vi rất quan trọng:** `Collections.copy` dùng thao tác thay thế phần tử theo chỉ số, không tự mở rộng danh sách. Destination phải có kích thước **ít nhất bằng source**, nếu không ném IndexOutOfBoundsException. Trong khi `copyForward` ví dụ ở trên dùng `add` để nối dữ liệu vào cuối một list mutable.

Vì vậy hai method có chữ ký PECS tương tự nhưng không hề có cùng hành vi về kích thước và vị trí lưu.

## 10. Wildcard capture: sửa trong chính một List<?> mà không biết T

Khi chỉ có:

~~~java
List<?> values;
~~~

không thể thêm tùy ý một String/Integer vì actual element type là unknown. Nhưng đôi khi tác vụ **không cần biết kiểu đó**, chỉ cần chuyển vị trí các phần tử **bên trong cùng list**.

Ví dụ hoán đổi hai phần tử:

~~~java
static void swapUnknown(List<?> values) {
    swapCaptured(values);
}

private static <T> void swapCaptured(List<T> values) {
    T first = values.get(0);
    values.set(0, values.get(1));
    values.set(1, first);
}
~~~

**Đây là mẫu wildcard capture helper**:
1. Method public nhận List<?> để không yêu cầu caller biết loại phần tử.
2. Compiler có thể capture wildcard thành một type variable tạm thời cho **cùng object** khi gọi helper.
3. Bên trong helper, mọi lần đọc/ghi dùng **cùng T**, do đó hoán đổi các giá trị đã được đọc từ danh sách vẫn type-safe.
4. Không có một giá trị T mới tùy ý nào từ bên ngoài được đưa vào danh sách.
5. Cần list mutable và đủ phần tử, nếu không có thể ném UnsupportedOperationException/IndexOutOfBoundsException.

Sử dụng:

~~~java
List<Integer> codes = new ArrayList<>(List.of(1, 2));
swapUnknown(codes);
System.out.println(codes); // [2, 1]
~~~

Điều này chứng tỏ câu “wildcard list không bao giờ ghi được” là quá đơn giản. **Với helper đã capture cùng một unknown type**, một thao tác nội bộ không làm thay đổi loại phần tử vẫn có thể an toàn.

### 10.1. Vì sao capture không giải quyết việc hoán đổi giữa hai wildcard lists?

Giả sử:

~~~java
static void invalid(List<?> first, List<?> second) {
    // Không thể tự lấy phần tử của first rồi set vào second
    // vì hai wildcard có thể là hai captured types khác nhau.
}
~~~

`first` có thể là List<String>, `second` có thể là List<Integer>. Việc cả hai dùng dấu `?` không chứng minh chúng có cùng element type.

Một helper có **một** T được áp dụng lên cùng list cho phép hoán đổi nội bộ. Nhưng để hoán đổi an toàn **giữa hai lists**, cần quan hệ kiểu mạnh hơn ở public API, ví dụ `<T> void swapFirst(List<T>, List<T>)`.

## 11. Ví dụ Java 17+ hoàn chỉnh, đã kiểm chứng

Lưu nội dung sau thành **ExactTypeDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.UnaryOperator;

public class ExactTypeDemo {
    static <T> T replaceFirst(
            List<T> values, T replacement) {
        return values.set(0, replacement);
    }

    static <T> void editAll(
            List<T> values, UnaryOperator<T> editor) {
        values.replaceAll(editor);
    }

    static <T> void swapFirst(
            List<T> left, List<T> right) {
        T oldLeft = left.get(0);
        left.set(0, right.get(0));
        right.set(0, oldLeft);
    }

    static <T> void copyForward(
            List<? extends T> source, List<? super T> target) {
        for (T value : source) {
            target.add(value);
        }
    }

    static void swapUnknown(List<?> values) {
        swapCaptured(values);
    }

    private static <T> void swapCaptured(List<T> values) {
        T first = values.get(0);
        values.set(0, values.get(1));
        values.set(1, first);
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(List.of("old", "middle"));

        System.out.println(
                "previous=" + replaceFirst(words, "new")
        );

        editAll(words, String::toUpperCase);
        System.out.println("edited=" + words);

        List<String> left =
                new ArrayList<>(List.of("A"));
        List<String> right =
                new ArrayList<>(List.of("B"));

        swapFirst(left, right);
        System.out.println(
                "swapped=" + left + "/" + right
        );

        List<Integer> codes =
                new ArrayList<>(List.of(1, 2));

        swapUnknown(codes);
        System.out.println("capture=" + codes);

        List<Integer> source = List.of(7, 8);
        List<Number> target = new ArrayList<>();

        copyForward(source, target);
        target.add(3.5);
        System.out.println("copied=" + target);

        List<? extends Number> producer = source;
        Number n = producer.get(0);
        System.out.println("read=" + n);

        List<? super Integer> consumer = target;
        consumer.add(9);

        Object item = consumer.get(0);
        System.out.println("written=" + target);
        System.out.println(
                "readBackType=" +
                item.getClass().getSimpleName()
        );
    }
}
~~~

Biên dịch bằng JDK hỗ trợ Java 17:

~~~bash
javac --release 17 -Xlint:all ExactTypeDemo.java
java ExactTypeDemo
~~~

**Stdout chính xác:**

~~~text
previous=old
edited=[NEW, MIDDLE]
swapped=[B]/[A]
capture=[2, 1]
copied=[7, 8, 3.5]
read=7
written=[7, 8, 3.5, 9]
readBackType=Integer
~~~

### 11.1. Giải thích từng kết quả

**`previous=old`**: `replaceFirst` vừa nhận String mới, vừa trả String cũ từ cùng List<String>. Generic method bảo toàn quan hệ T giữa danh sách, giá trị mới và return type.

**`edited=[NEW, MIDDLE]`**: `UnaryOperator<String>` đọc String và trả String; List.replaceAll có thể ghi kết quả trở lại đúng danh sách.

**`swapped=[B]/[A]`**: hai List<String> cùng một T nên có thể trao đổi giá trị ở hai hướng.

**`capture=[2, 1]`**: public method nhận List<?> và helper capture type argument nội bộ để hoán đổi hai giá trị có cùng kiểu đã được đọc từ chính danh sách đó.

**`copied=[7, 8, 3.5]`**: List<Integer> đưa Integer sang List<Number> qua producer extends / consumer super. Sau đó đích có thể thêm một Double vì type argument thực sự của đích là Number.

**`read=7`**: `List<? extends Number>` cho phép đọc Number an toàn từ List<Integer>.

**`written=[7, 8, 3.5, 9]`**: `List<? super Integer>` cho phép ghi Integer vào một List<Number>.

**`readBackType=Integer`**: biến đọc từ consumer wildcard có kiểu tĩnh Object; ở runtime đối tượng cụ thể tại vị trí 0 là Integer, nhưng điều đó **không đổi hợp đồng đọc** của `List<? super Integer>` thành Integer.

### 11.2. Điều kiện runtime của ví dụ

Mọi thao tác ghi dùng `ArrayList` mutable. Nếu truyền `List.of(...)` làm đích của `set`, `replaceAll` hoặc `add`, phương thức có thể ném UnsupportedOperationException dù **biên dịch hoàn toàn hợp lệ**.

`replaceFirst`, `swapFirst` và `swapCaptured` còn giả định danh sách có phần tử ở chỉ số được truy cập. Nếu list rỗng hoặc chỉ có một phần tử trong phép swap hai vị trí, có thể ném IndexOutOfBoundsException. Đây là **điều kiện dữ liệu**, không phải vấn đề generic type argument.

Không nên dùng unchecked casts để né những điều kiện đó: cast không thể biến một list immutable thành mutable hoặc tạo phần tử chưa tồn tại.

## 12. Những đoạn code cố ý không biên dịch

Các ví dụ sau được viết để **thử quy tắc kiểu**, không ghép cùng class runnable ở trên nếu muốn chạy chương trình hoàn chỉnh.

### 12.1. Thay một Integer vào List<String>

~~~java
List<String> words = new ArrayList<>(List.of("A"));

// replaceFirst(words, 42);
// Lỗi: không có T nhất quán giữa List<String> và Integer.
~~~

### 12.2. Hoán đổi List<String> và List<Integer>

~~~java
List<String> names = new ArrayList<>(List.of("A"));
List<Integer> ids = new ArrayList<>(List.of(1));

// swapFirst(names, ids);
// Lỗi suy luận: T có các equality constraints không tương thích.
~~~

### 12.3. Ghi qua extends

~~~java
List<? extends Number> source = List.of(1, 2);

// source.add(3);
// Không thể thêm một Number/Integer tùy ý vào captured subtype.
~~~

### 12.4. Đọc như T từ super

~~~java
List<? super Integer> sink = new ArrayList<Number>();

// Integer value = sink.get(0);
// Không biên dịch: kết quả chỉ có kiểu an toàn Object.
~~~

Cẩn thận: `sink.get(0)` có thể còn gây IndexOutOfBoundsException nếu đích chưa có phần tử; lỗi biên dịch ở đây xảy ra **trước khi xét runtime** vì type mismatch.

### 12.5. Ghi mapper trả loại khác vào List ban đầu

~~~java
List<String> names = new ArrayList<>(List.of("A"));
Function<String, Integer> toLength = String::length;

// names.replaceAll(toLength);
// Không hợp lệ: cần UnaryOperator<String>, không phải Function<String,Integer>.
~~~

Các ví dụ này minh họa compiler chặn **mất quan hệ kiểu** mà không cần chạy chương trình. Không được sửa bằng cách ép raw List rồi ghi sai element type.

## 13. Dùng kiểu chính xác cho Map<K,V> khi cần đọc và cập nhật value

Tương tự `List<T>`, một `Map<K,V>` có quan hệ giữa:
- Kiểu khóa `K`.
- Kiểu giá trị `V` đọc từ map.
- Kiểu giá trị `V` sẽ ghi lại vào map.

Ví dụ:

~~~java
static <K, V> V replaceValue(
        Map<K, V> map, K key, V replacement) {
    return map.put(key, replacement);
}
~~~

Nếu caller có `Map<String,Integer>`, method chỉ nhận value tương thích Integer; `Map<String,Number>` có thể nhận Integer hoặc Double dưới contract Number.

Với nhu cầu sửa giá trị dựa trên giá trị cũ:

~~~java
static <K, V> void editValue(
        Map<K, V> map, K key, UnaryOperator<V> change) {

    if (!map.containsKey(key)) {
        return;
    }

    V oldValue = map.get(key);
    map.put(key, change.apply(oldValue));
}
~~~

Bản code này được viết như **mảnh method độc lập** và cần `import java.util.Map`, `import java.util.function.UnaryOperator`. Nó cập nhật value với cùng V. Nếu map đang chứa một key gắn với null value, `oldValue` là null và `change` cần tự xử lý null; nếu map immutable, `put` có thể không được hỗ trợ.

### 13.1. Tại sao không lạm dụng Map<? extends K, ? extends V>?

Một map được nhìn qua producer wildcards:

~~~java
Map<? extends String, ? extends Number> view = someMap;
~~~

có thể cho đọc dữ liệu như String/Number ở những vị trí phù hợp, nhưng không bảo đảm cho phép cập nhật bằng một Number tùy ý vào value vì actual value type có thể là Integer, Double hoặc subtype Number khác.

Với lower bounds, có thể ghi một V phù hợp nhưng đọc lại chưa chắc ra V. Nếu API **thực sự cập nhật đúng giá trị V của Map<K,V> và trả V cũ**, named type parameters thường diễn đạt mối quan hệ tốt hơn.

Nếu nhiệm vụ là **copy entries một chiều** từ một map nguồn sang một map đích khác, có thể thiết kế wildcard tương ứng; không cần biến mọi method thành invariant khi không có quan hệ đọc-ghi hai chiều cần giữ.

## 14. So sánh chính xác: List<T>, List<? extends T>, List<? super T>

Ba chữ ký có cùng một ký tự T nhưng không có cùng ngữ nghĩa.

~~~java
static <T> void exact(List<T> list, T value) {
    list.add(value);
}

static <T> T produce(List<? extends T> list) {
    return list.get(0);
}

static <T> void consume(List<? super T> list, T value) {
    list.add(value);
}
~~~

Trong `exact`:
- Một T được suy luận từ toàn bộ các ràng buộc của lời gọi.
- Danh sách và value được gắn cùng một type argument T.
- Code có thể đọc từ list dưới dạng T khi cần.

Trong `produce`:
- List có unknown subtype của T.
- Method chỉ dùng giá trị đọc ra như T.
- Không thể thêm tùy ý value T trở lại.

Trong `consume`:
- List có unknown supertype của T.
- Method ghi value T được.
- Khi đọc, chỉ bảo đảm Object.

Điểm chính: **PECS quyết định vị trí wildcard dựa trên vai trò**, còn **named T quyết định ràng buộc chung giữa các vị trí kiểu**. Chúng bổ sung nhau, không loại trừ nhau.

## 15. Khi nào một chữ ký wildcard linh hoạt hơn và khi nào quá yếu?

### 15.1. Wildcard linh hoạt hơn: chỉ cần chuyển một chiều

~~~java
static <T> void appendAll(
        Collection<? extends T> source,
        Collection<? super T> target) {
    for (T element : source) {
        target.add(element);
    }
}
~~~

`Collection<Integer>` có thể chuyển vào `Collection<Number>`. Nếu dùng cả hai tham số `Collection<T>`, caller phải thỏa ràng buộc equality chặt hơn và có thể bị từ chối dù dữ liệu di chuyển một chiều hoàn toàn an toàn.

### 15.2. Wildcard quá yếu: cần trao đổi hai chiều

~~~java
static <T> void exchange(List<T> a, List<T> b) {
    T first = a.get(0);
    a.set(0, b.get(0));
    b.set(0, first);
}
~~~

Không thể thay bừa bằng hai tham số `List<? extends T>` rồi vẫn giữ logic, vì hai lists có thể nắm những captured subtypes khác nhau.

### 15.3. Không cần type parameter nếu chỉ một vị trí

Nếu chỉ cần nhận danh sách không rõ type và in số phần tử:

~~~java
static int sizeOf(List<?> list) {
    return list.size();
}
~~~

Không có một mối quan hệ giữa các vị trí kiểu phải đặt tên, nên `<?>` thường gọn và rõ hơn:

~~~java
static <T> int sizeOfOverGeneric(List<T> list) {
    return list.size();
}
~~~

Method thứ hai vẫn hợp lệ, nhưng type parameter T không đem lại giá trị về mối quan hệ kiểu nếu implementation và API không sử dụng T ở đâu khác. **Đừng thêm type parameter chỉ để tránh wildcard**; hãy dùng nó khi thật sự cần kết nối các vị trí.

## 16. Lưu ý về method references và kiểu Function đọc–ghi

Một API nhận mapper để **thay đổi List<T> tại chỗ** thường muốn:

~~~java
static <T> void modify(
        List<T> values, UnaryOperator<T> mapper) {
    values.replaceAll(mapper);
}
~~~

Một API tạo danh sách kết quả mới có thể muốn:

~~~java
static <T, R> List<R> transform(
        List<? extends T> input,
        Function<? super T, ? extends R> mapper) {

    List<R> output = new ArrayList<>();
    for (T item : input) {
        output.add(mapper.apply(item));
    }
    return output;
}
~~~

Ở hàm thứ hai:
- Input **chỉ được đọc** → `List<? extends T>`.
- Mapper nhận T và trả R (hoặc subtype phù hợp).
- Output là **List<R> mới**, không cần ép về List<T>.
- Hai type parameters T và R mô tả rõ việc **đầu vào và đầu ra có thể khác kiểu**.

Dùng:

~~~java
List<Integer> lengths = transform(
        List.of("Java", "Go"),
        String::length
); // [4, 2]
~~~

Nếu phải giữ danh sách gốc và kiểu phần tử gốc, hãy dùng API invariant cùng UnaryOperator<T>; nếu thật sự chuyển sang một loại kết quả mới, dùng generic Function<T,R> và tạo container R riêng.

## 17. Invariance không có nghĩa đối tượng con bị cấm

Một ngộ nhận:

> “List<T> là kiểu chính xác, tức chỉ chấp nhận phần tử có class runtime trùng hoàn toàn T.”

Sai. Với `T = Number`:

~~~java
List<Number> values = new ArrayList<>();
values.add(Integer.valueOf(4));
values.add(Double.valueOf(1.5));
~~~

Hai object có runtime classes khác nhau nhưng đều tương thích với **Number ở compile time**.

Cái không được phép là **thay type argument của collection** bằng một subtype rồi dùng nó như collection chứa supertype:

~~~java
List<Integer> integers = new ArrayList<>();
// List<Number> asNumbers = integers; // Không biên dịch.
~~~

Nghĩa của invariant là quan hệ subtype giữa **List<Integer> và List<Number>** không tự được kế thừa từ quan hệ Integer <: Number. Nó không ngăn `List<Number>` chứa những instance thuộc subclasses of Number.

## 18. Tránh sửa kiểu bằng raw cast hoặc unchecked cast

Cách làm sai dễ thấy:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));

// Không nên làm:
List raw = integers;
raw.add("text");
~~~

Nếu alias `integers` đọc phần tử "text" dưới kiểu Integer, nó có thể ném ClassCastException. Mục đích của generic method với cùng T là **không tạo đường đưa sai type argument vào data structure**.

Đừng dùng:

~~~java
// List<Number> forged = (List<Number>) (List<?>) integers;
~~~

để vượt qua invariance khi triển khai swap/copy hai chiều. Dù unchecked cast được compiler cho phép ở một vị trí có suppress warning, nó không biến collection thành loại runtime khác, và không đảm bảo dữ liệu tiếp tục đúng kiểu khi có thao tác ghi.

Nếu API hiện tại đòi invariant nhưng nghiệp vụ chỉ cần copy một chiều, hãy **đổi chữ ký thành PECS**. Nếu thực sự cần read/write hai chiều, hãy **đổi cấu trúc dữ liệu** để có cùng type argument ngay từ nơi tạo, hoặc đưa ra quy tắc chuyển đổi rõ ràng tạo object mới.

## 19. Ngoại lệ từ implementation và chính sách dữ liệu

Một generic signature hợp lệ không có nghĩa mọi thao tác thành công ở runtime.

### 19.1. Danh sách không sửa được

~~~java
List<String> fixed = List.of("A");

// replaceFirst(fixed, "B");
// Runtime UnsupportedOperationException khi gọi set.
~~~

Muốn sửa, tạo mutable copy:

~~~java
List<String> mutable = new ArrayList<>(fixed);
replaceFirst(mutable, "B");
~~~

### 19.2. Chỉ số không hợp lệ

~~~java
List<String> empty = new ArrayList<>();

// replaceFirst(empty, "A");
// Runtime IndexOutOfBoundsException.
~~~

Bài tập production cần check `isEmpty()`, quy định lỗi rõ, hoặc chọn API không phụ thuộc một index cố định.

### 19.3. Chính sách null

Java generics không tự cấm null. Một số List implementations chấp nhận null, còn factory methods như `List.of` và `List.copyOf` không chấp nhận null theo hợp đồng. Nếu API muốn cấm null, có thể yêu cầu `Objects.requireNonNull` và ghi chính sách đó rõ.

### 19.4. Side effects và thread safety

`List<T>` không tự khiến list thread-safe. Nếu nhiều thread gọi `swapFirst`, `editAll`, `replaceFirst` trên cùng mutable lists không đồng bộ, có thể gặp race conditions hoặc trạng thái bất nhất. Khi xử lý song song, cần đồng bộ phù hợp, sử dụng data structures hỗ trợ concurrency hoặc thiết kế immutable/functional mới.

## 20. Bảng chọn chữ ký API

| Mục tiêu thực tế | Gợi ý chữ ký | Lý do |
| --- | --- | --- |
| Chỉ đếm phần tử | `size(List<?>)` | Không cần biết T. |
| Chỉ đọc số | `sum(List<? extends Number>)` | Chấp nhận List<Integer>, List<Double>, List<Number>. |
| Chỉ thêm Integer | `append(List<? super Integer>)` | Chấp nhận đích List<Integer>, Number, Object. |
| Thay một phần tử và trả phần tử cũ | `<T> T replace(List<T>, T)` | Đọc và ghi cùng T. |
| Sửa mọi phần tử tại chỗ | `<T> void edit(List<T>, UnaryOperator<T>)` | T→T và ghi vào List<T>. |
| Hoán đổi hai danh sách cùng type argument | `<T> void swap(List<T>, List<T>)` | Bảo đảm cùng T ở hai hướng. |
| Hoán đổi bên trong một list chưa biết T | `swap(List<?>)` + capture helper | Chỉ đổi vị trí giá trị của cùng captured T. |
| Copy từ producer sang consumer | `<T> copy(List<? extends T>, List<? super T>)` | Không buộc hai type arguments giống hệt. |
| Biến T thành R và tạo kết quả mới | `<T,R> List<R> map(List<? extends T>, Function<? super T,? extends R>)` | Cho phép đổi loại dữ liệu. |
| Cập nhật map và trả giá trị V cũ | `<K,V> V replace(Map<K,V>,K,V)` | Giữ quan hệ key/value ở cả đọc và ghi. |

Đây là **gợi ý chữ ký theo vai trò**, không phải yêu cầu mọi method trên thế giới có đúng một hình dạng. Chọn theo bất biến dữ liệu, yêu cầu sửa đổi, và mức linh hoạt cần cấp cho caller.

## 21. Checklist review API generics

1. **Ghi rõ chiều luồng dữ liệu**: collection chỉ tạo ra giá trị, chỉ nhận giá trị hay cả hai?
2. **Nếu chỉ đọc**, cân nhắc `? extends T` để chấp nhận subtype producers.
3. **Nếu chỉ ghi**, cân nhắc `? super T` để chấp nhận supertype consumers.
4. **Nếu cần đọc–ghi cùng loại**, dùng **named type parameter T** thống nhất giữa collection, input values, mapper và output.
5. **Nếu có hai collection tương tác**, xác định chiều copy hay exchange; một chiều có thể dùng PECS, hai chiều có thể cần cùng T.
6. **Nếu chỉ dùng T ở một vị trí**, xem có thể dùng `<?>` thay cho type parameter T vô ích không.
7. **Không coi List<Object> và List<?> giống nhau**: List<Object> chấp nhận Object khi ghi; List<?> giữ unknown element type.
8. **Khi wildcard cần thao tác nội bộ**, cân nhắc capture helper và bảo đảm không trộn hai unknown captures khác nhau.
9. **Tránh unchecked casts và raw types** để phá invariance hoặc đánh lừa compiler.
10. **Kiểm tra mutability/indices/null** vì type safety không bảo đảm thao tác trên List thực sự được hỗ trợ.
11. **Tránh shared mutable state không đồng bộ**, nhất là method đổi nhiều collections.
12. **Dùng UnaryOperator<T> cho in-place transform**, Function<T,R> cho transform có thể đổi kiểu và trả container mới.
13. **Không lạm dụng type parameter để tạo sự phức tạp giả**: chính xác khi cần bảo toàn quan hệ; wildcard khi chỉ cần linh hoạt một hướng.
14. **Biên dịch với Java release mục tiêu** và thử cả trường hợp hợp lệ, không hợp lệ để xác nhận compile-time contract.

## 22. Câu hỏi tự kiểm tra

**1.** Tại sao `List<? extends Number>` cho đọc Number nhưng không cho thêm một Integer tùy ý?

**Đáp án:** Actual element type có thể là một subtype Number chưa biết (ví dụ Double), nên một Integer mới chưa chắc an toàn với mọi khả năng.

**2.** Tại sao `List<? super Integer>` nhận Integer nhưng `get` chỉ có thể dùng như Object?

**Đáp án:** Actual type argument có thể là Integer, Number hoặc Object; compiler không biết mọi phần tử được đọc đều là Integer.

**3.** Vì sao `<T> T replaceFirst(List<T>,T)` tốt hơn hai wildcards cho tác vụ cập nhật?

**Đáp án:** Cùng T liên hệ kiểu danh sách, replacement và giá trị trả về; method cần đồng thời ghi và đọc đúng loại đã khai báo.

**4.** `List<Integer>` có thể gán thành `List<Number>` không?

**Đáp án:** Không. Java generic types nhìn chung invariant; nếu gán được, một Double có thể được thêm vào list dành cho Integer.

**5.** Hai List<String> dùng được với `<T> void swapFirst(List<T>,List<T>)` không?

**Đáp án:** Có. Compiler chọn T là String và mọi giá trị hoán đổi giữ được type.

**6.** Hai List<String> và List<Integer> có hoán đổi bằng method đó được không?

**Đáp án:** Không. Compiler không tìm được một T thống nhất vì hai parameterized list types bất biến.

**7.** Vì sao `copyForward(List<? extends T>,List<? super T>)` có thể chấp nhận List<Integer> và List<Number>?

**Đáp án:** Một chiều dữ liệu: source sinh Integer dùng như Number, target nhận Number; không có yêu cầu ghi ngược Number vào List<Integer>.

**8.** `List<?>` có cho đổi chỗ hai phần tử trong chính nó được không?

**Đáp án:** Có thể, nếu list mutable, qua generic helper để capture unknown element type rồi đọc/ghi những giá trị lấy từ cùng list. Không được tự thêm một giá trị bên ngoài với type bất kỳ.

**9.** Vì sao hai `List<?>` khác nhau không thể mặc nhiên hoán đổi phần tử?

**Đáp án:** Hai wildcards có thể là hai captured types khác nhau, như String và Integer; không có bảo đảm hai chiều.

**10.** Tại sao `UnaryOperator<T>` phù hợp khi dùng `List.replaceAll`?

**Đáp án:** UnaryOperator nhận T và trả T, phù hợp với việc lấy element T rồi ghi trở lại cùng List<T>.

**11.** Khi cần biến String thành Integer và trả list mới, nên thiết kế API thế nào?

**Đáp án:** Dùng `Function<? super T,? extends R>` để tạo R và một `List<R>` mới; không biến List<String> gốc thành List<Integer> bằng unchecked cast.

**12.** `List<T>` có đảm bảo có thể gọi `set` không?

**Đáp án:** Không. List.of và những immutable/unmodifiable implementations có thể ném UnsupportedOperationException ở runtime; type parameter không mô tả mutability.

**13.** Trong Map<K,V>, nếu đọc value V rồi áp dụng UnaryOperator<V> và put lại, nên dùng kiểu gì?

**Đáp án:** `Map<K,V>` cùng type variable V ở chỗ đọc/ghi; nó giữ value type thống nhất.

**14.** Nếu một method chỉ trả `list.size()` thì có cần `<T>` không?

**Đáp án:** Thường không. `List<?>` đủ vì không có quan hệ T qua nhiều vị trí cần biểu đạt.

**15.** Nếu compiler chặn một phép ghi vào `List<? extends T>`, nên sửa bằng raw cast không?

**Đáp án:** Không. Hãy xem method có cần named T cho quan hệ đọc–ghi, hay cần cấu trúc mới/PECS để mô tả đúng chiều dữ liệu. Unchecked cast có thể tạo heap pollution.

## 23. Ghi nhớ

**Đặt wildcard theo hướng dữ liệu, đặt named type parameter theo quan hệ cần bảo toàn.**

~~~text
Đọc một chiều:    List<? extends T> ────→ T
Ghi một chiều:    T ────→ List<? super T>

Đọc rồi ghi lại cùng loại:
                  List<T> ────→ T ──transform──→ T ────→ List<T>

Hoán đổi hai chiều:
                  List<T> ⇄ List<T>
                  (cùng một T)

Một list chưa biết phần tử:
                  List<?> ──capture T──→ đọc/ghi nội bộ cùng T
~~~

Chọn **`List<T>`** hoặc **`Map<K,V>`** khi method cần lấy phần tử/vị trí có kiểu được khai báo rồi ghi lại một giá trị **phù hợp cùng type parameter**. Chọn **`? extends T`** khi muốn nhận producer linh hoạt, **`? super T`** khi muốn nhận consumer linh hoạt, và **`<?>`** khi không cần đặt tên cho loại phần tử.

Không vì một warning hay lỗi inference mà ép raw/unchecked để lách hệ thống kiểu. Đúng hơn là xem lại **mối quan hệ giữa các đầu vào, các giá trị được đọc và các giá trị được ghi**. Một chữ ký generic tốt phải mô tả chính xác mối quan hệ đó, đủ linh hoạt cho caller nhưng không mở đường phá vỡ tính an toàn của dữ liệu.
