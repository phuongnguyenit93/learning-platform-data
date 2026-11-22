# Type annotation: Retention và phạm vi nhìn thấy lúc biên dịch, runtime trong Java

**Type annotation** cho phép gắn annotation vào **vị trí sử dụng một kiểu** (*type use*), không chỉ trên khai báo class, field hay method. Ví dụ, annotation có thể nằm ở đối số kiểu generic trong `List<@Checked String>`, ở kiểu trả về của method, trên phần tử hoặc chiều của mảng, hay tại khai báo type parameter. Cơ chế này được chuẩn hóa từ Java 8, vẫn dùng trong Java hiện đại, và đặc biệt có giá trị cho những công cụ phân tích tĩnh hoặc những thư viện cần lưu siêu dữ liệu của kiểu.

Một annotation xuất hiện trong mã nguồn **không tự động có thể đọc được ở runtime**. Điều đó phụ thuộc trước hết vào **retention policy** được khai báo bằng `@Retention`, sau đó phụ thuộc **vị trí đặt annotation** (target) và khả năng của API dùng để đọc nó.

Ba retention policy trong `java.lang.annotation.RetentionPolicy`:

1. **`SOURCE`**: có trong source; không được giữ lại ở tệp `.class`.
2. **`CLASS`**: được lưu vào `.class` nhưng không được cung cấp cho **Java core reflection** tại runtime. Đây là retention mặc định nếu không khai báo `@Retention`.
3. **`RUNTIME`**: được lưu vào `.class` và có thể truy xuất qua **các reflection API thích hợp**, nếu loại vị trí được annotation đó hỗ trợ phản chiếu.

Điểm quan trọng: “retained at runtime” **không có nghĩa JVM tự thực thi quy tắc nghiệp vụ** hoặc mọi annotation ở mọi vị trí đều có một phương thức reflection để đọc. Bài này giải thích rõ từng ranh giới theo Java 17+ và các JDK hiện đại.

## 1. Phân biệt retention và target: hai câu hỏi độc lập

Java cung cấp hai meta-annotation quan trọng:

- `@Target`: annotation **được phép đặt ở đâu**.
- `@Retention`: annotation **được giữ đến giai đoạn nào**.

Ví dụ một type-use annotation có thể đọc qua reflection:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeTypeNote {
    String value();
}
```

Đây là **định nghĩa minh họa**, không có phương thức `main`. `ElementType.TYPE_USE` cho phép annotation xuất hiện ở vị trí sử dụng kiểu, còn `RetentionPolicy.RUNTIME` quy định độ tồn tại của siêu dữ liệu.

Ví dụ một annotation chỉ dùng cho quá trình biên dịch:

```java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.SOURCE)
@interface CompileTypeNote {
}
```

Đây là minh họa dùng các import ở trên. Nó cũng có thể được viết trên type use, nhưng Java compiler **không lưu** chính annotation đó vào class file sau khi biên dịch.

**Bảng tư duy:**

| Câu hỏi | Cơ chế quyết định | Ví dụ |
| --- | --- | --- |
| Có được đặt trên đối số kiểu `List<...>` không? | `@Target(TYPE_USE)` | `List<@RuntimeTypeNote("element") String>` |
| Có được đặt trên khai báo method không? | `@Target(METHOD)` | `@Deprecated` trên khai báo method |
| Có được đặt trên khai báo type parameter không? | `@Target(TYPE_PARAMETER)` hoặc phạm vi `TYPE_USE` theo luật áp dụng | `class Box<@Mark T>` |
| Có còn trong bytecode không? | `@Retention` | `CLASS` và `RUNTIME` được giữ trong `.class` |
| Core reflection có thấy được không? | `@Retention(RUNTIME)` **và API thích hợp** | `Field.getAnnotatedType()` |
| Annotation có tự kiểm tra null không? | **Không phải do retention** | Cần checker, framework hoặc code kiểm tra |

Một số annotation áp dụng cho cả declaration lẫn type use; các vị trí có cú pháp trông gần giống nhau nhưng ý nghĩa siêu dữ liệu khác nhau. Đừng suy luận retention từ vị trí đặt annotation.

## 2. RetentionPolicy.SOURCE: chỉ tồn tại ở giai đoạn nguồn

`SOURCE` phù hợp với thông tin phục vụ compiler, annotation processor hoặc công cụ kiểm tra mã nguồn, khi không muốn lưu thông tin đó vào binary artifact.

```java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.SOURCE)
@interface SourceOnly {
    String reason();
}

class Sample {
    java.util.List<@SourceOnly(reason = "review") String> names;
}
```

Đây là các **định nghĩa minh họa**, cần những import annotation ở mục trước. Trong source có `@SourceOnly` trên đối số kiểu `String`. Annotation processor hoặc công cụ phân tích nguồn có thể đọc thông tin này **trong quá trình biên dịch** qua model API thích hợp; khi compiler tạo `.class`, annotation `SOURCE` đó không được emit.

### Compiler có thể thấy SOURCE, nhưng không có nghĩa mọi công cụ tự xử lý nó

Một annotation processor chạy trong quá trình biên dịch có quyền tiếp cận model của source theo JSR 269, nhưng **việc annotation được nhìn thấy** không đồng nghĩa Java compiler có một luật mặc định tự kiểm tra `reason` hay từ chối code.

Muốn có tác dụng cụ thể, cần:

1. Một annotation processor hoặc static analyzer được cấu hình để đọc annotation;
2. Logic xác thực đủ các vị trí cần kiểm tra;
3. Quy tắc chẩn đoán lỗi/cảnh báo được công cụ thực hiện.

Annotation thuần túy chỉ là **metadata**. `@Retention(SOURCE)` không phải “bật chế độ static type checking” cho bất kỳ annotation tùy biến nào.

### SOURCE có thể dùng cho type-use annotation không?

**Có.** `@Target(TYPE_USE)` và `@Retention(SOURCE)` không mâu thuẫn. Một checker chuyên dụng có thể quan sát các vị trí sử dụng kiểu trong nguồn và báo vấn đề trước khi chạy chương trình.

Hạn chế: công cụ chỉ có thể phân tích thông tin mà compiler/model/source reader thực sự cung cấp. Không phải mọi vị trí type use đều xuất hiện như **một Element được đánh dấu annotation ở cấp khai báo**; đôi khi cần duyệt **TypeMirror** và các đối số kiểu/bounds của nó.

## 3. RetentionPolicy.CLASS: còn trong .class, không có trong core reflection

`CLASS` phù hợp với metadata cần được giữ trong bytecode để những công cụ phân tích binary, compiler đọc thư viện phụ thuộc, trình biến đổi bytecode hoặc các công cụ xây dựng có thể xem xét.

```java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.CLASS)
@interface BinaryNote {
}

class BinarySample {
    java.util.List<@BinaryNote String> names;
}
```

Đây là định nghĩa minh họa. Annotation `@BinaryNote` có thể được ghi vào `.class` dưới dạng **type annotation attribute** không hiển thị qua core reflection. `getAnnotatedType()` vẫn có thể mô tả cấu trúc `List<String>`, nhưng **không trả `BinaryNote`** ở type argument.

### CLASS là retention mặc định

Nếu không viết `@Retention` cho một annotation type, Java sử dụng **`RetentionPolicy.CLASS`** theo quy định của JLS và `Retention` API. Ví dụ:

```java
@Target(ElementType.TYPE_USE)
@interface DefaultRetentionTag {
}
```

Trong đoạn minh họa này, `DefaultRetentionTag` có retention `CLASS`, không phải `RUNTIME`. Một lỗi phổ biến là định nghĩa annotation tùy biến chỉ với `@Target(TYPE_USE)` rồi mong `field.getAnnotatedType().getAnnotation(...)` trả về nó. Nếu cần phản chiếu ở runtime, hãy khai báo `@Retention(RUNTIME)` rõ ràng.

### “Không thấy trong reflection” không đồng nghĩa annotation không có trong .class

Java class file dùng các thuộc tính mô tả type annotations, chẳng hạn:

- `RuntimeVisibleTypeAnnotations`: phục vụ các type annotations lưu với `RUNTIME`.
- `RuntimeInvisibleTypeAnnotations`: có thể chứa type annotations được lưu với `CLASS`.

Tên *RuntimeInvisible* có nghĩa là **không được truy xuất bằng Java core reflection**, không có nghĩa các byte trong class file không tồn tại. Công cụ đọc class file vẫn có thể truy vấn thuộc tính phù hợp.

Để kiểm tra file sau khi compile, có thể dùng:

```bash
javac -g Example.java
javap -v -p Example
```

Đây là **lệnh minh họa**, chỉ dùng khi có file `Example.java` tương ứng; tên file trong ví dụ độc lập cuối bài sẽ khác. `javap -v` cho phép xem metadata class file, nhưng index, constant pool và vị trí attribute thay đổi theo compiler và code, nên không nên ghi nhớ những số thứ tự cụ thể.

## 4. RetentionPolicy.RUNTIME: metadata có thể truy xuất qua reflection

Với `RUNTIME`, annotation được giữ trong class file và Java reflection có thể lấy ra **trên những phần tử/vị trí nó hỗ trợ**. Đối với type annotations, thường phải truy cập **`AnnotatedType`**, không chỉ những hàm phản chiếu declaration truyền thống.

```java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeTag {
    String value();
}

class Registry {
    java.util.List<@RuntimeTag("element") String> items;
}
```

Các định nghĩa minh họa này cần import `java.lang.annotation.*;`. Cách đọc annotation trên **đối số kiểu generic**:

```java
java.lang.reflect.Field field =
        Registry.class.getDeclaredField("items");

java.lang.reflect.AnnotatedParameterizedType type =
        (java.lang.reflect.AnnotatedParameterizedType)
                field.getAnnotatedType();

java.lang.reflect.AnnotatedType elementType =
        type.getAnnotatedActualTypeArguments()[0];

RuntimeTag annotation = elementType.getAnnotation(RuntimeTag.class);
System.out.println(annotation.value()); // element
```

Đây là **đoạn minh họa nằm trong ngữ cảnh có thể ném `NoSuchFieldException`**. `Field.getAnnotatedType()` mô tả **kiểu của field**, `AnnotatedParameterizedType` cho phép truy cập các type arguments, và `getAnnotation` trên argument type mới truy vấn đúng `@RuntimeTag("element")`.

### Vì sao Field.getAnnotation có thể không thấy?

```java
Field field = Registry.class.getDeclaredField("items");

// Annotation gắn vào type argument String, không gắn vào field declaration.
System.out.println(field.getAnnotation(RuntimeTag.class)); // null
```

Đây là đoạn minh họa cần `java.lang.reflect.Field` và class `Registry` ở trên. `Field.getAnnotation` hỏi “khai báo field này có annotation đó không?”. Nhưng metadata nằm trên **String ở bên trong List**; hai vị trí khác nhau.

Đối với annotation chỉ có `@Target(TYPE_USE)`, phương thức truy cập annotation trên **type** thường nằm ở `getAnnotatedType()`/các subclass của `AnnotatedType`. Nếu muốn annotation trên bản thân khai báo field, đó là ngữ cảnh **`FIELD`**, không phải tùy tiện dùng API của declaration để đọc type-use annotation.

## 5. Ba retention policy trên cùng kiểu sử dụng: so sánh trực tiếp

Giả sử có ba annotation types cùng chỉ cho phép `TYPE_USE`:

```java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.SOURCE)
@interface SourceTag {}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.CLASS)
@interface ClassTag {}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeTag {}
```

Đây là **minh họa độc lập về khai báo**, không dùng đồng thời trong file ví dụ hoàn chỉnh nếu đã có tên `RuntimeTag` khác. Khi được đặt vào một type argument, mức độ lưu giữ khác nhau:

| Đặc điểm | `SOURCE` | `CLASS` | `RUNTIME` |
| --- | --- | --- | --- |
| Có mặt trong mã nguồn | Có | Có | Có |
| Compiler/source tooling có thể phân tích khi biên dịch | Có | Có | Có |
| Lưu vào class file | Không | Có | Có |
| Java core reflection có thể đọc từ vị trí type use được hỗ trợ | Không | Không | Có |
| Bytecode reader xem được annotation sau compile | Không | Có | Có |
| JVM tự enforce luật @NonNull/@Readonly do người dùng đặt | Không | Không | Không |

Bảng mô tả **retention**, không phải bảo đảm mọi annotation processor đều tự quét mọi type use. Cũng không phải mọi vị trí type use có một đối tượng Reflection API tương đương; xem phần giới hạn bên dưới.

### Khi nào nên chọn policy nào?

- **`SOURCE`:** chú thích chỉ dành cho kiểm tra tại thời điểm build hoặc phân tích nguồn, không cần binary metadata.
- **`CLASS`:** công cụ phân tích/biến đổi class file cần thông tin, nhưng ứng dụng không cần Java core reflection lấy annotation.
- **`RUNTIME`:** thư viện hoặc công cụ runtime cần truy vấn một vị trí được reflection hỗ trợ, ví dụ type argument của một field hay kiểu trả về của method.

Không nên chọn `RUNTIME` “cho chắc” nếu không có consumer cần metadata lúc chạy. Nó ảnh hưởng kích thước metadata và tạo ra một contract giữ annotation trong artifact; còn `SOURCE` khiến thông tin không tồn tại ở class file, nên hoàn toàn không dùng được để phân tích dependency **chỉ có compiled binary**.

## 6. Declaration annotation và type-use annotation: hai nơi lưu khác nhau

Xét khai báo field:

```java
@Target(ElementType.FIELD)
@Retention(RetentionPolicy.RUNTIME)
@interface FieldDescription {
    String value();
}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface QualifiedType {
    String value();
}

class Customer {
    @FieldDescription("customer display name")
    java.util.List<@QualifiedType("nonempty-name") String> names;
}
```

Đây là **minh họa**, cần import annotation. `@FieldDescription` gắn vào **declaration** của field `names`; `@QualifiedType` gắn vào **type argument** `String`.

Hai đường truy vấn khác nhau:

```java
Field field = Customer.class.getDeclaredField("names");

FieldDescription declaration =
        field.getAnnotation(FieldDescription.class);

AnnotatedParameterizedType parameterized =
        (AnnotatedParameterizedType) field.getAnnotatedType();

QualifiedType argument =
        parameterized.getAnnotatedActualTypeArguments()[0]
                .getAnnotation(QualifiedType.class);
```

Đoạn minh họa cần import `java.lang.reflect.*;`, chứa trong ngữ cảnh xử lý `NoSuchFieldException`. **Không thể** chỉ dùng `getAnnotations()` trên `Field` rồi kết luận “các type annotations của field không tồn tại”; thực chất bạn có thể đang hỏi **sai vị trí**.

### TYPE_USE không chỉ là “annotation của field”

Các vị trí sử dụng kiểu có thể gồm:

```java
List<@QualifiedType("argument") String> values;

@QualifiedType("result") String find() {
    return "Java";
}

String @QualifiedType("array-dimension") [] names;
```

Đây là các **đoạn minh họa**, cần đặt trong class và import `List`; `QualifiedType` như đã định nghĩa. Với `String @QualifiedType("array-dimension") []`, annotation nằm trên **mảng/chiều mảng**, không nhất thiết nằm trên component type `String`. Java phân biệt các level của một array type; hãy đọc cấu trúc `AnnotatedArrayType` tương ứng thay vì đoán vị trí.

## 7. Những reflection API quan trọng dành cho type annotations

Java cung cấp các interface trong `java.lang.reflect` để phản chiếu cấu trúc annotated type:

| API | Vai trò |
| --- | --- |
| `Field.getAnnotatedType()` | Kiểu được khai báo của field, kèm những type annotations runtime có thể truy xuất |
| `Method.getAnnotatedReturnType()` | Kiểu trả về của method |
| `Executable.getAnnotatedParameterTypes()` | Kiểu của các tham số method/constructor |
| `Executable.getAnnotatedExceptionTypes()` | Các kiểu ngoại lệ trong `throws` |
| `Executable.getAnnotatedReceiverType()` | Receiver type được khai báo khi có |
| `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` | Type arguments, ví dụ `String` trong `List<@Tag String>` |
| `AnnotatedArrayType.getAnnotatedGenericComponentType()` | Component type của array; dùng khi annotation ở phần tử hoặc chiều khác |
| `AnnotatedWildcardType.getAnnotatedUpperBounds()` / `getAnnotatedLowerBounds()` | Các bounds có annotation của wildcard |
| `AnnotatedTypeVariable.getAnnotatedBounds()` | Các bounds của type variable |
| `TypeVariable.getAnnotatedBounds()` | Annotated bounds trong khai báo type parameter |

Không nhầm những phương thức trên với `getGenericType()` hoặc `getGenericReturnType()`: các phương thức generic phản ánh **cấu trúc type**, trong khi `getAnnotatedType()` và các API tương ứng cho phép truy vấn **runtime type-use annotations**.

### Ví dụ type argument lồng nhau

```java
class Container {
    java.util.Map<String,
            java.util.List<@RuntimeTag("inner") Integer>> values;
}
```

Đây là minh họa và giả định `RuntimeTag` có `@Target(TYPE_USE)`/`@Retention(RUNTIME)`. Để lấy annotation `inner`, cần duyệt từ kiểu field `Map<..., ...>` đến type argument thứ hai là `List<...>`, rồi tới type argument `Integer`:

```java
AnnotatedParameterizedType mapType =
        (AnnotatedParameterizedType)
                Container.class.getDeclaredField("values")
                        .getAnnotatedType();

AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType)
                mapType.getAnnotatedActualTypeArguments()[1];

RuntimeTag tag = listType.getAnnotatedActualTypeArguments()[0]
        .getAnnotation(RuntimeTag.class);
```

Đây là minh họa cần `java.lang.reflect.AnnotatedParameterizedType`, xử lý `NoSuchFieldException` và khai báo `RuntimeTag`. Việc cần đi qua **hai cấp generic** minh họa tại sao reflection chỉ nhìn field declaration không đủ.

## 8. Type parameter declaration và annotated bounds

Có hai kiểu vị trí dễ bị nhầm:

1. **Khai báo type parameter** như `class Box<@Mark T>`.
2. **Kiểu trong bound của type parameter** như `class Box<T extends @Mark Number>`.

Để chỉ định annotation rõ cho vị trí thứ nhất, dùng `ElementType.TYPE_PARAMETER`; với kiểu trong bound, dùng `ElementType.TYPE_USE`.

```java
@Target(ElementType.TYPE_PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface ParameterMark {
}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface BoundMark {
    String value();
}

class NumberBox<@ParameterMark T extends @BoundMark("positive-range") Number> {
}
```

Đây là **định nghĩa minh họa**, cần import `java.lang.annotation.*;`. Java core reflection có các đường đọc phù hợp:

```java
java.lang.reflect.TypeVariable<?> typeVar =
        NumberBox.class.getTypeParameters()[0];

boolean marked = typeVar.isAnnotationPresent(ParameterMark.class);

BoundMark bound = typeVar.getAnnotatedBounds()[0]
        .getAnnotation(BoundMark.class);
```

Đoạn minh họa dùng class/annotation ở trên. `marked` là `true`, `bound.value()` là `"positive-range"`. Dù cả hai đều được chú thích bằng ký pháp `@...` trong source, chúng nằm trên **hai loại vị trí khác nhau**.

**Lưu ý về ngữ nghĩa:** `@BoundMark("positive-range")` ở đây chỉ là metadata. JVM không tự kiểm tra rằng mọi `Number` có giá trị dương. Muốn có constraint thực thi, phải sử dụng checker/framework tương ứng hoặc code validation rõ ràng.

## 9. Giới hạn runtime reflection: không phải mọi TYPE_USE đều được phản chiếu

Đây là một trong những điểm dễ hiểu sai nhất của retention.

Ví dụ có thể đặt annotation ở type use của biến cục bộ, cast hoặc biểu thức tạo object (khi hợp lệ về cú pháp):

```java
void work() {
    @RuntimeTag("local") String text = "hello";
    Object result = (@RuntimeTag("cast") String) text;
    System.out.println(result);
}
```

Đây là **phương thức minh họa**, giả định `RuntimeTag` có `TYPE_USE` và `RUNTIME`.

Ngay cả khi compiler lưu runtime type annotation ở một số vị trí trong **Code attribute** của class file, **Java core reflection không cung cấp API tổng quát để hỏi type-use annotation của mọi local variable, cast hoặc biểu thức** trong body method. Không thể gọi `Method.getAnnotatedLocalVariableTypes()` vì **không có** API như vậy.

Muốn phân tích các vị trí này, thường cần:

- Công cụ nguồn/AST trong giai đoạn compile;
- Model và plugin/compiler API phù hợp;
- Công cụ đọc bytecode và `RuntimeVisibleTypeAnnotations`/`RuntimeInvisibleTypeAnnotations` ở những vị trí thực sự được lưu.

Do đó, câu “RUNTIME thì reflection thấy **mọi nơi**” là **sai**. Đúng hơn là “RUNTIME đủ điều kiện để những reflection API **được hỗ trợ** lấy annotation từ metadata runtime”.

### Reflection không thực thi quy tắc validation

```java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface NonNullByConvention {}

class Example {
    @NonNullByConvention String name;
}
```

Đây là minh họa; compiler không tự bảo đảm `name` khác `null` chỉ vì annotation mang tên `NonNullByConvention`. Không có cơ chế mặc định trong Java SE yêu cầu JVM từ chối `null` dựa trên một annotation tùy biến như vậy. Các công cụ phân tích nullness và framework có ngữ nghĩa riêng, phụ thuộc cấu hình và quy tắc của chúng.

## 10. Visibility ở thời điểm biên dịch: Annotation Processing API

**JSR 269** cung cấp API annotation processing hiện còn được dùng trong JDK hiện đại: `javax.annotation.processing`, `javax.lang.model.element`, `javax.lang.model.type`, `javax.lang.model.util`. Prefix `javax` ở đây là tên package chuẩn của Java SE, **không phải dấu hiệu API lỗi thời**.

Trong giai đoạn compile, annotation processor có thể duyệt:

- **Element**: khai báo class, method, field, type parameter...
- **TypeMirror**: biểu diễn kiểu và vị trí type annotations.
- **AnnotationMirror**: siêu dữ liệu của annotation được biểu diễn trong compiler model.

Ví dụ ý tưởng khi duyệt một field có kiểu `List<@SourceTag String>`:

```java
// ĐOẠN MINH HỌA nằm trong AnnotationProcessor / nơi có VariableElement field.
TypeMirror fieldType = field.asType();

if (fieldType instanceof DeclaredType declared) {
    for (TypeMirror argument : declared.getTypeArguments()) {
        for (AnnotationMirror annotation :
                argument.getAnnotationMirrors()) {
            System.out.println(annotation.getAnnotationType());
        }
    }
}
```

Đây **không phải một chương trình độc lập**, cần imports từ `javax.lang.model.*`, và biến `field` là `VariableElement` do processor nhận được. Nếu source khai báo type-use annotation và compiler model cung cấp vị trí đó, đây là hướng tiếp cận để đọc annotation **trên type argument**, kể cả khi policy là `SOURCE`.

**Cảnh báo quan trọng:** `RoundEnvironment.getElementsAnnotatedWith(...)` tìm các **elements được annotation theo model**, không phải một API bảo đảm trả mọi **type-use annotation lồng bên trong generic type argument**. Với `List<@Tag String>`, cần biết cách đi sâu vào `TypeMirror`; chỉ quét elements có annotation ở cấp khai báo có thể bỏ sót vị trí TYPE_USE.

### Compiler đọc binary dependency thì sao?

Khi build mã phụ thuộc một thư viện đã được compile:

- Annotation `SOURCE` của thư viện đó đã **không còn** trong `.class`, nên công cụ chỉ đọc binary không lấy lại được metadata source-only ban đầu.
- Annotation `CLASS` và `RUNTIME` có thể hiện diện trong class file, theo cấu trúc attribute tương ứng.
- Công cụ nào đọc được và áp dụng như thế nào phụ thuộc API, compiler, cách build và ngữ nghĩa riêng của công cụ.

Do đó, khi thiết kế một annotation dùng qua ranh giới **module/library binary**, phải cân nhắc liệu consumer có source hay chỉ có `.class`, và thực sự cần runtime reflection hay chỉ cần compile-time binary inspection.

## 11. Type annotation trên mảng: vị trí quan trọng ngang retention

Trong Java, ký hiệu `[]` biểu thị một cấp array type và có thể xuất hiện annotation trên từng cấp.

```java
String @RuntimeTag("array") [] names;
```

Đây là field minh họa; annotation trên phần **array level** được biểu diễn qua `AnnotatedArrayType`. Trong ví dụ:

```java
java.lang.reflect.AnnotatedArrayType type =
        (java.lang.reflect.AnnotatedArrayType)
                SomeClass.class.getDeclaredField("names")
                        .getAnnotatedType();

RuntimeTag arrayAnnotation = type.getAnnotation(RuntimeTag.class);
```

Đây là minh họa cần `SomeClass` thực sự khai báo field `names`, xử lý `NoSuchFieldException` và `RuntimeTag`. Trường hợp annotation nằm trên component type sẽ yêu cầu truy cập `type.getAnnotatedGenericComponentType()` thay vì `type.getAnnotation(...)`.

Với mảng nhiều chiều, việc đặt annotation ở `String @A [] @B []` phân biệt các **array levels**. Đừng gom tất cả annotations của mảng vào một danh sách rồi không còn biết mỗi annotation gắn vào cấp nào.

### Primitive types vẫn có thể được chú thích

```java
@RuntimeTag("numeric") int score;
```

Đây là field minh họa trong class phù hợp, với `RuntimeTag` target `TYPE_USE`. Annotation mang metadata trên `int` khi nó được sử dụng làm kiểu. Tuy nhiên, runtime vẫn xem `score` là `int` theo JVM type system; annotation không tự biến nó thành một kiểu primitive mới.

## 12. Bytecode và retention: cách kiểm tra bằng javap

Khi có một lớp được compile, `javap -v` có thể giúp phân biệt metadata lưu trong class file với dữ liệu Java reflection cung cấp.

Ví dụ kiểm tra file ví dụ đầy đủ ở cuối bài:

```bash
javac TypeAnnotationVisibilityDemo.java
javap -v -p 'TypeAnnotationVisibilityDemo$Sample'
```

Cú pháp lệnh thứ hai ở trên viết cho **shell hỗ trợ single quotes** (ví dụ Bash); trong Windows PowerShell cũng có thể truyền tên lớp lồng bằng single quotes. Nếu dùng công cụ/shell khác, cần quote dấu `$` theo quy tắc của shell để không bị khai triển biến.

Khi xem output, tìm các vùng liên quan đến annotation ở generic type arguments:

- `RuntimeVisibleTypeAnnotations`: các type annotations có retention `RUNTIME`.
- `RuntimeInvisibleTypeAnnotations`: các type annotations có retention `CLASS`.
- `SOURCE`: không có metadata annotation đó trong class file.

**Không đồng nhất `RuntimeInvisibleAnnotations` với `RuntimeInvisibleTypeAnnotations`.** Loại đầu mô tả một số annotation trên declaration; loại thứ hai mô tả type-use metadata và vị trí type target. Tùy chỗ đặt annotation và target, class file có thể chứa những loại attributes khác nhau.

`javap -v` phục vụ quan sát cấu trúc bytecode; số thứ tự constant pool và cách biểu diễn target ở output phụ thuộc phiên bản compiler nên không cần đưa thành expected output cố định trong kiểm thử.

## 13. Chương trình Java 17+ hoàn chỉnh: SOURCE, CLASS và RUNTIME

Chương trình dưới đây tạo ba type-use annotation có các retention khác nhau, đặt chúng lên **generic type arguments**, kiểm tra Java reflection, rồi đọc thêm annotation trên **return type**, **parameter type**, **array level**, **type parameter declaration** và **type bound**.

Lưu toàn bộ thành **TypeAnnotationVisibilityDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;
import java.util.List;

public class TypeAnnotationVisibilityDemo {

    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.SOURCE)
    @interface SourceType {}

    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.CLASS)
    @interface ClassType {}

    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface RuntimeType {
        String value();
    }

    @Target(ElementType.TYPE_PARAMETER)
    @Retention(RetentionPolicy.RUNTIME)
    @interface ParameterNote {}

    static final class Sample {
        List<@SourceType String> sourceValues = List.of("S");
        List<@ClassType String> classValues = List.of("C");
        List<@RuntimeType("element") String> runtimeValues =
                List.of("R");
        String @RuntimeType("array") [] arrayValues = {"A"};

        @RuntimeType("return") String echo(
                @RuntimeType("parameter") String input) {
            return input;
        }
    }

    static final class NumericBox<
            @ParameterNote T extends @RuntimeType("bound") Number> {}

    static AnnotatedType argumentType(String fieldName)
            throws ReflectiveOperationException {
        Field field = Sample.class.getDeclaredField(fieldName);
        AnnotatedParameterizedType annotated =
                (AnnotatedParameterizedType) field.getAnnotatedType();
        return annotated.getAnnotatedActualTypeArguments()[0];
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        boolean hasSource = argumentType("sourceValues")
                .isAnnotationPresent(SourceType.class);
        boolean hasClass = argumentType("classValues")
                .isAnnotationPresent(ClassType.class);

        RuntimeType runtime = argumentType("runtimeValues")
                .getAnnotation(RuntimeType.class);

        System.out.println("SOURCE via reflection: " + hasSource);
        System.out.println("CLASS via reflection: " + hasClass);
        System.out.println("RUNTIME type argument: " + runtime.value());

        Field runtimeField =
                Sample.class.getDeclaredField("runtimeValues");
        System.out.println("field declaration tag: " +
                (runtimeField.getAnnotation(RuntimeType.class) != null));

        Method echo = Sample.class.getDeclaredMethod(
                "echo", String.class);
        RuntimeType returnTag =
                echo.getAnnotatedReturnType()
                        .getAnnotation(RuntimeType.class);
        RuntimeType parameterTag =
                echo.getAnnotatedParameterTypes()[0]
                        .getAnnotation(RuntimeType.class);

        System.out.println("return type: " + returnTag.value());
        System.out.println("parameter type: " + parameterTag.value());

        Field arrayField =
                Sample.class.getDeclaredField("arrayValues");
        AnnotatedArrayType arrayType =
                (AnnotatedArrayType) arrayField.getAnnotatedType();
        System.out.println("array level: " +
                arrayType.getAnnotation(RuntimeType.class).value());

        TypeVariable<?> variable =
                NumericBox.class.getTypeParameters()[0];
        System.out.println("type parameter: " +
                variable.isAnnotationPresent(ParameterNote.class));

        RuntimeType boundTag =
                variable.getAnnotatedBounds()[0]
                        .getAnnotation(RuntimeType.class);
        System.out.println("type bound: " + boundTag.value());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac TypeAnnotationVisibilityDemo.java
java TypeAnnotationVisibilityDemo
```

**Stdout dự kiến, theo đúng thứ tự in của chương trình:**

```text
SOURCE via reflection: false
CLASS via reflection: false
RUNTIME type argument: element
field declaration tag: false
return type: return
parameter type: parameter
array level: array
type parameter: true
type bound: bound
```

**Giải thích kết quả:**

1. `SOURCE via reflection: false` — annotation chỉ ở nguồn và không được lưu vào class file.
2. `CLASS via reflection: false` — metadata nằm trong `.class` nhưng Java core reflection không cung cấp annotation đó.
3. `RUNTIME type argument: element` — `@RuntimeType("element")` nằm trên `String` của `List<String>` và được đọc qua `AnnotatedParameterizedType`.
4. `field declaration tag: false` — annotation gắn trên generic type argument, không gắn lên declaration của field; `Field.getAnnotation(...)` hỏi sai vị trí.
5. `return type: return` và `parameter type: parameter` — reflection có API riêng cho các **annotated types** của method return và parameters.
6. `array level: array` — annotation gắn trên array level; đường phản chiếu là `AnnotatedArrayType`.
7. `type parameter: true` — annotation có `@Target(TYPE_PARAMETER)` được đọc qua `TypeVariable`.
8. `type bound: bound` — annotation target `TYPE_USE` gắn trên `Number` trong phần `extends`, được truy vấn qua `getAnnotatedBounds()`.

**Đánh giá đúng phạm vi:** Chương trình chứng minh các vị trí **Java core reflection có API tương ứng**; nó không cố phản chiếu annotation ở local variable/cast, nơi core reflection không cung cấp API tổng quát. Bài không dựa vào các tính năng cũ đã bị loại bỏ, và không cần thư viện ngoài.

## 14. Các lỗi thường gặp và cách phòng tránh

### Lỗi 1: Không khai báo @Retention nhưng nghĩ annotation có ở runtime

```java
@Target(ElementType.TYPE_USE)
@interface Tag {}
```

Đây là định nghĩa minh họa. Retention mặc định là `CLASS`, nên `getAnnotation(Tag.class)` tại runtime sẽ không trả annotation đặt trên type use. Nếu reflection cần đọc nó, thêm `@Retention(RetentionPolicy.RUNTIME)`.

### Lỗi 2: Chỉ có @Retention(RUNTIME), không đặt target đúng

```java
@Target(ElementType.FIELD)
@Retention(RetentionPolicy.RUNTIME)
@interface FieldOnly {}

// SAI: FIELD không cho phép vị trí generic type argument.
// List<@FieldOnly String> values;
```

Đây là ví dụ sai đã comment, cần import `java.lang.annotation.*;`. **Retention không mở rộng những vị trí được phép sử dụng annotation.** Muốn gắn vào `String` trong `List<String>`, target phải cho phép `TYPE_USE`.

### Lỗi 3: Hỏi Field.getAnnotations thay vì AnnotatedType

```java
// Annotation nằm ở: List<@RuntimeType("element") String>
// Đọc sai chỗ: field.getAnnotation(RuntimeType.class)
// Đọc đúng chỗ: ((AnnotatedParameterizedType) field.getAnnotatedType())
//                 .getAnnotatedActualTypeArguments()[0]
//                 .getAnnotation(RuntimeType.class)
```

Đây là **minh họa logic truy vấn**, cần khai báo `field` và annotation trước khi dùng. Java không tự làm phẳng tất cả type-use annotations vào danh sách annotations của field declaration.

### Lỗi 4: Nghĩ retention RUNTIME đồng nghĩa mọi local variable có thể reflect

Java có thể lưu type annotations vào metadata của method body, nhưng core reflection không có phương thức liệt kê mọi annotation ở cast hoặc local variable. Nếu công cụ cần những vị trí này, hãy dùng compiler API/AST hoặc bytecode scanner, không dựa vào `Field`/`Method.getAnnotations()`.

### Lỗi 5: Nhầm CLASS với annotation không được lưu

`CLASS` có nghĩa annotation **được giữ** trong file binary nhưng **không có trong core reflection**. Khi không thấy annotation qua reflection, đừng lập tức kết luận compiler đã xóa nó; đọc `.class` với công cụ phù hợp.

### Lỗi 6: Nghĩ tên annotation tự định nghĩa semantics

`@NonNull`, `@Readonly` hoặc `@ThreadSafe` trong một thư viện có ý nghĩa theo **quy tắc của thư viện và công cụ tương ứng**. Java SE không tự biến mọi annotation trùng tên thành ràng buộc runtime hoặc hệ thống non-null types. Với dữ liệu quan trọng, validation và test vẫn cần explicit hoặc framework đã được cấu hình.

### Lỗi 7: Annotation SOURCE không thể đọc trong lúc compile

Sai. Source retention **không được ghi vào class file**, nhưng trong compilation đang xét, công cụ nguồn/processor có thể đọc metadata của source với model API thích hợp. Sự biến mất diễn ra khi cần tái sử dụng dữ liệu **chỉ từ binary artifact**, không phải ngay khi parser đọc source.

### Lỗi 8: Không hiểu vị trí trong generic, array và type parameter

`List<@Tag String>`, `String @Tag []`, `class Box<@Tag T>` và `class Box<T extends @Tag Number>` là các vị trí khác nhau. Chọn `TYPE_USE`, `TYPE_PARAMETER` và API reflection tương ứng dựa trên thứ bạn thực sự muốn mô tả, không chỉ dựa trên việc annotation nằm “gần tên kiểu”.

### Lỗi 9: Đổi retention của thư viện tùy tiện

Khi annotation đã là một phần contract của library, chuyển từ `RUNTIME` xuống `CLASS` hoặc `SOURCE` có thể làm framework dựa trên reflection mất metadata. Chuyển từ `SOURCE` lên `RUNTIME` có thể thay đổi nội dung binary và kỳ vọng của consumer. Đánh giá tương thích qua build/test và các tool downstream trước khi thay đổi retention.

## 15. Quy trình thực tế để chọn retention đúng

Khi định nghĩa một type annotation cho project hoặc thư viện, có thể trả lời tuần tự:

1. **Consumer là ai?** Compiler plugin, static analyzer, annotation processor, bytecode tool hay framework runtime?
2. **Consumer chạy khi nào?** Trên source đang biên dịch, class files của dependencies, lúc tải class hay runtime?
3. **Annotation gắn ở đâu?** Declaration (FIELD/METHOD/TYPE), type use (TYPE_USE), type parameter declaration (TYPE_PARAMETER) hay nhiều vị trí?
4. **Metadata có cần vượt ranh giới source → class file không?** Không → có thể dùng `SOURCE`. Có → cần `CLASS` hoặc `RUNTIME`.
5. **Có cần Java reflection thật không?** Có → `RUNTIME` và kiểm tra API tương ứng **có đọc được vị trí đó** không.
6. **Nếu chỉ đọc binary không dùng core reflection?** `CLASS` có thể đủ, và thường tránh giữ metadata cho mục tiêu reflection không cần thiết.
7. **Nếu annotation diễn đạt một quy tắc?** Công cụ nào enforce quy tắc, cấu hình ra sao và báo lỗi/cảnh báo ở giai đoạn nào?
8. **Test ở hai phía:** một bài test/processor compile-time khi cần; một bài reflection test trên compiled class khi cần runtime; nếu dùng CLASS, thêm bytecode inspection.

### Ví dụ lựa chọn theo tình huống

| Nhu cầu | Retention thường phù hợp | Lý do |
| --- | --- | --- |
| Annotation hỗ trợ phân tích source trong một lần build | `SOURCE` | Không cần lưu vào artifact |
| Công cụ phân tích class files của thư viện phụ thuộc | `CLASS` | Metadata tồn tại trong binary |
| Framework runtime đọc generic type argument trên field | `RUNTIME` | Dùng `AnnotatedParameterizedType` |
| Công cụ runtime đọc method return type | `RUNTIME` | Dùng `Method.getAnnotatedReturnType()` |
| Gắn annotation vào local variable rồi muốn dùng reflection để đọc nó | **Không chỉ giải quyết bằng retention** | Core reflection không có API tương ứng |
| Chỉ muốn kiểm tra non-null tĩnh | Tùy static checker | Chọn policy theo compiler/checker và cách dùng library |
| Muốn validate input runtime | Retention không đủ | Cần logic validation/framework runtime có đọc được metadata |

Không nên chọn policy chỉ vì annotation tên là `Check`, `Valid` hay `Nonnull`. Tên không xác định thời điểm tồn tại hay hành vi enforcement.

## 16. Bài tập thực hành có đáp án định hướng

**Bài 1 — so sánh ba policy.** Định nghĩa ba annotation target `TYPE_USE` với `SOURCE`, `CLASS`, `RUNTIME`, lần lượt đặt trên ba đối số kiểu `String` của `List<String>`. Hỏi policy nào có thể xuất hiện qua core reflection? **Đáp án:** chỉ `RUNTIME`, khi truy vấn đúng vị trí qua `AnnotatedParameterizedType`.

**Bài 2 — retention mặc định.** Nếu định nghĩa `@interface SourceMark {}` mà không có `@Retention` thì policy mặc định là gì? **Đáp án:** `CLASS`, không phải `SOURCE` hay `RUNTIME`.

**Bài 3 — declaration và type use.** Có field `List<@Tag String> values` với `Tag` target `TYPE_USE`, retention `RUNTIME`. Vì sao `Field.getAnnotation(Tag.class)` không tìm thấy annotation trên type argument? **Đáp án:** field declaration khác vị trí type argument; dùng `field.getAnnotatedType()` rồi đi tới `getAnnotatedActualTypeArguments()[0]`.

**Bài 4 — generic lồng nhau.** Cho `Map<String,List<@Tag Integer>>`. Dùng các `AnnotatedParameterizedType` theo thứ tự nào để đọc `Tag`? **Đáp án:** kiểu field Map → type argument thứ hai List → type argument đầu tiên Integer.

**Bài 5 — annotated bounds.** `class Box<@ParamNote T extends @BoundNote Number>`. Để đọc `ParamNote` dùng API nào? Để đọc `BoundNote` dùng API nào? **Đáp án:** `TypeVariable.getAnnotation(ParamNote.class)` và `TypeVariable.getAnnotatedBounds()[0].getAnnotation(BoundNote.class)`.

**Bài 6 — local variable.** Một local type use có retention `RUNTIME` nhưng `Method.getAnnotations()` không thấy nó. Có mâu thuẫn không? **Đáp án:** không; method declaration khác local variable type use, và core reflection không có API liệt kê mọi type use trong body.

**Bài 7 — annotation processor.** Một công cụ chỉ gọi `getElementsAnnotatedWith(TypeTag.class)` rồi báo không có vị trí `List<@TypeTag String>`. Điều gì cần kiểm tra? **Đáp án:** processor có thể đang bỏ qua những type uses bên trong `TypeMirror`; cần duyệt model của kiểu/đối số kiểu với `getAnnotationMirrors()` phù hợp.

**Bài 8 — binary dependency.** Thư viện chỉ phát hành JAR đã compile. Một consumer cần phân tích type-use annotation từ class file nhưng không cần runtime reflection. Nên cân nhắc retention nào? **Đáp án:** ít nhất phải giữ lại binary metadata; `CLASS` thường phù hợp, tùy công cụ. `SOURCE` sẽ không còn annotation trong JAR.

## 17. Tóm tắt kiến thức cần nhớ

- `@Target` quyết định **nơi được đặt annotation**; `@Retention` quyết định **giai đoạn metadata còn tồn tại**. Hai đặc tính độc lập.
- `SOURCE`: chỉ ở source, đọc được trong compiler/source tooling thích hợp, **không** được lưu vào `.class`.
- `CLASS`: được lưu vào `.class`, **không** hiển thị qua Java core reflection; **mặc định** nếu không có `@Retention`.
- `RUNTIME`: được lưu vào `.class` và có thể đọc qua reflection **tại những vị trí có API hỗ trợ**.
- Với type-use annotation, dùng các loại `AnnotatedType` và các phương thức như `Field.getAnnotatedType()`, `Method.getAnnotatedReturnType()`, `getAnnotatedActualTypeArguments()` và `TypeVariable.getAnnotatedBounds()`.
- Declaration annotation và type-use annotation không phải cùng một nơi lưu metadata.
- `@Retention(RUNTIME)` không tự tạo semantic như non-null, không cho phép reflection nhìn mọi local variable hoặc cast, và không tự chạy validation.
- Khi thiết kế annotation cho một library, xác định rõ **consumer, thời điểm sử dụng, vị trí metadata, ranh giới source/binary và cách kiểm thử**.

### Tài liệu chính thức

- [Java SE 25 — RetentionPolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/RetentionPolicy.html)
- [Java SE 25 — Retention](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Retention.html)
- [Java SE 25 — ElementType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html)
- [Java SE 25 — AnnotatedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java SE 25 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Java SE 25 — TypeVariable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Java Language Specification `9.6.4.2 — Retention](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.2)
- [Java Language Specification `9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.4)
