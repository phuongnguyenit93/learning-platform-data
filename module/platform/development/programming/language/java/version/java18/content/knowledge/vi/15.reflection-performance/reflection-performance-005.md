# Ảnh hưởng của vị trí lưu Method, Constructor hoặc Field đến khả năng tối ưu của JIT

## 1. Mục tiêu và bối cảnh Java 18

Từ **JDK 18**, JEP 416 thay đổi cách Core Reflection được triển khai bên trong JDK: lời gọi `Method.invoke` và `Constructor.newInstance` dựa trên cơ chế method handles, còn thao tác với `Field` sử dụng nền tảng truy cập trường liên quan đến method handles/variable handles. Các API `java.lang.reflect` vẫn được dùng như trước; hợp đồng kiểm tra kiểu, quyền truy cập và exception vẫn là điểm tựa cho code ứng dụng.

Một hệ quả hiệu năng quan trọng là: **vị trí và cách lưu đối tượng reflection có thể ảnh hưởng đến những gì JIT chứng minh được tại điểm gọi.** Cùng một method Java nhưng được gọi qua:

- `static final Method` cố định;
- trường instance `Method` thay đổi được;
- một phần tử của `Method[]`;
- kết quả tra cứu `Map` theo khóa động;

có thể tạo những cơ hội tối ưu khác nhau.

Bài này tập trung vào ba loại metadata reflection:

- `java.lang.reflect.Method` — mô tả method.
- `java.lang.reflect.Constructor` — mô tả constructor.
- `java.lang.reflect.Field` — mô tả trường dữ liệu.

**Mục tiêu học:** hiểu vì sao một reference ổn định, đặc biệt qua `static final`, thường thuận lợi cho JIT; phân biệt cache để tránh lookup lặp lại với tối ưu constant folding; biết cách đo thật thay vì suy diễn từ từ khóa `final`.

> **Lưu ý về phiên bản:** JEP 416 được đưa vào JDK 18 và còn liên quan đến JDK hiện đại. Triển khai Core Reflection cũ đã bị loại bỏ ở JDK 22. Vì vậy, không dùng những cấu hình quay về triển khai reflection cũ làm giải pháp tối ưu hoặc hướng dẫn tương thích hiện hành.

## 2. Ba tầng cần phân biệt: lookup, invoke và xử lý nghiệp vụ

Giả sử ứng dụng muốn gọi method:

```java
public int calculate(int delta) {
    return base + delta;
}
```

Có ba khoản công việc tách biệt:

1. **Lookup metadata:** tìm `Method` bằng `getMethod` hoặc `getDeclaredMethod`.
2. **Reflective invocation:** dùng `Method.invoke` với receiver và đối số; JDK kiểm tra quyền, kiểu, số lượng đối số và chuyển đổi hợp lệ.
3. **Target work:** thực thi thân `calculate`.

Ví dụ chưa cache:

```java
int calculateReflectively(Subject receiver, int delta)
        throws ReflectiveOperationException {
    Method m = Subject.class.getMethod("calculate", int.class);
    return (Integer) m.invoke(receiver, delta);
}
```

Nếu method này được gọi lặp lại nhiều lần, `getMethod` cũng chạy lặp lại. Việc cache metadata có thể tránh chi phí lookup, nhưng **không tự bảo đảm** JIT sẽ coi `m` là hằng tại điểm gọi.

Ví dụ dùng metadata cache:

```java
private static final Method CALCULATE_METHOD = findCalculateMethod();

private static Method findCalculateMethod() {
    try {
        return Subject.class.getMethod("calculate", int.class);
    } catch (NoSuchMethodException e) {
        throw new ExceptionInInitializerError(e);
    }
}
```

Ở đây:

- Lookup được thực hiện khi khởi tạo lớp chứa cache.
- Reference đến `Method` không thể được gán lại qua field `CALCULATE_METHOD`.
- Nếu JIT có thể chứng minh target ổn định, nó có thêm khả năng rút gọn đường gọi hoặc inline các lớp trung gian.

**Không nhầm:** `static final Method` không phải compile-time constant theo Java Language Specification. Nó là object reference được gán khi khởi tạo lớp, không phải một hằng kiểu `int`/`String` được `javac` ghi thành `ConstantValue`. Khả năng thấy nó như hằng tại runtime là một **quyết định tối ưu của JIT**, không phải bảo đảm về thời gian chạy trong đặc tả Java.

## 3. Vì sao JIT cần biết reflection target ổn định?

JIT (Just-In-Time compiler) biên dịch những đoạn code được thực thi đủ thường xuyên thành machine code và có thể thực hiện:

- Inlining: đưa nội dung các lời gọi nhỏ vào caller.
- Constant propagation/constant folding: dùng giá trị mà compiler chứng minh ổn định để rút gọn biểu thức.
- Devirtualization và giảm dispatch động khi biết đủ về target.
- Escape analysis: xác định một object có thật sự cần cấp phát hoặc tồn tại ngoài phạm vi không.
- Loại bỏ kiểm tra hoặc trung gian dư thừa khi chứng minh được điều kiện hợp lệ.

Ở một lời gọi reflection động:

```java
Object result = method.invoke(receiver, delta);
```

JIT cần biết `method` tương ứng với member nào. Nếu mỗi lần `method` có thể trỏ tới thành viên khác, khó biến luồng gọi thành một đường trực tiếp đến một target cố định.

Ngược lại:

```java
Object result = FIXED_METHOD.invoke(receiver, delta);
```

khi `FIXED_METHOD` được giữ trong `static final` và JIT suy ra được đối tượng thực tế, đường gọi dễ chuyên biệt hóa hơn.

Sơ đồ khái niệm:

```text
                           Điểm gọi reflection
                                    |
                     JIT có biết member target không?
                              /                 \
                             /                   \
                    Có khả năng biết          Chưa chứng minh được
                           |                       |
                           v                       v
                Chuyên biệt hóa đường gọi    Tra target / dispatch
                + inline khi có thể          + kiểm tra động
                           |                       |
                           +-----------+-----------+
                                       |
                                       v
                            Thực thi method/field
```

Sơ đồ này mô tả **cơ hội** của compiler, không phải lộ trình bắt buộc của mọi JVM hoặc mọi lần chạy. JIT còn phụ thuộc hotness, profile, kích thước code, giới hạn inlining, escape analysis, cấu hình và tải thực tế.

## 4. JEP 416: thay đổi quan trọng vẫn áp dụng hiện nay

JEP 416 đưa Core Reflection về gần hạ tầng `java.lang.invoke`:

- Lời gọi method và constructor dùng nền tảng method handles.
- Truy cập field dùng cơ chế truy cập trường dựa trên variable handles.
- Mục tiêu bao gồm giảm nhiều đường triển khai đặc thù của reflection và cho phép tận dụng tối ưu JIT có sẵn cho method-handle invocation.

Trong các phép đo ban đầu phục vụ thiết kế JEP 416, các reflective objects được giữ trong `static final` thường cho kết quả tốt hơn khi target được constant-fold. Khi metadata nằm ở vị trí không thuận lợi để constant-fold, nhất là `Field` trong tình huống biến động, một số benchmark ghi nhận suy giảm so với thiết kế cũ.

**Đọc kết quả lịch sử đúng cách:**

- Đây là quan sát về cấu hình benchmark cụ thể của JDK khi phát triển JEP 416, không phải định luật “reflection sau Java 18 luôn nhanh hơn”.
- Không lấy một tỉ lệ phần trăm lịch sử làm hệ số tối ưu của ứng dụng đang dùng JDK 27.
- Trên JDK hiện đại, không có ý nghĩa thực hành khi so sánh bằng cách bật lại implementation trước JDK 18: JDK 22 đã loại bỏ đường triển khai cũ và cờ tương thích trước đây không còn tác dụng để chọn lại nó.

Điều còn giá trị cho thiết kế hôm nay là **đo theo nơi metadata được lưu, hình dạng call site và đặc điểm workload**.

## 5. static final: tình huống thuận lợi nhất khi target cố định

Ví dụ với `Method`:

```java
import java.lang.reflect.Method;

public class CachedMethodExample {
    public static final class Service {
        public int addOne(int value) {
            return value + 1;
        }
    }

    private static final Method ADD_ONE = findAddOne();

    private static Method findAddOne() {
        try {
            return Service.class.getMethod("addOne", int.class);
        } catch (NoSuchMethodException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static int invoke(Service receiver, int value)
            throws ReflectiveOperationException {
        return (Integer) ADD_ONE.invoke(receiver, value);
    }

    public static void main(String[] args) throws Exception {
        System.out.println(invoke(new Service(), 7)); // 8
    }
}
```

Ưu điểm:

1. Lookup diễn ra một lần khi class được khởi tạo.
2. Mỗi invocation dùng cùng reference.
3. JIT có thể nhận ra target ổn định tại call site và tối ưu đường gọi.
4. Code giữ chữ ký reflection và dùng API công khai.

**Nhưng:** `final` chỉ ngăn gán lại reference của field. Nó không biến mọi trạng thái bên trong `Method` thành immutable và không cho phép bỏ qua các quy tắc access/argument checks theo hợp đồng API.

Nếu member được chọn là public thuộc public class, ví dụ có thể chạy mà không dùng `setAccessible(true)` hay can thiệp vào internals JDK.

## 6. Method trong instance field, non-final field và tham số method

### 6.1. Trường instance không final

```java
final class MethodRunner {
    private Method selected;

    MethodRunner(Method selected) {
        this.selected = selected;
    }

    Object execute(Object receiver, Object arg)
            throws ReflectiveOperationException {
        return selected.invoke(receiver, arg);
    }

    void selectAnother(Method next) {
        this.selected = next;
    }
}
```

Mỗi lần gọi `execute`, `selected` có thể là một method khác. Nếu nhiều member khác nhau được dùng tại một call site, JIT khó suy ra một target duy nhất.

Không nên kết luận “instance field luôn chậm”: nếu ứng dụng chỉ tạo một runner, không thay selected và JIT inline được caller, compiler **có thể** chứng minh target ổn định từ thông tin ngữ cảnh.

### 6.2. Trường instance final

```java
final class FixedRunner {
    private final Method method;

    FixedRunner(Method method) {
        this.method = method;
    }

    Object execute(Object receiver, Object arg)
            throws ReflectiveOperationException {
        return method.invoke(receiver, arg);
    }
}
```

Reference không đổi sau constructor. Đây là thiết kế tốt khi mỗi runner gắn với một method cụ thể, nhưng nó vẫn không giống một `static final Method` duy nhất cho cả lớp.

Nếu cùng một call site được gọi với hàng trăm runner có target khác nhau, `final` của từng instance không khiến tất cả giá trị trở thành một hằng chung.

### 6.3. Method truyền qua tham số

```java
static Object execute(Method method, Object receiver, Object value)
        throws ReflectiveOperationException {
    return method.invoke(receiver, value);
}
```

Nhìn riêng `execute`, target có thể thay đổi ở mọi lời gọi. Tuy nhiên, nếu caller truyền một field `static final` cố định và JIT inline được `execute`, compiler vẫn có thể constant-propagate giá trị ở call site.

Vì thế, vị trí khai báo chỉ là một yếu tố; **đường truyền dữ liệu và mức độ đa hình của call site** cũng quan trọng.

## 7. Metadata trong mảng, List và Map

### 7.1. static final của mảng không đồng nghĩa phần tử là hằng

```java
private static final Method[] METHODS = {ADD_ONE};

// ADD_ONE là Method đã được tìm trước đó.
Object result = METHODS[0].invoke(receiver, 7);
```

Từ khóa `final` ở đây cố định **reference tới mảng**, không cố định nội dung phần tử:

```java
METHODS[0] = anotherMethod; // Hợp lệ nếu code có quyền truy cập field.
```

JIT phải xét khả năng phần tử mảng thay đổi. Không thể suy ra `METHODS[0]` có cùng mức dễ constant-fold với `static final Method ADD_ONE` chỉ vì mảng được giữ bởi field `static final`.

### 7.2. List bất biến vẫn là một thao tác tra cứu

```java
private static final java.util.List<Method> METHODS =
    java.util.List.of(ADD_ONE);

Object result = METHODS.get(0).invoke(receiver, 7);
```

`List.of` tạo collection không cho sửa nội dung qua API của list. Điều này hữu ích cho an toàn dữ liệu nhưng không hứa rằng JIT sẽ constant-fold kết quả `get(0)` tại mọi call site.

JIT có thể inline và rút gọn một đường gọi list cụ thể nếu biết đủ. Tuy nhiên đó vẫn là optimization-dependent, không phải thuộc tính của riêng từ khóa `final` hay `List.of`.

### 7.3. Map phù hợp cho dispatch động

```java
private final java.util.Map<String, Method> routes;

Object dispatch(String operation, Object receiver, Object arg)
        throws ReflectiveOperationException {
    Method target = routes.get(operation);
    if (target == null) {
        throw new IllegalArgumentException("Unknown operation");
    }
    return target.invoke(receiver, arg);
}
```

Ở đây request có thể chọn nhiều method tùy `operation`. Đây là một thiết kế hợp lệ cho interpreter/plugin/framework, nơi tính linh hoạt quan trọng.

Nếu ứng dụng cần dispatch động, không nên thay nó bằng hàng loạt field `static final` chỉ để ép benchmark đẹp. Có thể phân chia hot path cố định ra khỏi nhánh dispatch động khi có số liệu chứng minh.

## 8. Constructor: vị trí lưu ảnh hưởng cả đường tạo object

Ví dụ:

```java
public static final class Point {
    public final int x;

    public Point(int x) {
        this.x = x;
    }
}
```

Tạo `Constructor<Point>` một lần:

```java
private static final Constructor<Point> POINT_CTOR = findPointCtor();

private static Constructor<Point> findPointCtor() {
    try {
        return Point.class.getConstructor(int.class);
    } catch (NoSuchMethodException e) {
        throw new ExceptionInInitializerError(e);
    }
}

static Point create(int x) throws ReflectiveOperationException {
    return POINT_CTOR.newInstance(x);
}
```

Khi target constructor cố định và JIT có đủ profile, nó có thêm cơ hội inline các bước xung quanh `newInstance` và tối ưu object allocation nếu escape analysis chứng minh object không thoát ra ngoài.

So sánh với:

```java
Constructor<?> constructor = constructors[index];
Object instance = constructor.newInstance(argument);
```

Target constructor có thể khác nhau theo `index`; JVM cần giữ hành vi tạo đúng class và áp dụng đúng access/argument checks.

**Không đánh đồng:** khả năng tối ưu constructor reflection với việc xóa hoàn toàn cấp phát object. Một object trả ra cho caller hoặc được giữ ở nơi khác thường vẫn cần tồn tại theo semantics.

## 9. Field: trường hợp cần đặc biệt chú ý đến accessor và boxing

Ví dụ:

```java
public static final class Counter {
    public int value = 10;
}
```

Cache `Field` cố định:

```java
private static final Field VALUE_FIELD = findValueField();

private static Field findValueField() {
    try {
        return Counter.class.getField("value");
    } catch (NoSuchFieldException e) {
        throw new ExceptionInInitializerError(e);
    }
}
```

Đọc bằng typed accessor:

```java
static int read(Counter receiver)
        throws IllegalAccessException {
    return VALUE_FIELD.getInt(receiver);
}
```

Các phương án khác:

```java
private Field chosenField = VALUE_FIELD;
private Field[] fieldOptions = {VALUE_FIELD};

// Method đọc từ vị trí có thể biến động:
int current = chosenField.getInt(receiver);

// Method đọc qua mảng:
int selected = fieldOptions[0].getInt(receiver);
```

Với field access, target cụ thể quyết định kiểu, offset/đường truy cập và semantics của việc đọc/ghi. Nếu JIT không nhận ra `Field` là một target ổn định, nó có ít cơ hội rút gọn hoặc inline một đường truy cập cụ thể.

Khi đọc primitive field, `getInt` giúp tránh việc trả về `Object` rồi unbox như `(Integer) field.get(receiver)`. Hai cách vẫn phải tuân thủ access/type rules, nhưng có chi phí boxing khác nhau; nên đo với cùng semantics thay vì so sánh lệch.

### 9.1. final Field metadata khác final của target field

Đừng nhầm:

- `static final Field VALUE_FIELD`: reference tới metadata reflection không đổi.
- `public final int value` trong `Counter`: chính field nghiệp vụ không được gán lại theo ngữ nghĩa Java thông thường.

Đặt metadata trong `static final` **không** thay đổi modifier của field đích, không tự bật quyền ghi một final field và không bỏ qua quy tắc Java Memory Model.

## 10. Bảng so sánh các vị trí lưu metadata

| Vị trí giữ metadata | Có tránh lookup mỗi lần? | Cơ hội JIT thấy target cố định | Lưu ý |
| --- | --- | --- | --- |
| `static final Method` / `Constructor` / `Field` | Có. | Thường thuận lợi khi call site cố định. | Không bảo đảm compiler luôn inline hoặc nhanh nhất. |
| `static Method` không final | Có. | Phụ thuộc khả năng chứng minh không thay đổi. | Có thể được gán lại. |
| `final` instance field | Có. | Có thể tốt khi object và call site đủ ổn định. | Nhiều instance có thể trỏ member khác nhau. |
| Instance field không final | Có. | Thường khó hơn nếu target thay đổi. | Không tự động chậm trong mọi workload. |
| Local variable lấy từ field cố định | Có nếu field đã cache. | Có thể propagate khi inlining. | Local `final` không phải yếu tố duy nhất. |
| Phần tử `static final Method[]` | Có. | Không tự cố định phần tử; phụ thuộc profile/JIT. | Mảng vẫn mutable. |
| `List.of(...).get(index)` | Có. | Phụ thuộc index và đường gọi. | Immutable list không bảo đảm kết quả `get` là JIT constant. |
| `Map.get(key)` | Có. | Khó hơn khi key/target rất đa dạng. | Thích hợp dynamic dispatch. |
| `getMethod` mỗi invocation | Không. | Bị thêm lookup cost; JIT vẫn có thể tối ưu một phần. | Tránh trong hot path nếu không cần. |

Chọn thiết kế theo **thực tế số member cần gọi**. Không nên cố thay một cơ chế plugin có hàng nghìn target biến động bằng những giả định về call site monomorphic.

## 11. Ví dụ hoàn chỉnh: cùng member, nhiều vị trí lưu

Lưu thành `ReflectionPlacementDemo.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionPlacementDemo {
    public static final class Subject {
        public int base;

        public Subject(int base) {
            this.base = base;
        }

        public int plus(int delta) {
            return base + delta;
        }
    }

    // Metadata có target cố định cho cả lớp.
    private static final Method CONST_METHOD = method();
    private static final Constructor<Subject> CONST_CTOR = ctor();
    private static final Field CONST_FIELD = field();

    // Chỉ reference tới mảng là final; phần tử không final.
    private static final Method[] METHOD_ARRAY = {CONST_METHOD};
    private static final Constructor<?>[] CTOR_ARRAY = {CONST_CTOR};
    private static final Field[] FIELD_ARRAY = {CONST_FIELD};

    // Có thể được thay thế ở runtime.
    private Method instanceMethod = CONST_METHOD;
    private Constructor<Subject> instanceCtor = CONST_CTOR;
    private Field instanceField = CONST_FIELD;

    private static Method method() {
        try {
            return Subject.class.getMethod("plus", int.class);
        } catch (NoSuchMethodException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    private static Constructor<Subject> ctor() {
        try {
            return Subject.class.getConstructor(int.class);
        } catch (NoSuchMethodException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    private static Field field() {
        try {
            return Subject.class.getField("base");
        } catch (NoSuchFieldException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public int methodConstant(Subject target, int delta)
            throws ReflectiveOperationException {
        return (Integer) CONST_METHOD.invoke(target, delta);
    }

    public int methodInstance(Subject target, int delta)
            throws ReflectiveOperationException {
        return (Integer) instanceMethod.invoke(target, delta);
    }

    public int methodArray(Subject target, int delta)
            throws ReflectiveOperationException {
        return (Integer) METHOD_ARRAY[0].invoke(target, delta);
    }

    public Subject constructorConstant(int value)
            throws ReflectiveOperationException {
        return CONST_CTOR.newInstance(value);
    }

    public Subject constructorInstance(int value)
            throws ReflectiveOperationException {
        return instanceCtor.newInstance(value);
    }

    public Subject constructorArray(int value)
            throws ReflectiveOperationException {
        return (Subject) CTOR_ARRAY[0].newInstance(value);
    }

    public int fieldConstant(Subject target)
            throws IllegalAccessException {
        return CONST_FIELD.getInt(target);
    }

    public int fieldInstance(Subject target)
            throws IllegalAccessException {
        return instanceField.getInt(target);
    }

    public int fieldArray(Subject target)
            throws IllegalAccessException {
        return FIELD_ARRAY[0].getInt(target);
    }

    public static void main(String[] args) throws Exception {
        var demo = new ReflectionPlacementDemo();
        var target = new Subject(10);

        System.out.println(demo.methodConstant(target, 2)); // 12
        System.out.println(demo.methodInstance(target, 2)); // 12
        System.out.println(demo.methodArray(target, 2));    // 12

        System.out.println(demo.constructorConstant(7).base); // 7
        System.out.println(demo.constructorInstance(7).base); // 7
        System.out.println(demo.constructorArray(7).base);    // 7

        System.out.println(demo.fieldConstant(target)); // 10
        System.out.println(demo.fieldInstance(target)); // 10
        System.out.println(demo.fieldArray(target));    // 10
    }
}
```

Biên dịch và chạy:

```sh
javac ReflectionPlacementDemo.java
java ReflectionPlacementDemo
```

Kết quả đúng về mặt chức năng không chứng minh phương án nào nhanh hơn. Ví dụ chỉ cho thấy **cùng member** và **cùng kết quả** khi reference metadata được lưu tại những nơi khác nhau.

Trong mọi phương án, quy tắc access, boxing/unboxing, widening và các exception của Core Reflection vẫn như nhau.

## 12. Ví dụ tối ưu sai: lookup lại trong vòng lặp

Không nên viết:

```java
for (int i = 0; i < requests.size(); i++) {
    Method m = Service.class.getMethod("handle", Request.class);
    m.invoke(service, requests.get(i));
}
```

Nếu cùng một method được gọi cho mọi phần tử, hãy lookup trước:

```java
Method m = Service.class.getMethod("handle", Request.class);

for (Request request : requests) {
    m.invoke(service, request);
}
```

Với hot path cố định, có thể lưu vào cache `static final` nếu vòng đời class và phạm vi target cho phép.

Tuy nhiên, không nên biến mọi local `Method` thành static field một cách máy móc. Nếu một method thuộc plugin có class loader riêng và có thể unload, static cache toàn cục có thể giữ class loader sống quá lâu; khi đó cân nhắc cache gắn với class/lifecycle phù hợp, chẳng hạn `ClassValue`.

## 13. Benchmark đúng: cần JMH, không chỉ nanoTime

Với những đoạn code cực ngắn, một phép đo thô dễ đưa ra kết luận sai vì:

- JIT chưa đủ warmup.
- Class loading và khởi tạo cache xuất hiện trong phép đo này nhưng không xuất hiện trong phép đo kia.
- Compiler loại bỏ phép tính không ảnh hưởng tới kết quả quan sát được.
- Escape analysis khiến một số constructor allocation không xảy ra.
- GC, CPU frequency, contention hoặc tác vụ nền gây nhiễu.
- Kết quả theo nanoseconds rất nhạy với kích thước method, boxing và cách nhận giá trị trả về.
- Call site chỉ được thử với một target trong benchmark nhưng production có hàng trăm target.

**JMH (Java Microbenchmark Harness)** do dự án OpenJDK Code Tools cung cấp là công cụ phù hợp để đo microbenchmark JVM với warmup, measurement, forks và cơ chế tiêu thụ kết quả.

Cần dùng cùng JDK vendor/version, cùng máy, cùng tham số JVM, và phân tích phân phối kết quả chứ không chỉ một số duy nhất.

### 13.1. Thứ cần so sánh

Ít nhất gồm:

1. Gọi trực tiếp: `target.plus(delta)`.
2. `Method` trong `static final`.
3. `Method` trong instance field.
4. `Method` lấy từ phần tử mảng.
5. `Constructor` trong `static final` so với instance field.
6. `Field` trong `static final` so với instance field/mảng.

Nếu cần giải thích tối ưu, mở rộng bằng một case nhiều target thay đổi ở cùng call site. Một benchmark chỉ dùng một `Method` dù đặt trong mảng chưa chắc mô phỏng được một hệ thống plugin đa hình.

### 13.2. Mẫu JMH để khảo sát vị trí lưu

Ví dụ sau dùng JMH trong **một dự án đã khai báo JMH dependency/annotation processor**. Đây không phải file Java chạy trực tiếp bằng `javac` đơn lẻ nếu chưa có JMH trên classpath.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(3)
public class MemberPlacementBenchmark {
    public static final class Subject {
        public int base;

        public Subject(int base) {
            this.base = base;
        }

        public int plus(int delta) {
            return base + delta;
        }
    }

    private static final Method METHOD = getMethod();
    private static final Constructor<Subject> CONSTRUCTOR = getConstructor();
    private static final Field FIELD = getField();

    private Method instanceMethod = METHOD;
    private Method[] methodArray = {METHOD};
    private Constructor<Subject> instanceConstructor = CONSTRUCTOR;
    private Field instanceField = FIELD;
    private Field[] fieldArray = {FIELD};

    private Subject receiver = new Subject(10);

    @Param({"1", "17"})
    public int delta;

    private static Method getMethod() {
        try {
            return Subject.class.getMethod("plus", int.class);
        } catch (NoSuchMethodException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    private static Constructor<Subject> getConstructor() {
        try {
            return Subject.class.getConstructor(int.class);
        } catch (NoSuchMethodException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    private static Field getField() {
        try {
            return Subject.class.getField("base");
        } catch (NoSuchFieldException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    @Benchmark
    public int direct() {
        return receiver.plus(delta);
    }

    @Benchmark
    public int methodStaticFinal() throws ReflectiveOperationException {
        return (Integer) METHOD.invoke(receiver, delta);
    }

    @Benchmark
    public int methodInstance() throws ReflectiveOperationException {
        return (Integer) instanceMethod.invoke(receiver, delta);
    }

    @Benchmark
    public int methodArray() throws ReflectiveOperationException {
        return (Integer) methodArray[0].invoke(receiver, delta);
    }

    @Benchmark
    public int constructorStaticFinal()
            throws ReflectiveOperationException {
        return CONSTRUCTOR.newInstance(delta).base;
    }

    @Benchmark
    public int constructorInstance()
            throws ReflectiveOperationException {
        return instanceConstructor.newInstance(delta).base;
    }

    @Benchmark
    public int fieldStaticFinal() throws IllegalAccessException {
        return FIELD.getInt(receiver);
    }

    @Benchmark
    public int fieldInstance() throws IllegalAccessException {
        return instanceField.getInt(receiver);
    }

    @Benchmark
    public int fieldArray() throws IllegalAccessException {
        return fieldArray[0].getInt(receiver);
    }
}
```

Chương trình benchmark có giá trị ở việc **thiết kế nhóm so sánh tương đồng**. Nó vẫn chưa chứng minh causal mechanism trong JIT. Muốn xác nhận tối ưu cụ thể, cần quan sát profile/compilation hoặc assembly/JIT diagnostics theo công cụ và JVM đang dùng.

### 13.3. Những bẫy riêng của benchmark này

- `constructorStaticFinal()` trả về field của object vừa tạo; JIT có thể loại bỏ allocation khi chứng minh object không escape. Đây là hiệu quả thật của tối ưu nhưng khiến kết quả không chỉ đo riêng overhead constructor reflection.
- `METHOD.invoke(receiver, delta)` phải tuân thủ boxing/return adaptation, khác bản chất với lời gọi trực tiếp; không tuyên bố chênh lệch hoàn toàn do vị trí lưu reference.
- Field trong instance field có thể vẫn được JIT tối ưu nhờ profile của benchmark; đừng mặc định nó chậm chỉ vì không có `final`.
- Benchmark không có dispatch polymorphic thực sự vì tất cả các variant đều chọn cùng một target. Với ứng dụng dynamic routing, cần thử thêm nhiều target có distribution thực tế.
- Kiểm tra cả throughput, allocation rate (nếu liên quan) và latency tail ở bài đo cấp ứng dụng, không chỉ `AverageTime` của một lời gọi rất nhỏ.

### 13.4. Không dựa vào một lần chạy

Kết quả JMH chịu ảnh hưởng của máy, hệ điều hành, bản JDK, GC, heap, CPU và lịch chạy. Nên:

- Chạy nhiều forks.
- Dùng đủ warmup.
- Giữ đầu vào và receiver có cấu trúc tương đương.
- Tiêu thụ kết quả của mỗi benchmark (JMH thực hiện xử lý cho giá trị trả về).
- So sánh mức sai số và độ ổn định; không phóng đại một chênh lệch nhỏ.
- Kiểm tra ứng dụng thật trước khi đổi kiến trúc.

## 14. Khi nào nên dùng MethodHandle hoặc VarHandle trực tiếp?

Nếu một hot path sử dụng một member cố định và kết quả đo chứng minh reflective dispatch là nút thắt, có thể cân nhắc API `java.lang.invoke` trực tiếp:

- `MethodHandle` cho method và constructor.
- `VarHandle` cho field và các access mode được hỗ trợ.

Ví dụ method handle typed:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class MethodHandleExample {
    public static final class Service {
        public int plus(int delta) {
            return 10 + delta;
        }
    }

    private static final MethodHandle PLUS = findPlus();

    private static MethodHandle findPlus() {
        try {
            return MethodHandles.lookup().findVirtual(
                Service.class,
                "plus",
                MethodType.methodType(int.class, int.class)
            );
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static int run(Service receiver, int delta) throws Throwable {
        return (int) PLUS.invokeExact(receiver, delta);
    }
}
```

`invokeExact` yêu cầu descriptor chính xác ở điểm gọi: trong ví dụ trên là `(Service, int)int`. Khi dùng sai, lỗi có thể là `WrongMethodTypeException`, không phải cùng nhóm exception của `Method.invoke`.

Method handle có kiểm tra quyền tại thời điểm tạo handle qua `Lookup`, còn Core Reflection kiểm tra quyền theo hợp đồng reflective call. Không được thay hai API cho nhau mà bỏ qua semantics access control.

Với field, có thể dùng:

```java
VarHandle handle = MethodHandles.lookup().findVarHandle(
    Counter.class, "value", int.class
);
int current = (int) handle.get(counter);
```

Ví dụ giả định `Counter` và field `value` là các member mà lookup class được phép truy cập.

**Lựa chọn API phải theo hợp đồng, không chỉ theo một microbenchmark.** `VarHandle` có các memory-ordering access mode khác nhau; `MethodHandle` có luật adaptation và exception riêng. Nếu cần dynamic metadata discovery, Core Reflection vẫn là API công khai phù hợp.

## 15. Cache có thể làm tăng chi phí bộ nhớ hoặc giữ class loader

Cache metadata mang lại lợi ích khi reuse, nhưng cũng có trách nhiệm quản lý vòng đời.

Ví dụ plugin runtime:

```text
PluginLoader A -- Class A -- Method A
PluginLoader B -- Class B -- Method B
                       |
                       v
             Global static Map cache
```

Nếu một global static map giữ `Method` của class thuộc plugin loader đã unload về mặt nghiệp vụ, reference đó có thể tiếp tục giữ những object liên quan sống trong heap. Điều này ảnh hưởng bộ nhớ và khả năng unload của class loader.

Giải pháp tùy ứng dụng:

- Cache theo vòng đời plugin, xóa entry khi plugin bị tháo gỡ.
- Dùng `ClassValue` cho cache dữ liệu gắn với `Class` khi phù hợp.
- Không cache vô hạn mọi member phát hiện qua scan.
- Đo lookup cost trước khi thêm lớp cache phức tạp.

Một cache động giữ member ở `Map` vẫn tránh được lookup lặp lại, dù không tạo điều kiện constant-fold giống một field `static final` đơn lẻ. Đó là lựa chọn hợp lý khi yêu cầu chức năng bắt buộc phải dynamic.

## 16. Tình huống thực tế và quyết định thiết kế

### 16.1. Adapter chỉ gọi một API cố định

Nếu một adapter luôn gọi cùng method public, hãy:

1. Lookup một lần.
2. Giữ metadata trong `static final` hoặc cấu trúc có vòng đời ổn định.
3. Dùng direct call nếu có thể và hợp đồng type/access phù hợp.
4. Chỉ chuyển sang MethodHandle khi đo được lợi ích và đã kiểm chứng exception semantics.

### 16.2. Framework serialization đọc field theo schema

Nếu một schema có nhiều field, một array/list metadata có thể là cấu trúc thuận tiện. Thay vì coi đó là “sai” vì JIT khó constant-fold:

- Giữ schema metadata cache ổn định theo class.
- Có thể tạo accessor chuyên biệt cho các field hot nếu profile chứng minh đáng làm.
- Giữ đường chung cho field hiếm và schema động.
- Tránh giữ class loader sau khi plugin/module hết vòng đời.

### 16.3. Hệ thống router gọi method theo tên

Nếu request chọn method theo tên:

```java
Method selected = registry.get(request.operation());
selected.invoke(handler, request);
```

Target thực sự thay đổi theo request. Static final cho **registry object** không có nghĩa từng lookup result là hằng JIT. Trong trường hợp này, hãy đo dispatch, parsing, validation và target work cùng nhau.

### 16.4. Có hàng triệu lời gọi tới một method nhỏ

Đây là tình huống dễ làm rõ chênh lệch reflection overhead:

- So sánh direct, cached reflection và MethodHandle.
- Kiểm soát boxing và kết quả trả về.
- Đo với input động và JMH.
- Phân tích chi phí end-to-end: method đích càng làm nhiều việc, tỉ lệ overhead reflection càng có thể ít quan trọng hơn.

## 17. Checklist khi review performance của Core Reflection

- [ ] Đã xác nhận đúng JDK runtime, vendor và phiên bản.
- [ ] Không dùng giả định về implementation reflection trước JDK 18.
- [ ] Không dùng cờ chuyển về triển khai cũ vốn đã bị loại bỏ từ JDK 22.
- [ ] Phân biệt chi phí lookup metadata với chi phí gọi/get/set.
- [ ] Đã kiểm tra `Method`/`Constructor`/`Field` được lưu tại đâu.
- [ ] Đã kiểm tra field `static final` có thật sự chứa metadata cố định.
- [ ] Không nhầm `static final Method[]` với các phần tử mảng immutable.
- [ ] Đã xét call site có một target hay nhiều target.
- [ ] Đã xét boxing, access checks, allocation và logic của method đích.
- [ ] Benchmark có warmup, forks và đầu ra được tiêu thụ.
- [ ] Đã thử trên workload ứng dụng, không chỉ microbenchmark.
- [ ] Cache không giữ class loader hoặc metadata vượt vòng đời cần thiết.
- [ ] Nếu dùng MethodHandle/VarHandle, đã kiểm tra lại hợp đồng kiểu và quyền truy cập.
- [ ] Không thay code đang dễ hiểu chỉ vì một chênh lệch nhỏ không ổn định.

## 18. Bài tập tự kiểm tra

1. Giải thích vì sao `static final Method` thường thuận lợi hơn một field mutable khi JIT muốn biết target của `invoke`.
2. Phân biệt compile-time constant của JLS với khả năng JIT constant-fold một object reference.
3. Với `static final Method[] methods`, chứng minh phần tử `methods[0]` vẫn có thể bị gán lại.
4. Tạo một class có `static final Constructor`, instance `Constructor` và mảng `Constructor[]`; chạy cùng một constructor và kiểm tra kết quả.
5. Thực hiện tương tự với `Field.getInt`; giải thích vì sao nên giữ cùng kiểu kết quả khi đo.
6. Tạo một registry `Map<String, Method>` chứa hai method và phân biệt cache lookup với target constant.
7. Biên dịch, chạy `ReflectionPlacementDemo` và xác nhận tất cả nhánh trả cùng kết quả chức năng.
8. Thiết kế JMH benchmark so sánh direct call, static final Method, instance Method và Method[]; xác định các biến cần giữ cố định.
9. Cho hai target thay đổi luân phiên tại một call site; so sánh với case chỉ dùng một target và giải thích ảnh hưởng của polymorphism.
10. Thử `Constructor.newInstance` trong JMH và giải thích vì sao escape analysis có thể làm kết quả khó diễn giải.
11. Viết một `static final MethodHandle` cho method public và gọi bằng `invokeExact`. Phân biệt exception type với reflection.
12. Giải thích vì sao một cache Method toàn cục có thể giữ class loader của plugin.
13. Đọc Oracle JDK 27 Migration Guide và giải thích vì sao không nên dùng cờ quay lại core reflection implementation cũ.
14. Dùng JMH với hai bản JDK hiện đang hỗ trợ trong dự án, ghi lại điều kiện đo và diễn giải sai số thay vì tuyên bố một tỷ lệ tăng tốc cố định.

**Tiêu chí hoàn thành:** bạn giải thích được mối quan hệ giữa **vị trí lưu reflection metadata → khả năng JIT nhận biết target → cơ hội tối ưu**, phân biệt cache lookup với JIT constant folding, biết giới hạn của `static final`/mảng/map, và thiết kế phép đo JMH có khả năng kiểm chứng trên JDK đang dùng.

## 19. Tài liệu tham khảo

- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): mục tiêu, thiết kế triển khai từ JDK 18 và các kết quả microbenchmark theo mức độ constant-fold của `Method`, `Constructor` và `Field`.
- [Oracle Java SE 27 — Package java.lang.reflect](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/package-summary.html): API công khai Core Reflection và mô hình member.
- [Oracle Java SE 27 — Method API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html): `Method.invoke`, contract kiểu/đối số/exception.
- [Oracle Java SE 27 — Constructor API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Constructor.html): `Constructor.newInstance` và contract tạo object.
- [Oracle Java SE 27 — Field API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Field.html): `Field.get`, `getInt` và các accessors.
- [Oracle Java SE 27 — MethodHandle API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html): typed handles, `invokeExact`, adaptation, access semantics.
- [Oracle Java SE 27 — VarHandle API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/VarHandle.html): typed accessors và variable access modes.
- [Oracle Java SE 27 — Removed Tools and Components](https://docs.oracle.com/en/java/javase/27/migrate/removed-tools-components.html): xác nhận implementation Core Reflection cũ đã bị loại bỏ từ JDK 22.
- [OpenJDK Code Tools — Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/): công cụ benchmark có warmup, measurement và forks.
- [Oracle Java Magazine — Reflection and MethodHandles on modern Java](https://blogs.oracle.com/javamagazine/java-reflection-method-handles/): bối cảnh JEP 416 và lưu ý tránh ngoại suy microbenchmark sang ứng dụng thật.
