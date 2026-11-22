# Annotation lặp ở khai báo hoặc vị trí sử dụng kiểu trong Java

Từ **Java 8**, Java hỗ trợ hai tính năng phối hợp chặt chẽ: **repeatable annotations** (`@Repeatable` — cho phép xuất hiện nhiều annotation cùng kiểu ở một vị trí) và **type annotations** (`@Target(ElementType.TYPE_USE)` — cho phép gắn annotation vào một kiểu được sử dụng trong mã). Điều dễ nhầm là annotation có thể mô tả **một khai báo** (*declaration*) hoặc mô tả **kiểu dữ liệu tại chỗ được sử dụng** (*type use*). Một kiểu annotation có thể hỗ trợ **cả hai**, nhưng đó không phải hai vị trí metadata đồng nhất.

Ví dụ hai trường hợp khác nhau:

```java
@Audit("reviewed")
@Audit("logged")
public String title() {
    return "Java";
}
```

Ở ví dụ này, giả sử `@Audit` có `@Target(ElementType.METHOD)`. Hai annotation đánh dấu **khai báo method** `title()`.

```java
public @TypeMark("non-null") @TypeMark("display") String title() {
    return "Java";
}
```

Ở đây, giả sử `@TypeMark` có `@Target(ElementType.TYPE_USE)`. Hai annotation gắn vào **kiểu trả về `String`**, không phải bản thân method declaration theo mục tiêu `METHOD`.

Cùng là hai annotation lặp, nhưng công cụ đọc metadata phải hỏi **đúng vị trí**:

- Khai báo method: `Method.getDeclaredAnnotationsByType(Audit.class)`.
- Kiểu trả về method: `Method.getAnnotatedReturnType().getAnnotationsByType(TypeMark.class)`.

Nội dung này giải thích cú pháp, ranh giới giữa hai nhóm ngữ cảnh, quy tắc `@Target` của annotation lặp và container, cách đọc reflection, tương tác với field/parameter/generic/array, những lỗi thường gặp và một chương trình chạy được bằng JDK 17+.

> **Phạm vi hiện hành:** các cơ chế `@Repeatable`, `TYPE_USE`, `AnnotatedType` và các API reflection `...AnnotationsByType` được giới thiệu từ Java 8, vẫn là thành phần của Java SE hiện đại. Không cần framework hoặc API legacy để sử dụng chúng. Annotation chỉ mang metadata; cơ chế kiểm tra hoặc xử lý nghiệp vụ phụ thuộc vào công cụ dùng metadata ấy.

## 1. Hai ngữ cảnh annotation cần phân biệt

### 1.1. Declaration annotation: mô tả thực thể được khai báo

Một **declaration annotation** nói về một phần tử được khai báo trong chương trình. Những target phổ biến:

| `ElementType` | Vị trí khai báo điển hình | Ví dụ ý nghĩa metadata |
| --- | --- | --- |
| `TYPE` | Khai báo class, interface, enum, record | Nhãn trạng thái của một kiểu |
| `METHOD` | Khai báo phương thức | Nhật ký, route, quy ước xử lý method |
| `FIELD` | Khai báo field | Cấu hình, mapping một thuộc tính |
| `PARAMETER` | Khai báo formal parameter | Quy tắc validate một tham số |
| `CONSTRUCTOR` | Khai báo constructor | Metadata về khởi tạo |
| `TYPE_PARAMETER` | Khai báo type parameter generic | Metadata dành cho tham số kiểu |
| `ANNOTATION_TYPE` | Khai báo annotation type | Metadata cho một annotation |
| `LOCAL_VARIABLE` | Khai báo biến cục bộ | Metadata sử dụng tại mức mã nguồn/công cụ |

Những hằng `ElementType` này có thể được kết hợp trong một `@Target({...})`. Không phải mọi annotation đều nên hỗ trợ mọi vị trí: target càng rộng, người sử dụng càng dễ gắn annotation vào nơi mà công cụ xử lý không mong đợi.

Ví dụ một annotation lặp trên method declaration:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Repeatable(Audits.class)
@interface Audit {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Audits {
    Audit[] value();
}
```

Các khai báo này cần các import `java.lang.annotation.*` tương ứng. Khi lặp hai `@Audit` trên một method, chúng là metadata của method declaration.

### 1.2. Type-use annotation: mô tả một kiểu tại vị trí được sử dụng

`ElementType.TYPE_USE` áp dụng cho các **type contexts** theo Java Language Specification, ví dụ:

- Kiểu của field, local variable hoặc formal parameter.
- Kiểu trả về của method, bao gồm các thành phần kiểu được annotation hợp lệ.
- Kiểu của một type argument trong generic: `List<@Mark String>`.
- Các thành phần kiểu mảng: `String @Mark []`.
- Kiểu receiver của instance method: `void work(@Mark Worker this)`.
- Kiểu dùng trong cast, `new`, `extends`, `implements` và các vị trí khác mà JLS xác định.

Ví dụ annotation lặp trên type use:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@Repeatable(TypeMarks.class)
@interface TypeMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMarks {
    TypeMark[] value();
}
```

Sau đó, ở ngữ cảnh hợp lệ:

```java
List<@TypeMark("normalized")
     @TypeMark("validated") String> names;
```

Hai `@TypeMark` mô tả **type argument `String`** trong `List<String>`, không phải bản thân field declaration hoặc kiểu `List` bên ngoài. Để lấy chúng bằng reflection, phải đi từ `Field.getAnnotatedType()` đến **type argument** tương ứng.

**Lưu ý:** bản thân hằng `TYPE_USE` không có nghĩa Java sẽ tự kiểm tra điều kiện “normalized” hoặc “validated”. Đây chỉ là tên metadata mà bạn hoặc một tool có thể diễn giải.

### 1.3. Một vị trí cú pháp có thể thuộc cả hai nhóm

Ví dụ khai báo field:

```java
@Mark String code;
```

Theo `@Target` của `Mark`, annotation ở vị trí này có thể được hiểu là:

1. Chỉ áp dụng cho **field declaration** khi `Mark` có target `FIELD` nhưng không `TYPE_USE`.
2. Chỉ áp dụng cho **type use của `String`** khi `Mark` có target `TYPE_USE` nhưng không `FIELD`.
3. Áp dụng **đồng thời** cho field declaration và type use khi `Mark` hỗ trợ cả `FIELD` lẫn `TYPE_USE` và ngữ cảnh thỏa luật JLS.

Cơ chế thứ ba quan trọng: cú pháp chỉ hiển thị một `@Mark` trước field nhưng có thể đóng góp metadata tới **hai nơi khác nhau** trong mô hình reflection/class file. Không được kết luận “annotation nằm trước field nên chắc chắn chỉ là declaration annotation”.

JLS cũng có các quy tắc đặc biệt cho annotation trên **class/interface/type parameter declaration** khi kiểu annotation chỉ khai báo `TYPE_USE`. Vì vậy, cách đọc chính xác luôn dựa trên **ngữ cảnh ngôn ngữ + `@Target`**, không chỉ dựa vào vị trí ký tự `@`.

## 2. `@Repeatable` là gì và container hoạt động ra sao?

Một repeatable annotation type cần chỉ ra **containing annotation type** bằng `@Repeatable(Container.class)`.

```java
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@interface Labels {
    Label[] value();
}
```

Trong một vị trí mà cả `Label` và `Labels` đều được phép dùng, Java cho phép:

```java
@Label("one")
@Label("two")
class Example {
}
```

Compiler biểu diễn nhiều `@Label` thông qua một **container annotation ngầm** có mảng `Labels.value()` chứa hai base annotation theo thứ tự xuất hiện.

Cú pháp tương đương về cấu trúc:

```java
@Labels({@Label("one"), @Label("two")})
class Example {
}
```

Hai ví dụ trên là **hai cách trình bày riêng**, không đặt cạnh nhau trên cùng một class declaration. Khi người dùng có nhu cầu thao tác container trực tiếp, họ có thể viết `@Labels` tường minh.

### 2.1. Điều kiện để container hợp lệ

Với `@Repeatable(Labels.class)` trên `Label`:

- Container `Labels` phải có **`Label[] value();`** — đúng tên `value` và đúng kiểu mảng.
- Nếu container có các annotation elements khác `value`, chúng phải có **default value**.
- Retention của container **không được ngắn hơn** retention của base annotation.
- `@Target` của container phải đáp ứng quy tắc tương thích với target của base annotation.
- Nếu base annotation có `@Documented`, container cũng phải có.
- Nếu base annotation có `@Inherited`, container cũng phải có.

Các điều kiện này được compiler kiểm tra. Một kiểu chỉ ghi `@Repeatable(X.class)` mà `X` không có `value()` phù hợp **không đủ** để làm annotation lặp hợp lệ.

### 2.2. Mối liên hệ giữa `@Target` của base và container

Khi bạn muốn lặp trên **method declarations**, cả base và container cần áp dụng được vào method declaration context. Cách viết dễ hiểu:

```java
@Target(ElementType.METHOD)
@Repeatable(Audits.class)
@interface Audit { String value(); }

@Target(ElementType.METHOD)
@interface Audits { Audit[] value(); }
```

Khi bạn muốn lặp trên **type uses**, cả base và container cần áp dụng được vào type context:

```java
@Target(ElementType.TYPE_USE)
@Repeatable(TypeMarks.class)
@interface TypeMark { String value(); }

@Target(ElementType.TYPE_USE)
@interface TypeMarks { TypeMark[] value(); }
```

Đừng viết `@Target(METHOD)` chỉ trên container rồi mong lặp `@TypeMark` bên trong generic `List<...>`: target `METHOD` không thích hợp cho type argument.

**Nuance của JLS:** target của base và container **không nhất thiết giống hệt nhau**. Container có thể áp dụng ở một tập vị trí hẹp hơn khi thỏa quan hệ `@Target` theo `9.6.3`; điều này cũng có thể làm **một số vị trí cho phép annotation đơn lẻ nhưng không cho phép nhiều annotation lặp**. Cách an toàn khi thiết kế API thông thường là cho hai kiểu cùng danh sách target phù hợp với nhu cầu thật.

### 2.3. Container của declaration và type use không “tự đổi chỗ”

Một container được tạo từ nhiều `@Audit` ở method declaration vẫn thuộc **declaration context**. Nó không biến thành annotation trên kiểu trả về chỉ vì method có return type.

Tương tự, nhiều `@TypeMark` nằm trước `String` của return type tạo metadata cho **type-use context**, không tự trở thành method declaration annotation.

Khi annotation type có `@Target({METHOD,TYPE_USE})`, cùng một chú thích ở vị trí trước return type có thể có hiệu lực ở cả hai ngữ cảnh theo JLS. Khi không muốn điều đó, hãy tách annotation types theo mục đích hoặc đặt annotation vào một vị trí không nhập nhằng.

## 3. Ví dụ declaration: annotation lặp trên class, method, field, parameter

### 3.1. Trên method declaration

```java
@Audit("security-review")
@Audit("performance-review")
public String perform(String input) {
    return input.trim();
}
```

Khai báo `Audit` có target `METHOD`, nên hai annotation thuộc method. Nếu có runtime retention:

```java
Method method = Service.class.getDeclaredMethod(
        "perform", String.class);

Audit[] reviews =
        method.getDeclaredAnnotationsByType(Audit.class);
```

`reviews.length == 2`, giữ thứ tự `security-review` rồi `performance-review`. Đoạn reflection giả định `Service` và `Audit` được khai báo hợp lệ cùng ngữ cảnh, và `Method` là `java.lang.reflect.Method`.

### 3.2. Trên class declaration

Với kiểu riêng:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Owners.class)
@interface Owner {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Owners {
    Owner[] value();
}

@Owner("platform")
@Owner("education")
class Catalog {
}
```

`Catalog.class.getDeclaredAnnotationsByType(Owner.class)` trả hai annotation theo đúng thứ tự. `TYPE` ở đây là target của **khai báo class/interface**, không nên nhầm với `TYPE_USE` của type argument `List<String>`.

### 3.3. Trên field declaration

Để gắn nhiều metadata lên chính field:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@Repeatable(Columns.class)
@interface Column {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Columns {
    Column[] value();
}

class RowData {
    @Column("public")
    @Column("indexed")
    String key;
}
```

Lúc reflection, hỏi `Field.getDeclaredAnnotationsByType(Column.class)`. Vì `Column` chỉ có `FIELD`, không phải `TYPE_USE`, nó không mô tả riêng kiểu `String`.

### 3.4. Trên formal parameter declaration

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@Repeatable(Checks.class)
@interface Check {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Checks {
    Check[] value();
}

class Form {
    void submit(@Check("required")
                @Check("trim") String name) {
    }
}
```

Ở đây annotation lặp thuộc **declaration của tham số `name`**. Có thể dùng `Method.getParameters()[0].getDeclaredAnnotationsByType(Check.class)` hoặc những API parameter declaration tương ứng. `Check` không tự gắn lên parameter type nếu target chỉ là `PARAMETER`.

**Ghi nhớ:** `PARAMETER` và `TYPE_USE` có thể cùng xuất hiện trước một kiểu tham số, nhưng là hai ý nghĩa khác nhau, và có thể cần hai đường reflection khác nhau.

## 4. Ví dụ type-use: kiểu trả về, tham số, generic và mảng

### 4.1. Kiểu trả về của phương thức

```java
class Sanitizer {
    public @TypeMark("trimmed")
           @TypeMark("printable") String sanitize(String input) {
        return input.trim();
    }
}
```

Hai annotation nằm **trước kiểu `String` trả về**, với `TypeMark` chỉ có `TYPE_USE`. Chúng gắn vào type use của return type. Reflection:

```java
Method method = Sanitizer.class.getDeclaredMethod(
        "sanitize", String.class);

TypeMark[] marks = method.getAnnotatedReturnType()
        .getAnnotationsByType(TypeMark.class);
```

`marks.length == 2`. Truy vấn `method.getDeclaredAnnotationsByType(TypeMark.class)` không thay thế được; nó hỏi method **declaration**, không hỏi kiểu trả về.

### 4.2. Kiểu của formal parameter

```java
class Sanitizer {
    void send(@TypeMark("raw")
              @TypeMark("external") String input) {
    }
}
```

Với `TypeMark` chỉ có `TYPE_USE`, dùng:

```java
Method method = Sanitizer.class.getDeclaredMethod(
        "send", String.class);

TypeMark[] marks =
        method.getAnnotatedParameterTypes()[0]
              .getAnnotationsByType(TypeMark.class);
```

Không nên dùng `method.getParameterAnnotations()` để thay thế hoàn toàn, vì đó là declaration annotations của parameter; khi cần type annotations, `getAnnotatedParameterTypes()` mới phản ánh đúng lớp metadata.

### 4.3. Type argument trong generic

```java
class Catalog {
    List<@TypeMark("trusted")
         @TypeMark("normalized") String> names;
}
```

Các annotation này thuộc **type argument `String`**, nằm **bên trong** kiểu `List<String>`. Để đọc:

```java
Field field = Catalog.class.getDeclaredField("names");

AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType) field.getAnnotatedType();

AnnotatedType elementType =
        listType.getAnnotatedActualTypeArguments()[0];

TypeMark[] marks =
        elementType.getAnnotationsByType(TypeMark.class);
```

`marks.length == 2` nếu annotation có `RUNTIME` retention. Việc hỏi `field.getAnnotatedType().getAnnotationsByType(...)` ở **tầng ngoài** có thể trả rỗng, vì annotation gắn vào **type argument**, không phải `List`.

Đây là một lỗi reflection thường gặp: *đọc đúng cây kiểu nhưng sai node*. `AnnotatedParameterizedType` cho phép đi vào các thành phần generic. Với kiểu lồng nhau như `Map<String,List<@TypeMark String>>`, cần đi qua nhiều cấp `AnnotatedType` tương ứng.

### 4.4. Mảng: annotate đúng cấp dimension

```java
class Data {
    String @TypeMark("array")
           @TypeMark("verified") [] values;
}
```

Trong cú pháp `String @TypeMark(...) []`, annotation gắn ở **cấp kiểu mảng** tương ứng, không phải declaration annotation của field.

`AnnotatedArrayType` đại diện cho kiểu mảng đã được annotate. Bạn có thể đọc `getAnnotationsByType` trên node mảng hoặc đi vào `getAnnotatedGenericComponentType()` khi muốn xem annotation trên kiểu phần tử. Với mảng nhiều chiều, mỗi nhóm `[]` có thể mang annotation của một dimension khác nhau; cần kiểm tra chính xác vị trí trong source và cây kiểu.

Không nhầm:

```java
@TypeMark("element") String[] names;
String @TypeMark("array") [] values;
```

Trong trường hợp đầu, `@TypeMark` trước `String` gắn vào **kiểu phần tử** theo quy tắc Java về các mức mảng; trong trường hợp sau, nó gắn vào cấp **array type**. Với annotation chỉ `TYPE_USE`, hai trường hợp không đồng nghĩa.

### 4.5. Type-use annotations trong cast, `new`, wildcard và receiver

Cú pháp minh họa (được đặt trong ngữ cảnh có các khai báo kiểu thích hợp):

```java
Object obj = "x";
String text = (@TypeMark("checked")
               @TypeMark("verified") String) obj;

List<@TypeMark("input")
     @TypeMark("safe") String> values = new ArrayList<>();

List<? extends @TypeMark("upper")
                   @TypeMark("bound") Number> numbers;
```

Java cho phép type annotations xuất hiện ở nhiều type context, kể cả cast type, type arguments và wildcard bounds theo luật JLS. Nhưng **không phải mọi vị trí type use đều có API core reflection để truy vấn như một `Field`**. Ví dụ cast expression bên trong thân method không có một `Method.getAnnotatedCastTypes()` phổ thông; công cụ có thể phải phân tích source hoặc bytecode.

Receiver parameter (Java 8) cũng là type-use context có ý nghĩa:

```java
class Processor {
    void run(@TypeMark("receiver")
             @TypeMark("audited") Processor this) {
    }
}
```

Với annotation có retention runtime, có thể đọc từ `Method.getAnnotatedReceiverType().getAnnotationsByType(TypeMark.class)`. Receiver parameter **không phải formal parameter**, nên không làm tăng `Method.getParameterCount()`.

## 5. Vị trí “cả declaration lẫn type use”: một annotation lặp được nhìn ở hai nơi

Giả sử bạn định nghĩa một annotation lặp có **hai target**:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.TYPE_USE})
@Repeatable(DualMarks.class)
@interface DualMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.TYPE_USE})
@interface DualMarks {
    DualMark[] value();
}
```

Sau đó:

```java
class Account {
    @DualMark("indexed")
    @DualMark("reviewed")
    String id;
}
```

Theo quy tắc Java, annotation ở vị trí trước field có thể vừa là **field declaration annotation** vừa là **annotation trên field type use**, vì `DualMark` và container `DualMarks` hỗ trợ cả `FIELD` lẫn `TYPE_USE`.

Lúc reflection, hai cách hỏi là **hai câu hỏi khác nhau**:

```java
Field field = Account.class.getDeclaredField("id");

DualMark[] declarationMarks =
        field.getDeclaredAnnotationsByType(DualMark.class);

DualMark[] typeMarks =
        field.getAnnotatedType()
             .getAnnotationsByType(DualMark.class);
```

Trong ví dụ này, hai mảng đều mô tả cùng hai nhãn ở hai ngữ cảnh tương ứng.

**Không suy ra rằng một lời khai báo khác có hai target sẽ luôn được công cụ đọc giống hệt ở mọi vị trí.** Các vị trí cú pháp và quy tắc “closest type” của JLS quyết định annotation áp dụng vào declaration, type use hay cả hai. Ví dụ khi viết `@TypeMark` trước kiểu generic, mục tiêu phải được xem trên đúng node generic hoặc đúng mức array.

### 5.1. Có nên thiết kế một annotation hỗ trợ cả hai target?

**Có**, nếu công cụ của bạn thực sự muốn cho phép hai cách hiểu nhất quán. Ví dụ một annotation dùng để ghi nhận chính field và type use của field.

**Nên tách hai annotation types** nếu hai ý nghĩa khác nhau:

- `@Persisted` trên field declaration: mô tả chiến lược lưu trữ field.
- `@Validated` trên kiểu `String`: mô tả tiêu chuẩn đầu vào của dữ liệu kiểu đó.

Khi tách, API đọc metadata rõ ràng và ít nhầm hơn. Một annotation “vừa lưu trữ vừa kiểm tra type” có thể khiến code xử lý phải phối hợp hai quy tắc không cùng bản chất.

## 6. Cơ chế compiler: container ở đúng ngữ cảnh

Trong một declaration context hợp lệ:

```java
@Audit("first")
@Audit("second")
void process() {}
```

Compiler coi các lần lặp như một annotation `@Audits` chứa mảng `Audit[]` theo thứ tự nguồn.

Trong một type context hợp lệ:

```java
@TypeMark("A") @TypeMark("B") String value;
```

Nếu `TypeMark` chỉ có `TYPE_USE`, compiler biểu diễn container ở **type-annotation location** thích hợp, khác với declaration-annotation location.

Ở mức class file, Java dùng các thuộc tính metadata phân biệt:

- `RuntimeVisibleAnnotations` / `RuntimeInvisibleAnnotations` cho declaration annotations tương ứng.
- `RuntimeVisibleTypeAnnotations` / `RuntimeInvisibleTypeAnnotations` cho type annotations tương ứng.

Chi tiết này lý giải tại sao một tool chỉ đọc declaration annotations có thể **không nhìn thấy** type-use metadata dù source code trông như annotation đứng trước field.

### 6.1. Retention quyết định mức độ có thể quan sát

| Retention | Ý nghĩa | Core reflection khi chạy |
| --- | --- | --- |
| `SOURCE` | Dùng tại nguồn; không yêu cầu lưu vào class file | Không thấy |
| `CLASS` | Lưu trong class file theo quy tắc annotation | Không phản chiếu trực tiếp như `RUNTIME` |
| `RUNTIME` | Dữ liệu được giữ để runtime API đọc ở những vị trí được hỗ trợ | Có, khi API hỏi đúng vị trí |

Để chương trình bên dưới quan sát được các annotation từ `Method`, `Field` và `AnnotatedType`, cả base annotation lẫn container được khai báo `@Retention(RUNTIME)`.

Một annotation có `@Target(TYPE_USE)` nhưng chỉ `@Retention(CLASS)` **không tự xuất hiện** khi bạn gọi `getAnnotatedReturnType().getAnnotationsByType(...)` ở runtime.

### 6.2. Không coi annotation là cơ chế kiểm tra bắt buộc

Gắn:

```java
List<@TypeMark("non-null")
     @TypeMark("trusted") String> values;
```

không làm Java tự cấm `null`, tự xác minh nguồn dữ liệu hoặc tự tẩy nội dung. `"non-null"`/`"trusted"` chỉ là giá trị String của annotation do người viết đặt. Một type-checker hoặc framework có thể định nghĩa ngữ nghĩa riêng, nhưng cần kiểm tra cụ thể khả năng hỗ trợ của công cụ đó.

Repeatable annotation chỉ làm một **kiểu metadata xuất hiện nhiều lần ở cùng một ngữ cảnh**, không kết hợp các quy tắc theo “AND” hay “OR” nếu bạn không tự định nghĩa.

## 7. Reflection: các điểm vào khác nhau

### 7.1. Annotation trên declaration

Các API như:

```java
Class.getDeclaredAnnotationsByType(...)
Method.getDeclaredAnnotationsByType(...)
Field.getDeclaredAnnotationsByType(...)
Parameter.getDeclaredAnnotationsByType(...)
```

đọc theo đối tượng **declaration** tương ứng. Tùy `@Inherited` và `getAnnotationsByType` so với `getDeclaredAnnotationsByType`, phạm vi tìm kiếm ở class có thể khác nhau. Với method và field, không giả định metadata từ superclass tự chuyển sang method/field override.

### 7.2. Annotation trên một kiểu

Các API tiêu biểu:

```java
Method.getAnnotatedReturnType()
Method.getAnnotatedParameterTypes()
Method.getAnnotatedReceiverType()
Field.getAnnotatedType()
Constructor.getAnnotatedParameterTypes()
```

chuyển bạn đến một `AnnotatedType`. Từ đó, hỏi:

```java
annotatedType.getAnnotationsByType(TypeMark.class)
```

để thu các annotation cùng repeatable type ở **đúng node type** đó.

Khi type phức tạp hơn:

- `AnnotatedParameterizedType` cho các type arguments: `getAnnotatedActualTypeArguments()`.
- `AnnotatedArrayType` cho thành phần của mảng: `getAnnotatedGenericComponentType()`.
- `AnnotatedWildcardType` cho các bounds: `getAnnotatedUpperBounds()` hoặc `getAnnotatedLowerBounds()`.
- `AnnotatedTypeVariable` cho bounds của type variable.

### 7.3. Đừng dùng sai API rồi kết luận annotation bị mất

Ví dụ field:

```java
List<@TypeMark("element")
     @TypeMark("checked") String> names;
```

Các lệnh sau không tương đương:

```java
Field field = Sample.class.getDeclaredField("names");

// Hỏi declaration của field:
TypeMark[] onField =
        field.getDeclaredAnnotationsByType(TypeMark.class);

// Hỏi type argument thứ nhất của generic List<String>:
AnnotatedParameterizedType type =
        (AnnotatedParameterizedType) field.getAnnotatedType();

TypeMark[] onElement =
        type.getAnnotatedActualTypeArguments()[0]
            .getAnnotationsByType(TypeMark.class);
```

Với `TypeMark` chỉ có `TYPE_USE`, `onField` rỗng, còn `onElement` có hai phần tử. Vì `AnnotatedType` là một **cây kiểu**, chọn nhầm cấp vẫn có thể khiến kết quả rỗng mà dữ liệu thực tế không mất.

### 7.4. `getAnnotation` khác `getAnnotationsByType`

Một repeatable annotation type có hai dạng hiện diện:

- Một annotation đơn lẻ có thể directly present.
- Nhiều annotation lặp thường được biểu diễn gián tiếp trong **container**.

Với nhiều annotation được chứa gián tiếp, `getAnnotation(Base.class)` không nhất thiết nhìn xuyên container. `getAnnotationsByType(Base.class)` và `getDeclaredAnnotationsByType(Base.class)` được thiết kế để nhận cả các annotation được chứa theo đúng quy tắc.

Đừng chỉ đếm số `getAnnotations()` trên declaration rồi suy ra số base annotations; bạn có thể nhận một container thay vì nhiều base annotations.

### 7.5. Trường hợp được phép nhưng dễ nhầm: một base và một container

JLS `9.7.5` **không cấm mọi cách đặt một base annotation cạnh một container annotation**. Nó cấm **nhiều base annotations** đồng thời có container trên cùng ngữ cảnh, đồng thời có những ràng buộc khi một base đi với nhiều container.

Do đó, thay vì ghi nhớ khẩu hiệu “không bao giờ được có `@Tag` cùng `@Tags`”, hãy hiểu rằng cách viết trộn có quy tắc chi tiết và **không nên sử dụng trong API thông thường vì dễ gây hiểu nhầm khi reflection**. Thực hành rõ ràng nhất là chọn **nhiều base annotations** hoặc **một container tường minh**, không trộn hai kiểu biểu diễn khi không thật sự cần.

## 8. Chương trình Java hoàn chỉnh: phân biệt declaration, type use và cả hai

Tạo tệp **`RepeatableContextsDemo.java`** dưới đây. Chương trình dùng API Java 8+, biên dịch/chạy trên JDK 17+ và không phụ thuộc thư viện bên ngoài.

Chương trình định nghĩa ba cặp annotation:

1. `Audit` / `Audits`: chỉ `METHOD` — metadata trên **declaration**.
2. `TypeMark` / `TypeMarks`: chỉ `TYPE_USE` — metadata trên **type use**.
3. `DualMark` / `DualMarks`: có cả `FIELD` và `TYPE_USE` — một vị trí có thể là **cả hai**.

Nó dùng reflection để đọc mỗi annotation từ đúng nơi:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public class RepeatableContextsDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @Repeatable(Audits.class)
    public @interface Audit {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Audits {
        Audit[] value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @Repeatable(TypeMarks.class)
    public @interface TypeMark {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeMarks {
        TypeMark[] value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.FIELD, ElementType.TYPE_USE})
    @Repeatable(DualMarks.class)
    public @interface DualMark {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.FIELD, ElementType.TYPE_USE})
    public @interface DualMarks {
        DualMark[] value();
    }

    static final class Sample {

        @DualMark("stored")
        @DualMark("reviewed")
        private String id = "A1";

        private List<@TypeMark("element-a")
                     @TypeMark("element-b") String> names =
                Arrays.asList("Ada", "Lin");

        @Audit("checked")
        @Audit("logged")
        public @TypeMark("trimmed")
               @TypeMark("displayed") String format(
                   @TypeMark("input")
                   @TypeMark("validated") String raw) {
            return raw.trim();
        }
    }

    public static void main(String[] args) throws Exception {
        Sample sample = new Sample();
        System.out.println("Call: " + sample.format(" Java "));

        Method format = Sample.class.getDeclaredMethod(
                "format", String.class);

        Audit[] audits =
                format.getDeclaredAnnotationsByType(Audit.class);
        System.out.println("Method audits: " + audits.length);
        System.out.println("First audit: " + audits[0].value());

        TypeMark[] onMethodDeclaration =
                format.getDeclaredAnnotationsByType(TypeMark.class);
        System.out.println("Type marks on method declaration: "
                + onMethodDeclaration.length);

        TypeMark[] onReturn =
                format.getAnnotatedReturnType()
                      .getAnnotationsByType(TypeMark.class);
        System.out.println("Return type marks: " + onReturn.length);
        System.out.println("First return mark: " + onReturn[0].value());

        TypeMark[] onParameterType =
                format.getAnnotatedParameterTypes()[0]
                      .getAnnotationsByType(TypeMark.class);
        System.out.println("Parameter type marks: "
                + onParameterType.length);

        TypeMark[] onParameterDeclaration =
                format.getParameters()[0]
                      .getDeclaredAnnotationsByType(TypeMark.class);
        System.out.println("Parameter declaration marks: "
                + onParameterDeclaration.length);

        Field id = Sample.class.getDeclaredField("id");
        System.out.println("Dual field declaration marks: "
                + id.getDeclaredAnnotationsByType(DualMark.class).length);
        System.out.println("Dual field type marks: "
                + id.getAnnotatedType()
                    .getAnnotationsByType(DualMark.class).length);

        Field names = Sample.class.getDeclaredField("names");
        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType) names.getAnnotatedType();
        AnnotatedType element =
                listType.getAnnotatedActualTypeArguments()[0];
        System.out.println("Generic element marks: "
                + element.getAnnotationsByType(TypeMark.class).length);
    }
}
```

Biên dịch và chạy:

```bash
javac RepeatableContextsDemo.java
java RepeatableContextsDemo
```

**Stdout dự kiến:**

```text
Call: Java
Method audits: 2
First audit: checked
Type marks on method declaration: 0
Return type marks: 2
First return mark: trimmed
Parameter type marks: 2
Parameter declaration marks: 0
Dual field declaration marks: 2
Dual field type marks: 2
Generic element marks: 2
```

**Giải thích:**

1. `format(" Java ")` trả `"Java"` do `trim()`; các annotation không làm thay đổi kết quả của method.
2. `format.getDeclaredAnnotationsByType(Audit.class)` trả hai annotation vì `Audit` có target `METHOD`. Thứ tự được giữ là `checked` rồi `logged`.
3. `format.getDeclaredAnnotationsByType(TypeMark.class)` trả rỗng vì `TypeMark` chỉ gắn vào type use ở ví dụ này.
4. `format.getAnnotatedReturnType()` chứa hai `TypeMark` của `String` trả về: `trimmed` và `displayed`.
5. `format.getAnnotatedParameterTypes()[0]` chứa hai `TypeMark` của kiểu formal parameter `String raw`. Nhưng `Parameter.getDeclaredAnnotationsByType(TypeMark.class)` không phải vị trí chứa type-use metadata này.
6. Field `id` có hai `DualMark`. Vì `DualMark` hỗ trợ cả `FIELD` và `TYPE_USE`, ta đọc được hai annotation trên **field declaration** và hai annotation trên **field type**.
7. Field `names` có kiểu ngoài là `List<...>`. Đi vào `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` mới thấy hai annotation trên **type argument `String`**.

Đoạn chương trình này minh họa về metadata, không hề định nghĩa cách thực thi logic kiểm tra `trimmed`, `displayed`, `stored` hay `validated`. Nếu muốn chúng có hiệu lực nghiệp vụ, một tool hoặc framework cần diễn giải riêng những nhãn ấy.

## 9. Những trường hợp dễ sai khi biên dịch

### 9.1. Repeatable có `TYPE_USE` nhưng container thiếu

```java
@Target(ElementType.TYPE_USE)
@Repeatable(TypeMarks.class)
@interface TypeMark {
    String value();
}

// KHÔNG HỢP LỆ nếu container chỉ có target METHOD:
@Target(ElementType.METHOD)
@interface TypeMarks {
    TypeMark[] value();
}
```

Cặp khai báo này không đáp ứng điều kiện container tương thích với base theo quy tắc JLS. Muốn lặp trong `List<@TypeMark ... String>`, container cần hỗ trợ type-use context thích hợp.

### 9.2. Type annotation được dùng trên method declaration với target không hợp lệ

Nếu annotation chỉ có target `METHOD`, không dùng nó như type argument:

```java
// KHÔNG BIÊN DỊCH:
// List<@Audit("wrong-target") String> labels;
```

`Audit` là declaration annotation dành cho method, không phải type-use annotation. Muốn gắn vào type argument, định nghĩa annotation riêng có `TYPE_USE` và container tương thích.

### 9.3. Khai báo generic mà đọc reflection ở sai node

```java
List<@TypeMark("a")
     @TypeMark("b") String> names;
```

Khi hỏi `Field.getDeclaredAnnotationsByType(TypeMark.class)`, kết quả rỗng; việc này **không có nghĩa compiler đã bỏ annotation**. Chúng nằm trên **type argument**. Hãy dùng `AnnotatedParameterizedType` và đi vào node `String`.

### 9.4. Nhầm `TYPE_PARAMETER` với `TYPE_USE`

`TYPE_PARAMETER` dùng ở **khai báo biến kiểu generic**, ví dụ `class Box<@Mark T>` khi `Mark` phù hợp. `TYPE_USE` dùng ở các vị trí sử dụng kiểu, chẳng hạn `List<@Mark String>`. Một annotation type chỉ có `TYPE_PARAMETER` không vì thế mà được gắn tùy ý lên mọi type argument trong mọi đoạn code.

### 9.5. Dùng sai retention rồi đòi hỏi reflection thấy metadata

Một annotation `SOURCE` hoặc `CLASS` không thể được kỳ vọng xuất hiện trực tiếp qua `getAnnotationsByType` của Reflection API theo cách `RUNTIME` hoạt động. Nếu mục tiêu là runtime reflection, khai báo retention `RUNTIME` nhất quán cho cả base và container.

### 9.6. Mất nhiều annotation do dùng API singular

`getAnnotation(TypeMark.class)` không có nhiệm vụ mở mọi container ngầm. Khi có nhiều annotation cùng kiểu, dùng `getAnnotationsByType(TypeMark.class)` hoặc `getDeclaredAnnotationsByType(TypeMark.class)` trên **đúng AnnotatedElement**.

### 9.7. Lẫn method declaration với method return type

`Method.getAnnotationsByType(Audit.class)` trả annotation trên method; `Method.getAnnotatedReturnType().getAnnotationsByType(TypeMark.class)` trả annotation trên return type. Không dùng hai phép đọc thay thế cho nhau.

### 9.8. Lạm dụng `@Target({METHOD, TYPE_USE})`

Khi cùng một annotation có thể áp dụng ở cả declaration và type use, metadata đôi khi xuất hiện ở cả hai chỗ. Nếu hai ý nghĩa nghiệp vụ tách biệt, nên tách hai annotation khác nhau để người đọc và công cụ reflection có giao diện rõ ràng.

### 9.9. Cho rằng type-use metadata được kiểm tra ở JVM theo tên nhãn

`@TypeMark("non-null")` không có nghĩa JVM tự từ chối `null`. Type-use annotation là dữ liệu mô tả. Muốn kiểm tra, cần công cụ có biết ý nghĩa annotation và tích hợp nó vào chu trình build hoặc runtime.

### 9.10. Cho rằng mọi type use đều có đối tượng reflection

Runtime reflection có khả năng đọc type annotations ở các phần tử class/method/field và nhiều thành phần kiểu được biểu diễn. Nhưng type uses của **local variable, cast, new expression** không có API core reflection một-một tương tự `Field.getAnnotatedType()`. Muốn phân tích chúng, thường cần source processing hoặc class-file processing thích hợp.

### 9.11. Trộn base với container và nghĩ luôn được phép hoặc luôn bị cấm

JLS `9.7.5` có các giới hạn chính xác. **Nhiều base annotations cùng kiểu cộng với container** ở cùng một context là lỗi. Nhưng **một** base và **một** container không tự bị cấm chỉ bởi quan hệ này. Dù được luật cho phép, tránh thiết kế nhập nhằng khiến trình đọc metadata có thể xử lý bất ngờ.

## 10. Khi nào chọn declaration annotation, khi nào chọn type-use annotation?

| Câu hỏi nghiệp vụ | Lựa chọn thường phù hợp | Vị trí Reflection |
| --- | --- | --- |
| “Method này được audit ở hai bước” | Repeatable `@Target(METHOD)` | `Method.getAnnotationsByType` |
| “Field này được map tới hai nhãn cấu hình” | Repeatable `@Target(FIELD)` | `Field.getAnnotationsByType` |
| “Kiểu kết quả của method mang hai điều kiện dữ liệu” | Repeatable `@Target(TYPE_USE)` trên return type | `Method.getAnnotatedReturnType()` |
| “Type argument `String` trong `List` có hai nhãn” | Repeatable `@Target(TYPE_USE)` trên type argument | `AnnotatedParameterizedType` |
| “Formal parameter có hai nhãn validate ở mức declaration” | Repeatable `@Target(PARAMETER)` | `Parameter.getAnnotationsByType` |
| “Kiểu của parameter được gắn hai nhãn” | Repeatable `@Target(TYPE_USE)` | `Method.getAnnotatedParameterTypes()` |
| “Một field cần cả hai nghĩa declaration và type” | `@Target({FIELD, TYPE_USE})` nếu có lý do | `Field` và `Field.getAnnotatedType()` |
| “Receiver của instance method mang hai nhãn kiểu” | `TYPE_USE` trên `TypeName this` | `Method.getAnnotatedReceiverType()` |
| “Type use ở cast trong method body” | `TYPE_USE`, công cụ phân tích mã | Không có core reflection API trực tiếp cho cast expression |

### 10.1. Tại sao phân biệt vị trí rất quan trọng?

Giả sử một framework dùng `@Tag` cho cả field mapping lẫn type constraints. Nếu nó chỉ đọc `Field.getAnnotations()`, nó có thể bỏ sót annotations đặt trên type argument hoặc array component. Ngược lại, nếu nó chỉ đọc `Field.getAnnotatedType()`, nó có thể bỏ sót các metadata declaration-only. Điều này có thể gây lỗi ở validation, serialization, schema generation hoặc các công cụ phân tích tĩnh.

Một triển khai đúng phải định nghĩa **vị trí annotation mà framework hỗ trợ** rồi dùng đúng đường đọc metadata. Không nên coi danh sách annotation của Java là một “túi metadata” phẳng cho mọi ngữ cảnh.

## 11. Checklist thiết kế và review

1. **Mục tiêu là declaration hay type use?** Viết rõ định nghĩa nghiệp vụ của annotation.
2. **`@Target` đã đúng chưa?** Dùng `METHOD/FIELD/PARAMETER` cho declaration tương ứng; `TYPE_USE` cho các vị trí dùng kiểu.
3. **Có thực sự cần repeatable không?** Nếu chỉ cần một metadata, không thêm `@Repeatable` vô ích.
4. **Base annotation chỉ đúng container chưa?** `@Repeatable(Container.class)`.
5. **Container có đúng `Base[] value()` không?** Kiểu trả về bắt buộc là mảng của base annotation.
6. **Các element phụ container có default chưa?** Compiler cần tạo container ngầm khi lặp.
7. **Target của container tương thích với base và vị trí định lặp chưa?** Không mặc định hai target phải giống hệt; kiểm tra JLS.
8. **Retention đủ dài chưa?** Nếu cần runtime reflection, cả base và container nên có `RUNTIME`.
9. **`@Documented` và `@Inherited` đã thỏa ràng buộc chưa?** Khi base có, container cần có tương ứng.
10. **Khi đọc declaration, có dùng đúng `Method/Field/Parameter` chưa?** Không lấy `AnnotatedType` thay cho mọi declaration.
11. **Khi đọc type use, có đi đúng `AnnotatedType` node chưa?** Return type, parameter type, generic argument, array dimension và receiver là các vị trí riêng.
12. **Có dùng `...AnnotationsByType` để lấy đủ annotation lặp không?** Đừng chỉ dùng singular `getAnnotation`.
13. **Khi một vị trí có thể là cả declaration và type use, công cụ có xử lý cả hai không?** Xác định chính sách tránh đọc trùng hay bỏ sót.
14. **Metadata có tự áp đặt hành vi không?** Không; cần checker/framework cụ thể.
15. **Đã viết test cho một annotation, hai annotation, container tường minh và sai target chưa?** Test cả cách lưu trữ và cách đọc.
16. **Đã xác nhận source level và API chưa?** Java 8+ hỗ trợ repeatable/type annotations; code ở bài dùng cú pháp cũ vẫn còn hợp lệ trong JDK mới.

## 12. Tự kiểm tra

1. `@Target(METHOD)` và `@Target(TYPE_USE)` khác nhau thế nào khi annotation xuất hiện trước return type của method?
2. Hai `@TypeMark` đặt trong `List<@TypeMark String>` nên đọc qua `Field.getAnnotationsByType` hay qua `AnnotatedParameterizedType`?
3. Tại sao container cho `@Repeatable(TypeMarks.class)` cần đúng `TypeMark[] value()`?
4. Nếu base có `RUNTIME` nhưng container có `CLASS` thì có vấn đề gì?
5. Với `@Target({FIELD,TYPE_USE})`, vì sao một annotation trước field có thể được quan sát ở cả field declaration và field type?
6. Vì sao `getAnnotation(Base.class)` có thể trả null trong khi `getAnnotationsByType(Base.class)` lại trả hai annotation?
7. Nếu một annotation mang tên `"non-null"` nằm trên type use, Java có tự kiểm tra null không?
8. Vì sao annotation trên cast trong thân method có thể cần class-file/source tooling thay vì core reflection?
9. Có phải mọi cách trộn một base annotation với container của nó đều bị JLS cấm không?
10. Nếu muốn annotation trên generic parameter declaration, hằng `TYPE_PARAMETER` tương ứng với ngữ cảnh nào?

**Kết luận:** `@Repeatable` trả lời **“được viết bao nhiêu annotation cùng kiểu ở một vị trí?”**, còn `@Target` và ngữ cảnh JLS trả lời **“vị trí ấy là declaration hay type use?”**. Một container hợp lệ cho phép lặp, nhưng metadata phải được đọc từ **đúng loại phần tử và đúng node kiểu**. Hãy thiết kế mục tiêu áp dụng tường minh, giữ retention phù hợp và dùng `getAnnotationsByType` trên `Method/Field/Parameter` hoặc `AnnotatedType` theo đúng ý nghĩa annotation.

## Tài liệu tham khảo chuẩn

- Java Language Specification (Java SE 26), **`9.7.4 — Where Annotations May Appear**: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.7.4
- Java Language Specification (Java SE 26), **`9.7.5 — Multiple Annotations of the Same Interface**: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.7.5
- Java Language Specification (Java SE 26), **`9.6.3 — Repeatable Annotation Interfaces**: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.6.3
- Java SE 25 API, **`java.lang.annotation.ElementType`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html
- Java SE 25 API, **`java.lang.reflect.AnnotatedType`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedType.html
- Java SE 25 API, **`java.lang.reflect.AnnotatedParameterizedType`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html
