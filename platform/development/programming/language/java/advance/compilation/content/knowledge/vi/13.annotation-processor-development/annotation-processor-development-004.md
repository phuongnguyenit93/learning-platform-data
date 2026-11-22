# Đọc Element, TypeMirror và mô hình ngôn ngữ khi xây dựng Java Annotation Processor

## 1. Mục tiêu: phân tích mã Java trước khi có Class ở runtime

Một annotation processor chạy trong quá trình `javac` biên dịch, khi chương trình đang được kiểm tra cú pháp và kiểu. Ở thời điểm này, nhiều lớp trong source **chưa có file `.class`**, nên không thể coi việc gọi `Class.forName(...)` hoặc Java Reflection là cách đáng tin để khám phá các khai báo nguồn.

Java cung cấp **Language Model API** trong module `java.compiler` để mô hình hóa khai báo và kiểu:

- **`Element`** trả lời: *đây là khai báo gì* — class, interface, method, constructor, field, parameter, type parameter, package hoặc module?
- **`TypeMirror`** trả lời: *kiểu Java của một vị trí/khai báo là gì* — primitive, declared type, array, type variable, wildcard, executable type, error type, v.v.?
- **`Elements`** và **`Types`** là hai nhóm utility truy vấn tên, package, thành viên, so sánh và biến đổi kiểu theo **ngữ nghĩa compiler**.
- **`RoundEnvironment`** cho biết những khai báo nào trong lượt xử lý hiện tại mang annotation được processor hỗ trợ.
- **`ProcessingEnvironment`** cung cấp `Elements`, `Types`, `Messager`, `Filer` và các options của processor.

Trong bài, ta sẽ viết một processor thực sự đọc class generic `Store<T extends Number>`, thu thập tên/kiểu của field bằng `Element` và `TypeMirror`, gọi `Types.erasure(...)`, rồi sinh một class nguồn Java có thể chạy. Ví dụ được biên dịch và chạy bằng OpenJDK 21 với `--release 17`; các API chính dùng được từ Java 17.

### Kết quả học tập

1. Phân biệt **declaration** (`Element`) và **type** (`TypeMirror`), không dùng sai Reflection.
2. Từ `TypeElement` đi xuống field/method/constructor và lên package, superclass, interfaces.
3. Phân biệt `TypeKind`, `DeclaredType`, `TypeVariable`, `ArrayType`, `ExecutableType` và `ErrorType`.
4. Dùng `Elements` và `Types` cho các thao tác đúng ngữ nghĩa: `isSameType`, `isAssignable`, `erasure`, `asMemberOf`.
5. Thiết kế bộ đọc ổn định khi gặp generics, inheritance, annotations và nhiều processing rounds.
6. Biết khi nào nên đọc mô hình, khi nào dùng `Filer`/`Messager` và khi nào cần API cây cú pháp.

## 2. Ba tầng khác nhau: source, language model và reflection

Hãy xem một khai báo Java:

```java
class Store<T extends Number> {
    private T id;
    private java.util.List<String> names;
}
```

Ở mã nguồn, `T` là type parameter có bound `Number`; `List<String>` là parameterized type. Trình biên dịch phải kiểm tra những kiểu này **trước** khi tạo bytecode.

| Tầng | Biểu diễn | Phù hợp để làm gì? |
| --- | --- | --- |
| Mã nguồn | `class Store<T extends Number>`, `List<String>` | Con người viết, IDE chỉnh sửa |
| **Language Model API** | `TypeElement` của `Store`; `VariableElement` của field; `TypeMirror` của `T` và `List<String>` | Processor đọc khai báo và kiểu ngay lúc compile |
| Binary/runtime | `Store.class`; JVM descriptors; `java.lang.Class`, `java.lang.reflect.Field` | Load/link/reflect trên những class đã được tạo |

Một field `names` có thể được mô hình hóa bởi **hai đối tượng mang ý nghĩa khác nhau**:

- `VariableElement`: *field nào, tên gì, modifiers gì, nằm trong class nào?*
- `TypeMirror` trả từ `field.asType()`: *kiểu nào được khai báo ở field đó?* — `java.util.List<java.lang.String>`.

Có thể có nhiều vị trí dùng **cùng một kiểu** `List<String>` nhưng mỗi field là một `VariableElement` khác nhau. Ngược lại, một `TypeElement` như `java.util.List` đại diện **khai báo generic** `List<E>`, trong khi nhiều `DeclaredType` có thể đại diện những kiểu dùng khác nhau như `List<String>` và `List<Integer>`.

**Điểm cần nhớ:** `Element` không có nghĩa là “một đối tượng thuộc kiểu đó đang tồn tại ở JVM”. `TypeMirror` không phải `Class<?>`. Không dùng `instanceof java.lang.Class` để suy luận về compile-time model.

## 3. Element: sơ đồ các loại khai báo

`Element` là interface gốc ở `javax.lang.model.element`. Những subtype thường gặp:

| Subtype | Đại diện | API đáng dùng |
| --- | --- | --- |
| `PackageElement` | Package Java | `getQualifiedName()`, `getEnclosedElements()` |
| `ModuleElement` | Module JPMS | `getQualifiedName()`, `getDirectives()` |
| `TypeElement` | Class, interface, record, enum, annotation interface | `getQualifiedName()`, `getTypeParameters()`, `getSuperclass()`, `getInterfaces()` |
| `ExecutableElement` | Method hoặc constructor | `getParameters()`, `getReturnType()`, `getThrownTypes()`, `getTypeParameters()` |
| `VariableElement` | Field, parameter, enum constant, v.v. | `getSimpleName()`, `asType()`, `getConstantValue()` |
| `TypeParameterElement` | Khai báo `T`, `E`, `K` | `getBounds()`, `getGenericElement()` |
| `RecordComponentElement` | Record component | `getAccessor()`, `asType()` |

`ElementKind` phân biệt chính xác bản chất declaration, ví dụ `CLASS`, `INTERFACE`, `ENUM`, `RECORD`, `METHOD`, `CONSTRUCTOR`, `FIELD`, `PARAMETER`, `TYPE_PARAMETER`, `PACKAGE`, `MODULE`. Với một field, nên kiểm tra `member.getKind() == ElementKind.FIELD` **trước** khi ép kiểu `(VariableElement) member`.

Một số API gốc của `Element`:

- `getSimpleName()`: tên đơn giản, thường không chứa tên package. Với một số kinds đặc biệt, tên có thể không giống định dạng người học đoán từ mã nguồn.
- `getKind()`: loại declaration; đây là tiêu chí lựa chọn branch đáng tin hơn việc tự phân tích chuỗi từ `toString()`.
- `getModifiers()`: tập `Modifier` như `PUBLIC`, `PRIVATE`, `STATIC`, `FINAL`. Modifiers trên declaration khác với các ràng buộc ngữ nghĩa chỉ được suy ra từ context.
- `getEnclosingElement()`: khai báo bao chứa trực tiếp, chẳng hạn field thuộc class, class top-level thuộc package.
- `getEnclosedElements()`: các khai báo con **trực tiếp**, không tự động là toàn bộ thành viên được kế thừa.
- `getAnnotationMirrors()`: các annotation ở dạng compiler model, không đòi hỏi runtime reflection.
- `asType()`: kiểu mà declaration này định nghĩa hoặc có, với ngữ nghĩa phụ thuộc loại element.

**Chú ý:** `getEnclosedElements()` có thể gồm constructors, methods, fields, inner classes, record components; không được giả định “phần tử đầu tiên luôn là field”. Nếu generator cần output xác định, **lọc theo `ElementKind` và sắp xếp** thay vì vô tình phụ thuộc thứ tự duyệt của một implementation compiler.

## 4. TypeMirror: mô hình của kiểu, không phải tên khai báo

`TypeMirror` nằm trong `javax.lang.model.type`. Nó mô tả các kiểu mà trình biên dịch đang giải quyết. API đầu tiên nên đọc là `getKind()` để xác định `TypeKind`. Một số dạng hay gặp:

| TypeKind / subtype | Ví dụ Java | Cách phân tích |
| --- | --- | --- |
| `INT`, `BOOLEAN`, ... / `PrimitiveType` | `int`, `boolean` | Primitive kinds, không phải `DeclaredType` |
| `DECLARED` / `DeclaredType` | `String`, `List<String>`, `Map<String, Integer>` | `asElement()`, `getTypeArguments()`, `getEnclosingType()` |
| `ARRAY` / `ArrayType` | `String[]`, `T[]` | `getComponentType()` |
| `TYPEVAR` / `TypeVariable` | `T` trong `class Box<T>` | `asElement()`, `getUpperBound()`, `getLowerBound()` |
| `WILDCARD` / `WildcardType` | `? extends Number`, `? super String` | `getExtendsBound()`, `getSuperBound()` |
| `EXECUTABLE` / `ExecutableType` | Kiểu của một method/constructor | `getParameterTypes()`, `getReturnType()`, `getThrownTypes()` |
| `VOID`, `NONE` / `NoType` | Kiểu trả về `void`; trường hợp không có superclass | Không coi `NONE` là `Object` |
| `NULL` / `NullType` | Kiểu null đặc biệt | Không đại diện một class Java |
| `ERROR` / `ErrorType` | Tham chiếu kiểu chưa/không giải quyết được | Xử lý cẩn trọng, nhất là giữa rounds |
| `INTERSECTION` / `IntersectionType` | Các upper bounds kết hợp | `getBounds()` |
| `UNION` / `UnionType` | Kiểu của multi-catch (`IOException | SQLException`) | `getAlternatives()` |

Các dạng phức tạp có thể nested: `List<? extends Number[]>` là một `DeclaredType` có argument `WildcardType`, với upper bound là `ArrayType`, component type là `Number`. Một processor nghiêm túc nên duyệt **cấu trúc subtype** hoặc dùng `TypeVisitor`, không regex trên chuỗi trả về của `TypeMirror.toString()`.

### Một nhầm lẫn quan trọng: ElementKind khác TypeKind

`TypeElement` cho `List` có `ElementKind.INTERFACE`, trong khi một **biểu thức kiểu** `List<String>` có `TypeKind.DECLARED`. Class, interface, enum và record đều có thể xuất hiện dưới dạng `DeclaredType` khi được dùng làm kiểu tham chiếu; không có `TypeKind.CLASS`. Vì vậy:

```java
ElementKind declarationKind = element.getKind();
TypeKind valueTypeKind = element.asType().getKind();
```

Đoạn trên chỉ là ví dụ đặt trong code processor có biến `element` sẵn. Hai dòng trả lời hai câu hỏi khác nhau, không nên đem so trực tiếp.

## 5. Types và Elements: không tự giải quyết ngữ nghĩa bằng chuỗi

Truy xuất hai utility qua `ProcessingEnvironment`:

```java
javax.lang.model.util.Elements elements =
        processingEnv.getElementUtils();
javax.lang.model.util.Types types =
        processingEnv.getTypeUtils();
```

Đây là đoạn code minh họa bên trong một processor; `processingEnv` là field được `AbstractProcessor` cung cấp sau khi khởi tạo.

### 5.1. Elements: thao tác trên khai báo

- `getTypeElement("java.util.List")`: tìm khai báo `TypeElement` theo tên đầy đủ. Có thể trả về `null` nếu compiler không tìm thấy kiểu trong môi trường này.
- `getPackageOf(element)`: xác định package của khai báo.
- `getAllMembers(typeElement)`: xem tập các thành viên của kiểu, bao gồm các thành viên thừa kế theo quy tắc API; khác `getEnclosedElements()`.
- `overrides(overrider, overridden, type)` và `hides(hider, hidden)`: kiểm tra quan hệ phương thức/ẩn tên theo ngữ nghĩa Java.
- `getBinaryName(typeElement)`: lấy tên nhị phân, có ích cho nested classes (khác source-qualified name).
- `getAllAnnotationMirrors(element)`: bao gồm cả những annotation được kế thừa theo quy tắc liên quan, khác việc chỉ đọc mirrors trực tiếp.

### 5.2. Types: thao tác trên kiểu

| API | Trả lời điều gì? |
| --- | --- |
| `isSameType(a, b)` | Hai kiểu tương đương theo mô hình type của compiler? |
| `isSubtype(a, b)` | `a` có là subtype của `b`? |
| `isAssignable(a, b)` | Giá trị kiểu `a` có thể được gán sang biến kiểu `b` theo quy tắc API? |
| `erasure(type)` | Kiểu nhận được khi áp dụng Java type erasure là gì? |
| `directSupertypes(type)` | Các supertypes trực tiếp của kiểu này là gì? |
| `asElement(type)` | Đối với một kiểu có declaration tương ứng, trả về `Element` liên quan (có thể null). |
| `asMemberOf(declaredType, member)` | Một member được nhìn nhận là **kiểu gì trong context của một declared/parameterized type cụ thể**? |
| `getDeclaredType(typeElem, args...)` | Tạo mô hình parameterized declared type từ declaration và các argument mirrors |
| `capture(type)` | Áp dụng capture conversion cho kiểu dùng wildcard |

**Không so kiểu bằng `a.toString().equals(b.toString())`** khi quyết định assignability hoặc generic compatibility. `toString()` rất hữu ích để log cho người đọc, nhưng chỉ là biểu diễn văn bản; quy tắc subtype, boxing, erasure, wildcard và generic substitutions phức tạp hơn sự giống nhau giữa hai chuỗi. Cũng không dùng `==` như hợp đồng kiểm tra hai kiểu có bằng nhau về ngữ nghĩa.

## 6. Ví dụ có thể chạy: đọc field, type variable và erasure

Ta sẽ tạo annotation `@Inspect`, dùng processor đọc class `Store<T extends Number>`, sắp xếp field theo tên, lấy cả kiểu gốc và kiểu sau erasure, rồi sinh `demo.StoreModel`. `Main` sẽ gọi method `StoreModel.summary()` để kết quả quan sát được trên stdout.

### 6.1. Cấu trúc dự án

```text
model-demo/
├── processor-src/
│   └── tool/
│       └── ModelProcessor.java
└── src/
    └── demo/
        ├── Inspect.java
        ├── Store.java
        └── Main.java
```

Dự án là Java classpath đơn giản, **không** có `module-info.java` và không dùng thư viện thứ ba. File processor nằm riêng để biên dịch trước, vì processor cần tồn tại dưới dạng class để `javac` thực thi nó.

### 6.2. src/demo/Inspect.java

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Inspect {}
```

`RetentionPolicy.SOURCE` hoàn toàn đủ vì processor chạy **trước khi** class file được hoàn thành; annotation chỉ cần xuất hiện trong nguồn của lần compile này. `@Target(TYPE)` hạn chế vị trí gắn, còn processor sẽ chủ động kiểm tra là `ElementKind.CLASS`.

### 6.3. src/demo/Store.java

```java
package demo;

import java.util.List;

@Inspect
public final class Store<T extends Number> {
    private final T id;
    private final List<String> names;

    public Store(T id, List<String> names) {
        this.id = id;
        this.names = names;
    }

    public T id() {
        return id;
    }

    public List<String> names() {
        return names;
    }
}
```

Hai field này được chọn có mục đích:

- `id` có kiểu nguồn `T`, một **type variable**, bound đầu tiên `Number`, erasure là `Number`.
- `names` có kiểu nguồn `List<String>`, một **declared parameterized type**, erasure là raw `List`.
- `id()` và `names()` là **methods**, vì vậy processor lọc `FIELD` sẽ không nhầm methods thành fields.
- Constructor là `CONSTRUCTOR`, không phải `FIELD`.

### 6.4. src/demo/Main.java

```java
package demo;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        System.out.println(StoreModel.summary());
        System.out.println(
                new Store<>(7, List.of("Ada", "Lin")).names().size());
    }
}
```

`StoreModel` chưa tồn tại trong các file source được viết bằng tay. Nó phải được sinh bởi processor. Điều này giúp xác nhận cả **giai đoạn model reading** và **giai đoạn sinh class** đã thành công.

### 6.5. processor-src/tool/ModelProcessor.java

```java
package tool;

import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.TypeMirror;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Inspect")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ModelProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (TypeElement annotation : annotations) {
            for (Element element
                    : roundEnv.getElementsAnnotatedWith(annotation)) {

                if (element.getKind() != ElementKind.CLASS) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "@Inspect requires a class",
                            element);
                    continue;
                }

                TypeElement type = (TypeElement) element;
                String pkg = processingEnv.getElementUtils()
                        .getPackageOf(type).getQualifiedName().toString();
                String simple = type.getSimpleName().toString() + "Model";
                String fullName = pkg.isEmpty() ? simple : pkg + "." + simple;

                List<VariableElement> fields = new ArrayList<>();
                for (Element member : type.getEnclosedElements()) {
                    if (member.getKind() == ElementKind.FIELD) {
                        fields.add((VariableElement) member);
                    }
                }
                fields.sort(Comparator.comparing(
                        f -> f.getSimpleName().toString()));

                List<String> tokens = new ArrayList<>();
                tokens.add("class=" + type.getQualifiedName());

                for (VariableElement field : fields) {
                    TypeMirror mirror = field.asType();
                    tokens.add(field.getSimpleName() + ":" + mirror
                            + "->" + processingEnv.getTypeUtils()
                                    .erasure(mirror));
                }

                String report = String.join("|", tokens);

                try {
                    JavaFileObject file = processingEnv.getFiler()
                            .createSourceFile(fullName, type);

                    try (Writer writer = file.openWriter()) {
                        if (!pkg.isEmpty()) {
                            writer.write("package " + pkg + ";\n");
                        }
                        writer.write(
                                "public final class " + simple + " {\n");
                        writer.write(
                                "  private " + simple + "() {}\n");
                        writer.write(
                                "  public static String summary() { return "
                                        + quote(report) + "; }\n");
                        writer.write("}\n");
                    }
                } catch (IOException ex) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Cannot generate " + fullName + ": " + ex,
                            element);
                }
            }
        }
        return true;
    }

    private static String quote(String text) {
        return "\"" + text.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                + "\"";
    }
}
```

Đây là processor hoàn chỉnh, có thể compile độc lập bằng JDK 17+. Nó **không import `demo.Inspect`** trong runtime classpath của processor: tên annotation được khai báo bằng chuỗi, và processor nhận `TypeElement` từ `annotations`. Cách này cho phép compile processor trước khi compile annotation và application.

### 6.6. Biên dịch và chạy từ thư mục model-demo

Linux/macOS, với working directory là `model-demo`:

```bash
mkdir -p build/processor build/classes build/generated
javac --release 17 -d build/processor processor-src/tool/ModelProcessor.java
javac --release 17 -processorpath build/processor -processor tool.ModelProcessor -s build/generated -d build/classes src/demo/Inspect.java src/demo/Store.java src/demo/Main.java
java -cp build/classes demo.Main
```

Trên Windows PowerShell, tạo thư mục bằng lệnh tương đương:

```powershell
New-Item -ItemType Directory -Force build/processor,build/classes,build/generated | Out-Null
javac --release 17 -d build/processor processor-src/tool/ModelProcessor.java
javac --release 17 -processorpath build/processor -processor tool.ModelProcessor -s build/generated -d build/classes src/demo/Inspect.java src/demo/Store.java src/demo/Main.java
java -cp build/classes demo.Main
```

**Stdout của `demo.Main` khi dùng OpenJDK 21 và các file trên:**

```text
class=demo.Store|id:T->java.lang.Number|names:java.util.List<java.lang.String>->java.util.List
2
```

Đã kiểm tra bằng OpenJDK 21 với `--release 17`: processor được gọi, source generated compile được, chương trình chạy ra đúng hai dòng trên. Chú ý: `TypeMirror.toString()` là biểu diễn phục vụ con người, không nên xem định dạng chuỗi của mọi TypeMirror là giao thức serialize ổn định xuyên mọi compiler. Nếu tạo file cấu hình/schema lâu dài, nên dùng cấu trúc API thay vì phụ thuộc nguyên văn `toString()`.

File được sinh:

```text
build/generated/demo/StoreModel.java
```

Nội dung trên công cụ kiểm thử:

```java
package demo;
public final class StoreModel {
  private StoreModel() {}
  public static String summary() { return "class=demo.Store|id:T->java.lang.Number|names:java.util.List<java.lang.String>->java.util.List"; }
}
```

Các file class liên quan ở `build/classes/demo/`: `Inspect.class`, `Store.class`, `Main.class` và `StoreModel.class`. `-s` chỉ nơi ghi **source được sinh**, `-d` chỉ nơi ghi **class output**, còn `-processorpath` chứa implementation của processor (khác classpath của ứng dụng).

### 6.7. Đọc từng bước trong processor

1. `roundEnv.getElementsAnnotatedWith(annotation)` trả về các elements được annotate bởi `demo.Inspect` trong round. Vì annotation được đánh dấu trên class `Store`, element là một `TypeElement`.
2. `element.getKind()` bảo đảm ta thực sự có khai báo class trước khi cast.
3. `getPackageOf(type)` xác định package, `getSimpleName()` xác định tên class để xây tên class nguồn mới.
4. `getEnclosedElements()` lấy các khai báo trực tiếp thuộc `Store`. Chỉ những member có `ElementKind.FIELD` được giữ lại.
5. `field.asType()` lấy `TypeMirror`: field `id` là `TYPEVAR`; `names` là `DECLARED`.
6. `Types.erasure(mirror)` cho `Number` với `T extends Number` và `List` với `List<String>`.
7. `Filer.createSourceFile(...)` tạo Java source và ghi originating `TypeElement`. File generated được compiler đưa vào quá trình biên dịch tiếp theo.
8. `return true` nghĩa là processor **claim** các annotation types đã được yêu cầu xử lý trong round; không phải trạng thái “mọi file đã ghi thành công”.

Ví dụ chỉ tạo một file từ một top-level class. Trong dự án thực tế, phải thiết kế naming policy tránh collision giữa nested classes, cùng simple name trong các package, và nhiều processors cùng muốn tạo một generated class.

## 7. Đọc generic types đúng cách

### 7.1. Kiểu của khai báo generic và kiểu được sử dụng không giống nhau

Giả sử có:

```java
class Box<T> {
    T value;
}
Box<String> box;
```

- `TypeElement` của `Box` nói rằng có type parameter `T`. `getTypeParameters()` trả về `TypeParameterElement`.
- `TypeElement.asType()` mô tả dạng generic của chính declaration, thường tương ứng `Box<T>`.
- Kiểu của một field/variable khai báo `Box<String>` là `DeclaredType` mang một type argument `String`. `getTypeArguments()` cho phép đọc argument đó.
- `Types.asElement(declaredType)` có thể trả về declaration `Box`, nhưng việc chỉ nhìn declaration không cho biết field được dùng với `String` hay `Integer`; phải đọc `DeclaredType.getTypeArguments()`.

Đừng nghĩ `TypeElement` có một bản riêng cho mỗi `Box<String>`. Đây là sự khác biệt giữa **declaration identity** và **applied/parameterized type**.

### 7.2. Type variable và bounds

Với `Store<T extends Number>`:

```java
for (var p : type.getTypeParameters()) {
    // p: TypeParameterElement, ví dụ tên T
    // p.getBounds(): danh sách upper bounds, ví dụ Number
}
```

Đây là **mẩu code trong processor có biến `type` kiểu `TypeElement`**, không phải chương trình độc lập. `TypeParameterElement` mô tả khai báo `T`; còn `field.asType()` của `T id` trả về `TypeVariable` (một loại `TypeMirror`). `Types.erasure(T)` theo bound đầu tiên cho `Number`; `T` không có bound tường minh sẽ có erasure `Object`.

Nếu generator chỉ in `typeMirror.toString()` mà bỏ bounds, có thể bỏ lỡ những ràng buộc giúp kiểm tra kiểu và sinh code đúng.

### 7.3. Wildcard không phải là TypeParameterElement

`List<? extends Number>` có argument là `WildcardType`, không có tên type parameter riêng. `? extends Number` là một **use-site type argument**, không giống khai báo `T extends Number`. Dùng `WildcardType.getExtendsBound()`/`getSuperBound()` khi cần đọc cấu trúc wildcard. Một visitor kiểm tra generic phải phân biệt hai dạng này.

### 7.4. Array và primitive

- `int`: `PrimitiveType` với kind `INT`.
- `String[]`: `ArrayType`, `getComponentType()` cho `String`.
- `T[]`: component type có thể là `TypeVariable`.
- `void` khi là return type của method: `NoType` với kind `VOID`, **không phải** một `TypeElement` cho class có tên “void”.

Generator thiết kế sai thường cast mọi `TypeMirror` sang `DeclaredType`; điều đó gây lỗi với primitive, array, type variable, wildcard và no-type.

## 8. Methods và constructors: ExecutableElement vs ExecutableType

Giả sử source có method:

```java
public List<String> names() {
    return names;
}
```

Trong model:

- **`ExecutableElement`** mô tả declaration phương thức `names`; `getSimpleName()` là tên, `getParameters()` chứa các `VariableElement` tham số, `getReturnType()` trả `TypeMirror` của kiểu trả về, `getThrownTypes()` liệt kê checked exceptions được khai báo.
- **`ExecutableType`** mô tả **kiểu callable** của method với parameter types, return type, thrown types, type variables. `ExecutableElement.asType()` có thể trả về `ExecutableType`.

Constructor cũng là `ExecutableElement` nhưng có `ElementKind.CONSTRUCTOR`; không nên suy diễn rằng nó giống method có tên class ở mọi phương diện. Cần dùng `getKind()` và API tương ứng.

Khi dùng annotation processor để kiểm tra method contract, nên kiểm tra:

1. `ElementKind.METHOD`.
2. `getModifiers()` và `getParameters()`.
3. `getReturnType()` và những type mirrors của tham số.
4. `Types.isAssignable` / `isSubtype` / `isSameType` khi thực sự cần quy tắc kiểu.
5. Phương thức generic: `getTypeParameters()`; một method `<T> T identity(T t)` có type variable **riêng của method**, không tự động là type variable của enclosing class.

`ExecutableElement.getReturnType()` trả kiểu theo declaration mà element biểu diễn. Khi method được kế thừa từ generic base và nhìn qua một subtype cụ thể, đôi khi phải dùng `Types.asMemberOf(...)` để lấy **kiểu đã thay tham số generic theo context của subtype**.

## 9. Vì sao asMemberOf quan trọng với kế thừa generic?

Xét đoạn Java **minh họa** sau:

```java
class Base<T> {
    T get() {
        return null;
    }
}

class StringBox extends Base<String> {
}
```

Ở declaration `Base<T>`, kiểu trả về của method `get()` là `T`. Nhưng khi method đó được nhìn như thành viên của `StringBox`, kiểu return hợp lý là `String`.

Một processor có thể dùng:

```java
DeclaredType containing = (DeclaredType) stringBoxType.asType();
TypeMirror memberType = types.asMemberOf(containing, getMethodElement);
ExecutableType adapted = (ExecutableType) memberType;
TypeMirror returnType = adapted.getReturnType();
```

Đây là **mẩu code bên trong processor**, giả định đã có:

- `stringBoxType` là `TypeElement` của `StringBox`;
- `getMethodElement` là `ExecutableElement` khai báo method `Base.get()`;
- `types` là `processingEnv.getTypeUtils()`.

Với `asMemberOf`, processor yêu cầu compiler thực hiện generic substitution khi member được nhìn trong containing declared type; kết quả return type biểu diễn `String`. Nếu chỉ gọi `getMethodElement.getReturnType()` trên declaration ở `Base<T>`, bạn có thể nhận kiểu `T` và sinh sai API cho `StringBox`.

**Không áp dụng `asMemberOf` cho một member không hợp lệ trong containing type.** Tài liệu API cho phép báo `IllegalArgumentException` nếu phần tử không phải member phù hợp. Cần xác định đúng context, không thử ép một method bất kỳ vào class không liên quan.

## 10. Đọc annotation bằng mô hình, không bắt buộc load annotation class

Một processor có thể đọc:

```java
for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
    TypeMirror annotationType = mirror.getAnnotationType();
    // Đọc annotation type và các giá trị phần tử qua AnnotationMirror
}
```

Đây là mẩu code với `element` là `Element` đã tìm được. `AnnotationMirror` và `AnnotationValue` cho phép xem annotation declaration và values trong môi trường compile. `Elements.getElementValuesWithDefaults(mirror)` giúp lấy cả giá trị mặc định nếu code generator cần một cấu hình hoàn chỉnh.

Dùng `element.getAnnotation(MyAnnotation.class)` cũng có chỗ phù hợp, đặc biệt khi processor có annotation API trên processor classpath. Nhưng nó tạo sự phụ thuộc vào runtime `Class` của annotation mà compiler có thể chưa load được theo cách người viết tưởng tượng. Với processor tổng quát, dùng `AnnotationMirror`, `TypeElement`, `TypeMirror` thường an toàn và linh hoạt hơn.

`@Retention(SOURCE)` **không ngăn** processor đọc annotation trên source; nó chỉ quy định retention sau compilation. Đừng đổi annotation thành `RUNTIME` chỉ để processor “thấy” nó.

## 11. Mô hình là semantic model, không phải AST toàn bộ

Language Model API cung cấp khai báo và kiểu đã được compiler diễn giải. Nó **không** mặc định cho biết từng phép cộng, literal, điều kiện if/else hay chính xác các ký tự source trong method body.

Cần phân biệt:

- **Language model (`javax.lang.model.*`):** declaration/type semantics; rất phù hợp để làm API generator, schema checker, DI metadata, mapper validation.
- **Tree API (`com.sun.source.tree`, `com.sun.source.util.Trees`) của JDK compiler:** truy cập cây cú pháp ở mức statement/expression khi công cụ và môi trường hỗ trợ. Đây là API khác, không đồng nghĩa mỗi `TypeMirror` có AST con.
- **Runtime reflection:** quan sát các classes đã load, không thể thay cho compile-time model khi source chưa thành class.
- **Compiler internal AST (`com.sun.tools.javac.*`):** các chi tiết triển khai nội bộ không phải hợp đồng chuẩn `javax.lang.model`; phụ thuộc chặt vào bản `javac`.

Nếu mục tiêu chỉ là “tạo mapper dựa vào fields, methods, modifiers và generic types”, ưu tiên `Element`/`TypeMirror`. Nếu cần phân tích body của method, chuyển sang công cụ AST phù hợp thay vì cố parse kết quả `Element.toString()`.

## 12. ErrorType, incomplete code và nhiều processing rounds

Source đang compile có thể tham chiếu một kiểu **chưa được giải quyết** vì một processor khác sẽ sinh ra nó ở round tiếp theo. Trong tình huống này, compiler có thể biểu diễn một phần kiểu bằng `ErrorType`. Điều đó cần cách xử lý có suy xét:

- Không cast `ErrorType` mù quáng sang class Java hoặc giả sử kiểu đã tồn tại ở runtime.
- Khi không thể xác thực một mối quan hệ kiểu, có thể phát diagnostic liên quan hoặc trì hoãn việc xử lý sang một round sau theo hợp đồng cụ thể của processor.
- Không “chạy vòng chờ” hoặc liên tục phát cùng một file để ép compiler resolve lại: có thể gặp `FilerException` hoặc vòng xử lý không ổn định.
- Đừng cache các model objects qua **nhiều compilation runs** hoặc build invocations như thể chúng là metadata bất biến. Model objects thuộc môi trường compilation và có thể thay đổi về khả năng resolve qua rounds.
- Trong `roundEnv.processingOver() == true`, không tạo Java source mới với kỳ vọng compiler sẽ tiếp tục mở round mới cho nó.

Theo `Processor` API, khi một processor đã được gọi trong một round, nó sẽ còn được gọi trong các round sau, bao gồm round cuối. `RoundEnvironment.errorRaised()` báo lỗi trong round trước; không đồng nghĩa mọi typed lookup lúc này đều đã ổn định.

Nếu processor dùng nhiều annotation types, `process(Set<? extends TypeElement> annotations, ...)` có thể nhận một **subset** những types nó hỗ trợ ở round. Không dùng giả định “mỗi lần process luôn có đúng một annotation type”; ví dụ của bài chạy trên một annotation để giữ sự tập trung.

## 13. Chẩn đoán lỗi đúng với Messager và Originating Elements

### 13.1. Gắn lỗi vào Element

Khi gặp một declaration không hợp lệ:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Unsupported declaration for @Inspect",
        element);
```

Đoạn này thuộc method `process` có `element` trong phạm vi. Compiler/IDE có thể gắn diagnostic vào vị trí của declaration; tốt hơn việc `System.out.println` một dòng không liên hệ với source.

`Diagnostic.Kind.WARNING` phù hợp vấn đề không khiến build phải dừng; `ERROR` phù hợp điều kiện phải sửa trước khi codegen đáng tin. Không nên nuốt lỗi cấu hình rồi tạo lớp rỗng như thể thành công.

### 13.2. Filer có ranh giới quyền sở hữu file

`Filer.createSourceFile(qualifiedName, originatingElements...)` tạo **source mới**. Phải tránh tạo lại cùng tên trong một compilation run, tránh đụng file source hiện có và tránh xung đột khi nhiều processors cùng sinh một tên. `FilerException` là một dạng `IOException` thường gặp cho tình huống vi phạm này.

Originating elements cho build tool manh mối về **đầu vào khiến output được sinh**. Chúng hỗ trợ cơ chế incremental annotation processing, nhưng không tự chứng minh mọi processor chạy incremental chính xác. Ngoài ra processor có thể cần phân biệt output “isolating” và “aggregating” tùy hợp đồng riêng của build system.

Khi dùng values từ annotation để sinh Java literal, phải escape chuỗi và validate tên. `TypeMirror.toString()` không phải API đảm bảo sinh được mã nguồn tương ứng mọi trường hợp; với generator quan trọng, hãy xây cấu trúc source từ model và dùng logic in type name đúng từng `TypeKind` hoặc một thư viện generation đáng tin.

## 14. Khi nào dùng visitor thay vì if/instanceof?

Với processor đơn giản, nhánh theo `getKind()` đủ rõ. Nhưng khi cần hỗ trợ nhiều loại `TypeMirror` — nested arrays, wildcard, intersection, executable, generics — cấu trúc visitor ít bỏ sót hơn:

```java
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.SimpleTypeVisitor14;

class TypeKinds extends SimpleTypeVisitor14<String, Void> {
    @Override
    protected String defaultAction(TypeMirror type, Void unused) {
        return type.getKind().name();
    }
}
```

**Đây là minh họa lớp Java riêng**, không phải toàn bộ processor. `SimpleTypeVisitor14` có trong Java 17 và xử lý các type shapes theo visitor framework. Nếu cần chủ động xử lý từng kind, override thêm `visitDeclared`, `visitArray`, `visitTypeVariable`, `visitWildcard`, `visitExecutable`, ... và tái đệ quy tới component/type arguments. Chọn version visitor phù hợp các loại type và compiler mà dự án phải hỗ trợ.

Tương tự, `ElementVisitor` / `SimpleElementVisitor...` giúp phân tích `TypeElement`, `VariableElement`, `ExecutableElement` một cách có cấu trúc. Một lợi ích lớn là khi Java bổ sung khai báo mới (ví dụ record components), lỗi/nhánh mặc định có thể được nhận ra thay vì silent-ignoring.

## 15. Dùng javac và test để kiểm chứng processor

Sau khi tạo các file như mục 6, có thể bật log rounds:

```bash
javac --release 17 -XprintRounds -XprintProcessorInfo -processorpath build/processor -processor tool.ModelProcessor -s build/generated -d build/classes src/demo/Inspect.java src/demo/Store.java src/demo/Main.java
```

Log giúp thấy processor có được gọi và có tạo round tiếp hay không. Không nên coi nguyên văn các dòng `-XprintRounds` là output bất biến giữa phiên bản compiler; hãy kiểm tra **file generated, diagnostics và hành vi chạy**.

### Negative test: tắt processor

Trong output sạch riêng, thử:

```bash
javac --release 17 -proc:none -d build/no-processor src/demo/Inspect.java src/demo/Store.java src/demo/Main.java
```

Không có `StoreModel.java` tự viết, nên nếu classpath không chứa một `demo.StoreModel` cũ, compile phải **thất bại** tại `Main` vì không resolve được `StoreModel`. Điều này chứng minh chương trình thật sự phụ thuộc vào generated code. **Đừng dùng thư mục output có class file cũ** vì nó có thể che giấu vấn đề.

### Kiểm tra tác dụng của erasure

Source `id` có type variable `T extends Number`, sau erasure là `Number`. Có thể xem class file:

```bash
javap -p -s -classpath build/classes demo.Store
```

`javap -s` sẽ thể hiện descriptor cho field `id` như `Ljava/lang/Number;`, trong khi processor đã đọc type mirror `T` trong compilation. Đây là hai góc nhìn phù hợp nhưng khác nhau: **compile-time generic type** và **binary field descriptor**.

### Kiểm tra đời sống toolchain

Lệnh `-processor` được chỉ định tường minh để tránh phụ thuộc cơ chế tự phát hiện processor khác nhau theo bản JDK. Từ JDK 23, mặc định annotation processing không còn tự chạy chỉ vì một processor tình cờ xuất hiện trên classpath; nên cấu hình processor path và chế độ processing rõ ràng trong build tool/CI.

## 16. Những lỗi phổ biến khi đọc mô hình

| Ngộ nhận hoặc lỗi | Nguyên nhân | Cách đúng |
| --- | --- | --- |
| `Class.forName("demo.Store")` trong processor | Class đang compile có thể chưa tồn tại trên processor runtime classpath | `Elements.getTypeElement("demo.Store")` |
| Coi `Element` chính là `TypeMirror` | Khai báo và kiểu là hai khái niệm khác | `Element.asType()` và kiểm tra `TypeKind` |
| Cast mọi `Element` sang `TypeElement` | Field, method, parameter có các subtype khác | Kiểm tra `getKind()` trước khi cast |
| Cast mọi `TypeMirror` sang `DeclaredType` | Primitive/array/typevar/wildcard không phải declared type | Dùng `getKind()` hoặc `TypeVisitor` |
| So `TypeMirror` bằng tên string | Không xét generic substitution, wildcard và assignability | Dùng `Types.isSameType` / `isAssignable` / `asMemberOf` |
| Dùng `getEnclosedElements()` để lấy thành viên thừa kế | API chỉ lấy declarations trực tiếp | Xem `Elements.getAllMembers()` |
| Đọc kiểu return của generic parent mà không thay `T` | Đang nhìn declaration thay vì subtype context | Dùng `Types.asMemberOf(...)` |
| Coi `TypeElement` của `List` như `List<String>` | Declaration khác applied parameterized type | Đọc `DeclaredType.getTypeArguments()` |
| Cho rằng `ErrorType` luôn là lỗi vĩnh viễn | Kiểu có thể được generated ở round tiếp | Kiểm tra rounds và policy hoãn/diagnostic |
| Processor làm việc bằng reflection | Trộn runtime model với compile-time model | Dùng `javax.lang.model` |
| Mã generated mỗi lần khác thứ tự | Dựa vào iteration order/mtime/HashMap | Sort và giữ output deterministic |
| Cố tạo cùng class hai lần | Xung đột `Filer` / nhiều rounds | Theo dõi naming/output ownership, chỉ tạo một lần |
| Processor đọc annotation SOURCE từ file `.class` | Annotation không được giữ ở runtime binary như đã nghĩ | Cung cấp source và xử lý đúng compile round |
| Dùng AST nội bộ thay mô hình chuẩn cho mọi vấn đề | Phụ thuộc chi tiết compiler và JDK build | Ưu tiên `Element`/`TypeMirror` nếu đủ |
| Chạy trên JDK khác mà `SourceVersion` không phù hợp | Khai báo phiên bản nguồn processor thấp/cao hơn compilation | Chọn source-version policy phù hợp và kiểm tra `javac --release` |

## 17. Bài tập tự kiểm tra

**Câu 1.** Với source `class Box<T extends Number> { T x; }`, `x` là loại `Element` nào? Kiểu của `x` là loại `TypeMirror` nào?

**Đáp án:** `x` là `VariableElement` với `ElementKind.FIELD`. `x.asType()` là `TypeVariable` với `TypeKind.TYPEVAR`; `Types.erasure(...)` cho `Number`.

**Câu 2.** Vì sao không thể lấy type arguments của field `List<String> names` chỉ bằng `Types.asElement(names.asType())`?

**Đáp án:** `asElement(...)` trả declaration của `List`, không mang thông tin type argument của use site như một `TypeElement` riêng. Cần cast `names.asType()` thành `DeclaredType` sau khi kiểm tra kind rồi đọc `getTypeArguments()`.

**Câu 3.** `getEnclosedElements()` có tự liệt kê method được kế thừa từ superclass không?

**Đáp án:** Không; nó liệt kê trực tiếp những declarations bên trong element. `Elements.getAllMembers(type)` là công cụ liên quan khi cần tập members gồm inherited ones, sau đó dùng `asMemberOf` để thích nghi kiểu theo context khi phù hợp.

**Câu 4.** Một method trong `Base<T>` trả `T`, nhưng subclass là `Derived extends Base<String>`. Muốn lấy kiểu trả về khi nhìn từ `Derived`, dùng API gì?

**Đáp án:** `Types.asMemberOf((DeclaredType) derived.asType(), baseMethodElement)`, sau đó đọc return type từ `ExecutableType`. Không chỉ dùng `baseMethodElement.getReturnType()` trong context của `Base<T>`.

**Câu 5.** `String[]` và `List<String>` có chung `TypeKind.DECLARED` không?

**Đáp án:** Không. `String[]` có `TypeKind.ARRAY`; `List<String>` có `TypeKind.DECLARED`.

**Câu 6.** Processor có thể đọc một annotation `@Retention(SOURCE)` trên class đang compile không?

**Đáp án:** Có. Annotation SOURCE tồn tại trong source model và có thể được annotation processor xử lý. Nó không cần có runtime retention.

**Câu 7.** Sau round đầu, một type chưa resolve được biểu diễn `ErrorType`. Processor nên gọi `Class.forName(...)` để buộc nó xuất hiện không?

**Đáp án:** Không. Runtime reflection không tạo class đang compile. Xử lý theo rounds, kiểm soát generated source và đưa ra diagnostic hoặc hoãn xử lý hợp lý.

**Câu 8.** Hai lần build thấy thứ tự fields khác nhau. Sửa generator thế nào?

**Đáp án:** Lọc đúng `FIELD`, áp dụng sort theo tên hoặc tiêu chí nghiệp vụ ổn định trước khi sinh output; không phụ thuộc collection iteration order tình cờ.

**Câu 9.** Khi nào `Messager` phù hợp hơn `Filer`?

**Đáp án:** Khi mục tiêu chỉ là báo điều kiện không hợp lệ/warning ở compile time, không cần artifact mới. `Filer` dành cho việc sinh source/class/resource.

**Câu 10.** Mã generator muốn sửa trực tiếp thân một method đang compile. `TypeMirror` có cung cấp cây statement để sửa không?

**Đáp án:** Không. `TypeMirror` mô tả kiểu, không phải AST method body. Standard JSR 269 tập trung vào mô hình khai báo/kiểu và file generation; tác vụ AST rewriting cần cơ chế chuyên dụng phù hợp.

## 18. Tài liệu tham khảo chính thức

- **Java SE 21 `Element` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/element/Element.html — declaration, `getKind`, `asType`, `getEnclosedElements`.
- **Java SE 21 `TypeElement` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/element/TypeElement.html — class/interface declarations, type parameters, interfaces và superclass.
- **Java SE 21 `TypeMirror` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html — interface gốc cho compile-time types.
- **Java SE 21 `Types` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/util/Types.html — `isAssignable`, `erasure`, `asMemberOf`, `getDeclaredType`.
- **Java SE 21 `Elements` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/util/Elements.html — query declarations, package, members, annotation mirrors.
- **Java SE 21 `RoundEnvironment` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html — round elements và trạng thái processing.
- **Java SE 21 `Processor` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html — lifecycle và semantics của `process`.
- **Oracle JDK 21 `javac`:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — `-processor`, `-processorpath`, `-s`, `-XprintRounds`.

**Kết luận:** khi xây dựng annotation processor, hãy nhìn **`Element` như khai báo** và **`TypeMirror` như kiểu Java mà compiler đã giải quyết**. Hãy dùng `Elements`/`Types` để làm việc theo ngữ nghĩa của ngôn ngữ — đặc biệt với generics và inheritance — rồi chỉ dùng `Filer` để sinh artifact mới và `Messager` để phản hồi lỗi. Mô hình này giúp processor đáng tin, có thể kiểm thử và ít phụ thuộc chi tiết triển khai của một bản `javac` cụ thể.