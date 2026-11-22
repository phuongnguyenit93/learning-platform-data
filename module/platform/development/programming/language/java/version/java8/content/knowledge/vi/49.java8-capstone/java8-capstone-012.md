# Xây annotation, đọc metadata và kiểm tra hợp đồng kiểu trong Java

## 1. Annotation là metadata có cấu trúc

Annotation cho phép gắn thông tin có kiểu vào declaration hoặc vị trí sử dụng kiểu trong Java. Compiler, annotation processor, framework hoặc chương trình dùng reflection có thể đọc metadata đó để kiểm tra quy ước, tạo mã, cấu hình dependency injection, mapping dữ liệu, routing hoặc validation.

Một annotation **không tự thay đổi hành vi của method hay kiểm tra dữ liệu**. Ví dụ, `@NonNull` do ứng dụng tự định nghĩa không tự ngăn `null`; cần static analyzer, annotation processor hoặc runtime validator hiểu và thực thi quy ước đó.

Bài này đi qua quy trình đầy đủ:

1. Thiết kế annotation: element hợp lệ, retention, target, default và annotation lặp.
2. Đọc metadata lúc runtime bằng reflection, kể cả generic type và type-use annotation.
3. Kiểm tra hợp đồng method và kiểu dữ liệu ở runtime.
4. Dùng annotation processor để phát hiện khai báo sai ngay trong lúc compile.
5. Chọn đúng cơ chế theo yêu cầu, hiểu giới hạn type erasure và module encapsulation.

Ví dụ dùng annotation/reflection APIs hiện hành, tương thích nền tảng Java 8+ ở phần API cốt lõi. Các chương trình minh họa đã được biên dịch và chạy bằng JDK 24. Ví dụ processor dùng `Set.of` nên cần JDK 9+; toàn bộ phần code có thể chạy bằng JDK 17+.

## 2. Khai báo annotation riêng

Cú pháp cơ bản:

```java
public @interface Audit {
    String value();
    String actor() default "system";
}
```

`@interface` khai báo một annotation type. Các method bên trong là **annotation elements**; chúng không có tham số và không khai báo `throws`. Khi sử dụng, caller cung cấp giá trị cho element bắt buộc:

```java
@Audit(value = "invoice.create", actor = "billing-service")
public void createInvoice() {
    // ...
}
```

Nếu annotation chỉ có một element tên `value`, có thể viết ngắn:

```java
@Audit("invoice.create")
public void createInvoice() {
    // ...
}
```

Nếu một element có `default`, caller được phép bỏ qua nó. Giá trị default được lấy từ định nghĩa annotation, không phải giá trị compiler tự suy ra từ context.

### 2.1. Kiểu dữ liệu được phép trong annotation element

Kiểu trả về của annotation element bị giới hạn ở:

- Primitive: `byte`, `short`, `int`, `long`, `float`, `double`, `char`, `boolean`.
- `String`.
- `Class` hoặc `Class<?>`.
- Enum.
- Một annotation type khác.
- Mảng một chiều của các kiểu được phép ở trên.

Không thể dùng `List<String>`, `Map`, kiểu generic tùy ý hoặc object runtime làm annotation element. Annotation được thiết kế như metadata khai báo, có thể lưu trong class file.

Ví dụ:

```java
public @interface Endpoint {
    String path();
    Class<?> handler();
    HttpMethod method() default HttpMethod.GET;
    String[] roles() default {};
}
```

`HttpMethod` phải là enum; `handler` nhận class literal như `InvoiceHandler.class`. Annotation element không thể là `new InvoiceHandler()`.

### 2.2. Giá trị annotation phải ổn định

Giá trị annotation thường là literal, enum constant, class literal, annotation lồng nhau hoặc mảng các giá trị hợp lệ. Không gọi hàm để tính giá trị annotation khi runtime.

```java
@Endpoint(
    path = "/invoices",
    handler = InvoiceHandler.class,
    method = HttpMethod.POST,
    roles = {"billing.write", "admin"}
)
class InvoiceController {
}
```

Khi đọc annotation, nếu element có default, accessor trả về default đó. Không cần tự kiểm tra caller đã viết element hay chưa nếu logic chỉ quan tâm giá trị cuối cùng.

## 3. Retention: metadata tồn tại đến khi nào?

`@Retention` quyết định annotation được giữ ở giai đoạn nào:

| Retention | Nơi tồn tại | Reflection runtime |
| --- | --- | --- |
| `SOURCE` | Mã nguồn trong lúc compile | Không đọc được từ class đã biên dịch |
| `CLASS` | Class file | Không được reflection runtime thông thường trả về |
| `RUNTIME` | Class file và runtime | Đọc được bằng reflection |

Nếu không khai báo `@Retention`, mặc định là `CLASS`. Hãy khai báo rõ retention để người dùng annotation biết framework có thể đọc nó ở giai đoạn nào.

**`SOURCE`** phù hợp với metadata chỉ phục vụ compiler hoặc annotation processor. Sau compile, runtime không cần giữ annotation đó.

**`CLASS`** phù hợp khi metadata cần được lưu trong bytecode nhưng không cần reflection runtime. Công cụ bytecode có thể đọc thông tin này.

**`RUNTIME`** cần thiết khi framework/application đọc annotation bằng reflection, ví dụ routing, dependency injection, validation hoặc serialization.

Không chọn `RUNTIME` theo thói quen cho mọi annotation. Metadata runtime có thể làm tăng kích thước class file và chi phí đọc/khởi tạo framework; chọn theo nhu cầu thật.

### 3.1. Annotation SOURCE vẫn dùng được trong processor

Annotation processor có thể đọc annotation `SOURCE` trong các processing rounds trước khi compiler hoàn tất. `SOURCE` không có nghĩa processor không nhìn thấy annotation; nó có nghĩa metadata không cần được giữ trong class file sau compile.

Ví dụ annotation runtime trên field:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ConfigKey {
    String value();
}
```

## 4. Target: annotation được đặt ở đâu?

`@Target` giới hạn vị trí annotation được sử dụng. Những `ElementType` thường gặp:

| ElementType | Vị trí |
| --- | --- |
| `TYPE` | Class, interface, enum, annotation type |
| `FIELD` | Field, bao gồm enum constant |
| `METHOD` | Method |
| `PARAMETER` | Parameter của method/constructor |
| `CONSTRUCTOR` | Constructor |
| `LOCAL_VARIABLE` | Local variable |
| `ANNOTATION_TYPE` | Một annotation type khác |
| `PACKAGE` | Package declaration |
| `MODULE` | Module declaration |
| `TYPE_PARAMETER` | Khai báo type parameter, ví dụ `<@Marker T>` |
| `TYPE_USE` | Vị trí sử dụng kiểu, gồm generic argument, array component, cast... |
| `RECORD_COMPONENT` | Record component (Java 16+) |

Nếu không khai báo `@Target`, annotation có thể được dùng ở nhiều declaration context theo quy tắc ngôn ngữ. Với annotation API dùng chung, khai báo target cụ thể giúp compiler bắt lỗi đặt sai chỗ.

### 4.1. Declaration annotation và type-use annotation khác nhau

Declaration annotation mô tả declaration:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Sensitive {
}

class Account {
    @Sensitive
    String accessToken;
}
```

Type-use annotation mô tả vị trí sử dụng một kiểu:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {
}

class Account {
    java.util.List<@NonNull String> roles;
}
```

Trong ví dụ thứ hai, `@NonNull` gắn với kiểu phần tử `String` bên trong `List`. Nó không tự kiểm tra nội dung list; code hoặc công cụ khác phải đọc metadata và áp dụng quy tắc.

### 4.2. TYPE_PARAMETER và TYPE_USE không giống nhau

```java
@Target(ElementType.TYPE_PARAMETER)
@interface StableTypeParameter {
}

@Target(ElementType.TYPE_USE)
@interface NonNullType {
}

class Box<@StableTypeParameter T> {
    @NonNullType T value;
}
```

`TYPE_PARAMETER` đánh dấu **khai báo biến kiểu T**. `TYPE_USE` đánh dấu **vị trí dùng kiểu T**. Một annotation có thể hỗ trợ cả hai target nếu thiết kế yêu cầu, nhưng không nên gộp hai nghĩa nếu consumer cần phân biệt.

## 5. Meta-annotations thường dùng

Meta-annotation là annotation dùng để mô tả chính annotation type.

### 5.1. @Documented

`@Documented` yêu cầu Javadoc đưa annotation vào tài liệu API được tạo. Nó hữu ích cho annotation mà người dùng thư viện cần nhìn thấy trong contract công khai.

### 5.2. @Inherited

`@Inherited` cho phép annotation gắn trên class được kế thừa khi đọc annotation trên subclass bằng `getAnnotation()`/`getAnnotations()`.

Giới hạn rất quan trọng:

- Chỉ áp dụng cho annotation target `TYPE`.
- Chỉ theo chuỗi superclass.
- Không kế thừa annotation từ interface.
- Không làm annotation trên method, field, parameter hay constructor tự kế thừa.
- `getDeclaredAnnotation()` chỉ đọc annotation khai báo trực tiếp trên class hiện tại.

Đừng nhầm `@Inherited` với quy tắc override method. Khi subclass override một method, annotation trên method cha không tự động xuất hiện trên method con.

### 5.3. @Repeatable

`@Repeatable` cho phép dùng một annotation nhiều lần trên cùng một element. Cần khai báo annotation container chứa mảng annotation lặp.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}

@Label("domain")
@Label("audited")
class InvoiceService {
}
```

Target và retention của container cần tương thích với annotation lặp; container phải có element `value()` trả về mảng annotation tương ứng.

Khi đọc annotation lặp, ưu tiên `getAnnotationsByType(Label.class)` hoặc `getDeclaredAnnotationsByType(...)`. Không chỉ gọi `getAnnotation(Labels.class)` vì cách đó phụ thuộc representation/container.

### 5.4. @Native

`@Native` đánh dấu field constant được dùng trong native code. Đây là annotation chuyên biệt cho tương tác Java/native; không dùng nó như annotation đánh dấu constant thông thường.

## 6. Ví dụ 1 — thiết kế annotation, kế thừa và annotation lặp

**AnnotationBasicsDemo.java**

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;
import java.util.Arrays;

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Component {
    String value();
}

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Labels {
    Label[] value();
}

@Component("billing")
@Label("domain")
@Label("audited")
class BaseHandler {
}

class ChildHandler extends BaseHandler {
}

public class AnnotationBasicsDemo {
    public static void main(String[] args) {
        Component inherited =
            ChildHandler.class.getAnnotation(Component.class);

        Label[] labels =
            BaseHandler.class.getAnnotationsByType(Label.class);

        System.out.println("inheritedComponent=" + inherited.value());
        System.out.println(
            "repeatableLabels=" +
            Arrays.toString(
                Arrays.stream(labels)
                    .map(Label::value)
                    .toArray(String[]::new)
            )
        );
        System.out.println("labelCount=" + labels.length);
    }
}
```

Chạy:

```bash
javac AnnotationBasicsDemo.java
java AnnotationBasicsDemo
```

Stdout:

```text
inheritedComponent=billing
repeatableLabels=[domain, audited]
labelCount=2
```

`Component` được tìm thấy trên subclass vì nó có `@Inherited`. Hai `Label` được đọc thành một mảng theo thứ tự khai báo. Nếu gọi `ChildHandler.class.getDeclaredAnnotation(Component.class)`, kết quả là `null` vì subclass không tự khai báo annotation đó.

## 7. Đọc annotation bằng reflection

Các API reflection cốt lõi nằm trong `java.lang.reflect` và `java.lang.Class`. Nhiều đối tượng reflection triển khai `AnnotatedElement`, cho phép đọc annotation từ class, field, method, constructor, parameter và package.

| API | Ý nghĩa |
| --- | --- |
| `getAnnotation(A.class)` | Đọc annotation có thể được kế thừa theo quy tắc annotation |
| `getDeclaredAnnotation(A.class)` | Chỉ đọc annotation khai báo trực tiếp |
| `getAnnotations()` | Annotation nhìn thấy theo quy tắc của element |
| `getDeclaredAnnotations()` | Annotation khai báo trực tiếp |
| `getAnnotationsByType(A.class)` | Đọc annotation lặp, kể cả qua container |
| `getDeclaredAnnotationsByType(A.class)` | Annotation lặp khai báo trực tiếp |
| `getDeclaredFields()` | Field khai báo trực tiếp trên class |
| `getDeclaredMethods()` | Method khai báo trực tiếp trên class |
| `getDeclaredConstructors()` | Constructor khai báo trực tiếp trên class |

`getFields()` và `getMethods()` có thể bao gồm member public kế thừa; `getDeclaredFields()` và `getDeclaredMethods()` chỉ trả member được khai báo trong class đang đọc. Chọn API theo phạm vi framework cần quét.

### 7.1. Đọc metadata field và method

```java
Field field = Settings.class.getDeclaredField("port");
ConfigKey configKey = field.getAnnotation(ConfigKey.class);

Method method = Settings.class.getDeclaredMethod(
    "endpoints", String.class, int.class
);

System.out.println(configKey.value());
System.out.println(method.getReturnType());
System.out.println(method.getParameterCount());
```

`getReturnType()` trả raw class. Nếu cần biết generic return type như `List<String>`, hãy dùng `getGenericReturnType()`.

### 7.2. Ví dụ 2 — đọc metadata declaration và generic signature

**ReflectionMetadataDemo.java**

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.util.Arrays;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface SettingKey {
    String value();
}

class AppSettings {
    @SettingKey("http.port")
    private int port = 8080;

    @SettingKey("http.host")
    private String host = "127.0.0.1";

    public List<String> endpoints(String region, int limit) {
        return List.of(region + "-api", region + "-admin")
            .subList(0, Math.min(limit, 2));
    }
}

public class ReflectionMetadataDemo {
    public static void main(String[] args) throws Exception {
        Field port = AppSettings.class.getDeclaredField("port");
        SettingKey key = port.getAnnotation(SettingKey.class);

        Method method = AppSettings.class.getDeclaredMethod(
            "endpoints", String.class, int.class
        );

        System.out.println("fieldKey=" + key.value());
        System.out.println("fieldType=" + port.getType().getTypeName());
        System.out.println("method=" + method.getName());
        System.out.println(
            "returnType=" +
            method.getGenericReturnType().getTypeName()
        );
        System.out.println(
            "returnIsParameterized=" +
            (method.getGenericReturnType() instanceof ParameterizedType)
        );
        System.out.println("parameterCount=" + method.getParameterCount());
        System.out.println(
            "parameterTypes=" +
            Arrays.toString(method.getParameterTypes())
        );
    }
}
```

Chạy:

```bash
javac ReflectionMetadataDemo.java
java ReflectionMetadataDemo
```

Stdout:

```text
fieldKey=http.port
fieldType=int
method=endpoints
returnType=java.util.List<java.lang.String>
returnIsParameterized=true
parameterCount=2
parameterTypes=[class java.lang.String, int]
```

Method trả về `List<String>`, vì vậy `getReturnType()` chỉ cho biết `List.class`, còn `getGenericReturnType()` giữ generic signature trong metadata class file.

## 8. Đọc generic type và hiểu type erasure

Reflection biểu diễn generic signature bằng interface `java.lang.reflect.Type`. Những dạng phổ biến:

| Type implementation | Ví dụ |
| --- | --- |
| `Class<?>` | `String`, `int`, `String[]` |
| `ParameterizedType` | `List<String>`, `Map<String, Integer>` |
| `TypeVariable<?>` | `T` trong `class Box<T>` |
| `WildcardType` | `? extends Number`, `? super Integer` |
| `GenericArrayType` | `T[]` khi T là type variable |

Ví dụ:

```java
Type type = method.getGenericReturnType();

if (type instanceof ParameterizedType) {
    ParameterizedType parameterized = (ParameterizedType) type;
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();

    System.out.println(raw.getTypeName());
    System.out.println(arguments[0].getTypeName());
}
```

Java generics dùng **type erasure**. Khi runtime tạo object từ `new ArrayList<String>()`, object không lưu một runtime class riêng là `ArrayList<String>`. `getClass()` trả về `ArrayList.class`.

Tuy vậy, compiler có thể ghi generic declaration signature vào class file. Reflection có thể đọc chữ ký khai báo của field/method/class:

- `Field.getGenericType()`
- `Method.getGenericReturnType()`
- `Method.getGenericParameterTypes()`
- `Class.getTypeParameters()`
- `Class.getGenericSuperclass()`
- `Class.getGenericInterfaces()`

Không thể chỉ nhìn object runtime rồi khẳng định mọi phần tử bên trong một `List` có cùng generic type đã khai báo. Nếu cần xác minh nội dung, phải duyệt phần tử và kiểm tra từng giá trị.

`List.class` là raw class; không có literal `List<String>.class`. Khi API cần nhận generic type, thường dùng `Type`, `ParameterizedType` hoặc type-token pattern có anonymous subclass để giữ generic superclass signature. Type token không khôi phục thông tin đã bị erasure khỏi object bất kỳ.

## 9. Type-use annotations và AnnotatedType

Để đọc annotation đặt trên một vị trí kiểu, dùng các API `AnnotatedType`, không chỉ `Field.getAnnotation(...)`.

Một số API:

- `Field.getAnnotatedType()`
- `Method.getAnnotatedReturnType()`
- `Method.getAnnotatedParameterTypes()`
- `Method.getAnnotatedReceiverType()`
- `Executable.getAnnotatedExceptionTypes()`
- `Class.getAnnotatedSuperclass()`
- `Class.getAnnotatedInterfaces()`

Các interface chuyên biệt gồm `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedTypeVariable` và `AnnotatedWildcardType`.

### 9.1. Ví dụ 3 — đọc annotation trong generic argument và array component

**TypeUseMetadataDemo.java**

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {
}

class TypedConfig {
    List<@NonNull String> names = List.of("api", "worker");
    @NonNull String[] labels = {"production", "internal"};
}

public class TypeUseMetadataDemo {
    public static void main(String[] args) throws Exception {
        Field names = TypedConfig.class.getDeclaredField("names");

        AnnotatedParameterizedType parameterized =
            (AnnotatedParameterizedType) names.getAnnotatedType();

        AnnotatedType elementType =
            parameterized.getAnnotatedActualTypeArguments()[0];

        Field labels = TypedConfig.class.getDeclaredField("labels");

        AnnotatedArrayType arrayType =
            (AnnotatedArrayType) labels.getAnnotatedType();

        AnnotatedType componentType =
            arrayType.getAnnotatedGenericComponentType();

        System.out.println(
            "genericElementIsNonNull=" +
            elementType.isAnnotationPresent(NonNull.class)
        );
        System.out.println(
            "arrayComponentIsNonNull=" +
            componentType.isAnnotationPresent(NonNull.class)
        );
        System.out.println(
            "genericType=" + names.getGenericType().getTypeName()
        );
    }
}
```

Chạy:

```bash
javac TypeUseMetadataDemo.java
java TypeUseMetadataDemo
```

Stdout:

```text
genericElementIsNonNull=true
arrayComponentIsNonNull=true
genericType=java.util.List<java.lang.String>
```

Đây chỉ là metadata. `@NonNull` không làm compiler từ chối `null` và cũng không tự validate phần tử được thêm vào list. Muốn có null-safety cần static analysis, processor hoặc runtime checks được cấu hình riêng.

## 10. Kiểm tra hợp đồng kiểu ở runtime

Một annotation mô tả contract; chương trình phải đọc và xác minh contract. Với method, contract có thể gồm số lượng và kiểu parameter, kiểu trả về, nullability theo từng vị trí, generic argument, annotation bắt buộc trên parameter/return type hoặc quy tắc domain như range, format và quyền truy cập.

Cần phân biệt **kiểu khai báo** với **kiểu object thực tế**. Reflection có thể đọc `Class<?>` của parameter và return type; đối số runtime cần kiểm tra riêng.

### 10.1. So sánh kiểu đúng chiều

Nếu muốn kiểm tra một object có thể được truyền vào parameter:

```java
Class<?> parameterType = method.getParameterTypes()[0];
boolean accepts = parameterType.isInstance(argument);
```

Nếu `argument` là `null`, `isInstance(null)` trả `false`; ứng dụng phải quyết định `null` có được phép không. Với primitive parameter, reflection invocation tự unbox wrapper tương ứng; cần từ chối `null` và chỉ nhận đúng wrapper có thể unbox.

Khi so sánh quan hệ subtype giữa hai class, nhớ chiều của `isAssignableFrom`:

```java
boolean acceptsString =
    CharSequence.class.isAssignableFrom(String.class);
```

Nghĩa là `CharSequence` có thể nhận instance của `String`. Gọi ngược `String.class.isAssignableFrom(CharSequence.class)` là sai với mục tiêu này.

### 10.2. Ví dụ 4 — annotation mô tả method contract

Ví dụ sau kiểm tra chữ ký method, argument runtime, null đối với primitive và kiểu kết quả. Đây là contract đơn giản dùng exact signature; nó chưa kiểm tra generic element type hoặc quy tắc nghiệp vụ.

**RuntimeContractDemo.java**

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodContract {
    Class<?>[] parameters();
    Class<?> returns();
}

class CatalogService {
    @MethodContract(
        parameters = {String.class, int.class},
        returns = List.class
    )
    public List<String> search(String prefix, int limit) {
        return List.of(prefix + "-one", prefix + "-two")
            .subList(0, Math.min(limit, 2));
    }
}

public class RuntimeContractDemo {
    static Class<?> boxed(Class<?> type) {
        if (!type.isPrimitive()) return type;
        if (type == int.class) return Integer.class;
        if (type == long.class) return Long.class;
        if (type == boolean.class) return Boolean.class;
        if (type == double.class) return Double.class;
        if (type == float.class) return Float.class;
        if (type == short.class) return Short.class;
        if (type == byte.class) return Byte.class;
        if (type == char.class) return Character.class;
        return Void.class;
    }

    static boolean signatureMatches(
        Method method,
        MethodContract contract
    ) {
        return Arrays.equals(
                method.getParameterTypes(),
                contract.parameters()
            )
            && method.getReturnType().equals(contract.returns());
    }

    static boolean argumentsMatch(
        Method method,
        Object[] args
    ) {
        Class<?>[] parameters = method.getParameterTypes();

        if (args == null) args = new Object[0];
        if (parameters.length != args.length) return false;

        for (int i = 0; i < parameters.length; i++) {
            if (args[i] == null) {
                if (parameters[i].isPrimitive()) return false;
            } else if (!boxed(parameters[i]).isInstance(args[i])) {
                return false;
            }
        }
        return true;
    }

    static Object invokeChecked(
        Object target,
        Method method,
        Object[] args
    ) throws Exception {
        MethodContract contract =
            method.getAnnotation(MethodContract.class);

        if (contract == null
                || !signatureMatches(method, contract)) {
            throw new IllegalStateException("method contract mismatch");
        }

        if (!argumentsMatch(method, args)) {
            throw new IllegalArgumentException("argument contract mismatch");
        }

        Object result = method.invoke(target, args);

        if (result != null
                && !boxed(contract.returns()).isInstance(result)) {
            throw new IllegalStateException("return contract mismatch");
        }

        return result;
    }

    public static void main(String[] args) throws Exception {
        CatalogService service = new CatalogService();

        Method method = CatalogService.class.getMethod(
            "search", String.class, int.class
        );

        MethodContract contract =
            method.getAnnotation(MethodContract.class);

        Object result = invokeChecked(
            service, method, new Object[] {"java", 2}
        );

        System.out.println(
            "signatureContractValid=" +
            signatureMatches(method, contract)
        );
        System.out.println(
            "validArgumentsAccepted=" +
            argumentsMatch(method, new Object[] {"java", 2})
        );
        System.out.println(
            "wrongArgumentRejected=" +
            !argumentsMatch(method, new Object[] {"java", "two"})
        );
        System.out.println(
            "nullPrimitiveRejected=" +
            !argumentsMatch(method, new Object[] {"java", null})
        );
        System.out.println(
            "resultSize=" + ((List<?>) result).size()
        );
    }
}
```

Chạy:

```bash
javac RuntimeContractDemo.java
java RuntimeContractDemo
```

Stdout:

```text
signatureContractValid=true
validArgumentsAccepted=true
wrongArgumentRejected=true
nullPrimitiveRejected=true
resultSize=2
```

Trong framework thực tế, không nên quét và parse annotation ở mỗi invocation. Hãy đọc metadata một lần, cache kết quả contract theo `Class`/`Method`, và kiểm tra cache invalidation/classloader lifecycle phù hợp. Tránh cache mạnh vô thời hạn trong ứng dụng hot reload hoặc plugin có classloader riêng.

## 11. Kiểm tra hợp đồng ngay lúc compile bằng annotation processor

Runtime validation phát hiện lỗi khi ứng dụng đang chạy hoặc khi method được gọi. Một số quy tắc có thể phát hiện sớm hơn trong quá trình compile:

- Field được đánh dấu phải dùng generic type rõ ràng, không dùng raw `List`.
- Annotation chỉ được đặt trên method có modifier nhất định.
- Method có annotation phải trả kiểu được hỗ trợ.
- Tên key, route hoặc schema phải duy nhất trong module.
- Cấu hình khai báo phải tuân theo convention.

Annotation processor triển khai `javax.annotation.processing.Processor`, thường mở rộng `AbstractProcessor`. Nó nhận annotation metadata qua `RoundEnvironment`, đọc kiểu bằng `TypeMirror`/`TypeElement`, và phát diagnostic bằng `Messager`.

Processor có thể phát `Diagnostic.Kind.ERROR` (compile thất bại), `WARNING` (cảnh báo) hoặc `NOTE` (thông tin). Dùng `Types` và `Elements` để so sánh kiểu theo compiler model; không cần tự parse source text. Khi cần tạo source/resource, dùng `Filer`.

### 11.1. Ví dụ 5 — annotation yêu cầu generic type argument tường minh

Cấu trúc ví dụ gồm annotation, processor, một source hợp lệ và một source sai. Annotation có retention `SOURCE`; processor đọc nó trong compile round.

**RequireTypeArguments.java**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.FIELD, ElementType.PARAMETER})
public @interface RequireTypeArguments {
}
```

**RequireTypeArgumentsProcessor.java**

```java
package demo;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.element.ElementKind;
import javax.tools.Diagnostic;

public final class RequireTypeArgumentsProcessor
        extends AbstractProcessor {

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public Set<String> getSupportedAnnotationTypes() {
        return Set.of("demo.RequireTypeArguments");
    }

    @Override
    public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv
    ) {
        for (Element element :
                roundEnv.getElementsAnnotatedWith(
                    demo.RequireTypeArguments.class
                )) {

            if (element.getKind() != ElementKind.FIELD
                    && element.getKind() != ElementKind.PARAMETER) {
                continue;
            }

            TypeMirror mirror = element.asType();

            if (mirror.getKind() != TypeKind.DECLARED) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "@RequireTypeArguments needs a declared generic type",
                    element
                );
                continue;
            }

            DeclaredType declared = (DeclaredType) mirror;
            TypeElement declaredElement =
                (TypeElement) declared.asElement();

            int declaredParameters =
                declaredElement.getTypeParameters().size();

            if (declaredParameters == 0
                    || declared.getTypeArguments().size()
                        != declaredParameters) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "raw or non-generic type: write explicit type arguments",
                    element
                );
            }
        }

        return true;
    }
}
```

**ValidTypedCatalog.java**

```java
package demo;

import java.util.List;

final class ValidTypedCatalog {
    @RequireTypeArguments
    List<String> names;
}
```

**InvalidTypedCatalog.java**

```java
package demo;

import java.util.List;

final class InvalidTypedCatalog {
    @RequireTypeArguments
    List names;
}
```

Compile annotation và processor trước:

```bash
javac -d out RequireTypeArguments.java RequireTypeArgumentsProcessor.java
```

Compile source hợp lệ, chỉ định processor rõ ràng:

```bash
javac -cp out -processorpath out -processor demo.RequireTypeArgumentsProcessor -d out ValidTypedCatalog.java
```

Kết quả:

```text
validGenericAccepted=true
```

Compile source raw type:

```bash
javac -cp out -processorpath out -processor demo.RequireTypeArgumentsProcessor -d out InvalidTypedCatalog.java
```

Compiler từ chối với diagnostic tương tự:

```text
InvalidTypedCatalog.java:7: error: raw or non-generic type: write explicit type arguments
    List names;
         ^
1 error
rawGenericRejected=true
```

Processor minh họa quy tắc rằng type được đánh dấu phải là declared generic type có đủ type arguments. Trong dự án thật, bổ sung test cho nested type, wildcard, generic subclass, type variable và các loại declaration mà annotation cho phép.

### 11.2. Vì sao chỉ định processor rõ ràng?

Nên dùng `-processor` và `-processorpath` (hoặc processor module path tương ứng) để xác định processor cần chạy. Cách này rõ ràng, tái lập được và phù hợp các JDK hiện đại; không phụ thuộc việc javac tự tìm processor trên application classpath.

Có thể đóng gói processor thành JAR và đăng ký service provider trong `META-INF/services/javax.annotation.processing.Processor`, nhưng cấu hình build vẫn nên chỉ rõ processor path/processor theo policy dự án. Annotation processing có thể chạy trong nhiều rounds; processor phải xử lý round cuối đúng quy tắc và tránh tạo source trùng lặp.

## 12. Runtime reflection hay compile-time processor?

| Tiêu chí | Reflection/runtime validator | Annotation processor |
| --- | --- | --- |
| Thời điểm | Khi ứng dụng chạy hoặc framework khởi tạo | Trong compile |
| Dữ liệu có sẵn | Class metadata, object runtime | Compiler element/type model |
| Kiểm tra object value | Có thể kiểm tra instance/argument thực tế | Không có object runtime |
| Kiểm tra source contract | Hạn chế ở metadata đã biên dịch | Phù hợp declaration/type rule |
| Kết quả lỗi | Exception/validation result lúc chạy | Compile error/warning |
| Chi phí | Có thể lặp nếu không cache | Tốn thời gian compile |
| Dùng tốt cho | Plugin, framework, dynamic configuration | Quy tắc compile-time, generated code, schema |

Dùng processor cho quy tắc có thể xác minh từ declaration. Dùng runtime validator khi cần kiểm tra object thật, configuration runtime, plugin hoặc class được nạp động. Có thể kết hợp cả hai: processor bắt lỗi sớm, runtime vẫn kiểm tra dữ liệu bên ngoài và cấu hình có thể thay đổi.

## 13. Đọc annotation trong framework: những chi tiết dễ sai

### 13.1. getAnnotation và getDeclaredAnnotation

Nếu annotation có `@Inherited`, `getAnnotation()` trên class con có thể trả annotation từ superclass. `getDeclaredAnnotation()` chỉ trả annotation được ghi trực tiếp trên class đó.

Khi quét method, `@Inherited` không áp dụng. Framework cần tự xác định quy tắc method override nếu muốn annotation ở superclass được áp dụng cho subclass.

### 13.2. Bridge method và synthetic member

Compiler có thể tạo bridge method để giữ polymorphism sau type erasure, và tạo synthetic member cho một số cấu trúc ngôn ngữ. Khi quét method để tạo route/handler, cân nhắc:

```java
for (Method method : type.getDeclaredMethods()) {
    if (method.isBridge() || method.isSynthetic()) {
        continue;
    }

    // Đọc annotation từ method thực.
}
```

Không loại bỏ synthetic/bridge một cách mù quáng nếu framework đang xây công cụ bytecode hoặc cần hỗ trợ generic override. Cần định nghĩa rõ method nào được coi là handler.

### 13.3. Tên parameter không luôn có trong reflection

`Parameter.getName()` có thể trả tên dạng `arg0`, `arg1` nếu class không được compile với metadata parameter name. Nếu framework phụ thuộc tên parameter, cấu hình compiler với `-parameters`:

```bash
javac -parameters MyService.java
```

Đừng dùng parameter name như định danh ổn định nếu build không đảm bảo flag đó.

### 13.4. Module encapsulation và truy cập private member

`setAccessible(true)` không bảo đảm có thể vượt mọi ranh giới module. Java Platform Module System có quy tắc exports/opens; truy cập reflective vào package không được mở có thể bị từ chối. `trySetAccessible()` cho phép kiểm tra khả năng mở quyền truy cập thay vì giả định thành công.

Ưu tiên public API và constructor/method được thiết kế cho framework. Nếu cần reflective access sâu, module sở hữu package phải mở package theo policy. Không thiết kế thư viện phụ thuộc vào việc luôn đọc được private state của mọi module.

### 13.5. Annotation proxy và giá trị mảng

Annotation instance do reflection trả về hoạt động như proxy. Giá trị array từ annotation element được trả dưới dạng bản sao; không sửa array đó để mong thay đổi metadata gốc. Annotation metadata là mô tả bất biến của declaration.

## 14. Thiết kế annotation API tốt

Một annotation nên có một ý nghĩa rõ, tên nói được contract và phạm vi target tối thiểu cần thiết.

Checklist thiết kế:

- Chọn tên mô tả mục đích, ví dụ `@Route`, `@ConfigKey`, `@RequiresRole`.
- Chọn `RetentionPolicy` theo consumer: processor, bytecode tool hay runtime.
- Khai báo `@Target` để giới hạn vị trí sử dụng.
- Dùng `@Documented` nếu người dùng API cần thấy annotation trong Javadoc.
- Chỉ dùng `@Inherited` nếu kế thừa class-level đúng với ngữ nghĩa.
- Dùng `@Repeatable` khi nhiều occurrence thực sự có ý nghĩa.
- Đặt default hợp lý và tránh default làm ẩn cấu hình quan trọng.
- Không đưa object lớn, mutable hoặc giá trị runtime vào annotation.
- Giữ annotation element có kiểu rõ ràng; dùng enum thay chuỗi tự do nếu tập giá trị hữu hạn.
- Viết processor/validator và test cho cả case hợp lệ lẫn không hợp lệ.
- Xác định behavior khi annotation bị thiếu, lặp, xung đột hoặc đặt sai context.
- Cân nhắc binary/source compatibility khi thay đổi annotation public đã phát hành.

### 14.1. Đừng dùng annotation như một ngôn ngữ cấu hình quá lớn

Annotation phù hợp với metadata nhỏ, tĩnh và gắn với code. Khi cấu hình cần expression động, danh sách lớn, bí mật, môi trường hoặc thay đổi mà không compile lại, dùng config file/service chuyên biệt. Không đặt password, token hay private key trong annotation vì giá trị có thể được lưu trong source và bytecode.

### 14.2. Annotation không thay thế type system

`@NonNull`, `@Range`, `@Immutable` hay `@ThreadSafe` tự định nghĩa không tạo ra guarantee của compiler/runtime. Chỉ khi có tool hiểu annotation và kiểm tra đúng quy tắc thì metadata mới tạo ra enforcement. Ghi rõ consumer nào chịu trách nhiệm thực thi contract.

## 15. Các lỗi thường gặp

1. **Quên `@Retention(RUNTIME)`:** reflection không đọc được annotation sau compile nếu retention là SOURCE/CLASS.
2. **Không khai báo retention:** mặc định CLASS, dễ khiến framework runtime không thấy annotation.
3. **Dùng RUNTIME cho mọi annotation:** giữ metadata không cần thiết; chọn theo consumer.
4. **Dùng `@Inherited` cho method:** annotation method không tự kế thừa.
5. **Nghĩ annotation trên interface tự truyền xuống class:** @Inherited chỉ theo superclass.
6. **Gọi getDeclaredAnnotation rồi mong thấy annotation superclass:** API chỉ đọc declaration hiện tại.
7. **Đọc container trực tiếp thay vì getAnnotationsByType:** dễ bỏ sót annotation repeatable theo cách compiler lưu.
8. **Target không phù hợp:** compiler từ chối annotation đặt ở context không được phép.
9. **Nhầm TYPE_PARAMETER với TYPE_USE:** một cái đánh dấu khai báo type variable, một cái đánh dấu vị trí dùng kiểu.
10. **Nghĩ @NonNull tự chặn null:** annotation không tự thêm runtime/static checking.
11. **Dùng kiểu element không hợp lệ:** annotation element không nhận List/Map/object tùy ý.
12. **Coi default là giá trị do caller gửi:** default được khai báo trong annotation type.
13. **Dùng getReturnType để đọc generic:** cần getGenericReturnType.
14. **Dùng getGenericReturnType để kiểm tra object list thực tế:** type erasure không cung cấp runtime element type của instance.
15. **Chỉ quét getMethods mà không hiểu kế thừa:** có thể trộn method public kế thừa với method khai báo trực tiếp.
16. **Không lọc bridge/synthetic method:** framework có thể xử lý một method logic nhiều lần.
17. **Tin Parameter.getName luôn là tên source:** compile cần -parameters.
18. **Dùng setAccessible(true) và giả định luôn thành công:** module encapsulation có thể chặn.
19. **Cache Method/Field mạnh vô thời hạn:** có thể giữ classloader/plugin không được giải phóng.
20. **Dùng reflection cho mỗi request:** đọc metadata một lần và cache contract phù hợp.
21. **So sánh isAssignableFrom ngược chiều:** target type gọi isAssignableFrom(actualType).
22. **Không xử lý primitive và wrapper:** reflection invocation cần wrapper tương ứng, primitive không nhận null.
23. **Dùng processor nhưng không khai báo processor path:** build có thể không chạy processor theo cấu hình hiện đại.
24. **Processor chỉ test case hợp lệ:** phải có negative compile test để chứng minh diagnostic hoạt động.
25. **Dùng processor parse source text:** ưu tiên Element, TypeMirror, Types, Elements.
26. **Phát diagnostic nhưng vẫn trả success:** lỗi contract cần Diagnostic.Kind.ERROR.
27. **Không xử lý nhiều processing rounds:** processor có thể được gọi nhiều lần; tránh tạo output trùng.
28. **Đưa secret vào annotation:** metadata có thể xuất hiện trong source, binary và tài liệu.

## 16. Checklist kiểm tra contract

- Annotation đã có tên và ý nghĩa rõ ràng chưa?
- Element types có đúng loại và default có hợp lý không?
- Retention đã phù hợp consumer chưa?
- Target có giới hạn vị trí cần thiết chưa?
- Có cần @Documented, @Inherited hoặc @Repeatable không?
- Container annotation có target/retention tương thích không?
- Framework có phân biệt getAnnotation() với getDeclaredAnnotation() không?
- Generic metadata có đọc qua getGeneric...() thay vì raw type không?
- Type-use metadata có đọc qua AnnotatedType không?
- Đã giải thích giới hạn type erasure chưa?
- Runtime validator có kiểm tra null, primitive-wrapper và assignability đúng chiều không?
- Có kiểm tra actual collection elements khi nghiệp vụ cần không?
- Có cache metadata mà không giữ classloader ngoài vòng đời không?
- Processor có diagnostic ERROR cho declaration sai không?
- Build có chỉ định processor rõ ràng không?
- Có test cả compile success và compile failure không?
- Module access, parameter names, bridge/synthetic members đã được xử lý theo contract chưa?

## 17. Câu hỏi ôn tập

**1.** Annotation dùng để làm gì?

**Đáp án:** Gắn metadata có kiểu vào declaration/type-use để compiler, processor, framework hoặc reflection đọc và xử lý.

**2.** Annotation có tự validate giá trị runtime không?

**Đáp án:** Không; cần processor, static analyzer hoặc runtime code hiểu và thực thi metadata.

**3.** Retention mặc định là gì nếu không khai báo?

**Đáp án:** CLASS.

**4.** Khi nào cần RUNTIME retention?

**Đáp án:** Khi ứng dụng/framework cần đọc annotation bằng reflection sau khi compile.

**5.** Annotation SOURCE có thể được annotation processor đọc không?

**Đáp án:** Có, trong compile processing rounds.

**6.** TYPE_PARAMETER khác TYPE_USE như thế nào?

**Đáp án:** TYPE_PARAMETER đánh dấu khai báo type variable; TYPE_USE đánh dấu vị trí sử dụng một kiểu.

**7.** @Inherited có áp dụng cho method không?

**Đáp án:** Không; chỉ annotation class-level theo chuỗi superclass.

**8.** Làm sao đọc annotation repeatable?

**Đáp án:** Dùng getAnnotationsByType hoặc getDeclaredAnnotationsByType.

**9.** Kiểu hợp lệ của annotation element gồm những gì?

**Đáp án:** Primitive, String, Class, enum, annotation và mảng một chiều của các kiểu đó.

**10.** getReturnType và getGenericReturnType khác gì?

**Đáp án:** Một trả raw Class; một trả Type có thể giữ generic signature.

**11.** Type erasure ảnh hưởng gì đến List<String>?

**Đáp án:** Runtime object không có class riêng cho List<String>; reflection đọc được generic declaration signature nhưng không tự biết mọi element của instance.

**12.** Interface nào đại diện generic declaration metadata?

**Đáp án:** java.lang.reflect.Type cùng ParameterizedType, TypeVariable, WildcardType và GenericArrayType.

**13.** API nào đọc type-use annotation trên field?

**Đáp án:** Field.getAnnotatedType().

**14.** @NonNull tự ngăn null được gán không?

**Đáp án:** Không, cần tool/runtime validation thực thi.

**15.** Chiều đúng của isAssignableFrom khi kiểm tra target nhận actual type?

**Đáp án:** targetType.isAssignableFrom(actualType).

**16.** Vì sao phải xử lý null khi parameter là primitive?

**Đáp án:** Primitive không nhận null; reflection invocation cũng không thể unbox null.

**17.** Annotation processor dùng API nào để đọc source model?

**Đáp án:** Element, TypeMirror, TypeElement, Types, Elements và RoundEnvironment.

**18.** Messager Diagnostic.Kind.ERROR có tác dụng gì?

**Đáp án:** Báo lỗi compile cho declaration không thỏa contract.

**19.** Vì sao nên chỉ định -processor và -processorpath?

**Đáp án:** Để build xác định rõ processor cần chạy, không phụ thuộc auto-discovery trên classpath.

**20.** Khi nào chọn runtime validator thay processor?

**Đáp án:** Khi cần kiểm tra object/runtime configuration, plugin hoặc dữ liệu chỉ có lúc ứng dụng chạy.

## 18. Tài liệu chính thức

- [Oracle Java SE 25 — Annotation Interface](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Annotation.html): mô hình annotation và API cơ bản.
- [Oracle Java SE 25 — Retention](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Retention.html): retention policy.
- [Oracle Java SE 25 — Target](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Target.html): element targets.
- [Oracle Java SE 25 — ElementType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html): các vị trí annotation được phép.
- [Oracle Java SE 25 — AnnotatedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedType.html): metadata của type-use annotation.
- [Oracle Java SE 25 — Type](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Type.html): mô hình generic type reflection.
- [Oracle Java SE 25 — ParameterizedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html): generic type argument.
- [Oracle Java SE 25 — AbstractProcessor](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): xây annotation processor.
- [Oracle Java SE 25 — RoundEnvironment](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): đọc element được đánh dấu trong processing round.
- [Oracle Java SE 25 — Messager](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/Messager.html): phát diagnostic compile.
- [Oracle Java SE 25 — TypeMirror](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html): compiler type model.
- [Oracle Java SE 25 — javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): tùy chọn compiler và annotation processing.
- [Oracle Java SE 25 — Java Language Specification, Annotations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html): quy tắc khai báo annotation type.

**Ghi nhớ:** Annotation chỉ là metadata; retention quyết định metadata tồn tại ở đâu, target quyết định được đặt ở đâu, còn processor hoặc runtime framework mới thực thi contract. Reflection có thể đọc generic declaration và type-use metadata, nhưng type erasure giới hạn điều có thể biết từ object runtime. Dùng annotation processor để bắt lỗi khai báo khi compile, runtime validator khi cần kiểm tra giá trị thực, và viết negative tests cho cả hai đường kiểm tra.