# Quan hệ giữa kiểm tra kiểu lúc biên dịch và dữ liệu lúc chạy trong Java Generics

Java Generics cho phép diễn đạt và kiểm tra quan hệ kiểu ngay trong mã nguồn, nhưng phần lớn đối số kiểu (như `String` trong `List<String>`) không trở thành thông tin kiểu riêng của từng đối tượng ở runtime. Để hiểu đúng Generics, phải phân biệt **kiểu tĩnh mà trình biên dịch kiểm tra** với **lớp và giá trị thực sự tồn tại khi JVM chạy**.

## 1. Hai tầng thông tin kiểu

- **Compile time (thời điểm biên dịch):** `javac` dựa vào khai báo `List<String>`, `Box<Integer>`, kiểu tham số phương thức, giới hạn `extends` và wildcard để kiểm tra phép gán, lời gọi phương thức, phần tử có thể thêm vào collection và kiểu giá trị trả về. Mục tiêu là phát hiện nhiều sai sót trước khi chạy.
- **Runtime (thời điểm chạy):** JVM làm việc với đối tượng thực tế như `ArrayList`, `String`, `Integer`; kiểm tra ép kiểu (`checkcast`), truy cập mảng (`aastore`), virtual dispatch và các quy tắc runtime khác. JVM không tự biết một đối tượng `new ArrayList<>()` hiện đang mang đối số kiểu `String` chỉ vì biến tham chiếu được khai báo `List<String>`.
- **Type erasure (xóa kiểu):** Java thường biên dịch đối số kiểu generic sang kiểu đã xóa: `List<String>` và `List<Integer>` cùng dùng lớp runtime `List`/`ArrayList` tương ứng. Biến kiểu `T` thường bị thay bằng cận trên của nó, hoặc `Object` nếu không có cận trên tường minh. Trình biên dịch chèn ép kiểu khi cần và có thể sinh bridge method để bảo toàn đa hình.

Điều này không có nghĩa Java “mất hết kiểm tra kiểu” ở runtime: runtime vẫn kiểm tra kiểu đối tượng và phép cast có thể gây `ClassCastException`. Điều bị xóa chủ yếu là **đối số kiểu của generic**, chẳng hạn `String` trong `List<String>`.

| Câu hỏi | Compile time | Runtime |
| --- | --- | --- |
| Có được gọi `names.add(123)` khi `names` là `List<String>`? | Không, lỗi biên dịch. | Không có cơ hội chạy nếu mã không biên dịch. |
| Đối tượng là `ArrayList` hay `LinkedList`? | Biết theo kiểu khởi tạo/luồng phân tích nếu đủ thông tin. | Xác định bằng lớp thực tế của đối tượng. |
| Một `ArrayList` mang `String` hay `Integer`? | Dùng khai báo generic để ràng buộc thao tác. | Bản thân đối tượng thông thường không giữ thông tin đối số kiểu đó. |
| `String name = names.get(0)` có an toàn tuyệt đối? | Hợp lệ khi giả định danh sách tuân thủ `List<String>`. | Cast do compiler chèn có thể thất bại nếu danh sách đã bị làm bẩn. |
| Có thể đọc `List<String>` từ khai báo trường? | Có trong mô hình type của compiler. | Reflection có thể đọc generic signature của **khai báo**, nếu metadata hiện diện; khác với đối số kiểu của từng đối tượng. |

## 2. Quan sát một chương trình chạy được

Tạo tệp `GenericsAtRuntime.java`:

```java
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;

public class GenericsAtRuntime {
    static class Catalog {
        List<String> titles = new ArrayList<>();
    }

    public static void main(String[] args) throws Exception {
        List<String> titles = new ArrayList<>();
        titles.add("java");

        String title = titles.get(0);
        System.out.println(title.toUpperCase());

        ArrayList<Integer> counts = new ArrayList<>();
        System.out.println(titles.getClass() == counts.getClass());
        System.out.println(titles instanceof List<?>);

        Field field = Catalog.class.getDeclaredField("titles");
        System.out.println(field.getGenericType().getTypeName());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac GenericsAtRuntime.java
java GenericsAtRuntime
```

Kết quả chuẩn (`stdout`):

```text
JAVA
true
true
java.util.List<java.lang.String>
```

Giải thích lần lượt:

1. `titles.add("java")` và `String title = titles.get(0)` được kiểm tra theo hợp đồng `List<String>` ở compile time.
2. `titles` và `counts` đều được khởi tạo bằng `new ArrayList<>()`. Đối số kiểu ở nguồn khác nhau nhưng lớp runtime vẫn cùng là `java.util.ArrayList`, nên phép so sánh `Class` trả về `true`.
3. `instanceof List<?>` hợp lệ: `List<?>` là một kiểu *reifiable* dùng được cho phép kiểm tra runtime. Điều này chỉ kiểm tra đối tượng có thực thi `List`; không xác minh kiểu phần tử.
4. `Field.getGenericType()` lấy metadata của **trường được khai báo** `Catalog.titles`, nên đọc được `List<String>`. Metadata này không chứng minh từng phần tử trong danh sách hiện đều là `String`.

Cần phân biệt `List<String> titles = new ArrayList<>();` với `new ArrayList<String>()`: cú pháp diamond `<>` yêu cầu compiler suy luận đối số kiểu, không thay đổi bản chất type erasure.

## 3. Type erasure hoạt động như thế nào?

Xét mã nguồn minh họa:

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class NumberBox<T extends Number> {
    T value;
}
```

Ở mức hình dung cấu trúc đã xóa kiểu:

```java
// Chỉ là mô hình giải thích sau erasure,
// không phải toàn bộ mã nguồn mà javac thật sự xuất ra.
class Box {
    private Object value;

    Box(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}

class NumberBox {
    Number value;
}
```

Quy tắc quan trọng:

- `T` không có cận trên tường minh thường xóa thành `Object`.
- `T extends Number` xóa thành `Number`. Với nhiều cận như `T extends Number & Comparable<T>`, cận **đầu tiên** chi phối erasure của `T`.
- Các tham số kiểu trong `List<String>`, `Map<String, Integer>` không tồn tại như các lớp JVM riêng biệt `ListOfString` hay `MapOfStringInteger`.
- Compiler có thể tạo cast hoặc bridge method. Một số generic signature vẫn được lưu trong metadata của class/method/field để công cụ và reflection đọc được, vì vậy erasure không đồng nghĩa xóa mọi dấu vết generic trong tệp `.class`.

Khi viết:

```java
Box<String> box = new Box<>("hello");
String message = box.get();
```

Compiler biết `box.get()` có kiểu biểu thức `String`, nhưng phiên bản đã xóa của phương thức `get` trả về `Object`. Ở bytecode tại nơi dùng giá trị, compiler có thể chèn `checkcast java/lang/String` để bảo vệ phép gán. Nếu dữ liệu thực tế sai kiểu, cast thất bại **khi chạy**.

Có thể tự kiểm tra bytecode của ví dụ biên dịch bằng:

```bash
javap -c -p GenericsAtRuntime
```

Hãy tìm các lệnh gọi `List.get` và `checkcast` ở nơi kết quả được dùng như `String`. Không cần giả định chính xác thứ tự/offset bytecode giống nhau ở mọi bản JDK.

## 4. Tại sao đã qua compiler vẫn có thể ClassCastException?

Generic type safety được đảm bảo trong điều kiện chương trình dùng generic API đúng cách và không phá vỡ hợp đồng qua raw type, unchecked cast, biến đổi mảng không an toàn, reflection hoặc mã ngoài đã biên dịch riêng.

Chương trình sau cố tình tạo **heap pollution**: một biến có kiểu tham số hóa trỏ tới cấu trúc chứa giá trị không phù hợp với kiểu đã khai báo.

Tạo tệp `HeapPollutionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");

        List raw = names; // Raw type: bỏ kiểm tra đối số kiểu.
        raw.add(42);      // Unchecked call: đưa Integer vào List<String>.

        try {
            String second = names.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Lệnh chạy:

```bash
javac -Xlint:rawtypes -Xlint:unchecked HeapPollutionDemo.java
java HeapPollutionDemo
```

Kết quả `stdout`:

```text
ClassCastException
```

`javac` phát cảnh báo cho raw type và thao tác thêm phần tử không được kiểm tra. Cảnh báo không tự chặn việc biên dịch. `raw.add(42)` có thể lưu `Integer` vì runtime `ArrayList.add` nhận đối tượng theo kiểu đã xóa, không tự kiểm tra “phải là String”. Khi lấy phần tử và gán cho `String`, cast do compiler thêm mới phát hiện giá trị thực tế là `Integer`.

Ngược lại, viết `names.add(42)` trực tiếp sẽ bị lỗi biên dịch. Dòng `List raw = names` không sao chép dữ liệu: `raw` và `names` là hai tham chiếu tới **cùng một danh sách**. Cũng vì vậy, dùng `@SuppressWarnings("unchecked")` chỉ để giấu cảnh báo không sửa được heap pollution.

Một unchecked cast khác:

```java
Object unknown = new ArrayList<Integer>();

@SuppressWarnings("unchecked")
List<String> assumed = (List<String>) unknown;
```

Runtime chỉ có thể kiểm tra `unknown` là một `List` thích hợp cho cast đã xóa; không xác nhận phần tử là `String`. Cast ở dòng này có thể thành công và lỗi xuất hiện muộn hơn khi đọc phần tử thành `String`. Chỉ suppress warning khi đã có cơ sở độc lập chứng minh dữ liệu phù hợp, và thu hẹp phạm vi annotation tới dòng/biến cần thiết.

## 5. Reifiable và non-reifiable: có thể kiểm tra đến đâu lúc chạy?

Một kiểu *reifiable* giữ đủ thông tin cần cho phép kiểm tra kiểu runtime của JVM. Ví dụ: `String`, `String[]`, `List<?>` và raw type `List`. Kiểu tham số hóa cụ thể như `List<String>` nhìn chung là *non-reifiable*: `String` ở trong dấu `<...>` không được dùng để xác minh mọi phần tử lúc chạy.

| Biểu thức | Hợp lệ? | Ý nghĩa |
| --- | --- | --- |
| `obj instanceof List<?>` | Có | Kiểm tra đối tượng có kiểu runtime tương thích với `List`. |
| `obj instanceof List<String>` với `obj` có kiểu tĩnh `Object` | Không | Không thể xác minh đối số kiểu `String` bằng `instanceof`. |
| `obj instanceof String` | Có | Kiểm tra kiểu lớp runtime `String`. |
| `new List<String>[5]` | Không | Không được tạo trực tiếp mảng có thành phần generic non-reifiable. |
| `new List<?>[5]` | Có | Thành phần mảng `List<?>` reifiable. |
| `new T()` hoặc `new T[5]` trong `class Box<T>` | Không | Biến kiểu `T` không cung cấp constructor/class component runtime phù hợp. |

Java array và generic collection có cơ chế khác nhau:

- **Mảng là covariant và reified ở mức kiểu thành phần**: `String[]` là một `Object[]` hợp lệ về quan hệ subtype, nhưng JVM biết mảng thật chứa `String` và có thể ném `ArrayStoreException` nếu ai đó cố đặt `Integer` vào.
- **Generic là invariant theo đối số kiểu**: `List<Integer>` không phải subtype của `List<Number>`, dù `Integer extends Number`. Quy tắc này ngăn một người nhận `List<Number>` đưa `Double` vào danh sách được người khác coi là `List<Integer>`.
- `List<? extends Number>` cho phép đọc phần tử như `Number` nhưng không cho thêm một `Integer` hoặc `Double` tùy ý (trừ `null`), vì không biết loại danh sách cụ thể mà wildcard đại diện. `List<? super Integer>` cho phép thêm `Integer` và đọc ra theo kiểu an toàn chung là `Object`.

Ví dụ mảng để đối chiếu:

```java
Object[] objects = new String[1];

try {
    objects[0] = 42;
} catch (ArrayStoreException ex) {
    System.out.println("ArrayStoreException");
}
```

Đoạn này in `ArrayStoreException` nếu đặt trong phương thức chạy được. Mảng phát hiện lỗi tại điểm **ghi** nhờ component type runtime. Ngược lại, danh sách generics thông thường có thể bị làm bẩn qua raw type và lỗi bị phát hiện ở điểm **đọc/cast**.

## 6. Quan hệ kiểu compile time không phải quan hệ lớp runtime

Một số tình huống thường gây nhầm:

**a) Invariance không biến mất vì erasure.**

```java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // Lỗi biên dịch.
List<? extends Number> readableNumbers = integers;
Number number = readableNumbers.isEmpty() ? 0 : readableNumbers.get(0);
```

Dù cả hai danh sách được xóa về `List` ở runtime, compiler vẫn áp dụng quan hệ kiểu generic trong chương trình nguồn. Wildcard diễn đạt khả năng sử dụng, không làm JVM tạo một loại `List` mới.

**b) Hai overload khác đối số kiểu có thể trùng chữ ký sau erasure.**

```java
// Hai phương thức sau KHÔNG thể cùng được khai báo trong một lớp:
// void process(List<String> values) {}
// void process(List<Integer> values) {}
```

Sau erasure cả hai có tham số kiểu `List`, nên gây *name clash*. Hãy đặt tên phương thức khác nhau, bổ sung tham số thực sự phân biệt, hoặc thiết kế một phương thức generic chung phù hợp.

**c) Overriding có thể cần bridge method.**

```java
class Parent<T> {
    T get() {
        return null;
    }
}

class Child extends Parent<String> {
    @Override
    String get() {
        return "child";
    }
}
```

Ở cấp nguồn, `Child.get()` override `Parent<String>.get()`. Sau erasure, phương thức của `Parent` có dạng trả `Object`, còn `Child` trả `String`. Compiler có thể sinh một bridge method tổng hợp để lời gọi đa hình qua `Parent` vẫn định tuyến tới triển khai `Child.get()`. Có thể xem bằng `javap -c -p Child` sau khi biên dịch đoạn mã trong một tệp phù hợp.

**d) Không được tạo kiểu generic bằng nguyên thủy.**

`List<int>` không hợp lệ vì đối số generic phải là reference type; dùng `List<Integer>`. Boxing/unboxing tự động giúp làm việc với `Integer`, nhưng điều đó không biến `int` thành một tham số generic của JVM.

## 7. Reflection biết gì và không biết gì?

Một nhầm lẫn phổ biến là “reflection có `ParameterizedType`, vậy erasure không xảy ra”. Hai sự thật cùng đúng:

1. Metadata trong class file có thể lưu **khai báo generic** của trường, phương thức, superclass và interface. `Field.getGenericType()`, `Method.getGenericReturnType()`, `Class.getGenericSuperclass()` hoặc `Class.getTypeParameters()` giúp đọc dữ liệu này.
2. Một đối tượng `new ArrayList<String>()` thường không lưu `String` như thuộc tính runtime riêng. `list.getClass()` trả về `ArrayList.class`; `getTypeParameters()` của `ArrayList.class` nói rằng lớp khai báo biến kiểu `E`, chứ không trả về đối số `String` mà biến tham chiếu của người gọi đã dùng.

Ví dụ, nếu khai báo một lớp con chuyên biệt:

```java
class StringList extends ArrayList<String> {
}
```

thì `StringList.class.getGenericSuperclass()` có thể mô tả `ArrayList<String>` vì kiểu được cố định trong **khai báo lớp con**. Nhưng tạo `new ArrayList<String>()` và hỏi `getClass().getGenericSuperclass()` không cung cấp cùng thông tin: đối tượng thuộc lớp `ArrayList`, vốn khai báo superclass không gắn `String`.

Khi ứng dụng cần truyền thông tin kiểu vào runtime, có hai hướng cơ bản:

- **Class token:** nhận `Class<T>`, chẳng hạn `String.class`, rồi dùng `type.cast(value)` hoặc `type.isInstance(value)` để kiểm tra một kiểu lớp cụ thể. `Class<T>` không biểu đạt đầy đủ kiểu lồng như `List<String>`.
- **Đại diện kiểu phức tạp:** truyền `java.lang.reflect.Type` hoặc cơ chế type token/type reference để giữ cấu trúc `List<String>` cho serializer/deserializer, framework hoặc hệ thống mapping. Metadata chỉ giúp mô tả kiểu mong muốn; kiểm tra từng phần tử vẫn cần logic xử lý dữ liệu phù hợp.

Đừng suy luận kiểu phần tử chỉ từ `collection.getClass()`; đừng nhầm `ParameterizedType` mô tả khai báo hoặc type token với khả năng JVM tự cưỡng chế đối số kiểu của mỗi collection.

## 8. Muốn kiểm tra cả phần tử ở runtime thì làm gì?

Khi dữ liệu đến từ nguồn không đáng tin về kiểu (JSON, reflection, API cũ, raw collection), hãy kiểm tra ở ranh giới nhận dữ liệu.

**Cách 1 — kiểm tra phần tử tường minh, tạo bản sao typed:**

```java
import java.util.ArrayList;
import java.util.List;

public class CheckedConversion {
    static List<String> requireStrings(List<?> source) {
        List<String> result = new ArrayList<>();
        for (Object value : source) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException("Expected String");
            }
            result.add(text);
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> names = requireStrings(List.of("Lan", "Mai"));
        System.out.println(names);
    }
}
```

Chạy `javac CheckedConversion.java` và `java CheckedConversion` cho `stdout`:

```text
[Lan, Mai]
```

Hàm nhận `List<?>`, nên an toàn khi đọc từng giá trị như `Object`. Pattern matching cho `instanceof String text` (được hỗ trợ trong Java 17) chỉ thêm giá trị đã kiểm tra vào danh sách mới. Với `List.of("Lan", 42)`, hàm phát `IllegalArgumentException` tại ranh giới chuyển đổi. Dùng bản sao cũng giúp hạn chế alias với dữ liệu đầu vào có thể bị thay đổi sau đó; nếu cần không cho sửa danh sách kết quả, có thể trả `List.copyOf(result)` khi các phần tử không null.

**Cách 2 — dùng runtime-checked view của Collections:**

```java
List<String> checked = java.util.Collections.checkedList(
        new java.util.ArrayList<>(), String.class);
```

`Collections.checkedList` tạo một view chặn việc thêm phần tử không tương thích với `String.class`, kể cả khi có mã cũ truy cập view qua raw type. Nó dùng runtime class token để kiểm tra phần tử, không tạo kiểu `List<String>` reified. Lưu ý view này không bảo vệ nếu bên ngoài còn giữ tham chiếu trực tiếp tới danh sách backing và sửa nó, và không tự làm sạch dữ liệu sai kiểu đã có sẵn trước khi bọc.

**Cách 3 — duy trì API typed từ đầu:** dùng `List<String>`, `Map<K,V>`, phương thức generic và wildcard phù hợp; tránh raw type, unchecked cast, reflective insert và truyền alias mutable cho mã không bảo đảm hợp đồng. Đây là biện pháp chính; kiểm tra runtime bổ sung ở những biên giới cần thiết.

## 9. Thiết kế và đọc lỗi theo đúng hai thời điểm

Khi thiết kế một phương thức generic:

```java
import java.util.List;
import java.util.NoSuchElementException;

class FirstElement {
    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new NoSuchElementException("Empty list");
        }
        return values.get(0);
    }
}
```

`<T>` diễn đạt quan hệ **đầu vào `List<T>` → đầu ra `T`**. Compiler suy luận kiểu ở điểm gọi:

```java
String name = FirstElement.first(List.of("Lan", "Mai"));
Integer count = FirstElement.first(List.of(1, 2, 3));
// String wrong = FirstElement.first(List.of(1, 2, 3)); // Lỗi kiểu.
```

Ví dụ này tập trung vào hợp đồng kiểu và chỉ là các đoạn khai báo/lời gọi minh họa; đặt ba lời gọi bên trong một phương thức khi chạy thực tế. Sau erasure, JVM không cần có phiên bản `first` riêng cho `String` và `Integer`. Kiểu trả về được compiler áp dụng tại vị trí gọi; nếu dữ liệu bị làm bẩn, cast có thể thất bại.

Khi điều tra lỗi, dùng đúng dấu hiệu:

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `incompatible types` | Sai quan hệ kiểu ở compile time, invariance hoặc thiếu chuyển đổi hợp lệ. | Sửa chữ ký generic, wildcard hoặc dữ liệu truyền vào; không ép cast để qua compiler. |
| `unchecked` / `rawtypes` warning | Trình biên dịch không chứng minh được hợp đồng generic. | Lần theo raw type, unchecked conversion/cast; thay bằng API typed hoặc kiểm tra từng phần tử. |
| `ClassCastException` khi đọc collection | Dữ liệu thực có lớp khác kiểu dự kiến tại điểm cast. | Truy ngược nơi chèn dữ liệu; tìm raw alias, reflection, deserialize hoặc unchecked cast. |
| `ArrayStoreException` | Mảng reified từ chối ghi sai component type. | Đừng dựa vào covariance để ghi phần tử; dùng kiểu mảng phù hợp hoặc collection với generic hợp đồng đúng. |
| `cannot select from a type variable` / `generic array creation` | Cần thông tin runtime không có sẵn từ `T`. | Nhận `Class<T>`, factory, `IntFunction<T[]>` hoặc thiết kế lại API. |
| `name clash ... same erasure` | Chữ ký generic khác nhau ở nguồn nhưng trùng sau erasure. | Đổi API hoặc chữ ký thực sự phân biệt. |

Lệnh `javac -Xlint:unchecked -Xlint:rawtypes TenFile.java` giúp phát hiện vị trí nguy cơ trước khi lỗi runtime xuất hiện. Khi đọc stack trace `ClassCastException`, tìm cả nơi **phát sinh dữ liệu không đúng kiểu**, vì vị trí ném lỗi thường chỉ là điểm dữ liệu được lấy ra và cast.

## 10. Các ngộ nhận cần tránh

1. **“Có Generics thì không bao giờ có ClassCastException.”** Sai: Generics kiểm tra hợp đồng ở compile time; dữ liệu vi phạm hợp đồng có thể đi vào qua đường unchecked/raw/reflection.
2. **“JVM biết đây là `List<String>` vì biến khai báo như vậy.”** Sai: khai báo biến là thông tin compiler dùng, không tự gắn `String` vào đối tượng `ArrayList`.
3. **“Mọi thông tin generic đều mất sạch sau biên dịch.”** Sai: erasure áp dụng cho thực thi generic, nhưng class file có thể giữ `Signature` metadata cho khai báo; reflection đọc được phần metadata này.
4. **“`instanceof List<?>` chứng minh các phần tử đều đúng kiểu.”** Sai: nó chỉ kiểm tra cấu trúc lớp `List` ở runtime.
5. **“`List<Integer>` có thể gán cho `List<Number>` vì `Integer extends Number`.”** Sai: bất biến theo đối số kiểu; dùng wildcard phù hợp nhu cầu đọc/ghi.
6. **“Cast `(List<String>) someList` sẽ rà soát các phần tử.”** Sai: unchecked cast thông thường không duyệt từng phần tử.
7. **“Bỏ cảnh báo bằng `@SuppressWarnings` khiến dữ liệu an toàn.”** Sai: annotation chỉ điều chỉnh cảnh báo compiler, không thay đổi đối tượng hoặc code kiểm tra runtime.

## 11. Tự kiểm tra hiểu bài

**Tình huống A.** Có `Object value = new ArrayList<Integer>();`. Có thể dùng `value instanceof List<?>` không? Có, nếu đối tượng thực thi `List` thì trả `true`. Có thể dùng `value instanceof List<String>` không? Không: kiểu đối số `String` không reifiable để JVM kiểm tra.

**Tình huống B.** Một phương thức nhận `List<String>` từ hệ thống cũ nhưng danh sách đã chứa `Integer`. Vì sao lời gọi `get` đôi khi chỉ lỗi sau đó? Phương thức `get` ở bytecode thao tác với giá trị theo kiểu đã xóa; lỗi phát sinh khi giá trị được cast sang `String` tại một điểm sử dụng đòi hỏi `String`. Không thể lấy thành công `String` từ một `Integer` bằng cast.

**Tình huống C.** Nếu cần nhận danh sách số chỉ để đọc, chọn `List<Number>` hay `List<? extends Number>`? Chọn `List<? extends Number>` khi muốn chấp nhận cả `List<Integer>`, `List<Double>`; đổi lại không thể tùy ý thêm số vào danh sách.

**Tình huống D.** `Field.getGenericType()` trả về `List<String>` có chứng minh dữ liệu lúc chạy là danh sách String không? Không. Nó phản ánh kiểu của trường được khai báo; phần tử vẫn có thể bị làm bẩn nếu các hàng rào an toàn bị vượt qua.

## Ghi nhớ

Generics là **hợp đồng kiểm tra kiểu mạnh ở compile time**; type erasure cho phép các instantiation dùng chung những lớp/thực thi runtime. JVM vẫn kiểm tra kiểu lớp thực và cast, nhưng không tự xác thực đối số generic cụ thể cho từng đối tượng collection. Vì vậy, hãy tin vào generic types để thiết kế API an toàn, coi raw/unchecked là dấu hiệu cần xem xét, và kiểm tra dữ liệu thực tại ranh giới nhận dữ liệu khi cần bảo đảm runtime.