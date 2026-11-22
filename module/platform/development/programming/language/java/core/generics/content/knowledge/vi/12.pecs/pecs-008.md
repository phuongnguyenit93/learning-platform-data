# Đọc chữ ký `Collections.copy`, `addAll` và `Comparator` qua quy tắc PECS

Khi đọc mã nguồn, tài liệu Javadoc hoặc chữ ký phương thức của Java Collections Framework, chúng ta thường gặp các kiểu như `? extends T` và `? super T`. Thay vì học thuộc từng API, hãy đọc chữ ký theo **luồng dữ liệu**: tham số nào **cung cấp** giá trị thuộc kiểu `T` cho phương thức, và tham số nào **nhận** hoặc **tiêu thụ** các giá trị `T` đó?

Quy tắc **PECS — Producer Extends, Consumer Super** giúp giải mã các chữ ký quan trọng:

~~~java
// Các chữ ký đã giản lược tên package và modifier để dễ đọc.
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src);

public boolean addAll(Collection<? extends E> c); // Collection<E>

public static <T> boolean addAll(
        Collection<? super T> c,
        T... elements); // Collections

public void sort(Comparator<? super E> c); // List<E>
~~~

Những dòng trên là **chữ ký để phân tích**, không phải một chương trình có thể biên dịch độc lập. `Collections.copy` sao chép vào các vị trí có sẵn; `Collection.addAll` nối các phần tử từ một collection nguồn; `Collections.addAll` nhận những phần tử varargs; `List.sort` tiêu thụ một `Comparator` có khả năng so sánh các phần tử trong danh sách.

Bài học tập trung vào cách **đọc chính xác từng chữ ký**, xác định đối số kiểu có thể truyền, hiểu lỗi compile-time, và phân biệt các điều kiện runtime mà generic không bảo đảm.

## 1. Nhắc lại quy tắc cần để đọc API

Generic class/interface Java thông thường **bất biến** theo đối số kiểu:

~~~java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // LỖI BIÊN DỊCH.
~~~

Đây là **đoạn minh họa** (cần import `java.util.*` và đặt trong class). Mặc dù `Integer` là subtype của `Number`, `List<Integer>` không là subtype của `List<Number>`. Nếu phép gán được chấp nhận, mã khác có thể gọi `numbers.add(3.5)` và phá vỡ hợp đồng của `List<Integer>`.

Wildcard giữ an toàn kiểu mà vẫn cho phép sử dụng quan hệ subtype theo **một chiều thao tác phù hợp**:

| Loại | Ý nghĩa với phần tử `T` | Khả năng biên dịch cốt lõi |
| --- | --- | --- |
| `? extends T` | Kiểu thực là `T` hoặc **subtype** của `T` | Đọc phần tử thành `T`; không thêm một `T` bất kỳ |
| `? super T` | Kiểu thực là `T` hoặc **supertype** của `T` | Thêm `T`; đọc ra chỉ bảo đảm `Object` |
| `T` không có wildcard | Đối số kiểu chính xác, khi `T` đã xác định | Có thể đọc/ghi `T` theo hợp đồng của container |

Góc nhìn `extends` không có nghĩa collection thực sự immutable. Nó vẫn có thể cho xóa hoặc xóa sạch; ngược lại, góc nhìn `super` không bảo đảm đối tượng collection có thể sửa ở runtime. PECS chủ yếu là **hợp đồng tương thích kiểu**.

Ta sẽ lần lượt đọc các phương thức theo bốn câu hỏi:

1. **`T` hoặc `E` là gì?** Nó được khai báo ở class hay ở chính phương thức?
2. **Tham số nào là nguồn, tham số nào là đích?**
3. **Các kiểu con/cha nào được chấp nhận?** Suy ra từ `extends` hoặc `super`.
4. **Khi chạy, phương thức làm gì với cấu trúc collection?** Nối thêm, ghi đè, sắp xếp và điều kiện tiền đề khác nhau.

## 2. Giải mã `Collections.copy`: nguồn `extends`, đích `super`

Chữ ký của tiện ích `java.util.Collections`:

~~~java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src);
~~~

Đây là **chữ ký phương thức để đọc**, không cần tự khai báo lại API này.

Đọc từ trái sang phải:

- `<T>`: **type parameter của phương thức**. Compiler có thể suy luận `T` từ đối số truyền vào hoặc caller có thể chọn tường minh.
- `dest: List<? super T>`: đích có đối số kiểu là `T` hoặc supertype của `T`, nên nhận được mọi phần tử được dùng như `T`.
- `src: List<? extends T>`: nguồn có đối số kiểu là `T` hoặc subtype của `T`, nên đọc các phần tử nguồn thành `T` an toàn.
- `void`: phương thức thay đổi `dest` và không trả về danh sách mới.
- `static`: gọi bằng `Collections.copy(dest, src)`, không gọi trên instance của `List`.

Từ chữ ký đã suy ra quan hệ hợp lệ: ví dụ có thể chuyển các phần tử `Integer` từ `List<Integer>` sang `List<Number>` hoặc `List<Object>` mà không ép kiểu.

### 2.1. Ví dụ chạy được và đầu ra

Tạo **`CollectionsCopyReadingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CollectionsCopyReadingDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(4, 5);
        List<Number> destination =
                new ArrayList<>(List.of(0, 0, 0));

        Collections.<Number>copy(destination, source);

        System.out.println("source = " + source);
        System.out.println("destination = " + destination);
        System.out.println("source size = " + source.size());
        System.out.println("destination size = " + destination.size());
    }
}
~~~

Biên dịch/chạy bằng Java 17 trở lên:

~~~bash
javac CollectionsCopyReadingDemo.java
java CollectionsCopyReadingDemo
~~~

Stdout chính xác:

~~~text
source = [4, 5]
destination = [4, 5, 0]
source size = 2
destination size = 3
~~~

`Collections.<Number>copy(...)` xác định rõ `T = Number`. Khi ấy:

- `src` yêu cầu `List<? extends Number>`, nên `List<Integer>` hợp lệ.
- `dest` yêu cầu `List<? super Number>`, nên `List<Number>` hợp lệ.
- Phương thức **ghi đè phần tử tại index 0 và 1** của đích, giữ nguyên phần tử index 2.
- Nó không thay đổi kích thước collection đích và không thay đổi nguồn.

Cũng có thể viết `Collections.copy(destination, source)`; compiler thường suy luận được kiểu phù hợp trong ví dụ này. Cú pháp `<Number>` chỉ nhằm làm lộ rõ cách áp dụng cận `extends`/`super` khi đọc chữ ký.

### 2.2. Điều kiện runtime quan trọng: không tự append

`Collections.copy` yêu cầu `dest.size() >= src.size()` ngay trước khi sao chép. Nếu đích ngắn hơn nguồn, nó ném `IndexOutOfBoundsException`, dù hai kiểu generic tương thích.

Ví dụ **cố ý gây lỗi runtime**:

~~~java
List<Integer> src = List.of(1, 2);
List<Number> dest = new ArrayList<>();

Collections.copy(dest, src); // Biên dịch nhưng ném IndexOutOfBoundsException.
~~~

Đoạn này cần import `java.util.*` và đặt trong class; mục tiêu chỉ để phân biệt hợp đồng runtime với kiểm tra kiểu. Ngoài ra, `dest` phải cho phép cập nhật bằng `set(index, value)`; danh sách không hỗ trợ sửa có thể ném `UnsupportedOperationException`.

**Đừng suy luận rằng `copy` tạo bản sao `List` mới.** Nó ghi vào **danh sách đích đã tồn tại**. Khi cần nối phần tử vào cuối, dùng `addAll`; khi cần một collection mới, dùng constructor như `new ArrayList<Number>(source)`.

### 2.3. Trường hợp gán đích/ngược chiều bị cấm

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<Number> numbers = new ArrayList<>(List.of(0, 0));

Collections.copy(numbers, integers); // Hợp lệ.
// Collections.copy(integers, numbers); // LỖI BIÊN DỊCH.
~~~

Tại chiều bị cấm, nguồn có thể đưa ra một `Double` qua `List<Number>`, trong khi đích `List<Integer>` chỉ nhận `Integer`. Wildcard chặn thao tác không an toàn **ngay tại vị trí gọi**.

## 3. `Collection<E>.addAll(Collection<? extends E>)`: collection nhận dữ liệu, đối số là nguồn

Chữ ký instance method trong giao diện `Collection<E>`:

~~~java
boolean addAll(Collection<? extends E> c);
~~~

Đây là **chữ ký giản lược để phân tích**. Cần xác định `E` là gì: `E` **thuộc kiểu generic của receiver**, tức đối tượng đứng bên trái dấu chấm khi gọi `destination.addAll(source)`.

Ví dụ:

~~~java
List<Number> destination = new ArrayList<>();
List<Integer> source = List.of(10, 20);

boolean changed = destination.addAll(source);
~~~

Ở đây receiver có kiểu `List<Number>`, nên `E = Number`. Tham số `c` trở thành `Collection<? extends Number>` và có thể nhận `List<Integer>`. Ta đọc chữ ký:

- `destination` **nhận thêm** các `Number` (và subtype).
- `source` **cung cấp** các phần tử tương thích `Number` cho receiver.
- Vì tham số `source` là producer, chữ ký dùng `extends`.
- Giá trị trả về `boolean` biểu thị collection **có thay đổi hay không** do lời gọi, không phải số phần tử được thêm.
- Phương thức thêm các phần tử vào receiver theo hợp đồng của implementation; ví dụ `List` thường thêm ở cuối, còn `Set` chỉ giữ phần tử chưa trùng theo quy tắc equality của set.

Cần chú ý: ở chữ ký của `Collection.addAll`, **không có tham số `? super E` cho destination** vì chính receiver đã được khai báo `Collection<E>`. Trong `Collections.copy`, cả nguồn và đích đều được truyền làm tham số, nên cả hai chiều được viết tường minh.

### 3.1. Chương trình chạy được: `List.addAll` và `Set.addAll`

Tạo **`CollectionAddAllDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class CollectionAddAllDemo {
    public static void main(String[] args) {
        List<Integer> integers = List.of(2, 4);
        List<Double> doubles = List.of(1.5, 2.5);
        List<Number> numbers = new ArrayList<>();

        boolean firstChange = numbers.addAll(integers);
        boolean secondChange = numbers.addAll(doubles);

        System.out.println("numbers = " + numbers);
        System.out.println("changes = " + firstChange + ", " + secondChange);

        Set<Number> unique = new LinkedHashSet<>();
        unique.add(2);
        boolean unchanged = unique.addAll(integers);

        System.out.println("unique = " + unique);
        System.out.println("unchanged = " + unchanged);
    }
}
~~~

Chạy:

~~~bash
javac CollectionAddAllDemo.java
java CollectionAddAllDemo
~~~

Stdout chính xác:

~~~text
numbers = [2, 4, 1.5, 2.5]
changes = true, true
unique = [2, 4]
unchanged = true
~~~

Ở đây `unique` ban đầu chỉ chứa `2`, nên `addAll(integers)` thêm được `4` và trả về `true`. Tên biến `unchanged` dễ gây hiểu lầm: boolean từ `addAll` báo **collection có thay đổi hay không**, không phải trạng thái 'không đổi'. Nếu `unique` đã chứa cả `2` và `4` thì cùng lời gọi sẽ trả về `false`.

### 3.2. Khi `addAll` không tương thích kiểu

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = List.of(1, 2.5);

// integers.addAll(numbers); // LỖI BIÊN DỊCH.
~~~

Receiver `integers` có `E = Integer`, nên tham số phải là `Collection<? extends Integer>`. `List<Number>` không bảo đảm mọi phần tử là `Integer`. Điều này giải thích vì sao hướng `numbers.addAll(integers)` hợp lệ, còn hướng ngược lại không.

### 3.3. Các điều kiện ngoài PECS

- `List.addAll` thường nối thêm phần tử vào cuối theo thứ tự iterator của nguồn; `Set.addAll` có thể bỏ phần tử trùng, tùy semantics của `equals`/`hashCode`.
- Receiver có thể không hỗ trợ sửa và ném `UnsupportedOperationException` (ví dụ `List.of(...)`).
- Một collection có thể hạn chế `null` hoặc kiểu phần tử theo đặc thù runtime dù chữ ký generic đã đúng.
- `Collection.addAll` có quy định về trường hợp source cũng chính là collection đang được thêm vào; không nên giả định mọi implementation xử lý self-add an toàn, đặc biệt khi nó không rỗng.

## 4. `Collections.addAll(Collection<? super T>, T...)`: phía đích được diễn đạt bằng `super`

Java có **một API khác trùng tên `addAll`**: phương thức tĩnh trong lớp tiện ích `java.util.Collections`:

~~~java
public static <T> boolean addAll(
        Collection<? super T> c,
        T... elements);
~~~

Đừng nhầm nó với `Collection<E>.addAll(Collection<? extends E>)`. Hai phương thức có **receiver và hướng dữ liệu** khác nhau.

Phân tích:

- `<T>`: một type parameter **của chính phương thức**, được suy luận từ các argument hoặc chọn tường minh.
- `c: Collection<? super T>`: collection là **consumer** của các phần tử `T`; chấp nhận collection của `T` hoặc supertype của `T`.
- `T... elements`: các giá trị `T` sẽ được **cung cấp** để thêm vào collection; đây là varargs, không phải một `Collection<? extends T>`.
- `boolean`: trả true nếu collection thay đổi sau thao tác.

### 4.1. Chương trình chạy được: dùng `Collections.addAll`

Tạo **`CollectionsAddAllDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;

public class CollectionsAddAllDemo {
    public static void main(String[] args) {
        Collection<Number> numbers = new ArrayList<>();
        Collection<Object> objects = new ArrayList<>();

        boolean addedNumbers =
                Collections.<Number>addAll(numbers, 1, 2.5, 3L);
        boolean addedObjects =
                Collections.<Integer>addAll(objects, 7, 8);

        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("changed = " + addedNumbers + ", " + addedObjects);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CollectionsAddAllDemo.java
java CollectionsAddAllDemo
~~~

Stdout:

~~~text
numbers = [1, 2.5, 3]
objects = [7, 8]
changed = true, true
~~~

Từ ký pháp tường minh `Collections.<Number>addAll(...)`:

- Các giá trị `1`, `2.5` và `3L` lần lượt được boxing thành `Integer`, `Double` và `Long`, đều tương thích với `Number`.
- `Collection<Number>` là một `Collection<? super Number>` hợp lệ.
- Ở `Collections.<Integer>addAll(objects, 7, 8)`, đích `Collection<Object>` phù hợp vì `Object` là supertype của `Integer`.
- Các giá trị `Number` khi in bằng `toString()` cho chuỗi `1`, `2.5`, `3` như stdout.

Trong mã ứng dụng thường có thể bỏ type argument tường minh để compiler suy luận, ví dụ `Collections.addAll(numbers, 1, 2.5, 3L)`. Ở đây ta viết `<Number>` để người học nhìn thấy mối liên hệ với `? super T`.

### 4.2. Đặt hai loại `addAll` cạnh nhau

| API | Dạng gọi | Ai là nguồn? | Ai là đích? | Vị trí wildcard | Giá trị trả về |
| --- | --- | --- | --- | --- | --- |
| `Collection<E>.addAll(Collection<? extends E>)` | `dest.addAll(src)` | Tham số collection `src` | Receiver `dest` | `src` có `extends E` | `boolean` |
| `Collections.<T>addAll(Collection<? super T>, T...)` | `Collections.addAll(dest, a, b)` | Các giá trị varargs `a`, `b` | Tham số collection `dest` | `dest` có `super T` | `boolean` |

Điểm chung là **dữ liệu đi vào collection đích với kiểu an toàn**. Điểm khác là một API đọc từ một collection nguồn, còn API kia nhận các phần tử riêng lẻ qua varargs.

Ví dụ nhận diện sai cú pháp:

~~~java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = List.of(1, 2);

numbers.addAll(integers); // Hợp lệ: instance addAll.
// Collections.addAll(numbers, integers); // Không phải cách thêm từng Integer.
~~~

Dòng tĩnh cuối nếu không chú thích sẽ gây **lỗi kiểu**: `Collections.addAll(numbers, integers)` cố đưa **chính đối tượng `List<Integer>` như một phần tử** vào `Collection<Number>`, trong khi `List<Integer>` không phải `Number`. Muốn dùng phiên bản tĩnh, truyền từng phần tử phù hợp: `Collections.addAll(numbers, 3, 4)`.

## 5. Vì sao `Comparator<? super T>` cũng là Consumer Super?

`Comparator<T>` không chứa danh sách. Nó biểu diễn một đối tượng có phương thức so sánh **hai giá trị `T`**:

~~~java
@FunctionalInterface
public interface Comparator<T> {
    int compare(T left, T right);
}
~~~

Đây là **chữ ký minh họa giản lược** của `Comparator`: trong JDK thật, interface còn khai báo và kế thừa các phương thức khác. Đừng tạo lại interface này khi sử dụng Java Collections Framework.

Phương thức so sánh **nhận** hai giá trị `T` từ caller, nên comparator đóng vai trò **consumer của các giá trị `T`**. Nếu một comparator so sánh được `Number` nói chung, nó đương nhiên so sánh được các `Integer`, là subtype của `Number`.

Do đó, `List<E>.sort` khai báo:

~~~java
default void sort(Comparator<? super E> c);
~~~

và `Collections.sort` có overload:

~~~java
public static <T> void sort(
        List<T> list,
        Comparator<? super T> c);
~~~

Đây là **các chữ ký để phân tích**, không phải mã class chạy độc lập. Ta đọc chúng như sau:

- Danh sách lưu chính xác các giá trị kiểu `E`/`T`.
- Comparator được **truyền vào để tiêu thụ** các phần tử từ danh sách, nên chấp nhận comparator có đối số kiểu `E`/`T` hoặc một **supertype**.
- Chỉ dùng `Comparator<E>` sẽ hạn chế không cần thiết: một `Comparator<Number>` xử lý được `Integer` nhưng sẽ không được truyền cho `List<Integer>`.
- Chiều ngược lại không an toàn: một `Comparator<Integer>` không thể được bảo đảm so sánh mọi phần tử của `List<Number>`, vì danh sách có thể chứa `Double`.

### 5.1. Chương trình chạy được: `Comparator<Number>` sắp xếp `List<Integer>`

Tạo **`ComparatorSuperDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class ComparatorSuperDemo {
    public static void main(String[] args) {
        Comparator<Number> byNumericValue = (a, b) ->
                Double.compare(a.doubleValue(), b.doubleValue());

        List<Integer> integers = new ArrayList<>(List.of(9, 2, 5));
        integers.sort(byNumericValue);
        System.out.println("integers = " + integers);

        List<Number> mixed = new ArrayList<>(List.of(3.5, 1, 2.0));
        Collections.sort(mixed, byNumericValue);
        System.out.println("mixed = " + mixed);
    }
}
~~~

Chạy:

~~~bash
javac ComparatorSuperDemo.java
java ComparatorSuperDemo
~~~

Stdout chính xác:

~~~text
integers = [2, 5, 9]
mixed = [1, 2.0, 3.5]
~~~

Tại `integers.sort(byNumericValue)`, `E = Integer`, còn tham số của `sort` là `Comparator<? super Integer>`. `Comparator<Number>` phù hợp vì `Number` là supertype của `Integer`. Phương thức `compare(Number, Number)` có thể nhận các `Integer` bất kỳ.

`Collections.sort(mixed, byNumericValue)` cũng hợp lệ vì danh sách của `Number` có comparator chính xác `Comparator<Number>`.

Lưu ý rằng comparator ví dụ biến mỗi số thành `double` để so sánh. Cách đó chỉ để minh họa quan hệ kiểu; với các số nguyên rất lớn, `BigDecimal` có yêu cầu chính xác đặc thù hoặc giá trị `NaN`, không nên dùng cách so sánh này một cách máy móc trong hệ thống thực. Chữ ký `Comparator<? super T>` bảo đảm **tương thích kiểu**, không bảo đảm comparator có thứ tự hợp lý hoặc nhất quán với `equals`.

### 5.2. Ví dụ bất hợp lệ theo hướng ngược lại

~~~java
Comparator<Integer> onlyIntegers = Integer::compare;
List<Number> mixed = new ArrayList<>(List.of(1, 2.5));

// mixed.sort(onlyIntegers); // LỖI BIÊN DỊCH.
~~~

Đoạn này cần import `java.util.*` và đặt trong class. `List<Number>` có thể chứa `Double`, mà `Comparator<Integer>` không hứa xử lý. Compiler từ chối để tránh việc comparator bị gọi với giá trị không phù hợp.

Tương tự, `List<Integer>.sort` được phép nhận một `Comparator<Object>` nếu comparator ấy có logic so sánh mọi `Object` phù hợp. Hợp đồng kiểu không nói rằng cách so sánh đó có nghĩa toán học; đây là trách nhiệm của implementation comparator.

## 6. Một bảng đối chiếu ba API theo luồng dữ liệu

| API/chữ ký | Dữ liệu đi từ đâu? | Dữ liệu đi tới đâu? | Wildcard producer | Wildcard consumer |
| --- | --- | --- | --- | --- |
| `Collections.copy(List<? super T> dest, List<? extends T> src)` | `src` | `dest`, ghi đè các vị trí đã có | `src: ? extends T` | `dest: ? super T` |
| `Collection<E>.addAll(Collection<? extends E> c)` | Tham số `c` | Receiver `this` | `c: ? extends E` | Đích là receiver `Collection<E>` |
| `Collections.addAll(Collection<? super T> c, T... elements)` | Các đối số varargs | Tham số `c` | Giá trị `T...` đã định kiểu | `c: ? super T` |
| `List<E>.sort(Comparator<? super E> c)` | Các phần tử của receiver `List<E>` | `c.compare` tiêu thụ hai `E` | Danh sách phát ra giá trị `E` | `c: ? super E` |

Hãy đặc biệt chú ý rằng **consumer không nhất thiết là một collection**: comparator, callback hoặc hàm có đầu vào kiểu `T` đều có thể đóng vai trò consumer.

Với mỗi chữ ký, hãy tự diễn đạt: “Đối tượng này **đọc/trả** `T` cho ai?” hoặc “Đối tượng này **nhận** `T` từ ai?”. Dấu `extends`/`super` sẽ trở nên tự nhiên.

## 7. Đọc generic type inference đúng cách

Hai loại type parameter rất dễ lẫn:

- **`E` thuộc `Collection<E>`/`List<E>`:** thường được xác định từ kiểu của receiver, ví dụ `List<Number> numbers` → `E = Number` tại `numbers.addAll(...)`.
- **`T` thuộc phương thức tĩnh `Collections.<T>copy` hoặc `Collections.<T>addAll`:** được suy luận ở **từng lời gọi** từ các tham số, hoặc được caller chỉ định rõ.

Ví dụ:

~~~java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>(List.of(0, 0));

Collections.<Number>copy(numbers, integers); // Hợp lệ.
Collections.<Integer>copy(numbers, integers); // Cũng hợp lệ.
~~~

Đây là **đoạn minh họa cần import `java.util.*` và đặt trong class**.

Với `T = Number`: nguồn `List<Integer>` phù hợp `List<? extends Number>`; đích `List<Number>` phù hợp `List<? super Number>`.

Với `T = Integer`: nguồn `List<Integer>` phù hợp `List<? extends Integer>`; đích `List<Number>` phù hợp `List<? super Integer>`.

**Không nhất thiết `T` phải bằng đúng đối số kiểu của nguồn hoặc đích.** Chỉ cần tồn tại một `T` thỏa đồng thời **nguồn ở phía dưới** và **đích ở phía trên** quan hệ subtype. Đây là lý do phương thức generic có thể biểu diễn nhiều kết hợp hơn kiểu bất biến cố định.

Ngược lại:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<Number> numbers = List.of(3, 4.5);

// Collections.<Number>copy(integers, numbers); // LỖI BIÊN DỊCH.
// Collections.<Integer>copy(integers, numbers); // LỖI BIÊN DỊCH.
~~~

Với `T = Number`, `List<Integer>` không là đích `List<? super Number>`. Với `T = Integer`, `List<Number>` không là nguồn `List<? extends Integer>`. Hai hướng đều không thỏa đồng thời cận kiểu.

### Đừng nhầm thứ tự tham số

`Collections.copy(dest, src)` đặt **đích trước, nguồn sau**. Điều này khác với một số hàm tự thiết kế có chữ ký `copy(source, destination)`. Khi sử dụng API thư viện, hãy đọc **tên tham số và Javadoc**, đừng chỉ suy từ tên `copy`.

## 8. Ba chương trình sai kiểu có chủ đích và cách sửa

### Sai kiểu 1 — Dùng `Collections.copy` để nạp một đích rỗng

~~~java
List<Integer> src = List.of(1, 2);
List<Number> dest = new ArrayList<>();

// Collections.copy(dest, src); // Biên dịch nhưng runtime IndexOutOfBoundsException.
dest.addAll(src); // Đúng nếu mục tiêu là nối hai phần tử.
~~~

`Collections.copy` là thao tác ghi đè, còn `addAll` là thao tác thêm vào collection. Thay API theo **hành vi cần thiết**, không chỉ theo cận generic.

### Sai kiểu 2 — Dùng phiên bản `Collections.addAll` để thêm cả collection

~~~java
List<Integer> src = List.of(1, 2);
List<Number> dest = new ArrayList<>();

// Collections.addAll(dest, src); // Sai: List<Integer> không phải Number.
dest.addAll(src);                  // Đúng: collection là nguồn.
Collections.addAll(dest, 3, 4);   // Đúng: mỗi phần tử là Number.
~~~

Nếu muốn gọi `Collections.addAll` với các phần tử từ source, có thể tự duyệt source hoặc biến đổi thành mảng phù hợp, nhưng thường `dest.addAll(src)` đã đúng và đơn giản hơn.

### Sai kiểu 3 — Dùng comparator quá hẹp cho danh sách

~~~java
Comparator<Integer> integerOnly = Integer::compare;
List<Number> mixed = new ArrayList<>(List.of(1, 2.5));

// mixed.sort(integerOnly); // LỖI: comparator không chấp nhận mọi Number.
Comparator<Number> numeric =
        (a, b) -> Double.compare(a.doubleValue(), b.doubleValue());
mixed.sort(numeric); // Hợp lệ.
~~~

Dùng comparator phù hợp **ít nhất với toàn bộ miền kiểu phần tử của list**. Không ép kiểu unchecked để bỏ qua cảnh báo compiler.

## 9. Các điều kiện runtime ngoài chữ ký

Đọc đúng chữ ký generic là bước cần thiết nhưng **chưa đủ** để khẳng định lời gọi chạy thành công.

### 9.1. `Collections.copy` cần danh sách đích đủ dài và có thể thay đổi

- `dest.size() < src.size()`: `IndexOutOfBoundsException`.
- `dest` không hỗ trợ cập nhật phần tử: có thể là `UnsupportedOperationException`.
- `dest.size() > src.size()`: các phần tử còn lại ở đích không bị thay đổi; kích thước giữ nguyên.
- Phương thức **sao chép các tham chiếu phần tử**, không tự động clone sâu các đối tượng.

### 9.2. `addAll` chịu quy tắc của collection đích

- `ArrayList.addAll` thêm phần tử và thường giữ thứ tự nguồn được duyệt.
- `Set.addAll` có thể không làm thay đổi collection nếu các phần tử đã tồn tại.
- Collection không hỗ trợ sửa có thể ném `UnsupportedOperationException`.
- Có collection hạn chế `null` hoặc phần tử không phù hợp theo quy tắc riêng.
- `boolean` cho biết **collection đã thay đổi hay chưa**; không phải một con số đếm.

### 9.3. `sort` cần comparator có hợp đồng nhất quán

`Comparator<? super T>` chỉ khẳng định comparator **nhận được các đối tượng kiểu `T`**. Nó không tự bảo đảm so sánh bắc cầu, nhất quán về thứ tự hoặc xử lý `null`. Comparator vi phạm hợp đồng tổng quát có thể khiến phép sắp xếp cho kết quả sai hoặc ném `IllegalArgumentException` trong một số tình huống. `List.of(...)` không hỗ trợ sắp xếp tại chỗ vì list không cho sửa.

PECS giải quyết **quan hệ kiểu compile-time**; các điều kiện về kích thước, mutability, thứ tự và semantics của comparator thuộc hợp đồng runtime của API.

## 10. Đọc thêm: `Comparator` có thể vừa tiêu thụ vừa tạo kết quả

Một comparator **nhận** hai giá trị `T` vào `compare(T, T)` rồi **trả về** một số nguyên biểu diễn thứ tự. Nó là *consumer của T* dù vẫn có output kiểu `int`.

Khi sử dụng method reference hoặc lambda, kiểu lambda thường được suy ra từ **target type**:

~~~java
Comparator<Number> compareNumbers = (a, b) ->
        Double.compare(a.doubleValue(), b.doubleValue());

List<Integer> integers = new ArrayList<>(List.of(5, 2, 9));
integers.sort(compareNumbers);
~~~

Các tham số `a` và `b` được compiler hiểu là `Number` theo target type `Comparator<Number>`. Khi `List<Integer>.sort` gọi comparator, mỗi `Integer` vẫn là một `Number` hợp lệ. Ta không cần tạo `Comparator<Integer>` mới.

Nếu triển khai một hàm nhận comparator:

~~~java
static <T> void sortItems(List<T> items, Comparator<? super T> ordering) {
    items.sort(ordering);
}
~~~

Đây là **phương thức minh họa cần import `java.util.*`**. `items` giữ đối số kiểu chính xác `T` để có thể sắp xếp các phần tử của nó, còn `ordering` được khai báo consumer super để chấp nhận comparator của `T` hoặc kiểu cha.

Điều này thể hiện PECS có thể dùng cho **interface nhận tham số**, không riêng collection.

## 11. Bảng bài tập: dự đoán khả năng biên dịch

Giả sử các biến khai báo bên trong một phương thức với `import java.util.*;`:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<Double> doubles = new ArrayList<>(List.of(2.5, 3.5));
List<Number> numbers = new ArrayList<>(List.of(0, 0));
List<Object> objects = new ArrayList<>();
Comparator<Number> numberComparator =
        (a, b) -> Double.compare(a.doubleValue(), b.doubleValue());
Comparator<Integer> integerComparator = Integer::compare;
~~~

Hãy phân tích từng biểu thức **độc lập**, không nối các biểu thức thành một chương trình rồi suy luận trạng thái runtime về sau:

| Biểu thức | Biên dịch? | Lý do |
| --- | --- | --- |
| `Collections.copy(numbers, integers);` | Có | Nguồn `Integer`, đích `Number`; PECS phù hợp |
| `Collections.copy(objects, integers);` | Có | Đích `Object` cũng nhận `Integer` |
| `Collections.copy(integers, numbers);` | Không | Nguồn `Number` không chắc là `Integer` |
| `numbers.addAll(integers);` | Có | Receiver có `E = Number`, nguồn `? extends Number` |
| `integers.addAll(numbers);` | Không | Receiver có `E = Integer`, nguồn không chắc là `Integer` |
| `Collections.addAll(numbers, 3, 4.5);` | Có | Có kiểu `T` tương thích với `Number` và các giá trị |
| `Collections.<Number>addAll(objects, 3, 4.5);` | Có | `Object` là supertype của `Number` |
| `Collections.<Number>addAll(integers, 3);` | Không | `Integer` không phải supertype của `Number` |
| `integers.sort(numberComparator);` | Có | `Comparator<Number>` tiêu thụ được `Integer` |
| `numbers.sort(integerComparator);` | Không | Comparator quá hẹp cho mọi `Number` |
| `Collections.sort(integers, numberComparator);` | Có | `Comparator<? super Integer>` nhận `Comparator<Number>` |
| `Collections.copy(numbers, doubles);` | Có | `Double` là subtype của `Number` |

Lưu ý riêng: với `Collections.copy(objects, integers)`, lời gọi **biên dịch**, nhưng `objects` ban đầu rỗng nên sẽ ném `IndexOutOfBoundsException` nếu chạy trong trạng thái đã khai báo. Đây không phải lỗi generic.

### Tự đặt câu hỏi trước khi xem compiler

1. `Collection.addAll` nhận một collection nguồn hay những phần tử varargs?
2. Vì sao `Collections.copy` dùng `super` cho đích nhưng `extends` cho nguồn?
3. Vì sao `Comparator<Number>` sắp xếp được `List<Integer>`, trong khi `Comparator<Integer>` không sắp xếp được `List<Number>`?
4. Khi nào `Collections.copy` biên dịch đúng nhưng vẫn thất bại lúc chạy?
5. Tại sao một comparator không lưu dữ liệu vẫn được xem là consumer theo PECS?

**Đáp án cốt lõi:** (1) `Collection.addAll` nhận một `Collection<? extends E>`; (2) nguồn đưa `T` ra, đích nhận `T`; (3) comparator kiểu cha nhận được subtype, còn comparator kiểu con không nhận mọi kiểu cha; (4) đích thiếu vị trí hoặc không cho sửa; (5) phương thức `compare` có các tham số đầu vào kiểu `T`.

## 12. Checklist ngắn khi gặp một chữ ký generic lạ

Đừng chỉ nhìn dấu `extends` hoặc `super`. Hãy làm rõ:

1. **Type parameter được khai báo ở đâu?** Trong class `Collection<E>`, hay ở đầu phương thức `static <T>`?
2. **Tham số dùng giá trị kiểu đó theo chiều nào?** Đọc giá trị ra từ source hay đưa giá trị vào consumer?
3. **Cận wildcard có phù hợp luồng dữ liệu không?** Producer `? extends T`, consumer `? super T`.
4. **Có điều kiện runtime nào ngoài kiểu dữ liệu?** `copy` cần kích thước đích, `addAll` cần collection cho phép thêm, `sort` cần comparator có hợp đồng nhất quán.
5. **API là instance hay static?** `dest.addAll(src)` khác hẳn `Collections.addAll(dest, item...)` dù trùng tên phương thức.

Ba nhóm chữ ký cho thấy PECS không phải khẩu hiệu áp dụng máy móc, mà là phương pháp **đọc trách nhiệm dữ liệu từ type signature**. `Collections.copy` minh họa rõ hai phía producer/consumer; `Collection.addAll` thể hiện nguồn `extends` bên cạnh receiver đã có kiểu `E`; `Collections.addAll` đặt đích `super` để nhận varargs; `Comparator<? super T>` cho thấy consumer còn có thể là một đối tượng nhận hai giá trị để so sánh. Đọc đúng các quan hệ này giúp viết API linh hoạt mà vẫn được compiler kiểm tra chặt chẽ.