# Giới hạn và cách khoanh vùng phép ép kiểu khi lưu trữ bằng `Object[]` trong Java Generics

Khi tự cài đặt một cấu trúc dữ liệu generic như `Stack<T>`, `Buffer<T>` hoặc `Store<T>`, ta thường cần bộ lưu trữ dạng mảng. Nhưng Java **không cho phép viết `new T[n]`** vì type variable `T` không phải kiểu có thể xác minh đầy đủ lúc chạy (*non-reifiable type*). Một hướng thực tế là giữ **`Object[]` làm chi tiết triển khai nội bộ**, chỉ nhận giá trị kiểu `T` từ API được compiler kiểm tra và thực hiện phép ép kiểu có kiểm soát tại điểm đọc:

```java
// Snippet nằm trong một lớp generic, không phải chương trình độc lập.
class SmallStore<T> {
    private final Object[] elements = new Object[10];

    void set(int index, T value) {
        elements[index] = value;
    }

    T get(int index) {
        @SuppressWarnings("unchecked")
        T value = (T) elements[index];
        return value;
    }
}
```

Đoạn trên minh họa ý tưởng, **chưa có kiểm tra chỉ số hay trạng thái phần tử**; chương trình đầy đủ có các kiểm tra này ở mục 6. Điều kiện cốt lõi là: **mọi giá trị được lưu vào mảng phải đi qua những đường ghi bảo đảm hợp đồng kiểu `T`**.

Một unchecked cast đặt gọn ở `get` có thể được biện minh bằng invariant của lớp. Tuy nhiên, annotation `@SuppressWarnings("unchecked")` **không tự tạo ra tính an toàn**: nếu dữ liệu đi qua raw type, reflection, unchecked alias hoặc một API công khai làm lộ mảng, invariant có thể bị phá.

> Nguyên tắc thiết kế: giữ `Object[]` ở trạng thái `private`, không trả nó dưới danh nghĩa `T[]`; khoanh vùng phép ép kiểu nhỏ nhất; kiểm soát toàn bộ đường ghi; khi API phải trả mảng thật, để caller cung cấp kiểu thành phần hoặc array factory.

## 1. Vì sao chọn `Object[]` thay vì `T[]`?

Với kiểu generic thông thường, compiler xóa type variable không có bound thành `Object`; nếu `T extends Number`, erasure là `Number`. Nhưng ở mã nguồn, `T` có thể lần lượt đại diện cho `String`, `Integer` hay nhiều kiểu tham chiếu khác.

```java
class GenericBox<T> {
    T[] values; // Được khai báo tham chiếu T[]

    void allocate(int n) {
        // values = new T[n]; // LỖI: generic array creation
    }
}
```

Mảng Java cần có **runtime component type** thực sự. Ví dụ, `new String[3]` tạo mảng runtime `String[]`; một cố gắng gán `Integer` vào mảng này qua tham chiếu `Object[]` sẽ bị JVM chặn.

Trong khi đó, `new Object[3]` có runtime type chính xác là `Object[]`. Nó có thể giữ nhiều loại **tham chiếu** đến đối tượng (bao gồm wrapper như `Integer`), nhưng chính mảng không tự chứng minh được mọi giá trị là `T`.

```java
Object[] values = new Object[3];
values[0] = "An";
values[1] = 42;
values[2] = null;
```

Các phép ghi trên hợp lệ đối với `Object[]`. Vì thế, dùng `Object[]` làm storage cần **invariant ở cấp cấu trúc dữ liệu**, thay vì trông chờ JVM tự kiểm tra `T` khi ghi.

## 2. Một invariant an toàn cần phát biểu chính xác thế nào?

Giả sử đang cài đặt `Store<T>` và chỉ cung cấp:

```java
void add(T value);
void set(int index, T value);
T get(int index);
```

Ta cần duy trì các điều kiện:

1. **Mảng nội bộ không thoát ra ngoài**: trường `Object[] elements` là `private` và không bị trả ra như một tham chiếu cho caller tự sửa.
2. **Mọi đường ghi đều đi qua API typed**: `add(T)` và `set(..., T)` nhận giá trị được kiểm tra theo `T` ở các lời gọi generic hợp lệ.
3. **Chỉ số hợp lệ**: giá trị trong vùng `0 <= index < size` là những giá trị đã được thêm/set theo hợp đồng; vùng capacity chưa dùng không bị xem như phần tử logic.
4. **Không lạm dụng raw/unchecked**: nếu client cast sang raw `Store` rồi gọi `add(42)` trên một `Store<String>`, điều kiện (2) đã bị phá; compiler có thể cảnh báo nhưng không cấm hoàn toàn mã cố ý không an toàn.
5. **Không có lối ghi khác**: native code, reflection đặc quyền, truy cập nội bộ không được kiểm soát hoặc thao tác không an toàn có thể phá giả định; invariant thuộc phạm vi API và thực thi thông thường mà thiết kế kiểm soát.
6. **Không bỏ qua concurrency**: nếu cấu trúc được chia sẻ giữa threads, phải cung cấp chính sách đồng bộ phù hợp. Invariant kiểu không tự bảo đảm visibility, atomicity hay thread-safety.

Nếu tất cả đường ghi bình thường đã đảm bảo `T`, thì đọc một phần tử trong vùng đã dùng và xem nó như `T` là lập luận hợp lý. Điều được chứng minh là **bất biến dữ liệu trong một thiết kế đóng**, không phải khả năng JVM xác nhận đối số generic bằng runtime cast.

### Invariant khác với kiểm tra lúc chạy

Với `Store<String>`, bytecode của `add(T)` khi `T` không bound có thể nhận tham số erasure `Object`, và `Object[]` cũng nhận `Object`. An toàn kiểu đến từ compiler kiểm tra các caller được viết bằng `Store<String>`, chứ không phải JVM phát hiện nhãn `String` trên mảng ở mọi lần `add`.

Do đó, nếu caller cố tình vượt qua hệ thống kiểu bằng raw type hoặc unchecked cast, cấu trúc có thể bị **heap pollution**. Một unchecked cast ở `get` không thể sửa dữ liệu đã sai.

## 3. Cách khoanh vùng `(T)` tại một điểm đọc

Thay vì rải các cast ở khắp nơi, nên giữ chúng ngay tại biên đọc nội bộ:

```java
T get(int index) {
    java.util.Objects.checkIndex(index, size);

    @SuppressWarnings("unchecked")
    T value = (T) elements[index];

    return value;
}
```

Ba dòng quan trọng:

- `Objects.checkIndex(index, size)` xác nhận chỉ số nằm trong vùng phần tử logic, thay vì toàn bộ capacity của mảng. Lỗi chỉ số gây `IndexOutOfBoundsException`, không liên quan generic.
- `(T) elements[index]` biểu diễn hợp đồng của cấu trúc: “phần tử đã lưu thuộc `T`”.
- Annotation được đặt ngay tại **biến local có phép cast**; không tắt cảnh báo cho cả class hay cả project.

**Cảnh báo unchecked không được giải quyết bằng annotation:** nó chỉ được **khoanh vùng** sau khi đã chứng minh các đường ghi bảo toàn invariant.

Nếu `T` không bound, erasure của `T` là `Object`; cast trong `get` có thể không kiểm tra thêm gì ở runtime. Khi caller nhận kết quả dưới kiểu cụ thể, compiler có thể chèn cast tại nơi sử dụng:

```java
Store<String> store = new Store<>(2);
store.add("Java");

String text = store.get(0); // Compiler kiểm tra lời gọi theo String
```

Nếu invariant bị phá và giá trị thật là `Integer`, lỗi `ClassCastException` có thể chỉ bộc lộ **ở caller** khi kết quả phải được xem là `String`. Vì vậy đừng khẳng định “đã cast trong `get` thì mọi sai kiểu sẽ bị phát hiện ngay trong `get`”.

Nếu `T extends Number`, cast khi dùng type variable có thể kiểm tra erasure `Number`, nhưng nó vẫn không bảo đảm kiểu chính xác `Integer` khi caller gắn `T = Integer`.

## 4. Những đường phá invariant phổ biến

### 4.1. Đưa raw type vào API

```java
// Snippet minh họa cố tình không an toàn.
Store<String> strings = new Store<>(1);
Store raw = strings;
raw.add(42); // Unchecked warning: bypass kiểm tra String của caller

// String bad = strings.get(0); // Có thể ném ClassCastException
```

Raw `Store` không còn ràng buộc `T = String` ở lần gọi `add`. Vì bytecode có thể nhận `Object`, số nguyên sau boxing có thể đi vào bộ lưu trữ `Object[]`.

Dù `Object[]` là trường private, compiler không thể ngăn mọi client cố ý bỏ qua hệ thống kiểu ở **API công khai**. Thiết kế bảo đảm an toàn đối với các lần sử dụng generic đúng kiểu, không hứa an toàn tuyệt đối trước mã tùy tiện cố tạo unchecked operations.

### 4.2. Trả thẳng mảng nội bộ

```java
// ĐỪNG làm thế nếu API cần giữ invariant:
Object[] exposed() {
    return elements; // Caller có thể sửa phần tử tùy ý
}
```

Ngay cả caller dùng `Store<String>` vẫn có thể làm:

```java
Object[] data = store.exposed();
data[0] = 123; // Không cần raw Store; invariant đã bị phá
```

Chỉ `private Object[]` **không đủ**, nếu class lại công khai một getter trả về chính mảng đó. Muốn trả snapshot dạng `Object[]` cho một API đặc thù, ít nhất phải sao chép và xác định hợp đồng rõ ràng; trong đa số API generic, nên trả một `List<T>`, phần tử `T`, hoặc mảng đúng component type qua factory.

### 4.3. Cho phép đường ghi khác không kiểm tra kiểu

Nếu có method nhận `Object` rồi ghi thẳng vào storage:

```java
// Ví dụ sai trong một Store<T>:
void addAnything(Object value) {
    elements[size++] = value;
}
```

Thì lời hứa “mọi phần tử thuộc `T`” không còn đúng. Khi lớp thực sự cần nhận dữ liệu dạng `Object` từ bên ngoài, phải kiểm tra bằng một `Class<T>` token (nếu phù hợp), validator hoặc chuyển đổi được chứng minh trước khi lưu.

### 4.4. Nhầm lỗi kiểu với lỗi quản lý mảng

Một cấu trúc dùng `Object[]` còn phải quản lý `size`, `capacity`, giới hạn chỉ số và chính sách `null`. Việc cast đúng không cứu được lỗi `ArrayIndexOutOfBoundsException`, truy cập phần tử chưa khởi tạo hoặc mất dữ liệu do resize không sao chép đủ.

Mảng Java chứa các giá trị `null` mặc định ở vùng chưa dùng. Do đó cần phân biệt **`size`** (số phần tử logic) với **`elements.length`** (dung lượng cấp phát).

## 5. Vì sao không được công khai `(T[]) elements`?

Giả sử `elements` được tạo bằng `new Object[10]`:

```java
// Cảnh báo: đây là API thiết kế sai nếu hứa trả runtime T[].
@SuppressWarnings("unchecked")
T[] unsafeArray() {
    return (T[]) elements;
}
```

Khi `T` không bound, phép cast có thể đi qua erasure là `Object[]`; nhưng object thực tế **vẫn là `Object[]`**. Nếu caller yêu cầu:

```java
Store<String> store = new Store<>(2);
// String[] strings = store.unsafeArray(); // Có thể ClassCastException
```

Thì caller trông chờ `String[]`, trong khi runtime array class không tương thích. Annotation `@SuppressWarnings` không thay đổi runtime component type.

**Khác biệt then chốt:**

- `(T) elements[i]`: có thể nằm trong một invariant kiểu được kiểm soát, vì một **giá trị phần tử** thực tế có thể là `String`.
- `(T[]) elements`: không hợp lệ làm lời hứa chung về runtime array class, vì bản thân đối tượng mảng `Object[]` không phải một `String[]`.

Đặt một cast unchecked nhỏ quanh **từng giá trị đã được bảo vệ** khác bản chất với việc gắn nhãn cho **toàn bộ object mảng** không có runtime component type tương ứng.

Một ngoại lệ về thiết kế: nếu bộ lưu trữ thực sự được khởi tạo qua `Array.newInstance(String.class, n)`, mảng runtime có thể là `String[]` đúng. Nhưng đó không còn là tình huống *backing array `Object[]` được tạo bằng `new Object[]`* đang phân tích.

## 6. Chương trình Java 17+ hoàn chỉnh với phép cast được khoanh vùng

Lưu toàn bộ nội dung sau vào **`ObjectArrayStoreDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.function.IntFunction;

public class ObjectArrayStoreDemo {
    static final class Store<T> {
        private Object[] elements;
        private int size;

        Store(int capacity) {
            if (capacity < 0) {
                throw new IllegalArgumentException("capacity");
            }
            elements = new Object[capacity];
        }

        void add(T value) {
            if (size == elements.length) {
                elements = Arrays.copyOf(
                        elements,
                        Math.max(1, elements.length * 2));
            }
            elements[size++] = value;
        }

        T get(int index) {
            Objects.checkIndex(index, size);

            @SuppressWarnings("unchecked")
            T result = (T) elements[index];

            return result;
        }

        void set(int index, T value) {
            Objects.checkIndex(index, size);
            elements[index] = value;
        }

        T[] toArray(IntFunction<T[]> factory) {
            T[] result = factory.apply(size);
            if (result.length != size) {
                throw new IllegalArgumentException("Array length mismatch");
            }
            System.arraycopy(elements, 0, result, 0, size);
            return result;
        }
    }

    public static void main(String[] args) {
        Store<String> names = new Store<>(1);
        names.add("An");
        names.add("Binh");
        names.set(1, "Lan");

        System.out.println("Stored: "
                + names.get(0) + ", " + names.get(1));

        String[] copy = names.toArray(String[]::new);
        System.out.println("Typed copy: " + Arrays.toString(copy));
        System.out.println("Array runtime type: "
                + copy.getClass().getTypeName());

        Object[] genericArray = new Object[] { "A", "B" };
        try {
            String[] impossible = (String[]) genericArray;
            System.out.println(impossible.length);
        } catch (ClassCastException exception) {
            System.out.println("Object[] cast: ClassCastException");
        }

        Object[] view = copy;
        try {
            view[0] = 42;
        } catch (ArrayStoreException exception) {
            System.out.println("Array write: ArrayStoreException");
        }

        // Đoạn cuối cố ý phá invariant bằng raw type.
        Store<String> polluted = new Store<>(1);
        Store raw = polluted;
        raw.add(42);

        try {
            String item = polluted.get(0);
            System.out.println(item);
        } catch (ClassCastException exception) {
            System.out.println("Raw alias: ClassCastException");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 -Xlint:rawtypes -Xlint:unchecked ObjectArrayStoreDemo.java
java ObjectArrayStoreDemo
```

**Standard output** (không bao gồm compiler warnings):

```text
Stored: An, Lan
Typed copy: [An, Lan]
Array runtime type: java.lang.String[]
Object[] cast: ClassCastException
Array write: ArrayStoreException
Raw alias: ClassCastException
```

Lưu ý kiểm chứng:

1. `Store<String>` nhận `"An"`, `"Binh"`, rồi cập nhật vị trí 1 thành `"Lan"`. Không có raw alias nào được dùng để sửa `names`, vì thế việc đọc theo `String` đúng với invariant.
2. Khi capacity ban đầu là 1 và gọi `add` lần thứ hai, `Arrays.copyOf` tăng kích thước mảng `Object[]`; **runtime component class của storage vẫn là `Object`**, điều này không làm lỗi vì storage được bao kín.
3. `toArray(String[]::new)` tạo `String[]` thật rồi dùng `System.arraycopy` chép các phần tử. Caller có mảng typed riêng và không sở hữu storage nội bộ.
4. Ép một mảng thực `Object[]` sang `String[]` thất bại bằng `ClassCastException`, dù toàn bộ phần tử hiện có trong nó đều là các chuỗi. **Kiểu runtime của mảng** mới là điều kiện quyết định cast này.
5. `String[]` có thể tham chiếu qua `Object[]`, nhưng ghi `Integer` vào nó bị từ chối bởi `ArrayStoreException`. Đây là cơ chế kiểm tra component type ở runtime.
6. Raw alias của `Store<String>` cho phép một lời gọi `add(42)` **có cảnh báo unchecked**. Sau đó, khi caller lấy phần tử để dùng như `String`, sẽ có `ClassCastException`. Bài thử cuối là ví dụ **cố ý làm sai**, không phải cách dùng đề xuất.

Phần `@SuppressWarnings("unchecked")` chỉ nằm ở local variable trong `get`; warning của raw alias cuối chương trình được giữ lại để bạn quan sát tại thời điểm biên dịch.

### Về tính an toàn của `toArray` trong ví dụ

Chữ ký `T[] toArray(IntFunction<T[]> factory)` yêu cầu caller cung cấp một factory phù hợp với `T`, ví dụ `String[]::new` cho `Store<String>`. Compiler kiểm tra kiểu của factory nếu caller không dùng raw/unchecked tricks.

Phương thức không trả mảng `Object[] elements`. Nó gọi factory để nhận một mảng thực có component type đã chọn, kiểm tra độ dài rồi sao chép giá trị sang đó. Nếu factory thực sự tạo mảng sai kiểu thông qua đường truy cập không an toàn, `System.arraycopy` có thể phát hiện phần tử không tương thích bằng kiểm tra runtime; nó **không** làm cho một factory không đáng tin trở nên đúng kiểu.

Trong code sản xuất, còn nên kiểm tra factory không trả `null` và xây dựng API size/capacity theo hợp đồng. Ví dụ giữ ngắn để tập trung vào câu hỏi về unchecked cast.

## 7. Ranh giới hợp lý của `@SuppressWarnings("unchecked")`

Có ba phạm vi thường thấy:

```java
// Phạm vi quá rộng: dễ che các unchecked lỗi ở nhiều chỗ.
@SuppressWarnings("unchecked")
class WholeClass<T> {
    // ...
}
```

```java
// Phạm vi hẹp hơn: chỉ một method, nhưng có thể che nhiều cast trong method.
@SuppressWarnings("unchecked")
T get(int index) {
    return (T) elements[index];
}
```

```java
// Phạm vi thường đáng ưu tiên trong ví dụ Object[]:
T get(int index) {
    Objects.checkIndex(index, size);
    @SuppressWarnings("unchecked")
    T value = (T) elements[index];
    return value;
}
```

Mục tiêu không phải “càng ít warning càng tốt” mà là **cho những cảnh báo khác vẫn xuất hiện**. Khi người bảo trì thêm một cast mới ở nơi khác, compiler cần tiếp tục báo để họ đánh giá tính an toàn của nó.

Một chú thích thiết kế hữu ích (ở mã thư viện thực tế) thường giải thích:

- Vì sao mảng chỉ chứa các giá trị được thêm qua API `T`.
- Vì sao không có đường cho caller sửa `Object[]` trực tiếp.
- Vì sao chỉ đọc các phần tử có chỉ số đã khởi tạo hợp lệ.
- Vì sao phép cast không được thực hiện ở những vị trí khác.

Nếu không đưa ra được lập luận cụ thể, không nên dùng `@SuppressWarnings` chỉ để “làm compiler im lặng”.

## 8. Hãy ưu tiên API chứa/đọc dữ liệu typed thay vì rải cast cho caller

Một API tốt làm cho caller chỉ phải làm việc với `T`:

```java
// Dạng chữ ký mong muốn:
void add(T item);
T get(int index);
void set(int index, T item);
int size();
```

Một API kém buộc client đọc `Object` rồi tự cast khắp nơi:

```java
// Thiết kế kém cho một cấu trúc tự nhận là generic:
Object getRaw(int index);
Object[] exposeStorage();
```

Khi `Store<T>` chịu trách nhiệm duy trì invariant và che storage, unchecked cast có thể được giới hạn ở **một biên đọc** bên trong class. Caller được compiler kiểm tra khi dùng `Store<String>` mà không phải thêm cast `(String)` thủ công.

Ngược lại, nếu công khai `Object[]`, mọi caller có thể phá invariant mà không cần dùng raw type. Việc phân tán cast cho caller khiến trách nhiệm an toàn bị chia nhỏ và khó kiểm toán.

### Trường hợp `T` có thể là `null`

Một `Store<T>` thông thường có thể cho phép lưu `null` vì kiểu tham chiếu generic không tự đồng nghĩa “non-null”. Phép cast `(T) null` không ném `ClassCastException`. Nếu API không chấp nhận `null`, nên thực thi quy tắc đó ngay tại `add`/`set` bằng `Objects.requireNonNull(value)` và tài liệu hóa hợp đồng.

Đừng xem `null` trong vùng capacity chưa dùng là một phần tử logic. Trường `size` tồn tại để phân biệt vùng dữ liệu đã thêm với vùng còn trống.

## 9. Khi nào dùng `Class<T>` thay vì chấp nhận unchecked cast theo invariant?

Một `Class<T>` token hữu ích khi bạn cần **kiểm tra class runtime tại ranh giới nhận dữ liệu** hoặc **tạo một mảng runtime thuộc đúng class phần tử**:

```java
// Snippet: Class<T> không mang thông tin generic lồng nhau.
static <T> T checkedValue(Object input, Class<T> type) {
    return type.cast(input);
}
```

Với `String.class`, `type.cast(input)` thật sự kiểm tra `input` có thể coi là `String`. Đây là sự khác biệt so với cast `(T)` bên trong generic method không được truyền type token: `T` không có runtime class identity riêng cho từng type argument.

Dùng token để tạo array:

```java
static <T> T[] typedArray(Class<T> elementType, int n) {
    @SuppressWarnings("unchecked")
    T[] result = (T[]) java.lang.reflect.Array.newInstance(elementType, n);
    return result;
}
```

Khi gọi `typedArray(String.class, 3)`, phản xạ tạo một mảng runtime `String[]`, không phải một `Object[]` được “ngụy trang”. Cast unchecked ở đây được biện minh bằng mối liên hệ giữa `elementType` và đối tượng array do chính method tạo.

Nhưng `Class<T>` chỉ mô tả một runtime class. Không có `List<String>.class` để bảo đảm toàn bộ phần tử của một danh sách có type argument `String`; với dữ liệu generic lồng nhau, cần validator cấu trúc hoặc API kiểu hóa đáng tin.

**Chọn giải pháp theo yêu cầu:**

- Nếu storage chỉ cần giữ `T` trong class đóng: `Object[]` + invariant + cast cục bộ có thể đủ.
- Nếu người dùng cần nhận `String[]` đúng runtime type: dùng `Class<T>`, array factory hoặc mảng mẫu.
- Nếu nguồn giá trị là `Object` không đáng tin: kiểm tra bằng `Class<T>.cast` hoặc validator thích hợp trước khi lưu.

## 10. Các lựa chọn thay thế tránh hoặc giảm cast

### 10.1. Dùng `List<T>`

```java
class ListBackedStore<T> {
    private final java.util.List<T> elements = new java.util.ArrayList<>();

    void add(T item) {
        elements.add(item);
    }

    T get(int index) {
        return elements.get(index);
    }
}
```

Đây thường là cách đơn giản nhất: sử dụng trực tiếp API generic chuẩn, không phải tự hiện thực bộ lưu trữ và invariant của `Object[]`. Việc một implementation bên dưới có thể dùng mảng không buộc code ứng dụng phải tiếp xúc với cast.

### 10.2. Nhận một array factory

```java
static <T> T[] allocate(int n, java.util.function.IntFunction<T[]> factory) {
    return factory.apply(n);
}

String[] names = allocate(3, String[]::new);
```

Phần `String[]::new` đặt việc tạo mảng ở nơi đã có component type cụ thể. Phương thức generic dùng factory, không cần viết `new T[n]`.

### 10.3. Dùng API `toArray` của collection

```java
java.util.List<String> values = java.util.List.of("An", "Binh");

String[] a = values.toArray(new String[0]);
String[] b = values.toArray(String[]::new);
Object[] c = values.toArray();
```

Hai cách đầu trả mảng `String[]` đúng runtime type vì caller cung cấp mẫu/generator. `toArray()` không tham số trả `Object[]`; đừng ép kết quả đó thành `String[]` rồi cho rằng mọi phần tử `String` sẽ làm cast thành công.

## 11. Cảnh báo về `Arrays.copyOf`, reflection và mảng trả ra ngoài

`Arrays.copyOf(Object[] original, int newLength)` trả `Object[]` với runtime component class theo overload đó và loại mảng nguồn; khi nguồn là `Object[]` thật, bản copy vẫn là `Object[]`.

```java
Object[] internal = new Object[] { "An", "Binh" };
Object[] copied = java.util.Arrays.copyOf(internal, 2);
// copied vẫn có runtime class là Object[]
```

Việc copy nội dung không tự chuyển kiểu component thành `String`. Để yêu cầu mảng đích cụ thể, dùng một API có type token/mảng mẫu/factory tương ứng.

Khi chỉ muốn snapshot tạm phục vụ duyệt dữ liệu mà không để client sửa storage gốc, bản sao `Object[]` có thể hữu ích nếu hợp đồng công khai rõ ràng rằng nó chỉ là `Object[]`. Không nên hứa trả `T[]` đúng runtime type dựa trên bản sao đó.

Khi trả `List<T>` từ storage, cần nhớ raw/unchecked alias có thể làm hỏng cả chính dữ liệu trước khi copy. Một biến `List<T>` chỉ an toàn nếu nguồn của nó giữ được invariant; với dữ liệu không đáng tin, kiểm tra phần tử ở biên nhập vẫn quan trọng.

## 12. Vấn đề đồng thời và mutation

Một class dùng `Object[]` tự tăng capacity như ví dụ có thể gặp race khi nhiều thread đồng thời gọi `add`, `set` hoặc `get`:

- `size` có thể bị cập nhật mất lượt.
- Resize có thể bị ghi đè hoặc đọc nhầm bản mảng cũ.
- Thread khác có thể không quan sát đầy đủ dữ liệu mới nếu không có quan hệ *happens-before* thích hợp.

Đây là vấn đề **concurrency**, không do unchecked cast trực tiếp gây ra. Phạm vi bài này chỉ hứa thiết kế generic đúng ở cách dùng tuần tự; để dùng đa luồng, cần đồng bộ hoặc cấu trúc dữ liệu chuyên cho concurrency.

Tương tự, một `String[]` được tạo khi `toArray(String[]::new)` là snapshot cấu trúc tại thời điểm method copy trong cách dùng tuần tự. Nó không có nghĩa mảng ấy tự cập nhật khi `Store` thay đổi sau đó.

## 13. Sai lầm phổ biến

**1. “Đã dùng `private Object[]` thì không thể sai kiểu.”** Chưa đủ. Nếu API công khai trả nguyên mảng hoặc cho phép nhận `Object` rồi ghi thẳng, invariant bị phá.

**2. “`@SuppressWarnings("unchecked")` làm cast an toàn.”** Sai. Annotation chỉ ẩn cảnh báo trong phạm vi được gắn.

**3. “Cast `(T)` luôn xác nhận class cụ thể của T tại runtime.”** Sai. Với `T` không bound, erasure là `Object`; class cụ thể có thể chỉ được kiểm tra ở caller.

**4. “Cast `(T[]) new Object[n]` sẽ tạo `String[]` khi T=String.”** Sai. Runtime class của object mảng vẫn là `Object[]`.

**5. “Vì `elements` chứa toàn String nên có thể cast cả mảng `Object[]` thành `String[]`.”** Sai. Array cast xét runtime component type của mảng, không quét phần tử để đoán class.

**6. “Khoanh vùng cast bằng cách gắn `@SuppressWarnings` trên class là tốt nhất.”** Không. Phạm vi càng lớn càng dễ che các unsafe operation mới.

**7. “Kiểm tra chỉ số theo `elements.length` là đủ.”** Không. Vùng capacity chưa sử dụng không nhất thiết là vùng phần tử logic; thường phải kiểm tra theo `size`.

**8. “Raw type không ảnh hưởng bộ lưu trữ vì mảng đang private.”** Không. Raw alias có thể truyền một giá trị sai `T` qua phương thức `add` công khai.

**9. “Có `T[]` trả về nghĩa là array thật có đúng runtime component class.”** Không, nếu implementation chỉ trả `Object[]` giả dạng bằng unchecked cast.

**10. “`List<T>` cần `new T[n]` mới hoạt động được.”** Không. Collection generic có thể dùng bộ lưu trữ nội bộ và API typed mà không tạo trực tiếp mảng `T[]` ở code ứng dụng.

## 14. Bài tập tự kiểm tra

**Câu 1.** `private Object[] elements` và `T get(int index)` có thể phối hợp trong một class generic không?

Có, nếu class kiểm soát mọi đường ghi, chỉ đọc phần tử đúng chỉ số, và phép cast tại `get` được biện minh bằng invariant.

**Câu 2.** Vì sao `(T) elements[index]` khác `(T[]) elements` về tính an toàn?

Một đối tượng phần tử thực tế có thể đúng kiểu `T` theo invariant. Nhưng một mảng runtime `Object[]` không biến thành `String[]` hay `Integer[]` nhờ cast tham chiếu.

**Câu 3.** Có nên trả chính `Object[] elements` để caller dùng trực tiếp không?

Thông thường không, nếu muốn bảo toàn invariant generic. Caller có thể sửa bất kỳ phần tử nào mà không qua `add(T)`.

**Câu 4.** Sau khi raw alias gọi `add(42)` trên một `Store<String>`, phương thức `get` có thể gặp điều gì?

Khi bên gọi cần `String`, `Integer` có thể bị cast sang `String` và gây `ClassCastException`. Phép cast trong `get` không tự sửa dữ liệu sai.

**Câu 5.** Muốn caller nhận `String[]` có runtime class đúng, nên làm gì?

Nhận `String.class`/tương ứng `Class<T>` để tạo array bằng reflection, hoặc nhận factory `String[]::new` và sao chép dữ liệu vào mảng đó.

**Câu 6.** Vì sao nên giới hạn `@SuppressWarnings("unchecked")` vào một local variable?

Để dễ kiểm toán chỗ cast đã được chứng minh an toàn và không che các unchecked warnings khác trong cùng lớp.

**Câu 7.** `Arrays.copyOf(new Object[]{"A"}, 1)` có trả `String[]` không?

Không. Nó sao chép một mảng `Object[]` thực, nên bản sao trong trường hợp này vẫn có runtime component type `Object`.

## 15. Checklist thiết kế `Object[]` backing storage

Khi xem xét một cấu trúc generic tự cài đặt, lần lượt kiểm tra:

1. **Storage được bao kín?** `private Object[]`, không có getter trả alias có thể sửa.
2. **Tất cả phương thức ghi đều typed?** Tránh đường ghi nhận `Object` thiếu kiểm tra.
3. **Vùng đọc đúng?** Chỉ số phải nhỏ hơn `size`, không phải chỉ nhỏ hơn capacity.
4. **Cast ở đâu?** Tập trung tại một điểm đọc hoặc biên chuyển đổi có invariant rõ.
5. **Suppress ở mức nào?** Chỉ đoạn nhỏ cần thiết; giải thích lý do an toàn.
6. **Có API trả array không?** Phải tạo mảng runtime đúng kiểu bằng factory/token, không làm giả từ `Object[]`.
7. **Có raw/unchecked clients không?** Nhận thức rằng caller cố ý bỏ hệ thống kiểu có thể phá invariant.
8. **Có null/concurrency không?** Tài liệu hóa và kiểm soát theo hợp đồng API.
9. **Có giải pháp đơn giản hơn không?** Nếu không bắt buộc quản lý array, dùng `ArrayList<T>` hoặc collection phù hợp.

**Kết luận:** `Object[]` là công cụ hợp lý để lưu trữ nội bộ trong một cấu trúc generic khi `new T[]` bị cấm, nhưng JVM không tự bảo đảm các phần tử của nó thuộc `T`. Tính an toàn phụ thuộc một invariant được duy trì qua các đường ghi typed và bộ lưu trữ không bị lộ. Hãy **khoanh vùng unchecked cast ở điểm đọc**, không dùng cast để giả mạo runtime `T[]`, và dùng `Class<T>` hoặc array factory khi cần một mảng public thực sự đúng kiểu.