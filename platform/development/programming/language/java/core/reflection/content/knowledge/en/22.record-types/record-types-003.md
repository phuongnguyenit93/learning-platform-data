# Thứ tự thành phần record và constructor chuẩn

Khi tạo record bằng Reflection, tìm được đúng các kiểu tham số mới giải quyết một nửa bài toán. Bạn còn phải đặt **đúng giá trị vào đúng vị trí**. Nếu hai thành phần cùng kiểu, việc đảo chúng có thể tạo một đối tượng hợp lệ về kiểu nhưng sai ý nghĩa.

Constructor chuẩn (*canonical constructor*) là constructor gắn với toàn bộ các thành phần được khai báo trong header của record. Thứ tự thành phần xác định thứ tự tham số của constructor này. Nhờ quan hệ đó, một công cụ ánh xạ dữ liệu có thể tìm constructor và sắp xếp đối số một cách có căn cứ.

Bài này dùng Java 17 trở lên và tập trung vào mối liên hệ giữa metadata thành phần, chữ ký constructor và dữ liệu dùng để tạo đối tượng.

## 1. Header của record xác định điều gì?

Với khai báo:

```java
record Trip(String origin, String destination, int transfers) {
}
```

Constructor chuẩn nhận ba tham số theo thứ tự:

| Vị trí | Thành phần | Kiểu tham số | Ý nghĩa giá trị |
| --- | --- | --- | --- |
| `0` | `origin` | `String` | Điểm xuất phát |
| `1` | `destination` | `String` | Điểm đến |
| `2` | `transfers` | `int` | Số lần chuyển chặng |

Quan hệ tên, kiểu và thứ tự này thuộc quy tắc [constructor chuẩn của record](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4.1). Nếu không khai báo constructor chuẩn tường minh, trình biên dịch cung cấp nó.

Record có thể có constructor khác để phục vụ cách tạo đối tượng tiện lợi hơn. Vì vậy, không chọn `getDeclaredConstructors()[0]` hoặc chỉ chọn constructor có số tham số trông phù hợp. Cần tìm **đúng dãy kiểu tham số theo thứ tự header**.

Đặc biệt, hai vị trí `origin` và `destination` đều là `String`. Reflection không biết chuỗi nào là điểm đi hay điểm đến chỉ bằng kiểu dữ liệu. Trách nhiệm gắn đúng giá trị với tên thành phần thuộc về mã ánh xạ.

## 2. Tìm constructor chuẩn từ metadata

`Class.getRecordComponents()` giữ thứ tự khai báo thành phần. Lấy `getType()` của từng thành phần theo thứ tự đó để tạo `Class<?>[]`, rồi truyền dãy kiểu vào `getDeclaredConstructor(...)`.

Quy trình:

1. Xác minh kiểu là record; kết quả thành phần khác `null`.
2. Giữ nguyên thứ tự mảng `RecordComponent[]`.
3. Chuyển từng thành phần thành `Class<?>` bằng `getType()`.
4. Tra cứu constructor có chính xác dãy kiểu đó.

[API `Class.getRecordComponents()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getRecordComponents()) mô tả cả quy tắc thứ tự và cách áp dụng để tìm constructor chuẩn.

Không sắp xếp thành phần theo tên trước bước tra cứu. Một thứ tự đẹp cho việc hiển thị không nhất thiết là thứ tự tham số hợp lệ.

`getDeclaredConstructor` tra cứu theo kiểu tham số, không tự chọn overload từ các giá trị thực tế như một lời gọi `new` được viết trong mã nguồn.

## 3. Thí nghiệm Java 17+ chạy độc lập

Chương trình có các trường hợp: record có constructor chuẩn rút gọn, constructor phụ, dữ liệu dạng bản đồ, tham số nguyên thủy, record rỗng, record generic và thành phần varargs.

Lưu toàn bộ vào **`RecordConstructorDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

public class RecordConstructorDemo {
    public record Trip(String origin, String destination, int transfers) {
        public Trip {
            origin = Objects.requireNonNull(origin, "origin").strip();
            destination = Objects.requireNonNull(destination, "destination").strip();
            if (transfers < 0) {
                throw new IllegalArgumentException("transfers must be nonnegative");
            }
        }

        public Trip(String origin, String destination) {
            this(origin, destination, 0);
        }
    }

    public record Empty() {
    }

    public record Bundle<T>(T content) {
    }

    public record Labels(String... values) {
    }

    public static <R extends Record> Constructor<R> canonicalConstructor(
            Class<R> recordType) throws NoSuchMethodException {
        Objects.requireNonNull(recordType, "recordType");
        RecordComponent[] components = recordType.getRecordComponents();
        if (components == null) {
            throw new IllegalArgumentException("Expected a record declaration");
        }
        Class<?>[] parameterTypes = Arrays.stream(components)
                .map(RecordComponent::getType)
                .toArray(Class<?>[]::new);
        return recordType.getDeclaredConstructor(parameterTypes);
    }

    public static <R extends Record> R constructFromMap(
            Class<R> recordType, Map<String, ?> values)
            throws ReflectiveOperationException {
        Objects.requireNonNull(values, "values");
        Constructor<R> constructor = canonicalConstructor(recordType);
        RecordComponent[] components = recordType.getRecordComponents();
        Object[] arguments = new Object[components.length];
        for (int i = 0; i < components.length; i++) {
            String name = components[i].getName();
            if (!values.containsKey(name)) {
                throw new IllegalArgumentException("Missing component: " + name);
            }
            arguments[i] = values.get(name);
        }
        if (values.size() != components.length) {
            throw new IllegalArgumentException("Unexpected component keys");
        }
        return constructor.newInstance(arguments);
    }

    @FunctionalInterface
    private interface CheckedAction {
        void run() throws ReflectiveOperationException;
    }

    private static void attempt(String label, CheckedAction action) {
        try {
            action.run();
            System.out.println(label + " -> success");
        } catch (InvocationTargetException ex) {
            System.out.println(label + " -> InvocationTargetException, cause="
                    + ex.getCause().getClass().getSimpleName());
        } catch (ReflectiveOperationException | IllegalArgumentException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Constructor<Trip> constructor = canonicalConstructor(Trip.class);
        System.out.println("Components = "
                + Arrays.stream(Trip.class.getRecordComponents())
                        .map(RecordComponent::getName).toList());
        System.out.println("Canonical parameters = "
                + Arrays.stream(constructor.getParameterTypes())
                        .map(Class::getTypeName).toList());

        Map<String, Object> input = new LinkedHashMap<>();
        input.put("destination", "Hue");
        input.put("transfers", 1);
        input.put("origin", " Hanoi ");
        System.out.println("Input key order = " + input.keySet());
        System.out.println("From map = " + constructFromMap(Trip.class, input));
        System.out.println("Same-type swap = "
                + constructor.newInstance("Hue", "Hanoi", 1));

        attempt("wrapper lookup", () -> Trip.class.getDeclaredConstructor(
                String.class, String.class, Integer.class));
        attempt("missing no-arg", () -> Trip.class.getDeclaredConstructor());
        attempt("null primitive", () -> constructor.newInstance("Hanoi", "Hue", null));
        attempt("validation failure", () -> constructor.newInstance("Hanoi", "Hue", -1));
        attempt("missing key", () -> constructFromMap(
                Trip.class, Map.of("origin", "Hanoi")));

        Constructor<Empty> emptyConstructor = canonicalConstructor(Empty.class);
        System.out.println("Empty parameter count = "
                + emptyConstructor.getParameterCount());
        System.out.println("Empty instance = " + emptyConstructor.newInstance());

        Constructor<?> bundleConstructor = canonicalConstructor(Bundle.class);
        System.out.println("Bundle parameters = "
                + Arrays.stream(bundleConstructor.getParameterTypes())
                        .map(Class::getTypeName).toList());
        System.out.println("Bundle instance = " + bundleConstructor.newInstance("book"));

        Constructor<Labels> labelsConstructor = canonicalConstructor(Labels.class);
        Labels labels = labelsConstructor.newInstance(
                (Object) new String[]{"x", "y"});
        System.out.println("Labels parameter = "
                + labelsConstructor.getParameterTypes()[0].getTypeName());
        System.out.println("Labels constructor isVarArgs = "
                + labelsConstructor.isVarArgs());
        System.out.println("Labels values = " + Arrays.toString(labels.values()));

        attempt("base Record", () -> canonicalConstructor(Record.class));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror RecordConstructorDemo.java
java RecordConstructorDemo
```

Kết quả:

```text
Components = [origin, destination, transfers]
Canonical parameters = [java.lang.String, java.lang.String, int]
Input key order = [destination, transfers, origin]
From map = Trip[origin=Hanoi, destination=Hue, transfers=1]
Same-type swap = Trip[origin=Hue, destination=Hanoi, transfers=1]
wrapper lookup -> NoSuchMethodException
missing no-arg -> NoSuchMethodException
null primitive -> IllegalArgumentException
validation failure -> InvocationTargetException, cause=IllegalArgumentException
missing key -> IllegalArgumentException
Empty parameter count = 0
Empty instance = Empty[]
Bundle parameters = [java.lang.Object]
Bundle instance = Bundle[content=book]
Labels parameter = java.lang.String[]
Labels constructor isVarArgs = true
Labels values = [x, y]
base Record -> IllegalArgumentException
```

`attempt()` là hàm hỗ trợ thí nghiệm: in loại lỗi để chương trình tiếp tục quan sát các trường hợp khác. Nó không phải hợp đồng xử lý lỗi dành cho một thư viện ánh xạ dữ liệu hoàn chỉnh.

## 4. Hai dãy cần đồng bộ: kiểu tham số và giá trị đối số

Hàm `canonicalConstructor` tạo dãy kiểu `[String.class, String.class, int.class]` từ metadata của `Trip`. Đó là cơ sở tìm đúng constructor.

Hàm `constructFromMap` tạo một dãy khác: **các giá trị đối số**. Dãy này cũng phải đi theo thứ tự thành phần, không theo thứ tự duyệt khóa của bản đồ.

Trong thí nghiệm, dữ liệu được thêm theo thứ tự:

```text
destination → transfers → origin
```

Nhưng hàm ánh xạ lần lượt hỏi giá trị của `origin`, `destination`, `transfers`, nên constructor nhận:

```text
" Hanoi " → "Hue" → 1
```

Constructor chuẩn rút gọn bỏ khoảng trắng hai đầu các chuỗi, nên kết quả cuối là `Trip[origin=Hanoi, destination=Hue, transfers=1]`.

### Vì sao đổi chỗ hai giá trị cùng kiểu không phát sinh lỗi?

Lời gọi `constructor.newInstance("Hue", "Hanoi", 1)` vẫn khớp chữ ký `(String, String, int)`. Nó tạo hành trình ngược lại một cách hợp lệ về kiểu.

Đây là lỗi ngữ nghĩa mà kiểm tra kiểu của Reflection không thể tự phát hiện. Nếu lấy dữ liệu theo tên thành phần, hãy dùng chính tên đó làm khóa rồi đặt giá trị vào đúng chỉ số của thành phần.

Đừng xây đối số bằng `values.values().toArray()` và hy vọng thứ tự bản đồ luôn khớp header. Ngay cả bản đồ giữ thứ tự thêm khóa cũng có thể được tạo theo thứ tự khác, như dữ liệu trong ví dụ.

### Phân biệt thiếu khóa với giá trị `null`

Mã mẫu dùng `containsKey(name)` trước `get(name)`. Cách này phân biệt không có dữ liệu cho thành phần với việc bên gọi chủ động truyền `null`.

Hàm mẫu yêu cầu đủ tên thành phần và từ chối khóa dư. Đây là chính sách ánh xạ của hàm mẫu, không phải hành vi tự động của Reflection. Sau khi thu thập đối số, giá trị `null` có được chấp nhận hay không còn phụ thuộc kiểu tham số và kiểm tra trong constructor.

## 5. Constructor rút gọn vẫn có đủ tham số

Khai báo `public Trip { ... }` trong chương trình là **constructor chuẩn rút gọn (compact canonical constructor)**. Việc bỏ danh sách tham số trong cú pháp nguồn không biến nó thành constructor không tham số.

Reflection vẫn nhìn thấy chữ ký `(String, String, int)`. Phần thân rút gọn sử dụng các biến tham số tương ứng header để kiểm tra hoặc chuẩn hóa dữ liệu; việc gán các trường thành phần được hoàn tất theo quy tắc của record. Xem [constructor chuẩn rút gọn trong JLS](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4.2).

Trong thí nghiệm:

- `origin` và `destination` được chuẩn hóa bằng `strip()`.
- `transfers` âm bị từ chối.
- Constructor phụ nhận hai chuỗi gọi `this(origin, destination, 0)`.

Dù constructor chuẩn được trình biên dịch cung cấp, viết đầy đủ hay viết rút gọn, cách tìm dựa trên metadata thành phần vẫn áp dụng. Không cần đoán kiểu cú pháp nào đã được tác giả dùng trong mã nguồn.

Record `Trip` không có constructor không tham số. Vì vậy, `Trip.class.getDeclaredConstructor()` ném `NoSuchMethodException`, dù nó có constructor phụ khác.

## 6. Tra cứu chữ ký khác với chuyển đổi đối số khi gọi

Đây là hai bước có các quy tắc khác nhau.

### Khi tra cứu

`int.class` và `Integer.class` là hai kiểu khác nhau. Vì thành phần `transfers` có kiểu `int`, tra cứu với `Integer.class` không tìm thấy constructor chuẩn và ném `NoSuchMethodException`.

Do đó, không dựng chữ ký bằng cách gọi `argument.getClass()` cho từng giá trị: giá trị `1` bên trong `Object[]` là `Integer`, còn constructor thực sự nhận `int`. Giá trị `null` thậm chí không có `getClass()` để dùng.

Hãy dựng chữ ký từ `RecordComponent.getType()`, vì nó mô tả **kiểu khai báo**, không phải lớp thực tế của đối số hiện tại.

### Khi gọi

`Constructor.newInstance(Object... arguments)` nhận các giá trị dạng đối tượng. Với tham số `int`, đối tượng `Integer` có thể được mở gói để truyền vào constructor. API cũng có các quy tắc chuyển đổi nguyên thủy được cho phép, nhưng không tự phân tích chuỗi số thành số hay tùy ý thu hẹp kiểu. Xem [hợp đồng `Constructor.newInstance`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)).

Trong thí nghiệm, truyền `null` cho vị trí `int` gây `IllegalArgumentException` trước khi phần thân constructor được thực hiện. Truyền `"1"` thay vì một giá trị số cũng không phải một bước chuyển đổi cấu hình được Reflection tự làm.

Một thư viện ánh xạ thực tế cần có bước chuyển đổi dữ liệu rõ ràng trước khi gọi constructor; thuật toán trong bài chỉ xử lý việc gắn tên với vị trí và gọi constructor.

## 7. Lỗi trước lời gọi và lỗi từ bên trong constructor

Hai trường hợp trong kết quả cần được phân biệt:

| Thí nghiệm | Kết quả | Constructor đã chạy phần kiểm tra dữ liệu chưa? |
| --- | --- | --- |
| Truyền `null` cho `transfers` kiểu `int` | `IllegalArgumentException` | Chưa vào phần thân |
| Truyền `transfers = -1` | `InvocationTargetException`, nguyên nhân là `IllegalArgumentException` | Đã vào và chủ động từ chối |

Ở trường hợp thứ hai, `InvocationTargetException` là lớp bọc của lời gọi Reflection. `getCause()` cho ngoại lệ mà constructor thực sự ném ra.

Công cụ gọi constructor nên giữ thông tin này khi báo lỗi. Một thông báo “sai kiểu tham số” không giải thích đúng trường hợp dữ liệu đã vào constructor nhưng vi phạm bất biến nghiệp vụ.

Cũng cần tách lỗi không tìm thấy constructor, lỗi không có quyền gọi và lỗi kiểm tra dữ liệu. Không dùng một thông báo chung khiến người dùng không biết cần sửa cấu trúc, quyền truy cập hay giá trị đầu vào.

## 8. Các trường hợp đặc biệt

### Record rỗng

`Empty` có header `()`. Metadata thành phần có độ dài `0`, nên dãy kiểu tham số cũng rỗng. Constructor chuẩn chính là constructor không tham số và có thể gọi bằng `newInstance()`.

Đây là kết quả từ cấu trúc record, không phải quy tắc rằng mọi record đều có constructor không tham số.

### Record generic

`Bundle<T>(T content)` có `T` không giới hạn cụ thể hơn, nên kiểu tham số dùng khi tra cứu là `Object.class`. Kết quả in `[java.lang.Object]` xác nhận điều đó.

`RecordComponent.getGenericType()` có ích để phân tích khai báo generic, nhưng `getDeclaredConstructor(...)` cần `Class<?>[]`. Vì vậy, thuật toán dùng [kiểu thành phần từ `getType()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html#getType()). Không thay dãy kiểu khai báo bằng lớp của giá trị `"book"`, tức `String.class`.

### Thành phần varargs

`Labels(String... values)` có một thành phần với kiểu `String[]`. Constructor chuẩn có **một tham số mảng**, và `isVarArgs()` cho `true`.

Cần phân biệt mảng của constructor đích với cơ chế varargs của chính `Constructor.newInstance(Object...)`. Trong ví dụ:

```java
Labels labels = labelsConstructor.newInstance(
        (Object) new String[]{"x", "y"});
```

Đây là đoạn trích từ chương trình đầy đủ. Phép ép `(Object)` làm cho toàn bộ `String[]` trở thành **một đối số**. Một cách biểu diễn tương đương là truyền mảng đối số bên ngoài chứa đúng một phần tử mảng chuỗi.

Không truyền hai chuỗi rời rồi cho rằng Reflection sẽ tự đóng gói chúng vào `String[]` của constructor. Mã gọi phải chuẩn bị đúng số đối số và hình dạng mảng.

### Lớp cơ sở và quyền truy cập

Ràng buộc `<R extends Record>` không loại bỏ được chính `Record.class`, nên hàm vẫn kiểm tra metadata thành phần có khác `null` hay không. Thí nghiệm `base Record` bị từ chối trước bước tra cứu constructor.

`getDeclaredConstructor` tìm cả constructor không công khai, nhưng việc tìm thấy không tự cấp quyền gọi. Ví dụ dùng record lồng công khai để lời gọi hợp lệ trong bối cảnh của nó. Khi áp dụng với kiểu từ package hoặc module khác, hãy xử lý quyền truy cập theo hợp đồng của ứng dụng, không mặc định mở mọi constructor.

## 9. Bảng kiểm áp dụng

| Việc cần kiểm tra | Căn cứ đúng |
| --- | --- |
| Có phải record không? | `isRecord()` hoặc mảng thành phần khác `null` |
| Thứ tự tham số chuẩn là gì? | Thứ tự của `getRecordComponents()` |
| Kiểu dùng để tra cứu là gì? | `RecordComponent.getType()` |
| Constructor nào là chuẩn? | Constructor khớp toàn bộ dãy kiểu theo header |
| Giá trị nào vào vị trí nào? | Gắn theo tên thành phần rồi đặt vào chỉ số tương ứng |
| Thiếu giá trị hay chủ động truyền `null`? | Kiểm tra sự tồn tại của khóa riêng với giá trị |
| Lỗi đến từ đâu? | Tách lỗi tra cứu, gọi Reflection và nguyên nhân của `InvocationTargetException` |
| Có constructor rút gọn không? | Cú pháp rút gọn không thay chữ ký theo header |

### Tự kiểm tra

1. Vì sao đổi chỗ `origin` và `destination` không gây lỗi kiểu?
2. Vì sao `Integer.class` không thay được `int.class` ở bước tìm constructor?
3. Nếu bản đồ dữ liệu giữ thứ tự thêm khóa, tại sao vẫn cần sắp đối số theo metadata?
4. Tại sao constructor rút gọn của `Trip` không được tìm bằng dãy kiểu rỗng?
5. Làm sao phân biệt tham số `int` không nhận được `null` với constructor chủ động từ chối giá trị âm?
6. Vì sao `Labels` có một tham số constructor dù một đối tượng có thể chứa nhiều chuỗi?

Quan hệ cần giữ xuyên suốt là **thứ tự thành phần → thứ tự kiểu tham số → thứ tự giá trị đối số**. Khi ba dãy này đồng bộ, việc tạo record qua Reflection có thể được kiểm chứng và giải thích rõ ràng.
