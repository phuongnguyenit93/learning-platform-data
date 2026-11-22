# Quy tắc truyền annotation tới trường, accessor và constructor của Java record

> **Phạm vi:** Bài thuộc **Java 14 → Tổ chức record**. Record từng là tính năng preview ở Java 14 nhưng đã chính thức từ **Java 16**. Nội dung dưới đây dựa vào quy tắc Java Language Specification (JLS) đang còn hiệu lực; ví dụ dùng **Java 17+** và không cần `--enable-preview`. Mục tiêu là hiểu chính xác cách annotation trên **record component** có thể được truyền tới **component field**, **accessor** và **tham số canonical constructor**.

## 1. Vì sao một annotation trên record header có thể xuất hiện ở nhiều vị trí?

Xét record:

```java
record Person(String name, int age) {}
```

Mỗi record component tương ứng với một số cấu trúc khác nhau:

- **Record component**: `name` được mô tả ngay trong header, có metadata riêng, đọc bằng `Class.getRecordComponents()`.
- **Component field**: Compiler khai báo ngầm field `private final String name`; đây là field bên trong record class, đọc bằng `getDeclaredField("name")`.
- **Accessor**: Nếu không tự khai báo, compiler tạo method `public String name()` để đọc field, tìm bằng `getDeclaredMethod("name")`.
- **Canonical constructor**: Nhận các tham số theo đúng thứ tự component; nếu không được tự khai báo, constructor được sinh ngầm. Tham số `name` có metadata riêng.
- **Type use**: `String` là một vị trí sử dụng kiểu có thể mang type annotation, khác với annotation khai báo field hoặc method.

Như vậy:

```text
record Person(@Marker String name, int age) {}
                |
                |  annotation viết trên component name
                |
                +--> metadata RECORD_COMPONENT (nếu @Target cho phép)
                +--> field private final name (nếu @Target cho phép FIELD)
                +--> accessor name() sinh ngầm (nếu cho phép METHOD)
                +--> tham số canonical constructor dẫn xuất (nếu cho phép PARAMETER)
                +--> kiểu String ở các vị trí phù hợp (nếu cho phép TYPE_USE)
```

**Không phải annotation nào cũng được sao chép đến mọi vị trí.** Java tuân theo `@Target` của loại annotation, trạng thái implicit/explicit của accessor và constructor, và quy tắc riêng cho annotation trên **declaration** so với annotation trên **type use**.

## 2. Hai metadata điều khiển: `@Target` và `@Retention`

### 2.1. `@Target` quyết định annotation áp dụng ở đâu

Trong `java.lang.annotation.ElementType`, các giá trị quan trọng cho record gồm:

| Target | Ý nghĩa khi annotation viết ở component header | Đọc bằng API Reflection |
| --- | --- | --- |
| `RECORD_COMPONENT` | Áp dụng cho record component, có metadata riêng | `RecordComponent.getAnnotation(...)` |
| `FIELD` | Truyền tới component field được sinh ngầm | `Field.getAnnotation(...)` |
| `METHOD` | Truyền tới accessor **sinh ngầm** | `Method.getAnnotation(...)` |
| `PARAMETER` | Truyền tới formal parameter được dẫn xuất cho canonical constructor | `Parameter.getAnnotation(...)` |
| `TYPE_USE` | Gắn vào **kiểu sử dụng** của component, field, return type hoặc parameter type được dẫn xuất | `getAnnotatedType()`, `getAnnotatedReturnType()` |

Có thể thiết kế annotation cho nhiều target:

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
@interface Trace {
    String value();
}

record Order(@Trace("header") String id) {}
```

Trong mẫu này, `Trace` có thể xuất hiện ở component, field, accessor implicit và constructor parameter implicit. **Các thành viên được khai báo tường minh** có ngoại lệ sẽ được giải thích ở phần 4–5.

Một annotation chỉ có `@Target(RECORD_COMPONENT)` không tự được chuyển đến field. Ngược lại, annotation chỉ có `@Target(FIELD)` có thể đặt ở component header để gắn với field được sinh, nhưng `RecordComponent.getAnnotation(...)` không vì thế mà nhìn thấy nó. Hai loại metadata **không đồng nhất**.

Với annotation không khai báo `@Target`, quy tắc applicability của JLS cho phép các ngữ cảnh declaration phù hợp, nhưng không đồng nghĩa nó áp dụng tự động cho mọi type-use context. Để API rõ ràng, nên khai báo đúng `@Target` ngay khi thiết kế annotation.

### 2.2. `@Retention` quyết định metadata được lưu đến giai đoạn nào

| Retention | Ý nghĩa | Reflection runtime |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Annotation có mặt ở source; compiler có thể sử dụng khi xử lý mã nguồn | Không đọc được |
| `RetentionPolicy.CLASS` | Được lưu vào class file theo quy tắc retention; là mặc định nếu không khai báo `@Retention` | Không đọc bằng Reflection thông thường |
| `RetentionPolicy.RUNTIME` | Metadata còn hiện diện ở runtime tại đúng phần tử được annotate | Đọc được qua các API Reflection tương ứng |

**Kết hợp cả hai điều kiện:** `@Target(FIELD)` nói annotation có thể được gắn vào field; muốn `Field.getAnnotation(...)` đọc được tại runtime, annotation còn phải được giữ lại với `@Retention(RUNTIME)`.

Compiler không tự kích hoạt bất kỳ validation hay mapping nào chỉ vì thấy annotation. Annotation chỉ là metadata. Framework hoặc mã do người viết phải thực sự đọc và xử lý metadata thì hành vi mới diễn ra.

## 3. Propagation tới component field

JLS `8.10.3 quy định mỗi record component có một field được khai báo ngầm: `private final` và không `static`. Những annotation của component có thể áp dụng trong **field declaration context** hoặc **type context** sẽ được gắn tới field phù hợp.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface StoredAs {
    String value();
}

record Account(@StoredAs("account_code") String code) {}
```

Đây là ví dụ khai báo riêng. Field `code` do compiler sinh có `@StoredAs("account_code")`. Annotation không tự xuất hiện trên accessor `code()` hoặc formal parameter constructor nếu `@Target` chỉ có `FIELD`.

Không nên tự khai báo lại instance field có cùng tên component để «giữ annotation». Record không cho phép khai báo instance field ngoài các field được dẫn xuất từ header. Muốn tác động cách phần tử được xử lý, hãy chọn annotation target và công cụ truy vấn tương ứng.

## 4. Propagation tới accessor: sự khác biệt giữa implicit và explicit

### 4.1. Accessor sinh ngầm

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface PublicView {}

record Profile(@PublicView String name) {}
```

Vì `name()` là accessor sinh ngầm, compiler gắn `@PublicView` lên method đó theo `@Target(METHOD)`.

### 4.2. Accessor viết tường minh

Nếu bạn tự viết accessor để chuẩn hóa dữ liệu, phòng vệ array hoặc thay đổi cách lấy giá trị:

```java
record Profile(@PublicView String name) {
    public String name() {
        return name.trim();
    }
}
```

Trong biến thể này, `@PublicView` trên component **không tự được truyền tới accessor `name()` tường minh**. Nếu framework đọc method annotation, cần khai báo trực tiếp:

```java
record Profile(@PublicView String name) {
    @PublicView
    public String name() {
        return name.trim();
    }
}
```

Ba khai báo `Profile` là **ba phiên bản minh họa độc lập**, không đặt chung cùng một package để biên dịch.

**Quy tắc JLS `8.10.3:** Accessor implicit nhận annotations thích hợp từ component; accessor explicit **không** được tự propagation. Điều này không làm mất các annotation trên chính record component hoặc component field.

Không dùng `@Override` để diễn tả «override accessor mặc định» khi không thực sự override phương thức của interface hoặc superclass. Method sinh ngầm không tồn tại song song sau khi bạn tự khai báo accessor.

## 5. Propagation tới canonical constructor parameter

Record có một canonical constructor gắn với danh sách component trong header. Ba cách khai báo dẫn tới ba tình huống annotation:

| Kiểu canonical constructor | Formal parameters | Annotation target `PARAMETER` từ header |
| --- | --- | --- |
| **Implicit** | Compiler tự tạo constructor và tham số dẫn xuất | **Được áp dụng** |
| **Compact** | Người viết khai báo thân `RecordName { ... }`, danh sách tham số vẫn được compiler dẫn xuất | **Được áp dụng** |
| **Normal explicit** | Người viết tự khai báo `RecordName(Type name, ...)` | **Không tự truyền** vào parameter đã khai báo tường minh |

### 5.1. Constructor ngầm định

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface ArgumentTag {}

record Query(@ArgumentTag String text) {}
```

Compiler sinh canonical constructor `Query(String text)`. Tham số `text` nhận `@ArgumentTag` vì target `PARAMETER` phù hợp.

### 5.2. Compact canonical constructor

```java
record Query(@ArgumentTag String text) {
    Query {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("empty");
        }
        text = text.trim();
    }
}
```

Compact constructor không viết formal parameters trong source, nhưng theo JLS `8.10.4.2` compiler **dẫn xuất chúng từ record header**. Annotation phù hợp vẫn áp dụng cho formal parameter `text`. Khi kết thúc thân compact constructor, các giá trị parameter đã được xử lý sẽ được gán cho component fields.

### 5.3. Normal canonical constructor viết tường minh

```java
record Query(@ArgumentTag String text) {
    Query(String text) {
        this.text = text;
    }
}
```

Ở biến thể này, `String text` trong constructor là một **formal parameter do người viết khai báo**. Annotation `@ArgumentTag` ở record header **không tự xuất hiện** trên parameter đó.

Nếu công cụ xử lý cần metadata tại constructor parameter, hãy annotate chính parameter tường minh:

```java
record Query(@ArgumentTag String text) {
    Query(@ArgumentTag String text) {
        this.text = text;
    }
}
```

Bốn mẫu `Query` trên là các biến thể **độc lập**, không dùng cùng một lúc trong một file.

Các annotation target `FIELD` hoặc `METHOD` từ header vẫn có thể nằm trên field và accessor implicit ngay cả khi constructor normal được viết tường minh. Đừng coi việc tự viết constructor là hành động xóa mọi annotation trong record.

**Constructor annotation và parameter annotation là hai thứ khác nhau.** Annotation có target `CONSTRUCTOR` đặt trên khai báo canonical constructor; annotation có target `PARAMETER` đặt trên một tham số. Record component annotation không tự trở thành annotation của toàn bộ constructor.

## 6. Ví dụ chạy được: kiểm tra bốn vị trí bằng Reflection

Chương trình sau chứng minh đồng thời propagation tới component, field, accessor và constructor parameter, cùng hai ngoại lệ explicit. Lưu file **`RecordAnnotationDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

public class RecordAnnotationDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({
        ElementType.RECORD_COMPONENT,
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER
    })
    @interface Mark {
        String value();
    }

    record Implicit(@Mark("header") String name) {}

    record Compact(@Mark("header") String name) {
        Compact {
            name = name.trim();
        }
    }

    record ExplicitAccessor(@Mark("header") String name) {
        public String name() {
            return name;
        }
    }

    record ExplicitConstructor(@Mark("header") String name) {
        ExplicitConstructor(String name) {
            this.name = name;
        }
    }

    record ExplicitBoth(@Mark("header") String name) {
        ExplicitBoth(@Mark("parameter") String name) {
            this.name = name;
        }

        @Mark("accessor")
        public String name() {
            return name;
        }
    }

    static String inspect(AnnotatedElement element) {
        Mark mark = element.getAnnotation(Mark.class);
        return mark == null ? "-" : mark.value();
    }

    static void print(String label, Class<?> clazz)
            throws ReflectiveOperationException {
        RecordComponent component = clazz.getRecordComponents()[0];
        Field field = clazz.getDeclaredField("name");
        Method accessor = clazz.getDeclaredMethod("name");
        Constructor<?> ctor = clazz.getDeclaredConstructor(String.class);

        System.out.println(label
                + ": component=" + inspect(component)
                + ", field=" + inspect(field)
                + ", accessor=" + inspect(accessor)
                + ", parameter=" + inspect(ctor.getParameters()[0]));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        print("Implicit", Implicit.class);
        print("Compact", Compact.class);
        print("ExplicitAccessor", ExplicitAccessor.class);
        print("ExplicitConstructor", ExplicitConstructor.class);
        print("ExplicitBoth", ExplicitBoth.class);
    }
}
```

Biên dịch/chạy với JDK 17+ có hỗ trợ release 17:

```bash
javac --release 17 RecordAnnotationDemo.java
java RecordAnnotationDemo
```

**Stdout:**

```text
Implicit: component=header, field=header, accessor=header, parameter=header
Compact: component=header, field=header, accessor=header, parameter=header
ExplicitAccessor: component=header, field=header, accessor=-, parameter=header
ExplicitConstructor: component=header, field=header, accessor=header, parameter=-
ExplicitBoth: component=header, field=header, accessor=accessor, parameter=parameter
```

**Giải thích:**

1. `Implicit`: Compiler tự khai báo method và constructor, nên annotation có target thích hợp được áp dụng ở cả bốn vị trí.
2. `Compact`: Constructor compact có thân do người viết định nghĩa nhưng formal parameter vẫn được dẫn xuất, nên nhận annotation.
3. `ExplicitAccessor`: Method viết tường minh **không nhận annotation từ header**; các vị trí còn lại không bị ảnh hưởng.
4. `ExplicitConstructor`: Formal parameter viết tường minh **không nhận annotation từ header**; accessor vẫn implicit nên có annotation.
5. `ExplicitBoth`: Ta chủ động annotate method và parameter bằng giá trị **khác** header. Reflection đọc đúng annotation gắn ở từng vị trí, không cố đồng bộ các giá trị.

`getDeclaredField` có thể truy vấn metadata của một field `private` mà không cần `setAccessible`, vì ví dụ không đọc/ghi nội dung của field.

## 7. Ví dụ riêng: `RECORD_COMPONENT` không phải `FIELD`

Lưu thành **`SeparateTargetsDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

public class SeparateTargetsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    @interface OnlyComponent {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    @interface OnlyField {}

    record Sample(@OnlyComponent @OnlyField String code) {}

    public static void main(String[] args)
            throws ReflectiveOperationException {
        var component = Sample.class.getRecordComponents()[0];
        var field = Sample.class.getDeclaredField("code");
        var method = Sample.class.getDeclaredMethod("code");
        var param = Sample.class.getDeclaredConstructor(String.class)
                .getParameters()[0];

        System.out.println("component-on-component="
                + component.isAnnotationPresent(OnlyComponent.class));
        System.out.println("component-on-field="
                + field.isAnnotationPresent(OnlyComponent.class));
        System.out.println("field-on-component="
                + component.isAnnotationPresent(OnlyField.class));
        System.out.println("field-on-field="
                + field.isAnnotationPresent(OnlyField.class));
        System.out.println("field-on-accessor="
                + method.isAnnotationPresent(OnlyField.class));
        System.out.println("field-on-parameter="
                + param.isAnnotationPresent(OnlyField.class));
    }
}
```

```bash
javac --release 17 SeparateTargetsDemo.java
java SeparateTargetsDemo
```

**Stdout:**

```text
component-on-component=true
component-on-field=false
field-on-component=false
field-on-field=true
field-on-accessor=false
field-on-parameter=false
```

Với code này, `@OnlyComponent` áp dụng cho metadata của record component; `@OnlyField` áp dụng cho field được sinh. Việc hai annotation cùng xuất hiện trong header **không làm các target bị trộn lẫn**.

## 8. `TYPE_USE`: annotation gắn với kiểu sử dụng

`@Target(TYPE_USE)` là một trường hợp cần tách khỏi declaration annotations. Ví dụ khai báo độc lập:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface DisplayType {}

record Title(@DisplayType String value) {}
```

Ở đây annotation đánh dấu **kiểu `String`**, không đơn giản là field declaration hay method declaration. Để kiểm tra các annotated types, dùng:

```java
// Các lệnh sau minh họa bên trong một phương thức có throws
// ReflectiveOperationException và đã khai báo class Title.
var component = Title.class.getRecordComponents()[0];
var field = Title.class.getDeclaredField("value");
var method = Title.class.getDeclaredMethod("value");
var parameter = Title.class.getDeclaredConstructor(String.class)
        .getParameters()[0];

var componentType = component.getAnnotatedType();
var fieldType = field.getAnnotatedType();
var accessorReturnType = method.getAnnotatedReturnType();
var constructorParameterType = parameter.getAnnotatedType();
```

Từng `AnnotatedType` có thể được truy vấn bằng `getAnnotation(DisplayType.class)`. Các type annotations trong generic arguments hoặc array dimensions còn có thể cần `AnnotatedParameterizedType`, `AnnotatedArrayType` hoặc API tương ứng.

**Không dùng `Method.getAnnotation(DisplayType.class)` để thay cho `Method.getAnnotatedReturnType().getAnnotation(DisplayType.class)`:** đó là hai vị trí metadata khác nhau. Nếu accessor hoặc normal canonical constructor được khai báo tường minh, hãy xem annotation trên **return type/parameter type được viết tường minh**; không mặc định propagation từ header.

Tên `@DisplayType` không có ý nghĩa validation sẵn có. Type annotation chỉ mô tả metadata; muốn tự động kiểm tra dữ liệu phải có processor hoặc mã thực thi cụ thể.

## 9. Áp dụng trong validation, JSON, mapper và framework

Annotation trên record component thường được thư viện dùng để mô tả điều kiện dữ liệu, tên trường hoặc cách chuyển đổi. Nhưng **nơi annotation xuất hiện** và **nơi framework thực sự đọc** là hai chuyện khác nhau.

Một thư viện có thể scan:

- `RecordComponent` để hiểu cấu trúc dữ liệu theo header.
- `Field` để lấy metadata mapping của field nội bộ.
- `Method` để xem annotation của accessor.
- `Parameter` để lấy thông tin dùng khi tạo đối tượng qua canonical constructor.
- `AnnotatedType` để hiểu annotation trên generic/container/return/parameter types.

Ví dụ giả định:

```java
// Minh họa ý tưởng, @SomeRule do thư viện cụ thể cung cấp.
record Payload(@SomeRule String text) {}
```

Không thể kết luận `@SomeRule` chắc chắn được áp dụng ở mọi vị trí nếu chưa đọc định nghĩa `@Target` và `@Retention`. Cũng không thể kết luận framework sẽ tự chạy `@SomeRule` chỉ vì annotation có mặt. Cần đọc tài liệu phiên bản đang dùng và viết integration test.

**Hai tình huống refactor thường gây thay đổi metadata:**

- Một record dùng accessor implicit có annotation METHOD từ header. Khi bạn thêm accessor explicit để clone array hoặc chuẩn hóa dữ liệu, metadata METHOD **không còn được tự áp dụng**. Nếu framework đọc method, phải xem xét annotate trực tiếp method explicit.
- Một record dùng canonical constructor implicit/compact có annotation PARAMETER từ header. Khi đổi thành normal canonical constructor explicit để thêm logic, annotation không tự truyền lên parameter do bạn viết. Nếu framework đọc parameter, annotate lại tại đúng parameter.

**Đừng suy đoán từ tên** các annotation quen thuộc như `@NotNull`, `@JsonProperty` hay `@Column`; các thư viện có thể đổi target, quy tắc scanning và xử lý metadata giữa các phiên bản. Kiểm tra **định nghĩa annotation và phiên bản thư viện thực tế**.

## 10. Kiểm tra annotation ở compile time, class file và runtime

| Giai đoạn | Công cụ | Chú ý |
| --- | --- | --- |
| Source processing | `javac` annotation processor; `javax.lang.model.*` | Có thể xử lý annotation `SOURCE`; metadata được diễn giải theo quy tắc mô hình phần tử của compiler. |
| Bytecode | `javap -v` hoặc công cụ phân tích class file | Metadata có thể được lưu theo retention và vị trí target; type annotations có attributes riêng. |
| Runtime | `java.lang.reflect.*` | Chỉ đọc được annotations có retention `RUNTIME`; phải truy vấn đúng phần tử hoặc annotated type. |
| Framework | Code của validation/serializer/mapper/ORM | Đọc target nào và thực thi điều gì tùy cấu hình/phiên bản framework. |

Có thể chạy lệnh sau khi compile chương trình ở phần 6:

```bash
javap -v 'RecordAnnotationDemo$Implicit'
```

Ở Bash, dấu `$` trong tên nested class cần được quote/escape để không bị shell diễn giải. `javap -v` cho nhiều thông tin, trong đó có thể thấy `Record` attribute và annotation metadata trên field/method/parameter; không sử dụng stdout cố định của lệnh này làm hợp đồng ứng dụng.

Khi runtime Reflection báo không thấy annotation, kiểm tra theo trình tự: **`@Retention` → `@Target` → implicit/explicit → đúng API Reflection → đúng phiên bản artifact đang chạy**. Cách này hiệu quả hơn việc thử chép annotation vào mọi nơi mà không hiểu điểm tiêu thụ thực sự.

## 11. Lỗi phổ biến

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Tưởng annotation trên component luôn hiện ở field, accessor, parameter | Có target không phù hợp, Reflection trả `null` | Xem `@Target` và từng nơi chứa metadata. |
| Đồng nhất `RECORD_COMPONENT` với `FIELD` | Query sai API, bỏ sót annotation | Dùng `RecordComponent` hoặc `Field` theo mục đích. |
| Cho rằng accessor explicit vẫn nhận annotation header | Metadata method thay đổi sau refactor | Annotate chính method explicit nếu cần. |
| Cho rằng normal canonical constructor nhận annotation parameter từ header | Framework validation parameter không thấy annotation | Annotate formal parameter explicit. |
| Cho rằng compact constructor không có parameter | Bỏ qua derived parameters trong constructor | Xem JLS `8.10.4.2`; tham số được compiler dẫn xuất. |
| Có `@Target` nhưng thiếu `@Retention(RUNTIME)` | Runtime Reflection không thấy annotation | Kiểm tra retention và công cụ đọc source/bytecode/runtime. |
| Dùng `getAnnotation` trên declaration cho `TYPE_USE` | Không thấy annotation trên kiểu | Dùng `getAnnotatedType` / `getAnnotatedReturnType`. |
| Thấy annotation là tưởng validation tự chạy | Đối tượng vẫn có thể chứa dữ liệu sai | Chạy test hành vi thật với framework/processor. |
| Đổi constructor/accessor mà chỉ test logic | Metadata vỡ dù code trả đúng giá trị | Test cả metadata mà thư viện dựa vào. |
| Copy annotation mà không xét source of truth | Annotation trùng lặp hoặc giá trị không nhất quán | Quy định một nơi khai báo hoặc kiểm tra tính nhất quán. |

## 12. Bài tập tự kiểm tra

**Bài 1 — Một annotation có hai target.**

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD})
@interface Visible {}

record Item(@Visible String code) {}
```

**Đáp án:** Field `code` và accessor implicit `code()` mang `@Visible`. `RecordComponent` không có annotation này theo target `RECORD_COMPONENT`, và formal parameter canonical constructor không có theo `PARAMETER`.

**Bài 2 — Nếu accessor được viết tường minh?**

```java
record Item(@Visible String code) {
    public String code() {
        return code;
    }
}
```

**Đáp án:** Field vẫn mang annotation; accessor explicit không tự nhận. Muốn annotation METHOD, ghi `@Visible` trực tiếp trước method. Đây là một biến thể riêng của ví dụ Bài 1.

**Bài 3 — Constructor compact và normal.**

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface CheckedInput {}

record A(@CheckedInput String text) {
    A {
        text = text.trim();
    }
}

record B(@CheckedInput String text) {
    B(String text) {
        this.text = text.trim();
    }
}
```

**Đáp án:** Formal parameter của `A` là derived parameter và mang `@CheckedInput`; formal parameter của normal canonical constructor `B` được khai báo tường minh nên không tự nhận. Đặt annotation vào `B(@CheckedInput String text)` nếu cần.

**Bài 4 — `@Target(FIELD)` nhưng processor đọc `RecordComponent` thì sao?**

**Đáp án:** `RecordComponent.getAnnotation` không thấy annotation chỉ dành cho FIELD. Cần đọc `Field` hoặc sửa thiết kế annotation để hỗ trợ RECORD_COMPONENT nếu đúng hợp đồng.

**Bài 5 — Tại sao `RetentionPolicy.CLASS` và `RetentionPolicy.RUNTIME` khác nhau?**

**Đáp án:** CLASS giữ annotation trong class file nhưng không expose qua core runtime Reflection. RUNTIME cho phép Reflection xem metadata trên phần tử được annotate. Khi một annotation «không hiện», phải kiểm tra retention trước khi kết luận compiler không propagation.

**Bài 6 — Khi nào cần `TYPE_USE`?**

**Đáp án:** Khi annotation mô tả một **lần sử dụng kiểu** như kiểu trong generic arguments hoặc return type, thay vì annotation declaration field/method. Truy vấn qua `AnnotatedType`, không giả định `getAnnotation` trên declaration tương đương.

## 13. Checklist khi triển khai

1. Xác định đối tượng tiêu thụ: Java reflection, framework runtime, annotation processor hay bytecode tool.
2. Kiểm tra annotation definition: `@Target`, `@Retention`, các target `TYPE_USE` và `RECORD_COMPONENT`.
3. Xác định thành viên compiler sinh hay do người viết khai báo: accessor implicit/explicit, constructor implicit/compact/normal.
4. Đọc metadata ở chính phần tử mà consumer thực sự scan.
5. Nếu custom accessor/constructor, quyết định có cần lặp annotation trên declaration tường minh hay không.
6. Thêm test kiểm tra reflection và test hành vi của framework khi annotation có tác dụng nghiệp vụ.
7. Build bằng release mục tiêu, chẳng hạn `javac --release 17`; dùng Java đang còn bảo trì khi triển khai.
8. Sau refactor annotation hoặc constructor/accessor, chạy lại các kiểm tra vì việc đổi từ implicit sang explicit có thể đổi metadata mà không đổi signature.

## 14. Nguồn chính thức

- [JLS Java SE 25 — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10): mô hình record component, các phần tử tương ứng và quy tắc truyền annotation.
- [JLS `8.10.3 Record Members](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.3): annotation trên field và accessor implicit; accessor explicit không tự nhận annotation từ component.
- [JLS `8.10.4 Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4): danh sách tham số dẫn xuất cho canonical constructor.
- [JLS `8.10.4.1 Normal Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4.1): constructor tường minh có parameter declaration riêng.
- [JLS `8.10.4.2 Compact Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4.2): compact constructor và tham số ngầm định.
- [JLS `9.6.4.1 `@Target`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.1), [`9.6.4.2 `@Retention`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.2): annotation applicability và retention.
- [Java SE 25 Javadoc — `RecordComponent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html): Reflection cho record component và annotated type.
- [Java SE 25 Javadoc — `ElementType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html): RECORD_COMPONENT, FIELD, METHOD, PARAMETER, TYPE_USE.
- [JEP 395 — Records](https://openjdk.org/jeps/395): phiên bản chính thức của records; với chương trình hiện hành, dùng đặc tả và API của release ổn định đang triển khai.

**Ghi nhớ:** Quy tắc annotation của record chỉ trở nên rõ ràng khi tách **metadata của component**, **field**, **accessor**, **constructor parameter** và **type use**. `@Target` quyết định vị trí hợp lệ, `@Retention` quyết định khả năng quan sát, còn việc **tự viết accessor hoặc normal constructor** quyết định annotation có còn được compiler truyền tới các declaration đó hay không.