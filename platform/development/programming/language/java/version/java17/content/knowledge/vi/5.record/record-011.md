# Annotation trên record component và các thành viên liên quan trong Java 17

**Chủ đề:** Java 17  
**Chương:** Record  
**Bài học:** Annotation trên component và các thành viên liên quan

Khi khai báo một `record`, các thành phần (*record components*) trong cặp ngoặc tròn không chỉ mô tả dữ liệu. Chúng còn quyết định những thành viên mà Java tạo ra: một field `private final` cho mỗi component, một accessor, và các tham số tương ứng của canonical constructor. Điều đặc biệt là **annotation viết trên record component có thể xuất hiện trên nhiều vị trí khác nhau** — tùy `@Target` của annotation và cách record khai báo các thành viên.

Với Java 17, cần phân biệt rõ:

- **Record component** trong phần header, ví dụ `name` trong `record User(String name) {}`.
- **Component field** do compiler khai báo ngầm: `private final String name`.
- **Accessor** tương ứng: `public String name()`.
- **Tham số của canonical constructor**: tham số `name` trong `User(String name)`.
- **Vị trí dùng kiểu (type use)**: chính kiểu `String` trong `@Marker String name`, khác với annotation của khai báo component.

Đây là hành vi của Java Language Specification (JLS), không phải cách framework tự “copy annotation”. Một framework có thể đọc các vị trí trên qua reflection hoặc annotation processing và xử lý theo quy ước riêng.

> **Mốc phiên bản:** `record` được chuẩn hóa ở Java 16 (JEP 395) và là tính năng ổn định, sử dụng mặc định trong Java 17. Các ví dụ bên dưới chỉ dùng API và cú pháp ổn định của Java 17, không cần bật preview.

## 1. Từ record component đến các thành viên của record

Xem một khai báo cơ bản:

```java
record User(long id, String name) {}
```

Về mặt mô hình, mỗi component liên quan tới các thành viên sau:

```text
record User(long id, String name) {}
            │           │
            │           └── component: name
            └────────────── component: id

Mỗi component tương ứng với:
  ├── component field: private final ...
  ├── accessor: public ... name()
  └── formal parameter trong canonical constructor

Record còn có equals(Object), hashCode(), toString()
và một canonical constructor.
```

Ví dụ, có thể hình dung gần đúng những thành viên do compiler cung cấp khi không khai báo tường minh:

```java
// MÃ MINH HỌA CẤU TRÚC; không phải bản thay thế hoàn toàn tương đương record.
final class UserLike {
    private final long id;
    private final String name;

    UserLike(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public long id() {
        return id;
    }

    public String name() {
        return name;
    }

    // equals, hashCode, toString còn được tạo theo quy tắc record.
}
```

Cú pháp record có ý nghĩa khai báo hơn ví dụ lớp thường: class record kế thừa `java.lang.Record`, ngầm định `final` và có quy tắc riêng về constructor, component và các thành viên. Ví dụ `UserLike` chỉ giúp nhìn thấy các vị trí có thể mang annotation.

**Trọng tâm:** Component **không đồng nhất** với field. Reflection cung cấp loại riêng là `java.lang.reflect.RecordComponent`. Một annotation trên header có thể được sử dụng làm annotation khai báo component, hoặc được lan truyền đến field, accessor, tham số, kiểu dữ liệu — theo đúng mục tiêu được phép.

## 2. `@Target` quyết định annotation thuộc về đâu

Meta-annotation `@Target` từ `java.lang.annotation` khai báo những phần tử Java mà một annotation có thể áp dụng.

Đối với record, các giá trị đặc biệt quan trọng là:

| `ElementType` | Vị trí tương ứng | Ví dụ nơi framework có thể đọc |
|---|---|---|
| `RECORD_COMPONENT` | Chính record component trong header | `RecordComponent.getAnnotation(...)` |
| `FIELD` | Component field `private final` được khai báo ngầm | `Class.getDeclaredField(...).getAnnotation(...)` |
| `METHOD` | Accessor **được khai báo ngầm** | `RecordComponent.getAccessor().getAnnotation(...)` |
| `PARAMETER` | Tham số được suy ra cho canonical constructor **ngầm định hoặc compact** | `Constructor.getParameters()[i].getAnnotation(...)` |
| `TYPE_USE` | Annotation đặt trên phần **kiểu sử dụng** của component và các khai báo liên quan | `getAnnotatedType()`, `getAnnotatedReturnType()`, `Parameter.getAnnotatedType()` |

Bốn mục đầu đề cập chủ yếu tới **declaration annotation**. `TYPE_USE` đề cập tới **type annotation**, cần đọc theo API reflection của kiểu được chú thích.

Ví dụ định nghĩa annotation dùng tại nhiều nơi:

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
```

Khi dùng:

```java
record Product(@Label("product-code") String code) {}
```

Vì `Label` áp dụng được cho **cả bốn ngữ cảnh khai báo**, annotation này có thể được nhận diện trên component, field, accessor được tạo ngầm, và tham số canonical constructor được tạo ngầm.

### 2.1. Đặt nhiều `@Target` không tạo nhiều component

Trong `record Product(@Label("product-code") String code) {}`, chỉ có **một component** `code`. Java không tạo bốn component tương ứng với bốn giá trị `@Target`.

Thay vào đó, annotation được xem xét độc lập khi compiler khai báo **các thành viên phát sinh**. Vì vậy, metadata được đặt tại nhiều vị trí của cùng cấu trúc record.

### 2.2. Chỉ định một mục tiêu đơn lẻ

Các khai báo dưới đây đều có ý nghĩa riêng:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface AccessorOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface ParameterOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeOnly {}
```

Một annotation chỉ có `@Target(FIELD)` **vẫn có thể được viết trên record component** để compiler lan truyền nó sang component field. Tương tự cho `METHOD`, `PARAMETER` và `TYPE_USE`. Điều này không có nghĩa annotation sẽ xuất hiện ở tất cả các vị trí, hay tự động trở thành annotation của chính component.

Ví dụ:

```java
record Example(
        @ComponentOnly
        @FieldOnly
        @AccessorOnly
        @ParameterOnly
        @TypeOnly String value
) {}
```

Trong record này, mỗi annotation được đọc tại vị trí mà nó nhắm tới. Đặc biệt, `@ComponentOnly` chỉ nằm trên component và **không** tự động thành annotation trên field, accessor hay tham số constructor.

## 3. Quy tắc lan truyền của annotation trên component

Xét record không có accessor hoặc canonical constructor do người viết tự khai báo:

```java
record Order(@Label("order-id") String id) {}
```

Với `@Label` có các target như mục 2, compiler xử lý độc lập từng nơi:

1. **Component:** Nếu annotation áp dụng cho `RECORD_COMPONENT`, nó thuộc metadata của component.
2. **Field:** Nếu áp dụng cho `FIELD`, nó được ghi trên field `private final String id` do record cung cấp.
3. **Accessor:** Nếu áp dụng cho `METHOD`, nó được ghi trên accessor `id()` **nếu accessor được tạo ngầm**.
4. **Canonical constructor parameter:** Nếu áp dụng cho `PARAMETER`, nó được ghi trên tham số suy ra từ header **nếu constructor dùng các tham số được suy ra**.
5. **Type use:** Nếu áp dụng cho `TYPE_USE`, thông tin type annotation đi cùng các vị trí kiểu được suy ra tương ứng.

Bảng dưới đây tóm tắt trường hợp **record không khai báo accessor/canonical constructor tường minh**:

| `@Target` của annotation trên header | `RecordComponent` | Field | Accessor ngầm định | Parameter constructor ngầm định |
|---|:---:|:---:|:---:|:---:|
| Chỉ `RECORD_COMPONENT` | Có | Không | Không | Không |
| Chỉ `FIELD` | Không | Có | Không | Không |
| Chỉ `METHOD` | Không | Không | Có | Không |
| Chỉ `PARAMETER` | Không | Không | Không | Có |
| `RECORD_COMPONENT, FIELD, METHOD, PARAMETER` | Có | Có | Có | Có |
| Chỉ `TYPE_USE` | Đọc qua **annotated type**, không qua declaration annotation | Đọc qua annotated type | Đọc qua annotated return type | Đọc qua annotated parameter type |

**Lưu ý:** Bảng nói về nơi annotation được đưa vào nếu khai báo đúng mục tiêu. Muốn đọc trực tiếp bằng reflection tại runtime còn cần `@Retention(RUNTIME)`.

### 3.1. Annotation có `RECORD_COMPONENT` nhưng không có `FIELD`

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ApiName {
    String value();
}

record Customer(@ApiName("customer_name") String name) {}
```

Trong trường hợp này:

- `Customer.class.getRecordComponents()[0].getAnnotation(ApiName.class)` tìm thấy annotation.
- `Customer.class.getDeclaredField("name").getAnnotation(ApiName.class)` trả về `null`.
- Accessor `name()` và tham số constructor cũng không có annotation này dưới dạng declaration annotation.

Đây là lựa chọn phù hợp nếu metadata **chỉ nên nói về component**.

### 3.2. Annotation chỉ áp dụng cho field

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface StoredField {}

record Customer(@StoredField String name) {}
```

`@StoredField` được compiler đưa tới field `name`. Gọi `RecordComponent.getAnnotation(StoredField.class)` không trả về annotation đó vì `StoredField` không có target `RECORD_COMPONENT`.

Một thư viện chỉ quét field và một thư viện chỉ quét record components **có thể thấy metadata khác nhau**, dù chúng đọc cùng một record. Đây là lý do phải hiểu cơ chế introspection của công cụ đang dùng.

## 4. Ví dụ reflection quan sát đồng thời bốn vị trí

Ví dụ hoàn chỉnh sau minh họa annotation có nhiều target và dùng reflection để kiểm tra kết quả.

Tạo file `RecordAnnotationDemo.java`:

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

record Invoice(@AuditTag("invoice-code") String code) {}

public class RecordAnnotationDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Invoice> type = Invoice.class;

        RecordComponent component = type.getRecordComponents()[0];
        Field field = type.getDeclaredField("code");
        Method accessor = type.getDeclaredMethod("code");

        Constructor<Invoice> constructor =
                type.getDeclaredConstructor(String.class);
        Parameter parameter = constructor.getParameters()[0];

        System.out.println("Component: "
                + component.isAnnotationPresent(AuditTag.class));
        System.out.println("Field: "
                + field.isAnnotationPresent(AuditTag.class));
        System.out.println("Accessor: "
                + accessor.isAnnotationPresent(AuditTag.class));
        System.out.println("Parameter: "
                + parameter.isAnnotationPresent(AuditTag.class));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 RecordAnnotationDemo.java
java RecordAnnotationDemo
```

Kết quả:

```text
Component: true
Field: true
Accessor: true
Parameter: true
```

**Cách đọc kết quả:**

- `RecordComponent` đại diện cho thành phần khai báo trong header.
- `Field` là đối tượng reflection cho trường lưu dữ liệu tương ứng.
- `Method` là accessor `code()`.
- `Parameter` là tham số của canonical constructor `Invoice(String code)`.

Cả bốn giá trị là `true` **vì `@AuditTag` nhắm tới cả bốn vị trí** và được giữ tới runtime. Với `@Target` hẹp hơn, một hoặc nhiều kết quả sẽ là `false`.

## 5. Khi tự viết accessor: annotation không tự lan truyền sang accessor đó

Record tự tạo accessor nếu người viết không khai báo nó. Nhưng có thể khai báo accessor để kiểm soát giá trị trả về:

```java
record Profile(String displayName) {
    @Override
    public String toString() {
        return displayName;
    }

    public String displayName() {
        return displayName.strip();
    }
}
```

Nếu accessor đã được khai báo **tường minh**, Java **không tự sao chép annotation trên component** sang phương thức này, kể cả annotation có `@Target(METHOD)`.

### 5.1. Trường hợp dễ gây bất ngờ

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.RECORD_COMPONENT, ElementType.METHOD})
@interface Expose {}

record Account(@Expose String username) {
    public String username() {  // Accessor khai báo tường minh
        return username;
    }
}
```

Khi dùng reflection:

```java
boolean onComponent = Account.class.getRecordComponents()[0]
        .isAnnotationPresent(Expose.class);

boolean onAccessor = Account.class.getDeclaredMethod("username")
        .isAnnotationPresent(Expose.class);

System.out.println(onComponent); // true
System.out.println(onAccessor);  // false
```

**Vì sao?** Thông tin trên component vẫn tồn tại, nhưng accessor này do người viết cung cấp. Quy tắc lan truyền sang **accessor ngầm định** không áp dụng nữa.

### 5.2. Muốn annotation hiện diện trên cả accessor tường minh

Gắn annotation trực tiếp cho phương thức:

```java
record Account(@Expose String username) {
    @Expose
    public String username() {
        return username;
    }
}
```

Bây giờ `@Expose` xuất hiện ở component **và** accessor, nhưng vì hai nơi được khai báo riêng. Đây là cách làm phù hợp nếu framework của ứng dụng đọc annotation trên getter/accessor bằng `Method`.

### 5.3. Phạm vi ảnh hưởng

Việc tự khai báo accessor chỉ thay đổi quy tắc tạo/accessor đó:

- Component vẫn có annotation phù hợp với `RECORD_COMPONENT`.
- Component field vẫn được compiler khai báo và nhận annotation phù hợp với `FIELD`.
- Tham số canonical constructor vẫn được xét theo quy tắc constructor ở mục tiếp theo.
- Accessor tường minh chỉ có những annotation được khai báo trực tiếp trên nó; không tự nhận annotation trên component.

Không nên sửa các khai báo khác chỉ để “đồng bộ” nếu framework không thực sự cần annotation ở các vị trí ấy.

## 6. Canonical constructor: ngầm định, compact và tường minh

Record có canonical constructor nhận các tham số tương ứng với component theo đúng thứ tự. Có ba cách biểu diễn thường gặp:

| Hình thức | Ví dụ | Tham số đến từ đâu? |
|---|---|---|
| Constructor ngầm định | `record User(String name) {}` | Compiler suy ra từ header |
| Compact constructor | `record User(String name) { User { ... } }` | Compiler vẫn suy ra từ header |
| Normal canonical constructor viết tường minh | `record User(String name) { User(String name) { ... } }` | Người viết tự khai báo danh sách tham số |

Khác biệt này quan trọng với annotation có `@Target(PARAMETER)`.

### 6.1. Constructor ngầm định nhận annotation tham số

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface CheckedInput {}

record Customer(@CheckedInput String name) {}
```

Tham số `name` của constructor do compiler tạo ra nhận `@CheckedInput`. Vì annotation không nhắm `RECORD_COMPONENT`, reflection trên `RecordComponent` không đọc thấy nó như declaration annotation.

### 6.2. Compact constructor vẫn dùng danh sách tham số suy ra

```java
import java.util.Objects;

record Customer(@CheckedInput String name) {
    Customer {
        Objects.requireNonNull(name);
    }
}
```

Mặc dù người viết cung cấp body để kiểm tra dữ liệu, compact constructor **không khai báo lại danh sách tham số**. Tham số `name` vẫn được tạo từ header, nên annotation `@CheckedInput` có thể xuất hiện trên tham số constructor.

Đoạn code `Objects.requireNonNull(name)` minh họa validation **do lập trình viên viết**. Bản thân `@CheckedInput` trong ví dụ không tự chạy logic kiểm tra.

### 6.3. Normal canonical constructor tường minh có annotation độc lập

```java
record Customer(@CheckedInput String name) {
    Customer(String name) {
        this.name = java.util.Objects.requireNonNull(name);
    }
}
```

Vì normal canonical constructor tự khai báo tham số `String name`, annotation `@CheckedInput` trên component **không tự được sao chép sang tham số viết tường minh**.

Nếu một thư viện đọc tham số constructor và cần metadata đó, hãy khai báo trực tiếp:

```java
record Customer(@CheckedInput String name) {
    Customer(@CheckedInput String name) {
        this.name = java.util.Objects.requireNonNull(name);
    }
}
```

Hai lần `@CheckedInput` phục vụ **hai ngữ cảnh**: trên header và trên tham số của constructor viết tường minh.

### 6.4. Ví dụ kiểm tra sự khác biệt bằng reflection

```java
import java.lang.annotation.*;
import java.lang.reflect.Constructor;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface InputMark {}

record ImplicitRecord(@InputMark String value) {}

record CompactRecord(@InputMark String value) {
    CompactRecord {
        if (value == null) throw new IllegalArgumentException("null");
    }
}

record ExplicitRecord(@InputMark String value) {
    ExplicitRecord(String value) {
        this.value = value;
    }
}

public class ConstructorAnnotationDemo {
    static boolean marked(Class<?> type) throws ReflectiveOperationException {
        Constructor<?> ctor = type.getDeclaredConstructor(String.class);
        return ctor.getParameters()[0].isAnnotationPresent(InputMark.class);
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        System.out.println(marked(ImplicitRecord.class));
        System.out.println(marked(CompactRecord.class));
        System.out.println(marked(ExplicitRecord.class));
    }
}
```

Biên dịch và chạy file `ConstructorAnnotationDemo.java`:

```bash
javac --release 17 ConstructorAnnotationDemo.java
java ConstructorAnnotationDemo
```

Kết quả:

```text
true
true
false
```

Bài học ở đây không phải compact constructor có một cơ chế “copy thủ công”. Cả constructor ngầm định và compact đều dùng **derived formal parameter list** từ record header theo JLS 8.10.4. Còn normal canonical constructor tự khai báo tham số nên có metadata độc lập.

### 6.5. Không nhầm canonical constructor với constructor phụ

Record có thể có thêm constructor khác, nhưng chúng phải chuyển tiếp bằng lời gọi constructor khác của cùng record, ví dụ `this(...)`:

```java
record Customer(String name, int level) {
    Customer(String name) {
        this(name, 1);
    }
}
```

Annotation trên component được xét cho **tham số canonical constructor tương ứng**, không tự sao chép sang mọi tham số của mọi constructor phụ.

## 7. `TYPE_USE`: annotation trên phần sử dụng kiểu

Một annotation có `@Target(TYPE_USE)` mô tả **vị trí một kiểu được sử dụng**, thay vì mô tả trực tiếp việc khai báo field, method, parameter hay component.

Ví dụ:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonEmptyType {}

record Document(@NonEmptyType String title) {}
```

Trong `record Document(@NonEmptyType String title) {}`:

- `@NonEmptyType` áp dụng lên cách sử dụng kiểu `String` ở component.
- Thông tin kiểu tương ứng có thể xuất hiện ở kiểu của component field, kiểu trả về accessor ngầm định và kiểu tham số constructor được suy ra.
- `RecordComponent.getAnnotation(NonEmptyType.class)` không phải API thích hợp để đọc **type annotation**.
- Nên dùng `RecordComponent.getAnnotatedType()`, và ở các thành viên liên quan dùng `getAnnotatedType()` hoặc `getAnnotatedReturnType()`.

### 7.1. Reflection cho TYPE_USE

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface FormatHint {}

record Report(@FormatHint String title) {}

public class TypeUseAnnotationDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        RecordComponent component = Report.class.getRecordComponents()[0];
        Field field = Report.class.getDeclaredField("title");
        Method accessor = Report.class.getDeclaredMethod("title");
        Parameter parameter = Report.class.getDeclaredConstructor(String.class)
                .getParameters()[0];

        System.out.println(component.getAnnotatedType()
                .isAnnotationPresent(FormatHint.class));
        System.out.println(field.getAnnotatedType()
                .isAnnotationPresent(FormatHint.class));
        System.out.println(accessor.getAnnotatedReturnType()
                .isAnnotationPresent(FormatHint.class));
        System.out.println(parameter.getAnnotatedType()
                .isAnnotationPresent(FormatHint.class));

        // Đây là declaration annotation của RecordComponent, không phải type use:
        System.out.println(component.isAnnotationPresent(FormatHint.class));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 TypeUseAnnotationDemo.java
java TypeUseAnnotationDemo
```

Kết quả:

```text
true
true
true
true
false
```

Sự phân biệt `RecordComponent.getAnnotations()` với `RecordComponent.getAnnotatedType().getAnnotations()` rất quan trọng khi phát triển thư viện reflection.

### 7.2. Với generic type, vị trí của annotation còn chi tiết hơn

```java
record Inbox(
        java.util.List<@FormatHint String> messages
) {}
```

Ở đây, `@FormatHint` được đặt trên **type argument `String`**, không phải trực tiếp trên kiểu `List`. Để đọc annotation trên type argument, cần tiếp tục đi vào `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`:

```java
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.RecordComponent;

RecordComponent component = Inbox.class.getRecordComponents()[0];

AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType) component.getAnnotatedType();

AnnotatedType elementType =
        listType.getAnnotatedActualTypeArguments()[0];

System.out.println(elementType.isAnnotationPresent(FormatHint.class));
// true
```

Đây là đoạn minh họa để dùng cùng định nghĩa `Inbox` và `FormatHint` ở trên.

Tương tự, annotation có thể được đặt trong các vị trí sử dụng kiểu phức tạp hơn như array, wildcard hoặc nested generic. Khi kiểm tra annotation trong các kiểu này, không chỉ nhìn vào `getAnnotations()` của phần tử ngoài cùng.

### 7.3. TYPE_USE không tự thực thi validation

Một annotation `@NonEmptyType` hoặc `@FormatHint` do mình tự định nghĩa **chỉ là metadata**. Java không tự kiểm tra chuỗi rỗng hay áp dụng định dạng. Muốn có hành vi đó, phải viết logic kiểm tra hoặc tích hợp công cụ/framework hiểu annotation này.

Không nên hiểu sự lan truyền metadata kiểu là sự lan truyền logic xử lý.

## 8. `@Retention` quyết định khả năng quan sát qua reflection

`@Target` nói về **vị trí hợp lệ**; `@Retention` nói về **thời gian lưu giữ metadata**.

| Retention policy | Ý nghĩa | Có đọc được bằng Java reflection tại runtime? |
|---|---|---|
| `SOURCE` | Dùng trong source; compiler không giữ annotation trong class file | Không |
| `CLASS` | Giữ trong class file theo quy tắc retention, nhưng không bắt buộc/không được cung cấp qua reflection runtime | Không |
| `RUNTIME` | Giữ metadata và công khai cho reflection runtime | Có |

Ví dụ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface RuntimeSchemaName {
    String value();
}

record Payload(@RuntimeSchemaName("payload_id") long id) {}
```

`Payload.class.getRecordComponents()[0].getAnnotation(RuntimeSchemaName.class)` trả về annotation với giá trị `"payload_id"`.

Nếu định nghĩa `RuntimeSchemaName` với retention `SOURCE` hoặc `CLASS`, việc không tìm thấy annotation ở runtime **không chứng minh annotation đã bị khai báo sai**. Có thể nó không được giữ để reflection đọc.

**Thực hành:** Khi viết thư viện đọc record qua reflection, xác nhận **cả `@Target` và `@Retention`**, không chỉ nhìn vị trí của annotation trong mã nguồn.

## 9. Annotation trên bản thân record class khác annotation trên component

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface DomainType {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface DomainField {}

@DomainType
record Customer(@DomainField String name, int age) {}
```

Hai annotation phục vụ hai mục đích:

- `@DomainType` nằm trên **class `Customer`**, có thể đọc qua `Customer.class.getAnnotation(DomainType.class)`.
- `@DomainField` nằm trên **component `name`**, có thể đọc qua `Customer.class.getRecordComponents()[0].getAnnotation(DomainField.class)`.

Không có quy tắc mặc định nào khiến một annotation trên record class được chép sang tất cả component. Ngược lại, annotation trên component cũng không tự biến thành annotation trên record class.

**`@Inherited` cũng không giải quyết việc này.** `@Inherited` dành cho cơ chế tìm annotation trên **class** qua quan hệ kế thừa class theo quy tắc reflection; nó không tạo cơ chế di truyền annotation giữa record component, field và accessor. Record ngầm định `final` nên cũng không có lớp con record để dựa vào kiểu kế thừa đó.

## 10. Annotation trên record và ý nghĩa khi dùng framework

Trong ứng dụng thực tế, record thường được dùng làm DTO, thông điệp hoặc đối tượng truyền dữ liệu. Thư viện có thể đọc annotation tại những vị trí khác nhau:

| Cách thư viện khảo sát record | Phần tử được đọc | Điều cần xem khi khai báo annotation |
|---|---|---|
| Quét record component | `Class.getRecordComponents()` | Annotation có `RECORD_COMPONENT` và retention phù hợp? |
| Quét field | `Class.getDeclaredFields()` | Annotation có `FIELD`? |
| Quét accessor | `Class.getDeclaredMethods()` hoặc `RecordComponent.getAccessor()` | Annotation có `METHOD`? Accessor tự tạo hay viết tay? |
| Quét tham số constructor | `Constructor.getParameters()` | Annotation có `PARAMETER`? Constructor ngầm định/compact hay normal tường minh? |
| Quét type-use | `AnnotatedType` | Annotation có `TYPE_USE` và truy cập đúng cấp kiểu/generic? |

Ví dụ annotation có cả `RECORD_COMPONENT` và `FIELD` có thể được một framework đọc trên component, một framework khác đọc trên field. **Không nên suy ra mọi framework đều quét cùng một vị trí** hoặc xử lý record theo cùng quy tắc. Tương thích thực tế phụ thuộc phiên bản và cách framework hỗ trợ record.

### 10.1. Khi thay đổi accessor để chuẩn hóa dữ liệu

```java
record User(String username) {
    public String username() {
        return username.strip();
    }
}
```

Nếu trước đây có annotation `@Target(METHOD)` trên component, rồi bạn bổ sung accessor tường minh, annotation đó **không còn được lan truyền sang accessor**. Framework đọc annotation từ `Method` có thể thay đổi hành vi, dù annotation trong header vẫn nguyên vẹn.

Vì thế, khi viết accessor riêng, cần kiểm tra annotation mà thành phần dùng reflection mong đợi, rồi khai báo trực tiếp trên accessor nếu cần.

### 10.2. Khi thay compact constructor bằng normal canonical constructor

```java
// Dạng compact: tham số được suy ra từ component.
record A(@ParameterOnly String name) {
    A {
        java.util.Objects.requireNonNull(name);
    }
}
```

```java
// Dạng normal: người viết tự khai báo tham số.
record B(@ParameterOnly String name) {
    B(String name) {
        this.name = java.util.Objects.requireNonNull(name);
    }
}
```

Với annotation `@Target(PARAMETER)`, việc đổi dạng constructor có thể làm thay đổi annotation trên **tham số constructor quan sát được bằng reflection**. Đây là khác biệt đáng quan tâm trong các thư viện có xử lý parameter metadata.

Nếu thư viện cần annotation trên tham số normal constructor của `B`, hãy gắn `@ParameterOnly` trực tiếp tại `B(@ParameterOnly String name)`.

### 10.3. Annotation không thay thế kiểm tra tính hợp lệ của record

```java
record Account(String number) {
    Account {
        if (number == null || number.isBlank()) {
            throw new IllegalArgumentException("number is required");
        }
    }
}
```

Đây là validation Java thông thường trong compact constructor. Annotation có thể **mô tả** ràng buộc; code hoặc framework được cấu hình phải **thực thi** ràng buộc. Không nên giả định rằng chỉ thêm annotation là dữ liệu tự được kiểm tra.

## 11. Annotation processing lúc biên dịch

Ngoài reflection runtime, các annotation processor có thể truy cập cấu trúc record khi xử lý mã nguồn. Với Java 17, API `javax.lang.model` hỗ trợ record, gồm:

- `ElementKind.RECORD` biểu diễn class record.
- `ElementKind.RECORD_COMPONENT` biểu diễn record component.
- `RecordComponentElement` là interface dành cho phần tử component, có thể dùng để truy cập thông tin tương ứng.
- Annotation processor có thể đọc metadata của component và các phần tử liên quan theo cách riêng.

Đây là **một cơ chế khác reflection runtime**. Annotation có retention `SOURCE` vẫn có thể hữu ích cho xử lý lúc biên dịch, dù không xuất hiện trong `getAnnotation(...)` khi ứng dụng chạy.

Ví dụ về ý tưởng xử lý:

```java
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;

static void inspect(Element element) {
    if (element.getKind() == ElementKind.RECORD_COMPONENT) {
        System.out.println("Record component: " + element.getSimpleName());
    }
}
```

Đoạn này là phần thân minh họa cho một processor hoặc một tiện ích chạy trong annotation processing; không phải một chương trình Java độc lập có thể gọi ngoài môi trường processor.

**Nguyên tắc:** Metadata được compiler lan truyền trong record không đồng nghĩa mọi processor hoặc thư viện sẽ tự tổng hợp nó thành một annotation duy nhất. Mỗi công cụ phải xác định rõ vị trí và loại phần tử mà nó đọc.

## 12. Các hiểu nhầm và lỗi thường gặp

### 12.1. “Gắn annotation lên component thì field, getter và constructor đều có annotation”

Không phải lúc nào cũng đúng. Việc lan truyền phụ thuộc `@Target`, retention, và các thành viên do compiler tạo ngầm hay được lập trình viên khai báo tường minh.

**Cách xử lý:** Đọc `@Target` của annotation, rồi xác định framework quét vị trí nào.

### 12.2. “`RECORD_COMPONENT` là target duy nhất dùng được trên header”

Sai. `FIELD`, `METHOD`, `PARAMETER`, `TYPE_USE` cũng có thể được viết ở header để Java áp dụng đúng ngữ cảnh. Nhưng không có nghĩa chúng đều hiển thị trong `RecordComponent.getAnnotations()`.

### 12.3. “Tự viết accessor vẫn giữ annotation được tự lan truyền”

Sai. Accessor tường minh không tự nhận annotation từ component. Nếu cần annotation trên accessor, khai báo trực tiếp.

### 12.4. “Compact constructor làm mất annotation tham số”

Sai. Compact constructor vẫn dùng danh sách tham số suy ra từ component; annotation phù hợp với `PARAMETER` được xét trên các tham số đó.

### 12.5. “Normal canonical constructor tự nhận annotation tham số từ header”

Sai. Nếu đã khai báo rõ tham số ở constructor, annotation trên tham số có thể khác annotation của component. Cần khai báo trực tiếp trên tham số constructor khi hệ thống yêu cầu.

### 12.6. “`getAnnotations()` và `getAnnotatedType()` đọc cùng thông tin”

Sai. API thứ nhất đọc **declaration annotations** của phần tử. API thứ hai cung cấp thông tin về **type annotations** trên cách sử dụng kiểu.

### 12.7. “Có `@Target(RECORD_COMPONENT)` thì reflection luôn đọc được”

Sai nếu retention không phải `RUNTIME`. `@Target` và `@Retention` giải quyết hai câu hỏi khác nhau.

### 12.8. “Annotation tự động kiểm tra dữ liệu của record”

Sai. Annotation thường là metadata. Muốn kiểm tra đầu vào cần mã Java tương ứng hoặc framework được thiết lập để xử lý annotation.

## 13. Bài tập tự luyện

### Bài 1. Xác định nơi annotation xuất hiện

Cho:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.PARAMETER})
@interface Limited {}

record Item(@Limited String code) {}
```

**Câu hỏi:** Trong số component, field, accessor và tham số canonical constructor ngầm định, vị trí nào có declaration annotation `@Limited` tại runtime?

**Đáp án:** Field và tham số constructor. Component không có `RECORD_COMPONENT`, accessor không có `METHOD`.

### Bài 2. Accessor tường minh

Cho:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.RECORD_COMPONENT, ElementType.METHOD})
@interface Visible {}

record Document(@Visible String title) {
    public String title() {
        return title;
    }
}
```

**Câu hỏi:** `Document.class.getDeclaredMethod("title").isAnnotationPresent(Visible.class)` trả về gì?

**Đáp án:** `false`, vì accessor do người viết khai báo tường minh. Component vẫn có `@Visible` do target `RECORD_COMPONENT`.

### Bài 3. Canonical constructor

Cho:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Required {}

record Profile(@Required String name) {
    Profile(String name) {
        this.name = name;
    }
}
```

**Câu hỏi:** Reflection trên tham số `Profile(String name)` có thấy `@Required` không? Nếu muốn có, sửa cách nào?

**Đáp án:** Không. Đặt `@Required` trực tiếp trước `String name` trong normal canonical constructor, hoặc cân nhắc compact constructor nếu phù hợp nhu cầu.

### Bài 4. Phân biệt type use và declaration

Cho:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Normalized {}

record Account(@Normalized String code) {}
```

**Câu hỏi:** Nên dùng `RecordComponent.getAnnotation(Normalized.class)` hay `RecordComponent.getAnnotatedType().getAnnotation(Normalized.class)`?

**Đáp án:** Dùng `getAnnotatedType().getAnnotation(...)`. `@Normalized` nhắm tới cách dùng kiểu `String`, không phải declaration annotation trên component.

### Bài 5. Annotation và validation

Cho:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface NotEmpty {}

record Tag(@NotEmpty String value) {}
```

**Câu hỏi:** Có thể tạo `new Tag("")` không?

**Đáp án:** Có, nếu không có logic kiểm tra khác. `@NotEmpty` trong ví dụ chỉ là metadata. Record không tự sinh validation từ annotation tự định nghĩa.

## 14. Quy trình kiểm tra khi gặp vấn đề annotation trên record

Khi một công cụ báo “không tìm thấy annotation”, nên xác định lần lượt:

1. **Annotation định nghĩa `@Target` thế nào?** Có `RECORD_COMPONENT`, `FIELD`, `METHOD`, `PARAMETER` hoặc `TYPE_USE` phù hợp không?
2. **Annotation có `@Retention(RUNTIME)` không?** Nếu không, reflection runtime không đọc được.
3. **Công cụ đọc phần tử nào?** `RecordComponent`, `Field`, `Method`, `Parameter` hay `AnnotatedType`?
4. **Accessor có được khai báo tường minh không?** Nếu có, annotation từ header không tự lan truyền sang accessor.
5. **Canonical constructor thuộc dạng nào?** Ngầm định và compact dùng tham số suy ra; normal canonical constructor khai báo tham số độc lập.
6. **Annotation có nằm trong generic type argument hoặc array type không?** Nếu là `TYPE_USE`, kiểm tra đúng vị trí trong cây `AnnotatedType`.
7. **Framework có hỗ trợ record theo phiên bản đang dùng không?** Không suy đoán rằng việc Java hỗ trợ record sẽ tự động khiến mọi thư viện đọc metadata theo đúng nhu cầu.

Những bước này thường đủ để phân biệt lỗi ở cách viết annotation với sự khác biệt trong cơ chế đọc metadata của thư viện.

## 15. Tài liệu chính thức

- [Java Language Specification 17 — `8.10 Record Classes`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): cấu trúc record, component và các thành viên liên quan.
- [JLS 17 — `8.10.3 Record Members`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): annotation lan truyền sang component field và accessor ngầm định; khác biệt với accessor tường minh.
- [JLS 17 — `8.10.4 Record Constructor Declarations`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): danh sách tham số suy ra, compact và normal canonical constructor.
- [JLS 17 — `9.7.4 Where Annotations May Appear`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): vị trí hợp lệ của annotation declaration và type use.
- [JDK 17 API — `RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html): `getAnnotation`, `getAnnotatedType`, `getAccessor` và các API reflection khác.
- [JDK 17 API — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): đọc annotation trên vị trí sử dụng kiểu.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): cơ sở thiết kế và thời điểm chuẩn hóa record trong Java 16.

**Ghi nhớ:** Một annotation trong header của record có thể phục vụ nhiều ngữ cảnh, nhưng **không tự động hiện diện ở mọi nơi**. Hãy xác định `@Target` và `@Retention`, phân biệt declaration annotation với `TYPE_USE`, rồi xét accessor/canonical constructor có được tạo ngầm hay khai báo tường minh. Đó là chìa khóa để sử dụng annotation trên record ổn định và có thể dự đoán trong Java 17.
