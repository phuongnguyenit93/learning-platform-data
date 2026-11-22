# Visitor và cách duyệt mô hình ngôn ngữ có cấu trúc trong Java Annotation Processing

Khi viết annotation processor, việc đọc vài class có annotation bằng `RoundEnvironment.getElementsAnnotatedWith(...)` chỉ là bước đầu. Một class còn có field, method, constructor, tham số, kiểu lồng nhau, tham số generic; mỗi kiểu lại có cấu trúc khác nhau: `List<String>`, `Map<K,V>`, mảng, wildcard `? extends Number`, v.v. Muốn phân tích chính xác, ta cần **duyệt mô hình ngôn ngữ có cấu trúc** thay vì biến mọi thứ thành chuỗi rồi tách bằng `split`.

Java cung cấp Visitor API trong module `java.compiler`, đặc biệt thuộc các package:

- `javax.lang.model.element`: các **phần tử khai báo** (*elements*) như class, method, field, package.
- `javax.lang.model.type`: các **kiểu** (*types*) như `DeclaredType`, `ArrayType`, `WildcardType`, `TypeVariable`.
- `javax.lang.model.util`: các visitor và tiện ích như `ElementScanner14`, `SimpleElementVisitor14`, `SimpleTypeVisitor14`, `ElementFilter`, `Elements`, `Types`.

Trong một processor, **`ElementVisitor` giải quyết loại phần tử khai báo**, còn **`TypeVisitor` giải quyết loại cấu trúc kiểu**. Hai hệ visitor liên quan nhưng không thay thế nhau.

## 1. Hai cây khác nhau: `Element` và `TypeMirror`

Ví dụ đầu vào Java:

```java
@InspectMe
class Customer {
    String name;
    java.util.List<? extends Number> scores;

    int count() {
        return scores.size();
    }
}
```

Có thể nhìn từ hai góc độ.

**Cây khai báo** (các `Element`):

```text
TypeElement Customer
├─ VariableElement name       (FIELD)
├─ VariableElement scores     (FIELD)
└─ ExecutableElement count    (METHOD)
```

Cấu trúc compiler thực tế có thể còn constructor, type parameter và các phần tử được ngôn ngữ/compiler bổ sung. Sơ đồ trên **chỉ minh họa các khai báo viết tay quan trọng**, không phải khẳng định `getEnclosedElements()` sẽ trả đúng ba nút.

**Cây cấu trúc kiểu** của field `scores` (các `TypeMirror`):

```text
DeclaredType List<? extends Number>
└─ WildcardType ? extends Number
   └─ DeclaredType Number
```

Điểm khác nhau:

| Câu hỏi | Mô hình phù hợp |
| --- | --- |
| Class có những field nào? | `TypeElement.getEnclosedElements()` và `ElementVisitor`. |
| Một phần tử là field hay tham số method? | `Element.getKind()` hoặc `visitVariable(...)` của visitor. |
| Method trả về kiểu gì? | `ExecutableElement.getReturnType()` nhận `TypeMirror`. |
| Đối số số 0 của `List<? extends Number>` là gì? | `DeclaredType.getTypeArguments()` rồi `TypeVisitor`. |
| Bound của `? extends Number` là kiểu nào? | `WildcardType.getExtendsBound()`. |
| Trên khai báo có annotation gì? | `Element.getAnnotationMirrors()`. |
| Trên vị trí sử dụng kiểu có type annotation gì? | `TypeMirror.getAnnotationMirrors()` ở nút tương ứng. |

**Không nhầm với Java Reflection.** Các API `javax.lang.model.*` mô hình hóa chương trình **khi biên dịch**; chúng không yêu cầu tải và chạy các class đầu vào. `java.lang.reflect.*` lại dùng cho metadata của những class được nạp ở runtime. Hai thế giới khác nhau dù có nhiều thuật ngữ giống nhau.

## 2. Visitor pattern: gọi đúng phương thức theo kiểu nút

`Element` có phương thức:

```java
<R, P> R accept(ElementVisitor<R, P> visitor, P parameter);
```

Tương tự, `TypeMirror` có:

```java
<R, P> R accept(TypeVisitor<R, P> visitor, P parameter);
```

Khi gọi `element.accept(visitor, context)`, mô hình ngôn ngữ sẽ điều phối sang phương thức phù hợp của visitor, chẳng hạn:

- `visitType(TypeElement, P)` cho khai báo class/interface/enum/record.
- `visitExecutable(ExecutableElement, P)` cho method/constructor.
- `visitVariable(VariableElement, P)` cho field, parameter hoặc enum constant.
- `visitTypeParameter(TypeParameterElement, P)` cho tham số generic.
- `visitDeclared(DeclaredType, P)` cho kiểu được khai báo.
- `visitArray(ArrayType, P)` cho kiểu mảng.
- `visitWildcard(WildcardType, P)` cho wildcard.

Hai nhóm tên `visit...` ở trên nằm trong **hai visitor interface khác nhau**. Nếu tự viết một loạt phép `instanceof`, code dễ dài và khó mở rộng. Visitor tận dụng cơ chế dispatch do `Element`/`TypeMirror` cung cấp; tuy nhiên, visitor **không tự quyết định mọi cạnh cần duyệt**.

Các tham số generic thường dùng:

- `R`: kiểu **kết quả** mà thao tác visit trả về. Nếu chỉ in hoặc thu thập vào cấu trúc bên ngoài, dùng `Void`.
- `P`: kiểu **ngữ cảnh bổ sung** truyền theo đường duyệt. Ví dụ dùng `String` chứa đường đi `"scores.arg0.extends"`, một đối tượng `Context`, hoặc `Void` nếu không cần.

Chẳng hạn `SimpleTypeVisitor14<Void, String>` có `R=Void`, `P=String`. Đây là mô hình dispatch có kiểu tĩnh rõ ràng, không phải Reflection vào class implementation nội bộ.

## 3. Ba nhóm hỗ trợ chính cho `ElementVisitor`

### `AbstractElementVisitor...`

`AbstractElementVisitor9` và các lớp cùng họ giúp tạo visitor bằng cách buộc bạn quyết định xử lý những loại phần tử được hỗ trợ. Nó có ích khi cần kiểm soát chặt, nhưng có thể phải override nhiều phương thức tùy mức version và cấu trúc cần hỗ trợ.

### `SimpleElementVisitor...`

`SimpleElementVisitor14<R, P>` cung cấp hành vi mặc định cho các loại phần tử: nếu không override phương thức riêng thì logic đi qua `defaultAction(...)`. Ví dụ dùng để **phân loại một nút** mà không cần tự động quét các phần tử con.

```java
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.SimpleElementVisitor14;

class NameVisitor extends SimpleElementVisitor14<String, Void> {
    @Override
    public String visitType(TypeElement type, Void ignored) {
        return type.getQualifiedName().toString();
    }

    @Override
    protected String defaultAction(Element element, Void ignored) {
        return element.getSimpleName().toString();
    }
}
```

Đây là **đoạn minh họa class hỗ trợ**, không có `main`. Nó diễn giải một `TypeElement` thành tên đủ và phần tử khác thành tên ngắn. `SimpleElementVisitor14` **không phải bộ duyệt sâu tự động**; muốn duyệt con, code gọi thêm API phù hợp.

### `ElementScanner...`

`ElementScanner14<R, P>` được thiết kế cho **đi qua các phần tử con** với một số chiến lược mặc định. Chẳng hạn `visitType` quét các phần tử được chứa trong kiểu; `visitExecutable` quét các parameter của executable. Khi override, có thể gọi `super.visitType(...)` để giữ hành vi đi xuống.

```java
@Override
public Void visitType(TypeElement type, Void ignored) {
    System.out.println("type=" + type.getSimpleName());
    return super.visitType(type, ignored); // Tiếp tục đến phần tử con.
}
```

Nếu **không** gọi `super.visitType(...)` hoặc không tự gọi `scan(...)`, phần traversal con do phương thức `visitType` của scanner cung cấp sẽ không diễn ra. Đây là lỗi rất thường gặp khi người viết chỉ quan tâm logic ở nút cha.

Tại JDK 17, nhóm visitor có các bản theo phiên bản source: ví dụ `ElementScanner9` phù hợp các cấu trúc tới Java 9, còn `ElementScanner14` có xử lý thành phần `record` xuất hiện sau đó. Khi viết processor cần hỗ trợ record Java 17, nên dùng phiên bản visitor có phương thức tương ứng thay vì trông chờ một visitor đời cũ tự hiểu mọi `ElementKind` mới.

## 4. Bắt đầu từ `RoundEnvironment` và các root

Trong một annotation processor, `process` nhận đầu vào:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        return true;
    }

    for (TypeElement annotationType : annotations) {
        for (Element target :
                roundEnv.getElementsAnnotatedWith(annotationType)) {
            new MyScanner().scan(target);
        }
    }
    return true;
}
```

Đây là **snippet cần đặt trong processor** với `MyScanner` do bạn tự định nghĩa. `roundEnv.getElementsAnnotatedWith(annotationType)` tìm những phần tử mang annotation được xử lý ở **vòng hiện tại**. `roundEnv.getRootElements()` là tập điểm vào khác khi muốn duyệt các root của round, không giới hạn theo một annotation cụ thể.

Một số chi tiết cần hiểu đúng:

1. Tập `annotations` chứa **các loại annotation được giao cho processor ở vòng này**, không phải collection annotation object runtime.
2. `getRootElements()` phản ánh **round hiện tại**, không mặc định là mọi class của project ở mọi round.
3. Một processor có thể được gọi nhiều round khi các processor tạo thêm source/class. Không nên giả định `process` chỉ gọi một lần.
4. `ElementScanner` duyệt từ **nút được đưa vào `scan`**, không tự tìm tất cả dependency và superclass của project.
5. Nếu dùng `return true`, processor claim các annotation types nhận được; `true` không có nghĩa biên dịch thành công.

Muốn lấy metadata từ root type: dùng `TypeElement` và các element con, chứ không cần `Class.forName(...)` để tải class đang biên dịch. Class nguồn thậm chí có thể chưa có bytecode để load.

## 5. Duyệt có cấu trúc với `ElementScanner14`

Một bộ duyệt khai báo có thể làm những việc sau:

```java
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.util.ElementScanner14;

final class FieldScanner extends ElementScanner14<Void, Void> {
    @Override
    public Void visitType(TypeElement type, Void ignored) {
        System.out.println("type=" + type.getSimpleName());
        return super.visitType(type, ignored);
    }

    @Override
    public Void visitVariable(VariableElement variable, Void ignored) {
        if (variable.getKind() == ElementKind.FIELD) {
            System.out.println("field=" + variable.getSimpleName());
        }
        return super.visitVariable(variable, ignored);
    }
}
```

Đây là một **class hỗ trợ minh họa**, không có `main`. Tại sao kiểm tra `ElementKind.FIELD` trong `visitVariable`? Vì cùng loại `VariableElement` còn đại diện cho **method parameter, constructor parameter, enum constant và nhiều kind biến khác**. Việc được dispatch vào `visitVariable` **không tự chứng minh phần tử đó là field**.

Khi quét class, `super.visitType(...)` làm scanner tiếp tục đi xuống các khai báo được chứa. `super.visitVariable(...)` giữ cơ chế mặc định ở nút biến. Nếu chỉ cần các field **trực tiếp** của một class, không cần scanner đệ quy:

```java
java.util.List<VariableElement> directFields =
        javax.lang.model.util.ElementFilter.fieldsIn(
                type.getEnclosedElements()
        );
```

Cách dùng `ElementFilter` đơn giản, không ghé thăm type lồng nhau. Khi cần khảo sát cả cây class lồng nhau hoặc xử lý khác nhau theo loại element, scanner rõ ràng hơn. Nếu cần member **kế thừa**, phải cân nhắc `Elements.getAllMembers(type)` và ngữ nghĩa kế thừa; `getEnclosedElements()` tự nó không duyệt superclass.

## 6. `TypeVisitor`: duyệt cấu trúc kiểu mà không parse chuỗi

Từ một field `VariableElement`:

```java
TypeMirror type = variable.asType();
```

`TypeMirror` biểu diễn **kiểu** của phần tử, khác `Element` biểu diễn **khai báo**. Dù `variable.asType().toString()` có thể in `"java.util.List<? extends java.lang.Number>"`, chuỗi này **không phải API parse ổn định** cho phân tích kiểu.

Những nhánh thường phải xử lý:

| `TypeMirror` con | Phương thức lấy phần cấu trúc |
| --- | --- |
| `DeclaredType` | `getTypeArguments()`, `asElement()`, `getEnclosingType()` |
| `ArrayType` | `getComponentType()` |
| `WildcardType` | `getExtendsBound()`, `getSuperBound()`; có thể `null` |
| `TypeVariable` | `getUpperBound()`, `getLowerBound()`, `asElement()` |
| `IntersectionType` | `getBounds()` |
| `UnionType` | `getAlternatives()` |
| `ExecutableType` | `getReturnType()`, `getParameterTypes()`, `getThrownTypes()`, `getTypeVariables()` |
| `PrimitiveType` | Dựa vào `getKind()` nếu cần phân biệt `INT`, `BOOLEAN`, v.v. |

Một kiểu generic lồng nhau như `Map<String, List<? extends Number>>` cần duyệt qua `DeclaredType` của `Map`, argument thứ hai `List`, wildcard và upper bound `Number`. **Chỉ lấy `asElement()` của `Map` không cho biết các đối số `String` hay `List<? extends Number>`**.

Với `SimpleTypeVisitor14<R, P>`, có thể override những nhánh cần thiết, ví dụ:

```java
@Override
public Void visitDeclared(DeclaredType type, String path) {
    for (int i = 0; i < type.getTypeArguments().size(); i++) {
        type.getTypeArguments().get(i)
            .accept(this, path + ".arg" + i);
    }
    return null;
}
```

`SimpleTypeVisitor14` xử lý dispatch theo kind, nhưng **không tự động duyệt toàn bộ đối số generic**: đó là quyết định của method bạn override. Vậy **ElementScanner** có sẵn bước quét con của mô hình element trong một số `visit...`; còn **SimpleTypeVisitor** chủ yếu cung cấp hành vi mặc định theo loại, việc đi vào `TypeMirror` con cần code chủ động.

## 7. Ví dụ đầy đủ Java 17: scanner của element kết hợp visitor của type

Ví dụ sau đọc class được đánh dấu `@InspectMe`, in tên class, các field và **cây kiểu** của từng field. Tất cả sử dụng API chuẩn JDK, không cần thư viện ngoài.

Ta chuẩn bị **ba file nguồn** trong cùng thư mục.

### File `InspectMe.java`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface InspectMe {
}
```

`SOURCE` thích hợp: processor quan sát annotation trong quá trình biên dịch, không cần reflection runtime.

### File `ModelWalkerProcessor.java`

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
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.type.WildcardType;
import javax.lang.model.util.ElementScanner14;
import javax.lang.model.util.SimpleTypeVisitor14;

@SupportedAnnotationTypes("InspectMe")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ModelWalkerProcessor extends AbstractProcessor {

    private static final class PrintType extends SimpleTypeVisitor14<Void, String> {
        @Override
        public Void visitDeclared(DeclaredType type, String path) {
            System.out.println(
                    path + ".declared=" + type.asElement().getSimpleName());

            for (int i = 0; i < type.getTypeArguments().size(); i++) {
                TypeMirror argument = type.getTypeArguments().get(i);
                argument.accept(this, path + ".arg" + i);
            }
            return null;
        }

        @Override
        public Void visitWildcard(WildcardType type, String path) {
            System.out.println(path + ".wildcard");

            TypeMirror upper = type.getExtendsBound();
            TypeMirror lower = type.getSuperBound();

            if (upper != null) {
                upper.accept(this, path + ".extends");
            }
            if (lower != null) {
                lower.accept(this, path + ".super");
            }
            return null;
        }
    }

    private static final class PrintElements extends ElementScanner14<Void, Void> {
        private final PrintType types = new PrintType();

        @Override
        public Void visitType(TypeElement type, Void unused) {
            System.out.println("type=" + type.getSimpleName());
            return super.visitType(type, unused);
        }

        @Override
        public Void visitVariable(VariableElement variable, Void unused) {
            if (variable.getKind() == ElementKind.FIELD) {
                String path = variable.getSimpleName().toString();
                System.out.println("field=" + path);
                variable.asType().accept(types, path);
            }
            return super.visitVariable(variable, unused);
        }
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }

        for (TypeElement annotationType : annotations) {
            for (Element element :
                    roundEnv.getElementsAnnotatedWith(annotationType)) {
                if (element instanceof TypeElement type) {
                    new PrintElements().scan(type);
                }
            }
        }
        return true;
    }
}
```

Các phương thức có vai trò khác nhau:

- `process` chỉ chọn các phần tử được gắn `@InspectMe`.
- `PrintElements.scan(type)` mở đầu việc quét cây khai báo, nhờ `ElementScanner14`.
- `visitType` in tên class, sau đó gọi `super.visitType` để quét tiếp các thành viên.
- `visitVariable` chỉ xử lý `FIELD`, không nhầm parameter hay enum constant.
- `variable.asType().accept(types, path)` chuyển từ **element** sang **type model**.
- `PrintType.visitDeclared` in tên kiểu được khai báo rồi đi xuống **các đối số generic**.
- `PrintType.visitWildcard` in dấu hiệu wildcard và đi tiếp vào các giới hạn nếu có.

Đây là một processor **chỉ đọc**, không tạo source, không gọi ứng dụng, không dùng runtime Reflection để phân tích class đầu vào.

### File `Customer.java`

```java
@InspectMe
public class Customer {
    String name;
    java.util.List<? extends Number> scores;
}
```

### Lệnh biên dịch/chạy processor

Mở terminal tại thư mục có ba file. Trước hết biên dịch annotation type và processor, để `javac` có thể nạp processor đã tồn tại:

```bash
javac -encoding UTF-8 InspectMe.java ModelWalkerProcessor.java
```

Sau đó gọi processor tường minh:

```bash
javac -encoding UTF-8 -cp . -processorpath . \
    -processor ModelWalkerProcessor -proc:only Customer.java
```

Trong `bash`, ký tự `\` nối tiếp dòng lệnh. Nếu dùng PowerShell/cmd, đặt lệnh trên **một dòng**:

```powershell
javac -encoding UTF-8 -cp . -processorpath . -processor ModelWalkerProcessor -proc:only Customer.java
```

**Các dòng chuẩn do processor in ra `stdout`:**

```text
type=Customer
field=name
name.declared=String
field=scores
scores.declared=List
scores.arg0.wildcard
scores.arg0.extends.declared=Number
```

Phân tích:

1. `Customer` được đánh dấu `@InspectMe`, nên có trong kết quả `getElementsAnnotatedWith(...)`.
2. Scanner vào `visitType(Customer)` và in tên kiểu.
3. `String name` là field đầu tiên. `asType()` trả kiểu `String`, tương ứng `DeclaredType` của `java.lang.String`.
4. `scores` có kiểu `java.util.List<? extends Number>`, tương ứng `DeclaredType` của `List`.
5. Đối số `scores.arg0` là `WildcardType`, vì type argument là `? extends Number`.
6. `getExtendsBound()` trả type `Number`, cũng là `DeclaredType`, nên có dòng `.extends.declared=Number`.
7. Trong ví dụ, processor lọc `FIELD`, nên nếu compiler có phần tử constructor ngầm định thì **nó không tạo ra dòng `field=`**.
8. Lệnh `-proc:only` yêu cầu `javac` thực hiện annotation processing mà không tiếp tục biên dịch `Customer.class`; đây là ví dụ kiểm tra cấu trúc, không phải ứng dụng có `main` để chạy bằng `java Customer`.

Ví dụ được thiết kế để có đầu ra trực quan; `System.out.println` dùng phục vụ học tập. Với processor thực tế, `Messager` phù hợp hơn để báo NOTE/WARNING/ERROR có tích hợp compiler.

## 8. Duyệt thêm mảng, type variable và nhiều bound

`PrintType` trong ví dụ chỉ triển khai **hai loại** `DeclaredType` và `WildcardType`. Đối với trường hợp tổng quát, phải tiếp tục bổ sung các override.

### Mảng với `visitArray`

Nếu một field có kiểu `String[][]`, `variable.asType()` là `ArrayType` của mảng ngoài. Mỗi lần gọi `getComponentType()` bỏ **một tầng** `[]`:

```java
@Override
public Void visitArray(javax.lang.model.type.ArrayType type, String path) {
    System.out.println(path + ".array");
    type.getComponentType().accept(this, path + ".component");
    return null;
}
```

Đây là một phương thức **bổ sung bên trong `PrintType`**, không phải một chương trình độc lập. Nếu duyệt `String[][]`, nó có thể in `.array` hai lần (mảng ngoài rồi mảng con), sau đó đến `.declared=String` của phần tử. `TypeVisitor` không tự đi qua các tầng mảng nếu bạn không viết bước đệ quy này.

### Biến kiểu với `visitTypeVariable`

Một khai báo generic:

```java
class Box<T extends Number> {
    T value;
}
```

`variable.asType()` của field `value` là `TypeVariable`. Muốn đi từ `T` đến upper bound, có thể override:

```java
@Override
public Void visitTypeVariable(
        javax.lang.model.type.TypeVariable type, String path) {
    System.out.println(path + ".variable=" +
            type.asElement().getSimpleName());
    type.getUpperBound().accept(this, path + ".upper");
    return null;
}
```

Đối với `T extends A & B`, `getUpperBound()` có thể là `IntersectionType`. Muốn thấy từng bound bên trong, triển khai thêm `visitIntersection` và gọi `getBounds()` trên từng `TypeMirror`.

### Intersection, union và executable types

```java
@Override
public Void visitIntersection(
        javax.lang.model.type.IntersectionType type, String path) {
    for (int i = 0; i < type.getBounds().size(); i++) {
        type.getBounds().get(i)
            .accept(this, path + ".bound" + i);
    }
    return null;
}
```

Với kiểu union trong multi-catch (`IOException | SQLException`), xử lý `UnionType.getAlternatives()`. Với kiểu phương thức, `ExecutableType` cho phép đọc return type, parameter types, thrown types và type variables.

Một trình duyệt tổng quát phải xác định **mục tiêu**: chỉ phân tích kiểu của field, hay còn muốn method signatures, constraints, superinterfaces, type parameters và type annotations. Không phải mọi nhánh đều cần cho tất cả processor.

### Cảnh giác vòng lặp đệ quy trong generic

Ví dụ `T extends Comparable<T>` có sự tự tham chiếu. Nếu cứ từ `TypeVariable T` đi vào upper bound `Comparable<T>` rồi vào argument `T` và lặp lại, chương trình có thể gây `StackOverflowError`.

Với visitor duyệt sâu cho dữ liệu thực tế, nên:

1. Theo dõi những type variable hoặc cấu trúc đang nằm trên **đường duyệt hiện tại**.
2. Khi gặp lại một nút thuộc chu trình, ghi nhận tham chiếu thay vì đi sâu vô hạn.
3. Nếu chỉ cần thông tin nông (ví dụ tên type argument), dừng ở đúng mức phục vụ nghiệp vụ.

`TypeMirror.toString()` không phải cách thay thế tốt cho phát hiện chu trình. Nên dựa trên semantics của `Types`, `Element` và một tập visited phù hợp mục tiêu; lưu mọi chuỗi type name làm khóa duy nhất có thể gộp nhầm những vị trí type-use khác nhau.

## 9. Khi nào dùng `ElementFilter`, visitor và scanner?

| Nhu cầu | Lựa chọn thích hợp |
| --- | --- |
| Chỉ tìm field trực tiếp của một class | `ElementFilter.fieldsIn(type.getEnclosedElements())`. |
| Chỉ lấy method trực tiếp | `ElementFilter.methodsIn(type.getEnclosedElements())`. |
| Chỉ xử lý một loại element, không cần duyệt con | `SimpleElementVisitor14` hoặc `switch(element.getKind())`. |
| Duyệt class và các khai báo thành viên lồng nhau | `ElementScanner14` với `super.visit...` thích hợp. |
| Phân tích kiểu tham số hóa, mảng, wildcard | `SimpleTypeVisitor14` hoặc một `TypeVisitor` có các override tương ứng. |
| Kiểm tra subtype hoặc assignability | `processingEnv.getTypeUtils()` (`Types.isSubtype`, `isAssignable`, ...), không parse `toString`. |
| Tìm khai báo theo tên chuẩn | `processingEnv.getElementUtils().getTypeElement(...)` khi phù hợp. |
| Cần phân tích biểu thức, câu lệnh hoặc thân phương thức | `javax.lang.model` **không phải AST đầy đủ**; với `javac`, cần xem `com.sun.source.util.Trees` hoặc `TreePathScanner` nếu mục tiêu là cú pháp nguồn. |

Visitor của `javax.lang.model` **không đồng nghĩa** visitor AST. `ElementScanner` duyệt **mô hình khai báo**, không tự mở mọi statement, `if`, vòng lặp, phép gán hay biểu thức trong thân method. `TypeVisitor` duyệt **cấu trúc kiểu**, không thực thi phương thức và không suy diễn đầy đủ mọi kiểu tại runtime.

## 10. Đọc annotation khi đang duyệt

Tại thời gian biên dịch, các đối tượng `Element` và `TypeMirror` đều có thể cho metadata annotation ở vị trí thích hợp. Hãy phân biệt:

```java
element.getAnnotationMirrors();
typeMirror.getAnnotationMirrors();
```

- `Element.getAnnotationMirrors()` đọc annotation trên **khai báo** đó, ví dụ `@InspectMe` của `Customer`.
- `TypeMirror.getAnnotationMirrors()` đọc **type annotation** nằm tại vị trí sử dụng kiểu, ví dụ `List<@Marker String>`; cần đi đến đúng nút `String` mới đọc annotation của kiểu ở vị trí đó.
- `AnnotationMirror` cho metadata ở mô hình compile time; không cần instantiate annotation object runtime.

Ví dụ nếu annotation có element giá trị mặc định:

```java
@Config(timeout = 1000)
class Endpoint {
}
```

Một processor có thể đọc `AnnotationMirror.getElementValues()` để lấy các cặp element được **ghi tường minh**. Muốn nhận cả giá trị default, sử dụng `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)`. Hai API không hoàn toàn tương đương.

`AnnotationValue` có phương thức `accept(AnnotationValueVisitor<R,P>,P)`. Khi cần xử lý nhiều loại giá trị annotation (primitive, string, enum constant, type literal, nested annotation, array), có thể dùng `SimpleAnnotationValueVisitor9`/họ visitor tương ứng thay vì dựa vào `toString()` của giá trị.

**Không nhầm** `AnnotationValueVisitor` với `ElementVisitor` hoặc `TypeVisitor`: hệ thứ ba này xử lý **giá trị bên trong annotation**. Ba tầng mô hình giúp processor vừa chọn đúng declaration, vừa đi đúng cấu trúc type, vừa giải mã metadata chính xác.

## 11. Truyền ngữ cảnh và xây dựng kết quả thay vì chỉ in

Ví dụ trên truyền `String path` qua tham số `P` của visitor kiểu. Trong code thực tế, ngữ cảnh có thể là một record Java 17:

```java
record VisitContext(String owner, String path, int depth) {
    VisitContext child(String segment) {
        return new VisitContext(owner, path + "." + segment, depth + 1);
    }
}
```

Khi đó có thể viết visitor `SimpleTypeVisitor14<Result, VisitContext>` để trả một cây `Result`, tích lũy cảnh báo, hoặc sinh tài liệu từ type model.

Lợi ích của cách này:

- Không cần dùng biến static mutable để theo dõi đang ở class/field nào.
- Có thể đưa tên owner, depth, cấu hình và tập visited theo đường duyệt một cách rõ ràng.
- Dễ viết unit test bằng cách đối chiếu cấu trúc kết quả hơn so với so khớp chuỗi log từ compiler.
- Cho phép nhiều lượt scan độc lập mà không chia sẻ trạng thái ngoài ý muốn.

`R` là kiểu của dữ liệu kết quả, `P` là kiểu ngữ cảnh. Nếu visitor có `R=Void`, trả `null` là đúng; đó không phải dấu hiệu xử lý thất bại.

Một lưu ý: ở `ElementScanner`, các method quét nhiều con **không mặc định cộng dồn mọi kết quả** thành danh sách cho bạn. Nếu muốn thu thập nhiều kết quả, hãy tự quyết định cấu trúc tích lũy phù hợp và thứ tự xử lý.

## 12. Phiên bản visitor và tính tương thích với Java 17+

API `javax.lang.model.util` có nhiều lớp mang hậu tố phiên bản: `ElementScanner6`, `ElementScanner7`, `ElementScanner8`, `ElementScanner9`, `ElementScanner14`; tương tự đối với `SimpleTypeVisitor...` và `SimpleElementVisitor...`. Các hậu tố chỉ cấp ngữ nghĩa xử lý của visitor theo **các language constructs được nhận diện tại version tương ứng**.

Không nên rút ra rằng processor luôn tự hiểu mọi construct Java mới chỉ vì đang chạy trên JDK mới. Ví dụ:

- Java 9 bổ sung một số phần tử liên quan tới module (`ModuleElement`).
- Java 14+ bổ sung support cho record component trong mô hình ngôn ngữ.
- Một visitor đời cũ gặp `ElementKind`/`TypeKind` mới có thể phải đi qua `visitUnknown` hoặc hành vi tương thích của lớp cha; không được giả định `visitType` có thể thay thế xử lý mọi kind mới.
- Chọn lớp visitor đủ mới cho source level bạn cần và xác định rõ chiến lược khi gặp phần tử chưa biết.

JDK 17 có `ElementScanner14` và `SimpleTypeVisitor14`, nên ví dụ dùng hai lớp này để dễ xử lý mã Java hiện đại hơn các visitor rất cũ. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` của processor mô tả ngôn ngữ mà processor hỗ trợ; nó **không tự nâng cấp** cách visitor duyệt phần tử mới.

Khi nâng phiên bản Java, cần chạy bộ test với cấu trúc mới (record, sealed classes, pattern...) và xác minh metadata compiler công bố; không suy luận từ tên hậu tố API rằng mọi cấu trúc đã được xử lý hoàn toàn.

## 13. Sai lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `ElementScanner` tự động duyệt generic `List<? extends Number>` | Scanner duyệt **khai báo element**; đối số generic cần duyệt bằng `TypeVisitor`/`TypeMirror`. |
| `SimpleTypeVisitor` tự động đi xuống mọi argument và bound | Chỉ dispatch theo loại; muốn đệ quy phải override và gọi `accept(...)` trên con. |
| Override `visitType` nhưng quên `super.visitType` | Mất bước scan phần tử con do scanner cung cấp. |
| `visitVariable` chỉ được gọi cho field | `VariableElement` còn có parameter, enum constant... cần xét `ElementKind`. |
| Cast mọi `TypeMirror` sang `DeclaredType` | Mảng, wildcard, type variable, primitive, union... cần nhánh khác. |
| `getEnclosedElements()` là toàn bộ các member kế thừa | Chỉ các phần tử khai báo/được chứa ở vị trí hiện tại; muốn kế thừa phải dùng mô hình `Elements` phù hợp. |
| `getRootElements()` luôn là tất cả source của mọi round | Root thay đổi theo round; file vừa được sinh có thể thành input của round sau. |
| Parse `typeMirror.toString()` để tìm `<`, `?`, `[]` | Không ổn định, dễ sai với kiểu lồng nhau, annotation, generic phức tạp; dùng API cấu trúc. |
| Dùng `Class.forName(...)` để đọc class đang được biên dịch | Class có thể chưa được sinh bytecode; dùng `TypeElement`, `TypeMirror`. |
| Nghĩ `ElementVisitor` duyệt toàn bộ thân method như AST | Không; muốn phân tích syntax tree cần API `Trees`/`TreePathScanner` thích hợp. |
| Xử lý `T extends Comparable<T>` bằng đệ quy vô hạn | Phát hiện chu trình hoặc giới hạn traversal hợp lý. |
| `Element.getAnnotationMirrors()` có đủ các type-use annotation sâu trong generic | Cần xuống đúng `TypeMirror` con rồi đọc annotation tại vị trí tương ứng. |
| Tin `SimpleElementVisitor9` tự hỗ trợ trọn vẹn record Java 17 | Chọn visitor phiên bản phù hợp và test các kind mới. |

## 14. Bài tập tự kiểm tra

Cho ví dụ (chỉ là snippet minh họa):

```java
class Container<K extends Number> {
    java.util.Map<String, java.util.List<? super K>> values;
}
```

Hãy trả lời:

1. `Container` thuộc loại element nào? **`TypeElement`**.
2. `values` thuộc loại element nào? **`VariableElement` với `ElementKind.FIELD`**.
3. `values.asType()` là loại `TypeMirror` nào? **`DeclaredType`** của `Map`.
4. Đối số thứ hai của `Map` là gì? **Một `DeclaredType` khác**, `List<? super K>`.
5. Đối số thứ nhất của `List` là gì? **`WildcardType`** với lower bound `K`.
6. Kiểu của `K` ở lower bound đó là gì? **`TypeVariable`**.
7. Muốn biết upper bound của `K` tại khai báo generic thì dùng gì? **Thông tin `TypeParameterElement.getBounds()` hoặc `TypeVariable.getUpperBound()`**, và xử lý thêm intersection khi có nhiều bound.
8. Nên chọn `ElementScanner` hay `TypeVisitor` để lấy wildcard `? super K`? **`TypeVisitor`**, sau khi lấy `TypeMirror` của field từ phần tử.
9. Khi chỉ muốn lấy field trực tiếp, có cần tự viết scanner không? **Không**; có thể dùng `ElementFilter.fieldsIn(type.getEnclosedElements())`.
10. Muốn tìm annotation trên chính khai báo field và annotation ở argument `String`, dùng chung một phép `getAnnotationMirrors()` không? **Không**; cần đọc đúng `Element` hay `TypeMirror` tại từng vị trí.
11. Processor có cần class `Container.class` tồn tại ở runtime để đọc generic đó không? **Không**; processor làm việc với language model lúc biên dịch.

Ghi nhớ quy trình: **chọn đúng root `Element` → duyệt cây khai báo bằng `ElementScanner` → tại vị trí cần phân tích kiểu, lấy `TypeMirror` → dispatch bằng `TypeVisitor` → xử lý giá trị annotation bằng các API `AnnotationMirror`/`AnnotationValue` khi cần**. Cách tổ chức này giúp processor có thể phân tích code thực mà không suy diễn từ chuỗi in kiểu.

## Tài liệu chính thức

- [Java SE 17 — `ElementVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ElementVisitor.html)
- [Java SE 17 — `ElementScanner14`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/ElementScanner14.html)
- [Java SE 17 — `SimpleElementVisitor14`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/SimpleElementVisitor14.html)
- [Java SE 17 — `TypeVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeVisitor.html)
- [Java SE 17 — `SimpleTypeVisitor14`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/SimpleTypeVisitor14.html)
- [Java SE 17 — `ElementFilter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/ElementFilter.html)
