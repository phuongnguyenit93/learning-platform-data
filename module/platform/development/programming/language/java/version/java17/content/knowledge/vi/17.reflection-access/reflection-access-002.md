# `Class.isRecord` và `Class.getRecordComponents` trong Java 17

Java 17 có Record Reflection API để chương trình nhận diện một kiểu record và đọc metadata của các component được khai báo trong record header. Hai phương thức quan trọng trên `java.lang.Class` là:

- **`Class.isRecord()`**: cho biết đối tượng `Class<?>` có đại diện cho một record class hay không.
- **`Class.getRecordComponents()`**: trả về metadata của các record component theo đúng thứ tự khai báo.

Các API này hữu ích khi xây dựng framework, serializer, mapper, công cụ kiểm tra kiểu dữ liệu, logging hoặc tiện ích xử lý object tổng quát. Thay vì suy đoán một lớp có phải record dựa trên tên, field hay phương thức, code có thể hỏi trực tiếp JVM thông qua reflection.

Record được giới thiệu chính thức trong Java 16; các phương thức reflection này cũng có từ Java 16 và dùng ổn định trong Java 17. Bài học tập trung vào cách nhận diện record, đọc thông tin component, gọi accessor, xử lý generic type và annotation, cùng những giới hạn cần biết khi làm việc với record bằng reflection.

## 1. Record component là gì?

Một record khai báo các thành phần dữ liệu ngay trên header:

```java
public record Person(String name, int age) {
}
```

`name` và `age` là hai **record component**. Khi khai báo record, Java tự cung cấp:

- Trường lưu trữ tương ứng với mỗi component; các trường này là `private final`.
- Accessor có tên trùng với component, ví dụ `name()` và `age()`.
- Canonical constructor nhận các component theo thứ tự khai báo.
- Các phương thức `equals()`, `hashCode()` và `toString()` được tạo theo quy tắc của record.

Có thể gọi accessor bình thường:

```java
Person person = new Person("Lan", 25);

System.out.println(person.name());
System.out.println(person.age());
```

Kết quả:

```text
Lan
25
```

Record component là khái niệm trong cấu trúc khai báo của record. Nó liên quan đến field lưu trữ, accessor và tham số canonical constructor, nhưng **không đồng nghĩa với một đối tượng `Field`**. Khi cần đọc đúng metadata của record header, API chuyên dụng là `Class.getRecordComponents()`.

## 2. Kiểm tra một class có phải record bằng `isRecord()`

`isRecord()` được gọi trên đối tượng `Class<?>`:

```java
Class<?> type = Person.class;

if (type.isRecord()) {
    System.out.println("Đây là record class");
} else {
    System.out.println("Đây không phải record class");
}
```

Kết quả:

```text
Đây là record class
```

Ví dụ so sánh với các kiểu thông thường:

```java
record Point(int x, int y) {
}

class Employee {
}

System.out.println(Point.class.isRecord());    // true
System.out.println(Employee.class.isRecord()); // false
System.out.println(String.class.isRecord());   // false
System.out.println(int.class.isRecord());      // false
System.out.println(java.lang.Record.class.isRecord()); // false
```

`java.lang.Record` là lớp cơ sở của record, nhưng bản thân `Record.class` không phải một record class. `isRecord()` kiểm tra metadata của kiểu đang được đại diện, không chỉ kiểm tra xem kiểu đó có nằm trong hệ phân cấp kế thừa từ `Record` hay không.

### Khi nào nên dùng `isRecord()`?

Dùng `isRecord()` khi code nhận một kiểu chưa biết trước, chẳng hạn:

- Một thư viện nhận `Class<?>` từ người dùng.
- Một serializer cần xử lý record theo component.
- Một công cụ debug cần hiển thị cấu trúc dữ liệu.
- Một mapper cần phân biệt record với JavaBean thông thường.
- Một framework cần chọn cách khởi tạo hoặc đọc dữ liệu tương ứng.

Không nên dùng tên lớp có chữ `Record`, số lượng field hoặc việc lớp kế thừa `java.lang.Record` như một phép thay thế cho `isRecord()`. API này thể hiện đúng ý định và tránh các suy đoán dễ sai.

## 3. Đọc danh sách component bằng `getRecordComponents()`

Khi kiểu là record, `getRecordComponents()` trả về một mảng `RecordComponent[]`:

```java
import java.lang.reflect.RecordComponent;

Class<?> type = Person.class;

if (type.isRecord()) {
    RecordComponent[] components = type.getRecordComponents();

    for (RecordComponent component : components) {
        System.out.println(component.getName());
        System.out.println(component.getType().getTypeName());
    }
}
```

Với record `Person(String name, int age)`, thông tin đọc được tương ứng:

```text
name
java.lang.String
age
int
```

**Thứ tự trong mảng trùng với thứ tự component được khai báo trong record header.** Với `Person(String name, int age)`, component đầu tiên là `name` và component thứ hai là `age`. Thứ tự này cũng là thứ tự các tham số của canonical constructor.

### Giá trị trả về khi kiểu không phải record

Cần chú ý hợp đồng của phương thức:

- Nếu `Class` đại diện cho record class, `getRecordComponents()` trả về mảng component.
- Nếu `Class` không đại diện cho record class, phương thức trả về **`null`**.
- Nếu record không khai báo component nào, phương thức trả về mảng rỗng, không phải `null`.

Ví dụ:

```java
record Marker() {
}

RecordComponent[] markerComponents =
        Marker.class.getRecordComponents();

System.out.println(markerComponents.length); // 0

RecordComponent[] stringComponents =
        String.class.getRecordComponents();

System.out.println(stringComponents == null); // true
```

Vì vậy, không nên gọi trực tiếp `getRecordComponents().length` mà chưa kiểm tra `isRecord()` hoặc kiểm tra kết quả `null`. Một cách viết an toàn:

```java
static void printComponents(Class<?> type) {
    RecordComponent[] components = type.getRecordComponents();

    if (components == null) {
        System.out.println(type.getName() + " không phải record");
        return;
    }

    if (components.length == 0) {
        System.out.println(type.getName() + " là record không có component");
        return;
    }

    for (RecordComponent component : components) {
        System.out.println(component.getName());
    }
}
```

Có thể gọi `isRecord()` trước để thể hiện rõ ý định; việc kiểm tra `null` trực tiếp cũng bảo vệ code khi chỉ cần xử lý kết quả trả về.

## 4. Các thông tin có thể đọc từ `RecordComponent`

Mỗi phần tử của mảng `RecordComponent[]` là một đối tượng `java.lang.reflect.RecordComponent`. API cung cấp metadata về component:

| Phương thức | Thông tin |
| --- | --- |
| `getName()` | Tên component trong record header. |
| `getType()` | Kiểu runtime dạng `Class<?>`, đã áp dụng type erasure với generic type. |
| `getGenericType()` | Kiểu khai báo có thông tin generic, trả về `Type`. |
| `getAnnotatedType()` | Kiểu có metadata annotation ở vị trí type-use. |
| `getAccessor()` | `Method` đại diện cho accessor của component. |
| `getDeclaringRecord()` | `Class<?>` của record khai báo component. |
| `getAnnotation(Class<T>)` | Lấy annotation được áp dụng cho component nếu có. |
| `getAnnotations()` | Lấy các annotation hiện diện trên component. |
| `isAnnotationPresent(Class<?>)` | Kiểm tra component có annotation chỉ định hay không. |

Ví dụ in tên, kiểu và accessor:

```java
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

static void describeRecord(Class<?> type) {
    if (!type.isRecord()) {
        throw new IllegalArgumentException("type phải là record");
    }

    for (RecordComponent component : type.getRecordComponents()) {
        Method accessor = component.getAccessor();

        System.out.println("Name: " + component.getName());
        System.out.println("Type: " + component.getType().getTypeName());
        System.out.println("Accessor: " + accessor.getName());
        System.out.println(
                "Declaring record: "
                        + component.getDeclaringRecord().getName()
        );
    }
}
```

Với `Person`, accessor tương ứng là `name()` và `age()`. `getDeclaringRecord()` trả về chính kiểu record chứa component đó.

## 5. Ví dụ hoàn chỉnh: duyệt metadata của record

Tạo file `RecordIntrospectionDemo.java`:

```java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

public class RecordIntrospectionDemo {

    public record Person(String name, int age, boolean active) {
    }

    public static void main(String[] args) {
        Class<?> type = Person.class;

        System.out.println("Class: " + type.getName());
        System.out.println("Is record: " + type.isRecord());

        if (!type.isRecord()) {
            return;
        }

        RecordComponent[] components = type.getRecordComponents();

        System.out.println("Component count: " + components.length);

        for (int i = 0; i < components.length; i++) {
            RecordComponent component = components[i];

            System.out.println("Component " + i);
            System.out.println("  name: " + component.getName());
            System.out.println(
                    "  type: " + component.getType().getTypeName()
            );
            System.out.println(
                    "  accessor: " + component.getAccessor().getName()
            );
        }

        System.out.println(
                "Names: " + Arrays.stream(components)
                        .map(RecordComponent::getName)
                        .toList()
        );
    }
}
```

Kết quả:

```text
Class: RecordIntrospectionDemo$Person
Is record: true
Component count: 3
Component 0
  name: name
  type: java.lang.String
  accessor: name
Component 1
  name: age
  type: int
  accessor: age
Component 2
  name: active
  type: boolean
  accessor: active
Names: [name, age, active]
```

Biên dịch và chạy bằng Java 17:

```bash
javac --release 17 -encoding UTF-8 RecordIntrospectionDemo.java
java RecordIntrospectionDemo
```

Ví dụ cho thấy có thể đọc cấu trúc record ngay từ `Class<?>` mà không cần tạo instance. Để đọc giá trị thực tế của từng component, cần một instance và gọi accessor tương ứng; đó là phần tiếp theo.

## 6. Dùng accessor để đọc giá trị component bằng reflection

`getRecordComponents()` chỉ trả metadata, không trả giá trị của một object. Mỗi `RecordComponent` cung cấp `getAccessor()` để lấy `Method` đại diện cho accessor.

Ví dụ:

```java
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

public class ReadRecordValues {

    public record Person(String name, int age) {
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Person person = new Person("Lan", 25);

        for (RecordComponent component :
                Person.class.getRecordComponents()) {

            Method accessor = component.getAccessor();
            Object value = accessor.invoke(person);

            System.out.println(component.getName() + " = " + value);
        }
    }
}
```

Kết quả:

```text
name = Lan
age = 25
```

Giải thích:

1. `Person.class.getRecordComponents()` lấy metadata của hai component.
2. `component.getAccessor()` lấy method accessor tương ứng.
3. `accessor.invoke(person)` gọi accessor trên instance `person`.
4. Giá trị trả về được nhận dưới dạng `Object` vì reflection không biết kiểu cụ thể tại thời điểm biên dịch.

Accessor của record là method đọc component, không phải setter. Record không cung cấp setter mặc định để thay đổi component sau khi khởi tạo.

### Viết helper đọc toàn bộ component thành Map

Một tiện ích nhỏ có thể chuyển một record thành map tên/giá trị:

```java
import java.lang.reflect.RecordComponent;
import java.util.LinkedHashMap;
import java.util.Map;

static Map<String, Object> toMap(Object value)
        throws ReflectiveOperationException {

    Class<?> type = value.getClass();

    if (!type.isRecord()) {
        throw new IllegalArgumentException("Object phải là record");
    }

    Map<String, Object> result = new LinkedHashMap<>();

    for (RecordComponent component : type.getRecordComponents()) {
        Object componentValue =
                component.getAccessor().invoke(value);

        result.put(component.getName(), componentValue);
    }

    return result;
}
```

Dùng `LinkedHashMap` để giữ thứ tự chèn theo thứ tự component trong record header:

```java
record Product(String code, int quantity) {
}

Product product = new Product("P-01", 4);

System.out.println(toMap(product));
```

Kết quả:

```text
{code=P-01, quantity=4}
```

Đây là ví dụ minh họa reflection. Serializer thực tế cần xử lý thêm kiểu lồng nhau, collection, null, annotation, chu kỳ object và chính sách bảo vệ dữ liệu nhạy cảm.

## 7. Phân biệt `getType()` và `getGenericType()`

Với component không dùng generic, hai phương thức thường cho kết quả gần giống nhau. Khác biệt rõ hơn khi record có generic type.

Ví dụ:

```java
import java.util.List;

record Envelope<T>(
        T payload,
        List<String> labels
) {
}
```

Duyệt metadata:

```java
import java.lang.reflect.RecordComponent;

for (RecordComponent component :
        Envelope.class.getRecordComponents()) {

    System.out.println("Name: " + component.getName());
    System.out.println(
            "Type: " + component.getType().getTypeName()
    );
    System.out.println(
            "Generic type: " + component.getGenericType().getTypeName()
    );
}
```

Kết quả điển hình:

```text
Name: payload
Type: java.lang.Object
Generic type: T
Name: labels
Type: java.util.List
Generic type: java.util.List<java.lang.String>
```

Giải thích:

- `getType()` trả kiểu `Class<?>` sau khi áp dụng type erasure.
- `getGenericType()` trả đối tượng `Type` có thể giữ thông tin generic trong chữ ký khai báo.
- Với component `T payload`, kiểu runtime sau erasure là `Object` trong ví dụ này, còn generic type vẫn thể hiện `T`.
- Với `List<String> labels`, `getType()` trả raw class `List`, còn `getGenericType()` thể hiện tham số kiểu `String`.

`Type` không phải lúc nào cũng là `Class<?>`. Tùy khai báo, nó có thể là `ParameterizedType`, `TypeVariable`, `WildcardType` hoặc kiểu mảng generic. Nếu framework cần phân tích generic type, phải xử lý các dạng `Type` tương ứng thay vì ép tất cả về `Class`.

### Kiểm tra kiểu generic bằng ParameterizedType

Ví dụ:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;

for (RecordComponent component :
        Envelope.class.getRecordComponents()) {

    Type genericType = component.getGenericType();

    if (genericType instanceof ParameterizedType parameterized) {
        System.out.println("Raw type: " + parameterized.getRawType());

        for (Type argument : parameterized.getActualTypeArguments()) {
            System.out.println("Type argument: " + argument.getTypeName());
        }
    }
}
```

Với `List<String>`, raw type là `List` và type argument là `String`. Với `T`, generic type là một `TypeVariable` nên không đi vào nhánh `ParameterizedType`.

## 8. Đọc annotation trên record component

Record component có thể mang annotation. Để annotation xuất hiện trong reflection, annotation cần có retention phù hợp, thường là `RetentionPolicy.RUNTIME`, và target cần bao gồm `ElementType.RECORD_COMPONENT`.

Ví dụ định nghĩa annotation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface Sensitive {
}
```

Dùng annotation trên record:

```java
public record Credentials(
        String username,
        @Sensitive String accessToken
) {
}
```

Kiểm tra annotation:

```java
import java.lang.reflect.RecordComponent;

for (RecordComponent component :
        Credentials.class.getRecordComponents()) {

    boolean sensitive = component.isAnnotationPresent(Sensitive.class);

    System.out.println(
            component.getName() + ": sensitive=" + sensitive
    );
}
```

Kết quả:

```text
username: sensitive=false
accessToken: sensitive=true
```

Có thể lấy trực tiếp annotation:

```java
Sensitive annotation =
        Credentials.class
                .getRecordComponents()[1]
                .getAnnotation(Sensitive.class);
```

Nếu annotation không có runtime retention, reflection runtime sẽ không đọc được annotation đó qua `getAnnotation()`.

### Annotation trên record component có thể được áp dụng ở nhiều vị trí

Record component liên quan đến nhiều phần tử được compiler tạo ra: field, accessor và tham số canonical constructor. Nếu annotation được khai báo với nhiều target phù hợp, compiler có thể áp dụng annotation đó lên các phần tử tương ứng theo quy tắc của record.

Ví dụ annotation:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.RECORD_COMPONENT,
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER
})
@interface Label {
    String value();
}
```

Khai báo:

```java
record User(
        @Label("Tên hiển thị") String displayName
) {
}
```

Khi kiểm tra, hãy xác định chính xác đang đọc annotation từ đâu:

- `RecordComponent.getAnnotation(...)` đọc annotation trên record component.
- `Field.getAnnotation(...)` đọc annotation trên backing field nếu annotation được áp dụng vào field.
- `Method.getAnnotation(...)` đọc annotation trên accessor nếu annotation được áp dụng vào method.
- `Parameter.getAnnotation(...)` đọc annotation trên tham số canonical constructor nếu annotation được áp dụng vào parameter.

Không giả định annotation xuất hiện ở mọi vị trí chỉ vì nó được viết trên record header. Kết quả phụ thuộc `@Target` của annotation.

## 9. Dùng `getAnnotatedType()` cho annotation ở vị trí kiểu

Annotation có thể gắn với **kiểu dữ liệu** (type-use), không chỉ gắn với chính component declaration.

Ví dụ annotation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonEmpty {
}
```

Khai báo record:

```java
record SearchRequest(
        @NonEmpty String query
) {
}
```

Đọc annotated type:

```java
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.RecordComponent;

RecordComponent component =
        SearchRequest.class.getRecordComponents()[0];

AnnotatedType annotatedType = component.getAnnotatedType();

System.out.println(annotatedType.getType().getTypeName());
System.out.println(
        annotatedType.isAnnotationPresent(NonEmpty.class)
);
```

Kết quả:

```text
java.lang.String
true
```

`getAnnotation()` trên `RecordComponent` và `getAnnotatedType()` giải quyết hai vị trí metadata khác nhau. Khi xây dựng validation framework, cần xác định annotation được định nghĩa cho component declaration hay cho type-use để đọc đúng API.

Lưu ý: annotation `@NonEmpty` trong ví dụ chỉ là metadata. Java không tự thực thi validation chỉ vì annotation tồn tại; framework hoặc code ứng dụng phải đọc và áp dụng quy tắc tương ứng.

## 10. Phân biệt record component với field và method thông thường

Một record như:

```java
record Order(String id, int quantity) {
    private static final String CATEGORY = "SALE";

    public String description() {
        return id + " x " + quantity;
    }
}
```

có hai record component là `id` và `quantity`. Nhưng khi dùng `getDeclaredFields()`, reflection còn có thể thấy field static `CATEGORY`. Khi dùng `getDeclaredMethods()`, reflection có thể thấy accessor và method tự khai báo.

Vì vậy, không nên dùng số lượng field để suy ra số lượng record component.

| API | Trả về | Mục đích |
| --- | --- | --- |
| `Class.getRecordComponents()` | `RecordComponent[]` hoặc `null` | Cấu trúc component được khai báo trong record header. |
| `Class.getDeclaredFields()` | `Field[]` | Field được khai báo trực tiếp trong class, bao gồm field không public. |
| `Class.getDeclaredMethods()` | `Method[]` | Method được khai báo trực tiếp trong class, bao gồm method không public. |
| `Class.getDeclaredConstructors()` | `Constructor<?>[]` | Constructor được khai báo trực tiếp trong class. |

Dùng đúng API theo câu hỏi cần trả lời. Nếu cần serializer hiểu tên và thứ tự component của record, `getRecordComponents()` là lựa chọn trực tiếp. Nếu cần kiểm tra một field static phụ trợ, dùng reflection field tương ứng.

## 11. Record component và canonical constructor

Record có canonical constructor nhận tham số theo thứ tự component. Có thể lấy kiểu tham số từ metadata rồi tìm constructor bằng reflection.

Ví dụ:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.RecordComponent;

record Coordinate(int x, int y) {
}

Class<Coordinate> type = Coordinate.class;

RecordComponent[] components = type.getRecordComponents();

Class<?>[] parameterTypes = new Class<?>[components.length];

for (int i = 0; i < components.length; i++) {
    parameterTypes[i] = components[i].getType();
}

Constructor<Coordinate> constructor =
        type.getDeclaredConstructor(parameterTypes);

Coordinate coordinate = constructor.newInstance(10, 20);

System.out.println(coordinate);
```

Kết quả:

```text
Coordinate[x=10, y=20]
```

Thứ tự component trong `getRecordComponents()` giúp xác định thứ tự kiểu tham số của canonical constructor. Tuy nhiên, metadata kiểu không cung cấp sẵn giá trị đầu vào; serializer hoặc mapper phải lấy giá trị từ nguồn dữ liệu, chuyển đổi chúng sang đúng kiểu rồi truyền theo đúng thứ tự.

### Tạo record có constructor validation

Nếu compact canonical constructor có validation, việc gọi constructor bằng reflection vẫn chạy validation đó:

```java
record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("value phải dương");
        }
    }
}
```

Khi gọi `newInstance(0)` qua reflection, constructor sẽ ném ngoại lệ. Với `Constructor.newInstance()`, ngoại lệ từ constructor thường được bọc trong `InvocationTargetException`; có thể xem nguyên nhân bằng `getCause()`.

Không nên cố khởi tạo record bằng cách tạo object rồi gán field bằng reflection. Hãy dùng canonical constructor để bảo đảm bất biến do record quy định được áp dụng.

## 12. Viết một helper tổng quát để mô tả record

Có thể kết hợp `isRecord()`, `getRecordComponents()`, `getGenericType()` và accessor thành một hàm mô tả:

```java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.stream.Collectors;

static String describe(Class<?> type) {
    if (!type.isRecord()) {
        return type.getName() + " (not a record)";
    }

    String components = Arrays.stream(type.getRecordComponents())
            .map(component ->
                    component.getName()
                            + ": "
                            + component.getGenericType().getTypeName()
            )
            .collect(Collectors.joining(", "));

    return type.getName() + "(" + components + ")";
}
```

Ví dụ:

```java
record Employee(String name, int level) {
}

System.out.println(describe(Employee.class));
```

Kết quả:

```text
Employee(java.lang.String name, int level)
```

Một helper mô tả record có thể hữu ích trong log, diagnostic tool hoặc công cụ phát sinh schema. Với ứng dụng production, không nên dùng chuỗi mô tả này làm định dạng serialization ổn định nếu chưa định nghĩa versioning và quy tắc tương thích.

## 13. Reflection với record trong môi trường module

Record Reflection API không xóa bỏ quy tắc truy cập của Java Platform Module System.

Một số điểm cần phân biệt:

- `isRecord()` và `getRecordComponents()` cung cấp thông tin về kiểu và metadata component.
- `getAccessor()` trả về method accessor; gọi method bằng reflection vẫn tuân theo quy tắc truy cập thông thường.
- Nếu record public nằm trong package được export, module khác có thể dùng API public theo readability và access rules.
- Nếu framework cần truy cập sâu vào private member, package có thể cần được mở cho module framework bằng `opens`.
- Không nên mở package chỉ vì muốn đọc metadata record; hãy xác định chính xác thao tác reflection nào cần quyền bổ sung.

Ví dụ, một record trong module thư viện:

```java
module com.acme.model {
    exports com.acme.model.api;
}
```

```java
package com.acme.model.api;

public record UserView(String name, int age) {
}
```

Module client:

```java
module com.acme.client {
    requires com.acme.model;
}
```

Client có thể dùng public record và accessor vì package đã export. Nếu một framework cần đọc private implementation detail bằng deep reflection, đó là yêu cầu khác và cần đánh giá `opens` theo đúng module đích.

### Không dùng reflection để sửa component field

Các component field của record là final và có tính chất không thể sửa thông qua reflective write. Ngay cả khi code có thể truy cập field bằng reflection để đọc, việc cố thay đổi giá trị field của record không phải cơ chế cập nhật record được hỗ trợ.

Ví dụ thiết kế đúng là tạo một record mới:

```java
record Person(String name, int age) {
}

Person original = new Person("Lan", 25);

Person updated = new Person(
        original.name(),
        26
);
```

Record biểu diễn dữ liệu theo giá trị; nếu cần trạng thái khác, tạo instance khác thay vì cố sửa component của instance hiện tại.

## 14. Những lỗi thường gặp

| Triệu chứng hoặc cách làm sai | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi `getRecordComponents().length` trực tiếp với mọi class | Phương thức trả `null` nếu class không phải record. | Kiểm tra `isRecord()` hoặc kiểm tra kết quả null trước khi duyệt. |
| Coi `null` và mảng rỗng là một trường hợp | Record không có component trả mảng rỗng; non-record trả null. | Xử lý riêng hai trường hợp. |
| Dùng số lượng field để đếm component | Record có thể có field static bổ sung; field và component là metadata khác nhau. | Dùng `getRecordComponents()`. |
| Ép `getGenericType()` về `Class<?>` | `Type` có thể là `ParameterizedType` hoặc `TypeVariable`. | Xử lý các implementation của `Type` phù hợp. |
| Gọi accessor mà không có instance | `Method.invoke()` cần đối tượng đích cho instance method. | Truyền instance record phù hợp vào `invoke()`. |
| Nghĩ `getRecordComponents()` trả giá trị của object | API chỉ trả metadata của kiểu. | Gọi accessor trên instance để lấy giá trị. |
| Nghĩ annotation luôn xuất hiện trên field, accessor và parameter | Việc lan truyền annotation phụ thuộc `@Target`. | Đọc annotation ở đúng phần tử và khai báo target cần thiết. |
| Nghĩ annotation tự chạy validation | Annotation chỉ là metadata. | Dùng framework hoặc code đọc annotation và thực thi quy tắc. |
| Cố gán lại record component field bằng reflection | Record component field là final và không hỗ trợ reflective write. | Tạo instance record mới qua canonical constructor. |
| Dùng API reflection record trên JDK cũ | `isRecord()` và `getRecordComponents()` không có trước Java 16. | Dùng JDK/API Java 16+; với bài này biên dịch theo Java 17. |

## 15. Bài thực hành

### Bài 1 — nhận diện record

Tạo một record `Book(String title, String author)` và một class thông thường `Library`. Dùng `isRecord()` để in kiểu nào là record, kiểu nào không phải.

### Bài 2 — đọc component theo thứ tự

Dùng `getRecordComponents()` trên:

```java
record Address(String city, String district, int postalCode) {
}
```

In chỉ số, tên component và kiểu của từng component. Xác nhận thứ tự metadata khớp record header.

### Bài 3 — xử lý non-record và record rỗng

Thử `String.class.getRecordComponents()` và `Marker.class.getRecordComponents()` với `record Marker() {}`. Giải thích vì sao một kết quả là `null` còn kết quả kia là mảng rỗng.

### Bài 4 — đọc giá trị bằng accessor

Tạo `record Product(String code, int quantity)` và một instance. Duyệt component, lấy `getAccessor()` rồi dùng `invoke(instance)` để in tên và giá trị.

### Bài 5 — phân biệt generic type

Tạo:

```java
record Page<T>(List<T> items, int pageNumber) {
}
```

So sánh `getType()` và `getGenericType()` của component `items`. Xác định phần thông tin nào bị type erasure và phần nào còn được giữ trong generic signature.

### Bài 6 — đọc annotation

Tạo annotation có `RetentionPolicy.RUNTIME` và `Target(ElementType.RECORD_COMPONENT)`. Gắn annotation lên một component, sau đó dùng `isAnnotationPresent()` và `getAnnotation()` để đọc.

### Bài 7 — khởi tạo bằng canonical constructor

Dùng metadata từ `getRecordComponents()` để tạo mảng kiểu tham số, lấy canonical constructor bằng `getDeclaredConstructor(...)` và khởi tạo một record bằng `newInstance(...)`. Thử với record có validation để quan sát `InvocationTargetException` khi dữ liệu không hợp lệ.

## 16. Ghi nhớ nhanh

| Nhu cầu | API |
| --- | --- |
| Kiểm tra một kiểu có phải record | `type.isRecord()` |
| Lấy component metadata | `type.getRecordComponents()` |
| Lấy tên component | `component.getName()` |
| Lấy kiểu runtime | `component.getType()` |
| Lấy generic type | `component.getGenericType()` |
| Lấy annotated type | `component.getAnnotatedType()` |
| Lấy accessor | `component.getAccessor()` |
| Lấy record khai báo component | `component.getDeclaringRecord()` |
| Kiểm tra annotation | `component.isAnnotationPresent(Annotation.class)` |
| Đọc annotation | `component.getAnnotation(Annotation.class)` |
| Đọc giá trị trên instance | `component.getAccessor().invoke(recordInstance)` |
| Tìm canonical constructor | `type.getDeclaredConstructor(componentTypes)` |

**Nguyên tắc cốt lõi:** Dùng `Class.isRecord()` để xác định chính xác kiểu có phải record hay không; dùng `Class.getRecordComponents()` để đọc tên, thứ tự, kiểu, generic metadata, annotation và accessor của từng component. Phương thức này trả `null` với class không phải record và trả mảng rỗng với record không có component. Metadata cho biết cấu trúc kiểu; muốn lấy giá trị cần gọi accessor trên instance, còn muốn tạo record cần đi qua constructor để giữ các bất biến của record.
