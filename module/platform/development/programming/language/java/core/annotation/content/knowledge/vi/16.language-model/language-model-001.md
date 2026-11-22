# Element, ElementKind và cấu trúc khai báo trong Java Annotation Processing

## 1. Mô hình ngôn ngữ: đọc khai báo Java ngay khi biên dịch

Khi xây dựng **annotation processor** bằng `javax.annotation.processing`, Java cung cấp một mô hình ngôn ngữ trong package `javax.lang.model`. Mô hình này cho phép compiler và processor mô tả class, interface, annotation type, record, field, method, constructor, parameter, type parameter, package hoặc module **mà không cần chạy chương trình**.

Ba khái niệm liên quan nhưng không đồng nhất:

- **`Element`** (`javax.lang.model.element.Element`): đại diện cho **một khai báo hoặc thành phần chương trình** có thể được mô hình ngôn ngữ biểu diễn, chẳng hạn class `User`, method `save`, parameter `id` hoặc record component `name`.
- **`ElementKind`**: enum phân loại **vai trò khai báo** của một `Element`, ví dụ `CLASS`, `METHOD`, `FIELD`, `PARAMETER`, `RECORD`.
- **`TypeMirror`** (`javax.lang.model.type.TypeMirror`): đại diện cho **kiểu Java** liên quan, ví dụ `String`, `List<String>`, type variable `T`, kiểu nguyên thủy `int` hoặc mảng `String[]`.

Sơ đồ tư duy:

~~~text
Mô hình declaration (javax.lang.model.element)
    Element
      +-- TypeElement           class / interface / enum / annotation / record
      +-- ExecutableElement     method / constructor
      +-- VariableElement       field / parameter / enum constant / ...
      +-- TypeParameterElement  khai báo T trong class Box<T>
      +-- RecordComponentElement record component
      +-- PackageElement        package
      +-- ModuleElement         module

Mô hình type (javax.lang.model.type)
    TypeMirror             String, T, int, List<String>, String[], ...
      +-- TypeKind          DECLARED, TYPEVAR, INT, ARRAY, ...
~~~

Một method tên `read` là `Element` có `ElementKind.METHOD`; kiểu trả về `String` của method ấy là `TypeMirror`. **Đừng nhầm “khai báo nào?” với “kiểu gì?”**.

API này thuộc module **`java.compiler`**, có sẵn trong JDK. Ví dụ bên dưới dùng **Java 17+**, trong đó record và record component đã là tính năng chính thức.

## 2. Ví dụ cấu trúc khai báo từ một file Java

Xét file `Demo.java`:

~~~java
package demo;

import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Label {
    String value();
    String category() default "general";
}

@Label("box")
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    @Label("reader")
    public T getOr(T fallback) {
        return value == null ? fallback : value;
    }

    static class Nested {}
}

record Pair(int left, int right) {}
~~~

Có thể hình dung một phần cấu trúc declaration:

~~~text
package demo                             PACKAGE
├── annotation interface Label          ANNOTATION_TYPE
│   ├── value()                          METHOD
│   └── category() default "general"     METHOD
├── class Box<T>                         CLASS
│   ├── T                                TYPE_PARAMETER
│   ├── field value                      FIELD
│   ├── constructor Box(T)               CONSTRUCTOR
│   │   └── parameter value              PARAMETER
│   ├── method getOr(T)                   METHOD
│   │   └── parameter fallback           PARAMETER
│   └── nested class Nested              CLASS
└── record Pair(int left, int right)     RECORD
    ├── record component left            RECORD_COMPONENT
    └── record component right           RECORD_COMPONENT
~~~

Đây là **sơ đồ khái niệm** tập trung vào các khai báo có ý nghĩa học tập, không phải bản in chính xác của toàn bộ `getEnclosedElements()`. Compiler còn biểu diễn các **member ngầm định/mandated** tương ứng, chẳng hạn accessor và constructor của record, default constructor khi có, hoặc các thành viên tạo sẵn của enum. Chi tiết tập member và vị trí xuất hiện phụ thuộc loại khai báo.

Một số quan hệ chính:

1. `Box` là một **`TypeElement`** có kind `CLASS`.
2. `T` ở `Box<T>` là **`TypeParameterElement`**, với kind `TYPE_PARAMETER`.
3. `value` là **`VariableElement`** có kind `FIELD`.
4. `getOr` là **`ExecutableElement`** có kind `METHOD`; tham số `fallback` là `VariableElement` có kind `PARAMETER`.
5. `Label` là **`TypeElement`** với kind `ANNOTATION_TYPE`, còn các phần tử `value()` và `category()` của annotation type được mô hình hóa thành **`ExecutableElement` có kind `METHOD`**.
6. `Pair` là **`TypeElement`** có kind `RECORD`; `left`, `right` trong record header là **`RecordComponentElement`**, không phải `VariableElement` kind `FIELD`.

**Hệ quả:** biết tên một khai báo chưa đủ để chọn cách xử lý. Phải kiểm tra `getKind()` và dùng interface con phù hợp.

## 3. `ElementKind`: phân loại đúng loại khai báo

`ElementKind` là enum trong `javax.lang.model.element`. Những giá trị rất thường gặp:

| `ElementKind` | Loại khai báo / thành phần | Interface chuyên biệt thường dùng |
|---|---|---|
| `PACKAGE` | Package | `PackageElement` |
| `MODULE` | Java module | `ModuleElement` |
| `CLASS` | Class thông thường | `TypeElement` |
| `INTERFACE` | Interface | `TypeElement` |
| `ENUM` | Enum type | `TypeElement` |
| `ANNOTATION_TYPE` | Annotation interface khai báo bằng `@interface` | `TypeElement` |
| `RECORD` | Record type | `TypeElement` |
| `FIELD` | Field | `VariableElement` |
| `ENUM_CONSTANT` | Hằng enum | `VariableElement` |
| `METHOD` | Method, bao gồm element method trong annotation interface | `ExecutableElement` |
| `CONSTRUCTOR` | Constructor | `ExecutableElement` |
| `PARAMETER` | Tham số method/constructor | `VariableElement` |
| `TYPE_PARAMETER` | Khai báo type variable như `T` | `TypeParameterElement` |
| `RECORD_COMPONENT` | Component khai báo trong record header | `RecordComponentElement` |
| `LOCAL_VARIABLE` | Biến cục bộ | `VariableElement` |
| `EXCEPTION_PARAMETER` | Biến bắt exception trong `catch` | `VariableElement` |
| `RESOURCE_VARIABLE` | Biến resource được khai báo tại try-with-resources | `VariableElement` |
| `BINDING_VARIABLE` | Biến được tạo bởi pattern, ví dụ `instanceof String s` | `VariableElement` |

Enum còn có các kind đặc thù như `STATIC_INIT`, `INSTANCE_INIT` và `OTHER`. Danh sách có thể được mở rộng trong những phiên bản Java mới, vì ngôn ngữ có thể thêm các cấu trúc khai báo.

Ví dụ nhánh an toàn:

~~~java
void inspect(Element element) {
    switch (element.getKind()) {
        case CLASS:
        case INTERFACE:
        case RECORD:
        case ENUM:
        case ANNOTATION_TYPE:
            TypeElement type = (TypeElement) element;
            System.out.println(type.getQualifiedName());
            break;
        case METHOD:
        case CONSTRUCTOR:
            ExecutableElement executable = (ExecutableElement) element;
            System.out.println(executable.getParameters().size());
            break;
        case FIELD:
        case PARAMETER:
            VariableElement variable = (VariableElement) element;
            System.out.println(variable.asType());
            break;
        default:
            // Còn nhiều kind khác: không ép kiểu vô điều kiện.
            break;
    }
}
~~~

Khối trên minh họa xử lý từng `kind`; để dùng độc lập cần import `javax.lang.model.element.*` và đặt method trong class thích hợp.

**Không ép mọi `Element` thành `TypeElement`** chỉ vì nó có `getSimpleName()`. `FIELD` không phải class; `RECORD_COMPONENT` không phải một field; `PARAMETER` không phải method.

Các method `ElementKind.isClass()`, `isInterface()` và `isField()` hỗ trợ một số phép nhóm, nhưng hãy đọc hợp đồng của từng method. Chẳng hạn `RECORD` được xem là dạng class cho mục đích phân loại, còn `ANNOTATION_TYPE` thuộc nhóm interface. Khi cần phân biệt riêng record với class thường, so sánh chính xác `getKind() == ElementKind.RECORD`.

## 4. Các thao tác chung qua interface `Element`

Dù là package, type, field hay method, các object `Element` đều hỗ trợ một số thao tác chung:

| API | Ý nghĩa | Lưu ý |
|---|---|---|
| `getKind()` | Trả về `ElementKind` | Dùng trước khi cast xuống interface con |
| `getSimpleName()` | Trả về `Name` của khai báo | `Name` hỗ trợ `contentEquals(...)`; không nhất thiết là `String` |
| `getEnclosingElement()` | Trả về element bao bên ngoài | Method thường có enclosing type; parameter có enclosing executable |
| `getEnclosedElements()` | Những khai báo nằm trong element đó | **Không** đồng nghĩa mọi member kế thừa |
| `getModifiers()` | Tập các modifier như `PUBLIC`, `PRIVATE`, `STATIC` | Không nên giả định mọi kind đều có cùng nhóm modifier |
| `getAnnotationMirrors()` | Các annotation declaration được mô hình hóa thành `AnnotationMirror` | Có thể thấy annotation retention `SOURCE` ngay khi biên dịch |
| `asType()` | Lấy kiểu Java tương ứng dưới dạng `TypeMirror` | Type khác với loại declaration `ElementKind` |
| `accept(visitor, p)` | Cho phép `ElementVisitor` xử lý theo kind | Hữu ích khi nhiều loại element có logic riêng |

Ví dụ thao tác độc lập:

~~~java
Element e = /* lấy element từ RoundEnvironment hoặc Elements */;
System.out.println(e.getKind());
System.out.println(e.getSimpleName());
System.out.println(e.getEnclosingElement());
System.out.println(e.asType());
~~~

Lưu ý: đoạn trên là **mẫu API**, không phải một chương trình Java độc lập; biến `e` cần lấy từ môi trường annotation processing.

### 4.1. Quan hệ enclosing và enclosed

- Với một top-level class `demo.Box`, `getEnclosingElement()` của nó là **package `demo`**.
- Với method `Box.getOr`, enclosing element là **`Box`**.
- Với parameter `fallback`, enclosing element là **method `getOr`**.
- Với type parameter `T`, enclosing element là class hoặc method generic khai báo `T`.
- Với record component `Pair.left`, enclosing element là record `Pair`.
- Với `ModuleElement`, enclosing element là `null`.

`getEnclosedElements()` không phải hàm gọi đệ quy qua toàn bộ cây: muốn duyệt sâu phải duyệt từng child. Khi chỉ cần các field hoặc method trong type, sử dụng `ElementFilter` để tách theo loại thay vì cast bừa.

### 4.2. Khai báo trực tiếp khác thành viên kế thừa

Với một `TypeElement`:

~~~java
List<? extends Element> direct = type.getEnclosedElements();
List<? extends Element> all = processingEnv.getElementUtils()
        .getAllMembers(type);
~~~

- `getEnclosedElements()` tập trung vào **thành viên trực tiếp và những phần tử mandated** của type đó.
- `Elements.getAllMembers(type)` lấy **các thành viên của type, bao gồm member kế thừa** theo mô hình Java.
- **Không** dùng `getEnclosedElements()` rồi kết luận class không có method thừa kế nào.

Với source declaration, API thường trả danh sách theo thứ tự tự nhiên của source, nhưng **thứ tự của implicit/mandated elements không được bảo đảm như một layout cố định**. Khi viết công cụ, lọc theo kind và tên, không phụ thuộc index như `getEnclosedElements().get(2)`.

## 5. Interface chuyên biệt và thuộc tính cần biết

### 5.1. `TypeElement`

`TypeElement` mô tả **khai báo** class, interface, enum, annotation interface hoặc record. Một số method quan trọng:

- `getQualifiedName()`: tên chuẩn như `demo.Box`; khác với `getSimpleName()` là `Box`.
- `getNestingKind()`: phân biệt top-level, member, local, anonymous.
- `getTypeParameters()`: các `TypeParameterElement` của class generic.
- `getSuperclass()`, `getInterfaces()`: các **TypeMirror** ở quan hệ kế thừa.
- `getRecordComponents()`: các `RecordComponentElement` theo thứ tự header của record (Java 16+).
- `getEnclosedElements()`: các thành viên khai báo trong type, gồm phần tử mandated liên quan.

Tên qualified name không nhất thiết có giá trị như class top-level trong mọi ngữ cảnh: class local và anonymous không có canonical name phù hợp để dùng như tên đầy đủ thông thường.

### 5.2. `ExecutableElement`

`ExecutableElement` mô tả method/constructor. Nó cung cấp:

- `getReturnType()`: **TypeMirror** của kiểu trả về; constructor có kiểu trả về đặc biệt theo mô hình.
- `getParameters()`: danh sách **VariableElement** của từng parameter.
- `getThrownTypes()`: các exception types được khai báo trong `throws`.
- `getTypeParameters()`: type parameters nếu method/constructor generic.
- `getDefaultValue()`: giá trị mặc định nếu element là phương thức khai báo phần tử của **annotation interface**; nếu không có default trả `null`.
- `isVarArgs()` và `isDefault()`: nhận biết varargs method và default method khi phù hợp.

Ví dụ `String category() default "general"` trong `@interface Label` là `ExecutableElement` kind `METHOD`; `category.getDefaultValue()` mô tả giá trị default. **Không có một kind riêng tên “ANNOTATION_ELEMENT” trong `ElementKind` Java 17.**

### 5.3. `VariableElement` và `TypeParameterElement`

`VariableElement` dùng cho field, parameter, enum constant và những loại biến khác. Nó có `asType()`; `getConstantValue()` chỉ có giá trị với **constant variable** thuộc kiểu nguyên thủy hoặc `String` và được khởi tạo bởi constant expression phù hợp.

`TypeParameterElement` dành cho **khai báo type parameter**, ví dụ `T` trong `Box<T>`; có thể đọc `getBounds()` và generic element sở hữu nó. Đừng nhầm `T` declaration với kiểu `T` mà field `value` sử dụng.

### 5.4. `RecordComponentElement` và hai bề mặt khác nhau của record

Với `record Pair(int left, int right) {}`:

- `Pair` có kind `RECORD`.
- Hai khai báo trong header có kind `RECORD_COMPONENT`.
- `TypeElement.getRecordComponents()` trả danh sách component theo thứ tự `left`, `right`.
- `RecordComponentElement.getAccessor()` trả về `ExecutableElement` cho accessor tương ứng như `left()`.
- Compiler cũng xử lý component fields và canonical constructor; các thành phần này là **những declaration khác** có kind phù hợp như `FIELD`, `METHOD`, `PARAMETER`.

Điều quan trọng cho annotation processing: annotation với `@Target(RECORD_COMPONENT)` mô tả component, khác với annotation chỉ có `FIELD` hoặc `METHOD`. Luôn hỏi đúng element mà công cụ muốn kiểm tra.

### 5.5. `PackageElement` và `ModuleElement`

`PackageElement` biểu diễn package, hỗ trợ `getQualifiedName()` và truy cập các loại nằm trong package theo mô hình compiler. `ModuleElement` biểu diễn module, có thể truy cập directives (`requires`, `exports`, `opens`...) qua API riêng. Với hệ thống module, một tên package hoặc type có thể cần ngữ cảnh module để phân giải duy nhất.

## 6. `ElementKind` khác `TypeKind` như thế nào?

Đây là cặp khái niệm dễ nhầm nhất.

Ví dụ `private T value;` bên trong `class Box<T>`:

~~~java
VariableElement field = /* tìm field "value" trong Box */;
System.out.println(field.getKind());       // FIELD
System.out.println(field.asType());        // T
System.out.println(field.asType().getKind()); // TYPEVAR
~~~

Dòng cuối sử dụng **`TypeKind.TYPEVAR`**, không phải `ElementKind.TYPE_PARAMETER`. Ý nghĩa:

- `FIELD`: khai báo là một field.
- `T` / `TYPEVAR`: kiểu của field là một type variable.
- `TYPE_PARAMETER`: loại của **khai báo `T`** trong `Box<T>`.

So sánh:

| Câu hỏi | API / enum |
|---|---|
| Đây là class hay method hay parameter? | `Element.getKind()` trả **ElementKind** |
| Đây là primitive `int`, array, declared type hay type variable? | `TypeMirror.getKind()` trả **TypeKind** |
| Method này trả kiểu gì? | `ExecutableElement.getReturnType()` → **TypeMirror** |
| Field này có kiểu gì? | `VariableElement.asType()` → **TypeMirror** |
| Class generic khai báo những `T` nào? | `TypeElement.getTypeParameters()` → **TypeParameterElement** |

Một `TypeElement` mô tả **declaration `Box<T>`**; kiểu sử dụng tại `Box<String>` là một `DeclaredType` với type argument `String`, không phải một `TypeElement` mới cho mỗi tham số hóa. Mô hình này cũng không đồng nghĩa `java.lang.Class<?>` hoặc runtime erasure.

Khi xử lý type checking, có thể dùng `javax.lang.model.util.Types` (nhận từ `processingEnv.getTypeUtils()`), chẳng hạn `isSameType` hoặc `isAssignable`; không dùng `String.equals` trên `TypeMirror.toString()` làm cơ sở type-system correctness.

## 7. Bài thực hành đầy đủ: annotation processor in cấu trúc khai báo

Bài này có **hai file nguồn** trong cùng thư mục: `ModelProcessor.java` (annotation processor) và `Demo.java` (các declaration được phân tích). Toàn bộ mã tương thích Java 17.

### 7.1. File `ModelProcessor.java`

~~~java
import java.util.Set;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.lang.model.util.ElementFilter;
import javax.lang.model.util.Elements;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ModelProcessor extends AbstractProcessor {
    private boolean done;

    @Override
    public boolean process(Set<? extends TypeElement> annotations, RoundEnvironment round) {
        if (done || round.processingOver()) return false;
        done = true;

        Elements elements = processingEnv.getElementUtils();
        TypeElement box = elements.getTypeElement("demo.Box");
        TypeElement pair = elements.getTypeElement("demo.Pair");
        TypeElement label = elements.getTypeElement("demo.Label");

        System.out.println("box-kind=" + box.getKind());
        System.out.println("box-name=" + box.getQualifiedName());
        System.out.println("box-parent=" + box.getEnclosingElement().getKind());
        System.out.println("type-param-kind=" + box.getTypeParameters().get(0).getKind());

        VariableElement field = ElementFilter.fieldsIn(box.getEnclosedElements())
                .stream().filter(e -> e.getSimpleName().contentEquals("value"))
                .findFirst().orElseThrow();
        System.out.println("field-kind=" + field.getKind());
        System.out.println("field-type=" + field.asType());

        ExecutableElement getter = ElementFilter.methodsIn(box.getEnclosedElements())
                .stream().filter(e -> e.getSimpleName().contentEquals("getOr"))
                .findFirst().orElseThrow();
        System.out.println("method-kind=" + getter.getKind());
        System.out.println("method-return=" + getter.getReturnType());
        System.out.println("method-param-kind=" + getter.getParameters().get(0).getKind());
        System.out.println("method-param-type=" + getter.getParameters().get(0).asType());
        System.out.println("method-parent=" + getter.getEnclosingElement().getSimpleName());

        AnnotationMirror mirror = box.getAnnotationMirrors().get(0);
        System.out.println("declared-annotation=" + mirror.getAnnotationType());
        System.out.println("explicit-values=" + mirror.getElementValues().size());
        System.out.println("values-with-defaults="
                + elements.getElementValuesWithDefaults(mirror).size());

        System.out.println("record-kind=" + pair.getKind());
        System.out.println("record-components=" + pair.getRecordComponents().size());
        RecordComponentElement first = pair.getRecordComponents().get(0);
        System.out.println("record-component-kind=" + first.getKind());
        System.out.println("record-accessor=" + first.getAccessor().getSimpleName());

        System.out.println("annotation-kind=" + label.getKind());
        ExecutableElement category = ElementFilter.methodsIn(label.getEnclosedElements())
                .stream().filter(e -> e.getSimpleName().contentEquals("category"))
                .findFirst().orElseThrow();
        System.out.println("annotation-member-kind=" + category.getKind());
        System.out.println("annotation-default=" + category.getDefaultValue());
        return false;
    }
}
~~~

### 7.2. File `Demo.java`

~~~java
package demo;
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Label {
    String value();
    String category() default "general";
}

@Label("box")
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    @Label("reader")
    public T getOr(T fallback) {
        return value == null ? fallback : value;
    }

    static class Nested {}
}

record Pair(int left, int right) {}
~~~

**Ghi chú:** `Label` có retention `SOURCE`. Annotation processor **vẫn nhìn thấy nó ngay trong quá trình biên dịch**, dù annotation này sẽ không được giữ lại để Java reflection runtime truy vấn sau khi compile.

### 7.3. Lệnh biên dịch và gọi processor

Thực hiện trong thư mục chứa hai file:

~~~bash
mkdir out
javac --release 17 -d out ModelProcessor.java
javac --release 17 -cp out -processorpath out -processor ModelProcessor -proc:only -d out Demo.java
~~~

Ở bước đầu, `javac` biên dịch `ModelProcessor` thành class trong `out`. Bước thứ hai chỉ rõ processor bằng `-processor ModelProcessor`, đưa nó vào processor path, rồi chạy annotation processing trên `Demo.java`.

`-proc:only` yêu cầu **chỉ chạy annotation processing, không sinh class file bình thường cho `Demo`**. Nếu cần build sản phẩm chạy được, biên dịch `Demo.java` riêng không có `-proc:only` hoặc dùng cấu hình build thích hợp.

Kết quả in từ processor khi sử dụng `javac --release 17`:

~~~text
box-kind=CLASS
box-name=demo.Box
box-parent=PACKAGE
type-param-kind=TYPE_PARAMETER
field-kind=FIELD
field-type=T
method-kind=METHOD
method-return=T
method-param-kind=PARAMETER
method-param-type=T
method-parent=Box
declared-annotation=demo.Label
explicit-values=1
values-with-defaults=2
record-kind=RECORD
record-components=2
record-component-kind=RECORD_COMPONENT
record-accessor=left
annotation-kind=ANNOTATION_TYPE
annotation-member-kind=METHOD
annotation-default="general"
~~~

### 7.4. Giải thích các kết quả quan trọng

- **`box-kind=CLASS`**, **`record-kind=RECORD`**, **`annotation-kind=ANNOTATION_TYPE`**: cùng mô hình `TypeElement` nhưng có các `ElementKind` khác nhau.
- **`box-parent=PACKAGE`**: class top-level `demo.Box` được bao bởi package `demo`, không phải bởi method hay class khác.
- **`type-param-kind=TYPE_PARAMETER`**: `T` là một khai báo type parameter.
- **`field-kind=FIELD`**, **`field-type=T`**: field `value` là declaration field, có kiểu `T`.
- **`method-kind=METHOD`**, **`method-return=T`**: method `getOr` trả về kiểu `T`, không phải `ElementKind.TYPE_PARAMETER`.
- **`method-param-kind=PARAMETER`**, **`method-param-type=T`**: parameter `fallback` là declaration riêng có kiểu `T`; enclosing element của nó là method `getOr`.
- **`declared-annotation=demo.Label`**: processor lấy annotation của `Box` ở dạng `AnnotationMirror`, **không cần load `java.lang.Class` của `Box`**.
- **`explicit-values=1`**: annotation `@Label("box")` chỉ cung cấp phần tử `value` tường minh.
- **`values-with-defaults=2`**: `Elements.getElementValuesWithDefaults` bổ sung phần tử `category` có default `"general"`.
- **`record-component-kind=RECORD_COMPONENT`** và **`record-accessor=left`**: record component và accessor là những mô hình riêng, có API chuyên biệt.
- **`annotation-member-kind=METHOD`**, **`annotation-default="general"`**: phần tử `category()` của `@interface Label` có kind `METHOD` và chứa default value.

Ví dụ chủ động lọc `field` và `method` bằng tên qua `ElementFilter`. Lý do: không nên giả định `getEnclosedElements()` chỉ gồm hai member ấy hoặc thứ tự member ngầm định luôn cố định.

### 7.5. Vì sao ví dụ chỉ in một lần?

Processor có thể được gọi trong **nhiều vòng annotation processing**. Biến `done` tránh in lặp; điều kiện `round.processingOver()` tránh xử lý vòng cuối.

`@SupportedAnnotationTypes("*")` nghĩa là processor chấp nhận mọi annotation type cho mục đích nhận vòng xử lý trong bài demo. `return false` cho biết processor **không claim toàn bộ annotation**, để những processor khác vẫn có thể xử lý nếu cần.

Với dự án thực tế, đừng giả định mọi symbol đều tồn tại: `elements.getTypeElement("demo.Box")` có thể trả về `null` nếu tên/type không được phân giải trong môi trường hiện tại. Code sản xuất nên kiểm tra `null` và báo lỗi bằng `processingEnv.getMessager().printMessage(...)`. Ở bài demo, hai file cùng được biên dịch đúng như hướng dẫn nên các phần tử kỳ vọng có mặt.

## 8. `RoundEnvironment`, `Elements` và `ElementFilter` trong quy trình processor

Annotation processor thường kế thừa `AbstractProcessor` và override:

~~~java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    for (Element root : roundEnv.getRootElements()) {
        // Tìm các top-level declaration thuộc vòng biên dịch này.
    }
    return false;
}
~~~

Có hai cách tìm element thông dụng:

**(A) Từ annotation được hỗ trợ:**

~~~java
for (Element element : roundEnv.getElementsAnnotatedWith(MyAnnotation.class)) {
    // Chỉ xử lý các declaration có annotation mục tiêu.
}
~~~

**(B) Từ tên hoặc cấu trúc khai báo:**

~~~java
TypeElement type = processingEnv.getElementUtils()
        .getTypeElement("demo.Box");
~~~

Đây là hai chiến lược bổ sung nhau. `getElementsAnnotatedWith` hữu ích khi framework processor được thiết kế quanh một annotation; `getTypeElement` hữu ích để phân giải một type theo tên từ môi trường compiler.

`ElementFilter` có các helper như:

~~~java
var fields = ElementFilter.fieldsIn(type.getEnclosedElements());
var methods = ElementFilter.methodsIn(type.getEnclosedElements());
var constructors = ElementFilter.constructorsIn(type.getEnclosedElements());
var types = ElementFilter.typesIn(type.getEnclosedElements());
~~~

Chúng **không sửa `getEnclosedElements()`**; chỉ lọc các element theo loại phù hợp. Với record component, dùng `type.getRecordComponents()` hoặc helper dành cho record component trên Java 17.

### Visitor thay cho ép kiểu theo nhánh dài

Nếu phải xử lý nhiều kind, có thể dùng `ElementVisitor` hoặc các lớp tiện ích như `SimpleElementVisitor14` (`javax.lang.model.util`). Visitor cung cấp điểm mở rộng theo loại element và giúp giảm các chuỗi `instanceof` khó bảo trì. Tuy nhiên, phiên bản visitor gắn với phiên bản ngôn ngữ; khi chuyển JDK, hãy kiểm tra class visitor hỗ trợ những kind mới như record.

## 9. Annotation trong mô hình `Element`: `AnnotationMirror` và giá trị mặc định

Một `Element` hỗ trợ:

~~~java
List<? extends AnnotationMirror> mirrors = element.getAnnotationMirrors();
~~~

`AnnotationMirror` đại diện cho một annotation đang được compiler phân tích. Nó có:

- `getAnnotationType()`: kiểu annotation dưới dạng `DeclaredType`.
- `getElementValues()`: map từ `ExecutableElement` (các phần tử annotation) tới `AnnotationValue`; **chỉ gồm giá trị được khai báo tường minh** ở nơi sử dụng.
- `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)`: lấy thêm những phần tử dùng giá trị `default` của annotation interface.

Với `@Label("box")`:

~~~java
@interface Label {
    String value();
    String category() default "general";
}
~~~

Annotation có hai phần tử về mặt API, nhưng ở nơi dùng chỉ viết một:

~~~java
@Label("box")
class Box<T> {}
~~~

Vì thế `mirror.getElementValues().size()` là `1`, trong khi `getElementValuesWithDefaults(mirror).size()` là `2`. Kết quả này đã được ví dụ ở trên xác minh.

**Ưu tiên `AnnotationMirror` trong annotation processor** khi cần quan sát metadata lúc compile-time, đặc biệt đối với retention `SOURCE`, type chưa thể load vào JVM đang chạy processor hoặc phần tử có giá trị kiểu class. Không giả định mọi annotation luôn có thể lấy an toàn thành một runtime annotation proxy và dùng reflection.

Cũng cần phân biệt:

- `element.getAnnotationMirrors()`: annotation được phản ánh tại element theo hợp đồng `AnnotatedConstruct`.
- `processingEnv.getElementUtils().getAllAnnotationMirrors(element)`: tiện ích để lấy annotation hiện diện có xét cơ chế inheritance khi áp dụng.
- `typeMirror.getAnnotationMirrors()`: annotation nằm trên **một type use**; có thể khác với annotation của **declaration**.

Nếu annotation chỉ có `@Target(TYPE_USE)`, hãy xem đúng mô hình kiểu (`TypeMirror`) và nơi nó được dùng, thay vì tìm nhầm trong annotation declaration trên `Element`.

## 10. `Element` không phải AST và cũng không phải reflection

Ba góc nhìn khác nhau:

| Mô hình | Đại diện | Phù hợp khi |
|---|---|---|
| `javax.lang.model.element` | Khai báo Java có kiểm tra symbol/type | Annotation processing lúc biên dịch, tạo code, phân tích cấu trúc declaration |
| `javax.lang.model.type` | Các kiểu Java trong môi trường compiler | So sánh/kiểm tra type, generic, assignability |
| AST / `com.sun.source.tree` (javac Tree API) | Cú pháp nguồn như if, for, invocation, expression | Muốn phân tích cấu trúc câu lệnh, biểu thức, vị trí mã nguồn |
| `java.lang.reflect` | Class/method/field của code đã load vào JVM | Đọc annotation `RUNTIME` và thành viên tại runtime |
| `javap -v` / class-file parser | Cấu trúc class file đã được biên dịch | Kiểm tra metadata và bytecode đã lưu |

Ví dụ, `Element` cho biết method `getOr` có một parameter `fallback`; nhưng nó **không phải một AST đầy đủ cho thân method** gồm toán tử `?:`, phép so sánh `==` và expression `return`. Nếu công cụ cần phân tích từng biểu thức trong body, nên dùng API cây nguồn thích hợp như `Trees`/`TreePathScanner`, không cố tìm tất cả node bằng `getEnclosedElements()`.

Ngược lại, Java reflection có `Class<?>`, `Method`, `Field` của các class đã load; nó không mô tả đầy đủ **type variable, compile-time SOURCE annotation và những declaration chưa được biên dịch** như annotation processing model.

## 11. Lỗi thường gặp khi xử lý Element

### 11.1. Ép mọi element thành `TypeElement`

~~~java
// SAI nếu e là FIELD, METHOD, PARAMETER hoặc RECORD_COMPONENT:
TypeElement t = (TypeElement) e;
~~~

Hãy kiểm tra `getKind()` rồi cast, hoặc dùng pattern `instanceof` khi phù hợp:

~~~java
if (e instanceof TypeElement type) {
    System.out.println(type.getQualifiedName());
}
~~~

### 11.2. So sánh tên thay vì so sánh kind

Hai khai báo ở hai scope khác nhau có thể cùng tên `value`, nhưng một là field, một là annotation member method. Nên dùng **`getKind()` + enclosing context + tên**; không dựa trên chuỗi tên.

### 11.3. Nhầm `ElementKind.TYPE_PARAMETER` và `TypeKind.TYPEVAR`

`T` trong danh sách khai báo type parameter có kind `TYPE_PARAMETER`; kiểu `T` của field/method là `TypeMirror` kind `TYPEVAR`. Đặt hai enum cạnh nhau để không lẫn.

### 11.4. Nhầm record component với component field

`RECORD_COMPONENT` mô tả khai báo trong record header. Field và accessor tương ứng là các element khác. Dùng `TypeElement.getRecordComponents()` và `RecordComponentElement.getAccessor()` khi cần xử lý record trực tiếp.

### 11.5. Bỏ sót giá trị `default` của annotation

`AnnotationMirror.getElementValues()` chỉ trả map giá trị **tường minh**. Dùng `Elements.getElementValuesWithDefaults(...)` nếu logic cần bức tranh đầy đủ.

### 11.6. Tưởng `getEnclosedElements()` bao gồm tất cả member kế thừa

Nó không phải API “lấy mọi member”. Đối với class, dùng `Elements.getAllMembers(type)` khi cần cả inherited members.

### 11.7. Giữ `Element` để dùng ngoài vòng đời compile task

`Element` gắn với **môi trường xử lý/compiler**. Không lưu tham chiếu object rồi kỳ vọng tái sử dụng ổn định trong một compilation khác hay ở runtime. Nếu cần lưu thông tin cho công cụ khác, chuyển thành mô hình dữ liệu rõ ràng gồm qualified name, kind và thông tin signature thích hợp.

### 11.8. Phụ thuộc vào thứ tự implicit members

Compiler có thể thêm default constructor, accessor hoặc method của enum. Hãy chọn member bằng `ElementFilter`, tên, kind và signature; không đọc vị trí danh sách cố định.

### 11.9. Chỉ xử lý vòng processing đầu tiên mà không có chủ đích

Processor có thể sinh thêm source, khiến các vòng annotation processing tiếp tục. Nếu không kiểm soát, code có thể in trùng hoặc tạo file trùng. Với processor thật, cần thiết kế state và chính sách round rõ ràng; ví dụ thực hành dùng `done` để in duy nhất một lần.

### 11.10. Tự lấy annotation `SOURCE` bằng Java reflection

Annotation `RetentionPolicy.SOURCE` có thể tồn tại **trong mô hình compiler khi processor chạy** nhưng không được lưu để đọc qua `Class.getAnnotation` sau biên dịch. Đây là lý do khác để dùng `AnnotationMirror` thay vì runtime reflection.

## 12. Checklist trước khi viết processor

1. **Mục tiêu là declaration hay type?** Chọn `Element`/`ElementKind` hay `TypeMirror`/`TypeKind`.
2. **Kind nào cần xử lý?** Nhận biết cả `CLASS`, `ANNOTATION_TYPE`, `RECORD`, `METHOD`, `PARAMETER` và những kind mới.
3. **Cần duyệt trực tiếp hay toàn bộ member?** Phân biệt `getEnclosedElements()`, `getAllMembers()` và `getRecordComponents()`.
4. **Tên có đủ xác định element?** Dùng qualified name, enclosing chain và signature khi cần, không dựa tên đơn.
5. **Cần đọc annotation SOURCE/CLASS?** Sử dụng compiler model, retention và `AnnotationMirror` đúng vị trí.
6. **Cần giá trị default?** Dùng `getElementValuesWithDefaults`.
7. **Đang xử lý round nào?** Xét `processingOver()`, root elements và khả năng được gọi lại.
8. **Có ép kiểu không an toàn?** Lọc `ElementKind`/dùng `ElementFilter` trước khi cast.
9. **Có kiểm tra compiler bằng ví dụ độc lập?** Chạy `javac --release 17 -processor ...` và đối chiếu output; với logic thực tế, bổ sung unit/integration tests.
10. **Có cần AST thay vì symbol model?** Nếu công việc đòi phân tích biểu thức/câu lệnh, dùng cây nguồn thích hợp.

## 13. Tài liệu chính thức

- [Java SE 17 — `Element`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/Element.html): các thao tác và quan hệ enclosing/enclosed.
- [Java SE 17 — `ElementKind`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ElementKind.html): các loại khai báo trong mô hình.
- [Java SE 17 — `TypeElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/TypeElement.html): class/interface/enum/annotation/record, member và record components.
- [Java SE 17 — `ExecutableElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ExecutableElement.html): method, constructor, parameters, default value.
- [Java SE 17 — `RecordComponentElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/RecordComponentElement.html): component trong record và accessor.
- [Java SE 17 — `Elements`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): tìm type, xem member kế thừa và bổ sung annotation defaults.
- [Java SE 17 — `AnnotationMirror`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html): biểu diễn annotation/value trong compiler.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): roots, annotated elements và vòng xử lý.

**Ghi nhớ:** **`Element` trả lời “khai báo nào?”, `ElementKind` trả lời “khai báo thuộc loại nào?”, `TypeMirror`/`TypeKind` trả lời “kiểu của nó là gì?”.** Trong annotation processor, hãy duyệt mô hình theo enclosing/enclosed, kiểm tra kind rồi chọn interface chuyên biệt. Dùng `AnnotationMirror` cho compile-time metadata, hiểu rõ record component và annotation defaults, đồng thời tránh nhầm mô hình declaration với AST hoặc reflection runtime.