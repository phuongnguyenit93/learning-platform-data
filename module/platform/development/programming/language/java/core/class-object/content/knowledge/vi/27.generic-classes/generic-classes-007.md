# Nhận diện raw type, cảnh báo không an toàn và xóa kiểu trong Java

> **Module:** Java Core — class/object  
> **Nhóm kiến thức:** Lớp generic  
> **Chủ đề:** Nhận diện raw type, cảnh báo không an toàn và xóa kiểu  
> **Phiên bản:** Java 17+. Các ví dụ chạy độc lập không cần bật tính năng preview.

## 1. Bài toán: vì sao viết generic mà vẫn có lỗi ép kiểu?

Java generics giúp các API tái sử dụng với nhiều kiểu dữ liệu trong khi vẫn được compiler kiểm tra quan hệ kiểu.

Ví dụ:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
~~~

`Box<String>` là hộp được compiler hiểu là giữ String. `Box<Integer>` là hộp giữ Integer. Tuy nhiên Java duy trì **raw types** để tương thích với mã cũ:

~~~java
Box raw = new Box("hello");
~~~

Khi dùng raw reference, compiler mất thông tin kiểu `T` trong những thao tác đi qua nó. Ví dụ một raw reference có thể đưa Integer vào một object vốn được biến khác khai báo `Box<String>`. Lúc đọc lại dưới kiểu String, chương trình có thể ném `ClassCastException`.

Điều đó dẫn tới ba khái niệm cần phân biệt:

- **Raw type:** tên của generic class/interface được dùng mà **không truyền type arguments** trong ngữ cảnh raw-type semantics, chẳng hạn `List` thay vì `List<String>`.
- **Unchecked warning:** compiler không đủ bằng chứng rằng một phép gọi, chuyển đổi hoặc cast generic sẽ duy trì type safety.
- **Type erasure:** cơ chế Java compiler xóa phần lớn type-parameter information khỏi runtime signatures, thay type variables bằng bounds/Object, đồng thời có thể chèn casts và tạo bridge methods.

**Type erasure xảy ra cả trong chương trình viết generics đúng chuẩn và không có warnings.** Raw type là một lựa chọn source-level làm suy yếu kiểm tra kiểu; không phải “điều tất yếu vì JVM dùng erasure”.

## 2. Nhận diện generic declaration, parameterized type và raw type

Xét:

~~~java
interface Repository<ID, ENTITY> {
    ENTITY find(ID id);
}
~~~

Đây là **interface fragment**. Hai type parameters là `ID` và `ENTITY`.

| Cú pháp | Phân loại | Ý nghĩa |
| --- | --- | --- |
| `Repository<ID,ENTITY>` trong declaration | Generic declaration | Định nghĩa hai type parameters |
| `Repository<String,User>` | Parameterized type | Chọn String cho ID, User cho ENTITY |
| `Repository<?,?>` | Parameterized type với wildcards | Biết đây là generic repository nhưng type arguments chưa rõ |
| `Repository` | Raw type | Bỏ các type arguments của generic declaration |
| `List<Object>` | Parameterized type | Exact element type là Object |
| `List<?>` | Parameterized type | Một element type chưa biết |
| `List` | Raw type | Bỏ type argument E |
| `String` | Ordinary non-generic type | Không phải raw |

### 2.1. Ký tự `T` không đồng nghĩa raw

Trong body `class Box<T>`, `T` là **type variable hợp lệ**. Compiler biết các occurrences của T phải nhất quán trong field, getter và setter. Nó không phải raw type.

### 2.2. Diamond operator không phải raw type

~~~java
List<String> names = new ArrayList<>();
~~~

`<>` là toán tử **diamond**, cho phép compiler infer type arguments từ context. Declaration này giữ generic type safety.

So sánh:

~~~java
List<String> names = new ArrayList(); // Raw construction, warning.
~~~

Ở vế phải không có diamond và type arguments, do đó `new ArrayList()` là raw construction. Compiler có thể chấp nhận qua unchecked conversion, nhưng không nên viết như thế trong code mới.

### 2.3. `var` cũng không tự biến generic thành raw

~~~java
var names = new ArrayList<String>();
~~~

Compiler suy ra `ArrayList<String>`. Còn:

~~~java
var names = new ArrayList<>();
~~~

khi thiếu target type context, element type thường được suy ra Object. Đây là **vấn đề inference**, không phải raw `ArrayList`.

## 3. Những chỗ raw type thường xuất hiện

Raw usage có thể nằm trong:

~~~java
List values;                   // Biến raw.
Set flags = new HashSet();     // Biến và constructor raw.
Map cache;                     // Field/local raw nếu viết trong class/method.
Class type = String.class;     // Raw Class.
Comparable candidate = "A";    // Raw Comparable.
Box box = new Box("A");        // Raw Box.
~~~

Các đoạn này là **fragments**, cần imports và declaration phù hợp.

Các tương ứng typed:

~~~java
List<String> values;
Set<String> flags = new HashSet<>();
Map<String, Integer> cache;
Class<?> type = String.class;
Comparable<String> candidate = "A";
Box<String> box = new Box<>("A");
~~~

### 3.1. Public raw API có tác động dây chuyền

Một method legacy:

~~~java
public List fetchAll()
~~~

không nói element type. Mọi caller phải đoán, cast hoặc truyền tiếp raw List. Nếu được quyền sửa API và data thực sự chỉ gồm User, trả `List<User>` sẽ tốt hơn vì compiler bảo vệ callers.

### 3.2. Raw superclass hoặc interface

~~~java
class LegacyComparator implements Comparable {
    @Override
    public int compareTo(Object other) {
        return 0;
    }
}
~~~

Đây là fragment. `Comparable` thực chất là `Comparable<T>`. Nếu class chỉ so với những LegacyComparator khác, có thể viết `implements Comparable<LegacyComparator>` với `compareTo(LegacyComparator other)` để type contract rõ ràng hơn.

### 3.3. Trường hợp Class literal

`String.class` và `List.class` là hợp lệ; không có cú pháp `List<String>.class` để tạo Class object reified theo element type. Nhưng việc reflection dùng `List.class` **không biện minh cho API khắp nơi nhận raw List**. Khi cần type-agnostic Class, dùng `Class<?>`; khi cần generic nested types, cân nhắc Type/ParameterizedType hoặc type descriptor.

## 4. Phân biệt `rawtypes` và `unchecked`

Đây là hai nhóm diagnostics có liên quan nhưng không giống nhau.

### 4.1. `rawtypes`: bỏ type arguments

Ví dụ:

~~~java
List raw = new ArrayList();
~~~

Bật lint:

~~~bash
javac -Xlint:rawtypes SomeFile.java
~~~

Compiler có thể chỉ ra các chỗ dùng tên `List`/`ArrayList` dạng raw.

### 4.2. `unchecked`: operation không thể được kiểm chứng đầy đủ

~~~java
List raw = new ArrayList();
raw.add("A");
List<String> names = raw;
~~~

Có thể gặp:

- **Unchecked call:** `raw.add("A")` được gọi qua raw receiver.
- **Unchecked conversion:** `List<String> names = raw` chuyển raw List sang parameterized type mà compiler không thể kiểm tra mọi element.

Những warnings này không tự tạo runtime exception tại thời điểm compile. Java program có thể vẫn chạy đúng với một bộ dữ liệu tương thích và thất bại khi dữ liệu khác được đưa vào.

### 4.3. Cờ compiler nên biết

~~~bash
javac -Xlint:rawtypes,unchecked SomeFile.java
javac -Xlint:all SomeFile.java
javac -Xlint:rawtypes,unchecked -Werror SomeFile.java
~~~

`-Werror` yêu cầu build thất bại nếu có warnings. Phù hợp cho module đã dọn sạch, nhưng dự án legacy thường nên kiểm kê và sửa warnings theo giai đoạn.

### 4.4. Không ghi raw diagnostics như stdout cố định

Compiler diagnostic text và line numbers có thể khác theo JDK, flags và source positions. Trong bài này, chỉ **stdout từ `java Program`** được ghi chính xác; những lint diagnostics sẽ được mô tả theo loại, không khẳng định từng dòng của compiler luôn giống nhau.

## 5. Chương trình hoàn chỉnh 1 — raw type gây lỗi cast muộn

Tạo tệp **`RawBoxFailureDemo.java`**:

~~~java
public class RawBoxFailureDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void legacyWrite(Box box) {
        box.set(42);
    }

    public static void main(String[] args) {
        Box<String> typed = new Box<>("Lan");
        System.out.println("Before = " + typed.get());

        legacyWrite(typed);

        try {
            String value = typed.get();
            System.out.println("After = " + value);
        } catch (ClassCastException ex) {
            System.out.println("Delayed ClassCastException");
        }

        System.out.println("Runtime class = "
                + Box.class.getSimpleName());
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 RawBoxFailureDemo.java
java RawBoxFailureDemo
~~~

**Stdout chính xác:**

~~~text
Before = Lan
Delayed ClassCastException
Runtime class = Box
~~~

### 5.1. Compiler tin `Box<String>` giữ String

Ở biến `typed`, compiler biết `get()` trả String theo source-level generic type. Nhưng method `legacyWrite` lại nhận raw `Box` rồi gọi `set(42)`, phá relationship T=String.

### 5.2. Vì sao set không ném lỗi ngay?

Erased setter của unbounded Box nhận Object. Integer là Object reference hợp lệ. Khi đọc vào String variable, compiler-inserted cast mới kiểm tra runtime object và phát hiện Integer không phải String.

### 5.3. `@SuppressWarnings` không chữa lỗi

Annotation chỉ ẩn warnings trong phạm vi method legacyWrite. Việc dùng suppression ở đây **cố ý minh họa code nguy hiểm**. Trong production, không nên giữ một helper phá type invariant như thế; hãy typed API hoặc validate data.

### 5.4. Thuật ngữ “heap pollution”

`Box<String>` lúc này có một field chứa Integer. Object và type argument bị lệch nhau do raw access, là ví dụ của **heap pollution**. Lỗi có thể xuất hiện cách xa nơi dữ liệu sai bị chèn.

## 6. Chương trình hoàn chỉnh 2 — nhìn compiler warnings

Tạo tệp **`RawWarningExample.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawWarningExample {
    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add("A");
        List<String> names = raw;

        System.out.println("First = " + names.get(0));
    }
}
~~~

Biên dịch và chạy bình thường:

~~~bash
javac -encoding UTF-8 RawWarningExample.java
java RawWarningExample
~~~

Chạy **riêng** lệnh này để xem diagnostics được phân loại:

~~~bash
javac -encoding UTF-8 -Xlint:rawtypes,unchecked RawWarningExample.java
~~~

**Stdout của chương trình:**

~~~text
First = A
~~~

### 6.1. Những vị trí lint sẽ cảnh báo

Có raw `List` và raw construction `ArrayList()`; gọi `raw.add("A")` có unchecked call; gán raw List sang `List<String>` có unchecked conversion.

### 6.2. Vì sao execution này không ném lỗi?

List hiện chỉ chứa String "A", nên compiler-inserted cast khi đọc String thành công. Nhưng nếu raw List bị thêm Integer, program có thể ném ClassCastException. Warning là **nguy cơ thiếu bảo đảm**, không phải chắc chắn lỗi trên từng input.

### 6.3. Không dùng `-Werror` rồi kỳ vọng chạy chương trình

Nếu dùng `-Werror` khi vẫn có warnings, build có thể thất bại. Đó là chủ đích của quality gate; chương trình chạy sau đó chỉ khi có class file hợp lệ từ lần biên dịch thành công.

## 7. Raw List, List<Object> và List<?> không tương đương

| Thuộc tính | `List` | `List<Object>` | `List<?>` |
| --- | --- | --- | --- |
| Loại khai báo | Raw | Parameterized | Parameterized với wildcard |
| `get(0)` được xem là | Object | Object | Object |
| `add("A")` | Có thể compile với unchecked warning | Compile được | Không compile |
| `add(42)` | Có thể compile với unchecked warning | Compile được | Không compile |
| `add(null)` | Có thể compile | Compile được nếu API cho phép | Compile được nếu API cho phép |
| Nhận reference từ List<String>? | Có, thông qua raw | Không vì invariance | Có |
| Dùng trong code mới | Tránh | Nếu contract là arbitrary Object | Nếu element type chưa biết |

### 7.1. Vì sao List<?> an toàn hơn raw?

`List<?>` thực sự có một type argument, nhưng là unknown. Compiler không cho thêm arbitrary non-null element vì actual element type có thể khác. Raw List bỏ qua ràng buộc ấy.

### 7.2. Vì sao List<?> không đồng nghĩa immutable?

Nó vẫn có thể trỏ đến mutable ArrayList. Phương thức `clear()` hoặc thao tác remove hợp lệ vẫn có thể làm List thay đổi; wildcard chủ yếu giới hạn thao tác không type-safe như add một String tùy ý.

### 7.3. Vì sao List<Object> không nhận List<String>?

Java generics invariant. Nếu một List<String> được gán sang List<Object>, người ta có thể add Integer qua alias List<Object>, làm List<String> chứa sai type. Compiler ngăn tình huống này.

### 7.4. Wildcards khác named type parameter

Wildcard biểu diễn một unknown element type; một generic method `<T> void copy(List<? extends T>, List<? super T>)` cho compiler biết quan hệ giữa producer/consumer. Không nên chuyển sang raw khi wildcard gây khó: có thể cần một helper `<T>` để capture type.

## 8. Chương trình hoàn chỉnh 3 — dùng wildcard an toàn

Tệp **`RawVsWildcardDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawVsWildcardDemo {
    static int count(List<?> values) {
        return values.size();
    }

    static String firstText(List<?> values) {
        return String.valueOf(values.get(0));
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "Mai"));
        List<?> unknown = names;

        System.out.println("Count = " + count(unknown));
        System.out.println("First = " + firstText(unknown));
        System.out.println("Same list = " + (unknown == names));

        names.add("An");

        System.out.println("After mutation = " + unknown);

        // unknown.add("X"); // Cố ý không biên dịch.
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 RawVsWildcardDemo.java
java RawVsWildcardDemo
~~~

**Stdout chính xác:**

~~~text
Count = 2
First = Lan
Same list = true
After mutation = [Lan, Mai, An]
~~~

### 8.1. List<?> không copy List

`unknown` và `names` là references đến cùng ArrayList; thay state qua names được nhìn thấy qua unknown.

### 8.2. Vì sao không gán `String first = unknown.get(0)`?

Compiler chỉ biết element type unknown, nên method get trả một giá trị đọc an toàn như Object. Nếu muốn String thật sự, phải kiểm tra/cast ở boundary dựa trên input invariant.

### 8.3. Đừng dùng raw type để bypass compiler

Việc `unknown.add("X")` không compile chính là type safety. Chuyển unknown thành raw List chỉ để add sẽ phá contract thay vì giải quyết thiết kế.

## 9. Unchecked conversion không duyệt tất cả phần tử

Xem:

~~~java
List raw = obtainLegacyList();
List<String> names = raw;
~~~

Đây là **fragment**, `obtainLegacyList` là một API legacy giả định có sẵn.

Compiler có thể cảnh báo unchecked conversion, nhưng **không chèn một vòng lặp tự động kiểm tra mọi element là String**. Erasure chỉ cho phép runtime biết object là List. Dữ liệu bên trong có thể sai.

Tương tự:

~~~java
List<String> names = (List<String>) raw;
~~~

cast không kiểm hết list contents. Nếu Object là List chứa Integer, việc ép sang List<String> có thể “thành công” ở thời điểm cast, nhưng đọc element vào String sau đó lại gây ClassCastException.

### 9.1. Một unchecked cast khác checked cast

`String.class.cast(value)` thật sự kiểm tra value là String runtime class, còn cast một List<?> sang List<String> không kiểm chứng generic element argument bị erasure.

### 9.2. Không dùng double cast để “xóa warning”

`(List<String>)(List<?>) source` có thể dời/bớt diagnostics trong một số source patterns, nhưng không bổ sung runtime validation. Câu hỏi thiết yếu vẫn là: **ai bảo đảm tất cả elements đúng String?**

### 9.3. Không mọi hỗn hợp Objects đều là pollution

`List<Object>` chứa String và Integer là hợp lệ theo contract. Heap pollution là mismatch với một **parameterized type được cam kết**, không phải cứ có nhiều runtime classes trong một collection là sai.

## 10. Chương trình hoàn chỉnh 4 — kiểm tra dữ liệu rồi trả collection typed

Tệp **`CheckedGenericBoundaryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CheckedGenericBoundaryDemo {
    static <T> List<T> checkedCopy(
            List<?> input, Class<T> type) {
        List<T> output = new ArrayList<>();

        for (Object item : input) {
            output.add(type.cast(item));
        }

        return List.copyOf(output);
    }

    public static void main(String[] args) {
        List<?> good = List.of("Lan", "Mai");
        List<String> names = checkedCopy(good, String.class);

        System.out.println("Names = " + names);

        try {
            List<?> bad = List.of("Lan", 7);
            checkedCopy(bad, String.class);
        } catch (ClassCastException ex) {
            System.out.println("Invalid element rejected");
        }

        System.out.println("Original count = " + good.size());

        try {
            names.add("An");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Result unmodifiable");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CheckedGenericBoundaryDemo.java
java CheckedGenericBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
Names = [Lan, Mai]
Invalid element rejected
Original count = 2
Result unmodifiable
~~~

### 10.1. Type safety của boundary đến từ đâu?

`Class<T>.cast` kiểm tra từng element tại runtime. Chỉ khi tất cả đều phù hợp, List<T> mới được xây. Không có unchecked cast nguyên List.

### 10.2. Vì sao dùng List.copyOf?

Result trở thành unmodifiable structural snapshot; nó không phụ thuộc vào underlying input List sau đó. Đây là ownership/mutability policy, **khác với** nhiệm vụ kiểm tra element type.

### 10.3. Null contract của demo

`Class.cast(null)` có thể trả null nhưng `List.copyOf` từ chối null elements. Trong demo input `List.of` không chứa null. Production code phải định nghĩa rõ liệu null elements được chấp nhận hay không.

### 10.4. Class<T> không reify nested generic arguments

Có `String.class` nhưng không có `List<String>.class`. Nếu mỗi element cần kiểu `List<Integer>`, cần kiểm tra List runtime type và elements ở tầng trong, hoặc dùng type descriptor/framework có validation phù hợp.

## 11. Type erasure: compiler làm gì với T?

Java generics chủ yếu có **erased runtime representation**. Với:

~~~java
class Holder<T> {
    private T value;

    T get() {
        return value;
    }
}
~~~

có thể hình dung erased runtime signatures tương đương:

~~~java
class Holder {
    private Object value;

    Object get() {
        return value;
    }
}
~~~

**Hai đoạn chỉ để minh họa cơ chế**, không phải hai class cùng có thể khai báo trong một file. Compiler còn có thể lưu generic metadata, chèn checkcasts hoặc sinh bridge methods.

### 11.1. Erasure của unbounded parameter

`<T>` không có bound cụ thể nên T erases thành Object.

### 11.2. Erasure của bounded parameter

`<N extends Number>` có erasure Number. Một field `N number` sẽ có runtime reflection Field.getType() là Number.

### 11.3. Multiple bounds

Với `<T extends Number & Comparable<T>>`, first bound Number quyết định erasure của T. Khi class bound không có và bound đầu là interface, interface đầu đó có thể là erasure.

### 11.4. Generic method erasure

`static <T> T identity(T input)` thường có erased parameters/return Object khi T unbounded. Nhưng compiler vẫn đảm bảo call `String s = identity("A")` typed đúng ở source.

### 11.5. Erasure không bắt buộc xóa toàn bộ metadata

Compiler có thể ghi generic `Signature` attributes cho classes/fields/methods. Reflection như `getTypeParameters` hoặc `getGenericParameterTypes` có thể đọc declaration metadata, dù runtime không có class specialization riêng cho Box<String>.

## 12. Chương trình hoàn chỉnh 5 — nhìn erasure bằng reflection

Tệp **`TypeErasureReflectionDemo.java`**:

~~~java
import java.lang.reflect.Field;
import java.util.Arrays;

public class TypeErasureReflectionDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class NumberBox<N extends Number> {
        private final N number;

        NumberBox(N number) {
            this.number = number;
        }

        N get() {
            return number;
        }
    }

    public static void main(String[] args) throws Exception {
        Box<String> text = new Box<>("Java");
        Box<Integer> count = new Box<>(17);

        Field valueField = Box.class.getDeclaredField("value");
        Field numberField =
                NumberBox.class.getDeclaredField("number");

        System.out.println("Same runtime class = "
                + (text.getClass() == count.getClass()));
        System.out.println("Box field = "
                + valueField.getType().getSimpleName());
        System.out.println("NumberBox field = "
                + numberField.getType().getSimpleName());
        System.out.println("Type parameters = "
                + Arrays.toString(Box.class.getTypeParameters()));
        System.out.println("Text = " + text.get());
        System.out.println("Count = " + count.get());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 TypeErasureReflectionDemo.java
java TypeErasureReflectionDemo
~~~

**Stdout chính xác:**

~~~text
Same runtime class = true
Box field = Object
NumberBox field = Number
Type parameters = [T]
Text = Java
Count = 17
~~~

### 12.1. Tại sao hai Box objects có cùng getClass?

Cả `new Box<String>` và `new Box<Integer>` sử dụng runtime class Box; type arguments không tạo hai runtime Class objects riêng.

### 12.2. Tại sao reflection biết T?

`Box.class.getTypeParameters()` đọc **generic declaration metadata**. Nó cho biết Box khai báo T, không phải T của object text = String trong tất cả ngữ cảnh runtime.

### 12.3. Khi nào reflection có thể tìm được concrete argument?

Một non-generic subclass `class StringBox extends Box<String>` có thể lưu generic superclass signature phản ánh String. Đó là metadata ở subclass declaration, không phải Box<T> tự reify type argument ở từng arbitrary Box instance.

## 13. Erasure và cast do compiler bổ sung

Trong code typed:

~~~java
Box<String> text = new Box<>("Core");
String value = text.get();
~~~

Erased `get()` có thể trả Object. Compiler chèn checkcast String khi cần để đảm bảo expression được sử dụng như String.

Điều này giải thích lỗi trong RawBoxFailureDemo: raw setter chèn Integer nhưng typed getter/caller cuối cùng đòi String.

### 13.1. Không phải mọi source-level get đều gây checkcast rõ trong bytecode

Compiler và JIT có thể tối ưu. Điều nên dựa vào là Java runtime phải bảo đảm type check ở nơi conversion thực sự cần; kết quả sai có thể ném ClassCastException.

### 13.2. Null và cast

Cast null sang String trả null, không ném ClassCastException. Null-related NPE có cơ chế khác với heap pollution.

### 13.3. Type erasure không cho phép compiler bỏ hết type checks

Typed Java source vẫn có compile-time constraints nghiêm ngặt. Chỉ những operations đi qua raw/unchecked/reflective unsafe paths mới làm một số guarantees không còn được chứng minh.

## 14. Bridge method giữ đúng đa hình khi xóa kiểu

Một superclass generic:

~~~java
class Parent<T> {
    T get() {
        return null;
    }
}
~~~

và subtype chuyên biệt hóa:

~~~java
class Child extends Parent<String> {
    @Override
    String get() {
        return "Core";
    }
}
~~~

Erased Parent.get trả Object, Child.get trả String. Compiler có thể sinh **bridge method** ở Child để các lời gọi polymorphic qua erased Parent signature vẫn dispatch tới Child override.

### 14.1. Bridge không phải dấu hiệu lỗi raw

Bridge thường có trong generic code hoàn toàn hợp lệ, không có unchecked warnings. Nó là cơ chế tương thích giữa generic overriding semantics và JVM method descriptors.

### 14.2. Reflection có thể thấy bridge

`java.lang.reflect.Method.isBridge()` phân biệt bridge methods do compiler tạo. Khi viết reflection scanners, cần tránh coi bridge như một method business trùng lặp độc lập.

## 15. Chương trình hoàn chỉnh 6 — tìm bridge bằng reflection

Tệp **`GenericBridgeMethodDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;

public class GenericBridgeMethodDemo {
    static class Parent<T> {
        T get() {
            return null;
        }
    }

    static final class Child extends Parent<String> {
        @Override
        String get() {
            return "Core";
        }
    }

    public static void main(String[] args) throws Exception {
        Parent<String> source = new Child();

        System.out.println("Value = " + source.get());
        System.out.println("Erased return = "
                + Parent.class.getDeclaredMethod("get")
                        .getReturnType().getSimpleName());

        boolean bridge =
                Arrays.stream(Child.class.getDeclaredMethods())
                        .anyMatch(Method::isBridge);

        System.out.println("Has bridge = " + bridge);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericBridgeMethodDemo.java
java GenericBridgeMethodDemo
~~~

**Stdout chính xác:**

~~~text
Value = Core
Erased return = Object
Has bridge = true
~~~

### 15.1. Tại sao get() trả Core qua Parent<String>?

Object thực sự là Child, override được dispatch qua bridge để method phù hợp với erased Parent.get signature.

### 15.2. Không nên hard-code synthetic method names

Compiler tạo bridge theo rules, nhưng tên và thứ tự methods trong reflection scan không phải một domain API ổn định. Dùng `Method.isBridge()` khi cần lọc.

## 16. Same erasure gây xung đột method signatures

Hai overload sau:

~~~java
void process(List<String> names) {
}

void process(List<Integer> values) {
}
~~~

đều erase parameter thành List, nên **không thể đặt đồng thời trong cùng class**. Compiler báo name clash/same erasure.

### 16.1. Cách sửa đúng

Nếu logic khác nhau, đặt tên methods khác:

~~~java
void processNames(List<String> names) {
}

void processCounts(List<Integer> values) {
}
~~~

Nếu logic giống nhau cho mọi type:

~~~java
static <T> int count(List<T> values) {
    return values.size();
}
~~~

Không thêm unchecked casts để ép hai overloads cùng tồn tại; source signatures đã xung đột.

### 16.2. Một số overloads generic vẫn hợp lệ

`process(List<String>)` và `process(Set<String>)` erase thành List và Set, là parameter types khác nhau, nên có thể overload nếu rules khác được thỏa.

## 17. Chương trình hoàn chỉnh 7 — generic metadata ở method declaration

Tệp **`GenericSignatureDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.util.List;

public class GenericSignatureDemo {
    static void processNames(List<String> names) {
        System.out.println("Names = " + names.size());
    }

    static void processCounts(List<Integer> numbers) {
        System.out.println("Numbers = " + numbers.size());
    }

    public static void main(String[] args) throws Exception {
        processNames(List.of("A", "B"));
        processCounts(List.of(1, 2, 3));

        Method method = GenericSignatureDemo.class
                .getDeclaredMethod("processNames", List.class);

        System.out.println("Erased type = "
                + method.getParameterTypes()[0].getSimpleName());
        System.out.println("Generic type = "
                + method.getGenericParameterTypes()[0].getTypeName());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 GenericSignatureDemo.java
java GenericSignatureDemo
~~~

**Stdout chính xác trên JDK 17:**

~~~text
Names = 2
Numbers = 3
Erased type = List
Generic type = java.util.List<java.lang.String>
~~~

### 17.1. Vì sao getGenericParameterTypes đọc được String?

Nó đọc declaration signature metadata, không có nghĩa JVM đã tạo riêng một runtime class List<String>. `getParameterTypes()` vẫn cho erased type List.

### 17.2. Vì sao reflection metadata không cho phép overload same erasure?

Compiler kiểm tra Java method signatures và JVM descriptors; việc generic metadata có String/Integer khác nhau không tạo hai runtime parameter classes độc lập.

## 18. Reifiable và non-reifiable type: hệ quả của erasure

Một **reifiable type** là kiểu đủ thông tin runtime để kiểm tra theo Java rules.

Một số ví dụ:

- `String`, `String[]` — reifiable.
- Raw `List` — reifiable.
- `List<?>` — reifiable vì tất cả type arguments là unbounded wildcard.
- `List<String>` — **không reifiable**.
- `T` (generic type variable thông thường) — không reifiable.

### 18.1. `instanceof List<String>` không compile

~~~java
Object value = new ArrayList<String>();

if (value instanceof List<String>) {
}
~~~

Mã này **cố ý không biên dịch**. Runtime check không thể chứng minh element type String từ một arbitrary List instance.

### 18.2. `instanceof List<?>` compile

~~~java
Object value = new ArrayList<String>();

if (value instanceof List<?> list) {
    System.out.println(list.size());
}
~~~

Đây là Java 17 fragment hợp lệ với instanceof pattern. Nó kiểm tra object implements List, **không** duyệt elements để kiểm tra String.

### 18.3. Không thể viết `T.class`

~~~java
class Factory<T> {
    Class<T> type() {
        return T.class; // Cố ý không biên dịch.
    }
}
~~~

T không phải một runtime Class literal. Nếu cần validation, nhận `Class<T>` từ caller hoặc một type descriptor.

### 18.4. Không thể `new T()` chỉ từ generic type parameter

Type erasure không cung cấp constructor tùy ý cho unknown T. Dùng `Supplier<? extends T>`, typed factory hoặc reflection có kiểm soát.

### 18.5. Không thể tạo generic array trực tiếp

`new T[10]` và `new List<String>[10]` đều không hợp lệ; Java arrays reify component type trong khi generic parameterized arguments như List<String> không reifiable.

## 19. Array covariance đối lập generic invariance

Arrays covariant:

~~~java
String[] words = {"A"};
Object[] items = words;
~~~

Nhưng lưu Integer qua items gây **ArrayStoreException**, vì runtime array biết component type String.

Generics invariant:

~~~java
List<String> words = new ArrayList<>();
List<Object> objects = words; // Cố ý không biên dịch.
~~~

Vì generic element type argument không reified giống runtime array component, compiler từ chối assignment làm rủi ro thêm arbitrary Objects vào List<String>.

### 19.1. ArrayStoreException khác ClassCastException

ArrayStoreException nổ tại runtime **array store**, khi object không phù hợp array component runtime type. ClassCastException nổ khi cast một reference không hợp lệ, ví dụ String read từ một raw-corrupted List.

### 19.2. Wildcard không là mảng typed mới

`List<?>` giúp đọc containers với unknown type argument trong generic APIs; nó không thay thế cơ chế runtime array component checking, và cũng không làm ArrayList immutable.

## 20. Chương trình hoàn chỉnh 8 — runtime check của array và List

Tệp **`ArrayAndGenericCheckDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ArrayAndGenericCheckDemo {
    public static void main(String[] args) {
        String[] strings = {"A"};
        Object[] objects = strings;

        try {
            objects[0] = 7;
        } catch (ArrayStoreException ex) {
            System.out.println("Array rejected Integer");
        }

        System.out.println("Array = " + strings[0]);

        Object value = new ArrayList<String>();
        if (value instanceof List<?> list) {
            System.out.println("List recognized = true");
            System.out.println("List size = " + list.size());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ArrayAndGenericCheckDemo.java
java ArrayAndGenericCheckDemo
~~~

**Stdout chính xác:**

~~~text
Array rejected Integer
Array = A
List recognized = true
List size = 0
~~~

### 20.1. Vì sao check List<?> hợp lệ?

Chỉ cần biết runtime type implements List. Không đưa một String vào bằng unchecked add và không giả định List chứa String.

### 20.2. Vì sao String[] không bị đổi thành Integer[]?

Object[] variable vẫn trỏ đến một array runtime type String[]. JVM chặn Integer ngay tại array store, nên element đầu giữ "A".

## 21. Generic varargs và heap pollution

Một varargs method:

~~~java
static <T> void process(T... values) {
}
~~~

thường có varargs array ở runtime. Nếu T non-reifiable, compiler có thể cảnh báo về possible heap pollution. Điều này đặc biệt quan trọng với parameterized types như `List<String>...`.

### 21.1. Nguy cơ khi varargs array bị sử dụng không an toàn

Một method có thể cast/expose varargs array như Object[] rồi đưa vào một incompatible parameterized object. Vì JVM không reify generic element arguments, runtime array store check không bảo vệ List<String> khỏi List<Integer> trong mọi tình huống non-reifiable array.

### 21.2. `@SafeVarargs` là lời cam kết

Annotation `@SafeVarargs` nói với compiler rằng developer đã chứng minh method không thực hiện unsafe operations trên varargs parameter và không để varargs array escape theo cách nguy hiểm. Nó **không thay đổi runtime behavior** và không chữa logic sai.

Ở Java 17, annotation được phép trên static/final/private instance methods hoặc constructors thích hợp, không dùng tùy tiện trên overridable instance methods.

### 21.3. Không nhầm safe varargs với deep immutable

Ngay cả khi bạn sao chép varargs elements sang unmodifiable List, nếu elements là mutable objects thì object graph vẫn có thể thay. Type safety, array ownership và object immutability là những concerns tách biệt.

## 22. Chương trình hoàn chỉnh 9 — copy generic varargs an toàn

Tệp **`SafeVarargsCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsCopyDemo {
    @SafeVarargs
    static <T> List<T> immutableCopy(T... values) {
        List<T> output = new ArrayList<>();

        for (T value : values) {
            output.add(value);
        }

        return List.copyOf(output);
    }

    public static void main(String[] args) {
        List<String> names = immutableCopy("Lan", "Mai");
        List<Integer> numbers = immutableCopy(1, 2, 3);

        System.out.println("Names = " + names);
        System.out.println("Numbers = " + numbers);

        try {
            names.add("An");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Unmodifiable");
        }
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 SafeVarargsCopyDemo.java
java SafeVarargsCopyDemo
~~~

**Stdout chính xác:**

~~~text
Names = [Lan, Mai]
Numbers = [1, 2, 3]
Unmodifiable
~~~

### 22.1. Vì sao annotation có cơ sở?

Method chỉ đọc từ varargs array, copy elements sang List mới, không cast array thành Object[] để sửa và không trả/giữ chính varargs array. Đây là implementation có contract an toàn với varargs về generic element types.

### 22.2. Null policy

`List.copyOf` không nhận null elements. Nếu method phải hỗ trợ null, cần thiết kế output container khác và công bố rõ. Null không phải là một vấn đề riêng của raw types.

## 23. Wildcard capture: thay raw bằng generic helper

Đôi khi một method nhận `List<?>` không thể tự làm một operation có vẻ hợp lý như hoán đổi hai elements vì không biết element type. Đừng chuyển sang raw `List` chỉ để compiler chấp nhận gọi `set`.

Dùng helper:

~~~java
static void swap(List<?> values, int a, int b) {
    captureSwap(values, a, b);
}

private static <T> void captureSwap(
        List<T> values, int a, int b) {
    T held = values.get(a);
    values.set(a, values.get(b));
    values.set(b, held);
}
~~~

Helper generic cho compiler biết các reads/writes ở cùng List chia sẻ một captured type T. Nó không thêm một arbitrary Object của kiểu khác.

### 23.1. Chương trình hoàn chỉnh 10 — wildcard capture

Tệp **`WildcardCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    static void swapFirstTwo(List<?> values) {
        swap(values, 0, 1);
    }

    private static <T> void swap(
            List<T> values, int a, int b) {
        T held = values.get(a);
        values.set(a, values.get(b));
        values.set(b, held);
    }

    public static void main(String[] args) {
        List<String> letters =
                new ArrayList<>(List.of("A", "B", "C"));

        swapFirstTwo(letters);

        System.out.println("Letters = " + letters);
        System.out.println("First = " + letters.get(0));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 WildcardCaptureDemo.java
java WildcardCaptureDemo
~~~

**Stdout chính xác:**

~~~text
Letters = [B, A, C]
First = B
~~~

### 23.2. Hạn chế khác generic type

List phải mutable và có ít nhất hai elements, nếu không có thể ném UnsupportedOperationException hoặc IndexOutOfBoundsException. Wildcard capture giải quyết **type consistency**, không giải quyết list size hay mutability.

## 24. `@SuppressWarnings` phải có phạm vi và bằng chứng

`@SuppressWarnings("rawtypes")` và `@SuppressWarnings("unchecked")` là annotations giảm compiler diagnostics trong vùng code tương ứng.

Chúng **không**:

- Tự validate element types.
- Biến unchecked cast thành checked cast.
- Thay đổi type erasure.
- Ngăn ClassCastException.
- Bảo đảm API không còn heap pollution.

### 24.1. Thứ tự xử lý warning tốt

1. Xác định chính xác cảnh báo phát sinh ở declaration hay operation.
2. Tìm boundary nơi type arguments bị mất.
3. Thay raw signature bằng parameterized type nếu có quyền sửa.
4. Dùng wildcard nếu type thật sự unknown.
5. Nếu external input cần typed form, validate/copy từng element.
6. Nếu unchecked cast vẫn không tránh được, chứng minh invariant và cô lập trong helper nhỏ.
7. Chỉ suppress đúng cảnh báo trong helper ấy.
8. Viết tests cho dữ liệu hợp lệ và bất hợp lệ.

### 24.2. Mẫu sai: tưởng checked List interface là đủ

~~~java
@SuppressWarnings("unchecked")
static <T> List<T> trust(Object candidate) {
    if (!(candidate instanceof List<?>)) {
        throw new IllegalArgumentException("Not a list");
    }
    return (List<T>) candidate;
}
~~~

Đây là **fragment có chủ đích KHÔNG bảo đảm element type**. Nó chỉ xác định candidate là List, không biết List chứa T. Nếu không có invariant từ bên ngoài, không nên expose List<T> bằng cách này.

### 24.3. Tránh suppress toàn bộ class/module

Suppression phạm vi rộng sẽ che thêm những unsafe operations được viết sau đó. Suppress nhỏ nhất có thể, kèm ghi chú tại sao unchecked cast an toàn trong tình huống cụ thể.

### 24.4. Giải pháp tạm không phải giải pháp hoàn chỉnh

Một wrapper method dùng unchecked cast có thể cần thiết vì library cũ, nhưng phải bảo vệ preconditions tại boundary; về lâu dài nên sửa API hoặc thay legacy data representation.

## 25. Migration API legacy mà không phá dữ liệu

Giả sử source cũ:

~~~java
List loadNames() {
    List values = new ArrayList();
    values.add("Lan");
    return values;
}
~~~

Đây là **method fragment**, import List/ArrayList khi đặt trong class.

Nếu contract chắc chắn chỉ chứa String:

~~~java
List<String> loadNames() {
    List<String> values = new ArrayList<>();
    values.add("Lan");
    return values;
}
~~~

### 25.1. Không chỉ sửa caller

Nếu source method vẫn return raw List, mọi nơi gọi sẽ tiếp tục có warnings/conversions. Tốt nhất sửa type arguments **ngay tại declaration gốc** khi có thể.

### 25.2. Nếu một List thật sự chứa nhiều runtime types

Đừng gán bừa `List<String>` chỉ để hết warning. Cân nhắc `List<Object>` nếu heterogeneous contents là design, hoặc sealed interface/value abstraction nếu variants có business meanings rõ. Nếu chỉ cần duyệt mà không biết element types, `List<?>`.

### 25.3. Third-party API không sửa được

Viết typed adapter và validate data ở một boundary nhỏ. Chỉ ghi raw/unchecked ở adapter khi thật sự buộc phải làm, kèm tests.

### 25.4. Migration không tự động tương thích 100%

Việc thêm generics có thể giữ nhiều erased binary descriptors tương tự legacy version, nhưng source overload resolution, bounds, inherited signatures, warnings, callers và type inference có thể thay đổi. Test source/binary compatibility theo API thực tế; đừng hứa mọi refactor generics đều “không breaking”.

### 25.5. Chọn hướng siết warnings

Bắt đầu với `-Xlint:rawtypes,unchecked`, lập danh sách modules/files, sửa upstream declarations, sau đó áp dụng `-Werror` cho vùng đã sạch. Không biến warnings thành lỗi toàn hệ thống ngay khi legacy dependencies chưa có đường migration.

## 26. Chương trình hoàn chỉnh 11 — adapter cho dữ liệu Map cũ

Tệp **`LegacyMapAdapterDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class LegacyMapAdapterDemo {
    static <K, V> Map<K, V> checkedCopy(
            Map<?, ?> source,
            Class<K> keyType,
            Class<V> valueType) {

        Map<K, V> output = new HashMap<>();

        for (Map.Entry<?, ?> entry : source.entrySet()) {
            K key = keyType.cast(entry.getKey());
            V value = valueType.cast(entry.getValue());
            output.put(key, value);
        }

        return Map.copyOf(output);
    }

    public static void main(String[] args) {
        Map<Object, Object> legacy = new HashMap<>();
        legacy.put("id", 17);

        Map<String, Integer> checked =
                checkedCopy(legacy, String.class, Integer.class);

        System.out.println("ID = " + checked.get("id"));
        System.out.println("Size = " + checked.size());

        legacy.put("bad", "not an integer");

        try {
            checkedCopy(legacy, String.class, Integer.class);
        } catch (ClassCastException ex) {
            System.out.println("Wrong value rejected");
        }

        System.out.println("Saved ID = " + checked.get("id"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LegacyMapAdapterDemo.java
java LegacyMapAdapterDemo
~~~

**Stdout chính xác:**

~~~text
ID = 17
Size = 1
Wrong value rejected
Saved ID = 17
~~~

### 26.1. Vì sao input Map<Object,Object> thay vì raw Map?

Chương trình mô phỏng một boundary chứa heterogeneous values bằng cách type-declare rõ ràng. Một legacy API thật có thể trả raw Map; adapter nhận `Map<?,?>` rồi kiểm tra key và value đúng type một cách tường minh. Không cần raw receiver ở phần domain typed.

### 26.2. Vì sao không in cả HashMap?

HashMap iteration order không được bảo đảm; demo dùng exact-key lookup và size để stdout ổn định. Bad entry được phát hiện bất kể iteration order vì nó là entry duy nhất sai type.

### 26.3. Map.copyOf chỉ bảo vệ cấu trúc Map

Returned Map là unmodifiable structural snapshot. Nếu V là mutable object, nội dung object vẫn có thể thay; type safety không tương đương deep immutability.

## 27. Lỗi compiler khác runtime exception như thế nào?

| Trường hợp | Thời điểm | Nguyên nhân |
| --- | --- | --- |
| `raw.add(...)` với -Xlint:unchecked | Compile warning | Thiếu chứng minh element type |
| `List<String> = raw` | Compile warning | Unchecked conversion |
| `List<String> → List<Object>` | Compile error | Generics invariance |
| `new List<String>[10]` | Compile error | Non-reifiable generic array creation |
| `value instanceof List<String>` | Compile error | Non-reifiable type test |
| Hai overloads List<String>/List<Integer> | Compile error | Same erasure |
| `T.class` hoặc `new T()` | Compile error | Type variable không reified |
| Đọc String từ raw-corrupted List | Runtime ClassCastException | Cast không hợp lệ |
| Lưu Integer vào String[] qua Object[] | Runtime ArrayStoreException | Runtime array component mismatch |
| Mutate List.of(...) | Runtime UnsupportedOperationException | Unmodifiable collection contract |

### 27.1. Tại sao bảng này quan trọng?

Không nên giải thích warnings như “lỗi sẽ nổ ngay” hoặc runtime ClassCastException như “compiler đã báo lỗi compile”. Java generics có một tầng compile-time checking và một số tầng runtime check khác nhau.

### 27.2. Warnings và errors cần strategy khác nhau

Compiler errors bắt buộc sửa để build. Warnings có thể chưa chặn build, nhưng nên xử lý vì chúng chỉ ra vùng không được generic type system bảo vệ. Không che hết warnings bằng annotations mà thiếu đánh giá invariant.

## 28. Sai lầm phổ biến và cách sửa

1. **Coi raw List là List<Object>.** Sửa: phân biệt parameterized Object với bỏ generic info.
2. **Coi diamond `<>` là raw.** Sửa: hiểu type inference.
3. **Cho rằng List<?> thêm String được vì String là Object.** Sửa: unknown type không đồng nghĩa Object.
4. **Coi wildcard là immutable List.** Sửa: generic add restrictions khác API mutability.
5. **Dùng raw type để né compiler invariance.** Sửa: dùng wildcards hoặc copy.
6. **Bỏ qua raw return type trong public API.** Sửa: chỉnh typed contract ở nguồn.
7. **Nhầm raw diagnostic với unchecked call.** Sửa: bật cả hai lint categories.
8. **Tưởng warnings là runtime exceptions.** Sửa: phân biệt compile diagnostics và execution.
9. **Nhìn execution thành công rồi kết luận unchecked safe.** Sửa: xét mọi data paths.
10. **Cast raw List sang List<String> rồi tưởng elements đã được kiểm tra.** Sửa: validate từng element.
11. **Thấy ClassCastException ở getter rồi chỉ sửa getter.** Sửa: tìm raw/unchecked writer gây heap pollution.
12. **Cho rằng Java erasure tạo một class Box<String> riêng.** Sửa: kiểm getClass và reflection.
13. **Cho rằng reflection không còn generic metadata nào.** Sửa: phân biệt getType với getGenericType.
14. **Cho rằng type erasure làm compiler không thể chặn unsafe set.** Sửa: typed source vẫn được kiểm tra.
15. **Cho rằng bounded T luôn erase về Object.** Sửa: xét first bound.
16. **Tưởng bridge method do mình vô tình overload.** Sửa: hiểu compiler-generated overriding compatibility.
17. **Tạo hai overloads chỉ khác List<String>/List<Integer>.** Sửa: đổi tên hoặc generic method.
18. **Dùng `instanceof List<String>`.** Sửa: dùng List<?> và validate elements.
19. **Tìm `List<String>.class`.** Sửa: runtime class token chỉ mang erased type.
20. **Dùng `new T()` hoặc `new T[]`.** Sửa: Supplier<T>/typed factory/List<T>.
21. **Coi arrays và generics có cùng variance.** Sửa: array covariant, generic invariant.
22. **Bỏ qua heap pollution của parameterized varargs.** Sửa: kiểm varargs body/array escape.
23. **Gắn @SafeVarargs mà chưa chứng minh method an toàn.** Sửa: không sửa varargs array không phù hợp.
24. **SuppressWarnings quá rộng.** Sửa: khoanh vùng và ghi lý do.
25. **Bọc unchecked cast trong một method tên “safe” nhưng không kiểm elements.** Sửa: Class<T>.cast từng phần tử.
26. **Dùng Class<T>.cast để mong validate nested List<String> tự động.** Sửa: validate nested structures.
27. **Chọn List<Object> khi contract thật là List<User>.** Sửa: giữ specific type.
28. **Không kiểm null khi dùng List.copyOf/Map.copyOf.** Sửa: xác định null policy.
29. **Nghĩ generic List luôn thread-safe.** Sửa: concurrency contract độc lập.
30. **Cho rằng unmodifiable List là deep immutable.** Sửa: xét mutable elements.
31. **Tưởng -Werror thay đổi Java runtime behavior.** Sửa: nó chỉ kiểm soát build.
32. **Dùng HashMap iteration để xuất stdout cố định.** Sửa: tránh suy vào thứ tự không được bảo đảm.
33. **Refactor public generic APIs mà không test compatibility.** Sửa: kiểm callers và dependency versions.
34. **Không dùng IDE/compiler lint trong legacy audit.** Sửa: đưa lint vào quy trình.
35. **Không ghi lại boundary nào đã chứng minh type-safe.** Sửa: tests/invariants/contract rõ.

## 29. Bảng quyết định: xử lý raw API thế nào?

| Bạn cần làm gì? | Cách thường phù hợp | Tránh |
| --- | --- | --- |
| Nhận một List bất kỳ để đọc size | `List<?>` | Raw List |
| Nhận List<Integer>/List<Double> để đọc Number | `List<? extends Number>` | Ép sang List<Number> |
| Thêm Integer vào List<Integer>/List<Number> | `List<? super Integer>` | Raw add |
| Lưu toàn bộ Strings | `List<String>` | List<Object> vô cớ |
| Xử lý heterogeneous values thật sự | `List<Object>`/domain union | Giả vờ List<String> |
| Legacy API trả raw nhưng data type xác định | Sửa declaration upstream | Suppress mọi call sites |
| Third-party API không sửa được | Typed adapter | Lan raw qua service/domain |
| External List<?> cần thành List<String> | Validate elements, copy | Unchecked cast nguyên List |
| Generic T cần runtime Class validation | Nhận `Class<T>` | `T.class` |
| Generic methods bị same erasure | Rename/generic abstraction | Overload chỉ khác type arg |
| Wildcard khó dùng set cùng type | Generic helper `<T>` | Cast sang raw |
| Varargs non-reifiable | Safe implementation + correct annotation | Blind @SafeVarargs |
| CI có warnings | Audit/lint; Werror khi sạch | Ignore warnings mãi |

## 30. Bài tập tự kiểm tra có đáp án

**Câu 1.** Raw type là gì?

**Đáp án:** Cách dùng một generic class/interface mà bỏ type arguments, ví dụ raw List.

**Câu 2.** Vì sao Java còn hỗ trợ raw types?

**Đáp án:** Để tương thích với code/libraries trước khi có generics.

**Câu 3.** `List<String> list = new ArrayList<>()` có raw không?

**Đáp án:** Không. Diamond được suy luận từ target type.

**Câu 4.** `List<?>` có giống raw List không?

**Đáp án:** Không. Wildcard giữ compiler checks đối với unknown element type.

**Câu 5.** `List<Object>` có nhận List<String> theo assignment bình thường không?

**Đáp án:** Không vì generic invariance.

**Câu 6.** `List<?>` có cho thêm "A" trực tiếp không?

**Đáp án:** Không, actual element type unknown.

**Câu 7.** `List<?>` có làm ArrayList immutable không?

**Đáp án:** Không.

**Câu 8.** Javac flag nào tìm raw uses?

**Đáp án:** `-Xlint:rawtypes`.

**Câu 9.** Javac flag nào tìm unchecked operations?

**Đáp án:** `-Xlint:unchecked`.

**Câu 10.** Có kết hợp hai flag không?

**Đáp án:** Có, `-Xlint:rawtypes,unchecked`.

**Câu 11.** `-Werror` có làm data runtime an toàn không?

**Đáp án:** Không; nó biến warnings thành lỗi build.

**Câu 12.** Một unchecked call có chắc ném exception ngay không?

**Đáp án:** Không. Nó báo compiler thiếu type-safety guarantee.

**Câu 13.** Heap pollution là gì?

**Đáp án:** Khi data thực tế không phù hợp parameterized type contract do unsafe operations.

**Câu 14.** Cast raw List sang List<String> có quét elements không?

**Đáp án:** Không.

**Câu 15.** Tại sao lỗi có thể nổ tại typed getter muộn hơn nơi raw add?

**Đáp án:** Cast cần thiết lúc đọc String mới phát hiện runtime Integer.

**Câu 16.** Erasure của unbounded T là gì?

**Đáp án:** Thường Object.

**Câu 17.** Erasure của T extends Number là gì?

**Đáp án:** Number.

**Câu 18.** Box<String> và Box<Integer> có tạo hai runtime classes không?

**Đáp án:** Không với ordinary generic class Box.

**Câu 19.** Reflection có thể thấy declaration type variable T không?

**Đáp án:** Có qua getTypeParameters/signature metadata.

**Câu 20.** Vì sao runtime Class của Box<String> không nói T=String?

**Đáp án:** Type argument không reified cho arbitrary generic instance.

**Câu 21.** Bridge method dùng làm gì?

**Đáp án:** Duy trì overriding/polymorphism khi erased signatures khác source-specialized signatures.

**Câu 22.** Bridge có phải code raw bị lỗi không?

**Đáp án:** Không, bridge cũng xuất hiện trong type-safe generic inheritance.

**Câu 23.** Hai methods `f(List<String>)` và `f(List<Integer>)` có thể overload cùng class không?

**Đáp án:** Không, name clash sau erasure.

**Câu 24.** Có dùng `instanceof List<String>` không?

**Đáp án:** Không, type không reifiable.

**Câu 25.** `instanceof List<?>` có kiểm tra toàn bộ String elements không?

**Đáp án:** Không, chỉ kiểm tra object là List.

**Câu 26.** Vì sao `T.class` không hợp lệ?

**Đáp án:** Type variable không có class literal/runtime reification như concrete class type.

**Câu 27.** Có thể `new T()` không?

**Đáp án:** Không chỉ dựa trên erased generic type parameter.

**Câu 28.** Có thể `new List<String>[10]` không?

**Đáp án:** Không, do generic array creation restrictions.

**Câu 29.** Lỗi lưu Integer vào String[] qua Object[] là gì?

**Đáp án:** ArrayStoreException.

**Câu 30.** Lỗi typed code đọc Integer dưới kiểu String thường là gì?

**Đáp án:** ClassCastException.

**Câu 31.** `@SuppressWarnings` có validate types không?

**Đáp án:** Không, chỉ suppress compiler diagnostics.

**Câu 32.** `@SafeVarargs` có làm unsafe method tự an toàn không?

**Đáp án:** Không, tác giả phải bảo đảm implementation thực sự safe.

**Câu 33.** Khi cần swap hai elements trong List<?> có phải dùng raw không?

**Đáp án:** Không; dùng generic wildcard-capture helper.

**Câu 34.** Khi nhận dữ liệu List<?> không đáng tin, làm sao có List<String>?

**Đáp án:** Kiểm từng element bằng String.class.cast và tạo List<String> mới, xử lý null theo contract.

**Câu 35.** Class<T> token có validate List<String> nested type tự động không?

**Đáp án:** Không; phải kiểm tra elements riêng.

**Câu 36.** Raw types có làm generic API dễ maintain hơn không?

**Đáp án:** Thường không; chúng bỏ type information và đẩy rủi ro sang callers.

**Câu 37.** Việc code không có raw warnings có đảm bảo business validation không?

**Đáp án:** Không; generics kiểm tra type, còn domain invariants cần logic riêng.

**Câu 38.** Java generics có tự giải quyết null, mutability và concurrency không?

**Đáp án:** Không, đó là các contract riêng.

**Câu 39.** Khi gặp warning đầu tiên nên làm gì?

**Đáp án:** Phân loại warning, tìm boundary mất type information và kiểm tra actual data contract trước khi cast/suppress.

**Câu 40.** Điều cốt lõi nhất?

**Đáp án:** Raw làm mất compiler generic checks; unchecked đánh dấu thao tác không chứng minh an toàn; erasure giải thích runtime representation. Muốn type safety, dùng typed APIs, wildcards/generic helpers và validation ở boundary.

## 31. Bài tập thực hành

### Bài 1 — xác định vị trí cảnh báo

Tạo RawWarningExample.java như trên, chạy `javac -Xlint:rawtypes,unchecked`. Ghi lại cảnh báo ở raw declaration, unchecked call và conversion. Sửa type thành List<String> với diamond rồi biên dịch lại.

### Bài 2 — cố ý tạo heap pollution

Viết Box<T> và helper raw set(42) vào Box<String>. Theo dõi thời điểm ClassCastException. Sau đó thay helper bằng `static <T> void set(Box<T> box, T value)` để compiler ngăn sai type.

### Bài 3 — thay raw bằng wildcard

Viết method nhận List<?> và in size/contents. Thử gọi với List<String> và List<Integer>. Chứng minh compile-time không cho add("A") rồi sửa API bằng bounded wildcards nếu cần read Number.

### Bài 4 — runtime validation

Dùng List<?> từ external input. Viết checkedCopy có Class<T>.cast từng element, test Strings đúng, một Integer sai và null policy.

### Bài 5 — quan sát erasure

Tạo Box<T> và NumberBox<N extends Number>. In Field.getType và Class.getTypeParameters; giải thích Object/Number/T khác nhau.

### Bài 6 — quan sát bridge

Override Parent<T>.get trong Child extends Parent<String>, kiểm reflection Method.isBridge và gọi qua Parent<String> reference.

### Bài 7 — generic method name clash

Thử compile hai overloads chỉ khác List<String>/List<Integer>. Đọc compiler error, đổi tên methods hoặc tạo một generic method nếu logic có thể dùng chung.

### Bài 8 — quality gate

Đưa `-Xlint:rawtypes,unchecked` vào một module, giảm warnings bằng typed APIs, scoped validation và migration tests. Khi module sạch mới cân nhắc `-Werror`.

## 32. Checklist cuối bài

1. Mỗi raw generic declaration có lý do compatibility rõ không?
2. Có thể thay bằng parameterized type cụ thể không?
3. Nếu unknown, đã cân nhắc wildcard `<?>` chưa?
4. Có mất typed contract trong public method return/parameter không?
5. Có raw superclass/interface hoặc Class declaration không?
6. Có bật cả rawtypes và unchecked lint categories chưa?
7. Có xác định unchecked call khác unchecked conversion không?
8. Cảnh báo có bị suppress quá rộng không?
9. Có chứng minh mọi unchecked casts bằng invariant hoặc validation không?
10. Có chỗ nào raw add/put gây heap pollution không?
11. Có dùng Class<T>.cast từng element từ external data không?
12. Có tránh nghĩ whole-List cast kiểm mọi elements không?
13. Có test negative input và delayed ClassCastException không?
14. Có phân biệt generic compile warnings với runtime exceptions không?
15. Có hiểu Type erasure unbounded/bounded khác nhau không?
16. Có tránh suy runtime Class theo Box<String> argument không?
17. Có hiểu generic declaration metadata vẫn tồn tại cho reflection không?
18. Có biết compiler có thể chèn cast và bridge methods không?
19. Có method signatures xung đột vì same erasure không?
20. Có tránh instanceof List<String> và new generic arrays không?
21. Có phân biệt arrays covariance và generic invariance không?
22. Có xem xét unsafe varargs và @SafeVarargs contract không?
23. Có wildcard capture helper khi cần typed set/get cùng unknown T không?
24. Có giữ null policy/ownership/mutability riêng không?
25. Có kiểm source/binary compatibility khi sửa legacy generic APIs không?
26. Có giữ raw/unchecked logic trong adapter thay vì lan vào domain không?
27. Có tránh dùng raw chỉ để qua compiler không?
28. Có xem xét generic bounds và variance đúng khi API cần không?
29. Có tests/CI audit warnings theo từng module không?
30. Có mô tả rõ boundary nào được compile-time kiểm và boundary nào cần runtime validation không?

## Kết luận

**Raw type** là dạng sử dụng generic class/interface mà bỏ type arguments; nó chủ yếu tồn tại để giữ tương thích với Java legacy và có thể cho phép **unchecked operations** làm phát sinh **heap pollution**. Java compiler có thể cảnh báo bằng `-Xlint:rawtypes,unchecked`, nhưng runtime lỗi `ClassCastException` đôi khi chỉ xuất hiện lúc code typed đọc dữ liệu sai, khá xa nơi raw writer chèn dữ liệu.

**Type erasure** là cách Java generics được biên dịch: type variables thường erase thành bound/Object, compiler chèn casts và bridge methods khi cần, còn parameterized Box<String>/Box<Integer> chia sẻ một runtime class. Đây không phải lý do bỏ generics; nguồn code generic đúng vẫn được kiểm tra rất mạnh ở compile time.

Khi gặp code raw hoặc unchecked, đừng chỉ dùng casts/suppression để giấu warnings. Hãy **khôi phục type arguments ở API**, dùng `List<?>` khi chưa biết element type, dùng type bounds/wildcards/generic helper khi cần, và **kiểm tra dữ liệu ở boundary** trước khi hứa với caller rằng một List thật sự là List<String>. Những bước này giúp Java 17+ code tận dụng generics an toàn, giữ compatibility có kiểm soát và tránh lỗi kiểu xuất hiện muộn.
