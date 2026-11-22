# Đọc giá trị mặc định của annotation bằng `Method.getDefaultValue()` trong Java

## 1. Giá trị mặc định của một phần tử annotation là gì?

Trong Java, annotation được khai báo bằng `@interface`. Các phần tử của annotation trông giống những phương thức không có tham số. Mỗi phần tử có thể **khai báo giá trị mặc định** bằng từ khóa `default`:

~~~java
@interface JobOptions {
    String owner() default "platform";
    int retries() default 3;
    boolean enabled();
}
~~~

Có ba phần tử:

- `owner()`: mặc định là `"platform"`.
- `retries()`: mặc định là `3`.
- `enabled()`: **không có mặc định**, vì vậy nơi sử dụng annotation phải cung cấp giá trị.

Ví dụ:

~~~java
@JobOptions(enabled = true)
class Worker {
}
~~~

Lúc Java phân tích annotation trên `Worker`, các phần tử `owner` và `retries` nhận giá trị mặc định, còn `enabled` có giá trị đã được truyền là `true`.

Nếu mục tiêu chỉ là **biết annotation thực tế trên class có giá trị gì**, ta thường gọi phương thức phần tử trên đối tượng annotation, chẳng hạn `options.owner()`. Nhưng nếu muốn **kiểm tra chính annotation type đã khai báo mặc định nào**, Java Reflection cung cấp:

~~~java
java.lang.reflect.Method.getDefaultValue()
~~~

Đây là trọng tâm của bài: **`Method.getDefaultValue()` đọc giá trị `default` được khai báo trong định nghĩa của phần tử annotation**, chứ không phải giá trị được truyền tại một nơi sử dụng cụ thể.

## 2. Chữ ký và hợp đồng của `Method.getDefaultValue()`

Theo Java SE 17, phương thức thuộc `java.lang.reflect.Method` có chữ ký:

~~~java
public Object getDefaultValue()
~~~

Ý nghĩa:

1. Nếu `Method` đại diện cho **một phần tử trong annotation type có khai báo `default`**, nó trả về giá trị mặc định đó.
2. Nếu phần tử annotation **không khai báo `default`**, nó trả về `null`.
3. Nếu `Method` **không đại diện phần tử annotation** (ví dụ phương thức thông thường của class), nó cũng trả về `null`.
4. Kiểu trả về tĩnh là `Object` vì các phần tử annotation có thể mang nhiều kiểu Java hợp lệ. Đối tượng thực tế có thể là một wrapper của kiểu nguyên thủy, `String`, `Class`, giá trị enum, annotation lồng nhau hoặc một mảng giá trị.

Quan trọng: `null` ở đây là **tín hiệu không có giá trị mặc định**, không phải một giá trị mặc định `null`. Java không cho khai báo `default null` trong một annotation element.

Để gọi `getDefaultValue()`, trước hết cần lấy `Method` của **annotation type**:

~~~java
Method method = JobOptions.class.getDeclaredMethod("retries");
Object defaultValue = method.getDefaultValue();
~~~

Đoạn này **chỉ là fragment minh họa**, cần khai báo `JobOptions` và import `java.lang.reflect.Method`; `getDeclaredMethod` có thể ném `NoSuchMethodException`.

Trong ví dụ trên `defaultValue` biểu diễn số nguyên `3` dưới dạng `Integer`, do `Method.getDefaultValue()` trả về `Object`. Nếu `JobOptions.class.getDeclaredMethod("enabled").getDefaultValue()` được gọi, kết quả là `null` vì `enabled` không có `default`.

## 3. Phân biệt ba khái niệm rất dễ nhầm

| Điều cần biết | Cách đọc phù hợp | Ví dụ kết quả |
| --- | --- | --- |
| Kiểu annotation có khai báo `default` nào cho `retries()`? | `JobOptions.class.getDeclaredMethod("retries").getDefaultValue()` | `3` |
| Annotation gắn trên `Worker` có giá trị `retries` thực tế bằng bao nhiêu? | `Worker.class.getAnnotation(JobOptions.class).retries()` | `3` hoặc giá trị được ghi đè |
| Có thực sự gắn `@JobOptions` lên `Worker` không? | `Worker.class.isAnnotationPresent(JobOptions.class)` | `true` nếu runtime có thể thấy annotation |

Giả sử nơi sử dụng ghi:

~~~java
@JobOptions(enabled = true, retries = 8)
class CustomWorker {
}
~~~

Khi đó:

- `JobOptions.class.getDeclaredMethod("retries").getDefaultValue()` **vẫn là `3`**, vì mặc định khai báo ở annotation type không đổi.
- `CustomWorker.class.getAnnotation(JobOptions.class).retries()` là **`8`**, vì đây là giá trị hiệu lực tại nơi sử dụng.
- `owner()` của annotation trên `CustomWorker` là `"platform"` vì không ghi đè.
- `enabled()` bằng `true`, mặc dù `JobOptions.class.getDeclaredMethod("enabled").getDefaultValue()` là `null`.

Vậy hai phép đọc trả lời **hai câu hỏi khác nhau**. `getDefaultValue()` đọc **định nghĩa**, còn việc gọi element method trên annotation object đọc **giá trị hiệu lực** (*effective value*) tại một vị trí cụ thể.

## 4. Chương trình Java 17 hoàn chỉnh: in cả mặc định và giá trị hiệu lực

Tạo duy nhất tệp **`DefaultValueDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

enum Level {
    LOW, HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface JobOptions {
    String owner() default "platform";
    int retries() default 3;
    Level level() default Level.HIGH;
    Class<?> type() default String.class;
    String[] tags() default {"java", "reflection"};
    boolean enabled();
}

@JobOptions(enabled = true, retries = 8)
class Worker {
}

public class DefaultValueDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Method[] elements = JobOptions.class.getDeclaredMethods();
        Arrays.sort(elements, Comparator.comparing(Method::getName));

        JobOptions options = Worker.class.getAnnotation(JobOptions.class);

        for (Method element : elements) {
            Object declaredDefault = element.getDefaultValue();
            Object effective = element.invoke(options);

            System.out.println(element.getName()
                    + " | default=" + format(declaredDefault)
                    + " | effective=" + format(effective));
        }
    }

    private static String format(Object value) {
        if (value == null) {
            return "<none>";
        }
        if (value instanceof String[] texts) {
            return Arrays.toString(texts);
        }
        if (value instanceof Class<?> type) {
            return type.getSimpleName() + ".class";
        }
        return String.valueOf(value);
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac -encoding UTF-8 DefaultValueDemo.java
java DefaultValueDemo
~~~

**Stdout chính xác:**

~~~text
enabled | default=<none> | effective=true
level | default=HIGH | effective=HIGH
owner | default=platform | effective=platform
retries | default=3 | effective=8
tags | default=[java, reflection] | effective=[java, reflection]
type | default=String.class | effective=String.class
~~~

### Vì sao kết quả có thứ tự này?

`Class.getDeclaredMethods()` **không cam kết thứ tự** của các phương thức trả về. Ví dụ dùng:

~~~java
Arrays.sort(elements, Comparator.comparing(Method::getName));
~~~

để sắp xếp theo tên phần tử, giúp stdout luôn có thứ tự `enabled`, `level`, `owner`, `retries`, `tags`, `type`. Nếu bỏ dòng sắp xếp, không nên viết test dựa vào thứ tự các phương thức mà reflection trả về.

### Vì sao `retries` có hai giá trị khác nhau?

Định nghĩa của `JobOptions` chứa `int retries() default 3;`. Nhưng `Worker` dùng `@JobOptions(enabled = true, retries = 8)`.

Do đó:

- `element.getDefaultValue()` trả về `Integer(3)`.
- `element.invoke(options)` gọi phần tử `retries()` trên **annotation instance của `Worker`**, trả về `Integer(8)`.

Với `owner`, nơi sử dụng không truyền giá trị nên cả hai đều là `"platform"`.

Với `enabled`, không có `default` nên `getDefaultValue()` trả `null`, nhưng Java vẫn yêu cầu khai báo `enabled = true` ở nơi sử dụng; vì vậy `element.invoke(options)` trả `true`.

### Vì sao cần `@Retention(RUNTIME)` trong ví dụ?

Chương trình đọc annotation trên class `Worker` bằng:

~~~java
JobOptions options = Worker.class.getAnnotation(JobOptions.class);
~~~

Câu lệnh này cần metadata của **lần sử dụng annotation** tồn tại ở runtime. Do vậy ví dụ gắn `@Retention(RetentionPolicy.RUNTIME)` lên `JobOptions`.

Tuy nhiên, chỉ riêng `JobOptions.class.getDeclaredMethod("owner").getDefaultValue()` đọc **mặc định từ định nghĩa annotation type**, không phải từ `Worker`. Giá trị `default` được biểu diễn trong class file của annotation type (thuộc tính `AnnotationDefault`) và có thể truy xuất nếu annotation type được nạp hợp lệ, ngay cả khi `@Retention` của annotation đó là `SOURCE` hoặc `CLASS`. Không nên suy rằng `getDefaultValue()` cần `RUNTIME`; **việc đọc annotation đang gắn trên một class** mới là lý do ví dụ sử dụng `RUNTIME`.

## 5. Những kiểu giá trị mặc định được phép trả về

Các phần tử annotation có giới hạn kiểu trả về theo ngôn ngữ Java. Các kiểu hợp lệ gồm:

- Kiểu nguyên thủy: `byte`, `short`, `int`, `long`, `char`, `float`, `double`, `boolean`.
- `String`.
- `Class` hoặc một dạng tham số hóa hợp lệ của `Class`, chẳng hạn `Class<?>`.
- Một **enum type**.
- Một **annotation type**.
- Mảng một chiều của các kiểu được phép ở trên.

Không được dùng `Object`, `List<String>`, `Map<...>`, mảng nhiều chiều hay kiểu đối tượng tùy ý làm kiểu phần tử annotation.

Bảng minh họa cách `getDefaultValue()` biểu diễn dữ liệu:

| Khai báo phần tử | Giá trị trả về khi gọi `getDefaultValue()` |
| --- | --- |
| `int count() default 5;` | `Integer` mang giá trị `5` |
| `boolean active() default true;` | `Boolean.TRUE` |
| `String label() default "main";` | Chuỗi `"main"` |
| `Class<?> type() default String.class;` | `Class` tương ứng `String.class` |
| `Level level() default Level.HIGH;` | Hằng enum `Level.HIGH` |
| `String[] names() default {"a", "b"};` | Mảng `String[]` có hai phần tử |
| `String required();` | `null` vì không có mặc định |

Trong bảng, `Level` giả định là enum đã khai báo như ở chương trình chạy.

### Với annotation lồng nhau

Một annotation có thể chứa annotation khác làm giá trị phần tử:

~~~java
@interface Nested {
    String code() default "ok";
}

@interface Outer {
    Nested nested() default @Nested;
}
~~~

Đây là hai định nghĩa annotation hợp lệ. Nếu gọi:

~~~java
Object value = Outer.class
        .getDeclaredMethod("nested")
        .getDefaultValue();
~~~

`value` là một đối tượng thể hiện annotation type `Nested`. Có thể kiểm tra và đọc phần tử:

~~~java
Nested nested = (Nested) value;
System.out.println(nested.code());
~~~

Đoạn minh họa trên cần nằm trong phương thức có thể ném hoặc xử lý `NoSuchMethodException`; kết quả in sẽ là:

~~~text
ok
~~~

Mặc định của `Nested.code()` được áp dụng vì `@Nested` trong định nghĩa `Outer` không truyền `code`.

### Với mảng

Nếu phần tử mặc định là mảng, `getDefaultValue()` trả về một **đối tượng mảng**, không phải chuỗi dạng `"[java, reflection]"`. Trong ví dụ `DefaultValueDemo`, ta chủ động gọi `Arrays.toString(texts)` để in mảng đẹp và có thể kiểm tra từng phần tử.

Cách in trực tiếp `System.out.println(element.getDefaultValue())` với một mảng sẽ sử dụng `Object.toString()` của mảng, thường cho một chuỗi dạng `[Ljava.lang.String;@...` chứ không in các phần tử. Vì vậy khi viết bài test hoặc công cụ audit mặc định annotation, cần xử lý mảng riêng (các kiểu mảng nguyên thủy khác nhau cần những overload `Arrays.toString` tương ứng).

## 6. Reflection đọc định nghĩa mặc định như thế nào?

Ở mức bytecode, giá trị mặc định của một phần tử annotation nằm trong metadata của **annotation type**, không phải chỉ ở nơi sử dụng.

Ví dụ `JobOptions.class` chứa khai báo method `retries()` và thông tin mặc định `3`. Nếu muốn quan sát bytecode do `javac` sinh ra, sau khi chạy chương trình ở phần 4, dùng:

~~~bash
javap -v JobOptions
~~~

Trong output chi tiết của `javap`, có thể tìm thuộc tính **`AnnotationDefault`** tương ứng với các phần tử có `default`. Những phần tử bắt buộc như `enabled()` không có giá trị mặc định như vậy. `javap` không phải nguồn thay thế cho hợp đồng Java Reflection, nhưng rất hữu ích để hiểu dữ liệu `getDefaultValue()` truy xuất.

Chính điểm lưu trữ này giải thích vì sao:

- Một class sử dụng annotation có thể bỏ qua một phần tử có `default`.
- Khi runtime đọc annotation, Java cung cấp giá trị mặc định cho phần tử bị bỏ qua.
- Reflection có thể xem định nghĩa mặc định bằng `Method.getDefaultValue()` mà **không cần trước đó lấy annotation từ một class cụ thể**.

Đặc biệt: không có cách chính thức tổng quát để dùng **chỉ đối tượng annotation đã đọc bằng Reflection** mà biết liệu người viết source đã ghi tường minh một giá trị **bằng mặc định** hay đã bỏ qua phần tử để dùng default. Chẳng hạn:

~~~java
@JobOptions(enabled = true)
class A {
}

@JobOptions(enabled = true, retries = 3)
class B {
}
~~~

Ở hai nơi sử dụng này, `retries()` đều trả `3`. Dựa vào giá trị hiệu lực và giá trị mặc định không đủ để kết luận source ban đầu có viết `retries = 3` hay không. Nếu yêu cầu phân tích chính xác cú pháp trong source, cần công cụ phân tích mã nguồn/annotation processing có khả năng giữ thông tin tường minh, thay vì suy đoán từ reflection runtime.

## 7. Khi nào nên dùng `getDefaultValue()`?

Đây là API có ích khi xây dựng **công cụ làm việc với annotation type**, chứ không chỉ đọc các annotation instance trong chương trình:

1. **Sinh tài liệu cấu hình:** duyệt các phần tử của annotation, liệt kê tên, kiểu và giá trị mặc định của từng tùy chọn.
2. **Kiểm tra hợp đồng thư viện:** phát hiện phần tử nào bắt buộc và phần tử nào có mặc định để đưa ra thông báo hướng dẫn.
3. **Tạo UI cấu hình hoặc metadata explorer:** hiển thị default mà API định nghĩa, không cần có một class đã sử dụng annotation.
4. **So sánh định nghĩa giữa hai phiên bản thư viện:** xem phần tử nào đổi mặc định, qua đó đánh giá thay đổi hành vi của client.
5. **Debug framework:** xác định liệu một giá trị hiệu lực đến từ mặc định của annotation type hay có thể đã được chỉ định trực tiếp (lưu ý không thể luôn phân biệt nguồn gốc chỉ bằng reflection).

Ví dụ một công cụ liệt kê tên các phần tử bắt buộc:

~~~java
for (Method element : JobOptions.class.getDeclaredMethods()) {
    if (element.getDefaultValue() == null) {
        System.out.println("Required: " + element.getName());
    }
}
~~~

Đây là **fragment** dùng khai báo `JobOptions` trong chương trình ở phần 4. Output ở ví dụ đó là:

~~~text
Required: enabled
~~~

Trong một annotation interface, các phương thức khai báo tường minh là các phần tử annotation; mỗi phần tử phải có tên và kiểu trả về hợp lệ, không có tham số. Vì vậy `getDeclaredMethods()` phù hợp để duyệt các phần tử của kiểu annotation được định nghĩa trực tiếp.

Nên tránh viết thư viện quét không kiểm tra kiểu đầu vào. Với một `Class<?> type` bất kỳ, có thể kiểm tra:

~~~java
if (!type.isAnnotation()) {
    throw new IllegalArgumentException("Not an annotation type");
}
~~~

Rồi mới duyệt các element methods. `Method.getDefaultValue()` cũng là API hợp lệ trên `Method` thông thường, nhưng lúc đó kết quả `null` không có nghĩa “phương thức thường là phần tử bắt buộc của annotation”.

## 8. Các giới hạn và lỗi có thể gặp

### 8.1. Không có mặc định thì trả `null`

Trong annotation type:

~~~java
@interface Connection {
    String url();
    int timeout() default 30;
}
~~~

`url()` là phần tử bắt buộc; `timeout()` có default bằng `30`. `getDefaultValue()` trả `null` cho `url()`, và `Integer(30)` cho `timeout()`. Java không cho `default null`, nên trường hợp `null` không mơ hồ với một default hợp lệ.

### 8.2. Không đọc giá trị ghi đè bằng `getDefaultValue()`

`@JobOptions(enabled = true, retries = 8)` không làm `JobOptions.class.getDeclaredMethod("retries").getDefaultValue()` đổi từ `3` thành `8`. Muốn đọc `8`, phải lấy annotation instance tại vị trí được gắn và gọi `retries()`, hoặc invoke method tương ứng trên instance như phần 4.

### 8.3. Tránh nhầm `default` của annotation với `default` của interface method

Phần tử annotation được định nghĩa:

~~~java
@interface Settings {
    int retries() default 3;
}
~~~

Còn `default` method của interface thông thường:

~~~java
interface Retrier {
    default int retries() {
        return 3;
    }
}
~~~

Hai cú pháp có nghĩa khác nhau. Với `Retrier.class.getDeclaredMethod("retries")`, `getDefaultValue()` trả về **`null`**, vì `Retrier.retries()` không phải phần tử của annotation type. Để biết đây là default method của interface, Reflection có phương thức **`Method.isDefault()`**, một API hoàn toàn khác.

### 8.4. Đừng dùng `getMethods()` rồi coi mọi phương thức là phần tử annotation

`getMethods()` bao gồm những public method được kế thừa từ các interface/class liên quan theo quy tắc reflection. Đối với một annotation type, cách dễ hiểu để duyệt phần tử khai báo của chính annotation type là `getDeclaredMethods()` rồi chỉ xử lý các method đó. Các phương thức như `annotationType()`, `equals()`, `hashCode()`, `toString()` thuộc hợp đồng `java.lang.annotation.Annotation` hoặc `Object`, **không phải** các annotation elements do ta khai báo.

### 8.5. Chú ý kiểu trả về `Object` và ép kiểu

Mã dưới đây không biên dịch vì `Object` không thể gán thẳng cho `int`:

~~~java
// Sai:
// int retries = JobOptions.class.getDeclaredMethod("retries").getDefaultValue();
~~~

Cách đúng khi biết chắc kiểu phần tử:

~~~java
Object raw = JobOptions.class
        .getDeclaredMethod("retries")
        .getDefaultValue();

int retries = (Integer) raw;
~~~

Đây là fragment cần đặt trong ngữ cảnh xử lý/khai báo `NoSuchMethodException`. Ép kiểu `(Integer)` phù hợp vì phần tử `retries()` được khai báo trả `int`, và giá trị phản chiếu của số nguyên là `Integer`. Với công cụ tổng quát, phải xem `Method.getReturnType()` và xử lý đúng kiểu thay vì ép mọi default thành `String`.

### 8.6. Một default có thể gây lỗi khi giải mã kiểu không còn tồn tại

API Java SE 17 của `Method.getDefaultValue()` có thể phát sinh:

- `TypeNotPresentException` nếu một giá trị mặc định tham chiếu tới một kiểu không khả dụng.
- `EnumConstantNotPresentException` nếu giá trị enum được khai báo trong default không tồn tại khi đọc.
- `AnnotationFormatError` nếu metadata mặc định gặp định dạng không hợp lệ.

Các tình huống này hay xuất hiện khi các lớp được biên dịch từ phiên bản thư viện không nhất quán, hoặc classpath/module path thiếu thành phần. Khi viết công cụ quét bytecode của nhiều artifact, không nên mặc định mọi giá trị trong annotation metadata đều luôn giải mã thành công.

### 8.7. Thay đổi giá trị default giữa các phiên bản có thể đổi hành vi

Giả sử phiên bản 1 khai báo:

~~~java
@interface RetryPolicy {
    int attempts() default 2;
}
~~~

và một client đã biên dịch dùng `@RetryPolicy` mà không chỉ định `attempts`. Nếu trong phiên bản 2 cùng annotation type đổi mặc định thành `4`, mã đọc metadata trong môi trường phiên bản 2 có thể nhận `4` mà không sửa source của client. **Giá trị mặc định là một phần hợp đồng có thể quan sát được**, không phải chỉ là ví dụ trong tài liệu.

Đây là lý do nên xem việc đổi `default` như một thay đổi **hành vi/semantics** của API, kể cả khi các khai báo sử dụng annotation cũ vẫn biên dịch và liên kết được. Cần chạy lại kiểm thử các công cụ/framework sử dụng giá trị đó.

## 9. Checklist khi viết bộ đọc mặc định annotation

Một quy trình thực tế:

1. Lấy chính annotation type, ví dụ `JobOptions.class`, và xác nhận `isAnnotation()` nếu đầu vào động.
2. Gọi `getDeclaredMethods()` để duyệt các element methods được khai báo trong annotation type đó.
3. Nếu cần kết quả ổn định, sắp xếp theo `Method.getName()`.
4. Với mỗi method, gọi `getDefaultValue()`; `null` nghĩa là phần tử không có default.
5. Kiểm tra `Method.getReturnType()` và trình bày giá trị phù hợp, đặc biệt với enum, `Class`, annotation lồng nhau và mảng.
6. Nếu muốn biết **giá trị hiệu lực tại nơi sử dụng**, lấy annotation instance bằng reflection với retention thích hợp, rồi gọi method phần tử trên instance.
7. Phân biệt `null` do không có default với lỗi decode metadata, thiếu class hoặc annotation không được giữ đến runtime.
8. Không kết luận chắc chắn một phần tử đã được ghi tường minh hay đã dùng default nếu chỉ dựa vào effective value từ runtime.

## 10. Câu hỏi tự kiểm tra và bài tập

**Câu 1.** `String owner() default "platform";` thì `Method.getDefaultValue()` trả về gì?

**Đáp án:** Một `String` có giá trị `"platform"`.

**Câu 2.** `boolean enabled();` không có `default`; vì sao `getDefaultValue()` là `null` nhưng `@JobOptions(enabled = true)` vẫn có thể trả `true` khi gọi `enabled()`?

**Đáp án:** Phần tử không có mặc định nên buộc nơi sử dụng truyền giá trị. `getDefaultValue()` đọc định nghĩa; `enabled()` trên annotation instance đọc giá trị hiệu lực.

**Câu 3.** Đổi `@JobOptions(enabled = true, retries = 8)` thành `@JobOptions(enabled = true, retries = 3)`. Có xác định được bằng reflection runtime rằng người viết source đã truyền `retries = 3` hay không?

**Đáp án:** Không thể kết luận một cách tổng quát chỉ từ effective value và declared default vì giá trị truyền tường minh bằng giá trị mặc định.

**Câu 4.** Có cần `@Retention(RUNTIME)` chỉ để gọi `JobOptions.class.getDeclaredMethod("owner").getDefaultValue()` không?

**Đáp án:** Không. Giá trị default thuộc định nghĩa annotation type. `RUNTIME` cần thiết khi muốn dùng runtime reflection để đọc `@JobOptions` đã gắn trên class như `Worker`.

**Câu 5.** Vì sao mã in `String[]` mặc định nên dùng `Arrays.toString` thay vì `String.valueOf`?

**Đáp án:** Vì mảng không override `toString()` để in danh sách phần tử. `Arrays.toString` biểu diễn nội dung mảng dễ đọc hơn.

**Câu 6.** `Method.isDefault()` và `Method.getDefaultValue()` có cùng ý nghĩa không?

**Đáp án:** Không. `isDefault()` nói tới default method của interface thông thường; `getDefaultValue()` trả về giá trị mặc định được khai báo cho annotation element.

**Bài thực hành:** Trong `DefaultValueDemo.java`, hãy bổ sung phần tử `long ttl() default 60L;` vào `JobOptions` rồi chạy lại. Dự đoán vị trí dòng mới sau sắp xếp theo tên, kiểu Java của kết quả `getDefaultValue()`, và giá trị hiệu lực khi `Worker` không chỉ định `ttl`. Sau đó thêm `ttl = 120L` ở nơi sử dụng để quan sát declared default **giữ nguyên** còn effective value **thay đổi**.

## 11. Tài liệu chuẩn

- [Java SE 17 — `java.lang.reflect.Method.getDefaultValue()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue()): chữ ký, giá trị trả về và các ngoại lệ liên quan.
- [Java SE 17 — `java.lang.reflect.Method.isDefault()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#isDefault()): phân biệt với default method của interface.
- [JLS Java SE 17 §9.6.2 — Defaults for Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2): quy tắc khai báo giá trị mặc định.
- [Java SE 17 — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): API đọc annotation đã gắn trên các phần tử chương trình.

Hãy ghi nhớ phân biệt quan trọng nhất: **`Method.getDefaultValue()` hỏi annotation type quy định mặc định gì; `element.invoke(annotationInstance)` hỏi annotation đang dùng thực sự có giá trị gì**. Hai phép đọc có thể trùng hoặc khác nhau tùy nơi sử dụng có ghi đè default hay không.