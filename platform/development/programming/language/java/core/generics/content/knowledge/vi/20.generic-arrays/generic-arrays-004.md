# Khác biệt giữa khai báo biến mảng generic và biểu thức tạo mảng trong Java

## 1. Vấn đề: “Khai báo được nhưng new không được” có mâu thuẫn không?

Một trong những tình huống gây ngạc nhiên khi kết hợp Java Generics với array:

~~~java
import java.util.List;

class Example {
    List<String>[] values;       // HỢP LỆ: khai báo biến/trường.

    void initialize() {
        // values = new List<String>[3]; // LỖI: generic array creation.
    }
}
~~~

Dấu ngoặc vuông `[]` đều xuất hiện trong hai chỗ, nhưng hai biểu thức làm **hai việc khác nhau**:

- `List<String>[] values;` **khai báo một biến hoặc trường có kiểu mảng**, tức phần tử của nó được mô tả ở compile time là `List<String>`. Câu lệnh chỉ thông báo kiểu cho compiler, **không tạo một đối tượng array runtime**.
- `new List<String>[3]` yêu cầu JVM **tạo một array object**, có kiểu thành phần runtime. Tham số kiểu `String` trong `List<String>` không được giữ đầy đủ ở runtime do type erasure, nên Java cấm kiểu biểu thức tạo mảng này.

Vì vậy, Java hoàn toàn có thể cho phép một **kiểu dùng trong khai báo** nhưng không cho phép **biểu thức trực tiếp tạo array của kiểu ấy**. Không có sự mâu thuẫn: quy tắc khai báo và quy tắc tạo đối tượng phục vụ những bước khác nhau.

Các câu hỏi chính sẽ được giải đáp:

1. Tại sao `List<String>[]` và `T[]` hợp lệ trong khai báo, nhưng `new List<String>[n]` và `new T[n]` lỗi?
2. Tại sao `new List<?>[n]` lại hợp lệ?
3. Có thể gán thẳng `new List<?>[n]` cho `List<String>[]` không?
4. Nếu dùng unchecked cast để tạo mảng generic, điều gì có thể sai ở runtime?
5. Những lựa chọn an toàn hơn gồm những gì, và khi nào dùng `List<List<String>>` hoặc nhận array từ caller?

## 2. Cần tách ba khái niệm: array type, biến và array creation expression

### 2.1. Array type là một kiểu

`String[]` là một array type có phần tử String.

`List<String>[]` là một array type có phần tử là một parameterized type `List<String>`.

`T[]` trong một generic class hoặc generic method là một array type có phần tử là **type variable T**.

Các kiểu này có thể xuất hiện trong chữ ký trường, biến cục bộ, tham số hoặc kiểu trả về:

~~~java
import java.util.List;

class Inventory<T> {
    T[] elements;                // Hợp lệ.
    List<String>[] groups;       // Hợp lệ.

    void accept(List<T>[] input) {  // Hợp lệ ở mức khai báo.
        // Có thể xử lý input theo kiểu đã khai báo.
    }

    List<T>[] expose() {         // Hợp lệ ở mức khai báo.
        return null;             // Chỉ minh họa chữ ký.
    }
}
~~~

Đoạn trên **không tạo** `List<T>[]` nào. Trường mảng instance khi chưa gán có giá trị mặc định null. Việc một chữ ký generic array hợp lệ không có nghĩa compiler sẽ tự biết cách tạo nó.

### 2.2. Một biến array chưa chắc có đối tượng array

~~~java
List<String>[] declared = null; // Hợp lệ.
~~~

`declared` có kiểu tĩnh `List<String>[]`, nhưng giá trị hiện tại là null. Compiler cho phép khai báo vì chưa phải sinh một array object có component type `List<String>` ở runtime.

Ngược lại, câu lệnh sau cần tạo đối tượng:

~~~java
// List<String>[] created = new List<String>[2];
// Lỗi compile-time: generic array creation.
~~~

### 2.3. Array creation expression phải có component type cho runtime

Mỗi Java array có một **runtime component type** để JVM kiểm soát việc gán phần tử. Với:

~~~java
String[] strings = new String[2];
~~~

component type runtime là `java.lang.String`. Nếu mảng thực sự là String[] mà bị gán phần tử Integer qua alias Object[], JVM từ chối bằng `ArrayStoreException`.

Với:

~~~java
// new List<String>[2]
~~~

JVM không sở hữu một runtime class riêng “List của String” để kiểm tra một phần tử List<?> vừa được gán có chứa String hay không. Vì thế Java không cho phép tạo array trực tiếp với component type không-reifiable như `List<String>`.

## 3. Quy tắc reifiable type giải thích sự khác biệt

**Reifiable type** là kiểu có đủ thông tin cần thiết ở runtime theo quy tắc Java. Các trường hợp hữu ích trong bài này:

- Kiểu không generic: `String`, `Integer`, `Runnable`.
- Raw type của generic class/interface: `List`, `Map`.
- Parameterized type chỉ có **unbounded wildcard arguments**, chẳng hạn `List<?>`, `Map<?, ?>`.
- Array type có component type reifiable, chẳng hạn `String[]` hoặc `List<?>[]`.

Trái lại:

- `List<String>` không reifiable.
- `List<Integer>` không reifiable.
- `List<? extends Number>` không reifiable vì wildcard có cận trên cụ thể, không phải unbounded `?`.
- `Map<String, List<Integer>>` không reifiable.
- Type variable `T` thông thường không phải kiểu có runtime component class cụ thể để dùng với `new T[n]`.

So sánh:

| Biểu thức | Java 17 | Lý do |
| --- | --- | --- |
| `new String[3]` | Hợp lệ | String là reifiable. |
| `new Integer[3]` | Hợp lệ | Integer là reifiable. |
| `new List[3]` | Hợp lệ, raw use | Raw List là reifiable, nhưng làm mất generic checking ở những chỗ sử dụng raw. |
| `new List<?>[3]` | Hợp lệ | List<?> là reifiable. |
| `new Map<?, ?>[3]` | Hợp lệ | Mọi type argument là unbounded wildcard. |
| `new List<String>[3]` | Không hợp lệ | List<String> không reifiable. |
| `new List<Integer>[3]` | Không hợp lệ | List<Integer> không reifiable. |
| `new List<? extends Number>[3]` | Không hợp lệ | Type argument không phải unbounded wildcard. |
| `new Map<String, Integer>[3]` | Không hợp lệ | Map<String,Integer> không reifiable. |
| `new T[3]` trong generic class | Không hợp lệ | T không có runtime component type xác định cho array creation. |

**Không nhầm `List<?>` với raw `List`.** `List<?>` là một parameterized type hợp lệ với wildcard, trong khi raw `List` bỏ type argument. Hai array creation expressions `new List<?>[3]` và `new List[3]` đều có thể biên dịch, nhưng kiểu tĩnh của kết quả khác nhau, kéo theo cách kiểm tra khi lập trình tiếp theo khác nhau.

## 4. Vì sao mảng kiểm tra kiểu ở runtime còn generics chủ yếu ở compile time?

Java array là **covariant**: nếu String là subtype của Object, thì String[] cũng là subtype của Object[].

~~~java
String[] strings = new String[1];
Object[] alias = strings; // Hợp lệ vì array covariance.
~~~

Nhưng array object vẫn mang component type runtime là String. Vì thế:

~~~java
Object[] alias = new String[1];

try {
    alias[0] = Integer.valueOf(7);
} catch (ArrayStoreException error) {
    System.out.println("Rejected non-String element");
}
~~~

JVM phát hiện đối tượng Integer không thể nằm trong String[] và ném `ArrayStoreException` **tại thời điểm gán**.

Generic parameterized types trong Java nhìn chung **invariant**:

~~~java
List<String> strings = new ArrayList<>();

// List<Object> objects = strings; // Không biên dịch.
List<?> unknown = strings;        // Hợp lệ.
~~~

Sự invariant này giúp compiler ngăn việc thêm Integer vào List<String> qua alias List<Object>. Nhưng do type erasure, runtime không phân biệt tổng quát `ArrayList<String>` và `ArrayList<Integer>` bằng hai runtime classes.

Nếu `new List<String>[n]` được cho phép, array covariance có thể tạo đường đưa một List<Integer> vào array tưởng như chỉ chứa List<String>. Với runtime component type chỉ kiểm tra được List, array store check có thể bỏ qua khác biệt type arguments. Đó là lý do **generic array creation bị cấm với component type không reifiable**.

## 5. Thí nghiệm lý thuyết: nếu new List<String>[] được phép thì sao?

Đây là **mã cố ý không hợp lệ** để giải thích thiết kế ngôn ngữ:

~~~java
// KHÔNG BIÊN DỊCH:
List<String>[] strings = new List<String>[1];

Object[] alias = strings;
alias[0] = List.of(123);

String value = strings[0].get(0);
~~~

Điểm nguy hiểm giả định:

1. Biến strings hứa rằng mọi phần tử array là List<String>.
2. Do array covariance, alias có kiểu Object[] nhưng trỏ đến cùng array.
3. Nếu JVM chỉ thấy runtime component type List, lệnh gán List<Integer> qua alias có thể vượt qua kiểm tra array store.
4. Sau đó compiler tin `strings[0].get(0)` là String.
5. Giá trị thực tế là Integer, dẫn đến `ClassCastException` ở thời điểm đọc.

Java không cho xây array trực tiếp bằng cú pháp generic không reifiable ngay từ bước đầu, qua đó giảm khả năng có mảng tuyên bố sai về type arguments.

**Lưu ý:** chương trình có thể vẫn tạo tình huống tương tự nếu chủ động dùng **unchecked cast**. Lệnh cấm generic array creation không thể ngăn mọi mã không an toàn, đặc biệt raw types và unchecked casts.

## 6. Khai báo List<String>[] hoàn toàn hợp lệ

Các khai báo:

~~~java
List<String>[] a;
List<String>[] b = null;
List<Integer>[][] matrix;
~~~

đều hợp lệ nếu đặt trong một ngữ cảnh Java tương ứng và có import `java.util.List`. Chúng chỉ thiết lập kiểu tĩnh; không phải array creation.

Một method có thể **nhận** hoặc **trả** kiểu array generic:

~~~java
static void inspect(List<String>[] rows) {
    for (List<String> row : rows) {
        System.out.println(row.size());
    }
}

static List<String>[] identity(List<String>[] rows) {
    return rows;
}
~~~

Việc những chữ ký trên hợp lệ không chứng minh method có thể tự khởi tạo `new List<String>[n]`. Để có một array object tương thích, method phải **nhận từ caller**, lấy từ API hợp lệ, hoặc dựa trên cách tạo đặc biệt có giả định và rủi ro rõ ràng.

Ví dụ với một biến chưa gán:

~~~java
List<String>[] rows;
// System.out.println(rows.length); // Không biên dịch: biến cục bộ chưa được gán.
~~~

Đừng nhầm “khai báo hợp lệ” với “biến đã có giá trị dùng được”. Trong Java, biến cục bộ phải được khởi tạo trước khi đọc.

## 7. Tại sao new List<?>[n] hợp lệ?

`List<?>` là **parameterized type với unbounded wildcard**, được Java xem là reifiable. Do đó:

~~~java
List<?>[] buckets = new List<?>[3];

buckets[0] = List.of("Java");
buckets[1] = List.of(10, 20);
buckets[2] = List.of(true);
~~~

Đoạn mã hợp lệ: mỗi phần tử của array là một List nhưng có thể có **kiểu phần tử khác nhau**. Điều đó khớp đúng với ý nghĩa wildcard: ta không tuyên bố một loại phần tử duy nhất.

Đọc dữ liệu:

~~~java
Object value = buckets[0].get(0);
System.out.println(value); // Java.
~~~

Giá trị lấy từ `List<?>` an toàn khi xem là Object. Compiler không cho kết luận ngay rằng nó là String nếu chưa kiểm tra bổ sung.

Một cách khởi tạo ngắn:

~~~java
List<?>[] buckets = {
    List.of("Java"),
    List.of(123)
};
~~~

Array initializer như trên cũng có thể tạo một array chứa List<?> theo ngữ cảnh đã khai báo, không phải `new List<String>[]`.

### Wildcard array không bảo đảm kiểu của mọi phần tử nằm sâu bên trong

~~~java
List<?>[] buckets = new List<?>[2];
buckets[0] = List.of("A");
buckets[1] = List.of(42);
~~~

Cả hai hợp lệ vì runtime component type của array là List. Mỗi List bên trong có thể mang kiểu phần tử khác nhau. `List<?>[]` vì thế **không thể dùng để thay thế an toàn cho `List<String>[]` khi nghiệp vụ yêu cầu mọi List đều chứa String**.

## 8. Không được gán trực tiếp List<?>[] thành List<String>[]

Đây là câu hỏi thường gặp sau khi học `new List<?>[n]`:

~~~java
// List<String>[] specific = new List<?>[3]; // Không biên dịch.
~~~

Compiler không cho gán vì `List<?>[]` có thể chứa List<Integer>, còn `List<String>[]` hứa các phần tử array là List<String>. Không có conversion an toàn cho lời gán trực tiếp này.

Thử trên Java 17 cho lỗi đại ý:

~~~text
incompatible types: List<?>[] cannot be converted to List<String>[]
~~~

Điều **có thể** làm nhưng không nên coi là an toàn mặc định là unchecked cast:

~~~java
@SuppressWarnings("unchecked")
List<String>[] risky = (List<String>[]) new List<?>[3];
~~~

Ở runtime, cast có thể được chấp nhận vì array object thực chất có component runtime tương ứng với List. Tuy nhiên cast không kiểm tra type argument String của từng List, vì thế `risky` có thể mang một cam kết kiểu chưa được chứng minh.

Các đoạn dùng unchecked cast như vậy chỉ nên tồn tại trong một utility rất hẹp, được document rõ bất biến, và phải bảo đảm không có đường ghi khiến các phần tử array sai type argument.

## 9. Ví dụ hoàn chỉnh Java 17+: khai báo, wildcard array, unchecked cast và lỗi runtime

Lưu chương trình sau vào **GenericArrayDemo.java**:

~~~java
import java.lang.reflect.Array;
import java.util.Arrays;
import java.util.List;

public class GenericArrayDemo {
    static <T> T[] makeArray(Class<T> componentType, int length) {
        @SuppressWarnings("unchecked")
        T[] result = (T[]) Array.newInstance(componentType, length);
        return result;
    }

    static <T> T[] copy(T[] input) {
        return Arrays.copyOf(input, input.length);
    }

    public static void main(String[] args) {
        // Khai báo hợp lệ dù không tạo array.
        List<String>[] declared = null;
        System.out.println("declared=" + declared);

        // Tạo được mảng reifiable List<?>.
        List<?>[] wildcard = new List<?>[2];
        wildcard[0] = List.of("Java");
        wildcard[1] = List.of(42);
        System.out.println(
                "wildcard=" + Arrays.toString(wildcard)
        );
        System.out.println(
                "wildcardType=" +
                wildcard.getClass().getComponentType().getName()
        );

        // Tạo array từ runtime Class token khi component type reifiable.
        String[] names = makeArray(String.class, 2);
        names[0] = "Java";
        names[1] = "Kotlin";
        String[] duplicate = copy(names);
        System.out.println(
                "copy=" + Arrays.toString(duplicate)
        );

        // Unchecked cast: hợp lệ về cú pháp nhưng KHÔNG tự bảo đảm
        // mọi List trong array đều chứa String.
        @SuppressWarnings("unchecked")
        List<String>[] risky = (List<String>[]) new List<?>[2];

        risky[0] = List.of("safe");
        Object[] alias = risky;

        // Runtime array chỉ biết component là List.
        alias[1] = List.of(42);

        System.out.println(
                "riskyClass=" +
                risky.getClass().getComponentType().getName()
        );

        try {
            String bad = risky[1].get(0);
            System.out.println(bad);
        } catch (ClassCastException exception) {
            System.out.println("polluted=ClassCastException");
        }

        // Đối chứng: JVM kiểm tra component String của String[].
        Object[] actualStrings = new String[1];

        try {
            actualStrings[0] = 42;
        } catch (ArrayStoreException exception) {
            System.out.println("arrayStore=ArrayStoreException");
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:unchecked GenericArrayDemo.java
java GenericArrayDemo
~~~

Stdout **chính xác**:

~~~text
declared=null
wildcard=[[Java], [42]]
wildcardType=java.util.List
copy=[Java, Kotlin]
riskyClass=java.util.List
polluted=ClassCastException
arrayStore=ArrayStoreException
~~~

### Giải thích output theo thứ tự

**`declared=null`:** biến có kiểu `List<String>[]` tồn tại nhưng chưa tham chiếu array object nào. Đây là khai báo hợp lệ.

**`wildcard=[[Java], [42]]`:** array chứa hai List có phần tử khác nhau. Kiểu `List<?>[]` diễn đạt đúng sự chưa biết này.

**`wildcardType=java.util.List`:** component runtime type là List, không phải List<String> hay List<Integer>. Điều này giúp hiểu vì sao một array store check không xác minh phần tử generic bên trong.

**`copy=[Java, Kotlin]`:** phương thức `makeArray(String.class,2)` tạo String[] bằng reflection; `Arrays.copyOf` dùng runtime array type của input để tạo bản sao thích hợp.

**`riskyClass=java.util.List`:** sau unchecked cast, array vẫn có component runtime là List. Cast không biến array thành loại runtime đặc biệt chứa List<String>.

**`polluted=ClassCastException`:** alias Object[] gán `List<Integer>` vào vị trí array vốn được biến risky nhìn như List<String>[]. JVM chấp nhận vì đối tượng được gán là List. Nhưng khi đọc phần tử đầu tiên với kiểu tĩnh String, compiler/JVM kiểm tra và ném ClassCastException vì thực tế là Integer.

**`arrayStore=ArrayStoreException`:** với array thực sự có component String, JVM từ chối ngay việc gán Integer qua alias Object[]. Đây là khác biệt giữa cơ chế array runtime và type erasure của generic arguments.

**Mục đích giáo dục:** đoạn dùng unchecked cast là ví dụ **cố ý không an toàn**. Không nên sao chép mẫu đó vào API production khi chưa chứng minh được bất biến thành phần, giới hạn alias và điểm ghi.

## 10. Các biểu thức tạo mảng bị Java từ chối: kiểm tra compile time

Đoạn sau **cố ý không biên dịch**, tách khỏi chương trình `GenericArrayDemo.java`:

~~~java
import java.util.List;

class InvalidArrays<T> {
    List<String>[] a = new List<String>[3];
    List<? extends Number>[] b =
            new List<? extends Number>[3];
    T[] c = new T[3];
    List<String>[] d = new List<?>[3];
}
~~~

Biên dịch Java 17:

~~~bash
javac --release 17 InvalidArrays.java
~~~

Lỗi tương ứng:

| Dòng | Nhóm lỗi | Vì sao |
| --- | --- | --- |
| `new List<String>[3]` | `generic array creation` | List<String> không reifiable. |
| `new List<? extends Number>[3]` | `generic array creation` | Wildcard có cận, không phải unbounded wildcard reifiable. |
| `new T[3]` | `generic array creation` | T là type variable, chưa có runtime component type. |
| `List<String>[] d = new List<?>[3]` | `incompatible types` | Không chuyển trực tiếp List<?>[] sang List<String>[] một cách an toàn. |

**Quan trọng:** không phải mọi chỗ xuất hiện kiểu generic array đều bị cấm. Các **vế trái** `List<String>[] a`, `T[] c` đều là những khai báo kiểu hợp lệ. Lỗi phát sinh ở **biểu thức khởi tạo bên phải**, hoặc vì phép gán hai array types không tương thích.

## 11. Khai báo T[] hợp lệ nhưng new T[n] không hợp lệ

Trong một generic class:

~~~java
class Buffer<T> {
    private T[] values; // Hợp lệ.

    Buffer(T[] supplied) {
        values = supplied; // Hợp lệ: nhận array do caller cung cấp.
    }

    T get(int index) {
        return values[index];
    }
}
~~~

Cách sử dụng:

~~~java
Buffer<String> buffer =
        new Buffer<>(new String[] {"A", "B"});

String first = buffer.get(0); // "A".
~~~

Caller đã tạo **String[]** bằng một component type reifiable, rồi cung cấp cho Buffer<T>. Generic class không phải tự suy diễn runtime class của T từ type erasure.

Ngược lại, không thể viết:

~~~java
class BadBuffer<T> {
    // T[] values = new T[3]; // Không biên dịch.
}
~~~

Lý do: Java không thể dùng một type variable T để tạo trực tiếp một runtime array có component type cụ thể, dù sau đó người dùng có thể tạo `BadBuffer<String>` hoặc `BadBuffer<Integer>`.

### Một cận kiểu cũng không tự làm new T[n] hợp lệ

~~~java
class BoundedBuffer<T extends Number> {
    // T[] items = new T[3]; // Không biên dịch.
}
~~~

Dù T bị xóa về Number khi biên dịch, `Number[]` không tương đương `Integer[]`, `Double[]` hoặc mọi T cụ thể. Nếu mục đích thật sự chỉ cần lưu Number, có thể cân nhắc tạo `new Number[n]` với thiết kế dựa trên Number; còn nếu API hứa T[], cần bảo đảm component type T bằng phương án thích hợp.

## 12. Giải pháp phụ thuộc nơi có thông tin component type

Bài toán này trước hết phải phân biệt **khai báo** mảng generic với **cấp phát**. Khi cần một array object thật, chọn cách mang được runtime component type phù hợp:

1. **Nhận mảng đã được caller tạo:** `static <T> T[] copy(T[] source) { return Arrays.copyOf(source, source.length); }` tận dụng component class thực của source.
2. **Nhận `Class<T>`:** dùng `Array.newInstance(componentType, length)`, cô lập cast vì reflection trả `Object`. Ví dụ `String.class` tạo `String[]`, chứ không tạo `Object[]` giả dạng.
3. **Nhận factory:** `IntFunction<T[]>` với `String[]::new` để caller trực tiếp quyết định runtime component class.
4. **Không buộc dùng mảng:** `List<List<String>>` mô tả nhiều nhóm chuỗi; `List<?>[]` chỉ hợp lý khi type arguments thật sự chưa biết và API cần array.

```java
static <T> T[] cloneOf(T[] source) {
    return java.util.Arrays.copyOf(source, source.length);
}

static <T> T[] make(int n, java.util.function.IntFunction<T[]> factory) {
    return factory.apply(n);
}
```

**Đừng đánh đồng token `List.class` với `List<String>.class` không tồn tại.** Một `Class<T>` hoặc factory có thể cung cấp runtime class của `String`, nhưng không làm type arguments của `List<String>` reifiable. Bài chuyên về array factories xử lý thêm null, factory trả sai kích thước, primitive arrays và `Collection.toArray`.

## 13. Vì sao không nên dùng (T[]) new Object[n] một cách máy móc?

Một mẹo phổ biến:

~~~java
class Risky<T> {
    @SuppressWarnings("unchecked")
    T[] create(int n) {
        return (T[]) new Object[n];
    }
}
~~~

Compiler có thể chấp nhận kèm cảnh báo unchecked bị suppress, nhưng runtime array thực tế luôn là **Object[]**. Nếu bên gọi cần `String[]`, việc JVM kiểm tra/cast kết quả cụ thể thành String[] có thể thất bại:

~~~java
Risky<String> factory = new Risky<>();
// String[] names = factory.create(2);
// Có thể ném ClassCastException: Object[] không phải String[].
~~~

**Vấn đề không chỉ ở kiểu phần tử lúc đọc:** ngay bản thân array object mang component type Object khác String. Do array runtime reification, Object[] không thể thay thế String[] khi caller yêu cầu String[].

Đôi khi thư viện dùng Object[] nội bộ và cast ở một ranh giới đã được thiết kế đặc biệt. Khi đó không được công bố tùy tiện API trả T[] nếu không đáp ứng runtime component type mà caller kỳ vọng. Một hướng dễ chứng minh hơn là lưu `Object[]` thật, kiểm tra từng giá trị lúc đọc, hoặc dùng `Class<T>` token để tạo array có component phù hợp.

## 14. Generic varargs có liên quan gì?

Một khai báo varargs generic:

~~~java
static <T> void printAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
~~~

`T...` về bản chất là tham số array type `T[]`. Java cho phép khai báo đó, nhưng khi lời gọi cần tạo array chứa một **non-reifiable type**, compiler có thể cảnh báo unchecked hoặc `possible heap pollution from parameterized vararg type`.

Ví dụ:

~~~java
static void showAll(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group);
    }
}
~~~

Đây là khai báo hợp lệ, nhưng nó có thể làm đường truyền giá trị non-reifiable qua array. Không nên xem cú pháp varargs như một cách lách an toàn quy tắc generic array creation.

Một phương thức `@SafeVarargs` chỉ nên dùng khi tác giả **thực sự chứng minh được thân phương thức không thực hiện những thao tác không an toàn trên varargs array**. Với Java 17, annotation có thể dùng trên static/final methods, constructors và private instance methods theo các điều kiện của ngôn ngữ. Nó **không tự thêm kiểm tra runtime** và không hợp pháp hóa thao tác gây heap pollution.

Khi API chỉ cần một tập hợp các phần tử generic, tham số `List<T>` hoặc `Collection<T>` thường giúp tránh một số tình huống rủi ro và cảnh báo liên quan varargs array.

## 15. Phân biệt ArrayStoreException và ClassCastException

Hai ngoại lệ này thường bị nhầm trong bài toán generic array:

| Tình huống | Điều kiểm tra thất bại | Ngoại lệ |
| --- | --- | --- |
| Gán Integer vào String[] qua Object[] | Runtime component type String của array | `ArrayStoreException` tại thời điểm gán. |
| Gán List<Integer> vào array có component runtime List | Component List vẫn phù hợp; store được chấp nhận | Không bắt buộc phát lỗi tại thời điểm gán. |
| Đọc Integer từ List nằm trong `List<String>[]` bị nhiễm và dùng như String | Cast phần tử Object thành String khi dùng | `ClassCastException` tại thời điểm đọc/sử dụng. |
| Cast array thật `Object[]` thành `String[]` | Runtime array class không tương thích | `ClassCastException` ngay ở cast array. |

Ví dụ:

~~~java
Object[] a = new String[1];
// a[0] = 5;             // Khi chạy: ArrayStoreException.

Object[] b = new List<?>[1];
b[0] = List.of(5);       // Hợp lệ: đối tượng là List.
~~~

Kết luận: **array kiểm tra kiểu phần tử trực tiếp của array ở runtime**, còn generic arguments bên trong collection có thể không được kiểm tra sâu. Cast được compiler chèn khi sử dụng generic value có thể phát hiện sai lệch về sau.

## 16. Những sai lầm thường gặp

### “Có thể khai báo List<String>[] tức là new List<String>[] cũng phải được”

Sai. Việc khai báo kiểu mảng không đòi tạo runtime array. `new` đòi runtime component type phù hợp; `List<String>` không reifiable.

### “List<?>[] có thể gán cho List<String>[] vì dấu ? bao quát String”

Sai. `List<?>` biểu thị kiểu phần tử chưa biết, không khẳng định String. Java không cho gán trực tiếp `List<?>[]` sang `List<String>[]`.

### “Unchecked cast đã sửa vấn đề cho mảng generic”

Sai. `(List<String>[]) new List<?>[n]` không thay đổi runtime component thành List<String>. Nó chỉ tuyên bố một kiểu tĩnh cụ thể mà JVM không thể kiểm tra đầy đủ. Mã có thể ném ClassCastException khi dùng dữ liệu sai kiểu.

### “new T[n] bị từ chối thì cứ thay bằng new Object[n] và ép T[]”

Nguy hiểm. Array thật là Object[], còn caller có thể yêu cầu String[]; cast array sẽ thất bại. Cần xem hợp đồng API và runtime component type.

### “new List<?>[n] cho phép đọc mọi phần tử như String”

Sai. Wildcard cho phép đọc một List có type argument chưa biết, nhưng phần tử lấy ra chỉ an toàn ở mức Object nếu không xác minh thêm.

### “ArrayStoreException và ClassCastException là một”

Sai. ArrayStoreException kiểm tra **lúc gán vào array**. ClassCastException kiểm tra **phép ép kiểu không tương thích**, bao gồm khi dùng dữ liệu generic được kỳ vọng là String nhưng thực chất là Integer.

### “Thấy generic array trong tham số method là chắc chắn lỗi”

Sai. `void read(List<String>[] input)` và `<T> void read(T[] input)` có thể là chữ ký hợp lệ; vấn đề nằm ở cách tạo/nhận một array có runtime representation phù hợp và an toàn.

### “Generics không tạo được mảng nên Java không thể làm việc với mảng generic”

Sai. Java có thể khai báo kiểu array chứa generic elements, nhận mảng từ caller, trả mảng theo chữ ký generic, dùng reifiable wildcard arrays, hoặc tạo mảng của lớp runtime đã biết bằng Class token. Điều bị cấm là **một số array creation expressions có component type non-reifiable**, không phải mọi thao tác liên quan mảng.

## 17. Quy trình chọn cách làm

Khi gặp một yêu cầu “cần mảng chứa giá trị generic”, kiểm tra theo thứ tự:

1. **Có thực sự bắt buộc dùng mảng không?** Nếu chỉ muốn danh sách các `List<String>`, `List<List<String>>` thường an toàn và đơn giản.
2. **Component type có reifiable không?** Với String, Integer, List<?> hoặc Map<?, ?>, có thể dùng array creation trực tiếp.
3. **Chỉ đang khai báo biến/tham số/kiểu trả về?** `List<String>[]` hay `T[]` hợp lệ; không cần tạo mảng ở dòng đó.
4. **Đang gọi `new ...[n]`?** Component type phải tuân theo quy tắc array creation, không thể dùng List<String>, List<? extends Number> hay type variable T tùy tiện.
5. **Có runtime component class được caller cung cấp?** Cân nhắc `Class<T>` với `Array.newInstance`.
6. **Có thể nhận mảng từ caller không?** Dùng `T[]` input và sao chép khi cần, tránh tự dựng một array có component type giả định.
7. **Có unchecked cast không?** Xác định rõ runtime array class thật, ai được ghi qua alias, và chuyện gì xảy ra nếu đọc dữ liệu sai generic arguments.
8. **Có varargs non-reifiable không?** Kiểm tra compiler warnings; chỉ sử dụng `@SafeVarargs` nếu phương thức thực sự an toàn.
9. **Có đang dựa vào ArrayStoreException để kiểm tra generic arguments?** Điều đó không đúng: runtime array store chỉ kiểm tra component class/interface có thể nhìn thấy, không xác minh phần tử bên trong collection.
10. **Kiểm thử với compiler mục tiêu** (ví dụ `javac --release 17`) để tránh nhầm giữa lỗi biên dịch và ngoại lệ runtime.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `List<String>[] rows;` hợp lệ nhưng `new List<String>[2]` bị từ chối?

**Đáp án:** Dòng đầu chỉ khai báo array type tại compile time; dòng sau yêu cầu tạo runtime array của non-reifiable component List<String>, không thể kiểm tra generic argument String tại array store.

**Câu 2.** `new List<?>[2]` có hợp lệ không? Điều đó cho phép thêm `List<Integer>` vào array không?

**Đáp án:** Có. List<?> là reifiable và có thể chứa các List với type arguments khác nhau. Từng List được đưa vào mảng đều tương thích với runtime component List.

**Câu 3.** Có gán trực tiếp `List<String>[] a = new List<?>[2];` được không?

**Đáp án:** Không. Kiểu List<?>[] không bảo đảm mỗi phần tử là List<String>; compiler báo incompatible types.

**Câu 4.** Nếu ép `(List<String>[]) new List<?>[2]`, lỗi chắc chắn xảy ra ngay không?

**Đáp án:** Không chắc. Cast có thể được chấp nhận vì array runtime vẫn là List[], nhưng cần unchecked conversion/cast và có nguy cơ heap pollution. Lỗi có thể xảy ra khi đọc dữ liệu không phải String.

**Câu 5.** `new T[2]` trong `class Buffer<T>` có hợp lệ không nếu T extends Number?

**Đáp án:** Không. Bound không cung cấp runtime component type cụ thể của T như Integer[] hay Double[].

**Câu 6.** Phương thức `<T> T[] copy(T[] source)` có nhất thiết sai không?

**Đáp án:** Không. Nó có thể nhận mảng thật đã được caller tạo với component type phù hợp; ví dụ `Arrays.copyOf` có thể tạo bản sao đúng runtime array class của nguồn.

**Câu 7.** Vì sao gán Integer vào `Object[] alias = new String[1]` ném ArrayStoreException, còn gán `List.of(42)` vào Object[] alias của List<?>[] có thể thành công?

**Đáp án:** Runtime component String không chấp nhận Integer. Runtime component List chấp nhận một List bất kể type argument bên trong; generic String không được xác minh tại array store.

**Câu 8.** `@SafeVarargs` có khiến array của List<String> trở nên reifiable không?

**Đáp án:** Không. Đây là annotation truyền đạt cam kết an toàn của phương thức đủ điều kiện, không bổ sung metadata runtime để kiểm tra generic arguments.

**Câu 9.** Nếu muốn cấu trúc nhiều nhóm chuỗi, nên ưu tiên `List<String>[]` hay `List<List<String>>`?

**Đáp án:** Nếu không có yêu cầu API bắt buộc là mảng, `List<List<String>>` thường phù hợp hơn vì có thể khởi tạo bình thường và compiler kiểm tra generic ở mỗi cấp; không cần generic array creation hoặc unchecked cast.

## 19. Ghi nhớ

**Kiểu khai báo không đồng nghĩa với khả năng tạo trực tiếp một đối tượng runtime của kiểu đó.** Java cho phép khai báo `List<String>[]` và `T[]`, nhưng cấm `new List<String>[n]` và `new T[n]` vì phần tử của những array creation expressions đó không có component type reifiable phù hợp.

`new List<?>[n]` hợp lệ vì unbounded wildcard là reifiable; tuy nhiên `List<?>[]` không chứng minh mỗi list chứa String. Mảng giữ runtime component type để phát `ArrayStoreException` khi cần, còn generic arguments thường bị xóa và lỗi sai kiểu có thể bộc lộ thành `ClassCastException` khi dữ liệu được sử dụng.

Trong thiết kế Java hiện đại, hãy ưu tiên **collection lồng nhau có kiểu rõ ràng**, nhận array phù hợp từ caller hoặc dùng `Class<T>` token khi bắt buộc tạo mảng của một component class reifiable. Chỉ dùng unchecked casts khi hiểu được toàn bộ ràng buộc runtime và phạm vi truy cập làm cho chúng thật sự an toàn.
