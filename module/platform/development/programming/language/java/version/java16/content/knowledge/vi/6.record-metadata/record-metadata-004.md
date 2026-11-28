# Lấy accessor bằng RecordComponent.getAccessor và gọi qua API công khai

Khi đã lấy được danh sách record component bằng `Class.getRecordComponents()`, ta có thể cần đọc giá trị của từng component từ một đối tượng record cụ thể. Mỗi component có một **accessor** tương ứng, chẳng hạn component `code` có accessor `code()`. Trong Java Reflection, `RecordComponent.getAccessor()` trả về đối tượng `Method` đại diện cho accessor đó.

Khi kiểu record chỉ được biết ở runtime, có thể gọi accessor thông qua API Reflection công khai `Method.invoke()`. Đây là cách hữu ích cho công cụ tạo schema, mapper, bộ kiểm tra dữ liệu và thư viện xử lý nhiều kiểu record khác nhau. Nội dung dưới đây tập trung vào API chính thức từ Java 16 và các quy tắc truy cập vẫn áp dụng trong Java hiện đại.

## 1. Accessor của record là gì?

Với khai báo:

```java
record Product(String code, int quantity) {}
```

Java cung cấp accessor cho từng component:

| Component | Accessor | Kiểu trả về |
| --- | --- | --- |
| `code` | `code()` | `String` |
| `quantity` | `quantity()` | `int` |

Accessor là phương thức instance không có tham số, tên trùng với tên component và trả về kiểu tương ứng. Cách gọi thông thường khi đã biết kiểu tại thời điểm biên dịch:

```java
Product product = new Product("BK-100", 3);

String code = product.code();
int quantity = product.quantity();
```

Accessor của record không theo quy ước JavaBeans `getCode()` hoặc `getQuantity()`. Tên phương thức chính là tên component.

Nếu chương trình đã biết kiểu `Product`, gọi accessor trực tiếp là cách rõ ràng nhất. Reflection có ích khi chương trình chỉ có một `Object` hoặc `Class<?>` và cần xử lý nhiều kiểu record mà không biết tên component từ trước.

## 2. `RecordComponent.getAccessor()` trả về gì?

Chữ ký API:

```java
public Method getAccessor()
```

Phương thức thuộc `java.lang.reflect.RecordComponent` và trả về đối tượng `java.lang.reflect.Method` mô tả accessor tương ứng.

Thông tin có thể lấy từ `Method`:

| API | Ý nghĩa |
| --- | --- |
| `getName()` | Tên accessor, trùng tên component |
| `getParameterCount()` | Số tham số; accessor không có tham số nên kết quả là `0` |
| `getReturnType()` | Kiểu trả về dưới dạng `Class<?>` |
| `getGenericReturnType()` | Kiểu trả về dưới dạng `Type`, có thể giữ thông tin generic |
| `getModifiers()` | Modifier của phương thức; accessor record là public |
| `getDeclaringClass()` | Lớp khai báo accessor |

Ví dụ đọc thông tin accessor:

```java
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

record Customer(long id, String name) {}

public class AccessorMetadataDemo {
    public static void main(String[] args) {
        for (RecordComponent component :
                Customer.class.getRecordComponents()) {
            Method accessor = component.getAccessor();

            System.out.printf(
                    "component=%s, method=%s, returnType=%s, parameters=%d%n",
                    component.getName(),
                    accessor.getName(),
                    accessor.getReturnType().getTypeName(),
                    accessor.getParameterCount()
            );
        }
    }
}
```

Kết quả:

```text
component=id, method=id, returnType=long, parameters=0
component=name, method=name, returnType=java.lang.String, parameters=0
```

Không cần tự ghép tên phương thức rồi tìm bằng `getDeclaredMethod()`. `getAccessor()` đã trả về chính xác accessor của component, giúp tránh đoán sai tên hoặc chọn nhầm phương thức.

## 3. Gọi accessor bằng `Method.invoke()`

Chữ ký thường dùng:

```java
public Object invoke(Object obj, Object... args)
```

Với accessor record, phương thức không nhận tham số, vì vậy chỉ cần truyền instance record làm đối số thứ nhất:

```java
Object value = accessor.invoke(recordInstance);
```

Trong đó:

- `accessor` là `Method` lấy từ `component.getAccessor()`.
- `recordInstance` là đối tượng record cần đọc.
- Kết quả trả về có kiểu tĩnh là `Object`. Nếu accessor trả về kiểu nguyên thủy, Java đóng gói giá trị thành wrapper tương ứng, ví dụ `int` thành `Integer`.

### Ví dụ hoàn chỉnh

Lưu thành tệp `RecordAccessorDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;
import java.math.BigDecimal;

public class RecordAccessorDemo {

    public record Product(
            String code,
            int quantity,
            BigDecimal price
    ) {}

    static void printRecordValues(Object value) {
        if (value == null || !value.getClass().isRecord()) {
            throw new IllegalArgumentException("Expected a non-null record");
        }

        Class<?> recordType = value.getClass();
        for (RecordComponent component :
                recordType.getRecordComponents()) {
            Method accessor = component.getAccessor();

            try {
                Object componentValue = accessor.invoke(value);
                System.out.printf(
                        "%s (%s) = %s%n",
                        component.getName(),
                        component.getType().getTypeName(),
                        componentValue
                );
            } catch (IllegalAccessException e) {
                throw new IllegalStateException(
                        "Cannot access accessor: " + accessor.getName(), e);
            } catch (InvocationTargetException e) {
                throw new IllegalStateException(
                        "Accessor failed: " + accessor.getName(),
                        e.getCause()
                );
            }
        }
    }

    public static void main(String[] args) {
        Product product = new Product(
                "BK-100",
                3,
                new BigDecimal("125000.00")
        );

        printRecordValues(product);
    }
}
```

Biên dịch và chạy bằng JDK 16 trở lên:

```bash
javac RecordAccessorDemo.java
java RecordAccessorDemo
```

Kết quả:

```text
code (java.lang.String) = BK-100
quantity (int) = 3
price (java.math.BigDecimal) = 125000.00
```

Hàm `printRecordValues` không cần biết trước record có component nào. Nó lấy kiểu runtime của đối tượng, duyệt metadata và gọi accessor tương ứng. Đây là mô hình thường gặp trong công cụ xử lý record tổng quát.

## 4. Xử lý giá trị trả về và kiểu generic

`Method.invoke()` luôn trả về `Object`. Với component tham chiếu, kết quả là đối tượng tương ứng; với kiểu nguyên thủy, kết quả được boxing:

| Kiểu accessor | Giá trị từ `invoke()` |
| --- | --- |
| `String` | Một đối tượng `String` |
| `BigDecimal` | Một đối tượng `BigDecimal` |
| `int` | Một `Integer` |
| `long` | Một `Long` |
| `boolean` | Một `Boolean` |

Ví dụ:

```java
import java.lang.reflect.Method;

public class CounterAccessorDemo {
    record Counter(int value) {}

    public static void main(String[] args) throws ReflectiveOperationException {
        Counter counter = new Counter(7);
        Method accessor = Counter.class
                .getRecordComponents()[0]
                .getAccessor();
        Object result = accessor.invoke(counter);

        System.out.println(result);                    // 7
        System.out.println(result instanceof Integer); // true
    }
}
```

Nếu cần sử dụng giá trị như một kiểu cụ thể, phải kiểm tra hoặc chuyển kiểu phù hợp:

```java
if (result instanceof Integer number) {
    int value = number;
    System.out.println(value + 1);
}
```

Với record generic:

```java
record Box<T>(T value) {}
```

Accessor của component `value` có kiểu khai báo là `T`, nhưng kiểu trả về ở mức bytecode chịu type erasure. Khi gọi qua reflection, kết quả vẫn là `Object`. Giá trị thực tế có thể là `String`, `Integer` hoặc một kiểu tham chiếu khác tùy đối tượng được tạo. Nếu cần metadata kiểu khai báo, đọc thêm `component.getGenericType()` hoặc `accessor.getGenericReturnType()`.

Không nên ép kiểu kết quả một cách mù quáng. Nếu xử lý record không biết trước kiểu, giữ kết quả ở dạng `Object` hoặc kiểm tra bằng pattern matching cho `instanceof` trước khi dùng.

## 5. Quyền truy cập: vì sao accessor public vẫn có thể gặp lỗi?

Accessor của record là phương thức `public`. Điều đó cho phép gọi nó như API công khai khi lớp record và package của nó có thể truy cập từ vị trí gọi.

Tuy nhiên, quyền truy cập phương thức còn phụ thuộc vào **lớp khai báo phương thức** và ranh giới module/package. Một phương thức public nằm trong một lớp không thể truy cập từ nơi gọi vẫn có thể gây `IllegalAccessException` khi gọi bằng reflection.

Để lời gọi qua API công khai hoạt động ổn định:

1. Đặt record trong một lớp có thể truy cập từ nơi gọi, thường là `public record` hoặc một record lồng `public` trong lớp public.
2. Nếu dùng Java Platform Module System, package chứa kiểu public cần được module khai báo `exports` cho module gọi.
3. Gọi accessor lấy từ `getAccessor()` và dùng `Method.invoke()` như ví dụ.
4. Xử lý `IllegalAccessException` để phát hiện lỗi cấu hình hoặc quyền truy cập.

Ví dụ khai báo module có package public:

```java
module com.example.models {
    exports com.example.models.api;
}
```

Khi kiểu record nằm trong package `com.example.models.api` và được khai báo public, module khác đọc được API public của package sau khi khai báo quan hệ đọc module thích hợp.

Không cần gọi `setAccessible(true)` chỉ để sử dụng accessor public trong một API công khai được cấu hình đúng. `setAccessible` và `trySetAccessible` phục vụ các tình huống truy cập sâu hơn; chúng chịu giới hạn của module và không phải cách sửa mặc định cho một API public có thiết kế hoặc cấu hình package chưa phù hợp.

## 6. Các ngoại lệ cần hiểu khi gọi `Method.invoke()`

| Ngoại lệ | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalAccessException` | Caller không có quyền truy cập phương thức hoặc lớp khai báo | Kiểm tra modifier, khả năng truy cập lớp và cấu hình module |
| `IllegalArgumentException` | Đối tượng đích không tương thích với lớp khai báo hoặc truyền sai số/kiểu đối số | Dùng đúng instance của record; accessor không cần đối số |
| `NullPointerException` | Đối tượng đích là `null` trong khi accessor là phương thức instance | Kiểm tra instance trước khi gọi |
| `InvocationTargetException` | Chính accessor phát sinh exception khi thực thi | Đọc `getCause()` để xem nguyên nhân gốc |

`InvocationTargetException` khác với `IllegalAccessException`: trường hợp đầu nghĩa là lời gọi đã đi vào accessor nhưng phần thực thi của accessor phát sinh lỗi; trường hợp sau nghĩa là reflection không thể thực hiện lời gọi do quyền truy cập.

Nếu accessor được khai báo tường minh trong record, lời gọi reflection sẽ chạy phần triển khai của phương thức đó. Vì vậy, không nên giả định mọi accessor tùy chỉnh đều chỉ là thao tác đọc field đơn giản hoặc không thể phát sinh lỗi runtime.

Đoạn xử lý cốt lõi dưới đây đặt bên trong hàm đang duyệt component; biến `accessor` và `recordInstance` đã được xác định trước đó:

```java
try {
    Object result = accessor.invoke(recordInstance);
} catch (IllegalAccessException e) {
    throw new IllegalStateException("Cannot access accessor", e);
} catch (InvocationTargetException e) {
    Throwable cause = e.getCause();
    System.err.println("Accessor threw: " + cause);
}
```

Trong ứng dụng thực tế, nên ghi lại tên record, tên component và nguyên nhân gốc để hỗ trợ chẩn đoán.

## 7. Khi nào dùng accessor trực tiếp, khi nào dùng reflection?

| Tình huống | Cách phù hợp |
| --- | --- |
| Biết kiểu record khi biên dịch | Gọi accessor trực tiếp, ví dụ `product.code()` |
| Kiểu record chỉ biết ở runtime | `getAccessor()` kết hợp `Method.invoke()` |
| Muốn tạo schema từ nhiều loại record | Duyệt `getRecordComponents()` và đọc metadata |
| Muốn gọi một accessor đã biết tên và kiểu | Gọi trực tiếp nếu có thể; nếu dùng reflection, lấy đúng `Method` từ component |
| Muốn đọc field nội bộ hoặc trạng thái không thuộc component | Xem lại yêu cầu; accessor chỉ cung cấp API của component |

Ví dụ, nếu đã biết kiểu:

```java
Product product = new Product("BK-100", 3, new BigDecimal("125000"));
String code = product.code();
```

đơn giản và an toàn kiểu hơn so với reflection. Nếu xây dựng thư viện dùng chung cho `Product`, `Customer`, `Order` và nhiều record khác, reflection giúp xử lý chúng qua cùng một luồng.

## 8. Bài tập tự kiểm tra

Cho record:

```java
record Account(String username, boolean active, long createdAt) {}
```

Hãy trả lời:

1. `Account.class.getRecordComponents()[0].getAccessor().getName()` trả về gì?
2. Accessor của `active` có bao nhiêu tham số?
3. Khi gọi accessor `active` qua `Method.invoke(account)`, kết quả có kiểu runtime nào?
4. `Method.invoke()` trả về kiểu gì trong khai báo API?
5. Ngoại lệ nào bọc exception phát sinh từ chính accessor?
6. Vì sao accessor public trong một lớp không thể truy cập vẫn có thể gây lỗi reflection?

**Đáp án:**

1. `"username"`.
2. `0`.
3. `Boolean` do giá trị nguyên thủy `boolean` được boxing thành wrapper khi trả qua `Object`.
4. `Object`.
5. `InvocationTargetException`; nguyên nhân gốc nằm trong `getCause()`.
6. Vì kiểm tra truy cập còn xét lớp khai báo và khả năng truy cập package/module, không chỉ modifier của phương thức.

## Ghi nhớ

**`RecordComponent.getAccessor()` trả về `Method` đại diện cho accessor public của component.** Khi kiểu chỉ được biết ở runtime, gọi `accessor.invoke(recordInstance)` để đọc giá trị; kết quả có kiểu `Object` và giá trị nguyên thủy được boxing. Hãy kiểm tra instance, xử lý `IllegalAccessException` và đọc `InvocationTargetException.getCause()` khi accessor phát sinh lỗi. Với kiểu đã biết lúc biên dịch, gọi accessor trực tiếp vẫn là lựa chọn đơn giản nhất.

## Tài liệu tham khảo

- [Oracle Java SE API — `RecordComponent.getAccessor()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html#getAccessor())
- [Oracle Java SE API — `Method.invoke(Object, Object...)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Oracle Java SE API — `InvocationTargetException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [Oracle Java SE — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html)
- [Oracle Java Platform Module System — `exports`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7.2)
