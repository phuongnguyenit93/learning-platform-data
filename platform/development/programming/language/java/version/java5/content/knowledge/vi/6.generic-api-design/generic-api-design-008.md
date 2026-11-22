# Giữ tính an toàn kiểu tại ranh giới reflection

## 1. Reflection tạo ra một ranh giới cần được kiểm tra rõ ràng

Với lời gọi Java thông thường, trình biên dịch biết phương thức, kiểu đối số và kiểu kết quả:

```java
String title = source.title();
```

Khi chuyển sang reflection, ta có thể làm việc bằng tên thành viên và các giá trị `Object`:

```java
Method method = source.getClass().getMethod("title");
Object result = method.invoke(source);
```

Hai dòng là đoạn minh họa; cần import `java.lang.reflect.Method` và xử lý các ngoại lệ reflection khi đặt vào chương trình.

Reflection vẫn kiểm tra những điều như khả năng truy cập, kiểu nhận lời gọi và khả năng truyền đối số theo chữ ký runtime. Tuy nhiên, nó không giữ toàn bộ quan hệ generic mà lời gọi nguồn bình thường được trình biên dịch bảo vệ.

Vì vậy, “dùng reflection nhưng không có cảnh báo unchecked” chưa đủ chứng minh rằng mọi dữ liệu generic vẫn đúng.

Mục tiêu là xây một ranh giới:

```text
Du lieu / thanh vien duoc tim dong
        |
        v
Kiem tra hinh dang va hop dong
        |
        v
Thuc hien reflection trong pham vi nho
        |
        v
Xac thuc ket qua va cau truc du lieu
        |
        v
Tra lai API co kieu ro rang
```

Bên ngoài ranh giới đó, mã nghiệp vụ nên nhận được các kiểu cụ thể hoặc interface đã biết, thay vì tiếp tục truyền `Method`, `Field` và `Object` khắp nơi.

Bài áp dụng cho Java hiện nay và sử dụng chương trình chạy với JDK 17 trở lên.

## 2. Tách bốn câu hỏi thay vì dùng một phép ép kiểu

Khi một thành viên được tìm hoặc gọi động, cần kiểm tra từng lớp hợp đồng:

| Câu hỏi | Ví dụ |
| --- | --- |
| Đã chọn đúng thành viên chưa? | Đúng tên, kiểu tham số, phương thức instance hay static |
| Giá trị truyền vào có phù hợp không? | Đúng đối tượng nhận lời gọi, đối số đúng vị trí và kiểu |
| Kết quả runtime có phù hợp không? | Đúng lớp/interface, đúng chính sách `null` |
| Dữ liệu bên trong có phù hợp không? | Từng phần tử của danh sách là chuỗi, cấu trúc lồng nhau đúng |

Một phép ép sang `T` không tự trả lời cả bốn câu hỏi.

Ví dụ, nếu một helper chỉ lấy kết quả của `method.invoke(receiver)` rồi ép bằng `(T)`, phép ép đó không có một token runtime riêng của `T` để xác thực kết quả theo kiểu cụ thể mà người gọi mong muốn. Nó có thể đẩy lỗi sang xa điểm reflection.

Thay vào đó, nhận `Class<T>` cho kết quả có thể kiểm tra, hoặc chuyển sang một interface có kiểu sau khi nạp đối tượng.

## 3. Nếu đã có interface chung, kết thúc reflection càng sớm càng tốt

Giả sử mọi thành phần được nạp động đều phải thực hiện:

```java
public interface Task {
    String execute();
}
```

Có thể nhận một `Class<?>` chưa biết, kiểm tra nó có phù hợp với `Task` không, rồi khởi tạo và trả `Task`:

```java
Class<? extends Task> checked = candidate.asSubclass(Task.class);
Task task = checked.getConstructor().newInstance();
String result = task.execute();
```

Đây là các dòng minh họa bên trong một phương thức có biến `candidate` và xử lý ngoại lệ phù hợp.

`asSubclass` kiểm tra quan hệ kiểu của token lớp. Nếu `candidate` không mô tả một kiểu phù hợp với `Task`, nó ném `ClassCastException` thay vì cho phép một phép ép `Class<?>` thiếu bằng chứng.

Kết quả sau khởi tạo đã có kiểu `Task`. Các lần `execute()` tiếp theo là lời gọi Java thông thường, được trình biên dịch kiểm tra, không cần `Method.invoke`.

Điều này hữu ích khi reflection chỉ cần để chọn hoặc khởi tạo cách cài đặt. Nếu giao thức có thể được mô tả bằng interface, đừng giữ toàn bộ giao thức dưới dạng tên phương thức chuỗi.

`getConstructor().newInstance()` cũng có hợp đồng riêng: lớp cần có constructor công khai không đối số phù hợp và phải khởi tạo được. Việc lớp thực hiện interface không chứng minh constructor tồn tại, lớp không trừu tượng hoặc quá trình khởi tạo sẽ thành công.

Cơ chế kiểm tra token được mô tả trong [Class.asSubclass](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#asSubclass(java.lang.Class)).

## 4. Khi thực sự cần Method.invoke, phải xác định hợp đồng của adapter

Ví dụ trong bài có một adapter:

```java
static <T> T invokeRequired(
        Object receiver, String methodName, Class<T> expected)
        throws ReflectiveOperationException
```

Đây là chữ ký minh họa, triển khai đầy đủ nằm ở phần sau.

Adapter chỉ hỗ trợ:

- Phương thức công khai, không có đối số.
- Phương thức instance, không phải static.
- Có kết quả, không phải `void`.
- Kết quả khác `null`.
- Token kết quả mô tả kiểu tham chiếu, chẳng hạn `String.class` hoặc `Integer.class`.
- Kiểu lớp ngoài của kết quả phải phù hợp với token.

Các giới hạn này giúp API có hợp đồng cụ thể. Nó không phải một bộ gọi mọi phương thức Java với mọi dạng chuyển đổi.

### Vì sao dùng Class.cast cho kết quả?

```java
Object result = method.invoke(receiver);
return expected.cast(Objects.requireNonNull(result, "result"));
```

`Class<T>.cast` kiểm tra kiểu runtime mà token biểu diễn và trả kết quả có kiểu `T`. Không cần phép ép `(T)` không được kiểm tra.

Nếu phương thức trả số nguyên mà token là `String.class`, adapter từ chối kết quả ngay tại ranh giới.

Tuy nhiên, phương thức đích **đã được chạy** trước khi kiểm tra kết quả. Nếu nó có tác dụng phụ, lỗi kiểm tra kiểu kết quả không hoàn tác các tác dụng phụ đó.

Khi giao thức đã có yêu cầu rõ về kiểu khai báo, có thể kiểm tra metadata thành viên ngay lúc liên kết adapter để phát hiện lỗi sớm hơn. Một adapter nghiêm ngặt cho phương thức trả `String` không cần đợi chạy rồi mới phát hiện khai báo trả `void`.

Với một adapter cho phép phương thức khai báo trả `Object` nhưng giá trị thực tế phải là chuỗi, kiểm tra runtime vẫn cần thiết. Phải chọn và công bố rõ mức hợp đồng đó.

## 5. Chương trình đầy đủ: kết quả có kiểu và phản ví dụ Field.set

Lưu thành `ReflectionTypeBoundaryDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ReflectionTypeBoundaryDemo {
    public interface Task {
        String execute();
    }

    public static final class GreetingTask implements Task {
        public GreetingTask() {
        }

        @Override
        public String execute() {
            return "hello from typed task";
        }
    }

    public static final class Source {
        public String title() {
            return "report";
        }

        public int count() {
            return 3;
        }

        public int twice(int value) {
            return value * 2;
        }

        public List<String> names() {
            return List.of("An", "Binh");
        }

        public List<?> mixed() {
            return List.of("An", 42);
        }

        public String failure() {
            throw new IllegalStateException("source failure");
        }

        public void reset() {
        }
    }

    public static final class Slot<T> {
        public T value;

        public Slot(T value) {
            this.value = value;
        }
    }

    static <T> T create(Class<?> implementation, Class<T> contract)
            throws ReflectiveOperationException {
        Objects.requireNonNull(implementation, "implementation");
        Objects.requireNonNull(contract, "contract");
        if (contract.isPrimitive()) {
            throw new IllegalArgumentException("reference contract required");
        }
        Class<? extends T> checked = implementation.asSubclass(contract);
        return checked.getConstructor().newInstance();
    }

    static <T> T invokeRequired(
            Object receiver, String methodName, Class<T> expected)
            throws ReflectiveOperationException {
        Objects.requireNonNull(receiver, "receiver");
        Objects.requireNonNull(expected, "expected");
        if (expected.isPrimitive()) {
            throw new IllegalArgumentException("reference result token required");
        }

        Method method = receiver.getClass().getMethod(methodName);
        if (Modifier.isStatic(method.getModifiers())
                || method.getReturnType() == void.class) {
            throw new IllegalArgumentException(
                    "a non-void instance method is required");
        }

        Object result = method.invoke(receiver);
        return expected.cast(Objects.requireNonNull(result, "result"));
    }

    static List<String> validateNames(Object value) {
        if (!(value instanceof List<?> elements)) {
            throw new IllegalArgumentException("a list is required");
        }

        List<String> result = new ArrayList<>();
        for (Object element : elements) {
            result.add(String.class.cast(
                    Objects.requireNonNull(element, "name")));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Task task = create(GreetingTask.class, Task.class);
        System.out.println(task.execute());

        Source source = new Source();
        String title = invokeRequired(source, "title", String.class);
        Integer count = invokeRequired(source, "count", Integer.class);
        System.out.println("title = " + title);
        System.out.println("count = " + count);

        Method twice = Source.class.getMethod("twice", int.class);
        Integer doubled = Integer.class.cast(twice.invoke(source, 21));
        System.out.println("twice = " + doubled);

        Object namesResult = invokeRequired(source, "names", Object.class);
        System.out.println("names = " + validateNames(namesResult));

        try {
            create(String.class, Task.class);
        } catch (ClassCastException exception) {
            System.out.println("wrong implementation rejected");
        }

        try {
            invokeRequired(source, "count", String.class);
        } catch (ClassCastException exception) {
            System.out.println("wrong result type rejected");
        }

        try {
            Object mixed = invokeRequired(source, "mixed", Object.class);
            validateNames(mixed);
        } catch (ClassCastException exception) {
            System.out.println("wrong list element rejected");
        }

        try {
            invokeRequired(source, "failure", String.class);
        } catch (InvocationTargetException exception) {
            System.out.println("target cause = "
                    + exception.getCause().getClass().getSimpleName());
        }

        try {
            invokeRequired(source, "reset", Object.class);
        } catch (IllegalArgumentException exception) {
            System.out.println("void method rejected before invocation");
        }

        try {
            Source.class.getMethod("twice", Integer.class);
        } catch (NoSuchMethodException exception) {
            System.out.println("lookup requires primitive parameter token");
        }

        Slot<String> slot = new Slot<>("safe");
        Field field = Slot.class.getField("value");
        field.set(slot, 42);
        try {
            String text = slot.value;
            System.out.println(text);
        } catch (ClassCastException exception) {
            System.out.println("reflective field write broke T");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror ReflectionTypeBoundaryDemo.java
java ReflectionTypeBoundaryDemo
```

Stdout:

```text
hello from typed task
title = report
count = 3
twice = 42
names = [An, Binh]
wrong implementation rejected
wrong result type rejected
wrong list element rejected
target cause = IllegalStateException
void method rejected before invocation
lookup requires primitive parameter token
reflective field write broke T
```

Chương trình biên dịch sạch cảnh báo nhưng vẫn chủ động minh họa một phép ghi reflection phá hợp đồng generic ở cuối. Điều đó cho thấy giới hạn của việc chỉ dựa vào bảng cảnh báo.

Lớp `Slot<T>` và trường `public` trong ví dụ được dùng để quan sát hành vi reflection. Đây không phải thiết kế lớp chứa được khuyến nghị cho mã ứng dụng.

## 6. Đọc từng lớp kiểm tra của chương trình

### 6.1. Kiểm tra kiểu cách cài đặt trước khi khởi tạo

`create(GreetingTask.class, Task.class)`:

1. Kiểm tra các token khác `null`.
2. Từ chối contract primitive.
3. Gọi `asSubclass` để liên kết token cách cài đặt với kiểu hợp đồng.
4. Tìm constructor công khai không đối số.
5. Khởi tạo đối tượng có kiểu phù hợp với `T`.

`create(String.class, Task.class)` bị từ chối trước khi khởi tạo vì `String` không thực hiện `Task`.

Hợp đồng kiểu đã biết không cần bị chuyển thành một phép ép unchecked của `Class`. Ta để API `asSubclass` cung cấp token có kiểu đã được kiểm tra.

### 6.2. Hình dạng phương thức được kiểm tra trước khi gọi

`getMethod(methodName)` tìm phương thức công khai không đối số. Adapter từ chối phương thức static và phương thức khai báo trả `void`.

Vì vậy, lời gọi với `"reset"` bị từ chối trước khi `reset` được thực thi. Điều này khác với lỗi kết quả sai lớp: trường hợp `"count"` cùng token `String.class` chỉ bị phát hiện sau khi `count` đã trả giá trị.

Nếu cần công bố thêm quy tắc về lớp khai báo, annotation, tham số hoặc kiểu trả về, hãy kiểm tra chúng trong giai đoạn liên kết adapter.

Không lấy “phương thức đầu tiên cùng tên” từ một mảng phương thức rồi hy vọng nó đúng. Overload, thành viên kế thừa và các phương thức do trình biên dịch sinh có thể làm lựa chọn đó sai.

### 6.3. Giá trị nguyên thủy được đóng hộp khi đi ra qua Object

`Source.count()` khai báo trả `int`. `Method.invoke` trả kết quả qua `Object` nên giá trị được đóng hộp thành `Integer`.

Do đó, adapter dùng `Integer.class` để kiểm tra giá trị trả về:

```java
Integer count = invokeRequired(source, "count", Integer.class);
```

`int.class` mô tả kiểu nguyên thủy, không phải lớp của đối tượng wrapper. Helper chủ động từ chối token primitive cho hợp đồng kiểm tra đối tượng này.

Nếu viết một bộ kiểm tra metadata trả về tổng quát, cần phân biệt kiểu khai báo primitive với kiểu wrapper của giá trị qua reflection. Không áp dụng máy móc `expected.isAssignableFrom(method.getReturnType())` mà bỏ qua chính sách primitive/wrapper của adapter.

### 6.4. Constructor và phương thức đích có thể tự ném ngoại lệ

`Source.failure()` ném `IllegalStateException`. Khi gọi bằng reflection, lỗi của đích được bọc trong `InvocationTargetException`.

Ví dụ đọc `getCause()` để phân biệt “phương thức đích đã chạy rồi lỗi” với “không tìm thấy hoặc không gọi được thành viên”.

Không nuốt mọi ngoại lệ rồi trả `null`. Cách đó làm mất cả nguyên nhân lẫn phân biệt giữa “không có kết quả” và “thực thi thất bại”.

Hợp đồng wrapper được mô tả trong [InvocationTargetException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/InvocationTargetException.html).

## 7. Tìm phương thức khác với truyền đối số khi gọi

Đoạn trong chương trình:

```java
Method twice = Source.class.getMethod("twice", int.class);
Integer doubled = Integer.class.cast(twice.invoke(source, 21));
```

có hai giai đoạn khác nhau.

### Giai đoạn tìm thành viên

`getMethod` nhận các token đúng kiểu tham số khai báo. Phương thức `twice(int)` được tìm bằng `int.class`.

Tìm bằng `Integer.class` không có nghĩa yêu cầu Java tự áp dụng autoboxing để chọn overload. Nó hỏi một chữ ký khai báo khác và dẫn tới `NoSuchMethodException` trong ví dụ.

Đối với phương thức generic, token tham số để tra cứu phải theo kiểu đã xóa của khai báo. Ví dụ `<T> T echo(T)` được tra theo `Object.class`; nếu `T extends Number` thì kiểu bị xóa có thể là `Number.class`.

### Giai đoạn thực thi thành viên đã chọn

Sau khi có đúng `Method`, `invoke` kiểm tra và chuyển đối số theo các quy tắc được hỗ trợ. Nó có thể thực hiện mở hộp và một số chuyển đổi mở rộng primitive, nhưng không tự tìm lại overload theo đối tượng runtime.

Nếu đối tượng nhận lời gọi không phù hợp với phương thức instance, số đối số sai hoặc chuyển đổi không hợp lệ, lời gọi có thể bị từ chối bằng `IllegalArgumentException`.

Không coi reflection là một phép “bỏ kiểm tra hết”. Nó giữ các kiểm tra runtime theo chữ ký mà nó nhìn thấy, nhưng mức thông tin đó không tương đương mọi ràng buộc generic ở mã nguồn.

Các hành vi này thuộc hợp đồng của [Method.invoke](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)).

## 8. Metadata generic không tự xác thực nội dung

`Source.names()` khai báo `List<String>`. Có thể đọc metadata generic của phương thức để thấy mô tả đó.

Tuy nhiên:

- `Method.invoke` vẫn trả một `Object`.
- Kiểu lớp ngoài của kết quả là một danh sách.
- Metadata là thông tin về khai báo, không phải một quá trình duyệt kiểm tra mọi phần tử của đối tượng được trả về.
- Dữ liệu có thể đã bị làm sai qua một đường reflection hoặc một thao tác unchecked khác.

Không nên sửa bằng:

```java
// List<String> names = (List<String>) method.invoke(source);
```

Phép ép này không xác thực từng phần tử và có thể tạo cảnh báo unchecked.

Ví dụ dùng `validateNames`:

1. Kiểm tra cấu trúc ngoài bằng `instanceof List<?>`.
2. Từ chối `null` ở từng phần tử.
3. Dùng `String.class.cast` cho từng giá trị.
4. Tạo một danh sách mới có kiểu `List<String>`.
5. Trả bản sao không cho sửa cấu trúc.

Vì vậy, kết quả của `mixed()` bị từ chối tại vị trí có `Integer`, còn `names()` tạo dữ liệu có hợp đồng rõ ràng.

Nếu cấu trúc là `List<List<String>>` hoặc một đối tượng có trường lồng nhau, bộ xác thực cần kiểm tra theo cấu trúc tương ứng. Chỉ thêm một token `List.class` không giải quyết được yêu cầu đó.

Việc sao chép tách cấu trúc kết quả khỏi các alias của danh sách nguồn. Nó không sao chép sâu mọi đối tượng phần tử và không tự xử lý nguồn bị thay đổi đồng thời trong lúc duyệt.

## 9. Field.set có thể phá quan hệ generic dù không có unchecked warning

Đây là phản ví dụ quan trọng của chương trình.

Khai báo:

```java
public static final class Slot<T> {
    public T value;

    public Slot(T value) {
        this.value = value;
    }
}
```

Ở mã Java bình thường:

```java
Slot<String> slot = new Slot<>("safe");
// slot.value = 42; // Khong bien dich
```

Nhưng với reflection:

```java
Field field = Slot.class.getField("value");
field.set(slot, 42);
```

`T` không có giới hạn tường minh nên bị xóa về `Object`. Kiểu trường runtime cho phép một đối tượng `Integer`. `Field.set` không biết từ chính đối tượng `slot` rằng đối số kiểu ở lời khai báo của người gọi là `String`.

Kết quả là `Slot<String>` chứa số nguyên. Dòng:

```java
String text = slot.value;
```

mới gây `ClassCastException`.

Không có phép ép unchecked trong các dòng reflection này. Biên dịch sạch `-Werror` không thể thay thế việc bảo vệ hợp đồng ở ranh giới phản chiếu.

Nếu `T extends Number` thì runtime có thể chặn một chuỗi, nhưng một giá trị `Double` vẫn có thể phá hợp đồng của một `Slot<Integer>`. Giới hạn sau xóa không giữ toàn bộ đối số kiểu cụ thể của đối tượng.

Hành vi ghi được quy định theo kiểu trường và khả năng chuyển đổi runtime trong [Field.set](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object)).

### Cách giữ an toàn cho đường ghi

Ưu tiên một phương thức có kiểu hoặc một adapter xác thực giá trị trước khi thay đổi trạng thái. Với một lớp chứa do mình thiết kế, có thể giữ `Class<T>` và dùng `type.cast(value)` theo hợp đồng của lớp thay vì công khai trường cho các đường ghi tùy ý.

Nếu dữ liệu là generic lồng nhau, cần bộ xác thực có cấu trúc. Một token cho lớp ngoài không tự bảo vệ phần tử bên trong.

Đối với thao tác có nhiều trường, hãy xác thực dữ liệu trước các bước ghi khi có thể. Nếu quá trình ghi có thể thất bại giữa chừng, phải xác định rõ đối tượng có thể bị cập nhật một phần hay không; reflection không tự cung cấp giao dịch hoặc hoàn tác.

## 10. Phân biệt các nhóm lỗi để không làm mất nguyên nhân

| Nhóm lỗi | Ý nghĩa thường gặp |
| --- | --- |
| `NoSuchMethodException`, `NoSuchFieldException` | Tên hoặc chữ ký thành viên không tồn tại theo cách tra cứu |
| `IllegalAccessException` | Không được phép truy cập thành viên trong ngữ cảnh hiện tại |
| `InstantiationException` | Không thể tạo đối tượng theo loại lớp đã chọn |
| `IllegalArgumentException` | Đối số reflection hoặc hợp đồng adapter không phù hợp |
| `InvocationTargetException` | Constructor hoặc phương thức đích đã ném lỗi |
| `ClassCastException` | Token hoặc bộ xác thực từ chối kiểu dữ liệu |
| `NullPointerException` theo hợp đồng helper | Giá trị bắt buộc khác `null` bị thiếu |

Bảng là hướng chẩn đoán, không phải danh sách đầy đủ mọi lỗi mà JVM có thể phát sinh.

Một adapter có thể ánh xạ các lỗi sang ngoại lệ miền phù hợp, nhưng nên giữ nguyên nhân gốc bằng `cause`. Đừng gộp tất cả thành một giá trị “không tìm thấy” nếu việc thực thi thực sự đã thất bại.

## 11. Khả năng truy cập không đồng nghĩa an toàn kiểu

`getMethod` tìm phương thức công khai, gồm những phương thức công khai kế thừa có liên quan. `getDeclaredMethod` tìm thành viên do chính lớp khai báo, có thể bao gồm thành viên không công khai.

Tìm được một đối tượng `Method` hoặc `Field` không có nghĩa tự động có quyền gọi hay ghi.

Việc yêu cầu thay đổi khả năng truy cập bằng các API reflection cũng không xác thực kiểu dữ liệu. Nó giải quyết một câu hỏi khác với “giá trị này có đáp ứng `T` hoặc cấu trúc nghiệp vụ không?”.

Ví dụ trong bài chỉ dùng các thành viên công khai và không thay đổi cờ truy cập. Khi làm việc với module Java hoặc thành viên không công khai, xử lý giới hạn truy cập theo hợp đồng nền tảng; không coi việc vượt được một rào truy cập là bằng chứng rằng dữ liệu đã an toàn.

## 12. Thiết kế adapter để phần còn lại của chương trình có thể tin cậy

Một ranh giới tốt thường có các đặc điểm:

- Tên và hình dạng thành viên được chọn theo giao thức cụ thể.
- Kiểm tra phần có thể biết trước ngay khi liên kết adapter.
- Phân biệt rõ phương thức instance, static, primitive và `void`.
- Giá trị không kiểu được kiểm tra trước khi trở thành kết quả có kiểu.
- Dữ liệu tập hợp được kiểm tra đến đúng độ sâu mà hợp đồng yêu cầu.
- Trạng thái nội bộ không bị phơi ra cho các đường ghi đi vòng quy tắc.
- Ngoại lệ giữ được nguyên nhân thực thi.
- Kết quả được đưa về interface hoặc kiểu miền rõ ràng càng sớm càng tốt.

Không cần xây một framework reflection tổng quát nếu chỉ có một giao thức nhỏ. Một adapter riêng cho thao tác đọc cấu hình, gọi một thành phần mở rộng hoặc lấy dữ liệu báo cáo thường có hợp đồng dễ kiểm tra hơn một hàm “gọi bất cứ thứ gì”.

Nếu không cần tra cứu động, một interface và lời gọi thông thường có thể đã đáp ứng yêu cầu. Reflection là một cơ chế liên kết, không tự thay thế thiết kế API.

## 13. Thực hành tự kiểm tra

### Bài 1: Vì sao (T) không đủ?

Một helper nhận `Object` từ `Method.invoke` rồi ép sang `T`. Người gọi gán kết quả cho `String`. Helper đã chứng minh kết quả là chuỗi chưa?

**Đáp án:** chưa. Biến kiểu bị xóa không cung cấp token runtime cụ thể. Cần kiểm tra bằng một `Class<T>` phù hợp hoặc một bộ xác thực kết quả có cấu trúc.

### Bài 2: Metadata List<String> có kiểm tra từng phần tử không?

**Đáp án:** không tự động. Nó mô tả khai báo. Nếu ranh giới có thể nhận dữ liệu bị làm sai, phải kiểm tra nội dung để thiết lập hợp đồng đáng tin.

### Bài 3: Vì sao tìm twice bằng Integer.class thất bại?

**Đáp án:** phương thức khai báo `twice(int)`. Tra cứu thành viên yêu cầu token `int.class` tương ứng; không tự áp dụng autoboxing để chọn một chữ ký khác.

### Bài 4: Biên dịch không cảnh báo đã bảo vệ Slot<String> chưa?

**Đáp án:** chưa. `Field.set` có thể ghi số nguyên vào trường `T` bị xóa về `Object`. Cần kiểm soát và xác thực đường ghi reflection.

### Bài 5: Phương thức đích ném IllegalStateException thì bắt ở đâu?

**Đáp án:** khi gọi bằng `Method.invoke`, kiểm tra `InvocationTargetException` và nguyên nhân của nó. Phân biệt lỗi trong phương thức đích với lỗi tra cứu, truy cập hoặc kiểm tra dữ liệu.

### Bài 6: Kết quả sai kiểu có nghĩa phương thức chưa chạy không?

**Đáp án:** không. Kiểm tra bằng `Class.cast` ở kết quả diễn ra sau thực thi. Muốn phát hiện những sai lệch có thể biết trước, kiểm tra metadata thành viên lúc liên kết adapter; vẫn phải thiết kế riêng cho tác dụng phụ và lỗi giữa chừng.

Điểm cần giữ là phạm vi của bằng chứng: reflection kiểm tra được chữ ký runtime, còn hợp đồng generic và nội dung dữ liệu phải được adapter bảo vệ trước khi trả quyền tin cậy cho phần còn lại của chương trình.
