# TypeMirror và phân biệt mô hình kiểu với Class lúc chạy trong Java

Trong hệ sinh thái annotation của Java, có hai cách nhìn về kiểu dữ liệu cần phân biệt:

- **Mô hình ngôn ngữ tại thời điểm biên dịch:** `javax.lang.model.type.TypeMirror` biểu diễn một *kiểu Java* mà trình biên dịch hoặc annotation processor đang phân tích. Nó có thể biểu diễn `List<String>`, `T extends Number`, wildcard, mảng, kiểu nguyên thủy và cả kiểu chưa thể phân giải hoàn chỉnh.
- **Đối tượng kiểu ở thời điểm chạy:** `java.lang.Class<?>` biểu diễn một class/interface/array/primitive/`void` trong runtime JVM. Nó gắn với class loading và reflection, không phải mô hình cú pháp/ngữ nghĩa đầy đủ của compiler.

Hai mô hình phục vụ những thời điểm khác nhau. **Không ép kiểu `TypeMirror` sang `Class<?>`**, cũng không giả định một kiểu mà processor thấy đã có thể được JVM load. Annotation processing có thể chạy **trước khi class đang xử lý được biên dịch thành bytecode**.

Ví dụ về cùng một khai báo:

```java
import java.util.List;

class Catalog {
    List<String> items;
}
```

- Annotation processor duyệt field `items` có thể lấy `VariableElement.asType()` và nhận một `DeclaredType` tương ứng với `java.util.List<java.lang.String>`.
- Sau khi biên dịch, `List.class` là `Class<List>` cho kiểu thô `List` (theo cách literal class được typed); không có `List<String>.class` trong Java.
- Runtime reflection **vẫn có** API `Field.getGenericType()` trả về `java.lang.reflect.Type` và có thể cho biết `List<String>` từ generic signature; không được nhầm điều đó với việc `Class<?>` tự giữ mọi đối số generic.

Bài này tập trung vào việc sử dụng `TypeMirror` đúng chỗ trong **annotation processing, mô hình ngôn ngữ và phân tích kiểu**; phần về `Class<?>` chỉ dùng để chỉ rõ ranh giới với runtime.

## 1. TypeMirror tồn tại trong mô hình ngôn ngữ nào?

Các API cơ bản của `javax.lang.model` thuộc module chuẩn `java.compiler`. Một số thành phần liên hệ với nhau:

| API | Câu hỏi mà nó trả lời |
| --- | --- |
| `Element` | “Đây là **khai báo/phần tử chương trình** nào?” |
| `TypeElement` | “Đây là khai báo class, interface, enum, record hoặc annotation type nào?” |
| `VariableElement` | “Đây là field, tham số, biến hay enum constant nào?” |
| `ExecutableElement` | “Đây là method, constructor hoặc annotation element nào?” |
| `TypeMirror` | “**Kiểu Java** của phần tử/biểu thức trong mô hình biên dịch là gì?” |
| `TypeKind` | “Kiểu đó thuộc nhóm nào: `DECLARED`, `ARRAY`, `TYPEVAR`, ...?” |
| `Types` | “Hai kiểu có bằng nhau, gán được, là subtype, hoặc có erasure nào?” |
| `Elements` | “Tìm khai báo theo tên, đọc thành phần và thông tin của khai báo như thế nào?” |

Ví dụ:

```java
// Trong processor, giả sử 'field' là VariableElement cho field items.
TypeMirror type = field.asType();
TypeKind kind = type.getKind();
```

Đây là **đoạn minh họa**, chưa phải chương trình độc lập (cần `VariableElement`, `TypeMirror`, `TypeKind` và biến `field`). Khi field là `List<String> items;`, `kind` thường là `TypeKind.DECLARED` vì đây là declared reference type được tham số hóa.

**Phân biệt `Element` với `TypeMirror`:**

- `TypeElement` cho bạn **khai báo List** — nơi có tên, modifier và các thành viên.
- `DeclaredType` cho bạn **một dạng kiểu List được sử dụng**, ví dụ `List<String>` hoặc `List<Integer>`, với những type arguments khác nhau.
- `VariableElement` cho bạn **khai báo field items**, còn `items.asType()` cho kiểu của field.

Đây không phải hai tên gọi khác nhau của cùng một đối tượng.

## 2. Các dạng TypeMirror thường gặp

`TypeMirror` là interface gốc của họ các interface mô hình kiểu. Một số dạng tiêu biểu:

| TypeKind hoặc interface | Minh họa trong Java | Cách xem |
| --- | --- | --- |
| `PrimitiveType` / `INT` | `int` | `getKind()==TypeKind.INT` |
| `DeclaredType` / `DECLARED` | `String`, `List<String>` | `getTypeArguments()` |
| `ArrayType` / `ARRAY` | `String[]` | `getComponentType()` |
| `TypeVariable` / `TYPEVAR` | `T` trong `class Box<T>` | `getUpperBound()` |
| `WildcardType` / `WILDCARD` | `? extends Number` | `getExtendsBound()` / `getSuperBound()` |
| `ExecutableType` / `EXECUTABLE` | Kiểu chữ ký của method/constructor | `getParameterTypes()`, `getReturnType()` |
| `NoType`, `NullType` | Kiểu giả `void`, package/module hoặc null type | Xét `getKind()` |
| `ErrorType` / `ERROR` | Một declared type chưa mô hình hóa đầy đủ | Cần xử lý khi phân giải chưa hoàn tất |

Lưu ý các `TypeKind` như `VOID`, `NONE`, `NULL` có ý nghĩa riêng. Không phải mọi `TypeMirror` đều tương ứng với một đối tượng `Class` có thể load. Ví dụ `? extends Number` chỉ là **wildcard type**, không phải một class độc lập.

### TypeMirror.toString() dùng để làm gì?

`TypeMirror.toString()` cung cấp **biểu diễn văn bản mang tính thông tin** của kiểu. Thường nó in tên đầy đủ như `java.util.List<java.lang.String>`, rất hữu ích cho log và thông báo lỗi.

Nhưng **không** lấy chuỗi đó để suy ra mọi quy tắc type checking, tự parse bằng regex hay dùng làm định danh ổn định tuyệt đối. Với logic compiler, hãy sử dụng `Types`, `TypeKind` và các interface chuyên biệt.

## 3. TypeMirror khác Class<?> như thế nào?

| Tiêu chí | `TypeMirror` | `Class<?>` |
| --- | --- | --- |
| Package | `javax.lang.model.type` | `java.lang` |
| Giai đoạn sử dụng chính | Biên dịch, annotation processing, phân tích cấu trúc nguồn | Runtime, class loading, reflection |
| Ý nghĩa | Một **kiểu của ngôn ngữ Java** trong mô hình compiler | Một **runtime class object** |
| Generic đã tham số hóa | Có `DeclaredType` với type arguments riêng | `List.class` không đại diện riêng `List<String>` |
| Wildcard/type variable | Có `WildcardType`, `TypeVariable` | Một `Class<?>` đơn lẻ không mô tả những cấu trúc này |
| Primitive | Có `PrimitiveType` | Có ví dụ `int.class` |
| Kiểu đang lỗi/chưa hoàn chỉnh | Có thể có `ErrorType` | Không phải một class runtime tải được tương đương |
| Thao tác so sánh kiểu | `Types.isSameType()`, `isAssignable()` ... | So sánh class, `isAssignableFrom()` ... |
| Truy cập thông tin khai báo | `Types.asElement()`, `DeclaredType.asElement()` | `Class.getDeclaredMethods()`, `getDeclaredFields()` ... |
| Phụ thuộc class loader | Không cần tải class được mô hình hóa như runtime class | Gắn với runtime class identity và class loader |

**Điểm tinh tế về generics:** Java reflection có các interface `java.lang.reflect.Type`, `ParameterizedType`, `TypeVariable`, `WildcardType` và `GenericArrayType`. Chúng có thể phản ánh **một phần cấu trúc generic được lưu trong class file** trên field/method. Vì thế không nên nói “runtime hoàn toàn không có thông tin generic”. Câu đúng là: **`Class<?>` tự nó không biểu diễn một `List<String>` cụ thể, và runtime reflection không thay thế toàn bộ mô hình compiler `TypeMirror`**.

### Tại sao không chuyển thẳng TypeMirror thành Class?

Khi processor đang phân tích `com.example.FutureService`, tệp class có thể **chưa được tạo**, thậm chí source có thể đang thiếu dependency hoặc bị lỗi tạm thời. Chạy `Class.forName("com.example.FutureService")` có thể thất bại; nếu load thành công cũng có thể lấy **phiên bản class cũ** trên classpath chứ không phải khai báo mới đang biên dịch.

Đừng làm:

```java
// SAI về mô hình: TypeMirror không phải java.lang.Class.
Class<?> runtimeClass = (Class<?>) typeMirror;
```

Đây là **mã minh họa cố ý không biên dịch được** (với `typeMirror` có kiểu `TypeMirror`). `typeMirror.getClass()` cũng chỉ trả về **class của đối tượng thực thi TypeMirror trong compiler**, không phải `Class` của kiểu mà nó đang biểu diễn.

Hãy để processor xử lý kiểu bằng `TypeMirror` và `Types`. Chỉ dùng `Class<?>` khi bạn thực sự đang ở mô hình runtime và cần tương tác với class đã load.

## 4. DeclaredType giúp giữ type arguments trước erasure

Giả sử có hai field:

```java
import java.util.List;

class Samples {
    List<String> names;
    List<Integer> counts;
}
```

Annotation processor đọc:

```java
// Hai biến fieldNames và fieldCounts là VariableElement thích hợp.
DeclaredType first = (DeclaredType) fieldNames.asType();
DeclaredType second = (DeclaredType) fieldCounts.asType();

// Kết quả type arguments lần lượt mô tả String và Integer.
first.getTypeArguments();
second.getTypeArguments();
```

Đây là **đoạn minh họa**, không phải một tệp chạy độc lập. Mỗi `DeclaredType` chứa thông tin kiểu được dùng (bao gồm type arguments), còn `first.asElement()` và `second.asElement()` cùng trỏ về khai báo `java.util.List` theo mô hình ngôn ngữ.

Ở runtime, cả hai instance `ArrayList<String>` và `ArrayList<Integer>` đều thuộc cùng runtime class `ArrayList.class`. Khác biệt ở source generic bị *erasure* trong các thao tác runtime thông thường. Tuy vậy, `Samples.class.getDeclaredField("names").getGenericType()` có thể phản ánh `List<String>` do khai báo mang generic signature; đó là API `java.lang.reflect.Type`, không phải `Class<List<String>>`.

### So sánh kiểu đúng cách bằng Types

`TypeMirror` không cam kết rằng một kiểu luôn được đại diện bởi **cùng một instance object**. Do đó, không dùng `==` hoặc `equals()` như tiêu chuẩn chung để kết luận hai kiểu Java có nghĩa tương đương.

Trong processor:

```java
Types types = processingEnv.getTypeUtils();

boolean same = types.isSameType(type1, type2);
boolean assignable = types.isAssignable(type1, type2);
boolean subtype = types.isSubtype(type1, type2);
TypeMirror erased = types.erasure(type1);
```

Đây là **đoạn minh họa** bên trong một `AbstractProcessor`; cần import `javax.lang.model.util.Types` và có sẵn hai `TypeMirror` tên `type1`, `type2`.

- `isSameType(a,b)`: kiểm tra cùng kiểu theo quy tắc mô hình ngôn ngữ.
- `isAssignable(a,b)`: kiểm tra một kiểu có thể gán cho kiểu khác.
- `isSubtype(a,b)`: quan hệ subtype (không đồng nghĩa hoàn toàn với assignability).
- `erasure(t)`: biểu diễn kiểu sau erasure theo quy tắc của `Types`.

**Không đánh đồng** `Types.isAssignable(source,target)` tại compile time với `Class.isAssignableFrom(otherClass)` ở runtime: API phía sau làm việc với class đã load, API phía trước làm việc với các Java types có thể gồm generic arguments và cấu trúc chưa tồn tại dưới dạng runtime class.

## 5. Annotation processor lấy TypeMirror từ đâu?

Một annotation processor thường mở rộng `javax.annotation.processing.AbstractProcessor`, được `javac` gọi trong các vòng (rounds) khi biên dịch. Các API chính:

1. `RoundEnvironment.getElementsAnnotatedWith(...)` tìm những phần tử được gắn annotation cần xử lý.
2. `Element.asType()` lấy `TypeMirror` của phần tử phù hợp.
3. `TypeMirror.getKind()` xem dạng kiểu.
4. `DeclaredType.getTypeArguments()` xem đối số generic.
5. `DeclaredType.asElement()` truy về khai báo kiểu nếu cần tên, modifiers hoặc các thành viên.
6. `ProcessingEnvironment.getTypeUtils()` và `getElementUtils()` cung cấp `Types` và `Elements`.

### Ví dụ Java 17 đầy đủ với annotation processor

Dùng **hai tệp** trong cùng một thư mục, không có package declaration. Ví dụ dùng `@Deprecated` có sẵn trong JDK làm dấu chọn field để giữ trọng tâm ở mô hình kiểu. Processor chỉ in metadata, **không xử lý lỗi thời của API**.

Tệp thứ nhất: **`TypeModelProcessor.java`**.

```java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeMirror;

@SupportedAnnotationTypes("java.lang.Deprecated")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class TypeModelProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) return false;

        for (Element element : roundEnv.getElementsAnnotatedWith(Deprecated.class)) {
            if (element.getKind() != ElementKind.FIELD) continue;

            TypeMirror type = element.asType();
            System.out.println("element=" + element.getSimpleName());
            System.out.println("type=" + type);
            System.out.println("kind=" + type.getKind());
            System.out.println("same=" +
                    processingEnv.getTypeUtils().isSameType(type, type));

            if (type instanceof DeclaredType declared) {
                System.out.println("arguments=" + declared.getTypeArguments());
                TypeElement raw = (TypeElement) declared.asElement();
                System.out.println("raw=" + raw.getQualifiedName());
            }
        }
        return false;
    }
}
```

Tệp thứ hai: **`Catalog.java`**.

```java
import java.util.List;

public class Catalog {
    @Deprecated
    List<String> items;
}
```

Chạy với JDK 17+ theo đúng thứ tự:

```bash
javac --release 17 -encoding UTF-8 TypeModelProcessor.java
javac --release 17 -encoding UTF-8 -processor TypeModelProcessor -proc:only Catalog.java
```

Cờ `-processor TypeModelProcessor` chỉ định processor, không cần cấu hình `META-INF/services`. Cờ `-proc:only` yêu cầu javac **chỉ xử lý annotation**, không tạo `Catalog.class`. Đây là điểm quan trọng: processor vẫn đọc được kiểu `List<String>` **trước khi class đích được tạo ra**.

Kết quả stdout của lệnh **thứ hai**, đã được kiểm chứng khi chạy thử JDK với `--release 17`:

```text
element=items
type=java.util.List<java.lang.String>
kind=DECLARED
same=true
arguments=java.lang.String
raw=java.util.List
```

Giải thích:

- `element=items`: `VariableElement` đại diện cho field mang `@Deprecated`.
- `type=java.util.List<java.lang.String>`: `element.asType()` biểu diễn kiểu khai báo của field, gồm generic argument.
- `kind=DECLARED`: đây là một declared reference type.
- `same=true`: `Types.isSameType(type,type)` xác nhận một kiểu bằng chính nó.
- `arguments=java.lang.String`: list đối số generic chứa một `TypeMirror` biểu diễn `String`.
- `raw=java.util.List`: `DeclaredType.asElement()` quay về khai báo interface `List`, khác với instance type `List<String>`.

**Đầu ra thuộc giai đoạn javac/processor, không phải stdout của `java Catalog`.** `Catalog` không có `main` và không được chạy như chương trình; trong lệnh thứ hai `-proc:only` còn chủ động tránh phát sinh `Catalog.class`.

### Trình tự thực tế trong một dự án

Thông thường processor được biên dịch thành JAR và đăng ký với `ServiceLoader` bằng `META-INF/services/javax.annotation.processing.Processor` hoặc được chỉ định bằng option của compiler/build tool. Ví dụ trên chọn cách `-processor` để học viên không cần dựng JAR hay tệp dịch vụ.

Một processor có thể được gọi nhiều vòng. Hãy xét `roundEnv.processingOver()` và quan hệ giữa các phần tử đã/generate trong mỗi vòng, thay vì giả định callback chỉ xảy ra đúng một lần cho toàn bộ build.

## 6. Khi element là Class<?>: MirroredTypeException

Một tình huống hay gặp trong **annotation processing** là annotation có element kiểu `Class<?>`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface Mapper {
    Class<?> target();
}

@Mapper(target = java.util.List.class)
class MyMapping {}
```

Đây là các **khai báo minh họa hợp lệ**. Khi processor đọc metadata bằng:

```java
Mapper annotation = typeElement.getAnnotation(Mapper.class);
Class<?> target = annotation.target();
```

Đoạn này **không phải chương trình độc lập**; `typeElement` cần là `TypeElement` tương ứng với `MyMapping`. Trong ngữ cảnh `javax.lang.model`, lời gọi element trả về `Class<?>` **không phải con đường đáng tin để lấy class runtime**. API có thể ném `javax.lang.model.type.MirroredTypeException` khi cần biểu diễn kiểu bằng `TypeMirror` thay vì class đã load.

Mẫu làm việc theo mô hình compiler:

```java
import javax.lang.model.type.MirroredTypeException;
import javax.lang.model.type.TypeMirror;

// Trong processor, sau khi xác nhận annotation != null:
try {
    annotation.target();
} catch (MirroredTypeException ex) {
    TypeMirror referencedType = ex.getTypeMirror();
    // Dùng Types/TypeKind/DeclaredType để xử lý kiểu.
}
```

Đây chỉ là **minh họa luồng API**, không phải một class độc lập. Khi viết processor thực tế, thường nên ưu tiên **`AnnotationMirror` + `AnnotationValue`**, tránh cố chuyển qua `Class<?>` ngay từ đầu.

### Lối đi bền vững: AnnotationMirror

`Element.getAnnotationMirrors()` trả những `AnnotationMirror` của phần tử ở mô hình ngôn ngữ. Mỗi `AnnotationMirror`:

- Có `getAnnotationType()` trả về `DeclaredType` của kiểu annotation.
- Có `getElementValues()` trả map từ `ExecutableElement` tới `AnnotationValue` **chỉ cho những giá trị ghi tường minh**.
- Có thể kết hợp `Elements.getElementValuesWithDefaults(annotationMirror)` khi cần gồm cả giá trị mặc định.

Với annotation element `Class<?> target()`, `AnnotationValue.getValue()` trong mô hình annotation processing tương ứng với một `TypeMirror` theo hợp đồng javax.lang.model, **không cần load `Class<?>` đích**.

Ví dụ minh họa:

```java
// Trong processor, với AnnotationMirror mirror đã chọn.
var withDefaults =
        processingEnv.getElementUtils().getElementValuesWithDefaults(mirror);

for (var entry : withDefaults.entrySet()) {
    Object value = entry.getValue().getValue();
    // Nếu element là Class<?>: value biểu diễn kiểu bằng TypeMirror.
    System.out.println(entry.getKey().getSimpleName() + "=" + value);
}
```

Đây là **đoạn code phụ thuộc ngữ cảnh processor** (không phải tệp chạy độc lập), thích hợp khi muốn duyệt element/value mà không gắn trực tiếp processor với một proxy annotation type duy nhất.

Nếu annotation element có kiểu `Class<?>[]`, tình huống tương tự có thể dùng `MirroredTypesException` hoặc một danh sách `AnnotationValue` chứa giá trị tương ứng; không nên giả định JVM luôn load được từng class được nhắc đến.

## 7. Elements, Types và việc tra cứu kiểu qua tên

Trong processor, cách “tìm kiểu theo tên” khác với runtime reflection:

```java
// Trong AbstractProcessor:
TypeElement element =
        processingEnv.getElementUtils().getTypeElement("java.util.List");

if (element != null) {
    TypeMirror declared = element.asType();
    System.out.println(declared);
}
```

Đây là **đoạn code trong ngữ cảnh processor**. `Elements.getTypeElement(...)` tra cứu khai báo kiểu trong **môi trường xử lý của compiler**, không gọi `Class.forName` để load một runtime class. Kết quả có thể phụ thuộc module, symbol resolution và việc type có trong mô hình hiện hành hay không.

Nếu cần phân biệt **một khai báo** với **một kiểu dùng khai báo ấy**:

- `TypeElement` đại diện khai báo class/interface.
- `TypeElement.asType()` cung cấp kiểu tương ứng của khai báo (có thể có type parameters theo bối cảnh).
- `Types.getDeclaredType(typeElement, args...)` tạo `DeclaredType` theo những type arguments mà compiler model chấp nhận.
- `DeclaredType.getTypeArguments()` đọc các đối số kiểu.
- `Types.asElement(type)` hữu ích khi muốn quay từ một declared type sang khai báo của nó.

Khi xử lý module-aware code, những API tra cứu trên `Elements` còn có biến thể lấy `ModuleElement` để tránh nhập nhằng kiểu cùng tên trong những module khác nhau. Không viết processor dựa vào classpath runtime tùy tiện để thay thế symbol table của compiler.

## 8. Annotation trên type-use và TypeMirror

Kể từ Java 8, annotation không chỉ được gắn trên khai báo mà còn trên **vị trí sử dụng kiểu**, ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_USE)
@interface Tag {}

class TypesWithTag {
    List<@Tag String> names;
}
```

Đây là các khai báo hợp lệ. Trong processor, một `TypeMirror` còn triển khai giao diện `AnnotatedConstruct` nên có thể cung cấp `getAnnotationMirrors()` cho **type-use annotations trực tiếp trên cấu trúc kiểu được xét**.

Ví dụ khi duyệt field `names`:

1. `field.asType()` là một `DeclaredType` cho `List<String>`.
2. Chọn `DeclaredType.getTypeArguments().get(0)` để lấy `TypeMirror` của đối số kiểu `String`.
3. Dùng `getAnnotationMirrors()` trên TypeMirror đối số ấy để xem annotation type-use `@Tag`.

Không đánh đồng `field.getAnnotationMirrors()` (annotation **trên khai báo field**) với annotation nằm **trên type argument bên trong kiểu của field**.

Runtime reflection cung cấp mô hình khác: `Field.getAnnotatedType()` và `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`. Hai API này làm việc với metadata còn lưu sau biên dịch và các điều kiện retention, không phải cùng một object hay vòng đời với `TypeMirror` trong processor.

## 9. ErrorType, nhiều vòng processing và các giới hạn của model

Trong annotation processing, các kiểu không nhất thiết đều ở trạng thái đã phân giải hoàn chỉnh. `TypeKind.ERROR` và `ErrorType` có thể xuất hiện khi một class/interface type chưa được mô hình hóa đầy đủ (chẳng hạn thiếu dependency hoặc source sẽ được sinh ra ở vòng sau).

Hãy thiết kế processor để:

- Kiểm tra `getKind()` hoặc dùng `TypeVisitor` thay vì cast mọi kiểu sang `DeclaredType`.
- Xử lý kiểu chưa phân giải một cách có kiểm soát, nhất là khi processor hỗ trợ **generated sources**.
- Tránh giữ `TypeMirror` rồi so sánh bằng identity hoặc dùng mã đối tượng như khóa ổn định qua môi trường/compilation khác nhau.
- Không load class đang biên dịch chỉ để “xác nhận” type: cách này có thể đụng bytecode cũ và khác classloader.
- Phát diagnostic có ích bằng `Messager` nếu kiểu/annotation không đúng hợp đồng.

API `TypeMirror.accept(TypeVisitor,...)` hỗ trợ triển khai các phép phân tích theo từng dạng kiểu. Với một processor cần xử lý array, wildcard, generics và các kiểu đặc biệt, visitor thường rõ ràng và ổn định hơn chuỗi cast cố định.

**Tính đúng phụ thuộc round:** Khi processor sinh thêm source, những khai báo mới có thể xuất hiện ở round sau. Không mặc định mọi symbol có thể được resolve đầy đủ ngay tại lượt đầu.

## 10. Những lỗi phổ biến khi phân biệt TypeMirror và Class

| Hiểu nhầm | Điều đúng cần nhớ |
| --- | --- |
| “`TypeMirror` thực chất là `Class<?>` khác tên” | Chúng thuộc hai mô hình khác nhau |
| “Có `TypeMirror` là lấy được `Class.forName` ngay” | Class đang xử lý có thể chưa tồn tại dưới dạng runtime class |
| “`getClass()` trên TypeMirror cho biết class được đại diện” | Nó trả class **của object TypeMirror**, không phải kiểu Java được mô hình hóa |
| “`TypeElement` và `DeclaredType` thay thế nhau được” | Một bên là khai báo; bên kia là một kiểu sử dụng khai báo ấy |
| “`List<String>` không thể phân biệt khỏi `List<Integer>` trong compiler” | `DeclaredType` lưu các type arguments; erasure không xóa thông tin khỏi mô hình compiler |
| “Runtime không có API generic nào” | Runtime có `java.lang.reflect.Type` và các subinterfaces, nhưng không phải toàn bộ compiler model |
| “So sánh hai TypeMirror dùng `==`” | Dùng `Types.isSameType()` khi cần so sánh kiểu theo ngữ nghĩa |
| “Lấy `Class<?>` trực tiếp từ annotation element khi processing là luôn an toàn” | Có thể gặp `MirroredTypeException`; dùng `AnnotationMirror`/`TypeMirror` |
| “Annotation có `Class<?>` nghĩa là processor bắt buộc load class đó” | Mô hình annotation processing có thể mô tả bằng `TypeMirror` mà không load class |
| “Mọi TypeMirror đều là DeclaredType” | Primitive, array, wildcard, type variable, error, void... có các dạng riêng |
| “`TypeMirror.toString()` là định danh chuẩn để so sánh kiểu” | Dùng các phép toán của `Types`, không dựa vào chuỗi hiển thị |

## 11. Checklist triển khai một annotation processor an toàn

1. **Xác định phase:** chỉ xử lý metadata tại compile time hay cần runtime behavior? Với compile time, dùng `javax.lang.model`.
2. **Chọn đúng Element:** `TypeElement` cho khai báo kiểu, `VariableElement` cho field/parameter, `ExecutableElement` cho method/constructor.
3. **Lấy TypeMirror đúng nguồn:** `element.asType()`, type arguments, return type hoặc bounds theo yêu cầu.
4. **Phân nhánh theo kind:** tránh cast ngầm mọi kiểu về `DeclaredType`.
5. **So sánh với Types:** `isSameType`, `isAssignable`, `erasure`... thay cho `==` và chuỗi.
6. **Tra cứu khai báo với Elements:** tránh load class chỉ để biết tên/quan hệ ở compiler model.
7. **Đọc annotation values qua model:** ưu tiên `AnnotationMirror` và default values khi cần; xử lý `Class<?>`-valued element cẩn thận.
8. **Lưu ý rounds/error types:** generated sources và symbol chưa hoàn chỉnh có thể thay đổi điều thấy được qua từng vòng.
9. **Kiểm thử 2 phase:** biên dịch processor, rồi biên dịch nguồn mẫu với `-processor` và xác minh diagnostic/đầu ra thực tế.
10. **Không trộn trách nhiệm:** Processor phân tích/sinh mã tại compile time; reflection `Class<?>` hoạt động trên những runtime classes đã load.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `TypeMirror` có thể mô hình hóa `List<String>` trong khi không tồn tại `List<String>.class`?

**Đáp án:** `TypeMirror` thuộc mô hình kiểu tại compile time và `DeclaredType` có thể giữ type arguments. Class literal chỉ tham chiếu runtime class `List.class`, không tạo class object riêng cho từng kiểu generic đã tham số hóa.

**Câu 2.** Processor gặp `VariableElement` cho field `String[] names`. Có nên cast `asType()` sang `DeclaredType` không?

**Đáp án:** Không. Kiểu field là array, dùng `ArrayType` và `getComponentType()`.

**Câu 3.** Hai `TypeMirror` thể hiện cùng kiểu Java cần kiểm tra bằng API nào?

**Đáp án:** `Types.isSameType()`, không suy luận từ `==` hoặc `toString()`.

**Câu 4.** Annotation element có kiểu `Class<?> target();`. Vì sao processor không nên luôn gọi `annotation.target()` và nhận `Class<?>`?

**Đáp án:** Môi trường biên dịch không đảm bảo class được nhắc đến đã load hoặc thậm chí đã được tạo. Lời gọi có thể ném `MirroredTypeException`; mô hình `AnnotationMirror`/`TypeMirror` phù hợp hơn.

**Câu 5.** Khi gọi `javac -proc:only` như ví dụ, processor vẫn đọc được `Catalog.items` không?

**Đáp án:** Có. Processor hoạt động trên mô hình ngôn ngữ do javac xây dựng; không cần `Catalog.class` được tạo.

**Câu 6.** Runtime reflection có đọc được generic signature `List<String>` không?

**Đáp án:** Có thể. `Field.getGenericType()` có thể trả `ParameterizedType` cho field khai báo `List<String>` khi metadata generic cần thiết được lưu. Nhưng đó là API `java.lang.reflect.Type`, không phải `TypeMirror` hay một `Class<List<String>>` riêng.

**Câu 7.** Processor muốn lấy khai báo interface của `List<String>` thì nên dùng gì?

**Đáp án:** Với `DeclaredType` phù hợp, dùng `asElement()` hoặc `Types.asElement()` để về `TypeElement` của `List`.

## Nguồn chính thức

- [Java SE 17: TypeMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html).
- [Java SE 17: DeclaredType](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/DeclaredType.html).
- [Java SE 17: TypeKind](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeKind.html).
- [Java SE 17: Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html).
- [Java SE 17: Elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html).
- [Java SE 17: AnnotationMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html).
- [Java SE 17: MirroredTypeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/MirroredTypeException.html).
- [Java SE 17: Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).

**Kết luận:** Để hiểu **kiểu như ngôn ngữ Java nhìn thấy lúc biên dịch**, dùng `TypeMirror` cùng `Elements` và `Types`. Để phản chiếu **class đang tồn tại ở JVM**, dùng `Class<?>` và các API reflection. Hai mô hình bổ sung cho nhau nhưng không thể thay thế bằng ép kiểu hay gọi `Class.forName` một cách máy móc.
