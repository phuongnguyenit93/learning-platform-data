# Giá trị annotation trong Java: không phụ thuộc vào lớp proxy hoặc cách cài đặt nội bộ của JDK

Khi dùng Reflection để đọc annotation ở runtime, ta nhận được một đối tượng Java có thể gọi các element như `name()`, `value()` hoặc `timeout()`. Đối tượng đó có **kiểu API công khai** của annotation, nhưng **lớp cụ thể** mà JDK dùng để triển khai nó là chi tiết cài đặt. Code đáng tin cậy phải thao tác qua **kiểu annotation, `java.lang.annotation.Annotation` và `java.lang.reflect.AnnotatedElement`**, chứ không dựa vào tên class proxy, invocation handler, field riêng tư, hay cấu trúc nội bộ của một phiên bản JDK.

Bài này giải thích cách đọc, so sánh, chuyển đổi và kiểm thử **giá trị annotation** đúng theo hợp đồng chuẩn, đặc biệt là việc phân biệt `annotation.annotationType()` với `annotation.getClass()`.

## 1. Tình huống thực tế: đọc một annotation trên class

Giả sử ta khai báo annotation để mô tả cấu hình dịch vụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ServiceInfo {
    String name();
    int timeoutMs() default 1000;
}

@ServiceInfo(name = "payment", timeoutMs = 2500)
class PaymentService {
}
```

Khi dùng Reflection:

```java
ServiceInfo info =
        PaymentService.class.getDeclaredAnnotation(ServiceInfo.class);
```

`info` mang **hợp đồng của `ServiceInfo`**. Ta có thể gọi `info.name()` và `info.timeoutMs()`; không cần biết JDK đã dùng class nội bộ nào để tạo đối tượng này.

**Đừng suy luận** rằng đối tượng trả về luôn là một instance của class có tên cố định như `$Proxy1`, một class nằm trong package nội bộ nào đó hoặc một kiểu do ứng dụng tự tạo. Tài liệu chính thức của Java nêu rõ lớp hiện thực annotation là **implementation-dependent**; dùng `getClass()` để xác định *annotation type* vì thế không đúng mục đích.

Đây là vấn đề **tính tương thích**: chương trình không nên ngừng hoạt động chỉ vì thay JDK, module, trình biên dịch hoặc cách Reflection triển khai annotation mà vẫn giữ nguyên hợp đồng Java.

## 2. Phân biệt “annotation type” với “implementation class”

Hai câu lệnh sau **không có ý nghĩa giống nhau**:

```java
Class<? extends java.lang.annotation.Annotation> type =
        info.annotationType();

Class<?> implementation = info.getClass();
```

- `annotationType()` là phương thức của interface công khai `java.lang.annotation.Annotation`. Nó trả về **đúng interface annotation** được khai báo trong mã nguồn, ví dụ `ServiceInfo.class`.
- `getClass()` là phương thức `Object.getClass()` trả về **lớp thực tế của đối tượng khi chạy**. Với một annotation lấy bằng Reflection, lớp đó do JDK chọn, nên không phải cách ổn định để xác định annotation type.
- Tên hiển thị, package, các field và cấu trúc class triển khai không được coi là một phần của hợp đồng sử dụng annotation.

Cách kiểm tra ổn định:

```java
if (info != null && info.annotationType() == ServiceInfo.class) {
    System.out.println(info.name());
}
```

Cách kiểm tra sai về thiết kế:

```java
// Sai hướng tiếp cận (minh họa, không khuyến nghị):
// if (info.getClass().getName().contains("$Proxy")) { ... }
// String realType = info.getClass().getName();
// Object handler = java.lang.reflect.Proxy.getInvocationHandler(info);
```

Trong một bản JDK cụ thể, mã dựa vào `Proxy` có thể **tình cờ** chạy; điều đó không làm chi tiết proxy trở thành API bắt buộc cho mọi annotation. Ngoài ra, `Proxy.getInvocationHandler(...)` chỉ phù hợp khi đối tượng thực sự là dynamic proxy; dùng nó như điều kiện để xem một annotation có hợp lệ hay không là sai mục tiêu.

Quy tắc đơn giản: **muốn biết kiểu annotation → `annotationType()`; muốn biết các element → gọi phương thức của kiểu annotation; muốn biết annotation nào gắn vào khai báo → dùng API của `AnnotatedElement`.**

## 3. Các API công khai cần dùng

| Mục đích | API ổn định |
| --- | --- |
| Lấy annotation trực tiếp trên một class | `SomeClass.class.getDeclaredAnnotation(Config.class)` |
| Lấy annotation có mặt theo quy tắc Reflection (có thể xét kế thừa đối với class) | `SomeClass.class.getAnnotation(Config.class)` |
| Đọc tất cả annotation được khai báo trực tiếp | `element.getDeclaredAnnotations()` |
| Tìm các annotation có thể lặp, kể cả qua container | `element.getDeclaredAnnotationsByType(Config.class)` hoặc `getAnnotationsByType(...)` tùy nhu cầu |
| Xác định kiểu annotation thật sự | `annotation.annotationType()` |
| Đọc từng element | `config.name()`, `config.timeoutMs()`, `config.value()` |
| So sánh hai giá trị annotation theo nội dung | `a.equals(b)` |
| Dùng annotation làm khóa trong map/set | `equals()` kết hợp `hashCode()` theo hợp đồng chuẩn |

`Class`, `Field`, `Method`, `Constructor` và nhiều đối tượng Reflection khác hỗ trợ giao diện `AnnotatedElement`. Người dùng thư viện nên nhận một kiểu annotation cụ thể qua đối số `Class<A>` rồi gọi API chuẩn:

```java
static <A extends java.lang.annotation.Annotation> A read(
        java.lang.reflect.AnnotatedElement source, Class<A> annotationType) {
    return source.getDeclaredAnnotation(annotationType);
}
```

Đây là một **đoạn phương thức minh họa** cần đặt trong một class nếu muốn biên dịch; nó trả về `null` khi annotation không được khai báo trực tiếp. Không có thao tác nào vào proxy, module nội bộ hay field riêng tư.

### `getAnnotation` và `getDeclaredAnnotation` không hoàn toàn giống nhau

`getDeclaredAnnotation` chỉ xét annotation **trực tiếp** trên khai báo đang đọc. `getAnnotation` có thể bao gồm annotation kế thừa ở cấp class nếu annotation type được đánh dấu `@Inherited` và các quy tắc tương ứng áp dụng. Do đó, chọn API dựa trên **ngữ nghĩa cần tìm**, không dựa trên class triển khai của annotation.

Với annotation `@Repeatable`, API `getAnnotationsByType` và `getDeclaredAnnotationsByType` hỗ trợ nhìn qua container. Việc lặp annotation là đặc điểm **ngôn ngữ/API**, không phải công việc của một proxy tự tạo mà code ứng dụng cần mở ra để đọc.

## 4. Ví dụ Java 17+ hoàn chỉnh: chỉ dùng hợp đồng công khai

Ví dụ sau cho thấy hai khai báo chứa annotation **tương đương về giá trị**, kể cả khi một khai báo dùng giá trị mặc định và khai báo kia ghi giá trị tường minh. Chương trình chỉ dựa vào hợp đồng `Annotation` và các phương thức phần tử.

Tạo file **`AnnotationContractDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.Objects;

enum Mode {
    PROD, DEV
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ServiceConfig {
    String name();
    int[] ports() default {8080, 8443};
    Mode mode() default Mode.PROD;
}

@ServiceConfig(name = "gateway")
class GatewayOne {
}

@ServiceConfig(name = "gateway", ports = {8080, 8443}, mode = Mode.PROD)
class GatewayTwo {
}

@ServiceConfig(name = "worker", ports = {9000}, mode = Mode.DEV)
class WorkerService {
}

public class AnnotationContractDemo {
    static ServiceConfig readConfig(Class<?> type) {
        return Objects.requireNonNull(
                type.getDeclaredAnnotation(ServiceConfig.class),
                () -> "Missing @ServiceConfig on " + type.getName()
        );
    }

    public static void main(String[] args) {
        ServiceConfig first = readConfig(GatewayOne.class);
        ServiceConfig second = readConfig(GatewayTwo.class);
        ServiceConfig other = readConfig(WorkerService.class);

        System.out.println("annotationType=" +
                first.annotationType().getSimpleName());
        System.out.println("name=" + first.name());
        System.out.println("ports=" + Arrays.toString(first.ports()));
        System.out.println("mode=" + first.mode());

        System.out.println("sameValues=" + first.equals(second));
        System.out.println("sameHash=" +
                (first.hashCode() == second.hashCode()));
        System.out.println("differentValues=" + !first.equals(other));
    }
}
```

Biên dịch và chạy trong thư mục chứa file bằng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 AnnotationContractDemo.java
java AnnotationContractDemo
```

**Stdout:**

```text
annotationType=ServiceConfig
name=gateway
ports=[8080, 8443]
mode=PROD
sameValues=true
sameHash=true
differentValues=true
```

Giải thích:

1. `readConfig` lấy annotation bằng `Class.getDeclaredAnnotation(ServiceConfig.class)`, sau đó báo lỗi rõ ràng nếu khai báo không có annotation. Không cần cast từ class proxy.
2. `first.annotationType().getSimpleName()` trả `"ServiceConfig"`, tên của annotation type thực sự. Nó **không** phụ thuộc tên class hiện thực tại runtime.
3. `first.name()` trả `"gateway"`. `first.ports()` là mảng `int[]`, nên chương trình dùng `Arrays.toString(...)` để in nội dung thay vì in định danh mảng.
4. `GatewayOne` dùng giá trị mặc định của `ports` và `mode`; `GatewayTwo` ghi đúng các giá trị ấy một cách tường minh. Theo hợp đồng `Annotation.equals`, hai annotation có cùng loại và giá trị của mọi element nên **tương đương**.
5. Nếu hai annotation tương đương thì `hashCode()` của chúng phải bằng nhau theo hợp đồng. Vì vậy `sameHash=true`, dù chương trình không biết class triển khai cụ thể.
6. `WorkerService` có các element khác, do đó `!first.equals(other)` là `true`.

Ví dụ **không in `first.getClass().getName()`**, không dùng `Proxy` và cũng không giả định `first` và `second` có cùng tham chiếu (`==`). Kết quả chỉ phụ thuộc API công khai và giá trị khai báo.

## 5. So sánh annotation phải dựa trên giá trị, không dựa trên danh tính

Annotation là **metadata có giá trị**, không phải một mô hình domain object được ứng dụng quản lý bằng danh tính tham chiếu. Gọi Reflection nhiều lần có thể trả về đối tượng có danh tính giống nhau hoặc khác nhau tùy cơ chế hiện thực; ứng dụng không nên dùng điều đó làm hợp đồng.

Cách so sánh đúng:

```java
boolean same = first.equals(second);
```

Không dùng:

```java
// Không biểu thị tương đương nội dung:
// boolean same = first == second;
```

Theo Javadoc của `java.lang.annotation.Annotation`, hai annotation tương đương khi:

- Chúng cùng **annotation type**.
- Mọi element tương ứng có **giá trị tương đương**.
- Với phần tử kiểu nguyên thủy, quy tắc so sánh theo kiểu tương ứng (đặc biệt `float` và `double` tuân theo `Float.equals`/`Double.equals`, không đơn thuần theo toán tử `==`).
- Với `String`, `Class`, enum hoặc nested annotation, so sánh theo `equals`.
- Với phần tử mảng, so sánh **nội dung mảng** bằng phép so sánh tương ứng của `Arrays.equals`, không so sánh hai tham chiếu mảng.

Cụ thể, trong ví dụ, `ports` có kiểu `int[]`. Hai mảng `new int[]{8080, 8443}` và `new int[]{8080, 8443}` thông thường là hai object khác nhau, nhưng `Arrays.equals` cho kết quả `true`. Vì thế `@ServiceConfig(ports = {8080, 8443})` và giá trị mặc định `{8080, 8443}` tương đương về mặt element.

### Hash code và sử dụng trong collection

Hợp đồng `Annotation.hashCode()` được Javadoc quy định theo từng element. Với mỗi cặp element tên `name` và giá trị `value`, contribution có dạng:

```text
(127 * name.hashCode()) XOR valueHashCode
```

Hash code toàn annotation là tổng các contribution ấy; phần giá trị mảng sử dụng `Arrays.hashCode` tương ứng, còn annotation lồng nhau sử dụng hash code của chính nó. **Không cần tự tính công thức này** trong ứng dụng: chỉ cần gọi `annotation.hashCode()`.

Nếu sử dụng annotation làm khóa `HashMap` hoặc phần tử `HashSet`, hãy dựa vào `equals`/`hashCode` như với các value object. Tuy nhiên, trong code cấu hình nghiệp vụ dài hạn, thường nên **chuyển các element sang một kiểu dữ liệu domain** rõ ràng thay vì để annotation object trở thành dependency tràn khắp các tầng ứng dụng.

## 6. `toString()` chỉ để quan sát, không phải định dạng dữ liệu ổn định

Ví dụ:

```java
String debug = first.toString();
```

Javadoc cho phép tạo một biểu diễn dạng chuỗi của annotation, thường gần với cú pháp annotation trong source. **Chi tiết chuỗi biểu diễn là implementation-dependent**. Những yếu tố như tên đầy đủ, thứ tự element, dấu ngoặc, dấu cách hoặc cách in mảng không nên trở thành hợp đồng lưu trữ hay giao tiếp giữa hệ thống.

Các thao tác cần tránh:

```java
// Ví dụ anti-pattern:
// String saved = first.toString();
// String name = saved.substring(saved.indexOf("name=") + 5);
// boolean gateway = first.toString().contains("gateway");
```

Những cách này dễ hỏng khi định dạng `toString()` thay đổi hoặc khi chuỗi giá trị chứa dấu phẩy, ngoặc, dấu nháy và escape.

Nếu cần JSON, YAML, log có cấu trúc hoặc so sánh bền vững, hãy lấy **element** bằng phương thức public rồi chuyển chúng sang kiểu dữ liệu thích hợp:

```java
String name = first.name();
int[] ports = first.ports();
Mode mode = first.mode();
```

Sau đó serializer của hệ thống tự định nghĩa trường và định dạng. Đừng dùng `toString()` của object annotation làm serialization protocol.

## 7. Không mở lớp proxy và các package nội bộ để lấy “giá trị thật”

Một số bản triển khai có thể cung cấp annotation runtime thông qua cơ chế dynamic proxy. Nhưng việc một bản JDK dùng proxy **không trao quyền bảo đảm** rằng:

- Mọi annotation của mọi JDK đều là một dynamic proxy cùng hình dạng.
- Tên class có hậu tố `$ProxyN` hoặc package cố định.
- Invocation handler có một field với tên và kiểu nhất định.
- Có thể đọc một map nội bộ chứa giá trị bằng `setAccessible(true)` mà không bị hạn chế module.
- Một lần gọi `getAnnotation` trả đúng cùng object về mặt tham chiếu ở mọi lần chạy.

Đặc biệt, các package như `sun.reflect.annotation` là **API nội bộ**, không phải hợp đồng Java SE cho ứng dụng. JPMS/module access có thể chặn reflection vào thành viên không được mở của JDK, và ngay cả khi truy cập thành công, code sẽ phụ thuộc layout nội bộ không được bảo đảm ổn định.

Đoạn dưới là **anti-pattern để nhận diện, không phải code nên chạy**:

```java
// Không viết logic nghiệp vụ phụ thuộc các thao tác sau:
// String implementationName = config.getClass().getName();
// java.lang.reflect.InvocationHandler h =
//         java.lang.reflect.Proxy.getInvocationHandler(config);
// h.getClass().getDeclaredField("memberValues").setAccessible(true);
```

Thay vì vậy:

```java
String name = config.name();
int[] ports = config.ports();
Class<? extends java.lang.annotation.Annotation> type =
        config.annotationType();
```

Nếu cần viết thư viện dùng chung cho **nhiều loại annotation**, có thể đọc các phương thức element từ chính annotation type bằng API Reflection chuẩn như `annotation.annotationType().getDeclaredMethods()`. Nhưng nên sử dụng giải pháp generic ấy **chỉ khi cần**; với một kiểu annotation đã biết, gọi `config.name()` ngắn gọn, có kiểm tra kiểu tĩnh và dễ bảo trì hơn.

Không được nhầm `getDeclaredMethods()` của **annotation type** với `getDeclaredMethods()` của **implementation class**. Chỉ bên thứ nhất mô tả phần element public thuộc hợp đồng annotation.

## 8. Khi cần duyệt element một cách tổng quát

Một framework có thể nhận `Annotation` bất kỳ và muốn liệt kê **tên/giá trị element** mà không biết kiểu ở thời điểm biên dịch. Có thể làm qua annotation interface:

```java
import java.lang.annotation.Annotation;
import java.lang.reflect.Method;
import java.lang.reflect.InvocationTargetException;

public final class AnnotationReader {
    private AnnotationReader() {
    }

    public static void printElements(Annotation annotation) {
        Class<? extends Annotation> type = annotation.annotationType();

        for (Method element : type.getDeclaredMethods()) {
            try {
                Object value = element.invoke(annotation);
                System.out.println(element.getName() + "=" + value);
            } catch (IllegalAccessException | InvocationTargetException ex) {
                throw new IllegalStateException(
                        "Cannot read @" + type.getName(), ex
                );
            }
        }
    }
}
```

Đây là **một class hỗ trợ minh họa độc lập**, không phải chương trình chạy `main`, và có hạn chế quan trọng: với element kiểu mảng, `System.out.println(value)` không cho nội dung mảng dễ đọc; cần dùng `Arrays.toString` hoặc `Arrays.deepToString` theo đúng kiểu. Thứ tự trả về của `getDeclaredMethods()` cũng **không được bảo đảm**, nên không được dựa vào thứ tự in để tạo giao thức lưu trữ hoặc kết quả kiểm thử.

Ví dụ `AnnotationReader` chỉ truy vấn **annotation interface** và gọi **phương thức element được khai báo công khai**, không khám phá private field của implementation. Đó là sự khác nhau giữa Reflection công khai đúng hợp đồng và reflection vào cấu trúc JDK nội bộ.

Nếu thư viện cần dữ liệu có thứ tự xác định, hãy sắp xếp `Method` theo `getName()` trước khi xử lý. Nếu cần chuyển thành DTO, cần tự xử lý các giá trị hợp lệ của annotation: primitive/wrapper, `String`, `Class`, enum, nested annotation và mảng một chiều của những loại này.

Trong trường hợp thuộc tính có kiểu `Class<?>`, việc đọc annotation có thể kéo theo quá trình phân giải type. Nếu class được tham chiếu không tồn tại ở runtime hoặc metadata không còn tương thích, việc đọc element có thể phát sinh exception đặc biệt; đọc annotation không phải luôn là một thao tác không thể thất bại.

## 9. Mảng annotation và giá trị bất biến

Một element annotation có thể trả `String[]`, `int[]`, `Class<?>[]`, enum array hoặc mảng nested annotation. Mảng là đối tượng **có thể thay đổi phần tử** trong Java, nên ứng dụng phải thận trọng khi truyền chúng ra ngoài:

```java
int[] snapshot = first.ports().clone();
snapshot[0] = 9001; // Chỉ thay đổi bản copy do ứng dụng tạo.
System.out.println(Arrays.toString(snapshot));
```

Code trên dùng `Arrays` trong ví dụ hoàn chỉnh của mục 4 và minh họa cách tạo **bản sao riêng để chỉnh sửa**, không hàm ý annotation itself là nơi nên lưu state mutable. Thay đổi các phần tử trong `snapshot` không thay đổi giá trị khai báo trên `@ServiceConfig`.

Đừng viết logic nhận dạng annotation bằng địa chỉ của mảng:

```java
// Không đúng để so sánh nội dung:
// boolean samePorts = first.ports() == second.ports();
```

Muốn kiểm tra nội dung hai mảng, dùng:

```java
boolean samePorts =
        java.util.Arrays.equals(first.ports(), second.ports());
```

Nếu muốn so sánh **toàn bộ** annotation, không cần so sánh từng element thủ công: `first.equals(second)` đã có hợp đồng rõ ràng, kể cả xử lý mảng. Khi ánh xạ ra domain object, nên bảo vệ các mảng mutable bằng bản sao phù hợp.

## 10. Khi annotation không tồn tại hoặc không có retention phù hợp

API `getAnnotation` hoặc `getDeclaredAnnotation` có thể trả `null`. Trường hợp thường gặp:

- Khai báo không gắn annotation ấy.
- Annotation có `@Retention(SOURCE)`, nên không còn sau biên dịch.
- Annotation có `@Retention(CLASS)` (mặc định nếu không có `@Retention`), nên không thể lấy qua Reflection runtime thông thường.
- Tìm trực tiếp trên class con bằng `getDeclaredAnnotation` trong khi annotation chỉ nằm trên superclass.
- Dùng `getAnnotation` để tìm một annotation kiểu repeatable nhưng thực tế có nhiều annotation được chứa trong **container**; lúc này `getAnnotationsByType` phù hợp hơn.

Với code ứng dụng cần Reflection runtime, khai báo annotation cần có `@Retention(RetentionPolicy.RUNTIME)`.

Một cách sử dụng an toàn khi annotation không bắt buộc:

```java
ServiceConfig config =
        SomeClass.class.getDeclaredAnnotation(ServiceConfig.class);

if (config == null) {
    // Không có metadata trên đúng khai báo được hỏi.
} else {
    String name = config.name();
}
```

Đây là snippet **minh họa**, cần thay `SomeClass` bằng kiểu thật và đặt trong method. Đừng tự coi `null` là bằng chứng “JDK đổi tên proxy”: đó là vấn đề có mặt của metadata, retention, target hoặc lựa chọn API truy vấn.

### Metadata không còn tương thích

Trong hệ thống có module, classloader hoặc thư viện được nâng cấp độc lập, annotation type có thể thay đổi trong khi những class file được biên dịch trước vẫn còn. Các tình huống này có thể dẫn đến lỗi khi truy cập giá trị:

- `IncompleteAnnotationException`: annotation thiếu element bắt buộc so với định nghĩa đang nạp.
- `AnnotationTypeMismatchException`: giá trị trong metadata không còn tương thích với kiểu phần tử của annotation hiện tại.
- `EnumConstantNotPresentException`: enum constant được tham chiếu trong annotation không còn.
- `TypeNotPresentException`: kiểu `Class` được tham chiếu trong annotation không còn sẵn để phân giải.

Giải pháp thông thường là kiểm tra và đồng bộ phiên bản dependency, sau đó biên dịch lại mã liên quan; **không** truy cập private map của annotation implementation để “sửa” metadata hỏng. Khi xử lý reflection tại ranh giới plugin hoặc ứng dụng, nên bắt và báo đúng lỗi tương thích thay vì nuốt mọi exception rồi giả định metadata rỗng.

## 11. Phụ thuộc đúng lớp API khi thiết kế kiến trúc

Một hệ thống dùng annotation tốt thường có ba lớp trách nhiệm:

```text
Java declaration
    ↓  Reflection API: AnnotatedElement.get...Annotation(...)
Annotation interface + element values
    ↓  Chuyển sang DTO/domain model riêng
Cấu hình đã kiểm chứng: name, ports, mode
    ↓
Business logic: khởi tạo, kiểm tra, định tuyến, v.v.
```

Ví dụ, thay vì chuyển trực tiếp `ServiceConfig` sâu vào tầng xử lý, có thể tạo bản ghi cấu hình:

```java
record ServiceSettings(String name, int[] ports, Mode mode) {
    ServiceSettings {
        ports = ports.clone();
    }

    @Override
    public int[] ports() {
        return ports.clone();
    }
}
```

Đây là **ví dụ minh họa record Java 17**, có thể dùng trong cùng package với `Mode` của ví dụ chính. Bản ghi tạo bản sao phòng vệ cho mảng để tránh việc code bên ngoài thay đổi ngầm phần tử mảng trong cấu hình.

Có thể ánh xạ dữ liệu từ annotation:

```java
ServiceSettings settings = new ServiceSettings(
        config.name(),
        config.ports(),
        config.mode()
);
```

Ở đây `config` là biến `ServiceConfig` đã đọc được; không phải một chương trình độc lập với `main`.

Khi đã chuyển sang `ServiceSettings`, các tầng nghiệp vụ không cần biết đối tượng `ServiceConfig` được JDK xây dựng như thế nào. Việc tách biệt giúp unit test đơn giản hơn và giảm độ phụ thuộc vào Reflection.

## 12. Kiểm thử theo hành vi thay vì implementation

Nên kiểm thử bằng những điều public API **cam kết**:

- `annotation.annotationType() == ServiceConfig.class`.
- `annotation.name().equals("gateway")`.
- `Arrays.equals(annotation.ports(), new int[]{8080, 8443})`.
- `annotation.mode() == Mode.PROD`.
- Hai annotation cùng kiểu và cùng giá trị element thì `equals()` trả `true`; hash code cũng tương đương.
- Khi thiếu annotation, `getDeclaredAnnotation` trả `null` và ứng dụng xử lý đúng.
- Khi cần hỗ trợ annotation lặp, `getDeclaredAnnotationsByType()` trả tập giá trị theo quy tắc API.

Không nên viết test khẳng định:

```java
// Không nên:
// assertTrue(annotation.getClass().getName().startsWith("com.sun.proxy"));
// assertEquals("...", annotation.toString());
// assertSame(annotation1, annotation2);
```

Những test này ràng buộc vào chi tiết class triển khai, định dạng chuỗi không ổn định hoặc danh tính đối tượng. Một dự án có thể vượt qua trên một phiên bản JDK và thất bại trên bản khác dù dữ liệu annotation và hợp đồng public không thay đổi.

Nên chạy test ít nhất trên những JDK mà ứng dụng công bố hỗ trợ; khi thất bại, ưu tiên kiểm tra `@Retention`, import, classpath/module path, sự hiện diện của metadata và kiểu/trị của element.

## 13. Những lỗi dễ gặp

| Cách làm | Vấn đề | Thay thế |
| --- | --- | --- |
| `annotation.getClass() == ServiceConfig.class` | So sánh class triển khai với annotation interface; không đúng hợp đồng. | `annotation.annotationType() == ServiceConfig.class`. |
| Đọc class name chứa `$Proxy` | Tên implementation-dependent. | Dùng `annotationType()` hoặc `instanceof` với interface annotation cần dùng. |
| Dùng `Proxy.getInvocationHandler()` để tìm giá trị | Phụ thuộc cơ chế proxy và handler nội bộ. | Gọi `annotation.name()` / `annotation.value()`. |
| Truy cập `sun.reflect.annotation.*` | API nội bộ không được bảo đảm ổn định. | Dùng `java.lang.annotation` và `java.lang.reflect` công khai. |
| Tìm field tên `memberValues` rồi `setAccessible(true)` | Layout private có thể thay đổi và JPMS có thể chặn. | Dùng phương thức element của annotation interface. |
| `a == b` để so sánh hai annotation | Kiểm tra tham chiếu object, không phải giá trị annotation. | `a.equals(b)`. |
| `a.ports() == b.ports()` | Mảng dùng equality tham chiếu. | `Arrays.equals(...)` hoặc so sánh `a.equals(b)`. |
| Parse `annotation.toString()` | Chuỗi không có format được bảo đảm. | Đọc từng element rồi serialize thành định dạng riêng. |
| `getAnnotation` trả `null` thì tự đoán proxy lỗi | Có thể do thiếu annotation hoặc retention không phải `RUNTIME`. | Kiểm tra khai báo, retention, target, API query và classpath. |
| Dùng `getAnnotations()` để tìm đủ annotation repeatable | Có thể chỉ thấy container. | `getAnnotationsByType(...)` hoặc bản `Declared` tương ứng. |
| Reflection vào class hiện thực để liệt kê element | Lẫn implementation methods với hợp đồng annotation. | `annotation.annotationType().getDeclaredMethods()`. |

## 14. Tự kiểm tra

1. `cfg.getClass()` và `cfg.annotationType()` có bảo đảm bằng nhau không? **Không**: một bên là lớp thực thi runtime, một bên là annotation interface. Dùng `annotationType()` khi cần xác định loại annotation.
2. Hai class khác nhau đều có `@ServiceConfig` với cùng giá trị mọi element, thì các annotation trả về có thể `equals()` bằng nhau không? **Có**: `equals` so nội dung annotation, không phải class mang annotation.
3. Tại sao không dùng `cfg.toString()` để lưu cấu hình? **Vì cách biểu diễn chuỗi là chi tiết cài đặt**, không phải định dạng serialization ổn định.
4. Mảng `int[]` trả về bởi `cfg.ports()` nên so sánh với mảng khác bằng gì? **`Arrays.equals`**, hoặc dùng `cfg.equals(otherCfg)` nếu so toàn bộ annotation.
5. Muốn liệt kê tên các element annotation tổng quát thì Reflection trên class nào? **`cfg.annotationType().getDeclaredMethods()`**, không phải class mà `cfg.getClass()` trả về.
6. `getDeclaredAnnotation` trả `null` thì nên làm gì đầu tiên? **Kiểm tra annotation có thật sự trực tiếp gắn tại nơi đọc và có `@Retention(RUNTIME)` hay không**, thay vì truy cập internals.
7. Có được viết thư viện Java dùng `Proxy.getInvocationHandler(cfg)` như phương tiện chuẩn để đọc annotation không? **Không nên**; dùng các element và API công khai.
8. Vì sao việc chuyển annotation sang DTO giúp hệ thống bền vững? **Business logic phụ thuộc dữ liệu có kiểu rõ ràng thay vì object Reflection hoặc implementation-specific class**.

Tài liệu chuẩn: [Java SE 17 – `java.lang.annotation.Annotation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html) (đặc biệt ghi chú về `annotationType()`, `equals`, `hashCode` và `toString`); [Java SE 17 – `java.lang.reflect.AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html). Các hợp đồng công khai này là cơ sở thiết kế code không phụ thuộc proxy hoặc chi tiết JDK nội bộ.
