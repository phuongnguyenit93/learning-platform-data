# Khoanh vùng cast không kiểm tra và nêu bất biến bảo đảm an toàn trong Java Generics

Khi thiết kế một API generic, đôi lúc bạn phải tích hợp mã cũ dùng **raw type**, lưu dữ liệu bằng `Object[]`, nhận một `Object` từ nguồn bên ngoài hoặc chuyển một tham chiếu chưa đủ thông tin kiểu về dạng tham số hóa. Java có thể cảnh báo **unchecked cast**: compiler không chứng minh đầy đủ được kiểu đích ở runtime, đặc biệt khi kiểu đích chứa đối số generic đã bị *type erasure*.

Phản ứng phù hợp **không phải** là gắn `@SuppressWarnings("unchecked")` lên toàn bộ class hoặc dùng một cast lớn rồi hy vọng. Thiết kế tốt phải giải quyết đồng thời hai việc:

1. **Khoanh vùng phép cast** tại một biên rõ ràng, càng nhỏ càng tốt: một biến local, một phương thức chuyển đổi nội bộ, hoặc một adapter dành riêng cho API legacy.
2. **Nêu và duy trì bất biến (*invariant*)** chứng minh cast an toàn trong phạm vi được giả định: dữ liệu đến từ đâu, ai được phép ghi, kiểu nào được phép lưu, liệu tham chiếu có rò rỉ, thời điểm nào dữ liệu được xác minh và có đường nào phá hợp đồng không.

Ví dụ:

```java
// Tóm tắt ý tưởng của một class generic:
class Buffer<T> {
    private final Object[] data = new Object[8];

    void set(int index, T value) {
        data[index] = value;
    }

    T get(int index) {
        // Bất biến cần chứng minh: phần tử tại vị trí hợp lệ đã
        // được ghi bằng T qua những đường được class kiểm soát.
        @SuppressWarnings("unchecked")
        T value = (T) data[index];
        return value;
    }
}
```

Đoạn này **chỉ minh họa vị trí cast**, chưa xử lý `size`, chỉ số hoặc phần tử chưa khởi tạo. Chương trình hoàn chỉnh trong bài sẽ xử lý các điểm đó. Nếu bạn không thể đưa ra chứng minh cho bất biến, bạn không có cơ sở để gọi cast là an toàn chỉ vì warning đã biến mất.

## 1. Hiểu đúng “unchecked” trong Java Generics

Xét một giá trị không biết nguồn gốc:

```java
Object input = java.util.List.of("An", 42);

// KHÔNG có phép kiểm tra runtime đầy đủ List<String>:
@SuppressWarnings("unchecked")
java.util.List<String> names = (java.util.List<String>) input;
```

Cast này có thể thành công vì object thật là một `List`; JVM không quét từng phần tử để xác minh đối số kiểu `String`. Khi sau đó đọc phần tử thứ hai dưới kiểu `String`, lỗi có thể xuất hiện:

```java
// String second = names.get(1); // ClassCastException
```

Đừng nhầm ba loại tình huống:

| Tình huống | JVM/compiler kiểm tra được gì? | Nhận xét |
| --- | --- | --- |
| `(String) input` | Runtime class có tương thích `String` | Checked cast thông thường |
| `(List<?>) input` | Runtime object có là `List` | Không kiểm tra kiểu từng phần tử |
| `(List<String>) input` | Không xác minh đầy đủ đối số kiểu `String` | Có thể có unchecked warning |
| `(T) item` trong method generic | Thường chỉ theo erasure/bound của `T` | Cần invariant hoặc runtime token |
| `(String[]) array` | Runtime component type của chính mảng | Khác cast tới generic `List<String>` |

**Unchecked warning không có nghĩa mọi cast đều sai.** Nó nói rằng **compiler không thể chứng minh trọn vẹn điều bạn đang khẳng định**. Có những vị trí nội bộ mà người triển khai giữ invariant đủ mạnh để biện minh cho cast; cũng có những cast trực tiếp từ dữ liệu không đáng tin mà không một lời chú thích nào làm chúng trở nên an toàn.

### Erasure giải thích vì sao compiler cần cảnh báo

Trong generics thông thường, `List<String>` và `List<Integer>` không có hai runtime class `List` chuyên biệt. `List<String>.class` không tồn tại. Vì vậy, kiểm tra runtime kiểu bên ngoài không thay thế kiểm tra type arguments bên trong.

Cũng vì vậy, một `Class<T>` có thể xác minh **một runtime class cụ thể** như `String.class`, nhưng không đủ để kiểm tra một cấu trúc lồng nhau như `Map<String,List<Integer>>` chỉ bằng `Class.cast`.

## 2. Một phép cast được biện minh bằng điều gì?

Để đánh giá một unchecked cast, nên viết một câu chứng minh cụ thể:

> Mọi phần tử được đọc tại vị trí hợp lệ của vùng lưu trữ này được ghi trước đó bằng các thao tác nhận `T`; vùng lưu trữ không bị công khai dưới dạng alias có thể sửa; không có đường ghi kiểu rộng hơn `T` không qua kiểm tra; việc đọc được thực hiện theo hợp đồng đồng bộ hóa đã công bố.

Từ câu đó, có các nghĩa vụ cần kiểm tra:

1. **Nguồn dữ liệu:** giá trị được tạo trong code typed hay lấy từ `Object`/raw/JSON/legacy API? Nếu chưa đáng tin, kiểm tra ở biên nhập.
2. **Đường ghi:** toàn bộ `add`, `set`, `replace`, deserialize, reflection wrapper có thật sự bảo toàn điều kiện kiểu không?
3. **Đường đọc:** chỉ đọc phần tử đã được khởi tạo trong vùng chỉ số hợp lệ, không nhầm `capacity` với `size`.
4. **Đóng gói:** nội bộ `Object[]` hoặc collection có bị trả ra để caller tự sửa không?
5. **Aliasing:** có raw alias, unchecked alias, iterator/container view hoặc tham chiếu tới backing collection nào có thể phá invariant không?
6. **Null policy:** generic `T` thường có thể nhận `null`; API có cho phép null không và đã thực thi nhất quán chưa?
7. **Concurrent modification:** nếu nhiều thread thao tác đồng thời, có đồng bộ để giữ atomicity/visibility cho trạng thái cần thiết không?
8. **Phạm vi cam kết:** proof giả định caller tuân thủ type system thông thường, hay API phải chống dữ liệu từ mã legacy không đáng tin?
9. **Thời điểm xác minh:** dữ liệu sau khi kiểm tra có còn có thể bị sửa qua alias khác không?
10. **Đầu ra:** return type có hứa thứ mà runtime object không có, ví dụ `String[]` nhưng object thật là `Object[]), không?

Chỉ khi biết rõ **điều kiện đầu vào**, **cơ chế giữ invariant** và **những đường có thể phá invariant**, mới có thể đánh giá một cast không kiểm tra có đáng chấp nhận hay không.

## 3. Khoanh vùng `@SuppressWarnings("unchecked")` tại nơi thật sự cần

So sánh ba phạm vi:

```java
// Không nên mặc định dùng phạm vi quá rộng:
@SuppressWarnings("unchecked")
class BroadSuppression<T> {
    // Các cast mới trong cả class cũng có thể mất cảnh báo.
}
```

```java
// Nhỏ hơn, nhưng có thể vẫn che các unchecked operations khác:
@SuppressWarnings("unchecked")
T get(int index) {
    return (T) elements[index];
}
```

```java
// Nên ưu tiên khi có invariant bảo đảm:
T get(int index) {
    java.util.Objects.checkIndex(index, size);

    @SuppressWarnings("unchecked")
    T value = (T) elements[index];

    return value;
}
```

Annotation ở biến local làm ý định hiển thị ngay cạnh cast và cho các warning phát sinh nơi khác **tiếp tục được compiler báo**.

**Nguyên tắc review:** mỗi lần dùng `@SuppressWarnings("unchecked")` nên có một **lý do có thể kiểm tra**, không chỉ “compiler cứ cảnh báo”. Nếu có thể thay cast bằng generic API chuẩn, wildcard `?` hoặc `Class<T>.cast` mà không làm sai contract, thường nên loại bỏ cast ngay từ đầu.

### `rawtypes` khác `unchecked`

```java
java.util.List raw = new java.util.ArrayList(); // raw type
raw.add("An");                                  // unchecked call
```

Khi bật `-Xlint:rawtypes -Xlint:unchecked`, bạn có thể thấy cảnh báo thuộc hai loại khác nhau:

- **`rawtypes`**: đang dùng raw `List` thay vì parameterized type khi có thể.
- **`unchecked`**: lời gọi hoặc phép chuyển không được compiler xác minh đầy đủ.

Không nên gắn suppression `unchecked` trên cả class để che các raw-type warnings; nên **sửa thiết kế nhập/xuất của API trước**, rồi khoanh vùng thật hẹp chỗ không thể tránh.

## 4. Bất biến điển hình cho `Object[]` làm backing storage

Trong một cấu trúc dữ liệu generic, Java cấm `new T[n]` vì `T` là non-reifiable. Nhưng `Object[]` nội bộ được phép:

```java
class SimpleStore<T> {
    private Object[] slots = new Object[4];
    private int size;

    void add(T value) {
        slots[size++] = value;
    }

    T get(int index) {
        @SuppressWarnings("unchecked")
        T item = (T) slots[index];
        return item;
    }
}
```

Đoạn trên **chưa đầy đủ**: có thể bị tràn mảng hoặc đọc vị trí chưa dùng. Muốn giải thích cast an toàn, invariant phải gồm cả ràng buộc cấu trúc:

- `0 <= size <= slots.length`.
- Các vị trí `slots[0]` đến `slots[size-1]` là phần tử logic đã được ghi qua API type-safe của `Store<T>`.
- `slots` không bị trả ra ngoài; không có method nhận `Object` rồi ghi không kiểm tra.
- `get(i)` chỉ chấp nhận `0 <= i < size`.
- Thao tác resize giữ nguyên dữ liệu, kiểu và thứ tự các vị trí logic.
- Nếu `null` bị cấm, mọi thao tác ghi phải kiểm tra; nếu `null` hợp lệ, method đọc phải giải thích cách phân biệt phần tử null với vị trí chưa dùng.
- Code sử dụng không cố ý phá generic contract bằng raw/unchecked operations.

Có thể kiểm soát các điều kiện này bằng việc **giữ storage private**, chỉ công khai phương thức typed, kiểm tra chỉ số và không để alias có quyền sửa lộ ra ngoài.

### Tại sao cast ở `get` hợp lý hơn cast cả array?

Khi invariant đúng, một **phần tử** trong array thực tế là object phù hợp với `T`. Nhưng object array được tạo bởi `new Object[n]` có runtime class **`Object[]`**, không biến thành `String[]` khi `T = String`.

```java
// Trong một lớp generic lưu private Object[]:
@SuppressWarnings("unchecked")
T[] wrong() {
    return (T[]) slots; // Không phải lời hứa runtime T[] an toàn
}
```

Nếu caller cần `String[]` mà `slots` là `Object[]`, runtime có thể ném `ClassCastException` tại điểm nhận giá trị. Cast từng phần tử và trả một **`T`** dựa trên invariant khác hoàn toàn với việc gắn một **runtime component class không có thật** cho mảng.

## 5. Giới hạn của bất biến typed API: raw alias vẫn có thể phá

Một `Buffer<String>` có phương thức `add(T)` được compiler kiểm tra khi caller dùng parameterized type:

```java
Buffer<String> strings = new Buffer<>();
strings.add("Java");
// strings.add(42); // Không biên dịch
```

Nhưng nếu caller cố ý sử dụng raw type:

```java
Buffer raw = strings;
raw.add(42); // Unchecked call warning
```

Thao tác này có thể đưa `Integer` vào bộ lưu trữ `Object[]` của `Buffer<String>`. Khi caller đọc thành `String`, compiler có thể chèn cast và gây `ClassCastException`.

Điều phải ghi trong lập luận an toàn là: **bất biến được bảo vệ cho những lần sử dụng typed bình thường**. Nó không bảo đảm chống mọi mã cố ý phá hệ thống kiểu bằng raw/unchecked alias, reflection tùy quyền hoặc unsafe native operations.

Nếu thư viện phải dùng trong môi trường có dữ liệu từ plugin/mã legacy không đáng tin, có thể cần **runtime validation khi nhập** bằng `Class<T>` token, validator hoặc định dạng/schema cụ thể, thay vì chỉ dựa vào generic `T` ở compile time.

Đừng viết “private field nên hoàn toàn không thể bị heap pollution” khi `add(T)` vẫn có thể bị gọi qua raw alias: private chỉ bảo vệ **truy cập trực tiếp vào field**, không chặn mọi đường gọi vào API bị làm mất tham số kiểu.

## 6. Biên dữ liệu chưa tin cậy: kiểm tra, không chỉ cast

Giả sử API nhận `Object input` từ reflection hoặc một hệ thống cũ. Cách làm sai:

```java
@SuppressWarnings("unchecked")
static <T> java.util.List<T> assume(Object input) {
    return (java.util.List<T>) input;
}
```

Phương thức này thực chất hứa trả `List<T>` dù không kiểm tra **bất kỳ phần tử nào**. Ngay cả khi object bên ngoài là `List`, một phần tử sai có thể gây lỗi ở caller sau đó. Nó cũng chưa phân biệt đúng lỗi nếu `input` không phải list.

Cách nên dùng khi cần một list có phần tử thuộc class runtime cụ thể:

```java
static <T> java.util.List<T> checkedCopy(
        Object input, Class<T> elementType) {
    java.util.Objects.requireNonNull(elementType, "elementType");

    if (!(input instanceof java.util.List<?> source)) {
        throw new IllegalArgumentException("not a List");
    }

    java.util.List<T> result =
            new java.util.ArrayList<>(source.size());

    for (Object item : source) {
        result.add(elementType.cast(
                java.util.Objects.requireNonNull(item, "element")));
    }

    return java.util.List.copyOf(result);
}
```

Từng bước đều có ý nghĩa:

1. **Kiểm tra cấu trúc ngoài**: `instanceof List<?>` xác nhận object là một `List`, không xác nhận kiểu phần tử.
2. **Yêu cầu token**: `Class<T> elementType` cho biết runtime class cần chấp nhận, ví dụ `String.class`.
3. **Kiểm tra mỗi phần tử**: `elementType.cast(item)` kiểm tra object tương thích với runtime class mong muốn. Giá trị sai bị báo ngay tại biên.
4. **Quy định null policy**: `requireNonNull(item)` khiến dữ liệu `null` bị từ chối rõ ràng, không trông chờ lỗi ở `List.copyOf` cuối phương thức.
5. **Sao chép**: trả một list mới không thể sửa cấu trúc để không tiếp tục phụ thuộc vào cấu trúc mutable của nguồn sau lần xác thực.
6. **Không có unchecked cast**: type safety đến từ thao tác `Class<T>.cast` trả về `T` cho từng item đã được kiểm tra.

Đây là một lựa chọn **hợp đồng API**, không bắt buộc với mọi nguồn. Nếu cho phép `null`, hãy chọn chính sách và cách xây kết quả khác, vì `List.copyOf` không chấp nhận null.

### `Class<T>` không đủ cho generics lồng nhau

`String.class` cho phép kiểm tra một phần tử kiểu `String`; nhưng không có `List<String>.class`. Vì vậy, nếu cần kiểm tra `List<List<String>>` hoặc `Map<String, List<Integer>>`, phải dùng validator/schema biết duyệt từng tầng; một `Class<List>` kiểu raw chỉ kiểm tra cấu trúc ngoài.

**Không giả vờ rằng `Type` hay `ParameterizedType` tự kiểm tra dữ liệu.** Reflection metadata mô tả khai báo/type schema; thư viện muốn xác minh dữ liệu phải thực thi validation phù hợp với schema đó.

## 7. Giữ hợp đồng an toàn khi dùng `List.copyOf` hoặc immutable snapshot

Nếu vừa nhận một `List<?> source` có thể được sửa qua alias khác, thao tác “validate toàn bộ rồi cast tham chiếu gốc thành `List<T>`” vẫn có rủi ro:

```java
// KHÔNG NÊN làm để công khai dữ liệu không đáng tin:
boolean allStrings = source.stream().allMatch(String.class::isInstance);

// Ngay sau đó source có thể bị sửa qua alias khác.
// @SuppressWarnings("unchecked")
// List<String> result = (List<String>) source;
```

Dù ở một thời điểm tất cả phần tử đều là `String`, **sự thật này không tự chuyển `List<?>` thành `List<String>` ở compile time**. Hơn nữa, nếu list mutable vẫn được chia sẻ, invariant đã kiểm tra có thể trở nên sai sau đó.

Sao chép từng phần tử **sau khi kiểm tra** sang container mới có kiểu `T` là một hướng tốt hơn. `List.copyOf` trong `checkedCopy` giúp tách cấu trúc kết quả khỏi nguồn, nhưng lưu ý:

- `List.copyOf` cho list không thể sửa cấu trúc, **không deep-copy các object phần tử mutable**.
- Nếu list nguồn bị sửa **trong lúc duyệt**, có thể xảy ra lỗi, đọc không nhất quán hoặc behavior khác tùy implementation. Không tuyên bố rằng riêng việc dùng `List.copyOf` tạo ra snapshot atomic trước mọi concurrent modification.
- Nếu muốn hỗ trợ dữ liệu đến từ nhiều thread, cần quy định concurrency policy và lấy snapshot nhất quán theo cơ chế đồng bộ phù hợp.

Một API an toàn cần nêu rõ **thời điểm kiểm tra**, **đối tượng sở hữu kết quả** và **những ràng buộc của dữ liệu trong tương lai**.

## 8. Wrapper `Collections.checkedList` hữu ích ở đâu?

Java cung cấp những wrapper kiểm tra runtime class của phần tử lúc có thao tác ghi qua wrapper:

```java
java.util.List<String> backing = new java.util.ArrayList<>();
java.util.List<String> checked =
        java.util.Collections.checkedList(backing, String.class);

checked.add("ok");

java.util.List raw = checked;
// raw.add(42); // Có unchecked warning; wrapper ném ClassCastException
```

Ưu điểm: nếu mã cũ gọi `add` qua **chính checked wrapper**, một phần tử runtime không tương thích với `String` sẽ bị chặn gần biên ghi.

Nhưng invariant cần nêu rõ:

- Wrapper **không sửa chữa** nội dung sai kiểu đã có trong backing list từ trước khi bọc.
- Một **alias khác** còn trỏ trực tiếp tới `backing` có thể bỏ qua wrapper và gây heap pollution.
- Wrapper cũng không tự biến generics của Java thành reified generics; `String.class` chỉ kiểm tra một runtime class cụ thể.
- Wrapper không mặc định làm backing list thread-safe hoặc immutable.

Do đó, `checkedList` là một **runtime guard tại các thao tác mà nó kiểm soát**, không thay cho việc kiểm soát quyền sở hữu backing collection hoặc xác thực nguồn dữ liệu không đáng tin.

## 9. Array factory: khi cast phần tử khác cast cả mảng

Nếu cần trả mảng typed thật cho caller, đừng viết:

```java
// Sai mục tiêu runtime nếu slots thực tế là new Object[n]:
@SuppressWarnings("unchecked")
T[] expose() {
    return (T[]) slots;
}
```

Thay vào đó, yêu cầu caller cung cấp một array factory:

```java
T[] toArray(java.util.function.IntFunction<T[]> factory) {
    java.util.Objects.requireNonNull(factory, "factory");

    T[] output = java.util.Objects.requireNonNull(
            factory.apply(size), "array");

    if (output.length != size) {
        throw new IllegalArgumentException("length");
    }

    System.arraycopy(slots, 0, output, 0, size);
    return output;
}
```

Khi `T = String`, caller dùng:

```java
String[] names = buffer.toArray(String[]::new);
```

Kết quả là `String[]` **thật**, vì `String[]::new` tạo mảng có runtime component type `String`. `System.arraycopy` sẽ áp dụng array store checks với mảng đích; nó không đổi runtime type của backing `Object[]`.

Tuy nhiên, array factory cũng có một **hợp đồng**: nó phải cấp phát mảng phù hợp `T[]` với kích thước được yêu cầu. Trong code trên, `null` và sai độ dài bị từ chối. Nếu caller dùng raw/unchecked để đưa factory tạo mảng sai kiểu, runtime có thể phát hiện mismatch; không nên tuyên bố method chống được mọi factory không đáng tin.

## 10. Chương trình Java 17+ hoàn chỉnh: an toàn, biên kiểm tra và phản ví dụ

Lưu thành **`UncheckedBoundaryDemo.java`**:

```java
import java.util.*;
import java.util.function.IntFunction;

public class UncheckedBoundaryDemo {
    static final class Buffer<T> {
        private Object[] slots = new Object[2];
        private int size;

        void add(T value) {
            if (size == slots.length) {
                slots = Arrays.copyOf(slots, slots.length * 2);
            }
            slots[size++] = value;
        }

        T get(int index) {
            Objects.checkIndex(index, size);

            // Invariant: slots[0..size) are written via add(T)
            // under parameterized use; storage does not escape.
            @SuppressWarnings("unchecked")
            T value = (T) slots[index];

            return value;
        }

        T[] toArray(IntFunction<T[]> arrayFactory) {
            Objects.requireNonNull(arrayFactory, "arrayFactory");

            T[] result = Objects.requireNonNull(
                    arrayFactory.apply(size), "array");

            if (result.length != size) {
                throw new IllegalArgumentException("length");
            }

            System.arraycopy(slots, 0, result, 0, size);
            return result;
        }
    }

    static <T> List<T> checkedCopy(
            Object candidate, Class<T> elementType) {
        Objects.requireNonNull(elementType, "elementType");

        if (!(candidate instanceof List<?> source)) {
            throw new IllegalArgumentException("not a List");
        }

        List<T> result = new ArrayList<>(source.size());

        for (Object value : source) {
            result.add(elementType.cast(
                    Objects.requireNonNull(value, "element")));
        }

        return List.copyOf(result);
    }

    // Cố ý sai: cast này không bảo đảm phần tử thuộc T.
    static <T> List<T> assumedList(Object candidate) {
        if (!(candidate instanceof List<?>)) {
            throw new IllegalArgumentException("not a List");
        }

        @SuppressWarnings("unchecked")
        List<T> result = (List<T>) candidate;

        return result;
    }

    public static void main(String[] args) {
        Buffer<String> buffer = new Buffer<>();
        buffer.add("An");
        buffer.add("Binh");

        System.out.println("Buffer read: " + buffer.get(0));

        String[] copy = buffer.toArray(String[]::new);
        System.out.println("Typed array: " + Arrays.toString(copy));
        System.out.println("Array type: "
                + copy.getClass().getTypeName());

        List<String> safe =
                checkedCopy(List.of("A", "B"), String.class);
        System.out.println("Validated list: " + safe);

        List<?> mixed = List.of("A", 42);

        try {
            checkedCopy(mixed, String.class);
        } catch (ClassCastException ex) {
            System.out.println("Mixed input: ClassCastException");
        }

        try {
            checkedCopy(List.of("ok"), Integer.class);
        } catch (ClassCastException ex) {
            System.out.println("Wrong token: ClassCastException");
        }

        try {
            checkedCopy(List.of("A"), null);
        } catch (NullPointerException ex) {
            System.out.println("Missing token: NullPointerException");
        }

        List<String> wronglyAssumed =
                UncheckedBoundaryDemo.<String>assumedList(mixed);

        try {
            String value = wronglyAssumed.get(1);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println(
                    "Unchecked assumption: ClassCastException");
        }

        // Cố ý phá invariant bằng raw alias:
        Buffer<String> polluted = new Buffer<>();
        Buffer raw = polluted;
        raw.add(42);

        try {
            String value = polluted.get(0);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("Raw alias: ClassCastException");
        }

        List<String> backing = new ArrayList<>(List.of("ok"));
        List<String> checked =
                Collections.checkedList(backing, String.class);

        List rawChecked = checked;

        try {
            rawChecked.add(42);
        } catch (ClassCastException ex) {
            System.out.println("Checked wrapper: ClassCastException");
        }

        System.out.println("Backing after blocked add: " + backing);
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 -Xlint:rawtypes -Xlint:unchecked UncheckedBoundaryDemo.java
java UncheckedBoundaryDemo
```

**Standard output** của chương trình (không gồm compiler warnings):

```text
Buffer read: An
Typed array: [An, Binh]
Array type: java.lang.String[]
Validated list: [A, B]
Mixed input: ClassCastException
Wrong token: ClassCastException
Missing token: NullPointerException
Unchecked assumption: ClassCastException
Raw alias: ClassCastException
Checked wrapper: ClassCastException
Backing after blocked add: [ok]
```

**Đọc kết quả theo ranh giới niềm tin:**

1. `Buffer<String>` ban đầu chỉ nhận chuỗi qua `add(T)`, không để lộ `slots`, và `get` đọc đúng vùng `size`. Unchecked cast nội bộ được gắn với invariant cụ thể.
2. `toArray(String[]::new)` tạo mảng typed thật; backing array vẫn là `Object[]` và không bị trả trực tiếp.
3. `checkedCopy` xác minh từng phần tử từ nguồn `Object` theo `String.class` hoặc `Integer.class`; dữ liệu sai được báo **ngay tại biên chuyển đổi**.
4. `assumedList` chỉ xác nhận object bên ngoài là `List` và cast unchecked, **không kiểm tra phần tử**; lỗi xuất hiện khi bên gọi đọc `Integer` như `String`.
5. Raw `Buffer` bypass generic compile-time check để ghi `Integer` vào buffer vốn được dùng dưới kiểu `Buffer<String>`. Cast nội bộ không thể cứu invariant đã bị phá.
6. `Collections.checkedList` phát hiện `Integer` khi raw alias cố gọi `add` qua wrapper; backing list giữ nguyên `[ok]`.

Chương trình có hai raw aliases **cố ý dùng để minh họa lỗi**, nên `-Xlint:rawtypes -Xlint:unchecked` được kỳ vọng báo warnings ở các dòng đó. Việc ghi rõ chỗ nào không an toàn quan trọng hơn việc cố làm cho build không còn bất cứ warning nào bằng suppression rộng.

## 11. `Class<T>` không phải phép “khôi phục” toàn bộ generics

Một API `Class<T>` rất hữu ích khi kiểu mong muốn là runtime class cụ thể:

```java
static <T> T verified(Object candidate, Class<T> type) {
    return type.cast(candidate);
}

String name = verified("Java", String.class);
```

Nếu truyền một `Integer` cho `String.class`, `ClassCastException` xảy ra tại `cast`. Không cần unchecked cast.

Tuy nhiên, không tồn tại `List<String>.class`. Với một danh sách generic:

```java
Object input = List.of("A", 42);

boolean outer = input instanceof List<?>; // true
```

`outer` chỉ chứng minh kiểu tổng thể. Muốn khôi phục một hợp đồng dữ liệu phức tạp, cần validator có khả năng đi qua các lớp lồng nhau và giải thích chính sách null/covariance/mutability tương ứng.

Nếu hệ thống dùng reflection `Type`/`ParameterizedType` hoặc một type token để mô tả `List<String>`, metadata đó giúp xác định **schema** muốn kiểm tra, nhưng nó vẫn không tự duyệt và xác nhận object theo schema. Phải tách **đặc tả kiểu** khỏi **thực thi validation**.

## 12. Với legacy API, đặt trust boundary ở đâu?

Một ứng dụng có thể phải gọi một thư viện cũ trả raw `List`:

```java
// Chữ ký legacy minh họa:
static java.util.List loadLegacy() {
    return java.util.List.of("An", "Binh");
}
```

Sai lầm thường gặp là rải cast `(List<String>) loadLegacy()` ở nhiều tầng, rồi cho toàn bộ project sử dụng `List<String>` như thể dữ liệu đã được kiểm tra.

Một hướng là tạo **adapter duy nhất**:

```java
static List<String> loadNames() {
    return checkedCopy(loadLegacy(), String.class);
}
```

Adapter này là ranh giới rõ ràng: sau khi nó trả kết quả, caller nhận một snapshot typed do method tạo, và không cần biết nguồn legacy ban đầu raw.

Tài liệu hóa adapter:

- Nguồn raw có thể không phải list hoặc có phần tử sai kiểu.
- Phần tử sai kiểu gây `ClassCastException` ở bước `Class.cast`.
- Phần tử null gây `NullPointerException` theo chính sách đã chọn.
- Danh sách kết quả không thể sửa cấu trúc, nhưng các object phần tử mutable không tự được deep-copy.
- Nếu dữ liệu nguồn bị sửa đồng thời trong quá trình duyệt, adapter không cam kết snapshot atomic nếu chưa có chính sách đồng bộ.

Với nguồn legacy đã được tin cậy bởi một hợp đồng **được chứng minh riêng**, có thể có chỗ dùng cast unchecked nội bộ; nhưng nên ghi cụ thể **ai là producer, dữ liệu được bảo vệ bằng gì và điều kiện nào khiến giả định mất hiệu lực**.

## 13. Các bất biến dễ tưởng đúng nhưng thực tế chưa đủ

### 13.1. “Danh sách hiện tại chứa toàn String”

Bất biến này nói về **một thời điểm**, không đủ nếu có raw alias hoặc thread khác có thể thêm `Integer` ngay sau khi kiểm tra.

Cần thêm điều kiện **không còn đường mutation ngoài kiểm soát** hoặc phải tạo snapshot với cơ chế đồng bộ thích hợp.

### 13.2. “Mọi lần gọi `add` nhận `T`”

Đúng với caller dùng `Buffer<String>` typed, nhưng raw alias `Buffer raw` vẫn có thể gọi `add(42)` với warning. Nếu ranh giới an toàn buộc phải chống cả raw callers, nên dùng runtime token để xác thực ở chỗ ghi.

### 13.3. “Mảng có các phần tử String nên là String[]”

Sai. Mảng tạo bằng `new Object[n]` vẫn có runtime component type `Object`, kể cả khi mọi phần tử đều là `String`. Cast cả mảng sang `String[]` có thể gây `ClassCastException`.

### 13.4. “Annotation suppression chỉ dùng ở một dòng nên cast chắc chắn an toàn”

Sai. **Phạm vi nhỏ giúp audit** và tránh che các warning khác; nó không chứng minh nội dung dữ liệu. Cần kiểm tra invariant trước khi suppress.

### 13.5. “Wrapper checked bảo vệ cả backing list”

Không nếu vẫn còn một alias trực tiếp của backing list có thể sửa. `Collections.checkedList` kiểm tra các thao tác **qua wrapper**, không tự giám sát mọi tham chiếu khác tới cùng object.

### 13.6. “Sao chép dữ liệu là đủ cho thread safety”

Sao chép từng phần tử tạo một kết quả riêng về cấu trúc, nhưng nếu nguồn bị ghi đồng thời khi đang duyệt thì snapshot có thể không nhất quán. Cần quy định đồng bộ hoặc cấu trúc immutable phù hợp khi yêu cầu đa luồng.

## 14. Generic arrays và varargs: trường hợp suppression cần đánh giá riêng

Một lớp generic không được phép viết `new T[n]` vì `T` non-reifiable. Cách dùng `Object[]` nội bộ cộng cast từng phần tử không tương đương việc tạo `T[]` thật.

Một generic varargs method cũng có thể tạo cảnh báo:

```java
static <T> void visit(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

Varargs được truyền dưới dạng array. Khi element type non-reifiable, compiler có thể cảnh báo về khả năng **heap pollution** và generic array creation.

Nếu nội dung thực sự an toàn và declaration thuộc loại được phép, `@SafeVarargs` có thể được dùng cho constructor hoặc method `static`, `final`, `private` (với điều kiện phiên bản Java tương ứng):

```java
@SafeVarargs
static <T> void printAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

`@SafeVarargs` là **lời cam kết của tác giả**, không khiến `T` reifiable và không sửa được thao tác ghi sai vào varargs array qua `Object[]` alias.

Khi audit cast hoặc generic arrays, hãy xét riêng:

- Kiểu mảng được tạo thực tế (`Object[]`, `String[]` hay `List[]`).
- Mảng có bị lộ/giữ alias hay không.
- Có phép ghi sai kiểu qua raw hoặc `Object[]` hay không.
- Có đủ điều kiện để cam kết `@SafeVarargs` hay không.

Không thêm `@SafeVarargs` hoặc `@SuppressWarnings` chỉ vì muốn tắt warnings mà không phân tích phần thân method.

## 15. Bounded generics không tự tạo một runtime class cho `T`

Ví dụ:

```java
static <T extends Number> T identity(T value) {
    return value;
}
```

Bound `Number` giúp compiler biết có thể dùng các thao tác được khai báo ở `Number`, và erasure của `T` dựa trên bound đó. Nó **không** làm `T` thành một runtime class cụ thể như `Integer` ở mọi lần gọi.

Nếu một generic adapter viết:

```java
@SuppressWarnings("unchecked")
static <T extends Number> T assumeNumber(Object value) {
    return (T) value;
}
```

Cast có thể chỉ kiểm tra đối tượng tương thích `Number`. Nếu caller kỳ vọng `Integer` nhưng dữ liệu thực là `Double`, lỗi có thể xuất hiện khi caller tiêu thụ kết quả.

Tương tự, một type parameter `T extends Comparable<? super T>` cho phép gọi `compareTo` theo quan hệ generic ở compile time, nhưng không xác minh mọi object chưa đáng tin thuộc đúng type argument của một container.

Khi biên nhận dữ liệu cần kiểm tra subtype cụ thể, dùng `Class<T>` hoặc validator phù hợp thay vì suy luận rằng có bound là đủ.

## 16. Review checklist: một unchecked cast đủ điều kiện merge chưa?

Hãy kiểm tra những câu sau trước khi phê duyệt code:

1. **Vì sao compiler không thể tự chứng minh?** Do erasure, raw legacy boundary, generic backing array hay một điểm khác?
2. **Có tránh được cast không?** Dùng `List<?>`, `Class<T>.cast`, typed copy, factory, wildcard PECS hoặc generic API chuẩn.
3. **Nếu không tránh được, cast nằm ở đâu?** Một biến local/phương thức adapter nhỏ có phải vị trí hợp lý nhất không?
4. **Bất biến viết thành lời có cụ thể không?** Ví dụ “mọi `slots[0..size)` được ghi qua `add(T)`, không có alias sửa storage”.
5. **Mọi đường ghi đã được liệt kê?** `set`, `addAll`, deserialize, listener/callback, raw API?
6. **Có nguy cơ raw alias/unchecked cast từ caller không?** Điều kiện tin cậy đã được giới hạn rõ chưa?
7. **Null được xử lý thế nào?** Cấm và báo ngay, hay cho phép nhất quán ở tất cả đường ghi?
8. **Storage có bị lộ không?** Return `Object[]`, array view, backing collection hoặc internal iterator mutable?
9. **Đọc đúng vùng logic không?** `size` và index check chính xác?
10. **Có concurrency policy không?** Nếu public API dự định thread-safe, proof về type safety phải tương thích với proof về đồng bộ.
11. **Cast được suppress ở scope nào?** Có che warnings khác ngoài ý muốn không?
12. **Tests có tình huống sai kiểu không?** Dữ liệu hỗn hợp, null, raw alias, array runtime mismatch, empty list?
13. **Có test API result không?** Kết quả là snapshot hay view; mutable hay unmodifiable; có ghi rõ trong Javadoc?
14. **Có bằng chứng runtime khi cần không?** `Class<T>.cast` hoặc validator thực sự kiểm tra dữ liệu ở biên?
15. **Có nên bật linter trong CI?** Ví dụ `javac -Xlint:unchecked -Xlint:rawtypes`, rồi xem xét cảnh báo ở từng vị trí.

Nếu không thể trả lời các câu về đường ghi và invariant, chưa nên coi một unchecked cast là đã được chứng minh an toàn.

## 17. Những lỗi phổ biến

**Lỗi 1 — “Unchecked cast đồng nghĩa code chắc chắn ném exception.”** Không. Compiler cảnh báo vì không thể chứng minh; cast có thể đúng hoặc sai tùy invariant/dữ liệu.

**Lỗi 2 — “Suppress warning sẽ khiến JVM kiểm tra generic type argument.”** Không. Annotation chỉ ảnh hưởng diagnostics của compiler.

**Lỗi 3 — “Một `List<String>` lấy bằng cast từ `Object` đã được xác thực.”** Không. Chỉ có thể đã kiểm tra kiểu ngoài `List`; từng phần tử chưa được kiểm chứng.

**Lỗi 4 — “`private Object[]` thì bất biến luôn được bảo đảm.”** Không. API raw `add` vẫn có thể làm hỏng nội dung; public getter để lộ alias cũng phá đóng gói.

**Lỗi 5 — “Cast `(T[]) new Object[n]` là cách tạo mảng đúng runtime type.”** Không. Với `T = String`, object vẫn là `Object[]`.

**Lỗi 6 — “Đã validate toàn bộ list thì cast tham chiếu gốc mãi mãi an toàn.”** Không nếu list mutable và có alias khác. Bản sao có kiểm tra giải quyết rủi ro cấu trúc tốt hơn, nhưng còn yêu cầu snapshot nhất quán khi concurrent mutation.

**Lỗi 7 — “Mọi cast trong class generic đều nên bị suppress ở cấp class.”** Không. Đó là cách dễ che các unsafe operations mới nhất.

**Lỗi 8 — “`Class<T>` kiểm tra được cả `List<Map<K,V>>`.”** Không. Token class đơn lẻ không biểu diễn toàn bộ type arguments lồng nhau.

**Lỗi 9 — “`Collections.checkedList` kiểm tra cả các đường ghi qua backing alias.”** Không. Chỉ thao tác qua wrapper được bảo vệ bằng check của wrapper.

**Lỗi 10 — “Bound `T extends Number` chứng minh object là `Integer` khi caller cần `Integer`.”** Không. Bound nói về quan hệ subtype, không khóa T thành một subtype cụ thể tại runtime.

**Lỗi 11 — “Nếu không có ClassCastException tại chỗ cast thì dữ liệu chắc chắn an toàn.”** Không. Lỗi có thể chỉ xuất hiện ở một lần đọc/truy xuất xa hơn.

**Lỗi 12 — “JUnit test với một `List<String>` đủ chứng minh cast.”** Không. Test cho ví dụ cụ thể không thay proof về tất cả đường ghi, aliases, lifetime và contract.

## 18. Bài tập tự kiểm tra

**Câu 1.** Vì sao `(List<String>) input` từ một `Object` có thể là unchecked cast?

Vì JVM không có runtime class chuyên biệt chứa type argument `String` cho list để kiểm tra đầy đủ; cast có thể xác nhận kiểu ngoài mà không xác minh mọi phần tử.

**Câu 2.** Có nên đặt `@SuppressWarnings("unchecked")` trên toàn bộ class để build sạch không?

Thông thường không. Nên khoanh vùng ở đúng local variable/method đã có invariant rõ, để các cảnh báo khác còn được báo.

**Câu 3.** Điều kiện cốt lõi để cast `(T) slots[i]` có thể biện minh trong `Buffer<T>` là gì?

Các phần tử thuộc vùng hợp lệ được ghi qua đường typed bảo toàn `T`; storage không rò rỉ và không có đường ghi không kiểm tra trong giả định sử dụng; index/size được kiểm soát.

**Câu 4.** Vì sao `(T[]) slots` khác với cast từng phần tử?

Mảng được tạo `new Object[n]` có runtime component type `Object`; cast không đổi class của mảng thành `String[]` khi `T = String`.

**Câu 5.** `Class<String>.cast(42)` giúp gì?

Nó ném `ClassCastException` ngay tại biên kiểm tra vì `Integer` không tương thích với runtime class `String`. Đây là checked runtime cast của một object.

**Câu 6.** `Collections.checkedList(backing, String.class)` có sửa các giá trị sai kiểu đã có trước không?

Không. Wrapper kiểm tra các thao tác phù hợp đi **qua chính wrapper**, không tự sửa backing hoặc ngăn alias bên ngoài ghi trực tiếp.

**Câu 7.** Nếu một API đã kiểm tra list rồi tiếp tục trả chính list gốc mutable, rủi ro còn lại?

Một alias khác có thể sửa list sau khi kiểm tra, khiến lời hứa kiểu không còn đúng. Cần quy định ownership và validation/snapshot thích hợp.

**Câu 8.** Bật `-Xlint:rawtypes -Xlint:unchecked` giúp gì?

Nó phát hiện các raw types và unchecked operations để reviewer tập trung phân tích, không tự chứng minh code có hoặc không có heap pollution.

**Câu 9.** `T extends Number` có thay được `Integer.class` khi cần kiểm tra runtime chính xác `Integer` không?

Không. `Number` là upper bound của nhiều subtype; cần token hoặc validator phù hợp với yêu cầu thực tế.

## 19. Kết luận: một nguyên tắc nhỏ, một chứng minh rõ

Một unchecked cast có thể là lựa chọn hợp lý trong **nội bộ một generic API được đóng gói chặt**, nhưng chỉ khi ta nêu rõ và duy trì được invariant chứng minh nội dung phù hợp. Hãy đặt cast tại **một trust boundary** dễ thấy; để `@SuppressWarnings("unchecked")` ở **phạm vi nhỏ nhất**; giữ raw types và backing arrays khỏi các phần API thông thường; kiểm tra dữ liệu chưa đáng tin bằng `Class<T>.cast` hoặc validator thay vì gắn nhãn qua unchecked cast.

**Không đánh đồng bốn việc:** type parameters ở compile time, runtime class của object, metadata generic của reflection và nội dung dữ liệu thực tế. Khi những quan hệ này được diễn đạt đúng trong chữ ký/Javadoc và được bảo vệ bằng kiểm tra hoặc invariant cụ thể, một API generic mới có thể xứng đáng được gọi là type-safe, dù ở bên trong còn một cast mà compiler không tự chứng minh được.