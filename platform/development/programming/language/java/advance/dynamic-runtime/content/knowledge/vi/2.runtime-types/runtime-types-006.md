# 2.6. Kiểm tra `isInstance`, `isAssignableFrom`, `cast` và `asSubclass`

Trong Java, một giá trị có **kiểu được khai báo** tại thời điểm biên dịch, nhưng đối tượng mà biến tham chiếu tới có **kiểu thực tế lúc chạy**. Khi kiểu chỉ được biết qua cấu hình, tên lớp, plugin hoặc API reflection, bốn phương thức của `java.lang.Class` giúp kiểm tra và chuyển đổi một cách có kiểm soát:

- `isInstance(Object)`: đối tượng này có thuộc kiểu đang xét không?
- `isAssignableFrom(Class<?>)`: một lớp/kiểu nguồn có thể được gán cho kiểu đích không?
- `cast(Object)`: kiểm tra và trả về đối tượng theo kiểu của một `Class<T>`.
- `asSubclass(Class<U>)`: kiểm tra và thu hẹp **đối tượng `Class`** thành một kiểu con của `U`.

Điểm mấu chốt là **phân biệt đối tượng với mô tả kiểu** và **đọc đúng chiều kiểm tra**. Các ví dụ dưới đây sử dụng Java 17 trở lên.

## 1. Nền tảng: `Object`, `Class<?>` và quan hệ kiểu

Xét đoạn mã:

```java
Object value = Integer.valueOf(42);
Class<?> actualType = value.getClass(); // java.lang.Integer
Class<?> declaredTarget = Number.class;
```

Biến `value` có kiểu khai báo `Object`, nhưng đối tượng thực tế là `Integer`, vốn kế thừa `Number`. `actualType` là một **class token**: đối tượng `Class` mô tả kiểu chạy, không phải một thể hiện `Integer`.

- Với **đối tượng**, hỏi `Number.class.isInstance(value)`.
- Với **hai kiểu**, hỏi `Number.class.isAssignableFrom(Integer.class)`.
- Muốn thu về tham chiếu `Number` từ `Object`, dùng `Number.class.cast(value)`.
- Có `Class<?>` tải động và cần đảm bảo nó triển khai một giao diện, dùng `raw.asSubclass(Interface.class)`.

`Class<?>` có nghĩa “biết đây là một `Class`, nhưng chưa biết kiểu chính xác của nó”. `Class<T>` còn giữ quan hệ kiểu ở mức biên dịch, chẳng hạn `Class<Number>`, và hỗ trợ trả về `T` từ `cast`. Mọi phép kiểm tra này đều theo **định danh kiểu ở JVM**, bao gồm class loader; hai lớp cùng tên nhưng được nạp bởi các class loader không tương thích không mặc nhiên là cùng một kiểu.

## 2. So sánh nhanh bốn API

| Phương thức | Gọi trên | Đối số | Kết quả | Không tương thích |
| --- | --- | --- | --- | --- |
| `type.isInstance(value)` | `Class<?>` mô tả kiểu đích | Một đối tượng | `boolean` | `false` |
| `target.isAssignableFrom(source)` | `Class<?>` kiểu đích | `Class<?>` kiểu nguồn | `boolean` | `false` |
| `type.cast(value)` | `Class<T>` kiểu mong muốn | Một đối tượng | `T` (cùng đối tượng) | `ClassCastException` |
| `raw.asSubclass(parent)` | `Class<?>` kiểu tìm thấy | `Class<U>` kiểu cha/ràng buộc | `Class<? extends U>` | `ClassCastException` |

Đối với `null`: `isInstance(null)` luôn là `false`; `cast(null)` trả về `null`. `isAssignableFrom(null)` và `asSubclass(null)` ném `NullPointerException` vì cần một đối tượng `Class` hợp lệ. Gọi bất kỳ phương thức nào qua biến `Class` đang là `null` cũng gây `NullPointerException`.

## 3. `isInstance` — hỏi về một đối tượng

Chữ ký API (rút gọn, không phải chương trình độc lập):

```java
boolean isInstance(Object obj)
```

Đối với lớp hoặc interface tham chiếu, đây là phép kiểm tra kiểu chạy tương tự `obj instanceof SomeType`, nhưng **kiểu đích có thể nằm trong một biến `Class<?>`**:

```java
Object data = "Java";
Class<?> expected = CharSequence.class; // có thể được chọn lúc chạy

System.out.println(expected.isInstance(data));       // true
System.out.println(Number.class.isInstance(data));   // false
System.out.println(String.class.isInstance(null));   // false
System.out.println(int.class.isInstance(42));         // false
```

`CharSequence` là interface do `String` triển khai, nên kết quả đầu là `true`. Dòng cuối có `42` được **autobox** thành `Integer` khi truyền vào tham số `Object`; `int.class` mô tả kiểu nguyên thủy, không phải `Integer.class`. Vì vậy kết quả vẫn là `false`. `isInstance` không thực hiện chuyển đổi nguyên thủy hay unboxing.

Nên dùng `isInstance` khi có **đối tượng cần kiểm tra** và **kiểu mong đợi được quyết định động**. Nếu biết tên kiểu ngay trong mã nguồn, `instanceof` (kể cả pattern matching từ Java 16) thường dễ đọc hơn:

```java
if (data instanceof String text) {
    System.out.println(text.length());
}
```

`isInstance` chỉ trả `boolean`; nó không cung cấp biến đã được thu hẹp kiểu như pattern variable `text`.

## 4. `isAssignableFrom` — hỏi về hai kiểu và chiều gán

Chữ ký API (rút gọn, không phải chương trình độc lập):

```java
boolean isAssignableFrom(Class<?> cls)
```

Đọc từ trái sang phải là: **“Kiểu bên trái có nhận được một giá trị thuộc kiểu bên phải không?”** Có thể nhớ bằng phép gán minh họa:

```java
// target.isAssignableFrom(source) kiểm tra quan hệ tương tự:
// Target target = sourceValue;   // sourceValue có kiểu Source
Number.class.isAssignableFrom(Integer.class); // true
Integer.class.isAssignableFrom(Number.class); // false
```

Đối số `source` có thể chính là `target`, một lớp con, một lớp triển khai interface, hoặc một kiểu mảng có thể gán theo quy tắc của Java:

| Biểu thức | Kết quả | Vì sao |
| --- | --- | --- |
| `Object.class.isAssignableFrom(String.class)` | `true` | `String` là một `Object` |
| `CharSequence.class.isAssignableFrom(String.class)` | `true` | `String` triển khai `CharSequence` |
| `String.class.isAssignableFrom(CharSequence.class)` | `false` | Không phải mọi `CharSequence` là `String` |
| `Number.class.isAssignableFrom(Number.class)` | `true` | Kiểu giống hệt nhau |
| `Number.class.isAssignableFrom(int.class)` | `false` | Không tự boxing `int` thành `Integer` |
| `int.class.isAssignableFrom(int.class)` | `true` | Cùng một kiểu nguyên thủy |
| `Number[].class.isAssignableFrom(Integer[].class)` | `true` | Mảng tham chiếu có tính hiệp biến |
| `Object[].class.isAssignableFrom(int[].class)` | `false` | `int[]` không phải mảng tham chiếu `Object[]` |
| `Object.class.isAssignableFrom(int[].class)` | `true` | Bản thân mọi mảng đều là đối tượng |

**Chú ý về mảng:** Quan hệ `Number[]` nhận `Integer[]` không bảo đảm mọi phép ghi phần tử sẽ thành công. Ví dụ, `Number[] xs = new Integer[1]; xs[0] = 3.14;` biên dịch được nhưng ném `ArrayStoreException` tại thời điểm chạy. Mảng nguyên thủy như `int[]` vẫn là đối tượng (`Object`, `Cloneable`, `Serializable`), song không là `Object[]`.

`isAssignableFrom` kiểm tra quan hệ kiểu tham chiếu và sự đồng nhất kiểu nguyên thủy; nó **không** xét widening primitive (`int` sang `long`), boxing/unboxing hay chuyển đổi ép kiểu tường minh. Sai lầm phổ biến nhất là đảo hai vế: `Integer.class.isAssignableFrom(Number.class)` kiểm tra một hướng khác và phải là `false`.

## 5. `cast` — kiểm tra đối tượng và nhận về kiểu `T`

Chữ ký API (rút gọn, không phải chương trình độc lập):

```java
T cast(Object obj)
```

`cast` dùng kiểm tra kiểu lúc chạy rồi trả về **chính đối tượng đã truyền vào**, theo kiểu `T` gắn với class token. Nó không tạo đối tượng mới, không chuyển đổi số và không tự động parse chuỗi:

```java
Object raw = Integer.valueOf(42);
Number number = Number.class.cast(raw); // OK, kiểu trả về là Number
System.out.println(number.intValue()); // 42

String nothing = String.class.cast(null); // hợp lệ: nothing == null
// String text = String.class.cast(raw); // ClassCastException lúc chạy
```

Dạng tiện dụng cho API đọc dữ liệu động:

```java
static <T> T checkedValue(Class<T> expected, Object value) {
    return expected.cast(value);
}

// Cách gọi:
// Integer count = checkedValue(Integer.class, someObject);
```

Không cần ép kiểu không kiểm soát `(T) value`. Compiler suy luận `T` từ `Class<T>`, còn JVM kiểm tra đối tượng ở `cast`. Trường hợp `obj == null` được phép: nếu ứng dụng yêu cầu giá trị bắt buộc khác `null` thì kiểm tra thêm `Objects.requireNonNull(obj)`.

`Class.cast` chủ yếu dành cho kiểu tham chiếu: `int.class.cast(Integer.valueOf(1))` ném `ClassCastException`, bởi lớp primitive không có thể hiện đối tượng phù hợp. `Integer.class.cast(Integer.valueOf(1))` mới hợp lệ. Một `ClassCastException` phát sinh từ `cast` là tín hiệu rõ ràng rằng dữ liệu đầu vào không thỏa hợp đồng kiểu mong đợi.

## 6. `asSubclass` — thu hẹp class token của một lớp tải động

Chữ ký API (rút gọn, không phải chương trình độc lập):

```java
<U> Class<? extends U> asSubclass(Class<U> clazz)
```

Đây là phép kiểm tra cho **đối tượng `Class`**, không phải cho instance. Nếu kiểu do `raw` đại diện là chính `U` hoặc là lớp con/kiểu triển khai `U`, kết quả là class token có kiểu `Class<? extends U>`. Nếu không, ném `ClassCastException`:

```java
Class<?> raw = StringBuilder.class;

Class<? extends CharSequence> valid =
        raw.asSubclass(CharSequence.class);    // OK

// raw.asSubclass(Number.class);               // ClassCastException
```

Có thể coi điều kiện tương thích gần như `Parent.class.isAssignableFrom(raw)`, nhưng `asSubclass` **vừa xác nhận vừa trả về class token đã có ràng buộc generic**, để tiếp tục gọi API như `getDeclaredConstructor()` và tạo instance có kiểu cha rõ ràng. Nó không tự tạo instance, không chứng minh constructor tồn tại hay có thể truy cập, và không bảo đảm lớp không abstract.

Ứng dụng điển hình là tải plugin/handler từ tên lớp: `Class.forName(name)` ban đầu chỉ cho `Class<?>`, sau đó `raw.asSubclass(Handler.class)` giúp từ chối lớp không triển khai `Handler` ngay tại ranh giới nạp. Khi cần kiểm tra mà không ném lỗi, dùng `Handler.class.isAssignableFrom(raw)`.

## 7. Ví dụ hoàn chỉnh chạy trên Java 17+

Lưu đúng tên file `RuntimeTypeChecks.java`:

```java
import java.util.Objects;

public class RuntimeTypeChecks {
    interface Handler {
        String handle();
    }

    public static final class HelloHandler implements Handler {
        public HelloHandler() {}

        @Override
        public String handle() {
            return "hello";
        }
    }

    static <T> T requireType(Class<T> expected, Object value) {
        Objects.requireNonNull(expected, "expected");
        return expected.cast(value);
    }

    static Handler loadHandler(String binaryName)
            throws ReflectiveOperationException {
        Class<?> raw = Class.forName(binaryName);
        Class<? extends Handler> type = raw.asSubclass(Handler.class);
        return type.getDeclaredConstructor().newInstance();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Object value = Integer.valueOf(42);

        System.out.println(Number.class.isInstance(value));
        System.out.println(String.class.isInstance(value));
        System.out.println(Number.class.isInstance(null));

        System.out.println(Number.class.isAssignableFrom(Integer.class));
        System.out.println(Integer.class.isAssignableFrom(Number.class));
        System.out.println(int.class.isAssignableFrom(Integer.class));

        Number number = requireType(Number.class, value);
        System.out.println(number.intValue());
        System.out.println(String.class.cast(null) == null);

        try {
            String.class.cast(value);
        } catch (ClassCastException expected) {
            System.out.println("cast: ClassCastException");
        }

        Handler handler = loadHandler(HelloHandler.class.getName());
        System.out.println(handler.handle());

        try {
            String.class.asSubclass(Handler.class);
        } catch (ClassCastException expected) {
            System.out.println("asSubclass: ClassCastException");
        }

        System.out.println(Number[].class.isAssignableFrom(Integer[].class));
        System.out.println(Object.class.isAssignableFrom(int[].class));
        System.out.println(Object[].class.isAssignableFrom(int[].class));
    }
}
```

Biên dịch/chạy ở thư mục chứa file:

```bash
javac --release 17 RuntimeTypeChecks.java
java RuntimeTypeChecks
```

Kết quả `stdout` chính xác (không tính dòng lệnh):

```text
true
false
false
true
false
false
42
true
cast: ClassCastException
hello
asSubclass: ClassCastException
true
true
false
```

**Giải thích luồng chạy:**

1. Ba dòng đầu dùng **instance**: `Integer` là `Number`, không là `String`; `null` không là instance của lớp nào.
2. Ba dòng kế tiếp dùng **class token** theo hướng đích ← nguồn: `Number` nhận `Integer`; chiều ngược lại và primitive so với wrapper đều không hợp lệ.
3. `requireType` trả về `Number` chứa giá trị `42`; `cast(null)` trả `null`. Thử ép `Integer` sang `String` làm phát sinh `ClassCastException` và được bắt có chủ đích.
4. `Class.forName` tìm lớp lồng `HelloHandler` theo tên nhị phân do `getName()` cấp; `asSubclass(Handler.class)` xác nhận hợp đồng, constructor tạo object mới, nên `handle()` in ra `hello`.
5. `String` không triển khai `Handler`, nên `asSubclass` ném `ClassCastException`. Ba dòng cuối xác nhận quy tắc của mảng tham chiếu, `Object` và mảng nguyên thủy.

Ví dụ sử dụng constructor public để minh họa đường đi tối giản. Trong hệ plugin thực tế, khởi tạo có thể thất bại nếu lớp abstract, constructor không tồn tại/không được phép truy cập, constructor ném lỗi hoặc class loader không thấy phụ thuộc.

## 8. Quy trình áp dụng khi kiểm tra dữ liệu động

**Trường hợp A — Có một đối tượng từ API, cần kiểm tra rồi sử dụng:** Với `Object payload` và một `Class<T> expected` do cấu hình xác định, dùng `expected.isInstance(payload)` nếu muốn rẽ nhánh nhẹ nhàng; dùng `expected.cast(payload)` nếu hợp đồng yêu cầu kiểu đó và muốn nhận trực tiếp `T`. Trước khi dùng `cast`, có thể xử lý `null` riêng theo quy tắc nghiệp vụ. Không cần `getClass()` chỉ để gọi `isInstance`.

**Trường hợp B — Đang xét hai class token:** Với `Class<?> source` và `Class<?> target`, viết `target.isAssignableFrom(source)`. Ví dụ bộ đăng ký handler muốn lọc các lớp triển khai `Handler` bằng `Handler.class.isAssignableFrom(candidate)`. Nếu cần biểu diễn kết quả thành kiểu dùng được trong API generic, chuyển sang `candidate.asSubclass(Handler.class)`.

**Trường hợp C — Nạp lớp qua tên cấu hình:** Chọn class loader thích hợp, nạp tên nhị phân, kiểm tra `asSubclass`, sau đó mới kiểm tra khả năng khởi tạo/constructor. Với tên lớp từ bên ngoài, chỉ chấp nhận tập lớp được cho phép, quan tâm tác động của khởi tạo lớp, quyền truy cập theo module và lỗi reflection. `Class.forName(name)` có thể kích hoạt khởi tạo lớp; nếu cần trì hoãn, cân nhắc dạng `Class.forName(name, false, loader)`.

**Trường hợp D — Kiểu generic có tham số:** `List.class.isInstance(List.of(123))` là `true`, nhưng điều đó **không chứng minh** danh sách là `List<String>`. Do *type erasure*, bốn API không kiểm tra tham số `String` trong `List<String>`. Khi cần xác thực nội dung, duyệt và kiểm tra từng phần tử (hoặc dùng cơ chế kiểm tra schema/type token có thông tin generic phù hợp); đừng coi `List.class.cast(...)` là chứng nhận an toàn generic.

## 9. Lỗi thường gặp và cách chẩn đoán

| Lỗi | Dấu hiệu | Cách sửa |
| --- | --- | --- |
| Đảo chiều `isAssignableFrom` | `Integer.class.isAssignableFrom(Number.class)` trả `false` ngoài mong đợi | Đặt **kiểu đích bên trái**, nguồn bên phải |
| Nhầm `isInstance` với `isAssignableFrom` | Truyền object vào API cần `Class` hoặc ngược lại | Xác định đang kiểm tra **giá trị** hay **mô tả kiểu** |
| Mong primitive tự boxing | `int.class.isInstance(1)` hoặc `int.class.cast(1)` không hoạt động như `Integer.class` | Dùng wrapper `Integer.class` cho đối tượng |
| Dùng `cast` để biến đổi dữ liệu | Mong `String.class.cast(42)` thành `"42"` | Dùng chuyển đổi chủ đích như `String.valueOf(42)` |
| Tin rằng `asSubclass` đảm bảo tạo được object | Class hợp lệ nhưng constructor lỗi hoặc không tồn tại | Kiểm tra abstract/constructor/access và xử lý ngoại lệ |
| Tin rằng kiểm tra `List.class` xác thực `List<String>` | Phần tử khác kiểu chỉ gây lỗi khi sử dụng | Xác thực từng phần tử và hạn chế unchecked cast |
| Nhầm lớp cùng tên là cùng kiểu | `isAssignableFrom` thất bại giữa hai class loader | Kiểm tra class loader và định danh class thực tế |
| Chỉ kiểm tra `isInstance` rồi cast một object đã thay đổi | Kết quả kiểm tra không còn khớp object dùng sau | Giữ cùng tham chiếu và dùng `expected.cast(value)` tại ranh giới sử dụng |

Tránh dùng exception như luồng điều khiển bình thường khi chỉ muốn biết `true/false`: chọn `isInstance` hoặc `isAssignableFrom`. Ngược lại, `cast` và `asSubclass` là lựa chọn phù hợp khi vi phạm hợp đồng kiểu phải được báo rõ ngay.

## 10. Tự kiểm tra

Hãy dự đoán trước khi chạy:

```java
System.out.println(CharSequence.class.isAssignableFrom(String.class));
System.out.println(String.class.isInstance(null));
System.out.println(Object[].class.isInstance(new int[] {1, 2}));
System.out.println(Cloneable.class.isAssignableFrom(int[].class));
```

Đáp án lần lượt là `true`, `false`, `false`, `true`. Giải thích: `String` triển khai `CharSequence`; `null` không là instance; `int[]` không phải `Object[]`, nhưng mọi array Java đều triển khai `Cloneable`.

**Ghi nhớ:** `isInstance` và `cast` nhận **đối tượng**; `isAssignableFrom` và `asSubclass` làm việc với **class token**. Khi kiểm tra hai kiểu, `Target.class.isAssignableFrom(Source.class)` đọc là “đích nhận được nguồn”; khi cần class token có ràng buộc kiểu, dùng `raw.asSubclass(Target.class)`.
