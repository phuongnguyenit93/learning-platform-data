# `Class<T>`, `Class<?>` và giới hạn kiểm tra kiểu trong Java Reflection

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu đối tượng `java.lang.Class` đại diện cho một kiểu ở thời gian chạy như thế nào, và tham số `T` trong `Class<T>` giúp kiểm tra kiểu ở thời gian biên dịch ra sao.
- Phân biệt `Class<String>`, `Class<?>`, `Class<? extends Number>`, và cách dùng đúng khi viết API Reflection.
- Dùng `Class.isInstance`, `Class.cast`, `Class.isAssignableFrom`, `Class.asSubclass` để kiểm tra kiểu lúc chạy; hiểu chiều quan hệ kiểu và giới hạn của từng phép kiểm tra.
- Nhận biết chính xác phần thông tin kiểu bị xóa (*type erasure*) và lý do không thể kiểm chứng `List<String>` chỉ bằng `List.class`.
- Áp dụng *class token* trong một API generic mà không giả định JVM có thể xác minh mọi tham số kiểu.

## 2. `Class` là gì và `T` có ý nghĩa gì?

Mỗi `Class` object mô tả một kiểu được JVM nhận biết tại thời gian chạy: lớp, interface, enum, record, mảng, kiểu nguyên thủy hoặc `void`. `String.class` trả về đối tượng `Class` mô tả `java.lang.String`; `someObject.getClass()` cho biết lớp thực tế của đối tượng. Trong phạm vi một class loader định nghĩa một lớp, JVM duy trì một `Class` object tương ứng; hai lớp cùng tên do các class loader khác nhau định nghĩa có thể là hai kiểu khác nhau.

Khai báo `Class<T>` được *generic hóa* để trình biên dịch theo dõi quan hệ giữa token lớp và kiểu `T`:

```java
Class<String> stringType = String.class;
Class<Integer> integerType = Integer.class;
Class<?> unknownType = String.class;
```

`T` trong `Class<T>` là tham số kiểu ở **compile time**, không phải một phiên bản khác của lớp `Class` ở runtime. Cả ba biến trên đều tham chiếu đối tượng `Class`; khác nhau ở những phép gán và kiểu kết quả mà trình biên dịch chấp nhận.

Ví dụ sau **không biên dịch**:

```java
Class<Object> objectType = String.class; // Lỗi: Class<String> không phải Class<Object>
Class<String> textType = Integer.class; // Lỗi: hai type token không tương thích
```

Vì generic trong Java *bất biến* (invariant), việc `String` kế thừa `Object` không làm cho `Class<String>` kế thừa `Class<Object>`. Nếu chỉ muốn giữ một token bất kỳ, dùng `Class<?>`.

## 3. `Class<T>` so với `Class<?>`

| Khai báo | Điều đã biết tại compile time | Trường hợp phù hợp |
| --- | --- | --- |
| `Class<String>` | Token đại diện cho `String` | API cần đúng kiểu `String` |
| `Class<T>` | Token tương ứng với tham số kiểu `T` được suy luận/khai báo | Phương thức hoặc lớp generic cần trả về `T` an toàn |
| `Class<?>` | Có một token lớp, nhưng kiểu cụ thể chưa biết | Duyệt metadata, đọc Reflection, lưu các loại token khác nhau |
| `Class<? extends Number>` | Token của một lớp là `Number` hoặc lớp con | Giới hạn token thuộc một hệ phân cấp |
| `Class<? super Integer>` | Token của `Integer` hoặc một kiểu cha của nó | Làm việc với token có giới hạn kiểu cha |

Ví dụ:

```java
Class<?> a = String.class;
Class<?> b = Integer.class;
Class<? extends Number> numberType = Double.class;

// Không hợp lệ: Double.class có kiểu Class<Double>, không phải Class<Number>.
// Class<Number> exactNumber = Double.class;
```

`Class<?>` **không có nghĩa là** `Class<Object>`. Dấu `?` biểu diễn một kiểu chưa biết (*wildcard capture*). Ta vẫn có thể gọi `getName()`, `getDeclaredMethods()`, `isInterface()` hay `isInstance(...)`; nhưng kết quả của `type.cast(value)` khi `type` là `Class<?>` chỉ được dùng an toàn như `Object` nếu không có thêm thông tin.

```java
Class<?> type = String.class;
Object value = type.cast("hello"); // Hợp lệ; compile time chưa chứng minh là String
// String s = type.cast("hello");   // Không biên dịch: thiếu bằng chứng kiểu String
```

Ngược lại, với `Class<String>`, compiler biết phương thức `cast` trả về `String`:

```java
Class<String> type = String.class;
String value = type.cast("hello"); // Không cần ép kiểu tường minh
```

Không nên đổi `Class<?>` sang `Class<String>` chỉ bằng ép kiểu không được kiểm tra: việc đó làm mất lợi ích của hệ thống kiểu và có thể dẫn đến lỗi lúc chạy.

## 4. Cách lấy `Class` object

| Cách lấy | Kiểu biểu thức/kết quả | Lưu ý |
| --- | --- | --- |
| `String.class` | `Class<String>` | Biết lớp tại lúc biên dịch; không cần tạo instance |
| `Integer.class` | `Class<Integer>` | Token của wrapper `Integer` |
| `int.class` | `Class<Integer>` theo quy tắc kiểu của class literal | Token vẫn mô tả **primitive `int`**, khác `Integer.class` |
| `String[].class` | `Class<String[]>` | Mảng còn thông tin component type lúc chạy |
| `obj.getClass()` | `Class<? extends ...>` dựa trên kiểu tĩnh đã xóa của biểu thức | Trả về lớp thực tế; `obj == null` gây `NullPointerException` |
| `Class.forName("java.lang.String")` | `Class<?>` | Tìm lớp theo tên; có thể ném `ClassNotFoundException` và mặc định kích hoạt khởi tạo lớp |

Ví dụ:

```java
String text = "Java";
Class<?> runtimeType = text.getClass();
Class<?> loadedType = Class.forName("java.lang.String");

System.out.println(runtimeType == loadedType); // true trong trường hợp class loader thông thường
System.out.println(int.class == Integer.class); // false
```

Tên đơn giản của lớp (`getSimpleName()`) và tên đầy đủ (`getName()`) là metadata mô tả kiểu; bản thân chúng không xác minh cấu trúc generic của một object. Với `Class.forName`, chỉ nạp tên lớp từ cấu hình/đầu vào đã được kiểm soát nếu chương trình sử dụng Reflection để tạo đối tượng hoặc gọi thành viên; không coi việc nạp lớp là xác nhận rằng lớp thỏa mãn một interface.

## 5. Những phép kiểm tra kiểu mà `Class` hỗ trợ ở runtime

### 5.1. `isInstance(Object)`: đối tượng có thuộc kiểu này?

`type.isInstance(value)` tương đương về ý nghĩa kiểm tra runtime với phép `value instanceof SomeKnownType`, nhưng `type` có thể được xác định động.

```java
System.out.println(Number.class.isInstance(Integer.valueOf(7))); // true
System.out.println(String.class.isInstance(7));                  // false
System.out.println(String.class.isInstance(null));               // false
```

Lệnh gọi trả về `boolean`, không chuyển kiểu của biến theo `T`. Riêng token primitive: `int.class.isInstance(Integer.valueOf(7))` trả về `false` vì một đối tượng `Integer` không phải instance của kiểu primitive `int`.

### 5.2. `cast(Object)`: kiểm tra và chuyển kiểu với một token

Phương thức `Class<T>.cast(Object)` có chữ ký trả về `T`. Khi đối tượng không tương thích, nó ném `ClassCastException`. Đối với `null`, `cast(null)` trả về `null`.

```java
static <T> T requireType(Object value, Class<T> expected) {
    return expected.cast(value);
}

String ok = requireType("Java", String.class);
// String bad = requireType(123, String.class); // Biên dịch được, ném ClassCastException
```

Vì tham số `value` chỉ có kiểu `Object`, compiler **không thể đảm bảo** rằng dữ liệu đầu vào thuộc kiểu mong đợi. Compiler đảm bảo *kiểu trả về của API* là `T`, còn `Class.cast` thực hiện bước kiểm tra lớp thực tế lúc chạy. Nếu muốn báo lỗi rõ ràng, có thể kiểm tra `expected.isInstance(value)` trước khi gọi `cast`; lưu ý xử lý `null` riêng theo yêu cầu nghiệp vụ.

### 5.3. `isAssignableFrom(Class<?>)`: hướng quan hệ gán

`Target.class.isAssignableFrom(Source.class)` trả về `true` nếu một giá trị thuộc `Source` có thể gán cho biến kiểu `Target` theo quan hệ runtime giữa các lớp/interface (bao gồm cùng kiểu). **Đọc từ trái sang phải: đích nhận nguồn**.

```java
System.out.println(Number.class.isAssignableFrom(Integer.class)); // true
System.out.println(Integer.class.isAssignableFrom(Number.class)); // false
System.out.println(CharSequence.class.isAssignableFrom(String.class)); // true
```

Phép kiểm tra này làm việc trên `Class` object, không kiểm tra một instance và không xác minh tham số kiểu của `List<String>`. Các token primitive chỉ tương thích với chính kiểu primitive đó trong phép này; không có quy tắc tự động boxing như phép gọi hàm Java thông thường.

### 5.4. `asSubclass(Class<U>)`: giới hạn token về một kiểu cha

`candidate.asSubclass(Base.class)` kiểm tra `candidate` có phải `Base` hoặc lớp con/implementation của `Base` hay không. Thành công trả về `Class<? extends Base>`; thất bại ném `ClassCastException`.

```java
Class<?> discovered = Integer.class;
Class<? extends Number> numericType = discovered.asSubclass(Number.class);

// discovered.asSubclass(Runnable.class); // Ném ClassCastException tại runtime
```

Đây là cách hợp lý để lọc các lớp được phát hiện bằng Reflection trước khi xử lý như plugin, strategy hoặc implementation của một API. `asSubclass` xác nhận **quan hệ kế thừa/implements**, không xác nhận constructor tồn tại, quyền truy cập thành viên, hay điều kiện chạy của ứng dụng.

## 6. Ví dụ hoàn chỉnh: type token và runtime check (Java 17+)

Tạo file `ClassTokenDemo.java`:

```java
public class ClassTokenDemo {
    static <T> T requireType(Object value, Class<T> expected) {
        return expected.cast(value);
    }

    static void describe(Class<?> type, Object value) {
        System.out.println(type.getSimpleName() + ": " + type.isInstance(value));
    }

    public static void main(String[] args) {
        Class<String> textType = String.class;
        Class<?> unknownType = Integer.class;
        Class<? extends Number> numberType =
                unknownType.asSubclass(Number.class);

        System.out.println(textType.getSimpleName());
        System.out.println(unknownType.getName());
        System.out.println(numberType.getSimpleName());
        System.out.println(Number.class.isAssignableFrom(Integer.class));

        describe(String.class, "Java");
        describe(String.class, 42);

        String name = requireType("HELLO", textType);
        System.out.println(name.toLowerCase());

        try {
            requireType(42, textType);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ClassTokenDemo.java
java ClassTokenDemo
```

Kết quả chuẩn:

```text
String
java.lang.Integer
Integer
true
String: true
String: false
hello
ClassCastException
```

Ở đây `textType` giúp compiler suy luận `T = String` cho `requireType`. Token `unknownType` chỉ biết có một lớp; `asSubclass(Number.class)` mới xác minh lớp đó thuộc họ `Number` và trả về kiểu token có giới hạn phù hợp. Chú ý dòng `requireType(42, textType)` vẫn hợp lệ ở compile time: lỗi chỉ được phát hiện ở runtime, đúng nơi `Class.cast` kiểm tra đối tượng.

## 7. Giới hạn quan trọng: *type erasure* và generic không được xác minh đầy đủ

Thông tin mà `Class` giữ ở runtime là kiểu *reified* như `String`, `Integer`, `List`, `String[]`. Đối với phần lớn kiểu generic, JVM không lưu đối số kiểu cụ thể của từng instance `List<String>` hoặc `List<Integer>` trong `Class` object. Hai danh sách đó đều có lớp runtime là `ArrayList` nếu cùng được tạo bằng `new ArrayList<>()`.

Ví dụ cú pháp sau **không hợp lệ trong Java**:

```java
// Class<List<String>> tokens = List<String>.class; // Không tồn tại class literal này
// boolean ok = obj instanceof List<String>;         // Không kiểm tra được đối số kiểu String
```

Có thể dùng `List.class` hoặc `obj instanceof List<?>` để kiểm tra object là một `List`; không thể từ đó kết luận tất cả phần tử là `String`. Ép `(List<String>) object` với giá trị chỉ biết là `Object` thường gây cảnh báo *unchecked cast*, vì compiler không thể kiểm chứng đối số kiểu.

Ví dụ runnable `ErasureDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.List;

public class ErasureDemo {
    List<String> declaredNames;

    public static void main(String[] args) throws Exception {
        List<String> names = new ArrayList<>();
        names.add("Ada");

        List<Integer> scores = new ArrayList<>();
        scores.add(10);

        System.out.println(names.getClass() == scores.getClass());
        System.out.println(List.class.isInstance(names));
        System.out.println(List.class.isInstance(scores));

        Field field = ErasureDemo.class.getDeclaredField("declaredNames");
        Type declaredType = field.getGenericType();
        System.out.println(declaredType.getTypeName());
        System.out.println(declaredType instanceof ParameterizedType);
    }
}
```

Chạy:

```bash
javac ErasureDemo.java
java ErasureDemo
```

Kết quả:

```text
true
true
true
java.util.List<java.lang.String>
true
```

Có hai lớp thông tin phải tách biệt:

1. `names.getClass()` và `scores.getClass()` chỉ cho biết lớp runtime của danh sách, nên giống nhau. `List.class.isInstance(...)` chỉ xác nhận interface `List`, **không kiểm tra kiểu phần tử**.
2. `Field.getGenericType()` có thể đọc khai báo `List<String>` từ metadata chữ ký generic của **trường** `declaredNames`; đó là thông tin về khai báo của thành viên, **không phải** bằng chứng mọi object gán vào trường/danh sách luôn chứa `String` ở runtime. `Type` và `ParameterizedType` mô tả kiểu khai báo; chúng không biến một `Class<List>` thành token có khả năng validate mọi phần tử.

Nếu nghiệp vụ cần xác minh `List<String>` lúc nhận dữ liệu không tin cậy, phải kiểm tra container **và từng phần tử**, hoặc dùng cơ chế giải mã/schema validation có kiểm tra cấu trúc. Ví dụ:

```java
static boolean isStringList(Object candidate) {
    if (!(candidate instanceof java.util.List<?> list)) {
        return false;
    }
    for (Object item : list) {
        if (!(item instanceof String)) {
            return false;
        }
    }
    return true;
}
```

Đoạn trên là phương thức minh họa để đặt trong một lớp Java 17+; quy ước của nó là **không chấp nhận phần tử `null`**, vì `null instanceof String` là `false`. Nếu `null` được cho phép, điều kiện cần đổi theo yêu cầu miền dữ liệu. Danh sách rỗng trả về `true` theo quy tắc “mọi phần tử đều là `String`”, không hàm ý có thể suy ra đối số generic từ danh sách rỗng.

## 8. Dùng `Class<T>` để thiết kế API an toàn hơn

Một lớp tình huống điển hình là lấy một object từ kho lưu trữ chung, rồi kiểm tra bằng class token trước khi trả về kiểu cụ thể:

```java
import java.util.Map;

public class TypedLookupDemo {
    static <T> T lookup(Map<String, Object> values,
                        String key,
                        Class<T> expectedType) {
        Object value = values.get(key);
        if (value == null) {
            throw new IllegalArgumentException("Missing value: " + key);
        }
        return expectedType.cast(value);
    }

    public static void main(String[] args) {
        Map<String, Object> values = Map.of("port", 8080, "host", "localhost");
        Integer port = lookup(values, "port", Integer.class);
        String host = lookup(values, "host", String.class);
        System.out.println(host + ":" + port);
    }
}
```

```bash
javac TypedLookupDemo.java
java TypedLookupDemo
```

```text
localhost:8080
```

Lợi ích: lời gọi `lookup(values, "port", Integer.class)` cho kết quả kiểu `Integer` mà không cần unchecked cast của caller. Giới hạn: kho `Map<String,Object>` vẫn có thể chứa giá trị sai kiểu; `cast` sẽ ném `ClassCastException` tại runtime. Phương pháp này phù hợp với kiểu cụ thể như `Integer`, `String` hoặc một interface/lớp cha; nó không tự kiểm chứng tham số generic lồng nhau như `Map<String, List<Integer>>`.

Trong một framework/plugin dùng Reflection, mẫu an toàn tương tự là nhận `Class<?>` sau khi tìm lớp, rồi gọi `asSubclass(ExpectedInterface.class)` để chứng minh giới hạn loại trước khi tiếp tục. Nếu còn cần khởi tạo và gọi phương thức, phải kiểm tra thêm constructor, quyền truy cập, exception và hợp đồng API tương ứng.

## 9. Sai lầm thường gặp và cách tránh

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Coi `Class<?>` là `Class<Object>` | Generic bất biến; wildcard là kiểu chưa biết | Dùng `Class<?>` cho khám phá lớp, `Class<T>` khi cần gắn với kết quả `T` |
| Nghĩ `Class<T>` xác nhận dữ liệu là `T` ngay ở compile time | Đầu vào có thể là `Object`/dữ liệu động | Dùng `cast` hoặc `isInstance` kiểm tra tại runtime |
| Đảo chiều `isAssignableFrom` | `Target.isAssignableFrom(Source)` kiểm tra đích nhận nguồn | Đặt kiểu đích bên trái và kiểm thử cả hai chiều |
| Dùng `List.class` để kết luận `List<String>` | Erasure làm mất đối số kiểu trên từng instance | Kiểm tra phần tử hoặc dùng schema validation |
| Tưởng `getGenericType()` là runtime validation | Nó trả về metadata của khai báo | Phân biệt metadata của field/method với nội dung object |
| Xem `int.class` và `Integer.class` như cùng token | Primitive và wrapper là hai kiểu runtime khác nhau | Chọn token theo kiểu dữ liệu thực sự cần kiểm tra |
| Ép `Class<?>` sang `Class<X>` thiếu căn cứ | Unchecked cast có thể làm sai cam kết kiểu với caller | Dùng `asSubclass` để kiểm tra subtype; dùng `cast` để kiểm tra instance |
| Coi `asSubclass` đảm bảo có thể khởi tạo | Quan hệ kế thừa không nói gì về constructor hay truy cập | Kiểm tra riêng điều kiện instantiation và Reflection |

## 10. Tự kiểm tra

1. Tại sao `Class<String>` không gán được cho `Class<Object>` dù `String` là `Object`? Vì `Class<T>` invariant; muốn giữ token bất kỳ, chọn `Class<?>`.
2. `Number.class.isAssignableFrom(Integer.class)` có kết quả gì? `true`, vì object `Integer` gán được vào biến kiểu `Number`; chiều ngược lại là `false`.
3. `String.class.cast(42)` khác `String.class.isInstance(42)` thế nào? Phép đầu ném `ClassCastException`; phép sau trả về `false`.
4. Tại sao `List.class.isInstance(List.of(1, 2))` không chứng minh danh sách là `List<String>`? Vì chỉ kiểm tra kiểu `List` ở runtime, không biết đối số kiểu của các phần tử.
5. Sau `Class<?> candidate = Integer.class;`, làm sao có token giới hạn trong `Number` mà không unchecked cast? Dùng `Class<? extends Number> sub = candidate.asSubclass(Number.class);`; method kiểm tra subtype trước khi trả về.

**Ghi nhớ:** `Class<T>` nối **kiểu tĩnh `T`** với token kiểu runtime, `Class<?>` thể hiện token chưa biết kiểu cụ thể, còn `Class.isInstance/cast/isAssignableFrom/asSubclass` chỉ xác minh những quan hệ kiểu thực sự còn tồn tại ở runtime. Tham số của phần lớn kiểu generic như `List<String>` bị erasure; đừng suy luận kiểm tra được `String` chỉ vì đã có `List.class`.
