# Kiểm thử ranh giới raw type, reflection và ép kiểu trong Java Generics

Java Generics chủ yếu bảo vệ **tính đúng kiểu ở thời điểm biên dịch**. Khi chương trình đi qua **raw type**, **unchecked cast**, **reflection** hoặc các API nhận dữ liệu dạng `Object`, một phần bảo đảm của compiler có thể bị bỏ qua. Đây chính là các *ranh giới kiểu* cần kiểm thử có chủ đích: không chỉ thử rằng dữ liệu đúng hoạt động, mà còn chứng minh dữ liệu sai bị từ chối ở đâu, hoặc sẽ gây lỗi muộn ở đâu nếu không có kiểm tra.

Mục tiêu của bài:

- Phân biệt **lỗi bị javac từ chối**, **cảnh báo unchecked nhưng code vẫn chạy**, và **exception xảy ra khi runtime tiêu thụ dữ liệu sai kiểu**.
- Tạo bài kiểm thử có cả *positive cases* và *negative cases*, thay vì chỉ chạy dữ liệu hợp lệ.
- Hiểu rằng một cast sang `List<String>` không xác minh từng phần tử của danh sách.
- Chứng minh `Field.set` và `Method.invoke` có thể bỏ qua **ràng buộc type argument** của generic declaration do erasure, dù vẫn thực hiện các runtime checks cần thiết đối với kiểu đã xóa.
- Kiểm tra các biện pháp phòng vệ như `Class<T>.cast`, `Collections.checkedList`, typed copy/validator và kiểm soát các đường ghi.
- Phân biệt array runtime checks với generic type checks và giải thích đúng `ClassCastException`, `ArrayStoreException`, `IllegalArgumentException`, `InvocationTargetException`.
- Tạo một chương trình Java 17+ độc lập, có kiểm tra kết quả **không phụ thuộc `-ea`**, in số bài kiểm thử thành công và làm chương trình thất bại khi điều kiện kỳ vọng không đúng.

**Nguyên tắc:** “Code chạy qua unchecked cast” không đồng nghĩa “đã chứng minh an toàn”. Một bài kiểm thử tốt phải hỏi **bất biến kiểu còn đúng sau khi đi qua mỗi ranh giới hay không**, và exception xuất hiện ngay ở biên hay chỉ khi một caller đọc kết quả với type argument cụ thể.

## 1. Ba tầng cần tách trong kế hoạch kiểm thử

| Tầng | Ví dụ | Kiểm tra bằng gì? | Kết quả đáng kỳ vọng |
| --- | --- | --- | --- |
| **Compile-time type checking** | `List<String>.add(42)` khi caller typed | `javac` | Lỗi biên dịch |
| **Compile-time warning** | `List raw = typed; raw.add(42)` | `javac -Xlint:rawtypes -Xlint:unchecked` | Biên dịch có cảnh báo về raw/unchecked |
| **Runtime ngoại lệ muộn** | Đọc một `Integer` ô nhiễm như `String` | Bài test chạy | `ClassCastException` khi giá trị được tiêu thụ theo kiểu cụ thể |
| **Runtime validation chủ động** | `String.class.cast(42)` | Bài test chạy | `ClassCastException` ngay ở biên kiểm tra |
| **Reflection trên generic declaration** | `Field.set` gán `List<Integer>` vào field khai báo `List<String>` | Reflection + đọc lại | Gán có thể thành công; lỗi khi đọc phần tử như `String` |
| **Array runtime check** | `Object[] a = new String[1]; a[0] = 42` | Bài test chạy | `ArrayStoreException` ngay khi ghi |
| **Wrong array cast** | `(String[]) new Object[]{"x"}` | Bài test chạy | `ClassCastException` vì runtime class của array là `Object[]` |

Ở tầng compile-time, compiler chặn thao tác trước khi có chương trình chạy. Ở tầng runtime, kết quả phụ thuộc **runtime class thực tế**, **kiểm tra do API áp dụng**, và **thời điểm caller sử dụng giá trị bị ô nhiễm**.

Không nên gom mọi hiện tượng thành một nhãn “Java generic không an toàn”: một code path có thể được bảo vệ tốt ở compile time, một đường khác bị raw type phá hợp đồng, trong khi reflection vẫn có những kiểm tra **erased parameter type** của riêng nó.

## 2. Xác định những ranh giới đáng kiểm thử

Một generic API thường có các vị trí rủi ro:

1. **Biên nhập dữ liệu:** `Object`, `List<?>`, dữ liệu parse từ JSON, input từ database/legacy API; caller có thể tuyên bố type argument mà không xác thực nội dung.
2. **Biên gọi bằng raw type:** compiler biết `List` nhưng không giữ quan hệ `List<String>`, nên một lời gọi `add(Integer)` có thể đi qua với unchecked warning.
3. **Biên reflection:** `Field.set`, `Method.invoke`, `Constructor.newInstance` dùng các runtime classes ở descriptor sau erasure; không thể tự xác minh mọi parameterized arguments.
4. **Biên ép kiểu:** `(T)`, `(List<T>)`, `Class<T>.cast`; cần phân biệt cast được JVM kiểm tra thật với cast mà compiler chỉ cảnh báo.
5. **Biên container/array:** `Object[]`, `T[]`, `List<T>`, arrays covariant và generic collections invariant; runtime kiểm tra mỗi loại theo cơ chế khác nhau.
6. **Biên trả kết quả:** API trả `List<T>`, `T`, `T[]`; cast có thể chưa thất bại tại lúc return nhưng lỗi xuất hiện ở caller.
7. **Biên mutation/alias:** một giá trị đã từng đúng kiểu có thể bị thay sau đó qua raw alias, backing list hoặc thread khác.

Với từng biên, hãy viết rõ ba yếu tố: **đầu vào không đáng tin là gì**, **nghĩa vụ của API là gì**, và **test phải quan sát điều gì**. Ví dụ một adapter `Object -> List<String>` có thể có hợp đồng “từ chối ngay mọi phần tử không phải `String`”; không thể chỉ kiểm tra rằng cast ngoài thành công.

## 3. Bài test compile-time: những thao tác Java phải từ chối

Các đoạn ở mục này **cố ý không biên dịch** và phải đặt trong file kiểm tra riêng; không đưa vào chương trình runnable sau đó.

```java
import java.util.*;

class CompileTimeFailures {
    static void test() {
        List<String> names = new ArrayList<>();

        // Sai kiểu phần tử: javac từ chối.
        names.add(42);

        // Generic invariance: List<String> không là List<Object>.
        List<Object> objects = names;

        // Java Generics không nhận primitive type argument.
        List<int> numbers = new ArrayList<>();

        // Không có generic class literal List<String>.
        Class<?> token = List<String>.class;

        Object input = names;
        // Không xác minh được type argument trong Object -> List<String>.
        boolean ok = input instanceof List<String>;
    }
}
```

Dùng `javac CompileTimeFailures.java` để xác nhận compiler báo lỗi. Thông điệp cụ thể có thể khác giữa các phiên bản JDK, nhưng **kết quả mong muốn là biên dịch không thành công**.

Một bộ test không nên chỉ “chạy đoạn sai và chờ `ClassCastException`”: những dòng trên **không tạo bytecode hợp lệ** nên không có runtime behavior để quan sát. Tách *negative compilation tests* khỏi *runtime exception tests*.

### Vì sao nên có negative compilation tests?

Một thư viện generic có thể vô tình làm yếu public API từ `void add(T)` thành `void add(Object)`, hoặc trả `Object` thay `T`. Các test chỉ chạy dữ liệu đúng có thể vẫn pass, nhưng những thao tác trước kia **bị compiler chặn** nay được chấp nhận. Negative compilation tests giúp phát hiện sự thay đổi hàng rào type safety ở **compile time**.

Khi xây CI, có thể đặt fixtures cố ý không compile trong một nhóm riêng, xác minh **exit code không bằng 0** và kiểm tra mẫu diagnostic cần thiết. Không trộn chúng vào lệnh build toàn bộ source chính.

## 4. Raw type: tạo heap pollution bằng đường ghi mà compiler cảnh báo

Ví dụ:

```java
List<String> names = new ArrayList<>();
names.add("ok");

List raw = names; // Raw type: bỏ qua type argument String.
raw.add(42);      // Unchecked call, thường vẫn biên dịch.

// String second = names.get(1); // Runtime ClassCastException.
```

Ở chỗ gọi `raw.add(42)`, method `add` được nhìn qua raw `List`. Mặc dù cùng object sau đó vẫn được dùng dưới biến `List<String>`, phần tử `Integer` đã lọt vào danh sách.

Hiện tượng một biến tham số hóa tuyên bố `List<String>` nhưng vùng dữ liệu nó tham chiếu chứa một phần tử không thỏa `String` gọi là **heap pollution**.

Bài test nên kiểm tra hai điểm riêng biệt:

- **Đường ghi raw có thể đi qua:** không nhất thiết ném exception ngay khi thêm vào `ArrayList`.
- **Đường đọc typed mới có thể thất bại:** `String value = names.get(1)` yêu cầu một `String`; compiler có thể chèn `checkcast String` tại điểm tiêu thụ kết quả.

Không viết test kiểu `Object o = names.get(1)` rồi kết luận “không có lỗi”: gán vào `Object` có thể không cần cast sang `String` nên chưa chạm tới điều kiện đang muốn kiểm tra.

### Raw type không nên là một phần API sản xuất

Raw types thường xuất hiện ở mã cũ hoặc đoạn minh họa. Với code mới, giữ `List<String>`, `List<?>`, hoặc `List<T>` theo đúng nghĩa. Các test raw alias cần **cô lập trong fixture dành riêng cho hành vi không an toàn** để cảnh báo không lan ra code nghiệp vụ.

Chạy:

```bash
javac -Xlint:rawtypes -Xlint:unchecked GenericBoundaryTests.java
```

Trong ví dụ đầy đủ có raw aliases **cố ý**, nên warning tại các dòng đó là điều được chờ đợi. Không dùng `@SuppressWarnings("unchecked")` ở cấp class chỉ để build test im lặng; mục đích của test là chứng minh compiler đang cảnh báo ở đúng biên.

## 5. Unchecked cast của cả `List<T>`: kiểm tra vỏ ngoài không kiểm tra phần tử

Với dữ liệu chưa biết:

```java
Object outside = List.of("one", 7);

@SuppressWarnings("unchecked")
List<String> claimed = (List<String>) outside;
```

Cast này có thể đi qua vì object thực hiện `List`; Java không có runtime class chuyên biệt cho `List<String>` để quét và chứng minh type argument `String`.

Hai bài test khác nhau:

```java
// Thành công: chỉ xác nhận kích thước.
boolean hasTwo = claimed.size() == 2;

// Thất bại: đọc phần tử Integer và yêu cầu String.
// String second = claimed.get(1);
```

Hành vi cần nhớ:

- **`List<String>` ở source code** là một hợp đồng generic mà compiler áp dụng cho các lời gọi typed.
- **`List` ở runtime** là interface/container bên ngoài; các type arguments như `String` đã bị erasure.
- **Unchecked cast** không chứng minh phần tử thực, và runtime exception có thể xuất hiện ở vị trí rất xa dòng cast.

Một test chỉ kiểm tra `claimed != null` hoặc `claimed.size()` **không đủ** để chứng minh giá trị trả về có thể được dùng như `List<String>`.

### Vấn đề `List<?> -> List<String>`

`List<?>` nói rõ “đây là list của một kiểu chưa biết”. Nó cho phép đọc từng phần tử như `Object`, không cho phép giả định tất cả là `String`. Nếu cần nâng contract lên `List<String>`, hãy **xác thực từng phần tử** hoặc có một proof đáng tin cậy về nguồn dữ liệu.

## 6. Reflection trên field generic: erased type và generic signature là hai việc khác nhau

Định nghĩa:

```java
static final class Document {
    public List<String> tags = new ArrayList<>(List.of("start"));
}
```

Đọc metadata:

```java
Field field = Document.class.getDeclaredField("tags");

Class<?> erased = field.getType();           // List.class
Type declared = field.getGenericType();     // ParameterizedType List<String>
```

`Field.getType()` trả `Class` ứng với kiểu trường ở runtime: `List`. `Field.getGenericType()` có thể trả `ParameterizedType` chứa `String` từ **chữ ký khai báo**. Metadata của khai báo **không phải** một runtime validator quét phần tử.

Vì vậy:

```java
Document document = new Document();
field.set(document, List.of(99)); // Object là List, nên có thể được gán.

// String tag = document.tags.get(0); // ClassCastException.
```

Reflection vẫn kiểm tra ràng buộc cần thiết của `Field.set` đối với **field type có ở runtime** và khả năng truy cập. Nó **không tự xác minh** `List<String>` bằng việc duyệt cả list. Việc gán `List<Integer>` vào field khai báo `List<String>` có thể thành công nếu object là `List` hợp lệ ở mức erased type.

Test tốt phải xác nhận:

1. Metadata generic thật sự cho thấy khai báo `List<String>`.
2. Runtime type của field là `List`.
3. Một giá trị `List<Integer>` đi vào được qua reflection khi điều kiện truy cập và kiểu erasure cho phép.
4. Khi caller sau đó đọc phần tử như `String`, invariant bị vi phạm và gây `ClassCastException`.

Nếu phản xạ gán một `String` không phải `List` vào field runtime `List`, `Field.set` sẽ từ chối vì **không tương thích erased field type**. Đừng suy luận reflection “chấp nhận mọi thứ”.

## 7. Reflection trên method generic: tìm theo kiểu tham số đã xóa

Một lớp:

```java
static final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    public void set(T next) {
        this.value = next;
    }

    T get() {
        return value;
    }
}
```

Vì `T` không có upper bound tường minh, erasure của `T` là `Object`. Phương thức reflection có thể được tìm theo:

```java
Method setter = Box.class.getDeclaredMethod("set", Object.class);
Box<String> box = new Box<>("first");

setter.invoke(box, 123); // Object argument hợp erased parameter.
```

Một phương thức `set(T)` trong Java source **không tự kiểm tra `T = String` ở runtime** khi lời gọi qua reflection dùng erased parameter `Object`. Vì thế, giá trị `Integer` có thể được lưu, và:

```java
// String value = box.get(); // ClassCastException.
```

sẽ bộc lộ heap pollution.

**Phân biệt hai loại ngoại lệ của reflection:**

- Nếu lời gọi `Method.invoke` có đối số **không phù hợp với parameter types ở runtime**, reflection có thể ném `IllegalArgumentException` ở biên invoke.
- Nếu **chính thân phương thức được gọi ném exception**, `Method.invoke` thường bọc nó trong `InvocationTargetException`. Test muốn xác minh ngoại lệ từ body nên kiểm tra `getCause()`.
- Nếu invocation thành công nhưng dữ liệu bị sai contract generic, lỗi có thể chỉ xuất hiện ở **lần đọc typed tiếp theo**, như ví dụ `Box<String>`.

Đừng viết test chỉ kiểm tra `setter.invoke` trả `null` với method `void` rồi coi dữ liệu hợp lệ: `void` có thể trả `null` qua reflection dù method đã ghi một giá trị sai kiểu.

### Bound sẽ ảnh hưởng erased signature

Với `class NumericBox<T extends Number>`, `set(T)` có erased parameter type `Number`, không phải `Object`. Reflection có thể từ chối một `String` không thuộc `Number` khi invoke, nhưng vẫn không thể tự xác minh chính xác mọi subtype `T` mà client kỳ vọng, ví dụ `Integer` so với `Double`.

## 8. `Class<T>.cast`: kiểm tra class runtime có thể chứng minh được

Một giá trị `Object` có thể được kiểm tra bằng class token cụ thể:

```java
String text = String.class.cast("safe");

// String bad = String.class.cast(7); // ClassCastException.
```

So với `(T)` trong một generic method không có runtime token, `Class<T>.cast` biết class được yêu cầu ở runtime. Cũng có `Class.isInstance`:

```java
boolean yes = String.class.isInstance("Java"); // true
boolean no = String.class.isInstance(7);       // false
```

Những góc cạnh cần thử:

- `String.class.isInstance(null)` trả `false`.
- `String.class.cast(null)` trả `null`; nếu hợp đồng muốn cấm null, cần dùng `Objects.requireNonNull` riêng.
- `Class<T>.cast` không có sẵn `List<String>.class` để xác minh type arguments lồng nhau. `List.class.cast(value)` chỉ biết object ngoài có là `List` hay không.

Một API adapter từ `Object` thành `List<T>` có thể **duyệt từng phần tử** và gọi `elementType.cast` trước khi sao chép sang một danh sách mới. Với dữ liệu nested, phải kiểm tra các tầng theo schema tương ứng, không chỉ dùng cast ngoài.

## 9. `Collections.checkedList`: runtime guard khi ghi qua wrapper

`Collections.checkedList(backing, String.class)` tạo một wrapper kiểm tra runtime class của phần tử đối với thao tác thêm/sửa **đi qua wrapper**:

```java
List<String> protectedList =
        Collections.checkedList(new ArrayList<>(), String.class);

List rawProtected = protectedList;

// rawProtected.add(4); // ClassCastException tại thao tác ghi.
```

Đây là một kiểm thử rất có giá trị vì nó cho thấy một cách kiểm tra chủ động **ngay tại biên ghi**, khác hẳn đọc muộn từ raw-polluted `ArrayList`.

Nhưng một `checkedList` **không** tự làm sạch phần tử sai kiểu đã tồn tại trước khi bọc. Nếu còn một alias khác tham chiếu **trực tiếp backing list** và ghi sai kiểu ở đó, wrapper không có cách chặn thao tác không đi qua nó.

Thử nghiệm nên bao gồm:

1. Ghi giá trị đúng kiểu qua wrapper thành công.
2. Ghi giá trị sai qua raw alias **của wrapper** bị chặn.
3. Backing không thay đổi sau lần ghi bị chặn.
4. Nếu thiết kế có thể để lộ alias backing, xác định test riêng cho đường bypass đó — hoặc thay đổi API để không lộ alias.

`checkedList` cũng không tự bảo đảm thread safety, immutability hay deep validation của generic nested elements.

## 10. Array covariance và runtime component type: hai lỗi khác nhau

Arrays được Java kiểm tra bằng **runtime component type**, khác với erased generic arguments của `List<String>`.

Trường hợp ghi sai:

```java
Object[] strings = new String[] { "x" };
strings[0] = 8; // ArrayStoreException.
```

Tham chiếu có kiểu `Object[]` nhưng object thật là `String[]`. JVM biết component type là `String` và chặn việc lưu `Integer`.

Trường hợp cast sai cả mảng:

```java
Object[] data = new Object[] { "x" };
// String[] actual = (String[]) data; // ClassCastException.
```

Mặc dù toàn bộ phần tử hiện có là `String`, object mảng vẫn có runtime class `Object[]`. Ép tham chiếu sang `String[]` không biến đổi object thành một mảng có component type khác.

Trường hợp cast đúng:

```java
Object[] data = new String[] { "x" };
String[] actual = (String[]) data; // Thành công: runtime class là String[].
```

Trong test, luôn phân biệt:

- `ArrayStoreException` là **thất bại khi ghi một phần tử** vào array có runtime component type không phù hợp.
- `ClassCastException` là **thất bại khi cast tham chiếu** tới một array class không phù hợp.

Một generic API dùng backing `new Object[n]` không thể hứa `T[]` typed thật chỉ nhờ unchecked cast `(T[]) data`. Nếu cần `String[]` đúng runtime type, phải tạo mảng đó qua `String[]::new` hoặc token/factory rồi sao chép phần tử.

## 11. Chương trình Java 17+ hoàn chỉnh: 17 bài kiểm thử độc lập

Lưu nguyên chương trình sau vào file **`GenericBoundaryTests.java`**. Nó chỉ dùng JDK chuẩn, không cần JUnit.

```java
import java.lang.reflect.*;
import java.util.*;

public class GenericBoundaryTests {
    private static int passed = 0;

    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        public void set(T next) {
            this.value = next;
        }

        T get() {
            return value;
        }
    }

    static final class Document {
        public List<String> tags =
                new ArrayList<>(List.of("start"));
    }

    static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }

        passed++;
        System.out.println("PASS " + label);
    }

    static void fails(
            String label,
            Class<? extends Throwable> expected,
            Runnable action) {
        try {
            action.run();
        } catch (Throwable error) {
            if (!expected.isInstance(error)) {
                throw new AssertionError(
                        label + " had "
                        + error.getClass().getSimpleName(),
                        error);
            }

            passed++;
            System.out.println(
                    "PASS " + label + " -> "
                    + error.getClass().getSimpleName());
            return;
        }

        throw new AssertionError(label + " did not throw");
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        List<String> typed = new ArrayList<>();
        typed.add("ok");

        check("typed write/read",
                typed.get(0).equals("ok"));

        List raw = typed;
        raw.add(42);

        fails("raw alias causes late failure",
                ClassCastException.class, () -> {
                    String value = typed.get(1);
                    System.out.println(value);
                });

        Object outside = List.of("one", 7);

        // Cố ý minh họa một cast không kiểm tra phần tử.
        @SuppressWarnings("unchecked")
        List<String> claimed = (List<String>) outside;

        check("unchecked outer cast does not inspect elements",
                claimed.size() == 2);

        fails("unchecked element read",
                ClassCastException.class, () -> {
                    String value = claimed.get(1);
                    System.out.println(value);
                });

        check("class token accepts String",
                String.class.isInstance("safe"));

        check("class token rejects Integer",
                !String.class.isInstance(7));

        fails("checked token cast",
                ClassCastException.class,
                () -> String.class.cast(7));

        Document document = new Document();
        Field field = Document.class.getDeclaredField("tags");

        check("field erased type",
                field.getType() == List.class);

        check("field generic signature",
                field.getGenericType()
                        instanceof ParameterizedType);

        field.set(document, List.of(99));

        fails("reflection field pollution",
                ClassCastException.class, () -> {
                    String value = document.tags.get(0);
                    System.out.println(value);
                });

        Box<String> box = new Box<>("first");
        Method setter = Box.class.getDeclaredMethod(
                "set", Object.class);

        check("generic method erased parameter",
                setter.getParameterTypes()[0] == Object.class);

        setter.invoke(box, 123);

        fails("reflection method pollution",
                ClassCastException.class, () -> {
                    String value = box.get();
                    System.out.println(value);
                });

        List<String> protectedList =
                Collections.checkedList(
                        new ArrayList<>(), String.class);

        List rawProtected = protectedList;

        fails("checkedList guards write",
                ClassCastException.class,
                () -> rawProtected.add(4));

        check("checkedList remains empty",
                protectedList.isEmpty());

        Object[] stringArray = new String[] { "x" };

        check("cast actual String[]",
                ((String[]) stringArray)[0].equals("x"));

        fails("array store guard",
                ArrayStoreException.class,
                () -> stringArray[0] = 8);

        Object[] objectArray = new Object[] { "x" };

        fails("Object[] is not String[]",
                ClassCastException.class, () -> {
                    String[] nope = (String[]) objectArray;
                    System.out.println(nope.length);
                });

        System.out.println("TOTAL PASS: " + passed);
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac -encoding UTF-8 -Xlint:rawtypes -Xlint:unchecked GenericBoundaryTests.java
java GenericBoundaryTests
```

**Standard output** (không bao gồm compiler warnings):

```text
PASS typed write/read
PASS raw alias causes late failure -> ClassCastException
PASS unchecked outer cast does not inspect elements
PASS unchecked element read -> ClassCastException
PASS class token accepts String
PASS class token rejects Integer
PASS checked token cast -> ClassCastException
PASS field erased type
PASS field generic signature
PASS reflection field pollution -> ClassCastException
PASS generic method erased parameter
PASS reflection method pollution -> ClassCastException
PASS checkedList guards write -> ClassCastException
PASS checkedList remains empty
PASS cast actual String[]
PASS array store guard -> ArrayStoreException
PASS Object[] is not String[] -> ClassCastException
TOTAL PASS: 17
```

**Vì sao test runner này không cần `-ea`?** `check` và `fails` **tự ném `AssertionError`** nếu điều kiện không thỏa. Toán tử `assert` của Java có thể bị tắt trừ khi JVM được chạy với `-ea`; harness ở đây luôn hoạt động.

**Cách đọc các dòng PASS:** mỗi dòng xác nhận **hành vi kỳ vọng của đúng một tình huống**. Dòng có `-> ClassCastException` là một **negative test thành công**, không phải lỗi ngoài ý muốn của toàn chương trình.

Trong code có hai raw aliases và hai unchecked calls cố ý; `-Xlint` sẽ phát cảnh báo. Chúng thuộc **fixture kiểm thử**, không phải mẫu mã nên đưa trực tiếp vào ứng dụng sản xuất.

## 12. Vì sao kiểm tra exception phải đủ chính xác?

Một bài test kém có thể viết:

```java
try {
    suspiciousOperation();
} catch (Exception ex) {
    System.out.println("pass");
}
```

Nếu `suspiciousOperation` ném `NullPointerException` do bug khác thay vì `ClassCastException` cần kiểm tra, test vẫn báo pass. Một bài test khác còn yếu hơn là bắt mọi exception nhưng **không fail khi không có exception**.

Trong chương trình đầy đủ, helper `fails(label, expected, action)` có hai điều kiện:

1. **Đúng loại exception**: dùng `expected.isInstance(error)`. Nếu exception sai loại, ném `AssertionError`.
2. **Bắt buộc phải có exception**: nếu `action.run()` không ném, helper cũng ném `AssertionError` thay vì im lặng pass.

Với các trường hợp kiểm tra rất chặt, bạn có thể so sánh `error.getClass() == expected` để yêu cầu class chính xác. `isInstance` cho phép subtype của exception mong đợi, phù hợp khi test chỉ cần bảo đảm một loại lỗi khái quát.

**Không nên khẳng định vị trí stack trace/line number cố định** nếu code có thể thay đổi hoặc được biên dịch bằng các JDK khác nhau. Test nên giữ kỳ vọng vào loại exception và hợp đồng thực sự quan trọng.

### Vì sao không chỉ kiểm tra `ClassCastException` mà bỏ qua dữ liệu?

Một negative test phải thường xuyên kiểm tra **trạng thái sau lỗi**. Ví dụ wrapper `checkedList` từ chối thêm một phần tử sai: ngoài exception, hãy xác nhận list không chứa phần tử đó. Nếu một API hứa transaction-like behavior, các test còn phải xác minh trạng thái không bị thay đổi một phần; nhiều collection API **không** hứa atomicity cho thao tác hàng loạt.

## 13. Negative compilation tests và cảnh báo `javac`: đừng phụ thuộc thông điệp chính xác

Với compile-time failures, nên tạo các fixture riêng:

```java
// File riêng dành cho kiểm tra compiler, không thuộc file runnable.
import java.util.*;

class WrongUse {
    void addWrongValue() {
        List<String> names = new ArrayList<>();
        names.add(3); // Sai kiểu: compiler từ chối.
    }
}
```

Khi xây kiểm thử tự động, hãy kiểm tra exit code của `javac` là thất bại. Nếu bạn cần xác minh **loại diagnostic**, có thể kiểm tra các từ khóa ổn định tương đối (như kiểu thực và kiểu yêu cầu) nhưng nên tránh so khớp toàn bộ dòng lỗi, dấu câu, đường dẫn tệp hay số dòng nếu phải hỗ trợ nhiều JDK.

Đối với một fixture raw alias được **phép biên dịch với warning**, có thể kiểm thử rằng `javac -Xlint:unchecked -Xlint:rawtypes` vẫn phát thông báo. Đừng nhầm **lỗi** và **cảnh báo**: `-Werror` có thể biến warnings thành lỗi build, nhưng đó là chính sách CI được cấu hình thêm, không có nghĩa lời gọi raw vốn dĩ bị JLS cấm trong mọi cấu hình.

Một chiến lược CI hợp lý có ba nhóm:

- **Compile-positive:** các lời gọi generic đúng phải compile.
- **Compile-negative:** các lời gọi sai type contract phải bị từ chối.
- **Runtime-boundary:** fixture cố ý dùng raw/reflection/unchecked, xác nhận exception và bất biến mong muốn.

Nhóm thứ ba có thể cho phép warnings có chủ đích mà không để các cảnh báo ấy tràn sang source chính.

## 14. Chọn test input để chạm đúng biên thay vì chỉ thử “happy path”

Đối với một API generic, nên có test cases như sau:

| Biên | Positive case | Negative/edge case |
| --- | --- | --- |
| `List<String>` typed | `add("A")`, `get(0)` | `add(42)` phải fail compile |
| Raw alias | Không dùng raw trong code thường | Raw `add(42)` làm lỗi lúc đọc typed |
| `Object -> List<String>` unchecked | List thực chỉ chứa String | List hỗn hợp String/Integer vẫn cast ngoài được, lỗi khi đọc |
| `Class<String>` | `cast("A")` | `cast(42)`; xét thêm null policy |
| `Field.set` | Gán list đúng kiểu | Gán `List<Integer>` vào field `List<String>` qua reflection |
| `Method.invoke` | Invoke với erased parameter đúng và dữ liệu hợp đồng đúng | Erased parameter cho phép dữ liệu trái type argument |
| `checkedList` | `add("A")` qua wrapper | Raw alias của wrapper `add(42)` bị từ chối |
| Mảng | `String[]` qua tham chiếu `Object[]` | Ghi Integer gây `ArrayStoreException` |
| Cast mảng | Runtime object thật `String[]` | Runtime object `Object[]` dù toàn String vẫn gây `ClassCastException` |
| Generic container mutable | Dùng API typed, không lộ backing | Raw alias hoặc mutation qua backing alias phá invariant |
| Null | Hợp đồng cho phép hoặc cấm rõ ràng | `Class.cast(null)` và `isInstance(null)` khác nhau |
| Empty container | Không phát sinh lỗi giả do không có phần tử | Kiểm tra quy tắc empty/vacuous truth; không nhầm thành bằng chứng mọi phần tử thuộc một `T` cụ thể |

**Chú ý:** một danh sách rỗng thỏa `stream().allMatch(String.class::isInstance)` do tính đúng rỗng (*vacuous truth*). Điều này không khôi phục được type argument `String` trên runtime class của list; nếu cần kiểm tra danh sách không rỗng, đặt thêm điều kiện `!list.isEmpty()`.

## 15. Reflection exceptions: kiểm tra đúng tầng

Ngoài trường hợp field/method generic bị ô nhiễm, reflection có các failure modes riêng.

### 15.1. `Field.set` với erased type không tương thích

Một field kiểu `List<String>` có erased type `List`. Nếu gọi:

```java
Field field = Document.class.getDeclaredField("tags");
// field.set(document, "not a list"); // IllegalArgumentException.
```

Reflection có quyền từ chối object **không phải `List`**. Nó không bắt buộc quét nội dung danh sách khi gán một object `List` hợp lệ.

### 15.2. `Method.invoke` và `InvocationTargetException`

Nếu phương thức phản chiếu tự ném `IllegalStateException` từ thân method, một lời gọi `invoke` có thể ném **`InvocationTargetException`**. Khi test, kiểm tra:

```java
try {
    method.invoke(target, arguments);
    throw new AssertionError("Expected target failure");
} catch (InvocationTargetException ex) {
    Throwable cause = ex.getCause();
    if (!(cause instanceof IllegalStateException)) {
        throw new AssertionError("Wrong target cause", cause);
    }
}
```

Đoạn này là **mẫu trong ngữ cảnh** có sẵn `method`, `target`, `arguments`, không phải chương trình độc lập. `InvocationTargetException` thuộc cách reflection **đóng gói ngoại lệ của code được gọi**, còn `ClassCastException` sau khi caller đọc dữ liệu sai generic contract là một tình huống khác.

Nếu tham số invoke không tương thích với **erased descriptor**, exception có thể được ném ngay từ `invoke` thay vì chạy vào method body.

### 15.3. Quyền truy cập và module system

`Field.getDeclaredField` không tự nghĩa là có quyền truy cập mọi private field. `IllegalAccessException`, `InaccessibleObjectException` hoặc chính sách module encapsulation có thể ngăn reflection tùy theo target và môi trường.

Để test **generic boundary** thay vì access control, fixture nên dùng declaration được truy cập hợp lệ, như trong chương trình trên. Nếu muốn kiểm tra module security/access control, tạo một nhóm test riêng; không diễn giải một `IllegalAccessException` là bằng chứng compiler/JVM đã bảo vệ `List<String>` ở mức phần tử.

## 16. Bất biến an toàn kiểu cần test được phát biểu thành lời

Giả sử thư viện tự cài `Store<T>` bằng `private Object[] slots`:

```java
class Store<T> {
    private Object[] slots = new Object[8];
    private int size;

    void add(T value) {
        slots[size++] = value;
    }

    T get(int index) {
        @SuppressWarnings("unchecked")
        T value = (T) slots[index];
        return value;
    }
}
```

Đây là snippet minh họa **chưa kiểm tra capacity/index**. Khi review bản hoàn chỉnh, invariant cần gồm:

1. `0 <= size <= slots.length`.
2. Mọi `slots[i]` thuộc vùng `0 <= i < size` đã được ghi qua các đường được kiểm soát theo `T`.
3. Storage không thoát ra ngoài dưới dạng alias có thể sửa trực tiếp.
4. Resize và các phương thức bulk update không bỏ qua kiểm tra kiểu hoặc làm hỏng ranh giới `size`.
5. Nếu cho phép null, quy tắc null được thực thi nhất quán; nếu không, chặn trước khi ghi.
6. Mọi caller phải tuân thủ hợp đồng typed, hoặc lớp phải có thêm runtime token/validator khi cần chống raw callers.
7. Nếu dùng giữa nhiều thread, cần cơ chế đồng bộ phù hợp; một invariant đúng trong single-thread code không tự chứng minh thread safety.

Đối với cast `(T) slots[index]`, một test chỉ đọc phần tử hợp lệ không đủ. Cần kiểm tra **mọi đường ghi có thể làm hỏng invariant**: raw alias, reflection, backing alias, `set`, `addAll`, deserialization và mutation cạnh tranh nếu API cho phép.

Nếu muốn bảo vệ ngay cả trước raw callers, có thể giữ một `Class<T>` token trong instance và kiểm tra `elementType.cast(value)` ở biên ghi. Điều này giúp chống những đối tượng runtime class sai, nhưng không tự xác thực nested generic type arguments như `List<String>`.

### Vì sao lỗi thường xuất hiện ở caller?

Với `T` không bound, erasure của `T` là `Object`. Một `get()` trả `T` có thể trở thành descriptor trả `Object` ở bytecode; caller cần `String` thì phải chuyển từ `Object` sang `String` theo kiểu tĩnh. Vì vậy `ClassCastException` thường xảy ra **khi caller sử dụng giá trị**, không nhất thiết trong `get` hoặc lúc ghi bằng raw type.

Khi test, phải buộc kết quả vào một biến/hoạt động thật sự yêu cầu kiểu mong muốn:

```java
String name = polluted.get(0); // Chạm kiểm tra kiểu String.
```

Nếu chỉ gọi `polluted.get(0)` rồi bỏ kết quả, có thể chưa quan sát được lỗi mà bài test nhằm chứng minh.

## 17. Cách sửa: chuyển từ “cast trước, lỗi sau” sang “validate ở biên”

Một adapter an toàn hơn cho input `Object`:

```java
static <T> List<T> validatedCopy(
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
```

Ưu điểm:

- `instanceof List<?>` kiểm tra cấu trúc ngoài.
- `Class<T>.cast` kiểm tra từng phần tử theo runtime class do caller cung cấp.
- `requireNonNull` diễn đạt null policy một cách chủ động.
- Copy từng phần tử sang `List<T>` mới giúp tránh alias cấu trúc với source sau khi kiểm tra.
- Không cần unchecked cast của cả `List<T>`.

Nhưng **chú ý giới hạn**: `List.copyOf` tạo kết quả unmodifiable về cấu trúc, không deep-copy object phần tử. Nếu nguồn mutable bị sửa **trong quá trình duyệt**, code không tự cung cấp snapshot atomic; cần đồng bộ hoặc hợp đồng concurrency phù hợp. `Class<T>` cũng chỉ kiểm tra một class cụ thể chứ không xác minh `List<Map<String,Integer>>` lồng nhau.

Bộ test cho adapter nên thử đủ: input không phải list, thiếu token, list đúng, list sai phần tử, list chứa null, list rỗng, source mutate sau copy, và các trường hợp concurrent mutation nếu API tuyên bố hỗ trợ.

## 18. Dùng test framework chuyên dụng mà không đánh mất ý nghĩa bài kiểm thử

Chương trình thuần JDK phía trên đã giúp hiểu cơ chế, không cần dependency. Trong codebase dùng **JUnit 5**, có thể chuyển helper thành:

```java
// Snippet JUnit 5, cần dependency org.junit.jupiter:junit-jupiter:
import static org.junit.jupiter.api.Assertions.*;

@Test
void rawAliasPollutionIsDetectedAtRead() {
    List<String> typed = new ArrayList<>();
    List raw = typed;
    raw.add(42);

    assertThrows(ClassCastException.class, () -> {
        String value = typed.get(0);
        System.out.println(value);
    });
}
```

Cần import `org.junit.jupiter.api.Test` và cài JUnit Jupiter trong project. Snippet này là **mẫu đưa vào test class có dependency phù hợp**, không thuộc chương trình thuần JDK ở mục 11.

Lợi ích của framework: test cases độc lập, có tên rõ, dễ chạy song song/chọn lọc, và báo lỗi theo từng method. Nhưng một `assertThrows` cũng không tự bảo đảm proof: vẫn phải cho **action cụ thể** chạm đúng cast hoặc biên kiểu, và kiểm tra state sau exception khi cần.

Với dự án có code coverage, hãy dùng các test boundary để bảo đảm đúng những đường mà generic type checks bị bỏ qua; đừng xem tỉ lệ coverage cao là bằng chứng tự thân rằng API type-safe.

## 19. Những lỗi thiết kế bài kiểm thử thường gặp

**Lỗi 1 — “Cast `List<String>` thành công nên đã kiểm tra kiểu phần tử.”** Không. Unchecked cast có thể chỉ xác nhận cấu trúc ngoài; đọc typed mới phát hiện sai.

**Lỗi 2 — “Raw type viết được nên Java không có type safety.”** Không. Java vẫn có type system mạnh tại code typed; raw types là một vùng tương thích cũ cần kiểm soát.

**Lỗi 3 — “Reflection bỏ qua toàn bộ mọi kiểu.”** Không. Reflection vẫn kiểm tra erased field/parameter types, truy cập và các điều kiện runtime khác; nó không xác thực tự động mọi generic type arguments.

**Lỗi 4 — “Field.getGenericType() trả `List<String>` nên Field.set kiểm tra từng phần tử.”** Không. Metadata của khai báo và validator dữ liệu là hai việc khác nhau.

**Lỗi 5 — “Method.invoke bị lỗi ở đâu cũng thành ClassCastException.”** Không. Có thể là `IllegalArgumentException` ở biên invoke, `InvocationTargetException` khi target method ném lỗi, hoặc `ClassCastException` khi caller đọc dữ liệu ô nhiễm về sau.

**Lỗi 6 — “`Class.cast(null)` luôn ném.”** Không. Nó trả `null`; null policy phải kiểm tra riêng.

**Lỗi 7 — “CheckedList bảo vệ cả backing alias.”** Không. Nó bảo vệ các thao tác qua wrapper, không ngăn mã khác sửa trực tiếp backing list.

**Lỗi 8 — “Mảng `Object[]` có toàn String thì cast được sang `String[]`.”** Không. Runtime class của array mới quyết định phép cast.

**Lỗi 9 — “`ArrayStoreException` và `ClassCastException` là một.”** Không. Một bên thường xảy ra khi ghi phần tử mảng sai component type; bên kia khi cast tham chiếu không phù hợp.

**Lỗi 10 — “Test pass nếu bắt được bất cứ Exception nào.”** Sai. Cần đúng exception type và fail nếu không ném.

**Lỗi 11 — “Chỉ cần test input đúng.”** Không. Ranh giới raw/reflection/cast quan trọng chính ở hành vi với input sai hoặc alias không đáng tin.

**Lỗi 12 — “Warning được suppress nghĩa là an toàn.”** Không. `@SuppressWarnings` chỉ thay đổi diagnostics; không tạo runtime checks.

**Lỗi 13 — “List rỗng qua allMatch chứng minh class T cụ thể.”** Không. Điều kiện đúng rỗng không tạo ra type token runtime.

**Lỗi 14 — “Test không ném exception khi bỏ kết quả `get()` là chứng cứ an toàn.”** Không. Có thể chưa xảy ra cast sang type argument cụ thể ở caller.

## 20. Checklist cho code review và CI

Một nhóm kiểm thử ranh giới generics có thể dùng checklist sau:

1. **Liệt kê mọi trust boundary:** raw, reflection, unchecked cast, Object input, native/deserialization, array/varargs.
2. **Với mỗi boundary, có positive + negative case không?** Ghi dữ liệu đúng thành công và sai bị xử lý theo đúng hợp đồng.
3. **Có negative compilation tests?** Những lời gọi sai generic type phải bị compiler từ chối.
4. **Có bật `-Xlint:unchecked -Xlint:rawtypes`?** Cảnh báo bất ngờ trong source chính cần được xem xét.
5. **Có kiểm tra erased descriptor?** Với reflection, phân biệt `getType/getGenericType`, `getParameterTypes/getGenericParameterTypes`.
6. **Exception kỳ vọng đúng lớp chưa?** Không bắt rộng rồi pass; với `InvocationTargetException` kiểm tra cause.
7. **Có ép typed read thật?** Một bài test heap pollution phải buộc compiler/runtime kiểm tra kiểu mong muốn tại điểm tiêu thụ.
8. **Có thử runtime token/validator?** `Class.cast`, null, wrong class và nested data.
9. **Có kiểm tra state sau thất bại?** Wrapper hoặc adapter đã thay đổi container trước khi từ chối hay chưa?
10. **Có kiểm tra alias/mutation?** Backing list private không lộ ra, raw caller có thể phá invariant hay không, source có thể bị sửa sau validation không?
11. **Arrays được thử cả cast và store?** Phân biệt `ClassCastException` với `ArrayStoreException`.
12. **Có tránh unchecked casts không cần thiết?** Ưu tiên `List<?>`, typed copy, token, hoặc API generic chuẩn.
13. **Có tách raw-fixture khỏi production code?** Không đặt `@SuppressWarnings` quá rộng để che các warning mới.
14. **Có chạy trên phiên bản Java mục tiêu?** Chẳng hạn dùng `javac --release 17` khi yêu cầu tương thích Java 17.
15. **Có xác minh cả hành vi và tài liệu?** Javadoc phải nêu null policy, loại exception, ownership, mutability, và lúc nào validation diễn ra.

## 21. Kết luận

Kiểm thử raw type, reflection và ép kiểu là cách nhìn rõ **ranh giới của bảo đảm compile-time trong Java Generics**. Mã typed thông thường được compiler bảo vệ; raw aliases và unchecked casts có thể phá hợp đồng; reflection thường kiểm tra **kiểu đã xóa** nhưng không kiểm tra từng generic type argument; các container và array có runtime guards khác nhau.

Bộ test tốt phải chứng minh ba điều: **compiler chặn lời gọi không hợp lệ ở nơi có đủ thông tin kiểu**, **runtime phát hiện hoặc không phát hiện sai kiểu tại đúng ranh giới theo thiết kế**, và **API có cách ngăn dữ liệu chưa đáng tin lan sang vùng typed**, chẳng hạn `Class<T>.cast`, validated copy hoặc wrapper có runtime checks. Quan trọng hơn cả, mỗi unchecked operation phải đi cùng một bất biến an toàn có thể phát biểu và kiểm thử, thay vì chỉ được che cảnh báo.