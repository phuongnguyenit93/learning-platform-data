# Reflection: `isAssignableFrom`, `cast` và `asSubclass`

Ba phương thức của `java.lang.Class` giúp xử lý **tương thích kiểu tại runtime** khi lớp hoặc đối tượng chỉ được biết sau khi chương trình chạy, chẳng hạn khi nạp plugin, chọn implementation theo cấu hình hay xử lý kết quả từ reflection. Chúng liên quan nhau nhưng trả lời **ba câu hỏi khác nhau**:

| Phương thức | Câu hỏi | Đầu vào | Kết quả |
| --- | --- | --- | --- |
| `target.isAssignableFrom(source)` | Giá trị mang kiểu `source` có thể gán cho biến kiểu `target` không? | `Class<?>` | `boolean` |
| `target.cast(object)` | Đối tượng `object` có phù hợp với kiểu `target` không? | `Object` | Đối tượng được kiểm tra và trả về với kiểu `T`, hoặc ném `ClassCastException` |
| `candidate.asSubclass(base)` | Kiểu `candidate` có thể được xem là lớp con/kiểu triển khai của `base` không? | `Class<U>` | Chính token `Class` hiện tại với kiểu tĩnh `Class<? extends U>`, hoặc ném `ClassCastException` |

Điểm chung là chúng dựa trên **danh tính kiểu ở runtime** và quan hệ kế thừa/triển khai thực tế. Chúng không tạo đối tượng mới, không ép kiểu dữ liệu theo nghĩa chuyển giá trị, và không thay thế việc kiểm tra generic type arguments.

## 1. Nền tảng: `Class<T>` là token kiểu

Ví dụ `String.class` có kiểu tĩnh `Class<String>`; `Runnable.class` là `Class<Runnable>`. Khi tên lớp chỉ có ở runtime, chẳng hạn sau `Class.forName("...")`, ta thường chỉ có `Class<?>`: biết có một kiểu cụ thể nhưng chưa biết đó là kiểu nào lúc biên dịch.

Giả sử:

~~~java
interface Task {}
class EmailTask implements Task {}
class Other {}
~~~

Các quan hệ sau là hợp lệ:

~~~java
Task task = new EmailTask();   // widening reference conversion
Object value = task;           // upcast hợp lệ
~~~

Ngược lại, `EmailTask task = (EmailTask) someTask` cần kiểm tra giá trị thực tại runtime. Với reflection, ta cần kiểm tra quan hệ này thông qua `Class`, vì không phải lúc nào tên kiểu cũng được biết ở compile time.

## 2. `Class.isAssignableFrom(Class<?>)`: kiểm tra quan hệ hai kiểu

Cú pháp:

~~~java
boolean accepted = Target.class.isAssignableFrom(Source.class);
~~~

**Đọc từ phải sang trái:** “Một giá trị kiểu `Source` có gán được vào biến kiểu `Target` hay không?”. Gọi trên **kiểu đích** và truyền **kiểu nguồn**. Phương thức trả về `true` khi hai kiểu giống nhau hoặc nguồn có thể chuyển sang đích bằng **identity conversion** hay **widening reference conversion**; không tính những chuyển đổi cần cast thu hẹp kiểu.

~~~java
Task.class.isAssignableFrom(EmailTask.class);   // true: implements Task
EmailTask.class.isAssignableFrom(Task.class);   // false: chiều ngược
Task.class.isAssignableFrom(Task.class);        // true: cùng kiểu
Object.class.isAssignableFrom(Task.class);      // true: interface cũng quy chiếu được đến Object
Runnable.class.isAssignableFrom(Thread.class); // true: Thread implements Runnable
~~~

Một lớp có thể triển khai nhiều interface, nên quan hệ tương thích kiểu rộng hơn chuỗi `extends`. Không cần đối tượng `new EmailTask()` để thực hiện phép kiểm tra này.

### Khi nào nên dùng?

Khi duyệt `Class<?>` nhận được từ scan classpath, plugin registry hoặc `Class.forName`, kiểm tra nó có đáp ứng contract mong muốn trước khi đăng ký:

~~~java
Class<?> candidate = EmailTask.class;
if (Task.class.isAssignableFrom(candidate)) {
    // candidate mang kiểu Task hoặc một subtype/implementation tương thích.
}
~~~

Đây chỉ là kiểm tra **kiểu**. Một lớp phù hợp vẫn có thể là abstract, interface, thiếu constructor thích hợp hoặc không thể khởi tạo vì quyền truy cập.

### Primitive và array: các trường hợp dễ nhầm

`isAssignableFrom` xét tương thích **tham chiếu**, không mô phỏng mọi quy tắc gán ở ngôn ngữ Java:

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| `long.class.isAssignableFrom(int.class)` | `false` | Không áp dụng primitive widening `int → long` |
| `int.class.isAssignableFrom(int.class)` | `true` | Cùng token primitive |
| `Integer.class.isAssignableFrom(int.class)` | `false` | Không áp dụng boxing |
| `Number[].class.isAssignableFrom(Integer[].class)` | `true` | Mảng tham chiếu có covariance |
| `Object[].class.isAssignableFrom(String[].class)` | `true` | `String[]` là subtype của `Object[]` |
| `Object[].class.isAssignableFrom(int[].class)` | `false` | `int[]` không phải mảng các tham chiếu `Object` |
| `Object.class.isAssignableFrom(int[].class)` | `true` | Mọi array là một `Object` |
| `Cloneable.class.isAssignableFrom(int[].class)` | `true` | Mọi array implement `Cloneable` |
| `java.io.Serializable.class.isAssignableFrom(int[].class)` | `true` | Mọi array implement `Serializable` |

Array covariance **không bảo đảm** mọi phép ghi phần tử an toàn: một biến `Object[]` tham chiếu tới `String[]` vẫn ném `ArrayStoreException` nếu cố ghi `Integer` vào đó.

Truyền `null` vào `isAssignableFrom(null)` ném `NullPointerException` vì phương thức cần một token lớp để so sánh.

## 3. `Class.cast(Object)`: kiểm tra và chuyển kiểu một đối tượng

`Class<T>.cast(Object)` thực hiện runtime cast theo token kiểu đại diện. Kết quả có kiểu tĩnh `T` nhờ generic của token `Class<T>`:

~~~java
Object raw = "hello";
String text = String.class.cast(raw); // "hello"
Runnable.class.cast(raw);             // ClassCastException: String không implements Runnable
~~~

Đối với kiểu tham chiếu, có thể hiểu gần như cast có kiểm tra ở runtime. Sự khác biệt quan trọng là **kiểu đích có thể được truyền vào dưới dạng tham số**:

~~~java
static <T> T requireType(Class<T> expected, Object value) {
    return expected.cast(value);
}

// Gọi: String name = requireType(String.class, someObject);
~~~

Các trường hợp cần nhớ:

- `target.cast(null)` trả `null`, **không** ném exception.
- Đối tượng không thuộc kiểu đích hoặc subtype tương thích → `ClassCastException`.
- Cast thành công trả **chính cùng tham chiếu đối tượng**, không clone, chuyển đổi giá trị hay gọi constructor.
- `int.class.cast(Integer.valueOf(1))` ném `ClassCastException`: `int.class` là token primitive, còn đối tượng là `Integer`; boxing/unboxing không xảy ra trong `Class.cast`.
- `Class<?> unknown = ...` vẫn có thể gọi `unknown.cast(value)`, nhưng trình biên dịch không thể tự suy ra đó là `Task`. Cần token `Class<Task>` hoặc một bước thu hẹp token hợp lệ.

Nếu chỉ cần câu trả lời `true/false` cho **một đối tượng**, dùng `expected.isInstance(value)` (dynamic equivalent of `instanceof`), thay vì bắt `ClassCastException` để kiểm tra thường xuyên.

## 4. `Class.asSubclass(Class<U>)`: thu hẹp *token lớp* an toàn

Giả sử bộ quét trả về `Class<?>`, trong khi API phía sau cần `Class<? extends Task>`. Việc cast generic trực tiếp:

~~~java
// Không nên: unchecked cast, quan hệ kiểu không được xác minh tại runtime.
// Class<? extends Task> typed = (Class<? extends Task>) candidate;
~~~

không có bảo đảm an toàn từ trình biên dịch. Thay vào đó:

~~~java
Class<?> candidate = EmailTask.class;
Class<? extends Task> typed = candidate.asSubclass(Task.class);
~~~

`asSubclass` kiểm tra `Task.class.isAssignableFrom(candidate)` theo quan hệ tương thích và trả **chính token `candidate`** với kiểu tĩnh mới. Nếu không phù hợp, nó ném `ClassCastException`:

~~~java
String.class.asSubclass(Task.class); // ClassCastException
Task.class.asSubclass(Task.class);   // Hợp lệ: cùng kiểu
~~~

Tên “subclass” ở API này bao gồm trường hợp **chính kiểu đó** và kiểu **implement interface**. Nó không đòi hỏi phải có một nhánh `extends` trực tiếp.

Điều `asSubclass` thay đổi là **cách trình biên dịch hiểu token `Class`**; nó không cast một object instance. Muốn kiểm tra một object, dùng `cast`; muốn biết quan hệ giữa hai token mà không ném exception, dùng `isAssignableFrom`.

## 5. Ví dụ chạy hoàn chỉnh (Java 17+)

Lưu toàn bộ vào **`ClassCompatibilityDemo.java`**. Ví dụ bao gồm interface, quan hệ hướng gán, array, primitive, cast đối tượng và thu hẹp token để khởi tạo implementation bằng reflection.

~~~java
public class ClassCompatibilityDemo {
    interface Task { String run(); }

    static final class EmailTask implements Task {
        public EmailTask() {}

        @Override
        public String run() { return "sent"; }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> candidate = EmailTask.class;

        System.out.println("Task <- EmailTask: " + Task.class.isAssignableFrom(candidate));
        System.out.println("EmailTask <- Task: " + EmailTask.class.isAssignableFrom(Task.class));
        System.out.println("Task <- Task: " + Task.class.isAssignableFrom(Task.class));
        System.out.println("Object <- Task: " + Object.class.isAssignableFrom(Task.class));
        System.out.println("Number[] <- Integer[]: " + Number[].class.isAssignableFrom(Integer[].class));
        System.out.println("Object[] <- int[]: " + Object[].class.isAssignableFrom(int[].class));
        System.out.println("Object <- int[]: " + Object.class.isAssignableFrom(int[].class));
        System.out.println("long <- int: " + long.class.isAssignableFrom(int.class));
        System.out.println("int <- int: " + int.class.isAssignableFrom(int.class));

        Object obj = new EmailTask();
        Task task = Task.class.cast(obj);
        System.out.println("cast: " + task.run());
        System.out.println("null cast: " + (Task.class.cast(null) == null));

        Class<? extends Task> typedClass = candidate.asSubclass(Task.class);
        Task created = typedClass.getDeclaredConstructor().newInstance();
        System.out.println("asSubclass: " + created.run());

        try { Task.class.cast("text"); }
        catch (ClassCastException e) {
            System.out.println("cast error: " + e.getClass().getSimpleName());
        }

        try { String.class.asSubclass(Task.class); }
        catch (ClassCastException e) {
            System.out.println("asSubclass error: " + e.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 ClassCompatibilityDemo.java
java ClassCompatibilityDemo
~~~

Stdout chính xác (đã biên dịch và chạy với `--release 17`):

~~~text
Task <- EmailTask: true
EmailTask <- Task: false
Task <- Task: true
Object <- Task: true
Number[] <- Integer[]: true
Object[] <- int[]: false
Object <- int[]: true
long <- int: false
int <- int: true
cast: sent
null cast: true
asSubclass: sent
cast error: ClassCastException
asSubclass error: ClassCastException
~~~

Các dòng bắt lỗi in **tên loại exception** qua `getSimpleName()` nên không phụ thuộc vào chi tiết thông báo lỗi giữa các bản JDK. Hai thao tác `cast` và `asSubclass` chỉ xác minh tương thích: lời gọi constructor qua `getDeclaredConstructor().newInstance()` mới thực sự tạo đối tượng.

## 6. Áp dụng trong thiết kế plugin / factory

Một factory có thể nhận tên lớp từ cấu hình và contract kiểu từ caller. **Đoạn sau là phương thức minh họa**, cần đặt bên trong một class Java và cung cấp một implementation hợp lệ; nó không phải chương trình độc lập:

~~~java
static <S> S create(String className, Class<S> contract)
        throws ReflectiveOperationException {
    Class<?> raw = Class.forName(className);

    if (!contract.isAssignableFrom(raw)) {
        throw new IllegalArgumentException(
                raw.getName() + " does not implement " + contract.getName());
    }

    Class<? extends S> implementation = raw.asSubclass(contract);
    return implementation.getDeclaredConstructor().newInstance();
}
~~~

Giải thích từng bước:

1. `Class.forName(className)` nạp/lấy token lớp theo tên đầy đủ; ở overload một tham số, việc khởi tạo class có thể diễn ra. Không nên nạp tùy ý tên lớp từ đầu vào không tin cậy.
2. `contract.isAssignableFrom(raw)` kiểm tra khả năng đáp ứng contract; sai thì trả lỗi nghiệp vụ rõ ràng.
3. `raw.asSubclass(contract)` đưa quan hệ đã kiểm tra vào **kiểu tĩnh** `Class<? extends S>`, thuận tiện cho reflection API.
4. `getDeclaredConstructor().newInstance()` gọi constructor không tham số rồi trả object thuộc `S`. Phải bảo đảm class cụ thể, constructor tồn tại và có thể truy cập; nếu không, reflection có thể ném `NoSuchMethodException`, `InstantiationException`, `IllegalAccessException` hoặc `InvocationTargetException`.

Một nơi khác có thể nhận object từ framework hoặc reflection rồi áp contract:

~~~java
Object value = /* kết quả từ framework */ null;
Task task = Task.class.cast(value); // Có thể trả null; kiểm tra null nếu contract cấm.
~~~

`cast` **không bảo đảm non-null**. Nếu kết quả có thể trống, phải kiểm tra `null` theo yêu cầu nghiệp vụ. Trong factory ở trên, constructor thành công sẽ trả một object; việc lớp đó có hành vi an toàn/hợp lệ hay không vẫn là trách nhiệm riêng của ứng dụng.

## 7. Giới hạn và các lỗi phổ biến

**Sai chiều của `isAssignableFrom`.** Khi lọc class triển khai `Task`, viết `Task.class.isAssignableFrom(candidate)`. Viết ngược `candidate.isAssignableFrom(Task.class)` thường lọc nhầm hoặc bỏ mất subtype cần chọn.

**Đồng nhất `Class` với instance.** `Task.class.isAssignableFrom(EmailTask.class)` so hai kiểu; `Task.class.isInstance(object)` kiểm tra instance và trả boolean; `Task.class.cast(object)` kiểm tra instance và trả tham chiếu kiểu `Task` hoặc ném lỗi; `EmailTask.class.asSubclass(Task.class)` kiểm tra token và trả token có generic hẹp hơn. Không thay thế lẫn nhau tùy tiện.

**Tưởng `cast` sẽ chuyển giá trị.** `String.class.cast(123)` không biến `123` thành `"123"`. Dùng API chuyển đổi giá trị như `String.valueOf` hoặc parse phù hợp khi yêu cầu là chuyển đổi dữ liệu.

**Tưởng phương thức xác nhận generic parameter.** Vì type erasure, `List.class.isAssignableFrom(ArrayList.class)` chỉ xác nhận quan hệ kiểu raw; không chứng minh phần tử là `String` hay `Integer`. Không có literal `List<String>.class` trong Java. Muốn kiểm tra kiểu phần tử, cần kiểm tra nội dung hoặc đọc metadata generic phù hợp (`ParameterizedType`) khi metadata đó thật sự hiện diện.

**Nhầm primitive với wrapper.** `Integer.class` khác `int.class`; `Integer.class.isAssignableFrom(int.class)` là `false`. Cả widening primitive lẫn boxing/unboxing đều không được `isAssignableFrom` áp dụng. `Class.cast` cũng không chuyển object thành primitive.

**Bỏ qua class loader.** Hai class có cùng tên đầy đủ nhưng do hai defining class loader khác nhau định nghĩa vẫn có thể là hai runtime type khác nhau. Vì vậy tên khớp không đủ để `isAssignableFrom`, `cast` hoặc `asSubclass` thành công; hệ thống plugin phải chú ý cách chia sẻ contract interface giữa các loader.

**Cho rằng tương thích kiểu đồng nghĩa có thể khởi tạo.** `asSubclass` không kiểm tra class có `abstract` hay interface, constructor phù hợp, accessibility, exception từ constructor hoặc side effect khi class loading. `Class.newInstance()` đã deprecated; ưu tiên `getDeclaredConstructor().newInstance()` khi cần reflection construction.

**Truyền null thiếu suy xét.** `isAssignableFrom(null)` và `asSubclass(null)` ném `NullPointerException`, còn `cast(null)` trả `null`. Khi thiết kế API, nên xác định rõ đầu vào nào được chấp nhận.

## 8. Chọn phương thức theo tình huống

- Có **hai `Class`**, chỉ cần quyết định chấp nhận subtype hay không → `target.isAssignableFrom(candidate)`.
- Có **một object**, cần giá trị typed và chấp nhận exception nếu sai → `target.cast(object)`.
- Có **một object**, chỉ muốn thử trước rồi rẽ nhánh → `target.isInstance(object)`.
- Có **`Class<?>`** từ reflection, cần chuyển thành **`Class<? extends Contract>`** để đưa cho API hoặc lấy typed constructor → `candidate.asSubclass(Contract.class)`.

Một chuỗi thường dùng trong runtime extensibility là: **nạp token `Class<?>` → kiểm tra `Contract.class.isAssignableFrom(raw)` → thu hẹp bằng `raw.asSubclass(Contract.class)` → khởi tạo qua constructor → dùng giá trị như `Contract`**. Nếu đối tượng xuất phát từ nguồn khác, có thể dùng `Contract.class.cast(value)` để kiểm tra ngay tại ranh giới nhận object.

Tài liệu chuẩn: [Java SE 21 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html), mục `isAssignableFrom`, `cast`, `asSubclass` và `isInstance`.