# Đọc giá trị phần tử annotation qua phương thức của annotation type

## 1. Annotation element là phương thức không tham số

Trong Java, annotation type được khai báo bằng `@interface`. Bên trong có thể khai báo các **annotation elements** dưới dạng phương thức **không có tham số**, trả về kiểu được ngôn ngữ cho phép. Ví dụ:

~~~java
@interface Route {
    String value();
    int priority() default 1;
}
~~~

`value()` và `priority()` không phải các field public cũng không phải những phương thức nghiệp vụ có thân hàm. Chúng là các **element declaration** của annotation type. Khi một class hay method được gắn annotation:

~~~java
@Route(value = "/orders", priority = 5)
class OrderEndpoint {
}
~~~

Java lưu các cặp tên–giá trị annotation thích hợp trong metadata của phần tử được đánh dấu. Nếu annotation có **`RetentionPolicy.RUNTIME`**, Reflection có thể đọc một instance annotation và gọi **phương thức element của annotation đó** để lấy giá trị:

~~~java
Route route = OrderEndpoint.class.getAnnotation(Route.class);
if (route != null) {
    System.out.println(route.value());    // /orders
    System.out.println(route.priority()); // 5
}
~~~

Các mảnh ví dụ này giải thích nguyên lý; chương trình Java 17 hoàn chỉnh ở phần 4 có khai báo import, retention và tất cả kiểu liên quan.

Điểm cốt lõi: **Đọc giá trị annotation là gọi element method trên annotation instance**. Không cần tìm một field có cùng tên, không dùng `Field.get`, và bản thân thao tác đọc metadata **không thực hiện nghiệp vụ** được mô tả bởi annotation.

## 2. Hai đối tượng cần phân biệt: annotation type và annotation instance

Giả sử có `@Rule("checkout")` gắn trên `Checkout.class`:

- **Annotation type** là `Rule.class`. Nó là đối tượng `Class<Rule>` đại diện định nghĩa `@interface Rule`, chứa các element method khai báo như `String value()` và `int retries() default 3`.
- **Annotation instance** là giá trị `Rule rule = Checkout.class.getAnnotation(Rule.class)`, đại diện thông tin annotation gắn trên lớp `Checkout`. Nó triển khai interface annotation và cung cấp giá trị của các element.
- **Đối tượng được annotation đánh dấu** là `Checkout.class`, không phải `rule`. Metadata thuộc về phần tử được gắn annotation (class, method, field, parameter, ...).

Luồng xử lý thường gặp:

~~~text
Định nghĩa @interface Rule
       |
       v
Dùng @Rule(...) trên một phần tử
       |
       v
Class file có annotation metadata (nếu retention cho phép)
       |
       v
Reflection: element.getAnnotation(Rule.class)
       |
       v
Rule annotation = ...
       |
       +-- annotation.value()
       +-- annotation.retries()
       +-- annotation.tags()
       +-- annotation.owner().name()
~~~

**Sai lầm hay gặp:** viết `Rule.class.getDeclaredMethod("retries")` rồi nghĩ chỉ có object `Method` đã chứa giá trị `5` của annotation trên `Checkout`. Thực tế `Method` đó là mô tả **element method** dùng chung cho cả annotation type. Muốn đọc **giá trị tại nơi sử dụng cụ thể**, phải gọi method trên đúng **annotation instance**. `Method.getDefaultValue()` lại là một API khác: nó mô tả **giá trị mặc định đã khai báo ở annotation type**, không phải giá trị override tại một nơi sử dụng.

## 3. Những kiểu trả về hợp lệ của annotation element

Một annotation element chỉ có thể trả về một trong những loại sau:

1. Kiểu primitive: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`.
2. `String`.
3. `Class` (kể cả các dạng `Class<?>` được ngôn ngữ cho phép).
4. Một kiểu `enum`.
5. Một kiểu annotation khác (nested annotation value).
6. Mảng **một chiều** của một trong các loại trên.

Bảng ví dụ:

| Khai báo element | Cách dùng tại annotation | Kiểu nhận được khi đọc |
| --- | --- | --- |
| `String value();` | `@Rule("checkout")` | `String` |
| `int retries() default 3;` | `@Rule(retries = 5, ...)` | `int` |
| `boolean enabled() default true;` | `enabled = false` | `boolean` |
| `Level level() default Level.LOW;` | `level = Level.HIGH` | `Level` |
| `Class<?> handler() default String.class;` | `handler = Integer.class` | `Class<?>` |
| `String[] tags() default {};` | `tags = {"fast", "safe"}` | `String[]` |
| `Owner owner() default @Owner(name = "system");` | `owner = @Owner(name = "core")` | `Owner` |

Java không chấp nhận một annotation element trả về `List<String>`, `Map`, `Object`, mảng nhiều chiều hay kiểu được phép khác dưới dạng tổng quát không hợp lệ. Thay vì trả `List<String>`, khai báo `String[]` và chuyển sang collection trong code ứng dụng nếu cần.

Ngoài ra, **`null` không phải giá trị annotation element hợp lệ**. Element bắt buộc được chỉ rõ tại nơi sử dụng nếu không có default, hoặc lấy default khi bỏ qua. Với element dạng `String[]`, mảng rỗng `{}` khác với `null`. Element method không khai báo tham số hay `throws` clause, và không có thân thực thi như method thông thường.

## 4. Ví dụ Java 17 hoàn chỉnh

Tạo file **`AnnotationElementsDemo.java`**. Chương trình định nghĩa annotation với nhiều loại element, gắn một annotation có giá trị tường minh và một annotation dùng default, rồi đọc bằng phương thức của annotation type.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

enum Level {
    LOW, HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@interface Owner {
    String name();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Rule {
    String value();
    int retries() default 3;
    Level level() default Level.LOW;
    Class<?> handler() default String.class;
    String[] tags() default {};
    Owner owner() default @Owner(name = "system");
}

@Rule(
        value = "checkout",
        retries = 5,
        level = Level.HIGH,
        handler = Integer.class,
        tags = {"fast", "safe"},
        owner = @Owner(name = "core"))
class Checkout {
}

@Rule("fallback")
class Fallback {
}

public class AnnotationElementsDemo {
    public static void main(String[] args) throws Exception {
        Rule rule = Checkout.class.getAnnotation(Rule.class);

        System.out.println("present=" + (rule != null));
        System.out.println("annotationType="
                + rule.annotationType().getSimpleName());
        System.out.println("value=" + rule.value());
        System.out.println("retries=" + rule.retries());
        System.out.println("level=" + rule.level());
        System.out.println("handler=" + rule.handler().getSimpleName());
        System.out.println("tags=" + Arrays.toString(rule.tags()));
        System.out.println("owner=" + rule.owner().name());

        Rule fallback = Fallback.class.getAnnotation(Rule.class);
        System.out.println("fallback-retries=" + fallback.retries());
        System.out.println("fallback-level=" + fallback.level());
        System.out.println("fallback-handler="
                + fallback.handler().getSimpleName());
        System.out.println("fallback-tags="
                + Arrays.toString(fallback.tags()));
        System.out.println("fallback-owner=" + fallback.owner().name());

        Method retriesMethod = Rule.class.getDeclaredMethod("retries");
        System.out.println("reflective-retries="
                + retriesMethod.invoke(rule));
        System.out.println("declared-default="
                + retriesMethod.getDefaultValue());

        System.out.println("missing="
                + (String.class.getAnnotation(Rule.class) == null));
    }
}
~~~

Biên dịch/chạy từ thư mục chứa file:

~~~bash
javac --release 17 AnnotationElementsDemo.java
java AnnotationElementsDemo
~~~

Output:

~~~text
present=true
annotationType=Rule
value=checkout
retries=5
level=HIGH
handler=Integer
tags=[fast, safe]
owner=core
fallback-retries=3
fallback-level=LOW
fallback-handler=String
fallback-tags=[]
fallback-owner=system
reflective-retries=5
declared-default=3
missing=true
~~~

Hành vi của ví dụ đã được xác minh qua Java Compiler ở mức Java 17 và chạy thử logic tương đương trong JShell. Bài dùng các annotation ở package mặc định để không cần file `module-info.java`; trong dự án thực tế nên khai báo package rõ ràng.

### Phân tích output

1. `@Retention(RUNTIME)` trên `Rule` khiến `Checkout.class.getAnnotation(Rule.class)` có thể lấy annotation được khai báo, nên `rule != null` là `true`. `annotationType()` trả `Rule.class`.
2. `rule.value()` là `"checkout"`, chính giá trị ghi trong `@Rule(value = "checkout", ...)`. `rule.retries()` trả primitive `int` bằng 5, không lấy default 3 vì annotation tại `Checkout` có ghi đè.
3. `rule.level()` trả enum `Level.HIGH`; `rule.handler()` trả `Integer.class`; `rule.tags()` trả mảng `String[]` chứa hai giá trị; `rule.owner()` trả **annotation instance lồng nhau** kiểu `Owner`, rồi `.name()` trả `"core"`.
4. `@Rule("fallback")` là cú pháp viết gọn cho element mang tên `value`. Vì các element khác đều có `default`, có thể bỏ qua chúng khi gắn annotation trên `Fallback`. Do đó `fallback.retries()` nhận 3, `fallback.tags()` trả mảng rỗng và `fallback.owner().name()` là `"system"`.
5. `Rule.class.getDeclaredMethod("retries")` lấy `Method` mô tả element method. `retriesMethod.invoke(rule)` trả **giá trị tại annotation instance `rule`**, tức 5; vì gọi qua `Method.invoke` có kiểu trả về `Object`, primitive `int` được boxing thành `Integer` trong quá trình phản chiếu.
6. `retriesMethod.getDefaultValue()` đọc **default trên khai báo element** (`3`). Nó không thay đổi theo nơi annotation được gắn. Nếu element không khai báo default, API này trả `null`.
7. `String.class.getAnnotation(Rule.class)` trả `null` vì annotation `Rule` không hiện diện trên `String.class` theo quy tắc tìm kiếm tương ứng. Code thực tế nên luôn xử lý tình huống annotation vắng mặt.

Đọc annotation element **không gọi một handler nghiệp vụ** vì nó chỉ trả về metadata. Ví dụ `handler = Integer.class` lưu một class literal; nó **không tạo `Integer` instance**, không khởi chạy logic xử lý nào.

## 5. Cách đọc gọn: gọi element method theo kiểu tĩnh

Nếu bạn biết annotation type tại thời điểm viết chương trình, cách đơn giản nhất là:

~~~java
Rule rule = SomeClass.class.getAnnotation(Rule.class);
if (rule != null) {
    String route = rule.value();
    int retries = rule.retries();
    Level level = rule.level();
    String[] tags = rule.tags();
}
~~~

Đoạn mã này chỉ minh họa, giả định `SomeClass` được gắn `@Rule` và các kiểu đã được định nghĩa như mục 4.

Ưu điểm của **typed API**:

- Compiler kiểm tra đúng tên method, đúng kiểu trả về.
- Không cần ép kiểu `Object` từ `Method.invoke`.
- Dễ đọc và dễ refactor khi annotation type đổi tên element.
- Các giá trị mảng/enum/class/nested annotation giữ đúng kiểu khai báo, giảm lỗi runtime.

Đối với annotation bắt buộc phải có, tùy API có thể dùng `getDeclaredAnnotation` để lấy annotation khai báo trực tiếp trên phần tử, hoặc `getAnnotation` cho cách tìm kiếm theo quy tắc `AnnotatedElement`. Dù dùng API nào, nếu không có annotation phù hợp thì kết quả là `null` (đối với `getAnnotation`/`getDeclaredAnnotation` đơn lẻ) — **không gọi `rule.value()` trước khi kiểm tra**.

Không nên dùng `field.get(...)` trên annotation instance để lấy `value` hay `retries`. Cấu trúc annotation type được công bố bằng **element method**, không có quy tắc public field cùng tên để đọc.

## 6. Đọc động: introspection element methods và `Method.invoke`

Một framework có thể không biết trước tất cả tên element trong annotation type. Khi đó có thể nhận `Annotation annotation` và duyệt element methods:

~~~java
import java.lang.annotation.Annotation;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

static void printElements(Annotation annotation) throws Exception {
    Method[] methods = annotation.annotationType().getDeclaredMethods();
    Arrays.sort(methods, Comparator.comparing(Method::getName));

    for (Method method : methods) {
        Object actualValue = method.invoke(annotation);
        Object defaultValue = method.getDefaultValue();

        System.out.println(method.getName()
                + " -> " + stringify(actualValue)
                + " (default=" + stringify(defaultValue) + ")");
    }
}

static String stringify(Object value) {
    if (value == null) return "null";
    if (value instanceof Object[] array) return Arrays.deepToString(array);
    if (value instanceof int[] array) return Arrays.toString(array);
    if (value instanceof long[] array) return Arrays.toString(array);
    if (value instanceof boolean[] array) return Arrays.toString(array);
    if (value instanceof char[] array) return Arrays.toString(array);
    if (value instanceof byte[] array) return Arrays.toString(array);
    if (value instanceof short[] array) return Arrays.toString(array);
    if (value instanceof float[] array) return Arrays.toString(array);
    if (value instanceof double[] array) return Arrays.toString(array);
    return String.valueOf(value);
}
~~~

Đây là **các phương thức minh họa để chèn vào một class**, không phải file có `main` độc lập. `printElements` chỉ cần một instance của annotation đã lấy từ Reflection. Nếu muốn dùng riêng các method này, hãy đặt chúng vào một class Java hợp lệ và truyền annotation tương ứng.

Các điểm quan trọng:

- `annotation.annotationType()` trả **đúng annotation interface**; nó là lựa chọn rõ nghĩa hơn `annotation.getClass()` khi muốn tra cứu các element. Một annotation instance ở runtime có thể do JDK triển khai dưới dạng proxy/implementation, nhưng **implementation class không phải hợp đồng element của bạn**.
- `getDeclaredMethods()` trên annotation type trả các element method khai báo trên chính annotation type. Không dựa vào thứ tự mảng trả về; sắp xếp theo tên nếu cần log ổn định.
- `Method.invoke(annotation)` gọi element method trên **annotation instance**. Nếu kết quả là primitive, `invoke` trả wrapper; nếu là mảng, nhận đối tượng mảng với đúng loại; nếu là annotation lồng nhau, nhận annotation instance.
- `Method.getDefaultValue()` trả default được **khai báo** trên element, hoặc `null` nếu không có default. Nó không cho biết giá trị thực tế tại mỗi lần dùng annotation.
- Nếu cần phân biệt một giá trị bằng đúng default do không chỉ rõ khi gắn annotation hay do người viết **ghi tường minh giá trị trùng default**, Reflection thường chỉ cho thấy **giá trị đã hợp thành**. Đừng dùng `actualValue.equals(defaultValue)` để kết luận người viết có/không gõ element tại source.
- Đừng coi `Annotation.toString()` là giao diện serialization dữ liệu ổn định. Hãy đọc các element cụ thể và tự định dạng khi muốn xuất JSON/log/API.

Mã lặp trên dùng `instanceof Object[]` để hiển thị các mảng reference; riêng mảng primitive có từng nhánh `Arrays.toString`. Nếu chỉ viết `String.valueOf(value)` cho một mảng, có thể nhìn thấy chuỗi tên kiểu/hash thay vì nội dung mảng.

## 7. Phân biệt default với giá trị instance

Trong `@interface RetryPolicy { int attempts() default 3; String label(); }`, phần tử `attempts()` có default là `3`, còn `label()` bắt buộc được cung cấp. `RetryPolicy.class.getDeclaredMethod("attempts").getDefaultValue()` trả `Integer(3)`; gọi `attempts()` trên annotation instance trả giá trị **hiệu lực** tại nơi sử dụng, có thể khác 3. `getDefaultValue()` trả `null` cho `label()` vì không khai báo default, không có nghĩa `label()` của annotation hợp lệ trả null.

Giá trị hiệu lực bằng default không chứng minh người viết đã bỏ qua element tại source. Bài riêng về `Method.getDefaultValue()` phân tích đầy đủ các kiểu dữ liệu, annotation evolution và phân biệt default method của interface.

## 8. Trường hợp `value` đặc biệt và những nhầm lẫn về cú pháp

Element tên `value` được Java cho phép viết gọn khi nó là element duy nhất được chỉ định tại nơi gắn annotation:

~~~java
@Rule("checkout")
class A {
}
~~~

Nó tương đương `@Rule(value = "checkout")` (các element còn lại dùng default nếu có). Nhưng nếu cần khai báo thêm element, dùng dạng đặt tên:

~~~java
@Rule(value = "checkout", retries = 5)
class B {
}
~~~

Không được hiểu `value()` là hàm tự mang ý nghĩa nghiệp vụ hoặc là phương thức đặc biệt tự chạy. Nó chỉ có quy tắc cú pháp tiện lợi khi khai báo annotation. Cú pháp `@Rule("checkout", retries = 5)` không phải kiểu rút gọn được cho phép trong Java; phải viết tên `value =` khi cung cấp thêm cặp element–value.

**Một annotation có thể có nhiều element**, nhưng chỉ duy nhất element `value` có cú pháp viết tắt này. Các element không có default phải được truyền tại nơi gắn annotation, dù tên của chúng không phải `value`.

## 9. Đọc trên đúng phần tử runtime

Để lấy annotation trên **method**, dùng `Method` từ `clazz.getDeclaredMethod(...)` rồi đọc bằng `method.getAnnotation(MyAnnotation.class)`; gọi `clazz.getAnnotation(...)` chỉ hỏi annotation của **class**. Đối với field, constructor, parameter hoặc TYPE_USE cũng phải chọn đúng đối tượng Reflection/`AnnotatedType`. `@Retention(RUNTIME)` bảo đảm metadata phù hợp được giữ để đọc; `@Target` chỉ hạn chế nơi dùng, không tự tạo hành vi. Các API declared, inherited và repeatable được giải thích ở phần đầu chương.

## 10. Lỗi runtime cần xử lý khi đọc annotation

Thao tác đọc annotation element thông thường đơn giản, nhưng mã framework xử lý class file từ nhiều phiên bản có thể gặp ngoại lệ:

| Tình huống | API liên quan | Cách hiểu/xử lý |
| --- | --- | --- |
| Annotation không tồn tại tại phần tử | `getAnnotation(...)` | Trả `null`; kiểm tra trước khi gọi element method |
| Annotation không giữ ở `RUNTIME` | `getAnnotation(...)` | Metadata không sẵn có với Reflection runtime, không tự suy ra tên/giá trị |
| Đọc method element từ annotation instance đúng kiểu | `rule.value()`, `rule.retries()` | Trả giá trị theo kiểu khai báo |
| Lấy default của element không có default | `Method.getDefaultValue()` | Trả `null`; không có nghĩa một annotation instance hợp lệ có giá trị `null` |
| Gọi `Method.invoke` với instance hoặc đối số sai | `invoke(...)` | Có thể ném `IllegalArgumentException` hoặc ngoại lệ Reflection liên quan |
| Class literal trong annotation tham chiếu kiểu không còn tồn tại | Element trả `Class<?>` | Có thể ném `TypeNotPresentException` khi truy cập element |
| Enum element tham chiếu enum constant đã bị loại ở runtime | Element trả `enum` | Có thể ném `EnumConstantNotPresentException` |
| Type khai báo element đã thay đổi không tương thích với metadata còn lưu | Đọc element từ class file cũ | Có thể ném `AnnotationTypeMismatchException` |
| Một required element bị thiếu do thay đổi không tương thích giữa các phiên bản | Lời gọi element method | Có thể ném `IncompleteAnnotationException` |

Khi dùng `Method.invoke`, ngoại lệ do method được gọi ném có thể được **bọc trong `InvocationTargetException`**, nên nếu cần diagnostic phải kiểm tra `getCause()`. Nếu chương trình giả định tên element từ cấu hình và gọi `getDeclaredMethod("name")` sai, API tra cứu có thể ném `NoSuchMethodException`; đó không phải là lỗi vì annotation instance không có giá trị.

Các trường hợp bất thường thường gắn với class file không đồng bộ phiên bản, thiếu dependency, class loader hoặc bytecode bị biến đổi. Không nên viết một bộ xử lý annotation chung rồi bắt mọi exception để silently bỏ qua metadata bắt buộc.

## 11. Đọc member value chưa thực hiện nghiệp vụ

Với `@MinimumAge(18)`, `annotation.value()` chỉ trả số `18`; nó không tự đọc một field, so tuổi hoặc từ chối input. Tương tự, element `handler()` trả `Class<?>` không tự khởi tạo và chạy handler. Cần validator/framework hoặc caller đọc cấu hình, lấy dữ liệu thực tế và ra quyết định. Bài cuối chương có ví dụ chạy được và chỉ rõ các ranh giới validation.

## 12. Checklist khi đọc annotation element trong ứng dụng

1. **Xác định nơi annotation được gắn:** class, method, field, constructor hay parameter; tra cứu đúng phần tử.
2. **Kiểm tra retention:** cần `RUNTIME` để đọc bằng Reflection runtime.
3. **Chọn đúng annotation type:** dùng `getAnnotation(MyAnno.class)` và kiểm tra `null`.
4. **Ưu tiên typed accessor:** `anno.value()`, `anno.level()`, `anno.tags()` nếu biết type; tránh Reflection hai lần không cần thiết.
5. **Nếu xử lý tổng quát:** dùng `annotation.annotationType().getDeclaredMethods()`, `method.invoke(annotation)` và `getDefaultValue()` đúng mục đích.
6. **Đừng nhầm default và actual:** default trên khai báo không chứng minh annotation instance hiện dùng default.
7. **Xử lý giá trị nhiều kiểu:** primitive/wrapper, `String`, `Class<?>`, enum, annotation lồng nhau, mảng một chiều; định dạng array đúng.
8. **Cân nhắc class loader và phiên bản:** thay đổi element signature hoặc enum/class được tham chiếu có thể khiến code đọc gặp exception ở runtime.
9. **Giữ biệt lập metadata và nghiệp vụ:** cần code/framework cụ thể để biến giá trị annotation thành validation, routing, xử lý giao dịch hoặc behavior.
10. **Kiểm thử trên artifact thực tế:** khi nhiều module hoặc công cụ bytecode tham gia, xác minh annotation thật sự được lưu và có giá trị phù hợp trong class file đã phát hành.

## 13. Tự kiểm tra

**Câu 1:** Annotation type khai báo `int retries() default 3;`. `Rule rule` trên `Checkout` ghi `retries = 5`. `rule.retries()` và `Rule.class.getDeclaredMethod("retries").getDefaultValue()` trả gì? **Lần lượt 5 và 3.**

**Câu 2:** `getAnnotation(MyAnno.class)` trả `null`. Có thể gọi `.value()` không? **Không.** Phải kiểm tra annotation có tồn tại tại đúng phần tử và giữ ở runtime.

**Câu 3:** Element khai báo `String[] tags() default {};`. Gọi `annotation.tags()` nhận `List<String>` hay `String[]`? **`String[]`**, phải dùng `Arrays.toString`/duyệt mảng nếu muốn hiển thị nội dung.

**Câu 4:** Vì sao gọi `rule.owner().name()` hợp lệ? **Vì `owner()` trả một annotation instance kiểu `Owner`**, mà `Owner` có element `name()` trả `String`.

**Câu 5:** Có thể dùng `annotation.getClass().getDeclaredMethods()` để coi mọi method tìm được là element chuẩn không? **Không nên.** Dùng `annotation.annotationType()` để lấy contract annotation type, tránh nhầm implementation class.

**Câu 6:** `handler()` trả `Integer.class`. Có nghĩa ứng dụng đã tạo `Integer` và chạy một handler không? **Không.** Đây chỉ là giá trị class literal; hành vi xử lý phải do caller quyết định.

**Câu 7:** `Method.getDefaultValue()` là `null` thì `annotation.element()` chắc cũng `null`? **Không.** Nó chỉ có nghĩa element không khai báo default; một annotation instance hợp lệ phải có giá trị theo quy tắc sử dụng annotation.

**Ghi nhớ:** **Element của annotation là phương thức không tham số trên annotation type.** Lấy annotation instance từ đúng phần tử (`getAnnotation`), rồi gọi phương thức element (`annotation.value()` hoặc `Method.invoke(annotation)`) để đọc **giá trị thực tế**. Chỉ dùng `Method.getDefaultValue()` khi muốn đọc **giá trị mặc định trong khai báo**, và không nhầm metadata với hành vi nghiệp vụ.
