# Sự lan truyền annotation tới field, accessor và tham số constructor

Một record component có thể liên quan đến nhiều khai báo mà Java tạo ra: field lưu giá trị, accessor đọc giá trị và tham số của canonical constructor. Khi gắn annotation lên record header, compiler có thể chuyển annotation đó sang các khai báo tương ứng. Quy tắc này được gọi là **annotation propagation**.

Sự lan truyền phụ thuộc vào hai yếu tố:

- Annotation có áp dụng trong context đích hay không, được quyết định bởi `@Target`.
- Thành phần tương ứng là implicit hay được khai báo tường minh. Một số thành phần chỉ nhận annotation lan truyền khi chúng được compiler ngầm khai báo.

Bài học thuộc chương **Metadata record** của module **JAVA_VERSION_JAVA16**. Các quy tắc về record annotation là tính năng chính thức từ Java 16 và vẫn áp dụng trong Java hiện đại.

## 1. Một record component liên quan đến những khai báo nào?

Xét record:

```java
record Customer(String code, String name) {}
```

Với mỗi component, Java có các thành phần tương ứng:

| Thành phần | Ví dụ với component `code` | Đặc điểm |
| --- | --- | --- |
| Record component | `code` trong record header | Metadata riêng của component |
| Component field | `private final String code` | Field ngầm định để lưu giá trị |
| Accessor | `public String code()` | Phương thức đọc giá trị component |
| Canonical constructor parameter | Tham số `String code` | Tham số khởi tạo component |

Một annotation đặt ở vị trí component có thể áp dụng cho chính component, cho field, cho accessor, cho tham số constructor, hoặc cho kiểu dữ liệu. Việc annotation thực sự xuất hiện ở vị trí nào phụ thuộc vào target và cách thành phần đó được khai báo.

Đây là lý do không nên mặc định rằng annotation viết trước tên component luôn được lưu giống nhau ở mọi nơi.

## 2. `@Target` quyết định annotation có thể lan truyền đến đâu

`@Target` khai báo những context mà annotation được phép áp dụng. Các target quan trọng khi làm việc với record:

| Target | Context |
| --- | --- |
| `ElementType.RECORD_COMPONENT` | Chính record component |
| `ElementType.FIELD` | Component field |
| `ElementType.METHOD` | Accessor method |
| `ElementType.PARAMETER` | Tham số canonical constructor |
| `ElementType.TYPE_USE` | Kiểu của component và các vị trí sử dụng kiểu liên quan |

Ví dụ annotation chỉ dành cho component:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentInfo {
    String value();
}
```

Với `@ComponentInfo`, Reflection đọc được annotation từ `RecordComponent`. Annotation không được lan truyền sang field, accessor hoặc tham số constructor vì target không bao gồm các context đó.

Nếu muốn cùng một annotation xuất hiện ở nhiều vị trí, khai báo các target cần thiết:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.RECORD_COMPONENT,
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER
})
@interface AuditTag {
    String value();
}
```

Annotation `AuditTag` có thể được áp dụng ở cả bốn context. Tuy nhiên, điều này **không có nghĩa** mọi khai báo đều tự động nhận annotation: accessor hoặc constructor parameter được khai báo tường minh có quy tắc riêng.

Nếu không khai báo `@Target`, annotation mặc định áp dụng trong mọi declaration context, bao gồm record component, field, method và formal parameter, ngoại trừ type parameter context; nó không mặc định áp dụng trong type-use context. Khi thiết kế annotation cho record, khai báo target rõ ràng giúp thể hiện chủ đích và tránh sử dụng nhầm vị trí.

### Annotation không có target RECORD_COMPONENT vẫn có thể viết ở record header

Đây là trường hợp dễ gây nhầm. Nếu annotation chỉ có target `FIELD`, nó vẫn có thể được viết trước kiểu component vì annotation áp dụng cho field tương ứng:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.RecordComponent;

public class FieldOnlyTargetDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    @interface FieldTag {}

    record Item(@FieldTag String code) {}

    public static void main(String[] args) throws NoSuchFieldException {
        RecordComponent component =
                Item.class.getRecordComponents()[0];
        Field field = Item.class.getDeclaredField("code");

        System.out.println(
                component.getAnnotation(FieldTag.class) == null);
        System.out.println(
                field.getAnnotation(FieldTag.class) != null);
    }
}
```

Kết quả:

```text
true
true
```

Trong trường hợp này:

- `Item.class.getRecordComponents()[0].getAnnotation(FieldTag.class)` trả về `null` vì annotation không áp dụng cho record component context.
- `Item.class.getDeclaredField("code").getAnnotation(FieldTag.class)` trả về annotation vì nó áp dụng cho field.

Tương tự, annotation chỉ có target `METHOD` có thể áp dụng cho accessor ngầm định; annotation chỉ có target `PARAMETER` có thể áp dụng cho tham số canonical constructor được ngầm định. Khi đọc metadata, phải phân biệt context đích với vị trí cú pháp annotation được viết.

## 3. Quy tắc lan truyền tới component field

Mỗi record component có một component field được khai báo ngầm định. Field này luôn là `private final` và không phải `static`.

Annotation xuất hiện trên record component được áp dụng cho field nếu annotation type phù hợp với **field declaration context** hoặc **type context**. Field component được tạo ngầm định nên không có trường hợp người lập trình viết lại field này trong thân record.

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.RecordComponent;

public class FieldPropagationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.FIELD
    })
    @interface Column {
        String value();
    }

    record Order(@Column("order_code") String code) {}

    public static void main(String[] args) throws NoSuchFieldException {
        RecordComponent component =
                Order.class.getRecordComponents()[0];
        Field field = Order.class.getDeclaredField("code");

        System.out.println(
                component.getAnnotation(Column.class).value());
        System.out.println(
                field.getAnnotation(Column.class).value());
    }
}
```

Kết quả:

```text
order_code
order_code
```

`@Column` có cả target `RECORD_COMPONENT` và `FIELD`, vì vậy cùng annotation được đọc tại metadata component và field. Nếu bỏ `FIELD` khỏi target, lời gọi `field.getAnnotation(Column.class)` sẽ không tìm thấy annotation được lan truyền.

Lưu ý: field component là chi tiết triển khai mà Java quy định cho record. Trong mã ứng dụng, ưu tiên dùng accessor để đọc giá trị; chỉ truy cập field qua Reflection khi thực sự cần phân tích metadata hoặc phục vụ một công cụ chuyên biệt.

## 4. Quy tắc lan truyền tới accessor method

Mỗi component có accessor cùng tên, không có tham số và trả về kiểu của component. Nếu accessor được compiler ngầm khai báo, annotation trên component được áp dụng cho accessor khi annotation type phù hợp với **method declaration context** hoặc **type context**.

Ví dụ với accessor implicit:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

public class AccessorPropagationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.METHOD
    })
    @interface ApiField {
        String value();
    }

    record Customer(@ApiField("display-name") String name) {}

    public static void main(String[] args) {
        RecordComponent component =
                Customer.class.getRecordComponents()[0];
        Method accessor = component.getAccessor();

        System.out.println(
                component.getAnnotation(ApiField.class).value());
        System.out.println(
                accessor.getAnnotation(ApiField.class).value());
    }
}
```

Kết quả:

```text
display-name
display-name
```

### Khi accessor được khai báo tường minh

Nếu record tự khai báo accessor, annotation trên component **không được lan truyền** sang accessor đó. Muốn Reflection đọc annotation ở method, phải gắn annotation trực tiếp lên method:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

public class ExplicitAccessorDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.METHOD
    })
    @interface ApiField {
        String value();
    }

    record Customer(@ApiField("component") String name) {
        @ApiField("accessor")
        public String name() {
            return name.trim();
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        RecordComponent component =
                Customer.class.getRecordComponents()[0];
        Method accessor = Customer.class.getDeclaredMethod("name");

        System.out.println(
                component.getAnnotation(ApiField.class).value());
        System.out.println(
                accessor.getAnnotation(ApiField.class).value());
    }
}
```

Khi đó:

- `Customer.class.getRecordComponents()[0].getAnnotation(ApiField.class)` đọc giá trị `"component"`.
- `Customer.class.getDeclaredMethod("name").getAnnotation(ApiField.class)` đọc giá trị `"accessor"`.

Đây là hai metadata ở hai khai báo khác nhau. Việc viết annotation ở component không thay thế việc viết annotation ở accessor tường minh.

## 5. Quy tắc lan truyền tới tham số canonical constructor

Canonical constructor nhận toàn bộ component theo thứ tự khai báo. Tham số được suy ra từ record header; annotation trên component được áp dụng cho tham số nếu annotation type phù hợp với **formal parameter context** hoặc **type context**.

Quy tắc này hoạt động trực tiếp với:

- Canonical constructor implicit, do compiler tạo.
- Compact canonical constructor, vì danh sách formal parameter được ngầm khai báo từ record header.

Ví dụ compact canonical constructor:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class CompactConstructorPropagationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.PARAMETER
    })
    @interface InputTag {
        String value();
    }

    record User(@InputTag("user-name") String name) {
        User {
            name = name.trim();
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Constructor<?> constructor =
                User.class.getDeclaredConstructor(String.class);
        Parameter parameter = constructor.getParameters()[0];

        System.out.println(
                parameter.getAnnotation(InputTag.class).value());
    }
}
```

Kết quả:

```text
user-name
```

Compact constructor không khai báo danh sách tham số trong mã nguồn, nhưng compiler tạo formal parameter tương ứng với từng component. Vì vậy, annotation có target `PARAMETER` được áp dụng cho formal parameter đó.

### Khi normal canonical constructor được khai báo tường minh

Với normal canonical constructor, người viết tự khai báo formal parameter. Annotation trên component có thể khác annotation trên tham số constructor. Nếu muốn tham số có annotation, hãy gắn annotation trực tiếp lên tham số:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;

public class NormalCanonicalConstructorPropagationDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.PARAMETER
    })
    @interface InputTag {
        String value();
    }

    record User(@InputTag("component") String name) {
        User(@InputTag("constructor-parameter") String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        RecordComponent component =
                User.class.getRecordComponents()[0];
        Constructor<?> constructor =
                User.class.getDeclaredConstructor(String.class);
        Parameter parameter = constructor.getParameters()[0];

        System.out.println(
                component.getAnnotation(InputTag.class).value());
        System.out.println(
                parameter.getAnnotation(InputTag.class).value());
    }
}
```

Trong ví dụ này, annotation trên component có giá trị `"component"`, còn annotation trên tham số constructor có giá trị `"constructor-parameter"`. Không nên giả định compiler sẽ sao chép annotation component sang tham số của normal canonical constructor tường minh.

## 6. Bảng tổng hợp: vị trí nào nhận annotation?

| Thành phần đích | Target cần có | Điều kiện lan truyền |
| --- | --- | --- |
| Record component | `RECORD_COMPONENT` | Annotation áp dụng trong record component context |
| Component field | `FIELD` hoặc target type-use phù hợp | Field component được khai báo ngầm định |
| Accessor implicit | `METHOD` hoặc target type-use phù hợp | Accessor được compiler ngầm khai báo |
| Accessor explicit | Không tự động nhận annotation từ component | Gắn annotation trực tiếp lên method nếu cần |
| Tham số canonical constructor implicit | `PARAMETER` hoặc target type-use phù hợp | Canonical constructor được compiler ngầm khai báo |
| Tham số compact canonical constructor | `PARAMETER` hoặc target type-use phù hợp | Formal parameter của compact constructor được ngầm khai báo |
| Tham số normal canonical constructor explicit | Không tự động nhận annotation từ component | Gắn annotation trực tiếp lên formal parameter nếu cần |
| Kiểu component | `TYPE_USE` | Đọc bằng `RecordComponent.getAnnotatedType()` và các API `AnnotatedType` |

Bảng này mô tả annotation áp dụng cho declaration hoặc type tương ứng. Một annotation có thể khai báo nhiều target và do đó xuất hiện ở nhiều vị trí cùng lúc.

## 7. Retention quyết định có đọc được annotation lúc runtime không

Compiler có thể lan truyền annotation theo target ngay cả khi retention không phải `RUNTIME`. Nhưng nếu muốn đọc bằng Java Reflection sau khi chương trình chạy, annotation phải được giữ lại cho runtime.

| Retention | Kết quả với Reflection runtime |
| --- | --- |
| `SOURCE` | Annotation không được lưu trong class file |
| `CLASS` | Annotation có trong class file nhưng không hiện diện qua runtime reflection |
| `RUNTIME` | Có thể đọc bằng Reflection |

Nếu không khai báo `@Retention`, giá trị mặc định là `RetentionPolicy.CLASS`. Vì vậy, annotation dùng cho runtime metadata thường cần:

```java
@Retention(RetentionPolicy.RUNTIME)
```

Đọc annotation ở từng vị trí bằng API phù hợp:

| Vị trí | Reflection API |
| --- | --- |
| Record component | `RecordComponent.getAnnotation(...)` |
| Field | `Field.getAnnotation(...)` |
| Accessor | `Method.getAnnotation(...)` |
| Constructor parameter | `Parameter.getAnnotation(...)` |
| Kiểu component | `RecordComponent.getAnnotatedType()` |

Annotation có target đúng nhưng retention `CLASS` vẫn không đọc được bằng các API runtime ở bảng trên. Nếu mục tiêu là xử lý annotation trong quá trình biên dịch, có thể dùng annotation processing API thay vì runtime Reflection.

## 8. Phân biệt declaration annotation và type-use annotation

Annotation ở record header có thể mô tả declaration của component hoặc mô tả chính kiểu được khai báo. Ví dụ:

```java
@Target(ElementType.RECORD_COMPONENT)
@interface RequiredField {}

@Target(ElementType.TYPE_USE)
@interface NonNullType {}

record Profile(
        @RequiredField @NonNullType String name
) {}
```

- `@RequiredField` mô tả record component declaration.
- `@NonNullType` mô tả kiểu `String`.

Để đọc declaration annotation:

```java
RecordComponent component =
        Profile.class.getRecordComponents()[0];

RequiredField required =
        component.getAnnotation(RequiredField.class);
```

Để đọc type-use annotation:

```java
NonNullType nonNull =
        component.getAnnotatedType().getAnnotation(NonNullType.class);
```

Với kiểu generic như `List<@NonNullType String>`, cần duyệt cấu trúc `AnnotatedType` để đến đúng tham số kiểu; annotation trên kiểu phần tử không phải annotation declaration của component.

Type-use annotation cũng có thể được phản ánh ở kiểu của field, kiểu trả về accessor và kiểu tham số constructor nếu các khai báo tương ứng được tạo theo quy tắc record. Khi truy cập các vị trí đó, dùng `Field.getAnnotatedType()`, `Method.getAnnotatedReturnType()` và `Parameter.getAnnotatedType()`. Với accessor tường minh hoặc normal canonical constructor tường minh, không giả định annotation được sao chép từ component; áp dụng cùng nguyên tắc về khai báo tường minh đã nêu ở phần 4 và phần 5.

## 9. Ví dụ tổng hợp: Kiểm tra propagation ở bốn vị trí

Đoạn mã sau dùng annotation có đủ bốn declaration target và một record không khai báo accessor hay canonical constructor tường minh:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;

public class RecordPropagationSummary {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.FIELD,
            ElementType.METHOD,
            ElementType.PARAMETER
    })
    @interface Trace {
        String value();
    }

    record Payment(@Trace("payment-id") long id) {}

    public static void main(String[] args) throws ReflectiveOperationException {
        RecordComponent component =
                Payment.class.getRecordComponents()[0];
        Field field = Payment.class.getDeclaredField("id");
        Method accessor = component.getAccessor();
        Constructor<?> constructor =
                Payment.class.getDeclaredConstructor(long.class);
        Parameter parameter = constructor.getParameters()[0];

        System.out.println(component.getAnnotation(Trace.class).value());
        System.out.println(field.getAnnotation(Trace.class).value());
        System.out.println(accessor.getAnnotation(Trace.class).value());
        System.out.println(parameter.getAnnotation(Trace.class).value());
    }
}
```

Kết quả:

```text
payment-id
payment-id
payment-id
payment-id
```

Kết quả này đúng vì field, accessor và canonical constructor parameter đều được compiler ngầm khai báo, đồng thời annotation có target tương ứng và retention runtime.

Nếu đổi ví dụ sang accessor tường minh hoặc normal canonical constructor tường minh, kết quả ở các vị trí đó có thể khác hoặc không có annotation. Hãy xem các ví dụ ở phần 4 và phần 5 để chọn cách khai báo phù hợp.

## 10. Các lỗi thường gặp

**Chỉ khai báo `RECORD_COMPONENT` nhưng mong annotation có mặt trên field và accessor**

Target chỉ cho phép annotation áp dụng lên component. Muốn lan truyền, thêm `FIELD` hoặc `METHOD` tương ứng.

**Chỉ khai báo `FIELD` rồi đọc bằng `RecordComponent.getAnnotation()`**

Annotation áp dụng cho field chứ không áp dụng cho component. Đọc bằng `Field.getAnnotation()`.

**Cho rằng accessor tường minh nhận annotation từ component**

Annotation component không được lan truyền tới accessor tường minh. Gắn annotation trực tiếp lên method nếu cần.

**Cho rằng normal canonical constructor tường minh luôn nhận annotation trên tham số**

Tham số được khai báo tường minh có thể có annotation riêng. Gắn annotation trực tiếp lên formal parameter nếu cần đọc qua `Parameter`.

**Quên retention runtime**

`@Retention` mặc định là `CLASS`. Dùng `RUNTIME` khi cần đọc annotation bằng Reflection lúc chạy.

**Đọc type-use annotation như declaration annotation**

`RecordComponent.getAnnotation(...)` đọc annotation component; `getAnnotatedType()` đọc annotation trên kiểu. Dùng API đúng vị trí.

## 11. Bài tập tự kiểm tra

Cho các khai báo:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

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

record A(@Label("a") String name) {}

record B(@Label("b-component") String name) {
    public String name() {
        return name;
    }
}

record C(@Label("c-component") String name) {
    C(@Label("c-parameter") String name) {
        this.name = name;
    }
}

record D(@Label("d") String name) {
    D {
        name = name.trim();
    }
}
```

Hãy dự đoán annotation đọc được ở accessor và tham số canonical constructor của từng record:

1. `A` dùng accessor và canonical constructor implicit.
2. `B` tự khai báo accessor tường minh.
3. `C` tự khai báo normal canonical constructor và gắn annotation riêng lên tham số.
4. `D` dùng compact canonical constructor.

**Đáp án:**

| Record | Accessor | Constructor parameter |
| --- | --- | --- |
| `A` | `"a"` | `"a"` |
| `B` | Không có annotation lan truyền | `"b-component"` |
| `C` | `"c-component"` | `"c-parameter"` |
| `D` | `"d"` | `"d"` |

Giải thích:

- `A` có cả accessor và canonical constructor implicit nên annotation được lan truyền đến cả hai.
- `B` có accessor explicit nên annotation không được lan truyền đến method; canonical constructor vẫn implicit nên tham số nhận annotation.
- `C` có accessor implicit nên nhận annotation component; normal canonical constructor parameter được khai báo tường minh nên giữ annotation riêng.
- `D` có accessor implicit và formal parameter của compact constructor được ngầm khai báo nên cả hai nhận annotation component.

## Ghi nhớ

**Annotation propagation của record phụ thuộc vào target và cách khai báo thành phần đích.** Field component được tạo ngầm định và nhận annotation phù hợp với field hoặc type context. Accessor chỉ nhận annotation lan truyền khi accessor được ngầm khai báo. Formal parameter nhận annotation từ component khi canonical constructor implicit hoặc compact; normal canonical constructor tường minh có thể khai báo annotation riêng. Muốn đọc bằng Reflection lúc runtime, khai báo `RetentionPolicy.RUNTIME` và dùng API đúng vị trí: `RecordComponent`, `Field`, `Method`, `Parameter` hoặc `AnnotatedType`.

## Tài liệu tham khảo

- [Java Language Specification — Record Components](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.1)
- [Java Language Specification — Record Members and Annotation Propagation](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.3)
- [Java Language Specification — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4)
- [Java Language Specification — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.4)
- [Oracle Java SE API — ElementType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html)
- [Oracle Java SE API — RetentionPolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/RetentionPolicy.html)
- [Oracle Java SE API — RecordComponent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html)
