# Java 7 — Varargs an toàn: Mối liên hệ giữa varargs, mảng và xóa kiểu generic

## 1. Vì sao varargs, array và generics phải được học cùng nhau?

Trong Java, cú pháp **varargs** giúp phương thức nhận số lượng đối số thay đổi, nhưng **bên dưới nó vẫn là một tham số mảng**. Đồng thời, Java dùng **type erasure (xóa kiểu generic)** để triển khai generics. Khi kiểu phần tử của varargs là một kiểu generic **không thể kiểm tra đầy đủ tại runtime** (*non-reifiable*), cách kết hợp này có thể tạo **heap pollution**: biến có kiểu generic trông hợp lệ nhưng thực tế đang tham chiếu một giá trị không đúng với tham số kiểu đã khai báo.

Ba ý nền tảng:

1. `String... words` tương ứng một tham số `String[]`: mảng có thể kiểm tra kiểu phần tử `String` ở runtime.
2. `List<String>... groups` tương ứng một tham số mảng, nhưng runtime chỉ còn kiểm tra được phần tử là `List`, **không kiểm tra được tham số kiểu `String`**.
3. `@SafeVarargs`, được giới thiệu trong Java 7 và vẫn áp dụng trên các JDK hiện đại, là **lời cam kết của tác giả phương thức** rằng cách dùng tham số varargs không gây thao tác generic không an toàn; nó **không** thay thế type erasure bằng reified generics và cũng không khiến compiler tự chứng minh mã là an toàn.

Bài này nói về kỹ thuật Java vẫn đang được sử dụng trên **Java 17+**, không yêu cầu chạy phiên bản JDK 7 đã cũ. Mọi ví dụ dùng API hiện đại đều ghi rõ khi cần; những snippet cố ý sai sẽ được đánh dấu là **không biên dịch** hoặc **gây lỗi runtime**.

## 2. Varargs thực chất là tham số mảng

Khai báo:

```java
static void printWords(String... words) {
    for (String word : words) {
        System.out.println(word);
    }
}
```

Đây là **phương thức minh họa**, cần đặt trong lớp Java. Trong thân phương thức, biến `words` có kiểu **`String[]`**: có `length`, có chỉ số `words[0]`, có thể duyệt bằng enhanced for.

Hai kiểu lời gọi:

```java
printWords("red", "blue");
printWords(new String[] {"red", "blue"});
```

đều hợp lệ. Với lời gọi dùng nhiều đối số riêng lẻ, trình biên dịch chuẩn bị mảng thích hợp để truyền tới phương thức. Lời gọi đã cung cấp mảng cùng kiểu có thể truyền trực tiếp tham chiếu mảng đó; vì vậy **không được mặc định một lời gọi varargs luôn tạo bản sao mảng mới**.

### 2.1. Những quy tắc cú pháp cần biết

- Varargs được viết dạng `Type... parameter` và phải là **tham số hình thức cuối cùng** của phương thức/constructor.
- Một phương thức có tối đa một tham số varargs.
- Có thể gọi với không đối số, một đối số, nhiều đối số hoặc một mảng thích hợp: `f()`, `f(x)`, `f(x,y)`, `f(array)`.
- Lời gọi không đối số theo dạng variable-arity tạo mảng có độ dài 0 cho tham số varargs; nó không mặc định là `null`.
- Khi **truyền mảng có sẵn**, phương thức có thể sửa chính mảng của caller. Điều này đúng ngay cả với varargs không sử dụng generic.

Ví dụ mã minh họa:

```java
static void changeFirst(String... words) {
    words[0] = "changed";
}

String[] source = {"before"};
changeFirst(source);
System.out.println(source[0]); // changed
```

Đoạn trên cần đặt trong một phương thức/lớp phù hợp; caller đã truyền thẳng `source`, nên việc gán `words[0]` được phản ánh trở lại trên mảng gốc. **Không nên sửa tham số varargs nếu API chỉ có ý định đọc.**

### 2.2. Cú pháp gọn không đồng nghĩa collection

`String...` không phải `List<String>` và cũng không tự tạo một tập hợp bất biến. Mảng có kích thước cố định nhưng phần tử có thể thay đổi; danh sách như `List.of(...)` có hợp đồng khác. Khi chọn API, hãy cân nhắc muốn nhận **nhiều đối số tiện lợi** hay nhận một **collection có vòng đời rõ ràng**.

## 3. Generics là thông tin kiểu ở compile-time; type erasure tác động thế nào?

Java generics giúp phát hiện nhiều lỗi kiểu khi biên dịch:

```java
List<String> names = new java.util.ArrayList<>();
names.add("Alice");
// names.add(42); // Không biên dịch: Integer không phải String.
```

Nhưng ở runtime, JVM không giữ `String` dưới dạng kiểu phần tử riêng trong một instance `List<String>`. Các biểu diễn `List<String>` và `List<Integer>` đều sử dụng class runtime là `java.util.List`/implementation tương ứng. Tham số kiểu generic bị **erased** theo các quy tắc của ngôn ngữ; compiler bổ sung cast khi cần ở vị trí sử dụng giá trị.

Ví dụ:

```java
List<String> names = List.of("Alice");
String first = names.get(0);
```

Đây là snippet trong một phương thức, Java 17+. Compiler đảm bảo tại mã nguồn rằng `names.get(0)` được dùng như `String` và có thể chèn cast phù hợp ở runtime. Nếu một thao tác không an toàn đã khiến danh sách thực tế chứa `Integer`, cast ở bước đọc có thể ném `ClassCastException`.

### 3.1. Type erasure không có nghĩa compiler bỏ qua generic

Compiler **vẫn kiểm tra** các ràng buộc generic tại compile-time. Type erasure ảnh hưởng đến cách thực thi và những điều có thể kiểm tra ở runtime. Sự khác nhau quan trọng:

| Vấn đề | Compile-time | Runtime |
| --- | --- | --- |
| `List<String>` và `List<Integer>` | Là các kiểu tham số hóa khác nhau | Cùng chung raw generic class, không có runtime check riêng cho `String`/`Integer` |
| `String[]` | Biết phần tử là `String` | Component type `String` còn hiện diện và JVM kiểm tra khi gán |
| `List<String>[]` | Kiểu mảng tham số hóa có thể xuất hiện trong khai báo | Không thể tạo trực tiếp bằng `new List<String>[n]` |
| `List<?>[]` | Hợp lệ để tạo mảng | Runtime biết component là `List`; wildcard không cam kết một kiểu phần tử cụ thể |
| `T[]` trong phương thức generic | Có thể dùng làm kiểu tham số/biến tham chiếu | Không thể tạo bằng `new T[n]` thông thường vì không có reified component type cho `T` |

Đừng hiểu “erasure” thành “Java không an toàn kiểu”. Những lỗi runtime xuất hiện khi ta đi qua điểm không thể kiểm tra kiểu generic đầy đủ, dùng raw type, cast unchecked, hoặc tạo **heap pollution**.

## 4. Reifiable và non-reifiable: ranh giới kiểm tra runtime

Một kiểu được gọi là **reifiable** khi thông tin kiểu cần thiết của nó đủ hiện diện để phân biệt ở runtime theo quy tắc JLS.

Ví dụ reifiable (theo ngữ cảnh dùng làm phần tử mảng):

- `String`, `Integer`, các kiểu primitive và các lớp thông thường.
- Raw type như `List`.
- Parameterized type với **toàn bộ type arguments là wildcard không giới hạn**, ví dụ `List<?>`.
- Mảng có component type reifiable, ví dụ `String[]`, `List<?>[]`.

Ví dụ **non-reifiable**:

- `List<String>`, `List<Integer>`, `Map<String,Integer>`.
- Các type variable như `T` không giữ được một kiểu component runtime cụ thể.
- Mảng có component type là parameterized type non-reifiable như `List<String>[]`.

Đây không phải quy ước tùy chọn: nó lý giải tại sao **JVM có thể kiểm tra việc ghi một `Integer` vào `String[]` nhưng không thể kiểm tra nội dung generic của một `List<Integer>` khi đối tượng đó được ghi vào `List[]`.**

## 5. Mảng có runtime component type, generics có type erasure

### 5.1. Mảng là covariant, đồng thời có kiểm tra kiểu khi ghi

```java
Object[] values = new String[1];
values[0] = "ok"; // Hợp lệ.
values[0] = 42;   // Runtime: ArrayStoreException.
```

Đây là **snippet cố ý có lỗi runtime** ở dòng cuối. Một `String[]` có thể được tham chiếu qua `Object[]` vì mảng có tính covariant, nhưng đối tượng mảng vẫn nhớ component type `String`; JVM từ chối việc ghi một `Integer` vào mảng đó.

### 5.2. Generic thông thường là invariant

```java
List<String> strings = new java.util.ArrayList<>();
// List<Object> objects = strings; // Không biên dịch.
```

`List<String>` **không** tự là subtype của `List<Object>`. Nếu Java cho phép phép gán này, ta có thể thêm `Integer` qua `List<Object>` rồi đọc từ `List<String>` như `String`. Generics ngăn tình huống này tại compile-time, trừ khi mã dùng các thao tác không an toàn để vượt rào.

### 5.3. Khi phần tử là generic List, kiểm tra của mảng không đủ sâu

```java
List[] runtimeArray = new List[1];
runtimeArray[0] = List.of(42); // Runtime chấp nhận: đây vẫn là một List.
```

Snippet Java 17+ này hợp lệ. Ở runtime, component type của mảng là `List`, **không phải `List<String>`**. Nếu một tham chiếu có kiểu `List<String>[]` (có được qua một thao tác không an toàn) cùng trỏ tới mảng trên, chương trình có thể gặp `ClassCastException` lúc đọc phần tử tưởng là String.

## 6. Varargs generic biến vấn đề thành một tình huống dễ gặp

Xét phương thức:

```java
static void processGroups(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

Đây là **phương thức minh họa**. Mặt cú pháp, `groups` là một mảng có kiểu khai báo `List<String>[]`. Nhưng lúc chạy, mảng được tạo cho lời gọi kiểu này có component runtime chỉ là `List`. Java có thể phát cảnh báo:

- **Ở vị trí khai báo:** `Possible heap pollution from parameterized vararg type ...`.
- **Ở vị trí lời gọi dạng variable-arity:** `unchecked generic array creation for varargs parameter ...`.

Thông báo chính xác phụ thuộc compiler và cờ kiểm tra, nhưng ý nghĩa là: compiler không thể tự chứng minh mọi thao tác với mảng generic này an toàn.

Một lời gọi như:

```java
processGroups(List.of("first"), List.of("second"));
```

hợp lệ nếu đặt trong lớp có phương thức trên, nhưng có thể phát cảnh báo vì lời gọi phải tạo mảng varargs chứa `List<String>` mà JVM không kiểm tra được tham số generic `String` ở component runtime.

**Rất quan trọng:** Cảnh báo **không đồng nghĩa phương thức chắc chắn bị lỗi**. Nhiều phương thức chỉ duyệt và đọc đúng kiểu vẫn hoạt động an toàn. Cảnh báo nói rằng thiết kế có **khả năng** rơi vào tình huống không an toàn nếu mảng bị sửa hoặc bị để lộ sai cách. Trách nhiệm xác minh thuộc về tác giả phương thức.

## 7. Heap pollution: cách một List<Integer> lọt vào vị trí List<String>

Đây là ví dụ **cố ý không an toàn**:

```java
static void unsafe(List<String>... groups) {
    Object[] alias = groups;    // Mảng generic được nhìn qua Object[].
    alias[0] = List.of(42);     // Runtime cho phép: component chỉ là List.
    String value = groups[0].get(0); // Runtime: ClassCastException.
    System.out.println(value);
}
```

Phân tích tuần tự:

1. `groups` có kiểu khai báo `List<String>[]` nhưng runtime array component là `List`.
2. Vì mảng Java covariant, tham chiếu qua `Object[] alias` là hợp lệ.
3. `alias[0] = List.of(42)` chèn một danh sách có phần tử `Integer`. JVM chỉ kiểm tra đối tượng này là `List`, nên **không ném `ArrayStoreException`**.
4. Sau đó compiler tin rằng `groups[0]` chứa `String`; phép đọc vào biến `String` có cast tương ứng.
5. Cast gặp `Integer` và ném **`ClassCastException`**.

Điều này gọi là **heap pollution**: tham chiếu với kiểu generic đã khai báo trỏ đến dữ liệu không thỏa kiểu đó, do ta đi qua một thao tác không được kiểm tra đầy đủ.

### 7.1. Phân biệt hai ngoại lệ runtime

| Lỗi | Ví dụ | Vì sao xảy ra? |
| --- | --- | --- |
| `ArrayStoreException` | Ghi `Integer` vào `String[]` thông qua `Object[]` | JVM biết component type runtime là `String` và từ chối ngay tại thao tác ghi. |
| `ClassCastException` | Đọc `Integer` như `String` sau khi làm ô `List<String>` chứa `List<Integer>` | Mảng có component `List` nên ghi lọt; cast ở bước đọc mới phát hiện sai kiểu. |

Không phải mọi `ClassCastException` đều do varargs, nhưng kết hợp varargs generic và alias mảng là một nguồn lỗi điển hình mà Java 7 hỗ trợ cảnh báo và annotation để quản lý.

### 7.2. Vì sao không thể `new List<String>[2]`?

```java
List<String>[] bad = new List<String>[2]; // Không biên dịch.
```

Đây là snippet **cố ý sai compile-time**: Java không cho tạo mảng trực tiếp với component type generic non-reifiable, bởi runtime không có cơ chế kiểm tra đầy đủ mọi lần ghi theo `String`.

Trong khi đó:

```java
List<?>[] allowed = new List<?>[2];
allowed[0] = List.of("hello");
allowed[1] = List.of(42);
```

Snippet Java 17+ này hợp lệ vì `List<?>` không khẳng định mọi phần tử phải là String; hai danh sách được phép có các tham số kiểu khác nhau. Khi đọc `allowed[1].get(0)`, kiểu suy ra an toàn chỉ là `Object` (trừ khi ta kiểm tra/cast thêm), không phải String.

**Không nên dùng raw `List[]` hoặc cast unchecked chỉ để qua compiler** nếu bài toán có thể biểu diễn bằng `List<List<String>>` hoặc một collection generic thông thường.

## 8. @SafeVarargs giải quyết cảnh báo theo một lời cam kết, không xóa rủi ro

`@SafeVarargs` là annotation chuẩn có từ Java 7. Áp dụng đúng nghĩa: *“Tôi đã kiểm tra và bảo đảm implementation của phương thức/constructor varargs không thực hiện thao tác không an toàn với các đối số thuộc kiểu non-reifiable.”*

Ví dụ thực sự an toàn:

```java
@SafeVarargs
static <T> List<T> safeCopy(T... items) {
    return new java.util.ArrayList<>(
            java.util.Arrays.asList(items));
}
```

Đây là **phương thức minh họa**, đặt trong lớp có import `java.util.List`. Nó chỉ đọc phần tử rồi tạo một **`ArrayList` mới**, không gán các đối tượng sai kiểu vào mảng, không trả tham chiếu mảng cho caller, không đưa mảng vào một phương thức không tin cậy. Dù `Arrays.asList(items)` tạo một view dùng mảng nền, constructor của `ArrayList` sao chép nội dung trước khi trả về nên danh sách kết quả không phải view trực tiếp của mảng varargs.

Giả sử:

```java
String[] source = {"before"};
List<String> copied = safeCopy(source);
source[0] = "after";
System.out.println(copied.get(0)); // before
```

Snippet trong phương thức Java 17+ cho thấy bản sao không bị ảnh hưởng khi caller thay phần tử mảng ban đầu. Nó cũng minh họa **lời gọi varargs có thể nhận một mảng đã tồn tại**: cách viết của method cần an toàn cho cả trường hợp đó.

### 8.1. Điều kiện để được dùng @SafeVarargs

Trên Java 17+, annotation được phép dùng ở **constructor** hoặc phương thức varargs **không thể bị override** theo các trường hợp mà ngôn ngữ cho phép, gồm:

- phương thức `static`;
- phương thức instance `final`;
- phương thức instance `private` (được cho phép từ Java 9);
- constructor có tham số varargs.

**Không thể gắn `@SafeVarargs` lên một phương thức instance có thể bị override** như `public void method(T... args)` không `final`, vì subclass có thể thay đổi implementation và phá cam kết. Cũng không thể dùng annotation này cho phương thức không khai báo varargs.

Nếu parameter đã là kiểu reifiable như `String...`, thông thường không cần `@SafeVarargs`; compiler không có cảnh báo non-reifiable tương ứng để triệt tiêu. Không gắn annotation cho mọi phương thức có dấu `...` một cách máy móc.

### 8.2. Annotation không tự kiểm chứng an toàn

Ví dụ sau dùng annotation **sai mục đích**:

```java
@SafeVarargs
static void wronglyTrusted(List<String>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(42); // Hành vi không an toàn vẫn tồn tại.
}
```

Nếu phương thức có chú thích này rồi được gọi trong ngữ cảnh mong đợi `List<String>`, heap pollution vẫn có thể xảy ra. Annotation có thể làm một số cảnh báo tại khai báo/lời gọi biến mất nhưng **không thay đổi runtime representation** và không cấm thực thi thao tác sai. Thậm chí code trong thân phương thức có thể sinh cảnh báo khác, tùy compiler.

Vì vậy, **không dùng `@SafeVarargs` như một cách “tắt cảnh báo cho build xanh”** khi chưa chứng minh implementation an toàn.

### 8.3. Còn @SuppressWarnings thì sao?

`@SuppressWarnings("unchecked")` (và trong một số trường hợp `"varargs"`) cũng có thể giảm cảnh báo, nhưng nó là một công cụ triệt tiêu cảnh báo theo phạm vi khai báo, **không phải cam kết API dành cho lời gọi varargs như `@SafeVarargs`**. Với việc phải dùng cast unchecked có kiểm chứng ở một vị trí nhỏ, hãy giới hạn suppression đúng tại đó và giải thích bằng invariant rõ ràng.

Nếu thiết kế cho phép loại bỏ hẳn varargs generic không an toàn, đó thường là lựa chọn tốt hơn việc suppress hàng loạt.

## 9. Cách viết một phương thức generic varargs an toàn

Một phương thức có thể phù hợp với `@SafeVarargs` khi:

1. **Không ghi sai kiểu vào mảng tham số.** Tránh gán một `List<Integer>` vào vị trí dự kiến chứa `List<String>` thông qua `Object[]` hoặc raw type.
2. **Không trả trực tiếp hoặc làm rò rỉ mảng varargs** sang nơi có thể sửa nó không đúng cách; tránh giữ tham chiếu mảng trong trạng thái dài hạn không kiểm soát.
3. **Không truyền mảng này vào mã không tin cậy** có thể ghi phần tử sai kiểu. Một method chỉ đọc array không tự chứng minh rằng method khác được gọi cũng chỉ đọc.
4. **Không cast unchecked vô căn cứ** như `(List<String>[]) new List<?>[n]` rồi để code khác tin rằng cast đã được kiểm tra.
5. **Hiểu rõ ai có quyền sửa dữ liệu đầu vào.** Nếu caller có thể truyền mảng sẵn có, implementation không nên biến đổi mảng đó trái hợp đồng.
6. **Kiểm tra tất cả overload, đường exception và các lời gọi khác** trong method, không chỉ happy path.
7. **Biên dịch với cảnh báo được bật, review annotation**; ghi test cho những đường ghi và alias mảng nếu có.

Với một phương thức chỉ đọc từng phần tử rồi tạo danh sách riêng, khả năng đảm bảo an toàn thường rõ ràng hơn phương thức trả về mảng hoặc lưu mảng vào field.

### 9.1. Copy và view là hai chuyện khác nhau

```java
@SafeVarargs
static <T> List<T> newList(T... elements) {
    return new java.util.ArrayList<>(
            java.util.Arrays.asList(elements));
}
```

Đây là method minh họa. Nó **copy** phần tử vào danh sách mới. Nếu thay bằng `return Arrays.asList(elements);`, danh sách trả về sẽ là view được hỗ trợ bởi mảng `elements`. Điều đó không nhất thiết tự động dẫn đến heap pollution trong mọi ngữ cảnh, nhưng nó **làm mảng varargs có thể bị thay đổi thông qua view**, nên không thể mặc định an toàn cho mọi kiểu T và mọi caller. Một khi cần annotation, hãy phân tích kỹ bất cứ đường nào khiến mảng varargs thoát ra ngoài method.

**Quan trọng:** copy nông các **phần tử**, không clone sâu các object bên trong. Nếu phần tử là đối tượng mutable, bản sao danh sách vẫn tham chiếu cùng phần tử đó. An toàn với heap pollution của mảng không đồng nghĩa immutable toàn bộ đồ thị đối tượng.

### 9.2. Đọc thuần trên mảng đầu vào có thể hợp lệ

```java
@SafeVarargs
static void printGroupSizes(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

Đây là method minh họa, không độc lập. Nó chỉ đọc độ dài danh sách và không dùng `Object[]` để ghi sai, không trả mảng ra ngoài. Nhưng nếu code thực tế thêm việc gán, lưu mảng vào field hoặc gửi sang handler khác, cam kết phải được review lại.

## 10. Ví dụ Java 17+ hoàn chỉnh: runtime type, copy an toàn, heap pollution

Tạo tệp **`VarargsErasureDemo.java`** sau. Phần `unsafe` được **cố ý giữ không an toàn để tái hiện lỗi**; không dùng mô hình đó trong production.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class VarargsErasureDemo {
    static void strings(String... words) {
        System.out.println("String component: "
                + words.getClass().getComponentType().getTypeName());
    }

    @SafeVarargs
    static <T> List<T> safeCopy(T... items) {
        return new ArrayList<>(Arrays.asList(items));
    }

    @SafeVarargs
    static void readGroups(List<String>... groups) {
        System.out.println("List component: "
                + groups.getClass().getComponentType().getTypeName());
        System.out.println("First: " + groups[0].get(0));
    }

    static void unsafe(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(42);
        String value = groups[0].get(0);
        System.out.println(value);
    }

    public static void main(String[] args) {
        strings("one", "two");
        List<String> group = List.of("alpha");
        readGroups(group);
        System.out.println("Safe copy: " + safeCopy("red", "blue"));

        String[] original = {"before"};
        List<String> copied = safeCopy(original);
        original[0] = "after";
        System.out.println("Independent copy: " + copied.get(0));

        try {
            unsafe(group);
        } catch (ClassCastException ex) {
            System.out.println("Unsafe: " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy trên JDK 17+ và bật cảnh báo:

```bash
javac --release 17 -Xlint:unchecked VarargsErasureDemo.java
java VarargsErasureDemo
```

Trong pha **biên dịch**, `javac` sẽ cảnh báo về `List<String>...` trong `unsafe` và lời gọi `unsafe(group)`, theo định dạng phụ thuộc phiên bản compiler. Đây là các **cảnh báo**, không phải dòng stdout của chương trình.

**Stdout chính xác khi chạy:**

```text
String component: java.lang.String
List component: java.util.List
First: alpha
Safe copy: [red, blue]
Independent copy: before
Unsafe: ClassCastException
```

### 10.1. Phân tích từng dòng

- `String component: java.lang.String`: varargs `String...` nhận mảng với component runtime là `String`.
- `List component: java.util.List`: `List<String>...` ở runtime chỉ kiểm tra được component `List`, không còn type argument `String`.
- `First: alpha`: `readGroups` chỉ đọc dữ liệu đúng kiểu, không có heap pollution trong lời gọi đó.
- `Safe copy: [red, blue]`: method `safeCopy` tạo danh sách riêng từ varargs.
- `Independent copy: before`: khi caller truyền sẵn `String[] original` rồi sửa nó, danh sách đã copy không đổi.
- `Unsafe: ClassCastException`: ghi một `List<Integer>` thông qua `Object[]` làm dữ liệu không còn phù hợp với `List<String>[]`. Khi đọc số 42 dưới dạng String, cast thất bại; khối catch trong demo bắt lỗi để chương trình kết thúc có kiểm soát.

**Mục đích học tập:** Quan sát chính xác rằng việc khai báo `List<String>...` trông type-safe nhưng vẫn có thể bị phá vỡ bằng thao tác qua array alias. Trong code thật, phải **loại bỏ thao tác không an toàn** chứ không dựa vào `catch (ClassCastException)` để xử lý hậu quả.

## 11. Tại sao kiểm thử compile warning quan trọng?

Với varargs có phần tử non-reifiable, cảnh báo compiler là tín hiệu về ranh giới không thể chứng minh hoàn toàn bằng hệ kiểu. Hãy bật kiểm tra:

```bash
javac --release 17 -Xlint:unchecked VarargsErasureDemo.java
```

Một số dự án còn dùng `-Xlint:varargs` để hiển thị cảnh báo liên quan đến hành vi varargs trong thân phương thức, kể cả khi có `@SafeVarargs` trong một số trường hợp. Đừng giả định bật annotation nghĩa là không còn bất cứ điều gì đáng xem xét.

Quy trình đọc warning:

1. **Đọc chữ ký phương thức:** kiểu phần tử `String` (reifiable) hay `List<String>`/`T` (non-reifiable)?
2. **Xác định vị trí cảnh báo:** khai báo, callsite hay thao tác trong thân phương thức?
3. **Xem có mutation/alias/leak array không:** cast sang `Object[]`, gán phần tử, lưu vào field, trả mảng hoặc view được backed bởi mảng.
4. **Nếu thật sự safe:** viết unit tests, ghi bất biến (invariant) và chỉ dùng `@SafeVarargs` tại method/constructor hợp lệ.
5. **Nếu không thể chứng minh:** đổi API sang collection hoặc copy dữ liệu để không phụ thuộc vào mảng generic non-reifiable.

Không dùng `-Xlint:none` hoặc suppress toàn dự án để “giải quyết” vấn đề; nó chỉ ẩn thông tin từ compiler.

## 12. Khi nào nên thay generic varargs bằng Collection/List?

Không phải API nào nhận nhiều nhóm dữ liệu cũng cần varargs. Với tập các danh sách được xử lý như một collection, chữ ký:

```java
static void processGroups(List<List<String>> groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

là một lựa chọn đơn giản, không tạo mảng varargs có phần tử `List<String>`. Snippet là method minh họa.

Lời gọi:

```java
processGroups(List.of(
        List.of("red", "blue"),
        List.of("green")));
```

Đây là code Java 17+ khi đặt trong lớp có method trên. API có thể dùng `Collection<? extends List<String>>` nếu cần chấp nhận nhiều loại collection và phù hợp nhu cầu; không nên dùng wildcard quá phức tạp khi không cần.

### 12.1. Bảng quyết định

| Bài toán | Thiết kế tham khảo | Lý do |
| --- | --- | --- |
| Nhận vài chuỗi, số nguyên hoặc giá trị thông thường | `String...`, `int...` | Kiểu phần tử reifiable, cú pháp tiện lợi. |
| Tạo bản sao của nhiều phần tử generic | `@SafeVarargs static <T> List<T> copy(T... items)` | Nếu implementation copy và không gây alias/leak không an toàn. |
| Nhận nhiều `List<String>`, chỉ đọc trong helper | `@SafeVarargs` trên method được phép | Cần review bảo đảm không heap pollution; có thể hợp lý để hỗ trợ callsite tiện lợi. |
| Nhận bộ sưu tập danh sách để xử lý theo pipeline | `List<List<String>>` hoặc `Collection<...>` | Không cần array generic varargs; mô tả cấu trúc dữ liệu rõ. |
| Muốn lưu danh sách phần tử lâu dài | `List<T>`/copy phù hợp | Không giữ tham chiếu mảng varargs của caller khi chưa kiểm soát ownership. |
| Cần component type runtime chính xác để tạo mảng | Truyền `IntFunction<T[]>`/factory hoặc `Class<T>` trong trường hợp phù hợp | Type erasure không cho phép `new T[n]` thông thường; factory cho caller xác định mảng cụ thể. |

**Không có nguyên tắc “generic varargs luôn sai”.** Tính an toàn đến từ implementation và hợp đồng API. Nếu phương thức chỉ tạo dữ liệu dùng ngay và không làm rò rỉ mảng, varargs generic có thể hợp lý. Nếu phương thức dùng một tập động lớn, cần nhiều phép biến đổi/stream hoặc muốn tránh generic array, collection thường biểu đạt tốt hơn.

## 13. Những ngộ nhận thường gặp

**Ngộ nhận 1 — “Varargs là List.”** Sai. Ở cấp khai báo phương thức và runtime, varargs là array; `List` là một API collection riêng.

**Ngộ nhận 2 — “Generic `List<String>` giữ nguyên kiểu String ở runtime.”** Không theo mô hình generics Java: type erasure không giữ `String` như runtime type argument được dùng để kiểm tra mảng.

**Ngộ nhận 3 — “`new List<String>[10]` chắc chắn chạy vì List là class hợp lệ.”** Không. Tạo array với component generic non-reifiable là lỗi biên dịch.

**Ngộ nhận 4 — “`String[]` và `List<String>[]` an toàn runtime như nhau.”** Không. `String[]` kiểm tra runtime component type `String`; `List<String>[]` không có runtime component mang đầy đủ tham số String.

**Ngộ nhận 5 — “ArrayStoreException và ClassCastException là một.”** Không. ArrayStoreException xảy ra khi cố ghi phần tử sai runtime component type; ClassCastException có thể xảy ra muộn hơn khi đọc dữ liệu đã bị heap pollution.

**Ngộ nhận 6 — “Compiler cảnh báo đồng nghĩa mã chắc chắn lỗi.”** Không. Cảnh báo cho biết chưa thể chứng minh an toàn tự động; code chỉ đọc có thể hợp lệ sau review.

**Ngộ nhận 7 — “Chỉ cần thêm @SafeVarargs là JVM kiểm tra generic array.”** Không. Annotation không đổi biểu diễn runtime hay tạo reified generics; nó là một cam kết có trách nhiệm của tác giả.

**Ngộ nhận 8 — “@SafeVarargs dùng được ở mọi method overridable.”** Không. Chỉ constructor hoặc phương thức thuộc nhóm được JLS cho phép như static/final/private trên JDK hiện đại.

**Ngộ nhận 9 — “Truyền String[] cho String... luôn tạo mảng mới.”** Không. Existing array có thể truyền trực tiếp; nếu method sửa phần tử, caller quan sát được thay đổi.

**Ngộ nhận 10 — “`Arrays.asList(items)` luôn là bản sao độc lập.”** Không. Nó là list view backed bởi array; muốn bản sao, có thể tạo `new ArrayList<>(Arrays.asList(items))`.

**Ngộ nhận 11 — “Raw type giúp giải quyết cảnh báo an toàn hơn.”** Không. Raw type loại bỏ nhiều kiểm tra compile-time; cần hạn chế hoặc bỏ dùng nếu có generic API phù hợp.

**Ngộ nhận 12 — “Có thể bắt ClassCastException để hợp thức hóa logic unsafe.”** Không. Cần sửa nguồn heap pollution, không chỉ che lỗi tại điểm đọc.

## 14. Checklist khi review một API varargs generic

Trước khi thêm `@SafeVarargs` hoặc nhận một phương thức có `T...`/`List<T>...`:

1. **Biết chính xác tham số là mảng:** `T...` tạo `T[]` ở khai báo; nó không phải collection.
2. **Phân loại kiểu phần tử:** reifiable hay non-reifiable?
3. **Rà soát thao tác ghi:** có mượn alias `Object[]` hoặc raw array để thay phần tử không?
4. **Rà soát tham chiếu thoát ra:** có trả array, lưu array trong field, đăng ký callback hoặc trả view backed bởi array không?
5. **Rà soát lời gọi thứ cấp:** array có được chuyển cho method khác có thể mutate hay giữ lại không?
6. **Kiểm tra ownership:** caller có thể truyền mảng sẵn có; method có được phép sửa nó không?
7. **Bật compiler warnings:** tối thiểu `-Xlint:unchecked`, cân nhắc `-Xlint:varargs`.
8. **Chỉ thêm @SafeVarargs khi chứng minh được:** method/constructor hợp lệ và toàn bộ đường đi không tạo heap pollution hoặc rò rỉ mảng một cách không an toàn.
9. **Cân nhắc API không dùng varargs:** `Collection<T>`, `List<T>`, `List<List<T>>` hoặc một kiểu domain phù hợp.
10. **Test cả lời gọi với mảng có sẵn:** không chỉ test các đối số rời rạc; xác nhận kết quả có copy khi hợp đồng yêu cầu.
11. **Giữ lỗi đúng tầng:** một `ClassCastException` xuất hiện muộn có thể do thao tác unchecked ở nơi khác; tìm nguồn ô nhiễm kiểu thay vì chỉ xử lý lỗi đọc.
12. **Dùng JDK hiện đại:** các quy tắc từ Java 7 vẫn được giữ trong Java 17+, nhưng code dự án nên biên dịch đúng release mục tiêu.

## 15. Câu hỏi tự kiểm tra

**1.** `static void f(String... s)` nhận tham số nào bên trong thân method? — **`String[]`**. Nó có `length` và có thể lấy `s[0]`.

**2.** Tại sao `List<String>...` phát cảnh báo? — Vì component generic `List<String>` non-reifiable; array runtime chỉ kiểm tra được `List`, không kiểm tra được đối số kiểu `String`.

**3.** `new List<String>[2]` có hợp lệ không? — **Không**, là lỗi generic array creation tại compile-time.

**4.** `new List<?>[2]` có hợp lệ không? — **Có**. Kiểu component `List<?>` là reifiable; mỗi phần tử list có thể chứa dữ liệu với generic type khác nhau.

**5.** `Object[] a = new String[1]; a[0] = 42;` gây lỗi gì? — **`ArrayStoreException`** ngay tại phép ghi.

**6.** Qua `Object[]` alias của một array có runtime component `List`, ghi `List<Integer>` vào chỗ dự kiến `List<String>` có chắc ném ArrayStoreException không? — **Không**. Runtime chỉ kiểm tra được `List`; lỗi có thể phát sinh về sau khi đọc/cast.

**7.** Annotation `@SafeVarargs` có làm JVM hiểu `List<String>` khác `List<Integer>` ở runtime không? — **Không**, nó chỉ là cam kết từ tác giả và tác động tới cảnh báo compiler.

**8.** Method `static <T> List<T> copy(T... items)` sao chép mọi phần tử vào `ArrayList` mới và không làm rò array có thể dùng `@SafeVarargs` không? — **Có**, nếu mọi đường thực thi thực sự không dùng mảng không an toàn.

**9.** Instance method public, không final, có thể override, được gắn `@SafeVarargs` không? — **Không**, method phải thuộc nhóm được phép theo JLS.

**10.** Caller truyền `String[] arr` trực tiếp cho method `f(String... s)`. Method sửa `s[0]`, caller có thấy không? — **Có thể thấy**, vì mảng được truyền bằng tham chiếu; không mặc định có copy.

**11.** Khi nào nên dùng `List<List<String>>` thay cho `List<String>...`? — Khi API bản chất nhận một collection của nhiều nhóm, muốn tránh generic array creation và có semantics collection rõ ràng.

**12.** Nếu compile warning biến mất sau khi thêm `@SafeVarargs`, điều đó chứng minh method an toàn chưa? — **Chưa**. Phải review write/alias/leak/call chain và kiểm thử.

## Tài liệu chính thức (quy tắc còn áp dụng)

- [Java Language Specification 17 §8.4.1 — Formal Parameters, Variable Arity](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): cú pháp và quy tắc varargs.
- [Java Language Specification 17 §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): cách xóa kiểu generic.
- [Java Language Specification 17 §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): khái niệm reifiable/non-reifiable.
- [Java Language Specification 17 §9.6.4.7 — @SafeVarargs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.7): điều kiện sử dụng annotation và hành vi liên quan cảnh báo.
- [Java SE 17 API — SafeVarargs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): ý nghĩa cam kết và lưu ý an toàn.
- [Java Language Specification 17 §10 — Arrays](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html): component type và quy tắc mảng.
- [Java SE 17 API — Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): danh sách backed bởi array; phân biệt với copy thực sự.

**Ghi nhớ:** **Varargs dùng mảng; generic type arguments bị xóa ở runtime.** Với `String...`, component type runtime đầy đủ; với `List<String>...`, mảng chỉ biết phần tử là `List`. Hãy loại bỏ alias/write không an toàn, không làm lộ mảng, dùng `@SafeVarargs` chỉ khi có cơ sở kiểm chứng và chọn `List/Collection` khi đó mới là mô hình dữ liệu phù hợp.